# Anti-pattern: Log mọi thứ ở INFO trong Java Core Logging

## 1. Anti-pattern “Log mọi thứ ở INFO” là gì?

**Log mọi thứ ở INFO** là cách thiết kế logging trong đó hầu hết diễn biến nội bộ của chương trình Java đều được ghi với level `INFO`, bất kể chúng là trạng thái vận hành bình thường, chi tiết cần debug, thao tác lặp trong vòng lặp, cảnh báo cần can thiệp hay lỗi thật sự. Ví dụ, một request HTTP có thể tạo hàng chục dòng `INFO` cho những việc nhỏ như “vào method”, “đọc biến”, “gọi repository”, “nhận kết quả” và “thoát method”.

`INFO` **không phải level sai**. Nó có vai trò rất quan trọng để mô tả những mốc vận hành có ý nghĩa và tương đối ổn định. Anti-pattern xuất hiện khi chương trình dùng INFO làm **level mặc định cho mọi điều muốn kể**, khiến log quan trọng bị chìm trong nhiễu, chi phí tăng và việc truy vấn/điều tra khó khăn hơn.

Ví dụ đối lập:

```text
Không nên:
INFO Enter OrderController.create()
INFO Request received
INFO Calling OrderService
INFO Validating order
INFO Validation completed
INFO Calling OrderRepository
INFO Repository returned
INFO Response created
INFO Exiting OrderController.create()

Nên, tùy yêu cầu vận hành:
INFO event=order.accepted order_id=42 status=ACCEPTED request_id=req-101
DEBUG event=order.validation.completed rule_set=v3 request_id=req-101
WARN event=payment.retry dependency=payment attempt=1 reason=TIMEOUT
ERROR event=order.processing.failed error_code=PAYMENT_UNAVAILABLE request_id=req-102
```

Các dòng trên là ví dụ văn bản, không phải output cố định của một framework cụ thể. Trong thực tế nên dùng **structured logging** để `event.name`, `error.code`, `request_id`, `service.name` và `outcome` là các trường có cấu trúc, không chỉ nhét chuỗi key/value vào `message`.

Mục tiêu bài học: hiểu semantics của log levels, tác hại kỹ thuật/chi phí/bảo mật khi lạm dụng INFO, biết chọn event có ý nghĩa, cấu hình và tối ưu logging trong Java, thiết kế quan sát có thể kiểm thử, và triển khai ví dụ Java 17 xác định về lọc level và đánh giá tham số lazy.

## 2. Vì sao lập trình viên dễ rơi vào anti-pattern này?

Một số nguyên nhân thường gặp:

1. **Muốn “chắc chắn thấy log” trên production:** DEBUG hay TRACE thường tắt, nên nhà phát triển chuyển tất cả sang INFO thay vì tạo đường debug có kiểm soát.
2. **Dùng log thay debugger hoặc tracing:** ghi “enter/exit”, giá trị biến, kết quả từng hàm để theo dõi execution flow.
3. **Thiếu event taxonomy:** chưa có quy ước phân biệt business milestone, warning, final failure, diagnostic detail và audit event.
4. **Lo thiếu thông tin khi incident xảy ra:** log thêm thật nhiều thay vì thiết kế các trường correlation, error code, trace và thời điểm cần chụp trạng thái.
5. **Copy/paste code:** log ở controller, service và DAO đều ghi INFO cho cùng request; một operation tạo nhiều dòng trùng nội dung.
6. **Cấu hình level quá thô:** chỉ biết root level INFO, chưa biết bật DEBUG tạm theo package/class hoặc correlation trong môi trường an toàn.
7. **Nhầm INFO với “an toàn/ít ảnh hưởng”:** level không tự giới hạn event rate, payload size, dữ liệu nhạy cảm hoặc chi phí ingest.

Cách sửa không phải đổi tất cả `INFO` sang `DEBUG` một cách cơ học. Cần trả lời **ai sẽ dùng dòng log này, để ra quyết định nào và cần giữ bao lâu**. Một event nghiệp vụ quan trọng có thể vẫn xứng đáng INFO hoặc có tuyến audit riêng; nhiều dòng DEBUG có thể bỏ hẳn nếu đã có metric/trace phù hợp.

## 3. Các mức log trong Java: chọn theo ngữ nghĩa

| Mục đích | SLF4J / Logback / Log4j2 thường dùng | JUL (`java.util.logging`) gần tương ứng | Ví dụ |
| --- | --- | --- | --- |
| Chi tiết cực sâu, nhiều bước nội bộ | TRACE | `FINER` hoặc `FINEST` tùy mức chi tiết | Parse từng token, trạng thái từng vòng lặp |
| Chi tiết phục vụ lập trình viên điều tra | DEBUG | `FINE` | Kết quả chọn branch, tham số đã làm sạch |
| Mốc hoạt động bình thường đáng quan sát | INFO | `INFO` | Service started, deployment applied, operation accepted |
| Bất thường có thể phục hồi hoặc suy giảm | WARN | `WARNING` | Retry do timeout, circuit breaker chuyển trạng thái |
| Thất bại thực sự cần chú ý | ERROR | `SEVERE` | Request/operation không hoàn tất, phụ thuộc unavailable |
| Audit/security nghiệp vụ bắt buộc | Không chỉ dựa vào một level | Kênh/sink có contract riêng | Role granted/revoked, admin policy changed |

Bảng chỉ đưa ra **cách hiểu gần tương đương**, không phải ánh xạ chuẩn một-một của API. JUL có `CONFIG`, `FINE`, `FINER`, `FINEST`, `INFO`, `WARNING`, `SEVERE`; SLF4J thường có `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`. Log4j2 còn có `FATAL`/các khả năng riêng nhưng SLF4J API thông thường không có method `fatal()`.

### INFO dùng đúng lúc nào?

INFO thường hợp lý cho **mốc có ý nghĩa vận hành** và tần suất được dự trù:

