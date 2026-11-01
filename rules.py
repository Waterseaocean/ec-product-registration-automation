import unicodedata


def reason(product):
    # [R01] 入力検査：IDが空、名称が文字列でない場合は判定を続けず停止。
    if not product['id'] or not isinstance(product['name'], str):
        raise ValueError('商品ID・名称不正')
    # [R02] 表記を揃える：NFKCは半角カナ等を正規化、casefoldは英字の大小差を吸収。
    name = unicodedata.normalize('NFKC', product['name']).casefold()
    # anyは1つでもTrueならTrue。inは単語が名称の一部に含まれるかを調べる。
    if any(word in name for word in ('禁止', 'ジャンク')):
        # returnで関数を終了するので、後続の価格・在庫はこの商品では調べない。
        return 'NG語'
    # [R03] 数値条件：画面属性の文字列を整数へ。変換不能ならValueErrorで停止。
    price, stock = int(product['price']), int(product['stock'])
    # 両端を含む範囲。notはその範囲外という意味。
    if not 1000 <= price <= 10000:
        return '価格範囲外'
    if stock < 1:
        return '在庫なし'
    if product['registered']:
        return '登録済み'
    # [R04] どの除外条件にも該当しない場合はNone＝理由なし＝対象。
    return None
