# Stream queue và mô hình log có thể đọc lại

## Mục tiêu bài học

Trong **Spring AMQP**, nhiều hệ thống bắt đầu bằng mô hình **producer → exchange → queue → consumer**: producer dùng **RabbitTemplate** phát message, broker định tuyến theo exchange/binding, consumer xử lý qua **@RabbitListener** rồi xác nhận. Mô hình này phù hợp với tác vụ nền như gửi email hoặc tạo hóa đơn. Nhưng nếu **nhiều bộ phận phải đọc cùng lịch sử sự kiện**, hoặc một consumer muốn **đọc lại các message đã xử lý**, queue thông thường bộc lộ giới hạn.

**RabbitMQ stream queue** được thiết kế cho các tình huống ấy. Nó lưu message như một **append-only log** có vị trí đọc (**offset**), duy trì bản ghi theo **retention** và cho phép nhiều consumer đọc lại cùng nội dung. Sau bài này, bạn có thể:

1. Giải thích vì sao stream queue có cơ chế **non-destructive consumption** khác classic/quorum queue.
2. Phân biệt **offset bắt đầu đọc**, **offset đã xử lý**, **checkpoint** và **retention**.
3. Khai báo stream với **x-queue-type=stream**, cấu hình giới hạn lưu trữ và định tuyến từ exchange.
4. Tích hợp stream qua **AMQP 0.9.1** hoặc **RabbitMQ Stream Protocol** trong Spring AMQP.
5. Thiết kế replay, consumer độc lập, idempotency, retry và quan sát hệ thống khi xảy ra lỗi.

## 1. Bài toán: không chỉ nhận message một lần

Giả sử **Order Service** phát các sự kiện:

- **OrderCreated:** đơn hàng được tạo.
- **OrderPaid:** thanh toán hoàn tất.
- **OrderShipped:** đơn đã bàn giao cho đơn vị vận chuyển.

Ban đầu, chỉ có **Analytics Service** xử lý các sự kiện để tổng hợp doanh thu. Một tháng sau, nhóm phát triển bổ sung **Fraud Detection Service**, cần đọc lại dữ liệu giao dịch còn được lưu để xây dựng tiêu chí phát hiện gian lận.

Với **queue công việc truyền thống**, khi message đã được xử lý và ACK, broker thường loại nó khỏi queue. Fraud Detection không thể yêu cầu chính queue ấy phát lại các message đã bị xóa. Có thể tạo thêm queue cho mỗi nhóm consumer từ đầu, nhưng queue mới cũng **không tự có lịch sử trước thời điểm được bind**.

Với **stream queue**, message được lưu trong một log; consumer đọc message mà không xóa nó. Analytics và Fraud Detection có thể đọc cùng stream từ các vị trí khác nhau, miễn dữ liệu cần đọc vẫn còn trong khoảng retention.

~~~mermaid
flowchart LR
    P["Order Service<br/>Producer"] --> X{"Topic exchange<br/>orders.events"}
    X -->|"routing: order.*"| S[("Stream queue<br/>orders.event-log")]
    S -->|"offset riêng"| A["Analytics Service"]
    S -->|"offset riêng"| F["Fraud Detection"]
    S -->|"replay dữ liệu còn lưu"| R["Consumer kiểm toán mới"]
~~~

**Giá trị nghiệp vụ:** giảm nhu cầu nhân bản một backlog riêng cho từng subscriber, cho phép rebuild báo cáo, khởi tạo consumer mới từ dữ liệu cũ và xử lý những sự kiện tồn đọng lớn. Stream **không tự biến hệ thống thành exactly-once** và cũng không thay thế database nghiệp vụ.

## 2. Stream queue là append-only log

**Append-only** nghĩa là broker ghi các bản tin mới ở phần cuối log. Mỗi message có một **offset** để xác định vị trí của nó trong stream. Consumer không lấy message ra khỏi log; nó chỉ dịch chuyển **vị trí đọc** của riêng mình.

~~~text
Stream: orders.event-log

Offset:       100            101              102              103
Message:   OrderCreated → OrderPaid      → OrderCreated →    OrderShipped
                │             │                │                │
                └─────────────┴────────────────┴────────────────┘
                                     append-only log

Analytics đã xử lý đến:               103
Fraud Detection đã xử lý đến:         101
Consumer mới (replay từ 100):         100 → 101 → 102 → 103
~~~

Ví dụ, dù Analytics đã xử lý offset **103**, Fraud Detection vẫn có thể đọc offset **102** nếu bản ghi chưa bị retention loại bỏ. Ngược lại, nếu dữ liệu sớm nhất còn lại là offset **101**, yêu cầu đọc từ **100** không thể khôi phục bản ghi đã mất khỏi stream.

### Ba khái niệm không được đánh đồng

