# Header mapping với Rabbit message

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **Spring Messaging MessageHeaders**, **RabbitMQ AMQP basic properties**, **application headers** và metadata chỉ có khi consumer nhận delivery.
- Giải thích chiều **outbound mapping** (Spring Message → AMQP Message) và **inbound mapping** (AMQP Message → Spring Message), đồng thời phân biệt header mapping với chuyển đổi body.
- Nhận biết các metadata thường gặp: **contentType**, **contentEncoding**, **messageId**, **correlationId**, **replyTo**, **type**, **timestamp**, **priority**, **deliveryMode**, **receivedExchange**, **receivedRoutingKey** và **deliveryTag**.
- Thiết kế một **header contract** ổn định cho eventType, schemaVersion, eventId và trace context; tránh phụ thuộc vào Java class name hoặc các header nội bộ của framework.
- Dùng Spring Integration **AMQP outbound/inbound channel adapter** và **RabbitTemplate** để phát, nhận, kiểm tra message properties thực tế.
- Kiểm soát **header mapper**, whitelist, kiểu dữ liệu và giới hạn tin cậy; không biến header từ producer bên ngoài thành quyền truy cập hay chỉ thị thực thi.
- Hiểu ảnh hưởng của header mapping đối với **AMQP gateway request–reply**, publisher confirms/returns, consumer ACK, retry, DLX/DLQ và idempotency.
- Xây dựng unit test, contract test và integration test để xác minh body, properties, routing và các bước xử lý lỗi.

## 1. Bài toán: payload đúng nhưng metadata sai

Giả sử hệ thống OrderService publish event **OrderCreated** qua RabbitMQ. Body JSON có thể hoàn toàn hợp lệ, nhưng dịch vụ Warehouse vẫn gặp lỗi vì:

- Producer đặt **contentType** là text/plain dù body là JSON.
- **schemaVersion** được đặt trong Spring MessageHeaders nhưng không được mapper đưa sang RabbitMQ application headers.
- Consumer sử dụng nhầm **correlationId** cho idempotency nên một event được retry bị xử lý lại.
- Một flow copy cả **replyChannel** hoặc đối tượng **Channel** nội bộ sang AMQP message.
- Producer đặt **tenantId=other-tenant** trong header rồi consumer tin đó là bằng chứng có quyền truy cập.
- Consumer dùng **receivedRoutingKey** như trường hợp nghiệp vụ đã được xác thực mà không kiểm tra payload.

Vấn đề không nằm duy nhất ở JSON serializer hay RabbitMQ bindings. **Header mapping** là bước chuyển metadata giữa mô hình **Spring Message** và mô hình **AMQP message**; cần xác định header nào có thể đi qua biên giao thức, chuyển thành thuộc tính nào và được phía nhận tin ở mức nào.

~~~mermaid
flowchart LR
    S["Service tạo event"] --> M["Spring Message<br/>payload + MessageHeaders"]
    M --> O["AMQP outbound adapter"]
    O --> HM["Outbound header mapper"]
    HM --> V["AMQP MessageConverter"]
    V --> W["AMQP body bytes<br/>Basic properties + headers"]
    W --> X["RabbitMQ exchange"]
    X --> Q["Queue"]
    Q --> I["AMQP inbound adapter"]
    I --> IM["Converter + inbound header mapper"]
    IM --> C["MessageChannel"]
    C --> H["Business handler"]
~~~

Sơ đồ thể hiện các **trách nhiệm logic**, không cam kết thứ tự gọi method nội bộ giữa mapper và converter trong mọi phiên bản. Converter quyết định biểu diễn payload/body; header mapper quyết định metadata tương ứng với hợp đồng. Một số endpoint còn đặt trực tiếp exchange/routing key ở cấu hình thay vì lấy từ Spring Message headers.

Bài này thuộc chương **Adapter AMQP** trong module **SPRING_INTEGRATION_ADAPTERS**: kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và MessageChannel, đồng thời quản lý hợp đồng message, lỗi và vòng đời kết nối. Cùng một nguyên tắc phân tách payload và metadata cũng áp dụng khi tích hợp File, SFTP, HTTP, JMS, Kafka và database.

## 2. Ba lớp metadata khác nhau

| Lớp | API/biểu diễn điển hình | Điều chứa bên trong |
| --- | --- | --- |
| **Spring Messaging MessageHeaders** | org.springframework.messaging.MessageHeaders | Header trên Spring Message di chuyển qua MessageChannel |
| **AMQP basic properties** | org.springframework.amqp.core.MessageProperties | Các trường AMQP như contentType, messageId, correlationId, replyTo, deliveryMode, priority |
| **AMQP application headers** | MessageProperties.getHeaders() | Bảng key/value do publisher gắn theo hợp đồng, ví dụ eventType, schemaVersion, traceparent |

Ngoài ra, Spring AMQP đưa một số **metadata nhận delivery** vào MessageProperties khi nhận message từ broker, ví dụ exchange/routing key thực nhận, consumer queue, delivery tag và redelivered. Chúng có thể được ánh xạ vào Spring MessageHeaders nhưng không phải tất cả đều là application headers do producer tự publish.

### 2.1. Cùng tên Message nhưng khác lớp

~~~java
// Noi bo Spring Integration / Spring Messaging
org.springframework.messaging.Message<String> springMessage;

// Bien giao thuc Spring AMQP / RabbitMQ
org.springframework.amqp.core.Message amqpMessage;
~~~

Spring Message có **payload kiểu Java** và MessageHeaders. Spring AMQP Message có **body byte[]** và MessageProperties. **RabbitMQ broker không lưu một đối tượng Java Spring Message nguyên dạng** khi publish.

### 2.2. Body không nằm trong headers

Ví dụ một bản tin AMQP logic:

~~~text
AMQP message
  body bytes: {"eventId":"evt-1001","orderId":"O-1001","totalVnd":150000}

  basic properties:
    contentType: application/json
    contentEncoding: UTF-8
    messageId: evt-1001
    correlationId: trace-request-17
    deliveryMode: persistent

  application headers:
    eventType: ORDER_CREATED
    schemaVersion: 1
    traceparent: 00-...-...-01
~~~

Ở phía consumer, **contentType** giúp converter giải mã body; **eventType/schemaVersion** giúp chọn schema hoặc xác thực hợp đồng; **messageId** hỗ trợ truy vết; **correlationId** liên kết trao đổi theo một quy tắc riêng. Không có trường nào trong số đó tự chứng minh Warehouse đã hoàn tất transaction.

### 2.3. Metadata nội bộ không phải dữ liệu wire

Spring MessageHeaders có những thành phần như:

- **MessageHeaders.ID** và **MessageHeaders.TIMESTAMP**: định danh/thời điểm tạo Spring Message nội bộ.
- **replyChannel** và **errorChannel**: điểm chuyển tiếp nội bộ, có thể là object MessageChannel, String hoặc giá trị định tuyến do framework xử lý.
- Thông tin gắn với **lifecycle, acknowledgment hoặc Channel** khi adapter tiếp nhận delivery.

Không đưa nguyên xi những object này qua RabbitMQ. Chúng không phải một phần của business event contract, có thể không biểu diễn được thành AMQP field table hợp lệ và có thể gây rò rỉ thông tin nội bộ.

## 3. Các loại header trong AMQP: inbound và outbound

Một vài header có thể được đặt lúc publish; một vài metadata chỉ biết sau khi broker đã giao delivery.

| Dữ liệu | Phía tạo thông thường | Ý nghĩa |
| --- | --- | --- |
| **contentType** | Publisher/converter | Định dạng body: JSON, text, binary... |
| **contentEncoding** | Publisher/converter | Charset hoặc encoding theo hợp đồng |
| **messageId** | Publisher | Định danh message do ứng dụng chọn, có thể để trống |
| **correlationId** | Publisher/gateway | Liên kết request–reply hoặc tracing nếu hợp đồng định nghĩa |
| **replyTo** | Publisher/gateway | Đích phản hồi AMQP khi dùng request–reply |
| **type** | Publisher | Mô tả loại message ở cấp AMQP nếu ứng dụng dùng |
| **priority** | Publisher | Độ ưu tiên khi queue và broker hỗ trợ chính sách tương ứng |
| **deliveryMode** | Publisher | Persistent/non-persistent theo AMQP và hỗ trợ broker |
| **timestamp** | Publisher | Metadata thời gian, không nên tự coi là thời điểm broker nhận |
| **eventType, schemaVersion** | Ứng dụng publisher | Header nghiệp vụ tùy chỉnh |
| **receivedExchange** | Consumer/broker client metadata | Exchange thực tế gắn với delivery được nhận |
| **receivedRoutingKey** | Consumer/broker client metadata | Routing key thực nhận; hỗ trợ điều tra |
| **consumerQueue** | Listener/consumer metadata | Queue mà consumer đã nhận message |
| **deliveryTag** | Broker delivery trên AMQP channel | Sử dụng ACK/NACK đúng channel |
| **redelivered** | Broker delivery | Tín hiệu một delivery có thể đã được giao trước |

Các tên như **receivedRoutingKey** là tên thuộc tính API Spring AMQP. Khi được ánh xạ sang Spring Message, key thường được định nghĩa qua các hằng **AmqpHeaders** và có thể có prefix giao thức. **Đừng tự suy một key String bất kỳ rồi cam kết nó có mặt trên mọi phiên bản**; dùng hằng của thư viện đang sử dụng và kiểm chứng bằng test.

### 3.1. Header thuộc AMQP basic properties khác application headers

~~~java
import org.springframework.amqp.core.MessageProperties;

MessageProperties props = new MessageProperties();

// Standard AMQP properties:
props.setContentType(MessageProperties.CONTENT_TYPE_TEXT_PLAIN);
props.setContentEncoding("UTF-8");
props.setMessageId("evt-1001");
props.setCorrelationId("request-17");

// Custom AMQP application headers:
props.setHeader("eventType", "ORDER_CREATED");
props.setHeader("schemaVersion", 1);
~~~

**MessageProperties.setHeader("correlationId", ...)** không phải cách tương đương đáng tin cậy với **setCorrelationId(...)** nếu phía nhận kỳ vọng trường standard AMQP correlation-id. Một tên trông giống nhau có thể nằm ở **hai nơi wire khác nhau**.

### 3.2. Received routing key không phải outbound routing key

Đối với publisher, **exchange và routing key** chọn đích giao. Chúng có thể được đặt trực tiếp:

~~~java
rabbitTemplate.convertAndSend(
    "orders.events", "orders.created", payload);
~~~

Đối với consumer, **receivedRoutingKey** là metadata của delivery đã tới queue. Không lấy nhầm receivedRoutingKey của một message trước đó làm routing key mới nếu logic outbound không được thiết kế rõ.

Khi message được dead-letter hoặc republish, routing key của lần publish mới có thể khác key gốc. Hãy giữ **eventType** trong payload hoặc custom header theo contract, không chỉ suy nghĩa event từ routing key tại mọi chặng.

## 4. Outbound header mapping và inbound header mapping

**Outbound mapping:**

~~~text
Spring MessageHeaders
    -> header mapper / adapter
    -> AMQP basic properties + application headers
    -> RabbitTemplate
    -> RabbitMQ
