# Chuyển từ XML namespace sang Java/annotation khi có nhu cầu

## 1. Tại sao chuyển cấu hình và khi nào không cần chuyển?

Trong chương **Nâng cấp và tương thích** của module **SPRING_AMQP**, ta xây ứng dụng RabbitMQ bằng `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding, xác nhận giao nhận, retry, dead-letter, transaction và observability. Một ứng dụng Spring AMQP lâu năm có thể khai báo hầu hết những thành phần đó trong **XML namespace**:

- `<rabbit:connection-factory>`, `<rabbit:admin>` và `<rabbit:template>`;
- `<rabbit:queue>`, `<rabbit:direct-exchange>`, `<rabbit:bindings>`;
- `<rabbit:listener-container>` và `<rabbit:listener>`;
- Các bean `MessageConverter`, retry/error handler và transaction manager.

Trong ứng dụng mới, ta thường gặp `@Configuration`, `@Bean`, `@EnableRabbit`, `@RabbitListener` và cấu hình `application.yml` của Spring Boot.

**Điểm cần nhớ:** XML namespace **vẫn là cách cấu hình được Spring AMQP hỗ trợ**. Chuyển sang Java/annotation là một quyết định kiến trúc/bảo trì, **không phải điều kiện bắt buộc để RabbitMQ hoạt động, cũng không đồng nghĩa nâng giao thức từ AMQP 0.9.1 lên AMQP 1.0**. Không cần sửa một hệ thống ổn định chỉ để mọi tệp có cùng định dạng.

Những lý do hợp lý để chuyển:

1. Team chuẩn hóa cấu hình Java, code review, refactoring, type checking và dependency injection.
2. Cần tùy biến listener container bằng API ít hoặc không có thuộc tính tương đương trong XML namespace.
3. Muốn dùng `@RabbitListener` với tham số DTO, `@Header`, validation, `@RabbitHandler` hoặc endpoint ID rõ ràng.
4. Chuyển sang Spring Boot auto-configuration để giảm bean infrastructure thủ công.
5. Muốn tách cấu hình theo module, profile hoặc feature flag để migration từng bước.
6. Có kiểm thử tích hợp đủ tốt để **đo sự tương đương hành vi** trước và sau.

Lý do **chưa nên chuyển ngay**: XML chứa nhiều `RabbitAdmin`/virtual host, anonymous queue, retry advice, RPC reply container, conditional declaration, transaction policy hoặc các custom bean phức tạp chưa được inventory/test. Việc thay cấu hình quá nhanh có thể tạo thêm consumer cạnh tranh, làm thay đổi ACK/retry hoặc khai báo lại queue với arguments không tương thích.

> **Mục tiêu migration:** thay đổi **cách Spring tạo bean và quản lý endpoint**, giữ nguyên **hợp đồng message, tên exchange/queue/binding, consumer semantics, ACK/retry/DLQ, transaction và hiệu ứng nghiệp vụ** — trừ khi đã có yêu cầu thay đổi hành vi riêng và test riêng.

## 2. Hai trục nâng cấp phải tách biệt

Có hai loại thay đổi dễ bị trộn:

| Trục thay đổi | Ví dụ | Có bắt buộc đi cùng? |
| --- | --- | --- |
| **Cách cấu hình** | XML namespace → `@Configuration`, `@Bean`, `@RabbitListener` | Không cần thay Spring AMQP major version |
| **Phiên bản framework/client** | Spring AMQP 2.x/3.x → 4.x, Spring Boot 3.x → 4.x | Không bắt buộc phải bỏ XML chỉ vì đổi version |
| **Giao thức RabbitMQ** | AMQP 0.9.1 `spring-rabbit` → RabbitMQ-specific AMQP 1.0 `spring-rabbitmq-client` | Là migration giao thức riêng, API khác |
| **Broker/queue semantics** | classic → quorum queue, thay DLX/TTL, broker cluster | Không phải nhiệm vụ của việc đổi XML sang annotation |
| **Schema dữ liệu** | Java serialized payload → JSON/Protobuf; DTO version | Là thay đổi wire contract riêng |

Mục tiêu của bài là **trục thứ nhất**: thay cách khai báo nhưng vẫn sử dụng **AMQP 0.9.1** với `CachingConnectionFactory`, `RabbitTemplate` và listener containers. Nếu đồng thời nâng Spring AMQP **4.x**, lưu ý Spring Framework 7, Jackson 3 và thay đổi retry API so với những bản cũ; hãy làm thành **hai đợt triển khai độc lập** nếu có thể.

### 2.1. Không nhầm các loại connection factory

```text
AMQP 0.9.1:
  org.springframework.amqp.rabbit.connection.ConnectionFactory
    └─ CachingConnectionFactory
  RabbitTemplate / RabbitAdmin
  SimpleRabbitListenerContainerFactory
  DirectRabbitListenerContainerFactory

RabbitMQ AMQP 1.0 (Spring AMQP 4.0+):
  org.springframework.amqp.rabbitmq.client.AmqpConnectionFactory
  RabbitAmqpTemplate / RabbitAmqpAdmin
  RabbitAmqpListenerContainerFactory
```

Dù `@RabbitListener` được dùng trong nhiều hoàn cảnh, đổi XML sang Java **không** tự thay protocol. Trong cùng JVM có thể có hai connection factory loại khác nhau, phải chọn đúng factory cho từng listener/template và kiểm thử riêng.

## 3. Đầu tiên lập bản đồ cấu hình cũ

Đừng bắt đầu bằng việc xóa `rabbit-context.xml`. Hãy lập **inventory** để biết chính xác XML đang điều khiển những gì.

| Mục cần ghi lại | Câu hỏi bắt buộc |
| --- | --- |
| Connection factory | Host/addresses, port, vhost, credentials, SSL, heartbeat, channel cache, publisher confirm type? |
| `RabbitAdmin` | Có bao nhiêu admin? Auto startup? Conditional declarations? Admin nào sở hữu topology nào? |
| Exchange | Tên broker, loại, durable, auto-delete, internal, alternate exchange và arguments? |
| Queue | Tên, durable, exclusive, auto-delete, classic/quorum, TTL, DLX, delivery limit, policy? |
| Binding | Exchange, destination, routing key, binding arguments, headers exchange mapping? |
| `RabbitTemplate` | Exchange/routing key mặc định, converter, reply timeout, mandatory, returns/confirm, transaction? |
| Listener | Queue nào, handler ref/method, concurrency, prefetch, SMLC/DMLC, ack mode, auto-startup? |
| Retry và DLQ | Advice chain, exception classification, backoff, recoverer, `defaultRequeueRejected`, DLX policy? |
| Message conversion | `SimpleMessageConverter`, Jackson JSON, trusted packages, type headers, encoding? |
| Transaction | `channelTransacted`, `transactionManager`, DB commit boundary, manual ACK? |
| RPC | Reply-to, Direct Reply-To, fixed reply queue, correlation, `@SendTo`/manual reply? |
| Observability | Listener ID, idle events, consumer failed events, Micrometer tags, log context? |
| Deployment | Replica count, multiple brokers, profile overrides, reload, graceful stop, Kubernetes probes? |

**Đầu ra thực hành:** một bảng đối chiếu **XML cũ → bean Java hoặc property mới → test tương đương**. Nếu không biết một thuộc tính XML đang làm gì, tra tài liệu **đúng phiên bản đang chạy**. Không giả định mặc định hiện đại trùng mặc định của XML cũ; ví dụ `prefetchCount` đã thay đổi giá trị mặc định từ 1 lên 250 ở Spring AMQP 2.0.

## 4. Ví dụ XML namespace đang chạy

Giả sử một service nhận sự kiện thanh toán qua routing key `payment.completed`. Bản XML minh họa sử dụng Spring AMQP hỗ trợ namespace rabbit; các placeholder được nạp từ cấu hình Spring của ứng dụng.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:rabbit="http://www.springframework.org/schema/rabbit"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/rabbit
         https://www.springframework.org/schema/rabbit/spring-rabbit.xsd">

    <rabbit:connection-factory id="rabbitConnectionFactory"
                               host="localhost"
                               username="guest"
                               password="guest"/>

    <rabbit:admin id="amqpAdmin"
                  connection-factory="rabbitConnectionFactory"/>

    <rabbit:queue id="paymentQueue"
                  name="payments.completed.q"
                  durable="true"/>

    <rabbit:direct-exchange id="paymentExchange"
                            name="payments.x"
                            durable="true">
        <rabbit:bindings>
            <rabbit:binding queue="paymentQueue"
                            key="payment.completed"/>
        </rabbit:bindings>
    </rabbit:direct-exchange>

    <rabbit:template id="paymentTemplate"
                     connection-factory="rabbitConnectionFactory"
                     exchange="payments.x"
                     routing-key="payment.completed"/>

    <bean id="paymentHandler"
          class="com.example.payment.PaymentHandler"/>

    <rabbit:listener-container
            connection-factory="rabbitConnectionFactory"
            type="simple"
            concurrency="2"
            max-concurrency="4"
            prefetch="10"
            acknowledge="auto">
        <rabbit:listener id="paymentListener"
                         queues="payments.completed.q"
                         ref="paymentHandler"
                         method="handle"/>
    </rabbit:listener-container>

</beans>
```

