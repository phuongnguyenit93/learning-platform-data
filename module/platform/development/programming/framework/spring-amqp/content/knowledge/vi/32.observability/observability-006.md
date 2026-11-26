# Phân biệt độ trễ chờ trong queue với thời gian xử lý

Một hệ thống **Spring AMQP** có thể bị người dùng phản ánh rằng “đơn hàng mất 12 giây mới được cập nhật”, trong khi log của `@RabbitListener` cho thấy đoạn xử lý chỉ mất 80 ms. Hai con số không nhất thiết mâu thuẫn: sự kiện có thể đã **chờ trong RabbitMQ**, nằm trong **buffer/prefetch ở client**, hoặc bị **retry** trước khi được xử lý thành công.

Để quan sát hệ thống bất đồng bộ đáng tin cậy, cần phân biệt ít nhất ba đại lượng:

- **Độ trễ chờ trong queue** (*queue waiting time*, *queue residence time*): khoảng từ khi message đã vào **queue cụ thể** đến khi broker gửi delivery tới consumer.
- **Thời gian xử lý** (*processing/handler duration*): thời gian đoạn mã ứng dụng thực sự thực thi khi listener nhận quyền xử lý; có thể gồm gọi database, HTTP, chuyển đổi nghiệp vụ và transaction.
- **Độ trễ đầu cuối** (*end-to-end/event latency*): khoảng từ một mốc nghiệp vụ hoặc publish đã định nghĩa đến khi kết quả nghiệp vụ được hoàn tất ở consumer. Nó có thể lớn hơn rất nhiều so với hai khoảng trên.

Bài thuộc chương **Quan sát hệ thống** của module **SPRING_AMQP**: kết hợp `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding, ACK/NACK, retry, dead-letter, metrics và distributed tracing để định vị thời gian chậm ở đúng tầng. Trọng tâm là **đo đúng đại lượng trước khi tối ưu**, thay vì chỉ nhìn một biểu đồ “latency” rồi suy đoán nguyên nhân.

## 1. Timeline của một message: chờ ở đâu, xử lý ở đâu?

Giả sử service Orders ghi đơn hàng, phát sự kiện `OrderCreated`, RabbitMQ định tuyến tới `billing.order-created` và Billing listener cập nhật database:

```text
Orders service         RabbitMQ broker                 Billing consumer
     |                      |                                |
t0   |  DB commit           |                                |
     |                      |                                |
t1   |-- publish ---------->|                                |
     |                      |                                |
t2   |                 enqueue vào queue                      |
     |                      |                                |
     |                [WAITING: ready]                        |
     |                      |                                |
t3   |                      |------ delivery --------------->|
     |                      |                                |
     |                      |                  [client prefetch / dispatch]
t4   |                      |                         @RabbitListener bắt đầu
     |                      |                                |
     |                      |                         [BUSINESS PROCESSING]
     |                      |                                |
t5   |                      |                         commit DB thành công
     |                      |                                |
     |                      |<--------- ACK -----------------|
t6   |                  broker ghi nhận ACK                  |
     |                      |                                |
