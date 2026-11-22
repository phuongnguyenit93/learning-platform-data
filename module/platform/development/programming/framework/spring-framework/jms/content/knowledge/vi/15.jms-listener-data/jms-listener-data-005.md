# JmsHeaders và ánh xạ metadata JMS

> **Ngữ cảnh:** Dữ liệu listener trong Spring Framework JMS. Khi `@JmsListener` nhận một message, phương thức xử lý không chỉ lấy **payload** mà còn có thể truy cập **JMS standard headers** và **application properties**. `org.springframework.jms.support.JmsHeaders` định nghĩa các tên header thống nhất ở tầng `org.springframework.messaging.MessageHeaders`; `SimpleJmsHeaderMapper` giúp chuyển đổi metadata giữa `jakarta.jms.Message` và Spring Message. Hiểu hai lớp này giúp dùng đúng correlation ID, message ID, priority, type, redelivery và các thuộc tính nghiệp vụ mà không nhầm lẫn với JSON body.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **JMS API header**, **JMS application property**, **Spring Messaging header** và **payload**.
2. Gọi đúng các constant `JmsHeaders.CORRELATION_ID`, `MESSAGE_ID`, `PRIORITY`, `TYPE`, `REDELIVERED`, `TIMESTAMP`, `DESTINATION`, `REPLY_TO`, `DELIVERY_MODE` và `EXPIRATION` mà không hard-code sai tên.
3. Dùng `@Header` và `@Headers` trong một `@JmsListener` để lấy metadata riêng lẻ hoặc toàn bộ metadata được ánh xạ.
4. Dùng `JmsMessageHeaderAccessor` hoặc `org.springframework.messaging.Message<T>` để đọc metadata theo cách ít phụ thuộc JMS provider; so sánh với đọc trực tiếp `jakarta.jms.Message`.
5. Hiểu chiều ánh xạ **inbound** (JMS → Spring) và **outbound** (Spring → JMS), cũng như các standard headers chỉ được đọc và các QoS header do JMS producer/provider quyết định.
6. Tạo một ví dụ Java 17/Spring Boot 3.3.5/Artemis chạy được, gửi String `TextMessage` có correlation ID + properties rồi xác minh metadata tại annotated listener.
7. Phân biệt `JmsHeaders` của Spring Framework với `DefaultJmsHeaderMapper` của **Spring Integration**, tránh lấy mặc định của component này áp đặt cho component khác.
8. Kiểm thử trường hợp metadata thiếu, sai kiểu, header bị provider ghi đè, multiple consumers, redelivery và rủi ro đưa secrets vào message headers.

**Nguyên tắc:** Metadata giúp **phân loại, liên kết, định tuyến, quan sát và trả lời message**. Metadata không tự động chứng minh message đã xử lý đúng một lần, không thay thế transaction/acknowledgement, và một header có tên gần giống cũng không nhất thiết cùng ý nghĩa giữa các abstraction.

## 2. Bốn lớp dữ liệu cần phân biệt

Cùng một sự kiện `order.created` có thể được biểu diễn:

~~~text
                         jakarta.jms.TextMessage
                      +----------------------------+
                      | BODY:                      |
                      |   {"orderId":"O-42"}       |
                      |                            |
                      | JMS STANDARD HEADERS:      |
                      |   JMSMessageID              |
                      |   JMSCorrelationID          |
                      |   JMSPriority               |
                      |   JMSType                   |
                      |   JMSRedelivered            |
                      |   JMSTimestamp ...          |
                      |                            |
                      | JMS APPLICATION PROPERTIES: |
                      |   eventType                 |
                      |   schemaVersion             |
                      |   tenantCode                |
                      +----------------------------+
                                      |
                                      | Spring JMS listener adapter
                                      | + SimpleJmsHeaderMapper
                                      v
                  org.springframework.messaging.Message<String>
                      +------------------------------------+
                      | payload: JSON String               |
                      | headers["jms_messageId"]           |
                      | headers["jms_correlationId"]       |
                      | headers["jms_priority"]            |
                      | headers["jms_type"]                |
                      | headers["eventType"]               |
                      | headers["schemaVersion"]           |
                      | headers["tenantCode"]              |
                      +------------------------------------+
                                      |
                      +---------------+---------------+
                      |                               |
                @Header("eventType")             @Headers Map
                @Header(JmsHeaders.TYPE)         hoặc MessageHeaders
~~~

| Khái niệm | Thuộc về | Cách đọc điển hình | Ví dụ |
| --- | --- | --- | --- |
| JMS standard header | `jakarta.jms.Message` | `getJMSCorrelationID()`, `getJMSMessageID()`, `getJMSPriority()` | `JMSCorrelationID` |
| JMS application property | `jakarta.jms.Message` | `getStringProperty("eventType")`, `getIntProperty("schemaVersion")` | `eventType` |
| Spring Messaging header | `org.springframework.messaging.MessageHeaders` | `get(JmsHeaders.CORRELATION_ID)`, `@Header(...)` | `jms_correlationId` |
| Payload/body | JMS `TextMessage`/`BytesMessage` hoặc Spring `Message<T>` | `getText()` hoặc `getPayload()` | JSON order body |
| Spring envelope ID/time | `MessageHeaders.ID`/`TIMESTAMP` | `headers.getId()` / `headers.getTimestamp()` | ID/thời điểm Spring Message |

**Quan trọng:** `MessageHeaders.ID` của Spring Messaging không đồng nghĩa `JMSMessageID` của broker. `MessageHeaders.TIMESTAMP` không mặc nhiên bằng `JMSTimestamp`. Muốn đọc JMS message ID/timestamp, dùng `JmsHeaders.MESSAGE_ID`/`JmsHeaders.TIMESTAMP`.

## 3. `JmsHeaders` là gì?

`org.springframework.jms.support.JmsHeaders` là interface chứa các `static final String` constant cho tên metadata JMS bên trong **Spring Messaging headers**. Interface này **không phải** JMS provider, không chứa trạng thái của một message, không phải lớp cần `new` và không tự thêm metadata nếu producer chưa đặt.

### 3.1. Bảng constants quan trọng

Các giá trị chuỗi dưới đây tương ứng Spring Framework 6.x/7.x:

| Constant Spring | Giá trị chuỗi | JMS API gốc | Ý nghĩa / kiểu khi đọc |
| --- | --- | --- | --- |
| `JmsHeaders.PREFIX` | `"jms_"` | Không có getter tương ứng | Prefix phân biệt JMS API headers với custom properties |
| `CORRELATION_ID` | `"jms_correlationId"` | `getJMSCorrelationID()` | `String` — liên kết message/request–reply |
| `MESSAGE_ID` | `"jms_messageId"` | `getJMSMessageID()` | `String` — ID do provider cấp khi gửi |
| `DESTINATION` | `"jms_destination"` | `getJMSDestination()` | `jakarta.jms.Destination` — đích thực tế |
| `REPLY_TO` | `"jms_replyTo"` | `getJMSReplyTo()` | `jakarta.jms.Destination` — đích mong nhận phản hồi |
| `DELIVERY_MODE` | `"jms_deliveryMode"` | `getJMSDeliveryMode()` | `Integer` — `DeliveryMode.PERSISTENT` hoặc `NON_PERSISTENT` |
| `EXPIRATION` | `"jms_expiration"` | `getJMSExpiration()` | `Long` — hạn hết hiệu lực epoch millis; `0` nghĩa là không hết hạn vì TTL |
| `PRIORITY` | `"jms_priority"` | `getJMSPriority()` | `Integer` — 0..9 |
| `REDELIVERED` | `"jms_redelivered"` | `getJMSRedelivered()` | `Boolean` — flag giao lại |
| `TYPE` | `"jms_type"` | `getJMSType()` | `String` — nhãn phân loại do producer/application đặt |
| `TIMESTAMP` | `"jms_timestamp"` | `getJMSTimestamp()` | `Long` — thời điểm gửi do JMS provider xác lập |

**Cách import chuẩn:**

~~~java
import org.springframework.jms.support.JmsHeaders;
~~~

Dùng `@Header(JmsHeaders.CORRELATION_ID)` thay vì lặp literal `"jms_correlationId"` khắp code. Giá trị từ JMS 1/2 cũ đôi khi xuất hiện dạng header `JMSCorrelationID`; trong **Spring Messaging headers**, tên key thường là **`jms_correlationId`**. Đó là hai biểu diễn khác lớp, không phải hai correlation ID độc lập.

### 3.2. Không phải mọi tên giống JMS đều là `JmsHeaders`

`JMSXDeliveryCount` là JMS-defined property rất hữu ích khi redelivery nhưng không có constant `JmsHeaders.DELIVERY_COUNT` trong danh sách trên. Đọc qua:

~~~java
// Snippet khi đã có raw jakarta.jms.Message:
int deliveryCount = raw.getIntProperty("JMSXDeliveryCount");
~~~

Theo provider/JMS spec, availability và semantics có điều kiện; có thể kiểm tra `raw.propertyExists("JMSXDeliveryCount")` trước khi đọc trong code tương thích nhiều provider. Ngoài ra, broker có thể thêm properties `JMS_*`/vendor-specific. **Không đặt các prefix chuẩn hoặc tên provider-reserved tùy tiện** làm tên custom property.

## 4. Cơ chế ánh xạ: JMS native → Spring Message

Một Spring `@JmsListener` có thể nhận:

~~~java
// Snippet: @Component chứa method này, đã bật hạ tầng JMS listener.
@JmsListener(destination = "orders.events")
public void onEvent(org.springframework.messaging.Message<String> event) {
    String body = event.getPayload();
    String correlationId = (String) event.getHeaders()
            .get(JmsHeaders.CORRELATION_ID);
}
~~~

Tại ranh giới adapter, Spring JMS chuyển native JMS message sang Spring Messaging message (payload + headers). `SimpleJmsHeaderMapper` là mapper cơ bản của Spring Framework dùng để chuyển JMS API headers và custom properties vào `MessageHeaders`. Vì vậy handler không phải trực tiếp gọi tất cả JMS getters để lấy những header đã được ánh xạ.

### 4.1. Chiều inbound

~~~text
jakarta.jms.Message                         Spring MessageHeaders
--------------------------------------------------------------------
getJMSCorrelationID()                -->    jms_correlationId
getJMSMessageID()                    -->    jms_messageId
getJMSPriority()                     -->    jms_priority
getJMSType()                         -->    jms_type
getJMSRedelivered()                  -->    jms_redelivered
getJMSDestination()                  -->    jms_destination
getJMSReplyTo()                      -->    jms_replyTo
getStringProperty("eventType")       -->    eventType
getIntProperty("schemaVersion")      -->    schemaVersion
...                                  -->    ...
~~~

Một mapping có thể bỏ qua metadata khi không có giá trị, không thể chuyển type hoặc bị chính sách mapper tùy chỉnh loại bỏ. Vì vậy, trong API business có header optional, dùng `@Header(name = "...", required = false)` với wrapper/reference type hoặc đọc raw `Message` và kiểm tra null, thay vì buộc mọi message đều có đủ header.

### 4.2. Chiều outbound

Nếu một integration dùng Spring Messaging `Message<T>` gửi ra JMS qua abstraction có header mapping, những headers được hỗ trợ sẽ được đưa sang JMS native:
- `JmsHeaders.CORRELATION_ID` → `setJMSCorrelationID(...)`;
- `JmsHeaders.REPLY_TO` → `setJMSReplyTo(...)` với một `Destination` hợp lệ;
- `JmsHeaders.TYPE` → `setJMSType(...)`;
- các header ứng dụng hợp lệ như `eventType` và `schemaVersion` → JMS properties.

**Nhưng** headers provider-managed chỉ được phản ánh khi đọc, không nên “copy ngược” từ Spring Message rồi hy vọng giữ nguyên. Những trường như `JMSMessageID`, `JMSDestination`, `JMSTimestamp`, `JMSExpiration`, `JMSPriority` và `JMSDeliveryMode` chịu quy tắc JMS producer/provider.

### 4.3. Phân biệt Spring Framework và Spring Integration

Trong Spring Framework JMS:
- `org.springframework.jms.support.JmsHeaderMapper` — giao diện mapping JMS ↔ Spring.
- `org.springframework.jms.support.SimpleJmsHeaderMapper` — triển khai mapper cơ bản.
- `org.springframework.jms.support.JmsHeaders` — danh sách constant chung.

Trong **Spring Integration JMS** (module khác):
- `org.springframework.integration.jms.DefaultJmsHeaderMapper` — lớp mapper dành cho gateways/adapters của Spring Integration.
- Mapper này có các tùy chọn riêng như `setMapInboundDeliveryMode(true)`, `setMapInboundExpiration(true)` và chính sách map priority.

Đừng áp dụng mặc định của `DefaultJmsHeaderMapper` trong Spring Integration lên mọi `@JmsListener` của Spring Framework. Muốn chỉnh mapping Spring Integration, cần cấu hình **integration inbound/outbound endpoint** phù hợp; một bean mapper không tự động thay đổi adapter của mọi listener thường.

Ví dụ cấu hình Spring Integration (snippet, chỉ dùng khi có dependency Spring Integration JMS):

~~~java
@Bean
DefaultJmsHeaderMapper integrationJmsHeaderMapper() {
    DefaultJmsHeaderMapper mapper = new DefaultJmsHeaderMapper();
    mapper.setMapInboundDeliveryMode(true);
    mapper.setMapInboundExpiration(true);
    return mapper;
}
~~~

