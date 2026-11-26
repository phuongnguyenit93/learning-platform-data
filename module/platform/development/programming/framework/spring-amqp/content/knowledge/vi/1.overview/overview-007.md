# Luồng tổng thể từ tạo thông điệp đến xử lý và xác nhận

Trong ứng dụng Spring, một tác vụ không nhất thiết phải được xử lý ngay trong luồng HTTP. Chẳng hạn, sau khi ghi nhận đơn hàng, hệ thống có thể gửi một thông điệp để dịch vụ khác tạo thông báo, cập nhật thống kê hoặc đồng bộ dữ liệu. **Spring AMQP** kết nối ứng dụng Java với RabbitMQ: phía gửi thường dùng `RabbitTemplate`, phía nhận thường dùng `@RabbitListener`.

Bài này theo dõi **một thông điệp từ khi được tạo, xuất bản, định tuyến, nằm trong hàng đợi, được xử lý cho đến khi được xác nhận**. Mục tiêu là phân biệt rõ ba việc thường bị nhầm lẫn:

1. Ứng dụng gửi đã gọi lệnh publish.
2. RabbitMQ đã chấp nhận thông điệp ở phía broker.
3. Ứng dụng nhận đã xử lý thành công và xác nhận lần giao thông điệp đó.

Ba sự kiện trên diễn ra ở những thời điểm khác nhau; thành công của sự kiện trước **không tự chứng minh** thành công của sự kiện sau.

## 1. Các thành phần trong một lần giao thông điệp

| Thành phần | Trách nhiệm trong luồng |
| --- | --- |
| **Producer** | Tạo nội dung thông điệp và gọi `RabbitTemplate.convertAndSend(...)`. |
| **RabbitTemplate** | Chuyển đổi payload thành AMQP message và publish qua connection/channel đến broker. |
| **Exchange** | Nhận thông điệp mới và quyết định định tuyến theo loại exchange, routing key, binding. |
| **Binding** | Quy tắc nối exchange với queue; với direct exchange, binding key thường được so với routing key. |
| **Queue** | Giữ thông điệp sẵn sàng giao cho consumer, theo các thiết lập về độ bền và chính sách của queue. |
| **Consumer / @RabbitListener** | Nhận delivery, thực thi nghiệp vụ; có thể xử lý thành công hoặc thất bại. |
| **Publisher confirm** | Tín hiệu broker gửi **về producer** để xác nhận việc publish được broker xử lý. |
| **Consumer acknowledgment (ack)** | Tín hiệu consumer gửi **về broker** sau khi xử lý delivery, để broker biết có thể loại bỏ delivery khỏi trạng thái chưa xác nhận. |

Ví dụ, hệ thống dùng:

- Exchange `orders.events` (loại `direct`).
- Routing key `order.created`.
- Binding từ exchange trên đến queue `orders.created.q` với binding key `order.created`.
- Listener nhận từ `orders.created.q` để xử lý sự kiện tạo đơn hàng.

Với **direct exchange**, thông điệp mang routing key `order.created` sẽ được đưa tới những queue có binding key phù hợp. Một exchange có thể định tuyến đến nhiều queue; một queue cũng có thể có nhiều binding. Consumer đọc **queue**, không đọc trực tiếp exchange.

## 2. Sơ đồ luồng từ đầu đến cuối

~~~mermaid
sequenceDiagram
    autonumber
    participant A as API / OrderService
    participant P as RabbitTemplate
    participant B as RabbitMQ broker
    participant C as @RabbitListener
    A->>A: Tạo event với ID, payload
    A->>P: convertAndSend(exchange, key, event)
    P->>B: basic.publish
    B->>B: Exchange + binding -> queue
    opt Bật publisher confirms
        B-->>P: basic.ack / basic.nack của publisher
    end
    B->>C: Giao message từ queue
    C->>C: Xử lý nghiệp vụ
    alt Xử lý thành công
        C-->>B: Consumer basic.ack
    else Không xử lý được
        C-->>B: basic.nack / basic.reject
        B->>B: Requeue / dead-letter / loại bỏ theo cấu hình
    end
