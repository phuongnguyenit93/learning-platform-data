# Phiên bản schema, trường tùy chọn và thay đổi cấu trúc sự kiện

Trong chương **Chuyển đổi dữ liệu** của **SPRING_AMQP**, producer dùng **RabbitTemplate** để gửi sự kiện qua exchange, queue và binding tới **@RabbitListener**. Những ứng dụng này không nhất thiết được triển khai cùng lúc. Consumer mới có thể phải đọc message do producer cũ gửi và vẫn còn trong queue; producer mới có thể đã hoạt động khi một số consumer chưa được nâng cấp.

Vì vậy, việc đổi cấu trúc JSON, thêm trường hay thay kiểu dữ liệu phải được quản lý như **thay đổi hợp đồng sự kiện (event contract)**. RabbitMQ truyền message và giữ metadata theo giao thức AMQP, nhưng **không tự đổi schema** trong body để phù hợp phiên bản code.

Bài học giúp bạn đánh giá tính tương thích, phân biệt trường bắt buộc/tùy chọn, chọn nơi lưu schema version, xây consumer hỗ trợ đồng thời v1/v2 và lập kế hoạch triển khai không bỏ sót message. Đây cũng là nền tảng để xử lý retry, dead-letter, xác nhận giao nhận, giao dịch và quan sát hệ thống bất đồng bộ đáng tin cậy.

## 1. Vì sao schema evolution là vấn đề của hệ thống message?

Giả sử Order Service phát sự kiện **OrderPlaced**. Billing Service lập hóa đơn, Analytics Service thống kê. Mỗi service có vòng đời phát hành độc lập.

~~~mermaid
flowchart LR
    O["Order Service<br/>Producer v1/v2"] --> X{"orders.events<br/>Topic exchange"}
    X --> BQ[("billing.order-placed.q<br/>Tồn đọng v1 + v2")]
    X --> AQ[("analytics.order-placed.q")]
    BQ --> B["Billing consumer<br/>v1 hoặc v2"]
    AQ --> A["Analytics consumer"]
~~~

Trong giai đoạn phát hành có thể đồng thời tồn tại:

- Producer cũ vẫn publish **v1**.
- Producer mới đã bắt đầu publish **v2**.
- Queue còn message v1 đang chờ xử lý hoặc được trả lại sau retry.
- Consumer cũ không hiểu payload v2.
- Consumer mới phải xử lý được dữ liệu từ nhiều phiên bản.

**Điểm mấu chốt:** Message lưu trong queue là dữ liệu đã phát hành, không biến đổi theo phiên bản ứng dụng. Khi nâng phiên bản consumer, phải kiểm tra cả **schema cũ có thể đang tồn đọng**.

| Thuật ngữ | Ví dụ | Vai trò |
|---|---|---|
| **Event type** | order.placed | Tên một sự thật nghiệp vụ |
| **Schema version** | 1, 2 | Định dạng và ngữ nghĩa của payload |
| **Routing key** | order.placed.v1 | Exchange sử dụng để chọn queue |
| **Service version** | billing 3.8.0 | Phiên bản ứng dụng triển khai |
| **Protocol version** | AMQP 0-9-1 | Giao thức trao đổi message |

Không tăng schema version chỉ vì refactor Java code mà payload và ngữ nghĩa không đổi. Ngược lại, thay đổi phá vỡ hợp đồng có thể cần schema version mới dù chỉ đổi một trường.

## 2. Ví dụ xuyên suốt: OrderPlaced v1 và v2

### 2.1. Sự kiện v1 ban đầu

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-1001",
  "orderId": "ord-5001",
  "totalCents": 125000,
  "shippingAddress": "12 Nguyen Hue, Ho Chi Minh City"
}
~~~

Định nghĩa hợp đồng:

| Trường | Kiểu | Bắt buộc | Quy tắc |
|---|---|---|---|
| **schemaVersion** | integer | Có | Giá trị 1 |
| **eventId** | string | Có | Không rỗng, dùng truy vết/idempotency |
| **orderId** | string | Có | Không rỗng |
| **totalCents** | integer | Có | Số nguyên không âm; đơn vị được quy định |
| **shippingAddress** | string | Có | Địa chỉ dạng text không rỗng |

Ví dụ dùng một đơn vị tiền được quy định trong hợp đồng minh họa. Khi có nhiều loại tiền tệ, hãy bổ sung **currency** và định nghĩa rõ đơn vị nhỏ nhất, tránh tự suy từ tên trường.

### 2.2. Thêm couponCode tùy chọn

Một phiên bản producer mới muốn cung cấp mã khuyến mại:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-1002",
  "orderId": "ord-5002",
  "totalCents": 89000,
  "shippingAddress": "85 Le Loi, Ho Chi Minh City",
  "couponCode": "WELCOME10"
}
~~~

