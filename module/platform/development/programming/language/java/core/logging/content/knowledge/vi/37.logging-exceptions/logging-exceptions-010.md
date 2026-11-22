# Đối chiếu exception với metric trong Java Core Logging

## 1. Vấn đề: vì sao số exception trong log khác số lỗi trên dashboard?

Trong ứng dụng Java, **exception**, **log event**, **metric measurement** và **trace/span event** có quan hệ với nhau nhưng không phải cùng một đơn vị đếm. Một HTTP request có thể ném exception nhiều lần, được retry rồi trả về thành công. Ngược lại, một request có thể trả 400 vì validation thất bại mà không ném exception nào. Vì vậy, câu hỏi “vì sao có 300 ERROR logs nhưng chỉ 80 failed requests?” không thể trả lời bằng cách đếm số dòng log.

Để đối chiếu chính xác phải xác định:

1. **Đối tượng đếm:** attempt, downstream call, business operation, HTTP request hay background job.
2. **Điểm ghi nhận:** khi exception được bắt, khi bắt đầu retry, khi request hoàn tất hay khi exporter nhận event.
3. **Kết quả:** tạm lỗi rồi hồi phục, thất bại cuối cùng, bị hủy, validation reject hay suy giảm chất lượng dịch vụ.
4. **Thời gian và phạm vi:** service, environment, operation, route, cửa sổ thời gian, đồng hồ và ingest delay.
5. **Điều kiện quan sát:** level filtering, sampling, duplicate log, async queue, metric scrape/export và lỗi collector.

Ví dụ: `POST /api/payments` gọi payment provider. Attempt đầu bị `SocketTimeoutException`, retry thành công. Một WARN log và một metric `dependency.exceptions` có thể xuất hiện, còn metric `http.requests.failed` phải bằng **0 cho request này** nếu kết quả HTTP cuối cùng thành công. Việc cả hai con số khác nhau là đúng về mặt ngữ nghĩa.

Một nguyên tắc cốt lõi: **log giải thích chuyện gì đã xảy ra; metric cho biết tần suất, phân bố và mức tác động; trace nối các bước của một luồng xử lý.** Không ép số dòng log, số Throwable và số request lỗi bằng nhau.

## 2. Những số đếm cần phân biệt

| Đại lượng | Đơn vị | Thời điểm ghi nhận |
| --- | --- | --- |
| `requests_total` | Request logic của service tại một entry point | Một lần khi request được ghi nhận theo lifecycle định nghĩa |
| `requests_failed_total` | Request kết thúc với outcome được định nghĩa là failure | Một lần **khi final outcome được xác định** |
| `exception_attempts_total` | Exception quan sát ở ranh giới của một attempt | Mỗi lần attempt thất bại, kể cả sau đó recovered |
| `retries_total` | Lần retry thực sự được bắt đầu | Không tính attempt đầu |
| `recovered_requests_total` | Request lỗi ít nhất một attempt nhưng cuối cùng thành công | Một lần tại completion |
| `fallbacks_total` | Lần dùng fallback theo contract | Khi fallback thật sự được thực thi |
| `http_request_duration` | Observation duration cho request | Khi request hoàn tất, tính theo lifecycle đúng |
| Exception log | Một log event về lỗi | Theo policy của logger/backend và mức severity |
| Span exception event | Dữ liệu lỗi gắn vào một span | Theo instrumentation/tracing sampling |

Những tên metric ở đây là **minh họa**, không phải tên mặc định của JDK, Micrometer, OpenTelemetry hoặc Prometheus. Framework có thể xuất metric HTTP theo tên và đơn vị khác; phải xem contract thực tế.

Phân biệt ba mức lỗi rất quan trọng:

- **Attempt failure:** một lần gọi tới DB/downstream hoặc một bước retry thất bại.
- **Operation failure:** nghiệp vụ hoặc job logic thất bại sau các cơ chế retry/fallback.
- **HTTP request failure:** response cuối phù hợp định nghĩa lỗi HTTP, thường phân biệt rõ 4xx và 5xx.

Ví dụ một request có 3 lần gọi downstream thất bại rồi fallback thành công có thể có 3 attempt failures, 1 fallback, 0 failed HTTP requests. Nếu dùng cùng tên `errors_total` cho cả ba tầng, dashboard sẽ không thể diễn giải đúng.