~~~

**Đọc sơ đồ theo hai vòng xác nhận riêng:**

- **Vòng publish**: `producer → broker → producer`. Publisher confirm cho biết broker xử lý việc publish; nó **không xác nhận** nghiệp vụ của listener đã chạy.
- **Vòng consume**: `broker → consumer → broker`. Consumer ack cho biết một delivery đã được consumer chấp nhận sau xử lý; nó **không thay thế** publisher confirm.

Đường trả về `basic.return` là trường hợp khác nữa: nếu bật cờ `mandatory` mà broker không định tuyến được thông điệp tới queue nào, broker có thể trả thông điệp về producer. Một publish **có thể được publisher-confirm ACK nhưng vẫn bị return vì không có queue phù hợp**. Vì vậy, khi cần bảo đảm thông điệp được định tuyến, ứng dụng phải xem xét cả confirm lẫn returned message.

## 3. Theo dõi chi tiết từng giai đoạn

### Bước 1 — Tạo thông điệp

Producer xác định **sự kiện gì đã xảy ra**, **khóa nhận diện sự kiện**, nội dung và metadata cần thiết. Ví dụ:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "orderId": "ORD-1001",
  "occurredAt": "2026-11-26T01:30:00Z"
}
~~~

Payload không bắt buộc là JSON; `RabbitTemplate` có thể gửi chuỗi, byte hoặc object thông qua `MessageConverter`. Nếu gửi object dưới dạng JSON, hai bên cần thống nhất định dạng, kiểu dữ liệu và cách tương thích khi schema thay đổi. `eventId` đặc biệt hữu ích để loại trừ tác động lặp khi thông điệp được giao lại.

### Bước 2 — Producer publish qua RabbitTemplate

Lệnh thường gặp:

~~~java
rabbitTemplate.convertAndSend(
    "orders.events",
    "order.created",
    "ORD-1001"
);
~~~

Ở đây `orders.events` là **exchange**, `order.created` là **routing key**, và `ORD-1001` là payload ví dụ. Lời gọi trả về không có nghĩa listener đã hoàn tất xử lý. Nếu cần biết broker có xác nhận publish hay chưa, phải cấu hình và theo dõi **publisher confirms**.

### Bước 3 — Exchange định tuyến qua binding

Broker nhận publish, tra các binding của exchange và chọn queue đích. Với direct exchange trong ví dụ:

~~~text
basic.publish(exchange="orders.events", routingKey="order.created")
                     |
                     v
                orders.events
                     |
           binding key "order.created"
                     |
                     v
               orders.created.q
~~~

Nếu không có binding phù hợp, thông điệp có thể không đến được queue nào. Khi `mandatory=false` (mặc định ở nhiều cấu hình), một thông điệp không định tuyến được có thể bị bỏ mà producer không nhận `basic.return`. Với `mandatory=true`, hãy theo dõi returned message để phát hiện vấn đề topology/routing.

### Bước 4 — Thông điệp chờ trong queue

RabbitMQ quản lý các thông điệp **ready** (đang chờ được giao) và **unacknowledged** (đã giao nhưng chưa được consumer xác nhận). Một queue có thể có nhiều consumer và RabbitMQ phân phối delivery theo trạng thái consumer, prefetch và các điều kiện khác.

**Durable queue** giúp định nghĩa queue tồn tại qua lần khởi động lại broker; nó **không tự đủ** để đảm bảo mọi thông điệp tồn tại qua sự cố. Độ bền còn phụ thuộc delivery mode của message, loại queue, chính sách replication/persistence và việc broker đã xác nhận publish ở thời điểm nào. Với dữ liệu quan trọng, nên thiết kế đồng thời queue phù hợp, persistent messages và publisher confirms.

### Bước 5 — Listener nhận và thực thi nghiệp vụ

