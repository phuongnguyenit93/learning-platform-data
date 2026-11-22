# Log ở boundary: ghi exception đúng nơi chịu trách nhiệm xử lý trong Java

## 1. “Log ở boundary” nghĩa là gì?

Trong **Java Core Logging và exception handling**, *boundary* là ranh giới nơi một thành phần **nhận trách nhiệm cuối cùng đối với kết quả của một thao tác**: trả HTTP response, hoàn tất một job, quyết định ACK/retry/dead-letter một message, kết thúc một CLI command hoặc bàn giao lỗi cho một hệ thống bên ngoài.

Nguyên tắc hữu ích là: **ghi log exception tại boundary có đủ ngữ cảnh để quyết định cách xử lý**, thay vì mọi tầng trung gian đều bắt lỗi, ghi stack trace rồi ném tiếp. Bản ghi ở đây nên mô tả **thao tác đã thất bại, kết quả cuối cùng, mã lỗi ổn định, correlation ID và exception/cause cần thiết**, chứ không chỉ nói “Có lỗi xảy ra”.

Một luồng điển hình:

```text
HTTP request
    |
    v
Controller ----------- nhận request / ủy quyền xử lý
    |
    v
Service -------------- áp dụng nghiệp vụ, có thể translate exception
    |
    v
Repository ----------- gọi DB / downstream, có thể ném IOException
    |
    +-> lỗi được truyền lên, giữ nguyên cause
    |
    v
HTTP exception boundary
    +-> quyết định HTTP status và response công khai
    +-> log một event thất bại kèm request ID, error code, throwable
    +-> trả response đã làm sạch cho client
```

Ví dụ nếu repository bị mất kết nối, ba tầng đều `logger.error("Failed", ex)` rồi ném tiếp sẽ tạo nhiều stack trace gần như giống nhau. Một exception ở request boundary đủ thông tin thường hữu ích hơn ba bản ghi trùng, dễ làm dashboard phóng đại số lỗi.

**Không phải quy tắc “chỉ được có một log trong toàn hệ thống”**: gateway, service A và service B có thể ghi sự kiện riêng cho những hành vi *tại boundary riêng*, ví dụ retry exhausted ở A và HTTP 502 ở gateway. Nhưng trong **một luồng xử lý của cùng component**, tránh log cùng throwable nhiều lần chỉ vì nó đi qua nhiều `catch`.

### Boundary và tầng trung gian khác nhau thế nào?

| Vị trí | Trách nhiệm | Quyết định logging |
| --- | --- | --- |
| Repository/DAO | Truy cập DB, filesystem, network | Thường ném exception để caller quyết định; không log full stack rồi throw lại |
| Domain/service | Áp quy tắc nghiệp vụ, translate lỗi, bổ sung context | Wrap exception có cause nếu cần; log nếu thật sự **xử lý/phục hồi** hoặc ghi một event nghiệp vụ độc lập |
| HTTP/controller boundary | Chốt status, response, mã lỗi của request | Log đúng mức theo outcome cuối và request context |
| Scheduled/background job boundary | Chốt job thành công/thất bại, retry/schedule tiếp | Log once sau khi xác định kết quả; tránh để exception chỉ biến mất trong Future |
| Message consumer boundary | Chốt ACK, retry, requeue hoặc dead-letter | Log quyết định terminal; tránh log ERROR ở mỗi attempt nếu còn retry bình thường |
| Application entry point | Chốt exit code/đóng tài nguyên | Log fatal/unhandled khi không có boundary nào phía trên |
| Framework/server | Có thể tự log lỗi chưa được xử lý | Xem logging mặc định để tránh tạo bản sao từ cả framework và ứng dụng |

Boundary **không nhất thiết là method trên cùng của call stack**. Đó là nơi một operation được kết thúc, chuyển thành status hoặc được bàn giao theo hợp đồng rõ ràng. Một service có thể là boundary cho một subsystem nếu nó tự xử lý lỗi, trả fallback và không truyền exception tiếp.

## 2. Phân biệt các hành động khi bắt exception

Một `catch` có thể làm nhiều việc khác nhau; lựa chọn ghi log phải theo **ý nghĩa xử lý**, không theo việc “code có `catch` nên phải log”.

| Tình huống | Cách làm chính | Log full exception tại đâu? |
| --- | --- | --- |
| Chỉ biết lỗi, chưa có quyền xử lý | Để exception truyền lên hoặc wrap giữ cause | Ở boundary xử lý cuối |
| Đổi lỗi hạ tầng thành lỗi miền nghiệp vụ | Ném exception mới với cause gốc | Boundary quyết định outcome, tránh ghi tại mỗi phép translate |
| Phục hồi hoàn toàn bằng fallback hợp lệ | Trả fallback, event có kết quả được phục hồi | Có thể log WARN/INFO tại nơi phục hồi nếu có giá trị, không báo thất bại toàn operation nếu nó đã thành công |
| Đã retry nhưng hết lượt | Chốt failed/timeout/dead-letter | Log một sự kiện terminal đầy đủ; các attempt có thể được đo bằng metric |
| Input không hợp lệ dự kiến | Trả 400 hoặc lỗi miền hợp lệ | Thường không cần full stack ERROR; dùng code, count, security policy |
| Lỗi không dự kiến ở API | Trả response an toàn, phát tín hiệu lỗi | Boundary log ERROR với throwable đã được kiểm soát |
| Cần audit độc lập | Tạo audit event cấu trúc theo policy | Audit không thay thế log exception; có thể cần pipeline bền riêng |

