# Publisher confirm bất đồng bộ và số publish đang chờ

Khi hệ thống dùng **Spring AMQP** liên tục gửi hàng nghìn sự kiện tới RabbitMQ, cách chờ **publisher confirm** quyết định đáng kể tới throughput, bộ nhớ và khả năng phục hồi khi broker chậm. Một publisher gọi `RabbitTemplate.convertAndSend(...)` rồi chặn thread để đợi broker xác nhận **từng message** sẽ khó tận dụng đường truyền. Ngược lại, publisher gửi không giới hạn và chỉ kiểm tra confirm sau đó có thể tích lũy rất nhiều message **đang chờ kết quả** (*outstanding/in-flight publishes*).

Giải pháp là kết hợp **publisher confirms bất đồng bộ**, **đối chiếu mỗi kết quả với từng lần gửi**, và **giới hạn số publish chưa có kết luận** bằng một *in-flight window* kèm backpressure. Khi broker trả ACK/NACK hoặc return, ứng dụng xử lý nhanh kết quả, giải phóng slot và cho phép những publish mới. Với kết quả không chắc chắn, hệ thống phải có retry có kiểm soát và event ID ổn định để chịu được duplicate.

Bài thuộc chương **Hiệu năng** của module **SPRING_AMQP**. Ta sử dụng `RabbitTemplate`, `CorrelationData`, `CompletableFuture`, exchange/queue/binding, publisher confirms/returns, metrics và outbox để tìm điểm cân bằng giữa **throughput, latency, độ tin cậy và lượng message đang chờ**. Các ví dụ chính hướng tới Java 17+, Spring Boot 3.x và Spring AMQP 3.x; khi áp dụng với phiên bản khác, cần đối chiếu API tương ứng.

## 1. Vấn đề: gửi một message rồi chờ ACK ngay

Giả sử hệ thống cần gửi 3.000 sự kiện đặt hàng mỗi giây tới durable queue. Để bảo đảm broker đã xử lý publish, producer có thể dùng correlated confirm:

```java
CorrelationData correlation =
        new CorrelationData(UUID.randomUUID().toString());

rabbitTemplate.convertAndSend(
        "orders.events", "orders.created", eventJson, correlation);

CorrelationData.Confirm confirm =
        correlation.getFuture().get(10, TimeUnit.SECONDS);
```

Code này đúng về mặt **chờ một lần gửi**, nhưng nếu đặt trong vòng lặp và `get(...)` ngay sau mỗi `convertAndSend` thì những lần gửi sẽ bị **serialize bởi thời gian đợi confirm**:

```text
Đợi confirm từng message:

send M1 ---[chờ ACK 100 ms]---> send M2 ---[chờ ACK 100 ms]---> send M3
         không gửi M2 khi M1 chưa có ACK

Confirm bất đồng bộ có giới hạn:

send M1 ---\
send M2 ----+----> các publish đang chờ (ví dụ tối đa 128)
send M3 ---/          |        |        |
                    ACK M2   ACK M1   ACK M3
                      |        |        |
                 giải phóng slot, nhận publish tiếp theo
```

Nếu mỗi lần chờ mất trung bình 100 ms, một thread **gửi rồi chờ tuần tự** chỉ có khả năng khoảng 10 lượt xác nhận/giây theo mô hình đơn giản. Đây **không phải** giới hạn của RabbitMQ: thời gian confirm của các publish có thể chồng lấp, broker xử lý theo batch và ứng dụng có thể sử dụng nhiều channels. Gửi bất đồng bộ giúp tăng lượng công việc có thể tiến triển trong khi chờ kết quả.

Tuy nhiên, `RabbitTemplate.convertAndSend` gọi bất đồng bộ theo nghĩa **không chờ publisher confirm**, chứ **không bảo đảm mọi lần gửi đều non-blocking**: lấy channel, network I/O, resource contention, connection loss hoặc publisher-side backpressure vẫn có thể làm lời gọi chậm hoặc ném lỗi.

## 2. Publisher confirm xác nhận điều gì?

Trong AMQP 0-9-1, một channel bật confirm mode sẽ nhận các kết quả từ broker:

- **`basic.ack` (publisher ACK):** broker xác nhận một hoặc nhiều publish theo semantics queue/độ bền hiện hành.
- **`basic.nack` (publisher NACK):** broker không thể xử lý một hoặc nhiều publish; trường hợp broker-generated NACK là ngoại lệ tương đối hiếm.
- **`basic.return`:** message gửi tới exchange tồn tại nhưng **không được định tuyến** tới queue nào khi `mandatory=true`, trừ các cơ chế routing fallback liên quan.
- **Channel/connection failure:** kết quả publish có thể bị mất hoặc không chắc chắn.

### 2.1. ACK không có nghĩa consumer đã xử lý

```text
          publisher                       RabbitMQ                      consumer
              |                              |                              |
              | --- basic.publish ---------->|                              |
              |                              |  định tuyến/persist          |
              |<--- publisher basic.ack -----|                              |
              |                              | --- basic.deliver ---------->|
              |                              |                           xử lý DB
              |                              |<--- consumer basic.ack ------|
```

Publisher ACK xảy ra ở phía **broker → publisher**, còn consumer ACK ở phía **consumer → broker**. Chúng độc lập. Publisher không được đánh dấu “đã cập nhật database downstream” chỉ vì nhận ACK.

Đối với persistent message được route vào durable queue, RabbitMQ xác nhận sau khi đáp ứng semantics persistence của queue đó; quorum queue có yêu cầu quorum tương ứng. Confirm latency vì vậy phụ thuộc loại queue, đường đĩa, replication, trạng thái node và batching. Không so sánh throughput một queue transient với quorum queue durable rồi quy kết chỉ do cấu hình publisher.

### 2.2. Mandatory return có thể đi cùng publisher ACK

Với exchange tồn tại nhưng routing key không khớp binding, `mandatory=true` làm broker trả `basic.return`, điển hình là `312 NO_ROUTE`. Broker sau đó **vẫn có thể publisher ACK**, vì nó đã xử lý publish và xác định không có nơi nhận.

Trong Spring AMQP, khi bật **correlated confirms + returns**, `CorrelationData.getReturn()` được điền **trước** khi confirm future hoàn tất ACK. Hành vi này cho phép callback kiểm tra đồng thời:

```java
correlation.getFuture().whenComplete((confirm, error) -> {
    if (error != null) {
        // Chưa xác định được kết quả như mong muốn.
    } else if (!confirm.isAck()) {
        // Broker/framework báo negative confirm.
    } else if (correlation.getReturn() != null) {
        // ACK nhưng message unroutable.
    } else {
        // Broker ACK, không có mandatory return.
    }
});
```

**Không gọi ACK + no-return là exactly-once:** nó không bảo đảm downstream consumer đã hoàn tất nghiệp vụ và không bảo đảm message sẽ không bị nhận lại.

### 2.3. Confirm trên channel không phải một thứ tự hoàn tất nghiệp vụ

RabbitMQ có thể xác nhận nhiều publish cùng lúc qua trường `multiple` ở mức AMQP 0-9-1. Kết quả confirm về bất đồng bộ và không nên giả định thứ tự callback luôn trùng hoàn toàn thứ tự message đã gửi. Spring AMQP xử lý chi tiết sequence/`multiple` để hoàn tất các correlated confirmations; ứng dụng nên dùng `CorrelationData` gắn với **publish attempt** thay vì suy theo vị trí trong danh sách gửi.

**Channel không tồn tại hoặc exchange bị sai:** Publish đến exchange chưa khai báo có thể gây `404 NOT_FOUND` và channel close, rồi Spring báo lỗi đồng bộ hoặc negative confirm với reason. Không nhầm tình huống này với `NO_ROUTE` return.

## 3. “Số publish đang chờ” nghĩa là gì?

Từ **in-flight/outstanding** có thể nói tới nhiều phạm vi khác nhau:

| Phạm vi | Định nghĩa | Ai quản lý? |
|---|---|---|
| Application pending publish | Ứng dụng đã gửi/đang thực hiện lần gửi nhưng chưa phân loại ACK/NACK/return/lỗi | Outbox relay / publisher service |
| Unconfirmed publish phía AMQP channel | Publish đã được broker/client ghi nhận theo confirm mode nhưng chưa có confirm | RabbitMQ Java client / Spring Rabbit |
| Network/write buffer | Bytes đang chờ đi qua socket hoặc hệ điều hành | Client, kernel, network |
| Broker queue `messages_ready` | Message đã nằm trong queue đợi delivery | RabbitMQ broker |
| Broker `messages_unacknowledged` | Message đã giao cho consumer nhưng chưa consumer ACK | RabbitMQ consumer side |
| Outbox pending | Ý định publish lưu DB chưa được hoàn tất theo quy tắc hệ thống | Database/outbox relay |

**Application pending không đồng nghĩa broker unconfirmed tuyệt đối**: một lời gọi send có thể chưa hoàn tất, một channel có thể đã đóng, hoặc timeout xảy ra khi broker đã nhận. Cần định nghĩa rõ metric dùng ranh giới nào.

Đặc biệt, **consumer prefetch** giới hạn delivery chưa ACK từ broker đến **consumer**, không giới hạn outstanding publishes của **producer**. Tăng hoặc giảm `prefetchCount` không phải cách trực tiếp điều khiển số publisher confirms đang chờ.

### 3.1. Vì sao không thể giữ số pending vô hạn?

Mỗi publish pending có thể khiến ứng dụng lưu:

- `CorrelationData` và `CompletableFuture`.
- Callback, dữ liệu tracing/metadata.
- Bản sao payload cần retry.
- Timestamps để đo confirm latency.
- Tham chiếu tới outbox row hoặc event ID.
- Tài nguyên channel, connection hoặc buffer tùy thiết kế.

Khi broker chậm hoặc mất kết nối, tốc độ publish tiếp tục cao trong khi confirmations ngừng về, số đối tượng pending tăng, làm heap/GC và downstream queue bị áp lực. Trường hợp xấu có thể dẫn đến OutOfMemoryError, rồi ứng dụng mất cả khả năng xác định những publish đang chờ.

**Giới hạn in-flight** là một cơ chế **backpressure ở phía publisher**. Khi đạt ngưỡng, hệ thống không gửi vô hạn; nó đợi, trả trạng thái overload, dừng poll outbox, hoặc hoãn nhận thêm công việc theo chính sách.

## 4. Chọn kích thước cửa sổ bằng throughput và confirm latency

Trong điều kiện tải tương đối ổn định, có thể dùng trực giác từ **Little’s Law**:

\[
L \approx \lambda W
\]

Trong đó:

- \(L\): số publish đang chờ confirm trung bình.
- \(\lambda\): throughput publish/confirm ổn định (message/giây).
- \(W\): thời gian trung bình từ gửi đến confirm (giây).

Ví dụ mục tiêu **3.000 message/giây**, thời gian confirm **trung bình 120 ms**:

\[
L \approx 3000 \times 0.120 = 360
\]

Cửa sổ chỉ có 64 slots nhiều khả năng sẽ làm publisher phải chờ khi confirm latency như giả định; cửa sổ 512 có thêm khoảng trống cho biến động. **512 là giá trị thử nghiệm**, không phải ngưỡng khuyến nghị chung cho RabbitMQ.

Một ví dụ khác:

| Throughput kỳ vọng | Mean confirm latency | Outstanding trung bình ước lượng |
|---|---:|---:|
| 200 msg/s | 20 ms | 4 |
| 2.000 msg/s | 50 ms | 100 |
| 3.000 msg/s | 120 ms | 360 |
| 5.000 msg/s | 250 ms | 1.250 |

**Giới hạn của công thức:**

- Dùng **mean latency**, không lấy p95/p99 nhân throughput rồi gọi đó là \(L\) trung bình.
- Chỉ là quan hệ trong điều kiện tương đối ổn định; broker outage khiến pending tăng mà throughput confirm giảm về 0.
- Không phản ánh trực tiếp CPU, kích thước payload, số channel, loại queue, broker memory alarm hay disk throughput.
- Window quá nhỏ có thể làm ứng dụng thiếu cơ hội pipelining; quá lớn làm tăng lượng work chưa có kết quả và áp lực khi reconnect.
- Sau mỗi điều chỉnh phải đo **throughput thực, p95/p99 confirm latency, pending peak, error/return và heap**.

Cách chọn thực tế là bắt đầu bằng một window hữu hạn như 64/128/256 tùy workload, benchmark với topology và durability đúng production, rồi tăng dần cho đến khi throughput gần bão hòa hoặc latency/tài nguyên bắt đầu xấu đi.

## 5. Bật correlated confirms và mandatory returns trong Spring AMQP

### 5.1. Spring Boot configuration

```yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
```

Ba cấu hình có vai trò riêng:

1. `publisher-confirm-type: correlated` bật correlated publisher confirms cho `CachingConnectionFactory` do Spring Boot cấu hình.
2. `publisher-returns: true` cho phép Spring nhận returned message.
3. `template.mandatory: true` yêu cầu broker trả lại publish không có route phù hợp.

Trong ví dụ, ứng dụng tự khai báo topology đã có exchange và binding:

```java
@Configuration
public class OrdersTopology {

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange("orders.events");
    }

    @Bean
    Queue ordersCreatedQueue() {
        return QueueBuilder.durable("orders.created.work").build();
    }

    @Bean
    Binding ordersCreatedBinding(
            DirectExchange ordersExchange,
            Queue ordersCreatedQueue) {
        return BindingBuilder.bind(ordersCreatedQueue)
                .to(ordersExchange).with("orders.created");
    }
}
```

Import các kiểu thuộc `org.springframework.amqp.core.*`, `org.springframework.context.annotation.Bean` và `org.springframework.context.annotation.Configuration`. Cần có `RabbitAdmin` hoặc cách provision broker tương đương để exchange, queue, binding tồn tại trước khi publish.

**Để đối chiếu persistence:** Message nên đặt `deliveryMode=PERSISTENT`, queue durable và loại queue phù hợp cam kết. Chỉ có publisher confirm trên message transient gửi vào non-durable queue không chứng minh cùng độ bền với persistent message vào quorum queue.

### 5.2. Cấu hình thủ công nếu không dùng Boot autoconfiguration

```java
CachingConnectionFactory factory =
        new CachingConnectionFactory("localhost", 5672);

factory.setPublisherConfirmType(
        CachingConnectionFactory.ConfirmType.CORRELATED);
factory.setPublisherReturns(true);

RabbitTemplate rabbit = new RabbitTemplate(factory);
rabbit.setMandatory(true);
```

`CachingConnectionFactory` thuộc `org.springframework.amqp.rabbit.connection` và `RabbitTemplate` thuộc `org.springframework.amqp.rabbit.core`.

Khi có **nhiều ConnectionFactory**, hãy kiểm tra template thật đang dùng factory đã bật confirms/returns; cấu hình trên một bean khác không mang lại kết quả cho template hiện tại.

**Cảnh báo:** Publisher confirm mode không dùng đồng thời với AMQP transaction mode trên **cùng channel**. Không bật `channelTransacted=true` trên publisher confirm channel như một cách tăng độ tin cậy; đây là hai cơ chế khác nhau.

## 6. Ví dụ publisher bất đồng bộ tối thiểu

Spring AMQP cung cấp `CorrelationData.getFuture()` thuộc loại `CompletableFuture<CorrelationData.Confirm>`. Thay vì gọi `get()` ngay sau mỗi send, ta đăng ký `whenComplete` rồi tiếp tục công việc khác.

Một kết quả nghiệp vụ hữu ích nên **tách ACK + no return, NACK, return và unknown outcome**:

```java
public enum PublishState {
    ACK_NO_RETURN, // Broker ACK, không có returned message
    UNROUTABLE,    // Confirm ACK nhưng mandatory return
    NACK,          // Negative confirm
    UNKNOWN        // Không thể xác định chắc chắn kết quả
}

public record PublishResult(PublishState state, String detail) {
}
```

`RabbitTemplate` gửi JSON UTF-8 và cung cấp kết quả bất đồng bộ:

```java
@Service
public class AsyncConfirmPublisher {
    private final RabbitTemplate rabbit;

    public AsyncConfirmPublisher(RabbitTemplate rabbit) {
        this.rabbit = rabbit;
    }

    public CompletionStage<PublishResult> publish(
            String eventId, String json) {

        CorrelationData cd = new CorrelationData(
                UUID.randomUUID().toString()); // publish attempt ID
        CompletableFuture<PublishResult> result =
                new CompletableFuture<>();

        // Đăng ký trước khi publish để không bỏ sót confirm quá nhanh.
        cd.getFuture().whenComplete((confirm, error) -> {
            if (error != null || confirm == null) {
                result.complete(new PublishResult(
                        PublishState.UNKNOWN, "confirm chưa xác định"));
            } else if (!confirm.isAck()) {
                result.complete(new PublishResult(
                        PublishState.NACK, confirm.getReason()));
            } else if (cd.getReturn() != null) {
                var returned = cd.getReturn();
                result.complete(new PublishResult(
                        PublishState.UNROUTABLE,
                        returned.getReplyCode() + " " +
                        returned.getReplyText()));
            } else {
                result.complete(new PublishResult(
                        PublishState.ACK_NO_RETURN, null));
            }
        });

        try {
            rabbit.convertAndSend(
                    "orders.events", "orders.created", json,
                    message -> {
                        MessageProperties p =
                                message.getMessageProperties();
                        p.setMessageId(eventId);
                        p.setContentType(
                                MessageProperties.CONTENT_TYPE_JSON);
                        p.setDeliveryMode(
                                MessageDeliveryMode.PERSISTENT);
                        return message;
                    },
                    cd);
        } catch (AmqpException sendError) {
            // Lỗi đồng bộ không chứng minh broker chưa từng nhận.
            result.complete(new PublishResult(
                    PublishState.UNKNOWN,
                    sendError.getClass().getSimpleName()));
        }

        return result;
    }
}
```

Import tiêu biểu: `java.util.UUID`, `java.util.concurrent.CompletableFuture`, `java.util.concurrent.CompletionStage`, `org.springframework.stereotype.Service`, `org.springframework.amqp.AmqpException`, `org.springframework.amqp.core.MessageProperties`, `org.springframework.amqp.core.MessageDeliveryMode`, `org.springframework.amqp.rabbit.connection.CorrelationData` và `org.springframework.amqp.rabbit.core.RabbitTemplate`.

Đối tượng `result` được hoàn thành khi callback có kết quả; caller **không cần block**. Ví dụ:

```java
publisher.publish(event.eventId(), event.json())
        .thenAccept(outcome -> {
            // Chỉ ghi metric/log hoặc enqueue kết quả.
            // Tránh DB write chậm ở thread callback.
            System.out.println("publisher outcome=" + outcome.state());
        });
```

**Ý nghĩa của tính bất đồng bộ:** Ta không chờ publisher ACK sau mỗi lần gửi. Tuy nhiên, việc đăng ký callback không làm toàn bộ quá trình send “zero-cost”, và **không có giới hạn số pending** nếu tiếp tục gọi `publish(...)` hàng loạt. Bởi vậy đây chỉ là bước nền; mục tiếp theo sẽ thêm cửa sổ giới hạn.

**Độ tin cậy:** Nếu process crash khi chưa nhận confirm, `CompletableFuture`/callback nằm trong RAM sẽ biến mất. Khi cần đảm bảo sự kiện không bị quên, lưu ý định gửi trong **transactional outbox** hoặc durable store trước khi publish.

## 7. Giới hạn outstanding publishes bằng Semaphore

### 7.1. Thiết kế bounded window

Ý tưởng: Mỗi publish cần chiếm một **permit** trước khi gửi. Khi nhận **kết quả cuối** hoặc biết thao tác send thất bại tại client, permit được trả lại. Nếu không còn permit, caller **không gửi thêm**, trả tín hiệu backpressure cho upstream/outbox poller.

```text
                            boundedPublisher (window = 128)
                                       |
   outbox/publisher ----------> acquire permit? ---- no ----> BACKPRESSURE
                                       |
                                      yes
                                       |
                                       v
                                  RabbitTemplate
                                       |
                           publish attempt + CorrelationData
                                       |
                          broker confirm / return / exception
                                       |
                                       v
                            classify result + release permit
                                       |
                         next outbox event may be published
```

**Quan trọng:** Một `Semaphore` giới hạn **số lần gửi ứng dụng đang giữ slot**, không thay thế cơ chế broker confirms, publisher return hay lưu bền payload. Khi channel/connection kẹt không trả kết quả, các permit có thể không được giải phóng: cần watchdog/circuit breaker và recovery có chủ đích, không mở thêm publisher vô hạn.

### 7.2. Code BoundedConfirmPublisher

Ví dụ sau giữ window **128 publish attempts**, tách `eventId` nghiệp vụ và `attemptId` dành cho correlated confirms:

```java
@Service
public class BoundedConfirmPublisher {

    public enum State {
        ACK_NO_RETURN, UNROUTABLE, NACK, UNKNOWN, BACKPRESSURED
    }

    public record Result(State state, String reason) {}

    private final RabbitTemplate rabbit;
    private final Semaphore slots = new Semaphore(128);
    private final ConcurrentMap<String, Long> pending =
            new ConcurrentHashMap<>();

    public BoundedConfirmPublisher(RabbitTemplate rabbit) {
        this.rabbit = rabbit;
    }

    public CompletionStage<Result> publish(String eventId, byte[] json) {
        if (!slots.tryAcquire()) {
            // Không chặn thread; upstream sẽ hoãn poll / thử lại sau.
            return CompletableFuture.completedFuture(
                    new Result(State.BACKPRESSURED, "window full"));
        }

        String attemptId = UUID.randomUUID().toString();
        CorrelationData correlation = new CorrelationData(attemptId);
        CompletableFuture<Result> result = new CompletableFuture<>();
        AtomicBoolean released = new AtomicBoolean(false);
        pending.put(attemptId, System.nanoTime());

        // Idempotent cleanup: callback và catch có thể race.
        Runnable releaseOnce = () -> {
            if (released.compareAndSet(false, true)) {
                pending.remove(attemptId);
                slots.release();
            }
        };

        correlation.getFuture().whenComplete((confirm, error) -> {
            try {
                if (error != null || confirm == null) {
                    result.complete(new Result(
                            State.UNKNOWN, "confirm unavailable"));
                } else if (!confirm.isAck()) {
                    result.complete(new Result(
                            State.NACK, confirm.getReason()));
                } else if (correlation.getReturn() != null) {
                    result.complete(new Result(
                            State.UNROUTABLE,
                            correlation.getReturn().getReplyText()));
                } else {
                    result.complete(new Result(
                            State.ACK_NO_RETURN, null));
                }
            } finally {
                releaseOnce.run();
            }
        });

        try {
            MessageProperties p = new MessageProperties();
            p.setMessageId(eventId);
            p.setContentType(MessageProperties.CONTENT_TYPE_JSON);
            p.setDeliveryMode(MessageDeliveryMode.PERSISTENT);

            rabbit.send(
                    "orders.events",
                    "orders.created",
                    new Message(json, p),
                    correlation);
        } catch (RuntimeException sendError) {
            // Có thể có unknown outcome khi mạng/channel lỗi.
            result.complete(new Result(
                    State.UNKNOWN, sendError.getClass().getSimpleName()));
            releaseOnce.run();
        }

        return result;
    }

    public int pendingCount() {
        return pending.size();
    }

    public long oldestPendingAgeMillis() {
        long now = System.nanoTime();
        return pending.values().stream()
                .mapToLong(start ->
                        TimeUnit.NANOSECONDS.toMillis(now - start))
                .max()
                .orElse(0L);
    }
}
```

