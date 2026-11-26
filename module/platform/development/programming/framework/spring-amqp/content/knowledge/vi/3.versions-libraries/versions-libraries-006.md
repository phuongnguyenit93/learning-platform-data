# spring-rabbitmq-client cho RabbitMQ AMQP 1.0 từ Spring AMQP 4.0

## 1. Vì sao Spring AMQP có thêm `spring-rabbitmq-client`?

Từ **Spring AMQP 4.0**, Spring cung cấp module **`org.springframework.amqp:spring-rabbitmq-client`** để ứng dụng Spring gửi và nhận thông điệp qua **AMQP 1.0 trên RabbitMQ**. Đây là phần mở rộng quan trọng bên cạnh đường tích hợp đã quen thuộc với `RabbitTemplate`, `@RabbitListener`, exchange, queue và binding qua **AMQP 0.9.1**.

Hai con số dễ gây nhầm lẫn:

- **Spring AMQP 4.0** là *phiên bản thư viện Spring* giới thiệu module mới.
- **AMQP 1.0** là *phiên bản giao thức* trao đổi thông điệp giữa client và RabbitMQ. Nó không phải bản nâng cấp tuần tự ở cấp API từ AMQP 0.9.1.

RabbitMQ **tích hợp AMQP 1.0 trực tiếp từ RabbitMQ 4.0**. RabbitMQ hiện đại có thể phục vụ cả AMQP 1.0 và AMQP 0.9.1 trên cổng mặc định `5672`: hai phía tự nhận diện giao thức khi thiết lập kết nối. Vì vậy, việc chuyển client không nhất thiết đòi hỏi đổi tên queue/exchange hay triển khai broker thứ hai. Tuy nhiên cần kiểm tra bản RabbitMQ thực tế, cấu hình truy cập, loại queue và các tính năng đang sử dụng.

**Mục tiêu bài học:** chọn đúng dependency, tạo `Environment` và connection factory AMQP 1.0, quản lý topology, publish bất đồng bộ bằng `RabbitAmqpTemplate`, tiêu thụ bằng `@RabbitListener`, hiểu settlement/retry/dead-letter và biết cách quan sát hệ thống khi tích hợp RabbitMQ.

## 2. Chọn đúng thư viện, đúng giao thức

| Nhu cầu | Thư viện Spring / client chính | API thường dùng | Điểm cần nhớ |
| --- | --- | --- | --- |
| Dự án RabbitMQ với AMQP **0.9.1** | `spring-rabbit` với RabbitMQ Java client 0.9.1 | `RabbitTemplate`, `RabbitAdmin`, `CachingConnectionFactory` | Hệ API đã được sử dụng phổ biến; publisher confirms và consumer ack dựa trên AMQP 0.9.1. |
| RabbitMQ với AMQP **1.0**, từ **Spring AMQP 4.0** | **`spring-rabbitmq-client`**, dựa vào `com.rabbitmq.client:amqp-client` | `RabbitAmqpTemplate`, `RabbitAmqpAdmin`, `RabbitAmqpListenerContainer` | Tích hợp chuyên biệt cho **RabbitMQ** và AMQP 1.0. |
| AMQP **1.0** với nhiều loại broker, từ **Spring AMQP 4.1** | `spring-amqp-client` dựa trên **Qpid ProtonJ2** | `AmqpClient`, `@AmqpListener` | Nhánh client AMQP 1.0 *đa broker*, là module khác với `spring-rabbitmq-client`. |

Hai thư viện `spring-rabbitmq-client` và `spring-amqp-client` không đồng nghĩa, mặc dù đều giao tiếp bằng AMQP 1.0. Nếu chỉ kết nối RabbitMQ và muốn dùng các API Spring Rabbit quen thuộc, `spring-rabbitmq-client` là lựa chọn cần tìm hiểu. Nếu ứng dụng phải chuyển đổi giữa RabbitMQ, ActiveMQ hoặc các broker AMQP 1.0 khác, cần đánh giá `spring-amqp-client` từ Spring AMQP 4.1 trở lên.

**Một chi tiết của dependency tree:** `spring-rabbitmq-client` phụ thuộc bắc cầu vào `spring-rabbit` để tái sử dụng một số interface, exception và cơ chế `@RabbitListener`. **Sự có mặt của `spring-rabbit` trong dependency tree không có nghĩa rằng `RabbitAmqpTemplate` đang chạy AMQP 0.9.1.** Protocol được xác định bởi implementation và connection factory đang sử dụng.

