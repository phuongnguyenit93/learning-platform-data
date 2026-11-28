# Kiểm thử dashboard, cảnh báo và truy vấn metric sau nâng cấp

Một lần nâng cấp Spring AI, Spring Boot, Micrometer, OpenTelemetry hoặc Prometheus có thể làm thay đổi cách metric được đăng ký, đặt tên, export, scrape và truy vấn. Ứng dụng vẫn chạy, endpoint health vẫn xanh, nhưng dashboard có thể mất series, percentile đổi cách tính hoặc alert không còn kích hoạt. Với hệ thống AI, một thay đổi như vậy có thể che giấu evaluator timeout, retrieval regression, tool failure hoặc chi phí tăng.

Vì vậy, kiểm thử sau nâng cấp phải bao phủ toàn bộ đường đi của telemetry: từ meter trong ứng dụng đến scrape exposition, PromQL, dashboard panel và alert notification. Cần có baseline trước nâng cấp, fixture có kết quả kỳ vọng, kiểm tra compatibility và bằng chứng sau khi rollout.

Bài học thuộc chương **Nâng cấp** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời theo dõi metrics, traces, cost và latency qua các phiên bản prompt, model và pipeline.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Lập inventory các thành phần ảnh hưởng đến telemetry trước khi nâng cấp.
2. Lưu baseline metric exposition, PromQL results, dashboard và alert states.
3. Phát hiện metric rename, unit change, label change, missing series và cardinality growth.
4. Kiểm tra histogram buckets, Timer/DistributionSummary và percentile sau khi đổi Micrometer registry.
5. Xác minh Prometheus scrape, target health, recording rules và alert rules.
6. Kiểm thử Grafana panel, variables, No Data và Error behavior.
7. Viết test cho query và alert bằng promtool cùng fixture metrics.
8. So sánh baseline/candidate bằng cùng dataset và traffic profile.
9. Thiết lập canary, release gate và rollback criteria.
10. Lưu evidence đủ để audit và tái lập sau nâng cấp.

## 2. Phạm vi kiểm thử sau nâng cấp

Một thay đổi dependency có thể ảnh hưởng nhiều lớp:

| Lớp | Ví dụ thay đổi | Rủi ro observability |
| --- | --- | --- |
| Java/runtime | JDK, JVM flags | Runtime metrics, memory/GC semantics |
| Spring Boot | Actuator, auto-configuration | Endpoint exposure, meter registration |
| Spring AI | ChatClient/model/tool observations | Observation names, tags, lifecycle |
| Micrometer | Core, registry, observation | Meter naming, filters, histogram export |
| OpenTelemetry | Bridge, SDK, exporter | Trace context, span attributes, export |
| Prometheus | Server, scrape config, rules | Staleness, query behavior, rule evaluation |
| Grafana | Dashboard/alerting version | Panel queries, No Data/Error states, notification |
| Model/provider | Model ID, usage response | Token/cost fields, latency and error classification |
| Application | Prompt, evaluator, pipeline | Quality verdicts, metric contract |

Không phải nâng cấp nào cũng làm thay đổi tất cả các lớp. Hãy ghi rõ thành phần nào thay đổi và thành phần nào được giữ nguyên.

### 2.1. Phân biệt hai loại regression

- **Instrumentation regression:** ứng dụng không ghi hoặc export telemetry đúng như trước, ví dụ metric biến mất hoặc label đổi tên.
- **Product/AI regression:** telemetry vẫn hoạt động nhưng chất lượng, latency hoặc cost thực sự thay đổi.

Hai loại có thể xảy ra cùng lúc. Không kết luận chất lượng model giảm khi evaluator coverage hoặc scrape completeness bị suy giảm.

### 2.2. Phạm vi của bài

Ví dụ sử dụng Spring Boot Actuator, Micrometer Prometheus registry, Prometheus và Grafana. Các metric `app.ai.*` là custom metrics do ứng dụng định nghĩa; tên thực tế trên Prometheus phải lấy từ scrape exposition của registry đang dùng.

## 3. Lập version inventory và compatibility matrix

Trước khi đổi dependency, ghi lại phiên bản đang chạy và phiên bản dự kiến. Không nâng đồng thời nhiều dependency nếu không cần thiết.

### 3.1. Inventory tối thiểu

Ghi các mục sau vào upgrade manifest:

- JDK và JVM vendor.
- Spring Boot.
- Spring AI BOM/starter và provider integrations.
- Micrometer core.
- Micrometer registry (Prometheus/OTLP).
- Micrometer Observation/Tracing bridge.
- OpenTelemetry API/SDK/exporter nếu có.
- Prometheus server và scrape configuration.
- Grafana và provisioning/dashboard schema.
- Model provider, model ID và usage metadata contract.
- Custom meter names, labels, histogram/SLO boundaries.
- Recording rules, alert rules và notification routes.

### 3.2. Compatibility matrix

| Component | Current | Candidate | Compatibility check | Evidence |
| --- | --- | --- | --- | --- |
| JDK | pinned | target | Supported runtime | Build/runtime report |
| Spring Boot | current | target | BOM/dependency alignment | Dependency tree |
| Spring AI | current | target | API + observation contract | Integration test |
| Micrometer | current | target | Registry naming/export | Scrape snapshot |
| OTel bridge | current | target | Context propagation/export | Trace test |
| Prometheus | current | target | Scrape/rules/query | promtool + targets |
| Grafana | current | target | Dashboard/alert behavior | Dashboard test |

