# Quan sát retry, redelivery, timeout và tỷ lệ lỗi trong Spring Messaging

Quan sát một luồng message cần trả lời được bốn câu hỏi: message đã được giao bao nhiêu lần, ứng dụng đã thử xử lý bao nhiêu lần, thao tác nào hết thời gian chờ, và cuối cùng bao nhiêu message thất bại sau khi đã dùng hết chính sách phục hồi. Bốn tín hiệu này liên quan với nhau nhưng không đồng nghĩa.

Điểm quan trọng là phân biệt **retry của ứng dụng**, **redelivery của broker**, **timeout ở một ranh giới cụ thể** và **lỗi cuối cùng của một message nghiệp vụ**. Nếu gộp tất cả thành một bộ đếm exception, dashboard có thể báo sai: một message lỗi ba lần rồi thành công không phải là một message nghiệp vụ thất bại.

## 1. Phân biệt các khái niệm

| Khái niệm | Điều gì xảy ra? | Nơi thường quan sát |
| --- | --- | --- |
| Retry | Ứng dụng hoặc framework gọi lại cùng thao tác sau một lần thất bại | Retry advice, retry template, reactive pipeline hoặc code của handler |
| Redelivery | Message được nguồn giao nhận/broker gửi lại sau khi bị reject, nack, rollback, mất acknowledgement hoặc consumer phục hồi | Broker, listener container và metadata/header của message |
| Timeout | Một thao tác chờ quá thời hạn đã cấu hình và kết thúc bằng kết quả timeout | Channel send/receive, request-reply, client, handler hoặc broker policy |
| Error/failure | Một lần xử lý hoặc toàn bộ message nghiệp vụ kết thúc không thành công | Handler, error flow, terminal result hoặc dead-letter queue |

**Retry không nhất thiết là redelivery.** Stateless retry có thể chạy lại handler ngay trong cùng lần nhận message; broker không cần gửi message lần nữa. Ngược lại, redelivery có thể xảy ra khi consumer chết trước khi ACK, kể cả khi ứng dụng không có retry loop.

**Một message có thể vừa redelivery vừa retry.** Ví dụ broker giao lại message sau một lần consumer restart; lần nhận mới này lại retry nội bộ thêm hai lần. Nếu chỉ đếm exception, ta không biết message đã được broker giao lại hay ứng dụng đã gọi handler nhiều lần.

**Timeout không chứng minh thao tác chưa xảy ra.** Producer có thể đã gửi message, consumer có thể đã commit database, nhưng response hoặc acknowledgement bị trễ/mất. Khi client timeout rồi retry, side effect có thể bị thực hiện hai lần nếu thiếu idempotency.

## 2. Mô hình đếm: delivery, attempt và kết quả cuối

Đặt tên rõ cho từng đơn vị đo:

- **Logical message:** một yêu cầu nghiệp vụ duy nhất, được nhận diện bằng `messageId` hoặc `eventId` ổn định.
- **Delivery:** một lần nguồn gửi message tới consumer. Một logical message có thể có nhiều delivery do redelivery.
- **Attempt:** một lần handler thực sự được gọi để xử lý message. Một delivery có thể có nhiều attempt nếu dùng retry nội bộ.
- **Terminal outcome:** kết quả cuối của logical message sau khi hoàn tất hoặc hết retry/recovery policy. Chỉ ghi một lần cho mỗi logical message.

Ví dụ: broker giao `order-42` hai lần; ở delivery thứ hai, handler được gọi ba lần rồi thành công. Số liệu đúng là 2 deliveries, 1 redelivery, 3 attempts trong delivery thứ hai (cộng với attempts của delivery đầu nếu có), và 1 terminal success. Không được ghi ba terminal failures chỉ vì có ba exception trước khi thành công.

