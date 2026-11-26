# Single Active Consumer cho yêu cầu tiêu thụ tuần tự

Trong các hệ thống dùng RabbitMQ và **Spring AMQP**, tăng số lượng consumer thường giúp tăng thông lượng. Nhưng khi message biểu diễn **những thay đổi phải áp dụng theo thứ tự**, xử lý song song lại có thể tạo ra kết quả sai: sự kiện cập nhật trạng thái mới hoàn tất trước sự kiện cũ; hai worker cùng trừ tồn kho; hoặc một thao tác thất bại bị thử lại sau khi các thao tác tiếp theo đã chạy.

**Single Active Consumer (SAC)** là tính năng của RabbitMQ cho phép nhiều consumer đăng ký cùng một queue nhưng tại mỗi thời điểm chỉ **một consumer được broker chọn làm active để nhận delivery**. Các consumer còn lại giữ vai trò chờ thay thế. Khi consumer active mất kết nối hoặc ngừng tiêu thụ, broker có thể chọn một consumer khác để tiếp tục.

Bài thuộc chương **Thứ tự và đồng thời** của module **SPRING_AMQP**. Ta sẽ sử dụng `RabbitTemplate`, `@RabbitListener`, exchange–queue–binding, ACK, retry, dead-letter và giám sát để hiểu khi nào SAC hữu ích, cấu hình như thế nào và những giới hạn cần nhớ khi muốn bảo đảm thứ tự **hiệu ứng nghiệp vụ**, chứ không chỉ thứ tự giao message.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích khác biệt giữa **một consumer đang active**, **một consumer được đăng ký**, **concurrency=1** và **exclusive consumer**.
2. Cấu hình queue RabbitMQ với argument `x-single-active-consumer=true` và kết nối bằng Spring AMQP.
3. Thiết kế listener xử lý tuần tự với `prefetchCount=1`, `AcknowledgeMode.AUTO` và giao dịch nghiệp vụ hoàn tất trước ACK.
4. Phân tích failover, redelivery, ACK bị mất, retry và DLQ; xác định khi nào thứ tự có thể thay đổi.
5. Nhận biết giới hạn của SAC đối với nhiều producer, xử lý bất đồng bộ trong listener và nhiều queue.
6. Kết hợp SAC với `eventId`, `aggregateVersion` và idempotency để bảo vệ trạng thái trước message trùng hoặc đến sai thứ tự.
7. Quyết định khi nào nên **chia queue theo khóa nghiệp vụ** để tăng thông lượng mà vẫn giữ thứ tự trong từng nhóm.

## 2. Vì sao cần tiêu thụ tuần tự?

Giả sử dịch vụ Order phát ba sự kiện cho cùng đơn hàng:

| Message | Thứ tự nghiệp vụ | Nội dung |
| --- | ---: | --- |
| `E1` | 1 | `CREATED` |
| `E2` | 2 | `PAID` |
| `E3` | 3 | `SHIPPED` |

Nếu các message đến cùng một queue nhưng có ba consumer đang xử lý song song, không có gì buộc consumer xử lý `E1` phải hoàn thành trước consumer xử lý `E2`. Một tác vụ ghi database có thể mất 500 ms, tác vụ khác chỉ mất 10 ms. Projection cuối cùng có nguy cơ lưu trạng thái cũ.

~~~mermaid
sequenceDiagram
    participant Q as orders.events.queue
    participant C1 as Consumer A
    participant C2 as Consumer B
    participant DB as Order projection

    Q->>C1: E1 (CREATED)
    Q->>C2: E2 (PAID)
    Note over C1: Xử lý chậm
    C2->>DB: Ghi PAID
    C1->>DB: Ghi CREATED
    Note over DB: Kết quả sai nếu không kiểm soát version
~~~

Mục tiêu có thể là:

- **Thứ tự xử lý toàn queue**: không bắt đầu xử lý message tiếp theo trước khi message trước đó hoàn tất.
- **Thứ tự theo aggregate/key**: các sự kiện cùng `orderId` phải theo thứ tự, còn các đơn hàng khác có thể chạy song song.
- **Thứ tự ghi kết quả**: version mới không bị version cũ ghi đè, kể cả khi delivery bị lặp hoặc đến lệch.

Ba mục tiêu này **khác nhau**. SAC giúp kiểm soát **số consumer active trên một queue**. Với listener đồng bộ và prefetch bằng 1, nó hỗ trợ xử lý tuần tự dễ dự đoán hơn. Nhưng để bảo đảm dữ liệu cuối cùng đúng khi có sự cố, vẫn cần versioning, deduplication và chính sách lỗi.

## 3. SAC hoạt động như thế nào?

Khi khai báo queue với argument `x-single-active-consumer=true`, RabbitMQ duy trì cơ chế chỉ chọn một consumer active trong tập consumer đăng ký ở queue đó.

~~~mermaid
flowchart LR
    P["RabbitTemplate / Producers"] --> X["orders.events.exchange"]
    X -->|"order.changed"| Q["orders.serial.queue<br/>x-single-active-consumer=true"]
    Q -->|"Delivery"| A["Ứng dụng A<br/>ACTIVE"]
    Q -. "Chờ, chưa nhận delivery" .-> B["Ứng dụng B<br/>STANDBY"]
    Q -. "Chờ, chưa nhận delivery" .-> C["Ứng dụng C<br/>STANDBY"]
    A -. "Disconnect / cancel" .-> F["RabbitMQ chọn consumer khác"]
    F --> B
~~~

