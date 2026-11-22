# Tham số payload, Message, header, Session và chuyển đổi dữ liệu

Một method gắn @JmsListener có thể nhận trực tiếp payload nghiệp vụ, một header cụ thể, toàn bộ header đã ánh xạ, Spring Message, JMS Message gốc hoặc JMS Session. Spring phân giải các tham số này thông qua adapter và hệ thống HandlerMethodArgumentResolver.

Việc chọn đúng kiểu tham số giúp listener vừa gọn cho xử lý nghiệp vụ, vừa có thể truy cập metadata hoặc API JMS khi thật sự cần. Spring Message và JMS Message là hai abstraction khác nhau; converter của Spring Messaging và converter của Spring JMS cũng có vai trò riêng.

## 1. Luồng nhận và phân giải tham số

Khi một message đến destination được khai báo trong @JmsListener, listener container nhận JMS Message và gọi MessagingMessageListenerAdapter để chuyển giao cho method.

~~~text
JMS provider
    |
    v
Listener container
    |
    v
Raw jakarta.jms.Message + jakarta.jms.Session
    |
    v
MessagingMessageListenerAdapter
    |
    | tạo Spring Message
    | map JMS headers bằng JmsHeaderMapper
    | chuyển body bằng JMS MessageConverter
    v
org.springframework.messaging.Message<?>
    |
    v
DefaultMessageHandlerMethodFactory
    |
    | @Payload / payload parameter
    | @Header / @Headers
    | Spring Message / MessageHeaders
    | raw JMS Message / Session
    v
@JmsListener method
~~~

MessagingMessageListenerAdapter giữ lại raw JMS Message và Session để có thể truyền chúng vào method nếu chữ ký yêu cầu. Đồng thời, adapter tạo Spring Message chứa payload cùng các header đã được ánh xạ.

## 2. Nhận payload trực tiếp

### 2.1. Tham số không annotation mặc định là payload

Một tham số method không thuộc nhóm kiểu đặc biệt như Message hoặc Session được xem là payload nếu không có annotation khác xác định cách phân giải.

~~~java
public record OrderCreated(String orderId, int quantity) {}

@Component
public class OrderListener {

    @JmsListener(destination = "orders.events")
    public void receive(OrderCreated event) {
        System.out.println(event.orderId());
    }
}
~~~

Spring lấy payload của message, chuyển đổi sang OrderCreated theo converter và cấu hình đang sử dụng, rồi truyền vào method.

Nếu muốn thể hiện rõ vai trò của tham số, dùng @Payload:

~~~java
@JmsListener(destination = "orders.events")
public void receive(@Payload OrderCreated event) {
    process(event);
}
~~~

@Payload hữu ích khi method có nhiều tham số hoặc khi cần gắn thêm validation.

### 2.2. Payload có thể là kiểu đơn giản hoặc domain object

Một listener có thể nhận:

- String khi body là text.
- byte[] khi body là dữ liệu nhị phân.
- Map khi body được biểu diễn bằng MapMessage.
- Một object Serializable khi dùng ObjectMessage và converter tương ứng.
- Domain object như OrderCreated khi converter đã được cấu hình để giải mã định dạng gửi đến.

Kiểu tham số phải tương thích với payload sau chuyển đổi. Nếu JMS TextMessage được converter mặc định chuyển thành String, method nhận OrderCreated sẽ cần thêm converter có khả năng phân tích định dạng nội dung đó.

Không nên cho rằng tên class ở tham số method tự khiến mọi JSON hoặc XML được giải mã. Cần cấu hình converter và hợp đồng serialization phù hợp.

## 3. Nhận một header bằng @Header

@Header lấy một giá trị header từ Spring Message và gắn nó vào tham số method.

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.events")
    public void receive(
            @Payload OrderCreated event,
            @Header(JmsHeaders.CORRELATION_ID) String correlationId,
            @Header("appSource") String source) {

        process(event, correlationId, source);
    }
}
~~~

Trong ví dụ:

- JmsHeaders.CORRELATION_ID là tên header Spring dùng cho JMSCorrelationID.
- appSource là application property do producer gửi, nếu header mapper đã ánh xạ property đó vào Spring Message headers.
- Spring phân giải header theo tên và chuyển kiểu sang kiểu tham số khi ConversionService hỗ trợ.

Nên dùng hằng số JmsHeaders cho metadata JMS chuẩn thay vì tự viết chuỗi tên header.

### 3.1. Header bắt buộc và header tùy chọn

Mặc định, @Header yêu cầu header phải tồn tại. Nếu header không có và không có giá trị mặc định, việc phân giải tham số sẽ thất bại.

Có thể khai báo header tùy chọn:

~~~java
@JmsListener(destination = "orders.events")
public void receive(
        @Header(name = "appSource", required = false) String source) {

    String actualSource = (source != null ? source : "unknown");
    processSource(actualSource);
}
~~~

Hoặc cung cấp defaultValue:

~~~java
@JmsListener(destination = "orders.events")
public void receive(
        @Header(
                name = "appSchemaVersion",
                required = false,
                defaultValue = "1"
        ) Integer schemaVersion) {

    processVersion(schemaVersion);
}
~~~

Default value được biểu diễn dưới dạng String rồi chuyển sang kiểu tham số nếu ConversionService hỗ trợ. Nếu dùng kiểu primitive, hãy cung cấp defaultValue hoặc bảo đảm header luôn có mặt để tránh tình huống không thể truyền null.

### 3.2. Header JMS chuẩn và application property

JmsHeaders định nghĩa các key chuẩn để biểu diễn thuộc tính JMS trong Spring Message.

| Hằng số | Key Spring | Giá trị thường gặp |
|---|---|---|
| JmsHeaders.CORRELATION_ID | jms_correlationId | String |
| JmsHeaders.DESTINATION | jms_destination | Destination |
| JmsHeaders.DELIVERY_MODE | jms_deliveryMode | Integer |
| JmsHeaders.EXPIRATION | jms_expiration | Long |
| JmsHeaders.MESSAGE_ID | jms_messageId | String |
| JmsHeaders.PRIORITY | jms_priority | Integer |
| JmsHeaders.REDELIVERED | jms_redelivered | Boolean |
| JmsHeaders.REPLY_TO | jms_replyTo | Destination |
| JmsHeaders.TIMESTAMP | jms_timestamp | Long |
| JmsHeaders.TYPE | jms_type | String |

Các header như destination, message ID, timestamp, delivery mode và priority thường là metadata do provider quản lý hoặc chỉ đọc ở phía consumer.

Application property do producer tự đặt có thể được đọc bằng tên key tương ứng nếu JmsHeaderMapper ánh xạ property đó.

~~~java
@JmsListener(destination = "orders.events")
public void receive(
        @Header("appEventId") String eventId,
        @Header("appSchemaVersion") Integer schemaVersion) {

    process(eventId, schemaVersion);
}
~~~

Không nhầm key Spring jms_correlationId với tên property JMS tùy chỉnh. Nếu cần truy cập thuộc tính JMS trực tiếp, có thể dùng raw JMS Message.

## 4. Nhận toàn bộ header bằng @Headers

Nếu method cần nhiều metadata, @Headers có thể đưa toàn bộ header đã được ánh xạ vào một Map<String, Object>.

~~~java
@JmsListener(destination = "orders.events")
public void receive(
        @Payload OrderCreated event,
        @Headers Map<String, Object> headers) {

    Object correlationId =
            headers.get(JmsHeaders.CORRELATION_ID);

    Object source = headers.get("appSource");

    process(event, correlationId, source);
}
~~~

Tham số có @Headers phải có kiểu có thể gán cho java.util.Map. Map chứa các header mà adapter/header mapper đã đưa vào Spring Message; nó không phải bản sao nguyên vẹn của mọi trường trong JMS provider.