```text
Logical message: evt-42
  Delivery #1: consumer chết trước ACK
  Delivery #2:
    Attempt #1 -> lỗi tạm thời
    Attempt #2 -> timeout
    Attempt #3 -> thành công
  Terminal outcome -> SUCCESS
```

Để nối các mốc này, log/trace nên mang `messageId`, `correlationId`, destination, attempt number, redelivery flag, outcome và trace id. Những giá trị định danh riêng lẻ này phù hợp với log hoặc trace; không nên dùng chúng làm metric tag vì số lượng giá trị không giới hạn.

## 3. Chỉ số nên thu thập

| Metric | Loại | Cách đếm hoặc đo | Mục đích |
| --- | --- | --- | --- |
| `messaging.deliveries` | Counter | Mỗi lần consumer nhận một delivery | Đo lượng message đi vào consumer |
| `messaging.redeliveries` | Counter | Mỗi delivery được đánh dấu là redelivered theo broker/adapter | Phát hiện requeue, restart hoặc ACK có vấn đề |
| `messaging.attempts` | Counter | Mỗi lần handler bắt đầu xử lý | Đo tổng số lần thực thi |
| `messaging.retries` | Counter | Mỗi attempt bổ sung sau attempt đầu | Đo retry do ứng dụng/framework khởi tạo |
| `messaging.timeouts` | Counter | Mỗi lần một thao tác kết thúc vì timeout | Phân biệt timeout với exception khác |
| `messaging.messages.completed` | Counter | Một lần cho mỗi logical message đạt terminal outcome | Đếm số message cuối cùng thành công/thất bại |
| `messaging.handler.duration` | Timer | Thời gian mỗi lần handler chạy, gắn outcome | Theo dõi latency, count, total time và phân phối |
| `messaging.retry.delay` | Timer | Thời gian chờ giữa các lần retry | Kiểm tra backoff có hoạt động đúng |
| `messaging.queue.depth` | Gauge | Số message đang chờ tại một thời điểm | Theo dõi backlog và sức chứa |
| `messaging.oldest.message.age` | Gauge | Tuổi của message cũ nhất chưa xử lý | Phát hiện queue bị tắc dù throughput vẫn có |

Ngoài các metric trên, theo dõi số message unacked/in-flight, số consumer hoạt động, consumer lag, dead-letter count, số lần ACK/NACK, circuit breaker state, thread pool active/rejected. Các metric broker phải lấy từ broker hoặc adapter tương ứng; `spring-messaging` không có API chung để đọc mọi redelivery counter của mọi broker.

## 4. Tính tỷ lệ lỗi đúng mẫu số

Không có một “error rate” duy nhất. Cần xác định mẫu số đang đếm attempt hay logical message:

\[
\text{Attempt failure rate} = \frac{\text{failed attempts}}{\text{total attempts}} \times 100\%
\]

\[
\text{Terminal message failure rate} = \frac{\text{terminal failed messages}}{\text{terminal completed messages}} \times 100\%
\]

\[
\text{Redelivery rate} = \frac{\text{redelivered deliveries}}{\text{total deliveries}} \times 100\%
\]

\[
\text{Timeout rate} = \frac{\text{timed-out operations}}{\text{all operations subject to the timeout}} \times 100\%
\]

Có thể tính thêm retry ratio bằng `retry attempts / total attempts`, hoặc `retry attempts / initial logical deliveries`, nhưng phải đặt tên metric và dashboard theo đúng định nghĩa đã chọn.

Ví dụ: 100 logical message được nhận, mỗi message có một attempt ban đầu. 20 attempt ban đầu thất bại tạm thời và đều được retry đúng một lần; 18 retry thành công, 2 retry thất bại cuối cùng. Tổng cộng có 120 attempts (100 lần đầu + 20 lần retry), trong đó 22 attempts thất bại (20 lần đầu + 2 lần retry cuối). Attempt failure rate = 22 / 120 ≈ 18,3%; terminal message failure rate = 2 / 100 = 2%; redelivery rate = 20 / 120 ≈ 16,7% nếu tổng deliveries bao gồm cả lần giao đầu và các lần giao lại.