Quy trình thông thường:

1. Ứng dụng A khai báo queue và đăng ký listener.
2. Ứng dụng B, C cũng đăng ký listener tới **cùng queue**, trong cùng virtual host.
3. Broker chọn A làm active. B và C vẫn đăng ký nhưng chưa nhận message từ queue đó.
4. A xử lý message và ACK.
5. Khi A ngừng hoạt động, broker chọn một consumer còn tồn tại để tiếp tục nhận delivery.

SAC **không đồng nghĩa** chỉ được kết nối một consumer. Chính việc có nhiều consumer đăng ký nhưng chỉ một active tạo ra lợi ích **dự phòng**. RabbitMQ thực hiện lựa chọn trên từng queue, không dựa vào tên service, số pod Kubernetes hoặc số thread trong một ứng dụng.

### 3.1. So sánh các phương án

| Phương án | Điều bảo đảm chính | Khi nào dùng |
| --- | --- | --- |
| `concurrency=1` trong một instance | Instance đó dùng một consumer; **không giới hạn** tổng consumer nếu có nhiều instance | Môi trường chỉ chạy một instance, hoặc phối hợp thêm SAC |
| SAC trên queue | Mỗi queue chỉ có một consumer active, các consumer khác có thể đứng chờ | Muốn nhiều replica dự phòng nhưng không xử lý song song cùng queue |
| Exclusive consumer | Queue chỉ cho một consumer độc quyền; consumer khác có thể bị từ chối đăng ký | Khi thực sự cần khóa quyền tiêu thụ, không cần cơ chế standby đăng ký sẵn như SAC |
| Một queue riêng cho mỗi partition/key-group | Cho phép nhiều luồng tuần tự độc lập | Cần mở rộng throughput nhưng vẫn giữ thứ tự theo khóa |
| Nhiều consumer bình thường | Tăng xử lý song song, thứ tự hoàn thành không cố định | Message độc lập, không đòi hỏi tuần tự |

**Chỉ đặt `concurrency=1` là chưa đủ khi chạy nhiều replica.** Nếu ứng dụng A và B đều có một consumer trên queue thông thường, broker có thể giao message cho cả hai. SAC phải được cấu hình **tại queue**.

### 3.2. Phạm vi mà SAC thực sự kiểm soát

SAC kiểm soát **delivery của broker đến các consumer đăng ký với queue**. Nó không trực tiếp kiểm soát:

- Thứ tự các producer khác nhau thực sự publish đến exchange/broker.
- Thứ tự sự kiện ở những queue khác nhau.
- Số tác vụ bất đồng bộ mà **một** listener tự tạo bên trong.
- Việc một message được giao lại sau khi active consumer chết, ACK bị mất hoặc message được requeue.
- Thứ tự ghi side effect ở database hay dịch vụ HTTP.
- Việc message lỗi bị đưa sang DLQ rồi được replay muộn.

Vì vậy, “SAC bảo đảm xử lý đúng thứ tự trong mọi tình huống” là phát biểu quá mạnh. Cần nói rõ **thứ tự nào**, **đơn vị nào**, và **giả định lỗi nào**.

## 4. Khai báo queue có `x-single-active-consumer`

RabbitMQ bật SAC bằng queue argument:

~~~java
QueueBuilder.durable("orders.serial.queue")
        .withArgument("x-single-active-consumer", true)
        .build();
~~~

Argument này phải có khi **khai báo queue**. Không thể bật/tắt SAC trên một queue đã tồn tại bằng cách thay đổi consumer concurrency hoặc thêm một policy thông thường; RabbitMQ không hỗ trợ cấu hình SAC qua policy. Muốn đổi queue hiện có, cần một kế hoạch tạo/migrate queue phù hợp.

### 4.1. Ví dụ topology với exchange, binding và terminal DLQ

~~~java
package com.example.serial;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderedMessagingTopology {

    public static final String EXCHANGE = "orders.events.exchange";
    public static final String ROUTING_KEY = "order.changed";
    public static final String QUEUE = "orders.serial.queue";

    public static final String DLX = "orders.events.dlx";
    public static final String DLQ = "orders.serial.dlq";
    public static final String DEAD_KEY = "order.changed.failed";

    @Bean
    DirectExchange ordersEventsExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue ordersSerialQueue() {
        return QueueBuilder.durable(QUEUE)
                .withArgument("x-single-active-consumer", true)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DEAD_KEY)
                .build();
    }

    @Bean
    Binding ordersSerialBinding() {
        return BindingBuilder.bind(ordersSerialQueue())
                .to(ordersEventsExchange())
                .with(ROUTING_KEY);
    }

    @Bean
    DirectExchange ordersDeadLetterExchange() {
        return new DirectExchange(DLX, true, false);
    }

    @Bean
    Queue ordersSerialDlq() {
        // DLQ cuối cùng: không tự quay về queue chính.
        return QueueBuilder.durable(DLQ).build();
    }

    @Bean
    Binding ordersSerialDlqBinding() {
        return BindingBuilder.bind(ordersSerialDlq())
                .to(ordersDeadLetterExchange())
                .with(DEAD_KEY);
    }
}
~~~

Ở ví dụ này:

- Producer publish đến `orders.events.exchange` với key `order.changed`.
- Binding đưa message vào `orders.serial.queue`.
- Dù A/B/C cùng đăng ký, broker chỉ giao cho một active consumer tại một thời điểm.
- Khi consumer từ chối message với `requeue=false`, DLX có thể đưa message vào `orders.serial.dlq` để điều tra.

