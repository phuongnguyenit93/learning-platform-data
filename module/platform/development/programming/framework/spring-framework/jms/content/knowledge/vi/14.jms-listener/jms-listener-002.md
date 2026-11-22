# Đăng ký DefaultJmsListenerContainerFactory cho @JmsListener trong Spring JMS

## 1. Bài toán: ai tạo và vận hành JMS listener?

Trong Spring Framework JMS, một phương thức Java có thể lắng nghe message bất đồng bộ chỉ bằng annotation:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.incoming")
    public void receive(String body) {
        System.out.println("Received: " + body);
    }
}
~~~

Đây là snippet cần các import Spring và được đặt trong một ứng dụng đã bật JMS annotation processing, chưa phải chương trình độc lập.

Tuy nhiên, annotation không tự mở connection tới broker, không tự quản lý JMS Session, MessageConsumer, transaction, thread, lỗi mạng hay conversion. Spring cần một **listener container** thực hiện những công việc ấy. Để tạo ra listener container cho mỗi @JmsListener theo một chính sách cấu hình thống nhất, Spring dùng **JmsListenerContainerFactory**.

Implementation tiêu chuẩn và thường gặp là:

~~~text
org.springframework.jms.config.DefaultJmsListenerContainerFactory
~~~

Factory này tạo các **DefaultMessageListenerContainer**, là những runtime containers trực tiếp polling/receiving JMS messages rồi gọi phương thức @JmsListener. Nó có thể áp dụng các cấu hình về ConnectionFactory, Queue/Topic, concurrency, transaction, acknowledgement, MessageConverter, DestinationResolver, recovery và lifecycle.

**Mục đích của bài học:** hiểu chính xác cách đăng ký DefaultJmsListenerContainerFactory trong Spring, chọn tên bean/default factory, trỏ listener tới factory, tận dụng Spring Boot auto-configuration và tránh các lỗi vận hành. Phần cuối có dự án Java 17, Spring Boot 3.3 và Apache ActiveMQ Artemis có thể chạy độc lập.

## 2. Ba tầng quan trọng: factory, container, listener

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] --> B["@EnableJms / annotation infrastructure"]
    A --> F["Bean: jmsListenerContainerFactory"]
    F --> B
    B --> L1["@JmsListener: orders.incoming"]
    B --> L2["@JmsListener: audit.events"]
    L1 --> C1["DefaultMessageListenerContainer #1"]
    L2 --> C2["DefaultMessageListenerContainer #2"]
    F -.-> C1
    F -.-> C2
    C1 --> J["jakarta.jms.ConnectionFactory → JMS Broker"]
    C2 --> J
    R["JmsListenerEndpointRegistry"] --> C1
    R --> C2
~~~

| Thành phần | Vai trò | Có trực tiếp receive message không? |
| --- | --- | --- |
| @JmsListener | Khai báo endpoint, destination, selector, factory | Không. |
| DefaultJmsListenerContainerFactory | Tạo container và gắn các policy cấu hình | Không; nó tạo container. |
| DefaultMessageListenerContainer | Nắm connection/session/consumer, nhận và chuyển message vào listener | Có. |
| JmsListenerEndpointRegistry | Quản lý/lấy container theo endpoint ID, lifecycle | Không tự chuyển payload. |
| JmsTemplate | Template gửi hoặc nhận đồng bộ từ application code | Tách biệt với factory của listener. |
| JMS ConnectionFactory | Tạo JMS connection tới broker | Không phải factory tạo listener container. |

Đây là phân biệt nền tảng. Đăng ký factory thành một Spring bean **không đồng nghĩa** đã đăng ký mọi listener; @JmsListener còn phải được Spring phát hiện và hạ tầng JMS annotation phải hoạt động.

### 2.1. Trình tự xử lý

1. Spring khởi tạo ConnectionFactory cùng các bean cấu hình.
2. Cơ chế @EnableJms hoặc Spring Boot auto-configuration kích hoạt annotation-driven JMS.
3. Spring scan bean methods có @JmsListener, biến mỗi annotation thành endpoint metadata.
4. Hạ tầng chọn JmsListenerContainerFactory cho endpoint.
5. Factory tạo DefaultMessageListenerContainer với cấu hình đã đặt.
6. Container start theo Spring lifecycle, kết nối broker và đăng ký/nhận message từ destination.
7. Khi broker giao message, container gọi message handler method qua adapter/converter.
8. Trên thành công/lỗi, container xử lý acknowledge/commit/rollback/recovery phù hợp cấu hình.

Factory được tái sử dụng để tạo các container có policy giống nhau; container và consumer thực tế tồn tại theo lifecycle riêng của từng listener endpoint.

## 3. Package và lớp cần import đúng

| Tên | Package | Ý nghĩa |
| --- | --- | --- |
| DefaultJmsListenerContainerFactory | org.springframework.jms.config | Tạo DefaultMessageListenerContainer. |
| JmsListenerContainerFactory | org.springframework.jms.config | Interface factory tổng quát. |
| DefaultMessageListenerContainer | org.springframework.jms.listener | Runtime consumer container. |
| @JmsListener | org.springframework.jms.annotation | Annotation method nhận JMS message. |
| @EnableJms | org.springframework.jms.annotation | Bật annotation infrastructure. |
| JmsListenerConfigurer | org.springframework.jms.annotation | Tùy biến registrar/default factory hoặc endpoints. |
| JmsListenerEndpointRegistrar | org.springframework.jms.config | Registrar được cung cấp cho configurer. |
| JmsListenerEndpointRegistry | org.springframework.jms.config | Truy vấn/start/stop annotated listener containers. |
| ConnectionFactory | jakarta.jms | JMS API tạo connection/context. |
| MessageConverter | org.springframework.jms.support.converter | JMS Message ↔ Java payload. |
| DestinationResolver | org.springframework.jms.support.destination | Chuyển String name thành JMS Destination. |

