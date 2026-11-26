# spring-rabbit-stream và phạm vi hỗ trợ RabbitMQ Streams

## Mục tiêu bài học

Trong hệ sinh thái **Spring AMQP**, cách làm quen thuộc là dùng **RabbitTemplate**, **@RabbitListener**, exchange, queue và binding để xây dựng tác vụ bất đồng bộ. Tuy nhiên, một số nghiệp vụ cần lưu nhiều sự kiện, cho nhiều nhóm đọc lại cùng dữ liệu hoặc xử lý thông lượng lớn. **RabbitMQ Streams** giải quyết những nhu cầu đó bằng cách lưu dữ liệu thành log có thứ tự; thư viện **spring-rabbit-stream** là lớp tích hợp Spring cho RabbitMQ **Stream Java Client**.

Sau bài này, bạn có thể:

1. Phân biệt RabbitMQ stream queue, RabbitMQ Stream Plugin, Stream Java Client và module **spring-rabbit-stream**.
2. Chọn đúng dependency, giao thức, cổng kết nối và phiên bản thư viện.
3. Cấu hình **RabbitStreamTemplate** để publish, **StreamListenerContainer** và **StreamRabbitListenerContainerFactory** để consume; khai báo stream và định vị offset.
4. Nêu chính xác **phạm vi hỗ trợ** và những tính năng của classic/quorum queue không thể áp dụng nguyên xi cho stream.
5. Đánh giá các yêu cầu về replay, retry, checkpoint, chống trùng, quan sát hệ thống và super streams.

## 1. Spring AMQP hỗ trợ RabbitMQ Streams ở lớp nào?

Trước khi chọn thư viện, cần phân biệt bốn lớp:

| Thành phần | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| **RabbitMQ stream queue** | Loại queue có dữ liệu lưu theo **append-only log**, hỗ trợ nhiều lượt đọc từ các offset khác nhau | Thuộc broker; được khai báo bằng queue type **stream** |
| **RabbitMQ Stream Plugin** | Cung cấp giao thức nhị phân riêng để ứng dụng truy cập streams hiệu quả | Bật plugin trên broker; mặc định lắng nghe TCP **5552** |
| **RabbitMQ Stream Java Client** | Client gốc dùng giao thức stream, cung cấp **Environment**, producer, consumer và offset tracking | Package Java **com.rabbitmq.stream** |
| **spring-rabbit-stream** | Adapter của **Spring AMQP** xây trên Stream Java Client | Cung cấp **RabbitStreamTemplate**, **StreamListenerContainer**, **StreamRabbitListenerContainerFactory**, **StreamAdmin** và hỗ trợ quan sát |

**spring-rabbit-stream không phải message broker, cũng không phải Spring Cloud Stream binder.** Đây là một module Spring AMQP bổ sung khả năng giao tiếp native với RabbitMQ Streams. Nó tồn tại song song với các thành phần AMQP 0.9.1 như RabbitTemplate và các listener container thông thường.

Hai con đường hợp lệ để tương tác với stream queue:

~~~mermaid
flowchart TB
    A["Ứng dụng Spring"]
    A --> R["RabbitTemplate / listener AMQP 0.9.1"]
    A --> S["spring-rabbit-stream:<br/>RabbitStreamTemplate / StreamListenerContainer"]
    R -->|"AMQP 0.9.1 :5672<br/>exchange / binding"| Q[("RabbitMQ stream queue<br/>append-only log")]
    S -->|"Stream protocol :5552<br/>Stream Java Client"| Q
    Q --> O["Offset + retention + replay"]
~~~

Đi qua **AMQP 0.9.1** vẫn có thể publish/consume một stream queue đã khai báo đúng loại, nhưng không cung cấp đầy đủ khả năng chuyên biệt như quản lý offset và thông lượng của native stream client. Nếu cần sử dụng RabbitMQ Streams đúng bản chất, ưu tiên luồng **spring-rabbit-stream → Stream Java Client → Stream Plugin**.

## 2. Vì sao stream khác queue công việc thông thường?

Hãy xét dịch vụ đặt hàng phát **OrderCreated**, **OrderPaid** và **OrderCancelled**. Hệ thống phân tích cần đọc lịch sử để xây lại báo cáo; dịch vụ giám sát cần đọc cùng sự kiện nhưng giữ tiến độ riêng.

Với **classic/quorum queue**, consumer hoàn tất và ACK thường làm message được loại khỏi queue. Với **stream**, dữ liệu được ghi nối tiếp vào một log; consumer đọc từ **offset** và việc đọc **không tự xóa message**. Dữ liệu cũ tồn tại theo **retention policy** (giới hạn tuổi hoặc dung lượng), không tồn tại vĩnh viễn theo mặc định nghiệp vụ.

