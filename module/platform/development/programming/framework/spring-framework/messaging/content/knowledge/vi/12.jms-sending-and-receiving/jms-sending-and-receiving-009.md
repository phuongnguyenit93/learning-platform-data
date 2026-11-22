# JmsMessagingTemplate nối JMS với Message của Spring

## 1. Vì sao cần JmsMessagingTemplate?

Jakarta Messaging (JMS) định nghĩa API gửi và nhận message giữa các thành phần thông qua `ConnectionFactory`, `Connection`, `Session`, `Destination`, `MessageProducer` và `MessageConsumer`. Spring Messaging lại cung cấp abstraction chung `Message<T>` với payload và headers, có thể dùng cùng các API messaging khác trong Spring.

`org.springframework.jms.core.JmsMessagingTemplate` nối hai mô hình đó. Nó là lớp client ở phía ứng dụng, xây trên `JmsTemplate`, nhưng nhận và trả về `org.springframework.messaging.Message<?>`. Nhờ vậy producer có thể tạo message bằng `MessageBuilder`, gắn metadata theo Spring headers, rồi gửi qua JMS mà không phải tự tạo `jakarta.jms.Message` và quản lý `Session`.

`JmsMessagingTemplate` phù hợp khi ứng dụng muốn dùng Spring Messaging abstraction để gửi, nhận đồng bộ hoặc request-reply qua JMS. Nó không phải broker, không tự chạy listener bất đồng bộ và không thay thế cấu hình JMS provider.

## 2. Vị trí của JmsMessagingTemplate trong kiến trúc

Có thể xem luồng gửi như sau:

~~~text
Ứng dụng / Producer
       |
       v
Spring Message<T>
  - payload
  - MessageHeaders
       |
       v
JmsMessagingTemplate
       |
       v
MessagingMessageConverter
  |                    |
  v                    v
Payload converter   JmsHeaderMapper
  |                    |
  +---------+----------+
            |
            v
       jakarta.jms.Message
            |
            v
       JmsTemplate
            |
            v
ConnectionFactory -> Session -> Producer
            |
            v
       JMS Destination
            |
            v
          Broker
~~~

Ở phía nhận, listener container lấy JMS message từ broker, converter chuyển body và headers thành Spring message, rồi endpoint xử lý payload/metadata. `JmsMessagingTemplate` chủ yếu là API client cho các thao tác chủ động từ code; `@JmsListener` và listener container đảm nhiệm việc nhận message bất đồng bộ.

## 3. Phân biệt các thành phần

| Thành phần | Vai trò |
| --- | --- |
| `jakarta.jms.ConnectionFactory` | Điểm vào để tạo kết nối tới JMS provider; thường do server, broker hoặc cấu hình ứng dụng cung cấp |
| `jakarta.jms.Destination` | Đích JMS như `Queue` hoặc `Topic` |
| `JmsTemplate` | Template JMS cấp thấp hơn; quản lý resource và cung cấp các thao tác gửi/nhận đồng bộ |
| `JmsMessagingTemplate` | Wrapper theo Spring Messaging; nhận/trả `Message<?>`, hỗ trợ headers và payload conversion |
| `MessagingMessageConverter` | Chuyển giữa Spring `Message<?>` và JMS `Message`; phối hợp payload converter với header mapper |
| `SimpleMessageConverter` | Converter payload mặc định; ánh xạ các kiểu Java phổ biến sang JMS message type |
| `JmsHeaderMapper` | Ánh xạ Spring `MessageHeaders` sang JMS headers/properties và ngược lại |
| `@JmsListener` | Đăng ký method nhận message bất đồng bộ thông qua listener container |

`JmsMessagingTemplate` không mở ra một giao thức messaging mới. Nó dùng JMS làm transport và Spring Messaging làm mô hình message ở tầng ứng dụng.

## 4. Khởi tạo JmsMessagingTemplate

Có ba cách khởi tạo phổ biến:

~~~java
JmsMessagingTemplate template = new JmsMessagingTemplate(connectionFactory);
~~~

Constructor nhận `ConnectionFactory` và tự tạo một `JmsTemplate` bên trong. Cách này phù hợp khi chỉ cần cấu hình cơ bản.

~~~java
JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setReceiveTimeout(2_000);
jmsTemplate.setPubSubDomain(false);

