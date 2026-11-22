# Technical error trong Logging và Exception của Java

## 1. Technical error là gì?

**Technical error** (lỗi kỹ thuật) là lỗi phát sinh từ phần mềm, hạ tầng hoặc điều kiện thực thi khiến ứng dụng **không thể hoàn tất một thao tác như dự kiến**: database timeout, lỗi I/O, kết nối đến dependency bị từ chối, cấu hình sai, hết tài nguyên, serialization failure, bug `NullPointerException` hoặc một tác vụ nền bị hỏng.

Trong hệ thống Java, exception giúp biểu diễn và truyền trạng thái lỗi. **Logging** là cơ chế để người vận hành hiểu chuyện gì đã xảy ra, ở bước nào, liên quan request/job nào và mức ảnh hưởng ra sao. Hai mục tiêu này khác nhau:

- **Throw/propagate exception**: báo cho caller biết thao tác thất bại để điều khiển luồng xử lý, rollback, retry hoặc phản hồi phù hợp.
- **Log technical error**: cung cấp dấu vết chẩn đoán cho hệ thống quan sát và điều tra.
- **Return an API result**: giao tiếp với client qua hợp đồng công khai, thường không chứa stack trace, SQL, token hoặc chi tiết hạ tầng.
- **Metric/alert**: theo dõi số lần lỗi, tỷ lệ lỗi, độ trễ, dependency health và tác động đến SLO.

Một lỗi kỹ thuật **không luôn là một bug**, cũng **không mặc nhiên cần log ERROR ở mọi tầng**. Kết nối đứt tạm thời có thể được retry và phục hồi; một request bị client hủy có thể là sự kiện bình thường; một bug bất ngờ có thể cần log tại ranh giới xử lý đúng một lần.

### Mục tiêu học tập

Sau bài này, bạn có thể:
1. Phân biệt **technical error** với validation error, lỗi nghiệp vụ và các dạng từ chối dự kiến.
2. Giữ nguyên **cause chain**, stack trace và thông tin phân loại khi chuyển đổi exception giữa các layer.
3. Thiết kế log theo schema có `error_code`, `operation`, `request_id`, `dependency`, `outcome` và nguồn lỗi.
4. Chọn logging boundary để tránh cùng exception bị log lặp ở repository, service, controller và framework.
5. Viết và chạy một ví dụ Java 17 độc lập với `java.util.logging` (JUL), xử lý lỗi dự kiến/lỗi kỹ thuật và không làm lộ exception message nhạy cảm.
6. Áp dụng nguyên tắc cho REST API, xử lý message, job nền, retry/timeout, monitoring và incident response.

## 2. Phân biệt lỗi kỹ thuật với lỗi nghiệp vụ

Một hệ thống đặt vé có thể từ chối mua vé vì đã hết chỗ. Đó là **kết quả nghiệp vụ dự kiến**. Ngược lại, nếu service không kết nối được database để biết còn chỗ hay không, đó là **technical error**. Hai tình huống có thể đều dẫn đến một request không thành công nhưng cách xử lý và logging khác nhau.

| Nhóm | Ví dụ | Ý nghĩa | Cách phản hồi/log thường phù hợp |
| --- | --- | --- | --- |
| **Validation** | Thiếu field bắt buộc, định dạng ngày sai | Input không thỏa hợp đồng | Phản hồi 4xx/mã xác thực; không mặc định ERROR |
| **Business rejection** | Hết hàng, không đủ số dư, trạng thái không cho phép | Hệ thống hoạt động đúng theo quy tắc | Mã nghiệp vụ rõ ràng; INFO hoặc audit theo nhu cầu |
| **Authentication/authorization** | Không đăng nhập hoặc không có quyền | Từ chối truy cập theo chính sách | 401/403 theo giao thức; audit/security event riêng |
| **Transient technical failure** | Network timeout, database tạm không sẵn sàng, rate limit upstream | Có thể phục hồi tùy điều kiện | Retry có giới hạn hoặc lỗi 5xx; warning/error tùy boundary |
| **Permanent technical/configuration failure** | Schema không tương thích, cấu hình sai, credential service không hợp lệ | Thường không giải quyết bằng retry ngay | Error/alert với mã cấu hình, can thiệp triển khai |
| **Unexpected defect** | Lỗi bất biến nội bộ, `NullPointerException`, logic sai | Chưa được dự kiến/hợp đồng hóa | Ghi một lần tại boundary, phân loại `UNEXPECTED`, điều tra |
| **Cancellation/interruption** | Client ngắt kết nối, task bị hủy hợp lệ, thread interrupt | Có thể là điều khiển vòng đời thay vì lỗi hệ thống | Giữ semantic hủy, không nâng mọi trường hợp lên ERROR |

**Phân loại theo ngữ nghĩa, không chỉ theo exception class.** `IllegalArgumentException` có thể do client gửi giá trị sai hoặc do một bug tạo dữ liệu sai ở bên trong. `IOException` có thể là timeout tạm thời, lỗi file bị xóa hoặc kết nối bị đóng khi shutdown. `SQLException` có thể mang SQLState/error code riêng. Muốn quyết định retry hay alert cần **bối cảnh thao tác và hợp đồng của dependency**.

### 2.1. Technical failure có thể xảy ra cả khi client gửi request hợp lệ

```text
Client POST /orders
       |
       v
Validate request          (PASS)
       |
       v
Business rule             (PASS)
       |
       v
Database write            (TIMEOUT)
       |
       v
Technical failure -> rollback/unknown commit? -> policy
```

Một timeout database cần phân biệt **có chắc chưa commit hay không**. Nếu request đã gửi đi rồi mất phản hồi, application có thể **không biết thao tác đã được thực thi**. Retry không có idempotency có thể tạo hai đơn hàng hoặc hai giao dịch. Không kết luận chỉ vì stack trace có `TimeoutException` thì retry an toàn.

### 2.2. HTTP status không phải toàn bộ chẩn đoán

Trong REST API, lỗi dependency có thể dẫn đến `503 Service Unavailable` hoặc `502 Bad Gateway` theo vai trò service; bug bất ngờ thường dùng `500 Internal Server Error`. Nhưng mapping phụ thuộc hợp đồng API, reverse proxy, retry semantics và loại lỗi. Không biến mọi technical error thành `500` và không coi mọi `500` đều do một cause duy nhất.

Trường `error_code=DEPENDENCY_TIMEOUT` có ích hơn text message tự do. Hãy chuẩn hóa mã lỗi công khai riêng với mã lỗi nội bộ nếu cần. Client không nên nhận host name database, JDBC URL, stack trace hay exception message chứa credential.

