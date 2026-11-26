# Tách kết nối publisher khỏi consumer bằng cấu hình phù hợp

Trong một dịch vụ **Spring AMQP**, chúng ta có thể vừa dùng **RabbitTemplate** để publish sự kiện, vừa dùng **@RabbitListener** để nhận công việc từ RabbitMQ. Nếu hai vai trò cùng sử dụng một kết nối AMQP vật lý, những vấn đề ở chiều publish có thể ảnh hưởng đến chiều consume. Tình huống dễ thấy là RabbitMQ kích hoạt **resource alarm** khi thiếu bộ nhớ hoặc dung lượng đĩa: broker có thể chặn một kết nối đang publish, khiến các hoạt động khác trên cùng kết nối cũng bị ảnh hưởng.

Vì vậy, trong ứng dụng vừa gửi vừa nhận message, có thể cần **tách kết nối publisher khỏi consumer**. Đây là bài học của chương **Kết nối và channel**: hiểu cấp kết nối bị ảnh hưởng, dùng cách tách sẵn có trong **RabbitTemplate**, biết khi nào phải tạo hai **ConnectionFactory** riêng, và kiểm chứng hành vi thực tế qua RabbitMQ Management.

Sau bài này, bạn sẽ có thể:

1. Phân biệt **TCP/AMQP connection**, **channel**, **CachingConnectionFactory**, **RabbitTemplate** và **@RabbitListener**.
2. Giải thích vì sao broker **blocked connection** là một lý do tách publisher/consumer.
3. Chọn đúng cách cấu hình **setUsePublisherConnection(true)** hoặc hai ConnectionFactory độc lập.
4. Tránh những lỗi liên quan **RabbitAdmin**, publisher confirms/returns và transaction của listener.
5. Quan sát, điều chỉnh số lượng connection/channel và xác minh hai luồng thực sự dùng các kết nối khác nhau.

## 1. Cần hiểu rõ connection và channel trước khi tách

RabbitMQ sử dụng **AMQP connection** (thông thường qua một kết nối TCP) để trao đổi dữ liệu giữa ứng dụng và broker. Mỗi connection có thể mang **nhiều AMQP channel**, là những phiên làm việc logic dùng để publish, consume, ack hoặc khai báo exchange, queue và binding.

~~~mermaid
flowchart TD
    APP["Một ứng dụng Spring Boot"] --> CF["CachingConnectionFactory"]
    CF --> CONN["AMQP Connection / TCP"]
    CONN --> PCH["Channel publish<br/>RabbitTemplate"]
    CONN --> CCH["Channel consume<br/>@RabbitListener"]
    CONN --> ACH["Channel quản trị<br/>RabbitAdmin"]
    PCH --> R[("RabbitMQ broker")]
    CCH --> R
    ACH --> R
~~~

Ở mô hình này, việc producer và consumer có **channel khác nhau** vẫn chưa đồng nghĩa đã có **connection khác nhau**. Cả hai có thể cùng nằm trong một TCP connection và cùng chịu tác động nếu broker đánh dấu connection đó là blocked.

| Thành phần | Chức năng | Vòng đời thường gặp |
| --- | --- | --- |
| **ConnectionFactory** | Tạo hoặc cung cấp AMQP connection; trong Spring AMQP đây là interface của framework | Tồn tại lâu dài như bean ứng dụng |
| **CachingConnectionFactory** | Quản lý và tái sử dụng connection/channel | Thường dùng chế độ cache **CHANNEL** |
| **Connection** | Kết nối vật lý hoặc proxy được framework quản lý | Thường được tái sử dụng |
| **Channel** | Phiên logic chạy trên connection, dùng publish/consume/ack | Publisher mượn rồi trả channel; listener có thể giữ channel suốt thời gian hoạt động |
| **RabbitTemplate** | Gửi message, request/reply, một số thao tác nhận chủ động | Có thể cấu hình dùng publisher connection riêng |
| **@RabbitListener** | Listener container đăng ký consumer và quản lý nhận/ack | Dùng ConnectionFactory của container |
| **RabbitAdmin** | Khai báo và kiểm tra topology (exchange/queue/binding) | Cần đi qua đúng connection phục vụ phần tài nguyên |

Ví dụ: một ứng dụng có 1 connection và 12 channel (2 cho listener, một số phục vụ publish, một số đang được cache). Tăng số channel **không** tạo ra một miền cô lập mới trước việc broker block cả connection.

## 2. Vì sao một connection chung có thể gây vấn đề?