Cách này phù hợp khi logic cần kiểm tra một nhóm metadata hoặc chuyển header vào một thành phần xử lý chung. Nếu chỉ cần một hoặc hai giá trị, @Header giúp chữ ký method rõ ràng hơn.

Không sửa trực tiếp Map hoặc MessageHeaders để thay đổi message đang nhận. MessageHeaders của Spring là immutable. Nếu cần tạo message mới với header khác, hãy dùng MessageBuilder hoặc MessageHeaderAccessor.

## 5. Nhận Spring Message<T>

org.springframework.messaging.Message<T> là abstraction của Spring, chứa cả payload và MessageHeaders.

~~~java
import org.springframework.messaging.Message;

@JmsListener(destination = "orders.events")
public void receive(Message<OrderCreated> message) {
    OrderCreated event = message.getPayload();

    String correlationId = message.getHeaders().get(
            JmsHeaders.CORRELATION_ID,
            String.class
    );

    Object source = message.getHeaders().get("appSource");

    process(event, correlationId, source);
}
~~~

Dùng Spring Message khi method cần cả payload và metadata, nhưng không muốn phụ thuộc trực tiếp vào API Jakarta JMS.

Spring Message cung cấp một góc nhìn thống nhất cho nhiều integration. JMS standard headers được ánh xạ vào các key thuộc JmsHeaders; application headers được giữ theo cấu hình của header mapper.

### 5.1. Dùng MessageHeaders hoặc JmsMessageHeaderAccessor

Nếu chỉ cần toàn bộ metadata, có thể nhận MessageHeaders hoặc một accessor chuyên biệt theo hỗ trợ của method argument resolver.

JmsMessageHeaderAccessor cung cấp các getter có kiểu cho thuộc tính JMS:

~~~java
@JmsListener(destination = "orders.events")
public void receive(Message<OrderCreated> message) {
    JmsMessageHeaderAccessor accessor =
            JmsMessageHeaderAccessor.wrap(message);

    String correlationId = accessor.getCorrelationId();
    String messageId = accessor.getMessageId();
    Integer priority = accessor.getPriority();
    Boolean redelivered = accessor.getRedelivered();
    Destination replyTo = accessor.getReplyTo();

    process(correlationId, messageId, priority, redelivered, replyTo);
}
~~~

Các getter này giúp giảm lỗi do tự viết tên header hoặc ép kiểu thủ công. Accessor đọc header đã được ánh xạ vào Spring Message; nó không thay thế raw JMS Message khi cần gọi API native mà mapper không cung cấp.

Spring Message ID và JMS message ID là hai giá trị khác nhau:

- message.getHeaders().getId() là ID của Spring Message instance.
- accessor.getMessageId() là JMSMessageID do provider quản lý.

Không dùng hai ID này thay thế lẫn nhau trong contract nghiệp vụ.

## 6. Nhận raw jakarta.jms.Message

Nếu method cần truy cập đầy đủ API của JMS provider hoặc các trường không có trong Spring header mapping, có thể nhận raw jakarta.jms.Message.

~~~java
@JmsListener(destination = "orders.events")
public void receive(jakarta.jms.Message rawMessage)
        throws JMSException {

    String correlationId = rawMessage.getJMSCorrelationID();
    String type = rawMessage.getJMSType();

    String eventId = rawMessage.getStringProperty("appEventId");
    boolean hasSource = rawMessage.propertyExists("appSource");

    String source = hasSource
            ? rawMessage.getStringProperty("appSource")
            : null;

    inspect(correlationId, type, eventId, source);
}
~~~

Raw JMS Message cho phép truy cập:

- JMSCorrelationID, JMSReplyTo, JMSType và các standard headers.
- Application properties bằng getStringProperty, getIntProperty, getObjectProperty và các getter tương ứng.
- Body theo kiểu message cụ thể như TextMessage, BytesMessage hoặc MapMessage.
- Các metadata và API mà provider hỗ trợ.

### 6.1. Nhận một subclass cụ thể

