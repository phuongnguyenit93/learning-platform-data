# Correlation ID và retry trong Java Logging

## 1. Vấn đề: một thao tác nhưng có nhiều lần thử

**Correlation ID** là mã dùng để liên kết những sự kiện log thuộc cùng một luồng xử lý hoặc cùng một thao tác logic. **Retry** là việc thử lại một thao tác sau thất bại hoặc tín hiệu tạm thời không thành công.

Hai cơ chế này thường xuất hiện cùng nhau trong dịch vụ Java gọi HTTP API, cơ sở dữ liệu, message broker hoặc một dịch vụ khác:

~~~text
Một yêu cầu thanh toán: correlation_id = corr-42
      |
      +-- Attempt 1: timeout
      |
      +-- Đợi theo retry policy
      |
      +-- Attempt 2: thành công
      |
      +-- Kết quả logic cuối: thành công
~~~

Nếu code tạo **correlation_id mới ở mỗi retry**, log sẽ trông như nhiều yêu cầu độc lập, khiến người vận hành khó nhận biết attempt 1 và attempt 2 thuộc cùng công việc. Ngược lại, nếu log chỉ có một correlation ID mà **không có số lần thử**, các event dễ bị xem là trùng nhau hoặc người đọc không biết lỗi nào đã phục hồi.

**Quy tắc trung tâm:** Với **cùng một thao tác logic**, thường giữ **correlation ID ổn định qua các lần retry**, đồng thời gắn **attempt number/attempt ID khác nhau cho từng lần thử**. Sau tất cả các attempt, ghi nhận **outcome cuối cùng** của thao tác.

Ví dụ log tốt:

~~~text
INFO  cid=corr-42 attempt=1 event=ATTEMPT_STARTED outcome=in_progress
WARN  cid=corr-42 attempt=1 event=ATTEMPT_FAILED reason=TIMEOUT outcome=retrying
INFO  cid=corr-42 attempt=2 event=ATTEMPT_STARTED outcome=in_progress
INFO  cid=corr-42 attempt=2 event=OPERATION_SUCCEEDED outcome=success
~~~

**Một attempt thất bại không nhất thiết là một thao tác thất bại.** Nếu attempt 2 thành công, kết quả cuối là success, không phải error. Khi retry đã cạn hoặc gặp lỗi không retry được, hãy phân biệt rõ bằng event cuối như OPERATION_FAILED.

## 2. Correlation ID dùng để trả lời câu hỏi gì?

Correlation ID giúp nối những sự kiện có quan hệ với nhau:

- Những lần gọi API nào thuộc cùng một lệnh tạo đơn?
- Những log nào thuộc cùng một message/job được xử lý lại?
- Lỗi timeout này có dẫn tới retry thành công hay không?
- Sau lần thử thứ mấy hệ thống hoàn thành?
- Các lớp Controller, Service, Client và background worker có đang nói về cùng một hoạt động không?
- Một thao tác có bị thực thi trùng vì retry hay message redelivery không?

Bản ghi có đủ context có thể gồm:

~~~json
{
  "timestamp": "2026-11-09T12:34:56.789Z",
  "level": "WARN",
  "service": "checkout",
  "logger_name": "com.example.payment.PaymentClient",
  "correlation_id": "corr-42",
  "attempt_id": "corr-42-a1",
  "retry_attempt": 1,
  "max_attempts": 3,
  "event_code": "PAYMENT_ATTEMPT_TIMEOUT",
  "reason_code": "PROVIDER_TIMEOUT",
  "outcome": "retrying",
  "message": "Payment attempt timed out; another attempt is planned"
}
~~~

Các field có tên rõ giúp truy vấn, nhóm theo correlation_id và phân biệt **attempt failure** với **terminal failure** mà không phải parse câu message.

**Correlation ID không phải dữ liệu bảo mật để xác thực người dùng.** Không dùng nó như credential hoặc bằng chứng một caller có quyền thao tác. Giá trị do client gửi cần kiểm tra và xử lý theo ranh giới tin cậy.

## 3. Phân biệt các ID thường gặp

Đừng dùng mọi loại ID thay thế nhau chỉ vì chúng đều là chuỗi:

| ID | Phạm vi thường gặp | Hành vi khi retry |
| --- | --- | --- |
| **correlation_id** | Một luồng nghiệp vụ/yêu cầu logic theo hợp đồng | Giữ ổn định nếu vẫn là cùng công việc |
| **request_id** | Một HTTP request hoặc một yêu cầu được hệ thống định nghĩa | Có thể giữ hoặc đổi tùy hợp đồng: một lần gọi HTTP vật lý có thể có request ID riêng |
| **operation_id** | Một thao tác nghiệp vụ | Thường giữ qua các lần thử của thao tác đó |
| **attempt_id** | Một lần thử vật lý | Phải phân biệt được từng attempt |
| **retry_attempt** | Thứ tự thử, ví dụ 1, 2, 3 | Tăng theo từng lần thử |
| **trace_id** | Một distributed trace | Có thể giữ qua retries thuộc cùng trace |
| **span_id** | Một span cụ thể trong trace | Span cho từng attempt thường có ID riêng |
| **idempotency_key** | Khóa để phía xử lý nhận diện các request lặp của cùng một ý định, nếu API hỗ trợ | Giữ ổn định cho cùng thao tác cần idempotent retry |
| **message_id** | Một message trong hệ thống queue | Có thể giữ qua redelivery của cùng message; tùy broker |
| **delivery_count** | Lần delivery được broker/consumer quan sát | Thay đổi qua redelivery |

**Correlation ID và idempotency key không giống nhau.** Correlation ID giúp **quan sát và liên kết log**; idempotency key giúp một hệ thống được thiết kế tương ứng **nhận ra nhiều lần gửi của cùng một lệnh** để chống tạo tác dụng phụ trùng.

**Correlation ID không tự chống trùng.** Hai POST request mang cùng correlation ID vẫn có thể tạo hai giao dịch nếu server không có cơ chế idempotency hoặc bảo đảm khác.

**Trace ID cũng không phải luôn bằng correlation ID.** Distributed tracing theo chuẩn như W3C Trace Context có quy định định dạng và cách truyền trace ID. Nếu đã có OpenTelemetry, hãy lấy trace/span ID từ context hợp lệ; không tự gán một chuỗi bất kỳ vào field trace_id rồi xem đó là trace thật.

## 4. Một thao tác logic, nhiều attempt

Mô hình khuyến nghị:

~~~text
logical_operation: createPayment
correlation_id: corr-42
operation_id: payment-op-42
idempotency_key: giá trị cố định cho cùng ý định (không nhất thiết ghi raw vào log)
    |
    +-- attempt=1 / attempt_id=a-1
    |      -> timeout
    |
    +-- attempt=2 / attempt_id=a-2
    |      -> HTTP 503
    |
    +-- attempt=3 / attempt_id=a-3
           -> thành công

Kết quả cuối: OPERATION_SUCCEEDED / outcome=success
~~~