Giả định `PaymentHandler.handle(String paymentId)` thực hiện nghiệp vụ đồng bộ và ném exception khi không thể xử lý. Đây là **sample baseline**, không phải cấu hình production hoàn thiện: `guest/guest` chỉ dùng ở RabbitMQ local; chưa khai báo DLX, retry hay TLS. Trong bài migration thật, phải chuyển cả những phần đang tồn tại ở hệ thống thật, không cắt bỏ vì ví dụ đơn giản.

### 4.1. Đừng nhầm ID bean và tên tài nguyên broker

Trong XML:

```xml
<rabbit:queue id="paymentQueue" name="payments.completed.q"/>
```

- `paymentQueue` là **bean ID** dùng để tham chiếu trong Spring.
- `payments.completed.q` là **queue name trong RabbitMQ**.
- Nếu chuyển thành `@Bean Queue paymentQueue()` nhưng vô tình gọi `new Queue("paymentQueue")` thì đã **đổi tên queue broker**, không chỉ đổi cách cấu hình.

Từ Spring AMQP 2.0, quy tắc alias bean ID/name của namespace đã thay đổi; khi di chuyển một ứng dụng cũ, đừng phụ thuộc vào alias tên broker như một bean name không được xác minh.

### 4.2. Listener container XML không đồng nghĩa Java @RabbitListener

`<rabbit:listener ref="paymentHandler" method="handle">` thường dùng adapter để gọi POJO method. Sau khi thêm `@RabbitListener` trên chính method đó, XML **vẫn còn** thì sẽ có thể tạo **hai consumer** cùng queue. Đó không phải một phép chuyển đổi “thêm annotation là xong”; phải **loại bỏ hoặc tắt endpoint XML cũ** tại bước cutover.

## 5. Cấu hình Java tương đương: connection, admin, template, topology

Có hai hướng:

1. **Spring Boot:** để Boot tạo connection factory/optional template/admin theo properties `spring.rabbitmq.*`; chỉ khai báo những bean custom cần thiết.
2. **Spring Framework không dùng Boot:** tự tạo `CachingConnectionFactory`, `RabbitAdmin`, `RabbitTemplate` và listener factory trong `@Configuration`.

Bản chính sau chọn **Spring Boot 3.x + Spring AMQP 3.x + Java 17+**, kết nối RabbitMQ AMQP **0.9.1** để so sánh với XML cũ. Cấu hình `spring.rabbitmq.*` thuộc Boot; nếu dùng Spring Framework thuần, những property đó không tự có hiệu lực trừ khi bạn tự bind.

### 5.1. application.yml quản lý kết nối

```yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST:localhost}
    port: 5672
    username: ${RABBITMQ_USERNAME:app_payment}
    password: ${RABBITMQ_PASSWORD}
    virtual-host: "/"
    publisher-confirm-type: correlated
    publisher-returns: true

app:
  payment:
    queue: payments.completed.q
    exchange: payments.x
    routing-key: payment.completed
```

Cấu hình confirm/returns là **nâng cấp tính quan sát có chủ đích**, không có trong XML baseline. Nếu mục tiêu **strict parity** trước tiên, nên giữ cấu hình tương đương XML và bật thêm confirm/returns trong một thay đổi riêng kèm test. Đừng vô tình coi “sửa config” là nguyên nhân của khác biệt publisher behavior.

Nếu môi trường dùng TLS, multiple addresses hoặc virtual host riêng, ánh xạ đúng các giá trị từ XML. Không hardcode credential vào source/manifest production. Spring Boot auto-configure `CachingConnectionFactory` khi phù hợp; **đừng tạo thêm một `@Bean CachingConnectionFactory` thủ công** chỉ vì quen XML, trừ khi thật sự cần cấu hình khác mặc định.

### 5.2. Java @Configuration khai báo exchange/queue/binding

```java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PaymentTopologyConfiguration {

    @Bean
    public Queue paymentQueue() {
        return QueueBuilder.durable("payments.completed.q").build();
    }

    @Bean
    public DirectExchange paymentExchange() {
        return new DirectExchange("payments.x", true, false);
    }

    @Bean
    public Binding paymentBinding(Queue paymentQueue,
                                  DirectExchange paymentExchange) {
        return BindingBuilder.bind(paymentQueue)
                .to(paymentExchange)
                .with("payment.completed");
    }
}
```

Các mục đối chiếu:

| XML | Java |
| --- | --- |
| `<rabbit:queue id="paymentQueue" name="payments.completed.q" durable="true"/>` | `@Bean Queue paymentQueue() { return QueueBuilder.durable("payments.completed.q").build(); }` |
| `<rabbit:direct-exchange name="payments.x" durable="true">` | `@Bean DirectExchange paymentExchange() ...` |
| `<rabbit:binding queue="paymentQueue" key="payment.completed"/>` | `BindingBuilder.bind(paymentQueue).to(paymentExchange).with("payment.completed")` |
| `<rabbit:admin connection-factory="..."/>` | `RabbitAdmin` bean hoặc auto-configured admin của Boot |
| `<rabbit:template ... exchange="payments.x" routing-key="payment.completed"/>` | `RabbitTemplate` đặt `exchange`/`routingKey` hoặc truyền khi gửi |
| `<rabbit:listener-container ...>` | `SimpleRabbitListenerContainerFactory` + `@RabbitListener`, hoặc bean `SimpleMessageListenerContainer` |
| `<rabbit:annotation-driven/>` | `@EnableRabbit` khi tự cấu hình |
| `<rabbit:listener ref="..." method="handle">` | `@RabbitListener` trên method hoặc giữ `MessageListenerAdapter` |

**Vai trò RabbitAdmin:** Spring AMQP khai báo `Queue`, `Exchange` và `Binding` beans vào broker khi một `RabbitAdmin` quản lý kết nối thích hợp, thường khi AMQP connection được mở. `@Bean` chỉ tạo mô tả trong ApplicationContext; **không** tự đồng nghĩa broker đã có topology. Với Boot auto-configuration mặc định, admin có thể đã được cung cấp; với ứng dụng non-Boot, tạo một `RabbitAdmin` riêng.

### 5.3. Nếu không dùng Spring Boot: tạo infrastructure tường minh

```java
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class StandaloneRabbitInfrastructure {

    @Bean
    CachingConnectionFactory rabbitConnectionFactory() {
        var cf = new CachingConnectionFactory("localhost");
        cf.setUsername("guest");
        cf.setPassword("guest");
        return cf;
    }

    @Bean
    RabbitAdmin amqpAdmin(CachingConnectionFactory rabbitConnectionFactory) {
        return new RabbitAdmin(rabbitConnectionFactory);
    }

    @Bean
    RabbitTemplate paymentTemplate(
            CachingConnectionFactory rabbitConnectionFactory) {
        RabbitTemplate template = new RabbitTemplate(rabbitConnectionFactory);
        template.setExchange("payments.x");
        template.setRoutingKey("payment.completed");
        return template;
    }
}
```

**Đây là phương án thay thế** Boot-managed infrastructure, **không phải cấu hình bổ sung phải chạy song song** với `spring.rabbitmq.*` auto-configuration. Ví dụ dùng `guest` chỉ phù hợp localhost; production phải tách credentials, TLS và cấu hình ngoài.

### 5.4. Nếu Boot auto-configure RabbitTemplate

Khi dùng Boot và không cần template custom, có thể:

```java
import org.springframework.stereotype.Service;

@Service
class PaymentEventPublisher {
    private final RabbitTemplate template;

    PaymentEventPublisher(RabbitTemplate template) {
        this.template = template;
    }

    void publish(String paymentId) {
        template.convertAndSend(
                "payments.x", "payment.completed", paymentId);
    }
}
```