Không tự suy ra compatibility chỉ từ việc ứng dụng compile. Đọc release notes/migration guide chính thức của đúng major/minor version và kiểm tra dependency convergence.

### 3.3. Phân biệt dependency được quản lý bởi BOM

Với Spring Boot/Spring AI, dùng BOM và dependency management được khuyến nghị cho tổ hợp phiên bản tương thích. Tránh override riêng Micrometer hoặc OpenTelemetry artifact khi BOM đã quản lý, trừ khi migration guide yêu cầu.

Lưu dependency tree trước và sau để phát hiện:

- Hai phiên bản Micrometer cùng tồn tại.
- Bridge OTel/Micrometer không tương thích.
- Provider starter kéo một phiên bản khác.
- Registry bị loại khỏi runtime classpath.
- Auto-configuration bị thay đổi do dependency exclusion.

Ví dụ Maven:

~~~bash
./mvnw -q dependency:tree -Dincludes=io.micrometer,io.opentelemetry,org.springframework.ai,org.springframework.boot
~~~

Ví dụ Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Chọn một build tool theo project. Không chạy lệnh của cả hai nếu project không dùng cả hai.

## 4. Chụp baseline trước nâng cấp

Baseline là bằng chứng để phân biệt thay đổi telemetry với thay đổi behavior.

### 4.1. Lưu scrape exposition

Lấy raw output từ endpoint Prometheus của ứng dụng trước nâng cấp, ví dụ `/actuator/prometheus`. Lưu:

- Metric names.
- HELP/TYPE metadata.
- Label names và các giá trị đại diện.
- Counter values.
- Histogram buckets, `_count`, `_sum`.
- Gauge values.

Không chỉ lưu screenshot dashboard. Raw exposition giúp phát hiện meter bị rename, filter hoặc không còn được đăng ký.

### 4.2. Lưu target health

Ghi trạng thái:

~~~promql
up{job="spring-ai"}
~~~

Ghi lại số target expected, target discovered và target scrape thành công. `up=0` khác với không có series `up`.

### 4.3. Lưu query results

Với mỗi dashboard panel quan trọng, lưu:

- Query text.
- Time range và timezone.
- Step/resolution.
- Raw result.
- Legend/label mapping.
- No Data/Error state nếu có.

So sánh query cùng time range và cùng workload profile. Không so một baseline giờ cao điểm với candidate giờ ít traffic.

### 4.4. Lưu dashboard và alert definitions

Export dashboard JSON, alert rules, recording rules và notification policy. Ghi version/UID và datasource reference. Trước khi nâng Grafana, lưu provisioning source hoặc backup cấu hình cần thiết theo quy trình vận hành.

### 4.5. Lưu baseline quality run

Chạy một evaluation dataset cố định và ghi:

- Expected/selected/completed cases.
- PASS/FAIL/INCONCLUSIVE/SKIPPED.
- Evaluator timeout/error.
- Score distributions.
- Retrieval metrics.
- Tool selection/execution outcomes.
- Token usage/cost.
- Model/retrieval/tool/evaluator latency.

Baseline cần ghi dataset, rubric, prompt, model, embedding/index và evaluator versions. Nếu một trong các biến này thay đổi, kết quả không còn là so sánh thuần instrumentation.

## 5. Xây metric contract trước và sau nâng cấp

Metric contract mô tả semantics mà dashboard và alert phụ thuộc. Không chỉ ghi tên metric.

### 5.1. Metric contract table

| Field | Cần xác định |
| --- | --- |
| Logical name | Tên ổn định trong code/catalog |
| Exported name | Tên thực tế trong scrape exposition |
| Type | Counter, Gauge, Timer, DistributionSummary |
| Unit | seconds, tokens, bytes, score, currency |
| Labels | Tên, taxonomy, cardinality budget |
| Lifecycle | Khi nào meter/series được tạo và cập nhật |
| Missing behavior | Khi nào series có thể không tồn tại |
| Histogram | Buckets/SLO boundaries/percentiles |
| Owner | Team chịu trách nhiệm |
| Consumers | Dashboard, alert, recording rule, SLO |

### 5.2. Ví dụ metric contract

| Logical metric | Type | Unit | Label dimensions |
| --- | --- | --- | --- |
| `app.ai.eval.criterion.completed` | Counter | events | `task_type`, `criterion`, `verdict` |
| `app.ai.eval.score` | DistributionSummary | score 0..1 | `task_type`, `criterion` |
| `app.ai.eval.duration` | Timer | seconds | `evaluator`, `outcome` |
| `app.ai.tool.execution` | Counter | events | `tool_family`, `outcome` |
| `app.ai.task.outcome` | Counter | events | `task_type`, `outcome` |

Đây là logical names. Micrometer registry có thể chuẩn hóa dấu chấm thành dấu gạch dưới, thêm suffix theo meter type và áp dụng convention riêng. Dùng exported name thực tế khi viết PromQL.

### 5.3. Kiểm tra metric rename

Nếu logical metric không đổi nhưng exported name thay đổi:

1. Xác định thay đổi đến từ registry convention, meter type hay custom naming.
2. Xác minh old và new series có cùng semantics/unit.
3. Cập nhật recording rules/dashboard/alerts có kế hoạch.
4. Nếu cần migration không gián đoạn, chạy dual-publish trong một khoảng thời gian ngắn.
5. Đặt ngày kết thúc dual-publish và xóa old path sau khi consumers đã chuyển.