Một lớp trung gian có thể thêm thông tin mà boundary không biết, nhưng **không cần log để thêm thông tin**. Có thể wrap đúng exception type với message đã làm sạch và cause gốc, hoặc truyền structured context lên cùng operation.

### Mẫu nên tránh: log rồi ném tiếp ở mọi tầng

```java
try {
    repository.save(entity);
} catch (SQLException ex) {
    logger.error("Save failed", ex);
    throw ex;
}
```

Đây là đoạn minh họa, cần `repository`, `entity`, logger và exception type phù hợp. Nếu caller cuối cùng cũng log stack trace, việc log ở repository tạo bản sao không mang thêm quyết định xử lý. Tệ hơn, nếu lỗi xảy ra hàng nghìn lần khi hệ thống bị quá tải, mỗi tầng có thể nhân ba hoặc bốn log ERROR, che khuất tín hiệu khác và tốn tài nguyên.

Trong trường hợp caller cần phân biệt lỗi miền:

```java
try {
    repository.save(entity);
} catch (SQLException ex) {
    throw new PersistenceUnavailableException(
            "Cannot complete persistence operation", ex);
}
```

Đây là **đoạn minh họa không chạy độc lập**; `PersistenceUnavailableException` là custom exception của ứng dụng. Constructor nhận `ex` làm cause rất quan trọng. Nếu tạo `new PersistenceUnavailableException("...")` mà **bỏ cause**, stack trace ở boundary sẽ khó cho biết vì sao DB call thất bại. Khi cần đối chiếu dữ liệu nội bộ, có thể thêm mã operation hoặc resource ID không nhạy cảm, nhưng không đưa SQL chứa bí mật hoặc request body vào message.

Một `catch` chỉ để `throw ex;` thường không cần tồn tại nếu không làm cleanup, translate hoặc điều khiển xử lý. Với cleanup, ưu tiên `try-with-resources` hoặc `finally` phù hợp.

## 3. Quy tắc “log once” cần hiểu đúng

Một guideline thường gặp là **“log an exception once, at the point it is handled”**. Đây là **quy tắc thiết kế**, không phải đặc tính Java tự bảo đảm.

- **Cùng exception, cùng operation:** đừng in stack trace giống nhau ở repository, service, controller và filter chỉ vì exception đi qua.
- **Nhiều operation riêng biệt:** nếu service B trả lỗi cho service A, B có thể log failure của request vào B; A sau khi retry hết có thể log failure của **operation A**. Các event có `service.name`, `event.name`, request/trace ID và trách nhiệm khác nhau.
- **Recovery xảy ra:** nếu một downstream timeout rồi fallback từ cache thành công, đừng báo toàn bộ HTTP request failed chỉ vì có exception trung gian. Ghi “fallback used” nếu cần và đo tỷ lệ degraded service.
- **Framework cũng có boundary:** Servlet container, Spring MVC exception resolver, scheduler hoặc messaging framework có thể tự log uncaught exceptions. Phải biết ai sở hữu error event để tránh app log một lần rồi framework log lại.
- **Audit/security khác operational error:** một access-denied event theo chính sách audit có thể cần lưu đầy đủ dù 403 là expected outcome và không cần stack trace ERROR.

Nếu không chắc tầng nào log, hỏi: **“Ai chịu trách nhiệm xác định kết quả cuối cùng, khởi động retry hoặc trả lỗi cho bên ngoài?”** Đây thường là nơi hợp lý nhất.

## 4. Ghi exception đúng API để giữ stack trace và cause

Các API thường gặp trong Java:

### SLF4J (với Logback hoặc Log4j2 backend phù hợp)

```java
logger.error("Operation failed", ex);
logger.error("Order failed orderId={}", safeOrderId, ex);
```

Trong SLF4J, truyền `Throwable` đúng overload/ở đối số cuối trong pattern thường cho phép backend xử lý stack trace. Không đổi thành:

```java
logger.error("Operation failed: {}", ex.getMessage());
logger.error("Operation failed: " + ex);
```

Hai dòng sau chỉ truyền **text đã dựng**, thường không giữ toàn bộ cause/stack trace trong cấu trúc logging event. Tuy nhiên **không phải stack trace nào cũng an toàn để xuất**: message của exception từ downstream có thể chứa token, SQL literal, file path, request URL hoặc dữ liệu khách hàng. Với dữ liệu nhạy cảm, phải có chính sách redaction/formatting, quyền truy cập log và chọn trường phù hợp, không mặc định mọi ERROR đều in được full Throwable.

### java.util.logging (JUL)

```java
logger.log(
        java.util.logging.Level.SEVERE,
        "event=request.failed error_code=DOWNSTREAM_UNAVAILABLE",
        ex);
```

JUL dùng `Level.SEVERE` cho trường hợp lỗi nặng; Handler/Formatter quyết định nội dung/đích. Không nhầm JUL `WARNING` và `SEVERE` với SLF4J `WARN`/`ERROR` là API hoàn toàn giống nhau. Cần cấu hình handler, filter, formatter và level thực tế.

### Giữ root cause khi wrap

```java
throw new OrderServiceUnavailableException(
        "Order operation unavailable", originalIOException);
```

Đây là mã minh họa; custom exception cần constructor nhận cause. Có thể lấy `getCause()` để hiểu nguyên nhân sâu hơn, nhưng **đừng bỏ mọi lớp wrapper**: exception ở service thường giải thích operation thất bại, còn root cause cho biết DB, HTTP, I/O hay validation là lý do kỹ thuật. Logging event nên giữ cả operation/context và cause chain.

**Chú ý suppressed exceptions:** `try-with-resources` có thể gắn exception xảy ra khi đóng resource vào `Throwable.getSuppressed()`. Một formatter stack trace đầy đủ có thể biểu diễn cả cause và suppressed exceptions; chỉ in `ex.getMessage()` có thể bỏ mất chúng.