Ở đây exchange/routing key đã được truyền **tường minh** nên không phụ thuộc cấu hình default template. Nếu thay bằng `template.convertAndSend(paymentId)` như một số XML cũ, phải giữ đúng `exchange` và `routingKey` mặc định bằng Boot properties hoặc customizer, nếu không message có thể đi sai đường.

## 6. Chuyển listener-container XML sang @RabbitListener

### 6.1. Định nghĩa factory đúng cấu hình cũ

```java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableRabbit
class PaymentListenerConfiguration {

    @Bean("paymentListenerFactory")
    SimpleRabbitListenerContainerFactory paymentListenerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);

        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(4);
        factory.setPrefetchCount(10);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);

        return factory;
    }
}
```

**SMLC:** `concurrentConsumers=2`, `maxConcurrentConsumers=4` là số consumer **trên mỗi application instance**. Với 3 Pod, tổng consumer có thể lên tới 12 khi tải tăng. `prefetch=10` là giới hạn delivery chưa ACK cho mỗi consumer, không phải số handler nghiệp vụ chạy song song.

`@EnableRabbit` bật nhận diện annotation trong Spring context tự cấu hình. Nếu Boot đã cung cấp infrastructure hỗ trợ, có thể không cần thêm annotation này, nhưng thêm ở cấu hình tự quản lý giúp minh họa ranh giới rõ ràng.

### 6.2. Chuyển POJO handler sang annotated endpoint

XML cũ:

```xml
<rabbit:listener-container connection-factory="rabbitConnectionFactory"
                           concurrency="2"
                           max-concurrency="4"
                           prefetch="10"
                           acknowledge="auto">
    <rabbit:listener id="paymentListener"
                     ref="paymentHandler"
                     method="handle"
                     queues="payments.completed.q"/>
</rabbit:listener-container>
```

Java mới:

```java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
class PaymentHandler {
    private final PaymentAuditService auditService;

    PaymentHandler(PaymentAuditService auditService) {
        this.auditService = auditService;
    }

    @RabbitListener(
            id = "paymentListener",
            queues = "payments.completed.q",
            containerFactory = "paymentListenerFactory")
    public void handle(String paymentId) {
        auditService.recordOnce(paymentId);
    }
}
```

`PaymentAuditService` là service nghiệp vụ giả định, ghi DB theo khóa duy nhất để redelivery không tạo tác động hai lần. Đây là **thay thế** cho bean `paymentHandler` trong XML, không thêm một consumer thứ hai.

**Cần xác minh converter:** đường XML `MessageListenerAdapter` và đường annotation có thể có bước chuyển đổi tham số khác nhau. Với `String` và content type dạng text, kết quả thường giống nhau; với JSON DTO, headers `__TypeId__`, method signature, type inference và converter có thể khác. Vì vậy phải test bằng **message bytes/properties thực** chứ không chỉ gọi thẳng Java method.

### 6.3. Đặt tên factory mặc định hay factory riêng?

Spring AMQP tìm bean có tên **`rabbitListenerContainerFactory`** làm factory mặc định cho `@RabbitListener` không chỉ định `containerFactory`.

- Nếu đặt tên `paymentListenerFactory` như ví dụ, **phải** khai báo `containerFactory = "paymentListenerFactory"` trên endpoint cần nó.
- Nếu muốn dùng mặc định cho toàn ứng dụng, tạo bean có tên `rabbitListenerContainerFactory` và bảo đảm các endpoint khác chấp nhận cùng cấu hình.
- Nếu nhiều loại container/factory, dùng tên rõ theo nghiệp vụ/protocol và tránh `@Primary` không cần thiết.
- Với Boot, default factory có thể đã tồn tại và được cấu hình qua properties; đừng đăng ký một factory cùng tên mà vô tình ghi đè hoặc làm Boot back off.

### 6.4. Cấu hình concurrency trên annotation

Nếu hệ thống cần một listener khác có độ đồng thời riêng:

```java
@RabbitListener(
        id = "fastPayments",
        queues = "payments.fast.q",
        containerFactory = "paymentListenerFactory",
        concurrency = "2-4")
public void fastHandle(String paymentId) {
    // ...
}
```

Với **SMLC**, `concurrency="2-4"` chỉ định khoảng min–max consumers cho endpoint, ghi đè cấu hình concurrency của factory. Với **DMLC**, chỉ dùng một số nguyên cho `consumersPerQueue`, không dùng `"2-4"`. Phân biệt hai loại trước khi copy XML.

### 6.5. Phương án chuyển ít rủi ro: giữ listener-container Java trước

Có thể chuyển XML thành **Java bean `SimpleMessageListenerContainer`**, vẫn dùng `MessageListenerAdapter` và POJO handler, **chưa đổi sang `@RabbitListener`**:

```java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.amqp.rabbit.listener.adapter.MessageListenerAdapter;
import org.springframework.context.annotation.Bean;

@Bean
SimpleMessageListenerContainer paymentLegacyContainer(
        ConnectionFactory connectionFactory,
        PaymentLegacyHandler paymentHandler) {

    var container = new SimpleMessageListenerContainer(connectionFactory);
    container.setQueueNames("payments.completed.q");
    container.setConcurrentConsumers(2);
    container.setMaxConcurrentConsumers(4);
    container.setPrefetchCount(10);
    container.setAcknowledgeMode(
            org.springframework.amqp.core.AcknowledgeMode.AUTO);

    var adapter = new MessageListenerAdapter(paymentHandler);
    adapter.setDefaultListenerMethod("handle");
    container.setMessageListener(adapter);

    return container;
}
```

Cách này giữ nguyên cơ chế **adapter gọi POJO method** gần với XML nhất, dễ kiểm thử behavior parity. Khi đã ổn định mới thay bằng factory + `@RabbitListener`. Không chạy bean `paymentLegacyContainer` cùng XML listener và annotation listener trên một queue trong một instance.

**Lifecycle khác nhau:** bean container tạo thủ công là Spring bean; container do `@RabbitListener` tạo được quản lý qua `RabbitListenerEndpointRegistry`, không phải bean có thể autowire trực tiếp theo tên. Monitoring hoặc thao tác start/stop trước đây tìm container bằng bean ID phải đổi theo registry.

## 7. Ánh xạ thuộc tính XML sang Java: đừng bỏ qua ngữ nghĩa

| XML namespace (ví dụ) | Java / annotation tương đương | Cạm bẫy |
| --- | --- | --- |
| `type="simple"` | `SimpleRabbitListenerContainerFactory` | Không vô tình dùng DMLC |
| `type="direct"` | `DirectRabbitListenerContainerFactory` | Concurrency dùng `consumersPerQueue` |
| `concurrency="2"` | `setConcurrentConsumers(2)` | Per instance, không phải toàn cluster |
| `max-concurrency="4"` | `setMaxConcurrentConsumers(4)` | Chỉ áp dụng SMLC |
| `consumers-per-queue="2"` | `setConsumersPerQueue(2)` | Chỉ DMLC |
| `prefetch="10"` | `setPrefetchCount(10)` | Không nhầm với số callback đồng thời |
| `acknowledge="auto"` | `setAcknowledgeMode(AUTO)` | Spring AUTO là container ACK, không phải RabbitMQ autoack |
| `acknowledge="manual"` | `setAcknowledgeMode(MANUAL)` hoặc `@RabbitListener(ackMode="MANUAL")` | Listener phải tự ACK/NACK đủ nhánh |
| `acknowledge="none"` | `setAcknowledgeMode(NONE)` | RabbitMQ auto-ack; thay đổi mất an toàn nếu vô tình bật |
| `channel-transacted="true"` | `setChannelTransacted(true)` trên container | Không tạo transaction nguyên tử RabbitMQ + database |
| `transaction-manager="..."` | `setTransactionManager(...)` nếu API/container hỗ trợ | Giữ đúng transaction manager và ranh giới DB |
| `auto-startup="false"` | `factory.setAutoStartup(false)` hoặc `@RabbitListener(autoStartup="false")` | Cutover phải chủ động start |
| `task-executor="..."` | `factory.setTaskExecutor(...)` | Tên/threads có thể ảnh hưởng concurrency |
| `receive-timeout="..."` | `setReceiveTimeout(...)` (SMLC) | Đơn vị thường milliseconds, không phải timeout nghiệp vụ |
| `default-requeue-rejected="false"` | `setDefaultRequeueRejected(false)` nếu factory/version hỗ trợ | Tạo thay đổi DLQ/retry rất lớn |
| `idle-event-interval="..."` | `setIdleEventInterval(...)` | Nếu bỏ có thể mất monitoring |
| `recovery-interval="..."` | `setRecoveryInterval(...)` ở SMLC/factory phù hợp | DMLC dùng cơ chế monitor/recovery khác |
| `missing-queues-fatal="..."` | `setMissingQueuesFatal(...)` | Ảnh hưởng startup/readiness |
| `exclusive="true"` | `container.setExclusive(true)` hoặc endpoint tùy API | Không chạy nhiều consumers tranh exclusive |
| `admin="..."` | `container.setRabbitAdmin(...)` hoặc declarable owner | Cần với conditional/auto-delete queues |

