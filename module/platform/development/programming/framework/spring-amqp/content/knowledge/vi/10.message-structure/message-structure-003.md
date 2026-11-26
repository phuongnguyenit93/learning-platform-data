# Content type, content encoding và định dạng dữ liệu

Trong chương **Cấu trúc thông điệp** của **SPRING_AMQP**, một message RabbitMQ không phải lúc nào cũng là chuỗi ký tự hoặc đối tượng Java. Ở cấp giao thức, message có **body là dãy byte** kèm các **properties** và **headers** mô tả ý nghĩa của dãy byte đó. Producer sử dụng **RabbitTemplate** để gửi message; consumer có thể dùng **@RabbitListener** để lấy dữ liệu và chuyển lại thành kiểu phù hợp.

Ba quyết định quan trọng nhất khi thiết kế message là: **body được tuần tự hóa theo định dạng nào**, **content type thể hiện định dạng đó ra sao** và **content encoding cho biết các byte được biểu diễn như thế nào**. Nếu hai phía hiểu khác nhau, hệ thống vẫn có thể kết nối RabbitMQ, định tuyến qua exchange/queue/binding và ACK thành công nhưng lại xử lý sai dữ liệu nghiệp vụ.

Ví dụ xuyên suốt: Order Service phát sự kiện **OrderCreated** dưới dạng JSON để Billing Service tiếp nhận. Mục tiêu là để producer Java, consumer Java và cả consumer ở ngôn ngữ khác đều giải mã được cùng hợp đồng dữ liệu.

## 1. Cấu trúc một message AMQP 0-9-1

~~~mermaid
flowchart LR
    P["Order Service<br/>Object Java"] --> S["Serialize<br/>JSON UTF-8"]
    S --> B["Body: byte[]"]
    M["Properties:<br/>contentType<br/>contentEncoding<br/>messageId"] --> X["AMQP message"]
    B --> X
    H["Headers:<br/>schema-version<br/>event-type"] --> X
    X --> E["Exchange → Queue"]
    E --> C["Billing Consumer<br/>Decode + Validate"]
~~~

Một message có thể được mô tả theo ba phần:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| **Body** | Các byte của JSON chứa orderId | Nội dung dữ liệu nghiệp vụ |
| **Standard properties** | contentType, contentEncoding, messageId, correlationId, deliveryMode | Metadata phổ biến của AMQP, định hướng xử lý |
| **Application headers** | schema-version = 1, event-type = order.created | Metadata do ứng dụng quy ước |

Lưu ý rằng **exchange** và **routing key** tham gia quá trình publish/định tuyến; chúng không tự xác định body là JSON hay binary. **Queue** giữ delivery; **consumer** chịu trách nhiệm giải mã nội dung theo hợp đồng đã thống nhất.

### 1.1. Body là byte[], không mặc định là String

Giả sử payload là:

~~~json
{
  "eventId": "evt-2001",
  "orderId": "ord-1001",
  "customerName": "Nguyễn An",
  "schemaVersion": 1
}
~~~

Trước khi gửi, dữ liệu này phải được chuyển thành byte. Với **UTF-8**, chữ tiếng Việt có dấu thường chiếm nhiều byte hơn ký tự ASCII. Nếu consumer dùng charset khác để giải mã, nội dung có thể thành ký tự lỗi.

~~~java
import java.nio.charset.StandardCharsets;

String json = "{\"customerName\":\"Nguyễn An\"}";

byte[] body = json.getBytes(StandardCharsets.UTF_8);

// Phía nhận:
String restored = new String(body, StandardCharsets.UTF_8);
System.out.println(restored);
~~~

Ví dụ đơn giản này chưa cần RabbitMQ nhưng giải thích bản chất của việc trao đổi dữ liệu qua message. **RabbitMQ không tự parse JSON và không tự sửa charset sai** cho ứng dụng.

### 1.2. Các properties nên nhận biết

| Property | Chức năng | Ví dụ |
|---|---|---|
| **contentType** | Loại nội dung theo cú pháp MIME | application/json |
| **contentEncoding** | Thông tin biểu diễn/giải mã nội dung theo quy ước hai phía | UTF-8 |
| **messageId** | Định danh message | evt-2001 |
| **correlationId** | Liên kết các message trong một quy trình hoặc request/reply | flow-901 |
| **replyTo** | Nơi gửi phản hồi trong request/reply | reply.queue |
| **type** | Nhãn loại message mức ứng dụng | order.created |
| **timestamp** | Thời điểm do producer gắn | Thời điểm publish/sự kiện tùy hợp đồng |
| **deliveryMode** | Thông tin persistence ở mức message | PERSISTENT |
| **priority** | Độ ưu tiên của message, nếu queue hỗ trợ | 3 |
| **headers** | Các key/value mở rộng | schema-version = 1 |

