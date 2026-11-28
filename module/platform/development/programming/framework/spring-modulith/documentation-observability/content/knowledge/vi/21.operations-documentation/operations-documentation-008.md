# Document thay đổi telemetry khi nâng cấp

Mỗi lần nâng Spring Boot, Spring Modulith, Micrometer, Micrometer Tracing hoặc OpenTelemetry, ứng dụng có thể thay đổi cách tạo, đặt tên, gắn thuộc tính, xuất và lưu telemetry. Một bản nâng cấp có thể không làm thay đổi nghiệp vụ nhưng vẫn khiến dashboard mất series, alert không còn khớp, trace thiếu span, log không còn correlation ID hoặc Collector nhận dữ liệu ở endpoint khác.

Vì vậy, nâng cấp dependency observability cần có **telemetry change record** đi cùng hồ sơ nâng cấp. Tài liệu này ghi lại tín hiệu trước và sau thay đổi, lý do, mức tương thích, ảnh hưởng tới dashboard/alert/SLO, cách kiểm chứng và phương án rollback. Nó giúp người trực vận hành biết dữ liệu đã đổi ở đâu và cách đọc dữ liệu mới sau deploy.

Bài thuộc chương **Tài liệu vận hành** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Phạm vi gồm module graph, Actuator, event metrics, module spans, context propagation, logs, sampling, OTLP exporter, Collector và các dashboard/alert dùng những tín hiệu đó.

> **Nguyên tắc:** không suy đoán telemetry sẽ thay đổi chỉ từ việc tăng version. Hãy đối chiếu release notes, migration guide, dependency graph, cấu hình thực tế và dữ liệu runtime. Các ví dụ version trong bài là tình huống minh họa có nguồn chính thức; dự án phải ghi đúng phiên bản đang dùng.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Lập inventory telemetry trước khi nâng cấp.
2. Phân loại thay đổi về metrics, traces, logs, event publication, resource attributes và OTLP transport.
3. Ghi lại tên meter/span, tags/attributes, units, cardinality và semantic meaning trước/sau.
4. Đối chiếu release notes của Spring Boot, Spring Modulith, Micrometer và OpenTelemetry.
5. Phát hiện breaking change ảnh hưởng dashboard, PromQL, alert, SLO và retention.
6. Thiết kế kiểm thử tương thích telemetry trong CI, staging và canary.
7. Lập kế hoạch dual-read/dual-write hoặc chuyển đổi có kiểm soát khi schema thay đổi.
8. Ghi bằng chứng triển khai, quyết định rollback và chủ sở hữu vận hành.

## 2. Vì sao phải document telemetry khi nâng cấp?

Telemetry là giao diện giữa ứng dụng và hệ thống vận hành. Dashboard, alert rules, SLO queries, log search và tracing backend đều phụ thuộc vào hình dạng dữ liệu được phát ra.

Ví dụ, một dashboard có thể truy vấn:

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Nếu tên metric, tag key hoặc cách chuẩn hóa URI thay đổi, dashboard có thể trả về rỗng dù ứng dụng vẫn nhận request bình thường. Tương tự, alert dựa trên span attribute cũ có thể không phát hiện lỗi sau khi instrumentation đổi semantic convention.

Một telemetry change record giúp trả lời:

- Phiên bản và cấu hình nào tạo ra dữ liệu cũ?
- Phiên bản và cấu hình nào tạo ra dữ liệu mới?
- Thay đổi là additive, semantic, breaking hay chỉ thay đổi transport?
- Dashboard/alert nào bị ảnh hưởng?
- Dữ liệu cũ và mới có thể so sánh trực tiếp không?
- Cần sửa query, retention, sampling hoặc Collector pipeline nào?
- Điều kiện nào chứng minh có thể tiếp tục rollout?
- Khi nào phải rollback và cách phục hồi dashboard/alert ra sao?

### Telemetry là một hợp đồng vận hành

Một hợp đồng telemetry cần định nghĩa tối thiểu:

| Thành phần | Nội dung phải ghi |
| --- | --- |
| Producer | Ứng dụng, module, library hoặc agent tạo tín hiệu |
| Signal | Metrics, traces, logs hoặc event/publication state |
| Identity | service.name, version, environment, module identifier |
| Schema | Metric/span/log names, tag/attribute keys, data types, units |
| Semantics | Tín hiệu đo điều gì, thời điểm nào, phạm vi nào |
| Transport | OTLP/HTTP, OTLP/gRPC, Prometheus scrape hoặc log pipeline |
| Destination | Collector, metrics backend, tracing backend, log backend |
| Consumer | Dashboard, alert, SLO, runbook, audit/report |
| Compatibility | Additive, compatible, migration-required hoặc breaking |
| Evidence | Release note, config diff, scrape, trace, log, test result |

## 3. Phạm vi và đối tượng phải inventory

Trước khi nâng cấp, liệt kê mọi thành phần có thể phát hoặc tiêu thụ telemetry:

| Nhóm | Những gì cần kiểm tra |
| --- | --- |
| Spring Boot | Actuator, auto-configuration, observation conventions, logging pattern, tracing và OTLP properties |
| Spring Modulith | Insight starter, module spans, event publication metrics, Event Publication Registry |
| Micrometer | Observation handlers, meter names, tags, registries, filters, naming convention |
| Micrometer Tracing | Bridge, sampler, propagator, MDC correlation, span processors |
| OpenTelemetry SDK | Resource, instrumentation scope, semantic conventions, exporter, schema URL |
| OpenTelemetry Collector | Receiver, processor, exporter, routing, tail sampling, authentication |
| Prometheus | Scrape targets, metric names, labels, recording rules và alert rules |
| Tracing backend | Service filters, span attributes, retention, query và trace search |
| Logging backend | Pattern/JSON schema, MDC fields, parsing, index mapping, retention |
| Dashboard/SLO | Queries, units, thresholds, grouping, annotations và owner |
| Deployment | Environment variables, secrets, ports, service DNS, rollout và rollback |

Trong ứng dụng modular monolith, ghi rõ các module có liên quan như order, inventory, billing và notification. Cùng một tiến trình thường có chung service.name; module identity nên nằm ở span name/attributes hoặc logger/module metadata theo instrumentation. Không tự biến mỗi application module thành một service độc lập trong tài liệu nếu kiến trúc thực tế vẫn là một ứng dụng.

### Inventory tín hiệu theo module

Ví dụ một bảng inventory:

| Module/luồng | Metrics | Traces | Logs | Consumer vận hành |
| --- | --- | --- | --- | --- |
| order | Request count, latency, event published | HTTP span, module invocation span | Order lifecycle, validation failure | Order dashboard, error-rate alert |
| inventory | Listener success/failure, backlog, stock operation | Module span, event listener span | Reservation, retry, exception | Backlog alert, inventory runbook |
| billing | Payment outcome, duration | Payment/module span | Gateway result, timeout | Payment SLO, latency alert |
| notification | Delivery count, failure | Notification span | Provider response, retry | Delivery dashboard |

Bảng này là ví dụ cấu trúc. Thay tên tín hiệu bằng những meter/span/log thực tế đã được kiểm chứng trong ứng dụng.

## 4. Phân loại thay đổi telemetry

Không phải mọi thay đổi đều có cùng mức rủi ro. Phân loại trước khi quyết định rollout:

| Loại | Ví dụ | Hành động |
| --- | --- | --- |
| **Additive** | Thêm một attribute hoặc metric mới | Kiểm tra cardinality, storage và consumer |
| **Rename** | Đổi meter name, span name, log field hoặc tag key | Cập nhật query và consumer; cần kế hoạch chuyển tiếp |
| **Semantic** | Giữ tên nhưng đổi ý nghĩa, thời điểm ghi hoặc phạm vi đo | Cập nhật mô tả, SLO và alert |
| **Type/unit** | Counter thành timer, milliseconds thành seconds | Sửa query, threshold, unit và recording rules |
| **Cardinality** | Thêm tag có nhiều giá trị như order ID hoặc tenant ID | Đánh giá chi phí và giới hạn trước khi phát hành |
| **Removal** | Xóa metric, span attribute hoặc log field | Tìm toàn bộ consumer và thời hạn ngừng dùng |
| **Transport/configuration** | Đổi OTLP endpoint, protocol, headers hoặc exporter | Kiểm tra network, auth, TLS, pipeline và loss window |
| **Sampling** | Đổi sampler hoặc tỷ lệ lấy mẫu | Đánh giá trace coverage, cost và khả năng điều tra |
| **Lifecycle/state** | Đổi trạng thái event publication hoặc completion timing | Cập nhật dashboard/alert và runbook theo semantics mới |
| **Resource identity** | Đổi service.name, environment hoặc service version | Cập nhật filter, grouping, ownership và alert routing |

Một metric giữ nguyên tên nhưng đổi từ “event đã publish” thành “event đã hoàn tất” là thay đổi semantic lớn. Ngược lại, thêm một attribute ổn định có thể là additive nhưng vẫn làm tăng cardinality nếu giá trị không được giới hạn.

### Ma trận tương thích

| Tình huống | Tương thích với consumer cũ? | Cần migration? |
| --- | --- | --- |
| Thêm metric mới, giữ nguyên metric cũ | Thường có | Cập nhật dashboard khi muốn dùng tín hiệu mới |
| Thêm attribute tùy chọn | Thường có | Kiểm tra parser/query có strict schema không |
| Đổi tên metric/tag | Không đảm bảo | Có |
| Đổi unit hoặc loại instrument | Không | Có |
| Đổi ý nghĩa metric nhưng giữ tên | Không về mặt ngữ nghĩa | Có, cần tên/version hoặc migration rõ |
| Xóa span attribute đang được query | Không | Có |
| Đổi service identity | Có thể làm mất nhóm dữ liệu cũ | Có |
| Đổi endpoint/transport | Không nếu receiver chưa tương thích | Có |
| Giảm sampling | Backend nhận ít trace hơn | Cần đánh giá điều tra/SLO |

## 5. Quy trình thu thập bằng chứng trước khi nâng cấp

Đừng bắt đầu change record chỉ bằng cách đọc release notes. Hãy lưu baseline thực tế:

1. Ghi version Spring Boot, Spring Modulith, Micrometer, Micrometer Tracing, OpenTelemetry SDK/exporter và Collector.
2. Lưu dependency tree hoặc Gradle dependency insight để xác định version thực sự được resolve.
3. Export danh sách meter từ /actuator/metrics và scrape /actuator/prometheus.
4. Chụp hoặc export dashboard, alert rules và SLO queries đang hoạt động.
5. Thu một tập trace đại diện: request thành công, request lỗi, luồng qua nhiều module và listener bất đồng bộ.
6. Thu log mẫu có correlation ID/MDC fields và log JSON nếu có.
7. Lưu Collector configuration, endpoint, protocol, processors và exporters.
8. Ghi sampling probability, parent sampler, tail sampling policy và retention.
9. Ghi traffic baseline: request/s, spans/trace, event publication/s, listener duration, log volume.
10. Lưu bằng chứng vào release/upgrade artifact có version và timestamp.

### Snapshot baseline

Ví dụ metadata của snapshot:

~~~yaml
snapshot:
  captured_at: "2026-11-27T10:30:00+07:00"
  environment: staging
  application:
    service_name: shop-application
    service_version: 2.7.4
    git_revision: "<commit-sha>"
  dependencies:
    spring_boot: "<resolved-version>"
    spring_modulith: "<resolved-version>"
    micrometer: "<resolved-version>"
    micrometer_tracing: "<resolved-version>"
    opentelemetry_sdk: "<resolved-version>"
    opentelemetry_collector: "<image-tag>"
  sampling:
    head_probability: 0.25
    tail_sampling_enabled: false
  exporters:
    traces: "otlp-http"
    metrics: "prometheus"
    logs: "json-file"
  evidence:
    prometheus_scrape: "artifacts/baseline/prometheus.txt"
    trace_examples: "artifacts/baseline/traces/"
    log_examples: "artifacts/baseline/logs.jsonl"
    collector_config: "artifacts/baseline/otel-collector.yaml"
~~~

Các giá trị trong ví dụ chỉ minh họa cấu trúc. Không commit secrets, access tokens, customer data hoặc payload thật vào snapshot. Dùng placeholder cho commit, version và đường dẫn thực tế của release.

## 6. Đọc release notes và dependency diff

Đối chiếu thay đổi ở mọi lớp, không chỉ version Spring Boot:

- Spring Boot release notes và configuration property changes.
- Spring Modulith release notes, API changes và migration notes.
- Micrometer/Micrometer Tracing migration guides.
- OpenTelemetry SDK/exporter release notes và semantic convention status.
- Collector distribution/component changes.
- Prometheus client/registry changes.
- Logging backend changes như Logback/Log4j2.

Ghi mỗi phát hiện thành một dòng trong change record, kèm nguồn, version áp dụng và mức chắc chắn. Phân biệt rõ:

- **Confirmed:** release note hoặc migration guide nói rõ hành vi thay đổi.
- **Observed:** kiểm thử/runtime diff cho thấy dữ liệu thay đổi.
- **Potential:** có khả năng ảnh hưởng nhưng chưa được xác minh.
- **Not applicable:** đã kiểm tra và không dùng tính năng đó.

Không đánh dấu “không ảnh hưởng” chỉ vì build thành công. Một ứng dụng có thể khởi động bình thường trong khi Prometheus series đổi tên hoặc trace backend không còn nhận span attributes cần thiết.

## 7. Ví dụ thay đổi: Spring Modulith 2.1 lên 2.2

Spring Modulith 2.2 có hai thay đổi đáng chú ý đối với event publication lifecycle:

1. Mặc định, việc đánh dấu publication hoàn tất tham gia transaction của listener. Trạng thái completion và thay đổi nghiệp vụ của listener có thể commit hoặc rollback cùng nhau.
2. Publication FAILED và ABANDONED được phân biệt. ABANDONED biểu thị publication không còn được retry theo policy.

Đây là thay đổi semantics của Event Publication Registry và cách vận hành, không nên tự động mô tả là một metric name rename. Hãy kiểm tra code/dashboard/alert của dự án đang đọc status nào và giả định transaction nào.

### Ví dụ change record

| Hạng mục | Trước nâng cấp | Sau nâng cấp | Tác động cần document |
| --- | --- | --- | --- |
| Listener business transaction | Listener hoàn tất và registry update có thể không cùng transaction theo hành vi cũ | Completion mặc định tham gia transaction listener | Kiểm tra tính nguyên tử, failure/retry và thời điểm publication biến mất khỏi backlog |
| Failed publication | Không có trạng thái abandoned riêng | Có FAILED và ABANDONED | Dashboard/alert phải tách lỗi còn retry với publication bị từ bỏ |
| Alert backlog | Có thể chỉ lọc incomplete/failed | Cần xác định cách xử lý abandoned | Thêm alert riêng và runbook xử lý thủ công |
| Recovery | Resubmit failed theo API phù hợp phiên bản | Cần kiểm tra API/policy và status mới | Kiểm thử retry, idempotency và audit |

Ví dụ alert cần được cập nhật theo semantics:

~~~promql
shop_event_listener_abandoned{
  event_type="OrderCompleted"
} > 0
~~~

Series trên là metric tùy chỉnh do ứng dụng xây dựng từ trạng thái registry; không giả định Spring Modulith tự xuất metric có tên này.

### Câu hỏi cần trả lời khi ghi nhận thay đổi

- Listener có phụ thuộc vào completion marker nằm ngoài transaction không?
- Dashboard có gộp FAILED và ABANDONED không?
- Runbook có hướng dẫn resubmit publication abandoned không?
- Có consumer nào xem số publication incomplete là số event business duy nhất không?
- Completion mode đang là DELETE, UPDATE hay ARCHIVE?
- Có cần giữ lịch sử publication để đối chiếu trước/sau không?

