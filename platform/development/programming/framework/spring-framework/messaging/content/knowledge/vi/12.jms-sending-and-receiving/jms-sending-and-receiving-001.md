# JmsTemplate và quản lý tài nguyên gửi nhận

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của `JmsTemplate` và `ConnectionFactory` trong Spring JMS.
- Dùng `send`, `convertAndSend`, `receive` và `receiveAndConvert` đúng trường hợp.
- Hiểu Spring tạo, sử dụng và giải phóng `Connection`, `Session`, `MessageProducer` và `MessageConsumer` như thế nào.
- Phân biệt `SingleConnectionFactory`, `CachingConnectionFactory` và connection pool của JMS provider.
- Chọn nhận đồng bộ bằng template hay nhận bất đồng bộ bằng listener container.
- Cấu hình transaction, acknowledgement, timeout và QoS phù hợp.
- Tránh rò rỉ tài nguyên, dùng sai thread, nhận message vô hạn và xử lý transaction không nhất quán.

## 1. JmsTemplate là gì?

JMS (Jakarta Messaging) định nghĩa API để gửi và nhận message qua một message provider. Ứng dụng thường phải thao tác với nhiều đối tượng:

~~~text
ConnectionFactory
       |
       v
   Connection
       |
       v
    Session
       |
       +---- MessageProducer ---- send(...)
       |
       +---- MessageConsumer ---- receive(...)
~~~

Nếu tự dùng JMS API, code phải tạo và đóng các đối tượng trung gian, xử lý `JMSException`, quản lý transaction và đảm bảo tài nguyên được giải phóng kể cả khi có lỗi.

`org.springframework.jms.core.JmsTemplate` là lớp trung tâm của Spring JMS, cung cấp các thao tác cấp cao để gửi hoặc nhận đồng bộ. Template đảm nhiệm việc lấy và giải phóng tài nguyên JMS cho từng thao tác, đồng thời chuyển các lỗi JMS sang hệ thống exception không checked của Spring.

Các lợi ích chính:

- Giảm code lặp khi tạo và đóng connection, session, producer hoặc consumer.
- Tích hợp với tài nguyên JMS được Spring transaction manager quản lý.
- Hỗ trợ destination theo tên hoặc đối tượng `Destination`.
- Hỗ trợ chuyển đổi payload qua `MessageConverter`.
- Cung cấp callback khi cần truy cập Session hoặc MessageProducer.
- Dùng chung an toàn giữa nhiều collaborator sau khi được cấu hình xong.

**Một instance JmsTemplate đã cấu hình xong là thread-safe.** Có thể khai báo một bean singleton và inject vào nhiều service. Không nên thay đổi cấu hình của template trong lúc các thread đang sử dụng nó.

## 2. ConnectionFactory và các tài nguyên JMS

### ConnectionFactory

`jakarta.jms.ConnectionFactory` là điểm vào của JMS provider. Nó tạo connection và chứa thông tin kết nối đặc thù provider, ví dụ:

- Broker URL hoặc JNDI resource.
- Authentication.
- TLS/SSL.
- Network failover.
- Connection pooling hoặc adapter quản lý tài nguyên.

Trong ứng dụng chạy trên application server, nên dùng `ConnectionFactory` được server quản lý qua JNDI nếu cần pooling và transaction integration của server. Với ứng dụng standalone, có thể dùng connection factory của provider như ActiveMQ hoặc Artemis.

### Connection

`Connection` đại diện kết nối tới provider. Connection thường được tái sử dụng thay vì tạo mới cho từng message. Việc mở connection có thể liên quan tới socket, thread và tài nguyên ở phía broker.

### Session

`Session` là ngữ cảnh tạo message, producer và consumer. Nó cũng xác định chế độ transaction và acknowledgement. JMS `Session` không phải đối tượng dùng đồng thời tùy ý từ nhiều thread; tránh chia sẻ một session cho nhiều luồng xử lý song song.

### MessageProducer và MessageConsumer

- `MessageProducer` gửi message tới queue hoặc topic.
- `MessageConsumer` nhận message từ destination và có thể dùng selector để lọc.

