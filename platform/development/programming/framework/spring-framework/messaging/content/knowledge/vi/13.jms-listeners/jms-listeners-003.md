# Bật @EnableJms và khai báo @JmsListener trong Spring JMS

## 1. Annotation-driven listener là gì?

Spring JMS cho phép khai báo một phương thức Java làm message listener bằng annotation `@JmsListener`. Khi ứng dụng khởi động, Spring phát hiện các phương thức được đánh dấu, tạo listener endpoint và quản lý listener container để nhận message từ JMS destination.

Hai annotation trung tâm:

- **@EnableJms:** bật cơ chế phát hiện và đăng ký các phương thức `@JmsListener` trong Spring ApplicationContext.
- **@JmsListener:** khai báo destination và phương thức xử lý message.

Cơ chế này tách phần nghiệp vụ khỏi mã quản lý vòng đời JMS. Thay vì tự viết vòng lặp nhận message, tạo consumer và xử lý recovery, ứng dụng khai báo listener; Spring tạo và quản lý container dựa trên cấu hình.

~~~text
JMS Provider / Broker
        |
        v
Queue hoặc Topic
        |
        v
JmsListenerContainerFactory
        |
        v
MessageListenerContainer
        |
        v
@JmsListener method
        |
        v
Business service
~~~

`@EnableJms` không tạo broker, queue hoặc connection tới JMS provider. Ứng dụng vẫn phải cấu hình một `jakarta.jms.ConnectionFactory` hợp lệ và một listener container factory.

## 2. Bật @EnableJms

Đặt `@EnableJms` trên một lớp cấu hình được Spring quản lý:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {
    // Các bean JMS được khai báo ở đây.
}
~~~

Khi ApplicationContext khởi động, Spring đăng ký hạ tầng annotation-driven JMS. Các thành phần chính:

- `JmsListenerAnnotationBeanPostProcessor`: phát hiện annotation `@JmsListener` trên các bean và đăng ký endpoint tương ứng.
- `JmsListenerEndpointRegistry`: quản lý các listener container được tạo cho những endpoint đó.
- `JmsListenerContainerFactory`: tạo container thực thi từng endpoint.

Listener class phải là Spring bean. Thông thường dùng `@Component` cùng component scanning, hoặc khai báo bằng `@Bean`.

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void receive(String payload) {
        System.out.println("Received: " + payload);
    }
}
~~~

Nếu class không phải Spring bean, annotation trên phương thức sẽ không tự tạo listener. Tạo đối tượng bằng `new OrderListener()` ở ngoài container cũng không kích hoạt cơ chế phát hiện annotation.

`@JmsListener` là repeatable annotation: một phương thức có thể được gắn nhiều khai báo để nhận từ nhiều destination.

## 3. Khai báo JmsListenerContainerFactory

Mỗi `@JmsListener` cần một listener container factory để tạo container. Theo mặc định, Spring tìm bean có tên:

`jmsListenerContainerFactory`

Nếu dùng tên khác, khai báo tên đó trong thuộc tính `containerFactory` của `@JmsListener`. Factory mặc định chỉ cần thiết khi có ít nhất một endpoint không chỉ định factory riêng.

### 3.1. Cấu hình DefaultJmsListenerContainerFactory

Ví dụ cấu hình phổ biến:

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
        factory.setConcurrency("3-10");
        factory.setSessionTransacted(true);

        return factory;
    }
}
~~~

Các cấu hình quan trọng:

| Cấu hình | Ý nghĩa |
|---|---|
| `setConnectionFactory(...)` | ConnectionFactory mà listener container dùng để kết nối broker |
| `setConcurrency("3-10")` | Số consumer tối thiểu và tối đa cho container hỗ trợ concurrency |
| `setSessionTransacted(true)` | Dùng local JMS transaction cho session xử lý message |
| `setTransactionManager(...)` | Tham gia transaction do transaction manager bên ngoài quản lý |
| `setMessageConverter(...)` | Chuyển JMS Message thành payload Java và ngược lại |
| `setDestinationResolver(...)` | Phân giải tên destination thành đối tượng JMS Destination |
| `setPubSubDomain(true)` | Cấu hình destination dạng Topic thay vì Queue |
| `setErrorHandler(...)` | Nhận lỗi không được xử lý trong quá trình listener thực thi |
| `setAutoStartup(false)` | Không tự khởi động container khi ApplicationContext refresh |

