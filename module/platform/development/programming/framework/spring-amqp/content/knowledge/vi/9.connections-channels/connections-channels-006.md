# PooledChannelConnectionFactory và giới hạn publisher confirm tương quan

Trong hệ thống xử lý bất đồng bộ, `RabbitTemplate` có thể phát rất nhiều message trong khi các `@RabbitListener` tiêu thụ message ở những tốc độ khác nhau. Mỗi lần publish, ứng dụng cần một **AMQP channel** để giao tiếp với RabbitMQ. Tạo kết nối TCP và channel mới liên tục sẽ tốn tài nguyên; vì thế **Spring AMQP** cung cấp nhiều cách quản lý kết nối và tái sử dụng channel, trong đó có `PooledChannelConnectionFactory`.

Tuy nhiên, một lựa chọn hiệu quả để **mượn và trả channel** chưa chắc phù hợp với yêu cầu **publisher confirm tương quan (correlated publisher confirms)**. Khi cần biết broker xác nhận **đúng message nào**, ứng dụng phải giữ thông tin tương quan cho đến khi tín hiệu xác nhận bất đồng bộ quay về. Đây chính là giới hạn cần hiểu trước khi chọn connection factory.

Bài thuộc chương **Kết nối và channel** của module **SPRING_AMQP**. Chúng ta sẽ tìm hiểu mô hình pooling, so sánh với `CachingConnectionFactory`, cấu hình một producer có publisher confirms và returns, rồi liên hệ đến exchange, queue, binding, consumer acknowledgment, retry, dead-letter, giao dịch và quan sát hệ thống.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **TCP connection**, **AMQP channel**, **channel pool** và **channel cache**.
2. Mô tả vòng đời mượn/trả channel của `PooledChannelConnectionFactory` và các rủi ro khi chia sẻ channel sai cách.
3. Giải thích vì sao **correlated publisher confirms** phải gắn kết trạng thái của một lần publish với confirm bất đồng bộ về sau.
4. Chọn `CachingConnectionFactory` khi cần `ConfirmType.CORRELATED` và `CorrelationData`.
5. Viết ví dụ Spring Boot phát message, nhận publisher confirm/return và phân biệt chúng với xác nhận của consumer.
6. Kiểm tra các chỉ số về connections, channels, pool contention, outstanding confirms và backlog để chẩn đoán hệ thống.

## 2. Connection khác channel như thế nào?

AMQP 0-9-1 sử dụng **connection** làm đường kết nối TCP giữa ứng dụng và RabbitMQ. Bên trong một connection, ứng dụng có thể mở **nhiều channel** được ghép chung trên connection đó. Phần lớn thao tác publish/consume/ack được thực hiện trên một channel.

~~~mermaid
flowchart LR
    subgraph APP["Ứng dụng Spring Boot"]
        T1["RabbitTemplate A"] --> F["Spring ConnectionFactory"]
        T2["RabbitTemplate B"] --> F
        L["@RabbitListener container"] --> F
    end
    F --> CONN["Một TCP connection AMQP"]
    CONN --> CH1["Channel 1"]
    CONN --> CH2["Channel 2"]
    CONN --> CH3["Channel 3"]
    CH1 --> B["RabbitMQ broker"]
    CH2 --> B
    CH3 --> B
~~~

| Khái niệm | Ý nghĩa | Chi phí/rủi ro |
|---|---|---|
| **Connection** | Một kết nối AMQP qua TCP, có xác thực, heartbeat và trạng thái mạng | Tạo mới tốn tài nguyên; gián đoạn connection ảnh hưởng các channel bên trong |
| **Channel** | Phiên AMQP logic nằm trong connection, có định danh riêng | Broker/client phải quản lý trạng thái channel; có giới hạn số lượng |
| **Channel pool** | Tập channel đã tạo, cho mã ứng dụng **mượn** khi cần và **trả** khi xong | Pool cạn dẫn đến chờ hoặc lỗi; cần kiểm soát channel được trả |
| **Channel cache** | Tái sử dụng channel đóng về mặt logic qua cơ chế cache | Cần cấu hình số channel lưu lại và cách quản lý khi có confirm đang chờ |

