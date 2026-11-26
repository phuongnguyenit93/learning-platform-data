# messageId, correlationId, timestamp, type và appId

## 1. Vì sao metadata của message quan trọng?

Khi xây hệ thống xử lý bất đồng bộ bằng **Spring AMQP** và RabbitMQ, nội dung thông điệp (*payload*) cho biết **cần xử lý dữ liệu gì**, còn các thuộc tính của message giúp trả lời **đây là thông điệp nào, liên quan đến luồng nào, được tạo lúc nào, thuộc loại nghiệp vụ gì và do ứng dụng nào phát**.

Giả sử hệ thống thương mại điện tử phát sự kiện tạo đơn hàng. Payload tối giản có thể là:

~~~json
{
  "orderId": "ORD-1001",
  "amount": 250000,
  "currency": "VND"
}
~~~

Nếu consumer chỉ nhìn payload, rất khó điều tra một bản ghi bị xử lý trùng sau retry hoặc tìm tất cả các sự kiện thuộc cùng phiên đặt hàng. Producer có thể bổ sung các **AMQP message properties**:

~~~text
messageId     = "evt-8edb2a"
correlationId = "checkout-6e42"
timestamp     = "2026-11-26T02:00:00Z"    (minh họa khi hiển thị)
type          = "order.created.v1"
appId         = "order-service"

body          = {"orderId":"ORD-1001","amount":250000,"currency":"VND"}
~~~

Đây là năm thuộc tính tiêu chuẩn của thông điệp trong **AMQP 0-9-1**. Với Spring AMQP, lớp thường dùng để thao tác là `org.springframework.amqp.core.MessageProperties`. RabbitMQ có thể chuyển tiếp những thuộc tính này cùng body qua exchange, binding và queue để `@RabbitListener` đọc được. Tuy nhiên, broker **không tự đảm bảo giá trị của năm trường là duy nhất, đúng thời gian hay đáng tin như chứng thực danh tính**.

Bài này thuộc chương **Cấu trúc thông điệp**, tập trung vào năm thuộc tính nói trên, cách thiết lập bằng `RabbitTemplate`, cách đọc và ứng dụng chúng cho tracing, xác nhận giao nhận, retry, dead-letter và idempotency.

## 2. Cấu trúc thông điệp trong Spring AMQP

Spring AMQP thể hiện một message theo hai phần chính:

~~~java
org.springframework.amqp.core.Message
    |
    +-- byte[] body
    |
    +-- MessageProperties messageProperties
           +-- messageId
           +-- correlationId
           +-- timestamp
           +-- type
           +-- appId
           +-- contentType, contentEncoding, deliveryMode, ...
           +-- headers (Map<String, Object>)
~~~

`Message#getBody()` trả về bytes của payload; `Message#getMessageProperties()` trả về metadata. Khi gọi `RabbitTemplate.convertAndSend(...)`, một `MessageConverter` chuyển object Java thành body và thiết lập một số thuộc tính liên quan đến mã hóa. `MessagePostProcessor` có thể bổ sung hoặc điều chỉnh các properties trước khi publish.

### 2.1. Bảng đối chiếu năm trường

| AMQP 0-9-1 property | Spring `MessageProperties` | Loại/ý nghĩa | Ví dụ | Dùng để |
| --- | --- | --- | --- | --- |
| `message-id` | `setMessageId(String)` / `getMessageId()` | ID do ứng dụng đặt cho message hoặc sự kiện | `evt-8edb2a` | Đối soát, nhận diện trùng lặp |
| `correlation-id` | `setCorrelationId(String)` / `getCorrelationId()` | ID nối các message trong một request/workflow | `checkout-6e42` | Ghép request/reply, liên kết log |
| `timestamp` | `setTimestamp(Date)` / `getTimestamp()` | Thời gian do publisher cung cấp | `2026-11-26T02:00:00Z` | Quan sát độ trễ, phân tích sự kiện |
| `type` | `setType(String)` / `getType()` | Nhãn loại message ở cấp ứng dụng | `order.created.v1` | Nhận diện loại sự kiện và contract |
| `app-id` | `setAppId(String)` / `getAppId()` | Tên/ID ứng dụng phát message | `order-service` | Đối soát nguồn phát, logging |

Cả năm trường đều là **metadata tùy chọn**: RabbitMQ không tự điền một UUID vào `messageId` hoặc tự gán `correlationId` theo workflow của doanh nghiệp. Khi cần sử dụng chúng để vận hành đáng tin cậy, hệ thống cần có **quy ước và cơ chế kiểm tra ở producer/consumer**.

### 2.2. Đừng nhầm properties, headers và delivery metadata

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **Standard message properties** | `messageId`, `correlationId`, `timestamp`, `type`, `appId` | Các field có định nghĩa sẵn trong AMQP 0-9-1. |
| **Application headers** | `traceparent`, `tenantId`, `schemaVersion` | Key/value do ứng dụng hoặc thư viện đặt trong bảng headers. |
| **Routing metadata** | Exchange, routing key, binding | Broker dùng để quyết định message đến queue nào. |
| **Delivery metadata** | Delivery tag, redelivered flag, received routing key | Thông tin về một lần giao message cho consumer. |
| **Transport outcome** | Publisher confirm ACK/NACK, consumer ACK/NACK | Tín hiệu xác nhận publish và delivery, không phải năm properties trên. |

