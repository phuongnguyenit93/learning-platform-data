# Thiết kế log, metric, trace và sự kiện vận hành

## 1. Khả năng quan sát bắt đầu từ câu hỏi vận hành

Một hệ thống cloud có nhiều thành phần chạy đồng thời: load balancer, API gateway, ứng dụng, queue, database, cache, container, VM và dịch vụ của nhà cung cấp. Khi một request chậm hoặc thất bại, chỉ nhìn CPU hay một dòng log riêng lẻ thường không đủ để biết vấn đề bắt đầu ở đâu, ảnh hưởng tới ai và cần xử lý thế nào.

**Observability (khả năng quan sát)** là khả năng suy luận trạng thái bên trong của hệ thống từ những tín hiệu mà hệ thống phát ra. Một thiết kế tốt giúp đội vận hành trả lời được: điều gì xảy ra, xảy ra ở đâu, ảnh hưởng tới người dùng nào, bắt đầu từ lúc nào, có liên quan tới thay đổi nào và hành động khắc phục nào là phù hợp.

Trong module **CLOUD_ARCHITECTURE**, kiến trúc được thiết kế từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Log, metric, trace và event là một phần của kiến trúc vận hành, cần được thiết kế cùng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và các nguyên tắc Well-Architected.

Sau bài này, bạn có thể:

- Phân biệt log, metric, distributed trace và event.
- Thiết kế telemetry theo câu hỏi vận hành và hành trình nghiệp vụ.
- Chuẩn hóa log có cấu trúc, metric label và trace context.
- Liên kết log/metric/trace bằng timestamp, resource identity và correlation ID.
- Chọn SLI, SLO, alert và dashboard phù hợp.
- Thiết kế telemetry pipeline với OpenTelemetry Collector hoặc thành phần tương đương.
- Kiểm soát sampling, cardinality, retention, access và dữ liệu nhạy cảm.
- Đánh giá chi phí, độ tin cậy và hiệu quả vận hành của nền tảng observability.

## 2. Bốn loại tín hiệu và câu hỏi mỗi loại trả lời

| Tín hiệu | Mô tả | Câu hỏi tiêu biểu |
|---|---|---|
| **Log** | Bản ghi về một sự kiện/sự việc tại một thời điểm, thường có ngữ cảnh chi tiết | Request nào lỗi? Validation nào bị từ chối? Error code nào xuất hiện? |
| **Metric** | Phép đo số học được tổng hợp theo thời gian hoặc dimension | Tỷ lệ lỗi, latency p95, CPU, queue depth đang tăng hay giảm? |
| **Trace** | Chuỗi span thể hiện đường đi của một operation qua nhiều process/service | Request bị chậm ở gateway, Inventory, database hay provider? |
| **Event** | Thông báo một thay đổi hoặc sự kiện có ý nghĩa nghiệp vụ/vận hành | Booking được xác nhận lúc nào? Deployment nào vừa diễn ra? Tenant bị suspend khi nào? |

Các khái niệm có thể liên quan nhưng không nên dùng lẫn nhau. Log có thể ghi một event; trace có thể chứa event/span event; metric có thể đếm số log hoặc event. Mỗi loại được tối ưu cho một dạng truy vấn khác nhau.

### 2.1. Ví dụ BookingCloud

Một khách hàng tạo booking. Request đi qua API gateway, Booking service, Inventory service, Payment provider và database.

- Metric cho biết trong 5 phút vừa rồi p95 latency của API tăng từ 180 ms lên 2,4 giây.
- Trace cho thấy phần lớn thời gian nằm ở Inventory service, cụ thể là chờ database connection.
- Log của Inventory ghi connection pool đã đạt giới hạn và request timeout.
- Event cho biết 3 phút trước đã triển khai phiên bản mới làm tăng concurrency.

Khi kết hợp bốn tín hiệu, nhóm vận hành có thể hình thành giả thuyết nguyên nhân và xác định thay đổi cần rollback hoặc điều chỉnh.

~~~mermaid
flowchart TB
    USER["User creates booking"] --> GW["API gateway"]
    GW --> BOOK["Booking service"]
    BOOK --> INV["Inventory service"]
    INV --> DB[("Inventory DB")]
    BOOK --> PAY["Payment provider"]
    BOOK --> OUT["Telemetry pipeline"]
    GW --> OUT
    INV --> OUT
    DB --> OUT
    OUT --> LOG["Logs"]
    OUT --> METRIC["Metrics"]
    OUT --> TRACE["Traces"]
    OUT --> EVENT["Operational events"]
    LOG --> QUERY["Investigation / dashboards / alerts"]
    METRIC --> QUERY
    TRACE --> QUERY
    EVENT --> QUERY
~~~

## 3. Bắt đầu từ hành trình nghiệp vụ và failure mode

Không nên bắt đầu bằng câu hỏi “cần cài agent nào?”. Hãy bắt đầu từ hành trình người dùng và những điều có thể hỏng.

### 3.1. Lập bản đồ dịch vụ

