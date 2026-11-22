# Error code trong Java Core Logging và xử lý exception

## 1. Error code là gì?

**Error code** là một định danh có cấu trúc, ổn định cho **loại lỗi** mà ứng dụng biết cách phân loại. Khi log chỉ chứa `"Request failed"` hoặc `"Lỗi xảy ra"`, người vận hành phải tìm hiểu bằng cách đọc message, stack trace, class Java hoặc truy vấn regex dễ vỡ. Khi thêm `errorCode` chuẩn hóa, ứng dụng và hệ thống giám sát có thể tìm, thống kê, phân biệt và liên kết từng nhóm lỗi mà không phụ thuộc ngôn ngữ thông báo.

Ví dụ:

~~~text
2026-11-10T03:00:00Z ERROR event=payment_failed errorCode=PAY-TIMEOUT requestId=req-101 retryable=true
2026-11-10T03:00:02Z ERROR event=payment_failed errorCode=PAY-TIMEOUT requestId=req-204 retryable=true
2026-11-10T03:00:04Z WARN  event=order_rejected errorCode=ORD-STATE-CONFLICT requestId=req-205 retryable=false
~~~

Hai dòng đầu có cùng **loại lỗi** nhưng **khác request**. Mã `PAY-TIMEOUT` không phải định danh duy nhất của một occurrence. Cũng không phải mọi lỗi có mã giống nhau đều cần phát sinh nhiều log ERROR trong một lần retry: đó là quyết định về logging policy.

Các lợi ích cụ thể:

- Truy vấn log và dựng dashboard theo `errorCode` thay vì parse chuỗi `Throwable.getMessage()`.
- Liên kết với runbook, đội phụ trách, severity/priority và gợi ý khắc phục.
- Phân biệt dữ liệu người dùng sai, nghiệp vụ bị từ chối, dependency lỗi và bug chưa biết.
- Duy trì hợp đồng lỗi cho client khi sửa code hoặc dịch message sang ngôn ngữ khác.
- Cho phép support nhận `requestId` hoặc `errorOccurrenceId` rồi đối chiếu loại lỗi trong log nội bộ được cấp quyền.
- Cấp khả năng tổng hợp metrics có cardinality thấp nếu mã được quản trị như **tập hữu hạn**.

Không nên sinh mã lỗi bằng cách hash message exception, ghép userId/orderId, lấy tên method/frame ngẫu nhiên hoặc dùng mỗi `UUID.randomUUID()`. Những giá trị đó hoặc bị thay đổi tùy request, hoặc không thể hiện **loại** lỗi.

## 2. Các khái niệm liên quan phải tách bạch

| Trường | Chức năng | Ví dụ | Đặc điểm |
| --- | --- | --- | --- |
| `errorCode` | Loại lỗi theo taxonomy của ứng dụng | `ORD-NOT-FOUND` | Giữ ổn định khi cùng một tình huống |
| `exceptionClass` | Kiểu đối tượng Java phát sinh | `IllegalStateException` | Có thể đổi do refactor |
| `message` | Thông báo cho con người | `Order not found` | Có thể dịch/sửa câu chữ |
| `httpStatus` | Kết quả HTTP tại API boundary | `404`, `409`, `503` | Phản ánh giao thức, không đủ diễn tả domain |
| `logLevel` | Mức chú ý của logging | `WARN`, `ERROR` | Được chọn theo giá trị vận hành |
| `retryable` | Hint theo loại lỗi/operation | `true` | Không bảo đảm retry side effect an toàn |
| `requestId` | Một request/correlation đầu vào | `req-101` | Nhiều event cùng request |
| `traceId` / `spanId` | Tracing phân tán | trace/span ID | Không phải lỗi hay idempotency key |
| `errorOccurrenceId` | Một lần lỗi cụ thể | `err-00042` | Khác cho occurrence khác khi có contract |
| `eventId` | Một lần phát log event | `logevt-005` | Dùng phát hiện duplicate ingest nếu được bảo toàn |

Trong một hệ thống, `ORD-NOT-FOUND` có thể xảy ra hàng triệu lần nhưng vẫn chỉ là **một loại lỗi**. Nếu dùng mỗi occurrence ID làm errorCode, metric `errors_total{error_code=...}` sẽ tạo nhãn mới cho từng request, gây high cardinality. Nếu dùng requestId thay errorCode, không thể tổng hợp theo nguyên nhân.

**Error code không đồng nghĩa HTTP status.** HTTP 409 Conflict có thể ứng với order state conflict, version conflict hoặc idempotency key conflict; các loại này cần hướng xử lý khác nhau. **Error code cũng không đồng nghĩa log level.** 404 có thể là outcome bình thường và chỉ cần INFO, còn 500 bất ngờ thường cần ERROR và stack trace trong sink nội bộ.

