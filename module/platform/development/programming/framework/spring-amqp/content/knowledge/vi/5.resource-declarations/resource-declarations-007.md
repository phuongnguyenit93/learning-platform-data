# @QueueBinding, @Queue và @Exchange trên listener trong Spring AMQP

Trong RabbitMQ, **producer gửi message đến exchange**, exchange dùng **binding** để định tuyến message tới một hoặc nhiều **queue**, còn consumer đọc message từ queue. Một listener chỉ biết tên queue sẽ không tự giải thích queue được tạo từ đâu, thuộc exchange nào, hay binding sử dụng routing key gì. Spring AMQP cho phép đặt khai báo topology ngay tại phương thức `@RabbitListener` thông qua `@QueueBinding`, `@Queue` và `@Exchange`. Nhờ đó, nơi nhận message cũng có thể mô tả tài nguyên mà nó phụ thuộc.

Bài học thuộc chương **Khai báo tài nguyên** của module **SPRING_AMQP**. Đây là kiến thức nền khi tích hợp RabbitMQ qua `RabbitTemplate`, `@RabbitListener`, exchange, queue và binding; từ cấu hình định tuyến cơ bản đến thiết kế xác nhận giao nhận, retry, dead-letter và quan sát hệ thống xử lý bất đồng bộ đáng tin cậy.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

- Mô tả chính xác nhiệm vụ của `@Queue`, `@Exchange`, `@QueueBinding` và `@RabbitListener`.
- Khai báo queue, exchange và binding trực tiếp trên listener, bao gồm direct, topic, fanout và headers exchange.
- Phân biệt `queues`, `queuesToDeclare` và `bindings` để chọn cách khai báo phù hợp.
- Hiểu lifecycle của tài nguyên, vai trò của `RabbitAdmin` và những lỗi khi topology trong code mâu thuẫn với tài nguyên đã tồn tại trên broker.
- Thiết kế cấu hình hợp lý cho shared queue, queue tạm, dead-lettering và nhiều instance; kiểm tra luồng message thật thay vì chỉ kiểm tra code biên dịch.

## 2. Tách bốn khái niệm: queue, exchange, binding và listener

~~~mermaid
flowchart LR
    P["OrderPublisher<br/>RabbitTemplate"] -->|"exchange=orders.events<br/>routingKey=order.created"| E["Topic exchange<br/>orders.events"]
    E -->|"Binding key:<br/>order.created"| Q["Durable queue<br/>orders.created.q"]
    Q --> L["@RabbitListener<br/>handleOrderCreated"]
~~~

| Khái niệm | Vai trò trong RabbitMQ | Annotation liên quan |
|---|---|---|
| **Exchange** | Nhận message do producer publish và định tuyến theo kiểu exchange | `@Exchange` |
| **Queue** | Giữ các message đang chờ consumer xử lý | `@Queue` |
| **Binding** | Liên kết queue với exchange; có thể kèm routing key hoặc arguments | `@QueueBinding` |
| **Listener** | Container/method lấy delivery từ queue và chạy nghiệp vụ | `@RabbitListener` |

Điểm cốt lõi: **listener tiêu thụ từ queue, không tiêu thụ trực tiếp từ exchange**. `@QueueBinding` mô tả quan hệ queue–exchange, còn `@RabbitListener` chỉ định method nào xử lý delivery từ queue đó.

Lệnh publish có các tham số `exchange` và `routingKey`; chúng không phải queue name. Producer chỉ cần biết đường publish thích hợp, còn consumer và topology quyết định message được nhận ở đâu.

## 3. Ví dụ đầy đủ: khai báo ngay trên @RabbitListener

Giả sử checkout service phát sự kiện `OrderCreated` đến topic exchange `orders.events` với routing key `order.created`. Một worker cần nhận event này qua queue bền vững `orders.created.q`.

~~~java
import org.springframework.amqp.core.ExchangeTypes;
import org.springframework.amqp.rabbit.annotation.Exchange;
import org.springframework.amqp.rabbit.annotation.Queue;
import org.springframework.amqp.rabbit.annotation.QueueBinding;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedConsumer {

    @RabbitListener(
        bindings = @QueueBinding(
            value = @Queue(
                value = "orders.created.q",
                durable = "true"
            ),
            exchange = @Exchange(
                value = "orders.events",
                type = ExchangeTypes.TOPIC,
                durable = "true"
            ),
            key = "order.created"
        )
    )
    public void handleOrderCreated(String payload) {
        System.out.println("Received: " + payload);
    }
}
~~~

