# Log cùng exception nhiều lần — Anti-pattern trong Java Core Logging

## 1. Vấn đề và tác động

**Log cùng exception nhiều lần** xảy ra khi **cùng một thất bại (failure occurrence)** được ghi lặp lại ở repository, service, controller, exception handler hoặc callback bất đồng bộ, thường kèm **cùng chuỗi stack trace**. Mẫu kinh điển là **log-and-rethrow**: mỗi tầng bắt ngoại lệ, ghi `logger.error(...)` rồi ném tiếp cho tầng trên, nơi nó lại được ghi.

~~~text
[Repository] ERROR save failed
java.sql.SQLException: connection timed out
   at ...
[Service] ERROR checkout failed
java.sql.SQLException: connection timed out
   at ...
[Controller] ERROR request failed
java.sql.SQLException: connection timed out
   at ...
~~~

Một request có thể sinh **ba bản ghi ERROR** dù chỉ có một căn nguyên và một outcome thất bại. Những vấn đề kéo theo:

- Chẩn đoán chậm vì ba stack trace giống nhau che khuất tín hiệu khác.
- Alert và dashboard đếm sai nếu `count(level=ERROR)` được coi là số request thất bại.
- I/O, CPU định dạng stack trace, ingest bytes, retention và chi phí backend tăng.
- Cùng nội dung exception có thể chứa SQL, URL, token hoặc PII bị sao chép qua nhiều sink.
- Các layer đưa ra message khác nhau khiến cùng một failure trông như ba nguyên nhân.
- Khi kết hợp retry hoặc asynchronous work, rất khó biết log nào thuộc **attempt**, log nào thuộc **failure cuối**.

**Nguyên tắc cốt lõi:** thường nên giữ **một ranh giới chịu trách nhiệm ghi failure cuối cùng**, giữ nguyên `cause` xuyên các layer và bổ sung ngữ cảnh dưới dạng exception có kiểu, `errorCode` hoặc structured fields. Không bắt buộc mọi lớp có `catch` phải ghi ERROR.

**Không áp dụng khẩu hiệu “log once” một cách tuyệt đối.** Một sự kiện audit, một lần retry đã được lên lịch, một fallback đã diễn ra hoặc một quyết định nghiệp vụ thật có thể đáng log riêng. Điều cần loại bỏ là **nhiều bản ghi đồng nghĩa chỉ vì exception đi qua nhiều catch**, không phải những sự kiện thật sự khác nhau.

## 2. Phải phân biệt các loại “trùng” trước khi sửa

| Hiện tượng | Bản chất | Hướng chẩn đoán |
| --- | --- | --- |
| **Log cùng Throwable nhiều lần trong code** | Nhiều lời gọi logger, ví dụ DAO → service → HTTP handler | Tìm `log-and-rethrow`, chọn owner |
| **Một LogEvent tới sink hai lần** | Một lời gọi log được chuyển qua nhiều appender/handler cùng đích | Kiểm tra Logback `additivity`, JUL parent handlers |
| **Một record bị collector nhân bản** | Hai shipper hoặc stdout + file cùng ingest, batch retry | So nguồn/offset, collector, exporter |
| **Retry/redelivery hợp lệ** | Nhiều lần thử thực tế, mỗi lần có event riêng | Dùng `attempt`, `messageId`, outcome |
| **Một stack trace nhiều “Caused by”** | Chuỗi nguyên nhân của một Throwable | Không tính mỗi “Caused by” là một log event |
| **Hai request độc lập lỗi giống nhau** | Hai failure occurrences thật sự | Phân biệt requestId/traceId/instance |

Một Throwable instance có thể bị ném qua ba tầng và cả ba ghi log. Nhưng một Throwable mới được wrap bằng `new DomainException(..., ex)` vẫn có thể là **cùng một failure nguyên gốc**, chứ không bắt buộc là một lỗi mới. Ngược lại, hai request có hai Throwable với message giống hệt nhau vẫn là hai lỗi thực.

**Đếm đúng đơn vị:**

- `LogRecord`/`LogEvent` = sự kiện logging sau level/filter.
- `Throwable` = đối tượng exception, có thể được rethrow và ghi nhiều lần.
- `attempt` = một lần thử xử lý.
- `operationId`/`requestId`/`messageId` = đơn vị nghiệp vụ hoặc tương quan, có thể chứa nhiều event.
- `errorCode` = **loại lỗi**, không duy nhất cho một lần thất bại.
- `errorOccurrenceId` = ID của một lần lỗi cụ thể nếu hệ thống có contract đó.
- `eventId` của log = ID của một record nguồn nếu cần nhận diện bản sao khi transport.

Đừng deduplicate theo duy nhất exception message, error code hoặc timestamp làm tròn: có thể xóa mất những sự kiện độc lập hợp lệ.

## 3. Anti-pattern Java: log rồi ném tiếp

