# Thử lại có giới hạn với backoff và jitter

Trong hệ thống Kafka, lỗi tạm thời có thể xuất hiện ở broker, network, database hoặc dịch vụ downstream. Một lần gọi thất bại chưa chắc có nghĩa thao tác không thể hoàn thành; nhưng thử lại liên tục ngay lập tức có thể làm dịch vụ đang quá tải càng khó phục hồi. Cách xử lý phổ biến là **bounded retry**: giới hạn số lần thử, tăng dần thời gian chờ bằng backoff và thêm jitter để các client không đồng loạt retry cùng lúc.

Retry cần được thiết kế cùng timeout, deadline, idempotency và chính sách xử lý lỗi cuối cùng. Kafka Producer đã có retry nội bộ; Kafka Consumer và Spring Kafka có các cơ chế retry/blocking retry hoặc retry topic. Bài viết phân biệt các tầng này, trình bày thuật toán backoff/jitter và cách đưa lỗi không thể phục hồi sang Dead Letter Topic (DLT).

## 1. Khi nào nên retry?

Retry phù hợp với lỗi có khả năng tự biến mất sau một khoảng thời gian ngắn, ví dụ:

- Network tạm thời mất kết nối hoặc connection reset.
- Broker đang bầu leader, partition tạm thời chưa có leader hoặc request bị throttle.
- Database từ chối kết nối trong thời gian ngắn hoặc deadlock có thể thử lại.
- HTTP service trả `429 Too Many Requests` hoặc `503 Service Unavailable`.
- Dịch vụ downstream có sự cố quá tải ngắn hạn và cung cấp thời điểm thử lại.

Không nên retry vô điều kiện mọi exception. Các lỗi sau thường cần sửa dữ liệu hoặc cấu hình thay vì thử lại cùng request:

- Payload sai schema, thiếu trường bắt buộc hoặc vi phạm validation.
- Không có quyền truy cập, credential sai hoặc ACL bị từ chối.
- Topic/partition không tồn tại do cấu hình sai.
- Business rule từ chối thao tác, ví dụ tài khoản bị khóa hoặc đơn hàng đã ở trạng thái không cho phép.
- Code gặp lỗi lập trình như `NullPointerException`.

Một số lỗi phụ thuộc ngữ cảnh: HTTP 404 có thể là lỗi vĩnh viễn, nhưng cũng có thể là eventual consistency khi tài nguyên vừa được tạo; lỗi database constraint thường không retry, còn deadlock có thể retry. Phân loại theo ý nghĩa nghiệp vụ và loại lỗi cụ thể, không chỉ theo lớp exception cha.

## 2. Giới hạn số lần thử và định nghĩa attempt

Một chính sách retry cần nói rõ số lần thử được tính như thế nào. Trong bài này, **`maxAttempts` là tổng số lần thực thi, bao gồm lần đầu**.

Ví dụ:

| `maxAttempts` | Lần đầu | Số lần retry tối đa |
|---:|---:|---:|
| 1 | 1 | 0 |
| 3 | 1 | 2 |
| 5 | 1 | 4 |

Một số framework đặt tên cấu hình theo `maxRetries`, nghĩa là số lần thử lại sau lần đầu. Cần kiểm tra semantics của API đang dùng để tránh cấu hình 5 retries nhưng tưởng chỉ có 5 lần thử tổng cộng.

Giới hạn số lần thử ngăn một message bị lặp vô hạn. Tuy nhiên, chỉ giới hạn số lần chưa đủ: nếu mỗi lần gọi có timeout dài, tổng thời gian xử lý vẫn có thể vượt SLA. Vì vậy, nên có cả:

- **Attempt limit:** số lần thực thi tối đa.
- **Per-attempt timeout:** thời gian tối đa cho từng lần gọi.
- **Total deadline:** thời hạn tổng cho toàn bộ thao tác, bao gồm thời gian chờ backoff.
- **Backoff cap:** thời gian chờ tối đa giữa hai lần thử.

Nếu downstream hỗ trợ header `Retry-After`, có thể tôn trọng gợi ý đó nhưng vẫn phải giới hạn bởi deadline và chính sách tối đa của ứng dụng.

