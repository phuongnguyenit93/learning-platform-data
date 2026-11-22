# JmsListenerConfigurer và đăng ký endpoint bằng chương trình

## Mục tiêu

Spring JMS có thể đăng ký listener bằng annotation `@JmsListener` hoặc bằng cấu hình Java. `JmsListenerConfigurer` là callback cho phép ứng dụng tùy chỉnh hạ tầng listener và đăng ký các `JmsListenerEndpoint` trực tiếp thông qua `JmsListenerEndpointRegistrar`.

Đăng ký bằng chương trình hữu ích khi danh sách destination đến từ cấu hình, khi mỗi endpoint cần một listener hoặc container factory riêng, hoặc khi ứng dụng muốn tạo endpoint theo một quy tắc cấu hình tại thời điểm khởi động.

Sau bài này, bạn có thể:

- Giải thích vai trò của `@EnableJms`, `JmsListenerConfigurer` và `JmsListenerEndpointRegistrar`.
- Tạo một `SimpleJmsListenerEndpoint` và gắn `MessageListener`.
- Phân biệt `SimpleJmsListenerEndpoint` với `MethodJmsListenerEndpoint`.
- Cấu hình ID, destination, selector, subscription và concurrency.
- Chọn default `JmsListenerContainerFactory` hoặc factory riêng cho từng endpoint.
- Hiểu `JmsListenerEndpointRegistry` tạo và quản lý listener container như thế nào.
- Kết hợp endpoint đăng ký bằng chương trình với endpoint `@JmsListener`.
- Tùy chỉnh argument binding, conversion và validation cho method endpoint.
- Theo dõi lifecycle, transaction và lỗi của endpoint.
- Chạy ví dụ Spring Boot với embedded ActiveMQ Artemis.

## 1. Listener endpoint là gì?

Trong Spring JMS, listener endpoint mô tả một nơi nhận message và cách Spring xử lý message ở đó. Endpoint là metadata cấu hình; listener container mới là thành phần kết nối với JMS provider, tạo consumer và gọi listener.

Các phần chính:

| Thành phần | Vai trò |
|---|---|
| `JmsListenerEndpoint` | Mô tả một endpoint JMS và cách cấu hình listener container cho endpoint đó. |
| `JmsListenerContainerFactory` | Tạo listener container từ endpoint. |
| `MessageListenerContainer` | Quản lý consumer, session, thread, transaction, recovery và việc dispatch message. |
| `JmsListenerEndpointRegistrar` | Nhận endpoint và factory trong giai đoạn cấu hình. |
| `JmsListenerEndpointRegistry` | Tạo, lưu và quản lý lifecycle của các listener container được đăng ký. |
| `JmsListenerConfigurer` | Callback cho Spring bean tùy chỉnh registrar và đăng ký endpoint bằng chương trình. |

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["Spring Application Context"] --> B["@EnableJms"]
    B --> C["JmsListenerAnnotationBeanPostProcessor"]
    C --> D["JmsListenerConfigurer callback"]
    D --> E["JmsListenerEndpointRegistrar"]
    E --> F["JmsListenerEndpoint"]
    E --> G["JmsListenerContainerFactory"]
    F --> H["JmsListenerEndpointRegistry"]
    G --> H
    H --> I["MessageListenerContainer"]
    I --> J["JMS Provider / Broker"]
    J --> I
    I --> K["MessageListener / POJO method"]
~~~

Endpoint xác định destination và listener. Factory cung cấp cách tạo container. Registry giữ container và quản lý vòng đời của nó cùng application context.

## 2. JmsListenerConfigurer và @EnableJms

`JmsListenerConfigurer` nằm trong package:

~~~java
org.springframework.jms.annotation.JmsListenerConfigurer
~~~

Đây là functional interface với một callback:

~~~java
void configureJmsListeners(JmsListenerEndpointRegistrar registrar);
~~~

Spring gọi callback này trong quá trình khởi tạo hạ tầng listener. Ứng dụng dùng registrar để:

- Đặt listener container factory mặc định.
- Chọn factory mặc định bằng bean name.
- Đăng ký một hoặc nhiều endpoint.
- Cấu hình `MessageHandlerMethodFactory` cho endpoint dùng method invocation.

Ví dụ khung cấu hình:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(JmsListenerEndpointRegistrar registrar) {
        // Đăng ký endpoint ở đây.
    }
}
~~~