Nếu consumer cũ **bỏ qua trường lạ**, nó vẫn đọc được các trường v1 vốn có. Consumer mới phải xử lý message cũ **không chứa couponCode**.

Với chính sách tương thích phù hợp, thêm một trường tùy chọn có thể không cần tăng schema version. Tuy vậy, nếu consumer cũ dùng JSON parser/validation theo chế độ **cấm trường lạ**, thay đổi này vẫn có thể gây lỗi. Cần kiểm chứng bằng dữ liệu thực tế.

### 2.3. Thay shippingAddress thành object: v2

Sau đó đội giao hàng cần tách đường phố và thành phố:

~~~json
{
  "schemaVersion": 2,
  "eventId": "evt-1003",
  "orderId": "ord-5003",
  "totalCents": 129000,
  "shipping": {
    "line1": "12 Nguyen Hue",
    "city": "Ho Chi Minh City"
  },
  "couponCode": "WELCOME10"
}
~~~

Sự khác biệt:

- V1 có **shippingAddress** kiểu string.
- V2 bỏ trường cũ, thay bằng **shipping** kiểu object chứa **line1** và **city**.
- Consumer chỉ hiểu v1 có thể không đọc được v2, hoặc tệ hơn: thiếu địa chỉ mà không báo lỗi.
- Consumer mới phải hiểu rõ hai cấu trúc và chuyển chúng sang mô hình dữ liệu nội bộ.

**Đây là thay đổi phá vỡ tương thích.** Không thể chỉ khai báo lại queue, đổi tên routing key hoặc nâng phiên bản RabbitMQ rồi kỳ vọng JSON cũ được chuyển thành JSON mới.

## 3. Backward compatibility và forward compatibility

Định nghĩa theo dữ liệu:

- **Backward compatibility:** Consumer **mới** đọc được message **cũ**.
- **Forward compatibility:** Consumer **cũ** đọc được message **mới**.
- **Full compatibility:** Cả hai chiều đều thỏa mãn trong phạm vi hợp đồng.

| Thay đổi | Consumer mới đọc cũ? | Consumer cũ đọc mới? | Điều kiện |
|---|---|---|---|
| Thêm optional field | Thường có | Thường có | Fallback cho field thiếu; bỏ qua unknown field |
| Thêm required field | Có thể lỗi | Tùy parser | Cũ không cung cấp field mà code mới yêu cầu |
| Xóa required field | Có thể có | Thường lỗi | Code cũ vẫn cần field |
| Đổi string thành object | Không tự động | Không tự động | Cần adapter hoặc schema version khác |
| Đổi tên một field | Không tự động | Không tự động | Cần alias/mapping |
| Đổi kiểu số thành chuỗi | Rủi ro | Rủi ro | Có thể bị ép kiểu ngoài ý muốn |
| Thêm enum value | Có thể có | Có thể lỗi | Consumer cũ xử lý unknown enum thế nào |
| Giữ kiểu, đổi ý nghĩa | Rất nguy hiểm | Rất nguy hiểm | Parser có thể thành công nhưng nghiệp vụ sai |

**JSON không tự bảo đảm tính tương thích.** Kết quả phụ thuộc JSON schema, deserializer, rule validation và logic nghiệp vụ của từng consumer.

### 3.1. Vì sao phải kiểm thử cả hai chiều?

Một đội có thể chạy consumer mới trước producer mới để bảo đảm nó đọc được backlog v1. Nhưng nếu producer v2 được kích hoạt trong lúc còn consumer cũ, consumer cũ cũng phải chịu được v2 — hoặc hai phiên bản phải được tách luồng để không đọc nhầm.

~~~mermaid
flowchart TD
    A["Đề xuất thay đổi event"] --> B{"Chỉ thêm optional field?"}
    B -->|"Có"| C["Thử consumer cũ với payload mới<br/>và consumer mới với payload cũ"]
    B -->|"Không, breaking change"| D["Tạo schema v2"]
    D --> E["Nâng consumer hỗ trợ v1 + v2"]
    E --> F["Đổi producer sang v2"]
    F --> G["Theo dõi backlog, lỗi schema, DLQ"]
    G --> H["Chỉ bỏ v1 khi hết dữ liệu cần đọc/replay"]
~~~

## 4. Optional field: missing, null và giá trị rỗng

Một trường có thể xuất hiện theo nhiều trạng thái:

~~~json
{"orderId":"ord-1"}
{"orderId":"ord-1","couponCode":null}
{"orderId":"ord-1","couponCode":""}
{"orderId":"ord-1","couponCode":"WELCOME10"}
~~~