## 3. Exponential backoff

Exponential backoff tăng dần thời gian chờ sau mỗi lần thất bại. Một công thức phổ biến là:

\[
d_n = \min(d_{max}, d_0 \times r^{n-1})
\]

Trong đó:

- `d0` là khoảng chờ ban đầu.
- `r` là hệ số tăng, thường từ 2 trở lên.
- `n` là số thứ tự lần retry.
- `dmax` là mức chờ tối đa (cap).

Ví dụ với `d0 = 200 ms`, `r = 2` và `dmax = 5 s`:

| Lần retry | Backoff trước jitter |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 | 3.200 ms |
| 6 trở đi | 5.000 ms |

Backoff cho downstream thời gian phục hồi và tránh tạo request mới liên tục. Nếu dùng fixed delay, mọi lần retry có cùng khoảng chờ; cách này dễ dự đoán nhưng có thể không đủ khi sự cố kéo dài.

## 4. Vì sao cần jitter?

Nếu hàng nghìn client cùng gặp lỗi tại một thời điểm và đều dùng backoff 1, 2, 4, 8 giây, chúng có thể retry đồng loạt theo từng đợt. Hiện tượng này gọi là *thundering herd*: khi dịch vụ vừa phục hồi, lượng request đồng bộ lại làm nó quá tải và tiếp tục lỗi.

**Jitter** thêm yếu tố ngẫu nhiên vào thời gian chờ để phân tán các lần retry theo thời gian. Một lựa chọn phổ biến là *full jitter*:

\[
sleep_n \sim U(0, d_n)
\]

Trong đó `U(0, d_n)` là giá trị ngẫu nhiên trong khoảng từ 0 tới backoff cap của lần retry đó.

Ví dụ, lần retry có backoff ceiling 800 ms thì mỗi client chọn ngẫu nhiên một thời gian từ 0 đến 800 ms. Các client sẽ không cùng gửi request tại một mốc cố định.

Các biến thể khác:

| Kiểu jitter | Cách chọn thời gian | Đặc điểm |
|---|---|---|
| Full jitter | Ngẫu nhiên từ 0 đến backoff ceiling | Phân tán mạnh, giảm đồng bộ retry |
| Equal jitter | Một nửa ceiling cộng phần ngẫu nhiên trong nửa còn lại | Giữ mức chờ tối thiểu, vẫn phân tán |
| Decorrelated jitter | Mức chờ mới phụ thuộc lần chờ trước và một khoảng ngẫu nhiên | Tránh chuỗi thời gian chờ đồng bộ, phân phối biến động hơn |

Không cần tự xây thuật toán phức tạp nếu thư viện đã cung cấp jitter phù hợp. Điều quan trọng là cap thời gian chờ, giới hạn tổng thời gian và đo kết quả dưới tải thực tế.

## 5. Retry budget và deadline

Retry làm tăng tải. Nếu 1.000 request ban đầu đều thất bại và mỗi request được thử thêm 5 lần, downstream có thể nhận tới 6.000 lần gọi cho cùng lượng công việc ban đầu. Khi dịch vụ đã quá tải, retry không giới hạn có thể tạo vòng lặp khuếch đại sự cố.

Một chính sách production nên có retry budget:

- Giới hạn số lần thử cho từng event/request.
- Giới hạn thời gian tổng cho một thao tác.
- Có thể giới hạn tỷ lệ retry trên tổng request trong một cửa sổ thời gian.
- Tạm ngừng hoặc giảm retry khi tỷ lệ lỗi vượt ngưỡng (circuit breaker/load shedding).
- Không retry đồng thời ở mọi tầng nếu tầng dưới đã tự retry.

Ví dụ, một HTTP call có deadline tổng 8 giây. Dù còn attempt, nếu thời gian còn lại không đủ cho backoff và một lần gọi có ý nghĩa, nên kết thúc sớm và chuyển sang xử lý lỗi. Timeout của từng lần gọi phải nhỏ hơn hoặc bằng thời gian còn lại.

