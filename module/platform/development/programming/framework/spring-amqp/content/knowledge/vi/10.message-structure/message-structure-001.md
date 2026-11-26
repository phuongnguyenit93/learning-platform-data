# org.springframework.amqp.core.Message và MessageProperties

## Mục tiêu bài học

Trong **Spring AMQP**, producer thường dùng **RabbitTemplate** gửi message qua exchange, broker định tuyến theo routing key và binding đến queue, còn consumer xử lý bằng **@RabbitListener**. Để xây dựng hệ thống bất đồng bộ đáng tin cậy, chúng ta cần hiểu chính xác **message mang dữ liệu gì**, **metadata nằm ở đâu**, **metadata nào được broker bổ sung lúc giao nhận** và **thành phần nào chịu trách nhiệm chuyển đổi payload**.

Sau bài này, bạn có thể:

1. Phân biệt **org.springframework.amqp.core.Message**, **MessageProperties**, **org.springframework.messaging.Message** và message của RabbitMQ Java Client.
2. Tạo message từ **byte[] body** và **MessageProperties**, đọc content type, encoding, headers, messageId, correlationId, deliveryMode.
3. Phân biệt metadata do **producer cung cấp** với metadata Spring bổ sung khi **consumer nhận**.
4. Dùng **RabbitTemplate.send**, **convertAndSend** và **@RabbitListener** để làm việc với message thô hoặc payload đã chuyển đổi.
5. Thiết kế event envelope, kiểm soát lỗi giải mã, hỗ trợ retry, dead-letter và idempotency mà không nhầm header với bảo đảm giao nhận.

## 1. Message trong Spring AMQP là gì?

Hai lớp trung tâm của bài học nằm trong package **org.springframework.amqp.core**:

~~~java
org.springframework.amqp.core.Message
org.springframework.amqp.core.MessageProperties
~~~

**Message** biểu diễn một thông điệp AMQP có **hai phần chính**:

- **body:** dữ liệu thô kiểu **byte[]**; có thể chứa văn bản UTF-8, JSON, dữ liệu nhị phân hoặc định dạng khác.
- **messageProperties:** đối tượng **MessageProperties** lưu metadata của thông điệp như contentType, contentEncoding, messageId, correlationId, deliveryMode, headers và thông tin nhận message.

Spring AMQP cung cấp constructor cơ bản:

~~~java
Message(byte[] body, MessageProperties messageProperties)
~~~

Hình dung cấu trúc:

~~~mermaid
flowchart LR
    P["Producer / RabbitTemplate"] --> M
    subgraph M["Spring AMQP Message"]
        direction TB
        B["body: byte[]<br/>JSON / text / binary"]
        H["MessageProperties<br/>contentType, headers,<br/>messageId, correlationId, ..."]
    end
    M --> X["Exchange"]
    X -->|"Routing key + binding"| Q[("Queue")]
    Q --> L["@RabbitListener"]
~~~

**Message không có generic type**: đây không phải **Message&lt;OrderCreated&gt;**. Body của AMQP Message luôn được biểu diễn ở dạng byte array, còn việc biến JSON thành Java object là trách nhiệm của **MessageConverter** hoặc code giải mã do ứng dụng viết.

### Phân biệt các lớp có tên tương tự

| Kiểu dữ liệu | Thuộc thư viện | Đặc điểm | Khi dùng |
| --- | --- | --- | --- |
| **org.springframework.amqp.core.Message** | Spring AMQP | Chứa **byte[]** và **MessageProperties** | Làm việc trực tiếp với RabbitTemplate.send hoặc listener cần message thô |
| **org.springframework.amqp.core.MessageProperties** | Spring AMQP | Metadata cho một AMQP Message | Đọc/ghi content type, headers, định danh, trường giao nhận |
| **org.springframework.messaging.Message&lt;T&gt;** | Spring Messaging | Payload kiểu **T** và MessageHeaders | @RabbitListener hoặc tầng abstraction đã chuyển đổi |
| **com.rabbitmq.client.Delivery** | RabbitMQ Java Client | Envelope, properties và body của lần giao message | Dùng trực tiếp RabbitMQ Java Client thay vì wrapper Spring |

Không import nhầm **org.springframework.messaging.Message** khi muốn gọi **message.getBody()** kiểu byte array; kiểu Spring Messaging dùng **getPayload()**.

## 2. Body là byte[]: content type không tự giải mã dữ liệu

Một message JSON có thể chứa byte:

~~~json
{
  "eventId": "5b05ff4c-2e97-40fd-bd6e-63df8b7f073b",
  "eventType": "order.created",
  "schemaVersion": 1,
  "orderId": "ORD-1001",
  "occurredAt": "2026-11-26T02:00:00Z"
}
~~~

Ở tầng AMQP, JSON ở trên được mã hóa thành **byte[]**. **MessageProperties.contentType="application/json"** chỉ là thông tin mô tả cách hiểu body; RabbitMQ không tự parse JSON, kiểm tra schema hay biến nó thành Java object.

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;

String json = "{\"eventType\":\"order.created\",\"orderId\":\"ORD-1001\"}";

MessageProperties properties = new MessageProperties();
properties.setContentType(MessageProperties.CONTENT_TYPE_JSON);
properties.setContentEncoding(StandardCharsets.UTF_8.name());

