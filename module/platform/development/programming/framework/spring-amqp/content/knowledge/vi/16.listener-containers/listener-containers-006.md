# Prefetch và số thông điệp chưa được xác nhận

## 1. Vì sao queue đã hết Ready mà việc vẫn chưa xử lý xong?

Trong **Spring AMQP** với RabbitMQ, producer dùng `RabbitTemplate` gửi message vào exchange; routing key và binding đưa message vào queue; `@RabbitListener` nhận và xử lý bất đồng bộ. Khi quan sát RabbitMQ Management UI, ta có thể gặp tình huống:

- Ban đầu queue có **100 Messages Ready**.
- Một consumer kết nối và nhận trước nhiều message.
- Chỉ số **Ready** giảm rất nhanh, nhưng **Unacknowledged** tăng lên.
- Method listener vẫn đang xử lý từng công việc, thậm chí chưa hoàn thành công việc đầu tiên.

Đó là hiệu ứng của **prefetch**: broker chuyển một số delivery cho consumer trước khi nhận ACK của những delivery đã giao. Vì vậy:

> **Prefetch giới hạn số delivery chưa ACK mà RabbitMQ có thể cấp cho consumer trong phạm vi QoS. Prefetch không phải số thread đang xử lý, không phải kích thước queue và không tự chứng minh message đã được xử lý thành công.**

Bài thuộc chương **Listener container** này phân tích **prefetch**, **Messages Unacknowledged**, chế độ ACK, số consumer, `SimpleRabbitListenerContainer`/`DirectMessageListenerContainer`, việc tuning throughput và fairness, cũng như sự tương tác với retry, dead-letter, giao dịch và quan sát hệ thống.

## 2. Ready, Unacknowledged và ACK: vòng đời một delivery

~~~mermaid
flowchart LR
    P["RabbitTemplate producer"]
    E["Exchange + binding"]
    R["Queue: READY"]
    U["UNACKNOWLEDGED<br/>đã giao, chưa ACK"]
    L["@RabbitListener xử lý"]
    A["Consumer ACK<br/>delivery hoàn tất"]
    RE["Requeue / redelivery"]
    DL["Dead-letter exchange / DLQ"]
    P --> E --> R
    R -->|"Deliver theo tín dụng prefetch"| U --> L
    L -->|"ACK"| A
    L -->|"NACK, requeue=true"| RE --> R
    L -->|"Reject, requeue=false"| DL
~~~

| Trạng thái/chỉ số | Ý nghĩa | Điều không nên suy ra |
| --- | --- | --- |
| **Messages Ready** | Message còn ở queue, sẵn sàng giao cho consumer. | Đây là tổng tất cả công việc chưa hoàn tất. |
| **Messages Unacknowledged** | Message đã delivery, broker chưa nhận ACK/NACK phù hợp. | Mọi message đều đang được CPU xử lý; một số có thể đang đợi trong client/container. |
| **Messages Total** | Tổng ready và unacked theo metric của queue. | Số message đã xử lý trong lịch sử. |
| **Consumer ACK** | Broker đã được xác nhận delivery theo chính sách consumer. | Publisher confirm ACK; hai ACK khác mục đích. |
| **Redelivered** | Delivery có thể từng được giao cho consumer trước đó. | Bộ đếm retry nghiệp vụ đầy đủ. |

Ví dụ có 50 message, một consumer prefetch 20, xử lý tuần tự và chưa ACK lần nào:

~~~text
Queue READY:            30
Queue UNACKNOWLEDGED:   20
Method đang xử lý:       1
Message đã xử lý xong:   0
~~~

Sau khi consumer ACK một message, broker có thể cấp message tiếp theo để giữ cửa sổ prefetch. Khi đó Ready giảm nhưng Unacknowledged vẫn có thể gần 20. **Không dùng Ready giảm về 0 làm bằng chứng toàn bộ nghiệp vụ đã hoàn thành**; phải kiểm tra thêm Unacked, ACK rate và transaction của consumer.

### 2.1. Unacked không có nghĩa message đã biến mất

Khi consumer dùng cơ chế ACK và channel/connection bị đóng trước ACK, RabbitMQ thông thường đưa các delivery chưa ACK về trạng thái có thể giao lại. Consumer khác có thể nhận chúng. Tuy nhiên:

- Dữ liệu có thực sự tồn tại qua restart hoặc lỗi node còn phụ thuộc queue durability, message persistence, replication và publisher confirms.
- Consumer có thể đã ghi DB **trước** khi ACK thất lạc. Redelivery khi ấy phải được xử lý **idempotent** bằng event ID/command ID ổn định.
- Requeue có thể ảnh hưởng thứ tự delivery; không mặc định mọi message sẽ trở lại đúng vị trí cũ trong mọi điều kiện đồng thời.

## 3. Prefetch hoạt động bằng tín dụng delivery

RabbitMQ hỗ trợ `basic.qos` với `prefetch_count` trong AMQP 0-9-1. Giả sử prefetch của consumer A là 5:

~~~text
Broker -> Consumer A: m1 [unacked]
Broker -> Consumer A: m2 [unacked]
Broker -> Consumer A: m3 [unacked]
Broker -> Consumer A: m4 [unacked]
Broker -> Consumer A: m5 [unacked]