Với BookingCloud, liệt kê:

- Thành phần nhận request và xác thực.
- Service sở hữu logic nghiệp vụ.
- Database, cache, queue và object storage.
- Dependency bên ngoài như payment/email provider.
- Batch job, scheduler và consumer bất đồng bộ.
- Control plane, deployment pipeline và thành phần quản trị.

Mỗi component nên có service name, owner, environment, version, region/zone và dependency map. Không có service identity thống nhất thì khó nhóm telemetry hoặc tìm người chịu trách nhiệm.

### 3.2. Xác định câu hỏi quan trọng

| Hành trình | Câu hỏi cần trả lời | Tín hiệu ưu tiên |
|---|---|---|
| Đăng nhập | Authentication failure tăng ở provider hay ứng dụng? | Metric + log + trace |
| Tạo booking | Tỷ lệ thành công và thời gian hoàn tất? | Metric + trace + event |
| Giữ slot | Timeout đến từ service hay database? | Trace + log + DB metric |
| Thanh toán | Kết quả unknown, decline hay provider outage? | Event + log audit + metric |
| Gửi email | Backlog và tuổi message lớn nhất? | Queue metric + event + worker log |
| Deploy | Version mới ảnh hưởng latency/error ra sao? | Deployment event + metric + trace |

### 3.3. Failure mode cần có telemetry

- Latency tăng nhưng error rate chưa tăng.
- Error tăng ở một region hoặc tenant tier.
- Database connection pool cạn hoặc query chậm.
- Queue backlog tăng và consumer lag lớn.
- Cache miss/stampede hoặc hot key.
- Retry amplification và circuit breaker mở.
- Một dependency bên ngoài trả 429/5xx.
- Certificate sắp hết hạn hoặc TLS handshake thất bại.
- Deployment/config change làm thay đổi behavior.
- Disk, memory, CPU hoặc quota gần giới hạn.

## 4. Log: ghi lại điều đã xảy ra

Log phù hợp với sự kiện cần chi tiết, đặc biệt khi điều tra lỗi, security incident và hành vi bất thường. Thiết kế log phải trả lời được ai làm gì, trên resource nào, ở đâu và kết quả ra sao.

### 4.1. Structured logging

Ưu tiên log có cấu trúc như JSON thay cho chuỗi tự do khó phân tích. Một record có thể gồm:

~~~json
{
  "timestamp": "2026-11-18T10:15:30.125Z",
  "severity": "ERROR",
  "service.name": "inventory-service",
  "service.version": "2.4.1",
  "deployment.environment": "production",
  "cloud.region": "ap-southeast-1",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "request_id": "req-7812",
  "tenant_tier": "standard",
  "event_name": "inventory.hold.failed",
  "error.type": "DatabaseTimeout",
  "error.code": "POOL_EXHAUSTED",
  "duration_ms": 1200
}
~~~

Giá trị trên chỉ minh họa. Không ghi access token, password, private key, payment credential, request body nhạy cảm hoặc PII nếu không thật sự cần. Thay vào đó dùng ID đã được kiểm soát, mask hoặc pseudonymize.

### 4.2. Các trường nên chuẩn hóa

| Trường | Mục đích |
|---|---|
| timestamp | Thời điểm phát sinh; thống nhất UTC và đồng bộ clock |
| severity | TRACE/DEBUG/INFO/WARN/ERROR theo convention |
| service.name | Nhóm log theo workload/service |
| service.version | So sánh behavior giữa release |
| environment/region/zone | Khoanh vùng môi trường và failure domain |
| trace_id/span_id | Liên kết với distributed trace |
| request_id/correlation_id | Theo dấu operation xuyên hệ thống |
| event_name/error.code | Phân tích máy đọc được |
| duration/status | Kết quả và thời gian xử lý |
| tenant scope an toàn | Phân tích ảnh hưởng theo tier/segment; tránh lộ định danh không cần thiết |

Không nhất thiết record nào cũng có mọi field; hãy thống nhất schema và quy tắc nullable.

### 4.3. Chọn severity

- **DEBUG:** chi tiết dùng trong phát triển/điều tra có kiểm soát; thường tắt hoặc sample ở production.
- **INFO:** mốc hoạt động bình thường có giá trị.
- **WARN:** tình huống bất thường có thể tự phục hồi hoặc chưa ảnh hưởng lớn.
- **ERROR:** operation thất bại cần điều tra hoặc xử lý.
- **FATAL/CRITICAL:** thành phần không thể tiếp tục hoạt động hoặc ảnh hưởng nghiêm trọng; tên gọi tùy convention.

Không log cùng một exception ở mọi tầng như ERROR; điều đó tạo hàng chục bản ghi cho một lỗi và làm khó xác định nguồn. Tầng sở hữu operation thường chịu trách nhiệm ghi lỗi cuối; tầng trung gian có thể bổ sung log debug/trace phù hợp.

### 4.4. Log sampling và tránh log storm

