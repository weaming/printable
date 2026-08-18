# Printable

CLI and functions help for printing tabular data.

## Install

`pip3 install printable`

## Rendering Engines

Two engines render tables: `python` (pure Python) and `column` (a ctypes binding of the compiled util-linux column command). By default (`auto`), the column engine is used when no `--grid` is set, and falls back to the python engine if the shared library is missing; grid styles always use the python engine. Select explicitly with `-e python|column|auto`.

Width calculation uses the native library when available and falls back to pure Python otherwise. 5000×6 mixed zh-en rows (`make bench`):

| engine            | width calc  | median (ms) | speedup (vs original) | speed up (vs now) |
| ----------------- | ----------- | ----------: | --------------------: | ----------------: |
| python (original) | pure Python |         322 |                  1.0x |                   |
| python (now)      | pure Python |          75 |                  4.3x |              1.0x |
| python + C width  | native C    |          27 |                 11.9x |              2.8x |
| column            | native C    |          17 |                 18.9x |              4.4x |

The original row is the pre-optimization implementation (git `a5ce114`): per-cell `wcswidth`, per-character control normalization, and duplicated row formatting. Optimizations: batched width calculation via the native library, flattened single-call batch, and regex-based normalization.

## Usage Example

```python
from printable import readable

print(readable(list_of_dict, grid='full'))
```

```
$ printable -t csv -f samples/sample.csv
 symbol     desp      last    change   changeper  turnover  changesign  lastupdate
 HSI        恆指      26623   -468     1.73%      802億     -           2018/10/04 16:09
 HSCEI      國指      10547   -239     2.21%      257億     -           2018/10/04 16:08
 000001.SH  上證指數  2821    29       1.06%      1254億    +           2018/09/28 15:10
 000300.SH  滬深 300  3438    35       1.04%      949億     +           2018/09/28 15:10
 USDHKD     港匯      7.8337  -0.0037  -0.0472%             -

$ printable -t csv -f samples/sample.csv --grid inner
 symbol    │ desp     │ last   │ change  │ changeper │ turnover │ changesign │ lastupdate
───────────┼──────────┼────────┼─────────┼───────────┼──────────┼────────────┼──────────────────
 HSI       │ 恆指     │ 26623  │ -468    │ 1.73%     │ 802億    │ -          │ 2018/10/04 16:09
───────────┼──────────┼────────┼─────────┼───────────┼──────────┼────────────┼──────────────────
 HSCEI     │ 國指     │ 10547  │ -239    │ 2.21%     │ 257億    │ -          │ 2018/10/04 16:08
───────────┼──────────┼────────┼─────────┼───────────┼──────────┼────────────┼──────────────────
 000001.SH │ 上證指數 │ 2821   │ 29      │ 1.06%     │ 1254億   │ +          │ 2018/09/28 15:10
───────────┼──────────┼────────┼─────────┼───────────┼──────────┼────────────┼──────────────────
 000300.SH │ 滬深 300 │ 3438   │ 35      │ 1.04%     │ 949億    │ +          │ 2018/09/28 15:10
───────────┼──────────┼────────┼─────────┼───────────┼──────────┼────────────┼──────────────────
 USDHKD    │ 港匯     │ 7.8337 │ -0.0037 │ -0.0472%  │          │ -          │

$ printable -t csv -f samples/sample.csv --grid full
┌───────────┬──────────┬────────┬─────────┬───────────┬──────────┬────────────┬──────────────────┐
│ symbol    │ desp     │ last   │ change  │ changeper │ turnover │ changesign │ lastupdate       │
├───────────┼──────────┼────────┼─────────┼───────────┼──────────┼────────────┼──────────────────┤
│ HSI       │ 恆指     │ 26623  │ -468    │ 1.73%     │ 802億    │ -          │ 2018/10/04 16:09 │
├───────────┼──────────┼────────┼─────────┼───────────┼──────────┼────────────┼──────────────────┤
│ HSCEI     │ 國指     │ 10547  │ -239    │ 2.21%     │ 257億    │ -          │ 2018/10/04 16:08 │
├───────────┼──────────┼────────┼─────────┼───────────┼──────────┼────────────┼──────────────────┤
│ 000001.SH │ 上證指數 │ 2821   │ 29      │ 1.06%     │ 1254億   │ +          │ 2018/09/28 15:10 │
├───────────┼──────────┼────────┼─────────┼───────────┼──────────┼────────────┼──────────────────┤
│ 000300.SH │ 滬深 300 │ 3438   │ 35      │ 1.04%     │ 949億    │ +          │ 2018/09/28 15:10 │
├───────────┼──────────┼────────┼─────────┼───────────┼──────────┼────────────┼──────────────────┤
│ USDHKD    │ 港匯     │ 7.8337 │ -0.0037 │ -0.0472%  │          │ -          │                  │
└───────────┴──────────┴────────┴─────────┴───────────┴──────────┴────────────┴──────────────────┘

$ printable -t csv -f samples/sample.csv --grid markdown
| symbol    | desp     | last   | change  | changeper | turnover | changesign | lastupdate       |
|-----------|----------|--------|---------|-----------|----------|------------|------------------|
| HSI       | 恆指     | 26623  | -468    | 1.73%     | 802億    | -          | 2018/10/04 16:09 |
| HSCEI     | 國指     | 10547  | -239    | 2.21%     | 257億    | -          | 2018/10/04 16:08 |
| 000001.SH | 上證指數 | 2821   | 29      | 1.06%     | 1254億   | +          | 2018/09/28 15:10 |
| 000300.SH | 滬深 300 | 3438   | 35      | 1.04%     | 949億    | +          | 2018/09/28 15:10 |
| USDHKD    | 港匯     | 7.8337 | -0.0037 | -0.0472%  |          | -          |                  |
```