Consumer A chưa ACK message nào:
  Broker không cấp m6 cho A vì A đã dùng hết tín dụng 5.

Consumer A -> Broker: ACK m1
Broker -> Consumer A: có thể cấp m6
~~~

### 3.1. Prefetch bằng 0 nghĩa là gì?

**`prefetch_count=0` ở RabbitMQ thường nghĩa là không giới hạn số delivery chưa ACK bởi QoS**, không có nghĩa là không giao message hoặc chỉ giao từng message một. Với consumer xử lý chậm, việc đặt 0 có thể cho phép broker đẩy nhiều delivery, gây áp lực bộ nhớ và giảm công bằng khi có consumer khác.

Nếu muốn thử mô hình “một message đang đợi ACK trên mỗi consumer”, bắt đầu với **`prefetch=1`**, không dùng 0.

### 3.2. RabbitMQ thường áp dụng QoS theo từng consumer

AMQP 0-9-1 mô tả `basic.qos` với khái niệm channel, nhưng **RabbitMQ với `global=false` áp dụng `prefetch_count` cho mỗi consumer mới trên channel**, không gom tất cả consumer thành một cửa sổ chung.

~~~text
basic.qos(prefetch_count=10, global=false)

Consumer A: tối đa 10 delivery chưa ACK
Consumer B: tối đa 10 delivery chưa ACK

Tổng có thể gần 20 delivery chưa ACK.
~~~

Với `global=true`, RabbitMQ có thêm giới hạn chung theo channel. Khi có cả giới hạn per-consumer và global, broker phải đáp ứng các giới hạn liên quan và chịu thêm chi phí điều phối. Bài này mặc định xét trường hợp phổ biến **global=false**; không suy luận rằng prefetch là giới hạn tổng cho mọi consumer trong JVM.

### 3.3. Công thức ước lượng

Nếu `P` là prefetch và `C` là số consumer thực sự hoạt động trong phạm vi đang tính, với per-consumer QoS và consumer có ACK:

\[
\text{Số delivery unacked tối đa gần đúng} \le P \times C
\]

Ví dụ có **3 consumer trên mỗi instance**, **2 instances**, prefetch **20**:

\[
20 \times 3 \times 2 = 120
\]

Tổng unacked có thể lên tới khoảng 120 delivery nếu có đủ backlog và không có giới hạn bổ sung. Đây là **trần gần đúng** chứ không phải số lượng broker bắt buộc giao; phụ thuộc queue, thời điểm, số consumer đang đăng ký, ACK rate, batching và cấu hình QoS.

**Lưu ý:** nếu một container nghe nhiều queue, bật `global=true`, hoặc broker dùng auto-ack, cần xác định lại phạm vi tính toán thay vì áp dụng công thức trên một cách máy móc.

## 4. Prefetch không phải concurrency hay channelCacheSize

| Cấu hình | Lớp áp dụng | Vai trò |
| --- | --- | --- |
| `prefetch` | RabbitMQ consumer QoS | Điều tiết delivery chưa ACK theo consumer/channel. |
| `concurrency` | Spring listener container | Số consumer xử lý song song. |
| `channelCacheSize` | `CachingConnectionFactory` | Số channel idle được cache; có thể thành trần channel khi `channelCheckoutTimeout > 0`. |
| `batchSize` / `messagesPerAck` | Listener container | Chính sách gom ACK theo loại container. |
| `publisher-confirm-type` | Producer | Nhận publisher ACK/NACK sau publish, khác consumer ACK. |
| `consumer_timeout` phía broker | RabbitMQ | Theo dõi delivery giữ unacked quá lâu. |
| `maxInFlight` tự triển khai ở producer | Producer application | Trần số lệnh publish đang chờ confirm, không phải prefetch. |

Ví dụ:

- `concurrency=1, prefetch=100`: một consumer có thể giữ gần 100 delivery unacked, nhưng không vì vậy thực thi 100 method cùng lúc.
- `concurrency=10, prefetch=1`: nhiều nhất khoảng 10 consumer có thể giữ mỗi người một delivery, cho phép xử lý song song theo năng lực của từng consumer.
- `concurrency=10, prefetch=20`: khoảng 200 delivery có thể ở trạng thái unacked, nhưng số lời gọi nghiệp vụ **đồng thời** thường phụ thuộc số consumer đang chạy, không phải 200.

Muốn tăng năng lực xử lý đồng thời, cần đánh giá concurrency cùng CPU, DB pool và downstream. Muốn giảm giao trước, điều chỉnh prefetch. **Tăng cả hai cùng lúc** khiến việc xác định nguyên nhân cải thiện/suy giảm trở nên khó khăn.

## 5. ACK mode ảnh hưởng trực tiếp đến Unacked

Spring AMQP có ba chế độ phổ biến:

| `AcknowledgeMode` | Broker nhận xác nhận thế nào? | Prefetch có ý nghĩa không? |
| --- | --- | --- |
| `AUTO` | Container ACK sau khi listener thành công; khi lỗi, reject/requeue theo policy. | **Có**, vì broker còn chờ ACK. |
| `MANUAL` | Code hoặc thành phần quản lý gửi `basicAck/basicNack/basicReject`. | **Có**; quên ACK sẽ giữ slot và có thể ngừng giao thêm. |
| `NONE` | Broker giao theo auto-ack, không đợi consumer ACK thủ công. | Không tạo backpressure theo unacked như AUTO/MANUAL. |

**Quan trọng:** `spring.rabbitmq.listener.simple.acknowledge-mode: auto` là **Spring container AUTO**, **không phải** RabbitMQ `autoAck=true`. Spring container thường ACK sau method thành công; `AcknowledgeMode.NONE` mới là chế độ không chờ manual ACK ở broker.

### 5.1. Manual ACK bị quên

Giả sử prefetch 10, listener MANUAL đã nhận mười delivery nhưng quên gửi ACK. RabbitMQ vẫn giữ chúng là unacked và thường không cấp delivery thứ 11 cho consumer đó. Ready có thể tăng cao dù consumer không nhận thêm message.

Điều này không tự động là lỗi broker: **QoS đang giới hạn đúng theo cấu hình**. Cần kiểm tra code ACK, thread xử lý, container cancellation, batch ACK và log channel.

### 5.2. Batch ACK và tín dụng prefetch

Một số cấu hình listener có thể **gom nhiều ACK** (`batchSize` hoặc `messagesPerAck` tùy container/phiên bản). Những message đã xử lý nhưng ACK chưa được phát vẫn tính vào Unacked. Nếu mức prefetch quá thấp so với batch ACK, framework có thể điều chỉnh hoặc người vận hành cần tăng mức tương ứng.

Không nên đồng nhất *listener nhận batch payload* với *batch acknowledgement*: đó là hai cơ chế khác nhau. Khi điều chỉnh prefetch, đọc cấu hình container đang chạy và đo ACK rate thay vì mặc định “method vừa return là UI lập tức giảm Unacked”.

## 6. Tác động tới throughput, fairness và bộ nhớ

### 6.1. Prefetch nhỏ: dễ phân phối công việc

`prefetch=1` thường là điểm bắt đầu hợp lý cho job xử lý lâu, kích thước lớn hoặc thời gian chạy không đồng đều. Khi consumer A đang xử lý một job 5 giây, nó không thể giữ thêm hàng chục message; consumer B nhanh hơn có thể nhận công việc tiếp theo sau khi ACK.

Nhược điểm: khi message xử lý rất nhanh và có độ trễ network đáng kể, prefetch 1 có thể khiến consumer tạm rảnh trong lúc chờ broker giao tiếp. Throughput khi đó không tận dụng hết khả năng.

### 6.2. Prefetch lớn: pipeline tốt hơn, nhưng không tăng số thread

`prefetch=100` có thể giảm thời gian chờ delivery/ACK khi message nhỏ và xử lý nhanh. Đổi lại:

- Nhiều message được giao trước, làm **Messages Ready** giảm dù nghiệp vụ chưa hoàn tất.
- Tăng **Messages Unacknowledged** và lượng payload/metadata trong client.
- Consumer nhanh mới kết nối khó lấy message đã bị consumer chậm giữ trước.
- Khi một instance chết, nhiều delivery chưa ACK phải được requeue/redeliver.
- Tăng độ trễ đợi trong consumer/client; cải thiện throughput chưa chắc cải thiện p95/p99 end-to-end latency.

Prefetch lớn **không biến một listener tuần tự thành một listener xử lý nhiều tác vụ đồng thời**. Nếu `handle()` mất hai giây thì một consumer vẫn có thể bị giới hạn bởi hai giây đó dù nó giữ một trăm delivery.

### 6.3. Ví dụ hai consumer khác tốc độ

~~~text
Queue có 40 message:

Consumer A: 1 job / 3 giây
Consumer B: 1 job / 0,3 giây

Nếu prefetch=20, A có thể giữ trước nhiều message chưa ACK.
B không được "lấy lại" những message đã cấp cho A chỉ vì B nhanh.

Nếu prefetch=1, A giữ ít message; B liên tục ACK sẽ thường
có cơ hội nhận thêm việc và phân phối có thể cân bằng hơn.
~~~

RabbitMQ không cam kết fairness tuyệt đối trong mọi thời điểm. Prefetch nhỏ chỉ **giảm khuynh hướng giao trước quá nhiều** cho consumer chậm.

### 6.4. Gợi ý mức prefetch để thử nghiệm

| Workload | Mức khởi điểm *để đo thử* | Điểm cần quan sát |
| --- | --- | --- |
| Job kéo dài, xử lý không đồng đều | `1–5` | Fairness, unacked, redelivery, p99. |
| Sự kiện đơn hàng có DB transaction | `5–20` | DB pool, commit latency, throughput hữu ích. |
| Message nhỏ và listener xử lý nhanh | `20–100` | ACK rate, throughput, heap, latency. |
| Payload lớn | `1–10` | Heap/RSS, GC, kích thước message, thời gian hồi phục. |
| Nhiều replicas/concurrent consumers | Bắt đầu nhỏ, tăng từng mức | Tổng số unacked và sức chịu tải của DB/broker. |

