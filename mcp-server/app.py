import os
import json
import hmac
import hashlib
import time
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
import boto3
from threading import Thread
import openai
import re
import requests

# 환경 변수 로드
load_dotenv()

# OpenAI 설정
openai_api_key = os.environ.get("OPENAI_API_KEY")
if openai_api_key and openai_api_key != "your-openai-api-key":
    openai.api_key = openai_api_key

app = Flask(__name__)

# Slack 클라이언트 초기화
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")

print(f"Bot Token 확인: {SLACK_BOT_TOKEN[:10]}..." if SLACK_BOT_TOKEN else "Bot Token이 설정되지 않음")

slack_client = WebClient(token=SLACK_BOT_TOKEN)

# AWS 클라이언트 초기화
aws_region = os.environ.get("AWS_REGION", "ap-northeast-2")

def verify_slack_request(request):
    """Slack 요청 검증"""
    timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
    signature = request.headers.get('X-Slack-Signature', '')
    
    # 타임스탬프 검증 (5분 이내)
    if abs(time.time() - float(timestamp)) > 60 * 5:
        return False
    
    # 서명 검증
    sig_basestring = f"v0:{timestamp}:{request.get_data(as_text=True)}"
    my_signature = 'v0=' + hmac.new(
        SLACK_SIGNING_SECRET.encode('utf-8'),
        sig_basestring.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(my_signature, signature)

@app.route('/slack/events', methods=['POST'])
def slack_events():
    """Slack 이벤트 처리"""
    # 요청 검증
    if not verify_slack_request(request):
        return jsonify({'error': 'Invalid request'}), 403
    
    data = request.json
    
    # URL 검증 처리
    if data.get('type') == 'url_verification':
        return jsonify({'challenge': data['challenge']})
    
    # 이벤트 처리
    if data.get('type') == 'event_callback':
        event = data['event']
        
        # 봇 자신의 메시지는 무시
        if event.get('bot_id'):
            return jsonify({'status': 'ok'}), 200
        
        # 비동기로 메시지 처리
        Thread(target=handle_message, args=(event,)).start()
        
        return jsonify({'status': 'ok'}), 200
    
    return jsonify({'status': 'ok'}), 200

def handle_message(event):
    """메시지 이벤트 처리"""
    channel = event.get('channel')
    user = event.get('user')
    text = event.get('text', '')
    thread_ts = event.get('thread_ts', event.get('ts'))
    
    # 디버깅: 이벤트 정보 출력
    print(f"이벤트 수신 - 채널: {channel}, 사용자: {user}, 텍스트: {text}")
    
    # 특정 채널에서만 작동하도록 설정 (선택사항)
    ALLOWED_CHANNELS = os.environ.get('ALLOWED_CHANNELS', '').split(',')
    ALLOWED_CHANNELS = [ch.strip() for ch in ALLOWED_CHANNELS if ch.strip()]  # 공백 제거
    
    print(f"허용된 채널: {ALLOWED_CHANNELS}")
    
    if ALLOWED_CHANNELS and channel not in ALLOWED_CHANNELS:
        # 허용된 채널이 아니면 무시
        print(f"채널 {channel}은(는) 허용되지 않음. 무시.")
        return
    
    try:
        # 봇 멘션 확인
        bot_user_id = get_bot_user_id()
        is_mention = f"<@{bot_user_id}>" in text
        is_dm = event.get('channel_type') == 'im'
        
        # 특정 채널에서는 멘션 없이도 모든 메시지에 반응 (선택사항)
        MONITOR_CHANNELS = os.environ.get('MONITOR_CHANNELS', '').split(',')
        is_monitor_channel = channel in MONITOR_CHANNELS
        
        # 특정 키워드 확인 (ALLOWED_CHANNELS에서만)
        is_keyword_trigger = False
        if ALLOWED_CHANNELS and channel in ALLOWED_CHANNELS:
            # "api 호출" 키워드가 있는지 확인
            if 'api 호출' in text.lower() or 'api호출' in text.lower():
                is_keyword_trigger = True
                print(f"키워드 'api 호출' 감지됨")
            # 짧은 영문/숫자만 입력한 경우도 처리 (상품번호로 추정)
            elif re.match(r'^[a-zA-Z0-9\-]+$', text.strip()) and len(text.strip()) < 20:
                is_keyword_trigger = True
                print(f"상품번호로 추정되는 입력 감지: {text.strip()}")
        
        if not is_mention and not is_dm and not is_monitor_channel and not is_keyword_trigger:
            return
        
        # 멘션 제거
        clean_text = text.replace(f"<@{bot_user_id}>", "").strip()
        
        # 사용자 의도 파악 및 처리
        print(f"처리할 텍스트: {clean_text}")
        response = process_user_request(clean_text, user)
        print(f"응답 준비됨: {response}")
        
        # Slack에 응답 전송 (스레드로)
        try:
            result = slack_client.chat_postMessage(
                channel=channel,
                text=response['text'],
                blocks=response.get('blocks'),
                thread_ts=event.get('ts')  # 원본 메시지의 타임스탬프를 사용하여 스레드 생성
            )
            print(f"메시지 전송 성공: {result['ok']}")
        except SlackApiError as e:
            print(f"Slack API 오류: {e.response['error']}")
            raise
        
    except Exception as e:
        print(f"Error handling message: {e}")
        slack_client.chat_postMessage(
            channel=channel,
            text=f"죄송합니다. 오류가 발생했습니다: {str(e)}",
            thread_ts=thread_ts
        )

def get_bot_user_id():
    """봇 User ID 가져오기"""
    try:
        response = slack_client.auth_test()
        return response['user_id']
    except SlackApiError as e:
        print(f"Error getting bot user ID: {e}")
        return None

def process_user_request(text, user_id):
    """사용자 요청 처리"""
    text_lower = text.lower()
    
    # "api 호출" 키워드 확인
    if 'api 호출' in text_lower or 'api호출' in text_lower:
        # 상품번호가 포함되어 있는지 확인 (숫자나 영문)
        # 텍스트에서 상품번호 추출 시도 (숫자, 영문, 하이픈 등)
        pattern = r'(?:상품번호|번호|제품번호|id)[\s:：]*([a-zA-Z0-9\-]+)'
        match = re.search(pattern, text, re.IGNORECASE)
        
        if match:
            product_id = match.group(1)
            return call_user_api(product_id)
        else:
            # 상품번호가 없으면 물어보기
            return {
                'text': '상품번호를 알려주세요.',
                'blocks': [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "🔍 *상품 정보를 조회하겠습니다.*\n\n조회할 상품번호를 입력해주세요.\n(예: aa, bb, 123 등)"
                        }
                    }
                ]
            }
    
    # 상품번호만 입력한 경우 (이전 대화 맥락에서)
    # 간단한 패턴: 짧은 영문/숫자 조합
    if re.match(r'^[a-zA-Z0-9\-]+$', text.strip()) and len(text.strip()) < 20:
        return call_user_api(text.strip())
    
    # OpenAI API 키가 있으면 AI 처리, 없으면 키워드 기반 처리
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    if openai_key and openai_key != "your-openai-api-key":
        try:
            # AI를 사용한 의도 분석
            intent = analyze_user_intent(text)
            
            # 의도에 따른 처리
            if intent['confidence'] < 0.7:
                return {
                    'text': f"요청을 정확히 이해하지 못했습니다. 다시 말씀해 주시겠어요?\n\n이해한 내용: {intent.get('action', '알 수 없음')}"
                }
            
            return execute_intent_action(intent, user_id)
            
        except Exception as e:
            print(f"AI 처리 중 오류: {e}")
            # AI 오류 시 키워드 기반으로 폴백
    
    # 키워드 기반 처리 (기존 코드)
    if 's3' in text_lower and ('목록' in text or 'list' in text_lower):
        return handle_s3_list()
    elif 'dynamodb' in text_lower or '데이터베이스' in text:
        return handle_dynamodb_query(user_id)
    elif '도움말' in text or 'help' in text_lower:
        return handle_help()
    else:
        return {
            'text': '무엇을 도와드릴까요? 다음 명령어를 사용할 수 있습니다:\n• API 호출\n• S3 버킷 목록\n• DynamoDB 조회\n• 도움말'
        }

