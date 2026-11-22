# JmsClient và API fluent từ Spring Framework 7.0

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vị trí của `JmsClient` trong Spring JMS và lý do API này được thêm từ Spring Framework 7.0.
- Tạo client từ `ConnectionFactory` hoặc tái sử dụng cấu hình của `JmsTemplate`.
- Dùng `destination(...)` để tạo operation handle và gọi các thao tác gửi, nhận, request-reply theo kiểu fluent.
- Phân biệt gửi payload, gửi Spring `Message<?>` và gửi payload kèm headers.
- Nhận kết quả dưới dạng `Optional<Message<?>>` hoặc `Optional<T>`, đồng thời cấu hình timeout và message selector.
- Thiết lập delivery mode, priority, time-to-live và delivery delay theo từng operation.
- Cấu hình converter và post-processor đúng package API.
- Chọn giữa `JmsClient`, `JmsTemplate`, `JmsMessagingTemplate` và `@JmsListener` theo nhu cầu.
- Viết ví dụ Java 17 chạy với embedded JMS broker.

## 1. JmsClient là gì?

`JmsClient` là fluent API mới của Spring Framework 7.0 dành cho các thao tác JMS phổ biến. API này được thiết kế theo phong cách của `JdbcClient` và các client fluent khác trong Spring.

`JmsClient` xây dựng trên `JmsTemplate`: client cung cấp cách viết gọn cho các thao tác gửi, nhận và request-reply, còn `JmsTemplate` thực hiện công việc JMS bên dưới, bao gồm quản lý tài nguyên cho từng thao tác.

~~~text
Ứng dụng
   |
   v
JmsClient
   |
   +-- destination(...)
   |
   +-- OperationSpec: QoS / timeout / selector
   |
   +-- send / receive / sendAndReceive
              |
              v
          JmsTemplate
              |
              v
      ConnectionFactory
              |
              v
       JMS Provider / Broker
~~~

Các đặc điểm chính:

- Có từ **Spring Framework 7.0**. Ứng dụng dùng Spring Framework 6.2 hoặc cũ hơn chưa có API này.
- Là lựa chọn fluent thay cho `JmsMessagingTemplate` trong các thao tác phổ biến.
- Làm việc với Spring Messaging `Message<?>` hoặc payload Java.
- Dùng `org.springframework.messaging.converter.MessageConverter` cho chuyển đổi payload ở lớp Spring Messaging.
- Ném `org.springframework.messaging.MessagingException` thay vì `org.springframework.jms.JmsException`.
- Cho phép cấu hình QoS và receive timeout ngay trên operation handle.
- Có thể dùng trực tiếp `ConnectionFactory` hoặc kế thừa cấu hình của `JmsTemplate` hiện có.

`JmsClient` là API đồng bộ. `receive()` và `sendAndReceive()` có thể block thread gọi trong lúc chờ message hoặc reply. Đối với consumer chạy nền liên tục, vẫn dùng listener container và `@JmsListener`.

## 2. Tạo JmsClient

Có hai nhóm factory method: `create(...)` để tạo client trực tiếp và `builder(...)` để cấu hình thêm converter hoặc post-processor trước khi build.

### Tạo từ ConnectionFactory

Cách ngắn nhất:

~~~java
JmsClient client = JmsClient.create(connectionFactory);
~~~

Hoặc dùng builder:

~~~java
JmsClient client = JmsClient.builder(connectionFactory)
        .build();
~~~

`ConnectionFactory` là điểm vào của JMS provider. Nó quyết định broker, authentication, TLS, failover và cách tạo connection. `JmsClient` không tự tạo broker hoặc tự cấu hình các chi tiết vendor-specific này.

### Tạo từ JmsTemplate đã cấu hình

Nếu ứng dụng đã có `JmsTemplate` với destination resolver, receive timeout, message converter hoặc các thiết lập khác, có thể tạo client từ template đó:

~~~java
JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setReceiveTimeout(2_000);