Không tạo alias metric bằng cách đổi tên trong dashboard nếu unit hoặc semantics đã thay đổi.

## 6. Kiểm tra naming convention và unit

Một trong những lỗi phổ biến sau nâng cấp là query vẫn chạy nhưng đang đọc sai metric.

### 6.1. Không đoán tên Prometheus từ tên Java

Ví dụ logical meter:

~~~java
Counter.builder("app.ai.tool.execution")
        .tag("tool_family", "order")
        .tag("outcome", "error")
        .register(registry)
        .increment();
~~~

Registry Prometheus thường export Counter với suffix `_total`, nhưng convention cụ thể phụ thuộc Micrometer registry/version và meter naming. Timer có thể export `_seconds_count`, `_seconds_sum`, `_seconds_max` và histogram `_bucket`. DistributionSummary có `_count`, `_sum` và bucket nếu histogram được bật.

Hãy mở raw exposition và ghi chính xác tên. Không sao chép tên ví dụ vào production query khi chưa xác minh.

### 6.2. Kiểm tra unit

Đơn vị thời gian thường là nguyên nhân gây sai dashboard:

- `Timer` có thể được export theo base unit seconds.
- Metric custom có thể mang suffix `_milliseconds` nếu app tự đặt tên sai.
- Một dashboard cũ có thể nhân/chia 1000 lần.

Đặt tên và unit theo convention của registry; không mã hóa đơn vị hai lần trong metric name và base unit.

### 6.3. So sánh HELP/TYPE

Một exported name giữ nguyên nhưng TYPE đổi từ counter sang gauge là breaking change đối với query. Tương tự, cùng metric name nhưng unit đổi từ milliseconds sang seconds làm mọi threshold và alert sai.

Kiểm tra HELP/TYPE cùng sample values, không chỉ tìm tên metric.

## 7. Kiểm tra labels và cardinality

Dashboard có thể trống sau nâng cấp vì label key đổi, label value thay taxonomy hoặc meter filter loại bỏ tag.

### 7.1. Label contract

Ví dụ label values hữu hạn:

- `task_type`: `rag`, `tool`, `policy`, `other`.
- `criterion`: `relevance`, `groundedness`, `fact_check`, `tool_selection`.
- `verdict`: `pass`, `fail`, `inconclusive`, `skipped`.
- `outcome`: `success`, `error`, `timeout`, `cancelled`.
- `evaluator`: `rule_based`, `model_judge`, `human`.

Không dùng run ID, case ID, user ID, conversation ID, prompt text, exception message hoặc trace ID làm Prometheus labels.

### 7.2. Kiểm tra label rename

Nếu `tool_family` đổi thành `tool`, query selector cũ sẽ trả empty vector. Kiểm tra label names từ exposition:

~~~promql
count by (__name__) ({__name__=~"app_ai_.*"})
~~~

PromQL không cung cấp một truy vấn tổng quát để liệt kê mọi label key/value như API metadata; dùng `/api/v1/series`, `/api/v1/labels` hoặc raw scrape exposition để điều tra.

### 7.3. Kiểm tra cardinality

So sánh số series theo metric family trước và sau. Nếu series tăng đột biến, kiểm tra:

- Label value mới được sinh từ input tự do.
- Thêm dimension model/prompt version không giới hạn.
- Tag có chứa path/URL/exception class động.
- Histogram bật thêm nhiều buckets.
- Meter registration lặp với nhiều tag combinations.

Đặt budget theo metric family và theo dõi số active series. Không chỉ nhìn tổng Prometheus series vì một metric có thể tăng cardinality trong khi tổng hệ thống vẫn ổn.

## 8. Kiểm tra MeterRegistry và Observation lifecycle

Sau nâng cấp Spring Boot/Spring AI/Micrometer, xác minh meter được đăng ký và cập nhật tại đúng thời điểm.

### 8.1. Kiểm tra registry thực tế

Trong integration test hoặc diagnostic endpoint nội bộ, kiểm tra:

- Prometheus registry có trong application context.
- MeterFilter không deny metric cần thiết.
- Custom `MeterBinder` được gọi.
- Meter names/tags đúng contract.
- Counter/Gauge không bị đăng ký trùng.
- Gauge giữ object reference còn sống.

### 8.2. Kiểm tra Spring AI observations

Các observation cho ChatClient, model và tool phụ thuộc phiên bản Spring AI và cấu hình. Khi nâng cấp:

1. Ghi danh sách observation/span names hiện tại.
2. Chạy một request chat-only, một RAG request và một tool call.
3. Kiểm tra trace có đủ parent/child spans.
4. Xác minh low-cardinality key values vẫn ổn định.
5. Xác minh high-cardinality attributes không bị chuyển thành metric labels.
6. Kiểm tra exception/status propagation.

Không giả định observation name hoặc attribute key giữ nguyên qua mọi major version. Dùng migration guide và trace thực tế của phiên bản đang chạy.

### 8.3. Kiểm tra context propagation

Một trace có thể bị tách thành nhiều trace nếu context không truyền qua executor, Reactor, async callbacks hoặc message queue. Kiểm thử:

- Synchronous request.
- Async evaluator.
- Reactive pipeline.
- Tool dispatch.
- Queue worker nếu có.