Ví dụ: `messageId="evt-8edb2a"` vẫn là một chuỗi ID ngay cả khi cùng message được **redeliver** nhiều lần. Nhưng **delivery tag** là giá trị gắn với một lần delivery trên channel, được broker tạo ra để consumer ACK; nó không thể thay thế `messageId` trong cơ chế chống xử lý trùng.

## 3. messageId: định danh một thông điệp hoặc sự kiện

### 3.1. Cách sử dụng

`messageId` thường là một chuỗi được producer tạo khi hình thành message, chẳng hạn UUID, ULID hoặc ID sự kiện đã lưu trong database. Nếu mục tiêu là **idempotency**, một quy ước hữu ích là:

> **Cùng một sự kiện nghiệp vụ được publish lại do retry phải giữ cùng event ID ổn định; consumer có thể dùng ID đó để nhận biết sự kiện đã xử lý.**

Ví dụ:

~~~text
Tạo event OrderCreated:
  messageId = evt-1001
  orderId   = ORD-1001

Lần publish thứ nhất:
  network timeout trước khi producer nhận confirm.

Producer retry cùng event:
  messageId = evt-1001 (giữ nguyên).

Consumer nhận hai delivery cùng messageId:
  lần đầu ghi nghiệp vụ;
  lần sau phát hiện evt-1001 đã xử lý và bỏ qua side effect trùng.
~~~

Nếu producer tạo UUID mới **mỗi lần retry cùng sự kiện**, consumer khó phát hiện hai lần giao thực chất là cùng một thao tác nghiệp vụ. Có thể lưu `eventId` trong payload hoặc outbox rồi dùng chính giá trị đó làm `messageId`.

### 3.2. Những gì messageId không bảo đảm

- RabbitMQ **không kiểm tra tính duy nhất** của `messageId`. Hai message khác nội dung có thể có cùng ID nếu producer tạo sai.
- RabbitMQ **không tự lọc trùng** chỉ vì các message có cùng `messageId`.
- `messageId` **không phải delivery tag** và không dùng để gọi `basicAck(...)`.
- `messageId` **không phải chứng cứ xác thực** rằng message đến từ hệ thống tin cậy.

Để chống trùng trong nghiệp vụ, một cách phổ biến là bảng `processed_events` có khóa duy nhất như `(consumer_name, message_id)`. Hãy cập nhật dấu đã xử lý **trong cùng transaction database** với thay đổi nghiệp vụ khi khả thi. Nếu transaction thất bại, dấu xử lý cũng cần rollback để cho phép thực hiện lại an toàn.

### 3.3. Nên tạo ID vào lúc nào?

Tạo `messageId` **khi sinh sự kiện**, trước các lần thử publish. Với outbox, ID được lưu cùng bản ghi outbox; publisher đọc lại ID này khi retry. Mỗi sự kiện nghiệp vụ mới nhận ID mới, dù thuộc cùng đơn hàng. Không dùng `orderId` đơn thuần làm message ID nếu một đơn hàng có thể sinh nhiều sự kiện `OrderCreated`, `OrderPaid` hoặc `OrderCancelled` cần phân biệt.

## 4. correlationId: nối các message thuộc một luồng

### 4.1. Không đồng nhất correlationId và messageId

Một phiên checkout có thể sinh nhiều sự kiện:

~~~mermaid
flowchart LR
    R["Checkout request<br/>correlationId=checkout-42"]
    O["OrderCreated<br/>messageId=evt-01<br/>correlationId=checkout-42"]
    P["PaymentRequested<br/>messageId=evt-02<br/>correlationId=checkout-42"]
    N["NotificationSent<br/>messageId=evt-03<br/>correlationId=checkout-42"]
    R --> O --> P --> N
~~~

Ba sự kiện có **`messageId` khác nhau** vì là ba message khác nhau, nhưng cùng **`correlationId`** để liên kết chúng về một workflow. Khi xem log phân tán, có thể tìm theo `checkout-42` để thấy toàn bộ chuỗi xử lý.

| Câu hỏi | Dùng trường |
| --- | --- |
| Đây có phải cùng một sự kiện đã được nhận trước đó? | `messageId` / event ID |
| Những message nào thuộc cùng yêu cầu checkout? | `correlationId` |
| Request này đang chờ reply nào? | `correlationId`, phối hợp `replyTo` khi dùng request/reply |
| Message được broker giao cho consumer lần thứ mấy? | Không suy ra chỉ từ hai trường trên; xem redelivery/retry metadata và hệ thống quan sát |

### 4.2. Trong RPC / request-reply

Với kiểu request/reply trên RabbitMQ:

1. Client publish request, kèm `replyTo` (đích gửi trả) và `correlationId` để nhận diện request đang chờ.
2. Service xử lý request, gửi response tới `replyTo` và mang correlation ID tương ứng theo contract của hai phía.
3. Client dùng correlation ID để ghép response với request ban đầu.