Các phần quan trọng của annotation lồng nhau:

1. `@Queue(value = "orders.created.q", durable = "true")`: mô tả **queue có tên cố định**, kỳ vọng tồn tại qua vòng đời ứng dụng và broker restart theo khả năng lưu trữ của broker.
2. `@Exchange(value = "orders.events", type = ExchangeTypes.TOPIC, durable = "true")`: mô tả **topic exchange** và thuộc tính bền vững.
3. `@QueueBinding(..., key = "order.created")`: liên kết queue với exchange qua **binding key** `order.created`.
4. `@RabbitListener(bindings = ...)`: đăng ký một listener container nhận message từ queue được khai báo.

Nhờ container và converter thích hợp, phương thức listener có thể nhận `String`, một POJO hoặc `Message`. Ở ví dụ này, publisher có thể gửi một chuỗi bằng `RabbitTemplate.convertAndSend`; việc nhận JSON thành POJO cần cấu hình message converter tương ứng, không do `@QueueBinding` quyết định.

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final RabbitTemplate rabbitTemplate;

    public OrderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishCreated(String orderId) {
        rabbitTemplate.convertAndSend(
            "orders.events",
            "order.created",
            "OrderCreated:" + orderId
        );
    }
}
~~~

Nếu exchange, queue và binding đã được khai báo thành công vào **cùng virtual host**, message ở ví dụ producer sẽ đến queue `orders.created.q`. Nếu thiếu binding hoặc chọn routing key không khớp, method listener sẽ không nhận được message đó.

## 4. Từng annotation cấu hình điều gì?

### 4.1. @Queue: tên, độ bền, exclusivity và thời điểm xóa

Các tham số thường gặp:

| Thuộc tính | Ví dụ | Diễn giải |
|---|---|---|
| `value` | `"orders.created.q"` | Tên queue; nên cố định với queue nghiệp vụ cần theo dõi |
| `durable` | `"true"` | Broker giữ định nghĩa queue qua restart, phụ thuộc cách broker vận hành |
| `exclusive` | `"false"` | Queue có cho phép các connection khác sử dụng hay chỉ connection khai báo |
| `autoDelete` | `"false"` | Cho broker tự xóa queue theo điều kiện auto-delete của RabbitMQ hay không |
| `arguments` | `@Argument(name = "...", value = "...")` | Các tham số nâng cao như TTL, DLX, maximum priority, queue type |

Các thuộc tính boolean của annotation được viết dưới dạng **chuỗi**, chẳng hạn `durable = "true"`. Đây là cú pháp annotation của Spring AMQP, không phải việc chuyển trực tiếp boolean Java. Nên khai báo tường minh những thuộc tính quan trọng cho vòng đời tài nguyên, tránh suy đoán mặc định khi đọc code hoặc đổi phiên bản.

**Durable queue không đồng nghĩa mọi message đều bền vững.** Độ bền message còn liên quan delivery mode, chính sách lưu trữ/replication của RabbitMQ, publisher confirm và lỗi hệ thống. Queue bền vững chỉ là một phần trong thiết kế độ tin cậy.

Nếu không cung cấp tên cho `@Queue`, ví dụ `value = @Queue`, Spring AMQP có thể tạo **anonymous queue** với tên được sinh tự động, non-durable, exclusive, auto-delete. Đây là lựa chọn hữu ích cho subscription tạm của mỗi instance; không thích hợp nếu yêu cầu tồn đọng message ổn định sau khi service ngắt kết nối.

### 4.2. @Exchange: tên và quy tắc routing

~~~java
@Exchange(
    value = "orders.events",
    type = ExchangeTypes.TOPIC,
    durable = "true",
    autoDelete = "false"
)
~~~

| Thuộc tính | Ý nghĩa |
|---|---|
| `value` | Tên exchange trên broker |
| `type` | Loại exchange: direct, topic, fanout, headers... |
| `durable` | Định nghĩa exchange có cần được giữ qua restart hay không |
| `autoDelete` | Cho phép broker xóa exchange khi đáp ứng điều kiện auto-delete |
| `arguments` | Các đối số mở rộng nếu exchange type/plugin hỗ trợ |