## 6. Java: bounded exponential backoff với full jitter

Ví dụ sau minh họa retry một lời gọi downstream. `maxAttempts` bao gồm lần gọi đầu tiên; mỗi attempt nhận thời gian còn lại để đặt timeout cho HTTP/database client.

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.Predicate;

@FunctionalInterface
interface TimedCall<T> {
    T execute(Duration remainingTime) throws Exception;
}

public final class RetrySupport {

    public static <T> T execute(
            TimedCall<T> operation,
            Predicate<Exception> retryable,
            int maxAttempts,
            Duration initialBackoff,
            Duration maxBackoff,
            Duration totalTimeout) throws Exception {

        if (maxAttempts < 1 || initialBackoff.isNegative()
                || maxBackoff.isNegative() || totalTimeout.isNegative()
                || initialBackoff.compareTo(maxBackoff) > 0) {
            throw new IllegalArgumentException("Invalid retry policy");
        }

        long deadline = System.nanoTime() + totalTimeout.toNanos();
        long ceilingMs = initialBackoff.toMillis();
        long maxBackoffMs = maxBackoff.toMillis();

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            long remainingNanos = deadline - System.nanoTime();
            if (remainingNanos <= 0) {
                throw new TimeoutException("Retry deadline exceeded");
            }

            try {
                return operation.execute(Duration.ofNanos(remainingNanos));
            } catch (Exception ex) {
                if (!retryable.test(ex) || attempt == maxAttempts) {
                    throw ex;
                }

                remainingNanos = deadline - System.nanoTime();
                if (remainingNanos <= 0) {
                    throw new TimeoutException("Retry deadline exceeded");
                }

                long upperBoundMs = Math.min(ceilingMs, maxBackoffMs);
                long delayMs = upperBoundMs == 0
                        ? 0
                        : ThreadLocalRandom.current().nextLong(upperBoundMs + 1);
                long delayNanos = TimeUnit.MILLISECONDS.toNanos(delayMs);
                long sleepNanos = Math.min(delayNanos, remainingNanos);

                try {
                    TimeUnit.NANOSECONDS.sleep(sleepNanos);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw interrupted;
                }

                ceilingMs = ceilingMs >= maxBackoffMs / 2
                        ? maxBackoffMs
                        : Math.min(maxBackoffMs, ceilingMs * 2);
            }
        }

        throw new IllegalStateException("Retry loop ended unexpectedly");
    }
}
```

Ví dụ gọi:

```java
String result = RetrySupport.execute(
        remaining -> paymentClient.authorize(
                request,
                remaining), // client phải áp dụng timeout này
        ex -> ex instanceof java.net.SocketTimeoutException
                || ex instanceof java.net.ConnectException,
        4,                         // tổng 4 attempts: 1 lần đầu + tối đa 3 retries
        Duration.ofMillis(200),
        Duration.ofSeconds(3),
        Duration.ofSeconds(8));