## 3. Điều kiện và khai báo dependency

### 3.1. Kiểm tra tương thích

Trước khi thêm module mới:

1. Dùng **Spring AMQP 4.0+**. Dòng 4.0 yêu cầu **Spring Framework 7.0**; khi dùng Spring Boot hãy chọn dòng Boot tương thích với các version Spring được Boot quản lý.
2. Dùng broker **RabbitMQ 4.0+** có AMQP 1.0 native và tài khoản/vhost có quyền làm việc với exchange, queue, binding. AMQP 1.0 của RabbitMQ sử dụng SASL để xác thực.
3. Xác nhận ứng dụng chỉ cần giao thức AMQP 1.0 cho RabbitMQ. Module này **không phải client AMQP 1.0 chung** cho mọi broker.
4. Xác nhận topology và cách xử lý lỗi phù hợp: exchange, routing key, queue, consumer settlement, dead-letter, idempotency. Không suy ra cấu hình retry/transaction của AMQP 0.9.1 sẽ áp dụng y nguyên cho AMQP 1.0.

### 3.2. Maven và Gradle

Ví dụ dùng **Spring AMQP 4.0.6** để minh họa cách khai báo một bản vá thuộc dòng 4.0. Khi áp dụng vào dự án, hãy chọn bản vá được hỗ trợ và đồng bộ với BOM/parent của dự án:

~~~xml
<!-- pom.xml: dự án tự quản lý version của Spring AMQP -->
<dependency>
    <groupId>org.springframework.amqp</groupId>
    <artifactId>spring-rabbitmq-client</artifactId>
    <version>4.0.6</version>
</dependency>
~~~

~~~groovy
// build.gradle: dự án tự quản lý version của Spring AMQP
dependencies {
    implementation 'org.springframework.amqp:spring-rabbitmq-client:4.0.6'
}
~~~

Nếu dự án đã dùng **Spring Boot dependency management/BOM tương thích**, thường nên bỏ version của dependency và để BOM chọn các bản cùng họ; không ghép tùy tiện `spring-rabbitmq-client` 4.x vào một ứng dụng dùng Spring Framework 6 / Boot 3.x.

Một số phiên bản Spring Boot mới có **starter chuyên biệt cho RabbitMQ AMQP 1.0** tên `org.springframework.boot:spring-boot-starter-amqp-rabbitmq`. Khi dùng starter, Spring Boot có thể tự cấu hình `Environment`, `RabbitAmqpTemplate`, `RabbitAmqpAdmin` và listener container factory. Cần tra tài liệu **đúng phiên bản Boot của dự án** thay vì suy rằng tên starter AMQP cũ luôn tương ứng một protocol. Ví dụ phần cấu hình Boot bên dưới sử dụng cách đặt thuộc tính trong tài liệu Spring Boot 4.2.

## 4. Các abstraction mới phối hợp như thế nào?

~~~mermaid
flowchart TD
    APP["Spring application"]
    ENV["com.rabbitmq.client.amqp.Environment"]
    CF["AmqpConnectionFactory / SingleAmqpConnectionFactory"]
    ADM["RabbitAmqpAdmin"]
    TEMPLATE["RabbitAmqpTemplate (async)"]
    LISTENER["RabbitAmqpListenerContainer / @RabbitListener"]
    BROKER["RabbitMQ AMQP 1.0"]
    EXCHANGE["Exchange + binding"]
    QUEUE["Queue"]
    APP --> ENV
    ENV --> CF
    CF --> ADM
    CF --> TEMPLATE
    CF --> LISTENER
    ADM --> BROKER
    TEMPLATE -->|"Publish"| BROKER
    BROKER --> EXCHANGE
    EXCHANGE --> QUEUE
    QUEUE -->|"Delivery"| LISTENER
    LISTENER -->|"Settle: accept / reject / requeue"| BROKER
~~~

