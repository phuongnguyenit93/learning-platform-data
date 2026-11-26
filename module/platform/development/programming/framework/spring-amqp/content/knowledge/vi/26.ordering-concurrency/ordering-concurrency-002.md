# Nhiều producer, nhiều channel và thứ tự quan sát thực tế

RabbitMQ thường được mô tả là hệ thống đưa message vào queue rồi giao theo thứ tự **FIFO** (*first in, first out*). Mô tả đó hữu ích, nhưng chưa đủ để kết luận các tác vụ trong hệ thống **Spring AMQP** sẽ hoàn tất theo đúng thứ tự nghiệp vụ. Khi có **nhiều producer, nhiều channel, nhiều consumer, retry hoặc xử lý bất đồng bộ**, có ít nhất bốn loại thứ tự khác nhau: thứ tự tạo sự kiện, thứ tự broker xếp message vào queue, thứ tự giao message và thứ tự ứng dụng xử lý xong.

Trong chương **Thứ tự và đồng thời** của module **SPRING_AMQP**, bài học này phân tích các giới hạn thứ tự khi ứng dụng dùng `RabbitTemplate`, exchange, queue, binding và `@RabbitListener`. Từ đó ta sẽ thực hành nhận diện lỗi đảo thứ tự, ghi nhận sự kiện có thể kiểm chứng được, và chọn cách thiết kế phù hợp khi phải đảm bảo thứ tự **theo từng đơn hàng hoặc tài khoản**.

## 1. Cần định nghĩa “thứ tự” trước khi nói RabbitMQ có đảm bảo hay không

Giả sử đơn hàng `O-42` phát sinh ba sự kiện:

~~~text
v1: OrderCreated
v2: OrderPaid
v3: OrderShipped
~~~

Ứng dụng nghiệp vụ mong muốn `v1 → v2 → v3`. Thế nhưng có thể quan sát được các thứ tự khác nhau:

| Mốc quan sát | Ý nghĩa | Ai quyết định? |
|---|---|---|
| **Thứ tự nghiệp vụ** | Phiên bản trạng thái, ví dụ `v1, v2, v3` | Database, logic cập nhật aggregate hoặc event store |
| **Thứ tự gọi publish** | Thời điểm ứng dụng gọi `convertAndSend` | Nhiều producer/thread |
| **Thứ tự trên channel** | Chuỗi lệnh publish truyền trên một AMQP channel | Client và giao thức trên channel đó |
| **Thứ tự enqueue vào queue** | Thứ tự message được broker đặt vào một queue cụ thể | Broker, routing và các channel cùng gửi |
| **Thứ tự delivery** | Trình tự broker giao message đến consumer | Queue, prefetch, số consumer và redelivery |
| **Thứ tự bắt đầu xử lý** | Listener hoặc task bắt đầu xử lý từng message | Container, thread pool và ứng dụng |
| **Thứ tự hoàn tất/ACK** | Tác dụng nghiệp vụ kết thúc hoặc ACK được gửi | Thời lượng xử lý, retry, transaction và ACK policy |

**Thứ tự enqueue không đồng nghĩa thứ tự hoàn tất nghiệp vụ.** Việc thấy `OrderPaid` trong log trước `OrderCreated` cũng không tự chứng minh broker đã xếp sai thứ tự: hai log có thể được tạo ở hai thread, hai máy có đồng hồ lệch hoặc một callback chạy nhanh hơn.

Để phân tích chính xác, nên gắn `eventId`, `aggregateId` và **số thứ tự nghiệp vụ `version`/`sequence`** vào message. Timestamp và delivery tag không thay thế được sequence nghiệp vụ.

## 2. Một producer và một channel: phạm vi đảm bảo hẹp

Trường hợp đơn giản:

~~~mermaid
flowchart LR
    P["Producer P1"] --> C["AMQP channel C1"]
    C --> E["Direct exchange"]
    E --> Q["Queue Q"]
    Q --> L["Một consumer đồng bộ"]
    P -.->|"publish A rồi B rồi C"| C
~~~

Khi một publisher gửi `A`, rồi `B`, rồi `C` **theo thứ tự trên cùng một channel** đến cùng một queue, broker thông thường enqueue các message theo thứ tự publish đó. Nếu queue có một consumer xử lý **đồng bộ**, không có priority, requeue, redelivery hoặc cơ chế làm thay đổi đường đi, listener thường xử lý `A → B → C`.

Đó là một **bảo đảm có điều kiện**:

- Giao thức duy trì thứ tự các lệnh publish trên **cùng AMQP channel**. Nó không gán thứ tự toàn cục cho các channel độc lập.
- Exchange quyết định **đích đến**; thứ tự chỉ có ý nghĩa khi xét **cùng một queue**. Những queue khác nhau có delivery và consumer độc lập.
- Queue FIFO không biến mọi cách xử lý phía consumer thành tuần tự. Nhiều consumer hoặc tác vụ async có thể hoàn tất khác thứ tự được giao.
- Message bị requeue, bị dead-letter rồi đưa về, hoặc được ưu tiên bởi priority queue có thể không giữ nguyên vị trí quan sát như ở luồng bình thường.