| Trạng thái | Ý nghĩa cần quy định | Ví dụ xử lý |
|---|---|---|
| **Không có key** | Producer chưa cung cấp thuộc tính | Không áp mã khuyến mại |
| **null** | Giá trị chưa biết hoặc cố ý không cung cấp | Coi như không có mã nếu contract cho phép |
| **Chuỗi rỗng** | Key có nhưng thiếu nội dung | Có thể reject vì không hợp lệ |
| **Giá trị hợp lệ** | Có dữ liệu nghiệp vụ | Kiểm tra format và áp dụng |

Đây là **quy ước của event**, không phải quy tắc cố định của JSON. Với một event cập nhật từng phần, **missing** có thể có nghĩa là “không thay đổi”, còn **null** có nghĩa “xóa giá trị”; lúc đó hai trạng thái tuyệt đối không được gộp.

### 4.1. Default value chỉ hợp lý khi đúng nghiệp vụ

Ví dụ:

- **couponCode thiếu** → không có mã khuyến mại, nếu contract định nghĩa như vậy.
- **totalCents thiếu** → không nên tự cho bằng 0 vì có thể tạo hóa đơn sai.
- **currency thiếu** → không được tự suy là USD/VND nếu hệ thống hỗ trợ nhiều tiền tệ.
- **shippingAddress thiếu** → cần validation hoặc chiến lược migration; không âm thầm dùng chuỗi rỗng.

### 4.2. Bẫy khi deserialize vào Java record

~~~java
public record OrderPlacedV1(
        String eventId,
        String orderId,
        long totalCents,
        String shippingAddress,
        String couponCode
) {}
~~~

Với một số cấu hình Jackson, nếu JSON thiếu **totalCents** thì kiểu nguyên thủy **long** có thể nhận giá trị mặc định **0**. Nếu thiếu **couponCode**, trường kiểu String có thể trở thành **null**.

Do đó, nên **validate sự hiện diện và kiểu dữ liệu trước khi chuyển thành DTO**, đặc biệt đối với tiền, ID và những field bắt buộc không có default nghiệp vụ hợp lệ.

## 5. Schema version nên được đặt ở đâu?

| Vị trí | Ví dụ | Ưu điểm | Hạn chế |
|---|---|---|---|
| **Body/envelope** | schemaVersion = 2 | Độc lập RabbitMQ, dễ lưu/replay | Phải parse envelope |
| **AMQP header** | schema-version = 2 | Nhìn trước khi parse payload | Có thể mất khi qua hệ thống không giữ headers |
| **Routing key** | order.placed.v2 | Queue có thể lọc theo version | Mỗi lần nâng version cần xem lại binding |

Ví dụ này chọn **schemaVersion trong body làm nguồn chính**. Header **schema-version** và routing key **order.placed.v1 / order.placed.v2** được dùng để hỗ trợ kiểm tra và chọn queue. Khi có nhiều bản biểu diễn, cần đảm bảo chúng nhất quán.

Một hệ thống khác có thể giữ routing key **order.placed** ổn định và chỉ đặt version trong JSON. Đây cũng là lựa chọn hợp lệ nếu các consumer đều biết cách đọc nhiều schema.

**Event type và schema version thuộc về hợp đồng dữ liệu.** Không tăng chung mọi event theo phiên bản release của ứng dụng nếu chúng không có cùng vòng đời schema.

## 6. Ví dụ Spring Boot + Spring AMQP: consumer đọc v1 và v2

Ví dụ dưới đây nhắm tới **Spring Boot 3.x, Spring AMQP 3.x và Jackson 2**. Với phiên bản dùng Jackson 3, cần chọn API/import phù hợp. Để kiểm soát version độc lập với Java class type header, listener nhận raw **Message** và tự phân tích JSON.

### 6.1. Dependency và kết nối

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
~~~

Cấu hình ví dụ cho RabbitMQ local đã tạo vhost **app_dev** và user có quyền:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    virtual-host: app_dev
    username: learn_amqp
    password: ${RABBITMQ_PASSWORD}
~~~

Cấp giá trị password qua biến môi trường/secret, không commit mật khẩu triển khai thật.

### 6.2. Khai báo exchange, queue, binding và DLQ

Cùng một nhóm Billing cần xử lý cả event v1 và v2, nên tạo **một queue** với **hai binding**.

