# DefaultJmsListenerContainerFactory và cấu hình mặc định trong Spring JMS

## 1. Factory làm nhiệm vụ gì?

Spring JMS hỗ trợ nhận message bất đồng bộ thông qua listener container. Thay vì ứng dụng tự gọi receive liên tục, một container quản lý JMS connection, session, consumer, vòng nhận message và việc gọi listener khi có message.

DefaultJmsListenerContainerFactory là một triển khai của JmsListenerContainerFactory. Nhiệm vụ của nó là tạo và cấu hình DefaultMessageListenerContainer cho từng JMS listener endpoint. Đây là lựa chọn mặc định phù hợp với phần lớn ứng dụng Spring JMS vì container hỗ trợ polling có kiểm soát, concurrency, transaction, tự phục hồi khi broker tạm thời mất kết nối và thay đổi cấu hình trong lúc chạy.

Cần phân biệt ba thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| DefaultJmsListenerContainerFactory | Giữ cấu hình dùng chung và tạo container cho endpoint |
| DefaultMessageListenerContainer | Quản lý consumer, session, thread, polling, transaction và vòng đời nhận message |
| Phương thức @JmsListener | Xử lý payload hoặc message mà container chuyển đến |

Factory không trực tiếp nhận message. Khi Spring phát hiện một phương thức có @JmsListener, hạ tầng listener endpoint dùng factory để tạo container riêng phục vụ phương thức đó.

## 2. Bật hạ tầng @JmsListener

Trong ứng dụng Spring thuần, đặt @EnableJms trên một lớp cấu hình để bật xử lý annotation:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {
}
~~~

Spring đăng ký bộ xử lý annotation và tạo các listener endpoint từ bean có phương thức @JmsListener. Mỗi phương thức được đăng ký sẽ có một listener container tương ứng. Các container được quản lý vòng đời thông qua JmsListenerEndpointRegistry.

Nếu annotation không chỉ định containerFactory, Spring mặc định tìm bean có tên jmsListenerContainerFactory. Có thể cấu hình factory mặc định rõ ràng qua JmsListenerConfigurer nếu muốn dùng một tên khác.

Ví dụ listener đơn giản:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void receive(String orderId) {
        System.out.println("Received order: " + orderId);
    }
}
~~~

Khi message đến orders.queue, container nhận message và gọi phương thức receive. Spring chuyển body của JMS message thành tham số String thông qua MessageConverter.

## 3. Khai báo DefaultJmsListenerContainerFactory

Một cấu hình tối thiểu cần có ConnectionFactory do JMS provider cung cấp:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        return factory;
    }
}
~~~

Khi Spring tạo container cho endpoint, factory chuyển cấu hình chung vào DefaultMessageListenerContainer mới. Sau đó, thông tin riêng của endpoint như destination, selector, subscription name và concurrency được áp dụng cho container tương ứng.

Trong Spring Boot, ConnectionFactory và factory mặc định có thể được tự động cấu hình tùy starter và broker dependency. Trong Spring Framework thuần, ứng dụng phải cung cấp ConnectionFactory bean và cấu hình broker client, địa chỉ, xác thực và các tùy chọn kết nối.

## 4. Các nhóm thuộc tính quan trọng

DefaultJmsListenerContainerFactory kế thừa nhiều thuộc tính từ AbstractJmsListenerContainerFactory và bổ sung các thuộc tính riêng cho DefaultMessageListenerContainer.

### 4.1. Kết nối và phân giải destination

| Thuộc tính | Mục đích |
| --- | --- |
| setConnectionFactory | Chọn JMS ConnectionFactory dùng để kết nối broker |
| setDestinationResolver | Phân giải tên destination thành Queue hoặc Topic |
| setPubSubDomain | Chọn domain mặc định: false cho queue, true cho topic |
| setClientId | Đặt JMS client ID, thường cần cho durable topic subscription |