~~~

**Inbound mapping:**

~~~text
RabbitMQ delivery
    -> Spring AMQP MessageProperties
    -> converter + inbound header mapper
    -> Spring MessageHeaders
    -> MessageChannel
~~~

### 4.1. Mapping không đồng nghĩa copy mọi key

Header mapper có thể:

- Ánh xạ **standard AMQP properties** được framework hỗ trợ sang những key nội bộ được định nghĩa.
- Đưa **application headers** đã được phép vào bảng headers của AMQP Message.
- Không ánh xạ một số header đặc biệt như MessageHeaders.ID, replyChannel/errorChannel hoặc dữ liệu không phù hợp với AMQP field table.
- Có khác biệt giữa danh sách header cho **inbound** và **outbound**.
- Thay đổi hành vi theo phiên bản Spring Integration, cách tạo adapter/gateway và cấu hình custom mapper.

Vì thế không nên viết quy tắc “mọi header đặt bằng MessageBuilder.setHeader đều tự động xuất hiện nguyên dạng ở RabbitMQ”. Khi cần một header làm hợp đồng bắt buộc, hãy **khai báo policy mapping và kiểm thử raw MessageProperties**.

### 4.2. Default mapper và custom mapper

Spring Integration AMQP cung cấp cơ chế **header mapping** và các triển khai mặc định/tùy chỉnh theo thế hệ API. Trong nhiều phiên bản có lớp **DefaultAmqpHeaderMapper** cùng các hằng **AmqpHeaders**; để kiểm soát header chính xác phải dùng API builder, endpoint property hoặc mapper SPI tương thích với phiên bản đang chạy.

**Cần phân biệt hai mức cấu hình:**

1. **Adapter/gateway cấp Spring Integration:** header mapper chuyển Spring MessageHeaders với AMQP properties/headers.
2. **RabbitTemplate cấp Spring AMQP:** MessageConverter và MessagePostProcessor tạo/sửa một AMQP Message cụ thể.

Một **RabbitTemplate.setMessageConverter(...)** không thay việc định nghĩa **header mapper** của Spring Integration endpoint. Ngược lại, chỉ cấu hình mapper cũng không khiến body JSON tự được deserialize thành domain DTO.

### 4.3. Ưu tiên whitelist

Trong môi trường liên dịch vụ, nên cho phép rõ các custom headers thực sự có hợp đồng:

~~~text
eventId
eventType
schemaVersion
traceparent
tracestate (nếu dùng)
tenantRef (nếu đã được xác thực và hợp đồng cho phép)
~~~

Tránh copy bừa:

~~~text
replyChannel
errorChannel
native Channel object
Java exception / Throwable
Authorization bearer token
database connection / ORM entity
~~~

Khi một flow cần chuyển nhiều metadata, không nhất thiết gửi tất cả. Có thể đưa **eventId/eventType/schemaVersion** vào payload envelope, còn trace context trong AMQP headers; **xác thực nghiệp vụ** phải thực hiện ở phía nhận.

## 5. Hợp đồng header cho OrderCreated

Giả sử hai service không nhất thiết viết bằng Java. Hợp đồng nên tránh phụ thuộc package class Java hoặc header framework nội bộ.

| Trường | Vị trí khuyến nghị | Kiểu | Quy tắc |
| --- | --- | --- | --- |
| **eventId** | JSON envelope và/hoặc header theo contract | String | Ổn định khi retry, có phạm vi duy nhất |
| **eventType** | JSON envelope, có thể mirror vào header | String | Ví dụ ORDER_CREATED |
| **schemaVersion** | JSON envelope và/hoặc header | Integer/Number | Consumer chỉ chấp nhận version được hỗ trợ |
| **occurredAt** | JSON envelope | UTC timestamp string | Thời gian domain; không thay bằng delivery timestamp |
| **traceparent** | Application header | String theo W3C Trace Context | Chỉ phục vụ tracing, phải validate format |
| **contentType** | Basic property | MIME media type | application/json cho JSON bytes |
| **contentEncoding** | Basic property | String | Thống nhất UTF-8 nếu contract yêu cầu |
| **messageId** | Basic property | String | Có thể dùng eventId theo quy ước cụ thể |
| **correlationId** | Basic property | String | Correlate request/workflow, không tự là eventId |

Ví dụ envelope:

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

Nếu header schemaVersion ghi **2** nhưng envelope ghi **1**, consumer không nên âm thầm chọn một giá trị tùy hứng. Cần quy tắc rõ: **payload là nguồn chuẩn**, header là bản sao để route/log, hoặc ngược lại theo contract; khi khác nhau thì reject/cách ly để điều tra.

### 5.1. Header không thay validation

Header **eventType=ORDER_CREATED** không chứng minh payload thật sự có schema OrderCreated. Header **schemaVersion=1** không chứng minh các trường data hợp lệ. **contentType=application/json** không bảo đảm body chứa JSON hợp lệ.

Consumer vẫn phải parse dữ liệu bằng converter phù hợp, validate schema/version và kiểm tra quyền theo trust boundary.

### 5.2. Khi nào cần đưa eventId vào body?

Nếu eventId chỉ nằm trong Spring MessageHeader, sự thay đổi mapper có thể khiến eventId mất khi đi qua một adapter khác. Đưa eventId vào **envelope** giúp giữ định danh qua SFTP → Spring Integration → AMQP → Kafka/HTTP mà không phụ thuộc hoàn toàn vào quy tắc map header của từng protocol.

Đừng tạo eventId mới khi retry cùng một business event; có thể tạo **attemptId** riêng cho từng lần publish, nhưng consumer phải nhìn thấy **eventId gốc**.

### 5.3. Phân loại header theo nguồn tin cậy

- **Business contract:** eventId/eventType/schemaVersion, phải validate và có versioning.
- **Transport metadata:** messageId/correlationId/replyTo/contentType; dùng để hỗ trợ giao thức, không tin để cấp quyền.
- **Delivery metadata:** receivedRoutingKey/deliveryTag/redelivered; phục vụ vận hành hoặc ACK/NACK, không publish như business data.
- **Observability metadata:** traceparent/tracestate; phục vụ distributed tracing, cần giới hạn/kiểm tra.
- **Sensitive/internal:** replyChannel/errorChannel/credentials/native objects; không truyền qua boundary công khai.

## 6. Hằng AmqpHeaders và metadata nhận được

Trong Spring AMQP/Spring Integration, các **hằng AmqpHeaders** giúp tránh hardcode tên header thuộc giao thức. Với các phiên bản có API tương ứng, import:

~~~java
import org.springframework.amqp.support.AmqpHeaders;

// Ten header cua Spring Message, khong phai field AMQP wire:
String correlationKey = AmqpHeaders.CORRELATION_ID;
String messageIdKey = AmqpHeaders.MESSAGE_ID;
String receivedRoutingKey = AmqpHeaders.RECEIVED_ROUTING_KEY;
String contentTypeKey = AmqpHeaders.CONTENT_TYPE;
~~~

Đừng nhầm **AmqpHeaders.CORRELATION_ID** (key dùng trong Spring MessageHeaders) với tên trường của **MessageProperties.getHeaders()**. Mapper có thể chuyển giá trị thành **basic property correlation-id**, không phải một custom application header có tên giống hệt.

### 6.1. Metadata consumer

Những thông tin thường chỉ có ở phía nhận:

- **RECEIVED_EXCHANGE / RECEIVED_ROUTING_KEY:** phục vụ log, phân tích đường route, phân biệt source.
- **CONSUMER_QUEUE:** consumer đọc từ queue nào.
- **DELIVERY_TAG:** dùng settle delivery trên AMQP channel tương ứng.
- **REDELIVERED:** broker/client đánh dấu delivery đã được gửi lại.
- **CHANNEL:** trong một số endpoint/manual-ack configuration có thể được expose cho handler.

**Không cần ép consumer metadata trở thành outbound headers của một message mới.** Khi một flow làm bridge từ queue A sang exchange B, hãy tạo message outbound có **business contract rõ ràng** và chỉ giữ trace/eventId cần thiết.

### 6.2. Delivery tag không sống qua connection restart

Delivery tag có phạm vi **AMQP channel**, không phải định danh global. Không ghi delivery tag vào database rồi dùng nó ACK trên channel khác sau khi restart. Với MANUAL ACK, xác nhận phải dùng **đúng channel đã nhận**; tránh chuyển Channel qua executor thread mà không kiểm chứng cơ chế async acknowledgment của phiên bản thư viện.

### 6.3. Redelivered không phải idempotency key

**redelivered=true** chỉ gợi ý broker đã giao message này trước đó. Nó không chứng minh lần trước consumer đã commit, cũng không phát hiện mọi trường hợp producer publish cùng event lần hai. Consumer cần **eventId ổn định và kho trạng thái bền vững**.

## 7. MessageConverter, header mapper và transformer

Ba thành phần giải quyết các câu hỏi khác nhau:

| Thành phần | Input/output | Chịu trách nhiệm |
| --- | --- | --- |
| **AMQP MessageConverter** | Java object ↔ AMQP body/properties | String/byte[]/JSON, content type, type metadata |
| **AMQP header mapper** | Spring MessageHeaders ↔ AMQP properties/headers | Standard transport metadata, application header allowlist |
| **Spring Integration transformer** | Spring Message/payload → payload khác | Chuẩn hóa domain, schema migration, text → DTO |

### 7.1. Content type nên khớp body

Nếu converter tạo JSON bytes, **contentType** phải phù hợp, thường là application/json. Nếu gửi String dạng text, có thể dùng text/plain và contentEncoding UTF-8. Sai content type có thể khiến consumer chọn converter không đúng và ném lỗi trước khi handler nghiệp vụ được gọi.

### 7.2. Type header của JSON converter

Một số JSON converters sử dụng AMQP application headers quy ước như **__TypeId__**, **__ContentTypeId__** hoặc **__KeyTypeId__** để hướng dẫn Java type mapping. Những header này **không phải business eventType** và không nên bắt consumer khác ngôn ngữ phụ thuộc vào Java class name.

Không cấu hình trust-all packages chỉ để khiến deserialization không còn lỗi. Dùng target DTO, type mapping cố định, trusted packages được giới hạn và schema validation theo phiên bản. Mức hỗ trợ/naming của converter có thể khác nhau giữa các thế hệ Spring AMQP/Jackson.

### 7.3. Tránh double serialization

Nếu transformer đã tạo **String JSON** nhưng outbound RabbitTemplate dùng JSON converter serialize chính String đó lần nữa, broker có thể nhận **JSON string literal** thay vì JSON object. Một flow chỉ nên có **một nơi chịu trách nhiệm serialize wire body** và test raw bytes.

Tương tự, việc thấy một header contentType=application/json không chứng minh converter đã được cấu hình đúng, càng không chứng minh body có thể parse.

## 8. Ví dụ thực hành: topology RabbitMQ

Ta xây dựng một pipeline đơn giản:

~~~mermaid
flowchart LR
    P["OrderPublisher"] --> OC["ordersOutbound<br/>DirectChannel"]
    OC --> OA["AMQP outbound adapter"]
    OA --> RT["RabbitTemplate"]
    RT --> X["orders.events<br/>direct exchange"]
    X --> Q["orders.created.q"]
    Q --> LC["SimpleMessageListenerContainer"]
    LC --> IA["AMQP inbound adapter"]
    IA --> IC["ordersInbound<br/>DirectChannel"]
    IC --> H["HeaderInspector<br/>Warehouse handler"]
~~~

Hợp đồng thử nghiệm:

~~~text
Exchange:      orders.events
Routing key:   orders.created
Queue:         orders.created.q
Body text:     evt-1001|O-1001|150000
Body encoding: UTF-8
Content type:  text/plain
App headers:   eventType=ORDER_CREATED, schemaVersion=1
Basic props:   messageId=evt-1001, correlationId=req-1001
~~~

Ví dụ dùng String để tập trung vào **header mapping**; khi sử dụng JSON DTO trong production, hãy thay converter/parser và quy tắc schema tương ứng.

### 8.1. Dependencies

Với Spring Boot sử dụng dependency management tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-amqp</artifactId>
    </dependency>
</dependencies>
~~~

Cần RabbitMQ broker test, ConnectionFactory cấu hình đúng host/port/vhost, credentials và quyền exchange/queue. Không hardcode password thật. Sử dụng các phiên bản Spring Integration và Spring AMQP được BOM quản lý để giảm rủi ro API không tương thích.

### 8.2. Java configuration cho exchange, queue và binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersHeadersTopology {

    public static final String EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "orders.created";
    public static final String QUEUE = "orders.created.q";

    @Bean
    public DirectExchange ordersEventsExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersCreatedQueue() {
        return new Queue(QUEUE, true);
    }

    @Bean
    public Binding ordersCreatedBinding(
            Queue ordersCreatedQueue,
            DirectExchange ordersEventsExchange) {

        return BindingBuilder.bind(ordersCreatedQueue)
            .to(ordersEventsExchange)
            .with(ROUTING_KEY);
    }
}
~~~

Spring bean mô tả topology; RabbitAdmin/AmqpAdmin phải có quyền tạo tương ứng hoặc hạ tầng phải provision trước. **Queue durable không chứng minh các message được xử lý đúng một lần**. Nếu queue cùng tên đã có thuộc tính không tương thích, broker có thể không chấp nhận redeclare; không sửa topology production bằng restart tùy tiện.

## 9. Java DSL outbound: đặt Spring MessageHeaders

Đầu tiên cho OrderService gửi Spring Message tới MessageChannel và Spring Integration AMQP outbound adapter:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrdersHeadersOutboundFlow {

    @Bean
    public MessageChannel ordersOutbound() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow ordersHeadersOutbound(
            RabbitTemplate rabbitTemplate) {
        return IntegrationFlow.from("ordersOutbound")
            .handle(Amqp.outboundAdapter(rabbitTemplate)
                .exchangeName(OrdersHeadersTopology.EXCHANGE)
                .routingKey(OrdersHeadersTopology.ROUTING_KEY))
            .get();
    }
}
~~~

Producer:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrdersHeadersPublisher {

    private final MessageChannel ordersOutbound;

    public OrdersHeadersPublisher(
            @Qualifier("ordersOutbound") MessageChannel ordersOutbound) {
        this.ordersOutbound = ordersOutbound;
    }

    public void publish() {
        boolean accepted = ordersOutbound.send(
            MessageBuilder.withPayload("evt-1001|O-1001|150000")
                .setHeader("eventType", "ORDER_CREATED")
                .setHeader("schemaVersion", 1)
                .setHeader("eventId", "evt-1001")
                .build());

        if (!accepted) {
            throw new IllegalStateException(
                "MessageChannel did not accept the event");
        }
    }
}
~~~

**Điều đoạn mã bảo đảm:** Spring Message được tạo có ba custom headers và một payload String. Outbound adapter sử dụng RabbitTemplate để gửi tới exchange/routing key cố định.

**Điều đoạn mã chưa bảo đảm nếu chưa test:** mỗi custom header được chuyển sang AMQP application headers với đúng tên/kiểu, contentEncoding chính xác, messageId đã được đặt hoặc publisher đã nhận confirm. Những kết quả đó phụ thuộc converter/header mapper và RabbitTemplate đang dùng thực tế.

### 9.1. Đừng dùng MessageHeaders.ID làm eventId

Spring MessageBuilder có thể tạo ID/timestamp cho message nội bộ. Nếu event bị retry hoặc một transformer tạo Spring Message mới, ID nội bộ có thể thay đổi. Dùng **eventId=evt-1001** trong payload hoặc contract làm khóa idempotency của consumer; không tự lấy MessageHeaders.ID thay thế.

### 9.2. Đừng tự động chuyển toàn bộ replyChannel/errorChannel

Một số Spring Message có replyChannel/errorChannel là object Spring MessageChannel. Các object này dùng trong runtime nội bộ và không phải AMQP replyTo. Khi gửi qua outbound adapter, chỉ expose những metadata đã được hợp đồng cho phép; không copy object framework vào AMQP field table.

### 9.3. Exchange/routing key do endpoint cấu hình

Trong DSL trên, đường đi outbound được xác định bằng **.exchangeName(...)** và **.routingKey(...)**. Vì thế, thêm một custom header tự đặt tên **routingKey** vào Spring Message không có nghĩa endpoint sẽ tự bỏ qua cấu hình DSL và dùng header đó.

Nếu business thực sự cần route động, phải dùng **routing key expression** hoặc cơ chế định tuyến được endpoint/phiên bản hỗ trợ và kiểm tra rằng giá trị lấy từ **nguồn tin cậy/whitelist**. Không lấy routing key tùy ý từ một message do bên ngoài kiểm soát để publish sang exchange có quyền nhạy cảm.

## 10. RabbitTemplate MessagePostProcessor: xác định raw properties

Khi cần **chứng minh chính xác** basic properties và application headers được đặt ra sao, Spring AMQP **RabbitTemplate** cung cấp lời gọi convertAndSend với **MessagePostProcessor**.

Đây là **đường gửi riêng** so với OrdersHeadersPublisher đi qua MessageChannel ở mục 9; không gọi cả hai cho một sự kiện thật.

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class ExplicitAmqpHeaderPublisher {

    private final RabbitTemplate rabbitTemplate;

    public ExplicitAmqpHeaderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishText() {
        rabbitTemplate.convertAndSend(
            OrdersHeadersTopology.EXCHANGE,
            OrdersHeadersTopology.ROUTING_KEY,
            "evt-1001|O-1001|150000",
            message -> {
                MessageProperties p = message.getMessageProperties();

                p.setContentType(
                    MessageProperties.CONTENT_TYPE_TEXT_PLAIN);
                p.setContentEncoding(
                    StandardCharsets.UTF_8.name());
                p.setMessageId("evt-1001");
                p.setCorrelationId("req-1001");
                p.setDeliveryMode(MessageDeliveryMode.PERSISTENT);

                p.setHeader("eventId", "evt-1001");
                p.setHeader("eventType", "ORDER_CREATED");
                p.setHeader("schemaVersion", 1);

                return message;
            });
    }
}
~~~

Đoạn này đặt trực tiếp **MessageProperties** trên Spring AMQP Message đã được converter tạo. Nó minh họa rõ:

- **messageId/correlationId** là basic properties.
- **eventId/eventType/schemaVersion** là application headers.
- **contentType/contentEncoding** mô tả body text.
- **deliveryMode** có liên quan khả năng lưu bền, nhưng vẫn cần queue policy/loại queue và publisher confirms cho hợp đồng độ tin cậy.

### 10.1. PostProcessor không thay policy mapper của mọi adapter

MessagePostProcessor áp dụng cho lời gọi RabbitTemplate sử dụng nó. Việc tạo một bean publisher tùy chỉnh **không tự thay đổi header mapper** của tất cả AMQP outbound adapters trong ứng dụng. Ngược lại, tùy chỉnh header mapper của một endpoint không nhất thiết được RabbitTemplate direct call sử dụng.

### 10.2. Về charset

Với converter mặc định hỗ trợ String, body thường được mã hóa theo charset được converter cấu hình. **Chỉ đặt contentEncoding sau khi bytes đã được tạo không mã hóa lại body**; trong production, phải cấu hình converter dùng đúng UTF-8 và xác minh bytes thực tế. Trong test sau, dùng ký tự tiếng Việt có dấu để phát hiện mismatch charset.

### 10.3. Nếu payload là JSON DTO

Thay String converter bằng JSON converter tương thích với phiên bản Spring AMQP/Jackson đang dùng. Converter có thể tự đặt contentType, type metadata và các header phục vụ deserialize. Không nên ép một JSON String đã serialize qua JSON converter lần nữa nếu điều đó biến JSON object thành JSON string literal.

Khi dùng DTO, schemaVersion và eventType vẫn cần được validate độc lập với metadata converter như __TypeId__.

## 11. Java DSL inbound: đọc headers đã được ánh xạ

Ta cấu hình một listener container của Spring AMQP nhận từ **orders.created.q**, sau đó AMQP inbound adapter đưa message vào **DirectChannel**.

### 11.1. Listener container

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersHeadersListenerConfig {

    @Bean("ordersHeadersContainer")
    public SimpleMessageListenerContainer ordersHeadersContainer(
            ConnectionFactory connectionFactory) {

        SimpleMessageListenerContainer container =
            new SimpleMessageListenerContainer(connectionFactory);

        container.setQueueNames(OrdersHeadersTopology.QUEUE);
        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(4);
        container.setPrefetchCount(8);
        container.setAcknowledgeMode(AcknowledgeMode.AUTO);
        container.setDefaultRequeueRejected(false);

        return container;
    }
}
~~~

Trong ví dụ này, **AUTO ACK** có nghĩa container chịu trách nhiệm ACK/NACK theo kết quả callback listener, không có nghĩa RabbitMQ ACK ngay khi giao. Đặt **defaultRequeueRejected(false)** tránh một số vòng requeue vô hạn khi exception được container xử lý theo mặc định, **không tự tạo DLX/DLQ**. Nếu muốn message lỗi được lưu, phải có dead-letter topology và test riêng.

### 11.2. Inbound IntegrationFlow

~~~java
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
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
public class OrdersHeadersInboundFlow {

    @Bean
    public MessageChannel ordersInbound() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow inboundOrdersWithHeaders(
            @Qualifier("ordersHeadersContainer")
            SimpleMessageListenerContainer container,
            OrdersHeaderInspector inspector) {

        return IntegrationFlow
            .from(Amqp.inboundAdapter(container))
            .channel("ordersInbound")
            .handle(String.class, (payload, headers) -> {
                inspector.accept(payload, headers);
                return null;
            })
            .get();
    }
}
~~~

**Kỳ vọng đầu vào:** với text/plain và converter phù hợp, payload ở handler là String. Nếu application JSON converter đang được cấu hình để phát byte[] hoặc DTO, phải thay input type/transformer. Không ép kiểu dựa trên giả định khi chưa kiểm tra consumer nhận dữ liệu gì.