Có thể khai báo trực tiếp subclass nếu listener chỉ xử lý một loại JMS message:

~~~java
@JmsListener(destination = "orders.text")
public void receive(TextMessage message) throws JMSException {
    String body = message.getText();
    processText(body);
}
~~~

Message nhận vào phải thực sự là TextMessage. Nếu provider gửi BytesMessage hoặc MapMessage, kiểu tham số không tương thích và listener không thể xử lý theo method này.

Khi destination có thể nhận nhiều loại message, dùng jakarta.jms.Message tổng quát rồi kiểm tra kiểu trước khi truy cập body:

~~~java
@JmsListener(destination = "mixed.events")
public void receive(jakarta.jms.Message message)
        throws JMSException {

    if (message instanceof TextMessage textMessage) {
        processText(textMessage.getText());
    }
    else if (message instanceof BytesMessage bytesMessage) {
        processBytes(bytesMessage);
    }
    else {
        throw new IllegalArgumentException(
                "Unsupported JMS message type: "
                        + message.getClass().getName()
        );
    }
}
~~~

Đoạn trên minh họa kiểm tra loại message; phần đọc BytesMessage cần tuân theo API đọc byte và độ dài body của JMS. Với hệ thống có contract rõ ràng, tốt hơn nên thống nhất message type và converter thay vì để một listener nhận nhiều định dạng không liên quan.

## 7. Nhận JMS Session

Method listener có thể nhận jakarta.jms.Session để dùng native JMS API. Session hữu ích khi cần:

- Tạo một JMS Message theo kiểu cụ thể.
- Tạo MessageProducer hoặc consumer theo nhu cầu.
- Gửi reply bằng cùng session của lần xử lý hiện tại.
- Truy cập API JMS mà JmsTemplate hoặc Spring Message abstraction không biểu diễn trực tiếp.

Ví dụ đọc raw message, lấy JMSReplyTo và gửi reply bằng Session:

~~~java
@JmsListener(destination = "orders.commands")
public void handle(
        OrderCommand command,
        jakarta.jms.Message request,
        Session session) throws JMSException {

    Destination replyTo = request.getJMSReplyTo();

    if (replyTo == null) {
        return;
    }

    MessageProducer producer = session.createProducer(replyTo);
    try {
        TextMessage reply = session.createTextMessage("accepted");
        reply.setJMSCorrelationID(request.getJMSCorrelationID());
        producer.send(reply);
    }
    finally {
        producer.close();
    }
}
~~~

Ví dụ giả định message có JMSReplyTo hợp lệ. Session được listener container cung cấp và quản lý. Ứng dụng chỉ đóng MessageProducer do mình tạo; không tự đóng Session hoặc Connection do container sở hữu.

JMS Session không được thiết kế để chia sẻ đồng thời giữa nhiều thread. Không lưu Session vào field của singleton listener, không truyền nó sang tác vụ bất đồng bộ và không sử dụng sau khi lần gọi listener kết thúc.

Nếu chỉ cần trả payload về một destination cố định hoặc dùng JMSReplyTo, có thể dùng method return value kết hợp @SendTo. Cách đó thường ít phụ thuộc JMS API hơn việc tự tạo producer bằng Session.

## 8. Phân biệt ba kiểu Message

Trong code listener, có thể gặp ba khái niệm mang tên Message:

| Kiểu | Package | Nội dung |
|---|---|---|
| Raw JMS Message | jakarta.jms.Message | Message gốc do JMS provider gửi |
| Spring Message<T> | org.springframework.messaging.Message | Payload Java và Spring MessageHeaders |
| MessageHeaders | org.springframework.messaging.MessageHeaders | Metadata đã được Spring ánh xạ |

Không import nhầm hai interface Message trong cùng một class. Khi method cần cả raw JMS Message và Spring Message, dùng import cho Spring Message rồi viết fully qualified name cho raw JMS type hoặc ngược lại.

Ví dụ:

~~~java
import org.springframework.messaging.Message;