```

Đặt các mốc:

| Mốc | Ý nghĩa | Ai có thể quan sát? |
|---|---|---|
| `t0` | Giao dịch nghiệp vụ nguồn commit | Orders service hoặc nguồn outbox |
| `t1` | Publisher bắt đầu gửi message | `RabbitTemplate` / producer instrumentation |
| `t2` | Message được enqueue vào **queue đích** | Chủ yếu broker; không có timestamp per-message enqueue chuẩn qua RabbitTemplate |
| `t3` | Broker giao message tới connection/consumer | Broker và client ở những mức quan sát khác nhau |
| `t4` | Method `@RabbitListener` bắt đầu xử lý | Application listener |
| `t5` | Tác dụng phụ nghiệp vụ/DB commit thành công | Business service/DB |
| `t6` | Broker chấp nhận ACK của delivery | Broker; không trùng chính xác thời điểm method return |

Từ đó có các khoảng khác nhau:

```text
Producer/outbox delay       = t1 - t0
Publish/routing overhead    = t2 - t1        (xấp xỉ, phụ thuộc broker)
TRUE queue waiting          = t3 - t2
Consumer dispatch/prefetch  = t4 - t3
Business processing         = t5 - t4
ACK completion interval     = t6 - t5
End-to-end business latency = t5 - t0
Publish-to-handler latency  = t4 - t1
```

**Phân biệt quan trọng:** Với instrumentation chỉ ở publisher và listener, ta thường đo được `t4 - t1`, **không đo trực tiếp** `t3 - t2`. Khoảng publish-to-handler bao gồm đi mạng, định tuyến, chờ ready trong queue, consumer prefetch, dispatch và clock skew nếu dùng hai host.

Nếu cùng một exchange định tuyến message đến **nhiều queue**, mỗi queue có `t2`, `t3` và thời gian chờ riêng; không có “queue waiting time” duy nhất của message ở mọi subscriber.

## 2. Độ trễ chờ trong queue khác thời gian xử lý như thế nào?

### 2.1. Queue waiting time

**Định nghĩa:** Message đã nằm trong queue nhưng chưa được broker giao cho consumer. Độ trễ thường tăng khi tốc độ publish cao hơn tốc độ consumer rút message, consumer thiếu tài nguyên hoặc broker chịu áp lực.

Ví dụ: RabbitMQ queue có 20.000 message `ready`, consumer xử lý ổn định 200 message/giây. Một message mới có thể phải chờ lâu dù xử lý từng message rất nhanh. Nhưng **không thể lấy 20.000/200 = 100 giây làm số đo chính xác cho từng message**: đó chỉ là ước lượng trong điều kiện đơn giản, ổn định và không có thay đổi tốc độ, ưu tiên, requeue hoặc nhiều đường routing.

### 2.2. Processing time

**Định nghĩa:** Thời gian thực thi logic của listener/business handler; ví dụ:

```java
@RabbitListener(queues = "billing.order-created")
public void process(String orderId) {
    billingService.createInvoice(orderId);
}
```

Nếu có instrumentation quanh lời gọi `billingService.createInvoice`, duration đo được phần code này. Nếu chỉ đặt timer đầu-cuối của method listener, nó bao gồm logic trong method nhưng **không** bao gồm message đang đợi trong broker, thời gian broker gửi delivery tới client, hoặc đoạn ACK sau khi listener trả về dưới `AcknowledgeMode.AUTO`.

Một thời gian handler cao có thể do database lock, truy vấn chậm, HTTP timeout, CPU, GC, thread contention hoặc retry đồng bộ bên trong method. Không nên quy nó ngay cho RabbitMQ.

### 2.3. Publish-to-consume age là một proxy, không phải queue waiting thuần

Publisher có thể thêm `publishedAtEpochMs` vào header và listener lấy `now - publishedAtEpochMs` lúc bắt đầu xử lý. Đây là **độ tuổi message tại điểm nhận vào listener**, hữu ích để báo động backlog; tuy nhiên nó gồm các phần không nằm trong broker queue:

- Lúc publisher encode/send và mạng đi tới broker.
- Thời gian broker route/persist, nhất là khi có durability/cluster replication.
- Thời gian message `ready` chờ consumer.
- Khoảng message đã được deliver nhưng chờ trong buffer/prefetch client.
- Sai lệch đồng hồ giữa producer và consumer.
- Nếu message được retry/requeue: tuổi từ publish gốc có thể gồm thời gian ở retry queue, TTL, dead-letter và các lần xử lý trước.

Vì vậy đặt tên `app.rabbit.receive.age` hoặc `publish_to_listener_latency` sẽ đúng bản chất hơn đặt tên `queue_wait_ms` cho phép tính này.

## 3. Đọc đúng các queue metrics của RabbitMQ

RabbitMQ Management API/Prometheus plugin cung cấp các tín hiệu về **số lượng và tốc độ**, không trực tiếp trả về một histogram thời gian chờ per-message chuẩn cho mọi queue.

| Chỉ số / trường phổ biến | Diễn giải đúng | Điều **không** suy ra được trực tiếp |
|---|---|---|
| `messages_ready` | Message ở queue đang sẵn sàng giao cho consumer | Không phải số ms chờ |
| `messages_unacknowledged` / `messages_unacked` | Delivery đã giao nhưng chưa được ACK | Không có nghĩa tất cả đang thực thi trong listener |
| `messages` | Tổng ready + unacked | Không tách được chờ broker với chờ client |
| Publish rate | Tốc độ message đến broker/queue | Không phải tốc độ nghiệp vụ đã xử lý thành công |
| Deliver/get rate | Tốc độ broker giao message/ứng dụng lấy message | Không phải throughput DB commit |
| Ack rate | Tốc độ acknowledgment của consumer | Không nhất thiết bằng số tác dụng phụ nghiệp vụ thành công |
| Redelivery rate | Tần suất message được giao lại | Không cho biết chính xác tuổi message hoặc số lần retry của từng ID |
| DLQ depth | Số message đang tồn ở dead-letter queue | Không cho biết nguyên nhân hay latency hoàn tất |
| Consumers / channel count | Số consumer và tài nguyên | Không tự chứng minh consumer đang hiệu quả |

**`ready` so với `unacked` là sự khác biệt mang tính chẩn đoán:**

- `ready` tăng cao, `unacked` ổn định ở mức thấp: có thể thiếu consumer, không đủ sức rút message, routing vào queue chưa có người nhận.
- `unacked` tăng cao: broker đã giao message nhưng ACK chậm; nguyên nhân có thể là handler chậm, transaction chưa xong, **prefetch quá lớn**, consumer treo hoặc connection mất khả năng tiến triển.
- Cả hai cao: tải đến vượt khả năng xử lý, consumer vừa tồn đọng trong queue vừa giữ nhiều delivery chưa ACK.
- Cả hai thấp nhưng khách hàng vẫn thấy chậm: có thể delay trước publish (outbox), retry trên queue khác, consumer in-memory backlog, network hoặc độ trễ hệ thống downstream.

**Nhớ:** `unacked` không đồng nghĩa `currently executing`. Khi `prefetchCount=50` và một consumer chỉ xử lý một callback mỗi lần, broker có thể đã giao hàng chục message chưa ACK, trong khi một message duy nhất đang chạy business code.

## 4. Vai trò của prefetch, concurrency và ACK

### 4.1. Prefetch chuyển phần chờ từ broker sang client

Ví dụ một consumer tuần tự có `prefetch=20`:

```text
RabbitMQ queue                       Consumer process
 ready: 100                             |
   |                                    |
   +---- broker delivers 20 ----------->| buffered/unacked: 20
                                        |
                                        +--> handler M1 đang chạy
                                        |    M2..M20 chờ callback
                                        |
 broker ready: 80                        |
 broker unacked: 20                      |