Với **Spring Framework 6.x/Spring Boot 3.x**, import JMS từ jakarta.jms.*, **không dùng javax.jms.*** của Spring Framework 5.

Tên lớp DefaultJmsListenerContainerFactory rất giống DefaultMessageListenerContainer. Hãy phân biệt hai thứ khi debug: một bên là **bean factory**, bên kia là **runtime listener** được tạo bởi factory.

## 4. Cách đăng ký mặc định trong Spring Framework

Khi một @JmsListener không chỉ định containerFactory, Spring mặc định tìm một Spring bean có tên **jmsListenerContainerFactory**.

Một cấu hình tiêu chuẩn:

~~~java
package example.config;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsConfig {

    @Bean("jmsListenerContainerFactory")
    public DefaultJmsListenerContainerFactory listenerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");
        return factory;
    }
}
~~~

Đây là **lớp cấu hình có thể biên dịch** nếu project có dependencies Spring JMS và một ConnectionFactory bean đã được đăng ký. Nó không phải toàn bộ dự án runnable nếu chưa có provider/broker.

Giải thích các điểm:

- @Configuration: Spring nhận diện class có bean definitions.
- @EnableJms: kích hoạt hạ tầng xử lý annotated JMS endpoints.
- @Bean("jmsListenerContainerFactory"): đăng ký **đúng bean name mặc định**.
- setConnectionFactory: chỉ tới JMS broker qua ConnectionFactory được inject.
- setPubSubDomain(false): dùng Queue domain khi phân giải tên động.
- setSessionTransacted(true): local JMS transaction, phù hợp khi cần rollback/redelivery.
- setConcurrency("1-3"): cho một container số concurrent consumers tối thiểu 1, tối đa 3 tùy workload.

Có thể dùng method có tên đúng để Spring lấy tên method làm bean name:

~~~java
@Bean
public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory cf) {
    DefaultJmsListenerContainerFactory f =
            new DefaultJmsListenerContainerFactory();
    f.setConnectionFactory(cf);
    return f;
}
~~~

Snippet này ngắn hơn nhưng phụ thuộc method name; nếu refactor đổi tên method mà không cập nhật @JmsListener, có thể làm mất contract tên bean. Với project lớn, dùng tên bean tường minh thường dễ review.

### 4.1. Chỉ cần đăng ký factory đã đủ chưa?

Chưa. Trong Spring Framework thuần cần:

1. Jakarta JMS provider/client library tương thích.
2. Spring JMS trên classpath.
3. ConnectionFactory bean kết nối đúng broker.
4. Kích hoạt JMS annotation infrastructure, thường bằng @EnableJms.
5. JmsListenerContainerFactory phù hợp.
6. Spring-managed @Component/@Service bean có @JmsListener methods.

Nếu OrderListener được tạo thủ công bằng new mà không được Spring quản lý, annotation sẽ không được scan thành endpoint. Nếu broker không chạy, factory bean có thể được tạo nhưng listener container không thể nhận message.

## 5. Chọn factory cụ thể trên @JmsListener

Ví dụ muốn dành một factory với concurrency riêng cho công việc quan trọng:

~~~java
@Component
public class PriorityOrderConsumer {

    @JmsListener(
        id = "priorityOrderConsumer",
        destination = "orders.priority",
        containerFactory = "priorityListenerFactory")
    public void handle(String text) {
        // Xử lý order có độ ưu tiên cao.
    }
}
~~~

Đây là snippet, cần import @Component và @JmsListener. Giá trị containerFactory là **tên Spring bean**, không phải fully-qualified class name hay tên queue.

Đăng ký bean phù hợp:

~~~java
@Bean("priorityListenerFactory")
DefaultJmsListenerContainerFactory priorityListenerFactory(
        ConnectionFactory connectionFactory) {
    DefaultJmsListenerContainerFactory f =
            new DefaultJmsListenerContainerFactory();
    f.setConnectionFactory(connectionFactory);
    f.setSessionTransacted(true);
    f.setPubSubDomain(false);
    f.setConcurrency("2-6");
    return f;
}
~~~

Đây là snippet nằm trong @Configuration class, không có main() độc lập.

Nếu listener không ghi containerFactory, nó dùng mặc định jmsListenerContainerFactory (hoặc default factory được registrar chỉ định). **Đừng tự giả định @Primary của bean cùng kiểu luôn quyết định factory cho endpoint.** Cơ chế annotated endpoint có quy ước bean name riêng.

### 5.1. Một ứng dụng có được nhiều factories không?

Có. Các workload có thể cần policy khác nhau:

| Factory bean name | Domain | Concurrency | Mục tiêu |
| --- | --- | --- | --- |
| jmsListenerContainerFactory | Queue | 1-3 | Consumer mặc định. |
| bulkListenerFactory | Queue | 3-10 | Nhóm jobs xử lý độc lập, throughput cao. |
| financeListenerFactory | Queue | 1 | Công việc cần thứ tự/kiểm soát chặt. |
| topicListenerFactory | Topic | 1 | Subscription sự kiện. |

Bảng chỉ là **ví dụ kiến trúc**, không phải cấu hình bắt buộc. Với Topic durable/shared subscriptions, phải thêm các thiết lập khác và xét giới hạn của provider; đừng dùng concurrency cao từ queue factory rồi giả định topic cũng xử lý hệt.

## 6. Vai trò của Spring Boot auto-configuration

### 6.1. Spring Boot có thể đăng ký factory sẵn

