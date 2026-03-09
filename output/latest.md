# 测试报告

## 1. 基本信息

- 任务编码：`REG_old_new_20260309_234049`
- 目标库：`rrs_test_dev`
- 旧版场景：`custTransInfo#old#20260309_01`
- 新版场景：`custTransInfo#new#20260309_01`
- 任务状态：`SUCCESS`
- 对比引擎：`DeepDiff(ignore_order=True)`

## 2. 汇总统计

- 总样本数：`21`
- 可配对指纹数：`12`
- 成功配对数：`7`
- 一致数：`2`
- 差异数：`5`
- 仅旧版存在数：`2`
- 仅新版存在数：`2`
- 无效样本数：`1`
- 阻断差异数：`3`
- 问题请求数：`10`

## 3. 问题请求分类

- `BLOCK`：`3`
- `MULTI_OLD`：`1`
- `NORMAL`：`2`
- `ONLY_NEW`：`2`
- `ONLY_OLD`：`2`

## 4. 差异明细统计

- `BLOCK`：`5`
- `NORMAL`：`4`

## 5. 结果明细

| pair_status | compare_status | diff_level | api_path | old_trace_id | new_trace_id | summary |
| --- | --- | --- | --- | --- | --- | --- |
| MATCHED | SUCCESS | SAME | /aml/wst/custTransInfo | TC001OLD_001 | TC001NEW_002 | 响应一致 |
| MATCHED | SUCCESS | NORMAL | /aml/wst/custTransInfo | TC002OLD_003 | TC002NEW_004 | $.data.totalCount:CHANGE; $.data.totalPage:CHANGE |
| MATCHED | SUCCESS | BLOCK | /aml/wst/custTransInfo | TC003OLD_005 | TC003NEW_006 | $.data:TYPE_CHANGE; $.retCode:CHANGE; $.retMsg:CHANGE |
| MATCHED | SUCCESS | SAME | /aml/wst/custTransInfo | TC004OLD_007 | TC004NEW_008 | 响应一致 |
| MATCHED | SUCCESS | NORMAL | /aml/wst/custTransInfo | TC005OLD_009 | TC005NEW_010 | $.data.content[1].transAmount:CHANGE |
| ONLY_OLD | SKIPPED | BLOCK | /aml/wst/custTransInfo | TC101OLD_011 | - | 旧版存在但新版无配对请求 |
| ONLY_NEW | SKIPPED | BLOCK | /aml/wst/custTransInfo | - | TC102NEW_012 | 新版存在但旧版无配对请求 |
| MULTI_OLD | SKIPPED | BLOCK | /aml/wst/custTransInfo | TC104OLDA_013 | TC104NEW_015 | 旧版存在2条重复样本 |
| MATCHED | SUCCESS | BLOCK | /aml/wst/custTransInfo | TC201OLD_016 | TC201NEW_017 | $.status_code:CHANGE |
| MATCHED | FAILED | BLOCK | /aml/wst/custTransInfo | TC204OLD_018 | TC204NEW_019 | Expecting value: line 1 column 1 (char 0) |
| ONLY_OLD | SKIPPED | BLOCK | /aml/wst/custTransInfo | TC103OLD_020 | - | 旧版存在但新版无配对请求 |
| ONLY_NEW | SKIPPED | BLOCK | /aml/wst/custTransInfo | - | TC103NEW_021 | 新版存在但旧版无配对请求 |

## 6. 结论

- 本次验证已覆盖正常配对、一般差异、阻断差异、仅单边存在、重复样本、非 200 状态码、非 JSON 响应等场景。
- 当前系统将找不到配对请求、非 200 状态码、非 JSON 响应、重复样本冲突都判定为问题请求。
- 当前实现已验证：请求按 `path + 请求参数` 配对，`response_body` 在配对后通过 `DeepDiff(ignore_order=True)` 单独比较。