Trong lúc outage, mỗi request lỗi có thể tạo nhiều log. Nếu log pipeline là synchronous dependency, logging còn có thể làm request chậm hoặc mất log khi hệ thống quá tải.

Biện pháp:

- Log structured và có mức độ rõ ràng.
- Rate limit/sampling cho log lặp.
- Giữ đầy đủ security audit và log lỗi hiếm theo policy; không sample bừa các sự kiện bắt buộc.
- Dùng asynchronous/buffered exporter với queue có giới hạn.
- Có metric cho dropped logs, exporter failure và backlog.
- Tránh log nguyên payload hoặc stack trace lặp liên tục.

## 5. Metric: đo trạng thái và xu hướng

Metric phù hợp để theo dõi liên tục, tạo dashboard, alert và tính SLI. Nó thường là số liệu có timestamp, value và một tập dimension/label.

### 5.1. Counter, gauge, histogram và summary

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| Counter | Chỉ tăng trong vòng đời process; có thể reset khi restart | Tổng request, tổng error, số message xử lý |
| Gauge | Giá trị có thể tăng/giảm | Active connections, queue depth, memory usage |
| Histogram | Phân phối quan sát được theo buckets/count/sum | Request duration, payload size |
| Summary | Phân vị/summary tính tại client tùy hệ thống | Latency quantiles tại process |

Histogram thường hữu ích cho aggregation giữa nhiều instance; quantile của summary không phải lúc nào cũng gộp chính xác giữa replicas. Chọn loại phù hợp với backend metrics.

### 5.2. RED cho service

Với service xử lý request, có thể theo dõi:

- **Rate:** số request/giây.
- **Errors:** số hoặc tỷ lệ request thất bại.
- **Duration:** latency distribution, thường xem p50/p95/p99.

### 5.3. USE cho resource

Với resource/hạ tầng:

- **Utilization:** mức sử dụng CPU, memory, disk, network hoặc pool.
- **Saturation:** mức hàng đợi/chờ hoặc áp lực vượt capacity.
- **Errors:** lỗi ở resource, ví dụ disk error hoặc network drop.

RED và USE bổ sung nhau. RED cho biết service user-facing đang tốt hay xấu; USE giúp tìm tài nguyên có thể là nguyên nhân.

### 5.4. Metric cho BookingCloud

~~~text
http_server_requests_total{service,route,status_class}
http_server_request_duration_seconds_bucket{service,route}
booking_create_total{outcome}
inventory_hold_duration_seconds_bucket{region}
db_pool_active_connections{service}
db_pool_waiting_requests{service}
queue_messages_ready{queue}
queue_oldest_message_age_seconds{queue}
cache_requests_total{cache_name,result}
payment_provider_requests_total{provider,outcome}
~~~

Đây là tên metric minh họa. Không đưa booking_id, user_id, raw URL, email hoặc trace_id vào label metric.

### 5.5. Cardinality

Cardinality là số tổ hợp label khác nhau. Nếu mỗi request tạo một label với user ID hoặc URL chứa ID duy nhất, số time series có thể tăng khổng lồ, gây tốn RAM, storage và query chậm.

Nguyên tắc:

- Dùng route template như /bookings/{id}, không dùng URL raw.
- Chỉ giữ dimension có tập giá trị hữu hạn và hữu ích.
- Không thêm user ID, order ID, trace ID làm metric label.
- Dùng log/trace để điều tra chi tiết một entity.
- Theo dõi active series, label churn và metric ingestion volume.

## 6. Distributed tracing: theo dấu một request qua nhiều service

Trace ghi nhận đường đi của một operation qua các service/process. Một trace gồm nhiều **span**; mỗi span có start/end time, parent relation, attribute và event.

### 6.1. Trace và span

- Trace ID nhận diện toàn bộ operation.
- Span ID nhận diện một đoạn công việc.
- Parent span ID biểu diễn quan hệ gọi/bao chứa.
- Span attributes mô tả service, route, peer, status hoặc operation.
- Span event ghi mốc trong một span, ví dụ retry hoặc validation result.

~~~mermaid
flowchart LR
    T["Trace: Create booking"] --> G["Gateway span"]
    G --> B["Booking API span"]
    B --> I["Inventory client span"]
    I --> DB["Database span"]
    B --> P["Payment client span"]
    B --> Q["Publish event span"]
~~~

Trace cho biết thời gian ở đâu và quan hệ giữa các lời gọi. Nó không tự giải thích business correctness hoặc dữ liệu nào đã commit; cần kết hợp log và event.

### 6.2. Context propagation

Khi service A gọi B, trace context cần được truyền qua HTTP header, messaging metadata hoặc context mechanism tương ứng. W3C Trace Context phổ biến với các header như traceparent và tracestate.

Với message bất đồng bộ, producer inject context vào message; consumer extract context để tiếp tục trace hoặc tạo linked span phù hợp. Một workflow có thể kéo dài qua queue và nhiều process, vì vậy không dựa vào thread-local context.

