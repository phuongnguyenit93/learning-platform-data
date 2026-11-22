# Giảm phụ thuộc vào lớp Java nội bộ và tuần tự hóa ObjectMessage

## 1. Vấn đề cần giải quyết

Một hệ thống messaging chỉ thực sự tách rời khi hai phía trao đổi một hợp đồng dữ liệu ổn định mà không phải chia sẻ toàn bộ cấu trúc triển khai của nhau. Nếu producer gửi trực tiếp object thuộc domain model, entity ORM hoặc lớp Java nội bộ, consumer sẽ phụ thuộc vào tên lớp, package, cấu trúc field, thư viện và phiên bản build của producer.

Vấn đề trở nên rõ hơn khi dùng JMS `ObjectMessage`. Kiểu message này chứa một object Java `Serializable`; bên nhận phải giải tuần tự hóa object đó để sử dụng. Trong Spring JMS, `SimpleMessageConverter` mặc định chuyển một object `Serializable` thành `ObjectMessage` khi gọi các phương thức chuyển đổi như `JmsTemplate.convertAndSend`.

Hệ quả thường gặp:

- Producer và consumer phải có class tương thích ở runtime.
- Thay đổi package, class hierarchy hoặc cấu trúc object có thể làm hỏng việc đọc message cũ.
- Consumer bị phụ thuộc vào Java và quy tắc serialization của JVM.
- Khó tích hợp service viết bằng ngôn ngữ khác.
- Việc deserialize dữ liệu không đáng tin cậy có thể tạo rủi ro bảo mật nghiêm trọng.
- Một thay đổi nội bộ tưởng như nhỏ có thể buộc nhiều service phải phát hành cùng lúc.

Cách thiết kế bền vững là tách **mô hình nghiệp vụ nội bộ** khỏi **hợp đồng message bên ngoài**, sau đó chuyển đổi qua định dạng có schema rõ ràng như JSON, Avro hoặc Protocol Buffers. Với JMS, thường dùng `TextMessage` cho JSON/XML hoặc `BytesMessage` cho dữ liệu nhị phân đã được định nghĩa schema.

## 2. Phân biệt object nội bộ và message contract

### 2.1. Không gửi trực tiếp domain entity

Giả sử Order Service có entity nội bộ:

~~~java
@Entity
public class OrderEntity {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY)
    private CustomerEntity customer;

    @OneToMany(fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines;

    private BigDecimal total;
    private String internalRiskFlag;
    private int persistenceVersion;
}
~~~

Đây là cấu trúc phục vụ persistence và logic nội bộ. Nó có thể chứa quan hệ lazy, proxy ORM, field nội bộ, thông tin nhạy cảm hoặc chi tiết không thuộc hợp đồng tích hợp.

Nếu gửi trực tiếp entity này, consumer có thể vô tình phụ thuộc vào:

- Tên class và package của producer.
- Quan hệ ORM và cách framework biểu diễn proxy.
- Field nội bộ không có ý nghĩa với consumer.
- Cách biểu diễn tiền tệ, trạng thái hoặc thời gian của domain model.
- Phiên bản thư viện và classpath của ứng dụng producer.

Thay đổi database hoặc refactor domain model khi đó trở thành thay đổi giao thức giữa các service.

### 2.2. Tạo DTO theo mục đích tích hợp

Tạo một DTO công khai, nhỏ và chỉ chứa dữ liệu consumer cần:

~~~java
import java.util.List;

public record OrderPlacedV1(
    String eventId,
    String orderId,
    String customerId,
    String occurredAt,
    List<OrderLineData> lines,
    String currency,
    long totalMinorUnits
) {
    public record OrderLineData(
        String productId,
        int quantity
    ) {}
}
~~~

`occurredAt` trong ví dụ là chuỗi thời gian theo ISO 8601, ví dụ `2026-11-07T10:30:00Z`. Contract cần quy định rõ timezone và độ chính xác. Dùng chuỗi ở đây giúp ví dụ không phụ thuộc vào việc đăng ký module Jackson hỗ trợ `java.time`.

DTO này là một **message contract**. Nó không cần phản ánh đầy đủ entity, aggregate hay object graph của producer. Một event có thể chỉ công bố ID và các fact cần thiết; consumer có thể truy vấn dữ liệu khác qua API phù hợp nếu thật sự cần.

Nên chuyển đổi ở ranh giới giữa domain và messaging:

~~~java
OrderPlacedV1 toContract(OrderEntity order, String eventId) {
    return new OrderPlacedV1(
        eventId,
        order.getId().toString(),
        order.getCustomer().getId().toString(),
        order.getPlacedAt().toString(),
        order.getLines().stream()
            .map(line -> new OrderPlacedV1.OrderLineData(
                line.getProductId(),
                line.getQuantity()))
            .toList(),
        order.getCurrency(),
        order.getTotalMinorUnits()
    );
}
~~~