```

Đối với M20, thời gian chờ tại broker kết thúc khi broker giao nó đi (`t3`), **nhưng nó vẫn chưa bắt đầu handler (`t4`)**. Nếu ta chỉ xem `messages_ready`, có thể tưởng backlog giảm; nếu chỉ xem handler timer, cũng không thấy được thời gian M20 nằm trong prefetch buffer.

Khi đổi `prefetch` từ 20 lên 200, số message ready có thể giảm nhanh hơn mà độ trễ đến khi xử lý **không giảm tương ứng**; thậm chí có thể tăng nếu một consumer giữ quá nhiều delivery chưa ACK.

### 4.2. Concurrency và trần throughput

Giả sử handler có p95 = 120 ms và 4 consumer chạy độc lập, số message xử lý/giây tối đa phụ thuộc cả phân phối latency, CPU, DB, thread, batch và redelivery. Không nên tính chính xác `4 / 0.12` chỉ từ p95, vì **p95 không phải giá trị trung bình**.

Các tham số thường kiểm soát:

```java
@Bean("billingListenerFactory")
SimpleRabbitListenerContainerFactory billingListenerFactory(
        ConnectionFactory connectionFactory) {

    SimpleRabbitListenerContainerFactory factory =
            new SimpleRabbitListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
    factory.setConcurrentConsumers(2);
    factory.setMaxConcurrentConsumers(8);
    factory.setPrefetchCount(10);
    factory.setDefaultRequeueRejected(false);
    return factory;
}
```

Các class thuộc `org.springframework.amqp.rabbit.config`, `org.springframework.amqp.rabbit.connection`, `org.springframework.amqp.core`, `org.springframework.context.annotation`. Đặt `defaultRequeueRejected(false)` trong ví dụ chỉ phù hợp khi queue có DLX hợp lệ và có chính sách retry/backoff riêng; không copy vào production nếu muốn requeue mặc định.

**Cần đo trước khi tăng concurrency:** nhiều consumer có thể làm database lock contention, rate limit HTTP downstream và processing p99 tệ hơn. Nếu một workload cần thứ tự theo aggregate, tăng concurrency còn làm tăng nguy cơ xử lý sai thứ tự.

### 4.3. ACK không trùng thời điểm xử lý xong

Trong `AcknowledgeMode.AUTO`, framework thường ACK khi listener hoàn thành bình thường; nếu listener ném exception, container áp dụng reject/requeue tùy chính sách. Nhưng **đo duration đến dòng return không bao gồm chắc chắn độ trễ ACK được broker xử lý**.

Nếu DB commit xong rồi connection lỗi trước ACK, message có thể được redeliver. Một handler ngắn **không bảo đảm** hoàn tất đầu-cuối đúng một lần; cần idempotency và theo dõi tỷ lệ redelivery.

## 5. Thiết kế bộ số liệu: tách ít nhất ba timer

Nên thiết kế metrics có **tên nêu rõ ranh giới**, đơn vị và source của timestamp:

| Metric ứng dụng đề xuất | Điểm bắt đầu → kết thúc | Diễn giải |
|---|---|---|
| `app.rabbit.producer.send.duration` | Vào hàm gửi → hàm gửi trả về | Thời gian thực thi thao tác publisher; chưa chắc đã có confirm |
| `app.rabbit.publisher.confirm.duration` | Publish → broker confirm được nhận | Round-trip/cam kết broker theo confirms, không phải business processing |
| `app.rabbit.receive.age` | `publishedAtEpochMs` → lúc callback listener bắt đầu | Publish-to-listener latency (**proxy cho chờ**, không phải queue residence thuần) |
| `app.rabbit.handler.duration` | Listener bắt đầu → logic nghiệp vụ kết thúc/throw | Thời gian xử lý ở ứng dụng |
| `app.rabbit.business.commit.duration` | Bắt đầu DB transaction → commit | Thành phần DB của xử lý, có thể khác handler duration |
| `app.rabbit.business.end_to_end.duration` | Thời điểm domain event nguồn commit → DB consumer commit | Độ trễ nghiệp vụ đầu-cuối, có thể gồm outbox và nhiều queue |
| `app.rabbit.retry.age` | Publish gốc → lần xử lý lại hiện tại | Tuổi sự kiện khi retry; cần phân biệt queue hopping |
| `app.rabbit.dlq.oldest.age` | Mốc gốc đã chọn → thời điểm đo ở DLQ | Theo dõi sự kiện lỗi chưa được giải quyết |

Không phải hệ thống nào cũng đo được mọi timer. Một ứng dụng chỉ có publisher và listener **không thể tự biết chính xác t2 enqueue và t3 delivery** nếu broker không cấp tín hiệu phù hợp. Khi cần queue residence chính xác, cần broker-level tracing/instrumentation hoặc cơ chế thêm timestamp ở broker được hỗ trợ và kiểm chứng; các field do producer tự gắn chỉ cho phép **xấp xỉ**.

### 5.1. Cùng tên “latency” nhưng chênh hàng trăm lần

Ví dụ một message:

| Khoảng | Giá trị minh họa |
|---|---:|
| Domain commit → outbox relay publish | 900 ms |
| Publish → broker enqueue | 20 ms |
| Chờ ready trong queue | 6.000 ms |
| Đã deliver → listener bắt đầu (prefetch/dispatch) | 1.500 ms |
| Handler/DB | 80 ms |
| ACK broker ghi nhận | 5 ms |
| **Đến khi DB consumer commit** | **8.500 ms** |

Một dashboard chỉ hiển thị `handler p95=80ms` có thể làm nhóm phát triển tưởng ứng dụng nhanh, nhưng business event thật mất 8,5 giây để có tác dụng. Ngược lại, nếu chỉ nhìn tuổi message 7.520 ms mà gọi “DB slow”, đội kỹ thuật có thể tối ưu sai nơi.

## 6. Đo publish-to-listener age và handler duration với Micrometer

Phần này dùng **Spring Boot 3.x, Spring AMQP 3.x, Micrometer**, Java 17+. Đây là ví dụ instrumentation **ứng dụng**; không đo chính xác broker enqueue/dequeue. Trong dự án thật nên có Actuator/Micrometer registry phù hợp Prometheus/OpenTelemetry.

### 6.1. Gắn mốc thời gian khi gửi bằng RabbitTemplate

Producer thêm timestamp ở bước publish, **không dùng timestamp mặc định của RabbitMQ như đồng hồ enqueue**, vì RabbitMQ 0-9-1 không tự cung cấp cho ứng dụng một timestamp enqueue chuẩn trên mỗi message qua `RabbitTemplate`.

```java
@Service
public class OrderEventPublisher {

    private final RabbitTemplate rabbitTemplate;

    public OrderEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(String eventId, String jsonPayload) {
        rabbitTemplate.convertAndSend(
                "orders.events",
                "orders.created",
                jsonPayload,
                message -> {
                    MessageProperties props = message.getMessageProperties();
                    props.setHeader(
                            "publishedAtEpochMs", System.currentTimeMillis());
                    props.setMessageId(eventId);
                    props.setContentType(MessageProperties.CONTENT_TYPE_JSON);
                    props.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                    return message;
                });
    }
}
```

Import cần thiết: `org.springframework.amqp.rabbit.core.RabbitTemplate`, `org.springframework.amqp.core.MessageProperties`, `org.springframework.amqp.core.MessageDeliveryMode`, `org.springframework.stereotype.Service`.

`publishedAtEpochMs` do producer tạo. Nó cho phép ước lượng độ tuổi message tại consumer nếu đồng hồ tương đối đồng bộ; **không phải mốc broker đã enqueue**. Khi message được requeue/dead-letter, timestamp có thể vẫn là mốc publish gốc, nên tuổi nhận được bao gồm cả các lần chờ và retry.

Nếu dùng **transactional outbox**, cần phân biệt thêm `occurredAt` (domain event) với `publishedAtEpochMs` (lần relay publish). Một event có thể đã nằm trong outbox lâu trước khi broker nhìn thấy nó. Nếu muốn đo *từ khi có ý định gửi*, lưu thêm thời điểm commit/created của outbox bằng database clock, rồi đo riêng **outbox lag**.

### 6.2. Consumer đo hai đại lượng khác nhau

```java
@Component
public class BillingListener {

