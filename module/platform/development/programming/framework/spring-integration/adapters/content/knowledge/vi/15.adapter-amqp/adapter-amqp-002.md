# AMQP outbound channel adapter

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả đường đi **MessageChannel → AMQP outbound channel adapter → RabbitTemplate → RabbitMQ exchange → queue**.
- Phân biệt outbound adapter **một chiều** với outbound gateway **request–reply**.
- Thiết kế payload, AMQP message properties, headers, routing key, binding và MessageConverter cho sự kiện nghiệp vụ.
- Viết luồng Spring Integration Java DSL publish message đến RabbitMQ và kiểm tra kết quả thực tế.
- Phân biệt **publisher confirms**, **publisher returns** và **consumer ACK**, từ đó quyết định retry, lưu tiến độ, idempotency và outbox.
- Đánh giá hiệu năng, bảo mật, vòng đời kết nối và cách phục hồi khi hệ thống đích gặp lỗi.

## 1. Tại sao cần AMQP outbound channel adapter?

Giả sử ứng dụng đặt hàng tạo một sự kiện **OrderCreated** sau khi ghi nhận đơn hàng. Hệ thống kho, dịch vụ thông báo và hệ thống phân tích đều cần sự kiện này nhưng không cần được gọi trực tiếp trong cùng một HTTP request. RabbitMQ có thể đứng giữa: producer publish sự kiện vào **exchange**, broker định tuyến message đến những **queue** phù hợp, các consumer tự nhận khi sẵn sàng.

**AMQP outbound channel adapter** của Spring Integration là endpoint ở **biên gửi**. Nó nhận một Spring Message từ MessageChannel, chuyển nội dung qua hạ tầng Spring AMQP rồi publish tới RabbitMQ. Các xử lý nghiệp vụ phía trước không phải trực tiếp quản lý channel của RabbitMQ client.

~~~mermaid
flowchart LR
    S["OrderService<br/>OrderCreated"] --> M["Spring Message<br/>payload + headers"]
    M --> C["MessageChannel<br/>ordersToAmqp"]
    C --> A["AMQP outbound<br/>channel adapter"]
    A --> T["RabbitTemplate<br/>MessageConverter"]
    T --> X["RabbitMQ direct exchange<br/>orders.events"]
    X -->|"orders.created"| Q["Queue<br/>orders.created.q"]
    Q --> H["Consumer bên nhận"]
~~~

Điểm cần ghi nhớ:

- **Spring MessageChannel** là hạ tầng messaging nội bộ ứng dụng; nó không phải RabbitMQ queue.
- **Outbound adapter** tiêu thụ message và tạo tác động publish một chiều; không tự trả response nghiệp vụ của consumer.
- **RabbitTemplate** và **ConnectionFactory** quản lý phía client AMQP, trong khi **exchange/binding/queue** là topology ở broker.
- **Consumer** quyết định cách xử lý delivery và ACK sau khi message đến queue. Producer không được tự suy diễn kết quả nghiệp vụ của consumer.

## 2. Hành trình publish và những mốc hoàn tất khác nhau

| Giai đoạn | Thành phần | Điều đã xảy ra |
| --- | --- | --- |
| 1. Chuẩn bị sự kiện | Business service / transformer | Tạo payload và thông tin định danh nghiệp vụ |
| 2. Chuyển giao nội bộ | MessageChannel | Chấp nhận message theo ngữ nghĩa channel |
| 3. Xử lý ở biên | AMQP outbound adapter | Nhận message, xác định exchange/routing key và cách chuyển đổi |
| 4. Tạo AMQP message | MessageConverter | Ánh xạ payload và properties thành body bytes + metadata |
| 5. Gửi yêu cầu | RabbitTemplate | Publish qua ConnectionFactory theo cấu hình |
| 6. Broker tiếp nhận | RabbitMQ exchange | Đánh giá routing, có thể phát publisher confirm |
| 7. Message đến queue | Binding/queue | Queue chứa delivery theo topology và chính sách broker |
| 8. Nghiệp vụ bên nhận | Consumer | Đọc delivery, xử lý và ACK/NACK theo hợp đồng |

**Bước 2 không chứng minh bước 6; bước 6 không chứng minh bước 7; bước 7 không chứng minh bước 8.** Mỗi bước có cách quan sát và cơ chế phục hồi riêng.

### 2.1. Exchange và routing key quyết định nơi đến

RabbitMQ không yêu cầu mọi producer gửi trực tiếp đến một queue. Producer publish đến exchange với routing key; exchange dùng binding và loại exchange để định tuyến:

~~~mermaid
flowchart TD
    P["Publisher"] --> E["Direct exchange<br/>orders.events"]
    E -->|"Binding key: orders.created"| Q1["orders.created.q"]
    E -. "Không có binding phù hợp" .-> U["Unroutable<br/>cần xử lý theo policy"]
    Q1 --> C["AMQP inbound consumer"]
~~~

| Khái niệm | Trách nhiệm |
| --- | --- |
| **Exchange** | Điểm tiếp nhận publish và quyết định định tuyến |
| **Routing key** | Thông tin producer cung cấp để exchange chọn route |
| **Binding** | Liên kết exchange với queue theo điều kiện định tuyến |
| **Queue** | Giữ message đã được route đến theo chính sách broker |
| **Consumer acknowledgment** | Xác nhận hoặc từ chối delivery ở phía consumer |

**Direct exchange** thường dùng routing key khớp binding key; **topic exchange** dùng pattern; **fanout exchange** dùng bindings để phát đến nhiều queue. **Default exchange** có tên rỗng và cho phép route theo tên queue, nhưng đó là trường hợp riêng. Bài này dùng exchange có tên để làm rõ mô hình.