Message message = new Message(
        json.getBytes(StandardCharsets.UTF_8),
        properties);

byte[] rawBody = message.getBody();
String decoded = new String(rawBody, StandardCharsets.UTF_8);

System.out.println(decoded);
System.out.println(message.getMessageProperties().getContentType());
~~~

**Giữ contentType khớp dữ liệu thực**:

| Body | Content type điển hình | Lưu ý |
| --- | --- | --- |
| Văn bản thuần | **text/plain** | Cần thống nhất charset; UTF-8 là lựa chọn phổ biến |
| JSON | **application/json** | Cần schema và parser/JSON converter phù hợp |
| XML | **application/xml** | Cần converter/parser XML phù hợp |
| Protobuf | **application/x-protobuf** hoặc loại đã thỏa thuận | Phải chia sẻ schema và version giữa producer/consumer |
| Binary tùy ý | **application/octet-stream** | Không cố giải mã thành String |

**contentEncoding** (ví dụ **UTF-8**) mô tả encoding; nó không phải cờ tự động nén dữ liệu. Nếu body được nén gzip, hai bên phải thống nhất format, header nhận diện và xử lý giải nén/giới hạn kích thước.

**Không suy luận rằng body là JSON chỉ vì header nói vậy.** Consumer vẫn cần parse, validate, kiểm tra schemaVersion và xử lý dữ liệu không hợp lệ.

## 3. MessageProperties gồm những nhóm metadata nào?

**MessageProperties** tập hợp phần lớn metadata mà code Spring AMQP thao tác. Một số thuộc tính tương ứng với trường trong **AMQP BasicProperties**; những thuộc tính khác là thông tin được Spring điền khi nhận và dispatch message.

### 3.1. Nhóm mô tả payload và định danh

| Thuộc tính / getter | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **contentType / getContentType()** | MIME type của body | **application/json** |
| **contentEncoding / getContentEncoding()** | Charset hoặc encoding theo hợp đồng | **UTF-8** |
| **contentLength / getContentLength()** | Metadata độ dài, nếu có | **128** |
| **messageId / getMessageId()** | ID do publisher/converter/ứng dụng gán | **event-1001** |
| **correlationId / getCorrelationId()** | Liên kết message với request/workflow | **checkout-2026-1001** |
| **type / getType()** | Chuỗi mô tả kiểu message theo hợp đồng | **order.created** |
| **timestamp / getTimestamp()** | Thời điểm được publisher gán nếu có | **Date** |
| **appId / getAppId()** | Dấu hiệu nguồn phát nếu được gán | **order-service** |
| **replyTo / getReplyTo()** | Địa chỉ hồi đáp cho mô hình request/reply | Tên queue hoặc địa chỉ reply-to |

**messageId và correlationId không tự được RabbitMQ bảo đảm tính duy nhất.** Nếu ứng dụng cần idempotency, producer phải sinh **eventId ổn định** và consumer phải thực sự lưu/so sánh ID đã xử lý. CorrelationId dùng cho liên kết các bước của cùng một workflow; không mặc nhiên là khóa duy nhất của từng event.

**contentLength không nên dùng thay cho message.getBody().length** khi xử lý body thực tế: nếu code tạo message thủ công, metadata độ dài có thể vắng hoặc không phản ánh dữ liệu đã thay đổi. Đo byte thực tế khi kiểm tra kích thước.

### 3.2. Nhóm điều khiển giao nhận

| Thuộc tính | Ý nghĩa | Giới hạn cần biết |
| --- | --- | --- |
| **deliveryMode** | PERSISTENT hoặc NON_PERSISTENT | Chỉ đặt persistent không tự bảo đảm message tồn tại qua mọi sự cố |
| **priority** | Độ ưu tiên message | Chỉ có ý nghĩa với loại queue và cấu hình hỗ trợ priority |
| **expiration** | TTL riêng của message, biểu diễn bằng chuỗi mili-giây theo AMQP 0.9.1 | Không thay thế queue TTL hoặc retry policy |
| **userId** | Thuộc tính AMQP user-id nếu được gửi | Broker có thể kiểm tra user-id theo ngữ cảnh; không coi là token xác thực nghiệp vụ |
| **headers** | Bảng key/value tùy chọn | Không phải mọi kiểu Java object đều chuyển đổi an toàn sang AMQP field table |

Ví dụ:

~~~java
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;

MessageProperties props = new MessageProperties();
props.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
props.setPriority(5);
props.setExpiration("60000"); // TTL per-message: 60.000 ms.
props.setMessageId("event-1001");
props.setCorrelationId("checkout-2026-1001");
props.setAppId("order-service");
props.setType("order.created");
~~~

**Các điều kiện phía broker vẫn quyết định kết quả**:

- Message persistent cần queue/topology phù hợp, publisher confirms và chính sách broker để đạt độ tin cậy cần thiết.
- Priority chỉ có tác dụng khi loại queue hỗ trợ và **x-max-priority** được cấu hình phù hợp (chẳng hạn classic priority queue); không đặt priority rồi mặc nhiên kỳ vọng mọi stream/quorum queue đổi thứ tự.
- Per-message **expiration="60000"** không phải “đợi 60 giây rồi tự retry”. Khi hết hạn, message có thể bị loại hoặc dead-letter nếu queue có DLX và điều kiện áp dụng; thứ tự và thời điểm thực tế tùy chính sách queue.
- Thay đổi metadata trên message đã publish **không thay đổi bản copy đang nằm trên RabbitMQ**; phải publish message mới nếu cần payload/properties mới.