Trong ứng dụng Spring Boot có starter JMS và ConnectionFactory phù hợp, Boot thường tự tạo JmsTemplate và default JMS listener container factory. Theo tài liệu Spring Boot, annotation listeners cũng có thể được kích hoạt tự động; **không nhất thiết phải thêm @EnableJms** cho app Boot điển hình.

Ví dụ dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-artemis</artifactId>
</dependency>
~~~

Khi đó @JmsListener(destination="orders.incoming") có thể hoạt động mà không cần một bean factory khai báo tường minh.

**Tuy nhiên**, khi bạn tạo một bean tên jmsListenerContainerFactory, Boot auto-configuration thường sẽ back off theo điều kiện. Lúc ấy các tùy chọn bạn chưa cấu hình có thể **không** mặc nhiên giống default Boot. Không nên vừa ghi manual bean vừa suy luận Boot luôn áp toàn bộ spring.jms.listener.* properties.

### 6.2. Khi nào chọn manual factory?

Tạo factory thủ công khi có nhu cầu cụ thể như:

- Local transaction hay external transaction manager.
- Concurrency khác nhau cho các nhóm workload.
- Queue/Topic domain và subscription riêng.
- DestinationResolver theo JNDI hoặc naming policy.
- MessageConverter/Jackson, reply QoS, validation.
- ErrorHandler, recovery backoff, polling timeout, task executor.
- Sử dụng native ConnectionFactory hoặc JTA-managed resource.
- Start/stop policy riêng, vận hành và giám sát ở mức listener.

Nếu defaults của Boot đã phù hợp, **không cần viết factory chỉ để có một bean nhìn thấy trong source code**.

## 7. Tận dụng DefaultJmsListenerContainerFactoryConfigurer trong Spring Boot 3.x

Spring Boot cung cấp **DefaultJmsListenerContainerFactoryConfigurer** để áp những defaults và properties Boot đã tính toán lên một factory do bạn tạo, rồi bạn chỉ override phần khác biệt. Đây là cách hữu ích nhất nếu app có nhiều listener factories.

**Import dành cho Spring Boot 3.x:**

~~~java
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
~~~

Trong Spring Boot 4.x, package liên quan đã thay đổi; không dùng bừa API docs Boot 4 để compile project Boot 3.3.

Ví dụ:

~~~java
@Configuration
class ListenerFactories {

    @Bean("bulkListenerFactory")
    DefaultJmsListenerContainerFactory bulkFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        configurer.configure(factory, connectionFactory);
        factory.setConcurrency("3-8");
        factory.setPubSubDomain(false);
        return factory;
    }
}
~~~

Snippet này cần import Configuration, Bean, ConnectionFactory và DefaultJmsListenerContainerFactory; nó minh họa trình tự quan trọng:

1. Tạo factory mới.
2. Gọi configurer.configure(factory, connectionFactory) để nhận defaults Boot.
3. **Sau đó** override setConcurrency/setPubSubDomain cho factory cụ thể.

Nếu gọi overrides trước configure, configure có thể đặt lại một số settings, làm kết quả khác ý định.

### 7.1. CachingConnectionFactory và native connection

DefaultMessageListenerContainer tự quản lý connection recovery và các JMS resource cache phù hợp. Boot thường khuyên listener container làm việc với native ConnectionFactory thay vì vô tình chia sẻ wrapper cache dùng cho các producers.

Trong Spring Boot 3.x có helper:

~~~java
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;