Xác minh trace ID được liên kết xuyên suốt và không ghi trace ID thành metric tag.

## 9. Kiểm tra histogram và percentile

Histogram config có thể thay đổi số bucket hoặc cách export khi registry/version đổi. Dashboard p95 vẫn trả số nhưng có thể dùng bucket khác hoặc mất histogram.

### 9.1. Xác minh bucket series

Với Timer:

~~~promql
count by (le) (
  app_ai_eval_duration_seconds_bucket
)
~~~

Truy vấn giúp xem các bucket label đang có. Kiểm tra raw exposition để xác minh boundaries và `_count`/`_sum`.

### 9.2. p95 với classic histogram

~~~promql
histogram_quantile(
  0.95,
  sum by (le, evaluator, outcome) (
    rate(app_ai_eval_duration_seconds_bucket[5m])
  )
)
~~~

Chỉ dùng query này nếu metric thực sự là classic histogram với bucket `le`. Nếu registry/exporter chuyển sang native histogram hoặc tên/format khác, cần cập nhật query theo dạng dữ liệu mới.

### 9.3. So sánh p95 không đủ

So sánh:

- Histogram bucket boundaries.
- Sample count.
- Sum/mean.
- p50/p95/p99.
- Tỷ lệ timeout/error.
- SLO bucket counts.

Nếu p95 thay đổi mạnh nhưng sample count giảm hoặc histogram không còn export, điều tra instrumentation trước khi kết luận latency thay đổi.

### 9.4. DistributionSummary cho score

Score 0..1 có thể được export dưới `_count`, `_sum` và `_bucket` khi histogram bật. Kiểm tra các SLO boundaries vẫn bao gồm threshold rubric. Nếu ngưỡng PASS là 0.8 mà bucket 0.8 bị loại, query tỷ lệ đạt ngưỡng có thể sai.

## 10. Kiểm tra Prometheus scrape và target health

### 10.1. Target health

~~~promql
up{job="spring-ai"}
~~~

- `1`: scrape thành công.
- `0`: target được scrape nhưng scrape thất bại.
- Empty result: không có series khớp selector, target chưa được discovery hoặc series đã stale/mất.

Không gộp ba trạng thái thành zero traffic.

### 10.2. Phát hiện target biến mất

~~~promql
absent_over_time(up{job="spring-ai"}[5m])
~~~

Biểu thức trả series nếu không có sample matching trong cửa sổ. Nó không biết số target kỳ vọng; cần inventory/service discovery hoặc expected target count để phát hiện thiếu một phần target.

### 10.3. Scrape freshness

Nếu có metric heartbeat do ứng dụng cập nhật:

~~~promql
time() - app_ai_telemetry_last_successful_observation_timestamp_seconds
~~~

Giá trị lớn cho biết lần observation gần nhất đã cũ. Nếu metric biến mất, query cũng empty; kết hợp target health và absent checks.

### 10.4. Scrape interval và rate window

Sau nâng cấp, scrape interval hoặc evaluation interval có thể thay đổi. `rate()`/`increase()` cần đủ samples trong range. Chọn window đủ lớn so với scrape interval và traffic. Một query rỗng với series mới chỉ có một sample không đồng nghĩa rate bằng zero.

## 11. Kiểm thử PromQL sau nâng cấp

Mỗi query quan trọng cần có input fixture và kết quả kỳ vọng. Đừng chỉ kiểm tra query syntax.

### 11.1. Golden query cases

Chuẩn bị fixture cho:

1. Có PASS và FAIL.
2. Chỉ có PASS.
3. Chỉ có INCONCLUSIVE.
4. Không có evaluation data.
5. Target up=0.
6. Target series biến mất.
7. Counter reset sau restart.
8. Histogram có sample ở các bucket.
9. Một label value mới xuất hiện.
10. Metric series bị thiếu do MeterFilter.

### 11.2. PASS rate

~~~promql
sum by (task_type, criterion) (
  rate(app_ai_eval_criterion_completed_total{verdict="pass"}[15m])
)
/
sum by (task_type, criterion) (
  rate(app_ai_eval_criterion_completed_total{verdict=~"pass|fail"}[15m])
)
~~~

Kỳ vọng:

- PASS=8, FAIL=2: ratio 80% nếu hai nhóm có cùng cửa sổ và sample profile.
- Chỉ có PASS: 100% chỉ hợp lệ khi coverage/telemetry completeness chứng minh không có FAIL; nếu FAIL series đáng lẽ phải tồn tại nhưng biến mất, đây là instrumentation regression.
- Chỉ có INCONCLUSIVE: mẫu số không có decided cases; kết quả N/A/No Data.
- Không có series: No Data, không tự điền 100%.

### 11.3. Không che missing bằng vector(0)

`or vector(0)` tạo fallback không nhãn và không biết dimensions mong đợi. Nó có thể gây một series zero không nhãn bên cạnh series có labels hoặc làm dashboard hiểu sai. Nếu cần zero theo `task_type`/`criterion`, dùng info metric/pre-initialization cho tập dimensions hữu hạn và giám sát health riêng.

### 11.4. Counter reset

Sau restart, Counter có thể reset về 0. Dùng `rate()`/`increase()` trên Counter raw; không lấy delta thủ công giữa hai instant values. Kiểm thử restart/redeploy để xác minh rate không tạo spike giả.