Nếu context không được truyền, trace bị đứt thành nhiều trace riêng và khó phân tích latency end-to-end.

### 6.3. Parent-child và span links

Parent-child phù hợp lời gọi lồng nhau trong cùng một operation. Với consumer xử lý nhiều message hoặc batch kết hợp nhiều trace nguồn, span link có thể biểu diễn quan hệ mà không ép tất cả thành một cây parent-child đơn giản.

### 6.4. Trace instrumentation

Có thể dùng auto-instrumentation cho HTTP client/server, database driver, messaging và runtime. Bổ sung manual span quanh operation nghiệp vụ quan trọng:

- booking.create
- inventory.hold
- payment.authorize
- booking.confirm
- notification.dispatch

Không tạo span quá nhỏ cho mọi dòng code nếu không mang lại giá trị. Không để span name chứa ID duy nhất; dùng operation name/route template để tránh cardinality ở trace backend.

### 6.5. Sampling

Trace volume có thể rất lớn. Sampling quyết định trace nào được giữ:

- **Head sampling:** quyết định ở đầu trace, trước khi biết kết quả cuối. Chi phí thấp và dễ scale nhưng có thể bỏ lỡ trace lỗi hiếm.
- **Tail sampling:** quyết định sau khi thu thập trace (hoặc đủ một phần), có thể ưu tiên trace lỗi/slow nhưng cần buffer, state và tài nguyên collector/backend.
- **Parent-based sampling:** child thường tuân theo quyết định từ parent để duy trì một trace thống nhất.

Một chiến lược thường gặp là giữ tỷ lệ nhỏ trace bình thường nhưng giữ nhiều hơn trace lỗi, latency cao hoặc operation quan trọng. Cần cân nhắc privacy, quota, sampling bias và khả năng tail sampler xử lý trace phân tán qua nhiều collector.

## 7. Event vận hành và audit event

Event biểu diễn một thay đổi có ý nghĩa. Ví dụ:

- Deployment bắt đầu/thành công/thất bại.
- Feature flag được thay đổi.
- Tenant bị suspend/activate.
- Database failover hoàn tất.
- Certificate rotation hoặc KMS key policy đổi.
- Queue consumer vượt retry threshold.
- Booking chuyển từ PENDING sang CONFIRMED.

### 7.1. Phân biệt event nghiệp vụ với log

Log thường phục vụ chẩn đoán và có thể không được thiết kế để consumer khác phụ thuộc. Event nghiệp vụ có schema, owner, delivery semantics và compatibility policy; nó có thể kích hoạt workflow.

Audit event ghi lại hành động quan trọng với identity, action, resource, outcome và thời gian. Audit cần integrity, retention và quyền truy cập riêng; không sample tùy tiện nếu tổ chức yêu cầu lưu đầy đủ.

### 7.2. Event schema mẫu

~~~json
{
  "eventId": "evt-8124",
  "eventType": "booking.confirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-18T10:15:30Z",
  "source": "booking-service",
  "subject": "booking/bkg-8124",
  "correlationId": "corr-7812",
  "data": {
    "tenantTier": "standard",
    "bookingStatus": "confirmed"
  }
}
~~~

Payload trên chỉ minh họa. Chỉ đưa dữ liệu tối thiểu, tránh PII/secret không cần thiết. Event schema cần quy định version, key, timestamp, source, delivery/duplicate semantics và cách xử lý consumer.

### 7.3. Ordering, duplicate và replay

Event broker có thể giao message trùng hoặc không giữ global ordering. Consumer cần idempotency/event ID, partition key hoặc sequence theo yêu cầu nghiệp vụ. Replay phải được kiểm soát vì xử lý lại audit/event có thể tạo side effect.

Event operational như “deployment completed” thường có thể dùng để annotate dashboard hoặc liên kết release với metric; không nên biến mọi log thành event bus nếu không có consumer hoặc contract rõ.

## 8. Liên kết log, metric, trace và event

Giá trị lớn nhất xuất hiện khi bốn loại tín hiệu có thể dẫn qua lại.

### 8.1. Correlation fields

Thống nhất các trường phù hợp:

- trace_id/span_id.
- request_id/correlation_id.
- service.name/version/environment.
- deployment_id hoặc change_id.
- region/zone/cluster/namespace.
- operation/event name.
- tenant tier hoặc segment an toàn khi được phép.

Không sử dụng một correlation ID làm nhãn metric có cardinality cao. Nó hữu ích trong log/trace và link tới event.

### 8.2. Điều tra từ alert tới nguyên nhân

Một workflow tiêu biểu:

1. Metric alert báo p95 booking latency vượt SLO burn threshold.
2. Dashboard phân rã latency theo region, route và service version.
3. Trace exemplar hoặc sampled trace đưa tới một request chậm.
4. Trace cho thấy Inventory DB span có thời gian chờ cao.
5. Log theo trace ID cho biết connection pool gần exhausted.
6. Deployment event cho biết một version mới tăng worker concurrency.
7. Runbook chỉ dẫn rollback hoặc giới hạn concurrency, rồi theo dõi phục hồi.