`@EnableJms` bật annotation-driven listener infrastructure. Nó đăng ký processor xử lý `@JmsListener` và một `JmsListenerEndpointRegistry` mặc định.

Ngay cả khi không dùng annotation `@JmsListener`, vẫn có thể dùng `@EnableJms` cùng `JmsListenerConfigurer` để chỉ đăng ký endpoint bằng chương trình.

### Không nhầm configurer với container

`JmsListenerConfigurer` không trực tiếp nhận message. Nó chỉ khai báo endpoint và cách tạo container trong giai đoạn cấu hình.

`JmsListenerEndpointRegistrar` cũng không phải listener đang chạy. Nó là helper nhận endpoint và chuyển chúng tới registry.

Message thực tế được nhận bởi consumer do listener container quản lý.

## 3. JmsListenerEndpointRegistrar

Registrar là helper để đăng ký endpoint với registry và lựa chọn factory tạo container.

Các API thường dùng:

| Phương thức | Mục đích |
|---|---|
| `registerEndpoint(endpoint)` | Đăng ký endpoint bằng factory mặc định. |
| `registerEndpoint(endpoint, factory)` | Đăng ký endpoint với factory được chỉ định. |
| `setContainerFactory(factory)` | Đặt factory mặc định cho endpoint chưa chỉ định factory. |
| `setContainerFactoryBeanName(name)` | Đặt bean name của factory mặc định; lookup qua BeanFactory. |
| `setEndpointRegistry(registry)` | Chỉ định registry quản lý endpoint. |
| `setMessageHandlerMethodFactory(factory)` | Cấu hình method argument binding/invocation cho method endpoint. |

Ví dụ chọn factory mặc định theo bean name:

~~~java
@Override
public void configureJmsListeners(JmsListenerEndpointRegistrar registrar) {
    registrar.setContainerFactoryBeanName("jmsListenerContainerFactory");

    SimpleJmsListenerEndpoint endpoint = new SimpleJmsListenerEndpoint();
    endpoint.setId("ordersEndpoint");
    endpoint.setDestination("orders.queue");
    endpoint.setMessageListener(message -> {
        // Xử lý message.
    });

    registrar.registerEndpoint(endpoint);
}
~~~

Trong ví dụ, `jmsListenerContainerFactory` phải là một bean `JmsListenerContainerFactory` có tên tương ứng. Nếu endpoint không chỉ định factory riêng, registrar dùng factory mặc định.

Có thể truyền factory trực tiếp:

~~~java
registrar.registerEndpoint(endpoint, ordersListenerFactory);
~~~

Cách này hữu ích khi Queue và Topic cần cấu hình khác nhau, hoặc các nhóm listener có transaction, concurrency, converter hay acknowledgement policy riêng.

### Factory mặc định cho @JmsListener

Nếu ứng dụng có endpoint `@JmsListener` không khai báo `containerFactory`, Spring cần một factory mặc định. Theo convention, infrastructure tìm bean tên `jmsListenerContainerFactory`.

Có thể đặt factory mặc định qua registrar trong `JmsListenerConfigurer`. Endpoint đã truyền factory riêng sẽ dùng factory đó.

## 4. SimpleJmsListenerEndpoint

`SimpleJmsListenerEndpoint` là implementation đơn giản của `JmsListenerEndpoint`. Nó nhận trực tiếp một đối tượng `jakarta.jms.MessageListener`.

Ví dụ:

~~~java
SimpleJmsListenerEndpoint endpoint = new SimpleJmsListenerEndpoint();
endpoint.setId("auditEndpoint");
endpoint.setDestination("audit.queue");
endpoint.setMessageListener(message -> {
    System.out.println("received JMS message");
});
registrar.registerEndpoint(endpoint);
~~~

Các thuộc tính kế thừa từ `AbstractJmsListenerEndpoint`:

| Setter | Ý nghĩa |
|---|---|
| `setId(id)` | Đặt ID ổn định để registry quản lý và truy xuất container. |
| `setDestination(name)` | Đặt tên Queue hoặc Topic. |
| `setSelector(expression)` | Đặt JMS message selector. |
| `setSubscription(name)` | Đặt tên durable subscription khi dùng Topic. |
| `setConcurrency(value)` | Đặt concurrency cho listener nếu container hỗ trợ. |
| `setMessageListener(listener)` | Đặt callback JMS thực hiện xử lý message. |

### MessageListener nhận JMS Message thô

Với simple endpoint, listener nhận đối tượng `jakarta.jms.Message`:

~~~java
endpoint.setMessageListener(message -> {
    if (message instanceof TextMessage textMessage) {
        try {
            System.out.println(textMessage.getText());
        }
        catch (JMSException ex) {
            throw new IllegalStateException("Cannot read TextMessage", ex);
        }
    }
});
~~~

Bạn tự quyết định cách đọc loại message và xử lý JMS headers/properties. Đây là API ở mức JMS thấp, phù hợp khi cần toàn quyền kiểm soát message hoặc khi listener hiện có đã implement `MessageListener`.

Nếu muốn delegate nhận String, Map hoặc POJO đã convert, hãy cấu hình converter/adapter phù hợp hoặc dùng method endpoint để tận dụng argument resolution.

## 5. MethodJmsListenerEndpoint

`MethodJmsListenerEndpoint` cũng là một implementation của `JmsListenerEndpoint`, nhưng nó mô tả một method trên một bean cần được gọi khi message tới.

Các thông tin cần thiết:

- Bean instance cần gọi.
- `java.lang.reflect.Method` cần thực thi.
- `MessageHandlerMethodFactory` tạo invocation handler và argument resolvers.
- Destination, ID và các thuộc tính endpoint kế thừa.

Ví dụ khung:

~~~java
MethodJmsListenerEndpoint endpoint = new MethodJmsListenerEndpoint();
endpoint.setId("orderMethodEndpoint");
endpoint.setDestination("orders.queue");
endpoint.setBean(orderService);
endpoint.setMethod(OrderService.class.getMethod("processOrder", String.class));
endpoint.setMessageHandlerMethodFactory(messageHandlerMethodFactory);
registrar.registerEndpoint(endpoint);
~~~

Bean đích:

~~~java
public class OrderService {

    public void processOrder(String orderId) {
        System.out.println("order=" + orderId);
    }
}
~~~

`MethodJmsListenerEndpoint` dùng `MessagingMessageListenerAdapter` để chuyển message thành tham số method và gọi bean. Điều này gần với cơ chế của `@JmsListener`.

Nếu bean được proxy bởi AOP, có thể cần cung cấp method cụ thể trên target class bằng `setMostSpecificMethod` theo cấu trúc proxy. Method và bean phải tương thích; method phải có thể được invocation infrastructure gọi.

### MessageHandlerMethodFactory

`MessageHandlerMethodFactory` cung cấp cơ chế tạo `InvocableHandlerMethod`, bao gồm argument resolver, conversion và validation.

Mặc định, Spring dùng `DefaultMessageHandlerMethodFactory`. Có thể tùy chỉnh để thêm validator hoặc converter:

~~~java
@Bean
DefaultMessageHandlerMethodFactory jmsHandlerMethodFactory(
        Validator validator) {

    DefaultMessageHandlerMethodFactory factory =
            new DefaultMessageHandlerMethodFactory();
    factory.setValidator(validator);
    return factory;
}
~~~

Sau đó cấu hình factory cho registrar và endpoint:

~~~java
registrar.setMessageHandlerMethodFactory(jmsHandlerMethodFactory);
endpoint.setMessageHandlerMethodFactory(jmsHandlerMethodFactory);
~~~

Method endpoint có thể nhận payload, raw JMS `Message`, JMS `Session`, Spring `Message<?>`, `@Header`, `@Headers` và tham số được hỗ trợ khác. Một tham số payload có thể khai báo rõ bằng `@Payload`; `@Valid` có thể kích hoạt validation nếu validator đã được cấu hình.

## 6. Simple endpoint và Method endpoint khác nhau thế nào?

| Tiêu chí | SimpleJmsListenerEndpoint | MethodJmsListenerEndpoint |
|---|---|---|
| Đầu vào listener | JMS `MessageListener` | Bean và method cụ thể |
| Cách gọi | Gọi `onMessage(Message)` | Dùng `MessagingMessageListenerAdapter` và method invocation |
| Payload conversion | Listener tự đọc message hoặc tự dùng converter | Có argument resolution và conversion |
| Header binding | Listener tự đọc JMS headers/properties | Có thể dùng `@Header` và `@Headers` |
| Validation | Tự gọi validation trong listener | Có thể cấu hình qua `MessageHandlerMethodFactory` |
| Độ phức tạp | Ít cấu hình, kiểm soát trực tiếp | Linh hoạt hơn cho POJO method |
| Phù hợp | Listener JMS hiện có hoặc logic raw message | POJO, method signature, conversion và validation |

