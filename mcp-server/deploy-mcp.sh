#!/bin/bash

# AWS 배포 설정
EC2_USER="ec2-user"
EC2_HOST="15.164.221.43"
KEY_FILE="~/.ssh/aws-seoul.pem"
REMOTE_DIR="/home/service/mcp-server"

echo "🚀 MCP 서버 AWS 배포 시작..."

# 1. 원격 디렉토리 생성
echo "📁 원격 디렉토리 생성 중..."
ssh -i "${KEY_FILE}" "${EC2_USER}@${EC2_HOST}" "mkdir -p ${REMOTE_DIR}"

# 2. 파일 업로드
echo "📤 파일 업로드 중..."
scp -i "${KEY_FILE}" -r \
    app.py \
    requirements.txt \
    .env.example \
    "${EC2_USER}@${EC2_HOST}:${REMOTE_DIR}/"

if [ $? -ne 0 ]; then
    echo "❌ 업로드 실패"
    exit 1
fi

# 3. 서버 설정 및 시작
echo "🔧 서버 설정 중..."
ssh -i "${KEY_FILE}" "${EC2_USER}@${EC2_HOST}" << 'EOF'
    cd /home/service/mcp-server
    
    # Python 환경 확인
    if ! command -v python3 &> /dev/null; then
        echo "Python3 설치 중..."
        sudo yum install -y python3 python3-pip
    fi
    
    # 가상환경 생성
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    
    # 패키지 설치
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    
    # .env 파일 확인
    if [ ! -f ".env" ]; then
        echo "⚠️  .env 파일을 생성해주세요:"
        echo "cp .env.example .env"
        echo "그리고 실제 값을 입력하세요"
    fi
    
    # 기존 프로세스 종료
    pkill -f "app.py" || true
    
    # 새 프로세스 시작
    nohup python3 app.py > mcp.log 2>&1 &
    
    sleep 3
    if pgrep -f "app.py" > /dev/null; then
        echo "✅ MCP 서버가 성공적으로 시작되었습니다"
        echo "📋 로그 확인: tail -f /home/service/mcp-server/mcp.log"
    else
        echo "❌ MCP 서버 시작 실패"
        tail -n 20 mcp.log
    fi
EOF

echo "🎉 배포 완료!"
echo "📌 다음 단계:"
echo "1. SSH로 접속: ssh -i ${KEY_FILE} ${EC2_USER}@${EC2_HOST}"
echo "2. .env 파일 설정: cd /home/service/mcp-server && vi .env"
echo "3. Slack Event URL 업데이트: http://${EC2_HOST}:3000/slack/events"