ConnectionFactory là thành phần bắt buộc để container tạo kết nối JMS. Nó thường được cung cấp bởi ActiveMQ Artemis, IBM MQ, Amazon SQS JMS wrapper hoặc một JMS provider khác.

DestinationResolver cho phép ứng dụng phân giải tên destination theo quy tắc riêng, ví dụ dùng JNDI hoặc tạo destination động. Nếu không cấu hình resolver riêng, Spring dùng cơ chế mặc định dựa trên domain queue/topic được chọn.

### 4.2. Chuyển đổi message

setMessageConverter cấu hình MessageConverter dùng để chuyển JMS Message thành đối số phương thức listener và chuyển giá trị trả về thành JMS reply khi có hỗ trợ phản hồi.

SimpleMessageConverter mặc định phù hợp với các kiểu cơ bản như String, byte array, Map và Serializable. Khi trao đổi DTO JSON, có thể cấu hình converter JSON phù hợp để tránh phải tự đọc TextMessage và parse body trong từng listener.

Ví dụ cấu hình converter tùy chỉnh:

~~~java
factory.setMessageConverter(orderMessageConverter);
~~~

Biến orderMessageConverter phải là một MessageConverter bean đã được cấu hình trước, ví dụ converter dựa trên Jackson. Định dạng serialize phải thống nhất giữa producer và consumer.

### 4.3. Concurrency và executor

| Thuộc tính | Ý nghĩa |
| --- | --- |
| setConcurrency | Cấu hình giới hạn consumer tối thiểu và tối đa dưới dạng chuỗi |
| setTaskExecutor | Chọn executor chạy các listener invoker |
| setMaxMessagesPerTask | Giới hạn số lần nhận message trong một task trước khi task được lên lịch lại |

Với DefaultMessageListenerContainer, giá trị concurrency có thể là một số hoặc khoảng min-max:

~~~java
factory.setConcurrency("3-10");
~~~

Chuỗi 3-10 có nghĩa container giữ tối thiểu ba consumer và có thể tăng dần đến mười khi tải tăng. Nếu truyền "5", mức tối thiểu là một và mức tối đa là năm.

Concurrency cao hơn giúp queue xử lý nhiều message đồng thời, nhưng thứ tự xử lý giữa các message có thể thay đổi. Với topic, cần thận trọng khi tăng số consumer: trong cấu hình thông thường, nhiều consumer cùng node có thể nhận cùng một bản sao message của topic. Chỉ tăng concurrency cho topic khi provider và kiểu subscription hỗ trợ rõ ràng.

Nếu không cấu hình TaskExecutor, DefaultMessageListenerContainer sử dụng SimpleAsyncTaskExecutor. Executor này tạo thread theo nhu cầu và không phải thread pool tái sử dụng truyền thống. Với tải lớn hoặc giới hạn tài nguyên chặt, hãy cân nhắc cung cấp executor có giới hạn và giám sát số thread đang hoạt động.

### 4.4. Cache tài nguyên JMS

setCacheLevel hoặc setCacheLevelName quyết định container cache Connection, Session và MessageConsumer ở mức nào.

Các mức thường dùng:

| Mức cache | Tài nguyên được giữ |
| --- | --- |
| CACHE_NONE | Không cache tài nguyên JMS |
| CACHE_CONNECTION | Cache Connection |
| CACHE_SESSION | Cache Connection và Session |
| CACHE_CONSUMER | Cache Connection, Session và MessageConsumer |
| CACHE_AUTO | Để container chọn mức phù hợp theo chiến lược transaction |

Với tài nguyên JMS cục bộ, DefaultMessageListenerContainer mặc định cache Connection, Session và Consumer ở mức CACHE_CONSUMER. Khi sử dụng external transaction manager, mặc định là CACHE_NONE để lấy lại các tài nguyên mới trong phạm vi transaction, phù hợp với yêu cầu của một số Jakarta EE/XA server.

Không nên mặc định bọc listener container bằng CachingConnectionFactory mà không đọc hướng dẫn của container. DefaultMessageListenerContainer đã có cơ chế cache riêng theo vòng đời của nó; cache bên ngoài có thể gây vấn đề khi stop/start hoặc khi container scale consumer động.