Một exchange **không lưu message để consumer đọc trực tiếp**. Nó quyết định định tuyến message đến queue. Đừng nhầm việc exchange durable với việc message đã được lưu bền vững.

### 4.3. @QueueBinding: nối hai tài nguyên

~~~java
@QueueBinding(
    value = @Queue(value = "orders.created.q", durable = "true"),
    exchange = @Exchange(
        value = "orders.events",
        type = ExchangeTypes.TOPIC
    ),
    key = "order.created"
)
~~~

Ở đây:

- `value` là mô tả **queue** trong binding.
- `exchange` là mô tả **exchange**.
- `key` là **binding key**, được RabbitMQ diễn giải tùy theo loại exchange.
- `arguments` (nếu dùng) là các tham số của **binding**, khác với `arguments` nằm trong `@Queue` hoặc `@Exchange`.

Các annotation này mô tả tài nguyên RabbitMQ. Chúng không đảm nhận xử lý lỗi nghiệp vụ, acknowledgement hay retry của listener.

## 5. @RabbitListener: queues, queuesToDeclare hay bindings?

Spring AMQP cung cấp ba cách phổ biến để chỉ định queue đích. Chọn theo ai sở hữu topology và mức khai báo cần thiết.

| Cách | Tác dụng | Phù hợp khi |
|---|---|---|
| `@RabbitListener(queues = "orders.created.q")` | Listener **tham chiếu queue có tên**; bản thân biểu thức này không khai báo queue/exchange/binding | Queue được khai báo trước bởi `@Bean`, hạ tầng hoặc service khác |
| `@RabbitListener(queuesToDeclare = @Queue(...))` | Cung cấp định nghĩa queue để đăng ký khai báo | Chỉ cần queue hoặc publish qua default exchange |
| `@RabbitListener(bindings = @QueueBinding(...))` | Khai báo trọn quan hệ queue, exchange và binding trong annotation | Listener sở hữu hoặc công bố rõ tuyến message của mình |

Ví dụ nhận từ queue đã có:

~~~java
@RabbitListener(queues = "billing.payment.q")
public void processPayment(String body) {
    // Handle payment event.
}
~~~

Ví dụ khai báo queue và nhận qua default exchange:

~~~java
@RabbitListener(
    queuesToDeclare = @Queue(
        value = "notification.simple.q",
        durable = "true"
    )
)
public void receiveNotification(String body) {
    // Handle notification.
}
~~~

RabbitMQ có **default exchange** (tên rỗng, kiểu direct đặc biệt) tự có binding đến queue bằng chính tên queue. Vì vậy, với ví dụ `queuesToDeclare`, producer có thể publish qua exchange rỗng với routing key `notification.simple.q`, miễn là queue đã tồn tại. Nếu yêu cầu custom topic/fanout exchange, hãy khai báo binding riêng qua `@QueueBinding` hoặc cơ chế khác.

Không cần đồng thời cung cấp cả `queues`, `queuesToDeclare` và `bindings` cho một listener để “chắc chắn nhận được”; hãy chọn một chiến lược tương ứng với topology. Với những hệ thống dùng IaC hoặc resource provisioning độc lập, `queues` thường giúp tách rõ trách nhiệm khai báo khỏi trách nhiệm consume.

## 6. Định tuyến cho từng loại exchange

### 6.1. Direct exchange: khóa phải khớp

~~~java
@RabbitListener(bindings = @QueueBinding(
    value = @Queue(value = "payment.authorized.q", durable = "true"),
    exchange = @Exchange(
        value = "payments.direct",
        type = ExchangeTypes.DIRECT,
        durable = "true"
    ),
    key = "payment.authorized"
))
public void onAuthorized(String body) {
    // ...
}
~~~

Với **direct exchange**, message có routing key `payment.authorized` khớp với binding của queue này; `payment.failed` không khớp nếu không có binding tương ứng.

### 6.2. Topic exchange: hỗ trợ wildcard

~~~java
@RabbitListener(bindings = @QueueBinding(
    value = @Queue(value = "orders.audit.q", durable = "true"),
    exchange = @Exchange(
        value = "orders.events",
        type = ExchangeTypes.TOPIC,
        durable = "true"
    ),
    key = { "order.created", "order.cancelled", "shipment.#" }
))
public void auditOrderEvents(String body) {
    // ...
}
~~~