| Khái niệm | Câu hỏi nó trả lời | Điểm cần nhớ |
| --- | --- | --- |
| **Offset của message** | Message ở vị trí nào trong log? | Do stream xác định; không nên coi là số thứ tự nghiệp vụ của đơn hàng |
| **Vị trí consumer bắt đầu đọc** | Khi đăng ký, consumer muốn bắt đầu từ đâu? | Có thể chọn đầu log, cuối log, offset cụ thể hoặc thời điểm phù hợp |
| **Checkpoint / stored offset** | Consumer đã ghi nhận tiến độ xử lý đến đâu? | Do client/ứng dụng quản lý; có thể nằm trong broker hoặc hệ thống lưu trữ khác |

**Lưu checkpoint không xóa message.** Checkpoint cũng không phải một giao dịch nguyên tử với database của ứng dụng nếu không có thiết kế bổ sung.

### So sánh cách ACK của queue truyền thống với stream

Trong classic/quorum queue, consumer ACK thành công thường khiến broker loại message khỏi queue. Với **native stream consumer**, ứng dụng theo dõi offset; việc consumer đọc hay lưu checkpoint **không xóa** bản ghi khỏi log. Nếu dùng **AMQP 0.9.1 để đọc stream**, consumer vẫn phải dùng acknowledgement theo giao thức và QoS/prefetch, nhưng ACK khi đó **không đồng nghĩa với xóa dữ liệu stream**.

Do vậy, “đã nhận”, “đã ACK”, “đã checkpoint” và “nghiệp vụ đã commit” là những mốc khác nhau cần quan sát riêng.

## 3. So sánh classic queue, quorum queue và stream queue

| Tiêu chí | Classic queue | Quorum queue | Stream queue |
| --- | --- | --- | --- |
| Mô hình phổ biến | Backlog tác vụ, chia tải worker | Backlog tác vụ cần tính sẵn sàng và độ bền cao | Log sự kiện, replay, nhiều nhóm đọc độc lập |
| Sau khi consumer ACK | Message được loại khỏi queue | Message được loại khỏi queue | Message **vẫn được giữ** theo retention |
| Đọc lại message đã xử lý | Không từ queue đã xóa message | Không từ queue đã xóa message | **Có**, khi dữ liệu còn trong log |
| Vị trí đọc | Thường là message sẵn sàng tiếp theo | Thường là message sẵn sàng tiếp theo | **Offset** do consumer chọn/theo dõi |
| Durable | Có thể durable hoặc non-durable | Durable | **Luôn durable** |
| Exclusive/auto-delete | Có thể cấu hình tùy trường hợp | Không phải mô hình queue tạm | **Không hỗ trợ** như queue tạm |
| Message TTL | Có | Có các quy tắc hỗ trợ riêng | Không có TTL từng message; dùng **retention** |
| Dead-letter exchange (DLX) | Có | Có | **Không hỗ trợ DLX kiểu queue truyền thống** |
| Message priority | Có trên classic queue phù hợp | Không hỗ trợ message priority như classic | **Không hỗ trợ** |
| Nhiều consumer cần cùng lịch sử | Thường tạo queue riêng cho mỗi nhóm | Thường tạo queue riêng cho mỗi nhóm | Nhiều consumer đọc **cùng stream** |
| Thứ tự xử lý | Có thể thay đổi khi nhiều worker, redelivery | Có thể thay đổi khi nhiều worker, redelivery | Thứ tự **lưu trong từng stream**, nhưng ứng dụng vẫn cần kiểm soát xử lý song song |

**Không chọn stream chỉ vì “nó mới hơn”.** Nếu bài toán là job queue với retry, DLQ, TTL và ACK xóa tác vụ, classic/quorum queue thường phù hợp hơn. Nếu bài toán đòi **đọc lại log, fan-out lớn, backlog lớn, thông lượng cao**, stream là lựa chọn đáng cân nhắc.

## 4. Khai báo stream queue và chính sách giữ dữ liệu

RabbitMQ stream được khai báo như một queue với argument **x-queue-type=stream**. Đây là thuộc tính **cố định từ lúc tạo**; không thể đổi một queue đang tồn tại từ classic/quorum sang stream chỉ bằng policy.

Stream phải **durable**, không exclusive và không auto-delete. Sau khi khai báo, stream có thể **bind với exchange** như các queue AMQP 0.9.1 khác.

### 4.1. Ví dụ Spring AMQP qua RabbitAdmin

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderStreamTopology {

    @Bean
    public TopicExchange ordersEventExchange() {
        return new TopicExchange("orders.events", true, false);
    }

    @Bean
    public Queue ordersEventLog() {
        return QueueBuilder.durable("orders.event-log")
                .stream()
                .withArgument("x-max-age", "7D")
                .withArgument("x-max-length-bytes", 5_000_000_000L)
                .build();
    }

    @Bean
    public Binding ordersEventBinding(
            Queue ordersEventLog, TopicExchange ordersEventExchange) {
        return BindingBuilder.bind(ordersEventLog)
                .to(ordersEventExchange)
                .with("order.*");
    }
}
~~~

Điều kiện: ứng dụng có **Spring AMQP**, kết nối AMQP 0.9.1 (thường cổng **5672**), **RabbitAdmin** được cấu hình để khai báo bean queue/exchange/binding, và user có quyền trên vhost.

Trong ví dụ:

- **QueueBuilder.durable(...).stream()** đặt queue type thành stream.
- **x-max-age=7D** đặt khoảng thời gian lưu mong muốn là bảy ngày.
- **x-max-length-bytes=5_000_000_000** đặt ngưỡng kích thước log khoảng 5 GB thập phân.
- **TopicExchange** định tuyến event có routing key gồm hai phần như **order.created**, **order.paid** tới cùng một stream.

**Lưu ý:** Binding key **order.*** chỉ khớp một từ sau **order.**. Nó không tự khớp **order.payment.completed**; nếu muốn toàn bộ nhánh đa cấp có thể dùng **order.#**.

**RabbitAdmin chỉ tự khai báo khi có AMQP connection được mở** theo cấu hình. Một ứng dụng **chỉ** dùng native stream client, không khởi tạo connection AMQP, không nên dựa vào việc bean Queue ở trên tự được khai báo. Khi đó sử dụng **StreamAdmin**, CLI, Kubernetes operator hoặc công cụ provisioning.

### 4.2. Retention không phải TTL từng message

RabbitMQ quản lý stream thành các **segment** trên đĩa. Retention loại bỏ **segment cũ** khi điều kiện thời gian/dung lượng phù hợp, không xóa riêng từng message ngay đúng giây hết hạn.

| Thiết lập | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **x-max-age** | **7D**, **12h** | Ngưỡng thời gian giữ dữ liệu cũ |
| **x-max-length-bytes** | **5_000_000_000** | Ngưỡng dung lượng lưu trữ log |
| **x-stream-max-segment-size-bytes** | **100_000_000** | Kích thước segment, ảnh hưởng mức hạt khi retention dọn dữ liệu |

Hai điều kiện tuổi và dung lượng có thể được kết hợp. Chính sách broker (**policy**) có thể thay đổi retention mà không tạo lại stream; với các đối số segment/bloom filter, có những giới hạn về việc áp policy sau khi stream đã tồn tại. Broker thường giữ **ít nhất segment cuối vẫn có message**, nên kích thước hay tuổi thực tế có thể tạm vượt ngưỡng.

**Không có một giá trị retention “luôn an toàn”.** Nếu consumer cần replay 30 ngày, cấu hình chỉ giữ 7 ngày là không đủ. Nếu không đặt retention, log có thể tiếp tục tăng tới khi cạn dung lượng đĩa; không nên mặc định rằng RabbitMQ sẽ tự dọn một stream không có policy.

### 4.3. Producer qua RabbitTemplate vẫn có thể gửi vào stream

Stream queue vẫn tham gia mô hình exchange/binding. Nếu topology phía trên được khai báo, producer AMQP có thể publish:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(String eventJson) {
        rabbitTemplate.convertAndSend(
                "orders.events", "order.created", eventJson);
    }
}
~~~

Ở đường đi này, producer gửi tới **topic exchange** bằng **AMQP 0.9.1**, exchange định tuyến vào **orders.event-log**. Stream không yêu cầu mọi producer đều dùng native client. Tuy nhiên **RabbitTemplate không cung cấp toàn bộ tính năng quản lý offset và publishing deduplication của native stream client**; đó là khác biệt ở lớp giao thức.

## 5. Hai đường truy cập một stream queue

~~~mermaid
flowchart TB
    APP["Ứng dụng Spring"]
    APP --> A["RabbitTemplate / listener AMQP 0.9.1"]
    APP --> B["RabbitStreamTemplate / StreamListenerContainer"]
    A -->|"AMQP 0.9.1<br/>TCP 5672"| EX["Exchange / Stream queue<br/>RabbitMQ core"]
    B -->|"RabbitMQ Stream Protocol<br/>TCP 5552"| PL["RabbitMQ Stream Plugin"]
    PL --> EX
    EX --> LOG[("Append-only log<br/>offset + retention")]
~~~

| Con đường | Dependency / API Spring | Khi dùng |
| --- | --- | --- |
| **AMQP 0.9.1** | **spring-rabbit**, RabbitTemplate, listener container AMQP | Ứng dụng đã có Spring AMQP, muốn định tuyến tới stream qua exchange hoặc đọc bằng consumer args |
| **Native Stream Protocol** | **spring-rabbit-stream**, RabbitStreamTemplate, StreamListenerContainer, Stream Java Client | Cần replay/offset tracking, thông lượng stream tối ưu, publishing deduplication và super streams |

Đối với **AMQP 0.9.1**, stream queue được RabbitMQ core hỗ trợ theo queue type **stream**. Để dùng **native Stream Protocol**, phải **bật rabbitmq_stream plugin** trên broker:

~~~bash
rabbitmq-plugins enable rabbitmq_stream
~~~

Cổng mặc định thường là **5672** cho AMQP 0.9.1 và **5552** cho native Stream Protocol, nhưng có thể được cấu hình lại. Trong cluster hoặc Docker/Kubernetes, native stream client còn cần truy cập **advertised host/port** của các node mà broker trả về khi discovery; mở bootstrap port chưa chắc đủ.