Các import chính:

```java
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;
```

**Điều cần chú ý khi dùng code:**

1. **Tách `eventId` và `attemptId`.** `eventId` cần ổn định qua retry để consumer deduplicate; `attemptId` mới cho mỗi lần publish để không nhầm callbacks của các lần gửi.
2. **Callback được đăng ký trước send.** Confirm đến nhanh vẫn được xử lý.
3. **`releaseOnce` sử dụng `AtomicBoolean`.** Lỗi send đồng bộ và callback bất đồng bộ có thể xảy ra gần nhau; nếu release hai lần, số permit sẽ vượt window và cơ chế giới hạn mất tác dụng.
4. **`tryAcquire` không block.** Caller nhận `BACKPRESSURED` và phải **hoãn work**, không xoay vòng retry ngay trong một hot loop.
5. **Không giữ payload trong `pending`.** Bản payload cần retry nên nằm ở outbox/durable store, không phải trong map vô hạn của JVM. Pending chỉ giữ `attemptId` và thời gian phục vụ giám sát.
6. **Sync exception được phân loại UNKNOWN thận trọng.** Một số lỗi cấu hình là lỗi vĩnh viễn, một số lỗi truyền thông khiến broker có thể đã nhận; component phân loại ở tầng điều phối cần xem exception và có chính sách riêng, không tự động gửi lại vô hạn.
7. **Không có confirm mãi mãi** sẽ giữ permit mãi mãi. Mẫu trên cần watchdog, timeout policy, shutdown coordination hoặc connection recovery trước khi dùng production.
8. **Window này ở cấp một bean/JVM**, không phải giới hạn toàn cluster. Nếu chạy 10 replicas, mỗi replica 128 permits thì tổng số publish pending của hệ thống có thể cao hơn nhiều.

`pendingCount()` là **số attempt ứng dụng đang chờ**. Nó không tương đương số broker-side outstanding unconfirmed tuyệt đối nếu kết quả bị mất do lỗi đường truyền.

### 7.3. Tích hợp với outbox poller

Một outbox relay có thể lấy các row `NEW/RETRY` từ database và gọi `BoundedConfirmPublisher.publish(...)`. Khi kết quả:

| Kết quả | Hành động ở outbox |
|---|---|
| `ACK_NO_RETURN` | Nếu quy tắc định tuyến đúng, ghi `SENT`; lưu thời điểm xác nhận |
| `UNROUTABLE` | Không đánh dấu `SENT`; sửa routing/topology, quarantine hoặc retry có điều kiện |
| `NACK` | Ghi retry có backoff theo loại lỗi; giữ event ID |
| `UNKNOWN` | Coi là publish **chưa chắc chắn**, không tự gán “chưa gửi”; retry idempotent khi recovery |
| `BACKPRESSURED` | Để row chờ lần poll sau, không coi là lỗi broker của message |

**Không cập nhật database chậm ngay trong confirm callback.** Callback nên ghi metric, chuyển kết quả sang hàng đợi công việc hoặc executor giới hạn, rồi worker khác cập nhật outbox. Nếu worker dùng executor không bền, cần có cơ chế đối soát row đang `IN_FLIGHT` bằng lease/recovery để không mất kết quả khi process crash.

Nếu outbox dùng `FOR UPDATE SKIP LOCKED` để claim row, hãy gắn ownership token/lease để kết quả publish cũ không được phép cập nhật nhầm row đã được một worker khác claim sau timeout.

## 8. Timeout: không có confirm không có nghĩa broker chưa nhận

### 8.1. Một failure window kinh điển

```text
Publisher                  RabbitMQ
    |                         |
    |-- publish event E ----->|
    |                         | lưu message thành công
    |                         |
    |<-- ACK (mất mạng) -------X
    |
    | chờ confirm quá hạn
    | outcome = UNKNOWN
    |
    |-- retry cùng event E --->|  có thể thêm bản thứ hai
    |                         |
    +--- consumer phải idempotent (eventId E)
```

Ứng dụng **không được** coi timeout là broker NACK, và không được khẳng định message chưa vào queue. Vì thế:

- **Business event ID giữ nguyên** trong mọi lần retry.
- **Mỗi lần publish dùng attempt/correlation ID mới** để quan sát.
- **Outbox row vẫn chưa `SENT`** khi chưa có kết luận xác nhận phù hợp.
- **Consumer lưu dấu vết eventId** cùng DB transaction để redelivery/retry không gây side effect hai lần.
- Phân biệt timeout do broker/network với lỗi không có exchange, routing key sai hoặc credential không hợp lệ để tránh retry vô hạn.

### 8.2. Vì sao không tự động release permit ở mọi timeout?

Một cách làm nguy hiểm:

```java
// Pseudocode không nên sao chép máy móc:
future.orTimeout(5, TimeUnit.SECONDS)
      .whenComplete((confirm, error) -> slots.release());
```

`CompletableFuture.orTimeout(...)` có thể hoàn tất future theo timeout trong khi broker **vẫn đang xử lý** publish và chưa trả confirm. Nếu ứng dụng release slot sau timeout rồi tiếp tục gửi nhanh, số publish thực sự đang chờ ở tầng client/broker có thể **lớn hơn window đã cấu hình**. Thêm nữa, timeout trên chính future có thể làm ứng dụng không còn nhận được kết quả muộn theo cách dự định.

Một chính sách an toàn hơn:

1. **Đo tuổi attempt và phát cảnh báo** khi vượt confirm timeout/SLO.
2. **Tạm dừng publish mới (circuit breaker)** nếu outstanding quá già hoặc kết nối không còn đáng tin; không mở thêm unlimited retries.
3. **Quyết định recovery ở cấp connection/channel** để các outstanding attempts được phân loại/huỷ theo semantics của client/framework; cần kiểm thử việc đóng/reset publisher connection trước khi cho phép gửi tiếp.
4. Giữ trạng thái outbox **UNKNOWN/RETRYABLE**, không xóa business event.
5. Sau khi hạ tầng ổn định, retry với stable event ID và consumer idempotent.
6. Chỉ giải phóng resource một cách an toàn khi attempt đã được kết luận hoặc hạ tầng sở hữu attempt đã được xử lý như một failure boundary.

**Điểm cân bằng:** Không để permit kẹt vô hạn, nhưng cũng không phát hành vô hạn permit mỗi khi timer hết hạn trong khi socket/broker vẫn treo. Phần code ở mục 7 mới là **khung giới hạn in-flight**, cần watchdog/circuit breaker và lifecycle handling hoàn chỉnh ở production.

### 8.3. Không retry trực tiếp trên callback thread

`CompletableFuture.whenComplete` có thể chạy trên thread hoàn tất future; Spring AMQP callbacks thường được điều phối qua executor của connection factory hoặc thread đã hoàn tất future. Callback có thể nằm trên luồng nhạy cảm với latency của việc xử lý confirms.

Không nên thực hiện trong callback:

- Ghi database blocking quá lâu.
- Gọi HTTP API hoặc chờ lock nghiệp vụ.
- Chờ đồng bộ một publisher confirm khác.
- `Thread.sleep` rồi retry ngay trên cùng callback.
- Publish vô hạn khi broker đang down.

Thay vào đó, callback **chỉ phân loại kết quả, ghi metric/gửi tín hiệu**. Retry là công việc của relay/scheduler giới hạn, dựa trên dữ liệu bền vững. `thenApplyAsync/whenCompleteAsync` với **executor riêng có giới hạn** là một lựa chọn để tách hậu xử lý nặng khỏi confirm callback, nhưng không nên tạo unbounded task queue mới để thay thế vấn đề outstanding publishes.