Trong **topic exchange**, `*` đại diện cho đúng một segment giữa các dấu chấm; `#` đại diện cho không hoặc nhiều segment. Với binding `shipment.#`, message `shipment.created`, `shipment.vn.delivered` và `shipment` đều có thể khớp. Hai key `order.created` và `order.cancelled` là hai binding tương ứng cho cùng queue.

Điểm cần nhớ: wildcard trong binding key có ý nghĩa đối với **topic exchange**; đừng kỳ vọng direct exchange sẽ tự xử lý wildcard theo topic semantics.

### 6.3. Fanout exchange: bỏ qua routing key

~~~java
@RabbitListener(bindings = @QueueBinding(
    value = @Queue,
    exchange = @Exchange(
        value = "alerts.broadcast",
        type = ExchangeTypes.FANOUT,
        durable = "true"
    )
))
public void receiveBroadcast(String body) {
    // ...
}
~~~

`@Queue` không có tên ở đây tạo một queue tạm phục vụ listener; mỗi instance có thể nhận queue riêng. **Fanout** sao chép định tuyến đến các queue đã binding mà không dùng routing key. Phù hợp cho subscriber tạm nhận thông báo broadcast khi đang chạy.

Nhưng nếu mỗi replica service đều tạo một queue tạm, **mỗi replica có thể xử lý cùng một sự kiện**. Điều này khác với các replica cùng nghe **một queue cố định**, nơi các delivery được phân phối giữa các consumer của queue đó. Nếu nghiệp vụ chỉ muốn xử lý một lần ở cấp nhóm consumer, hãy chọn shared queue phù hợp, không tạo anonymous queue cho từng replica.

### 6.4. Headers exchange: so khớp application headers

~~~java
import org.springframework.amqp.rabbit.annotation.Argument;

@RabbitListener(bindings = @QueueBinding(
    value = @Queue(value = "orders.vn.mobile.q", durable = "true"),
    exchange = @Exchange(
        value = "orders.by-header",
        type = ExchangeTypes.HEADERS,
        durable = "true"
    ),
    arguments = {
        @Argument(name = "x-match", value = "all"),
        @Argument(name = "region", value = "vn"),
        @Argument(name = "channel", value = "mobile")
    }
))
public void onVietnamMobileOrder(String body) {
    // ...
}
~~~

Ở **headers exchange**, `arguments` của `@QueueBinding` xác định điều kiện so khớp. `x-match = all` yêu cầu các điều kiện khai báo cùng khớp; `x-match = any` có nghĩa là chỉ cần một điều kiện phù hợp trong nhóm so khớp. `x-match` là đối số của binding, **không** phải header producer phải gắn vào message.

Producer có thể gửi:

~~~java
rabbitTemplate.convertAndSend(
    "orders.by-header",
    "",
    "OrderCreated:O-1001",
    message -> {
        message.getMessageProperties().setHeader("region", "vn");
        message.getMessageProperties().setHeader("channel", "mobile");
        return message;
    }
);
~~~

Trong headers exchange, routing key không tham gia điều kiện routing chuẩn; các header `region` và `channel` quyết định kết quả. Với direct/topic/fanout exchange, chỉ gắn hai header này **không tự tạo** routing tương ứng.

## 7. Vòng đời khai báo trên broker: annotation chỉ là mô tả

Annotation Java là **metadata của ứng dụng**. Để exchange, queue và binding thực sự tồn tại trên RabbitMQ, ứng dụng cần cơ chế khai báo phù hợp, thường là `RabbitAdmin` (một triển khai `AmqpAdmin`) do Spring Boot/Spring AMQP cấu hình và kết nối được đến broker.

~~~mermaid
sequenceDiagram
    participant Boot as Spring application
    participant Ann as @RabbitListener / annotations
    participant Admin as RabbitAdmin / declaration infrastructure
    participant Broker as RabbitMQ broker
    Boot->>Ann: Phát hiện listener
    Ann->>Admin: Đăng ký topology declarations
    Admin->>Broker: Declare exchange, queue, binding
    Broker-->>Admin: Thành công hoặc lỗi khai báo
    Boot->>Broker: Bắt đầu tiêu thụ từ queue
    Broker-->>Boot: Delivery khi có message
~~~