### 11.5. Recording rules

Nếu dashboard dùng recording rules, test cả source query và recorded series. Rule có thể không còn match sau metric rename hoặc label change dù panel query nhìn có vẻ đúng.

## 12. Kiểm tra Grafana dashboard

Dashboard test cần xác minh cả dữ liệu và cách thể hiện.

### 12.1. Panel inventory

| Panel | Query contract | Visual expectation |
| --- | --- | --- |
| Request rate | Counter rate | Có đơn vị requests/s |
| Model latency | Timer histogram | p50/p95/p99 có unit seconds |
| Tool error rate | Error / total attempts | No Data khi không có attempts |
| Evaluation PASS rate | PASS / (PASS + FAIL) | Hiển thị denominator/coverage |
| Score distribution | Summary histogram | Threshold rubric hiển thị |
| Evaluator availability | timeout/error / attempts | Tách evaluator failure khỏi quality FAIL |
| Task outcome | verified_success/terminal | Pending không bị tính thành failed |
| Token/cost | Usage và currency | Không trộn currency |
| Scrape health | `up`/absent | Phân biệt down và missing |

### 12.2. Dashboard variables

Kiểm tra variables:

- `job`.
- `instance` hoặc service group.
- `task_type`.
- `criterion`.
- `environment`.
- `release_channel` nếu cardinality hữu hạn.

Sau nâng cấp, label key đổi có thể làm variable query trả empty. Kiểm tra variable options với datasource mới và xác minh multi-select/All behavior.

### 12.3. Unit và legend

Kiểm tra:

- seconds vs milliseconds.
- requests/s vs total requests.
- ratio 0..1 vs percentage 0..100.
- currency và cost unit.
- tokens vs token/s.
- histogram quantile legend có đúng evaluator/task labels.

Một panel có số liệu vẫn có thể sai nếu unit hoặc legend sai.

### 12.4. No Data và Error

Test ba trường hợp riêng:

- No Data: query không có series/sample.
- Error: datasource/query execution thất bại.
- Zero: series có giá trị quan sát bằng 0.

Grafana alerting có cấu hình riêng cho No Data và Error; hành vi có thể thay đổi theo phiên bản và rule type. Kiểm tra trạng thái thực tế và notification policy, không giả định No Data tự động tương đương alert firing.

### 12.5. Dashboard provisioning

Nếu dashboard được quản lý bằng provisioning:

1. Export JSON trước nâng cấp.
2. Validate JSON sau nâng cấp.
3. Import vào folder test riêng.
4. Kiểm tra datasource UID và dashboard UID.
5. Mở các panel quan trọng bằng cùng time range.
6. Kiểm tra biến và annotation.
7. So sánh JSON diff, bỏ qua field runtime không ổn định nếu cần.

Không sửa trực tiếp dashboard production để thử nghiệm.

## 13. Kiểm thử alert rules và notification

Một alert đúng syntax vẫn có thể không gửi notification hoặc gửi quá nhiều.

### 13.1. Alert scrape target down

~~~yaml
groups:
  - name: spring-ai-observability
    rules:
      - alert: SpringAiScrapeTargetDown
        expr: up{job="spring-ai"} == 0
        for: 2m
        labels:
          severity: page
        annotations:
          summary: "Spring AI metrics target is down"
          description: "Prometheus cannot scrape {{ $labels.instance }}."
~~~

Alert này chỉ bắt target tồn tại nhưng scrape thất bại. Cần rule riêng cho target series biến mất hoặc expected target count bị thiếu.

### 13.2. Alert evaluator error rate

Đây là rule thứ hai trong cùng danh sách `rules` của group ở ví dụ trước. Khi lưu thành file độc lập, đặt rule này trong một group có `rules` list riêng.

~~~yaml
      - alert: SpringAiEvaluatorErrorRateHigh
        expr: |
          (
            sum(rate(app_ai_eval_execution_total{
              outcome=~"timeout|error"
            }[10m]))
            /
            sum(rate(app_ai_eval_execution_total[10m]))
          ) > 0.05
          and
          sum(rate(app_ai_eval_execution_total[10m])) > 0
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Spring AI evaluator error rate is high"
          description: "More than 5% of evaluator attempts failed."
~~~

Ngưỡng 5% chỉ là ví dụ. Nếu denominator không có attempts, biểu thức không kích hoạt; tạo alert riêng cho evaluator inactivity/coverage thấp nếu đó là điều cần phát hiện.

### 13.3. Alert quality regression

Quality regression alert nên dựa trên:

- Cùng rubric/evaluator version.
- Đủ sample size.
- Coverage đạt ngưỡng.
- Cùng task_type/criterion hoặc cohort tương đương.
- Baseline đã được xác nhận.

Với offline batch, thường phù hợp hơn khi quality gate chạy trong evaluation pipeline và publish run summary. Không dùng rate trong 5 phút cho batch chạy một lần mỗi đêm.

### 13.4. Test alert lifecycle

Kiểm tra:

1. Inactive khi dữ liệu bình thường.
2. Pending khi condition đúng nhưng chưa đủ `for`.
3. Firing sau khi vượt thời gian.
4. Resolved khi condition hồi phục.
5. No Data khi series biến mất.
6. Error khi datasource/rule evaluation lỗi.
7. Notification routing, grouping, silence và inhibition.