Tài liệu chính thức có **bảng property ↔ namespace attribute** cho từng container và đánh dấu SMLC/DMLC. Có các thuộc tính **không được namespace biểu diễn trực tiếp**, cũng có khác biệt theo phiên bản. Không cố tạo mapping “tên XML đổi sang camelCase là đủ” nếu property thiếu ở factory; có thể cần `ContainerCustomizer` hoặc bean container thủ công.

### 7.1. DMLC ví dụ riêng

```java
import org.springframework.amqp.rabbit.config.DirectRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;

@Bean("directPaymentListenerFactory")
DirectRabbitListenerContainerFactory directPaymentListenerFactory(
        ConnectionFactory connectionFactory) {

    var factory = new DirectRabbitListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setConsumersPerQueue(2);
    factory.setPrefetchCount(10);
    return factory;
}
```

Chỉ dùng DMLC nếu XML cũ là `type="direct"` hoặc đã quyết định **đổi container type riêng**. DMLC sử dụng client thread model và recovery/monitoring khác SMLC. Một migration cú pháp thuần không nên âm thầm đổi cả container type và semantics.

## 8. @RabbitListener và cách khai báo topology bằng annotation

Bạn có thể giữ `@Bean Queue/Exchange/Binding` tách khỏi listener, hoặc gói declarables ngay trên annotation.

### 8.1. Khai báo trực tiếp tại endpoint

```java
import org.springframework.amqp.rabbit.annotation.Exchange;
import org.springframework.amqp.rabbit.annotation.Queue;
import org.springframework.amqp.rabbit.annotation.QueueBinding;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
class AnnotationPaymentListener {

    @RabbitListener(
            id = "annotatedPaymentListener",
            bindings = @QueueBinding(
                    value = @Queue(
                            value = "payments.completed.q",
                            durable = "true"),
                    exchange = @Exchange(
                            value = "payments.x",
                            type = "direct",
                            durable = "true"),
                    key = "payment.completed"))
    public void onPayment(String paymentId) {
        // Business service xử lý message.
    }
}
```

Đây là **lựa chọn thay thế** phần `PaymentTopologyConfiguration` + listener đã dùng ở mục 5–6. **Không đăng ký đồng thời `AnnotationPaymentListener` và `PaymentHandler` trên cùng queue** trong test muốn chỉ một consumer nhận message.

**Khi nào thích annotation bindings?** Khi endpoint và topology đơn giản, cùng một team sở hữu cả hai và các tham số không thay đổi thường xuyên.

**Khi nào nên dùng `@Bean` declarables?** Khi topology dùng chung nhiều listener/service, có DLX, quorum, queue arguments, multiple bindings, conditional admin, broker-named queue hoặc bạn muốn IaC quản lý topology. Annotations làm nổi bật địa chỉ listener, nhưng không thay thế mọi chính sách broker.

### 8.2. queues, queuesToDeclare và bindings khác nhau

| Cách viết | Ý nghĩa |
| --- | --- |
| `@RabbitListener(queues="payments.completed.q")` | **Nghe queue có tên đó**; queue phải tồn tại hoặc được quản lý khai báo bên ngoài |
| `@RabbitListener(queuesToDeclare=@Queue(...))` | Khai báo queue theo annotation khi hạ tầng có `RabbitAdmin` |
| `@RabbitListener(bindings=@QueueBinding(...))` | Khai báo queue/exchange/binding gắn với endpoint |
| `@RabbitListener(queues="#{paymentQueue.name}")` | Dùng tên queue từ bean nếu cần bean/SpEL |

**Sai lầm thường gặp:** chuyển XML `<rabbit:queue id="paymentQueue" name="payments.completed.q">` thành `@RabbitListener(queues="paymentQueue")`. Chuỗi ở `queues` là **broker queue name**, không phải tên `@Bean`; nếu Broker không có queue `paymentQueue`, listener có thể fail startup.

### 8.3. Đừng dùng anonymous queue khi yêu cầu durability

Ví dụ `@Queue` không đặt tên trong `@QueueBinding` có thể tạo **anonymous/exclusive/auto-delete queue**. Điều này phù hợp với một listener tạm kiểu pub/sub, nhưng **không** phù hợp queue công việc cần giữ message qua restart. Chuyển XML named durable queue thành anonymous queue là thay đổi semantics nghiêm trọng.

### 8.4. Queue arguments và migration bất biến

Nếu XML cũ dùng `x-queue-type=quorum`, `x-dead-letter-exchange`, TTL, max length, priority hoặc các arguments khác, phải chuyển tương đương qua `QueueBuilder`/`@Argument` hoặc quản lý bằng RabbitMQ policy phù hợp. Đừng giữ đúng **tên queue** nhưng thay **arguments**: RabbitMQ thường từ chối re-declare không tương đương bằng `PRECONDITION_FAILED`.

Một ví dụ thay cho bean queue đơn giản:

```java
@Bean
Queue durableQuorumPaymentQueue() {
    return QueueBuilder.durable("payments.completed.q")
            .quorum()
            .deadLetterExchange("payments.dlx")
            .deadLetterRoutingKey("payment.invalid")
            .build();
}
```

**Ví dụ này chỉ đúng nếu broker đang có queue quorum với arguments tương ứng hoặc đã có kế hoạch migration queue type riêng.** Không thay bean `paymentQueue()` ở mục 5 bằng snippet này trong môi trường queue đang là classic, vì không thể đổi classic → quorum tại chỗ chỉ bằng code. Nếu áp dụng DLX, phải tạo DLX, DLQ và binding của nó.

## 9. Message converter: thay XML nhưng giữ nguyên wire format

Một lỗi migration khó phát hiện: XML cũ dùng `SimpleMessageConverter` hoặc `Jackson2JsonMessageConverter`, Java listener mới dựa vào converter khác, nhận `String`/`byte[]`/JSON DTO không tương đương.

### 9.1. Hai tầng chuyển đổi của annotated method

Với `@RabbitListener` có thể có:

1. **AMQP `MessageConverter`:** body bytes + properties → Java payload.
2. **Spring Messaging method argument conversion:** chọn/ép kiểu tham số cho method được annotation.

Trong khi đó, `MessageListenerAdapter` cũ thường gọi method POJO theo contract của adapter converter. Hai đường không nhất thiết suy luận cùng class từ headers/type inference.

**Test bắt buộc**:

- `contentType`/charset có đúng không?
- Spring JSON type headers `__TypeId__`, `__ContentTypeId__`, `__KeyTypeId__` có còn được dùng như cũ không?
- DTO interface/abstract có cần alias mapping không?
- Lỗi parse có bị xử lý trước khi business method được gọi không?
- Tên field JSON, enum, timestamps, null behavior có đổi không?

### 9.2. Ví dụ Jackson JSON cho Spring AMQP 3.x

```java
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;

@Bean
Jackson2JsonMessageConverter paymentJsonConverter() {
    return new Jackson2JsonMessageConverter(
            "com.example.payment.messaging.dto");
}

@Bean("paymentJsonListenerFactory")
SimpleRabbitListenerContainerFactory paymentJsonListenerFactory(
        ConnectionFactory cf,
        Jackson2JsonMessageConverter paymentJsonConverter) {

    var factory = new SimpleRabbitListenerContainerFactory();
    factory.setConnectionFactory(cf);
    factory.setMessageConverter(paymentJsonConverter);
    factory.setConcurrentConsumers(2);
    factory.setPrefetchCount(10);
    return factory;
}
```

Converter ở đây chấp nhận type metadata cho package DTO đã định, nhưng phải kiểm tra constructor/`trustedPackages` behavior của **phiên bản đang dùng**, không bật wildcard `*` cho message không đáng tin cậy. Nếu publisher dùng một converter khác, cần gắn đúng vào `RabbitTemplate`.

### 9.3. Spring AMQP 4.x: Jackson 3 là một thay đổi riêng

