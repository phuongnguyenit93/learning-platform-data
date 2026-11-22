# Spring AMQP và RabbitMQ trong bài toán dùng AMQP

## Mục tiêu

Sau bài này, bạn có thể chọn đúng protocol và Spring integration cho RabbitMQ; thiết kế exchange, queue và binding; gửi/nhận message bằng `RabbitTemplate` và `@RabbitListener`; cấu hình JSON, publisher confirms, consumer acknowledgements, retry và dead-letter exchange; đồng thời nhận biết giới hạn của giao nhận message trong hệ thống phân tán.

## 1. AMQP, RabbitMQ và Spring AMQP

**AMQP (Advanced Message Queuing Protocol)** là giao thức ở tầng ứng dụng cho hệ thống message-oriented middleware. Ứng dụng gửi message được gọi là producer/publisher; ứng dụng xử lý message là consumer; broker nhận, lưu và định tuyến message giữa hai phía.

**RabbitMQ** là message broker hỗ trợ nhiều giao thức, trong đó có AMQP 0-9-1 và AMQP 1.0. Broker và ứng dụng có thể chạy trên các máy khác nhau. Producer không cần biết consumer đang chạy ở đâu; producer chỉ cần gửi message tới broker theo topology đã khai báo.

**Spring AMQP** đưa các abstraction của Spring vào lập trình AMQP: dependency injection, template gửi/nhận, listener container, message converter, khai báo topology bằng bean và cơ chế phục hồi kết nối. Dự án có module nền `spring-amqp` và các module client triển khai giao thức.

Cần phân biệt ba thành phần:

- **Protocol:** định dạng và quy tắc giao tiếp trên mạng, ví dụ AMQP 0-9-1 hoặc AMQP 1.0.
- **Broker:** RabbitMQ nhận, lưu và route message.
- **Spring abstraction:** API Java giúp ứng dụng dùng broker qua template, admin và listener container.

Spring AMQP không phải là một message broker. Nó là thư viện phía ứng dụng để làm việc với broker.

## 2. Phân biệt AMQP 0-9-1 và AMQP 1.0

Hai giao thức có tên gần nhau nhưng là hai wire protocol khác nhau, không phải hai phiên bản có thể đổi qua lại chỉ bằng cấu hình port.

| Giao thức | Mô hình | Spring integration thường dùng |
|---|---|---|
| AMQP 0-9-1 | Exchange, routing key, binding, queue; consumer acknowledgement và publisher confirms theo mô hình RabbitMQ | `spring-rabbit`, `RabbitTemplate`, `RabbitAdmin`, `@RabbitListener` |
| AMQP 1.0 | Message, sender/receiver link, address, settlement và flow control theo mô hình AMQP 1.0 | `spring-amqp-client` hoặc `spring-rabbitmq-client` tùy broker và mục tiêu |

RabbitMQ 4.0 hỗ trợ cả AMQP 0-9-1 và AMQP 1.0. Hai giao thức có thể cùng dùng listener port mặc định 5672; client gửi protocol header để broker nhận biết giao thức muốn sử dụng. Việc hai client cùng kết nối tới một broker không làm cho client library của chúng tương thích lẫn nhau.

Các lựa chọn Spring hiện nay:

- **AMQP 0-9-1:** dùng `spring-rabbit`. Đây là con đường phổ biến của Spring Boot RabbitMQ starter, với `RabbitTemplate` và `@RabbitListener`.
- **AMQP 1.0 trên RabbitMQ:** Spring AMQP 4.0 bổ sung `spring-rabbitmq-client`, dựa trên RabbitMQ AMQP 1.0 Java client. API tiêu biểu là `RabbitAmqpTemplate`, `RabbitAmqpAdmin` và `RabbitAmqpListenerContainer`. Module này dành cho RabbitMQ, không phải client chung cho mọi broker AMQP 1.0.
- **AMQP 1.0 đa broker:** Spring AMQP 4.1 bổ sung `spring-amqp-client`, dựa trên Qpid ProtonJ2. Module này có thể làm việc với các peer AMQP 1.0, bao gồm RabbitMQ, ActiveMQ và các dịch vụ tương thích khác. API tiêu biểu là `AmqpClient`, `AmqpMessageListenerContainer` và `@AmqpListener`.

Nếu dự án đang dùng Spring AMQP 3.x, hãy kiểm tra dependency và tài liệu đúng nhánh trước khi sao chép ví dụ của 4.x. Spring AMQP 4.x yêu cầu nền Spring Framework 7; không nâng riêng một module mà bỏ qua compatibility của Spring Boot, Spring Framework và Java.

## 3. Mô hình AMQP 0-9-1: exchange, routing key, binding và queue

Trong AMQP 0-9-1, producer publish message tới **exchange**. Exchange dùng loại exchange và các **binding** để quyết định message sẽ được route tới queue nào. Consumer đăng ký nhận message từ queue.

