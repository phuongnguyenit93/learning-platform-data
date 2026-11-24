# AMQP message converter

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **AMQP message converter**, **Spring Integration transformer** và **header mapper** trong đường đi từ payload Java tới RabbitMQ và ngược lại.
- Giải thích **body**, **MessageProperties**, **contentType**, **contentEncoding**, AMQP headers và Spring MessageHeaders ảnh hưởng tới kiểu dữ liệu như thế nào.
- Chọn đúng converter cho **String**, **byte[]**, **JSON DTO** và dữ liệu từ hệ thống khác; tránh lạm dụng Java native serialization.
- Xây dựng luồng **Spring Integration AMQP outbound/inbound adapter** với hợp đồng dữ liệu đơn giản, rồi mở rộng sang JSON có version.
- Phân tích tính tương thích schema, type metadata, trusted types, dữ liệu không tin cậy, lỗi decode/deserialize và poison message.
- Thiết kế kiểm thử giữa producer và consumer, xử lý retry/DLQ/idempotency và quan sát converter trong production.

## 1. Vì sao adapter AMQP cần message converter?

Trong ứng dụng Java, nghiệp vụ thường thao tác với **OrderCreatedEvent**, **String**, **Map** hoặc **byte[]**. RabbitMQ không truyền trực tiếp tham chiếu đối tượng Java qua mạng. Một message AMQP trên wire có **body là dãy byte** và **properties/headers** mô tả nội dung, định danh và thông tin giao tiếp.

Khi Spring Integration kết nối RabbitMQ:

- **Outbound adapter** phải biểu diễn payload nội bộ thành dữ liệu mà producer AMQP có thể gửi.
- **Inbound adapter** phải biến AMQP delivery thành Spring Message có payload/headers mà handler hiểu được.
- **Gateway** phải xử lý conversion cho **cả request và reply**, trong khi vẫn giữ correlation và timeout.

~~~mermaid
flowchart LR
    D["OrderCreatedEvent / String"] --> M["Spring Message<br/>payload + headers"]
    M --> OA["AMQP outbound adapter"]
    OA --> CV1["MessageConverter<br/>toMessage"]
    CV1 --> AM["AMQP Message<br/>body bytes + properties"]
    AM --> X["RabbitMQ exchange / queue"]
    X --> CV2["MessageConverter<br/>fromMessage"]
    CV2 --> IA["AMQP inbound adapter"]
    IA --> IC["Spring MessageChannel"]
    IC --> H["Transformer / Validator<br/>Service activator"]
~~~

Đây là nội dung thuộc chương **Adapter AMQP** của module **SPRING_INTEGRATION_ADAPTERS**: việc chuyển đổi tại biên kết nối quan trọng như cách chọn inbound/outbound adapter, MessageChannel, poller/listener hoặc xử lý vòng đời. Tương tự File/SFTP/HTTP/JMS/Kafka/database, **hợp đồng message ở biên** phải được định nghĩa rõ, không chỉ cấu hình kết nối thành công.

## 2. Ba lớp message và trách nhiệm chuyển đổi

Trong một hệ thống Spring Integration + Spring AMQP thường gặp ba biểu diễn khác nhau:

| Lớp | Kiểu dữ liệu điển hình | Trách nhiệm |
| --- | --- | --- |
| **Đối tượng nghiệp vụ** | OrderCreatedEvent, OrderId, PriceQuote | Biểu diễn ý nghĩa và quy tắc của domain |
| **Spring Messaging Message** | org.springframework.messaging.Message với payload và MessageHeaders | Chuyển giao nội bộ qua MessageChannel |
| **Spring AMQP Message** | org.springframework.amqp.core.Message với body byte[] và MessageProperties | Biểu diễn thông điệp cần gửi/đã nhận từ RabbitMQ |

**Đừng nhầm hai class cùng tên Message**:

~~~java
// Spring Integration/Spring Messaging:
org.springframework.messaging.Message<String> internal;

// Spring AMQP:
org.springframework.amqp.core.Message wireMessage;
~~~

Một Spring AMQP Message có **body bytes** và properties. Spring Messaging Message có **payload có thể thuộc nhiều kiểu** và headers nội bộ. Chúng không phải hai tên gọi cho cùng một class.

### 2.1. Các khái niệm thường bị trộn lẫn

| Thành phần | Tác vụ chính | Ví dụ |
| --- | --- | --- |
| **MessageConverter (AMQP)** | Java object ↔ AMQP Message | String → UTF-8 bytes; JSON bytes → DTO |
| **Transformer (Spring Integration)** | Spring Message/payload này → message/payload khác theo flow | CSV String → OrderEvent; OrderEvent → JSON text |
| **Header mapper** | Chọn và ánh xạ metadata giữa header nội bộ với properties/headers giao thức | Correlation ID, custom eventId |
| **Serializer/Deserializer** | Chuyển dữ liệu sang/từ wire format cụ thể | Jackson JSON, Avro, Protobuf |
| **Validator** | Kiểm tra hợp đồng và quy tắc nghiệp vụ | orderId bắt buộc, totalVnd > 0 |

Converter có thể sử dụng serializer bên trong nhưng **không thay thế validation nghiệp vụ**. Một JSON parse thành công vẫn có thể chứa orderId rỗng hoặc tổng tiền âm.

### 2.2. Đường đi outbound và inbound

~~~mermaid
sequenceDiagram
    participant S as Business Service
    participant C as MessageChannel
    participant O as Outbound Adapter
    participant V as AMQP MessageConverter
    participant B as RabbitMQ
    participant I as Inbound Adapter
    participant H as Handler
    S->>C: Spring Message<OrderCreated>
    C->>O: Chuyển message
    O->>V: toMessage(payload)
    V-->>O: AMQP body + properties
    O->>B: Publish
    B-->>I: Delivery từ queue
    I->>V: fromMessage(AMQP message)
    V-->>I: Java payload
    I->>H: Spring Message<payload>
~~~

Sơ đồ thể hiện trách nhiệm **logic**. Converter cụ thể ở producer và consumer có thể là **hai bean khác nhau**, cùng áp dụng một hợp đồng wire format, chứ không nhất thiết là cùng một instance.

## 3. MessageProperties quan trọng không kém body

Một AMQP message không chỉ có bytes. Properties giúp phía nhận hiểu cách diễn giải dữ liệu:

~~~text
AMQP Message
├── body: byte[]
└── MessageProperties
    ├── contentType: text/plain | application/json | ...
    ├── contentEncoding: UTF-8 | ...
    ├── messageId / correlationId
    ├── deliveryMode: persistent | non-persistent
    ├── application headers
    └── metadata khác tùy publisher/consumer
~~~

| Property | Ảnh hưởng đến chuyển đổi | Lưu ý |
| --- | --- | --- |
| **contentType** | Gợi ý chọn converter hoặc cách decode | Khai JSON không tự chứng minh body là JSON hợp lệ |
| **contentEncoding** | Charset/compression tùy hợp đồng | Sai charset có thể làm hỏng ký tự tiếng Việt |
| **headers** | Metadata ứng dụng hoặc type mapping | Chỉ tin các header được phép |
| **messageId** | Truy vết một bản tin | Có thể vắng mặt; không mặc nhiên là eventId |
| **correlationId** | Ghép request–reply/tracing | Không tự là idempotency key |
| **deliveryMode** | Hành vi lưu bền ở broker theo policy | Không quyết định DTO class |
| **receivedRoutingKey** | Metadata nhận được từ broker khi consumer đọc | Không thay thế validation payload |

**Exchange và routing key quyết định route**; converter quyết định **cách biểu diễn body và properties**. Một bản JSON hợp lệ vẫn có thể không tới queue nào nếu binding không khớp. Ngược lại, message đã tới queue đúng vẫn có thể bị consumer từ chối vì sai schema.

### 3.1. Content type không phải Java class

**application/json** cho biết định dạng JSON. Nó **không tự nói** JSON đó biểu diễn OrderCreatedEvent phiên bản nào, thuộc package Java nào, hay có an toàn để instantiate một class tùy ý không.

Hợp đồng ổn định thường cần ít nhất **eventType**, **schemaVersion** và schema của payload. Java class name không nên là chuẩn giao tiếp bắt buộc giữa các nhóm ngôn ngữ khác nhau.

### 3.2. Charset cần chốt ở hai phía

Ví dụ chuỗi **Đơn hàng đã tạo** khi chuyển thành bytes UTF-8 cần được consumer đọc lại bằng UTF-8. Nếu producer đặt contentEncoding sai hoặc consumer tự dùng charset hệ điều hành, kết quả có thể bị lỗi ký tự.

Với JSON, UTF-8 là lựa chọn thông dụng và phù hợp với ecosystem hiện đại. Với text/plain hoặc CSV, hãy ghi rõ charset trong hợp đồng; không giả định default của hệ thống ngoài trùng với default JVM.