JmsClient client = JmsClient.create(jmsTemplate);
~~~

Hoặc cần thêm converter/post-processor:

~~~java
JmsClient client = JmsClient.builder(jmsTemplate)
        .messagePostProcessor(message ->
                MessageBuilder.fromMessage(message)
                        .setHeader("source", "billing")
                        .build())
        .build();
~~~

Overload nhận `JmsOperations` cũng cho phép dùng một implementation tùy chỉnh của contract thao tác JMS. Khi truyền `JmsTemplate`, `JmsClient` tái sử dụng cấu hình của template đó theo mặc định.

Dùng cách này khi cần giữ hành vi đã được thiết lập ở ứng dụng hiện tại trong lúc chuyển dần sang API fluent.

## 3. destination(...) và OperationSpec

Trước khi gửi hoặc nhận, chọn JMS destination:

~~~java
JmsClient.OperationSpec orders =
        client.destination("orders.queue");
~~~

Có hai overload:

~~~java
// Destination object có sẵn.
JmsClient.OperationSpec byObject =
        client.destination(queue);

// Tên destination được resolver chuyển thành Destination.
JmsClient.OperationSpec byName =
        client.destination("orders.queue");
~~~

`destination(...)` trả về một `JmsClient.OperationSpec` gắn với destination đó. Đây là operation handle có thể tái sử dụng cho nhiều thao tác gửi hoặc nhận.

Operation handle cho phép thiết lập các tùy chọn trước khi gọi thao tác:

~~~java
client.destination("orders.queue")
        .withTimeToLive(30_000)
        .withPriority(5)
        .send("ORD-1001");
~~~

Các phương thức `with...` trả về `OperationSpec` để tiếp tục nối lời gọi. Mỗi tùy chọn được áp dụng cho các thao tác tương ứng tiếp theo trên handle đó:

- `withDeliveryDelay(...)`: các thao tác gửi tiếp theo.
- `withDeliveryPersistent(...)`: các thao tác gửi tiếp theo.
- `withPriority(...)`: các thao tác gửi tiếp theo.
- `withTimeToLive(...)`: các thao tác gửi tiếp theo.
- `withReceiveTimeout(...)`: các thao tác nhận tiếp theo.

Nếu cùng destination nhưng cần hai chính sách QoS khác nhau, tạo hai operation handle riêng để ý định rõ ràng:

~~~java
JmsClient.OperationSpec urgentOrders = client.destination("orders.queue")
        .withPriority(9)
        .withTimeToLive(5_000);

JmsClient.OperationSpec normalOrders = client.destination("orders.queue")
        .withPriority(4)
        .withTimeToLive(60_000);
~~~

Tên destination dạng String được phân giải qua `DestinationResolver` của cấu hình JMS bên dưới. Nếu ứng dụng dùng JNDI hoặc resolver đặc thù provider, có thể tạo client từ `JmsTemplate` đã cấu hình resolver đó.

## 4. Gửi payload và Spring Message

### Gửi payload đơn giản

`send(payload)` chuyển payload thành message và gửi tới destination đã bind:

~~~java
client.destination("orders.queue")
        .send("ORD-1001");
~~~

Đây là cách phù hợp khi handler chỉ cần payload. Không phải tự tạo `jakarta.jms.TextMessage` hay `MessageCreator`.

### Gửi payload cùng headers

Có thể truyền map headers:

~~~java
client.destination("orders.queue")
        .send(
                "ORD-1001",
                Map.of(
                        "eventType", "OrderCreated",
                        "correlationId", "checkout-9001"
                )
        );
~~~

Headers thuộc Spring Messaging `MessageHeaders`. Converter/header mapper ở lớp JMS quyết định cách metadata được ánh xạ sang JMS headers hoặc properties. Hãy kiểm tra mapping khi contract liên hệ với consumer không dùng Spring.

### Gửi Spring Message<?> có sẵn

