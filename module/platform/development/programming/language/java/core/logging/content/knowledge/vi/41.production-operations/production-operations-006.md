# Truy tìm sự cố trong Java Logging khi vận hành production

## 1. Truy tìm sự cố là gì?

Trong môi trường production, **truy tìm sự cố (incident investigation / troubleshooting)** là quá trình thu thập, liên kết và kiểm chứng bằng chứng để trả lời **hệ thống bị ảnh hưởng ở đâu, từ khi nào, vì sao, phạm vi tác động và cách phục hồi an toàn**. Java logging đóng vai trò cung cấp những dấu vết chi tiết về hành vi của ứng dụng; kết hợp logs với metrics, distributed tracing, trạng thái hạ tầng và dữ liệu nghiệp vụ mới giúp hình thành chẩn đoán đáng tin.

Một sự cố ví dụ:

~~~text
10:01  Người dùng báo thanh toán trả lỗi 503
10:02  Metrics ghi nhận tỷ lệ lỗi tăng ở payment-api
10:03  Logs cho thấy timeout khi gọi inventory-service
10:04  Traces chỉ ra thời gian chờ connection pool tăng
10:05  Pool metrics và DB dashboard xác nhận nghẽn kết nối
10:06  Kích hoạt phương án giảm tải theo runbook
~~~

Timeline này **chỉ minh họa**, không phải dữ liệu sự cố thật. Điểm quan trọng là dòng log timeout chỉ là **dấu hiệu**. Nếu nguyên nhân thực sự là pool cạn kết nối hoặc dependency quá tải, chỉ tăng HTTP timeout có thể che triệu chứng chứ không giải quyết nguyên nhân.

Cần phân biệt:

- **Symptom:** người dùng gặp 5xx hoặc request chậm.
- **Signal:** error rate tăng, latency p99 tăng, log xuất hiện TIMEOUT.
- **Evidence:** log event, trace span, metric, cấu hình, triển khai và commit trạng thái nghiệp vụ đã được kiểm tra.
- **Hypothesis:** pool cạn vì rò connection.
- **Root cause:** cơ chế gây sự cố sau khi đã đối chiếu bằng chứng và loại trừ giả thuyết khác.
- **Mitigation:** giảm tải, rollback hoặc chuyển tuyến để khôi phục dịch vụ.
- **Permanent fix:** sửa code/cấu hình và thêm kiểm soát để tránh tái diễn.

**Không đồng nhất “không còn ERROR log” với “đã hết sự cố”.** Logging có thể bị lọc level, sampling, collector outage hoặc gián đoạn chính pipeline thu thập.

## 2. Những câu hỏi đầu tiên khi nhận cảnh báo

Trước khi đào sâu stack trace, xác lập bối cảnh:

| Câu hỏi | Dữ liệu cần xác nhận |
| --- | --- |
| Ai bị ảnh hưởng? | Người dùng, tenant, region, API, message consumer hoặc job |
| Từ khi nào? | Thời điểm bắt đầu và khoảng thời gian theo UTC/offset |
| Tác động? | Availability, latency, throughput, backlog, dữ liệu sai hoặc thất thoát |
| Độ nghiêm trọng? | SLO bị ảnh hưởng, rủi ro bảo mật/dữ liệu, chức năng trọng yếu |
| Có thay đổi gần đây? | Deploy, config, secret/certificate rotation, schema, feature flag |
| Có phụ thuộc bên ngoài? | Database, cache, broker, HTTP gateway, DNS hoặc cloud service |
| Có phương án giảm thiểu? | Rollback, traffic shifting, rate limit, circuit breaker, pause job |
| Cần bảo toàn bằng chứng gì? | Log query, traces, metric snapshots, version, timeline và correlation IDs |

Trong một incident có tác động lớn, việc **phục hồi dịch vụ theo runbook** có thể được ưu tiên trước phân tích toàn bộ root cause. Tuy nhiên mỗi thay đổi phục hồi phải được ghi lại để tránh làm mất dữ kiện và để biết thay đổi nào thực sự có hiệu quả.

**Đặt cửa sổ thời gian rõ ràng.** Dữ liệu trước thời điểm bắt đầu, lúc lỗi và sau khi can thiệp rất quan trọng; chỉ tìm từ khóa "ERROR" ở phút cuối có thể bỏ qua event khởi phát hoặc sự thay đổi cấu hình trước đó.

## 3. Quy trình điều tra có kiểm soát

Một vòng điều tra có thể theo các bước:

1. **Xác nhận tác động:** dùng SLI/SLO, synthetic probe hoặc trạng thái nghiệp vụ, không chỉ đếm log.
2. **Khoanh vùng:** region, service, endpoint, version, tenant, instance, consumer group.
3. **Thu evidence tối thiểu:** timestamp, requestId/traceId, errorCode, metric, deploy event.
4. **Tái dựng timeline:** nối các event theo hệ thống nguồn và thời gian phù hợp.
5. **Xây giả thuyết:** ghi cụ thể điều gì có thể giải thích triệu chứng.
6. **Kiểm tra giả thuyết:** tìm tín hiệu củng cố lẫn phản chứng.
7. **Giảm tác động:** rollback/giảm tải/chuyển tuyến theo quyền và runbook.
8. **Đối soát phục hồi:** latency, error rate, business outcomes và backlog thực sự cải thiện chưa.
9. **Lưu bằng chứng và quyết định:** cấu hình/phiên bản/correlation liên quan và lý do can thiệp.
10. **Theo dõi sau incident:** sửa lâu dài, regression tests, dashboards và alerting.

**Mỗi mệnh đề quan trọng nên có nguồn bằng chứng và giới hạn của nguồn.** Ví dụ “thấy TIMEOUT ở client” không chứng minh dependency không nhận request; có thể server xử lý xong nhưng response bị chậm hoặc mất trên mạng.

Trong báo cáo, phân biệt **observed**, **inferred**, **unknown** và **confirmed**. Cách này giúp đội khác không biến giả thuyết ban đầu thành kết luận khi sự cố còn đang phát triển.

## 4. Các nguồn tín hiệu và độ tin cậy tương đối