JmsMessagingTemplate template = new JmsMessagingTemplate(jmsTemplate);
~~~

Constructor nhận `JmsTemplate` hữu ích khi cần tái sử dụng cấu hình có sẵn như `DestinationResolver`, default destination, QoS, receive timeout, connection settings hoặc message converter. `JmsMessagingTemplate` dùng `JmsTemplate` đó làm nền tảng.

Trong Spring container, có thể khai báo bean:

~~~java
@Configuration
public class JmsClientConfiguration {
    @Bean
    public JmsMessagingTemplate jmsMessagingTemplate(ConnectionFactory connectionFactory) {
        return new JmsMessagingTemplate(connectionFactory);
    }
}
~~~

`ConnectionFactory` phải được cung cấp bởi JMS provider, application server, JNDI hoặc cấu hình hạ tầng của ứng dụng. `JmsMessagingTemplate` không tự khởi động broker hay tự tạo tài nguyên JMS vật lý.

Template nên được cấu hình xong rồi dùng chung giữa các component. `JmsTemplate` và `JmsMessagingTemplate` được thiết kế để chia sẻ an toàn sau khi khởi tạo; không tạo mới một template cho từng message.

## 5. Gửi Spring Message trực tiếp bằng send()

Phương thức `send(...)` nhận một Spring `Message<?>`. Đây là cách phù hợp khi producer cần kiểm soát cả payload và headers:

~~~java
Message<String> message = MessageBuilder
        .withPayload("OrderPlaced: ORD-2048")
        .setHeader("eventType", "OrderPlaced")
        .setHeader("schemaVersion", 1)
        .build();

jmsMessagingTemplate.send("orders.queue", message);
~~~

Template chuyển Spring message thành JMS message, resolve destination theo tên và gửi qua `JmsTemplate`. Caller không cần trực tiếp tạo `Session`, `MessageProducer` hoặc `TextMessage`.

Các dạng gọi thường dùng:

~~~java
jmsMessagingTemplate.send("orders.queue", message);
jmsMessagingTemplate.send(destination, message);
jmsMessagingTemplate.send(message); // cần default destination
~~~

Với overload nhận tên, tên destination được chuyển thành `Destination` thông qua `DestinationResolver` của `JmsTemplate` nền. Với overload nhận object `Destination`, resolver không cần tra cứu tên. Overload không có destination yêu cầu đã cấu hình default destination.

## 6. Gửi payload bằng convertAndSend()

Nếu chỉ cần gửi payload và một số headers, có thể dùng `convertAndSend(...)`. Template tạo Spring message từ payload/headers, chuyển payload thành JMS message rồi gửi:

~~~java
Map<String, Object> headers = Map.of(
        "eventType", "OrderPlaced",
        "schemaVersion", 1);

jmsMessagingTemplate.convertAndSend(
        "orders.queue",
        "OrderPlaced: ORD-2048",
        headers);
~~~

Khác biệt chính:

| API | Đầu vào | Khi nên dùng |
| --- | --- | --- |
| `send(destination, message)` | Spring `Message<?>` đã tạo | Cần kiểm soát payload và toàn bộ metadata của envelope |
| `convertAndSend(destination, payload)` | Object payload | Gửi nhanh một payload qua converter đã cấu hình |
| `convertAndSend(destination, payload, headers)` | Payload và map headers | Muốn truyền metadata nhưng không cần tự tạo message |
| `convertAndSend(..., postProcessor)` | Payload và callback hậu xử lý JMS message | Cần chỉnh thuộc tính JMS sau khi payload đã được convert |

`convertAndSend` không có nghĩa mọi object Java đều tự chuyển thành JSON. Kiểu JMS message được tạo phụ thuộc `MessageConverter` đang cấu hình.

## 7. Payload conversion: từ object Java sang JMS Message

`JmsMessagingTemplate` mặc định dùng `MessagingMessageConverter`. Converter này phối hợp hai phần:

- Payload converter chuyển object Java thành JMS body, ví dụ `TextMessage`, `BytesMessage`, `MapMessage` hoặc `ObjectMessage`.
- Header mapper chuyển Spring headers thành JMS headers/properties và chuyển ngược lại khi nhận.