Trong dự án Spring Boot có `spring-boot-starter-amqp`, phần lớn cấu hình cơ bản có thể được auto-configure, nhưng khả năng **tự khai báo** còn phụ thuộc việc có `AmqpAdmin` phù hợp, thiết lập auto-declaration, connection đến broker và quyền của tài khoản. Nếu ứng dụng tắt khai báo động, chạy chế độ listener không khởi động, hoặc topology được quản lý bên ngoài, annotation không thể ép broker tự tạo tài nguyên.

Một số điều quan trọng khi vận hành:

1. Exchange, queue và binding thuộc **virtual host** cụ thể. Cùng tên ở hai virtual host là hai tài nguyên riêng.
2. Tài khoản ứng dụng cần quyền phù hợp để khai báo và sử dụng topology. Quyền publish/consume không mặc nhiên đồng nghĩa quyền cấu hình tài nguyên.
3. Khai báo tài nguyên thường có tính idempotent **khi các thuộc tính tương thích**. Khai báo lại tên queue đã tồn tại nhưng khác durability, exclusivity, auto-delete hoặc một số arguments có thể bị RabbitMQ từ chối.
4. Để nhiều replica cùng khai báo một topology, chúng phải dùng **cùng bộ thuộc tính**; nếu replica chạy các phiên bản cấu hình khác nhau, broker có thể trả lỗi tương đương `PRECONDITION_FAILED` (inequivalent argument).
5. Nếu queue bị xóa khi ứng dụng đang hoạt động, hành vi tái khai báo phụ thuộc cấu hình admin/container/recovery. Không nên dựa vào việc “cứ có annotation thì queue chắc chắn sẽ được hồi sinh ngay”.

### Vì sao queue đã có không đổi được chỉ bằng annotation?

Ví dụ queue `orders.created.q` đã được tạo với `durable = false`; bạn sửa code thành `durable = "true"` rồi restart. Broker có thể từ chối khai báo lại do định nghĩa queue **không tương thích**. Sửa source không tương đương một migration topology trên broker.

Đối với queue đang có message sản xuất, việc xóa/tạo lại có thể gây mất dữ liệu hoặc gián đoạn. Cần lập kế hoạch migrate tài nguyên và chuyển tải traffic/message; không thử “xóa queue cũ cho hết lỗi” trên môi trường thật.

## 8. Queue cố định và queue tạm: chọn theo yêu cầu nghiệp vụ

| Tiêu chí | Named durable queue | Anonymous temporary queue |
|---|---|---|
| Ví dụ `@Queue` | `@Queue(value = "orders.created.q", durable = "true")` | `@Queue` |
| Tên | Cố định theo hợp đồng topology | Thường được sinh tự động |
| Vòng đời | Phù hợp xử lý công việc ngay cả khi consumer tạm vắng | Phù hợp đăng ký nhận khi instance đang hoạt động |
| Nhiều replica cùng listen | Cạnh tranh consume từ **cùng queue** | Thường **mỗi instance có queue riêng** |
| Broadcast fanout | Mỗi nhóm subscriber nên có queue riêng ổn định nếu cần backlog | Mỗi instance có thể nhận một bản khi đang online |
| Trường hợp nên dùng | Order fulfillment, payment, notification task cần retry/backlog | Debug subscriber, session tạm, sự kiện không cần giữ khi offline |

Ví dụ: ba replica của `order-worker` cùng nghe queue `orders.created.q` giúp chia tải một luồng công việc. Ngược lại, nếu ba replica dùng `@Queue` vô danh gắn vào một fanout exchange, mỗi replica có thể nhận cùng sự kiện, phù hợp broadcast nhưng có nguy cơ xử lý nghiệp vụ lặp ngoài ý muốn.

Chú ý: Queue bền vững vẫn phụ thuộc cách publish message, cấu hình broker và cơ chế an toàn của ứng dụng. `durable = "true"` không tạo guarantee exactly-once.

## 9. @Argument: cấu hình TTL, dead-letter và binding theo headers

Annotation `@Argument` dùng để truyền arguments ở **ba cấp khác nhau**:

| Nơi khai báo | Ví dụ argument | Tác dụng |
|---|---|---|
| `@Queue(arguments = ...)` | `x-message-ttl`, `x-dead-letter-exchange` | Thuộc tính/chính sách của queue |
| `@Exchange(arguments = ...)` | Tham số mở rộng của exchange/plugin | Tham số của exchange |
| `@QueueBinding(arguments = ...)` | `x-match`, header `region` | Tham số điều kiện binding, nhất là headers exchange |