| Thành phần | Vai trò |
| --- | --- |
| `Environment` | Entry point của RabbitMQ AMQP 1.0 Java client: cấu hình kết nối dùng chung, executor, metrics/observation; tạo connection đến node/cluster. |
| `AmqpConnectionFactory` | Interface của gói **`org.springframework.amqp.rabbitmq.client`**. `SingleAmqpConnectionFactory` quản lý một AMQP 1.0 connection để các link publisher, consumer và management cùng sử dụng. |
| `RabbitAmqpAdmin` | Khai báo exchange, queue, binding từ các bean Spring; sử dụng khả năng topology management của AMQP 1.0 client. |
| `RabbitAmqpTemplate` | Implementation của `AsyncAmqpTemplate`, cung cấp thao tác send/receive và request-reply; trả về `CompletableFuture`. |
| `RabbitAmqpListenerContainer` | Tạo consumer AMQP 1.0, giao message cho listener, quản lý việc settle và recovery. |
| `RabbitAmqpListenerContainerFactory` | Factory để `@RabbitListener` xây container AMQP 1.0 đúng loại. |

**Phân biệt hai `ConnectionFactory`:** `org.springframework.amqp.rabbitmq.client.AmqpConnectionFactory` dành cho AMQP 1.0 trong module mới; `org.springframework.amqp.rabbit.connection.ConnectionFactory` của `spring-rabbit` dành cho AMQP 0.9.1. Import sai interface sẽ gây lỗi cấu hình hoặc khiến component không dùng đúng đường kết nối.

## 5. Ví dụ cấu hình thủ công bằng Java

Ví dụ này mô tả một ứng dụng Spring AMQP **4.0.x** kết nối RabbitMQ qua **AMQP 1.0**. Giả định RabbitMQ đang chạy tại `localhost:5672` và tài khoản `guest/guest` được phép dùng ở môi trường phát triển cục bộ. Các class dưới đây đặt cùng package để tham chiếu hằng số topology.

### 5.1. Định nghĩa topology và các bean AMQP 1.0

~~~java
import com.rabbitmq.client.amqp.Environment;
import com.rabbitmq.client.amqp.impl.AmqpEnvironmentBuilder;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.annotation.RabbitListenerAnnotationBeanPostProcessor;
import org.springframework.amqp.rabbitmq.client.AmqpConnectionFactory;
import org.springframework.amqp.rabbitmq.client.RabbitAmqpAdmin;
import org.springframework.amqp.rabbitmq.client.RabbitAmqpTemplate;
import org.springframework.amqp.rabbitmq.client.SingleAmqpConnectionFactory;
import org.springframework.amqp.rabbitmq.client.config.RabbitAmqpListenerContainerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DemoTopology {

    public static final String EXCHANGE = "orders.events";
    public static final String QUEUE = "orders.created.q";
    public static final String ROUTING_KEY = "order.created";

    @Bean
    Environment rabbitAmqpEnvironment() {
        return new AmqpEnvironmentBuilder()
                .connectionSettings()
                .uri("amqp://guest:guest@localhost:5672/%2f")
                .environmentBuilder()
                .build();
    }

    @Bean
    AmqpConnectionFactory amqp10ConnectionFactory(Environment rabbitAmqpEnvironment) {
        return new SingleAmqpConnectionFactory(rabbitAmqpEnvironment);
    }

    @Bean
    RabbitAmqpAdmin amqp10Admin(AmqpConnectionFactory amqp10ConnectionFactory) {
        return new RabbitAmqpAdmin(amqp10ConnectionFactory);
    }

    @Bean
    RabbitAmqpTemplate amqp10Template(AmqpConnectionFactory amqp10ConnectionFactory) {
        return new RabbitAmqpTemplate(amqp10ConnectionFactory);
    }

    @Bean(RabbitListenerAnnotationBeanPostProcessor.DEFAULT_RABBIT_LISTENER_CONTAINER_FACTORY_BEAN_NAME)
    RabbitAmqpListenerContainerFactory rabbitListenerContainerFactory(
            AmqpConnectionFactory amqp10ConnectionFactory) {
        return new RabbitAmqpListenerContainerFactory(amqp10ConnectionFactory);
    }

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

Ở đây:

- `Environment` quản lý thiết lập của native RabbitMQ AMQP 1.0 client; `%2f` trong URI là tên vhost mặc định `/` đã được URL-encode.
- `SingleAmqpConnectionFactory` tạo/quản lý kết nối AMQP 1.0. Producer và consumer sử dụng các link của connection này, không dùng channel `com.rabbitmq.client.Channel` của AMQP 0.9.1.
- `RabbitAmqpAdmin` quét các bean `Exchange`/`Queue`/`Binding` khi khởi động để khai báo topology. Trong ví dụ, direct exchange định tuyến `order.created` tới `orders.created.q`.
- Bean container factory được đặt đúng **tên mặc định** mà `@RabbitListener` tìm kiếm. Nếu không khai báo factory và không có auto-configuration phù hợp, annotation có thể không có container AMQP 1.0 để sử dụng.

Đây là cấu hình **thủ công**, phù hợp khi muốn nhìn rõ cách các thành phần kết nối. Với Spring Boot có sẵn auto-configuration tương ứng, thường không cần định nghĩa trùng những bean hạ tầng này.

### 5.2. Publish qua RabbitAmqpTemplate

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.amqp.rabbitmq.client.RabbitAmqpTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final RabbitAmqpTemplate template;

    public OrderEventPublisher(RabbitAmqpTemplate template) {
        this.template = template;
    }

    public CompletableFuture<Boolean> publishOrderCreated(String orderId) {
        return template.convertAndSend(
                DemoTopology.EXCHANGE,
                DemoTopology.ROUTING_KEY,
                orderId
        );
    }
}
~~~