## 5. Các mặc định thực tế của container

Factory mới tạo ra DefaultMessageListenerContainer. Nếu không override, container sử dụng các mặc định quan trọng sau:

| Cấu hình của container | Mặc định | Ý nghĩa |
| --- | --- | --- |
| concurrentConsumers | 1 | Một consumer tối thiểu |
| maxConcurrentConsumers | 1 | Không tự scale lên nhiều consumer |
| receiveTimeout | 1000 ms | Mỗi lần polling chờ tối đa một giây |
| recoveryInterval | 5000 ms | Thử phục hồi sau khoảng năm giây |
| cacheLevel | CACHE_CONSUMER với tài nguyên cục bộ; CACHE_NONE khi có external transaction manager | Cache theo cách quản lý transaction |
| sessionTransacted | false | JMS Session không transacted |
| sessionAcknowledgeMode | AUTO_ACKNOWLEDGE | Chế độ acknowledge mặc định |
| maxMessagesPerTask | Thường là -1 với TaskExecutor thông thường | Task invoker có thể tiếp tục nhận cho đến khi container dừng |

Mặc định của container là nền tảng ban đầu. Factory có thể thay đổi các giá trị này cho toàn bộ endpoint sử dụng nó; annotation hoặc endpoint có thể ghi đè một số thiết lập riêng, ví dụ concurrency.

### 5.1. receiveTimeout và polling

DefaultMessageListenerContainer dùng vòng lặp gọi MessageConsumer.receive(timeout). receiveTimeout là thời gian chờ của mỗi lần polling, không phải thời gian tối đa xử lý nghiệp vụ.

Mặc định 1000 ms cho phép container định kỳ kiểm tra trạng thái, quản lý task và phản ứng với shutdown. Không nên đặt 0 một cách tùy tiện vì 0 có nghĩa chờ vô hạn và có thể khiến việc dừng container khó khăn hơn.

### 5.2. recoveryInterval và BackOff

Nếu broker tạm thời không khả dụng hoặc quá trình tạo consumer thất bại, container tự thử phục hồi. Mặc định khoảng cách giữa các lần thử là 5000 ms.

Có thể dùng setRecoveryInterval để thay khoảng thời gian cố định hoặc setBackOff để cấu hình chiến lược tăng dần, ví dụ exponential backoff:

~~~java
factory.setRecoveryInterval(10_000L);
~~~

Nếu cần chiến lược linh hoạt hơn, truyền một BackOff implementation:

~~~java
factory.setBackOff(new ExponentialBackOff(1_000L, 2.0));
~~~

Không cấu hình recoveryInterval và BackOff như hai chính sách độc lập cùng lúc mà không kiểm tra thứ tự áp dụng. Việc đặt recoveryInterval tạo fixed backoff và có thể ghi đè BackOff đã cấu hình.

## 6. Acknowledge và transaction: mặc định cần đánh giá kỹ

Một điểm quan trọng khi cấu hình factory là cách container xác nhận message đã được xử lý.

Mặc định sessionTransacted là false và sessionAcknowledgeMode là AUTO_ACKNOWLEDGE. Với DefaultMessageListenerContainer, AUTO_ACKNOWLEDGE thực hiện acknowledge trước khi gọi listener. Nếu listener ném exception, message không được tự động redeliver theo cơ chế này.

Điều đó có nghĩa một listener có thể thất bại sau khi message đã được acknowledge. Nếu nghiệp vụ yêu cầu xử lý đáng tin cậy, hãy cấu hình transaction phù hợp.

### 6.1. Dùng JMS local transaction

Cách phổ biến trong ứng dụng độc lập hoặc Spring thông thường là bật sessionTransacted:

~~~java
factory.setSessionTransacted(true);
~~~