~~~text
Stream: orders.events.stream
Offset     0               1               2               3
           | OrderCreated  | OrderPaid     | OrderCreated  | OrderCancelled
           ---------------------------------------------------------------->

Consumer Analytics: đã xử lý đến offset 3
Consumer Audit:     đã xử lý đến offset 1
Consumer mới:       có thể bắt đầu lại từ offset 0, nếu dữ liệu chưa bị retention loại bỏ
~~~

Các thuộc tính cốt lõi:

- **Append-only:** message mới được ghi ở cuối log; consumer không xóa record sau khi đọc.
- **Non-destructive consumption:** nhiều consumer độc lập có thể đọc cùng message, kể cả tại các thời điểm khác nhau.
- **Replay:** consumer có thể bắt đầu từ đầu, cuối, offset chỉ định hoặc vị trí theo khả năng của client/broker; chỉ replay được phần dữ liệu **còn giữ**.
- **Retention:** loại dữ liệu cũ theo tuổi/dung lượng, áp dụng theo segment; không đồng nghĩa với TTL theo từng message.
- **Replication và persistence:** stream được thiết kế lưu bền và nhân bản; vẫn cần quản trị quorum, ổ đĩa và khả năng phục hồi cụm.

**Hệ quả thiết kế:** stream thích hợp cho lịch sử sự kiện, fan-out nhiều nhóm, dữ liệu đầu vào analytics và các backlog lớn. Một job queue chỉ cần “nhận việc → ACK → xóa”, DLQ, TTL, ưu tiên và retry truyền thống thường phù hợp hơn với classic hoặc quorum queue.

## 3. Phiên bản và dependency cần tương thích

Spring AMQP giới thiệu hỗ trợ RabbitMQ Streams ban đầu từ nhánh **2.4**. Các khả năng tiếp tục được bổ sung theo từng nhánh, nên không nên suy đoán rằng một ví dụ trên tài liệu phiên bản mới sẽ chạy nguyên trạng với mọi bản 2.4/3.x.

| Mốc hoặc thành phần | Ý nghĩa thực tế |
| --- | --- |
| **Spring AMQP 2.4** | Bắt đầu có module **spring-rabbit-stream**, RabbitStreamTemplate và StreamListenerContainer |
| **Spring AMQP 2.4.5** | Bổ sung **adviceChain** và cơ chế retry stateless cho stream listener |
| **Spring AMQP 2.4.13** | Có **StreamAdmin** phục vụ khai báo streams qua native client |
| **Spring AMQP 3.0.5** | Bổ sung hỗ trợ Micrometer Observation cho template và stream listener |
| **Các nhánh Spring AMQP 3.x/4.x** | Chọn tài liệu API và bộ dependency đúng nhánh; kiểm tra lại yêu cầu Java, Spring Framework và Spring Boot tương ứng |

### Maven

Khi dự án dùng **Spring Boot dependency management/BOM**, nên để BOM quản lý phiên bản Spring AMQP:

~~~xml
<!-- Giữ starter RabbitMQ phù hợp với phiên bản Spring Boot đang sử dụng. -->
<dependency>
    <groupId>org.springframework.amqp</groupId>
    <artifactId>spring-rabbit-stream</artifactId>
</dependency>
~~~

Nếu **không dùng BOM**, phải chỉ định phiên bản cùng họ và tương thích với các module Spring AMQP khác. Ví dụ, khi sử dụng nhánh **3.2.x**, phiên bản **spring-rabbit-stream** cần khớp phiên bản **spring-rabbit** và **spring-amqp** đang dùng; không tùy tiện ghép artifact 4.x với 3.x.

### Gradle

~~~groovy
dependencies {
    // Phiên bản lấy từ dependency management hoặc platform/BOM.
    implementation 'org.springframework.amqp:spring-rabbit-stream'
}
~~~

**Lưu ý về starter:** Với Spring Boot 3.x, starter tích hợp RabbitMQ AMQP 0.9.1 phổ biến là **spring-boot-starter-amqp**. Trong tài liệu Spring Boot 4.x hiện hành, RabbitMQ AMQP 0.9.1 dùng **spring-boot-starter-rabbitmq**, còn **spring-boot-starter-amqp** dành cho AMQP 1.0 tổng quát. Cần đọc đúng phiên bản Spring Boot của dự án thay vì sao chép tên starter từ bài hướng dẫn khác phiên bản.