    private final BillingService billingService;
    private final Timer successTimer;
    private final Timer failureTimer;
    private final Timer receiveAgeTimer;
    private final Counter invalidTimestampCounter;

    public BillingListener(
            BillingService billingService, MeterRegistry registry) {
        this.billingService = billingService;

        this.successTimer = Timer.builder("app.rabbit.handler.duration")
                .tag("queue", "billing.order-created")
                .tag("result", "success")
                .publishPercentileHistogram()
                .register(registry);

        this.failureTimer = Timer.builder("app.rabbit.handler.duration")
                .tag("queue", "billing.order-created")
                .tag("result", "failure")
                .publishPercentileHistogram()
                .register(registry);

        this.receiveAgeTimer = Timer.builder("app.rabbit.receive.age")
                .description("Publisher timestamp to listener entry")
                .tag("queue", "billing.order-created")
                .publishPercentileHistogram()
                .register(registry);

        this.invalidTimestampCounter = Counter.builder(
                        "app.rabbit.receive.timestamp.invalid")
                .tag("queue", "billing.order-created")
                .register(registry);
    }

    @RabbitListener(queues = "billing.order-created")
    public void onMessage(Message message) {
        // Lấy mốc ngay lúc callback bắt đầu, trước business code.
        long entryEpochMs = System.currentTimeMillis();
        long startNanos = System.nanoTime();
        boolean success = false;

        recordMessageAge(message, entryEpochMs);

        try {
            billingService.handle(message.getBody());
            success = true;
        } finally {
            long nanos = System.nanoTime() - startNanos;
            (success ? successTimer : failureTimer)
                    .record(nanos, TimeUnit.NANOSECONDS);
        }
    }

    private void recordMessageAge(Message message, long entryEpochMs) {
        Object raw = message.getMessageProperties()
                .getHeaders().get("publishedAtEpochMs");

        if (!(raw instanceof Number number)) {
            invalidTimestampCounter.increment();
            return;
        }

        long ageMs = entryEpochMs - number.longValue();

        // Ngưỡng minh họa 7 ngày; loại trừ clock skew/giá trị sai.
        if (ageMs < 0 || ageMs > Duration.ofDays(7).toMillis()) {
            invalidTimestampCounter.increment();
            return;
        }

        receiveAgeTimer.record(ageMs, TimeUnit.MILLISECONDS);
    }
}
```

Import tiêu biểu:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;
```

Ví dụ ghi:

- `app.rabbit.receive.age` **một lần khi handler bắt đầu**, trước khi xử lý; nhận giá trị `now - publishedAtEpochMs`.
- `app.rabbit.handler.duration` bằng **monotonic clock** `System.nanoTime()` trong **cùng process** để tránh lỗi khi đồng hồ hệ thống được chỉnh.
- `result=success/failure` dựa trên việc business method return hay throw. Nếu method nuốt exception rồi trả về bình thường thì instrumentation cũng ghi success; code nghiệp vụ phải báo lỗi đúng cách.
- Với `BillingService.handle` có DB transaction, đo quanh lời gọi sẽ gồm cả giai đoạn transaction proxy hoàn tất nếu gọi qua một Spring bean khác.

**Giới hạn:** Timer trên đo đoạn listener method, **không đo ACK/NACK hoàn tất ở broker** và không bao gồm thời gian chờ callback được dispatch từ prefetch buffer. Cần bộ đo broker và trace để tìm các đoạn còn lại.

### 6.3. Phân biệt time source và clock skew

Có hai phương pháp đo khác nhau:

| Cách đo | Đồng hồ | Tính chất |
|---|---|---|
| `System.nanoTime()` từ đầu đến cuối một đoạn code trong cùng JVM | Monotonic elapsed clock | Phù hợp cho handler duration, không so sánh trực tiếp giữa hai máy |
| Epoch timestamp ở producer và listener | Wall clock giữa hai máy | Phù hợp cho event age **nếu NTP/chrony đồng bộ**, vẫn có sai số |
| Timestamp do broker ghi khi enqueue/deliver | Broker/observability extension | Có thể gần queue wait thật hơn, nhưng cần hỗ trợ cụ thể |
| Timestamp trong JSON `occurredAt` | Domain clock/DB time | Đo age từ lúc nghiệp vụ, không đồng nghĩa publish/queue wait |

Một message sinh ở máy producer có clock nhanh hơn consumer 5 giây có thể tạo **age âm**. Đừng âm thầm ép về 0 rồi để histogram sai; đếm `invalid_timestamp`, kiểm tra đồng bộ thời gian và cách parse.

**Không so sánh `System.nanoTime()` giữa hai JVM/process**, vì giá trị chỉ có ý nghĩa đo chênh lệch thời gian trong cùng miền đồng hồ monotonic.

## 7. Micrometer Observation, tracing và timing tích hợp của Spring AMQP

Spring AMQP tích hợp Micrometer theo hai cách khác nhau.

### 7.1. Listener timer truyền thống

Từ các phiên bản Spring AMQP có hỗ trợ Micrometer (2.2+), listener container có thể ghi timer tự động khi có `MeterRegistry` phù hợp. Tên thông dụng là `spring.rabbitmq.listener` với các nhãn như `listenerId`, `queue`, `result` và `exception`.

Timer này đo **hoạt động listener ở phía ứng dụng**, không tự trở thành histogram queue-wait per-message. Khi có nhiều consumer hoặc prefetch, thời gian nằm trong buffer/broker vẫn không được suy ra chỉ từ timer.

### 7.2. Observation/tracing (Spring AMQP 3.0+)