Chọn `SimpleJmsListenerEndpoint` khi đã có một `MessageListener` và muốn đăng ký nó theo cấu hình. Chọn `MethodJmsListenerEndpoint` khi muốn Spring quản lý việc gọi một method của bean với các tham số đã bind.

## 7. Đặt ID, destination, selector và concurrency

### ID endpoint

Mỗi endpoint nên có ID duy nhất trong cùng registry:

~~~java
endpoint.setId("billingOrdersEndpoint");
~~~

ID được dùng để xác định listener container:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("billingOrdersEndpoint");
~~~

Đặt ID có ý nghĩa giúp log, metrics và thao tác vận hành dễ theo dõi. Nếu không đặt, endpoint có thể được cấp ID mặc định, nhưng ID tường minh thuận tiện hơn cho quản lý.

Không đăng ký hai endpoint cùng ID trong một registry. Hãy tạo ID ổn định, duy nhất và không phụ thuộc vào dữ liệu không được kiểm soát.

### Destination

`setDestination("orders.queue")` nhận tên destination dạng String. Listener container dùng DestinationResolver của factory để phân giải tên thành Queue hoặc Topic.

Domain phải khớp với destination thực tế:

- Queue dùng point-to-point domain.
- Topic dùng publish/subscribe domain.
- Nếu dùng factory riêng, cấu hình `pubSubDomain` trên factory tương ứng.

Tên String không tự quyết định Queue hay Topic.

### Message selector

Selector là biểu thức JMS áp dụng trên header/property của message:

~~~java
endpoint.setSelector("eventType = 'OrderCreated'");
~~~

Chỉ message có property `eventType` phù hợp mới được giao cho consumer. Selector không truy vấn JSON body. Producer cần đặt property đúng kiểu và tên.

### Concurrency

Có thể đặt concurrency theo chuỗi:

~~~java
endpoint.setConcurrency("3-8");
~~~

Ý nghĩa thường là mức thấp nhất và cao nhất của consumer, nếu container hỗ trợ scaling. Một giá trị như `"5"` đặt giới hạn trên là 5 và mức thấp nhất là 1.

Khả năng scale thực tế phụ thuộc loại container và provider. Với `DefaultMessageListenerContainer`, concurrency có thể điều chỉnh số consumer trong phạm vi được cấu hình. Hãy cân đối với năng lực database, downstream và broker.

### Durable subscription

Với Topic, endpoint có thể đặt tên subscription:

~~~java
endpoint.setSubscription("inventorySubscription");
~~~

Tên này chỉ là một phần của cấu hình durable subscription. Listener container còn cần pub-sub domain, durable subscription được bật và client ID/provider settings thích hợp. Đặt subscription name một mình không biến endpoint Queue thành durable Topic subscription.

## 8. Chọn container factory cho endpoint

Endpoint chỉ mô tả nơi nhận và listener. Factory tạo container và quyết định phần lớn hành vi vận hành.

Ví dụ factory:

~~~java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-6");
    return factory;
}
~~~

Có thể đăng ký một endpoint bằng factory mặc định:

~~~java
registrar.registerEndpoint(endpoint);
~~~

Hoặc chọn factory riêng:

~~~java
registrar.registerEndpoint(endpoint, topicListenerFactory);
~~~

Một ứng dụng dùng cả Queue và Topic có thể định nghĩa:

- Queue factory với `pubSubDomain=false`.
- Topic factory với `pubSubDomain=true`.
- Factory giao dịch cho listener cần rollback.
- Factory không transacted cho listener có policy khác.

Không giả định các endpoint dùng chung một factory sẽ tự có destination domain khác nhau theo tên.

## 9. JmsListenerEndpointRegistry và lifecycle

`JmsListenerEndpointRegistry` tạo listener container từ endpoint và factory đã đăng ký. Nó cũng quản lý lifecycle của các container đó trong application context.

Các API thường dùng:

| API | Mục đích |
|---|---|
| `getListenerContainer(id)` | Lấy container theo endpoint ID. |
| `getListenerContainerIds()` | Lấy tập ID container đã đăng ký. |
| `getListenerContainers()` | Lấy collection các container đang được registry quản lý. |
| `start()` | Khởi động các container theo lifecycle của registry. |
| `stop()` | Dừng các container theo lifecycle của registry. |
| `isRunning()` | Kiểm tra registry đang chạy hay không. |

Ví dụ:

~~~java
@Autowired
private JmsListenerEndpointRegistry registry;