Spring AMQP **4.0** giới thiệu `JacksonJsonMessageConverter` và `DefaultJacksonJavaTypeMapper` dựa trên **Jackson 3** (package `tools.jackson.*`), trong khi các class Jackson 2 như `Jackson2JsonMessageConverter` được deprecated-for-removal ở 4.0. Spring AMQP 4.0 cũng yêu cầu **Spring Framework 7**. Đây là **migration thư viện**, không phải hậu quả tự động của đổi XML sang Java.

Nếu ứng dụng đang 3.x và muốn hạn chế rủi ro, chuyển XML → Java trước với **cùng version & converter**, kiểm thử thành công rồi mới nâng Boot/Spring AMQP/Jackson theo một lượt riêng. Tránh đổi hai chiều cùng lúc rồi không biết lỗi do type mapper, method signature hay framework version.

## 10. ACK, retry, DLQ và transaction: nhóm thuộc tính không được đổi ngầm

### 10.1. AUTO, MANUAL và NONE

| XML cũ | Java mới | Tác động |
| --- | --- | --- |
| `acknowledge="auto"` | `AcknowledgeMode.AUTO` | Spring ACK khi listener trả về bình thường, tùy error handler/transaction |
| `acknowledge="manual"` | `AcknowledgeMode.MANUAL` | Method phải gọi `Channel.basicAck/basicNack/basicReject` |
| `acknowledge="none"` | `AcknowledgeMode.NONE` | RabbitMQ tự coi delivery được ACK ngay, không đợi business commit |

**Không nhầm Spring AUTO với RabbitMQ auto-ack.** Trong Spring, `NONE` mới tương ứng kiểu broker không chờ ACK. Đổi từ `AUTO` sang `NONE` trong migration có thể làm mất message khi handler bị lỗi.

Ví dụ listener manual (chỉ dùng khi factory/endpoint chọn MANUAL, không chạy song song với AUTO):

```java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;

@RabbitListener(
        id = "manualPayments",
        queues = "payments.manual.q",
        containerFactory = "paymentListenerFactory",
        ackMode = "MANUAL")
public void onManualPayment(Message message, Channel channel)
        throws IOException {

    long tag = message.getMessageProperties().getDeliveryTag();

    try {
        // Xử lý đồng bộ và commit DB tại service nghiệp vụ.
        paymentService.processOnce(message.getBody());
        channel.basicAck(tag, false);
    }
    catch (NonRetryablePaymentException ex) {
        channel.basicReject(tag, false); // DLX nếu queue đã cấu hình.
    }
    catch (RetryablePaymentException ex) {
        channel.basicNack(tag, false, true); // Demo; cần backoff thực tế.
    }
}
```

`paymentService` và exception classes là thành phần ứng dụng giả định. Ví dụ này thể hiện **vị trí ACK**; trong production cần xét lỗi bất ngờ, lỗi ngay khi ACK và tránh vòng requeue nóng. Vì mã ví dụ đặt trên một method bên ngoài class, khi đưa vào dự án phải gắn trong Spring-managed component có inject service.

### 10.2. Retry advice chain không tự được chuyển sang annotation

XML có thể khai báo retry interceptor qua `advice-chain`. Chỉ thêm `@RabbitListener` mà không gắn advice tương ứng vào factory sẽ đổi số lần retry và hành vi hết retry.

Phân biệt:

- **Retry phía publisher:** `RabbitTemplate` và publisher confirms/returns; timeout/network outcome có thể không xác định.
- **Retry phía consumer:** listener exception, backoff, advice chain, `defaultRequeueRejected`, DLQ.
- **Redelivery từ broker:** khi consumer/channel mất trước ACK, có thể giao lại message dù listener đã commit DB.

Khi migrate:

1. Giữ nguyên policy retry/backoff/error classification trong vòng đầu tiên.
2. Kiểm tra recoverer khi hết retry: reject, republish error exchange hoặc forward DLQ?
3. Đừng tự động bật `defaultRequeueRejected=false` để “hết lỗi log”: có thể làm message mất nếu DLX chưa cấu hình.
4. Đảm bảo consumer **idempotent** với business key, nhất là khi rollout có Pod XML cũ và Pod Java mới cùng nghe queue.

### 10.3. Chú ý version API retry

Spring AMQP **4.0** chuyển các API retry dùng trong dự án sang Spring Core Retry thay cho dependency `spring-retry` ở các version trước. Nếu code XML cũ khai báo bean `RetryOperationsInterceptor`/`RetryTemplate` từ Spring Retry và trong cùng PR lại nâng Spring AMQP major version, cần **đối chiếu breaking changes riêng**. Không sao chép nguyên Java `RetryInterceptorBuilder` từ tài liệu 2.x/3.x sang 4.x mà không đọc migration guide.

### 10.4. Transaction giữa DB và RabbitMQ

`channelTransacted` là lựa chọn giao dịch của RabbitMQ channel. Dù có Spring DB `PlatformTransactionManager`, đồng bộ commit với RabbitMQ là **best-efforts one-phase**, không XA atomic DB+broker. Chuyển cấu hình không thay đổi giới hạn này.

Nếu một consumer ghi DB rồi ACK thất lạc, message có thể redeliver. Nếu một publisher ghi DB rồi publish và crash giữa hai bước, có thể mất event. Với nghiệp vụ quan trọng, dùng **transactional outbox + idempotent inbox** thay vì coi `@Transactional` là giải pháp bao trùm.

## 11. Migrating RPC và reply queues cần kiểm thử riêng

Một số XML cũ cấu hình `<rabbit:template reply-queue="..." reply-address="...">` cùng `<rabbit:reply-listener/>`. Chuyển thành `new RabbitTemplate(connectionFactory)` mà bỏ reply listener có thể làm requester timeout dù worker đã trả lời.

| Trường hợp | Phải giữ gì khi đổi sang Java |
| --- | --- |
| Direct Reply-To mặc định | Không khai báo pseudo-queue `amq.rabbitmq.reply-to`; template quản lý reply container |
| Fixed reply queue | `setReplyAddress(...)`, listener container có `setMessageListener(rabbitTemplate)`, queue tồn tại |
| RPC timeout | `replyTimeout` và ngân sách HTTP/worker phù hợp |
| Correlation custom | `correlationId`, `userCorrelationId`, `correlationKey` (nếu dùng legacy) |
| Returns/confirm | `mandatory`, publisher returns, `CorrelationData` và callback ownership |
| Nhiều requester Pod | Fixed reply queue riêng **cho mỗi requester instance/template**; không chia sẻ competing consumers |

**Không gộp migration RPC với đổi sang AMQP 1.0**. `RabbitAmqpTemplate` của module mới có API async/settlement khác; đó là lộ trình riêng.

## 12. Chuyển một phần bằng @ImportResource: cách giữ ranh giới rõ

Bạn **không cần chuyển toàn bộ XML trong một commit**. Spring hỗ trợ import cấu hình XML vào Java context.

Ví dụ đang giữ nguyên connection factory và RabbitAdmin trong XML, nhưng chuyển topology/handler sang Java:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportResource;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;