Container của Spring AMQP nhận message từ queue và gọi method có `@RabbitListener`. Việc xử lý có thể gồm ghi cơ sở dữ liệu, gửi thông báo hoặc cập nhật trạng thái. Cần phân biệt **nhận được delivery** và **hoàn thành side effect**: nếu chương trình chết ở giữa, broker có thể chưa nhận ack, và thông điệp sẽ có khả năng được giao lại.

### Bước 6 — Xác nhận hoặc xử lý thất bại

Trong Spring AMQP, hai chế độ quan trọng là:

| Chế độ listener | Hành vi |
| --- | --- |
| `AUTO` | **Spring listener container** gửi ack sau khi listener hoàn tất thành công. Khi listener ném lỗi, container quyết định reject/nack theo cấu hình và loại lỗi. Đây không phải AMQP `autoAck=true`. |
| `MANUAL` | Ứng dụng chủ động gọi `basicAck`, `basicNack` hoặc `basicReject` trên channel; phải bảo đảm mỗi delivery được xử lý xác nhận đúng cách. |
| `NONE` | RabbitMQ giao thông điệp với AMQP auto-ack; broker xem delivery đã được xác nhận khi giao, dù code nghiệp vụ có thể chưa xử lý xong. |

Ở chế độ `AUTO`, ví dụ listener trả về bình thường thì Spring gửi ack; nếu ném exception, thông điệp có thể bị requeue theo chính sách mặc định/đã cấu hình. Không nên để lỗi vĩnh viễn tạo vòng **requeue vô hạn**.

## 4. Ví dụ tối thiểu với Spring Boot

Ví dụ dưới đây dùng Java và `spring-boot-starter-amqp`. Cài RabbitMQ tại `localhost:5672` trước khi chạy ứng dụng; có thể dùng instance cục bộ với user dành cho môi trường phát triển. Các class minh họa đặt trong cùng package để sử dụng chung hằng số topology.

### 4.1. Khai báo dependency và kết nối

Nếu dùng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Trong `application.yml`:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
    listener:
      simple:
        acknowledge-mode: auto
~~~

Tài khoản `guest` chỉ thích hợp cho môi trường RabbitMQ cục bộ và thường bị giới hạn kết nối từ `localhost`. Môi trường triển khai thật nên sử dụng tài khoản, quyền truy cập và cấu hình kết nối riêng.

### 4.2. Khai báo exchange, queue và binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AmqpTopology {
    public static final String EXCHANGE = "orders.events";
    public static final String QUEUE = "orders.created.q";
    public static final String ROUTING_KEY = "order.created";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue ordersQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding ordersBinding(Queue ordersQueue, DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
            .to(ordersExchange)
            .with(ROUTING_KEY);
    }
}
~~~

Khi kết nối và khai báo thành công, Spring AMQP có thể khai báo các bean topology này với RabbitMQ thông qua cơ chế admin. Queue `orders.created.q` đã có binding tương ứng với routing key `order.created`.

### 4.3. Gửi message

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishCreated(String orderId) {
        rabbitTemplate.convertAndSend(
            AmqpTopology.EXCHANGE,
            AmqpTopology.ROUTING_KEY,
            orderId
        );
    }
}
~~~

Để phát sự kiện bằng HTTP khi thực hành:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderDemoController {
    private final OrderEventPublisher publisher;

    public OrderDemoController(OrderEventPublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping("/demo/orders/{orderId}")
    public ResponseEntity<String> publish(@PathVariable String orderId) {
        publisher.publishCreated(orderId);
        return ResponseEntity.accepted().body("Publish da duoc yeu cau: " + orderId);
    }
}
~~~

Phản hồi HTTP `202 Accepted` ở đây chỉ báo ứng dụng đã thực hiện lời gọi gửi trong ví dụ, **không hứa** consumer đã xử lý xong. API thật phải thiết kế cách phản ánh trạng thái publish phù hợp với mức bảo đảm mà hệ thống cung cấp.

### 4.4. Nhận và xử lý message

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @RabbitListener(queues = AmqpTopology.QUEUE)
    public void handle(String orderId) {
        // Ví dụ đơn giản; thực tế cần xử lý nghiệp vụ có tính idempotent.
        System.out.println("Da xu ly su kien tao don: " + orderId);
    }
}
~~~