### 2.2. Endpoint một chiều không có reply nghiệp vụ

Outbound channel adapter nhận message và gọi thao tác publish; nó không phát reply message mang kết quả nghiệp vụ của hệ thống nhận. Một lần gọi adapter có thể lỗi đồng bộ hoặc phát sinh producer callback, nhưng **ACK của broker không trở thành business response của người xử lý đơn hàng**.

Nếu cần gửi yêu cầu qua AMQP rồi nhận một phản hồi nghiệp vụ để flow tiếp tục, dùng **AMQP outbound gateway** hoặc thiết kế quy trình phản hồi bất đồng bộ với correlation ID và nơi nhận reply riêng.

## 3. Adapter, gateway và các hướng giao tiếp AMQP

| Endpoint | Hướng dữ liệu | Hợp đồng | Ví dụ |
| --- | --- | --- | --- |
| **AMQP outbound channel adapter** | Spring MessageChannel → RabbitMQ | One-way | Publish OrderCreated |
| **AMQP inbound channel adapter** | RabbitMQ queue → Spring MessageChannel | One-way | Nhận OrderCreated |
| **AMQP outbound gateway** | Flow → RabbitMQ → reply về flow | Request–reply | Truy vấn kết quả xử lý qua AMQP |
| **AMQP inbound gateway** | RabbitMQ request → flow → AMQP reply | Request–reply | Nhận lệnh, thực thi rồi trả kết quả |

AMQP gateway có thể sử dụng reply-to destination, correlation ID và timeout. Những thông tin đó khác **publisher confirm** và **consumer ACK**. Không chọn gateway chỉ để “biết broker có nhận message chưa”; hãy sử dụng publisher confirms/returns phù hợp cho nhu cầu xác nhận kỹ thuật.

## 4. Payload, MessageConverter và AMQP properties

Một Spring Message gồm **payload** và **MessageHeaders**. AMQP message trên đường truyền có **body bytes** và **message properties**. Cần ánh xạ rõ từng phần:

~~~text
Spring Message
├── payload: String / byte[] / DTO / ...
└── headers
    ├── eventId (nếu được bổ sung)
    ├── correlation ID
    └── metadata của flow
           |
           v
AMQP outbound adapter + MessageConverter
           |
           v
AMQP message
├── body: byte[]
└── properties
    ├── contentType / contentEncoding
    ├── deliveryMode
    ├── messageId / correlationId
    └── application headers đã được mapping
           |
           v
RabbitMQ exchange + routing key
~~~

Không nên giả định mọi Spring header tự động được chuyển sang AMQP properties. Việc ánh xạ phụ thuộc module, cấu hình adapter, RabbitTemplate và converter.

| Payload | Hướng chuyển đổi | Lưu ý |
| --- | --- | --- |
| **String** | Mã hóa bytes theo charset, thường dùng dạng text | Producer và consumer phải thống nhất charset |
| **byte[]** | Chuyển body nhị phân | Consumer cần hiểu đúng wire format |
| **DTO hoặc Java record** | Converter/serializer tạo JSON, Avro, Protobuf hoặc schema khác | Không phát Java object tùy ý khi nhiều ngôn ngữ sử dụng |
| **File lớn** | Đọc/stream hoặc tham chiếu file tùy thiết kế | Không nên nạp toàn bộ nội dung lớn vào một message theo mặc định |

### 4.1. Các metadata nên thiết kế có chủ đích

| Trường | Công dụng | Điều cần tránh |
| --- | --- | --- |
| **contentType** | Khai báo kiểu body | Khai JSON nhưng gửi bytes không phải JSON |
| **contentEncoding** | Charset/compression theo hợp đồng | Decoder sai charset |
| **deliveryMode** | Xác định chế độ persistent nếu cần | Cho rằng chỉ queue durable là đủ |
| **messageId** | Truy vết bản tin | Tự coi là khóa chống trùng nghiệp vụ |
| **correlationId** | Ghép request/reply hoặc tracing | Dùng thay eventId khi mục đích khác nhau |
| **eventId** | Khóa nghiệp vụ ổn định qua retry | Sinh eventId mới mỗi lần gửi lại |
| **replyTo** | Dùng trong request–reply | Thêm tùy tiện vào one-way event |
| **routing key** | Định tuyến ở exchange | Nhầm với Spring MessageChannel name |

Các header Spring Integration như **replyChannel** và **errorChannel** có thể là tham chiếu nội bộ tới MessageChannel, **không nên serialize nguyên dạng ra RabbitMQ**. Hãy chỉ cho phép những metadata thực sự cần vượt biên và kiểm tra loại/giá trị header.

### 4.2. Converter và transformer làm hai nhiệm vụ

- **Transformer** trong flow chuẩn hóa sự kiện nghiệp vụ, ví dụ OrderCreated DTO thành JSON String với schemaVersion.
- **MessageConverter** của RabbitTemplate chuyển payload thành AMQP body/properties để publish.

Nếu converter JSON đã chuyển DTO thành JSON, không nên có thêm transformer JSON chồng lên khiến body bị double-encoded. Với sự kiện thực tế, cần quy ước schema, charset, trường bắt buộc, version và giới hạn kích thước payload.

## 5. Ví dụ Spring Integration Java DSL: gửi OrderCreated lên RabbitMQ

Ví dụ tạo topology và luồng sau:

~~~mermaid
flowchart LR
    P["OrderEventPublisher"] --> CH["ordersToAmqp<br/>DirectChannel"]
    CH --> AD["Amqp.outboundAdapter"]
    AD --> R["RabbitTemplate"]
    R --> EX["orders.events"]
    EX -->|"orders.created"| Q["orders.created.q"]
~~~

