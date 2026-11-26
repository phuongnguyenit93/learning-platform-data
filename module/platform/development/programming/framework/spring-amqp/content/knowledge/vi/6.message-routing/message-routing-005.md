# Default exchange và định tuyến theo tên queue

## 1. Vấn đề: gửi đến queue mà không khai báo exchange riêng

Trong một ứng dụng sử dụng **Spring AMQP** và RabbitMQ, producer thường gửi thông điệp thông qua `RabbitTemplate`, RabbitMQ dùng **exchange** và **binding** để quyết định queue đích, sau đó consumer xử lý bằng `@RabbitListener`. Với bài toán đơn giản, chẳng hạn một producer cần đưa lệnh xử lý hóa đơn vào đúng queue `billing.invoice.q`, có thể sử dụng **default exchange** thay vì phải tự tạo một direct exchange và binding.

Default exchange cho phép gửi thông điệp theo **tên queue**:

~~~java
rabbitTemplate.convertAndSend("billing.invoice.q", "INV-1001");
~~~

Trong cấu hình `RabbitTemplate` mặc định, câu lệnh trên publish vào exchange có tên rỗng (`""`), với **routing key là `billing.invoice.q`**. RabbitMQ chuyển thông điệp vào queue cùng tên nếu queue ấy đang tồn tại.

Điều này hữu ích khi bắt đầu học định tuyến, khi cần gửi trực tiếp vào một queue công việc đã biết, hoặc khi sử dụng một số cơ chế request/reply. Tuy nhiên, nó cũng tạo quan hệ phụ thuộc trực tiếp giữa producer và **tên queue**; khi một sự kiện phải phân phối cho nhiều nhóm consumer hoặc cần định tuyến linh hoạt, exchange do ứng dụng quản lý thường phù hợp hơn.

Sau bài này, người học có thể:

1. Giải thích default exchange là gì, vì sao tên exchange rỗng và binding nào xuất hiện tự động.
2. Dùng đúng overload `RabbitTemplate.convertAndSend(...)` để định tuyến theo tên queue.
3. Phân biệt kết quả **publish**, **định tuyến thành công** và **consumer đã xử lý/ack**.
4. Phát hiện lỗi queue không tồn tại bằng mandatory returns; hiểu vai trò của publisher confirms.
5. Quyết định lúc nào dùng default exchange và lúc nào chuyển sang direct, topic hoặc fanout exchange.

## 2. Default exchange thực chất là gì?

RabbitMQ cung cấp sẵn một **direct exchange mặc định** cho mỗi virtual host. Trong giao thức AMQP 0-9-1, exchange này có **tên là chuỗi rỗng `""`**; một số giao diện quản trị và API có thể hiển thị nó dưới tên **`amq.default`**.

Không cần khai báo exchange này bằng Spring hoặc qua RabbitMQ Management UI. RabbitMQ tự cung cấp nó như một phần hạ tầng định tuyến của virtual host.

### 2.1. Binding ngầm theo tên queue

Khi RabbitMQ tạo một queue, broker **tự động thiết lập một binding ngầm** từ default exchange đến queue đó với **routing key đúng bằng tên queue**. Ví dụ:

~~~text
Virtual host: /

Queue: billing.invoice.q
    ^ 
    | binding ngầm có routing key = "billing.invoice.q"
    |
Default exchange: ""
~~~

Nếu producer publish với:

~~~text
exchange   = ""
routingKey = "billing.invoice.q"
body       = "INV-1001"
~~~

RabbitMQ sẽ định tuyến thông điệp vào `billing.invoice.q`, miễn là queue ấy đang tồn tại và producer có quyền publish tương ứng.

**Không tạo `Binding` riêng tới default exchange:** binding nói trên được RabbitMQ duy trì tự động theo vòng đời queue. Default exchange không dùng như exchange do ứng dụng tự quản lý binding bằng các lệnh bind/unbind. Khi ứng dụng cần mapping routing key tùy ý, hãy khai báo exchange và binding riêng.

### 2.2. Những điểm phải phân biệt