**messageId** có thể giúp truy vết và chống xử lý trùng, nhưng RabbitMQ **không tự đảm bảo duy nhất**, **không tự deduplicate** chỉ vì hai message trùng ID. Producer phải có quy tắc sinh ID; consumer phải có cơ chế idempotency nếu nghiệp vụ cần.

## 2. Content type: body đang chứa định dạng gì?

**Content type** (AMQP basic property **content_type**) là chuỗi mô tả loại dữ liệu, thường dùng MIME media type.

| Content type | Body thường chứa | Trường hợp dùng |
|---|---|---|
| **application/json** | JSON được mã hóa thành byte | Event, command, DTO liên dịch vụ |
| **text/plain** | Văn bản thuần | Thông báo/chỉ thị văn bản ngắn |
| **application/octet-stream** | Byte nhị phân chung | File/chunk dữ liệu hoặc codec tự định nghĩa |
| **application/xml** | XML | Hệ thống cần tương thích XML |
| **application/protobuf** hoặc một media type đã thỏa thuận | Protobuf binary | Contract protobuf/schema rõ ràng |
| **application/x-java-serialized-object** | Java native serialization | Cần cân nhắc tránh trong tích hợp liên dịch vụ |

Các media type như **application/json**, **text/plain** và **application/octet-stream** có ý nghĩa quen thuộc. Với định dạng binary đặc thù, các đội phải thỏa thuận tên media type và phiên bản schema; **contentType là nhãn**, không đảm bảo consumer có đủ decoder.

### 2.1. Content type không phải routing key

~~~text
Exchange: commerce.orders.events
Routing key: order.created.v1
Queue: billing.order-created.q
Content type: application/json
Content encoding: UTF-8
Body: {"eventId":"evt-2001","orderId":"ord-1001"}
~~~

Exchange dựa trên **routing key/binding** để chọn queue. Content type giúp **consumer và message converter** biết cách đọc body. Trên các exchange thông dụng direct/topic/fanout, content type không tự quyết định định tuyến.

Nếu cần định tuyến theo header như media type, có thể dùng **headers exchange** với binding header thích hợp; đây là lựa chọn topology riêng, không phải hành vi mặc định.

### 2.2. Khai báo sai content type có thể gây hậu quả gì?

Giả sử body thực tế là JSON nhưng producer gắn **text/plain**. Với một số converter, consumer có thể nhận được **String** thay vì DTO; với converter khác, nó có thể bị từ chối.

Ngược lại, body thực tế là một tệp nén nhưng gắn **application/json**, bộ giải mã JSON sẽ báo lỗi. Vì vậy, **contentType phải khớp với byte thực tế**, không được chỉ đặt theo tên event.

## 3. Content encoding và charset

**Content encoding** là một standard property kiểu chuỗi của AMQP. Trong Spring AMQP, nó thường được sử dụng để ghi **charset của nội dung văn bản**, chẳng hạn **UTF-8**. Nhưng không nên giả định mọi hệ thống dùng trường này theo một quy ước giống nhau, vì đôi khi nó được sử dụng để mô tả phép biến đổi như nén dữ liệu.

Phân biệt ba tầng:

| Tầng | Câu hỏi | Ví dụ |
|---|---|---|
| **Format** | Dữ liệu có cấu trúc gì? | JSON |
| **Character encoding** | Văn bản chuyển sang byte thế nào? | UTF-8 |
| **Compression/transform** | Dữ liệu đã biến đổi thêm chưa? | gzip trước khi publish |

Ví dụ:

~~~text
Java object
   ↓ Serialize
JSON text
   ↓ UTF-8 encode
JSON bytes
   ↓ (tùy chọn) gzip
Compressed bytes
   ↓ Publish
AMQP body
~~~

Một consumer phải làm **ngược lại các bước đã được producer áp dụng**. Nếu producer nén bằng gzip, consumer phải giải nén trước khi parse JSON; chỉ đặt một chuỗi **contentEncoding=gzip** không khiến mọi consumer và converter tự giải nén.

### 3.1. UTF-8 là mặc định hợp lý cho JSON liên dịch vụ

Ví dụ hợp đồng đơn giản:

~~~text
contentType = application/json
contentEncoding = UTF-8
body = JSON bytes encoded as UTF-8
~~~

Ưu tiên UTF-8 vì hỗ trợ Unicode, phổ biến trên các ngôn ngữ, và tương thích tốt với JSON. Các consumer cần nhất quán về charset khi giải mã text; nếu đã thỏa thuận UTF-8, không nên tự suy từ locale của hệ điều hành.

Với JSON truyền giữa hệ thống, cũng có thể ghi charset theo tham số của media type, chẳng hạn **application/json; charset=UTF-8**, tùy converter và giao thức tích hợp. Nên **chọn một quy ước thống nhất** và tránh để contentType và contentEncoding mâu thuẫn.

### 3.2. Khi content encoding bị thiếu

Trong nhiều cấu hình, **contentEncoding** có thể là null/không được cung cấp. Consumer phải có fallback theo hợp đồng; ví dụ JSON được thỏa thuận là UTF-8. Không nên tự mặc định dữ liệu nhị phân cũng là UTF-8.