**Không nhầm ba artifact/khái niệm:**

- **spring-rabbit**: tích hợp Spring cho mô hình RabbitMQ AMQP 0.9.1 (RabbitTemplate, listener container truyền thống).
- **spring-rabbit-stream**: tích hợp Spring cho native RabbitMQ Streams.
- **Spring Cloud Stream Rabbit binder**: lớp abstraction binder khác; có hỗ trợ stream ở phạm vi riêng và quy tắc cấu hình riêng. Thêm spring-rabbit-stream không tự động chuyển mọi binding của Spring Cloud Stream sang native stream.

## 4. Chuẩn bị RabbitMQ Streams

Máy chủ RabbitMQ cần hỗ trợ queue type **stream** và bật **rabbitmq_stream** để phục vụ kết nối native. Trên máy broker:

~~~bash
rabbitmq-plugins enable rabbitmq_stream
~~~

Các cổng thường gặp trong môi trường phát triển:

| Cổng | Giao thức/công cụ | Dùng bởi |
| --- | --- | --- |
| **5672** | RabbitMQ AMQP 0.9.1 | RabbitTemplate, RabbitAdmin, listener AMQP truyền thống |
| **5552** | RabbitMQ Stream Protocol, khi plugin được bật | RabbitStreamTemplate, Stream Java Client, StreamListenerContainer |
| **15672** | RabbitMQ Management HTTP UI (khi management plugin được bật) | Quan sát queue, connection và một số thao tác quản trị |

Tên host và cổng được quảng bá trong topology của stream phải truy cập được từ ứng dụng. Khi chạy trong Docker, Kubernetes hoặc qua proxy, lỗi *stream discovery/advertised host* có thể xảy ra **dù đã kết nối được bootstrap endpoint**. Vì thế cần kiểm tra cấu hình advertised host/port và mạng của tất cả node liên quan, không chỉ mở cổng 5552 ở node đầu tiên.

Với môi trường thực tế, tạo user riêng, thiết lập quyền trên vhost, cân nhắc TLS, cấu hình retention và giám sát ổ đĩa. Tài khoản mặc định **guest/guest** chỉ thích hợp cho ví dụ cục bộ theo thiết lập RabbitMQ.

### Khai báo một stream

Một stream queue có tham số **x-queue-type=stream** và phải durable. Nếu ứng dụng đã dùng cơ chế RabbitAdmin của Spring AMQP, có thể khai báo:

~~~java
@Bean
Queue orderStreamQueue() {
    return QueueBuilder.durable("orders.events.stream")
            .stream()
            .build();
}
~~~

**Điểm dễ bỏ sót:** RabbitAdmin thường khai báo bean khi AMQP connection khởi tạo. Nếu ứng dụng chỉ dùng các thành phần native stream, không có AMQP connection kích hoạt RabbitAdmin, bean Queue phía trên có thể **chưa được khai báo thực tế**. Khi đó nên dùng **StreamAdmin** hoặc provisioning bên ngoài (CLI, operator, IaC).

Đối với ví dụ ở phần sau, ta dùng **StreamAdmin** để tự tạo stream với chính native Environment đang dùng.

## 5. Ví dụ: publish và consume stream bằng Spring AMQP

Ví dụ tối thiểu dưới đây dùng một ứng dụng Spring, một RabbitMQ đã bật Stream Plugin ở **localhost:5552**, và payload String đại diện cho một sự kiện. Nếu dùng Spring Boot, bạn có thể tận dụng Environment auto-configuration; ở đây các bean được tạo tường minh để nhìn rõ vai trò của từng thư viện. Các đoạn mã giả định đã có đúng dependency theo phần 3.

### 5.1. Cấu hình Environment, StreamAdmin, RabbitStreamTemplate và listener factory

~~~java
import com.rabbitmq.stream.Environment;
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
public class OrderStreamConfig {

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
            creator.stream("orders.events.stream")
                    .maxAge(Duration.ofDays(7))
                    .create();
        });
    }

    @Bean
    RabbitStreamTemplate orderStreamTemplate(Environment streamEnvironment) {
        return new RabbitStreamTemplate(streamEnvironment, "orders.events.stream");
    }

    @Bean
    RabbitListenerContainerFactory<StreamListenerContainer> orderStreamFactory(
            Environment streamEnvironment) {
        return new StreamRabbitListenerContainerFactory(streamEnvironment);
    }
}
~~~