| Khái niệm | Điều cần hiểu |
| --- | --- |
| **Default exchange** | Direct exchange có tên `""`; RabbitMQ tạo sẵn. |
| **Queue mặc định** | RabbitMQ **không** tạo một queue toàn cục để nhận mọi thông điệp gửi vào default exchange. Queue đích phải thực sự tồn tại. |
| **Routing key** | Là chuỗi do producer cung cấp; với default exchange, nó phải trùng **chính xác tên queue**. |
| **Binding ngầm** | RabbitMQ tự nối mỗi queue với default exchange theo tên queue; không cần bean `Binding`. |
| **`RabbitTemplate` mặc định** | Thường publish đến exchange `""` nếu chưa cấu hình một default exchange khác cho template. |
| **`@RabbitListener`** | Tiêu thụ từ **queue**; không nhận message trực tiếp từ exchange. |

Default exchange vẫn tuân theo ranh giới **virtual host**: queue `billing.invoice.q` trong vhost `/billing` không phải queue `billing.invoice.q` trong vhost `/`. Producer và consumer phải kết nối đúng vhost.

## 3. Luồng định tuyến khi dùng tên queue

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Producer / RabbitTemplate
    participant X as Default exchange ""
    participant Q as Queue billing.invoice.q
    participant C as @RabbitListener
    P->>X: basic.publish routingKey="billing.invoice.q"
    Note over X,Q: Binding ngầm: key = tên queue
    X->>Q: Enqueue message
    opt Publisher confirms được bật
        X-->>P: Broker xác nhận publish
    end
    Q->>C: Giao message
    C->>C: Xử lý nghiệp vụ
    C-->>Q: Consumer acknowledgment sau xử lý
~~~

Diễn giải từng giai đoạn:

1. Producer tạo payload, ví dụ mã hóa đơn `INV-1001`.
2. `RabbitTemplate` publish với exchange `""` và routing key `billing.invoice.q`.
3. Broker tra binding ngầm của default exchange; thấy queue trùng tên và đưa thông điệp vào queue.
4. RabbitMQ giao message cho một consumer của queue khi có điều kiện giao nhận phù hợp. Nếu chưa có consumer, message có thể nằm ở trạng thái **ready**.
5. Listener xử lý và gửi xác nhận theo cơ chế acknowledgment của container. Trong chế độ `AUTO` của Spring listener container, container gửi ack sau khi method thành công.

Sơ đồ minh họa đường thành công. Nếu queue không tồn tại, **không có binding đích** để định tuyến; nếu listener xử lý thất bại, thông điệp có thể bị reject, requeue hoặc dead-letter theo cấu hình. Producer nhận publisher confirm **không chứng minh** listener đã hoàn tất.

### 3.1. Routing key được so khớp như thế nào?

Default exchange thực hiện định tuyến trực tiếp theo tên queue, **không dùng wildcard**:

| Queue đã tồn tại | Routing key gửi tới default exchange | Kết quả |
| --- | --- | --- |
| `billing.invoice.q` | `billing.invoice.q` | Định tuyến vào queue. |
| `billing.invoice.q` | `billing.*.q` | Không khớp theo wildcard; không định tuyến vào queue trên. |
| `billing.invoice.q` | `Billing.invoice.q` | Không khớp do khác chữ hoa/chữ thường. |
| `billing.invoice.q` | `billing.invoice` | Không khớp; đây là tên khác. |
| `billing.invoice.q` và `audit.events.q` | `audit.events.q` | Định tuyến vào `audit.events.q`. |

Một publish vào default exchange với một routing key là tên queue cụ thể **không tự trở thành broadcast** đến các queue khác. Nếu muốn cùng một sự kiện đến cả queue xử lý hóa đơn lẫn queue ghi audit, dùng exchange có các binding thích hợp.

## 4. Triển khai bằng Spring Boot và Spring AMQP

Ví dụ sử dụng API quen thuộc của **RabbitMQ AMQP 0-9-1**: `RabbitTemplate`, `Queue` và `@RabbitListener`. Với Spring Boot 3.x, dependency thông dụng là `spring-boot-starter-amqp`; khi sử dụng dòng Boot khác, chọn starter RabbitMQ 0-9-1 theo tài liệu tương ứng với phiên bản dự án.