```

Đây là helper minh họa; `paymentClient.authorize` cần là API do ứng dụng triển khai và phải thực sự áp dụng timeout được truyền vào. Nếu thư viện downstream bỏ qua timeout, deadline bên ngoài không thể tự dừng một lời gọi đang block. Trong code production cần bổ sung metric attempt, log có correlation/event ID, kiểm tra overflow cho các duration cực lớn và phân loại exception theo API thực tế.

Không bắt `Throwable` để retry. Các lỗi như `OutOfMemoryError`, `StackOverflowError` hoặc lỗi runtime nghiêm trọng không nên được xử lý bằng retry thông thường. Khi thread bị interrupt, cần khôi phục interrupt flag và kết thúc thay vì tiếp tục retry.

## 7. Idempotency trước khi retry side effect

Retry có thể khiến cùng một thao tác được gửi nhiều lần. Với timeout, client đôi khi không biết server đã thực hiện thao tác hay chưa. Ví dụ payment API đã trừ tiền nhưng phản hồi bị mất; gửi lại request không có idempotency có thể trừ tiền lần hai.

Trước khi retry side effect, cần có một trong các bảo vệ sau:

- Idempotency key ổn định, ví dụ `eventId` hoặc `paymentCommandId`, được hệ thống đích lưu và kiểm tra.
- Unique constraint hoặc inbox table để ngăn áp dụng cùng event nhiều lần.
- Upsert theo entity version hoặc sequence để từ chối cập nhật cũ.
- Transactional outbox/inbox cho giao tiếp giữa các dịch vụ.

Không sinh idempotency key mới cho mỗi attempt. Tất cả lần thử của cùng một thao tác phải dùng cùng key để hệ thống đích nhận ra đó là cùng một yêu cầu.

## 8. Kafka Producer đã có retry nội bộ

Kafka Java Producer tự xử lý retry cho các lỗi có thể thử lại. Một số cấu hình quan trọng:

| Cấu hình | Vai trò |
|---|---|
| `retries` | Số lần producer có thể retry request lỗi; giá trị hiệu lực phụ thuộc client version và cấu hình khác |
| `delivery.timeout.ms` | Giới hạn tổng thời gian producer cố gắng gửi record, bao gồm chờ batch, request và retry |
| `request.timeout.ms` | Thời gian chờ phản hồi cho một request riêng lẻ |
| `enable.idempotence` | Bảo vệ khỏi duplicate do retry trong phạm vi producer session và bảo đảm thứ tự batch theo điều kiện Kafka hỗ trợ |
| `acks` | Mức xác nhận producer yêu cầu từ broker |

Ví dụ cấu hình producer:

```properties
acks=all
enable.idempotence=true
retries=2147483647
delivery.timeout.ms=120000
request.timeout.ms=30000
max.in.flight.requests.per.connection=5
```

Giá trị trên chỉ minh họa một cấu hình có retry và idempotence; cần kiểm tra tương thích theo Kafka client version. `delivery.timeout.ms` là giới hạn tổng quan trọng: đặt `retries` rất lớn không có nghĩa producer thử vô hạn. Khi hết delivery timeout, callback/future báo lỗi.

### Không bọc retry ứng dụng quanh `send()` một cách máy móc

Nếu producer `send()` đã thất bại hoặc timeout, ứng dụng có thể không biết chắc broker đã append record hay phản hồi bị mất. Gọi `send()` lại như một thao tác mới có thể tạo duplicate; idempotent producer không tự deduplicate hai lần `send()` độc lập chỉ vì payload giống nhau.

Ưu tiên để Kafka Producer quản lý retry request nội bộ. Nếu ứng dụng cần phát lại ở tầng nghiệp vụ, giữ nguyên event ID và dùng consumer deduplication/idempotency ở phía nhận. Không block bằng `Future.get()` rồi gửi lại không giới hạn mỗi khi timeout.

## 9. Kafka Consumer: blocking retry và retry topic

Consumer có hai chiến lược phổ biến khi xử lý record lỗi:

### Blocking retry

Consumer/container giữ record đang lỗi và thử lại sau backoff trước khi tiếp tục xử lý luồng. Cách này giữ thứ tự trong partition tốt hơn vì record sau thường phải chờ record trước được xử lý hoặc recover.

Đánh đổi:

- Partition có thể bị chặn trong thời gian retry.
- Consumer throughput giảm nếu lỗi kéo dài.
- Tổng thời gian retry phải phù hợp với `max.poll.interval.ms` và cách container quản lý poll/pause.
- Một poison message không thể xử lý có thể chặn các record sau nếu không có giới hạn và recoverer.

### Retry topic (non-blocking retry)

Consumer chuyển record lỗi sang retry topic với thời điểm xử lý lại, rồi tiếp tục record tiếp theo ở topic gốc. Cách này tránh giữ partition gốc trong thời gian chờ dài, nhưng có thể làm thay đổi ordering: record N thất bại được đưa sang retry topic trong khi record N+1 ở topic gốc đã được xử lý trước.

Retry topic phù hợp khi:

- Có thể chấp nhận eventual ordering hoặc xử lý theo version/sequence.
- Thời gian chờ retry dài hơn ngân sách poll.
- Muốn tách tải retry khỏi luồng chính.

Nếu nghiệp vụ bắt buộc ordering nghiêm ngặt theo key, cần cân nhắc blocking retry hoặc thiết kế sequence/version và consumer có thể phát hiện dữ liệu đến sai thứ tự. Không bật non-blocking retry chỉ vì cấu hình dễ hơn.

## 10. Spring Kafka: `DefaultErrorHandler` với exponential backoff

Với Spring Kafka, `DefaultErrorHandler` có thể cấu hình blocking retry và recoverer. Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.ExponentialBackOffWithMaxRetries;
import org.springframework.kafka.support.serializer.DeserializationException;

@Bean
DefaultErrorHandler kafkaErrorHandler(KafkaTemplate<Object, Object> template) {
    var recoverer = new DeadLetterPublishingRecoverer(template);

    // 4 retries sau lần xử lý đầu tiên = tối đa 5 attempts.
    var backOff = new ExponentialBackOffWithMaxRetries(4);
    backOff.setInitialInterval(1_000L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(10_000L);

    var handler = new DefaultErrorHandler(recoverer, backOff);
    handler.addNotRetryableExceptions(
            IllegalArgumentException.class,
            DeserializationException.class);

    return handler;
}
```

