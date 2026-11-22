# Retry message trong Java Core Logging

## Mục tiêu học tập

Bài học thuộc nhóm **Logging trong ứng dụng message**, chủ đề **Retry message**. Trong hệ thống xử lý message bất đồng bộ, một message có thể được nhận nhiều lần do lỗi tạm thời, worker crash, timeout, consumer rebalance, việc chưa xác nhận ACK/offset hoặc một cơ chế retry có chủ đích. Logging ở đây không chỉ là in exception mỗi lần xử lý thất bại. Log cần giúp người vận hành trả lời: **message nào**, **đang ở lần thử thứ mấy**, **tại sao thử lại**, **khi nào thử tiếp**, **đã xử lý thành công hay chưa**, và **đã thật sự chuyển vào dead-letter queue (DLQ) hay chỉ mới yêu cầu chuyển**.

Sau bài này, bạn có thể:

- Phân biệt **delivery attempt**, **processing attempt**, **business operation** và **retry của việc gửi log**.
- Thiết kế các log event ổn định cho `received`, `processing`, `retry_planned`, `retry_scheduled`, `processed`, `acknowledged`, `retry_exhausted` và `dead_letter_confirmed`.
- Dùng `message_id`, `attempt`, `operation_id`, `correlation_id` và `trace_id` đúng ngữ nghĩa, tránh nhầm lẫn khi message được nhận lại.
- Quyết định mức log phù hợp để giữ tín hiệu lỗi nhưng tránh “log storm” khi retry nhiều lần.
- Hiểu cơ chế ACK/NACK/requeue của RabbitMQ, commit offset của Kafka và giới hạn của at-least-once delivery.
- Đánh giá backoff, jitter, retry limit, poison message, DLQ/parking queue, idempotency và transactional outbox.
- Chạy ví dụ Java 17 độc lập để quan sát log retry xác định, không nhầm một bản ghi “đã lên kế hoạch” với xác nhận từ broker.
- Kiểm thử các trường hợp crash, timeout, duplicate, DLQ thất bại và lỗi bảo mật trong log payload.

**Nguyên tắc trọng tâm:** Một log retry phải mô tả **trạng thái được chứng minh tại thời điểm ghi**. Nếu chưa được broker xác nhận đã đặt lịch retry, đừng ghi “retry đã lên lịch thành công”; nếu mới yêu cầu gửi DLQ, đừng ghi “đã vào DLQ”; nếu handler đã chạy xong nhưng offset chưa commit, đừng khẳng định message chắc chắn không được xử lý lại.

## 1. Retry message là gì?

Một message-driven application thường có producer phát message lên broker/topic/queue, sau đó consumer nhận và xử lý. Một message có thể lỗi vì:

1. **Lỗi tạm thời (transient):** downstream timeout, HTTP 503, database connection tạm mất, rate limit, broker/network ngắt quãng.
2. **Lỗi lâu dài (permanent):** schema không hợp lệ, thiếu field bắt buộc, một thao tác bị từ chối không thể hồi phục bằng việc thử lại, message phiên bản không được hỗ trợ.
3. **Lỗi chưa xác định (ambiguous):** consumer gọi hệ thống bên ngoài, timeout trước khi biết side effect đã hoàn tất hay chưa.
4. **Lỗi hạ tầng consumer/broker:** process crash, mất ACK, rebalance, chưa commit offset, network partition hoặc queue chuyển trạng thái.

Retry là **một cơ chế thử xử lý lại**, không phải bằng chứng chắc chắn message được xử lý đúng một lần. Khi at-least-once delivery, một message logic có thể đến consumer nhiều lần; log phải cho phép phân biệt **số lần thử xử lý** và **số lần nghiệp vụ thực sự áp dụng side effect**.

### Các thuật ngữ cần phân biệt

| Khái niệm | Ý nghĩa | Vấn đề logging nếu nhầm |
| --- | --- | --- |
| **Message ID** | Định danh một message logic theo giao ước ứng dụng; có thể không do broker tự cấp | Nếu tự sinh ID mới mỗi lần retry, không thể ghép các lần thử với nhau |
| **Delivery attempt** | Một lần broker hoặc cơ chế trung gian giao message đến consumer | Một processing attempt có thể khác số lần delivery nếu framework retry ngay trong process |
| **Processing attempt** | Một lần handler bắt đầu thực hiện nghiệp vụ | Đếm retry sai khi dùng số lần nhận từ broker như tổng số handler invocation |
| **Business operation ID** | Định danh hành động logic cần bảo vệ idempotency | Retry có thể tạo nhiều log nhưng chỉ được thực hiện side effect một lần |
| **Consumer instance** | JVM/pod/worker nhận message tại một thời điểm | Cần phân tích lỗi chỉ xảy ra trên một instance |
| **Correlation/trace ID** | Gắn chuỗi tác vụ phân tán | Không nhất thiết duy nhất cho từng event hoặc từng retry |
| **Broker acknowledgement / offset commit** | Đánh dấu tiến độ xử lý theo semantics của broker | Handler return không luôn đồng nghĩa message đã ACK/commit |
| **Retry scheduling** | Đặt message cho lần chạy tiếp theo, ngay hoặc có delay | “Planned” khác “confirmed” nếu publish tới retry queue/broker thất bại |
| **Dead-lettering** | Chuyển message không xử lý được sang kênh lỗi | “Requested DLQ” khác “confirmed routed/persisted at DLQ” |

**Ví dụ:** Một command `operation_id=pay-71` có `message_id=msg-71`. Consumer nhận một lần, retry handler tại chỗ ba lượt, sau đó crash trước khi ACK. Broker giao lại message cho instance khác. Có thể có **nhiều handler attempts**, **hai lượt broker delivery** và **chỉ một logical payment operation**. Chỉ dựa trên tổng số log `processing_started` không thể suy ra đã thu tiền bao nhiêu lần.

## 2. Vòng đời message và các mốc cần log

Một mô hình khái niệm:

```text
Producer publishes msg-71
          |
          v
      Broker / queue
          |
          v
    Consumer receives
          |
          +--> start processing, attempt=1
                    |
                    +--> SUCCESS ---> commit/ACK requested ---> ACK confirmed
                    |
                    +--> TRANSIENT FAILURE
                    |      |
                    |      +--> retry planned (backoff)
                    |                 |
                    |           schedule/publish retry
                    |                 |
                    |          confirmed? -> next attempt
                    |
                    +--> PERMANENT FAILURE
                    |      |
                    |      +--> route to DLQ / quarantine
                    |
                    +--> RETRIES EXHAUSTED
                           |
                           +--> route to DLQ / terminal policy
```

Các mốc logging nên rõ ràng:

| Mốc | Gợi ý event code | Level tham khảo | Điều thật sự đã biết |
| --- | --- | --- | --- |
| Nhận message | `message.received` | DEBUG hoặc INFO có sampling | Broker/client đã giao message vào consumer |
| Bắt đầu handler | `message.processing_started` | DEBUG | Consumer bắt đầu xử lý attempt |
| Lỗi tạm thời | `message.processing_failed` | WARN hoặc DEBUG theo policy | Handler gặp lỗi đã phân loại |
| Có quyết định thử tiếp | `message.retry_planned` | INFO/WARN tùy rủi ro | Policy đã chọn retry, chưa chắc đã được broker lên lịch |
| Broker xác nhận retry | `message.retry_scheduled` | INFO | Retry transport đã xác nhận theo semantics API |
| Xử lý thành công | `message.processed` | INFO | Handler/business đã thành công theo contract được định nghĩa |
| ACK/offset commit xác nhận | `message.acknowledged` / `message.offset_committed` | DEBUG hoặc INFO khi cần | Đã có xác nhận ở mốc broker tương ứng |
| Hết retry | `message.retry_exhausted` | ERROR/WARN tùy tác động | Max attempts đã dùng hết; không có lần thử tiếp theo theo policy |
| Đề nghị chuyển DLQ | `message.dlq_requested` | WARN/ERROR | Consumer/handler **yêu cầu** chuyển kênh, chưa chứng minh thành công |
| DLQ được xác nhận | `message.dlq_confirmed` | WARN/ERROR hoặc audit | Đích DLQ đã xác nhận theo contract và tuyến được kiểm tra |
| Bản ghi lỗi được replay | `message.replay_requested` / `message.replayed` | INFO/WARN | Replay phải gắn operator/ID và sinh một processing lifecycle mới |