**Giữ ổn định:** correlation_id, operation_id và idempotency key nếu các attempt đúng là cùng một ý định.  
**Thay đổi theo attempt:** retry_attempt, attempt_id, thời điểm bắt đầu, thời gian chờ, duration, HTTP status hoặc lý do thất bại.

Nếu ứng dụng có **một user action mới tạo một ý định mới** (ví dụ người dùng chủ động tạo thêm đơn hàng độc lập), không tái sử dụng idempotency key hoặc correlation scope của thao tác cũ một cách vô ý.

### Khi nào nên tạo correlation ID?

Lý tưởng là **tại đầu ranh giới của logical operation**, ví dụ HTTP filter, message consumer hoặc job scheduler. Sau đó truyền nó xuống các lớp và qua những lần retry.

Sai:

~~~java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    String correlationId = java.util.UUID.randomUUID().toString();
    callRemoteService(correlationId);
}
~~~

Đoạn này là ví dụ minh họa trong method có **maxAttempts** và **callRemoteService**. Nó tạo ID mới ở mỗi lần thử, khiến các attempt khó nối thành một thao tác.

Đúng hơn:

~~~java
String correlationId = java.util.UUID.randomUUID().toString();

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    callRemoteService(correlationId, attempt);
}
~~~

Đây cũng là snippet minh họa, không phải chương trình Java độc lập. Với hệ thống đã có correlation ID do caller/middleware cấp, **không nhất thiết tạo UUID mới**; hãy tuân thủ hợp đồng propagation và validation.

## 5. Số lần thử: quy ước rõ ràng để tránh nhầm

Nên ghi rõ **retry_attempt** hoặc **attempt_number** bắt đầu từ **1** cho lần gọi đầu tiên, nếu đó là quy ước của hệ thống.

Ví dụ:

| Field | Ý nghĩa |
| --- | --- |
| **retry_attempt=1** | Lần gọi vật lý đầu tiên |
| **retry_attempt=2** | Lần gọi vật lý thứ hai |
| **max_attempts=3** | Tổng số lần thử tối đa được cho phép, bao gồm lần đầu |
| **retry_count=1** | Số lần *đã thử lại* sau lần đầu (khi dùng quy ước này) |
| **attempt_id** | ID duy nhất trong phạm vi cần theo dõi từng lần gọi |
| **retry_delay_ms** | Thời gian định chờ trước attempt tiếp theo, nếu có |
| **duration_ms** | Thời gian thực của attempt/operation tương ứng |

**max_attempts khác max_retries.** Một cấu hình **max_retries=3** thường có nghĩa một lần gọi đầu cộng tối đa ba lần retry, tức **bốn attempts**; nhưng các thư viện có thể có tên và ngữ nghĩa khác. Cần đọc đúng contract và ghi tên field không mơ hồ.

Trong log nên ghi:
- **attempt=1/3**, hoặc retry_attempt=1 và max_attempts=3.
- Outcome là **retrying**, **success**, **failed**, **cancelled** hoặc **degraded** khi phù hợp.
- **reason_code** tách khỏi message.
- Nếu có timeout/retry delay, ghi đơn vị rõ như **timeout_ms**, **retry_delay_ms**.

Tránh ghi **retry=1** không nói đó là lần đầu, retry lần thứ nhất hay tổng số retry đã xảy ra.

## 6. Những sự kiện nào cần log?

Không nhất thiết log mọi bước ở INFO; hãy chọn event có giá trị điều tra và mức phù hợp.

| Event | Tình huống | Level tham khảo |
| --- | --- | --- |
| **ATTEMPT_STARTED** | Bắt đầu một lần thử | DEBUG hoặc INFO khi cần demo/giám sát chi tiết |
| **ATTEMPT_FAILED** | Một lần thử gặp lỗi *có thể* retry | DEBUG/WARN tùy mức độ và tần suất |
| **RETRY_SCHEDULED** | Đã quyết định thử lại sau delay | DEBUG/INFO hoặc WARN nếu gây suy giảm |
| **OPERATION_SUCCEEDED** | Hoàn thành logical operation | INFO nếu hữu ích |
| **OPERATION_RECOVERED** | Thành công sau retry/fallback | INFO/WARN tùy tín hiệu cần quan sát |
| **OPERATION_FAILED** | Hết retry hoặc gặp lỗi không retry được | ERROR/SEVERE |
| **RETRY_ABORTED** | Bị hủy hoặc vượt deadline/retry budget | Tùy outcome và tác động |

Ví dụ sau một timeout nhưng vẫn sẽ thử lại:

~~~json
{
  "correlation_id": "corr-42",
  "retry_attempt": 1,
  "max_attempts": 3,
  "event_code": "ATTEMPT_FAILED",
  "outcome": "retrying",
  "reason_code": "TIMEOUT"
}
~~~

Khi attempt 2 thành công:

~~~json
{
  "correlation_id": "corr-42",
  "retry_attempt": 2,
  "max_attempts": 3,
  "event_code": "OPERATION_SUCCEEDED",
  "outcome": "success"
}
~~~

**Không ghi OPERATION_FAILED sau attempt 1 nếu code vẫn đang retry cùng thao tác.** Điều đó khiến dashboard hoặc alert đếm một request thành vừa thất bại vừa thành công.

Một số hệ thống vẫn log từng ATTEMPT_FAILED ở mức ERROR theo nhu cầu kiểm toán; khi đó cần phân biệt event_code/outcome rõ và tránh dùng đếm ERROR đơn thuần làm tỷ lệ lỗi cuối.

## 7. Retry policy phải đi cùng ngữ nghĩa nghiệp vụ

Correlation ID giải quyết quan sát; **retry policy** quyết định có nên thử lại hay không. Không vì muốn log đẹp mà retry một thao tác không an toàn.

Các câu hỏi cần trả lời:

1. **Lỗi có tạm thời không?** Timeout, connection reset, một số 429/5xx có thể retry, nhưng phụ thuộc API và trạng thái thực.
2. **Thao tác có idempotent không?** GET thường dễ retry hơn POST tạo side effect; vẫn phải tuân thủ contract của endpoint.
3. **Phía server có cơ chế idempotency không?** Nếu một request timeout nhưng server đã xử lý, gửi lại mù quáng có thể tạo tác dụng phụ hai lần.
4. **Tổng deadline còn bao nhiêu?** Không retry vô hạn khi user đã hết thời gian chờ.
5. **Backoff thế nào?** Exponential backoff + jitter hoặc theo Retry-After khi hợp lệ.
6. **Retry budget giới hạn ra sao?** Tránh nhân tải lên dependency đang gặp sự cố.
7. **Cancellation/interruption được xử lý thế nào?** Không cố retry khi thao tác đã bị hủy.
8. **Ai chịu trách nhiệm retry?** Client, SDK, gateway, queue consumer hay một lớp orchestration?

### Không phải mọi lỗi đều nên retry