**Hợp đồng minh họa:** sự kiện được biểu diễn dưới dạng String **eventId|orderId|totalVnd**. Đây là mẫu tối giản cho bài học; production nên dùng JSON/Avro/Protobuf với parser/serializer và schema rõ ràng.

### 5.1. Dependencies và kết nối

Với Spring Boot, sử dụng dependency management phù hợp để quản lý phiên bản Spring Integration/Spring AMQP:

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

Ứng dụng cần RabbitMQ broker khả dụng và RabbitTemplate/ConnectionFactory được cấu hình host, port, virtual host, xác thực, TLS theo môi trường. Credential thật cần được đưa qua secret manager hoặc environment, không commit vào source.

### 5.2. Topology và outbound IntegrationFlow

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
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
public class OrdersAmqpOutboundConfiguration {

    public static final String EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "orders.created";
    public static final String QUEUE = "orders.created.q";

    @Bean
    public DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue createdOrdersQueue() {
        return new Queue(QUEUE, true);
    }

    @Bean
    public Binding createdOrdersBinding(
            Queue createdOrdersQueue,
            DirectExchange ordersExchange) {
        return BindingBuilder.bind(createdOrdersQueue)
            .to(ordersExchange)
            .with(ROUTING_KEY);
    }

    @Bean
    public MessageChannel ordersToAmqp() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow publishOrdersFlow(RabbitTemplate rabbitTemplate) {
        return IntegrationFlow.from("ordersToAmqp")
            .handle(Amqp.outboundAdapter(rabbitTemplate)
                .exchangeName(EXCHANGE)
                .routingKey(ROUTING_KEY))
            .get();
    }
}
~~~

**Giải thích:**

1. **DirectExchange** nhận message publish, dùng routing key để định tuyến.
2. **Queue** được tạo durable để minh họa topology cần tồn tại qua broker restart; durable queue không tự bảo đảm message không mất.
3. **Binding** liên kết exchange với queue bằng **orders.created**.
4. **ordersToAmqp** là DirectChannel mà producer nội bộ gửi Spring Message vào.
5. **Amqp.outboundAdapter(rabbitTemplate)** tạo outbound endpoint; exchangeName và routingKey là thuộc tính đích của lần publish.

Bean exchange, queue, binding có thể được RabbitAdmin tự khai báo khi đã cấu hình đúng, có connection và đủ quyền. Nếu tổ chức quản lý topology bằng hạ tầng riêng, ứng dụng không được mặc nhiên coi bean declaration đồng nghĩa topology broker đã có; hãy xác minh thực tế.

### 5.3. Producer gửi vào MessageChannel

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final MessageChannel ordersToAmqp;

    public OrderEventPublisher(
            @Qualifier("ordersToAmqp") MessageChannel ordersToAmqp) {
        this.ordersToAmqp = ordersToAmqp;
    }

    public void publish(
            String eventId, String orderId, long totalVnd) {
        if (eventId == null
                || !eventId.matches("[A-Za-z0-9_-]{1,80}")
                || orderId == null
                || !orderId.matches("[A-Za-z0-9_-]{1,80}")
                || totalVnd <= 0) {
            throw new IllegalArgumentException(
                "Order event khong hop le");
        }

        String body = eventId + "|" + orderId + "|" + totalVnd;
        Message<String> message = MessageBuilder.withPayload(body)
            .setHeader("eventId", eventId)
            .build();

        boolean accepted = ordersToAmqp.send(message);
        if (!accepted) {
            throw new IllegalStateException(
                "Khong chuyen duoc message vao channel");
        }
    }
}
~~~

Ví dụ:

~~~java
publisher.publish("evt-1001", "O-1001", 150000L);
~~~

Body minh họa là:

~~~text
evt-1001|O-1001|150000
~~~

**eventId nằm trong payload** để consumer có thể đọc được ngay cả khi header ứng dụng eventId không được mapper chuyển vào AMQP properties. Nếu đối tác yêu cầu eventId xuất hiện trong AMQP header, cần cấu hình và kiểm thử việc mapping một cách chủ đích.

**DirectChannel** gọi outbound handler trong chuỗi xử lý đồng bộ. Lỗi gửi đồng bộ có thể lan ngược đến caller; tuy nhiên **send() thành công không chứng minh đã nhận publisher confirm, đã route vào queue hoặc consumer đã xử lý**.

### 5.4. Thử nghiệm theo từng ranh giới

1. Chạy RabbitMQ trong môi trường test và cấu hình ConnectionFactory.
2. Khởi động ứng dụng; kiểm tra exchange, queue, binding đã được khai báo thực tế.
3. Gọi phương thức publish với evt-1001, O-1001 và 150000.
4. Dùng RabbitMQ management hoặc consumer test để quan sát message trong orders.created.q, body và properties.
5. Gửi một eventId khác, kiểm tra routing ổn định.
6. Trong test riêng, thử routing key không được bind để xem cơ chế publisher returns khi đã cấu hình mandatory.
7. Tạm dừng consumer để quan sát backlog; bật lại để kiểm tra consumer đọc message theo ACK policy.

Nếu consumer xử lý rất nhanh, queue có thể trống khi bạn xem; **queue depth bằng 0 không tự chứng minh publish thất bại**. Dùng publish/deliver/ack metrics hoặc consumer kiểm chứng nội dung.

**Giới hạn ví dụ:** Định dạng phân cách bằng dấu gạch đứng chỉ phù hợp với ID được validate như trên. Mã chưa xử lý confirm/return, outbox, retry, transaction hay schema version. Với production cần bổ sung trước khi dùng để phát sự kiện quan trọng.

## 6. Ba cơ chế xác nhận phải phân biệt