### 11.3. Inspector sử dụng header đúng mục đích

~~~java
import java.util.Map;

import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.stereotype.Service;

@Service
public class OrdersHeaderInspector {

    public void accept(
            String payload, Map<String, Object> headers) {

        // Contract demo: eventId|orderId|totalVnd
        String[] fields = payload.split("\\|", -1);
        if (fields.length != 3
                || fields[0].isBlank()
                || fields[1].isBlank()) {
            throw new IllegalArgumentException(
                "Invalid OrderCreated payload");
        }

        Object eventType = headers.get("eventType");
        Object schemaVersion = headers.get("schemaVersion");

        // Mandatory wire headers: require that inbound mapper
        // actually exposed them with these names.
        if (!"ORDER_CREATED".equals(eventType)
                || !(schemaVersion instanceof Number)
                || ((Number) schemaVersion).intValue() != 1) {
            throw new IllegalArgumentException(
                "Unsupported or missing AMQP header contract");
        }

        Object receivedKey =
            headers.get(AmqpHeaders.RECEIVED_ROUTING_KEY);
        Object correlationId =
            headers.get(AmqpHeaders.CORRELATION_ID);

        // Metadata helps tracing, not authorization.
        System.out.println(
            "eventId=" + fields[0]
                + ", receivedKey=" + receivedKey
                + ", correlationId=" + correlationId);

        // Real application: validate and commit business transaction.
        // Only then let synchronous callback finish for AUTO ACK.
    }
}
~~~

**Điều kiện để chạy đúng:** outbound sender phải đưa custom headers **eventType** và **schemaVersion** sang AMQP, inbound mapper phải đưa chúng vào Spring MessageHeaders tương ứng. Hai quy tắc đó cần **integration test với broker thực**. Nếu một mapper bị cấu hình whitelist khác, inspector sẽ fail fast thay vì giả vờ message có schema đúng.

**Dấu receivedRoutingKey:** dùng hằng **AmqpHeaders.RECEIVED_ROUTING_KEY** thay vì một chuỗi tự đoán, và chấp nhận nó có thể thiếu ở cấu hình/version không hỗ trợ mapping tương ứng. Không dùng routing key từ broker làm bằng chứng caller được quyền cập nhật một tenant cụ thể.

### 11.4. Nếu không muốn phụ thuộc application header mapping?

Đưa **eventId/eventType/schemaVersion** vào một **envelope ở body**, sau đó transformer parse và validate bằng schema được consumer kiểm soát. Headers tiếp tục dành cho trace context, AMQP basic properties và thông tin vận hành.

Ví dụ:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 1,
  "data": { "orderId": "O-1001", "totalVnd": 150000 }
}
~~~

Nếu vẫn mirror fields lên headers để route nhanh, nên có test bảo đảm giá trị header **không mâu thuẫn** với envelope.

## 12. Tùy chỉnh header mapping theo chính sách

Default header mapper giúp giảm cấu hình; custom mapping phù hợp khi có **hợp đồng bắt buộc, dữ liệu không tin cậy hoặc các header cần đổi tên/kiểu**.

### 12.1. Những câu hỏi phải trả lời trước khi viết mapper

1. Header nào được phép đi từ **Spring Message** sang AMQP?
2. Header nào được chấp nhận khi **RabbitMQ delivery** đi vào flow?
3. Header nào là **standard AMQP property**, header nào là **application header**?
4. Những header nào chỉ có khi consumer nhận delivery và **không được publish lại**?
5. Khi giá trị thiếu/sai kiểu, **reject** hay dùng default được hợp đồng cho phép?
6. Có cần đổi tên **eventType → businessEventType** hay không? Đổi tên làm mất tương thích với consumer cũ thế nào?
7. SchemaVersion được biểu diễn bằng Number hay String? Có chấp nhận Long/Integer/byte theo bridge AMQP không?
8. Header nào cần tồn tại sau bước transformer/router?
9. Có hạn chế tổng số header, kích thước String/byte[] và nested value không?
10. Header tin cậy đến đâu và liệu nó có thể ảnh hưởng **authorization** hay không?

### 12.2. Không dựa vào một tên method API tưởng tượng

Tùy phiên bản, Spring Integration AMQP có **DefaultAmqpHeaderMapper**, header-mapper SPI và cấu hình endpoint/DSL tương ứng. Tên setter/builder và tập header mặc định có thể khác nhau giữa các phiên bản. Khi tùy chỉnh mapper, phải chọn một cách được **chính phiên bản thư viện** hỗ trợ rồi test raw properties; không copy máy móc code header mapper của HTTP/JMS sang AMQP.

Một **hợp đồng mapping** có thể được mô tả rõ trước khi viết implementation:

| Nguồn | Đích | Chính sách |
| --- | --- | --- |
| Spring header eventType | AMQP app header eventType | String, tối đa kích thước đã quy định |
| Spring header schemaVersion | AMQP app header schemaVersion | Số nguyên dương thuộc versions hỗ trợ |
| Spring header eventId | AMQP app header eventId hoặc messageId | String ổn định; format kiểm tra |
| Spring AmqpHeaders.CORRELATION_ID | AMQP basic property correlation-id | Chỉ phục vụ workflow/tracing |
| Spring header traceparent | AMQP app header traceparent | Chuỗi W3C đúng format; optional |
| Spring replyChannel/errorChannel | Không map trực tiếp | Header runtime nội bộ |
| Inbound receivedRoutingKey | Spring AmqpHeaders.RECEIVED_ROUTING_KEY | Chỉ đọc, phục vụ quan sát |
| Inbound deliveryTag/Channel | Header nội bộ phục vụ MANUAL ACK nếu hỗ trợ | Không lưu/publish lại |

### 12.3. Mapping có thể do một Spring Integration transformer chuẩn hóa

Nếu message đi từ HTTP/SFTP vào AMQP, một transformer trước outbound adapter có thể xây lại Spring Message với **chỉ những header được cho phép**; các bước còn lại dùng mapper của AMQP endpoint.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class EventHeaderNormalizer {

    public Message<String> normalize(
            String payload, String eventId) {

        return MessageBuilder.withPayload(payload)
            .setHeader("eventId", eventId)
            .setHeader("eventType", "ORDER_CREATED")
            .setHeader("schemaVersion", 1)
            .build();
    }
}
~~~

**Chú ý:** MessageBuilder tạo Spring Message mới vẫn có các header nội bộ cần thiết, và việc các custom headers đi qua AMQP tùy header mapper. Transformer **không phải** sự thay thế tự động cho AMQP mapper; nó giúp loại bớt header đầu vào trước khi tới biên.

### 12.4. Cẩn thận khi chuyển đổi kiểu

AMQP field table có bộ kiểu dữ liệu hỗ trợ riêng. Một header dạng **ObjectMapper**, **Throwable**, **MessageChannel** hoặc ORM entity không phải giá trị wire an toàn. Ngay với **schemaVersion**, dữ liệu có thể được biểu diễn dưới kiểu số khác nhau ở hai phía; consumer nên validate bằng **Number** rồi kiểm tra range thay vì ép cứng mọi trường hợp thành Integer mà không test.

Nếu cần object phức tạp, hãy serialize có chủ đích vào **payload** với schema, hoặc đổi thành một header String nhỏ được định nghĩa rõ. Đừng dựa vào Java native serialization của header để trao đổi liên dịch vụ.

## 13. CorrelationId, replyTo và AMQP gateway request–reply

**Correlation** là một trong những lý do quan trọng nhất để hiểu header mapping. Tuy nhiên, có nhiều ID mang chữ “correlation” nhưng khác ngữ nghĩa:

| Định danh | Thuộc lớp | Mục đích |
| --- | --- | --- |
| **Spring MessageHeaders.ID** | Spring Messaging | ID của Spring Message trong flow |
| **AMQP messageId** | Basic property | Định danh một message theo producer contract |
| **AMQP correlationId** | Basic property | Ghép request/reply hoặc workflow nếu contract quy định |
| **AMQP replyTo** | Basic property | Địa chỉ AMQP để consumer/gateway gửi reply |
| **Publisher CorrelationData ID** | Spring AMQP publisher confirms | Ghép một lần publish với confirm/return của broker |
| **eventId** | Business payload/header | Idempotency cho một event qua retry |
| **traceId/spanId** | Distributed tracing | Liên kết các spans và log xuyên hệ thống |

**Không có quy tắc chung rằng tất cả các ID này đều phải bằng nhau.** Có thể chủ động đặt một vài giá trị giống nhau theo hợp đồng, nhưng phải mô tả phạm vi và vòng đời của từng định danh.

### 13.1. Outbound adapter không tự có business reply

Một **AMQP outbound channel adapter** thường publish một chiều. Nếu broker gửi **publisher confirm ACK**, điều đó là tín hiệu cho lần publish, không phải reply nghiệp vụ.

Một **AMQP outbound gateway** gửi request và chờ reply theo hợp đồng AMQP request–reply, nơi replyTo/correlationId và timeout trở nên quan trọng.

~~~mermaid
sequenceDiagram
    participant C as HTTP/Service caller
    participant OG as AMQP outbound gateway
    participant B as RabbitMQ
    participant IG as AMQP inbound gateway
    participant S as QuoteService
    C->>OG: Request Quote
    OG->>B: Publish request + replyTo/correlation
    B->>IG: Request delivery
    IG->>S: Request Spring Message
    S-->>IG: Business reply
    IG->>B: Publish reply to replyTo
    B-->>OG: Reply delivery
    OG-->>C: Matching response
~~~

### 13.2. Reply-to không phải Spring replyChannel

Trong Spring Integration, **replyChannel** là header nội bộ chỉ nơi nhận reply trong Spring Messaging. Ở AMQP, **replyTo** là property dùng để gửi reply trên broker; gateway có thể quản lý đường map giữa hai thế giới.

Không đưa một object **DirectChannel**, **TemporaryReplyChannel** hay tên Spring channel bất kỳ vào AMQP application header và nghĩ rằng broker sẽ tự route tới channel đó. Cần để AMQP gateway quản lý correlation/reply address theo APIs và cấu hình phiên bản.

### 13.3. Không tự override replyTo/correlationId khi gateway quản lý

Một gateway có thể dùng reply container, reply-to address hoặc cơ chế direct reply-to tùy cấu hình và phiên bản. Nếu custom header mapper hoặc transformer tự sửa **replyTo/correlationId** mà không hiểu cơ chế gateway đang dùng, reply có thể:

- Không tới đúng destination.
- Tới nhưng không được ghép với request đang chờ.
- Bị timeout dù consumer đã xử lý thành công.
- Bị nhầm giữa hai requests khi application xử lý đồng thời.

Khi tùy biến, phải test **nhiều requests song song**, các response đến lệch thứ tự, timeout, delayed reply và consumer restart. Không chỉ test một request success.

### 13.4. CorrelationData không phải AMQP correlationId

Spring AMQP **CorrelationData** được dùng theo dõi publisher confirms/returns theo lần publish. CorrelationData ID **không mặc nhiên** được copy thành AMQP basic property correlationId; muốn sử dụng cùng một giá trị cần quy tắc rõ và code/cấu hình chuyển phù hợp.