Một số ví dụ:
- Lỗi validation rõ ràng: thường cần sửa input, không retry như một lỗi transient.
- HTTP 401/403: thường là vấn đề xác thực/phân quyền; chỉ có thể retry nếu có cơ chế refresh token hoặc policy được xác định riêng.
- HTTP 429: thường cần tôn trọng rate limit, Retry-After nếu có, và budget.
- HTTP 502/503/504: có thể là transient, nhưng phải xét idempotency, deadline và trạng thái dependency.
- Read timeout: **không chứng minh server chưa thực thi**.
- Lỗi logic hoặc dữ liệu không hợp lệ: retry thường chỉ lặp lại thất bại.

**Không lấy status code một mình làm quyết định retry tuyệt đối.** Hợp đồng API và khả năng tạo side effect quan trọng hơn.

## 8. Timeout không có nghĩa server chưa xử lý

Đây là điểm đặc biệt quan trọng khi Correlation ID đi cùng retry.

~~~text
Client (cid=corr-42)              Server
       |                            |
       |------ POST payment ------->|
       |                            |  Thực thi và commit thành công
       |          phản hồi bị mất   |
       |<---- client timeout -------|
       |                            |
       |------ POST retry --------->|
       |                            |  Nếu không chống trùng:
       |                            |  có thể tạo lần thanh toán thứ hai
~~~

Trong tình huống này, client biết **không nhận được phản hồi đúng hạn**, chứ không biết chắc server có thực thi giao dịch hay không.

**Correlation ID chỉ giúp thấy hai lần gọi thuộc cùng thao tác. Nó không bảo đảm lần gọi thứ hai được xử lý an toàn.**

### Idempotency key khác correlation ID

**Idempotency key** được gửi theo hợp đồng với server để server nhận ra nhiều lần gửi của cùng một lệnh. Khi hệ thống server hỗ trợ đúng:
- Cùng key và cùng ý định có thể trả kết quả của lần xử lý trước.
- Thao tác tạo side effect tránh thực thi trùng trong phạm vi đảm bảo được tài liệu hóa.
- Phía server cần lưu/check kết quả, ràng buộc payload, xử lý tranh chấp đồng thời và TTL theo contract.

**Đừng giả định đặt header Idempotency-Key là đủ.** Nếu server không hiểu header hoặc không có bảo đảm deduplication, việc gửi key không làm POST tự idempotent.

### Có nên ghi idempotency key trong log?

Thường **không ghi nguyên key nếu nó có giá trị bảo mật, dự đoán được, chứa PII hoặc được dùng như bearer token**. Có thể ghi một **idempotency_ref** hoặc mã liên kết an toàn theo chính sách ứng dụng. Correlation ID cũng nên được kiểm soát độ dài và mức độ nhạy cảm.

### Cùng correlation ID có thể chứa nhiều thao tác

Một HTTP request có thể tạo đơn và sau đó khởi tạo thanh toán. Các thao tác đó có thể cùng correlation ID ở cấp request, nhưng **idempotency key của tạo đơn và thanh toán nên phân biệt** theo contract. Không sử dụng một key toàn cục cho mọi side effect chỉ vì chúng cùng correlation ID.

## 9. Exponential backoff, jitter và Retry-After

Retry lập tức theo vòng lặp có thể làm dependency đang quá tải càng khó phục hồi.

Một phương án phổ biến:
- Delay tăng theo hàm mũ: **baseDelay × 2^(attempt-1)**.
- Có mức trần **maxDelay**.
- Thêm **jitter** để nhiều client không cùng retry một lúc.
- Tôn trọng **Retry-After** hoặc tín hiệu rate-limit hợp lệ của server khi policy yêu cầu.
- Không vượt quá **tổng deadline** và **retry budget**.

Ví dụ minh họa, không phải công thức áp dụng cứng cho mọi dịch vụ:

~~~text
attempt 1 thất bại -> delay ngẫu nhiên trong khoảng 0..200 ms
attempt 2 thất bại -> delay ngẫu nhiên trong khoảng 0..400 ms
attempt 3 thất bại -> hết 3 attempts -> terminal failure
~~~

Khi log quyết định retry, các field hữu ích:
- retry_attempt, max_attempts
- retry_delay_ms
- next_attempt_at nếu cần, có timezone rõ
- deadline_remaining_ms
- reason_code
- rate_limit_status nếu phù hợp

**Backoff không tự bảo đảm an toàn nghiệp vụ.** Với lệnh không idempotent, cần giải quyết chống trùng và trạng thái giao dịch trước.

Không đặt một delay ngẫu nhiên vào expected stdout của bài demo nếu không cố định seed và điều kiện chạy; ví dụ Java 17 dưới đây **mô phỏng retry không ngủ** để đầu ra xác định.

## 10. Ví dụ Java 17 chạy độc lập: giữ Correlation ID qua retry

Ví dụ này minh họa:
- Cùng một **correlation_id** cho mọi attempt thuộc một logical operation.
- **attempt_id** và số lần thử thay đổi.
- Một **idempotency_ref** an toàn để quan sát; nó **không phải** cơ chế chống trùng của server.
- Lần thử 1 timeout, lần 2 thành công trong kịch bản đầu.
- Kịch bản thứ hai timeout cả ba lần và ghi **OPERATION_FAILED** một lần.
- Logger JUL có sẵn trong JDK 17, không cần dependency ngoài.
- Handler tùy biến in output ngắn, không timestamp động.
- Throwable được gắn vào LogRecord khi có lỗi.
- Không dùng ThreadLocal để tránh nhầm lẫn ngữ cảnh trong demo.

Tạo file **CorrelationRetryDemo.java**:

~~~java
import java.util.concurrent.TimeoutException;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class CorrelationRetryDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.checkout.PaymentClient");

    private record RetryContext(
            String correlationId,
            String idempotencyRef,
            int attempt,
            int maxAttempts) {

        String attemptId() {
            return correlationId + "-a" + attempt;
        }
    }

    private static final class CompactHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }

            Object[] parameters = record.getParameters();
            RetryContext ctx = (RetryContext) parameters[0];
            String outcome = (String) parameters[1];

            StringBuilder line = new StringBuilder()
                    .append(record.getLevel().getName())
                    .append(" | cid=").append(ctx.correlationId())
                    .append(" | attempt=")
                    .append(ctx.attempt()).append("/")
                    .append(ctx.maxAttempts())
                    .append(" | attempt_id=").append(ctx.attemptId())
                    .append(" | idem_ref=").append(ctx.idempotencyRef())
                    .append(" | event=").append(record.getMessage())
                    .append(" | outcome=").append(outcome);

            if (record.getThrown() != null) {
                line.append(" | error=")
                    .append(record.getThrown()
                            .getClass()
                            .getSimpleName());
            }

            System.out.println(line);
        }

        @Override
        public void flush() {
            System.out.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }

    private static void event(
            RetryContext context,
            Level level,
            String eventCode,
            String outcome,
            Throwable cause) {

        LogRecord record = new LogRecord(level, eventCode);
        record.setLoggerName(LOG.getName());
        record.setParameters(new Object[] {context, outcome});

        if (cause != null) {
            record.setThrown(cause);
        }

        LOG.log(record);
    }

    private static void simulateGateway(
            int attempt,
            int successOnAttempt) throws TimeoutException {

        if (attempt != successOnAttempt) {
            throw new TimeoutException("simulated timeout");
        }
    }

    private static void runScenario(
            String correlationId,
            String idempotencyRef,
            int successOnAttempt,
            int maxAttempts) {

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            RetryContext context = new RetryContext(
                    correlationId,
                    idempotencyRef,
                    attempt,
                    maxAttempts);

            event(context, Level.INFO, "ATTEMPT_STARTED",
                    "in_progress", null);

            try {
                simulateGateway(attempt, successOnAttempt);
                event(context, Level.INFO, "OPERATION_SUCCEEDED",
                        "success", null);
                return;

            } catch (TimeoutException error) {
                if (attempt == maxAttempts) {
                    event(context, Level.SEVERE, "OPERATION_FAILED",
                            "failed", error);
                    return;
                }

                event(context, Level.WARNING, "ATTEMPT_FAILED",
                        "retrying", error);
            }
        }
    }

    public static void main(String[] args) {
        Handler output = new CompactHandler();

        output.setLevel(Level.ALL);
        LOG.setLevel(Level.ALL);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(output);

        try {
            // Attempt 1 timeout, attempt 2 success.
            runScenario("corr-42", "safe-ref-42", 2, 3);

            // All attempts timeout.
            runScenario("corr-99", "safe-ref-99", -1, 3);
        } finally {
            LOG.removeHandler(output);
            output.close();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 CorrelationRetryDemo.java
java CorrelationRetryDemo
~~~

**Stdout chính xác của chương trình:**

~~~text
INFO | cid=corr-42 | attempt=1/3 | attempt_id=corr-42-a1 | idem_ref=safe-ref-42 | event=ATTEMPT_STARTED | outcome=in_progress
WARNING | cid=corr-42 | attempt=1/3 | attempt_id=corr-42-a1 | idem_ref=safe-ref-42 | event=ATTEMPT_FAILED | outcome=retrying | error=TimeoutException
INFO | cid=corr-42 | attempt=2/3 | attempt_id=corr-42-a2 | idem_ref=safe-ref-42 | event=ATTEMPT_STARTED | outcome=in_progress
INFO | cid=corr-42 | attempt=2/3 | attempt_id=corr-42-a2 | idem_ref=safe-ref-42 | event=OPERATION_SUCCEEDED | outcome=success
INFO | cid=corr-99 | attempt=1/3 | attempt_id=corr-99-a1 | idem_ref=safe-ref-99 | event=ATTEMPT_STARTED | outcome=in_progress
WARNING | cid=corr-99 | attempt=1/3 | attempt_id=corr-99-a1 | idem_ref=safe-ref-99 | event=ATTEMPT_FAILED | outcome=retrying | error=TimeoutException
INFO | cid=corr-99 | attempt=2/3 | attempt_id=corr-99-a2 | idem_ref=safe-ref-99 | event=ATTEMPT_STARTED | outcome=in_progress
WARNING | cid=corr-99 | attempt=2/3 | attempt_id=corr-99-a2 | idem_ref=safe-ref-99 | event=ATTEMPT_FAILED | outcome=retrying | error=TimeoutException
INFO | cid=corr-99 | attempt=3/3 | attempt_id=corr-99-a3 | idem_ref=safe-ref-99 | event=ATTEMPT_STARTED | outcome=in_progress
SEVERE | cid=corr-99 | attempt=3/3 | attempt_id=corr-99-a3 | idem_ref=safe-ref-99 | event=OPERATION_FAILED | outcome=failed | error=TimeoutException
~~~

### Giải thích cách chương trình hoạt động

1. **runScenario** nhận correlationId một lần, bên ngoài vòng for. Mọi attempt của cùng scenario dùng giá trị đó.
2. **RetryContext** là record immutable chứa những field cụ thể cho một lần thử.
3. **attemptId()** tạo chuỗi dễ xem từ correlation ID và số lần thử. Đây là **định danh demo**, không phải cơ chế sinh ID toàn cục an toàn cho mọi luồng đồng thời.
4. **idempotencyRef** là mã tham chiếu an toàn cho log. Ví dụ không thực hiện request thực và không triển khai server idempotency; đừng xem nó như bằng chứng đã chống trùng.
5. **simulateGateway** ném TimeoutException nếu attempt không phải lần được cấu hình thành công. Nó mô phỏng lỗi, không có mạng, không backoff thật và không có side effect.
6. **LogRecord.setParameters** gắn context với event theo một quy ước **riêng của demo**. JUL không tự định nghĩa schema correlation_id.
7. **record.setThrown(cause)** bảo toàn Throwable cho event lỗi. Handler chỉ in tên lớp exception để stdout ổn định; một Formatter production có thể xuất cause chain/stack trace.
8. **ATTEMPT_FAILED** có outcome=retrying, không bị hiểu là kết quả cuối.
9. Khi hết attempts, chỉ ghi **một** OPERATION_FAILED ở mức SEVERE. Với kịch bản thành công, OPERATION_SUCCEEDED xuất đúng một lần.
10. **LOG.setUseParentHandlers(false)** tránh JUL root Handler tạo dòng bổ sung, và custom Handler in stdout chứ không dùng ConsoleHandler mặc định thường ghi stderr.

### Vì sao đây chưa phải một retry client production?

Để dùng với HTTP thật, cần thêm:
- Chính sách phân loại lỗi retryable/non-retryable.
- Deadline, per-attempt timeout, backoff, jitter, retry budget.
- Cancellation/InterruptedException.
- Idempotency key theo contract server.
- Propagation context qua HTTP headers và tracing framework.
- Metrics và security controls.
- Xử lý status không xác định (timeout nhưng server có thể đã commit).

Ví dụ trên cố ý tách **cơ chế logging correlation** khỏi những chính sách mạng/phân tán vốn phụ thuộc ứng dụng.

## 11. Correlation ID trong SLF4J MDC

Với SLF4J/Logback, **MDC (Mapped Diagnostic Context)** cho phép thêm các key–value có phạm vi xử lý.

Một mẫu code minh họa, giả định có Logger **log**, biến **correlationId**, **maxAttempts** và method **sendPayment()**:

~~~java
import org.slf4j.MDC;

MDC.put("correlation_id", correlationId);
try {
    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        MDC.put("retry_attempt", Integer.toString(attempt));

        try {
            log.info("Starting payment attempt");
            sendPayment();
            log.info("Payment succeeded");
            break;
        } finally {
            MDC.remove("retry_attempt");
        }
    }
} finally {
    MDC.remove("correlation_id");
}
~~~

Đây **không phải class Java chạy độc lập** và chưa có logic quyết định retry khi lỗi; nó chỉ minh họa **vòng đời MDC**. Khi chuyển thành production, cần xử lý lỗi theo policy và giữ correlationId không đổi.

Ưu điểm:
- correlation_id tồn tại trong scope bao quanh cả vòng retry.
- retry_attempt chỉ tồn tại trong đúng lần thử.
- finally bảo đảm xóa key khi thoát scope theo đường điều khiển Java thông thường.
- Code nghiệp vụ không cần nối correlation ID thủ công vào mỗi message.

**Nhưng MDC.put một mình chưa bảo đảm có field trong log file.** Backend và layout/encoder phải được cấu hình để xuất key. Một pattern text của Logback có thể có:

~~~xml
<pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS,UTC} %-5level cid=%X{correlation_id} attempt=%X{retry_attempt} %logger - %msg%n</pattern>
~~~

