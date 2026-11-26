# Thiết kế envelope sự kiện và định danh ổn định cho từng thông điệp

Khi tích hợp **RabbitMQ với Spring AMQP**, một message thường đi qua nhiều thành phần: ứng dụng tạo sự kiện, **RabbitTemplate** publish vào exchange, exchange định tuyến qua binding đến queue, rồi một hoặc nhiều **@RabbitListener** xử lý. Trong thực tế, publisher có thể gửi lại sau timeout, broker có thể giao lại message chưa được ACK, hoặc thông điệp lỗi được chuyển sang dead-letter queue. Nếu không có định danh ổn định, consumer khó biết một lần nhận là **sự kiện mới** hay **lần giao lại của sự kiện cũ**.

Giải pháp là thiết kế **event envelope**: một cấu trúc thống nhất bao quanh dữ liệu nghiệp vụ, mang định danh sự kiện, loại sự kiện, phiên bản hợp đồng, nguồn phát sinh, thời điểm và ngữ cảnh truy vết. Bài học thuộc chương **Cấu trúc thông điệp**, tập trung vào việc định danh một **sự kiện logic** nhất quán từ producer đến consumer.

Sau bài này, bạn có thể:

1. Phân biệt **payload nghiệp vụ** và **metadata của envelope**, cùng các thuộc tính AMQP trên đường truyền.
2. Chọn và duy trì **eventId** ổn định qua retry, redelivery, dead-letter và publisher gửi lại.
3. Phân biệt **eventId**, **aggregateId**, **messageId**, **correlationId**, **causationId** và **deliveryTag**.
4. Viết mã Spring AMQP publish/consume envelope JSON qua **RabbitTemplate** và **@RabbitListener**.
5. Áp dụng **idempotency**, transactional outbox, versioning và logging để xử lý bất đồng bộ đáng tin cậy.

## 1. Vấn đề của payload không có envelope

Xét một publisher gửi trực tiếp:

~~~json
{
  "orderId": "O-1001",
  "amount": 259000,
  "currency": "VND"
}
~~~

Payload này cho consumer biết số tiền và mã đơn hàng, nhưng chưa trả lời rõ:

- Đây là **order.created**, **order.paid** hay một loại sự kiện khác?
- Có phải phiên bản cấu trúc dữ liệu mà consumer đang hỗ trợ không?
- Khi consumer nhận payload lần thứ hai, đó là **đơn hàng khác**, một **sự kiện khác của cùng đơn hàng**, hay **cùng sự kiện được gửi/giao lại**?
- Sự kiện phát sinh lúc nào, do ứng dụng nào phát ra?
- Nó thuộc luồng request/transaction hoặc sự kiện nguồn nào để truy vết qua nhiều dịch vụ?

Nếu lấy **orderId** làm định danh message, sẽ có lỗi: cùng một đơn hàng có thể phát sinh nhiều sự kiện hợp lệ như **order.created**, **order.paid**, **order.cancelled**. Tất cả cùng **orderId** nhưng không phải cùng sự kiện.

Nếu sinh **UUID mới mỗi lần RabbitTemplate thử publish lại**, lại có lỗi khác: một sự kiện logic có thể bị consumer tưởng là nhiều sự kiện mới và tạo tác dụng phụ lặp.

**Quy tắc nền tảng:** định danh **sự kiện logic** phải được tạo khi sự kiện hình thành, lưu cùng sự kiện, rồi **giữ nguyên ở mọi lần publish lại và giao lại cùng sự kiện**.

## 2. Một envelope thực tế trông thế nào?

Một mẫu envelope JSON dành cho domain event:

~~~json
{
  "eventId": "e5b8a51a-50fa-4c38-a7d7-67dc9318c7fd",
  "eventType": "order.created",
  "schemaVersion": 1,
  "source": "order-service",
  "aggregateType": "Order",
  "aggregateId": "O-1001",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-26T01:15:42Z",
  "correlationId": "1bd738b6-7693-43f8-9c9a-23b51e5eb030",
  "causationId": null,
  "data": {
    "orderId": "O-1001",
    "totalMinor": 259000,
    "currency": "VND"
  }
}
~~~

Envelope gồm **metadata chung** ở cấp ngoài và **data** chứa dữ liệu riêng của từng loại sự kiện.

| Field | Vai trò | Quy tắc thiết kế |
| --- | --- | --- |
| **eventId** | Định danh **một sự kiện logic** | Bắt buộc, duy nhất trong phạm vi quy ước hệ thống, bất biến qua retry/redelivery |
| **eventType** | Loại sự kiện, ví dụ **order.created** | Dùng tên ổn định, rõ ngữ nghĩa đã xảy ra |
| **schemaVersion** | Phiên bản hợp đồng của envelope/payload theo quy ước | Bắt buộc nếu consumer cần phân biệt các cấu trúc tương thích/không tương thích |
| **source** | Dịch vụ hoặc thành phần tạo sự kiện | Ổn định, hữu ích để truy vết và xác định chủ sở hữu |
| **aggregateType** | Loại thực thể nghiệp vụ liên quan | Tùy bài toán; ví dụ **Order** |
| **aggregateId** | Định danh thực thể nghiệp vụ | Có thể lặp giữa nhiều sự kiện khác nhau của cùng thực thể |
| **aggregateVersion** | Phiên bản trạng thái của aggregate tại thời điểm sự kiện | Tùy chọn; hữu ích cho kiểm soát thứ tự và phát hiện bỏ sót |
| **occurredAt** | Thời điểm sự kiện nghiệp vụ phát sinh | Dùng ISO 8601 với timezone rõ ràng, thường UTC |
| **correlationId** | Gom các message cùng một luồng nghiệp vụ/request | Có thể giữ nguyên trên nhiều sự kiện khác nhau |
| **causationId** | Định danh message/event/command trực tiếp dẫn đến sự kiện này | Tùy chọn; phải có quy ước rõ đang tham chiếu loại ID nào |
| **data** | Payload dữ liệu nghiệp vụ | Cấu trúc gắn với eventType và schemaVersion |