Trong ứng dụng thực tế, **host, port, credentials, TLS** phải lấy từ cấu hình theo môi trường hoặc secret manager. Bean **Environment** là kết nối native stream; nó **không phải** Spring **Environment** lưu property của ứng dụng. **StreamAdmin** lo provisioning, **RabbitStreamTemplate** là producer và **orderStreamFactory** tạo stream consumer cho **@RabbitListener**.

**Chú ý:** Với retention **7 ngày**, dữ liệu cũ hơn có thể bị loại theo segment; consumer ngừng hoạt động quá lâu có nguy cơ không còn đọc lại được các offset đã mất. Hạn lưu dữ liệu phải khớp với thời gian xử lý, replay và nhu cầu kiểm toán.

### 5.2. Producer: gửi dữ liệu bất đồng bộ

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.rabbit.stream.producer.RabbitStreamTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStreamPublisher {
    private final RabbitStreamTemplate template;

    public OrderStreamPublisher(RabbitStreamTemplate template) {
        this.template = template;
    }

    public CompletableFuture<Boolean> publish(String eventJson) {
        return template.convertAndSend(eventJson);
    }
}
~~~

Ví dụ caller kiểm tra kết quả publish:

~~~java
publisher.publish("{\"type\":\"OrderCreated\",\"orderId\":\"order-42\"}")
        .whenComplete((confirmed, error) -> {
            if (error != null) {
                // Log + xử lý thất bại để gửi lại an toàn.
                return;
            }
            if (!Boolean.TRUE.equals(confirmed)) {
                // Tín hiệu publish chưa được xác nhận thành công.
                return;
            }
            // Broker đã xác nhận publish; consumer chưa chắc xử lý xong.
        });
~~~

**RabbitStreamTemplate** trả về **CompletableFuture&lt;Boolean&gt;**; producer phải quan sát cả kết quả và exception. Khi publish thất bại hoặc không nhận được kết quả rõ ràng, retry có thể tạo message trùng nếu publish trước đó thực sự đã được ghi. Với event quan trọng, cần có **eventId**, outbox/deduplication và chính sách xử lý publish cụ thể.

Khác với RabbitTemplate nhận tham số exchange + routing key, RabbitStreamTemplate ở ví dụ này được khởi tạo cho **một streamName**. Nếu cần native message, sử dụng **send(com.rabbitmq.stream.Message)** và builder của client; nếu cần nhiều stream, tạo template tương ứng hoặc cấu hình abstraction phù hợp.

### 5.3. Consumer: @RabbitListener dùng stream container

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditConsumer {

    @RabbitListener(
            id = "order-audit-stream-listener",
            queues = "orders.events.stream",
            containerFactory = "orderStreamFactory")
    public void onEvent(String eventJson) {
        System.out.println("Audit nhan event: " + eventJson);
        // Thực tế: parse JSON, kiểm tra schema, chống trùng và ghi DB.
    }
}
~~~

**containerFactory="orderStreamFactory" là phần thiết yếu.** Nếu bỏ thuộc tính này trong ứng dụng có listener factory AMQP thông thường làm mặc định, phương thức có thể chạy qua cơ chế consume khác và không có toàn bộ hành vi native stream mong muốn.

Khi sử dụng **StreamRabbitListenerContainerFactory**, tài liệu Spring AMQP hiện hành chỉ hỗ trợ trực tiếp các thuộc tính **id**, **queues**, **autoStartup**, **containerFactory** trên annotation; những thuộc tính như **concurrency** của listener truyền thống có thể bị bỏ qua. **Mỗi stream listener container nhận một stream name**, vì thế không truyền danh sách nhiều queue để mong container tự xử lý như SimpleRabbitListenerContainer.

### 5.4. Tùy biến vị trí đọc và theo dõi offset

Native consumer có thể được cấu hình điểm bắt đầu đọc bằng **OffsetSpecification** và chiến lược lưu offset. Sau đây là **lựa chọn nâng cao** khi muốn kiểm soát việc replay và checkpoint; nó thay cho listener factory mặc định của ví dụ 5.3 khi người học thực hành:

~~~java
@Bean
RabbitListenerContainerFactory<StreamListenerContainer> replayFactory(
        Environment streamEnvironment) {
    StreamRabbitListenerContainerFactory factory =
            new StreamRabbitListenerContainerFactory(streamEnvironment);
    factory.setNativeListener(true);
    factory.setConsumerCustomizer((id, builder) -> builder
            .name("audit-replay-consumer")
            .offset(OffsetSpecification.first())
            .manualTrackingStrategy());
    return factory;
}
~~~

~~~java
@RabbitListener(
        id = "audit-replay-listener",
        queues = "orders.events.stream",
        containerFactory = "replayFactory")