Đây là **một phần** của cấu hình Logback, không phải file cấu hình đầy đủ. Nếu dùng JSON encoder, kiểm tra rằng correlation_id và retry_attempt được export thành field đúng tên/kiểu.

### Cẩn thận với scope lồng nhau

Nếu tầng trên đã đặt correlation_id và tầng dưới gọi:

~~~java
MDC.put("correlation_id", anotherId);
// ...
MDC.remove("correlation_id");
~~~

thì correlation ID gốc sẽ bị mất, vì **remove không tự khôi phục giá trị cũ**.

Trong scope có thể ghi đè, lưu giá trị trước:

~~~java
String previous = MDC.get("correlation_id");
MDC.put("correlation_id", currentId);
try {
    performOperation();
} finally {
    if (previous == null) {
        MDC.remove("correlation_id");
    } else {
        MDC.put("correlation_id", previous);
    }
}
~~~

Đây là snippet minh họa, cần method/biến đã tồn tại. Với nhiều key, có thể snapshot **MDC.getCopyOfContextMap()** và khôi phục **MDC.setContextMap(...)** theo ownership. Không gọi **MDC.clear()** vô tội vạ trong một helper vì có thể xóa trace_id, request_id và các field do caller quản lý.

## 12. Key-value event với SLF4J 2.x

**SLF4J 2.x** có fluent API cho phép đưa field gắn với **một event**:

~~~java
log.atWarn()
        .addKeyValue("event_code", "ATTEMPT_FAILED")
        .addKeyValue("retry_attempt", attempt)
        .addKeyValue("max_attempts", maxAttempts)
        .addKeyValue("reason_code", "PROVIDER_TIMEOUT")
        .addKeyValue("outcome", "retrying")
        .setCause(exception)
        .log("Payment attempt timed out");
~~~

Đây là đoạn code minh họa với Logger SLF4J 2.x, biến attempt, maxAttempts và exception trong scope. Khi MDC đã mang correlation_id, encoder có thể ghi cả correlation ID và những field riêng của event. **setCause(exception)** giữ Throwable; không chỉ in exception.getMessage() nếu cần stack trace.

**addKeyValue không tự chuyển tất cả log thành JSON.** Provider/back-end (Logback, Log4j 2 qua SLF4J provider phù hợp...) phải có encoder/layout được cấu hình thực sự serialize field.

Nên dùng event-specific field cho:
- event_code
- retry_attempt
- max_attempts
- reason_code
- retry_delay_ms
- outcome
- error_type

Còn correlation_id, trace_id và request_id có thể nằm trong scoped context nếu đúng vòng đời. Dù thiết kế thế nào, **sự kiện đã tạo** phải capture đúng giá trị, không lệ thuộc vào thời điểm async appender ghi xuống đĩa.

## 13. Truyền correlation khi dùng ExecutorService hoặc CompletableFuture

Retry có thể chạy trong **worker thread khác** với thread ban đầu. Trong SLF4J với backend MDC theo thread, **không được giả định MDC tự truyền qua ExecutorService**, thread pool hoặc CompletableFuture.

Mẫu capture → install → restore (snippet minh họa):

~~~java
Map<String, String> captured = MDC.getCopyOfContextMap();