## 5. Ví dụ Java 17 độc lập: một boundary, một event lỗi

Ví dụ dưới đây mô phỏng hai loại boundary: **HTTP request** và **background job**. Repository ném `IOException`, service wrap thành `ItemUnavailableException` với cause gốc, HTTP boundary bắt và log **một lần** rồi trả thông điệp an toàn. Background job có exception riêng và boundary của job ghi kết quả thất bại một lần.

Ví dụ dùng **JUL trong JDK** và một `Handler` tùy biến chỉ in level, event, exception type và root-cause type để stdout **xác định**, không phụ thuộc timestamp, thread ID hoặc stack trace thay đổi. **Production thường nên giữ throwable đầy đủ ở sink được bảo vệ**, tùy phân loại dữ liệu. Handler này chỉ phục vụ kiểm thử ý tưởng, không phải logging backend production.

Lưu đúng tên tệp **`BoundaryLoggingDemo.java`**:

```java
import java.io.IOException;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class BoundaryLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger("example.boundary");

    static final class ItemUnavailableException
            extends RuntimeException {
        ItemUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    record Response(int status, String body) {}

    private static void setupLogger() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }

                Throwable thrown = record.getThrown();
                Throwable root = thrown;
                while (root != null && root.getCause() != null) {
                    root = root.getCause();
                }

                String type = thrown == null
                        ? "none" : thrown.getClass().getSimpleName();
                String rootType = root == null
                        ? "none" : root.getClass().getSimpleName();

                System.out.printf(
                        "LOG level=%s %s exception=%s root_cause=%s%n",
                        record.getLevel().getName(),
                        record.getMessage(), type, rootType);
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };
        handler.setLevel(Level.ALL);
        LOG.addHandler(handler);
    }

    // Repository: phát sinh lỗi nhưng không log rồi ném lại.
    private static String loadFromRepository(String itemId)
            throws IOException {
        if ("broken".equals(itemId)) {
            throw new IOException("upstream unavailable");
        }
        return "item:" + itemId;
    }

    // Service: translate và giữ nguyên cause; không log trùng.
    private static String getItem(String itemId) {
        try {
            return loadFromRepository(itemId);
        } catch (IOException ex) {
            throw new ItemUnavailableException(
                    "Item backend unavailable", ex);
        }
    }

    // HTTP boundary: quyết định status, response và error event.
    private static Response handleRequest(
            String requestId, String itemId) {
        try {
            return new Response(200, getItem(itemId));
        } catch (ItemUnavailableException ex) {
            LOG.log(
                    Level.SEVERE,
                    "event=http.request.failed request_id=" + requestId
                            + " error_code=ITEM_UNAVAILABLE",
                    ex);
            return new Response(
                    503, "Service temporarily unavailable");
        }
    }

    // Job boundary: log khi job thực sự kết thúc thất bại.
    private static void runJob(String jobId, Runnable task) {
        try {
            task.run();
        } catch (RuntimeException ex) {
            LOG.log(Level.SEVERE,
                    "event=job.failed job_id=" + jobId, ex);
        }
    }

    public static void main(String[] args) {
        setupLogger();

        Response ok = handleRequest("req-001", "ok");
        System.out.printf(
                "HTTP req-001 status=%d body=%s%n",
                ok.status(), ok.body());

        Response unavailable = handleRequest("req-002", "broken");
        System.out.printf(
                "HTTP req-002 status=%d body=%s%n",
                unavailable.status(), unavailable.body());

        runJob("nightly-7", () -> {
            throw new IllegalStateException("checkpoint mismatch");
        });

        System.out.println("DONE");
    }
}
```

Biên dịch và chạy với **Java 17+**:

```bash
javac BoundaryLoggingDemo.java
java BoundaryLoggingDemo
```

**Stdout chính xác:**

```text
HTTP req-001 status=200 body=item:ok
LOG level=SEVERE event=http.request.failed request_id=req-002 error_code=ITEM_UNAVAILABLE exception=ItemUnavailableException root_cause=IOException
HTTP req-002 status=503 body=Service temporarily unavailable
LOG level=SEVERE event=job.failed job_id=nightly-7 exception=IllegalStateException root_cause=IllegalStateException
DONE
```

Giải thích theo từng bước:

1. `req-001` thành công: trả 200 và không có ERROR log. Điều này không cấm access logging độc lập; bài này đang minh họa **exception logging**, không phải access log đầy đủ.
2. `req-002` gặp `IOException` ở repository. Service tạo `ItemUnavailableException(..., ex)` nên giữ cause; không in stack trace tại hai tầng này. Boundary log `SEVERE` một lần và chọn HTTP 503.
3. Client chỉ nhận `Service temporarily unavailable`, không thấy message nội bộ `upstream unavailable`, tên Java exception hay stack trace. Trong production cần chính sách response mapping chuẩn.
4. `runJob` bắt lỗi `IllegalStateException` và log event `job.failed` tại boundary của job. Nó không có HTTP status vì là loại operation khác.
5. Handler demo chỉ in **tên type** của throwable và root cause, nên output hoàn toàn xác định. `LogRecord` thực sự có `Throwable`; backend thật có thể render stack trace, nhưng hãy đánh giá dữ liệu nhạy cảm trong exception message.
6. `runJob` ở ví dụ coi lỗi là **terminal** và kết thúc job. Nếu dùng scheduler có chính sách retry, không được nuốt exception khiến framework hiểu job đã hoàn thành; phải báo kết quả cho scheduler/retry mechanism theo hợp đồng.