**spring-rabbit-stream** là module tích hợp của **Spring AMQP** (hỗ trợ ban đầu từ Spring AMQP 2.4), không phải message broker và cũng không đồng nhất với **Spring Cloud Stream Rabbit binder**. Chọn version dependency phù hợp với phiên bản Spring/Spring Boot trong dự án.

### 5.1. Sự khác nhau khi consume

Consumer dùng **AMQP 0.9.1** có thể đặt **x-stream-offset** lúc đăng ký và phải có consumer ACK/QoS phù hợp. Nếu không đặt offset, nó bắt đầu từ **các message mới được append sau khi đăng ký**. ACK phục vụ cơ chế giao message/credit, **không xóa message khỏi log**.

Consumer dùng **native Stream Protocol** chọn **OffsetSpecification** và có thể lưu tiến độ bằng cơ chế **server-side offset tracking** theo consumer name, hoặc lưu offset ngoài broker. Native listener không dùng cách hiểu ACK/xóa message như listener của classic queue.

## 6. Offset: đọc từ đầu, cuối, vị trí cụ thể hoặc thời gian

Để replay, ứng dụng phải **chỉ định nơi bắt đầu đọc**. Một số vị trí phổ biến:

| Vị trí | Native Stream Java Client | Ý nghĩa |
| --- | --- | --- |
| **first** | **OffsetSpecification.first()** | Đọc từ message sớm nhất **còn giữ** trong log |
| **last** | **OffsetSpecification.last()** | Bắt đầu từ **chunk cuối** hiện có; có thể nhận nhiều message trong chunk |
| **next** | **OffsetSpecification.next()** | Chỉ nhận những message append **từ sau thời điểm subscribe** |
| **offset(n)** | **OffsetSpecification.offset(n)** | Bắt đầu từ offset chỉ định nếu còn; broker xử lý vị trí nằm ngoài phạm vi còn lưu |
| **timestamp** | **OffsetSpecification.timestamp(...)** | Bắt đầu gần thời điểm broker ghi dữ liệu; độ chính xác phụ thuộc chunk |

**Cẩn thận với last:** nó **không có nghĩa là “chỉ lấy đúng một message cuối cùng”**. RabbitMQ dùng chunk làm đơn vị lưu/truyền; **last** có thể phát lại các message trong chunk cuối. Nếu chỉ muốn message **mới từ bây giờ**, dùng **next**.

**first không có nghĩa lịch sử vĩnh viễn.** Khi retention đã dọn các segment cũ, first chỉ trỏ đến bản ghi sớm nhất còn tồn tại. Tương tự, đọc từ timestamp có thể bắt đầu tại ranh giới chunk và trả thêm một số message đến sớm hơn thời điểm đã chọn.

### 6.1. Bài tập tư duy về offset

Stream hiện có offset **200–209** (các offset 0–199 đã hết hạn). Một consumer đăng ký:

- **first**: có thể đọc từ offset **200**.
- **next**: chờ bản ghi **210** và các bản ghi sau đó.
- **last**: bắt đầu từ **chunk cuối** chứa các bản ghi gần cuối; không bảo đảm chỉ nhận 209.
- **offset(205)**: nhận được các message từ **205** nếu còn trong log.
- **offset(0)**: không khôi phục được offset 0–199 chỉ bằng việc đặt lại vị trí.

## 7. Ví dụ native stream bằng Spring AMQP

Phần này dùng **spring-rabbit-stream** để vừa publish vừa consume theo offset. Để minh họa, dùng một stream cố định **orders.event-log**. Có thể đặt stream này trước bằng công cụ vận hành; ví dụ dưới khai báo nó bằng **StreamAdmin** và không phụ thuộc vào RabbitAdmin của AMQP 0.9.1.

### 7.1. Dependency

Trong dự án có BOM quản lý Spring AMQP, khai báo dependency không cần ghim lẻ một version:

~~~xml
<dependency>
    <groupId>org.springframework.amqp</groupId>
    <artifactId>spring-rabbit-stream</artifactId>
</dependency>
~~~

Nếu không có dependency management, phải cung cấp phiên bản **spring-rabbit-stream** tương thích với các module Spring AMQP khác, đồng thời dùng phiên bản RabbitMQ có Stream Plugin phù hợp. Không trộn tùy ý các nhánh phiên bản chỉ vì class có tên giống nhau.

### 7.2. Kết nối, khai báo stream và listener factory

~~~java
import com.rabbitmq.stream.Environment;
import com.rabbitmq.stream.OffsetSpecification;
import java.time.Duration;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.listener.RabbitListenerContainerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.rabbit.stream.config.StreamRabbitListenerContainerFactory;
import org.springframework.rabbit.stream.listener.StreamListenerContainer;
import org.springframework.rabbit.stream.producer.RabbitStreamTemplate;
import org.springframework.rabbit.stream.support.StreamAdmin;

@Configuration
@EnableRabbit
public class NativeStreamConfig {

    @Bean(destroyMethod = "close")
    Environment streamEnvironment() {
        return Environment.builder()
                .host("localhost")
                .port(5552)
                .username("guest")
                .password("guest")
                .build();
    }