Ví dụ bên dưới là **ba snippet minh họa**, không phải chương trình hoàn chỉnh: `log` (SLF4J), `order`, `orderRef`, `saveToDatabase(...)` và các helper là thành phần của ứng dụng.

~~~java
// Repository: ghi lỗi rồi tiếp tục ném.
try {
    saveToDatabase(order);
} catch (SQLException ex) {
    log.error("database save failed orderRef={}", orderRef, ex);
    throw ex;
}

// Service: lại ghi cùng exception rồi ném tiếp.
try {
    orderRepository.save(order);
} catch (SQLException ex) {
    log.error("checkout failed orderRef={}", orderRef, ex);
    throw ex;
}

// HTTP boundary: lại in cùng stack trace lần ba.
try {
    checkoutService.checkout(order);
} catch (SQLException ex) {
    log.error("request failed orderRef={}", orderRef, ex);
    return serverErrorResponse();
}
~~~

Nếu controller còn ném tiếp cho `@ControllerAdvice` và global handler cũng log, có thể thành bốn lần. Lỗi không nằm ở `SQLException`; lỗi nằm ở **cách phân công trách nhiệm log**.

### Cách thay thế

Repository chuyển lỗi hạ tầng thành exception có ý nghĩa và **giữ cause**, nhưng không in stack trace:

~~~java
// Snippet trong repository adapter.
try {
    saveToDatabase(order);
} catch (SQLException ex) {
    throw new OrderStorageException(
            "ORDER_STORAGE_UNAVAILABLE", ex);
}
~~~

Service có thể ném tiếp, hoặc chuyển abstraction một lần nếu thật sự cần, mà không log cùng cause.

Boundary cuối biết `requestId`, `operation` và kết quả cuối:

~~~java
// Snippet trong HTTP boundary; không rethrow sau khi trả response.
try {
    checkoutService.checkout(order);
    return successResponse();
} catch (OrderStorageException ex) {
    log.error(
        "event=checkout_failed errorCode={} requestId={} orderRef={}",
        ex.errorCode(), requestId, safeOrderRef, ex);
    return serverErrorResponse();
}
~~~

Đoạn trên cần class `OrderStorageException` và helper/biến của ứng dụng. Khi framework đã có global exception handler giữ vai trò này, nên để handler log và trả response; **đừng vừa log ở controller vừa rethrow để framework log lại**.

**Tại sao giữ cause quan trọng?** Exception có kiểu giúp tầng trên không phụ thuộc SQL/JDBC, còn `cause` giúp kỹ sư xác định nguyên nhân thật. Không nên đổi thành `new OrderStorageException("...", null)` rồi mất ngữ cảnh; cũng không nên copy nguyên `ex.getMessage()` chứa secret vào public error response.

## 4. Một quy tắc ownership rõ cho các tầng

| Tầng | Trách nhiệm | Chính sách ghi exception thường hợp lý |
| --- | --- | --- |
| Repository / JDBC adapter | Phân loại lỗi lưu trữ, giữ cause | **Không log stack** nếu sẽ ném lên |
| Domain/service | Kiểm tra rule, chuyển exception, fallback hoặc retry | Ghi **event mới** khi có quyết định phục hồi; không log mỗi lần catch/rethrow |
| HTTP `@ControllerAdvice` / error boundary | Map status, trả lỗi an toàn, xác định outcome cuối | Một event final failure và throwable ở sink nội bộ |
| Message consumer | ACK/NACK, retry, DLQ, xác định kết quả message | Log attempt/outcome theo policy, không ghi stack ở mọi callback |
| Job/scheduler coordinator | Xác định job failed/succeeded, retry budget | Owner của final job failure |
| Async caller/worker | Theo dõi Future/stage và quyết định kết quả | Chọn **một owner**; tránh cả worker và caller cùng log stack |
| Security/audit module | Ghi hành động nhạy cảm theo policy độc lập | **Có thể bắt buộc** ghi một audit event riêng |
| Logging backend/collector | Định dạng và chuyển event đến sink | Không tự nhân bản cùng event ngoài chủ đích |

**Heuristic:** *“Nếu tầng này chỉ ném cùng một failure lên trên mà chưa xử lý, liệu bản ghi log này bổ sung điều gì không thể có tại boundary?”* Nếu không, thường bỏ log. Nếu tầng này đã có một hành động mới như retry, rollback, circuit-breaker transition hoặc compensation, đó có thể là **event khác nghĩa**, không phải bản sao.

Một hệ thống có thể dùng nhiều ranh giới: HTTP request, message processing, background job. Một request liên service có thể sinh outcome ở từng service. Điều quan trọng là **có quy ước đếm và ownership theo từng operation**, không ép toàn bộ distributed trace chỉ được có một ERROR.

## 5. Demo Java 17 độc lập: từ ba LogRecord xuống một