Ví dụ này cố ý chỉ dùng một thread và memory; nó **không thử logging async, độ bền log, tính đầy đủ audit hoặc framework routing thật**. Để kiểm tra production, phải test tại HTTP/job boundary thực sự và xác nhận event đã tới backend.

## 6. HTTP boundary: chốt response và log ở đúng chỗ

Đối với ứng dụng web, các điểm xử lý exception thường bao gồm `@RestControllerAdvice`/`@ExceptionHandler` trong Spring MVC, Servlet error handler/Filter được thiết kế cho lỗi, hoặc tương đương trong framework khác. Nguyên tắc:

- **Exception-to-response mapping:** phân loại exception thành mã lỗi ổn định và status HTTP thích hợp.
- **Không lộ thông tin nội bộ:** body công khai nên gồm `error_code`/message an toàn, request ID; không trả stack trace, SQL query, đường dẫn nội bộ hoặc token.
- **Ghi đúng kết quả:** nếu exception được xử lý thành HTTP 404/409 hợp lệ, đừng mặc định log ERROR. Nếu backend timeout và request thất bại cuối cùng, ERROR có thể hợp lý.
- **Chọn thời điểm:** chỉ xem operation là hoàn tất ở giai đoạn xử lý phù hợp. Đối với async/streaming request, không giả định controller return nghĩa là response đã hoàn tất.
- **Tránh logging hai nơi:** framework có thể tự log exception chưa được xử lý; nếu `@ExceptionHandler` đã log rồi trả response, cấu hình server/access logging cần phân biệt các loại event.
- **Bao phủ lỗi sớm:** authentication filter, malformed request hoặc routing 404 có thể xảy ra trước controller advice; cần logging riêng ở boundary tương ứng nếu chính sách đòi theo dõi.

### Đoạn minh họa Spring MVC

```java
@RestControllerAdvice
class ApiExceptionHandler {
    private static final org.slf4j.Logger LOG =
            org.slf4j.LoggerFactory.getLogger(
                    ApiExceptionHandler.class);

    @ExceptionHandler(ItemUnavailableException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    public ApiError unavailable(ItemUnavailableException ex) {
        String requestId = TrustedRequestContext.currentRequestId();
        LOG.error(
                "event=http.request.failed error_code=ITEM_UNAVAILABLE request_id={}",
                requestId, ex);
        return new ApiError(
                "ITEM_UNAVAILABLE", "Service temporarily unavailable");
    }
}
```

**Đây là mã khái niệm, không phải file độc lập chạy được**: cần Spring MVC, các imports/annotations và lớp `ItemUnavailableException`, `ApiError`, `TrustedRequestContext` được định nghĩa phù hợp. `TrustedRequestContext` đại diện cho request ID đã được tạo/kiểm chứng tại ingress tin cậy; không lấy ID chưa kiểm chứng từ bất kỳ header client nào rồi coi là danh tính an toàn. Nếu muốn kiểm status/body ở runtime, bổ sung integration test với handler thực tế.

Khi có nhiều handler, cần quy định handler nào tạo error log chính và handler nào chỉ chuyển response. Một global handler bắt `Exception` rất rộng có thể che bug, nuốt `Error` hoặc làm mọi lỗi giống nhau; không nên dùng để “bắt tất cả và trả 200”.

### Status không tự nói đủ về mức độ lỗi

| Kết quả HTTP | Ý nghĩa thường gặp | Hướng log exception |
| --- | --- | --- |
| `400` input invalid | Lỗi client dự kiến theo contract | Thường DEBUG/INFO hoặc chỉ metric; không spam stack trace |
| `401` unauthenticated | Thiếu/xác thực không thành công | Có thể tạo security event có cấu trúc; không log credential |
| `403` unauthorized | Thiếu quyền | Audit/security theo policy; không tự coi đây là server crash |
| `404` not found | Tài nguyên/route không tìm thấy | Có thể là hành vi bình thường; chú ý scanner/path probing |
| `409` conflict | Tranh chấp phiên bản/trạng thái | Thường là outcome dự kiến hoặc lỗi nghiệp vụ cần phân tích |
| `429` rate limit | Client vượt giới hạn | Metric/rule security, không cần full Throwable ở mọi lần |
| `500` unhandled | Lỗi không dự kiến | ERROR với context tối thiểu và nguyên nhân |
| `502/503/504` upstream/dependency unavailable | Thất bại phụ thuộc, timeout hoặc không sẵn sàng | ERROR hoặc WARN theo chính sách và khả năng hồi phục |

Đây là **gợi ý phân loại**, không phải bảng bắt buộc cho mọi ứng dụng. Có trường hợp 404 ở endpoint quan trọng bất thường, hoặc 403 lặp hàng loạt cần alert security. Ngược lại, một 503 trong lần retry thành công không có nghĩa HTTP request cuối đã thất bại. Hãy log kết quả theo ranh giới thực tế.

## 7. Background job, scheduler và thread boundary

Trong các task chạy nền, không có HTTP exception handler chịu trách nhiệm. Boundary có thể là job runner, scheduler callback hoặc task completion handler.

### ExecutorService và Future

Với `ExecutorService.submit(...)`, exception trong tác vụ có thể được giữ trong `Future`; caller cần gọi `get()` hoặc kiểm kết quả theo hợp đồng để nhìn thấy lỗi. Nếu bỏ qua Future, exception có thể không được biểu diễn bằng một error event đáng tin.

```java
Future<?> future = executor.submit(() -> runScheduledOperation());
try {
    future.get();
} catch (ExecutionException ex) {
    logger.error("event=job.failed job_id={}", jobId, ex.getCause());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    logger.warn("event=job.wait_interrupted job_id={}", jobId);
}
```