Spring `RabbitTemplate` hỗ trợ request/reply qua `convertSendAndReceive(...)` và có cơ chế nội bộ quản lý correlation. **Không tự ý ghi đè hoặc giả định cơ chế correlation nội bộ của template luôn trùng với correlation ID nghiệp vụ của bạn**; khi xây RPC cần theo tài liệu và cấu hình của phiên bản Spring AMQP đang chạy.

### 4.3. correlationId không phải traceId

`correlationId` là một ID tùy chọn do ứng dụng định nghĩa. **Distributed tracing** thường dùng khái niệm trace ID/span ID và các chuẩn propagation như W3C `traceparent`. Có thể log cả `correlationId` và trace ID để đối soát, nhưng hai trường có vòng đời và ý nghĩa khác nhau.

Nếu không có request gốc, ứng dụng có thể tạo một correlation ID mới cho workflow. Khi sinh sự kiện tiếp theo, nên **truyền tiếp ID hiện có** nếu muốn nối chuỗi liên hệ; không bắt buộc mọi hệ thống đều phải dùng cùng quy ước.

## 5. timestamp: thời điểm publisher ghi nhận, không phải thời điểm broker ACK

### 5.1. Ai tạo giá trị timestamp?

Thuộc tính `timestamp` trong AMQP 0-9-1 do **producer cung cấp**. RabbitMQ không mặc nhiên gán thời gian nhận message cho trường này. Trong Spring AMQP, API sử dụng `java.util.Date`:

~~~java
import java.time.Instant;
import java.util.Date;
import org.springframework.amqp.core.MessageProperties;

MessageProperties props = new MessageProperties();
props.setTimestamp(Date.from(Instant.now()));
~~~

Giá trị thời gian AMQP 0-9-1 trên wire có **độ phân giải theo giây**; không nên dựa vào nó để tính chính xác độ trễ mức millisecond. Khi cần độ chính xác cao cho audit hoặc SLA, dùng thêm timestamp trong payload/log/trace theo một contract đã xác định.

### 5.2. Phân biệt các mốc thời gian

| Mốc thời gian | Ai thường ghi? | Ý nghĩa |
| --- | --- | --- |
| `occurredAt` trong payload | Domain/application | Nghiệp vụ thực sự xảy ra khi nào, chẳng hạn đơn được tạo. |
| AMQP `timestamp` | Producer | Message được producer đánh dấu thời gian nào. |
| Broker enqueue/accept | Broker/metrics | Broker đưa message vào queue hoặc ghi nhận publish khi nào; không mặc nhiên là AMQP `timestamp`. |
| Consumer received time | Consumer | Listener bắt đầu thấy message khi nào. |
| Consumer completed time | Consumer | Xử lý nghiệp vụ kết thúc khi nào. |

Ví dụ đơn hàng phát sinh lúc 09:00 nhưng publisher outbox bị nghẽn và đến 09:07 mới gửi. Khi đó `occurredAt` có thể là 09:00, `timestamp` là 09:07; nếu lúc 09:12 consumer mới nhận, thời gian chờ queue là một phần của độ trễ cần quan sát. Việc dùng mốc nào cho metric phải được thống nhất trong hệ thống.

### 5.3. Những giới hạn thường bị bỏ qua

- Nếu producer không set timestamp, giá trị có thể là `null`. Consumer phải xử lý trường hợp thiếu.
- Nếu đồng hồ máy producer lệch, việc trừ `now - timestamp` có thể cho giá trị âm hoặc lớn sai.
- `timestamp` không tự kích hoạt TTL. Message expiration phải dùng cấu hình `expiration`/TTL tương ứng trên message hoặc queue.
- `timestamp` không thay thế việc kiểm tra expiry, idempotency hoặc xử lý message trễ so với trạng thái nghiệp vụ hiện tại.

Nên đồng bộ đồng hồ máy chủ, ghi thời gian chuẩn UTC (hoặc ISO-8601 trong log/payload), và không tự suy ra thứ tự tuyệt đối giữa nhiều producer chỉ từ timestamp.

## 6. type: loại message theo contract của ứng dụng

`type` là chuỗi mô tả message ở cấp nghiệp vụ, chẳng hạn:

~~~text
order.created.v1
order.paid.v1
payment.failed.v2
inventory.reserved.v1
~~~

Trong Spring AMQP:

~~~java
message.getMessageProperties().setType("order.created.v1");
~~~

RabbitMQ **không kiểm tra giá trị `type`** và với exchange trực tiếp hoặc topic thông thường broker vẫn định tuyến theo **routing key, exchange type và binding**, không theo `type`. Producer có thể gửi:

~~~text
exchange    = "orders.events"
routingKey  = "order.created"
type        = "order.created.v1"
~~~

Trong ví dụ này `routingKey` quyết định queue nào nhận message; `type` giúp consumer/logging biết nội dung message thuộc contract nào. Hai giá trị có thể giống nhau theo quy ước nhưng **không phải cùng một field**.