Đây là **hợp đồng minh họa do ứng dụng thiết kế**, không phải cấu trúc bắt buộc của RabbitMQ hoặc Spring AMQP. Có thể chọn chuẩn như **CloudEvents** nếu tổ chức cần trao đổi liên hệ sinh thái, nhưng khi đã chọn hợp đồng nào thì producer và consumer phải thống nhất cấu trúc, ngữ nghĩa và chính sách thay đổi phiên bản.

### Vì sao có cả eventId lẫn aggregateId?

~~~text
Aggregate: Order O-1001
    |
    +-- Event A: order.created   eventId = evt-A
    +-- Event B: order.paid      eventId = evt-B
    +-- Event C: order.shipped   eventId = evt-C

aggregateId = O-1001 cho cả ba
eventId khác nhau vì đây là ba sự kiện logic khác nhau
~~~

**aggregateId** trả lời “sự kiện liên quan đến thực thể nào?”. **eventId** trả lời “đây là sự kiện cụ thể nào?”. Consumer không nên dùng riêng aggregateId để chống xử lý lặp mọi loại sự kiện.

### Vì sao occurredAt không thay thế eventId?

Hai sự kiện có thể phát sinh rất gần nhau hoặc có cùng độ chính xác timestamp. Đồng hồ giữa các node còn có sai số. **occurredAt** phù hợp cho phân tích, audit và độ trễ; nó không phải khóa định danh đáng tin cậy. Nếu cần xác định thứ tự cập nhật trên một aggregate, một **aggregateVersion** tăng đơn điệu do hệ thống nguồn quản lý thường có ý nghĩa nghiệp vụ rõ hơn so với sắp xếp theo thời gian.

## 3. Những loại ID nào dễ bị nhầm?

RabbitMQ dùng **AMQP basic.properties** và các thuộc tính giao nhận. Spring AMQP cũng cung cấp **MessageProperties**. Một số tên nghe giống eventId nhưng có vòng đời khác nhau.

| Tên | Được tạo/quản lý bởi | Phạm vi và mục đích | Có nên dùng làm định danh sự kiện? |
| --- | --- | --- | --- |
| **eventId** trong envelope | Ứng dụng nguồn | Cố định cho một sự kiện logic | **Có** |
| **messageId** trong AMQP properties | Thường do publisher đặt; broker không tự bảo đảm có/duy nhất | Metadata của message vận chuyển | Có thể đặt **bằng eventId** theo quy ước, nhưng không nên xem broker đảm bảo |
| **aggregateId / orderId** | Hệ thống nghiệp vụ | Nhận diện thực thể, lặp qua nhiều sự kiện | **Không** |
| **correlationId** | Điểm bắt đầu một luồng nghiệp vụ hoặc ứng dụng tương tác | Liên kết nhiều request/event/message | **Không** |
| **causationId** | Ứng dụng phát sinh sự kiện mới | Nối quan hệ nguyên nhân trực tiếp | **Không** |
| **deliveryTag** | Broker cấp cho lần delivery trên **channel** | Dùng khi ACK/NACK trên channel tương ứng | **Không**; có thể thay đổi khi giao lại |
| **redelivered** | Broker đánh dấu ở lần giao | Gợi ý message có thể đã được giao trước đó | **Không**; không phải bộ đếm hay idempotency key |
| **traceId / traceparent** | Hệ thống distributed tracing | Liên hệ các span/service trong một trace | **Không**; không thay thế eventId |

**Ví dụ:** hai lần delivery của cùng một message có thể có **deliveryTag khác nhau**; cả hai phải mang **cùng eventId**. Khi ứng dụng tạo hai event khác nhau từ một request, hai event có **eventId khác nhau** nhưng có thể dùng **cùng correlationId**.

## 4. Vòng đời của một eventId ổn định

Một eventId nên được tạo **một lần tại thời điểm ứng dụng xác định một sự kiện nghiệp vụ đã xảy ra**. ID có thể dùng **UUIDv4** hoặc UUIDv7 (nếu nền tảng hỗ trợ và có quy ước thống nhất), hoặc một loại định danh phân tán khác có nguy cơ trùng rất thấp. Không cần gắn cơ chế sinh ID vào RabbitMQ.

~~~mermaid
flowchart TD
    A["Nghiệp vụ tạo sự kiện"] --> B["Tạo eventId một lần<br/>đóng gói envelope"]
    B --> C[("Lưu event / outbox<br/>eventId bất biến")]
    C --> D["Publisher gửi qua RabbitTemplate"]
    D --> E{"Broker confirm / route"}
    E -->|"Thành công"| Q[("Queue")]
    E -->|"Timeout hoặc trạng thái không rõ"| R["Retry publish<br/>tái dùng envelope cũ"]
    R --> D
    Q --> L["@RabbitListener"]
    L -->|"Lỗi trước ACK"| RD["Redelivery hoặc dead-letter"]
    RD --> L
    L --> I["Kiểm tra idempotency<br/>theo eventId"]
~~~

Các nguyên tắc:

1. **Sự kiện mới thực sự** → tạo eventId mới, kể cả khi cùng aggregateId.
2. **Publish lại cùng sự kiện** do timeout, confirm không rõ hoặc dispatcher retry → **giữ eventId cũ**.
3. **Redelivery** do consumer chưa ACK → **giữ eventId trong body**, vì nghiệp vụ vẫn là cùng sự kiện.
4. **Đưa message vào DLQ, sửa lỗi rồi replay cùng sự kiện** → nên giữ eventId gốc để consumer phát hiện xử lý lặp; ghi thêm metadata riêng cho lần replay nếu cần.
5. **Tái xây dựng sự kiện khác mang ý nghĩa nghiệp vụ mới** → tạo eventId mới, đồng thời lưu mối quan hệ với sự kiện trước khi thích hợp.

**Đừng sinh UUID trong chính phương thức retry của publisher** nếu hàm đó được gọi lại cho cùng sự kiện. Hãy để publisher nhận **envelope đã có eventId** hoặc đọc envelope nguyên vẹn từ outbox.

### Retry không phải lúc nào cũng do consumer

- **Publisher retry:** publisher không chắc broker đã nhận thông điệp và gửi lại; có thể xuất hiện hai message giống nhau trong queue.
- **Consumer redelivery:** consumer xử lý nhưng mất connection trước ACK; message cũ có thể được giao lại.
- **Application retry:** listener retry lại logic xử lý hoặc đưa vào retry queue; vẫn là cùng sự kiện logic.
- **Business retry:** người dùng thực sự thực hiện một hành động nghiệp vụ mới. Có thể tạo một sự kiện mới, dù thông tin như orderId vẫn giống nhau.

Phân biệt các loại retry này giúp chọn đúng **eventId** và **idempotency key**.

## 5. Event envelope và AMQP message properties

Một message gửi bằng Spring AMQP gồm **body** (bytes) và **MessageProperties**. Có thể đưa envelope JSON vào body và sao chép một số metadata trọng yếu vào AMQP properties để router, công cụ quản trị và consumer dễ tra cứu.

~~~text
AMQP message
├── properties
│   ├── contentType: application/json
│   ├── contentEncoding: UTF-8
│   ├── messageId: e5b8a51a-...
│   ├── type: order.created
│   ├── correlationId: 1bd738b6-...
│   ├── deliveryMode: persistent
│   └── headers: {schema_version: 1}
└── body (JSON bytes)
    ├── eventId: e5b8a51a-...
    ├── eventType: order.created
    ├── schemaVersion: 1
    ├── aggregateId: O-1001
    └── data: {...}
~~~

| AMQP property | Gợi ý sử dụng | Lưu ý |
| --- | --- | --- |
| **contentType** | **application/json** | Cho biết định dạng body; không bảo đảm body hợp lệ |
| **contentEncoding** | **UTF-8** | Hữu ích khi encode/decode bytes |
| **messageId** | Đặt bằng **eventId** nếu mọi publisher tuân theo quy ước | Là trường tùy chọn; broker không sinh UUID và không tự chống trùng |
| **type** | Đặt bằng **eventType** | Có thể hỗ trợ dispatch/quan sát |
| **correlationId** | Sao chép correlationId của envelope | Phục vụ tương quan, không phải khóa chống lặp |
| **headers** | **schema_version**, trace context hoặc metadata kỹ thuật | Tránh đưa bí mật hoặc dữ liệu cá nhân nhạy cảm |
| **deliveryMode** | **PERSISTENT** với queue durable khi cần lưu bền | Không thay thế publisher confirm hoặc thiết kế queue HA |
| **timestamp** | Có thể đặt thời gian publish | Không nhất thiết trùng **occurredAt** nghiệp vụ |
| **replyTo** | Phù hợp request/reply | Không cần cho domain event chỉ phát một chiều |

Trong hợp đồng ví dụ, **body eventId là danh tính chuẩn**. Việc đặt AMQP **messageId=eventId** là quy ước của ứng dụng để thống nhất quan sát. Consumer có thể kiểm tra hai giá trị có khớp không; khi không khớp, xử lý theo chính sách dữ liệu lỗi thay vì tùy tiện chọn một giá trị.

Routing key như **order.created** thường phù hợp với eventType, nhưng **routing key là quy tắc định tuyến**, không phải định danh của từng event. Một sự kiện publish đến fanout hoặc topic exchange có thể xuất hiện trong nhiều queue với **cùng eventId**.

## 6. Thực hành Spring AMQP: định nghĩa và publish envelope JSON

Ví dụ dưới đây dùng **Java 17, Spring Boot 3.x, Spring AMQP và Jackson**. Với các dòng Spring Boot/Spring AMQP khác, kiểm tra dependency và cách auto-configure Jackson tương ứng. Ta chủ động serialize JSON bytes nên **không phụ thuộc** việc thay đổi tên class JSON MessageConverter giữa các phiên bản Spring AMQP.

Các dependency tham khảo khi sử dụng Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-amqp")
    implementation("org.springframework.boot:spring-boot-starter-json")
}
~~~

Nếu dùng phần idempotency với PostgreSQL ở sau bài, cần bổ sung **spring-boot-starter-jdbc** và driver database tương ứng.

Kết nối broker cục bộ qua **application.yml** (đổi thông tin cho môi trường đang dùng):

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: app
    password: local_dev_password
    virtual-host: /
~~~

Thông tin đăng nhập chỉ mang tính minh họa môi trường thực hành. Ở hệ thống triển khai, quản lý mật khẩu bằng biến môi trường hoặc secret manager.

### 6.1. Định nghĩa envelope bằng Java record

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;