## 9. Một số cách publish khác và đánh đổi

RabbitMQ phân biệt ba cách phổ biến:

| Phương án | Cơ chế | Ưu điểm | Hạn chế |
|---|---|---|---|
| **Publish rồi chờ confirm từng message** | Mỗi lần gửi lại gọi `get` hoặc `waitForConfirms` | Dễ hiểu, dễ debug | Throughput thấp khi confirm latency lớn |
| **Publish theo batch rồi đợi** | Gửi N message, chờ batch confirms, tiếp tục | Hiệu năng khá hơn; code tương đối đơn giản | Batch bị chặn cho đến khi chờ xong; retry batch dễ tạo duplicate |
| **Publish và xử lý confirms bất đồng bộ** | Tạo correlation/future/callback cho từng attempt | Pipelining tốt, giảm thời gian idle | Cần bounded window, error classification, timeout/recovery, metrics |

**Không dùng publisher confirms để thay đổi ý nghĩa giao dịch DB.** Chờ từng confirm không làm DB update + publish thành một transaction. Với dual-write và độ tin cậy nghiệp vụ, transactional outbox vẫn là lựa chọn phù hợp.

### 9.1. Batch gửi và chờ một điểm barrier

Ví dụ minh họa một batch 100 message: gửi với 100 `CorrelationData` rồi đợi `CompletableFuture.allOf(...)` trong test/tool hoặc luồng batch worker:

```java
List<CorrelationData> attempts = new ArrayList<>();

for (int i = 0; i < 100; i++) {
    CorrelationData cd =
            new CorrelationData(UUID.randomUUID().toString());
    attempts.add(cd);
    rabbitTemplate.convertAndSend(
            "orders.events", "orders.created",
            "{\"batchIndex\":" + i + "}",
            cd);
}

CompletableFuture<?>[] futures = attempts.stream()
        .map(CorrelationData::getFuture)
        .toArray(CompletableFuture[]::new);

CompletableFuture.allOf(futures)
        .get(15, TimeUnit.SECONDS);

for (CorrelationData cd : attempts) {
    var confirm = cd.getFuture().join();
    if (!confirm.isAck() || cd.getReturn() != null) {
        // Phân loại riêng message không có kết quả tốt.
    }
}
```

`allOf` chỉ cho biết các futures đã hoàn tất **bình thường** khi nó trả về thành công; vẫn phải kiểm tra từng `confirm.isAck()` và `getReturn()`. Nếu timeout, **một số publish có thể đã thành công**: không đánh dấu cả batch “chưa gửi” hoặc retry bừa toàn bộ mà không có idempotency.

Batch ở đây có barrier chờ chung và dễ hiểu; bounded asynchronous window thường phù hợp hơn với relay lưu lượng liên tục.

### 9.2. RabbitTemplate và channel cache

`CachingConnectionFactory` quản lý các channels và cache để hạn chế chi phí tạo channel. Theo Spring AMQP, các channels có outstanding correlated confirms được xử lý thận trọng: từ Spring AMQP 2.1, channel không được trả về cache để dùng như bình thường khi còn confirms chưa được giải quyết; với RabbitTemplate, **thông thường chỉ một outstanding confirm trên một physical channel tại một thời điểm** theo cơ chế logical close.

Vì vậy, tăng window từ 128 lên 4.096 không đồng nghĩa trên **một channel** sẽ có 4.096 confirms song song như ví dụ với native Java client. Spring có thể sử dụng nhiều channels/tài nguyên; phải đo channel churn, connection/channel cache và áp lực broker.

**Đừng nhầm `channelCacheSize` với một hard cap tuyệt đối cho số channels:** `CachingConnectionFactory` quản lý cache, còn giới hạn/bottleneck thực tế phụ thuộc mode và cấu hình. Khi cần giới hạn publish, hãy dùng bounded window/worker pool, giám sát channel count và sizing theo kết quả benchmark.

Một số connection factory khác không hỗ trợ **correlated publisher confirms** như `PooledChannelConnectionFactory` trong cấu hình được tài liệu Spring AMQP mô tả. Không tự đổi loại factory để “pooling nhanh hơn” rồi mất tính năng correlated confirms; kiểm tra tính năng của factory và phiên bản đang dùng.

## 10. Đo confirm latency và pending bằng Micrometer

Để tối ưu, cần ít nhất **hai chiều**: số publish đang chờ và thời gian từ send đến confirm.

### 10.1. Bộ metrics đề xuất

| Metric ứng dụng | Loại | Ý nghĩa |
|---|---|---|
| `app.rabbit.publisher.inflight` | Gauge | Số publish attempts đang chiếm slots |
| `app.rabbit.publisher.oldest_inflight.age` | Gauge | Tuổi attempt lâu nhất chưa có kết luận |
| `app.rabbit.publisher.confirm.duration` | Timer/histogram | Từ gọi publish đến confirm/return xử lý xong |
| `app.rabbit.publisher.outcome.total` | Counter | Số ACK_NO_RETURN, NACK, UNROUTABLE, UNKNOWN, BACKPRESSURED |
| `app.rabbit.publisher.backpressure.total` | Counter | Số lần window đầy, upstream phải hoãn gửi |
| `app.rabbit.publisher.send.error.total` | Counter | Số lỗi đồng bộ khi gọi RabbitTemplate |
| `app.rabbit.publisher.confirm.timeout.total` | Counter | Số attempt vượt ngưỡng tuổi chờ xác nhận |
| `app.rabbit.publisher.retry.total` | Counter | Số attempt retry từ outbox |
| `app.rabbit.outbox.pending` | Gauge | Số event intents chưa hoàn thành |
| `app.rabbit.outbox.oldest.age` | Gauge | Tuổi event chờ relay lâu nhất |
| `app.rabbit.publisher.throughput` | Counter/rate | Publish attempts/s và confirmed publish/s tách biệt |

Không gắn `eventId`, `attemptId` hoặc payload vào metric tags vì cardinality cao. Dùng nhãn hữu hạn như `service`, `destination`, `result`, `queue_type`; ID cụ thể thuộc **structured log/tracing**.

### 10.2. Ghi Gauge và Timer

Sử dụng component `BoundedConfirmPublisher`:

```java
@Configuration
public class PublisherMetricsConfig {
    @Bean
    MeterBinder publisherMeterBinder(
            BoundedConfirmPublisher publisher) {

        return registry -> {
            Gauge.builder("app.rabbit.publisher.inflight",
                            publisher,
                            BoundedConfirmPublisher::pendingCount)
                    .register(registry);

            Gauge.builder("app.rabbit.publisher.oldest_inflight.age",
                            publisher,
                            p -> p.oldestPendingAgeMillis() / 1000.0)
                    .baseUnit("seconds")
                    .register(registry);
        };
    }
}
```

Các import: `io.micrometer.core.instrument.Gauge`, `io.micrometer.core.instrument.binder.MeterBinder`, `org.springframework.context.annotation.Configuration` và `org.springframework.context.annotation.Bean`.

Đo duration bằng monotonic clock để tránh wall-clock drift:

```java
long startNanos = System.nanoTime();

correlation.getFuture().whenComplete((confirm, error) -> {
    long elapsed = System.nanoTime() - startNanos;
    confirmTimer.record(elapsed, TimeUnit.NANOSECONDS);
    // Đếm ACK/NACK/return; sau đó giải phóng permit.
});
```

Đặt `Timer.builder(...).publishPercentileHistogram()` trong initialization (không tạo meter mới mỗi message). Khi callback hoàn tất bất thường hoặc connection recovery thất bại, cần có metric phân biệt **UNKNOWN**/timeout thay vì lặng lẽ bỏ sample.