### 6.1. type khác contentType và JSON type headers

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `type` | `order.created.v1` | Loại sự kiện hoặc message theo contract nghiệp vụ. |
| `contentType` | `application/json` | Định dạng bytes của payload. |
| `contentEncoding` | `UTF-8` | Cách diễn giải ký tự hoặc encoding phù hợp với payload. |
| `__TypeId__` trong headers (tùy converter) | Tên hoặc token của Java DTO | Metadata mà một số JSON converter của Spring AMQP dùng để chọn kiểu Java khi deserialize. |
| `schemaVersion` trong custom headers/body (nếu dùng) | `1` | Phiên bản schema theo quy ước ứng dụng. |

**Không dựa vào `type` để Spring tự deserialize JSON vào đúng lớp Java**. `JacksonJsonMessageConverter`/converter cụ thể có quy tắc riêng về type headers, inferred listener type và mapping. Các giá trị Java class name từ nguồn không tin cậy cần được kiểm soát, tránh cấu hình deserialization tùy ý.

Tốt nhất hãy dùng tên type ổn định, độc lập tên package Java. Khi thay đổi schema không tương thích, chọn cách versioning rõ ràng (`order.created.v2`, schema ID hoặc mapping phù hợp) và duy trì consumer tương thích trong giai đoạn chuyển đổi.

### 6.2. Nên làm gì khi consumer gặp type lạ?

Khi nhận `type` không hỗ trợ, đừng parse mù rồi ACK như đã hoàn tất. Thay vào đó:

1. Ghi log đủ `messageId`, `type`, `correlationId` và queue.
2. Phân loại đây là lỗi dữ liệu/contract không thể khắc phục bằng retry ngay.
3. Theo chính sách của hệ thống, reject/dead-letter hoặc đưa vào quy trình điều tra.
4. Tránh requeue vô hạn cùng message chỉ vì consumer không hiểu một type mới.

## 7. appId: nhận diện ứng dụng phát message

`appId` (AMQP wire property `app-id`) là tên/ID ứng dụng producer, ví dụ `order-service`, `payment-service` hoặc `batch-importer`:

~~~java
message.getMessageProperties().setAppId("order-service");
~~~

Một số hệ thống bổ sung thông tin phát hành, môi trường và version ở **custom headers**, chẳng hạn `producerVersion=2026.11`, thay vì nhồi quá nhiều dữ liệu vào `appId`.

### 7.1. appId dùng để làm gì?

- **Observability:** nhóm log và metrics theo dịch vụ phát.
- **Điều tra:** tìm nguồn message chứa sai schema hoặc thiếu metadata.
- **Phân tích tương thích:** phát hiện một version producer cũ còn gửi message.
- **Kiểm soát convention:** xác minh team/service nào có trách nhiệm với type và contract.

### 7.2. appId không phải chứng thực danh tính

`appId` là **chuỗi do publisher tự điền**. Broker không dùng nó như bằng chứng ứng dụng đã được xác thực. Một producer có quyền publish hoàn toàn có thể đặt `appId="trusted-service"` dù đó không phải dịch vụ thật.

Để phân quyền và xác thực, cần sử dụng **RabbitMQ user/permission/vhost, TLS**, cơ chế quản lý secret và phân quyền hạ tầng. Nếu cần chứng cứ chống sửa đổi message, phải áp dụng cơ chế ký/kiểm tra phù hợp ở cấp ứng dụng.

Không đưa password, access token hay dữ liệu cá nhân nhạy cảm vào `appId` hoặc các message headers nhằm mục đích logging.

## 8. Ví dụ đầy đủ: producer gắn năm thuộc tính, listener đọc lại

Ví dụ dùng **Spring AMQP qua RabbitMQ AMQP 0-9-1** với `spring-boot-starter-amqp` trên Spring Boot 3.x. Có thể áp dụng cùng ý tưởng metadata cho các phiên bản tương thích, nhưng ví dụ Java này nhắm đến `RabbitTemplate` và `@RabbitListener`, không tự động áp dụng nguyên xi cho các client AMQP 1.0.

### 8.1. Dependency và kết nối

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
}
~~~

~~~yaml
# application.yml - RabbitMQ cục bộ
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
    listener:
      simple:
        acknowledge-mode: auto
~~~

`guest/guest` chỉ là tài khoản thí nghiệm cục bộ và thường không cho kết nối từ máy khác. Production cần user/vhost/permission riêng, lưu secret an toàn và kết nối TLS theo yêu cầu triển khai.

### 8.2. Khai báo exchange, queue và binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderMessagingTopology {
    public static final String EXCHANGE = "orders.events";
    public static final String QUEUE = "orders.created.q";
    public static final String ROUTING_KEY = "order.created";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue ordersCreatedQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding ordersCreatedBinding(
            Queue ordersCreatedQueue, DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersCreatedQueue)
                .to(ordersExchange)
                .with(ROUTING_KEY);
    }
}
~~~

`RabbitAdmin` trong cấu hình Spring Boot tương ứng có thể khai báo topology từ bean. Direct exchange chọn queue bằng **binding key `order.created`**, chứ không dựa vào năm trường metadata.