~~~mermaid
sequenceDiagram
    participant A as Outbound adapter
    participant T as RabbitTemplate
    participant X as RabbitMQ exchange
    participant Q as Queue
    participant C as Consumer
    A->>T: Publish AMQP message
    T->>X: basic.publish
    alt Có route phù hợp
        X->>Q: Định tuyến đến queue
    else Unroutable với mandatory
        X-->>T: basic.return
    end
    X-->>T: Publisher confirm ACK/NACK
    Q-->>C: Delivery
    C-->>Q: Consumer ACK/NACK (riêng)
~~~

| Tín hiệu | Bên gửi | Ý nghĩa | Không chứng minh |
| --- | --- | --- | --- |
| **Publisher confirm** | RabbitMQ → publisher | Broker xác nhận publish theo cơ chế confirms | Consumer hoàn tất nghiệp vụ |
| **Publisher return** | RabbitMQ → publisher | Publish không route được với mandatory và không có route phù hợp | Lỗi parse/ghi dữ liệu của consumer |
| **Consumer ACK/NACK** | Consumer → RabbitMQ | Consumer xác nhận/từ chối một delivery | Producer có business reply |

### 6.1. Publisher confirms

Publisher confirms được bật ở tầng RabbitMQ client. Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
~~~

Với correlated confirms, ứng dụng có thể dùng **CorrelationData** và callback/future theo API của Spring AMQP để liên kết kết quả ACK/NACK với lần publish. **Bật confirms không tự động biến outbound adapter thành gateway**, không tự lưu trạng thái outbox và không mặc nhiên trả business reply cho caller.

Nếu nghiệp vụ cần khẳng định event đã đạt mốc broker, phải có cơ chế thu thập confirm, xử lý NACK/timeout và cập nhật trạng thái theo đúng hợp đồng. Không chỉ dựa vào boolean của MessageChannel.send().

### 6.2. Mandatory và publisher returns

Nếu exchange tồn tại nhưng không có binding nào phù hợp, message có thể **unroutable**. Để quan sát trường hợp này, có thể bật returns và mandatory:

~~~yaml
spring:
  rabbitmq:
    publisher-returns: true
    template:
      mandatory: true
~~~

Với RabbitTemplate, có thể xử lý returned message qua **ReturnsCallback** hoặc cơ chế theo dõi phù hợp. RabbitMQ có thể gửi **publisher confirm ACK** cho một bản publish **không route được**, nên **confirm ACK không thay thế kiểm tra returns**.

Nếu nhiều phần ứng dụng dùng chung RabbitTemplate, hãy quản lý callbacks tập trung; không tự ý ghi đè callback của phần khác. Trong luồng quan trọng, nên có publish tracker thống nhất để liên kết eventId, confirm, return và timeout.

### 6.3. Consumer ACK không liên quan trực tiếp đến producer confirm

Consumer ACK diễn ra sau khi RabbitMQ giao message cho consumer theo mode và chính sách phía nhận. Một message có thể đã được producer confirm trước khi consumer bắt đầu xử lý.

Do đó nếu cần đo “hệ thống kho đã cập nhật xong”, producer phải có **phản hồi nghiệp vụ hoặc cơ chế đối soát**, không thể chỉ nhìn publisher confirm ACK.

## 7. Durable queue, persistent message và bảo đảm giao nhận

Độ tin cậy phụ thuộc cả topology, message properties, broker, producer lẫn consumer:

- Exchange, queue và binding có tồn tại đúng không?
- Queue durable và loại queue/broker policy có đáp ứng mục tiêu chịu lỗi không?
- Message có **delivery mode persistent** khi cần lưu bền không?
- Publisher có theo dõi confirms và returns không?
- Consumer ACK ở thời điểm phù hợp chưa, có khả năng redelivery không?
- Có idempotency và checkpoint phục hồi sau restart không?

**Durable queue** không tự làm mọi message trở thành persistent, không ngăn producer publish sai routing key và không bảo đảm exactly-once end-to-end. Kiểm tra cấu hình delivery mode của converter/template thay vì suy diễn từ kiểu payload String hay DTO.

Với quorum queue hoặc chính sách bền vững khác, cần xét yêu cầu cụm RabbitMQ, throughput, khả năng khôi phục và cách triển khai. Một lựa chọn queue tốt vẫn không thay thế kiểm soát tác động nghiệp vụ trùng lặp.

## 8. Lỗi outbound, retry và trạng thái gửi không rõ

Một lần publish có thể thất bại hoặc không rõ kết quả vì những lý do khác nhau. Không nên retry tất cả lỗi bằng cùng một chính sách:

| Giai đoạn | Lỗi ví dụ | Phản ứng nên thiết kế |
| --- | --- | --- |
| **Trước gửi** | DTO serialize lỗi, schema không hợp lệ, message quá lớn | Cách ly, sửa dữ liệu/hợp đồng; retry đơn thuần không chữa được |
| **Kết nối** | RabbitMQ không sẵn sàng, DNS/TLS lỗi, không đủ quyền | Retry có giới hạn và backoff; cảnh báo vấn đề cấu hình |
| **Định tuyến** | Exchange thiếu, routing key không match binding | Kiểm tra topology; dùng publisher returns cho unroutable |
| **Broker xử lý publish** | Publisher confirm NACK hoặc channel bị đóng | Lưu trạng thái gửi lỗi; cân nhắc retry theo chính sách |
| **Không nhận confirm** | Broker có thể đã nhận trước khi network timeout | Ghi trạng thái UNKNOWN, đối soát và retry với eventId ổn định |
| **Phía nhận xử lý lỗi** | Consumer parse sai, DB deadlock | Retry/requeue/DLQ ở consumer; producer không tự sửa lỗi đó |