Do đó, câu “RabbitMQ đảm bảo thứ tự” chỉ hữu ích khi nêu rõ **trên channel nào, trong queue nào, tại mốc enqueue/delivery nào và dưới điều kiện xử lý nào**.

## 3. Nhiều producer và nhiều channel: không có thứ tự publish toàn cục

Hai service cùng phát sự kiện vào `orders.events.x`:

~~~mermaid
sequenceDiagram
    participant P1 as Producer P1
    participant C1 as Channel C1
    participant P2 as Producer P2
    participant C2 as Channel C2
    participant Q as orders.events.q
    P1->>C1: publish OrderCreated (v1)
    P2->>C2: publish OrderPaid (v2)
    Note over C1,C2: Mạng, scheduling và kết nối độc lập
    C2->>Q: broker nhận v2
    C1->>Q: broker nhận v1
    Note over Q: Thứ tự enqueue thực tế: v2, v1
~~~

Mặc dù `P1` gọi publish trước `P2` theo đồng hồ ứng dụng, message `v2` có thể đến broker trước `v1`. Trong một queue cụ thể, RabbitMQ vẫn có thứ tự xếp hàng quan sát được, nhưng thứ tự này chỉ phản ánh **thứ tự broker tiếp nhận/enqueue**, không phải thứ tự cập nhật nghiệp vụ ở các producer khác nhau.

Ví dụ các khả năng:

| Nguồn publish | Thứ tự trên từng channel | Thứ tự có thể enqueue vào cùng queue |
|---|---|---|
| `P1/C1` gửi `A1 → A2`; `P2/C2` gửi `B1 → B2` | Mỗi channel giữ thứ tự riêng | `A1, B1, A2, B2` hoặc `B1, B2, A1, A2` hoặc các cách xen kẽ hợp lệ |
| Hai producer gửi `OrderCreated(v1)` và `OrderPaid(v2)` | Không có quan hệ thứ tự giữa hai channel | `v1, v2` **hoặc** `v2, v1` |
| Một publisher phát lần lượt nhưng các lệnh dùng các channel khác nhau | Không còn cùng chuỗi lệnh trên một channel | Không thể dựa vào thứ tự gọi method để suy ra thứ tự enqueue |
| Một channel phát `A → B` đến queue Q | `A` đứng trước `B` trong chuỗi publish | Thông thường Q enqueue `A` trước `B`, nếu không có ngoại lệ về routing/queue |

### 3.1. Có thể dùng chung một RabbitTemplate nhưng vẫn có nhiều channel

`RabbitTemplate` là thành phần tiện dụng để publish từ nhiều thread; về cơ chế, nó sử dụng channel thông qua `ConnectionFactory` và bộ nhớ đệm channel khi được cấu hình. **Dùng chung một instance `RabbitTemplate` không có nghĩa toàn bộ thread trong ứng dụng đang publish tuần tự trên một channel duy nhất.**

Không nên lấy thứ tự log của hai lời gọi `rabbitTemplate.convertAndSend(...)` ở hai thread làm bằng chứng cho thứ tự broker nhận message. Cũng không nên bắt nhiều thread trực tiếp dùng chung một `com.rabbitmq.client.Channel` không đồng bộ: channel không phải một đường publish an toàn cho các lời gọi concurrent tùy ý.

Nếu **một luồng** cần gửi hai message theo thứ tự trên một channel, Spring AMQP hỗ trợ scoped operations bằng `RabbitTemplate.invoke(...)`:

~~~java
// Ví dụ minh họa: publisher confirms đã được bật trên connection factory.
rabbitTemplate.invoke(ops -> {
    ops.convertAndSend("orders.events.x", "orders.event", createdEvent);
    ops.convertAndSend("orders.events.x", "orders.event", paidEvent);
    ops.waitForConfirmsOrDie(10_000);
    return null;
});
~~~

Trong scope đó, thao tác dùng channel dành riêng cho lần `invoke`, tránh việc mỗi lời gọi rời rạc có thể lấy channel khác. **Scoped channel không biến các publisher khác thành một hàng đợi toàn cục**; nếu hai tiến trình cùng cần cập nhật đơn hàng, vẫn phải tổ chức thứ tự ở tầng nghiệp vụ.

### 3.2. Publisher confirms không phải số thứ tự giao message

Publisher confirms báo broker đã chấp nhận publish hoặc NACK publish trên một channel. Callback confirm có thể đến sau một khoảng trễ; khi có nhiều message in-flight, **thứ tự callback/hoàn tất Future không dùng làm thứ tự nghiệp vụ hoặc thứ tự consumer xử lý**.