<escape>Producer → Exchange → Binding → Queue → Consumer</escape>

Các thành phần:

- **Exchange:** điểm nhận message từ producer và thực hiện định tuyến.
- **Routing key:** chuỗi producer gửi kèm để exchange so khớp với binding.
- **Binding:** quy tắc nối exchange với queue, có thể kèm routing key hoặc header.
- **Queue:** nơi broker lưu message để consumer nhận.
- **Virtual host (vhost):** vùng namespace và phân quyền riêng cho exchange, queue, binding và user.

### Bốn loại exchange cơ bản

| Exchange | Cách route | Ví dụ sử dụng |
|---|---|---|
| Direct | Routing key phải khớp chính xác binding key | Route lệnh `invoice.create` tới queue xử lý hóa đơn |
| Topic | Routing key khớp pattern; `*` là đúng một từ, `#` là không hoặc nhiều từ | Chọn các nhóm event như `order.created`, `order.cancelled` |
| Fanout | Gửi bản sao tới mọi queue được bind; bỏ qua routing key | Broadcast cache invalidation hoặc cập nhật cấu hình |
| Headers | So khớp message headers theo các binding arguments | Route theo nhiều thuộc tính metadata thay vì routing key |

Ví dụ Topic exchange:
- Binding `order.*` khớp `order.created` hoặc `order.cancelled`.
- Binding `order.#` khớp `order.created`, `order.payment.failed` hoặc `order.item.added`.
- `*` khớp đúng một đoạn giữa hai dấu chấm; `#` khớp không hoặc nhiều đoạn.

RabbitMQ có **default exchange** là direct exchange không tên (tên rỗng). Mỗi queue được tự động bind vào default exchange với routing key bằng tên queue. Vì vậy, gửi `convertAndSend("billing.orders", event)` thực chất dùng default exchange và queue name làm routing key.

### Durable, exclusive và auto-delete

Queue và exchange có thuộc tính vòng đời:

- **Durable:** topology tồn tại sau broker restart.
- **Exclusive:** queue chỉ gắn với connection sở hữu và bị xóa khi connection đó đóng.
- **Auto-delete:** queue có thể bị xóa khi consumer cuối cùng ngừng đăng ký sau khi queue từng có consumer.

Durable queue và persistent message là hai việc khác nhau. Queue durable không tự biến mọi message thành persistent; producer cần đặt delivery mode phù hợp. Với workload quan trọng, còn phải chọn queue type, replication, broker storage và publisher confirms.

## 4. Spring AMQP 0-9-1: các abstraction chính

Với Spring AMQP và RabbitMQ 0-9-1, các class quan trọng gồm:

| Thành phần | Vai trò |
|---|---|
| `ConnectionFactory` / `CachingConnectionFactory` | Quản lý connection và tái sử dụng channel |
| `AmqpTemplate` | Interface gửi/nhận message |
| `RabbitTemplate` | Implementation dùng RabbitMQ Java client |
| `AmqpAdmin` | Interface khai báo/xóa exchange, queue và binding |
| `RabbitAdmin` | Quản lý topology trên RabbitMQ |
| `@RabbitListener` | Đánh dấu method xử lý message bất đồng bộ |
| `RabbitListenerContainerFactory` | Tạo và cấu hình listener container |
| `MessageConverter` | Chuyển đổi object Java và AMQP message |

`RabbitTemplate` là API thường dùng để publish message. `@RabbitListener` là API thường dùng để consume message. Listener container quản lý consumer, concurrency, acknowledgement và vòng đời kết nối phía sau.

Với Spring Boot, dependency phổ biến cho AMQP 0-9-1 là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Để Boot quản lý phiên bản dependency bằng BOM, không tự chọn version của Spring AMQP và RabbitMQ client trừ khi có lý do tương thích cụ thể.

## 5. Kết nối RabbitMQ bằng Spring Boot

Ví dụ cấu hình `application.yml`:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: app
    password: ${RABBITMQ_PASSWORD}
    virtual-host: /orders
    connection-timeout: 5s
~~~

Các giá trị cần khớp với broker:
- Host/port là địa chỉ broker.
- Username/password phải có quyền truy cập vhost.
- Virtual host phân tách topology và quyền truy cập.
- Connection timeout giới hạn thời gian chờ khi tạo kết nối.

Không commit password thật vào repository. Production nên dùng secret manager hoặc secret injection. Khi dùng TLS, cấu hình SSL theo Spring Boot/RabbitMQ và xác minh chứng chỉ broker; không tắt certificate verification để né lỗi kết nối.

Spring Boot thường tự cấu hình:
- RabbitMQ `ConnectionFactory`.
- `RabbitTemplate` / `AmqpTemplate`.
- `AmqpAdmin` / `RabbitAdmin`.
- Listener container factory mặc định cho `@RabbitListener`.