- Ứng dụng bắt đầu/dừng, đã nạp cấu hình quan trọng không chứa secret, health transition.
- Một trạng thái nghiệp vụ quan trọng thay đổi hoặc một tác vụ nền hoàn thành, khi policy yêu cầu quan sát.
- Một event **request completion** cho mỗi request nếu tổ chức chủ động duy trì access logging với volume/retention/quyền truy vấn thích hợp.
- Kết quả của một batch/job có ý nghĩa, tổng số đối tượng xử lý hoặc điểm checkpoint, thay vì mỗi item nhỏ.
- Việc thay đổi chế độ vận hành/deployment version/feature gate quan trọng, có owner và điều kiện phát rõ ràng.

**Không có quy tắc “INFO không bao giờ được ghi cho từng request”.** Access logs có thể chủ đích ghi một completion event mỗi request và phục vụ incident/traffic analytics. Vấn đề là nhân bản các thông điệp INFO **không có thêm giá trị** trong mỗi bước và không có dự toán dung lượng.

### WARN và ERROR cần phân biệt final outcome

- **WARN:** lỗi tạm thời được hồi phục, retry, fallback, yêu cầu bất thường nhưng hệ thống vẫn đáp ứng.
- **ERROR:** thao tác đã **thất bại cuối cùng**, service không thể đáp ứng một yêu cầu quan trọng, hoặc tình huống cần xử lý có mức nghiêm trọng phù hợp.
- Một `IOException` ở attempt đầu không tự động có nghĩa cả HTTP request thất bại; retry có thể thành công.
- Validation 400 hoặc từ chối quyền 403 không nhất thiết là ERROR của server. Tùy threat model, có thể cần event bảo mật, metric và audit riêng.
- Một `NullPointerException` bị catch và xử lý an toàn có thể vẫn cần điều tra code quality, nhưng log severity nên phản ánh hậu quả và policy, không chỉ type của exception.

Tổ chức nên định nghĩa severity conventions, error codes và event owners cho mỗi loại operation. Bản chất của severity là **ưu tiên diễn giải**, không phải quy tắc cứng “cứ throw là ERROR”.

## 4. Hệ quả thứ nhất: INFO noise che mất lỗi thật

Khi 99% dòng log là INFO lặp lại, kỹ sư gặp sự cố phải sàng lọc nhiều thông điệp không mang giá trị để tìm vài ERROR/WARN cần xem. Hệ quả:

- Search trả về quá nhiều results, phải bổ sung regex và điều kiện loại trừ.
- Timeline request khó đọc vì mỗi method tạo vài dòng INFO, trong khi event thất bại thực sự thiếu `error.code` hoặc `outcome`.
- Dashboard dựa vào log counts phản ánh số call sites thay vì hành vi ứng dụng.
- Người vận hành có thể bỏ qua cảnh báo do quen với số lượng lớn message không đáng chú ý (**alert fatigue**).
- Khi thay đổi log statements, đường biểu diễn “INFO volume” thay đổi mạnh dù traffic và nghiệp vụ không đổi.

Ví dụ một request gọi repository 12 lần và mỗi lần ghi “query started/query finished” ở INFO: 24 dòng log có thể chẳng giúp biết request cuối **thành công, chậm hay lỗi**. Thay vào đó, completion event mang `duration_ms`, `route`, `http.status_code`, `request_id`, và metric latency theo route có thể giải thích tác động tốt hơn.

Một quy tắc hữu ích: **mỗi event INFO phải trả lời một câu hỏi vận hành cụ thể**. Nếu câu hỏi “khi nào tôi cần tìm event này?” không có câu trả lời rõ, dòng log có thể thuộc DEBUG/TRACE, metric/trace, hoặc không nên tạo.

## 5. Hệ quả thứ hai: chi phí tạo log trong JVM

Ngay cả khi log “chỉ là text”, quá trình tạo event có thể tiêu thụ CPU, heap, I/O và thời gian request.

Các khoản chi phí có thể xuất hiện:

1. **Tính toán tham số:** xây message, truy cập field, serialize object, nối String, format số/ngày.
2. **Cấp phát đối tượng:** StringBuilder, mảng byte, map, stack trace, exception details gây áp lực GC.
3. **Encoder/layout:** format timestamp, severity, thread, MDC, JSON escaping, Unicode encoding.
4. **Appender/handler:** ghi vào console/file/network, lock contention, flush hoặc fsync tùy cấu hình.
5. **Async queue:** enqueue, allocate buffers, backpressure hoặc discard khi đầy.
6. **Agent/shipper và backend:** CPU parse/index, lưu disk, network egress, retention, truy vấn.
7. **Tác động bắc cầu:** nếu log nhanh hơn backend, queue/disk đầy làm ứng dụng giảm throughput, kéo latency hoặc mất log.

Không phải mỗi INFO call đều gây chi phí như nhau: message hằng số rất nhỏ có thể rẻ, trong khi dump một đối tượng lớn hoặc stack trace ở mọi request có thể cực đắt. Benchmark trong workload/stack thực thay vì suy luận tuyệt đối từ level.

### Tham số được đánh giá sớm (eager evaluation)

Sai phổ biến:

```java
logger.fine("state=" + expensiveSnapshot());
```

Trong Java, `expensiveSnapshot()` được gọi **trước** khi method `fine` quyết định có log hay không. Nếu FINE đã tắt, chi phí tạo snapshot vẫn xảy ra.

JUL có các overload dùng `Supplier<String>` giúp tạo message khi level cho phép:

```java
logger.log(Level.FINE, () -> "state=" + expensiveSnapshot());
```

Khi `FINE` bị tắt, supplier này **không được gọi để format message**. Với SLF4J, placeholder parametrization giúp tránh nối String trước khi check level, nhưng **không hoãn biểu thức tính toán đắt** được truyền làm argument:

```java
logger.debug("state={}", expensiveSnapshot()); // expensiveSnapshot() vẫn chạy
```

Nếu cần tránh tính toán, cân nhắc:

```java
if (logger.isDebugEnabled()) {
    logger.debug("state={}", expensiveSnapshot());
}
```

Các đoạn SLF4J trên **không phải chương trình độc lập**; cần logger/dependency. Với SLF4J 2.x, fluent API có thể hỗ trợ supplier qua overload thích hợp, nhưng phải kiểm đúng phiên bản/provider và semantics:

```java
logger.atDebug()
      .addArgument(() -> expensiveSnapshot())
      .log("state={}");
```

Không kết luận mọi API logging đều lazy chỉ vì message có placeholder. Ngoài ra, logging một object qua `toString()` có thể tạo IO hoặc đọc dữ liệu nhạy cảm; không đưa object nguyên vẹn vào INFO mặc định.

## 6. Hệ quả thứ ba: chi phí vận chuyển, lưu trữ và truy vấn

Giả sử một Java API phục vụ **2.000 request/giây**, một request tạo trung bình **6 dòng INFO**, mỗi dòng sau serialize khoảng **400 byte**.

```text
events_per_second = 2.000 × 6 = 12.000 events/s
bytes_per_second  = 12.000 × 400 = 4.800.000 B/s
                  ≈ 4,8 MB/s (decimal)
bytes_per_day     = 4.800.000 × 86.400
                  = 414.720.000.000 B
                  ≈ 414,72 GB/ngày (decimal)
```

Nếu thiết kế lại còn **một completion event/request** cùng kích thước trung bình 400 byte:

```text
events_per_second = 2.000
bytes_per_day     = 2.000 × 400 × 86.400
                  = 69.120.000.000 B
                  ≈ 69,12 GB/ngày
reduction         ≈ 345,60 GB/ngày
```

Đây là ví dụ **ước lượng số byte thô**, chưa gồm index, metadata, replication, compression, retention tier, network overhead, retries hay log của các thành phần khác. Tỷ lệ giảm này không phải cam kết; khi thay đổi schema/format, kích thước event có thể thay đổi.

Chi phí tăng không chỉ ở “phí ingest”: log volume lớn làm tăng file rotation, thời gian Collector parse, queue depth, khả năng bị backend throttling, chi phí query và lưu trữ lâu dài. Một điều đáng lo là log quan trọng có thể bị **mất do hệ thống bảo vệ quá tải**, đúng lúc incident xảy ra.

Bài học không phải loại bỏ mọi INFO để tiết kiệm. Hãy ưu tiên **giảm event không có mục đích và payload thừa**, giữ những mốc dùng được, tối ưu pipeline có quan sát và đánh giá tổng chi phí.

## 7. Hệ quả thứ tư: lộ dữ liệu nhạy cảm và rủi ro bảo mật

INFO thường được bật trên production lâu dài và gửi vào hệ thống tập trung có nhiều người hoặc dịch vụ truy cập. Nếu dùng INFO để dump mọi thứ, rất dễ ghi:

- Password, token, API key, cookie, authorization header hoặc connection string chứa credential.
- Request/response body có PII, thông tin thanh toán, hồ sơ cá nhân.
- Raw URL/query string chứa signed links, email hoặc temporary code.
- Full SQL query kèm giá trị tham số nhạy cảm.
- Toàn bộ object Java có `toString()` chứa secret field.
- Thông tin tenant/resource không cần thiết cho mục tiêu điều tra.

**Đổi INFO sang DEBUG không phải biện pháp bảo mật.** DEBUG có thể được bật khi incident, và dữ liệu vẫn có thể đi qua console/file/Collector. Phải thiết kế **data minimization tại call site**, structured allowlist, redaction và quyền truy cập cho mọi level. Với audit, không ghi plaintext secret trong before/after state.

Đầu vào không đáng tin có thể chứa newline/CR hoặc ký tự điều khiển gây **log injection** nếu nối trực tiếp vào text line. JSON encoder được kiểm chứng giúp escape record boundaries, nhưng không xác minh các trường actor/outcome do client tự gửi. Tách metadata hệ thống tin cậy khỏi trường do user cung cấp.

## 8. Hệ quả thứ năm: làm sai ngữ nghĩa metric và alert

Nếu hệ thống đặt alert `count(severity=INFO) > N`, mỗi lần phát hành thêm một log statement có thể làm alert tăng mà không liên quan sự cố. Tương tự:

- **Số dòng INFO ≠ số request.** Một request tạo nhiều logs, request khác không có do filter/sampling.
- **Số dòng ERROR ≠ failed request count.** Một request có nhiều retry hoặc exception được log nhiều tầng.
- **Log được exporter gửi lại** có thể tạo bản sao, làm số dòng tăng dù ứng dụng không hoạt động nhiều hơn.
- **Log volume giảm** có thể do ứng dụng ít traffic, do logging bị tắt hoặc do pipeline drop — không thể khẳng định hệ thống khỏe chỉ từ biểu đồ log count.

Metric SLI như request success/error rate, latency và throughput nên được instrument tại boundary với định nghĩa rõ, không suy ra bằng cách đếm message tự do. Nếu dùng log-derived metrics, phải thiết kế event name, unique event ID, level/sampling policy, dedup và error handling minh bạch.

### Đừng biến INFO thành nguồn sự thật của audit

Sự kiện audit có thể phải giữ ngay cả khi INFO root level bị thay đổi, agent lỗi hoặc pipeline sampling. Với thao tác như cấp quyền/quản trị, cần audit event schema và lưu bền theo hợp đồng, có thể dùng outbox hay audit store riêng. Một `logger.info("role changed")` thường **không cung cấp tính nguyên tử giữa DB commit và audit record**.

## 9. Chọn đúng mức độ quan sát: log, metric hay trace?

