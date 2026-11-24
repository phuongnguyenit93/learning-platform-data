# Thu thập log, metric và dữ liệu sự cố từ tiến trình native

## 1. Vì sao cần thiết kế observability riêng cho native process?

Một ứng dụng Spring Boot chạy bằng GraalVM Native Image vẫn cần log, metric, trace và dữ liệu chẩn đoán để vận hành. Các tín hiệu ứng dụng như HTTP request, lỗi nghiệp vụ, database pool và queue lag thường tiếp tục dùng Spring Boot Actuator, Micrometer và logging framework. Tuy nhiên, khi process native crash, bị OOM hoặc gặp lỗi ở native library, đội vận hành còn cần thông tin ở cấp process và hệ điều hành như exit code, signal, core dump, native stack trace và debug symbols.

Không thể giả định công cụ thu thập của JVM/HotSpot sẽ hoạt động nguyên trạng với Native Image. JFR, heap dump, JMX, debugger và profiler phụ thuộc GraalVM distribution, phiên bản, option build và hệ điều hành. Cần xác minh khả năng được hỗ trợ trên đúng executable.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, bài học này xây dựng cách thu thập dữ liệu sự cố từ lúc request đi vào đến khi native process kết thúc. Mục tiêu là giữ đủ ngữ cảnh để điều tra mà không làm lộ secret, tăng overhead không cần thiết hoặc phụ thuộc vào shell trong distroless container.

## 2. Các lớp tín hiệu cần thu thập

| Lớp | Dữ liệu | Câu hỏi được trả lời |
|---|---|---|
| Application logs | Event, error, stack trace, request ID | Ứng dụng đã xử lý điều gì và lỗi ở đâu? |
| Metrics | Request rate, latency, error, CPU/RAM, pool usage | Hệ thống đang hoạt động ra sao theo thời gian? |
| Distributed traces | Span, parent/child, dependency calls | Request chậm hoặc lỗi ở service nào? |
| Process/container | Exit code, signal, restart, OOM, RSS | Process kết thúc thế nào và dùng tài nguyên ra sao? |
| Native diagnostics | Core dump, native stack, debug symbols | Crash xảy ra ở native frame hoặc library nào? |
| Build provenance | Commit, toolchain, flags, binary digest | Binary nào đang chạy và được build bằng gì? |
| Runtime profiles | JFR/heap dump nếu được hỗ trợ | Allocation, GC hoặc object retention có dấu hiệu gì? |

Không có một tín hiệu duy nhất thay thế tất cả. Log cung cấp sự kiện, metric cho biết xu hướng, trace nối các thành phần trong một request, còn core dump/native stack hỗ trợ điều tra crash ở mức process.

## 3. Ghi log ra stdout và stderr

Trong container, ứng dụng nên ghi log ra stdout/stderr để Docker/Kubernetes hoặc logging agent thu thập. Không cần ghi log vào file trong container nếu nền tảng đã quản lý log stream.

Spring Boot thường dùng logging framework đã cấu hình trong ứng dụng. Có thể điều chỉnh level qua cấu hình runtime:

```yaml
logging:
  level:
    root: INFO
    com.example.orders: INFO
```

Trong môi trường điều tra có thể tăng level cho package cụ thể trong thời gian giới hạn. Tránh bật DEBUG/TRACE toàn hệ thống lâu dài vì log volume, CPU, I/O và dữ liệu nhạy cảm có thể tăng đáng kể.

Với image distroless/scratch, stdout/stderr vẫn được container runtime thu thập dù không có shell. Hãy xác minh log thực sự xuất hiện trong `kubectl logs`, Docker logs hoặc hệ thống log tập trung.

## 4. Dùng structured logging để tìm kiếm và liên kết sự kiện

Log dạng văn bản tự do khó truy vấn khi có hàng trăm replica. Structured logging giúp đưa trường dữ liệu vào schema ổn định:

```json
{
  "timestamp": "2026-11-23T10:15:30.123Z",
  "level": "ERROR",
  "service": "orders-service",
  "environment": "production",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "requestId": "req-82f1",
  "event": "payment_authorization_failed",
  "orderId": "ord-1001",
  "errorType": "PaymentTimeoutException"
}
```

Đây là ví dụ schema; giá trị thực tế cần tuân thủ chính sách dữ liệu. Không ghi access token, password, private key, full payment data hoặc payload cá nhân không cần thiết.