Điểm khác biệt ngay lập tức với `RabbitTemplate` quen thuộc: `RabbitAmqpTemplate.convertAndSend(...)` trả về **`CompletableFuture<Boolean>`** để theo dõi kết quả publish bất đồng bộ. Không nên bỏ qua future trong luồng nghiệp vụ cần biết kết quả gửi. Ví dụ phía gọi:

~~~java
publisher.publishOrderCreated("ORD-1001")
        .whenComplete((accepted, error) -> {
            if (error != null) {
                // Ghi lỗi, đánh dấu trạng thái gửi cần đối soát.
            } else if (Boolean.TRUE.equals(accepted)) {
                // Publish được phía broker xác nhận; chưa phải consumer đã xử lý.
            } else {
                // Broker không xác nhận publish thành công.
            }
        });
~~~

Đoạn gọi này được đặt **bên trong method có biến `publisher`** thuộc kiểu `OrderEventPublisher`. Kết quả future liên quan đến thao tác gửi qua client AMQP 1.0; **nó không có nghĩa rằng `@RabbitListener` đã cập nhật cơ sở dữ liệu thành công**. Với yêu cầu độ tin cậy cao, cần thiết kế timeout, log có event ID và cách đối soát khi trạng thái gửi chưa rõ.

`RabbitAmqpTemplate` vẫn làm việc với abstraction `org.springframework.amqp.core.Message`/`MessageProperties` và `MessageConverter`. Client có thể gửi chuỗi như trên hoặc DTO đã được cấu hình converter thích hợp. Khi gửi DTO dạng JSON, hãy chọn converter nhất quán ở hai phía và có chiến lược tương thích schema.

### 5.3. Nhận qua @RabbitListener

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedConsumer {

    @RabbitListener(queues = DemoTopology.QUEUE)
    public void onOrderCreated(String orderId) {
        System.out.println("Xu ly su kien OrderCreated: " + orderId);
        // Thực tế: kiểm tra event ID trùng, cập nhật DB, xử lý lỗi.
    }
}
~~~

Phương thức `onOrderCreated` vẫn mang annotation quen thuộc. Tuy nhiên, nhờ container factory đã cấu hình, bên dưới nó là **RabbitMQ AMQP 1.0 consumer** thay vì consumer AMQP 0.9.1. Nếu ứng dụng đồng thời có hai protocol, hãy dùng `containerFactory` tường minh cho từng listener để tránh chọn nhầm.

## 6. Cấu hình nhanh bằng Spring Boot khi có starter AMQP 1.0

Trong **Spring Boot 4.2**, tài liệu mô tả ba starter riêng: `spring-boot-starter-amqp-rabbitmq` cho RabbitMQ AMQP 1.0; `spring-boot-starter-rabbitmq` cho RabbitMQ AMQP 0.9.1; và `spring-boot-starter-amqp` cho AMQP 1.0 đa broker. Ví dụ Gradle cho trường hợp RabbitMQ AMQP 1.0:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp-rabbitmq'
}
~~~

Ví dụ `application.yml`:

~~~yaml
spring:
  amqp:
    rabbitmq:
      host: localhost
      port: 5672
      username: guest
      password: guest
      template:
        exchange: orders.events
        routing-key: order.created
        default-receive-queue: orders.created.q
~~~