Từ Spring AMQP 3.0, `RabbitTemplate` và listener containers có hỗ trợ **Micrometer Observation**. Khi bật `observationEnabled`, mô hình Observation quản lý timers/traces và **thay thế các Micrometer listener timers cơ bản của cùng container**, tránh coi chúng là hai nguồn đo độc lập.

Cấu hình minh họa:

```java
@Configuration
public class RabbitObservationConfiguration {

    @Bean
    RabbitTemplate observedRabbitTemplate(ConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setObservationEnabled(true);
        return template;
    }

    @Bean("observedListenerFactory")
    SimpleRabbitListenerContainerFactory observedListenerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setObservationEnabled(true);
        return factory;
    }
}
```

Nếu listener `@RabbitListener` dùng factory trên, chỉ định `containerFactory="observedListenerFactory"`. Với Spring Boot tự cấu hình một template/container mặc định, có thể dùng cấu hình/customizer tương ứng; không tạo thêm bean chỉ để instrumentation rồi vô tình bỏ qua cấu hình cũ như converter, concurrency, retry hoặc `RabbitAdmin`.

Tài liệu Spring AMQP 3.x công bố các Observation metrics như `spring.rabbit.listener`, `spring.rabbit.template` và long-task timer liên quan. Tên/labels thực tế phụ thuộc phiên bản và backend; **không đánh đồng `spring.rabbitmq.listener` (timer cũ) với `spring.rabbit.listener` (Observation)**.

Khi có Micrometer Tracing/OpenTelemetry/Zipkin hoặc backend tracing tương ứng và propagation được cấu hình đúng, một trace có thể nối các span publish/receive, giúp kiểm tra đường đi của message qua service. **Span lifetime chỉ biểu diễn khoảng đã instrument**, không tự bổ sung một span cho thời gian message nằm im trong broker nếu không có broker-side instrumentation. Tracing còn có sampling nên không thể dùng từng trace mẫu làm phân phối latency của toàn bộ traffic.

### 7.3. Không gắn eventId vào metric labels

Nhãn hợp lý: `service`, `queue`, `listener`, `result`, `exception.category`, `environment` trong một tập giá trị được giới hạn. Không gắn `eventId`, `orderId`, timestamp hoặc correlation ID làm tag metric: cardinality tăng không giới hạn, gây áp lực lên Prometheus/metrics backend.

Đặt message ID/correlation ID vào **structured logs/traces**, có phân quyền và không ghi payload chứa dữ liệu nhạy cảm. Dashboard dùng các metrics tổng hợp; khi điều tra một message cụ thể mới drill down qua trace/log.

## 8. Dashboard: đặt các biểu đồ cạnh nhau

Một dashboard hữu ích cho mỗi queue quan trọng nên có:

| Nhóm biểu đồ | Cần hiện gì? | Câu hỏi chẩn đoán |
|---|---|---|
| Queue depth | Ready, unacked, tổng messages | Message bị kẹt ở broker hay đã deliver? |
| Throughput | Publish, deliver, ACK, redelivery theo giây | Tốc độ vào có vượt tốc độ tiêu thụ không? |
| Latency histogram | Receive age p50/p95/p99; handler duration p50/p95/p99 | Chậm do backlog hay do từng lần xử lý? |
| Downstream | DB query/transaction time, HTTP dependency time | Handler chậm vì resource nào? |
| Errors | Listener failures, retries, NACK/reject, DLQ count | Có retry loop/poison messages? |
| Capacity | Consumer count, prefetch, thread pool, CPU/GC, DB pool | Có thiếu parallelism hay quá tải downstream? |
| End-to-end | Domain event commit → consumer DB commit | SLA nghiệp vụ thực tế đạt không? |

RabbitMQ Prometheus plugin có metric chi tiết như `rabbitmq_detailed_queue_messages_ready` và `rabbitmq_detailed_queue_messages_unacked` khi bật/scrape **metric families và endpoint chi tiết phù hợp**. Không giả định mọi cài đặt đều xuất các series này trên `/metrics` mặc định. Tên metric, labels, endpoint và data availability phải được kiểm chứng trong môi trường triển khai.

Ví dụ PromQL **minh họa** khi các histogram đã được Micrometer/Prometheus xuất đúng tên:

```promql
# p95 publish-to-listener age, đơn vị giây
histogram_quantile(
  0.95,
  sum by (le, queue) (
    rate(app_rabbit_receive_age_seconds_bucket[5m])
  )
)

# p95 handler duration, đơn vị giây
histogram_quantile(
  0.95,
  sum by (le, queue) (
    rate(app_rabbit_handler_duration_seconds_bucket[5m])
  )
)
```

Các series `*_bucket` chỉ xuất hiện nếu timer được cấu hình publish histogram và registry/backend có hỗ trợ. Vì `Timer` thường xuất theo **giây** trên Prometheus, đừng so sánh một đồ thị đơn vị giây với SLO cấu hình mili-giây mà không quy đổi.

**Không cộng p95 queue age với p95 handler duration rồi gọi là p95 end-to-end.** Percentile không có tính chất cộng tuyến tính: hai message tạo ra p95 của hai đại lượng có thể khác nhau. Muốn end-to-end p95, cần đo trực tiếp độ trễ end-to-end trên từng event.

## 9. Mẫu triệu chứng và cách phân tích nguyên nhân

| Hiện tượng | Giả thuyết ưu tiên kiểm tra | Hành động kiểm chứng |
|---|---|---|
| `ready` tăng; receive age tăng; handler p95 ổn định thấp | Consumer throughput không theo kịp lượng publish | Đối chiếu rates, consumer count, CPU, thiếu listener |
| `unacked` tăng; handler duration cao | Business processing/DB/HTTP chậm | So sánh trace/span DB, pool và downstream latency |
| `ready` giảm; `unacked` cao; handler vẫn ngắn | Prefetch quá lớn, delivery nằm trong client buffer, ACK bị kẹt hoặc timing không đầy đủ | Thử giảm prefetch, xem consumer utilization, connection/ACK |
| `ready` thấp; receive age cao | Outbox chậm, network/routing, prefetch buffer, clock skew, retry queue | Đo producer/outbox lag, NTP, đường retry và timestamps |
| Handler p99 cao, CPU thấp | DB locks, I/O, HTTP timeout hoặc thread pool wait | Xem dependency metrics, trace và thread dumps |
| Redelivery tăng, DLQ tăng | NACK/requeue loop, message poison, downstream không ổn định | Phân loại exception, retry delay và giới hạn |
| Publish confirm latency cao nhưng consumer processing bình thường | Broker/network/durability hoặc publisher path chậm | Publisher confirm timer, disk alarms, cluster health |
| Chỉ một loại event có receive age cao | Routing queue/partition riêng, payload lớn hoặc handler đặc thù | Phân nhóm queue, event type có giá trị hữu hạn |
| p50 tốt, p99 rất xấu | Long-tail dependency, retry, GC, lock contention | Histogram, trace các ca chậm, không chỉ average |