~~~java
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class SchemaTopology {
    public static final String EVENTS = "orders.events";
    public static final String V1_KEY = "order.placed.v1";
    public static final String V2_KEY = "order.placed.v2";
    public static final String QUEUE = "billing.order-placed.q";
    public static final String DLX = "billing.dlx";
    public static final String DLQ = "billing.order-placed.dlq";
    public static final String DEAD_KEY = "billing.order-placed.failed";

    @Bean
    public Declarables schemaResources() {
        TopicExchange events = new TopicExchange(EVENTS, true, false);
        DirectExchange dlx = new DirectExchange(DLX, true, false);

        Queue work = QueueBuilder.durable(QUEUE)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DEAD_KEY)
                .build();
        Queue failed = QueueBuilder.durable(DLQ).build();

        return new Declarables(
                events,
                dlx,
                work,
                failed,
                BindingBuilder.bind(work).to(events).with(V1_KEY),
                BindingBuilder.bind(work).to(events).with(V2_KEY),
                BindingBuilder.bind(failed).to(dlx).with(DEAD_KEY)
        );
    }
}
~~~

Với cấu hình này, message reject với **requeue=false** có thể được dead-letter sang queue **billing.order-placed.dlq**. Exchange/queue durable không tự bảo đảm tất cả message bền vững; ứng dụng còn cần message persistence, publisher confirm và chiến lược tin cậy phù hợp.

### 6.3. Định nghĩa DTO theo từng schema

Đặt những record package-private dưới đây trong một file **OrderEvents.java** thuộc cùng Java package với producer và consumer của ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonInclude;

@JsonIgnoreProperties(ignoreUnknown = true)
@JsonInclude(JsonInclude.Include.NON_NULL)
record OrderPlacedV1(
        int schemaVersion,
        String eventId,
        String orderId,
        long totalCents,
        String shippingAddress,
        String couponCode
) {}

record ShippingAddress(String line1, String city) {}

@JsonIgnoreProperties(ignoreUnknown = true)
@JsonInclude(JsonInclude.Include.NON_NULL)
record OrderPlacedV2(
        int schemaVersion,
        String eventId,
        String orderId,
        long totalCents,
        ShippingAddress shipping,
        String couponCode
) {}

record NormalizedOrder(
        String eventId,
        String orderId,
        long totalCents,
        String shippingText,
        String couponCode
) {}
~~~

Ý nghĩa:

- **OrderPlacedV1 và OrderPlacedV2** thể hiện hai hợp đồng dữ liệu độc lập.
- **JsonIgnoreProperties(ignoreUnknown=true)** hỗ trợ việc bỏ qua trường JSON mới ngoài các trường biết trước; không thay thế kiểm tra version.
- **JsonInclude(NON_NULL)** giúp producer bỏ key **couponCode** khi null; consumer phải hỗ trợ missing.
- **NormalizedOrder** là mô hình nội bộ để nghiệp vụ Billing không phụ thuộc DTO của từng phiên bản.

### 6.4. Producer gửi hai version bằng RabbitTemplate

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class VersionedOrderPublisher {
    private final RabbitTemplate rabbitTemplate;
    private final ObjectMapper mapper;

    public VersionedOrderPublisher(
            RabbitTemplate rabbitTemplate,
            ObjectMapper mapper
    ) {
        this.rabbitTemplate = rabbitTemplate;
        this.mapper = mapper;
    }

    public void publishV1(OrderPlacedV1 event)
            throws JsonProcessingException {
        if (event.schemaVersion() != 1) {
            throw new IllegalArgumentException("Wrong v1 schemaVersion");
        }
        send(SchemaTopology.V1_KEY, event, event.eventId(), 1);
    }

    public void publishV2(OrderPlacedV2 event)
            throws JsonProcessingException {
        if (event.schemaVersion() != 2) {
            throw new IllegalArgumentException("Wrong v2 schemaVersion");
        }
        send(SchemaTopology.V2_KEY, event, event.eventId(), 2);
    }

    private void send(
            String key,
            Object event,
            String eventId,
            int schemaVersion
    ) throws JsonProcessingException {
        byte[] json = mapper.writeValueAsBytes(event);

        Message message = MessageBuilder.withBody(json)
                .setContentType(MessageProperties.CONTENT_TYPE_JSON)
                .setContentEncoding(StandardCharsets.UTF_8.name())
                .setMessageId(eventId)
                .setHeader("schema-version", schemaVersion)
                .build();

        rabbitTemplate.send(SchemaTopology.EVENTS, key, message);
    }
}
~~~

**RabbitTemplate.send(...)** gửi một Message đã có JSON bytes và AMQP properties. Điều này giúp nhìn rõ **contentType**, **contentEncoding**, **messageId** và schema-version. Nếu dùng **convertAndSend(object)** cùng JSON MessageConverter, vẫn cần bảo đảm converter hai phía thống nhất schema và target type.

**Producer publish thành công không chứng minh consumer đã xử lý.** Khi cần độ tin cậy phải bật publisher confirm/mandatory return và xử lý kết quả; phía consumer ACK riêng sau khi nghiệp vụ hoàn tất.