    @Bean
    StreamAdmin streamAdmin(Environment streamEnvironment) {
        return new StreamAdmin(streamEnvironment, creator -> {
            creator.stream("orders.event-log")
                    .maxAge(Duration.ofDays(7))
                    .create();
        });
    }

    @Bean
    RabbitStreamTemplate orderStreamTemplate(Environment streamEnvironment) {
        return new RabbitStreamTemplate(streamEnvironment, "orders.event-log");
    }

    @Bean
    RabbitListenerContainerFactory<StreamListenerContainer> replayFactory(
            Environment streamEnvironment) {
        StreamRabbitListenerContainerFactory factory =
                new StreamRabbitListenerContainerFactory(streamEnvironment);
        factory.setNativeListener(true);
        factory.setConsumerCustomizer((id, builder) -> builder
                .name("orders-analytics")
                .offset(OffsetSpecification.first())
                .manualTrackingStrategy());
        return factory;
    }
}
~~~

Để chạy local, RabbitMQ phải bật plugin và cho phép user kết nối native trên port 5552. Ví dụ **guest/guest** chỉ để học với broker local; trên môi trường thật hãy lấy thông tin kết nối từ cấu hình/secret, dùng user riêng và TLS khi cần.

Các bean trong ví dụ:

- **Environment** là môi trường của **RabbitMQ Stream Java Client**, khác với **org.springframework.core.env.Environment**.
- **StreamAdmin** tạo stream qua native client, có thể dùng cho ứng dụng chỉ dùng stream.
- **RabbitStreamTemplate** publish trực tiếp vào tên stream.
- **StreamRabbitListenerContainerFactory** tạo stream listener theo cơ chế native; **setNativeListener(true)** cho phép truy cập message và context của Stream Java Client.
- **ConsumerCustomizer** gán tên **orders-analytics**, offset khởi đầu và chiến lược checkpoint thủ công.

### 7.3. Publish vào native stream

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.rabbit.stream.producer.RabbitStreamTemplate;
import org.springframework.stereotype.Service;

@Service
public class NativeOrderPublisher {
    private final RabbitStreamTemplate template;

    public NativeOrderPublisher(RabbitStreamTemplate template) {
        this.template = template;
    }

    public CompletableFuture<Boolean> publish(String eventJson) {
        return template.convertAndSend(eventJson);
    }
}
~~~

Ví dụ sử dụng:

~~~java
publisher.publish("{\"eventId\":\"e-101\",\"type\":\"OrderCreated\"}")
        .whenComplete((confirmed, failure) -> {
            if (failure != null || !Boolean.TRUE.equals(confirmed)) {
                // Ghi log, cảnh báo, lên lịch xử lý publish lỗi.
                return;
            }
            // Broker đã xác nhận publish, chưa có nghĩa Analytics xử lý xong.
        });
~~~

**RabbitStreamTemplate** publish bất đồng bộ và trả **CompletableFuture<Boolean>**. Kết quả được xác nhận ở phía broker không tự đảm bảo transaction ở consumer đã commit; nếu không nhận được xác nhận rõ ràng, retry có thể khiến event xuất hiện trùng. Event quan trọng nên có **eventId** và chính sách publish đáng tin cậy.

### 7.4. Consume, xử lý, rồi lưu offset

~~~java
import com.rabbitmq.stream.Message;
import com.rabbitmq.stream.MessageHandler.Context;
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class AnalyticsStreamListener {

    @RabbitListener(
            id = "analytics-order-events",
            queues = "orders.event-log",
            containerFactory = "replayFactory")
    public void handle(Message message, Context context) {
        String eventJson = new String(
                message.getBodyAsBinary(), StandardCharsets.UTF_8);

        // Ví dụ minh họa: thay bằng xử lý và commit nghiệp vụ thật.
        System.out.println("Analytics processed: " + eventJson);

        // Chỉ lưu checkpoint khi phần việc cần thiết đã thành công.
        context.storeOffset();
    }
}
~~~

**Quan trọng:** trong ví dụ minh họa, việc in ra console được xem là hoàn tất công việc. Với ứng dụng thực tế, đặt **context.storeOffset()** sau khi việc ghi database hoặc tác vụ nghiệp vụ đã được xác nhận. Không đặt checkpoint vô điều kiện trong khối **finally**, vì có thể đánh dấu vượt qua message chưa xử lý được.

**@RabbitListener** với native stream factory chỉ hỗ trợ một phần thuộc tính annotation: những thuộc tính quan trọng là **id**, **queues** (một stream), **autoStartup**, **containerFactory**. Các thuộc tính listener truyền thống như **concurrency** không mặc nhiên có tác dụng giống AMQP queue listener.

### 7.5. Khởi động lại và thực hiện replay

Với consumer name **orders-analytics** và manual tracking, Stream Java Client có thể lưu offset **phía broker**. Khi consumer cùng tên kết nối lại, **stored offset có thể được ưu tiên hơn OffsetSpecification.first()**. Điều này giúp consumer tiếp tục từ vị trí đã xử lý, nhưng cũng khiến người học ngạc nhiên khi đổi code sang first mà không thấy replay toàn bộ.