@Configuration(proxyBeanMethods = false)
@EnableRabbit
@ImportResource("classpath:legacy-rabbit-infrastructure.xml")
class HybridRabbitConfiguration {
    // Bean Java mới được nạp trong cùng ApplicationContext.
}
```

**Chỉ dùng hybrid khi đã xác minh nội dung XML còn lại:** nếu `legacy-rabbit-infrastructure.xml` vẫn khai báo `<rabbit:listener-container>` cũ, thêm `@RabbitListener` có thể tạo duplicate consumer. Cách giảm rủi ro là tách XML thành các phần có chủ sở hữu rõ:

```text
legacy-rabbit-infrastructure.xml  -> CF/admin/template (còn giữ)
legacy-rabbit-listeners.xml       -> listener container cũ (bật ở profile cũ)
PaymentTopologyConfiguration     -> Queue/Exchange/Binding mới (sau cutover)
PaymentListenerConfiguration     -> listener factory + annotation mới
```

**Quy tắc chỉ một owner:** trong cùng ApplicationContext, mỗi bean name có một định nghĩa chủ đích; mỗi listener endpoint logic chỉ nên có **một cách đăng ký**. Có thể nhiều Pod cũ/mới cùng consume queue trong rolling update theo competing consumers, nhưng điều đó phải là **quyết định rollout**, không phải hậu quả bất ngờ của việc import trùng cấu hình.

### 12.1. Bean override bị che giấu

Nếu XML khai báo `paymentTemplate` và Java cũng có `@Bean("paymentTemplate")`, tùy Spring/Boot version có thể lỗi khởi động do trùng bean name hoặc override khi được phép. **Không bật bean overriding chỉ để migration chạy qua**; hãy xóa đúng bean XML, hoặc đặt tên bean Java tạm và inject bằng `@Qualifier` khi thử nghiệm.

### 12.2. RabbitAdmin có thể bị nhân đôi

Nếu XML và Java cùng tạo `RabbitAdmin`, hai admin có thể cùng khai báo tất cả `Queue`/`Exchange`/`Binding` beans do Spring thấy trong context. Với declarations tương đương có thể không lỗi, nhưng với **conditional ownership, multiple brokers hoặc arguments khác** có thể dẫn đến conflict.

Để giữ ownership:

- Xác minh số admin thực tế và connection factory của từng admin.
- Dùng `Declarable.setAdminsThatShouldDeclare(...)` hoặc `explicitDeclarationsOnly` theo yêu cầu, hoặc phân quyền quản lý topology bên ngoài app.
- Với exclusive/anonymous queues, cần đúng connection/admin owner.
- Không chuyển namespace `declared-by` thành “tất cả admins đều khai báo” do quên mapping.

## 13. Cắt chuyển listener mà không chạy hai consumer ngoài ý muốn

### 13.1. Hai chế độ có thể kiểm soát được

**Chế độ legacy:**

```text
XML listener container = ENABLED
Java @RabbitListener   = DISABLED / bean không được tạo
Publisher              = Không thay đổi
Topology owner         = XML/RabbitAdmin cũ
```

**Chế độ Java:**

```text
XML listener container = DISABLED / không import
Java @RabbitListener   = ENABLED
Publisher              = Không thay đổi
Topology owner         = Quyền sở hữu đã chuyển rõ
```

Để thực hiện, có thể dùng `@Profile("rabbit-java-listener")` hoặc `@ConditionalOnProperty` cho **toàn bộ bean listener mới**, đồng thời chỉ import XML listener cũ ở profile còn lại. Đây là điều kiện app tự thiết kế, không có sẵn một property của Spring AMQP tự động “tắt listener XML khi có annotation”.

### 13.2. Annotation trên method và bean điều kiện

Ví dụ:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
    name = "app.messaging.java-listener.enabled",
    havingValue = "true")
class NewPaymentListener {

    private final PaymentAuditService service;

    NewPaymentListener(PaymentAuditService service) {
        this.service = service;
    }

    @RabbitListener(
            id = "paymentListener",
            queues = "payments.completed.q",
            containerFactory = "paymentListenerFactory")
    public void onMessage(String paymentId) {
        service.recordOnce(paymentId);
    }
}
```

**Đây là một cách thay thế `PaymentHandler` ở phần 6**, không thêm nó trong cùng app khi `PaymentHandler` cũng là annotated endpoint. Ngoài ra phải có **cơ chế tương ứng để không nạp XML listener** khi feature flag bật: annotation condition **không** tự tắt XML listener.

Tránh đẩy business flag vào message để “một consumer nhận nhưng tự bỏ qua”: RabbitMQ đã giao delivery cho consumer đó, consumer khác sẽ không nhận cùng delivery chỉ vì handler quyết định skip. Tắt container/không tạo bean đúng cách mới là biện pháp migration.

### 13.3. Triển khai nhiều replica và rolling update

Nếu trong rolling deployment một số Pod dùng XML listener và số khác dùng Java listener cùng queue, chúng là **competing consumers**. Đây có thể là rollout được phép khi:

- Wire contract, converter, ack, retry và idempotency **tương thích**.
- Queue/topology không bị hai version re-declare với arguments khác.
- Không có yêu cầu ordering mà hai version xử lý khác nhau.
- Có rollback/stop drain, metrics theo `version` và quan sát hiệu ứng nghiệp vụ.

Nếu cần so sánh hai phiên bản mà **không muốn Java worker thực sự xử lý message**, không chạy hai consumer cùng queue rồi “quan sát” kết quả: phải dùng **shadow queue khác** có binding phù hợp và bảo đảm shadow worker không thực hiện tác động nghiệp vụ thật.

## 14. Kiểm soát vòng đời container sau khi chuyển

### 14.1. XML bean container và annotation registry

Listener được khai báo bằng bean `SimpleMessageListenerContainer` hoặc namespace có thể quản lý theo bean/group phù hợp với cách parser tạo container. Với `@RabbitListener`, container do infrastructure tạo ra được giữ bởi `RabbitListenerEndpointRegistry`, **không phải Bean thông thường** để inject theo tên:

```java
import org.springframework.amqp.rabbit.listener.RabbitListenerEndpointRegistry;
import org.springframework.stereotype.Service;

@Service
class PaymentListenerControl {
    private final RabbitListenerEndpointRegistry registry;

    PaymentListenerControl(RabbitListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean stop() {
        var container = registry.getListenerContainer("paymentListener");
        if (container == null) {
            return false;
        }
        container.stop();
        return true;
    }

    public boolean start() {
        var container = registry.getListenerContainer("paymentListener");
        if (container == null) {
            return false;
        }
        container.start();
        return true;
    }
}
```

Không gọi `start/stop` từ request public không xác thực. Nếu listener có nhiều replica, registry **chỉ quản lý container trong JVM cục bộ**, không điều khiển tất cả Pod của một Deployment.

### 14.2. @RabbitListener id không phải Queue name

`id="paymentListener"` giúp định danh endpoint trong registry và event/metrics; `queues="payments.completed.q"` là tên queue broker. Không dùng nhầm ID nội bộ khi gọi `getListenerContainer("payments.completed.q")`.

Nếu XML cũ dùng group container, khi chuyển cần kiểm tra cách gắn `group` tại `@RabbitListener` hoặc quản lý nhóm qua registry/scheduler tương đương. Không giả định mọi group bean XML cũ tồn tại dưới cùng tên trong annotation model.

### 14.3. Graceful shutdown và prefetch

Khi tắt Pod listener:

- SMLC/DMLC cố hoàn thành message đang xử lý trong `shutdownTimeout`, theo configuration và container type.
- Nếu Pod bị kill/connection đóng trước ACK, RabbitMQ có thể redeliver.
- `forceStop=true` ở phiên bản hỗ trợ dừng sau current message và requeue prefetched messages chưa xử lý.
- Với `AUTO`, business DB commit rồi mất ACK vẫn có thể nhận lại message; dùng unique business key.

Một migration cấu hình “xanh” nhưng làm quá trình shutdown lâu hơn hoặc requeue nhiều hơn vẫn là thay đổi vận hành cần đo.

## 15. Kịch bản nâng Spring Boot 3.x / Spring AMQP 3.x và 4.x

Không nên đặt bài toán “XML → Java” thành “phải dùng library mới nhất”. Có thể phân giai đoạn:

| Giai đoạn | Spring/Boot | Nhiệm vụ | Acceptance |
| --- | --- | --- | --- |
| A. Baseline | Version cũ đang chạy | Snapshot cấu hình, metrics, behavior | Test request/reply, ack/DLQ, consumer count |
| B. Chỉ cấu hình | **Giữ nguyên version** | XML → Java/annotation từng cụm | Contract và side effects không đổi |
| C. Tách nâng library | Nâng theo BOM tương thích | Jackson, Retry API, JDK, Spring Framework | Compile/test + integration/chaos |
| D. Tùy chọn nâng giao thức | Spring AMQP/RabbitMQ hỗ trợ AMQP 1.0 | Đổi client/protocol nếu thật sự cần | Migration riêng với test cross-protocol |

Spring AMQP 4.0 đưa vào `spring-rabbitmq-client` (RabbitMQ AMQP 1.0 native) và API Jackson 3; **không** có nghĩa bản XML của AMQP 0.9.1 phải được thay hết mới nâng. Chọn BOM của Spring Boot phù hợp; không trộn dependency của 3.x/4.x chỉ vì cùng tên `spring-rabbit`.

Nếu tài liệu cũ đang dùng Spring Retry (`org.springframework.retry.*`), kiểm tra phần **“What's New 4.0”**: framework đã chuyển các tiện ích retry của dự án sang Spring Core Retry. Không dán nguyên code builder API cũ trong lộ trình nâng major version.

## 16. Kế hoạch migration từng bước

### Pha 0 — khóa hành vi và chuẩn bị rollback