## 3. Exception là tín hiệu; log là dấu vết

Java exception thường mang:
- **Type**: `IOException`, `TimeoutException`, `IllegalStateException` hoặc custom exception.
- **Message**: chuỗi giải thích, **có thể** chứa dữ liệu không được phép chia sẻ.
- **Cause**: exception nguồn trong `getCause()`, giúp truy ra lớp phát sinh.
- **Stack trace**: chuỗi call frames, file/line và các đoạn `Caused by` khi được renderer xuất.
- **Suppressed exceptions**: các lỗi phụ khi đóng resource trong `try-with-resources` hoặc cơ chế khác.
- **Context**: thông tin nghiệp vụ như operation, dependency, correlation ID, retry attempt, thường nên là **các log fields** được kiểm soát, không phải nhồi raw payload vào message.

Ví dụ đường truyền lỗi:

```text
Repository: IOException("read timed out")
             |
             v
Service: TechnicalFailure("DEPENDENCY_UNAVAILABLE", cause)
             |
             v
HTTP boundary: log một technical event + map thành 503
             |
             v
Client: response code và error_id an toàn
```

Ở repository, không phải lúc nào cũng cần `logger.error(..., e)` trước khi throw. Nếu service lại log cùng lỗi và controller tiếp tục log, người vận hành sẽ thấy ba stack traces cho một request. Log nhiều không đồng nghĩa quan sát tốt hơn.

### 3.1. Bảo toàn cause khi wrap

Mẫu đúng trong Java:

```java
// Mảnh code tích hợp, không phải chương trình chạy độc lập.
try {
    repository.write(order);
} catch (java.io.IOException cause) {
    throw new OrderStorageException(
            "ORDER_STORAGE_UNAVAILABLE", cause);
}
```

`OrderStorageException` là **custom exception do dự án định nghĩa**; constructor phải lưu `cause` bằng `super(message, cause)`. Khi đó boundary có thể biết root cause type và stack trace khi được phép hiển thị.

Mẫu sai:

```java
// Phản diện: làm mất cause và có thể đưa text nhạy cảm vào error.
catch (java.io.IOException e) {
    throw new RuntimeException(e.getMessage());
}
```

`getMessage()` không thay thế `getCause()`. Thao tác trên có thể làm mất call stack nguồn và copy raw thông tin nhạy cảm vào thông điệp mới. Một mã lỗi ổn định cùng cause được bảo toàn thường tốt hơn.

### 3.2. Đừng nuốt exception chỉ để “không thấy ERROR”

```java
// Phản diện: caller có thể tưởng thao tác đã thành công.
try {
    repository.write(order);
} catch (Exception ignored) {
    logger.warn("Temporary issue");
}
```

Nếu bỏ qua lỗi, transaction/caller có thể tiếp tục trong trạng thái không hợp lệ. Chỉ swallow một lỗi khi có **policy và fallback thật sự** cho phép tiếp tục, đồng thời trạng thái và metric phải phản ánh kết quả. Không bắt `Exception` chung rồi luôn trả success để giảm số log ERROR.

## 4. Logging boundary: ghi ở nơi quyết định kết quả

**Logging boundary** là nơi một phần hệ thống chịu trách nhiệm quan sát lỗi cuối cùng của một thao tác: HTTP exception handler, consumer container boundary, scheduler/job runner hoặc worker supervisor. Đây thường là nơi có đủ request/job context và quyết định kết quả/response.

Một thiết kế khuyến nghị:

```text
Transport / controller / consumer
           |
           v
        Service
           |
           v
       Repository  -- IOException
           |
           v
   Wrap preserving cause
           |
           v
     Propagate through
           |
           v
    Boundary decides outcome
           |
           +--> classify / map response or retry
           |
           +--> emit one coherent error event
           |
           +--> metrics / alert / retry policy
```

### 4.1. Không log rồi throw ở mọi tầng

Phản diện:

```java
// Các mảnh code minh họa; không phải lớp Java hoàn chỉnh.
// Repository
catch (IOException e) {
    logger.error("DB failed", e);
    throw e;
}

// Service
catch (IOException e) {
    logger.error("Order failed", e);
    throw new OrderStorageException("DEPENDENCY_UNAVAILABLE", e);
}

// Controller
catch (OrderStorageException e) {
    logger.error("Request failed", e);
    throw e;
}
```

Một failure tạo nhiều bản ghi `ERROR` gần giống nhau. Các hệ thống tổng hợp có thể đếm nhầm ba lỗi, stack traces lặp tốn chi phí và cảnh báo bị khuếch đại.

Cách tốt hơn:
- Repository gắn **cause/type và context cần thiết** thông qua exception hoặc structured result, không log lặp trừ khi có event riêng hữu ích.
- Service wrap lỗi theo **semantic** và không che nguyên nhân.
- Boundary ghi một event với request ID, operation, classification, dependency, outcome.
- Nếu cần một log thấp tầng để quan sát retry/circuit breaker, dùng **event khác** như `dependency_retry_scheduled` hoặc DEBUG có mục đích; không copy lại cùng ERROR vô tận.

**Ngoại lệ:** Có thể cần log ở nhiều tầng khi mỗi log mô tả **sự kiện khác nhau**: “retry đã lên lịch”, “circuit breaker chuyển OPEN”, “request cuối cùng thất bại”. Chúng không phải duplicate vô nghĩa nếu schema/outcome khác nhau.

### 4.2. Phân biệt handled và unhandled

Nếu một lỗi đã được xử lý và fallback thành công, có thể dùng `WARN` hoặc INFO kèm `recovered=true`. Nếu thao tác cuối thất bại, boundary có thể dùng `ERROR` hoặc `SEVERE` theo backend và mức ảnh hưởng. Nếu chỉ log ERROR trước khi retry rồi retry thành công, dashboard có thể thấy false alarm nếu không có result cuối cùng.

Ví dụ luồng:

```text
dependency_attempt_failed attempt=1 transient=true
dependency_retry_scheduled backoff_ms=200
dependency_attempt_succeeded attempt=2
request_completed outcome=SUCCESS recovered=true
```

Không ghi `request_failed` khi request cuối cùng thành công. Cần phân biệt **attempt-level error** với **operation-level failure**.

## 5. Thiết kế schema log cho technical error

Ví dụ event JSON minh họa:

```json
{
  "event": "technical_error",
  "occurred_at": "2026-11-10T03:00:00Z",
  "severity": "ERROR",
  "service": "order-api",
  "operation": "order_read",
  "request_id": "req-104",
  "error_code": "DEPENDENCY_UNAVAILABLE",
  "category": "TRANSIENT_DEPENDENCY",
  "dependency": "orders-db",
  "exception_type": "IOException",
  "outcome": "FAILED",
  "retryable": true,
  "attempt": 1
}
```