**Channel không phải đối tượng an toàn để tùy ý sử dụng đồng thời từ nhiều luồng.** RabbitMQ Java client không khuyến khích các luồng chia sẻ một channel để publish đồng thời. Việc dùng chung channel thiếu đồng bộ có thể làm sai thứ tự frame, gây lỗi giao thức hoặc làm phức tạp tương quan confirm. `RabbitTemplate` kết hợp với connection factory giúp quản lý cách lấy và trả tài nguyên; ứng dụng không nên giữ tham chiếu channel rồi đưa tùy tiện cho nhiều thread.

Ngoài channel pool, RabbitMQ còn có các giới hạn như `channel_max` thương lượng với broker và tài nguyên hệ điều hành (socket, file descriptor, bộ nhớ). Tăng số channel không tự đảm bảo throughput cao hơn; cần quan sát trước khi chỉnh.

## 3. `PooledChannelConnectionFactory` quản lý gì?

`PooledChannelConnectionFactory` của Spring AMQP cung cấp **pool các AMQP channel**, dựa trên **Apache Commons Pool 2**. Nó quản lý connection phục vụ các channel và phân biệt pool dành cho thao tác **transactional** với pool dành cho thao tác **non-transactional**. Khi `RabbitTemplate` cần publish, framework mượn một channel thích hợp; khi thao tác kết thúc và channel được đóng về mặt logic, channel đủ điều kiện có thể được trả về pool để tái sử dụng.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Producer
    participant T as RabbitTemplate
    participant F as PooledChannelConnectionFactory
    participant B as RabbitMQ
    P->>T: Gửi message
    T->>F: Mượn channel
    F-->>T: Channel từ pool / channel được tạo
    T->>B: basic.publish trên channel
    T->>F: Kết thúc thao tác và trả channel
    F-->>T: Channel trở lại pool khi hợp lệ
    T-->>P: Lệnh gửi hoàn tất ở phía client
    Note over P,B: Kết thúc lệnh gửi không chứng minh consumer đã xử lý
~~~

### 3.1. Điểm mạnh

- **Tái sử dụng channel:** giảm chi phí tạo/hủy channel thường xuyên.
- **Giới hạn tài nguyên có chủ đích:** cấu hình kích thước pool, số channel cho phép hoạt động, thời gian chờ mượn và kiểm soát contention theo API của phiên bản đang sử dụng.
- **Tách channel giao dịch và không giao dịch:** tránh đem một channel có trạng thái transaction dùng nhầm cho luồng bình thường.
- **Phù hợp tác vụ ngắn:** mỗi lần gọi dùng channel trong phạm vi rõ ràng rồi trả lại.

### 3.2. Điều gì pool không làm thay?

Pool không biến message thành **bền vững**, không quyết định exchange/binding nào được dùng, không tự giải quyết **retry**, **dead-letter**, **idempotency** hoặc giao dịch database. Cũng không nên hiểu “pool channel” là “mỗi lần publish mở một TCP connection riêng”: channel được ghép trên kết nối AMQP và được quản lý bởi connection factory.

Một pool cấu hình quá nhỏ dưới tải đồng thời có thể làm thread chờ channel; cấu hình quá lớn có thể tăng số channel đang mở và chi phí phía broker. Trạng thái **channel pool đang sử dụng** không đồng nhất với số channel nhìn thấy ở RabbitMQ Management: một channel rảnh trong pool vẫn có thể đang mở trên broker.

## 4. Hạn chế cốt lõi: correlated publisher confirms

### 4.1. Publisher confirm dùng để xác nhận điều gì?

RabbitMQ hỗ trợ **publisher confirms** để broker thông báo kết quả xử lý publication theo giao thức confirm. Tín hiệu confirm được gửi **bất đồng bộ** trên channel đã phát message. Broker dùng **delivery tag/sequence number trong phạm vi channel** để chỉ ra publication được xác nhận; nó có thể xác nhận từng publish hoặc theo nhóm.

Trong Spring AMQP, **correlated publisher confirms** cho phép ứng dụng gắn một `CorrelationData` (thường có ID ứng với `eventId`) vào lần gửi để biết message nghiệp vụ nào được broker **ack** hoặc **nack**.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Producer
    participant T as RabbitTemplate
    participant C as Channel có confirm
    participant B as RabbitMQ
    P->>T: publish(eventId=E-01, CorrelationData)
    T->>C: basic.publish + đăng ký tương quan
    C->>B: Publish trên channel + sequence number
    Note over P,B: Producer có thể tiếp tục công việc khác
    B-->>C: basic.ack hoặc basic.nack (sequence number)
    C-->>T: Ghép confirm với publication
    T-->>P: Hoàn tất callback/future của E-01