Trong code Spring Integration, import `org.springframework.integration.jms.DefaultJmsHeaderMapper`. Đoạn này **không** phải API `SimpleJmsHeaderMapper` và **không** là cấu hình bắt buộc cho ví dụ Spring Boot JMS ở phần sau.

## 5. Truy cập metadata bằng `@Header` và `@Headers`

Trong một listener có thể khai báo payload và các metadata riêng:

~~~java
// Snippet đặt trong @Component được Spring quản lý.
@JmsListener(destination = "orders.events")
public void process(
        @Payload String payload,
        @Header(JmsHeaders.CORRELATION_ID) String correlationId,
        @Header(name = JmsHeaders.MESSAGE_ID, required = false)
                String messageId,
        @Header(name = "eventType", required = false)
                String eventType,
        @Headers Map<String, Object> headers) {

    System.out.println("correlation=" + correlationId);
    System.out.println("messageId=" + messageId);
    System.out.println("type=" + eventType);
}
~~~

Imports:
~~~java
import java.util.Map;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;
~~~

**Ý nghĩa annotations:**
- `@Payload`: lấy payload đã qua conversion; có thể là String/DTO tùy converter.
- `@Header("eventType")`: lấy một key metadata đã được map từ JMS property `eventType`; không đọc field trong JSON body.
- `@Header(JmsHeaders.CORRELATION_ID)`: lấy standard JMSCorrelationID qua Spring key.
- `@Headers Map<String,Object>`: nhận map metadata gồm JMS standard headers và custom properties được mapper đưa vào.
- `required=false`: nếu key không tồn tại, reference type như `String` có thể nhận null; tránh buộc mọi message đều phải có metadata chỉ phục vụ tracing.
- `MessageHeaders` cũng có thể được inject để truy cập headers tổng thể theo API Spring; `JmsMessageHeaderAccessor` cung cấp getters có kiểu.

**Không dùng `jakarta.jms.Message` làm kiểu của `@Payload` một cách tùy tiện.** Spring hỗ trợ raw `jakarta.jms.Message` như tham số trực tiếp, còn `@Payload` biểu thị dữ liệu đã chuyển đổi. Đừng nhầm hai kiểu `Message` có cùng tên nhưng thuộc package khác nhau.

### 5.1. Dùng `org.springframework.messaging.Message<T>`

~~~java
// Snippet: dùng tên đầy đủ của Message để tránh nhầm với jakarta.jms.Message.
@JmsListener(destination = "orders.events")
public void process(org.springframework.messaging.Message<String> event) {
    String payload = event.getPayload();
    String cid = (String) event.getHeaders()
            .get(JmsHeaders.CORRELATION_ID);
    Integer priority = (Integer) event.getHeaders()
            .get(JmsHeaders.PRIORITY);
    // validate và xử lý nghiệp vụ.
}
~~~

Lợi ích: handler dễ tái sử dụng logic theo abstraction Spring, có đầy đủ headers trong một đối tượng. Nhược điểm: nếu cần method native của provider/JMS (ví dụ `getJMSXDeliveryCount` hoặc thao tác raw `BytesMessage`), nên nhận `jakarta.jms.Message` trực tiếp hoặc thiết kế adapter riêng.

### 5.2. `JmsMessageHeaderAccessor`

~~~java
// Snippet: event có kiểu org.springframework.messaging.Message<String>.
JmsMessageHeaderAccessor accessor =
        JmsMessageHeaderAccessor.wrap(event);

String cid = accessor.getCorrelationId();
String id = accessor.getMessageId();
Integer priority = accessor.getPriority();
Boolean redelivered = accessor.getRedelivered();
Long expiration = accessor.getExpiration();
~~~

Import `org.springframework.jms.support.JmsMessageHeaderAccessor`. Các getters trả wrapper/reference và có thể trả null tùy metadata/mapping; không tự unbox `Integer`/`Long` khi chưa kiểm tra. `wrap(event)` chỉ cung cấp cách đọc typed từ Spring headers đã có; nó **không tự gọi broker** để lấy header bị thiếu.

### 5.3. Nhận raw `jakarta.jms.Message`

~~~java
// Snippet khác: có raw JMS message ngay trong listener.
@JmsListener(destination = "orders.events")
public void processRaw(jakarta.jms.Message message)
        throws jakarta.jms.JMSException {

    String cid = message.getJMSCorrelationID();
    String id = message.getJMSMessageID();
    int priority = message.getJMSPriority();
    boolean redelivered = message.getJMSRedelivered();
    String eventType = message.getStringProperty("eventType");
    int schemaVersion = message.getIntProperty("schemaVersion");
}
~~~

Khi cần biết **header có thật trên wire không**, đọc raw JMS giúp kiểm tra trực tiếp, nhất là khi đã có custom header mapper hoặc converter và nghi ngờ ánh xạ metadata. Nếu dùng DTO trong handler, raw Message chỉ là một tham số mà Spring hỗ trợ; cần kiểm tra handler method signature phù hợp. **Không dùng cả hai snippet listener này trên cùng production queue chỉ để debug**, bởi mỗi consumer có thể cạnh tranh lấy và ACK message.

## 6. Các header dễ nhầm về ý nghĩa

### 6.1. `JMSCorrelationID` so với `JMSMessageID`

**`JMSMessageID`:** do provider cấp (thường sau send), giúp nhận diện một JMS message. Một vài provider/config có thể vô hiệu hóa message ID khi producer gọi `setDisableMessageID(true)`; vì vậy header này không nhất thiết luôn có ở mọi hạ tầng. Không dùng `JMSMessageID` như idempotency key nghiệp vụ nếu producer có thể retry gửi lại cùng sự kiện, vì mỗi send có thể được cấp ID mới.

**`JMSCorrelationID`:** do producer/ứng dụng đặt để liên kết các message trong một logical request hoặc request–reply. Giá trị có thể bằng request ID, command ID, correlation ID đã có từ ingress, hoặc một ID do broker/client phối hợp. Không tự động bằng `JMSMessageID`.

~~~java
// Snippet khi gửi một JMS Message trước producer.send(...).
message.setJMSCorrelationID("request-2026-001");
~~~

Consumer:
~~~java
@Header(JmsHeaders.CORRELATION_ID) String correlationId
~~~

**Không** thay bằng `message.setStringProperty("JMSCorrelationID", "...")`; đó chỉ tạo property có tên gần giống standard header, không đảm bảo `getJMSCorrelationID()` thay đổi.

Nếu dùng Spring Integration, generic Spring Integration `correlationId` header khác `jms_correlationId` header. Một generic `MessageHeaders.ID` UUID cũng khác JMS message ID. Ba khái niệm có thể cùng mục đích quan sát nhưng không được coi là đồng nhất.

### 6.2. `JMSType` và application `eventType`