### Ví dụ queue có thời hạn lưu message và dead-letter exchange

~~~java
import org.springframework.amqp.rabbit.annotation.Argument;

@RabbitListener(bindings = @QueueBinding(
    value = @Queue(
        value = "orders.processing.q",
        durable = "true",
        arguments = {
            @Argument(
                name = "x-message-ttl",
                value = "60000",
                type = "java.lang.Integer"
            ),
            @Argument(
                name = "x-dead-letter-exchange",
                value = "orders.dlx"
            )
        }
    ),
    exchange = @Exchange(
        value = "orders.events",
        type = ExchangeTypes.TOPIC,
        durable = "true"
    ),
    key = "order.created"
))
public void handleOrder(String payload) {
    // ...
}
~~~

Các lưu ý không thể bỏ qua:

- `x-message-ttl = 60000` giới hạn tuổi message ở **queue này**, tính bằng mili giây. Đây không phải timeout của phương thức listener.
- `type = "java.lang.Integer"` giúp biểu diễn giá trị TTL theo kiểu số mà broker mong đợi. Nếu gửi TTL như chuỗi không đúng kiểu field-table, broker có thể từ chối hoặc không xử lý như dự định.
- `x-dead-letter-exchange = "orders.dlx"` chỉ **chỉ định đích dead-letter**. Muốn các message thực sự đến DLQ, cần có exchange `orders.dlx` và queue/binding tương ứng, cùng quyền truy cập cần thiết.
- Expired message, rejected/nacked message hay message vượt giới hạn queue có thể dead-letter theo quy tắc RabbitMQ và cấu hình thực tế. `@RabbitListener` không tự tạo retry delay, backoff hoặc bảo đảm các message lỗi đều vào DLQ.
- Nếu listener tiêu thụ message trước khi TTL hết hạn, TTL không “trì hoãn xử lý” message. Một queue dành cho **delayed retry thông qua TTL/DLX** thường **không nên đặt listener tiêu thụ trên chính retry queue**; topology retry là thiết kế riêng.

Với tham số vận hành có thể thay đổi, cân nhắc **RabbitMQ policies** thay vì hard-code mọi `x-argument` vào annotation. Có những thuộc tính queue phải quyết định khi tạo và không thể sửa bằng policy; cần kiểm tra tài liệu RabbitMQ đúng phiên bản. Thay đổi TTL/DLX trực tiếp trên queue đã tồn tại có thể gây xung đột khai báo.

## 10. Có cần đặt toàn bộ topology vào listener?

Không. Spring AMQP còn hỗ trợ Java `@Bean` cho `Queue`, `Exchange` và `Binding` hoặc quản lý tài nguyên RabbitMQ bằng công cụ hạ tầng riêng. Ví dụ:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderTopology {

    @Bean
    TopicExchange ordersExchange() {
        return new TopicExchange("orders.events", true, false);
    }

    @Bean
    Queue ordersCreatedQueue() {
        return QueueBuilder.durable("orders.created.q").build();
    }

    @Bean
    Binding ordersBinding(Queue ordersCreatedQueue,
                          TopicExchange ordersExchange) {
        return BindingBuilder.bind(ordersCreatedQueue)
                .to(ordersExchange)
                .with("order.created");
    }
}
~~~

Listener lúc này chỉ cần:

~~~java
@RabbitListener(queues = "orders.created.q")
public void handleOrderCreated(String body) {
    // ...
}
~~~

Hai hướng tiếp cận là:

- **Khai báo lồng trong listener:** ít mã cho bài học, module độc lập hoặc consumer tự sở hữu topology của mình; một chỗ cho thấy quan hệ queue–exchange–binding.
- **Khai báo bằng @Bean / IaC / quản trị broker:** dễ tập trung cấu hình topology, dùng chung cho nhiều listener/service, tách trách nhiệm giữa hạ tầng và code nghiệp vụ, kiểm soát migration.

Tránh tạo cùng một tài nguyên ở nhiều nơi với các định nghĩa mâu thuẫn. Nếu kết hợp annotation và `@Bean`, hãy thống nhất tên và mọi thuộc tính queue/exchange. Nếu topology được tạo sẵn bên ngoài, `@RabbitListener(queues = ...)` thường đủ để ứng dụng tiêu thụ.