~~~

Để ghép được **E-01** với confirm, thư viện phải theo dõi mối quan hệ giữa **channel, publish sequence number và `CorrelationData`** cho tới khi broker phản hồi. Kết quả publish trả về ngay trong `convertAndSend` không thể thay cho confirm đến sau đó.

### 4.2. Vì sao cần cân nhắc khi dùng channel pool?

**`PooledChannelConnectionFactory` không phải lựa chọn hỗ trợ luồng publisher confirm tương quan của Spring AMQP.** Vòng đời “mượn channel → gửi → trả pool” được tối ưu cho sử dụng channel ngắn hạn, trong khi confirm có thể còn **đang chờ** khi mã publish kết thúc. Channel bị tái sử dụng không đúng thời điểm sẽ khiến việc gắn confirm bất đồng bộ với lời gọi cũ trở nên phức tạp.

Hạn chế cần áp dụng khi thiết kế: **nếu producer yêu cầu `ConfirmType.CORRELATED`, `CorrelationData` hoặc callback/future để theo dõi từng publication, hãy sử dụng `CachingConnectionFactory`** với publisher confirms được cấu hình phù hợp. Không chỉ thêm `spring.rabbitmq.publisher-confirm-type: correlated` rồi giả định một bean `PooledChannelConnectionFactory` tự hỗ trợ cùng khả năng.

Điều này không có nghĩa mọi ứng dụng đều bắt buộc phải dùng correlated confirms. Chúng cần thiết khi hệ thống phải biết publication **nào** được broker xác nhận, phục vụ retry có kiểm soát, đánh dấu outbox và giám sát từng sự kiện. Với producer không có yêu cầu này, pooled channels có thể là lựa chọn cần đánh giá bằng tải thực tế.

### 4.3. Những tín hiệu không được đánh đồng

| Tín hiệu | Nơi phát sinh | Nó cho biết gì? | Nó **không** tự đảm bảo gì? |
|---|---|---|---|
| `RabbitTemplate.convertAndSend(...)` trả về | Client producer | Lời gọi gửi phía client kết thúc mà chưa ném exception đồng bộ | Broker đã lưu an toàn, message có queue nhận hoặc listener xử lý xong |
| **Publisher confirm ACK** | RabbitMQ broker | Broker xác nhận publication theo cơ chế confirm | Đã được định tuyến đến queue mong muốn hoặc consumer xử lý thành công |
| **Publisher confirm NACK** | RabbitMQ broker | Publication không được broker xác nhận thành công | Không thể tự suy ra trạng thái nghiệp vụ cuối cùng |
| **Publisher return** | Broker khi không định tuyến và bật mandatory phù hợp | Message không có queue đích phù hợp để nhận | Broker đã xử lý thành công một consumer nào đó |
| **Consumer acknowledgment** | Consumer/listener container | Xác nhận giao nhận ở phía tiêu thụ theo chế độ ack | Giao dịch bên ngoài, side effect hoặc nghiệp vụ liên quan đều đúng |
| **Kết quả nghiệp vụ** | Ứng dụng/DB | Công việc đã thành công/thất bại theo hợp đồng nghiệp vụ | Không đồng nhất với publisher confirm hay consumer ack |

Một message **không định tuyến được** có thể vừa được broker **ACK publication**, vừa bị **return** nếu bật `mandatory` và publisher returns. **Publisher confirm ACK không chứng minh queue đích đã nhận**. Đó là lý do producer tin cậy cần xem xét cả confirms, returns, routing và các xác nhận nghiệp vụ phù hợp.

## 5. So sánh `PooledChannelConnectionFactory` và `CachingConnectionFactory`

| Tiêu chí | `PooledChannelConnectionFactory` | `CachingConnectionFactory` |
|---|---|---|
| Cách tái sử dụng channel | Apache Commons Pool 2; mượn/trả vào pool | Cache lại channel đã dùng để tái sử dụng |
| Quản lý nhóm channel | Pool transactional và non-transactional | Cache channel transactional và non-transactional |
| Connection | Quản lý connection phục vụ các channel trong pool | Thường dùng một connection chia sẻ ở chế độ `CHANNEL`; có chế độ cache connection khác |
| Giới hạn số channel | Phụ thuộc cấu hình pool; cần theo dõi nhu cầu mượn/trả | `channelCacheSize` là kích thước cache; chỉ trở thành giới hạn mượn có ý nghĩa khi cấu hình thời gian chờ checkout phù hợp |
| **Correlated publisher confirms** | **Không chọn cho yêu cầu này** | **Hỗ trợ qua `ConfirmType.CORRELATED`** |
| Publisher returns | Không dựa vào factory này như giải pháp cho cùng luồng confirm/return tương quan | Có thể cấu hình `publisherReturns`, `mandatory` và callback |
| Phù hợp | Tái sử dụng channel trong tác vụ ngắn khi không cần correlated confirms | Producer cần biết ACK/NACK theo từng message, tracking với `CorrelationData` |