Đây là đoạn minh họa, cần `executor`, `logger`, `jobId` và imports/logic, không chạy độc lập. `ExecutionException` là wrapper của lỗi task; có thể log nguyên wrapper hoặc cause tùy nhu cầu giữ bối cảnh, nhưng không làm mất thông tin gốc. Khi gặp `InterruptedException`, **khôi phục interrupt flag** nếu không truyền tiếp exception; đừng nuốt và tiếp tục chờ vô hạn.

Nếu một task tự log ERROR rồi ném exception và nơi gọi `future.get()` lại log, sẽ có hai event giống nhau. Chọn đúng nơi sở hữu kết quả: **bản thân job** nếu nó xử lý và hoàn tất tại đó, hoặc **orchestrator** khi nó quan sát kết quả cuối cùng từ Future.

### CompletableFuture và reactive pipeline

Trong `CompletableFuture`, một exception có thể được wrap bởi `CompletionException` hoặc được chuyển sang callback `exceptionally`/`handle`/`whenComplete`. Không gắn nhiều callback `whenComplete` cùng log ERROR một lỗi, rồi lại log ở HTTP response mapping. Quyết định rõ callback nào xử lý và nơi nào chỉ propagate.

Với reactive code, error signal có thể xảy ra bất đồng bộ. Các hook dạng `doOnError` có thể log khi có subscription/retry; **mỗi retry có thể tạo thêm một log** ngay cả khi toàn operation sau cùng thành công. Cần chọn giữa per-attempt diagnostic và terminal failure event, đồng thời dùng context propagation đúng thay vì giả định `ThreadLocal` luôn có giá trị.

### Scheduled tasks

Một số scheduler xử lý exception trong task theo quy tắc riêng (dừng schedule, ghi log, tái chạy hoặc giữ lỗi trong Future). Đừng giả định exception “sẽ tự được log ở đâu đó”. Kiểm framework/scheduler thực tế, quy định nơi chốt trạng thái `SUCCESS`/`FAILED` và báo metric job outcome. Không catch `Throwable` rộng để nuốt cả lỗi JVM nghiêm trọng chỉ nhằm giữ scheduler chạy.

## 8. Message consumer: ACK, retry và dead-letter boundary

Một message consumer có boundary rất rõ: **sau khi xử lý, consumer quyết định ACK/commit offset, retry/requeue hoặc chuyển tới dead-letter queue (DLQ)**. Ghi log phải đồng nhất với quyết định đó.

```text
Message nhận
   -> validate
   -> xử lý
      +-> thành công: commit/ACK, metric success
      +-> lỗi tạm thời: retry theo policy
      +-> lỗi không thể xử lý: reject/DLQ hoặc dừng theo policy
   -> log event terminal theo quyết định cuối
```

Ví dụ:

- Nếu broker cho retry 5 lần, đừng phát 5 stack trace ERROR với message “processing failed permanently” ngay ở attempt thứ nhất.
- Có thể ghi DEBUG/WARN có kiểm soát cho retry attempt, kèm `attempt`, `max_attempts`, `message_id` và reason code; metric đếm retry thường hữu ích hơn nhiều stack trace giống nhau.
- Khi hết retry và chuyển DLQ, consumer boundary tạo **terminal failure event** ghi quyết định và nguyên nhân, đúng một lần theo ngữ nghĩa logic nếu có thể.
- Nếu message bị reject vì schema không hợp lệ, cần policy riêng cho poison message, tránh retry vô hạn khiến log và DLQ tăng mạnh.
- Nếu handler catch exception, log rồi **acknowledge dù chưa xử lý**, có thể khiến message mất vĩnh viễn. Không làm điều đó chỉ để “tránh lỗi đỏ”.

**Điều kiện quan trọng:** ghi log và ACK/commit offset không phải một transaction nguyên tử chỉ vì chúng nằm trong cùng method. Một consumer có thể xử lý thành công, bị timeout khi ACK rồi retry, dẫn đến duplicate. Dùng idempotency/dedup cho hiệu ứng nghiệp vụ quan trọng và mô tả semantics của broker/framework thực tế.

Trong messaging framework tự động log unhandled exceptions, nếu handler catch–log–rethrow để kích hoạt retry, framework có thể in lại cùng throwable. Khi cần giao cho framework xử lý, có thể chỉ **propagate và để nó log**; hoặc điều chỉnh cấu hình để event terminal được log ở đúng owner.

## 9. Retry boundary và lỗi transient

Một hoạt động có thể gặp lỗi ngắn hạn rồi thành công. Khi đó boundary cuối cùng nên mô tả **kết quả sau tất cả attempt**, không nhất thiết cảnh báo ERROR ở từng lần.

| Diễn biến | Log gợi ý | Metric hữu ích |
| --- | --- | --- |
| Attempt 1 timeout; attempt 2 thành công | Event outcome `recovered` hoặc DEBUG retry; không đánh dấu request failed | `retry_attempts_total` |
| Hết retry, response 503 | Một terminal ERROR kèm error code và attempt count | `operations_failed_total` |
| Lỗi input không retryable | Outcome `rejected`/`denied` theo policy, có thể không full stack | `invalid_requests_total` |
| Circuit breaker đang open | Log/state transition hoặc event rate-limited; tránh log WARN cho mỗi call nếu traffic lớn | `circuit_breaker_open_total` |
| Timeout do client đã hủy yêu cầu | Phân loại cancellation, kiểm việc tác vụ còn chạy hay không | `cancelled_operations_total` |