public void inspectListeners() {
    for (String id : registry.getListenerContainerIds()) {
        MessageListenerContainer container =
                registry.getListenerContainer(id);
        System.out.println(id + " -> " + container);
    }
}
~~~

Các listener container do registry tạo không phải bean riêng trong application context và không thể autowire trực tiếp như bean thông thường. Muốn quản lý chúng, hãy truy cập qua registry bằng ID.

### Đăng ký lúc khởi động và đăng ký runtime

`JmsListenerConfigurer` là nơi phù hợp để đăng ký endpoint trong giai đoạn cấu hình application context. Registrar gom các endpoint và registry tạo container trong lifecycle khởi động.

Nếu cần tạo một endpoint sau khi ứng dụng đã chạy, có thể dùng API của registry:

~~~java
registry.registerListenerContainer(endpoint, containerFactory, true);
~~~

Tham số cuối `true` yêu cầu container khởi động ngay. Khi đăng ký runtime, cần kiểm soát ID duy nhất, destination hợp lệ, quyền truy cập và vòng đời container. Không tạo endpoint mới theo từng message hoặc từng HTTP request nếu không có chính sách giới hạn rõ ràng; số consumer/container có thể tăng không kiểm soát.

Registry quản lý start/stop và destroy. Khi ứng dụng shutdown, các container được registry quản lý sẽ được dừng theo lifecycle.

## 10. Kết hợp đăng ký chương trình với @JmsListener

Một ứng dụng có thể dùng đồng thời:

- `@JmsListener` cho endpoint cố định, đơn giản.
- `JmsListenerConfigurer` cho endpoint sinh từ cấu hình hoặc danh sách destination.

Ví dụ annotation:

~~~java
@Component
public class AuditListener {

    @JmsListener(destination = "audit.queue")
    public void receive(String event) {
        System.out.println("audit=" + event);
    }
}
~~~

Đồng thời, configurer đăng ký endpoint:

~~~java
@Override
public void configureJmsListeners(JmsListenerEndpointRegistrar registrar) {
    SimpleJmsListenerEndpoint endpoint = new SimpleJmsListenerEndpoint();
    endpoint.setId("dynamicOrdersEndpoint");
    endpoint.setDestination("orders.queue");
    endpoint.setMessageListener(orderMessageListener);
    registrar.registerEndpoint(endpoint);
}
~~~

Cả hai loại endpoint đều được quản lý bởi `JmsListenerEndpointRegistry` và sử dụng container factory tương ứng.

Nếu muốn bỏ hoàn toàn annotation, vẫn có thể chỉ dùng `@EnableJms` và `JmsListenerConfigurer`. Cần có registrar/registry infrastructure để tạo listener container.

## 11. Đăng ký nhiều endpoint từ cấu hình

Một trường hợp thường gặp là danh sách destination đến từ application properties hoặc cấu hình triển khai. Có thể lặp qua danh sách đã được kiểm tra và tạo một endpoint cho mỗi destination.

Ví dụ minh họa:

~~~java
@Override
public void configureJmsListeners(JmsListenerEndpointRegistrar registrar) {
    for (String queueName : configuredQueues) {
        SimpleJmsListenerEndpoint endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId("queue-" + queueName);
        endpoint.setDestination(queueName);
        endpoint.setMessageListener(message -> process(queueName, message));
        registrar.registerEndpoint(endpoint);
    }
}
~~~

Mỗi endpoint cần:

- ID duy nhất.
- Destination hợp lệ.
- Listener có thể xử lý loại message nhận được.
- Factory phù hợp với Queue/Topic.
- Concurrency và transaction policy phù hợp với tải.

Danh sách destination nên đến từ cấu hình được kiểm soát. Không lấy tùy ý destination từ request bên ngoài rồi đăng ký listener, vì thao tác đó có thể mở quyền consume tới queue/topic mà service không được phép truy cập.

Nếu một danh sách chứa cả Queue và Topic, hãy mang theo domain trong cấu hình và đăng ký với factory đúng domain. Không suy luận loại destination từ hậu tố tên.

## 12. Tùy chỉnh method binding, conversion và validation

Với `MethodJmsListenerEndpoint`, Spring dùng `MessageHandlerMethodFactory` để tạo cơ chế gọi method. Factory mặc định hỗ trợ các tham số phổ biến:

- Payload đã convert.
- Raw `jakarta.jms.Message`.
- `jakarta.jms.Session`.
- Spring `Message<?>`.
- Tham số có `@Header`.
- Map có `@Headers`.
- `@Payload` và validation với `@Valid`.

Ví dụ method:

~~~java
public void process(
        @Payload OrderCreated order,
        @Header("tenantId") String tenantId) {
    // Xử lý order của tenant.
}
~~~

Có thể đặt custom validator hoặc conversion support:

~~~java
DefaultMessageHandlerMethodFactory factory =
        new DefaultMessageHandlerMethodFactory();
factory.setValidator(orderValidator);
factory.afterPropertiesSet();

registrar.setMessageHandlerMethodFactory(factory);
~~~

Trong cấu hình Spring thông thường, nếu factory được khai báo thành bean, container lifecycle gọi initialization callback. Không cần tự gọi `afterPropertiesSet()` lần nữa cho bean đã được Spring quản lý.

Chỉ tùy chỉnh `MessageHandlerMethodFactory` khi cần thay đổi argument resolver, conversion hoặc validation. Với simple endpoint nhận raw JMS Message, factory này không điều khiển cách listener lambda đọc payload.

## 13. Reply và error handling

Programmatic endpoint có thể dùng simple listener để gửi reply bằng JMS Session nếu listener nhận được session qua cơ chế Spring phù hợp, hoặc dùng `JmsTemplate` để gửi response tường minh.

Với method endpoint, cơ chế method invocation có thể trả về giá trị response. Hạ tầng annotation-driven JMS hỗ trợ reply destination qua `JMSReplyTo` hoặc `@SendTo`; với endpoint method đăng ký bằng chương trình, cần cấu hình invocation/response path phù hợp và kiểm tra factory/endpoint implementation đang dùng.

Không giả định `SimpleJmsListenerEndpoint` tự chuyển giá trị return của một lambda thành reply. Nó chỉ nhận một JMS `MessageListener` có `onMessage` trả về `void`.

Lỗi listener được xử lý bởi container và transaction policy:

- Với transacted session, exception có thể khiến session rollback và message được redeliver theo provider.
- Với acknowledgement tự động, độ tin cậy phụ thuộc semantics của provider/container; cần hiểu rõ hành vi khi listener lỗi.
- Nếu listener chạy bất đồng bộ, lỗi không thể được trả ngược qua call stack của producer.
- Retry/redelivery có thể tạo duplicate; handler nên idempotent.
- Cấu hình error handler, dead-letter policy và observability ở đúng tầng JMS/provider.

Đừng coi việc endpoint đăng ký thành công là bằng chứng message đã được xử lý. Đăng ký chỉ tạo consumer/listener container; kết quả nghiệp vụ cần được xác nhận bằng log, reply, event hoặc trạng thái ứng dụng.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không có message tới listener | Chưa bật `@EnableJms`, endpoint chưa đăng ký hoặc container factory thiếu | Kiểm tra configurer, registrar và factory |
| `No default JMS listener container factory` | Endpoint không chỉ định factory và không có default factory | Đăng ký factory hoặc truyền factory vào `registerEndpoint` |
| Destination không được resolve | Tên sai, Queue/Topic domain sai hoặc broker chưa provision | Kiểm tra destination resolver và broker |
| Hai endpoint nhận cùng message ngoài ý muốn | Cùng destination, cùng selector và semantics consumer/topic chưa được thiết kế đúng | Kiểm tra Queue/Topic, subscription và selector |
| Endpoint ID trùng | Tạo ID giống nhau trong registry | Sinh ID ổn định và duy nhất |
| Listener không chạy sau khi đăng ký | Container chưa start hoặc registry lifecycle chưa được kích hoạt | Kiểm tra registry và container factory |
| Concurrency không thay đổi | Container implementation không hỗ trợ dynamic scaling hoặc endpoint không dùng factory mong muốn | Kiểm tra loại container và factory thực tế |
| Method endpoint không bind được tham số | Chưa đặt bean/method hoặc method handler factory | Kiểm tra MethodJmsListenerEndpoint và argument resolver |
| `@Header` không tìm thấy giá trị | Producer không gửi property/header tương ứng | Kiểm tra JMS properties và tên header |
| Message bị redeliver liên tục | Listener liên tục ném exception trong transacted session | Xử lý poison message, giới hạn retry và DLQ |
| Listener nhận sai loại body | Simple endpoint nhận raw JMS Message | Kiểm tra Message type hoặc dùng converter/method endpoint |
| Endpoint runtime tăng liên tục | Đăng ký mới lặp lại theo request hoặc không quản lý ID | Chỉ đăng ký theo lifecycle có kiểm soát và theo dõi registry |