**DLQ là đường lỗi**, không phải cách duy trì thứ tự tuyệt đối: nếu event `E2` bị đưa sang DLQ, `E3` có thể tiếp tục được xử lý. Muốn “không bỏ qua một version nào”, ứng dụng phải có quy trình dừng/gắn cờ aggregate và khôi phục khoảng thiếu, không chỉ dựa vào SAC.

### 4.2. Nếu dùng quorum queue

SAC cũng được RabbitMQ hỗ trợ cho **quorum queue**. Khi yêu cầu đặc tính replication/durability của quorum queue, có thể khai báo queue với cả hai argument:

~~~java
@Bean
Queue ordersSerialQuorumQueue() {
    return QueueBuilder.durable("orders.serial.quorum.queue")
            .withArgument("x-queue-type", "quorum")
            .withArgument("x-single-active-consumer", true)
            .build();
}
~~~

Đây là **phương án thay thế**, không phải bean bổ sung để cùng xử lý một luồng với ví dụ classic queue. Nếu chọn quorum queue, hãy thống nhất tên queue và binding cho phương án đó. Kiểu queue là quyết định kiến trúc/khai báo; không thể đơn giản redeclare một classic queue đang tồn tại thành quorum queue với cùng tên.

Việc chọn classic hay quorum queue còn phụ thuộc phiên bản RabbitMQ, chính sách HA, lưu trữ, tải và cách vận hành. **SAC không thay thế cơ chế durability và replication**.

## 5. Cấu hình Spring AMQP để xử lý tuần tự

Queue SAC giới hạn số consumer **active**; phía Spring AMQP nên thiết kế listener cho mô hình xử lý **một message, một lần**. Với Spring Boot có `spring-boot-starter-amqp`, có thể tạo `SimpleRabbitListenerContainerFactory` như sau.

### 5.1. Listener factory: một consumer mỗi instance, prefetch bằng 1

~~~java
package com.example.serial;

import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderedListenerConfiguration {

    @Bean
    Jackson2JsonMessageConverter jsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean
    SimpleRabbitListenerContainerFactory orderedListenerFactory(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter jsonMessageConverter) {

        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(jsonMessageConverter);

        factory.setConcurrentConsumers(1);
        factory.setMaxConcurrentConsumers(1);
        factory.setPrefetchCount(1);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setDefaultRequeueRejected(false);

        return factory;
    }
}
~~~

Vì sao chọn những tham số này?

| Cấu hình | Lợi ích | Điều cần nhớ |
| --- | --- | --- |
| `concurrentConsumers=1`, `maxConcurrentConsumers=1` | Một consumer trong mỗi instance; dễ quan sát và tránh consumer dư thừa | **SAC** mới giới hạn toàn bộ các replica |
| `prefetchCount=1` | Broker thường chỉ giao **một delivery chưa ACK** đến active consumer tại một thời điểm | Giảm khả năng pipeline, có thể giảm throughput |
| `AcknowledgeMode.AUTO` | Container ACK sau khi listener return thành công; xử lý exception theo cấu hình | Không phải `autoAck=true` của RabbitMQ client |
| `defaultRequeueRejected(false)` | Tránh vòng requeue vô hạn khi listener thất bại | Queue cần DLX/DLQ và chính sách lỗi phù hợp |

**Prefetch bằng 1 là lựa chọn dễ hiểu nhất khi cần xử lý tuần tự nghiêm ngặt.** Nếu prefetch lớn hơn 1, broker có thể gửi nhiều message chưa ACK tới một consumer. Listener đồng bộ vẫn có thể xử lý tuần tự, nhưng nếu ứng dụng tự tạo thread hoặc ACK không đúng thứ tự, mức độ chắc chắn của toàn luồng sẽ giảm.

SAC là tính năng **broker queue**; cấu hình `orderedListenerFactory` không tự kích hoạt SAC trên một queue thiếu `x-single-active-consumer`.

### 5.2. Event DTO và consumer

Ví dụ event chứa định danh và phiên bản theo đơn hàng:

~~~java
package com.example.serial;

import java.util.UUID;

public record OrderChanged(
        UUID eventId,
        String orderId,
        long aggregateVersion,
        String status
) {}
~~~

Listener không tạo tác vụ nền rồi return ngay; nó đợi service xử lý xong:

~~~java
package com.example.serial;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderedOrderListener {

    private final OrderStateService orderStateService;

    public OrderedOrderListener(OrderStateService orderStateService) {
        this.orderStateService = orderStateService;
    }

    @RabbitListener(
            queues = OrderedMessagingTopology.QUEUE,
            containerFactory = "orderedListenerFactory")
    public void onOrderChanged(OrderChanged event) {
        // Service hoàn thành DB transaction trước khi listener return.
        orderStateService.applyOnce(event);
    }
}
~~~

Hợp đồng của `OrderStateService.applyOnce()` phải bảo đảm:

1. Giao dịch ghi kết quả thành công hoặc ném exception để listener không ACK như thành công.
2. `eventId` đã xử lý trước đó không tạo side effect lần hai.
3. `aggregateVersion` cũ không ghi đè phiên bản mới.
4. Nếu phiên bản phải **liền mạch** mà thiếu một version, không âm thầm áp dụng các event phía sau.

Đối với state trong database, có thể dùng bảng đánh dấu event đã xử lý kèm unique key (`consumer_name`, `event_id`), cùng transaction với bảng trạng thái đích. Nếu chỉ cần trạng thái mới nhất, conditional update theo version có thể đủ cho một số nghiệp vụ; nếu cần ghi nhận **mọi bước chuyển trạng thái**, phải xử lý khoảng thiếu version riêng.