### 6.5. Consumer: parse, validate và chuẩn hóa

~~~mermaid
flowchart LR
    M["AMQP Message"] --> V{"schemaVersion"}
    V -->|"v1"| D1["Validate v1<br/>shippingAddress"]
    V -->|"v2"| D2["Validate v2<br/>shipping object"]
    V -->|"khác"| ERR["Reject / DLQ"]
    D1 --> N["NormalizedOrder"]
    D2 --> N
    N --> B["Billing service<br/>idempotent"]
~~~

Code listener xử lý raw Message để xác định version trước khi tạo DTO:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class VersionedOrderConsumer {
    private final ObjectMapper mapper;

    public VersionedOrderConsumer(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @RabbitListener(queues = SchemaTopology.QUEUE)
    public void handle(Message message) {
        final NormalizedOrder order;

        try {
            order = decode(message);
        } catch (JsonProcessingException | IllegalArgumentException ex) {
            throw new AmqpRejectAndDontRequeueException(
                    "Invalid or unsupported OrderPlaced schema", ex
            );
        }

        // Thay phần demo này bằng xử lý idempotent theo eventId.
        System.out.println(
                "Billing order " + order.orderId()
                        + ", total=" + order.totalCents()
                        + ", shipTo=" + order.shippingText()
        );
    }

    private NormalizedOrder decode(Message message)
            throws JsonProcessingException {
        MessageProperties props = message.getMessageProperties();

        if (!MessageProperties.CONTENT_TYPE_JSON.equals(
                props.getContentType())) {
            throw new IllegalArgumentException("Not application/json");
        }

        String encoding = props.getContentEncoding();
        if (encoding != null && !encoding.equalsIgnoreCase("UTF-8")) {
            throw new IllegalArgumentException("Not UTF-8");
        }

        JsonNode root = mapper.readTree(message.getBody());
        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException("Expected JSON object");
        }

        JsonNode versionNode = root.get("schemaVersion");
        if (versionNode == null || !versionNode.isIntegralNumber()
                || !versionNode.canConvertToInt()) {
            throw new IllegalArgumentException("Missing schemaVersion");
        }
        int version = versionNode.intValue();

        Object header = props.getHeaders().get("schema-version");
        if (header != null && (!(header instanceof Number)
                || ((Number) header).intValue() != version)) {
            throw new IllegalArgumentException("Version header mismatch");
        }

        requireText(root, "eventId");
        requireText(root, "orderId");

        JsonNode amount = root.get("totalCents");
        if (amount == null || !amount.isIntegralNumber()
                || !amount.canConvertToLong()
                || amount.longValue() < 0) {
            throw new IllegalArgumentException("Invalid totalCents");
        }

        if (version == 1) {
            requireText(root, "shippingAddress");
            OrderPlacedV1 v1 = mapper.treeToValue(
                    root, OrderPlacedV1.class
            );
            return new NormalizedOrder(
                    v1.eventId(),
                    v1.orderId(),
                    v1.totalCents(),
                    v1.shippingAddress(),
                    v1.couponCode()
            );
        }

        if (version == 2) {
            JsonNode shipping = root.get("shipping");
            if (shipping == null || !shipping.isObject()) {
                throw new IllegalArgumentException("Missing shipping");
            }
            requireText(shipping, "line1");
            requireText(shipping, "city");

            OrderPlacedV2 v2 = mapper.treeToValue(
                    root, OrderPlacedV2.class
            );
            return new NormalizedOrder(
                    v2.eventId(),
                    v2.orderId(),
                    v2.totalCents(),
                    v2.shipping().line1() + ", " + v2.shipping().city(),
                    v2.couponCode()
            );
        }

        throw new IllegalArgumentException(
                "Unsupported schemaVersion: " + version
        );
    }

    private static void requireText(JsonNode root, String name) {
        JsonNode field = root.get(name);
        if (field == null || !field.isTextual()
                || field.textValue().isBlank()) {
            throw new IllegalArgumentException(
                    "Missing or invalid field: " + name
            );
        }
    }
}
~~~

Một số điểm kỹ thuật:

- **Kiểm tra required fields trước khi treeToValue** để tránh field thiếu bị biến thành giá trị mặc định của kiểu nguyên thủy.
- **Body version** là nguồn chính; header có mặt thì phải bằng version trong body.
- Dữ liệu v1/v2 đều thành **NormalizedOrder**, nên code nghiệp vụ không cần nhận biết format cũ.
- **AmqpRejectAndDontRequeueException** yêu cầu không requeue khi lỗi hợp đồng. Với listener container AUTO và DLX hợp lệ, message bị reject có thể vào DLQ.
- Đoạn demo chỉ ghi log. Trong ứng dụng thật phải gọi service xử lý có **transaction, idempotency** và chính sách lỗi tạm thời riêng.
- Nếu cần, đọc **getReceivedRoutingKey()** để xác minh routing key v1/v2 khớp body version, phát hiện producer gắn sai key.