| Nguồn | Hữu ích cho | Giới hạn |
| --- | --- | --- |
| **Application logs** | Error codes, lifecycle events, exceptions, request context | Có thể thiếu event do level/sampling/drop |
| **Structured audit logs** | Hành động có ý nghĩa bảo mật/nghiệp vụ | Không thay thế toàn bộ debug traces |
| **Metrics** | Error rate, latency p95/p99, throughput, saturation | Thường thiếu thông tin theo từng request |
| **Distributed traces** | Timeline giữa services, duration từng span | Có sampling, missing propagation |
| **JVM diagnostics** | Heap, GC pauses, thread states, safepoint | Cần chụp đúng thời điểm, quyền truy cập |
| **Database/broker telemetry** | Slow queries, pool pressure, queue lag, retries | Chưa chắc cho thấy nguyên nhân từ Java code |
| **Infrastructure events** | OOMKill, restarts, deployment, node pressure | Không tự chứng minh bug ứng dụng |
| **Business database/outbox** | Xác minh side effects và trạng thái cuối | Có thể thiếu timeline kỹ thuật |
| **Third-party status** | Outage bên ngoài và thay đổi upstream | Mối liên hệ nhân quả vẫn cần kiểm chứng |

**Logs mô tả những điều đã được ghi; metrics cho thấy quy mô; traces cho thấy quan hệ thời gian.** Một trace có span timeout nhưng business database vẫn commit thành công là tình huống hoàn toàn có thể xảy ra khi response hoặc ACK đến muộn.

Không chạy lệnh thay cấu hình, dọn log hoặc khởi động lại service chỉ để “thử cho nhanh” trước khi đánh giá tác động. Trong production, cần giữ bằng chứng và tuân theo quyền vận hành.

## 5. Thiết kế log để truy tìm hiệu quả

Một event Java dễ điều tra thường có:

| Field | Mục đích |
| --- | --- |
| timestamp | Thời điểm phát event với timezone rõ ràng |
| level | Mức độ của event; không thay thế errorCode |
| service / environment / version | Khoanh vùng bản triển khai |
| instanceId / host / pod / region | Xác định nơi phát event |
| eventCode | Tên sự kiện ổn định, phù hợp aggregation |
| requestId / correlationId | Theo dõi một request/workflow |
| traceId / spanId | Ghép log với distributed trace |
| userRef / tenantRef đã phê duyệt | Khoanh vùng phạm vi; tránh raw PII |
| operation / routeTemplate | Chức năng xảy ra lỗi |
| outcome / reasonCode | Trạng thái và nguyên nhân theo mã chuẩn |
| errorCode / exceptionType | Phân nhóm lỗi, alert và dashboard |
| durationMs / attemptNo | Thời gian và lần thử |
| dependencyName / statusCode | Phụ thuộc và response nếu có |
| schemaVersion | Cho phép thay đổi hợp đồng serialization có kiểm soát |

Ví dụ một structured event:

~~~json
{
  "timestamp": "2026-11-10T03:02:41Z",
  "level": "WARN",
  "service": "payment-api",
  "environment": "production",
  "version": "2.8.1",
  "instanceId": "payment-api-3",
  "eventCode": "DEPENDENCY_TIMEOUT",
  "requestId": "req-42",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "operation": "authorize_payment",
  "dependencyName": "inventory-service",
  "attemptNo": 1,
  "durationMs": 1200,
  "errorCode": "INVENTORY_TIMEOUT"
}
~~~

Đây là **ví dụ schema** chứ không phải output mặc định của Logback/JUL. Các tên field phải được chuẩn hóa theo tổ chức và instrumentation thật. Thông tin version/instance giúp so sánh lỗi chỉ xuất hiện sau một deployment hoặc trên một nhóm node.

Không ghi nguyên request body/token/Authorization header chỉ vì đang điều tra production. **Bằng chứng cần đủ nhưng không được làm lộ dữ liệu nhạy cảm.**

## 6. Correlation ID, request ID và trace ID

Khi một request đi qua API gateway, service, database và message broker, có thể có hàng chục dòng log trên nhiều machines. Các ID phải có ý nghĩa riêng:

- **requestId:** nhận diện request ở một boundary; thường dùng để tra cứu nhanh.
- **correlationId/workflowId:** liên kết một workflow có nhiều requests/messages.
- **traceId:** gắn các spans thuộc một distributed trace qua propagation.
- **spanId:** định danh một operation/span trong trace, không thay traceId.
- **messageId/eventId:** giúp tìm một logical event khi có retry/redelivery.
- **attemptNo:** phân biệt nhiều lần thử của cùng thao tác.
- **jobId:** gom events thuộc background job hoặc batch.

Một trace có thể chứa nhiều HTTP calls hoặc messages; một logical message có thể được giao lại trong nhiều attempts. **Không lấy traceId làm khóa dedup nghiệp vụ**. Không dùng email/phone làm requestId mặc định.

Các ID lấy từ HTTP headers hoặc message envelopes **không tự đáng tin**. Validate grammar, độ dài và encoding; nếu client gửi ID lỗi có CR/LF, cần tạo ID mới hoặc áp policy an toàn để tránh log forging.

Trong hệ thống dùng SLF4J/Logback, MDC thường chứa requestId/traceId. Tuy nhiên **MDC chỉ là context trên thread/adapter**, không tự truyền qua network. Với executor, CompletableFuture, servlet async, Reactor hoặc message consumer, cần capture/activate/restore đúng scope.

## 7. Tái dựng timeline khi đồng hồ và ingestion trễ

Một truy vấn log có thể sắp theo timestamp nhưng thứ tự hiển thị **không luôn bằng thứ tự xảy ra**. Những nguyên nhân:

- Clock skew giữa host/VM/container và giữa các region.
- Buffered/async appenders và network queue khiến log tới backend muộn.
- Collector gắn ingestion timestamp khác với event timestamp.
- Retries/redelivery xảy ra ngoài thứ tự request ban đầu.
- Spans có overlap; một operation bất đồng bộ không có quan hệ thứ tự toàn cục.
- Application timestamp trước DB commit dù commit hoàn tất muộn hơn.

Một event nên giữ **eventTime** và **observed/ingestedTime** riêng khi cần. Tìm dấu vết theo khoảng thời gian rộng hơn một chút so với triệu chứng, dùng correlation và thứ tự causal/sequence khi có; không chỉ tin sort timestamp.