## 11. Lỗi thực tế và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể gặp | Hướng kiểm tra |
|---|---|---|
| Listener không nhận message, producer không báo lỗi | Exchange/routing key/binding không khớp; message unroutable | Xem topology trong RabbitMQ Management UI; kiểm tra publish exchange và routing key; cân nhắc publisher returns/mandatory |
| Application startup lỗi `PRECONDITION_FAILED` | Queue/exchange cùng tên đã tồn tại với thuộc tính khác | So sánh durable, autoDelete, exclusive, type và arguments với broker thực tế |
| Queue không được tạo | Thiếu/disable `RabbitAdmin`, thiếu quyền configure, sai virtual host hoặc declaration bị lỗi | Xem auto-configuration, logs, quyền và connection settings |
| Fanout message được nhiều instance cùng xử lý | Mỗi instance tạo anonymous queue riêng | Dùng shared queue nếu muốn competing consumers; dùng queue riêng có chủ đích nếu muốn broadcast |
| Message vào queue nhưng consumer lỗi chuyển kiểu | Payload/MessageConverter không khớp, header kiểu dữ liệu sai | Kiểm tra converter, contentType, body thực tế và signature method |
| DLX đã khai báo nhưng không thấy DLQ nhận message | Chưa khai báo DLQ/binding hoặc DLX policy/quyền không phù hợp | Xác nhận cả topology dead-letter; xem broker logs và queue arguments |
| Đổi tham số queue trong code nhưng không có hiệu lực | Tài nguyên broker đã tồn tại hoặc bị từ chối khai báo lại | Đọc lỗi declare; xây migration thay vì giả định annotation cập nhật in-place |

### Một quy trình kiểm tra nhanh

1. Mở RabbitMQ Management UI đúng **virtual host** và tìm exchange/queue tương ứng.
2. Xác nhận exchange type, thuộc tính durable/autoDelete, queue arguments và binding keys.
3. Publish một message thử với exchange/routing key rõ ràng; kiểm tra queue có nhận message.
4. Theo dõi log listener, converter, acknowledgement và exception. Nếu message có trong queue nhưng không được xử lý, vấn đề không còn nằm ở routing đơn thuần.
5. Nếu message có thể bị unroutable, cấu hình publisher confirms/returns theo yêu cầu để phát hiện lỗi, thay vì dựa vào việc `convertAndSend` không ném exception.
6. Với retry/DLQ, xác nhận đường dead-letter và các điều kiện broker thực hiện dead-letter; đừng coi tên queue `retry` hoặc `dlq` là chức năng tự động.

## 12. Các điểm liên quan độ tin cậy và vận hành

Khai báo tài nguyên giúp message đến **đúng nơi**, nhưng tự nó không bảo đảm message được xử lý chính xác một lần:

| Mục tiêu | Cấu hình liên quan | Chú ý |
|---|---|---|
| Định tuyến đúng | Exchange type, binding key/arguments, publish routing key | Mismatched routing có thể làm message không đến queue |
| Tồn tại qua restart | Durable queue/exchange, persistent messages, cấu hình lưu trữ broker | Cần publisher confirms và bảo đảm khác tùy mức yêu cầu |
| Xác nhận xử lý | Listener container ack mode, consumer acknowledgement | Ack là chuyện delivery, không phải do `@QueueBinding` tự làm |
| Retry lỗi tạm thời | Retry interceptor/container, delayed retry topology hoặc cơ chế được thiết kế | Có thể gây trùng; cần idempotency |
| Dead-letter | DLX/DLQ, policy hoặc `x-dead-letter-exchange`, xử lý reject/nack | Broker phải có exchange, queue và binding đích phù hợp |
| Quan sát | Queue depth, unacked count, consumer count, publish returns, DLQ | Quan sát topology và luồng thực tế để phát hiện lỗi |

Tương tự, các transaction ở phía producer/consumer là một vấn đề khác với khai báo exchange/queue/binding; việc đặt `durable = "true"` không thay thế transaction hoặc acknowledgement.

## 13. Bài tập có đáp án gợi ý

### Bài tập 1 — Chọn cách khai báo

Một nền tảng đã có queue `invoice.tasks.q` được tạo bởi Terraform hoặc script RabbitMQ. Service chỉ cần consume queue đó. Nên dùng `queues`, `queuesToDeclare` hay `bindings`?

**Gợi ý:** `@RabbitListener(queues = "invoice.tasks.q")` để dùng queue có sẵn. Cần cấu hình quyền và xác minh queue tồn tại. Đừng tự khai báo lại resource nếu service không sở hữu topology.

