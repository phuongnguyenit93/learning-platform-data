# Chọn nơi ghi lỗi trong Java Core Logging

## 1. “Nơi ghi lỗi” có hai ý nghĩa

Khi một exception xuất hiện trong ứng dụng Java, câu hỏi không chỉ là **có gọi logger hay không**, mà còn là:

1. **Tầng hoặc thành phần nào có trách nhiệm ghi nhận lỗi?** Ví dụ repository, service, HTTP exception handler, message consumer hay job runner.
2. **Sự kiện lỗi được xuất tới đích nào?** Ví dụ console, file, bộ thu thập log tập trung, kênh cảnh báo hoặc audit trail chuyên biệt.

Hai quyết định này liên quan nhưng không đồng nhất. Một `Logger` ở API boundary có thể phát **một sự kiện lỗi**, trong khi logging backend phân phối sự kiện đó tới nhiều handler/appender. Ngược lại, ba tầng Java cùng gọi `logger.error` cho một exception không có nghĩa hệ thống đáng tin hơn: nó có thể chỉ tạo ba dòng trùng, gây tăng chi phí và làm nhiễu điều tra.

**Quy tắc thực hành:** ưu tiên ghi lỗi tại **ranh giới nơi thành phần thực sự biết kết quả cuối cùng và có đủ ngữ cảnh để quyết định cách xử lý**. Ở tầng thấp, nếu chưa xử lý được, hãy truyền exception lên và giữ nguyên nguyên nhân (`cause`). Đừng dùng quy tắc “log một lần” một cách máy móc: nhiều sự kiện khác nhau, nhiều boundary khác nhau hoặc một lần retry có kết quả riêng vẫn có thể xứng đáng có log, miễn mỗi log mang thông tin mới và mục đích rõ ràng.

### Ví dụ một request nhiều tầng

~~~text
HTTP request
   |
   v
Controller / REST boundary    <-- chuyen exception thanh HTTP response,
   |                               biet requestId, ma loi va outcome
   v
OrderService                 <-- quyet dinh nghiep vu / retry
   |
   v
OrderRepository              <-- gap SQLException / ket noi DB hong
   |
   +-- wrap exception, giu cause, KHONG tu log neu chi rethrow
   |
   v
OrderService                 <-- propagate; co the enrich context
   |
   v
HTTP boundary                <-- log terminal failure MOT LAN
   |
   +--> Logging backend ------> console / file / collector theo policy
   |
   +--> Tra response an toan cho client
~~~

Sơ đồ trên là **một cách tổ chức phổ biến**, không phải yêu cầu mọi ứng dụng đều đặt log tại controller. Với ứng dụng chạy nền, boundary có thể là worker, scheduler, consumer, CLI hoặc bộ điều phối job.

## 2. Vì sao logging ở mọi `catch` thường là lỗi thiết kế?

Một anti-pattern điển hình:

~~~java
// Minh hoa sai lam, khong phai chuong trinh doc lap.
try {
    repository.save(order);
} catch (SQLException ex) {
    logger.log(Level.SEVERE, "Repository failed", ex);
    throw new StorageFailure("SAVE_FAILED", ex);
}

// Ở service:
try {
    saveOrder();
} catch (StorageFailure ex) {
    logger.log(Level.SEVERE, "Service failed", ex);
    throw ex;
}

// Ở API:
try {
    createOrder();
} catch (StorageFailure ex) {
    logger.log(Level.SEVERE, "HTTP request failed", ex);
    return serverErrorResponse();
}
~~~

Ba đoạn mã là **mã tích hợp minh họa**, phụ thuộc các biến/class/method đã có, không biên dịch độc lập. Cùng một sự cố hạ tầng có thể tạo ba stack trace gần như giống nhau.

Hậu quả gồm:

- Log volume, chi phí thu thập và chi phí lưu tăng theo độ sâu call stack.
- Một lỗi thực tế có thể bị đếm như nhiều incident, gây báo động giả.
- Context bị rải rác; dòng ở repository không biết outcome cuối cùng là retry thành công, fallback hay HTTP 503.
- Việc log exception sớm có thể chứa raw SQL, đường dẫn, dữ liệu cá nhân hoặc credential.
- Các cấp độ `ERROR`/`SEVERE` có thể bị lạm dụng dù lỗi đã được xử lý hoặc có đường phục hồi.

Cách viết phù hợp hơn khi repository **không xử lý được**:

~~~java
// Doan minh hoa: StorageFailure la exception do ung dung dinh nghia.
try {
    repository.save(order);
} catch (SQLException cause) {
    throw new StorageFailure("SAVE_FAILED", cause);
}
~~~