Ví dụ:

~~~text
eventTime=03:02:00.000 service=api       REQUEST_STARTED req-42
eventTime=03:02:00.020 service=api       CALL_INVENTORY req-42
eventTime=03:02:01.220 service=api       INVENTORY_TIMEOUT req-42
eventTime=03:02:01.250 service=api       FALLBACK_USED req-42
eventTime=03:02:01.310 service=api       REQUEST_COMPLETED req-42
ingestedTime=03:02:05.xxx collector=central
~~~

Đây là timeline giả lập. **Một timeout xuất hiện trước REQUEST_COMPLETED có thể là lỗi tạm thời đã được phục hồi**, không nhất thiết là request cuối cùng thất bại.

Khi cần thứ tự chắc chắn cho một workflow, dùng sequence/eventId/causationId hoặc transaction state được cam kết. Timestamp một mình không phải bằng chứng exactly-once hoặc business completion.

## 8. Từ triệu chứng đến truy vấn ban đầu

Mỗi loại triệu chứng gợi ý hướng tìm:

| Triệu chứng | Log fields / metric gợi ý | Chưa được phép kết luận |
| --- | --- | --- |
| Tỷ lệ HTTP 5xx tăng | routeTemplate, statusCode, exceptionType, version | Mọi 5xx đều do JVM bug |
| Latency p99 tăng | durationMs, dependencyName, pool wait, GC pause | Chắc chắn CPU thiếu |
| Java process restart | startup events, shutdown reason, pod events | Cứ restart là OOM |
| OOM/heap pressure | OutOfMemoryError, heap usage, GC, memory limit | Mọi memory tăng là leak |
| Connection timeout | dependency, timeout class, DNS, retries | Dependency không hề xử lý request |
| Database lỗi | SQLState, pool wait, slow query fingerprint | Cứ SQLException là DB outage |
| Queue backlog | consumer group, lag, DLQ, attempts | Broker đã mất message |
| Dữ liệu nghiệp vụ không nhất quán | eventId, transaction outcome, outbox/inbox | ACK đồng nghĩa commit |
| Log bị mất | logger level, agent queue, collector drop | Application không phát event |
| Lỗi chỉ ở một version | deployment markers, version, flags | Chắc chắn code version mới gây lỗi |

Trước khi dùng search rộng toàn bộ production, hãy xác định **service + environment + time window + một correlation key**. Cách này nhanh hơn và giảm nguy cơ đọc quá nhiều thông tin nhạy cảm.

**Không tìm riêng một từ ERROR rồi coi đó là toàn bộ sự cố.** WARN có thể chứa chỉ báo ban đầu, còn INFO chứa event xác nhận khôi phục hoặc event deploy.

## 9. Xây giả thuyết và tìm phản chứng

Một giả thuyết có giá trị phải đưa ra **dấu hiệu kiểm tra được**, không chỉ mô tả chung “hệ thống quá tải”.

Ví dụ giả thuyết: **JDBC connection pool bị cạn khiến API trả timeout**.

Dự đoán có thể kiểm chứng:

- Trong cùng thời gian, pool active tiến gần max và pending requests/wait time tăng.
- Log có errorCode hoặc exceptionType tương ứng với không lấy được connection.
- DB có thể khỏe hoặc không; nếu DB chậm, thời gian giữ connection tăng.
- Chỉ các endpoints dùng DB bị ảnh hưởng nhiều.
- Sau giảm số request/khôi phục pool hoặc sửa transaction giữ connection lâu, latency/error cải thiện.

Phản chứng:

- Pool vẫn còn nhiều connection rảnh khi timeout.
- Timeout xuất phát từ DNS/HTTP dependency khác, không có bước JDBC.
- Triệu chứng bắt đầu trước thay đổi cấu hình pool dự kiến liên quan.

Đừng chỉ chọn các log củng cố kết luận đầu tiên. Ghi **giả thuyết, bằng chứng ủng hộ, bằng chứng bác bỏ và độ chắc chắn** trong incident notes. Nếu có thể, so sánh cohort lỗi với cohort thành công để xem khác biệt thật là gì.

## 10. Phân tích exception trong Java

Stack trace có nhiều tầng:

~~~text
java.lang.IllegalStateException: order request failed
    at example.OrderService.process(OrderService.java:52)
Caused by: java.net.SocketTimeoutException: Read timed out
    at example.InventoryClient.fetch(InventoryClient.java:91)
~~~

Các yếu tố cần phân biệt:

- **Exception type:** biểu diễn loại lỗi gần nhất, thường có ích khi nhóm lỗi.
- **Cause chain:** ngoại lệ được wrap bởi tầng cao; root cause có thể nằm sâu.
- **Suppressed exceptions:** xuất hiện với try-with-resources và một số cleanup.
- **Frame đầu tiên thuộc ứng dụng:** giúp chỉ ra nơi phát hoặc wrap, không nhất thiết là bug gốc.
- **Thread name, requestId, dependency:** giúp liên kết lỗi với hoạt động thực.
- **Retry context:** cùng một exception có thể xuất hiện nhiều lần cho một request.
- **Terminal outcome:** sau lỗi có thể đã fallback thành công.

**Đọc root cause không có nghĩa chỉ lấy dòng cuối cùng.** Thông điệp cuối có thể chỉ là kết quả network timeout; cần metrics/traces để biết vì sao dependency chậm, DNS lỗi hay pool đã bão hòa.

Đừng cố log cả request/response raw vào Throwable message để dễ debug; exception text có thể chứa token, signed URL, SQL parameters và dữ liệu cá nhân. Dùng errorCode, exception class, dependency name và correlation ID; lưu dữ liệu nhạy cảm theo quy trình có kiểm soát khi thật sự cần.

### SLF4J parameterized logging không tự loại bí mật

Ví dụ tích hợp:

~~~java
logger.error("event={} requestId={} errorCode={}",
        "inventory_failed", validatedRequestId, "DEPENDENCY_TIMEOUT",
        exception);
~~~

Dòng này cần SLF4J và một backend. Khi exception được truyền đúng dưới dạng Throwable ở cuối, provider có thể xuất stack trace; chính Throwable cũng có thể chứa dữ liệu nhạy cảm. Placeholder **không phải redaction**.