Khi đó, việc nhận message và xử lý listener nằm trong JMS transaction. Nếu listener hoàn tất bình thường, container commit transaction. Nếu listener ném exception, transaction rollback và broker có thể giao lại message theo chính sách redelivery của provider.

Transaction cục bộ này bao phủ thao tác JMS trong Session. Nếu listener đồng thời cập nhật database bằng JDBC, hai tài nguyên chưa tự động trở thành một transaction phân tán duy nhất. Hãy thiết kế idempotency hoặc cơ chế outbox/inbox để xử lý trường hợp database commit nhưng JMS commit thất bại.

### 6.2. Dùng external transaction manager

Nếu cần kết hợp JMS với tài nguyên khác trong một XA transaction, có thể cấu hình PlatformTransactionManager, thường là JtaTransactionManager cùng XA-aware ConnectionFactory:

~~~java
factory.setTransactionManager(transactionManager);
~~~

Cách này có thể phối hợp việc nhận message và xử lý nghiệp vụ trong transaction phân tán. Nó cần broker/provider hỗ trợ XA, transaction manager được cấu hình đúng và có chi phí vận hành cao hơn.

Không dùng XA chỉ vì muốn tránh mọi duplicate. Với nhiều ứng dụng, local JMS transaction kết hợp xử lý idempotent là lựa chọn đơn giản và hiệu quả hơn.

### 6.3. Idempotency và redelivery

Ngay cả khi dùng transaction, duplicate vẫn có thể xảy ra ở một số tình huống biên, ví dụ JVM dừng sau khi logic nghiệp vụ chạy nhưng trước khi transaction JMS commit hoàn tất.

Consumer nên có event ID hoặc business key để nhận biết message đã được xử lý. Việc ghi nhận trạng thái xử lý cần được phối hợp với cập nhật nghiệp vụ để một message được giao lại không tạo tác động lặp ngoài ý muốn.

## 7. Cấu hình một factory cho nhiều listener

Ví dụ sau cấu hình factory dùng chung cho queue listener:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("2-6");
        factory.setSessionTransacted(true);
        factory.setReceiveTimeout(1_000L);
        factory.setRecoveryInterval(5_000L);

        return factory;
    }
}
~~~

Factory được đặt tên jmsListenerContainerFactory nên các @JmsListener không chỉ định containerFactory sẽ dùng nó.

Listener:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void handle(String orderId) {
        process(orderId);
    }

    private void process(String orderId) {
        System.out.println("Processing order: " + orderId);
    }
}
~~~

Đoạn cấu hình này yêu cầu ConnectionFactory đã được cung cấp bởi JMS provider và broker đang hoạt động. Ví dụ chỉ mô tả cách cấu hình Spring; stdout thực tế phụ thuộc message được gửi và thời điểm listener nhận.

## 8. Tạo nhiều factory cho các nhóm listener

Không phải mọi listener đều cần cùng concurrency, transaction hoặc domain. Có thể tạo nhiều factory với tên khác nhau:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory fastQueueFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("3-8");
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    public DefaultJmsListenerContainerFactory auditQueueFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Chọn factory ngay trên listener:

~~~java
@Component
public class AuditListener {

    @JmsListener(
        destination = "audit.queue",
        containerFactory = "auditQueueFactory"
    )
    public void handle(String event) {
        writeAudit(event);
    }

    private void writeAudit(String event) {
        System.out.println("Audit: " + event);
    }
}
~~~

Factory fastQueueFactory có thể phục vụ queue có lưu lượng lớn, còn auditQueueFactory giữ concurrency thấp để kiểm soát thứ tự và tải. Việc chọn concurrency phải dựa trên khả năng xử lý, giới hạn connection/session của provider và yêu cầu thứ tự nghiệp vụ.

## 9. Thuộc tính riêng của từng @JmsListener

Một endpoint có thể ghi đè một số thiết lập chung từ factory:

~~~java
@JmsListener(
    id = "priorityOrders",
    destination = "orders.queue",
    selector = "priority >= 8",
    concurrency = "2-4"
)
public void handlePriorityOrder(String orderId) {
    processPriorityOrder(orderId);
}
~~~

Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| destination | Tên queue hoặc topic cần lắng nghe |
| containerFactory | Tên bean factory dùng để tạo container |
| id | ID duy nhất để quản lý container qua registry |
| selector | JMS message selector |
| concurrency | Giới hạn consumer cho endpoint; có thể override concurrency từ factory |
| subscription | Tên durable subscription khi dùng topic phù hợp |

Nếu nhiều endpoint dùng cùng factory, chúng có thể có concurrency riêng. Không cần tạo factory mới chỉ để thay đổi concurrency cho một listener nếu annotation đã hỗ trợ thuộc tính đó.

## 10. Queue và topic: cấu hình domain

DefaultJmsListenerContainerFactory kế thừa setPubSubDomain:

- false: sử dụng queue, là mặc định.
- true: sử dụng topic.

Ví dụ factory cho topic:

~~~java
@Bean
public DefaultJmsListenerContainerFactory topicListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setClientId("inventory-service");
    factory.setSessionTransacted(true);

    return factory;
}
~~~

Một listener có thể dùng factory đó:

~~~java
@JmsListener(
    destination = "inventory.events",
    subscription = "inventory-audit",
    containerFactory = "topicListenerFactory"
)
public void handleInventoryEvent(String event) {
    recordInventoryEvent(event);
}
~~~

Durable subscription cần client ID và subscription name phù hợp với quy tắc của provider. Subscription shared có thể được cấu hình riêng bằng setSubscriptionShared(true) khi JMS provider hỗ trợ. Với topic, không tăng concurrency tùy tiện vì có thể khiến một node nhận nhiều bản sao của cùng message.

Nếu dùng queue và topic đồng thời, hãy tạo factory riêng cho từng domain hoặc cấu hình endpoint rõ ràng. Đừng để pubSubDomain mặc định của factory khiến listener kết nối nhầm loại destination.

## 11. ErrorHandler, ExceptionListener và quan sát

Factory có thể cấu hình hai cơ chế xử lý lỗi khác nhau:

- ErrorHandler nhận các exception không được xử lý phát sinh trong quá trình gọi listener.
- ExceptionListener nhận JMSException từ provider hoặc hạ tầng listener. Nếu ErrorHandler cũng được cấu hình, một số JMSException có thể tiếp tục được chuyển đến ErrorHandler sau ExceptionListener.

Ví dụ:

~~~java
factory.setErrorHandler(error ->
    logger.error("JMS listener failed", error)
);
~~~

Nếu không cấu hình ErrorHandler, exception từ listener được ghi log ở mức WARN theo hành vi mặc định của container. Exception không tự động được truyền ngược về JMS provider như một lỗi listener.

Có thể cấu hình ExceptionListener để quan sát lỗi kết nối hoặc lỗi JMS ở tầng provider:

~~~java
factory.setExceptionListener(exception ->
    logger.error("JMS provider error", exception)
);
~~~

Spring Framework 6.1+ cũng hỗ trợ ObservationRegistry cho việc ghi nhận quan sát xử lý message. Khi có Micrometer ObservationRegistry, có thể cấu hình qua factory để theo dõi thời gian xử lý và các thông tin quan sát phù hợp.

Không coi ErrorHandler là cơ chế retry hoặc redelivery. Retry và redelivery cần được quyết định bằng transaction, acknowledgement, chính sách broker hoặc cơ chế retry riêng.

## 12. Recovery, shutdown và quản lý vòng đời

DefaultMessageListenerContainer triển khai SmartLifecycle, nên Spring quản lý việc start và stop cùng application context.

Các thuộc tính đáng chú ý:

- setAutoStartup(false): không tự động start container khi context khởi động.
- setPhase(...): điều khiển thứ tự start/stop tương đối giữa các thành phần lifecycle.
- setRecoveryInterval(...): cấu hình khoảng thời gian thử kết nối lại.
- setBackOff(...): cấu hình chiến lược retry khi container không thể thiết lập listener.
- setTaskExecutor(...): quản lý thread thực thi listener.