**Không bắt tất cả exception nghiệp vụ vào nhánh reject không requeue.** Ví dụ lỗi database tạm thời cần retry hữu hạn với backoff, trong khi lỗi schema cố định thường cần DLQ/quarantine và cảnh báo.

### 6.6. Gửi hai sự kiện mẫu

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SchemaDemoRunner {
    @Bean
    ApplicationRunner sendSamples(VersionedOrderPublisher publisher) {
        return args -> {
            publisher.publishV1(new OrderPlacedV1(
                    1, "evt-1001", "ord-5001", 125000,
                    "12 Nguyen Hue, Ho Chi Minh City", null
            ));

            publisher.publishV2(new OrderPlacedV2(
                    2, "evt-1003", "ord-5003", 129000,
                    new ShippingAddress("12 Nguyen Hue", "Ho Chi Minh City"),
                    "WELCOME10"
            ));
        };
    }
}
~~~

Khi đã kết nối RabbitMQ và khai báo topology đúng, cả v1 và v2 đi vào **billing.order-placed.q**, được consumer xử lý bằng hai nhánh deserialize và một mô hình chuẩn hóa.

Nếu có nhiều consumer, retry hoặc message được redeliver, **thứ tự hoàn thành không được bảo đảm** chỉ vì publisher gửi v1 trước v2.

## 7. JSON MessageConverter và type headers

Spring AMQP có **MessageConverter** giúp biến object thành AMQP Message và ngược lại. Ví dụ trong Spring AMQP 3.x, **Jackson2JsonMessageConverter** có thể chuyển DTO thành JSON; các phiên bản dùng Jackson 3 có API và import phù hợp khác.

Khi dùng converter, cần xác định:

- Converter của **RabbitTemplate** và listener có thống nhất không.
- **contentType** có là application/json không.
- **Target type** được chọn từ tham số @RabbitListener, mapping hay Java type header.
- Có chính sách bỏ qua trường lạ, nhận null, unknown enum và version mới không.
- Payload từ **Go/Python/Node.js** không nhất thiết có type header do Jackson Java tạo.

Một số converter dùng header như **__TypeId__** để mô tả Java type. **Đừng coi tên package/class Java là hợp đồng schema giữa các microservice khác ngôn ngữ**. Ưu tiên event type và schemaVersion độc lập công nghệ, sau đó ánh xạ sang DTO do consumer kiểm soát.

Cũng không deserialize tùy ý class theo type header từ nguồn không tin cậy. Dùng allowlist, type mapping hoặc DTO đích cố định.

## 8. Chiến lược triển khai v1 → v2

### 8.1. Consumer-first cho breaking change

| Giai đoạn | Producer | Consumer | Dữ liệu trong queue |
|---|---|---|---|
| A | Chỉ v1 | Đọc v1 | V1 |
| B | Chỉ v1 | **Đọc v1 + v2** | V1 |
| C | V1/v2 trong rollout | Đọc v1 + v2 | V1 và v2 có thể trộn |
| D | Chỉ v2 | Đọc v1 + v2 | V1 còn từ backlog/retry/replay |
| E | Chỉ v2 | Có thể bỏ v1 sau xác minh | Không còn v1 cần xử lý |

Nếu producer bắt đầu gửi v2 khi consumer cũ chưa hiểu, message có thể bị reject, lặp lại hoặc chuyển DLQ. Vì vậy, với **một queue chung cho nhiều version**, mở rộng khả năng đọc của consumer **trước** là chiến lược an toàn.

Không bỏ hỗ trợ v1 ngay khi producer ngừng phát v1. Kiểm tra queue, DLQ, retry, hệ thống replay và các producer cũ còn sót lại.

### 8.2. Khi nào tách queue theo version?

Có thể định tuyến như sau:

~~~text
orders.events topic exchange
  order.placed.v1 -> billing.order-placed.v1.q
  order.placed.v2 -> billing.order-placed.v2.q
~~~

Cách này hữu ích khi consumer v1 chưa nâng cấp đồng bộ được hoặc hệ thống cần cô lập backlog. Đổi lại, phải quản lý hai queue, DLQ/retry riêng, worker pool và migration dữ liệu.

**Không dual-publish v1 và v2 của cùng một sự kiện để Billing xử lý hai lần** nếu chưa có cơ chế dedup. Nếu phải phát song song, định nghĩa eventId/idempotency key, thời điểm ngừng phát cũ và cách chuyển các consumer.