Trong Spring Boot, `CachingConnectionFactory` thường là lựa chọn được auto-configure khi dùng `spring-boot-starter-amqp` và chưa tự định nghĩa bean connection factory khác. **Không nên khai báo đồng thời hai factory cùng mục đích mà không chỉ rõ bean nào được `RabbitTemplate` và listener container sử dụng.** Nếu tạo bean pooled factory tùy chỉnh, đừng mặc nhiên cho rằng thuộc tính Boot dành cho caching sẽ kích hoạt correlated confirms trên pooled factory.

## 6. Ví dụ 1 — Dùng pooled channels khi không yêu cầu correlated confirms

Ứng dụng Spring Boot có thể khai báo `PooledChannelConnectionFactory` khi đã có Apache Commons Pool 2 trong classpath. Với Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-pool2</artifactId>
    </dependency>
</dependencies>
~~~

Ví dụ cấu hình connection factory **thay cho** cấu hình caching ở mục tiếp theo:

~~~java
import org.springframework.amqp.rabbit.connection.PooledChannelConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitPooledFactoryConfig {

    @Bean
    PooledChannelConnectionFactory rabbitConnectionFactory() {
        com.rabbitmq.client.ConnectionFactory client =
                new com.rabbitmq.client.ConnectionFactory();
        client.setHost("localhost");
        client.setPort(5672);
        client.setUsername("lab");
        client.setPassword("lab123456");

        return new PooledChannelConnectionFactory(client);
    }
}
~~~

Đây là cấu hình minh họa cho môi trường local. Khi chạy thực tế, lấy host, thông tin xác thực, TLS và giới hạn pool từ cấu hình quản lý tập trung; đừng ghi mật khẩu thật vào source. Apache Commons Pool 2 cần hiện diện tại runtime; cấu hình giới hạn pool theo API `PoolConfigurer` của phiên bản Spring AMQP đang dùng và đo đạc trước khi tăng kích thước.

Giả sử exchange/queue đã khai báo tương ứng, producer có thể phát bằng `RabbitTemplate` như thường:

~~~java
@Service
public class AuditPublisher {
    private final RabbitTemplate rabbitTemplate;

    public AuditPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(String auditEvent) {
        rabbitTemplate.convertAndSend(
                "audit.events", "audit.logged", auditEvent);
    }
}
~~~

Các đoạn code là hai phần trong **cùng một ứng dụng**; khi tách thành các file Java thực tế, cần import `RabbitTemplate` và `Service` ở lớp `AuditPublisher`. Cấu hình pooled không tạo exchange `audit.events` hay queue/binding tự động: phải khai báo chúng riêng hoặc dùng topology có sẵn.

**Giới hạn của ví dụ:** lời gọi trả về không phải biên nhận xác nhận message cụ thể đã được broker xử lý. Nếu nghiệp vụ yêu cầu retry đúng từng event sau ACK/NACK, lựa chọn này chưa đáp ứng yêu cầu correlated confirms.

## 7. Ví dụ 2 — Cấu hình correlated publisher confirms với caching

### 7.1. Cấu hình Spring Boot

Với producer cần bảo đảm biết broker xác nhận **từng lần publish**, dùng `CachingConnectionFactory`. Khi sử dụng auto-configuration của Spring Boot, không khai báo bean `PooledChannelConnectionFactory` từ mục 6 trong cùng ví dụ.

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: lab
    password: lab123456
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    cache:
      channel:
        size: 25
~~~

| Thuộc tính | Ý nghĩa |
|---|---|
| `publisher-confirm-type: correlated` | Bật cơ chế publisher confirm có liên hệ với `CorrelationData` |
| `publisher-returns: true` | Cho phép nhận message bị trả lại khi không định tuyến được |
| `template.mandatory: true` | Yêu cầu broker trả về message không thể định tuyến trong tình huống phù hợp |
| `cache.channel.size` | Số channel mong muốn giữ trong cache, **không mặc nhiên là giới hạn số channel đang hoạt động** |