public record EventEnvelope(
        String eventId,
        String eventType,
        int schemaVersion,
        String source,
        String aggregateType,
        String aggregateId,
        Long aggregateVersion,
        Instant occurredAt,
        String correlationId,
        String causationId,
        JsonNode data
) {}
~~~

Sử dụng **JsonNode** cho **data** giúp ví dụ có thể mô tả nhiều eventType. Ở hệ thống thực, consumer thường cần DTO cụ thể và validation tương ứng với từng loại sự kiện/phiên bản.

Một factory tạo sự kiện khi đơn hàng phát sinh:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Component;

@Component
public class OrderEventFactory {
    private final ObjectMapper mapper;
    private final Clock clock = Clock.systemUTC();

    public OrderEventFactory(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public EventEnvelope orderCreated(
            String orderId,
            long totalMinor,
            String currency,
            long aggregateVersion,
            String correlationId,
            String causationId) {

        ObjectNode data = mapper.createObjectNode();
        data.put("orderId", orderId);
        data.put("totalMinor", totalMinor);
        data.put("currency", currency);

        return new EventEnvelope(
                UUID.randomUUID().toString(),  // Tạo đúng một lần
                "order.created",
                1,
                "order-service",
                "Order",
                orderId,
                aggregateVersion,
                Instant.now(clock),
                correlationId,
                causationId,
                data
        );
    }
}
~~~

**Chỉ gọi orderCreated khi cần tạo sự kiện logic mới.** Sau khi có đối tượng EventEnvelope, lưu nó (thường vào outbox) và truyền lại **chính đối tượng hoặc JSON đã lưu** khi publish retry. Đừng gọi lại factory mỗi lần publish timeout.

### 6.2. Khai báo exchange, queue và binding

Ví dụ một direct exchange định tuyến event **order.created** tới queue Billing:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class EventTopology {
    public static final String EXCHANGE = "demo.orders.events";
    public static final String QUEUE = "demo.billing.order-created";
    public static final String ROUTING_KEY = "order.created";

    @Bean
    DirectExchange eventsExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue billingQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding billingBinding(Queue billingQueue,
                           DirectExchange eventsExchange) {
        return BindingBuilder.bind(billingQueue)
                .to(eventsExchange)
                .with(ROUTING_KEY);
    }
}
~~~

Trong môi trường có **RabbitAdmin** hoạt động, những bean trên có thể được auto-declare khi connection mở. Việc publish message không tự bảo đảm exchange/binding đã tồn tại; cần xử lý topology và quyền RabbitMQ phù hợp.

### 6.3. RabbitTemplate gửi body và message properties đồng nhất

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.Date;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class EnvelopePublisher {
    private final RabbitTemplate rabbitTemplate;
    private final ObjectMapper mapper;

    public EnvelopePublisher(
            RabbitTemplate rabbitTemplate,
            ObjectMapper mapper) {
        this.rabbitTemplate = rabbitTemplate;
        this.mapper = mapper;
    }

    public void publish(EventEnvelope event) throws JsonProcessingException {
        MessageProperties properties = new MessageProperties();
        properties.setMessageId(event.eventId());
        properties.setType(event.eventType());
        properties.setContentType(MessageProperties.CONTENT_TYPE_JSON);
        properties.setContentEncoding(StandardCharsets.UTF_8.name());
        properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        properties.setTimestamp(Date.from(event.occurredAt()));
        properties.setHeader("schema_version", event.schemaVersion());
        if (event.correlationId() != null) {
            properties.setCorrelationId(event.correlationId());
        }

        byte[] jsonBody = mapper.writeValueAsBytes(event);
        Message message = new Message(jsonBody, properties);

        rabbitTemplate.send(
                EventTopology.EXCHANGE,
                EventTopology.ROUTING_KEY,
                message
        );
    }
}
~~~

Điểm quan trọng:

- **eventId** được nhận từ envelope, **không sinh mới trong publish(...)**.
- **messageId** của AMQP được đặt bằng eventId theo hợp đồng của ứng dụng.
- **contentType=application/json** thể hiện dữ liệu body là JSON.
- **occurredAt** vẫn nằm trong body; AMQP timestamp chỉ là metadata bổ sung.
- **deliveryMode=PERSISTENT** phù hợp với yêu cầu bền dữ liệu khi queue durable, nhưng chưa bảo đảm end-to-end delivery.
- Một message có thể được exchange định tuyến tới nhiều queue; các consumer vẫn thấy cùng **eventId**.

Ở ví dụ này, publisher đã có **EventEnvelope** do nghiệp vụ hoặc outbox cấp. Nếu call publish thất bại và cần retry, gọi lại **publish(event)** với cùng event, tránh **orderEventFactory.orderCreated(...)** lần thứ hai.

## 7. Consumer kiểm tra envelope và chống xử lý lặp

Một listener nên kiểm tra cả **tính hợp lệ của hợp đồng** và **trạng thái đã xử lý của eventId**.

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class BillingOrderCreatedListener {
    private final ObjectMapper mapper;
    private final BillingProjectionService projectionService;

    public BillingOrderCreatedListener(
            ObjectMapper mapper,
            BillingProjectionService projectionService) {
        this.mapper = mapper;
        this.projectionService = projectionService;
    }

    @RabbitListener(queues = EventTopology.QUEUE)
    public void onMessage(Message message) throws IOException {
        EventEnvelope event =
                mapper.readValue(message.getBody(), EventEnvelope.class);

        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }
        if (!"order.created".equals(event.eventType())
                || event.schemaVersion() != 1) {
            throw new IllegalArgumentException("Unsupported event contract");
        }
        if (event.data() == null
                || !event.data().hasNonNull("orderId")
                || !event.data().hasNonNull("totalMinor")
                || !event.data().hasNonNull("currency")) {
            throw new IllegalArgumentException("Invalid event data");
        }

        String amqpMessageId = message.getMessageProperties().getMessageId();
        if (amqpMessageId != null
                && !amqpMessageId.equals(event.eventId())) {
            throw new IllegalArgumentException("Conflicting message IDs");
        }

        projectionService.applyOnce(event);
    }
}
~~~

