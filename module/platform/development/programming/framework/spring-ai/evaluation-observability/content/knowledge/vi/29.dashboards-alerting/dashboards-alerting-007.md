# Liên kết cảnh báo tới trace, dữ liệu đánh giá và hướng dẫn xử lý

## 1. Một cảnh báo cần dẫn người trực tới bằng chứng

Một alert báo tỷ lệ factuality của RAG giảm dưới ngưỡng. Người trực cần trả lời ngay ba câu hỏi:

1. Phạm vi nào đang bị ảnh hưởng: route, prompt version, model hay release?
2. Những request hoặc evaluation cases nào tạo ra tín hiệu đó?
3. Cần làm gì để xác nhận nguyên nhân và khôi phục dịch vụ?

Nếu notification chỉ chứa tên alert và giá trị metric, người trực phải tự tìm dashboard, truy vấn log, mở tracing backend, tìm evaluation run và dò runbook. Quá trình này chậm, dễ nhầm cohort và làm tăng thời gian xử lý incident.

Một alert hữu ích nên chứa đường dẫn tới đúng ngữ cảnh:

- Dashboard hiển thị SLI, numerator/denominator, time window và cohort đang báo động.
- Trace hoặc exemplar đại diện để điều tra execution cụ thể.
- Evaluation run/case search để xem PASS/FAIL, evidence và judge output.
- Runbook mô tả các bước xác minh, hành động và tiêu chí phục hồi.
- Release/deployment metadata để xác định thay đổi gần nhất.

Bài thuộc chương **Dashboard và cảnh báo** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module học đánh giá ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện suy giảm qua các phiên bản prompt, model và pipeline.

Sau bài, bạn có thể:

1. Thiết kế alert labels và annotations để mang đủ ngữ cảnh vận hành.
2. Liên kết alert tới Grafana dashboard và runbook ổn định.
3. Dùng Prometheus exemplars để đi từ metric tới Tempo trace.
4. Kết nối trace với log và metric để điều tra xuyên suốt.
5. Mở đúng evaluation run hoặc danh sách cases liên quan tới cohort.
6. Viết runbook có bước xác minh, xử lý, rollback và recovery.
7. Kiểm tra link, quyền truy cập, redaction và khả năng bảo trì.

## 2. Luồng điều tra từ alert tới nguyên nhân

Một luồng điều tra có thể được tổ chức như sau:

~~~text
Prometheus rule detects SLI regression
  -> Alertmanager groups and routes notification
      -> Dashboard link
          -> Confirm cohort, numerator, denominator, time range
          -> Open exemplar
              -> Tempo trace
                  -> ChatClient / ChatModel / Advisor / Tool / VectorStore spans
                  -> Correlated logs
          -> Evaluation search link
              -> Evaluation run
                  -> Failed cases and judge evidence
      -> Runbook link
          -> Verify impact
          -> Mitigate or rollback
          -> Confirm recovery
~~~

Mỗi liên kết giải quyết một câu hỏi khác nhau:

| Link | Câu hỏi được trả lời |
|---|---|
| Dashboard | Metric nào vượt ngưỡng và cohort nào bị ảnh hưởng? |
| Trace | Một execution cụ thể đã đi qua những span nào? |
| Logs | Exception, provider response và application event nào xảy ra? |
| Evaluation | Những cases nào fail, judge đã dùng rubric nào và evidence ra sao? |
| Runbook | Người trực cần xác minh và hành động theo thứ tự nào? |
| Release details | Prompt, model, index hoặc application version nào vừa thay đổi? |

Đừng cố nhét mọi dữ liệu vào notification. Notification nên là điểm điều hướng ngắn gọn; dashboard, trace backend, evaluation store và runbook giữ phần chi tiết.

## 3. Alert có labels và annotations

Trong Prometheus alerting rule, labels xác định danh tính và phân loại alert instance; annotations chứa thông tin mô tả như summary, description và runbook link.

Ví dụ:

~~~yaml
groups:
  - name: spring-ai-quality
    rules:
      - alert: AiRagFactualityPassRateLow
        expr: |
          (
            sum by (route, prompt_version, model_family) (
              increase(app_ai_eval_cases_total{
                criterion="factuality",
                source="online_sampled",
                outcome="pass"
              }[24h])
            )
            /
            sum by (route, prompt_version, model_family) (
              increase(app_ai_eval_cases_total{
                criterion="factuality",
                source="online_sampled",
                outcome=~"pass|fail"
              }[24h])
            )
          ) < 0.90
          and
          sum by (route, prompt_version, model_family) (
            increase(app_ai_eval_cases_total{
              criterion="factuality",
              source="online_sampled",
              outcome=~"pass|fail"
            }[24h])
          ) >= 200
        for: 20m
        labels:
          severity: warning
          team: ai-quality
          service: rag-assistant
          criterion: factuality
        annotations:
          summary: "Factuality is low for {{ $labels.route }}"
          description: "Prompt {{ $labels.prompt_version }} with model {{ $labels.model_family }} has pass rate {{ $value }}."
          dashboard_url: "https://grafana.example/d/ai-quality/quality?var-route={{ $labels.route }}&var-criterion=factuality&var-prompt={{ $labels.prompt_version }}&var-model={{ $labels.model_family }}&from=now-24h&to=now"
          runbook_url: "https://runbooks.example/ai/rag-factuality-low"
          evaluation_url: "https://eval.example/search?source=online_sampled&route={{ $labels.route }}&criterion=factuality&prompt_version={{ $labels.prompt_version }}&model_family={{ $labels.model_family }}&window=24h"