Đây là **các khoảng minh họa, không phải mặc định được khuyến nghị cứng** của Spring hay RabbitMQ. Chọn dựa trên tải và đo thực tế.

## 7. Spring Boot 3.x: cấu hình Simple listener container

Dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
}
~~~

Ví dụ `application.yml`:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
    listener:
      type: simple
      simple:
        acknowledge-mode: auto
        prefetch: 10
        concurrency: 2
        max-concurrency: 4
        default-requeue-rejected: false
~~~

Ý nghĩa:

- `prefetch: 10`: tín dụng unacked theo consumer theo QoS RabbitMQ thông dụng.
- `concurrency: 2`: bắt đầu với hai concurrent consumers.
- `max-concurrency: 4`: `SimpleMessageListenerContainer` có thể điều chỉnh số consumer lên tới bốn nếu điều kiện scale phù hợp.
- `acknowledge-mode: auto`: container ACK khi listener hoàn tất thành công.
- `default-requeue-rejected: false`: trong lab, exception chưa được xử lý có thể dẫn tới reject không requeue; **không copy sang production** khi chưa phân loại lỗi tạm thời, retry và DLX.

Khi số consumer scale từ hai lên bốn, trần unacked gần đúng của listener trên một instance có thể tăng từ **20 tới 40**. Cần xem consumer count thực tế trong broker, không lấy riêng cấu hình max làm dữ liệu đo.

**Prefetch mặc định:** trong Spring AMQP 2.x/3.x, listener container thường có prefetch mặc định **250** (đã tăng từ 1 kể từ Spring AMQP 2.0). Đây là mặc định **của Spring container**, không phải kích thước cache channel hay mặc định của RabbitMQ server. Hãy xác minh ở bản thư viện và factory thực tế, nhất là khi có cấu hình override.

## 8. Direct listener container: tham số khác Simple

Với `DirectMessageListenerContainer`:

~~~yaml
spring:
  rabbitmq:
    listener:
      type: direct
      direct:
        acknowledge-mode: auto
        prefetch: 10
        consumers-per-queue: 3
~~~

`consumers-per-queue=3` là số consumer trên **mỗi queue** ở direct container. Không suy luận rằng `simple.concurrency` và `direct.consumers-per-queue` có cùng cơ chế scale động. `SimpleMessageListenerContainer` và `DirectMessageListenerContainer` khác mô hình thread/consumer; prefetch vẫn có ý nghĩa điều tiết delivery cho consumer có ACK.

Nếu có custom `RabbitListenerContainerFactory`, cấu hình trên có thể không áp dụng cho listener sử dụng factory riêng. Khi cần kiểm chứng, xem loại container đang sử dụng, số consumer và QoS thật ở RabbitMQ.

## 9. Java configuration với prefetch rõ ràng

Tạo một listener container factory dành riêng cho queue xử lý đơn hàng:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersListenerConfig {

    @Bean
    SimpleRabbitListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPrefetchCount(10);
        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(4);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        return factory;
    }
}
~~~

Listener chọn factory:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersListener {

    @RabbitListener(
            queues = OrderTopology.QUEUE,
            containerFactory = "ordersListenerFactory")
    public void handle(String eventId) {
        // Production: domain service xử lý idempotent rồi commit DB.
        System.out.println("Processed " + eventId);
    }
}
~~~

Factory riêng này không cần ghi đè default factory của Spring Boot. Nhưng nếu ứng dụng dùng JSON converter, Bean Validation, retry advice hoặc custom ErrorHandler, phải bảo đảm factory riêng cũng có các cơ chế đó; nếu không listener này có thể có hành vi khác.

## 10. Topology và producer để thử nghiệm

Một direct exchange, queue durable và binding:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderTopology {
    public static final String EXCHANGE = "orders.events";
    public static final String QUEUE = "orders.processing.q";
    public static final String ROUTING_KEY = "order.created";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue ordersQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding ordersBinding(Queue ordersQueue, DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
                .to(ordersExchange)
                .with(ROUTING_KEY);
    }
}
~~~

Producer:

~~~java
import java.util.UUID;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrdersPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrdersPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendOne() {
        String eventId = UUID.randomUUID().toString();
        rabbitTemplate.convertAndSend(
                OrderTopology.EXCHANGE,
                OrderTopology.ROUTING_KEY,
                eventId,
                message -> {
                    message.getMessageProperties().setMessageId(eventId);
                    return message;
                }
        );
    }
}
~~~

`RabbitAdmin` có thể tự khai báo topology nếu Spring Boot cấu hình phù hợp. Đừng nhầm đây là mẫu gửi đảm bảo: `convertAndSend` không ném exception chưa chứng minh queue nhận an toàn; khi cần bảo đảm phía publisher, bật **publisher confirms** và **mandatory returns**, theo dõi `CorrelationData`.

### 10.1. Listener chậm để nhìn thấy Unacked