configurer.configure(
        factory,
        ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
~~~

Đây là snippet. Cần xem ConnectionFactory thực tế: JTA/XA provider, connection pool, caching wrapper có đặc tính khác nhau. **Không unwrap tùy tiện mọi loại wrapper** nếu có transaction integration đặc biệt.

### 7.2. Boot properties nào liên quan?

~~~properties
spring.jms.listener.min-concurrency=2
spring.jms.listener.max-concurrency=6
spring.jms.listener.auto-startup=true
~~~

Những properties này có thể được Boot configurer đưa vào default factory. Nếu tự tạo manual factory và **không dùng configurer**, đừng mong chúng luôn được áp. Cần test cấu hình runtime và kiểm tra theo đúng phiên bản Boot.

Khi ứng dụng có cả producer và listener, properties của **JmsTemplate** (ví dụ receive timeout cho template) không phải tất cả properties của **listener container**; hai thành phần có lifecycle khác nhau.

## 8. Các settings quan trọng của DefaultJmsListenerContainerFactory

| Thiết lập | Tác dụng | Lưu ý |
| --- | --- | --- |
| setConnectionFactory | JMS connection resource | Phải đúng broker/credentials và cùng topology với producer. |
| setPubSubDomain | Queue hoặc Topic | false queue, true topic khi phân giải tên tương ứng. |
| setDestinationResolver | String name → Destination | Dynamic/JNDI/custom resolver tùy deployment. |
| setMessageConverter | JMS Message ↔ Java payload | Cần thống nhất với method signature và sender converter. |
| setSessionTransacted | Local JMS transaction | Lỗi listener có thể dẫn đến rollback/redelivery. |
| setSessionAcknowledgeMode | JMS acknowledge mode | Không đồng nhất với local JMS transaction. |
| setTransactionManager | External Spring transaction manager | Chỉ tạo XA khi hạ tầng/resource thực sự hỗ trợ. |
| setConcurrency | Số consumers đồng thời | Tác động lên throughput, ordering và broker resources. |
| setReceiveTimeout | Receive polling timeout | Khác TTL của message và business timeout. |
| setRecoveryInterval / setBackOff | Khôi phục sau lỗi connection | Phụ thuộc provider và operational policy. |
| setCacheLevel | Cache JMS handles | Xem transaction manager, pooling và container lifecycle. |
| setTaskExecutor | Executor chạy invoker tasks | Thread pool cần đủ tài nguyên và giới hạn an toàn. |
| setErrorHandler | Ghi nhận/quan sát listener exceptions | Không thay transaction/redelivery policy. |
| setAutoStartup | Tự khởi động container theo lifecycle | Cần khi triển khai theo giai đoạn hoặc bảo trì. |
| setReplyQosSettings | QoS của response messages | Không áp vào input message TTL. |

Một số setter được thừa kế từ AbstractJmsListenerContainerFactory, còn số khác dành cho DefaultJmsListenerContainerFactory. **Không cần gọi tất cả setters trong mỗi cấu hình**. Hãy bắt đầu bằng ConnectionFactory, transaction và concurrency được hiểu rõ, rồi mở rộng theo requirements đã test.

## 9. Concurrency: setConcurrency("min-max") và hệ quả

~~~java
factory.setConcurrency("3-10");
~~~

Với mỗi DefaultMessageListenerContainer tạo từ factory, đây là chính sách số consumers từ mức core/minimum tới maximum. Nó **không** biểu thị “toàn ứng dụng có tối đa 10 consumers”.

Ví dụ có 4 endpoint @JmsListener cùng dùng factory 3-10, tổng số sessions/consumers có thể lớn hơn 10. Số consumers thực tế còn phụ thuộc load, executor, broker, constraints và chiến lược scaling.

### 9.1. Khi nhiều consumers thì ordering thay đổi

~~~text
Queue giao message A → consumer #1 xử lý 2 giây.
Queue giao message B → consumer #2 xử lý 100 ms.

B có thể hoàn tất trước A.
~~~

Nếu workflow yêu cầu cập nhật trạng thái order theo đúng thứ tự, không nên tăng concurrency mà không có ordering strategy. Một số broker hỗ trợ message grouping như JMSXGroupID, nhưng cần integration tests để chứng minh behavior trong topology đang chạy.

### 9.2. Annotation concurrency có thể override factory

~~~java
@JmsListener(
    destination = "orders.bulk",
    containerFactory = "bulkListenerFactory",
    concurrency = "2-5")
public void onBulk(String body) { /* ... */ }
~~~

Đây là snippet. Concurrency khai báo ở endpoint có thể override mặc định của factory cho listener ấy. Nếu kiến trúc quản lý concurrency tập trung, tránh override rải rác không được review.

### 9.3. Topic không giống queue

Với Queue, thêm consumers thường là competing-consumer pattern. Với Topic, semantics dựa trên subscription; nhiều consumers của subscription không shared có thể gây trùng delivery hoặc lỗi provider. Durable subscription còn yêu cầu identity/clientId và subscription name được quản lý theo quy tắc JMS provider.

Không áp setConcurrency("3-10") của queue vào topic mà chưa thiết kế shared/durable subscription. Factory topic thường được tách riêng và được kiểm tra bằng broker thật.

## 10. Transaction và acknowledgement

### 10.1. Local JMS transaction

~~~java
factory.setSessionTransacted(true);
~~~

Với DefaultMessageListenerContainer, cách này cho phép một lời gọi listener nhận message trong local JMS transaction. Khi method xử lý xong bình thường và commit, message được acknowledge theo transaction. Khi lỗi phù hợp thoát ra ngoài, transaction có thể rollback; broker redeliver theo chính sách.

Điều này **không** biến message processing thành exactly-once end-to-end. Consumer cần idempotency key vì có thể nhận lại message sau rollback hoặc lỗi giữa side effect và commit.

### 10.2. Nếu listener nuốt exception

~~~java
@JmsListener(destination = "orders.incoming")
public void handle(String body) {
    try {
        processOrder(body);
    } catch (RuntimeException ex) {
        // Nếu chỉ log rồi return, container có thể coi là thành công.
    }
}
~~~

Đây là anti-pattern: nếu nghiệp vụ cần retry, exception phải được propagate hoặc có chính sách failure explicit. Ghi log rồi trả về bình thường trong một transacted session có thể khiến container commit dù xử lý thất bại.

### 10.3. AUTO_ACKNOWLEDGE và nguy cơ mất redelivery

Trong DefaultMessageListenerContainer, AUTO_ACKNOWLEDGE có semantics khiến acknowledgement diễn ra trước khi user listener được thực thi; do đó lỗi listener có thể không dẫn đến redelivery. Spring khuyến nghị setSessionTransacted(true) hoặc transaction manager phù hợp khi cần rollback đáng tin cậy.

Đừng thay đổi ack mode chỉ dựa trên tên hằng số; JMS provider, container class và transaction config cùng quyết định hành vi thực tế.

### 10.4. External transaction manager

~~~java
factory.setTransactionManager(jmsTransactionManager);
~~~

Snippet cần một PlatformTransactionManager được inject phù hợp với resources. Một JmsTransactionManager cục bộ có thể quản lý JMS nhưng **không tự gom JDBC database** vào cùng transaction. Muốn XA/JTA atomicity giữa JMS và DB cần JTA coordinator, XA-capable ConnectionFactory/DataSource và hạ tầng phù hợp.

Trong hệ thống không cần/không thể dùng XA, kiến trúc transactional outbox + idempotency/reconciliation thường thực tế hơn. Dù dùng cách nào, cần giới hạn retry, redelivery backoff, poison message management và DLQ policy ở broker.

### 10.5. Boot default không giống manual factory

Spring Boot default JMS listener factory có thể được cấu hình transactional theo policy của Boot. Nếu thay thế bằng manual bean chỉ gọi setConnectionFactory, **không được** suy rằng transactional policy và transaction manager auto-configured vẫn được áp như trước. Dùng configurer nếu muốn bảo toàn Boot defaults, rồi override tường minh.

## 11. MessageConverter và method signature

~~~java
@JmsListener(destination = "orders.incoming")
public void receive(String body) {
    // TextMessage có thể được chuyển thành String.
}
~~~

Default SimpleMessageConverter của Spring xử lý các JMS Message types phổ biến như TextMessage, BytesMessage và MapMessage tương ứng với String/byte[]/Map. Nếu producer gửi JSON trong TextMessage, default converter thường trả về String, **không tự deserialise thành một record bất kỳ**.

### 11.1. Cấu hình Jackson MessageConverter

~~~java
@Bean
MessageConverter converter(ObjectMapper mapper) {
    MappingJackson2MessageConverter c =
            new MappingJackson2MessageConverter();
    c.setObjectMapper(mapper);
    c.setTargetType(MessageType.TEXT);
    c.setTypeIdPropertyName("PayloadType");
    c.setTypeIdMappings(
            Map.of("order-created-v1", OrderCreatedEvent.class));
    return c;
}
~~~

Đây là snippet trong @Configuration với các imports Spring JMS/Jackson/java.util.Map và DTO OrderCreatedEvent sẵn có. Theo Spring JMS, MappingJackson2MessageConverter thường cần type-id property để chuyển từ JMS message sang DTO đúng class.

Khi manual factory:

~~~java
factory.setMessageConverter(converter);
~~~

Đây là snippet sử dụng bean converter đã inject. Nếu Boot configurer được sử dụng, converter auto-configured thường được áp vào factory dựa trên beans/properties; kiểm tra lại khi tạo custom factory.

**Quan trọng:** cấu hình converter cho listener factory **không tự thay đổi** JmsTemplate bean được ứng dụng tạo riêng. Producer và consumer phải thống nhất wire format, target type, type ID và Jackson settings.

### 11.2. @Header, @Payload và jakarta.jms.Message

@JmsListener có thể nhận String/DTO, raw jakarta.jms.Message, jakarta.jms.Session hoặc các annotated parameters như @Header. Spring Messaging argument resolution hoạt động bên trên JMS layer, nên một exception “could not resolve method argument” không nhất thiết là lỗi broker.

Với DTO, cần validate payload ngay tại consumer boundary; message converter không quyết định semantics của null, số tiền, thời gian và schema phiên bản nghiệp vụ.

## 12. DestinationResolver và selector trong listener factory

### 12.1. DestinationResolver

Tên String trong @JmsListener được chuyển thành jakarta.jms.Destination bởi DestinationResolver của container. Có thể cấu hình:

~~~java
factory.setDestinationResolver(
        new DynamicDestinationResolver());
~~~

Đây là snippet; import đúng org.springframework.jms.support.destination.DynamicDestinationResolver. Trong enterprise/JNDI deployment có thể thay bằng JndiDestinationResolver hoặc custom resolver.

**Không nhầm:** nếu chỉ gọi jmsTemplate.setDestinationResolver(...) thì các @JmsListener không tự dùng resolver đó. Producer JmsTemplate và listener factory phải được cấu hình tương ứng để tránh một bên gửi queue vật lý nhưng bên kia lookup JNDI tên khác.

### 12.2. Selector

~~~java
@JmsListener(
    destination = "orders.incoming",
    selector = "EventType = 'ORDER_CREATED'",
    containerFactory = "jmsListenerContainerFactory")
public void handle(String payload) { /* ... */ }
~~~

Selector lọc dựa trên JMS headers/properties, không trực tiếp truy vấn JSON body. Nếu producer không gắn property EventType đúng kiểu, message không khớp dù JSON body chứa eventType tương tự.

### 12.3. Reply QoS

Factory có thể cấu hình chất lượng gửi cho response messages từ annotated endpoints khi dùng @SendTo hoặc JMSReplyTo:

~~~java
QosSettings replyQos = new QosSettings();
replyQos.setPriority(2);
replyQos.setTimeToLive(10_000L);
factory.setReplyQosSettings(replyQos);
~~~

Đây là snippet; QosSettings thuộc org.springframework.jms.support.QosSettings. Nó không thay đổi TTL hoặc priority của **message đầu vào**.

## 13. Dự án Java 17 chạy được: Spring Boot 3.3 + ActiveMQ Artemis

Demo chứng minh bean jmsListenerContainerFactory được đăng ký và thực tế tạo một container nhận message bằng @JmsListener. Chúng ta sử dụng String payload để tập trung vào registration/lifecycle, không thêm JSON converter.

### 13.1. Chuẩn bị broker

Cần JDK 17+, Maven, Docker và TCP 61616 trống. Khởi động broker Artemis:

~~~bash
docker run --detach --rm --name jms-factory-lab \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Đợi broker khởi động xong; có thể xem log bằng docker logs jms-factory-lab. Image demo thường cấu hình credentials artemis/artemis cho môi trường học; không dùng credentials demo trong production.

Broker cần cho phép dùng hoặc tự tạo queue demo.factory.orders. Dự án chạy trên broker/queue **sạch** để tránh message từ lần thực hành trước.

Cấu trúc thư mục:

~~~text
spring-jms-factory-lab/
├── pom.xml
└── src/main/
    ├── java/example/jmsfactory/
    │   ├── JmsFactoryLabApplication.java
    │   ├── JmsFactoryConfiguration.java
    │   └── OrderReceiver.java
    └── resources/application.properties
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>spring-jms-factory-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
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

Đây là phiên bản cố định để tái lập demo Spring Framework 6.x/Jakarta JMS. Khi đưa vào production, chọn bản Spring Boot được bảo trì và kiểm thử dependency security theo chính sách tổ chức.

### 13.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

Không chạy web server. Chương trình gửi message từ CommandLineRunner sau khi Spring context được khởi tạo và listener container auto-start theo lifecycle.

### 13.4. JmsFactoryConfiguration.java

~~~java
package example.jmsfactory;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsFactoryConfiguration {

    @Bean("jmsListenerContainerFactory")
    public DefaultJmsListenerContainerFactory listenerFactory(
            ConnectionFactory cf) {

        DefaultJmsListenerContainerFactory f =
                new DefaultJmsListenerContainerFactory();
        f.setConnectionFactory(cf);
        f.setPubSubDomain(false);
        f.setSessionTransacted(true);
        f.setConcurrency("1");
        f.setReceiveTimeout(1_000L);
        return f;
    }
}
~~~

Đây là file Java hoàn chỉnh. Bean factory có chính xác tên jmsListenerContainerFactory nên listener không cần khai báo containerFactory. setConcurrency("1") đơn giản hóa demo và tránh tăng số sessions/consumers không cần thiết. Local JMS transaction giúp ack/rollback theo transaction.

### 13.5. OrderReceiver.java

~~~java
package example.jmsfactory;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderReceiver {

    private final CountDownLatch latch = new CountDownLatch(1);
    private final AtomicReference<String> last =
            new AtomicReference<>();

    @JmsListener(
        id = "orderEndpoint",
        destination = "demo.factory.orders")
    public void onOrder(String payload) {
        last.set(payload);
        latch.countDown();
    }

    public boolean waitForMessage(long seconds)
            throws InterruptedException {
        return latch.await(seconds, TimeUnit.SECONDS);
    }

    public String getLast() {
        return last.get();
    }
}
~~~

Lớp này là Spring @Component, được component-scan bởi @SpringBootApplication cùng package cha. Listener method nhận String nhờ default converter cho TextMessage.

CountDownLatch và AtomicReference là công cụ **chỉ để xác định output minh họa**; chúng không phải hệ thống job tracking hay ack logic production.

### 13.6. JmsFactoryLabApplication.java

~~~java
package example.jmsfactory;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsFactoryLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsFactoryLabApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JmsTemplate template, OrderReceiver receiver) {
        return args -> {
            template.convertAndSend(
                    "demo.factory.orders", "ORDER-42");
            System.out.println("sent: ORDER-42");

            if (!receiver.waitForMessage(10)) {
                throw new IllegalStateException(
                        "Listener did not receive within 10 seconds");
            }
            System.out.println(
                    "listener received: " + receiver.getLast());
        };
    }
}
~~~