### 3.3. Nhóm headers tùy biến

**MessageProperties.getHeaders()** cung cấp Map chứa các header ngoài nhóm AMQP properties chuẩn.

~~~java
MessageProperties props = new MessageProperties();
props.setHeader("eventType", "order.created");
props.setHeader("schemaVersion", 1);
props.setHeader("tenantScope", "retail");

String eventType = props.getHeader("eventType");
Object schemaVersion = props.getHeaders().get("schemaVersion");
~~~

Các trường trong headers phù hợp với dữ liệu nhỏ dùng để **định tuyến, tương thích schema, truy vết và hỗ trợ chính sách xử lý**. Không đưa toàn bộ object nghiệp vụ, token đăng nhập hoặc dữ liệu nhạy cảm vào headers.

Phân biệt:

- **props.setHeader("eventType", ...)** thêm header tùy biến vào AMQP message.
- **props.setContentType(...)** thiết lập thuộc tính MIME chuẩn của message.
- **rabbitTemplate.send(exchange, routingKey, message)** quyết định **đích publish**; routing key không tự lấy từ một custom header tên **routingKey**.
- **headers exchange** mới có thể dùng headers để match theo binding; direct/topic exchange thường dựa trên routing key.

Một số Spring converter thêm header phục vụ chuyển đổi type, ví dụ **__TypeId__** và các header liên quan. Chúng là **metadata của converter**, không phải sự thay thế cho trường **eventType** và **schemaVersion** trong hợp đồng nghiệp vụ.

## 4. Metadata nào xuất hiện khi consumer nhận message?

AMQP có **envelope của lần giao message**, bao gồm exchange/routing key và delivery tag. Spring gộp các thông tin quan sát được khi giao nhận vào **MessageProperties** của message nhận được, bên cạnh properties do publisher gửi.

| Getter khi nhận | Nó phản ánh gì? | Nên dùng để làm gì? |
| --- | --- | --- |
| **getReceivedExchange()** | Exchange nơi message đến trong lần giao nhận | Chẩn đoán định tuyến |
| **getReceivedRoutingKey()** | Routing key mà broker cung cấp cho delivery | Chẩn đoán hoặc xử lý nhiều loại event |
| **getConsumerQueue()** | Queue nơi consumer nhận message | Log và phân loại nguồn |
| **getConsumerTag()** | Consumer tag của lần subscribe | Chẩn đoán listener/consumer |
| **getDeliveryTag()** | Delivery tag của **channel nhận hiện tại** | Chỉ dùng cùng channel đó để ACK/NACK nếu manual ack |
| **isRedelivered()** | Cờ broker cho biết delivery có được đánh dấu gửi lại | Quan sát; không phải bằng chứng đầy đủ về trùng nghiệp vụ |
| **getReceivedDeliveryMode()** | Delivery mode được nhận từ wire | Phân biệt metadata inbound và thuộc tính dùng khi publish |

Những trường này thường **không được producer tự đặt** bằng cách gắn header tùy ý. Chúng mô tả **bối cảnh lần nhận**. Một message được dead-letter rồi đi qua exchange/queue khác có thể được giao dưới routing key và thông tin nhận khác lần trước.

### Vì sao deliveryTag không phải messageId?

**deliveryTag** chỉ có ý nghĩa **trong phạm vi một AMQP channel**, dùng cùng Channel khi xác nhận. Nếu mất kết nối hoặc message được giao lại, deliveryTag có thể thay đổi. Không dùng deliveryTag làm eventId, idempotency key hoặc correlationId.

**redelivered=true** chỉ cho biết RabbitMQ gắn cờ message được giao lại. Trùng nghiệp vụ còn có thể xuất phát từ **producer publish lại cùng event**, retry hoặc outbox gửi lặp; khi đó redelivered có thể là false. Chống trùng phải dựa vào **định danh nghiệp vụ ổn định**.

### Không trộn properties lúc publish với lúc nhận

~~~text
Producer tạo:
  body, contentType, contentEncoding, messageId,
  correlationId, deliveryMode, headers, ...

RabbitTemplate:
  basic.publish(exchange, routingKey, body + BasicProperties)

RabbitMQ:
  exchange định tuyến đến queue qua binding

Consumer nhận:
  body + properties từ publisher
  + receivedExchange + receivedRoutingKey
  + consumerQueue + consumerTag + deliveryTag + redelivered
~~~

Chữ **routing key** trong lời gọi publish là tham số của phương thức **send**, còn **receivedRoutingKey** là thông tin về lần giao nhận. Không giả định mọi trường trong MessageProperties đều là thuộc tính được gửi nguyên vẹn từ producer.

## 5. Ví dụ Spring AMQP: khai báo topology và gửi Message thủ công

Ví dụ này dùng **Spring Boot 3.x** và **spring-boot-starter-amqp**. Với các nhánh Spring Boot khác, kiểm tra dependency/starter tương ứng; logic lớp **Message** và **MessageProperties** vẫn là trọng tâm.