### 5.3. Gửi event bằng `RabbitTemplate`

~~~java
package com.example.serial;

import java.util.UUID;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderChangedPublisher {

    private final RabbitTemplate rabbitTemplate;

    public OrderChangedPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(String orderId, long version, String status) {
        var event = new OrderChanged(
                UUID.randomUUID(), orderId, version, status);

        rabbitTemplate.convertAndSend(
                OrderedMessagingTopology.EXCHANGE,
                OrderedMessagingTopology.ROUTING_KEY,
                event);
    }
}
~~~

Ví dụ này minh họa exchange/routing key; để gửi/nhận JSON tương ứng, `RabbitTemplate` phải sử dụng JSON converter phù hợp. Trong ứng dụng Spring Boot, converter bean có thể được nối vào template qua auto-configuration khi cấu hình phù hợp; cần kiểm tra thực tế cùng consumer.

**Quan trọng:** `UUID.randomUUID()` ở ví dụ trên tạo ID cho một **event mới**. Khi retry publish **cùng một event**, phải giữ nguyên `eventId`. Với hệ thống production có cập nhật DB rồi publish, nên ghi event vào **transactional outbox** và relay gửi lại từ bản ghi bền vững. SAC không xử lý cửa sổ mất event giữa DB commit và publish.

## 6. Thứ tự được bảo đảm đến đâu?

RabbitMQ queue có thứ tự lưu/đưa message ra theo các quy tắc hàng đợi, nhưng **thứ tự hiệu ứng cuối cùng** phụ thuộc nhiều ranh giới khác nhau.

### 6.1. Thứ tự publish không đồng nhất với thứ tự nghiệp vụ

Ví dụ hai producer gửi event cho cùng `orderId`:

~~~text
Producer A ghi version 7 → tạm dừng trước publish
Producer B ghi version 8 → publish trước
Producer A tiếp tục       → publish version 7
RabbitMQ nhìn thấy: version 8, rồi version 7
~~~

SAC không thể biết version 7 “nên đến trước” version 8. Nó chỉ tiêu thụ theo thứ tự broker giao, chịu ảnh hưởng các quy tắc queue và sự cố.

Giải pháp: duy trì **version/sequence** ngay tại nơi ghi dữ liệu nghiệp vụ; bảo đảm publish nhất quán bằng outbox/relay thích hợp; và consumer kiểm tra version. Nếu yêu cầu thứ tự chặt theo aggregate, phải giải quyết cả **thứ tự ghi/publish** và **thứ tự xử lý**.

### 6.2. Một consumer vẫn có thể xử lý song song bên trong

Ví dụ lỗi thiết kế:

~~~java
@RabbitListener(
        queues = OrderedMessagingTopology.QUEUE,
        containerFactory = "orderedListenerFactory")
public void onOrderChanged(OrderChanged event) {
    executorService.submit(() -> process(event));
    // Return ngay => container có thể ACK trước khi process xong.
}
~~~

Mặc dù queue dùng SAC, nhiều tác vụ được gửi vào thread pool có thể hoàn thành **không đúng thứ tự**. Nếu process thất bại sau khi listener return, container có thể đã ACK message, gây mất cơ hội redelivery.

Khi yêu cầu tuần tự, thực hiện xử lý **đồng bộ trong listener** hoặc dùng một cơ chế bất đồng bộ có queue nội bộ, thứ tự và ranh giới ACK được thiết kế tường minh. Đừng thêm `@Async` vào đường xử lý chỉ để tăng throughput mà không kiểm tra hậu quả đối với ACK.

### 6.3. Redelivery và retry có thể thay đổi thứ tự quan sát

Một message chưa ACK có thể được gửi lại sau khi consumer chết. Nếu dùng `basicNack(requeue=true)` hoặc retry qua TTL/DLX, vị trí và thời điểm message quay lại không luôn tương đương “quay lại đúng vị trí ban đầu rồi chặn mọi message phía sau”. Trong khi đó, chuyển message lỗi sang DLQ cho phép message tiếp theo tiếp tục.

Ví dụ:

~~~text
E1 (version 1): thành công, ACK
E2 (version 2): lỗi, chuyển sang DLQ
E3 (version 3): thành công, ACK
E2: được replay sau khi sửa lỗi
~~~

Nếu nghiệp vụ yêu cầu áp dụng **mọi chuyển trạng thái đúng thứ tự**, thứ tự trên là không chấp nhận được, dù SAC hoạt động chính xác.

### 6.4. Prefetch và ACK

Với `prefetchCount=1`, khi message `E2` chưa được ACK, broker không tiếp tục giao một delivery mới tới cùng consumer trong phạm vi credit tương ứng. Điều này giúp hạn chế các delivery chưa xử lý dồn cùng lúc.

Tuy vậy:

- Khi listener xử lý **xong DB nhưng ACK chưa đến broker**, consumer có thể chết và broker redeliver `E2`.
- Khi event đã vào DLQ hoặc bị ACK sau khi bỏ qua, message phía sau có thể được xử lý.
- Với nhiều queue, mỗi queue có active consumer riêng; hoàn toàn có thể chạy song song.
- Những thay đổi do ứng dụng ngoài queue (HTTP callback, job scheduler, outbox relay khác) vẫn có thể xảy ra theo thứ tự khác.

SAC + prefetch 1 hỗ trợ một **đường xử lý tuần tự cơ bản**, không thay thế idempotency hay kiểm tra version.

