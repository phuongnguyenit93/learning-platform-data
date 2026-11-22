# Gửi bằng MessageCreator và convertAndSend

Trong Spring JMS, JmsTemplate cung cấp hai cách gửi message thường dùng:

- **send(..., MessageCreator):** ứng dụng tự tạo đối tượng jakarta.jms.Message thông qua Session do Spring cung cấp. Cách này phù hợp khi cần kiểm soát kiểu JMS message, JMS headers hoặc properties.
- **convertAndSend(...):** ứng dụng truyền một object Java; MessageConverter đã cấu hình sẽ chuyển object đó thành JMS message. Cách này phù hợp với payload nghiệp vụ thông thường.

Cả hai cách đều dùng JmsTemplate để quản lý việc gửi qua ConnectionFactory. Template xử lý vòng đời connection/session theo cấu hình, vì vậy code nghiệp vụ không phải tự mở và đóng JMS resource cho từng lần gửi.

## 1. JmsTemplate và luồng gửi message

JmsTemplate thuộc package org.springframework.jms.core. Nó là API trung tâm của Spring Framework để gửi và nhận message theo kiểu đồng bộ qua Jakarta Messaging.

Một luồng gửi cơ bản:

~~~text
Application service
       |
       | send(...) hoặc convertAndSend(...)
       v
     JmsTemplate
       |
       | lấy Connection / Session từ ConnectionFactory
       | tạo hoặc chuyển đổi JMS Message
       v
   JMS Producer
       |
       v
 Queue hoặc Topic
       |
       v
   JMS Provider
~~~

Để gửi được message, ứng dụng cần một ConnectionFactory tương thích với Jakarta Messaging và kết nối được tới JMS provider. Provider có thể là ActiveMQ Artemis, ActiveMQ Classic bản hỗ trợ Jakarta Messaging hoặc một sản phẩm JMS khác.

JmsTemplate không tự tạo broker. Tên destination truyền vào cũng phải phù hợp với cách provider quản lý queue/topic. Ứng dụng có thể dùng destination object được cấu hình sẵn hoặc để DestinationResolver phân giải tên destination.

## 2. Gửi message bằng MessageCreator

### 2.1. MessageCreator là gì?

MessageCreator thuộc package org.springframework.jms.core. Đây là functional interface có một method:

~~~java
jakarta.jms.Message createMessage(jakarta.jms.Session session)
        throws jakarta.jms.JMSException;
~~~

JmsTemplate gọi callback này khi đã có JMS Session phù hợp. Callback dùng Session để tạo đối tượng JMS message và trả về cho template gửi đi.

Nhờ vậy, ứng dụng có thể tạo chính xác loại message cần thiết:

- TextMessage cho nội dung text.
- BytesMessage cho dữ liệu byte.
- MapMessage cho tập property có kiểu dữ liệu đơn giản.
- ObjectMessage cho object Serializable khi provider và chính sách bảo mật cho phép.
- Message rỗng payload nếu chỉ cần headers/properties.

MessageCreator phù hợp khi cần điều khiển chi tiết việc tạo message hoặc sử dụng API đặc thù của Jakarta Messaging.

### 2.2. Gửi TextMessage

Ví dụ service gửi một nội dung text đến queue tên orders:

~~~java
import jakarta.jms.TextMessage;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.core.MessageCreator;
import org.springframework.stereotype.Service;

@Service
public class OrderTextSender {

    private final JmsTemplate jmsTemplate;