### 8.3. Producer dùng MessagePostProcessor

~~~java
import java.time.Instant;
import java.util.Date;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderCreatedPublisher {

    private final RabbitTemplate rabbitTemplate;

    public OrderCreatedPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(
            String orderId,
            String eventId,
            String workflowId) {

        rabbitTemplate.convertAndSend(
                OrderMessagingTopology.EXCHANGE,
                OrderMessagingTopology.ROUTING_KEY,
                orderId,
                message -> {
                    var props = message.getMessageProperties();
                    props.setMessageId(eventId);
                    props.setCorrelationId(workflowId);
                    props.setTimestamp(Date.from(Instant.now()));
                    props.setType("order.created.v1");
                    props.setAppId("order-service");
                    return message;
                }
        );
    }
}
~~~

Điểm quan trọng của method trên:

- `orderId` là **body** trong ví dụ tối giản; message converter của Spring chuyển nó thành bytes.
- `eventId` đại diện một **sự kiện đã được sinh**. Khi phải retry publish cùng sự kiện, caller phải truyền lại **chính eventId cũ**, không tự tạo UUID mới.
- `workflowId` được truyền xuyên qua nhiều sự kiện để gom log vào một workflow.
- `timestamp` ở đây ghi lúc gọi publish. Nếu đang dùng outbox và cần lưu thời điểm sự kiện phát sinh, nên lấy mốc đó từ record outbox, không suy diễn giá trị publish time là business occurred time.
- `type` và `appId` mô tả message và nguồn phát, không thay đổi việc định tuyến của direct exchange.

Ví dụ gọi (đặt trong method có sẵn bean `OrderCreatedPublisher publisher`):

~~~java
String eventId = java.util.UUID.randomUUID().toString();
String workflowId = "checkout-1001";

publisher.publish("ORD-1001", eventId, workflowId);
// Nếu cần retry cùng eventId, giữ nguyên eventId và workflowId.
~~~

Một producer thực tế thường có **event DTO** gồm `eventId`, `occurredAt` và version trong payload hoặc outbox, cùng một `MessageConverter` JSON phù hợp. Ví dụ dùng chuỗi `orderId` để làm nổi bật năm AMQP properties và tránh trộn thêm yêu cầu serialization.

### 8.4. Consumer đọc message và metadata

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Date;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedConsumer {

    @RabbitListener(queues = OrderMessagingTopology.QUEUE)
    public void onMessage(Message message) {
        MessageProperties p = message.getMessageProperties();
        String orderId = new String(message.getBody(), StandardCharsets.UTF_8);

        String messageId = p.getMessageId();
        String correlationId = p.getCorrelationId();
        Date sentAt = p.getTimestamp();
        String type = p.getType();
        String appId = p.getAppId();

        System.out.printf(
                "orderId=%s, messageId=%s, correlationId=%s, "
                        + "timestamp=%s, type=%s, appId=%s%n",
                orderId, messageId, correlationId, sentAt, type, appId
        );

        // Production: kiểm tra type/metadata bắt buộc và idempotency
        // trước khi ghi nghiệp vụ. Chỉ hoàn tất khi đã xử lý an toàn.
    }
}
~~~

Listener nhận `Message` trực tiếp nên không cần đoán cách ánh xạ metadata từ method argument. Trong trường hợp dùng DTO:

~~~java
// Ví dụ về ý tưởng, chỉ áp dụng khi đã cấu hình converter phù hợp:
// @RabbitListener(queues = "orders.created.q")
// void onCreated(OrderCreatedEvent event, Message rawMessage) { ... }
~~~

Cần đọc tài liệu đúng phiên bản nếu muốn binding kết hợp DTO, `@Header` và method parameters. Ví dụ chính sử dụng **một tham số `Message`** để có khả năng kiểm chứng rõ ràng.

Nếu producer không điền một số metadata, các getter có thể trả về `null`. Listener thật cần **kiểm tra và chọn chính sách**: từ chối message thiếu ID quan trọng, sinh log cảnh báo hoặc hỗ trợ message legacy theo contract đã thống nhất; không nên tùy tiện tạo message ID mới ở consumer rồi cho rằng đã chống trùng thành công.

## 9. Theo dõi một sự kiện qua RabbitMQ

~~~mermaid
sequenceDiagram
    autonumber
    participant A as OrderService
    participant T as RabbitTemplate
    participant B as Exchange/Queue RabbitMQ
    participant C as @RabbitListener
    participant D as Database
    A->>A: Tạo eventId ổn định + workflowId
    A->>T: convertAndSend + 5 properties
    T->>B: Publish body và properties
    opt Bật publisher confirms
        B-->>T: Confirm ACK/NACK của lần publish
    end
    B->>C: Giao message, giữ metadata
    C->>C: Kiểm tra messageId/type
    C->>D: Ghi nghiệp vụ + dấu processed(eventId)
    D-->>C: Commit
    C-->>B: Consumer ACK
~~~

Trong đường đi này:

1. **Exchange, routing key và binding** quyết định queue đích.
2. **Body và properties** được delivery đến consumer.
3. **Publisher confirm** cho biết broker xử lý publish ra sao, không cho biết consumer đã commit.
4. **Consumer ACK** chỉ được gửi sau khi listener hoàn tất theo chế độ đã cấu hình. Nếu consumer bị lỗi giữa commit DB và ACK, message có thể được giao lại.
5. **`messageId` ổn định + dấu đã xử lý trong DB** giúp tránh áp dụng nghiệp vụ trùng.

Với `acknowledge-mode: auto` của **Spring listener container**, container ACK khi method xử lý thành công; đây không phải RabbitMQ `autoAck=true`. Nếu listener ném lỗi, việc requeue, reject hoặc dead-letter phụ thuộc vào cấu hình lỗi và retry. Năm thuộc tính metadata **không tự tạo ra exactly-once delivery hoặc exactly-once side effect**.

## 10. messageId, correlationId và CorrelationData là ba thứ khác nhau

Khi bật publisher confirms ở Spring AMQP, producer có thể dùng:

~~~java
import org.springframework.amqp.rabbit.connection.CorrelationData;

CorrelationData confirmData = new CorrelationData(eventId);
rabbitTemplate.convertAndSend(
        OrderMessagingTopology.EXCHANGE,
        OrderMessagingTopology.ROUTING_KEY,
        orderId,
        message -> {
            message.getMessageProperties().setMessageId(eventId);
            message.getMessageProperties().setCorrelationId(workflowId);
            return message;
        },
        confirmData
);
~~~

Đây là ví dụ code trong method có sẵn `rabbitTemplate`, `eventId`, `workflowId` và `orderId`. Khi bật `publisher-confirm-type=correlated`, ứng dụng có thể quan sát kết quả publish thông qua callback hoặc `confirmData.getFuture()`.

| Trường/đối tượng | Nơi tồn tại | Mục đích |
| --- | --- | --- |
| `MessageProperties.messageId` | Property **trên wire**, đi cùng message | ID sự kiện / thông điệp để nhận diện và đối soát. |
| `MessageProperties.correlationId` | Property **trên wire**, đi cùng message | Nối request/reply hoặc chuỗi workflow. |
| `CorrelationData` | Đối tượng **phía Spring publisher** để theo dõi confirm | Ghép publisher ACK/NACK với lệnh gửi tương ứng. |

Ba giá trị có thể được ứng dụng chọn bằng nhau trong một tình huống cụ thể, nhưng **không tự động là cùng một cơ chế**. Đặc biệt, `CorrelationData` không thay thế `correlationId` trong message properties. Consumer thường không có được object `CorrelationData` mà producer dùng để đợi publisher confirm.

Nếu cần phát hiện message không định tuyến được, ngoài confirms còn phải xử lý **mandatory returns** (`RabbitTemplate.ReturnsCallback` hoặc dữ liệu return gắn với correlation khi được hỗ trợ). Một publish được broker **confirm ACK** vẫn có thể là **unroutable** nếu thiếu binding phù hợp.

## 11. Metadata khi retry, redelivery và dead-letter

### 11.1. Consumer nhận lại một delivery

Giả sử listener đã cập nhật DB nhưng mất connection trước khi ACK. RabbitMQ có thể gửi lại cùng message. Thông thường các thuộc tính được phát như `messageId`, `correlationId`, `type` và `appId` vẫn đi cùng message qua lần giao lại; **delivery tag** có thể khác vì là một lần delivery mới. Broker cũng có thể đánh dấu **redelivered** hoặc thêm metadata liên quan đến lịch sử dead-letter.

~~~text
Lần delivery đầu:
  messageId = evt-1001
  correlationId = checkout-1001
  deliveryTag = 7
  side effect DB hoàn tất, ACK thất lạc

Lần delivery lại:
  messageId = evt-1001
  correlationId = checkout-1001
  deliveryTag = 12 (minh họa; không giả định luôn tăng kiểu này)
  consumer phát hiện evt-1001 đã xử lý
  -> không thực hiện lại side effect
~~~

Việc broker có thể giao lại thông điệp là lý do cần **idempotency**; bản thân `messageId` chỉ là khóa đầu vào cho cơ chế đó.

### 11.2. Republish qua retry queue hoặc DLX

Với dead-letter exchange (DLX), RabbitMQ có thể thêm/cập nhật các header liên quan lịch sử dead-letter (ví dụ `x-death` trong các luồng phù hợp). Những header này **khác** năm thuộc tính chuẩn đang học.

Nếu **ứng dụng chủ động tạo message mới** để retry qua queue khác, cần quyết định rõ:

- **Retry cùng logical event**: giữ **event ID ổn định** để consumer chống trùng; có thể có `attemptId` hoặc `retryCount` riêng để quan sát số lần thử.
- **Tạo sự kiện nghiệp vụ mới thật sự**: dùng message ID mới, giữ correlation ID nếu vẫn thuộc cùng workflow.
- **Thời gian**: phân biệt thời điểm sự kiện xảy ra và thời điểm một lần republish diễn ra; nếu cần cả hai, lưu ở những trường rõ ràng.
- **Loại và nguồn phát**: giữ `type` và quy ước `appId` nhất quán; nếu một retry service thực sự là publisher mới, ghi rõ tác nhân và nguồn gốc event ở contract/log.