## 15. Ví dụ Java 17+ chạy được: đăng ký endpoint với embedded Artemis

Ví dụ sử dụng Spring Boot 4.1.2 và ActiveMQ Artemis embedded. Không dùng `@JmsListener`; endpoint được tạo trong `configureJmsListeners` và đăng ký qua registrar.

Producer gửi một String tới `orders.queue`. Spring JMS converter mặc định chuyển String thành `TextMessage`. Simple endpoint nhận raw JMS Message và listener đọc nội dung.

### Cấu trúc project

~~~text
jms-programmatic-endpoint-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          ProgrammaticJmsApplication.java
          OrderMessageHandler.java
      resources/
        application.properties
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>jms-programmatic-endpoint-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>

        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=orders.queue
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
~~~

Cấu hình embedded broker phù hợp cho demo/test. Nó không tạo ra durability production khi dữ liệu được lưu trong bộ nhớ.

### OrderMessageHandler.java

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;
import jakarta.jms.TextMessage;

import org.springframework.stereotype.Component;

@Component
public class OrderMessageHandler implements MessageListener {

    private final CountDownLatch received = new CountDownLatch(1);

    @Override
    public void onMessage(Message message) {
        if (!(message instanceof TextMessage textMessage)) {
            throw new IllegalArgumentException("Expected a TextMessage");
        }

        try {
            System.out.println("received=" + textMessage.getText());
            received.countDown();
        }
        catch (JMSException ex) {
            throw new IllegalStateException("Cannot read order message", ex);
        }
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return received.await(timeout, unit);
    }
}
~~~

### ProgrammaticJmsApplication.java

~~~java
package demo;

import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class ProgrammaticJmsApplication implements JmsListenerConfigurer {

    private final OrderMessageHandler orderMessageHandler;

    public ProgrammaticJmsApplication(OrderMessageHandler orderMessageHandler) {
        this.orderMessageHandler = orderMessageHandler;
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(ProgrammaticJmsApplication.class, args)) {
            // ApplicationRunner waits for the registered endpoint to receive one message.
        }
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setPubSubDomain(false);
        factory.setConcurrency("1");
        return factory;
    }

    @Override
    public void configureJmsListeners(JmsListenerEndpointRegistrar registrar) {
        registrar.setContainerFactoryBeanName("jmsListenerContainerFactory");

        SimpleJmsListenerEndpoint endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId("programmaticOrdersEndpoint");
        endpoint.setDestination("orders.queue");
        endpoint.setConcurrency("1");
        endpoint.setMessageListener(orderMessageHandler);

        registrar.registerEndpoint(endpoint);
    }

    @Bean
    ApplicationRunner sendOrder(
            JmsTemplate jmsTemplate,
            OrderMessageHandler orderMessageHandler) {

        return args -> {
            jmsTemplate.convertAndSend("orders.queue", "ORD-42");

            if (!orderMessageHandler.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for the programmatic JMS endpoint"
                );
            }
        };
    }
}
~~~

Chạy bằng Java 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Dòng stdout do ứng dụng in ra (bỏ qua log khởi động của Spring Boot):

~~~text
received=ORD-42
~~~

### Giải thích luồng chạy

1. `@EnableJms` bật listener endpoint infrastructure và registry.
2. Spring tạo `OrderMessageHandler`, một đối tượng implement JMS `MessageListener`.
3. Spring gọi `configureJmsListeners` trên application configurer.
4. Configurer đặt factory mặc định theo bean name `jmsListenerContainerFactory`.
5. `SimpleJmsListenerEndpoint` được tạo với ID `programmaticOrdersEndpoint`, destination `orders.queue` và handler.
6. Registrar đăng ký endpoint. Registry dùng factory để tạo và quản lý listener container.
7. `ApplicationRunner` gửi String `ORD-42` qua `JmsTemplate`.
8. Listener container nhận JMS TextMessage và gọi `OrderMessageHandler.onMessage`.
9. Handler đọc text, in kết quả và giảm latch để runner kết thúc.
10. Application context đóng và registry dừng listener container theo lifecycle.

Ví dụ cho thấy endpoint được đăng ký bằng chương trình dù không có method nào gắn `@JmsListener`. Factory quyết định connection, transaction và concurrency; endpoint quyết định destination và listener.