Ví dụ dùng exponential backoff có giới hạn và gửi record sang DLT sau khi hết retry. `ExponentialBackOffWithMaxRetries(4)` nghĩa là bốn lần retry sau lần xử lý ban đầu. Các class/package và cấu hình có thể khác theo phiên bản Spring Kafka; hãy xác nhận API trong phiên bản dự án.

Với `DeadLetterPublishingRecoverer` mặc định, đích thường là topic gốc cộng hậu tố `.DLT` và giữ partition tương ứng. Topic DLT cần được tạo với số partition phù hợp; nếu không, cấu hình destination resolver tường minh. Cần cấu hình serializer/deserializer của `KafkaTemplate` để có thể publish cả key, value và header của record lỗi.

### Phân loại exception

Chỉ retry lỗi có khả năng phục hồi. Các lỗi deserialize hoặc validation thường nên được phân loại non-retryable và đưa thẳng tới DLT/quy trình xử lý riêng. Không retry lỗi schema sai hàng trăm lần vì dữ liệu không tự trở nên hợp lệ sau vài giây.

Recoverer chỉ nên xem record đã được recover khi việc publish DLT thành công. Nếu publish DLT thất bại, cần để lỗi được quan sát và xử lý theo cấu hình error handler, tránh âm thầm bỏ qua record.

## 11. Spring Kafka: retry topic với `@RetryableTopic`