### 5.1. Dependency và topology

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderAmqpTopology {
    @Bean
    TopicExchange orderExchange() {
        return new TopicExchange("orders.events", true, false);
    }

    @Bean
    Queue auditOrderEventsQueue() {
        return QueueBuilder.durable("orders.events.audit").build();
    }

    @Bean
    Binding auditOrderBinding(Queue auditOrderEventsQueue,
                              TopicExchange orderExchange) {
        return BindingBuilder.bind(auditOrderEventsQueue)
                .to(orderExchange)
                .with("order.*");
    }
}
~~~

Queue này nhận **order.created**, **order.paid** và các routing key có hai thành phần tương tự. Binding **order.*** không tự khớp chuỗi nhiều cấp như **order.payment.completed**; cần dùng binding khác hoặc **order.#** nếu muốn khớp nhiều cấp. Để chạy, broker phải có RabbitMQ AMQP 0.9.1, tài khoản kết nối hợp lệ và **RabbitAdmin**/provisioning khai báo topology.

### 5.2. Producer chủ động tạo cả body và MessageProperties

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.UUID;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishOrderCreated(
            String orderId, String correlationId) {
        String eventId = UUID.randomUUID().toString();
        String json = "{\"eventId\":\"" + eventId
                + "\",\"eventType\":\"order.created\""
                + ",\"schemaVersion\":1"
                + ",\"orderId\":\"" + orderId + "\"}";

        MessageProperties props = new MessageProperties();
        props.setContentType(MessageProperties.CONTENT_TYPE_JSON);
        props.setContentEncoding(StandardCharsets.UTF_8.name());
        props.setMessageId(eventId);
        props.setCorrelationId(correlationId);
        props.setType("order.created");
        props.setTimestamp(new Date());
        props.setAppId("order-service");
        props.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        props.setHeader("eventType", "order.created");
        props.setHeader("schemaVersion", 1);

        Message message = new Message(
                json.getBytes(StandardCharsets.UTF_8), props);

        rabbitTemplate.send(
                "orders.events", "order.created", message);
    }
}
~~~

Trong ví dụ minh họa này, **orderId** nên được validate/serialize bằng JSON library ở ứng dụng thực, thay vì ghép chuỗi JSON; đoạn code chỉ nhằm cho thấy **new Message(body, props)**. Dữ liệu orderId chứa dấu nháy kép hay ký tự đặc biệt sẽ cần JSON serialization đúng chuẩn.

**RabbitTemplate.send** nhận **Message đã được tạo sẵn**; nó không cần suy đoán payload Java cần chuyển thành byte như thế nào. Bên gửi có toàn quyền đặt contentType, messageId và headers trong phạm vi AMQP cho phép.

**Không đồng nhất việc send() trả về với thành công end-to-end.** Để producer biết broker đã nhận publish cần **publisher confirms**, và để phát hiện message không route tới queue cần **mandatory + returns** hoặc cơ chế tương ứng. Queue durable và message persistent cũng không thể tự thay thế thiết kế retry/outbox.

### 5.3. Consumer đọc Message thô

~~~java
import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class AuditOrderListener {
    private static final Logger log =
            LoggerFactory.getLogger(AuditOrderListener.class);

    @RabbitListener(queues = "orders.events.audit")
    public void onEvent(Message message) {
        MessageProperties props = message.getMessageProperties();

        String json = new String(
                message.getBody(), StandardCharsets.UTF_8);

        log.info("eventId={}, type={}, route={}, queue={}",
                props.getMessageId(),
                props.getHeader("eventType"),
                props.getReceivedRoutingKey(),
                props.getConsumerQueue());

        // Thực tế: parse JSON, kiểm tra schema và ghi audit vào DB
        // với cơ chế idempotency theo eventId.
        log.debug("Payload size={} bytes", message.getBody().length);
    }
}
~~~

Ở đây listener nhận **org.springframework.amqp.core.Message** để có cả body và properties. Nếu chỉ cần nội dung nghiệp vụ dạng DTO, hãy dùng **MessageConverter** rồi nhận payload đã giải mã thay vì mọi listener tự parse byte[].

**Không log nguyên body khi có dữ liệu nhạy cảm.** Ví dụ chỉ log ID, type, routing key và kích thước. Khi phải lưu raw message để chẩn đoán, cần giới hạn truy cập, thời gian lưu và cơ chế che dữ liệu nhạy cảm.

## 6. send() và convertAndSend() khác nhau thế nào?

Hai API của **RabbitTemplate** dùng cùng hạ tầng AMQP nhưng chia trách nhiệm khác nhau:

| API | Đầu vào | Ai tạo byte[] và MessageProperties? | Phù hợp |
| --- | --- | --- | --- |
| **send(exchange, key, Message)** | AMQP Message thô | **Ứng dụng tự tạo** | Cần kiểm soát chính xác payload và metadata |
| **convertAndSend(exchange, key, Object)** | Đối tượng Java | **MessageConverter** | Payload đơn giản hoặc DTO với converter phù hợp |
| **convertAndSend(..., MessagePostProcessor)** | Đối tượng Java + callback chỉnh Message | Converter tạo Message, post-processor điều chỉnh trước publish | Muốn thêm headers/messageId sau khi convert |
| **receive(queueName)** | Tên queue | Trả về **AMQP Message thô** | Đọc body và metadata từ queue |
| **receiveAndConvert(queueName)** | Tên queue | **MessageConverter** chuyển Message thành Java object | Cần dữ liệu đã được giải mã |

### 6.1. MessagePostProcessor để thêm metadata