Bảng chỉ đưa ra **giả thuyết**, không phải suy luận chắc chắn từ một metric. Mỗi quyết định nên dựa trên **ít nhất một tín hiệu về độ sâu queue, một về latency và một về tốc độ/xử lý**.

### 9.1. Ví dụ 1: lỗi tưởng là xử lý chậm

- Publisher rate: 500 message/giây.
- ACK rate ổn định: 300 message/giây.
- `messages_ready` tăng đều.
- Handler p95: 35 ms, gần như không đổi.
- `receive.age` p95: từ 0,5 giây tăng lên 45 giây.

**Diễn giải:** Từng handler không chậm đi, nhưng tổng năng lực xử lý thấp hơn lượng vào nên backlog tăng. Ưu tiên kiểm tra số consumer, downstream capacity, concurrency/partitioning và burst management; chỉ tối ưu SQL từng message có thể không giải quyết nhu cầu throughput nếu không định lượng.

### 9.2. Ví dụ 2: lỗi ở database

- `messages_unacknowledged` tăng.
- Handler p95 từ 80 ms lên 2.800 ms.
- DB connection pool chạm trần; query lock wait tăng.
- `messages_ready` có thể tăng sau đó vì các consumer xử lý lâu hơn.

**Diễn giải:** Bottleneck nằm ở tài nguyên xử lý. Tăng số consumer vô hạn có thể làm DB tranh chấp nhiều hơn. Cần tối ưu transaction/query, kiểm soát concurrency, backpressure hoặc tách workload.

### 9.3. Ví dụ 3: prefetch che backlog

- `prefetchCount` tăng từ 10 lên 200.
- `messages_ready` giảm nhanh, `messages_unacknowledged` tăng.
- Handler duration không đổi.
- `receive.age` vẫn cao do message đã nhận nhưng chưa được dispatch.

**Diễn giải:** Queue broker có vẻ “nhẹ” hơn, nhưng thời gian chờ đã dịch sang consumer buffer. Kết hợp ready/unacked/receive age để tránh tối ưu sai.

## 10. Công thức ước lượng chờ và giới hạn

Trong điều kiện hệ thống **tương đối ổn định**, định luật Little đưa ra:

\[
L = \lambda W
\]

Trong đó `L` là số message trung bình trong **một phạm vi đo đã xác định**, `λ` là throughput ổn định, `W` là thời gian trung bình message nằm trong phạm vi đó.

Có thể lấy ví dụ lý tưởng:

- Trung bình `messages_ready = 1.000`.
- Rate rút message ổn định khoảng `100 message/giây`.
- Không có priority, bursts, retry/requeue đáng kể và tốc độ vào/ra cân bằng lâu dài.

Khi các giả định thỏa mãn, `W_ready ≈ 1.000 / 100 = 10 giây` là **ước lượng trung bình thời gian ở trạng thái ready**, không phải p95/p99. Với queue đang **tăng liên tục**, điều kiện stationary/steady-state bị phá vỡ, nên dùng phép chia này để báo cáo “queue wait thực tế” là sai.

Cũng cần phân biệt **số message ready trung bình** và **snapshot ready**: một thời điểm bất thường không đại diện cho `L` trung bình. Nếu ACK rate khác delivery rate do batch, retry hoặc redelivery, nên cẩn thận chọn rate phù hợp với ranh giới đo.

**Kết luận:** Queue depth/rate rất hữu ích để **dự báo và xác nhận xu hướng**, nhưng không thay thế việc instrument timestamp/latency ở đúng ranh giới.

## 11. Retry, dead-letter và khái niệm “tuổi message”

Một message có thể đi qua nhiều queue:

```text
orders.events -> orders.work
                     |
                     | thất bại
                     v
                 orders.retry (TTL 30s)
                     |
                     | dead-letter lại
                     v
                 orders.work
                     |
                     | hết lần thử
                     v
                 orders.dead
```

Khi message được gửi lại:

- **Tuổi event** từ `occurredAt` có thể tiếp tục tăng; hữu ích cho SLO nghiệp vụ và cảnh báo event quá cũ.
- **Tuổi tính từ publish ban đầu** cũng tiếp tục tăng nếu header `publishedAtEpochMs` được bảo tồn, gồm cả 30 giây ở retry queue.
- **Thời gian ở queue hiện tại** bắt đầu khi message được enqueue vào queue đó; khác tuổi event qua nhiều queue.
- Một application republish có thể tạo timestamp mới; lúc này `publishedAtEpochMs` chỉ đo tuổi **lần publish mới**, nếu không giữ thêm `originalPublishedAt`.
- Header `x-death` do RabbitMQ gắn khi dead-letter có thể hỗ trợ nhận diện lịch sử dead-letter, **không phải một đồng hồ latency phổ quát**; message có thể requeue/redeliver mà không có cùng dấu vết `x-death`.

Nếu dashboard trộn message mới xử lý lần đầu với message retry 10 phút trước, p99 của `receive.age` có thể tăng mạnh dù thời gian chờ **ở queue làm việc hiện tại** vẫn thấp. Nên phân nhóm hợp lý theo **lần giao, đường retry hoặc event age**, đồng thời giữ một metric end-to-end bao quát nghiệp vụ.

**Không phải “message đã vào DLQ” nghĩa là xử lý hoàn tất.** Nó chỉ được cách ly để điều tra/replay. SLO đến khi nghiệp vụ được hoàn tất phải có quy tắc riêng cho sự kiện lỗi vĩnh viễn.