Nếu muốn gắn `attempt=3` vào event cuối, cần cung cấp dữ liệu attempt từ retry library hoặc operation context; đừng suy đoán từ số lần method được gọi. Một lỗi downstream lặp ở hàng trăm request vẫn có thể tạo nhiều boundary events hợp lệ, nhưng cần **rate limiting/aggregation và metrics** để tránh làm nghẽn hệ thống logging.

Nguyên tắc “log once” không có nghĩa xóa lịch sử retry. Dùng **metric + diagnostic log có giới hạn** cho từng attempt, và **terminal event** cho kết quả mà người vận hành cần điều tra.

## 10. Structured logging ở boundary

Một bản ghi lỗi tốt nên trả lời được **thao tác nào thất bại, ở đâu, kết quả, tác động và nguyên nhân**:

```json
{
  "timestamp": "2026-01-01T00:00:00Z",
  "event.name": "http.request.failed",
  "service.name": "catalog-api",
  "deployment.environment.name": "prod",
  "http.route": "/items/{itemId}",
  "http.method": "GET",
  "http.status_code": 503,
  "request_id": "req-002",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "error.code": "ITEM_UNAVAILABLE",
  "exception.type": "ItemUnavailableException",
  "cause.type": "IOException",
  "retry.attempts": 3,
  "message": "Item lookup failed after retry"
}
```

Đây là **schema JSON minh họa**, không phải tập attribute được mọi backend tự nhận diện. Tên key của OpenTelemetry semantic conventions và khả năng mapping của collector/cloud log store có thể thay đổi theo phiên bản. Chọn một schema nội bộ ổn định, rồi map thích hợp sang backend.

Các trường quan trọng:

| Trường | Tác dụng | Lưu ý |
| --- | --- | --- |
| `event.name` | Định danh thao tác/sự kiện ổn định | Không dùng message tự do làm tên event |
| `error.code` | Nhóm lỗi logic để thống kê và query | Không đồng nhất với exception class |
| `exception.type` / cause | Chẩn đoán loại lỗi | Stack trace có thể chứa dữ liệu nhạy cảm |
| `request_id`/`job_id`/`message_id` | Tìm kết quả operation | ID phải từ nguồn tin cậy, ổn định trong scope |
| `trace_id` / `span_id` | Liên kết distributed trace | Một request có thể có nhiều span; tracing có thể sampled |
| `http.route` | Endpoint template | Tránh raw path có ID/token trong log chung |
| `http.status_code` | Kết quả HTTP cuối | Không dùng giá trị dự kiến trước exception mapping |
| `retry.attempts` | Số lần thử đã thực hiện | Đọc từ retry policy/runtime |
| `service.name` / environment | Phân biệt service/tầng lỗi | Giúp hiểu nhiều error logs qua các microservice |
| `duration_ms` | Tác động độ trễ | Đo bằng monotonic clock theo lifecycle của operation |

Trong hệ thống phân tán, logging ở hai boundary có thể tạo hai event với cùng trace ID nhưng **event name, service name và operation khác nhau**. Đó không nhất thiết là duplicate. Khi phân tích lỗi, có thể nhóm theo trace ID, operation ID và error code, không mặc định mỗi ERROR tương ứng một request lỗi độc lập.

## 11. MDC, thread pool và ngữ cảnh đáng tin

Để giữ correlation ID, nhiều logging backend hỗ trợ MDC (Mapped Diagnostic Context). Tuy nhiên MDC thông thường gắn với thread. Trong `ExecutorService`, `CompletableFuture` hoặc reactive pipeline, ngữ cảnh **không tự động** đi theo mọi task.

Mẫu khái niệm khi sử dụng SLF4J MDC:

```java
try (var ignored = org.slf4j.MDC.putCloseable(
        "request_id", trustedRequestId)) {
    service.handleRequest();
} catch (ServiceException ex) {
    logger.error("event=request.failed request_id={}",
            trustedRequestId, ex);
}
```

Đây không phải chương trình độc lập; cần SLF4J, logger, service và `trustedRequestId`. Lưu ý `MDC.putCloseable` là helper cho scope hiện tại; nó không tự động truyền context sang một worker thread mới, cũng không biến `request_id` thành danh tính đã xác thực. Nếu thread pool có context trước đó, phải quản lý restore/cleanup theo hợp đồng framework để không rò rỉ metadata giữa các request. Không đặt nguyên HTTP body hoặc secrets vào MDC.

**Tại boundary nên ưu tiên context từ nguồn tin cậy**:

- Request ID từ ingress đã kiểm tra hoặc tạo lại khi client input không hợp lệ.
- Actor/principal từ authentication context, không từ header do client tự khai.
- Error code từ exception mapping/policy của server.
- Route template do framework match, không phải raw path có token.
- Service/deployment metadata từ cấu hình chạy, không do request tùy ý ghi đè.

Nếu request ID không sẵn có, vẫn log event kèm service, operation và error code, không tự bịa actor danh tính hay gán ID giả. Với nghiệp vụ nhạy cảm, audit trail có hợp đồng khác operational error logging.

## 12. Bảo mật: tránh lộ thông tin khi ghi exception

Exception thường chứa thông tin từ tầng thấp: URL truy vấn có token, DB connection string, câu SQL, đường dẫn nội bộ, payload client hoặc thông tin người dùng. **Kết hợp context hữu ích với data minimization**:

1. Không ghi plaintext password, API key, access token, cookie, authorization header, full request body hoặc dữ liệu cá nhân không cần thiết.
2. Dùng `error.code` và ID nội bộ được phép dùng thay vì nối toàn bộ exception message vào một text field công khai.
3. Phân biệt **client response** (message an toàn) và **server log** (có thể giữ chi tiết kỹ thuật trong kho được phân quyền). Không trả `ex.toString()` hoặc stack trace cho client.
4. Áp secret redaction ở nguồn và pipeline khi thích hợp; collector-side masking là lớp bổ sung, không xóa được dữ liệu đã ghi vào stdout hoặc buffer trước đó.
5. Kiểm quyền xem log, vùng lưu trữ, retention và audit việc truy xuất, nhất là khi log chứa actor ID, IP, tài nguyên nhạy cảm.
6. Nếu bật full stack trace ở production, kiểm trường exception message và suppressed/cause chain; một filter chỉ che message ngoài cùng có thể bỏ sót secret sâu trong cause.
7. Tránh log injection: dùng encoder JSON có escaping đúng; không tin nguyên dữ liệu client gửi làm `event.name`, level hoặc actor.

**Nguy cơ “logging failure khiến nghiệp vụ lỗi thêm”**: với operational logs, không nên để việc ghi log đụng exception phụ làm mất original error hoặc làm hỏng response nếu pipeline logging thất bại. Nhưng cũng không được catch–ignore vô hạn trong hệ thống audit bắt buộc. Cần chọn policy fail-open/fail-closed theo loại sự kiện và hợp đồng nghiệp vụ.

## 13. Ghi log cho exception được xử lý có nên WARN không?

Không có ánh xạ universal từ mọi Java exception class sang log level. Cùng `IOException` có thể:

- Là một timeout tạm trong retry và operation sau cùng thành công: có thể chỉ DEBUG/INFO diagnostic hoặc metric.
- Là timeout sau khi hết retry và HTTP 503: ERROR/WARN theo chính sách, có terminal event.
- Là lỗi client hủy download: thường không tự động phát ERROR với full stack cho mỗi request, nhưng cần biết cancellation rate.
- Là lỗi không mong đợi gây mất dữ liệu: cần ERROR, alert và cơ chế xử lý/khắc phục thích hợp.

Một cách ra quyết định:

| Boundary outcome | Mức thường cân nhắc | Nội dung ưu tiên |
| --- | --- | --- |
| Success | INFO access log hoặc chỉ metrics | Route/operation, duration, status |
| Expected rejection | DEBUG/INFO/WARN hoặc audit/security riêng | Error code, actor/resource khi phù hợp, reason |
| Recovered/degraded | INFO/WARN có giới hạn | Fallback mode, dependency, retry count |
| Terminal failure | ERROR hoặc JUL SEVERE | Operation, outcome, correlation, exception |
| Cơ chế logging/audit lỗi | Alert vận hành riêng | Queue/exporter errors, dropped records, gaps |
| Không thể tiếp tục process | FATAL nếu backend hỗ trợ, hoặc ERROR/SEVERE | Lifecycle event, recovery status, tránh vòng log |

Đừng xếp mọi 4xx vào ERROR và mọi 5xx vào WARN/ERROR mà không xét nghiệp vụ. Tăng độ chi tiết INFO/WARN vô kiểm soát khi lỗi lặp liên tục có thể gây log storm; cần đo số lỗi bằng metrics và cấu hình rate limit/sampling hợp lý **không làm mất audit bắt buộc**.

## 14. Các anti-pattern thường gặp

| Anti-pattern | Vì sao không tốt | Lựa chọn tốt hơn |
| --- | --- | --- |
| `catch (Exception ex) { log.error(..., ex); throw ex; }` ở mọi lớp | Nhiều stack trace trùng, chưa có quyết định outcome | Propagate/translate, log tại boundary xử lý |
| `catch (Exception ex) { return null; }` | Nuốt lỗi, caller tưởng thành công hoặc NPE về sau | Trả lỗi theo contract, ghi outcome ở boundary |
| Log message rồi bỏ throwable | Mất stack/cause/suppressed details | Dùng overload nhận `Throwable` khi an toàn |
| Wrap exception mà bỏ cause | Mất nguyên nhân gốc | `new DomainException("...", ex)` |
| Log ERROR cho mọi validation failure | Noise, alert fatigue, chi phí lớn | Expected 4xx theo policy, metric/security event nếu cần |
| Log lỗi ở từng retry attempt như terminal failure | Báo giả dù operation hồi phục, log storm | Event terminal sau retry + metric attempt |
| Ghi exception vào HTTP response | Lộ đường dẫn, token, cấu trúc nội bộ | Response code/message an toàn, request ID |
| Ghi raw request/exception message vào MDC | Rò dữ liệu, thread reuse gây nhầm context | Trường allowlist, scope/cleanup |
| Cứ `catch (Throwable)` để “log mọi thứ” | Có thể che `Error` nghiêm trọng, OOM | Catch kiểu lỗi xử lý được, để fatal failure có chính sách riêng |
| Log ngay trong repository và controller cùng một Throwable | Trùng và khó xác định owner | Repository giữ cause; controller/handler chốt kết quả |
| Log lỗi ở job rồi quên ném lại khi scheduler cần retry | Scheduler hiểu job thành công | Truyền outcome/exception theo scheduler contract |
| Catch lỗi consumer, log và ACK bừa | Mất message, vi phạm at-least-once | ACK/retry/DLQ theo policy |
| Dùng một log ERROR thay cho audit event | Không đủ tính bền/actor/outcome | Audit riêng khi bắt buộc |
| Logger chỉ in `ex.getMessage()` | Message có thể trống/nhạy cảm, thiếu cause | Stable code + typed throwable được kiểm soát |
| Giả định một lần `logger.error` = backend nhận một event | Async queue, filter, collector có thể drop/retry | End-to-end probe, drop metrics, backpressure |