@JmsListener(destination = "orders.events")
public void receive(
        Message<OrderCreated> springMessage,
        jakarta.jms.Message rawMessage,
        Session session) throws JMSException {

    OrderCreated payload = springMessage.getPayload();
    String correlationId = rawMessage.getJMSCorrelationID();

    process(payload, correlationId);
}
~~~

Không phải listener nào cũng cần cả ba. Hãy chọn kiểu tham số theo phần dữ liệu mà logic thực sự sử dụng.

## 9. Chuyển đổi dữ liệu từ JMS body sang payload

Đây là phần quan trọng khi method khai báo kiểu payload cụ thể như OrderCreated.

Có hai lớp chuyển đổi cần phân biệt:

1. **JMS MessageConverter:** thuộc package org.springframework.jms.support.converter. Nó đọc body của jakarta.jms.Message và chuyển thành object Java; ví dụ TextMessage thành String hoặc JSON TextMessage thành OrderCreated.
2. **Spring Messaging MessageConverter và ConversionService:** thuộc package org.springframework.messaging.converter và org.springframework.core.convert. Chúng tham gia phân giải payload/header thành kiểu tham số method mà DefaultMessageHandlerMethodFactory yêu cầu.

Listener adapter sử dụng MessagingMessageConverter để tạo Spring Message. Converter này kết hợp một JMS payload converter với JmsHeaderMapper để ánh xạ JMS headers sang Spring MessageHeaders. Sau đó DefaultMessageHandlerMethodFactory dùng argument resolver để gắn payload, header và các tham số đặc biệt vào method.

### 9.1. SimpleMessageConverter mặc định

SimpleMessageConverter của Spring JMS hỗ trợ các kiểu JMS phổ biến:

| JMS message | Payload Java |
|---|---|
| TextMessage | String |
| BytesMessage | byte[] |
| MapMessage | Map |
| ObjectMessage | Serializable object |

Ví dụ:

- TextMessage chứa "order-42" trở thành String.
- BytesMessage chứa byte payload trở thành byte[].
- MapMessage trở thành Map với các key/value đã được đọc.
- ObjectMessage có thể trở thành object Serializable nếu class có thể được deserialize.

Nếu method nhận String hoặc byte[] tương ứng, payload thường đã đúng kiểu và không cần chuyển đổi thêm.

Không dùng ObjectMessage với object từ nguồn không tin cậy nếu chưa cấu hình chính sách deserialization/trusted package phù hợp. Với tích hợp giữa nhiều service, JSON hoặc schema format có version thường dễ kiểm soát hơn Java serialization.

### 9.2. Chuyển JSON TextMessage thành domain object

Nếu producer gửi JSON trong TextMessage và listener muốn nhận OrderCreated, cần JMS converter hiểu JSON.

Ví dụ cấu hình MappingJackson2MessageConverter:

~~~java
@Bean
public org.springframework.jms.support.converter.MessageConverter
        orderJmsMessageConverter() {

    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();

    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    converter.setTypeIdMappings(
            Map.of("order-created", OrderCreated.class)
    );

    return converter;
}
~~~

Gắn converter vào listener container factory:

~~~java
@Bean
public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory,
        org.springframework.jms.support.converter.MessageConverter
                orderJmsMessageConverter) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setMessageConverter(orderJmsMessageConverter);

    return factory;
}
~~~

Producer cần gửi type ID property _type với giá trị order-created theo contract đã cấu hình. Mapping này cho phép converter chọn OrderCreated mà không cần truyền tên class Java nội bộ.

Listener có thể nhận:

~~~java
@JmsListener(destination = "orders.events")
public void receive(@Payload OrderCreated event) {
    process(event);
}
~~~

Ví dụ dùng Jackson 2 và API MappingJackson2MessageConverter của Spring Framework 6.1. Nếu dự án dùng converter khác, cần cấu hình type mapping, content type và message type tương ứng.

Không cho producer bên ngoài tự do gửi tên class tùy ý để deserialize. Dùng type ID allowlist hoặc mapping cố định sang các kiểu đã được ứng dụng cho phép.