### 13.5. Không gửi test notification đến người thật

Trong staging, dùng receiver/sink riêng hoặc notification endpoint giả lập. Xác minh payload, labels, annotations và grouping trước khi bật routing production.

## 14. Tự động kiểm tra Prometheus rules

Prometheus cung cấp `promtool` để kiểm tra syntax và mô phỏng rule evaluation.

### 14.1. Validate rule files

~~~bash
promtool check rules rules/spring-ai-alerts.yml
~~~

### 14.2. Test rule với fixture

Ví dụ file `tests/spring-ai-alerts.test.yml`:

~~~yaml
rule_files:
  - ../rules/spring-ai-alerts.yml
evaluation_interval: 1m
tests:
  - interval: 1m
    input_series:
      - series: 'up{job="spring-ai",instance="spring-ai-app:8080"}'
        values: '1 1 0 0 0'
    alert_rule_test:
      - eval_time: 4m
        alertname: SpringAiScrapeTargetDown
        exp_alerts:
          - exp_labels:
              job: spring-ai
              instance: spring-ai-app:8080
              severity: page
~~~

Chạy:

~~~bash
promtool test rules tests/spring-ai-alerts.test.yml
~~~

Đảm bảo đường dẫn `rule_files` được resolve đúng theo working directory/cách gọi `promtool` của phiên bản đang dùng. Có thể chạy lệnh từ project root hoặc thống nhất đường dẫn tương đối trong CI. Thêm fixture cho evaluator error và missing target; test rule `absent_over_time` riêng với expected behavior.

### 14.3. Test recording rules

Nếu dashboard dùng recording rules, thêm test expression và expected sample values. Không chỉ test alert rules mà bỏ qua các series trung gian mà dashboard phụ thuộc.

## 15. Kiểm thử ứng dụng và scrape exposition

PromQL test không thể phát hiện một meter chưa từng được export nếu fixture không chạy qua ứng dụng.

### 15.1. Unit test với SimpleMeterRegistry

Unit test kiểm tra:

- Counter tăng đúng số lần.
- Score được ghi vào DistributionSummary.
- Timer có count và duration đúng.
- Tag values nằm trong taxonomy.
- Invalid score không ghi metric.
- Missing/inconclusive không bị đổi thành zero score.

SimpleMeterRegistry không xác minh Prometheus naming convention.

### 15.2. Integration test với Prometheus registry

Dùng registry/exporter thực tế của ứng dụng để:

1. Khởi tạo Spring context test.
2. Chạy một request chat-only.
3. Chạy một RAG request.
4. Chạy một tool call thành công và một tool error fixture.
5. Chạy evaluator PASS/FAIL/INCONCLUSIVE và timeout fixture.
6. Lấy scrape exposition.
7. Kiểm tra metric names, TYPE, labels, units và bucket boundaries.
8. Xác nhận không có ID hoặc nội dung tự do trong labels.

### 15.3. Kiểm tra metric registration sau restart

Khởi động lại ứng dụng và kiểm tra:

- Meter được đăng ký lại.
- Counter reset được xử lý đúng bởi PromQL.
- Gauge không giữ object cũ.
- Không có meter trùng do lifecycle callback chạy nhiều lần.
- Scrape endpoint tiếp tục hoạt động.

## 16. So sánh baseline và candidate

So sánh cần giữ workload và evaluation input ổn định.

### 16.1. Test matrix

| Test | Baseline | Candidate | Expected |
| --- | --- | --- | --- |
| Scrape target | UP | UP | Cùng job/target contract |
| Metric family | Snapshot | Snapshot | Không mất metric quan trọng |
| Labels | Snapshot | Snapshot | Không rename ngoài kế hoạch |
| Histogram | Snapshot | Snapshot | Unit/buckets đúng |
| PromQL | Golden queries | Golden queries | Cùng semantics |
| Dashboard | Export | Import/test | Panel/variable đúng |
| Alerts | Rule tests | Rule tests | Lifecycle/route đúng |
| Traces | Sample traces | Sample traces | Context/attributes đúng |
| Evaluation | Same dataset | Same dataset | Coverage/verdict comparable |
| Cost/latency | Same workload | Same workload | Unit/cohort comparable |

### 16.2. Diff metric catalog

Tạo diff gồm:

- Added metric families.
- Removed metric families.
- Renamed metrics.
- Changed TYPE/unit.
- Added/removed labels.
- Changed label values.
- Changed histogram buckets.
- Changed sample count/cardinality.

Mỗi diff phải có lý do và consumer impact. Removed metric mà dashboard/alert vẫn tham chiếu là breaking change.

### 16.3. So sánh kết quả quality

Chỉ so sánh khi:

- Dataset và ground truth giống nhau.
- Rubric/evaluator version tương thích.
- Expected cases và coverage được công bố.
- Model/prompt/pipeline variables được ghi rõ.
- Telemetry completeness đạt ngưỡng.

Nếu mục tiêu nâng cấp là dependency observability, giữ model/prompt/dataset cố định. Nếu nâng cấp cả model hoặc prompt, tách thí nghiệm để không gán nhầm thay đổi.

## 17. Canary và rollout

Không thay toàn bộ production observability stack cùng lúc nếu có thể triển khai theo giai đoạn.

### 17.1. Staging

- Nâng dependency và registry.
- Chạy golden tests.
- Kiểm tra scrape/query/dashboard/alerts.
- Chạy evaluation dataset.
- Kiểm tra evidence và cleanup.