~~~

Các domain example phải được thay bằng URL thực tế của tổ chức. Rule minh họa giả định metric có labels route, prompt_version và model_family với tập giá trị hữu hạn.

Labels cần ổn định vì chúng tham gia nhận diện, deduplication, grouping và routing của alert. Annotations phù hợp cho URL và nội dung dài hơn.

Tài liệu: [Prometheus — Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/).

## 4. Chọn alert labels đủ để phân loại

Một alert có thể dùng các labels có danh mục hữu hạn:

| Label | Ví dụ | Công dụng |
|---|---|---|
| alertname | AiRagFactualityPassRateLow | Tên rule |
| severity | page, ticket, warning | Mức độ |
| team | ai-quality, platform | Đội sở hữu |
| service | rag-assistant | Dịch vụ |
| route | rag, chat, agent | Cohort |
| criterion | factuality, relevance | Tiêu chí |
| prompt_version | prompt-v13 | Phiên bản prompt |
| model_family | model-large | Nhóm model |
| environment | production, staging | Môi trường |

Không thêm trace_id, request_id, user_id, conversation_id, case_id hoặc raw query vào labels. Các giá trị này thay đổi theo từng event, làm alert instances phân mảnh và tăng cardinality.

Nếu một alert aggregate đại diện hàng nghìn cases, không có một case_id duy nhất phù hợp để gắn vào alert. Hãy liên kết tới evaluation search có filter theo cohort và time range; từ đó người trực chọn case cụ thể.

## 5. Dùng annotations cho các link điều hướng

Một annotation contract có thể gồm:

| Annotation | Mục đích |
|---|---|
| summary | Tiêu đề ngắn trong notification |
| description | Giá trị hiện tại, ngưỡng và cohort |
| dashboard_url | Dashboard đã chọn filter phù hợp |
| runbook_url | Hướng dẫn xử lý |
| evaluation_url | Search page hoặc run report |
| release_url | Deployment/change details nếu có |
| owner_url | Kênh hoặc trang liên hệ của owner |

Prometheus không bắt buộc các tên annotation này; chúng là convention do tổ chức định nghĩa. Notification template phải đọc đúng keys đã thống nhất.

URL cần trỏ tới trang ổn định, không trỏ tới tab browser tạm hoặc URL chứa token đăng nhập. Dùng hostname nội bộ, DNS và reverse proxy đã được tổ chức hỗ trợ.

## 6. Link tới Grafana dashboard theo cohort

Một dashboard alert nên mở đúng dashboard và truyền các filter đã có trong alert labels.

Ví dụ annotation:

~~~yaml
dashboard_url: "https://grafana.example/d/ai-quality/quality?var-environment=production&var-route={{ $labels.route }}&var-criterion=factuality&var-prompt={{ $labels.prompt_version }}&var-model={{ $labels.model_family }}&from=now-24h&to=now"
~~~

Dashboard có thể có các variables:

- environment
- service
- route
- prompt version
- model family
- criterion

Khi mở từ alert, dashboard tự chọn cohort tương ứng. Người trực vẫn cần nhìn thấy tổng traffic, bad count, numerator/denominator, time window và comparison baseline.

Nếu alert không có prompt_version, đừng tạo URL với giá trị rỗng khiến dashboard lọc sai. Có thể dùng dashboard overview không filter theo prompt hoặc tạo alert rule riêng cho cohort đó.

## 7. Dùng Grafana data links cho bảng request và evaluation

Dashboard thường có table panel lấy dữ liệu từ log store hoặc evaluation database. Data link có thể mở record chi tiết dựa trên field của hàng đang chọn.

Ví dụ bảng evaluation cases:

| case reference | criterion | outcome | prompt | model | trace reference |
|---|---|---|---|---|---|
| eval-case-1042 | factuality | FAIL | prompt-v13 | model-large | trace reference |
| eval-case-1043 | factuality | PASS | prompt-v13 | model-large | trace reference |
| eval-case-1050 | factuality | ERROR | prompt-v13 | model-large | trace reference |

Cấu hình link theo field của row:

- Evaluation detail: dùng case reference làm path parameter.
- Trace detail: dùng trace reference làm path parameter.
- Run detail: dùng evaluation run reference.
- Logs: dùng trace reference và time range.

Các field này lấy từ event store hoặc query backend. Không cần đưa case ID hoặc trace ID thành metric label để tạo data link.

Trong Grafana, data links hỗ trợ chuyển giá trị từ field hoặc row sang URL đích. Cách cấu hình cụ thể phụ thuộc panel, datasource và phiên bản Grafana. Kiểm tra link trên một row thật trước khi đưa vào production.