Chương trình sau chỉ dùng **JDK 17** (`java.util.logging`). `Capture` là test handler lưu các `LogRecord` in-memory, giúp phân biệt **số event phát tới sink** với số dòng stack trace. Chương trình chạy tuần tự, không kết nối DB thật.

Lưu file **`DoubleExceptionLogDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class DoubleExceptionLogDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.double.exception");

    static final class StorageException extends RuntimeException {
        StorageException(Throwable cause) {
            super("storage failed", cause);
        }
    }

    static final class Capture extends Handler {
        final List<LogRecord> records = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                records.add(record);
            }
        }

        @Override
        public void flush() {
            // Không có I/O đệm cần flush.
        }

        @Override
        public void close() {
            // Không giữ tài nguyên ngoài.
        }

        void clear() {
            records.clear();
        }
    }

    static void repository() {
        throw new StorageException(
                new IllegalStateException("connection interrupted"));
    }

    // Cách sai: repository log và ném tiếp.
    static void repositoryBad() {
        try {
            repository();
        } catch (StorageException ex) {
            LOG.log(Level.SEVERE,
                    "event=repository_failed errorCode=STORAGE_UNAVAILABLE",
                    ex);
            throw ex;
        }
    }

    // Cách sai: service log và ném tiếp.
    static void serviceBad() {
        try {
            repositoryBad();
        } catch (StorageException ex) {
            LOG.log(Level.SEVERE,
                    "event=service_failed errorCode=STORAGE_UNAVAILABLE",
                    ex);
            throw ex;
        }
    }

    static void boundaryBad() {
        try {
            serviceBad();
        } catch (StorageException ex) {
            LOG.log(Level.SEVERE,
                    "event=request_failed errorCode=STORAGE_UNAVAILABLE",
                    ex);
        }
    }

    // Cách tốt: boundary chịu trách nhiệm ghi lỗi cuối.
    static void boundaryGood() {
        try {
            repository();
        } catch (StorageException ex) {
            LOG.log(Level.SEVERE,
                    "event=request_failed errorCode=STORAGE_UNAVAILABLE",
                    ex);
        }
    }

    public static void main(String[] args) {
        Level previousLevel = LOG.getLevel();
        boolean previousParent = LOG.getUseParentHandlers();

        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        LOG.setLevel(Level.ALL);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(capture);

        try {
            boundaryBad();

            System.out.println(
                    "before_log_records=" + capture.records.size());

            Throwable first = capture.records.get(0).getThrown();
            boolean sameThrowable = capture.records.stream()
                    .allMatch(r -> r.getThrown() == first);
            System.out.println(
                    "before_same_throwable=" + sameThrowable);

            capture.clear();
            boundaryGood();

            System.out.println(
                    "after_log_records=" + capture.records.size());
            System.out.println(
                    "after_preserves_cause="
                    + (capture.records.get(0)
                            .getThrown().getCause() != null));
        } finally {
            LOG.removeHandler(capture);
            LOG.setUseParentHandlers(previousParent);
            LOG.setLevel(previousLevel);
            capture.close();
        }
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac -encoding UTF-8 DoubleExceptionLogDemo.java
java DoubleExceptionLogDemo
~~~

**Stdout xác định:**

~~~text
before_log_records=3
before_same_throwable=true
after_log_records=1
after_preserves_cause=true
~~~

Phân tích:

1. `repository()` tạo một `StorageException` có `IllegalStateException` làm `cause`.
2. `repositoryBad()` và `serviceBad()` gọi `LOG.log(Level.SEVERE, ..., ex)` rồi `throw ex`, giữ **cùng Throwable object**.
3. `boundaryBad()` lại log, nên `Capture.records` có ba `LogRecord` nhưng tham chiếu tới cùng một Throwable. Đây là bằng chứng cụ thể cho anti-pattern.
4. `boundaryGood()` không log ở tầng dưới, chỉ log một lần tại boundary; `getThrown().getCause()` vẫn khác null nên chuỗi nguyên nhân không bị mất.
5. `setUseParentHandlers(false)` ngăn JUL root handler xuất thêm console text ngoài ý muốn; nó không phải sửa chính anti-pattern trong code.
6. `Capture.records` dùng `ArrayList` vì demo chạy tuần tự. Không dùng handler này như thư viện logging concurrent production; nếu test nhiều thread, cần đồng bộ và cách chụp phù hợp.
7. Demo dùng event message cố định và không in stack trace để output kiểm chứng được. Logger/backend thực tế có thể format Throwable khác; việc đếm `LogRecord` đáng tin hơn số dòng text.

Logic tương đương đã được chạy bằng JShell với các API có mặt trong Java 17, cho đúng bốn dòng trên. Đây **không phải tuyên bố biên dịch file bằng riêng `javac` JDK 17 trên máy**.

## 6. Không log ở mọi catch, nhưng vẫn giữ ngữ cảnh

Một exception nên được **phân loại bằng contract**, không đoán từ chuỗi message:

~~~java
// Đây là snippet class riêng của ứng dụng.
public final class OrderStorageException extends RuntimeException {
    private final String errorCode;

    public OrderStorageException(String errorCode, Throwable cause) {
        super("Order persistence failed", cause);
        this.errorCode = errorCode;
    }

    public String errorCode() {
        return errorCode;
    }
}
~~~

Trong repository adapter, `catch(SQLException ex)` có thể ném `new OrderStorageException("ORDER_STORAGE_UNAVAILABLE", ex)`. Một tầng khác có thể bổ sung `orderRef`/`retryBudget` vào context có cấu trúc nhưng không nhất thiết in stack trace. Tại boundary, error code, requestId, outcome và throwable đủ giúp điều tra.

**Wrapper exception không làm tự động tăng số failure.** `OrderStorageException` có một `Caused by: SQLException` thì đó là **cause chain** trong một event nếu chỉ log một lần. `Throwable.addSuppressed(...)` hoặc try-with-resources cũng có thể đưa `Suppressed` vào stack trace; không coi mỗi phần là một log event riêng.

Khi chuyển loại exception, tránh:

~~~java
// Sai nếu làm mất root cause:
throw new OrderStorageException("ORDER_STORAGE_UNAVAILABLE", null);

// Đúng khi cần giữ nguyên nhân:
throw new OrderStorageException("ORDER_STORAGE_UNAVAILABLE", ex);
~~~

`ex` ở đây là Throwable đã bắt được; snippets không đủ để chạy độc lập. Không copy nguyên exception message của dependency vào public API response: nó có thể chứa SQL, URL, token hoặc thông tin nhạy cảm.

### Khi nào một tầng giữa nên log?

Khi tầng đó **thực sự đưa ra một quyết định có ý nghĩa**:

- `event=retry_scheduled` với `attempt`/`retryDelayMs`.
- `event=fallback_used` khi đi sang endpoint backup thành công.
- `event=circuit_breaker_opened` khi trạng thái circuit breaker đổi.
- `event=compensation_started` khi một saga bắt đầu rollback có chủ ý.
- `event=access_denied` ở security/audit trail nếu chính sách yêu cầu.

Chúng khác về **loại sự kiện**, không chỉ đổi câu `"Error occurred"` thành `"Service failed"`. Không nhất thiết ghi một stack trace đầy đủ ở từng event trung gian.

## 7. SLF4J: truyền Throwable theo đúng API

Ở SLF4J, truyền Throwable như một đối số exception để backend quản lý stack trace. Ví dụ:

~~~java
// Snippet trong boundary; LOG là org.slf4j.Logger.
LOG.error("event=checkout_failed errorCode={} requestId={} orderRef={}",
        "ORDER_STORAGE_UNAVAILABLE", requestId, safeOrderRef, ex);
~~~

Các biến do ứng dụng cung cấp. Với SLF4J phù hợp, đối số Throwable cuối được xử lý là cause; không cần tự stringify stack trace. Để tường minh nhất khi không cần placeholder, có thể dùng:

~~~java
LOG.error("event=checkout_failed", ex);
~~~

Các cách dễ sai:

~~~java
// Sai: log-and-rethrow khiến tầng trên có thể in lại cùng Throwable.
catch (OrderStorageException ex) {
    LOG.error("event=checkout_failed", ex);
    throw ex;
}

// Sai: System.err và backend cùng in một exception.
catch (OrderStorageException ex) {
    ex.printStackTrace();
    LOG.error("event=checkout_failed", ex);
    return errorResponse();
}

// Rủi ro: message của exception bị lặp và có thể mang PII/secret.
LOG.error("event=checkout_failed detail=" + ex.getMessage(), ex);
~~~

Các đoạn trong `catch` là snippets cần `try`, `LOG` và response helper thích hợp. `Throwable#printStackTrace()` mặc định in qua `System.err` và thoát khỏi structured logging/correlation; khi backend log Throwable tiếp, console có thể hiện hai stack trace.