### 8.1. Retry không bảo đảm chỉ gửi một lần

Giả sử producer publish event **evt-1001** thành công nhưng mất kết nối trước khi nhận publisher confirm. Ứng dụng thấy timeout, retry ngay và broker có thể nhận cùng event lần thứ hai.

Giải pháp quan trọng là giữ **eventId ổn định**, ví dụ evt-1001, và dùng **idempotent consumer**: lưu eventId đã xử lý cùng kết quả nghiệp vụ hoặc dùng unique constraint/inbox table. Không tạo eventId mới mỗi khi retry, không dùng MessageHeaders.ID mới làm khóa chống trùng duy nhất.

**Retry** nghĩa là thử lại một thao tác có thể thất bại. **Idempotency** nghĩa là việc thử lại không tạo tác động nghiệp vụ trùng. Hai cơ chế cần bổ trợ nhau.

### 8.2. Trạng thái UNKNOWN cần được thừa nhận

Khi không biết chắc broker đã nhận hay chưa, không nên ép sự kiện vào duy nhất hai trạng thái SUCCESS/FAILED. Một thiết kế outbox có thể dùng các trạng thái ứng dụng như:

~~~text
NEW -> SENDING -> CONFIRMED
           |       |
           |       +-- (chờ xử lý nghiệp vụ riêng)
           |
           +--> RETRYABLE_ERROR
           +--> PERMANENT_ERROR
           +--> UNKNOWN -> đối soát hoặc gửi lại idempotent
~~~

Đây là các nhãn **do ứng dụng tự thiết kế**, không phải enum mặc định Spring Integration. Tùy SLA, có thể lưu thời điểm gửi cuối, số lần retry, lỗi cuối cùng, eventId, exchange và routing key để điều tra.

### 8.3. Retry có giới hạn và backoff

- Chỉ retry khi có khả năng hồi phục, ví dụ broker tạm thời không kết nối được.
- Dùng backoff và có thể thêm jitter để tránh đồng loạt retry sau sự cố.
- Với sai schema, không đủ quyền hoặc routing không tồn tại, cần cảnh báo và sửa đúng nguyên nhân.
- Sau khi hết số lần retry, giữ event trong nơi lưu trạng thái bền vững để vận hành có thể xử lý tiếp.
- Đảm bảo publisher confirm/return và các lỗi bất đồng bộ có đường xử lý riêng, không chỉ bắt exception trong phương thức gọi send().

### 8.4. DLQ không tự nhận mọi lỗi publish

**Dead-letter exchange/queue** ở RabbitMQ chủ yếu phục vụ những trường hợp message đã vào queue rồi bị reject/nack không requeue, quá hạn TTL hoặc bị dead-letter theo chính sách khác. Nếu outbound adapter **không thể publish vào exchange**, hoặc message bị **unroutable**, bản tin chưa chắc đã vào một queue để cơ chế DLQ đó xử lý.

Vì vậy cần tách hai câu hỏi:

1. **Producer không publish được:** lưu ở outbox/error store, retry/alert theo chính sách producer.
2. **Consumer không xử lý được delivery:** dùng retry, requeue, DLX/DLQ và idempotency theo chính sách consumer.

~~~mermaid
flowchart TD
    E["Event chờ publish"] --> V{"Payload/route hợp lệ?"}
    V -- "Không" --> BAD["Cách ly và sửa hợp đồng"]
    V -- "Có" --> PUB["AMQP outbound publish"]
    PUB --> C{"Confirm / return / timeout"}
    C -- "ACK và không return" --> OK["Đạt mốc broker theo cấu hình"]
    C -- "Returned unroutable" --> RT["Sửa binding hoặc routing"]
    C -- "NACK hoặc lỗi tạm thời" --> RET["Retry có giới hạn"]
    C -- "UNKNOWN" --> UN["Đối soát + eventId ổn định"]
    RET --> PUB
~~~

Ngay cả nhánh **ACK và không return** vẫn chưa chứng minh consumer đã xử lý xong nghiệp vụ.

## 9. Giao dịch database và transactional outbox

Một bài toán phổ biến: ứng dụng ghi đơn hàng vào database rồi gửi AMQP event. Đây là hai tài nguyên độc lập, nên có các tình huống:

1. Database commit thành công nhưng ứng dụng chết **trước lúc publish**: hệ thống bên nhận không biết đơn hàng mới.
2. Publish thành công nhưng producer chết **trước khi ghi trạng thái đã gửi**: lần chạy lại có thể gửi lại event.
3. Broker nhận event nhưng publisher **không nhận confirm**: trạng thái gửi không chắc chắn.

**Transactional outbox** là mẫu phù hợp khi sự kiện cần gắn với thay đổi nghiệp vụ:

~~~mermaid
flowchart LR
    S["OrderService"] --> TX["Database transaction"]
    TX --> O["Orders table"]
    TX --> OB["Outbox events"]
    OB --> W["Outbox worker<br/>retry + trạng thái"]
    W --> C["MessageChannel"]
    C --> A["AMQP outbound adapter"]
    A --> MQ["RabbitMQ"]
    MQ --> I["Idempotent consumer"]
~~~

Trong cùng transaction database, hệ thống ghi Order và bản ghi OutboxEvent (ví dụ eventId, payload, event type, schemaVersion). Worker đọc outbox, chuyển vào MessageChannel và phát qua outbound adapter. Worker lưu kết quả publish theo mốc xác nhận đã cam kết; khi lỗi, nó có thể thử lại.

**Outbox không tạo một giao dịch nguyên tử giữa database và RabbitMQ.** Nó giúp giảm khoảng trống “DB đã commit nhưng event chưa được ghi nhận để phát”, đồng thời cung cấp cơ sở phục hồi. Consumer phía nhận **vẫn phải idempotent** vì publish có thể lặp do crash/timeout.