Đây là **quy ước event code** minh họa, không phải API mặc định của Java, Kafka hay RabbitMQ. Tổ chức có thể chọn tên khác, nhưng nghĩa event cần cố định và được ghi vào schema/contract. Cách chọn level phụ thuộc mức độ ảnh hưởng; một transient timeout sẽ tự hồi phục có thể không cần in stack trace lớn ở mọi attempt.

### Chỗ dễ ghi log sai

- Gọi `logger.info("message processed successfully")` khi mới deserialise thành công, nhưng handler chưa làm xong.
- Ghi `retry_scheduled` trước khi broker thật sự chấp nhận message trong retry topic/queue.
- Ghi `dlq_confirmed` ngay sau khi gọi API gửi DLQ mà chưa nhận publish confirm/ack tương ứng.
- Ghi `acknowledged` trước khi commit offset thành công; nếu commit bị lỗi, message có thể được giao lại.
- Chỉ ghi `ERROR` cho attempt đầu; lần thứ năm mới thành công nhưng không có log tổng kết khiến người vận hành hiểu nhầm message thất bại.
- Chỉ ghi lỗi cuối mà không giữ `attempt_count`/`first_attempt_at`/`last_error_code`, khó biết đã retry trong bao lâu.

## 3. Lược đồ log tối thiểu khi retry

Một log JSON hữu ích có thể có:

```json
{
  "timestamp": "2026-11-10T02:00:03.125Z",
  "level": "WARN",
  "service": "payment-consumer",
  "environment": "staging",
  "event": "message.retry_planned",
  "message_id": "msg-71",
  "operation_id": "pay-71",
  "correlation_id": "corr-22",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "destination": "payments.commands",
  "partition": 2,
  "offset": 147,
  "consumer_group": "payment-workers",
  "attempt": 2,
  "max_attempts": 5,
  "next_attempt": 3,
  "retry_delay_ms": 2000,
  "error_code": "DOWNSTREAM_TIMEOUT",
  "exception_type": "java.net.http.HttpTimeoutException",
  "outcome": "RETRY_PLANNED"
}
```

**Đây là JSON minh họa**, không phải stdout mặc định của SLF4J/Logback và không ngụ ý một broker bất kỳ luôn có các trường `partition`/`offset`. Những field phù hợp sẽ phụ thuộc giao thức.

Các điểm cần quy định:

1. **`timestamp`:** thời điểm event log được tạo tại điểm ra quyết định; nếu collector nhận trễ, giữ thêm `observed_timestamp`/ingested time riêng.
2. **`message_id`:** ID logic ổn định qua retry; nếu producer không cung cấp, cân nhắc bổ sung envelope ID trong schema hoặc idempotency key có kiểm soát.
3. **`operation_id`:** ID tác vụ nghiệp vụ cần chống trùng side effect. Một operation có thể có nhiều message; quan hệ phải rõ.
4. **`attempt`:** số đếm bắt đầu từ 1 cho lần xử lý đầu (một **quy ước**, không mặc định mọi framework). Phân biệt “số retry đã làm” = `attempt - 1` nếu định nghĩa ban đầu là 1.
5. **`max_attempts`:** tổng số lần thực hiện handler cho phép. Nếu policy nói “max 3 retries” thì thông thường có 1 initial + 3 retries = 4 attempts; tránh đổi lẫn hai khái niệm.
6. **`error_code`:** mã lỗi ổn định ít cardinality hơn chuỗi message exception. Có thể thêm exception type và stack trace ở ngữ cảnh cần thiết, không đưa raw payload vào.
7. **`retry_delay_ms` và `next_attempt_at`:** dùng khi có kế hoạch delay. Nếu lập lịch chưa được xác nhận, ghi `retry_planned` và chỉ đổi event thành `retry_scheduled` sau xác nhận thật.
8. **`destination`/`queue`/`topic`:** đường vận chuyển hữu ích khi gỡ lỗi, nhưng trường `partition`/`offset` chỉ dùng cho broker có semantics tương ứng.
9. **`consumer_group`/`consumer_id`:** giúp xác định rebalance hoặc instance lỗi. Đừng dùng ID với cardinality lớn làm nhãn metric trực tiếp.
10. **`delivery_id` hoặc `delivery_tag`:** thông tin về một lượt giao, có thể chỉ có ý nghĩa trong connection/channel hiện tại; không dùng để thay stable message ID.

### Không log những gì?

- Toàn bộ body message theo mặc định; đặc biệt dữ liệu thanh toán, mật khẩu, token, cookie, credential, thông tin cá nhân hoặc tài liệu bí mật.
- Headers như `Authorization`, `Cookie`, access key, chữ ký hoặc token session.
- Full URL chứa token ở query, connection string có mật khẩu, broker credentials.
- Exception message lấy trực tiếp từ hệ thống bên ngoài mà chưa qua redaction; một số exception chứa URL hoặc dữ liệu người dùng.
- Payload bị lỗi deserialization một cách tự động chỉ để biết “tại sao invalid”; thay bằng schema version, field path an toàn, message size, error code và ID.

Lưu ý `trace_id` không phải mã xác thực. Tuy nhiên, nó vẫn có thể là metadata nhạy cảm theo chính sách. Đối với sự kiện bắt buộc audit, quyền xem log và retention cần chính sách riêng. Chỉ bật logging chi tiết payload trong thử nghiệm an toàn và có thời hạn, không mặc định ở production.

## 4. Chọn mức log để không tạo log storm

Giả sử một lỗi HTTP 503 gây retry 10 lần cho 100.000 message; nếu mỗi attempt in toàn bộ exception stack trace ở ERROR, hệ thống có thể tạo hàng triệu dòng, làm nghẽn collector và che mất lỗi thật.

Một chính sách tham khảo:

| Sự kiện | Level gợi ý | Điều kiện/ghi chú |
| --- | --- | --- |
| Message received/start processing | DEBUG | Chỉ bật chọn lọc; metrics đếm toàn bộ message |
| Retryable failure dự kiến và còn retry | WARN hoặc DEBUG | Ghi error code, attempt, next delay; stack trace có chọn lọc |
| Retry scheduled/publish confirmed | INFO hoặc DEBUG | Chỉ kết luận scheduled khi cơ chế thực sự xác nhận |
| Success ở attempt đầu | INFO được sampling hoặc DEBUG | Giữ throughput/success count ở metrics |
| Success sau retry | INFO | Ghi `attempts_used`, `elapsed_ms`, last error code an toàn |
| Permanent failure | ERROR hoặc WARN | Phân biệt hành vi invalid input kỳ vọng với sự cố hệ thống |
| Retries exhausted | ERROR | Ghi tổng số lần thử, destination, policy, hậu quả và DLQ decision |
| DLQ publish failed | ERROR | Một lỗi quan trọng mới về đường cứu hộ, cần alert riêng |
| DLQ confirmed | WARN/ERROR theo chính sách | Chỉ rõ đã lưu theo contract nào |
| Duplicate/idempotency skip | INFO/DEBUG | Không coi là handler success mới hoặc business side effect mới |