**Tránh ép exception vào placeholder `{}` chỉ để hiển thị `toString()`.** Khi mục tiêu là stack trace, dùng dạng tường minh `LOG.error("Failure", ex)` hoặc cuối danh sách argument như contract của SLF4J. Test với provider/backend đang chạy để thấy output thực tế.

### Fluent API trong SLF4J 2.x

~~~java
// Snippet, chỉ dùng khi ứng dụng có SLF4J 2.x.
LOG.atError()
   .addKeyValue("event", "checkout_failed")
   .addKeyValue("errorCode", "ORDER_STORAGE_UNAVAILABLE")
   .addKeyValue("requestId", requestId)
   .setCause(ex)
   .log("Checkout failed");
~~~

Đây là một log event với một cause. Việc key–value được xuất thành JSON tùy encoder/layout, không tự xảy ra chỉ vì dùng fluent builder. Fluent API không tồn tại trong SLF4J 1.7; và quên `log()` sẽ khiến event không được phát.

## 8. HTTP controller và global exception handler

Trong ứng dụng web, exception có thể đi qua controller, interceptor, servlet filter, error resolver và `@ControllerAdvice`. Mỗi lớp **có thể** log tùy implementation/cấu hình, chứ không phải tất cả tự động log.

~~~text
Request -> Controller -> Service -> Repository throws
             |
             +-- catch/log/rethrow?
             |
             v
         Global exception handler
             |
             +-- map status/public-safe error
             +-- log terminal failure?
             |
             v
         HTTP response