~~~java
import java.util.UUID;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

String eventId = UUID.randomUUID().toString();
String text = "Order ORD-1001 has been created";

rabbitTemplate.convertAndSend(
        "orders.events",
        "order.created",
        text,
        message -> {
            MessageProperties props = message.getMessageProperties();
            props.setMessageId(eventId);
            props.setCorrelationId("checkout-1001");
            props.setHeader("eventType", "order.created");
            props.setHeader("schemaVersion", 1);
            return message;
        });
~~~

Với **SimpleMessageConverter** mặc định, đầu vào String thường được mã hóa theo charset đã cấu hình và được gắn content type dạng text, nên listener nhận **String** có thể hoạt động trực tiếp.

**MessagePostProcessor** có thể sửa Message do converter tạo, nhưng không biến JSON string thành Java DTO và cũng không chứng minh message đã được gửi thành công. Nếu muốn đổi kiểu body cần thực sự convert lại dữ liệu.

### 6.2. MessageConverter và lựa chọn format

Spring AMQP có interface:

~~~java
public interface MessageConverter {
    Message toMessage(Object object, MessageProperties messageProperties);
    Object fromMessage(Message message);
}
~~~

**SimpleMessageConverter** là converter thường được RabbitTemplate dùng mặc định nếu không cấu hình loại khác:

- **String:** chuyển sang byte array, đặt content type phù hợp với text.
- **byte[]:** giữ dạng binary.
- **Serializable:** có hỗ trợ Java serialization theo chính sách an toàn được cấu hình, nhưng không nên chọn Java native serialization làm hợp đồng liên dịch vụ.
- Khi nhận, converter dựa vào content type và encoding để quyết định trả **String**, **byte[]** hoặc object khác.

Với hệ thống nhiều service, **JSON converter** thường phù hợp hơn cho DTO và schema độc lập với implementation Java. Tên converter phụ thuộc nhánh Spring AMQP:

| Nhánh thư viện | JSON converter thường dùng | Ghi chú |
| --- | --- | --- |
| **Spring AMQP 3.x** | **Jackson2JsonMessageConverter** | Dựa trên Jackson 2 |
| **Spring AMQP 4.x** | **JacksonJsonMessageConverter** | Dựa trên Jackson 3; kiểm tra cấu hình và API đúng nhánh |

Ví dụ cấu hình minh họa với **Spring AMQP 3.x**:

~~~java
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JsonMessageConfig {
    @Bean
    MessageConverter jsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }
}
~~~

Khi dùng JSON converter, đảm bảo producer và consumer thống nhất converter, expected payload type, Content-Type, các class/record có thể giải mã và quy tắc evolution của schema. Với **@RabbitListener** nhận DTO, converter của listener container cũng phải đúng; một bean converter ở context **không bảo đảm mọi custom listener factory tự dùng đúng converter** nếu factory được tạo thủ công. Nên kiểm tra cấu hình của RabbitTemplate và RabbitListenerContainerFactory.

### 6.3. Vì sao chỉ đổi contentType chưa đủ?

Giả sử producer gọi **convertAndSend(String json)** với SimpleMessageConverter rồi dùng post-processor đổi **contentType** thành **application/json**. Body vẫn là **byte[] chứa JSON text**. Phía nhận với SimpleMessageConverter, contentType không phải text có thể khiến payload sau conversion là **byte[]**, nên listener khai báo **String** có thể không xử lý như mong muốn.

Vì vậy cần chọn một trong hai đường rõ ràng:

1. **Raw message:** tạo body JSON bằng serializer, đặt application/json, listener nhận **Message** và parse có kiểm soát.
2. **Typed message:** dùng JSON MessageConverter ở cả hai phía và listener nhận DTO đúng contract.

Không được coi **contentType** là thao tác biến đổi dữ liệu.

## 7. @RabbitListener có thể nhận những gì từ Message?

Một method **@RabbitListener** có thể nhận **Message**, **MessageProperties**, **com.rabbitmq.client.Channel**, **@Header**, **@Headers** hoặc payload đã được converter giải mã.

~~~java
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class OrderHeaderListener {

    @RabbitListener(queues = "orders.events.audit")
    public void inspect(Message message,
                        MessageProperties properties,
                        @Header("eventType") String eventType) {
        System.out.println(eventType);
        System.out.println(properties.getMessageId());
        System.out.println(message.getBody().length);
    }
}
~~~

Trong một ứng dụng, chọn **một listener chính** để thực hiện tác động nghiệp vụ trên queue đó. Nếu đồng thời bật **AuditOrderListener** ở mục 5.3 và **OrderHeaderListener** ở đây trên cùng queue, chúng trở thành **competing consumers**: mỗi message được giao cho một consumer, không mặc nhiên cho cả hai. Dùng queue khác nếu mỗi chức năng phải nhận một bản sao sự kiện.

Để nhận **@Header**, phải chắc chắn header tồn tại hoặc khai báo tùy chọn mặc định/required=false khi hệ thống có nhiều phiên bản producer. Ví dụ **@Header("eventType")** sẽ không tự sinh giá trị eventType từ routing key.

**org.springframework.messaging.Message&lt;T&gt;** là abstraction khác, có thể được Spring AMQP dựng sau conversion; trong trường hợp đó dùng **getPayload()** và **getHeaders()** theo Spring Messaging. Không trộn hai kiểu trong cùng một ví dụ mà không nêu rõ.