## 4. SimpleMessageConverter: lựa chọn cơ bản

Spring AMQP có **SimpleMessageConverter** để xử lý một số kiểu dữ liệu phổ biến:

| Dữ liệu Java khi gửi | Biểu diễn thường gặp | Khi nhận lại |
| --- | --- | --- |
| **String** | Body bytes dạng text và content type text/plain | Có thể được chuyển thành String theo charset |
| **byte[]** | Body nhị phân | Có thể giữ byte[] |
| **Serializable object** | Java native serialized object khi dùng nhánh serialization hỗ trợ | Chỉ nên deserialize khi có cơ chế trust/giới hạn rất chặt |
| **application/json nhưng converter vẫn là Simple** | Body bytes JSON từ producer khác | Không nên giả định Simple tự map JSON thành DTO |

**SimpleMessageConverter không phải JSON DTO converter.** Nó có thể xử lý text hoặc bytes, nhưng nếu consumer cần đối tượng domain từ JSON, phải có converter JSON phù hợp hoặc bước transformer parse JSON bên trong flow.

### 4.1. Gửi String bằng RabbitTemplate

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class TextEventPublisher {
    private final RabbitTemplate rabbitTemplate;

    public TextEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish() {
        rabbitTemplate.convertAndSend(
            "orders.events",
            "orders.created",
            "evt-1001|O-1001|150000");
    }
}
~~~

Với **SimpleMessageConverter** mặc định phù hợp, String được mã hóa thành body bytes và message properties dạng text. Bên nhận sử dụng converter tương thích có thể nhận String. Trong production, hãy kiểm tra **contentType/contentEncoding thực tế** bằng test với broker, không chỉ suy đoán từ Java type.

### 4.2. Gửi AMQP Message đã dựng sẵn

Khi muốn kiểm soát body/properties rõ ràng, dùng RabbitTemplate.send:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class RawAmqpPublisher {
    private final RabbitTemplate rabbitTemplate;

    public RawAmqpPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishText() {
        MessageProperties props = new MessageProperties();
        props.setContentType(MessageProperties.CONTENT_TYPE_TEXT_PLAIN);
        props.setContentEncoding(StandardCharsets.UTF_8.name());
        props.setHeader("schemaVersion", 1);

        byte[] bytes = "evt-1002|O-1002|200000"
            .getBytes(StandardCharsets.UTF_8);

        Message amqp = new Message(bytes, props);
        rabbitTemplate.send(
            "orders.events", "orders.created", amqp);
    }
}
~~~

Đây là **Spring AMQP Message**, không phải Spring Integration Message. Cần lưu ý header ứng dụng schemaVersion đã được đặt trực tiếp vào AMQP properties; việc đặt Spring Message header tương tự trong một outbound flow không nhất thiết tự ánh xạ y hệt nếu header mapper cấu hình khác.

### 4.3. Tại sao nên tránh Java native serialization?

Java serialization thường ràng buộc hai phía vào class/package/version Java và có rủi ro khi deserialize dữ liệu không tin cậy. Ngay cả khi converter hỗ trợ Serializable, không nên dùng định dạng này để giao tiếp mở qua broker với nhiều ứng dụng không cùng kiểm soát.

Nên ưu tiên **JSON, Avro hoặc Protobuf** với schema có version; cấu hình type whitelist/trust rõ ràng và giới hạn kích thước trước khi tạo đối tượng. Không cấu hình tin cậy mọi package chỉ để hết lỗi deserialize trong production.

## 5. JSON message converter và dữ liệu DTO

Khi producer phát đối tượng OrderCreatedEvent, consumer muốn nhận DTO Java có kiểm soát thay vì parse một chuỗi thủ công. Spring AMQP có các converter tích hợp Jackson, nhưng **tên class/API thay đổi theo thế hệ thư viện**. Ví dụ ở những dự án sử dụng **Spring AMQP 3.x + Jackson 2**, có thể dùng **Jackson2JsonMessageConverter**. Khi nâng lên thế hệ Spring AMQP/Jackson mới, phải chọn converter tương ứng của phiên bản và kiểm thử di trú.

### 5.1. Hợp đồng domain minh họa

~~~java
package com.example.contract;

public record OrderCreatedEvent(
    String eventId,
    String orderId,
    long totalVnd,
    int schemaVersion
) {}
~~~

Wire format mong muốn:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "O-1001",
  "totalVnd": 150000,
  "schemaVersion": 1
}
~~~

**Một DTO parse thành công chưa bảo đảm dữ liệu hợp lệ.** Handler vẫn cần kiểm tra eventId không rỗng, orderId đúng mẫu, totalVnd dương, schemaVersion được hỗ trợ và quyền xử lý đơn hàng.

### 5.2. Cấu hình JSON converter cho RabbitTemplate (Spring AMQP 3.x)

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JsonAmqpProducerConfiguration {

    @Bean("jsonRabbitTemplate")
    public RabbitTemplate jsonRabbitTemplate(
            ConnectionFactory connectionFactory) {

        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(
            new Jackson2JsonMessageConverter());
        return template;
    }
}
~~~

Ví dụ gửi:

~~~java
OrderCreatedEvent event =
    new OrderCreatedEvent("evt-1001", "O-1001", 150000, 1);

jsonRabbitTemplate.convertAndSend(
    "orders.events", "orders.created", event);
~~~

Với Jackson JSON converter, body thường chứa JSON và content type phù hợp. Converter có thể thêm **type metadata headers** để Java consumer xác định kiểu đích. **Không nên coi các type header này là dữ liệu đáng tin vô điều kiện** hoặc biến tên class/package thành wire contract giữa các tổ chức.

Mã trong mục này **được gắn phạm vi Spring AMQP 3.x**. API converter cho thế hệ thư viện khác cần được thay theo tài liệu của phiên bản tương ứng; không kết hợp class import cũ với thư viện đã loại bỏ nó.

### 5.3. Vì sao sender và receiver phải thống nhất?

Nếu sender dùng JSON converter còn receiver vẫn dùng SimpleMessageConverter, một AMQP message có contentType application/json có thể được receiver nhìn thấy như **byte[]**, không phải OrderCreatedEvent. Nếu sender dùng Java serialization nhưng receiver chỉ hiểu JSON, kết quả không thể decode đúng bằng việc đổi routing key.

Có ba lựa chọn tương đối phổ biến:

1. **Dùng JSON converter tương thích ở cả producer và consumer**, có chính sách type mapping/trust được kiểm soát.
2. **Nhận bytes hoặc String tại biên**, sau đó transformer trong Spring Integration parse thành DTO theo schema đã xác định.
3. **Dùng schema-based format khác** như Avro/Protobuf, với serializer/deserializer tương ứng và quản lý schema version.

Lựa chọn thứ hai thường hữu ích nếu muốn tách **wire format** khỏi **class name** của producer, đặc biệt khi các ứng dụng thuộc nhiều nhóm hoặc ngôn ngữ khác nhau.

## 6. Type metadata và trusted types

Một số JSON converter của Spring AMQP có thể phát metadata về kiểu Java, chẳng hạn những header quy ước như **__TypeId__**, **__ContentTypeId__** hoặc **__KeyTypeId__**, tùy converter, kiểu payload và cấu hình.

| Metadata | Có thể giúp gì? | Nguy cơ |
| --- | --- | --- |
| **__TypeId__** | Gợi ý kiểu đối tượng cho converter | Producer không tin cậy có thể yêu cầu kiểu ngoài hợp đồng |
| **__ContentTypeId__ / __KeyTypeId__** | Gợi ý kiểu nội dung collection/map | Type mapping không thống nhất giữa hai ứng dụng |
| **contentType = application/json** | Xác định định dạng JSON | Không tự xác định domain type/version |
| **eventType/schemaVersion** | Chọn schema nghiệp vụ ổn định | Phải validation và duy trì compatibility |

### 6.1. Không tin class name từ message ngoài

Không bao giờ cấu hình **trust all packages** một cách vô điều kiện chỉ vì consumer gặp lỗi chuyển JSON sang DTO. Với dữ liệu từ đối tác hoặc các ứng dụng khác, nên:

- Chỉ cho phép các DTO đã được định nghĩa trong **contract package** tin cậy.
- Dùng **type ID mapping** cố định hoặc **target type** được ứng dụng chọn, nếu converter hỗ trợ.
- Validate schemaVersion, eventType và các trường bắt buộc.
- Giới hạn message size và độ sâu nested JSON khi cần.
- Không deserialize Java native object từ nguồn không tin cậy.

### 6.2. Class name không phải hợp đồng liên dịch vụ

Nếu producer Java package **com.shop.events.OrderCreatedEvent** đổi thành **com.shop.contract.OrderCreated**, consumer không nên bị buộc phải đổi chỉ vì tên class nội bộ của producer thay đổi. Một hợp đồng tốt giữ được:

~~~text
eventType = "ORDER_CREATED"
schemaVersion = 1
payload = JSON theo schema công khai nội bộ
~~~

Sau đó consumer tự ánh xạ vào model của mình. Với converters dùng type headers, cần kiểm tra type mapping/trust và tương thích của hai phía khi triển khai từng dịch vụ không đồng thời.

## 7. Transformer và converter trong IntegrationFlow

Một mô hình dễ kiểm thử là tách ba bước:

1. **Adapter + converter:** xử lý giao thức AMQP, đưa payload vào flow.
2. **Transformer:** chuẩn hóa payload thành hợp đồng domain, chuyển đổi schema khi cần.
3. **Service activator:** validate và thực hiện business logic.

~~~mermaid
flowchart LR
    B["AMQP Message<br/>body/properties"] --> A["AMQP inbound adapter<br/>converter"]
    A --> C["rawEvents channel"]
    C --> T["Transformer<br/>decode / normalize"]
    T --> H["Service activator<br/>validate + process"]
    H --> DB[("Database")]
~~~

Ví dụ:

- Consumer chọn nhận **String JSON** tại biên.
- Transformer dùng Jackson ObjectMapper để parse thành OrderCreatedEvent.
- Handler kiểm tra eventId/totalVnd và thực hiện transaction.
- ACK chỉ xảy ra sau ranh giới hoàn tất đã thiết kế; nếu chuyển sang thread async cần xem lại điểm ACK.

**Converter và transformer có thể trùng một phần khả năng kỹ thuật nhưng không trùng trách nhiệm kiến trúc.** Converter nên tập trung vào wire format/AMQP properties; transformer thực hiện đổi model theo hợp đồng của flow.

### 7.1. Tránh double serialization

Nếu một transformer đã tạo **String JSON** và RabbitTemplate lại sử dụng JSON converter được cấu hình để chuyển String thành **JSON string literal**, consumer có thể nhận một chuỗi chứa dấu nháy/escape thay vì object JSON mong muốn.

Khi thiết kế, hãy chọn **một nơi chịu trách nhiệm serialize JSON** và kiểm tra **raw body bytes** thực sự trên broker, không chỉ Java object đầu vào.

### 7.2. Khi nào giữ byte[]?

Nếu hệ thống gửi Avro/Protobuf, compressed data hoặc định dạng nhị phân khác, giữ **byte[]** ở adapter rồi dùng transformer/deserializer chuyên biệt có thể rõ ràng hơn việc ép tất cả thành String. Với payload lớn, cần giới hạn kích thước và cân nhắc mô hình tham chiếu tới object storage thay vì dồn toàn bộ dữ liệu vào broker message.

## 8. Chuẩn bị ví dụ thực hành Spring Integration

Ta xây dựng một luồng **một chiều** có producer và consumer giao tiếp qua RabbitMQ. Để kiểm tra chính xác conversion, trước tiên dùng **String text/plain** với SimpleMessageConverter, sau đó thiết kế phương án JSON.

Topology:

~~~text
Exchange:       orders.events           (direct)
Routing key:    orders.created
Queue:          orders.created.q        (durable)
Payload text:   evt-1001|O-1001|150000
Charset:        UTF-8
~~~

~~~mermaid
flowchart LR
    B["OrderPublisher"] --> C1["ordersOutbound<br/>DirectChannel"]
    C1 --> OA["AMQP outbound adapter"]
    OA --> R["RabbitTemplate<br/>SimpleMessageConverter"]
    R --> X["RabbitMQ<br/>orders.events"]
    X --> Q["orders.created.q"]
    Q --> IA["AMQP inbound adapter<br/>MessageConverter"]
    IA --> C2["ordersInbound<br/>DirectChannel"]
    C2 --> TR["Transformer<br/>String → OrderEvent"]
    TR --> H["OrderService"]
~~~

### 8.1. Dependency Maven

Với Spring Boot và dependency management phù hợp:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-amqp</artifactId>
    </dependency>
</dependencies>
~~~

Sử dụng BOM của Spring Boot để có những phiên bản Spring AMQP/Spring Integration tương thích. Ví dụ dùng record Java nên thích hợp với Java 17 trở lên. Chạy RabbitMQ test với ConnectionFactory đã cấu hình host, port, virtual host và credentials; không hardcode thông tin đăng nhập thật trong source.

### 8.2. Khai báo exchange, queue và binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersRabbitTopology {

    public static final String EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "orders.created";
    public static final String QUEUE = "orders.created.q";

    @Bean
    public DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersQueue() {
        return new Queue(QUEUE, true);
    }

    @Bean
    public Binding ordersBinding(
            Queue ordersQueue, DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
            .to(ordersExchange)
            .with(ROUTING_KEY);
    }
}
~~~

**Bean declaration không đồng nghĩa RabbitMQ đã có topology.** Cần RabbitAdmin/AmqpAdmin được bật, có connection và quyền khai báo, hoặc hệ thống vận hành provision exchange/queue/binding trước. Queue durable không tự bảo đảm publisher đã chọn persistent delivery mode hoặc business consumer đã hoàn tất.

### 8.3. MessageConverter của ví dụ

Ví dụ text này được thiết kế để dùng **SimpleMessageConverter** cho cả đường gửi và nhận. Nếu ứng dụng tùy chỉnh RabbitTemplate hay inbound adapter sang JSON converter thì phải điều chỉnh cấu hình tương ứng; không thể giữ giả định inbound payload luôn là String.

Trong ứng dụng chỉ có cấu hình mặc định Spring Boot phù hợp, RabbitTemplate thường dùng converter cơ bản cho String. Khi muốn rõ ràng hơn, có thể khai báo template dùng SimpleMessageConverter:

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.SimpleMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TextRabbitTemplateConfiguration {

    @Bean("textRabbitTemplate")
    public RabbitTemplate textRabbitTemplate(
            ConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(new SimpleMessageConverter());
        return template;
    }
}
~~~

**Quy tắc triển khai:** Nếu cùng ứng dụng có template JSON và text, inject theo **@Qualifier** để không mơ hồ. Các ví dụ text và JSON sau đây là **những phương án cấu hình**, không phải yêu cầu tạo nhiều RabbitTemplate beans rồi inject không có qualifier.

## 9. Java DSL: outbound adapter và inbound adapter với String

### 9.1. Outbound IntegrationFlow

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class TextOrdersOutboundConfiguration {

    @Bean
    public MessageChannel ordersOutbound() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow ordersOutboundFlow(
            @Qualifier("textRabbitTemplate")
            RabbitTemplate rabbitTemplate) {
        return IntegrationFlow.from("ordersOutbound")
            .handle(Amqp.outboundAdapter(rabbitTemplate)
                .exchangeName(OrdersRabbitTopology.EXCHANGE)
                .routingKey(OrdersRabbitTopology.ROUTING_KEY))
            .get();
    }
}
~~~

**ordersOutbound** là tên channel nội bộ, không phải RabbitMQ queue. Outbound adapter nhận Spring Message rồi sử dụng hạ tầng AMQP để publish tới exchange và routing key đã khai báo.

### 9.2. Producer gửi Spring Message

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrdersChannelPublisher {

    private final MessageChannel ordersOutbound;

    public OrdersChannelPublisher(
            @Qualifier("ordersOutbound") MessageChannel ordersOutbound) {
        this.ordersOutbound = ordersOutbound;
    }

    public void publish(String eventId, String orderId, long totalVnd) {
        if (eventId == null || !eventId.matches("[A-Za-z0-9_-]{1,80}")
                || orderId == null
                || !orderId.matches("[A-Za-z0-9_-]{1,80}")
                || totalVnd <= 0) {
            throw new IllegalArgumentException(
                "OrderCreated khong hop le");
        }

        String body = eventId + "|" + orderId + "|" + totalVnd;
        boolean accepted = ordersOutbound.send(
            MessageBuilder.withPayload(body)
                .setHeader("eventId", eventId)
                .build());

        if (!accepted) {
            throw new IllegalStateException(
                "Khong gui duoc message vao channel");
        }
    }
}
~~~

Với input **evt-1001**, **O-1001**, **150000**, payload là:

~~~text
evt-1001|O-1001|150000
~~~

**eventId được đưa vào body** để consumer nhận diện được mà không lệ thuộc header mapper. Header Spring Integration **eventId** là metadata nội bộ; nếu muốn chuyển thành AMQP application header cần cấu hình và kiểm thử mapping. Trong sản phẩm thật, hãy thay định dạng phân cách chuỗi bằng JSON/schema có version.

### 9.3. Parse payload và validate domain

Mô hình domain của ví dụ:

~~~java
public record OrderEvent(
    String eventId,
    String orderId,
    long totalVnd
) {}
~~~

Transformer parser:

~~~java
public final class OrderTextParser {

    private OrderTextParser() {}