## 8. Ví dụ thay đổi: Spring Boot 4.2 và OpenTelemetry conventions

Release notes Spring Boot 4.2.0-M2 mô tả một số thay đổi observability cần đưa vào change record:

- Có thể opt-in OpenTelemetry semantic conventions bằng property management.observations.conventions: open-telemetry.
- Khi dùng convention này, một số property tùy chỉnh meter name cũ như management.observations.http.server.requests.name không còn có hiệu lực.
- Có cấu hình OTLP chung dưới management.opentelemetry.otlp cho endpoint, headers và compression; property riêng từng signal được ưu tiên nếu có.
- MDC trace/span keys có thể đổi qua management.tracing.mdc.trace-id-key và management.tracing.mdc.span-id-key; correlation pattern mặc định theo key mới.

Đây là ví dụ theo release notes milestone được công bố. Khi nâng một bản stable cụ thể, đối chiếu release notes/configuration changelog của đúng bản đó trước khi áp dụng.

### Ví dụ property diff cần document

~~~yaml
# Cấu hình minh họa trước khi chuyển conventions.
management:
  observations:
    conventions: default
    http:
      server:
        requests:
          name: http.server.requests
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://otel-collector:4318/v1/traces
~~~

~~~yaml
# Cấu hình minh họa sau khi opt-in OpenTelemetry conventions
# và dùng chung OTLP HTTP base endpoint.
management:
  observations:
    conventions: open-telemetry
  opentelemetry:
    otlp:
      endpoint: http://otel-collector:4318
      headers:
        Authorization: "<secret-from-secret-store>"
      compression: gzip
~~~

Hai đoạn trên chỉ minh họa hình dạng property. Hãy xác minh endpoint, path, placeholder, transport và tên property theo đúng Spring Boot minor version. Không copy secret vào YAML được commit.

Khi đổi conventions, không chỉ sửa tên metric trong dashboard. Hãy đối chiếu cả metric name, instrument type, unit, label/tag keys, span name, kind, status, attribute keys, resource attributes, log correlation fields, MDC keys, alert thresholds, SLO queries và Collector processors có filter/route theo tên hoặc attributes cũ không.

## 9. Ví dụ thay đổi: Micrometer Prometheus registry

Migration guide Micrometer 1.17 mô tả hành vi mới khi hai meter name khác nhau nhưng ánh xạ về cùng một Prometheus name sau quy tắc suffix. Ví dụ counter test và test.total có thể đụng tên sau khi Prometheus thêm hậu tố _total. Trước 1.17, một meter có thể bị mất khỏi scrape mà không có lỗi rõ; từ 1.17, meter đăng ký sau có thể bị từ chối với log cảnh báo.

Đây là thay đổi quan trọng cho bước nâng cấp:

1. Quét meter names trước khi deploy.
2. Kiểm tra collision sau quy tắc normalize của registry.
3. Đọc log registration failure.
4. Xác nhận scrape không có duplicate series.
5. Thêm kiểm thử đăng ký meter cho instrumentation nội bộ.

Ví dụ xung đột:

~~~java
registry.counter("test").increment();
registry.counter("test.total").increment(42);
~~~

Không đặt tên meter theo cảm tính. Hãy kiểm tra Prometheus exposition thực tế và tránh đăng ký meter khác loại có thể sinh cùng metric family/time series.

## 10. Theo dõi metrics trước và sau nâng cấp

Với mỗi meter quan trọng, document:

| Trường | Nội dung |
| --- | --- |
| Meter name | Tên Micrometer và tên sau export |
| Instrument | Counter, Gauge, Timer, DistributionSummary |
| Unit | Seconds, bytes, items hoặc unit nghiệp vụ |
| Tags | Key, value domain, optional/required |
| Cardinality | Số series dự kiến và giới hạn |
| Semantics | Điều gì làm meter tăng/đổi giá trị |
| Reset/lifecycle | Counter reset theo process hay theo business window |
| Consumer | Dashboard, alert, SLO, recording rule |
| Change | Added, renamed, removed, semantic change |

### Bảng diff metrics

| Meter | Trước | Sau | Consumer | Migration |
| --- | --- | --- | --- | --- |
| HTTP request count | Tên/labels baseline | Tên/labels mới đã xác minh | Request dashboard | Sửa PromQL nếu đổi |
| HTTP duration | Unit/percentile baseline | Unit/aggregation mới | Latency SLO | Xác minh đơn vị |
| module.events.published | Publication counter | Đối chiếu exposition mới | Event dashboard | Không coi là completion metric |
| Listener completion | Custom counter | Custom counter/registry gauge | Consumer alert | Giữ semantic và label ổn định |
| Export failure | Collector/SDK metric | Collector/SDK metric mới | Telemetry pipeline alert | Kiểm tra tên component |

Đối với Spring Modulith, module.events.published là metric publication. Không đổi mô tả thành “listener đã xử lý” trừ khi có một metric riêng thực sự đo completion.

### Kiểm tra cardinality

Ước lượng số series:

\[
\text{series count} \approx \prod_{i=1}^{n} |\text{distinct values of tag}_i|
\]

Ví dụ metric có module (5 giá trị), event_type (12 giá trị), outcome (3 giá trị) có tối đa khoảng 180 tổ hợp trước khi xét các dimension khác. Thêm order_id với hàng triệu giá trị có thể làm cardinality tăng không kiểm soát.