### 4.1. Dependency và kết nối

Với Gradle và Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
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
    virtual-host: /
~~~

Đây là cấu hình phục vụ thí nghiệm với RabbitMQ cục bộ; tài khoản `guest` mặc định thường chỉ cho kết nối từ loopback. Khi triển khai thực tế, dùng tài khoản/vhost/permission riêng và bảo vệ thông tin xác thực bằng cơ chế quản lý secret.

### 4.2. Chỉ khai báo queue, không khai báo exchange hay binding

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InvoiceQueueConfiguration {
    public static final String INVOICE_QUEUE = "billing.invoice.q";

    @Bean
    Queue invoiceQueue() {
        return QueueBuilder.durable(INVOICE_QUEUE).build();
    }
}
~~~

`QueueBuilder.durable(...)` tạo bean queue với `durable=true`, `exclusive=false` và `autoDelete=false`; queue không bị xóa chỉ vì listener tạm dừng. Trong cấu hình Spring Boot phù hợp, `RabbitAdmin` sẽ khai báo bean `Queue` này với RabbitMQ khi kết nối. **Binding ngầm đến default exchange do RabbitMQ tạo ra**, nên không cần:

~~~java
// KHÔNG CẦN làm điều này cho default exchange:
// @Bean Binding bindingToDefaultExchange() { ... }
~~~

Để bảo đảm queue tồn tại trước khi gửi, hãy kiểm tra cấu hình admin/permissions và kết quả khai báo. Nếu queue chưa được tạo mà producer gửi trước, việc đặt routing key đúng tên **không tự sinh queue**.

### 4.3. Producer: hai cách publish tương đương trong cấu hình mặc định

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class InvoicePublisher {
    private final RabbitTemplate rabbitTemplate;

    public InvoicePublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishInvoice(String invoiceId) {
        // Cách 1: chỉ truyền routing key và payload.
        // Đúng khi default exchange của RabbitTemplate là "".
        rabbitTemplate.convertAndSend(
                InvoiceQueueConfiguration.INVOICE_QUEUE,
                invoiceId
        );
    }

    public void publishInvoiceExplicitly(String invoiceId) {
        // Cách 2: chỉ rõ exchange rỗng để luôn chọn default exchange.
        rabbitTemplate.convertAndSend(
                "",
                InvoiceQueueConfiguration.INVOICE_QUEUE,
                invoiceId
        );
    }
}
~~~

| Lời gọi | Tham số thứ nhất | Hệ quả |
| --- | --- | --- |
| `convertAndSend(queueName, body)` | **Routing key** | Dùng exchange đã cấu hình làm *default exchange của `RabbitTemplate`*; mặc định ban đầu là `""`. |
| `convertAndSend("", queueName, body)` | **Exchange name** | Chỉ rõ RabbitMQ default exchange; tham số tiếp theo là routing key = tên queue. |
| `convertAndSend("orders.events", "order.created", body)` | **Exchange name** | Gửi qua exchange do ứng dụng khai báo, sau đó RabbitMQ dùng binding đã cấu hình. |

**Bẫy khi refactor:** Nếu sau này ứng dụng gọi `rabbitTemplate.setExchange("orders.events")` hoặc cấu hình `spring.rabbitmq.template.exchange`, overload **hai tham số** sẽ gửi vào `orders.events` thay vì default exchange. Vì vậy, nếu định tuyến theo tên queue là yêu cầu có chủ đích, cách gọi **ba tham số với `""`** làm ý đồ rõ ràng và ít phụ thuộc cấu hình bên ngoài hơn.

### 4.4. Consumer lắng nghe queue

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class InvoiceListener {

    @RabbitListener(queues = InvoiceQueueConfiguration.INVOICE_QUEUE)
    public void handleInvoice(String invoiceId) {
        // Ví dụ tối giản: trong thực tế cần idempotency và xử lý lỗi.
        System.out.println("Dang xu ly hoa don: " + invoiceId);
    }
}
~~~