    public static OrderEvent parse(String body) {
        if (body == null || body.length() > 1024) {
            throw new IllegalArgumentException(
                "Payload rong hoac qua lon");
        }

        String[] fields = body.split("\\|", -1);
        if (fields.length != 3
                || !fields[0].matches("[A-Za-z0-9_-]{1,80}")
                || !fields[1].matches("[A-Za-z0-9_-]{1,80}")) {
            throw new IllegalArgumentException(
                "Sai hop dong eventId|orderId|totalVnd");
        }

        final long total;
        try {
            total = Long.parseLong(fields[2]);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                "totalVnd khong phai so hop le", ex);
        }
        if (total <= 0) {
            throw new IllegalArgumentException(
                "totalVnd phai duong");
        }
        return new OrderEvent(fields[0], fields[1], total);
    }
}
~~~

**Transformer** chuyển String thành OrderEvent và áp dụng một phần validation. Converter AMQP trước đó chỉ cần cho handler một String tương thích. Với format JSON thực tế, dùng Jackson/JSON Schema validation thay vì split chuỗi; dấu phân cách có thể xuất hiện trong dữ liệu đầu vào.

### 9.4. Inbound IntegrationFlow

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class TextOrdersInboundConfiguration {

    @Bean
    public MessageChannel rawOrders() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow ordersInboundFlow(
            ConnectionFactory connectionFactory) {
        return IntegrationFlow
            .from(Amqp.inboundAdapter(
                connectionFactory, OrdersRabbitTopology.QUEUE))
            .channel("rawOrders")
            .transform(String.class, OrderTextParser::parse)
            .handle(OrderEvent.class, (event, headers) -> {
                System.out.println(
                    "Received event " + event.eventId()
                        + " for order " + event.orderId());
                return null; // One-way inbound adapter.
            })
            .get();
    }
}
~~~

Trong ví dụ, AMQP inbound adapter phải dùng converter phù hợp để cung cấp **String** cho transformer. Với Spring AMQP SimpleMessageConverter và message text/plain phát từ producer minh họa, đây là kết quả mong đợi. Nếu converter nhận bytes hoặc DTO, phải đổi bước transform cho đúng; không nên ép mọi payload thành String một cách mù quáng.

**DirectChannel giữ chuỗi xử lý đồng bộ.** Nếu business handler thực tế ném exception và exception lan tới listener container, ACK/NACK có thể phụ thuộc vào kết quả callback, acknowledge mode và error handler của container. Nếu thay bằng ExecutorChannel, điểm ACK và xử lý lỗi thay đổi đáng kể.

### 9.5. Kết quả mong đợi và giới hạn

1. Broker có exchange **orders.events**, queue **orders.created.q** và binding **orders.created**.
2. Gọi OrdersChannelPublisher.publish với dữ liệu hợp lệ.
3. Consumer nhận text/plain dưới dạng String; transformer tạo OrderEvent.
4. Handler in đúng eventId/orderId.
5. Dữ liệu sai hợp đồng khiến transformer ném lỗi; **không thử vô hạn trên queue production** khi chưa có retry/requeue/DLQ.

Mã demo **chỉ in log**, chưa ghi database hay idempotency store. Nó không chứng minh một nghiệp vụ đã commit hoặc AMQP delivery đã được xử lý đúng một lần.

## 10. Mở rộng JSON: những điều cần cấu hình đồng bộ

Ví dụ JSON ở mục 5 dùng **Jackson2JsonMessageConverter** cho RabbitTemplate (phạm vi Spring AMQP 3.x). Khi bổ sung consumer Spring Integration, cần quyết định rõ **phần nào parse JSON**:

| Thiết kế | Payload sau inbound adapter | Điểm chịu trách nhiệm parse JSON |
| --- | --- | --- |
| Inbound adapter được cấu hình JSON converter thích hợp | OrderCreatedEvent hoặc kiểu đích theo mapping | Converter ở biên AMQP |
| Inbound dùng SimpleMessageConverter nhận application/json | Thường có thể là byte[] | Transformer JSON của IntegrationFlow |
| Inbound đọc bytes từ converter nhị phân | byte[] | Deserializer riêng theo schema |
| Inbound nhận JSON String đã giải mã đúng charset | String | Transformer ObjectMapper |

Không kết luận một cách máy móc rằng Spring Integration inbound adapter **tự động dùng converter của một RabbitTemplate bean khác**. Adapter và listener/container có cấu hình conversion riêng theo cách tạo endpoint. Muốn kiểm soát kiểu payload, phải nhìn cấu hình endpoint **đang dùng thực sự**.

### 10.1. JSON transformer nhận bytes khi biên giữ dữ liệu thô

Với các message JSON được đưa vào flow dưới dạng byte[], có thể parse theo **target type cố định**:

~~~java
import java.io.IOException;

import com.fasterxml.jackson.databind.ObjectMapper;

public final class OrderJsonDecoder {

    private final ObjectMapper objectMapper;