## 3. Một request, nhiều attempt và nhiều log

```text
HTTP request req-42
      |
      +-- attempt 1 -> IOException/timeout
      |      +-- WARN log "dependency.attempt.failed"
      |      +-- exception_attempts_total += 1
      |      +-- retries_total += 1
      |
      +-- attempt 2 -> success
             |
             +-- requests_total += 1
             +-- requests_failed_total += 0
             +-- recovered_requests_total += 1
```

Cùng một request ID có thể xuất hiện trong nhiều log events: request started, downstream timeout, retry scheduled, request completed. **Không phải mỗi event là một request.** Nếu collector retry xuất lại chính log event timeout, còn có thể xuất hiện **hai bản sao** của một log event duy nhất.

Khi định nghĩa metric error rate, nên dùng cùng loại đơn vị và cùng owner:

```text
request_error_rate =
    increase(requests_failed_total within window)
    / increase(requests_total within window)

dependency_attempt_failure_rate =
    failed_dependency_attempts
    / all_dependency_attempts
```

Hai tỷ lệ trả lời hai câu hỏi khác nhau. Một service có thể có tỷ lệ dependency attempts thất bại cao nhưng lỗi HTTP thấp nhờ retry và fallback; đó là **degraded dependency** cần theo dõi riêng vì retry kéo latency và tài nguyên tăng.

## 4. Ma trận đối chiếu các tình huống thường gặp

| Trường hợp | Exception Java | Log mong đợi | Metric phù hợp |
| --- | --- | --- | --- |
| Request thành công ngay | Không | Completion log theo policy | requests +1, failed +0 |
| Attempt 1 timeout, attempt 2 thành công | Có một exception | WARN attempt lỗi có `outcome=RETRY` | attempt exception +1, retry +1, recovered +1, failed +0 |
| Hai attempt đều lỗi, trả 503 | Hai exception | WARN attempt 1, lỗi cuối với outcome FAILED | attempt exception +2, retry +1, failed request +1 |
| Validation 400 được xử lý bình thường | Có thể không có | Request completion status 400, reason code | HTTP 4xx +1; exception +0 |
| Exception được catch, fallback trả 200 | Có exception | WARN/INFO ghi rõ recovered/degraded | fallback +1, failed request +0 |
| Exception không xử lý, container trả 500 | Có exception | ERROR tại exception boundary | failed request +1; exception count tùy owner |
| Job nền lỗi sau HTTP 202 | Có trong worker | Job exception log | job failed +1, không tự đổi HTTP 202 |
| Một Throwable được wrap và rethrow nhiều lớp | Có thể nhiều Throwable objects | Tránh ghi stack trùng ở mọi lớp | Đếm attempt/operation theo boundary, không theo số catch |
| Một log event được exporter gửi lại | Không có exception mới trong nghiệp vụ | Có thể 2 bản sao cùng event ID | Không tăng business failure counter lần nữa |
| Stream bị client ngắt | Có thể `IOException` | Phân biệt client disconnect và server failure | Outcome riêng theo contract |

Một exception chỉ là **cơ chế ngôn ngữ Java**. Kết quả HTTP hay nghiệp vụ là quyết định của service. Nếu ControllerAdvice chuyển exception thành HTTP 409, metric status vẫn phải phản ánh 409, không giả định mọi exception bằng 5xx.

## 5. Thiết kế log exception có thể truy ngược từ metric

Ví dụ structured log cho một lỗi tại attempt boundary:

```json
{
  "timestamp": "2026-01-01T00:00:00Z",
  "event.name": "dependency.attempt.failed",
  "service.name": "checkout-api",
  "deployment.environment.name": "prod",
  "operation": "payment.authorize",
  "http.route": "/api/payments",
  "request_id": "req-42",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "attempt": 1,
  "exception.type": "java.net.SocketTimeoutException",
  "error.code": "DOWNSTREAM_TIMEOUT",
  "outcome": "RETRY",
  "message": "Payment provider timed out"
}
```

Đây là schema **minh họa**, không phải định dạng mặc định mà mọi cloud backend, Micrometer hay OpenTelemetry tự hiểu. Muốn query theo field, phải có JSON encoder/parser và quy tắc mapping tương ứng.

Những trường quan trọng:

1. **`event.name`** có nghĩa ổn định, phân biệt lỗi attempt với request completion.
2. **`operation` và `http.route`** cho phép lọc cùng phạm vi metric, thường là tập giá trị hữu hạn.
3. **`error.code` và `exception.type`** định nghĩa nhóm lỗi, có thể chuẩn hóa để làm metric dimension.
4. **`attempt`, `outcome`** cho biết event chỉ là retry hay thất bại cuối cùng.
5. **`request_id` và `trace_id`** nối log trong request hoặc trace, **không** làm metric label.
6. **Timestamp/UTC** để so cửa sổ thời gian, đồng thời biết ingest timestamp nếu pipeline bị trễ.
7. **Message/stack trace** phục vụ điều tra; phải sanitize, giới hạn kích thước và bảo vệ dữ liệu nhạy cảm.

Log HTTP completion nên có `event.name=http.request.completed`, final status, duration và outcome của toàn request. Đừng đặt `outcome=FAILED` ở event completion chỉ vì attempt đầu từng ném exception; phải dựa vào response cuối.

### Level và chính sách ghi stack trace

Một timeout sẽ được retry thường phù hợp với WARN ở attempt boundary hơn là ERROR request failure. Có thể giữ summary ngắn cho các attempts và chỉ ghi stack trace đầy đủ khi cần tại boundary cuối để giảm duplicate log volume.

Nếu cùng Throwable bị ghi tại DAO, service và controller rồi rethrow, ba ERROR logs có thể đến từ **một request lỗi**, không phải ba request lỗi. Dùng event name và owner của log để phân biệt; không dựa vào việc hai stack traces giống nhau để dedup nghiệp vụ.

## 6. Ví dụ Java 17 hoàn chỉnh và stdout xác định

Ví dụ sử dụng **chỉ JDK 17**. Ba request được xử lý tuần tự. Counter trong ví dụ là số nguyên tĩnh để dễ hiểu, không phải implementation thread-safe cho Servlet production. Logging dùng JUL (`java.util.logging`) với Handler ghi message cố định ra stdout, không thêm timestamp từ formatter mặc định.

Kịch bản:

- `req-1` thành công ngay.
- `req-2` gặp `IllegalStateException` ở attempt 1, sau đó retry thành công.
- `req-3` gặp exception ở cả attempt 1 và 2; sau attempt 2 request thất bại cuối cùng.