**Đây không phải quy tắc cứng cho mọi hệ thống.** Ví dụ một message invalid do client gửi sai schema thường xuyên có thể là WARN và metric; một lệnh thanh toán không xử lý được có thể cần ERROR và alert. Quan trọng là event code và outcome rõ, không phải cứ retry thì phải ERROR ở mọi bước.

### Chiến lược giảm trùng log exception

- Giữ một log có context đủ ở ranh giới xử lý message; không log rồi `throw` lại cùng exception ở mọi lớp service/repository.
- Nếu retry nhiều lần vì cùng error code, log event ngắn ở các attempt trung gian; log chi tiết có kiểm soát ở **first failure** và/hoặc **exhausted**.
- Thay hàng nghìn dòng lặp bằng metric `retry_attempts_total`, `retry_exhausted_total` và summary theo cửa sổ thời gian, không làm mất khả năng điều tra theo message ID khi cần.
- Sampling cho transient log có thể chấp nhận, nhưng không sampling tùy tiện log audit, security event hoặc critical outcome bắt buộc.
- Đừng tính serialized payload hay stack trace rất đắt trước khi kiểm tra enabled level, vì Java đánh giá argument trước khi gọi logger.

## 5. Classify lỗi trước khi quyết định retry

Retry mọi exception là một anti-pattern:

| Loại lỗi | Ví dụ | Hành vi thường phù hợp | Nội dung log |
| --- | --- | --- | --- |
| **Transient** | Downstream 503, network timeout, broker tạm unavailable | Backoff có giới hạn, retry an toàn | `error_code`, attempt, next delay, latency |
| **Rate-limited** | HTTP 429 / quota | Tôn trọng retry-after nếu được cung cấp và phù hợp, thêm jitter | Reason/limit an toàn, retry plan |
| **Permanent/schema** | Payload thiếu trường bắt buộc, schema version không hỗ trợ | Không retry cùng dữ liệu vô hạn; DLQ/quarantine hoặc reject theo policy | Schema version, violation code, message ID |
| **Business rejection** | Quyền truy cập bị từ chối, business rule không thỏa | Không tự retry như transient | Outcome rejected/denied, safe reason |
| **Ambiguous side effect** | Timeout sau khi remote API có thể đã xử lý | Reconcile/idempotent retry; không kết luận “chưa xử lý” | Operation ID, timeout, `outcome=UNKNOWN` |
| **Consumer bug** | NullPointerException do code | Có thể cần giới hạn, DLQ và alert; retry vô hạn không tự sửa bug | Exception type, app version, attempt/exhaustion |
| **Resource pressure** | Disk full, OOM risk, connection pool cạn | Bảo vệ hạ tầng, giảm tải, circuit breaker hoặc tạm dừng tiêu thụ | Error category, queue lag, health indicators |

Classification phải nằm ở tầng nghiệp vụ/adapter có đủ context. Chỉ phân loại theo chuỗi exception message là mong manh. Một `TimeoutException` không bảo đảm side effect từ remote **chưa** xảy ra. Nếu remote operation cần không trùng, sử dụng idempotency key/reconciliation theo contract tương ứng.

**Poison message** là message liên tục gây thất bại nếu retry không thay đổi được đầu vào hoặc điều kiện cần thiết. Nó có thể chặn partition/queue, làm tăng retry storm và phát sinh log nhiễu. Phải có giới hạn attempts, DLQ/parking policy, thời gian giữ và cơ chế xử lý có giám sát.

## 6. Chính sách retry: backoff, jitter và giới hạn

Một chiến lược thường dùng là **exponential backoff**:

\[d_n = \min(d_{\max}, d_{\text{base}} \times 2^{n-1})\]

Ở đây `n` là số thứ tự **lần retry sắp được lên lịch**, bắt đầu từ 1 (không phải số thứ tự attempt hiện tại của mọi framework). Ví dụ base 1 giây, cap 30 giây:

| Retry number | Delay chưa jitter |
| ---: | ---: |
| 1 | 1 giây |
| 2 | 2 giây |
| 3 | 4 giây |
| 4 | 8 giây |
| 5 | 16 giây |
| 6 trở đi | tối đa 30 giây theo cap |

**Jitter** là độ ngẫu nhiên có kiểm soát được thêm vào lịch retry để tránh hàng nghìn consumer đồng loạt đánh vào downstream khi nó vừa phục hồi. Không tự suy ra công thức jitter của thư viện; các chiến lược *full jitter*, *equal jitter*, *decorrelated jitter* có phân bố khác nhau. Với rate limit từ downstream, tôn trọng `Retry-After` nếu giao thức và chính sách cho phép.

Cần công bố:

- `max_attempts` là tổng số lần gọi handler hay chỉ số retry?
- Retry ngay tại process hay gửi tới delayed queue/topic?
- Retry delay có tồn tại qua consumer restart không?
- Những lỗi nào retry được, lỗi nào phải đưa DLQ ngay?
- Có retry theo priority/tenant hay giới hạn concurrency không?
- Khi retry service thất bại, original message được ACK/commit khi nào?
- Có giới hạn tổng thời gian xử lý, TTL và circuit breaker không?

**Cảnh báo quan trọng:** `Thread.sleep(...)` ngay trong message listener có thể chiếm consumer thread, làm giảm concurrency và ảnh hưởng broker heartbeat/polling hoặc partition ordering. Với delay dài, nên cân nhắc cơ chế retry của framework, delayed queue/topic hoặc scheduler bền vững. Cơ chế cụ thể tùy RabbitMQ, Kafka và thư viện.

## 7. Java 17 chạy độc lập: mô phỏng log retry minh bạch

Ví dụ dùng **JDK 17+**, không cần broker, SLF4J hay thư viện ngoài. Nó mô phỏng ba message:

1. `msg-101` gặp lỗi tạm thời trong hai attempts, xử lý thành công ở attempt 3.
2. `msg-202` có lỗi schema permanent, **đề nghị** đưa DLQ ngay ở attempt 1.
3. `msg-303` luôn gặp timeout, hết tối đa 3 attempts rồi **đề nghị** đưa DLQ.

Để không tạo kết luận sai, chương trình dùng event `message.retry_planned` (chỉ là quyết định sẽ retry) và `message.dlq_requested` (chỉ là đề nghị chuyển), **không** in `retry_scheduled` hoặc `dlq_confirmed` vì chương trình không kết nối broker. Delay là **giá trị kế hoạch**, chương trình cố ý không `sleep`, không có queue hay durable ACK. `Clock.fixed(...)` giúp timestamp/đầu ra xác định.

Tạo file **`RetryMessageLoggingDemo.java`**:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

public class RetryMessageLoggingDemo {
    record Message(String id, String operationId) {
    }

    static class RetryableFailure extends Exception {
        private final String code;