**Các giá trị ở trên là dữ liệu minh họa.** `retryable=true` chỉ đúng khi tầng phân loại và chính sách retry chứng minh thao tác an toàn để retry. Đừng tự động gắn `retryable=true` cho mọi `IOException`.

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `event` | Loại bản ghi kỹ thuật ổn định | Phân biệt `technical_error` với `retry_scheduled` |
| `operation` | Thao tác logic đang thất bại | Tên ngắn ổn định, không nhúng raw URL |
| `error_code` | Mã lỗi nội bộ | Từ danh sách quản lý, có thể phân nhóm theo domain |
| `category` | Lỗi dependency/config/bug/resource | Cần tiêu chí định nghĩa rõ |
| `outcome` | `FAILED`, `RECOVERED`, `CANCELLED` | Theo kết quả **cuối của boundary** |
| `dependency` | Hệ thống con bị ảnh hưởng | Dùng alias như `orders-db`, không chứa credentials |
| `exception_type` | Lớp exception nguồn phù hợp | Không lấy raw exception message làm mã lỗi |
| `request_id` / `trace_id` | Correlation | Validate độ dài/ký tự; không phải secret |
| `attempt` | Lần thử xử lý | Phải biết rõ phạm vi và nguồn đếm |
| `retryable` | Có được retry theo policy hay không | Không suy ra từ class/HTTP status đơn thuần |
| `duration_ms` | Độ trễ thao tác | Số thực đo, không suy từ timestamp rời rạc |
| `service` / `instance` | Nơi quan sát lỗi | Giúp ghép log đa service |
| `error_id` | ID của một lần lỗi cụ thể | Hữu ích khi đối chiếu response an toàn với log |

Một log không nên chứa **toàn bộ request body**, password, token, private key, JDBC connection string có credential, cookie, thẻ thanh toán hoặc dữ liệu cá nhân không cần thiết. `Throwable.getMessage()`, stack traces, suppressed exceptions và thông điệp của client libraries có thể chứa URI hoặc payload. Hãy đưa các thông tin được phép theo **allowlist** và quyết định riêng cách xuất full throwable.

**Structured logging** như SLF4J 2 fluent API giúp các field dễ tìm kiếm; nó **không tự động lọc dữ liệu nhạy cảm**. Không đưa raw exception, DTO hoặc headers vào key-value pairs nếu chưa đánh giá.

## 6. Java 17 độc lập: phân biệt business error và technical error

Ví dụ dùng `java.util.logging` (JUL) có sẵn trong JDK 17, không yêu cầu Maven/Gradle. Chương trình mô phỏng bốn kết quả:
1. Thao tác thành công.
2. Từ chối theo nghiệp vụ (`ORDER_NOT_FOUND`).
3. Lỗi dependency (`IOException`) được wrap thành custom `TechnicalFault` nhưng giữ nguyên cause.
4. Lỗi bất ngờ (`IllegalStateException`).

Một exception trong demo cố tình chứa chuỗi bí mật **giả lập**, nhưng logger chỉ ghi **mã lỗi chuẩn hóa và exception type**, không ghi raw message hoặc stack trace. Đây là quyết định để stdout tất định và chứng minh nguyên tắc **data minimization**; khi triển khai thật, stack trace có thể cần được ghi vào sink nội bộ với chính sách bảo mật và redaction phù hợp.

Tạo tệp `TechnicalErrorLoggingDemo.java`:

```java
import java.io.IOException;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class TechnicalErrorLoggingDemo {
    private static final class BusinessFault extends RuntimeException {
        private final String code;

        BusinessFault(String code) {
            super(code);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    private static final class TechnicalFault extends RuntimeException {
        private final String code;

        TechnicalFault(String code, Throwable cause) {
            super("Technical operation failed", cause);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    private static final class CaptureHandler extends Handler {
        private final StringBuilder events = new StringBuilder();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.append(record.getLevel().getName())
                        .append(' ')
                        .append(record.getMessage())
                        .append('\n');
            }
        }

        @Override
        public void flush() {
            // Capture trong bộ nhớ; không có I/O ra file.
        }

        @Override
        public void close() {
            flush();
        }

        String text() {
            return events.toString();
        }
    }

    private static void callDatabase() throws IOException {
        throw new IOException("database password=demo-db-secret");
    }

    private static String readOrder(int scenario) {
        if (scenario == 1) {
            throw new BusinessFault("ORDER_NOT_FOUND");
        }
        if (scenario == 2) {
            try {
                callDatabase();
            } catch (IOException cause) {
                throw new TechnicalFault("DEPENDENCY_UNAVAILABLE", cause);
            }
        }
        if (scenario == 3) {
            throw new IllegalStateException(
                    "debug token=demo-access-token");
        }
        return "READY";
    }

    private static void handle(
            Logger logger, String requestId, int scenario) {
        try {
            readOrder(scenario);
            logger.info("event=order_read result=OK requestId="
                    + requestId);
        } catch (BusinessFault business) {
            logger.info("event=order_read result=REJECTED code="
                    + business.code() + " requestId=" + requestId);
        } catch (TechnicalFault technical) {
            logger.severe("event=technical_error operation=order_read"
                    + " code=" + technical.code()
                    + " causeType="
                    + technical.getCause().getClass().getSimpleName()
                    + " requestId=" + requestId);
        } catch (RuntimeException unexpected) {
            logger.severe("event=technical_error operation=order_read"
                    + " code=UNEXPECTED causeType="
                    + unexpected.getClass().getSimpleName()
                    + " requestId=" + requestId);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lesson.technical.error.demo");
        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);

        CaptureHandler capture = new CaptureHandler();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        try {
            handle(logger, "req-101", 0);
            handle(logger, "req-102", 1);
            handle(logger, "req-103", 2);
            handle(logger, "req-104", 3);

            String output = capture.text();
            System.out.print(output);
            boolean secretLeaked =
                    output.contains("demo-db-secret")
                    || output.contains("demo-access-token");
            System.out.println("secretLeaked=" + secretLeaked);
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac TechnicalErrorLoggingDemo.java
java TechnicalErrorLoggingDemo
```

**Stdout chính xác** khi chạy trong JVM mới, không có code bên ngoài can thiệp vào logger demo:

```text
INFO event=order_read result=OK requestId=req-101
INFO event=order_read result=REJECTED code=ORDER_NOT_FOUND requestId=req-102
SEVERE event=technical_error operation=order_read code=DEPENDENCY_UNAVAILABLE causeType=IOException requestId=req-103
SEVERE event=technical_error operation=order_read code=UNEXPECTED causeType=IllegalStateException requestId=req-104
secretLeaked=false
```