Khi broker mất kết nối, container có thể tự phục hồi và tạo lại tài nguyên JMS. Hãy quan sát log recovery, số consumer đang hoạt động, số lần reconnect và trạng thái queue.

Khi shutdown, container dừng consumer và giải phóng session/connection theo vòng đời. Nếu listener đang xử lý message lâu, hãy xác định thời gian shutdown phù hợp và tránh dừng broker hoặc JVM quá gấp.

## 13. Những sai lầm thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| @JmsListener không được đăng ký | Thiếu @EnableJms hoặc bean listener không được Spring quản lý | Bật annotation support và kiểm tra component scanning |
| Không tìm thấy container factory | Tên bean không phải jmsListenerContainerFactory và annotation không chỉ định factory | Đặt đúng tên mặc định hoặc dùng containerFactory rõ ràng |
| Listener kết nối nhầm queue/topic | pubSubDomain không đúng domain | Dùng factory riêng hoặc đặt pubSubDomain phù hợp |
| Listener xử lý tuần tự dù mong muốn song song | concurrentConsumers vẫn bằng 1 | Tăng concurrency sau khi kiểm tra thứ tự và năng lực broker |
| Message bị mất khi listener ném exception | AUTO_ACKNOWLEDGE mặc định của DefaultMessageListenerContainer acknowledge trước listener | Bật sessionTransacted hoặc dùng transaction manager |
| Message được xử lý lặp | Broker redelivery hoặc transaction commit không hoàn tất | Thiết kế consumer idempotent bằng event ID/business key |
| Broker phục hồi chậm | recoveryInterval quá dài hoặc BackOff chưa phù hợp | Điều chỉnh recovery/backoff theo SLA và giới hạn reconnect |
| Thread tăng không kiểm soát | SimpleAsyncTaskExecutor mặc định tạo thread theo nhu cầu | Cung cấp TaskExecutor có giới hạn và giám sát tải |
| Topic nhận message trùng trong cùng ứng dụng | Tăng concurrency topic không đúng cách | Giữ một consumer hoặc dùng shared subscription theo khả năng provider |
| Cache gây lỗi stop/start | Bọc listener container bằng CachingConnectionFactory không phù hợp | Ưu tiên cache do container quản lý và kiểm tra transaction strategy |

## 14. Checklist cấu hình production

- [ ] Cung cấp ConnectionFactory đúng broker, endpoint và credentials.
- [ ] Bật @EnableJms trong ứng dụng Spring thuần.
- [ ] Đặt tên factory mặc định là jmsListenerContainerFactory hoặc chỉ rõ containerFactory trên từng endpoint.
- [ ] Xác định queue hay topic và cấu hình pubSubDomain tương ứng.
- [ ] Chọn concurrency theo tải, thứ tự message và giới hạn tài nguyên broker.
- [ ] Cấu hình sessionTransacted hoặc transaction manager khi cần redelivery đáng tin cậy.
- [ ] Thiết kế listener idempotent để xử lý duplicate.
- [ ] Kiểm tra message converter và schema payload.
- [ ] Cấu hình ErrorHandler, ExceptionListener, recovery/backoff và log.
- [ ] Cấu hình executor có giới hạn nếu dùng thread pool riêng.
- [ ] Kiểm tra cache level phù hợp với transaction manager và provider.
- [ ] Kiểm thử broker restart, listener exception, redelivery, queue backlog và shutdown.
- [ ] Theo dõi active consumer, processing latency, redelivery count, error rate và recovery attempts.

## 15. Tài liệu tham khảo

- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework API — DefaultJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html)
- [Spring Framework API — AbstractJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/config/AbstractJmsListenerContainerFactory.html)
- [Spring Framework API — JmsListener](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [Spring Framework API — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework API — AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework API — AbstractPollingMessageListenerContainer](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html)
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