`DefaultJmsListenerContainerFactory` tạo `DefaultMessageListenerContainer`. Đây là lựa chọn thường dùng cho ứng dụng cần quản lý transaction, recovery và concurrency.

### 3.2. Dùng factory có tên riêng

Một ứng dụng có thể có nhiều nhóm listener với cấu hình khác nhau:

~~~java
@Bean
DefaultJmsListenerContainerFactory ordersListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrency("2-6");
    factory.setSessionTransacted(true);
    return factory;
}

@Bean
DefaultJmsListenerContainerFactory auditListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrency("1");
    factory.setSessionTransacted(true);
    return factory;
}
~~~

Chọn factory cho từng listener:

~~~java
@JmsListener(
    id = "ordersListener",
    destination = "orders.queue",
    containerFactory = "ordersListenerFactory"
)
public void receiveOrder(String payload) {
    // Xử lý đơn hàng.
}

@JmsListener(
    id = "auditListener",
    destination = "audit.queue",
    containerFactory = "auditListenerFactory"
)
public void receiveAudit(String payload) {
    // Xử lý audit.
}
~~~

Factory riêng hữu ích khi listener khác nhau về concurrency, transaction, converter, destination type hoặc error handling.

## 4. Khai báo @JmsListener

Cách đơn giản nhất là chỉ định destination:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(String payload) {
    orderService.process(payload);
}
~~~

`destination` có thể là tên Queue hoặc Topic tùy cấu hình listener container factory. Với cấu hình mặc định `pubSubDomain=false`, Spring xử lý destination như Queue.

Các thuộc tính thường dùng:

| Thuộc tính | Vai trò |
|---|---|
| `id` | Định danh endpoint/container để quản lý và quan sát |
| `destination` | Tên Queue hoặc Topic cần lắng nghe |
| `containerFactory` | Tên bean factory tạo listener container |
| `selector` | JMS message selector để lọc message theo header/property |
| `subscription` | Tên durable subscription khi nghe Topic |
| `concurrency` | Ghi đè concurrency của factory cho endpoint |
| `autoStartup` | Quyết định container có tự khởi động cùng context không |

Ví dụ kết hợp các thuộc tính:

~~~java
@JmsListener(
    id = "priorityOrders",
    destination = "orders.queue",
    selector = "priority >= 5",
    concurrency = "2-4",
    containerFactory = "jmsListenerContainerFactory"
)
public void receivePriorityOrder(String payload) {
    orderService.processPriority(payload);
}
~~~

Selector là biểu thức JMS message selector áp dụng lên JMS headers và properties. Nó không truy vấn nội dung body của TextMessage hoặc JSON payload. Nếu cần lọc theo trường nằm trong body, hãy nhận message rồi kiểm tra trong code nghiệp vụ.

### 4.1. Dùng property placeholder cho destination

Không cần hard-code tên destination trong source. Có thể lấy tên từ cấu hình ứng dụng:

~~~java
@JmsListener(destination = "${app.jms.orders-destination}")
public void receiveOrder(String payload) {
    orderService.process(payload);
}
~~~

Trong file cấu hình, khai báo destination tương ứng:

~~~properties
app.jms.orders-destination=orders.queue
~~~

Spring resolve placeholder khi đăng ký endpoint. Có thể dùng SpEL nếu cần tham chiếu bean hoặc biểu thức cấu hình động, nhưng nên giữ destination dễ kiểm soát và có thể kiểm tra khi khởi động.

## 5. Queue, Topic và durable subscription

JMS có hai mô hình destination chính:

- **Queue (point-to-point):** một message được giao cho một consumer trong nhóm consumer cạnh tranh.
- **Topic (publish-subscribe):** message được phát tới các subscriber đang đăng ký; durable subscription cho phép broker giữ message theo chính sách khi subscriber offline.

### 5.1. Nghe Topic

Với `DefaultJmsListenerContainerFactory`, bật pub/sub domain:

~~~java
@Bean
DefaultJmsListenerContainerFactory topicListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    return factory;
}
~~~

Khai báo listener dùng factory này:

~~~java
@JmsListener(
    id = "newsSubscriber",
    destination = "news.topic",
    containerFactory = "topicListenerFactory"
)
public void receiveNews(String news) {
    newsService.handle(news);
}
~~~

Nếu factory không được cấu hình pubSubDomain phù hợp, container có thể diễn giải tên destination sai loại hoặc không nhận được message như mong đợi.

### 5.2. Durable Topic subscription

Thuộc tính `subscription` của `@JmsListener` đặt tên subscription. Chỉ đặt tên này chưa đủ để bật durable subscription; container factory cũng cần cấu hình durable mode và client identity theo yêu cầu của provider.

~~~java
@Bean
DefaultJmsListenerContainerFactory durableTopicListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setClientId("billing-service-client");
    return factory;
}
~~~

Listener sử dụng durable subscription:

~~~java
@JmsListener(
    id = "billingEvents",
    destination = "billing.topic",
    subscription = "billing-service-subscription",
    containerFactory = "durableTopicListenerFactory"
)
public void receiveBillingEvent(String payload) {
    billingService.process(payload);
}
~~~

Các điểm cần nhớ:

- Durable subscription chỉ áp dụng cho Topic.
- Client ID phải ổn định và duy nhất theo phạm vi mà broker quy định.
- Tên subscription phải ổn định và duy nhất trong client ID đó.
- Một durable subscription thông thường chỉ có một consumer hoạt động tại một thời điểm. Muốn nhiều consumer dùng chung subscription, cần shared subscription và JMS provider hỗ trợ JMS 2.0 trở lên; cấu hình `setSubscriptionShared(true)` trên factory.
- Concurrency của listener phải tương thích với loại subscription đang dùng.

Không dùng cùng một durable subscription identity cho nhiều ứng dụng độc lập nếu chúng không được thiết kế để chia sẻ subscription.

## 6. Kiểu tham số của listener method

Spring chuyển JMS message thành các tham số method dựa trên `MessageConverter` và argument resolver.

Các kiểu tham số thường dùng:

- **Payload Java:** String, DTO hoặc kiểu domain nếu converter hỗ trợ.
- **jakarta.jms.Message:** message JMS gốc khi cần truy cập property, delivery mode, reply-to hoặc metadata của provider.
- **jakarta.jms.Session:** JMS Session hiện tại khi cần thao tác JMS cấp thấp.
- **org.springframework.messaging.Message<?>:** message Spring với payload và headers đã được ánh xạ.
- **@Header:** lấy một header cụ thể.
- **@Headers:** lấy tập headers vào một Map.
- **@Payload:** đánh dấu rõ tham số là payload.
- **@Valid:** yêu cầu validation payload nếu đã cấu hình validator phù hợp.

Ví dụ:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        @Payload OrderCreated event,
        @Header(JmsHeaders.MESSAGE_ID) String messageId,
        @Header(name = "correlationId", required = false)
        String correlationId) {

    orderService.process(event, messageId, correlationId);
}
~~~

`JmsHeaders.MESSAGE_ID` là header Spring ánh xạ từ JMS message ID. Với header tùy chọn, đặt `required=false` để tránh lỗi khi message không có giá trị đó.

Nếu cần kiểm soát đầy đủ message:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        jakarta.jms.Message jmsMessage,
        jakarta.jms.Session session) throws JMSException {

    String messageId = jmsMessage.getJMSMessageID();
    String correlationId = jmsMessage.getJMSCorrelationID();

    // Xử lý theo yêu cầu của ứng dụng.
}
~~~

Không nên đưa toàn bộ JMS Message hoặc Session vào tầng domain. Hãy giữ API JMS ở adapter/listener layer và chuyển dữ liệu cần thiết thành đối tượng nghiệp vụ.

## 7. MessageConverter và chuyển đổi payload

JMS truyền các loại message như TextMessage, BytesMessage, MapMessage, ObjectMessage và Message. Listener thường muốn nhận DTO hoặc String thay vì tự đọc từng loại JMS message.

Spring JMS dùng `MessageConverter` để chuyển đổi giữa JMS message và object Java.

### 7.1. SimpleMessageConverter mặc định

Nếu không cấu hình converter khác, Spring sử dụng `SimpleMessageConverter`. Những ánh xạ thông dụng:

| JMS message | Java object |
|---|---|
| TextMessage | String |
| BytesMessage | byte[] |
| MapMessage | Map |
| ObjectMessage | Serializable object |

Vì vậy, ví dụ sau nhận trực tiếp String từ TextMessage:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(String payload) {
    System.out.println(payload);
}
~~~

SimpleMessageConverter thuận tiện cho kiểu dữ liệu đơn giản. Với DTO phức tạp, nên cấu hình converter có schema/format rõ ràng.

### 7.2. JSON converter cho DTO

Có thể dùng `MappingJackson2MessageConverter`:

~~~java
@Bean
MappingJackson2MessageConverter jacksonJmsMessageConverter() {
    MappingJackson2MessageConverter converter =
        new MappingJackson2MessageConverter();

    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    return converter;
}

@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory,
        MappingJackson2MessageConverter converter) {

    DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setMessageConverter(converter);
    factory.setSessionTransacted(true);
    return factory;
}
~~~

Khi converter được cấu hình cho factory, listener có thể nhận DTO:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(OrderCreated event) {
    orderService.process(event);
}
~~~

Producer cũng phải dùng converter tương thích. Hãy thống nhất JSON format, type mapping, schema version và quy tắc xử lý khi payload không hợp lệ giữa producer và consumer.

Không bật cơ chế deserialize Java object tùy ý từ nguồn không đáng tin cậy. Với message qua broker hoặc từ hệ thống ngoài, JSON/Bytes cùng schema rõ ràng thường dễ kiểm soát hơn ObjectMessage chứa Java serialized object.

## 8. Concurrency và thứ tự xử lý

Listener container có thể chạy nhiều consumer để tăng throughput. Với DefaultJmsListenerContainerFactory:

~~~java
factory.setConcurrency("3-10");
~~~

Chuỗi `3-10` có nghĩa container bắt đầu với tối thiểu 3 consumer và có thể tăng tới 10 theo nhu cầu. Một giá trị đơn như `4` đặt upper limit là 4, với minimum mặc định là 1. Muốn cố định đúng 4 consumer, dùng `4-4`.

Có thể ghi đè concurrency cho một endpoint:

~~~java
@JmsListener(
    destination = "orders.queue",
    concurrency = "2-6"
)
public void receive(String payload) {
    orderService.process(payload);
}
~~~

Khi concurrency lớn hơn một:

- Nhiều listener invocation có thể chạy đồng thời.
- Bean listener và service được gọi phải thread-safe.
- Thứ tự hoàn tất xử lý có thể khác thứ tự broker giao message.
- Throughput có thể tăng, nhưng tải lên database và dịch vụ downstream cũng tăng.
- Nếu cần tuần tự hóa theo orderId hoặc aggregate key, phải thiết kế partitioning/ordering riêng.

Một consumer đơn thường dễ giữ thứ tự xử lý hơn, nhưng giới hạn throughput. Đừng tăng concurrency chỉ dựa trên số lượng message; hãy đo thời gian xử lý, năng lực broker và tài nguyên downstream.

## 9. Acknowledgment, transaction và redelivery

Độ tin cậy của listener phụ thuộc acknowledgment mode và transaction.

### 9.1. AUTO_ACKNOWLEDGE và sessionTransacted

Với `DefaultMessageListenerContainer`, chế độ `AUTO_ACKNOWLEDGE` mặc định acknowledge message trước khi listener method chạy. Vì vậy, nếu listener ném exception, message không tự được redeliver theo chế độ mặc định này.

Để listener xử lý trong local JMS transaction, cấu hình:

~~~java
factory.setSessionTransacted(true);
~~~

Khi listener hoàn tất bình thường, session commit. Nếu listener ném exception ra khỏi invocation, transaction có thể rollback và broker có thể redeliver message theo chính sách provider.

Để cơ chế này hoạt động đúng:

- Không nuốt exception nếu muốn container biết xử lý thất bại.
- Hiểu giới hạn số lần redelivery và dead-letter policy của broker.
- Đảm bảo nghiệp vụ có tính idempotent vì message có thể được giao lại.
- Không giả định rollback JMS tự rollback một transaction database độc lập.

### 9.2. Transaction manager bên ngoài