public void onNativeEvent(
        com.rabbitmq.stream.Message message,
        com.rabbitmq.stream.MessageHandler.Context context) {

    // Chuyển đổi và xử lý message vào DB hoặc dịch vụ của ứng dụng.
    processAndCommit(message);
    context.storeOffset();  // Chỉ checkpoint sau khi xử lý thành công.
}
~~~

Trong đoạn trên, **processAndCommit(message)** là hàm nghiệp vụ do bạn tự triển khai; nó phải hoàn thành phần việc cần thiết trước khi checkpoint. **setNativeListener(true)** cho phép handler truy cập native message và **Context**, bao gồm cơ chế lưu offset thủ công. **OffsetSpecification.first()** được dùng để minh họa replay từ điểm sớm nhất **còn tồn tại**; khi xây dựng consumer phục hồi bình thường, cần quy định cách dùng offset đã lưu/offset khởi đầu và kiểm tra chính xác hành vi của client theo cấu hình hiện tại.

Offset lưu trong broker hoặc storage riêng **không đồng nhất** với transaction ở database của bạn. Nếu cập nhật DB xong nhưng tiến trình dừng trước **storeOffset()**, event có thể được đọc lại. Consumer phải **idempotent**; không thể dùng offset như một cam kết exactly-once liên hệ thống.

### 5.5. Spring Boot có thể tự cấu hình một phần

Trong ứng dụng Spring Boot có hỗ trợ RabbitMQ Streams và dependency phù hợp, có thể khai báo tên stream cho template mặc định bằng property:

~~~yaml
spring:
  rabbitmq:
    stream:
      name: orders.events.stream
~~~

Spring Boot có thể tạo/cấu hình bean **RabbitStreamTemplate** dựa trên property và các converter/customizer sẵn có; nếu tự tạo bean cùng mục đích, cần tránh cấu hình trùng và kiểm tra điều kiện auto-configuration của **đúng phiên bản Boot**. Property này **không thay thế** yêu cầu phải có stream queue, quyền truy cập broker và listener factory cho native stream khi cần.

## 6. Phạm vi hỗ trợ: tính năng nào có và không?

Một lỗi thiết kế phổ biến là xem stream như classic/quorum queue có khả năng đọc lại. Thực tế stream có **semantics khác**, và module Spring chỉ ánh xạ một phần API AMQP truyền thống sang stream.

| Khả năng | Classic/quorum queue + Spring AMQP AMQP 0.9.1 | RabbitMQ Streams + spring-rabbit-stream |
| --- | --- | --- |
| **Gửi message** | RabbitTemplate với exchange/routing key | RabbitStreamTemplate gửi vào stream bằng native protocol |
| **Nhận message** | Simple/Direct listener container, @RabbitListener | StreamListenerContainer hoặc StreamRabbitListenerContainerFactory, @RabbitListener theo giới hạn riêng |
| **Dữ liệu sau tiêu thụ** | ACK thường loại message khỏi queue | Đọc **không xóa**, dữ liệu tồn tại theo retention |
| **Chọn nơi bắt đầu đọc** | Thường giao message chưa ACK/còn trong queue | Có thể chọn **offset** và replay dữ liệu còn lưu |
| **Nhiều consumer đọc cùng dữ liệu** | Thường cần nhiều queue để mỗi nhóm có bản sao | Các consumer độc lập đọc cùng stream với tiến độ riêng |
| **Message TTL** | Có trên queue loại phù hợp | **Không có TTL từng message**; dùng retention theo stream |
| **Priority message/consumer** | Có tính năng hỗ trợ trong mô hình queue nhất định | **Không hỗ trợ** theo semantics stream |
| **Dead-letter exchange (DLX)** | Có trên queue loại phù hợp | **Stream queue không hỗ trợ DLX kiểu queue thông thường** |
| **Ack/Nack/requeue truyền thống** | Điều khiển giao lại/xóa message trong queue | Native stream dùng **offset/checkpoint**, không có cách diễn dịch 1:1 |
| **Retry listener** | Các retry interceptor và recoverer AMQP thông thường | Có **stateless retry** theo hỗ trợ của StreamListenerContainer; **không có stateful retry** của container |
| **Super stream** | Không phải topology queue truyền thống | Có hỗ trợ topology partition và tiêu thụ qua native stream client |
| **Micrometer Observation** | Có các hook quan sát AMQP | Có với RabbitStreamTemplate/stream listener từ nhánh tương ứng |

**Các giới hạn cần kiểm tra đặc biệt:**

