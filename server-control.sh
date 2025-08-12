#!/bin/bash

# 서버 애플리케이션 제어 스크립트
APP_NAME="aws_upload-0.0.1-SNAPSHOT.jar"
APP_DIR="/home/service"
LOG_FILE="${APP_DIR}/app.log"
PID_FILE="${APP_DIR}/app.pid"

# 함수들
start_app() {
    echo "🚀 애플리케이션 시작 중..."
    
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "⚠️ 애플리케이션이 이미 실행 중입니다 (PID: $(cat $PID_FILE))"
        return 1
    fi
    
    cd "$APP_DIR"
    nohup java -Xms256m -Xmx512m -Duser.timezone=Asia/Seoul -jar "$APP_NAME" > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    
    sleep 3
    if kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "✅ 애플리케이션이 시작되었습니다 (PID: $(cat $PID_FILE))"
    else
        echo "❌ 애플리케이션 시작 실패"
        rm -f "$PID_FILE"
        return 1
    fi
}

stop_app() {
    echo "🛑 애플리케이션 중지 중..."
    
    if [ ! -f "$PID_FILE" ]; then
        echo "⚠️ PID 파일을 찾을 수 없습니다. 프로세스 이름으로 종료를 시도합니다..."
        pkill -f "$APP_NAME"
        sleep 2
        if pgrep -f "$APP_NAME" > /dev/null; then
            echo "❌ 애플리케이션 중지 실패"
            return 1
        else
            echo "✅ 애플리케이션이 중지되었습니다"
            return 0
        fi
    fi
    
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        sleep 2
        
        if kill -0 "$PID" 2>/dev/null; then
            echo "⚠️ 강제 종료를 시도합니다..."
            kill -9 "$PID"
            sleep 1
        fi
        
        if kill -0 "$PID" 2>/dev/null; then
            echo "❌ 애플리케이션 중지 실패"
            return 1
        else
            echo "✅ 애플리케이션이 중지되었습니다"
            rm -f "$PID_FILE"
        fi
    else
        echo "⚠️ 프로세스가 이미 종료되었습니다"
        rm -f "$PID_FILE"
    fi
}

restart_app() {
    echo "🔄 애플리케이션 재시작 중..."
    stop_app
    sleep 2
    start_app
}

status_app() {
    echo "📊 애플리케이션 상태 확인..."
    
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        PID=$(cat "$PID_FILE")
        echo "✅ 애플리케이션이 실행 중입니다 (PID: $PID)"
        
        # 포트 확인
        if netstat -tulpn 2>/dev/null | grep ":8080" | grep -q "$PID"; then
            echo "🌐 포트 8080에서 서비스 중"
        fi
        
        # 메모리 사용량
        if command -v ps >/dev/null; then
            MEMORY=$(ps -o pid,rss,pmem -p "$PID" | tail -1)
            echo "💾 메모리 사용량: $MEMORY"
        fi
    else
        echo "❌ 애플리케이션이 실행되지 않음"
        rm -f "$PID_FILE"
    fi
}

show_logs() {
    echo "📋 애플리케이션 로그 (최근 20줄):"
    if [ -f "$LOG_FILE" ]; then
        tail -20 "$LOG_FILE"
    else
        echo "⚠️ 로그 파일을 찾을 수 없습니다: $LOG_FILE"
    fi
}

# 메인 로직
case "$1" in
    start)
        start_app
        ;;
    stop)
        stop_app
        ;;
    restart)
        restart_app
        ;;
    status)
        status_app
        ;;
    logs)
        show_logs
        ;;
    *)
        echo "사용법: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "명령어:"
        echo "  start   - 애플리케이션 시작"
        echo "  stop    - 애플리케이션 중지"
        echo "  restart - 애플리케이션 재시작"
        echo "  status  - 애플리케이션 상태 확인"
        echo "  logs    - 로그 보기"
        exit 1
        ;;
esac

exit $?