## 3. Thiết kế taxonomy có ý nghĩa và ổn định

Một catalog mã lỗi nên có scope rõ (service, domain hoặc API), chủ sở hữu và quy tắc thay đổi. Ví dụ:

| Error code minh họa | Ý nghĩa | HTTP tham khảo | Severity tham khảo | Retry? |
| --- | --- | --- | --- | --- |
| `REQ-VALIDATION-001` | Request không đáp ứng schema/hợp đồng | 400/422 theo semantics | INFO/WARN | Không nếu input không đổi |
| `ORD-NOT-FOUND` | Order không tồn tại/không nhìn thấy theo policy | 404 | INFO/WARN | Thường không |
| `ORD-STATE-CONFLICT` | Trạng thái/version không cho phép thao tác | 409 | WARN | Cần đọc state mới |
| `AUTH-FORBIDDEN` | Principal không được phép thao tác | 403 | WARN/audit | Không nếu quyền không đổi |
| `PAY-TIMEOUT` | Dependency thanh toán timeout | 503/504 tùy layer | WARN/ERROR | Cần kiểm tra idempotency |
| `DB-UNAVAILABLE` | Backend dữ liệu tạm không sẵn sàng | 503/500 tùy boundary | ERROR | Có điều kiện |
| `SYS-UNEXPECTED` | Lỗi chưa nhận diện / bug | 500 | ERROR | Không mặc định |

Đây là **mã do bài học đặt ra**, không phải chuẩn do Java, HTTP hay một framework quy định. Mỗi sản phẩm có thể dùng `E_ORDER_NOT_FOUND` hoặc `ORD-0042`, miễn contract được áp dụng đồng nhất.

Quy tắc đặt mã:

1. **Đặt theo ngữ nghĩa, không theo chi tiết implementation.** `PAY-TIMEOUT` không phải `SocketTimeoutException#34`; thay thư viện HTTP không cần đổi public code.
2. **Không tái sử dụng mã cũ cho nghĩa mới.** Nếu semantics không còn tương thích, thêm mã mới, version hoặc deprecate có lộ trình.
3. **Không thay mã khi thay message hoặc dịch ngôn ngữ.** API client và dashboard có thể dùng code; message là để hiển thị.
4. **Phân biệt các hành động khác nhau.** Validation permanent và dependency timeout transient không nên cùng `GENERAL_ERROR` nếu chúng cần policy retry khác nhau.
5. **Không mã hóa dữ liệu động vào mã.** Order ID, tenant ID, hostname, email và port nằm ở field khác có kiểm soát.
6. **Không biến mọi class Exception thành một error code.** Các exception quá thấp như `IllegalArgumentException` cũng có thể do lỗi lập trình, không luôn do request sai.
7. **Có mã fallback an toàn** như `SYS-UNEXPECTED` nhưng theo dõi tỷ lệ fallback để phát triển catalog khi có nhu cầu thực.
8. **Có namespace/ownership rõ** nếu nhiều service dùng chung catalog. Tránh hai domain dùng trùng mã với nghĩa trái ngược.

### Catalog nên có những gì?

Với mỗi code, ghi mô tả trigger cụ thể, trường hợp không được áp mã, ownership/team, ví dụ log, policy trả response, retryability, severity, public-safe title, link runbook, version và ngày deprecated nếu có. Nên có contract test để không sửa xóa mã theo cách phá tương thích.

Một service nhỏ có thể khai báo enum, hệ thống lớn có thể có shared catalog/schema. Không vì muốn chia sẻ mà buộc domain logic phụ thuộc trực tiếp một HTTP enum hoặc Logback class: mapping transport có thể nằm ở adapter.

## 4. Exception class, root cause và boundary xử lý

Luồng exception Java có thể nhiều tầng:

~~~text
HTTP controller / message consumer
          |
          v
Application service
          |
          +--> Domain check -> DomainException(ORD-STATE-CONFLICT)
          |
          +--> Payment adapter -> IOException / timeout
                                   được phân loại PAY-TIMEOUT
~~~

Tầng domain nêu tình huống nghiệp vụ hoặc trả kết quả kiểu `Result`; adapter chuyển lỗi kỹ thuật của dependency sang error code có nghĩa; boundary quyết định log severity, response HTTP hoặc retry/DLQ.

Ví dụ trong domain:

~~~java
// Snippet minh họa: một class DomainException riêng của ứng dụng.
public final class DomainException extends RuntimeException {
    private final String errorCode;

    public DomainException(String errorCode, String safeMessage,
                           Throwable cause) {
        super(safeMessage, cause);
        this.errorCode = errorCode;
    }

    public String errorCode() {
        return errorCode;
    }
}
~~~