Không thêm trace ID, span ID, publication UUID, customer ID hoặc order ID vào metric tags. Giữ định danh từng request/event trong traces/logs; dùng tags hữu hạn cho metrics.

## 11. Theo dõi traces và module spans trước/sau nâng cấp

Trace contract nên ghi span name và kind, parent/child relationship, attributes và data type, status/error recording, resource attributes, instrumentation scope, propagator, context carrier, sampling policy và exporter.

Với Spring Modulith, lấy một số luồng đại diện:

~~~text
HTTP POST /orders
  └─ order module invocation
       ├─ inventory module invocation
       └─ OrderCompleted publication
            └─ inventory listener
~~~

So sánh trace trước/sau:

| Hạng mục | Câu hỏi kiểm tra |
| --- | --- |
| Root span | Tên, kind và status còn như mong đợi không? |
| Module span | Tên và module attributes có đổi không? |
| Event listener span | Có tiếp tục trace gốc hoặc tạo trace mới theo thiết kế không? |
| Context | traceparent, baggage và MDC có được truyền qua async boundary không? |
| Sampling | Root/child decision có nhất quán không? |
| Export | Collector nhận đủ spans, đúng protocol và endpoint không? |
| Privacy | Attributes mới có đưa dữ liệu nhạy cảm vào trace không? |

Không coi việc trace ID khác nhau giữa hai lần chạy là lỗi; mỗi request mới có trace ID mới. Hãy so cấu trúc, tên span, attributes và parent relationship trên cùng kịch bản.

### Semantic conventions và schema

OpenTelemetry semantic conventions quy định tên span, metric, unit, attributes và ý nghĩa chung để nhiều instrumentation/backend hiểu nhất quán. Khi nâng instrumentation, kiểm tra maturity/stability của convention và schema URL nếu có.

Không mặc định mọi instrumentation đều bảo đảm telemetry shape ổn định. Instrumentation được gắn nhãn unstable có thể đổi span/metric names hoặc attributes giữa các version. Với stable instrumentation, kiểm tra cam kết stability và schema migration tương ứng.

## 12. Theo dõi logs và correlation fields

Với mỗi logging backend, ghi pattern console/file hoặc JSON schema, trace ID/span ID MDC keys, business correlation ID/request ID/event ID, field parser/index mapping, redaction, masking và retention.

Ví dụ log contract:

~~~json
{
  "timestamp": "2026-11-27T10:30:00+07:00",
  "level": "INFO",
  "service.name": "shop-application",
  "service.version": "2.8.0",
  "traceId": "trace-example",
  "spanId": "span-example",
  "module": "inventory",
  "message": "Reservation completed"
}
~~~

JSON chỉ minh họa schema; giá trị thực phải được lấy từ encoder và MDC của ứng dụng. Nếu MDC key thay đổi, kiểm tra cả correlation pattern và log parser. Nếu structured logging xuất fields riêng, không giả định logging.pattern.correlation tự sửa schema JSON.

Không đưa token, cookie, mật khẩu, thông tin thanh toán hoặc payload cá nhân vào change record. Chỉ lưu log mẫu đã redact.

## 13. OTLP exporter và Collector configuration diff

Ghi lại cấu hình theo từng signal:

| Signal | Transport | Endpoint | Headers/auth | Compression | Receiver/pipeline |
| --- | --- | --- | --- | --- | --- |
| Traces | OTLP/HTTP hoặc gRPC | Trace endpoint | Secret reference | gzip/none | OTLP receiver → processors → trace exporter |
| Metrics | OTLP hoặc Prometheus scrape | Metrics endpoint | Secret reference | gzip/none | Metrics receiver/pipeline |
| Logs | OTLP hoặc file/agent | Logs endpoint | Secret reference | gzip/none | Logs receiver/pipeline |

Khi endpoint, headers hoặc compression được cấu hình chung, ghi rõ precedence giữa common properties và signal-specific properties. Với HTTP, kiểm tra path /v1/traces, /v1/metrics và /v1/logs; không suy ra endpoint từ một signal cho mọi signal khác.

### Collector diff

Kiểm tra receiver protocol và port, TLS/authentication/network exposure, batch/memory limiter/retry/queue, tail sampling policies và trace-aware routing, attribute/resource processors, exporter destination/timeout, cùng Collector self-observability.

Đổi exporter endpoint có thể tạo một khoảng mất dữ liệu trong lúc rollout. Ghi rõ thời điểm chuyển, cách xác nhận receiver mới và liệu backend cũ còn cần giữ để tra cứu dữ liệu lịch sử hay không.

## 14. Dashboard, alert và SLO migration

Mỗi thay đổi telemetry phải truy ra consumer. Dùng bảng impact:

| Consumer | Query phụ thuộc | Thay đổi telemetry | Hành động |
| --- | --- | --- | --- |
| HTTP dashboard | Metric name, URI tag, unit | Convention/name/unit | Cập nhật query và panel unit |
| Module graph dashboard | /actuator/modulith schema | Module structure/endpoint | So JSON schema và permissions |
| Event dashboard | Publication counter, registry status | Lifecycle/metric semantics | Tách publish, complete, failed, abandoned |
| Trace search | Span name/attributes/service name | Span/attribute conventions | Cập nhật filter và saved queries |
| Log search | MDC/JSON fields | Key/parser change | Cập nhật parser/index mapping |
| Error alert | Error status/tag/query | Semantic change | Replay test và xác minh alert |
| SLO | Request count/latency/error rate | Meter name/unit/sample | Tính lại baseline nếu semantics đổi |