Với retry không chặn luồng chính, Spring Kafka hỗ trợ `@RetryableTopic`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @RetryableTopic(
            attempts = "4", // tổng số lần xử lý, gồm lần đầu
            backoff = @Backoff(
                    delay = 1_000,
                    multiplier = 2.0,
                    maxDelay = 10_000))
    @KafkaListener(topics = "orders.events", groupId = "order-handler")
    public void listen(OrderEvent event) {
        orderService.process(event);
    }
}
```

Trong ví dụ, `attempts="4"` là tổng bốn lần xử lý (một lần đầu và tối đa ba lần trên retry topic), khác với constructor `ExponentialBackOffWithMaxRetries(4)` ở ví dụ trước. Cần đọc đúng semantics của annotation ở phiên bản Spring Kafka đang dùng.

Retry topic tạo thêm topic và luồng chuyển tiếp. Cần xác định suffix, số partition, replication factor, retention, consumer group, DLT và cách khôi phục record. Non-blocking retry có thể làm event sau được xử lý trước event đang chờ retry; bảo vệ ordering bằng key/sequence/version nếu nghiệp vụ cần.

## 12. DLT: kết thúc retry có kiểm soát

Dead Letter Topic (DLT) là nơi lưu record không thể xử lý sau khi đã hết retry hoặc gặp lỗi được phân loại không retry. DLT giúp luồng chính tiếp tục và giữ lại dữ liệu để điều tra hoặc replay có kiểm soát.

Một record DLT nên giữ:

- Original topic, partition và offset.
- Event ID/correlation ID nếu có.
- Exception class và thông tin lỗi đã được làm sạch.
- Timestamp lần xử lý lỗi cuối.
- Số attempt hoặc retry history nếu framework cung cấp.
- Payload gốc và headers cần thiết, tuân thủ chính sách bảo vệ dữ liệu.

Không nên đưa credential, token hoặc thông tin cá nhân nhạy cảm vào exception header/log. DLT cần có owner, retention, cảnh báo, quy trình điều tra và replay; nếu không, nó chỉ trở thành nơi chứa lỗi không ai xử lý.

Replay từ DLT phải có kiểm soát. Trước khi gửi lại, xác định nguyên nhân đã được sửa, giữ event ID ổn định và bảo đảm consumer downstream idempotent. Tránh replay hàng loạt khi lỗi gốc vẫn tồn tại vì có thể tạo thêm một đợt quá tải.

## 13. Retry và ordering

Retry có thể thay đổi thứ tự quan sát record tùy chiến lược:

| Chiến lược | Ordering trong partition gốc | Tác động |
|---|---|---|
| Blocking retry | Thường giữ thứ tự vì record lỗi chặn record sau | Giảm throughput partition trong lúc chờ |
| Retry topic | Có thể đảo thứ tự giữa record đang retry và record mới | Luồng chính tiếp tục, cần sequence/version nếu phải khôi phục thứ tự |
| Producer retry nội bộ với idempotence | Kafka bảo vệ thứ tự batch trong điều kiện cấu hình hỗ trợ | Không thay thế ordering giữa nhiều producer hoặc nhiều partition |
| Application republish | Phụ thuộc key, partition và thời điểm gửi lại | Có thể tạo duplicate hoặc đưa event cũ xuống sau event mới |

Nếu ordering theo entity là bắt buộc, dùng key ổn định để các event của entity vào cùng partition, giữ thứ tự gửi và tránh retry topic làm vượt qua event trước. Nếu dùng retry topic, có thể lưu sequence number và chỉ áp dụng event khi version kế tiếp hợp lệ; event đến sớm cần được buffer hoặc chờ predecessor.

## 14. Tránh retry lồng nhau và khuếch đại tải

Một request có thể đi qua nhiều tầng:

```text
Kafka consumer
  -> Spring retry
      -> service retry
          -> HTTP client retry
              -> downstream retry