RabbitMQ có cơ chế **resource alarm**, chẳng hạn memory alarm hoặc disk alarm, để bảo vệ broker khi tài nguyên khan hiếm. Broker có thể **chặn hoạt động publish** trên kết nối đang gửi message. Vì chặn theo **connection**, một ứng dụng trộn publish và consume trên cùng connection có nguy cơ bị ảnh hưởng cả hai chiều.

~~~mermaid
flowchart LR
    A["Publisher"] --> C["Một AMQP connection chung"]
    B["Consumer"] --> C
    C --> R[("RabbitMQ<br/>resource alarm")]
    R -.->|"Block connection do publish"| C
    R -->|"Khó tiêu thụ để giải phóng tài nguyên"| Q[("Queue backlog")]
~~~

Một chuỗi sự cố có thể diễn ra:

1. Ứng dụng nhận message từ một queue, xử lý và publish một sự kiện tiếp theo.
2. Broker thiếu tài nguyên và chặn connection đang publish.
3. Vì consumer cũng dùng connection đó, việc xử lý/nhận message có thể bị cản trở.
4. Consumer không kịp giải phóng backlog, làm tình trạng thiếu tài nguyên kéo dài.

Tách connection giúp hạn chế vòng phụ thuộc này: **publisher connection** có thể bị block trong khi **consumer connection** vẫn có cơ hội tiếp tục nhận/ack message để giảm tải broker. Đây là lý do chính để dùng tính năng tách kết nối.

**Phạm vi bảo vệ:** tách connection chỉ giảm rủi ro do trạng thái/block ở **cấp connection**. Nếu cả broker mất kết nối, không có quyền truy cập, hoặc một node đang ngừng phục vụ, hai connection vẫn có thể cùng lỗi. Đây không phải cơ chế failover broker, replication hay xác nhận giao nhận message.

## 3. Lựa chọn cấu hình nào phù hợp?

Có hai hướng phổ biến:

| Cách | Khi dùng | Đặc điểm |
| --- | --- | --- |
| **A. Một CachingConnectionFactory chính + RabbitTemplate.setUsePublisherConnection(true)** | Một broker/vhost, ứng dụng vừa publish vừa consume; muốn thay đổi ít | Framework dùng publisher connection factory riêng khi có thể; listener tiếp tục dùng factory chính |
| **B. Hai ConnectionFactory độc lập + gán rõ RabbitTemplate và listener container** | Cần cấu hình riêng cho từng vai trò, nhiều endpoint/credential hoặc giới hạn connection/channel khác nhau | Quyền kiểm soát rõ ràng, nhưng cần tự liên kết đúng các bean |

**Khuyến nghị cho đa số ứng dụng Spring Boot dùng RabbitMQ AMQP 0-9-1:** bắt đầu với cách A nếu cùng broker/vhost và không có yêu cầu phức tạp. Cách B phù hợp khi cần quản trị vòng đời, tài khoản, connection name hoặc tham số cache khác hẳn giữa hai vai trò.

Không nên cố giải quyết bằng cách chỉ tăng **spring.rabbitmq.cache.channel.size**: đó là cấu hình cache channel, chưa đảm bảo publisher và consumer nằm trên hai connection vật lý.

## 4. Cách A: Sử dụng publisher connection riêng của RabbitTemplate

Spring AMQP cung cấp **RabbitTemplate.setUsePublisherConnection(true)**. Khi bật và ConnectionFactory hỗ trợ **getPublisherConnectionFactory()**, thao tác publish thông thường của template sẽ dùng connection của factory dành cho publisher, tách khỏi connection mà listener container đang dùng.

Với **CachingConnectionFactory**, Spring AMQP có thể quản lý một publisher connection factory nội bộ và dùng cùng thông tin kết nối cơ bản (broker, virtual host, xác thực) với factory chính. Chế độ này hỗ trợ các ứng dụng vừa gửi vừa nhận trên cùng broker nhưng muốn cô lập **connection**.

### 4.1. Ví dụ với Spring Boot 3.x: tùy chỉnh template được auto-configure

Thêm starter AMQP:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-amqp")
}
~~~

Một **application.yml** tối thiểu:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: app
    password: local_dev_password
    virtual-host: /
    cache:
      connection:
        mode: channel
      channel:
        size: 25
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Giá trị **app/local_dev_password** chỉ là tài khoản ví dụ của môi trường lab. Hãy dùng user thực tế của RabbitMQ và đưa secret qua biến môi trường hoặc hệ thống quản lý bí mật khi triển khai thật.

Trong **Spring Boot 3.x**, có thể khai báo **RabbitTemplateCustomizer**:

~~~java
import org.springframework.boot.autoconfigure.amqp.RabbitTemplateCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PublisherConnectionConfig {

    @Bean
    RabbitTemplateCustomizer separatePublisherConnection() {
        return rabbitTemplate ->
                rabbitTemplate.setUsePublisherConnection(true);
    }
}
~~~

**Lợi ích:** Spring Boot tiếp tục tạo và cấu hình RabbitTemplate theo properties, converter, retry/observation khi có; customizer chỉ bật **usePublisherConnection**. Trong các bản Spring Boot 4.x, package của **RabbitTemplateCustomizer** có thể khác (đặc biệt giữa 4.0, 4.1 và 4.2); hãy đối chiếu API theo phiên bản dự án. Chính phương thức **RabbitTemplate.setUsePublisherConnection(true)** thuộc Spring AMQP vẫn là điểm cấu hình cần hiểu.

**Lưu ý về YAML:** các thiết lập **publisher-confirm-type**, **publisher-returns** và **template.mandatory** ở ví dụ phục vụ quan sát xác nhận và phát hiện message không được route; **chúng không phải điều kiện bắt buộc để tách connection**. Muốn kiểm chứng tách kết nối tối thiểu, chỉ cần bật usePublisherConnection và phát sinh cả thao tác publish lẫn consume.

### 4.2. Ví dụ thuần Spring AMQP: tạo template chủ động

Nếu không dùng Spring Boot customizer hoặc cần một template chuyên dùng để publish:

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DedicatedPublishingTemplateConfig {

    @Bean
    RabbitTemplate rabbitTemplate(ConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setUsePublisherConnection(true);
        return template;
    }
}
~~~

Ở đây **connectionFactory** cần là loại hỗ trợ publisher connection factory tách biệt, chẳng hạn **CachingConnectionFactory**. Đừng giả định mọi triển khai custom của interface **ConnectionFactory** đều cung cấp factory phụ.

Nếu tự khai báo RabbitTemplate trong Spring Boot, bean mặc định của Boot có thể **không được tạo** nữa. Khi cần bảo toàn message converter, retry, mandatory, observability hoặc cấu hình khác do Boot quản lý, hãy dùng **RabbitTemplateConfigurer** tương ứng phiên bản Boot để cấu hình template tùy chỉnh trước khi bật **setUsePublisherConnection(true)**. Đừng vô tình mất cấu hình chỉ vì muốn tách connection.

### 4.3. Minh họa đường đi khi bật usePublisherConnection

~~~mermaid
flowchart TD
    APP["Spring Boot application"] --> MAIN["CachingConnectionFactory chính"]
    MAIN --> C["Consumer connection"]
    MAIN --> PUB["Publisher connection factory nội bộ"]
    PUB --> P["Publisher connection"]
    APP --> RT["RabbitTemplate<br/>usePublisherConnection=true"]
    APP --> RL["@RabbitListener"]
    RT --> P
    RL --> C
    C --> R[("RabbitMQ broker/vhost")]
    P --> R
~~~

Các publisher và consumer vẫn có thể sử dụng **cùng broker và cùng virtual host**. Tách connection **không** tự tạo exchange, binding, queue hoặc sao chép message; topology vẫn quyết định đường đi. Một message publish bằng RabbitTemplate vẫn được route theo exchange và routing key.

### 4.4. Đặt tên connection để kiểm chứng trên Management UI

Spring AMQP hỗ trợ **ConnectionNameStrategy** nhằm gắn tên dễ đọc vào connection. Với publisher connection factory nội bộ, Spring AMQP thường dùng tên tạo từ strategy chính kèm hậu tố **.publisher**. Tên thực tế có thể chịu ảnh hưởng của phiên bản và cấu hình tùy chỉnh.

Ví dụ Spring Boot auto-configure CachingConnectionFactory có thể nhận bean:

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionNameStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ConnectionNamesConfig {

    @Bean
    ConnectionNameStrategy connectionNameStrategy() {
        return connectionFactory -> "orders-service";
    }
}
~~~

Trong **RabbitMQ Management → Connections**, sau khi cả publisher và consumer đã tạo kết nối, bạn có thể thấy các tên tương tự:

~~~text
orders-service
orders-service.publisher
~~~

Đây là **tên hiển thị** hỗ trợ quan sát, không phải định danh độc nhất để đảm bảo bảo mật hay ràng buộc quyền.

## 5. Cấu hình queue, publisher và listener để thử