Ví dụ xử lý an toàn đối với message đã thỏa thuận là JSON UTF-8:

~~~java
String encoding = message.getMessageProperties().getContentEncoding();

if (encoding != null && !encoding.equalsIgnoreCase("UTF-8")) {
    throw new IllegalArgumentException(
            "Unsupported content encoding: " + encoding
    );
}
~~~

Sau đó có thể parse trực tiếp **byte[]** bằng JSON parser đã được cấu hình, hoặc chuyển thành **String** qua **StandardCharsets.UTF_8**.

### 3.3. Không nhập nhằng encoding văn bản và nén

Nếu cần nén JSON, hãy định nghĩa rõ:

- **Định dạng logic** của dữ liệu sau khi giải nén là JSON.
- **Thuật toán nén** được biểu diễn ở property/header nào và tên giá trị chuẩn là gì.
- **Trình tự xử lý**: giải nén → decode/parse JSON.
- **Giới hạn kích thước sau giải nén** để tránh payload nén nhỏ nhưng giải nén quá lớn.
- **Producer/consumer** đều dùng codec được kiểm soát; không tự phát kết hợp các bộ chuyển đổi có cách hiểu contentEncoding khác nhau.

Spring AMQP có các post-processor để nén/giải nén message; nếu dùng, phải cấu hình đúng ở cả chiều gửi và chiều nhận. Không giả định RabbitMQ broker sẽ thực hiện bước nén hoặc giải nén thay ứng dụng.

## 4. Chọn định dạng dữ liệu theo nhu cầu

| Định dạng | Ưu điểm | Hạn chế | Khi nên cân nhắc |
|---|---|---|---|
| **JSON** | Dễ đọc, đa ngôn ngữ, công cụ phong phú | Có thể lớn hơn binary; cần quản lý schema | Event/command giữa microservice |
| **Plain text** | Đơn giản | Thiếu cấu trúc và validation phức tạp | Thông báo ngắn, job chỉ gồm ID |
| **Protobuf/Avro** | Gọn, schema rõ, có công cụ sinh code | Cần hệ sinh thái schema/tooling | Lưu lượng lớn, hợp đồng chặt |
| **XML** | Có schema và tích hợp legacy | Verbose | Kết nối hệ thống XML |
| **Binary tự định nghĩa** | Có thể tối ưu sâu | Khó debug và dễ lệch phiên bản | Bài toán có codec riêng |
| **Java serialization** | Dễ truyền object trong môi trường Java | Rủi ro bảo mật, phụ thuộc class/JVM, kém tương thích | Thường **tránh** trong hệ thống có nhiều dịch vụ |

**Khuyến nghị khởi đầu cho bài học:** chọn **JSON + UTF-8 + schemaVersion**. Nó phù hợp mục tiêu Spring AMQP: kết hợp RabbitTemplate, @RabbitListener, định tuyến message và kiểm thử xử lý bất đồng bộ. Chỉ chuyển sang binary khi có số liệu throughput, bandwidth, payload size hoặc yêu cầu schema chứng minh lợi ích.

Đừng đặt định dạng dựa trên sở thích của một microservice nếu nhiều dịch vụ ngôn ngữ khác phải tiêu thụ. Contract nên mô tả ý nghĩa trường, kiểu dữ liệu và quy tắc phát triển phiên bản.

## 5. Thực hành: gửi JSON kèm content metadata

Ví dụ này dùng **Spring Boot + Spring AMQP** và Java 17. Producer chuyển object thành JSON bytes rồi gửi với các thuộc tính mô tả đúng. Consumer nhận raw message, xác minh metadata rồi giải mã.

### 5.1. Dependency và kết nối

Với Maven:

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

Ví dụ kết nối RabbitMQ local:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    virtual-host: app_dev
    username: learn_amqp
    password: local-demo-only
~~~

Các giá trị vhost/user/password phải được tạo và cấp quyền trước trên broker. Mật khẩu trên chỉ minh họa; dùng biến môi trường hoặc secret manager trong môi trường thật.

### 5.2. Khai báo exchange, queue và binding

~~~java
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class MessageStructureTopology {
    public static final String EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "order.created.v1";
    public static final String QUEUE = "billing.order-created.q";

    @Bean
    public Declarables messageStructureResources() {
        DirectExchange exchange =
                new DirectExchange(EXCHANGE, true, false);
        Queue queue = QueueBuilder.durable(QUEUE).build();

        return new Declarables(
                exchange,
                queue,
                BindingBuilder.bind(queue)
                        .to(exchange)
                        .with(ROUTING_KEY)
        );
    }
}
~~~

**Direct exchange** chọn queue theo routing key chính xác. Việc queue nhận JSON hay text được quyết định bởi **message properties và consumer logic**, không phải bởi loại exchange. Trong cấu hình Spring Boot thông dụng, RabbitAdmin có thể tự khai báo các bean topology khi kết nối được thiết lập.