Do đó một message có thể có:

~~~text
eventId:             evt-1001
messageId:           evt-1001
correlationId:       request-17
publisherAttemptId:  attempt-812
traceId:             4f4c...
~~~

Producer retry có thể tạo **attempt mới** nhưng consumer vẫn nhìn thấy **eventId cũ** để chống trùng.

## 14. Header mapping không thay publisher confirms hoặc consumer ACK

Header mapping làm dữ liệu **có thể được diễn giải và truy vết đúng**. Nó không tự bổ sung cơ chế bảo đảm giao nhận.

~~~mermaid
flowchart LR
    P["Producer"] --> M["AMQP body + headers"]
    M --> EX["RabbitMQ exchange"]
    EX --> Q["Queue"]
    Q --> LC["Consumer listener"]
    LC --> H["Business handler"]
    EX -. "Publisher confirm / return" .-> P
    H -. "Consumer ACK/NACK via listener" .-> Q
~~~

### 14.1. Ba mốc khác nhau

1. **MessageChannel.send hoàn tất:** đã đi qua kênh theo semantics của kênh đó; không tự chứng minh broker confirmed.
2. **Publisher confirm/return:** broker báo kết quả publish hoặc unroutable trong điều kiện tương ứng.
3. **Consumer ACK/NACK:** phía nhận quyết định settlement của delivery theo AUTO/MANUAL mode; có thể sau khi business handler xử lý hoặc sau khi đã lưu bền inbox.

Một AMQP header **messageId=evt-1001** hoặc **correlationId=req-17** không thay thế bất kỳ tín hiệu nào phía trên.

### 14.2. AUTO ACK và DirectChannel

Với AMQP inbound listener container **AcknowledgeMode.AUTO** và handler đồng bộ qua **DirectChannel**, exception của handler có thể lan về listener và ảnh hưởng ACK/NACK theo error policy. Nếu custom header validation fail fast và exception thực sự lan về container, delivery có thể bị reject/requeue theo cấu hình.

Nếu flow dùng **errorChannel** hấp thụ lỗi rồi return bình thường, container có thể thấy callback thành công và ACK. Nếu dùng **ExecutorChannel**, callback có thể hoàn tất sau khi executor chấp nhận task nhưng trước khi business worker chạy. Cần định nghĩa lại **ranh giới ACK**.

### 14.3. MANUAL ACK và Channel header

Một số AMQP inbound endpoints có thể expose native AMQP Channel/deliveryTag phục vụ manual acknowledgment. Khi đó phải:

- Cấu hình listener container **AcknowledgeMode.MANUAL**.
- Dùng đúng channel và delivery tag của **chính delivery**.
- Không serialize hoặc publish lại Channel object.
- Không ACK một tag đã settle hoặc dùng tag trên channel khác.
- Đảm bảo mọi đường lỗi có quyết định ACK/NACK/reject phù hợp.

Đừng dùng receivedRoutingKey hoặc messageId làm delivery tag. Manual ACK vẫn không tự tạo transaction nguyên tử với database; cần idempotency khi broker redeliver.

### 14.4. Metadata khi redelivery

Khi broker giao lại message, delivery tag và những metadata consumer-side có thể thay đổi. **eventId** do business contract định nghĩa phải giữ ổn định. Nếu consumer dùng Spring MessageHeaders.ID của lần nhận làm idempotency key, nó có thể ghi trùng vì ID Spring Message mới không nhất thiết giống lần nhận trước.

## 15. Header tracing giữa HTTP, AMQP và Kafka

Một luồng thường gặp:

~~~mermaid
flowchart LR
    HTTP["HTTP request<br/>traceparent"] --> H["HTTP inbound gateway"]
    H --> SI["Spring Message<br/>trace context"]
    SI --> AM["AMQP outbound adapter"]
    AM --> MQ["RabbitMQ"]
    MQ --> C["AMQP inbound adapter"]
    C --> K["Kafka outbound adapter"]
    K --> KC["Kafka consumer"]
~~~

Nếu trace context được phát qua **application headers**, các hệ thống có thể nối spans của cùng một chuỗi tác vụ. Tuy nhiên:

- **traceparent/tracestate** là metadata observability, không phải authorization.
- Không phải tất cả adapter đều dùng cùng tên header hoặc cùng quy tắc mapping.
- Một OpenTelemetry/Micrometer instrumentation có thể quản lý propagation thay bạn; tự ghi đè traceparent có thể phá trace context đang có.
- Cần kiểm tra giới hạn kích thước headers để tránh tạo payload/header quá lớn khi đi qua nhiều giao thức.
- Không copy nguyên khối HTTP headers (Cookie, Authorization, X-Forwarded-*) vào AMQP mà không có whitelist.

### 15.1. Phân biệt traceId với correlationId

TraceId liên kết spans để quan sát luồng phân tán. CorrelationId AMQP có thể dùng ghép một request với reply trong messaging. Chúng **có thể liên quan** nhưng không bắt buộc đồng nhất. Một business workflow có thể có nhiều requests/retries, nhiều messageId/correlationId nhưng cùng eventId hoặc traceId theo chính sách.

### 15.2. Bảo toàn trace context khi retry

Khi retry qua RabbitMQ hoặc DLQ, có thể cần giữ trace context để debug, nhưng cũng phải tạo span mới cho **lần xử lý mới** theo instrumentation. Không tái sử dụng spanId bừa bãi như thể cùng một thao tác chưa bao giờ kết thúc.

### 15.3. Không dùng trace headers cho quyết định nghiệp vụ

Một header traceparent sai/giả mạo không được khiến consumer chấp nhận thanh toán, bỏ qua validation hay thay đổi tenant của dữ liệu. Tất cả header ngoài boundary phải được coi là input chưa tin cậy cho đến khi hệ thống xác minh theo cơ chế riêng.

## 16. Bảo mật và giới hạn kiểu dữ liệu

AMQP headers là dữ liệu đến từ producer, broker hoặc mapper. Không coi chúng là bằng chứng đáng tin cho role, tenant, quyền truy cập hoặc kết quả xử lý.

### 16.1. Các trường hợp nguy hiểm

~~~text
application header:
  role = ADMIN
  tenantId = another-company
  __TypeId__ = unexpected.Java.Class
  retryCount = 0
  replyTo = arbitrary.queue
~~~

Những giá trị này có thể bị producer gửi sai hoặc cố tình thao túng. Với consumer nhiều tenant, **tenant authorization** phải dựa vào identity/ACL và business policy tin cậy, không chỉ một header String từ RabbitMQ.

### 16.2. Whitelist trước khi đưa vào business

Ví dụ một bộ quy tắc:

| Header | Chấp nhận | Kiểm tra |
| --- | --- | --- |
| eventType | Các tên event contract đã định nghĩa | String, enum allowlist |
| schemaVersion | Những version thực sự hỗ trợ | Number, range rõ |
| eventId | Định danh có format/độ dài giới hạn | Unique scope, checksum nếu cần |
| traceparent | Optional | Độ dài và định dạng W3C phù hợp |
| x-death | Metadata vận hành theo broker | Không dùng làm idempotency/authorization |
| __TypeId__ | Chỉ theo converter/type mapper tin cậy | Whitelist target DTO, không trust all |
| replyTo | Chỉ nơi trả reply theo contract/gateway | Không cho phép publish tới đích không được kiểm soát |
| Authorization/Cookie | Không truyền qua AMQP mặc định | Loại bỏ hoặc dùng token chuyên biệt an toàn |

### 16.3. Header lớn hoặc sai kiểu

Không đặt object tùy ý vào header; AMQP field table có tập kiểu dữ liệu giới hạn. Một Map lồng sâu, object Throwable hoặc blob lớn có thể gây lỗi serialization/conversion và tăng network/memory.

Nên giới hạn:

- Số lượng header.
- Độ dài key và String value.
- Kiểu value được cho phép.
- Payload/header tổng và độ sâu nested data.
- Những metadata cần retention khi dead-letter/replay.

Nếu cần chứa tài liệu lớn, dùng payload hoặc tham chiếu object storage, không nhét file vào application headers.

### 16.4. Logging và PII

Không log raw application headers không chọn lọc; chúng có thể chứa thông tin người dùng, token, session hoặc nội dung nhạy cảm. Nên log **eventId/eventType/schemaVersion/receivedRoutingKey/errorCode** theo chính sách dữ liệu, mask những trường không cần thiết.

### 16.5. Chống xung đột giữa trusted và untrusted header

Nếu một inbound adapter nhận **tenantId** từ RabbitMQ và phía HTTP/API gateway đã xác thực một tenant khác, đừng chọn tenant tùy tiện bằng “header nào đến sau thắng”. Cần định nghĩa nguồn sự thật và kiểm tra sự nhất quán; nếu khác thì reject hoặc đưa vào luồng điều tra.

## 17. Header mapping khi retry, requeue và dead-letter

Một message có thể gặp các trạng thái:

~~~mermaid
flowchart LR
    P["Publisher"] --> X["Main exchange"]
    X --> Q["Main queue"]
    Q --> C["Consumer"]
    C -->|"ACK"| OK["Hoàn tất delivery"]
    C -->|"NACK requeue=true"| Q
    C -->|"NACK requeue=false"| DLX["Dead-letter exchange"]
    DLX --> DLQ["DLQ"]
    DLQ --> R["Replay có kiểm soát"]
    R --> X
~~~

### 17.1. Requeue cùng delivery và republish là hai việc khác nhau

**Requeue** yêu cầu broker giao lại một delivery đang tồn tại; nó không có nghĩa application đã serialize một Spring Message mới. **Republish** tạo một lần AMQP publish mới, có thể với properties/headers khác.

Khi republish, nếu code xây một AMQP Message mới từ payload và quên copy eventId/schemaVersion, consumer có thể không xác thực được nguồn dữ liệu hoặc không nhận diện duplicate. Nếu copy toàn bộ metadata cũ, có thể mang theo **deliveryTag, receivedRoutingKey, x-death, replyTo** hoặc những header không phù hợp.

**Cách đúng:** tái tạo những **business/trace headers được cho phép** theo contract, giữ eventId ổn định, tạo attemptId mới khi tracking cần và để broker/adapter tạo delivery metadata mới.

### 17.2. DLX không phải một header

Dead-letter exchange là **exchange name trong cấu hình queue/policy**, không phải một custom header eventType=FAILED mà RabbitMQ đọc để tự chọn DLQ. Broker quyết định dead-letter từ những điều kiện và cấu hình queue; **x-dead-letter-exchange** và **x-dead-letter-routing-key** là những queue arguments/policy phù hợp.

Một consumer NACK với **requeue=false** có thể khiến message đi vào DLX nếu topology hợp lệ. Đặt một header **dlq=true** lên message thường không có tác dụng tương đương.

### 17.3. x-death, headers phát sinh khi dead-letter

RabbitMQ có thể thêm metadata lịch sử dead-letter như **x-death** và các thông tin first/last death theo phiên bản. Những header này giúp điều tra **queue, reason và lịch sử**; không phải hợp đồng idempotency hay chứng cứ business đã xử lý.