Để thực hành đọc lại từ đầu một cách có chủ đích:

1. Đảm bảo dữ liệu cần đọc vẫn còn theo retention.
2. Sử dụng một consumer name **mới**, ví dụ **orders-replay-demo-01**, chưa có checkpoint lưu trên broker; đặt **OffsetSpecification.first()**.
3. Quan sát message cũ xuất hiện lại. Nếu dùng cùng logic làm thay đổi database, phải xử lý trùng theo **eventId**.
4. Với hệ thống thực, nên lập **quy trình replay riêng**, có thể ghi kết quả vào bảng/đích thử nghiệm trước khi áp dụng lên trạng thái sản xuất.

Không nên tùy tiện xóa checkpoint hoặc đổi tên consumer trên production để “đọc lại cho chắc”: replay ngoài ý muốn có thể nhân đôi email, hóa đơn hoặc giao dịch.

## 8. Offset tracking và vấn đề xử lý lặp

### Ví dụ: consumer sập giữa commit và checkpoint

~~~text
T0  Consumer nhận OrderPaid (offset 511)
T1  Consumer ghi giao dịch vào database và COMMIT thành công
T2  Tiến trình đột ngột dừng, chưa storeOffset(511)
T3  Consumer chạy lại từ checkpoint cũ
T4  OrderPaid (offset 511) được đọc lại
~~~

Nếu ở T4 consumer tăng doanh thu thêm lần nữa, hệ thống bị sai. Đây là lý do **lưu offset không tạo exactly-once xuyên database và broker**.

Một thiết kế đáng tin cậy:

- **Producer:** tạo **eventId** ổn định cho một sự kiện nghiệp vụ; dùng **transactional outbox** nếu cần lưu event nhất quán với thay đổi database nguồn.
- **Consumer:** lưu **eventId đã xử lý** trong cùng transaction với tác động nghiệp vụ; đặt unique constraint để message phát lại không gây thêm tác động.
- **Checkpoint:** thực hiện sau khi tác động đã commit (hoặc xử lý xác định là duplicate an toàn).
- **Hệ thống bên ngoài:** nếu gọi API thanh toán/email, cần idempotency key hoặc workflow riêng; một transaction database cục bộ không thể bao trùm mọi API từ xa.

Nếu dùng server-side tracking, đặt **consumer name ổn định qua các lần khởi động** và không cho nhiều consumer độc lập tùy ý dùng cùng một tracking name. Nếu nhiều instance cùng tên tự ghi offset mà không điều phối, vị trí lưu có thể bị ghi đè hoặc xen kẽ. Dùng super streams/single-active-consumer hoặc cơ chế sở hữu partition phù hợp khi muốn chia tải có checkpoint.

### Khác nhau giữa replay và retry

**Replay:** chủ động đọc lại một đoạn lịch sử theo offset để xây lại view, kiểm toán hoặc sửa lỗi trước đây. Có thể chạy thành một job riêng và thường phải kiểm soát khối lượng lớn.

**Retry:** cố xử lý lại một message thất bại. Trên native stream, không thể giả định các thao tác **nack/requeue/DLX** hoạt động giống classic/quorum queue. Cần quy định số lần thử, backoff và cách **cách ly event lỗi** (error queue/stream hoặc bảng lỗi) trước khi consumer tiếp tục. Tránh retry vô hạn khiến consumer mắc kẹt ở một offset.

Spring AMQP native stream listener hỗ trợ **stateless retry interceptor** ở những phiên bản có tính năng này; **stateful retry** của listener container truyền thống không được hỗ trợ tương đương. Có thể dùng **StreamMessageRecoverer** để xây luồng xử lý sau khi retry thất bại. Cấu hình phải theo đúng phiên bản **spring-rabbit-stream** đang dùng.

## 9. Hạn chế về lưu trữ và tính thứ tự

### 9.1. Stream queue không phải kho lưu trữ vĩnh viễn

Retention có thể xóa segment dù còn consumer chậm chưa đọc tới. Nếu ứng dụng offline 10 ngày trong khi stream giữ dữ liệu 7 ngày, nó **có nguy cơ mất khả năng replay** phần dữ liệu quá cũ. Hãy xác định:

- Khoảng thời gian offline tối đa được chấp nhận.
- Thời gian cần giữ lịch sử theo yêu cầu nghiệp vụ/pháp lý.
- Dung lượng dự kiến = lưu lượng publish × kích thước message × thời gian giữ, cộng overhead/replication.
- Phương án **snapshot**, đồng bộ lại từ database nguồn hoặc archive nếu consumer bỏ lỡ retention.

### 9.2. Thứ tự được giữ trong log nhưng xử lý có thể song song

Stream có thứ tự offset trong **một** log. Điều này không bảo đảm ứng dụng xử lý đúng thứ tự nếu:

- Consumer thực hiện công việc song song và hoàn tất lệch thứ tự.
- Nhiều hệ thống nguồn phát sự kiện cùng lúc, không có thứ tự nghiệp vụ toàn cục.
- Một message lỗi bị xử lý lại sau các message mới.
- Hệ thống dùng **super streams** với nhiều partition.