Khi cần kiểm soát payload và headers ngay từ đầu, tạo Spring `Message<?>`:

~~~java
Message<String> message = MessageBuilder
        .withPayload("ORD-1001")
        .setHeader("eventType", "OrderCreated")
        .setHeader("correlationId", "checkout-9001")
        .build();

client.destination("orders.queue").send(message);
~~~

Dùng kiểu này khi message đã được xây dựng ở tầng Spring Messaging hoặc cần giữ cấu trúc metadata theo contract của ứng dụng.

## 5. Nhận message và Optional

Khác với nhiều API nhận đồng bộ cũ trả về `null` khi hết thời gian chờ, `JmsClient` biểu diễn kết quả bằng `Optional`.

### Nhận toàn bộ Spring Message

~~~java
Optional<Message<?>> result = client.destination("orders.queue")
        .withReceiveTimeout(1_000)
        .receive();
~~~

Nếu nhận được message, `Optional` chứa payload và headers. Nếu hết timeout mà không có message, kết quả là `Optional.empty()`.

### Nhận payload đã chuyển đổi

~~~java
Optional<String> orderId = client.destination("orders.queue")
        .withReceiveTimeout(1_000)
        .receive(String.class);
~~~

`receive(String.class)` yêu cầu converter chuyển payload sang kiểu đích `String`.

Các overload hỗ trợ message selector:

~~~java
Optional<Message<?>> message = client.destination("orders.queue")
        .withReceiveTimeout(1_000)
        .receive("eventType = 'OrderCreated'");

Optional<Order> order = client.destination("orders.queue")
        .withReceiveTimeout(1_000)
        .receive("eventType = 'OrderCreated'", Order.class);
~~~

Selector là biểu thức JMS áp dụng trên JMS headers và properties được provider hỗ trợ; nó không truy vấn tùy ý nội dung payload.

### Xử lý Optional

~~~java
Optional<String> received = client.destination("orders.queue")
        .withReceiveTimeout(1_000)
        .receive(String.class);

received.ifPresentOrElse(
        value -> System.out.println("Received: " + value),
        () -> System.out.println("No message before timeout")
);
~~~

Không gọi `get()` mà không kiểm tra `isPresent()` hoặc dùng `orElseThrow()` nếu timeout là tình huống bình thường trong nghiệp vụ.

### Timeout và blocking

Nhận đồng bộ giữ thread gọi cho đến khi có message hoặc hết timeout. Vì thế, luôn xác định thời gian chờ cho một thao tác nhận có thể không có dữ liệu:

~~~java
Optional<String> result = client.destination("orders.queue")
        .withReceiveTimeout(2_000)
        .receive(String.class);
~~~

`withReceiveTimeout` tính bằng milliseconds. Nếu không thiết lập timeout phù hợp, receive có thể chờ vô hạn theo cấu hình mặc định của `JmsTemplate`.

`Optional.empty()` biểu thị không nhận được message trong khoảng chờ; lỗi kết nối hoặc lỗi chuyển đổi được báo bằng exception.

## 6. Request-reply với sendAndReceive

`sendAndReceive` gửi request tới destination và chờ reply. Có các dạng chính:

~~~java
// Gửi payload, chuyển reply sang kiểu đích.
Optional<Reply> reply = client.destination("quotes.requests")
        .withReceiveTimeout(2_000)
        .sendAndReceive(request, Reply.class);

// Gửi payload kèm headers.
Optional<Reply> replyWithHeaders = client.destination("quotes.requests")
        .withReceiveTimeout(2_000)
        .sendAndReceive(request, requestHeaders, Reply.class);

// Gửi và nhận Spring Message đầy đủ.
Optional<Message<?>> messageReply = client.destination("quotes.requests")
        .withReceiveTimeout(2_000)
        .sendAndReceive(requestMessage);
~~~