Điểm quan trọng:

- Delivery tag dùng cho **publisher confirm** được tính theo channel, không phải ID toàn cục của message.
- Delivery tag dùng cho **consumer ACK** cũng chỉ có ý nghĩa trên channel nhận delivery đó; không thể so tag từ hai channel để suy ra thứ tự.
- `CorrelationData` giúp nối confirm với lần publish đã gửi. Nó không tự thiết lập `v1` phải được xử lý trước `v2`.
- Publisher confirm không chứng minh consumer đã ACK, đã ghi DB hoặc đã hoàn tất nghiệp vụ.
- Với message có thể không được định tuyến, cần thêm `mandatory` và publisher returns để kiểm tra đường routing; confirm ACK một mình không đủ.

Nếu cần thứ tự nghiệp vụ xuyên producer, phải có một nơi **cấp sequence và điều phối publish** (ví dụ một dòng aggregate trong database cùng transactional outbox). Không thể suy ra thứ tự này chỉ bằng việc chờ confirm của hai channel khác nhau.

## 4. Một queue, nhiều consumer: thứ tự hoàn tất có thể đảo

RabbitMQ phân phối message từ một queue tới các consumer đang hoạt động. Với hai consumer có thời gian xử lý khác nhau:

~~~mermaid
sequenceDiagram
    participant Q as Queue Q
    participant C1 as Consumer C1
    participant C2 as Consumer C2
    participant DB as Database
    Q->>C1: giao A (version 1)
    Q->>C2: giao B (version 2)
    C1->>C1: xử lý A mất 500 ms
    C2->>DB: ghi B sau 20 ms
    C2-->>Q: ACK B
    C1->>DB: ghi A sau 500 ms
    C1-->>Q: ACK A
    Note over DB: Thứ tự hoàn tất: B rồi A
~~~

Trong ví dụ, broker đã giao `A` trước `B`, nhưng database quan sát `B` trước `A`. Đây là hệ quả bình thường của xử lý concurrent, không phải lỗi FIFO của queue.

Trong Spring AMQP:

- `SimpleMessageListenerContainer` (**SMLC**) với `concurrentConsumers > 1` có nhiều consumer nhận từ cùng queue.
- `DirectMessageListenerContainer` (**DMLC**) với `consumersPerQueue > 1` cũng có nhiều consumer cho mỗi queue.
- `@RabbitListener(concurrency = "2-4")` có thể cho phép số consumer tăng/giảm tùy container/factory; lựa chọn cụ thể cần đối chiếu với loại container và phiên bản Spring AMQP.
- Ngay cả khi chỉ có **một consumer**, listener tự tách task sang executor hoặc trả về `CompletableFuture`/`Mono` có thể cho phép các tác vụ xử lý hoàn tất khác thứ tự nếu có nhiều message đang chờ ACK.

**Prefetch không phải bộ sắp xếp.** `prefetch=1` giới hạn số delivery chưa ACK có thể đang ở một consumer; nó thường giúp triển khai xử lý tuần tự hơn khi kết hợp một consumer và ACK sau khi xử lý xong. Nếu có **hai consumer**, mỗi consumer vẫn có thể nhận một message và xử lý song song. Ngược lại, `prefetch > 1` không tự động làm đảo thứ tự nếu chỉ có một listener đồng bộ xử lý tuần tự trên một thread; rủi ro đến từ concurrency thực tế, retry và cách ứng dụng điều phối completion.

## 5. Thứ tự sau requeue, retry, dead-letter và phục hồi consumer

Đường đi của message khi thất bại có thể phá vỡ giả định “message đầu tiên phải xong rồi mới xử lý message tiếp theo”.

~~~text
Queue ban đầu:       [A(v1), B(v2), C(v3)]
Consumer xử lý A:   thất bại
A được requeue:     vị trí thực tế phụ thuộc trạng thái queue/concurrency
Consumer khác:      có thể hoàn tất B hoặc C trước A
~~~

Trong RabbitMQ, khi requeue, broker cố đặt message gần vị trí ban đầu nếu có thể; vì các delivery và ACK khác có thể diễn ra đồng thời, message có thể quay về vị trí gần đầu queue và **không nhất thiết giữ được thứ tự quan sát ban đầu**. Ngoài ra:

| Cơ chế | Ảnh hưởng có thể gặp |
|---|---|
| `basicNack(..., requeue=true)` | Message quay lại queue, có thể được giao lại nhanh và xen với message khác |
| Consumer/channel chết khi còn unacked | Message chưa ACK được giao lại; tác dụng nghiệp vụ cũ có thể đã xảy ra |
| DLX → retry queue có TTL → work queue | `A` chờ trong retry queue trong khi `B`, `C` tiếp tục được xử lý |
| Spring Retry chạy bên trong listener | Có thể giữ consumer chờ và làm tăng latency; kết quả tùy retry policy |
| Producer phát lại một event cũ | Event trùng lặp có thể xuất hiện sau event phiên bản mới |
| Priority queue | Ưu tiên message có thể thay đổi thứ tự giao so với thứ tự publish |
| Nhiều queue cùng nhận bản sao qua fanout/topic | Mỗi queue có tốc độ consumer, retry và ACK riêng; kết quả giữa các queue khác nhau |