Với state machine của đơn hàng, nên dùng **orderId**, **eventVersion** hoặc số phiên bản aggregate; xác định cách xử lý event đến muộn, trùng hoặc sai thứ tự.

### 9.3. Stream không phải queue tạm

Stream luôn durable và replicated. Không khai báo stream **exclusive**, **auto-delete** hoặc **non-durable** kiểu AnonymousQueue. Các tính năng **per-message TTL, message priority, consumer priority và DLX** kiểu classic/quorum queue không phải semantics hỗ trợ của stream. Nếu cần xử lý job trì hoãn và dead-letter tự động, cân nhắc topology queue truyền thống hoặc thiết kế kênh lỗi riêng.

## 10. Super streams: khi một log cần chia thành nhiều partition

Một stream đơn có thứ tự và throughput của riêng nó. Với lưu lượng rất lớn, **super stream** tổ chức một stream logic thành nhiều partition stream, thường có exchange để định tuyến message theo routing key.

~~~mermaid
flowchart LR
    P["Order producer"] --> R{"Partition theo orderId"}
    R --> S0[("orders-0")]
    R --> S1[("orders-1")]
    R --> S2[("orders-2")]
    S0 --> C0["Consumer partition 0"]
    S1 --> C1["Consumer partition 1"]
    S2 --> C2["Consumer partition 2"]
~~~

Các sự kiện có cùng **orderId** nên đi vào cùng partition nếu muốn giữ thứ tự theo đơn. **Không có một thứ tự offset toàn cục giữa các partition**. Việc tăng số partition và thay đổi khóa băm có thể ảnh hưởng phân bố dữ liệu; cần cân nhắc khi áp dụng production.

Native **RabbitMQ Stream Java Client** và **spring-rabbit-stream** hỗ trợ super streams; việc phân phối consumer/single-active-consumer, offset và độ song song phải cấu hình theo topology, không chỉ tăng **@RabbitListener(concurrency=...)** như queue thường.

## 11. Quan sát hệ thống: đừng nhìn mỗi độ dài queue

Ở classic/quorum queue, **ready messages** tăng liên tục thường biểu thị backlog. Với stream, log được **cố ý giữ lại**, nên “queue dài” hoặc “dung lượng lớn” không nhất thiết là consumer bị nghẽn.

| Chỉ số | Câu hỏi | Hành động khi bất thường |
| --- | --- | --- |
| **Publish rate và xác nhận publish** | Có nhận được event mới, broker có xác nhận? | Kiểm tra kết nối, flow control, lỗi xác nhận và publisher retry |
| **Consumer offset** | Consumer đã xử lý đến đâu? | Theo dõi checkpoint theo tên consumer/partition |
| **Latest offset và consumer lag** | Consumer còn cách đuôi stream bao xa? | Phân tích tốc độ xử lý, scaling và bottleneck phía sau |
| **Oldest retained offset** | Dữ liệu cần replay còn không? | Tăng retention hoặc dùng snapshot/archive |
| **Stream disk usage, segment và replica** | Log và replication có khỏe mạnh? | Điều chỉnh retention, dung lượng đĩa, cụm broker |
| **Retry, error stream và duplicate events** | Message lỗi có làm nghẽn hoặc xử lý trùng không? | Cải thiện validation, backoff, DLQ/application error flow và idempotency |

Nên ghi **eventId**, **correlationId**, **consumer name**, **stream name**, **offset**, **processing duration** vào log/tracing, nhưng không ghi thông tin nhạy cảm không cần thiết. Spring AMQP hỗ trợ **Micrometer Observation** cho RabbitStreamTemplate và stream listener ở những nhánh phiên bản phù hợp; cần bật hook quan sát đúng component.

## 12. Chọn stream khi nào?

| Tình huống | Lựa chọn hợp lý | Lý do |
| --- | --- | --- |
| Gửi thông báo email từng việc, worker ACK rồi bỏ việc khỏi queue | **Classic/quorum queue** | Dễ dùng retry, DLX, TTL và chia tải |
| Analytics cần đọc lại sự kiện cuối tuần để xây lại báo cáo | **Stream queue** | Replay từ offset còn giữ |
| Audit và Fraud cùng cần lịch sử giao dịch nhưng tiến độ đọc độc lập | **Stream queue** | Consumer độc lập, không xóa message sau đọc |
| Một stream bị giới hạn thông lượng, cần phân vùng theo khóa nghiệp vụ | **Super streams** | Mở rộng qua partition |
| Lưu trữ lịch sử 10 năm, yêu cầu truy vấn tùy ý | **Database/data lake/archive** kết hợp stream | Stream không thay thế kho lưu trữ dài hạn và công cụ truy vấn |
| Phải có kết quả đồng bộ ngay trong request | **HTTP/gRPC/giao dịch trực tiếp** khi phù hợp | Stream là cơ chế bất đồng bộ, không phải một transaction RPC |

**Ví dụ kết hợp:** Order Service phát **OrderPaid** vào một stream để Audit/Analytics đọc lại, đồng thời phát command **SendInvoiceEmail** sang quorum queue cho worker gửi email và dùng DLQ khi thất bại. Hai kiểu tài nguyên có thể cùng tồn tại trên RabbitMQ.