    public OrderTextSender(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void send(String orderId) {
        MessageCreator creator = session -> {
            TextMessage message =
                    session.createTextMessage(orderId);

            message.setStringProperty("eventType", "OrderCreated");
            message.setStringProperty("appSource", "order-service");
            return message;
        };

        jmsTemplate.send("orders", creator);
    }
}
~~~

Trong ví dụ:

1. JmsTemplate chọn Session theo ConnectionFactory và cấu hình transaction.
2. Callback nhận Session và tạo TextMessage.
3. Ứng dụng thêm JMS properties.
4. Callback trả TextMessage cho JmsTemplate.
5. JmsTemplate gửi message đến destination orders.

Không tự gọi session.close() trong callback. Session thuộc vòng đời do JmsTemplate quản lý.

### 2.3. Tạo nhiều loại JMS message

Với BytesMessage:

~~~java
jmsTemplate.send("order.bytes", session -> {
    byte[] payload = "order-42".getBytes(StandardCharsets.UTF_8);

    BytesMessage message = session.createBytesMessage();
    message.writeBytes(payload);
    message.setStringProperty("eventType", "OrderCreated");

    return message;
});
~~~

Với MapMessage:

~~~java
jmsTemplate.send("order.map", session -> {
    MapMessage message = session.createMapMessage();
    message.setString("orderId", "order-42");
    message.setInt("quantity", 2);
    return message;
});
~~~

Nên chọn message type theo contract giữa producer và consumer. TextMessage phù hợp với text/JSON đã serialize; BytesMessage phù hợp với byte payload; MapMessage phù hợp với cấu trúc key-value đơn giản có kiểu JMS hỗ trợ.

ObjectMessage có thể thuận tiện nhưng làm producer và consumer phụ thuộc vào Java serialization và class compatibility. Việc deserialize object từ nguồn không tin cậy có rủi ro bảo mật. Với hệ thống tích hợp nhiều service, JSON hoặc một schema format có version thường dễ quản lý hơn.

## 3. Đặt JMS header và property bằng MessageCreator

MessageCreator cho phép sử dụng trực tiếp các API của Jakarta JMS để thiết lập metadata.

JMS message có hai nhóm metadata cần phân biệt:

- **JMS-defined headers:** thuộc tính chuẩn do JMS định nghĩa như JMSCorrelationID, JMSReplyTo, JMSPriority, JMSExpiration, JMSDeliveryMode và JMSType. Một số header do provider quản lý hoặc có quy tắc riêng khi thiết lập.
- **Application properties:** các giá trị do ứng dụng đặt bằng setStringProperty, setIntProperty, setBooleanProperty hoặc setObjectProperty với kiểu được JMS hỗ trợ.

Ví dụ:

~~~java
jmsTemplate.send("orders", session -> {
    TextMessage message = session.createTextMessage(
            "{\"orderId\":\"order-42\"}"
    );

    message.setJMSCorrelationID("corr-900");
    message.setJMSPriority(7);
    message.setStringProperty("appEventId", "evt-100");
    message.setIntProperty("appSchemaVersion", 2);

    return message;
});
~~~

Không phải mọi JMS header đều có thể ghi tùy ý. Ví dụ JMSMessageID, JMSTimestamp, JMSRedelivered và JMSExpiration thường do provider tính hoặc quản lý theo quá trình gửi/nhận. Hãy kiểm tra API JMS và provider trước khi cố đặt chúng.

Tên application property phải tuân theo quy tắc tên identifier của JMS. Nên dùng tên đơn giản như appEventId hoặc appSchemaVersion; tránh khoảng trắng, dấu chấm và dấu gạch ngang. Không dùng prefix dành riêng như JMSX cho property nghiệp vụ.

Nếu metadata được sử dụng xuyên nhiều transport, hãy định nghĩa contract application header riêng rồi ánh xạ sang JMS property ở biên tích hợp.

## 4. Gửi object bằng convertAndSend

### 4.1. Cơ chế hoạt động

convertAndSend nhận object Java và dùng MessageConverter của JmsTemplate để chuyển object thành jakarta.jms.Message trước khi gửi.

Các overload phổ biến:

~~~java
jmsTemplate.convertAndSend(Object message);

jmsTemplate.convertAndSend(
        String destinationName,
        Object message
);

jmsTemplate.convertAndSend(
        Destination destination,
        Object message
);
~~~

Có thể gửi đến destination mặc định đã cấu hình hoặc chỉ rõ tên/đối tượng Destination.

Ví dụ:

~~~java
jmsTemplate.convertAndSend("orders", new OrderCreated(
        "order-42",
        2
));
~~~

JmsTemplate gọi converter để biến OrderCreated thành một loại JMS message mà converter hỗ trợ, rồi gửi tới orders.

### 4.2. Ví dụ với record Java

~~~java
public record OrderCreated(
        String orderId,
        int quantity
) {
}
~~~

Service gửi event:

~~~java
@Service
public class OrderEventSender {

    private final JmsTemplate jmsTemplate;