### Không chuyển ngưỡng SLO một cách mù quáng

Nếu metric đổi unit hoặc cách tính, threshold cũ có thể không còn ý nghĩa. Ví dụ duration đổi từ milliseconds sang seconds, histogram bucket boundaries đổi, request filter/URI normalization đổi, error status mapping đổi hoặc sampling giảm khiến trace count giảm nhưng request count không đổi.

Giữ nguyên SLO business nếu định nghĩa nghiệp vụ không đổi. Nếu measurement implementation thay đổi, document cách quy đổi, thời gian chạy song song và điểm bắt đầu baseline mới.

### Kế hoạch tương thích query

Khi rename metric hoặc attribute:

1. Nếu có thể, phát tín hiệu cũ và mới song song trong giai đoạn chuyển tiếp.
2. Tạo dashboard/alert query mới và so kết quả với query cũ.
3. Ghi ngày ngừng dùng tên cũ.
4. Cập nhật runbook và ownership.
5. Chỉ xóa query cũ sau khi hết thời hạn tương thích và không còn consumer.

Không duy trì hai metric tương đương mãi mãi nếu điều đó làm tăng chi phí hoặc gây nhầm lẫn. Đặt ngày kết thúc dual publishing.

## 15. Kiểm thử telemetry trong CI và staging

Kiểm thử observability phải xác minh cả cấu trúc lẫn ý nghĩa:

| Test | Điều cần xác minh |
| --- | --- |
| Meter contract test | Tên, type, unit và tags của meter quan trọng |
| Prometheus scrape test | Không có duplicate names/series, metric có xuất ra |
| Trace contract test | Span name, kind, parent, status và attributes |
| Context propagation test | Trace/MDC đi qua executor, event listener và async boundary |
| Log schema test | JSON fields, correlation keys và redaction |
| Collector config validation | Receiver, processors, exporters và pipeline hợp lệ |
| Dashboard query test | Query trả dữ liệu với telemetry mới |
| Alert rule test | Alert kích hoạt/clear theo kịch bản dự kiến |
| Load/cardinality test | Series count, spans/s, queue, memory và export failures |

### Kịch bản kiểm chứng tối thiểu

1. Gửi HTTP request thành công.
2. Gửi HTTP request gây lỗi có kiểm soát.
3. Gọi qua ít nhất hai application modules.
4. Publish event và xác minh listener completion.
5. Tạo listener failure và kiểm tra registry status.
6. Chạy async listener để kiểm tra context propagation.
7. Kiểm tra metric scrape và log correlation.
8. Kiểm tra trace trong backend.
9. Kiểm tra alert bằng dữ liệu/kịch bản có kiểm soát.
10. Tạo traffic đủ lớn để quan sát cardinality và Collector capacity.

Đừng chỉ kiểm tra ứng dụng khởi động. Một exporter có thể lỗi âm thầm sau khi request đã thành công; dashboard query cũng có thể sai mà không ảnh hưởng health endpoint.

## 16. Rollout, canary và rollback

Một rollout observability an toàn nên chia thành các bước:

~~~mermaid
flowchart TD
    A["Inventory và baseline cũ"] --> B["Đọc release notes, lập telemetry diff"]
    B --> C["CI: contract tests + query tests"]
    C --> D["Staging: chạy luồng đại diện và load test"]
    D --> E{"Telemetry mới đạt tiêu chí?"}
    E -->|"Không"| R["Dừng rollout, sửa hoặc rollback"]
    E -->|"Có"| F["Canary một instance / một nhóm traffic"]
    F --> G{"Metrics, traces, logs và alerts ổn định?"}
    G -->|"Không"| R
    G -->|"Có"| H["Mở rộng rollout"]
    H --> I["Xác nhận dashboards, SLO và runbook"]
    I --> J["Đóng migration, lưu evidence"]
~~~

### Canary checklist

- Service identity mới xuất hiện đúng.
- Scrape target healthy và metric series có dữ liệu.
- Không có duplicate meter registration hoặc scrape errors.
- Span tree có root/child/module spans như mong đợi.
- Trace/log correlation hoạt động.
- Event publication và listener completion được quan sát riêng.
- Collector queue, memory, rejected spans và exporter failures trong ngưỡng.
- Dashboard/alert không có gap ngoài dự kiến.
- Không tăng cardinality hoặc chi phí bất thường.

### Rollback plan

Rollback cần nêu:

1. Phiên bản application và dependency cuối cùng đã biết là tốt.
2. Collector config/image cũ và endpoint cũ.
3. Dashboard/alert rule version cũ.
4. Cách xử lý metric name/schema đã dual-publish.
5. Dữ liệu nào đã được ghi vào backend mới và có thể tiếp tục truy vấn không.
6. Event publication/registry state có tương thích khi hạ version không.
7. Ai có quyền quyết định rollback và điều kiện kích hoạt.

Rollback code không tự động rollback dữ liệu registry đã được ghi bởi version mới. Nếu event publication schema/lifecycle đã đổi, cần kiểm tra khả năng đọc dữ liệu cũ/mới và migration persistence trước khi hạ version.

## 17. Mẫu telemetry change record

