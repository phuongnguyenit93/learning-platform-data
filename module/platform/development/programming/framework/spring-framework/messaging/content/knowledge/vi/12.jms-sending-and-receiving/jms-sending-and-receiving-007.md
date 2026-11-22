# MessagePostProcessor của JMS và thiết lập thuộc tính sau chuyển đổi

Trong Spring JMS, JmsTemplate có thể nhận một object Java, chuyển object đó thành jakarta.jms.Message bằng MessageConverter rồi gửi đến broker. Có những trường hợp ứng dụng muốn dùng converter để tạo body nhưng vẫn cần bổ sung correlation ID, application properties hoặc reply destination trước khi gửi.

MessagePostProcessor giải quyết bước đó. JmsTemplate gọi processor sau khi converter tạo JMS message và trước khi gửi message. Processor nhận đối tượng JMS Message, có thể thiết lập metadata, rồi trả về message sẽ được gửi.

Đây là cách kết hợp hai lợi ích:

- MessageConverter chịu trách nhiệm chuyển payload Java thành loại JMS message phù hợp.
- MessagePostProcessor chịu trách nhiệm hoàn thiện metadata của JMS message sau chuyển đổi.

## 1. MessagePostProcessor là gì?

MessagePostProcessor thuộc package org.springframework.jms.core và là một functional interface. Hợp đồng chính:

~~~java
jakarta.jms.Message postProcessMessage(
        jakarta.jms.Message message
) throws jakarta.jms.JMSException;
~~~

Processor nhận JMS message đã được tạo, chỉnh sửa message nếu cần và trả về message cho JmsTemplate gửi đi. Vì chỉ có tham số Message, processor không nhận trực tiếp Session hay MessageProducer.

JmsTemplate cung cấp các overload convertAndSend có thể nhận MessagePostProcessor, ví dụ:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        event,
        messagePostProcessor
);
~~~

Luồng xử lý:

~~~text
Java object
    |
    v
MessageConverter.toMessage(...)
    |
    v
JMS Message đã có body
    |
    v
MessagePostProcessor.postProcessMessage(...)
    |
    | thêm correlation ID / properties / reply-to
    v
JMS Message hoàn chỉnh
    |
    v
JmsTemplate gửi qua MessageProducer
    |
    v
JMS provider / broker
~~~

Processor chạy sau bước chuyển đổi nên có thể làm việc trực tiếp với TextMessage, BytesMessage, MapMessage hoặc loại JMS message mà converter tạo ra. Nó không phải converter thứ hai và không có nhiệm vụ serialize lại payload.

## 2. Phân biệt MessageConverter, MessageCreator và MessagePostProcessor

Ba API thường xuất hiện cạnh nhau nhưng giải quyết ba nhiệm vụ khác nhau.

| API | Đầu vào | Trách nhiệm | Khi nên dùng |
|---|---|---|---|
| MessageConverter | Object Java và Session | Tạo/chuyển đổi giữa object Java và JMS Message | Muốn định nghĩa cách serialize/deserialize payload |
| MessageCreator | JMS Session | Tự tạo một JMS Message hoàn chỉnh | Cần kiểm soát loại message hoặc tạo body bằng JMS API |
| MessagePostProcessor | JMS Message đã được tạo | Bổ sung/chỉnh sửa metadata sau chuyển đổi | Muốn giữ converter và thêm JMS header/property trước khi gửi |

Ví dụ:

- Dùng MappingJackson2MessageConverter để biến OrderCreated thành TextMessage chứa JSON.
- Dùng MessagePostProcessor để đặt JMSCorrelationID và appEventId trên TextMessage đó.
- Dùng MessageCreator nếu cần tự gọi session.createBytesMessage(), ghi byte và kiểm soát toàn bộ quá trình tạo message.

MessagePostProcessor không thay thế MessageCreator khi cần Session để tạo một JMS message mới hoặc ghi body. Nó cũng không thay thế MessageConverter khi cần chuyển object thành JSON/XML.

## 3. Thêm JMS properties sau khi converter tạo message

### 3.1. Dùng lambda với convertAndSend

Ví dụ gửi một event Java và bổ sung application properties:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        event,
        message -> {
            message.setStringProperty("appSource", "order-service");
            message.setStringProperty("appEventId", eventId);
            message.setIntProperty("appSchemaVersion", 2);
            return message;
        }
);
~~~

Trình tự diễn ra:

1. JmsTemplate nhận event.
2. MessageConverter chuyển event thành JMS Message.
3. Lambda nhận message đã có body.
4. Processor thêm các property.
5. Processor trả message.
6. JmsTemplate gửi message đến orders.events.

Các property ở ví dụ này là metadata do ứng dụng định nghĩa. Consumer có thể đọc bằng getStringProperty hoặc getIntProperty, và broker có thể dùng property trong JMS selector.

### 3.2. Dùng class riêng khi logic phức tạp

Khi cần tái sử dụng cùng quy tắc ở nhiều nơi, có thể tạo một class triển khai MessagePostProcessor:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.core.MessagePostProcessor;

public class OrderMetadataPostProcessor
        implements MessagePostProcessor {

    private final String correlationId;
    private final String eventId;

    public OrderMetadataPostProcessor(
            String correlationId,
            String eventId) {
        this.correlationId = correlationId;
        this.eventId = eventId;
    }

    @Override
    public Message postProcessMessage(Message message)
            throws JMSException {

        message.setJMSCorrelationID(correlationId);
        message.setStringProperty("appEventId", eventId);
        message.setStringProperty("appSource", "order-service");

        return message;
    }
}
~~~

Sử dụng:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        event,
        new OrderMetadataPostProcessor(correlationId, eventId)
);
~~~

Tên method đúng của interface là postProcessMessage. Trong code ứng dụng, hãy dùng đúng tên này khi triển khai class; các ví dụ lambda không cần viết tên method.

## 4. Thiết lập JMSCorrelationID và các header chuẩn

JMS định nghĩa một số header chuẩn bên cạnh application properties. MessagePostProcessor có thể đặt những header mà Jakarta Messaging cho phép ứng dụng thiết lập.

Ví dụ:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        event,
        message -> {
            message.setJMSCorrelationID(correlationId);
            message.setJMSType("OrderCreated");
            return message;
        }
);
~~~

Các header thường cần quan tâm:

| Header JMS | Mục đích | Cách xử lý |
|---|---|---|
| JMSCorrelationID | Liên kết request/reply hoặc các message cùng workflow | Có thể đặt bằng setJMSCorrelationID |
| JMSReplyTo | Destination mà consumer có thể gửi reply | Có thể đặt bằng setJMSReplyTo với Destination đã có |
| JMSType | Nhãn loại message theo contract JMS | Có thể đặt bằng setJMSType |
| JMSMessageID | ID do provider gán cho message đã gửi | Provider quản lý |
| JMSTimestamp | Thời điểm provider gửi message | Provider quản lý |
| JMSRedelivered | Cho biết message đã được giao lại | Provider quản lý |
| JMSPriority | Mức ưu tiên gửi | Thiết lập qua QoS của producer/JmsTemplate |
| JMSDeliveryMode | Persistent hoặc non-persistent | Thiết lập qua QoS của producer/JmsTemplate |
| JMSExpiration | Thời điểm hết hạn | Thiết lập qua time-to-live của producer/JmsTemplate |

Không phải mọi trường JMS đều có setter công khai. Ví dụ, message API không cung cấp setJMSMessageID hoặc setJMSTimestamp để ứng dụng tự gán các giá trị provider quản lý.

MessagePostProcessor cũng không nhận Session. Nếu cần đặt JMSReplyTo, hãy cung cấp một Destination đã được tạo/cấu hình sẵn cho processor thay vì cố tạo queue/topic bên trong callback.

## 5. Thiết lập JMSReplyTo

JMSReplyTo là header chứa Destination để consumer biết nơi gửi phản hồi. Vì MessagePostProcessor không có Session, destination cần được lấy từ cấu hình hoặc được inject từ nơi khác.

Ví dụ khi ứng dụng đã có một Destination bean:

~~~java
@Bean
public MessagePostProcessor replyToPostProcessor(
        @Qualifier("orderReplies") Destination replyDestination) {

    return message -> {
        message.setJMSReplyTo(replyDestination);
        return message;
    };
}
~~~

Sau đó truyền processor vào convertAndSend:

~~~java
jmsTemplate.convertAndSend(
        "orders.commands",
        command,
        replyToPostProcessor
);
~~~

Ví dụ này giả định orderReplies là Destination hợp lệ do provider/container cung cấp. Tên bean và cách tạo queue/topic phụ thuộc cấu hình ứng dụng.