Các trường hữu ích:
- Timestamp có timezone rõ ràng, thường chuẩn hóa UTC.
- Service name, environment và version.
- Trace ID/span ID nếu có tracing.
- Request/correlation ID.
- Event name ổn định.
- Error type và stack trace theo policy.
- Instance/pod identity nếu platform không tự gắn.

Tránh dùng user ID, order ID hoặc giá trị tùy ý làm metric label vì cardinality có thể tăng mạnh. Những giá trị định danh cụ thể phù hợp hơn trong log/trace đã được bảo vệ.

## 5. Giữ correlation ID xuyên suốt request

Khi một request đi qua gateway, Order API, payment service và database, cần có cách liên kết log giữa các thành phần. Dùng W3C Trace Context hoặc cơ chế correlation đã thống nhất.

Nếu hệ thống dùng Micrometer Tracing/OpenTelemetry, trace context có thể được propagate qua HTTP client và server instrumentation. Log correlation có thể đưa trace ID/span ID vào MDC hoặc structured fields tùy logging setup.

Không tự tạo trace ID mới ở mọi layer nếu đã có context từ request cha. Điều đó làm mất quan hệ giữa các span. Với message broker, cần propagate context qua message headers theo instrumentation/convention của hệ thống.

Khi request đến từ client không tin cậy, không dùng nguyên giá trị header bất kỳ làm định danh nội bộ nếu chưa validate độ dài/format. Gateway có thể tạo hoặc chuẩn hóa request ID.

## 6. Thu thập stack trace của exception Java

Native executable vẫn chạy Java application code và có thể phát sinh exception Java. Log exception cần giữ type, message phù hợp và stack trace đủ để xác định đường đi.

Ví dụ:

```java
try {
    paymentGateway.authorize(command);
} catch (PaymentException ex) {
    log.error(
            "Payment authorization failed for orderId={}",
            command.orderId(),
            ex);
    throw ex;
}
```

Không log rồi nuốt exception nếu caller cần xử lý; cũng không log cùng một exception ở mọi tầng gây trùng lặp. Chọn một boundary chịu trách nhiệm ghi lỗi và gắn correlation context.

Độ chi tiết stack trace native có thể phụ thuộc option build và GraalVM version. Nếu cần trace đầy đủ hơn, xác minh option tương ứng trên toolchain đang dùng và kiểm tra kết quả trên executable, không suy ra từ JVM test.

## 7. Log startup và shutdown có cấu trúc

Startup log cần cho biết process đã qua những mốc nào:
- Process bắt đầu.
- Spring context được khởi tạo.
- Server bind port.
- Dependency bắt buộc sẵn sàng.
- Readiness chuyển thành true.

Shutdown log nên ghi:
- Nhận tín hiệu dừng.
- Ngừng nhận traffic/drain.
- Đóng listener, datasource, broker consumer và scheduler.
- Hoàn tất shutdown hoặc hết grace period.

Không ghi secret hoặc connection string đầy đủ. Dùng duration và trạng thái để đo time-to-ready và shutdown duration. Nếu process bị SIGKILL hoặc OOM, shutdown log có thể không xuất hiện; cần kết hợp container events và exit metadata.

## 8. Metrics ứng dụng bằng Actuator và Micrometer

Spring Boot Actuator cùng Micrometer cung cấp metrics ở cấp ứng dụng. Ví dụ các nhóm thường cần:
- HTTP server request count và duration.
- JVM/native process memory metrics mà registry/runtime cung cấp.
- CPU/process metrics.
- Database connection pool.
- Executor/thread pool.
- Cache hit/miss.
- Queue depth/consumer lag.
- Business counters như order accepted/rejected.

Dependency và registry cần được thêm đúng, ví dụ Prometheus registry nếu hệ thống scrape Prometheus. Chỉ cấu hình endpoint không tự tạo mọi metric mong muốn.