### 17.2. Canary

Triển khai candidate lên một phần instance:

- Theo dõi target health và scrape completeness.
- So metric names/labels giữa baseline và candidate.
- So latency, error, token usage và quality coverage.
- Theo dõi cardinality và Prometheus ingestion.
- Kiểm tra alert noise và notification route.

Không dùng label `instance` làm dimension để tổng hợp product quality nếu mục tiêu là so release; dùng release cohort hữu hạn và label cardinality thấp.

### 17.3. Rollout gates

Ví dụ:

| Gate | Điều kiện |
| --- | --- |
| Instrumentation | Metric catalog contract đạt |
| Scrape | Expected targets healthy |
| Queries | Golden PromQL tests PASS |
| Dashboard | Không panel quan trọng nào No Data ngoài dự kiến |
| Alerts | Rule tests và notification sink PASS |
| Traces | Context propagation đạt |
| Quality | Evaluation coverage đủ, không có critical regression |
| Cost | Ingestion/cardinality không vượt budget |

### 17.4. Rollback trigger

Rollback hoặc pause rollout nếu:

- Metric family quan trọng biến mất.
- Alert/recording rule không còn đúng.
- Dashboard quality hiển thị false green do missing data.
- Scrape failures hoặc cardinality tăng vượt budget.
- Trace context bị mất ở critical path.
- Critical quality/business guardrail vi phạm.

Không rollback chỉ vì một panel thẩm mỹ thay đổi nếu semantics và alerting đã được xác minh; ghi nhận và lên kế hoạch sửa dashboard.

## 18. Rollback và tương thích ngược

Rollback cần được chuẩn bị trước khi rollout.

### 18.1. Giữ compatibility window

Nếu đổi metric names hoặc labels, có thể dual-publish old/new metrics tạm thời:

1. Export cả hai trong một release.
2. Chuyển dashboard/alerts sang new series.
3. Xác minh consumers đã chuyển.
4. Theo dõi một compatibility window.
5. Xóa old series ở release sau.

Không dual-publish lâu dài nếu làm tăng cardinality hoặc ingestion cost đáng kể.

### 18.2. Dashboard rollback

Giữ dashboard JSON trước nâng cấp. Nếu candidate panel sai, restore dashboard version đã export; không cần rollback application nếu telemetry contract vẫn đúng và vấn đề chỉ ở visualization.

### 18.3. Alert rollback

Giữ rule files và notification policy cũ. Khi rollback, xác minh rule evaluation và notification route sau khi restore. Không tắt alert toàn bộ chỉ để loại bỏ noise; sửa selector/threshold hoặc silence có thời hạn và owner.

### 18.4. Schema và data compatibility

Nếu evaluation result schema thay đổi, version hóa record và hỗ trợ reader cũ trong giai đoạn migration nếu cần. Không xóa raw results cũ trước khi report/evidence đã được export và kiểm tra.

## 19. Troubleshooting sau nâng cấp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Dashboard trống | Metric rename, scrape fail, label selector cũ | Raw exposition, `up`, selector |
| p95 bằng N/A | Histogram mất hoặc thiếu samples | `_bucket`, `_count`, registry config |
| p95 tăng 1000 lần | Unit seconds/milliseconds bị đổi | HELP/TYPE, base unit, panel unit |
| PASS rate thành 100% | FAIL series missing hoặc denominator selector sai | PASS/FAIL counts, coverage |
| Alert không fire | Rule inactive, query empty, `for` chưa đủ | Prometheus rules/alert state |
| Alert fire liên tục | Label churn, threshold, No Data mapping | Rule output, Grafana state |
| Trace bị tách | Context propagation/bridge mismatch | Span parent IDs, async boundary |
| Cardinality tăng | Tag value động hoặc bucket tăng | Series count theo metric family |
| Metric trùng | Binder/bean lifecycle đăng ký lặp | Registry meter list |
| Quality metric không khớp report | Retry/double emission hoặc commit ordering | Result store/outbox và counters |

### 19.1. Dashboard trống nhưng target UP

`up=1` chỉ chứng minh scrape endpoint trả lời. Nó không chứng minh metric family cụ thể đã được đăng ký. Kiểm tra:

1. Raw exposition có metric family không?
2. MeterFilter có loại metric không?
3. Lazy meter đã từng được tạo chưa?
4. Metric name hoặc label key có đổi không?
5. Query range có đủ samples không?

### 19.2. PASS rate tăng sau nâng cấp

Không vội kết luận quality cải thiện. Kiểm tra FAIL series, evaluator coverage, skipped/inconclusive, dataset mix, rubric version và evaluator error. Missing FAIL series có thể làm query denominator nhỏ đi hoặc rỗng.

### 19.3. Alert No Data sau rollout

Kiểm tra alert rule datasource, query output, No Data/Error state mapping, target discovery và scrape interval. Ghi lại notification receiver thử nghiệm để xác minh alert lifecycle end-to-end.

## 20. Bài thực hành tổng hợp

**Bối cảnh:** ứng dụng Spring AI được nâng Spring Boot và Micrometer. Sau deploy:

- Endpoint Actuator vẫn trả HTTP 200.
- Dashboard model latency p95 chuyển sang No Data.
- Evaluation PASS rate tăng từ 91% lên 100%.
- Alert evaluator timeout không còn kích hoạt.
- Prometheus active series tăng 35%.
- Trace của tool call đôi lúc không có parent span.