Ví dụ khai báo một direct exchange, queue và binding; consumer tiếp nhận sự kiện đã publish:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderTopology {
    public static final String EXCHANGE = "lab.orders.events";
    public static final String QUEUE = "lab.orders.handlers";
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
    Binding ordersBinding(Queue ordersQueue,
                          DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
                .to(ordersExchange)
                .with(ROUTING_KEY);
    }
}
~~~

**RabbitAdmin** dùng connection factory chính (consumer) để tự động khai báo topology khi kết nối phù hợp được mở. Nếu trong context có nhiều admin hoặc queue được hạ tầng quản lý, cần xác định rõ admin chịu trách nhiệm và đảm bảo các khai báo tồn tại trước khi publish/consume.

Publisher:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(String orderId) {
        rabbitTemplate.convertAndSend(
                OrderTopology.EXCHANGE,
                OrderTopology.ROUTING_KEY,
                "order.created:" + orderId
        );
    }
}
~~~

Consumer:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {
    @RabbitListener(queues = OrderTopology.QUEUE)
    public void onOrderCreated(String message) {
        System.out.println("[listener] " + message);
    }
}
~~~

Để publish một message sau khi ứng dụng khởi động, thêm runner:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class DemoRunnerConfig {
    @Bean
    ApplicationRunner sendDemo(OrderPublisher publisher) {
        return args -> publisher.publish("O-1001");
    }
}
~~~

Sau khi chạy, log ứng dụng sẽ có thông điệp tương tự:

~~~text
[listener] order.created:O-1001
~~~

Kiểm tra trên RabbitMQ Management: có **connection cho listener** và **connection khác cho publisher** (nếu đều đã được khởi tạo và kết nối chưa bị đóng), đồng thời queue có consumer và message được deliver/ack. **Không chỉ dựa vào log listener** để khẳng định đã tách kết nối; log chỉ chứng minh message đi đến consumer.

## 6. Publisher confirms và returns vẫn cần cấu hình đúng

Tách kết nối publisher không đồng nghĩa publish đã được xác nhận thành công. Hãy phân biệt:

| Cơ chế | Điều xác nhận | Cấu hình liên quan |
| --- | --- | --- |
| **Publisher confirm** | Broker xác nhận đã xử lý publish theo publisher-confirm protocol | **publisher-confirm-type: correlated** |
| **Publisher return** | Message không được route tới queue trong trường hợp mandatory | **publisher-returns: true**, template **mandatory: true** |
| **Consumer ack** | Message đã được consumer/container xác nhận sau xử lý | Cấu hình ack của listener |
| **Dead-letter / retry** | Cách xử lý message lỗi hoặc bị reject | Queue DLX, chính sách retry/listener |

Ví dụ Spring Boot cấu hình:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Để nhận callback, cần đăng ký trên RabbitTemplate tương ứng:

~~~java
rabbitTemplate.setConfirmCallback((correlation, ack, cause) -> {
    if (!ack) {
        System.err.println("Publish NACK: " + cause);
    }
});

rabbitTemplate.setReturnsCallback(returned -> {
    System.err.println("Unroutable message: "
            + returned.getReplyText());
});
~~~

Đây là đoạn mã đặt **trong phần cấu hình template** khi template đã được tạo; **không tự động xuất hiện chỉ nhờ YAML**. Nếu cần gắn publisher confirm với từng yêu cầu nghiệp vụ, dùng **CorrelationData** và theo dõi kết quả/callback một cách có kiểm soát.

**Chú ý:** publisher confirm **ACK** không xác nhận mọi queue/consumer đã xử lý nghiệp vụ. Khi exchange tồn tại nhưng không có binding khớp, publish có thể vẫn được confirm ACK nhưng message không được route; publisher return với mandatory giúp phát hiện trường hợp không có queue đích. Retry hoặc gọi publish lần hai cũng có thể tạo message trùng, nên consumer vẫn cần thiết kế idempotency.

## 7. Ngoại lệ quan trọng: publish nằm trong consumer transaction

**setUsePublisherConnection(true)** có giới hạn có chủ đích: nếu RabbitTemplate đang tham gia **transaction được bắt đầu bởi listener container**, Spring AMQP dùng **channel của consumer transaction**, ngay cả khi template được cấu hình sử dụng publisher connection riêng.

Ví dụ nghiệp vụ nhận message, xử lý và publish tiếp trong cùng AMQP transaction:

~~~text
Consumer listener bắt đầu AMQP transaction
    |
    +-- consume từ input.queue
    +-- xử lý và gửi output event bằng RabbitTemplate transacted
    +-- commit/rollback transaction của channel

Khi publish tham gia transaction ấy:
    -> dùng channel transaction đã gắn với thread listener
    -> không tách sang publisher connection độc lập