### 8.3. DLQ và replay của message cũ

Một message có schema chưa hỗ trợ không nhất thiết là message “vô giá trị”. Nó có thể cần được replay sau khi nâng consumer:

1. Lưu message cùng original exchange/routing key, eventId, schemaVersion và lỗi.
2. Phân loại malformed payload, unsupported version và lỗi downstream.
3. Nâng consumer/contract trước khi replay.
4. Replay có giới hạn tốc độ và giám sát idempotency.
5. Xác nhận đã hoàn thành xử lý rồi mới dọn DLQ.

DLQ **không tự chạy lại** khi một consumer mới được deploy; cần cơ chế redrive/replay có chủ đích.

## 9. Lỗi schema và lỗi xử lý nghiệp vụ cần phân biệt

~~~mermaid
flowchart TD
    A["Message từ queue"] --> B{"Có nhận diện được schema?"}
    B -->|"Không"| C["Reject không requeue<br/>DLQ + cảnh báo"]
    B -->|"Có"| D{"Validate required fields?"}
    D -->|"Không"| C
    D -->|"Có"| E["Normalize v1/v2"]
    E --> F["Xử lý nghiệp vụ"]
    F --> G{"Thành công?"}
    G -->|"Có"| H["ACK"]
    G -->|"Lỗi tạm thời"| I["Retry hữu hạn / backoff<br/>sau ngưỡng vào DLQ"]
~~~

- **Malformed JSON, thiếu required field, version chưa hỗ trợ:** thường không được sửa bằng retry ngay cùng message; nên reject/quarantine với log rõ nguyên nhân.
- **Database/HTTP tạm gián đoạn:** có thể retry hữu hạn và delay/backoff.
- **Mất kết nối trước ACK:** message có thể giao lại; idempotency bảo vệ khỏi side effect lặp.
- **Xử lý thành công nhưng ACK không tới broker:** cùng eventId có thể nhận lại, dù schema hoàn toàn đúng.

Message ID là dữ liệu do producer cung cấp, RabbitMQ không tự loại message trùng ID. Cần unique constraint/transaction hoặc idempotency store phù hợp với nghiệp vụ.

## 10. Thay đổi cấu trúc khác dễ bị bỏ sót

| Thay đổi | Rủi ro |
|---|---|
| Thêm enum value | Consumer Java cũ có thể không parse được |
| String ID → số | Mất số 0 đầu, vượt giới hạn số chính xác của client |
| Epoch milliseconds → seconds | Sai thời gian dù vẫn là kiểu số |
| BigDecimal → double | Mất chính xác khi xử lý tiền |
| null → missing | Đổi ngữ nghĩa cập nhật/xóa trường |
| Đổi đơn vị tiền tệ | Parser vẫn chạy nhưng logic tính toán sai |
| Object → array | Consumer cũ không nhận dạng cấu trúc |
| Đổi contentType JSON → Protobuf | Cần thay decoder, contract và migration |
| Đổi tên event/routing key | Binding cũ không khớp, có thể unroutable |

Với số tiền nên có quy tắc **minorUnits + currency** hoặc decimal có precision/rounding rõ ràng. Với thời điểm nên thống nhất **UTC, ISO 8601** hoặc epoch với đơn vị ghi rõ.

**Thay đổi ngữ nghĩa là thay đổi schema**, ngay cả khi JSON parser không báo lỗi.

## 11. Quan sát và kiểm thử tương thích

### 11.1. Theo dõi đúng metadata

| Chỉ số/metadata | Mục đích |
|---|---|
| eventType, schemaVersion | Xác định loại và phiên bản message |
| exchange, routing key, queue | Chẩn đoán định tuyến |
| eventId, correlationId | Ghép log và phát hiện duplicate |
| Lỗi parse/validation theo version | Xác định consumer chưa tương thích |
| Ready, Unacked, consumer count | Nhìn backlog hoặc listener kẹt |
| DLQ count, dead-letter reason | Theo dõi lỗi không hồi phục |
| Redelivery/replay | Kiểm tra cơ chế retry/idempotency |

Không log toàn bộ payload nếu chứa dữ liệu cá nhân hoặc bí mật. Log event ID, schema version và mã lỗi thường đủ để chẩn đoán.

### 11.2. Ma trận test nên có