## 15. Kiểm thử boundary logging

Không chỉ test `catch` trả đúng status; cần kiểm **đúng số event, đúng nơi, đúng loại lỗi và không lộ dữ liệu**.

| Kịch bản | Mong đợi |
| --- | --- |
| Repository ném IOException, service wrap | Cause chain tồn tại; repository không log full stack nếu không xử lý |
| HTTP boundary map ItemUnavailable | Một terminal error event với request ID + error code, trả status/body an toàn |
| Request thành công | Không có exception ERROR event; access log/metric độc lập nếu được cấu hình |
| Validation failure dự kiến | 4xx/error code đúng; không stack trace ERROR vô ích |
| Retry thất bại lần đầu nhưng lần sau thành công | Không báo terminal failure; retry metric tăng |
| Retry exhausted | Một terminal failure event, đúng attempt count và outcome |
| Worker task exception | Job owner nhận lỗi và quyết định retry/fail, không bị swallow ngoài ý muốn |
| Future exception | Orchestrator quan sát kết quả; không log trùng với task |
| Message handler lỗi | ACK/retry/DLQ nhất quán; không ACK sai vì đã log |
| Lỗi từ framework trước controller | Error/access logging bao phủ theo policy, không ghi trùng |
| Nhiều request đồng thời | Không trộn MDC, trace ID hoặc actor giữa thread |
| Exception message có secret | Secret không xuất hiện trong client response/log không được phép |
| Log backend/collector lỗi | Có metric và alert; operational failure policy không che original exception |
| Truy vấn ở log backend | Event có thể tìm theo service, event.name, request ID; không bị nhân bản ngoài ý định |

Trong unit test, thay logger bằng test appender/handler có kiểm soát hoặc capture event để assert chính xác `event.name`, level, throwable type/cause và count. Với async logger, đợi condition/flush theo timeout thay vì dùng `Thread.sleep` cứng để khẳng định event đã đến. Tại integration test, bật framework exception handler, middleware và backend thực để xác nhận không log hai lần.

Đừng dùng phép đo số dòng stack trace làm số lần exception; một event có thể render nhiều dòng. Hãy đếm **log event** hoặc event ID theo cấu trúc.

## 16. Vận hành: log không thay thế metrics và trace

Boundary logging cung cấp sự kiện chi tiết, nhưng một nền tảng đáng tin cần nhiều tín hiệu:

- **Metrics:** số operation failed, retry count, latency, downstream timeout, queue backlog; phù hợp tính rate/SLO mà không cần parse mọi log.
- **Tracing:** hiểu request đi qua service và span nào; một trace có thể có nhiều boundary events ở các service khác nhau, và trace có thể sampled.
- **Structured logs:** điều tra từng operation với status/error code/context, giữ exception có kiểm soát.
- **Audit events:** hành động nhạy cảm hoặc pháp lý bắt buộc cần bảo đảm riêng, không lấy mẫu tùy tiện.

Ví dụ khi payment service lỗi, có thể có ERROR event tại payment boundary và ERROR event tại checkout boundary nếu checkout cuối cùng thất bại: hai event mô tả **hai operation khác nhau**, nên đặt event name, service, outcome rõ ràng. Khi làm dashboard, nhóm theo service/operation thay vì cộng tất cả ERROR để suy ra số request thất bại.

Log ERROR ở mọi tầng còn có thể che sự cố logging: khi queue quá tải, nó có thể bắt đầu drop, khiến người vận hành thiếu những event quan trọng nhất. Theo dõi `dropped_logs`, exporter failures, ingest lag và event probe độc lập với logger nếu có yêu cầu reliability.

## 17. Checklist áp dụng

- [ ] Đã xác định đúng **boundary chốt kết quả** cho HTTP request, job, message, CLI và worker?
- [ ] Repository/service chỉ translate hoặc propagate nếu chưa thật sự xử lý, tránh log-and-rethrow trùng stack?
- [ ] Khi wrap exception đã giữ `cause` và không phá chain/suppressed information?
- [ ] Exception được log bằng API nhận `Throwable`, không chỉ `getMessage()`, khi policy cho phép?
- [ ] Expected failure, recovered operation, terminal failure và audit đã có level/outcome riêng?
- [ ] Response/error code cho client an toàn, không lộ stack trace, token hay dữ liệu nội bộ?
- [ ] Có request/job/message ID, service, event name, retry count và context đáng tin?
- [ ] MDC được propagate và cleanup đúng khi async/thread pool?
- [ ] Không phát terminal ERROR ở từng retry attempt nếu operation cuối thành công?
- [ ] Job/Future/consumer không nuốt lỗi làm scheduler hoặc broker hiểu sai outcome?
- [ ] Đã kiểm frame­work default logging, middleware dispatch và async completion để tránh ghi trùng?
- [ ] Có test count/event type/Throwable, test secret leakage và end-to-end readback từ log backend?
- [ ] Metrics, trace và audit policy bổ sung logging theo đúng nhu cầu thay vì trộn lẫn?

**Ghi nhớ:** “log ở boundary” không có nghĩa đẩy mọi exception lên cao nhất hoặc bỏ log ở tầng dưới một cách máy móc. Nó có nghĩa **mỗi error event phải có một chủ sở hữu, một kết quả xử lý rõ ràng và ngữ cảnh đủ để điều tra**. Tầng trung gian giữ/translate nguyên nhân; boundary quyết định trả response, retry, fallback hay kết thúc tác vụ rồi ghi log phù hợp. Cách làm này giảm trùng stack trace, giảm noise, bảo vệ dữ liệu và khiến log trở thành bằng chứng đáng tin về điều thực sự đã xảy ra.