Trong lab, thay listener đơn giản ở mục 9 bằng listener dưới đây:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class SlowOrdersListener {

    @RabbitListener(
            queues = OrderTopology.QUEUE,
            containerFactory = "ordersListenerFactory")
    public void handle(String eventId) throws InterruptedException {
        Thread.sleep(1_000L); // CHỈ sử dụng trong bài thực hành.
        System.out.println("Done: " + eventId);
    }
}
~~~

**Chỉ bật một trong hai listener mẫu** trên queue `OrderTopology.QUEUE` khi đo: nếu cả `OrdersListener` và `SlowOrdersListener` cùng hoạt động, chúng trở thành **competing consumers**, làm tăng số consumer và sai lệch kết quả.

Với `prefetch=10` và hai consumer, broker có thể hiển thị gần **20 Unacked** khi backlog còn lớn, dù chỉ hai method call đang chạy. Đây chính là lý do không xem số Unacked là số thread đang hoạt động.

## 11. Manual ACK: kiểm soát được nhưng phải gửi xác nhận đúng

Nếu cần `AcknowledgeMode.MANUAL`, hãy đặt prefetch và ACK mode trên factory riêng:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ManualFactoryConfig {
    @Bean
    SimpleRabbitListenerContainerFactory manualOrdersFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPrefetchCount(5);
        factory.setConcurrentConsumers(1);
        factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);
        return factory;
    }
}
~~~

Listener xử lý và ACK từng delivery:

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class ManualOrdersListener {

    @RabbitListener(
            queues = OrderTopology.QUEUE,
            containerFactory = "manualOrdersFactory")
    public void handle(
            String eventId,
            Channel channel,
            @Header(AmqpHeaders.DELIVERY_TAG) long tag) throws IOException {
        try {
            processIdempotently(eventId); // Commit nghiệp vụ trước khi ACK.
            channel.basicAck(tag, false);
        } catch (RuntimeException businessFailure) {
            channel.basicNack(tag, false, false); // Reject; DLQ nếu có DLX.
        }
    }

    private void processIdempotently(String eventId) {
        // Minh họa: thay bằng domain service/DB transaction thật.
        System.out.println("Processed: " + eventId);
    }
}
~~~

Đây là **minh họa đơn giản trong lab**: cần bổ sung phân loại exception để không dead-letter nhầm lỗi DB tạm thời. Khi thử nó, tắt các listener khác dùng chung queue. Code không khai báo DLX; muốn quan sát DLQ khi `requeue=false` cần cấu hình DLX/DLQ đúng.

**Lưu ý an toàn:**

- Delivery tag thuộc **channel**, không phải message ID; không ổn định qua redelivery.
- `basicAck(tag, false)` ACK một delivery; `multiple=true` có thể ACK nhiều delivery và không nên dùng tùy tiện khi xử lý bất đồng bộ.
- Không ACK/NACK **hai lần** cùng delivery; broker có thể đóng channel do delivery tag không hợp lệ.
- Nếu ACK bị mất vì connection chết, producer/consumer không thể mặc định broker đã nhận. Consumer phải idempotent.
- Không chia sẻ raw `Channel` tùy tiện giữa các thread.
- Không dùng `basicNack(requeue=true)` vô hạn với payload sai vĩnh viễn: cần retry giới hạn và dead-letter.

Với workload thông thường, `AUTO` giúp đơn giản hóa vòng đời ACK, giảm nguy cơ quên xác nhận.

## 12. Consumer chết, Unacked được xử lý ra sao?

Giả sử consumer A nhận 20 delivery, ACK ba, rồi ứng dụng bị kill:

~~~mermaid
sequenceDiagram
    autonumber
    participant Q as RabbitMQ queue
    participant A as Consumer A
    participant B as Consumer B
    Q->>A: Deliver 20 messages
    A-->>Q: ACK 3 messages
    Note over A: Process bị kill / connection đóng
    Q->>Q: Requeue 17 delivery chưa ACK
    Q->>B: Redeliver khi B còn capacity
    B->>B: Kiểm tra eventId đã xử lý chưa
    B-->>Q: ACK sau transaction
~~~

Những message chưa ACK thường được broker đưa trở lại để consumer khác nhận khi channel/connection đóng. Tuy nhiên:

- Requeue/redelivery có thể làm thứ tự xử lý khác thứ tự enqueue, nhất là khi có nhiều consumer.
- `redelivered` không phải bộ đếm chính xác mọi lần retry của một logical event; producer có thể republish bản sao có delivery mới.
- Với **quorum queues**, delivery limit và chính sách poison message tùy phiên bản/broker policy; nhiều lần requeue có thể dẫn tới dead-letter hoặc drop.
- Nếu DB commit thành công nhưng ACK thất lạc, lần redelivery có thể gây side effect trùng. Dùng **eventId/commandId ổn định** và unique constraint/transaction để chống trùng.

### 12.1. ACK timeout và prefetch là hai cơ chế khác nhau

RabbitMQ có thể dùng **consumer delivery acknowledgement timeout** để phát hiện delivery không được ACK quá lâu. Khi vượt ngưỡng theo cấu hình broker, channel có thể bị đóng, dẫn tới requeue các delivery chưa ACK.

- Prefetch giới hạn **số lượng** unacked.
- Consumer acknowledgement timeout giới hạn **thời gian** unacked.