Listener không cần biết producer sử dụng default exchange hay direct/topic exchange: nó chỉ đọc những message **đã vào queue `billing.invoice.q`**. Dùng một endpoint HTTP hoặc `ApplicationRunner` để gọi:

~~~java
invoicePublisher.publishInvoiceExplicitly("INV-1001");
~~~

Đoạn trên là lệnh minh họa **bên trong một method có biến `invoicePublisher` thuộc kiểu `InvoicePublisher`**. Nếu queue đã được khai báo và consumer đang chạy, log listener sẽ hiển thị `INV-1001`.

## 5. Nếu queue không tồn tại thì điều gì xảy ra?

Đây là phần dễ hiểu sai nhất về định tuyến theo tên queue.

Giả sử producer gọi:

~~~java
rabbitTemplate.convertAndSend("", "billing.queue.does.not.exist", "INV-404");
~~~

Tên routing key trông giống tên queue, nhưng RabbitMQ **không tự tạo queue** theo routing key. Khi không có queue/binding tương ứng, message **không định tuyến được** (*unroutable*).

### 5.1. Mặc định: message có thể bị bỏ

Với AMQP 0-9-1, nếu publish vào một exchange tồn tại mà không tìm thấy queue đích:

- Khi cờ `mandatory=false` và không có cấu hình xử lý thay thế phù hợp, broker có thể **loại bỏ** message mà producer không nhận `basic.return`.
- Khi cờ `mandatory=true`, broker dùng **`basic.return`** để trả về message không định tuyến được cho publisher; ứng dụng có thể bắt tín hiệu này qua `RabbitTemplate.ReturnsCallback`.
- Publisher confirm ACK, nếu được bật, có thể xác nhận broker đã xử lý lần publish **ngay cả khi message bị return**. Do đó **confirm ACK khác với xác nhận có queue đích**.

Không nên chỉ nhìn việc `convertAndSend(...)` chạy xong mà kết luận message đã nằm trong queue.

### 5.2. Bật publisher returns và publisher confirms

Ví dụ `application.yml` (bổ sung vào cùng block `spring.rabbitmq` ở trên):

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Đây là **phần cấu hình minh họa bổ sung**; khi chép vào ứng dụng, gộp các key với `spring.rabbitmq.host/port/...` đã khai báo, không tạo nhiều block `spring` trùng nhau trong cùng YAML.

Với các thuộc tính trên:

1. Producer publish với `mandatory=true`.
2. Nếu không có queue trùng routing key, RabbitMQ gửi **returned message** với thông tin reply code/reply text/exchange/routing key.
3. Nếu bật correlated publisher confirms, broker cũng gửi confirm ACK/NACK theo quy trình publisher confirm.
4. Ứng dụng phải theo dõi **cả return và confirm**, vì hai tín hiệu trả lời hai câu hỏi khác nhau.