Ví dụ cấu hình exposure:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
```

Chỉ expose endpoint cần thiết và giới hạn qua network policy/authentication. Không đưa endpoint metrics hoặc environment/config dump ra public internet.

## 9. Phân biệt JVM metrics với native process metrics

Một số metric mang tên JVM có thể không có cùng ý nghĩa hoặc không khả dụng trong Native Image như trên HotSpot. Micrometer binder và Spring Boot version có thể cung cấp tập metric khác nhau tùy runtime.

Phân biệt:
- Heap/object metrics do Native Image runtime cung cấp.
- Process RSS/CPU từ OS/container.
- Cgroup memory/CPU limit và throttling.
- Application-level request/connection metrics.
- GC metrics nếu collector/runtime expose được.

Không giả định mọi JMX-based JVM binder đều hoạt động trong native executable. Kiểm tra metric registry thực tế và đối chiếu với nguồn dữ liệu của container platform. Nếu cần RSS chính xác, metrics từ cgroup/container runtime thường là nguồn phù hợp hơn.

## 10. Chọn metric có cardinality kiểm soát

Metric label nên có tập giá trị hữu hạn và ổn định: method, status class, outcome, region hoặc dependency name đã giới hạn. Tránh label theo:
- Request ID.
- Trace ID.
- User ID.
- Order ID.
- URL path chứa identifier tùy ý.
- Exception message tự do.

Các label cardinality cao có thể làm tăng memory và storage của metrics backend. Dữ liệu định danh chi tiết nên nằm trong log/trace theo quyền truy cập và retention phù hợp.

Tạo dashboard theo service, environment và version; có thể xem request rate, error rate, p95/p99 latency, saturation, dependency latency, RSS và restart count.

## 11. Distributed tracing cho dependency calls

Trace giúp thấy một request gồm những span nào: inbound HTTP, service method, SQL, outbound HTTP, broker publish/consume. Spring Boot có thể dùng Micrometer Tracing với bridge/exporter tương ứng hoặc OpenTelemetry SDK/instrumentation theo stack đã chọn.

Cần xác minh:
- Trace context được nhận và propagate.
- Outbound HTTP client có instrumentation.
- Database/broker spans có ý nghĩa.
- Sampling phù hợp với volume.
- Exporter gửi dữ liệu tới collector.
- Native executable chạy được instrumentation đã chọn.

Build metadata của Native Image và tracing runtime là hai phần khác nhau. Framework/dependency cần có native support/metadata, trong khi endpoint OTLP, service name và sampling là cấu hình runtime.

Không export mọi request với sampling 100% nếu volume lớn mà chưa tính chi phí. Giữ error/high-latency sampling theo chính sách và tránh đưa dữ liệu nhạy cảm vào span attributes.

## 12. Ghi nhận exit code, signal và restart reason

Khi native process kết thúc, log ứng dụng có thể không kịp flush. Container runtime/orchestrator cung cấp thông tin bổ sung:
- Exit code.
- Termination reason.
- Signal hoặc trạng thái OOMKilled.
- Restart count.
- Container start/finish timestamp.
- Previous container logs.
- Pod events và node pressure.

Với Kubernetes:

```bash
kubectl describe pod <pod-name>
kubectl logs <pod-name> --previous
kubectl get events --sort-by=.lastTimestamp
```

Với Docker:

```bash
docker inspect orders-service
docker logs --timestamps orders-service
```

Lưu thông tin này trong incident timeline. Exit code không phải lúc nào cũng đủ để xác định nguyên nhân; kết hợp signal, kernel event, cgroup memory và native diagnostics.

## 13. OOM và dữ liệu bộ nhớ

Native process có thể bị hệ điều hành/container runtime dừng khi vượt memory limit. Trong trường hợp OOM kill, ứng dụng có thể không có cơ hội ghi exception hoặc shutdown log.

Thu thập:
- Container memory usage và peak.
- Memory limit/request.
- Process RSS nếu có.
- Heap limit/runtime metrics nếu được hỗ trợ.
- CPU throttling và request concurrency.
- Restart/OOMKilled events.
- Workload/traffic trước thời điểm lỗi.

Phân biệt heap với RSS. RSS còn gồm code, native memory, thread stacks, mapped files và shared libraries. Không tăng heap limit một cách máy móc khi container memory limit không đổi.

## 14. Core dump và native crash diagnostics

Khi process crash ở native code hoặc runtime, core dump có thể giúp phân tích trạng thái process tại thời điểm lỗi. Khả năng tạo core dump phụ thuộc OS, kernel, container runtime, ulimit, security policy và storage.

Trên Linux, kiểm tra giới hạn core dump của process/container và cấu hình host theo policy. Core dump có thể rất lớn và chứa dữ liệu nhạy cảm trong memory. Không bật dump vô hạn cho mọi replica production.

Quy trình tổng quát:
1. Xác định signal/exit reason.
2. Xác nhận core dump có được tạo.
3. Lưu binary chính xác cùng debug symbols.
4. Ghi architecture, OS/kernel và shared library versions.
5. Dùng debugger/toolchain tương thích để mở core.
6. Phân tích native stack và map địa chỉ về symbol.
7. Liên hệ native frame với Java/application stack khi thông tin có sẵn.

Không dùng binary mới build để phân tích core dump của binary cũ nếu không có đảm bảo symbol/layout giống nhau.

## 15. Giữ debug symbols và build provenance

Khi build với debug information, cần lưu symbol files hoặc executable chưa strip theo chính sách. Artifact nên gắn:
- Git commit.
- Native executable SHA-256.
- GraalVM distribution/version.
- JDK/compiler/plugin versions.
- Build arguments.
- Target architecture/OS.
- Dependency/SBOM identity.
- Debug symbol artifact ID.

Nếu production image đã strip symbols, symbol archive phải tương ứng chính xác binary digest. Dùng artifact store riêng, hạn chế quyền truy cập và retention theo incident policy.

Debug symbols có thể tiết lộ source path, package và tên function. Không công khai chúng cùng image nếu không cần.

## 16. JFR, heap dump và JMX phụ thuộc phiên bản

GraalVM Native Image có thể hỗ trợ một số monitoring capabilities như JFR, heap dump hoặc JMX trong các distribution/version nhất định. Tập tính năng, option build và cách kích hoạt khác nhau; không mặc định chúng có mặt như HotSpot.

Trước khi dựa vào:
1. Ghi GraalVM distribution/edition/version.
2. Kiểm tra Native Image documentation và compiler help.
3. Bật monitoring feature ở build time nếu yêu cầu.
4. Chạy thử trên executable native.
5. Xác minh recording/dump thực sự được tạo và đọc được bằng tool tương thích.
6. Đo overhead và xác định output path/quota.

Nếu tính năng không có trong toolchain, dùng OS/container metrics, structured logs, core dump hoặc profiler được hỗ trợ thay thế. Không đưa option JFR/heapdump vào pipeline chỉ vì compiler chấp nhận cú pháp của một release khác.

## 17. Thu thập log và diagnostics trong distroless container

Distroless/scratch thường không có shell, package manager, curl hoặc debugger. Điều này không ngăn stdout/stderr được thu thập, nhưng làm thay đổi quy trình điều tra.

Chuẩn bị:
- Logging collector ở node/platform.
- Metrics scrape hoặc exporter.
- Tracing collector.
- Ephemeral debug container có network/process context phù hợp.
- Host-level tools cho core dump và process inspection.
- Volume/storage dành cho diagnostics nếu được bật.
- Image digest và binary/symbol artifacts.

Không cài debugger vào production container đang chạy. Dùng debug image hoặc ephemeral container theo chính sách nền tảng, bảo đảm dữ liệu được thu thập thuộc đúng pod/process và cùng thời điểm sự cố.

## 18. Bảo vệ dữ liệu sự cố

Log, trace, heap dump và core dump có thể chứa dữ liệu nhạy cảm. Đặt chính sách:
- Mask/token redaction trước khi ghi.
- Hạn chế payload logging.
- Mã hóa dữ liệu khi truyền và lưu.
- RBAC cho log/trace/diagnostic store.
- Retention và deletion.
- Audit truy cập dữ liệu sự cố.
- Giới hạn dung lượng dump và quota.
- Không gửi secret qua command-line arguments hoặc build logs.

Core dump/heap dump cần được xem là dữ liệu có mức nhạy cảm cao vì có thể chứa nội dung memory của process. Chỉ thu thập khi có lý do, bảo vệ storage và xóa sau thời hạn được duyệt.

## 19. Incident workflow cho native process

Khi native service gặp crash hoặc tăng memory:

1. Ghi thời điểm, service version, pod/container ID và image digest.
2. Thu logs trước/sau sự cố cùng trace ID/request ID liên quan.
3. Thu metrics CPU, RSS, cgroup memory, latency, error và restart.
4. Kiểm tra exit code, signal, OOMKilled và orchestrator events.
5. Lưu native stack/core dump nếu đã cấu hình và có thể thu thập an toàn.
6. Lấy debug symbols đúng binary digest.
7. Đối chiếu dependency/native library và toolchain version.
8. Tái hiện với cùng image/config/workload trong staging.
9. Ghi nguyên nhân, điều kiện kích hoạt và biện pháp khắc phục.
10. Bổ sung alert/test/runbook để phát hiện sớm lần sau.

Không rebuild rồi thay thế artifact trước khi lưu evidence. Việc thay image hoặc restart có thể làm mất trạng thái process và dữ liệu tạm cần cho điều tra.

## 20. Ma trận dữ liệu cần có theo loại sự cố

| Sự cố | Dữ liệu ưu tiên |
|---|---|
| HTTP latency tăng | Request metrics, trace, dependency spans, CPU/throttling |
| Exception nghiệp vụ | Structured logs, stack trace, trace ID |
| Native crash/segfault | Signal, core dump, debug symbols, native stack |
| OOMKilled | Cgroup peak, RSS, heap metrics, memory limit, restart events |
| Startup fail | Startup logs, exit code, config/secret mount, loader error |
| Database outage | Dependency metrics, connection pool, readiness, DB logs |
| DNS/TLS failure | Resolver/network events, certificate/trust config, client errors |
| GC pause/heap pressure | GC/runtime metrics nếu hỗ trợ, allocation/live set, JFR nếu khả dụng |

Ma trận giúp on-call thu thập dữ liệu có mục đích. Không bật mọi diagnostic mode cho mọi incident nếu chi phí hoặc độ nhạy cảm không phù hợp.

## 21. Bài thực hành: thiết lập incident evidence cho Order API native

**Bối cảnh:** Order API chạy bằng native executable trong distroless container, xuất hiện restart bất thường và đôi khi tăng RSS sau burst traffic.

**Bước 1 — Chuẩn hóa log.** Ghi structured JSON ra stdout, thêm service/version/trace ID/request ID và không log secret.

**Bước 2 — Bật metrics.** Thu request rate, p95/p99, error, process/container memory, CPU, connection pool và restart count.

**Bước 3 — Bật tracing.** Kiểm tra inbound/outbound propagation và sampling; xác minh trace đến collector từ native executable.

**Bước 4 — Gắn provenance.** Lưu image digest, binary checksum, GraalVM version, build arguments và symbol artifact.

**Bước 5 — Kiểm tra crash evidence.** Xác minh exit code/signal, OOM events và core dump policy trên staging; chỉ bật dump khi storage và quyền truy cập đã được kiểm soát.

**Bước 6 — Kiểm tra profiler.** Nếu distribution hỗ trợ JFR/heap dump, bật theo tài liệu và tạo sample; nếu không, ghi rõ giới hạn và dùng OS/container metrics.

**Bước 7 — Diễn tập sự cố.** Tạo tải burst trong staging, quan sát RSS, latency, restart và log; diễn tập thu thập evidence trước khi restart/redeploy.

**Bước 8 — Viết runbook.** Ghi lệnh thu log/events, nơi lấy dump/symbol, quyền truy cập và retention.

Tiêu chí hoàn thành: log/metric/trace có thể liên kết; restart/OOM có evidence; native crash có quy trình core/symbol nếu nền tảng hỗ trợ; image digest và toolchain truy vết được; dữ liệu sự cố được bảo vệ.

## 22. Kết luận

Vận hành Native Image cần kết hợp tín hiệu ứng dụng với dữ liệu ở cấp process và hệ điều hành. Spring Boot Actuator/Micrometer và tracing tiếp tục giúp theo dõi request, dependency và business behavior; container events, exit code, cgroup metrics, native stack, core dump và debug symbols hỗ trợ điều tra crash/OOM.

Hãy chuẩn hóa structured logs và correlation, thu metrics có cardinality kiểm soát, xác minh JFR/heap dump/JMX theo đúng GraalVM distribution/version, và giữ symbol gắn với binary digest. Với distroless container, chuẩn bị logging/metrics collector và debug workflow bên ngoài. Thu thập đủ evidence trước khi restart hoặc thay artifact, đồng thời bảo vệ log, trace và dump như dữ liệu nhạy cảm.