Nếu khai báo bean `Queue`, `Exchange` và `Binding`, RabbitAdmin có thể tự động khai báo topology lên broker. Nếu ứng dụng tạo listener với queue không tồn tại, listener có thể không khởi động được hoặc không nhận message cho tới khi queue được khai báo đúng.

## 6. Khai báo topology bằng Java configuration

Ví dụ một luồng event đơn giản: producer publish `order.created` tới Topic exchange; queue của bộ phận billing nhận event này.

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderAmqpTopology {

    @Bean
    TopicExchange ordersExchange() {
        return new TopicExchange("orders.events", true, false);
    }

    @Bean
    Queue billingQueue() {
        return QueueBuilder.durable("billing.orders").build();
    }

    @Bean
    Binding billingBinding(
            Queue billingQueue,
            TopicExchange ordersExchange) {

        return BindingBuilder.bind(billingQueue)
            .to(ordersExchange)
            .with("order.created");
    }
}
~~~

Đây là một topology tối giản. Ứng dụng cần kết nối tới RabbitMQ và có RabbitAdmin để các bean topology được khai báo. Khi một exchange hoặc queue đã tồn tại với thuộc tính không khớp, RabbitMQ có thể trả lỗi `PRECONDITION_FAILED`; không nên đổi thuộc tính queue đang dùng bằng cách chỉ sửa bean rồi restart ứng dụng.

Khi thay đổi queue type, durability, TTL hoặc dead-letter arguments, hãy có kế hoạch migration: tạo queue mới, chuyển binding/consumer, xử lý backlog, rồi mới ngừng queue cũ.

## 7. Gửi message bằng RabbitTemplate

Giả sử event là một record Java:

~~~java
import java.time.Instant;

public record OrderCreated(
    String eventId,
    String orderId,
    Instant occurredAt
) {}
~~~

Producer dùng `RabbitTemplate`:

~~~java
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {

    private final RabbitTemplate rabbitTemplate;

    OrderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    void publish(OrderCreated event) {
        rabbitTemplate.convertAndSend(
            "orders.events",
            "order.created",
            event,
            message -> {
                message.getMessageProperties()
                    .setMessageId(event.eventId());
                message.getMessageProperties()
                    .setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                return message;
            }
        );
    }
}
~~~

Các tham số của `convertAndSend`:
1. Exchange: `orders.events`.
2. Routing key: `order.created`.
3. Payload: object `OrderCreated`.
4. MessagePostProcessor: bổ sung metadata trước khi publish.

Nếu không chỉ định exchange, template dùng default exchange. Nếu chỉ truyền queue name, queue name sẽ được dùng làm routing key qua default exchange.

### Message properties và headers

AMQP message có body và metadata. Các metadata thường dùng:

- `messageId`: định danh message.
- `correlationId`: liên kết request và response hoặc các message cùng luồng nghiệp vụ.
- `contentType`: kiểu nội dung, ví dụ `application/json`.
- `deliveryMode`: persistent hoặc non-persistent.
- `timestamp`: thời điểm tạo message.
- `replyTo`: địa chỉ nhận response trong request/reply.
- Headers: thông tin bổ sung như tenant, event type hoặc trace context.

Nên có event ID ổn định trong payload hoặc header để consumer chống xử lý trùng. Không đưa toàn bộ domain object phức tạp, entity JPA hoặc dữ liệu nhạy cảm vào message chỉ vì converter có thể serialize chúng.

## 8. MessageConverter: JSON thay vì Java serialization

Spring AMQP sử dụng `MessageConverter` để chuyển object thành byte array và khôi phục payload khi consumer nhận message.

Converter mặc định là `SimpleMessageConverter`, hỗ trợ text, byte array và Java serialized object. Java native serialization làm producer và consumer phụ thuộc chặt vào class Java, dễ gây lỗi khi class thay đổi và có rủi ro deserialization. Với hệ thống nhiều service hoặc nhiều ngôn ngữ, JSON hoặc schema-based format thường phù hợp hơn.

Với Spring AMQP 4.x, có thể dùng Jackson 3 converter:

~~~java
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class AmqpConverterConfiguration {

    @Bean
    MessageConverter amqpMessageConverter() {
        return new JacksonJsonMessageConverter();
    }
}
~~~

Spring Boot sẽ gắn bean `MessageConverter` vào template và listener factory được auto-configure. Nếu tự tạo `RabbitTemplate` hoặc listener factory riêng, phải cấu hình converter tương ứng trên instance đó.

Lưu ý theo phiên bản:
- Spring AMQP 4.x sử dụng converter dựa trên Jackson 3, tiêu biểu là `JacksonJsonMessageConverter`.
- Spring AMQP 3.x thường dùng `Jackson2JsonMessageConverter` dựa trên Jackson 2.
- Không copy import converter của 4.x vào dự án 3.x mà không kiểm tra dependency và Javadoc.