Mẫu sau có thể dùng trong pull request hoặc release artifact. Mỗi release nên tạo một record riêng, liên kết tới release notes, dependency diff và evidence.

~~~yaml
telemetry_change:
  id: "OBS-2026-042"
  title: "Upgrade Spring Boot and Spring Modulith"
  status: "proposed" # proposed | verified | deployed | rolled_back
  owner: "platform-observability"
  reviewers:
    - "application-team"
    - "sre"

  release:
    application: "shop-application"
    from:
      spring_boot: "<old-version>"
      spring_modulith: "<old-version>"
      micrometer: "<old-version>"
      micrometer_tracing: "<old-version>"
      opentelemetry: "<old-version>"
    to:
      spring_boot: "<new-version>"
      spring_modulith: "<new-version>"
      micrometer: "<new-version>"
      micrometer_tracing: "<new-version>"
      opentelemetry: "<new-version>"
    git_revision: "<commit-sha>"

  changes:
    - signal: "metrics"
      producer: "spring-modulith-insight"
      name_before: "module.events.published"
      name_after: "module.events.published"
      semantic_change: false
      compatibility: "compatible"
      consumers:
        - "event-dashboard"
        - "event-publication-alert"
      action: "verify scrape and keep query"
      evidence: "<release-note-or-test-link>"

    - signal: "event-publication"
      producer: "spring-modulith-event-publication-registry"
      field_before: "FAILED"
      field_after: "FAILED, ABANDONED"
      semantic_change: true
      compatibility: "migration-required"
      consumers:
        - "event-backlog-dashboard"
        - "event-recovery-runbook"
      action: "add abandoned series and separate alert"
      evidence: "<release-note-or-test-link>"

  runtime:
    service_name: "shop-application"
    environment: "staging"
    sampling:
      strategy: "parent-based-ratio"
      probability: 0.25
    exporters:
      traces: "otlp-http"
      metrics: "prometheus"
      logs: "json"

  validation:
    dependency_diff: "pass"
    meter_contract: "pass"
    prometheus_scrape: "pass"
    trace_contract: "pass"
    log_schema: "pass"
    collector_pipeline: "pass"
    dashboard_queries: "pass"
    alert_rules: "pass"
    load_test: "pending"

  rollout:
    canary: "one-instance"
    start: "<timestamp>"
    success_criteria:
      - "no missing critical meter"
      - "no duplicate Prometheus series"
      - "module spans visible"
      - "event backlog remains within SLA"
    rollback_trigger:
      - "critical metric disappears"
      - "export failure exceeds threshold"
      - "alert query stops matching"
    rollback_revision: "<previous-known-good>"

  evidence:
    baseline: "<artifact-location>"
    after_upgrade: "<artifact-location>"
    dashboards: "<dashboard-links>"
    alerts: "<rule-links>"
    runbook: "<runbook-link>"
~~~

Đây là mẫu, không phải dữ liệu release thực. Thay mọi placeholder bằng version, query, evidence và quyết định đã được kiểm chứng. Không đánh dấu VERIFIED nếu mới chỉ đọc release notes mà chưa chạy test/runtime comparison.

## 18. Checklist review cho pull request nâng cấp

### Trước khi merge

- [ ] Đã ghi version cũ/mới của toàn bộ observability dependency.
- [ ] Đã đọc release notes/migration guides của từng thành phần liên quan.
- [ ] Đã lưu baseline metrics, traces, logs và Collector config.
- [ ] Đã phân loại thay đổi additive/semantic/breaking.
- [ ] Đã liệt kê dashboard, alert, SLO và runbook bị ảnh hưởng.
- [ ] Đã kiểm tra meter names, types, units, tags và cardinality.
- [ ] Đã kiểm tra span names, attributes, resource identity và context propagation.
- [ ] Đã kiểm tra MDC/log fields và structured logging schema.
- [ ] Đã kiểm tra OTLP endpoints, headers, TLS, compression và Collector pipeline.
- [ ] Đã viết hoặc cập nhật telemetry contract tests.
- [ ] Đã có rollout và rollback plan.

### Sau khi deploy

- [ ] Prometheus scrape thành công và không có duplicate series.
- [ ] Metrics quan trọng xuất hiện với đúng labels/units.
- [ ] Trace có module spans và parent relationship mong đợi.
- [ ] Log có correlation fields và parser đọc đúng.
- [ ] Event publication/consumer completion có trạng thái đúng.
- [ ] Dashboard và alert trả dữ liệu đúng.
- [ ] Collector không có rejected/failed telemetry bất thường.
- [ ] Cardinality, memory, ingestion và storage nằm trong ngân sách.
- [ ] Runbook và change record đã cập nhật evidence triển khai.
- [ ] Đã ghi thời điểm ngừng hỗ trợ telemetry schema cũ nếu có dual publishing.

## 19. Lỗi thường gặp khi document telemetry migration