Không đặt một chuỗi tùy ý vào JMSReplyTo; thuộc tính này cần một đối tượng jakarta.jms.Destination. Nếu muốn gửi đến destination được xác định động bằng tên, hãy xử lý việc phân giải destination ở tầng cấu hình hoặc nơi có quyền truy cập Session/ DestinationResolver phù hợp.

## 6. JMS properties: tên và kiểu dữ liệu hợp lệ

Application property được đặt bằng các method như:

~~~java
message.setStringProperty("appSource", "order-service");
message.setIntProperty("appSchemaVersion", 2);
message.setBooleanProperty("appReplay", false);
message.setLongProperty("appCreatedAt", epochMillis);
~~~

JMS property hỗ trợ các kiểu scalar như boolean, byte, short, int, long, float, double và String. setObjectProperty cũng chỉ chấp nhận các kiểu giá trị được JMS quy định, không phải object Java tùy ý.

Tên property phải tuân theo cú pháp Java identifier. Nên dùng tên như appEventId, appSchemaVersion hoặc appSource. Tránh dấu chấm, dấu gạch ngang và khoảng trắng nếu property cần tương thích JMS.

Không dùng prefix dành riêng JMSX hoặc JMS_ cho application property. Không đặt property có giá trị null; nếu không có giá trị, hãy bỏ qua property hoặc dùng quy ước rõ ràng trong contract.

Tên property phân biệt chữ hoa/chữ thường. appEventId và appeventid là hai key khác nhau; producer và consumer phải dùng thống nhất một cách viết.

Không đặt entity JPA, Spring bean, MessageChannel, servlet request, token hoặc object lớn vào property. JMS properties là metadata nhỏ, có thể được broker kiểm tra bằng selector và thường được đưa vào log/management console.

## 7. Dùng property cho JMS selector

JMS selector lọc message dựa trên JMS headers và message properties, không đọc trực tiếp field bên trong JSON body.

Ví dụ processor đặt eventType và appSchemaVersion:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        event,
        message -> {
            message.setStringProperty("eventType", "OrderCreated");
            message.setIntProperty("appSchemaVersion", 2);
            return message;
        }
);
~~~

Listener có thể lọc theo selector:

~~~java
@JmsListener(
        destination = "orders.events",
        selector = "eventType = 'OrderCreated' AND appSchemaVersion >= 2"
)
public void handle(OrderCreated event) {
    // Xử lý event phù hợp với selector.
}
~~~

Selector dùng cú pháp biểu thức của JMS và các kiểu property hỗ trợ. Nếu property bị thiếu, biểu thức có thể cho kết quả UNKNOWN và message không khớp selector. Cần xác định rõ giá trị mặc định và version contract.

Không dùng selector như cơ chế phân quyền. Producer có thể đặt property theo contract, nhưng quyền gửi/nhận destination vẫn phải được kiểm soát bằng broker ACL và security của ứng dụng.

## 8. Kết hợp MessagePostProcessor với JSON converter

Một use case phổ biến là converter tạo JSON TextMessage, sau đó processor thêm metadata JMS.

Ví dụ cấu hình JSON converter:

~~~java
@Bean
public MessageConverter jacksonJmsMessageConverter(
        ObjectMapper objectMapper) {

    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();

    converter.setObjectMapper(objectMapper);
    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");

    return converter;
}
~~~

Cấu hình JmsTemplate dùng converter:

~~~java
@Bean
public JmsTemplate jmsTemplate(
        ConnectionFactory connectionFactory,
        MessageConverter jacksonJmsMessageConverter) {

    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setMessageConverter(jacksonJmsMessageConverter);
    return template;
}
~~~

Gửi event và bổ sung metadata:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        event,
        message -> {
            message.setJMSCorrelationID(correlationId);
            message.setStringProperty("appEventId", eventId);
            message.setStringProperty("appSource", "order-service");
            return message;
        }
);
~~~

Converter tạo TextMessage từ object event; processor thêm correlation ID và application properties vào message đó. Body JSON không cần bị serialize lần thứ hai.

Nếu converter dùng property _type để lưu type ID, đừng ghi đè key này bằng một ý nghĩa khác. Consumer có thể dựa vào type ID để chọn class khi deserialize. Với message đến từ bên ngoài, cần giới hạn type mapping vào các kiểu được phép; không cho phép client tự do chỉ định tên class tùy ý.

MappingJackson2MessageConverter là API của Spring Framework 6.1 khi sử dụng Jackson 2. Kiểm tra phiên bản Spring/Jackson của dự án và chọn converter phù hợp nếu stack đã chuyển sang một phiên bản khác.