## 7. Failover: active chuyển sang standby

Giả sử ứng dụng A đang active, ứng dụng B đang standby. A nhận event `E42` và đang cập nhật DB.

~~~mermaid
sequenceDiagram
    participant Q as RabbitMQ (SAC)
    participant A as Instance A (active)
    participant B as Instance B (standby)
    participant DB as Database

    Q->>A: Giao E42
    A->>DB: COMMIT E42
    Note over A,Q: A mất kết nối trước khi broker nhận ACK
    Q-->>B: Chọn B làm active
    Q->>B: Redelivery E42
    B->>DB: Kiểm tra eventId=E42
    DB-->>B: Đã xử lý, bỏ qua side effect
    B-->>Q: ACK
~~~

Có hai cửa sổ quan trọng:

| Thời điểm A chết | Kết quả có thể xảy ra | Điều cần làm |
| --- | --- | --- |
| Trước DB commit, chưa ACK | Transaction rollback; message có thể giao lại cho B | B xử lý lại và commit |
| Sau DB commit, trước khi broker nhận ACK | Message có thể giao lại dù side effect đã thành công | B phát hiện duplicate bằng `eventId` và ACK mà không lặp side effect |

Khi active consumer không còn đủ điều kiện tiếp tục, RabbitMQ có thể chuyển quyền active sang consumer khác. **Quá trình failover có độ trễ**, phụ thuộc phát hiện lỗi kết nối, topology và kiểu queue. Không khẳng định có thời gian chuyển đổi cố định hoặc không có khoảng gián đoạn.

Một consumer mới active không tự động khôi phục ngữ cảnh trong heap của consumer cũ. Mọi thông tin cần cho recovery (eventId, version, tiến độ, transaction result) phải nằm trong kho dữ liệu hoặc message bền vững.

### 7.1. Idempotency trong database

Có thể lưu bảng đánh dấu event đã xử lý:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      UUID NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE order_projection (
    order_id VARCHAR(64) PRIMARY KEY,
    version  BIGINT NOT NULL,
    status   VARCHAR(32) NOT NULL
);
~~~

Trong **cùng một database transaction**:

1. Thử insert `processed_events(consumerName, eventId)` với unique constraint.
2. Nếu event đã được commit trước đó, bỏ qua side effect và kết thúc thành công.
3. Nếu chưa có, kiểm tra version và cập nhật trạng thái nghiệp vụ.
4. Commit cả marker lẫn kết quả, sau đó listener mới return để container ACK.

Cách này xử lý redelivery an toàn hơn việc chỉ đọc `redelivered` trong header. Flag redelivered không phải khóa định danh ổn định và không thể bảo đảm không có bản sao do producer publish lại.

### 7.2. Xử lý khoảng thiếu version

Có hai loại yêu cầu:

- **Chỉ giữ trạng thái mới nhất**: cho phép áp dụng version cao hơn và bỏ qua version thấp hơn, ví dụ projection `status`/`lastVersion`.
- **Bắt buộc xử lý mọi bước**: cần `expectedVersion = currentVersion + 1` cho từng aggregate. Nếu nhận version 7 khi đang ở version 5, phải lưu lại/chờ version 6 hoặc đưa aggregate vào quy trình khôi phục; không tự coi version 7 là hợp lệ.

Đừng dùng retry vô hạn để “chờ version còn thiếu” nếu không có cơ chế giới hạn và cảnh báo: nó có thể làm tắc toàn queue SAC, ảnh hưởng những aggregate độc lập phía sau. Có thể chọn dừng có cảnh báo, lưu sự kiện chờ theo aggregate hoặc chuyển sang kiến trúc partition theo khóa.

## 8. Retry, dead-letter và bài toán chặn cả queue

Vì một queue SAC có một consumer active, một message lỗi không được kiểm soát có thể chặn dòng xử lý của cả queue.

Ví dụ listener ném exception liên tục; với requeue ngay lập tức, message độc quay lại và làm CPU/log tăng cao. Nếu message được đưa sang DLQ, luồng có thể tiếp tục nhưng **một bước nghiệp vụ đã bị bỏ qua**.

| Chính sách lỗi | Ưu điểm | Rủi ro với thứ tự |
| --- | --- | --- |
| Requeue ngay (`requeue=true`) | Không bỏ message ngay | Có thể lặp nhanh, tiêu thụ tài nguyên và đổi thứ tự khi giao lại |
| Retry hữu hạn trong listener | Giữ event tại nơi xử lý trong số lần thử ngắn | Giảm throughput khi lỗi; không giải quyết outage kéo dài |
| Retry qua delay queue | Giảm tải khi hệ thống phụ thuộc lỗi | Message rời queue chính; event phía sau có thể chạy trước |
| Terminal DLQ | Có nơi điều tra message lỗi và không retry mãi | Dễ xuất hiện khoảng thiếu trong chuỗi event nghiệp vụ |
| Tạm dừng consumer và khắc phục thủ công | Giữ nguyên ranh giới trước message lỗi khi cấu hình phù hợp | Toàn queue bị chặn; cần SLA vận hành và cảnh báo |
| Tách queue theo aggregate/shard | Một key lỗi không chặn mọi key khác | Quản lý nhiều queue, số replica và routing phức tạp hơn |

### 8.1. Cấu hình retry hữu hạn minh họa

~~~java
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;