Chỉ tính terminal failure khi message đã đi đến kết quả cuối, không đưa message còn đang retry hoặc đang chờ vào mẫu số terminal. Với dashboard theo thời gian, dùng `rate()` của counter trong một cửa sổ thời gian thay vì so sánh tổng tích lũy từ lúc process khởi động.

Ví dụ Prometheus nếu metric `messaging.attempts` được export thành `messaging_attempts_total` và có tag `outcome`:

```promql
sum(rate(messaging_attempts_total{outcome="failure"}[5m]))
/
clamp_min(sum(rate(messaging_attempts_total[5m])), 1e-9)
```

`1e-9` là epsilon rất nhỏ để tránh chia cho 0 mà không nâng mẫu số lên 1 khi lưu lượng thấp. Khi không có traffic trong cửa sổ, dashboard nên thể hiện trạng thái không có dữ liệu thay vì diễn giải thành tỷ lệ 0%.

Đối với terminal error rate, dùng một counter khác chỉ tăng đúng một lần cho mỗi logical message hoàn tất, ví dụ `messaging_messages_completed_total{outcome="failure"}` chia cho tổng outcome success và failure. Không dùng attempt counter làm mẫu số cho terminal error rate.

## 5. Micrometer: Counter, Timer, Gauge và Observation

Spring sử dụng Micrometer để cung cấp abstraction trung lập với monitoring backend. Các meter thường dùng:

- `Counter`: đếm số sự kiện tích lũy, chẳng hạn attempt lỗi, retry, redelivery hoặc timeout. Counter chỉ tăng; khi làm dashboard nên xem tốc độ tăng trong một khoảng thời gian.
- `Timer`: đo thời lượng và số lần thực hiện. Timer đã chứa count và total time; tùy registry còn có max, histogram, percentile hoặc SLO bucket. Dùng Timer cho latency thay vì tự tạo một Counter thời gian.
- `Gauge`: đo giá trị tại thời điểm đọc, chẳng hạn queue depth, số message in-flight hoặc số slot consumer đang dùng.
- `Observation`: abstraction kết hợp metrics và tracing. Observation có thể tạo timer/counter và span khi registry được cấu hình handler phù hợp.

### 5.1. Spring Framework cung cấp những observation nào?

Trong tài liệu observability của Spring Framework 7, các observation liên quan trực tiếp đến messaging gồm `jms.message.publish` (thời gian gửi JMS message tới destination) và `jms.message.process` (thời gian ứng dụng xử lý message đã nhận). Tích hợp JMS dùng Micrometer Jakarta JMS instrumentation; cần dependency `io.micrometer:micrometer-jakarta9` và cấu hình `ObservationRegistry` trên `JmsTemplate` hoặc listener container factory tương ứng.

Spring Framework không tự động tạo một bộ metric retry, redelivery, timeout và terminal error đầy đủ cho mọi `MessageChannel`, STOMP endpoint, RSocket handler hoặc broker. Với các boundary chưa có instrumentation sẵn, thêm metric/observation ở producer, handler, retry policy và adapter.

### 5.2. Spring Integration có metric cho channel và handler

Đây là khả năng của **Spring Integration**, một module riêng dùng chung abstraction `spring-messaging`. Khi có `MeterRegistry`, Spring Integration đăng ký timer cho phần lớn `AbstractMessageChannel` và `AbstractMessageHandler`, counter cho `AbstractMessageSource`. Một số meter phổ biến:

| Meter | Tags chính | Ý nghĩa |
| --- | --- | --- |
| `spring.integration.send` với `type=channel` | `name`, `result`, `exception` | Thời gian gửi qua channel |
| `spring.integration.send` với `type=handler` | `name`, `result`, `exception` | Thời gian xử lý handler |
| `spring.integration.receive` với `type=channel` hoặc `type=source` | `name`, `result`, `exception` | Số lần nhận message |
| `spring.integration.channel.queue.size` | `name` | Queue size của `QueueChannel` |
| `spring.integration.channel.queue.remaining.capacity` | `name` | Dung lượng còn lại của `QueueChannel` |