### 6.1. Giải thích output

- `req-101`: kết quả `OK`; không có technical error.
- `req-102`: từ chối nghiệp vụ `ORDER_NOT_FOUND`, được ghi `INFO` chứ không mặc định là lỗi hệ thống cần báo động.
- `req-103`: lỗi I/O được wrap thành `TechnicalFault` với code `DEPENDENCY_UNAVAILABLE` và giữ `IOException` làm `cause`. Logger ghi `causeType=IOException` mà không lộ raw message chứa chuỗi `demo-db-secret`.
- `req-104`: lỗi bất ngờ đi qua nhánh `RuntimeException`, được phân loại `UNEXPECTED` và ghi tên class `IllegalStateException` mà không lộ message chứa token giả.
- `secretLeaked=false` chỉ chứng minh **hai chuỗi mẫu không xuất hiện trong output của demo**, không chứng minh mọi nơi trong ứng dụng thật đã xử lý bí mật an toàn.
- `CaptureHandler` giữ text trong `StringBuilder` và tắt parent handler nên không có timestamp/stack trace phụ; code chỉ minh họa một thread, **không phải một logger production đa luồng**.
- Hai lỗi kỹ thuật được **handled tại boundary mô phỏng**: hàm `handle` không trả HTTP status hay thực thi rollback thật. Trong hệ thống thực, phải kết hợp transaction, response mapping, retry và error metrics theo contract.

### 6.2. Vì sao demo không in full stack trace?

Một full stack trace từ exception cụ thể có thể chứa file/line number và message bất định, khó có stdout cố định. Quan trọng hơn, exception message do thư viện tạo đôi khi chứa token, URL hoặc dữ liệu riêng tư. Demo chủ ý xuất **code/type an toàn**. Với production, một sink chẩn đoán có quyền truy cập hẹp có thể cần stack trace để sửa bug; phải bảo đảm data classification, retention và xử lý secret trước khi cho phép xuất đầy đủ.

**Không** áp quy tắc “cấm mọi stack trace”. Quy tắc đúng là chọn **khi nào, ở đâu, với quyền nào** có thể ghi stack trace, và bảo đảm message/cause không chứa dữ liệu nhạy cảm. Không thể kiểm soát toàn bộ thư viện bên thứ ba chỉ bằng một regex.

### 6.3. Giới hạn và cải tiến production

Bộ phân loại `scenario` chỉ là giả lập. Trong ứng dụng thật không đọc một số integer từ client để quyết định loại lỗi. Phân loại dựa trên exception/result contract, retry policy, dependency health và ảnh hưởng nghiệp vụ. Các lỗi checked như `IOException` thường được wrap tại service boundary khi cần chuyển sang domain-independent technical exception, nhưng không phải lúc nào wrap cũng cần thiết.

Một handler production nên:
- Dùng exception code do hệ thống quản lý, không dùng raw `getMessage()` làm label.
- Kiểm tra cause trước khi gọi `getCause().getClass()` hoặc dùng một phương thức an toàn khi cause là null.
- Gắn correlation ID do server tạo/đã validate.
- Quyết định log level sau khi biết lỗi có được recover hay không.
- Không bắt `Error`, `InterruptedException` hoặc cancellation theo cách làm mất signal của runtime.
- Giữ exception nguyên gốc và chấp hành đường xử lý giao dịch/ack/HTTP response phù hợp.

## 7. Log level: ERROR không phải “mỗi lần throw”

Java JUL dùng `SEVERE`, `WARNING`, `INFO`, `FINE`...; SLF4J/Logback/Log4j 2 thường dùng `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE`. **Tên level khác nhau**, và mức chọn vẫn phụ thuộc ý nghĩa của event.

| Sự kiện | Mức tham khảo | Giải thích |
| --- | --- | --- |
| Input sai hợp đồng | INFO/DEBUG hoặc metric | Client có thể gửi input sai bình thường; không gây log storm |
| Business rejection hợp lệ | INFO, audit theo chính sách | Hệ thống thực thi đúng quy tắc |
| Dependency lỗi tạm thời, sau đó retry thành công | WARN/DEBUG ở attempt; INFO cho outcome | Không gọi operation là FAILED nếu đã recover |
| Dependency lỗi khiến operation cuối cùng thất bại | ERROR/SEVERE tại boundary | Cần điều tra tỷ lệ lỗi và ảnh hưởng |
| Bug bất ngờ/unhandled | ERROR/SEVERE tại boundary | Cần stack/context được kiểm soát và alert nếu đáng kể |
| Không có message vì client đã hủy | Tùy giao thức, có thể INFO/DEBUG | Không biến mọi cancellation thành outage |
| Shutdown có kiểm soát | INFO/WARN tùy lifecycle | Phân biệt shutdown bình thường và lỗi không hoàn tất drain |
| Lỗi trong logger/appender | Status/internal diagnostic channel | Tránh gọi lại chính pipeline đang hỏng |

Không có bảng level chung cho mọi hệ thống. Ví dụ một lỗi config khi khởi động có thể là **fatal đối với service**, trong khi một request đơn lẻ 500 có thể chỉ là một trong nhiều nghìn yêu cầu. Xem **phạm vi tác động, tần suất, khả năng phục hồi và cam kết SLO**.

### 7.1. Tránh alert storm và false severity

Một request gọi dependency 3 lần rồi thất bại cuối:
- Ba lần `attempt_failed` có thể được thống kê bằng metrics.
- Chỉ một `operation_failed` với error code cần báo ở cấp operation.
- Nếu retry cuối thành công, event tổng kết nên là `operation_completed recovered=true`.
- Nếu retry đã được lên lịch nhưng chưa thực thi, đừng gọi operation đã thành công.

Khi downstream lỗi diện rộng, hàng chục nghìn request có thể tạo hàng chục nghìn ERROR. Rate limiting, sampling của **diagnostic logs**, aggregation và alert theo tỷ lệ lỗi có thể giảm nhiễu; không sampling tùy ý **audit event bắt buộc**.

## 8. Bảo mật và tính riêng tư của exception logs

Lỗi kỹ thuật thường đi kèm thông điệp của hệ thống con. Các ví dụ dễ rò rỉ:

```text
Connection failed: jdbc:vendor://db.internal/app?user=svc&password=secret
HTTP call failed: https://partner.example.test?api_key=secret
Rejected payload: {"email":"x@example.test","password":"secret"}
Authorization failed: Bearer secret-token
```