    public OrderEventSender(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.events", event);
    }
}
~~~

Ví dụ này giả định JmsTemplate đã được cấu hình với ConnectionFactory và MessageConverter tương thích. Record không tự động trở thành JSON chỉ vì gọi convertAndSend; kết quả phụ thuộc converter đang được cấu hình.

## 5. MessageConverter mặc định và converter chuyên biệt

JmsTemplate sử dụng org.springframework.jms.support.converter.MessageConverter. Interface này khác với org.springframework.messaging.converter.MessageConverter của Spring Messaging.

MessageConverter mặc định trong Spring JMS là SimpleMessageConverter. Nó hỗ trợ chuyển đổi các kiểu thường gặp:

| Kiểu Java | JMS message được tạo |
|---|---|
| String | TextMessage |
| byte[] | BytesMessage |
| Map | MapMessage |
| Serializable object | ObjectMessage |
| jakarta.jms.Message | Giữ message JMS đã có theo cơ chế converter |

Với kiểu dữ liệu khác, SimpleMessageConverter có thể không biết cách chuyển đổi và ném MessageConversionException.

Không nên mặc định convertAndSend(object) tạo JSON. Nếu muốn JSON, cần cấu hình JSON-aware MessageConverter, ví dụ MappingJackson2MessageConverter trong Spring Framework 6.1 khi dự án dùng Jackson 2 tương thích.

Ví dụ cấu hình converter:

~~~java
@Bean
public MessageConverter jacksonJmsMessageConverter(ObjectMapper objectMapper) {
    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();

    converter.setObjectMapper(objectMapper);
    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");

    return converter;
}
~~~

Trong cấu hình thực tế, khai báo bean converter theo cơ chế của ứng dụng và gắn nó với JmsTemplate. Khi dùng Spring Boot, cần kiểm tra auto-configuration và bean được inject để chắc chắn template đang sử dụng đúng converter.

### 5.1. Gắn type information

Một JSON converter có thể cần metadata để xác định kiểu Java khi nhận message. MappingJackson2MessageConverter hỗ trợ type ID property, ví dụ _type.

Không nên để producer bên ngoài tự do chỉ định tên class Java tùy ý rồi deserialize theo class name đó. Hãy dùng mapping type ID sang một tập kiểu đã cho phép hoặc cấu hình type mapper chặt chẽ. Điều này giảm rủi ro deserialize payload không đáng tin.

Nếu producer và consumer độc lập, contract JSON có version thường dễ bảo trì hơn việc truyền tên class nội bộ của Java application.

## 6. Dùng MessagePostProcessor với convertAndSend

convertAndSend có overload nhận MessagePostProcessor. Processor được gọi sau khi object đã được chuyển thành JMS Message và trước khi template gửi message.

Ví dụ:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        event,
        message -> {
            message.setJMSCorrelationID(correlationId);
            message.setStringProperty("appSource", "order-service");
            message.setIntProperty("appSchemaVersion", 2);
            return message;
        }
);
~~~

MessagePostProcessor phù hợp khi muốn giữ lợi ích của converter nhưng vẫn cần thêm JMS headers hoặc properties.

Các overload có thể dùng destination name hoặc Destination object. Hãy chọn overload phù hợp với cách ứng dụng quản lý destination.

Phân biệt vai trò:

- MessageCreator tạo toàn bộ JMS Message từ Session.
- MessagePostProcessor chỉnh sửa JMS Message đã được converter tạo.
- MessageConverter chuyển object Java thành JMS Message hoặc ngược lại.

Nếu chỉ cần thêm correlation ID hoặc một property, MessagePostProcessor thường ngắn gọn hơn tự tạo toàn bộ TextMessage bằng MessageCreator.

## 7. So sánh MessageCreator và convertAndSend

| Tiêu chí | send(MessageCreator) | convertAndSend |
|---|---|---|
| Đầu vào | Callback nhận JMS Session | Object Java |
| Ai tạo JMS Message? | Code trong MessageCreator | MessageConverter |
| Kiểm soát loại Text/Bytes/Map/ObjectMessage | Trực tiếp | Theo converter |
| Thiết lập JMS property | Trực tiếp trên message | Qua MessagePostProcessor hoặc converter |
| Serialize JSON | Tự viết hoặc gọi serializer trong callback | Cấu hình JSON MessageConverter |
| Mức độ code | Chi tiết hơn | Ngắn gọn hơn cho payload thông thường |
| Phù hợp | Cần kiểm soát message JMS cụ thể | Gửi object theo contract và converter đã cấu hình |

Quyết định theo yêu cầu:

- Dùng MessageCreator khi cần tạo loại JMS message cụ thể, ghi bytes/map, hoặc kiểm soát chi tiết header/property.
- Dùng convertAndSend khi đã có object Java và converter phù hợp.
- Dùng convertAndSend kết hợp MessagePostProcessor khi muốn serialize tự động rồi bổ sung metadata JMS.
- Dùng Destination object khi destination được quản lý bởi container hoặc cấu hình hạ tầng; dùng tên destination khi cơ chế resolver của ứng dụng đã được xác định.

## 8. Queue, Topic và Destination

JmsTemplate có thể gửi đến destination bằng tên hoặc bằng object jakarta.jms.Destination.

Ví dụ gửi queue:

~~~java
jmsTemplate.convertAndSend("orders.queue", event);
~~~

Ví dụ gửi topic khi template được cấu hình theo publish-subscribe domain:

~~~java
jmsTemplate.setPubSubDomain(true);
jmsTemplate.convertAndSend("orders.topic", event);
~~~

Thiết lập pubSubDomain ảnh hưởng cách template phân giải tên destination. Không thay đổi cấu hình này tùy tiện trên một JmsTemplate đang được nhiều service dùng chung; hãy cấu hình một lần lúc khởi tạo hoặc dùng template riêng theo domain.

Nếu đã có Destination object:

~~~java
jmsTemplate.convertAndSend(orderDestination, event);
~~~

DestinationResolver chịu trách nhiệm phân giải destination name thành Destination. Cách phân giải cụ thể phụ thuộc cấu hình resolver và provider. Một tên queue/topic có thể được tạo động hoặc phải tồn tại sẵn tùy broker và chính sách triển khai.

## 9. Transaction và thời điểm gửi

JmsTemplate tham gia vào transaction JMS nếu được gọi trong phạm vi transaction phù hợp. Với transaction cục bộ, JmsTransactionManager quản lý transaction của một ConnectionFactory. Khi dùng JTA/XA, cần cấu hình transaction manager và resource provider tương thích.

Ví dụ:

~~~java
@Transactional
public void createOrderAndPublish(OrderCreated event) {
    orderRepository.save(toEntity(event));
    jmsTemplate.convertAndSend("orders.events", event);
}
~~~

Đoạn này chỉ bảo đảm atomicity giữa database và JMS nếu cả hai resource thực sự tham gia cùng một distributed transaction phù hợp, chẳng hạn JTA/XA với cấu hình đúng. Nếu dùng transaction database cục bộ cùng JMS session độc lập, hai thao tác có thể không commit/rollback nguyên tử.

Với kiến trúc cần độ tin cậy cao mà không dùng XA, cân nhắc transactional outbox: ghi trạng thái nghiệp vụ và event vào cùng database transaction, sau đó một publisher riêng gửi event sang broker và đánh dấu đã phát. Thiết kế này cần xử lý gửi lặp bằng idempotency.

## 10. Lỗi thường gặp khi gửi JMS

### 10.1. Không có ConnectionFactory

JmsTemplate cần ConnectionFactory. Nếu không có bean hoặc provider client tương thích, ứng dụng không thể tạo JMS connection.

Kiểm tra dependency của provider, cấu hình broker URL, credential và cách tạo bean ConnectionFactory.

### 10.2. Destination không tồn tại hoặc sai loại

Tên destination có thể được resolver phân giải thành queue hoặc topic. Nếu broker không cho phép tạo động hoặc tên sai, thao tác gửi có thể thất bại.

Kiểm tra queue/topic trên broker, pubSubDomain, DestinationResolver và quyền gửi của tài khoản.

### 10.3. MessageConversionException

SimpleMessageConverter không hỗ trợ mọi object. Nếu convertAndSend nhận kiểu không được hỗ trợ, hãy cấu hình converter phù hợp hoặc gửi bằng MessageCreator.

### 10.4. JSON không được tạo như mong đợi

convertAndSend không mặc định serialize mọi POJO thành JSON. Kiểm tra MessageConverter thực tế được gắn với JmsTemplate, Jackson version và target message type.

### 10.5. JMS property không hợp lệ

Tên property không tuân theo quy tắc identifier hoặc giá trị có kiểu không được JMS hỗ trợ có thể gây JMSException. Dùng tên key đơn giản và kiểu scalar được provider hỗ trợ.

### 10.6. Message được gửi nhưng consumer không xử lý

Gửi thành công không đồng nghĩa listener đã xử lý xong. Kiểm tra destination, selector, subscription, acknowledgement, listener container và trạng thái broker.