Mỗi thao tác gửi/nhận có thể cần producer hoặc consumer. Việc tạo rồi đóng liên tục các đối tượng này có thể tốn chi phí, vì vậy Spring cung cấp các wrapper connection factory để tái sử dụng tài nguyên.

## 3. JmsTemplate quản lý tài nguyên như thế nào?

Một lần gửi đơn giản thường đi qua chuỗi:

~~~text
JmsTemplate.convertAndSend(...)
          |
          v
Lấy ConnectionFactory
          |
          v
Lấy Connection và Session
          |
          v
Tạo MessageProducer
          |
          v
MessageConverter tạo JMS Message
          |
          v
Producer gửi message
          |
          v
Giải phóng producer / session / connection
~~~

Khi thao tác không thuộc transaction đang hoạt động, template tạo hoặc lấy các tài nguyên cần thiết, thực hiện thao tác rồi giải phóng chúng theo đúng thứ tự.

Khi đang có JMS resource được Spring transaction manager bind vào thread, template phát hiện và sử dụng tài nguyên transactional đó. Template không đóng tài nguyên thuộc transaction ở giữa thao tác; transaction manager chịu trách nhiệm hoàn tất và giải phóng khi transaction kết thúc.

Điều này có nghĩa:

- Không cần tự gọi `createConnection()`, `createSession()` hoặc `close()` khi dùng các phương thức thông thường của `JmsTemplate`.
- Không giữ `Session`, `MessageProducer` hoặc `MessageConsumer` trong field của service để dùng lâu dài.
- Không tự đóng tài nguyên mà template hoặc transaction manager đang quản lý.
- Nếu thật sự dùng JMS API trực tiếp, phải tuân theo quy tắc ownership và release của `ConnectionFactoryUtils` hoặc `JmsUtils`.

### Resource lifecycle và transaction-bound resource

~~~text
Không có transaction:
JmsTemplate
  -> lấy tài nguyên
  -> gửi/nhận
  -> đóng hoặc trả tài nguyên về wrapper/cache

Có transaction Spring:
TransactionManager
  -> bind Connection/Session vào thread
  -> JmsTemplate lấy lại Session đã bind
  -> gửi/nhận trong transaction
  -> commit hoặc rollback
  -> unbind và release tài nguyên
~~~

Spring cung cấp `ConnectionFactoryUtils` để tìm hoặc lấy session gắn với transaction hiện tại. Đây chủ yếu là utility nội bộ được `JmsTemplate` và listener container sử dụng; code ứng dụng thông thường nên gọi template thay vì tự quản lý utility này.

## 4. Gửi message với JmsTemplate

### send và MessageCreator

Dùng `send` khi muốn tự tạo JMS Message từ `Session`:

~~~java
jmsTemplate.send("orders.queue", session ->
        session.createTextMessage("ORD-1001")
);
~~~

Callback `MessageCreator` nhận `Session` do template cung cấp. Có thể dùng session để tạo `TextMessage`, `BytesMessage`, `MapMessage`, `ObjectMessage` hoặc đặt JMS property và header theo yêu cầu.

Đây là lựa chọn phù hợp khi cần kiểm soát chính xác loại JMS message hoặc thuộc tính native.

### convertAndSend

Nếu chỉ cần gửi một object và để Spring chuyển đổi thành JMS message, dùng `convertAndSend`:

~~~java
jmsTemplate.convertAndSend("orders.queue", "ORD-1001");
~~~

Mặc định, `SimpleMessageConverter` hỗ trợ các dạng phổ biến:

| Java payload | JMS message |
|---|---|
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` | `MapMessage` |
| `Serializable` | `ObjectMessage` |

Có thể thay converter bằng `setMessageConverter(...)` nếu contract cần JSON, XML hoặc định dạng khác. Khi gửi `ObjectMessage`, phải kiểm soát lớp được deserialize và chỉ dùng với nguồn đáng tin cậy; không bật cơ chế deserialize tùy tiện cho message bên ngoài.

### MessagePostProcessor

Sau khi converter tạo JMS message nhưng trước khi gửi, có thể bổ sung property hoặc header bằng `MessagePostProcessor`:

~~~java
jmsTemplate.convertAndSend(
        "orders.queue",
        "ORD-1001",
        message -> {
            message.setStringProperty("eventType", "OrderCreated");
            message.setJMSCorrelationID("checkout-9001");
            return message;
        }
);
~~~

Dùng JMS properties cho dữ liệu có thể được selector sử dụng. Các JMS header chuẩn như correlation ID có API riêng. Không dùng property tùy ý thay thế những header chuẩn nếu ứng dụng cần tương thích với hệ thống khác.

### QoS: delivery mode, priority và time-to-live

JMS cho phép điều chỉnh Quality of Service:

- **Delivery mode:** persistent hoặc non-persistent.
- **Priority:** mức ưu tiên từ 0 đến 9 theo JMS.
- **Time-to-live (TTL):** thời gian message có hiệu lực trước khi hết hạn.

Có thể cấu hình trên template:

~~~java
jmsTemplate.setDeliveryPersistent(true);
jmsTemplate.setPriority(4);
jmsTemplate.setTimeToLive(60_000);
jmsTemplate.setExplicitQosEnabled(true);
~~~

`setExplicitQosEnabled(true)` yêu cầu template sử dụng các QoS value đã cấu hình. Nếu không bật, một số provider có thể áp dụng giá trị mặc định được cấu hình tại connection factory hoặc broker. Cần kiểm tra chính sách thực tế của provider.

Persistent delivery có thể tăng độ bền nhưng cũng ảnh hưởng hiệu năng. TTL phù hợp cho dữ liệu hết giá trị sau một khoảng thời gian; không dùng TTL nếu message phải được giữ đến khi xử lý xong theo nghiệp vụ.

### Gửi nhiều message trên một Session

Khi cần nhiều thao tác JMS dùng chung Session hoặc MessageProducer, có thể dùng:

- `SessionCallback<T>`: nhận Session.
- `ProducerCallback<T>`: nhận Session và MessageProducer.

Ví dụ khái niệm:

~~~java
jmsTemplate.execute((SessionCallback<Void>) session -> {
    Queue queue = session.createQueue("orders.queue");
    MessageProducer producer = session.createProducer(queue);
    try {
        producer.send(session.createTextMessage("ORD-1001"));
        producer.send(session.createTextMessage("ORD-1002"));
    }
    finally {
        producer.close();
    }
    return null;
});
~~~

Trong callback, session do template cung cấp và không được đóng thủ công. Producer do code tạo trực tiếp phải được đóng. Nếu dùng transaction, các thao tác trong callback tuân theo transaction của session.

## 5. Nhận đồng bộ bằng JmsTemplate

JMS thường được dùng cho xử lý bất đồng bộ, nhưng template cũng hỗ trợ nhận đồng bộ.

Các phương thức phổ biến:

- `receive(destination)`: nhận JMS `Message`.
- `receiveSelected(destination, selector)`: nhận message thỏa selector.
- `receiveAndConvert(destination)`: nhận rồi chuyển payload sang object.
- Các overload có thể nhận destination object, destination name hoặc default destination.

Ví dụ:

~~~java
Message message = jmsTemplate.receive("orders.queue");
~~~

Hoặc nhận object đã chuyển đổi:

~~~java
Object payload = jmsTemplate.receiveAndConvert("orders.queue");
~~~

Nếu không có message trong thời gian chờ, phương thức trả về `null`. Vì thế phải kiểm tra null trước khi sử dụng payload.

### receiveTimeout

Nhận đồng bộ làm thread gọi bị block cho tới khi có message hoặc timeout. Nếu không cấu hình giới hạn hợp lý, thread có thể bị giữ quá lâu.

~~~java
jmsTemplate.setReceiveTimeout(2_000);

Object payload = jmsTemplate.receiveAndConvert("orders.queue");

if (payload == null) {
    System.out.println("No message before timeout");
}
else {
    System.out.println("Received: " + payload);
}
~~~

Chọn timeout theo yêu cầu ứng dụng. Nhận không chờ, nhận chờ một khoảng thời gian và nhận chờ vô hạn là các chính sách khác nhau; không để một API synchronous receive chặn request thread vô thời hạn.

### Message selector

Selector là biểu thức JMS dùng để lọc message theo header hoặc property:

~~~java
Message message = jmsTemplate.receiveSelected(
        "orders.queue",
        "eventType = 'OrderCreated'"
);
~~~

Selector không lọc theo payload tùy ý; nó hoạt động trên các JMS header và property được hỗ trợ. Dùng selector khi consumer cần nhận một tập message cụ thể từ cùng destination.

### Request-reply

`JmsTemplate` có thao tác request-reply cơ bản: gửi request và chờ response trên temporary queue được tạo cho lần gọi. Đây là mô hình đồng bộ trên messaging và có thể giữ thread trong thời gian chờ.

Dùng request-reply khi contract thực sự cần kết quả ngay. Với quy trình dài hoặc nhiều bước, nên dùng correlation ID và một workflow bất đồng bộ để tránh giữ request thread.

## 6. Nhận bất đồng bộ bằng listener container

`JmsTemplate.receive(...)` phù hợp với polling hoặc một thao tác nhận đồng bộ ngắn. Với consumer chạy liên tục, Spring khuyến nghị dùng listener container.

Có hai cách thường dùng:

- `@JmsListener`: khai báo phương thức nhận message; Spring đăng ký endpoint và quản lý listener container.
- `DefaultMessageListenerContainer`: cấu hình container trực tiếp khi cần kiểm soát sâu hơn.

Ví dụ với annotation:

~~~java
@Configuration
@EnableJms
public class JmsListenerConfiguration {
}

@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue", concurrency = "2-5")
    public void receive(String orderId) {
        System.out.println("Processing order: " + orderId);
    }
}
~~~

Listener container quản lý thread nhận, đăng ký consumer, acquisition/release tài nguyên, transaction và chuyển lỗi. Nếu concurrency lớn hơn một, listener có thể được gọi trên nhiều thread; bean listener phải thread-safe.

### DefaultMessageListenerContainer

Có thể khai báo container bằng Java Configuration:

~~~java
@Bean
public DefaultMessageListenerContainer orderListenerContainer(
        ConnectionFactory connectionFactory,
        OrderListener orderListener) {

    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();

    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.queue");
    container.setMessageListener((MessageListener) message ->
            orderListener.handle(message)
    );
    container.setConcurrentConsumers(2);
    container.setMaxConcurrentConsumers(5);
    container.setSessionTransacted(true);

    return container;
}
~~~

Đây là ví dụ cấu hình container thủ công. Trong ứng dụng thực tế, có thể dùng `@JmsListener` và `DefaultJmsListenerContainerFactory` để cấu hình tập trung. Không tạo thêm một container thủ công cho cùng endpoint đã được `@JmsListener` đăng ký.

## 7. Connection reuse, caching và pooling

JMS có nhiều đối tượng trung gian được tạo khi gửi hoặc nhận. Tái sử dụng phù hợp giúp giảm chi phí tạo tài nguyên.

### SingleConnectionFactory

`SingleConnectionFactory` trả về cùng một JMS Connection cho các lần gọi `createConnection()` và bỏ qua thao tác close trên shared connection. Nó hữu ích trong một số môi trường standalone hoặc testing khi muốn tái sử dụng connection.

Nó không cache Session, Producer và Consumer theo cách của `CachingConnectionFactory`, và cũng không phải một connection pool nhiều connection.

### CachingConnectionFactory

`CachingConnectionFactory` mở rộng `SingleConnectionFactory` và bổ sung cache cho:

- JMS `Session`.
- `MessageProducer`.
- `MessageConsumer`.

Có thể cấu hình:

~~~java
CachingConnectionFactory cachingFactory =
        new CachingConnectionFactory(targetConnectionFactory);

cachingFactory.setSessionCacheSize(10);
cachingFactory.setCacheProducers(true);
cachingFactory.setCacheConsumers(false);
~~~

Cache Session có giới hạn theo từng loại acknowledgement; số session thực tế có thể nhiều hơn giá trị cấu hình trong trường hợp dùng nhiều acknowledgement mode. Session không còn dùng sẽ được trả về cache khi được đóng qua proxy.

Lưu ý:

- Phải đóng Session đã lấy từ CachingConnectionFactory để session được trả về cache.
- Consumer được cache có thể có semantics khác với việc tạo consumer mới rồi đóng ngay; cần đặc biệt cẩn trọng với selector và durable subscription.
- Producer/consumer của temporary destination không được cache.
- CachingConnectionFactory chia sẻ một connection và cache resource; nó không thay thế connection pool thực thụ khi cần nhiều connection độc lập.

### Khi nào cần provider connection pool?

Với tải lớn hoặc nhiều consumer/producer đồng thời, cần xem xét pool do provider hoặc môi trường triển khai cung cấp. Một connection pool có thể quản lý nhiều connection, session và giới hạn tài nguyên tốt hơn việc chỉ chia sẻ một connection.

Không xếp chồng nhiều lớp cache/pool một cách tùy tiện. Cần hiểu lớp nào sở hữu connection, session, transaction và lifecycle shutdown để tránh double-close, resource starvation hoặc hành vi không mong muốn.

## 8. Transaction và acknowledgement

### Mặc định của JmsTemplate

Theo mặc định, Session do `JmsTemplate` tạo là:

- Không transacted.
- `AUTO_ACKNOWLEDGE`.

Có thể thay đổi bằng `sessionTransacted` và `sessionAcknowledgeMode`, hoặc dùng transaction manager của Spring. Nếu Session được tạo trong một transaction đang hoạt động, các tham số transaction/acknowledgement của phương thức tạo Session bị transaction infrastructure chi phối.

### JmsTransactionManager

`JmsTransactionManager` quản lý transaction cục bộ cho một `ConnectionFactory`. Nó bind cặp Connection/Session vào thread. `JmsTemplate` tự nhận ra tài nguyên đã bind và tham gia transaction đó.

~~~java
@Bean
public JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

Khi kết hợp với transaction declarative, thao tác gửi hoặc nhận bằng template có thể tham gia transaction JMS được quản lý. Transaction manager này chỉ quản lý một JMS ConnectionFactory; nó không tự tạo transaction nguyên tử giữa JMS và database.

### Listener transaction

Với listener container, có thể bật local JMS transaction:

~~~java
container.setSessionTransacted(true);
~~~

Khi listener xử lý thất bại và exception được truyền ra khỏi listener, việc nhận message có thể rollback trong JMS transaction và message có thể được giao lại theo chính sách provider.

Nếu listener vừa cập nhật database vừa nhận JMS message, local JMS transaction không tự rollback database transaction. Có thể xảy ra tình huống database đã commit nhưng JMS rollback và message được giao lại. Consumer cần idempotency hoặc duplicate detection.

Nếu thật sự cần một transaction phân tán bao gồm database và JMS, cần JTA transaction manager cùng XA-capable ConnectionFactory được cấu hình đúng. XA có chi phí và yêu cầu vận hành cao; nhiều hệ thống chọn Transactional Outbox hoặc inbox/idempotency để quản lý nhất quán theo kiến trúc ứng dụng.

## 9. Ví dụ Java 17 hoàn chỉnh với ActiveMQ Classic embedded

Ví dụ dưới đây dùng Spring Framework 6.2.19, ActiveMQ Classic 6.2.6 và Java 17. Broker được chạy embedded trong cùng JVM bằng VM transport, nên không cần cài broker ngoài. Chương trình gửi một String, nhận lại String và kiểm tra lần nhận tiếp theo timeout.

Cấu trúc thư mục:

~~~text
jms-template-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── JmsTemplateDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jms-template-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-broker</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-client</artifactId>
            <version>6.2.6</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/JmsTemplateDemo.java`:

~~~java
package demo;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.broker.BrokerService;
import org.springframework.jms.connection.CachingConnectionFactory;
import org.springframework.jms.core.JmsTemplate;

public class JmsTemplateDemo {

    public static void main(String[] args) throws Exception {
        BrokerService broker = new BrokerService();
        broker.setBrokerName("jms-template-demo");
        broker.setPersistent(false);
        broker.setUseJmx(false);
        broker.start();
        broker.waitUntilStarted();

        ActiveMQConnectionFactory providerFactory =
                new ActiveMQConnectionFactory("vm://jms-template-demo");

        CachingConnectionFactory connectionFactory =
                new CachingConnectionFactory(providerFactory);
        connectionFactory.setSessionCacheSize(2);

        try {
            JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
            jmsTemplate.setReceiveTimeout(500);

            jmsTemplate.convertAndSend("orders.demo", "ORD-1001");
            System.out.println("sent=ORD-1001");

            Object received =
                    jmsTemplate.receiveAndConvert("orders.demo");
            System.out.println("received=" + received);

            Object secondReceive =
                    jmsTemplate.receiveAndConvert("orders.demo");
            System.out.println(
                    "secondReceiveTimedOut=" + (secondReceive == null)
            );
        }
        finally {
            connectionFactory.destroy();
            broker.stop();
            broker.waitUntilStopped();
        }
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.JmsTemplateDemo
~~~

Kết quả stdout của chương trình:

~~~text
sent=ORD-1001
received=ORD-1001
secondReceiveTimedOut=true
~~~

Giải thích:

1. Embedded broker được khởi động trước khi tạo client connection factory.
2. `CachingConnectionFactory` bọc provider factory và tái sử dụng connection/session theo cấu hình.
3. `JmsTemplate.convertAndSend` dùng converter mặc định để chuyển String thành `TextMessage`.
4. `receiveAndConvert` lấy message và chuyển lại thành String.
5. Lần nhận thứ hai không có message nên trả `null` sau timeout 500 ms.
6. `CachingConnectionFactory.destroy()` đóng shared connection và cache; broker được dừng trong khối finally.

Ví dụ dùng broker non-persistent cho mục đích học tập. Nó không đại diện cho cấu hình độ bền production. Trong môi trường thật, dùng broker, authentication, TLS, persistence, destination policy và transaction phù hợp.

## 10. Khi nào dùng JmsTemplate, khi nào dùng listener?

| Nhu cầu | Lựa chọn |
|---|---|
| Gửi message tới queue/topic | `JmsTemplate.send` hoặc `convertAndSend` |
| Gửi payload Java có converter | `convertAndSend` |
| Tạo JMS Message tùy chỉnh từ Session | `send` với `MessageCreator` |
| Nhận một message theo yêu cầu và có timeout | `receive` hoặc `receiveAndConvert` |
| Poll theo lịch hoặc selector | `receiveSelected` hoặc poller chuyên dụng |
| Consumer chạy liên tục, bất đồng bộ | `@JmsListener` hoặc `DefaultMessageListenerContainer` |
| Cần nhiều thao tác trên một Session/Producer | `SessionCallback` hoặc `ProducerCallback` |
| Cần transaction JMS cục bộ | `JmsTransactionManager` hoặc session transacted |
| Cần transaction phân tán JMS + database | JTA/XA nếu thật sự cần; cân nhắc Outbox/inbox |

## 11. Lỗi thường gặp và cách tránh

1. **Tự tạo và đóng Connection/Session trong mọi service.** Dùng `JmsTemplate` để template quản lý lifecycle; chỉ dùng JMS API trực tiếp khi có nhu cầu cụ thể.
2. **Giữ Session hoặc Producer trong field dùng chung.** Session không phải đối tượng thread-safe để nhiều thread thao tác đồng thời.
3. **Tạo JmsTemplate mới cho từng message.** Cấu hình một template dùng chung sau khi khởi tạo xong.
4. **Dùng receive không timeout trên request thread.** Synchronous receive có thể block lâu; đặt timeout rõ hoặc chuyển sang listener container.
5. **Dùng JmsTemplate làm consumer chạy liên tục.** Mỗi receive đồng bộ là một thao tác riêng; dùng listener container cho nhận bất đồng bộ lâu dài.
6. **Không kiểm tra null từ receive.** Timeout hoặc queue rỗng có thể trả null.
7. **Nhầm CachingConnectionFactory với pool nhiều connection.** CachingConnectionFactory chia sẻ một connection và cache resource; dùng provider pool hoặc managed factory khi cần pooling thực sự.
8. **Không đóng Session khi dùng CachingConnectionFactory trực tiếp.** Session phải được đóng để trả về cache.
9. **Cache MessageConsumer mà không xét durable subscription.** Consumer caching có thể ảnh hưởng lifecycle subscription; kiểm tra semantics provider và cấu hình cache.
10. **Cho rằng send() có nghĩa consumer đã xử lý xong.** Send chỉ là thao tác producer với provider; xử lý downstream là bước khác.
11. **Cho rằng transaction JMS bao gồm database.** JmsTransactionManager chỉ quản lý một ConnectionFactory; cần XA hoặc kiến trúc Outbox/idempotency cho nhất quán đa tài nguyên.
12. **Bắt exception rồi nuốt trong listener.** Nếu listener container dùng transacted session, việc không truyền exception có thể làm transaction commit và message bị acknowledge. Chỉ nuốt lỗi khi đã xử lý hoặc chuyển lỗi theo chính sách rõ ràng.
13. **Không có retry hoặc DLQ policy.** Cấu hình redelivery limit, backoff và dead-letter destination ở broker/provider; tránh retry vô hạn.
14. **Dùng ObjectMessage với dữ liệu không đáng tin cậy.** Ưu tiên JSON hoặc định dạng schema rõ ràng và kiểm soát type deserialization.
15. **Không quản lý shutdown.** Đóng cache/connection factory và dừng listener container theo lifecycle của Spring context.

## 12. Checklist vận hành

- [ ] Dùng ConnectionFactory do provider hoặc container quản lý.
- [ ] Cấu hình một JmsTemplate dùng chung sau khi khởi tạo.
- [ ] Xác định queue hay topic và destination resolver phù hợp.
- [ ] Chọn send/convertAndSend theo nhu cầu chuyển đổi payload.
- [ ] Đặt receiveTimeout cho thao tác nhận đồng bộ.
- [ ] Dùng listener container cho consumer chạy liên tục.
- [ ] Chọn cache hoặc pool theo concurrency và đặc tính provider.
- [ ] Không chia sẻ Session/Producer/Consumer không an toàn giữa các thread.
- [ ] Cấu hình transaction và acknowledgement phù hợp với yêu cầu mất/giao lại message.
- [ ] Kiểm tra retry, redelivery, TTL, delivery mode và dead-letter policy.
- [ ] Thiết kế consumer idempotent nếu có khả năng redelivery.
- [ ] Theo dõi connection, session, consumer count, queue depth, delivery latency và lỗi provider.
- [ ] Đóng resource wrapper và listener container đúng lifecycle.

## 13. Kết luận

`JmsTemplate` cung cấp API gửi và nhận đồng bộ, đồng thời quản lý việc lấy và giải phóng Connection, Session, Producer và Consumer. `ConnectionFactory` quyết định cách kết nối và tái sử dụng tài nguyên; `SingleConnectionFactory` chia sẻ connection, còn `CachingConnectionFactory` bổ sung cache session/producer/consumer. Dùng `receiveTimeout` cho nhận đồng bộ, listener container cho consumer bất đồng bộ, và chọn transaction theo đúng ranh giới tài nguyên. Khi nắm rõ lifecycle, cache, transaction và timeout, ứng dụng tránh được rò rỉ tài nguyên và xử lý message ổn định hơn.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 Reference: Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html) — JmsTemplate, ConnectionFactory, resource caching và listener containers.
- [Spring Framework 6.2 Reference: Sending a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html) — send, convertAndSend, MessageConverter, MessagePostProcessor và callback.
- [Spring Framework 6.2 Reference: Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html) — synchronous receive, timeout, listener containers và transaction.
- [Spring Framework 6.2.19 Javadoc: JmsTemplate](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/core/JmsTemplate.html) — API gửi/nhận, default session settings và resource lifecycle.
- [Spring Framework 6.2.19 Javadoc: CachingConnectionFactory](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html) — cache Session, MessageProducer, MessageConsumer và lifecycle.
- [Spring Framework 6.2.19 Javadoc: ConnectionFactoryUtils](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/connection/ConnectionFactoryUtils.html) — lấy transactional Session và release Connection.
- [Spring Framework 6.2.19 Javadoc: JmsTransactionManager](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html) — transaction cục bộ cho một ConnectionFactory.
- [ActiveMQ Classic: JMS and Jakarta Messaging support](https://activemq.apache.org/components/classic/documentation/jms2) — tương thích Jakarta JMS và client.