~~~mermaid
flowchart TD
    ALERT["Metric alert"] --> DASH["Service dashboard"]
    DASH --> TRACE["Slow/error trace"]
    TRACE --> LOG["Related structured logs"]
    DASH --> EVENT["Deployment / config events"]
    LOG --> ROOT["Root-cause hypothesis"]
    EVENT --> ROOT
    ROOT --> ACTION["Runbook / mitigation"]
    ACTION --> VERIFY["Verify SLI and user impact"]
~~~

### 8.3. Time synchronization

Timestamp cần thống nhất định dạng và đồng bộ clock. Dùng UTC để lưu trữ/truy vấn xuyên region; dùng monotonic clock cho duration trong process. Clock drift có thể làm thứ tự log/trace sai hoặc span duration âm.

## 9. SLI, SLO và alerting

Observability không phải thu thập mọi thứ. Mục tiêu là biết trải nghiệm và độ tin cậy đang đạt cam kết hay không.

### 9.1. SLI

**Service Level Indicator (SLI)** là phép đo phản ánh một khía cạnh chất lượng dịch vụ. Ví dụ:

- Availability: tỷ lệ request hợp lệ được phục vụ thành công.
- Latency: tỷ lệ request hoàn tất dưới ngưỡng thời gian.
- Freshness: tuổi của dữ liệu hoặc độ trễ projection.
- Queue processing: tỷ lệ message được xử lý trong deadline.
- Durability: tỷ lệ operation đã được xác nhận lưu bền vững theo semantics.

Định nghĩa numerator/denominator rõ ràng. Không tính request bị client abort hoặc validation error vào availability mà không có lý do; không loại trừ lỗi hệ thống để làm chỉ số đẹp.

### 9.2. SLO và error budget

SLO là mục tiêu cho SLI trong một cửa sổ thời gian. Ví dụ minh họa:

- 99,9% request tạo booking hợp lệ thành công trong rolling 30 ngày.
- 95% GET catalog hoàn thành dưới 300 ms.
- 99% event booking được consumer xử lý trong 60 giây.

Error budget là phần lỗi/vi phạm được cho phép theo SLO. Khi burn rate quá nhanh, nhóm có thể giảm tốc độ release, tập trung reliability work hoặc thực hiện mitigation.

### 9.3. Alert theo symptom

Ưu tiên alert về user-visible symptom:

- Booking success rate suy giảm.
- p95/p99 latency vượt SLO.
- Payment outcome unknown tăng.
- Queue oldest message age vượt deadline.
- Error budget burn rate quá nhanh.

Alert nguyên nhân như CPU cao, disk gần đầy hoặc connection pool chạm ngưỡng cũng hữu ích, nhưng cần severity và routing phù hợp; tránh gửi page cho mọi metric bất thường không có tác động.

### 9.4. Multi-window/multi-burn-rate

Một cửa sổ ngắn phát hiện burn nhanh; cửa sổ dài xác nhận tác động kéo dài. Có thể kết hợp short-window và long-window để tránh alert do spike ngắn. Ngưỡng cần theo SLO và operational capacity, không sao chép một cấu hình chung cho mọi service.

### 9.5. Alert phải dẫn đến hành động

Mỗi alert quan trọng cần:

- Owner/on-call route.
- Severity và user impact.
- Dashboard liên quan.
- Runbook hoặc bước chẩn đoán.
- Điều kiện resolve/auto-close.
- Escalation khi không xử lý được.

Alert không có action hoặc owner thường trở thành noise.

## 10. Telemetry pipeline và OpenTelemetry

### 10.1. Kiến trúc pipeline

~~~mermaid
flowchart LR
    APP["Apps / SDKs / agents"] --> COL["Collector / agent"]
    INFRA["Cloud / network / DB telemetry"] --> COL
    COL --> PROC["Filter / enrich / batch / sample"]
    PROC --> LOGS["Log backend"]
    PROC --> METRICS["Metrics backend"]
    PROC --> TRACES["Trace backend"]
    PROC --> EVENTS["Event / audit store"]
    LOGS --> UI["Dashboards / query"]
    METRICS --> UI
    TRACES --> UI
    EVENTS --> UI
~~~

**OpenTelemetry (OTel)** cung cấp API, SDK, semantic conventions và protocol/collector để tạo, thu thập và export telemetry. Nó không bắt buộc bạn dùng một backend duy nhất; có thể xuất tới một hoặc nhiều hệ thống quan sát tùy kiến trúc.

### 10.2. Collector responsibilities

Collector/agent có thể:

- Receive telemetry qua OTLP hoặc receiver phù hợp.
- Parse, normalize và enrich resource attributes.
- Batch/compress để giảm overhead mạng.
- Filter/drop field nhạy cảm.
- Apply sampling hoặc tail sampling.
- Route theo signal/environment/tenant policy.
- Retry export có giới hạn và queue nội bộ.
- Expose health/queue/drop metrics của chính pipeline.