Với Spring Integration 6.0 trở lên, Observation API hỗ trợ cả metrics và tracing. Cần có `ObservationRegistry` và cấu hình `@EnableIntegrationManagement`; mặc định không component nào được instrument chỉ vì registry đã tồn tại. Dùng `observationPatterns` để chọn component cần theo dõi, ví dụ `*` cho toàn bộ component hoặc pattern cụ thể để giới hạn phạm vi.

```java
@Configuration
@EnableIntegrationManagement(observationPatterns = "*")
public class IntegrationObservabilityConfiguration {
    // ObservationRegistry và MeterRegistry được cung cấp trong ApplicationContext.
}
```

Đoạn cấu hình trên bật observation cho các component Spring Integration khớp pattern. Nếu chỉ muốn metrics truyền thống, MeterRegistry có thể kích hoạt các meter của channel/handler mà không cần bật Observation tracing.

### 5.3. Spring Boot Actuator và nơi xem metric

Spring Boot tự cấu hình composite `MeterRegistry` khi registry exporter tương ứng có trên classpath. Ví dụ thêm Prometheus registry để export metrics cho Prometheus; cấu hình expose endpoint `prometheus` nếu cần scrape. `/actuator/metrics` hữu ích để kiểm tra tên meter và giá trị hiện có trong lúc chẩn đoán; đây không phải endpoint để monitoring backend scrape liên tục trong production. Dùng endpoint/exporter dành cho backend như `/actuator/prometheus` khi được bật.

## 6. Đo retry và redelivery ở đúng nơi

### 6.1. Retry nội bộ ứng dụng

Retry nội bộ xảy ra khi policy gọi lại handler hoặc thao tác downstream. Tăng `messaging.retries` khi bắt đầu mỗi lần thử bổ sung; tăng `messaging.attempts` mỗi khi handler thực sự bắt đầu. Nếu retry thành công, terminal outcome vẫn là success.

Spring Integration cung cấp `RequestHandlerRetryAdvice`, dựa trên `RetryTemplate`, để cấu hình `RetryPolicy` và `RecoveryCallback` cho handler. Stateless retry thực hiện các lần thử ngay trong advice. Stateful retry giữ retry state, ném exception trở lại caller và chờ message originator gửi lại; ví dụ originator có thể là broker hỗ trợ NACK/redelivery hoặc consumer có khả năng resubmit. Vì vậy stateful retry có thể đi kèm redelivery từ upstream.

Đừng mặc định mọi `RuntimeException` đều đáng retry. Lỗi validation, schema sai, thiếu quyền hoặc lỗi nghiệp vụ không tự biến mất khi gọi lại. Retry nên giới hạn số lần, có backoff và chỉ áp dụng cho lỗi tạm thời. Nếu nhiều tầng cùng retry (client, service, broker, handler), số lần gọi downstream có thể nhân lên; hãy xác định một nơi sở hữu retry chính và dùng deadline chung.

### 6.2. Redelivery từ broker

Redelivery là một lần giao mới của cùng message từ broker/nguồn. Nguyên nhân phổ biến: consumer NACK/reject với requeue, transaction rollback, consumer chết trước ACK hoặc broker không nhận được ACK đúng hạn. Cách xử lý phụ thuộc broker và acknowledgement mode.

Ví dụ với RabbitMQ/Spring AMQP: `MessageProperties.isRedelivered()` cho biết message được đánh dấu là redelivered; đây là cờ boolean, không phải bộ đếm chính xác số lần đã giao. Nếu cần số lần dead-letter/requeue, dùng metadata broker như header lịch sử dead-letter phù hợp hoặc metric của broker. Đừng giả định header của RabbitMQ có mặt trong Kafka, JMS hoặc RSocket.