Nếu **không dùng Spring Boot auto-configuration**, có thể tạo `CachingConnectionFactory` trực tiếp và gọi `setPublisherConfirmType(CachingConnectionFactory.ConfirmType.CORRELATED)` cùng `setPublisherReturns(true)`; sau đó cấu hình `RabbitTemplate` với `mandatory` và xử lý kết quả. Đây là **phương án thay thế**, không cần làm cả hai trong cùng ứng dụng.

### 7.2. Topology tối thiểu: exchange, queue, binding

Để publisher có queue đích thực sự, khai báo một direct exchange cùng queue:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderEventTopology {

    @Bean
    DirectExchange orderEventsExchange() {
        return new DirectExchange("orders.events", true, false);
    }

    @Bean
    Queue orderEventsQueue() {
        return QueueBuilder.durable("orders.created").build();
    }

    @Bean
    Binding orderCreatedBinding(Queue orderEventsQueue,
                                DirectExchange orderEventsExchange) {
        return BindingBuilder.bind(orderEventsQueue)
                .to(orderEventsExchange)
                .with("order.created");
    }
}
~~~

### 7.3. Publish có `CorrelationData` và theo dõi future

Ví dụ dưới dùng API `CorrelationData.getFuture()` của các phiên bản Spring AMQP hiện đại. `eventId` làm khóa theo dõi ở producer và được gắn thêm vào AMQP headers để consumer cũng có thể ghi log cùng định danh:

~~~java
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private static final Logger log =
            LoggerFactory.getLogger(OrderEventPublisher.class);

    private final RabbitTemplate rabbitTemplate;

    public OrderEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public String publishCreated(String orderId) {
        String eventId = UUID.randomUUID().toString();
        CorrelationData correlation = new CorrelationData(eventId);

        rabbitTemplate.convertAndSend(
                "orders.events",
                "order.created",
                orderId,
                message -> {
                    message.getMessageProperties()
                            .setHeader("eventId", eventId);
                    return message;
                },
                correlation);

        correlation.getFuture().whenComplete((confirm, error) -> {
            if (error != null) {
                log.error("Publish confirmation failed, eventId={}",
                        eventId, error);
                return;
            }

            if (!confirm.isAck()) {
                log.warn("Broker NACK eventId={}, reason={}",
                        eventId, confirm.getReason());
                return;
            }

            if (correlation.getReturned() != null) {
                log.warn("Broker ACK but unroutable, eventId={}, reply={}",
                        eventId, correlation.getReturned().getReplyText());
                return;
            }

            log.info("Broker confirmed publication, eventId={}", eventId);
        });

        return eventId;
    }
}
~~~

**Diễn giải chính xác:**

- `convertAndSend(...)` thực hiện lệnh gửi; `CorrelationData` gắn lần publish với kết quả xác nhận **bất đồng bộ** sau đó.
- `confirm.isAck()` nghĩa là broker đã ACK publication theo giao thức publisher confirm. ACK **không phải** xác nhận listener chạy thành công.
- `correlation.getReturned()` cho biết publication liên quan bị trả về khi không định tuyến được, trong cấu hình hỗ trợ publisher returns và `mandatory`. Spring AMQP sắp xếp việc ghi thông tin return liên quan trước khi hoàn tất future confirm theo luồng hỗ trợ này.
- `confirm.getReason()` có thể hữu ích với NACK nhưng không phải mọi tình huống đều mang đủ nguyên nhân ở một chuỗi dễ đọc.
- Trường `eventId` ở header được ứng dụng đặt riêng để **truy vết nghiệp vụ**; ID bên trong `CorrelationData` phục vụ đối chiếu publisher confirm và không nên mặc định coi là header do broker tự thêm.

Ví dụ trên mới **ghi log** kết quả. Trong hệ thống thật, cần gắn nó với **trạng thái outbox/retry** có giới hạn, kiểm soát số publication chưa nhận confirm, xử lý timeout và đóng ứng dụng an toàn. Một callback bất đồng bộ có thể xảy ra sau khi phương thức `publishCreated` đã trả về.