Collector là thành phần quan trọng. Nếu nó lỗi hoặc backlog tăng, telemetry có thể mất ngay lúc hệ thống đang gặp sự cố. Cần triển khai HA, buffer hữu hạn, resource limit và alert riêng.

### 10.3. Agent, gateway và collector tier

Các lựa chọn:

| Mô hình | Ưu điểm | Đánh đổi |
|---|---|---|
| Agent/sidecar per workload | Gần nguồn, enrich theo pod/host | Nhiều instance và resource overhead |
| Node/daemon collector | Một collector phục vụ nhiều workload trên node | Cần phân tách tenant/pod metadata đúng |
| Gateway collector tier | Tập trung routing, tail sampling, policy | Thêm hop và cần scale/HA |
| Direct export từ app | Đơn giản với workload nhỏ | App phụ thuộc backend, retry/buffer khó kiểm soát |

Có thể kết hợp agent/node collector với gateway tier. Quyết định dựa trên deployment model, network boundary, telemetry volume, tail sampling requirement và failure tolerance.

### 10.4. Backpressure cho telemetry

Không để exporter retry vô hạn hoặc queue vô hạn. Khi backend không khả dụng:

- Buffer trong giới hạn memory/disk.
- Bỏ telemetry theo priority policy nếu buffer đầy; giữ security audit theo yêu cầu riêng.
- Metric dropped spans/logs, queue depth, export errors và retry count.
- Tránh telemetry pipeline chiếm hết CPU/memory của business workload.
- Ưu tiên xử lý signal thiết yếu; giảm debug/high-volume attributes trước.

## 11. Bảo mật và quyền riêng tư trong telemetry

Telemetry thường chứa nhiều thông tin nhạy cảm hơn dự kiến: URL query, headers, SQL parameters, user attributes, IP, email, file path hoặc payload.

### 11.1. Data minimization và redaction

- Không ghi credential, access token, session cookie, private key hoặc payment secret.
- Mask email/phone/address hoặc thay bằng identifier giả danh khi cần correlation.
- Không capture request/response body mặc định nếu không có mục đích và kiểm soát.
- Kiểm soát SQL statement/parameter capture.
- Giảm precision của client IP hoặc bỏ field nếu không cần.
- Dùng allowlist attributes thay vì thu thập mọi context có sẵn.

### 11.2. Access control

Tách quyền đọc telemetry theo vai trò: application developer có thể xem log service; security team xem audit/security events; analyst chỉ xem aggregate đã mask; tenant customer chỉ xem dữ liệu của tenant mình nếu sản phẩm cung cấp observability portal.

Telemetry multi-tenant cần tenant-scoped query và policy; một dashboard shared không được lộ log/trace của tenant khác.

### 11.3. Retention và data residency

Chọn retention theo loại tín hiệu, nhu cầu incident investigation, compliance và chi phí. Log debug có thể giữ ngắn; audit có thể cần giữ lâu theo policy; metrics aggregate có thể giữ lâu hơn raw high-resolution data. Kiểm tra region lưu trữ và đường export sang backend khác có đáp ứng data residency không.

### 11.4. Audit telemetry platform

Ghi lại ai truy vấn/export telemetry, thay đổi retention, sampling, access policy và alert route. Bảo vệ log/audit khỏi bị sửa hoặc xóa bởi application role đang bị điều tra.

## 12. Sampling, retention và chi phí

Telemetry volume có thể tăng theo request rate, số span/request, log bytes/request và label cardinality. Chi phí không chỉ là storage mà còn ingestion, indexing, query, network egress, collector compute và license.

### 12.1. Sampling theo giá trị

- Giữ tỷ lệ trace nền cho traffic bình thường.
- Ưu tiên trace lỗi, slow trace hoặc operation critical nếu dùng tail sampling.
- Giữ security audit theo yêu cầu; không đánh đồng audit với debug log.
- Sample debug logs ở nguồn khi volume lớn.
- Không sample metric SLI theo cách làm sai denominator.

### 12.2. Retention tier

| Dữ liệu | Ví dụ retention strategy |
|---|---|
| High-cardinality debug logs | Ngắn, có sampling và access giới hạn |
| Application error/security logs | Theo nhu cầu vận hành và policy |
| Audit events | Theo yêu cầu pháp lý/hợp đồng và tamper protection |
| High-resolution metrics | Ngắn hơn; downsample cho thời gian dài |
| Aggregated metrics/SLO history | Dài hơn để phân tích xu hướng |
| Traces | Sampling/retention theo error, latency và purpose |

Đây là nguyên tắc phân tầng, không phải khuyến nghị số ngày áp dụng chung. Mỗi tổ chức cần thống nhất retention và deletion policy.

### 12.3. Giảm chi phí mà không làm mất khả năng điều tra