### Phần A — Chẩn đoán

1. Xác định các giả thuyết instrumentation regression.
2. Chọn raw exposition, target health và trace evidence cần lấy.
3. Kiểm tra metric names, TYPE, units, labels và histogram buckets.
4. Xác định liệu PASS rate tăng có thể do FAIL series missing hay evaluator coverage giảm.
5. Tìm nguyên nhân cardinality tăng.

### Phần B — Viết test

1. Tạo fixture Counter PASS/FAIL và test PASS rate.
2. Tạo fixture evaluator timeout/error và test alert.
3. Tạo histogram fixture và test p95 query.
4. Test target up=0 và target series absent.
5. Test dashboard variables với label key mới.
6. Test trace parent-child qua async tool execution.

### Phần C — Release decision

1. Quyết định có tiếp tục rollout không.
2. Định nghĩa gate để mở lại rollout.
3. Xác định dashboard/alert cần sửa và metric contract nào phải giữ tương thích.
4. Lập kế hoạch rollback nếu candidate không đạt.

### Phần D — Evidence

1. Lưu dependency inventory và compatibility matrix.
2. Lưu baseline/candidate scrape exposition.
3. Lưu PromQL golden test results và promtool output.
4. Export dashboard/alert definitions.
5. Lưu trace references đã scrub.
6. Viết comparison report và quyết định rollout.

### Câu hỏi tự kiểm tra

- Vì sao HTTP 200 của Actuator không chứng minh metric family tồn tại?
- `up=0` khác absent `up` thế nào?
- Vì sao metric name giữ nguyên nhưng TYPE/unit đổi vẫn là breaking change?
- Timer histogram mất bucket ảnh hưởng p95 ra sao?
- Vì sao `or vector(0)` có thể tạo false green?
- Khi nào cần dual-publish metric cũ và mới?
- Làm sao kiểm tra Grafana No Data khác Error?
- Vì sao alert rule cần test notification sink?
- Tại sao SimpleMeterRegistry không đủ để xác minh Prometheus exposition?
- Làm sao phát hiện trace context bị mất qua async boundary?
- Vì sao quality regression không thể kết luận khi evaluator coverage thấp?
- Rollback dashboard có nhất thiết phải rollback application không?

## 21. Những điều cần ghi nhớ

1. **Chụp baseline trước khi nâng cấp.** Giữ dependency inventory, scrape exposition, query results, dashboard, alert rules và evaluation summary.
2. **Metric contract bao gồm semantics, type, unit, labels và lifecycle.** Tên metric giống nhau không bảo đảm dữ liệu tương đương.
3. **Không đoán exported names.** Kiểm tra raw exposition của registry đang chạy.
4. **Kiểm tra labels và cardinality.** Label rename làm query rỗng; label động làm tăng series.
5. **Histogram cần được kiểm tra riêng.** Bucket boundaries, count, sum và unit ảnh hưởng percentile/SLO.
6. **`up=1` không chứng minh mọi meter đều tồn tại.** Target health và metric completeness là hai kiểm tra khác nhau.
7. **No Data, Error và Zero là ba trạng thái khác nhau.** Không tự động chuyển missing thành zero.
8. **Test PromQL bằng fixture và promtool.** Kiểm tra syntax, expected values, alert lifecycle và recording rules.
9. **Kiểm tra Grafana variables, units và alert state.** Panel có số liệu vẫn có thể sai semantics.
10. **Tách instrumentation regression khỏi AI quality regression.** Coverage thấp hoặc evaluator lỗi làm kết luận quality không đáng tin.
11. **Canary trước rollout rộng.** Theo dõi scrape, query, dashboard, alert, trace, quality và cardinality.
12. **Chuẩn bị rollback và compatibility window.** Dual-publish chỉ tạm thời và có kế hoạch kết thúc.

## Tài liệu tham khảo

- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): registry, meter filters và export.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): ChatClient/model/tool observations.
- [Micrometer Reference — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html): Prometheus registry và exposition.
- [Micrometer Reference — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): histogram, SLO buckets và quantiles.
- [Micrometer Reference — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): meter naming/filtering và cardinality.
- [Prometheus — Jobs and Instances](https://prometheus.io/docs/concepts/jobs_instances/): target scrape health và `up`.
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): rate, increase, absent và histogram_quantile.
- [Prometheus — Recording Rules](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/): rule configuration và evaluation.
- [Prometheus — Unit Testing Rules](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/): promtool rule tests.
- [Grafana — Alert rule evaluation](https://grafana.com/docs/grafana/latest/alerting/fundamentals/alert-rule-evaluation/): Pending, Firing, No Data và Error.
- [Grafana — Dashboard JSON model](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/view-dashboard-json-model/): export và kiểm tra dashboard.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): trace context qua service/process boundaries.

**Lưu ý phiên bản:** Spring AI observation names, Spring Boot Actuator behavior, Micrometer Prometheus naming, histogram export và Grafana alert state phụ thuộc phiên bản/cấu hình. Các metric `app.ai.*` và alert rules trong bài là ví dụ custom. Trước khi rollout, đối chiếu migration guide của đúng phiên bản và xác minh raw exposition, PromQL results, dashboard panels, notification delivery và trace context trong môi trường staging.