## 12. SLO và alert: theo dõi đúng trải nghiệm nghiệp vụ

Một SLO hữu ích cần rõ **đối tượng**, **điểm bắt đầu**, **điểm hoàn tất** và **mức percentile**:

| SLO ví dụ | Ranh giới đo | Cảnh báo/phân tích |
|---|---|---|
| 95% `OrderCreated` đến listener trong 2 giây | Producer publish → listener callback | Chú ý proxy và clock skew |
| 99% handler xử lý trong 500 ms | Vào handler → transaction hoàn tất/throw | Đánh giá DB/HTTP latency |
| 99% hóa đơn được tạo trong 10 giây sau DB order commit | Domain commit → billing DB commit | Bao gồm outbox, broker, retry và processing |
| Outbox không có event pending lâu quá 1 phút | Outbox created/committed → relay publish confirmed | Phát hiện trễ **trước** broker queue |
| DLQ event quan trọng được giải quyết trong 30 phút | Event vào DLQ → xử lý điều tra/replay hoàn tất | Cần trạng thái vận hành độc lập |

Đây là **ngưỡng minh họa**, không phải tiêu chuẩn cố định của RabbitMQ. Chọn ngưỡng dựa trên SLA thực, phân phối traffic, giờ cao điểm và recovery requirements.

Gợi ý alert phân tầng:

1. **Độ trễ đầu-cuối** vượt SLO: ảnh hưởng người dùng, cần cảnh báo nghiệp vụ.
2. **Receive age và queue ready** đồng thời tăng: điều tra năng lực xử lý và backlog.
3. **Handler duration và unacked** đồng thời tăng: điều tra downstream/DB/prefetch/ACK.
4. **Redelivery, retry hoặc DLQ** tăng bất thường: điều tra poison message và chính sách retry.
5. **Timestamp invalid** tăng: sai clock hoặc mapping/serialization; tạm không tin các biểu đồ receive-age.
6. **Queue không consumer** hoặc listener stopped: alert độc lập, không chờ p95 xuất hiện vì không có message được xử lý để ghi latency.

**Survivorship bias:** Khi queue tắc nặng, các message chưa tới listener **không có mặt trong histogram receive age**. Có thể thấy latency của message đã xử lý vẫn đẹp trong khi hàng nghìn message chưa được quan sát. Vì vậy histogram ứng dụng luôn phải đi cùng `messages_ready`, tuổi backlog (nếu có nguồn đo phù hợp) và trạng thái consumer.

## 13. Bài thực hành: mô phỏng và tìm đúng nguyên nhân

Chuẩn bị một RabbitMQ có `orders.events`, queue durable `billing.order-created`, binding phù hợp, producer dùng `RabbitTemplate` và consumer dùng `@RabbitListener`. Bật RabbitMQ Management hoặc Prometheus plugin, Micrometer/Actuator, và instrumentation ở mục 6.

### Thí nghiệm 1 — Baseline khi hệ thống ổn định

Publish 100 event/giây với 2 consumer, mỗi event xử lý trong khoảng 10–20 ms (giả lập bằng test handler). Ghi ready/unacked, publish/ACK rate, handler p50/p95/p99 và receive age p50/p95/p99. Xác nhận chênh lệch theo thời gian, không chỉ một snapshot.

### Thí nghiệm 2 — Làm chậm handler

Thêm database call chậm hoặc sleep minh họa 300 ms trong handler **chỉ ở môi trường test**. Đối chiếu handler timer tăng trước, sau đó unacked/ready tăng nếu lượng vào vượt năng lực. Dùng trace để nhìn đúng đoạn DB/HTTP chậm.

### Thí nghiệm 3 — Tăng lượng publish

Giữ handler latency gần như không đổi, tăng tốc publish lên vượt khả năng xử lý. Quan sát ready tăng và receive-age tăng dù handler duration không thay đổi nhiều. Giải thích theo throughput/bottleneck.

### Thí nghiệm 4 — Thay đổi prefetch

Với handler tuần tự, thử `prefetch=1`, `prefetch=10` rồi `prefetch=100`. Theo dõi ready giảm/chuyển sang unacked ra sao, receive age có cải thiện không, và liệu có chênh lệch công bằng giữa consumers.

### Thí nghiệm 5 — Mất consumer

Dừng tất cả consumers nhưng tiếp tục publish. Ready tăng, **histogram handler không có sample mới**. Khi khởi động consumer trở lại, receive-age cao cho các message tồn đọng. Đây là ví dụ vì sao không thể đánh giá sức khỏe hệ thống chỉ từ timer của listener.

### Thí nghiệm 6 — Retry queue

Đặt một loại event luôn ném exception để đi qua retry queue TTL rồi quay lại work queue. So sánh `event age` tính từ publish gốc với độ chờ ở queue hiện tại. Quan sát redelivery/DLQ và không nhầm một lần retry 30 giây với handler 30 giây.

### Thí nghiệm 7 — Outbox chậm

Nếu producer có transactional outbox, cho relay tạm dừng sau khi DB đã commit. RabbitMQ queue có thể không có backlog, nhưng độ trễ từ `occurredAt` đến consumer vẫn tăng. Đo riêng outbox pending age và producer publish-to-listener age.

### Thí nghiệm 8 — Clock skew

Trong môi trường test, mô phỏng producer timestamp nhanh hơn consumer 5 giây (có thể chỉnh **giá trị header** thay vì thay clock máy). Xác nhận metric `invalid_timestamp` tăng, không ghi một age âm thành 0. Sửa timestamp/đồng bộ clock rồi kiểm tra lại.

### Thí nghiệm 9 — Consumer crash trước ACK

Cho business DB commit nhưng khiến channel/consumer mất kết nối trước ACK (test fault injection). Message có thể redeliver. Theo dõi tỷ lệ duplicate/redelivery và chứng minh idempotent handler không tạo hóa đơn hai lần; đừng xem một handler success timer là bảo đảm ACK đã đến broker.

### Thí nghiệm 10 — SLO và cảnh báo đa tín hiệu

Đặt SLO publish-to-listener p95 và handler p95 phù hợp lab. Tạo ba kịch bản: queue backlog, handler chậm, prefetch quá lớn. Xác nhận alert có thể phân biệt nguyên nhân bằng ready/unacked/latency thay vì cùng phát một thông báo “RabbitMQ slow”.