    public OrderJsonDecoder(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public OrderCreatedEvent decode(byte[] bytes) {
        if (bytes == null || bytes.length == 0
                || bytes.length > 64 * 1024) {
            throw new IllegalArgumentException(
                "JSON rong hoac vuot gioi han");
        }

        try {
            OrderCreatedEvent event = objectMapper.readValue(
                bytes, OrderCreatedEvent.class);

            if (event.eventId() == null || event.eventId().isBlank()
                    || event.orderId() == null
                    || event.orderId().isBlank()
                    || event.totalVnd() <= 0
                    || event.schemaVersion() != 1) {
                throw new IllegalArgumentException(
                    "OrderCreatedEvent khong hop dong");
            }
            return event;
        } catch (IOException ex) {
            throw new IllegalArgumentException(
                "Khong giai ma duoc JSON OrderCreatedEvent", ex);
        }
    }
}
~~~

Trong ví dụ này, **OrderCreatedEvent.class là kiểu đích do consumer chọn**, không lấy tên class tùy ý từ AMQP header. Dù dùng target type cố định, vẫn cần giới hạn kích thước/depth và validation nghiệp vụ.

### 10.2. Điểm đặt transformer trong DSL

Nếu inbound endpoint đã được kiểm chứng phát **byte[]**, có thể thêm:

~~~java
// Minh hoa mot doan trong IntegrationFlow sau AMQP inbound.
.transform(byte[].class, jsonDecoder::decode)
.handle(OrderCreatedEvent.class, (event, headers) -> {
    orderService.accept(event);
    return null;
})
~~~

Đây là **đoạn DSL**, không phải toàn bộ một Java class. Nếu endpoint đã dùng JSON converter và phát OrderCreatedEvent thì **không thêm bước transform byte[]** nữa. Một IntegrationFlow có thể bao gồm nhiều transformer, nhưng mỗi bước phải rõ input/output type và trách nhiệm.

### 10.3. Converter khi xử lý reply của gateway

Với AMQP gateway request–reply, conversion áp dụng cho **cả hai chiều**:

~~~mermaid
flowchart LR
    C["Caller DTO"] --> P["Request converter"]
    P --> Q["Request queue"]
    Q --> IG["AMQP inbound gateway"]
    IG --> S["Service activator"]
    S --> RG["Reply Message"]
    RG --> RC["Reply converter"]
    RC --> D["Reply destination"]
    D --> CC["Caller decode"]
~~~

Caller có thể gửi JSON request nhưng cần JSON reply thuộc schema khác. Hãy kiểm tra contentType, schemaVersion, correlation/reply-to, timeout và type mapping cho **cả request và response**. **Publisher confirm không phải business reply**.

## 11. Lỗi conversion có thể xảy ra ở đâu?

Lỗi chuyển đổi cần phân loại theo thời điểm; một lỗi converter phía nhận có thể xảy ra **trước khi service activator được gọi**.

| Giai đoạn | Lỗi ví dụ | Điều cần xử lý |
| --- | --- | --- |
| **Producer: domain → body** | Object không serialize được | Không publish; lưu trạng thái lỗi và sửa payload/schema |
| **Producer: headers/properties** | Header chứa kiểu không hỗ trợ hoặc không hợp lệ | Chỉ map header cần thiết; không chuyển object hạ tầng |
| **Broker routing** | Exchange không tồn tại hoặc binding không khớp | Publisher error/returns; không phải lỗi parse |
| **Consumer: body → payload** | contentType sai, JSON lỗi, type không tin cậy | Listener error policy, reject/requeue/DLQ |
| **Transformer: payload → domain** | SchemaVersion không hỗ trợ, field thiếu | Cách ly hoặc phản hồi lỗi nghiệp vụ phù hợp |
| **Service activator** | DB/HTTP downstream thất bại | Retry/backoff, ACK và idempotency |
| **Gateway: reply conversion** | Reply DTO không serialize được | Caller timeout hoặc reply error theo cấu hình; cần log/alert |

### 11.1. Lỗi converter trước khi có Spring Message

Nếu AMQP inbound converter thất bại trước khi tạo được Spring Integration Message, **errorChannel nội bộ của flow có thể không nhận một message bình thường theo cách handler lỗi downstream nhận được**. Error handler của Spring AMQP listener container và advice/retry policy có vai trò quan trọng.

Đừng chỉ viết:

~~~text
try {
    businessHandler(message);
} catch (Exception e) {
    ...
}
~~~

rồi kỳ vọng bắt được lỗi khi Jackson không thể deserialize **trước thời điểm handler được gọi**. Phải test tại **container boundary**.

### 11.2. Lỗi cố định hay lỗi tạm thời?

**Lỗi cố định** thường gồm:

- Payload JSON sai cú pháp, không thể parse.
- SchemaVersion không được hỗ trợ.
- Kiểu object/type metadata không được phép.
- Dữ liệu quá kích thước hoặc bắt buộc thiếu trường.
- Content type không thuộc danh sách được chấp nhận.

**Lỗi tạm thời** thường gồm broker mất kết nối, database timeout, HTTP downstream quá tải; nhưng ngay cả lỗi hạ tầng cũng cần retry có giới hạn và nhận diện trạng thái không rõ.

Retry một message **sai JSON** 1.000 lần thường không giúp dữ liệu trở thành hợp lệ. Ngược lại, reject không requeue ngay một message gặp lỗi database thoáng qua có thể làm gián đoạn nghiệp vụ. Cần phân loại trước khi quyết định.

## 12. ACK/requeue/DLQ và mối liên hệ với converter

Khi AMQP inbound listener xử lý một delivery:

~~~mermaid
flowchart TD
    Q["RabbitMQ queue"] --> CV{"AMQP converter"}
    CV -->|"Sai định dạng/type"| BAD["Lỗi conversion"]
    CV -->|"Hợp lệ"| T{"Transformer + Validator"}
    T -->|"Sai schema/nghiệp vụ"| BIZ["Cách ly / reply lỗi theo policy"]
    T -->|"Hợp lệ"| H["Business handler"]
    H -->|"Thành công"| ACK["ACK theo container"]
    H -->|"Lỗi tạm thời"| RET["Retry hữu hạn + backoff"]
    BAD --> DL["Reject không requeue / DLQ<br/>nếu policy phù hợp"]
    BIZ --> DL
    RET --> H
~~~

**ACK/NACK** thuộc consumer/listener và có thể bị ảnh hưởng bởi:

- **AcknowledgeMode.AUTO/MANUAL/NONE**.
- Container error handler và exception classification.
- Retry advice, transaction và cách exception lan truyền.
- Error channel hoặc bất đồng bộ qua ExecutorChannel.
- Cấu hình dead-letter exchange/queue trên RabbitMQ.

### 12.1. Poison message

Giả sử producer gửi body không phải JSON nhưng contentType lại là application/json. Consumer cố parse thành DTO và lỗi mọi lần nhận. Nếu exception luôn dẫn tới requeue ngay, RabbitMQ có thể liên tục giao một poison message, tăng CPU, redelivery và log.

Một phương án:

1. Giới hạn retry của lỗi được xem là tạm thời.
2. Với lỗi format/schema cố định, reject không requeue.
3. Nếu queue được cấu hình DLX và DLQ đúng, cô lập message lỗi.
4. Ghi metadata an toàn: eventId (nếu lấy được), contentType, nguồn, loại lỗi, thời điểm.
5. Có công cụ sửa dữ liệu và replay có kiểm soát.

**DLQ không tự xuất hiện chỉ vì converter ném exception.** Phải cấu hình DLX, routing key, queue/binding và broker policy. Khi lỗi xảy ra ngay trong producer trước publish, DLQ của consumer không cứu được bản tin chưa vào queue; cần nguồn lưu bền khác như outbox.

### 12.2. Đừng ACK quá sớm sau conversion

Một message parse JSON thành DTO thành công không có nghĩa transaction business đã commit. Với **DirectChannel**, handler đồng bộ có thể để exception lan ngược tới listener; với **ExecutorChannel**, producer của channel có thể return trước khi handler chạy và listener có thể ACK sớm.

Nếu hệ thống chọn ACK khi DTO mới được lưu vào **inbox/queue nội bộ bền vững**, phải định nghĩa rõ điểm lưu bền và cách replay. Không dựa vào QueueChannel trong bộ nhớ để bảo đảm dữ liệu không mất sau crash.

### 12.3. Chống trùng sau redelivery

Khi consumer đã ghi DB thành công nhưng chết trước ACK, broker có thể giao lại cùng AMQP message. Converter có thể tạo **một Java object mới** ở lần nhận thứ hai; object instance khác nhau không có nghĩa đó là event nghiệp vụ mới.

Dùng **eventId ổn định** với unique constraint hoặc inbox table, lưu trong transaction nghiệp vụ khi có thể. Không dựa vào Java object identity, MessageHeaders.ID hoặc chỉ vào AMQP redelivered flag để chống trùng.

## 13. Schema evolution và tương thích giữa các phiên bản

Converter JSON chỉ giải quyết việc biến bytes thành dữ liệu Java. Một hệ thống phát sự kiện trong nhiều năm cần quản lý **schema evolution** để producer và consumer có thể được triển khai không đồng thời.

### 13.1. Hợp đồng sự kiện đề xuất

~~~json
{
  "eventId": "evt-1001",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T02:00:00Z",
  "data": {
    "orderId": "O-1001",
    "totalVnd": 150000
  }
}
~~~

Ví dụ này có **envelope** gồm định danh/type/version/time và **data** nghiệp vụ. Cần thống nhất thời điểm UTC, đơn vị tiền (VND), quy tắc số nguyên, độ chính xác, nullability và kích thước tối đa với tất cả consumer.

**Java DTO và schema ngoài không đồng nhất.** Producer có thể đổi package/class nhưng giữ schemaVersion 1 nếu wire contract thực sự không đổi. Ngược lại, nếu đổi ý nghĩa của totalVnd hoặc bỏ trường bắt buộc, cần đánh giá tương thích và có thể tăng schemaVersion.

### 13.2. Ma trận thay đổi schema

| Thay đổi | Rủi ro | Cách triển khai an toàn hơn |
| --- | --- | --- |
| Thêm trường tùy chọn | Consumer cũ có thể từ chối unknown field nếu cấu hình chặt | Kiểm thử consumer cũ, bổ sung default hợp lý |
| Thêm trường bắt buộc | Consumer/producer cũ không cung cấp được | Tạo phiên bản contract hoặc giai đoạn chuyển tiếp |
| Đổi tên trường | Consumer cũ có thể mất dữ liệu cần thiết | Duy trì alias/migration rõ ràng |
| Đổi kiểu từ number sang String | Mapper có thể thất bại hoặc âm thầm ép kiểu | Coi là breaking change nếu không chứng minh tương thích |
| Đổi đơn vị tiền | Dữ liệu vẫn parse thành công nhưng nghiệp vụ sai | Đổi schema version và ghi rõ đơn vị |
| Đổi eventType/routing key | Consumer có thể không nhận message | Phối hợp exchange/binding và contract cùng lúc |
| Đổi Java package khi có __TypeId__ | Converter consumer phụ thuộc type header có thể lỗi | Mapping type ID ổn định hoặc chọn target DTO nội bộ |

**Unknown fields:** Có consumer cấu hình bỏ qua field lạ; có consumer từ chối. Không tự cho rằng Jackson hoặc bất kỳ JSON converter nào mặc định xử lý như nhau trong mọi phiên bản/cấu hình.

### 13.3. Versioning không nên chỉ dựa vào routing key

Routing key như **orders.created** mô tả hướng gửi sự kiện trên RabbitMQ. Consumer có thể cần schemaVersion để biết cách parse body. Có thể đặt event type/version trong payload hoặc application headers, nhưng quy tắc phải rõ và kiểm thử được qua cả producer/consumer.

Nếu đổi routing key thành **orders.created.v2**, cần bảo đảm binding tồn tại, consumer đăng ký đúng và tính tương thích được quản lý. Chỉ thêm chuỗi v2 vào routing key không tự làm schema JSON tương thích.

## 14. Kiểm thử converter không cần broker và kiểm thử tích hợp với broker

Kiểm thử tốt cần tách:

1. **Converter unit test:** object → AMQP body/properties → object, không cần broker.
2. **Contract test:** raw bytes/contentType/schemaVersion tương thích giữa producer và consumer.
3. **Integration test:** publish vào exchange, route đến queue, inbound adapter phát đúng payload type.
4. **Failure test:** malformed JSON, type không được tin cậy, quá kích thước, schema sai và lỗi listener.
5. **Recovery test:** retry/redelivery, ACK/DLQ, restart và idempotency.

### 14.1. Unit test SimpleMessageConverter

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.support.converter.SimpleMessageConverter;

class SimpleConverterTest {

