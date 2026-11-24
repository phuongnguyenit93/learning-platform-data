# JMS message converter

## 1. Vì sao cần MessageConverter trong JMS?

Hệ thống bán hàng gửi sự kiện `OrderPaid` tới queue `orders.paid`. Ở phía gửi, code Java đang có một DTO; ở phía nhận, nghiệp vụ muốn xử lý các trường như `eventId`, `orderId` và `amountMinor`. Tuy nhiên, JMS broker không truyền một DTO Java bất kỳ theo cách mà mọi ngôn ngữ đều hiểu. Broker truyền **JMS Message** như `TextMessage`, `BytesMessage`, `MapMessage` hoặc `ObjectMessage`; phần nội dung đó phải được quy đổi sang định dạng phù hợp với hai phía.

**JMS `MessageConverter`** là thành phần đảm nhận chuyển đổi giữa **đối tượng Java** và **body của JMS Message**. Trong Spring JMS, interface cần biết là `org.springframework.jms.support.converter.MessageConverter`; `JmsTemplate`, các JMS adapter và gateway của Spring Integration sử dụng converter này để giảm code thao tác JMS thuần.

Đây là một kiến thức nền của module **SPRING_INTEGRATION_ADAPTERS**: module kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`, rồi áp dụng hợp đồng message, xử lý lỗi và vòng đời kết nối cho file, SFTP, HTTP, JMS, AMQP, Kafka và database. Bài học tập trung vào **JMS message converter**: cách chuyển payload, giữ đúng headers, cấu hình converter cho từng loại endpoint và xử lý dữ liệu sai định dạng.

Sau bài này, bạn có thể:

1. Phân biệt **JMS Message**, **Spring Message**, **MessageConverter**, **HeaderMapper** và transformer của Spring Integration.
2. Giải thích cách `SimpleMessageConverter` chuyển `String`, `byte[]`, `Map` và đối tượng Java có thể serialize.
3. Chọn hai chiến lược trao đổi JSON: **`String` + `ObjectMapper`** và **Jackson JMS converter + DTO**.
4. Cấu hình converter cho `JmsTemplate`, JMS inbound/outbound channel adapter và gateway.
5. Thiết kế hợp đồng schema/version, xử lý conversion error, transaction, retry và dữ liệu không tin cậy.

## 2. Hai loại Message và nơi conversion diễn ra

Spring Integration tách biệt message nội bộ với message bên ngoài:

| Đối tượng | Thuộc thư viện | Chứa gì? | Đi qua đâu? |
|---|---|---|---|
| JMS `Message` | `jakarta.jms.Message` | Body JMS, JMS header và JMS properties | Broker/connection JMS |
| Spring `Message<T>` | `org.springframework.messaging.Message<T>` | `payload` kiểu Java và `MessageHeaders` | `MessageChannel` trong Spring Integration |
| JMS `MessageConverter` | `org.springframework.jms.support.converter.MessageConverter` | Quy tắc Java object ↔ JMS body | `JmsTemplate`, adapter/gateway |
| JMS `JmsHeaderMapper` | `org.springframework.integration.jms.JmsHeaderMapper` | Quy tắc ánh xạ metadata JMS ↔ Spring headers | Adapter/gateway Spring Integration |
| Transformer/validator | Các bước trong IntegrationFlow | Quy tắc dữ liệu/DTO/schema nghiệp vụ | Sau inbound hoặc trước outbound endpoint |

Đường gửi:

~~~mermaid
flowchart LR
    A["Java DTO hoặc JSON String"] --> B["Spring Message payload"]
    B --> C["JMS outbound adapter / gateway"]
    C --> D["MessageConverter: Java -> JMS body"]
    C --> E["HeaderMapper: Spring headers -> JMS metadata"]
    D --> F[("JMS Message trên broker")]
    E --> F
~~~

Đường nhận:

~~~mermaid
flowchart LR
    A[("JMS Message từ broker")] --> B["JMS inbound adapter / gateway"]
    B --> C["MessageConverter: JMS body -> Java object"]
    B --> D["HeaderMapper: JMS metadata -> Spring headers"]
    C --> E["Spring Message"]
    D --> E
    E --> F["MessageChannel"]
    F --> G["Validate -> Handler"]
~~~

Một ví dụ cụ thể: producer gửi `TextMessage` có chuỗi JSON `{"eventId":"evt-901"}` và JMS property `eventType=OrderPaid`. Nếu dùng converter mặc định, Spring Message có thể mang payload `String` chứa JSON và header được ánh xạ từ `eventType`. **Converter không tự validate `eventId`, không tự ghi DB và không biến header thành một phần của JSON body.**

### `HeaderMappingMessageConverter` trong Spring Integration

Khi tích hợp JMS adapter/gateway, Spring Integration có thể bọc `MessageConverter` được cung cấp trong `HeaderMappingMessageConverter`. Lớp bọc này phối hợp phép chuyển đổi body với `JmsHeaderMapper`. Vì vậy, đưa một converter tùy chỉnh vào endpoint **không tự tắt việc ánh xạ JMS headers**; đồng thời `extractPayload`/`extractRequestPayload`/`extractReplyPayload` vẫn quyết định **đối tượng nào** được đưa tới converter.

Khi viết converter riêng, cần hiểu đúng ranh giới:

- **Converter** quyết định biểu diễn của body (`TextMessage` JSON, `BytesMessage` binary...).
- **Header mapper** xử lý metadata được phép ánh xạ; không phải mọi Spring header hợp lệ là JMS property.
- **Transformer** chuyển DTO nghiệp vụ, kiểm tra schema hoặc thay đổi hình dạng dữ liệu theo yêu cầu hệ thống.

## 3. `SimpleMessageConverter`: hành vi mặc định

`SimpleMessageConverter` của Spring JMS thường là converter mặc định khi ứng dụng không cấu hình loại khác.

| Java object gửi đi | JMS message thường tạo | Java object khi nhận lại | Lưu ý |
|---|---|---|---|
| `String` | `TextMessage` | `String` | Thích hợp JSON/XML dạng text |
| `byte[]` | `BytesMessage` | `byte[]` | Phải thống nhất encoding/format |
| `Map` có kiểu JMS hỗ trợ | `MapMessage` | `Map` | JMS map có giới hạn về các kiểu value |
| `Serializable` | `ObjectMessage` | Đối tượng Java | Phụ thuộc Java serialization và tương thích class |

Một DTO Java **không mặc nhiên trở thành JSON** chỉ vì dự án có Jackson:

~~~java
// Có thể tạo ObjectMessage nếu OrderPaidEvent implements Serializable,
// hoặc gặp MessageConversionException nếu kiểu không được hỗ trợ.
jmsTemplate.convertAndSend("orders.paid", orderPaidEvent);
~~~

Nếu hệ thống nhận dùng .NET, JavaScript hoặc ngôn ngữ khác, `ObjectMessage` không phải hợp đồng liên dịch vụ phù hợp. Nó còn đặt ra rủi ro deserialization khi nhận dữ liệu không tin cậy và vấn đề tương thích class giữa hai lần triển khai. **Ưu tiên JSON `TextMessage` hoặc định dạng binary có schema** cho hệ thống trao đổi ngoài phạm vi một ứng dụng Java đồng nhất.

### Ví dụ nhận trực tiếp với `JmsTemplate`

~~~java
Object value = jmsTemplate.receiveAndConvert("orders.paid");
if (value == null) {
    // Không có JMS message trong khoảng receiveTimeout đã cấu hình.
} else if (value instanceof String json) {
    // TextMessage -> String với SimpleMessageConverter.
    System.out.println(json);
} else {
    throw new IllegalArgumentException(
            "Unexpected JMS payload type: " + value.getClass().getName());
}
~~~

`receiveAndConvert(...)` gọi converter sau khi nhận JMS Message, còn `receive(...)` trả đối tượng `jakarta.jms.Message` để code tự xử lý. Nếu producer gửi `BytesMessage` thì không nên ép kết quả thành `String` mà chưa giải mã bytes theo contract.

## 4. Hợp đồng JSON xuyên suốt bài

Giả sử queue `orders.paid` dùng contract sau:

~~~json
{
  "eventId": "evt-901",
  "schemaVersion": 1,
  "eventType": "OrderPaid",
  "orderId": "ORD-901",
  "amountMinor": 320000,
  "currency": "VND"
}
~~~

Hợp đồng gồm:

- `eventId`: ID sự kiện **ổn định giữa các lần retry**, dùng ở inbox/idempotency store.
- `schemaVersion`: version hợp đồng để bên nhận phân biệt dạng payload.
- `eventType`: giúp handler/router xác định nghiệp vụ.
- `orderId`: khóa aggregate để xử lý ordering khi cần.
- `amountMinor`: số nguyên biểu diễn tiền theo đơn vị nhỏ đã thỏa thuận; tránh sai số khi dùng `double`.
- `currency`: mã tiền tệ hoặc giá trị theo quy tắc đã công bố.

Một DTO minh họa bằng Java 17+:

~~~java
public record OrderPaidEvent(
        String eventId,
        int schemaVersion,
        String eventType,
        String orderId,
        long amountMinor,
        String currency) {
}
~~~

`OrderPaidEvent` là **model nghiệp vụ**, không phải JMS API type. Đặt record trong package của ứng dụng và bảo đảm producer/consumer thống nhất contract. Record này có thể deserialize từ JSON qua Jackson mà không cần Java `Serializable`.

Có hai cách cấu hình converter chính. Trong cùng một ứng dụng, hãy chọn chiến lược phù hợp **cho từng destination**; không vô tình dùng hai converter với quy tắc payload khác nhau trên cùng queue.

## 5. Cách A: giữ JMS payload là JSON `String`

Chiến lược dễ tương tác nhất giữa nhiều công nghệ là:

1. Spring gửi **chuỗi JSON** cho `JmsTemplate.convertAndSend(...)` hoặc JMS outbound adapter.
2. Converter mặc định tạo `TextMessage`.
3. Inbound adapter nhận `TextMessage` và tạo Spring payload `String`.
4. Một **transformer/handler** dùng Jackson `ObjectMapper` để parse JSON thành DTO và validate schema.

~~~mermaid
flowchart LR
    A["OrderPaidEvent"] -->|"ObjectMapper.writeValueAsString"| B["String JSON"]
    B -->|"SimpleMessageConverter"| C["JMS TextMessage"]
    C -->|"SimpleMessageConverter"| D["String JSON"]
    D -->|"ObjectMapper.readValue"| E["OrderPaidEvent"]
~~~

### 5.1. Producer gửi JSON

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jms.core.JmsTemplate;

public class OrderPaidPublisher {
    private final JmsTemplate jmsTemplate;
    private final ObjectMapper objectMapper;

    public OrderPaidPublisher(JmsTemplate jmsTemplate, ObjectMapper objectMapper) {
        this.jmsTemplate = jmsTemplate;
        this.objectMapper = objectMapper;
    }

    public void publish(OrderPaidEvent event) {
        try {
            String json = objectMapper.writeValueAsString(event);
            jmsTemplate.convertAndSend("orders.paid", json, message -> {
                message.setStringProperty("eventType", event.eventType());
                message.setIntProperty("schemaVersion", event.schemaVersion());
                return message;
            });
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("Invalid OrderPaidEvent", ex);
        }
    }
}
~~~

Đoạn này là class dùng trong một ứng dụng đã có `JmsTemplate`, `ObjectMapper` và `ConnectionFactory` phù hợp broker. Bước `writeValueAsString` tạo JSON theo schema đã thống nhất; `convertAndSend` chuyển `String` thành JMS `TextMessage`. `MessagePostProcessor` thêm **JMS properties**; các properties này không thay thế dữ liệu trong JSON body.

### 5.2. Inbound flow nhận `String` và parse theo schema

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Bean
public IntegrationFlow orderPaidJsonInbound(
        ConnectionFactory connectionFactory,
        ObjectMapper objectMapper,
        OrderPaidService orderPaidService) {

    return IntegrationFlow
            .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                    .destination("orders.paid"))
            .<String, OrderPaidEvent>transform(json -> {
                try {
                    return objectMapper.readValue(json, OrderPaidEvent.class);
                } catch (JsonProcessingException ex) {
                    throw new IllegalArgumentException("Invalid OrderPaid JSON", ex);
                }
            })
            .handle(OrderPaidEvent.class, (event, headers) -> {
                orderPaidService.handle(event);
                return null;
            })
            .get();
}
~~~

`OrderPaidService` là service nghiệp vụ có method `void handle(OrderPaidEvent event)` do ứng dụng tự triển khai. Phương thức `@Bean` được đặt trong class `@Configuration` có `@EnableIntegration` hoặc cấu hình Spring Integration tương đương.

**Ưu điểm:** ít phụ thuộc vào JMS converter phía đối tác; JSON là hợp đồng dễ debug, có thể kiểm tra kiểu event và schema trước khi deserialize sâu. **Đánh đổi:** phải viết bước serialize/deserialize và quy tắc validation riêng trong flow; không để mỗi handler copy cùng logic parse.

## 6. Cách B: JMS Jackson converter chuyển trực tiếp JSON ↔ DTO

Khi **cả producer và consumer** thống nhất cách khai báo loại dữ liệu bằng một JMS property, Spring JMS hỗ trợ `MappingJackson2MessageConverter` để biến Java DTO thành JSON trong JMS body và chuyển ngược thành object.

### 6.1. Tạo converter

Ví dụ theo **Spring Framework 6.x / Spring Integration 6.x**:

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Bean("orderPaidJmsConverter")
public MappingJackson2MessageConverter orderPaidJmsConverter() {
    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();

    // Mặc định converter này thường tạo BytesMessage; chọn JSON TextMessage.
    converter.setTargetType(MessageType.TEXT);

    // JMS property dùng để xác định DTO khi nhận.
    converter.setTypeIdPropertyName("_type");
    converter.setTypeIdMappings(Map.of(
            "order-paid-v1", OrderPaidEvent.class));

    return converter;
}
~~~

Điểm quan trọng:

- `setTargetType(MessageType.TEXT)` yêu cầu converter phát **`TextMessage`** chứa JSON.
- `setTypeIdPropertyName("_type")` xác định một **JMS message property** được dùng để suy ra Java type khi nhận; tên này cần được producer/consumer thống nhất.
- `setTypeIdMappings(...)` ánh xạ một **alias ổn định** (`order-paid-v1`) sang class Java trong ứng dụng. Nếu không có mapping hợp lệ, một số cấu hình converter sẽ dựa vào tên class, tạo phụ thuộc không cần thiết vào package Java.
- Khi inbound converter nhận JMS `TextMessage`, nó đọc `_type` rồi chuyển body JSON thành `OrderPaidEvent`.

**Lưu ý phiên bản:** `MappingJackson2MessageConverter` là lựa chọn phổ biến trong Spring Framework 6.x. Spring Framework 7 đánh dấu API này deprecated để chuyển sang `JacksonJsonMessageConverter`, phù hợp Jackson thế hệ mới. Khi nâng Spring lên 7+, xem Javadoc của phiên bản được dùng và chuyển sang API thay thế tương ứng; không trộn ví dụ Jackson 2 với thư viện Jackson 3 một cách tự động.

### 6.2. Áp dụng cho `JmsTemplate`

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;

@Bean("orderPaidJmsTemplate")
public JmsTemplate orderPaidJmsTemplate(
        ConnectionFactory connectionFactory,
        MappingJackson2MessageConverter orderPaidJmsConverter) {

    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setMessageConverter(orderPaidJmsConverter);
    return template;
}
~~~

Nếu có nhiều bean kiểu `MappingJackson2MessageConverter`, inject bằng `@Qualifier("orderPaidJmsConverter")`. Khi gọi:

~~~java
// orderPaidJmsTemplate là bean ở ví dụ trên.
OrderPaidEvent event = new OrderPaidEvent(
        "evt-902", 1, "OrderPaid", "ORD-902", 410000, "VND");
orderPaidJmsTemplate.convertAndSend("orders.paid", event);
~~~

JMS message được gửi sẽ có JSON body và `_type=order-paid-v1` theo mapping cấu hình. Khi nhận bằng template **cùng hợp đồng**:

~~~java
Object value = orderPaidJmsTemplate.receiveAndConvert("orders.paid");
if (value instanceof OrderPaidEvent event) {
    System.out.println("Order ID = " + event.orderId());
}
~~~

Giá trị vẫn có thể là `null` khi không có message trong `receiveTimeout`. Hai đoạn gửi và nhận dành cho producer/consumer test; trong production thường là **hai ứng dụng khác nhau** để tránh một thành phần tự tiêu thụ sự kiện của chính mình ngoài chủ ý.

### 6.3. Java DSL: outbound adapter dùng Jackson JMS converter

Spring Integration cho phép cấu hình converter trên `JmsTemplate` do outbound adapter quản lý:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;

@Bean
public IntegrationFlow orderPaidOutbound(
        ConnectionFactory connectionFactory,
        MappingJackson2MessageConverter orderPaidJmsConverter) {

    return IntegrationFlow.from("orderPaidOutput")
            .handle(Jms.outboundAdapter(connectionFactory)
                    .destination("orders.paid")
                    .configureJmsTemplate(template ->
                            template.jmsMessageConverter(orderPaidJmsConverter)))
            .get();
}
~~~

Ở flow này, upstream gửi Spring Message chứa `OrderPaidEvent` tới channel `orderPaidOutput`; outbound adapter trích payload và dùng JSON converter. Không cần tự serialize trước thành `String` nếu converter đã nhận DTO đúng kiểu.

**Tránh double conversion:** nếu upstream đã serialize DTO thành chuỗi JSON, nhưng adapter lại dùng Jackson converter hướng tới DTO, converter có thể serialize **chính chuỗi đó** thành JSON string có dấu ngoặc kép/escape (không còn là JSON object). Chọn **một** ranh giới serialize nhất quán.

### 6.4. Java DSL: message-driven inbound dùng cùng converter

~~~java
@Bean
public IntegrationFlow orderPaidTypedInbound(
        ConnectionFactory connectionFactory,
        MappingJackson2MessageConverter orderPaidJmsConverter,
        OrderPaidService orderPaidService) {

    return IntegrationFlow
            .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                    .destination("orders.paid")
                    .jmsMessageConverter(orderPaidJmsConverter))
            .handle(OrderPaidEvent.class, (event, headers) -> {
                orderPaidService.handle(event);
                return null;
            })
            .get();
}
~~~

Ở đây inbound endpoint giải mã JSON `TextMessage` thành `OrderPaidEvent` trước khi tạo Spring Message. Nếu thiếu JMS property `_type` hoặc alias không được chấp nhận, conversion có thể thất bại **trước khi handler được gọi**.

**Hai inbound example ở mục 5 và mục 6 là hai phương án thay thế**, không nên triển khai đồng thời để cạnh tranh trên cùng queue khi mục đích chỉ có một consumer logic. Producer và consumer phải thống nhất dùng cách A hoặc B (hoặc converter tùy chỉnh tương thích).

## 7. Áp dụng converter cho các loại JMS endpoint

| Endpoint | Vai trò converter | Cấu hình cần chú ý |
|---|---|---|
| `JmsTemplate` trực tiếp | `convertAndSend` và `receiveAndConvert` | `setMessageConverter(...)` |
| JMS polling inbound channel adapter | JMS message nhận bởi `JmsTemplate` → Spring payload | Converter trên template được adapter dùng; `extractPayload` |
| JMS message-driven inbound channel adapter | Listener callback → Spring payload | `jmsMessageConverter(...)` trên DSL spec hoặc `message-converter` trong XML |
| JMS outbound channel adapter | Spring payload → JMS message | Converter trong `JmsTemplate`; `extractPayload` |
| JMS inbound gateway | JMS request → Spring request và Spring reply → JMS reply | Converter và cờ `extractRequestPayload`/`extractReplyPayload` |
| JMS outbound gateway | Spring request → JMS request và JMS reply → Spring reply | Converter phải hiểu **cả hai chiều** |

### Inbound polling Java DSL

~~~java
IntegrationFlow.from(
        Jms.inboundAdapter(connectionFactory)
                .destination("orders.paid")
                .configureJmsTemplate(template ->
                        template.jmsMessageConverter(orderPaidJmsConverter)
                                .receiveTimeout(-1)),
        endpoint -> endpoint.poller(poller ->
                poller.fixedDelay(5000)
                        .maxMessagesPerPoll(10)))
        .handle(OrderPaidEvent.class, (event, headers) -> {
            orderPaidService.handle(event);
            return null;
        })
        .get();
~~~

Đây là **fragment** trong một method tạo `IntegrationFlow` đã có `connectionFactory`, `orderPaidJmsConverter` và `orderPaidService`. Poller quyết định thời điểm lấy message; `receiveTimeout(-1)` nghĩa là một lần JMS receive không chờ khi queue rỗng. Chỉ chọn **một** inbound flow cho queue `orders.paid` trong bài thực hành để tránh competing consumers ngoài ý muốn.

### Cấu hình XML

Spring Integration JMS XML namespace hỗ trợ `message-converter` cho các JMS adapter/gateway:

~~~xml
<int:channel id="orderPaidInput"/>

<int-jms:message-driven-channel-adapter
        id="orderPaidInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.paid"
        channel="orderPaidInput"
        message-converter="orderPaidJmsConverter"/>

<int-jms:outbound-channel-adapter
        id="orderPaidOutbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.paid.outbound"
        channel="orderPaidOutput"
        message-converter="orderPaidJmsConverter"/>
~~~

Đây là XML **minh họa**: cần khai báo namespaces `int`/`int-jms`, bean converter `orderPaidJmsConverter`, bean `jmsConnectionFactory`, các channel và consumer. Hai destination khác nhau được dùng để tránh demo tự lặp lại message. Không thêm các fragment XML vào ứng dụng vốn đã khai báo Java DSL tương đương, trừ khi cần nhiều endpoint theo thiết kế.

## 8. `extractPayload` và chuyển đổi toàn Spring Message

Các JMS adapter/gateway có cấu hình **chọn phần nào của Spring Message được đưa tới converter**:

| Cờ | Đường xử lý | `true` thường mặc định | Khi `false` |
|---|---|---|---|
| `extractPayload` của inbound adapter | JMS → Spring | Chuyển JMS body thành Spring payload | Có thể giữ JMS Message nguyên bản làm payload tùy endpoint |
| `extractPayload` của outbound adapter | Spring → JMS | Chuyển Spring payload thành JMS body | Converter nhận **toàn Spring Message** làm đối tượng cần chuyển |
| `extractRequestPayload` của gateway | Chiều request | Chỉ chuyển nội dung nghiệp vụ | Có thể đưa Spring Message/JMS Message nguyên bản tùy chiều và endpoint |
| `extractReplyPayload` của gateway | Chiều reply | Chỉ chuyển nội dung nghiệp vụ | Có thể chuyển cả Message thay vì chỉ payload |

**Đừng bật `extractPayload(false)` chỉ để giữ headers.** Spring Integration vẫn hỗ trợ header mapping khi trích payload, và dữ liệu nằm trong Spring headers có thể được ánh xạ qua `JmsHeaderMapper` theo quy tắc. Việc chuyển toàn Spring Message làm JMS body phù hợp chủ yếu khi cả hai đầu hiểu kiểu nội bộ của Spring; đó là coupling không cần thiết với hệ thống bên ngoài.

Khi viết custom converter, cần kiểm tra loại object converter thực sự nhận: `String`, DTO hay `Message<?>`. Nếu converter chỉ hỗ trợ `OrderPaidEvent` nhưng outbound endpoint được cấu hình truyền **toàn Spring Message**, phép chuyển có thể lỗi vì kiểu đầu vào không khớp.

## 9. Header mapping, type ID và schema version

Ví dụ JMS message mang:

~~~text
JMS body:      {"eventId":"evt-902","schemaVersion":1,...}
JMS property:  _type = "order-paid-v1"
JMS property:  eventType = "OrderPaid"
JMS header:    JMSMessageID = <provider-generated>
JMS header:    JMSCorrelationID = <if set by contract>
~~~

Các loại metadata có vai trò khác nhau:

| Metadata | Ý nghĩa | Nên đặt ở đâu? |
|---|---|---|
| `_type` | Alias mà Jackson JMS converter dùng để chọn Java class | JMS property được đặt tên rõ |
| `schemaVersion` | Version hợp đồng dữ liệu | Payload, có thể lặp ở JMS property nếu cần selector |
| `eventType` | Loại sự kiện nghiệp vụ | Payload và/hoặc JMS property |
| `eventId` | Idempotency key ổn định | Payload là nguồn sự thật |
| `JMSMessageID` | ID của lần gửi do provider cấp | JMS header, phục vụ truy vết |
| `JMSCorrelationID` | Liên kết request-reply theo JMS | JMS header, cần contract riêng |

`DefaultJmsHeaderMapper` ánh xạ một số JMS headers và properties dạng scalar (`String`, primitive, wrapper phù hợp). Nó **không** thể lưu tùy ý mọi object trong Spring headers thành JMS properties. Một số header nội bộ của Spring (`id`, `timestamp`, `replyChannel` hoặc các object phức tạp) không thể được xem là contract cho bên ngoài nếu chưa được ánh xạ chủ động.

### Type ID khác schema version

`_type=order-paid-v1` giúp converter biết Java class cần deserialize. `schemaVersion=1` xác định cấu trúc hợp đồng nghiệp vụ. Chúng **có thể** đi cùng nhau, nhưng không tự động tương đương:

- Một Java DTO có thể hỗ trợ nhiều schema version nếu ứng dụng có logic tương thích.
- Một schema version có thể được nhiều ngôn ngữ triển khai bằng các class khác tên.
- Nếu producer nâng schema mà consumer chưa hỗ trợ, chỉ giữ tên class/alias không đổi có thể khiến deserialize thành công nhưng **ngữ nghĩa sai**.

Vì vậy, sau conversion hãy kiểm tra `schemaVersion`, các trường bắt buộc, giá trị cho phép và quan hệ nghiệp vụ. Converter chỉ tạo object; nó không xác nhận toàn bộ dữ liệu hợp lệ về mặt nghiệp vụ.

### Kiểm soát loại object được deserialize

Không lấy tên class từ JMS property do nguồn không tin cậy gửi tới rồi cho phép tự động load bất kỳ class nào. Với Jackson JMS converter, nên dùng **alias allowlist** và hạn chế class được hỗ trợ (như mapping một alias tới `OrderPaidEvent.class`). Nếu nhận `ObjectMessage`, còn phải kiểm tra chính sách trusted packages của JMS provider/Jackson và hạn chế Java deserialization.

Một message thiếu `_type`, mang alias lạ hoặc có JSON không khớp type phải được **coi là lỗi contract**, không nên mặc định tự đoán class nào “gần đúng” rồi xử lý tiếp.

## 10. Conversion error, transaction và redelivery

Lỗi conversion có thể xuất hiện ở nhiều thời điểm:

| Tình huống | Ví dụ | Thường xảy ra ở đâu? | Hành động phù hợp |
|---|---|---|---|
| Java object không chuyển được | DTO không hỗ trợ trong `SimpleMessageConverter` | Trước khi gửi JMS | Sửa converter/schema, không retry mù quáng |
| JSON serialize thất bại | Object chứa giá trị không thể serialize | Producer/converter outbound | Ghi lỗi có context, quarantine dữ liệu sai |
| Thiếu `_type` | JSON đúng nhưng metadata loại không có | Inbound Jackson converter | Từ chối hoặc dùng contract fallback được định nghĩa rõ |
| Alias không được hỗ trợ | `_type=unknown-event-v99` | Inbound converter | Phân loại lỗi version/contract |
| JSON sai cú pháp | `{"eventId":` | Inbound converter hoặc transformer | Không để poison message lặp vô hạn |
| JSON đúng nhưng business invalid | `amountMinor=-1` | Validator/handler | Trả lỗi nghiệp vụ hoặc quarantine |
| Header/property không hợp lệ | Value là object mà JMS property không hỗ trợ | Header mapper/JMS provider | Dùng scalar/serialize rõ ràng |

### 10.1. Lỗi xuất hiện trước khi handler chạy

Ví dụ consumer dùng Jackson converter, nhưng producer gửi JMS `TextMessage` thiếu `_type`. Converter có thể ném `MessageConversionException` **trước khi một Spring Message hợp lệ đến `MessageChannel`**. Handler ở cuối flow chưa bao giờ nhìn thấy event để validate; vì thế chỉ viết `try/catch` trong handler **không đủ** để quan sát mọi lỗi của endpoint.

Với JMS message-driven inbound adapter/gateway, Spring Integration có thể đưa lỗi conversion thành `ErrorMessage` tới `errorChannel`. Từ Spring Integration 4.2, lỗi conversion cũng được đưa qua đường này nếu error channel được cấu hình.

### 10.2. `errorChannel` không tự tạo rollback

~~~mermaid
flowchart TD
    A["JMS listener nhận message"] --> B["MessageConverter chuyển body"]
    B --> C{"Conversion OK?"}
    C -->|"Có"| D["Spring Message -> handler"]
    C -->|"Không"| E["Exception / ErrorMessage"]
    E --> F{"Error flow ném lỗi ra ngoài?"}
    F -->|"Có, JMS session transacted"| G["Rollback -> broker redelivery"]
    F -->|"Không, error đã xử lý"| H["Listener có thể commit JMS"]
    G --> I["Retry có giới hạn / DLQ theo broker policy"]
~~~

Nếu `errorChannel` **nuốt exception** rồi kết thúc bình thường, listener container có thể coi callback thành công và **commit JMS transaction**, làm message biến mất khỏi queue dù conversion thất bại. Nếu muốn broker redeliver, exception phải lan ra transaction boundary trong đường xử lý **đồng bộ** và listener phải được cấu hình transacted.

Mặt khác, **message sai schema vĩnh viễn** không trở nên hợp lệ sau 100 lần retry. Hãy cấu hình retry có giới hạn, backoff, dead-letter queue/quarantine và quy trình sửa dữ liệu; không để một poison message gây bão lỗi.

### 10.3. Converter và transaction không cùng trách nhiệm

`MessageConverter` không quản lý commit/rollback JMS, DB hay delivery guarantees. `JmsTransactionManager` và listener container điều phối JMS transaction; transaction DB được quản lý riêng. Giả sử handler đã commit DB nhưng JMS session rollback vì lỗi mạng, cùng message có thể redeliver. Vì vậy cần idempotency theo `eventId` cùng một unique constraint/inbox table trong transaction DB.

Khi chuyển từ `DirectChannel` sang `ExecutorChannel`, exception của handler ở thread khác có thể xảy ra **sau** khi listener đã commit JMS, bất kể converter trước đó thành công. Hãy xác định ranh giới thread/transaction cho toàn flow, đặc biệt khi trộn Spring Integration với JDBC, HTTP hoặc Kafka.

## 11. Custom MessageConverter khi JSON không đủ

Có những trường hợp dữ liệu bên ngoài phải dùng binary frame, legacy record hoặc một định dạng có schema riêng. Khi đó có thể tự triển khai Spring JMS `MessageConverter`:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Session;
import org.springframework.jms.support.converter.MessageConversionException;
import org.springframework.jms.support.converter.MessageConverter;

public final class OrderCodeConverter implements MessageConverter {

    @Override
    public Message toMessage(Object object, Session session)
            throws JMSException, MessageConversionException {

        if (!(object instanceof String orderCode)) {
            throw new MessageConversionException("Expected String order code");
        }
        if (orderCode.isBlank() || orderCode.length() > 64) {
            throw new MessageConversionException("Invalid order code");
        }
        return session.createTextMessage(orderCode);
    }

    @Override
    public Object fromMessage(Message message)
            throws JMSException, MessageConversionException {

        if (!(message instanceof jakarta.jms.TextMessage textMessage)) {
            throw new MessageConversionException("Expected TextMessage");
        }
        String orderCode = textMessage.getText();
        if (orderCode == null || orderCode.isBlank() || orderCode.length() > 64) {
            throw new MessageConversionException("Invalid order code");
        }
        return orderCode;
    }
}
~~~

Ví dụ này cố ý chỉ nhận một kiểu body đơn giản; không phải converter JSON. Một custom converter production nên có:

- Quy định rõ **kiểu dữ liệu Java vào/ra**, body format, encoding, schema và giới hạn độ dài.
- Kiểm tra `null`, dữ liệu bị cắt, bytes không hợp lệ, version ngoài hỗ trợ và message type sai.
- Chuyển lỗi thành `MessageConversionException` có thông tin kỹ thuật đủ theo dõi nhưng **không ghi dữ liệu nhạy cảm vào exception/log**.
- Không giữ JMS `Session`/`Message` lâu ngoài callback hoặc chia sẻ những đối tượng không an toàn giữa threads.
- Kiểm thử tương thích với producer/consumer thực qua broker, vì header mapping và JMS provider có thể ảnh hưởng kết quả.

`MarshallingMessageConverter` cũng là lựa chọn trong Spring JMS khi ứng dụng đã có `Marshaller`/`Unmarshaller` cho XML hoặc định dạng được hỗ trợ. Cần cấu hình đúng cách chuyển byte/text và thỏa thuận schema với hệ thống bên ngoài.

## 12. Hiệu năng, versioning và khả năng tương thích

### 12.1. Chọn giữa `TextMessage` và `BytesMessage`

| Tiêu chí | JSON `TextMessage` | Binary `BytesMessage` |
|---|---|---|
| Quan sát/debug | Dễ đọc trong công cụ broker | Cần công cụ giải mã đúng format |
| Kích thước | Có thể lớn với nhiều field và tên dài | Một số format nhị phân tiết kiệm hơn |
| Tương thích | Phổ biến giữa nhiều ngôn ngữ | Phải thống nhất schema/encoding/version |
| Kiểm tra schema | JSON Schema/validator hoặc mapping DTO | Validator/schema registry phù hợp |
| Rủi ro thường gặp | Unknown field, type mismatch, escaping/encoding | Sai framing/charset/codec/version |

Chọn format dựa trên **hợp đồng và hạ tầng thực tế**, không chỉ benchmark serialize trong JVM. Message quá lớn ảnh hưởng memory, broker quota, network, latency và retry. Dù dùng JSON hay binary, vẫn đặt giới hạn kích thước và theo dõi lỗi chuyển đổi.

### 12.2. Chiến lược thay đổi schema

Khi thêm `discountMinor` vào `OrderPaidEvent`:

1. Xác định field mới có optional/default hợp lệ hay không.
2. Nâng `schemaVersion` nếu hợp đồng thay đổi theo quy tắc versioning.
3. Xác nhận consumer phiên bản cũ xử lý unknown fields ra sao; mặc định một số Jackson converter có thể bỏ qua field lạ, nhưng **không xem đó là bằng chứng nghiệp vụ tương thích**.
4. Nếu đổi ý nghĩa của field hoặc xóa field bắt buộc, cân nhắc version mới của event type/destination và migration.
5. Viết integration test giữa producer/consumer các version cần hỗ trợ, bao gồm failure path.

`_type` giúp chọn Java type tại receiver, nhưng một alias không thể thay việc quản lý hợp đồng schema. Với hệ thống nhiều ngôn ngữ, giữ type alias là tên nghiệp vụ thay vì Java package/class name sẽ giảm coupling.

### 12.3. Thread safety và lifecycle

`JmsTemplate` và converter cấu hình sẵn thường được dùng lại như bean singleton. Không thay đổi converter, type mappings hoặc `ObjectMapper` của bean đang phục vụ nhiều listener threads trong lúc runtime. Cấu hình trước khi ứng dụng nhận message; nếu cần nhiều contract, dùng converter/adapter được cấu hình riêng.

Khi JMS broker disconnect, `ConnectionFactory`/listener container chịu trách nhiệm khôi phục kết nối theo cấu hình. Converter **không** tự retry kết nối, tự bảo đảm QoS hoặc quyết định khi nào message được acknowledge. Trong production, theo dõi **queue backlog, age, lỗi conversion theo schemaVersion, redelivery, DLQ, số consumer và thời gian xử lý handler**.

## 13. Thực hành: kiểm chứng hai chiến lược conversion

**Môi trường:** JMS broker thử nghiệm có queue `orders.paid`, Java 17+, Spring Integration/JMS, Jackson và service `OrderPaidService`. Mỗi lượt thử chỉ chạy **một** inbound flow phù hợp contract; dùng producer test để gửi JMS message với body/headers rõ ràng.

### Phần A — SimpleMessageConverter + Jackson transformer

1. Gửi một `String` JSON chứa `evt-901` bằng `JmsTemplate.convertAndSend`.
2. Dùng consumer nhận `TextMessage` và kiểm tra body đúng JSON, property `eventType` có giá trị mong đợi.
3. Chạy flow ở mục 5, kiểm tra transformer tạo `OrderPaidEvent` đúng và handler gọi một lần khi không có lỗi.
4. Gửi JSON sai cú pháp, thử thiếu `orderId` và `amountMinor` âm; phân biệt lỗi parser, lỗi validation và lỗi nghiệp vụ.
5. Kiểm tra handler nhận đúng header được ánh xạ, nhưng không giả định mọi Spring header nội bộ đều có mặt.

### Phần B — MappingJackson2MessageConverter

1. Cấu hình `MappingJackson2MessageConverter` với `MessageType.TEXT`, `_type` và alias `order-paid-v1`.
2. Gửi trực tiếp `OrderPaidEvent` qua converter; kiểm tra body JMS là JSON object chứ không phải JSON string đã bị serialize hai lần.
3. Chạy inbound flow ở mục 6, xác nhận handler nhận `OrderPaidEvent` thay vì `String`.
4. Gửi `TextMessage` đúng JSON nhưng **thiếu `_type`**; quan sát lỗi trước handler và chiến lược error channel.
5. Gửi `_type=unknown-alias`, trường sai kiểu và schemaVersion không hỗ trợ. Đối chiếu các lỗi conversion và validation.
6. Gửi lại một `eventId` sau khi consumer gặp lỗi; xác nhận DB unique constraint/idempotency không tạo tác động lặp.

### Phần C — Xử lý lỗi và vận hành

1. Với listener transacted, cố ý tạo lỗi converter; quan sát broker redelivery khi exception được ném ra.
2. Cấu hình error channel xử lý exception mà không ném lại; quan sát sự khác biệt về commit (chỉ trên môi trường test).
3. Thiết lập retry giới hạn và DLQ/quarantine cho poison message; xác nhận consumer tiếp tục xử lý message hợp lệ.
4. Ngắt broker, khởi động lại, quan sát recovery của listener và xác nhận converter không bị tạo lại theo mỗi message ngoài ý muốn.
5. Đo tốc độ xử lý với 100–1.000 message: so sánh parse JSON trong transformer và JMS Jackson converter, bao gồm CPU, latency, kích thước message và GC; kết luận từ số đo thực tế thay vì giả định cách nào luôn nhanh hơn.

### Câu hỏi tự đánh giá

1. `SimpleMessageConverter` nhận Java `String` sẽ thường tạo kiểu JMS message nào?
2. Tại sao gửi DTO Java trực tiếp có thể không tạo ra JSON như người dùng mong đợi?
3. `MessageConverter` và `JmsHeaderMapper` có khác nhau về trách nhiệm không? Cho ví dụ.
4. Vai trò của `setTypeIdPropertyName("_type")` và `setTypeIdMappings(...)` là gì?
5. Vì sao `_type` nên là alias allowlist thay vì tên class tùy ý từ producer?
6. Vì sao dùng cả `ObjectMapper.writeValueAsString` ở upstream lẫn Jackson JMS converter ở outbound có thể làm sai body?
7. Conversion error xuất hiện trước handler thì cần quan sát ở đâu?
8. Vì sao error flow nuốt exception có thể khiến broker commit message lỗi?
9. `extractPayload(false)` có cần thiết để giữ Spring/JMS headers hay không?
10. Với hệ thống gồm Java, .NET và Node.js, bạn chọn contract nào và cần kiểm tra gì để versioning an toàn?

## 14. Tài liệu tham khảo

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): converter trong JMS adapter/gateway, header mapping, `extractPayload` và conversion error.
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html): `JmsTemplate`, `MessageConverter`, gửi/nhận JMS.
- [Spring Framework API — SimpleMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html): mapping mặc định giữa Java object và JMS message.
- [Spring Framework API — MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html): `targetType`, `typeIdPropertyName`, type ID mappings; lưu ý deprecated từ Spring Framework 7.
- [Spring Integration API — JmsMessageDrivenChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsMessageDrivenChannelAdapterSpec.html): `jmsMessageConverter`, `headerMapper`, `extractPayload`.
- [Spring Integration API — JmsTemplateSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsTemplateSpec.html): `jmsMessageConverter` trên JMS DSL template.

**Ghi nhớ:** JMS converter chuyển **body** giữa Java object và JMS Message; header mapper chuyển **metadata** giữa JMS và Spring Integration. Để giao tiếp ổn định với hệ thống ngoài, phải chọn rõ chiến lược JSON `String` hoặc Jackson DTO, thống nhất type alias và schema version, kiểm tra dữ liệu sau conversion, và thiết kế error channel, rollback/redelivery cùng idempotency cho trường hợp message lỗi hoặc bị gửi lại.