### 5.3. Định nghĩa dữ liệu nghiệp vụ

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        String customerName,
        int schemaVersion
) {}
~~~

Đây là DTO đơn giản cho thực hành; ứng dụng thật thường bổ sung **occurredAt**, thông tin trạng thái và các trường nghiệp vụ cần thiết. Với hợp đồng đa ngôn ngữ, ghi rõ kiểu thời gian (ví dụ UTC/ISO 8601) và quy tắc số tiền, mã tiền tệ để không mất độ chính xác.

### 5.4. Producer: serialize JSON thành byte và gắn properties

Ví dụ dưới đây dùng **Jackson 2 ObjectMapper** thường có trong dự án Spring Boot 3.x. Nếu ứng dụng dùng Jackson 3/Spring Boot 4.x, dùng API mapper phù hợp phiên bản đó; ý tưởng chuẩn hóa JSON bytes và AMQP metadata giữ nguyên.

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class OrderEventPublisher {
    private final RabbitTemplate rabbitTemplate;
    private final ObjectMapper objectMapper;

    public OrderEventPublisher(
            RabbitTemplate rabbitTemplate,
            ObjectMapper objectMapper
    ) {
        this.rabbitTemplate = rabbitTemplate;
        this.objectMapper = objectMapper;
    }

    public void publish(OrderCreatedEvent event) throws Exception {
        // Jackson tạo JSON hợp lệ, tránh tự nối chuỗi từ dữ liệu đầu vào.
        byte[] jsonBytes = objectMapper.writeValueAsBytes(event);

        Message message = MessageBuilder.withBody(jsonBytes)
                .setContentType(MessageProperties.CONTENT_TYPE_JSON)
                .setContentEncoding(StandardCharsets.UTF_8.name())
                .setMessageId(event.eventId())
                .setHeader("schema-version", event.schemaVersion())
                .setHeader("event-type", "order.created")
                .build();

        rabbitTemplate.send(
                MessageStructureTopology.EXCHANGE,
                MessageStructureTopology.ROUTING_KEY,
                message
        );
    }
}
~~~

Khi sử dụng **RabbitTemplate.send(...)**, bạn truyền một **Message đã có body bytes + properties**. Trong ví dụ này, Spring AMQP không cần tự đoán kiểu dữ liệu từ object, vì code đã chủ động tạo JSON bytes.

Giá trị quan trọng:

~~~text
contentType     = application/json
contentEncoding = UTF-8
messageId       = evt-2001
headers:
  schema-version = 1
  event-type     = order.created
body:
  {"eventId":"evt-2001","orderId":"ord-1001", ...}
~~~

RabbitMQ truyền những property này cùng message, nhưng **không kiểm tra JSON có đúng schema hay không**. Producer phải serialize đúng và consumer phải validate.