Đây là **chuỗi giả minh họa** những điều không nên ghi. Hãy lưu **dependency alias, code, request ID và exception type**, không ghi raw credential hoặc request body.

Các điểm cần review:
- `exception.getMessage()` và `exception.toString()`.
- Cause chain, suppressed exceptions và stack traces đầy đủ.
- Headers như `Authorization`, `Cookie`; signed URL và query string.
- SQL bind values, connection URI, file path có thông tin cá nhân.
- DTO `toString()`/record-generated methods, JSON serializer và HTTP wire logging.
- MDC/ThreadContext hoặc structured logging fields được thêm tự động.
- Log collector, stdout, debug endpoints, backup, alert và ticket trích log.

**Một regex ở collector không thay thế việc không tạo secret trong log.** Nếu exception message đã được ghi ra stdout thì một lớp masking trong dashboard không xóa dữ liệu ở stdout, file hoặc forwarder upstream.

Khi secret thật bị lộ qua log: chặn tiếp diễn, đánh giá các sink, giới hạn truy cập, rotate/revoke credential theo chính sách, điều tra truy cập và khắc phục rủi ro. Không paste secret thật trong incident ticket/chat để “nhờ xem lỗi”.

## 9. Spring Boot / REST API: xử lý lỗi ở điểm vào

Trong Spring MVC, `@RestControllerAdvice` cùng `@ExceptionHandler` là một boundary phổ biến để map exception thành response. Đây là **mã tích hợp minh họa** cho dự án Spring hiện đại, không phải chương trình thuần Java 17 chạy không có dependency.

```java
// Mảnh minh họa Spring MVC. Các kiểu BusinessFault/TechnicalFault
// ở đây là custom exceptions do dự án định nghĩa.
@RestControllerAdvice
class ApiErrorHandler {
    private static final org.slf4j.Logger log =
        org.slf4j.LoggerFactory.getLogger(ApiErrorHandler.class);

    @ExceptionHandler(TechnicalFault.class)
    org.springframework.http.ResponseEntity<ApiError> onTechnical(
            TechnicalFault ex) {
        String errorId = java.util.UUID.randomUUID().toString();
        log.error("event=technical_error errorId={} code={}",
                  errorId, ex.code());
        return org.springframework.http.ResponseEntity
                .status(503)
                .body(new ApiError("SERVICE_UNAVAILABLE", errorId));
    }

    @ExceptionHandler(Exception.class)
    org.springframework.http.ResponseEntity<ApiError> onUnexpected(
            Exception ex) {
        String errorId = java.util.UUID.randomUUID().toString();
        log.error("event=technical_error errorId={} code=UNEXPECTED",
                  errorId);
        return org.springframework.http.ResponseEntity
                .status(500)
                .body(new ApiError("INTERNAL_ERROR", errorId));
    }

    record ApiError(String code, String errorId) {}
}
```

**Lưu ý thiết kế:**
1. Đoạn trên chỉ cho thấy **điểm map lỗi**; nó không khai báo `TechnicalFault`, `ApiError` bên ngoài hay cấu hình security/transaction. Constructor/method của custom exception do dự án cung cấp.
2. Không trả `ex.getMessage()`/stack trace về client. Dùng `errorId` để đối chiếu với log nội bộ.
3. `503` không phải lựa chọn đúng cho **mọi** TechnicalFault; một lỗi không phục hồi có thể là `500`, một gateway có thể trả `502`. Cần phân loại cụ thể.
4. `@ExceptionHandler(Exception.class)` không phải nơi nên swallow/capture mọi lỗi ở mọi stack: framework có sẵn exception resolvers, validation và security filters. Xác minh lớp này không vô tình map 400/401/403 thành 500 hoặc che mất response định sẵn.
5. Mã này **cố ý không in throwable stack trace**. Khi production cần điều tra sâu, hãy quyết định chính sách bảo mật và có thể dùng overload logger nhận `Throwable` tại **boundary duy nhất**.
6. Nếu exception bị xử lý bởi filter trước khi tới MVC hoặc servlet container sau khi response commit, advice có thể không nhận được. Quan sát lỗi ở đúng ranh giới HTTP lifecycle.
7. Không tạo errorId bằng request header tùy ý. UUID do server sinh trong ví dụ để tránh người dùng chèn newline hoặc ID giả vào log.
8. Nếu có tracing, log trace ID đã được xác nhận từ context để hỗ trợ điều tra xuyên dịch vụ.

### 9.1. Ví dụ an toàn với SLF4J 2.x

Một log structured ngắn gọn:

```java
// Mảnh tích hợp, logger thuộc SLF4J 2.x; các biến
// phải đến từ context đã kiểm soát và enum/mã lỗi ổn định.
log.atError()
   .addKeyValue("event", "technical_error")
   .addKeyValue("operation", "order_read")
   .addKeyValue("error_code", "DEPENDENCY_UNAVAILABLE")
   .addKeyValue("dependency", "orders-db")
   .addKeyValue("request_id", safeRequestId)
   .log("Order read failed");
```

Không phải mọi backend/encoder sẽ hiển thị key-value fields nếu chưa cấu hình. `atError()` chỉ biểu diễn level; API không tự biến dữ liệu nhạy cảm thành an toàn. Khi dùng MDC, dọn/khôi phục context theo scope để tránh một request mang dữ liệu của request khác trên thread pool.

### 9.2. Stack trace: khi nào và cách nào?

Với SLF4J thông thường, backend có thể nhận throwable:

```java
// Mảnh tích hợp, chạy khi Throwable đã được đánh giá an toàn
// để xuất ở sink nội bộ; không đưa vào phản hồi client.
logger.error("Dependency failed operation={} errorCode={}",
             "order_read", "DEPENDENCY_UNAVAILABLE", cause);
```

`cause` là đối số throwable cuối; backend phù hợp sẽ ghi stack/cause. Cần **đánh giá nội dung exception message** và cấu hình backend/encoder trước khi áp dụng cho dữ liệu nhạy cảm. Nếu raw exception chứa secret hoặc payload, hãy ưu tiên một mã lỗi an toàn, giữ chi tiết cho kênh điều tra có kiểm soát và không coi masked stack trace là mặc định được bảo đảm.

## 10. Technical error trong ứng dụng message và scheduled job

Các boundary khác REST có chính sách lỗi riêng:

- **Message consumer**: nhận event, xử lý, commit thay đổi nghiệp vụ, ack/commit message; lỗi kỹ thuật có thể khiến broker giao lại. Log receipt/attempt và result khác nhau, không ghi `PROCESSED` trước transaction commit.
- **Scheduled job**: lỗi một task nên gắn job name, execution ID, attempt, thời điểm và status. Đừng để chỉ có một exception không kèm job identity.
- **Batch pipeline**: có thể xử lý một phần; log `PARTIAL_FAILURE` và counts đáng tin, không gọi toàn batch `SUCCESS`.
- **Background executor**: exception có thể nằm trong `Future` hoặc đi tới `UncaughtExceptionHandler`; cần kiểm soát ai ghi log và ai xử lý retry/cancel.
- **Stream processing**: redelivery và retry tạo nhiều attempt-level logs; outcome cuối và idempotency phải được xác định riêng.

Ví dụ luồng message:

```text
message_received eventId=evt-42 attempt=1
dependency_failed eventId=evt-42 attempt=1 retryable=true
retry_scheduled eventId=evt-42 attempt=1 delayMs=500
message_received eventId=evt-42 attempt=2
message_applied eventId=evt-42 attempt=2
ack_requested eventId=evt-42 attempt=2
```

Chỉ **log `ack_confirmed` khi client/broker thực sự có cơ chế xác nhận**. `ack_requested` không tự chứng minh broker đã ghi nhận. Đừng retry một thao tác chuyển tiền hay gửi email khi chưa có idempotency key hoặc cơ chế reconcile.

### 10.1. Phân biệt “message fail” với “system fail”

Một message không parse được có thể là **poison message**; retry mãi thường không giúp. Lỗi dependency timeout có thể tạm thời. Sự kiện đã được xử lý nhưng broker giao lại có thể là **duplicate delivery** hợp lệ, không phải technical failure của nghiệp vụ.

Đặt error code và retry policy theo ngữ nghĩa; dùng DLQ/quarantine nếu phù hợp. **Không log nguyên payload** để chứng minh message bị lỗi; dùng event ID, schema version, hash/fingerprint có đánh giá rủi ro và mã validation.

### 10.2. Đừng nuốt interruption/cancellation

Với một thread đang chờ, `InterruptedException` là tín hiệu điều khiển quan trọng. Nếu code quyết định không rethrow, thường cần khôi phục interrupt status để tầng trên biết việc hủy:

```java
// Mảnh code tích hợp, không phải chương trình độc lập.
try {
    Thread.sleep(1000);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Thoát hoặc truyền tín hiệu cancel theo contract của task.
    return;
}
```

Trong các luồng xử lý async, `CancellationException` hoặc client disconnect có thể là hành vi bình thường. Không log ERROR cho tất cả trường hợp. Không bắt `Throwable` rồi coi mọi tình trạng, kể cả `OutOfMemoryError` hay `ThreadDeath`, là một lỗi nghiệp vụ có thể retry.

## 11. Retry, backoff, timeout, circuit breaker và error logging

Technical error thường kéo theo cơ chế phục hồi, nhưng một chiến lược sai có thể làm sự cố lớn hơn.

### 11.1. Retry chỉ khi có thể an toàn

Các câu hỏi trước khi retry:
- Lỗi có **thật sự transient** hay là auth/config/schema bug?
- Thao tác có **idempotent** hoặc có idempotency key không?
- Có timeout tổng, số lần thử tối đa, backoff và jitter không?
- Nếu request đã tới dependency rồi mất response, có rủi ro **ambiguous success** không?
- Có thể vượt deadline của client hoặc xấu đi khi dependency đang quá tải không?
- Mỗi retry attempt có log ERROR lớn gây log storm không?

Đừng viết `catch(Exception e) { retryForever(); }`. Một lỗi auth 401 từ dependency thường không biến mất bằng retry vô hạn; một database timeout cũng không tự chứng minh transaction chưa commit.

### 11.2. Log theo attempt và outcome

Ví dụ:

```text
attempt_failed operation=charge attempt=1 code=UPSTREAM_TIMEOUT
retry_requested operation=charge attempt=1 delayMs=250
attempt_failed operation=charge attempt=2 code=UPSTREAM_TIMEOUT
operation_failed operation=charge attempts=2 code=RETRY_EXHAUSTED
```

Đây là log minh họa, **không phải lời khuyên retry thanh toán mà thiếu idempotency**. Khi retry thành công, thay `operation_failed` bằng outcome `SUCCESS recovered=true`. Ở mức metrics, có thể đếm tất cả attempts, còn log ERROR cuối operation chỉ một lần theo trách nhiệm boundary.

### 11.3. Circuit breaker không phải “bắt lỗi rồi im lặng”

Một circuit breaker OPEN có thể chủ động từ chối gọi dependency để giảm tải. Đây là một **kết quả điều khiển**: log `dependency_circuit_open`/`short_circuited` với code ổn định, không giả vờ database vừa ném timeout cho request đó. Khi breaker đổi trạng thái, event `circuit_opened`/`circuit_closed` có giá trị quan sát riêng.

### 11.4. Fallback thành công vẫn cần quan sát

Nếu primary bị lỗi nhưng fallback hoạt động, thao tác cuối có thể `SUCCESS` hoặc `DEGRADED_SUCCESS`. Log `fallback_activated`/`degraded=true` và metric để operator biết hệ thống đang phụ thuộc đường dự phòng, nhưng không đánh dấu mọi request cuối cùng là lỗi nếu hợp đồng vẫn được đáp ứng.

## 12. Correlation, tracing và phân tán lỗi qua nhiều dịch vụ

Một technical error có thể đi từ service A -> B -> database. Nếu mỗi service đều ghi full stack trace của một timeout, việc điều tra có thể bị nhiễu. Hãy dùng:
- `trace_id`/`span_id`: liên kết các thao tác trong distributed tracing khi có.
- `request_id`/`correlation_id`: mã theo request/workflow, được sinh hoặc kiểm tra định dạng.
- `service` và `operation`: nguồn ghi và tác vụ.
- `dependency` và `error_code`: phân nhóm lỗi.
- `event_id`: định danh một lần ghi event nếu hệ thống cần deduplicate ingestion.

Một chuỗi correlation giúp liên hệ “B báo dependency timeout” và “A trả 503”; **không nên cộng hai log đó thành hai lỗi độc lập nếu đang đo số request lỗi**. Quan sát nên có số đo request-level và dependency-attempt-level riêng.

**MDC/ThreadContext** hữu ích để gắn request ID nhưng phải:
1. Chỉ đặt metadata được phép, không đưa token/header/body/credential.
2. Chuyển context qua async thread/pool theo công cụ đúng; không giả định `ThreadLocal` tự được truyền qua executor.
3. Dọn hoặc khôi phục `MDC` trong `finally`/scope khi hoàn tất.
4. Không tin raw correlation header từ client nếu nó chưa được kiểm tra về length/charset/trust.
5. Chú ý exception có thể được log ở thread khác sau khi request context đã đóng.