## 8. MessageProperties trong ACK/NACK và redelivery

Để hiểu vòng đời message, hãy phân biệt ba lớp xác nhận:

| Hoạt động | Ai xác nhận cho ai? | Metadata liên quan |
| --- | --- | --- |
| **Publisher confirm** | Broker phản hồi publisher | Channel publish/confirm sequence, callback của producer |
| **Consumer ACK/NACK** | Consumer phản hồi broker về một delivery | **deliveryTag trên channel nhận** |
| **Hoàn tất nghiệp vụ** | Ứng dụng xác nhận đã commit tác động ở DB/hệ thống ngoài | **eventId**, trạng thái transaction, idempotency record |

**MessageProperties.getDeliveryTag()** chỉ hữu ích khi callback đang xử lý message nhận qua channel. Không dùng deliveryTag của lần nhận cũ để ACK trên connection/channel mới.

### Ví dụ manual acknowledgement

Nếu listener factory được cấu hình **AcknowledgeMode.MANUAL**, listener có thể tự ACK khi nghiệp vụ đã xử lý:

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class ManualAckAuditListener {

    @RabbitListener(
            queues = "orders.events.audit",
            containerFactory = "manualAckFactory")
    public void onMessage(Message message, Channel channel)
            throws IOException {
        long tag = message.getMessageProperties().getDeliveryTag();

        try {
            processAndCommitAudit(message);
            channel.basicAck(tag, false);
        } catch (RuntimeException ex) {
            // Không requeue vô hạn. Cần cấu hình DLX/quy trình lỗi.
            channel.basicNack(tag, false, false);
        }
    }

    private void processAndCommitAudit(Message message) {
        // Thay bằng kiểm tra schema + ghi DB có idempotency.
    }
}
~~~

**Đây là ví dụ minh họa manual ack, không được bật song song với các listener ví dụ khác trên cùng queue nếu muốn quan sát một xử lý duy nhất.** Phải thực sự cấu hình bean **manualAckFactory** ở chế độ MANUAL trước khi chạy. **basicNack(tag, false, false)** báo broker không requeue; message chỉ được dead-letter nếu queue có DLX và điều kiện phù hợp, nếu không có thể bị loại. Với lỗi tạm thời, thiết kế retry/backoff riêng; đừng chọn requeue vô hạn gây vòng lặp nóng.

Trong **AcknowledgeMode.AUTO** của Spring listener container, thường không cần code tự gọi basicAck: container ACK khi handler hoàn tất thành công; khi handler ném exception, cách reject/requeue phụ thuộc error handling. **AUTO không phải broker ACK trước khi code nghiệp vụ chạy**.

### redelivered không đủ để chống trùng

~~~text
T0: Consumer nhận event E, deliveryTag = 15
T1: Consumer ghi DB thành công
T2: Connection mất trước khi broker nhận ACK
T3: Broker giao lại E, deliveryTag mới có thể = 1 trên channel mới
T4: Consumer phải nhận ra eventId của E đã xử lý
~~~

Message bị giao lại có thể mang cờ **redelivered**, nhưng publisher cũng có thể publish cùng event hai lần với cờ này false. **Idempotency phải dựa trên eventId nghiệp vụ**, không dựa duy nhất vào redelivered hay deliveryTag.

## 9. Thiết kế hợp đồng thông điệp có thể tiến hóa

Trong hệ thống nhiều service, cấu trúc dữ liệu phải ổn định theo thời gian và có quy tắc nâng cấp version. Ví dụ payload:

~~~json
{
  "eventId": "e9bd609d-4da6-49d7-b585-a7753499b2c2",
  "eventType": "order.created",
  "schemaVersion": 2,
  "occurredAt": "2026-11-26T02:00:00Z",
  "aggregateId": "ORD-1001",
  "aggregateVersion": 3,
  "data": {
    "orderId": "ORD-1001",
    "totalAmount": 150000,
    "currency": "VND"
  }
}
~~~

Có thể song song gắn metadata:

~~~text
contentType:   application/json
contentEncoding: UTF-8
messageId:     e9bd609d-4da6-49d7-b585-a7753499b2c2
correlationId: checkout-session-46
type:          order.created
headers:
  eventType:     order.created
  schemaVersion: 2
~~~

Một số thông tin xuất hiện cả trong body và metadata là **có chủ đích**: header giúp định tuyến/quan sát nhanh, body giữ **hợp đồng nghiệp vụ tự chứa** cho lưu trữ, replay hoặc chuyển broker. Tuy vậy, việc lặp lại thông tin phải nhất quán; nếu **schemaVersion trong header khác body**, consumer cần chính sách từ chối hoặc phát hiện sai lệch.

| Trường | Đặt ở đâu? | Lý do |
| --- | --- | --- |
| **eventId** | Trong body; có thể gắn messageId tương ứng | Là khóa idempotency bền vững khi republish |
| **eventType** | Trong body; có thể lặp ở header/type | Cho phép dispatch và quan sát |
| **schemaVersion** | Trong body; có thể lặp ở header | Xử lý tương thích định dạng |
| **occurredAt** | Trong body | Thời điểm nghiệp vụ xảy ra; khác lúc broker nhận |
| **aggregateVersion** | Trong body nếu nghiệp vụ cần thứ tự | Kiểm tra event đến muộn hoặc sai thứ tự |
| **correlationId** | Property/header và log/tracing | Nối nhiều bước của một workflow |
| **deliveryTag** | Chỉ có trong metadata của lần nhận | ACK/NACK; không đưa vào event envelope |