1. **Không áp dụng DLQ từ queue thông thường:** Nếu một event không xử lý được, ứng dụng cần gửi nó sang **error stream/queue riêng**, ghi trạng thái lỗi hoặc thực hiện công việc phục hồi. Đừng chỉ cấu hình **x-dead-letter-exchange** trên stream rồi kỳ vọng broker tự dead-letter như classic/quorum queue.
2. **Không dùng TTL/priority làm chính sách nghiệp vụ:** Stream xử lý bằng retention và tiêu thụ theo thứ tự trong log. Nhu cầu delay, deadline, deadline retry hay mức ưu tiên thường cần thành phần khác.
3. **Không sao chép thuộc tính của listener:** **concurrency** trên @RabbitListener và nhiều lựa chọn container AMQP có thể bị bỏ qua với stream factory. Dùng **consumer customizer**, partition/super stream và cấu hình Environment đúng API.
4. **Không hiểu checkpoint như ACK xóa dữ liệu:** Offset chỉ đánh dấu điểm tiến độ đọc; message vẫn có thể còn trong log hoặc đã bị retention loại bỏ.
5. **Không dựa vào transaction AMQP truyền thống:** Không được suy luận việc cấu hình **channelTransacted** hoặc RabbitTemplate transaction sẽ tạo transaction giữa native stream, database và hệ thống ngoài. Phân phối vẫn có tình huống giao/lưu lặp, nên cần outbox và idempotency.

Với **AMQP 0.9.1 client kết nối tới queue type stream**, có cơ chế acknowledgement nhằm quản lý credit, nhưng các thao tác đó không biến stream thành classic queue. Khi thiết kế nên chọn rõ đang dùng **native stream consumer** hay **AMQP consumer của stream queue**, tránh lẫn khái niệm ACK với store offset.

## 7. Super Streams: khi nào cần phân vùng?

Một stream riêng có thể đủ cho nhiều bài toán. Khi dữ liệu hoặc số consumer vượt khả năng của một stream, **super stream** chia một luồng logic thành nhiều **partition streams**. Producer phân phối message theo khóa định tuyến; nhóm consumer đọc các partition và vẫn có thể giữ thứ tự **bên trong từng partition**.

~~~mermaid
flowchart LR
    P["Order Event Producer"] --> H{"Routing theo orderId"}
    H --> P0[("orders-0")]
    H --> P1[("orders-1")]
    H --> P2[("orders-2")]
    P0 --> C0["Consumer partition 0"]
    P1 --> C1["Consumer partition 1"]
    P2 --> C2["Consumer partition 2"]
~~~

Ví dụ: các event của **orderId=42** luôn được định tuyến cùng một partition để consumer theo dõi trạng thái đơn theo thứ tự. **Thứ tự giữa các partition không được bảo đảm**; việc tăng số partition/đổi routing có thể ảnh hưởng cách phân phối khóa. Cần thiết kế schema, phân vùng và khả năng idempotency trước khi dùng trong sản xuất.

Spring AMQP hỗ trợ khai báo topology **SuperStream** (chẳng hạn một bean **new SuperStream("orders", 3)** trong môi trường có RabbitAdmin) và **RabbitStreamTemplate** có hàm định tuyến dành cho super stream. Native **StreamListenerContainer** có thể tiêu thụ super stream với cơ chế **single active consumer** theo tên nhóm. Để kiểm soát concurrency thực tế, ngoài tham số concurrency của super stream còn cần xét cấu hình **Environment**; không lấy thuộc tính **concurrency** của @RabbitListener thông thường làm phép thay thế.

Chỉ nên chuyển sang super streams sau khi đo thông lượng, phân phối dữ liệu và độ trễ của một stream. Phân vùng bổ sung chi phí quản trị, điều phối consumer, theo dõi lag và xử lý thay đổi partition.

## 8. Retry, lưu offset và xử lý lỗi cho đáng tin cậy

Spring AMQP Streams tham gia hệ thống bất đồng bộ giống như RabbitTemplate/@RabbitListener truyền thống nhưng yêu cầu một chiến lược phục hồi **dựa trên log và checkpoint**:

| Tình huống | Nguy cơ | Cách xử lý phù hợp |
| --- | --- | --- |
| DB commit xong nhưng producer chưa publish event | Mất sự kiện dù nghiệp vụ thành công | **Transactional outbox**: ghi dữ liệu và bản ghi outbox cùng transaction, publisher đọc outbox để gửi |
| Producer gửi thành công nhưng không nhận được confirm | Có thể gửi trùng khi retry | **eventId/publishingId**, deduplication nơi phù hợp, retry có kiểm soát; không suy luận confirm timeout là broker chưa ghi |
| Consumer xử lý DB xong nhưng chưa store offset | Khi restart có thể đọc lại event | Checkpoint sau commit, idempotent handler bằng khóa eventId hoặc thiết kế tác động bên ngoài an toàn |
| Consumer gặp lỗi tạm thời | Có thể bị kẹt tại một offset hoặc bỏ qua sai dữ liệu | **Stateless retry** giới hạn số lần, backoff, timeout; sau ngưỡng phải ghi sự kiện lỗi/đưa sang kênh phục hồi có kiểm soát |
| Message sai schema hoặc không thể xử lý | Thử lại mãi gây nghẽn tiến độ | Cách ly event lỗi ở **error queue/stream** riêng, lưu metadata và lý do, cho phép xử lý lại thủ công |
| Consumer offline lâu hơn retention | Những offset cũ có thể không còn | Thiết kế retention phù hợp, theo dõi consumer lag, snapshot/bootstrap từ nguồn sự thật nếu cần |

**Stateless retry** của Spring là cơ chế interceptor thử lại khi listener lỗi; đó không phải tính năng broker tự dead-letter native stream. Tài liệu Spring AMQP nêu **StreamRetryOperationsInterceptorFactoryBean** và **StreamMessageRecoverer** cho tình huống xử lý native message; **stateful retry** không được hỗ trợ trên stream listener container.

Với nghiệp vụ nhạy cảm (trừ tiền, xác nhận thanh toán, phát hành hóa đơn), luôn coi **at-least-once và replay** là nguồn có thể gây trùng tác động. Chọn **eventId** ổn định, theo dõi kết quả theo eventId, dùng unique constraint hoặc idempotency key ở hệ thống ngoài. Lưu offset không thể một mình biến các thao tác này thành exactly-once.

## 9. Quan sát và vận hành stream

Trong luồng native stream, ngoài kết quả nghiệp vụ nên quan sát:

- **Publish rate/confirm/failure:** producer gửi nhanh đến đâu, broker xác nhận thế nào, có sự kiện lỗi liên tục không.
- **Stream length, retention và disk usage:** dung lượng log, tốc độ tăng, thời điểm segment cũ bị loại, khả năng đầy ổ đĩa.
- **Consumer offset và lag:** mỗi nhóm đã xử lý tới đâu so với offset cuối còn lưu. Một consumer không có lag chưa chắc nghiệp vụ ngoài broker đã hoàn tất.
- **Retry và poison events:** số lần lỗi, bản ghi chuyển tới error stream/queue, thời gian phục hồi, tỷ lệ xử lý trùng bị phát hiện.
- **Topology và connection:** port 5552, TLS, advertised host, stream leader/replica, số partition và trạng thái single active consumer.

Từ Spring AMQP **3.0.5**, **RabbitStreamTemplate** và stream listener có hỗ trợ **Micrometer Observation**. Có thể bật **observationEnabled** trên template, container hoặc listener factory để thu thập các observation tương ứng; khi observation bật, cơ chế timers cũ của container được xử lý theo observation và có thể bị tắt để tránh đếm trùng. Kết hợp log có **correlationId/eventId**, metric và trace để phân biệt lỗi producer, kết nối, consumer và nghiệp vụ.

Giám sát độ dài stream **khác** giám sát độ dài queue: stream giữ dữ liệu theo retention, nên kích thước lớn không mặc nhiên có nghĩa consumer bị nghẽn. **Consumer lag và tốc độ tiến offset** thường phản ánh sức khỏe xử lý tốt hơn.

## 10. Lựa chọn đúng công nghệ theo bài toán

| Nhu cầu | Hướng ưu tiên | Lý do |
| --- | --- | --- |
| Gửi email, xử lý job, điều phối retry với DLX/TTL | **Classic/quorum queue + RabbitTemplate/@RabbitListener** | Dễ tổ chức job queue, xác nhận xóa message, DLX và quy tắc retry theo queue |
| Lưu lịch sử event để replay, nhiều nhóm cùng đọc | **RabbitMQ Streams + spring-rabbit-stream** | Append-only log, nhiều consumer độc lập, quản lý offset |
| Sự kiện có tốc độ ghi lớn, một stream đạt giới hạn | **Super streams** | Phân vùng thông lượng và consumer, giữ thứ tự trong mỗi partition |
| Đã dùng Spring Cloud Stream binder và muốn thử stream | **Kiểm tra binder version và các thuộc tính hỗ trợ** | Binder là abstraction riêng; hỗ trợ consumer/producer stream có giới hạn theo phiên bản |
| Cần phản hồi đồng bộ ngay lập tức | **REST/gRPC hoặc giao tiếp đồng bộ phù hợp** | Native stream không làm một workflow bất đồng bộ trở thành một RPC transaction |