Ở đây constructor của `StorageFailure` phải nhận và giữ `cause`, không nuốt nguyên nhân. Tầng trên có thể quyết định retry hoặc báo thất bại cuối cùng. Nếu service thực sự **fallback thành công**, thường không nên báo “request failed” ở mức lỗi nghiêm trọng, mà nên ghi sự kiện fallback/độ suy giảm phù hợp.

**Nguyên tắc phân biệt:** *Bắt exception* là hành vi điều khiển luồng; *ghi log* là một quyết định quan sát vận hành. Không phải mọi `catch` đều cần log.

## 3. Xác định nơi ghi lỗi theo quyền sở hữu kết quả

Để chọn tầng chịu trách nhiệm, đặt lần lượt các câu hỏi:

1. **Tầng này đã xử lý xong lỗi chưa?** Nếu có kết quả cuối cùng hoặc fallback thật sự, log outcome tại đây có ý nghĩa.
2. **Tầng này có đủ ngữ cảnh không?** Request ID, operation, mã lỗi chuẩn, retry count, resource category và đích phản hồi thường chỉ rõ ở boundary.
3. **Lỗi có còn được ném lên không?** Nếu chỉ bổ sung context rồi rethrow, tránh log cùng exception ở mọi tầng.
4. **Ai sẽ hành động dựa trên log?** On-call, đội bảo mật, developer hay bộ phận vận hành có cần nhận thông tin tại vị trí đó không?
5. **Một tầng khác có tự động log lỗi này không?** Web framework, servlet container, message framework và global exception handler có thể đã ghi nó.

| Tình huống | Nơi thường nên ghi | Lý do |
| --- | --- | --- |
| HTTP request thất bại sau khi xử lý cuối cùng | Global exception handler / request boundary | Biết method, route mẫu, request ID, status và error code |
| Repository gặp lỗi và chỉ wrap/rethrow | Thường **không** ghi tại repository | Chưa biết lỗi có được retry, fallback hay xử lý ở trên |
| Service đã thử fallback và thực sự thành công | Tại service thực hiện fallback, nếu có giá trị vận hành | Ghi **degradation/fallback**, không tuyên bố toàn request đã fail |
| Scheduled job kết thúc thất bại | Job runner / scheduler boundary | Biết job ID, số lần thử và outcome cuối |
| Message consumer lỗi tạm thời | Retry coordinator/consumer policy | Biết có retry, backoff hay đã đưa DLQ |
| Lỗi không được bắt trong một thread | Uncaught exception boundary như cơ chế phòng vệ cuối | Có thể ghi lỗi không được xử lý; không thay cho giám sát job/worker |
| Hành động bảo mật cần audit | Kênh audit có schema riêng theo policy | Mục đích kiểm chứng khác log chẩn đoán |
| Một thành phần phát hiện corruption của dữ liệu cục bộ | Thành phần sở hữu dữ liệu, đồng thời thông báo upstream | Có thể cần một event độc lập vì đây không chỉ là cùng exception bị rethrow |

**Nơi có đủ ngữ cảnh thường tốt hơn nơi exception được tạo ra.** Dù vậy, nếu một tầng sở hữu cơ chế phục hồi, circuit breaker hoặc tính toàn vẹn dữ liệu, nó có thể cần ghi một sự kiện riêng — ví dụ `fallback_activated` hoặc `cache_entry_evicted`. Khi đó hãy mô tả **hành động đã thực hiện**, chứ không lặp lại toàn bộ stack trace.

## 4. Ví dụ Java 17 chạy độc lập: một exception, một boundary log

Ví dụ sử dụng `java.util.logging` (JUL) có sẵn trong JDK 17. Repository mô phỏng lỗi từ tầng thấp và **wrap với cause**; service chỉ chuyển tiếp; HTTP boundary mô phỏng quyết định cuối là trả `503` và ghi **một** event lỗi.

Để kết quả có thể kiểm chứng, formatter trong ví dụ chỉ in message và **loại exception**, không in stack trace (cố ý). `LogRecord` vẫn giữ `Throwable` được truyền vào; trong ứng dụng production, formatter/backend ở kênh hạn chế quyền có thể ghi stack trace đã được xem xét dữ liệu nhạy cảm.