Payload converter mặc định là `SimpleMessageConverter`. Các ánh xạ cơ bản:

| Payload Java | JMS message |
| --- | --- |
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` | `MapMessage` |
| Object triển khai `Serializable` | `ObjectMessage` |

Với chiều nhận, converter đọc body của các JMS message type tương ứng và trả về kiểu Java phù hợp.

`ObjectMessage` dùng Java serialization. Nó có thể tiện trong hệ thống Java đồng nhất, nhưng làm producer và consumer phụ thuộc class/version, khó tương thích với ngôn ngữ khác và cần kiểm soát an toàn khi deserialize dữ liệu không tin cậy. Với hợp đồng liên dịch vụ, JSON hoặc một format schema-based thường dễ quản lý hơn.

### 7.1. Dùng MappingJackson2MessageConverter cho JSON

`MappingJackson2MessageConverter` chuyển object Java thành JSON trong `TextMessage` hoặc `BytesMessage`. Có thể chọn `MessageType.TEXT` để body là JSON text:

~~~java
MappingJackson2MessageConverter payloadConverter =
        new MappingJackson2MessageConverter();
payloadConverter.setTargetType(MessageType.TEXT);
payloadConverter.setTypeIdPropertyName("_type");
payloadConverter.setTypeIdMappings(Map.of(
        "orderPlaced", OrderPlaced.class));

MessagingMessageConverter bridgeConverter =
        new MessagingMessageConverter(payloadConverter);

JmsMessagingTemplate template = new JmsMessagingTemplate(connectionFactory);
template.setJmsMessageConverter(bridgeConverter);
~~~

Ở đây `_type` là JMS property dùng để xác định kiểu payload khi deserialize. `setTypeIdMappings` cho phép dùng mã loại như `orderPlaced` thay vì truyền tên class Java đầy đủ. Đây là cách kiểm soát danh sách kiểu được phép chuyển đổi; không nên để message bên ngoài tùy ý chỉ định bất kỳ class nào.

Nếu dùng converter JSON ở producer, listener/consumer cũng cần converter tương thích để đọc cùng wire format. Có thể cấu hình converter tương ứng cho `DefaultJmsListenerContainerFactory` hoặc listener adapter. Đảm bảo schema, type ID, encoding và quy tắc versioning thống nhất giữa hai phía.

### 7.2. Cấu hình converter cho JmsMessagingTemplate

Phương thức `setJmsMessageConverter(...)` của `JmsMessagingTemplate` nhận converter thuộc package `org.springframework.jms.support.converter`. Đây là JMS converter, khác với `org.springframework.messaging.converter.MessageConverter` của Spring Messaging.

`MessagingMessageConverter` là lớp cầu nối: nó dùng một JMS payload converter và một `JmsHeaderMapper`. Có thể truyền payload converter riêng vào constructor hoặc cấu hình header mapper sau khi tạo.

Không nhầm `JmsMessagingTemplate.setJmsMessageConverter(...)` với `JmsTemplate.setMessageConverter(...)`. Hai API có thể cùng nhận một JMS converter, nhưng converter của `JmsMessagingTemplate` cần xử lý cả Spring message envelope và mapping headers.

## 8. Spring headers được ánh xạ sang JMS headers và properties

Spring `MessageHeaders` có thể chứa metadata ứng dụng và các header chuẩn. Khi chuyển qua JMS, `SimpleJmsHeaderMapper` thực hiện ánh xạ:

- JMS API headers như correlation ID hoặc reply-to được chuyển qua các setter tương ứng của JMS message.
- Các header tùy chỉnh được chuyển thành JMS message properties nếu tên và kiểu giá trị hợp lệ.
- Khi nhận, các JMS headers và user properties được ánh xạ ngược thành Spring headers.
- `MessageHeaders.CONTENT_TYPE` được ánh xạ sang JMS property có tên tuân thủ JMS `content_type`.

Ví dụ:

~~~java
Message<String> message = MessageBuilder
        .withPayload("OrderPlaced: ORD-2048")
        .setHeader("eventType", "OrderPlaced")
        .setHeader(JmsHeaders.CORRELATION_ID, "checkout-2048")
        .setHeader("schemaVersion", 1)
        .build();

jmsMessagingTemplate.send("orders.queue", message);
~~~

`eventType` và `schemaVersion` là application properties. `JmsHeaders.CORRELATION_ID` biểu diễn JMS correlation ID chuẩn; dùng hằng số này giúp tránh nhầm với một custom property chỉ có tên gần giống.

### 8.1. JMS headers không phải tất cả đều ghi được

Một số trường JMS do provider tạo và chỉ đọc ở phía nhận, chẳng hạn destination thực tế, delivery mode, expiration, message ID, priority, redelivered flag và timestamp. `SimpleJmsHeaderMapper` có thể đưa các giá trị đó vào Spring headers khi nhận, nhưng không gửi chúng ngược thành giá trị outbound bằng cách gọi setter không hợp lệ.

Với metadata ứng dụng, nên dùng các giá trị đơn giản mà JMS property hỗ trợ, như `String`, `Boolean`, `Integer`, `Long`, `Double` và các kiểu primitive wrapper hợp lệ. Không đưa object tùy ý, collection phức tạp hoặc dữ liệu lớn vào JMS property.

Không giả định mọi Spring header đều được bảo toàn nguyên trạng qua broker. Một số header là metadata nội bộ của Spring; adapter/provider có thể bỏ qua hoặc không hỗ trợ. Hãy kiểm tra headers cần thiết ở consumer thật.

### 8.2. JmsHeaders

`org.springframework.jms.support.JmsHeaders` cung cấp các tên header chuẩn để làm việc với JMS metadata, ví dụ correlation ID, reply-to, destination, delivery mode, expiration, message ID, priority, redelivered và timestamp.

Ưu tiên dùng các hằng số `JmsHeaders` khi muốn biểu diễn thuộc tính JMS chuẩn. Với metadata riêng của domain, dùng tên rõ nghĩa như `eventType`, `tenantCode` hoặc `schemaVersion`. Tránh dùng tên `id` hoặc `type` chung chung khi chúng có thể trùng với metadata framework/provider.

## 9. Destination và DestinationResolver

`JmsMessagingTemplate` dùng destination resolution của `JmsTemplate` bên dưới. Khi truyền tên queue/topic dạng `String`, template nhờ `DestinationResolver` chuyển tên đó thành `jakarta.jms.Destination`.

`DynamicDestinationResolver` là resolver mặc định của `JmsTemplate`. Nó dùng JMS `Session` để tạo hoặc resolve destination theo tên, với queue là domain mặc định (`pubSubDomain=false`). Nếu destination đã được quản trị và bind trong JNDI, có thể cấu hình `JndiDestinationResolver` trên `JmsTemplate` rồi truyền template đó vào `JmsMessagingTemplate`.

Ví dụ tái sử dụng một JmsTemplate có resolver riêng:

~~~java
JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setDestinationResolver(jndiDestinationResolver);
jmsTemplate.setPubSubDomain(false);

JmsMessagingTemplate messagingTemplate =
        new JmsMessagingTemplate(jmsTemplate);
~~~

Với queue/topic đã provision sẵn, kiểm soát tên và quyền truy cập ở broker/application server. Không bật dynamic destination creation chỉ để che lỗi sai tên JNDI. `JmsMessagingTemplate` không tự quyết định queue hay topic theo tên; domain và resolver thuộc cấu hình JMS bên dưới.

## 10. Nhận message đồng bộ

`JmsMessagingTemplate` hỗ trợ các thao tác nhận đồng bộ:

- `receive(destinationName)` trả Spring `Message<?>` hoặc `null` nếu không nhận được message trước timeout.
- `receiveAndConvert(destinationName, targetClass)` trả payload đã chuyển đổi sang kiểu Java yêu cầu hoặc `null` nếu không nhận được message.

Nhận đồng bộ làm thread gọi bị block trong thời gian chờ. Timeout được điều khiển bởi `receiveTimeout` của `JmsTemplate` nền. Hãy đặt timeout rõ ràng và tránh gọi receive vô hạn từ request thread của web server.

Ví dụ:

~~~java
Message<?> message = jmsMessagingTemplate.receive("orders.queue");
if (message != null) {
    System.out.println(message.getPayload());
}

String text = jmsMessagingTemplate.receiveAndConvert(
        "notifications.queue", String.class);
~~~

Nhận đồng bộ phù hợp với công cụ quản trị, tác vụ có lịch hoặc luồng request cần chờ phản hồi. Đối với consumer chạy liên tục, nên dùng listener container và `@JmsListener` để xử lý bất đồng bộ.

## 11. Nhận message bất đồng bộ bằng @JmsListener

`@JmsListener` đăng ký một method làm endpoint nhận JMS. Spring tạo listener container để quản lý consumer, thread, session, transaction và việc dispatch tới method.

Method có thể nhận payload trực tiếp hoặc nhận Spring `Message<T>` nếu cần cả payload và headers:

~~~java
@Component
public class OrderListener {
    @JmsListener(destination = "orders.queue")
    public void handle(Message<OrderPlaced> message) {
        OrderPlaced order = message.getPayload();
        Object correlationId = message.getHeaders().get(
                JmsHeaders.CORRELATION_ID);
        // xử lý order và correlationId
    }
}
~~~

Khi nhận Spring `Message`, method có thể đọc cả custom headers lẫn JMS headers đã được mapper đưa vào. Cũng có thể inject riêng một header bằng `@Header`, hoặc dùng `@Headers` để nhận toàn bộ metadata.

`JmsMessagingTemplate` gửi message từ phía producer; listener container nhận message từ broker. Không dùng vòng lặp `receive()` liên tục để thay thế listener container trong một consumer production nếu cần quản lý concurrency, recovery và transaction.

## 12. Request-reply: gửi yêu cầu và chờ phản hồi

JMS hỗ trợ request-reply bằng cách gửi request có thông tin reply destination, thường thông qua `JMSReplyTo`. `JmsMessagingTemplate` cung cấp hai nhóm API:

- `sendAndReceive(destinationName, requestMessage)` gửi Spring message và trả Spring message phản hồi.
- `convertSendAndReceive(destinationName, request, targetClass)` chuyển request, gửi, nhận reply rồi chuyển payload phản hồi thành kiểu đích.

Ví dụ:

~~~java
Message<String> request = MessageBuilder
        .withPayload("price-check:SKU-42")
        .setHeader(JmsHeaders.CORRELATION_ID, "price-req-42")
        .build();

Message<?> reply = jmsMessagingTemplate.sendAndReceive(
        "pricing.requests", request);

if (reply != null) {
    System.out.println("reply=" + reply.getPayload());
}

PriceQuote quote = jmsMessagingTemplate.convertSendAndReceive(
        "pricing.requests",
        new PriceRequest("SKU-42"),
        PriceQuote.class);
~~~

Kết quả reply có thể là `null` nếu hết thời gian chờ. Hãy cấu hình timeout, correlation và reply destination phù hợp. Cách request-reply tiện lợi thường dùng temporary queue nếu message không cung cấp reply destination; tạo temporary destination cho từng yêu cầu có chi phí và giới hạn vận hành riêng.

Với listener endpoint, method có thể trả về một object hoặc Spring `Message<?>`; `@SendTo` chỉ định destination mặc định cho reply khi phù hợp. Nếu request đã có `JMSReplyTo`, Spring có thể gửi response về destination đó. Hãy phân biệt reply của một request đang chờ với event notification độc lập.

Không dùng request-reply cho mọi luồng chỉ vì muốn nhận xác nhận. Nếu consumer có thể xử lý lâu, dùng command + event kết quả hoặc trạng thái xử lý bất đồng bộ sẽ tránh giữ thread chờ và giảm phụ thuộc thời gian.

## 13. Transaction, acknowledgement và độ tin cậy

`JmsMessagingTemplate` sử dụng `JmsTemplate` nên chịu ảnh hưởng bởi transaction và resource configuration của JMS bên dưới.

### 13.1. Giao dịch JMS

`JmsTransactionManager` quản lý transaction cho một `ConnectionFactory` và bind JMS `Connection`/`Session` vào thread. `JmsTemplate` có thể phát hiện resource đã bind và tham gia transaction đó.

Ở phía listener, `DefaultJmsListenerContainerFactory.setSessionTransacted(true)` tạo JMS session có transaction cục bộ. Nếu listener ném exception và container rollback session, broker có thể redeliver message theo chính sách provider.

### 13.2. Database và JMS không tự commit nguyên tử

Một `@Transactional` dùng JDBC transaction manager không tự làm thao tác gửi JMS commit/rollback cùng database. Nếu database commit nhưng publish thất bại, consumer có thể không nhận event. Nếu publish thành công rồi database rollback, consumer có thể nhận sự kiện cho dữ liệu chưa commit.

Khi cần phối hợp database và JMS, có thể dùng JTA/XA với resource manager được cấu hình đúng, hoặc transactional outbox trong database kết hợp publisher và idempotent consumer. `JmsMessagingTemplate` không tự tạo distributed transaction.

### 13.3. Idempotency và redelivery

JMS provider có thể redeliver message khi consumer rollback, mất kết nối hoặc không ack thành công. Vì vậy consumer cần chịu được xử lý lặp:

- Gắn `eventId` ổn định cho mỗi event logic.
- Lưu event ID đã xử lý cùng transaction với thay đổi nghiệp vụ.
- Dùng unique constraint hoặc inbox table để chặn hai lần xử lý đồng thời.
- Phân loại lỗi tạm thời và lỗi dữ liệu; retry có giới hạn, có backoff và DLQ theo cấu hình provider.

Đừng coi `JMSMessageID` là business ID. Broker tạo message ID theo cơ chế transport; event ID do ứng dụng quản lý để dedup qua retry/replay.

## 14. QoS, timeout và lỗi

Vì `JmsMessagingTemplate` dùng `JmsTemplate`, có thể cấu hình QoS và receive timeout ở template nền:

- Delivery mode: persistent hoặc non-persistent theo yêu cầu và khả năng broker.
- Priority: mức ưu tiên message; provider có thể áp dụng theo cách riêng.
- Time-to-live: thời hạn message còn hiệu lực.
- Explicit QoS: bật khi muốn `JmsTemplate` áp dụng rõ các giá trị QoS do ứng dụng cấu hình thay vì dùng default từ provider.
- Receive timeout: thời gian chờ cho thao tác nhận đồng bộ.

Không nhầm TTL với timeout xử lý của consumer. TTL quyết định thời gian message có thể tồn tại/được giao theo broker; receive timeout quyết định thread gọi receive chờ bao lâu.

`JmsMessagingTemplate` căn chỉnh exception với Spring Messaging và các client operation tương tự, nên API của nó phát sinh `org.springframework.messaging.MessagingException`. `JmsTemplate` trực tiếp sử dụng hệ exception `org.springframework.jms.JmsException`. Cần thống nhất cách bắt lỗi ở tầng ứng dụng.

Khi gửi lỗi, cần xác định đó là lỗi resolve destination, lỗi chuyển đổi payload, lỗi kết nối/provider hay lỗi transaction. Không retry mù quáng lỗi schema hoặc destination sai; retry có thể phù hợp với lỗi kết nối tạm thời nhưng cần giới hạn và tránh gửi trùng.

## 15. Ví dụ tích hợp Java 17 + Spring Framework 6.2

Ví dụ này dùng một `ConnectionFactory` do JMS provider hoặc application server cung cấp. Nó gửi một Spring `Message<String>` vào queue `orders.queue`; listener nhận Spring message và đọc payload cùng headers.

Ví dụ cần có broker hoạt động và queue `orders.queue` được tạo hoặc được provider cho phép tạo động. Maven chỉ cung cấp thư viện Spring/JMS; nó không tự cung cấp broker.

Cấu trúc project:

~~~text
jms-messaging-template-demo/
  pom.xml
  src/main/java/com/example/messaging/JmsConfiguration.java
  src/main/java/com/example/messaging/OrderPublisher.java
  src/main/java/com/example/messaging/OrderListener.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>jms-messaging-template-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.18</spring.version>
        <jakarta.jms.version>3.1.0</jakarta.jms.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>${jakarta.jms.version}</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/messaging/JmsConfiguration.java`:

~~~java
package com.example.messaging;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsMessagingTemplate;

@Configuration
@EnableJms
@ComponentScan("com.example.messaging")
public class JmsConfiguration {

    @Bean
    public JmsMessagingTemplate jmsMessagingTemplate(
            ConnectionFactory connectionFactory) {
        return new JmsMessagingTemplate(connectionFactory);
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-4");
        return factory;
    }
}
~~~

`src/main/java/com/example/messaging/OrderPublisher.java`:

~~~java
package com.example.messaging;

import org.springframework.jms.core.JmsMessagingTemplate;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class OrderPublisher {
    private final JmsMessagingTemplate jmsMessagingTemplate;

    public OrderPublisher(JmsMessagingTemplate jmsMessagingTemplate) {
        this.jmsMessagingTemplate = jmsMessagingTemplate;
    }

    public void publish(String orderId) {
        Message<String> message = MessageBuilder
                .withPayload("OrderPlaced: " + orderId)
                .setHeader("eventType", "OrderPlaced")
                .setHeader("schemaVersion", 1)
                .setHeader(JmsHeaders.CORRELATION_ID, "checkout-" + orderId)
                .build();

        this.jmsMessagingTemplate.send("orders.queue", message);
    }
}
~~~

`src/main/java/com/example/messaging/OrderListener.java`:

~~~java
package com.example.messaging;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void handle(Message<String> message) {
        System.out.println("payload=" + message.getPayload());
        System.out.println("eventType=" + message.getHeaders().get("eventType"));
        System.out.println("correlationId=" +
                message.getHeaders().get(JmsHeaders.CORRELATION_ID));
    }
}
~~~

Ứng dụng phải cung cấp một bean `ConnectionFactory` trỏ tới JMS provider. Sau khi Spring context khởi động, có thể gọi `orderPublisher.publish("ORD-2048")`. Listener container nhận message bất đồng bộ và in:

~~~text
payload=OrderPlaced: ORD-2048
eventType=OrderPlaced
correlationId=checkout-ORD-2048
~~~

Đây là output của listener khi broker giao message thành công. Thời điểm in phụ thuộc listener thread và broker. Ví dụ dùng `String` nên `SimpleMessageConverter` chuyển payload thành `TextMessage`; custom headers được map thành JMS properties, còn correlation ID dùng JMS header chuẩn.

Để gửi DTO thay cho chuỗi, hãy cấu hình `MessagingMessageConverter` với `MappingJackson2MessageConverter` ở cả `JmsMessagingTemplate` và listener container, đồng thời thống nhất type ID/schema. Ví dụ converter JSON ở phần 7.1 minh họa cấu hình payload converter.