~~~

Nếu controller đã ghi full stack rồi rethrow, global handler lại log, **code đang tự nhân đôi event**. Chọn contract rõ:

1. Service/repository giữ exception type/cause, không log chỉ vì rethrow.
2. Controller không catch chỉ để in stack rồi rethrow.
3. Handler chịu trách nhiệm map status/public response và ghi **một** final failure event khi cần.
4. Filter có thể ghi access event như `request_completed`, duration và status, nhưng không nhất thiết ghi lại Throwable.
5. Kiểm tra framework/container error logging mặc định nếu dùng rethrow cho framework; đừng vừa ghi thủ công vừa yêu cầu framework ghi lần nữa.

Đối với 4xx dự kiến, một exception domain có thể chỉ cần INFO/WARN hoặc metrics. Không nhất thiết tạo một ERROR kèm stack trace cho mọi validation failed hoặc 404. Một unexpected 500 có thể cần một ERROR ở boundary, cùng requestId và code an toàn để support.

**Không xuất full exception stack trong HTTP response** với lý do “chỉ log một lần”: response có quyền xem khác với log nội bộ. Dùng public-safe error code và correlation ID.

## 9. Exception trong Future, CompletableFuture và worker

Với `ExecutorService.submit(...)`, lỗi từ worker được giữ trong `Future`. Caller nhận `ExecutionException` khi gọi `Future.get()` và có thể truy nguyên nhân qua `getCause()`. Nếu worker đã log rồi rethrow, caller lại log ở catch của `get()`, một failure có hai stack trace.

~~~java
// Anti-pattern dạng snippet: executor, LOG, performWork() có sẵn.
Future<?> future = executor.submit(() -> {
    try {
        performWork();
    } catch (RuntimeException ex) {
        LOG.error("event=worker_failed", ex);
        throw ex;
    }
});

try {
    future.get();
} catch (ExecutionException ex) {
    LOG.error("event=job_failed", ex.getCause());
}
~~~

Cách tốt hơn phụ thuộc **ai sở hữu outcome cuối**:

- **Caller/job coordinator là owner:** worker chỉ ném exception, caller quyết định retry/fail và log một lần.
- **Worker là operation độc lập và tự finalize:** worker có thể ghi một lỗi cuối, caller ghi trạng thái tổng hợp mà không in lại cùng stack.
- **Cần hai sự kiện khác nghĩa:** `task_attempt_failed` và `job_failed_after_retries`; mỗi event có `attempt`/`outcome`, full stack chỉ tại nơi có giá trị.

Với `CompletableFuture`, các callback `whenComplete`, `handle`, `exceptionally` và lời gọi `join()` đều có thể quan sát cùng failure; `join()` thường ném `CompletionException`. Nếu mọi callback gọi `LOG.error("failed", throwable)` rồi propagate, lỗi bị log theo số callback. Chọn một boundary, dùng callback còn lại cho cleanup, mapping hoặc metrics thích hợp.

**Không coi `ExecutionException`/`CompletionException` là các business errors mới mặc nhiên.** Chúng thường là wrapper. Mapper nên phân loại cause theo contract của ứng dụng, không log wrapper stack riêng rồi log root cause lần nữa chỉ để thấy hai chuỗi `Caused by`.

Khi catch `InterruptedException` để cleanup, giữ semantics interruption và có thể phục hồi interrupt flag đúng cách nếu không ném lại. Không bắt `Throwable` rộng rồi tiếp tục chạy bình thường, đặc biệt với `Error` như `OutOfMemoryError`.

### Context qua thread pool

MDC thường gắn với thread; khi worker và caller ghi log, cần truyền/capture context ở boundary. Nếu worker tái sử dụng thread còn requestId của request trước, việc có hai log “giống nhau” càng khó điều tra. Dọn MDC trong `finally`, dùng propagation tương ứng với logging/tracing framework, không gắn dữ liệu nhạy cảm vào global static state.

## 10. Retry và message redelivery: có những log khác nhau hợp lệ

Ví dụ với cùng messageId:

~~~text
event=attempt_failed messageId=msg-1001 attempt=1 errorCode=PAY-TIMEOUT
event=retry_scheduled messageId=msg-1001 attempt=1 delayMs=500
event=attempt_failed messageId=msg-1001 attempt=2 errorCode=PAY-TIMEOUT
event=message_dead_lettered messageId=msg-1001 attempts=2 outcome=failure
~~~

Bốn dòng mô tả **bốn mốc vận hành**, không phải bốn bản sao cùng một LogEvent. Nhưng nếu mỗi mốc đều in full stack trace giống nhau, chi phí và nhiễu vẫn cao. Một policy phù hợp có thể ghi attempt failure ở WARN với errorCode/retry metadata, và một terminal failure ở ERROR có Throwable sau khi hết retry budget.

Đừng xóa các attempt events chỉ vì chúng mang cùng errorCode. Với at-least-once message delivery, broker có thể giao lại sau khi side effect đã commit nhưng trước ACK; log phải phân biệt **messageId**, **delivery/attempt**, **processing outcome**. Nếu business side effect không được phép lặp, cần **idempotency** độc lập với việc giảm log.

### Trong một distributed trace

Service B có thể ghi `event=payment_service_failed` vì công việc của B thật sự thất bại, còn Service A ghi `event=checkout_failed` vì phụ thuộc B dẫn đến một request A thất bại. Đó có thể là **hai operation outcomes khác nhau ở hai service**; không tự động xóa một vì chúng cùng traceId. Khi tính SLO, chọn ranh giới đo và service rõ ràng, không cộng mọi ERROR trong trace thành số request cuối thất bại.

## 11. Phân biệt anti-pattern code với backend nhân đôi event

Đừng sửa catch/rethrow nếu vấn đề thực sự nằm ở logging configuration:

~~~text
Java logger calls -> LogEvent
                       |
                       +--> logger/appender hierarchy
                       |
                       +--> stdout + file sinks
                                   |
                                   v
                             shipper/collector
                                   |
                                   v
                              backend/index
~~~

**Logback additivity:** khi logger con có appender và cùng appender còn được gắn ở root, mặc định event có thể đi tới sink hai lần nhờ additivity. Ví dụ cấu hình **snippet** (phải có `CONSOLE` đã định nghĩa):

~~~xml
<logger name="com.example.orders" level="DEBUG">
    <appender-ref ref="CONSOLE"/>
</logger>
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

Nếu dùng console chung, chỉ gắn tại root và dùng logger con chỉnh level. Không đặt `additivity="false"` cho mọi logger một cách bừa bãi; nếu không có appender riêng, log có thể biến mất.

**JUL parent handlers:** `java.util.logging.Logger` có thể chuyển `LogRecord` tới handler của logger hiện tại và của parent nếu `useParentHandlers=true`. Kiểm tra `getHandlers()` và việc đăng ký handler hai lần, thay vì chỉ nhìn message.

**Collector:** một event nguồn có thể được ingest qua cả console và file; retry batch khi ACK không chắc chắn cũng có thể tạo bản sao. Nếu log nguyên bản của process chỉ có một dòng nhưng index có hai, ưu tiên xem shipper/collector và query. Đừng dedup bằng `requestId` hay `exceptionType` vì một request có nhiều event đúng.

**Chuỗi cause:** `Caused by` và `Suppressed` chỉ là thành phần trong một stack trace, không phải dấu hiệu logger đã được gọi nhiều lần. Đếm record tại sink mới phân biệt được.

## 12. Một final failure event nên chứa gì?

Ví dụ structured log **minh họa**, không tự động là output của JUL/SLF4J:

~~~json
{
  "timestamp": "2026-11-10T03:00:00Z",
  "level": "ERROR",
  "service": "checkout",
  "event": "checkout_failed",
  "errorCode": "ORDER_STORAGE_UNAVAILABLE",
  "requestId": "req-101",
  "traceId": "4f0e2c13b69a497389d74e71a52b4e62",
  "operation": "place_order",
  "attempt": 3,
  "outcome": "failed",
  "durationMs": 2450,
  "exceptionType": "OrderStorageException"
}
~~~

Ngoài các field này, backend có thể giữ throwable/stack trace ở sink nội bộ có quyền. Phân biệt:

- `errorCode` = loại lỗi, thuộc catalog hữu hạn.
- `requestId`/`traceId` = tương quan nhiều event; không là unique log ID.
- `attempt` = lần thử, không đưa vào tên errorCode.
- `outcome` = kết quả cuối hoặc mốc tạm; không suy từ level.
- `messageId`/`jobId` = đơn vị async có thể có nhiều attempts.
- `eventId` = từng log event nếu cần dedup transport, khác requestId.
- `exceptionType` hữu ích cho debug nhưng có thể đổi khi refactor; không thay mã lỗi domain.