Không nên dùng riêng `x-death` hoặc redelivered flag như cơ chế chống trùng tuyệt đối: số lần delivery và cách message đi qua retry/republish còn tùy topology, broker version và chiến lược retry.

### 11.3. Transactional outbox

Trong hệ thống vừa ghi database vừa phát message, một lần DB commit thành công nhưng publish chưa kịp thực hiện sẽ khiến sự kiện bị bỏ sót nếu không có cơ chế bổ sung. **Transactional outbox** giải quyết bằng cách ghi dữ liệu nghiệp vụ và bản ghi sự kiện (gồm `eventId`, `type`, `correlationId`, `occurredAt`) trong **cùng transaction DB**. Một publisher khác gửi event từ outbox và theo dõi broker confirm.

Khi publisher outbox retry, nó dùng **eventId cũ** làm `messageId`. Consumer vẫn phải idempotent vì broker có thể đã nhận một lần publish trước đó mà confirm bị thất lạc.

## 12. Thiết kế quy ước metadata cho hệ thống nhiều dịch vụ

Một bộ quy ước đơn giản:

| Thuộc tính | Quy ước gợi ý | Xử lý khi thiếu/sai |
| --- | --- | --- |
| `messageId` | ID duy nhất cho một logical event, giữ nguyên khi publish retry. | Với queue nghiệp vụ quan trọng, coi message thiếu ID là lỗi contract và đưa vào xử lý lỗi có kiểm soát. |
| `correlationId` | ID từ request/workflow gốc, truyền cho các sự kiện phát sinh cùng workflow. | Có thể tạo mới ở điểm bắt đầu workflow nếu contract cho phép; ghi log rõ nguồn. |
| `timestamp` | Do producer đặt, UTC; trong payload lưu thêm business occurredAt nếu khác publish time. | Phân biệt null/clock skew; không dùng làm điều kiện thứ tự tuyệt đối. |
| `type` | Tên event trung lập với Java class, có version khi schema thay đổi. | Validate type được hỗ trợ; reject/DLQ theo chính sách thay vì requeue vô hạn. |
| `appId` | Tên logic ổn định của publisher service. | Dùng để quan sát, không dùng làm credential hay căn cứ authorization. |

Trong log, nên có cả `messageId` và `correlationId`, cùng queue, routing key, `type`, `appId`, event ID trong DB và kết quả xử lý. Không cần log toàn bộ body nếu có dữ liệu khách hàng nhạy cảm.

### 12.1. Đừng dùng timestamp để thay thế kiểm tra tính hợp lệ

Một message cũ chưa chắc lỗi; consumer có thể cố ý xử lý lại để đồng bộ dữ liệu. Ngược lại, message mới vẫn có thể không còn hợp lệ vì trạng thái nghiệp vụ đã thay đổi. Khi cần ràng buộc tuổi message, dùng **TTL hoặc quy tắc nghiệp vụ** rõ ràng; không tự loại bỏ chỉ vì `timestamp` trông cũ.

### 12.2. Đừng dùng type làm khóa định tuyến khi broker không được cấu hình như vậy

Với **direct exchange** thường dùng trong ví dụ, key `order.created` quyết định binding nào khớp. Với **topic exchange**, pattern của routing key quyết định khớp wildcard. `type="order.created.v1"` vẫn là property phục vụ ứng dụng; nếu muốn route theo loại sự kiện, producer nên đặt routing key thích hợp hoặc thiết kế header exchange/binding tường minh.

### 12.3. Đừng dùng appId thay thế danh tính publisher đã xác thực

Chỉ một tài khoản RabbitMQ có quyền publish mới được broker cho phép gửi tới exchange tương ứng. `appId` có thể giúp điều tra các service hợp lệ nhưng không thay thế quyền broker. Cần đối chiếu vhost, permissions, credentials và audit logs khi có yêu cầu truy vết nguồn phát mang tính bảo mật.

## 13. Bài thực hành

Sử dụng RabbitMQ cục bộ có Management UI và Spring Boot với topology, producer, consumer ở mục 8. Không thử những thao tác cố ý tạo lỗi trên queue production.