### 7.4. Consumer để phân biệt ACK ở hai phía

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {
    private static final Logger log =
            LoggerFactory.getLogger(OrderCreatedListener.class);

    @RabbitListener(queues = "orders.created")
    public void onCreated(String orderId,
                          @Header("eventId") String eventId) {
        log.info("Consumer processed eventId={}, orderId={}",
                eventId, orderId);
        // Ghi dữ liệu nghiệp vụ, kiểm tra eventId/idempotency nếu cần.
    }
}
~~~

Với chế độ `AUTO` của listener container trong Spring AMQP, consumer thường ACK message sau khi phương thức kết thúc thành công. **Consumer ack** khác hoàn toàn **publisher confirm**: broker có thể xác nhận một message trước khi consumer bắt đầu xử lý nó. Bảo đảm nghiệp vụ cần được đánh giá ở thời điểm ghi dữ liệu, giao dịch và xử lý lỗi của listener.

## 8. Những giới hạn thực tế của correlated confirms

Chuyển sang `CachingConnectionFactory` giúp **có cơ chế** correlated confirms, nhưng không đồng nghĩa cứ publish là không bao giờ mất dữ liệu:

### 8.1. Confirm đến sau, có thể trễ hoặc không đến kịp

Broker, mạng, connection/channel và tải hệ thống ảnh hưởng thời gian phản hồi. Cần đặt **thời hạn chờ xác nhận ở cấp ứng dụng**, giới hạn số publish đang chờ và có cách đánh dấu trạng thái `UNKNOWN` khi timeout. Timeout **không chứng minh broker chưa nhận message**: publication có thể đã được chấp nhận nhưng confirm thất lạc khi kết nối hỏng.

### 8.2. Không được retry vô điều kiện khi không rõ kết quả

Nếu producer gửi lại cùng công việc sau timeout, consumer có thể nhận **hai bản sao**. Thiết kế **idempotency** tại consumer theo `eventId` hoặc khóa nghiệp vụ để tránh tính tiền, giữ hàng hay phát thông báo hai lần. Confirm không biến cơ chế phân phối thành exactly-once.

### 8.3. ACK và return giải quyết hai câu hỏi khác nhau

Một message có thể được ACK tại broker nhưng không khớp **binding** nào. `mandatory` và publisher returns giúp nhận biết tình huống không định tuyến được; chỉ kiểm tra `confirm.isAck()` là chưa đủ khi nghiệp vụ yêu cầu message vào một queue cụ thể.

### 8.4. Callback và future phải được theo dõi có giới hạn

Mỗi `CorrelationData` đang chờ confirm chiếm tài nguyên theo dõi. Khi publish với tốc độ cao, cần kiểm soát **outstanding confirms**, độ trễ ACK/NACK, thời gian chờ, độ dài queue và memory. Không nên gom vô hạn futures trong một collection hoặc chặn một thread cho từng future nếu chưa có chính sách backpressure phù hợp.

### 8.5. Correlated confirm không tạo atomic transaction với database

Ví dụ `Order Service` commit đơn rồi publish event; tiến trình chết giữa hai bước có thể làm **thiếu event**. Với dữ liệu nghiệp vụ quan trọng, dùng **transactional outbox** (ghi dữ liệu và event outbox trong cùng DB transaction) kết hợp publish, confirm, retry và idempotency để tăng độ tin cậy. Cần theo dõi trạng thái outbox từ lúc tạo event đến lúc xác nhận broker.

## 9. Điều chỉnh pooling, caching và concurrency

### Với `PooledChannelConnectionFactory`

- Cấu hình pool theo **số tác vụ đồng thời thực sự cần mượn channel**, thay vì đơn giản đặt một con số rất lớn.
- Theo dõi thời gian chờ mượn channel, số yêu cầu chờ, pool exhaustion, số channel đang mở và lỗi kết nối. Apache Commons Pool 2 có các tham số như `maxTotal`, `maxIdle`, cơ chế chờ khi cạn; cách truyền cấu hình vào factory phụ thuộc API phiên bản.
- Tách rõ thao tác transactional và non-transactional; đừng giả định transaction AMQP tương đương transaction của database.
- Không giữ channel qua một công việc bất đồng bộ dài rồi trả pool ở thời điểm tùy tiện. Hãy để `RabbitTemplate` và connection factory quản lý tài nguyên.

### Với `CachingConnectionFactory`