**Chú ý:** Timer của `RabbitTemplate`/Micrometer Observation có thể đo phạm vi send method, **không mặc định là thời gian chờ correlated publisher confirm**. Muốn phân tích confirm RTT, phải đo riêng từ mốc publish attempt đến lúc future confirm được hoàn tất. Nên dùng `System.nanoTime()` trong **một JVM**; không so sánh trực tiếp nanos giữa các process.

### 10.3. Đặt RabbitMQ broker metrics cạnh application metrics

Dashboard hữu ích nên hiển thị:

- Publish attempts/s, confirmed/s và ratio ACK/NACK/return.
- Pending window usage: `inflight / configuredWindow`, oldest pending age.
- Publisher confirm RTT p50/p95/p99 và số timeout.
- Broker connections/channels, flow control/connection blocked, disk/memory alarms.
- Queue ready, messages unacknowledged, redelivery và consumer ACK rate.
- Outbox pending count/oldest age và số bản ghi `RETRY`.
- JVM heap, GC pauses, thread pools và CPU.
- End-to-end event age từ domain commit tới consumer DB commit.

Nếu broker đang bị **memory/disk alarm**, việc chỉ tăng số outstanding sẽ làm tình trạng tệ hơn. Confirm RTT và pending cùng tăng là tín hiệu cần **giảm tốc gửi**, không phải cứ tăng window.

## 11. Benchmark: tìm điểm cân bằng throughput–latency

### 11.1. Thiết kế phép đo công bằng

Một benchmark hữu ích phải cố định:

1. **Topology**: classic durable queue hay quorum queue, số replicas, binding/fan-out.
2. **Delivery mode**: persistent hay transient.
3. **Kích thước message**: 1 KiB, 10 KiB, 100 KiB... có thể cho kết quả rất khác.
4. **Số publisher instances/threads và channels**.
5. **Network**: cùng LAN, qua vùng mạng, TLS, bandwidth.
6. **Consumers**: có đang đọc/ACK hay queue tích lũy ready?
7. **Workload**: constant rate hay burst, thời gian warm-up và số mẫu.
8. **Cách đo**: throughput confirmed, confirm mean/p95/p99, unknown outcomes, peak pending và heap.

Không so sánh “100.000 messages/giây” của broker test transient local với production quorum queue persistent qua WAN rồi coi là chỉ số kỳ vọng.

### 11.2. Kế hoạch thí nghiệm nhiều window

| Lần thử | In-flight limit | Điều cần ghi |
|---|---:|---|
| A | 1 | Baseline gần kiểu send-and-wait |
| B | 16 | Thay đổi throughput và confirm RTT |
| C | 64 | Bắt đầu thấy lợi ích pipelining |
| D | 128 | Pending/heap/channel utilization |
| E | 256 | Throughput tăng tiếp hay bão hòa? |
| F | 512 | Confirm p99, broker alarms và backpressure |

Các giá trị là **bậc thử nghiệm**, không phải đề xuất mặc định. Để quyết định window production, xét cả **khả năng chịu outage**: nếu broker treo, bao lâu window đầy, upstream có dừng được không, outbox có tồn đủ lâu không.

**Tín hiệu dừng tăng window:** throughput không còn tăng đáng kể nhưng confirm latency tail, số channels, heap, broker alarms hoặc retry tăng. Khi ấy tối ưu bottleneck thực (disk, quorum replication, network, payload, concurrency hoặc DB) thay vì tiếp tục tăng số pending.

### 11.3. Đọc đúng kết quả

Ví dụ giả định cùng topology và payload:

| Window | Confirmed throughput | p95 confirm | Pending peak | Nhận xét |
|---|---:|---:|---:|---|
| 1 | 45 msg/s | 25 ms | 1 | Đợi từng confirm |
| 32 | 950 msg/s | 40 ms | 32 | Pipelining giúp throughput |
| 128 | 2.900 msg/s | 65 ms | 127 | Tiến gần mục tiêu |
| 512 | 3.050 msg/s | 210 ms | 480 | Thêm pending nhưng ít throughput |
| 2.048 | 3.030 msg/s | 780 ms | 1.800 | Bão hòa, tail latency xấu |

Đây là **số liệu minh họa**, không phải benchmark thực nghiệm. Trong kịch bản này, window 128 có thể là lựa chọn ban đầu hợp lý hơn 512 hoặc 2.048, nhưng vẫn phải xác minh theo SLO/tải thực.

**Không cộng p95 confirm với p95 handler rồi gọi là p95 end-to-end.** Các percentile không có tính cộng đơn giản; đo end-to-end trên cùng event ID nếu đó là SLO nghiệp vụ.

## 12. Tối ưu mà không đánh mất độ tin cậy

### 12.1. Outbox và số publish chờ

Một kiến trúc ổn định:

```text
DB business transaction
          |
          v
  transactional outbox (NEW)
          |
          v
  relay claims up to N rows
          |
          v
  bounded async publisher
          |
          +--> ACK + no return --> mark SENT
          |
          +--> NACK / UNKNOWN --> schedule RETRY with backoff
          |
          +--> UNROUTABLE -----> quarantine / fix topology
          |
          +--> WINDOW FULL ---> stop claiming, try later

Consumer receives (possibly duplicate) -> dedup(eventId) + DB commit
```

Tách rõ **N số publish attempts** và **N row đã claim trong DB**. Không claim hàng chục nghìn row rồi để lease hết hạn trong khi window chỉ có 128. Đặt batch size, lease duration, max parallel workers và publisher slots thống nhất.

### 12.2. Backpressure phải truyền tới upstream

Khi window đầy:

- Outbox poller dừng lấy thêm row hoặc giảm tốc.
- API nguồn có thể tiếp nhận dữ liệu bằng DB transaction + outbox nhưng cần quota storage và alert backlog.
- Nếu không có outbox, producer phải có hàng đợi bền vững hoặc phản hồi áp lực tải theo contract.
- Không block listener callback thread bằng `Semaphore.acquire()` nếu việc phát ra RabbitMQ đang nằm trong luồng cần giải phóng ACK từ kết nối khác.
- Đừng lặp `tryAcquire()` với 0 delay; dùng scheduler/backoff hoặc signal khi slot được release.

**Không dùng hàng đợi RAM vô hạn** giữa application worker và RabbitTemplate để “giải quyết” backpressure: chỉ di chuyển điểm tắc nghẽn và có thể mất messages khi crash.

### 12.3. Consumer idempotency vẫn bắt buộc

Publisher ACK được nhận thì outbox có thể đánh dấu `SENT`, nhưng consumer vẫn có thể nhận duplicate do:

- Broker redelivery khi consumer ACK mất.
- Relay retry sau publish đã thành công nhưng update outbox `SENT` thất bại.
- Publisher timeout khi broker đã lưu message.
- Người vận hành replay DLQ hoặc event store.

Dùng `eventId` cố định và unique key, ví dụ `(consumer_name, event_id)` trong DB consumer, cùng transaction ghi side effect nghiệp vụ. Correlated attempt ID chỉ phục vụ quan sát publish, **không thay event ID**.

## 13. Những lỗi hiệu năng và vận hành điển hình

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Throughput thấp; CPU rảnh | Mỗi publish chờ confirm đồng bộ | Profile producer loop, xem confirm RTT |
| Pending tăng; ACK rate giảm | Broker/disk/network/queue bị chậm hoặc blocked | Confirm RTT, broker alarms, connection state |
| Heap/GC tăng cùng số pending | Unbounded future/payload/callback map | Heap histogram, pending count, retained payload |
| Window thường full nhưng broker không bão hòa | Window quá nhỏ hoặc quản lý channels chưa hiệu quả | Confirm mean, channel count, benchmark tăng window |
| Window tăng nhưng throughput không cải thiện | Đã bão hòa broker/network/durable storage | Broker resource metrics, p95/p99 confirm |
| ACK nhiều nhưng consumer thiếu message | Mandatory returns bị bỏ qua, routing sai | `CorrelationData.getReturn()`, binding, DLQ |
| NACK/UNKNOWN bị retry liên tục | Backoff thiếu, reconnect storm | Retry rate, attempt IDs, broker logs |
| Pending không giảm sau outage | Không có watchdog hoặc callback/future không hoàn tất | Oldest pending age, connection/channel shutdown |
| Đã release slot rồi callback lại release nữa | Race giữa sync exception và async callback | Semaphore permit count > window, unit test race |
| Result callback chậm | Đang làm DB/HTTP blocking trong callback | Executor thread dumps, confirm backlog |
| Retry tạo message mới `eventId` mỗi lần | Thiếu stable business identity | Duplicate side effects, outbox records |
| Một replica OK nhưng toàn cluster quá tải | Window chỉ giới hạn mỗi process | Tổng pending qua replicas, global quota |