**Ví dụ thực tế:** Hệ thống bán hàng có thể dùng quorum queue cho command **SendConfirmationEmail**, còn event **OrderPaid** được lưu ở stream để Analytics, Audit và Fraud Detection đọc cùng lịch sử với offset độc lập. Hai công nghệ hoàn toàn có thể cùng tồn tại trong một RabbitMQ cluster, miễn là topology, retention và đường kết nối được quản lý nhất quán.

## 11. Bài tập thực hành

1. **Khởi tạo stream:** Bật **rabbitmq_stream**, kiểm tra cổng 5552, khai báo **orders.events.stream** với retention 7 ngày bằng StreamAdmin. Quan sát stream trong RabbitMQ Management.
2. **Publish:** Gọi **RabbitStreamTemplate.convertAndSend** nhiều lần; đọc kết quả **CompletableFuture&lt;Boolean&gt;** và tạo log tương ứng với lần publish thành công/lỗi.
3. **Consume và replay:** Tạo listener qua **StreamRabbitListenerContainerFactory**. Thực hiện một lượt từ offset đầu, ghi nhận kết quả; thay đổi cách chọn offset, khởi động consumer khác và so sánh tập dữ liệu đọc được.
4. **Kiểm tra giới hạn:** Thử cấu hình một thuộc tính @RabbitListener của container AMQP thông thường như **concurrency** và tìm trong tài liệu lý do nó không áp dụng giống StreamListenerContainer. Phân tích vì sao không nên dựa vào DLX/TTL kiểu classic queue.
5. **Idempotency:** Giả lập consumer xử lý xong DB nhưng dừng trước **storeOffset()**. Chạy lại và thêm bảng chứa **eventId** có unique constraint để bảo đảm không tạo trùng dữ liệu.
6. **Thiết kế hệ thống:** Chia các event theo **orderId** vào ba partition của super stream; giải thích khi nào giữ được thứ tự, khi nào không và cách theo dõi consumer lag theo partition.

### Câu hỏi tự đánh giá

- **RabbitStreamTemplate** khác **RabbitTemplate** ở transport và khả năng nào? Tại sao chỉ thêm dependency chưa đủ để kết nối native?
- Tại sao consumer A đã xử lý một event nhưng consumer B vẫn có thể đọc lại event đó từ stream?
- Nếu stream giữ dữ liệu trong 7 ngày nhưng consumer tắt 10 ngày, điều gì có thể xảy ra?
- Khi nào cần **StreamAdmin** thay vì chỉ khai báo **QueueBuilder.stream()**?
- Vì sao không thể bê nguyên cấu hình **dead-letter exchange, message TTL, stateful retry** của classic queue sang stream?
- Publisher confirm thành công và consumer store offset thành công có đồng nghĩa transaction database đã được hoàn tất đúng một lần không?

## Tài liệu tham khảo chính thức

- [Spring AMQP — Using the RabbitMQ Stream Plugin](https://docs.spring.io/spring-amqp/reference/stream.html): thành phần Spring, khai báo stream, publish, listener, super stream, retry, observation.
- [Spring AMQP — Stream listener container attributes](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): thuộc tính listener container theo loại.
- [Spring Boot — RabbitMQ AMQP và stream template](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): starter và auto-configuration theo phiên bản Boot.
- [RabbitMQ — Streams and Superstreams](https://www.rabbitmq.com/docs/streams): semantics, retention, offset và tính năng hỗ trợ/không hỗ trợ.
- [RabbitMQ — Stream Plugin](https://www.rabbitmq.com/docs/stream): cài plugin, native protocol, TCP listener, TLS, advertised host và cấu hình kết nối.
- [Spring Cloud Stream RabbitMQ binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-stream-consumer.html): phạm vi hỗ trợ stream khi dùng binder, một abstraction khác.

---

**Ghi nhớ:** **spring-rabbit-stream** tích hợp Spring với **native RabbitMQ Streams**, sử dụng **RabbitStreamTemplate** để publish và **StreamListenerContainer/@RabbitListener** với factory phù hợp để consume. **Stream là append-only log**, hỗ trợ replay/retention/offset; không có đầy đủ semantics của classic/quorum queue như **TTL từng message, priority, DLX, ACK xóa message và stateful retry**. Chọn version cùng họ, thiết kế idempotency và lưu offset đúng thời điểm để xử lý bất đồng bộ đáng tin cậy.