    @Test
    void textRoundTrip() {
        SimpleMessageConverter converter =
            new SimpleMessageConverter();

        Message amqp = converter.toMessage(
            "Don hang so O-1001", new MessageProperties());

        Object decoded = converter.fromMessage(amqp);

        assertEquals("Don hang so O-1001", decoded);
        assertEquals(
            MessageProperties.CONTENT_TYPE_TEXT_PLAIN,
            amqp.getMessageProperties().getContentType());
    }
}
~~~

Đây là **unit test converter**, không chứng minh kết nối RabbitMQ, routing hoặc consumer ACK. Muốn kiểm thử ký tự tiếng Việt, nên đưa payload thực có dấu tiếng Việt vào test và xác minh bytes/charset nếu hợp đồng dùng UTF-8.

### 14.2. Unit test JSON converter theo phiên bản

Với Spring AMQP 3.x/Jackson 2, một converter JSON có thể được kiểm thử tương tự:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;

class OrderJsonConverterTest {

    @Test
    void eventRoundTrip() {
        Jackson2JsonMessageConverter converter =
            new Jackson2JsonMessageConverter();

        OrderCreatedEvent original =
            new OrderCreatedEvent("evt-1001", "O-1001", 150000, 1);

        Message encoded = converter.toMessage(
            original, new MessageProperties());

        Object decoded = converter.fromMessage(encoded);

        OrderCreatedEvent event =
            assertInstanceOf(OrderCreatedEvent.class, decoded);
        assertEquals(original.eventId(), event.eventId());
        assertEquals(original.totalVnd(), event.totalVnd());
    }
}
~~~

Ví dụ test này **cố ý giới hạn trong một môi trường 3.x đồng nhất**, nơi producer/consumer dùng cùng converter/type mapping và được phép deserialize OrderCreatedEvent. Nếu converter từ chối type metadata hoặc target type khác, cần cấu hình mapper/trust theo hợp đồng thay vì bỏ qua kiểm tra bảo mật.

Unit round-trip trên **cùng một converter** chưa đủ để kết luận hai ứng dụng khác phiên bản, khác ngôn ngữ hoặc khác package tương thích. Bắt buộc có **contract vectors** là body JSON/bytes và properties mong đợi ở cả hai phía.

### 14.3. Test trực tiếp raw bytes và properties

Một test hợp đồng có thể kiểm tra:

~~~text
Input domain:  OrderCreatedEvent(evt-1001, O-1001, 150000, v1)
Expected body: JSON object với 4 trường đã chốt
Expected contentType: application/json
Expected charset: UTF-8 nếu hợp đồng cần nêu rõ
Allowed headers: correlationId, eventId, schemaVersion (theo chính sách)
Rejected headers: Spring replyChannel, errorChannel, object Java tùy ý
Expected consumer type: OrderCreatedEvent hoặc domain model được chọn
~~~

Không chỉ so sánh **Object.equals()** sau deserialize; phải kiểm tra cả bytes, properties và các trường nghiệp vụ có bị thay đổi/loại bỏ ngoài ý muốn không.

### 14.4. Ma trận kiểm thử converter

| Kịch bản | Producer | Consumer | Kết quả cần kiểm chứng |
| --- | --- | --- | --- |
| Text đúng | Simple, String text/plain | Simple | Nhận String và charset đúng |
| Bytes đúng | byte[] | Binary/byte[] | Nội dung bytes giữ nguyên |
| JSON đúng | Jackson JSON | JSON converter tương thích | DTO và schemaVersion đúng |
| JSON qua Simple | application/json bytes | Simple | Kiểm tra payload byte[] hoặc thực tế converter phát; không ép DTO |
| JSON lỗi cú pháp | Bytes JSON sai | JSON parser | Lỗi tại conversion/transformer, cách ly theo policy |
| Unknown type header | Type ID không được phép | Converter có whitelist | Từ chối an toàn, không trust all |
| Unknown schema version | JSON hợp cú pháp, version mới | Validator | Phát hiện không tương thích rõ ràng |
| Sai charset | Producer/metadata không khớp | Text converter | Phát hiện lỗi ký tự, không âm thầm corrupt |
| Payload lớn | Body vượt giới hạn | Consumer | Reject/cách ly theo ngưỡng trước khi gây OOM |
| JSON double-encoded | String JSON qua JSON converter lần nữa | Consumer | Test body phát hiện chuỗi bị bọc |
| Header nội bộ | Spring replyChannel/errorChannel | AMQP mapper | Không chuyển object hạ tầng ngoài ý muốn |
| Trùng eventId | Cùng sự kiện gửi lại | Consumer | Business side effect thực hiện một lần |
| Consumer restart | Broker redeliver | Consumer | Converter hoạt động, idempotency bảo vệ nghiệp vụ |

### 14.5. Test topology vẫn cần dù converter đúng

Một event JSON hợp lệ có thể không tới consumer nếu exchange/routing key sai. Integration test cần xác minh:

- Exchange **orders.events** tồn tại đúng loại.
- Queue **orders.created.q** có binding **orders.created**.
- Producer đủ quyền publish và consumer đủ quyền read.
- Message body/properties thực tế đúng khi consumer nhận.
- Publisher confirm/return được xử lý nếu yêu cầu bảo đảm giao nhận.

**MessageConverter không xử lý định tuyến RabbitMQ.** Đừng mất thời gian sửa JSON converter khi lỗi thật là binding không khớp.

## 15. Security: converter là ranh giới dữ liệu không tin cậy

Message đến từ broker có thể do một ứng dụng khác publish, có thể là phiên bản cũ, cấu hình sai hoặc nguồn không hoàn toàn tin cậy. Converter/mapper là **ranh giới vào dữ liệu ngoài**, cần được kiểm soát.

### 15.1. Các nguyên tắc bắt buộc

- Không dùng Java native deserialization cho dữ liệu không tin cậy.
- Hạn chế package/type được phép map từ type headers, tránh cấu hình trust all.
- Giới hạn kích thước body trước khi deserialize; đánh giá độ sâu JSON và nguy cơ payload làm tốn CPU/bộ nhớ.
- Validate contentType, schemaVersion, eventType, field bắt buộc và miền giá trị sau khi parse.
- Dùng target DTO hoặc type mapping do **consumer kiểm soát**, không cho message tự chọn class tùy ý.
- Không đưa credentials, stack trace hoặc dữ liệu cá nhân không cần thiết vào application headers/log.
- Dùng TLS và quyền RabbitMQ tối thiểu theo exchange/queue/virtual host.
- Đặt timeouts, retry limits, DLQ và cảnh báo cho các lỗi converter xảy ra liên tục.

### 15.2. AMQP header injection

Đừng cho producer ngoài quyền thay đổi mọi quyết định nghiệp vụ bằng header. Ví dụ:

~~~text
Header: role=ADMIN
Header: tenantId=other-company
Header: __TypeId__=some.unexpected.Class
~~~

Các giá trị này **không được tự mặc định là đáng tin** chỉ vì message đến từ một RabbitMQ queue đã định tuyến đúng. Quyền xử lý tenant/role phải được xác minh bằng cơ chế bảo mật của ứng dụng và contract, type mapper phải chỉ cho phép kiểu hợp lệ.

### 15.3. PII và payload encryption

TLS bảo vệ đường truyền nhưng không thay chính sách dữ liệu tại broker và consumer. Nếu message chứa dữ liệu cá nhân hoặc thanh toán, cần cân nhắc:

- Giảm thiểu các trường xuất hiện trong event.
- Phân quyền RabbitMQ đọc queue và truy cập management.
- Chính sách retention, TTL, DLQ và xóa dữ liệu lỗi.
- Mã hóa ở cấp payload nếu mô hình bảo mật yêu cầu.
- Mask/redact log, không in toàn bộ JSON để debug ở production.

## 16. Performance và lifecycle của conversion

### 16.1. Cost của chuyển đổi

| Tình huống | Chi phí chính | Đề xuất |
| --- | --- | --- |
| String nhỏ | Encoding/decoding charset | Dùng UTF-8 rõ ràng và converter phù hợp |
| JSON DTO nhỏ | Reflection/mapper, parse, object allocation | Tái sử dụng converter/ObjectMapper; đo latency |
| JSON lồng sâu | Parse CPU, heap, giới hạn độ sâu | Giới hạn input và schema |
| Batch nhiều event | Số message, overhead conversion và broker | Đo batch throughput, không batch tùy tiện nếu mất ý nghĩa ACK |
| Payload lớn | Memory copies, network, heap/GC | Giới hạn size, cân nhắc object storage reference |
| Schema migration | Mapping và validation nhiều version | Xác định version support, tránh converter logic quá phức tạp |

**Không tạo ObjectMapper mới cho từng message** nếu không có lý do: mapper đã cấu hình phù hợp thường có thể tái sử dụng; việc khởi tạo lặp lại gây overhead. Tương tự, RabbitTemplate và ConnectionFactory nên được Spring quản lý dùng chung theo cách cấu hình ứng dụng.

### 16.2. Conversion ảnh hưởng ACK latency

Với AMQP inbound adapter message-driven và DirectChannel đồng bộ, thời gian convert + transform + business handler có thể giữ listener callback. Nếu payload lớn hoặc JSON parse chậm, message ở trạng thái unacked lâu hơn, ảnh hưởng **prefetch quota** và throughput.

~~~mermaid
flowchart TD
    Q["RabbitMQ delivery"] --> V["Deserialize / convert"]
    V --> T["Transformer + validation"]
    T --> H["Business handler"]
    H --> ACK["Container ACK"]
    V -. "Lỗi conversion" .-> E["Error handler"]
    T -. "Lỗi schema" .-> E
    H -. "Lỗi business" .-> E
~~~

Sơ đồ minh họa luồng **đồng bộ với ACK theo listener outcome**; không phải bảo đảm thứ tự ACK trong mọi cấu hình transaction, batching hoặc async channel.

### 16.3. Prefetch và concurrency không sửa được lỗi converter

Nếu 10% message lỗi schema, tăng concurrent consumers từ 2 lên 20 có thể chỉ làm số lỗi và DLQ tăng nhanh hơn. Nếu converter quá nặng, tuning concurrency có thể giúp ở mức nào đó nhưng phải kiểm tra CPU/heap/GC và giới hạn downstream.

Trước khi tối ưu prefetch, nên đo **conversion latency**, handler latency, số message sai, ready/unacked, listener consumer count và memory peak.

### 16.4. Lifecycle và phiên bản converter

RabbitTemplate, MessageConverter, ConnectionFactory và inbound listener thường là Spring beans. Khi nâng phiên bản:

1. Đọc lại hợp đồng type mapping và content type.
2. Chạy contract tests giữa producer mới với consumer cũ và ngược lại.
3. Kiểm tra những class converter Jackson thay đổi theo thế hệ.
4. Kiểm tra serializer security/trusted types và các headers mặc định.
5. Đánh giá dữ liệu còn trong queue từ phiên bản cũ khi consumer mới khởi động.
6. Có phương án rollback/migration nếu payload mới không thể parse bởi consumer cũ.

**Container isRunning() không chứng minh converter hoạt động đúng.** Một consumer có thể liên tục nhận rồi reject message do schema mismatch trong khi vẫn báo đang chạy.

## 17. Chọn converter cho các tình huống thực tế

Không phải mọi hệ thống đều cần một JSON converter duy nhất. Nên chọn theo **hợp đồng với producer/consumer**, khả năng thay đổi schema và yêu cầu bảo mật.

| Nhu cầu | Phương án thích hợp | Điểm phải kiểm tra |
| --- | --- | --- |
| Cả hai phía gửi text đơn giản | SimpleMessageConverter + String | contentType, charset, escape và validation |
| Chuyển bytes nhị phân không đổi | byte[] hoặc converter nhị phân | Content type, kích thước, serializer tương ứng |
| Spring AMQP 3.x trao đổi DTO JSON có kiểm soát | Jackson2JsonMessageConverter | Type metadata, trusted types, JSON schema |
| Nhiều ngôn ngữ trao đổi JSON event | Parse bytes/String theo schema domain ổn định | Không phụ thuộc Java package headers |
| Nhiều kiểu contentType trên một queue | Converter phân nhánh theo content type hoặc transformer router phù hợp | Thiếu/sai contentType, fallback an toàn |
| Event Avro/Protobuf | Serializer/deserializer schema-based | Schema registry/version và tính tương thích |
| Tác vụ lớn/binary | Tham chiếu object storage hoặc xử lý có giới hạn | Memory, throughput, checksum, bảo mật |
| Request–reply qua AMQP gateway | Converter request và reply được định nghĩa riêng | Reply-to, correlation, timeout, error contract |

### 17.1. Một queue nhận nhiều content type

Đôi khi queue nhận cả text/plain và application/json. Thay vì thử parse JSON cho mọi message, cần có chiến lược rõ:

~~~mermaid
flowchart TD
    M["AMQP Message"] --> CT{"contentType"}
    CT -->|"application/json"| J["JSON converter<br/>schema + version validation"]
    CT -->|"text/plain"| T["Text converter<br/>charset + parser"]
    CT -->|"application/octet-stream"| B["Binary parser / schema"]
    CT -->|"Khác hoặc thiếu"| E["Reject/cách ly theo policy"]
    J --> D["Domain event"]
    T --> D
    B --> D
~~~

Spring AMQP có các cơ chế kết hợp converter, chẳng hạn lựa chọn delegate theo content type ở các phiên bản hỗ trợ. Tuy nhiên, một converter điều phối **không loại bỏ nghĩa vụ định nghĩa hợp đồng** và cách xử lý khi content type không hợp lệ.

Nếu chỉ một eventType được phép trong queue, việc chấp nhận quá nhiều định dạng có thể tăng complexity và attack surface. Có khi tách queue/route theo contract là giải pháp dễ bảo trì hơn.

### 17.2. Case study: SFTP CSV → AMQP JSON → Warehouse

**Bài toán:** đối tác upload file đơn hàng qua SFTP; ứng dụng Spring Integration tải file, parse CSV, chuẩn hóa đơn hàng rồi publish OrderCreated JSON lên RabbitMQ. Dịch vụ Warehouse tiêu thụ và cập nhật cơ sở dữ liệu.

~~~mermaid
flowchart LR
    S["SFTP CSV"] --> IA["SFTP inbound adapter<br/>poller"]
    IA --> P["CSV parser / validator"]
    P --> O["OrderCreatedEvent"]
    O --> CV["JSON serializer / AMQP converter"]
    CV --> AO["AMQP outbound adapter"]
    AO --> Q["RabbitMQ orders.created.q"]
    Q --> AI["AMQP inbound adapter"]
    AI --> V["JSON decode + schema check"]
    V --> W["Warehouse handler<br/>idempotency + DB"]
~~~

Trong flow này:

1. SFTP inbound có thể phát File hoặc dữ liệu từ xa tùy adapter và cấu hình; bước parser CSV chịu trách nhiệm chuẩn hóa.
2. Domain event **không nên** phụ thuộc đường dẫn file hay Java class của SFTP adapter.
3. JSON conversion và AMQP routing được định nghĩa riêng; producer gửi tới exchange/routing key đúng.
4. Warehouse dùng schemaVersion/eventId để validate và chống trùng.
5. File đã được chọn, RabbitMQ đã ACK publish và Warehouse đã commit DB là **ba mốc khác nhau**.
6. Nếu cần không mất event sau DB commit ở bước nhập liệu, phải cân nhắc durable metadata, outbox hoặc nguồn retry tương ứng.

### 17.3. Case study: HTTP request → AMQP request–reply

**Bài toán:** HTTP inbound gateway nhận yêu cầu báo giá, rồi dùng AMQP outbound gateway hỏi một dịch vụ báo giá qua RabbitMQ. Dịch vụ báo giá dùng AMQP inbound gateway trả JSON reply.

~~~text
HTTP request JSON
  -> HTTP inbound gateway / DTO validation
  -> Spring Integration MessageChannel
  -> AMQP outbound gateway (request converter)
  -> RabbitMQ request queue
  -> AMQP inbound gateway + QuoteService
  -> AMQP reply JSON (reply converter)
  -> HTTP response mapping
~~~

Mỗi ranh giới cần xác định:

- **HTTP content type** và JSON DTO có thể khác cấu hình **AMQP content type**.
- **AMQP reply-to/correlation** không phải HTTP request ID, dù có thể map phục vụ tracing.
- **Timeout HTTP** và **timeout AMQP RPC** cần có ngân sách thời gian hợp lý.
- Reply nghiệp vụ ERROR có thể map thành mã HTTP đã định nghĩa; không gửi stack trace nguyên bản.
- Retry request có side effect phải giữ idempotency key ổn định.

Đừng dùng publisher confirm thay cho business reply; converter chỉ đảm nhiệm biểu diễn dữ liệu, không tạo ra hợp đồng trả kết quả nếu endpoint là adapter một chiều.

## 18. Checklist trước khi triển khai converter lên production

| Nhóm | Câu hỏi cần xác nhận |
| --- | --- |
| **Wire format** | JSON/text/binary nào? charset và content type cụ thể? |
| **Schema** | eventType/schemaVersion ở đâu, các trường bắt buộc và kiểu dữ liệu? |
| **Type mapping** | Consumer tự chọn target DTO hay tin vào type header? Có whitelist không? |
| **Security** | Có Java native deserialization hay trust-all packages không? |
| **Message size** | Giới hạn body, nesting, compression và memory peak ở đâu? |
| **Headers** | Header nào được phép đi qua broker? Có làm lộ nội bộ/PII không? |
| **Compatibility** | Producer mới ↔ consumer cũ, producer cũ ↔ consumer mới đã test chưa? |
| **Error** | Malformed JSON bị reject, retry hay DLQ? Converter fail ở lớp nào? |
| **ACK** | Việc parse/validate/commit xảy ra trước hay sau consumer ACK? |
| **Idempotency** | EventId ổn định qua retry? Consumer kiểm tra trùng ra sao? |
| **Topology** | Exchange, routing key, queue và binding đúng virtual host chưa? |
| **Observability** | Có metric conversion errors theo contentType/schemaVersion/endpoint không? |
| **Lifecycle** | Khi shutdown/restart, các message cũ có còn decode được không? |

### 18.1. Những metric nên theo dõi

Không chỉ đếm số lần RabbitTemplate.convertAndSend được gọi. Đối với converter và message contract, nên theo dõi:

- **conversion_success_total** và **conversion_failure_total**, chia theo endpoint/eventType/schemaVersion.
- **payload_size_bytes** và độ trễ serialize/deserialize.
- **unsupported_content_type_total** và **unsupported_schema_version_total**.
- Số message bị **reject**, **requeue** hoặc vào **DLQ** do lỗi dữ liệu.
- RabbitMQ **ready/unacked**, số consumer, publish/confirm/return rates.
- **business_processed_total**, số eventId trùng và latency end-to-end.

Tên metric trên là **đề xuất thiết kế**, không phải cam kết Spring Integration hay Micrometer tự tạo sẵn tất cả. Phải instrument hoặc bật tính năng phù hợp với phiên bản thư viện.

### 18.2. Log không nên chứa gì?

Tránh log toàn bộ body JSON có thông tin cá nhân, headers chứa token, mật khẩu, connection URI hoặc serialized object không rõ nguồn. Nên log:

~~~text
endpoint=ordersInbound
eventId=evt-1001
eventType=ORDER_CREATED
schemaVersion=1
contentType=application/json
errorCode=INVALID_SCHEMA
retryable=false
~~~

Đây là ví dụ log an toàn theo hướng **metadata đủ chẩn đoán**, nhưng ngay cả eventId có thể cần xử lý theo chính sách dữ liệu của tổ chức. Không suy đoán một định danh luôn vô hại.

## 19. Sai lầm thường gặp

**“RabbitMQ trực tiếp gửi OrderCreatedEvent Java object.”** RabbitMQ mang body bytes và properties; converter/serializer ở hai phía mới tạo đối tượng Java.

**“MessageConverter và Spring Integration transformer là cùng một lớp.”** Converter ở biên giao thức; transformer chuẩn hóa payload trong flow. Có thể cùng dùng Jackson nhưng trách nhiệm khác nhau.

**“SimpleMessageConverter tự parse mọi application/json thành DTO.”** Nó không phải JSON domain converter. Khi nhận JSON dưới dạng bytes, cần JSON converter hoặc transformer phù hợp.

**“contentType=application/json nghĩa là dữ liệu chắc chắn hợp lệ.”** Content type chỉ là metadata; phải parse, validate schema và dữ liệu.

**“Chỉ cần sender dùng Jackson, receiver tự nhận đúng class.”** Receiver cần converter/mapper hoặc transformer tương ứng; type metadata có thể bị thiếu/không tin cậy.

**“Tin mọi __TypeId__ từ producer là tiện và an toàn.”** Type header có thể bị giả mạo, cần whitelist/target type, không trust all.

**“Java native serialization là phương án chung cho mọi message.”** Nó ràng buộc runtime/class và mang rủi ro deserialize dữ liệu không tin cậy.

**“Serialize JSON hai lần không ảnh hưởng consumer.”** Có thể biến JSON object thành một JSON string literal; phải kiểm tra raw body.

**“Đổi Java package không ảnh hưởng giao tiếp.”** Nếu converter phụ thuộc Java class type header, đổi package có thể phá compatibility.

**“SchemaVersion chỉ cần trong routing key.”** Routing key phục vụ định tuyến; payload và schema vẫn cần hợp đồng ổn định.

**“Converter thành công tức là business đã commit.”** Conversion chỉ tạo/đọc dữ liệu; handler/transaction còn ở phía sau.

**“Nếu business handler bắt exception thì mọi lỗi decode được xử lý.”** Conversion có thể thất bại trước khi handler nhận message.

**“Mọi lỗi converter đều nên requeue vô hạn.”** Malformed JSON hoặc type không hợp lệ không tự sửa sau nhiều lần nhận.

**“ErrorChannel mặc nhiên xử lý mọi lỗi listener.”** Phải xem lỗi xảy ra trước/sau khi tạo Spring Message, error handler và advice.

**“Queue durable bảo đảm exactly-once.”** Redelivery, retry sau mất confirm và side effect trùng vẫn có thể xảy ra.

**“MessageHeaders.ID có thể làm khóa idempotency.”** Cần eventId/business key ổn định qua các lần gửi/nhận lại.

**“Tăng prefetch là cách sửa JSON parse lỗi.”** Prefetch chỉ giới hạn delivery chưa ACK; tăng có thể khuếch đại tải lỗi.

**“Đã có JSON converter nên không cần contract tests.”** Producer/consumer thay version, headers và default mapping có thể khác nhau.

## 20. Câu hỏi tự kiểm tra

1. Spring Messaging Message và Spring AMQP Message khác nhau về payload/body và headers/properties ra sao?
2. AMQP MessageConverter thực hiện việc gì mà Spring Integration transformer không nhất thiết thực hiện?
3. ContentType và contentEncoding ảnh hưởng đến kiểu payload và charset như thế nào?
4. SimpleMessageConverter xử lý String/byte[] ra sao? Vì sao không mặc định biến JSON thành OrderCreatedEvent?
5. Khi nào nên dùng JSON converter, khi nào nên để inbound phát byte[] rồi transformer tự parse?
6. Vì sao producer và consumer phải thống nhất wire schema thay vì chỉ thống nhất Java class?
7. Type header __TypeId__ dùng để làm gì và có rủi ro gì khi đến từ producer ngoài?
8. Vì sao không nên bật trust all packages để sửa lỗi deserialize?
9. Java native serialization có những rủi ro bảo mật và compatibility nào?
10. Khi transformer đã serialize DTO thành JSON String, JSON converter ở outbound có thể tạo lỗi double encoding thế nào?
11. Trong Java DSL minh họa, MessageChannel nào chuyển String tới outbound AMQP adapter?
12. Trong inbound Java DSL, converter cung cấp String trước hay sau bước OrderTextParser.parse?
13. Nếu message application/json được SimpleMessageConverter trả về byte[], bạn cần đổi flow thế nào?
14. Vì sao handler domain có thể không bắt được lỗi xảy ra trong AMQP converter?
15. Malformed JSON nên retry vô hạn hay cô lập? Lỗi DB timeout thì sao?
16. DLQ có tự xuất hiện khi converter ném exception không? Phải cấu hình những gì?
17. Converter thành công và consumer ACK có bảo đảm business side effect đúng một lần không?
18. Khi nâng Spring AMQP/Jackson, những test nào phát hiện thay đổi converter/type mapping?
19. Làm thế nào kiểm tra producer mới vẫn tương thích consumer cũ khi thêm trường JSON?
20. Nếu hệ thống nhận từ SFTP rồi phát Kafka/AMQP, vì sao nên chuẩn hóa thành domain event độc lập giao thức?

## Tổng kết

**AMQP message converter** là thành phần chuyển đổi giữa **đối tượng Java và AMQP Message body/properties**, giúp Spring Integration inbound/outbound adapter hoặc gateway trao đổi dữ liệu qua RabbitMQ. **SimpleMessageConverter** phù hợp những trường hợp String/byte[] cơ bản; **JSON converter** cần schema và type mapping rõ ràng; những định dạng khác cần serializer/deserializer thích hợp. **ContentType, contentEncoding, type headers và application headers** là phần của hợp đồng giao tiếp, không phải chi tiết có thể bỏ qua.

Thiết kế đáng tin cậy phải phân biệt **converter ở biên** với **transformer/validator nghiệp vụ**, chỉ tin những kiểu dữ liệu được cho phép, kiểm thử raw bytes/properties và compatibility qua các phiên bản. Lỗi conversion có thể xảy ra trước business handler nên phải phối hợp **listener error handling, retry/DLQ, ACK và idempotency**. Trong module **SPRING_INTEGRATION_ADAPTERS**, tư duy này cũng áp dụng khi dữ liệu đi qua File, SFTP, HTTP, JMS, Kafka hoặc database: định nghĩa message contract ổn định, xác định ranh giới lỗi và vòng đời kết nối trước khi cho hệ thống trao đổi dữ liệu thật.