Type header có thể được dùng để ánh xạ payload về class Java. Với producer/consumer khác ngôn ngữ, nên thống nhất JSON schema và event type ổn định; không phụ thuộc tên package/class Java của producer. Cấu hình trusted packages/type mapping theo allowlist thay vì tin mọi class name đến từ message.

## 9. Nhận message bằng @RabbitListener

Listener khai báo queue cần consume:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
class BillingOrderListener {

    @RabbitListener(queues = "billing.orders")
    public void handle(OrderCreated event) {
        // Validate và xử lý nghiệp vụ billing.
    }
}
~~~

Khi message tới queue, listener container chuyển payload qua MessageConverter rồi gọi method. Method có thể nhận payload đã chuyển đổi, Spring AMQP `Message`, headers hoặc các tham số hỗ trợ khác.

Listener là bất đồng bộ: producer không chờ method `handle` chạy xong. Nếu cần phản hồi ngay, có thể dùng request/reply; nếu chỉ cần phát event, nên để consumer độc lập xử lý.

### Queue binding ngay trên annotation

Với topology đơn giản, `@RabbitListener` có thể khai báo queue, exchange và binding:

~~~java
@RabbitListener(bindings = @QueueBinding(
    value = @Queue(value = "inventory.orders", durable = "true"),
    exchange = @Exchange(value = "orders.events", type = "topic"),
    key = "order.created"
))
public void updateInventory(OrderCreated event) {
    // Cập nhật tồn kho.
}
~~~

Với topology có nhiều queue, DLX, TTL hoặc queue type, Java bean cấu hình thường rõ ràng hơn. Cần bảo đảm queue/exchange đã tồn tại hoặc có RabbitAdmin khai báo chúng.

## 10. Chọn routing topology theo bài toán

| Bài toán | Topology phù hợp | Giải thích |
|---|---|---|
| Một nhóm worker chia nhau xử lý task | Direct exchange hoặc default exchange + queue | Mỗi message trong queue được một consumer nhận thành công |
| Một event cần nhiều service cùng nhận | Fanout hoặc Topic exchange với queue riêng cho từng service | Mỗi queue có backlog và consumer độc lập |
| Route theo loại event | Topic exchange | Routing key như `order.created`, `order.cancelled` |
| Route theo chính xác một command | Direct exchange | Key như `invoice.generate` |
| Route theo nhiều metadata | Headers exchange | Binding so khớp header values |
| Gọi service và chờ kết quả | Request/reply | Dùng correlation ID và reply address, có timeout |
| Lưu log/event để đọc lại lâu dài | RabbitMQ Streams hoặc event store phù hợp | Stream có mô hình lưu và replay khác queue truyền thống |

Một điểm quan trọng: nếu hai service cùng bind một queue, chúng cạnh tranh nhận message. Nếu cần cả hai service đều nhận một bản event, mỗi service cần queue riêng được bind vào exchange.

## 11. Publisher confirms và returned messages

Publish là thao tác bất đồng bộ. Việc `RabbitTemplate.convertAndSend(...)` trả về không đồng nghĩa broker đã lưu message hoặc message đã route tới queue.

Có hai cơ chế khác nhau:

- **Publisher confirm:** broker xác nhận publish đã được broker chấp nhận hoặc từ chối.
- **Publisher return:** broker trả lại message khi publish với `mandatory=true` nhưng không route được tới queue nào.

Hai cơ chế này độc lập với consumer acknowledgement. Confirm không nói rằng consumer đã xử lý message; nó chỉ phản ánh trạng thái publish ở phía broker.

Cấu hình ví dụ trong Spring Boot:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Khi dùng correlated confirms, `CorrelationData` giúp liên kết confirm với message gửi đi:

~~~java
import org.springframework.amqp.rabbit.connection.CorrelationData;

CorrelationData correlation = new CorrelationData(event.eventId());

rabbitTemplate.convertAndSend(
    "orders.events",
    "order.created",
    event,
    correlation
);

correlation.getFuture().whenComplete((confirm, error) -> {
    if (error != null) {
        // Lỗi khi chờ kết quả confirm.
    }
    else if (!confirm.isAck()) {
        // Broker nack: xử lý publish chưa được chấp nhận.
    }
    else if (correlation.getReturn() != null) {
        // Broker trả message vì không route được.
    }
});
~~~

Trong production, hãy ghi nhận lỗi publish, quyết định retry hoặc lưu outbox để gửi lại. Không retry mù quáng khi kết quả publish chưa rõ: broker có thể đã nhận message nhưng connection mất trước khi client nhận confirm, khiến lần gửi lại tạo duplicate.

## 12. Consumer acknowledgement, prefetch và độ tin cậy

Khi RabbitMQ giao message cho consumer, broker cần biết khi nào message được xem là xử lý xong. Với AMQP 0-9-1 có ba chế độ thường gặp trong Spring AMQP:

| Spring AcknowledgeMode | Hành vi |
|---|---|
| `AUTO` | Listener container ack sau khi listener xử lý thành công; exception có thể dẫn đến reject/nack theo cấu hình |
| `MANUAL` | Code ứng dụng chủ động ack/nack sau khi xử lý |
| `NONE` | Broker coi message đã được acknowledge ngay khi giao; thông lượng cao nhưng có thể mất message nếu consumer chết |

Chú ý: `AUTO` của Spring listener container không đồng nghĩa với RabbitMQ `autoAck=true` ở giao thức. Spring AUTO thường đợi listener kết thúc thành công rồi mới acknowledge.

Với consumer cần độ tin cậy, thường dùng AUTO hoặc MANUAL thay vì NONE. Nếu process chết trước khi ack, message chưa được xác nhận có thể được broker giao lại. Vì vậy consumer cần idempotent.

**Prefetch** giới hạn số message chưa ack mà broker có thể giao trước cho một consumer/channel. Prefetch thấp giúp hạn chế lượng message đang nằm trong bộ nhớ và phân phối tải đều hơn; prefetch cao có thể tăng throughput nhưng làm tăng số message in-flight và nguy cơ dồn tải vào một consumer.

## 13. Retry, requeue và Dead Letter Exchange

Khi listener ném exception, ứng dụng cần quyết định có thử lại hay không:

- Lỗi tạm thời (database timeout, dịch vụ phụ thuộc tạm mất) có thể retry với backoff.
- Lỗi dữ liệu không hợp lệ hoặc không thể khắc phục không nên requeue vô hạn.
- Khi vượt số lần thử, message nên được reject và route tới dead-letter exchange (DLX) nếu cấu hình.
- DLQ lưu message lỗi để điều tra, sửa dữ liệu hoặc replay có kiểm soát.

Spring Boot có thể bật retry cho listener:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        retry:
          enabled: true
          initial-interval: 1s
          multiplier: 2.0
          max-interval: 10s
          max-attempts: 3
~~~

Retry của listener khác retry khi publish từ `RabbitTemplate`. Boot mặc định tắt listener retry. Khi retry đã hết, recoverer mặc định có thể reject mà không requeue; message chỉ vào DLQ nếu broker có dead-letter exchange được cấu hình. Nếu listener exception mà retry bị tắt và cấu hình vẫn requeue rejected message, delivery có thể lặp vô hạn.

Ví dụ topology DLX:

~~~java
@Bean
DirectExchange ordersDlx() {
    return new DirectExchange("orders.dlx");
}

@Bean
Queue billingDlq() {
    return QueueBuilder.durable("billing.orders.dlq").build();
}

@Bean
Binding billingDlqBinding(
        @org.springframework.beans.factory.annotation.Qualifier("billingDlq")
        Queue billingDlq,
        DirectExchange ordersDlx) {

    return BindingBuilder.bind(billingDlq)
        .to(ordersDlx)
        .with("billing.orders.failed");
}
~~~

Queue chính cần khai báo dead-letter exchange và routing key:

~~~java
@Bean
Queue billingQueue() {
    return QueueBuilder.durable("billing.orders")
        .deadLetterExchange("orders.dlx")
        .deadLetterRoutingKey("billing.orders.failed")
        .build();
}
~~~

Đây là cấu hình broker topology; hãy kiểm tra queue hiện tại có cùng arguments hay không trước khi triển khai. Nếu queue đã tồn tại với arguments khác, RabbitMQ có thể từ chối khai báo lại. DLQ không nên là nơi lưu message vô thời hạn mà không có người xử lý: cần alert, dashboard, quy trình kiểm tra và chính sách replay.

Requeue ngay lập tức khi mọi consumer đều đang gặp cùng một lỗi có thể tạo vòng lặp tốn CPU/network. Hãy dùng backoff, retry có giới hạn và DLQ.

## 14. Durable queue, persistent message và queue type

Ba khái niệm cần tách biệt:

1. **Durable exchange:** topology exchange sống qua broker restart.
2. **Durable queue:** queue sống qua broker restart.
3. **Persistent message:** message được gửi với delivery mode persistent.

Để tăng độ bền dữ liệu, thường cần cả durable queue và persistent message, cùng publisher confirms. Tuy nhiên, độ bền cuối cùng còn phụ thuộc queue type, replica, broker storage và cấu hình cluster.

RabbitMQ có nhiều queue type:
- **Classic queue:** queue truyền thống, phù hợp nhiều workload đơn giản.
- **Quorum queue:** queue replicated dựa trên Raft, hướng tới độ an toàn và tính sẵn sàng cao hơn trong cluster; có chi phí tài nguyên và đặc tính vận hành riêng.
- **Stream:** cấu trúc log bền vững, hỗ trợ đọc lại theo offset và nhiều consumer độc lập; khác queue tiêu thụ message truyền thống.