**Tiêu chí đạt:** Học viên phân biệt queue residence thật với publish-to-listener proxy; đọc đúng ready/unacked, đo handler bằng monotonic clock, nhận ra tác động prefetch/retry/outbox, và thiết kế dashboard/SLO không bị sai vì thiếu sample hoặc clock skew.

## 14. Những ngộ nhận phổ biến

| Nhận định sai | Điều đúng cần nhớ |
|---|---|
| “`@RabbitListener` chạy 50 ms nên end-to-end latency là 50 ms.” | Message có thể đã chờ nhiều giây trong broker, client buffer hoặc outbox. |
| “`messages_ready=0` nghĩa là hệ thống không backlog.” | Message có thể đang unacked/prefetched hoặc chờ ở retry/outbox. |
| “`messages_unacked` đều đang thực thi trong Java code.” | Một phần có thể nằm trong consumer buffer do prefetch. |
| “Header timestamp của producer là thời điểm broker enqueue.” | Đó là thời điểm producer tự gắn; network/routing chưa diễn ra. |
| “`now - publishedAt` là queue waiting time chính xác.” | Đây là publish-to-listener age với clock skew và nhiều thành phần khác. |
| “Giảm ready bằng tăng prefetch chắc chắn giảm latency.” | Có thể chỉ chuyển chờ sang client, unacked tăng. |
| “Micrometer listener timer đo thời gian message nằm trong queue.” | Timer thường đo thời gian listener thực thi, không phải queue residence. |
| “Lấy p95 queue + p95 handler = p95 end-to-end.” | Percentile không cộng đơn giản; đo end-to-end trực tiếp. |
| “Nếu histogram age đẹp thì không backlog.” | Các message chưa tới listener không tạo sample; phải xem queue depth. |
| “Retry message có age cao nghĩa là queue work đang chậm.” | Age có thể bao gồm thời gian ở retry queue và các lần xử lý trước. |
| “System.currentTimeMillis là đủ để đo chính xác giữa mọi máy.” | Đồng hồ có skew; cần đồng bộ và sanity checks. |
| “Tăng consumer luôn giảm thời gian xử lý.” | Có thể tăng DB contention, mất ordering và làm p99 xấu hơn. |

## 15. Câu hỏi tự kiểm tra

1. Phân biệt `t3 - t2` với `t5 - t4` trong timeline là gì?
2. Nếu `messages_ready` tăng nhưng handler p95 không đổi, giả thuyết nào hợp lý hơn: từng handler chậm đi hay tổng throughput không theo kịp?
3. Vì sao một message đã chuyển từ `ready` sang `unacked` vẫn có thể chưa vào handler?
4. Vì sao `nowConsumer - timestampProducer` không phải thời gian chờ trong queue chính xác?
5. Khi `defaultRequeueRejected=true` và message bị requeue nhiều lần, timestamp gốc có thể ảnh hưởng biểu đồ age thế nào?
6. Một queue có 0 ready nhưng listener stopped, chỉ dựa vào handler timer có báo được sự cố không?
7. Lý do gì khiến `System.nanoTime()` phù hợp hơn `currentTimeMillis()` để đo duration **trong một JVM**?
8. Có thể cộng hai giá trị p95 để ra p95 của tổng độ trễ không?
9. Nếu DB commit thành công nhưng mất ACK broker, metric handler success chứng minh điều gì và không chứng minh điều gì?
10. Vì sao phải xem `messages_ready`/`unacked` cùng histogram latency thay vì chỉ xem histogram?

**Đáp án gợi ý:** (1) queue waiting và business processing; (2) thiếu throughput/capacity; (3) prefetch/consumer buffer/dispatch; (4) gồm publish, network, routing, broker wait, client wait, clock skew; (5) age tăng qua nhiều lần thử; (6) không, cần health/consumer count; (7) monotonic elapsed time; (8) không; (9) handler hoàn tất nhưng ACK có thể chưa được broker ghi nhận; (10) tránh survivorship bias và tách chờ với xử lý.

## 16. Tổng kết

**Độ trễ chờ trong queue** là thời gian message nằm ở broker queue trước delivery; **thời gian xử lý** là thời gian code nghiệp vụ chạy; còn **độ trễ đầu-cuối** có thể bao gồm outbox, publish, routing, queue waiting, prefetch, xử lý và ACK. Không được gọi phép đo `publishedAt → @RabbitListener` là queue residence thuần: đó là **publish-to-listener age**, một proxy hữu ích nhưng chứa nhiều phần và phụ thuộc đồng hồ.

Với Spring AMQP, hãy đo handler duration bằng Micrometer/Observation, gắn timestamp có nguồn rõ ràng cho message age, theo dõi `messages_ready` và `messages_unacknowledged` trên RabbitMQ, cùng publish/ACK rates, redelivery, retry và DLQ. Chỉ khi **metrics về số lượng, tốc độ và độ trễ** được đặt cạnh nhau, đội ngũ mới phân biệt được queue backlog, consumer buffer, slow business processing và sự cố downstream — từ đó tối ưu hệ thống bất đồng bộ đúng nơi.

### Tài liệu tham khảo

- [RabbitMQ — Monitoring](https://www.rabbitmq.com/docs/monitoring): queue metrics `messages_ready`, `messages_unacknowledged`, publish/deliver rates.
- [RabbitMQ — Monitoring with Prometheus and Grafana](https://www.rabbitmq.com/docs/prometheus): Prometheus metrics và detailed queue metrics.
- [RabbitMQ — Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch): message unacknowledged và tác động prefetch.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ACK, redelivery và publisher confirm.
- [Spring AMQP — Micrometer Integration](https://docs.spring.io/spring-amqp/reference/3.2/amqp/receiving-messages/micrometer.html): listener timers và tags.
- [Spring AMQP — Micrometer Observation](https://docs.spring.io/spring-amqp/reference/3.2/amqp/receiving-messages/micrometer-observation.html): observation cho RabbitTemplate/listener containers.
- [Spring AMQP — Observability Metrics](https://docs.spring.io/spring-amqp/reference/3.2/appendix/micrometer.html): tên observation metric và conventions.