Với SLF4J 2.x, dùng `addKeyValue` và `setCause` để tạo event có cấu trúc; cần cấu hình encoder đúng để các field thực sự được xuất. Không lạm dụng MDC để lưu `errorCode` cho cả request nếu một lỗi đã được xử lý rồi các log thành công phía sau sẽ mang code cũ.

## 13. Bảo mật: log lặp làm lộ dữ liệu nhiều lần hơn

Một exception không chỉ chứa class và stack frame; `getMessage()`, cause, suppressed exception hoặc dependency metadata có thể chứa hostname, database name, SQL literals, URL query, access token hoặc PII.

Những yêu cầu quan trọng:

1. Không ghi password, token, cookie, private key, OTP hoặc dữ liệu nhạy cảm ngoài chính sách.
2. Log event name và errorCode hữu hạn, không ghép nguyên `ex.getMessage()` vào public error hay field dynamic.
3. Truyền Throwable một lần vào sink nội bộ được bảo vệ, có redaction và quyền truy cập phù hợp.
4. Kiểm soát log injection từ newline/control character trong input; parameterized logging **không tự bảo đảm** dữ liệu đã được sanitize.
5. Giữ `requestId`, `traceId` và định danh nghiệp vụ dạng ít nhạy cảm khi có thể; không dùng email/phone làm correlation key mặc định.
6. Giữ audit/security events bắt buộc dù chúng cùng incident với log lỗi: chúng có purpose, schema và retention riêng.

Việc bỏ stack trace dư thừa **không thay thế** RBAC, encryption, retention và quy trình ứng phó sự cố. Ngược lại, không được lấy “log once” làm lý do tắt hết audit logging hoặc che các hành vi truy cập bất thường.

## 14. Kiểm thử bằng số LogRecord, không chỉ mock logger

### Unit test

Dùng capturing handler/appender của backend thực:

- Một request ném exception từ repository qua service tới boundary → **đúng một final failure record** ở sink được chọn nếu đó là policy.
- Cause chain được bảo toàn: `getThrown().getCause()` còn thông tin gốc.
- Hai request lỗi tương tự → hai occurrences riêng, không bị dedup nhầm vì cùng errorCode.
- Một retry rồi thành công → vẫn có attempt/fallback events theo policy, nhưng không có false terminal failure.
- Một retry hết budget → có terminal failure đúng một lần cho operation cuối và các attempt events cần thiết.
- Worker và caller cùng quan sát exception → không cả hai ghi full stack trace khi chỉ caller là owner.
- `CompletableFuture` callback propagation → không nhân bản cùng event ở nhiều callback.
- Một validation 4xx dự kiến → log level phù hợp, không mặc định ERROR stack trace.

### Integration test

- **Spring/web framework:** kiểm tra controller, filter, advice và error resolver có cùng log exception không.
- **Logback/JUL:** chỉ một lời gọi logger tới đúng sink; test additivity/parent handlers và appender registration.
- **Collector:** một event nguồn có bị thu hai lần từ stdout/file hoặc queue retry không.
- **Thread pool:** MDC/requestId của task A không rò sang task B.
- **Message consumer:** crash trước ACK và redelivery không gây side effect lặp; log phân biệt attempt.
- **Privacy:** marker dữ liệu giả nhạy cảm không xuất vào sink không được phép, bao gồm stack trace.
- **Performance:** đo số events, ingest bytes, chi phí khi nhiều exception, không tạo stress cho ổ production.

Một test chỉ mock `LOG.error(...)` trong controller **không chứng minh backend chỉ ghi một record**, vì cấu hình Logback/JUL/collector có thể nhân đôi. Test tại **sự kiện thực nhận ở sink** hoặc đọc stdout/ingest trong môi trường tích hợp.

## 15. Runbook khi production có nhiều stack trace giống nhau

1. Lấy một nhóm log nghi lặp với timestamp chính xác, `logger`, `requestId`, `traceId`, `errorCode`, `attempt` và `service.instance`.
2. Kiểm tra log **nguyên bản của một process**: nếu đã có nhiều records, tìm nơi gọi logger và appender. Nếu chỉ một nhưng backend nhiều, tìm collector/index.
3. Xác định exception được tạo ở đâu, catch/rethrow/wrap ở lớp nào, ai đã xử lý và ai quyết định outcome cuối.
4. Kiểm tra controller, global handler, interceptor, Future/callback, message retry và framework error logger.
5. Chọn một owner cho terminal failure; các tầng khác chỉ log **event có ý nghĩa khác** hoặc ném exception giữ `cause`.
6. Bảo đảm không loại security/audit event cần giữ và không làm mất stack trace phục vụ debug.
7. Test số LogRecord, các điều kiện retry/fallback và structured fields trước khi deploy.
8. Kiểm tra routing của appender, stdout/file và collector để phát hiện nguồn trùng đồng thời.
9. So sánh trước/sau: số failed operations thực, số ERROR records, ingest bytes, alert noise, queue drops.
10. Cập nhật code review guideline và runbook để anti-pattern không quay lại.

