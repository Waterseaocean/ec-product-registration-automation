from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


class Handler(BaseHTTPRequestHandler):
    # [S01] HTTP応答：BaseHTTPRequestHandlerを継承し、GET時の処理を定義。
    def do_GET(self):
        # __file__はこのPythonファイル。隣のHTMLをバイト列として読み出す。
        body = Path(__file__).with_name('mock.html').read_bytes()
        # 200＝成功。ヘッダーで形式・文字コードを伝え、本文を送信する。
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        # 標準のアクセスログを抑制。passは何もせず通る文。
        pass


@contextmanager
def serve(port=0):
    # [S02] サーバーの寿命管理。0ならOSに空きポートを選ばせる。
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    # サーバーの待ち受けを別スレッドで動かし、ブラウザ操作と並行させる。
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # yieldより前で準備し、withのasへURLを渡す。with終了後にfinallyへ進む。
        yield f'http://127.0.0.1:{server.server_port}/'
    finally:
        # 停止要求→ポート解放→スレッド終了を待つ、の順に片付ける。
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    # [S03] 手動起動だけ固定8765番を使用。自動化側からのserve()は空きポート。
    with serve(8765) as url:
        print(url, flush=True)
        import threading
        # Ctrl+Cなどで終了するまで待機する。
        threading.Event().wait()