Tăng prefetch không giải quyết job xử lý quá thời hạn ACK. Với tác vụ rất dài, cần đánh giá khả năng chia nhỏ job, ACK/transaction semantics, timeout broker và idempotency.

## 13. Tương tác với retry, dead-letter và giao dịch

| Cơ chế | Trạng thái tín dụng prefetch | Điều cần quan tâm |
| --- | --- | --- |
| Retry đồng bộ nhiều lần **trong listener** | Message vẫn unacked trong thời gian retry. | Chiếm slot lâu, cần backoff và giới hạn tổng thời gian. |
| `basicNack(requeue=true)` | Delivery cũ được giải quyết, broker có thể giao lại. | Có thể tạo vòng lặp nóng nếu lỗi vĩnh viễn. |
| Reject không requeue với DLX | Delivery cũ kết thúc, broker dead-letter theo policy. | Phải có DLX/binding hợp lệ, nếu không có thể mất dấu message lỗi. |
| Republish sang retry queue | Là message mới theo đường publish khác. | Prefetch của từng queue/consumer là riêng. |
| DB commit xong, ACK mất | Broker có thể redeliver. | Consumer idempotent theo eventId. |
| Publisher confirm ACK | Không giải phóng slot prefetch của consumer. | Nó chỉ xác nhận giai đoạn producer publish. |

**Prefetch không tạo exactly-once delivery**. Cho dù prefetch chỉ là 1, một consumer có thể commit DB rồi chết trước ACK. Sau đó broker giao lại cùng message. Với business event quan trọng, producer nên dùng publisher confirms/outbox để không bỏ sót publish; consumer dùng idempotency và transaction để tránh xử lý trùng.

### 13.1. Tại sao tăng prefetch khi retry nhiều dễ phản tác dụng?

Nếu mỗi message bị retry đồng bộ thêm 15 giây, một consumer giữ tín dụng trong thời gian đó. Với prefetch 100 và nhiều consumers, một lượng lớn delivery có thể đã được giao nhưng chưa hoàn tất, trong khi Ready giảm. Giải pháp là **phân loại lỗi tạm thời/vĩnh viễn**, retry giới hạn, DLX/DLQ và đo thời gian ACK; không chỉ tăng prefetch để che lỗi.

## 14. Quan sát trước khi điều chỉnh cấu hình

### 14.1. RabbitMQ Management UI

Những metric quan trọng:

| Metric | Cách đọc |
| --- | --- |
| `messages_ready` | Broker còn việc sẵn sàng giao. |
| `messages_unacknowledged` | Broker đã giao, chờ ACK từ consumer. |
| `messages` / Total | Tổng ready và unacked tại queue. |
| `consumers` | Số consumer thực tế đã đăng ký; cần đối chiếu cấu hình concurrency. |
| Deliver/get rate | Tốc độ broker giao message. |
| ACK rate | Tốc độ consumer xác nhận delivery. |
| Redeliver rate | Có nhiều delivery phải giao lại không? |
| Consumer capacity (nếu có) | Consumer đang đủ capacity hay bị giới hạn xử lý. |
| DLQ depth | Số message lỗi được dead-letter và chưa giải quyết. |
| Client heap/GC/DB pool | Nhiều unacked có tạo áp lực bộ nhớ hoặc pool? |

**Bảng chẩn đoán nhanh:**

| Triệu chứng | Nghi vấn | Kiểm tra |
| --- | --- | --- |
| Ready thấp, Unacked cao | Prefetch lớn, listener/DB xử lý chậm hoặc ACK bị trì hoãn. | Processing latency, ACK rate, batch/manual ACK, consumer count. |
| Ready cao, Unacked gần `P×C` | Consumer dùng hết tín dụng prefetch. | DB/CPU/downstream, số consumer, thời gian chờ ACK. |
| Ready cao, Unacked gần 0 | Không có consumer, consumer canceled, connection lỗi, không nhận delivery. | Listener logs, channels, consumer count, QoS. |
| Unacked tăng mãi với MANUAL | Code không ACK/NACK hoặc xử lý nền không hoàn tất. | Audit ACK path và delivery tags. |
| Tăng prefetch nhưng throughput không tăng | Bottleneck khác prefetch. | CPU, DB, network, IO, retry, p99 latency. |
| Nhiều redelivery sau khi scale/restart | Consumer chưa ACK hoặc connection đóng. | Event ID/idempotency, ack mode, shutdown grace period. |

### 14.2. CLI kiểm chứng

~~~bash
# Các queue trong virtual host "/".
rabbitmqctl list_queues -p / name messages_ready messages_unacknowledged consumers

# Xem thông tin consumer và prefetch theo CLI/bản RabbitMQ.
rabbitmqctl list_consumers -p /

# Kiểm tra trạng thái connection/channel khi consumer biến mất.
rabbitmqctl list_connections -p / name state channels
~~~

Các lệnh cần quyền quản trị RabbitMQ. Tên cột cụ thể của `list_consumers` có thể khác theo phiên bản; sử dụng `rabbitmqctl help list_consumers` để đối chiếu trên bản đang chạy. Trong production, Management API/Prometheus thường phù hợp hơn việc chạy CLI lặp liên tục.