### 5.5. Consumer: kiểm tra content type, encoding và parse body

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class BillingOrderListener {
    private final ObjectMapper objectMapper;

    public BillingOrderListener(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @RabbitListener(queues = MessageStructureTopology.QUEUE)
    public void receive(Message message) throws Exception {
        MessageProperties props = message.getMessageProperties();

        String contentType = props.getContentType();
        if (!MessageProperties.CONTENT_TYPE_JSON.equals(contentType)) {
            throw new IllegalArgumentException(
                    "Unsupported contentType: " + contentType
            );
        }

        String encoding = props.getContentEncoding();
        if (encoding != null && !encoding.equalsIgnoreCase("UTF-8")) {
            throw new IllegalArgumentException(
                    "Unsupported contentEncoding: " + encoding
            );
        }

        OrderCreatedEvent event = objectMapper.readValue(
                message.getBody(), OrderCreatedEvent.class
        );

        if (event.schemaVersion() != 1) {
            throw new IllegalArgumentException(
                    "Unsupported schema version: " + event.schemaVersion()
            );
        }

        System.out.println(
                "Billing received order " + event.orderId()
        );

        // Ở đây sẽ gọi service nghiệp vụ có xử lý lặp an toàn.
    }
}
~~~

Ví dụ cố ý yêu cầu **contentType = application/json chính xác**. Trong tích hợp thực tế có thể chấp nhận cú pháp media type với tham số, như **application/json; charset=UTF-8**, bằng bộ phân tích MIME phù hợp; nên chuẩn hóa quy tắc ở hai phía trước khi mở rộng.

Listener nhận **org.springframework.amqp.core.Message** nên đọc được raw body, headers và properties. Sau khi gọi **objectMapper.readValue(byte[], ...)**, JSON parser chuyển dữ liệu sang **OrderCreatedEvent**.

Trong cấu hình listener AUTO thông dụng, phương thức **trả về thành công** thì container xác nhận delivery. Nếu deserialize hoặc validate lỗi, listener ném exception; kết quả requeue/retry/dead-letter sẽ phụ thuộc cấu hình container và chiến lược xử lý lỗi. **Không mặc định mọi exception đều tự vào DLQ**.

### 5.6. Thử nghiệm end-to-end

Một runner đơn giản để tạo một sự kiện:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PublishDemoRunner {
    @Bean
    ApplicationRunner publishExample(OrderEventPublisher publisher) {
        return args -> publisher.publish(
                new OrderCreatedEvent(
                        "evt-2001",
                        "ord-1001",
                        "Nguyễn An",
                        1
                )
        );
    }
}
~~~

Các bước chạy:

1. Khởi động RabbitMQ và bảo đảm vhost/tài khoản được cấp quyền.
2. Khởi động Spring Boot với các class của bài và kiểm tra exchange **orders.events**, queue **billing.order-created.q**, binding **order.created.v1**.
3. Quan sát log listener có **Billing received order ord-1001**.
4. Trong RabbitMQ Management UI, có thể tạm dừng consumer hoặc dùng một queue thử nghiệm để xem property **content_type**, **content_encoding** và các headers khi message còn chờ.
5. Thử đổi **contentType** thành **text/plain** nhưng vẫn gửi JSON bytes; quan sát listener từ chối theo hợp đồng.
6. Thử truyền payload JSON không hợp lệ; quan sát lỗi parse và chính sách retry/requeue đang áp dụng.

Để tránh vòng lặp message lỗi khi thử, dùng queue/broker dành riêng cho phát triển và xác định chính sách giới hạn retry hoặc dead-letter trước khi phát nhiều message malformed.

## 6. MessageConverter: để Spring AMQP chuyển đổi thay ứng dụng

Ở mục 5, ta dùng **RabbitTemplate.send(Message)** và **@RabbitListener(Message)** để thấy rõ body bytes và metadata. Trong ứng dụng thường gặp, Spring AMQP cung cấp **MessageConverter** để tự chuyển **object ↔ byte[]** theo quy tắc đã cấu hình.

~~~mermaid
flowchart LR
    O["Object Java"] -->|"toMessage()"| MC["MessageConverter"]
    MC --> AMQP["AMQP Message<br/>body + properties"]
    AMQP -->|"fromMessage()"| MC2["MessageConverter"]
    MC2 --> DTO["DTO / String / byte[]"]
~~~

### 6.1. SimpleMessageConverter làm gì?

Một cấu hình Spring AMQP phổ biến dùng **SimpleMessageConverter**:

| Object khi gửi | Hành vi thường gặp | Lưu ý |
|---|---|---|
| **String** | Mã hóa theo charset, content type văn bản | Consumer cần cùng charset |
| **byte[]** | Giữ nguyên body bytes | Content type thường là dạng binary/default nếu không đặt rõ |
| **Serializable** | Java native serialization, content type riêng | **Không khuyến nghị** khi trao đổi giữa microservice |

Ở chiều nhận, SimpleMessageConverter dựa vào content type để quyết định xử lý text hoặc Java serialization; với những loại không được hỗ trợ như JSON của bên thứ ba, nó có thể trả về **byte[]**. Vì vậy, **convertAndSend(object)** không có nghĩa Spring AMQP tự tạo JSON cho mọi object.

**Không nên dựa vào Java native deserialization của dữ liệu không đáng tin cậy.** Nó mang rủi ro bảo mật, phụ thuộc tên class và phiên bản Java, khó tích hợp với service dùng ngôn ngữ khác. Ưu tiên JSON với schema rõ ràng hoặc codec binary được kiểm soát.

### 6.2. JSON MessageConverter

Nếu ứng dụng dùng Spring AMQP 3.x với Jackson 2, có thể khai báo converter:

~~~java
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JsonMessageConverterConfig {
    @Bean
    public MessageConverter jsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }
}
~~~

Khi converter này được sử dụng cho cả producer và listener, đoạn gửi có thể ngắn hơn:

~~~java
rabbitTemplate.convertAndSend(
        MessageStructureTopology.EXCHANGE,
        MessageStructureTopology.ROUTING_KEY,
        new OrderCreatedEvent("evt-2002", "ord-1002", "Linh", 1)
);
~~~

Và listener có thể nhận DTO trực tiếp:

~~~java
@RabbitListener(queues = MessageStructureTopology.QUEUE)
public void receive(OrderCreatedEvent event) {
    System.out.println(event.orderId());
}
~~~

**Hai đoạn code trên là phương án khác với raw Message ở mục 5**; không đăng ký đồng thời hai listener nghe cùng một queue trong cùng bài thử nếu bạn muốn cả hai nhận một bản sao, vì chúng sẽ là competing consumers.

Điều kiện quan trọng: **RabbitTemplate** và **listener container** phải thực sự sử dụng JSON converter. Với cấu hình auto-configuration thông dụng, Spring Boot có thể phát hiện bean MessageConverter; nếu tự tạo RabbitTemplate hoặc listener factory, hãy gán converter rõ ràng.

Ví dụ cấu hình listener factory do ứng dụng tự tạo:

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;