Trong request-reply cơ bản, Spring JMS dùng temporary reply destination cho lần gọi và chờ response theo timeout. Phía responder phải gửi reply về destination được chỉ ra trong JMS `JMSReplyTo`; client và responder cần thống nhất format payload, correlation và converter.

`sendAndReceive` là thao tác đồng bộ. Không dùng nó để chờ một workflow dài trong request thread. Với quy trình nhiều bước, nên dùng correlation ID, event reply và trạng thái workflow bất đồng bộ.

Nếu không có reply trước timeout, kết quả là `Optional.empty()`.

## 7. Cấu hình QoS theo từng operation

JmsClient cho phép thiết lập Quality of Service trên operation handle thay vì phải thay đổi cấu hình chung của toàn bộ `JmsTemplate`.

| Phương thức | Ý nghĩa | Đơn vị / giá trị |
|---|---|---|
| `withDeliveryPersistent(boolean)` | Chọn persistent hoặc non-persistent delivery | `true` / `false` |
| `withPriority(int)` | Mức ưu tiên JMS | 0–9 |
| `withTimeToLive(long)` | Thời gian message có hiệu lực | milliseconds |
| `withDeliveryDelay(long)` | Trì hoãn trước khi message được chuyển giao | milliseconds |
| `withReceiveTimeout(long)` | Thời gian tối đa chờ khi receive | milliseconds |

Ví dụ:

~~~java
JmsClient.OperationSpec delayedAudit = client.destination("audit.queue")
        .withDeliveryPersistent(true)
        .withPriority(7)
        .withDeliveryDelay(2_000)
        .withTimeToLive(60_000);

delayedAudit.send("AUDIT-1001");
~~~

Một số lưu ý:

- Priority 9 là mức cao nhất và 0 là thấp nhất theo JMS.
- TTL dương làm message hết hạn sau khoảng thời gian đã cấu hình; chọn TTL theo giá trị nghiệp vụ của message.
- Delivery delay yêu cầu provider hỗ trợ tính năng tương ứng của JMS.
- QoS được đặt rõ trên operation sẽ ghi đè giá trị QoS quản trị ở provider cho lần gửi đó.
- Nếu cần giữ QoS do broker/provider quản trị, đừng đặt các tùy chọn explicit không cần thiết trên handle.

Các thiết lập này thuộc operation handle, giúp hai luồng gửi tới cùng queue có thể dùng chính sách khác nhau.

## 8. Builder: converter và post-processor

Khi cần tùy chỉnh cách payload được chuyển đổi hoặc bổ sung metadata cho tất cả message gửi đi, dùng builder.

### Đăng ký MessageConverter

`JmsClient.Builder.messageConverter(...)` nhận converter thuộc **Spring Messaging**:

~~~java
import org.springframework.messaging.converter.MessageConverter;

JmsClient client = JmsClient.builder(connectionFactory)
        .messageConverter(customMessageConverter)
        .build();
~~~

Converter này có kiểu:

`org.springframework.messaging.converter.MessageConverter`

Nó chuyển payload trong Spring `Message<?>` giữa dạng serialized và kiểu Java đích. Nếu đăng ký nhiều converter, chúng được xét theo thứ tự đăng ký.

Cần phân biệt với converter JMS truyền thống:

- `org.springframework.messaging.converter.MessageConverter`: làm việc với Spring `Message<?>` và payload.
- `org.springframework.jms.support.converter.MessageConverter`: chuyển đổi giữa object và native `jakarta.jms.Message` như `TextMessage`, `BytesMessage`, `MapMessage`.

`JmsClient` ưu tiên contract converter chung của Spring Messaging. Nếu cần thay đổi cách biểu diễn native JMS message ở tầng `JmsTemplate`, có thể cấu hình converter JMS trên template rồi tạo `JmsClient` từ template đó.

### Đăng ký MessagePostProcessor

Builder có thể thêm processor để biến đổi Spring Message trước khi gửi:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.core.MessagePostProcessor;
import org.springframework.messaging.support.MessageBuilder;