## 9. MessagePostProcessor không thiết lập QoS của producer

Một nhầm lẫn phổ biến là cố dùng MessagePostProcessor để thay đổi JMSPriority, JMSDeliveryMode hoặc JMSExpiration. Những thông tin này được điều khiển bởi các tham số gửi của MessageProducer/JmsTemplate, không phải application properties.

JmsTemplate có các thuộc tính QoS như deliveryMode, priority và timeToLive. Để template áp dụng các giá trị này cho từng lần gửi, bật explicitQosEnabled.

Ví dụ cấu hình:

~~~java
@Bean
public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);

    template.setExplicitQosEnabled(true);
    template.setDeliveryMode(DeliveryMode.PERSISTENT);
    template.setPriority(7);
    template.setTimeToLive(60_000L);

    return template;
}
~~~

Ví dụ này áp dụng QoS cấu hình cho các lần gửi của template:

- DeliveryMode.PERSISTENT yêu cầu provider lưu bền vững theo khả năng và cấu hình broker.
- Priority có giá trị trong khoảng 0 đến 9; 4 là mức mặc định theo JMS.
- Time-to-live tính bằng milliseconds; 60.000 tương ứng 60 giây.

Nếu cần QoS khác nhau theo từng message, có thể dùng template được cấu hình riêng hoặc overload send/convertAndSend có tham số QoS phù hợp trong API đang dùng. Không giả định MessagePostProcessor có thể thay thế các tham số này.

Cũng cần phân biệt message expiration với application property có tên appExpiresAt. Một property tự đặt không làm broker tự hết hạn message.

## 10. Xử lý lỗi trong MessagePostProcessor

Method postProcessMessage có thể ném JMSException. Nếu việc bổ sung metadata thất bại, JmsTemplate không thể tiếp tục gửi như thể message đã hoàn chỉnh.

Ví dụ kiểm tra dữ liệu trước khi gắn property:

~~~java
MessagePostProcessor processor = message -> {
    if (eventId == null || eventId.isBlank()) {
        throw new JMSException("eventId is required");
    }

    message.setStringProperty("appEventId", eventId);
    return message;
};
~~~

JmsTemplate dịch các JMSException sang hệ thống unchecked exception của Spring JMS, thuộc nhánh JmsException. Hãy xử lý exception ở service boundary theo chính sách của ứng dụng.

Không bắt rồi bỏ qua exception trong processor. Nếu metadata bắt buộc bị thiếu, gửi message có thể làm consumer không thể correlation, lọc hoặc xử lý đúng.

Một số lỗi thường gặp:

- Tên property không hợp lệ theo JMS.
- Giá trị property không thuộc kiểu JMS hỗ trợ.
- JMSReplyTo không phải Destination hợp lệ.
- Converter tạo loại message không tương thích với thao tác processor đang thực hiện.
- Property type ID của JSON converter bị ghi đè.
- Provider từ chối metadata hoặc gửi message vì destination/permission/network không hợp lệ.

## 11. Giữ processor stateless và an toàn khi dùng đồng thời

MessagePostProcessor thường được dùng như lambda hoặc Spring bean và có thể được tái sử dụng bởi nhiều lần gửi. Nếu processor là singleton, không lưu correlation ID hoặc event ID của từng request vào mutable field dùng chung.

Ví dụ không an toàn:

~~~java
@Component
public class UnsafeProcessor implements MessagePostProcessor {

    private String currentCorrelationId;

    public void setCorrelationId(String value) {
        this.currentCorrelationId = value;
    }

    @Override
    public Message postProcessMessage(Message message)
            throws JMSException {
        message.setJMSCorrelationID(currentCorrelationId);
        return message;
    }
}
~~~

Hai thread gửi đồng thời có thể ghi đè currentCorrelationId của nhau, khiến message nhận sai correlation ID.

Thay vào đó, tạo processor riêng cho mỗi lần gửi bằng lambda đóng trên giá trị bất biến:

~~~java
MessagePostProcessor processorFor(String correlationId) {
    return message -> {
        message.setJMSCorrelationID(correlationId);
        return message;
    };
}
~~~

Giá trị correlationId được truyền vào khi tạo processor cho lần gửi đó. Processor không cần chia sẻ state mutable giữa các thread.

## 12. Kiểm thử MessagePostProcessor

Nên kiểm tra cả logic processor và kết quả trên broker.

### 12.1. Unit test cho processor

