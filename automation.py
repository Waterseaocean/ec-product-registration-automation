"""模擬EC画面専用。実ECへの汎用自動接続は行わない。"""
import argparse
import json
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, expect
from rules import reason

# [P01] 基準フォルダ：実行した場所ではなく、このファイルの場所を使う。
ROOT = Path(__file__).parent


def run(page, url, output, execute=False, keyword='', max_pages=20):
    # [P02] 実行状態の準備。pageは操作対象、execute=Falseなら予約しない。
    output = Path(output)
    # parents=Trueは親も作成、exist_ok=Trueは作成済みでもエラーにしない。
    output.mkdir(parents=True, exist_ok=True)
    # []は順序付きリスト、set()は重複しない集合。商品IDと一覧の並びを別々に記憶。
    decisions, completed, seen, pages = [], [], set(), set()
    # 辞書にログを集約。decisions/completedは上のリストと同じ実体を参照する。
    result = {'mode': 'execute' if execute else 'dry-run', 'status': 'running',
              'decisions': decisions, 'completed': completed, 'pending_verification': []}
    # 単位はミリ秒。毎回3秒待つのではなく、対象操作の既定待ち時間上限。
    page.set_default_timeout(3000)
    try:
        # [P03] 検索：ラベルで入力欄、役割と名前でボタンを探して操作。
        page.goto(url)
        page.get_by_label('検索キーワード').fill(keyword)
        page.get_by_label('最低価格').fill('0')
        # exact=Trueは「検索」を完全一致で探す指定。
        page.get_by_role('button', name='検索', exact=True).click()
        # [P04] 一覧の反復：range(20)は最大20回、_は回数の値を使わない慣例。
        for _ in range(max_pages):
            # exists()はファイルの有無。raiseで異常経路へ移動する。
            if (ROOT / 'STOP').exists():
                raise RuntimeError('STOPファイルによる停止')
            # CSSセレクター：tbody（表本文）の中のtr（行）を探す。
            rows = page.locator('tbody tr')
            # nth(i)は0始まりのi番目。商品IDの並びを変更できないタプルにする。
            signature = tuple(rows.nth(i).get_attribute('data-id') for i in range(rows.count()))
            # 同じ並びが再出現したら、ページ送りの循環とみなして停止。
            if signature in pages:
                raise RuntimeError('同じ一覧が再出現')
            pages.add(signature)
            # 今のページの対象ID。次のページでは空に戻す。
            selected = []
            # [P05] 商品読取：各行のdata-*属性からPythonの辞書を作る。
            for i in range(rows.count()):
                row = rows.nth(i)
                # 辞書内包表記：4つの属性名を順に組み立て、名前:値へ変換。
                p = {k: row.get_attribute('data-' + k) for k in ('id', 'name', 'price', 'stock')}
                state = row.get_attribute('data-registered')
                # 不明な状態を勝手に未登録と判断しない。
                if state not in ('true', 'false'):
                    raise ValueError('登録状態不明')
                # HTMLの文字列'true'/'false'をPythonのTrue/Falseへ変換。
                p['registered'] = state == 'true'
                # [P06] 選別・選択：reason()は除外理由、対象ならNoneを返す。
                why = reason(p)
                if p['id'] in seen:
                    why = '重複ID'
                # seenは予約成功IDではなく、今回見た全IDを記録する集合。
                seen.add(p['id'])
                # NoneならON、それ以外はOFF。クリック反転ではなく状態を指定。
                row.get_by_role('checkbox').set_checked(why is None)
                # orは理由がNoneなら表示用の「対象」を使う。appendは1件追加。
                decisions.append({'id': p['id'], 'reason': why or '対象'})
                if why is None:
                    selected.append(p['id'])
            # [P07] 予約・確認：空リストは条件判定でFalseなので、対象0件なら通らない。
            if execute and selected:
                # 一覧開始時だけでなく、外部への書き込み直前にも停止要求を確認。
                if (ROOT / 'STOP').exists():
                    raise RuntimeError('予約直前に停止')
                dialog_ok = []
                # コールバック：ダイアログが出たときにPlaywrightがこの関数を呼ぶ。
                def confirm(dialog):
                    # f文字列は{}内の値を埋め込む。len()は対象件数。
                    expected = f'{len(selected)}件を予約登録しますか？'
                    ok = dialog.type == 'confirm' and dialog.message == expected
                    # 外側のリストに結果を残す。関数終了後にも呼び出し元から読める。
                    dialog_ok.append(ok)
                    # 条件式：一致ならOK、不一致ならキャンセル。
                    dialog.accept() if ok else dialog.dismiss()
                # confirm()ではなくconfirmを渡す。今は呼ばず、次の発生時に1回呼ぶ。
                page.once('dialog', confirm)
                # 送信前にコピーを記録し、成功確認まで「結果不明」の可能性を残す。
                result['pending_verification'] = selected.copy()
                page.get_by_role('button', name='選択商品を予約登録').click()
                if dialog_ok != [True]:
                    # 教材では想定外の確認を拒否した場合、この未確認リストを空にする。
                    result['pending_verification'] = []
                    raise RuntimeError('確認ポップアップが想定外')
                # [P08] 成功照合：ボタンを押せたことと、予約が成功したことを分ける。
                # join()でIDをカンマ連結。expectは期待する表示になるまで再確認する。
                expect(page.get_by_role('status')).to_have_text('予約完了: ' + ','.join(selected))
                for product_id in selected:
                    # CSSの属性セレクターで該当IDの行だけを指定し、登録状態も検査。
                    expect(page.locator(f'tr[data-id="{product_id}"]')).to_have_attribute('data-registered', 'true')
                # 全件確認できてから成功IDを追加。extendはリストの要素をまとめて追加。
                completed.extend(selected)
                result['pending_verification'] = []
            # [P09] 最終ページ判定とページ送り。
            next_button = page.get_by_role('button', name='次の一覧')
            if next_button.is_disabled():
                result['status'] = 'success'
                # breakは一覧のforを終了し、下のforに付いたelseも実行しない。
                break
            next_button.click()
        else:
            # このelseはifではなくforに対応。上限までbreakしなかった場合だけ実行。
            raise RuntimeError('ページ上限に到達')
    # [P10] 異常時の証跡と、正常・異常どちらでも行うJSON保存。
    except Exception as exc:
        result.update(status='stopped', error=str(exc))
        page.screenshot(path=str(output / 'error.png'), full_page=True)
        # 捕まえた例外を再び外へ伝え、成功扱いにしない。
        raise
    finally:
        # dumpsで辞書→JSON文字列。日本語をそのまま、2文字字下げ、UTF-8で保存。
        (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    # 例外が外へ伝わった場合はここへ到達しない。正常時のみ結果を返す。
    return result


def main():
    # [P11] CLI引数：利用者がコマンド末尾へ付けた指定を読み取る。
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    # store_trueは指定があればTrue、指定しなければFalse。
    parser.add_argument('--execute', action='store_true', help='模擬画面で予約登録を行う')
    parser.add_argument('--headed', action='store_true')
    parser.add_argument('--keyword', default='')
    parser.add_argument('--scenario', choices=['empty', 'error', 'loop', 'unknown', 'duplicate'])
    args = parser.parse_args()
    from mock_server import serve
    # [P12] 実行環境の開始と終了。withは終了時の後片付けを組にする。
    with serve() as url, sync_playwright() as pw:
        # notで真偽を反転。--headedならheadless=Falseとなり画面を表示。
        browser = pw.chromium.launch(headless=not args.headed)
        page = browser.new_page()
        # Pathの/はパス結合。%fはマイクロ秒で、実行ごとに保存先を分ける。
        output = ROOT / 'runs' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        try:
            # シナリオ指定時だけURLへクエリーを追加。名前付き引数で実行条件を渡す。
            result = run(page, url + ('?scenario=' + args.scenario if args.scenario else ''), output,
                         execute=args.execute, keyword=args.keyword)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            # run()が失敗しても保存先を表示し、ブラウザを閉じる。
            print('記録:', output)
            browser.close()


if __name__ == '__main__':
    # 直接実行した場合だけ開始。テストからimportした場合は開始しない。
    main()