MessagePostProcessor tenantProcessor = message ->
        MessageBuilder.fromMessage(message)
                .setHeader("tenantId", "tenant-42")
                .build();

JmsClient client = JmsClient.builder(connectionFactory)
        .messagePostProcessor(tenantProcessor)
        .build();
~~~

Processor đã đăng ký được áp dụng theo thứ tự đăng ký và chạy cho các thao tác gửi `send` và `sendAndReceive` của client.

**Chú ý package:** `JmsClient.Builder` dùng `org.springframework.messaging.core.MessagePostProcessor`, nhận và trả Spring `Message<?>`. `JmsTemplate.convertAndSend(...)` có overload dùng `org.springframework.jms.core.MessagePostProcessor`, thao tác trên native `jakarta.jms.Message` và có thể ném `JMSException`. Hai interface có tên gần giống nhưng xử lý hai lớp message khác nhau.

## 9. JmsClient, JmsTemplate, JmsMessagingTemplate và @JmsListener

| API | Mục đích | Kiểu message / kết quả | Khi nên dùng |
|---|---|---|---|
| `JmsTemplate` | API JMS truyền thống, callback cấp thấp và thao tác template | Native JMS message hoặc payload đã convert; receive có thể trả null | Cần `MessageCreator`, `SessionCallback`, `ProducerCallback`, hoặc kiểm soát JMS API chi tiết |
| `JmsMessagingTemplate` | Kết nối JmsTemplate với Spring Messaging abstraction | Spring `Message<?>`; exception thuộc Spring Messaging | Ứng dụng đang dùng contract `MessageSendingOperations` / `MessageReceivingOperations` |
| `JmsClient` | API fluent cho send, receive và request-reply đồng bộ | Payload hoặc Spring `Message<?>`; receive trả `Optional` | Thao tác JMS phổ biến, muốn đặt destination và QoS ngay tại call site |
| `@JmsListener` | Đăng ký consumer bất đồng bộ | Listener nhận payload hoặc JMS/Spring message theo cấu hình | Consumer chạy liên tục, không muốn thread nghiệp vụ tự poll |

`JmsClient` không thay thế listener container. Khi cần nhận bất đồng bộ, dùng:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void receive(String orderId) {
        System.out.println("Processing " + orderId);
    }
}
~~~

Listener container quản lý thread nhận, resource acquisition/release, acknowledgement và transaction. Nếu concurrency lớn hơn một, listener bean phải thread-safe.

Dùng `JmsTemplate` trực tiếp khi cần thao tác nhiều lần trên cùng Session hoặc Producer bằng callback. Dùng `JmsClient` khi thao tác là gửi/nhận thông thường và muốn API ngắn, dễ đọc.

## 10. Resource lifecycle và cấu hình ConnectionFactory

`JmsClient` ủy quyền thao tác thực tế cho `JmsTemplate`. Template quản lý việc lấy và giải phóng Connection, Session, Producer và Consumer cho các thao tác gửi/nhận đồng bộ.

Điều đó không có nghĩa cấu hình ConnectionFactory có thể bỏ qua. Hiệu năng production phụ thuộc cách provider hoặc wrapper tái sử dụng tài nguyên:

- Dùng ConnectionFactory do application server quản lý nếu cần pooling và transaction integration của môi trường đó.
- Có thể bọc provider factory bằng `SingleConnectionFactory` để tái sử dụng một connection.
- Dùng `CachingConnectionFactory` khi cần cache Session, Producer và Consumer.
- Không tự giữ Session hoặc MessageProducer trong field của service để dùng đồng thời từ nhiều thread.
- Nếu đã có `JmsTemplate` cấu hình sẵn, tạo `JmsClient.create(jmsTemplate)` để kế thừa các thiết lập đó.
- Khởi tạo client sau khi ConnectionFactory và converter đã được cấu hình; không thay đổi cấu hình template trong lúc ứng dụng đang xử lý message.