Trong Spring AMQP, listener container với chế độ acknowledge **AUTO** thường chỉ ACK sau khi phương thức listener trả về thành công. Nếu **applyOnce(...)** có transaction database và được gọi qua bean Spring khác, transaction của service cần **commit trước khi listener trả về**. Nếu nó ném ngoại lệ, việc requeue, retry hay dead-letter phụ thuộc cấu hình; không nên giả định dữ liệu lỗi sẽ tự động vào DLQ.

**Cảnh báo về poison message:** JSON không parse được hoặc thiếu eventId sẽ tiếp tục thất bại nếu bị requeue vô hạn. Cần phân loại lỗi không thể sửa bằng retry, cấu hình retry có giới hạn và dead-letter queue. Tuyệt đối không tự sinh eventId mới ở consumer để “chữa” message thiếu định danh, vì như vậy sẽ làm hỏng khả năng chống trùng.

### 7.1. Chống trùng bằng khóa duy nhất trong database

Consumer có thể gặp tình huống: ghi dữ liệu thành công, connection RabbitMQ bị mất trước khi ACK, rồi broker giao lại cùng event. Dùng một bảng lưu các event đã xử lý theo **tên consumer + eventId**.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_event (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE billing_order_projection (
    order_id TEXT PRIMARY KEY,
    total_minor BIGINT NOT NULL,
    currency VARCHAR(3) NOT NULL
);
~~~

Ví dụ một service nhận event và cập nhật projection **trong cùng transaction database**:

~~~java
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BillingProjectionService {
    private final JdbcTemplate jdbc;

    public BillingProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyOnce(EventEnvelope event) {
        int inserted = jdbc.update(
                """
                INSERT INTO processed_event (consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT DO NOTHING
                """,
                "billing",
                UUID.fromString(event.eventId())
        );

        if (inserted == 0) {
            return; // Đã xử lý cùng eventId cho consumer billing
        }

        String orderId = event.data().get("orderId").asText();
        long totalMinor = event.data().get("totalMinor").asLong();
        String currency = event.data().get("currency").asText();

        jdbc.update(
                """
                INSERT INTO billing_order_projection
                    (order_id, total_minor, currency)
                VALUES (?, ?, ?)
                ON CONFLICT (order_id)
                DO UPDATE SET
                    total_minor = EXCLUDED.total_minor,
                    currency = EXCLUDED.currency
                """,
                orderId, totalMinor, currency
        );
    }
}
~~~

**Ý nghĩa transaction:** nếu cập nhật projection lỗi, dòng **processed_event** cũng rollback. Nếu commit thành công nhưng ACK mất, lần giao lại sẽ thấy khóa **(billing, eventId)** đã tồn tại, bỏ qua side effect và trả về bình thường để container có thể ACK.

Ví dụ dùng cú pháp **ON CONFLICT** của PostgreSQL; các database khác cần câu SQL tương đương. Trong hệ thống thật cần thêm validation chuẩn dữ liệu (kiểu số, tiền tệ, eventId là UUID hợp lệ), index và xử lý các eventType khác theo hợp đồng.

### 7.2. Vì sao khóa gồm consumer_name và eventId?

Một event **order.created** có thể đi đến cả **Billing** và **Analytics** qua hai queue. Mỗi nhóm phải tự xử lý một lần. Nếu dùng duy nhất eventId trong một bảng chống trùng dùng chung, Billing xử lý trước có thể khiến Analytics bị hiểu nhầm là trùng.

~~~text
eventId = evt-001
  |
  +-- billing.queue   -> processed_event("billing", evt-001)
  +-- analytics.queue -> processed_event("analytics", evt-001)
~~~

Mỗi consumer nghiệp vụ xác định phạm vi idempotency của mình. Một event có thể hợp lệ với nhiều consumer, trong khi **mỗi consumer xử lý một event không quá một lần ở tầng side effect được bảo vệ**.

Nếu side effect đi ra **API bên ngoài** (ví dụ hệ thống thanh toán không cùng database), transaction ở bảng processed_event **không thể tự bao trùm** HTTP call. Khi đó hãy dùng idempotency key do API ngoài hỗ trợ, outbox cho yêu cầu đi tiếp, hoặc cơ chế đối soát.

## 8. Publisher retry và transactional outbox

Không thể coi câu lệnh **RabbitTemplate.send(...) trả về** là chứng cứ chắc chắn event đã tới mọi queue và được xử lý. Có những trường hợp publisher không nhận được kết quả rõ ràng (mất kết nối, timeout, crash) dù broker thực tế đã nhận message.

**Transactional outbox** giúp producer giữ cùng eventId trong suốt các lần publish lại:

~~~mermaid
flowchart TD
    U["Request tạo đơn hàng"] --> TX["DB transaction"]
    TX --> O[("orders: O-1001")]
    TX --> OB[("outbox: eventId=evt-001<br/>event_json bất biến")]
    OB --> D["Outbox dispatcher"]
    D --> RT["RabbitTemplate publish<br/>messageId=evt-001"]
    RT --> R[("RabbitMQ")]
    R -.->|"Confirm hoặc timeout"| D
    D --> S["Đánh dấu SENT khi có bằng chứng phù hợp"]
~~~

Các bước:

1. Trong **cùng database transaction**, ghi thay đổi trạng thái nghiệp vụ và thêm **một bản ghi outbox** với eventId, eventType và envelope JSON.
2. Sau commit, dispatcher đọc bản ghi outbox chưa hoàn tất và publish qua RabbitTemplate.
3. Khi có publisher confirm/return và kết quả phù hợp, cập nhật trạng thái outbox theo chính sách.
4. Nếu dispatcher crash sau khi RabbitMQ nhận message nhưng trước khi đánh dấu hoàn tất, dispatcher có thể publish lại **chính JSON đó với eventId cũ**.
5. Consumer xử lý trùng dựa trên khóa idempotency.

Phác thảo:

~~~text
BEGIN DATABASE TRANSACTION
  INSERT/UPDATE orders ...
  INSERT INTO outbox(event_id, event_type, event_json, status)
       VALUES (eventIdDaTao, 'order.created', jsonDaLuu, 'PENDING')
COMMIT

dispatcher:
  read outbox PENDING
  publish event_json with messageId = event_id
  verify confirm/return according to delivery policy
  mark SENT (or retry later with same event_id and event_json)
~~~

Outbox giải quyết khoảng trống giữa commit DB và việc **có thể gửi lại**. Nó không tự tạo *exactly-once delivery*: publisher gửi trùng vẫn có thể xảy ra. Phương án kết hợp điển hình là **outbox ở producer + idempotent consumer**.

**Phân biệt hai lớp chống trùng:** khóa duy nhất của **business transition** ở producer giúp tránh tạo hai eventId cho cùng một hành động bị request retry; còn **eventId** của envelope giúp consumer nhận ra cùng một event được gửi/giao lại. Nếu producer tạo hai event khác nhau cho cùng nghiệp vụ sai, dedupe theo eventId ở consumer không phát hiện chúng là cùng hành động.

## 9. Thiết kế correlationId và causationId để truy vết

Giả sử một request tạo đơn hàng dẫn đến những sự kiện tiếp theo:

~~~mermaid
flowchart LR
    REQ["HTTP request<br/>correlationId=C-17"] --> A["order.created<br/>eventId=E-1"]
    A --> B["payment.requested<br/>eventId=E-2<br/>causationId=E-1"]
    B --> C["payment.completed<br/>eventId=E-3<br/>causationId=E-2"]
~~~

Trong ví dụ:

- **eventId** thay đổi ở E-1, E-2, E-3 vì đây là ba sự kiện khác nhau.
- **correlationId=C-17** được truyền xuyên suốt để gom chúng vào một quy trình nghiệp vụ.
- **causationId** của E-2 tham chiếu E-1, của E-3 tham chiếu E-2 để tái dựng quan hệ nhân quả gần nhất.

Nếu nguồn phát sinh là command không có eventId, cần định nghĩa nhất quán causationId tham chiếu **commandId**; đừng trộn các định dạng ID thiếu quy ước trong cùng hệ thống.

**Tracing khác correlation nghiệp vụ:** W3C **traceparent** và span context hỗ trợ quan sát các thao tác phân tán. Tracing system có thể tạo trace/span mới hoặc nối liên kết tùy async boundary và sampling. Truy vết kỹ thuật không thay thế **eventId** đã lưu bền. Khi dùng Micrometer Observation/Tracing của Spring, ưu tiên cơ chế propagation tương thích thay vì tự tạo ngẫu nhiên một trace ID mỗi lần retry.

## 10. Versioning: sự kiện tồn tại lâu hơn code

Message có thể nằm trong queue, DLQ hoặc outbox rất lâu trước khi consumer xử lý. Khi producer thay đổi dữ liệu, cần có quy ước version rõ ràng.

Ví dụ **order.created** phiên bản 1:

~~~json
{
  "eventType": "order.created",
  "schemaVersion": 1,
  "data": {
    "orderId": "O-1001",
    "totalMinor": 259000,
    "currency": "VND"
  }
}
~~~

Phiên bản 2 thêm thông tin tùy chọn:

~~~json
{
  "eventType": "order.created",
  "schemaVersion": 2,
  "data": {
    "orderId": "O-1001",
    "totalMinor": 259000,
    "currency": "VND",
    "promotionCode": "WELCOME"
  }
}
~~~

Thêm field tùy chọn có thể giữ tương thích với một số consumer, nhưng không nên tự cho rằng mọi consumer sẽ bỏ qua field lạ. Breaking change như đổi nghĩa **totalMinor**, đổi kiểu dữ liệu hoặc xóa field bắt buộc cần chiến lược nâng cấp rõ ràng.

| Tình huống | Cách xử lý nên cân nhắc |
| --- | --- |
| Thêm field tùy chọn | Kiểm tra consumer có cho phép field mới không; đặt default hợp lý |
| Thay đổi ý nghĩa/đơn vị giá trị | Tạo version mới hoặc eventType mới tùy hợp đồng |
| Consumer nhận schemaVersion chưa hỗ trợ | Phân loại lỗi, đưa vào DLQ/parking queue thay vì retry vô hạn |
| Replay sự kiện cũ | Consumer cần hiểu phiên bản đã phát hành hoặc có bộ chuyển đổi |
| Tăng aggregateVersion | Dựa trên phiên bản do nguồn quản lý, không dựa đơn thuần vào timestamp |

**Một eventId đã phát hành không đổi chỉ vì code serializer đổi phiên bản.** Nếu bạn chỉ truyền lại cùng sự kiện từ outbox, hãy ưu tiên giữ **body đã lưu**. Nếu thật sự tạo sự kiện mới để biểu diễn một nghiệp vụ khác, khi đó mới cấp eventId mới.

## 11. Sự kiện đi qua retry và dead-letter

Với consumer lỗi, thông điệp có thể được requeue, gửi sang retry queue rồi đưa về queue gốc hoặc dead-letter đến DLQ. Quy tắc định danh cần nhất quán:

| Bước | eventId trong envelope | Lưu ý |
| --- | --- | --- |
| Publish lần đầu | **E-1** | Được tạo tại nguồn |
| Publisher gửi lại do confirm không chắc chắn | **E-1** | Không gọi factory để tạo UUID mới |
| Consumer nhận lại sau mất ACK | **E-1** | deliveryTag có thể khác; redelivered là metadata giao nhận |
| Retry qua queue riêng | **E-1** | Nếu application republish, giữ nguyên body identity |
| DLQ nhận thông điệp lỗi | **E-1** | Metadata dead-letter như x-death phục vụ chẩn đoán, không thay eventId |
| Replay cùng sự kiện từ DLQ | **E-1** | Có thể thêm replayAttempt/replayedAt ở metadata, không giả dạng sự kiện mới |
| Một nghiệp vụ mới liên quan | **E-2** | eventId mới, có thể giữ correlationId và ghi causationId |

Với RabbitMQ, header **x-death** có thể cung cấp thông tin lý do và lịch sử dead-letter theo cơ chế broker. Nó **không** phải idempotency key; cấu trúc có thể thay đổi theo các lần dead-letter. Nếu một công cụ replay tự sửa messageId, **eventId trong body** giúp bảo toàn danh tính sự kiện với điều kiện công cụ tôn trọng hợp đồng.

**Tình huống cần tránh:** consumer cứ requeue cùng một message lỗi vĩnh viễn. Dù có eventId ổn định, hệ thống vẫn cần retry có giới hạn, backoff và DLQ để tránh nghẽn queue. Khi message được sửa nội dung để phục hồi dữ liệu bị lỗi, nên ghi lại quá trình xử lý và chính sách xác định đó có còn là cùng event logic hay không.

## 12. Thứ tự, tính duy nhất và mức bảo đảm thực tế

**UUID ngẫu nhiên không mô tả thứ tự nghiệp vụ.** Nếu sự kiện cần được áp dụng theo chuỗi thay đổi của một aggregate, dùng **aggregateVersion** do hệ thống nguồn quản lý hoặc số thứ tự nghiệp vụ tương đương. Hai event có thể có timestamp gần giống, một publisher bị chậm, hoặc nhiều producer gửi song song.

Một consumer xử lý các phiên bản **Order O-1001** nên cân nhắc:

- **Version bằng bản đã áp dụng:** có thể là duplicate hoặc không cần cập nhật lại; vẫn đối chiếu eventId.
- **Version kế tiếp:** có thể áp dụng nếu các điều kiện khác hợp lệ.
- **Version nhảy cóc:** có thể đã thiếu một sự kiện, cần xử lý thiếu dữ liệu hoặc chờ/replay.
- **Version cũ:** không nên ghi đè trạng thái mới nếu projection yêu cầu thứ tự.

Tùy nghiệp vụ, có thể dùng queue partition theo aggregateId và cấu hình Single Active Consumer để giảm cạnh tranh. Nhưng ngay cả SAC cũng không tự bảo đảm exactly-once hoặc thứ tự hoàn tất sau mọi lỗi và retry.

### Bảng phân biệt các mức bảo đảm

| Mục tiêu | Công cụ liên quan | Điều vẫn phải lưu ý |
| --- | --- | --- |
| Message được publish đến broker | **Publisher confirms** | Confirm không chứng minh consumer xử lý xong |
| Message được route đến queue | **Exchange/binding + publisher returns/mandatory** | Return chỉ phản ánh không route được trong các trường hợp áp dụng |
| Message tồn tại khi broker restart | **Durable queue + persistent message + loại queue thích hợp** | Cần thiết kế HA và confirm phù hợp |
| Consumer xử lý một lần dù redelivery | **eventId + dedupe atomically với side effect** | Side effect ngoài DB cần idempotency riêng |
| Chuỗi event đúng thứ tự nghiệp vụ | **aggregateVersion + routing/consumer policy** | Không dựa vào timestamp hay UUID để đoán thứ tự |
| Có thể replay sau khi lỗi | **Outbox, DLQ, lưu envelope bền vững** | Phải bảo toàn eventId và hợp đồng version |

## 13. Quan sát và bảo vệ thông tin trong envelope

Khi log publish và consume, nên có:

~~~text
eventId=e5b8a51a-... eventType=order.created schemaVersion=1
aggregateId=O-1001 correlationId=1bd738b6-...
queue=demo.billing.order-created attempt=2 outcome=duplicate_skipped
~~~

Tại publisher, ghi eventId, eventType, đích exchange/routing key và trạng thái confirm/return. Tại consumer, ghi eventId, queue, kết quả xử lý/đã bỏ qua vì trùng, nguyên nhân lỗi và thời gian xử lý.

Các nguyên tắc vận hành:

1. **Log có cấu trúc** với eventId và correlationId để nối các bước điều tra.
2. **Không đưa eventId duy nhất của từng message làm metric label** cho Prometheus/Micrometer: cardinality có thể tăng không giới hạn. Dùng eventType, queue, outcome và service làm nhãn có kiểm soát.
3. **Không đưa mật khẩu, token, dữ liệu thẻ hoặc thông tin nhạy cảm** vào metadata để tiện debug; áp dụng nguyên tắc tối thiểu dữ liệu.
4. **Đặt giới hạn kích thước message** và kiểm soát payload; payload lớn gây tốn bộ nhớ và ảnh hưởng throughput broker.
5. **Kiểm tra eventId trước khi xử lý nghiệp vụ**; không tự chữa dữ liệu lỗi bằng cách cấp ID mới tại consumer.
6. **Quan sát Ready/Unacked, DLQ, retry count, confirm/return**, và đối chiếu log với eventId thực tế.

### Quy trình thử nghiệm thực tế

Trong các bước sau, **E-1** và **E-2** chỉ là ký hiệu ngắn cho **hai UUID hợp lệ khác nhau**. Khi chạy mã PostgreSQL bên trên, cần truyền eventId ở định dạng UUID.

1. Tạo một envelope **order.created** với eventId **E-1** và publish tới queue Billing. Xác nhận listener xử lý một lần.
2. Publish **lại đúng envelope E-1**; bảng processed_event đã có khóa nên không tạo side effect lần hai.
3. Tạo sự kiện khác **order.paid** cho cùng orderId, cấp eventId **E-2**; consumer phù hợp được phép xử lý đó là sự kiện mới.
4. Cho listener ném lỗi trước ACK và kiểm tra cơ chế redelivery. Khi xử lý lại, eventId vẫn là **E-1**.
5. Kiểm tra messageId property trùng eventId trong body, schemaVersion được consumer hỗ trợ, và các log có correlationId.
6. Thử một message thiếu eventId hoặc version không hỗ trợ; xác minh chính sách lỗi đưa đến DLQ/parking queue và **không** retry vô hạn.
7. Nếu dùng outbox, mô phỏng dispatcher publish thành công nhưng chưa kịp đánh dấu SENT; lần gửi sau phải **giữ nguyên eventId và event_json**.

## 14. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng **orderId** thay eventId | Các sự kiện khác nhau của một đơn hàng bị hiểu là trùng | Dùng eventId riêng cho từng sự kiện |
| Sinh UUID mới trong mỗi lần publish retry | Một sự kiện bị xem thành nhiều sự kiện mới | Tạo ID trước, lưu envelope và tái sử dụng |
| Dựa vào **deliveryTag** để dedupe | Tag chỉ có ý nghĩa trong channel/delivery | Dùng eventId trong body hoặc hợp đồng tương đương |
| Giả định RabbitMQ tự sinh **messageId** | Có messageId rỗng hoặc trùng mà code không kiểm soát | Publisher chủ động đặt theo quy ước |
| Dùng **correlationId** làm khóa chống trùng | Một workflow có nhiều sự kiện bị bỏ qua sai | Correlation để truy vết, eventId để dedupe |
| Ghi processed_event **ngoài transaction** cập nhật dữ liệu | Có thể đánh dấu đã xử lý dù side effect rollback | Lưu dedupe và side effect cùng transaction khi cùng DB |
| Chỉ chống trùng ở một consumer dùng chung global key | Các chức năng độc lập có thể chặn lẫn nhau | Dùng **consumer_name + eventId** |
| Cho message sai schema retry mãi | Poison message chiếm queue | Validation, retry giới hạn và DLQ |
| Đổi schema nhưng không version | Consumer cũ đọc sai hợp đồng | Quản lý version và tương thích |
| Log toàn bộ payload nhạy cảm | Lộ dữ liệu và log phình to | Log metadata cần thiết, ẩn thông tin nhạy cảm |

## 15. Checklist thiết kế envelope trước khi triển khai

Hãy trả lời rõ những câu hỏi:

- **eventId** được tạo tại đâu, một lần hay nhiều lần, và lưu bền với sự kiện thế nào?
- Khi **publisher retry**, cùng body và eventId có được dùng lại không?
- eventType, schemaVersion, source, occurredAt và data có hợp đồng rõ ràng không?
- Khi cùng một **aggregateId** phát nhiều sự kiện, có tạo eventId khác nhau không?
- Consumer dùng **(consumer_name, eventId)** hoặc phạm vi idempotency tương đương chưa?
- Side effect được bảo vệ trong transaction nào; có gọi API ngoài cần idempotency riêng không?
- Publisher confirm/returns, retry và dead-letter có bảo toàn danh tính logic không?
- Consumer xử lý **schemaVersion lạ** và eventId thiếu như thế nào?
- Có cần **aggregateVersion** để bảo vệ thứ tự nghiệp vụ không?
- Có thể tra eventId/correlationId trong logs, traces và thông tin broker mà không làm tăng cardinality metric quá mức không?

**Nguyên tắc cuối:** một sự kiện nghiệp vụ mới nhận **eventId mới**, còn mọi lần **gửi lại hoặc giao lại cùng sự kiện** phải giữ **eventId ổn định**. Envelope cung cấp hợp đồng dữ liệu có thể version, RabbitTemplate và @RabbitListener vận chuyển và xử lý, còn **transactional outbox + idempotent consumer** giúp hệ thống chịu được retry, timeout, crash và redelivery. Đây là nền tảng để xây dựng luồng bất đồng bộ đáng tin cậy trong **Spring AMQP và RabbitMQ**.

### Tài liệu tham khảo

- [RabbitMQ – Publishers](https://www.rabbitmq.com/docs/publishers)
- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ – Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)
- [Spring AMQP – Sending Messages](https://docs.spring.io/spring-amqp/reference/amqp/sending-messages.html)
- [CloudEvents – Specification](https://cloudevents.io/)