| Thông tin cần biết | Nguồn thích hợp | Ví dụ |
| --- | --- | --- |
| Request thành công/thất bại, latency, số lượng | Metrics HTTP và completion log theo policy | `http.server.request.duration`, status 503 |
| Một operation nghiệp vụ quan trọng đã đổi trạng thái | INFO business event hoặc audit route nếu bắt buộc | `order.accepted`, `role.revoked` |
| Một dependency retry nhưng cuối cùng recovered | WARN event + metric retries/fallback | `dependency.retry` |
| Giá trị biến ở một branch khi debug | DEBUG/TRACE có kiểm soát, không chứa secret | `validation.rule.chosen` |
| Luồng qua nhiều services/spans và thời lượng | Distributed trace + correlation | `trace_id`, span name/duration |
| Tần suất lỗi theo service/route/error code | Counter/histogram, có tags hữu hạn | `requests_failed_total` |
| Bằng chứng bắt buộc theo nghiệp vụ | Audit event + durable store/outbox | `access.policy.changed` |
| Tình trạng log pipeline | Self-metrics và canary | Queue depth, dropped events, ingest lag |

**Một event không phải lúc nào chỉ thuộc một tín hiệu.** Có thể dùng completion log và request duration metric song song, nhưng phải hiểu chúng cùng mô tả **một request ở hai đơn vị quan sát khác nhau**. Metrics dùng dimensions hữu hạn; request ID/trace ID thích hợp trong log/trace, không làm metric labels để tránh cardinality cao.

## 10. Thiết kế chính sách INFO có chủ đích

Thay câu “để hết ở INFO cho dễ xem” bằng một **event catalog**.

| Event | Có nên ghi INFO? | Trường nên có | Lý do |
| --- | --- | --- | --- |
| `service.started` | Thường có | service, version, environment, config profile an toàn | Mốc vận hành hiếm |
| `http.request.completed` | Có nếu access log policy yêu cầu | method, matched route, status, duration, request ID | Một event/request được dự toán |
| `batch.completed` | Có | job ID, processed count, failed count, elapsed | Tổng kết một batch thay vì mỗi item |
| `order.accepted` | Tùy nghiệp vụ | event ID, order ID nội bộ hợp lệ, outcome | Mốc nghiệp vụ cần đối chiếu |
| `repository.query.started` | Thường không | DEBUG/TRACE hoặc metric DB | Tần suất cao và ít ý nghĩa trực tiếp |
| `loop.item.processed` | Thường không | DEBUG chọn lọc hoặc tổng hợp | Tránh hàng triệu events |
| `dependency.retry` | WARN khi bất thường | dependency, attempt, reason, request ID | Thể hiện suy giảm |
| `request.failed` | ERROR nếu thất bại thật | error code, route, request ID, exception type | Hỗ trợ điều tra final failure |
| `authz.access.denied` | Security/audit tùy policy | actor đã xác minh, resource, reason | Không chỉ dựa vào mức INFO |
| `credential.rotated` | Audit route riêng | key identifier, actor, outcome | Không ghi secret và không mặc định sampling |

**Danh sách này không phải luật cứng.** Một hệ thống yêu cầu access logging đầy đủ có thể ghi INFO ở mỗi HTTP request; batch processing có thể phải audit từng item; security policy có thể yêu cầu giữ mọi denied event. Cần xác định yêu cầu, khối lượng, retention, người dùng dữ liệu và ranh giới tin cậy trước khi chọn.

### Một contract cho event INFO

Một log INFO quan trọng nên trả lời:

- **Điều gì xảy ra?** `event.name` ổn định, outcome.
- **Ở đâu?** `service.name`, environment, instance/version khi có ích.
- **Khi nào?** timestamp có timezone/UTC và phân biệt ingest time.
- **Đối tượng nào?** ID nội bộ chỉ khi cần và theo chính sách bảo mật.
- **Liên quan request nào?** `request_id`/`trace_id`/`span_id` khi tồn tại.
- **Mức ảnh hưởng?** status/error code/duration/count nếu là completion event.
- **Có cách tìm lại không?** JSON schema, encoder/parser, retention và quyền search.

Tránh dùng INFO message không có danh mục như `"Step 7 done"`: sau refactor bước 7 đổi nghĩa thì dashboard/saved search có thể hỏng. Event name cần ổn định; message có thể thay đổi để thân thiện với người đọc.

## 11. Ví dụ Java 17 chạy độc lập: INFO có ý nghĩa, FINE có kiểm soát, supplier lazy

Ví dụ này chỉ dùng **JDK 17**, không cần Maven, SLF4J hay Spring Boot. Nó minh họa ba điều:

1. `INFO`, `WARNING` và `SEVERE` có ngữ nghĩa riêng và vẫn in khi logger đang ở ngưỡng INFO.
2. Chuỗi nối tham số đắt **được tính dù `FINE` đang tắt**, trong khi message qua `Supplier<String>` của JUL được hoãn.
3. Khi tạm bật FINE, chỉ những diagnostic events được chọn mới xuất hiện; không cần chuyển mọi câu chuyện chi tiết lên INFO.

Tạo file **`LoggingInfoAntipatternDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingInfoAntipatternDemo {
    private static final Logger LOG =
            Logger.getLogger("example.logging.levels");

    private static String buildDiagnostic(AtomicInteger calls) {
        calls.incrementAndGet();
        // Trong ứng dụng thật có thể rất tốn CPU hoặc cấp phát.
        return "details=redacted-summary";
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(
                            record.getLevel().getName()
                            + " " + record.getMessage());
                }
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };
        sink.setLevel(Level.ALL);
        LOG.addHandler(sink);

        AtomicInteger eager = new AtomicInteger();
        AtomicInteger lazy = new AtomicInteger();

        try {
            // Không in vì FINE tắt, nhưng buildDiagnostic vẫn chạy!
            LOG.fine("event=payment.detail "
                    + buildDiagnostic(eager));

            // Không in và không gọi buildDiagnostic khi FINE tắt.
            LOG.log(Level.FINE, () ->
                    "event=payment.detail " + buildDiagnostic(lazy));

            // Các mốc có nghĩa vận hành vẫn được ghi rõ level.
            LOG.info("event=order.accepted order_id=42");
            LOG.warning(
                    "event=payment.retry attempt=1 reason=TIMEOUT");
            LOG.severe(
                    "event=payment.failed reason=TIMEOUT");

            // Bật FINE có kiểm soát để lấy một diagnostic event.
            LOG.setLevel(Level.FINE);
            LOG.log(Level.FINE, () ->
                    "event=payment.detail " + buildDiagnostic(lazy));

            System.out.printf(
                    "COUNTS eager_calls=%d lazy_calls=%d%n",
                    eager.get(), lazy.get());
        } finally {
            LOG.removeHandler(sink);
            sink.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac LoggingInfoAntipatternDemo.java
java LoggingInfoAntipatternDemo
```