Không chọn queue type chỉ vì tên gọi. Hãy căn cứ yêu cầu mất dữ liệu tối đa, số replica, throughput, latency, replay và năng lực vận hành broker.

## 15. Retry và xử lý duplicate: đừng giả định exactly-once

AMQP acknowledgements và publisher confirms giúp ứng dụng biết một số trạng thái giao nhận, nhưng không tạo exactly-once cho nghiệp vụ end-to-end.

Ví dụ:
1. Consumer nhận `order.created`.
2. Consumer ghi đơn hàng vào database thành công.
3. Process dừng trước khi gửi ack.
4. Broker giao lại message.
5. Consumer chạy lần hai và có thể ghi đơn hàng trùng.

Cách bảo vệ:
- Mỗi event có `eventId` ổn định.
- Consumer lưu bảng inbox/processed-event với unique constraint.
- Việc đánh dấu event đã xử lý và cập nhật dữ liệu nghiệp vụ diễn ra trong cùng database transaction.
- Nếu event đã xử lý, consumer trả về thành công để ack mà không lặp side effect.
- Producer dùng transactional outbox để lưu event cùng transaction nghiệp vụ rồi một publisher riêng gửi message tới RabbitMQ.

Không nên chỉ dựa vào message ID do broker sinh để chống trùng nghiệp vụ. ID do producer tạo cần ổn định qua các lần retry và replay.

## 16. Transaction giữa database và RabbitMQ

Spring AMQP hỗ trợ channel transaction, nhưng transaction trên RabbitMQ channel và transaction JDBC/JPA là hai resource riêng.

- `RabbitTemplate.setChannelTransacted(true)` dùng channel transaction cho publish.
- Listener container có thể chạy với channel transacted để ack/reject gắn với commit/rollback.
- Transaction manager của database không tự động làm transaction RabbitMQ trở thành atomic.
- Muốn transaction phân tán cần XA/JTA và resource hỗ trợ; mô hình này có chi phí và giới hạn vận hành.

Với nhiều hệ thống nghiệp vụ, transactional outbox/inbox thường dễ vận hành hơn: commit database trước, sau đó publish outbox event; consumer deduplicate bằng inbox. Đây vẫn là mô hình at-least-once nhưng có kiểm soát duplicate.

## 17. Request/reply và RPC

RabbitMQ có thể hỗ trợ request/reply qua reply queue, correlation ID và reply-to address. Spring AMQP cung cấp `RabbitTemplate.convertSendAndReceive(...)` để triển khai request/reply.

Mẫu này hữu ích khi:
- Client thực sự cần kết quả của một thao tác từ service khác.
- Có timeout rõ ràng.
- Request và response có correlation ID.
- Server có thể xử lý request và gửi reply trong thời gian dự kiến.

Không nên dùng RPC qua message broker cho mọi lời gọi nội bộ. Request/reply vẫn tạo coupling về thời gian: caller phải chờ response và cần xử lý timeout, response bị mất, retry và duplicate. Nếu nghiệp vụ là event notification hoặc background work, publish event và xử lý bất đồng bộ thường phù hợp hơn.

## 18. AMQP 1.0 trong Spring AMQP 4.x

Khi hệ thống cần AMQP 1.0, hãy chọn đúng module thay vì dùng `RabbitTemplate` của AMQP 0-9-1 rồi giả định protocol sẽ tự đổi.

### Generic AMQP 1.0: spring-amqp-client

Spring AMQP 4.1 bổ sung dependency:

~~~xml
<dependency>
    <groupId>org.springframework.amqp</groupId>
    <artifactId>spring-amqp-client</artifactId>
</dependency>
~~~

Module này dựa trên Qpid ProtonJ2 và hỗ trợ peer AMQP 1.0 nói chung. API có `AmqpConnectionFactory`, `SingleAmqpConnectionFactory`, `AmqpClient`, `AmqpMessageListenerContainer` và annotation `@AmqpListener`.

Ví dụ khởi tạo client theo kiểu fluent API:

~~~java
@Bean
AmqpConnectionFactory amqpConnectionFactory() {
    return new SingleAmqpConnectionFactory();
}

@Bean
AmqpClient amqpClient(AmqpConnectionFactory connectionFactory) {
    return AmqpClient.builder(connectionFactory)
        .defaultToAddress("/queues/orders.in")
        .messageConverter(new JacksonJsonMessageConverter())
        .build();
}
~~~

Ví dụ gửi message:

~~~java
amqpClient.to("/queues/orders.in")
    .body(orderCreated)
    .messageId(orderCreated.eventId())
    .send();
~~~