Thử gọi:

~~~bash
curl -X POST http://localhost:8080/demo/orders/ORD-1001
~~~

Quan sát dòng log từ listener. Với `acknowledge-mode: auto`, khi method `handle` kết thúc bình thường, container gửi consumer ack. Nếu thêm `throw new IllegalStateException("fail");` vào listener, hãy theo dõi message có bị giao lại hay không; hành vi cụ thể phụ thuộc chính sách retry/requeue hiện hành.

## 5. Hai tầng xác nhận: publisher confirm và consumer ack

Một ứng dụng cần phân biệt rõ loại tín hiệu mình đang nhìn thấy:

| Tín hiệu | Ai gửi → ai nhận? | Chứng minh điều gì? | Không chứng minh điều gì? |
| --- | --- | --- | --- |
| `convertAndSend` trả về | Code gọi trở về producer | Lời gọi publish đã kết thúc phía client mà không ném exception đồng bộ. | Broker đã chấp nhận/định tuyến, consumer đã xử lý. |
| **Publisher confirm ACK** | Broker → producer | Broker đã xử lý publish và xác nhận theo ngữ nghĩa của queue/broker. | Listener đã hoàn tất nghiệp vụ; message chắc chắn đi tới queue khi không kiểm tra return. |
| **Publisher confirm NACK** | Broker → producer | Broker không thể xác nhận publish đó. | Consumer đã nhận hoặc đã xử lý. |
| **Returned message** | Broker → producer | Message không định tuyến được theo điều kiện `mandatory`. | Listener có chạy hay không, bởi message chưa vào queue đích mong muốn. |
| **Consumer ACK** | Consumer → broker | Consumer xác nhận delivery, broker có thể xóa delivery khỏi trạng thái chưa ack. | Publisher có cơ chế chống trùng lặp, hoặc side effect của consumer có bảo đảm đúng một lần. |
| **Consumer NACK/REJECT** | Consumer → broker | Delivery bị từ chối; broker xử lý tùy `requeue` và cấu hình DLX. | Message chắc chắn sẽ được retry thành công. |

### 5.1. Bật publisher confirms và returned messages

Ví dụ `application.yml` bổ sung:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Đoạn trên cần **gộp vào** cùng cây cấu hình `spring.rabbitmq` đã khai báo, không tạo hai block `spring` riêng trong một file. Khi publisher confirms được bật, producer có thể gắn `CorrelationData` để liên hệ confirm với message đã gửi:

~~~java
import org.springframework.amqp.rabbit.connection.CorrelationData;

CorrelationData data = new CorrelationData("evt-1001");
rabbitTemplate.convertAndSend(
    AmqpTopology.EXCHANGE,
    AmqpTopology.ROUTING_KEY,
    "ORD-1001",
    data
);

data.getFuture().whenComplete((confirm, error) -> {
    if (error != null) {
        // Không lấy được kết quả confirm: ghi nhận và đối soát.
        return;
    }
    if (confirm.isAck()) {
        // Broker xác nhận publish; vẫn cần kiểm tra returned message.
    } else {
        // Broker NACK: ghi nhận nguyên nhân confirm.getReason().
    }
});
~~~

Đây là đoạn minh họa đặt **trong method của bean đang có `rabbitTemplate`**. Trong luồng thật, hãy ghi log có `eventId`, theo dõi timeout hoặc trường hợp chưa nhận được confirm, đồng thời cấu hình `RabbitTemplate.ReturnsCallback` để xử lý message bị trả về. Với correlated confirms, thông tin returned message cũng có thể được gắn vào `CorrelationData`. **Không tự retry mọi trường hợp không nhận confirm bằng một bản ghi nghiệp vụ mới**: broker có thể đã nhận publish nhưng xác nhận bị thất lạc, dẫn đến phát lặp.

### 5.2. Khi nào cần ack thủ công?