### 9.3. ConversionService của method argument factory

DefaultMessageHandlerMethodFactory mặc định dùng GenericMessageConverter của Spring Messaging cùng ConversionService để xử lý việc chuyển đổi payload và header sang kiểu tham số.

Ví dụ nếu payload đã là String "42", method có thể yêu cầu Integer khi ConversionService hỗ trợ chuyển đổi String sang Integer:

~~~java
@JmsListener(destination = "metrics.values")
public void receive(@Payload Integer value) {
    processValue(value);
}
~~~

Tuy nhiên, GenericMessageConverter không phải JSON parser. Nó không tự biến chuỗi JSON thành OrderCreated. Muốn giải mã JSON, hãy cấu hình JMS JSON converter như phần trước.

ConversionService cũng có thể chuyển header String thành kiểu tham số như Integer hoặc Boolean nếu có converter phù hợp. Khi thay đổi conversion service, cần kiểm thử cả payload lẫn header để tránh thay đổi ngoài ý muốn.

### 9.4. Hai MessageConverter khác package

| Converter | Package | Công việc |
|---|---|---|
| JMS MessageConverter | org.springframework.jms.support.converter | Chuyển Java object và jakarta.jms.Message |
| Spring Messaging MessageConverter | org.springframework.messaging.converter | Chuyển payload của Spring Message sang kiểu Java hoặc dạng serialized |

DefaultJmsListenerContainerFactory.setMessageConverter nhận converter thuộc Spring JMS. DefaultMessageHandlerMethodFactory.setMessageConverter nhận converter thuộc Spring Messaging.

Hai method có cùng tên nhưng cấu hình ở hai tầng khác nhau. Khi dùng import, nên ghi rõ package nếu có cả hai interface trong một file.

## 10. Tùy chỉnh method argument resolution

DefaultMessageHandlerMethodFactory là thành phần tạo các argument resolver cho method được đánh dấu @JmsListener.

Có thể tùy chỉnh:

- setValidator(Validator): xác thực payload có @Valid hoặc annotation validation tương ứng.
- setConversionService(ConversionService): điều chỉnh chuyển đổi payload/header.
- setMessageConverter(MessageConverter): thay converter của Spring Messaging dùng khi bind tham số.
- setCustomArgumentResolvers(...): bổ sung resolver cho kiểu tham số riêng.
- setArgumentResolvers(...): thay toàn bộ danh sách resolver; đây là tùy chọn nâng cao.

Ví dụ bật validation cho payload:

~~~java
@Configuration
@EnableJms
public class JmsMethodConfiguration implements JmsListenerConfigurer {

    private final Validator validator;

    public JmsMethodConfiguration(Validator validator) {
        this.validator = validator;
    }

    @Bean
    public DefaultMessageHandlerMethodFactory jmsHandlerMethodFactory() {
        DefaultMessageHandlerMethodFactory factory =
                new DefaultMessageHandlerMethodFactory();

        factory.setValidator(validator);
        return factory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        registrar.setMessageHandlerMethodFactory(
                jmsHandlerMethodFactory()
        );
    }
}
~~~

Listener:

~~~java
@JmsListener(destination = "orders.events")
public void receive(@Payload @Valid OrderCreated event) {
    process(event);
}
~~~

Ví dụ giả định OrderCreated có các constraint Jakarta Validation và Validator đã được cấu hình trong ApplicationContext. Nếu validation thất bại, method listener không được gọi với payload không hợp lệ; lỗi được chuyển qua cơ chế xử lý lỗi của listener container.

Nếu cần tham số đặc biệt, ví dụ một tenant context đã được xác thực hoặc một metadata wrapper riêng, có thể triển khai HandlerMethodArgumentResolver rồi đăng ký qua setCustomArgumentResolvers. Chỉ dùng custom resolver khi kiểu tham số thực sự lặp lại và có contract rõ ràng.

## 11. Header mapping và cách đọc metadata

