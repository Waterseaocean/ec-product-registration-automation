import tempfile
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
from automation import run, ROOT
from mock_server import serve
from rules import reason


class RulesTests(unittest.TestCase):
    def test_boundaries(self):
        p = dict(id='x', name='商品', price=1000, stock=1, registered=False)
        for price, expected in [(999, '価格範囲外'), (1000, None), (10000, None), (10001, '価格範囲外')]:
            self.assertEqual(reason(dict(p, price=price)), expected)
        self.assertEqual(reason(dict(p, name='ジャンク品')), 'NG語')
        self.assertEqual(reason(dict(p, stock=0)), '在庫なし')
        self.assertEqual(reason(dict(p, registered=True)), '登録済み')

    def test_invalid_data(self):
        with self.assertRaises(ValueError):
            reason(dict(id='', name='商品', price=1000, stock=1, registered=False))
        with self.assertRaises(ValueError):
            reason(dict(id='x', name='商品', price='不明', stock=1, registered=False))


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.temp = tempfile.TemporaryDirectory()
        self.server = serve()
        self.url = self.server.__enter__()

    def tearDown(self):
        self.context.close()
        self.server.__exit__(None, None, None)
        self.temp.cleanup()

    def run_lab(self, execute=False, scenario='', **kwargs):
        return run(self.page, self.url + scenario, Path(self.temp.name), execute, **kwargs)

    def test_dry_run(self):
        result = self.run_lab()
        self.assertEqual(result['completed'], [])
        self.assertEqual([p['id'] for p in result['decisions'] if p['reason']=='対象'], ['A001','A005','A007'])
        self.assertEqual(self.page.locator('#history').inner_text(), '')

    def test_execute_and_rerun(self):
        self.assertEqual(self.run_lab(True)['completed'], ['A001','A005','A007'])
        self.assertEqual(self.page.locator('#history').inner_text(), 'A001, A005, A007')
        self.assertEqual(self.run_lab(True)['completed'], [])

    def test_empty(self):
        self.assertEqual(self.run_lab(True, '?scenario=empty')['decisions'], [])

    def test_keyword(self):
        self.assertEqual(self.run_lab(True, keyword='ノート')['completed'], ['A005'])

    def test_duplicate(self):
        result = self.run_lab(True, '?scenario=duplicate')
        self.assertEqual(result['completed'], ['A001','A005','A007'])
        self.assertTrue(any(p['reason']=='重複ID' for p in result['decisions']))

    def test_abnormal_scenarios(self):
        for scenario in ['error', 'unknown', 'loop']:
            with self.subTest(scenario=scenario):
                with self.assertRaises(Exception):
                    self.run_lab(True, '?scenario=' + scenario)
                self.assertTrue((Path(self.temp.name)/'error.png').exists())
                import json
                result = json.loads((Path(self.temp.name)/'result.json').read_text(encoding='utf-8'))
                self.assertEqual(result['status'], 'stopped')
                self.assertNotIn('A005', result['completed'])

    def test_page_limit(self):
        with self.assertRaisesRegex(RuntimeError, '上限'):
            self.run_lab(max_pages=1)

    def test_stop_file(self):
        stop = ROOT / 'STOP'
        if stop.exists():
            self.skipTest('既存STOPファイルを保持')
        try:
            stop.touch()
            with self.assertRaisesRegex(RuntimeError, 'STOP'):
                self.run_lab(True)
        finally:
            stop.unlink()


if __name__ == '__main__':
    unittest.main()