        RetryableFailure(String code) {
            super(code);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    static class PermanentFailure extends Exception {
        private final String code;

        PermanentFailure(String code) {
            super(code);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    static void handle(Message message, int attempt)
            throws RetryableFailure, PermanentFailure {
        if ("msg-101".equals(message.id()) && attempt < 3) {
            throw new RetryableFailure("DOWNSTREAM_TIMEOUT");
        }
        if ("msg-202".equals(message.id())) {
            throw new PermanentFailure("SCHEMA_INVALID");
        }
        if ("msg-303".equals(message.id())) {
            throw new RetryableFailure("DOWNSTREAM_TIMEOUT");
        }
    }

    static void log(Clock clock, String event, Message message,
                    int attempt, String details) {
        System.out.println("at=" + Instant.now(clock)
                + " event=" + event
                + " message_id=" + message.id()
                + " operation_id=" + message.operationId()
                + " attempt=" + attempt
                + " " + details);
    }

    static void consume(Message message, int maxAttempts, Clock clock) {
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                handle(message, attempt);
                log(clock, "message.processed", message, attempt,
                        "outcome=SUCCESS attempts_used=" + attempt);
                return;
            } catch (PermanentFailure error) {
                log(clock, "message.dlq_requested", message, attempt,
                        "reason=" + error.code()
                        + " outcome=PERMANENT_FAILURE");
                return;
            } catch (RetryableFailure error) {
                if (attempt < maxAttempts) {
                    long delayMs = 1000L << (attempt - 1);
                    log(clock, "message.retry_planned", message, attempt,
                            "next_attempt=" + (attempt + 1)
                            + " delay_ms=" + delayMs
                            + " error_code=" + error.code());
                } else {
                    log(clock, "message.retry_exhausted", message,
                            attempt, "error_code=" + error.code());
                    log(clock, "message.dlq_requested", message,
                            attempt, "reason=RETRIES_EXHAUSTED");
                }
            }
        }
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-10T02:00:00Z"),
                ZoneOffset.UTC);

        consume(new Message("msg-101", "op-101"), 3, clock);
        consume(new Message("msg-202", "op-202"), 3, clock);
        consume(new Message("msg-303", "op-303"), 3, clock);
    }
}
```

Biên dịch và chạy:

```bash
javac RetryMessageLoggingDemo.java
java RetryMessageLoggingDemo
```

**stdout chính xác:**

```text
at=2026-11-10T02:00:00Z event=message.retry_planned message_id=msg-101 operation_id=op-101 attempt=1 next_attempt=2 delay_ms=1000 error_code=DOWNSTREAM_TIMEOUT
at=2026-11-10T02:00:00Z event=message.retry_planned message_id=msg-101 operation_id=op-101 attempt=2 next_attempt=3 delay_ms=2000 error_code=DOWNSTREAM_TIMEOUT
at=2026-11-10T02:00:00Z event=message.processed message_id=msg-101 operation_id=op-101 attempt=3 outcome=SUCCESS attempts_used=3
at=2026-11-10T02:00:00Z event=message.dlq_requested message_id=msg-202 operation_id=op-202 attempt=1 reason=SCHEMA_INVALID outcome=PERMANENT_FAILURE
at=2026-11-10T02:00:00Z event=message.retry_planned message_id=msg-303 operation_id=op-303 attempt=1 next_attempt=2 delay_ms=1000 error_code=DOWNSTREAM_TIMEOUT
at=2026-11-10T02:00:00Z event=message.retry_planned message_id=msg-303 operation_id=op-303 attempt=2 next_attempt=3 delay_ms=2000 error_code=DOWNSTREAM_TIMEOUT
at=2026-11-10T02:00:00Z event=message.retry_exhausted message_id=msg-303 operation_id=op-303 attempt=3 error_code=DOWNSTREAM_TIMEOUT
at=2026-11-10T02:00:00Z event=message.dlq_requested message_id=msg-303 operation_id=op-303 attempt=3 reason=RETRIES_EXHAUSTED
```

### Giải thích từng bước

1. `Message` dùng Java record (JDK 17 hỗ trợ); `id` là ID message logic, `operationId` là ID thao tác nghiệp vụ. Chúng được giữ nguyên qua các lần thử.
2. `RetryableFailure` và `PermanentFailure` thể hiện phân loại lỗi bằng type riêng, thay vì phân tích chuỗi message exception.
3. `maxAttempts=3` gồm **một lần đầu + tối đa hai lần xử lý lại**. Sau lỗi ở attempt 3 không còn next attempt.
4. Delay `1000` và `2000` ms là **kế hoạch** exponential backoff. Không có `Thread.sleep` và không hề gửi message sang broker, vì vậy các timestamps đều giống nhau theo `Clock.fixed`.
5. `msg-101` thành công ở attempt 3. `message.processed` chỉ có nghĩa hàm mô phỏng xử lý đã trả về thành công; nó **không** chứng minh đã ACK/commit offset hoặc đã ghi tác dụng phụ bền vững.
6. `msg-202` gặp permanent error nên không dùng hết retry budget; phát `message.dlq_requested` ngay.
7. `msg-303` thử đúng ba lần, phát `message.retry_exhausted` và `message.dlq_requested`. Việc thật sự đưa message tới DLQ cần publisher/transport có xác nhận; ví dụ không làm điều đó.
8. Không log payload, token hay exception message tùy ý. Các ID và error code đều là dữ liệu giả an toàn.

### Nâng cấp khi tích hợp broker thật

Trong hệ thống thực tế, thay vòng lặp trong `consume` bằng:

- Adapter broker nhận message, mang theo ID/correlation/attempt đáng tin.
- Handler nghiệp vụ có idempotency và contract rõ về success/failure.
- Retry policy có timer/delayed queue/topic hoặc retry framework bền vững.
- Publisher/consumer ACK để biết retry scheduling, DLQ và offset commit có thành công không.
- Logging tại **ranh giới xác nhận** đúng như `retry_planned` vs `retry_scheduled`, `dlq_requested` vs `dlq_confirmed`.

Ví dụ là chương trình minh họa semantics logging, không phải mã RabbitMQ/Kafka production. Không dùng nó làm consumer thật vì nó không có retry delay, broker acknowledgement, durable storage, thread-safety đa consumer hay phục hồi khi process crash.

## 8. SLF4J/Logback: logging với message context

Trong ứng dụng dùng SLF4J, parameterized logging giúp giữ thông tin có cấu trúc hơn việc nối chuỗi liên tục:

```java
// Trích đoạn tích hợp SLF4J: giả sử logger và metadata
// đã được khai báo, kiểm tra dữ liệu được phép log.
logger.warn(
    "event=message.retry_planned message_id={} attempt={} next_attempt={} " +
    "delay_ms={} error_code={}",
    messageId, attempt, nextAttempt, delayMs, errorCode);
```

Đây là **trích đoạn**, cần dependency SLF4J và các biến được khai báo. Không phải chương trình Java độc lập. Dùng placeholder để giảm ghép chuỗi sớm, nhưng nếu xây các đối số đắt tiền trước lời gọi, Java vẫn đánh giá chúng. Với volume lớn, giới hạn verbosity và đo allocation.

### MDC và rò context giữa các message

Một thread pool consumer có thể xử lý lần lượt message A rồi B trên **cùng thread**. Nếu MDC không được clear, log của B có thể mang `message_id`/`trace_id` của A, gây nhầm điều tra hoặc rò dữ liệu giữa tenant.

Ví dụ scoped MDC, **trích đoạn SLF4J**:

```java
try (org.slf4j.MDC.MDCCloseable messageScope =
             org.slf4j.MDC.putCloseable("message_id", messageId)) {
    // Gọi handler, ghi log trong phạm vi message hiện tại.
    processMessage();
}
```

Cần xác định `processMessage()`, `messageId` và backend MDC tương thích. Khi scope kết thúc, key này được xóa khỏi MDC bởi `MDCCloseable`; nếu code có context trước đó cho cùng key hoặc quản lý nhiều key, nên có chính sách **lưu và khôi phục context gốc** hoặc scope thống nhất, không mù quáng xóa context của tác vụ bao quanh. Với `CompletableFuture`, executor hoặc async worker, MDC/trace context **không tự động lan truyền ở mọi cấu hình**; phải dùng instrumentation/propagation phù hợp và test để tránh mất context hoặc dính nhầm request.

**Không mặc định tin headers mang từ producer.** Một client không tin cậy có thể tự khai `attempt=999` hoặc `tenant_id=admin`. Các trường điều khiển retry/authorization phải được validate và quản lý trong metadata của hệ thống tin cậy. Từ logging có thể phân biệt `reported_attempt` và `internal_attempt` khi cần điều tra.

## 9. RabbitMQ: ACK/NACK, requeue và DLQ

RabbitMQ tiêu thụ message qua broker delivery tới consumer. Trong mô hình manual acknowledgement:

- **ACK**: consumer xác nhận delivery đã xử lý theo contract; broker có thể loại delivery khỏi trạng thái unacked. Nó không tự chứng minh một external business side effect đã commit.
- **NACK/reject với requeue=true**: yêu cầu broker đặt message trở lại để giao tiếp theo semantics queue. Nếu lỗi còn đó, message có thể bị giao lại liên tục, tạo **hot retry loop** và log storm.
- **NACK/reject với requeue=false**: broker có thể dead-letter message nếu queue có dead-letter exchange/routing được cấu hình, hoặc loại bỏ theo policy. **Không tự suy ra luôn có DLQ**.
- **DLX/DLQ**: tùy loại queue, chính sách dead-lettering và cấu hình, message có thể đi tới queue xử lý lỗi; cần quan sát xác nhận/tình trạng thực tế.

**Delivery tag** gắn với channel của RabbitMQ, không phải stable ID của message trên toàn hệ thống. Không dùng delivery tag làm idempotency key. Trường `redelivered` có thể cho biết delivery từng được redeliver theo cách broker biết, nhưng không đủ để đếm chính xác mọi handler attempts hoặc mọi side effect đã xảy ra.

Khi muốn delay retry:

1. Consumer phân loại transient failure.
2. Chọn delay/backoff và nơi retry sẽ chạy tiếp, ví dụ delayed/retry queue được cấu hình.
3. Publish bản retry, **chờ publish confirm hoặc cơ chế xác nhận tương ứng** theo policy.
4. Chỉ ACK original khi đã có cơ sở rằng message không bị mất giữa “ACK original” và “publish retry”.
5. Nếu publish fail, không log “retry scheduled” như sự thật; báo lỗi và áp dụng recovery policy.

Đây là **mô hình nghiệp vụ**, không phải bảo đảm rằng hai bước publish + ACK nguyên tử trên mọi cấu hình. Có thể có khoảng trống hoặc duplicate nếu crash/timeout giữa các bước. Thiết kế idempotency/durable relay để chấp nhận at-least-once. Với RabbitMQ quorum queues và delivery limits hoặc các plugin delayed message, kiểm tra tài liệu **đúng loại queue và phiên bản** vì semantics khác nhau.

### Logging riêng cho RabbitMQ

Các field hữu ích: `queue`, `exchange`, `routing_key`, `message_id`, `correlation_id`, `consumer_tag`, `redelivered`, `delivery_tag` và attempt metadata đáng tin. Không log body mặc định.

Ví dụ event sau khi publish retry **đã được xác nhận**:

```json
{
  "event": "message.retry_scheduled",
  "message_id": "msg-71",
  "queue": "payments.retry.5s",
  "attempt": 1,
  "next_attempt": 2,
  "retry_delay_ms": 5000,
  "publish_confirmation": "CONFIRMED"
}
```

JSON chỉ minh họa schema; không phải RabbitMQ tự phát field này. Nếu ACK original sau đó thất bại, cần log thêm **trạng thái của ACK** và chấp nhận khả năng duplicate. Việc retry publish thành công không tự động xác nhận original đã được ACK.

## 10. Kafka: retry khác với RabbitMQ như thế nào?

Kafka consumer đọc record theo `topic`/`partition`/`offset`. Trong Kafka, **commit offset** thể hiện tiến độ đọc của consumer group; đó **không** phải ACK từng message theo kiểu RabbitMQ. Một consumer có thể xử lý record nhiều lần nếu chưa commit offset hoặc bị rebalance/crash. Các API/framework retry có chiến lược khác nhau.

Cần phân biệt các mô hình:

### 10.1. Retry tại chỗ trên consumer thread

Handler giữ record hiện tại và thử lại trong cùng process. Cách này đơn giản nhưng nếu `sleep` lâu hoặc retry bị chặn, có thể cản consumer poll/heartbeat hoặc giữ partition không tiến lên, tùy framework/cấu hình. Ghi log `attempt` của handler, nhưng **offset vẫn là offset của record**; đừng giả định mỗi attempt có offset mới.

### 10.2. Retry topic và delayed processing

Một ứng dụng/framework có thể publish record lỗi sang một hoặc nhiều retry topics với delay khác nhau. Khi đó:

- Record retry có thể mang metadata/message envelope mới ở tầng broker, nhưng cần **giữ original message ID/operation ID** để liên hệ.
- `topic` và `offset` của bản retry **khác** nguồn; chúng không được dùng làm định danh duy nhất của business operation.
- Commit offset nguồn và publish bản retry là hai thao tác cần thiết kế tránh mất/duplicate; khả năng atomic transaction tùy tích hợp Kafka và nguồn dữ liệu nghiệp vụ.
- Retry topics có thể làm thay đổi ordering giữa các message cùng key; nếu ordering quan trọng, cần chính sách riêng.

### 10.3. Khi nào ghi `offset_committed`?

Chỉ sau khi API commit hoặc cơ chế framework báo thành công theo contract. Việc handler return không đồng nghĩa offset đã commit; với auto-commit, semantics còn khác. Nếu framework tự commit theo batch, log `message.processed` vẫn nên được hiểu là handler success chứ không khẳng định commit của từng record.

Nếu cần xử lý đúng một lần trong một pipeline Kafka cụ thể, phải nghiên cứu **Kafka transactions**, `read_committed`, idempotent producer và phạm vi semantics của ứng dụng. “Exactly-once processing” trong một tuyến Kafka được cấu hình đúng **không tự bao gồm** mọi side effect ngoài Kafka như gửi email, gọi payment API hoặc sửa DB bên ngoài. Log phải phản ánh đúng ranh giới ấy.

### Các trường Kafka nên dùng khi điều tra

- `topic`, `partition`, `offset` của record hiện tại và `original_topic/partition/offset` khi phát sang retry topic.
- `consumer_group`, `consumer_instance`, `record_key` đã giảm nhạy cảm nếu cần.
- `message_id`/`operation_id` ổn định qua retry, retry header được validate, timestamp nguồn/ingest.
- `rebalance`, `commit_failed`, `retry_topic_publish_failed` và `replayed` có event code riêng.

Lưu ý consumer group lag lớn không tự chứng minh số log bị mất; nó phản ánh tiến độ đọc theo group và cần đối chiếu với retry/backlog/handler metrics.

## 11. Idempotency và độ tin cậy khi xử lý lại

Một vấn đề chính của retry message là **side effect lặp lại**. Ví dụ consumer gọi API thanh toán, remote server đã ghi nhận giao dịch nhưng response mất vì network timeout. Nếu consumer retry mà không có idempotency key, có thể phát sinh hai lần thu tiền. Logging rất quan trọng để điều tra, nhưng **không thay thế** cơ chế ngăn double effect.

### 11.1. Idempotent consumer bằng business key

Một thiết kế có thể lưu `operation_id`/`message_id` đã xử lý thành công trong DB. Khi cùng message tới lại, consumer kiểm tra và bỏ qua side effect:

```text
Receive message with operation_id=pay-71
BEGIN transaction
  INSERT processed_operations(operation_id=pay-71) if absent
  IF already exists:
      skip duplicate effect
  ELSE:
      apply business state change
COMMIT
ACK/commit progress according to broker contract
```

Đây là **pseudocode**, cần unique constraint và transaction/isolation phù hợp. Nếu chỉ làm `SELECT` rồi `INSERT` không có ràng buộc đồng thời, hai worker có thể cùng thấy “chưa tồn tại” và thực thi side effect hai lần. Nếu side effect là call đến hệ thống bên ngoài, transaction DB cục bộ **không** bảo đảm nguyên tử với API ngoài; cần idempotency contract, outbox/saga hoặc reconciliation.

Log cho duplicate có thể là:

```text
event=message.duplicate_skipped message_id=msg-71 operation_id=pay-71 reason=already_processed
```

Đừng ghi `message.processed outcome=NEW_SUCCESS` cho một duplicate đã bỏ qua nếu không có xử lý nghiệp vụ mới. Một message bị skip do đã xử lý không phải lỗi; có thể ghi INFO/DEBUG và tăng metric `idempotency_skips_total`.

### 11.2. Transactional outbox

Khi một xử lý phải cập nhật DB rồi phát event tiếp, có thể ghi **business change và outbox event trong cùng transaction**. Publisher đọc outbox và retry khi broker lỗi. Điều này giảm rủi ro “DB đã commit nhưng publish event bị mất”. Tuy nhiên publisher có thể gửi lại, nên consumer vẫn cần idempotent.

Tương tự, khi chuyển message lỗi sang retry topic/DLQ rồi ACK original, cần xác định độ bền của chuyển tiếp; không được khẳng định chuyển tuyến là atomic nếu broker API hoặc transaction không cung cấp cam kết đó.

### 11.3. Outcome UNKNOWN

Khi call ngoại vi timeout:

```text
event=message.side_effect_outcome_unknown
message_id=msg-71
operation_id=pay-71
error_code=REMOTE_TIMEOUT
next_action=RECONCILE_OR_IDEMPOTENT_RETRY
```

Không ghi `payment.failed` như một sự thật chắc chắn nếu remote đã có thể thu tiền. Cần probe/reconcile theo operation ID hoặc retry an toàn dựa trên idempotency key. Trong log, phân biệt **attempt thất bại về mặt giao tiếp** với **business effect chưa xảy ra**.

## 12. Retry, dead-letter queue và poison message

DLQ/parking queue là một cơ chế bảo vệ pipeline khỏi message không xử lý được bằng policy hiện tại. Tuy nhiên, DLQ không phải “thùng rác”: message trong đó có thể chứa dữ liệu nhạy cảm, cần retention, quyền truy cập, cảnh báo, khả năng xử lý lại và truy vết.

### Chuyển DLQ cần hai mốc

1. **`message.dlq_requested`**: ứng dụng quyết định message không được thử thêm và yêu cầu chuyển tuyến.
2. **`message.dlq_confirmed`**: một thành phần/broker xác nhận theo contract rằng message đã được nhận ở đích DLQ tương ứng.

Nếu cơ chế broker trực tiếp dead-letter khi NACK/reject, application có thể chỉ biết “request broker thực hiện policy”, không có xác nhận riêng về từng message ở DLQ. Lúc này không nên giả vờ đã xác nhận; kết hợp broker metrics, DLQ consumer/inspection và end-to-end test để xác thực.

Thông tin hữu ích khi exhausted:

```json
{
  "event": "message.retry_exhausted",
  "message_id": "msg-303",
  "operation_id": "op-303",
  "attempt": 5,
  "max_attempts": 5,
  "first_attempt_at": "2026-11-10T02:00:00Z",
  "last_attempt_at": "2026-11-10T02:01:14Z",
  "error_code": "DOWNSTREAM_TIMEOUT",
  "terminal_policy": "DLQ",
  "outcome": "RETRIES_EXHAUSTED"
}
```

Đây là **ví dụ schema**, không phải log thực. Nếu message sau đó được operator replay, giữ `original_message_id`/`operation_id`, thêm `replay_id`, `replay_reason`, actor/approver theo policy và liên kết lifecycle cũ/mới. Không xóa lịch sử retry cũ hoặc reset ID khiến điều tra mất trace.

### Đừng replay DLQ vô hạn

Một poison message có thể tiếp tục fail sau replay. Cần giới hạn vòng replay, kiểm soát ai được replay, kiểm tra version/schema đã sửa, tách traffic replay khỏi business traffic và có cơ chế dừng khẩn khi phát hiện log storm. Replay cần audit vì nó có thể tái kích hoạt side effect.

## 13. Metrics và tracing đi cùng log retry

Logging từng attempt giúp điều tra từng message, nhưng để giám sát toàn hệ thống nên có metrics độc lập:

| Metric gợi ý | Định nghĩa | Tránh nhầm |
| --- | --- | --- |
| `messages_received_total` | Số deliveries quan sát được tại consumer | Không bằng số message logic duy nhất |
| `message_processing_attempts_total` | Số lượt handler đã thực thi | Có thể lớn hơn deliveries nếu retry in-process |
| `message_retry_planned_total` | Số lần policy chọn retry | Chưa chắc broker đã chấp nhận schedule |
| `message_retry_scheduled_total` | Số lần scheduling được xác nhận | Không chứng minh attempt tiếp theo đã chạy |
| `messages_processed_total` | Số handler completions thành công theo contract | Không tự chứng minh ACK/offset commit |
| `message_processing_failures_total` | Số attempt thất bại, theo error category | Khác số logical messages thất bại cuối cùng |
| `message_retries_exhausted_total` | Số message logic hết retry budget | Không tự chứng minh DLQ success |
| `message_dlq_failures_total` | Số lần chuyển DLQ hoặc publish route thất bại | Cần alert riêng |
| `message_duplicate_skips_total` | Số deliveries bị bỏ qua do idempotency | Không phải message loss |
| `message_processing_duration_seconds` | Histogram thời gian handler | Không bao gồm queue residence trừ khi định nghĩa vậy |
| `message_retry_delay_seconds` | Phân bố delay đã chọn/đã thực hiện | Đừng lẫn planned và actual |
| `message_age_seconds` / `retry_queue_lag` | Độ trễ từ event gốc tới thời điểm xử lý | Có thể khác broker consumer lag |
| `broker_commit_failures_total` | Lỗi ACK/offset commit theo adapter | Tên và semantics khác nhau giữa broker |

Các tên chỉ là gợi ý, không tự có sẵn trong mọi framework. Với Prometheus/metrics, **không dùng `message_id`, `operation_id`, `trace_id` làm metric labels** vì cardinality khổng lồ. Dùng nhãn có tập giá trị hữu hạn như `service`, `consumer_group`, `error_category`, `outcome` và tên topic/queue được kiểm soát. ID chi tiết nằm trong log/trace, không nằm trong nhãn metric.

### Trace context qua retry

Một message gốc có trace context do producer truyền. Trong các lần retry, có thể giữ liên kết với trace gốc qua parent context hoặc span links tùy instrumentation/semantics:

- Không ép mọi attempt ở các thời điểm cách xa hàng giờ phải xuất trong cùng một span kéo dài liên tục.
- Tạo span cho từng delivery/processing attempt khi tracing stack hỗ trợ, giữ `message_id`/`operation_id` để tìm quan hệ.
- Validate các tracing headers từ nguồn không tin cậy theo policy.
- Khi executor/async listener đổi thread, context propagation và cleanup phải được kiểm tra, không tự giả định MDC/ThreadContext luôn truyền đúng.

Điều tra thường bắt đầu bằng `message_id` rồi theo event codes `retry_planned`, `retry_scheduled`, `processed`, `acknowledged` hoặc `dlq_confirmed`. Nếu event thiếu đoạn cuối, phải xác định liệu worker crash, sink log mất, broker action chưa thành công hay hệ thống chỉ chưa index kịp.

## 14. Sự cố logging có thể làm retry tệ hơn

Nếu mỗi retry tạo log lớn và hệ thống retry hàng loạt, logging sink có thể thành bottleneck:

- **Sync logging** có thể giữ consumer thread trong I/O, làm tăng processing latency.
- **Async logging** có bounded queue; khi đầy có thể block producer hoặc drop log tùy policy.
- **Collector outage** làm log đến chậm hoặc mất; không nên dùng số dòng log làm số message processed duy nhất.
- **Stack trace lặp** tạo volume lớn, giảm throughput của log shipper và tăng retention/storage cost.
- **Log nhạy cảm từ payload/exception** có thể phát tán rộng trong collector, DLQ và dashboard.

Cần tách ít nhất bốn loại số liệu: message handler attempts, application policy filtered logs, logging queue drops và actual message broker redeliveries. Nếu dashboard thấy số log retry thấp hơn, chưa chắc lỗi đã giảm: có thể logger level/sampling hoặc logging pipeline bị nghẽn.

Nếu audit/critical events cần không mất, thiết kế đường lưu bền vững riêng và chính sách fail-open/fail-closed đã được phê duyệt. **Không dùng một logging appender chung làm nguồn duy nhất để quyết định ACK**; broker acknowledgement phải dựa trên kết quả xử lý và chính sách giao nhận, không dựa vào việc log đã được in.

## 15. Thời gian và ordering khi message retry

Một message có thể được phát lúc 09:00, xử lý attempt 1 lúc 09:01, retry attempt 2 lúc 09:03 và tới DLQ lúc 09:20. Các mốc cần tách:

- `produced_at`: khi producer tạo message (nguồn gốc và trust level rõ ràng).
- `first_received_at`: khi consumer lần đầu quan sát message.
- `attempt_started_at` và `attempt_finished_at`: ranh giới từng handler attempt.
- `retry_planned_at` / `retry_scheduled_at`: lúc policy quyết định và lúc scheduler/broker xác nhận.
- `next_attempt_at`: thời điểm sớm nhất dự kiến, không nhất thiết chính xác khi worker bắt đầu.
- `last_failure_at`: lỗi cuối đã xảy ra.
- `dlq_requested_at` / `dlq_confirmed_at`: hai mốc khác nhau.
- `ingested_at`: lúc collector/index nhận log, có thể muộn vì queue.

Dùng `Instant`/ISO-8601 với offset rõ để lưu timestamp; dùng `System.nanoTime()` để đo **duration trong cùng JVM**, không dùng nó như epoch timestamp across services. Clock skew có thể làm timestamp trên hai máy trông ngược thứ tự; kết hợp attempt sequence, broker offsets, business version, causal links và event IDs.

**Ordering** là một đặc tính phụ thuộc broker và cách retry:

- Một partition Kafka có ordering theo offset của record **trong partition đó**, nhưng chuyển lỗi sang retry topic có thể cho các record mới vượt qua record đang chờ.
- RabbitMQ requeue và multiple consumers có thể làm thứ tự giao/xử lý khác với thứ tự publish.
- Retry async/scheduled có thể chạy trên worker khác, không giữ thứ tự request gốc.

Nếu business cần strict ordering theo key, thiết kế partition/serial execution và retry policy chuyên biệt; không kết luận thứ tự đúng chỉ vì timestamp trong log tăng đều.

## 16. Kịch bản kiểm thử logging cho retry

Một bộ test cần khẳng định cả **positive path** và **negative path**:

| Mã | Kịch bản | Log đúng | Điều không được xảy ra |
| --- | --- | --- | --- |
| R1 | Thành công attempt 1 | `processed` với `attempt=1`, outcome SUCCESS | Không có retry/exhausted |
| R2 | Transient fail rồi thành công | `retry_planned`/`scheduled` đúng mốc, sau đó `processed` | Không ghi terminal FAILED khi cuối cùng thành công |
| R3 | Permanent invalid schema | `dlq_requested` hoặc reject theo policy ở attempt đầu | Không retry vô hạn |
| R4 | Hết max attempts | `retry_exhausted` với count, reason và terminal policy | Không có next attempt vượt giới hạn |
| R5 | Publish retry bị lỗi | `retry_publish_failed`, original được giữ/xử lý theo policy | Không ghi `retry_scheduled` thành công giả |
| R6 | DLQ publish bị lỗi | `dlq_publish_failed` có alert/metric | Không ghi `dlq_confirmed` khi chưa nhận xác nhận |
| R7 | Handler success rồi crash trước ACK/commit | Redelivery có thể tới; idempotent skip | Không phát sinh business effect thứ hai |
| R8 | Remote timeout sau side effect | `outcome=UNKNOWN`, reconciliation/idempotency | Không khẳng định side effect thất bại chắc chắn |
| R9 | Retry header sai hoặc thiếu | Default/validation policy có log an toàn | Không tin retry count/tenant từ input tùy ý |
| R10 | Consumer rebalance trong processing | Log có group/partition/instance và commit status | Không coi handler return là offset commit |
| R11 | 1.000 messages đồng loạt lỗi | Metrics và log volume trong ngân sách | Không tạo log storm làm cạn queue/CPU |
| R12 | DLQ replay sau khi sửa lỗi | Liên kết original ID, replay ID và actor | Không mất lịch sử retries trước đó |
| R13 | Collector down trong lúc retry | Message processing vẫn theo policy và log loss được đo | Không giả định thiếu log = không retry |
| R14 | Message chứa secret giả | Log chỉ có metadata đã duyệt | Không phát tán raw secret qua log, DLQ, trace |

### Cách triển khai integration test

1. Tạo các message test với `message_id` và `operation_id` duy nhất.
2. Mô phỏng downstream lỗi transient có số lần xác định, sau đó hồi phục.
3. Đối chiếu số handler attempts, retry delay, thời điểm scheduling acknowledgement và số business effects thực tế.
4. Gây lỗi permanent; xác minh không retry ngoài ý muốn và quan sát DLQ/parking theo contract.
5. Dừng consumer sau side effect nhưng trước broker ACK; khởi động lại, kiểm tra không sinh thêm side effect vì idempotency.
6. Gây lỗi publish retry/DLQ để chứng minh các event log **không báo success trước confirmation**.
7. Đo log volume, queue depth, CPU, p95/p99 handler, consumer lag và visibility latency.
8. Truy vấn log tập trung theo message ID, kiểm tra correlation/tracing, exception code, không có raw payload nhạy cảm.
9. Khôi phục môi trường thử và xác minh không có test message/queue tạm tồn dư gây ảnh hưởng đến người dùng thật.

Nếu dùng broker thật, đặt timeout và cleanup rõ; một test yêu cầu “số log chính xác ngay sau handler” có thể sai vì appender/collector bất đồng bộ. Chờ có deadline, phân biệt **không tới sink** và **chưa searchable**.

## 17. Runbook khi retry tăng bất thường

Khi cảnh báo `retry_attempts_total`/`retry_exhausted_total` tăng:

1. **Xác định phạm vi:** queue/topic, consumer group, service release, khoảng thời gian, error category và số message logic bị ảnh hưởng.
2. **Tách signal:** bao nhiêu deliveries, processing attempts, exhausted messages và duplicate skips? Tránh đếm số dòng ERROR thành số message hỏng.
3. **Nhận diện nguồn lỗi:** downstream 5xx/timeout, schema đổi, invalid auth, rate limit, DB outage, message poison hay consumer bug.
4. **Kiểm tra retry policy:** max attempts, backoff, jitter, queue capacity, pending/retry topic lag, hot requeue và concurrency.
5. **Kiểm tra broker ACK/offset:** có redelivery ngoài dự kiến do crash/rebalance/commit fail? Có publish retry thành công nhưng original ACK fail dẫn đến duplicate?
6. **Đánh giá side effect:** hoạt động nghiệp vụ có thể đã thành công một phần? Có idempotency key và reconciliation không?
7. **Kiểm tra DLQ:** các message exhausted đã thực sự vào DLQ? DLQ có permission/quota/retention phù hợp? Có kẹt ở bước publish?
8. **Giảm tải an toàn:** theo policy, giảm concurrency, circuit breaker, tăng backoff, giới hạn retry storm và sửa root cause; không tắt audit hoặc xóa message chưa điều tra.
9. **Xác minh hồi phục:** processing success rate tăng, consumer lag giảm, queue backlog drain, log visibility và error metrics trở lại bình thường.
10. **Ngăn tái diễn:** thêm regression test cho schema, retry policy, dedup/ACK boundary và dashboard/tracing.

Nếu poison message lặp cùng ID gây nóng partition, không chọn “retry mãi đến khi hết lỗi”. Cần có terminal policy với giám sát, giải pháp triage và khả năng replay an toàn.

## 18. Các lỗi thiết kế/logging thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| In `ERROR` + stack trace ở mọi attempt | Log storm che root cause và nghẽn logging pipeline | Event code, hạn chế verbosity, summary và metrics |
| Không có stable message ID | Không ghép retry qua consumer instance/topic | Gắn application-level ID, giữ original ID qua retry |
| `attempt=0` ở nơi khác `attempt=1` | Dashboard và policy đếm sai | Ghi contract, một quy ước và test biên |
| Nhầm max retries với max attempts | Thử quá nhiều/ít so với yêu cầu | Định nghĩa tổng handler invocations và số retries |
| Ghi “retry scheduled” trước publish confirm | Báo success sai khi broker đang lỗi | Planned → confirmation/failure events |
| Ghi “DLQ complete” ngay sau NACK | Không biết DLX thực sự đã route/lưu | Kiểm tra broker semantics và DLQ evidence |
| Dựa vào log call để ACK message | Log sink không bảo đảm business outcome | ACK/commit theo xử lý + durable policy |
| Retry mọi lỗi validation | Poison messages đốt tài nguyên | Classify permanent/transient và DLQ |
| Đọc retry count từ untrusted header | Bypass policy, route sai tenant hoặc retry quá mức | Validate, dùng internal attempts |
| Dùng broker offset/delivery tag làm business ID | Không ổn định xuyên retry hoặc connection | Operation ID/idempotency key riêng |
| Dùng `Thread.sleep` lâu trong listener | Nghẽn thread/partition, có thể ảnh hưởng poll/heartbeat | Scheduled retry/delayed queue hoặc policy phù hợp |
| Không idempotent khi ACK mất | Một side effect được thực hiện nhiều lần | DB unique constraint/outbox/idempotency key |
| Retry remote timeout và kết luận “chưa xử lý” | Double charge/mutation | UNKNOWN outcome + reconciliation |
| Ghi raw payload và headers khi lỗi | Rò PII/secret vào log tập trung | Chỉ log safe metadata, error code, redaction |
| Không quan sát DLQ publish error | Message kẹt/mất khỏi điều tra | Metrics/alert và failure path được thử |
| Chỉ đo log lines chứ không đo attempts | Log sampling/drop tạo số liệu ảo | Metrics nghiệp vụ và broker counters |
| Reuse MDC giữa messages | Sai correlation/tenant leakage | Scope, cleanup, propagation tests |
| Chỉ nhìn timestamp để kết luận ordering | Async retry có reorder/clock skew | Version/offset/attempt sequence và causal links |

## 19. Checklist triển khai thực tế

- [ ] Có định nghĩa rõ message ID, operation ID, correlation ID và attempt/delivery count?
- [ ] Có phân biệt handler attempt, broker delivery và retry publish hay không?
- [ ] Error classifier xác định transient/permanent/ambiguous, có unit test?
- [ ] Max attempts, exponential backoff, jitter và total retry TTL được cấu hình/kiểm thử?
- [ ] `retry_planned`, `retry_scheduled`, `retry_publish_failed` có nghĩa riêng?
- [ ] `dlq_requested` và `dlq_confirmed` chỉ phát ở đúng acknowledgement boundary?
- [ ] ACK/offset commit không bị đánh đồng với handler success?
- [ ] Consumer idempotent với business side effects, có xử lý duplicate và UNKNOWN outcomes?
- [ ] Log có message ID, attempt, reason code, next delay, service, consumer instance và ngữ cảnh broker phù hợp?
- [ ] Không ghi raw payload, secret, token hay untrusted exception message?
- [ ] MDC/trace context được truyền và cleanup đúng qua thread pool/async?
- [ ] Có metric cho attempts, retry planned/scheduled, exhausted, DLQ failures và idempotency skips, với labels bounded?
- [ ] Đã thử transient recover, permanent invalid, process crash, rebalance, publish failure và replay DLQ?
- [ ] Có dashboard/alert đối với retry storm và poison message?
- [ ] Có runbook/owner/quyền xử lý DLQ và retention đủ để điều tra?
- [ ] Có quy trình rollback khi thay đổi retry policy mà không làm mất dấu vết?

**Tiêu chí hoàn thành:** Bạn giải thích được lifecycle một message qua nhiều attempts, phân biệt planned/confirmed tại ranh giới broker, không nhầm ACK với handler success, thiết kế log retry đủ để điều tra và không làm lộ payload, đồng thời chạy được ví dụ Java 17 với kết quả đúng như bảng.

## 20. Câu hỏi tự kiểm tra

1. Một message được broker giao hai lần nhưng handler retry ba lần ở delivery đầu: `delivery_attempts` và `processing_attempts` có thể khác nhau thế nào?
2. Vì sao `message_id` và `operation_id` không nên được thay bằng Kafka offset hoặc RabbitMQ delivery tag?
3. Khi handler lỗi vì dữ liệu thiếu field bắt buộc, điều gì khiến việc retry nhiều lần trở nên nguy hiểm?
4. Sự khác biệt giữa `message.retry_planned` và `message.retry_scheduled` là gì?
5. Khi publish tới DLQ thất bại sau khi ACK original, sự cố nào có thể xảy ra?
6. Vì sao client timeout sau khi gọi payment API không chứng minh thanh toán chưa thực hiện?
7. Một consumer Kafka xử lý record thành công nhưng crash trước khi commit offset; điều gì xảy ra và cần cơ chế gì?
8. Vì sao retry topic có thể thay đổi ordering của các message cùng key?
9. Tại sao log từng attempt không thay thế được metric tổng số processing attempts?
10. Khi mọi attempt đều in stack trace ERROR, logging pipeline có thể ảnh hưởng chính consumer ra sao?
11. Làm cách nào để đảm bảo log của message B không mang MDC/trace ID của message A trong thread pool?
12. Việc Kafka hỗ trợ exactly-once semantics trong một pipeline có đảm bảo email hoặc payment API bên ngoài chỉ thực hiện một lần không?
13. Nên log gì khi retry publisher trả về timeout và chưa biết broker đã nhận message hay chưa?
14. Khi operator replay một DLQ message, cần giữ lại những ID/mốc nào để điều tra toàn bộ lịch sử?
15. Vì sao ví dụ `RetryMessageLoggingDemo` không in `dlq_confirmed` dù đã có nhánh quyết định DLQ?

## Tài liệu tham khảo

- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms) — phân biệt acknowledgement của consumer và publisher.
- [RabbitMQ — Negative Acknowledgements](https://www.rabbitmq.com/docs/nack) — requeue/reject semantics và rủi ro redelivery.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx) — cấu hình và hành vi dead-lettering.
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs) — offset commit, polling và consumer progress.
- [Apache Kafka — Delivery Semantics](https://kafka.apache.org/documentation/#semantics) — các mức bảo đảm giao nhận và giới hạn của exactly-once.
- [Spring for Apache Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html) — retry topics và các tradeoff về ordering.
- [SLF4J Manual](https://www.slf4j.org/manual.html) — parameterized logging, logger API và MDC.
- [Oracle Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html) — injectable clock/test deterministic.
- [Oracle Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) — thời điểm rõ ràng trong log.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — dữ liệu nhạy cảm, tín hiệu sự kiện và bảo vệ log.