## 14. Kiểm thử confirm bất đồng bộ và bounded window

Cần phối hợp **unit tests điều khiển kết quả giả lập** với **integration tests trên RabbitMQ thật**. Mock phù hợp kiểm tra state machine/backpressure, nhưng không thể tái hiện chính xác thứ tự `basic.return`/confirm hoặc channel shutdown.

### 14.1. Unit test cửa sổ và cleanup

Thiết kế một adapter publisher để cấp `CompletableFuture` do test kiểm soát, rồi kiểm tra:

1. Gửi đủ 128 attempts chưa hoàn tất → `pendingCount()=128`.
2. Gửi attempt thứ 129 → nhận `BACKPRESSURED`, không gọi RabbitTemplate.
3. Hoàn tất một confirm ACK → pending giảm về 127, permit được giải phóng.
4. Gửi attempt mới → được nhận.
5. Làm cho cả **send throw** và **confirm callback** cùng xảy ra → `releaseOnce` chỉ trả permit một lần.
6. Kết quả ACK nhưng có returned message → `UNROUTABLE` chứ không phải `ACK_NO_RETURN`.
7. Negative confirm → `NACK` và reason có thể null.
8. Confirm tương ứng attempt nào phải hoàn tất đúng outcome của attempt đó, kể cả callbacks đảo thứ tự.

Mã `BoundedConfirmPublisher` mục 7 truy cập `RabbitTemplate` trực tiếp; để mock được hoàn toàn việc hoàn tất confirm trong unit test, nên trích abstraction `PublishTransport` và stub future/return. Không giả lập bằng `Thread.sleep` hoặc dựa vào broker để cưỡng ép đúng một thứ tự callback.

### 14.2. Integration test trên RabbitMQ thật

Dùng Spring Boot Test + Testcontainers, tạo direct exchange, durable queue và binding cô lập. Bật:

```yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
```

Sau đó:

- Publish 100 event JSON hợp lệ, **không chờ confirm trong vòng lặp**.
- Thu thập 100 `CompletionStage`/`CompletableFuture`, chờ tất cả hoàn tất **với timeout hữu hạn**.
- Assert mỗi publish thành `ACK_NO_RETURN`; kiểm tra queue test nhận đúng các `eventId`.
- Gửi một publish với routing key không có binding: confirm ACK có thể đi kèm `NO_ROUTE` return → `UNROUTABLE`.
- Gửi vào exchange không tồn tại: quan sát lỗi channel/negative confirm; **không** mong `basic.return(NO_ROUTE)`.
- Thử queue durable với persistent message và, nếu sản phẩm dùng quorum queues, test đúng queue type.
- Không có consumer khác tranh queue và không dùng một exchange shared giữa các test chạy song song.

Ví dụ **bước chờ có giới hạn trong integration test**:

```java
List<CompletableFuture<BoundedConfirmPublisher.Result>> results =
        new ArrayList<>();

for (int i = 0; i < 100; i++) {
    CompletionStage<BoundedConfirmPublisher.Result> sent =
            publisher.publish("event-" + i,
                    ("{\"eventId\":\"event-" + i + "\"}")
                            .getBytes(StandardCharsets.UTF_8));
    results.add(sent.toCompletableFuture());
}

CompletableFuture.allOf(
        results.toArray(CompletableFuture[]::new))
        .get(20, TimeUnit.SECONDS);

assertThat(results).allSatisfy(future ->
        assertThat(future.join().state())
                .isEqualTo(
                        BoundedConfirmPublisher.State.ACK_NO_RETURN));
```

Import ở đoạn test: `java.util.ArrayList`, `java.util.List`, `java.util.concurrent.CompletableFuture`, `java.util.concurrent.CompletionStage`, `java.nio.charset.StandardCharsets`, `java.util.concurrent.TimeUnit` và AssertJ `assertThat`.

**Giới hạn test:** Với window 128, gửi 100 message không tràn cửa sổ; điều kiện overload phải test riêng bằng controlled transport hoặc cố ý giữ confirms trong môi trường fault injection. Nếu broker trả confirm cực nhanh, test không thể giả định `pendingCount()` luôn đạt 100 tại một thời điểm.

### 14.3. Fault injection cho outage và unknown outcome

Trong môi trường test cô lập:

1. Publish liên tục tới durable queue và đo pending/throughput/confirm RTT.
2. Cắt kết nối publisher hoặc tạm dừng broker có kiểm soát.
3. Kiểm tra window **không phình vô hạn**, alert oldest pending tăng và relay dừng gửi mới.
4. Phục hồi connection theo cơ chế đã thiết kế; event intents còn trong outbox.
5. Retry với **cùng eventId nhưng attemptId mới**; consumer không áp dụng tác dụng phụ hai lần.
6. Khẳng định trạng thái timeout/connection failure được báo **UNKNOWN**, không mặc định broker chưa nhận.
7. Đối soát outbox `SENT`/`RETRY` và queue state sau phục hồi.

Không thể chứng minh “sẽ không bao giờ duplicate” bằng một lần fault test. Mục tiêu là kiểm chứng quy tắc idempotency và recoverability trong điều kiện outcome không chắc chắn.

## 15. Bài thực hành theo lộ trình

### Bài 1 — Baseline synchronous confirm

Gửi 500 persistent messages theo kiểu mỗi send chờ confirm bằng `get(...)`. Đo thời gian tổng, confirm p50/p95, CPU, channel count và throughput confirmed. Giải thích vì sao vòng lặp chờ tuần tự bị giới hạn bởi confirm RTT.

### Bài 2 — Asynchronous correlated confirms

Thay bằng `getFuture().whenComplete(...)`, gửi 500 messages trước khi đợi tất cả. Gắn `attemptId` riêng từng publish, tổng hợp ACK/NACK/return. So sánh throughput với bài 1 dưới **cùng queue type, message size, network và durability**.

### Bài 3 — Bounded window 32/128/512

Sử dụng `BoundedConfirmPublisher` và outbox poller có thể hoãn khi `BACKPRESSURED`. Đo throughput, peak pending, oldest pending, heap và p95 confirm. Chọn ngưỡng không đẩy broker vào bão hòa.

### Bài 4 — Confirm ACK nhưng không route

Gửi tới exchange tồn tại với routing key không có binding và `mandatory=true`. Kỳ vọng `ACK + return NO_ROUTE`; outbox không đánh dấu `SENT`. Kiểm chứng rằng chỉ đếm publisher ACK sẽ cho kết quả sai.

### Bài 5 — Exchange không tồn tại

Publish vào tên exchange chưa khai báo. Quan sát channel exception `404 NOT_FOUND`, negative confirm/exception đồng bộ tùy timing; không coi đó là mandatory return. Sửa topology rồi gửi lại với attempt ID khác và cùng event ID.

### Bài 6 — Broker bị nghẽn

Dùng fault injection hoặc điều kiện lab làm confirm RTT tăng. Quan sát window đầy, outbox chậm dần. Đảm bảo upstream không tạo unbounded in-memory queue hay retry loop nóng.

### Bài 7 — Timeout và retry tạo duplicate

