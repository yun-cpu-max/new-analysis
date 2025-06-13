from flask import Flask, jsonify
from threading import Thread
from daily_news_analyzer import run_daily_analysis

app = Flask(__name__)

# 백그라운드에서 실행할 함수
def background_analysis():
    try:
        run_daily_analysis()
    except Exception as e:
        # 필요하다면 로그로 저장 가능
        print(f"[ERROR] 분석 중 오류 발생: {e}")

@app.route('/run-news-analysis', methods=['POST'])
def run_news_analysis():
    try:
        # 백그라운드 스레드에서 실행
        thread = Thread(target=background_analysis)
        thread.start()

        # 즉시 응답 반환
        return jsonify({
            'status': 'started',
            'message': '분석이 백그라운드에서 시작되었습니다.'
        }), 202
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'스레드 실행 중 오류 발생: {str(e)}'
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