## 13. Bài tập thực hành

### Bài 1 — Tạo stream và quan sát log

Khai báo **orders.event-log** bằng **QueueBuilder.durable(...).stream()** hoặc **StreamAdmin**, đặt retention 7 ngày. Publish năm event qua **RabbitStreamTemplate**. Mở RabbitMQ Management để xác minh queue type, tốc độ publish và số liệu stream.

### Bài 2 — Phân biệt first, last và next

Publish năm message **trước khi** consumer khởi động. Chạy lần lượt ba consumer với các tên theo dõi khác nhau:

- Consumer A khởi đầu bằng **first()**.
- Consumer B khởi đầu bằng **next()**.
- Consumer C khởi đầu bằng **last()**.

Ghi lại message mỗi consumer nhìn thấy, rồi publish thêm hai message. Giải thích vì sao **last** có thể nhận hơn một bản ghi từ chunk cuối.

### Bài 3 — Replay và checkpoint

Dùng listener native ở mục 7, lưu offset sau khi xử lý. Dừng và chạy lại **cùng consumer name**, ghi lại vị trí đọc. Tiếp theo dùng **consumer name mới** và **first()** để chủ động replay. Chú ý không thực hiện tác động nghiệp vụ không idempotent khi thử nghiệm.

### Bài 4 — Giả lập crash giữa commit và storeOffset

Giả sử eventId **e-101** làm tăng số lượng đơn đã thanh toán trong database. Consumer commit xong nhưng crash trước khi checkpoint; khi chạy lại, event được đọc lại. Thiết kế bảng **processed_events(event_id unique)** để xử lý lại mà không tăng số lượng hai lần.

### Bài 5 — Tính retention

Hệ thống nhận trung bình **2.000 message/giây**, mỗi message khoảng **1 KB**, và phải đọc lại được ít nhất **72 giờ**. Ước lượng dung lượng log chưa tính overhead và replication:

\[
2{,}000 \times 1{,}000 \times 72 \times 3{,}600
= 518{,}400{,}000{,}000\ \text{bytes}
\]

Tức khoảng **518,4 GB dữ liệu thô**. Khi thiết kế thực, cộng overhead, segment, bản sao replication, tăng trưởng bất thường và khoảng an toàn. Giải thích vì sao **x-max-age=3D** và **x-max-length-bytes=100 GB** có thể khiến dữ liệu hết hạn theo dung lượng **trước 72 giờ**.

### Câu hỏi tự đánh giá

1. Vì sao consumer đọc thành công một message trong stream không khiến message ấy biến mất?
2. **first**, **last** và **next** khác nhau ở đâu? Vì sao last không phải đúng một message cuối?
3. Offset được lưu sau khi commit database có thể gây đọc trùng trong tình huống nào?
4. RabbitTemplate có thể publish vào stream queue không? Khi nào cần bật Stream Plugin và dùng RabbitStreamTemplate?
5. Vì sao retention không bảo đảm giữ chính xác từng message đến thời điểm hết hạn?
6. Dùng **quorum queue** hay **stream queue** cho worker gửi email cần DLX? Vì sao?
7. Thứ tự trong một stream có đồng nghĩa với thứ tự toàn cục giữa các partition super stream không?

## 14. Tài liệu tham khảo chính thức

- [RabbitMQ — Streams and Superstreams](https://www.rabbitmq.com/docs/streams): semantics append-only, offset, retention, queue arguments, feature matrix và super streams.
- [RabbitMQ — Stream Plugin](https://www.rabbitmq.com/docs/stream): bật native plugin, TCP/TLS listener, flow control và advertised host/port.
- [RabbitMQ — Stream Core vs Stream Plugin](https://www.rabbitmq.com/docs/stream-core-plugin-comparison): AMQP 0.9.1 so với native stream protocol, tracking và tính năng chuyên biệt.
- [RabbitMQ Stream Java Client — Reference](https://rabbitmq.github.io/rabbitmq-stream-java-client/stable/htmlsingle/): OffsetSpecification, consumer name, tracking strategy và replay.
- [Spring AMQP — Using the RabbitMQ Stream Plugin](https://docs.spring.io/spring-amqp/reference/stream.html): RabbitStreamTemplate, StreamAdmin, StreamListenerContainer, native @RabbitListener và super streams.

---

**Ghi nhớ:** **Stream queue là log append-only được lưu bền và nhân bản**, cho phép nhiều consumer đọc lại cùng message theo **offset**. Việc đọc, ACK hoặc checkpoint **không xóa** bản ghi; **retention** mới quyết định phần lịch sử còn lại. Spring AMQP cho phép publish qua **RabbitTemplate/AMQP 0.9.1** hoặc dùng native **spring-rabbit-stream** để quản lý offset và replay. Luôn thiết kế **idempotency, checkpoint sau xử lý thành công, retention đủ dài và giám sát consumer lag** để hệ thống bất đồng bộ hoạt động đáng tin cậy.