def handle_s3_list():
    """S3 버킷 목록 조회"""
    try:
        s3 = boto3.client('s3')
        response = s3.list_buckets()
        
        buckets = response['Buckets']
        
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*S3 버킷 목록* (총 {len(buckets)}개)"
                }
            }
        ]
        
        for bucket in buckets[:10]:  # 최대 10개만 표시
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"• `{bucket['Name']}` - 생성일: {bucket['CreationDate'].strftime('%Y-%m-%d')}"
                }
            })
        
        return {
            'text': f'S3 버킷 {len(buckets)}개를 찾았습니다.',
            'blocks': blocks
        }
        
    except Exception as e:
        return {'text': f'S3 조회 중 오류가 발생했습니다: {str(e)}'}

def handle_dynamodb_query(user_id):
    """DynamoDB 조회 예제"""
    # 실제 구현시 테이블명과 조건을 동적으로 처리
    return {
        'text': 'DynamoDB 조회 기능은 준비 중입니다.',
        'blocks': [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*DynamoDB 조회*\n이 기능은 곧 추가될 예정입니다."
                }
            }
        ]
    }

def handle_help():
    """도움말 표시"""
    return {
        'text': '사용 가능한 명령어',
        'blocks': [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*🤖 AWS 봇 사용법*\n저를 멘션하거나 DM으로 다음과 같이 말씀해주세요:"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "• `API 호출` - 상품 정보 조회\n• `S3 버킷 목록 보여줘`\n• `DynamoDB 데이터 조회`\n• `도움말`"
                }
            }
        ]
    }