1. Xác nhận tất cả exchanges/queues/bindings, types/arguments/policies từ RabbitMQ Management hoặc IaC.
2. Chốt phiên bản Spring AMQP/Boot, converter và retry library hiện tại.
3. Đo baseline: queue ready/unacked, publish/ack rates, redelivery, DLQ, listener success/error, p95/p99.
4. Chụp lại **đường đi message** và các lỗi đã biết như consumer retry, late reply, lost confirm.
5. Tạo integration test có RabbitMQ thật và DB nếu nghiệp vụ thay đổi dữ liệu.
6. Thiết kế feature flag/profile để có thể **quay lại XML listener** nếu cần.

### Pha 1 — chuyển topology và producer trước

1. Chuyển queue/exchange/binding XML sang `@Bean` **giữ nguyên broker names và arguments**.
2. Đảm bảo **một chủ sở hữu topology**; không tạo thêm admin không kiểm soát.
3. Chuyển template XML sang bean Java/Boot properties; so sánh exchange, routing key, converter, mandatory, confirms/returns.
4. Chưa chuyển listener; kiểm tra tất cả message vẫn route tới queue cũ.
5. Canary và theo dõi publisher returns/errors; rollback nếu declaration mismatch.

### Pha 2 — chuyển listener với contract cố định

1. Tạo `SimpleRabbitListenerContainerFactory` tương đương XML (type, concurrency, prefetch, ACK, retry).
2. Chuyển một POJO/adapter sang `@RabbitListener` **ở môi trường test/canary**.
3. **Tắt/không import XML listener** cũ của endpoint đó, không chỉ thêm annotation.
4. Gửi cùng tập payload đã kiểm thử: text, JSON, invalid, duplicate, delayed.
5. Kiểm tra ACK/NACK/requeue/DLQ, DB commit, method argument converter và consumer count.
6. Thực hiện rolling update có kiểm soát; giữ tương thích message schema giữa Pod cũ/mới.

### Pha 3 — làm sạch sau khi đã ổn định

1. Gỡ XML bean/listener đã thay thế và import không cần thiết.
2. Không gỡ các XML bean **chưa migrate** chỉ để giảm số dòng.
3. Kiểm tra bean name collisions, số RabbitAdmin, registry ID và lifecycle control.
4. Duy trì tài liệu mapping, runbook rollback, owner topology và kiểm thử.
5. Sau khi hoàn tất cú pháp migration, mới cân nhắc refactor converter, retry, queue type hoặc nâng major version.

## 17. Kiểm thử regression xác minh “cùng hành vi”

Một unit test `new PaymentHandler().handle(...)` không đủ: nó bỏ qua broker routing, message conversion, container ACK và auto declaration. Dùng nhiều cấp độ kiểm thử:

| Test | Với XML cũ | Với Java mới | Điều cần bằng nhau |
| --- | --- | --- | --- |
| Bootstrapping | Nạp XML | Nạp Java config | Không có bean trùng, context startup |
| Topology | Admin khai báo | Admin khai báo | Exchange type, queue args, bindings |
| Publish | Template gửi | Template gửi | Exchange/key, contentType/headers, body |
| Consumer count | Container XML | Annotation factory | Số consumer per replica theo cấu hình |
| Happy path | Handler POJO | `@RabbitListener` | Nghiệp vụ được commit một lần |
| Bad JSON/schema | Converter/adapter lỗi | Annotation converter lỗi | Không commit, retry/DLQ đúng |
| Temporary DB error | Retry policy cũ | Retry policy mới | Attempt/backoff và ACK không thay đổi |
| Crash sau commit | Broker redeliver | Broker redeliver | Idempotency, không side effect trùng |
| RPC reply | XML template/reply listener | Java template/reply listener | Correlation/reply timeout giữ nguyên |
| Startup queue thiếu | SMLC/DMLC config | Factory config | Fatal/recovery policy đúng |
| Shutdown | XML container stop | Registry stop | Draining/requeue/trạng thái cuối |
| Multiple replica | XML pods | Java pods | Queue load sharing, không xử lý trùng business |

### 17.1. Testcontainers integration skeleton

Bộ test dưới dùng Spring Boot 3.x/Spring AMQP 3.x, JUnit 5 và **Testcontainers 1.x** (package `org.testcontainers.containers.RabbitMQContainer`). Với Testcontainers 2.x, artifact/package thay đổi; đừng trộn phụ thuộc 1.x/2.x.

```java
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@Testcontainers
@SpringBootTest
class PaymentMessagingMigrationIT {

    @Container
    static RabbitMQContainer broker =
            new RabbitMQContainer("rabbitmq:4.1-management");

    @DynamicPropertySource
    static void rabbitProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", broker::getHost);
        registry.add("spring.rabbitmq.port", broker::getAmqpPort);
        registry.add("spring.rabbitmq.username", () -> "guest");
        registry.add("spring.rabbitmq.password", () -> "guest");
    }

    @Autowired RabbitTemplate rabbitTemplate;

    @Test
    void contextHasPublisher() {
        assertNotNull(rabbitTemplate);
        // Thêm assertions topology + send/consume thật theo business.
    }
}
```

Đây là **skeleton**: các beans cần nằm trong test application context, listener business service cần được cung cấp, không đồng thời kích hoạt hai endpoint cùng queue. Test thực tế nên dùng Awaitility để chờ DB/state commit; `@RabbitListenerTest`/`spring-rabbit-test` hữu ích cho test invocation, nhưng không thay thế broker thật khi muốn đo ACK/DLQ/confirm.