### 14.3. Đếm đúng số consumer

`concurrency=4` trong source code **không chứng minh đang có bốn consumer**. Cần tính:

- Số application instances đang chạy.
- Container đã start hay đang recover connection/queue.
- `SimpleMessageListenerContainer` có scale động từ min tới max không.
- Listener subscribe một hay nhiều queue.
- Consumer có bị broker cancel hoặc dùng single-active-consumer semantics không.
- `DirectMessageListenerContainer` có số consumer theo queue là bao nhiêu.

Lấy **số consumer thực tế** từ broker rồi mới so sánh Unacked với prefetch.

## 15. Quy trình tuning theo dữ liệu

1. **Đo baseline**: throughput thực, latency p95/p99, Ready/Unacked, consumer count, ACK rate, redelivery, heap/GC và DB pool.
2. **Cố định concurrency**, thử thay prefetch theo mức tăng như 1 → 5 → 10 → 20.
3. **Thử job nhanh và chậm**: so sánh fairness, độ trễ và mức backlog cục bộ.
4. **Kiểm tra bộ nhớ**: payload lớn có thể khiến prefetch cao trở nên đắt.
5. **Thử consumer crash** trong lab: kiểm tra redelivery và idempotency.
6. **Sau đó mới điều chỉnh concurrency** nếu CPU/DB/downstream còn headroom; đo lại từng lần.
7. **Theo dõi production** theo giờ cao điểm và network/broker load, không dựa vào benchmark vài giây.

### 15.1. Ước lượng ngân sách payload

Với `C` consumers, `P` prefetch và payload trung bình `S` bytes:

\[
\text{Kích thước payload inflight bậc độ lớn} \approx C \times P \times S
\]

Ví dụ 12 consumer, prefetch 100, payload trung bình 200 KB:

\[
12 \times 100 \times 200\text{ KB} = 240\,000\text{ KB}
\]

Đây chỉ là **ngân sách payload thô**; metadata, object allocation, broker/client buffering, GC và tỷ lệ message đã giải mã sẽ làm mức RAM thực tế khác nhau. Không coi công thức là số heap đã được xác minh.

## 16. Bài thực hành

Thực hành trên RabbitMQ cục bộ có Management UI và Spring Boot 3.x, không cố tình sleep/kill consumer trên production.

| Bước | Thao tác | Điều cần xác minh |
| --- | --- | --- |
| 1 | Khai báo topology ở mục 10; bật **một** listener chậm `SlowOrdersListener`. | Queue đúng, consumer count, prefetch. |
| 2 | Đặt `prefetch=1`, hai consumer, publish 30 event ID. | Unacked thường gần tối đa 2 khi đủ backlog; phần còn lại Ready. |
| 3 | Restart có kiểm soát với `prefetch=10`, vẫn hai consumer. | Unacked có thể tăng gần 20 và Ready giảm nhanh hơn. |
| 4 | Tăng consumer từ hai lên bốn, giữ prefetch 10. | Trần unacked có thể tăng từ ~20 lên ~40; kiểm tra consumer count thật. |
| 5 | Thử hai consumer khác tốc độ, so sánh prefetch 1 và 20. | Đo fairness và thời gian hoàn tất. |
| 6 | Dừng một consumer đang có unacked trong lab. | Message chưa ACK có thể được redeliver; idempotency không lặp side effect. |
| 7 | Bật manual ACK rồi cố ý giữ vài delivery chưa ACK. | Broker có thể ngừng cấp thêm khi chạm prefetch; đừng quên cleanup thử nghiệm. |
| 8 | Tạo một message lỗi và DLQ thử nghiệm. | Reject không requeue đi tới DLQ nếu topology đúng. |
| 9 | Bật publisher confirms, dừng consumer rồi publish. | Broker có thể ACK publish trong khi message vẫn Ready và chưa có consumer ACK. |

**Phiếu ghi kết quả:**

~~~text
Spring AMQP version / RabbitMQ version:
Queue type:
Listener container: SIMPLE / DIRECT
ACK mode: AUTO / MANUAL / NONE
Configured prefetch:
Actual consumer count:
Payload size / processing time:
Messages Ready:
Messages Unacknowledged:
Deliver rate / ACK rate / redelivery rate:
DLQ depth:
Heap / GC / DB pool:
Publisher confirm behavior:
Consumer crash / recovery:
Idempotency result:
~~~

Hãy đo nhiều mốc thời gian khi còn backlog. Chỉ một ảnh UI ngay sau publish dễ khiến hiểu nhầm Ready giảm nghĩa là đã hoàn thành tất cả công việc.

## 17. Những hiểu nhầm phổ biến

**“Prefetch=10 nghĩa là queue chỉ giữ tối đa 10 message.”** Không. Prefetch chỉ điều tiết delivery chưa ACK; queue có thể chứa nhiều message Ready.

**“Prefetch=10 nghĩa là xử lý 10 method song song.”** Không. Số consumer và mô hình xử lý quyết định concurrency.

**“Prefetch=0 là không nhận message.”** Không. Với RabbitMQ, prefetch 0 thường là không giới hạn tín dụng unacked theo QoS.

