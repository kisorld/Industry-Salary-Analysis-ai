# API 说明

## GET `/api/health`

检查后端是否可用。

## GET `/api/sample/analyze?use_ai=true`

使用内置样例数据分析。`use_ai=true` 时会尝试调用 Qwen；失败时返回本地模板报告。

## POST `/api/upload/analyze?use_ai=true`

上传 CSV/Excel 并分析。字段支持中文表头：

- 岗位名称
- 岗位类别
- 公司
- 城市
- 薪资
- 经验
- 学历
- 发布时间
- 来源

## POST `/api/scrape/poc`

公开页面采集 PoC。

```json
{
  "url": "https://example.com/jobs.html",
  "limit": 20
}
```

## POST `/api/report`

生成 Word 报告。

```json
{
  "title": "行业薪酬洞察报告",
  "use_ai": true
}
```

## GET `/api/download/report`

下载 Word 报告。

## GET `/api/download/cleaned`

下载清洗后的 CSV。