- `channelCacheSize` nói về số channel có thể được **lưu lại**, không mặc định là giới hạn cứng số channel mở. Khi cấu hình checkout timeout dương để giới hạn checkout, cần hiểu mối quan hệ giữa số channel đang dùng, cache size và thời gian chờ.
- Bật `ConfirmType.CORRELATED` khi producer cần biết ACK/NACK theo từng publish; bật returns và `mandatory` nếu cần phát hiện không định tuyến được.
- Tách tải publisher/consumer khi cần bằng cấu hình connection factory phù hợp. Luôn kiểm chứng hành vi thực tế khi thay connection factory tùy chỉnh.
- Đo đạc trước khi tăng cache hoặc concurrency; tăng song song có thể tăng áp lực broker, số channel và backlog.

**Không nhầm `prefetch` với kích thước channel pool.** Prefetch ảnh hưởng số message mà consumer được giao trước khi ACK; channel pool/cache ảnh hưởng việc ứng dụng mượn và tái sử dụng channel. Hai tham số giải quyết những điểm nghẽn khác nhau.

## 10. Quan sát trong RabbitMQ Management

RabbitMQ Management (thường tại `http://localhost:15672` nếu bật plugin) hỗ trợ kiểm tra:

| Khu vực/chỉ số | Quan sát | Điều có thể suy luận |
|---|---|---|
| **Connections** | Số connection và trạng thái | Ứng dụng có mở TCP/AMQP connection không; có reconnect bất thường không |
| **Channels** | Số channel, connection liên quan, hoạt động publish/confirm/ack | Số channel đang mở, biến động quá lớn hoặc channel bị đóng lỗi |
| **Exchanges** | Loại exchange, routing/binding | Message có thể tới queue nào |
| **Queues and Streams** | Ready, Unacked, Consumers, message rates | Consumer có theo kịp hay message đang bị tồn |
| **Logs/metrics của producer** | `eventId`, publish timestamp, confirm ACK/NACK, return, latency | Publication cụ thể được broker xác nhận ra sao |
| **Metrics ứng dụng** | Pool active/idle/waiters, cache utilization, outstanding confirmations | Pool/cache có nghẽn, confirm có tồn đọng hay không |

Management hiển thị **số channel của broker**, thường không phản ánh trực tiếp số phần tử **idle** bên trong pool của ứng dụng; để biết pool đang cạn hay không cần instrument pool/client và đọc log. Management cũng không tự hiển thị bảng `CorrelationData` của mỗi lần publish: ứng dụng phải log hoặc xuất metrics thích hợp.

### Thực hành A — Quan sát pooled channels

1. Chạy RabbitMQ và ứng dụng dùng `PooledChannelConnectionFactory` từ mục 6, cấu hình exchange/binding hợp lệ cho `audit.events`.
2. Gửi một loạt message nhỏ bằng producer, quan sát số connection/channel trong Management.
3. Lặp lại với tải đồng thời cao hơn có kiểm soát, theo dõi thời gian publish và trạng thái chờ mượn channel ở ứng dụng.
4. Ghi lại trường hợp pool chưa đủ, sau đó chỉnh thông số pool phù hợp và đối chiếu. Không suy rằng channel phải đóng hoàn toàn sau từng publish, vì chúng có thể được giữ lại để tái sử dụng.

### Thực hành B — Correlated confirm có queue đích

1. Dùng ứng dụng `CachingConnectionFactory` với cấu hình ở mục 7.
2. Publish `ORD-1001` tới `orders.events` với routing key `order.created`.
3. Quan sát log `eventId` và `Broker confirmed publication` khi broker trả ACK.
4. Quan sát consumer nhận `eventId` tương ứng nếu listener chạy. So sánh thời điểm publisher confirm và log consumer, hiểu rằng hai tín hiệu khác nhau.

### Thực hành C — ACK nhưng không định tuyến được

1. Vẫn dùng cấu hình `publisher-returns: true` và `template.mandatory: true`.
2. Publish tới **exchange tồn tại** `orders.events` nhưng dùng routing key `order.unknown`, không có binding nào phù hợp.
3. Kiểm tra kết quả returned message cho `eventId`; publisher confirm vẫn có thể ACK publication.
4. Đối chiếu queue `orders.created` không tăng do message sai routing key. Không suy rằng ACK đồng nghĩa message đã tới queue.

### Thực hành D — Mất confirm và retry