// Đặt trong cấu hình orderedListenerFactory, trước return:
factory.setAdviceChain(
        RetryInterceptorBuilder.stateless()
                .maxAttempts(3)
                .backOffOptions(500, 2.0, 2_000)
                .recoverer(new RejectAndDontRequeueRecoverer())
                .build());
~~~

`maxAttempts(3)` gồm lần gọi đầu và hai lần thử lại trong cùng chu kỳ listener; sau đó recoverer chỉ thị reject không requeue. Queue ở mục 4 có DLX để nhận message bị dead-letter.

**Đây là phương án khi chấp nhận chuyển message lỗi sang DLQ rồi tiếp tục.** Nếu nghiệp vụ yêu cầu xử lý mọi version liên tiếp, không thể dùng nó như một giải pháp “giữ thứ tự tuyệt đối”. Cần quy tắc dừng hoặc cơ chế lưu các event chờ của cùng aggregate.

### 8.2. Vì sao ACK thủ công không tự giải quyết thứ tự?

`AcknowledgeMode.MANUAL` cho phép code gọi `basicAck`, `basicNack`. Nhưng đặt ACK trước DB commit vẫn có thể mất tác dụng nghiệp vụ; ACK sau commit vẫn có thể redelivery nếu ACK thất lạc. Manual ACK chỉ chuyển trách nhiệm quyết định thời điểm sang ứng dụng.

Với listener đồng bộ và DB transaction được đóng đúng ranh giới, `AcknowledgeMode.AUTO` thường dễ dùng để tránh quên ACK. Chỉ chọn MANUAL khi cần kiểm soát đặc biệt và đã xác minh đầy đủ delivery tag, channel lifecycle, exception path cùng tính idempotent.

## 9. SAC và thông lượng: khi nào cần phân vùng queue?

SAC bảo vệ một luồng xử lý tuần tự nhưng cũng tạo **một điểm giới hạn throughput** trên từng queue. Thêm 10 pod standby không làm cùng queue xử lý nhanh gấp 10 lần.

Ví dụ consumer xử lý mỗi message trung bình 20 ms thì công suất gần đúng là:

\[
\mu \approx \frac{1}{0.020} = 50\ \text{message/giây}
\]

Nếu producer gửi trung bình 80 message/giây, backlog có thể tăng khoảng 30 message/giây, tương đương 1.800 message/phút, nếu điều kiện tải giữ ổn định và không có cơ chế giới hạn đầu vào. SAC không tự giảm tốc độ producer.

### 9.1. Chia theo `orderId` để giữ thứ tự từng đơn hàng

Khi các đơn hàng **độc lập**, không nhất thiết phải tuần tự hóa toàn bộ sự kiện của tất cả đơn. Có thể dùng một tập queue cố định:

~~~text
orders.partition.0  (SAC)  ← orderId hash về 0
orders.partition.1  (SAC)  ← orderId hash về 1
orders.partition.2  (SAC)  ← orderId hash về 2
orders.partition.3  (SAC)  ← orderId hash về 3
~~~

Mọi event của **cùng `orderId`** phải được publish tới **cùng partition** và theo một quy tắc thứ tự nguồn phù hợp. Mỗi partition có active consumer riêng; bốn partition có thể xử lý đồng thời, nhưng từng partition chạy tuần tự.

Ví dụ cách tính partition tĩnh ở producer:

~~~java
public final class OrderPartitionRouting {

    private static final int PARTITIONS = 4;

    private OrderPartitionRouting() {
    }

    public static String routingKey(String orderId) {
        int index = Math.floorMod(orderId.hashCode(), PARTITIONS);
        return "orders.partition." + index;
    }
}
~~~

Trong topology thực tế, cần có một direct exchange với các binding chính xác từ từng routing key đến queue tương ứng, và mỗi queue được khai báo `x-single-active-consumer=true`.

**Ràng buộc quan trọng:**

- Không thay đổi số partition tùy tiện. Từ 4 sang 8 có thể khiến các event mới của cùng `orderId` chuyển queue trong khi event cũ còn tồn, phá vỡ thứ tự.
- Không chọn partition bằng round-robin cho cùng aggregate nếu cần giữ thứ tự.
- Hãy giữ thứ tự publish của từng aggregate; hash chỉ giải quyết việc **cùng key đến cùng queue**, không sửa lỗi producer gửi version 8 trước version 7.
- Một partition chứa nhiều key; một message lỗi có thể chặn các key khác cùng partition, nên vẫn cần chính sách retry hợp lý.
- Phân bố tải có thể lệch khi một orderId rất “nóng”. Cần đo queue depth và tuổi event theo partition.

### 9.2. Tiêu chí quyết định

| Tình huống | Gợi ý kiến trúc |
| --- | --- |
| Lưu lượng nhỏ, thứ tự toàn luồng là bắt buộc | Một queue SAC, một listener đồng bộ, prefetch 1 |
| Muốn chạy nhiều replica dự phòng nhưng xử lý tuần tự | SAC trên một queue + nhiều instance standby |
| Nhiều aggregate độc lập, cần throughput cao | Nhiều partition queues, mỗi queue SAC |
| Message độc lập, không yêu cầu thứ tự hoàn thành | Consumer concurrency bình thường |
| Phải xử lý mọi version liên tiếp, không chấp nhận khoảng thiếu | SAC hoặc partition + kiểm tra expectedVersion + quy trình xử lý gap |
| Cần gọi DB hoặc API lâu cho từng message | Xem xét tối ưu batch/IO, tách quy trình dài thành job; theo dõi latency của một consumer active |

## 10. Vận hành và quan sát SAC