- Lỗi cố định: reject không requeue, cách ly vào final DLQ theo topology.
- Lỗi transient: retry hữu hạn, có backoff; có thể chuyển sang retry queue/jobserver.
- Retry queue TTL có thể dead-letter trở lại main exchange sau khi message hết hạn.
- Mọi vòng main → retry → main phải có điểm dừng, không chỉ dựa vào x-death count.

### 17.4. Đừng mạo danh broker metadata

Header như **redelivered**, **x-death** hoặc **deliveryTag** không nên được application tạo tùy ý để tự khẳng định message đã được xử lý mấy lần. Nếu cần tổng số business attempts qua restart, lưu **attempt counter bền vững** do ứng dụng kiểm soát, hoặc cơ chế delivery limit được broker hỗ trợ và đã kiểm chứng.

### 17.5. Replay từ DLQ nên giữ gì?

| Dữ liệu | Khi replay |
| --- | --- |
| eventId | Giữ nguyên để consumer nhận diện duplicate |
| eventType/schemaVersion | Giữ hoặc migrate có kiểm soát theo hợp đồng mới |
| Payload | Sửa nếu lỗi dữ liệu; ghi audit về sửa đổi |
| traceparent | Có thể tạo trace/span mới theo instrumentation, liên kết lại lịch sử |
| messageId | Theo chính sách có thể giữ eventId hoặc tạo message ID mới cho attempt |
| correlationId/replyTo | Chỉ giữ nếu workflow còn hợp lệ; không gửi reply vào destination đã hết thời hạn |
| deliveryTag/consumerQueue/receivedRoutingKey | Không sao chép như publisher-supplied metadata |
| x-death | Dùng để chẩn đoán, không dùng làm business ID hoặc reset tùy tiện |

Khi sửa payload rồi giữ eventId, cần có chính sách xử lý **same ID, changed content**: lưu audit/hash, version và quyết định replay có được phép coi là cùng sự kiện sau sửa lỗi hay không.

## 18. Lỗi header mapping xảy ra ở đâu?

| Vị trí | Lỗi điển hình | Cách quan sát và xử lý |
| --- | --- | --- |
| **Spring Message creation** | Header bắt buộc thiếu hoặc sai kiểu | Validate trước khi gửi vào outbound channel |
| **Outbound header mapper** | Không map được object, header bị lọc | Test raw AMQP MessageProperties, cấu hình allowlist |
| **AMQP converter** | Body JSON sai định dạng, contentType không khớp | Chọn converter và contract phù hợp |
| **RabbitTemplate publish** | Giá trị header không hỗ trợ, exchange sai | Exception synchronous, publisher confirms/returns tùy loại |
| **Broker routing** | Binding không khớp | Publisher return khi mandatory/returns, alternate exchange |
| **Inbound converter** | Type metadata không tin cậy, decode lỗi | Listener error handler, retry/DLQ theo policy |
| **Inbound header mapper** | Không expose header mà handler mong đợi | Fail fast, contract test, kiểm tra mapper |
| **Transformer/validator** | Header schemaVersion mâu thuẫn payload | Reject/cách ly dữ liệu, không retry nóng |
| **Service activator** | Header hợp lệ nhưng DB/API lỗi | Retry bounded, transaction, idempotency |
| **AMQP gateway reply** | Correlation/replyTo bị thay đổi | Reply không match, timeout, kiểm tra gateway |

### 18.1. Lỗi trước khi có Spring Message

Nếu inbound MessageConverter hoặc header mapper thất bại trước khi adapter tạo Spring Message, handler trong IntegrationFlow **có thể chưa được gọi**, nên một try/catch bao quanh business handler không bắt được lỗi này.

Vì thế cần hiểu **Spring AMQP listener error handler** và các exception fatal/retryable theo phiên bản, cùng chính sách ACK/NACK và DLX. Không giả định errorChannel ở giữa flow bắt được mọi lỗi transport/conversion.

### 18.2. ErrorChannel hấp thụ lỗi

Nếu handler ném exception nhưng custom errorChannel xử lý rồi kết thúc bình thường, container AUTO ACK có thể coi listener callback đã hoàn tất. Một message header sai bị log error chưa chắc được broker requeue hoặc dead-letter.

Điều cần kiểm tra trong integration test:

1. Exception có đi ngược tới listener container hay không?
2. Container dùng AUTO hay MANUAL ACK?
3. Error handler có reject không requeue hay có retry?
4. DLX/DLQ có route message lỗi thật không?
5. Consumer business state đã commit hay rollback?

### 18.3. Retry lỗi schema bao nhiêu lần?

**Thiếu eventType**, **schemaVersion không hỗ trợ**, **type metadata ngoài allowlist** thường là lỗi dữ liệu cố định; requeue liên tục không làm headers tự sửa.

**Database tạm thời lỗi** là chuyện khác; handler có thể retry hữu hạn với backoff, rồi chuyển sang retry queue hoặc DLQ theo hợp đồng. Header mapper chỉ giúp metadata đi đúng, không có trách nhiệm tự chọn retry policy nghiệp vụ.

## 19. Unit test, contract test và integration test

Một bài học về header mapping phải kiểm tra **raw AMQP properties**, không chỉ so sánh Spring Message ở đầu và cuối flow.

### 19.1. Unit test MessageProperties

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.MessageProperties;

class AmqpPropertiesUnitTest {

    @Test
    void basicPropertiesAndApplicationHeadersAreDifferent() {
        MessageProperties p = new MessageProperties();
        p.setMessageId("evt-1001");
        p.setCorrelationId("req-1001");
        p.setHeader("eventType", "ORDER_CREATED");
        p.setHeader("schemaVersion", 1);

        assertEquals("evt-1001", p.getMessageId());
        assertEquals("req-1001", p.getCorrelationId());
        assertEquals(
            "ORDER_CREATED", p.getHeaders().get("eventType"));
        assertTrue(p.getHeaders().get("schemaVersion") instanceof Number);
    }
}
~~~

Test này chỉ kiểm tra API MessageProperties, **chưa thử Spring Integration mapper hoặc broker**.

### 19.2. Integration test đọc raw RabbitMQ message

Trong broker test cô lập, không khởi chạy một consumer khác trên queue, dùng RabbitTemplate gửi rồi receive message dạng Spring AMQP Message:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

class AmqpRawHeaderContractTest {

    private final RabbitTemplate rabbitTemplate;