Lưu thành **`ExceptionMetricReconciliationDemo.java`**:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ExceptionMetricReconciliationDemo {
    private static final Logger LOG =
            Logger.getLogger("example.exception.metrics");

    private static long requestsTotal;
    private static long requestsFailed;
    private static long exceptionAttempts;
    private static long retries;
    private static long requestsRecovered;

    private static void executeAttempt(String requestId, int attempt) {
        if ("req-2".equals(requestId) && attempt == 1) {
            throw new IllegalStateException("temporary downstream failure");
        }
        if ("req-3".equals(requestId)) {
            throw new IllegalStateException("downstream unavailable");
        }
    }

    private static boolean handleRequest(String requestId) {
        requestsTotal++;

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                executeAttempt(requestId, attempt);

                if (attempt > 1) {
                    requestsRecovered++;
                }
                return true;
            } catch (IllegalStateException ex) {
                exceptionAttempts++;

                boolean willRetry = attempt < 2;
                String outcome = willRetry ? "RETRY" : "FAILED";
                Level level = willRetry ? Level.WARNING : Level.SEVERE;

                LOG.log(level,
                        "request_id=" + requestId
                        + " attempt=" + attempt
                        + " exception_type="
                        + ex.getClass().getSimpleName()
                        + " outcome=" + outcome);

                if (willRetry) {
                    retries++;
                } else {
                    requestsFailed++;
                    return false;
                }
            }
        }
        throw new AssertionError("Unreachable");
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(
                            record.getLevel().getName() + " "
                            + record.getMessage());
                }
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };
        sink.setLevel(Level.ALL);
        LOG.addHandler(sink);

        try {
            handleRequest("req-1");
            handleRequest("req-2");
            handleRequest("req-3");

            System.out.printf(
                    "METRIC requests_total=%d requests_failed_total=%d "
                    + "exception_attempts_total=%d retries_total=%d "
                    + "requests_recovered_total=%d%n",
                    requestsTotal, requestsFailed, exceptionAttempts,
                    retries, requestsRecovered);
        } finally {
            LOG.removeHandler(sink);
            sink.close();
        }
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac ExceptionMetricReconciliationDemo.java
java ExceptionMetricReconciliationDemo
```

**Stdout chính xác:**

```text
WARNING request_id=req-2 attempt=1 exception_type=IllegalStateException outcome=RETRY
WARNING request_id=req-3 attempt=1 exception_type=IllegalStateException outcome=RETRY
SEVERE request_id=req-3 attempt=2 exception_type=IllegalStateException outcome=FAILED
METRIC requests_total=3 requests_failed_total=1 exception_attempts_total=3 retries_total=2 requests_recovered_total=1
```

Đối chiếu từng số:

| Counter | Giá trị | Lý do |
| --- | ---: | --- |
| `requests_total` | 3 | Ba request logic, mỗi request được nhận một lần |
| `requests_failed_total` | 1 | Chỉ `req-3` thất bại cuối cùng |
| `exception_attempts_total` | 3 | `req-2` có một attempt exception; `req-3` có hai |
| `retries_total` | 2 | `req-2` và `req-3` đều thử lần hai |
| `requests_recovered_total` | 1 | Chỉ `req-2` hồi phục sau retry |
| Exception log events | 3 | Mỗi attempt thất bại ghi một event tại ranh giới đã chọn |

**Giới hạn:** chương trình dùng `long` tĩnh không thread-safe và Handler in text, không export metric, không có HTTP server, không ghi stack trace thực hoặc liên kết trace. Trong production dùng metric registry/thread-safe counter và logging encoder/handler phù hợp. Đây là bài thử **ngữ nghĩa đếm**, không phải benchmark performance hay hợp đồng durability.

Ví dụ không in message exception để stdout cố định và tránh dữ liệu không an toàn. Ở ứng dụng thật, khi cần điều tra, dùng overload logging nhận `Throwable` tại boundary đã chọn, chẳng hạn `logger.log(Level.SEVERE, "Request failed", ex)`. Không log lại nguyên stack ở từng tầng nếu không thêm giá trị.

## 7. Micrometer và Spring Boot: điểm tăng counter

Micrometer hỗ trợ Counter, Timer, DistributionSummary và các abstraction đo lường; Spring Boot có thể cung cấp HTTP server observations/metrics nếu đã cấu hình. Đừng tự instrument thêm một request counter giống metric framework đang tạo rồi cộng hai nguồn làm số request tăng gấp đôi.

Ví dụ danh mục thiết kế:

```text
dependency.attempt.exceptions
  tags: service, operation, error_code, exception_type

business.requests.failed
  tags: service, operation, outcome

business.operation.duration
  tags: service, operation, outcome
```

Đây là **tên minh họa do ứng dụng chọn**, không có sẵn trong mọi Micrometer registry. Đoạn Java minh họa (không độc lập, cần `micrometer-core`, `MeterRegistry` và biến context):

```java
Counter.builder("dependency.attempt.exceptions")
        .tag("operation", operationName)
        .tag("error_code", errorCode)
        .register(meterRegistry)
        .increment();
```

Đặt câu lệnh tăng counter này **một lần tại attempt boundary** được định nghĩa. Với `requests_failed_total`, tăng khi final outcome là failed ở HTTP/operation boundary tương ứng. Tránh đặt cùng tên counter ở repository, service, controller và exception handler khiến một request bị đếm nhiều lần.

Khi xuất sang Prometheus, tên Micrometer có thể được normalize và gắn suffix theo registry và naming convention. Phải kiểm đúng tên metric thực trong backend trước khi viết truy vấn. Không tự giả định metric `http.server.requests` của phiên bản A còn nguyên tên, tags và đơn vị ở phiên bản B.

### Timer và histogram

Counter lỗi chỉ nói số lần, không giải thích hậu quả latency. Một request có retry thành công có thể mất thời gian dài hơn nhiều, nên timer/histogram cũng quan trọng. Cần đo elapsed time bằng clock đơn điệu ở lifecycle request hoặc operation, không dùng chênh lệch giữa hai wall-clock timestamps làm đồng hồ đo duration.

Ví dụ quan hệ:

```text
request succeeded after 2 attempts:
  failed_request_counter += 0
  attempt_exception_counter += 1
  retries_counter += 1
  duration histogram records full request time once