## 16. Kiểm thử và quan sát

Kiểm thử bridge nên xác nhận cả payload lẫn headers sau khi message đi qua broker:

1. Gửi `Message<String>` và xác nhận consumer nhận đúng `TextMessage` payload.
2. Kiểm tra custom property như `eventType` và `schemaVersion` được ánh xạ và đọc lại.
3. Kiểm tra `JmsHeaders.CORRELATION_ID`, `JMSReplyTo` và các header chuẩn cần dùng.
4. Gửi payload không được converter hỗ trợ để xác nhận lỗi conversion rõ ràng.
5. Kiểm tra message type JSON (`TextMessage`/`BytesMessage`) và type ID mapping giữa producer/consumer.
6. Dừng broker hoặc làm mất kết nối để xác nhận recovery/retry theo cấu hình.
7. Ném exception trong listener để kiểm tra rollback/redelivery khi session transacted.
8. Kiểm tra duplicate và idempotency khi broker redeliver message.
9. Kiểm tra request-reply timeout và trường hợp không có reply.

Log nên có event ID, correlation ID, destination, message type và kết quả xử lý. Không log token, secret hoặc payload nhạy cảm. Theo dõi số message gửi lỗi, conversion failure, listener exception, redelivery, queue depth, message age và consumer lag nếu provider cung cấp.