Có thể dùng mock jakarta.jms.Message để xác nhận các setter được gọi:

~~~java
Message message = mock(Message.class);

MessagePostProcessor processor = candidate -> {
    candidate.setStringProperty("appSource", "order-service");
    candidate.setIntProperty("appSchemaVersion", 2);
    return candidate;
};

Message result = processor.postProcessMessage(message);

assertSame(message, result);
verify(message).setStringProperty("appSource", "order-service");
verify(message).setIntProperty("appSchemaVersion", 2);
~~~

Ví dụ này cần JUnit và Mockito trong test classpath. Nó xác nhận processor đặt đúng metadata trên object nhận vào, nhưng không chứng minh converter và broker hoạt động đúng.

### 12.2. Integration test với JMS provider

Với broker test, xác nhận:

1. Converter tạo đúng loại JMS message và body.
2. Processor được gọi sau conversion.
3. JMSCorrelationID và application properties có giá trị đúng.
4. Consumer đọc được property bằng getter phù hợp.
5. JMS selector lọc message theo property như mong đợi.
6. JSON type ID vẫn được giữ nguyên.
7. QoS delivery mode, priority và expiration theo cấu hình template.
8. Processor ném JMSException thì message không được gửi như một message thành công.
9. Transaction commit/rollback ảnh hưởng đến việc message được phát ra theo cấu hình.
10. Nhiều lần gửi đồng thời không làm lẫn correlation ID.

Đừng chỉ mock JmsTemplate rồi kết luận property đã được broker lưu và consumer đọc được. Những hành vi native JMS cần integration test với provider tương thích.

## 13. Khi nào nên dùng MessagePostProcessor?

| Nhu cầu | Cách phù hợp |
|---|---|
| Chuyển POJO thành JSON/TextMessage | MessageConverter |
| Thêm correlation ID sau khi converter chạy | MessagePostProcessor |
| Thêm event ID, source, schema version | MessagePostProcessor |
| Đặt JMSReplyTo từ Destination đã có | MessagePostProcessor |
| Tạo BytesMessage và ghi body bằng Session | MessageCreator |
| Đặt priority, delivery mode, time-to-live | QoS của JmsTemplate/MessageProducer |
| Lọc consumer theo eventType hoặc version | JMS property + selector |
| Serialize định dạng không được converter hỗ trợ | Custom MessageConverter hoặc MessageCreator |

MessagePostProcessor đặc biệt hữu ích khi metadata phụ thuộc vào từng lần gửi, như correlation ID, event ID hoặc tenant đã được server xác thực. Nếu metadata là cố định cho mọi message, có thể cấu hình trong converter hoặc lớp gửi message chung; tránh lặp cùng một quy tắc ở nhiều nơi.

## 14. Checklist trước khi phát hành

1. Converter đang dùng tạo ra loại JMS Message nào?
2. Processor có chạy sau conversion và trước khi send không?
3. Có trả về đúng JMS Message cần gửi không?
4. Property name có tuân theo quy tắc JMS và tránh prefix dành riêng không?
5. Property value có thuộc kiểu dữ liệu JMS hỗ trợ không?
6. JMSCorrelationID, JMSType hoặc JMSReplyTo có đúng contract không?
7. Có đang cố đặt QoS bằng property thay vì producer configuration không?
8. Có vô tình ghi đè type ID property của JSON converter không?
9. Processor có stateless/thread-safe khi được tái sử dụng không?
10. Metadata từ client đã được validate và xác thực chưa?
11. Exception trong processor có được xử lý đúng không?
12. Integration test đã kiểm tra broker, selector và consumer chưa?

## 15. Tài liệu tham khảo

- [MessagePostProcessor — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/core/MessagePostProcessor.html)
- [JmsTemplate — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [MessageConverter — Spring JMS Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/support/converter/MessageConverter.html)
- [MappingJackson2MessageConverter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html)
- [Jakarta Messaging 3.1 — Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message)
- [Jakarta Messaging 3.1 — MessageProducer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer)
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html)

MessagePostProcessor là bước hoàn thiện JMS message sau khi converter đã tạo body. Dùng nó cho metadata theo từng lần gửi; để MessageConverter xử lý serialization, MessageCreator xử lý việc tự tạo message bằng Session và JmsTemplate/MessageProducer quản lý QoS. Ranh giới rõ ràng giữa ba phần giúp payload, metadata và chính sách giao nhận dễ kiểm thử, vận hành.