| Bước | Thao tác | Kết quả cần quan sát |
| --- | --- | --- |
| 1 | Khởi động ứng dụng, tạo queue `orders.created.q`, exchange `orders.events` và binding `order.created`. | Queue và binding xuất hiện đúng trong cùng virtual host. |
| 2 | Gọi `publish("ORD-1001", "evt-1001", "checkout-1001")`. | Listener đọc body và đủ năm thuộc tính. |
| 3 | Publish sự kiện mới `evt-1002` với cùng `checkout-1001`. | `messageId` khác, `correlationId` giống; log có thể ghép workflow. |
| 4 | Bỏ `setTimestamp` và gửi lại vào queue thử nghiệm. | Consumer có thể thấy `timestamp=null`; tránh gọi method trên null. |
| 5 | Đổi `type` sang `order.created.v2` khi consumer chỉ hiểu v1. | Consumer ghi nhận type không hỗ trợ và thực hiện chính sách lỗi; không requeue vô hạn. |
| 6 | Gửi cùng logical event ID hai lần và thêm bảng processed-event. | Side effect nghiệp vụ chỉ xảy ra một lần nhờ idempotency, dù message có thể được giao nhiều lần. |
| 7 | Bật publisher confirms, gắn `CorrelationData` rồi so sánh với `correlationId` của message. | Confirm theo dõi lần publish; message correlation ID vẫn là thông tin workflow. |
| 8 | Dừng listener khi queue còn tồn tại, publish và chạy lại listener. | Message được giữ và giao khi consumer trở lại theo độ bền/persistence phù hợp. |
| 9 | Cấu hình DLX/DLQ thử nghiệm và cố ý reject một message lỗi schema. | Kiểm tra metadata gốc, headers do broker thêm và số message tại DLQ. |

### Mẫu log cần ghi nhận

~~~text
eventId/messageId:
correlationId:
timestamp:
type:
appId:
exchange + routingKey:
queue:
publisherConfirm:
consumerReceivedAt:
consumerResult:
redelivered:
retry/dead-letter info:
DB transaction / idempotency result:
~~~

Để kiểm chứng thời gian, ghi thêm `Instant.now()` phía consumer khi nhận, nhưng nhớ rằng so sánh với AMQP timestamp có thể chịu sai lệch đồng hồ producer/consumer và độ phân giải theo giây của trường này.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Hai message có `messageId` giống nhau. RabbitMQ có tự loại một message vì trùng không?

**Trả lời:** Không. Broker không mặc nhiên bảo đảm uniqueness hoặc deduplication theo `messageId`; ứng dụng phải thiết kế cơ chế chống trùng.

**Câu 2.** Một checkout sinh ba event với ba message ID khác nhau. Có nên cho cả ba cùng correlation ID không?

**Trả lời:** Có thể, nếu muốn liên kết chúng về cùng workflow. `correlationId` không buộc phải giống `messageId`.

**Câu 3.** Timestamp trên message có phải giờ RabbitMQ đã xử lý message không?

**Trả lời:** Không. Thuộc tính này do publisher gán; broker không tự mặc định điền ngày giờ nhận.

**Câu 4.** Producer đặt `type="order.created.v1"` nhưng routing key là `order.cancelled`. Direct exchange có tự sửa đường đi theo type không?

**Trả lời:** Không. Direct exchange định tuyến theo routing key/binding. `type` là metadata ứng dụng.

**Câu 5.** `appId="payment-service"` chứng minh request đến từ payment-service đã được xác thực chưa?

**Trả lời:** Chưa. `appId` do publisher cung cấp, không thay thế cơ chế xác thực và phân quyền của RabbitMQ.

**Câu 6.** `CorrelationData("evt-1001")` và `MessageProperties.setCorrelationId("checkout-1001")` có cùng chức năng không?

**Trả lời:** Không. `CorrelationData` giúp publisher liên kết broker confirm với lần gửi; property `correlationId` đi cùng message để liên kết workflow hoặc request/reply.

**Câu 7.** Listener đã commit DB nhưng mất ACK. Nếu cùng message được giao lại, nên dùng gì để tránh ghi trùng?

**Trả lời:** Dùng event ID/`messageId` ổn định, bảng dấu đã xử lý có unique constraint và transaction DB thích hợp; consumer ack riêng không tạo exactly-once side effect.

## 15. Tài liệu tham khảo

- [RabbitMQ — AMQP 0-9-1 Model Explained](https://www.rabbitmq.com/tutorials/amqp-concepts): message attributes, headers, exchange, queue và routing.
- [RabbitMQ — Consumers (Message Properties)](https://www.rabbitmq.com/docs/consumers): `message-id`, `correlation-id`, `timestamp`, `type` và `app-id`.
- [Spring AMQP — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): cách chuyển body/object và quản lý `MessageProperties` khi gửi và nhận.
- [Spring AMQP — Sending Messages](https://docs.spring.io/spring-amqp/reference/amqp/sending-messages.html): `RabbitTemplate`, `MessagePostProcessor` và `CorrelationData`.
- [Spring AMQP — MessageProperties Javadoc](https://docs.spring.io/spring-amqp/api/org/springframework/amqp/core/MessageProperties.html): API getter/setter của metadata.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): phân biệt tín hiệu xác nhận publish và delivery.

**Ghi nhớ:** `messageId` nhận diện **một sự kiện/message**, `correlationId` nối **nhiều message trong một workflow**, `timestamp` là **thời gian publisher ghi nhận**, `type` mô tả **loại sự kiện**, còn `appId` mô tả **ứng dụng phát**. Cả năm là metadata bổ trợ cho body và routing; chúng không tự định tuyến, xác thực, deduplicate hay xác nhận xử lý. Trong Spring AMQP, cần kết hợp chúng với exchange/queue/binding, publisher confirms, `@RabbitListener`, consumer ACK, retry/dead-letter, outbox và idempotency để xây dựng luồng xử lý bất đồng bộ đáng tin cậy.