Lưu ý: flag `redelivered` cho biết một delivery có dấu hiệu đã được giao lại, **không** phải số lần retry chính xác. Header `x-death` chỉ ghi lịch sử dead-letter, không đếm đầy đủ requeue trực tiếp hay retry trong cùng lời gọi xử lý.

### Trường hợp đặc biệt: poison message

Nếu buộc các sự kiện của một đơn hàng xử lý đúng thứ tự, việc chuyển ngay `A(v1)` sang dead-letter rồi xử lý `B(v2)` có thể làm trạng thái downstream sai. Cần một trong các chiến lược:

1. **Tạm dừng dòng sự kiện của aggregate** khi thiếu version; giữ sự kiện đến sau trong nơi lưu bền vững hoặc chờ phục hồi event thiếu.
2. **Thiết kế thao tác có thể chịu out-of-order** bằng version check và trạng thái hội tụ, chỉ áp dụng event mới hơn khi ngữ nghĩa cho phép.
3. **Dừng cả shard/queue** khi yêu cầu thứ tự tuyệt đối và chấp nhận giảm thông lượng, kết hợp cảnh báo, khôi phục có kiểm soát.

Không chọn `basicNack(requeue=true)` liên tục như một cơ chế “đợi đúng thứ tự”: message có thể bị trả vào queue và tiêu thụ lại quá nhanh, tốn tài nguyên và khiến lỗi không được xử lý dứt điểm.

## 6. Quan sát thực tế bằng eventId, aggregateId và sequence

Một trace có thể trông như sau:

| eventId | aggregateId | version | Producer/Channel | Thời điểm gọi publish | Thời điểm bắt đầu xử lý | Hoàn tất |
|---|---|---:|---|---|---|---|
| `e101` | `O-42` | 1 | `P1/C1` | 10:00:00.100 | 10:00:00.280 | 10:00:00.780 |
| `e102` | `O-42` | 2 | `P2/C2` | 10:00:00.120 | 10:00:00.230 | 10:00:00.250 |
| `e103` | `O-42` | 3 | `P1/C1` | 10:00:00.150 | 10:00:00.400 | 10:00:00.470 |

Số version tăng theo nghiệp vụ, nhưng consumer **bắt đầu xử lý v2 trước v1** và **hoàn tất v2, v3 trước v1**. Chỉ nhìn thứ tự log hoặc thời điểm ACK sẽ dễ kết luận sai rằng event được tạo sai.

Nên ghi ít nhất các trường:

- `eventId`: định danh duy nhất cho sự kiện, **giữ nguyên khi retry/republish** cùng một sự kiện.
- `aggregateId`: khóa mà doanh nghiệp yêu cầu thứ tự, ví dụ `orderId` hoặc `accountId`.
- `version` / `sequence`: số tăng đơn điệu cho **từng aggregate**, được cấp tại nguồn có quyền quyết định thứ tự.
- `producerInstance`, `publishAttempt`, `correlationId`: truy vết lần gửi và publisher confirm.
- `consumerName`, `consumerInstance`, `receivedAt`, `processedAt`, `redelivered`: phân tích thời điểm nhận và hoàn tất.
- `messageId` và mã lỗi: hỗ trợ điều tra duplicate, retry, dead-letter.

Không dùng `messageId` UUID ngẫu nhiên hoặc header timestamp để **so sánh thứ tự**. Đồng hồ hai máy khác nhau có thể lệch; timestamp do publisher tạo không phải “enqueue timestamp” của broker. RabbitMQ không mặc định cung cấp một sequence toàn cục cho mọi channel/queue mà ứng dụng có thể dùng để khôi phục thứ tự nghiệp vụ.

## 7. Thực hành: gửi event từ nhiều producer đến cùng queue

Đầu tiên khai báo topology:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderEventTopology {
    @Bean
    DirectExchange orderEventsExchange() {
        return new DirectExchange("orders.events.x", true, false);
    }

    @Bean
    Queue orderEventsQueue() {
        return QueueBuilder.durable("orders.events.q").build();
    }

    @Bean
    Binding orderEventsBinding(
            @Qualifier("orderEventsQueue") Queue orderEventsQueue,
            @Qualifier("orderEventsExchange") DirectExchange orderEventsExchange) {
        return BindingBuilder.bind(orderEventsQueue)
                .to(orderEventsExchange)
                .with("orders.event");
    }
}
~~~

Định nghĩa sự kiện có version:

~~~java
import java.util.UUID;

public record OrderEvent(
        UUID eventId,
        UUID orderId,
        long version,
        String eventType) {}
~~~

Producer gửi:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {
    private final RabbitTemplate template;

    public OrderEventPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void publish(OrderEvent event) {
        template.convertAndSend(
                "orders.events.x", "orders.event", event);
    }
}
~~~

`RabbitTemplate` cần `MessageConverter` phù hợp (chẳng hạn JSON converter) nếu gửi `OrderEvent` trực tiếp; nếu không, có thể serialize payload bằng cơ chế được ứng dụng cấu hình. Mã trên thể hiện routing, **không cam kết publisher confirm và không thiết lập thứ tự xuyên nhiều producer**. Muốn publish có xác nhận, cấu hình correlated confirms, returns và mandatory routing rồi xử lý ACK/NACK tương ứng; muốn tránh mất sự kiện sau DB commit, sử dụng transactional outbox.

Thử chạy hai producer trong hai tiến trình cùng gọi `publish` cho các version khác nhau. Khi log consumer ghi version theo thứ tự nhận, bạn có thể thấy nhiều cách xen kẽ. Không kết luận “bất biến mỗi lần chạy sẽ đảo” vì scheduling không xác định; một thử nghiệm đơn lẻ có thể tình cờ luôn trả về cùng một thứ tự.

## 8. Khi cần thứ tự theo aggregate: partition + một consumer hoạt động mỗi shard

Nếu tất cả đơn hàng đều phải đi qua một queue có một consumer, hệ thống dễ giữ thứ tự xử lý tuần tự nhưng giới hạn throughput. Thực tế thường chỉ cần thứ tự **trong cùng một đơn hàng**; hai đơn hàng độc lập có thể xử lý song song.

Chiến lược:

1. Cấp **version đơn điệu cho từng `orderId`** trong database khi thay đổi đơn hàng. Khi nhiều producer đụng cùng order, database/transaction phải quyết định phiên bản 1, 2, 3...
2. Tính shard từ `orderId`, đưa tất cả event của cùng order tới **một queue shard cố định**.
3. Mỗi queue shard xử lý tuần tự bằng **một active consumer**, ACK sau khi nghiệp vụ hoàn tất. Có thể dùng `x-single-active-consumer` khi chạy nhiều instance.
4. Xác minh version ở consumer; nếu gặp version bị thiếu hoặc trùng, xử lý rõ ràng. Nếu cần *version n+1* phải đợi *version n*, phải có cơ chế giữ/chặn, không chỉ dựa vào thứ tự broker giao.

~~~mermaid
flowchart TB
    P["Nhiều producer"] --> S{"hash(orderId) % 4"}
    S -->|0| Q0["orders.shard.0.q"]
    S -->|1| Q1["orders.shard.1.q"]
    S -->|2| Q2["orders.shard.2.q"]
    S -->|3| Q3["orders.shard.3.q"]
    Q0 --> C0["Một active consumer"]
    Q1 --> C1["Một active consumer"]
    Q2 --> C2["Một active consumer"]
    Q3 --> C3["Một active consumer"]
~~~

### 8.1. Định tuyến bằng direct exchange

Ví dụ dùng **bốn shard cố định**. Một `orderId` được băm ra shard index; tất cả sự kiện của order đó dùng cùng routing key:

~~~java
public final class OrderShard {
    public static final int SHARD_COUNT = 4;

    private OrderShard() {}

    public static String routingKey(java.util.UUID orderId) {
        int index = Math.floorMod(orderId.hashCode(), SHARD_COUNT);
        return "orders.shard." + index;
    }
}
~~~

~~~java
rabbitTemplate.convertAndSend(
        "orders.sharded.x",
        OrderShard.routingKey(event.orderId()),
        event);
~~~

Để ví dụ chạy được, phải khai báo direct exchange `orders.sharded.x`, bốn durable queue `orders.shard.0.q` đến `orders.shard.3.q` và binding theo các routing key tương ứng. `hashCode()` của UUID xác định nhất quán trên các JVM Java cho cùng UUID; tuy nhiên **đổi `SHARD_COUNT` sẽ đổi routing key của nhiều aggregate**. Việc mở rộng số shard phải có quy trình chuyển đổi định tuyến và trạng thái đang chờ, tránh tách event cũ/mới của cùng order sang hai queue song song.

Đây là **partition logic do ứng dụng tự thực hiện**, không cần giả định broker có cơ chế phân vùng giống Kafka. Có thể dùng consistent-hash exchange khi đã cài plugin và chấp nhận quy tắc routing của nó, nhưng không bắt buộc cho ví dụ này.

### 8.2. Chỉ một active consumer trên queue

Khai báo một shard minh họa; các shard còn lại tương tự:

~~~java
@Bean
Queue orderShardZero() {
    return QueueBuilder.durable("orders.shard.0.q")
            .withArgument("x-single-active-consumer", true)
            .deadLetterExchange("orders.ordering.dlx")
            .deadLetterRoutingKey("orders.shard.0.failed")
            .build();
}
~~~

Ví dụ này còn cấu hình DLX cho message thất bại. Khi chạy thật, phải khai báo thêm exchange `orders.ordering.dlx`, queue cách ly và binding với routing key `orders.shard.0.failed`; nếu thiếu đích dead-letter, reject không requeue có thể làm mất message. Việc cách ly lỗi cũng **không tự chặn** các sự kiện phiên bản tiếp theo, nên cần chính sách phục hồi theo aggregate.

RabbitMQ **single active consumer (SAC)** chỉ chọn một consumer đang hoạt động trên cùng queue tại một thời điểm, ngay cả khi có nhiều instance đăng ký; consumer khác ở trạng thái dự phòng cho failover. Một active consumer **chưa đủ** để bảo đảm kết thúc xử lý theo thứ tự nếu listener tách nhiều task async hoặc phát ACK trước khi tác dụng nghiệp vụ được ghi.

Với listener đồng bộ, có thể dùng factory:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;

@Bean("orderedFactory")
SimpleRabbitListenerContainerFactory orderedFactory(
        ConnectionFactory connectionFactory) {

    SimpleRabbitListenerContainerFactory factory =
            new SimpleRabbitListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrentConsumers(1);
    factory.setMaxConcurrentConsumers(1);
    factory.setPrefetchCount(1);
    factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
    factory.setDefaultRequeueRejected(false);
    return factory;
}
~~~

~~~java
@RabbitListener(
        queues = "orders.shard.0.q",
        containerFactory = "orderedFactory")
public void consume(OrderEvent event) {
    orderProjectionService.applyInTransaction(event);
}
~~~

`OrderProjectionService.applyInTransaction` là nghiệp vụ giả định: ghi trạng thái và event ID đã xử lý trong database transaction, ném exception nếu xử lý không thành công. Có thể khai báo listener tương đương cho ba queue khác. Khi `AUTO` ACK, container ACK sau khi method trả về thành công; nếu method ném lỗi, cách reject/requeue phụ thuộc vào cấu hình error handler và DLX.

**Điều kiện cần thêm:** luôn kiểm soát retry/dead-letter để không xử lý `v3` khi `v2` chưa được áp dụng mà nghiệp vụ yêu cầu thứ tự nghiêm ngặt. `defaultRequeueRejected(false)` minh họa xử lý lỗi bằng reject/DLX, **không tự đảm bảo thứ tự nghiệp vụ**. Trong hệ thống có yêu cầu thứ tự cứng, phải chặn các phiên bản tiếp theo, lưu buffer bền vững hoặc dừng consumer của shard khi chưa khôi phục được event còn thiếu.

### 8.3. Một queue mỗi shard chỉ giải quyết một nửa bài toán

Nếu `Producer P1` và `Producer P2` cùng phát event cho `O-42` từ **hai channel khác nhau**, broker vẫn có thể nhận `v2` trước `v1` dù cả hai event được route vào cùng một shard. SAC sẽ **tuần tự xử lý thứ tự queue đang có**, nghĩa là vẫn có thể xử lý `v2` trước `v1`.

Muốn thứ tự có ý nghĩa, phải giải cả **hai đầu**:

- **Đầu phát:** cấp sequence và điều phối publish theo aggregate. Một transactional outbox được ghi cùng database transaction giúp không mất event; relay cần duy trì thứ tự của từng aggregate khi publish, ví dụ một luồng/partition cho cùng key hoặc publish đúng sequence với giới hạn in-flight phù hợp.
- **Đầu nhận:** chỉ áp dụng version hợp lệ và chống trùng lặp; nếu version chưa tới thì đợi/đưa vào kho chờ bền vững hoặc phát cảnh báo tùy chính sách.

Outbox với nhiều relay và `FOR UPDATE SKIP LOCKED` **không tự giữ thứ tự** nếu hai relay cùng gửi hai version của một aggregate. Nếu yêu cầu thứ tự, row claiming và cách phát phải bảo đảm một aggregate không bị hai worker làm vượt nhau.

## 9. Chống duplicate và phát hiện version thiếu ở consumer

Ví dụ consumer duy trì version đã xử lý:

~~~sql
CREATE TABLE order_projection (
    order_id UUID PRIMARY KEY,
    last_applied_version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE consumed_order_event (
    event_id UUID PRIMARY KEY,
    order_id UUID NOT NULL,
    event_version BIGINT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Thuật toán xử lý trong **một database transaction**:

~~~text
lock bản ghi projection(orderId) bằng SELECT ... FOR UPDATE

if eventId đã nằm trong consumed_order_event:
    coi là duplicate; không áp dụng tác dụng lần nữa

else if event.version == last_applied_version + 1:
    cập nhật projection theo event
    INSERT consumed_order_event(eventId, orderId, event.version)
    UPDATE last_applied_version = event.version
    commit; ACK

else if event.version <= last_applied_version:
    xác minh đây là bản trùng/cũ hợp lệ
    ghi metric hoặc cảnh báo; không áp dụng lùi trạng thái

else:
    thiếu version trung gian
    đưa event vào nơi chờ bền vững / tạm dừng aggregate / cảnh báo
    không đánh dấu version cao hơn là đã áp dụng
~~~

Không dùng `max(version)` đơn thuần rồi bỏ mọi sự kiện version thấp hơn nếu hệ thống yêu cầu **mỗi sự kiện phải được xử lý đầy đủ**. Với một phép cập nhật dạng “đặt trạng thái cuối cùng” có thể cho phép bỏ sự kiện cũ; với chuỗi “trừ tiền, cộng điểm, gửi hóa đơn” thì bỏ version trung gian có thể gây mất tác dụng nghiệp vụ.

Nếu bản ghi `order_projection` chưa tồn tại, tạo row với version 0 bằng thao tác an toàn trước khi lock (ví dụ `INSERT ... ON CONFLICT DO NOTHING` trên PostgreSQL). Các transaction đồng thời phải khóa trên **cùng orderId** để tránh hai consumer cùng áp dụng một version. Unique constraint `event_id` bảo vệ idempotency; có thể thêm unique `(order_id, event_version)` nếu domain quy định chính xác một event cho mỗi version.

Trường hợp bị thiếu version, cần chọn một chính sách phục hồi rõ: replay từ outbox/event store, đợi sự kiện trễ đến trong khoảng thời gian cho phép, hoặc chuyển sang trạng thái cần can thiệp. Không giữ vô hạn một AMQP delivery unacked chỉ để đợi message còn thiếu, vì sẽ tiêu tốn prefetch và khó phục hồi khi consumer chết; kho chờ nên bền vững, có timeout và công cụ vận hành.

## 10. Một message đi qua nhiều queue: không có thứ tự hoàn tất giữa các service

Với fanout exchange hoặc topic exchange có nhiều binding, cùng một sự kiện có thể đến queue của kho, billing và notification:

~~~mermaid
flowchart LR
    E["orders.events.x"] --> Q1["inventory.q"]
    E --> Q2["billing.q"]
    E --> Q3["notification.q"]
    Q1 --> C1["Inventory consumer"]
    Q2 --> C2["Billing consumer"]
    Q3 --> C3["Notification consumer"]
~~~

Một service có thể xử lý xong `OrderShipped` trước khi service khác hoàn tất `OrderPaid`. **Không có “ACK chung” xuyên ba queue** và không thể dùng tốc độ consumer của một queue để kết luận thứ tự của queue khác.

Nếu nghiệp vụ đòi hỏi “chỉ gửi email giao hàng sau khi billing đã xác nhận thanh toán”, giải pháp nên là **dependency ở tầng nghiệp vụ**: billing phát sự kiện `PaymentSettled`, hoặc workflow/saga đợi các điều kiện thỏa mãn. Routing tất cả sự kiện qua fanout không tự đồng bộ các service với nhau.

## 11. Bộ thí nghiệm để kiểm chứng thứ tự

Sử dụng exchange, queue và listener thử nghiệm; ghi đủ `eventId`, `aggregateId`, `version` và thời điểm trong log. Để tránh nhầm do đồng hồ máy, ưu tiên kiểm tra version và sự kiện đã commit; timestamp chỉ là dữ liệu phụ trợ.

| Thí nghiệm | Thiết lập | Điều cần quan sát |
|---|---|---|
| Một publisher, một channel | Gửi `A → B → C` vào cùng queue, một consumer đồng bộ | Thứ tự enqueue/delivery thường đi theo publish |
| Hai publisher, hai channel | P1 gửi v1, P2 gửi v2 cùng `orderId` | Thứ tự enqueue có thể khác thứ tự producer log |
| Hai consumer | C1 xử lý lâu, C2 xử lý nhanh | Thứ tự hoàn tất/ACK có thể đảo dù queue giao trước đúng thứ tự |
| Một consumer, prefetch=1 | Xử lý đồng bộ, ACK sau DB commit | Không có hai delivery unacked đồng thời trên consumer đó |
| Một consumer, task async | Listener giao task cho executor rồi return sớm | Completion hoặc tác dụng nghiệp vụ có thể đảo; ACK sớm là rủi ro |
| Requeue message đầu | Làm v1 thất bại rồi requeue | v2/v3 có thể bị quan sát trước v1 tùy concurrency/đường retry |
| Retry qua TTL + DLX | v1 rời work queue sang retry queue | v2 có thể tiếp tục xử lý khi v1 đang chờ |
| SAC + shard | Hai instance đăng ký một queue `x-single-active-consumer` | Chỉ một active consumer, consumer khác dự phòng; vẫn phải kiểm tra publish order |
| Hai channel, publisher confirms | Gửi nhiều message đồng thời và quan sát confirm callbacks | Confirm không phải thứ tự nghiệp vụ hoặc thứ tự xử lý của consumer |
| Consumer restart | Dừng sau khi DB đã commit nhưng trước ACK | Redelivery và xử lý duplicate qua inbox/version |
| Fanout sang ba queue | Ba service tiêu thụ tốc độ khác nhau | Mỗi queue có tiến độ và thứ tự hoàn tất riêng |
| Thay số shard | Thử đổi `SHARD_COUNT` khi còn message cũ | Phát hiện nguy cơ cùng aggregate bị chia giữa queue cũ và mới |

**Chỉ số vận hành nên theo dõi:** `ready`/`unacked` theo queue, consumer count, publisher confirms/returns, redelivery rate, retry/DLQ rate, thời gian từ publish đến ACK, độ trễ xử lý theo shard, số event duplicate, số khoảng trống version và tuổi lớn nhất của event đang chờ phục hồi.

## 12. Các giả định sai cần tránh

| Giả định | Vì sao không đúng |
|---|---|
| “RabbitMQ FIFO nên nghiệp vụ luôn xử lý đúng thứ tự” | FIFO ở queue không quyết định thứ tự của nhiều producer hoặc completion của nhiều consumer |
| “Cùng dùng một `RabbitTemplate` nghĩa là cùng một channel” | Channel có thể được lấy từ pool/cache theo lời gọi và thread |
| “Publisher confirm đến trước thì message được tạo trước” | Confirm phản ánh việc broker xác nhận publish trên channel, không phải sequence toàn cục |
| “Delivery tag lớn hơn nghĩa là event mới hơn” | Delivery tag chỉ có phạm vi trên từng channel |
| “`prefetch=1` đủ giữ thứ tự toàn hệ thống” | Nhiều consumer, nhiều channel và retry vẫn có thể làm đảo thứ tự |
| “Single active consumer đảm bảo cả thứ tự producer” | SAC chỉ giới hạn consumer đang nhận từ một queue, không sắp lại event v2/v1 |
| “Dùng TTL/DLX retry sẽ giữ nguyên vị trí message” | Message rời work queue rồi quay lại sau, có thể đi sau message mới |
| “Timestamp đủ dùng để so thứ tự sự kiện” | Đồng hồ lệch và publish qua nhiều đường; cần version/sequence ở nguồn |
| “Dùng một queue cho tất cả order là tối ưu” | Một queue tuần tự có thể trở thành điểm nghẽn; có thể partition theo orderId |
| “Chia shard và gửi là đủ” | Khi cùng aggregate có nhiều producer, thứ tự publish vẫn cần điều phối; consumer phải kiểm version |

## 13. Nguyên tắc chọn thiết kế

**Trường hợp không cần thứ tự nghiệp vụ:** các sự kiện độc lập, xử lý idempotent và có thể hội tụ, ví dụ cập nhật số liệu hoặc gửi thông báo riêng lẻ. Dùng nhiều consumer, prefetch và concurrency phù hợp để tăng throughput; không cần ép tất cả thành một luồng tuần tự.

**Trường hợp chỉ cần thứ tự theo một khóa:** ví dụ từng `orderId` hoặc `accountId`. Hãy cấp version ở nguồn, route cùng khóa vào cùng shard, xử lý mỗi shard tuần tự, kiểm version và duplicate ở consumer. Mỗi shard có thể chạy song song với shard khác để giữ thông lượng.

**Trường hợp yêu cầu thứ tự tuyệt đối giữa mọi sự kiện:** cần một bộ tuần tự hóa duy nhất hoặc một nguồn log có thứ tự toàn cục, cộng với consumer tuần tự. Chi phí là throughput thấp hơn và khả năng một lỗi chặn toàn luồng. Trước khi chọn, phải chứng minh nghiệp vụ thực sự cần một thứ tự duy nhất giữa các aggregate độc lập.

**Điểm cần nhớ:** RabbitMQ giữ được các quan hệ thứ tự có điều kiện bên trong một channel và một queue, nhưng không thể tự suy ra thứ tự nghiệp vụ khi nhiều producer, nhiều channel, nhiều consumer và retry cùng hoạt động. Với Spring AMQP, cách an toàn là **định nghĩa thứ tự bằng sequence từ nguồn, quan sát bằng eventId/aggregateId/version, điều phối publish theo khóa, rồi xử lý idempotent và kiểm tra version ở consumer**. Khi đó việc tăng concurrency sẽ là một quyết định có kiểm soát thay vì một giả định rằng hệ thống FIFO sẽ tự lo mọi thứ.