### Quy tắc tiến hóa schema

1. **Phân biệt trường bắt buộc và tùy chọn.** Đặt default rõ ràng cho consumer cũ khi thêm trường mới.
2. **Không tự ý đổi ý nghĩa của trường cũ.** Nếu đơn vị đổi từ đồng sang xu hoặc tên trạng thái khác nghĩa, cần version schema và bước migration.
3. **Consumer phải xử lý schema không hỗ trợ.** Log định danh, đưa vào luồng lỗi có kiểm soát và cảnh báo; không retry vô hạn.
4. **Không phụ thuộc vào tên Java class trong message xuyên dịch vụ.** Dùng eventType/schemaVersion theo hợp đồng đa ngôn ngữ, tránh ràng buộc với header **__TypeId__** của converter.
5. **Kiểm soát kích thước body/headers.** Message quá lớn làm tăng sử dụng bộ nhớ, network và nguy cơ trễ/timeout ở listener.

## 10. Headers khi retry, dead-letter và quan sát

Khi một message bị reject/nack hoặc hết hạn trong queue được cấu hình dead-letter phù hợp, RabbitMQ có thể gửi message tới **dead-letter exchange (DLX)**. Lần giao nhận sau có thể kèm metadata/header về lịch sử chết, thường được quan sát qua **x-death**.

| Thông tin | Mục đích | Điều không nên suy luận |
| --- | --- | --- |
| **x-death** | Ghi lịch sử dead-letter theo nhóm lý do/queue | Không phải luôn có, không phải cơ chế tính retry duy nhất |
| **receivedExchange/receivedRoutingKey** | Cho biết delivery hiện tại đến từ đâu | Không nhất thiết là exchange/routing ban đầu nếu đã DLX |
| **eventId/messageId** | Truy vết và chống trùng | RabbitMQ không tự bảo đảm ID được publisher gán |
| **correlationId** | Nối luồng xử lý giữa các service | Không tự báo transaction thành công |
| **redelivered** | Phát hiện dấu hiệu broker giao lại | Không bao quát publisher gửi trùng |

**Không dựa vào việc tăng một header retryCount là đủ để có retry có giới hạn.** Header chỉ ghi thông tin; cần thành phần **đọc, cập nhật và thực thi** chính sách retry, backoff, số lần tối đa, kênh lỗi và giám sát. Nếu lỗi không thể phục hồi (invalid JSON, schema chưa hỗ trợ), nên cách ly message thay vì thử lại vô hạn.

### Quan sát message trong môi trường thật

Khi log hoặc trace:

- Ghi **eventId, eventType, schemaVersion, correlationId**, tên queue và routing key khi phù hợp.
- Ghi thời gian xử lý, kết quả ACK/NACK, số lần retry, DLQ và trạng thái transaction nghiệp vụ.
- Không log toàn bộ body nếu có thông tin khách hàng, token, số tài khoản hoặc nội dung nhạy cảm.
- Không tin dữ liệu trong header/body là đã được xác thực chỉ vì đến từ RabbitMQ; kiểm soát quyền publisher, vhost, TLS và validate payload.

**MessageProperties có thể thay đổi trong bộ nhớ Java**, nhưng việc log/chỉnh object nhận được không thay đổi bản tin đã lưu trên broker. Muốn phát một phiên bản message mới cần publish lại với body/properties mong muốn và chiến lược idempotency đúng.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Listener nhận **byte[]** thay vì String | Content type không tương thích với SimpleMessageConverter | Đồng bộ contentType/encoding và converter; hoặc nhận raw Message rồi parse |
| **MessageConversionException** | Body không đúng format/schema hoặc converter không khớp | Validate JSON, cấu hình converter, xử lý lỗi có giới hạn |
| **@Header("eventType")** thiếu giá trị | Producer không gửi custom header | Thống nhất contract hoặc khai báo header không bắt buộc |
| Không lấy được routing key bằng **getHeader("routingKey")** | Routing key là tham số publish/delivery envelope | Dùng **getReceivedRoutingKey()** trên message nhận |
| JSON lỗi khi orderId có dấu nháy kép | Ghép chuỗi JSON thủ công | Dùng JSON serializer, validate |
| messageId luôn null | Producer không gán | Sinh **eventId** ổn định rồi gán **messageId** nếu cần |
| Dùng deliveryTag làm khóa chống trùng | DeliveryTag chỉ có ý nghĩa trong một channel | Dùng eventId và dữ liệu idempotency |
| Message persistent nhưng vẫn mất | Chưa có queue/topology/publisher confirm phù hợp hoặc sự cố vượt chính sách độ bền | Dùng queue durable, confirms, returns, retry/outbox |
| NACK không đưa được message vào DLQ | Queue chưa cấu hình DLX/binding tương ứng | Kiểm tra topology dead-letter và reject/requeue semantics |
| Xử lý event bị lặp sau sự cố | ACK chưa đến broker hoặc producer publish lại | Idempotent consumer, outbox và kiểm tra eventId |

### Quy trình chẩn đoán ngắn