## 16. Kiểm thử endpoint

Nên kiểm tra các trường hợp:

- Endpoint có ID duy nhất và đúng destination.
- Registrar dùng đúng default factory hoặc factory được truyền trực tiếp.
- Message tới đúng Queue/Topic domain.
- Listener nhận đúng JMS message type và payload.
- Selector chỉ lọc đúng message cần nhận.
- Concurrency phù hợp và listener thread-safe.
- Durable subscription có subscription name/client ID phù hợp nếu dùng Topic.
- Listener exception dẫn tới transaction rollback/redelivery đúng policy.
- Registry start/stop cùng application context.
- Runtime registration không tạo endpoint trùng hoặc vượt giới hạn cấu hình.

Với method endpoint, kiểm tra thêm:

- Bean và method đã được gắn đúng.
- MethodHandlerMethodFactory có argument resolver cần thiết.
- Payload conversion và custom header binding hoạt động.
- Validation từ chối dữ liệu không hợp lệ.
- Reply destination và response converter được cấu hình đúng nếu method trả kết quả.

## 17. Checklist triển khai

- [ ] Bật `@EnableJms` để khởi tạo endpoint infrastructure.
- [ ] Implement `JmsListenerConfigurer` trong Spring-managed bean.
- [ ] Đăng ký endpoint trong `configureJmsListeners`.
- [ ] Chọn `SimpleJmsListenerEndpoint` cho raw `MessageListener`.
- [ ] Chọn `MethodJmsListenerEndpoint` cho bean method cần argument binding.
- [ ] Mỗi endpoint có ID duy nhất và ổn định.
- [ ] Destination, Queue/Topic domain và selector chính xác.
- [ ] Chọn default factory hoặc truyền factory riêng cho endpoint.
- [ ] Concurrency và transaction phù hợp với tải.
- [ ] Method endpoint có `MessageHandlerMethodFactory` nếu cần conversion/validation tùy chỉnh.
- [ ] Dùng `JmsListenerEndpointRegistry` để quan sát và quản lý lifecycle.
- [ ] Không tạo endpoint mới theo từng message/request mà không có giới hạn.
- [ ] Kiểm thử redelivery, rollback, shutdown và destination resolution.
- [ ] Không log raw message hoặc secret ngoài chính sách bảo mật.

## Ghi nhớ

- `JmsListenerConfigurer` là callback để tùy chỉnh registrar và đăng ký JMS endpoint bằng chương trình.
- `JmsListenerEndpointRegistrar` nhận endpoint và chọn `JmsListenerContainerFactory`.
- `SimpleJmsListenerEndpoint` gắn một JMS `MessageListener`; `MethodJmsListenerEndpoint` gắn một bean và method.
- Endpoint có thể cấu hình ID, destination, selector, durable subscription name và concurrency.
- `JmsListenerEndpointRegistry` tạo listener container và quản lý lifecycle; các container này không phải bean độc lập trong application context.
- Có thể kết hợp endpoint programmatic với `@JmsListener`, hoặc chỉ dùng programmatic registration.
- Đăng ký endpoint ở giai đoạn configurer khi khởi động; dùng registry API nếu cần thêm endpoint runtime có kiểm soát.
- Factory quyết định connection, transaction, concurrency và Queue/Topic domain; endpoint quyết định destination và listener.
- `MessageHandlerMethodFactory` điều khiển argument binding, conversion và validation cho method endpoint.

## Tài liệu chính thức

- [Spring Framework Reference 7.0: Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/annotated.html)
- [Spring Framework 7.0.10 Javadoc: JmsListenerConfigurer](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/annotation/JmsListenerConfigurer.html)
- [Spring Framework 7.0.10 Javadoc: JmsListenerEndpointRegistrar](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistrar.html)
- [Spring Framework 7.0.10 Javadoc: JmsListenerEndpoint](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/config/JmsListenerEndpoint.html)
- [Spring Framework 7.0.10 Javadoc: SimpleJmsListenerEndpoint](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/config/SimpleJmsListenerEndpoint.html)
- [Spring Framework 7.0.10 Javadoc: MethodJmsListenerEndpoint](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/config/MethodJmsListenerEndpoint.html)
- [Spring Framework 7.0.10 Javadoc: JmsListenerEndpointRegistry](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html)
- [Spring Framework Reference: Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Boot 4.1 Reference: JMS](https://docs.spring.io/spring-boot/4.1/reference/messaging/jms.html)
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