Chế độ `MANUAL` có ích khi ứng dụng cần quyết định ack/nack sau một chuỗi thao tác đặc biệt. Ví dụ minh họa:

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;

@RabbitListener(queues = AmqpTopology.QUEUE, ackMode = "MANUAL")
public void handleManually(Message message, Channel channel) throws IOException {
    long deliveryTag = message.getMessageProperties().getDeliveryTag();
    try {
        processBusinessOperation(message);
        channel.basicAck(deliveryTag, false);
    } catch (TemporaryFailure ex) {
        channel.basicNack(deliveryTag, false, true);  // requeue
    } catch (PermanentFailure ex) {
        channel.basicReject(deliveryTag, false);     // không requeue
    }
}
~~~

`processBusinessOperation`, `TemporaryFailure` và `PermanentFailure` là tên minh họa, cần hiện thực theo nghiệp vụ. Trong ví dụ, `false` ở tham số `multiple` nghĩa là chỉ xác nhận **delivery tag hiện tại**, không xác nhận hàng loạt. Nếu reject với `requeue=false`, message chỉ đi vào dead-letter queue khi đã khai báo cơ chế dead-letter thích hợp; nếu không, nó có thể bị loại bỏ. Không được vừa ack vừa nack cùng một delivery, hay tiếp tục dùng delivery tag trên channel đã đóng.

Với bài toán thông thường, `AUTO` cộng retry, xử lý lỗi, dead-letter và idempotency có thể dễ vận hành hơn `MANUAL`. Việc xử lý lỗi ở consumer cần được thiết kế nhất quán với ack mode đã chọn.

## 6. Điều gì xảy ra nếu hệ thống lỗi giữa đường?

| Điểm lỗi | Hiện tượng có thể xảy ra | Cách xử lý phù hợp |
| --- | --- | --- |
| Producer lỗi trước khi publish | Chưa có thông điệp ở broker. | Ghi trạng thái và thử lại theo chính sách phù hợp. |
| Broker nhận publish nhưng producer mất confirm | Producer không biết publish có thành công hay không. | Đối soát, sử dụng `eventId` ổn định và consumer idempotent. |
| Sai exchange/routing key/binding | Publish có thể không vào queue mong muốn. | Kiểm tra topology; bật `mandatory` và xử lý returned message. |
| Consumer lỗi khi đang xử lý | Delivery chưa ack có thể bị requeue hoặc dead-letter. | Retry có giới hạn, phân loại lỗi tạm thời/vĩnh viễn. |
| Consumer commit DB xong nhưng mất kết nối trước ACK | Broker có thể giao lại chính event đó. | Lưu dấu `eventId` đã xử lý trong giao dịch nghiệp vụ. |
| Listener lỗi vĩnh viễn và liên tục requeue | Message bị lặp xử lý, tốn tài nguyên và chặn tiến độ. | Retry có backoff và giới hạn; đưa đến DLQ để điều tra. |

### Vì sao phải xử lý trùng lặp?

Giả sử listener đã trừ tồn kho trong database, nhưng kết nối RabbitMQ đứt trước khi `basic.ack` đến broker. Sau khi consumer kết nối lại, broker có thể **giao lại cùng message**. Nếu listener trừ tồn kho lần thứ hai, dữ liệu sẽ sai dù hệ thống message broker đang hoạt động đúng.

Biện pháp thực tế là cấp một `eventId` duy nhất, lưu dấu đã xử lý bằng ràng buộc unique và làm cho **ghi dấu + thay đổi nghiệp vụ** nằm trong cùng một giao dịch database khi có thể. Như vậy, lần giao lại có thể được nhận diện và bỏ qua một cách an toàn. Cơ chế giao nhận phổ biến vì thế là **at-least-once + idempotent consumer**, không nên giả định broker tự đảm bảo side effect nghiệp vụ đúng một lần.

### Khi vừa cập nhật DB vừa publish