Giải thích:

1. Boot tạo ConnectionFactory và JmsTemplate từ Artemis starter.
2. Spring tạo JmsFactoryConfiguration và bean jmsListenerContainerFactory.
3. @EnableJms/Boot infrastructure phát hiện @JmsListener trên OrderReceiver.
4. Factory sinh một DefaultMessageListenerContainer và listener được start.
5. CommandLineRunner gửi TextMessage chứa ORDER-42 đến queue.
6. Container nhận message, chuyển payload thành String và gọi OrderReceiver.onOrder.
7. CountDownLatch mở, CommandLineRunner in kết quả đã nhận. Nếu listener không chạy hoặc không nhận trong 10 giây, chương trình báo lỗi.

**Lưu ý quan trọng:** latch được countdown khi handler chạy, chưa phải bằng chứng transaction đã commit thành công trong broker. Demo chỉ kiểm chứng listener được đăng ký và gọi. Muốn chứng minh ack/commit/idempotency cần integration tests riêng.

### 13.7. Chạy và output

Trong thư mục có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Khi broker chạy đúng, queue sạch và không có competing consumer, hai dòng do application tự in:

~~~text
sent: ORDER-42
listener received: ORDER-42
~~~

Spring Boot/Artemis có thể ghi thêm log. Vì listener container là thành phần chạy liên tục, tiến trình **có thể tiếp tục hoạt động** sau hai dòng trên; nhấn Ctrl+C để dừng app khi kiểm tra xong. Dừng broker sau đó:

~~~bash
docker stop jms-factory-lab
~~~

### 13.8. Các thí nghiệm hữu ích

- Đổi @Bean name thành ordersFactory nhưng không sửa @JmsListener: kiểm tra startup/factory resolution; Spring Boot có thể auto-register default khác tùy conditions, nên **phải kiểm tra bean thực tế** thay vì đoán.
- Giữ bean name ordersFactory và đặt containerFactory="ordersFactory" trên annotation; quan sát listener sử dụng factory ấy.
- Đổi setConcurrency("1") thành "2-4", gửi nhiều message; quan sát throughput/ordering.
- Thử gửi một message dạng bytes trong khi method nhận String; kiểm tra converter và logs.
- Thử listener ném RuntimeException khi Session transacted; quan sát broker redelivery/DLQ.
- Đổi domain thành Topic nhưng sender vẫn dùng Queue; giải thích vì sao hai bên không giao tiếp đúng.
- Dùng JmsListenerEndpointRegistry lấy endpoint "orderEndpoint" và kiểm tra isRunning.

## 14. Quản lý listener containers bằng JmsListenerEndpointRegistry

Factory bean là template tạo container; những containers do annotation infrastructure sinh có thể được quản lý qua registry.

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;

MessageListenerContainer container =
        registry.getListenerContainer("orderEndpoint");

if (container != null) {
    System.out.println(container.isRunning());
}
~~~

Snippet này cần biến registry là bean JmsListenerEndpointRegistry được inject; không phải file chạy độc lập.

Khi bảo trì, registry có các operation start()/stop() cho registered listener containers:

~~~java
registry.stop();
registry.start();
~~~

**Không dùng stop/start như một cách xóa message**. Message vẫn chịu broker policy, prefetch/in-flight delivery và JMS transaction. Khi rolling deployment, cần graceful shutdown, readiness/drain và timeout kiểm soát.

Nếu @JmsListener không khai báo id, Spring có thể tạo id nội bộ; với hệ thống cần quản lý runtime, nên đặt id **duy nhất và ổn định** để dễ monitoring. Endpoint id không đồng nghĩa destination name.

