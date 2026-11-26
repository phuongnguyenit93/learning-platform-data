# Publish chưa có confirm và delivery chưa ack khi mất kết nối

Trong hệ thống dùng **RabbitMQ và Spring AMQP**, mất kết nối có thể xảy ra ngay giữa một thao tác gửi message hoặc xử lý message. Hai trường hợp đặc biệt nguy hiểm là:

1. **Producer đã gửi lệnh publish nhưng chưa nhận publisher confirm.** Không thể biết chắc broker đã lưu message hay chưa.
2. **Broker đã giao message cho consumer nhưng chưa ghi nhận ACK.** Khi channel/connection mất và broker phát hiện sự cố, message chưa được xác nhận có thể được giao lại.

Hai hiện tượng này thường dẫn đến **message trùng lặp**, dù ứng dụng đã cấu hình reconnect tự động. Nếu ứng dụng xử lý sai kết quả không xác định, nó còn có thể **làm mất message** hoặc ghi nhận trạng thái nghiệp vụ sai.

Bài này thuộc chương **Phục hồi kết nối** của module **SPRING_AMQP**. Ta sử dụng `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding, publisher confirms, consumer acknowledgments, retry và dead-letter để nhận diện hai cửa sổ lỗi, thiết kế phục hồi an toàn và kiểm chứng bằng các kịch bản ngắt kết nối thực tế.

## 1. Hai chiều truyền tin, hai loại ACK khác nhau

RabbitMQ sử dụng các cơ chế xác nhận với mục đích và phạm vi khác nhau:

| Xác nhận | Hướng | Cho biết điều gì? | Không bảo đảm điều gì? |
|---|---|---|---|
| **Publisher confirm** | Broker → producer | Broker đã xử lý publish ở mức được cam kết bởi loại queue và cấu hình liên quan; có ACK hoặc NACK | Consumer đã nhận, xử lý hoặc ACK |
| **Publisher return** | Broker → producer | Message không thể định tuyến tới queue khi publish với cờ `mandatory` | Broker đã lưu hoặc consumer đã xử lý |
| **Consumer ACK** | Consumer → broker | Consumer xác nhận delivery được xử lý thành công theo hợp đồng của ứng dụng | Producer nhận biết được việc xử lý, hoặc tác dụng nghiệp vụ hoàn toàn không thể lặp |
| **Consumer NACK/reject** | Consumer → broker | Consumer không xử lý thành công và chọn requeue hoặc reject | Bảo đảm retry sẽ có độ trễ, giới hạn số lần, hay đi tới DLQ nếu chưa cấu hình |

**Publisher ACK** và **consumer ACK** là hai sự kiện khác nhau. Publisher confirm dùng thông tin xác nhận theo **channel của publisher**; consumer ACK dùng **delivery tag trên channel nhận message**. Không thể so sánh hoặc sử dụng chéo hai loại tag.

Một vòng đời đơn giản:

~~~mermaid
sequenceDiagram
    participant P as Producer (RabbitTemplate)
    participant B as RabbitMQ
    participant C as Consumer (@RabbitListener)
    participant D as Database
    P->>B: basic.publish(eventId=e1)
    B-->>P: publisher confirm ACK
    B->>C: basic.deliver(e1, deliveryTag=7)
    C->>D: Ghi nghiệp vụ
    D-->>C: COMMIT
    C->>B: basic.ack(tag=7)
~~~

Trong thực tế, kết nối có thể đứt **trước hoặc sau** một trong hai đường xác nhận. Chương trình không được mặc nhiên suy ra “message chưa gửi” chỉ vì chưa thấy publisher confirm, cũng không được suy ra “message sẽ không được giao lại” chỉ vì consumer đã gọi `basicAck`.

## 2. Cửa sổ lỗi của publish đang chờ confirm

Hãy xét producer gửi `OrderCreated(eventId=e1)` và chờ correlated publisher confirm:

~~~text
T0  Producer tạo message e1
T1  Producer gọi RabbitTemplate.send(...)
T2  Lệnh basic.publish đang đi qua mạng
T3  Broker có thể đã nhận, route và lưu message e1
T4  Broker gửi publisher confirm
T5  Producer nhận confirm
~~~

Nếu connection mất **giữa T1 và T5**, producer có thể thấy timeout, exception hoặc completion báo lỗi do channel bị đóng. Nhưng riêng việc **không nhận được confirm** không chứng minh broker chưa nhận message.

~~~mermaid
flowchart TD
    P["Producer gửi e1"] --> L["Mất kết nối trước khi nhận confirm"]
    L --> A{"Broker đã xử lý publish?"}
    A -->|Chưa| U["e1 chưa có ở broker"]
    A -->|Rồi| V["e1 có thể đã nằm trong queue"]
    U --> R["Producer không biết chắc kết quả"]
    V --> R
    R --> X["Giữ ý định gửi bền vững, retry e1"]
    X --> Y["Có thể tạo duplicate nếu lần trước đã đến broker"]
    Y --> Z["Consumer idempotent theo eventId"]
~~~

### 2.1. Ba kết quả phải phân biệt

| Kết quả quan sát ở producer | Có thể kết luận | Hành động gợi ý |
|---|---|---|
| Nhận **confirm ACK**, message không bị return khi `mandatory` | Broker đã xác nhận publish và message đã được route theo hợp đồng | Có thể ghi trạng thái gửi thành công; consumer vẫn xử lý độc lập |
| Nhận **confirm NACK** hoặc publisher return | Publish không thành công hoặc không đến queue đích như mong đợi | Ghi nhận thất bại, kiểm tra topology, retry theo chính sách |
| **Timeout, connection reset, channel closed trước confirm** | **Không xác định** broker đã nhận hay chưa | Không đánh dấu thành công; giữ event và gửi lại sau; chấp nhận khả năng duplicate |

Với `mandatory=true`, một message không route được có thể được **return** nhưng vẫn có publisher confirm ACK vì broker đã xử lý lệnh publish. Do đó, **confirm ACK một mình không đủ chứng minh message tới queue đích**.

Mất kết nối sau khi broker đã xử lý publish nhưng trước khi producer nhận ACK thường là tình huống gây duplicate:

~~~text
Lần 1:
  Producer gửi e1 ----- RabbitMQ nhận và lưu e1
  Publisher confirm ACK ----X---- producer không nhận được

Lần 2 sau reconnect:
  Producer gửi lại e1 ----- RabbitMQ nhận và lưu thêm e1

Consumer có thể nhận 2 delivery mang cùng eventId=e1.
~~~

Đừng tạo `eventId` mới mỗi khi gửi lại **cùng một sự kiện nghiệp vụ**. Nên dùng **eventId ổn định** để downstream phát hiện duplicate, đồng thời dùng một **correlation ID riêng cho từng lần publish attempt** để nối confirm với đúng attempt.

### 2.2. Confirm được nhận cũng có giới hạn

Publisher confirm phản ánh việc broker chấp nhận publish theo loại queue và điều kiện durability tương ứng. Với thông điệp cần chịu được broker restart, thường phải kết hợp:

- **Durable exchange**, **durable queue** và binding chính xác.
- Message có **persistent delivery mode**.
- Queue type/cluster topology và khả năng chịu lỗi theo mục tiêu của hệ thống.
- Publisher confirms/returns, xử lý timeout và giám sát đầy đủ.

Confirm **không có nghĩa mọi consumer đã nhận message** và cũng không tạo giao dịch nguyên tử giữa RabbitMQ với database bên producer.

## 3. Cấu hình RabbitTemplate để nhìn thấy trạng thái publish

Spring Boot có thể bật correlated confirms và returns bằng cấu hình:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Ví dụ khai báo một exchange, queue và binding:

~~~java
import org.springframework.amqp.core.*;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;

@Configuration
public class OrderMessagingTopology {
    public static final String EXCHANGE = "orders.events.x";
    public static final String QUEUE = "orders.created.q";
    public static final String ROUTING_KEY = "orders.created";
    public static final String PARKING_EXCHANGE = "orders.parking.x";
    public static final String PARKING_QUEUE = "orders.parking.q";
    public static final String PARKING_KEY = "orders.parking";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue ordersQueue() {
        return QueueBuilder.durable(QUEUE)
                .deadLetterExchange(PARKING_EXCHANGE)
                .deadLetterRoutingKey(PARKING_KEY)
                .build();
    }

    @Bean
    DirectExchange parkingExchange() {
        return new DirectExchange(PARKING_EXCHANGE, true, false);
    }

    @Bean
    Queue parkingQueue() {
        return QueueBuilder.durable(PARKING_QUEUE).build();
    }

    @Bean
    Binding parkingBinding(
            @Qualifier("parkingQueue") Queue queue,
            @Qualifier("parkingExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue).to(exchange).with(PARKING_KEY);
    }

    @Bean
    Binding ordersBinding(
            @Qualifier("ordersQueue") Queue queue,
            @Qualifier("ordersExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue).to(exchange).with(ROUTING_KEY);
    }
}
~~~

Ví dụ cấu hình thêm **parking queue** để listener có thể reject message lỗi với `requeue=false` mà vẫn giữ message để điều tra. Parking queue ở đây **không có đường tự động quay về queue chính**; nếu muốn retry tạm thời, cần thiết kế thêm vòng TTL/DLX có giới hạn số lần. Việc queue có tồn tại tại thời điểm publish hay không vẫn phụ thuộc quá trình khai báo topology và quyền truy cập broker. Trong Spring AMQP, `RabbitAdmin` có thể khai báo lại exchange/queue/binding khi kết nối được thiết lập, nhưng **không thay thế việc kiểm tra cấu hình thực tế và quyền khai báo**.

Producer gửi một event với ID nghiệp vụ ổn định:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class ConfirmedOrderPublisher {
    private final RabbitTemplate rabbitTemplate;

    public ConfirmedOrderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishOnce(UUID eventId, String jsonPayload) throws Exception {
        MessageProperties properties = new MessageProperties();
        properties.setMessageId(eventId.toString());
        properties.setContentType(MessageProperties.CONTENT_TYPE_JSON);
        properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);

        Message message = new Message(
                jsonPayload.getBytes(StandardCharsets.UTF_8), properties);

        // Mỗi attempt có correlation ID riêng; eventId vẫn giữ nguyên.
        CorrelationData correlation =
                new CorrelationData(UUID.randomUUID().toString());

        rabbitTemplate.send(
                OrderMessagingTopology.EXCHANGE,
                OrderMessagingTopology.ROUTING_KEY,
                message,
                correlation);

        CorrelationData.Confirm confirm =
                correlation.getFuture().get(10, TimeUnit.SECONDS);

        if (!confirm.isAck() || correlation.getReturned() != null) {
            throw new IllegalStateException("Publish không được xác nhận/route");
        }
    }
}
~~~

Đoạn mã dùng API `CorrelationData.getFuture()` để chờ kết quả. Khi timeout hoặc connection lỗi, phương thức có thể ném exception. **Caller phải lưu trạng thái “cần gửi” một cách bền vững trước khi gọi** nếu không được phép mất sự kiện: giữ payload trong biến hoặc retry ngay trong RAM không đủ khi ứng dụng bị dừng đột ngột.

Khi bắt exception từ `publishOnce`, **không mặc định xóa bản ghi sự kiện, cũng không khẳng định broker chưa nhận**. Để gửi lại một cách an toàn, nên đọc từ outbox và thử lại với cùng `eventId`; sau khi confirm ACK và không bị return, mới cập nhật trạng thái đã gửi.

### 3.1. Không chờ confirm trên đường xử lý nhạy latency khi không cần

Ví dụ trên chờ tối đa 10 giây để minh họa cách xác nhận. Nếu hàng nghìn message được gửi liên tiếp, chờ từng confirm sẽ làm giảm throughput. Khi thông lượng cao, có thể dùng callback/`CompletableFuture` của confirm để theo dõi **nhiều publish in-flight**, giới hạn số attempt đồng thời và chỉ đánh dấu từng outbox row khi kết quả tương ứng được xác nhận. Dù dùng cách nào, timeout vẫn là kết quả **không xác định**, không được xem là “publish chắc chắn thất bại”.

## 4. Mất kết nối sau delivery nhưng trước consumer ACK

Tình huống thứ hai xảy ra ở chiều ngược lại. Broker giao một message cho consumer, consumer bắt đầu chạy nghiệp vụ và chưa gửi hoặc chưa được broker ghi nhận `basicAck`.

~~~text
T0  RabbitMQ gửi basic.deliver(e1, tag=15)
T1  Listener nhận e1
T2  Listener gọi database / API
T3  Database có thể đã COMMIT tác dụng nghiệp vụ
T4  Listener gửi basicAck(tag=15)
T5  Broker ghi nhận ACK
~~~

Nếu channel/connection đóng **trước T5**, broker có thể phát lại message chưa được xác nhận. Broker không biết chính xác transaction nghiệp vụ ở database đã thành công hay chưa.

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant C1 as Consumer cũ
    participant DB as Database
    participant C2 as Consumer sau recovery
    B->>C1: delivery e1, tag=15
    C1->>DB: INSERT/UPDATE theo e1
    DB-->>C1: COMMIT thành công
    Note over C1,B: Connection mất trước khi ACK được ghi nhận
    B--xC1: Channel đóng; unacked delivery được requeue
    B->>C2: redelivery e1, tag=1 (channel mới)
    C2->>DB: applyOnce(e1)
    DB-->>C2: Đã xử lý e1; không thực hiện lại
    C2->>B: basicAck(tag=1)
~~~

Trong ví dụ, `tag=15` trên channel cũ và `tag=1` trên channel mới là **hai delivery tag khác nhau** cho cùng event. Delivery tag chỉ hợp lệ trên channel mà broker cấp nó. **Không sử dụng tag của channel trước khi reconnect để ACK trên channel mới**.

### 4.1. Broker sẽ làm gì với delivery chưa ACK?

- Với delivery ở chế độ cần ACK thủ công hoặc ACK bởi container sau xử lý, broker theo dõi trạng thái **unacked** trên channel.
- Khi broker **phát hiện channel/connection đã đóng**, các delivery còn unacked có thể được **requeue và giao lại** cho consumer đang hoạt động hoặc consumer khôi phục.
- Nếu kết nối chỉ **tạm gián đoạn mà broker chưa phát hiện**, broker có thể vẫn giữ unacked một thời gian. Heartbeat và cơ chế phát hiện kết nối lỗi ảnh hưởng độ trễ phục hồi.
- Message được requeue do channel đóng **không mặc nhiên đi qua DLX**, không tự tạo bản ghi `x-death` và không nhất thiết chờ theo retry/backoff.
- Khi được giao lại, cờ `redelivered` có thể cho biết message từng được giao, nhưng **không phải bộ đếm số lần** và không phải bằng chứng tác dụng nghiệp vụ đã hoặc chưa commit.

Một ACK có thể đã được producer hoặc consumer ghi ra socket trước khi connection lỗi, nhưng phía gửi không biết broker đã xử lý nó chưa. Với consumer ACK, lệnh `basicAck` không có phản hồi ACK thứ hai từ broker. Vì vậy, **ngay cả lời gọi `basicAck` trả về không thay thế idempotency**.

### 4.2. Giới hạn của AUTO và MANUAL acknowledgment

| Chế độ | Cách hoạt động thường gặp | Điều xảy ra nếu mất connection |
|---|---|---|
| `AcknowledgeMode.AUTO` của Spring AMQP | Container gửi ACK sau khi listener đồng bộ trả về thành công (hoặc sau completion của kiểu async được hỗ trợ) | Nếu broker chưa nhận ACK, message có thể redeliver |
| `AcknowledgeMode.MANUAL` | Ứng dụng tự `basicAck`/`basicNack` với delivery tag | Tag/channel cũ không thể tiếp tục được dùng khi đã đóng |
| `AcknowledgeMode.NONE` / broker auto-ack | Broker xem delivery đã được ACK ngay khi giao, không đợi xử lý nghiệp vụ | Nếu ứng dụng chết giữa xử lý, message có thể **mất** đối với consumer |

Trong workload phải bảo đảm xử lý nghiệp vụ, tránh auto-ack của broker nếu không chấp nhận mất message khi consumer chết. Tuy nhiên, ACK thủ công không tự tạo bảo đảm “xử lý đúng một lần”.

## 5. Vấn đề khó nhất: tác dụng nghiệp vụ đã xảy ra nhưng ACK chưa tới broker

Giả sử service thanh toán đã cộng điểm cho khách hàng, nhưng kết nối RabbitMQ mất trước khi ACK. Nếu broker giao lại message và listener lặp lại phép cộng, khách hàng bị cộng điểm hai lần.

**Giải pháp chính là idempotent consumer**, thường qua một bảng inbox hoặc unique business key. Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Ứng dụng có thể triển khai dịch vụ xử lý riêng:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IdempotentOrderService {
    private final ProcessedEventRepository inbox;
    private final OrderProjectionRepository projection;

    public IdempotentOrderService(
            ProcessedEventRepository inbox,
            OrderProjectionRepository projection) {
        this.inbox = inbox;
        this.projection = projection;
    }

    @Transactional
    public void applyOnce(UUID eventId, byte[] payload) {
        // INSERT ... ON CONFLICT DO NOTHING; false nếu đã xử lý.
        if (!inbox.insertIfAbsent("order-projection", eventId)) {
            return;
        }

        projection.apply(payload); // Ghi DB trong cùng transaction.
    }
}
~~~

`ProcessedEventRepository` và `OrderProjectionRepository` là các thành phần nghiệp vụ minh họa. Chúng phải dùng **cùng transaction database**, và khóa unique phải được database thực thi. Nếu `projection.apply(...)` thất bại, transaction rollback cả dấu vết inbox, cho phép lần giao lại thử xử lý. Nếu đã commit, lần nhận trùng sẽ không lặp lại tác dụng.

Listener dùng manual ACK để minh họa ranh giới sau khi DB commit:

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import java.util.UUID;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {
    private final IdempotentOrderService service;

    public OrderCreatedListener(IdempotentOrderService service) {
        this.service = service;
    }

    @RabbitListener(
            queues = OrderMessagingTopology.QUEUE,
            ackMode = "MANUAL")
    public void onMessage(Message message, Channel channel) throws IOException {
        long tag = message.getMessageProperties().getDeliveryTag();

        try {
            UUID eventId = UUID.fromString(
                    message.getMessageProperties().getMessageId());
            service.applyOnce(eventId, message.getBody());
        } catch (Exception ex) {
            // Không tự retry vô hạn: queue cần có DLX/retry hữu hạn.
            if (channel.isOpen()) {
                channel.basicNack(tag, false, false);
            }
            return;
        }

        // Thành công ở DB chưa đủ: broker còn phải nhận ACK.
        if (channel.isOpen()) {
            channel.basicAck(tag, false);
        }
    }
}
~~~

Ở đây, `UUID.fromString(...)` có thể lỗi nếu publisher không đặt message ID đúng chuẩn; message đó được NACK thay vì đánh dấu thành công. Topology phía trên đã cấu hình DLX tới `orders.parking.q`, nên `basicNack(tag, false, false)` chuyển message sang nơi cách ly. Phải có cơ chế phân loại lỗi và theo dõi poison message; nếu bổ sung retry tự động, cần giới hạn số lượt và phân biệt lỗi tạm thời với lỗi vĩnh viễn.

**Lưu ý về race:** `channel.isOpen()` chỉ là một phép kiểm tra tức thời; channel vẫn có thể đóng ngay sau đó, khiến `basicAck` ném `IOException`. Code không nên cố dùng lại tag cũ trên channel khác. Khi không thể ACK, message có thể được giao lại; `applyOnce` sẽ phát hiện event đã commit.

Nếu consumer gọi một API bên ngoài như gửi email hoặc thanh toán, database transaction của inbox **không bao trùm HTTP call**. Phải truyền idempotency key cho API nếu có hỗ trợ, hoặc ghi sự kiện điều khiển qua outbox riêng để tác dụng ngoài DB cũng có quy trình retry an toàn.

## 6. Phục hồi connection trong Spring AMQP không phục hồi “trạng thái đã bay”

Các thành phần Spring AMQP thường tham gia xử lý reconnect:

- **`CachingConnectionFactory`** quản lý connection/channel dùng bởi `RabbitTemplate` và listener containers, có cơ chế caching và tạo lại tài nguyên theo lifecycle.
- **`SimpleMessageListenerContainer` (SMLC)** và **`DirectMessageListenerContainer` (DMLC)** phát hiện lỗi consumer/channel, khôi phục việc đăng ký consumer theo chiến lược và khoảng thời gian recovery thích hợp.
- **`RabbitAdmin`** có thể khai báo lại exchange, queue, binding do ứng dụng quản lý khi kết nối mới được thiết lập, nếu được cấu hình để thực hiện.
- RabbitMQ Java client cũng có khả năng automatic connection/topology recovery, nhưng trong ứng dụng Spring AMQP tiêu chuẩn, **nên để Spring quản lý recovery của listener/connection**, tránh vô tình tạo hai lớp recovery chồng nhau.

Hệ thống có thể tự tạo lại connection và listener nhưng **không có nghĩa**:

1. Publish chưa được confirm sẽ tự động phát lại đúng một lần.
2. Future chờ confirm trên channel cũ sẽ nhận kết quả chắc chắn từ broker sau reconnect.
3. Delivery tag trên channel cũ vẫn hợp lệ trên channel mới.
4. Consumer đã làm xong nghiệp vụ sẽ được broker xem là ACK.
5. Queue không durable hoặc message transient tự nhiên tồn tại qua broker restart.
6. Mọi thao tác application-level như DB commit/HTTP call được rollback khi RabbitMQ disconnect.

Đây là khác biệt cốt lõi giữa **khôi phục đường kết nối** và **khôi phục độ tin cậy đầu cuối của message**.

### 6.1. Heartbeat, backoff và topology

Ví dụ một số cấu hình Spring Boot:

~~~yaml
spring:
  rabbitmq:
    addresses: rabbitmq-1:5672,rabbitmq-2:5672
    requested-heartbeat: 30s
    connection-timeout: 5s
    listener:
      simple:
        acknowledge-mode: manual
        prefetch: 16
        retry:
          enabled: false
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

`requested-heartbeat` giúp hai đầu phát hiện kết nối hỏng khi không có traffic phù hợp; không phải bảo đảm broker sẽ requeue ngay tại thời điểm dây mạng đứt. `connection-timeout` giới hạn thời gian tạo kết nối. Khi chọn địa chỉ nhiều node, cần cấu hình cluster và client connection settings theo hạ tầng thực tế; danh sách hostname **không** tự thay thế độ bền message hay bảo đảm failover tức thời.

Consumer có thể mất một khoảng thời gian reconnect/redeclare. RabbitAdmin muốn khai báo lại topology phải có quyền quản lý tương ứng; queue durable còn tồn tại sau reconnect khi broker chưa mất dữ liệu, nhưng queue auto-delete/exclusive có vòng đời khác. Thử nghiệm nên bao gồm cả broker restart và application restart, không chỉ disconnect TCP.

### 6.2. Không đặt retry vô hạn bên trong request

`RabbitTemplate` có thể được bọc bằng retry của Spring để thử lại lỗi truyền thông. Nhưng khi **publish attempt đầu tiên không có confirm**, retry tự động cũng có thể phát message lần nữa dù attempt đầu đã đến broker. Vì vậy:

- Có event ID ổn định và consumer idempotent.
- Nếu cần chịu process crash, ghi ý định publish bền vững trước.
- Dùng retry có giới hạn, exponential backoff + jitter, không giữ request thread chờ vô hạn.
- Tránh retry dồn dập khi broker vừa phục hồi; kiểm soát số publish in-flight.

## 7. Outbox giải quyết trạng thái publish không xác định

Đối với lệnh “ghi database rồi phát sự kiện”, **transactional outbox** là cách phổ biến để giữ ý định gửi trong database:

~~~mermaid
flowchart LR
    CMD["Lệnh tạo đơn hàng"] --> DB["DB transaction"]
    DB --> O["orders"]
    DB --> OB["outbox_event: PENDING"]
    OB --> REL["Publisher relay"]
    REL --> MQ["RabbitTemplate → RabbitMQ"]
    MQ -->|"Confirm ACK + không return"| DONE["Đánh dấu SENT"]
    MQ -->|"Timeout / mất kết nối / NACK"| KEEP["Giữ event, retry sau"]
    KEEP --> REL
    MQ --> Q["Queue → @RabbitListener"]
    Q --> IN["Inbox idempotency"]
~~~

Một bảng outbox tối thiểu:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    payload_json JSONB NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX outbox_unsent_idx
    ON outbox_event (status, next_attempt_at, created_at);
~~~

Flow chuẩn:

1. Trong **cùng database transaction**, ghi `orders` và `outbox_event(PENDING)`. Rollback sẽ hủy cả hai.
2. Một relay lấy event chưa gửi, publish bằng `RabbitTemplate` và theo dõi confirm/return.
3. Khi nhận confirm ACK hợp lệ, không bị return, relay đánh dấu row thành `SENT`.
4. Khi timeout hoặc disconnect, **giữ row**, retry với **cùng eventId** sau backoff.
5. Nếu publish thành công nhưng relay chết trước khi đánh dấu `SENT`, row được gửi lại; consumer xử lý duplicate bằng inbox.

Trong production, nhiều relay cần cơ chế claim/lease hoặc database row lock để không tranh cùng event, cùng với kế hoạch xử lý worker crash và dọn các row `SENT` theo retention. Outbox bảo đảm event không bị biến mất chỉ vì publisher process chết, nhưng vẫn có thể publish **at least once**, không tự tạo exactly-once delivery.

Không đặt cả thao tác gửi RabbitMQ lẫn database commit trong một method `@Transactional` rồi cho rằng hai bên đã có giao dịch phân tán nguyên tử. RabbitMQ channel transaction và Spring transaction synchronization không cung cấp atomic commit DB + broker như một XA transaction.

## 8. Requeue, retry và DLX khác với redelivery khi connection chết

Ba nguồn redelivery phổ biến có ngữ nghĩa khác nhau:

| Nguyên nhân | Ai kích hoạt? | Message đi đường nào? | Có tự giới hạn số lần không? |
|---|---|---|---|
| Consumer gọi `basicNack(tag, false, true)` | Ứng dụng | Quay lại cùng queue | Không |
| Consumer gọi `basicNack(tag, false, false)` | Ứng dụng | DLX nếu queue được cấu hình; có thể tới retry/DLQ | Không nếu chưa thiết kế giới hạn |
| Channel/connection đóng khi còn unacked | Broker sau khi phát hiện đóng | Delivery có thể được **requeue để redeliver** | Không bảo đảm retry hữu hạn theo nhu cầu ứng dụng |

Đặc biệt, **message requeue do kết nối đóng không tự sinh `x-death` với reason `rejected`**. `x-death` ghi nhận các sự kiện dead-letter mà broker quản lý (như rejected, expired); không nên dùng `x-death` làm bộ đếm tuyệt đối cho mọi lần redelivery.

Khi cần chờ giữa các lần retry, dùng delayed/retry topology (TTL + DLX hoặc cơ chế phù hợp), nhưng điều kiện dừng phải được quản lý chặt chẽ. Message sau một số lần xử lý thất bại cần đến **parking-lot/DLQ** để điều tra, không chạy vô hạn qua loop.

Với queue type và chính sách broker khác nhau, có thể tồn tại các giới hạn giao lại bổ sung (ví dụ delivery limit của quorum queues). Nếu dựa vào tính năng này, cần kiểm tra **loại queue, phiên bản RabbitMQ và policy thực tế**; không mặc nhiên suy ra nó có cùng semantics với số lần retry của ứng dụng.

## 9. Ma trận tình huống ngắt kết nối

| Thời điểm mất kết nối | Producer / consumer thấy gì? | Broker có thể còn gì? | Thiết kế cần làm |
|---|---|---|---|
| Trước khi producer gọi publish | Không có attempt gửi | Chưa có message từ attempt đó | Giữ event chưa gửi trong outbox |
| Sau khi gửi publish, trước khi broker nhận | Timeout/đóng channel | Message có thể chưa có | Retry cùng eventId |
| Broker đã nhận publish, confirm chưa đến producer | Timeout/confirm chưa rõ | Message **có thể đã vào queue** | Retry cùng eventId; consumer dedup |
| Confirm ACK và route hợp lệ đã đến producer | Producer có xác nhận | Broker đã nhận publish theo hợp đồng | Đánh dấu SENT; tiếp tục giám sát consumer |
| Confirm ACK nhưng message bị return | Producer biết không route được | Không có queue đích phù hợp | Sửa binding/routing; không đánh dấu SENT |
| Broker giao message, consumer chưa xử lý | Consumer mất connection | Delivery còn unacked rồi có thể requeue | Redelivery; kiểm tra trạng thái idempotency |
| Consumer đã DB commit, chưa gửi ACK | Listener biết DB xong, ACK chưa có | Delivery có thể redeliver | Inbox unique key ngăn ghi lặp |
| Consumer gửi ACK ngay trước disconnect | Không biết chắc broker nhận ACK | Có thể đã ACK **hoặc** sẽ redeliver | Không cố ACK tag cũ; dedup trên lần mới |
| Consumer chết trước DB commit | Transaction DB thường rollback nếu đúng cấu hình | Delivery được giao lại khi channel đóng | Retry message; transaction nghiệp vụ nguyên tử |
| Consumer vẫn đang chạy tác vụ nền khi connection mất | Callback có thể chạy tiếp | Broker có thể requeue sang consumer khác | Idempotency/locking chống xử lý trùng đồng thời |
| Broker restart, message/queue không durable | Client tự reconnect | Message/queue có thể mất | Durable topology, persistent message, confirm và kiểm thử durability |
| Relay publish rồi chết trước khi update outbox | DB còn PENDING/CLAIMED | Broker có thể đã nhận | Publish lại; eventId không đổi; consumer dedup |

Không thể phân biệt mọi nhánh chỉ bằng exception kiểu `AmqpConnectException` hoặc một log “connection reset”. Từ góc nhìn ứng dụng, nhiều sự kiện thật trên broker đều dẫn đến cùng một lỗi phía client. Cần kết hợp **publisher confirm/return, outbox state, event ID và consumer inbox**, thay vì cố đoán kết quả từ tên exception.

## 10. Kiểm thử mất kết nối một cách có chủ đích

Nên thử trên môi trường tích hợp có RabbitMQ thật; mock `RabbitTemplate` thường chỉ kiểm tra hàm được gọi, không mô phỏng chính xác trạng thái TCP/channel hay broker requeue.

### 10.1. Test ở phía publisher

1. Gửi một event `e1`, xác nhận topology exchange/queue/binding hoạt động; kiểm tra confirm ACK, không có return.
2. Dùng fault injection hoặc proxy mạng để cắt kết nối **sau khi lệnh publish được gửi nhưng trước khi confirm đến client**. Không được giả định chính xác broker đã nhận hay chưa.
3. Kiểm tra outbox vẫn ở trạng thái cần gửi khi confirm không được xác định.
4. Cho producer reconnect, retry **cùng eventId=e1**. Ghi nhận số delivery ở queue hoặc số callback consumer; có thể thấy một hoặc hai delivery tùy timing.
5. Gửi với routing key sai và `mandatory=true` để xác nhận publisher return được ghi nhận dù có thể nhận confirm ACK.

### 10.2. Test ở phía consumer

1. Cấu hình manual ACK, consumer xử lý một event trong database transaction.
2. Cắt connection sau database commit nhưng trước khi broker ghi nhận ACK; hoặc dừng consumer khi message vẫn còn *unacked*.
3. Chờ broker phát hiện channel/connection đã đóng, quan sát message redeliver.
4. Xác minh **tác dụng nghiệp vụ chỉ xuất hiện một lần** nhờ inbox unique key, dù listener có thể được gọi nhiều lần.
5. Kiểm tra delivery tag của lần nhận mới, tuyệt đối không ACK bằng tag cũ.
6. Lặp thử với consumer async, tác vụ xử lý chậm, nhiều instance và `prefetch` lớn để phát hiện xử lý trùng đồng thời.

Không dùng chính retry mặc định của client làm công cụ tạo tình huống “đúng một lần”, vì thời điểm ngắt mạng khó tái lập tuyệt đối. Có thể kết hợp điểm chặn có kiểm soát trong mã test, broker logs và các hook thử nghiệm nhằm tạo cửa sổ lỗi.

### 10.3. Những điều cần xác minh sau restart

- `RabbitAdmin` có khai báo lại topology như dự kiến không; durable và persistent đã được cấu hình đúng chưa?
- Listener có tái đăng ký consumer; có lỗi “queue not found”, permission hoặc channel exception không?
- Outbox relay có tiếp tục từ các row chưa `SENT`, tránh mất event khi ứng dụng chết?
- Những delivery còn unacked có được redeliver; bảng inbox có chặn duplicate tác dụng nghiệp vụ?
- DLQ và retry topology có giữ được poison message và không tạo vòng lặp vô hạn?

## 11. Quan sát và cảnh báo trong vận hành

Để điều tra một sự cố, cần theo dõi **cả publisher và consumer**:

| Tín hiệu | Ý nghĩa vận hành |
|---|---|
| `connection_closed` / reconnect count | Tần suất mất kết nối, gợi ý hạ tầng hoặc cấu hình heartbeat |
| Số publisher confirms đang chờ và quá hạn | Nguy cơ publish chưa biết kết quả |
| Publisher NACK / returned messages | Broker từ chối hoặc không có đường routing hợp lệ |
| Độ tuổi outbox `PENDING` lâu nhất | Sự kiện đã commit DB nhưng chưa được xác nhận phát |
| Outbox retry attempts và publish lag | Khả năng phục hồi sau broker lỗi; hiệu quả backoff |
| Queue `messages_ready` và `messages_unacknowledged` | Backlog chờ nhận so với delivery đang được xử lý |
| Consumer redelivery rate | Dấu hiệu disconnect, NACK/requeue hoặc xử lý thất bại |
| Duplicate event count ở inbox | Đánh giá hiệu quả idempotency và độ thường xuyên giao lại |
| DLQ/parking-lot depth, tuổi message | Message lỗi cần can thiệp hoặc retry đã cạn |
| Thời gian từ nhận delivery tới ACK | Phát hiện listener chậm, transaction dài hoặc task async bị treo |

Trong log/tracing, giữ `eventId` và `correlationId` xuyên các lần publish/receive, thêm `publishAttempt`, consumer instance, queue, message ID, mã lỗi và trạng thái confirm. Cần phân biệt **eventId cố định** của nghiệp vụ với **attempt ID mới** của mỗi lần gửi để không đánh đồng duplicate message với hai sự kiện độc lập.

Khi RabbitMQ khôi phục sau gián đoạn, backlog outbox và queue có thể đổ vào cùng lúc. Nên hạn chế số publish in-flight, đặt backoff có jitter, chọn prefetch/concurrency phù hợp và theo dõi tải database để tránh tạo sự cố tiếp theo trong quá trình catch-up.

## 12. Các hiểu lầm cần tránh

| Nhận định sai | Giải thích đúng |
|---|---|
| “Publish timeout nghĩa là broker chưa nhận message” | Kết quả **không xác định** khi confirm chưa tới producer |
| “Broker confirm ACK nghĩa là consumer đã xử lý” | Confirm chỉ xác nhận phía publish, consumer có ACK riêng |
| “Có confirm ACK thì không cần returns” | Publish không route có thể được broker confirm ACK; cần mandatory returns |
| “Ứng dụng reconnect thì Future cũ được tiếp tục an toàn” | Channel/confirm state cũ không biến thành giao dịch xuyên reconnect |
| “DB commit thành công nghĩa là message sẽ không giao lại” | Nếu consumer ACK chưa được broker ghi nhận, message có thể redeliver |
| “basicAck trả về nghĩa là broker chắc chắn đã nhận” | Consumer ACK là thao tác gửi một chiều, không có confirm ACK lần hai |
| “Có x-death nghĩa là đếm được mọi lần reconnect/redelivery” | x-death phản ánh dead-letter events, không phải mọi kiểu requeue |
| “Auto-ack đơn giản hơn và vẫn không mất message” | Với broker auto-ack, message có thể mất khi consumer chết trước xử lý |
| “Retry publish vô hạn sẽ có exactly-once delivery” | Retry khi outcome unknown có thể tạo duplicate; cần event ID và dedup |
| “Chỉ cần một DLQ là xử lý được mất kết nối” | DLQ không thay thế publisher confirms, outbox hoặc consumer idempotency |

## 13. Quy tắc thiết kế cuối cùng

**Phía publisher**, hãy coi mọi publish **chưa có confirm rõ ràng** là một kết quả **không xác định**. Giữ ý định gửi trong nơi lưu bền vững khi nghiệp vụ yêu cầu, retry với cùng `eventId`, theo dõi confirm/return và chỉ đánh dấu thành công sau khi broker xác nhận hợp lệ.

**Phía consumer**, hãy coi mọi delivery **chưa được broker ghi nhận ACK** là **có thể được giao lại**, kể cả khi database hoặc API đã xử lý xong. ACK sau khi nghiệp vụ commit, không ACK bằng delivery tag của channel cũ, và bảo vệ tác dụng nghiệp vụ bằng idempotency/unique constraint hoặc idempotency key tại dịch vụ ngoài.

Trong **Spring AMQP**, reconnect giúp `RabbitTemplate` và `@RabbitListener` có thể tiếp tục hoạt động, nhưng **không khôi phục sự chắc chắn của các thao tác đang dang dở**. Thiết kế bền vững dựa trên phối hợp **publisher confirms + mandatory returns, durable topology, transactional outbox khi cần, at-least-once delivery, consumer idempotency, retry hữu hạn và quan sát trạng thái**. Đó là cách duy trì tính đúng đắn khi mạng, broker hoặc ứng dụng lỗi đúng tại ranh giới xác nhận.