Nếu cần phối hợp JMS với transaction manager của ứng dụng, có thể cấu hình `setTransactionManager(...)` trên factory bằng transaction manager phù hợp. Môi trường JTA/XA có thể phối hợp nhiều resource nếu provider và datasource hỗ trợ XA.

`setSessionTransacted(true)` tạo local JMS transaction. Nó không tự biến thao tác database và JMS thành một distributed atomic transaction.

Nếu không dùng XA, cân nhắc Outbox pattern, idempotency key hoặc eventual consistency để xử lý tình huống database commit thành công nhưng gửi message thất bại, hoặc ngược lại.

### 9.3. Redelivery và dead-letter

Spring listener container không tự định nghĩa đầy đủ chính sách lưu trữ message lỗi cho mọi broker. Redelivery delay, maximum delivery attempts, dead-letter address/queue và message expiry thường do JMS provider cấu hình.

Hãy xác định rõ:

1. Lỗi nào được retry?
2. Số lần retry tối đa là bao nhiêu?
3. Khi hết số lần retry, message được chuyển đi đâu?
4. Ai theo dõi và xử lý dead-letter?
5. Consumer có thể xử lý lặp an toàn không?

Không retry vô hạn message lỗi dữ liệu cố định vì có thể gây vòng lặp và chiếm tài nguyên queue.

## 10. Error handling và giám sát listener

Có thể cấu hình ErrorHandler cho listener container:

~~~java
factory.setErrorHandler(exception -> {
    // Ghi log/metric an toàn; không log token hoặc payload nhạy cảm.
});
~~~

ErrorHandler là nơi quan sát lỗi phát sinh trong quá trình listener thực thi. Nó không thay thế transaction rollback, provider redelivery hoặc dead-letter policy.

Một số điểm cần theo dõi:

- Số message đã nhận và đã xử lý thành công.
- Số listener exception và số lần redelivery.
- Consumer count và trạng thái listener container.
- Queue depth, message age và dead-letter count.
- Thời gian xử lý và lỗi downstream.
- Connection recovery và thời gian container ngừng nhận message.

Dùng correlation ID hoặc message ID để liên kết log. Tránh ghi toàn bộ payload, credential hoặc header nhạy cảm.

## 11. Reply từ listener bằng @SendTo

Listener method có thể trả về giá trị. Spring chuyển giá trị đó thành JMS message và gửi phản hồi:

- Nếu request có JMSReplyTo, phản hồi được gửi tới destination đó.
- Nếu không có JMSReplyTo, có thể khai báo destination mặc định bằng `@SendTo`.

Ví dụ:

~~~java
@JmsListener(destination = "orders.request")
@SendTo("orders.reply")
public OrderStatus process(OrderCommand command) {
    return orderService.process(command);
}
~~~

Có thể trả về Spring `Message<?>` nếu cần thêm headers vào phản hồi. Nếu destination phản hồi cần được tính ở runtime, dùng `JmsResponse` để gói response cùng destination cụ thể.

Chỉ dùng reply pattern khi producer thực sự chờ phản hồi. Với event một chiều, listener thường nên trả về void để tránh tạo message không cần thiết.

## 12. Quản lý listener container

Các listener container được tạo bởi `@JmsListener` được quản lý trong `JmsListenerEndpointRegistry`.

Nếu gán ID cho endpoint:

~~~java
@JmsListener(id = "ordersListener", destination = "orders.queue")
public void receive(String payload) {
    orderService.process(payload);
}
~~~

Có thể truy cập container theo ID:

~~~java
@Autowired
private JmsListenerEndpointRegistry registry;

public void stopOrdersListener() {
    MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

    if (container != null) {
        container.stop();
    }
}
~~~

Registry cho phép truy xuất và quản lý lifecycle của các listener container. Có thể dùng để start/stop listener theo trạng thái ứng dụng, feature flag hoặc quy trình vận hành.

Nếu annotation đặt `autoStartup=false`, container không tự chạy khi context khởi động; ứng dụng có thể chủ động start sau khi điều kiện cần thiết đã sẵn sàng.

## 13. Ví dụ Java 17+ chạy với embedded Artemis broker

Ví dụ sau khởi động một broker Artemis nhúng, cấu hình Spring với `@EnableJms`, đăng ký `@JmsListener`, gửi ba message bằng JmsTemplate và đợi listener xử lý.