Kiểu nhận `String` ở đây giúp hiểu ý tưởng, nhưng production nên dùng **catalog/enum** để tránh caller tự đặt mã tùy tiện. Cần giữ nguyên nhân bằng `cause` khi phục vụ điều tra, song không có nghĩa được ghi nguyên tất cả message/stack trace vào mọi sink: exception có thể chứa SQL, URL query, access token hoặc PII.

**Không map bằng text exception:**

~~~java
// Không nên: message có thể thay đổi theo ngôn ngữ, dependency hoặc dữ liệu.
if (exception.getMessage().contains("not found")) {
    code = "ORD-NOT-FOUND";
}
~~~

Nếu exception đã được thiết kế với loại và mã ổn định thì map theo kiểu đó. Với thư viện bên thứ ba, adapter có thể map theo **typed exception + trạng thái/protocol** được tài liệu hóa; nếu không đủ bằng chứng, fallback an toàn.

### Xử lý exception bọc trong async

`CompletionException`, `ExecutionException` và một số wrapper do framework tạo có thể có `getCause()`. Nếu cause là domain exception được phân loại thì có thể giữ code. Tuy nhiên, việc duyệt toàn bộ cause để tìm một `IllegalArgumentException` là sai: lỗi lập trình trong thư viện cũng có thể dùng loại exception này.

Khi xử lý `InterruptedException`, cần duy trì semantics hủy/interrupt; nếu bắt để cleanup trong Java, cân nhắc `Thread.currentThread().interrupt()` khi phù hợp. Không dùng `catch (Throwable)` bao mọi thứ rồi chạy tiếp như bình thường; `Error` như OutOfMemoryError không phải domain validation.

## 5. Java 17 hoàn chỉnh: phân loại exception và ghi mã lỗi

Chương trình này chỉ dùng **JDK 17**. Nó tạo enum mã lỗi, tìm exception có code trong cause chain, chọn `httpStatus`/`retryable`/mức JUL tương ứng, sau đó phát event qua `java.util.logging`.

Lưu **`ErrorCodeDemo.java`**:

~~~java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import java.util.concurrent.CompletionException;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ErrorCodeDemo {
    enum ErrorCode {
        INPUT_INVALID("REQ-VALIDATION-001", Level.WARNING, 400, false),
        ORDER_NOT_FOUND("ORD-NOT-FOUND", Level.INFO, 404, false),
        PAYMENT_TIMEOUT("PAY-TIMEOUT", Level.SEVERE, 503, true),
        UNEXPECTED("SYS-UNEXPECTED", Level.SEVERE, 500, false);

        final String value;
        final Level level;
        final int httpStatus;
        final boolean retryable;

        ErrorCode(String value, Level level, int httpStatus,
                  boolean retryable) {
            this.value = value;
            this.level = level;
            this.httpStatus = httpStatus;
            this.retryable = retryable;
        }
    }

    static final class AppException extends RuntimeException {
        final ErrorCode errorCode;

        AppException(ErrorCode errorCode, Throwable cause) {
            super(errorCode.name(), cause);
            this.errorCode = errorCode;
        }
    }

    static ErrorCode classify(Throwable error) {
        Set<Throwable> visited =
                Collections.newSetFromMap(new IdentityHashMap<>());

        for (Throwable current = error;
             current != null && visited.add(current);
             current = current.getCause()) {

            if (current instanceof AppException app) {
                return app.errorCode;
            }
        }

        return ErrorCode.UNEXPECTED;
    }

    static void logFailure(Logger log, String requestId,
                           Throwable error) {
        ErrorCode code = classify(error);
        LogRecord record = new LogRecord(
                code.level,
                "event=request_failed errorCode=" + code.value
                + " requestId=" + requestId
                + " retryable=" + code.retryable
                + " httpStatus=" + code.httpStatus);

        record.setLoggerName(log.getName());
        record.setThrown(error);
        log.log(record);
    }

    static final class MessageOnlyHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                System.out.println(record.getMessage());
            }
        }

        @Override
        public void flush() {
            // Không có I/O đệm riêng.
        }

        @Override
        public void close() {
            // Không giữ tài nguyên bên ngoài.
        }
    }

    public static void main(String[] args) {
        Logger log = Logger.getLogger("demo.error.codes");
        log.setUseParentHandlers(false);
        log.setLevel(Level.ALL);

        MessageOnlyHandler sink = new MessageOnlyHandler();
        sink.setLevel(Level.ALL);
        log.addHandler(sink);

        try {
            logFailure(log, "req-100",
                    new AppException(ErrorCode.INPUT_INVALID, null));
            logFailure(log, "req-101",
                    new CompletionException(
                        new AppException(
                            ErrorCode.PAYMENT_TIMEOUT,
                            new IllegalStateException("gateway timeout"))));
            logFailure(log, "req-102",
                    new IllegalStateException("unexpected condition"));
        } finally {
            log.removeHandler(sink);
            sink.close();
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ErrorCodeDemo.java
java ErrorCodeDemo
~~~

**Stdout xác định** (logic tương đương đã chạy bằng JShell, chỉ dùng API từ Java 17):

~~~text
event=request_failed errorCode=REQ-VALIDATION-001 requestId=req-100 retryable=false httpStatus=400
event=request_failed errorCode=PAY-TIMEOUT requestId=req-101 retryable=true httpStatus=503
event=request_failed errorCode=SYS-UNEXPECTED requestId=req-102 retryable=false httpStatus=500
~~~

Giải thích:

1. `ErrorCode` là catalog nhỏ của bài học. `Level.WARNING` và `Level.SEVERE` thuộc JUL, tương tự ý nghĩa log WARN/ERROR phổ biến nhưng không là enum của Logback/SLF4J.
2. `AppException` nêu code do application biết rõ. `classify(...)` chỉ lấy kiểu `AppException` đầu tiên trong cause chain, không suy từ một chuỗi message không ổn định.
3. `IdentityHashMap` cùng một `Set` dựa trên identity giúp dừng nếu gặp chuỗi cause bất thường lặp lại. Tình huống thường gặp vẫn là một chuỗi acyclic.
4. `CompletionException` bọc `PAY-TIMEOUT` không làm mất mã. `IllegalStateException` chưa biết dẫn tới `SYS-UNEXPECTED`.
5. `LogRecord` có `level`, `message` và `thrown`. Handler trong demo cố ý chỉ in message nên stdout ổn định; handler thực có thể in stack trace và cần chính sách redaction.
6. `setUseParentHandlers(false)` tránh logger root xuất thêm một bản ghi làm output bị trùng.
7. `httpStatus` chỉ là metadata của demo, chương trình **không trả HTTP response**; `retryable=true` không gọi retry. Ở ứng dụng đa transport, nên tách HTTP mapper khỏi domain enum.

**Giới hạn:** ví dụ mô tả policy khi không có request từ mạng, không kiểm thử SQL/HTTP hay exception message chứa PII. Không sao chép nguyên cơ chế log throwable ra public sink. `requestId` phải được tạo/kiểm tra và giới hạn ký tự ở boundary thực.

## 6. Structured logging: ghi code thành trường dễ query

Trong hệ thống thực, nên sử dụng structured log JSON hoặc encoder có trường cố định:

~~~json
{
  "timestamp": "2026-11-10T03:15:00Z",
  "level": "ERROR",
  "service": "checkout",
  "event": "payment_failed",
  "errorCode": "PAY-TIMEOUT",
  "errorCategory": "dependency",
  "requestId": "req-101",
  "traceId": "4f0e2c13b69a497389d74e71a52b4e62",
  "retryable": true,
  "attempt": 3,
  "outcome": "failed",
  "durationMs": 4100
}
~~~

Đây là JSON minh họa, không phải output của `ErrorCodeDemo`. Field `traceId` được điền giá trị giả; giá trị thật phải đến từ tracing context được quản lý. Không đưa full request body, password, auth header hay stack trace chưa kiểm soát vào JSON.

Một tập trường ổn định thường gồm:

- `event`: loại sự kiện log như `payment_failed`.
- `errorCode`: loại lỗi chuẩn; không dùng nguyên exception message.
- `errorCategory`: nhóm như `validation`/`domain`/`dependency`/`unexpected` nếu hữu ích.
- `requestId`, `traceId`: correlation, không phải error taxonomy.
- `attempt`, `outcome`: phân biệt lỗi tạm trong retry và thất bại cuối cùng.
- `service`/`instance`/`version`: định vị nơi phát.
- `exceptionType` hoặc stack trace ở sink nội bộ bảo vệ khi cần.
- `httpStatus` chỉ nếu event có ngữ cảnh HTTP, không ép vào mọi job/consumer.

**Không xây dashboard bằng regex parse lời thông báo nếu có thể xuất field độc lập.** Đổi ngôn ngữ message không nên làm hỏng số liệu theo `errorCode`.

### SLF4J parameterized logging

Ví dụ snippet SLF4J (**cần dependency/backend, không phải JDK-only**):

~~~java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(PaymentService.class);

void reportFailure(String requestId, String errorCode,
                   Throwable cause) {
    LOG.error("event=payment_failed errorCode={} requestId={}",
            errorCode, requestId, cause);
}
~~~

`PaymentService` là class của ứng dụng, không có sẵn trong snippet. Với SLF4J, throwable được truyền ở cuối lời gọi varargs và backend có thể ghi stack trace. Đừng tự chuyển `cause` thành string rồi lại truyền throwable dẫn đến hai bản stack trace.

SLF4J 2.x hỗ trợ fluent key–value API:

~~~java
LOG.atError()
   .addKeyValue("event", "payment_failed")
   .addKeyValue("errorCode", errorCode)
   .addKeyValue("requestId", requestId)
   .setCause(cause)
   .log("Payment failed");
~~~

Đây cũng là snippet cần SLF4J 2.x và backend tương thích. Có các key–value trong API không tự bảo đảm output JSON: cần encoder/layout hỗ trợ và integration test với runtime đang dùng.

## 7. HTTP API: error code và RFC 9457 Problem Details

Với HTTP, **Problem Details** theo RFC 9457 cung cấp định dạng `application/problem+json` gồm các trường như `type`, `title`, `status`, `detail`, `instance`. Ứng dụng có thể bổ sung `errorCode` và `requestId` làm **extension members**.

Một response minh họa:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "The requested order was not found.",
  "instance": "/problems/occurrences/err-24",
  "errorCode": "ORD-NOT-FOUND",
  "requestId": "req-101"
}
~~~

`api.example.com` và các ID trên chỉ là dữ liệu ví dụ. **Theo RFC 9457, `type` là định danh primary của problem type**; `errorCode` là extension application-specific, không thay `type`. `instance` định danh một occurrence chứ không là code taxonomy.

Một số quy tắc:

- `status` trong body phải khớp HTTP response status do origin server tạo. Không gắn 404 trong JSON khi response thật là 500.
- `title` là tóm tắt cho loại problem; `detail` giúp client hiểu/sửa request, **không** chứa stack trace, SQL, password hoặc host nội bộ.
- `type` cần ổn định nếu client dùng để phân nhánh, có thể liên kết tới tài liệu. Không nên để client tùy tiện dereference URI chưa đáng tin.
- `instance` không nên chứa dữ liệu nhận dạng nhạy cảm. Nếu nhận requestId để support, cần giới hạn quyền tra cứu, tránh lộ log của user khác.
- `errorCode` nếu được thêm phải có hợp đồng version/stability riêng; không ghi mã nội bộ có thể tiết lộ cấu trúc hạ tầng nếu không được phép.
- `Retry-After` có thể hữu ích cho tình huống phù hợp; retry vẫn phải xét idempotency, budget và trạng thái side effect.
- RFC 9457 **obsoletes RFC 7807**. API đang có định dạng lỗi khác có thể tiếp tục dùng nếu được quản trị ổn định; không nhất thiết đổi chỉ vì muốn thêm mã.

### Ví dụ map HTTP nhưng không trộn tầng

| Lỗi của ứng dụng | Mã | Status theo contract mẫu | Ý nghĩa cho client |
| --- | --- | --- | --- |
| Không đúng dữ liệu đầu vào | `REQ-VALIDATION-001` | 400 | Sửa request |
| Không tìm thấy order | `ORD-NOT-FOUND` | 404 | Kiểm tra trạng thái/ID được phép truy cập |
| Order version conflict | `ORD-STATE-CONFLICT` | 409 | Đọc lại state và giải xung đột |
| Principal thiếu quyền | `AUTH-FORBIDDEN` | 403 | Xin quyền phù hợp |
| Dependency tạm unavailable | `PAY-TIMEOUT` | 503 trong mẫu | Thử lại có kiểm soát nếu an toàn |
| Unexpected bug | `SYS-UNEXPECTED` | 500 | Liên hệ support với requestId |

Một timeout ở upstream có thể được gateway trả 504 trong một số kiến trúc; không coi `PAY-TIMEOUT` đồng nhất 503 cho mọi transport. HTTP status nên do adapter cuối quyết định theo RFC 9110 và hợp đồng ứng dụng.

## 8. Error code trong message consumer, job và async task

Với message broker hoặc batch, HTTP status thường **không tồn tại**. Error code giúp chọn policy xử lý:

~~~text
Consume message / run job
       |
       v
Validate context + process
       |
       +-- Success -> ACK/commit/outcome success
       |
       +-- Transient failure -> retry có giới hạn/backoff
       |
       +-- Permanent failure -> reject/DLQ theo policy
       |
       +-- Unknown failure -> alert và xử lý an toàn
~~~

Log có thể như:

~~~json
{
  "event": "message_processing_failed",
  "messageId": "msg-1001",
  "consumer": "billing-worker",
  "errorCode": "PAY-TIMEOUT",
  "retryable": true,
  "attempt": 2,
  "action": "retry_scheduled",
  "correlationId": "flow-42"
}
~~~

Cùng message có thể bị redeliver sau ACK/commit không chắc chắn; không dùng errorCode thay `messageId` hay `idempotencyKey`. Một code có thể xuất ở mỗi attempt, nhưng **metric failure cuối cùng** nên tính theo outcome của operation, không đơn giản đếm mọi dòng ERROR.

Phân biệt:

- **Temporary:** timeout/dependency unavailable; retry có backoff, limit, kiểm tra có side effect chưa.
- **Permanent:** dữ liệu không hợp lệ, schema không hỗ trợ, resource/permission không cho phép; xử lý DLQ, quarantine, hoặc reject theo policy.
- **Unknown:** exception không thuộc catalog; phải log chẩn đoán trong sink bảo vệ, alert; tránh retry vô hạn.
- **Cancellation/interrupt:** không coi mặc định là lỗi nghiệp vụ. Tôn trọng contract dừng task.

Khi chuyển vào DLQ, có thể giữ `originalMessageId`, `failureCode`, `attempts`, `firstFailureAt`, `lastFailureAt`, source/destination và summary an toàn. Đừng chép nguyên stack trace hoặc secret trong headers để “giữ nguyên nhân” nếu không có kiểm soát quyền.

## 9. Retryable không nghĩa là được phép retry mọi thao tác

`retryable` nên được hiểu là một **hint**. Khả năng retry an toàn phụ thuộc operation:

| Error code | Cách xử lý thường gặp | Rủi ro nếu retry mù |
| --- | --- | --- |
| `REQ-VALIDATION-001` | Sửa input | Tạo spam, không bao giờ thành công |
| `ORD-NOT-FOUND` | Kiểm tra ID/state theo hợp đồng | Tăng tải vô ích |
| `ORD-STATE-CONFLICT` | Đọc state mới, giải conflict | Race điều kiện cập nhật |
| `AUTH-FORBIDDEN` | Xác minh quyền, không retry tự động | Thăm dò quyền hoặc rate-limit |
| `PAY-TIMEOUT` | Kiểm tra trạng thái charge và idempotency key | Trừ tiền hai lần |
| `DB-UNAVAILABLE` | Backoff + deadline, circuit breaker | Retry storm khi DB đang quá tải |
| `SYS-UNEXPECTED` | Điều tra/alert; không mặc định retry | Che bug, lặp side effect |

Nếu request POST đã commit nhưng response bị mất, timeout ở client không chứng minh thất bại. Dùng idempotency key hoặc trạng thái nghiệp vụ trước khi retry. Tại HTTP, `Retry-After` có thể cung cấp thời gian chờ hợp lý. Tại message consumer, retry topic, dead-letter, ACK và side effect cần contract riêng.

Không nên đưa `attempt=2` vào errorCode thành `PAY-TIMEOUT-ATTEMPT-2`; attempt phải là field khác. Cũng không dùng `errorCode` làm idempotency key vì nhiều operation khác nhau có thể cùng một code.

## 10. Tránh log trùng và chọn mức log có ý nghĩa

Một exception có thể đi từ repository lên service rồi HTTP handler. Nếu tầng nào cũng:

~~~java
catch (Exception ex) {
    log.error("failed", ex);
    throw ex;
}
~~~

thì một failure có thể tạo nhiều stack trace, gây alert trùng. Đoạn trên chỉ là snippet trong một khối `try` có logger phù hợp. Mã lỗi giúp nhóm các event nhưng **không tự loại duplicate**.

Thiết kế có trách nhiệm rõ:

1. **Domain/adapter:** tạo exception đã phân loại và giữ cause, có thể thêm metadata an toàn.
2. **Service:** chỉ log khi có một sự kiện mới (fallback invoked, retry scheduled, business compensation), không log full stack trace vô điều kiện rồi rethrow.
3. **Boundary cuối:** quyết định response/retry và ghi một record kết quả thất bại cần thiết với errorCode, requestId, outcome.
4. **Logging backend:** tránh appender con/root ghi cùng event hai lần do additivity; integration test số record tại sink.
5. **Metrics:** đếm operation/request failure theo outcome, không đếm số lần stack trace in ra.

Validation 400 có thể log INFO/WARN tùy hành vi dự kiến; 404 không mặc định là sự cố server nghiêm trọng. ERROR dùng cho failure quan trọng chưa được xử lý/khôi phục. Đừng chỉnh level lên ERROR cho mọi code chỉ vì tên nó là “error”.

## 11. Context và MDC: tránh lẫn mã lỗi giữa request

SLF4J MDC gắn metadata với **thread hiện tại**. Nếu dùng MDC cho `requestId`/`traceId`, luôn cleanup trong `finally` để request B không mang requestId của A. `errorCode` có thể là field trên **event** thường tốt hơn MDC kéo dài cả request: nếu bạn đặt errorCode vào MDC sau một lỗi rồi quên xóa, các event thành công tiếp theo có thể bị gắn mã lỗi cũ.

Ví dụ scoped MDC minh họa (cần SLF4J, không phải chương trình JDK thuần):

~~~java
import java.util.Map;
import org.slf4j.MDC;

Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("requestId", requestId);
    processRequest();
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
~~~

`requestId` và `processRequest()` là thành phần của ứng dụng. Khi dùng ExecutorService/CompletableFuture, context có thể không tự lan sang worker thread; capture snapshot khi submit và restore/cleanup theo boundary, không lấy MDC của thread writer async thay cho context tại lúc event được tạo.

Tránh đưa dữ liệu bí mật vào MDC: bất kỳ appender/encoder có thể xuất trường đó. Một formatter hiển thị `%X{requestId}` không tự sanitize input.

## 12. Bảo mật: public code và internal cause không giống nhau

Lỗi kỹ thuật có thể chứa SQL, hostname, URL query, token, cookie và dữ liệu cá nhân. **Không đưa raw exception message/stack trace ra public response**, kể cả khi errorCode đã được gắn đúng.

Ví dụ không nên:

~~~text
errorCode=SQL_ERROR_FOR_john@example.com
message=Connect failed with Authorization: Bearer <secret>
~~~

Đây là ví dụ dữ liệu giả về định dạng xấu, không phải dữ liệu thật. Error code phải đến từ catalog đã duyệt, không từ input và không chứa userId/email/token.

Nên tách:

- **Public error:** mã công khai ổn định (`SYS-UNEXPECTED`), thông báo an toàn, requestId/occurrenceId đã kiểm soát.
- **Internal log:** code, event, dependency, exception type, stack trace được phép, context nghiệp vụ cần thiết và đã redaction.
- **Audit/security log:** sự kiện truy cập, từ chối quyền hoặc thay đổi quyền theo retention/access policy; khác log chẩn đoán thường.
- **Monitoring:** metrics theo code/category, không bao gồm userId hoặc URL động làm nhãn.

Cần lưu ý nguy cơ **user enumeration**: trong quy trình reset password/login, trả các mã phân biệt “email tồn tại” và “email không tồn tại” có thể lộ tài khoản; theo threat model có thể phải dùng public response thống nhất, trong khi internal audit có mã riêng phù hợp.

Lọc ký tự xuống dòng/control của input trước khi log để giảm log injection. Parameterized logging hỗ trợ định dạng nhưng **không tự mã hóa hoặc ẩn PII**. Bảo vệ log bằng ACL/RBAC, retention, encryption, audit truy cập và data minimization.

## 13. Monitoring bằng mã lỗi và giới hạn cardinality

Mã lỗi hữu hạn phù hợp với metric label:

~~~text
requests_failed_total{service="checkout",error_code="PAY-TIMEOUT",route="/orders"}
requests_failed_total{service="checkout",error_code="ORD-STATE-CONFLICT",route="/orders"}
~~~

Đây là ví dụ dạng Prometheus text, **không phải metric được xuất bởi Java demo**.

Không đưa `requestId`, `errorOccurrenceId`, `userId`, `messageId`, exception message hoặc path chứa ID động làm label. Những giá trị đó tạo cardinality rất lớn và tăng chi phí lưu giữ time series. Hãy đặt chúng trong log/tracing có index và retention phù hợp.

Dashboard hữu ích có thể biểu diễn:

- Top error codes theo count và tốc độ tăng.
- Tỷ lệ `PAY-TIMEOUT` theo dependency và deployment.
- Lỗi không phân loại `SYS-UNEXPECTED` và số lần xuất hiện mã mới.
- Tỷ lệ failed operations **cuối cùng**, riêng biệt với số retry attempts.
- Link tới runbook và truy vấn logs lọc theo code/service/time, sau đó tìm requestId cụ thể.

Chú ý một operation có thể retry ba lần rồi thành công; nếu metric dùng “số dòng ERROR”, hệ thống sẽ báo ba lần failure dù kết quả cuối là thành công. Định nghĩa rõ mẫu số và sự kiện outcome.

## 14. Kiểm thử error code như API contract

| Tình huống | Kỳ vọng |
| --- | --- |
| Exception domain đã phân loại | Giữ mã và ý nghĩa đúng |
| `CompletionException` bọc domain exception | Không làm mất mã phía trong |
| Exception không biết | Mã fallback `SYS-UNEXPECTED`, response an toàn |
| Hai request cùng loại lỗi | Cùng errorCode, khác requestId |
| Retry hai lần và failure cuối | `attempt`, `outcome` rõ; không đếm operation nhiều lần |
| 404/400 thông thường | Không bắt buộc ghi ERROR/stack trace |
| HTTP Problem Details | `status` body và status HTTP khớp, `type`/`errorCode` ổn định |
| Mã code đổi message | Contract test xác nhận code không đổi |
| Security exception chứa secret | Không lộ ở public response hoặc sink không được phép |
| Async/thread pool | MDC được dọn đúng, requestId không rò |
| Logback/SLF4J structured output | JSON field `errorCode` có mặt thật, không chỉ trong mock |
| Metrics | Nhãn `error_code` là giá trị thuộc catalog hữu hạn |
| Deprecated code | Có version/alias/migration plan, không tái dùng nghĩa khác |

Test taxonomy: dùng enum/cấu hình catalog, kiểm tra không có code rỗng/trùng nhau; pattern tên được tuân thủ; mỗi code có owner/response mapping/runbook theo policy. Với public API, snapshot/contract test giúp phát hiện một refactor vô tình đổi code khiến client rẽ nhánh sai.

Test logging tại **appender/handler nhận event**, không chỉ mock `logger.error`. Với JUL, xem `LogRecord.getMessage()`, `getThrown()`, `getLevel()`; với SLF4J/Logback cần encoder thật để xác minh key–value được phát đúng. Trong async pipeline test propagation, buffering và shutdown.

## 15. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Code lấy từ exception message | Thay đổi theo người dùng/dependency; có thể lộ secret | Map sang catalog hữu hạn |
| Code bằng tên Java class | Refactor làm vỡ hợp đồng client | Mã nghiệp vụ độc lập implementation |
| Một mã `ERROR_UNKNOWN` cho mọi thứ | Không có tín hiệu điều tra rõ | Mã chuyên biệt cho lỗi thực sự cần action |
| Mỗi lần lỗi tạo mã UUID mới | Bùng nổ cardinality, không thể tổng hợp | UUID dành cho occurrence, code dành cho loại |
| Đồng nhất code với HTTP status | Nhiều lỗi có cùng 409/503 nhưng xử lý khác | Hai trường và mapper riêng |
| Đồng nhất code với log level | 404 bình thường thành ERROR vô ích | Chọn level theo impact/policy |
| Map mọi IllegalArgumentException thành 400 | Lỗi lập trình bị che thành lỗi client | Chỉ map typed domain exception |
| Retry mọi code có chữ TIMEOUT | Có thể lặp charge/update hoặc retry storm | Idempotency + budget + trạng thái side effect |
| Log exception ở mọi tầng rồi rethrow | Stack trace/alert nhân bản | Ownership ghi lỗi ở boundary |
| Copy Throwable message vào response | Lộ SQL, token, host, PII | Public-safe message + redaction |
| Dùng code làm idempotency key | Nhiều operation khác nhau bị gộp | Key theo operation |
| Đổi nghĩa code mà không version | Client/dashboard chạy sai | Version/deprecation/aliases |
| Bật SLF4J fluent và tưởng tự ra JSON | Field key–value có thể không được encoder in | Integration test backend/layout |

## 16. Checklist triển khai

1. Định nghĩa mục đích mã lỗi (client, support, observability, retry, runbook).
2. Tạo taxonomy có chủ sở hữu, mã ổn định, mô tả và chính sách tương thích.
3. Phân biệt errorCode với exception class, HTTP/gRPC status, log level, requestId và occurrenceId.
4. Phân loại ở domain/adapter; ánh xạ ở boundary, giữ cause nhưng không để lộ thông tin nhạy cảm.
5. Ghi structured fields với `event`, `errorCode`, `requestId`/`traceId`, `attempt`, `outcome` khi phù hợp.
6. Đặt một boundary chịu trách nhiệm log failure cuối cùng; log retry như sự kiện riêng.
7. Chọn retry policy theo operation và idempotency, không chỉ theo code.
8. Kiểm soát public response, dữ liệu log, RBAC/retention và nguy cơ user enumeration.
9. Kiểm thử contract, cause wrapper, fallback, formatter, metrics cardinality và async context.
10. Dùng code hữu hạn trong metrics; dùng requestId trong log/traces để truy vết occurrence.

**Ghi nhớ:** Error code là tên **loại lỗi** có ý nghĩa và ổn định. Exception class là chi tiết Java, HTTP status là kết quả giao thức, log level là mức độ chú ý, còn requestId/traceId/occurrenceId giúp truy tìm **lần xảy ra cụ thể**. Không trộn vai trò, không sinh mã từ text động và không dùng error code để thay thế idempotency hay bảo mật.

### Tài liệu tham khảo chính thức

- IETF — [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html), [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html).
- Java SE 17 — [Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html), [CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html), [java.util.logging.LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html).
- SLF4J — [Manual](https://www.slf4j.org/manual.html), [MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html).
- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html).