### 9.1. Bao giờ không cần outbox?

Không phải luồng nào cũng cần mẫu này. Nếu sự kiện mang tính best-effort và mất một vài thông báo có thể chấp nhận, cơ chế gửi trực tiếp đơn giản hơn có thể đáp ứng. Nhưng với nghiệp vụ tài chính, tồn kho, đơn hàng hoặc audit có ràng buộc dữ liệu, cần ghi rõ yêu cầu **không mất sự kiện**, **không tạo side effect trùng** và cách kiểm chứng trước khi bỏ qua outbox.

### 9.2. Transaction của RabbitTemplate có thay thế outbox không?

Spring AMQP và RabbitMQ có hỗ trợ những cơ chế giao dịch/xác nhận của riêng chúng, nhưng transaction của broker **không mặc nhiên** bao phủ transaction của database hoặc HTTP/SFTP/Kafka. Phải xác định đúng phạm vi từng tài nguyên và thứ tự commit. Không tuyên bố exactly-once end-to-end chỉ vì bật một cờ transaction.

## 10. MessageChannel quyết định cách adapter được kích hoạt

AMQP outbound adapter là **consumer của MessageChannel**. Loại channel ảnh hưởng độ trễ, khả năng chịu tải và đường lỗi:

| Channel | Cơ chế | Điều cần cân nhắc với AMQP outbound |
| --- | --- | --- |
| **DirectChannel** | Subscriber chạy đồng bộ trên luồng gửi | Lỗi RabbitTemplate đồng bộ có thể lan ngược; publish chậm giữ caller |
| **ExecutorChannel** | Giao việc cho thread pool | Producer có thể được trả về sớm; lỗi publish xuất hiện ở thread khác |
| **QueueChannel** | Lưu message cho polling consumer lấy | Cần poller, capacity, xử lý khi queue đầy và độ bền sau restart |
| **PublishSubscribeChannel** | Phân phát đến nhiều subscriber | Một nhánh outbound có thể thành công khi nhánh khác thất bại |

### 10.1. DirectChannel trong ví dụ

Khi OrderEventPublisher gọi send(), DirectChannel thường gọi AMQP outbound handler trên cùng luồng. Nếu chuyển đổi hoặc publish ném exception ngay, caller có thể quan sát lỗi. Nhưng **publisher confirm hoặc return có thể được nhận sau**, không nằm trong cùng kết quả boolean của send().

### 10.2. QueueChannel và poller ở phía outbound

Nếu muốn điều tiết tốc độ gửi theo nhịp, có thể đặt **QueueChannel** trước outbound endpoint rồi dùng **polling consumer** lấy message để publish:

~~~mermaid
flowchart LR
    P["Producer"] --> Q["QueueChannel"]
    POL["Poller của consumer"] -.-> Q
    Q --> A["AMQP outbound adapter"]
    A --> R["RabbitMQ"]
~~~

Poller này **lấy message đã có từ channel nội bộ**; nó không phải AMQP inbound polling. RabbitMQ producer được gọi khi endpoint consumer nhận được message.

**QueueChannel mặc định dùng bộ nhớ**, không phải hàng đợi lưu bền. Nếu tiến trình chết trước publish, những message chờ có thể mất. Dùng MessageStore bền vững, outbox hoặc broker ngoài nếu yêu cầu chịu lỗi cao.

### 10.3. Không dùng concurrency để che giấu nghẽn tải

Nếu business flow tạo 1.000 event/giây nhưng RabbitMQ hoặc network chỉ xử lý 100 event/giây, việc tăng executor vô hạn có thể chỉ làm tăng backlog, memory và timeout. Cần giới hạn:

- Số publish đồng thời, queue capacity và thời gian chờ.
- Kích thước payload, serializer cost và giới hạn kết nối/channel.
- Nhịp retry/backoff khi broker không khả dụng.
- Khả năng consumer xử lý backlog sau khi publisher phục hồi.

RabbitMQ có thể duy trì trật tự message trong queue ở những điều kiện nhất định nhưng **thứ tự xử lý nghiệp vụ** có thể thay đổi khi có nhiều publishers/consumers, retry, priority hoặc requeue. Nếu cần thứ tự theo orderId, hãy dùng version/sequence và chính sách xử lý phù hợp thay vì chỉ tin vào một queue.

## 11. Routing đến một hay nhiều hệ thống

### 11.1. Một queue, nhiều competing consumers

Khi nhiều consumer cùng consume **một queue**, broker thường phân phối delivery để chia tải. Chúng **không mặc nhiên mỗi bên đều nhận một bản sao**. Trường hợp này thích hợp để scale out nhiều instance của cùng một worker.

### 11.2. Một event, nhiều hệ thống độc lập

Nếu warehouse và notifications đều cần mọi OrderCreated, hãy tạo hai queue và bind cả hai vào exchange theo quy tắc phù hợp:

~~~mermaid
flowchart TD
    P["AMQP outbound adapter"] --> X["orders.events"]
    X -->|"orders.created"| WQ["warehouse.orders.q"]
    X -->|"orders.created"| NQ["notifications.orders.q"]
    WQ --> W["Warehouse inbound consumer"]
    NQ --> N["Notifications inbound consumer"]
~~~

Mỗi queue có backlog, retry, consumer ACK và DLQ riêng. Producer chỉ cần publish một sự kiện với exchange/routing key theo hợp đồng.

### 11.3. Routing key tĩnh hay động?