```

Đừng chỉ đo thời gian của attempt cuối rồi gắn nhãn là full request duration. Nếu HTTP async/streaming, completion có thể muộn hơn lúc controller return; instrumentation phải chọn đúng lifecycle.

## 8. OpenTelemetry và liên kết log, metric, trace

OpenTelemetry tổ chức telemetry dựa trên resource attributes, context và các loại signal riêng biệt. **Không tự có một metric cho mỗi exception log**. Tùy instrumentation, exception có thể thành span event, logger record hoặc không xuất khi bị lọc.

Chiến lược đối chiếu:

- Log có `trace_id`, `span_id`, service, operation, error code, attempt và outcome.
- Span thể hiện call/operation; exception event có thể gắn vào span đang hoạt động. Span status không nhất thiết bằng HTTP final status trong mọi workflow.
- Metrics tổng hợp theo dimensions có số giá trị hữu hạn như service, route, outcome và error code.
- Exemplar, nếu backend/SDK hỗ trợ, giúp nhảy từ một mẫu metrics tới trace mà không biến trace ID thành label của tất cả time series.
- Nếu trace sampling không giữ trace cụ thể, log vẫn có thể mang ID và request metric vẫn phải phản ánh traffic theo chính sách.

Tên OTel semantic conventions về HTTP và exception thay đổi theo phiên bản; `error.type`, `exception.type` hoặc route attributes cần được đối chiếu với instrumentation thực tế. Một số backend yêu cầu mapping để làm nút “View trace” hoạt động.

### MDC và async context

Với SLF4J/Logback, MDC thường lưu dữ liệu theo thread. Khi request chuyển qua `ExecutorService`, `CompletableFuture` hoặc reactive pipeline, MDC không mặc nhiên truyền đúng sang worker. Điều này có thể khiến log thiếu hoặc mang sai `request_id`/`trace_id` trong khi metric vẫn tăng đúng.

Cần dùng context propagation được framework/instrumentation hỗ trợ, khôi phục/xóa context khi tác vụ kết thúc và test thread pool tái sử dụng. **MDC là ngữ cảnh quan sát**, không nên là nguồn xác thực quyền hoặc dùng làm metric label chứa ID tùy ý.

## 9. Cardinality: không biến log detail thành metric label

Logs có thể giữ request ID, stack trace và message phục vụ tìm kiếm; metric time series thường phải có **tập labels giới hạn**.

| Label tương đối phù hợp | Ví dụ | Điều kiện |
| --- | --- | --- |
| `service` | `checkout-api` | Danh mục service được quản lý |
| `environment` | `prod` | Tập nhỏ |
| `operation` hoặc `http.route` | `payment.authorize`, `/api/orders/{id}` | Template route thay vì raw URL |
| `outcome` | `SUCCESS`, `FAILED`, `RECOVERED` | Enum nhỏ |
| `error_code` | `DOWNSTREAM_TIMEOUT`, `VALIDATION_ERROR` | Danh mục được kiểm soát |
| `exception_type` | `SocketTimeoutException` | Kiểm giới hạn class, có thể gom nhóm |
| `dependency` | `payment-provider` | Tên logic, tránh host động |

**Không dùng** `request_id`, `trace_id`, order ID, user ID, exception message, stack trace, raw URL, SQL statement hoặc token làm metric label. Một triệu ID sẽ gây số lượng series rất cao; mang ID vào log/trace có kiểm soát quyền truy cập thay vì metrics.

Ngay cả exception type cũng phải kiểm: ứng dụng có thể có nhiều class lỗi tùy biến; không lấy `exception.toString()` hoặc message làm type. Với nhóm lỗi quá rộng, quy về danh mục `TIMEOUT`, `CONFLICT`, `INVALID_INPUT`, `UNKNOWN`.

## 10. Các nguyên nhân chênh lệch hợp lệ

### A. Retry và fallback

Một request có thể ném nhiều exception, được retry rồi thành công. Metric final failure thấp hơn attempt exception count là đúng. Ngay cả khi circuit breaker mở và trả fallback, request có thể degrade mà không ném cùng loại exception mới.

### B. Exception bị catch, wrap hoặc rethrow

Một lỗi low-level có thể được bọc thành `ServiceException` và ném lại qua nhiều lớp. Nếu mỗi catch log stack và tăng counter, hệ thống đo một lỗi nhiều lần. Tách metric dependency attempt khỏi metric final operation. Ưu tiên log đầy đủ tại một boundary có ngữ cảnh nhất quán, ghi events khác loại khi thật sự cần.

### C. HTTP/Business outcome không đồng nhất với exception

Validation 400 hoặc access denial có thể là nhánh logic bình thường. Ngược lại, HTTP 200 có thể mang business outcome `FAILED` trong body nếu API thiết kế như vậy. Đừng dùng metric exception để thay thế metric HTTP 5xx hoặc business failures.

### D. Job async sau khi HTTP request kết thúc

Nếu endpoint trả 202 Accepted và worker sau đó lỗi, job failure không làm HTTP response 202 trở thành 500. Log/metric của job phải có job ID/correlation phù hợp và đơn vị job outcome riêng.

### E. Log level/sampling và queue drop

Một exception được quan sát ở code nhưng log có thể bị filter theo mức, sampling, async queue discard, Collector parse lỗi hoặc backend quota. Metric vẫn có thể được cập nhật. Ngược lại metrics có thể bị mất scrape/export trong khi log vẫn đủ.

### F. Event time, ingestion time và cửa sổ metrics

Log xảy ra lúc 10:00:58 nhưng nhập backend lúc 10:01:14. Counter được exporter/scrape vào thời điểm khác. Nếu so chart theo các cửa sổ đúng 1 phút mà không nới dung sai và xem ingest lag, số liệu có thể lệch.

### G. Counter reset và aggregation

Process restart làm counter in-memory về 0. Hệ thống time series thường xử lý counter reset trong `rate()`/`increase()` phù hợp; đừng lấy chênh lệch thô của hai điểm trước/sau restart rồi kết luận số lỗi âm. Khi cộng nhiều instance, phải giữ đúng service, route, environment và group labels.

### H. Nhiều service cùng quan sát một sự cố

Gateway, service và downstream có thể cùng log và đo một failure. Tổng “errors” cộng từ mọi service không phải số request người dùng lỗi. Ranh giới đo phải chọn rõ: edge request, per-service request, dependency attempt hay business operation.

## 11. Quy trình đối chiếu khi dashboard xuất hiện spike

1. **Kiểm tên và định nghĩa metric:** Đang đếm failed requests, error responses hay attempts? Instrumentation owner nào phát?
2. **Chọn scope:** service, environment, operation/route, outcome và khoảng thời gian; kiểm clock, timezone và ingest lag.
3. **Tính ratio đúng đơn vị:** hai counter cùng scope mới được dùng làm tử/mẫu cho error rate.
4. **Tìm log tương ứng:** lọc theo service, operation, `event.name`, error code; phân biệt `dependency.attempt.failed` với `http.request.completed`.
5. **Lấy correlation ID:** dùng `request_id`/`trace_id` của một request điển hình; dựng timeline retry/fallback/exception handler.
6. **Xác định điểm tăng counter:** có log từ nhiều tầng nhưng metric chỉ tăng một lần, hay một counter bị tăng trùng ở nhiều catch?
7. **Kiểm sampling và dữ liệu thiếu:** logs có bị lọc/dropped, metrics có scrape lỗi hoặc stale series không?
8. **Kiểm thời điểm:** logs có thể xuất hiện sau scrape window; query kèm độ trễ phù hợp.
9. **Kiểm outcome cuối:** request có thực sự lỗi hay đã hồi phục, là lỗi HTTP hay business?
10. **Ghi kết luận và sửa đúng tầng:** schema, instrumentation, bộ lọc, pipeline exporter hay dashboard query.

Ví dụ query ở mức ý tưởng:

```text
Metric:
  increase(requests_failed_total{service="checkout-api"}[5m])