Client thường được tạo một lần và inject vào service. Không cần tạo một JmsClient mới cho từng message.

## 11. Exception và cách xử lý lỗi

Các thao tác trên `JmsClient` ném `org.springframework.messaging.MessagingException`. Điều này giúp API đồng nhất với Spring Messaging và các client operation handle khác.

~~~java
try {
    client.destination("orders.queue").send("ORD-1001");
}
catch (MessagingException ex) {
    // Ghi log có destination, eventId/correlationId và xử lý lỗi.
    throw ex;
}
~~~

Một số nhóm lỗi có thể gặp:

- Destination không phân giải được hoặc không tồn tại.
- Broker mất kết nối, authentication thất bại hoặc provider từ chối thao tác.
- Converter không thể chuyển payload sang định dạng đích.
- Selector không hợp lệ.
- Request-reply không có response trước timeout.

Phân biệt lỗi với timeout:

- `Optional.empty()`: thao tác receive hoặc request-reply không nhận được message trước timeout.
- `MessagingException`: thao tác gặp lỗi khi thực hiện, ví dụ lỗi kết nối hoặc chuyển đổi.

Không dùng `Optional.empty()` như bằng chứng broker đã lỗi. Nếu cần phân biệt timeout với trạng thái nghiệp vụ khác, ghi log và metrics ở nơi gọi.

Nếu dùng `JmsTemplate` trực tiếp, exception ở lớp JMS là `JmsException`; không bắt nhầm `JMSException` cho mọi thao tác client vì `JmsClient` đã chuyển lỗi sang `MessagingException`.

## 12. Ví dụ Java 17 hoàn chỉnh với embedded ActiveMQ

Ví dụ dùng Spring Framework 7.0.10, ActiveMQ Classic 6.2.6 và Java 17. Broker chạy embedded trong cùng JVM bằng VM transport. Chương trình gửi payload String và Spring Message, nhận lại dưới hai dạng khác nhau rồi kiểm tra timeout bằng `Optional.empty()`.

Cấu trúc thư mục:

~~~text
jms-client-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── JmsClientDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jms-client-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>7.0.10</spring-framework.version>
        <activemq.version>6.2.6</activemq.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-broker</artifactId>
            <version>${activemq.version}</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-client</artifactId>
            <version>${activemq.version}</version>
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

Tệp `src/main/java/demo/JmsClientDemo.java`:

~~~java
package demo;