## 17. Lỗi thường gặp

- **Dùng nhầm `JmsTemplate` và `JmsMessagingTemplate`:** `JmsTemplate` làm việc chủ yếu với JMS API; `JmsMessagingTemplate` nhận Spring `Message<?>` và căn chỉnh với Spring Messaging.
- **Nhầm hai loại MessageConverter:** converter trong `org.springframework.jms.support.converter` làm việc với JMS message; converter trong `org.springframework.messaging.converter` thuộc abstraction messaging khác.
- **Cho rằng mọi object Java đều thành JSON:** converter mặc định dùng `SimpleMessageConverter`; Serializable object thường thành `ObjectMessage`.
- **Dùng ObjectMessage giữa các service khác ngôn ngữ:** Java serialization gây phụ thuộc class và rủi ro khi deserialize dữ liệu không tin cậy.
- **Giả định mọi Spring header đều qua broker:** chỉ những header được mapper/provider hỗ trợ mới được bảo toàn.
- **Đặt custom header với kiểu không hợp lệ cho JMS property:** chuyển đổi có thể thất bại hoặc provider từ chối message.
- **Tự đặt JMSMessageID hoặc trường chỉ đọc:** các trường này do provider quản lý; dùng application event ID cho dedup.
- **Gọi receive đồng bộ trên request thread không có timeout:** thread có thể bị block lâu.
- **Dùng JmsMessagingTemplate làm consumer bất đồng bộ:** dùng `@JmsListener` và listener container cho luồng nhận liên tục.
- **Không cấu hình destination resolver:** tên queue/topic có thể được resolve theo domain mặc định ngoài dự kiến.
- **Cho rằng gửi thành công nghĩa là consumer xử lý xong:** send thành công chỉ phản ánh kết quả gửi theo provider; consumer có thể xử lý sau hoặc redeliver.
- **Bỏ qua transaction/acknowledgement:** default auto-acknowledge không phù hợp với mọi yêu cầu reliability; cấu hình session transaction và idempotency theo nghiệp vụ.
- **Cho rằng JDBC @Transactional tự bao gồm JMS:** cần transaction manager phù hợp, JTA/XA hoặc outbox khi cần phối hợp hai resource.

