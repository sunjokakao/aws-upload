#!/bin/bash

# 가상환경 활성화
source venv/bin/activate

# 패키지 설치
pip install -r requirements.txt

echo "설치 완료! 이제 다음 명령어로 서버를 실행하세요:"
echo "source venv/bin/activate"
echo "python3 app.py"