Trong Spring AMQP, listener ném exception thường khiến message bị reject và requeue theo cấu hình mặc định `defaultRequeueRejected=true`. Requeue một message lỗi không thể phục hồi có thể tạo vòng lặp redelivery. `ConditionalRejectingErrorHandler` phân loại một số lỗi không thể phục hồi như conversion hoặc validation failure để reject mà không requeue; có thể cấu hình dead-letter exchange để vận hành xử lý message lỗi.

Khi ghi metric redelivery, chỉ tăng counter khi adapter/broker xác nhận delivery là redelivered. Không suy ra redelivery chỉ từ việc `attempt > 1`, vì attempt thứ hai có thể là retry nội bộ. Ngược lại, không coi redelivered flag là số attempt chính xác.

## 7. Quan sát timeout theo từng boundary

Timeout phải gắn với thao tác cụ thể. Một hệ thống có thể có nhiều timeout độc lập:

| Loại timeout | Ý nghĩa | Cách quan sát |
| --- | --- | --- |
| Send timeout | Channel không chấp nhận message trước hạn | Đếm kết quả send false/exception và đo thời gian chờ |
| Receive timeout | Không có message trước hạn polling | Đếm lần receive trả `null` do timeout |
| Request-reply timeout | Caller không nhận reply trong thời gian chờ | Đếm timeout tại template/requester và theo dõi trace phía xử lý |
| Handler/dependency timeout | Database hoặc service downstream vượt deadline | Timer cho handler và từng dependency; timeout counter riêng |
| Broker acknowledgement/visibility timeout | Broker không nhận ACK trước hạn và có thể giao lại | Metric broker, unacked count, redelivery count |
| Message TTL/expiration | Message hết hạn trước khi consumer xử lý | Broker expired/dead-letter metrics; không gọi nhầm là handler timeout |

Trong Spring Messaging, `MessageChannel.send(message, timeout)` chờ channel chấp nhận message trong thời gian chỉ định; trả `false` nếu không gửi được, bao gồm timeout hoặc interrupt. `PollableChannel.receive(timeout)` chờ message và trả `null` khi timeout hoặc bị interrupt. `GenericMessagingTemplate` cũng có `sendTimeout` và `receiveTimeout` để cấu hình thời gian chờ.

Các timeout này không tương đương timeout xử lý nghiệp vụ. Send thành công chỉ có nghĩa channel chấp nhận message theo contract của channel; nó không chứng minh handler đã xử lý hoặc database đã commit. Receive timeout chỉ nói không có message được trả về trước hạn; nó không nói queue bị lỗi.

### 7.1. Timeout có thể tạo kết quả không xác định

Giả sử client gửi `CreatePayment`, server xử lý và commit payment, nhưng response bị mất. Client hết thời gian chờ và gửi lại request. Nếu server không nhận diện idempotency key, payment có thể bị tạo hai lần.

Để giảm rủi ro:

1. Đặt timeout theo deadline end-to-end, nhỏ dần qua các tầng downstream để tầng ngoài còn thời gian phản hồi.
2. Khi timeout, ghi outcome `timeout/unknown` riêng nếu chưa biết thao tác đã commit hay chưa.
3. Dùng idempotency key hoặc deduplication theo message/event id cho command có side effect.
4. Truy vấn trạng thái theo correlation/idempotency key trước khi quyết định retry một thao tác có kết quả chưa rõ.
5. Không tăng timeout vô hạn để che backlog; đo queue depth, oldest-message age và handler latency để tìm nơi tắc.

## 8. Ví dụ Java 17: phân biệt attempt failure với terminal failure