Traces cũng có thể ghi exception message và attributes tự động, nên cần chính sách bảo mật tương tự log. Không có lý do để log token ở span event chỉ vì ứng dụng đã tránh in token ở console.

## 13. Performance và độ tin cậy của technical error logs

Một hệ thống đang gặp sự cố đôi khi tạo **nhiều log hơn lúc khỏe**, gây hiệu ứng khuếch đại lỗi:
- Một dependency timeout làm hàng ngàn requests cùng in stack trace dài.
- Encoder serialize exception cause/suppressed và MDC lớn, tăng CPU/heap/GC.
- Async queue đầy gây drop/block; sync appender ghi file/network chậm làm request p99 tăng.
- Disk log đầy trở thành lỗi thứ hai; collector tiếp tục retry batch và làm tăng duplicate.
- Logger/appender lỗi rồi handler lại gọi cùng logger, có nguy cơ đệ quy hoặc log storm.

Cần đo:
- Technical errors theo `service/operation/error_code` (nhãn cardinality thấp).
- Error rate, p95/p99 latency, retry count, dependency timeout rate.
- Logging queue size, dropped events, formatter/serialization cost và bytes emitted.
- Disk/network pressure, retention, shipping failure và thời gian shutdown flush.
- Recovery time và số request bị ảnh hưởng.

**Không đặt `requestId`, full URL, exception message hay user ID vào metric label** khi số lượng giá trị gần như vô hạn. Giữ các ID ở log/trace, metric label dùng enum/nhóm ổn định.

### 13.1. Log failure của chính logger

Nếu file appender lỗi, việc gọi `logger.error("appender failed", e)` qua chính appender đó có thể không xuất được hoặc gây vòng. Sử dụng status logger/internal diagnostic channel độc lập, rate limit và health metrics. Audit quan trọng có thể cần một sink có độ bền riêng thay vì mặc định dựa vào pipeline best-effort.

### 13.2. Tính toàn vẹn và retention

Technical error logs có thể chứa stack trace, host names, request IDs và dữ liệu cá nhân gián tiếp. Chỉ giữ theo thời hạn cần thiết, phân quyền truy cập, mã hóa và quản lý backup/export. Nếu ứng dụng cần chứng cứ audit bắt buộc, phải thiết kế cách ghi bền vững (ví dụ outbox/transactional store) phù hợp; `logger.error` trả về **không phải lời hứa đã lưu thành công**.

## 14. Kiểm thử technical error logging

Một bộ test tốt nên xét **loại lỗi**, **đường truyền exception**, **kết quả nghiệp vụ** và **dòng log tại sink**.

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Input validation fail | Response/client error đúng; không tạo ERROR kỹ thuật giả |
| Business rule từ chối | Mã nghiệp vụ ổn định; không alarm như outage |
| Repository ném IOException | Cause được bảo toàn khi wrap; code và boundary đúng |
| Dependency timeout trước khi request tới đích | Retry policy phù hợp, không kết luận đã commit |
| Timeout sau khi gửi write | Hỗ trợ ambiguous outcome/idempotency, không tự replay mù |
| Retry thành công | Có attempt metrics; outcome cuối không báo FAILED |
| Retry hết giới hạn | Một operation-level failure với code chuẩn hóa |
| Unexpected RuntimeException | Ghi một lần ở boundary với ID tra cứu |
| Exception chứa password/token giả | Không xuất secret ở message/JSON/stack/collector đã kiểm tra |
| Exception có suppressed causes | Debug path bảo toàn thông tin nguồn nếu cần |
| InterruptedException / cancel | Hệ thống tôn trọng cancellation; không nhầm lỗi nghiêm trọng |
| Hai layer cùng log | Không nhân bản cùng stack trace ngoài chủ đích |
| Async logging queue đầy | Drop/block policy và metric rõ ràng |
| Appender hỏng | Diagnostics không quay lại cùng appender gây đệ quy |
| HTTP response đã commit | Boundary không cố trả hai response hoặc che lỗi |
| Message consumer crash trước ack | Redelivery/idempotency đúng; không ghi ACK confirmed giả |
| MDC qua thread pool | Correlation đúng, context dọn, không rò dữ liệu giữa requests |
| Collector nhân đôi log | Phân biệt duplicate ingestion với duplicate execution |

### 14.1. Kiểm thử stdout/handler ở unit test

Ví dụ Java 17 ở mục 6 đã dùng `CaptureHandler` để đối chiếu message. Trong test thực:
- Dựng logger riêng cho test, tắt parent handlers để không tác động hệ thống khác.
- Assert `event=technical_error` xuất đúng một lần tại boundary dự kiến.
- Assert mã lỗi và correlation ID hợp lệ; không phụ thuộc raw exception message.
- Dùng canary secret giả để đảm bảo không lọt ra **mọi trường** của event (message, MDC, structured keys, throwable renderer).
- Assert response code và transaction outcome riêng với log.
- Test cả appender/collector nếu có, không dừng ở text được capture trong unit test.

### 14.2. Fault injection

Trong staging, tạo các điều kiện có kiểm soát:
1. Database hết kết nối hoặc timeout có giới hạn.
2. Dependency trả 429/503 với retry policy khác nhau.
3. Client đóng kết nối giữa chừng.
4. Worker bị interrupt/cancel.
5. Appender/collector tạm không sẵn sàng.
6. Hai requests đồng thời gây lỗi giống nhau.
7. Process restart ở các mốc giữa DB commit và log/ack.

Quan sát số log, mã lỗi, độ trễ, retry, transaction và không có dữ liệu nhạy cảm. Không làm hỏng file log/database production chỉ để “thử WARN/ERROR”.

## 15. Những sai lầm thường gặp