Không gọi logger.error cho mỗi retry rồi coi tổng số ERROR chính là tổng số request thất bại. Phải tách **attempt failure** và **logical operation failure**.

## 11. JVM: GC pauses, heap và OutOfMemoryError

Những triệu chứng liên quan runtime:

- Latency tăng đột ngột đồng thời với các GC pauses kéo dài.
- Heap tiến gần giới hạn, GC chạy dày và throughput giảm.
- OutOfMemoryError có loại khác nhau: Java heap space, Metaspace, direct buffer memory hoặc thread creation failure có cơ chế và dữ kiện khác nhau.
- Container bị **OOMKilled bởi giới hạn hệ điều hành/cgroup** có thể không để lại OutOfMemoryError trong Java logs.
- Liveness/readiness probes timeout có thể khiến orchestration restart, khiến dấu vết ở JVM bị mất sau khi container cũ biến mất.

Nguồn kiểm tra:

| Nguồn | Vai trò |
| --- | --- |
| GC logs hoặc JFR | Pause, allocation pressure, collector behavior |
| Heap usage metrics | Old gen, heap committed/used theo thời gian |
| Container memory RSS/limits | Phân biệt heap với memory ngoài heap và OOMKill |
| JVM flags/heap limits | Xác định cấu hình runtime thật |
| Thread counts, native memory | Khi nghi rò thread/native allocation |
| Deploy/config timeline | Biết lỗi chỉ xảy ra trên version/memory limit mới |

Trong môi trường được phép, **jcmd** có thể truy vấn tiến trình Java để lấy thread hoặc heap information. Ví dụ ý tưởng vận hành:

~~~text
jcmd <java-pid> Thread.print
jcmd <java-pid> GC.heap_info
~~~

Các lệnh trên là **mẫu thao tác**, cần thay PID thật theo quyền và hướng dẫn phiên bản JVM. Không chạy heap dump bừa trong production: dump có thể chứa secrets/PII, tốn dung lượng lớn và làm ảnh hưởng dịch vụ; chỉ thực hiện theo incident procedure.

**GC trùng thời điểm lỗi không tự chứng minh GC là root cause.** Phải đối chiếu pause duration, request latency và những phụ thuộc bị ảnh hưởng.

## 12. JVM: deadlock, thread pool và blocking

Khi request chậm mà CPU không cao, có thể nghi thread đang chờ khóa, I/O hoặc pool.

Các dấu hiệu:

- Nhiều threads ở trạng thái WAITING/BLOCKED trên cùng resource.
- Executor queue length tăng, active threads chạm max.
- CompletableFuture hoặc reactive code gọi blocking API trên scheduler không phù hợp.
- Số threads tăng liên tục vì executor không shutdown hoặc có leak.
- Deadlock detection hoặc thread dump cho thấy lock cycle.
- HTTP client/DB connection pool chờ lâu; ứng dụng không nhất thiết dùng CPU cao.

Kiểm tra bằng JVM thread dump/JFR và metrics của executor, đồng thời liên kết log các stage: REQUEST_RECEIVED → HANDLER_STARTED → CALL_DEPENDENCY → TIMEOUT. **Không suy ra deadlock chỉ vì thread WAITING**; rất nhiều threads bình thường chờ queue, timer hoặc socket.

Khi capture thread dump, cần quyền và bảo vệ file đầu ra vì stack/ThreadLocal có thể phản ánh thông tin hệ thống. Không đăng dump chứa nội dung nhạy cảm lên kênh chat/ticket không có phân quyền.

Test reproduction ở staging có thể dùng CountDownLatch/CyclicBarrier để tạo điều kiện tranh chấp; không dùng Thread.sleep để tuyên bố đã chứng minh race condition.

## 13. HTTP clients: timeout và retry storm

Khi Java service gọi dependency HTTP, cần phân biệt các loại timeout:

| Loại | Giai đoạn | Hướng điều tra |
| --- | --- | --- |
| Connect timeout | Chưa kết nối được tới endpoint | DNS, route, network, listener |
| Read/response timeout | Đợi dữ liệu phản hồi quá lâu | Upstream latency, thread/pool saturation |
| Connection acquisition timeout | Chờ lấy connection từ client pool | Pool limits, leaked/held connections |
| Deadline/cancellation | Tổng ngân sách thời gian request hoặc RPC | Propagation của deadline và retry |
| TLS handshake failure | Bắt tay mã hóa thất bại | Cert chain, truststore, protocol version |

**Không đánh đồng một timeout client với việc upstream chưa xử lý.** Upstream có thể đã ghi dữ liệu nhưng phản hồi chậm hoặc ACK thất lạc. Retry một thao tác không idempotent có thể nhân side effects.

Log nên có dependencyName, operation, timeoutCategory, attemptNo, durationMs, statusCode (nếu đã có response), retryable và terminal outcome. Không log raw Authorization, URL kèm token hoặc body nhạy cảm.

Khi backend chậm, quá nhiều clients cùng retry có thể gây **retry storm**, làm sự cố nặng hơn. Kiểm tra exponential backoff + jitter, retry budget, circuit breaker, concurrency limit và timeout chain.

## 14. JDBC/database: kết nối, transaction và truy vấn chậm

Các lỗi database thường thể hiện qua SQLException hoặc timeout trong Java logs, nhưng cần đối chiếu với metrics từ pool và database.

Kiểm tra:

1. **Pool active/idle/pending:** có cạn kết nối không, time-to-acquire tăng khi nào?
2. **Slow query:** query fingerprint, elapsed time, locks, missing indexes, execution plans.
3. **Transaction boundaries:** có transaction giữ connection trong lúc chờ HTTP không?
4. **Lock contention/deadlock:** theo dấu từ database và SQLState.
5. **Connection lifetime/recovery:** network idle timeout, proxy reset, database failover.
6. **Schema migrations:** sự cố có bắt đầu sau deploy hoặc DDL?
7. **Error classification:** transient connection error khác constraint violation hoặc validation failure.

Ví dụ log chuẩn hóa:

~~~json
{
  "eventCode": "DB_CONNECTION_ACQUIRE_FAILED",
  "service": "order-api",
  "dependencyName": "orders-db",
  "errorCode": "POOL_TIMEOUT",
  "requestId": "req-42",
  "durationMs": 3000
}
~~~

Đây là **event minh họa**. Không log SQL bind parameters hoặc credentials để điều tra. Khi cần SQL diagnostics, dùng query identifier/fingerprint và hệ thống truy vấn có kiểm soát. Logger DEBUG của JDBC/ORM có thể tiết lộ raw values và tăng tải, nên không bật tùy tiện ở production.

**Pool cạn có thể là hậu quả** của database chậm hoặc application giữ connection lâu, không nhất thiết là cấu hình pool quá nhỏ. Phải kiểm tra timeline trước khi tăng max pool size.

## 15. Message brokers và background jobs

Với Kafka, RabbitMQ hoặc hệ thống queue khác, request hoàn tất ở HTTP nhưng công việc bất đồng bộ có thể còn đang xử lý.

Các stage nên quan sát:

~~~text
EVENT_CREATED
   |
   v
PUBLISH_REQUESTED
   |
   v
PUBLISH_CONFIRMED
   |
   v
DELIVERY_RECEIVED
   |
   v
PROCESSING_STARTED
   |
   +-- SUCCESS --> ACKNOWLEDGED / OFFSET_COMMITTED
   |
   +-- FAILED --> RETRY_SCHEDULED --> REDELIVERED
                                      |
                                      v
                                  DEAD_LETTERED
~~~

**PUBLISH_REQUESTED không đồng nghĩa broker nhận.** **Broker confirm không đồng nghĩa consumer xử lý.** **ACK/offset commit không tự chứng minh side effect trong DB đã commit** nếu không có transaction/idempotency contract.

Khi truy tìm sự cố:

- Tìm messageId/eventId, consumer group, topic/partition/offset hoặc queue.
- Phân biệt một logical message với nhiều attempts.
- Kiểm tra backlog/lag, DLQ, retry delay, consumer rebalance và broker health.
- Đối chiếu outbox/inbox và business database để xác nhận sự kiện đã xử lý đúng.
- Nếu redelivery, kiểm tra idempotency và duplicate side effects.
- Khi replay từ DLQ, giữ causation/correlation và audit người thực hiện.

Một log event vắng mặt có thể do log drop, không phải message mất. Nguồn xác minh phải gồm broker metadata và business state.

## 16. Hạ tầng: container, Kubernetes và Linux host

Khi Java chạy trên Kubernetes/VM, sự cố có thể đến từ hạ tầng:

| Triệu chứng | Nguồn kiểm tra |
| --- | --- |
| Pod restart nhiều lần | Pod/container status, restart reason, prior logs |
| OOMKilled | cgroup memory, container limits, node pressure |
| CPU throttling | CPU quotas/throttling metrics, request latency |
| Readiness/liveness thất bại | Probe events, JVM pause, startup time |
| DNS/TLS thất bại | Resolver, cert expiry/rotation, network policy |
| Node disk pressure | Logging spool, ephemeral storage, volume health |
| Deployment rollout lệch | Pod version, image digest, config checksum |
| Chỉ một zone/region lỗi | Instance/zone metadata, upstream route |

Đừng mặc định pod restart là ứng dụng tự crash. Orchestrator có thể kill vì cgroup memory, probe timeout hoặc node eviction. Phải xem cả deployment events và logs của container trước khi restart khi hệ thống lưu được.

Không thay production resource limits/connection strings chỉ dựa vào một log WARN. Thực hiện có kiểm soát, ghi lại baseline và metrics sau thay đổi.

## 17. Nếu không thấy log: điều tra pipeline logging

Một sự cố nghiêm trọng có thể đi kèm **mất chính log quan sát**. Pipeline thường gồm:

~~~text
Java logger / Logback / JUL
       |
       v
stdout / rolling file / journald
       |
       v
Host agent / DaemonSet / sidecar
       |
       v
Queue, retry, parsing, buffering
       |
       v
Collector / gateway
       |
       v
Index / archive / dashboard
~~~

Các câu hỏi cần trả lời:

- Log level/filter có chặn event? Logger name và effective level có đúng?
- AsyncAppender có queue đầy và drop event không?
- Console/file path có đúng, rolling policy có xóa file trước khi agent đọc?
- Container/runtime/journald có rate-limit hoặc rotate log không?
- Agent có state offset/cursor và permission đúng không?
- Multiline parser có trộn/tách stack traces sai?
- Collector đang retry/throttle, trả lỗi 429/5xx hoặc bị disk-full?
- Backend index/query có time window và filters đúng không?
- Trace sampling/retention có che bớt bằng chứng không?

**Không thấy log không chứng minh hành động không xảy ra.** Trước khi kết luận thiếu event, kiểm tra collector health, backlog, drop metrics, sampling và nguồn local. Tuy nhiên trong một số hệ thống, một event audit bắt buộc không được tạo cũng là sự cố độc lập cần điều tra với business source/outbox.

## 18. Các truy vấn log theo chiến lược pivot

Đừng bắt đầu bằng dump toàn bộ production logs. Một chuỗi truy vấn thường hiệu quả:

1. Chọn **service + environment + time range** theo alert.
2. Xác định **eventCode/errorCode** tăng bất thường; tách theo version/region.
3. Từ một sự kiện cụ thể, lấy **requestId hoặc traceId**.
4. Tìm tất cả events của ID ấy, không chỉ ERROR.
5. Mở trace để thấy spans upstream/downstream và duration.
6. Pivot theo **dependencyName** nếu nhiều requests cùng timeout.
7. So cohort lỗi với cohort thành công trong cùng version.
8. Kiểm tra config/deploy/feature flag đúng thời điểm bắt đầu.
9. Tìm phản chứng và đối chiếu metrics/broker/DB.
10. Ghi câu truy vấn, time window và bằng chứng để có thể tái lập.

Ví dụ pseudo-query (không phải cú pháp cụ thể của Elasticsearch, Loki hay Splunk):

~~~text
WHERE environment = "production"
  AND service = "payment-api"
  AND timestamp BETWEEN "03:00Z" AND "03:10Z"
GROUP BY eventCode, version, region
COUNT events
~~~