Chương trình dưới đây mô phỏng hai logical message. `order-1` được broker redeliver, lần xử lý đầu thất bại tạm thời rồi retry thành công. `order-2` timeout ở cả hai attempt và kết thúc thất bại. Chương trình dùng bộ đếm Java đơn giản để minh họa cách tính; trong ứng dụng thật, các counter này được ghi bằng Micrometer.

**MessagingObservabilityDemo.java**

```java
import java.util.Locale;

public class MessagingObservabilityDemo {

    enum Result { SUCCESS, TRANSIENT_FAILURE, TIMEOUT }

    static final class Metrics {
        int deliveries;
        int redeliveries;
        int attempts;
        int retryAttempts;
        int failedAttempts;
        int timeouts;
        int completedMessages;
        int failedMessages;
    }

    static Result handle(String messageId, int attempt) {
        if ("order-1".equals(messageId) && attempt == 1) {
            return Result.TRANSIENT_FAILURE;
        }
        if ("order-2".equals(messageId)) {
            return Result.TIMEOUT;
        }
        return Result.SUCCESS;
    }

    static void consume(String messageId, boolean redelivered,
                        int maxAttempts, Metrics metrics) {
        metrics.deliveries++;
        if (redelivered) {
            metrics.redeliveries++;
        }

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            metrics.attempts++;
            if (attempt > 1) {
                metrics.retryAttempts++;
            }

            Result result = handle(messageId, attempt);
            if (result == Result.SUCCESS) {
                metrics.completedMessages++;
                return;
            }

            metrics.failedAttempts++;
            if (result == Result.TIMEOUT) {
                metrics.timeouts++;
            }
        }

        metrics.completedMessages++;
        metrics.failedMessages++;
    }

    static double percentage(int numerator, int denominator) {
        return denominator == 0 ? 0.0 : 100.0 * numerator / denominator;
    }

    public static void main(String[] args) {
        Metrics metrics = new Metrics();
        consume("order-1", true, 2, metrics);
        consume("order-2", false, 2, metrics);

        System.out.println("deliveries=" + metrics.deliveries);
        System.out.println("redeliveries=" + metrics.redeliveries);
        System.out.println("attempts=" + metrics.attempts);
        System.out.println("retryAttempts=" + metrics.retryAttempts);
        System.out.println("failedAttempts=" + metrics.failedAttempts);
        System.out.println("timeouts=" + metrics.timeouts);
        System.out.println("completedMessages=" + metrics.completedMessages);
        System.out.println("failedMessages=" + metrics.failedMessages);
        System.out.printf(Locale.ROOT, "attemptFailureRate=%.1f%%%n",
                percentage(metrics.failedAttempts, metrics.attempts));
        System.out.printf(Locale.ROOT, "terminalMessageFailureRate=%.1f%%%n",
                percentage(metrics.failedMessages, metrics.completedMessages));
    }
}
```

Biên dịch và chạy:

```bash
javac MessagingObservabilityDemo.java
java MessagingObservabilityDemo
```

Output chính xác:

```text
deliveries=2
redeliveries=1
attempts=4
retryAttempts=2
failedAttempts=3
timeouts=2
completedMessages=2
failedMessages=1
attemptFailureRate=75.0%
terminalMessageFailureRate=50.0%
```

Ví dụ cho thấy 3 trong 4 attempt thất bại, nhưng chỉ 1 trong 2 logical message thất bại cuối cùng. `order-1` có một attempt lỗi nhưng vẫn là terminal success. Redelivery là một delivery broker bổ sung; retryAttempts chỉ đếm attempt nội bộ sau attempt đầu trong từng delivery.

### 8.1. Gắn Timer và Counter Micrometer vào handler

Trong ứng dụng Spring, inject `MeterRegistry` và ghi metric ở ranh giới mà ứng dụng sở hữu. Ví dụ sau đo thời gian xử lý từng lần gọi handler và phân loại attempt success/failure:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

public final class InstrumentedHandler {
    private final MessageHandler delegate;
    private final MeterRegistry registry;