Tài liệu: [Grafana — Data links](https://grafana.com/docs/grafana/latest/panels-visualizations/configure-data-links/).

## 8. Liên kết metric tới trace bằng Prometheus exemplars

Một metric aggregate cho biết có latency spike, nhưng không chỉ ra request nào tạo ra observation đó. Exemplar gắn một measurement đại diện với trace context, thường là trace ID.

Ví dụ khái niệm:

~~~text
app_ai_request_duration_seconds_bucket
  sample: 8.7 seconds
  exemplar:
    trace_id: 4bf92f3577b34da6a3ce929d0e0e4736
~~~

Trong Grafana với Prometheus datasource đã bật exemplar và Tempo datasource đã cấu hình, người trực có thể:

1. Mở panel latency hoặc error metric.
2. Chọn exemplar marker trên biểu đồ.
3. Xem trace ID và chọn Query with Tempo.
4. Đọc trace, span duration, status và attributes.
5. Mở logs liên quan nếu trace/log correlation đã được cấu hình.

Exemplar không phải một metric label thông thường. Nó cung cấp đường dẫn từ aggregate measurement tới một observation cụ thể mà không tạo time series riêng cho từng trace.

Tài liệu: [Grafana — Introduction to exemplars](https://grafana.com/docs/grafana/latest/fundamentals/exemplars/).

## 9. Cấu hình trace datasource trong Grafana

Để link exemplar hoạt động, cần có các thành phần:

- Application phát trace context và spans.
- OpenTelemetry Collector hoặc pipeline tương đương chuyển trace tới backend.
- Tempo hoặc tracing backend lưu trace.
- Prometheus nhận metrics và exemplars.
- Grafana kết nối cả Prometheus và Tempo.
- Prometheus datasource được cấu hình exemplar trace ID key và Tempo datasource đích.

Với Prometheus self-managed, exemplar storage có thể cần bật bằng feature flag --enable-feature=exemplar-storage. Ứng dụng/metrics pipeline phải xuất OpenMetrics có exemplar; Prometheus text exposition thông thường không mang exemplar. Trong Grafana, dùng Prometheus datasource, panel Time series và bật hiển thị Exemplars. Tên key trace ID và Tempo datasource phải khớp cấu hình.

Trace ID trong exemplar phải khớp với trace ID được lưu trong backend. Nếu metrics dùng trace_id nhưng datasource đang tìm traceID hoặc tên key khác, link có thể không xuất hiện.

Tài liệu: [Grafana — Tempo data source](https://grafana.com/docs/grafana/latest/datasources/tempo/).

## 10. Kiểm tra trace có thực sự được lưu

Một exemplar có thể trỏ tới trace đã bị loại bởi sampling hoặc retention. Khi đó link vẫn xuất hiện nhưng trace backend trả về not found.

Các bước kiểm tra:

1. Xác nhận trace ID được ghi đúng trong exemplar.
2. Tìm trace ID trực tiếp trong Tempo.
3. Kiểm tra trace exporter và Collector export errors.
4. Xem head/tail sampling policy.
5. Kiểm tra trace retention và thời điểm trace hết hạn.
6. Đối chiếu timestamp, tenant và datasource.
7. Xác nhận trace backend chưa bị đổi hoặc xóa.

Nếu dùng tail sampling, pipeline metrics/exemplars có thể xử lý trước khi tail sampler quyết định giữ trace. Do đó exemplar không đảm bảo trace tương ứng chắc chắn còn trong storage. Thiết kế sampling policy để giữ đủ error/slow traces và hiểu rõ thứ tự các pipeline stages.

Tài liệu: [Grafana Cloud — Configure and use exemplars](https://grafana.com/docs/grafana-cloud/send-data/traces/configure/exemplars/).

## 11. Liên kết từ log tới trace

Khi application log có trace ID, Grafana Loki có thể cung cấp link từ log line tới trace.

Ví dụ log có cấu trúc:

~~~json
{
  "timestamp": "2026-11-27T10:15:30Z",
  "level": "ERROR",
  "service": "rag-assistant",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "error_class": "PROVIDER_TIMEOUT",
  "message": "ChatModel call timed out"
}
~~~

Cấu hình Loki datasource với Derived fields để trích trace ID từ log line. Chọn Tempo datasource làm internal link target. Khi người trực mở log details, Grafana có thể hiển thị link tới trace tương ứng.

Regex minh họa cho JSON trace_id:

~~~regex
"trace_id":"(\w+)"
~~~

Pattern cần khớp chính xác format log thực tế. Nếu JSON có khoảng trắng hoặc field order khác, dùng parser JSON hoặc regex phù hợp.

Tài liệu: [Grafana — Configure trace to logs correlation](https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/configure-trace-to-logs/).

## 12. Liên kết từ trace tới logs và metrics

Chiều ngược lại cũng quan trọng. Khi người trực mở trace và tìm thấy span ChatModel chậm, họ cần xem logs cùng span và metrics của dependency.

Grafana Tempo hỗ trợ cấu hình:

- Trace to logs: từ span mở logs liên quan trong Loki.
- Trace to metrics: từ span mở query trên Prometheus.
- Trace correlations: tạo link tới hệ thống ngoài hoặc data source khác.

Correlation cần quy tắc match phù hợp như service name, span attributes, trace ID và time range. Cấu hình hai phía khi tính năng yêu cầu cả trace datasource và log datasource.

Tài liệu: [Grafana Tempo — Trace correlations](https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/trace-correlations/).

## 13. Alert aggregate không nên chứa một trace ID tùy ý

Một alert cohort có thể đại diện hàng nghìn request. Không có một trace ID duy nhất mô tả đầy đủ cohort.

Tránh:

- Chọn trace ID đầu tiên rồi gắn vào alert.
- Đưa trace ID vào metric label.
- Gắn case ID của một failure ngẫu nhiên vào alert aggregate.
- Dùng exemplar như thể nó đại diện thống kê cho mọi request.

Nên làm:

- Link dashboard đã filter theo route/model/prompt/time range.
- Dùng exemplars để mở một số traces đại diện.
- Có table panel liệt kê top slow/error requests từ log/event store.
- Sắp xếp theo duration, error class hoặc impact.
- Giữ trace/case IDs trong record store và link chi tiết từ table.

Nếu cần một trace cụ thể trong notification, chỉ dùng khi alert thực sự gắn với một request-level event có trace ID rõ ràng và được phép truy cập.

## 14. Liên kết alert tới evaluation data

Quality alert cần mở đúng dataset/run/cases để người trực kiểm tra:

- Dataset version và sampling policy.
- Criterion và rubric version.
- Generator model và prompt version.
- Judge model và evaluator version.
- PASS/FAIL/ERROR/INVALID/SKIPPED/INCONCLUSIVE counts.
- Response, retrieved evidence và judge rationale theo quyền truy cập.
- Human review hoặc adjudication nếu có.

Một alert online aggregate nên link tới evaluation search với filter theo criterion, route, prompt/model version và time window. Không đặt case_id cố định vào alert nếu alert bao phủ nhiều cases.

Một alert offline release gate có thể link tới report của evaluation run cụ thể. Run ID lấy từ release/evaluation orchestration system, không nhất thiết là Prometheus label. Hãy lưu link run report trong metadata của release hoặc notification được pipeline phát ra.

## 15. Ví dụ evaluation search URL

Một URL search có thể truyền cohort filters:

~~~text
https://eval.example/search
  ?source=online_sampled
  &criterion=factuality
  &route=rag
  &prompt_version=prompt-v13
  &model_family=model-large
  &from=2026-11-27T09:00:00Z
  &to=2026-11-27T10:00:00Z
~~~

Đây là route minh họa. Evaluation application cần xác định API và filter contract của chính nó.

Trang search nên:

1. Xác nhận người dùng có quyền xem dataset/case.
2. Hiển thị tổng số eligible, selected, applicable và evaluated cases.
3. Hiển thị PASS/FAIL và các terminal non-verdict outcomes.
4. Cho phép mở case detail.
5. Cung cấp link tới trace nếu trace còn tồn tại.
6. Hiển thị prompt, generator, judge và rubric versions.
7. Giữ redaction và audit trail.

Nếu query trả quá nhiều cases, cung cấp pagination và sort theo severity hoặc timestamp.

## 16. Link từ evaluation case tới trace

Evaluation case nên lưu một reference tới request/task và trace nếu có:

~~~json
{
  "evaluationRunId": "eval-run-2026-11-27-01",
  "caseId": "eval-case-1042",
  "taskReference": "task-771",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "criterion": "factuality",
  "outcome": "FAIL",
  "promptVersion": "prompt-v13",
  "generatorModel": "model-large",
  "judgeModel": "judge-model-v4",
  "rubricVersion": "factuality-v3"
}
~~~

Schema là đề xuất cho application event store, không phải payload mặc định của Spring AI.

Trace có thể hết hạn trước evaluation record. Khi đó case detail vẫn phải hiển thị verdict, evidence và metadata đã được lưu hợp lệ, đồng thời đánh dấu trace link unavailable. Không coi trace backend là nơi lưu duy nhất cho evaluation result.

## 17. Link từ alert tới runbook

Runbook phải là tài liệu vận hành có version và owner. URL trong alert nên trỏ tới một trang ổn định, không trỏ tới bản nháp hoặc file trên máy cá nhân.

Một runbook tốt có các phần:

1. Alert meaning: điều kiện nào đã fire và SLI nào bị ảnh hưởng.
2. Impact: route, feature, cohort và user impact.
3. Dashboards: panel cần mở và filter mặc định.
4. First checks: kiểm tra numerator, denominator, traffic và time range.
5. Trace/log path: cách tìm exemplar hoặc request record.
6. Evaluation path: cách xem failed cases và judge health.
7. Likely causes: provider, prompt, retrieval, tool, deployment hoặc instrumentation.
8. Mitigation: rollback, pause canary, fallback, throttle hoặc disable feature.
9. Recovery: điều kiện xác nhận SLI trở lại bình thường.
10. Escalation: owner, contact và khi nào cần incident commander.

Runbook nên có ngày review gần nhất, người sở hữu và liên kết tới dashboard liên quan.

## 18. Ví dụ runbook cho factuality regression

~~~markdown
# AiRagFactualityPassRateLow

## Meaning
Online factuality pass rate dưới target trên cohort prompt/model.

## Impact
Kiểm tra route, prompt version, model family, evaluated count và coverage.

## First checks
1. Mở dashboard quality từ alert.
2. Xác nhận numerator, denominator và cửa sổ 24h.
3. Kiểm tra completion coverage và judge attempt error rate.
4. Xác nhận rubric, judge model và sampling policy không đổi ngoài dự kiến.

## Evidence
1. Mở evaluation search theo criterion/route/prompt/model.
2. Review các failed cases có severity cao.
3. Mở trace liên quan nếu có.
4. Kiểm tra retrieval evidence và model/tool spans.

## Mitigation
1. Pause rollout candidate nếu regression gắn với prompt/model release.
2. Route traffic về control version đã xác minh.
3. Không sửa rubric chỉ để làm pass rate tăng.

## Recovery
1. Chạy lại fixed evaluation dataset.
2. Xác nhận quality gate và coverage đạt.
3. Theo dõi online cohort qua cửa sổ đủ sample.
4. Ghi lại root cause và quyết định release.
~~~

Nội dung runbook phải phù hợp với quyền hạn thực tế của người trực. Không đưa lệnh destructive hoặc thao tác production không có xác nhận và quy trình change control.

## 19. Alertmanager notification template

Prometheus phát hiện alert; Alertmanager xử lý grouping, routing, inhibition, silencing và notification. Notification template nên hiển thị summary, description và các link đã định nghĩa.

Ví dụ Go template:

~~~gotemplate
{{ range .Alerts }}
Alert: {{ .Labels.alertname }}
Status: {{ .Status }}
Severity: {{ .Labels.severity }}
Service: {{ .Labels.service }}
Route: {{ .Labels.route }}

{{ .Annotations.summary }}
{{ .Annotations.description }}

{{ with .Annotations.dashboard_url }}Dashboard: {{ . }}{{ end }}
{{ with .Annotations.runbook_url }}Runbook: {{ . }}{{ end }}
{{ with .Annotations.evaluation_url }}Evaluation: {{ . }}{{ end }}
Source rule: {{ .GeneratorURL }}
---
{{ end }}
~~~

Template cần xử lý annotations có thể vắng mặt, vì không phải alert nào cũng có evaluation_url hoặc route. Notification channel cũng có thể giới hạn độ dài; giữ phần summary ngắn và đưa chi tiết vào link.

Nếu notification group chứa nhiều alert instances, render từng alert trong group thay vì chỉ dùng một annotation chung không còn đúng với tất cả instances.

Tài liệu: [Prometheus — Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/) và [Prometheus — Alerts API](https://prometheus.io/docs/alerting/latest/alerts_api/).

## 20. Phân biệt generator URL với runbook URL

Prometheus/Alertmanager có thể cung cấp GeneratorURL để mở nguồn alert/rule. URL này hữu ích để xác định alert expression và nguồn phát hiện.

Runbook URL là liên kết do đội vận hành khai báo để hướng dẫn xử lý. Dashboard URL mở metrics và cohort. Evaluation URL mở dữ liệu quality. Trace link thường được mở từ exemplar hoặc record detail.

Bốn loại link không thay thế nhau:

| Link | Nơi mở | Vai trò |
|---|---|---|
| GeneratorURL | Prometheus | Xem rule và alert source |
| Dashboard URL | Grafana | Xác nhận phạm vi và xu hướng |
| Runbook URL | Docs/wiki | Thực hiện điều tra và mitigation |
| Evaluation/trace URL | Evaluation store/Tempo | Xem bằng chứng cụ thể |

Không gọi GeneratorURL là runbook. Người trực cần cả nguồn alert lẫn hướng dẫn hành động.

## 21. Thiết kế link cho các loại alert Spring AI

| Alert | Dashboard | Evidence link | Runbook |
|---|---|---|---|
| User request error ratio high | RED/request dashboard | Exemplars và error logs | Request availability incident |
| ChatModel latency high | Model latency dashboard | Tempo trace và provider logs | Provider latency |
| VectorStore retrieval slow | Retrieval dashboard | Trace spans và query metadata | Retrieval performance |
| Tool failure ratio high | Tool dashboard | Tool span/log record | Tool dependency failure |
| Factuality pass rate low | Quality dashboard | Evaluation search/cases | Factuality regression |
| Judge attempt error high | Evaluator dashboard | Judge attempts/traces | Evaluator provider incident |
| Evaluation coverage low | Evaluation queue dashboard | Pending/skipped/error case search | Evaluation backlog |
| Cost per task high | Cost dashboard | Cost ledger records | Cost investigation |

Mỗi loại alert cần mở dashboard với filter phù hợp. Đừng đưa mọi alert về một dashboard tổng quan rồi để người trực tự tìm lại cohort.

## 22. Correlation ID và context propagation

Để liên kết được request, trace, evaluation case và cost record, ứng dụng cần một correlation model nhất quán.

Ví dụ:

~~~text
user_request_id
  -> task_id
      -> trace_id
          -> span_id
      -> model_operation_id
      -> evaluation_case_id
          -> evaluation_run_id
      -> cost_event_id
~~~

Không nhất thiết tất cả ID đều là metric labels. Chúng phù hợp với event store, logs và trace attributes có chính sách kiểm soát.

Trong asynchronous evaluation, trace của evaluator có thể là trace mới. Lưu task reference và link giữa producer trace với evaluation trace bằng span link hoặc correlation metadata theo kiến trúc tracing. Không giả định một async worker luôn thuộc cùng parent span sau khi queue boundary đã kết thúc.

Context propagation phải được kiểm thử qua executor, Reactor, messaging và retry paths. Nếu trace context bị mất ở queue, evaluation result vẫn cần giữ task reference để truy lại request gốc theo quyền truy cập.

## 23. Bảo vệ dữ liệu trong link và notification

URL có thể bị lưu trong notification history, chat channel, ticket, browser history và access logs. Không đưa dữ liệu nhạy cảm vào query string.

Tránh đưa vào link:

- Raw user prompt hoặc completion.
- Retrieved document text.
- Personal identifiers.
- Access token, API key hoặc signed URL dài hạn.
- Tool arguments chứa dữ liệu khách hàng.
- Trace/case IDs nếu người nhận notification không có quyền xem.

Ưu tiên truyền cohort filters hữu hạn như route, criterion, model family và version. Hệ thống đích xác thực user rồi kiểm tra quyền truy cập record.

Nếu cần deep link tới một case nhạy cảm, dùng opaque reference có TTL và authorization ở server. Không coi URL khó đoán là cơ chế phân quyền.

## 24. URL encoding và label hygiene

Alert template có thể đưa label values vào query parameters. Chỉ dùng labels có danh mục hữu hạn và giá trị được kiểm soát.

Không đưa free-form label vào URL nếu không có encoding phù hợp. Các ký tự như dấu cách, dấu cộng, dấu &, dấu # hoặc Unicode có thể làm query bị sai hoặc tạo URL injection.

Khuyến nghị:

- Dùng slug ổn định cho route, model family và release.
- Kiểm soát tập giá trị của prompt_version.
- Không dùng raw user input làm label.
- Dùng URL builder ở application notification service nếu cần tham số động phức tạp.
- Kiểm tra redirect destination theo allowlist.
- Không nối chuỗi URL từ dữ liệu không tin cậy.

Các ví dụ URL trong bài chỉ sử dụng label values đơn giản để dễ đọc.

## 25. Quyền truy cập và môi trường

Một link tốt vẫn vô ích nếu người nhận không thể mở hoặc link trỏ sai môi trường.

Kiểm tra:

- Alert production mở Grafana production.
- Staging alert mở staging datasource.
- Tempo datasource đúng tenant/region.
- Evaluation app có quyền truy cập dataset/case.
- Runbook được chia sẻ cho on-call.
- Notification URL dùng hostname nội bộ có thể truy cập từ mạng vận hành.
- SSO/session không bị mất khi mở link từ notification client.

Không nhúng credential vào URL để giải quyết lỗi authentication. Sử dụng SSO, service authorization và access policy chuẩn của tổ chức.

## 26. Link phải tồn tại lâu hơn vòng đời alert

Alert có thể được gửi lại, forward vào ticket hoặc xem lại sau vài ngày. Link cần có độ bền tương ứng.

Dashboard URL nên dùng dashboard UID ổn định, không dùng URL tạm từ Explore session. Runbook URL nên trỏ tới trang canonical có redirect khi đổi cấu trúc docs. Evaluation URL cần xử lý run đã archive. Trace URL cần thông báo khi trace hết retention.

Nếu một tài nguyên đã hết hạn, trang đích nên giải thích trạng thái và đưa người dùng tới dữ liệu thay thế nếu có. Không để link chết mà không có thông tin.

## 27. Kiểm thử link end-to-end

Trước khi bật alert production, kiểm thử từ rule tới notification:

1. Tạo một alert test trong staging.
2. Xác nhận labels và annotations render đúng.
3. Mở dashboard URL và kiểm tra variables được áp dụng.
4. Xác nhận time range bao phủ thời điểm alert.
5. Mở exemplar từ panel metric.
6. Kiểm tra trace tồn tại trong Tempo.
7. Mở log từ trace và trace từ log nếu hai chiều được cấu hình.
8. Mở evaluation search và kiểm tra cohort filter.
9. Mở case detail và trace link của case.
10. Mở runbook và xác nhận các bước còn đúng.
11. Kiểm tra notification trên từng channel được hỗ trợ.
12. Kiểm tra user không có quyền nhận được access denied phù hợp.

Kiểm thử cả firing và resolved notifications. Alert có thể resolve trước khi người nhận mở link; dashboard cần cho phép xem lịch sử tại thời điểm alert fire.

## 28. Xử lý link lỗi và dữ liệu không còn tồn tại

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra |
|---|---|---|
| Dashboard mở nhưng không có data | Sai variable hoặc time range | Kiểm tra label filter và timestamp |
| Dashboard filter rỗng | Alert thiếu label hoặc annotation | Kiểm tra rule output labels |
| Trace link 404 | Trace bị drop hoặc hết retention | Kiểm tra sampling/export/storage |
| Không có exemplar marker | Instrumentation hoặc datasource chưa bật | Kiểm tra exposition và Prometheus config |
| Log không mở trace | Derived field regex sai | Kiểm tra trace_id format |
| Trace không mở log | Trace-to-logs correlation chưa cấu hình | Kiểm tra Tempo và Loki datasource |
| Evaluation search không có case | Sai cohort, source hoặc time zone | Kiểm tra filter contract |
| Runbook 403/404 | Quyền hoặc URL đã đổi | Kiểm tra owner, SSO và canonical URL |
| URL bị cắt trong notification | Channel giới hạn độ dài | Rút gọn link và dùng short title |

Khi link lỗi, ghi rõ đó là lỗi điều hướng hay lỗi dữ liệu gốc. Ví dụ trace 404 không chứng minh request không có trace; trace có thể đã bị retention xóa.

## 29. Quan sát link quality

Có thể theo dõi chính khả năng sử dụng các link vận hành:

- Tỷ lệ dashboard link mở thành công.
- Tỷ lệ runbook URL trả HTTP 200/authorized.
- Tỷ lệ exemplar trace còn tồn tại.
- Tỷ lệ evaluation links trả được kết quả.
- Thời gian từ alert fire tới lần mở dashboard/trace đầu tiên nếu hệ thống incident có dữ liệu phù hợp.
- Tỷ lệ alert thiếu required annotations.

Không đo việc một cá nhân đã click link bằng cách theo dõi người dùng ngoài chính sách privacy. Có thể kiểm tra link bằng synthetic probes hoặc integration tests định kỳ.

Metric link health nên dùng labels hữu hạn như alertname, environment và link_type. Không đưa URL đầy đủ hoặc token vào labels.

## 30. Ownership và bảo trì

Mỗi alert cần có owner chịu trách nhiệm giữ link đúng.

| Thành phần | Owner nên chịu trách nhiệm |
|---|---|
| Prometheus alert rule | Service/platform owner |
| Dashboard UID và variables | Observability/dashboard owner |
| Tempo datasource và exemplar mapping | Observability platform |
| Evaluation search/case detail | Evaluation platform owner |
| Runbook | Service on-call owner |
| Release metadata link | Delivery/release owner |
| Access policy | Security/platform owner |

Khi đổi dashboard UID, datasource name, evaluation route hoặc runbook path, cập nhật alert annotations và kiểm thử notification. Không để người trực tự phát hiện link đã hỏng trong incident.

Runbook cần có review date. Dashboard cần có owner và mô tả panel. Evaluation schema cần version để link cũ vẫn có thể được xử lý hoặc redirect.

## 31. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ gửi tên alert và giá trị | Người trực phải tự tìm context | Thêm dashboard, runbook và evidence links |
| Đưa trace ID vào metric label | Cardinality tăng mạnh | Dùng exemplar |
| Một trace ID đại diện alert aggregate | Điều tra sai một request | Link dashboard và exemplar list |
| Đưa case ID vào alert label | Alert instances bị phân mảnh | Link evaluation search |
| Dashboard URL không có filter | Mở sai cohort | Truyền route/version/model variables |
| Không truyền time range | Dashboard không chứa thời điểm incident | Đặt range quanh alert window |
| Link trực tiếp vào Explore session | URL dễ hết hạn | Dùng dashboard UID ổn định |
| Alertmanager template chỉ render common annotations | Mất link khi group nhiều alerts | Render từng alert instance |
| URL chứa raw prompt/token | Rò rỉ dữ liệu | Dùng opaque reference và authorization |
| Exemplar không có trace trong storage | Link trả 404 | Kiểm tra sampling và retention |
| Runbook không có owner | Hướng dẫn lỗi thời | Gán owner và review date |
| Không test resolved notification | Link/history thiếu context | Kiểm thử cả firing và resolved |

## 32. Bài tập tự kiểm tra

### Bài 1 — Alert factuality aggregate

Alert báo factuality pass rate thấp trên prompt-v13/model-large với 2.000 cases. Nên link tới một case cố định hay evaluation search?

**Đáp án:** Evaluation search theo criterion, prompt version, model family và time range. Từ search, người trực chọn failed cases cụ thể.

### Bài 2 — Trace ID trong metric label

Một team muốn thêm trace_id vào app_ai_request_duration_seconds để mở trace nhanh. Có nên làm không?

**Đáp án:** Không. Trace ID tạo cardinality cao. Dùng Prometheus exemplar và Grafana Tempo integration.

### Bài 3 — Exemplar trả 404

Grafana hiển thị exemplar nhưng Tempo không tìm thấy trace. Cần kiểm tra gì?

**Đáp án:** Trace ID mapping, exporter, Collector, sampling order, tail sampling decision, tenant và retention. Exemplar không đảm bảo trace chắc chắn được giữ.

### Bài 4 — Dashboard mở sai prompt

Alert có prompt-v13 nhưng dashboard mở tất cả prompt versions. Cần sửa ở đâu?

**Đáp án:** Annotation dashboard_url cần truyền prompt_version label thành Grafana variable và dashboard phải áp dụng variable đó trong query.

### Bài 5 — Alert group nhiều instances

Một notification group chứa ba routes, nhưng template chỉ hiển thị CommonAnnotations.dashboard_url. Có thể mất link hoặc context không?

**Đáp án:** Có. Render từng item trong Alerts để giữ annotations và labels đúng với từng alert instance.

### Bài 6 — Runbook URL 403

On-call nhận alert nhưng runbook trả 403. Có nên nhúng token vào URL?

**Đáp án:** Không. Sửa SSO, group permissions hoặc access policy và kiểm tra quyền của on-call role.

### Bài 7 — Evaluation trace đã hết hạn

Case detail vẫn có verdict nhưng trace link đã hết retention. Evaluation UI cần làm gì?

**Đáp án:** Giữ verdict/evidence metadata hợp lệ, đánh dấu trace unavailable và cung cấp request/task reference hoặc log link còn được phép truy cập.

### Bài 8 — Alert không có prompt label

Một alert về provider-wide 429 không có prompt_version. Dashboard URL nên làm gì?

**Đáp án:** Mở dashboard provider/dependency overview không filter prompt. Không truyền biến rỗng khiến dashboard hiển thị no data.

## 33. Checklist trước khi phát hành alert links

- [ ] Alert có summary và description dễ hiểu?
- [ ] Labels chỉ chứa dimensions hữu hạn?
- [ ] Annotations có dashboard_url và runbook_url?
- [ ] Quality alerts có evaluation_url phù hợp?
- [ ] Dashboard link truyền đúng route/version/model/environment?
- [ ] Time range bao phủ lúc alert fire?
- [ ] Dashboard hiển thị numerator, denominator, sample size và baseline?
- [ ] Exemplar được bật và trỏ tới đúng trace datasource?
- [ ] Trace backend giữ đủ traces theo sampling/retention policy?
- [ ] Logs có trace ID và Derived field đã cấu hình?
- [ ] Tempo trace-to-logs correlation hoạt động?
- [ ] Evaluation search có quyền truy cập và filter đúng cohort?
- [ ] Case detail liên kết được với trace khi trace còn tồn tại?
- [ ] Runbook có owner, review date và recovery criteria?
- [ ] Alertmanager template render từng alert instance?
- [ ] Firing và resolved notifications đều đã được kiểm thử?
- [ ] URL không chứa secret, raw prompt hoặc dữ liệu nhạy cảm?
- [ ] Link hoạt động trong môi trường production và staging tương ứng?

## 34. Tài liệu tham khảo

1. [Prometheus — Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): labels, annotations và template variables trong alert rules.
2. [Prometheus — Alerts API](https://prometheus.io/docs/alerting/latest/alerts_api/): alert labels, annotations và generator URL.
3. [Grafana — Introduction to exemplars](https://grafana.com/docs/grafana/latest/fundamentals/exemplars/): mở trace từ exemplar trên metric.
4. [Grafana — Data links](https://grafana.com/docs/grafana/latest/panels-visualizations/configure-data-links/): liên kết từ panel/field tới URL đích.
5. [Grafana — Tempo data source](https://grafana.com/docs/grafana/latest/datasources/tempo/): tracing datasource và correlation với metrics/logs.
6. [Grafana — Trace to logs correlation](https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/configure-trace-to-logs/): liên kết hai chiều giữa Tempo và Loki.
7. [Grafana — Trace correlations](https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/trace-correlations/): link theo ngữ cảnh từ span tới hệ thống liên quan.
8. [Prometheus — Exposition formats](https://prometheus.io/docs/instrumenting/exposition_formats/): OpenMetrics và exemplar metadata trong metric exposition.
9. [OpenTelemetry — Metrics data model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/#exemplars): exemplar data và liên kết measurements với trace context.
10. [Spring AI 2.1.0 — Observability](https://docs.spring.io/spring-ai/reference/observability/): observations của ChatClient, ChatModel, tools và VectorStore.
11. [Spring AI 2.1.0 — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): Evaluator API và đánh giá relevance/factuality.

*Các hostname, alert names, metric names, labels và URL trong ví dụ là giả định. Thay bằng endpoint, datasource UID, dashboard UID và route thực tế của tổ chức. Trước khi phát hành, kiểm thử link từ notification thật, xác nhận quyền truy cập và bảo đảm trace/evaluation records được lưu theo retention policy.*