### 17.2. Kiểm tra số listener endpoint và factory thực

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.amqp.rabbit.listener.RabbitListenerEndpointRegistry;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class PaymentListenerRegistrationTest {

    @Autowired RabbitListenerEndpointRegistry registry;

    @Test
    void containsExactlyOnePaymentEndpoint() {
        var container = registry.getListenerContainer("paymentListener");
        assertNotNull(container);
        assertTrue(registry.getListenerContainerIds()
                .contains("paymentListener"));
    }
}
```

Ví dụ trên chỉ kiểm tra **annotation registry** và cần chạy trong Spring test context; nó **không phát hiện** một XML container khác cũng đang subscribe cùng queue. Cần đọc thêm số active consumers từ broker/đếm beans listener hoặc test gửi message để chứng minh chỉ một endpoint đúng nghĩa. Trên Kubernetes, còn phải cộng consumers của các Pod cũ/new theo rollout.

### 17.3. Test lỗi chuyển đổi và DLQ

1. Gửi payload hợp lệ qua cùng exchange/key, xác minh handler mới nhận và DB commit.
2. Gửi payload không hợp lệ (contentType/JSON/schema), xác minh không commit và DLX/DLQ hoạt động **theo policy cũ**.
3. Cố tình lỗi DB rồi phục hồi, đo retry/ACK/redelivery và business idempotency.
4. Gửi duplicate eventId/business key, không nhân đôi side effects.
5. Kiểm tra publisher returned khi routing key sai nếu bật mandatory returns.
6. Nếu có transaction DB, ngắt consumer sau commit trước ACK; assert redelivery vẫn lặp an toàn.
7. Chạy với XML test profile và Java test profile trên **hai application context tách biệt**, so sánh kết quả.

**Không chạy song song hai profile đang dùng cùng broker queue và cùng database trừ khi test đã chủ ý kiểm tra competing consumers.** Khi đo behavior parity, tách queue vhost/test containers để kết quả của phiên bản này không làm nhiễu phiên bản kia.

## 18. Chẩn đoán sau migration

| Triệu chứng | Nguyên nhân dễ gặp | Kiểm tra trước |
| --- | --- | --- |
| Hai lần xử lý mỗi event | Cả XML listener và `@RabbitListener` cùng tồn tại, hoặc publisher tạo duplicate | Bean/container count, eventId, inbox |
| Consumer count tăng gấp đôi | Listener registration trùng hoặc rolling surge | XML import, registry IDs, Pod versions |
| Lỗi `PRECONDITION_FAILED` khi startup | Queue arguments/type thay đổi | RabbitMQ queue properties vs `QueueBuilder` |
| Không có message vào listener | Queue name nhầm bean ID, sai vhost/binding | `queues` broker name, topology |
| Bean definition conflict | XML và Java định nghĩa cùng ID | Bean registry, `@ImportResource`, Boot overriding |
| Chạy được nhưng JSON DTO lỗi | Converter/type mapper khác | ContentType, type headers, DTO signature |
| Message bị requeue mãi | Advice/recoverer hoặc `defaultRequeueRejected` bị bỏ | Retry policy, exception types, DLX |
| Message “biến mất” khi lỗi | Vô tình đổi `AUTO` → `NONE` hoặc reject không DLX | ACK mode, queue DLX, broker log |
| Monitoring không còn thấy listener | Registry ID thay bean ID | `RabbitListenerEndpointRegistry` |
| Startup lâu/consumer không active | `autoStartup`/`missingQueuesFatal` khác XML | Factory properties, broker queue existence |
| DB API quá tải | Concurrency × replicas tăng | SMLC vs DMLC, prefetch, Hikari pool |
| RPC timeout sau chuyển | Quên reply queue/container/correlation | `replyAddress`, reply listener, Direct Reply-To |
| Không có topology mới | Chỉ tạo `Queue` bean, thiếu `RabbitAdmin`/permissions | Admin active, vhost, connect lifecycle |
| Test chạy được nhưng production lỗi | Test không dùng broker thật hoặc Boot-specific config khác | Testcontainers, profiles, secrets |
| Upgrade 4.x compilation lỗi | Spring Core Retry/Jackson 3 API khác | Version BOM/migration notes |

### 18.1. Có thể kiểm tra runtime theo những câu hỏi nào?

- Có **bao nhiêu `RabbitAdmin`** và chúng kết nối broker/vhost nào?
- Queue đang thuộc classic/quorum, durable, DLX arguments nào?
- `RabbitListenerEndpointRegistry.getListenerContainerIds()` chứa những endpoint nào?
- Số broker consumers trên `payments.completed.q` có tương ứng số Pod × concurrency?
- Message header/contentType trước và sau migration có giống không?
- Khi listener throw exception, broker nhìn thấy ACK, NACK, redelivery hay DLQ?
- Publisher confirms/returns có được cấu hình trên template thực sự đang gửi không?
- Khi shutdown, còn unacked hoặc DLQ tăng không?

## 19. Những anti-pattern trong chuyển đổi XML → Java

**Xóa XML rồi tự tạo lại topology theo tên Java method.** Bean name không phải broker name; thay queue/exchange names có thể làm message cũ bị kẹt.

**Thêm @RabbitListener nhưng giữ nguyên <rabbit:listener-container>.** Hai consumer cạnh tranh trên cùng queue, dễ làm metric và test bị lệch.

**Cùng lúc đổi SMLC sang DMLC và chỉnh concurrency.** Không còn là migration cú pháp; có thể thay thread model/recovery và độ song song.

**Chuyển sang annotation bindings cho mọi topology phức tạp.** Có thể làm mất conditional admin, DLX hoặc resource ownership; `@Bean` và IaC vẫn có chỗ đứng.

**Tưởng Boot auto-configuration luôn áp cho bean custom.** Một factory/template tự tạo có thể không nhận toàn bộ `spring.rabbitmq.*` properties của factory mặc định; phải cấu hình/cài Boot configurer thích hợp.

**Bật Bean overriding để bỏ qua trùng cấu hình.** Che giấu ownership conflict và khiến kết quả phụ thuộc thứ tự nạp configuration.

**Chuyển default Jackson converter mà không test type headers.** Thay đổi class được deserialize hoặc lỗi trước method listener, ảnh hưởng retry/DLQ.

**Nâng Spring AMQP 4.x cùng PR với XML migration mà không tách rollback.** Khi lỗi, khó xác định do code config, Spring Framework 7, Jackson 3, Retry API hay client protocol.

**Giả định retry/requeue mặc định giữ nguyên.** Chỉ một `defaultRequeueRejected`/advice chain bị bỏ cũng đủ làm poison message loop hoặc mất message.

**Chỉ unit test handler method.** Không thấy exchange binding, RabbitAdmin, converter, ACK, reply container, confirms và lifecycle thực tế.

**Tự đổi queue classic sang quorum trong QueueBuilder khi “refactor”.** Queue type không đổi tại chỗ; có thể làm startup fail.

**Cắt XML nhưng quên auth/TLS/vhost/metrics.** Việc method annotate chạy được localhost không chứng minh production tương đương.

## 20. Checklist trước và sau cutover

- [ ] Có lý do rõ ràng để migrate; nếu XML vẫn phù hợp, không ép chuyển toàn bộ?
- [ ] Đã **inventory** connection factory, admin, template, topology, listeners, converter, ACK, retry, DLX, RPC, metrics và profiles?
- [ ] Đã chốt đây là **thay cú pháp**, không đồng thời đổi major version, protocol hoặc queue type?
- [ ] Mọi queue/exchange/binding giữ nguyên broker name, durability, arguments và routing keys?
- [ ] Bean ID Java và broker resource name được đối chiếu tường minh?
- [ ] Có đúng **một topology owner**; nhiều admin/conditional declarations đã xử lý?
- [ ] Có đúng **một listener endpoint logic** mỗi app instance; không bật XML và annotation trùng?
- [ ] Container type SMLC/DMLC, concurrency, prefetch, ACK, retry/backoff/recoverer, channel transaction và startup flag tương đương?
- [ ] Message converter, contentType/charset, JSON type mapper và trusted packages được giữ đúng?
- [ ] `RabbitTemplate` có exchange/routing key mặc định, mandatory, returns, confirms và RPC reply timeout/queue như cũ?
- [ ] `@RabbitListener` có ID ổn định, containerFactory đúng, và registry/lifecycle management được điều chỉnh?
- [ ] Spring Boot auto-configuration và bean custom có được kiểm tra để tránh chồng cấu hình?
- [ ] Đã thử payload hợp lệ, lỗi converter, DB failure, retry/DLQ, redelivery, RPC và shutdown trên RabbitMQ thật?
- [ ] Có dashboard so sánh throughput, p95/p99, queue ready/unacked, redelivery, DLQ, consumer counts và unique business effects?
- [ ] Có kế hoạch feature flag/profile, rollback XML và dừng listener mới đúng cách?
- [ ] Khi nâng Spring AMQP 4.x/Jackson 3/Spring Core Retry, có PR/test migration riêng?
- [ ] Đã dọn XML cũ **chỉ sau** khi cutover ổn định, không xóa những bean vẫn được dùng?

**Kết luận:** chuyển từ Spring AMQP XML namespace sang Java/annotation chỉ có giá trị khi giúp cấu hình rõ ràng và bảo trì tốt hơn **mà không làm thay đổi vô ý semantics của hệ thống message**. Hãy kiểm kê trước, chuyển từng lớp, giữ ownership topology và chỉ một listener đăng ký, đối chiếu converter/ACK/retry/transaction, chạy test broker thật và triển khai có rollback. `@Bean`, `@EnableRabbit` và `@RabbitListener` không thay thế được thiết kế publisher confirms, idempotency, retry/DLQ và observability — chúng chỉ là một cách biểu diễn cấu hình khác.

## Tài liệu tham khảo chính thức

- [Spring AMQP — Configuring the Broker](https://docs.spring.io/spring-amqp/reference/amqp/broker-configuration.html): XML namespace, `RabbitAdmin`, declarables, conditional declarations và mapping Java.
- [Spring AMQP — Asynchronous Consumer](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): `<rabbit:listener-container>`, `MessageListenerAdapter`, container types, consumer behavior.
- [Spring AMQP — Enable Listener Endpoint Annotations](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable.html): `@EnableRabbit`, `rabbitListenerContainerFactory`, `@RabbitListener` và XML `<rabbit:annotation-driven/>`.
- [Spring AMQP — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html): `queues`/`queuesToDeclare`/`bindings`, declaration annotation.
- [Spring AMQP — Listener Container Attributes](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): bảng property Java với namespace attributes, SMLC/DMLC, ACK/prefetch/retry/lifecycle.
- [Spring AMQP — Container Management](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/container-management.html): `RabbitListenerEndpointRegistry`, start/stop và container ID.
- [Spring AMQP — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): converter/type headers/serialization và phiên bản Jackson.
- [Spring AMQP — Transactions](https://docs.spring.io/spring-amqp/reference/amqp/transactions.html): `channelTransacted`, transaction synchronization và giới hạn XA.
- [Spring AMQP — Template](https://docs.spring.io/spring-amqp/reference/amqp/template.html): `RabbitTemplate`, publisher confirms/returns, retries và request–reply.
- [Spring AMQP 4.0 — What's New](https://docs.spring.io/spring-amqp/reference/4.0/whats-new.html): Spring Framework 7, Jackson 3, Spring Core Retry, RabbitMQ AMQP 1.0 module mới.
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): `spring.rabbitmq.*`, auto-configured connection/template/listener factory, custom configurer.
- [Spring AMQP — Testing](https://docs.spring.io/spring-amqp/reference/testing.html): `spring-rabbit-test`, `@RabbitListenerTest`, test utilities và kiểm thử cùng broker.