## 15. Khi nào cần JmsListenerConfigurer?

Cách @Bean name jmsListenerContainerFactory là đường đơn giản. Với yêu cầu đặc biệt, JmsListenerConfigurer cho phép cấu hình JmsListenerEndpointRegistrar để chọn default factory hoặc đăng ký endpoints theo chương trình.

~~~java
@Configuration
@EnableJms
class RegistrarConfig implements JmsListenerConfigurer {

    private final JmsListenerContainerFactory<?> selectedFactory;

    RegistrarConfig(
            @Qualifier("priorityListenerFactory")
            JmsListenerContainerFactory<?> selectedFactory) {
        this.selectedFactory = selectedFactory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {
        registrar.setContainerFactory(selectedFactory);
    }
}
~~~

Đây là snippet, cần import @Configuration, @EnableJms, @Qualifier và các lớp JmsListenerConfigurer/JmsListenerEndpointRegistrar/JmsListenerContainerFactory. Bean priorityListenerFactory phải tồn tại; đoạn này không tự tạo factory.

JmsListenerConfigurer cũng có thể register SimpleJmsListenerEndpoint programmatically. Chỉ dùng khi registration dựa trên runtime metadata hoặc khi cần thay factory mặc định có lý do; không cần phức tạp hóa mọi ứng dụng chỉ có vài @JmsListener methods.

## 16. Những lỗi phổ biến và cách debug

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| Annotation tồn tại nhưng method không chạy | Chưa bật JMS infrastructure, bean nằm ngoài component scan | Kiểm tra @EnableJms hoặc Boot auto-config, component scan. |
| Không tìm thấy default factory | Bean không tên jmsListenerContainerFactory | Kiểm tra BeanFactory và containerFactory attribute. |
| Đã có nhiều factory nhưng dùng sai | Endpoint không chỉ định factory | Ghi đúng containerFactory, kiểm tra registry/container. |
| Bean tạo thủ công bỏ qua Boot properties | Không dùng configurer | Dùng Boot configurer hoặc tự set các properties. |
| Gửi được nhưng không nhận | Sai broker, destination, queue/topic, selector hoặc ACL | So sánh ConnectionFactory, DestinationResolver và broker stats. |
| Listener ném lỗi conversion | Converter/argument mismatch | Kiểm tra Message type, Jackson type ID, DTO, logs. |
| Lỗi trong handler mà không redeliver | AUTO_ACKNOWLEDGE, swallowed exception | Dùng transaction policy đúng và cho lỗi propagate. |
| Message xử lý lặp sau restart | JMS redelivery hoặc retry | Thêm idempotency và broker DLQ/retry config. |
| Concurrency cao khiến sai thứ tự | Nhiều consumers cạnh tranh | Giảm concurrency hoặc thiết kế grouping/partition. |
| Topic nhận message không đúng | Subscription/shared/durable cấu hình sai | Tách topic factory và test broker thật. |
| Resource leak/too many sessions | Caching wrapper/lifecycle hoặc quá nhiều endpoints | Kiểm tra native ConnectionFactory và container cache. |
| Factory không connect khi startup | Broker chưa chạy/credentials lỗi | Xem connection URL, logs recovery, firewall, ACL. |
| Không thấy listener container dưới tên bean | Container được infrastructure tạo, registry quản lý | Truy vấn JmsListenerEndpointRegistry. |
| Selector chạy nhưng không match | Property thiếu/sai kiểu, JSON field không phải JMS property | Inspect message headers/properties. |
| Stop container nhưng message vẫn có | Stop không xóa queue, message vẫn nằm broker | Dùng broker metrics, không purge tự động. |
| Bật @Transactional nhưng DB/JMS không nguyên tử | Chỉ có transaction manager cục bộ | Thiết kế outbox/JTA-XA theo yêu cầu thực. |

### 16.1. Checklist debug có thứ tự

1. Có ConnectionFactory bean thật và đang connect **đúng broker** chưa?
2. ApplicationContext có factory bean đúng tên, đúng type chưa?
3. Infrastructure @EnableJms/Boot có phát hiện @JmsListener method chưa?
4. @JmsListener có id, destination, selector, containerFactory đúng không?
5. Registry tìm được container theo endpoint id không, container.isRunning() ra sao?
6. JMS broker có queue/topic, subscriber/consumer, ACL và route đúng không?
7. Listener converter/DTO/argument có phù hợp message type không?
8. Transaction/ack/rollback, retry, DLQ và exception handling có đúng policy không?
9. Concurrency/executor/cache có gây starvation hay race/order issue không?
10. Sender/consumer deployment version có cùng contract tên destination và payload không?

## 17. Các quyết định thiết kế production

### 17.1. Không biến factory thành singleton thay đổi runtime liên tục

Factory thường được cấu hình **khi bootstrap** trước khi nó tạo listener containers. Việc gọi factory.setConcurrency(...) sau khi containers đã được tạo không phải cách tin cậy để cập nhật mọi runtime containers đang chạy. Nếu cần thay đổi concurrency động, dùng management API phù hợp của container, restart/rollout hoặc chiến lược config được xác minh, không mutate bean rồi mong mọi listener tự đổi.

### 17.2. Dùng factory riêng cho policy thực sự khác

Một factory cho mọi listener đơn giản dễ bảo trì. Nhiều factories hợp lý khi:

- Workload cần queue/topic khác nhau.
- Concurrency/SLA khác nhau.
- Transaction manager hoặc security/connection factory khác nhau.
- Converter/payload version khác nhau.
- Retry/error/lifecycle cần tách rõ.

Đừng tạo hàng chục factories chỉ vì mỗi listener có một queue khác nhau; destination thường là thuộc tính của @JmsListener, còn factory quản lý **policy chung**.

### 17.3. Không dùng selector làm ranh giới bảo mật

Nếu listener dùng selector TenantId = 'A', điều đó chỉ là filter delivery, **không thay broker ACL/credentials hoặc tenant isolation**. Factory kết nối bằng tài khoản có quyền phù hợp mới là một lớp enforcement. Không log payload nhạy cảm trong ErrorHandler mà không masking.

### 17.4. Giám sát vận hành

Ít nhất nên có:

- Broker connection/session/consumer count.
- Queue depth, message age, processing rate, expiry count.
- Listener container started/stopped, recovery attempts.
- Failed processing, redelivery, DLQ/quarantine count.
- End-to-end latency, idempotency conflict.
- Thread/executor saturation, DB pool utilization.
- Schema conversion/validation errors.

Không chỉ tính “listener method đã gọi bao nhiêu lần” để kết luận business transaction committed thành công.

## 18. Câu hỏi tự kiểm tra

**1. DefaultJmsListenerContainerFactory có phải container trực tiếp nhận message không?** Không. Nó tạo DefaultMessageListenerContainer cho endpoint.

**2. Tên bean mặc định mà @JmsListener tìm là gì?** jmsListenerContainerFactory, trừ khi endpoint/registrar chỉ định factory khác.

**3. Spring Boot có luôn yêu cầu @EnableJms không?** Không. Boot auto-configuration có thể kích hoạt JMS annotated listener infrastructure; Spring Framework thuần thường cần @EnableJms.

**4. Khi nào nên dùng DefaultJmsListenerContainerFactoryConfigurer?** Khi tạo factory riêng trên Boot nhưng muốn kế thừa các defaults/properties thay vì manual reset.

**5. @JmsListener(containerFactory="...") chứa kiểu gì?** Tên Spring bean của JmsListenerContainerFactory, không phải destination.

**6. setConcurrency("3-10") là giới hạn toàn ứng dụng?** Không, là cấu hình cho mỗi container tạo từ factory.

**7. setSessionTransacted(true) có giúp rollback JMS khi listener throw exception không?** Có trong local JMS transaction khi cấu hình/provider phù hợp; vẫn cần retry/idempotency.

**8. Local JMS transaction có commit DB cùng lúc không?** Không tự động; cần JTA/XA hoặc kiến trúc nhất quán thay thế.

**9. Vì sao hai listener cùng Queue xử lý song song có thể đổi thứ tự?** Vì nhiều consumers có thể nhận và hoàn thành ở thời điểm khác nhau.

**10. Dùng factory Queue để nhận Topic được không?** Phải cấu hình đúng pubSubDomain và subscription semantics; không chỉ đổi destination String.

**11. Vì sao listener không nhận DTO từ JSON dù JmsTemplate gửi thành công?** Converter/target type/type ID/ObjectMapper hoặc method argument không tương thích.

**12. Ai có thể start/stop annotated JMS listener containers?** JmsListenerEndpointRegistry và container lifecycle API.

**13. Factory bean được đăng ký có chắc JMS listener đã chạy không?** Không; phải có annotation processing, endpoint hợp lệ, broker connection và container start.

**14. Vì sao nuốt exception trong listener nguy hiểm?** Container có thể commit/ack khi application silently fail, làm message không redeliver.

**15. Nên kiểm tra cái gì trước khi scale consumers lên 10?** Ordering, idempotency, broker/session limits, executor, DB pool, throughput và retry rates.

### Bài tập thực hành

1. Chạy project mục 13; xác nhận hai dòng stdout và quan sát container trong broker console.
2. Đổi bean name thành ordersFactory, thêm containerFactory="ordersFactory" trên listener; giải thích sự phụ thuộc tên bean.
3. Tạo một factory riêng cho topic và một factory riêng cho queue, test đúng publish/subscribe semantics.
4. Gửi 20 messages, tăng concurrency, đo thời gian xử lý và thứ tự hoàn thành.
5. Thử listener throw RuntimeException với setSessionTransacted(true), theo dõi redelivery và DLQ broker.
6. Tạo Configurer-based factory và dùng Boot properties min/max concurrency; so sánh với manual factory.
7. Gắn DynamicDestinationResolver/JndiDestinationResolver phù hợp; kiểm tra người gửi và listener cùng physical destination.
8. Thêm JMS property EventType ở producer rồi dùng @JmsListener selector; thử khi property thiếu.
9. Dùng JmsListenerEndpointRegistry tìm endpoint ID và kiểm tra isRunning.
10. Cấu hình MappingJackson2MessageConverter với type ID; gửi DTO và test conversion errors.
11. Cài hai listener cùng queue với selector khác nhau; quan sát message không match vẫn nằm trong broker.
12. Viết checklist triển khai production gồm credentials, transaction, concurrency, retry/DLQ, observability và shutdown.

## 19. Tài liệu tham khảo

- Spring Framework 6.2 — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — Using Spring JMS / Message Listener Containers: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Processing Messages Within Transactions: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Framework 6.2 — DefaultJmsListenerContainerFactory API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
- Spring Framework 6.2 — JmsListener API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/annotation/JmsListener.html
- Spring Framework 6.2 — JmsListenerEndpointRegistry API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html
- Spring Boot 3.4 — JMS reference: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Spring Boot 3.4 — DefaultJmsListenerContainerFactoryConfigurer API: https://docs.spring.io/spring-boot/3.4.4/api/java/org/springframework/boot/autoconfigure/jms/DefaultJmsListenerContainerFactoryConfigurer.html
- Spring guide — Messaging with JMS: https://spring.io/guides/gs/messaging-jms/
- Jakarta Messaging 3.1 specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Apache ActiveMQ Artemis Docker guide: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