Đăng ký callback khi khởi động Spring:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class RoutingReturnsObserver {
    private final RabbitTemplate rabbitTemplate;

    public RoutingReturnsObserver(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @PostConstruct
    void registerCallbacks() {
        rabbitTemplate.setReturnsCallback(returned -> {
            System.err.printf(
                "UNROUTABLE exchange='%s', routingKey='%s', reply=%d %s%n",
                returned.getExchange(),
                returned.getRoutingKey(),
                returned.getReplyCode(),
                returned.getReplyText()
            );
        });

        rabbitTemplate.setConfirmCallback((correlation, ack, cause) -> {
            System.out.printf(
                "PUBLISH_CONFIRM correlation=%s, ack=%s, cause=%s%n",
                correlation != null ? correlation.getId() : null,
                ack,
                cause
            );
        });
    }
}
~~~

`ReturnsCallback` và `ConfirmCallback` được gắn vào instance `RabbitTemplate` và nên được đăng ký **tập trung**, vì việc gắn lại có thể thay thế callback mà code khác đã đặt. Đoạn ví dụ dùng `System.out/err` để dễ quan sát; production nên dùng logging có `eventId` hoặc `correlationId`, metrics và cơ chế xử lý lỗi phù hợp.

Khi cần liên kết một publisher confirm với request cụ thể, gắn `CorrelationData`:

~~~java
import org.springframework.amqp.rabbit.connection.CorrelationData;

CorrelationData data = new CorrelationData("invoice-event-1001");
rabbitTemplate.convertAndSend(
        "",
        InvoiceQueueConfiguration.INVOICE_QUEUE,
        "INV-1001",
        data
);

data.getFuture().whenComplete((confirm, error) -> {
    if (error != null) {
        // Không nhận được kết quả xác nhận như mong đợi: cần đối soát.
        return;
    }
    if (!confirm.isAck()) {
        // Broker NACK: ghi nhận reason và quyết định xử lý.
    }
    // ACK ở đây KHÔNG chứng minh rằng listener đã xử lý xong.
});
~~~

Đoạn này minh họa code đặt **trong một method đã có biến `rabbitTemplate`**. Với mandatory returns và correlated confirms, có thể tra thông tin returned message được liên hệ với `CorrelationData` theo API của phiên bản Spring AMQP đang sử dụng. Trong thực tế, hãy quan tâm cả timeout, kết nối bị ngắt và khả năng confirm thất lạc. Retry publish không kiểm soát có thể gây gửi trùng; nên dùng event ID ổn định.

### 5.3. Phân biệt lỗi không định tuyến với queue không có consumer

| Trạng thái | Queue có tồn tại? | Default exchange có định tuyến được? | Điều quan sát |
| --- | --- | --- | --- |
| Queue đúng tên, listener đang chạy | Có | Có | Message thường được giao và xử lý nhanh. |
| Queue đúng tên, listener tắt | Có | **Có** | Message có thể ở trạng thái **ready** chờ consumer. |
| Queue chưa khai báo | Không | **Không** | Có thể có returned message khi `mandatory=true`. |
| Queue có ở **vhost khác** | Không có trong vhost của producer | **Không** trong vhost producer | Kiểm tra vhost và quyền truy cập; queue cùng tên ở nơi khác không giúp định tuyến. |
| Queue được tự tạo lại sau khi bị xóa | Có thể được tạo lại | Có sau khi tái khai báo | Queue mới có thể không còn message trước khi bị xóa. |

Message không được tiêu thụ ngay **không đồng nghĩa** định tuyến thất bại. Hãy nhìn queue ready, consumer count và returned message trước khi kết luận.

## 6. Default exchange và custom exchange: lựa chọn theo mục tiêu

Với **custom direct exchange**, producer publish bằng một *routing key nghiệp vụ*, ví dụ `invoice.created`, còn queue có tên độc lập `billing.invoice.q`:

~~~text
Producer
  exchange = "billing.events"
  routingKey = "invoice.created"
        |
        v
Custom direct exchange "billing.events"
        |
        | bindingKey = "invoice.created"
        v
Queue "billing.invoice.q"
~~~

Còn với **default exchange**:

~~~text
Producer
  exchange = ""
  routingKey = "billing.invoice.q"
        |
        v
Default direct exchange ""
        |
        | binding ngầm theo tên queue
        v
Queue "billing.invoice.q"
~~~

| Tiêu chí | Default exchange | Custom direct/topic/fanout exchange |
| --- | --- | --- |
| Phải khai báo exchange? | Không, broker có sẵn. | Thường có; ứng dụng quản lý khai báo. |
| Phải khai báo binding? | Không; broker tạo binding ngầm theo tên queue. | Có; ứng dụng chọn key/pattern hoặc fanout. |
| Routing key | **Tên queue chính xác**. | Khóa nghiệp vụ hoặc pattern tùy loại exchange. |
| Producer có cần biết tên queue? | **Có**. | Không nhất thiết; producer có thể chỉ biết event/routing key. |
| Phân phối cùng message đến nhiều queue | Không phải mục đích thiết kế; mỗi routing key trỏ đến queue có tên tương ứng. | Có thể với nhiều binding, topic pattern hoặc fanout. |
| Thay tên queue mà không sửa producer | Khó; phải sửa routing key của producer. | Có thể chỉ sửa binding/topology nếu giữ routing key. |
| Trường hợp phù hợp | Gửi trực tiếp đến một queue đã biết, tác vụ đơn giản, queue reply. | Event-driven, pub/sub, nhiều dịch vụ nhận, phân vùng định tuyến, topology cần thay đổi linh hoạt. |

### 6.1. Ví dụ định tuyến một sự kiện cho nhiều hệ thống

Sự kiện `invoice.created` cần được nhận bởi cả **dịch vụ gửi email** và **dịch vụ phân tích**. Nếu producer publish vào default exchange với routing key `email.invoice.q` thì chỉ queue có tên đó là đích trực tiếp; queue `analytics.invoice.q` không nhận được message đó chỉ vì “cùng quan tâm đến hóa đơn”.

Một custom exchange có thể hỗ trợ yêu cầu:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class InvoiceEventTopology {
    @Bean
    DirectExchange invoiceEvents() {
        return new DirectExchange("invoice.events", true, false);
    }

    @Bean
    Queue invoiceEmailQueue() {
        return new Queue("email.invoice.q", true);
    }

    @Bean
    Queue invoiceAnalyticsQueue() {
        return new Queue("analytics.invoice.q", true);
    }

    @Bean
    Binding emailInvoiceBinding(Queue invoiceEmailQueue, DirectExchange invoiceEvents) {
        return BindingBuilder.bind(invoiceEmailQueue)
                .to(invoiceEvents)
                .with("invoice.created");
    }

    @Bean
    Binding analyticsInvoiceBinding(
            Queue invoiceAnalyticsQueue,
            DirectExchange invoiceEvents) {
        return BindingBuilder.bind(invoiceAnalyticsQueue)
                .to(invoiceEvents)
                .with("invoice.created");
    }
}
~~~

Producer lúc này gửi:

~~~java
rabbitTemplate.convertAndSend(
        "invoice.events",
        "invoice.created",
        "INV-1001"
);
~~~

Một publish có thể được định tuyến đến **cả hai queue** vì cùng có binding key `invoice.created`. Phần này minh họa giới hạn của default exchange; không cần thay custom exchange nếu bài toán chỉ yêu cầu gửi trực tiếp đến một queue.

## 7. Các ngộ nhận thường gặp

### “Không khai báo exchange tức producer gửi thẳng vào queue?”

Theo mô hình AMQP 0-9-1, producer vẫn **publish vào một exchange**: ở đây là exchange có tên rỗng `""`. Exchange này thực hiện định tuyến dựa trên binding ngầm mà RabbitMQ tạo cho queue.

### “Không cần khai báo queue vì default exchange tự có sẵn?”

Sai. **Exchange có sẵn**; còn **queue phải tồn tại** do ứng dụng, công cụ quản trị hoặc thành phần khác tạo ra. Routing key là tên queue không tạo queue mới.

### “Có thể chọn key `invoice.created` rồi mong RabbitMQ tự tìm `billing.invoice.q`?”

Không. Với default exchange, key `invoice.created` chỉ khớp queue **có tên đúng là `invoice.created`**. Muốn định tuyến event key đến queue tên khác, dùng custom exchange và binding.

### “Tất cả `RabbitTemplate.convertAndSend(queue, body)` đều dùng default exchange?”

Không chắc. Overload hai tham số sử dụng exchange đã được cấu hình làm mặc định **cho instance `RabbitTemplate`**. Khi muốn chọn chắc RabbitMQ default exchange, truyền rõ tham số exchange là `""`.

### “Publisher confirm ACK đồng nghĩa listener đã xử lý xong?”

Không. Confirm phản ánh broker xử lý **publish**; consumer ack phản ánh **delivery** được xác nhận; nghiệp vụ cũng cần xử lý idempotency khi message bị giao lại.

### “Bật durable queue là đủ để không mất thông điệp?”

Không. Queue durability, message persistence, publisher confirms, loại queue, cấu hình replication và chính sách broker là những mảnh ghép khác nhau. Ngoài ra, message có thể không vào queue do sai routing key hoặc bị consumer xử lý lỗi.

## 8. Thực hành kiểm chứng đường đi của message

Chuẩn bị RabbitMQ có Management UI và một Spring Boot app với các class ở mục 4. Khi thực hành, dùng queue thử nghiệm riêng để tránh ảnh hưởng dữ liệu production.

| Bước | Hành động | Kết quả dự kiến |
| --- | --- | --- |
| 1 | Khởi động ứng dụng có bean `Queue("billing.invoice.q", ...)`. | RabbitMQ có queue `billing.invoice.q` và binding ngầm tới default exchange. |
| 2 | Gọi `publishInvoiceExplicitly("INV-1001")`. | `@RabbitListener` in mã hóa đơn; queue không giữ message sau khi được xử lý và ack thành công. |
| 3 | Tắt consumer nhưng giữ queue tồn tại, rồi publish `INV-1002`. | Message có thể ở trạng thái **ready**; khi consumer chạy lại, message được giao. |
| 4 | Bật mandatory returns và publish tới `missing.invoice.q` chưa tồn tại. | `ReturnsCallback` nhận thông báo unroutable; nếu bật confirms, kết quả confirm cần được đọc riêng. |
| 5 | Giữ queue `billing.invoice.q` nhưng publish với key `billing.*.q`. | Không định tuyến vào queue; default exchange không hỗ trợ wildcard. |
| 6 | Cấu hình `RabbitTemplate` dùng exchange khác, thử lần lượt overload hai tham số và ba tham số với `""`. | Nhìn thấy sự khác nhau giữa exchange mặc định của template và RabbitMQ default exchange. |
| 7 | Tạo hai queue và binding tới custom exchange ở mục 6.1, publish một sự kiện. | Hai consumer queue độc lập có thể nhận cùng sự kiện nếu bindings trùng key. |

### 8.1. Những chỉ số cần quan sát

- **Exchange**: publisher thực sự dùng exchange `""` hay một exchange khác?
- **Routing key**: có khớp tuyệt đối với tên queue trong đúng virtual host không?
- **Queue**: có tồn tại, được tự khai báo bởi `RabbitAdmin` hay do quy trình bên ngoài quản lý?
- **Messages ready/unacknowledged**: message đang chờ consumer hay đã được giao mà chưa ack?
- **Consumer count**: có listener đang kết nối, xử lý đúng queue không?
- **Publisher returns/confirms**: message có bị return vì không định tuyến được hay broker xác nhận publish?
- **Retry/dead-letter**: listener thất bại có requeue vô hạn hay message được xử lý theo chính sách lỗi?

Nếu queue có `ready > 0` nhưng không có consumer, cần khởi động/kiểm tra listener; không phải lỗi default exchange. Nếu queue không tồn tại và có returned message, cần kiểm tra bước khai báo queue, tên queue, vhost và quyền kết nối trước khi tăng retry.

## 9. Sử dụng default exchange trong hệ thống đáng tin cậy

Default exchange **đơn giản hóa định tuyến**, nhưng không thay thế các quyết định kiến trúc về giao nhận:

| Rủi ro | Biện pháp |
| --- | --- |
| Publish trước khi queue được khai báo | Khai báo topology trước, kiểm tra readiness; theo dõi mandatory returns và kết quả publish. |
| Producer và consumer dùng tên queue khác nhau | Quản lý tên queue bằng cấu hình/contract thống nhất; kiểm tra vhost; tránh string literal rải rác. |
| Queue đổi tên khiến producer mất đích | Lên kế hoạch migration hoặc chuyển sang custom exchange để tách tên routing khỏi tên queue. |
| Broker nhận publish nhưng producer mất kết nối trước confirm | Ghi event ID, đối soát trạng thái chưa rõ, cân nhắc retry có kiểm soát. |
| Listener xử lý DB rồi mất kết nối trước consumer ack | Broker có thể giao lại message; consumer phải **idempotent**. |
| Listener liên tục lỗi | Retry hữu hạn và backoff, dead-letter exchange/queue và giám sát DLQ. |
| Ghi DB thành công nhưng publish chưa thực hiện | Khi cần đảm bảo cả hai sự kiện, cân nhắc **transactional outbox**. |

Ví dụ, một dịch vụ xử lý thanh toán nhận lệnh từ queue `payments.capture.q` qua default exchange. Nếu việc ghi database thành công nhưng consumer ack bị thất lạc, RabbitMQ có thể giao lại cùng message. Dù routing đã đúng, dịch vụ vẫn phải dùng **event ID/payment request ID** để không ghi nhận thanh toán hai lần.

**Kết luận về mức bảo đảm:** Default exchange trả lời câu hỏi **“message sẽ đi vào queue tên nào?”**. Publisher confirm trả lời câu hỏi broker đã xử lý publish ra sao; consumer ack trả lời delivery đã được xác nhận chưa. Không cơ chế nào tự đảm bảo side effect nghiệp vụ chỉ được thực hiện đúng một lần.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Producer gọi `rabbitTemplate.convertAndSend("", "report.jobs.q", payload)`. Trong vhost hiện tại chỉ có queue `report.jobs.q`. Message đi đâu?

**Trả lời:** Default exchange dùng routing key `report.jobs.q`, khớp binding ngầm của queue cùng tên; message được định tuyến vào `report.jobs.q`.

**Câu 2.** Nếu trong broker chưa có queue `report.jobs.q` thì lệnh publish có tự tạo queue không?

**Trả lời:** Không. Queue phải được khai báo độc lập; bật mandatory returns để nhận thông tin không định tuyến được.

**Câu 3.** Vì sao `convertAndSend("report.jobs.q", payload)` đôi khi không gửi vào default exchange?

**Trả lời:** Vì instance `RabbitTemplate` có thể được cấu hình một exchange mặc định khác. Overload hai tham số dùng exchange của template.

**Câu 4.** Muốn producer phát sự kiện `report.generated` cho cả queue `email.report.q` và `audit.report.q` thì nên dùng default exchange không?

**Trả lời:** Nên khai báo custom exchange với binding phù hợp. Default exchange yêu cầu routing key bằng đúng tên queue, không dùng một event key để phân phối tự động tới nhiều queue có tên khác nhau.

**Câu 5.** Producer nhận publisher confirm ACK, nhưng listener không ghi log. Phải kiểm tra gì?

**Trả lời:** Kiểm tra có returned message không, queue có tồn tại không, exchange/routing key/vhost có đúng không, messages ready/unacknowledged, consumer count và lỗi listener. Confirm ACK không đồng nghĩa listener đã xử lý.

## 11. Tài liệu tham khảo

- [RabbitMQ — Exchanges](https://www.rabbitmq.com/docs/exchanges): default exchange, binding ngầm theo tên queue và các loại exchange.
- [RabbitMQ — Queues](https://www.rabbitmq.com/docs/queues): khai báo queue, virtual host, durability và vòng đời queue.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): khác biệt giữa publisher confirm và consumer ack.
- [Spring AMQP Reference — RabbitTemplate](https://docs.spring.io/spring-amqp/reference/amqp/sending-messages.html): publish message qua template, routing key, exchange và callback.
- [Spring AMQP Reference — Configuring the Broker](https://docs.spring.io/spring-amqp/reference/amqp/broker-configuration.html): khai báo queue, exchange và binding bằng Spring.

**Ghi nhớ:** Với RabbitMQ AMQP 0-9-1, **default exchange là exchange có tên rỗng `""`** và RabbitMQ tự tạo binding ngầm cho mỗi queue theo **tên queue**. `RabbitTemplate.convertAndSend("", queueName, payload)` gửi vào đúng queue đang tồn tại trong vhost. Khi hệ thống cần định tuyến theo sự kiện, phân phối cho nhiều queue hoặc thay đổi topology độc lập với producer, hãy sử dụng exchange và binding riêng, đồng thời duy trì publisher confirms, consumer acknowledgments, retry/dead-letter và idempotency để xử lý bất đồng bộ đáng tin cậy.