| Sai sót | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ ghi version dependency | Không biết dữ liệu runtime đã đổi gì | Ghi schema diff và evidence trước/sau |
| Chỉ so tên metric | Bỏ sót unit, type, tags và semantic meaning | Ghi đầy đủ meter contract |
| Coi publication counter là completion | Alert báo khỏe khi listener chưa xử lý | Dùng registry và completion metrics |
| Không inventory dashboard/alert | Query cũ trả rỗng sau deploy | Truy vết từng consumer trước khi merge |
| Không kiểm tra cardinality | Chi phí storage tăng đột ngột | Tính series budget và giới hạn tag values |
| Dựa vào trace sample để đo request count | SLO/error rate sai lệch | Dùng metrics toàn traffic cho SLO |
| Chỉ test Actuator health | Exporter hoặc backend có thể vẫn hỏng | Test scrape, trace, log và Collector end-to-end |
| Không giữ snapshot cũ | Không thể so sánh hoặc rollback query | Lưu baseline có version và timestamp |
| Không ghi rõ convention stability | Instrumentation unstable đổi schema ngoài dự kiến | Ghi maturity, release và schema version |
| Rollback code nhưng quên registry data | Version cũ không đọc được publication mới | Kiểm tra persistence compatibility trước rollout |
| Không đặt ngày kết thúc dual publishing | Hai schema tồn tại vô thời hạn | Ghi deprecation date và owner |

## 20. Bài thực hành: lập change record cho một lần nâng cấp

Giả sử nhóm chuẩn bị nâng Spring Boot, Spring Modulith và Micrometer trong ứng dụng có các module order, inventory và billing.

1. Ghi lại BOM/dependency tree hiện tại và version mục tiêu.
2. Export Prometheus scrape, trace mẫu, log mẫu và Collector config.
3. Đọc release notes từng thành phần, đánh dấu các thay đổi observability.
4. Tạo bảng diff cho metrics, traces, logs, resource identity và event registry.
5. Tìm dashboard, alert, SLO và runbook đang dùng các tên/attributes cũ.
6. Chạy ứng dụng phiên bản mới trong staging và thu cùng loại dữ liệu baseline.
7. So sánh meter names, units, labels, span tree, MDC fields và exporter output.
8. Kiểm thử event publication thành công, thất bại, retry và abandoned nếu version hỗ trợ.
9. Chạy dashboard queries và Prometheus rule tests trên dữ liệu mới.
10. Đo cardinality, spans/second, Collector memory và export failures.
11. Hoàn tất rollout/canary criteria và ghi evidence vào change record.
12. Chỉ đóng migration sau khi owner SRE/application xác nhận và query cũ được xử lý theo deprecation plan.

Mẫu bảng tổng hợp:

| Tín hiệu | Baseline | Sau nâng cấp | Tương thích | Consumer cần sửa | Evidence |
| --- | --- | --- | --- | --- | --- |
| Metrics | … | … | … | … | … |
| Traces | … | … | … | … | … |
| Logs | … | … | … | … | … |
| Event registry | … | … | … | … | … |
| OTLP/Collector | … | … | … | … | … |
| Dashboards/alerts | … | … | … | … | … |

### Câu hỏi tự kiểm tra

1. Vì sao dependency tree không đủ để chứng minh telemetry tương thích?
2. Khác biệt giữa thay đổi tên metric và thay đổi ý nghĩa metric là gì?
3. Vì sao cần lưu baseline scrape/trace/log trước khi nâng cấp?
4. Khi Spring Boot opt-in OpenTelemetry semantic conventions, những consumer nào có thể bị ảnh hưởng?
5. Vì sao metric module.events.published không thể thay cho listener completion?
6. Khi Spring Modulith thêm trạng thái ABANDONED, dashboard và runbook cần thay đổi gì?
7. Vì sao Prometheus meter name collision cần được kiểm tra trước deploy?
8. Tại sao thêm một tag mới vẫn có thể là thay đổi rủi ro cao?
9. Khi đổi OTLP endpoint chung, cần kiểm tra precedence và signal path nào?
10. Điều kiện nào phải đạt trước khi xóa telemetry schema cũ?

## 21. Tổng kết

Document thay đổi telemetry là một phần của quy trình nâng cấp production. Một change record tốt lưu version và cấu hình cũ/mới, mô tả thay đổi metrics/traces/logs/event lifecycle, chỉ ra consumer bị ảnh hưởng, mức tương thích, bằng chứng kiểm thử, rollout và rollback.

Hãy so sánh dữ liệu runtime trước/sau thay vì dựa vào tên dependency hoặc giả định rằng nâng cấp patch/minor không đổi telemetry. Với Spring Modulith, đặc biệt theo dõi module spans, event publication lifecycle và metrics publication; với Spring Boot/Micrometer/OpenTelemetry, kiểm tra conventions, meter registration, MDC, resource attributes và OTLP pipeline. Chỉ đóng migration khi dashboard, alerts, SLO, Collector và runbook đã được xác minh trên dữ liệu của phiên bản mới.

## Tài liệu tham khảo

- [Spring Modulith 2.2 GA release notes](https://spring.io/blog/2026/11/19/spring-modulith-2-2-ga-2-1-3-and-2-0-10-released/).
- [Spring Modulith 2.2 — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Boot 4.2.0-M2 Release Notes — Observability improvements](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.2.0-M2-Release-Notes).
- [Micrometer 1.17 Migration Guide](https://github.com/micrometer-metrics/micrometer/wiki/1.17-Migration-Guide).
- [OpenTelemetry — Telemetry Stability](https://opentelemetry.io/docs/specs/otel/telemetry-stability/).
- [OpenTelemetry — General Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/general/).
- [OpenTelemetry — How to write semantic conventions](https://opentelemetry.io/docs/specs/semconv/how-to-write-conventions/).
- [Prometheus — Recording Rules](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/).
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/).