Giả lập message đã được broker nhận nhưng confirm bị mất. Outbox retry cùng `eventId`; receiver dedup bằng unique key. Đo số publish attempts so với số event logic và số side effects nghiệp vụ.

### Bài 8 — Callback chậm

Cố tình đặt blocking operation trong callback **chỉ trong lab**; quan sát executor/callback delay và pending age. Chuyển công việc blocking sang bounded executor/relay riêng; xác nhận callback trở lại nhanh và không tạo hàng đợi executor vô hạn.

### Bài 9 — Nhiều replicas

Triển khai nhiều publisher instances, mỗi instance window 128. Đo tổng pending và xác minh mỗi outbox row có ownership token/lease; không để hai relay cùng ghi `SENT` do callback từ attempt cũ.

### Bài 10 — Benchmark theo queue type và durability

Chạy cùng kịch bản với classic durable queue và quorum queue (khi được hạ tầng hỗ trợ), persistent delivery, kích thước message cố định. So sánh confirm latency distribution, confirmed throughput và tài nguyên. Không lấy kết quả của queue transient làm chuẩn cho workload yêu cầu durability.

**Tiêu chí đạt:** Không chờ từng confirm trong đường publish throughput cao; outstanding có giới hạn; ACK, NACK, return và unknown được phân loại; timeout không bị hiểu là chắc chắn thất bại; retry giữ eventId và dựa trên outbox/idempotency; metrics chỉ ra được khi window hoặc broker đã bão hòa.

## 16. Những sai lầm thường gặp

| Nhận định sai | Điều cần hiểu đúng |
|---|---|
| “`convertAndSend` trả về là broker ACK.” | Method có thể trả về trước publisher confirm; dùng future/callback. |
| “Gửi async nghĩa là gửi vô hạn không sao.” | Pending futures, payload và channels cần được giới hạn/backpressure. |
| “Confirm ACK chứng minh consumer đã commit DB.” | Publisher confirm và consumer ACK/DB commit độc lập. |
| “Confirm ACK chắc chắn có queue nhận.” | Mandatory return có thể đi cùng ACK. |
| “Publisher NACK xảy ra khi routing key sai.” | Unroutable mandatory thường return + ACK; NACK là tín hiệu khác. |
| “Timeout nghĩa là message đã bị mất.” | Outcome không chắc chắn, broker có thể đã nhận. |
| “Sau timeout cứ release permit và publish tiếp vô hạn.” | Window có thể mất hiệu lực nếu broker/channel vẫn đang xử lý pending. |
| “Một CorrelationData dùng được cho mọi attempt.” | Phải đối chiếu từng attempt riêng biệt. |
| “Callback confirm được phép làm DB blocking tùy ý.” | Có thể làm chậm xử lý confirms và khiến pending tích tụ. |
| “Tăng channelCacheSize là đủ thay bounded window.” | Cache không phải cơ chế hard cap publish pending. |
| “Consumer prefetch giới hạn publisher outstanding.” | Prefetch điều khiển delivery chưa ACK phía consumer. |
| “Window càng lớn thì throughput luôn càng cao.” | Sau điểm bão hòa, latency/heap/retry có thể tăng mà throughput không tăng. |
| “Có confirms thì không cần outbox.” | Confirms không giúp khôi phục event intent khi process crash trước khi nhận/lưu kết quả. |
| “Mỗi lần retry tạo eventId mới cho sạch.” | Làm mất khả năng dedup logic sự kiện. |

## 17. Câu hỏi tự kiểm tra

1. Publisher confirms khác với ACK của `@RabbitListener` ở ranh giới nào?
2. Vì sao chờ `getFuture().get(...)` ngay sau mỗi send làm throughput thường thấp?
3. Trường hợp nào confirm ACK và `CorrelationData.getReturn() != null` đồng thời đúng?
4. `CorrelationData` nên dùng event ID cố định hay attempt ID riêng trong ứng dụng có retry?
5. Nếu muốn 3.000 msg/s và mean confirm latency 120 ms, ước lượng số outstanding trung bình là bao nhiêu?
6. Tại sao không thể lấy p95 confirm RTT nhân throughput rồi gọi là outstanding trung bình?
7. `Semaphore` trong publisher bảo vệ loại tài nguyên nào? Nó có giới hạn consumer prefetch không?
8. Khi send đồng bộ ném exception cùng lúc callback confirm chạy, làm sao tránh release permit hai lần?
9. Nếu future confirm không hoàn tất trong thời gian dài, chỉ gọi `orTimeout` rồi release permit có thể gây rủi ro gì?
10. Vì sao callback không nên trực tiếp gọi DB hoặc retry network blocking?
11. Khi outbox nhận `BACKPRESSURED`, nên xử lý row thế nào?
12. Tại sao consumer vẫn cần idempotency dù publisher đã dùng correlated confirms?
13. Spring Rabbit có thể quản lý channel thế nào khi còn outstanding correlated confirms?
14. Những metric nào cho thấy tăng window đã vượt điểm hiệu quả?

**Đáp án gợi ý:** (1) broker→publisher khác consumer→broker; (2) serialize thời gian đợi RTT; (3) mandatory unroutable; (4) attempt ID riêng và business event ID giữ nguyên; (5) khoảng 360; (6) Little’s Law dùng mean trong hệ ổn định; (7) số publish attempts chưa có kết quả, không phải prefetch; (8) `AtomicBoolean.compareAndSet`; (9) số unconfirmed thực có thể vượt window và mất kết quả muộn; (10) tránh nghẽn callback executor; (11) hoãn poll/retry có backoff, không đánh dấu SENT; (12) timeout/redelivery có thể gây duplicate; (13) không trả channel để tái sử dụng khi còn confirm chưa hoàn tất; (14) throughput phẳng nhưng p95/p99 latency, pending, memory, retries tăng.

## 18. Tổng kết

**Publisher confirm bất đồng bộ** cho phép ứng dụng Spring AMQP tiếp tục gửi và xử lý công việc trong khi chờ RabbitMQ xác nhận, tránh giới hạn throughput của mô hình chờ ACK từng message. Tuy nhiên, **không giới hạn số publish đang chờ** sẽ chuyển bài toán latency thành áp lực heap, callback, channel và khả năng phục hồi khi broker chậm.

Một thiết kế tốt kết hợp `CorrelationData.getFuture().whenComplete(...)`, **in-flight window hữu hạn** bằng `Semaphore` hoặc cơ chế điều phối tương đương, backpressure truyền tới outbox poller, timeout/unknown outcome có kiểm soát, theo dõi confirm latency và pending age. Phải phân biệt **ACK**, **NACK**, **mandatory return** và lỗi kết nối; với retry, giữ event ID ổn định và dùng consumer idempotent.

Kích thước window không có đáp án cố định: hãy chọn từ **throughput mục tiêu, mean confirm latency, queue type, durability, số channels và phép đo thực tế**. Định nghĩa rõ mức “đã gửi thành công”, xác nhận bằng broker metrics và kiểm thử fault injection trước khi đưa vào production.

### Tài liệu tham khảo

- [Spring AMQP — RabbitTemplate: Correlated Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): `CorrelationData`, `CompletableFuture`, `getReturn()` và callbacks.
- [Spring AMQP — Connection and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): `CachingConnectionFactory`, publisher confirm channels, separate publisher connection.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ACK/NACK, durability, thứ tự confirm và batching.
- [RabbitMQ — Publishers](https://www.rabbitmq.com/docs/publishers): streaming confirms, batch, synchronous wait và lỗi publish.
- [RabbitMQ — Java Tutorial: Publisher Confirms](https://www.rabbitmq.com/tutorials/tutorial-seven-java): so sánh synchronous/batch/asynchronous confirms.
- [Spring AMQP — Reliability and Publisher Confirms](https://docs.spring.io/spring-amqp/reference/amqp/template.html): phương thức gửi và quản lý kết quả.