`JMSType` là standard JMS header có thể dùng mô tả loại thông điệp ở cấp ứng dụng. `JmsHeaders.TYPE` ánh xạ tới nó. Nhiều hệ thống cũng có custom property `eventType` hoặc `schemaVersion` để dùng selector, versioning và liên thông cross-platform.

~~~java
message.setJMSType("order.created");
message.setStringProperty("eventType", "order.created");
message.setIntProperty("schemaVersion", 1);
~~~

Đây là **hai field khác** cho loại sự kiện (standard JMSType và custom property). Nếu dùng cả hai, nên có contract bảo đảm chúng nhất quán; nếu không, consumer dễ dùng nhầm một metadata đã cũ.

Quan trọng: JSON converter có thể dùng một JMS property riêng, ví dụ `_type`, để mang alias Java DTO. **`_type` không mặc định là `JMSType`** và không đồng nghĩa `JmsHeaders.TYPE`. Producer và consumer phải thống nhất cách chọn DTO.

### 6.3. `JMSReplyTo` không phải String destination tự do

`JMSReplyTo` trên raw JMS là `jakarta.jms.Destination`. Nếu bạn đặt generic Spring header:

~~~java
// Snippet: replyQueue là jakarta.jms.Destination hợp lệ.
message.setJMSReplyTo(replyQueue);
~~~

thì mapping inbound tương ứng là `JmsHeaders.REPLY_TO` mang kiểu Destination. Không mặc định rằng `@Header(JmsHeaders.REPLY_TO) String queueName` sẽ luôn resolve được mọi provider-specific Destination; nếu dùng raw JMS destination, khai báo `Destination` hoặc dùng `JmsMessageHeaderAccessor.getReplyTo()`.

Trong mô hình request–reply phải xử lý:
- correlation key phù hợp và duy nhất, tránh reply trùng;
- reply destination có quyền send/consume đúng;
- TTL và late replies khi caller đã timeout;
- idempotency của business operation nếu client retry.

### 6.4. `JMSPriority`, `JMSDeliveryMode`, `JMSExpiration`

Các header này liên quan QoS và thường **được provider xác lập trong lần send**:

| Header | Đọc ở listener | Cách đặt khi gửi |
| --- | --- | --- |
| `JMSPriority` | `JmsHeaders.PRIORITY` hoặc `getJMSPriority()` | `MessageProducer.send(..., priority, ...)`; hoặc template QoS |
| `JMSDeliveryMode` | `JmsHeaders.DELIVERY_MODE` hoặc `getJMSDeliveryMode()` | `DeliveryMode.PERSISTENT/NON_PERSISTENT` tại producer |
| `JMSExpiration` | `JmsHeaders.EXPIRATION` hoặc `getJMSExpiration()` | Đặt TTL; provider tính expiration |
| `JMSTimestamp` | `JmsHeaders.TIMESTAMP` hoặc `getJMSTimestamp()` | Provider xác định lúc gửi; không tự chỉnh timestamp |
| `JMSMessageID` | `JmsHeaders.MESSAGE_ID` hoặc `getJMSMessageID()` | Provider cấp nếu không bị disable |

**Không** làm:

~~~java
// Minh họa cách KHÔNG nên đặt QoS.
message.setJMSPriority(9);
message.setJMSExpiration(System.currentTimeMillis() + 60_000L);
~~~

Provider có thể ghi đè khi send. Với Spring `JmsTemplate`:
~~~java
// Snippet: cấu hình template ở lúc tạo bean, không chỉnh singleton mỗi request.
template.setExplicitQosEnabled(true);
template.setPriority(7);
template.setDeliveryMode(jakarta.jms.DeliveryMode.PERSISTENT);
template.setTimeToLive(60_000L);
~~~

Đặt `explicitQosEnabled=true` để `JmsTemplate` chủ động áp dụng QoS đã cấu hình qua producer. Đừng lấy giá trị `JmsHeaders.PRIORITY` trong Spring header map làm bằng chứng một lời gọi producer `send` sẽ giữ priority ấy khi gửi tiếp: còn phụ thuộc API và policy QoS đang sử dụng.

### 6.5. `JMSRedelivered` và `JMSXDeliveryCount`

Khi consumer rollback/session recover hoặc chưa ACK thành công, broker có thể giao lại message:
- `JMSRedelivered` → Boolean cho biết đây là redelivery trong phạm vi JMS provider.
- `JMSXDeliveryCount` → property số lần giao theo đặc tả/provider; hữu ích để theo dõi redelivery.
- Không dùng `JMSRedelivered=false` để khẳng định business side effect chưa từng diễn ra.
- Không dùng delivery count để làm **idempotency key**. Nếu producer gửi một event trùng lần nữa, đó có thể là message mới với count = 1.

Nên dùng application `eventId`/`commandId` ổn định trong body hoặc property để chống xử lý trùng nghiệp vụ.

## 7. Project chạy được: kiểm chứng ánh xạ metadata ở `@JmsListener`

Bài thực hành gửi một String bằng `JmsTemplate`, đặt **JMSCorrelationID**, **JMSType**, và custom properties, sau đó listener nhận và kiểm tra các Spring headers tương ứng. Ví dụ ưu tiên kết quả có assertions để không báo PASS nếu metadata bị ánh xạ sai.

### 7.1. Điều kiện cần

- Java 17+, Gradle (hoặc Gradle wrapper), Spring Boot 3.3.5 và ActiveMQ Artemis broker.
- Broker chạy ở `tcp://localhost:61616`; cấu hình user `artemis/artemis` chỉ cho môi trường Docker demo riêng.
- Queue anycast `demo.jms.metadata` có quyền send/consume; broker test có thể cho auto-create, nhưng nên tạo trước ở môi trường chia sẻ.
- Không chạy listener khác trên cùng queue test, không dùng queue có message nghiệp vụ thật.
- Nếu broker không sẵn sàng/sai credentials, demo có thể fail trước khi kiểm tra header; đó là lỗi connection/config, không phải header mapping.

Có thể chạy Artemis bằng Docker trong môi trường học cách ly:

~~~bash
docker run --detach --rm --name artemis-metadata-test -p 61616:61616 -p 8161:8161 apache/artemis:latest-alpine
~~~

Đợi broker sẵn sàng qua `docker logs artemis-metadata-test`. Khi xong, dùng `docker stop artemis-metadata-test`. Không chạy lệnh này nếu máy đang có broker dùng cổng 61616. Không dùng mật khẩu mặc định ở production.

### 7.2. Cấu trúc project

~~~text
jms-header-mapping/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── MetadataApplication.java
    │   └── MetadataListener.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-header-mapping'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: "tcp://localhost:61616"
    user: "artemis"
    password: "artemis"
~~~

