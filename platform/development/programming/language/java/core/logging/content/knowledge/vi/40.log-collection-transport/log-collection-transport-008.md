# Retry vận chuyển log trong Java Core Logging

## 1. Retry vận chuyển là gì?

Trong hệ thống logging có collector hoặc kho log tập trung, **retry vận chuyển (transport retry)** là việc thử gửi lại log event hoặc một batch log khi lần chuyển trước không được xác nhận thành công theo hợp đồng của đường truyền. Đây là một bước trong **log pipeline**, không phải việc chạy lại thao tác nghiệp vụ vốn đã tạo ra log.

~~~text
Java application
       |
       v
Logger / Handler / Appender
       |
       v
Local buffer / queue / file spool
       |
       v
Exporter / log shipper
       |
    send batch --------------------+
       |                           |
       v                           v
Collector / gateway            Network failure
       |                           |
       v                           v
Response / acknowledgment     Retry policy
       |                           |
       +--> accepted               +--> delay, retry,
            (theo contract)             or stop
       |
       v
Index / durable store (co the la buoc sau)
~~~

Ví dụ một ứng dụng Java ghi event `order_loaded`. Exporter gộp 100 event, gửi HTTP tới collector; collector tạm trả `503`. Exporter có thể giữ batch và gửi lại sau một khoảng trì hoãn. Nếu ứng dụng **tự chạy lại `loadOrder()`** chỉ vì exporter gửi log lỗi, ta đã nhầm lẫn hai loại retry và có thể tạo side effect nghiệp vụ trùng.

Một hệ thống ghi log tốt cần trả lời rõ bốn câu hỏi:

1. **Retry ở tầng nào?** Appender, log shipper, collector exporter hay ứng dụng?
2. **Thế nào là thành công?** HTTP 202, ACK của broker, collector đã nhận vào queue, hay đã lưu bền vững?
3. **Khi nào dừng retry?** Theo số lần, tuổi dữ liệu, thời gian, loại lỗi hoặc giới hạn tài nguyên?
4. **Nếu kết quả gửi không rõ ràng thì sao?** Có thể nhận bản trùng, mất bản ghi hoặc cả hai tùy thiết kế.

**Phân biệt quan trọng:** `logger.info(...)` trả về bình thường không đồng nghĩa event đã đến collector. Nó có thể mới được chấp nhận vào queue, buffer hoặc file cục bộ. Tương tự, `send()` không ném exception cũng chưa chắc là kho log cuối cùng đã xác nhận lưu bền vững.

## 2. Những lỗi nào có thể retry?

Không phải mọi thất bại vận chuyển đều nên thử lại. Cần phân loại theo **khả năng tự hồi phục** và **hợp đồng của đích nhận**.

| Nhóm kết quả | Tình huống thường gặp | Hướng xử lý |
| --- | --- | --- |
| **Accepted / confirmed** | Đích trả xác nhận đúng hợp đồng | Đánh dấu batch/event hoàn tất ở tầng giao nhận tương ứng |
| **Transient / retryable** | Kết nối tạm ngắt, đích quá tải, `503`, đôi khi `429` | Retry có giới hạn, backoff, jitter; tôn trọng hướng dẫn từ đích |
| **Permanent / non-retryable** | Payload sai schema, sai encoding, lỗi cấu hình kéo dài | Không retry vô hạn cùng dữ liệu; phân loại, cách ly và cảnh báo |
| **Ambiguous / unknown** | Timeout sau khi gửi request; kết nối mất trước khi nhận ACK | Có thể đích đã nhận; retry đòi chính sách dedup/idempotency |
| **Partial success** | Một phần event được chấp nhận, phần còn lại bị reject/retry | Chỉ xử lý phần chưa thành công theo ngữ nghĩa của API, tránh resend mù |

Một số ví dụ HTTP để **khởi đầu thiết kế**, không phải luật cố định của mọi collector:

- `429 Too Many Requests`: thường là tín hiệu giới hạn tốc độ; kiểm tra `Retry-After` và chính sách backpressure.
- `500`, `502`, `503`, `504`: thường đáng retry có giới hạn; trước hết kiểm tra tài liệu API, khả năng chống trùng và chi phí.
- `408 Request Timeout`, timeout kết nối hoặc I/O exception: có thể retry nhưng kết quả của lần trước **có thể không rõ**, nhất là sau khi request đã được gửi.
- `400 Bad Request`: thường payload không hợp lệ; gửi lại không thay đổi dữ liệu sẽ không giúp gì. Một số hệ thống trả thông tin lỗi chi tiết cho từng record.
- `401`/`403`: thường là vấn đề xác thực/phân quyền; cần xử lý credential/config bằng luồng riêng, **không retry nóng**.
- `413 Content Too Large`: thường cần giảm batch/sửa giới hạn, không gửi lại nguyên batch vô hạn.
- `404` hoặc URL sai: thường phải sửa endpoint/config, không nên retry mù.