```

Nếu mỗi tầng thử lại 3 lần, một event có thể tạo số request lớn hơn nhiều so với dự kiến. Hãy chọn một tầng sở hữu retry chính, các tầng khác có timeout rõ ràng và chỉ retry lỗi mà tầng đó hiểu.

Nguyên tắc:

- Xác định tổng deadline xuyên suốt các tầng.
- Tránh mỗi tầng tự áp dụng số lần retry độc lập.
- Dùng exponential backoff có cap và jitter ở client gọi dịch vụ.
- Tôn trọng `Retry-After` nhưng không vượt deadline.
- Có circuit breaker hoặc load shedding khi downstream liên tục lỗi.
- Giới hạn số record trong retry topic và tốc độ replay.
- Theo dõi retry rate, DLT rate và số lần gọi downstream trên mỗi event.

## 15. Theo dõi và vận hành retry

Các chỉ số nên có:

| Metric | Ý nghĩa |
|---|---|
| `retry_attempts_total` | Tổng số attempt bổ sung sau lần đầu |
| `retry_exhausted_total` | Số thao tác hết retry/deadline |
| `retry_delay_seconds` | Phân bố thời gian chờ giữa các lần thử |
| `retry_success_total` | Số thao tác thành công sau retry |
| `dlt_records_total` | Số record được chuyển tới DLT |
| `downstream_error_rate` | Tỷ lệ lỗi dịch vụ đang được retry |
| `consumer_lag` | Lag của consumer group trong lúc retry |
| `retry_queue_age` | Tuổi record đang chờ trong retry topic |

Log nên có event ID, topic, partition, offset, attempt hiện tại, max attempts, exception class, delay và deadline còn lại. Dùng correlation ID để nối các log qua dịch vụ. Tránh log toàn bộ payload hoặc secret.

Một đợt retry tăng nhanh cùng downstream latency tăng là dấu hiệu hệ thống đang khuếch đại tải. Cần giảm tốc độ, mở circuit breaker hoặc tạm dừng luồng phụ thuộc thay vì tăng số retry.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Retry không dừng | Không đặt attempt limit hoặc exception bị phân loại retryable quá rộng | Đặt `maxAttempts`, deadline và danh sách lỗi retry rõ ràng |
| Nhiều client retry cùng thời điểm | Dùng backoff cố định hoặc exponential không jitter | Thêm full/equal jitter và cap |
| Downstream càng retry càng quá tải | Retry budget quá lớn hoặc retry lồng nhau | Giới hạn tỷ lệ retry, deadline, circuit breaker và một tầng retry chính |
| Payment bị thực hiện hai lần | Retry thao tác không idempotent sau timeout mơ hồ | Dùng idempotency key ổn định và dedup ở hệ thống đích |
| Kafka Producer gửi duplicate | Ứng dụng gọi `send()` mới sau lỗi không rõ kết quả | Dùng producer retry nội bộ/idempotence; giữ event ID nếu republish ở tầng nghiệp vụ |
| Consumer partition bị chặn lâu | Blocking retry kéo dài hoặc poison message | Giới hạn retry/backoff, recover sang DLT hoặc dùng retry topic khi ordering cho phép |
| Event sau được xử lý trước event lỗi | Non-blocking retry đưa event lỗi sang topic khác | Dùng blocking retry hoặc sequence/version để kiểm soát ordering |
| DLT publish thất bại | Topic đích thiếu partition, serializer sai hoặc broker lỗi | Kiểm tra DLT topology, serializer, ACL và không đánh dấu recover thành công khi publish thất bại |
| Record DLT không được xử lý | Không có owner, alert hoặc quy trình replay | Thiết lập dashboard, retention, runbook và replay có kiểm soát |

## 17. Checklist thiết kế bounded retry

- Phân loại rõ lỗi transient, permanent và lỗi cần điều tra.
- Định nghĩa `maxAttempts` là tổng lần thử hay số retries sau lần đầu.
- Đặt per-attempt timeout và total deadline.
- Dùng exponential backoff có cap khi sự cố có thể kéo dài.
- Thêm jitter để phân tán retry giữa nhiều client.
- Tôn trọng `Retry-After` nhưng vẫn giữ retry budget.
- Chỉ retry side effect khi có idempotency key hoặc cơ chế dedup phù hợp.
- Với Kafka Producer, ưu tiên retry nội bộ và `delivery.timeout.ms`; tránh application retry mù.
- Với Kafka Consumer, chọn blocking retry hay retry topic theo yêu cầu ordering và poll interval.
- Phân loại exception non-retryable và cấu hình DLT/recoverer.
- Không retry lồng nhau ở mọi tầng.
- Theo dõi attempt, delay, retry success/exhausted, consumer lag và DLT.
- Có runbook sửa nguyên nhân và replay DLT an toàn.
- Kiểm thử outage, timeout mơ hồ, poison message và downstream phục hồi trong staging.

## 18. Ghi nhớ

Bounded retry cần giới hạn số lần thử và thời gian tổng. Exponential backoff tăng khoảng chờ theo cấp số nhân; jitter phân tán thời điểm retry để tránh thundering herd. Retry chỉ dành cho lỗi có khả năng phục hồi và side effect phải idempotent vì timeout không luôn cho biết thao tác đã xảy ra hay chưa.

Kafka Producer đã có retry nội bộ được kiểm soát bởi `delivery.timeout.ms` và idempotence. Kafka Consumer cần chọn blocking retry hoặc retry topic theo yêu cầu ordering; lỗi hết retry nên được recover vào DLT có quy trình xử lý rõ ràng. Kết hợp attempt limit, deadline, backoff cap, jitter, retry budget và quan sát vận hành giúp hệ thống phục hồi lỗi tạm thời mà không khuếch đại sự cố.