    public InstrumentedHandler(MessageHandler delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    public void handle(Message<?> message) {
        String outcome = "success";
        Timer.Sample sample = Timer.start(registry);
        try {
            delegate.handleMessage(message);
            registry.counter("messaging.attempts", "outcome", "success").increment();
        }
        catch (RuntimeException ex) {
            outcome = "failure";
            registry.counter("messaging.attempts", "outcome", "failure").increment();
            throw ex;
        }
        finally {
            sample.stop(registry.timer("messaging.handler.duration",
                    "operation", "consume", "outcome", outcome));
        }
    }
}
```

Đây là ví dụ minh họa decorator cho một handler; trong ứng dụng thật cần tích hợp vào flow sao cho không tạo hai lần ghi metric cho cùng một attempt. Counter retry nên tăng tại retry policy khi bắt đầu attempt bổ sung; redelivery counter nên tăng tại adapter khi nhận được broker redelivery flag; timeout counter tăng tại đúng boundary phát hiện timeout. Counter terminal outcome chỉ tăng ở nơi biết logical message đã kết thúc.

Không đưa `messageId`, `correlationId`, `userId`, exception message hoặc payload vào tag. Các giá trị có cardinality cao làm tăng số time series và chi phí lưu trữ. Dùng tag có tập giá trị nhỏ như `destination=orders`, `operation=consume`, `outcome=success|failure|timeout`, `exception=TimeoutException`; giữ ID cụ thể trong structured log hoặc trace.

## 9. Dashboard và cảnh báo

Một dashboard vận hành message nên có ít nhất các nhóm sau:

| Nhóm | Biểu đồ nên có | Câu hỏi trả lời |
| --- | --- | --- |
| Throughput | Deliveries/s, attempts/s, terminal messages/s | Lưu lượng có thay đổi bất thường không? |
| Reliability | Attempt failure rate, terminal failure rate, timeout rate | Handler có lỗi tạm thời hay message cuối cùng bị thất bại? |
| Retry/redelivery | Retry attempts/s, redelivery rate, số lần redelivery theo queue | Consumer có liên tục thử lại hoặc broker phải giao lại không? |
| Latency | Handler p50/p95/p99, request-reply latency, retry delay | Xử lý chậm ở tầng nào? |
| Backlog | Queue depth, oldest message age, unacked, consumer lag | Message có đang tích tụ hoặc bị kẹt không? |
| Recovery | Dead-letter count, recovery callback count, circuit breaker state | Message lỗi có được chuyển tới nơi xử lý cuối không? |

Alert nên kết hợp tỷ lệ và số lượng tuyệt đối. Một lỗi trong một message có thể tạo tỷ lệ 100% khi traffic rất thấp; ngược lại, tỷ lệ lỗi 1% ở hàng chục nghìn message mỗi phút vẫn là lượng lỗi lớn. Theo dõi cả xu hướng, throughput và backlog để tránh cảnh báo sai.

Các tín hiệu đáng cảnh báo:

- Terminal failure rate tăng vượt SLO trong cửa sổ liên tục.
- Retry attempts tăng nhanh trong khi terminal success không tăng tương ứng.
- Redelivery tăng cùng với unacked messages hoặc consumer restart.
- Timeout tăng cùng với p95/p99 latency và queue age.
- Queue depth hoặc oldest-message age tăng liên tục dù consumer đang hoạt động.
- Dead-letter count tăng hoặc recovery path thường xuyên được gọi.

## 10. Quy trình điều tra khi tỷ lệ lỗi tăng

1. **Xác định metric đang tăng.** Attempt failure, terminal failure, retry, redelivery hay timeout? Kiểm tra đúng mẫu số và khoảng thời gian.
2. **Chia theo destination và operation.** Tìm queue/route/handler nào có thay đổi; chỉ dùng tag có cardinality thấp.
3. **Đối chiếu latency và backlog.** p95/p99 tăng trước timeout thường gợi ý dependency chậm hoặc consumer thiếu capacity; queue depth tăng cho thấy tốc độ nhận lớn hơn tốc độ xử lý.
4. **Tách lỗi tạm thời và lỗi không thể phục hồi.** Xem exception family, conversion/validation, network, database, broker và downstream dependency.
5. **Kiểm tra retry policy.** Max attempts, backoff, jitter, retryable exception classifier, recovery callback và việc nhiều tầng cùng retry.
6. **Kiểm tra redelivery tại broker.** ACK/NACK, requeue policy, consumer restart, unacked count, dead-letter và metadata broker.
7. **Kiểm tra timeout boundary.** Send, receive, request-reply, handler hay acknowledgement timeout? Xác định thao tác có thể đã commit dù caller timeout không.
8. **Lần theo một message cụ thể.** Dùng `messageId`/`correlationId` trong log và trace để xem delivery, attempt, retry delay, timeout và terminal outcome.
9. **Xác nhận phục hồi.** Sau khi sửa, terminal failure rate và backlog phải giảm; retry/redelivery không còn tăng liên tục; message không bị xử lý trùng.

## 11. Lỗi thiết kế quan sát thường gặp

- Gộp retry nội bộ và redelivery broker thành một counter, khiến không biết tầng nào tạo thêm lần xử lý.
- Tính error rate bằng số exception chia cho số message đã nhận; mẫu số không cùng đơn vị với tử số.
- Đếm một message thất bại cuối cùng nhiều lần vì mỗi attempt đều ném exception.
- Chỉ đo timeout ở client mà không theo dõi handler/broker, khiến thao tác đã commit nhưng response bị mất bị hiểu nhầm là chưa chạy.
- Ghi message id hoặc user id vào metric tag, tạo cardinality rất cao.
- Dùng `Timer` và `Counter` cho cùng một lần đo latency một cách trùng lặp; Timer đã cung cấp count.
- Retry lỗi không thể phục hồi, gây redelivery storm hoặc DLQ loop.
- Coi `/actuator/metrics` là backend scrape production thay vì dùng exporter/endpoint metrics chuyên dụng.
- Bật logging debug toàn bộ message flow ở hệ thống có lưu lượng lớn mà không cân nhắc chi phí log và dữ liệu nhạy cảm.

## 12. Ghi nhớ

- Retry là lần gọi lại do policy; redelivery là broker/nguồn giao lại message. Hai việc có thể xảy ra cùng nhau nhưng phải đếm riêng.
- Timeout chỉ xác nhận thời gian chờ đã hết; không chứng minh side effect chưa xảy ra.
- Tách `deliveries`, `attempts`, `retries`, `redeliveries`, `timeouts` và terminal message outcomes.
- Tính cả attempt failure rate và terminal message failure rate; chúng có mẫu số khác nhau.
- Dùng Counter cho số lần, Timer cho thời gian, Gauge cho trạng thái hiện tại, Observation cho metrics/tracing kết hợp.
- Spring Framework có JMS observations; Spring Integration có metrics/observations cho channel và handler; broker-specific redelivery phải lấy từ broker hoặc adapter.
- Giữ metric tags có cardinality thấp; dùng structured logs/traces để truy tìm một message cụ thể.
- Giới hạn retry, dùng backoff, idempotency và dead-letter/recovery policy để tránh vòng lặp xử lý lỗi.

## Tài liệu tham khảo

- [Spring Framework Reference — Observability Support and JMS Messaging](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Integration Reference — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Spring Integration Reference — Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html)
- [Spring Integration Reference — MessageChannel and PollableChannel](https://docs.spring.io/spring-integration/reference/channel/interfaces.html)
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer Reference — Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html)
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer Reference — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Spring AMQP Reference — Exception Handling and Requeue](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html)
- [Spring Framework API — MessageChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html)
- [Spring Framework API — PollableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html)