Future<?> future = executor.submit(() -> {
    Map<String, String> previous =
            MDC.getCopyOfContextMap();

    try {
        if (captured == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }

        executeRetryOperation();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
});
~~~

Cần import **java.util.Map, java.util.concurrent.Future, org.slf4j.MDC**, có biến executor và method executeRetryOperation. Đoạn này không phải ví dụ độc lập.

Ý nghĩa:
- Capture context **trước khi submit**.
- Cài context trong worker đang chạy retry.
- Dọn/khôi phục context cũ của worker trong finally.
- Không làm mất các key thuộc công việc trước hoặc để lại key cho công việc sau.

Nếu scope retry hoàn thành ở thread nguồn nhưng task đã submit vẫn chạy, việc source thread xóa MDC không đồng nghĩa worker mất correlation. **Từng task cần snapshot context phù hợp** và không giữ tham chiếu mutable chia sẻ tùy tiện.

Trong reactive frameworks hoặc virtual-thread workflows, dùng cơ chế propagation được framework hỗ trợ và kiểm thử cancellation, thread hopping, context restore. Không mặc định ThreadLocal luôn biểu diễn đúng toàn bộ hành trình của request.

## 14. Propagation qua HTTP và microservices

Ví dụ request đi qua nhiều service:

~~~text
API Gateway
  | correlation_id=corr-42
  | trace_id=trace-X
  v
Order Service
  | attempt=1
  v
Payment Service --> TIMEOUT
  |
Order Service
  | attempt=2
  v
Payment Service --> SUCCESS
~~~

Ở đây các event có thể chia sẻ **correlation_id=corr-42**. Nhưng mỗi HTTP attempt cũng có thể có **request ID vật lý riêng** do gateway hoặc upstream tạo ra.

### Cần thiết kế hợp đồng header

Có thể quy định một header nội bộ như:

~~~text
X-Correlation-ID: corr-42
~~~

Tên header này là quy ước ứng dụng, **không phải chuẩn bắt buộc của Java**. Khi gửi retry:
- Giữ correlation ID ổn định nếu vẫn là cùng logical operation.
- Tạo attempt ID mới hoặc truyền attempt number nếu hợp đồng cho phép.
- Truyền trace context theo công cụ tracing đang dùng.
- Không mặc định tái sử dụng span ID của một attempt cũ.
- Chỉ truyền context qua các trust boundary được phép.

**W3C Trace Context** sử dụng các header như **traceparent** và **tracestate** cho tracing. Không tự thay một header này bằng correlation ID tùy ý; chúng có định dạng và ngữ nghĩa riêng.

### ID từ client có đáng tin không?

Một caller bên ngoài có thể tự gắn chuỗi rất dài, ký tự xuống dòng, dữ liệu nhạy cảm hoặc ID giả mạo. Trước khi đưa vào log/forward:
- Validate độ dài và bộ ký tự.
- Có cơ chế tạo ID an toàn khi thiếu hoặc không hợp lệ.
- Tránh log injection.
- Không coi ID là thông tin ủy quyền.
- Cân nhắc phân biệt external_correlation_id và internal_correlation_id.

**Không truyền nguyên toàn bộ MDC qua ranh giới dịch vụ** nếu nó chứa tenant metadata, secret hoặc context nội bộ không được phép rời hệ thống.

## 15. Retry trong message queue và job processing

Retry không chỉ xảy ra khi gọi HTTP. Một message queue có thể **redeliver** cùng một message sau khi consumer crash, timeout hoặc không xác nhận xử lý.

Ví dụ:

~~~text
Message M:
  message_id=msg-42
  correlation_id=corr-42
  operation_id=payment-op-42

Delivery 1 -> consumer timeout, chưa ack
Delivery 2 -> consumer xử lý lại
Delivery 3 -> thành công, ack
~~~

Mô hình log nên phân biệt:
- **correlation_id:** liên kết toàn bộ nghiệp vụ.
- **message_id:** định danh message theo broker/ứng dụng.
- **delivery_attempt** hoặc **delivery_count:** lần được consumer nhận.
- **consumer_instance:** instance xử lý nếu cần.
- **outcome:** retrying, processed, dead_lettered hoặc failed.
- **reason_code:** lỗi tạm thời/lỗi cuối.
- **idempotency key/dedupe ID:** cơ chế nghiệp vụ độc lập để tránh side effect trùng.

**Không mặc định delivery count của mọi broker bắt đầu từ một hoặc được duy trì giống nhau**. Ví dụ một số broker không có delivery count sẵn; khi đó có thể cần trường riêng trong payload/header hoặc chính sách redelivery.

### Dead-letter queue (DLQ)

Sau khi retry vượt giới hạn, message có thể được chuyển vào DLQ. Khi đó log cuối có thể là:

~~~json
{
  "correlation_id": "corr-42",
  "message_id": "msg-42",
  "event_code": "MESSAGE_DEAD_LETTERED",
  "outcome": "dead_lettered",
  "reason_code": "RETRIES_EXHAUSTED"
}
~~~

Không nên đánh đồng **message đã chuyển DLQ** với **giao dịch đã hoàn tất**. Có thể vẫn cần vận hành thủ công, replay, audit hoặc bù trừ theo workflow.

### Replay có phải là cùng logical operation?

Tùy hợp đồng. Nếu replay lại cùng một intent để hoàn tất yêu cầu cũ, correlation ID/operation ID có thể cần được giữ. Nếu người vận hành tạo **một thao tác mới** từ dữ liệu cũ, có thể dùng correlation ID mới và ghi **original_correlation_id** để liên kết lịch sử. Quy tắc này phải được tài liệu hóa, không áp dụng máy móc.

## 16. Nested retry: tránh nhân số lần gọi

Một gateway có retry, HTTP client SDK cũng retry, service gọi SDK lại retry thêm. Khi đó số lần gọi thực tế có thể lớn hơn tưởng tượng.

Ví dụ:
- Tầng Service thử tối đa 3 lần.
- Mỗi attempt của Service gọi SDK, SDK tự thử 3 lần.

Khi mọi tầng đều cạn retry, có thể tạo đến **9 lần gọi mạng** cho một thao tác ở tầng trên, nếu không có điều kiện dừng khác.

~~~text
service attempt 1 -> sdk attempts 1,2,3
service attempt 2 -> sdk attempts 1,2,3
service attempt 3 -> sdk attempts 1,2,3
~~~

Log cần biết **attempt ở tầng nào**:
- outer_attempt
- sdk_attempt
- total_attempt_count nếu được đo đúng
- correlation_id chung
- span ID theo tầng/thao tác
- retry_policy hoặc retry_layer nếu cần điều tra

**Không tái sử dụng một field attempt=1 cho nhiều tầng retry khác nhau** rồi kết luận số lần gọi thật từ nó.

Giải pháp thiết kế thường là:
- Chọn tầng chịu trách nhiệm retry chính.
- Tắt hoặc giới hạn retry ở tầng khác nếu policy cho phép.
- Dùng deadline và retry budget xuyên tầng.
- Quan sát retry rate, dependency load và error rate.
- Chỉ retry thao tác an toàn theo contract.

## 17. Log level và cách đếm lỗi: attempt khác operation

Một lỗi thường gặp là mọi attempt timeout đều ghi ERROR, sau đó operation thành công cũng ghi INFO. Dashboard đếm ERROR sẽ tưởng request thất bại dù đã phục hồi.

Nên phân biệt **hai loại chỉ số**:

**Attempt failure rate:** số attempt thất bại / tổng attempts.  
**Operation failure rate:** số logical operations cuối cùng thất bại / tổng logical operations.

Ví dụ 100 operations, trong đó 15 operations cần retry nhưng cuối cùng 98 thành công, 2 thất bại:
- Tỷ lệ operation failure là **2/100 = 2%**.
- Số attempt failure có thể lớn hơn 2, và phải dùng đúng mẫu số attempts để tính tỷ lệ tương ứng.

Không lấy count(log level=ERROR) làm mẫu số hoặc tử số của operation failure nếu logging policy ghi lỗi ở nhiều tầng hoặc sampling/drop log.

### Metric nên đo riêng

Một số metric có ích:
- retry_attempts_total theo service/dependency/reason_code có cardinality thấp.
- logical_operations_total theo outcome.
- retry_exhausted_total.
- retry_delay_seconds hoặc duration của attempt.
- dependency latency/error rate.
- circuit breaker status theo dependency.

Đừng đưa **correlation_id** hoặc **attempt_id** vào metric labels tùy tiện: mỗi request có thể tạo một giá trị mới, làm time-series cardinality tăng rất lớn.

Correlation ID thuộc log/tracing, còn metric thường dùng label có miền giá trị được kiểm soát.

## 18. Schema structured logging cho retry

Một schema đủ dùng có thể gồm:

| Field | Ví dụ | Kiểu | Ghi chú |
| --- | --- | --- | --- |
| timestamp | 2026-11-09T12:34:56.789Z | String time | UTC/offset rõ ràng |
| level | WARN | String/enum | Theo backend mapping |
| service | checkout | String | Resource |
| correlation_id | corr-42 | String | Ổn định qua cùng logical operation |
| operation | authorizePayment | String | Tên thao tác |
| attempt_id | corr-42-a1 | String | Riêng cho attempt |
| retry_attempt | 1 | Number | Lần thứ nhất, bắt đầu từ 1 |
| max_attempts | 3 | Number | Bao gồm lần đầu |
| event_code | ATTEMPT_FAILED | String/enum | Mã sự kiện ổn định |
| outcome | retrying | String/enum | Chưa phải terminal |
| reason_code | PROVIDER_TIMEOUT | String/enum | Phân loại lỗi |
| retry_delay_ms | 200 | Number | Nếu có delay |
| duration_ms | 130 | Number | Thời gian đo thực |
| error_type | TimeoutException | String | Loại exception |
| trace_id | ID theo trace | String | Từ tracing context |
| span_id | ID span hiện tại | String | Có thể đổi mỗi attempt |
| idempotency_ref | safe-ref-42 | String | Chỉ nếu an toàn cho log |

Không nên ghi tất cả mọi field trong mọi event. **ATTEMPT_STARTED** có thể không có error_type; **OPERATION_FAILED** cần outcome=failed và reason_code; **OPERATION_SUCCEEDED** không cần thêm cause chỉ để đủ cột.

Số đo cần có unit rõ. Field retry_delay_ms nên là Number, không ghi chuỗi "200ms" nếu muốn lọc số.

### Ví dụ hai event thuộc một correlation

~~~json
{"correlation_id":"corr-42","retry_attempt":1,"max_attempts":3,"event_code":"ATTEMPT_FAILED","reason_code":"PROVIDER_TIMEOUT","outcome":"retrying"}
{"correlation_id":"corr-42","retry_attempt":2,"max_attempts":3,"event_code":"OPERATION_SUCCEEDED","outcome":"success"}
~~~

Từ hai bản ghi, ta biết một thao tác được retry và cuối cùng thành công. Chúng không thể bị hiểu là hai payment độc lập nếu schema được sử dụng đúng.

## 19. Quản lý Correlation ID trong lifecycle Java

Một số vị trí có thể sở hữu correlation ID:
- HTTP filter / interceptor tại request boundary.
- Message consumer nhận metadata từ broker.
- Job scheduler hoặc batch processor.
- Workflow orchestrator.
- Tracing middleware.

Không nên:
- Tạo UUID mới bên trong từng retry.
- Đưa correlation ID vào **Logger name** động cho mỗi request.
- Dùng biến static mutable global chứa currentCorrelationId.
- Đặt MDC rồi quên clear/remove khi thread được tái sử dụng.
- Xóa luôn trace ID của caller bằng MDC.clear() trong một method nhỏ.

### Scope có giá trị đã tồn tại

Giả sử caller đã đặt correlation_id. Một helper khác đặt lại cùng key rồi chỉ gọi **MDC.remove("correlation_id")** trong finally sẽ làm mất ID của caller.

Mẫu save/restore từng key:

~~~java
String old = MDC.get("correlation_id");
MDC.put("correlation_id", newCorrelationId);

try {
    performOperation();
} finally {
    if (old == null) {
        MDC.remove("correlation_id");
    } else {
        MDC.put("correlation_id", old);
    }
}
~~~

Đây là snippet minh họa, không phải Java độc lập. Với scope nhiều key, có thể dùng snapshot **MDC.getCopyOfContextMap()** và restore **MDC.setContextMap(...)** theo quy tắc ownership.

**MDC.putCloseable** giúp tự remove key khi close, nhưng không tự khôi phục một giá trị cũ bị overwrite. Nếu operation lồng nhau có thể ghi đè correlation_id, phải dùng restore chủ động hoặc một abstraction scope đã được kiểm thử.

## 20. Bảo mật, độ tin cậy và cardinality

Correlation ID và context retry cần được coi là dữ liệu vận hành có thể truy vấn.

### Những rủi ro thường gặp

- Client gửi header correlation chứa newline, text dài, dữ liệu nhạy cảm hoặc một giá trị giả.
- ID có chứa user email, số điện thoại hoặc token.
- Log raw **idempotency_key** có thể lộ một mã mà phía server coi là nhạy cảm.
- Copy toàn bộ HTTP request/response vào exception log làm lộ Authorization header.
- Một hệ thống multitenant ghi sai tenant_id do MDC leak.
- Index tất cả ID ngẫu nhiên gây chi phí lớn.
- Log retry quá nhiều tạo sự cố dung lượng hoặc làm chậm luồng xử lý.

### Hướng xử lý

- Validate ID đến từ bên ngoài, giới hạn length và character set.
- Sinh ID nội bộ mới khi cần và ghi quan hệ với external ID theo hợp đồng.
- Không dùng correlation ID làm quyết định authorization.
- Chỉ log những field thực sự cần; redact secret.
- Dùng JSON encoder/serializer chuẩn, escape ký tự điều khiển.
- Dọn MDC tại request/task boundary, kể cả khi exception.
- Cân nhắc sampling các event chi tiết nhưng giữ terminal outcome cần thiết theo chính sách quan sát/audit.
- Đặt retention và quyền truy cập phù hợp.
- Không coi text log là audit storage bảo đảm bền vững.

### Correlation ID có nên toàn cục duy nhất?

Để tránh va chạm khi ghép log, thường nên sinh ID với đủ entropy trong phạm vi hệ thống, chẳng hạn UUID v4 hoặc cơ chế ID do tracing/request middleware quản lý. Nhưng **không có một định dạng bắt buộc cho mọi correlation ID**. Một hệ thống có thể nhận ID từ đối tác theo contract. Độ dài, format, phạm vi duy nhất và trust boundary phải được thống nhất.

## 21. Kiểm thử đúng những điều quan trọng

Một bộ test nên kiểm tra cả correctness của retry và observability:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Thành công ngay attempt 1 | Một correlation ID, attempt=1, OPERATION_SUCCEEDED |
| Timeout rồi thành công | Cùng correlation ID, attempt tăng, outcome cuối success |
| Hết retries | Một event OPERATION_FAILED cuối; không giả báo success |
| Lỗi không retryable | Không chạy thêm attempt, outcome failed rõ |
| Timeout sau server commit | Idempotency/tra cứu trạng thái ngăn side effect trùng theo contract |
| HTTP 429 với Retry-After | Delay/budget đúng policy |
| Cancellation/deadline | Không tiếp tục retry sau khi hết điều kiện |
| Concurrent requests | Hai request có correlation ID khác nhau không làm nhiễu MDC |
| Thread pool reuse | Request B không thừa hưởng correlation ID của A |
| CompletableFuture/executor | Correlation được propagate và restore đúng |
| Nested retry ở SDK | Phân biệt outer và inner attempt, đo số gọi mạng thật |
| Broker redelivery | Giữ correlation theo logical job, phân biệt delivery attempts |
| Collector JSON | Field attempt là Number và correlation_id không bị bỏ |
| Client ID độc hại | Validation và log escaping đúng; không rò secret |
| Exception chain | Throwable được giữ và ghi ở boundary hợp lý |

### Kiểm tra log bằng query

Một số câu hỏi truy vấn:
- Hiển thị **tất cả event của correlation_id=corr-42**, sắp theo event time và attempt.
- Đếm **OPERATION_FAILED** theo reason_code, không chỉ đếm ATTEMPT_FAILED.
- Tìm các operations có nhiều attempt nhưng outcome cuối success.
- Tìm một correlation ID có **các terminal outcome mâu thuẫn** (ví dụ vừa success vừa failed), cần điều tra bug/race.
- Tìm retry bị kéo dài gần deadline.
- Phát hiện các request không có correlation ID hoặc attempts có retry_attempt không tăng hợp lý.

Khi log nằm trên nhiều host, clock skew có thể làm timestamp không phản ánh thứ tự nhân quả tuyệt đối. Hãy kết hợp attempt number, span relationship và event code; không chỉ sắp xếp theo chuỗi timestamp.

## 22. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tạo correlation ID trong retry loop | Mỗi attempt trông như request khác | Tạo/nhận ID một lần ở logical operation |
| Dùng một attempt_id cho mọi lần thử | Không phân biệt được attempt | ID/number riêng cho từng attempt |
| Dùng correlation ID để chống trùng | Server vẫn có thể commit nhiều lần | Idempotency contract và dedupe thật |
| Tạo idempotency key mới ở mỗi retry | Server không nhận ra cùng ý định | Giữ key theo một logical operation |
| Tái sử dụng idempotency key cho thao tác độc lập | Có thể trả nhầm kết quả/dedupe sai | Phân biệt mỗi ý định nghiệp vụ |
| Ghi mọi ATTEMPT_FAILED là OPERATION_FAILED | Dashboard/alert phóng đại tỷ lệ lỗi | Event code và outcome riêng |
| Chỉ log lỗi attempt, không ghi terminal outcome | Khó biết request cuối thành công không | OPERATION_SUCCEEDED/FAILED rõ |
| Không thống nhất max_attempts và max_retries | Lệch số lần thử | Định nghĩa quy ước bắt đầu từ 1 |
| Dùng MDC nhưng không cleanup | Context leak trong thread pool | try/finally và restore |
| Không truyền context qua async boundary | Worker log thiếu ID | Capture/install/restore |
| Dùng trace_id tự chế như trace chuẩn | Tracing không liên kết | Lấy ID từ tracing context |
| Copy toàn bộ MDC qua trust boundary | Rò dữ liệu nội bộ | Allowlist và propagation policy |
| Không xử lý timeout ambiguous | Tạo side effect trùng | Idempotency và tra cứu trạng thái |
| Retry ngay liên tục | Tăng tải khi dependency lỗi | Backoff, jitter, budget, deadline |
| Retry đồng thời ở nhiều tầng | Nhân số lần gọi mạng | Đặt owner retry và budget |
| Dùng request_id làm metric label | Cardinality lớn | Giữ ID trong log/tracing |
| Đếm số dòng log là số request | Sai khi sampling/drop/log trùng | Dùng metrics và outcome |
| Chỉ kiểm tra stdout, không kiểm tra collector | Field có thể mất/đổi type | Integration test pipeline |

## 23. Checklist production

1. **Xác định logical operation:** Retry đang phục vụ đúng ý định nào?
2. **Correlation ID:** Sinh/nhận tại boundary, giữ ổn định qua attempts của cùng operation.
3. **Attempt:** Có attempt number/ID riêng, quy ước max_attempts rõ.
4. **Idempotency:** Nếu có side effect, bảo đảm backend hỗ trợ chống trùng theo contract.
5. **Outcome:** Phân biệt attempt failure, retrying, recovered, success, terminal failed.
6. **Retry policy:** Phân loại lỗi, deadline, timeout, budget, backoff, jitter, Retry-After.
7. **Layering:** Tránh các lớp retry chồng nhau không được kiểm soát.
8. **Logging:** event_code và reason_code ổn định, field number có unit.
9. **Throwable:** Giữ exception/cause; không ghi stack trace trùng ở nhiều tầng.
10. **MDC:** Context đúng scope, cleanup/restore trong finally.
11. **Async:** Propagate context qua executor, queue và callback.
12. **Tracing:** trace_id/span_id đúng chuẩn và không dùng thay idempotency key.
13. **HTTP/MQ:** Truyền metadata theo hợp đồng và validate trust boundary.
14. **Privacy:** Không ghi secret, token hoặc key nhạy cảm trong log.
15. **Collector:** Parse JSON đúng field/type và timestamp.
16. **Metric:** Tách retry attempt metrics khỏi operation outcome metrics.
17. **QA:** Test timeout sau commit, concurrent requests, thread reuse, exhaustion và cancellation.

## 24. Câu hỏi tự kiểm tra

**1. Correlation ID có nên đổi sau mỗi retry không?**  
Thông thường không, nếu các retry thuộc cùng logical operation. Giữ correlation ID, thay attempt number/ID.

**2. Attempt ID và correlation ID khác gì nhau?**  
Correlation ID nối toàn bộ công việc; attempt ID xác định một lần thử riêng biệt trong đó.

**3. Correlation ID có ngăn server tạo hai payment khi timeout không?**  
Không. Cần idempotency hoặc cơ chế chống trùng theo contract phía server.

**4. Vì sao timeout chưa chứng minh operation đã thất bại ở server?**  
Server có thể đã commit nhưng phản hồi bị mất hoặc đến muộn, khiến client chỉ biết mình chưa nhận phản hồi.

**5. Khi attempt 1 thất bại nhưng attempt 2 thành công, kết quả cuối là gì?**  
OPERATION_SUCCEEDED/outcome=success; attempt 1 có thể có event ATTEMPT_FAILED/outcome=retrying.

**6. max_attempts=3 có nghĩa ba lần retry sau lần đầu không?**  
Không. Theo quy ước trong bài, nó là ba lần thử **tổng cộng**, gồm lần gọi đầu.

**7. MDC có tự truyền qua ExecutorService không?**  
Không nên giả định. Phải capture/install/restore context trong worker hoặc dùng cơ chế propagation đã được kiểm thử.

**8. Có nên đưa correlation_id vào metric label không?**  
Thông thường không, vì cardinality rất cao. Dùng ID trong log/tracing và metrics với label ít giá trị phân biệt.

**9. Tại sao idempotency key phải giữ qua các lần retry của cùng một ý định?**  
Để một backend có hỗ trợ idempotency nhận ra chúng thuộc cùng thao tác và xử lý chống trùng đúng hợp đồng.

**10. Có thể dùng cùng correlation ID qua broker redelivery không?**  
Có thể, nếu redelivery thuộc cùng công việc logic; thêm delivery attempt/message ID để phân biệt từng lần nhận.

**11. Ghi WARNING cho mỗi attempt failure có bắt buộc không?**  
Không. Tùy logging policy và lưu lượng; event_code, reason_code và outcome mới là nền tảng để diễn giải đúng.

**12. Chỉ có correlation ID có đủ để phân tích retry không?**  
Chưa đủ. Nên có attempt number/ID, event_code, outcome, reason_code và terminal result để phân biệt từng lần thử.

## 25. Ghi nhớ

**Correlation ID giúp thấy nhiều lần retry là một công việc; attempt ID cho biết mỗi lần thử là sự kiện riêng; idempotency bảo vệ tác dụng phụ nếu hệ thống thực sự hỗ trợ; outcome cho biết kết quả cuối.**

Trong ứng dụng Java, hãy tạo hoặc tiếp nhận correlation ID tại ranh giới logical operation, giữ nó ổn định qua cùng retry workflow, tăng attempt number theo quy ước, ghi ATTEMPT_FAILED khác OPERATION_FAILED, truyền context qua HTTP/queue/async đúng cách và dọn MDC sau scope. Thử lại chỉ khi hợp đồng nghiệp vụ, deadline, retry budget và idempotency cho phép; **logging tốt không thể sửa một retry policy thiếu an toàn**, nhưng giúp phát hiện và giải thích các lỗi đó nhanh hơn.