**Stdout chính xác:**

```text
INFO event=order.accepted order_id=42
WARNING event=payment.retry attempt=1 reason=TIMEOUT
SEVERE event=payment.failed reason=TIMEOUT
FINE event=payment.detail details=redacted-summary
COUNTS eager_calls=1 lazy_calls=1
```

Diễn giải:

- Ban đầu `LOG.setLevel(Level.INFO)` tắt các record `FINE`. Dòng `LOG.fine("..." + buildDiagnostic(eager))` không được publish nhưng **hàm vẫn gọi một lần**, nên `eager_calls=1`.
- `LOG.log(Level.FINE, () -> ...)` chỉ đánh giá supplier khi record được cho phép. Lần đầu ở INFO bị bỏ, nên `lazy` chưa tăng.
- `INFO` giữ mốc thành công cần theo dõi, `WARNING` ghi retry/suy giảm, `SEVERE` ghi thất bại. Ví dụ có cả WARN và ERROR để minh họa taxonomy; trong một operation thực có thể không nên ghi lỗi cuối nếu retry đã hồi phục.
- `LOG.setLevel(Level.FINE)` bật diagnostic tạm; lần supplier thứ hai được gọi đúng một lần và in một dòng FINE.
- `Handler` tùy biến loại bỏ timestamp/layout mặc định để output xác định. `LOG.setUseParentHandlers(false)` tránh parent handlers in thêm bản sao ra stderr.
- Các counter trong ví dụ chỉ dùng để kiểm chi phí *đánh giá tham số* chứ không đo CPU/GC/I/O thật. Muốn benchmark độ trễ/throughput cần JMH/profiling và stack sản xuất tương ứng.

**Giới hạn:** đây là ví dụ JUL chạy tuần tự với log message text. Nó chưa có HTTP server, JSON encoder, async queue, MDC, audit storage hoặc distributed tracing. Trong ứng dụng có nhiều thread, đổi logger level toàn cục sẽ ảnh hưởng mọi thread cùng dùng logger; production nên có policy/config/TTL/permission cho việc bật DEBUG/FINE, thay vì toggle tùy tiện từ một request.

## 12. JUL, SLF4J, Logback, Log4j2 và Spring Boot: cấu hình level

### JUL

Một thiết lập Java đơn giản:

```java
Logger logger = Logger.getLogger("com.example.orders");
logger.setLevel(Level.INFO);  // Cho phép INFO, WARNING, SEVERE.
logger.fine("Low-level detail");
logger.info("Order accepted");
```

Đoạn này **không độc lập** nếu chưa import/context; nơi ghi còn phụ thuộc `Handler`, level trên handler và cấu hình `LogManager`. Trong JUL, event chỉ thực sự ra output khi vượt qua **lọc ở logger và handler**. Việc đổi logger level không đủ nếu handler vẫn lọc `FINE`. Có thể dùng file cấu hình JUL theo ứng dụng, nhưng tên option cần kiểm cùng runtime.

### SLF4J

SLF4J là **facade**, không phải nơi lưu log. Một provider/backend tương thích như Logback hoặc Log4j2 thực hiện filter, encoder và appenders. Với SLF4J:

```java
logger.debug("event=order.validation rule={}", ruleName);
logger.info("event=order.accepted orderId={}", orderId);
logger.warn("event=payment.retry attempt={}", attempt);
logger.error("event=order.failed code={}", errorCode, throwable);
```

Đây là **đoạn minh họa**, không chạy độc lập vì cần logger, biến context và dependency SLF4J. Mức INFO không cần chứa full exception stack cho mọi retry; `ERROR` có `Throwable` nên được dùng khi failure có ý nghĩa và được quan sát tại một boundary phù hợp.

### Logback

Cấu hình level minh họa (giả định ứng dụng **đã có appender**):

```xml
<configuration>
    <!-- Chỉ nhóm code cần điều tra tạm dùng DEBUG. -->
    <logger name="com.example.payment" level="DEBUG"/>

    <!-- Root của những nhóm còn lại vẫn INFO. -->
    <root level="INFO"/>
</configuration>
```

Đây chỉ là **mảnh cấu hình biểu đạt level**, không là file Logback đầy đủ bảo đảm log xuất ra: cần cấu hình appender/encoder và gắn appender-ref phù hợp. Nếu appender cũng có ThresholdFilter hoặc root/child additivity gây log trùng, phải kiểm pipeline thực tế.

Log4j2 có cấu trúc configuration/logger/appender riêng; không chép XML Logback rồi mong Log4j2 hiểu giống nhau.

### Spring Boot

Spring Boot thường cho phép khai báo log level theo package (khi stack hỗ trợ):

```properties
logging.level.root=INFO
logging.level.com.example.payment=DEBUG
```

Đây là **một mảnh `application.properties`**, không phải ứng dụng Spring Boot hoàn chỉnh. Việc thay đổi level runtime qua Actuator hay giao diện quản trị phụ thuộc dependency, endpoint exposure, phiên bản và cơ chế xác thực; không để endpoint đổi level mở công khai. Nếu bật DEBUG ở production, nên có **owner, phạm vi package, TTL/giới hạn thời gian, giám sát volume và quy trình tắt lại**.

### Chọn thay đổi mức log theo phạm vi