Ví dụ giả định domain đã có phương thức `getTotalMinorUnits` để trả về số tiền theo đơn vị nhỏ nhất đã quy định trong contract. Không nên mặc định mọi currency đều có hai chữ số thập phân; hợp đồng cần quy định rõ đơn vị hoặc dùng biểu diễn decimal dạng chuỗi kèm currency.

Việc chuyển đổi tường minh có một lợi ích quan trọng: khi domain model thay đổi, producer chỉ cần giữ cho mapper tiếp tục tạo ra contract tương thích. Consumer không cần biết producer đã đổi entity như thế nào.

### 2.3. Tách module contract khỏi module triển khai

| Cách chia sẻ | Mức phụ thuộc | Khi phù hợp |
|---|---|---|
| Chia sẻ entity/domain class | Rất cao | Tránh dùng giữa các service độc lập |
| Chia sẻ Java DTO JAR | Trung bình đến cao | Hệ thống Java có quy trình release đồng bộ và quản lý version chặt |
| Chia sẻ schema trung lập, mỗi bên tự tạo DTO | Thấp hơn | Service độc lập, đa ngôn ngữ, triển khai và nâng cấp riêng |

Một thư viện DTO riêng tốt hơn việc chia sẻ domain entity, nhưng nó vẫn tạo phụ thuộc vào Java artifact và lịch phát hành của thư viện. Với hệ thống phân tán hoặc đa ngôn ngữ, nên coi JSON Schema, Avro schema, Protobuf schema hoặc AsyncAPI contract là nguồn hợp đồng chính. Mỗi service có thể sinh code hoặc tự ánh xạ sang kiểu nội bộ.

Không nên để package Java của producer trở thành tên định danh giao thức mà consumer bắt buộc phải biết.

## 3. ObjectMessage hoạt động như thế nào?

### 3.1. Đặc điểm của JMS ObjectMessage

`jakarta.jms.ObjectMessage` là một loại JMS message có body chứa một object Java có thể tuần tự hóa. Object truyền vào phải triển khai `Serializable`. API cung cấp `Session.createObjectMessage(Serializable)` để tạo message và `getObject()` để đọc object ở phía nhận.

Ví dụ thuần JMS:

~~~java
import jakarta.jms.ObjectMessage;
import jakarta.jms.Session;

ObjectMessage message = session.createObjectMessage(orderEvent);
~~~

`ObjectMessage` giữ snapshot của object tại thời điểm gọi `setObject`; thay đổi object gốc sau đó không làm thay đổi body của message. Khi nhận, message ở chế độ chỉ đọc; API cho phép gọi `clearBody` trước khi ghi lại body.

Vấn đề của kiểu message này không chỉ là việc class phải triển khai `Serializable`. Nội dung được biểu diễn bằng cơ chế Java Object Serialization, vì vậy consumer phải hiểu cấu trúc serialized object và có các class cần thiết để dựng lại object graph.

### 3.2. Spring có thể tạo ObjectMessage mà không dễ nhận ra

`SimpleMessageConverter` là converter mặc định được `JmsTemplate` dùng cho `convertAndSend` và `receiveAndConvert` nếu không cấu hình converter khác.

Mapping mặc định của converter này:

| Object gửi vào | JMS message được tạo |
|---|---|
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` | `MapMessage` |
| Object triển khai `Serializable` | `ObjectMessage` |

Vì vậy, đoạn code sau có thể tạo `ObjectMessage` nếu `PlaceOrder` triển khai `Serializable` và `JmsTemplate` vẫn dùng `SimpleMessageConverter`:

~~~java
jmsTemplate.convertAndSend("orders", command);
~~~

Việc đổi tên method thành `convertAndSend` không có nghĩa payload được chuyển thành JSON. Kiểu JMS message phụ thuộc vào converter đang được cấu hình.

Nếu muốn tự tạo `TextMessage`, có thể dùng `send` với `MessageCreator`; nếu muốn chuyển object DTO thành JSON, hãy cấu hình converter JSON và kiểm tra kiểu message thực tế ở phía JMS.

### 3.3. Vì sao không nên dùng ObjectMessage làm hợp đồng tích hợp dài hạn?

**Phụ thuộc class và classpath.** Consumer phải có class tương thích để đọc serialized object. Di chuyển package hoặc đổi class name có thể làm consumer không tìm thấy class.

**Phụ thuộc phiên bản serialization.** Việc thêm, xóa hoặc đổi kiểu field, thay đổi class hierarchy và `serialVersionUID` có thể ảnh hưởng khả năng đọc message đã lưu. Java serialization có quy tắc tương thích riêng, nhưng không phải schema evolution contract phù hợp cho nhiều service độc lập.

**Phụ thuộc Java.** Consumer viết bằng Go, Python, JavaScript hoặc .NET không thể sử dụng trực tiếp Java object graph như một hợp đồng dữ liệu thông thường.

**Khó quan sát và kiểm tra.** Payload không phải văn bản JSON/XML dễ đọc. Việc kiểm tra message trong broker console, log hoặc công cụ tích hợp trở nên khó khăn hơn.

**Rủi ro deserialization.** Java deserialization có thể khởi tạo object và thực thi logic trong quá trình dựng object graph. Dữ liệu serialized không đáng tin cậy có thể khai thác gadget class trong classpath hoặc gây tiêu thụ tài nguyên quá mức.

**Khó kiểm soát dữ liệu.** Object graph có thể chứa nhiều field và tham chiếu ngoài ý muốn, làm lộ dữ liệu nội bộ hoặc tạo payload quá lớn.

Do đó, không nên coi `ObjectMessage` là định dạng tích hợp mặc định giữa service, đặc biệt khi producer và consumer có vòng đời phát hành độc lập hoặc broker nhận message từ nguồn không hoàn toàn đáng tin cậy.

## 4. Chọn định dạng message độc lập với Java

### 4.1. So sánh các loại JMS body

| Loại message | Nội dung | Ưu điểm | Giới hạn |
|---|---|---|---|
| `TextMessage` | Một chuỗi văn bản | Dễ đọc, phù hợp JSON/XML, đa ngôn ngữ | Cần quy ước encoding và schema |
| `BytesMessage` | Dãy byte | Phù hợp Avro, Protobuf, dữ liệu nhị phân | Cần schema/encoding và công cụ giải mã |
| `MapMessage` | Tập field tên/giá trị kiểu JMS hỗ trợ | Hợp đồng đơn giản, không cần Java class | Kiểu dữ liệu và cấu trúc lồng nhau bị giới hạn |
| `ObjectMessage` | Java Serializable object | Tiện trong ứng dụng Java cũ | Coupling class, serialization và rủi ro deserialization |

Không có định dạng nào phù hợp mọi trường hợp. JSON thường dễ quan sát và tích hợp; Avro/Protobuf có schema và encoding nhị phân phù hợp khi cần tối ưu kích thước hoặc quản lý schema chặt; `MapMessage` có thể đủ cho payload rất đơn giản.

### 4.2. JSON trong TextMessage

Ví dụ body JSON của event:

~~~json
{
  "eventId": "evt-01J8A2",
  "orderId": "ord-10042",
  "customerId": "cus-700",
  "occurredAt": "2026-11-07T10:30:00Z",
  "currency": "VND",
  "totalMinorUnits": 12500000
}
~~~

Body này có thể được consumer Java, Kotlin, Python, Go hoặc JavaScript đọc nếu các bên thống nhất schema và cách biểu diễn giá trị.

JSON không tự làm message trở nên an toàn hoặc tương thích. Producer và consumer vẫn phải thống nhất:

- Tên field, kiểu dữ liệu và field bắt buộc/tùy chọn.
- Format timestamp, timezone và độ chính xác.
- Biểu diễn tiền tệ và số thập phân.
- Giá trị enum và cách xử lý giá trị chưa biết.
- Null, field bị thiếu và default.
- Quy tắc tương thích khi thêm hoặc bỏ field.

Không bật cơ chế polymorphic deserialization tùy tiện để JSON có thể khởi tạo bất kỳ Java class nào theo metadata do message gửi tới. Ưu tiên DTO đích rõ ràng và type mapping có allowlist.

### 4.3. JSON trong BytesMessage

Một số converter ghi JSON dưới dạng `BytesMessage` thay vì `TextMessage`. Nội dung là byte nên phải thống nhất encoding; với JSON dạng văn bản, UTF-8 là lựa chọn phổ biến.

`BytesMessage` cũng có thể chứa format nhị phân khác. Không được giả định mọi BytesMessage đều là UTF-8 JSON; hãy xác định content type, schema ID hoặc metadata tương ứng.

### 4.4. Avro và Protocol Buffers

Khi hệ thống cần schema rõ ràng và payload nhị phân, có thể dùng:

- **Avro:** schema mô tả record và field; hữu ích khi cần schema evolution và tích hợp schema registry.
- **Protocol Buffers:** message schema định nghĩa field number và kiểu dữ liệu; hỗ trợ code generation cho nhiều ngôn ngữ.
- **CBOR hoặc format nhị phân khác:** phù hợp khi có yêu cầu cụ thể về kích thước, hiệu năng hoặc thiết bị.

Với `BytesMessage`, producer ghi byte đã encode; consumer đọc byte rồi decode bằng schema tương ứng. Hai phía phải thống nhất cách tìm schema: schema ID trong message property, registry, version được định tuyến hoặc một cơ chế khác.

Không chỉ dựa vào thứ tự field hay tên class Java để giải mã. Với Protobuf, field number là một phần của contract; không tái sử dụng field number đã bỏ. Với Avro, cần tuân thủ quy tắc writer schema/reader schema và compatibility của registry.

## 5. Thiết kế envelope và metadata ổn định

Một message tích hợp thường cần phân biệt phần mô tả hợp đồng, metadata vận hành và payload nghiệp vụ.

Ví dụ envelope ở dạng JSON:

~~~json
{
  "messageType": "order.placed",
  "schemaVersion": 1,
  "messageId": "evt-01J8A2",
  "correlationId": "req-9F2",
  "occurredAt": "2026-11-07T10:30:00Z",
  "payload": {
    "orderId": "ord-10042",
    "customerId": "cus-700",
    "currency": "VND",
    "totalMinorUnits": 12500000
  }
}
~~~

Các trường thường có ý nghĩa:

| Trường | Ý nghĩa |
|---|---|
| `messageType` | Tên loại hợp đồng ổn định, ví dụ `order.placed` |
| `schemaVersion` | Phiên bản cấu trúc payload |
| `messageId` | Định danh duy nhất của message |
| `correlationId` | Liên kết message với request hoặc workflow |
| `causationId` | Message trực tiếp gây ra message hiện tại |
| `occurredAt` | Thời điểm sự kiện nghiệp vụ xảy ra |
| `payload` | Dữ liệu nghiệp vụ theo schema |

Có thể đặt một số metadata trong JMS properties/headers thay vì lặp lại trong JSON body. Nếu dùng converter có type ID property, ví dụ `eventType`, cần thống nhất đây là property do converter sử dụng và ánh xạ nó sang type ID ổn định.

Đừng đưa tên Java class như `com.company.order.internal.OrderEntity` vào field type ID. Hãy dùng identifier theo contract như `order.placed.v1` hoặc `order-placed-v1`. Consumer ánh xạ identifier này sang DTO riêng của nó.

### 5.1. Phân biệt JMS headers, properties và body

- **JMS headers** là metadata chuẩn do JMS định nghĩa, ví dụ `JMSMessageID`, `JMSCorrelationID`, `JMSReplyTo` và thông tin delivery.
- **JMS properties** là metadata ứng dụng gắn vào message, thường dùng cho selector, type ID, tenant hoặc tracing. Giá trị property phải thuộc kiểu dữ liệu JMS hỗ trợ.
- **Body** chứa payload hoặc envelope nghiệp vụ.

Không đặt payload lớn trong JMS property; property phù hợp cho metadata đơn giản. Không đặt mọi thông tin nghiệp vụ vào header vì body mới là nơi chứa contract chính và được version hóa.

## 6. Cấu hình Spring JMS để không tạo ObjectMessage

### 6.1. Hiểu converter đang được dùng

`JmsTemplate` sử dụng một `org.springframework.jms.support.converter.MessageConverter` để chuyển object thành JMS message khi gọi các method `convertAndSend` hoặc `receiveAndConvert`.

Nếu không cấu hình converter, `SimpleMessageConverter` được sử dụng. Do đó, chỉ đổi DTO thành record hoặc chuyển package không đủ để bảo đảm message không còn là `ObjectMessage`; phải cấu hình converter và kiểm tra kết quả ở phía JMS.

### 6.2. Spring Framework 7: JacksonJsonMessageConverter

Với Spring Framework 7, dùng `JacksonJsonMessageConverter` (Jackson 3) để chuyển DTO thành JSON. Đặt target type là `MessageType.TEXT` nếu muốn body là `TextMessage`:

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.JacksonJsonMessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JmsMessagingConfiguration {

    @Bean
    JacksonJsonMessageConverter jmsMessageConverter() {
        JacksonJsonMessageConverter converter =
            new JacksonJsonMessageConverter();

        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("eventType");
        converter.setTypeIdMappings(Map.of(
            "order.placed.v1", OrderPlacedV1.class,
            "inventory.reserved.v1", InventoryReservedV1.class
        ));

        return converter;
    }
}
~~~

Trong ví dụ:

- Body là JSON được tạo từ DTO.
- JMS property `eventType` chứa type ID.
- `order.placed.v1` được ánh xạ tới DTO `OrderPlacedV1`.
- Consumer không cần nhận tên package Java của producer.

Spring Framework 7 cũng cung cấp `JmsClient` cho cách gửi/nhận message theo API messaging hiện đại. Nếu ứng dụng đã dùng `JmsTemplate`, có thể tiếp tục dùng nó và cấu hình converter phù hợp.

### 6.3. Spring Framework 6.2: MappingJackson2MessageConverter

Với Spring Framework 6.2 và Jackson 2, dùng `MappingJackson2MessageConverter`. Cấu hình type ID mapping tương tự:

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JmsMessagingConfiguration {

    @Bean
    MappingJackson2MessageConverter jmsMessageConverter() {
        MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();

        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("eventType");
        converter.setTypeIdMappings(Map.of(
            "order.placed.v1", OrderPlacedV1.class,
            "inventory.reserved.v1", InventoryReservedV1.class
        ));

        return converter;
    }
}
~~~

`MappingJackson2MessageConverter` là converter Jackson 2; trong Spring 7 nó đã được đánh dấu deprecated để chuyển sang `JacksonJsonMessageConverter`. Chọn đúng converter theo phiên bản Spring/Jackson đang dùng, không trộn class Jackson 2 và Jackson 3 trong cùng ví dụ cấu hình.

### 6.4. Gắn converter vào JmsTemplate

Tạo `JmsTemplate` với converter đã cấu hình:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MessageConverter;

@Bean
JmsTemplate jmsTemplate(
        ConnectionFactory connectionFactory,
        MessageConverter converter) {

    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setMessageConverter(converter);
    return template;
}
~~~

Đây là ví dụ cấu hình thủ công; trong ứng dụng Spring Boot, cần bảo đảm bean converter được gắn vào `JmsTemplate` mà ứng dụng thực sự sử dụng. Chỉ khai báo converter bean không phải lúc nào cũng chứng minh mọi template tùy chỉnh đều dùng nó.

### 6.5. Gắn converter vào listener container

Consumer dùng `@JmsListener` cũng cần listener container có converter tương ứng để chuyển JMS message thành DTO:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.converter.MessageConverter;

@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory,
        MessageConverter converter) {

    DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setMessageConverter(converter);
    return factory;
}
~~~

Consumer nhận DTO:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventListener {

    @JmsListener(
        destination = "orders.events",
        containerFactory = "jmsListenerContainerFactory"
    )
    public void onOrderPlaced(OrderPlacedV1 event) {
        // Ánh xạ contract sang mô hình nội bộ của consumer.
    }
}
~~~

Producer gửi DTO:

~~~java
jmsTemplate.convertAndSend("orders.events", event);
~~~

Nếu converter cần type ID property để chọn class đích, producer và consumer phải dùng cùng quy ước type ID mapping. Kiểm thử message thực tế sẽ phát hiện trường hợp converter chỉ được cấu hình ở một phía.

### 6.6. Dùng MessagePostProcessor cho metadata

Có thể gắn correlation ID hoặc metadata đơn giản sau khi converter đã tạo JMS message:

~~~java
jmsTemplate.convertAndSend(
    "orders.events",
    event,
    message -> {
        message.setJMSCorrelationID(correlationId);
        message.setStringProperty("tenantId", tenantId);
        return message;
    }
);
~~~

`MessagePostProcessor` tác động lên JMS message sau khi chuyển đổi payload và trước khi gửi. Không dùng metadata do client tự khai báo làm bằng chứng xác thực tenant hoặc quyền truy cập; server cần kiểm tra danh tính và quyền bằng cơ chế bảo mật đáng tin cậy.

## 7. Quản lý type ID mà không làm lộ Java package

Một số converter cần biết DTO đích khi đọc message. Có thể truyền type ID trong JMS property.

Không nên dùng tên class đầy đủ:

~~~text
com.example.orders.internal.OrderPlacedEntity
~~~

Thay vào đó dùng tên hợp đồng ổn định:

~~~text
order.placed.v1
inventory.reserved.v1
~~~

Converter được cấu hình với mapping tường minh:

~~~java
converter.setTypeIdPropertyName("eventType");
converter.setTypeIdMappings(Map.of(
    "order.placed.v1", OrderPlacedV1.class,
    "inventory.reserved.v1", InventoryReservedV1.class
));
~~~

Type ID là identifier của contract; class Java chỉ là implementation mà từng consumer chọn để ánh xạ. Consumer khác có thể ánh xạ cùng ID sang class khác hoặc một cấu trúc khác bằng ngôn ngữ khác.

Không bật polymorphic type resolution rộng chỉ để tránh phải khai báo mapping. Hãy giới hạn loại payload được phép giải mã, dùng DTO cụ thể và kiểm tra schema trước khi xử lý.

## 8. Bảo mật và giới hạn của việc thay ObjectMessage bằng JSON

### 8.1. Vì sao Java deserialization cần được hạn chế?

Deserialization của Java không chỉ đọc các giá trị primitive. Nó dựng lại object graph và có thể gọi logic tùy biến như `readObject` trong quá trình xử lý. Nếu dữ liệu đầu vào không đáng tin cậy và classpath có gadget phù hợp, quá trình deserialize có thể dẫn đến thực thi hành vi ngoài dự kiến hoặc tiêu thụ tài nguyên quá mức.

Oracle khuyến nghị tránh deserialize dữ liệu không đáng tin cậy và dùng serialization filter để giới hạn class cùng kích thước/độ phức tạp của object graph khi không thể tránh. Serialization filter không tự bật mặc định chỉ vì ứng dụng chạy trên JDK mới.

JEP 290 cung cấp `ObjectInputFilter` để kiểm soát class, kích thước mảng, độ sâu graph và số lượng tham chiếu. Tuy nhiên, với JMS, việc cấu hình filter cụ thể còn phụ thuộc JMS provider/client tạo luồng deserialize. Cần kiểm tra tài liệu và khả năng cấu hình của provider đang dùng; không giả định ứng dụng có thể gắn filter trực tiếp vào `ObjectMessage.getObject`.

Nếu buộc phải duy trì `ObjectMessage` trong hệ thống cũ:

- Chỉ nhận từ producer và broker đã xác thực, được kiểm soát.
- Dùng allowlist class và serialization filter phù hợp ở đúng nơi provider thực hiện deserialization.
- Giới hạn kích thước message, độ sâu object graph, số reference và thời gian xử lý.
- Không mở rộng classpath hoặc allowlist một cách tùy tiện.
- Có kế hoạch loại bỏ ObjectMessage khỏi contract tích hợp.

Các biện pháp trên là phòng thủ bổ sung. Chúng không biến Java native serialization thành định dạng tích hợp độc lập với Java.

### 8.2. JSON cũng cần kiểm soát đầu vào

Đổi sang JSON giảm coupling class và tránh Java native object deserialization, nhưng JSON không tự động an toàn. Consumer vẫn cần:

- Giới hạn kích thước payload và độ sâu cấu trúc.
- Kiểm tra schema, kiểu dữ liệu, độ dài chuỗi và miền giá trị.
- Không bật Jackson default typing hoặc polymorphic class resolution rộng với dữ liệu không tin cậy.
- Chỉ ánh xạ các type ID đã được cho phép.
- Kiểm tra quyền truy cập và tính hợp lệ nghiệp vụ sau khi parse.
- Không log payload có thông tin bí mật hoặc dữ liệu cá nhân không cần thiết.

Với `MappingJackson2MessageConverter` của Spring 6.2.19 trở lên, có API `setTrustedPackages` để giới hạn package được tin cậy khi converter xử lý type ID theo class. Đây là kiểm soát cho converter JSON của Spring; nó không thay thế serialization filter của Java và cũng không phải lý do để truyền class name nội bộ qua message. Ưu tiên synthetic type ID mapping rõ ràng.

### 8.3. Bảo vệ metadata và payload

- Dùng TLS và xác thực kết nối producer/consumer.
- Phân quyền destination ở broker và ở tầng ứng dụng.
- Không tin tenant ID, user ID hoặc role chỉ vì chúng xuất hiện trong header.
- Mã hóa hoặc loại bỏ field nhạy cảm theo chính sách dữ liệu.
- Thiết lập retention, dead-letter queue và quyền truy cập message phù hợp.
- Ghi log message ID, type ID, correlation ID và lỗi chuyển đổi; hạn chế ghi body đầy đủ.

## 9. Schema evolution và tương thích producer-consumer

### 9.1. Thêm field

Thêm field tùy chọn thường dễ tương thích hơn đổi tên hoặc đổi kiểu field. Ví dụ schema mới thêm `shippingMethod`:

~~~json
{
  "orderId": "ord-10042",
  "currency": "VND",
  "totalMinorUnits": 12500000,
  "shippingMethod": "EXPRESS"
}
~~~

Consumer cũ phải có chính sách rõ ràng với field chưa biết: bỏ qua nếu hợp đồng cho phép hoặc từ chối nếu cần kiểm soát nghiêm. Consumer mới phải xử lý trường hợp producer cũ chưa gửi field đó bằng default hoặc giá trị vắng mặt có ý nghĩa.

Jackson converter trong Spring có cấu hình mặc định riêng về unknown properties; không nên dựa vào mặc định đó làm chính sách schema. Hãy cấu hình và kiểm thử theo contract đã chọn.

### 9.2. Thay đổi phá vỡ tương thích

Các thay đổi sau thường có nguy cơ phá vỡ consumer:

- Đổi tên field hoặc đổi kiểu dữ liệu.
- Đổi ý nghĩa của field mà vẫn giữ tên cũ.
- Chuyển field tùy chọn thành bắt buộc.
- Xóa enum value mà consumer cũ vẫn có thể nhận.
- Thay đổi đơn vị đo, timezone hoặc cách biểu diễn tiền.
- Tái sử dụng schema version hoặc type ID cho payload khác.

Nếu cần thay đổi lớn, phát hành contract version mới, ví dụ `order.placed.v2`, hoặc dùng version trong envelope. Giữ consumer có thể đọc version cũ trong giai đoạn chuyển đổi.

### 9.3. Quy tắc cho enum và giá trị chưa biết

Consumer không nên giả định producer chỉ gửi các enum value đã biết ở thời điểm compile. Khi schema cho phép enum mở rộng, consumer cần nhánh xử lý unknown phù hợp: bỏ qua có kiểm soát, chuyển sang trạng thái generic hoặc đưa vào dead-letter để điều tra. Không tự suy diễn giá trị mới thành một trạng thái nghiệp vụ khác.

### 9.4. Schema registry và code generation

Với Avro/Protobuf, có thể quản lý schema trong repository hoặc schema registry. Pipeline nên kiểm tra compatibility trước khi phát hành. Code generation tạo DTO/serializer từ schema, nhưng không làm mất nhu cầu kiểm tra phiên bản, quyền truy cập và semantics nghiệp vụ.

Với JSON, JSON Schema hoặc AsyncAPI có thể mô tả payload, message channel, operation, header và security scheme. Lưu schema như artifact có version và kiểm thử producer/consumer dựa trên cùng hợp đồng.

## 10. Migration khỏi ObjectMessage

Không nên đổi producer trước rồi hy vọng consumer cũ tự đọc được JSON. Producer và consumer cần một kế hoạch chuyển đổi có thứ tự.

### Bước 1: Kiểm kê

Xác định:

- Producer nào gửi tới từng queue/topic.
- Consumer nào đang đọc từng destination.
- Message hiện tại là `ObjectMessage`, `TextMessage`, `BytesMessage` hay `MapMessage`.
- DTO/entity nào được serialize và classpath nào đang được chia sẻ.
- Message có thời gian lưu dài hoặc còn tồn tại trong queue/dead-letter queue không.
- Retry, replay và lịch sử message có yêu cầu tương thích ngược không.

### Bước 2: Chốt contract trung lập

Thiết kế payload có version, type ID ổn định và metadata cần thiết. Xác định cách biểu diễn thời gian, tiền, enum, null và ID. Viết ví dụ JSON hoặc schema nhị phân làm tài liệu kiểm thử.

### Bước 3: Nâng cấp consumer trước

Triển khai consumer có thể đọc định dạng mới. Nếu phải xử lý message cũ trong giai đoạn chuyển đổi, cô lập nhánh đọc legacy, giới hạn nguồn tin cậy và áp dụng filter phù hợp. Không mở rộng deserialization tùy tiện để phục vụ dual-read.

Một lựa chọn an toàn hơn là tạo destination version mới, để consumer mới chỉ nhận contract mới, sau đó chuyển producer và drain destination cũ theo kế hoạch.

### Bước 4: Cấu hình converter ở cả hai phía

Gắn converter JSON/bytes vào `JmsTemplate` và listener container. Kiểm tra producer thực sự tạo đúng kiểu JMS message; kiểm tra consumer đọc đúng DTO và type ID.

### Bước 5: Chuyển producer

Map domain object sang DTO contract, publish qua converter và giữ nguyên semantics của command/event. Không đưa entity ORM hoặc exception object vào payload.

### Bước 6: Theo dõi và kết thúc migration

Theo dõi số message mới/cũ, conversion failure, dead-letter, consumer lag và retry. Chờ destination cũ được xử lý hết hoặc di chuyển theo quy trình đã xác định. Sau đó loại bỏ legacy deserialization code và dependency Java serialization khỏi đường đi message.

## 11. Kiểm thử contract và kiểm tra kiểu JMS message

Một bài kiểm thử chỉ xác nhận method `convertAndSend` không ném exception là chưa đủ. Cần xác nhận message wire format đúng như hợp đồng.

### 11.1. Kiểm tra kiểu message được tạo

Trong test dùng JMS provider thực tế hoặc test broker tương thích, gửi DTO và kiểm tra message nhận được là `TextMessage` nếu đã cấu hình `MessageType.TEXT`:

~~~java
Message message = receiveRawMessage("orders.events");

assertThat(message).isInstanceOf(TextMessage.class);
assertThat(((TextMessage) message).getText()).contains("\"orderId\"");
assertThat(message.getStringProperty("eventType"))
    .isEqualTo("order.placed.v1");
~~~

`receiveRawMessage` ở đây đại diện helper của test để nhận message JMS thô; cần triển khai bằng test infrastructure đang dùng. Đoạn trên là minh họa assertion, không phải test độc lập có thể biên dịch nguyên trạng nếu chưa có helper và broker.

Nếu test nhận được `ObjectMessage`, hãy kiểm tra converter thực sự được gắn vào template đang gửi, không chỉ kiểm tra bean converter tồn tại trong ApplicationContext.

### 11.2. Kiểm thử tương thích

- Producer mới tạo payload theo schema mới.
- Consumer cũ có thể bỏ qua field tùy chọn mới nếu contract quy định.
- Consumer mới có thể đọc payload cũ và áp dụng default đúng.
- Type ID chưa được đăng ký bị từ chối có kiểm soát.
- Payload sai schema hoặc quá lớn không làm consumer cạn tài nguyên.
- Duplicate message không gây side effect lặp.
- Correlation ID và metadata được giữ đúng qua converter.
- Contract không chứa class name hoặc field nội bộ ngoài ý muốn.

### 11.3. Kiểm thử serialization regression

Thêm một kiểm tra regression bảo đảm đường gửi message không tạo `ObjectMessage`. Điều này đặc biệt hữu ích nếu có nhiều `JmsTemplate`, nhiều listener factory hoặc cấu hình tùy chỉnh.

Không cần cấm `ObjectMessage` trên mọi queue nếu hệ thống còn một use case nội bộ được kiểm soát và có lý do rõ ràng; nhưng từng destination tích hợp cần có contract và allowlist kiểu message được phép.

## 12. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| DTO vẫn bị gửi thành ObjectMessage | Template đang dùng SimpleMessageConverter | Cấu hình JSON converter trên đúng JmsTemplate |
| Consumer không tìm thấy class | Message chứa class name/package của producer | Dùng type ID trung lập và mapping sang DTO consumer |
| Consumer parse JSON thất bại | Hai bên không thống nhất schema hoặc encoding | Chuẩn hóa schema, content type và UTF-8 |
| Type ID không được nhận diện | Thiếu property hoặc mapping khác nhau | Thống nhất property name và type ID mapping |
| Consumer nhận body đúng nhưng listener lỗi | Listener container dùng converter khác | Cấu hình converter cho listener factory |
| Field mới làm consumer cũ lỗi | Chính sách unknown field không tương thích | Quy định forward/backward compatibility và kiểm thử |
| ObjectMessage cũ không deserialize được | Class/version không tương thích | Cô lập migration legacy, drain message hoặc dùng destination version mới |
| Deserialize gây rủi ro bảo mật | Nhận object graph không đáng tin cậy | Tránh ObjectMessage; nếu bắt buộc, filter/allowlist tại provider |
| JSON chứa dữ liệu nội bộ | Map trực tiếp domain entity sang payload | Dùng DTO contract và mapper tường minh |
| Message quá lớn | Gửi toàn bộ aggregate hoặc dữ liệu lặp | Chỉ gửi fact cần thiết, dùng ID tham chiếu khi phù hợp |
| Đổi converter nhưng không có hiệu lực | Một template/listener factory khác đang xử lý | Kiểm tra wiring và test raw JMS message |

## 13. Checklist thiết kế trước khi phát hành

- [ ] Message có DTO/schema độc lập với entity và class nội bộ.
- [ ] Producer ánh xạ domain model sang contract tại ranh giới messaging.
- [ ] Không gửi ORM proxy, persistence entity, Spring object hoặc exception object.
- [ ] Không dùng Java native serialization cho destination tích hợp.
- [ ] Chọn rõ `TextMessage`, `BytesMessage` hoặc `MapMessage` theo contract.
- [ ] JSON/Avro/Protobuf có schema và version được quản lý.
- [ ] Type ID là identifier ổn định, không phải Java fully qualified class name.
- [ ] Converter được gắn vào cả template và listener container thực tế.
- [ ] Metadata và correlation được định nghĩa rõ.
- [ ] Payload được kiểm tra schema, giới hạn kích thước và xác thực nghiệp vụ.
- [ ] Có chiến lược duplicate, retry, dead-letter và replay.
- [ ] Có kế hoạch migration cho message cũ còn trong broker.
- [ ] Test xác nhận kiểu JMS message thực tế và contract tương thích.

## 14. Tài liệu tham khảo

- [Spring Framework Reference — Sending a Message with JMS](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): `JmsTemplate`, `convertAndSend`, `MessageConverter`, `SimpleMessageConverter`, `JmsClient` và cách gửi message.
- [Spring Framework Javadoc — JacksonJsonMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/JacksonJsonMessageConverter.html): converter JSON dùng Jackson 3 trong Spring Framework 7.
- [Spring Framework 6.2 Javadoc — MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html): converter JSON Jackson 2 và type ID mapping.
- [Spring Framework Javadoc — SimpleMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html): mapping giữa Java object và các kiểu JMS message, bao gồm `Serializable` sang `ObjectMessage`.
- [Jakarta Messaging API — ObjectMessage](https://jakarta.ee/specifications/messaging/3.0/apidocs/jakarta/jms/ObjectMessage.html): contract `Serializable`, `setObject` và `getObject`.
- [Jakarta Messaging Specification — Message body](https://jakarta.ee/specifications/messaging/3.0/jakarta-messaging-spec-3.0.html): các dạng body `TextMessage`, `BytesMessage`, `MapMessage`, `StreamMessage` và `ObjectMessage`.
- [Oracle Java Serialization Filters](https://docs.oracle.com/en/java/javase/22/core/java-serialization-filters.html): `ObjectInputFilter`, JEP 290/JEP 415 và giới hạn deserialization.
- [Oracle Secure Coding Guidelines for Java SE](https://www.oracle.com/technologies/javase/seccodeguide.html): hướng dẫn bảo vệ dữ liệu serialized không đáng tin cậy.