Trong cấu hình Boot này, các bean `RabbitAmqpTemplate`, `RabbitAmqpAdmin` và container factory có thể được autoconfigure; ứng dụng vẫn phải bảo đảm exchange, queue, binding cần thiết đã được khai báo. Cấu hình `spring.amqp.rabbitmq.*` **khác** `spring.rabbitmq.*` của RabbitMQ AMQP 0.9.1. Đối với dự án Spring AMQP 4.0 dùng Boot đời khác, kiểm tra tính khả dụng của starter và tên property theo tài liệu Boot **đúng version**, hoặc dùng cấu hình Java tại mục 5.

Lưu ý bảo mật: `guest/guest` chỉ phù hợp demo cục bộ. Trong môi trường chạy thật nên tạo user, vhost và permission riêng; dùng secret store và TLS/SSL bundle theo hệ thống triển khai.

## 7. Xác nhận giao nhận trên AMQP 1.0: settlement thay cho basic.ack

Một khác biệt quan trọng ở tầng giao thức là AMQP 1.0 dùng **message settlement/disposition**. Đừng sao chép thao tác `channel.basicAck(deliveryTag, ...)` của AMQP 0.9.1 sang listener AMQP 1.0.

| Tình huống | RabbitMQ AMQP 0.9.1 | RabbitMQ AMQP 1.0 với Spring AMQP |
| --- | --- | --- |
| Gửi | `RabbitTemplate`, có thể cấu hình publisher confirms/returns. | `RabbitAmqpTemplate` và `CompletableFuture` theo dõi kết quả publish. |
| Nhận | Listener container sử dụng AMQP 0.9.1 delivery/channel. | `RabbitAmqpListenerContainer` nhận qua AMQP 1.0 consumer link. |
| Thành công | Consumer ACK (ví dụ `basic.ack`). | **Accept/settle** delivery. |
| Không thể xử lý | Reject/NACK; có thể requeue. | Settlement theo trạng thái **REJECT/REQUEUE** và cơ chế broker tương ứng. |
| Quản lý luồng | Thường thảo luận về channel và prefetch. | AMQP 1.0 sử dụng link và **consumer credit**. |

Mặc định container có thể tự settlement sau khi listener hoàn tất. Nếu cần quyết định trạng thái thủ công, cấu hình `autoSettle=false` (tương ứng ý nghĩa `AcknowledgeMode.MANUAL`) và xử lý bằng `org.springframework.amqp.core.AmqpAcknowledgment` hoặc `com.rabbitmq.client.amqp.Consumer.Context`.

Ví dụ listener minh họa settlement thủ công:

~~~java
import org.springframework.amqp.core.AmqpAcknowledgment;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class ManualSettlementConsumer {

    @RabbitListener(
            queues = DemoTopology.QUEUE,
            ackMode = "#{T(org.springframework.amqp.core.AcknowledgeMode).MANUAL}",
            id = "manualAmqp10Consumer")
    public void process(String orderId, AmqpAcknowledgment acknowledgment) {
        if (orderId.isBlank()) {
            // Lỗi nội dung không thể sửa bằng cách giao lại.
            acknowledgment.acknowledge(AmqpAcknowledgment.Status.REJECT);
            return;
        }

        try {
            // Thay bằng thao tác nghiệp vụ có tính idempotent.
            System.out.println("Da xu ly: " + orderId);
            acknowledgment.acknowledge(); // ACCEPT
        } catch (IllegalStateException temporaryFailure) {
            // Chỉ sử dụng khi có chính sách giới hạn retry / dead-letter.
            acknowledgment.acknowledge(AmqpAcknowledgment.Status.REQUEUE);
        }
    }
}
~~~

**Không chạy `OrderCreatedConsumer` và `ManualSettlementConsumer` trên cùng queue trong một bài thử nếu cần quan sát chính xác cách một listener xử lý:** hai listener sẽ cạnh tranh nhận thông điệp. Khi thử mục 7, hãy tạm bỏ listener `OrderCreatedConsumer` ở mục 5.3 hoặc dùng queue riêng.

`AmqpAcknowledgment.Status.REJECT` thể hiện từ chối; `REQUEUE` yêu cầu giao lại; `acknowledge()` chấp nhận delivery. Thông điệp bị reject có được dead-letter hay bị loại bỏ còn phụ thuộc chính sách queue/DLX. Requeue vô hạn có thể gây vòng lặp liên tục với lỗi không khắc phục được.

