#!/bin/bash

# AWS 배포 설정
EC2_USER="ec2-user"
EC2_HOST="15.164.221.43"  # 실제 EC2 IP로 변경
KEY_FILE="~/.ssh/aws-seoul.pem"  # 실제 키 파일 경로로 변경
APP_NAME="aws_upload-0.0.1-SNAPSHOT.jar"
REMOTE_DIR="/home/service"
LOCAL_JAR="build/libs/${APP_NAME}"

echo "🚀 AWS 배포 시작..."

# 1. 프로젝트 빌드
echo "📦 프로젝트 빌드 중..."
./gradlew clean build
if [ $? -ne 0 ]; then
    echo "❌ 빌드 실패"
    exit 1
fi
echo "✅ 빌드 완료"

# 2. JAR 파일 업로드
echo "📤 JAR 파일 업로드 중..."
scp -i "${KEY_FILE}" "${LOCAL_JAR}" "${EC2_USER}@${EC2_HOST}:${REMOTE_DIR}/"
if [ $? -ne 0 ]; then
    echo "❌ 업로드 실패"
    exit 1
fi
echo "✅ 업로드 완료"

# 3. 서버에서 애플리케이션 재시작
echo "🔄 서버 재시작 중..."
ssh -i "${KEY_FILE}" "${EC2_USER}@${EC2_HOST}" << 'EOF'
    cd /home/service
    
    # 기존 프로세스 종료
    echo "🛑 기존 프로세스 종료..."
    pkill -f aws_upload
    sleep 2
    
    # 새 애플리케이션 시작
    echo "▶️ 새 애플리케이션 시작..."
    nohup java -Xms256m -Xmx512m -Duser.timezone=Asia/Seoul -jar aws_upload-0.0.1-SNAPSHOT.jar > app.log 2>&1 &
    
    # 시작 확인
    sleep 3
    if pgrep -f aws_upload > /dev/null; then
        echo "✅ 애플리케이션이 성공적으로 시작되었습니다"
    else
        echo "❌ 애플리케이션 시작 실패"
        exit 1
    fi
EOF

if [ $? -eq 0 ]; then
    echo "🎉 배포 성공!"
    echo "🔗 테스트: curl http://${EC2_HOST}:8080/users/test"
else
    echo "❌ 배포 실패"
    exit 1
fi