Khi dùng SAC, số consumer **registered** có thể lớn hơn số consumer **active**. Đừng thấy queue có ba consumer rồi kết luận ba consumer đang chia tải.

Những chỉ số cần theo dõi:

| Chỉ số | Mục đích |
| --- | --- |
| Consumer active/standby và thay đổi vai trò | Phát hiện failover, active bị mất kết nối liên tục |
| `messages_ready` | Lượng message đang đợi active consumer |
| `messages_unacknowledged` | Delivery đã nhận nhưng chưa ACK |
| Publish rate, delivery rate, ACK rate | Tìm nơi tạo backlog hoặc xử lý chậm |
| Processing latency p50/p95/p99 | Ước lượng công suất của consumer active |
| Consumer connection/channel churn | Phát hiện kết nối không ổn định dẫn đến chuyển active |
| Redelivery count/rate | Phát hiện crash, ACK thất lạc, requeue |
| DLQ size và oldest message age | Phát hiện poison message và event bị bỏ qua |
| Deduplication hits, out-of-order versions | Đo duplicate và vi phạm thứ tự nghiệp vụ |
| End-to-end event age | Đo thời gian từ lúc tạo event đến khi DB đích commit |

Một sự cố điển hình là **đăng ký được nhiều standby nhưng throughput vẫn thấp**: đó có thể là đặc tính đúng của SAC, không phải broker không chia tải. Hãy xem latency mỗi event, độ sâu queue và công suất của một active consumer trước khi cân nhắc partition.

Khi active consumer chuyển sang replica khác, nên log các trường như `eventId`, `orderId`, `aggregateVersion`, consumer instance ID, queue, thời điểm bắt đầu/kết thúc xử lý, trạng thái commit và thông tin redelivery. Không dùng `deliveryTag` làm khóa dedup vì delivery tag chỉ có ý nghĩa trong phạm vi channel.

## 11. Kịch bản kiểm thử với hai instance

Để chứng minh cấu hình SAC hoạt động đúng, cần chạy kiểm thử ở **broker thực** với ít nhất hai instance hoặc hai consumer đăng ký cùng queue. Những bài thử dưới đây dùng topology ở mục 4 và listener ở mục 5.

### Kịch bản A — chỉ một instance nhận delivery

1. Khởi động hai instance A và B cùng đăng ký `orders.serial.queue`.
2. Publish lần lượt `E1`, `E2`, `E3` với routing key `order.changed`.
3. Đối chiếu log hoặc giao diện quản lý broker để xem consumer active.
4. Xác minh chỉ consumer active nhận các delivery mới trong điều kiện bình thường.

**Kỳ vọng:** không có cơ chế cạnh tranh chia message cho cả A và B như queue có nhiều consumer thông thường.

### Kịch bản B — failover khi active dừng

1. Giữ A active và B standby.
2. Dừng A có chủ đích.
3. Publish thêm `E4`.
4. Xác minh B được chọn làm active và tiếp tục nhận message.

**Kỳ vọng:** queue có thể phục hồi việc tiêu thụ mà không cần người vận hành tạo một consumer mới. Đo thời gian chuyển vai trò; không giả định bằng 0.

### Kịch bản C — crash sau DB commit, trước ACK

1. Cho A xử lý `E5` và commit DB.
2. Cắt kết nối hoặc mô phỏng redelivery trước khi broker xác nhận ACK.
3. Để B tiếp tục nhận event.
4. Xác minh marker `eventId=E5` ngăn ghi trùng.

**Kỳ vọng:** có thể nhận lại delivery nhưng không áp dụng side effect hai lần.

### Kịch bản D — listener vô tình xử lý bất đồng bộ

1. Thử phiên bản listener đẩy event vào thread pool rồi return ngay, chỉ trong môi trường kiểm thử.
2. Tạo các event có thời gian xử lý khác nhau.
3. Quan sát thứ tự hoàn thành và thời điểm ACK.
4. Khôi phục listener đồng bộ.

**Kỳ vọng:** nhìn thấy vì sao SAC không bảo đảm thứ tự hoàn thành khi tự thêm concurrency bên trong handler.

### Kịch bản E — lỗi và DLQ tạo khoảng thiếu

1. Gửi các event version 1, 2, 3 của cùng đơn hàng.
2. Làm version 2 thất bại vượt retry budget.
3. Xác minh version 2 đi DLQ và version 3 có thể được tiếp tục delivery.
4. Kiểm tra version guard hoặc quy trình chờ gap không cho projection rơi vào trạng thái sai.

**Kỳ vọng:** xác định rõ chính sách nghiệp vụ khi có event thiếu, không suy diễn SAC sẽ tự sửa thứ tự.

### Kịch bản F — nhiều producer gửi sai thứ tự

1. Cố ý publish version 8 trước version 7 từ hai producer.
2. Xác minh consumer nhận theo thứ tự broker thấy, không tự sắp xếp theo version.
3. Kiểm tra cơ chế version/sequence trong DB.

**Kỳ vọng:** phân biệt thứ tự tới queue với thứ tự sự kiện nghiệp vụ.

### Kịch bản G — tải vượt công suất một active consumer

1. Tăng tốc độ publish lên trên tốc độ listener có thể commit.
2. Theo dõi `messages_ready`, event age, CPU và database latency.
3. Tăng số replica standby mà không tăng số queue.
4. So sánh với phương án chia queue theo orderId.

**Kỳ vọng:** chứng minh standby tăng khả năng tiếp quản, không tăng throughput của một queue SAC.