Log:
  filter service.name="checkout-api"
     and event.name="http.request.completed"
     and outcome="FAILED"
     and timestamp in comparable window

Trace:
  inspect trace_id from representative failed request
```

Đây **không phải một truy vấn có thể copy vào mọi backend**. Với Prometheus, `increase(counter[5m])` phải được nhóm đúng labels và xử lý reset; với Cloud Logging, Elastic/Loki hay hệ khác, cú pháp filter và schema khác nhau.

## 12. Tính error rate đúng — và cách sai

Cách sai:

```text
ERROR logs in 5 minutes = 150
HTTP requests in 5 minutes = 1000

150 / 1000 = 15% failed HTTP requests? KHÔNG KẾT LUẬN ĐƯỢC.
```

150 logs có thể gồm retries, lỗi job nền, stack trace trùng, exporter duplicates, hoặc exception đã recovered; một số request lỗi không tạo ERROR log.

Cách đúng nếu hai metric cùng boundary và policy:

```text
requests_total increase over 5 minutes = 1000
requests_failed_total increase over 5 minutes = 20

request_error_rate = 20 / 1000 = 2%
```

Ở đây `requests_failed_total` đã được định nghĩa là **request kết thúc lỗi** theo contract. Nếu cần tỷ lệ 5xx, dùng final HTTP status 5xx; nếu muốn thất bại nghiệp vụ, dùng counter riêng. Khi mẫu số bằng 0, xử lý biểu đồ/query theo quy tắc đã định thay vì chia cho 0.

Không kết luận 20 request lỗi phải tạo đúng 20 ERROR log: completion events có thể khác chính sách, retries tạo thêm attempt logs, hoặc stack trace chỉ được ghi ở một subset.

## 13. Một "hợp đồng quan sát" dùng chung

| Trường | Trong log | Trong metric | Trong trace |
| --- | --- | --- | --- |
| `service.name`, environment | Có | Tag/resource hữu hạn | Resource |
| `operation`/`http.route` | Có | Label bounded | Span name/attribute |
| `outcome`, `error_code` | Có | Enum tag | Span attribute/status phù hợp |
| `exception.type` | Có khi phát lỗi | Tag có kiểm soát | Exception event khi có instrumentation |
| `request_id` | Có để tìm event | **Không** thành label | Có thể có correlation attribute |
| `trace_id`/`span_id` | Có nếu context tồn tại | **Không** thành label; exemplar nếu hỗ trợ | Định danh trace/span |
| `attempt` và retry result | Có | Đếm số retries, không label request ID | Subspan/attempt event |
| Exception message/stack | Có khi cần, sanitize | **Không** là tag | Cần bảo vệ dữ liệu nhạy cảm |
| Duration | Completion log | Timer/histogram | Span duration |

Chốt các quy ước: event names, metric names, owner của từng counter, list error codes, status mapping, cấu trúc request/attempt, timestamp, giới hạn labels và retention. Quản lý schema/version khi ứng dụng và backend nâng cấp.

Hợp đồng phải phân biệt **nguyên nhân** (dependency timeout) với **ảnh hưởng cuối** (request success/failure). Khi đầy đủ, metric cho biết tình trạng tổng thể còn log/trace cung cấp bằng chứng cụ thể.

## 14. Kiểm thử và giám sát hai pipeline

### Các test nên có

| Tình huống | Log kỳ vọng | Metric kỳ vọng |
| --- | --- | --- |
| Success ngay | Không attempt exception | request +1, failed +0 |
| Timeout rồi retry thành công | WARN attempt=1, outcome=RETRY | exception attempt +1, retry +1, recovered +1 |
| Hai attempts lỗi | WARN attempt=1, final ERROR/SEVERE | attempt +2, retry +1, failed request +1 |
| Business validation trả 400 | Completion có status/reason | HTTP 4xx +1, exception không bắt buộc |
| Bắt exception và fallback | Có dấu hiệu recovered | failure +0, fallback/degraded theo contract |
| Wrap/rethrow | Không log cùng stack trùng ở các tầng | Request final failure tăng một lần |
| Background job lỗi | Log thuộc job | Job error +1; HTTP đã trả không đổi |
| Thread pool/reactive context | Request ID đúng, không trộn giữa luồng | Label hữu hạn, counts đúng |
| Log queue đầy | Có drop/retry metrics ở pipeline | Business counter vẫn phản ánh nghiệp vụ |
| Metrics exporter lỗi | Log có thể vẫn đủ | Scrape/export health báo lỗi |
| Restart process | Log có thể đến trễ | Query counter reset không âm bất thường |
| Message chứa secret | Redaction hoạt động | Không tạo tag có secret |
| Multi-service request | Events phân biệt service/span | Không cộng nhầm edge errors với dependency errors |

Với unit test, dùng stub/fake downstream để ép lỗi từng attempt, assert counter increments và log sink. Với integration test, chạy backend/metric registry/collector thật, kiểm ingest và eventual query bằng điều kiện chờ có timeout thay vì `Thread.sleep(1000)` rồi cho rằng xong.

### Sức khỏe logging và metric pipelines

- Logging: dropped events, async queue depth, exporter errors, parse failures, ingest lag và missing heartbeat.
- Metrics: scrape target up/down, remote-write backpressure, export failure, stale series, label cardinality và reset.
- Tracing: sampling rate, missing spans, exporter errors, context propagation.
- Nghiệp vụ: số requests/transactions từ boundary tin cậy, dùng đối chiếu độc lập khi observability pipeline lỗi.

Nếu metrics báo request traffic vẫn chạy mà log rate bằng 0, có thể log level/sampling thay đổi hoặc pipeline mất tín hiệu. Nếu logs có lỗi nhưng không có metric, có thể metrics exporter lỗi hoặc instrumentation thiếu. Đừng tự coi “không có sample” là “0 lỗi”.

## 15. Sai lầm phổ biến và cách sửa

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `count(ERROR logs)` để tính số request lỗi | Duplicate, retry, sampling làm số sai | Dùng final request failure metric |
| Tăng failed request tại mọi `catch` | Một request bị đếm nhiều lần | Một owner ở completion boundary |
| Ghi đầy đủ stack rồi rethrow ở nhiều tầng | Log trùng, tăng chi phí | Ghi stack ở ranh giới có ngữ cảnh |
| Nhầm attempt exception với final error | Retry thành công vẫn bị đánh dấu lỗi | Tách attempt/recovered/failed |
| Dùng exception message làm metric label | Cardinality và PII cao | Dùng mã lỗi/type chuẩn hóa |
| Gắn trace ID hoặc request ID vào metric label | Tạo vô số time series | IDs ở log/trace; exemplar nếu hỗ trợ |
| Gọi HTTP 400 là 5xx vì có exception | Sai nghĩa response status | Mapping theo final HTTP status |
| Job async lỗi và tăng HTTP 500 đã trả 202 | Sửa ngược lịch sử request | Dùng job outcome metric riêng |
| So log ingest phút này với metric scrape phút khác | Mismatch do trễ | Cửa sổ + ingest delay |
| Cộng errors của gateway, service, dependency | Double counting cùng failure | Phân biệt measurement boundary |
| Tin rằng metric/log export luôn đầy đủ | Mất sample do lỗi pipeline | Self-metrics, canary, health alerts |

## 16. Checklist triển khai trong ứng dụng Java

- [ ] Có định nghĩa riêng cho request, operation, attempt, retry và exception occurrence?
- [ ] Mỗi counter có một owner và thời điểm tăng rõ ràng, không tăng cùng metric ở nhiều layer?
- [ ] Có phân biệt attempt bị lỗi nhưng request recovered với request thật sự thất bại?
- [ ] Log chứa service, operation/route, error code, attempt/outcome và correlation ID cần thiết?
- [ ] Có tránh log trùng Throwable khi wrap/rethrow và hạn chế stack trace không cần thiết?
- [ ] Có bảo vệ exception message/stack khỏi secret, token và dữ liệu cá nhân?
- [ ] Metric tags chỉ là enum/route/service hữu hạn, không có ID hoặc message động?
- [ ] Đã hiểu metric HTTP/framework có sẵn trước khi thêm counter tự viết?
- [ ] Context từ SLF4J MDC/OTel được propagate và dọn đúng qua thread/reactive?
- [ ] Dashboard dùng cùng window, timezone, counter reset handling và scope multi-instance?
- [ ] Có test success, retry-recovered, final failure, validation 4xx, job async và exporter failure?
- [ ] Có tự giám sát log pipeline, metric pipeline và tracing pipeline khi dữ liệu đối chiếu không khớp?

**Ghi nhớ:** **exception** là biến cố trong luồng xử lý, **log** là bằng chứng chi tiết do chính sách logging quyết định, còn **metric** là phép đo tổng hợp tại một boundary rõ ràng. Để đối chiếu chính xác, hãy phân biệt attempt và request, định nghĩa final outcome, dùng error code/service/operation chung, đặt request/trace ID trong log chứ không trong metric labels, và kiểm tra cả sampling lẫn sức khỏe pipeline. Việc hai số liệu khác nhau thường là thông tin có ý nghĩa — không nhất thiết là một lỗi.