Các credentials này **chỉ dành cho Docker demo trên máy cá nhân**. Nếu dùng broker test của tổ chức, cấp quyền theo role và lấy secret từ môi trường/secret manager, chẳng hạn `SPRING_ARTEMIS_USER` và `SPRING_ARTEMIS_PASSWORD`, không commit mật khẩu thật vào Git. `mode: native` ngăn vô tình dùng embedded broker khi bạn muốn kiểm tra đường kết nối thực.

### 7.3. Listener nhận cả payload và headers

`src/main/java/demo/MetadataListener.java`:

~~~java
package demo;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class MetadataListener {

    private final CountDownLatch latch = new CountDownLatch(1);
    private final AtomicReference<Observed> observed =
            new AtomicReference<>();
    private volatile String expectedBody;

    public record Observed(
            String correlationId,
            String messageId,
            String messageType,
            String eventType,
            Integer schemaVersion,
            Map<String, Object> headers) {
    }

    public void expect(String runId) {
        expectedBody = "event:" + runId;
    }

    @JmsListener(destination = "demo.jms.metadata")
    public void handle(
            @Payload String body,
            @Header(name = JmsHeaders.CORRELATION_ID, required = false)
                    String correlationId,
            @Header(name = JmsHeaders.MESSAGE_ID, required = false)
                    String messageId,
            @Header(name = JmsHeaders.TYPE, required = false)
                    String messageType,
            @Header(name = "eventType", required = false)
                    String eventType,
            @Header(name = "schemaVersion", required = false)
                    Integer schemaVersion,
            @Headers Map<String, Object> headers) {

        String expected = expectedBody;
        if (expected == null || !expected.equals(body)) {
            return; // Chỉ ghi nhận message đúng của lượt demo.
        }

        observed.set(new Observed(
                correlationId,
                messageId,
                messageType,
                eventType,
                schemaVersion,
                new HashMap<>(headers)));
        latch.countDown();
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return latch.await(timeout, unit);
    }

    public Observed observed() {
        return observed.get();
    }
}
~~~

**Chi tiết nên lưu ý:**
- `@Header` và `@Headers` thuộc `org.springframework.messaging.handler.annotation`, không phải annotation định nghĩa trong `jakarta.jms`.
- Các key `JmsHeaders.*` ánh xạ standard JMS headers. `eventType` và `schemaVersion` là **custom JMS properties** nên dùng trực tiếp tên contract.
- `required=false` tránh lỗi ràng buộc khi một provider/config không gửi một header tùy chọn; trong phần assert sẽ kiểm tra những header dự kiến.
- `@Headers Map<String,Object>` chứa metadata hiện có của Spring Messaging, không phải nguyên văn mọi implementation-specific field của provider.
- `CountDownLatch` tạo điểm đồng bộ giữa listener thread và `ApplicationRunner`, giúp không phải ngủ ngẫu nhiên để hy vọng message đã nhận.
- `AtomicReference` cùng `latch` cho phép đọc snapshot metadata sau callback; callback không giữ reference đến một native JMS Message đã có thể bị container tái sử dụng/đóng session.
- Code intentionally chỉ có một lượt thử trên một instance; để xử lý nhiều requests concurrent, cần correlation table/registry theo runId, không dùng một latch singleton cho mọi message.
- Nếu queue test chứa message cũ, listener có thể tiêu thụ nó trước khi `expect` được gọi. Vì vậy, chỉ dùng dedicated queue trống hoặc filter/isolated consumer hợp lý cho integration test nghiêm túc.

### 7.4. Ứng dụng gửi message và xác minh

`src/main/java/demo/MetadataApplication.java`:

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.JmsHeaders;

@SpringBootApplication
@EnableJms
public class MetadataApplication {

    private static final String QUEUE = "demo.jms.metadata";