Các thao tác gửi/nhận trả về `CompletableFuture`, vì vậy cần xử lý completion/error bất đồng bộ. Address `/queues/orders.in` là ví dụ quy ước destination của RabbitMQ; broker AMQP 1.0 khác có thể dùng address convention khác.

### AMQP 1.0 riêng cho RabbitMQ: spring-rabbitmq-client

Spring AMQP 4.0 bổ sung `spring-rabbitmq-client`, dựa trên RabbitMQ AMQP 1.0 Java client. API có `RabbitAmqpTemplate`, `RabbitAmqpAdmin` và `RabbitAmqpListenerContainer`. Module này dành cho RabbitMQ, không phải client chung cho mọi AMQP 1.0 broker.

Nếu dự án dùng AMQP 0-9-1, tiếp tục dùng `spring-rabbit`, `RabbitTemplate` và `@RabbitListener`. Nếu dự án cần interoperability AMQP 1.0 với nhiều broker, xem xét `spring-amqp-client`. Nếu cần AMQP 1.0 với API đặc thù RabbitMQ, cân nhắc `spring-rabbitmq-client`.

## 19. Chọn RabbitMQ queue hay Stream?

Queue và RabbitMQ Stream giải quyết các nhu cầu khác nhau.

| Nhu cầu | Queue | Stream |
|---|---|---|
| Worker nhận task và xử lý một lần | Phù hợp | Có thể dùng nhưng thường không cần |
| Nhiều consumer cùng đọc một log event độc lập | Cần queue riêng cho từng consumer | Phù hợp |
| Xóa message sau khi consumer ack | Mô hình queue | Stream giữ log theo retention |
| Đọc lại dữ liệu từ offset cũ | Không phải mô hình chính | Hỗ trợ replay |
| Lưu event dài hạn theo retention | Cần thêm hệ thống lưu trữ | Phù hợp hơn |

RabbitMQ Stream dùng protocol/client riêng, không đồng nhất với AMQP queue. Spring Boot có `RabbitStreamTemplate` và cấu hình riêng cho RabbitMQ Streams. Không dùng thuật ngữ “AMQP stream” để gọi mọi queue hoặc mọi stream.

## 20. Kiểm thử ứng dụng Spring AMQP

Unit test có thể kiểm tra logic business handler bằng cách gọi trực tiếp service. Nhưng để xác minh routing, exchange, queue, ack, retry và DLQ, cần integration test với RabbitMQ thật.

Nên có các test sau:

1. **Topology:** kiểm tra exchange, queue và binding được khai báo với đúng tên, type, durability và routing key.
2. **Publish/consume:** gửi event qua `RabbitTemplate`, xác nhận listener nhận đúng payload.
3. **Routing:** publish nhiều routing key và xác nhận mỗi queue chỉ nhận loại event phù hợp.
4. **Publisher confirm:** xác minh broker ack/nack và xử lý returned message khi không có binding.
5. **Acknowledgement:** listener thành công thì message được ack; listener lỗi thì message được requeue hoặc reject theo cấu hình.
6. **Retry/DLQ:** tạo lỗi có chủ đích, xác nhận số lần retry và message xuất hiện ở DLQ khi hết lượt.
7. **Idempotency:** gửi cùng event ID nhiều lần và xác nhận side effect chỉ xảy ra một lần.
8. **Broker restart:** xác minh durable queue/persistent message theo đúng loại queue và storage config.
9. **Protocol compatibility:** nếu dùng AMQP 1.0, test với client và broker đúng protocol, không thay bằng test AMQP 0-9-1.

Testcontainers có thể khởi chạy RabbitMQ container cho integration test. Dùng queue/exchange riêng cho từng test hoặc cleanup có kiểm soát để message từ test trước không ảnh hưởng kết quả. Không chỉ mock `RabbitTemplate` rồi kết luận broker routing đã đúng.

## 21. Quan sát và vận hành

Theo dõi cả application và broker:

- Publish rate, publish confirm latency, nack/return count.
- Queue depth, message ready, message unacknowledged.
- Consumer count, consumer utilization và prefetch.
- Redelivery count, DLQ depth và tuổi message trong DLQ.
- Connection/channel count, reconnect, broker alarms và disk/memory watermark.
- Listener processing latency và lỗi theo destination/event type.

Spring AMQP có tích hợp Micrometer metrics/Observation cho template và listener container. RabbitMQ Management plugin cung cấp dashboard/API về queue, exchange, connection, channel và consumer. Queue depth và broker health nên lấy từ broker metrics, không chỉ từ log ứng dụng.

Khi chạy production:
- Dùng vhost và user riêng cho từng ứng dụng hoặc miền nghiệp vụ.
- Cấp quyền configure/write/read tối thiểu.
- Dùng TLS cho kết nối qua mạng không tin cậy.
- Đặt connection name dễ nhận diện.
- Theo dõi channel cache, consumer concurrency và prefetch.
- Đặt alert cho DLQ, queue backlog, consumer không hoạt động và broker resource alarm.