Một tình huống khác là ứng dụng đã commit đơn hàng trong DB nhưng bị dừng trước khi publish event. Transaction của database không tự bao gồm việc publish RabbitMQ. Khi hai hành động phải đi cùng nhau về mặt nghiệp vụ, có thể dùng **transactional outbox**: cùng transaction DB lưu đơn hàng và một bản ghi sự kiện; một tiến trình khác publish outbox, theo dõi confirm rồi đánh dấu đã gửi. Cách này vẫn cần xử lý việc gửi lặp và consumer idempotent.

## 7. Quan sát luồng và tìm điểm nghẽn

Khi debug, hãy đối chiếu **message ID/event ID**, routing key, queue đích và các chỉ số:

- **Publish / confirm / return**: ứng dụng có publish không, broker có ACK/NACK không, có message bị return do định tuyến sai không?
- **Messages ready**: message còn chờ được giao, có thể do thiếu consumer hoặc consumer xử lý chậm.
- **Messages unacknowledged**: message đã giao nhưng chưa ack, có thể do listener đang chạy lâu hoặc prefetch/concurrency chưa phù hợp.
- **Consumer count, redelivered**: có consumer hoạt động không, có thông điệp bị giao lại nhiều lần không?
- **Retry, dead-letter queue**: lỗi được xử lý dứt điểm hay đang lặp vô hạn, DLQ có đang tích tụ không?

Ví dụ, nếu publish được confirm nhưng `messages_ready` tăng đều, kiểm tra listener có đang kết nối và tiêu thụ queue đúng tên không. Nếu `messages_unacknowledged` tăng, kiểm tra thời gian xử lý, timeout, I/O bị chặn và cấu hình prefetch. Nếu queue luôn trống nhưng producer nhận returned message, hãy kiểm tra exchange, binding và routing key trước.

RabbitMQ Management UI (nếu đã bật) giúp xem queue, ready/unacked, consumer và tốc độ vào/ra. Trong hệ thống thật, nên có dashboard, cảnh báo DLQ và log gắn `eventId` xuyên suốt producer/consumer.

## 8. Bài thực hành theo một thông điệp

Thực hiện lần lượt trong môi trường phát triển:

1. Khởi động RabbitMQ và ứng dụng Spring Boot; xác nhận exchange `orders.events`, queue `orders.created.q` và binding `order.created` đã xuất hiện.
2. Gọi `POST /demo/orders/ORD-1001`; kiểm tra listener nhận `ORD-1001` và message sau đó không còn ở trạng thái unacknowledged.
3. Dừng listener hoặc ứng dụng consumer (nếu tách producer/consumer), publish thêm message; quan sát `messages_ready` rồi khởi động lại consumer để thấy message được giao.
4. Cố ý làm listener ném exception; ghi nhận cơ chế requeue hiện có, sau đó cấu hình retry có giới hạn và dead-letter queue để tránh vòng lặp vô tận.
5. Thử routing key không có binding khi `mandatory=true` và bật returns callback; so sánh **returned message**, **publisher confirm** và **consumer ack**.
6. Mô phỏng xử lý cùng một `eventId` hai lần và bổ sung kiểm tra idempotency; kết quả nghiệp vụ cuối cùng phải giống như xử lý một lần.

**Câu hỏi tự kiểm tra:** Nếu một producer đã nhận publisher confirm ACK nhưng không thấy log listener, những nơi cần kiểm tra đầu tiên là gì? Câu trả lời nên đi từ returned message và topology đến queue ready/unacked, consumer connectivity và log lỗi; publisher confirm ACK riêng lẻ không đảm bảo listener đã chạy.

## 9. Ghi nhớ về chuỗi giao nhận

`RabbitTemplate → exchange → binding → queue → @RabbitListener → consumer ack` là luồng giao thông điệp cơ bản. Publisher confirm nằm ở phía **publish**; consumer ack nằm ở phía **xử lý delivery**; returned message phát hiện một lớp lỗi **định tuyến**. Để biến luồng này thành xử lý bất đồng bộ đáng tin cậy, ứng dụng còn cần chiến lược retry/dead-letter, idempotency, cấu hình durability phù hợp và khả năng quan sát từ đầu đến cuối.