**“Messages Ready bằng 0 là xử lý xong.”** Không. Cần kiểm tra Unacked, ACK rate, DB commit và DLQ.

**“Unacked tăng nghĩa là RabbitMQ làm mất message.”** Không. Broker đang chờ xác nhận các delivery đã giao.

**“Spring AUTO nghĩa là RabbitMQ auto-ack.”** Không. Spring `AcknowledgeMode.AUTO` thường ACK sau khi xử lý; `NONE` mới là kiểu không đợi ACK thủ công.

**“Prefetch=1 đảm bảo exactly once.”** Không. Nếu DB commit rồi ACK thất lạc, broker có thể redeliver.

**“Prefetch lớn hơn luôn tăng throughput.”** Không. Nếu bị giới hạn bởi DB, CPU hoặc downstream, tăng prefetch chỉ tăng lượng unacked.

**“Publisher confirm ACK làm giảm Unacked.”** Không. Publisher confirm và consumer acknowledgement là hai giai đoạn độc lập.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Queue có 100 message, hai consumer, mỗi consumer prefetch 10 và chưa ACK. Có thể có tối đa khoảng bao nhiêu Unacked theo QoS thông thường?

**Trả lời:** Khoảng 20 delivery unacked; phần còn lại có thể Ready. Đây là trần gần đúng, không phải số chắc chắn broker giao ngay.

**Câu 2.** `prefetch=20`, `concurrency=1` có tạo 20 thread xử lý không?

**Trả lời:** Không. Một consumer có thể giữ 20 delivery, nhưng số method đang chạy đồng thời phụ thuộc concurrency và cơ chế xử lý.

**Câu 3.** `acknowledge-mode=NONE` có tạo giới hạn unacked như AUTO không?

**Trả lời:** Không. Broker không chờ ACK thủ công; prefetch không điều tiết tín dụng unacked theo cùng cách.

**Câu 4.** Vì sao Ready vẫn cao nhưng consumer không nhận thêm?

**Trả lời:** Có thể đã dùng hết các slot prefetch vì những delivery cũ chưa ACK, hoặc consumer/connection có vấn đề. Kiểm tra Unacked, consumer count, ACK mode và log.

**Câu 5.** Vì sao prefetch 1 vẫn không tránh được xử lý trùng sau khi consumer chết?

**Trả lời:** DB có thể đã commit trước khi ACK đến broker. Message chưa ACK có thể được giao lại; cần event ID, transaction và idempotency.

**Câu 6.** Tăng prefetch có thay thế retry/backoff và DLX không?

**Trả lời:** Không. Prefetch là flow control; retry, reject/requeue, DLX và transaction là chính sách xử lý lỗi riêng.

**Câu 7.** Một app có ba replicas, mỗi replica bốn consumer, prefetch 5. Trần ước lượng unacked là bao nhiêu nếu tất cả đều hoạt động?

**Trả lời:** Khoảng `3 × 4 × 5 = 60`, giả sử QoS per-consumer thông dụng và không có giới hạn khác.

**Câu 8.** Vì sao không kết luận hiệu quả chỉ từ biểu đồ Messages Ready?

**Trả lời:** Ready có thể giảm do broker đã *giao trước* message; chúng vẫn Unacked hoặc xử lý thất bại. Cần đối chiếu ACK rate, redelivery và kết quả nghiệp vụ.

## 19. Tài liệu tham khảo

- [RabbitMQ — Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch): `basic.qos`, giới hạn per-consumer, `global` và sự khác biệt so với mô tả AMQP 0-9-1 truyền thống.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ACK/NACK, QoS, publisher confirm và consumer acknowledgment.
- [RabbitMQ — Consumers](https://www.rabbitmq.com/docs/consumers): consumer lifecycle, delivery acknowledgement timeout và vận hành consumer.
- [RabbitMQ — Queues](https://www.rabbitmq.com/docs/queues): queue, ready/unacked, requeue và delivery.
- [Spring AMQP — Asynchronous Consumer](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): listener containers, prefetch, concurrency và chế độ ACK.
- [Spring AMQP — Choosing a Container](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/choose-container.html): so sánh Simple/Direct listener container.
- [Spring AMQP — Annotation-driven Listener](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html): `@RabbitListener` và container factory.
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.rabbitmq.listener.simple.prefetch` và `spring.rabbitmq.listener.direct.prefetch`.

**Ghi nhớ:** Với **Spring AMQP**, prefetch kiểm soát **bao nhiêu delivery chưa ACK** có thể được RabbitMQ cấp cho consumer, chứ không quyết định số lời gọi nghiệp vụ song song. Ở cấu hình RabbitMQ thông dụng `global=false`, giới hạn này thường là **theo consumer**, khiến tổng Unacked tiềm năng tăng theo **prefetch × số consumer thực tế**. Hãy đánh giá cùng ACK mode, container type, concurrency, batch ACK, throughput và Ready/Unacked. Kết hợp publisher confirms, consumer ACK, retry/dead-letter, giao dịch, idempotency và giám sát để xử lý bất đồng bộ đáng tin cậy.