MessagingMessageListenerAdapter dùng JmsHeaderMapper để chuyển JMS standard headers sang Spring Message headers. Application properties cũng có thể được mapper đưa vào header map theo cấu hình.

Nên dùng JmsHeaders cho metadata chuẩn:

~~~java
@JmsListener(destination = "orders.events")
public void receive(
        @Header(JmsHeaders.CORRELATION_ID) String correlationId,
        @Header(JmsHeaders.MESSAGE_ID) String jmsMessageId,
        @Header("appEventId") String eventId) {

    log(correlationId, jmsMessageId, eventId);
}
~~~

Nếu custom property không xuất hiện trong Spring headers, kiểm tra JmsHeaderMapper đang dùng. Khi cần đọc property native trực tiếp, dùng raw JMS Message:

~~~java
@JmsListener(destination = "orders.events")
public void receive(jakarta.jms.Message message) throws JMSException {
    if (message.propertyExists("appEventId")) {
        String eventId = message.getStringProperty("appEventId");
        process(eventId);
    }
}
~~~

Không giả định tất cả JMS metadata đều có thể ghi từ phía consumer. Nhiều trường như JMSMessageID, JMSTimestamp, JMSRedelivered, destination hoặc priority được provider quản lý và chỉ có ý nghĩa đọc ở listener.

Nếu cần tùy chỉnh việc ánh xạ, có thể cấu hình JmsHeaderMapper phù hợp trong MessagingMessageConverter. Khi thay đổi mapping, hãy kiểm tra cả header chuẩn và application property trên broker thật.

## 12. Lỗi thường gặp khi khai báo tham số listener

### 12.1. Method nhận sai kiểu payload

Ví dụ incoming message là TextMessage nhưng method yêu cầu một domain object mà converter không hỗ trợ. Kiểm tra message type, JMS MessageConverter và định dạng body.

### 12.2. JSON bị đưa vào method dưới dạng String

SimpleMessageConverter chỉ chuyển TextMessage thành String. Cấu hình MappingJackson2MessageConverter hoặc một converter JSON tương thích nếu cần domain object.

### 12.3. Header không tồn tại

@Header mặc định yêu cầu header phải có. Kiểm tra tên key, JmsHeaderMapper, producer property và dùng required=false/defaultValue khi nghiệp vụ cho phép.

### 12.4. Dùng sai tên JMS header

JMSCorrelationID được ánh xạ vào JmsHeaders.CORRELATION_ID. Dùng hằng số Spring để đọc header chuẩn thay vì đoán key dạng jms_...

### 12.5. Nhầm raw JMS Message với Spring Message

jakarta.jms.Message là message native; org.springframework.messaging.Message là wrapper payload + headers. Kiểm tra import và kiểu tham số.

### 12.6. Dùng Session sau khi listener kết thúc

Session thuộc listener container và có vòng đời theo lần xử lý. Không lưu Session vào singleton hoặc dùng trong thread khác.

### 12.7. @Headers nhận kiểu không phải Map

Tham số có @Headers phải assignable to java.util.Map. Nếu chỉ cần một header, dùng @Header thay vì nhận toàn bộ map.

### 12.8. ConversionService không hỗ trợ kiểu đích

GenericMessageConverter có thể không tìm được converter cho cặp kiểu nguồn/đích. Đăng ký custom Converter hoặc dùng converter chuyên biệt cho định dạng serialized.

### 12.9. Header bị ép kiểu sai

Một JMS property có thể được gửi dưới kiểu String nhưng method lại yêu cầu Integer hoặc enum. Kiểm tra kiểu thật ở producer và ConversionService được cấu hình cho listener.

### 12.10. Validation thất bại

Nếu payload có @Valid nhưng Validator chưa được cấu hình, validation có thể không chạy theo mong muốn. Đăng ký Validator với DefaultMessageHandlerMethodFactory và kiểm thử payload không hợp lệ.

## 13. Kiểm thử listener method signature và conversion