    public static void main(String[] args) {
        SpringApplication.run(MetadataApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(
            JmsTemplate template,
            MetadataListener listener) {

        return args -> {
            String runId = UUID.randomUUID().toString();
            listener.expect(runId);

            template.convertAndSend(
                    QUEUE, "event:" + runId, message -> {
                        message.setJMSCorrelationID(runId);
                        message.setJMSType("order.created");
                        message.setStringProperty(
                                "eventType", "order.created");
                        message.setIntProperty("schemaVersion", 1);
                        message.setStringProperty("runId", runId);
                        return message;
                    });

            if (!listener.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not receive matching message");
            }

            MetadataListener.Observed data = listener.observed();
            if (data == null
                    || !runId.equals(data.correlationId())) {
                throw new IllegalStateException(
                        "JMSCorrelationID mapping mismatch");
            }
            if (data.messageId() == null
                    || data.messageId().isBlank()) {
                throw new IllegalStateException(
                        "JMSMessageID was not supplied");
            }
            if (!"order.created".equals(data.messageType())
                    || !"order.created".equals(data.eventType())
                    || !Integer.valueOf(1).equals(
                            data.schemaVersion())) {
                throw new IllegalStateException(
                        "Type or custom property mismatch");
            }

            Map<String, Object> headers = data.headers();
            if (!Objects.equals(
                    headers.get(JmsHeaders.CORRELATION_ID), runId)
                    || !Objects.equals(
                    headers.get(JmsHeaders.MESSAGE_ID),
                    data.messageId())
                    || !Objects.equals(headers.get("runId"), runId)) {
                throw new IllegalStateException(
                        "Mapped headers map mismatch");
            }

            Object priority = headers.get(JmsHeaders.PRIORITY);
            if (!(priority instanceof Integer level)
                    || level < 0 || level > 9) {
                throw new IllegalStateException(
                        "Missing/invalid JMS priority header");
            }

            System.out.println("CORRELATION_ID_MAPPED=true");
            System.out.println("MESSAGE_ID_PRESENT=true");
            System.out.println("JMS_TYPE_MAPPED=true");
            System.out.println("CUSTOM_PROPERTIES_MAPPED=true");
            System.out.println("PRIORITY_MAPPED=true");
            System.out.println("ALL_ASSERTIONS_PASSED");
        };
    }
}
~~~

**Vì sao các assertions có giá trị:**

1. `JmsTemplate.convertAndSend` với body String tạo `TextMessage` qua `SimpleMessageConverter` mặc định.
2. `MessagePostProcessor` chạy sau chuyển đổi payload; các setter `setJMSCorrelationID` và `setJMSType` đặt **standard JMS headers**, trong khi `setStringProperty`/`setIntProperty` thêm **application properties**.
3. Listener không dùng `receiveAndConvert` đồng bộ; Spring container nhận message ở background consumer thread rồi bind các tham số.
4. Một `UUID` mới được dùng cho mỗi lượt; callback chỉ báo thành công khi body khớp ID dự kiến, tránh PASS giả do message cũ từ lần test khác.
5. `JMSMessageID` do broker/provider cấp khi send. Demo giả định chế độ message ID bình thường; nếu phía producer cấu hình disable message ID, assertion tương ứng sẽ không còn phù hợp.
6. `JmsHeaders.PRIORITY` được đọc từ **headers inbound** để chứng minh mapper đưa priority vào Spring metadata; code chỉ yêu cầu range 0..9, không ép priority cụ thể khi chưa đặt QoS.
7. Một custom property `runId` được kiểm tra trong `@Headers Map` để chứng minh ứng dụng có thể lấy properties cùng standard headers.
8. `CountDownLatch` bảo đảm khi main in `ALL_ASSERTIONS_PASSED`, listener đã quan sát được message và metadata. Nó **không** chứng minh transaction của database hay ACK/commit JMS chắc chắn đã hoàn tất.
9. Bài không thêm `@JmsListener` thứ hai trên cùng queue, tránh competing consumer làm test không ổn định.
10. Nếu broker không chạy, quyền sai hoặc message không đến, chương trình ném exception/timeout và không in PASS.

### 7.5. Chạy và output mong đợi

Tạo đúng các file, bảo đảm JDK/Gradle và broker sẵn sàng, rồi:

~~~bash
gradle bootRun
~~~

Khi phép thử thành công, các dòng do **ứng dụng** in ra là:

~~~text
CORRELATION_ID_MAPPED=true
MESSAGE_ID_PRESENT=true
JMS_TYPE_MAPPED=true
CUSTOM_PROPERTIES_MAPPED=true
PRIORITY_MAPPED=true
ALL_ASSERTIONS_PASSED
~~~

Spring Boot và Artemis có thể ghi thêm logs. `runId` là UUID ngẫu nhiên không in ra; output kiểm chứng bên trên ổn định. Nếu chương trình ném lỗi, không tự coi các dòng đã in trước đó là kết quả PASS tổng thể.

**Chưa cần broker có JSON converter:** demo chỉ gửi String `TextMessage`. Nó kiểm tra đúng nội dung về **headers/metadata mapping**, không trộn lỗi serialize DTO JSON vào kết luận.

Đây là ví dụ về logic có thể biên dịch khi dependencies đúng; việc chạy thật phụ thuộc broker, credentials và queue test. Không chạy trên production queue hoặc để demo nhận message nghiệp vụ.

## 8. Ánh xạ metadata khi gửi lại message

Một lỗi phổ biến: consumer nhận message từ queue A rồi muốn forward nó sang queue B bằng Spring Messaging `Message<T>`. Nếu copy nguyên `MessageHeaders` inbound sang outbound, bạn có thể mang theo metadata chỉ nên đọc.

**Ví dụ:**

~~~text
Inbound:
  jms_messageId = "ID:provider-123"
  jms_timestamp = 1700000000000
  jms_priority = 4
  jms_correlationId = "request-42"
  eventType = "order.created"

Outbound mong muốn:
  JMSMessageID = do provider cấp lại
  JMSTimestamp = thời điểm provider gửi lại
  JMSDestination = queue B
  JMSPriority = theo QoS outbound
  JMSCorrelationID = có thể bảo toàn request-42
  eventType = bảo toàn nếu hợp đồng cho phép
~~~

**Cách tiếp cận:** phân loại metadata thành:
- **Có thể mang qua:** business eventId, correlation ID theo contract, schemaVersion/eventType nếu ý nghĩa không đổi.
- **Do provider phải cấp lại:** message ID, send timestamp, destination, expiration theo TTL, priority/delivery mode theo send operation.
- **Không nên truyền mù:** trace/baggage có secrets, metadata tenant nội bộ, retry counter có semantics riêng, headers provider-specific.
- **Cần tái tính hoặc đánh dấu:** hop count, routing history, processing state, redelivery/attempt info. Không copy `JMSRedelivered` rồi kỳ vọng broker xem đó là lần giao lại trên queue B.

**Gợi ý:** nếu viết bridge, tạo một **outbound message mới** với payload và tập properties được phép đưa tiếp, cấu hình producer QoS rõ, rồi để provider cấp ID/header mới. Kiểm tra lại bằng integration test với broker thay vì copy raw object làm source of truth.

## 9. Metadata và JMS selector

Selector của JMS chọn message theo **JMS standard headers và message properties**, không phân tích body JSON. Vì vậy hai producer cần thống nhất **tên và kiểu property**:

~~~java
// Snippet: trong MessagePostProcessor producer.
message.setStringProperty("eventType", "order.created");
message.setIntProperty("schemaVersion", 1);
message.setBooleanProperty("urgent", true);
~~~

Consumer có thể dùng:

~~~java
@JmsListener(
    destination = "orders.events",
    selector = "eventType = 'order.created' AND schemaVersion >= 1")
public void onOrder(String body) {
    // Listener chỉ nhận message có selector TRUE.
}
~~~

Selector không đọc `eventType` field nằm trong body JSON nếu producer chưa đặt JMS property `eventType`. Nếu producer đặt `schemaVersion` kiểu String `"1"`, so sánh số `schemaVersion >= 1` không tự parse thành số — có thể **không khớp**. Nếu property thiếu, biểu thức được tính theo logic SQL NULL/UNKNOWN; chỉ TRUE mới được giao.

**JMS header name và Spring key khác nhau trong selector:**
- Trên Spring Messaging side: `@Header(JmsHeaders.PRIORITY)`, giá trị key là `jms_priority`.
- Trong JMS selector syntax: dùng **`JMSPriority >= 7`**, **không** phải `jms_priority >= 7` (trừ khi producer thực sự tạo custom property khác tên và provider cho phép).
- Trong Spring MessageHeaders: `JmsHeaders.CORRELATION_ID` → `"jms_correlationId"`.
- Trong JMS selector: `JMSCorrelationID = 'request-42'`.

**Không** dùng tên Spring internal header key trực tiếp trong JMS selector rồi kỳ vọng provider hiểu mapping Java của Spring. Selector chạy ở tầng JMS/broker, không chạy qua method parameter resolver của Spring.

### 9.1. Types và case sensitivity

| Producer đặt | Spring nhận | Selector phù hợp |
| --- | --- | --- |
| `setStringProperty("eventType", "order.created")` | `@Header("eventType") String` | `eventType = 'order.created'` |
| `setIntProperty("schemaVersion", 2)` | `@Header("schemaVersion") Integer` | `schemaVersion >= 2` |
| `setBooleanProperty("urgent", true)` | `@Header("urgent") Boolean` | `urgent = TRUE` |
| `setJMSCorrelationID("req-42")` | `@Header(JmsHeaders.CORRELATION_ID) String` | `JMSCorrelationID = 'req-42'` |
| `setJMSType("order.created")` | `@Header(JmsHeaders.TYPE) String` | `JMSType = 'order.created'` |

Property names phân biệt hoa/thường (`eventType` khác `EventType`); tên literal của String cũng phân biệt. Trong selector, kiểm tra missing bằng `IS NULL`, không dùng `= NULL`. Nếu ghép input vào selector, cần validate/escape để tránh sai cú pháp và lọc nhầm.

## 10. Request–reply và correlation metadata

Một flow request–reply có thể sử dụng:
- `JMSCorrelationID` để ghép response vào request;
- `JMSReplyTo` để chỉ nơi trả lời;
- `JMSMessageID` để làm correlation theo một convention nhất định (ví dụ reply correlation ID là message ID của request);
- `eventId`/`requestId` riêng để liên kết nghiệp vụ qua retry.

~~~text
Requester                  Worker                  Reply queue
    |                        |                          |
    |-- request ------------>|                          |
    | JMSCorrelationID=R123  |                          |
    | JMSReplyTo=replyQueue  |                          |
    |                        |-- reply ----------------->|
    |                        |   JMSCorrelationID=R123   |
    |<----------------------- reply matched by R123 ----|
~~~

Đây là **một convention**, không phải provider tự chọn mọi correlation ID cho bạn. Mọi phía phải thống nhất có phản chiếu `JMSCorrelationID` hay dùng `JMSMessageID` của request làm key. Một JMS selector trả reply sai ID có thể khiến caller chờ timeout dù message đã xuất hiện.

Với Spring `@JmsListener` trả về non-void/`@SendTo`, Spring có thể dùng `JMSReplyTo` hoặc default reply destination để trả phản hồi. Khi trả về Spring Messaging `Message<?>`, một số headers có thể được map outbound; xem cấu hình adapter. Tránh gán header `jms_replyTo` là String tùy tiện nếu mapper yêu cầu JMS `Destination`.

**Tính tin cậy:** request–reply cần deadline/TTL, xử lý late reply, duplicate request, idempotency, và không dùng reply queue chung mà consumer nào cũng có thể lấy nhầm message.

## 11. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `@Header("JMSCorrelationID")` không lấy được | Đây là tên JMS API header, không phải Spring Messaging key tiêu chuẩn | `@Header(JmsHeaders.CORRELATION_ID)` hoặc raw `getJMSCorrelationID()` |
| `@Header("jms_messageId")` có null | Provider có thể disable ID hoặc mapper custom không cung cấp | Dùng `required=false`, kiểm tra raw JMS/provider config |
| `@Header("eventType")` null dù body JSON có field | Selector/header mapper không parse JSON field thành property | Producer đặt JMS property `eventType` rõ |
| `@Header("schemaVersion") Integer` lỗi | Producer gửi property dưới dạng String hoặc sai tên/type | Chuẩn hóa producer `setIntProperty`, validate contract |
| `JmsHeaders.TYPE` khác `_type` | JMSType và converter type-id property là hai trường khác | Quy định event type/schema rõ, tránh tự đồng nhất |
| `@Header(JmsHeaders.REPLY_TO) String` không bind | Giá trị native là `Destination`, không phải tên queue String portable | Đọc `Destination` hoặc dùng accessor |
| Lấy `MessageHeaders.ID` làm JMS message ID | Spring envelope ID và provider JMS ID khác nhau | Dùng `JmsHeaders.MESSAGE_ID` |
| Đọc `JmsHeaders.PRIORITY` rồi forward với cùng priority | QoS outbound do producer/provider quyết định | Cấu hình explicit QoS trong sender |
| Copy `jms_redelivered=true` sang send mới | Redelivery flag là trạng thái provider, không phải metadata nghiệp vụ tùy ý | Để provider quản lý, dùng eventId riêng |
| Dùng `DefaultJmsHeaderMapper` trong code Spring JMS nhưng không có class | Class này thuộc module Spring Integration, không phải Spring Framework core JMS | Dùng `SimpleJmsHeaderMapper` hoặc thêm Spring Integration khi thực sự cần |
| Header type bị mất sau bridge | Mapper chỉ chuyển các kiểu JMS property hợp lệ hoặc có prefix/allowlist | Kiểm tra mapper, type, contract, integration tests |
| Consumer nhận đúng headers nhưng xử lý trùng | Message có thể redeliver hoặc producer retry | Dedupe theo eventId, transaction/ACK đúng |
| Header chứa token/user PII | Log/monitoring/broker browse có thể lộ dữ liệu | Hạn chế dữ liệu, ẩn secrets, quản lý ACL và retention |
| Listener không chạy | Sai destination/ACL, factory, transaction hoặc selector, không nhất thiết mapping | Kiểm tra broker URL, registry, listener container và logs |
| Header có giá trị nhưng selector không match | Dùng Spring key `jms_priority` thay vì JMS selector `JMSPriority`, hoặc sai type | Viết selector theo JMS syntax và property type |
| `JmsHeaders.EXPIRATION` không có trong Spring Integration map | Spring Integration mapper có lựa chọn map inbound expiration | Bật đúng mapper option ở integration endpoint nếu cần |

## 12. Kiểm thử metadata: nên kiểm tra những gì?

### 12.1. Bộ test có dữ liệu xác định

| Case | Message đầu vào | Điều cần xác minh |
| --- | --- | --- |
| T01 | Có JMSCorrelationID và `eventType` String | `@Header(JmsHeaders.CORRELATION_ID)`, `@Header("eventType")` đúng |
| T02 | Có JMSType | `@Header(JmsHeaders.TYPE)` đúng, không nhầm converter `_type` |
| T03 | Không có JMSCorrelationID | Header optional là null; listener không fail vì required |
| T04 | Có custom `schemaVersion` kiểu int | `@Header("schemaVersion") Integer` nhận kiểu phù hợp |
| T05 | `schemaVersion` String `"1"` | Test converter/binder và selector số; không giả định tự động tương thích |
| T06 | Có `JMSReplyTo` | `Destination` được map đúng, không ép String |
| T07 | Producer không đặt `JMSMessageID` thủ công | Provider cấp JMSMessageID theo policy; assert có giá trị nếu ID enabled |
| T08 | Priority khi gửi là 7 qua explicit QoS | Header nhận phản ánh actual JMSPriority do provider xác nhận |
| T09 | TTL > 0 | `JMSExpiration` có giá trị hợp lý, không set header trực tiếp |
| T10 | Redelivery sau rollback | `JMSRedelivered`, `JMSXDeliveryCount` thay đổi theo contract/provider |
| T11 | Producer retry phát hai messages cùng eventId | JMS IDs có thể khác, eventId vẫn trùng; consumer idempotency |
| T12 | Spring Message forward sang JMS | Standard read-only headers được provider cấp lại, metadata nghiệp vụ được chọn lọc |

**Lưu ý:** T06/T08/T09/T10/T12 cần cấu hình hoặc thí nghiệm broker riêng. Demo runnable chỉ tập trung vào inbound mapping của correlation/type/custom props/priority để giữ phạm vi rõ ràng.

### 12.2. Không kiểm tra bằng cách gọi method Java trực tiếp

Gọi:

~~~java
listener.handle(...);
~~~

không đi qua JMS container, `JmsHeaderMapper` hay provider, nên **không thể** chứng minh binding `@Header` hoạt động. Integration test phải gửi một JMS message thật qua broker hoặc mô phỏng đúng tầng listener adapter/message conversion trong test framework phù hợp.

### 12.3. Các assertions nên có

- Producer đặt đúng native header bằng setter tiêu chuẩn.
- Producer đặt custom properties với đúng **kiểu JMS**.
- Listener nhận đúng payload và các headers theo key `JmsHeaders.*`.
- Header optional không làm handler fail khi thiếu.
- Một bộ test có ID riêng để không nhận nhầm message từ lần chạy khác.
- Dùng latch/future có timeout hữu hạn, không dựa vào `Thread.sleep` cố định.
- Kiểm tra error path: không có broker, thiếu quyền consume, converter sai, transaction rollback hoặc selector không match.
- Khi nhiều producer khác nhau, contract test xác minh chúng tạo cùng JMS property names/types, bất kể Java/Node/Go.
- Trong test negative về mapping, có thể nhận raw JMS message để so sánh native headers, rồi xác định lỗi nằm ở producer hay mapper.

## 13. Vận hành: logging và tracing metadata đúng cách

Một log event có thể chứa:

~~~text
broker=artemis-test
queue=orders.events
eventId=e-123
jmsCorrelationId=req-456
jmsMessageId=ID:...
jmsRedelivered=false
eventType=order.created
schemaVersion=1
handlerResult=success
~~~

Đây là **định dạng log minh họa**, không phải output luôn do Spring in. Không log toàn bộ `@Headers Map` khi không kiểm soát nội dung: có thể chứa tenant IDs, tokens, custom PII hoặc vendor-specific headers.

**Khuyến nghị observability:**
- Dùng `eventId`/`correlationId` ổn định để liên kết producer→broker→consumer logs.
- Nếu dùng OpenTelemetry, quy ước W3C trace context (`traceparent`/`tracestate`) theo instrumentation đang triển khai; **không** mặc định `JMSCorrelationID` là trace ID chuẩn.
- Khi broker redeliver, ghi log `JMSRedelivered` và `JMSXDeliveryCount` với eventId để phân tích retry.
- Không coi `JMSMessageID` là nghiệp vụ unique across producer retries.
- Có metrics queue depth, oldest age, retry/DLQ và latency xử lý.
- Nếu gửi lại qua bridge, lập rõ danh sách headers được phép giữ, không copy toàn bộ standard JMS headers/provider internals.

## 14. Checklist áp dụng

- [ ] Biết phân biệt `jakarta.jms.Message` và `org.springframework.messaging.Message<?>`.
- [ ] Dùng `org.springframework.jms.support.JmsHeaders` cho standard JMS headers đã map.
- [ ] Không nhầm `MessageHeaders.ID` với `JmsHeaders.MESSAGE_ID`.
- [ ] Dùng `@Header` cho một field, `@Headers Map` cho tập metadata.
- [ ] Header optional có `required=false`/kiểu nullable hoặc kiểm tra null phù hợp.
- [ ] Custom JMS properties có tên/type trong contract; không phụ thuộc JSON body.
- [ ] Metadata cần selector được đặt thành JMS property đúng kiểu.
- [ ] `JMSReplyTo` được biểu diễn bằng `Destination` khi truy cập native.
- [ ] QoS do producer/template quản lý; không đặt priority/expiration qua custom mapping rồi kỳ vọng provider giữ.
- [ ] `JmsHeaderMapper`/`SimpleJmsHeaderMapper` và Spring Integration `DefaultJmsHeaderMapper` được phân biệt đúng module.
- [ ] Khi dùng integration gateway/adapter, policy inbound/outbound mapping được review và test.
- [ ] Không đưa PII/secrets không cần thiết vào JMS properties/logs.
- [ ] Có integration test trên queue riêng với broker thật, không ACK message production.
- [ ] Có chiến lược ACK/transaction/idempotency độc lập với metadata headers.

### Câu hỏi tự kiểm tra

1. `JmsHeaders.CORRELATION_ID` có giá trị chuỗi nào, và nó ánh xạ tới getter JMS nào?
2. Vì sao `JMSCorrelationID`, `JMSMessageID` và Spring `MessageHeaders.ID` không nên dùng thay cho nhau?
3. `@Header(JmsHeaders.TYPE)` tương ứng `JMSType` hay converter property `_type`?
4. Cách nào lấy toàn bộ metadata đã được Spring ánh xạ trong `@JmsListener`?
5. `@Header(JmsHeaders.REPLY_TO) String` có phải luôn hợp lệ không? Vì sao?
6. Tại sao `message.setJMSPriority(9)` trước gửi có thể không bảo đảm priority 9 được dùng?
7. Spring Framework `SimpleJmsHeaderMapper` khác gì Spring Integration `DefaultJmsHeaderMapper`?
8. Nếu `eventType` chỉ có trong JSON body, `@Header("eventType")` tự đọc được không?
9. Nếu muốn selector theo priority, bạn viết `JMSPriority >= 7` hay `jms_priority >= 7`?
10. Với một message được giao lại sau rollback, bạn xem các metadata nào và vì sao chúng không thay thế deduplication nghiệp vụ?
11. Khi forward message qua queue khác, nên làm gì với JMSMessageID và JMSTimestamp?
12. Test gọi trực tiếp method annotated có chứng minh Spring header mapping hoạt động không?

**Ghi nhớ:** `JmsHeaders` là **tên metadata JMS trong Spring Messaging headers**. `@Header`/`@Headers` giúp listener lấy standard headers và custom properties; `SimpleJmsHeaderMapper` thực hiện chuyển đổi giữa native JMS và Spring Message. Đọc đúng key, type và chiều mapping; để JMS provider quản lý header read-only/QoS; dùng eventId/correlation ID có hợp đồng ổn định; kiểm chứng bằng listener thật trên broker test.

## Tài liệu tham khảo

1. Spring Framework 6.2 — Annotation-driven JMS Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
2. Spring Framework 6.2 — `JmsHeaders` constants and package: https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/jms/support/JmsHeaders.html
3. Spring Framework 6.1 — `SimpleJmsHeaderMapper`: https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/jms/support/SimpleJmsHeaderMapper.html
4. Spring Framework 6.2 — `JmsMessageHeaderAccessor`: https://www.javadoc.io/static/org.springframework/spring-jms/6.2.13/org/springframework/jms/support/JmsMessageHeaderAccessor.html
5. Spring Integration 6.x — JMS Header Mapping / `DefaultJmsHeaderMapper`: https://docs.spring.io/spring-integration/reference/jms.html
6. Spring Boot 3.x — JMS / Artemis support: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
7. Jakarta Messaging 3.1 Specification — Message headers and properties: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