## 22. Lỗi thường gặp

- **Nhầm AMQP 0-9-1 với AMQP 1.0:** hai giao thức khác nhau; phải chọn đúng client/module.
- **Cho rằng RabbitTemplate tự route tới queue theo tên:** template publish tới exchange; queue nhận message qua binding. Default exchange là trường hợp đặc biệt.
- **Chỉ tạo queue mà không bind exchange:** message có thể không route tới queue mong muốn.
- **Cho rằng durable queue làm mọi message persistent:** queue durability và delivery mode là hai thuộc tính riêng.
- **Không bật publisher confirms:** producer không biết broker đã chấp nhận message hay chưa.
- **Không bật mandatory/returns:** message không route có thể bị drop mà producer không nhận được return.
- **Nhầm publisher confirm với consumer ack:** một cái xác nhận phía broker nhận publish, cái còn lại xác nhận consumer xử lý delivery.
- **Dùng AUTOACK/NONE cho workload quan trọng:** broker có thể xem message đã xong trước khi consumer xử lý thành công.
- **Retry vô hạn:** poison message có thể tạo vòng lặp requeue và làm nghẽn queue.
- **Không chống duplicate:** broker redelivery có thể khiến side effect bị thực hiện nhiều lần.
- **Đổi queue arguments trực tiếp:** topology mismatch có thể khiến broker trả `PRECONDITION_FAILED`.
- **Dùng Java serialization giữa các service:** tạo coupling với class Java và rủi ro deserialization.
- **Đưa ID duy nhất vào metric tag:** cardinality tăng rất nhanh; dùng trace/log cho định danh message.
- **Dùng queue như event log có replay:** nếu cần đọc lại theo offset và retention, xem RabbitMQ Streams hoặc event store.

## 23. Checklist trước khi triển khai

- [ ] Đã xác định giao thức AMQP 0-9-1 hay AMQP 1.0.
- [ ] Đã chọn đúng module: `spring-rabbit`, `spring-rabbitmq-client` hoặc `spring-amqp-client`.
- [ ] Spring Boot, Spring Framework, Spring AMQP và Java version tương thích.
- [ ] Đã xác định exchange type, routing key, binding và queue cho từng consumer.
- [ ] Queue/exchange durability, message persistence và queue type phù hợp yêu cầu.
- [ ] Message schema có version, event ID và metadata cần thiết.
- [ ] Converter JSON phù hợp Jackson 2/3 theo Spring AMQP version.
- [ ] Publisher confirms và returned messages được xử lý khi cần độ tin cậy.
- [ ] Consumer acknowledgement, prefetch, retry và DLQ có cấu hình rõ ràng.
- [ ] Consumer có idempotency/inbox để xử lý duplicate.
- [ ] Database + publish được thiết kế bằng outbox hoặc transaction phù hợp.
- [ ] Có integration test với broker thật và test broker restart khi cần.
- [ ] Có metric/alert cho backlog, DLQ, confirm, consumer và broker health.
- [ ] Credentials, vhost, permissions và TLS được quản lý an toàn.

## Tài liệu tham khảo

- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/amqp.html): abstraction, template, connection, converter, transaction và recovery.
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): starter, connection properties, RabbitTemplate, listener, retry và auto-configuration.
- [Spring AMQP — AMQP Abstractions](https://docs.spring.io/spring-amqp/reference/amqp/abstractions.html): Message, Exchange, Queue và Binding.
- [Spring AMQP — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): SimpleMessageConverter và Jackson JSON converter.
- [Spring AMQP — Sending Messages](https://docs.spring.io/spring-amqp/reference/amqp/sending-messages.html): RabbitTemplate, publisher confirms và returns.
- [Spring AMQP — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html): `@RabbitListener` và listener container.
- [Spring AMQP — Generic AMQP 1.0 Support](https://docs.spring.io/spring-amqp/reference/amqp10-client.html): `spring-amqp-client`, ProtonJ2, `AmqpClient` và `@AmqpListener`.
- [Spring AMQP — RabbitMQ AMQP 1.0 Support](https://docs.spring.io/spring-amqp/reference/rabbitmq-amqp-client.html): `spring-rabbitmq-client`, `RabbitAmqpTemplate` và listener container.
- [RabbitMQ — AMQP 0-9-1 Model Explained](https://www.rabbitmq.com/tutorials/amqp-concepts): exchange, queue, binding, routing và acknowledgement.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): delivery acknowledgement, publisher confirms, nack và prefetch.
- [RabbitMQ — Exchanges](https://www.rabbitmq.com/docs/exchanges): loại exchange và định tuyến.
- [RabbitMQ — Spring AMQP Tutorial](https://www.rabbitmq.com/tutorials/tutorial-one-spring-amqp): ví dụ producer/consumer với Spring AMQP và AMQP 0-9-1.