Nên kiểm thử từng nhóm tham số và ít nhất một luồng integration qua broker.

Unit test hoặc method-level test có thể xác nhận:

1. Payload được gắn đúng vào tham số @Payload.
2. @Header lấy đúng standard JMS header.
3. @Header lấy đúng application property đã map.
4. required=false và defaultValue hoạt động như contract.
5. @Headers chứa các key mong đợi.
6. Spring Message giữ payload và header.
7. JmsMessageHeaderAccessor trả về correlation ID, message ID và reply destination đúng.
8. Raw JMS Message được truyền khi method khai báo kiểu phù hợp.
9. Session được cung cấp cho lần gọi listener.
10. @Valid từ chối payload không hợp lệ.

Integration test với broker cần kiểm tra:

- TextMessage, BytesMessage, MapMessage và ObjectMessage theo contract.
- JSON type ID và mapping sang domain class.
- JMS standard headers và custom properties sau khi đi qua mapper.
- ConversionException khi payload sai định dạng.
- Missing header và default value.
- Message subclass mismatch.
- Reply qua JMSReplyTo hoặc @SendTo.
- Transaction/acknowledgement và redelivery khi listener ném exception.

Không chỉ gọi method bằng một object Java đã dựng sẵn rồi kết luận JMS converter và header mapping hoạt động đúng. Các bước nhận raw JMS Message, chuyển đổi body và map metadata chỉ được xác nhận đầy đủ khi chạy qua adapter/container thực tế.

## 14. Checklist thiết kế chữ ký @JmsListener

- Tham số payload có đúng kiểu sau khi JMS converter chạy không?
- Có nên dùng @Payload để làm rõ vai trò tham số không?
- Chỉ lấy các header cần thiết bằng @Header?
- Header JMS chuẩn có dùng hằng số JmsHeaders không?
- Header tùy chọn đã có required=false hoặc defaultValue phù hợp chưa?
- Có thực sự cần toàn bộ Map qua @Headers không?
- Dùng Spring Message<T> khi cần cả payload và metadata?
- Dùng raw jakarta.jms.Message chỉ khi cần API JMS native?
- Có cần Session cho thao tác JMS cấp thấp không?
- Session và producer có được quản lý vòng đời đúng không?
- JMS MessageConverter và Spring Messaging MessageConverter đã được cấu hình đúng tầng chưa?
- JSON/XML có converter chuyên biệt và type mapping an toàn chưa?
- ConversionService có hỗ trợ kiểu header/payload đích không?
- @Valid có Validator được đăng ký không?
- Integration test đã xác minh header mapping, body conversion và transaction chưa?

## 15. Tài liệu tham khảo

- [Spring Framework Reference — Annotation-driven JMS Listener Endpoints](https://docs.spring.io/spring-framework/docs/6.1.x/reference/html/integration.html)
- [JmsListener — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [MessagingMessageListenerAdapter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/listener/adapter/MessagingMessageListenerAdapter.html)
- [JmsHeaders — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/support/JmsHeaders.html)
- [JmsMessageHeaderAccessor — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/support/JmsMessageHeaderAccessor.html)
- [MessagingMessageConverter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/support/converter/MessagingMessageConverter.html)
- [SimpleMessageConverter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html)
- [MappingJackson2MessageConverter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html)
- [DefaultMessageHandlerMethodFactory — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/handler/annotation/support/DefaultMessageHandlerMethodFactory.html)
- [PayloadMethodArgumentResolver — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/handler/annotation/support/PayloadMethodArgumentResolver.html)

Một chữ ký listener tốt chỉ nhận đúng phần thông tin mà nghiệp vụ cần. Hãy dùng payload cho dữ liệu nghiệp vụ, @Header cho metadata cụ thể, Spring Message khi cần payload cùng headers, raw JMS Message và Session khi cần native JMS API; đồng thời cấu hình riêng converter ở tầng JMS và tầng method argument để tránh nhầm lẫn khi chuyển đổi dữ liệu.