### Kịch bản H — redeclare queue với argument khác

1. Trong môi trường kiểm thử, tạo queue SAC.
2. Thử khai báo lại **cùng tên queue** nhưng không có argument `x-single-active-consumer` hoặc có giá trị khác.
3. Quan sát lỗi không tương đương argument (nếu broker từ chối redeclare).
4. Khôi phục topology nhất quán.

**Kỳ vọng:** thấy rằng thay đổi queue argument là bài toán migration, không phải chỉ sửa annotation của consumer rồi restart.

## 12. Lỗi hiểu sai thường gặp

| Hiểu sai | Diễn giải đúng |
| --- | --- |
| “`concurrency=1` bảo đảm cả cluster chỉ có một consumer” | Mỗi instance có thể có một consumer; phải dùng SAC hoặc cơ chế điều phối khác để giới hạn toàn queue |
| “SAC luôn giữ đúng thứ tự nghiệp vụ” | Nó kiểm soát active delivery trên một queue; cần kiểm soát publish, version, redelivery và side effect |
| “Có hai replica tức là xử lý nhanh gấp đôi” | Replica standby chỉ sẵn sàng takeover; throughput vẫn do một active consumer của queue quyết định |
| “Prefetch 100 không ảnh hưởng gì vì chỉ có một consumer” | Một active consumer vẫn có thể giữ nhiều message chưa ACK; cần cân nhắc độ trễ/độ tin cậy |
| “Consumer trả về là message đã xử lý xong” | Sai nếu listener tự tạo tác vụ async rồi return; ACK có thể đến trước side effect |
| “SAC ngăn message trùng” | Crash sau DB commit trước ACK có thể tạo redelivery; cần idempotency |
| “Đẩy một message lỗi vào DLQ vẫn giữ thứ tự tuyệt đối” | Message sau có thể được xử lý trước khi lỗi được replay |
| “Có thể bật SAC bằng policy cho queue cũ” | SAC là queue argument khai báo ban đầu; cần kế hoạch migration |
| “Một queue SAC đủ mở rộng vô hạn” | Một active consumer giới hạn throughput; cần partition khi key độc lập |
| “Mọi event cùng orderId vào cùng partition là đã đúng thứ tự” | Còn phải kiểm soát thứ tự publish và version ở nơi ghi kết quả |

## 13. Checklist triển khai

- [ ] Xác định yêu cầu là thứ tự **toàn queue**, **theo aggregate** hay chỉ thứ tự cập nhật kết quả.
- [ ] Khai báo queue với `x-single-active-consumer=true` ngay từ đầu; kiểm tra arguments của queue đang chạy.
- [ ] Nếu chạy nhiều replica, xác minh chỉ một consumer **active** nhưng các consumer còn lại vẫn đăng ký.
- [ ] Đặt listener đồng bộ và `prefetchCount=1` khi cần đường xử lý tuần tự đơn giản.
- [ ] Chỉ ACK khi xử lý/transaction đã kết thúc thành công; phân biệt AUTO của Spring với auto-ack của broker.
- [ ] Có `eventId` ổn định và deduplication bền vững; ACK thất lạc không gây side effect trùng.
- [ ] Có `aggregateVersion` hoặc sequence guard nếu kết quả phải tôn trọng thứ tự nghiệp vụ.
- [ ] Định nghĩa cách xử lý event lỗi: retry hữu hạn, tạm dừng, DLQ, khôi phục khoảng thiếu.
- [ ] DLX/DLQ, routing key và binding đã được kiểm chứng; replay không tạo vòng lặp.
- [ ] Producer dùng publisher confirms/returns và outbox nếu nghiệp vụ không chấp nhận mất event giữa DB commit và publish.
- [ ] Quan sát queue depth, unacked, consumer active, redelivery, DLQ, processing latency và event age.
- [ ] Nếu cần thông lượng cao hơn, chọn partition theo key ổn định và lên kế hoạch migration khi thay đổi partition count.
- [ ] Đã kiểm thử failover ở cả hai thời điểm: **trước commit** và **sau commit nhưng trước ACK**.

## 14. Tổng kết

**Single Active Consumer** cho RabbitMQ là cách thực tế để có **một consumer active trên mỗi queue** trong khi vẫn giữ nhiều consumer standby để tiếp quản khi instance hiện tại gặp lỗi. Trong Spring AMQP, cấu hình thường kết hợp queue argument `x-single-active-consumer=true` với `@RabbitListener` đồng bộ, `prefetchCount=1`, ACK sau khi xử lý thành công và một đường lỗi có điểm dừng.

Nhưng **tiêu thụ tuần tự không tự biến thành xử lý nghiệp vụ chính xác một lần hoặc đúng thứ tự tuyệt đối**. Producer có thể publish sai thứ tự, một message có thể redeliver sau failover, event có thể đi DLQ và được replay muộn, hoặc listener có thể tự xử lý song song. Với dữ liệu quan trọng, cần giữ `eventId` và `aggregateVersion`, viết consumer idempotent, quy định cách xử lý khoảng thiếu version và quan sát toàn tuyến.

Khi một queue trở thành nút thắt, mở rộng bằng cách **chia queue theo khóa nghiệp vụ** và bật SAC cho từng partition, thay vì chỉ tăng số replica chờ trên cùng queue. Cách này cho phép bảo vệ thứ tự ở phạm vi thật sự cần thiết mà vẫn giữ được khả năng mở rộng, failover và độ tin cậy đầu cuối trong hệ thống **SPRING_AMQP**.