@Bean
public SimpleRabbitListenerContainerFactory jsonListenerFactory(
        ConnectionFactory connectionFactory,
        MessageConverter jsonMessageConverter
) {
    SimpleRabbitListenerContainerFactory factory =
            new SimpleRabbitListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setMessageConverter(jsonMessageConverter);
    return factory;
}
~~~

Khi dùng factory này, khai báo **containerFactory="jsonListenerFactory"** trên @RabbitListener. Đoạn trên là phương thức bean mẫu cần đặt trong một lớp **@Configuration**, không phải một class Java độc lập.

**Phiên bản thư viện rất quan trọng.** Các phiên bản Spring AMQP dùng Jackson 3 có class converter/API khác phiên bản dùng Jackson 2; chọn đúng converter theo tài liệu của phiên bản dự án. Không copy import của Spring AMQP 3.x vào dự án 4.x mà không kiểm tra.

### 6.3. Headers mô tả kiểu Java không phải hợp đồng schema công khai

Các JSON converter có thể dùng header nội bộ như **__TypeId__**, **__ContentTypeId__** để hỗ trợ suy luận kiểu. Những giá trị này có thể phụ thuộc tên lớp hoặc cấu hình mapper của ứng dụng Java.

Nếu producer Java giao tiếp với consumer Node.js, Go hoặc Python, nên xem **contentType**, **schemaVersion** và **trường nghiệp vụ trong JSON** là hợp đồng chính. Không yêu cầu hệ thống khác biết tên package Java như **com.example.domain.OrderCreatedEvent** để parse event.

Ngoài ra, **không tin cậy header tự khai báo kiểu từ nguồn bên ngoài để deserialize tùy ý**. Dùng target DTO cố định, danh sách kiểu được cho phép hoặc chính sách type mapping kiểm soát chặt.

## 7. Hợp đồng message nên mô tả những gì?

Một message contract tốt cần nhiều thông tin hơn contentType đơn lẻ.

Ví dụ hợp đồng **OrderCreated v1**:

| Thuộc tính | Quy định |
|---|---|
| Exchange | **orders.events** |
| Routing key | **order.created.v1** |
| Content type | **application/json** |
| Encoding | **UTF-8** |
| Event name | **order.created** |
| Schema version | **1** |
| ID của event | **eventId** (duy nhất theo quy ước producer) |
| ID nghiệp vụ | **orderId** |
| Thời gian | **occurredAt**, ISO 8601 UTC |
| Payload | JSON có trường bắt buộc và optional rõ ràng |
| Quy tắc retry | Giới hạn số lần thử và xử lý trường hợp không giải mã được |
| Xử lý lặp | Consumer idempotent theo **eventId** |

Ví dụ envelope JSON có thể dùng:

~~~json
{
  "eventId": "evt-2001",
  "eventType": "order.created",
  "schemaVersion": 1,
  "occurredAt": "2026-11-26T01:30:00Z",
  "data": {
    "orderId": "ord-1001",
    "customerName": "Nguyễn An"
  }
}
~~~

Có thể để **eventType/schemaVersion** ở headers hoặc bên trong payload, thậm chí cả hai vì nhu cầu quan sát và tương thích. Nếu đặt hai nơi, phải xác định chúng có đồng nhất hay không; không để header nói version 2 nhưng body là schema version 1.

### 7.1. Thay đổi schema mà không làm hỏng consumer

| Thay đổi | Mức rủi ro | Cách kiểm soát |
|---|---|---|
| Thêm trường tùy chọn | Thường thấp nếu consumer bỏ qua trường lạ | Kiểm thử deserializer của consumer |
| Bỏ trường đang bắt buộc | Cao | Phát version mới, triển khai lộ trình chuyển đổi |
| Đổi kiểu **orderId** từ String sang number | Cao | Bản mới có schema/version khác |
| Đổi JSON sang Protobuf | Cao | Đổi contract và contentType, hỗ trợ cả hai trong giai đoạn chuyển đổi |
| Thêm header phụ trợ | Thường thấp | Không cho consumer cũ phụ thuộc header mới |

Khi có nhiều service, publish một event không chỉ là phương thức Java: đó là thay đổi hợp đồng. Cần kiểm thử **producer → serialized bytes → consumer decode** thay vì chỉ unit test DTO.

### 7.2. Phân biệt version của event và version của giao thức

- **AMQP 0-9-1**: giao thức RabbitMQ đang dùng để chuyển message.
- **schemaVersion = 1/2**: phiên bản của **dữ liệu nghiệp vụ** trong message.
- **RabbitMQ server version**: phiên bản broker.
- **Spring AMQP / Jackson version**: phiên bản thư viện serializer/deserializer.

Chúng là bốn loại phiên bản khác nhau. Ví dụ, nâng Spring AMQP không tự nâng schemaVersion của tất cả event, nhưng có thể làm thay đổi cách converter xử lý metadata; cần kiểm thử tương thích.

## 8. Xử lý content type hoặc payload sai trong consumer