def call_user_api(product_id):
    """사용자 API 호출"""
    try:
        # API 엔드포인트
        api_url = f"http://15.164.221.43:8080/users/{product_id}"
        
        print(f"API 호출: {api_url}")
        
        # API 호출
        response = requests.get(api_url, timeout=10)
        
        # 응답 처리
        if response.status_code == 200:
            # Content-Type 확인
            content_type = response.headers.get('Content-Type', '')
            
            if 'application/json' in content_type:
                # JSON 응답 처리
                data = response.json()
                response_text = json.dumps(data, indent=2, ensure_ascii=False)
            else:
                # 텍스트 응답 처리
                response_text = response.text
            
            # 응답 포맷팅
            return {
                'text': f'상품번호 {product_id}의 정보를 조회했습니다.',
                'blocks': [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"✅ *상품 정보 조회 완료*\n상품번호: `{product_id}`"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"```{response_text}```"
                        }
                    }
                ]
            }
        elif response.status_code == 404:
            return {
                'text': f'상품번호 {product_id}를 찾을 수 없습니다.',
                'blocks': [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"❌ *조회 실패*\n상품번호 `{product_id}`를 찾을 수 없습니다."
                        }
                    }
                ]
            }
        else:
            return {
                'text': f'API 호출 중 오류가 발생했습니다. (상태코드: {response.status_code})',
                'blocks': [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"⚠️ *API 오류*\n상태코드: {response.status_code}\n응답: {response.text}"
                        }
                    }
                ]
            }
            
    except requests.exceptions.Timeout:
        return {'text': '⏱️ API 요청 시간이 초과되었습니다.'}
    except requests.exceptions.ConnectionError:
        return {'text': '🔌 API 서버에 연결할 수 없습니다.'}
    except Exception as e:
        print(f"API 호출 오류: {e}")
        return {'text': f'❌ 오류가 발생했습니다: {str(e)}'}

def analyze_user_intent(text):
    """OpenAI를 사용한 사용자 의도 분석"""
    try:
        # GPT-3.5 또는 GPT-4 사용
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": """당신은 AWS 서비스 요청을 분석하는 어시스턴트입니다.
사용자의 자연어 요청을 분석하여 다음 형식의 JSON으로 변환하세요:
{
  "action": "AWS 작업 유형",
  "parameters": {"필요한 파라미터들"},
  "confidence": 0.0-1.0 사이의 확신도
}

가능한 action 값:
- list_s3: S3 버킷 목록 조회
- query_dynamodb: DynamoDB 조회
- help: 도움말 요청
- unknown: 알 수 없는 요청

예시:
- "S3 버킷들 보여줘" → {"action": "list_s3", "parameters": {}, "confidence": 0.95}
- "버킷 목록 알려줘" → {"action": "list_s3", "parameters": {}, "confidence": 0.9}
- "데이터베이스 조회" → {"action": "query_dynamodb", "parameters": {}, "confidence": 0.85}"""
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            temperature=0.3,
            max_tokens=200
        )
        
        # 응답 파싱
        result = json.loads(response.choices[0].message.content)
        return result
        
    except Exception as e:
        print(f"OpenAI API 오류: {e}")
        # 기본값 반환
        return {
            "action": "unknown",
            "parameters": {},
            "confidence": 0.0
        }

def execute_intent_action(intent, user_id):
    """분석된 의도에 따라 액션 실행"""
    action = intent.get('action', 'unknown')
    
    if action == 'list_s3':
        return handle_s3_list()
    elif action == 'query_dynamodb':
        return handle_dynamodb_query(user_id)
    elif action == 'help':
        return handle_help()
    else:
        # AI가 이해하지 못한 경우 친절한 응답
        return {
            'text': '죄송합니다. 요청을 이해하지 못했습니다.',
            'blocks': [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "😅 요청을 이해하지 못했습니다.\n\n다음과 같이 말씀해보세요:"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "• `S3 버킷 목록을 보여줘`\n• `데이터베이스 조회해줘`\n• `도움말`"
                    }
                }
            ]
        }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port, debug=True)