Tạo file `ErrorLoggingBoundaryDemo.java`:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ErrorLoggingBoundaryDemo {
    private static final Logger LOGGER =
            Logger.getLogger("demo.error.boundary");

    private static final class StorageUnavailableException
            extends RuntimeException {
        StorageUnavailableException(Throwable cause) {
            super("STORAGE_UNAVAILABLE", cause);
        }
    }

    private static final class OrderRepository {
        void load(String orderId) {
            try {
                // Mo phong loi ha tang, khong phai DB thuc.
                throw new IllegalStateException("simulated storage outage");
            } catch (IllegalStateException cause) {
                // Giu nguyen cause; KHONG log roi lai rethrow.
                throw new StorageUnavailableException(cause);
            }
        }
    }

    private static final class OrderService {
        private final OrderRepository repository = new OrderRepository();

        void load(String orderId) {
            repository.load(orderId);
        }
    }

    private static void handleRequest(String requestId) {
        OrderService service = new OrderService();
        try {
            service.load("order-demo-42");
            System.out.println("response=200 requestId=" + requestId);
        } catch (StorageUnavailableException failure) {
            // Boundary biet outcome cuoi cung la 503.
            LOGGER.log(Level.SEVERE,
                    "event=order_load_failed requestId=" + requestId
                    + " errorCode=STORAGE_UNAVAILABLE",
                    failure);
            System.out.println("response=503 requestId=" + requestId);
        }
    }

    public static void main(String[] args) {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.ALL);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String exceptionType = record.getThrown() == null
                        ? ""
                        : " exceptionType="
                          + record.getThrown().getClass().getSimpleName();
                return record.getLevel().getName() + ": "
                        + formatMessage(record)
                        + exceptionType
                        + System.lineSeparator();
            }
        });
        LOGGER.addHandler(handler);

        try {
            handleRequest("req-101");
        } finally {
            LOGGER.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ErrorLoggingBoundaryDemo.java
java ErrorLoggingBoundaryDemo
~~~

**Stdout chính xác:**

~~~text
response=503 requestId=req-101
~~~

**Stderr chính xác:**

~~~text
SEVERE: event=order_load_failed requestId=req-101 errorCode=STORAGE_UNAVAILABLE exceptionType=StorageUnavailableException
~~~

`ConsoleHandler` của JUL ghi vào **stderr**, còn ví dụ dùng `System.out.println` để mô phỏng response. Khi terminal gộp cả stdout và stderr, thứ tự hiển thị giữa hai luồng không được bảo đảm; vì vậy kết quả được nêu riêng.

### Những điều cần học từ ví dụ

1. **Repository:** chuyển lỗi hạ tầng thành `StorageUnavailableException` có cause, không tự ghi thêm một `SEVERE`.
2. **Service:** truyền exception lên, vì service không có chính sách retry/fallback trong demo.
3. **Boundary:** biết kết quả cuối là `503`, nên phát event `order_load_failed` cùng request ID và error code.
4. **Throwable được đính kèm:** overload `LOGGER.log(Level.SEVERE, message, failure)` đặt exception vào `LogRecord`; formatter demo in loại exception chứ không in stack trace. Backend thực có thể chọn chính sách khác.
5. **Không tiết lộ lỗi nội bộ cho client:** response demo chỉ chứa status và request ID, không gửi thông tin hạ tầng hoặc exception message.
6. **Không log nguyên dữ liệu nghiệp vụ:** ID trong ví dụ là giá trị giả ổn định; trong hệ thống thật, request ID và resource ID vẫn cần phân loại theo chính sách riêng tư.
7. **`setUseParentHandlers(false)`:** cô lập log demo khỏi handler của logger cha, tránh output phụ trùng. Trong ứng dụng thật, cần hiểu cấu hình logger hierarchy trước khi tắt kế thừa.

**Giới hạn:** chương trình không mở HTTP socket, không gọi database và không chứng minh cách Spring/Jakarta tự động chuyển exception. Đây là ví dụ JDK độc lập mô phỏng boundary để tập trung vào **vị trí ghi lỗi** và **giữ cause**.

## 5. `log and rethrow` hay `propagate with cause`?

### Khi nào không nên `log and rethrow`?

Nếu tầng dưới không có hành động bổ sung hoặc không nắm outcome cuối, cách sau dễ tạo log trùng:

~~~java
// Doan ma tich hop, khong chay doc lap.
catch (SQLException ex) {
    logger.log(Level.SEVERE, "Database query failed", ex);
    throw new StorageFailure("STORAGE_UNAVAILABLE", ex);
}
~~~

Tầng trên sẽ thấy `StorageFailure`, và có thể tiếp tục log lại exception cùng stack trace.

Thường nên làm:

~~~java
// Doan ma tich hop; StorageFailure duoc dinh nghia rieng
// va constructor cua no phai luu cause.
catch (SQLException ex) {
    throw new StorageFailure("STORAGE_UNAVAILABLE", ex);
}
~~~

Khi cần bổ sung ngữ cảnh, dùng mã operation và `cause`; tránh nối raw SQL, token hoặc payload vào exception message. Nếu tầng dưới **đã xử lý lỗi** (ví dụ vô hiệu hóa cache record bị hỏng hoặc chuyển sang read replica), nó có thể log một event mang ý nghĩa độc lập như `cache_entry_discarded` hay `read_replica_fallback`.

### Không nuốt exception

~~~java
// Sai neu loi khong thuc su duoc xu ly.
try {
    performCriticalOperation();
} catch (Exception ignored) {
    // Khong lam gi: caller co the tuong xu ly da thanh cong.
}
~~~

Không xử lý và không truyền lỗi lên khiến tầng trên **không có thông tin để ghi đúng outcome**. Trường hợp “best effort” thực sự được chấp nhận cần được tài liệu hóa và thường nên có metric hoặc log sự kiện phù hợp.

### Không bắt `Throwable` một cách đại trà

`Throwable` bao gồm `Error` (ví dụ lỗi nghiêm trọng về tài nguyên/runtime), không chỉ `Exception`. Một HTTP boundary hoặc worker thường không nên bắt `Throwable` rồi tiếp tục như không có gì. Chỉ thực hiện thao tác phù hợp với hợp đồng framework và quy trình shutdown. Đối với `InterruptedException`, nếu đã bắt mà không ném tiếp, thường cần khôi phục trạng thái interrupt qua `Thread.currentThread().interrupt()` để không phá cơ chế hủy tác vụ.

## 6. Chọn mức log theo kết quả, không chỉ theo loại exception

Severity không đồng nghĩa “có exception thì phải ERROR”. Mức phù hợp phụ thuộc khả năng phục hồi, tác động, tần suất và việc hệ thống có cần can thiệp hay không.

| Tình huống | Mức thường cân nhắc | Vì sao |
| --- | --- | --- |
| Người dùng nhập dữ liệu không hợp lệ, trả 400 đúng kỳ vọng | `DEBUG`/`FINE` hoặc `INFO`; đôi khi không log từng request | Đây có thể là luồng kiểm tra hợp lệ bình thường |
| Truy cập bị từ chối theo quyền, trả 403 | Theo chính sách security/audit; log vận hành không nhất thiết `ERROR` | Cần phân biệt expected denial và dấu hiệu tấn công |
| Tài nguyên không tồn tại, trả 404 bình thường | `DEBUG`/`INFO` hoặc access log | Không nên tạo on-call alert cho mọi lần 404 |
| Timeout được retry thành công | `DEBUG`/`FINE` hoặc `WARNING` cho event retry nếu hữu ích | Request cuối đã thành công; metrics cho retry giúp quan sát |
| Fallback thành công nhưng chất lượng suy giảm | `WARNING` thường hợp lý | Có degraded service cần theo dõi, không phải hoàn toàn thất bại |
| Dependency lỗi và request cuối trả 503 | `SEVERE` trong JUL, `ERROR` trong SLF4J khi đúng policy | Lỗi tác động tới kết quả và cần điều tra |
| Lỗi xử lý message đã hết retry, vào DLQ | Log terminal outcome theo chính sách | Không spam một stack trace `ERROR` ở mọi attempt |
| Không thể ghi audit event bắt buộc | Cảnh báo/incident có ưu tiên riêng, có thể fail closed | Không thể coi chỉ log `WARN` là đã bảo đảm audit |

**JUL không có enum `ERROR`:** mức thường được dùng cho lỗi nghiêm trọng là `Level.SEVERE`; cảnh báo là `Level.WARNING`. Các thư viện SLF4J/Logback/Log4j 2 thường có `ERROR` và `WARN`. Không nên dùng tên level lẫn lộn khi viết code ví dụ.

Số lượng exception không phải số lượng request thất bại: một request có thể có nhiều retry nhưng cuối cùng thành công. Metrics như `http_requests_total{outcome=...}`, `dependency_retries_total` và `job_failures_total` giúp đo tác động tốt hơn việc đếm thô số dòng `ERROR`.

## 7. Chọn boundary cho từng loại ứng dụng

### 7.1. Web API / REST

Trong HTTP application, **global exception handler** hoặc middleware/filter tập trung thường có đủ status, route mẫu, request ID và error code để ghi log terminal failure một lần. Ví dụ quy tắc:

~~~text
OrderRepository throws StorageFailure (cause preserved)
     |
OrderService propagates or handles/retries
     |
Global HTTP exception handler:
  - maps expected errors to 4xx, unexpected ones to 5xx
  - logs a structured event at appropriate level
  - returns sanitized response containing requestId/errorCode
~~~

Mã controller/framework cần tuân theo vòng đời cụ thể của Spring MVC, Jakarta Servlet, Quarkus, Micronaut hoặc framework đang dùng. Một exception đã được handler ghi có thể lại bị container ghi nếu tiếp tục ném ra sau khi trả response, nên phải xác định một nơi sở hữu log cuối cùng.

**Đừng log raw request URL hay body**: query string, header và exception message có thể chứa PII, token hoặc dữ liệu khách hàng. Ưu tiên `routePattern`, request ID, status, duration và error code.

### 7.2. Message consumer và background worker

Message consumer có thể **nack/requeue**, retry với backoff, đưa message vào dead-letter queue/topic hoặc xử lý thành công bằng fallback. Vì thế nơi log terminal failure thường là **consumer error handler/retry coordinator**, nơi biết message đã thực sự được ack, đưa DLQ hay chưa.

Một event `message_process_attempt_failed` có thể ở `DEBUG`/`INFO` để quan sát attempt; sau khi hết retry, event `message_dead_lettered` có thể có severity cao hơn. **“Đã có ý định gửi DLQ” không đồng nghĩa broker xác nhận lưu DLQ**. Nếu việc publish DLQ thất bại, phải phân biệt outcome và tránh ack bản gốc quá sớm theo chính sách.

Với Kafka, việc commit offset có ngữ nghĩa khác ack riêng của một số queue broker; không sao chép một mẫu logging/ack cho tất cả sản phẩm. Dùng message ID/correlation ID và reason code đã được chuẩn hóa, không dump payload nhạy cảm.

### 7.3. Scheduled jobs / batch

Một job runner biết `jobId`, `runId`, attempt, số item thành công, số item thất bại và outcome cuối cùng. Lỗi một record có thể được ghi thành event xử lý riêng nếu có chính sách bỏ qua và tổng kết; lỗi khiến **cả job thất bại** nên được ghi ở boundary cuối.

Nếu cứ log `ERROR` cho từng record bị từ chối theo nghiệp vụ rồi thêm một `ERROR` tổng kết, dashboard có thể phóng đại số incident. Có thể dùng metric đếm record fail và một log terminal failure nếu job dừng.

### 7.4. CLI, main và thread không được giám sát

Ở ứng dụng CLI, boundary cuối thường là `main` hoặc lớp điều phối lệnh: log nguyên nhân hữu ích, trả exit code phù hợp và không lộ stack trace nhạy cảm cho người dùng cuối. `Thread.UncaughtExceptionHandler` có thể là **cơ chế dự phòng** cho lỗi không được bắt, nhưng không nên xem đó là nơi ghi lỗi duy nhất.

Trong `ExecutorService`, exception của task được nộp qua `submit` có thể được giữ trong `Future` và xuất hiện khi gọi `get()`, thay vì đi tới uncaught handler. Với `CompletableFuture`, phải quan sát completion exceptional hoặc callback; với job framework, sử dụng error handler/lifecycle do framework cung cấp.

## 8. Cách ghi exception đúng trong JUL và SLF4J

### 8.1. Java Util Logging

Để đính kèm `Throwable` (giữ thông tin nguyên nhân/stack trace cho formatter phù hợp):

~~~java
// Doan tich hop: LOGGER va failure la bien da co.
LOGGER.log(Level.SEVERE, "Order load failed", failure);
~~~

Đây là overload `Logger.log(Level, String, Throwable)`. Nếu dùng overload tham số hóa:

~~~java
LOGGER.log(Level.SEVERE,
        "Order load failed requestId={0}",
        new Object[] {requestId});
~~~

thì các tham số được dùng để format message nhưng **không tự đính kèm `failure`**. Khi cần cả tham số cấu trúc và throwable theo một formatter cụ thể, hãy dùng API/backend hỗ trợ trường riêng, hoặc thiết kế event/LogRecord phù hợp. Không giả định Java có overload `log(Level, String, Object[], Throwable)`.

**Tránh kiểu này:**

~~~java
LOGGER.severe("Order failed: " + failure.getMessage());
~~~

Nó có thể mất stack trace/cause, in dữ liệu nhạy cảm từ message và tạo chuỗi sớm. Nếu cần mã lỗi ổn định, dùng `errorCode` được ánh xạ chủ động, không mặc định dùng mọi `getMessage()` do thư viện dưới trả về.

### 8.2. SLF4J (kèm backend như Logback hoặc Log4j 2)

Ví dụ mã tích hợp:

~~~java
// Can SLF4J API va backend. logger/requestId/failure da ton tai.
logger.error("Order load failed requestId={} errorCode={}",
        requestId, "STORAGE_UNAVAILABLE", failure);
~~~

Trong cách dùng SLF4J phổ biến, `Throwable` ở đối số cuối được backend/API xử lý như exception khi overload varargs phù hợp được chọn. Cần thử trên phiên bản và provider thực tế để bảo đảm throwable được gắn đúng. Đối với message không tham số hóa, mẫu rõ ràng là `logger.error("Order load failed", failure)`.

**Đừng đánh đồng “formatter in stack trace” với “formatter chắc chắn không làm lộ dữ liệu”.** Exception có thể mang đường dẫn, raw SQL, thông tin người dùng hoặc message từ input; kiểm tra chính sách redaction và nơi lưu trước khi bật log chi tiết.

## 9. Chọn nơi *xuất* log: handler, appender và kênh cảnh báo

Sau khi quyết định **thành phần nào phát log**, logging backend mới quyết định **nơi ghi ra**.

~~~text
One terminal failure event
           |
           v
         Logger
           |
      Backend routing
       /       |       \
 Console     File     Central collector
 stdout/err  rotating   search/alert/retention
~~~

Với JUL, có thể gắn `ConsoleHandler`, `FileHandler` và handler riêng, mỗi cái có level/filter/formatter. Với SLF4J, việc route và ghi thực tế do backend như Logback/Log4j 2 điều khiển qua appender.

| Đích | Khi phù hợp | Điều cần lưu ý |
| --- | --- | --- |
| Console / stdout/stderr | Developer, CLI, container và hệ thống có log collector | Ai thu thập stdout/stderr, có duplicate qua pipeline không? |
| Local file / rotating file | Ứng dụng cần lưu nội bộ, môi trường cho phép quản lý file | Disk, rotation, retention, permission, volume |
| Central log platform | Điều tra liên service, tìm kiếm, cảnh báo có phân quyền | Chi phí, PII, độ trễ/độ tin cậy exporter |
| Security/audit store | Sự kiện theo chính sách bảo mật hoặc kiểm toán | Schema, integrity, quyền truy cập và acknowledgment riêng |
| Metrics/traces | Đo tỷ lệ lỗi, retry, latency, đường đi request | Không thay thế log chi tiết khi cần bối cảnh |

**Một log event có thể được fan-out tới nhiều đích** mà không cần gọi logger nhiều lần. Ngược lại, nếu ứng dụng đã ghi stdout và collector tự đưa nó vào kho tập trung, cấu hình thêm remote appender gửi cùng event tới đúng kho đó có thể tạo dữ liệu trùng.

Level của logger nguồn có thể lọc event **trước** khi handler/appender thấy nó; filter tại mỗi đích chỉ tiếp tục lọc phần event đã được tạo. Audit trail có yêu cầu chặt về completeness/durability không nên chỉ là một dòng `INFO` có thể biến mất khi thay đổi logging level.

## 10. Privacy, security và logging lỗi

Exception thường là **đường rò rỉ thông tin ngoài ý muốn**. Ví dụ:

- `SQLException` hoặc log truy vấn có thể chứa tham số dữ liệu cá nhân.
- HTTP client exception có thể đưa URL với query token vào message.
- Validation exception có thể chứa raw body hoặc field người dùng nhập.
- Stack trace có thể chứa tên lớp/hạ tầng và đường dẫn nội bộ.
- `MDC` có thể vô tình mang email, session ID hoặc dữ liệu từ request cũ nếu không được dọn.

**Ưu tiên log các trường đã cho phép:** `requestId`, operation code, route pattern, status, error code, exception type khi phù hợp, duration và số lần retry. `requestId` và correlation ID vẫn có thể liên kết với một cá nhân, nên cũng cần retention và phân quyền.

Không log password, token, cookie, toàn bộ DTO, header xác thực hoặc raw user input để “đủ thông tin điều tra”. **Không dùng chuỗi đã băm của email/IP rồi mặc nhiên gọi là anonymous.** Nếu bắt buộc lưu dữ liệu nhạy cảm, cần kênh được duyệt, masking/redaction có kiểm thử, khóa truy cập và retention riêng.

Một logger không nên lộ nguyên cause sang HTTP response hoặc thông báo lỗi hiển thị cho người dùng. Boundary có thể trả `errorCode` ổn định và correlation ID; chi tiết nội bộ chỉ dành cho log phù hợp quyền truy cập.

## 11. Các trường hợp đặc biệt cần cân nhắc

### Khi fallback thành công

Giả sử cache bị lỗi, service bỏ cache và đọc database thành công. Log hợp lý có thể là:

~~~text
event=cache_fallback_activated operation=load_order
outcome=RECOVERED requestId=req-101
~~~

Nếu repository log `SEVERE` rồi boundary cuối trả HTTP 200, hệ thống cảnh báo có thể nhận nhầm một incident lớn. Tốt hơn là thành phần thực hiện fallback ghi **một event degraded/recovered** và metric phục vụ theo dõi.

### Khi nhiều tầng đều có giá trị quan sát độc lập

Một hệ thống có thể cần log tại cả gateway và service nếu hai log mô tả **hai sự kiện riêng**: gateway kết thúc HTTP 502 và service phát sinh timeout khi gọi dependency. Cần trường `traceId`/`requestId` để tương quan, tránh tạo cảm giác hai sự cố không liên quan. Đây không phải lý do để từng method trong cùng service log cùng một stack trace.

### Khi lỗi gây ảnh hưởng bảo mật

Một hành động đăng nhập bị từ chối có thể cần audit event ngay cả khi HTTP status 401 là expected. Audit và diagnostic log nên tách mục đích, schema, độ bền và quyền truy cập. **Không nâng mọi 401/403 thành `SEVERE`**; dùng chính sách security monitoring hoặc rate-based alerts phù hợp.

### Khi có retry

Nếu một dependency timeout ở attempt 1, thành công ở attempt 2, việc log `ERROR` ở tầng thấp cho attempt 1 có thể báo sai outcome của request. Retry coordinator nên cung cấp metric và event retry; chỉ log terminal failure ở mức ERROR nếu cuối cùng không phục hồi. Với retry có tác dụng phụ, vẫn cần idempotency và quy tắc giao dịch; logging không tự giải quyết vấn đề trùng nghiệp vụ.

## 12. Kiểm thử để bảo đảm chọn đúng nơi ghi lỗi

Không nên chỉ assert rằng “có log ERROR” một cách chung chung. Hãy kiểm tra **số event, tầng phát, severity, context và trạng thái cuối**.

| Tình huống test | Điều cần kỳ vọng |
| --- | --- |
| Repository ném exception, HTTP trả 503 | Một terminal error event ở boundary; cause còn nguyên |
| Repository lỗi một lần, retry thành công | Không tạo terminal failure giả; có metric/event retry nếu policy yêu cầu |
| Lỗi validation kỳ vọng, trả 400 | Không có `SEVERE` không cần thiết; response có error code |
| Service fallback thành công | Event `RECOVERED`/`DEGRADED` đúng outcome |
| Message thất bại nhiều attempt rồi DLQ | Phân biệt attempt failure và DLQ confirmed; không nhân stack trace vô hạn |
| Một logger được gắn handler ở cả child và root | Phát hiện duplicate do additivity/parent handlers |
| Exception chứa secret giả | Secret không được xuất sang các đích đã kiểm thử |
| Logging backend unavailable | Ứng dụng xử lý theo policy, không xem `logger.info()` là durable acknowledgment |
| Client nhận 500 | Không chứa raw stack trace, SQL hoặc token |
| Async task thất bại | Error handler/future quan sát được outcome; không phụ thuộc duy nhất uncaught handler |

### Bài kiểm tra với log đã thu thập

Trong unit/integration test, dùng appender/handler test để bắt event rồi assert:

- Đúng **một** event `order_load_failed` cho một request thất bại trong policy này.
- Có `requestId`, mã lỗi ổn định và exception type.
- Không có password, token, raw request body hoặc stack trace không được phép.
- Tầng repository không tự ghi `SEVERE` rồi rethrow.
- Status/exception/outcome khớp logic nghiệp vụ.
- Nếu log đến nhiều sink, xác định mỗi sink nhận sự kiện như thế nào; không nhầm fan-out với ghi logger nhiều lần.

Với SLF4J/Logback hoặc Log4j 2, cách gắn test appender phụ thuộc backend và version; với JUL có thể dùng `Handler` tùy biến thu `LogRecord`. **Đừng sửa logger root toàn cục trong một test rồi để cấu hình đó rò sang các test khác**; tạo logger riêng và dọn handler/lifecycle sau kiểm thử.

## 13. Các lỗi phổ biến và cách sửa

| Sai lầm | Vấn đề | Cách làm tốt hơn |
| --- | --- | --- |
| Mỗi `catch` đều gọi `ERROR` rồi rethrow | Cùng exception gây nhiều dòng trùng | Log tại boundary quyết định outcome, giữ cause khi truyền |
| Chỉ log `ex.getMessage()` | Mất stack trace, message có thể chứa PII | Gắn `Throwable` đúng API; log mã lỗi ổn định và kiểm soát sink |
| Ghi ở repository rồi gateway cũng ghi | Không rõ đâu là terminal failure | Phân chia quyền sở hữu log theo tầng |
| Nuốt exception không log/không propagate | Tầng trên tưởng đã thành công | Xử lý thật sự, hoặc propagate/fail với mã phù hợp |
| Mọi 4xx đều `SEVERE` | Cảnh báo nhiễu | Severity theo tác động, audit/security policy riêng |
| Retry từng attempt đều ghi stack trace đầy đủ | Log storm và số lỗi bị đếm sai | Metric/structured attempt event; terminal failure rõ ràng |
| Log trước khi database transaction commit | Có thể ghi “success” dù rollback | Ghi đúng thời điểm/outcome hoặc dùng cơ chế đảm bảo sự kiện |
| Dùng `System.out.println(ex)` trong ứng dụng web | Thiếu context, schema, route và kiểm soát | Dùng logger ở boundary, backend cấu hình |
| Bật DEBUG và log raw payload | Rò rỉ PII/credential | Schema allowlist, redaction, retention phù hợp |
| Chỉ dựa vào `UncaughtExceptionHandler` | Future/async có thể giữ exception bên trong | Quan sát failure tại executor/job boundary |
| Log một lần rồi nghĩ đã lưu bền | Async queue, file/network có thể lỗi | Theo dõi delivery/flush/retention phù hợp yêu cầu |
| Có nhiều appender nên gọi logger nhiều lần | Tạo bản ghi không cần thiết | Một event, backend fan-out theo filter |

## 14. Checklist nhanh cho dự án Java

- [ ] Xác định tầng sở hữu **kết quả cuối** của request/job/message.
- [ ] Đặt lỗi terminal tại boundary hoặc error handler có context đầy đủ.
- [ ] Khi wrap exception, giữ `cause`; tránh `log and rethrow` nếu không có sự kiện độc lập.
- [ ] Phân biệt expected business errors, transient failure, fallback, retry và terminal failure.
- [ ] Định nghĩa level JUL/SLF4J theo tác động, không theo tên `Exception` đơn thuần.
- [ ] Gắn request ID, operation, error code, retry count khi cần; không dump payload.
- [ ] Đính kèm Throwable bằng API đúng khi cần stack trace; kiểm soát rủi ro PII và nơi lưu.
- [ ] Kiểm tra logger hierarchy, handler/appender, additivity và duplicate pipeline.
- [ ] Tách log chẩn đoán với audit event có yêu cầu riêng.
- [ ] Quan sát async task/future/message handler, không bỏ sót failure.
- [ ] Test terminal failure, fallback success, retry success, dữ liệu nhạy cảm và log duplication.
- [ ] Đo hiệu quả bằng metrics/traces cùng log, tránh biến mỗi dòng lỗi thành một incident.

### Tự kiểm tra kiến thức

**Câu 1.** Repository log `SEVERE` rồi ném exception; controller cũng log `SEVERE`. Có phải chắc chắn tốt hơn không?  
**Đáp:** Không. Nếu là cùng một thất bại chưa được xử lý ở repository, đó thường là log trùng. Nên giữ cause và log ở boundary biết outcome.

**Câu 2.** Retry lần một timeout, lần hai thành công. Có nên ghi “request failed” ở lần đầu?  
**Đáp:** Không. Có thể ghi event retry hoặc metric; terminal outcome vẫn là thành công.

**Câu 3.** Có exception thì bắt buộc ghi `ERROR` hoặc `SEVERE`?  
**Đáp:** Không. Validation error 400, denied 403, fallback thành công và lỗi hạ tầng thật có mục đích/severity khác nhau.

**Câu 4.** Một event được ghi ra console và file có phải ứng dụng phải gọi logger hai lần?  
**Đáp:** Không. Handler/appender có thể fan-out một event tới nhiều đích.

**Câu 5.** `LOGGER.severe(ex.getMessage())` có bảo đảm giữ stack trace và bảo mật không?  
**Đáp:** Không. Nó chỉ ghi chuỗi message và có thể lộ dữ liệu nhạy cảm; phải cân nhắc gắn Throwable cùng schema/sink phù hợp.

**Câu 6.** Thread task thất bại nhưng không thấy uncaught log, có chắc không có lỗi?  
**Đáp:** Không. Task trong `Future` hoặc `CompletableFuture` có thể giữ lỗi để caller/handler quan sát.

**Ghi nhớ:** “Chọn nơi ghi lỗi” trước hết là chọn **nơi sở hữu outcome và đủ ngữ cảnh**, không phải tìm vị trí `catch` đầu tiên. Tầng không xử lý được nên propagate exception cùng cause; boundary cuối ghi sự kiện lỗi đã phân loại, không nhân stack trace ở mọi tầng. Sau đó logging backend mới định tuyến event đến console, file hoặc collector với chính sách level, quyền riêng tư và độ tin cậy phù hợp.