Khi consumer gặp message mà nó không thể giải mã:

~~~mermaid
flowchart TD
    A["Delivery từ RabbitMQ"] --> B{"Content type hỗ trợ?"}
    B -->|"Không"| X["Lỗi không tương thích"]
    B -->|"Có"| C{"Encoding/transform phù hợp?"}
    C -->|"Không"| X
    C -->|"Có"| D{"Decode + validate schema thành công?"}
    D -->|"Không"| X
    D -->|"Có"| E["Xử lý nghiệp vụ"]
    E --> F{"Thành công?"}
    F -->|"Có"| G["ACK"]
    F -->|"Không"| H["Retry hữu hạn / DLQ"]
    X --> I["DLQ/quarantine + cảnh báo"]
~~~

Phân loại lỗi quan trọng:

- **Không hỗ trợ contentType**, sai charset, body không parse được, schemaVersion không hỗ trợ: thường là lỗi **khó tự hồi phục** nếu retry nguyên message không thay đổi. Cần đưa vào DLQ/quarantine và thông báo cho producer hoặc đội quản lý contract.
- **Database/HTTP downstream tạm gián đoạn**: có thể thử lại **có giới hạn**, kèm delay/backoff.
- **Broker/consumer mất kết nối trước ACK**: message có thể bị giao lại, vì vậy xử lý phải idempotent.

**Không để message JSON hỏng liên tục requeue ngay** vì sẽ tạo vòng lặp lỗi và tiêu tốn CPU. Spring AMQP có các cơ chế error handler, retry interceptor, recoverer và dead-letter theo cấu hình; cần thiết kế rõ trong ứng dụng.

### 8.1. Chỉ dùng ACK sau khi xử lý phù hợp

Content type đúng không có nghĩa công việc đã hoàn thành. Consumer nên ACK theo cơ chế listener container sau khi deserialize, validate và xử lý nghiệp vụ thành công. Nếu nghiệp vụ có transaction database, cần phối hợp ACK và commit theo chiến lược tin cậy.

Trường hợp database đã ghi xong nhưng consumer chết trước ACK, RabbitMQ có thể giao lại message. **eventId** trong body hoặc **messageId** trong property hữu ích cho xử lý trùng, nhưng phải kết hợp ràng buộc/transaction ở storage; broker không tự làm việc này.

## 9. Quan sát và chẩn đoán lỗi định dạng

Trong RabbitMQ Management UI, khi một message còn đang chờ, có thể xem **Properties**, **Headers**, **Payload** (tùy cách UI hiển thị và quyền truy cập). Với payload binary, UI có thể chỉ hiển thị dạng byte/base64; điều đó **không chứng minh dữ liệu bị hỏng**.

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Chữ tiếng Việt thành ký tự lạ | Encode/decode khác charset | Đối chiếu UTF-8 từ producer đến consumer |
| Listener nhận byte[] dù mong DTO | Converter mặc định không hiểu JSON | Kiểm tra MessageConverter và contentType |
| Lỗi JSON parse | Payload không phải JSON hợp lệ hoặc sai charset | Kiểm tra body bytes và contract |
| Lỗi không tương thích schema | Trường bắt buộc thiếu, kiểu khác, version mới | Kiểm tra schemaVersion và serializer |
| Consumer yêu cầu class Java không tồn tại | Phụ thuộc type header Java nội bộ | Cố định DTO đích hoặc dùng mapping độc lập ngôn ngữ |
| Gửi thành công nhưng không có message trong queue | Routing key/binding không khớp | Kiểm tra exchange, routing và publisher return |
| Delivery lặp dù contentType đúng | ACK mất, redelivery/retry | Xem redelivered flag và idempotency |
| Payload bị nén đọc như văn bản | Chưa giải nén hoặc dùng sai codec | Kiểm tra quy ước compression |
| Chỉ một số instance lỗi decode | Khác version/schema/converter giữa instance | Kiểm tra rollout và compatibility |

### 9.1. Log đủ để truy vết, nhưng không lộ dữ liệu

Một bản log hữu ích thường có:

~~~text
eventId=evt-2001
eventType=order.created
schemaVersion=1
contentType=application/json
contentEncoding=UTF-8
routingKey=order.created.v1
bodySizeBytes=142
decodeStatus=success
~~~

Nên tránh log toàn bộ body nếu message có dữ liệu cá nhân, token hoặc thông tin thanh toán. Log **messageId/eventId**, schema version, định dạng và kích thước thường đủ để điều tra phần lớn lỗi metadata; log payload chỉ khi có quyền và cơ chế bảo vệ phù hợp.

## 10. Kiểm thử tương thích giữa producer và consumer

Một bộ kiểm thử hữu ích có thể chứa các trường hợp:

1. **Happy path:** JSON UTF-8 hợp lệ, contentType = application/json, schemaVersion được hỗ trợ.
2. **Sai contentType:** body JSON nhưng metadata text/plain → consumer từ chối có kiểm soát.
3. **Thiếu contentEncoding:** xử lý theo fallback đã thỏa thuận, không phụ thuộc locale máy chạy.
4. **Sai charset:** body không phải UTF-8 hợp lệ hoặc khai báo encoding không đúng → báo lỗi thay vì âm thầm sửa.
5. **JSON malformed:** thiếu dấu ngoặc, trường sai kiểu → đi vào luồng xử lý lỗi định dạng.
6. **Version tương thích:** thêm trường optional và kiểm tra consumer cũ vẫn đọc được.
7. **Version không tương thích:** schemaVersion mới có thay đổi phá vỡ → consumer không ACK thành công như thể đã xử lý.
8. **Thử lại/đưa vào DLQ:** malformed payload không bị retry vô hạn.
9. **Nhiều consumer:** hai bản triển khai dùng cùng contract; không phụ thuộc package/class Java của producer.
10. **Payload lớn:** áp giới hạn kích thước trước và sau giải nén để tránh cạn bộ nhớ.

Nên lưu một vài **message mẫu (fixtures)** theo schema và kiểm thử thực tế **serialize → publish hoặc tạo Message → deserialize**. Unit test chỉ so sánh hai object Java có thể bỏ sót sự khác biệt ở contentType, charset và header.

## 11. Bài tập thực hành

### Bài A — Phân biệt metadata và nội dung

Với message sau:

~~~text
Exchange: orders.events
Routing key: order.created.v1
contentType: application/json
contentEncoding: UTF-8
messageId: evt-2001
header schema-version: 1
body: {"orderId":"ord-1001"}
~~~

Hãy chỉ ra phần nào dùng để **định tuyến**, phần nào mô tả **định dạng**, phần nào dùng để **truy vết**, và phần nào chứa **dữ liệu nghiệp vụ**. Nếu đổi routing key mà không thay body, event có thể đi đến queue khác không?

### Bài B — Khảo sát charset

Tạo payload có tên **“Nguyễn An”**, gửi theo UTF-8 và đọc lại bằng UTF-8. Sau đó cố ý giải mã như ISO-8859-1 trong môi trường thử nghiệm và so sánh chuỗi kết quả. Giải thích vì sao contentType application/json một mình chưa luôn đủ để ứng dụng bất kỳ giải mã đúng khi các hệ thống không tuân cùng quy ước.

### Bài C — Đổi converter

Thử hai cách:

1. **MessageBuilder + RabbitTemplate.send(...)**, listener nhận **Message** rồi đọc body.
2. **JSON MessageConverter + convertAndSend(object)**, listener nhận DTO.

Quan sát **contentType**, **contentEncoding**, body bytes và type headers thực tế. Đảm bảo hai cách sử dụng **hai queue thử nghiệm riêng** hoặc chạy lần lượt để không bị competing consumers che khuất kết quả.

### Bài D — Schema version và DLQ

Phát message có **schemaVersion=99** trong khi consumer chỉ hỗ trợ v1. Yêu cầu consumer phân loại đây là lỗi hợp đồng, đưa vào DLQ hoặc vùng cách ly có kiểm soát, gắn message ID vào log và không retry vô hạn. Sau đó thử thêm trường optional ở v1 để đánh giá tính tương thích.

## 12. Những điều cần nhớ

- **Body của RabbitMQ là byte[]**; contentType và contentEncoding là metadata giúp các phía diễn giải body.
- **Content type** mô tả loại dữ liệu như JSON, text hoặc binary; **content encoding** phải được hiểu theo quy ước rõ ràng về charset/biến đổi dữ liệu.
- **JSON + UTF-8 + schemaVersion** là điểm khởi đầu dễ tích hợp nhiều ngôn ngữ.
- **RabbitTemplate.send(Message)** phù hợp khi muốn kiểm soát bytes/properties trực tiếp; **convertAndSend(object)** phụ thuộc MessageConverter được cấu hình.
- **SimpleMessageConverter** không mặc nhiên biến mọi DTO thành JSON; khi dùng JSON converter cần đồng bộ cách xử lý ở producer và listener.
- **Headers kiểu Java** có thể hỗ trợ converter, nhưng hợp đồng liên dịch vụ nên dùng event/schema độc lập ngôn ngữ và tránh deserialize từ type metadata không tin cậy.
- Giải mã thành công mới là một phần của hệ thống tin cậy: còn phải kết hợp routing, publisher confirm/return, ACK, retry hữu hạn, dead-letter, idempotency và quan sát.

### Tài liệu tham khảo

- [Spring AMQP Reference — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): chuyển đổi message và các converter.
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/): RabbitTemplate, listener container, cấu hình và xử lý lỗi.
- [RabbitMQ — AMQP 0-9-1 Reference](https://www.rabbitmq.com/amqp-0-9-1-reference): properties và cách publish/consume message.
- [RFC 8259 — JSON](https://www.rfc-editor.org/rfc/rfc8259): cú pháp, Unicode và tính tương thích của JSON.