### Bài tập 2 — Topic wildcard

Binding key là `order.*`. Xác định routing key nào khớp trong `order.created`, `order.vn.created`, `order` và `shipment.created`.

**Đáp án:** chỉ `order.created` khớp: `*` đại diện một segment. Nếu muốn tất cả dạng `order`, `order.created`, `order.vn.created`, có thể cân nhắc `order.#`.

### Bài tập 3 — Mỗi replica có queue riêng

Ba instance dùng `@Queue` vô danh trên `alerts.broadcast` (fanout) và đều ghi email khi có message. Vì sao người dùng có thể nhận ba email? Hãy sửa thiết kế để ba instance chia tải một luồng gửi email.

**Gợi ý:** Mỗi instance có queue khác nhau nên fanout định tuyến một bản tới mỗi queue. Chuyển sang **một queue có tên cố định** mà cả ba replica listen, đồng thời dùng cơ chế idempotency nghiệp vụ để chống xử lý trùng do redelivery.

### Bài tập 4 — Sửa durable queue bằng annotation

Queue `orders.created.q` tồn tại với `durable = false`. Bạn sửa annotation thành `durable = "true"` và gặp lỗi khai báo không tương thích. Có nên xóa queue ngay?

**Gợi ý:** Không xóa trực tiếp trên môi trường có dữ liệu. Kiểm tra thuộc tính broker, lượng message tồn, người dùng/producer/consumer, lên phương án migration queue mới và chuyển luồng có kiểm soát.

### Bài tập 5 — Đặt TTL cho retry

Một nhóm khai báo `orders.retry.q` có TTL 30 giây nhưng đặt listener trực tiếp lên chính queue này. Họ kỳ vọng message được xử lý sau 30 giây. Chỉ ra vấn đề và đề xuất sơ đồ đúng.

**Gợi ý:** Listener có thể lấy message ngay trước khi TTL hết. Đối với kiểu delayed retry dựa trên TTL/DLX, message cần nằm trong retry queue **không có consumer**, sau khi hết TTL được dead-letter trở lại exchange/queue xử lý chính. Đây là một cách thiết kế; cần kiểm tra khả năng broker và tránh retry vô hạn.

### Bài tập 6 — Headers exchange

Tạo binding `x-match=all`, `region=vn`, `channel=mobile`. Message A có hai header như vậy; message B chỉ có `region=vn`. Message nào được định tuyến?

**Đáp án:** A khớp, B không khớp. Với `x-match=any`, các điều kiện so khớp sẽ khác. Đừng dùng `key = "region.vn"` để thay thế header khi exchange là kiểu headers.

## 14. Checklist triển khai

Trước khi đưa `@RabbitListener(bindings = ...)` vào ứng dụng:

- [ ] Xác nhận queue name cố định hay anonymous phù hợp với quy mô và nhu cầu backlog.
- [ ] Chọn đúng exchange type và binding key/arguments; kiểm tra routing bằng message thực.
- [ ] Quy định rõ durable, autoDelete, exclusive và những queue arguments quan trọng.
- [ ] Kiểm tra `RabbitAdmin`/cơ chế declaration và quyền configure trong đúng virtual host.
- [ ] So khớp topology với tài nguyên đã tồn tại; lên migration nếu cần đổi thuộc tính không tương thích.
- [ ] Đảm bảo publisher dùng đúng exchange, routing key và payload/converter.
- [ ] Test nhiều consumer/replica để biết message chia tải hay broadcast.
- [ ] Nếu dùng DLX, khai báo và xác minh riêng exchange, DLQ, binding, quyền và chính sách retry.
- [ ] Kiểm tra kết quả với version Spring AMQP/RabbitMQ thực tế của dự án; quan sát queue depth, unacked và DLQ khi chạy.

**Ghi nhớ:** `@Queue` định nghĩa nơi giữ message, `@Exchange` định nghĩa nơi nhận publish để định tuyến, `@QueueBinding` gắn queue với exchange, còn `@RabbitListener` đăng ký consumer lấy message từ queue. Nắm rõ bốn vai trò này sẽ giúp bạn khai báo topology Spring AMQP minh bạch, tránh lỗi routing và xây nền tảng đúng cho acknowledgements, retry, dead-letter cùng các cơ chế vận hành đáng tin cậy.