Đừng chạy một job “xóa các dòng giống nhau” trong backend làm biện pháp đầu tiên. Nó không giảm format/I/O nguồn và có thể xóa nhầm hai request hợp lệ có message giống nhau. Chỉ dedup record transport nếu có `eventId`/provenance và contract rõ.

## 16. Những cách sửa sai thường gặp

| Cách sửa vội | Hậu quả | Cách đúng |
| --- | --- | --- |
| Bỏ mọi `LOG.error` trong mọi service | Mất event fallback/recovery thật | Giữ sự kiện có ý nghĩa, bỏ log-and-rethrow dư |
| Tăng log level để bớt dòng | Hai ERROR vẫn có thể lặp, mất INFO hữu ích | Chọn owner log và sửa routing |
| Đặt `additivity=false` cho mọi logger | Logger không có appender riêng có thể mất log | Chỉ sửa sau khi xác định lỗi hierarchy |
| Bỏ hoàn toàn Throwable khỏi mọi log | Mất root cause khi cần điều tra | Giữ một Throwable ở sink nội bộ phù hợp |
| `printStackTrace()` rồi `LOG.error(...)` | Hai bản xuất ra stderr/backend | Dùng logging API một lần |
| Bọc exception không giữ `cause` | Không truy ra lỗi gốc | Dùng constructor có cause |
| Catch `Throwable` rồi chạy tiếp | Có thể nuốt fatal Error/interrupt | Tôn trọng lifecycle và exception type |
| Worker và caller cùng log | Một async failure thành hai stack traces | Phân công ownership rõ |
| Đếm ERROR log làm failed requests | Sai khi retry/nhiều sink | Đếm terminal outcome hoặc HTTP status thực |
| Dùng requestId làm log event ID | Một request có nhiều event hợp lệ | ID mỗi event riêng nếu cần ingest dedup |
| Tắt audit cho “đỡ trùng” | Mất chứng cứ và có thể vi phạm retention | Audit và diagnostic log tách mục đích |
| Log `ex.getMessage()` ra public response | Lộ hệ thống, dữ liệu nhạy cảm | Public-safe code/message + correlation ID |
| Chỉ test mock logger | Bỏ qua appender/collector duplication | Đếm LogRecord/appender output thực |
| Dedup bằng message thuần | Gộp hai requests độc lập | So context, attempts, eventId/provenance |

## 17. Checklist code review

- [ ] Có `catch` nào chỉ log rồi `throw ex`/`throw new Exception(..., ex)` không?
- [ ] Ai chịu trách nhiệm ghi **terminal failure** tại HTTP, message hoặc job boundary?
- [ ] Đã giữ `cause` mà không ghi cùng stack trace ở mọi layer chưa?
- [ ] Có event trung gian thật (`retry_scheduled`, `fallback_used`, `audit_decision`) cần giữ không?
- [ ] `ERROR`/`WARN` được chọn theo impact và final outcome, không đơn thuần theo HTTP status?
- [ ] `errorCode`, `requestId`, `traceId`, `messageId` và `attempt` có đúng ý nghĩa không?
- [ ] Worker, Future.get, CompletableFuture callbacks có log lặp cùng failure không?
- [ ] Controller/filter/global handler/framework có cùng ghi một exception không?
- [ ] Appender additivity, JUL parent handlers hoặc collector có nhân bản một event không?
- [ ] Test đếm event tại sink đã được thực hiện, không chỉ mock log API?
- [ ] Metrics/SLO có đếm outcome cuối thay vì số dòng ERROR?
- [ ] Stack trace/exception message không làm lộ secret và audit events vẫn được bảo toàn?

**Ghi nhớ:** Một exception đi qua nhiều catch không mặc nhiên là nhiều lỗi. **Đừng log ở mỗi tầng rồi ném tiếp.** Hãy giữ `cause`, phân loại `errorCode`, ghi các quyết định thực sự phát sinh ở từng tầng, và để ranh giới chịu trách nhiệm đưa ra **một log có ích cho outcome cuối**. Đồng thời phân biệt log trùng do **appender/collector** và sự kiện retry/audit **hợp lệ** để không chữa triệu chứng bằng cách mất log quan trọng.

### Tài liệu tham khảo chính thức

- Java SE 17 — [`java.util.logging.Logger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html), [`LogRecord`](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html), [`Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html).
- Java SE 17 — [`ExecutionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html), [`CompletionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html).
- SLF4J — [Manual: parameterized logging và Fluent API](https://www.slf4j.org/manual.html).
- Logback — [Architecture: Logger/Appender/additivity](https://logback.qos.ch/manual/architecture.html), [Configuration](https://logback.qos.ch/manual/configuration.html).
- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html).