~~~

Lý do là một AMQP transaction gắn với **channel**; nếu publish chuyển sang channel/connection khác, nó không còn tham gia cùng transaction. Spring AMQP ưu tiên giữ đúng ngữ nghĩa transaction.

| Tình huống | usePublisherConnection=true có tách publish không? |
| --- | --- |
| HTTP request hoặc service method publish thông thường | **Có**, khi ConnectionFactory hỗ trợ và không có transaction tiêu thụ ràng buộc |
| Scheduled job publish message | **Có**, với điều kiện tương tự |
| Listener nhận message rồi gọi publisher **ngoài** một AMQP transaction chia sẻ | **Thường có**, tùy cấu hình template và transaction thực tế |
| Template transacted chạy trong transaction của listener | **Không**; dùng channel transaction đang liên kết với listener |
| Custom ConnectionFactory không có publisher factory riêng | **Không thể giả định** sẽ có kết nối thứ hai |

**Đừng hiểu tách connection là giao dịch nguyên tử giữa database và RabbitMQ.** Dù dùng một hay hai connection, Spring AMQP không tự cung cấp distributed transaction exactly-once giữa DB và broker. Với nghiệp vụ cần độ tin cậy cao, thường phải cân nhắc idempotency, transactional outbox hoặc cơ chế nhất quán phù hợp.

### RabbitAdmin nên dùng connection nào?

Với topology mà listener sẽ tiêu thụ, **RabbitAdmin** thường nên sử dụng **consumer/main ConnectionFactory**, đặc biệt khi có **exclusive queue** hoặc **AnonymousQueue** phụ thuộc vòng đời connection.

Không nên khởi tạo RabbitAdmin từ **RabbitTemplate đã bật usePublisherConnection=true** rồi dùng nó để khai báo queue độc quyền cho listener: queue có thể bị khai báo trên publisher connection và không thể được consumer dùng như dự kiến. Ưu tiên constructor **RabbitAdmin(ConnectionFactory)** với main factory.

## 8. Cách B: tạo hai ConnectionFactory độc lập

Nếu publisher và consumer cần các tham số khác nhau, ví dụ connection name, cache size, broker endpoint hoặc credential riêng, hãy khai báo tường minh hai **CachingConnectionFactory**, gắn RabbitTemplate cho publisher và listener container cho consumer.

Ví dụ dưới đây dùng cùng broker/vhost nhưng **hai connection factory độc lập** để minh họa ranh giới. Đây là lựa chọn thay thế cho cách A, không cần bật **setUsePublisherConnection(true)** trên template dùng dedicated publisherConnectionFactory.

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration(proxyBeanMethods = false)
public class TwoConnectionFactoriesConfig {

    private static CachingConnectionFactory newFactory(String name) {
        CachingConnectionFactory cf =
                new CachingConnectionFactory("localhost");
        cf.setPort(5672);
        cf.setUsername("app");
        cf.setPassword("local_dev_password");
        cf.setVirtualHost("/");
        cf.setConnectionNameStrategy(factory -> name);
        return cf;
    }

    @Bean("consumerConnectionFactory")
    @Primary
    CachingConnectionFactory consumerConnectionFactory() {
        CachingConnectionFactory cf = newFactory("orders-consumers");
        cf.setChannelCacheSize(30);
        return cf;
    }

    @Bean("publisherConnectionFactory")
    CachingConnectionFactory publisherConnectionFactory() {
        CachingConnectionFactory cf = newFactory("orders-publishers");
        cf.setChannelCacheSize(30);
        cf.setPublisherConfirmType(
                CachingConnectionFactory.ConfirmType.CORRELATED);
        cf.setPublisherReturns(true);
        return cf;
    }

    @Bean
    RabbitTemplate rabbitTemplate(
            @Qualifier("publisherConnectionFactory")
            CachingConnectionFactory publisherFactory) {
        RabbitTemplate template = new RabbitTemplate(publisherFactory);
        template.setMandatory(true);
        return template;
    }

    @Bean("rabbitListenerContainerFactory")
    SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
            @Qualifier("consumerConnectionFactory")
            CachingConnectionFactory consumerFactory) {
        SimpleRabbitListenerContainerFactory listenerFactory =
                new SimpleRabbitListenerContainerFactory();
        listenerFactory.setConnectionFactory(consumerFactory);
        listenerFactory.setConcurrentConsumers(2);
        listenerFactory.setMaxConcurrentConsumers(4);
        listenerFactory.setPrefetchCount(10);
        return listenerFactory;
    }

    @Bean
    RabbitAdmin rabbitAdmin(
            @Qualifier("consumerConnectionFactory")
            CachingConnectionFactory consumerFactory) {
        return new RabbitAdmin(consumerFactory);
    }
}
~~~