| Input | Kết quả mong đợi |
|---|---|
| V1 đủ trường bắt buộc | Chuẩn hóa thành NormalizedOrder |
| V1 thiếu couponCode | Xử lý với null/default đã thỏa thuận |
| V1 couponCode = null | Theo quy ước contract |
| V1 có trường JSON chưa biết | Consumer tolerant bỏ qua |
| V2 shipping object hợp lệ | Chuẩn hóa thành cùng mô hình |
| Thiếu totalCents | Reject, không tự coi là 0 |
| totalCents là chuỗi | Reject nếu schema yêu cầu integer |
| V1 thiếu shippingAddress | Reject hoặc migration đã định nghĩa |
| V2 shipping thiếu city | Reject |
| schemaVersion = 99 | DLQ/quarantine, không requeue vô hạn |
| Header schema-version khác body | Reject |
| JSON malformed | Reject |
| Replay cùng eventId | Không nhân đôi tác dụng phụ |

Nên lưu các **message mẫu/fixtures** do producer thực tế tạo và kiểm thử trực tiếp với code consumer, không chỉ unit test hai object Java. Nếu dùng JSON Schema/Avro/Protobuf và schema registry, có thể tự động hóa một phần kiểm tra tương thích, nhưng **không thay thế kiểm thử ý nghĩa nghiệp vụ**.

## 12. Bài tập thực hành

### Bài A — Xác định breaking change

Với OrderPlaced v1, đánh giá:

1. Thêm couponCode tùy chọn.
2. Xóa orderId.
3. Đổi totalCents sang String.
4. Thêm paymentMethod bắt buộc.
5. Đổi shippingAddress từ String sang object.

Hãy xác định consumer mới đọc được dữ liệu cũ không, consumer cũ đọc được dữ liệu mới không và những giả định nào về parser phải kiểm chứng.

### Bài B — Missing, null và chuỗi rỗng

~~~json
{"schemaVersion":1,"eventId":"evt-a","orderId":"ord-a","totalCents":100,"shippingAddress":"A"}
{"schemaVersion":1,"eventId":"evt-b","orderId":"ord-b","totalCents":100,"shippingAddress":"B","couponCode":null}
{"schemaVersion":1,"eventId":"evt-c","orderId":"ord-c","totalCents":100,"shippingAddress":"C","couponCode":""}
~~~

Viết validation cho couponCode theo contract của nhóm: khi nào xem là không có mã, khi nào reject?

### Bài C — Nâng lên v3

Giả sử v3 đổi amount thành object:

~~~json
{
  "schemaVersion": 3,
  "eventId": "evt-3001",
  "orderId": "ord-6001",
  "money": {
    "minorUnits": 120000,
    "currency": "VND"
  },
  "shipping": {
    "line1": "12 Nguyen Hue",
    "city": "Ho Chi Minh City"
  }
}
~~~

Thêm DTO v3, branch deserialize, validation currency, binding v3 và test v1/v2 vẫn xử lý được.

### Bài D — Kế hoạch rollout

Queue có 100.000 message v1, ba instance Billing đang chạy phiên bản cũ. Order Service cần chuyển v2. Đề xuất thứ tự triển khai, cách quan sát backlog, DLQ, retry và điều kiện gỡ hỗ trợ v1.

### Bài E — Xử lý message chưa hỗ trợ

Gửi schemaVersion=99. Xác nhận consumer phân loại là lỗi schema và từ chối không requeue. Mô tả quy trình nâng code rồi replay message từ DLQ cùng idempotency key.

## 13. Những điều cần nhớ

- **Schema là hợp đồng dữ liệu giữa producer và consumer**, RabbitMQ không tự chuyển cấu trúc body.
- **Backward compatibility** cho phép consumer mới đọc message cũ; **forward compatibility** cho phép consumer cũ đọc message mới.
- Thêm optional field thường dễ tương thích hơn việc đổi tên/kiểu hoặc bỏ required field, nhưng phải thử cả **missing**, **null** và **unknown fields**.
- **Breaking change** cần schema version mới hoặc cơ chế adapter rõ ràng; rollout consumer-first giúp đọc được backlog v1 và dữ liệu v2.
- **Version trong body, header và routing key** phải nhất quán nếu được dùng đồng thời.
- **Chuẩn hóa v1/v2 về mô hình nội bộ chung** giúp nghiệp vụ ít phụ thuộc format bên ngoài.
- Lỗi schema thường cần DLQ/quarantine, còn lỗi downstream tạm thời có thể retry hữu hạn.
- **Publisher confirms, ACK, dead-letter, transaction và idempotency** vẫn cần thiết để xử lý bất đồng bộ đáng tin cậy khi schema phát triển.

### Tài liệu tham khảo

- [Spring AMQP — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): chuyển đổi object và AMQP Message.
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/): RabbitTemplate, @RabbitListener và xử lý lỗi.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): xác nhận giao nhận.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): xử lý dead-letter.
- [RFC 8259 — JSON](https://www.rfc-editor.org/rfc/rfc8259): cấu trúc JSON và khả năng tương tác.