Một query thứ hai có thể lọc **requestId = req-42** và sắp theo event timestamp. Nhưng tổng count log không bằng số users hay số business failures nếu một request sinh nhiều log hoặc có retry.

Khi dùng Elasticsearch/Kibana, Grafana Loki, OpenSearch hoặc Splunk, cú pháp và trường index có thể khác nhau. Không sao chép pseudo-query trên và coi nó chạy ngay mà chưa xác nhận schema backend.

## 19. Ví dụ Java 17 chạy độc lập: truy dấu hai request từ JUL

Ví dụ dưới dùng **java.util.logging (JUL)** có sẵn trong Java SE, không cần SLF4J/Logback/Maven. Một Handler in-memory giữ các event có cấu trúc, sau đó truy vấn theo requestId. Case đầu có timeout nhưng fallback thành công; case thứ hai chỉ quan sát được event bắt đầu và lỗi từ dependency.

Tạo file **IncidentInvestigationDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class IncidentInvestigationDemo {
    record Event(String requestId, String service,
                 String stage, String errorCode) {}

    record Captured(Level level, Event event) {}

    static final class CaptureHandler extends Handler {
        final List<Captured> records = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            Object[] params = record.getParameters();
            if (params != null && params.length == 1
                    && params[0] instanceof Event event) {
                records.add(new Captured(record.getLevel(), event));
            }
        }

        @Override
        public void flush() {}

        @Override
        public void close() {}
    }

    private static void emit(Logger logger, Level level, Event event) {
        logger.log(level, "structured-event", new Object[]{event});
    }

    private static void inspect(List<Captured> records, String requestId) {
        List<Captured> matches = records.stream()
                .filter(row -> row.event().requestId().equals(requestId))
                .toList();

        System.out.println("TRACE " + requestId);
        for (Captured row : matches) {
            Event event = row.event();
            System.out.println(row.level().getName() + " "
                    + event.service() + " " + event.stage()
                    + " code=" + event.errorCode());
        }

        boolean terminalObserved = matches.stream()
                .anyMatch(row -> row.event().stage().equals("REQUEST_COMPLETED")
                        || row.event().stage().equals("REQUEST_FAILED"));

        System.out.println("SUMMARY " + requestId
                + " events=" + matches.size()
                + " terminalObserved=" + terminalObserved);
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("incident.investigation.demo");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        CaptureHandler handler = new CaptureHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);
        try {
            emit(logger, Level.INFO,
                    new Event("req-42", "gateway", "REQUEST_STARTED", "NONE"));
            emit(logger, Level.WARNING,
                    new Event("req-42", "catalog", "DOWNSTREAM_TIMEOUT",
                            "CATALOG_TIMEOUT"));
            emit(logger, Level.INFO,
                    new Event("req-42", "gateway", "FALLBACK_USED", "NONE"));
            emit(logger, Level.INFO,
                    new Event("req-42", "gateway", "REQUEST_COMPLETED", "NONE"));

            emit(logger, Level.INFO,
                    new Event("req-43", "gateway", "REQUEST_STARTED", "NONE"));
            emit(logger, Level.WARNING,
                    new Event("req-43", "inventory", "DB_POOL_EXHAUSTED",
                            "POOL_TIMEOUT"));

            inspect(handler.records, "req-42");
            inspect(handler.records, "req-43");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac IncidentInvestigationDemo.java
java IncidentInvestigationDemo
~~~

**Stdout chính xác của chương trình:**

~~~text
TRACE req-42
INFO gateway REQUEST_STARTED code=NONE
WARNING catalog DOWNSTREAM_TIMEOUT code=CATALOG_TIMEOUT
INFO gateway FALLBACK_USED code=NONE
INFO gateway REQUEST_COMPLETED code=NONE
SUMMARY req-42 events=4 terminalObserved=true
TRACE req-43
INFO gateway REQUEST_STARTED code=NONE
WARNING inventory DB_POOL_EXHAUSTED code=POOL_TIMEOUT
SUMMARY req-43 events=2 terminalObserved=false
~~~

### Vì sao demo có ích?

- Sử dụng **JUL Logger + Handler + LogRecord** thật, nhưng chụp dữ liệu trong bộ nhớ thay vì gửi tới backend.
- Dữ liệu **Event** được truyền qua LogRecord parameters, không parse một chuỗi message tự ghép. Handler kiểm tra kiểu và lấy Level để lưu.
- **req-42** có một warning timeout, nhưng sau đó fallback và terminal event REQUEST_COMPLETED. Nếu chỉ grep WARNING, có thể báo sai rằng request cuối cùng thất bại.
- **req-43** mới có hai event, event cuối quan sát là DB_POOL_EXHAUSTED; **terminalObserved=false** chỉ nghĩa là **không thấy terminal event trong mẫu log**, không chứng minh request đã mất hoặc DB pool chắc chắn là root cause.
- Output dùng level **WARNING** theo tên của JUL, khác nhãn **WARN** thường thấy trong SLF4J/Logback.
- Không có timestamp để stdout không phụ thuộc đồng hồ. Ở production, event cần timestamp, service/version, traceId, duration, dependency và correlation đúng.
- Mô hình dùng một thread; **ArrayList không phải collector thread-safe**. Đừng dùng nguyên CaptureHandler này như backend logging production hoặc test concurrency không đồng bộ.
- Demo không có collector, sampling, GC, HTTP/DB calls, retries thực, tính bền vững hay phân quyền. Nó minh họa **cách suy luận dựa trên các stage đã quan sát**, không phải bằng chứng thực của một incident.

**Bài tập mở rộng:** thêm REQUEST_FAILED cho req-43 rồi xác minh terminalObserved chuyển true; thêm một event WARN khác trước REQUEST_COMPLETED của req-42 và kiểm tra kết quả cuối vẫn được suy ra từ terminal stage, không chỉ mức độ log.

## 20. Quy trình truy tìm một HTTP 503 trong production

Giả sử error rate của route POST /orders tăng sau rollout.

**Bước 1 — Xác nhận vấn đề:** đo HTTP 503 rate, p95/p99 latency và số orders đã commit. Xác định version, region và thời điểm bắt đầu.

**Bước 2 — Tìm mẫu lỗi:** group theo eventCode, errorCode, dependencyName; nếu tất cả lỗi đều đi qua inventory, kiểm tra inventory và connection pools.

**Bước 3 — Chọn mẫu request:** dùng requestId/traceId của một request lỗi, xem toàn bộ timeline từ REQUEST_STARTED đến terminal. Tìm fan-out calls, retry/fallback, timeouts và transaction result.

**Bước 4 — Kiểm tra thay đổi:** deploy mới, config timeout, cache, DNS/TLS cert, database pool, feature flags. So sánh một instance/version đang lỗi với một instance còn khỏe.

**Bước 5 — Đối chiếu telemetry:** CPU, GC, threads, pool wait, dependency metrics, DB locks, broker lag, Kubernetes events.

**Bước 6 — Giảm thiểu:** nếu bằng chứng chỉ ra rollout làm tăng request concurrency, rollback/giảm traffic hoặc giới hạn đồng thời theo runbook; không thay cả timeout và pool size cùng lúc nếu điều đó làm mất khả năng phân biệt nguyên nhân.

**Bước 7 — Verify recovery:** error rate và latency trở lại baseline, queue backlog drain, đơn hàng không thiếu/trùng, customer-facing probes thành công.

**Bước 8 — Ghi lại evidence và follow-ups:** root cause khi đã đủ căn cứ, biện pháp sửa lâu dài, detection gaps và test tránh tái diễn.

**Truy tìm không phải “sửa log cho hết ERROR”**. Mọi thay đổi cấu hình logging phải bảo toàn khả năng quan sát thiết yếu và yêu cầu audit.

## 21. Production logging: tăng độ chi tiết có kiểm soát

Khi logs hiện có chưa đủ, đội vận hành đôi khi cần bật DEBUG tạm thời. Cần kiểm soát:

| Rủi ro | Cách giảm thiểu |
| --- | --- |
| DEBUG làm lộ headers/body/token/PII | Review logger của thư viện, redact/omit từ nguồn |
| Tăng volume làm đầy disk/collector | Giới hạn scope: service/instance/logger/time window |
| Async queue bị drop | Theo dõi dropped logs, queue và backpressure |
| CPU/GC tăng vì format stack trace | Profile, không dump objects lớn |
| Dynamic level không tự trở về | Có owner, expiry/rollback và audit change |
| Log forging từ dữ liệu user | Structured encoding, validate IDs, escape control chars |
| Truy cập log vượt quyền | RBAC, audit truy vấn/export, dữ liệu tối thiểu |

Không log nguyên Authorization, Cookie, access token, credit card hoặc SQL bind parameters để điều tra sự cố. Có thể ghi **eventCode, requestId, payload schema, kích thước, status, exceptionType**, và dùng kho bằng chứng bảo vệ riêng nếu thật sự cần chi tiết nhạy cảm theo quy trình.

**Log level là lựa chọn mức độ quan sát, không phải mức độ bảo mật của field.** Một dòng ERROR có token vẫn là rò rỉ, còn một dòng DEBUG chỉ ghi một errorCode cố định có thể an toàn hơn.

## 22. Query nhiều nguồn mà không làm mất bối cảnh

Khi phát hiện một sự kiện trong dashboard, cần lưu:

- Query và time range đã dùng, timezone, environment.
- Tên service, deployment version, host/pod hoặc region.
- requestId/traceId, spanId và eventCode.
- Dashboard panel/metric hoặc trace URL nội bộ được cấp quyền.
- Các event trước và sau, không chỉ ảnh chụp một exception.
- Thời điểm ingest và source timestamp nếu nghi đồng hồ lệch.
- Những thay đổi đã thực hiện trong incident và thời điểm chúng diễn ra.

**Không chia sẻ public URL chứa token hoặc dữ liệu cá nhân**. Khi cần đưa evidence vào incident ticket, ưu tiên ID tham chiếu, link nội bộ có phân quyền và ảnh/đoạn đã redact theo policy.

Một log query trả 0 record có thể do sai index, sampling, retention, tokenization khác schema hoặc timeline chỉ lệch phút. Luôn đối chiếu collector health nếu dữ liệu quan sát dường như biến mất hàng loạt.

## 23. Incident response, mitigation và kiểm chứng kết quả

Trong nhiều sự cố, mitigation và root-cause analysis diễn ra song song nhưng không phải một việc.

**Mitigation** có thể gồm:

- Rollback một release có bằng chứng gây suy giảm.
- Giới hạn concurrency, traffic hoặc retry budget.
- Tạm pause một noncritical background job theo runbook.
- Fail over sang dependency khỏe khi mô hình consistency cho phép.
- Thay certificate/secret khi có chứng cứ về sự cố xác thực và quy trình cấp quyền phù hợp.
- Bật circuit breaker/fallback đã được thiết kế và thử trước.

**Sau mitigation**, phải kiểm chứng bằng các tín hiệu độc lập:

1. Error rate và latency cải thiện có bền hay chỉ tạm thời.
2. Throughput và backlog thực sự phục hồi.
3. Business transactions không bị mất/trùng.
4. Số connections/threads/GC pauses về mức hợp lý.
5. Không xuất hiện lỗi mới ở downstream hoặc cohort khác.
6. Logging/collector còn hoạt động và không bị drop vì tải tăng.

Một rollback có thể làm error giảm nhưng chưa giải quyết được **messages đang kẹt trong DLQ** hoặc các side effects trùng. Đặt tiêu chí “incident resolved” theo trải nghiệm người dùng và trạng thái nghiệp vụ, không chỉ theo dashboard của một service.

## 24. Postmortem: từ sự cố tới hệ thống tốt hơn

Một postmortem có ích cần là **bản tường thuật có bằng chứng**, không phải chỉ liệt kê lỗi cá nhân.

Các phần khuyến nghị:

| Phần | Nội dung |
| --- | --- |
| Summary | Triệu chứng và tác động đến users/SLO |
| Timeline | Sự kiện, cảnh báo, triển khai, mitigation, recovery |
| Detection | Alert nào phát hiện; có độ trễ hoặc blind spot không |
| Technical cause | Cơ chế lỗi, điều kiện kích hoạt, phản chứng đã kiểm |
| Contributing factors | Backpressure, thiếu timeout budget, config, capacity, monitoring |
| Impact | Request failures, latency, downtime, sai/trùng dữ liệu |
| Mitigation | Đã làm gì, ai phê duyệt, kết quả ra sao |
| Recovery verification | Metrics, traces và business checks |
| Corrective actions | Owner, mức ưu tiên và acceptance tests |
| Monitoring gaps | Cần eventCode/metric/trace/alert nào mới |
| Privacy/security | Có log lộ secret hoặc evidence access issue không |

Tránh tuyên bố chắc chắn khi dữ liệu không đủ. Nếu incident có nhiều nguyên nhân góp phần, mô tả causal chain thay vì ép thành một root cause duy nhất.

**Postmortem không nên làm tăng rủi ro riêng tư:** chỉ trích dẫn log đã được redact hoặc lưu references tới kho evidence có phân quyền; không copy nguyên credential, raw payload hay dữ liệu khách hàng.

## 25. Lỗi thường gặp khi truy tìm sự cố

| Cách làm sai | Vì sao nguy hiểm | Cách cải thiện |
| --- | --- | --- |
| Tìm ERROR rồi kết luận request failed | Có thể fallback/retry thành công | Xác minh terminal outcome |
| Coi lastObserved stage là trạng thái cuối | Logs có thể thiếu/drop | Đối soát business state |
| Đếm log errors = số users lỗi | Một user có nhiều retries/events | Đếm theo request/eventId |
| Tin một timestamp là thứ tự tuyệt đối | Clock skew, buffered logs | Correlation + causal metadata |
| Thấy timeout thì kết luận upstream không xử lý | ACK/response có thể mất | Idempotency và nguồn upstream |
| Tăng timeout/pool trước khi đo | Che nguyên nhân và tạo thêm tải | Kiểm tra metrics và baseline |
| Bật DEBUG toàn production | Rủi ro leak, disk full, perf overhead | Bật có giới hạn, audit, expiry |
| Log toàn bộ request/exception payload | Có thể lộ secrets và PII | Schema allowlist và redaction |
| Tin rằng thiếu log nghĩa là không có event | Collector có thể lỗi/sampling | Kiểm tra source→agent→backend |
| Chỉ nhìn service đang báo lỗi | Dependency/hạ tầng có thể là nguyên nhân | Pivot bằng trace/metrics |
| Reset service mà không lưu evidence | Mất state và timeline quan trọng | Chụp bằng chứng phù hợp trước khi can thiệp |
| Chỉ verify app không còn ERROR | Backlog/business data có thể sai | Business reconciliation |
| Giả định GC xảy ra là root cause | GC có thể chỉ là hệ quả | So pause/latency và allocation |
| Dùng một trace để kết luận cả hệ thống | Trace có thể sampling/ngoại lệ | So cohort + aggregate metrics |

## 26. Kiểm thử khả năng truy tìm trước khi có incident thật

Khả năng điều tra cần được thử khi hệ thống còn khỏe:

- **Synthetic canary request** có correlation ID an toàn, xác minh event từ gateway đến backend.
- **Timeout simulation** ở dependency test: log errorCode/attemptNo chính xác; terminal outcome không bị ghi sai.
- **Crash/restart** ở staging: biết log cuối đã được flush hay queue có thể mất gì.
- **Collector outage:** xác minh backlog, retry, log drop metrics, time-to-drain.
- **Concurrency:** request A/B xen kẽ không trộn MDC.
- **JVM pressure:** thử CPU/GC/thread pool ở môi trường được phép để xem metrics và alert.
- **DB pool exhaustion:** test giới hạn connection và error classification.
- **Message redelivery/DLQ:** giữ eventId và attempt, không nhân side effects.
- **Deployment rollback drill:** đảm bảo version markers và acceptance checks rõ.
- **Privacy test:** ID chứa newline/token giả không làm lộ dữ liệu hoặc tạo forged log.
- **Time skew/ingestion delay:** query và timeline vẫn giải thích được lệch thời gian.
- **Access test:** incident responder chỉ xem được data cần thiết.

Đánh giá test không chỉ dựa vào việc “có log”. Cần kiểm tra một người vận hành có thể **từ một alert tìm được root-cause candidates và bằng chứng phân biệt** mà không cần bật dump dữ liệu nhạy cảm hay sửa production tùy tiện.

## 27. Checklist thực hành truy tìm sự cố production

| Hạng mục | Kiểm tra |
| --- | --- |
| Bối cảnh | Xác định impact, severity, scope, start time và owner |
| Logging | Structured eventCode, requestId, traceId, version và outcome |
| Query | Khoanh service/env/time range trước, rồi pivot bằng correlation |
| Timeline | Phân biệt eventTime với ingestionTime và clock skew |
| Exceptions | Đọc cause chain, phân loại timeout, không lộ secret |
| JVM | Có GC/heap/thread metrics/JFR khi cần và được phép |
| HTTP | Phân biệt connect/read/pool timeout, retry budget/idempotency |
| DB | So pool saturation, SQL fingerprint, locks và transaction |
| Messaging | Publish confirm, consumer attempts, ACK/commit và DLQ |
| Infrastructure | Pod/container restarts, OOMKill, node resource, DNS/TLS |
| Pipeline | Kiểm tra log drop, rotation, agent queue, collector và retention |
| Hypotheses | Ghi ủng hộ, phản chứng, chưa biết và mức tin cậy |
| Mitigation | Thay đổi có chủ đích, rollback/giảm tải theo runbook |
| Verification | SLO, backlog, business state và telemetry đều phục hồi |
| Security | RBAC, redaction, bảo vệ incident evidence |
| Learning | Postmortem, regression tests, alert và owner action items |

**Kết luận:** truy tìm sự cố bằng Java Logging là quá trình **liên kết dấu vết và kiểm chứng giả thuyết**. Bắt đầu từ tác động và time window, dùng eventCode cùng requestId/traceId để dựng timeline, kiểm tra JVM, HTTP, database, message broker, hạ tầng và pipeline thu log, sau đó đối soát với metrics/traces/trạng thái nghiệp vụ. Log là nguồn bằng chứng mạnh khi có schema và correlation đúng, nhưng **một dòng ERROR hoặc một khoảng trống log không phải toàn bộ sự thật**.