Ở cấu hình này:

- **consumerConnectionFactory** dành cho listener container và RabbitAdmin.
- **publisherConnectionFactory** dành cho RabbitTemplate gửi message.
- **@Primary** giúp injection không chỉ định qualifier ưu tiên main/consumer factory, nhưng với các thành phần quan trọng vẫn nên dùng **@Qualifier** rõ ràng.
- **rabbitListenerContainerFactory** là tên factory mặc định mà @RabbitListener tìm khi không đặt containerFactory tường minh.
- **setPublisherConfirmType(CORRELATED)** và **setPublisherReturns(true)** áp dụng cho factory trực tiếp dùng để publish.
- **RabbitTemplate.setUsePublisherConnection(true) không cần thiết** ở đây; template đã trỏ tới publisher factory riêng. Bật thêm có thể khiến nó tìm một publisher factory phụ khác.

**Lưu ý với Spring Boot:** khi tự cung cấp ConnectionFactory và listener container factory, bạn chịu trách nhiệm kiểm tra các tùy chọn Boot thường cấu hình tự động (TLS, retry, listener ack, conversion, observations, health và các tham số khác). Ví dụ cố ý dùng credential lab và không thay cho cấu hình production. Để tránh nhân bản cấu hình, có thể dùng các **Configurer** của Spring Boot tương ứng đúng phiên bản khi xây bean tùy chỉnh.

### Khi nào cần endpoint hoặc vhost khác nhau?

Hai factory trong ví dụ dùng chung host/port/vhost để minh họa sự tách biệt **connection**. Nếu thiết kế dùng broker, virtual host hoặc tài khoản khác nhau, thay từng factory cho phù hợp. Khi đó:

1. Topology phải tồn tại ở **broker/vhost mà listener thực sự kết nối**.
2. Publisher phải gửi tới exchange ở **broker/vhost tương ứng với publisher factory**.
3. Nếu publisher và consumer kết nối hai broker khác nhau, chúng **không tự trao đổi message** chỉ vì exchange và queue trùng tên.
4. Cần giải pháp định tuyến liên broker/federation/shovel hoặc hệ thống trung gian riêng nếu thật sự muốn chuyển message giữa broker.

Trong phần lớn ứng dụng vừa publish vừa consume cùng một topology, **hai connection vào cùng broker/vhost** là phạm vi tách phù hợp nhất.

## 9. Điều chỉnh connection và channel cache theo tải

**CachingConnectionFactory** mặc định dùng **CacheMode.CHANNEL**: có thể tái sử dụng một connection chính, còn các channel được cache để giảm chi phí tạo mới. Khi dùng connection publisher riêng, có thể điều chỉnh **channel cache** cho từng vai trò nếu hệ thống thực sự cần.

| Thuộc tính | Tác dụng | Điều cần nhớ |
| --- | --- | --- |
| **channelCacheSize** | Số channel nhàn rỗi được giữ lại trong cache | Mặc định đây không phải giới hạn số channel đồng thời |
| **channelCheckoutTimeout** | Nếu lớn hơn 0, việc lấy channel có thể phải chờ | Khi bật timeout, kích thước channel cache trở thành giới hạn channel được checkout theo connection |
| **CacheMode.CHANNEL** | Cache channel trên connection | Thường phù hợp cho RabbitAdmin auto-declare |
| **CacheMode.CONNECTION** | Cache nhiều connection | Có các lưu ý riêng; auto-declaration của RabbitAdmin không được hỗ trợ ở chế độ này theo tài liệu Spring AMQP |
| **connectionLimit** | Giới hạn tổng số connection khi dùng connection cache mode phù hợp | Không nhầm với connectionCacheSize chỉ giữ số connection idle |

Trong Spring Boot có thể cấu hình cơ bản:

~~~yaml
spring:
  rabbitmq:
    cache:
      connection:
        mode: channel
      channel:
        size: 25
        checkout-timeout: 0ms
~~~

**0ms** có nghĩa không dùng cơ chế chờ để áp giới hạn channel theo timeout; cache size lúc này chỉ là số channel nhàn rỗi có thể giữ lại. Giá trị cache được chọn theo số listener, tốc độ publish và quan sát channel thực tế. Đặt cache quá nhỏ ở workload nhiều publisher có thể khiến channel mở/đóng liên tục, còn quá lớn tiêu tốn tài nguyên broker.