## 8. Retry, dead-letter và giao dịch: những gì phải thiết kế thêm

AMQP 1.0 chỉ giải quyết việc trao đổi và settle delivery; **không tự tạo ra exactly-once cho thay đổi nghiệp vụ**.

| Điểm lỗi | Hậu quả có thể xảy ra | Biện pháp |
| --- | --- | --- |
| Publisher nhận lỗi hoặc timeout future | Không chắc message đã được broker chấp nhận hay chưa. | Ghi event ID, trạng thái gửi và đối soát; tránh phát sinh event mới không kiểm soát khi retry. |
| Sai exchange/binding/routing key | Message không vào queue dự kiến hoặc publish thất bại. | Kiểm tra topology, quyền user, kết quả future và log broker. |
| Listener bị dừng trước settlement | Message có thể được giao lại. | Thiết kế handler **idempotent**. |
| Handler thất bại tạm thời | Cần thử lại nhưng tránh quay vòng nóng. | Retry có giới hạn, backoff/TTL/delay phù hợp; theo dõi số lần giao lại. |
| Handler thất bại vĩnh viễn | Thử lại không giúp giải quyết. | Reject, định tuyến đến DLQ khi cấu hình cho phép, ghi dữ liệu đủ để điều tra. |
| Commit DB thành công nhưng settlement thất lạc | Message có thể xuất hiện lần nữa. | Dùng event ID duy nhất, xử lý trùng trong transaction DB. |
| Ghi DB thành công nhưng chưa kịp publish | Thay đổi nghiệp vụ tồn tại mà không có event. | Xem xét **transactional outbox** để lưu DB record và event trong cùng DB transaction. |

**Ví dụ idempotency:** Event `evt-1001` yêu cầu gửi hóa đơn. Listener đã tạo hóa đơn nhưng mất kết nối trước khi accept. Broker có thể giao lại `evt-1001`; listener phải nhận diện ID này đã xử lý và tránh tạo hóa đơn thứ hai. Dùng bảng đánh dấu xử lý với unique constraint và ghi dấu trong cùng transaction với thay đổi nghiệp vụ (nếu khả thi).

**Không suy diễn tương đương transaction:** transaction/channel của RabbitMQ AMQP 0.9.1, database transaction và `CompletableFuture` của publisher là các cơ chế khác nhau. Việc đổi sang `spring-rabbitmq-client` không tự tạo transaction phân tán giữa DB và RabbitMQ. Khi cần cam kết publish cùng thay đổi DB, cân nhắc outbox; khi cần xử lý một event duy nhất, dùng idempotency.

## 9. Quan sát hoạt động và kiểm tra thực hành

Tùy hạ tầng, có thể quan sát RabbitMQ Management UI, log ứng dụng, metrics và tracing/observation của native RabbitMQ AMQP 1.0 client. Các câu hỏi vận hành quan trọng:

- Producer tạo event nào, gửi đến exchange/routing key nào, future hoàn thành thành công/thất bại hay timeout?
- Exchange, binding và queue có tồn tại, cùng vhost/permission với client không?
- Số message **ready** và **unacknowledged** tăng vì thiếu consumer hay vì listener xử lý chậm?
- Listener có nhận đúng message không, có re-delivery lặp lại, số message vào DLQ đang tăng không?
- Người vận hành có theo dấu được cùng `eventId` từ DB nghiệp vụ đến publish, consume, settlement và DLQ không?

### Quy trình thử nghiệm

1. Chạy RabbitMQ phiên bản hỗ trợ AMQP 1.0, tạo user/vhost phù hợp; khởi động ứng dụng dùng cấu hình ở mục 5.
2. Xác nhận exchange `orders.events`, queue `orders.created.q` và binding `order.created` xuất hiện trong RabbitMQ Management UI.
3. Gọi `OrderEventPublisher.publishOrderCreated("ORD-1001")` từ một luồng thử nghiệm hoặc endpoint phát sự kiện; quan sát `CompletableFuture` và log `@RabbitListener`.
4. Dừng consumer rồi gửi thêm sự kiện: queue phải giữ message theo cấu hình hiện có; bật lại consumer và xác nhận nó tiếp tục nhận.
5. Chuyển sang listener manual settlement của mục 7; thử payload rỗng để quan sát reject, và thử lỗi tạm thời để đánh giá chính sách requeue.
6. Cấu hình DLX/DLQ cho queue và retry hữu hạn; mô phỏng một lỗi không thể khắc phục, xác minh message được chuyển đến nơi dự kiến.
7. Gửi cùng `eventId` nhiều lần để xác nhận xử lý nghiệp vụ không lặp; theo dõi metrics và log để thấy sự khác nhau giữa delivery và side effect.