**Không dựa duy nhất vào status code** nếu collector định nghĩa ngữ nghĩa đặc biệt. Chẳng hạn một API có thể trả `200` cùng body báo lỗi từng phần, hoặc `202` chỉ xác nhận đã đưa vào hàng đợi. Chính contract của hệ thống nhận mới xác định success và retry policy.

## 3. Retry không tương đương lưu bền vững

Hãy tách các mốc trong vòng đời một event:

~~~text
EVENT_CREATED
    |
    v
ACCEPTED_BY_LOCAL_BUFFER
    |
    v
SENT_BY_EXPORTER
    |
    v
RECEIVED_OR_ACKED_BY_COLLECTOR
    |
    v
INDEXED_OR_DURABLY_STORED
~~~

Tùy hạ tầng, acknowledgment ở bước `RECEIVED` có thể **không** chứng minh `DURABLY_STORED`. Đường truyền TCP gửi xong bytes không chứng minh ứng dụng phía đích đã parse, chấp nhận hoặc lưu dữ liệu. Ngay cả HTTP `2xx` cũng chỉ có ý nghĩa theo hợp đồng cụ thể.

Khi thiết kế logging, nên định nghĩa rõ **delivery guarantee**:

- **Best effort:** có thể drop khi lỗi, nghẽn hoặc shutdown; đổi lại giảm overhead.
- **At-most-once:** tránh gửi lặp, nhưng có thể mất khi kết quả gửi không rõ.
- **At-least-once:** thử gửi lại tới khi nhận ACK theo chính sách; giảm mất dữ liệu khi lỗi tạm, đổi lại **có thể có bản trùng**.
- **Exactly-once ở đích cuối:** cần cơ chế xác nhận, giao dịch/dedup cụ thể trên toàn đường; không thể tự suy ra chỉ vì exporter retry.

Audit log hoặc log nghiệp vụ cực kỳ quan trọng có thể cần kênh bảo đảm mạnh hơn log chẩn đoán thông thường. Khi tính toàn vẹn là bắt buộc, xem xét persistent queue, outbox/inbox, event ID, acknowledgment, kiểm tra integrity và một hệ thống lưu độc lập phù hợp. **Retry chỉ là một phần của độ tin cậy, không phải bảo đảm độc lập.**

## 4. Exponential backoff và jitter

Một exporter không nên gửi lại lỗi `503` liên tục không delay. Retry nóng tạo thêm tải chính lúc collector đang quá tải, làm tăng queue, network và chi phí.

Một lịch backoff đơn giản:

\[
d_n = \min(d_{max}, d_0\, 2^{n-1})
\]

Trong đó:

- `n`: số lần gửi **đã thất bại** tính từ 1.
- `d0`: thời gian chờ đầu tiên, ví dụ 250 ms.
- `dMax`: trần, ví dụ 2.000 ms.

| Lần gửi vừa thất bại | Chờ theo công thức (d0=250 ms, max=2.000 ms) |
| --- | ---: |
| 1 | 250 ms |
| 2 | 500 ms |
| 3 | 1.000 ms |
| 4 | 2.000 ms |
| 5 trở đi | 2.000 ms |

Dãy đều đặn như vậy dễ khiến hàng nghìn client đồng loạt thử lại và tiếp tục gây **thundering herd**. Vì thế trong production, thường thêm **jitter** (độ ngẫu nhiên) để phân tán thời điểm retry. Một ví dụ:

~~~text
cappedDelay = min(maxDelay, baseDelay * 2^(failureCount - 1))
actualDelay = random(0, cappedDelay)      # full jitter
~~~

Một số hệ thống dùng equal jitter/decorrelated jitter. Không có công thức tối ưu duy nhất; chọn dựa trên tải, SLA, loại collector và yêu cầu latency. Đặt **giới hạn retry tổng**, timeout mỗi request, tổng thời gian cho phép, và hành động cuối khi hết ngân sách.

**`Retry-After`:** nếu đích trả header này cùng đáp ứng tương ứng, cần diễn giải dạng số giây hoặc ngày HTTP, dùng clock phù hợp và giới hạn độ dài chờ theo policy. Không cộng/nhân tùy tiện cùng backoff khi chưa có quy tắc; mục tiêu là tôn trọng nhịp đích nhận mà vẫn bảo vệ bộ đệm cục bộ.

**Phân biệt bốn giá trị:** `connectTimeout`, `requestTimeout`, `backoffDelay` và `maxRetryAge`. Một lần gửi chờ 5 giây không có nghĩa phải đợi 5 giây trước lần retry; timeout và delay là hai quyết định riêng.

## 5. Ví dụ Java 17 độc lập: giả lập chính sách retry của exporter

Ví dụ này dùng duy nhất **Java SE 17 và JUL**, không cần broker hoặc dịch vụ mạng. Một `Transport` giả trả lại kết quả theo kịch bản để dễ kiểm chứng:

- `batch-1`: hai lần lỗi tạm thời rồi nhận ACK ở lần 3.
- `batch-2`: lỗi vĩnh viễn ngay lần 1.
- `batch-3`: lần 1 không rõ đã gửi thành công hay chưa, sau đó còn lỗi tạm thời, và hết 4 lần gửi.