Để tùy chỉnh factory publisher nội bộ trong cách A, có thể kiểm tra loại factory:

~~~java
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;

// Đặt trong đoạn cấu hình nhận CachingConnectionFactory mainFactory.
ConnectionFactory publisherFactory =
        mainFactory.getPublisherConnectionFactory();

if (publisherFactory instanceof CachingConnectionFactory cachingPublisher) {
    cachingPublisher.setChannelCacheSize(40);
}
~~~

Không nên ép kiểu khi chưa kiểm tra: Spring AMQP có thể cho phép publisher factory kiểu khác tùy phiên bản/cấu hình. Cũng không nên đặt cache channel của publisher để cố giới hạn số connection: chúng là hai loại tài nguyên khác nhau.

## 10. Xác minh tách connection bằng RabbitMQ Management

Một bài kiểm chứng hoàn chỉnh:

1. Khởi chạy RabbitMQ cục bộ, bật plugin **Management** (giao diện thông thường ở **http://localhost:15672**).
2. Khởi động ứng dụng Spring Boot có @RabbitListener. Kiểm tra queue và consumer trên Management UI.
3. Publish message bằng RabbitTemplate đã bật **usePublisherConnection**.
4. Mở tab **Connections**, xác nhận ít nhất hai connection phục vụ vai trò consumer/publisher của ứng dụng (trong điều kiện các connection đã được tạo).
5. Đối chiếu connection name, channels trên từng connection và hoạt động publish/deliver/ack.
6. Dừng publisher hoặc thay điều kiện publish thử nghiệm, quan sát consumer vẫn dùng kết nối riêng của mình.

Các chỉ số đáng kiểm tra:

| Nơi xem | Cần thấy gì? |
| --- | --- |
| **Connections** | Các connection tách biệt, tên gợi ý **orders-service** và **orders-service.publisher** hoặc tên bạn tự cấu hình |
| **Channels** | Channel publish nằm dưới publisher connection; channel consume nằm dưới consumer connection |
| **Queues** | Consumer count, Ready, Unacked và tốc độ deliver/ack |
| **Exchanges** | Exchange/binding phù hợp để message được route |
| **Overview** | Memory, disk, message rates và dấu hiệu resource alarms |
| **Spring logs** | Kết nối thành công, exceptions/timeout, publisher callback, lỗi listener |

Nếu dùng Docker Compose service tên **rabbitmq**, có thể xem từ CLI:

~~~bash
docker compose exec rabbitmq rabbitmqctl list_connections name state channels
docker compose exec rabbitmq rabbitmqctl list_channels connection number consumer_count
~~~

Các cột và cách hiển thị có thể khác giữa các bản RabbitMQ; dùng **rabbitmqctl help list_connections** hoặc **rabbitmqctl help list_channels** khi CLI báo không hỗ trợ tên cột. Việc nhìn thấy hai connection cùng địa chỉ broker **không chứng minh** chúng có quyền, retry hoặc mục tiêu khác nhau; hãy kiểm tra chúng được tạo bởi những factory nào trong ứng dụng.

### Thử tình huống blocked connection có kiểm soát

Trên môi trường lab phù hợp, bạn có thể quan sát memory/disk alarm và sự khác biệt giữa publisher connection và consumer connection bằng công cụ giám sát broker. Tuy nhiên **không nên cố tình làm đầy đĩa hoặc tăng sử dụng bộ nhớ trên broker dùng chung**. Khi có resource alarm thực, mục tiêu là kiểm tra publisher bị chặn trong khi consumer vẫn có cơ hội tiến hành giao nhận và giải phóng backlog, không phải khẳng định hệ thống hoạt động bình thường trong mọi trường hợp thiếu tài nguyên.

## 11. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Chỉ thấy một connection | Template chưa bật **usePublisherConnection**, chưa có publish, hoặc đang dùng factory không hỗ trợ publisher factory | Kiểm tra cấu hình template, ConnectionFactory thực và chạy publish thử |
| Đã tăng channel cache nhưng consumer vẫn bị block | Producer/consumer vẫn dùng chung connection | Tách publisher connection thay vì chỉ tăng cache channel |
| Không thấy queue sau khi cấu hình factory thứ hai | RabbitAdmin dùng nhầm publisher ConnectionFactory hoặc thiếu quyền | Đặt admin với main/consumer factory, kiểm tra vhost và logs |
| **ACCESS_REFUSED** | Sai user/password/vhost hoặc quyền | Kiểm tra cấu hình của **cả hai** connection factory |
| **PRECONDITION_FAILED** | Khai báo queue/exchange khác thuộc tính đã tồn tại | So sánh queue type, durable, arguments; lên kế hoạch sửa topology |
| Publisher confirm ACK nhưng listener không nhận | Không có binding, sai exchange/routing key, listener dùng broker khác hoặc message bị route sai | Kiểm tra publisher returns, topology và consumer connection |
| Listener báo queue không tồn tại | Listener dùng sai broker/vhost hoặc RabbitAdmin chưa declare | Xác minh factory mà listener dùng và queue trên broker |
| Có hai factory nhưng tự động inject sai | Thiếu **@Qualifier** hoặc cấu hình factory mặc định | Đặt tên bean và qualifier tường minh, dùng @Primary có chủ đích |
| Bật separate publishing nhưng publish trong listener transaction vẫn dùng connection chung | Spring dùng channel transaction gắn với consumer | Kiểm tra phạm vi transaction; không phá ngữ nghĩa transaction chỉ để tách connection |
| Nhiều channel mở/đóng liên tục | Cache channel quá nhỏ so với tải | Quan sát channel churn rồi điều chỉnh cache theo số liệu thực |
| Chỉ thấy một connection sau khi thử publish một lần rồi chờ lâu | Connection publisher chưa được tạo, đã tự đóng, hoặc không hiển thị trong phạm vi lọc UI | Mở đúng vhost/broker, phát sinh traffic và xem logs |

## 12. Bài tập tự kiểm tra

**Câu 1.** Một ứng dụng có một connection và 30 channel. Vì sao vẫn có nguy cơ publisher làm consumer bị ảnh hưởng khi broker block connection?

**Câu 2.** Bạn bật **RabbitTemplate.setUsePublisherConnection(true)** trên CachingConnectionFactory nhưng gọi publish khi đang tham gia AMQP transaction của listener. Publish sẽ nhất thiết dùng connection thứ hai không?

**Câu 3.** Có một main ConnectionFactory dùng bởi @RabbitListener và một publisher factory riêng. RabbitAdmin khai báo **AnonymousQueue** để listener consume nên gắn vào factory nào?

**Câu 4.** Bật publisher confirm và nhận ACK. Điều đó có chứng minh listener đã ghi database thành công không? Nếu không có binding khớp, cơ chế nào giúp phát hiện?

**Câu 5.** Bạn khai báo hai CachingConnectionFactory khác nhau, RabbitTemplate gắn trực tiếp vào publisher factory. Có cần bật thêm **usePublisherConnection=true** không?

**Đáp án:**

1. Vì blocked là trạng thái **cấp connection**; nhiều channel trên cùng connection vẫn chia sẻ rủi ro.
2. **Không**; Spring AMQP sử dụng channel transaction của listener để giữ ngữ nghĩa AMQP transaction.
3. **Main/consumer ConnectionFactory**; queue exclusive có vòng đời phụ thuộc connection, tránh tạo ở publisher connection rồi consume ở connection khác.
4. **Không**; confirm không xác nhận xử lý nghiệp vụ. Dùng **publisher returns + mandatory** để phát hiện message không route được trong các trường hợp áp dụng.
5. **Không cần**; template đã dùng dedicated publisher factory. Bật thêm có thể làm chọn một publisher factory phụ khác.

## 13. Checklist trước khi triển khai

Hãy xác nhận **vai trò từng ConnectionFactory**, broker/vhost, cách template được tạo, có bật **usePublisherConnection** hay đã dùng factory riêng, RabbitAdmin sở hữu topology nào, listener container thật sự sử dụng factory nào, channel cache và timeout, publisher confirms/returns, transaction của listener, monitoring và kịch bản mất kết nối.

Tách connection là một kỹ thuật **cô lập tải và sự cố ở tầng AMQP connection**. Nó giúp một dịch vụ Spring AMQP vừa publish vừa consume có khả năng vận hành ổn định hơn khi broker chặn kết nối do publish, nhưng không thay thế **ack, retry, dead-letter, idempotency, giao dịch và quan sát hệ thống**. Hãy kiểm chứng bằng **Connections/Channels** trên RabbitMQ Management thay vì chỉ nhìn số message xử lý thành công.

### Tài liệu tham khảo

- [Spring AMQP – Connection and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html)
- [Spring AMQP – AmqpTemplate, Using a Separate Connection](https://docs.spring.io/spring-amqp/reference/amqp/template.html#using-a-separate-connection)
- [Spring AMQP – Correlated Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html#correlated-publisher-confirms-and-returns)
- [Spring Boot – AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html)
- [RabbitMQ – Resource Alarms](https://www.rabbitmq.com/docs/alarms)