- Giảm cardinality và bỏ attributes không dùng.
- Chuẩn hóa route/service naming.
- Tách debug, operational và audit data.
- Dùng sampling có mục tiêu.
- Nén/batch telemetry.
- Downsample metrics cũ.
- Chọn retention theo giá trị điều tra.
- Theo dõi cost per million spans/log records và query volume.

## 13. Dashboard và runbook

Dashboard nên được tổ chức theo service và hành trình nghiệp vụ, không chỉ theo hạ tầng.

### 13.1. Các dashboard nên có

- **Service health:** request rate, error rate, p95/p99, saturation.
- **Dependency:** latency/error theo database, cache, queue, provider.
- **Business flow:** booking created/confirmed/failed, payment pending/unknown, cancellation.
- **Infrastructure:** CPU, memory, network, disk, connection pool, autoscaling.
- **Queue/workers:** backlog, oldest message age, retry, DLQ, processing latency.
- **Release:** metric theo service version, deployment event, canary vs baseline.
- **Security:** denied access, unusual egress, auth failures, policy change.
- **Telemetry pipeline:** dropped data, collector backlog, export failure, ingestion cost.

### 13.2. Runbook

Runbook nên ghi:

1. Alert nghĩa là gì và user impact có thể có.
2. Dashboard, trace query, log filter liên quan.
3. Những nguyên nhân có khả năng và cách phân biệt.
4. Hành động mitigation an toàn: rollback, scale, failover, rate limit hoặc disable feature.
5. Hành động không được thực hiện vì có thể làm mất dữ liệu/bypass security.
6. Điều kiện xác nhận đã phục hồi.
7. Khi nào escalation tới owner/provider/security team.

Runbook cần được kiểm tra qua incident drill; tài liệu không được cập nhật sẽ trở thành nguồn gây chậm xử lý.

## 14. Kiểm thử telemetry như một tính năng của hệ thống

Không chỉ kiểm tra ứng dụng chạy; cần xác minh telemetry có tới backend, có thể truy vấn và không chứa dữ liệu nhạy cảm.

### 14.1. Test instrumentation

- Request tạo booking có trace ID xuyên gateway và các service.
- Error log liên kết đúng trace/span.
- Metric label dùng route template, không dùng ID duy nhất.
- Deployment event có service/version/environment.
- Async consumer nhận propagated context hoặc link phù hợp.
- Collector export và backend ingest hoạt động.

### 14.2. Test khi telemetry backend lỗi

- Tắt log backend và quan sát app có bị block không.
- Làm trace exporter chậm để kiểm tra queue/buffer.
- Làm collector restart để kiểm tra retry và mất dữ liệu.
- Tạo high-volume traffic để kiểm tra memory/cardinality.
- Kiểm tra business request vẫn trong SLO khi observability backend degraded.
- Kiểm tra alert cho telemetry loss/drop.

### 14.3. Test privacy/security

Gửi request chứa secret/PII giả và xác minh redaction ở log, trace, event, exception và collector. Dùng role không được cấp quyền thử query telemetry tenant khác; kết quả phải bị từ chối.

## 15. Kiến trúc tham chiếu cho BookingCloud

~~~mermaid
flowchart TB
    subgraph WORKLOAD["Production workloads"]
      GW["API gateway"]
      BOOK["Booking service"]
      INV["Inventory service"]
      PAY["Payment service"]
      WORK["Workers"]
      DB[("Databases / cache / queue")]
    end
    GW --> BOOK
    BOOK --> INV
    BOOK --> PAY
    BOOK --> DB
    INV --> DB
    WORK --> DB
    GW --> COL["OTel node/sidecar collectors"]
    BOOK --> COL
    INV --> COL
    PAY --> COL
    WORK --> COL
    DB --> INFRA["Cloud integration / exporters"]
    INFRA --> COL
    COL --> GATE["Collector gateway tier"]
    GATE --> L["Log backend"]
    GATE --> M["Metrics backend"]
    GATE --> T["Trace backend"]
    GATE --> E["Event/audit store"]
    L --> OPS["Dashboards / alerting / on-call"]
    M --> OPS
    T --> OPS
    E --> OPS
~~~

Thiết kế cho phép chuẩn hóa và xử lý telemetry trước khi gửi tới backend riêng theo signal. Pipeline cần network path riêng, identity, TLS, buffer, quota và observability của chính nó.

## 16. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi review | Bằng chứng cần có |
|---|---|---|
| **Operational Excellence** | Telemetry có giúp on-call tìm nguyên nhân và hành động nhanh? | Dashboard, runbook, trace/log correlation, incident drill |
| **Security** | Log/trace có chứa secret/PII? Ai có thể truy vấn hoặc export? | Redaction test, RBAC, audit, retention và tenant isolation |
| **Reliability** | Collector/backend mất kết nối có làm ứng dụng bị ảnh hưởng? | Buffer bounded, drop metrics, HA, pipeline failure tests |
| **Performance Efficiency** | Instrumentation và exporter có thêm latency/CPU/memory quá mức? | Overhead benchmark, sampling, batch, cardinality control |
| **Cost Optimization** | Ingestion, indexing, storage, query và egress tăng theo dimension nào? | Cost per signal/tenant/service, retention, sampling report |
| **Sustainability** | Có thu thập telemetry dư thừa hoặc giữ raw data lâu hơn cần thiết? | Data inventory, downsampling, lifecycle, dropped-unused field review |