Ưu tiên bật DEBUG cho namespace `com.example.payment` thay vì đổi toàn hệ thống `root=DEBUG`. Thêm request/trace correlation, metrics và tracing thường cung cấp dữ liệu điều tra mà không cần mọi package phát nhiều dòng thông thường ở INFO.

Không hardcode secret trong configuration file hoặc log level change events. Thay đổi log level cũng nên có audit hoặc change tracking phù hợp nếu nó ảnh hưởng chi phí và privacy.

## 13. Làm ít log nhưng “giàu thông tin”

Một event thông tin tốt không đồng nghĩa event dài. Ví dụ access completion:

```json
{
  "timestamp": "2026-01-01T00:00:01Z",
  "severity": "INFO",
  "event.name": "http.request.completed",
  "service.name": "orders-api",
  "deployment.environment.name": "prod",
  "http.method": "POST",
  "http.route": "/api/orders",
  "http.status_code": 201,
  "duration_ms": 34.5,
  "request_id": "req-101",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Đây là schema **minh họa**, không phải payload được tất cả SDK/Collector sinh tự động. Tên attribute trong OpenTelemetry HTTP semantic conventions và mapping backend có thể khác theo phiên bản; cấu hình phải được kiểm cùng runtime đang dùng.

So với mười dòng INFO “enter/exit”, completion event này dễ lọc theo route, status, duration và request ID. Với một request có lỗi, có thể thêm `error.code` và `exception.type`, còn message/stack trace được tạo riêng theo policy.

Một structured event nên có:

- **event name** và schema version ổn định nếu nhiều hệ thống đọc nó.
- Timestamp rõ UTC/offset, service, environment, version và instance khi cần.
- Outcome, status/error code, duration/count với đơn vị xác định.
- Request/trace ID cho correlation, không làm metric labels.
- Những trường có nguồn đáng tin và không chứa secrets.
- Độ lớn được giới hạn để tránh làm parser/ingester hoặc storage quá tải.

**Không dùng raw exception message, raw URL, user ID hay request ID làm metric labels.** Cardinality metric sẽ tăng cực lớn; correlation thuộc log/traces với quyền truy cập thích hợp.

## 14. Khi nào aggregate thay vì INFO từng event?

Nhiều đoạn code ghi INFO trong loop:

```java
for (Order order : orders) {
    logger.info("Processed order {}", order.id());
}
```

Đây là đoạn **SLF4J minh họa**, không chạy độc lập; cần `orders`/`Order`/`logger`. Nếu có một triệu phần tử, việc tạo một triệu dòng INFO có thể không hữu ích. Hướng thay thế:

- Đếm tổng processed/failed/skipped, thời gian chạy và ghi **một summary event** khi batch hoàn tất.
- Dùng metric counter/timer để đo tiến độ, throughput và failure rate.
- Nếu cần kiểm toán từng item, ghi **audit/business event** có hợp đồng lưu bền, không đơn thuần INFO.
- Khi cần truy ID cụ thể để debug, bật diagnostic có kiểm soát theo job/request ID hoặc dùng query từ dữ liệu nghiệp vụ, không tự ghi PII hàng loạt.
- Với long-running job, ghi **periodic checkpoint** theo thời gian/khối lượng đã định, không mỗi item.
- Nếu cần debug một tỷ lệ nhỏ, sampling có policy và lưu tỷ lệ mẫu, tránh dùng dữ liệu đã sampling để chứng minh tổng số đầy đủ.

Không aggregation quá mức làm mất thông tin bắt buộc. Ví dụ một thao tác chuyển tiền phải lưu được từng transaction theo policy sẽ không thể thay bằng một dòng “đã xử lý 1.000 giao dịch”.

## 15. Sampling, rate limiting và chính sách khi log quá nhiều

Thay INFO chi tiết bằng DEBUG không tự loại mọi rủi ro: DEBUG có thể được bật và tạo burst khổng lồ. Có thể dùng:

| Kỹ thuật | Tác dụng | Rủi ro cần quản lý |
| --- | --- | --- |
| **Level filtering** | Chỉ bật mức phù hợp, tắt detail mặc định | Bỏ lỡ ngữ cảnh nếu lỗi chưa có event chính |
| **Dynamic level theo phạm vi** | Bật DEBUG cho package/service trong cửa sổ ngắn | Tăng volume/PII khi bật rộng hoặc không tắt |
| **Sampling log chẩn đoán** | Giữ tỷ lệ nhỏ events cùng loại | Không dùng cho audit bắt buộc; tránh bias |
| **Rate limiting** | Chặn spam log của loop/lỗi lặp | Có thể mất số liệu nếu không có suppressed count |
| **Aggregation** | Tóm tắt N events thành counters/summary | Mất chi tiết từng event |
| **Dedup/suppression** | Tránh in lặp cùng lỗi trong burst | Phải giữ first/last, count và scope |
| **Bounded async queue** | Tách tốc độ request khỏi tốc độ output | Queue đầy gây block/drop tùy policy |
| **Payload limit/redaction** | Giảm event size và nguy cơ lộ dữ liệu | Có thể cắt stack/context hữu ích |

Khi sampling, phải định nghĩa **đơn vị lấy mẫu**: per-request, per-event, per-error code hay per-trace. Sampling độc lập từng dòng có thể khiến timeline của request thiếu các bước bất kỳ; sampling nhất quán theo trace/request thường hữu ích hơn khi mục tiêu là dựng một luồng xử lý, nhưng có trade-off riêng.

Quan trọng: **không biến sampling thành cách che sự cố**. Metric request/error nên đo ở boundary với semantics riêng; counter `logs_dropped_total`, queue depth, oldest event age và exporter retries cần được quan sát độc lập.

### Rate limit WARN/ERROR có nên không?

Đôi khi một lỗi cấu hình có thể phát hàng triệu ERROR/giây và làm log backend quá tải. Có thể giới hạn message lặp với **suppressed count** và alert dựa trên metric, nhưng phải biết rule nào bắt buộc giữ từng event (như audit). Mất toàn bộ dấu vết trong lúc incident còn tệ hơn giảm log theo policy có chủ đích.

Thay vì tắt mọi ERROR, thiết kế event summary:

```text
ERROR event=dependency.failed code=DB_UNAVAILABLE first_seen=... 
WARN event=dependency.failures_suppressed count=12000 interval=60s
```

Đây là dữ liệu minh họa; thống kê suppressed phải đến từ counter chính xác, không đo lại bằng số dòng log đã giữ.

## 16. Tránh log trùng tại nhiều tầng

Một request lỗi có thể đi qua DAO → Service → Controller. Anti-pattern thường đi cùng “INFO ở mọi bước” là **log rồi ném lại cùng exception**:

```java
try {
    repository.save(order);
} catch (RuntimeException ex) {
    logger.error("Repository failed", ex);
    throw ex;
}
```

Đây là fragment minh họa, không chạy độc lập vì cần `repository`/`order`/`logger`. Nếu service và controller cũng ghi ERROR stack trace rồi rethrow, backend có thể nhận ba error logs cho **một request lỗi**.

Cách cải thiện:

1. Chọn một **boundary** chịu trách nhiệm log lỗi cuối có đầy đủ service/route/request ID/outcome.
2. Tầng thấp có thể tạo diagnostic event khác loại hoặc thêm context vào exception, không bắt buộc in nguyên stack.
3. Nếu attempt thất bại nhưng retry thành công, ghi WARN/metric retries và final success rõ ràng.
4. Dùng metric riêng cho downstream attempt errors và HTTP failed requests; không cộng hai số thành “failed requests”.
5. Nếu cần log nhiều event thực, đặt `event.name` khác nhau và ghi `event_id` logic để query/dedup transport retries.

**Một request ID không phải event ID.** Một request có thể có nhiều event hợp lệ. Dedup cùng transport event cần khóa riêng; không gộp mọi dòng cùng request ID và coi là một.

## 17. Logging trong Servlet, Spring MVC và async Java

Web app thường có nhiều chỗ có thể ghi log:

```text
Gateway -> Servlet Filter -> Security Filter
        -> Controller -> Service -> Repository
        -> Exception Handler -> Response