**Routing key tĩnh** như orders.created dễ kiểm thử và quản lý khi mỗi flow publish một loại sự kiện. Routing key động có thể cần khi có nhiều eventType, tenant hoặc vùng, nhưng cần quy định giá trị hợp lệ, topic/binding tương ứng và cách xử lý message không route. Không tạo routing key tùy tiện từ input không tin cậy.

## 12. Vòng đời kết nối, bảo mật và giám sát

AMQP outbound adapter thường phụ thuộc RabbitTemplate, ConnectionFactory và các kết nối/channel của RabbitMQ client. Nhiều endpoint Spring Integration tham gia cơ chế **Lifecycle/SmartLifecycle**, nhưng **endpoint đang running** không đồng nghĩa broker đang sẵn sàng hoặc mọi publish đã được confirmed.

### 12.1. Những yếu tố vận hành chính

| Nhóm | Cần thiết kế hoặc theo dõi |
| --- | --- |
| **Kết nối** | Host, port, virtual host, timeout, reconnect, pooled channels |
| **Bảo mật** | TLS, kiểm tra chứng chỉ, tài khoản tối thiểu quyền, secret rotation |
| **Topology** | Exchange/queue/binding đã được provision; quyền declare/publish |
| **Producer** | Publish attempts, exceptions, confirms ACK/NACK, returned messages |
| **Broker** | Publish rate, route rate, queue ready/unacked, connection/channel count |
| **Nghiệp vụ** | EventId đã phát, trạng thái outbox, số event consumer xử lý thực sự |
| **Hiệu năng** | Publish latency, confirm latency, retries, backlog age |
| **Lỗi** | Unroutable, timeout, lỗi converter, lỗi permission, UNKNOWN |

Không ghi credential và payload nhạy cảm nguyên văn vào log. Hãy dùng eventId/correlationId, tên endpoint, exchange/routing key đã kiểm soát và mã lỗi để truy vết.

### 12.2. Start, stop và graceful shutdown

Một lần dừng ứng dụng an toàn thường cần:

1. Ngừng tạo thêm công việc publish mới.
2. Ghi nhận hoặc duy trì trạng thái event đang chờ trong outbox/hàng đợi bền vững.
3. Theo dõi các publish đang in-flight và kết quả confirm theo SLA.
4. Dừng outbound consumer và tài nguyên dùng chung theo thứ tự phù hợp.
5. Khởi động lại từ trạng thái đã lưu, không dựa vào bộ nhớ tiến trình.

**stop() không đồng nghĩa đã drain thành công mọi message đang gửi**, và dừng một endpoint không nhất thiết tự đóng ConnectionFactory dùng chung cho các flow khác. Nếu trước AMQP outbound còn có HTTP/JMS/Kafka/SFTP hoặc database endpoint, cần phân tích thời điểm ACK/commit phía trước trước khi cho caller tin rằng publish đã hoàn tất.

## 13. Kịch bản tích hợp: OrderService → RabbitMQ → hai consumer

Một ứng dụng cần phát OrderCreated cho kho và dịch vụ thông báo. Các điều kiện:

- Order được lưu thành công phải có sự kiện tương ứng để phát.
- RabbitMQ có thể tạm dừng; ứng dụng phải gửi lại an toàn.
- Hai hệ thống nhận đầy đủ sự kiện độc lập.
- Consumer không thực thi nghiệp vụ hai lần khi event được giao lại.

Thiết kế tham khảo:

~~~mermaid
flowchart TD
    S["OrderService"] --> TX["Database transaction"]
    TX --> O["Orders"]
    TX --> OB["OutboxEvent: evt-1001"]
    OB --> W["Outbox publishing worker"]
    W --> C["ordersToAmqp"]
    C --> A["AMQP outbound adapter"]
    A --> X["orders.events exchange"]
    X --> WQ["warehouse.orders.q"]
    X --> NQ["notifications.orders.q"]
    WQ --> WC["Warehouse idempotent consumer"]
    NQ --> NC["Notification idempotent consumer"]
    A -. "Confirm/return/trạng thái" .-> W
~~~

Những quyết định phải được ghi trong thiết kế:

1. **Event identity:** eventId ổn định qua các lần retry, schemaVersion cụ thể.
2. **Routing topology:** hai queue và bindings, quyền publish/consume của từng dịch vụ.
3. **Producer tracking:** ACK/NACK, return, timeout, UNKNOWN và cách cập nhật outbox.
4. **Consumer processing:** inbox/unique constraint để tránh side effect trùng.
5. **Failure policy:** lỗi schema đi vào nơi cách ly; lỗi kết nối retry có giới hạn.
6. **Observability:** đối chiếu outbox confirmed với business outcome tại warehouse và notifications.

Như vậy, một lần **AMQP outbound publish thành công** không phải đồng nghĩa hai consumer đã hoàn thành. Mỗi hệ thống có tiến độ và đường lỗi của riêng mình.

## 14. Bộ kiểm thử cần có trước production

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Đúng exchange/binding | Message đến queue đích qua AMQP outbound adapter |
| Sai routing key | Cơ chế mandatory/returns phát hiện unroutable |
| Broker không sẵn sàng | Không đánh dấu event hoàn tất sai; có retry/alert |
| Publisher confirm | ACK/NACK được gắn đúng lần publish và eventId |
| Broker nhận nhưng consumer chậm | Không nhầm confirm ACK với business completion |
| Payload không hợp lệ | Converter/validator phát hiện và cách ly |
| Duplicate eventId | Consumer không tạo side effect trùng |
| Nhiều queue một exchange | Hai hệ thống đều nhận event khi binding phù hợp |
| Nhiều worker trên cùng queue | Competing consumer, không mặc nhiên broadcast |
| Restart producer | Event chưa xác nhận được phục hồi theo outbox |
| Network timeout sát confirm | Có xử lý UNKNOWN và retry idempotent |
| Tải đỉnh | Theo dõi confirm latency, rate, backlog, timeout và memory |
| Shutdown giữa publish | Không dựa vào QueueChannel trong bộ nhớ cho dữ liệu bắt buộc lưu bền |