Với hệ thống sản xuất, ưu tiên thêm cảnh báo khi DLQ tăng, khi message ready/unacknowledged vượt ngưỡng, và khi publish future lỗi/timeout.

## 10. Các nhầm lẫn thường gặp

**“Có `spring-rabbit` trong dependency tree tức là vẫn dùng AMQP 0.9.1?”** Không. `spring-rabbitmq-client` kéo theo `spring-rabbit` để dùng chung một số API Spring; protocol thực tế của `RabbitAmqpTemplate` là AMQP 1.0.

**“Đổi `RabbitTemplate` thành `RabbitAmqpTemplate` là đủ?”** Chưa đủ. Cần cấu hình `Environment`, connection factory AMQP 1.0, admin và listener container factory đúng loại; đồng thời rà soát kết quả publish bất đồng bộ, settlement, retry và vận hành.

**“`spring-rabbitmq-client` chạy được mọi broker AMQP 1.0?”** Không. Module này bám vào RabbitMQ AMQP 1.0 Java client. Từ Spring AMQP 4.1 có module riêng `spring-amqp-client` hỗ trợ AMQP 1.0 đa broker dựa trên Qpid ProtonJ2.

**“`@RabbitListener` trong AMQP 1.0 có thể nhận `com.rabbitmq.client.Channel` và gọi `basicAck`?”** Không. Đó là API 0.9.1. Với AMQP 1.0, dùng settlement qua `AmqpAcknowledgment` hoặc `Consumer.Context` nếu cần kiểm soát thủ công.

**“Publish future thành công nghĩa là đơn hàng đã được consumer xử lý?”** Không. Publish outcome chỉ phản ánh giai đoạn gửi/broker; thành công cuối cùng của nghiệp vụ phải được ghi nhận riêng.

**“Mọi message reject đều xuất hiện trong DLQ?”** Không. Broker cần policy hoặc cấu hình dead-letter phù hợp; không có cấu hình đó, message có thể bị loại bỏ. Hãy kiểm tra behavior thực tế của queue đang dùng.

## 11. Tài liệu tham khảo

- [Spring AMQP 4.0 — RabbitMQ AMQP 1.0 Support](https://docs.spring.io/spring-amqp/reference/4.0/rabbitmq-amqp-client.html): các lớp `Environment`, `SingleAmqpConnectionFactory`, `RabbitAmqpAdmin`, `RabbitAmqpTemplate`, `RabbitAmqpListenerContainer` và manual settlement.
- [Spring AMQP 4.0 — What's New](https://docs.spring.io/spring-amqp/reference/4.0/whats-new.html): thời điểm giới thiệu module mới và thay đổi lớn của Spring AMQP 4.0.
- [Spring AMQP — Generic AMQP 1.0 Support](https://docs.spring.io/spring-amqp/reference/amqp10-client.html): phân biệt `spring-amqp-client` từ Spring AMQP 4.1 với module RabbitMQ-specific.
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): starter và thuộc tính cấu hình theo dòng Spring Boot tương ứng.
- [RabbitMQ — AMQP 1.0](https://www.rabbitmq.com/docs/amqp): RabbitMQ 4.0+ hỗ trợ AMQP 1.0 native và cách negotiation giao thức.
- [RabbitMQ AMQP 1.0 Java Client](https://rabbitmq.github.io/rabbitmq-amqp-java-client/stable/htmlsingle/): cấu hình môi trường, connection, message publisher, consumer, metrics và observation.

Điểm cần nhớ khi học **Spring AMQP** là: `RabbitTemplate` là đường quen thuộc cho AMQP 0.9.1; **`RabbitAmqpTemplate`** trong **`spring-rabbitmq-client` từ 4.0** là đường dành cho **AMQP 1.0 trên RabbitMQ**. Dù đổi protocol, ứng dụng xử lý bất đồng bộ đáng tin cậy vẫn cần thiết kế topology, xác nhận giao nhận, retry, dead-letter, idempotency, giao dịch và khả năng quan sát như những phần không thể tách rời.