Để ví dụ chạy nhanh và **stdout xác định**, chương trình **chỉ tính và ghi lịch trì hoãn**, không thực sự `Thread.sleep`. Nó mô phỏng **logic retry**, chưa thực hiện vận chuyển mạng, queue bền vững, jitter hoặc receiver dedup. Message payload không được in vào log.

Tạo file **`LogTransportRetryDemo.java`**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogTransportRetryDemo {
    private static final int MAX_ATTEMPTS = 4;

    enum SendResult {
        ACKED, RETRYABLE, PERMANENT, UNKNOWN
    }

    enum Outcome {
        DELIVERED, PERMANENT_FAILED, EXHAUSTED
    }

    record Batch(String batchId, String eventName) {}

    interface Transport {
        SendResult send(Batch batch);
    }

    private static Transport scripted(SendResult... results) {
        if (results.length == 0) {
            throw new IllegalArgumentException("Missing results");
        }
        return new Transport() {
            private int index;

            @Override
            public SendResult send(Batch batch) {
                if (index < results.length) {
                    return results[index++];
                }
                return results[results.length - 1];
            }
        };
    }

    private static long backoffMillis(int failedAttempt) {
        long base = 250L;
        long cap = 2_000L;
        return Math.min(cap, base << (failedAttempt - 1));
    }

    private static Outcome deliver(
            Batch batch, Transport transport, Logger logger) {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            SendResult result = transport.send(batch);

            if (result == SendResult.ACKED) {
                logger.info("event=transport_confirmed batchId="
                        + batch.batchId() + " attempt=" + attempt);
                return Outcome.DELIVERED;
            }

            if (result == SendResult.PERMANENT) {
                logger.warning("event=transport_rejected batchId="
                        + batch.batchId() + " attempt=" + attempt);
                return Outcome.PERMANENT_FAILED;
            }

            if (attempt == MAX_ATTEMPTS) {
                logger.severe("event=transport_exhausted batchId="
                        + batch.batchId() + " attempt=" + attempt
                        + " lastResult=" + result);
                return Outcome.EXHAUSTED;
            }

            logger.warning("event=transport_retry_scheduled batchId="
                    + batch.batchId() + " attempt=" + attempt
                    + " result=" + result
                    + " delayMs=" + backoffMillis(attempt));
        }
        throw new AssertionError("Unreachable");
    }

    private static Logger loggerWithStdoutHandler() {
        Logger logger = Logger.getLogger("demo.transport.retry");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.print(getFormatter().format(record));
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + ": "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        logger.addHandler(handler);
        return logger;
    }

    public static void main(String[] args) {
        Logger logger = loggerWithStdoutHandler();
        try {
            Outcome first = deliver(
                    new Batch("batch-1", "order_loaded"),
                    scripted(SendResult.RETRYABLE,
                            SendResult.RETRYABLE,
                            SendResult.ACKED),
                    logger);

            Outcome second = deliver(
                    new Batch("batch-2", "order_loaded"),
                    scripted(SendResult.PERMANENT),
                    logger);

            Outcome third = deliver(
                    new Batch("batch-3", "order_loaded"),
                    scripted(SendResult.UNKNOWN,
                            SendResult.RETRYABLE,
                            SendResult.RETRYABLE,
                            SendResult.RETRYABLE),
                    logger);

            int delivered =
                    (first == Outcome.DELIVERED ? 1 : 0)
                    + (second == Outcome.DELIVERED ? 1 : 0)
                    + (third == Outcome.DELIVERED ? 1 : 0);

            logger.info("event=summary delivered=" + delivered
                    + " failed=" + (3 - delivered));
        } finally {
            for (Handler handler : logger.getHandlers()) {
                logger.removeHandler(handler);
                handler.close();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LogTransportRetryDemo.java
java LogTransportRetryDemo
~~~

**Stdout chính xác của ví dụ:**

~~~text
WARNING: event=transport_retry_scheduled batchId=batch-1 attempt=1 result=RETRYABLE delayMs=250
WARNING: event=transport_retry_scheduled batchId=batch-1 attempt=2 result=RETRYABLE delayMs=500
INFO: event=transport_confirmed batchId=batch-1 attempt=3
WARNING: event=transport_rejected batchId=batch-2 attempt=1
WARNING: event=transport_retry_scheduled batchId=batch-3 attempt=1 result=UNKNOWN delayMs=250
WARNING: event=transport_retry_scheduled batchId=batch-3 attempt=2 result=RETRYABLE delayMs=500
WARNING: event=transport_retry_scheduled batchId=batch-3 attempt=3 result=RETRYABLE delayMs=1000
SEVERE: event=transport_exhausted batchId=batch-3 attempt=4 lastResult=RETRYABLE
INFO: event=summary delivered=1 failed=2
~~~

**Stderr:** trống khi chạy thành công. JUL `ConsoleHandler` tiêu chuẩn thường xuất ra stderr, nhưng ví dụ **không dùng `ConsoleHandler`**; custom `Handler` ở đây chủ động xuất ra stdout và formatter loại bỏ timestamp động.

### Giải thích từng trường hợp

- `batch-1`: lần 1 và 2 trả `RETRYABLE`. Policy đề xuất chờ 250 ms, 500 ms; lần 3 có `ACKED`, không retry nữa.
- `batch-2`: `PERMANENT` nên dừng ngay, không tạo retry storm với payload sai.
- `batch-3`: `UNKNOWN` nghĩa **không biết đích đã nhận lần gửi trước hay chưa**. Nếu retry trong hệ thống thật, phải chấp nhận khả năng duplicate hoặc dựa vào dedup của receiver. Khi hết lần 4 thì `EXHAUSTED`.
- `MAX_ATTEMPTS=4` là **tổng cộng bốn lần gửi**, không phải bốn lần retry sau lần đầu.
- `backoffMillis` minh họa exponential backoff có trần nhưng **chưa có jitter**; code không sleep và không lưu dữ liệu xuống ổ đĩa. Vì vậy dòng `retry_scheduled` chỉ mô phỏng **ý định/lịch policy**, không chứng minh đã có timer chạy.
- `Batch.eventName` nằm trong đối tượng nhưng không được ghi vào event log; message ID/metadata của backend có thể là dữ liệu cần phân loại. Không nên in nguyên batch payload vào mỗi lần retry.

**Không đưa code mô phỏng này thẳng vào production**. Một exporter thực phải có cơ chế bảo toàn queue, bất đồng bộ/timeout, quản lý cancellation, thread, retry budget, backpressure, tín hiệu xác nhận và xử lý restart.

## 6. Gửi qua HTTP trong Java: nhận diện kết quả và kiểm soát timeout

Một exporter HTTP thực có thể dùng `java.net.http.HttpClient` của JDK 17. Đoạn dưới đây **chỉ minh họa một lần gửi**, không phải chương trình độc lập hoặc một retry loop hoàn chỉnh:

~~~java
// Ma tich hop; client, endpoint, ndjson, batchId da duoc tao.
// endpoint phai la dich collector duoc phe duyet.
HttpRequest request = HttpRequest.newBuilder(URI.create(endpoint))
        .timeout(Duration.ofSeconds(5))
        .header("Content-Type", "application/x-ndjson")
        .header("X-Batch-Id", batchId)
        .POST(HttpRequest.BodyPublishers.ofString(
                ndjson, StandardCharsets.UTF_8))
        .build();

HttpResponse<Void> response =
        client.send(request, HttpResponse.BodyHandlers.discarding());

int status = response.statusCode();
~~~

Các import cần khi tích hợp:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
~~~

Từ `status` phải áp dụng policy **đúng theo collector đang dùng**. Ví dụ: `429` có thể cần `Retry-After`; `503` có thể retry; `400` có thể cần cách ly payload. Cần xử lý `IOException`, timeout, và `InterruptedException` của `send`. Nếu đã bắt `InterruptedException` mà không ném tiếp, thông thường phải khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()`, không lặng lẽ tiếp tục retry trong lúc hệ thống muốn shutdown.

**`X-Batch-Id` chỉ là header do ví dụ đặt.** Nó không tự kích hoạt idempotency. Chỉ khi phía collector được thiết kế để nhận ID này, lưu trạng thái và loại bản trùng đúng hợp đồng thì nó mới giúp chống gửi trùng. Một số collector không hiểu header này hoặc bỏ qua hoàn toàn.

**Đừng đọc `response.statusCode() == 200` rồi suy ra mọi event đã lưu.** Hãy kiểm tra danh sách status thành công được hỗ trợ, response body (nếu có partial success), khả năng trả trạng thái async và các quyền hạn của endpoint.

## 7. Queue, buffer và backpressure khi vận chuyển gián đoạn

Nếu collector không khả dụng trong 30 phút, retry mỗi request không giải quyết được câu hỏi **những event mới sẽ đi đâu**. Cần một chính sách buffer và backpressure:

| Thiết kế | Ưu điểm | Rủi ro / điều kiện |
| --- | --- | --- |
| Queue trong RAM | Nhanh, giảm I/O | Mất khi process crash/restart; có thể hết heap |
| File spool / persistent queue | Có thể giữ qua restart khi cấu hình đúng | Disk đầy, permission, corruption, durability, vận hành phức tạp |
| Chặn producer khi queue đầy | Giảm drop nếu upstream chờ được | Logging có thể làm chậm hoặc kẹt request chính |
| Drop có kiểm soát | Bảo vệ ứng dụng chính | Phải thống kê lượng log mất và mức độ chấp nhận |
| Sampling / giảm verbosity | Giảm tải cho log chẩn đoán | Không phù hợp với mọi loại log, nhất là audit bắt buộc |
| Tách ưu tiên / kênh audit | Đảm bảo resource cho sự kiện quan trọng | Đòi thiết kế độc lập, policy và giám sát riêng |

**Bộ đệm vô hạn không phải giải pháp.** Khi collector lỗi lâu, queue trong RAM có thể làm JVM gặp OOM; queue trên đĩa có thể làm đầy filesystem, ảnh hưởng ứng dụng khác. Thiết kế phải có dung lượng/tuổi tối đa và hành động khi vượt ngưỡng.

Đối với dữ liệu bắt buộc phải giữ, phải quyết định ứng dụng sẽ **fail closed, block, đưa vào durable outbox hoặc báo lỗi rõ** khi không thể lưu. Với log chẩn đoán thông thường, bảo vệ availability của ứng dụng có thể quan trọng hơn việc chờ vô hạn. Cân bằng này cần quyết định rõ trong SLO/policy, không nên là tác dụng phụ không được biết của appender.

### Retry trong ứng dụng hay trong collector?

- **Appender/exporter trong Java:** thích hợp khi thư viện cung cấp queue, retry, circuit breaker hoặc persistent storage được kiểm thử. Đừng tự viết transport retry trong mọi call site.
- **Agent/log shipper tại host hoặc sidecar:** ứng dụng ghi stdout/file, agent chịu trách nhiệm đọc, buffer, retry và gửi. Ứng dụng không cần chờ network exporter trên mỗi request.
- **Collector tầng trung gian:** có thể nhận từ nhiều agent rồi retry tới kho downstream. Lúc này acknowledgment tại collector có thể chỉ xác nhận đã nhận vào hàng đợi trung gian.

**Chỉ định một tầng sở hữu retry cho mỗi hop**, đồng thời hiểu các tầng khác có thể cũng retry theo hop riêng. Nếu ứng dụng tự retry HTTP, agent lại retry và collector lại retry mà không có ngân sách chung, sẽ xảy ra **retry amplification**; mất kết nối nhỏ có thể tạo lượng request lớn hơn nhiều so với tải bình thường.

## 8. Trường hợp kết quả gửi không xác định và nguy cơ duplicate

Tình huống dễ hiểu sai:

~~~text
Exporter                       Collector
   |                               |
   | --- POST batch-42 ----------> |
   |                               | accepted batch
   |  X response lost / timeout    |
   |
   | --- POST batch-42 again ----> |
   |                               | duplicate possible
~~~

Nếu exporter timeout **sau khi** collector đã nhận batch, nó không có đủ thông tin để chắc lần đầu thất bại. Retry có thể tăng độ tin cậy của **at-least-once delivery**, nhưng cũng có thể tạo log trùng.

Chiến lược giảm trùng:

1. Gán `eventId` duy nhất cho từng event tại nguồn, hoặc `batchId` bền vững theo một tập event **cố định**.
2. Khi retry, **giữ nguyên ID** và nội dung batch tương ứng; không cấp ID mới cho cùng sự kiện chỉ vì retry.
3. Đích nhận cần cơ chế dedup/idempotency thực sự, có retention đủ cho cửa sổ retry, và phải xử lý race giữa các request trùng.
4. Dùng metadata `attempt`, `lastErrorCode`, `firstSeenAt` riêng cho việc vận chuyển; không biến mỗi lần retry thành event nghiệp vụ mới.
5. Xác minh bằng test mất ACK, timeout và restart để biết khi nào nhận trùng.

**Không gộp nhầm hai cấp trùng:** một event có thể được phát **hai lần từ Java** vì logger hierarchy/handler duplicate, trong khi một event khác chỉ được phát một lần nhưng **được exporter gửi lại**. Cần phân biệt nguồn duplication khi điều tra.

Nếu collector hỗ trợ **partial success**, không được tự động gửi lại toàn bộ batch mà không xét hợp đồng trả về. Có thể cần retry riêng các event chưa nhận hoặc chấp nhận nguy cơ trùng để bảo toàn dữ liệu theo policy.

## 9. Batch, thứ tự, giới hạn kích thước và retry

Log thường được gửi theo batch để giảm chi phí mạng. Nhưng batching thêm các câu hỏi:

- **Batch size:** quá lớn có thể gây `413`, tăng latency và memory; quá nhỏ tăng overhead.
- **Flush interval:** event có thể nằm trong queue chờ đủ số lượng; cần xác định khi nào flush.
- **Partial acknowledgment:** hệ thống nhận đã chấp nhận những event nào?
- **Ordering:** nếu batch 2 được gửi thành công trước batch 1 đang retry, log có thể đến kho theo thứ tự khác với thời điểm phát.
- **Compression:** phải thống nhất encoding, giới hạn size và xử lý lỗi giải nén.
- **Event boundaries:** với NDJSON, mỗi record phải là JSON hợp lệ; retry không phải dịp để ghép/truncate tùy ý.
- **Retention và mất mát:** khi queue hoặc spool chạm trần, batch nào bị xóa? Có đo drop count không?

**Không mặc định phải giữ thứ tự tuyệt đối của mọi log giữa nhiều thread, host hoặc service.** Dùng timestamp, event ID, request ID/trace ID và thông tin sequence nếu use case cần. Địa chỉ IP, process ID và timestamp đơn lẻ không đủ để chứng minh thứ tự toàn hệ thống.

Một event nhỏ bị lỗi vĩnh viễn có thể khiến **cả batch bị reject** nếu API chỉ trả “all or nothing”. Cần chính sách cách ly/bisect batch có kiểm soát hoặc giới hạn kích thước, nhưng không nên tự tách batch vô hạn mà không có giới hạn depth/attempt.

## 10. Quan sát vận chuyển: log, metrics và alert

Một hệ thống retry không thể vận hành chỉ bằng thông báo “retrying…” trên mỗi attempt. Nên có **metric** theo collector, outcome và reason code được chuẩn hóa:

| Tín hiệu | Cần trả lời |
| --- | --- |
| `export_attempts_total` | Bao nhiêu lần thực sự gọi transport |
| `export_success_total` | Bao nhiêu batch/event được ACK theo contract |
| `export_failures_total` | Lỗi transient, permanent, timeout phân loại thế nào |
| `export_retries_total` | Đã retry bao nhiêu lần, có dấu hiệu storm không |
| `queue_size` / `queue_bytes` | Bao nhiêu dữ liệu chưa gửi |
| `oldest_queued_age_seconds` | Event lâu nhất đang tồn đọng bao lâu |
| `dropped_events_total` | Đã mất bao nhiêu event theo chính sách overflow |
| `export_latency_seconds` | Thời gian mỗi lần gửi hoặc từ tạo đến ACK |
| `last_success_timestamp` | Bao lâu chưa gửi thành công |
| `partial_failure_total` | Có bao nhiêu response chấp nhận một phần |

Tên metric trong bảng là **ví dụ thiết kế**, không phải tên chuẩn được mọi exporter cung cấp.

### Chống “log storm” và vòng lặp lỗi

Nếu exporter gặp lỗi rồi dùng **chính cùng exporter đó** để gửi `logger.error("export failed")`, mỗi lỗi có thể tạo thêm log cần vận chuyển, từ đó thêm lỗi — một vòng lặp tự khuếch đại. Nên:

- Giới hạn tốc độ log nội bộ của exporter; tổng hợp lỗi theo khoảng thời gian.
- Dùng metric hoặc kênh diagnostic độc lập/ít phụ thuộc vào đích đang lỗi.
- Chỉ phát event khi **trạng thái chuyển đổi** (healthy → degraded, retrying → recovered, retry → exhausted) nếu có thể.
- Không thêm `messageId`/`batchId` làm label metric cho từng event vì cardinality quá lớn.
- Cảnh báo theo backlog/age/drop và thời gian mất kết nối, không chỉ theo một exception lẻ.

Ví dụ event chẩn đoán:

~~~text
event=log_export_retry_scheduled
destination=collector-primary
reasonCode=SERVICE_UNAVAILABLE
attempt=2 delayMs=500 queueSize=3200
~~~

Một event như vậy phục vụ điều tra, nhưng **không chứng minh lần retry đã chạy hoặc thành công**. Khi ACK thật sự nhận được, dùng event khác như `log_export_confirmed` và cập nhật metric phù hợp.

## 11. Shutdown, restart và việc giữ dữ liệu chưa gửi

Shutdown hook có thể giúp flush hoặc drain queue khi JVM **tắt có trật tự**, nhưng không bảo đảm khi nhận `SIGKILL`, process crash, host mất điện hoặc vượt grace period của container.

Với exporter cần giữ dữ liệu qua restart:

1. Xác định event đã nằm trong **RAM** hay đã được ghi vào **persistent queue**.
2. Kiểm tra chính sách fsync/durability và tình huống file spool bị hỏng/đầy.
3. Khi khởi động lại, xác định cách phục hồi và retry các batch chưa được ACK.
4. Không xóa checkpoint/offset trước khi điều kiện xác nhận của hop được đáp ứng.
5. Thêm event ID và xử lý duplicate vì crash có thể xảy ra sau ACK nhưng trước khi cập nhật checkpoint.
6. Có timeout/graceful shutdown cho worker nhưng không xem shutdown hook là phương án duy nhất.

**Tailing file có offset/checkpoint:** file shipper thường theo dõi vị trí đã đọc trong file. “Đã đọc tới offset X” khác “đã gửi/lưu thành công dữ liệu tới offset X”. Cần hiểu chính sách checkpoint và rotation/truncation của shipper để đánh giá mất hoặc trùng.

**Container stdout:** một ứng dụng viết stdout thành công chỉ chứng minh dữ liệu đã đến stream của container/runtime theo ngữ cảnh; log agent và collector vẫn có thể chậm, mất hoặc retry. Đối với audit yêu cầu bảo toàn mạnh, cần kiến trúc và xác nhận riêng.

## 12. Bảo mật và quyền riêng tư trong retry

Retry có thể làm tồn tại **nhiều bản sao của cùng log**: trong queue RAM, file spool, network buffer, collector tạm và kho cuối. Cần bảo vệ dữ liệu ở tất cả các chặng.

- **Không log payload trong thông báo lỗi vận chuyển.** HTTP response body có thể chứa dữ liệu nhạy cảm do proxy hoặc backend phản chiếu.
- Dùng `batchId`, `destinationCode`, `attempt`, `reasonCode` đã được kiểm soát thay vì dump toàn bộ NDJSON.
- Hạn chế log chứa access token, cookie, email, phone, IP hoặc ID cá nhân khi không có mục đích rõ.
- Bảo vệ file spool: quyền hệ điều hành, mã hóa phù hợp, hạn lưu, xử lý khi xóa hoặc disk đầy.
- Không gửi log nhạy cảm sang endpoint dự phòng ở khu vực hoặc bên thứ ba chưa được phép.
- Khi debug retry, không paste raw request/response vào ticket, chat hoặc alert không phù hợp quyền.
- Đảm bảo thư viện HTTP không vô tình ghi `Authorization` header hoặc query parameter vào stack trace.
- Kiểm tra TLS/certificate và cấu hình xác thực của collector; không bỏ xác thực TLS chỉ để “retry thành công”.
- Dữ liệu đã băm hoặc pseudonym vẫn có thể liên kết với cá nhân; cần retention và quyền truy cập.

**Thời gian retry tối đa cũng ảnh hưởng retention:** một batch được giữ trong spool thêm nhiều giờ hoặc ngày có thể tạo một kho dữ liệu thứ cấp. Retention trên collector không tự động áp dụng cho file spool ở agent.

## 13. Kiểm thử retry vận chuyển bằng fault injection

Trước khi đưa vào production, test không chỉ “kết nối thành công” mà cả đường lỗi.

| Kịch bản test | Điều cần kiểm tra |
| --- | --- |
| Collector trả `503` hai lần rồi `2xx` | Retry đúng số lần/delay, chỉ đánh dấu confirmed khi có ACK |
| Trả `429` kèm `Retry-After` | Áp chính sách chờ phù hợp, không tạo retry storm |
| Trả `400` do schema sai | Không retry vô hạn; có cách ly và metric |
| Network timeout sau khi server đã nhận | Kết quả UNKNOWN, dedup/at-least-once đúng kỳ vọng |
| Collector nhận một phần batch | Không âm thầm bỏ phần lỗi, không resend sai theo contract |
| Queue gần đầy khi collector down | Block/drop/spill theo policy; có metric, không OOM |
| Disk spool đầy hoặc không ghi được | Cảnh báo, phản ứng được định nghĩa; không nói “durable” khi chưa ghi |
| Kill process giữa gửi và ACK | Xác minh phục hồi, resend và nguy cơ duplicate |
| Restart khi có batch chưa ACK | Phục hồi checkpoint và giữ event ID |
| Multiple exporters cùng retry | Không đồng loạt tạo tải đột biến, jitter/cap có hiệu quả |
| Shutdown trong lúc queue còn dữ liệu | Graceful drain có giới hạn; xử lý phần còn lại rõ ràng |
| Authorization hoặc TLS sai | Không tự disable bảo mật, không retry nóng |
| Log exporter chính bị lỗi | Diagnostic/metric nội bộ không tạo vòng lặp log storm |
| Payload chứa secret test | Không xuất lại payload trong exception, spool/alert ngoài policy |

### Unit test chính sách (độc lập với network)

Ở ví dụ `LogTransportRetryDemo`, có thể test các tính chất:

- Với `RETRYABLE, RETRYABLE, ACKED`: đúng 3 lần gọi `Transport.send`, trả `DELIVERED`.
- Với `PERMANENT`: chỉ gọi 1 lần, trả `PERMANENT_FAILED`.
- Với bốn kết quả retryable/unknown: không vượt `MAX_ATTEMPTS=4`, trả `EXHAUSTED`.
- Delays: 250, 500, 1.000 ms và chạm trần 2.000 ms theo công thức.
- Batch ID được giữ **không đổi** qua mọi attempt.
- Không ghi raw payload trong event log, chỉ metadata đã được phê duyệt.

Đây là các yêu cầu kiểm thử gợi ý, **không phải tuyên bố đã chạy unit test trong một môi trường CI cụ thể**. Với HTTP exporter thật, nên có stub server có thể trả status, delay, mất kết nối và nhận trùng có chủ đích; kiểm tra các record ở collector test khi có thể.

## 14. Lỗi triển khai phổ biến

| Sai lầm | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| Retry ngay, không delay | Tăng tải đúng lúc collector quá tải | Backoff + jitter + cap |
| Retry mãi mọi HTTP `4xx` | Không sửa được payload/config, tiêu tốn tài nguyên | Phân loại permanent và xử lý riêng |
| Xem timeout luôn là thất bại chắc chắn | Có thể gửi trùng khi server đã nhận | Định nghĩa UNKNOWN, dedup/idempotency |
| Xem `2xx` là đã lưu bền cuối cùng | ACK có thể chỉ xác nhận tầng trung gian | Kiểm tra contract từng hop |
| Để queue trong RAM vô hạn | JVM OOM, tác động nghiệp vụ | Giới hạn queue, backpressure/drop/spool |
| Không giám sát drop và age | Mất log im lặng | Metrics, dashboard, alert |
| Mỗi lỗi export lại gửi log qua chính exporter đó | Log storm tự khuếch đại | Diagnostic độc lập, rate limit |
| Resend toàn bộ batch sau partial success | Duplicates hoặc số event sai | Xử lý response theo hợp đồng |
| Chỉ nhìn số lần `logger.info` | Không biết event có tới collector không | Đo ACK, backlog và end-to-end |
| Tạo batch ID mới ở mỗi retry | Receiver khó dedup cùng batch | ID ổn định cho cùng nội dung |
| Bỏ qua shutdown/restart | Mất queue hoặc gửi trùng ngoài ý muốn | Durable queue, checkpoint, idempotency |
| Retry authentication lỗi bằng cách tắt TLS | Mở rủi ro bảo mật | Sửa credential/cert theo quy trình |
| Giữ spool chứa PII không hạn lưu | Tạo kho dữ liệu thứ cấp | Phân quyền, mã hóa, retention |
| Dùng `Thread.sleep` ở request thread khi exporter lỗi | Làm request chậm và nghẽn thread | Executor/shipper tách biệt, backpressure có chủ đích |

## 15. Checklist vận hành

- [ ] Xác định hop nào sở hữu retry và ý nghĩa của ACK ở từng hop.
- [ ] Phân loại lỗi `ACKED / RETRYABLE / PERMANENT / UNKNOWN / PARTIAL` theo contract.
- [ ] Đặt timeout, max attempts, max retry age, backoff, jitter và `Retry-After`.
- [ ] Không retry nóng các lỗi schema/permission/config không thể tự hồi phục.
- [ ] Thiết kế queue/buffer có giới hạn và chính sách khi quá tải rõ ràng.
- [ ] Xác định queue RAM hay persistent, checkpoint, restart và graceful shutdown.
- [ ] Đảm bảo event/batch ID ổn định để hỗ trợ dedup khi resend.
- [ ] Xử lý partial success, batch quá lớn, duplicate và ordering khi cần.
- [ ] Theo dõi `queue_size`, age, retry, failures, drop và last success.
- [ ] Tránh log storm từ chính exporter; sử dụng diagnostic/metrics độc lập.
- [ ] Không đưa payload/token/PII vào log lỗi vận chuyển hoặc alert.
- [ ] Kiểm thử `429`, `503`, timeout sau ACK, crash, disk full, restart và receiver down.
- [ ] Phân biệt mức đảm bảo log chẩn đoán với audit/event cần lưu bền.
- [ ] Kiểm tra phiên bản/cấu hình thật của agent, collector và backend trước khi dựa vào retry tự động.

### Câu hỏi tự kiểm tra

**Câu 1.** `logger.info()` thành công có nghĩa log đã được collector nhận không?  
**Đáp:** Không. Event có thể mới nằm trong queue hoặc buffer cục bộ.

**Câu 2.** Exporter timeout sau khi gửi batch. Có thể chắc collector chưa nhận không?  
**Đáp:** Không. Đây là kết quả không xác định; resend có thể tạo trùng và cần policy dedup/idempotency.

**Câu 3.** Tại sao nên có jitter?  
**Đáp:** Để nhiều exporter không retry cùng lúc khi collector vừa phục hồi hoặc đang quá tải.

**Câu 4.** Khi collector trả `400` do JSON schema sai, có nên retry nguyên batch vô hạn?  
**Đáp:** Không. Cần phân loại lỗi permanent, cách ly và sửa payload hoặc schema.

**Câu 5.** `Retry-After` có nghĩa mọi exporter phải ngủ đúng giá trị đó không?  
**Đáp:** Không tuyệt đối. Phải đọc quy ước header của endpoint, diễn giải đúng định dạng, kết hợp với giới hạn an toàn và chính sách tải.

**Câu 6.** Vì sao persistent queue vẫn có thể tạo bản trùng?  
**Đáp:** Một lần gửi có thể đã được nhận, nhưng exporter chết trước khi ghi checkpoint/ACK cục bộ nên gửi lại sau restart.

**Câu 7.** Có nên cho mọi retry error gửi vào cùng kênh log đang bị lỗi không?  
**Đáp:** Không. Điều đó có thể sinh vòng lặp log storm; ưu tiên metric/kênh diagnostic ít phụ thuộc hơn.

**Ghi nhớ:** Retry vận chuyển giúp log vượt qua lỗi mạng hoặc đích nhận tạm thời, nhưng chỉ đáng tin khi đi kèm **phân loại kết quả, backoff/jitter, giới hạn retry, queue/backpressure, ACK rõ nghĩa, ID ổn định, xử lý duplicate và giám sát**. Nó không tự bảo đảm `exactly once` hay lưu bền ở đích cuối; phải xác định hợp đồng của từng hop trong pipeline logging.