### 14.1. Ba bài thử đặc biệt quan trọng

**Unroutable:** Trong test, publish vào exchange hợp lệ với routing key không match binding. Quan sát **return** khi mandatory được bật. Không kết luận route thành công chỉ từ confirm ACK.

**Trạng thái không rõ:** Ngắt kết nối sau khi broker có thể đã nhận publish nhưng trước khi producer nhận confirm. Kiểm tra worker lưu UNKNOWN hoặc chưa xác nhận, và retry giữ eventId ổn định.

**Khởi động lại và xử lý trùng:** Gửi lại một eventId đã được consumer ghi thành công. Xác minh inbox hoặc unique constraint bảo vệ side effect.

## 15. Sai lầm thường gặp

**Nhầm RabbitMQ queue với Spring MessageChannel.** Channel nằm trong ứng dụng; queue nằm trong broker, hai nơi có bảo đảm lưu trữ và cơ chế chuyển giao khác nhau.

**Cho rằng producer gửi trực tiếp vào queue trong mọi trường hợp.** RabbitMQ publish tới exchange. Với default exchange, routing key có thể là tên queue, nhưng không nên khái quát thành mọi topology.

**Nhầm publisher confirm ACK với consumer ACK.** Hai cơ chế thuộc hai chiều giao tiếp khác nhau; không cơ chế nào tự đóng vai trò business reply.

**Không xử lý returned messages.** Một bản publish có thể được exchange xác nhận nhưng không đến queue nào vì routing không phù hợp.

**Dùng send() để đánh dấu chắc chắn sự kiện đã được mọi consumer xử lý.** Kết quả gửi vào channel và xác nhận broker chỉ là các mốc trung gian.

**Coi durable queue là bảo đảm exactly-once.** Cần xem persistence, broker policy, producer confirms, consumer ACK và idempotency.

**Retry vô hạn khi sai schema, thiếu exchange hoặc không đủ quyền.** Các lỗi này thường cần sửa hợp đồng/cấu hình trước khi gửi lại.

**Dùng MessageHeaders.ID làm eventId nghiệp vụ.** Một message được dựng lại có thể có ID mới dù vẫn là cùng sự kiện; dùng eventId ổn định.

**Đẩy DTO Java không có hợp đồng serializer.** Consumer khác ngôn ngữ hoặc phiên bản không chắc giải mã được; định nghĩa wire format và version.

**Cho rằng DLQ ở consumer sẽ giữ lại mọi lỗi publish.** Lỗi producer, unroutable và message đã vào queue là những tình huống khác nhau.

**Xem QueueChannel trong bộ nhớ như outbox.** Khi tiến trình chết, message chờ có thể mất; chọn nguồn lưu bền khi cần.

**Cho rằng nhiều consumer trên một queue sẽ nhận cùng mọi event.** Chúng thường chia delivery để xử lý song song; fan-out cần topology nhiều queue.

## 16. Câu hỏi tự kiểm tra

1. Một event đi từ OrderService qua MessageChannel, AMQP outbound adapter và RabbitTemplate tới RabbitMQ theo những bước nào?
2. Exchange, routing key, binding và queue khác nhau ở điểm nào?
3. AMQP outbound channel adapter khác outbound gateway ra sao? Trường hợp nào cần gateway?
4. Điều gì thực sự được chứng minh khi MessageChannel.send() trả về thành công?
5. Vì sao publisher confirm ACK không bảo đảm message đã route vào đúng queue? Khi nào dùng mandatory và returns?
6. Producer confirm, publisher return và consumer ACK do những bên nào phát ra?
7. Payload String được chuyển thành AMQP body như thế nào? Khi phát DTO JSON, cần hợp đồng gì?
8. Vì sao eventId phải giữ ổn định giữa các lần retry và khác MessageHeaders.ID?
9. Nếu broker có thể đã nhận nhưng ứng dụng timeout trước confirm, cần trạng thái và cách phục hồi nào?
10. Queue durable có giúp bỏ qua idempotent consumer được không? Vì sao?
11. Nếu kho và thông báo đều cần OrderCreated, phải thiết kế exchange/queue/binding như thế nào?
12. Chuyển DirectChannel sang ExecutorChannel thay đổi đường báo lỗi và thời điểm producer được trả về ra sao?
13. Vì sao dead-letter queue của consumer không tự cứu được mọi lỗi publish của producer?
14. Tại sao transactional outbox thường được cân nhắc khi lưu database rồi publish AMQP?
15. Những metric nào cho biết producer lỗi routing, broker nghẽn hoặc consumer đang chậm?

## Tổng kết

**AMQP outbound channel adapter** là cầu nối một chiều từ **Spring Integration MessageChannel** sang **RabbitTemplate**, qua **RabbitMQ exchange** để định tuyến vào những queue phù hợp. Thiết kế đúng phải xác định rõ payload, MessageConverter, properties, routing key, độ bền message và phân biệt **send vào channel**, **publisher confirm**, **publisher return**, **message đã vào queue** và **consumer ACK**. Những mốc này không thể thay thế kết quả nghiệp vụ cuối cùng. Trong hệ thống tích hợp File, SFTP, HTTP, JMS, AMQP, Kafka và database, nên dùng retry có giới hạn, eventId ổn định, idempotent consumer, outbox khi cần, quan sát toàn luồng và quản lý vòng đời kết nối để phát sự kiện an toàn.