import java.util.Optional;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.broker.BrokerService;
import org.springframework.jms.core.JmsClient;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class JmsClientDemo {

    public static void main(String[] args) throws Exception {
        BrokerService broker = new BrokerService();
        broker.setBrokerName("jms-client-demo");
        broker.setPersistent(false);
        broker.setUseJmx(false);
        broker.start();
        broker.waitUntilStarted();

        ActiveMQConnectionFactory connectionFactory =
                new ActiveMQConnectionFactory(
                        "vm://jms-client-demo?create=false"
                );

        try {
            JmsClient client = JmsClient.create(connectionFactory);

            // Gửi payload đơn giản với QoS riêng cho operation.
            client.destination("orders.payload.demo")
                    .withDeliveryPersistent(false)
                    .withTimeToLive(30_000)
                    .send("ORD-1001");

            // Gửi một Spring Message có headers.
            Message<String> outgoing = MessageBuilder
                    .withPayload("ORD-1002")
                    .setHeader("eventType", "OrderCreated")
                    .build();

            client.destination("orders.message.demo").send(outgoing);

            // Nhận payload đã chuyển đổi thành String.
            Optional<String> payload = client
                    .destination("orders.payload.demo")
                    .withReceiveTimeout(1_000)
                    .receive(String.class);

            // Nhận toàn bộ Spring Message.
            Optional<Message<?>> message = client
                    .destination("orders.message.demo")
                    .withReceiveTimeout(1_000)
                    .receive();

            // Queue đã rỗng: kết quả là Optional.empty().
            Optional<String> noMessage = client
                    .destination("orders.payload.demo")
                    .withReceiveTimeout(100)
                    .receive(String.class);

            System.out.println(
                    "payloadReceived=" + payload.orElse("<empty>")
            );
            System.out.println(
                    "messagePayload="
                            + message.map(Message::getPayload).orElse("<empty>")
            );
            System.out.println("emptyAfterTimeout=" + noMessage.isEmpty());
        }
        finally {
            broker.stop();
            broker.waitUntilStopped();
        }
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.JmsClientDemo
~~~

Các dòng stdout do chương trình tạo:

~~~text
payloadReceived=ORD-1001
messagePayload=ORD-1002
emptyAfterTimeout=true
~~~

Giải thích:

1. Broker embedded được khởi động trước khi tạo `ActiveMQConnectionFactory`.
2. `JmsClient.create(connectionFactory)` tạo client sử dụng Spring JMS.
3. Lần gửi đầu dùng payload String và đặt persistent delivery cùng TTL trên operation.
4. Lần gửi thứ hai dùng Spring `Message<?>` với header `eventType`.
5. `receive(String.class)` trả về payload đã chuyển đổi trong `Optional<String>`.
6. `receive()` trả về Spring `Message<?>` trong `Optional`.
7. Lần nhận cuối hết timeout nên `Optional.isEmpty()` trả về true.
8. Broker được dừng trong `finally`.

Ví dụ dùng broker non-persistent để chạy nhanh trong môi trường học tập; nó không mô phỏng cấu hình durability production. Trong ứng dụng thật, cấu hình authentication, TLS, persistence, destination policy, resource cache/pool và transaction theo yêu cầu hệ thống.

## 13. Lỗi thường gặp

1. **Dùng JmsClient trong Spring Framework 6.2.** API này chỉ có từ Spring Framework 7.0. Với 6.2, dùng `JmsTemplate` hoặc `JmsMessagingTemplate`.
2. **Nhầm JmsClient là reactive hoặc asynchronous.** API gửi/nhận của client là đồng bộ; dùng listener container cho consumer bất đồng bộ.
3. **Quên bind destination trước khi gửi/nhận.** Các thao tác thông thường được gọi trên `OperationSpec` trả về từ `destination(...)`.
4. **Nhận message mà không đặt timeout.** Thread gọi có thể block lâu hoặc vô hạn theo cấu hình nhận.
5. **Không xử lý Optional.empty().** Timeout không trả null; phải kiểm tra Optional.
6. **Nhầm payload với Spring Message.** Dùng `send(payload)` khi chỉ cần dữ liệu; dùng `send(Message<?>)` khi cần headers.
7. **Dùng nhầm MessageConverter.** Builder nhận `org.springframework.messaging.converter.MessageConverter`; converter JMS native thuộc package `org.springframework.jms.support.converter`.
8. **Dùng nhầm MessagePostProcessor.** Builder dùng `org.springframework.messaging.core.MessagePostProcessor`; overload cũ của JmsTemplate dùng `org.springframework.jms.core.MessagePostProcessor`.
9. **Cho rằng custom headers luôn được ánh xạ giống nhau ở mọi provider.** Kiểm tra header mapper và JMS properties ở ranh giới transport.
10. **Đặt QoS trên operation nhưng mong provider admin override.** QoS explicit của client sẽ ghi đè cấu hình quản trị provider cho thao tác đó.
11. **Dùng selector để lọc payload.** JMS selector áp dụng lên header/property, không phải truy vấn tùy ý body.
12. **Dùng sendAndReceive cho quy trình dài.** Request-reply là đồng bộ và giữ thread chờ response; dùng workflow bất đồng bộ cho tác vụ lâu.
13. **Tạo JmsClient mới cho mỗi message.** Tạo client một lần sau khi cấu hình ConnectionFactory và tái sử dụng.
14. **Bỏ qua resource reuse ở production.** Dùng managed/pooling/caching ConnectionFactory phù hợp với provider và tải.
15. **Dùng JmsClient thay cho JmsTemplate callback khi cần Session trực tiếp.** Với nhiều thao tác native trên Session hoặc Producer, dùng `SessionCallback` hoặc `ProducerCallback` của JmsTemplate.

## 14. Checklist triển khai

- [ ] Ứng dụng dùng Spring Framework 7.0 trở lên.
- [ ] Tạo một `JmsClient` dùng chung từ ConnectionFactory hoặc JmsTemplate đã cấu hình.
- [ ] Chọn destination bằng `Destination` object hoặc destination name phù hợp resolver.
- [ ] Tạo operation handle riêng khi cần QoS hoặc timeout khác nhau.
- [ ] Dùng payload hay Spring `Message<?>` đúng nhu cầu metadata.
- [ ] Xử lý `Optional.empty()` cho timeout.
- [ ] Đặt `withReceiveTimeout` cho thao tác nhận đồng bộ.
- [ ] Kiểm tra selector theo JMS headers/properties.
- [ ] Cấu hình converter và post-processor đúng package Spring Messaging.
- [ ] Hiểu rằng QoS explicit có thể override cấu hình provider.
- [ ] Bắt `MessagingException` tại ranh giới phù hợp.
- [ ] Dùng `@JmsListener` và listener container cho nhận bất đồng bộ.
- [ ] Dùng ConnectionFactory có pooling/caching phù hợp và kiểm thử transaction, redelivery, TTL.

## 15. Kết luận

`JmsClient` là fluent API của Spring Framework 7.0 cho các thao tác JMS phổ biến. `destination(...)` tạo operation handle gắn với một destination; `send`, `receive` và `sendAndReceive` hỗ trợ payload hoặc Spring `Message<?>`; `Optional` biểu diễn trường hợp không có message trước timeout. Các phương thức `with...` cho phép đặt QoS và timeout ngay trên từng operation. Client dựa trên `JmsTemplate` để thực hiện thao tác và quản lý tài nguyên, trong khi consumer chạy liên tục vẫn nên dùng listener container. Khi phân biệt rõ converter Spring Messaging với converter JMS native, xử lý timeout và chọn đúng mô hình nhận, API fluent giúp code gửi nhận ngắn gọn và dễ đọc.

## Tài liệu tham khảo chính thức

- [Spring Framework 7.0 Reference: Using Spring JMS](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/using.html) — vị trí của JmsClient, cách tạo từ ConnectionFactory/JmsTemplate và resource lifecycle.
- [Spring Framework 7.0 Reference: Sending a Message](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/sending.html) — ví dụ gửi bằng JmsClient, headers và Spring Messaging post-processor.
- [Spring Framework 7.0 Reference: Receiving a Message](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/receiving.html) — synchronous receive, timeout và listener-based asynchronous receipt.
- [Spring Framework 7.0.10 Javadoc: JmsClient](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/core/JmsClient.html) — factory methods, destination handle, exception model và ví dụ fluent.
- [Spring Framework 7.0.9 Javadoc: JmsClient.OperationSpec](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/core/JmsClient.OperationSpec.html) — send, receive, selector, request-reply và QoS/timeout methods.
- [Spring Framework 7.0.9 Javadoc: JmsClient.Builder](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/core/JmsClient.Builder.html) — đăng ký MessageConverter và MessagePostProcessor.
- [Spring Framework 7.0.9 Javadoc: Spring Messaging MessageConverter](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/converter/MessageConverter.html) — chuyển đổi payload trong Spring Message.
- [Spring Framework 7.0.9 Javadoc: Spring Messaging MessagePostProcessor](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/core/MessagePostProcessor.html) — post-process Spring Message trước khi gửi.
- [Spring Framework 7.0 Reference: Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/annotated.html) — nhận message bất đồng bộ bằng `@JmsListener`.