1. Xác định đang làm việc với **AMQP Message thô** hay **Spring Messaging Message đã convert**.
2. Xem **body bytes**, **contentType**, **contentEncoding** và **MessageConverter** đang áp dụng.
3. Kiểm tra các trường **messageId, correlationId, headers** producer thực sự gán.
4. Ở consumer, kiểm tra **receivedRoutingKey, consumerQueue, deliveryTag** thay vì suy luận từ custom header.
5. Phân loại lỗi **publish/routing**, **convert**, **nghiệp vụ**, **ACK/NACK** hoặc **retry/DLX** để xử lý đúng tầng.

## 12. Bài tập thực hành

### Bài 1 — Tạo và đọc Message

Tạo JSON string cho event **OrderCreated**, convert UTF-8 thành byte[], tạo MessageProperties với **application/json**, messageId, correlationId và hai custom headers. Tạo **new Message(body, props)** rồi in **getBody().length**, **getContentType()**, **getHeaders()**. Giải thích vì sao Message không phải **Message&lt;OrderCreated&gt;**.

### Bài 2 — So sánh send và convertAndSend

Publish cùng một nội dung theo hai cách: **RabbitTemplate.send** với Message tự tạo và **RabbitTemplate.convertAndSend(String)**. Cho consumer nhận raw Message và so sánh **contentType**, headers, messageId và body. Dùng MessagePostProcessor gắn custom header cho convertAndSend.

### Bài 3 — Metadata publish so với receive

Publish vào topic exchange **orders.events** với routing key **order.created**, bind queue **orders.events.audit**. Trong listener, in **receivedExchange**, **receivedRoutingKey**, **consumerQueue** và **deliveryTag**. Tại sao các trường này không nên được producer gắn bằng custom header?

### Bài 4 — Kiểm chứng giải mã

Gửi cùng chuỗi JSON nhưng lần đầu để contentType **text/plain**, lần sau **application/json**, sử dụng SimpleMessageConverter. Quan sát **receiveAndConvert** hoặc listener với converter tương ứng. Thiết kế lại để hai phía dùng JSON converter và nhận DTO theo schema ổn định.

### Bài 5 — Crash trước khi ACK

Thiết kế consumer ghi eventId vào bảng **processed_events** có unique constraint cùng transaction với việc ghi audit. Giả lập database commit thành công rồi process crash trước ACK. Cho message được giao lại và chứng minh không tạo dữ liệu audit trùng.

### Bài 6 — Xử lý schema version sai

Publish event có **schemaVersion=999** nhưng consumer chỉ hiểu 1 và 2. Thiết kế cách từ chối có kiểm soát, log eventId/correlationId, ghi lỗi và đưa message tới DLQ nếu được cấu hình. Giải thích vì sao retry vô hạn không giải quyết payload không tương thích.

### Câu hỏi tự đánh giá

1. **Message** của Spring AMQP có mấy thành phần cốt lõi? Body có kiểu dữ liệu gì?
2. **contentType** và **contentEncoding** khác nhau thế nào? Chúng có tự biến body thành DTO không?
3. Sự khác nhau giữa **messageId**, **correlationId** và **deliveryTag**?
4. **getReceivedRoutingKey()** khác custom header tên **routingKey** ở điểm nào?
5. Khi nào dùng **send**, khi nào dùng **convertAndSend** và **MessagePostProcessor**?
6. Vì sao thiết lập deliveryMode **PERSISTENT** không đủ bảo đảm end-to-end?
7. **redelivered=false** có chứng minh event chưa từng được xử lý hay chưa?
8. Nếu một event phải replay sau nhiều tháng, nên lưu eventType và schemaVersion ở đâu để contract vẫn dễ hiểu?

## 13. Tài liệu tham khảo chính thức

- [Spring AMQP API — Message](https://docs.spring.io/spring-amqp/api/org/springframework/amqp/core/Message.html): constructor, body và MessageProperties.
- [Spring AMQP API — MessageProperties](https://docs.spring.io/spring-amqp/api/org/springframework/amqp/core/MessageProperties.html): content type, headers, delivery metadata, messageId và correlationId.
- [Spring AMQP — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): SimpleMessageConverter, JSON converter, chuyển đổi chiều gửi/nhận và chú ý an toàn.
- [Spring AMQP — Annotated Endpoint Method Signature](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable-signature.html): @RabbitListener nhận raw Message, MessageProperties, Channel, @Header và payload.
- [Spring AMQP — Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/confirms.html): giới hạn của send và cơ chế xác nhận publish.
- [RabbitMQ — AMQP 0.9.1 Concepts](https://www.rabbitmq.com/tutorials/amqp-concepts): message, exchange, queue, binding, routing key và delivery.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ACK/NACK theo channel và publisher confirms.

---

**Ghi nhớ:** **org.springframework.amqp.core.Message = byte[] body + MessageProperties**. Body mang dữ liệu; properties mang contentType, encoding, headers, định danh và metadata giao nhận. **RabbitTemplate.send** gửi Message có sẵn, **convertAndSend** dùng MessageConverter, **@RabbitListener** có thể nhận raw Message hoặc payload đã convert. **DeliveryTag thuộc một channel**, còn **eventId/messageId** giúp theo dõi nghiệp vụ; tự đặt headers hoặc deliveryMode **không thay thế** publisher confirms, ACK/NACK, retry, dead-letter và idempotency.