Trong môi trường thử nghiệm riêng, mô phỏng lỗi kết nối quanh thời điểm publish/confirm rồi ghi lại các event chưa xác định trạng thái. Thiết kế retry có giới hạn và consumer chống xử lý trùng; đừng thử đóng connection hay xóa queue trên broker đang dùng bởi các dịch vụ khác. Kiểm tra rằng hệ thống không đánh dấu event `DELIVERED` chỉ vì `convertAndSend` kết thúc.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân nên kiểm tra | Hướng xử lý |
|---|---|---|
| Đã cấu hình correlated confirms nhưng callback không đến | Ứng dụng đang dùng pooled factory hoặc chưa bật confirm đúng bean | Kiểm tra connection factory thực sự được inject; dùng caching có `CORRELATED` |
| `convertAndSend` không lỗi nhưng message không vào queue | Sai exchange, routing key, binding, vhost; consumer xử lý quá nhanh | Xem Management, bật mandatory/returns, đối chiếu queue và log |
| Confirm ACK nhưng không có consumer log | Message không định tuyến, consumer dừng, backlog, listener lỗi | Xem return, Ready/Unacked, Consumers, listener logs |
| Nhiều channel mở nhưng pool có vẻ không rảnh | Channel được giữ để tái sử dụng; công việc chưa trả channel; pool sizing | Đo active/idle/waiters ở ứng dụng và channel count ở broker |
| Thread gửi bị chờ lâu | Pool cạn hoặc channel checkout đang bị giới hạn | Đo thời gian chờ mượn, xem concurrency, giới hạn tải hợp lý |
| Confirm trễ và bộ nhớ producer tăng | Quá nhiều in-flight publications / futures | Giới hạn outstanding, đặt timeout và backpressure |
| Retry gây xử lý trùng | Producer không biết publish trước đó đã được nhận hay chưa | Dùng event ID, outbox và consumer idempotent |
| Queue có message nhưng không xử lý | Không có consumer, listener lỗi, prefetch/ack bất thường | Kiểm tra Ready, Unacked, Consumers, retry/DLQ |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Pool channel và pool TCP connection có giống nhau không?

Không. `PooledChannelConnectionFactory` tập trung vào tái sử dụng **AMQP channel**, vốn có thể cùng nằm trên một connection TCP. Chi phí và giới hạn của connection khác channel.

**Câu 2.** Vì sao một lần `convertAndSend` trả về chưa đủ để đánh dấu event “đã được broker xác nhận”?

Vì thao tác gửi phía client và **publisher confirm bất đồng bộ** là hai mốc khác nhau. Cần chờ/nhận ACK/NACK và quản lý trường hợp timeout.

**Câu 3.** Nếu phải đối chiếu ACK/NACK theo từng `eventId`, nên dùng factory nào?

Dùng `CachingConnectionFactory` hỗ trợ `ConfirmType.CORRELATED` và gửi kèm `CorrelationData`. Không dựa vào `PooledChannelConnectionFactory` để thực hiện luồng confirm tương quan.

**Câu 4.** Broker ACK publisher confirm có đồng nghĩa một `@RabbitListener` đã xử lý thành công?

Không. Confirm chỉ gắn với publication; consumer ack và kết quả nghiệp vụ là các tín hiệu riêng.

**Câu 5.** Khi một message sai routing key, tại sao publisher confirm có thể ACK?

Broker có thể xác nhận đã xử lý publication, trong khi message không có binding đích. Cần `mandatory` và publisher returns để nhận biết unroutable message.

**Câu 6.** Vì sao producer và consumer vẫn cần idempotency dù có correlated publisher confirms?

Do confirm có thể thất lạc hoặc đến muộn, producer retry có thể làm message được gửi nhiều lần. Consumer cần phát hiện `eventId` đã xử lý để tránh lặp side effect.

## 13. Ghi nhớ

- **`PooledChannelConnectionFactory`** dùng Apache Commons Pool 2 để tái sử dụng AMQP channel; phù hợp khi lợi ích pooling được chứng minh bằng tải thực tế và **không có yêu cầu correlated publisher confirms**.
- **`CachingConnectionFactory` + `ConfirmType.CORRELATED` + `CorrelationData`** là lựa chọn phù hợp khi producer cần ghép ACK/NACK từ broker với từng publication.
- **Publisher confirm, publisher return, consumer ack và kết quả nghiệp vụ là những mốc độc lập**. Không dùng một tín hiệu để thay thế các tín hiệu còn lại.
- Vận hành đáng tin cậy còn cần **binding đúng, kiểm soát outstanding confirms, retry có giới hạn, DLQ, idempotency, transactional outbox và quan sát connection/channel/queue**.