### 10.7. Gửi trong transaction nhưng database và broker lệch nhau

Nếu hai resource không tham gia cùng transaction phân tán, một bên có thể commit trong khi bên kia rollback. Dùng XA khi phù hợp hoặc transactional outbox cùng consumer idempotent.

## 11. Ví dụ cấu hình Spring Boot

Trong Spring Boot, starter JMS và provider tương ứng có thể giúp cấu hình ConnectionFactory. Ví dụ với ActiveMQ Artemis:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-artemis")
}
~~~

Cấu hình kết nối native broker:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: ARTEMIS_USER
    password: ARTEMIS_PASSWORD
~~~

Các giá trị ARTEMIS_USER và ARTEMIS_PASSWORD là placeholder minh họa; trong ứng dụng thật hãy bind chúng từ biến môi trường hoặc secret manager. Không hard-code credential trong source control.

Sau khi JMS infrastructure được cấu hình, có thể inject JmsTemplate vào service như các ví dụ trên. Nếu dùng ActiveMQ Classic, chọn starter/client tương ứng với phiên bản Jakarta Messaging mà ứng dụng yêu cầu. Không trộn client javax.jms cũ với Spring Framework 6.x dùng jakarta.jms.

## 12. Kiểm thử việc gửi message

### 12.1. Unit test cho service

Có thể mock JmsTemplate để xác minh service gửi đến đúng destination và truyền đúng object hoặc MessageCreator. Với MessageCreator, test callback có thể cấp một mock Session và kiểm tra kiểu message/metadata được tạo.

Unit test này kiểm tra code điều phối, nhưng không chứng minh broker nhận message.

### 12.2. Integration test với broker

Dùng broker test hoặc Testcontainers tương thích để xác nhận:

1. ConnectionFactory kết nối được.
2. send(MessageCreator) tạo đúng loại JMS message.
3. convertAndSend sử dụng đúng MessageConverter.
4. MessagePostProcessor thêm đúng JMS header/property.
5. Queue/topic và destination resolver hoạt động.
6. Transaction commit/rollback theo cấu hình.
7. Consumer nhận payload và metadata đúng kiểu.

Không nên chỉ kiểm tra method send() trả về mà kết luận dữ liệu đã được consumer xử lý. Với luồng bất đồng bộ, cần chờ message ở consumer hoặc xác nhận bằng cơ chế đồng bộ dành cho test.

### 12.3. Kiểm thử lỗi

Nên bao gồm:

- Broker không sẵn sàng hoặc mất kết nối.
- Destination sai hoặc không có quyền gửi.
- Payload không được converter hỗ trợ.
- JSON không hợp lệ hoặc type ID không được cho phép.
- JMS property sai tên hoặc sai kiểu.
- Transaction rollback.
- Message gửi lặp và consumer xử lý idempotent.

## 13. Checklist chọn cách gửi

1. Payload hiện tại đã là jakarta.jms.Message hay là object Java?
2. Có cần tự chọn TextMessage, BytesMessage hoặc MapMessage không?
3. Converter của JmsTemplate có hỗ trợ kiểu payload không?
4. Có cần JSON converter hoặc serializer chuyên biệt không?
5. Cần thêm JMS header/property sau chuyển đổi không?
6. Destination là queue hay topic và resolver được cấu hình thế nào?
7. ConnectionFactory và provider client có tương thích Jakarta namespace không?
8. Transaction bao gồm những resource nào?
9. Lỗi conversion, destination và network được xử lý ra sao?
10. Integration test đã xác minh message thật qua broker chưa?

## 14. Tài liệu tham khảo

- [JmsTemplate — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [MessageCreator — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/core/MessageCreator.html)
- [MessagePostProcessor — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/core/MessagePostProcessor.html)
- [JmsTemplate — Spring JMS Reference](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring JMS Message Converters](https://docs.spring.io/spring-framework/reference/integration/jms.html)
- [JmsTransactionManager — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html)
- [Jakarta Messaging Specification](https://jakarta.ee/specifications/messaging/3.1/)

MessageCreator trao quyền tạo JMS message trực tiếp thông qua Session. convertAndSend giao việc chuyển object cho MessageConverter. Khi cần cả chuyển đổi tự động và metadata tùy chỉnh, kết hợp convertAndSend với MessagePostProcessor; luôn kiểm tra converter, destination, provider và transaction đang được dùng trong runtime.