**Cấu trúc dự án**

~~~text
jms-listener-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          JmsListenerDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jms-listener-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
            <version>2.37.0</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.37.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/JmsListenerDemo.java**

~~~java
package demo;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Session;
import org.apache.activemq.artemis.core.config.impl.ConfigurationImpl;
import org.apache.activemq.artemis.core.server.embedded.EmbeddedActiveMQ;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

public class JmsListenerDemo {

    public static void main(String[] args) throws Exception {
        EmbeddedActiveMQ broker = new EmbeddedActiveMQ();
        broker.setConfiguration(new ConfigurationImpl()
            .setPersistenceEnabled(false)
            .setSecurityEnabled(false)
            .addAcceptorConfiguration("netty", "tcp://127.0.0.1:61616"));
        broker.start();

        ActiveMQConnectionFactory nativeFactory =
            new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

        try {
            try (Connection connection = nativeFactory.createConnection();
                 Session session = connection.createSession(
                     false, Session.AUTO_ACKNOWLEDGE)) {
                session.createQueue("orders.queue");
            }

            OrderListener listener = new OrderListener(3);

            try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

                context.registerBean(
                    "nativeConnectionFactory",
                    ConnectionFactory.class,
                    () -> nativeFactory
                );
                context.registerBean(
                    "orderListener",
                    OrderListener.class,
                    () -> listener
                );
                context.register(JmsConfiguration.class);
                context.refresh();

                JmsTemplate template = context.getBean(JmsTemplate.class);
                template.convertAndSend("orders.queue", "order-1");
                template.convertAndSend("orders.queue", "order-2");
                template.convertAndSend("orders.queue", "order-3");

                if (!listener.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "Timed out waiting for JMS messages"
                    );
                }

                List<String> received = new ArrayList<>(listener.messages());
                Collections.sort(received);
                System.out.println("receivedCount=" + received.size());
                System.out.println("messages=" + received);
            }
        }
        finally {
            nativeFactory.close();
            broker.stop();
        }
    }

    @Configuration
    @EnableJms
    static class JmsConfiguration {

        @Bean
        DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
                ConnectionFactory nativeConnectionFactory) {

            DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
            factory.setConnectionFactory(nativeConnectionFactory);
            factory.setConcurrency("1-2");
            factory.setSessionTransacted(true);
            return factory;
        }

        @Bean
        JmsTemplate jmsTemplate(ConnectionFactory nativeConnectionFactory) {
            return new JmsTemplate(nativeConnectionFactory);
        }
    }

    @Component
    static class OrderListener {
        private final CountDownLatch latch;
        private final List<String> messages =
            Collections.synchronizedList(new ArrayList<>());

        OrderListener(int expectedMessages) {
            this.latch = new CountDownLatch(expectedMessages);
        }

        @JmsListener(destination = "orders.queue")
        public void receive(String payload) {
            messages.add(payload);
            latch.countDown();
        }

        boolean await(long timeout, TimeUnit unit) throws InterruptedException {
            return latch.await(timeout, unit);
        }

        List<String> messages() {
            synchronized (messages) {
                return List.copyOf(messages);
            }
        }
    }
}
~~~