    AmqpRawHeaderContractTest(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @Test
    void rawPropertiesMatchContract() {
        rabbitTemplate.convertAndSend(
            OrdersHeadersTopology.EXCHANGE,
            OrdersHeadersTopology.ROUTING_KEY,
            "evt-1001|O-1001|150000",
            m -> {
                MessageProperties p = m.getMessageProperties();
                p.setContentType(
                    MessageProperties.CONTENT_TYPE_TEXT_PLAIN);
                p.setContentEncoding(StandardCharsets.UTF_8.name());
                p.setMessageId("evt-1001");
                p.setHeader("eventType", "ORDER_CREATED");
                p.setHeader("schemaVersion", 1);
                return m;
            });

        Message amqp = rabbitTemplate.receive(
            OrdersHeadersTopology.QUEUE, 2000L);

        assertNotNull(amqp);
        MessageProperties p = amqp.getMessageProperties();
        assertEquals("evt-1001", p.getMessageId());
        assertEquals(
            "ORDER_CREATED", p.getHeaders().get("eventType"));
        assertEquals(
            1,
            ((Number) p.getHeaders().get("schemaVersion")).intValue());
        assertEquals(
            MessageProperties.CONTENT_TYPE_TEXT_PLAIN,
            p.getContentType());
        assertEquals(
            "evt-1001|O-1001|150000",
            new String(amqp.getBody(), StandardCharsets.UTF_8));
    }
}
~~~

**Cách chạy đúng:** Đây là một test method minh họa cần Spring test context/extension và RabbitTemplate được inject từ bean test, RabbitMQ broker thực, topology do test provision, và **không có listener khác đang tiêu thụ cùng queue**. Trong môi trường cần kiểm tra encoding, hãy cấu hình text converter dùng UTF-8 tương thích, không chỉ đặt contentEncoding.

**RabbitTemplate.receive là thao tác tiêu thụ**, không phải xem dữ liệu không thay đổi. Không chạy test này trên queue production.

### 19.3. Test riêng Spring Integration outbound mapping

Test mục 19.2 xây AMQP properties tường minh bằng MessagePostProcessor, nên **nó không tự chứng minh header mapper của outbound adapter ở mục 9** đã làm đúng.

Để test mapper:

1. Chạy OrdersHeadersOutboundFlow với RabbitMQ và test queue, **không chạy inbound consumer** cùng queue đó.
2. Gọi OrdersHeadersPublisher.publish() để gửi Spring Message có custom headers.
3. Đọc raw AMQP Message từ test queue và kiểm tra **getHeaders().get("eventType")**, schemaVersion, eventId, contentType và mọi basic property cần thiết.
4. Nếu field thiếu, kiểm tra header mapper của endpoint và danh sách outbound mappings trong phiên bản đang dùng.
5. Không giải quyết bằng cách hardcode dữ liệu ở handler test rồi tuyên bố mapper đã đúng.

### 19.4. Test inbound mapping

Để kiểm tra chiều ngược lại:

1. Dùng RabbitTemplate direct publish một AMQP Message có **basic properties** và **application headers** đã biết.
2. Chạy AMQP inbound adapter với một handler test nhận Spring MessageHeaders.
3. Kiểm tra các header bắt buộc được expose đúng tên/kiểu; đối chiếu với **AmqpHeaders** của phiên bản.
4. Thử header thiếu, sai type, sai version và custom header không nằm trong allowlist.
5. Kiểm tra error outcome: ACK/requeue/DLQ đúng theo policy, không bị nuốt exception.

### 19.5. Test sự khác nhau giữa ID

Một contract test nên tạo:

~~~text
eventId           = evt-1001
messageId         = msg-10
correlationId     = req-17
publisherAttempt  = attempt-82
traceId           = trace-xyz
~~~

Sau đó xác minh application:

- Dùng **eventId** để chống trùng.
- Dùng **correlationId** cho request–reply/workflow theo contract.
- Dùng **CorrelationData** của lần publish để ghép confirms.
- Dùng **traceparent**/traceId cho observability.
- Không dùng MessageHeaders.ID hoặc deliveryTag để thay tất cả các định danh trên.

### 19.6. Test hai phiên bản producer/consumer

Khi thêm **schemaVersion=2**, producer mới và consumer cũ có thể chạy song song trong nhiều giờ. Cần test:

| Producer | Consumer | Kết quả kỳ vọng |
| --- | --- | --- |
| v1 | v1 | Parse đúng |
| v1 | v2 | Vẫn nhận v1 nếu còn hỗ trợ |
| v2 | v1 | Từ chối có kiểm soát hoặc vẫn tương thích theo contract |
| v2 | v2 | Parse đúng v2 |
| Header version 2, payload v1 | v1/v2 | Phát hiện conflict theo chính sách |
| Header eventType không hợp lệ | v1/v2 | Không route vào handler đặc quyền |

Không chỉ kiểm tra JSON DTO deserialize; cần test **header mapper và header type** ở cả hai phía.

## 20. Chẩn đoán sự cố header mapping trong production

Một số triệu chứng trông giống lỗi RabbitMQ nhưng nguyên nhân thực sự là metadata mapping.

| Triệu chứng | Giả thuyết | Cách phân biệt |
| --- | --- | --- |
| Handler báo thiếu eventType | Outbound không map hoặc inbound filter header | Đọc raw AMQP properties trước, rồi Spring MessageHeaders |
| schemaVersion đổi từ Number sang String | Producer/header converter thay định dạng | Contract test từng phiên bản và giới hạn kiểu |
| JSON converter không tạo DTO | contentType sai, __TypeId__ sai/trust không hợp lệ | Kiểm tra body bytes, basic properties, converter logs |
| Gateway timeout dù service trả reply | replyTo/correlationId bị đổi hoặc reply không route | Trace request/reply properties và gateway correlation |
| Message đi vào queue sai | Exchange/routing key expression không đúng | Kiểm tra outbound endpoint và broker bindings |
| Chỉ mất trace sau AMQP hop | Trace context không được propagate hoặc mapper filter | So sánh traceparent trước và sau hop |
| Consumer lấy nhầm tenant | Header untrusted bị dùng thay business/auth context | Audit source of truth và policy validation |
| Publisher confirm ACK nhưng consumer không thấy | Confirm chỉ xác nhận publish, chưa chắc route đúng | Kiểm tra mandatory/returns, queue, consumer status |
| Dead-letter rồi replay mất eventId | Republisher không copy business contract | Kiểm tra payload/headers trước/sau retry |
| AMQP channel bị đóng sau ACK | Có thể ACK sai deliveryTag/channel hoặc ACK hai lần | Listener mode, native channel/tag, logs protocol |

### 20.1. Quy trình điều tra một header bị mất

Không nên nhìn handler trước rồi đoán mapper:

1. **Tại nguồn:** Spring MessageHeaders có eventType/schemaVersion chưa?
2. **Tại publisher:** Outbound adapter dùng RabbitTemplate và header mapper nào? Có whitelist không?
3. **Tại RabbitMQ:** Raw AMQP MessageProperties có header cần thiết chưa? Nó nằm trong **basic property** hay **getHeaders()**?
4. **Tại inbound:** MessageConverter có nhận đúng body/contentType không? Header mapper có expose custom key không?
5. **Tại flow:** Transformer/filter/router có tạo Spring Message mới làm mất custom headers không?
6. **Tại handler:** Data type của header có đúng không? Có bị override bởi nguồn ngoài không?
7. **Tại lỗi:** Khi header sai, message ACK, retry hay DLQ? Có hot loop không?

Làm theo thứ tự này giúp phân biệt lỗi **publisher**, **broker**, **mapper inbound** và **business validation** thay vì sửa ngẫu nhiên một lớp.

### 20.2. Đề xuất observability

| Metric/log field | Mục đích |
| --- | --- |
| **missing_required_header_total** | Phát hiện contract bị phá vỡ |
| **invalid_header_type_total** | Theo dõi giá trị header không tương thích |
| **unsupported_schema_version_total** | Cảnh báo producer mới vượt consumer |
| **unexpected_content_type_total** | Nhận diện converter/producer sai |
| **header_mapping_failure_total** | Lỗi converter/header mapper |
| **message_size_bytes / header_count** | Giám sát tải và lạm dụng metadata |
| **publisher_return_total** | Header đúng nhưng route AMQP chưa đúng vẫn bị phát hiện |
| **consumer_requeue_total / dlq_ingress** | Lỗi dữ liệu gây requeue hoặc DLQ |
| **eventId/traceId** | Liên kết log và nghiệp vụ khi được phép |

**Đây là tên metric gợi ý**, không phải cam kết framework tự xuất tất cả. Có thể instrument bằng Micrometer/Observation tùy phiên bản và chiến lược monitoring. Khi đưa eventType/schemaVersion làm metric labels, cần hạn chế cardinality; **không dùng eventId làm label** của metric tổng hợp.

### 20.3. Log thông tin tối thiểu

~~~text
endpoint=ordersInbound
eventType=ORDER_CREATED
schemaVersion=1
eventId=evt-1001
contentType=text/plain
receivedRoutingKey=orders.created
errorCode=MISSING_MANDATORY_HEADER
retryable=false
~~~

Log này là ví dụ về metadata để điều tra; không nên log toàn bộ payload nhạy cảm, Authorization/Cookie hoặc native Channel object. Nếu eventId có thể là thông tin định danh nhạy cảm, phải áp dụng chính sách lưu trữ, mask và truy cập tương ứng.

### 20.4. Prefetch không sửa được mapping

Một số message có header sai khiến listener lỗi, queue ready tăng và DLQ tăng. Tăng **prefetch** hoặc **consumer concurrency** có thể chỉ khiến nhiều message lỗi được nhận/đẩy vào DLQ nhanh hơn. Cần sửa **contract/mapper/converter** trước khi tuning throughput.

### 20.5. Khi nâng cấp framework

Khi nâng Spring Boot, Spring AMQP, Spring Integration hoặc Jackson, phải kiểm tra:

- Header names và những **AmqpHeaders** hiện có.
- Default inbound/outbound header mapping policy.
- Mapping của correlationId, replyTo và request–reply gateway.
- JSON type headers/trusted packages và converter behavior.
- Kiểu dữ liệu application headers sau serialize/deserialize.
- Message còn trong RabbitMQ queue do phiên bản producer cũ gửi.
- Tác động tới error handling, ACK/requeue/DLQ khi header không hợp lệ.

**Không chỉ chạy một happy-path unit test.** Test producer mới → consumer cũ và producer cũ → consumer mới bằng broker test để phát hiện breaking changes.

## 21. Tình huống đa adapter: File/SFTP → AMQP → Kafka

Một công ty nhận file CSV từ đối tác qua SFTP, tạo OrderCreated và phân phối sang Warehouse (RabbitMQ) rồi Analytics (Kafka).

~~~mermaid
flowchart LR
    SFTP["SFTP inbound adapter<br/>poller"] --> PAR["CSV parser"]
    PAR --> ENV["OrderCreated envelope<br/>eventId + schemaVersion"]
    ENV --> O["AMQP outbound adapter"]
    O --> RB["RabbitMQ queue"]
    RB --> I["AMQP inbound adapter"]
    I --> VA["Validate + normalize"]
    VA --> K["Kafka outbound adapter"]
    K --> KC["Analytics consumer"]
~~~

### 21.1. Metadata của SFTP không nên trở thành business header AMQP

Các header của file inbound như tên file, đường dẫn tạm, file-lock/token hoặc trạng thái polling có thể phục vụ quá trình nhập liệu. Không chuyển toàn bộ chúng vào AMQP application headers mà không xét nhu cầu và bảo mật.

Thay vì phụ thuộc đường dẫn file, hãy tạo **eventId**, **eventType**, **schemaVersion**, **sourceSystem** được kiểm soát và lưu trữ checksum/import batch ID nếu contract cần.

### 21.2. AMQP received headers không tự phù hợp với Kafka

Kafka có headers và cơ chế serialization khác RabbitMQ. Khi chuyển từ AMQP inbound sang Kafka outbound:

- Giữ **eventId/eventType/schemaVersion** theo hợp đồng chung.
- Giữ trace context theo instrumentation.
- Không gửi **AmqpHeaders.DELIVERY_TAG**, native Channel, consumer queue hoặc x-death nguyên xi sang Kafka.
- Kafka topic/partition/key cần được xác định theo hợp đồng riêng; không sử dụng receivedRoutingKey như key duy nhất mà không thiết kế.
- Kafka consumer phải có idempotency nếu upstream có thể redeliver/retry.

### 21.3. Khi chuyển tiếp có tính bền vững

Consumer A nhận AMQP message, transformer tạo Spring Message rồi outbound Kafka gửi. Nếu RabbitMQ ACK **trước khi Kafka producer xác nhận kết quả cần thiết**, có thể mất event giữa hai hệ thống. Nếu Kafka đã nhận nhưng RabbitMQ ACK thất bại, có thể gửi trùng.

Header mapping chỉ bảo đảm metadata được diễn giải đúng, **không** giải quyết khoảng trống transaction giữa RabbitMQ và Kafka. Hãy cân nhắc durable inbox/outbox, producer confirms/acks tương ứng và idempotent consumer ở các phía.

### 21.4. Khi nguồn là HTTP thay vì SFTP

HTTP inbound gateway có thể nhận Authorization, Cookie, Host, trace headers và body JSON. Chỉ đưa **header cần thiết theo AMQP contract** vào outbound message. Không copy toàn bộ HTTP headers vào RabbitMQ hoặc để một header người dùng tự gửi quyết định routingKey/tenant đặc quyền.

## 22. Checklist thiết kế header mapping

| Nhóm | Câu hỏi cần xác minh trước production |
| --- | --- |
| **Contract** | eventId/eventType/schemaVersion nằm trong body, headers hay cả hai? |
| **Wire body** | Text, JSON, Avro/Protobuf hay bytes? ContentType/charset cụ thể? |
| **Outbound mapper** | Những Spring MessageHeaders nào được map tới AMQP properties/application headers? |
| **Inbound mapper** | Những AMQP properties nào được expose ở Spring MessageHeaders? |
| **Direction** | Header nào chỉ xuất hiện khi nhận delivery, không hợp lệ khi publish? |
| **Reserved headers** | replyChannel/errorChannel/ID/TIMESTAMP và Channel/tag được loại khỏi wire ra sao? |
| **Correlation** | messageId, correlationId, eventId, publisher attemptId, traceId khác nhau thế nào? |
| **Gateway** | replyTo/correlationId có được gateway quản lý và request–reply đã được test chưa? |
| **Dynamic routing** | Exchange/routing key có lấy từ nguồn tin cậy và allowlist không? |
| **Schema** | Kiểu và giá trị schemaVersion được chuẩn hóa ở cả hai phía chưa? |
| **Security** | Header từ producer ngoài có thể ảnh hưởng role/tenant/privilege không? |
| **Size/type** | Giới hạn số header, kích thước, kiểu dữ liệu và nested objects? |
| **Converter** | MessageConverter có đặt contentType đúng và không double encode? |
| **Errors** | Mapper/converter lỗi trước handler được container xử lý ra sao? |
| **Reliability** | ACK, confirms/returns và DLQ được test theo đúng ranh giới? |
| **Trace** | traceparent/tracestate có được propagate đúng mà không lộ token? |
| **Retry** | Replay có giữ eventId nhưng không copy deliveryTag/channel không? |
| **Monitoring** | Có đo thiếu/sai header, schema conflict, DLQ và conversion failure? |
| **Compatibility** | Producer cũ/consumer mới và producer mới/consumer cũ đã test? |

### 22.1. Quy tắc quyết định nhanh

Nếu một giá trị **định nghĩa ý nghĩa nghiệp vụ của event**, ưu tiên đặt nó trong **payload envelope có schema** hoặc ít nhất bảo đảm hợp đồng ổn định qua các protocol adapters. Nếu một giá trị **phục vụ giao thức**, dùng standard AMQP property đúng chức năng. Nếu một giá trị **chỉ tồn tại trong một delivery/session**, không phát nó như metadata bền vững.

### 22.2. Khi nào không cần custom header mapper?

Nếu hệ thống dùng ít metadata, một producer và consumer cùng version và default mapper đã đáp ứng contract được kiểm thử, custom mapper có thể làm tăng độ phức tạp không cần thiết. Nhưng nếu header phải đi qua nhiều ngôn ngữ, versions, gateway, hoặc có yêu cầu bảo mật, **mapping policy explicit + contract test** sẽ giúp giảm rủi ro.

## 23. Những sai lầm thường gặp

**“Spring MessageHeaders chính là RabbitMQ application headers.”** Spring MessageHeaders nằm trong ứng dụng; AMQP message có basic properties và field table. Header mapper phải quyết định những metadata được chuyển.

**“Đặt MessageBuilder.setHeader là đủ để broker nhận đúng.”** Có thể bị filter, đổi tên/kiểu hoặc không được map. Phải test raw MessageProperties.

**“MessageProperties.getHeaders() chứa mọi standard property.”** messageId, correlationId, replyTo, contentType là standard AMQP properties riêng; chúng không mặc nhiên là entries cùng tên trong application headers.

**“AmqpHeaders.CORRELATION_ID là business eventId.”** Correlation ID có thể dùng ghép request/reply; eventId dùng idempotency theo contract.

**“Publisher CorrelationData ID luôn là AMQP correlationId.”** CorrelationData phục vụ confirms/returns của lần publish; muốn cùng giá trị cần thiết kế mapping rõ ràng.

**“MessageHeaders.ID giữ nguyên khi một event được retry.”** Một Spring Message mới có thể có ID mới; eventId nghiệp vụ phải được giữ độc lập.

**“replyChannel và replyTo là cùng một header.”** Một bên thuộc Spring Messaging runtime, một bên là AMQP basic property. Gateway mới chịu trách nhiệm bridge theo cấu hình.

**“AMQP inbound gateway tự trả đúng reply dù sửa correlationId tùy ý.”** Override metadata gateway quản lý có thể làm reply không khớp request hoặc timeout.

**“receivedRoutingKey là outbound routing key mặc định.”** Nó mô tả delivery đã nhận. Khi publish lại, routing key phải được chọn theo hợp đồng outbound.

**“Consumer phải tin mọi eventType/schemaVersion vì producer ở cùng broker.”** Broker không biến custom header thành dữ liệu đã được xác thực; phải validate schema và nguồn tin cậy.

**“contentType=application/json chứng minh body JSON hợp lệ.”** Converter vẫn có thể lỗi parse; nội dung và schema phải kiểm tra độc lập.

**“JSON type header __TypeId__ an toàn khi trust-all packages.”** Type metadata không tin cậy có rủi ro deserialization và ràng buộc vào Java classes; giới hạn target types.

**“Có thể truyền cả Java Throwable/MessageChannel trong AMQP headers.”** Header values phải tuân thủ kiểu AMQP field table và security policy; object nội bộ không phù hợp.

**“Cứ copy toàn bộ HTTP headers sang RabbitMQ là giữ nguyên context.”** Có thể lộ Authorization/Cookie, tạo header quá lớn hoặc cho phép giả mạo tenant/routing.

**“traceparent là bằng chứng caller được quyền.”** Trace context phục vụ observability, không phải authentication/authorization.

**“Nếu header mất thì tăng prefetch.”** Prefetch chỉ điều chỉnh cửa sổ unacked của consumer, không sửa mapper/converter.

**“Header schemaVersion và payload schemaVersion mâu thuẫn thì chọn đại một bên.”** Phải định nghĩa nguồn sự thật hoặc reject/cách ly conflict.

**“Dùng JSON converter là header mapper tự đúng.”** Serializer body và mapper metadata có trách nhiệm khác nhau.

**“Một test RabbitTemplate direct chứng minh Spring Integration outbound header mapping.”** Test direct MessagePostProcessor không chạy qua mapper của Integration adapter; cần test từng path.

**“RabbitTemplate.receive chỉ xem queue, không lấy message.”** Receive thực sự tiêu thụ; dùng broker/queue test riêng.

**“DeliveryTag và Channel có thể lưu DB để ACK sau restart.”** Delivery tag gắn với channel hiện tại; không sử dụng làm định danh bền vững.

**“redelivered=true chứng minh lần trước xử lý thành công.”** Nó là tín hiệu broker delivery, không phải trạng thái transaction nghiệp vụ.

**“Copy toàn bộ headers khi replay DLQ là an toàn.”** Có thể mang theo metadata cũ, replyTo hết hạn, x-death, deliveryTag hoặc thông tin nhạy cảm.

**“Publisher confirm ACK bảo đảm handler đã commit.”** Publisher confirm thuộc broker–publisher; consumer ACK và business commit là các mốc khác.

**“ErrorChannel log lỗi thì broker chắc chắn NACK.”** Custom error flow có thể hấp thụ exception; phải kiểm tra container/error handler và broker thực tế.

**“Cùng queue, nhiều consumer thì tất cả đều nhận mọi event.”** Consumer cùng queue thường cạnh tranh delivery; broadcast cần nhiều queue/bindings theo nhóm.

**“Header tenantId do producer đặt đủ để cập nhật tenant tương ứng.”** Consumer phải áp dụng authentication/authorization/business policy của hệ thống, không tin trường tùy ý từ ngoài.

## 24. Câu hỏi tự kiểm tra

1. Spring Messaging MessageHeaders khác Spring AMQP MessageProperties ở điểm nào?
2. AMQP **basic property** khác **application header** như thế nào? Hãy lấy ba ví dụ cho mỗi loại.
3. contentType và contentEncoding ảnh hưởng tới body conversion ra sao?
4. Vì sao Spring MessageHeaders.ID không phù hợp làm idempotency key khi retry?
5. eventId, messageId, correlationId, publisher CorrelationData ID và traceId có thể khác nhau ở những khía cạnh nào?
6. Outbound header mapping làm gì? Inbound header mapping làm gì?
7. Default mapper có bảo đảm mọi custom header đều được publish nguyên dạng không? Cần kiểm thử bằng cách nào?
8. AmqpHeaders.RECEIVED_ROUTING_KEY biểu diễn gì? Tại sao nó không phải routing key outbound đương nhiên?
9. receivedExchange và consumerQueue có ý nghĩa ở phía producer hay consumer?
10. DeliveryTag có phạm vi ra sao? Vì sao không ACK trên một AMQP channel khác?
11. Spring Integration replyChannel khác RabbitMQ replyTo như thế nào?
12. Vì sao tùy chỉnh correlationId của AMQP outbound gateway có thể làm request–reply timeout?
13. Khi nào nên dùng JSON envelope chứa eventType/schemaVersion thay vì phụ thuộc hoàn toàn vào application headers?
14. Nếu schemaVersion header là 2 nhưng payload schemaVersion là 1, consumer nên làm gì?
15. Tại sao chỉ đặt header __TypeId__ không đủ để đảm bảo một DTO được deserialize an toàn?
16. Khi nào cần dùng RabbitTemplate MessagePostProcessor thay vì chỉ MessageBuilder.setHeader?
17. Trong Java DSL ví dụ, đâu là MessageChannel nội bộ và đâu là RabbitMQ queue?
18. Nếu OrdersHeadersPublisher tạo eventType nhưng raw AMQP message thiếu eventType, kiểm tra những nơi nào?
19. Nếu raw AMQP message có eventType nhưng handler không thấy, kiểm tra những nơi nào?
20. Lỗi MessageConverter trước khi Spring Integration tạo Message có chắc đi qua service activator không?
21. Vì sao errorChannel có thể làm thay đổi kết quả ACK/NACK?
22. DirectChannel và ExecutorChannel khác nhau thế nào về thời điểm listener callback kết thúc?
23. Nếu consumer bridge AMQP → Kafka, những headers nào nên giữ, những headers nào nên loại bỏ?
24. Vì sao traceparent không được dùng để quyết định role hoặc tenant?
25. Dùng x-death để tính tổng số business attempts có những giới hạn nào?
26. Khi replay từ DLQ, vì sao giữ eventId nhưng không sao chép deliveryTag?
27. MessageId và correlationId nên được đặt vào basic properties hay custom application headers nếu consumer cần các trường chuẩn?
28. Một AMQP inbound adapter nhận text/plain và JSON trên cùng queue cần chiến lược converter/validation nào?
29. Test raw RabbitTemplate message khác contract test của Spring Integration header mapper thế nào?
30. Những tình huống producer mới ↔ consumer cũ cần kiểm thử khi thay đổi header names/type?
31. Vì sao một message có header đúng vẫn có thể không route tới queue nghiệp vụ?
32. Tại sao queue durable, publisher confirms và consumer ACK vẫn không tự bảo đảm exactly-once business processing?
33. Cần làm gì khi một header từ RabbitMQ yêu cầu consumer xử lý tenant không khớp context đã xác thực?
34. Những metric nào giúp phát hiện schemaVersion sai, header thiếu và converter lỗi?
35. Một hệ thống SFTP → Spring Integration → AMQP → Kafka nên chọn thông tin nào làm business contract ổn định xuyên giao thức?

## Tổng kết

**Header mapping với Rabbit message** là bước chuyển đổi metadata giữa **Spring MessageHeaders** và **Spring AMQP MessageProperties**, bao gồm **AMQP basic properties**, **application headers** và những metadata chỉ xuất hiện khi consumer nhận delivery. **Outbound mapping** đưa những header hợp lệ từ Spring Integration ra giao thức AMQP; **inbound mapping** đưa thông tin AMQP cần thiết vào Spring Message để router, transformer và service activator sử dụng. Header mapping **khác** MessageConverter xử lý body và cũng **khác** transformer chuẩn hóa domain.

Một hợp đồng đáng tin cậy cần định nghĩa rõ **eventId, eventType, schemaVersion, contentType, contentEncoding, messageId, correlationId và trace context**. Không nhầm **Spring replyChannel với AMQP replyTo**, **CorrelationData với business correlationId** hoặc **deliveryTag với idempotency key**. Hãy áp dụng whitelist, giới hạn kiểu dữ liệu, validate headers không tin cậy và tuyệt đối không cho custom header tùy ý quyết định quyền truy cập.

Trong **SPRING_INTEGRATION_ADAPTERS**, các ví dụ Java DSL minh họa Spring Message → **AMQP outbound adapter → RabbitTemplate → RabbitMQ → AMQP inbound adapter → DirectChannel**. Cần kiểm tra **raw AMQP body/properties**, **Spring MessageHeaders ở hai đầu**, exception/errorChannel và kết quả ACK/NACK/confirm/return bằng integration tests, không chỉ dựa vào việc MessageChannel.send() trả về. Khi thiết kế thêm retry, DLX/DLQ, gateway hoặc bridge sang Kafka/HTTP/SFTP, giữ **business contract ổn định**, chọn lại headers đúng vai trò và đặt ranh giới lưu bền, idempotency cùng khả năng khôi phục trước khi đưa luồng vào production.