## 18. Checklist review

1. Ứng dụng cần Spring `Message<?>` hay chỉ cần gửi/nhận JMS payload đơn giản?
2. `JmsMessagingTemplate` dùng đúng `ConnectionFactory` và `JmsTemplate` đã cấu hình chưa?
3. Destination là Queue hay Topic? Resolver và `pubSubDomain` có đúng không?
4. `send` hay `convertAndSend` phù hợp với hợp đồng payload?
5. Payload converter có tạo đúng JMS message type không?
6. Nếu dùng JSON, type ID và schema version có được kiểm soát không?
7. Headers nào là JMS standard header, headers nào là custom property?
8. Các header cần thiết có được mapper/provider bảo toàn không?
9. Consumer nhận Spring `Message<T>` hay chỉ payload? Có cần `@Header`/`@Headers` không?
10. Nhận message đồng bộ có timeout phù hợp không, hay nên dùng listener container?
11. Request-reply có reply destination, correlation và timeout rõ ràng không?
12. Session transaction/acknowledgement có phù hợp với yêu cầu reliability không?
13. Consumer có idempotent khi redelivery không?
14. Database và JMS có cần outbox hoặc JTA/XA không?
15. Có kiểm thử lỗi conversion, destination, broker, timeout và listener rollback không?

## 19. Ghi nhớ

`JmsMessagingTemplate` là cầu nối giữa Spring `Message<?>` và Jakarta JMS, được xây trên `JmsTemplate`. `send` chuyển một Spring message đã có payload/headers; `convertAndSend` tạo message từ payload và headers thông qua converter. `MessagingMessageConverter` phối hợp payload converter với `JmsHeaderMapper`, giúp Spring headers đi qua JMS headers/properties theo khả năng của provider. `SimpleMessageConverter` hỗ trợ các kiểu cơ bản; JSON converter phù hợp hơn khi cần hợp đồng liên dịch vụ. Dùng `receive` cho thao tác đồng bộ có timeout, `@JmsListener` cho nhận bất đồng bộ và `sendAndReceive`/`convertSendAndReceive` cho request-reply. Độ tin cậy cuối cùng phụ thuộc destination, converter, transaction, acknowledgement, provider và idempotency của consumer.

### Tài liệu tham khảo

- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — Sending a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html)
- [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
- [Spring Framework 6.2.18 — JmsMessagingTemplate Javadoc](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/jms/core/JmsMessagingTemplate.html)
- [Spring Framework 6.2 — MessagingMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/converter/MessagingMessageConverter.html)
- [Spring Framework 6.2 — SimpleJmsHeaderMapper Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/SimpleJmsHeaderMapper.html)
- [Spring Framework 6.2 — MappingJackson2MessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html)