Chạy từ thư mục `jms-listener-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.JmsListenerDemo
~~~

**Kết quả từ chương trình**

~~~text
receivedCount=3
messages=[order-1, order-2, order-3]
~~~

Giải thích:

1. Embedded Artemis broker mở TCP acceptor tại cổng 61616.
2. ConnectionFactory của Artemis được đăng ký làm Spring bean.
3. `@EnableJms` bật annotation processing và đăng ký listener container.
4. Bean OrderListener có phương thức `@JmsListener` được phát hiện và lắng nghe `orders.queue`.
5. JmsTemplate gửi ba TextMessage.
6. Listener nhận payload dưới dạng String nhờ SimpleMessageConverter mặc định.
7. CountDownLatch đợi đủ ba message; danh sách được sắp xếp trước khi in để kết quả ổn định.

Ví dụ dùng broker nhúng để học và kiểm thử. Production cần cấu hình broker độc lập, credentials, TLS, destination provisioning, monitoring, transaction và redelivery policy phù hợp.

## 14. Lỗi thường gặp

1. **Quên @EnableJms:** Spring không bật annotation-driven listener infrastructure; phương thức @JmsListener không được đăng ký.
2. **Listener không phải Spring bean:** annotation chỉ được phát hiện trên bean trong ApplicationContext.
3. **Thiếu factory mặc định:** nếu không chỉ định `containerFactory`, Spring tìm bean `jmsListenerContainerFactory`.
4. **Sai tên factory:** thuộc tính `containerFactory` phải khớp tên bean thực tế.
5. **Nhầm Queue và Topic:** kiểm tra `pubSubDomain` của factory và cấu hình destination ở broker.
6. **Selector lọc theo body:** JMS selector chỉ xét headers/properties, không truy vấn JSON hoặc TextMessage body.
7. **DTO không được convert:** cấu hình MessageConverter tương thích ở producer và listener factory.
8. **Concurrency quá cao:** có thể gây tải lớn lên broker, database và downstream; listener bean phải thread-safe.
9. **Dùng AUTO_ACKNOWLEDGE nhưng kỳ vọng rollback:** DefaultMessageListenerContainer acknowledge trước listener; dùng transaction nếu cần rollback/redelivery.
10. **Nuốt exception trong listener:** container có thể coi invocation hoàn tất và không rollback như mong đợi.
11. **Nhầm ErrorHandler với dead-letter:** ErrorHandler quan sát lỗi; broker policy mới quyết định redelivery và dead-letter.
12. **Dùng durable subscription thiếu client identity:** cấu hình durable mode, client ID và subscription name đúng với provider.
13. **Tăng concurrency trên durable subscription không shared:** một durable subscription thông thường chỉ cho một consumer; cần shared subscription và broker hỗ trợ nếu muốn scale ngang cùng subscription.
14. **Không đóng tài nguyên producer/consumer tự tạo:** ưu tiên JmsTemplate và listener container; nếu dùng JMS API trực tiếp, quản lý Session và resource đúng vòng đời.
15. **Không theo dõi container:** dùng ID ổn định và JmsListenerEndpointRegistry để quan sát, start hoặc stop endpoint.

## 15. Checklist triển khai

Trước khi đưa listener vào production, hãy kiểm tra:

1. ConnectionFactory đã kết nối đúng broker và được Spring quản lý vòng đời chưa?
2. Configuration có `@EnableJms` chưa?
3. Listener class có phải Spring bean không?
4. Có factory bean `jmsListenerContainerFactory` hoặc factory riêng được chỉ định đúng không?
5. Queue/Topic, selector và durable subscription đã khớp cấu hình broker chưa?
6. MessageConverter có tương thích với producer và schema payload không?
7. Concurrency có phù hợp với thứ tự nghiệp vụ và năng lực downstream không?
8. Acknowledgment/transaction có đáp ứng yêu cầu redelivery không?
9. Listener có idempotent và xử lý duplicate an toàn không?
10. ErrorHandler, retry, backoff và dead-letter policy đã được xác định chưa?
11. Log/metric có correlation ID và tránh dữ liệu nhạy cảm không?
12. Có integration test với JMS provider để xác nhận annotation được đăng ký và message thực sự được nhận không?

## 16. Kết luận

`@EnableJms` bật hạ tầng annotation-driven JMS; `@JmsListener` khai báo destination và phương thức xử lý. Listener container factory quyết định ConnectionFactory, concurrency, converter, transaction, error handling và loại destination. Spring quản lý vòng đời các container qua JmsListenerEndpointRegistry.

Một listener đáng tin cậy cần nhiều hơn annotation: phải cấu hình đúng Queue/Topic, converter, transaction, concurrency, retry/redelivery và khả năng quan sát. Bắt đầu với một listener đơn giản, kiểm thử cùng JMS provider, sau đó mở rộng concurrency và transaction theo tải cùng yêu cầu nghiệp vụ.

## 17. Tài liệu tham khảo

- [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
- [EnableJms — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/annotation/EnableJms.html)
- [JmsListener — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [DefaultJmsListenerContainerFactory — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html)
- [JmsListenerEndpointRegistry — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html)
- [DefaultMessageListenerContainer — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [JmsTemplate — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)