Observability tốt không phải thu thập tối đa. Đó là thu thập tín hiệu đủ để trả lời câu hỏi quan trọng, theo cách an toàn, đáng tin cậy và có chi phí có thể kiểm soát.

## 17. Bài thực hành: thiết kế observability cho luồng tạo booking

BookingCloud có request POST tạo booking qua API gateway, Booking service, Inventory service, Payment service và queue notification. Gần đây p95 latency tăng, một số request timeout nhưng dashboard chỉ có CPU và tổng số request.

Hãy thực hiện:

**Bài 1 — Service map:** vẽ luồng request đồng bộ và bất đồng bộ, liệt kê service, datastore, external dependency và owner.

**Bài 2 — Log schema:** đề xuất JSON log cho booking create success/failure có service/version, trace ID, request ID, operation name, error code và duration; loại bỏ secret/PII.

**Bài 3 — Metrics:** chọn RED cho từng service, USE cho database/queue/cache và metric nghiệp vụ booking success/pending/failed.

**Bài 4 — Trace:** mô tả span/parent-child từ gateway tới Inventory, Payment và database; truyền context qua notification queue.

**Bài 5 — Events:** chọn event cho deployment, payment outcome và booking state transition; xác định schema/version/owner.

**Bài 6 — SLI/SLO:** định nghĩa success rate, latency và queue processing freshness với numerator/denominator rõ ràng.

**Bài 7 — Alert/runbook:** tạo symptom-based alert cho booking success giảm và p95 tăng; dẫn link tới dashboard, trace, log và deployment event.

**Bài 8 — Privacy/cost:** chọn sampling, cardinality, retention, redaction và access policy.

**Bài 9 — Failure test:** tắt telemetry backend, tạo outage Inventory và kiểm tra ứng dụng không bị logging pipeline làm nghẽn.

### Khung kết quả tự kiểm tra

| Vấn đề hiện tại | Tín hiệu cần bổ sung | Hành động có thể thực hiện |
|---|---|---|
| Chỉ thấy CPU và request count | RED, USE, p95/p99 | Khoanh vùng service/resource |
| Không biết service nào chậm | Distributed trace | Tìm span có latency cao |
| Log không liên kết request | trace_id/request_id | Mở log từ trace |
| Không biết release gây lỗi | Deployment/config event + version metric | Rollback/canary analysis |
| Queue bị trễ | Oldest message age, consumer lag | Scale consumer hoặc điều tra poison message |
| Telemetry tốn kém | Cardinality/ingestion/retention metrics | Giảm label và sample phù hợp |
| Log chứa PII | Redaction và access audit | Mask, giới hạn quyền, xử lý retention |

Kết quả cần chứng minh người vận hành có thể từ alert đi tới trace/log liên quan và xác định bước xử lý, đồng thời telemetry không làm rò dữ liệu hoặc gây ảnh hưởng đáng kể tới workload.

## 18. Checklist trước khi đưa observability vào production

- [ ] Service map, owner và dependency được định nghĩa.
- [ ] Log có cấu trúc, timestamp chuẩn và severity nhất quán.
- [ ] Metric bao gồm RED cho service và USE cho resource quan trọng.
- [ ] Cardinality được kiểm soát; không có ID duy nhất trong metric labels.
- [ ] Trace context được truyền qua HTTP và message queue.
- [ ] Span thể hiện operation/dependency quan trọng; sampling có chủ đích.
- [ ] Event/audit có schema, owner, retention và delivery semantics.
- [ ] Log/metric/trace/event liên kết bằng trace ID, request/correlation ID, service và version.
- [ ] SLI/SLO có numerator/denominator, window và exclusion policy rõ.
- [ ] Alert có owner, severity, dashboard và runbook.
- [ ] Collector/exporter có buffer hữu hạn, retry giới hạn và drop metrics.
- [ ] Telemetry backend lỗi không làm business request bị block.
- [ ] Secret/PII được redacted; access control và tenant isolation đã test.
- [ ] Retention, region/data residency và deletion policy được phê duyệt.
- [ ] Có dashboard cho chính telemetry pipeline và ingestion cost.
- [ ] Đã test instrumentation, privacy, sampling, outage và overhead.

Log cho biết chi tiết sự việc; metric cho biết xu hướng và mức độ ảnh hưởng; trace chỉ ra đường đi và thời gian qua từng thành phần; event ghi nhận các thay đổi có ý nghĩa. Khi được chuẩn hóa, liên kết và vận hành cùng SLI/SLO, bốn tín hiệu tạo thành nền tảng giúp đội ngũ hiểu trạng thái hệ thống, phản ứng nhanh và cải tiến kiến trúc cloud dựa trên bằng chứng.