```

Nếu mỗi layer ghi `INFO "request arrived"` và `INFO "request completed"`, một HTTP call có thể tạo nhiều completion-like records. Nên thống nhất:

- Chọn một nơi ghi **HTTP completion event**, dùng status thực tế và duration ở giai đoạn request hoàn tất.
- **404, 401, 403 và exception trước controller** cũng cần được quan sát theo access/security policy; nếu chỉ log ở controller có thể bỏ sót.
- Với async Servlet/WebFlux, controller return không luôn là response completion; dùng lifecycle hook đúng framework để tránh log sớm/trùng.
- Dùng `http.route` từ framework matched route, không lấy raw URL có token/ID làm metric label.
- Context propagation/MDC/ThreadContext phải đi theo request qua `ExecutorService`, `CompletableFuture` hay reactive pipeline; khôi phục/xóa context khi thread được tái sử dụng.

SLF4J MDC có thể giúp thêm `request_id`/`trace_id` vào record, nhưng **MDC không tự bảo đảm propagation qua mọi task**. Không log raw headers, request body hoặc query string chỉ để “đủ thông tin INFO”.

### Async logging và rủi ro khi queue đầy

Async appender giúp giảm blocking trong nhiều tình huống, nhưng vẫn có chi phí encode, allocation, queue, copy context và disk/network. Khi queue đầy, một số cấu hình block request, một số drop các level ưu tiên thấp hoặc fallback sync; tùy framework và phiên bản. Do đó, bật async **không giải quyết gốc rễ** của anti-pattern quá nhiều INFO.

Cần giám sát `logs_dropped_total`, queue usage, exporter errors và latency tác động lên business requests. Không nói “async chắc chắn nhanh hơn” nếu chưa benchmark trong workload và failure modes thật.

## 18. Khi incident: bật DEBUG tạm thay vì INFO tràn lan

Một quy trình điều tra có kiểm soát:

1. **Xem SLI/metric trước:** service nào có lỗi, route nào, phiên bản nào, thời gian nào.
2. **Xem INFO/ERROR có cấu trúc:** request completion, error code, correlation, outcome, retry.
3. **Chọn phạm vi DEBUG:** package/class/service cần điều tra, có thể chọn instance và thời hạn ngắn.
4. **Phê duyệt theo quyền:** người vận hành có quyền đổi log level; không để endpoint quản trị không xác thực.
5. **Đánh giá data risk:** DEBUG mới có ghi token, PII hoặc payload nội bộ không? Nếu có, sửa call site trước.
6. **Giới hạn volume:** quan sát queue/disk/backend ingest, có ngưỡng rollback.
7. **Dựng timeline:** theo `request_id`/`trace_id`, kết hợp trace spans và metric.
8. **Tắt level chi tiết và ghi nhận:** trở về cấu hình an toàn, lưu query/incident notes và đánh giá thêm event catalog nếu thiếu bằng chứng.

Nếu thường xuyên phải bật DEBUG để trả lời một câu hỏi cố định, có thể thiếu **một event INFO/ERROR có nghĩa** hoặc thiếu metric/trace; không nên giữ DEBUG bật toàn thời gian.

## 19. Kiểm thử và đánh giá chất lượng INFO logging

### Unit tests và code review

| Kịch bản | Điều cần kiểm |
| --- | --- |
| INFO khi service khởi động | Một event có version/environment, không có secret |
| Request thành công | Completion event theo policy, không lặp INFO ở nhiều layer |
| Request thất bại | ERROR tại final boundary, error code và request/trace ID đúng |
| Attempt lỗi rồi retry thành công | WARN/retry metric, final request không bị ghi FAILED |
| Level INFO và FINE/DEBUG disabled | Không tạo diagnostic event; supplier/guard không tính payload đắt |
| Bật DEBUG cho một package | Chỉ chi tiết được chọn xuất, không mở toàn root ngoài yêu cầu |
| Message chứa newline/quote | JSON Lines vẫn hợp lệ, không bị log injection |
| Dữ liệu chứa token/PII | Không xuất vào INFO, DEBUG, stack trace, MDC hay sink |
| Async request/thread pool | Correlation không lẫn request, cleanup đúng |
| Logger/appender cấu hình sai | Có health signals để phát hiện missing logs |
| Backend 429/503 hoặc queue full | Backpressure/drop theo chính sách, app ổn định trong giới hạn |
| Audit event bắt buộc | Không bị mất vì level filtering/sampling INFO |
| Deployment thay log level | Dashboard và saved searches không dựa vào text mong manh |

Với Java 17 demo bên trên, test nội dung phải thấy chính xác **3 dòng severity**, **1 dòng FINE sau khi bật**, và counter `eager_calls=1, lazy_calls=1`. Khi chuyển sang SLF4J/Logback trong ứng dụng thật, cần unit/integration test backend và encoder, không suy diễn JUL handler tương đương hoàn toàn.

### Đo lường hiệu năng

Dùng benchmark đại diện với JMH khi so sánh eager vs lazy logging; có thể quan sát allocations/op, throughput, p95/p99 latency của request, GC pauses, log bytes/s và queue backlog. Cần kiểm cả log enabled và disabled, payload nhỏ/lớn, nhiều thread và failure scenarios.

**Không benchmark bằng một lần gọi `System.nanoTime()` rồi kết luận** chi phí của framework. Warmup, JIT, constant folding, GC và sink I/O khiến đo thủ công rất dễ sai. Với pipeline log thật, bottleneck có thể ở JSON encoder, disk fsync, Collector hoặc cloud ingest chứ không ở việc gọi `logger.info`.

## 20. Những anti-pattern liên quan

| Sai lầm | Tác động | Hướng sửa |
| --- | --- | --- |
| Mọi method đều ghi INFO enter/exit | Nhiễu, tốn storage | TRACE/DEBUG có kiểm soát, tracing |
| Log INFO mỗi vòng lặp/item | Chi phí tỷ lệ số item | Aggregate + metrics/batch summary |
| Dump toàn bộ object ở INFO | CPU/GC, dữ liệu nhạy cảm | Field allowlist và lazy formatting |
| Nối String trước khi logger kiểm level | Tính toán thừa khi level tắt | Supplier/guard, parameterized API thích hợp |
| Coi mọi exception là ERROR | Recovered attempts thành “lỗi cuối” | Severity theo outcome; attempt vs request |
| Ghi cùng stack trace ở mọi tầng | Duplicate records, alert nhiễu | Log tại boundary chịu trách nhiệm |
| Chỉ có INFO, không có error code/event name | Search khó, dashboard dựa text | Structured events, taxonomy |
| Root DEBUG bật vĩnh viễn để “đủ dữ liệu” | Volume và nguy cơ PII | Bật theo package, scope/TTL, giám sát |
| Sampling tất cả INFO kể cả audit | Mất event bắt buộc | Kênh audit riêng, retention/durability |
| Giảm INFO mà bỏ cả completion events cần thiết | Blind spot trong incident | Giữ mốc quan trọng và metric/trace |
| Dùng user ID/request ID làm metric labels | Cardinality tăng vô hạn | Dùng chúng trong log/trace |
| Không giám sát pipeline sau thay đổi level | Tưởng yên ắng là khỏe | Self-metrics, heartbeat, canary |
| INFO với raw URL và query | Lộ token/PII và tạo nhiều giá trị | Matched route và data minimization |
| Dùng console INFO count làm business KPI | Lệch do duplicate/filter/sampling | Instrument counter tại business boundary |

## 21. Checklist chuyển từ “log mọi thứ ở INFO” sang logging có mục đích

- [ ] Đã liệt kê những event cần người vận hành tìm được trong production?
- [ ] INFO dành cho milestones/completion/summary có ý nghĩa, có dự toán tần suất?
- [ ] DEBUG/TRACE dành cho chi tiết nội bộ; có cơ chế bật đúng package và giới hạn thời gian?
- [ ] WARN/ERROR phản ánh recoverable vs final failure, không chỉ loại `Throwable`?
- [ ] Có một owner cho request completion và exception logging, tránh log trùng vô nghĩa?
- [ ] Có `event.name`, outcome, error code, service, route, duration và correlation fields khi cần?
- [ ] Không ghi secret/PII/raw token hoặc dump toàn bộ object ở bất kỳ level nào?
- [ ] Những phép tính đắt trong log disabled dùng supplier/guard đúng API phiên bản?
- [ ] Loop/batch high-frequency log được tổng hợp hoặc chuyển thành metrics khi phù hợp?
- [ ] Sampling/rate limits có chính sách rõ và không vi phạm yêu cầu audit bắt buộc?
- [ ] Metrics là SLI có ngữ nghĩa riêng, không dựa vào số dòng INFO/ERROR?
- [ ] Dùng structured JSON encoder và kiểm search/index ở log backend?
- [ ] Đã đo log bytes/s, allocations/GC, queue/drop, backend ingest/cost trước và sau thay đổi?
- [ ] Có unit/integration tests cho log level filtering, duplicate, retry/recovery, async context và privacy?
- [ ] Có canary/self-metrics để phát hiện logging pipeline im lặng hoặc mất log khi sự cố xảy ra?

**Kết luận:** `INFO` không phải “thùng chứa cho mọi điều muốn ghi”, mà là **mức cho những sự kiện vận hành bình thường cần được giữ và tìm thấy**. Dùng DEBUG/TRACE cho chi tiết, WARN cho suy giảm có thể phục hồi, ERROR cho thất bại cuối theo contract, và audit route riêng nếu cần lưu bền. Chọn đúng event, dùng structured fields/correlation, tránh tạo message đắt khi level tắt và quan sát chi phí/dữ liệu nhạy cảm giúp Java logging **ít nhiễu hơn nhưng hữu ích hơn trong sự cố**.