| Sai lầm | Vì sao gây hại | Cách sửa |
| --- | --- | --- |
| Log `ERROR` cho mọi exception | Validation, business reject và cancel có thể là bình thường | Phân loại theo semantic/outcome |
| `logger.error(...)` rồi `throw` ở mọi layer | Trùng stack traces, méo error rate | Logging boundary rõ ràng |
| Wrap bằng `new RuntimeException(e.getMessage())` | Mất cause và có thể lộ secret | `super(message, cause)` với mã lỗi an toàn |
| Bắt `Exception` rồi trả success | Che lỗi, dữ liệu sai, khó retry | Propagate/map đúng contract |
| Chỉ log `e.getMessage()` | Thiếu root cause/type và context, có thể lộ secret | Safe error code, cause preservation |
| Log toàn bộ `request`/`body` với stack trace | Rò PII/token, tăng dung lượng | Metadata/allowlist, kiểm soát throwable |
| Trả stack trace về HTTP client | Lộ đường dẫn, cấu trúc nội bộ, bí mật | Mã lỗi công khai + errorId |
| Dùng exception class làm retry policy | Không phân biệt timeout đã commit/không commit | Retry theo idempotency và contract |
| Log mỗi retry như operation cuối thất bại | Alert storm/false alarms | Tách attempt-level và final outcome |
| Dùng một code `INTERNAL_ERROR` cho mọi thứ ở nội bộ | Khó phân loại và điều tra | Mã lỗi nội bộ có hệ thống |
| Dựa vào log là chứng cứ transaction commit | Log có thể mất/có trước rollback | Dùng durable audit/outbox khi bắt buộc |
| Tin MDC tự chạy qua mọi async task | Context thất lạc hoặc trộn giữa threads | Propagate/cleanup theo scope |
| Đưa request ID vào metric label | Cardinality rất cao | ID ở log/trace, metric label ổn định |
| Bắt `Throwable` và retry cả `Error` | Che lỗi JVM/lifecycle nghiêm trọng | Bắt theo contract, không nuốt error |
| Không restore interrupt | Mất tín hiệu hủy, treo shutdown | `Thread.currentThread().interrupt()` |
| Log lỗi appender bằng chính appender | Đệ quy/log storm/mất diagnostics | Status channel độc lập |
| Chỉ xem exception message | Không biết operation, dependency, customer impact | Structured fields và correlation |

## 16. Bài tập tự kiểm tra

**Câu 1 — Business hay technical?** API nhận request hợp lệ nhưng khách hàng không đủ số dư. Có phải một `technical_error` cần alert SEVERE?

**Đáp án:** thường **không**. Đây là business rejection dự kiến; trả mã kết quả hợp đồng và ghi INFO/audit khi cần. Nếu hệ thống tính số dư bị lỗi database thì đó lại là lỗi kỹ thuật.

**Câu 2 — Log hai lần?** Repository gọi `logger.error("read failed", e)` rồi throw; service cũng gọi logger và rethrow; HTTP handler ghi stack trace. Số dòng ERROR nhiều chứng minh ba sự cố độc lập không?

**Đáp án:** **không**. Có thể cả ba chỉ mô tả một failure. Nên chọn boundary sở hữu log cuối cùng và giữ cause/context giữa các tầng.

**Câu 3 — Retry database timeout.** Một thao tác tạo đơn hàng gửi xong nhưng không nhận response. Có thể lập tức retry vô hạn vì lỗi thuộc class `TimeoutException` không?

**Đáp án:** **không**. Cần xem khả năng thao tác đã commit, idempotency key, deadline, retry budget, backoff và reconcile. Exception class một mình không xác định việc retry an toàn.

**Câu 4 — Cause preservation.** Vì sao `throw new RuntimeException(e.getMessage())` không tốt bằng `throw new TechnicalFault("DEPENDENCY_UNAVAILABLE", e)`?

**Đáp án:** phiên bản đầu làm mất cause chain và có thể copy dữ liệu nhạy cảm từ raw message. Phiên bản sau lưu nguyên nhân để điều tra và dùng mã lỗi ổn định.

**Câu 5 — Secret trong exception.** Một thư viện ném `IOException("url?api_key=secret")`. Việc trả `e.getMessage()` về client hoặc ghi không kiểm soát có rủi ro nào?

**Đáp án:** có thể lộ credential cho client, log viewer hoặc collector. Hãy dùng mã lỗi, dependency alias và error ID an toàn; xem xét nơi lưu stack trace theo quyền/policy.

**Câu 6 — Interruption.** Một worker bắt `InterruptedException` nhưng không rethrow và không restore interrupt. Có thể ảnh hưởng gì?

**Đáp án:** tầng trên có thể mất tín hiệu hủy, task tiếp tục hoặc shutdown chậm. Nếu không truyền exception tiếp, thường nên restore interrupt status và kết thúc công việc theo contract.

**Câu 7 — Outcome.** Dependency fail ở attempt đầu nhưng retry lần hai thành công. Có nên log `operation_failed` cho request không?

**Đáp án:** không nên nếu outcome cuối là thành công. Có thể log `attempt_failed`, `retry_scheduled` và `operation_completed recovered=true`, cùng metrics về retry.

## 17. Checklist production cho Technical error logs

Trước khi đưa logging exception vào production, kiểm tra:

1. **Có taxonomy rõ ràng**: validation, business, authn/authz, technical transient/permanent, unexpected defect, cancellation.
2. **Exception được truyền đúng nghĩa**: bảo toàn `cause`, không che lỗi thành success, không bắt quá rộng.
3. **Có logging boundary** cho HTTP, message consumer, job/executor; không log cùng stack trace nhiều tầng.
4. **Schema có event/error code/operation/outcome/request ID**, dependency và service khi cần; không nhét mọi context vào message tự do.
5. **Level phản ánh kết quả cuối và mức ảnh hưởng**, phân biệt attempt-level với operation-level.
6. **Retry có idempotency, timeout, backoff và giới hạn**, xử lý trường hợp không chắc dependency đã commit.
7. **Client response an toàn**, không trả stack trace, SQL, token hay lỗi hạ tầng chi tiết.
8. **Throwable logging được review**, gồm message, cause, suppressed, MDC, structured fields và sink phụ.
9. **Correlation hoạt động qua async/distributed boundaries**; MDC/context được cleanup; ID không do client tự quyết tùy ý.
10. **Metrics/alerts dùng label cardinality thấp**, quan sát error rate, retries, queue depth, log loss và dependency health.
11. **Kiểm thử lỗi giả lập** ở các đường success/reject/timeout/bug/cancel/recovery và có test canary secret.
12. **Quyền truy cập, retention, backup và audit log** được bảo vệ theo chính sách; không coi logger thông thường là transactional audit store.
13. **Không tạo đệ quy logging** khi appender hỏng; có internal status/health diagnostics độc lập.
14. **Có quy trình incident response** cho credential/PII vô tình xuất trong exception logs.

**Kết luận:** Technical error logging hiệu quả không phải là in càng nhiều stack trace càng tốt. Hãy **phân biệt lỗi kỹ thuật với kết quả nghiệp vụ**, giữ nguyên nhân exception đúng cách, ghi một event chẩn đoán có cấu trúc tại boundary phù hợp, và dùng correlation ID để nối các dấu vết. Khi kết hợp retry/idempotency, bảo mật log, metrics và kiểm thử lỗi thực tế, hệ thống Java vừa dễ điều tra vừa tránh nhân bản log, rò rỉ dữ liệu và làm trầm trọng sự cố.