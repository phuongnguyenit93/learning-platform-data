# Micrometer Timer cho `RabbitTemplate` và `@RabbitListener` trong Spring AMQP

Một hệ thống RabbitMQ có thể vẫn đang gửi và nhận message nhưng xử lý ngày càng chậm. Chỉ nhìn số message trong queue chưa cho biết thời gian bị tiêu tốn ở đâu: lúc ứng dụng publish, trong broker, khi listener thực thi logic nghiệp vụ hay trong quá trình gọi một hệ thống bên ngoài. **Micrometer Timer** là công cụ đo **thời gian thực thi và số lần thực hiện** một thao tác, từ đó tạo cơ sở để phân tích độ trễ, throughput và tỷ lệ lỗi.

Trong chương **Quan sát hệ thống** của **SPRING_AMQP**, bài học này tập trung vào Timer ở hai điểm:

1. **`RabbitTemplate`:** thời gian thực thi thao tác gửi qua API của Spring AMQP.
2. **Listener container / `@RabbitListener`:** thời gian xử lý một lần gọi listener.

Ngoài ra, bài viết chỉ ra cách cấu hình Micrometer với Spring Boot Actuator, xem metric bằng Prometheus, tự tạo Timer cho nghiệp vụ và tránh những cách diễn giải sai về publisher confirm, acknowledgement, retry và dead-letter. Giám sát thời gian chỉ có ý nghĩa khi người vận hành hiểu **chính xác điểm bắt đầu và kết thúc phép đo**.

## 1. Timer đo gì và không đo gì?

Một `Timer` trong Micrometer ghi nhận:

- **Số lần đo** (`count`): có bao nhiêu thao tác đã được Timer ghi nhận.
- **Tổng thời gian** (`total time`): tổng thời lượng các lần đo.
- **Phân phối thời gian**: tùy cấu hình registry, có thể thu được các bucket histogram, percentile hoặc giá trị cực đại theo cửa sổ thống kê.

Nếu một Timer ghi bốn lần thực thi với thời gian 10 ms, 20 ms, 30 ms và 40 ms thì:

```text
count                 = 4
total                 = 100 ms
average               = 100 ms / 4 = 25 ms
```

**Timer không tự đo “thời gian message ở trong queue”**. Muốn biết message chờ bao lâu trước khi được consumer nhận, cần đo riêng thời điểm publish/receive, theo dõi độ trễ hàng đợi hoặc sử dụng dữ liệu từ hệ thống broker/tracing phù hợp.

**Timer cũng không tự chứng minh message được xử lý thành công đúng một lần.** Một event có thể được retry ba lần và Timer đếm ba lần gọi listener, dù chỉ có một sự kiện nghiệp vụ logic. Phải đọc metric trong ngữ cảnh ack, retry, redelivery và idempotency.

### Các mốc thời gian trong một luồng bất đồng bộ

```mermaid
sequenceDiagram
    participant P as Producer
    participant T as RabbitTemplate
    participant B as RabbitMQ
    participant L as @RabbitListener
    participant D as Database / API ngoài
    P->>T: convertAndSend(event)
    T->>B: basic.publish
    T-->>P: Lệnh gửi trả về
    Note over P,T: Timer cho template thường kết thúc tại đây
    B-->>P: Publisher confirm (nếu bật; có thể đến sau)
    Note over B: Message có thể chờ trong queue
    B->>L: Delivery
    L->>D: Xử lý nghiệp vụ
    D-->>L: Kết quả
    Note over L,D: Timer listener đo phần thực thi được instrument
    L-->>B: Consumer ack theo cấu hình
```

Khi ứng dụng cần một chỉ số **end-to-end latency** từ lúc tạo event tới lúc xử lý thành công, phải thiết kế phép đo bổ sung có quan hệ theo `eventId`. Cộng đơn giản hai Timer template và listener **không cho ra** độ trễ đầu cuối, vì còn thời gian truyền, queue waiting, scheduling, retry và có thể là broker confirm bất đồng bộ.

## 2. Micrometer và các mức quan sát trong Spring AMQP

Spring AMQP có khả năng tích hợp Micrometer để đo listener và `RabbitTemplate`. Trong các phiên bản hỗ trợ tính năng Timer, framework có thể đăng ký Timer tự động khi Micrometer hiện diện và instrumentation tương ứng được bật. Tên metric thường gặp:

| Đối tượng | Tên meter Micrometer thường gặp | Điều quan sát |
|---|---|---|
| `RabbitTemplate` | `spring.rabbitmq.template` | Thời gian lời gọi thao tác template được instrument |
| Listener container | `spring.rabbitmq.listener` | Thời gian thực thi lời gọi listener được instrument |
| Nghiệp vụ tự định nghĩa | Ví dụ `app.order.processing` | Thời gian logic mà ứng dụng quyết định đo |

**Lưu ý về phiên bản:** tên meter, tập tags mặc định, trạng thái bật/tắt instrumentation và cách kết hợp với Micrometer Observation có thể khác giữa các phiên bản Spring AMQP/Spring Boot. Khi nâng cấp, hãy xem meter thực sự được đăng ký qua `/actuator/metrics` hoặc `MeterRegistry` thay vì tự giả định mọi phiên bản đều tạo cùng một chuỗi metric.

### Timer truyền thống và Observation không phải hai lớp đo cần cộng dồn

Spring AMQP hiện đại hỗ trợ **Micrometer Observation** cho template và listener. Observation có thể tạo metric và trace/span thông qua các handler đã cấu hình. Với đường code đã bật Observation, các Timer Micrometer truyền thống tương ứng thường **bị vô hiệu hóa để tránh đo trùng**.

Vì vậy hãy chọn chủ đích:

- **Chỉ cần Timer/Prometheus:** dùng instrumentation Timer của Spring AMQP và các metric nghiệp vụ bổ sung.
- **Cần metric kết hợp tracing:** dùng Observation với `ObservationRegistry`, exporter/handler phù hợp và kiểm tra tên metric thực tế thu được.

Đừng bật nhiều cơ chế rồi cho rằng `spring.rabbitmq.listener` xuất hiện hai lần là hai giai đoạn riêng biệt. Mục tiêu là **một phép đo có định nghĩa rõ ràng**, không phải càng nhiều metric tương tự càng tốt.

## 3. Thiết lập Spring Boot Actuator và Micrometer

Ví dụ dùng **Spring Boot 3.x, Java 17+, Spring AMQP** và RabbitMQ cục bộ.

### 3.1. Dependencies

Nếu dùng Gradle và Spring Boot dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

`spring-boot-starter-actuator` cung cấp tích hợp Micrometer và endpoint giám sát; Prometheus registry xuất dữ liệu ở định dạng scrape của Prometheus. Trong hệ thống không dùng Prometheus, có thể dùng registry khác nhưng **tên/định dạng xuất metric** sẽ khác.

### 3.2. Cấu hình mẫu

```yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        spring.rabbitmq.listener: true
        spring.rabbitmq.template: true
      slo:
        spring.rabbitmq.listener: 50ms,100ms,500ms,1s
        spring.rabbitmq.template: 10ms,50ms,100ms,500ms
```

Đây là cấu hình **học tập**; `guest/guest` thích hợp cho RabbitMQ local theo cấu hình mặc định, không dành cho môi trường production. Khi bật `/actuator/prometheus`, phải bảo vệ endpoint bằng network policy và authentication phù hợp; các metric có thể làm lộ tên queue, listener hoặc thành phần nội bộ.

Các mức `slo` trong ví dụ là **ngưỡng bucket phục vụ thống kê**, chưa phải cam kết SLO thật. Cần dựa vào ngân sách độ trễ và tải thực tế của hệ thống để chọn bucket phù hợp, tránh tạo quá nhiều time series không cần thiết.

### 3.3. Tạo topology để có dữ liệu đo

```java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TelemetryTopology {
    public static final String EXCHANGE = "demo.telemetry.exchange";
    public static final String QUEUE = "demo.telemetry.orders";
    public static final String ROUTING_KEY = "order.created";

    @Bean
    public DirectExchange telemetryExchange() {
        return new DirectExchange(EXCHANGE);
    }

    @Bean
    public Queue telemetryQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    public Binding telemetryBinding() {
        return BindingBuilder.bind(telemetryQueue())
                .to(telemetryExchange()).with(ROUTING_KEY);
    }
}
```

Khi dùng auto-declare của `RabbitAdmin`, runtime phải có quyền khai báo topology trên đúng vhost; nếu topology được provision trước, có thể giảm quyền của ứng dụng. Các ví dụ bên dưới gửi String message để không cần converter JSON tùy biến.

## 4. Timer tự động cho `RabbitTemplate`

Spring AMQP có hỗ trợ ghi Timer cho các thao tác gửi bằng `RabbitTemplate`, thường qua tùy chọn `micrometerEnabled`. Với phiên bản sử dụng Timer truyền thống và `MeterRegistry` có mặt, các Timer này thường được bật theo mặc định; để diễn đạt ý định rõ ràng, có thể bật trên bean:

```java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TelemetryRabbitTemplateConfig {

    @Bean("telemetryRabbitTemplate")
    public RabbitTemplate telemetryRabbitTemplate(
            ConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMicrometerEnabled(true);
        return template;
    }
}
```

Đoạn này sử dụng **Timer mode**; nếu ứng dụng đã bật Observation cho template, hãy dùng một chiến lược nhất quán thay vì giả định cả hai cùng hoạt động. Có thể thêm các tag tùy biến ổn định theo API Spring AMQP của phiên bản đang dùng.

Producer gửi event:

```java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class TelemetryOrderPublisher {
    private final RabbitTemplate template;

    public TelemetryOrderPublisher(
            @Qualifier("telemetryRabbitTemplate") RabbitTemplate template) {
        this.template = template;
    }

    public void publish(String eventId) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId trống");
        }
        template.convertAndSend(
                TelemetryTopology.EXCHANGE,
                TelemetryTopology.ROUTING_KEY,
                eventId);
    }
}
```

Sau khi thực hiện vài lần publish, có thể truy vấn tên meter theo phiên bản:

```bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/spring.rabbitmq.template
curl -s http://localhost:8080/actuator/prometheus
```

Endpoint `/actuator/metrics/spring.rabbitmq.template` trả về dạng thống kê cùng các tag khả dụng khi meter đã được đăng ký. Nếu chưa thấy meter, hãy xác nhận đã thực sự gọi `RabbitTemplate`, Micrometer registry đã được tạo, chế độ Timer/Observation và Actuator exposure đúng.

### `RabbitTemplate` Timer không phải publisher confirm latency

Đây là lỗi diễn giải phổ biến nhất. Phép đo ở thao tác `convertAndSend(...)` tập trung vào **đường thực thi cục bộ của lời gọi template**. Khi dùng publisher confirms bất đồng bộ, broker có thể xác nhận publish **sau khi** phương thức đã return.

Ví dụ:

```text
0 ms   : bắt đầu RabbitTemplate.convertAndSend()
7 ms   : convertAndSend() return
50 ms  : broker gửi publisher confirm ack
90 ms  : consumer bắt đầu xử lý
135 ms : consumer hoàn tất

Template call duration ≈ 7 ms
Publisher confirm latency ≈ 50 ms
Queue wait / consumer latency: cần đo riêng
```

Không được lấy Timer template 7 ms để kết luận rằng message đã durable trên broker hoặc consumer đã xử lý trong 7 ms. Nếu cần **publish-to-confirm latency**, hãy tạo phép đo chuyên biệt bắt đầu trước publish và kết thúc khi nhận callback/future confirm theo `CorrelationData`, đồng thời xử lý `nack` và trạng thái không rõ kết quả khi timeout.

Một publisher confirm `ack` cũng **không khẳng định message đã được route tới một queue**. Khi có yêu cầu phát hiện unroutable publish, hãy phối hợp `mandatory`/returns hoặc cơ chế định tuyến tương đương. Bộ metric riêng nên theo dõi confirm `ack`, `nack`, returned message và thời gian chờ confirm, thay vì chỉ nhìn Timer template.

## 5. Timer tự động cho listener container

Với `@RabbitListener`, listener container là nơi framework nhận delivery và gọi method xử lý. Tính năng Micrometer Timer của container có thể tạo metric thường mang tên `spring.rabbitmq.listener`.

Ví dụ dùng factory riêng:

```java
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class TelemetryListenerConfiguration {

    @Bean("telemetryListenerFactory")
    public SimpleRabbitListenerContainerFactory telemetryListenerFactory(
            ConnectionFactory connectionFactory,
            SimpleRabbitListenerContainerFactoryConfigurer configurer) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        configurer.configure(factory, connectionFactory);
        factory.setMicrometerEnabled(true);
        factory.setConcurrentConsumers(2);
        factory.setPrefetchCount(10);
        return factory;
    }
}
```

`configurer.configure(...)` giữ lại thiết lập được Spring Boot quản lý cho factory; các setter sau đó thể hiện lựa chọn riêng cho listener này. Nếu đang dùng Observation mode cho listener, không cố bật legacy Timer đồng thời chỉ để có thêm một metric trùng.

Listener đơn giản:

```java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class TelemetryOrderListener {

    @RabbitListener(
            id = "telemetry-order-listener",
            queues = TelemetryTopology.QUEUE,
            containerFactory = "telemetryListenerFactory")
    public void receive(String eventId) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId trống");
        }

        // Trong ứng dụng thực: ghi DB hoặc gọi service nghiệp vụ idempotent.
        System.out.println("Received " + eventId);
    }
}
```

Khi listener thực thi, timer framework có thể ghi nhận thời lượng và kết quả lời gọi. Các tag thường dùng để phân biệt listener, queue, kết quả và exception, nhưng **tên tag và giá trị cụ thể cần được kiểm chứng trên meter của phiên bản đang chạy**.

Ví dụ truy vấn:

```bash
curl -s http://localhost:8080/actuator/metrics/spring.rabbitmq.listener
```

### Điều gì nằm trong khoảng đo listener?

Thời lượng listener thường phản ánh phần code được container instrument khi gọi listener, bao gồm việc xử lý diễn ra đồng bộ trong lời gọi đó. Nó **không tự tính** thời gian message nằm chờ trong RabbitMQ trước khi giao tới consumer.

Khi listener:

- **Gọi database đồng bộ:** thời gian chờ database có thể góp vào duration listener.
- **Ném exception:** phép đo vẫn có thể được ghi nhận với tag kết quả/thất bại theo instrumentation.
- **Retry ngay trong listener advice:** tổng số lần thử và phạm vi Timer phụ thuộc vào vị trí lời gọi được instrument trong chuỗi advice; cần kiểm tra bằng integration test.
- **Trả `CompletableFuture`, `Mono` hoặc xử lý bất đồng bộ:** thời điểm kết thúc lời gọi Java và thời điểm nghiệp vụ bất đồng bộ hoàn thành có thể khác nhau. **Không mặc định Timer built-in luôn đo đến khi kết quả async hoàn tất** mà không xác nhận ngữ nghĩa của phiên bản/adapter.
- **Ack MANUAL:** một method return nhanh không chứng minh ack đã được broker nhận. Timer listener không thay thế metric xác nhận giao nhận.

Nếu cần đo chính xác một nghiệp vụ bất đồng bộ từ lúc bắt đầu đến lúc hoàn tất, hãy tự tạo phép đo gắn với tín hiệu completion cuối cùng thay vì phụ thuộc vào duration của method khởi tạo công việc.

## 6. Tự tạo Timer cho bước nghiệp vụ quan trọng

Timer framework thường cho biết “listener chạy bao lâu”. Trong thực tế còn cần biết bước nào làm chậm: kiểm tra dữ liệu, truy vấn database, ghi trạng thái, gọi HTTP API hay xác nhận nghiệp vụ.

Ví dụ dưới đây tạo **Timer riêng cho logic xử lý đơn hàng** bằng `MeterRegistry`. Nó khác với Timer tự động cho listener và vì vậy **không nên cộng hai tổng thời gian** như hai giai đoạn nối tiếp: khoảng đo có thể chồng lấp.

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class MeasuredOrderListener {
    private final MeterRegistry registry;
    private final Timer successTimer;
    private final Timer failureTimer;

    public MeasuredOrderListener(MeterRegistry registry) {
        this.registry = registry;

        this.successTimer = Timer.builder("app.orders.processing")
                .description("Thời gian xử lý nghiệp vụ theo lần gọi")
                .tag("result", "success")
                .register(registry);

        this.failureTimer = Timer.builder("app.orders.processing")
                .description("Thời gian xử lý nghiệp vụ theo lần gọi")
                .tag("result", "failure")
                .register(registry);
    }

    @RabbitListener(
            id = "measured-order-listener",
            queues = "demo.measure.orders")
    public void onEvent(String eventId) {
        Timer.Sample sample = Timer.start(registry);
        try {
            if (eventId == null || eventId.isBlank()) {
                throw new IllegalArgumentException("eventId trống");
            }

            // Ví dụ tối giản: thay bằng lời gọi nghiệp vụ thực.
            System.out.println("Processing " + eventId);
            sample.stop(successTimer);
        } catch (RuntimeException ex) {
            sample.stop(failureTimer);
            throw ex; // Giữ nguyên chính sách retry/reject/DLQ của listener.
        }
    }
}
```

**Lưu ý khi chạy thử:** method `onEvent` ở trên là một **phương án listener khác** với `TelemetryOrderListener` ở mục 5, dùng queue `demo.measure.orders` chưa được khai báo trong topology mẫu. Muốn chạy độc lập, hãy khai báo queue đó hoặc đổi sang `TelemetryTopology.QUEUE` và chỉ bật **một** consumer tương ứng khi so sánh. Nếu cả hai listener nghe cùng một queue, chúng là *competing consumers*: mỗi message được phân phối cho một trong các consumer, không được gửi bản sao tới cả hai.

### Tại sao dùng `Timer.Sample`?

`Timer.Sample` ghi mốc bắt đầu trước khi biết kết quả. Khi hoàn tất, ta chọn Timer đã có tag `result=success` hoặc `result=failure`. Cách này tránh phải tạo meter theo giá trị tùy ý từ payload.

Trong code trên, mỗi nhánh gọi `sample.stop(...)` đúng một lần; exception được ném tiếp để container vẫn áp dụng retry/ack/dead-letter đúng chính sách. Không nên bắt exception rồi return bình thường **chỉ để metric trông đẹp hơn**: như vậy có thể khiến container ack một message chưa được xử lý xong.

Với tác vụ thực tế, nên tách riêng những Timer có ý nghĩa nghiệp vụ:

| Tên đề xuất | Khoảng đo | Vì sao hữu ích |
|---|---|---|
| `app.orders.validation` | Kiểm tra/deserialize dữ liệu nghiệp vụ | Tìm lỗi xử lý payload bất thường |
| `app.orders.database` | Giao dịch đọc/ghi database | Phát hiện downstream DB chậm |
| `app.orders.partner_call` | Gọi HTTP API ngoài | Xác định latency và timeout của đối tác |
| `app.orders.processing` | Toàn bộ xử lý nghiệp vụ | Theo dõi mục tiêu hiệu năng của listener |

Các Timer trên có thể **lồng nhau**. Ví dụ `processing` bao gồm cả `database` và `partner_call`; không cộng tổng thời gian của chúng với nhau như những đoạn không giao nhau. Khi muốn đo thời gian xếp hàng tới lúc xử lý, cần metric riêng cho tuổi event/message.

## 7. Cách đọc metric bằng Actuator và Prometheus

Micrometer sử dụng một tên meter logic như `spring.rabbitmq.listener`. Registry Prometheus thường chuyển sang tên chuỗi phù hợp với Prometheus, ví dụ:

```text
spring_rabbitmq_listener_seconds_count
spring_rabbitmq_listener_seconds_sum
spring_rabbitmq_listener_seconds_bucket   (khi histogram được bật)

spring_rabbitmq_template_seconds_count
spring_rabbitmq_template_seconds_sum
spring_rabbitmq_template_seconds_bucket   (khi histogram được bật)
```

Tên hậu tố và chuỗi đầy đủ cần **kiểm chứng bằng scrape thực tế**, bởi phiên bản Micrometer/Prometheus client và cấu hình Observation có thể ảnh hưởng output. `seconds_count` đếm số phép đo, còn `seconds_sum` cộng tổng thời gian đã quy đổi sang giây; bucket xuất hiện khi có cấu hình phân phối tương ứng.

### 7.1. Throughput xử lý từ Timer count

Ví dụ PromQL cho số lần gọi listener được instrument mỗi giây:

```promql
sum(rate(spring_rabbitmq_listener_seconds_count[5m]))
```

Đây là **tốc độ lần xử lý được đo**, không mặc định là số **event logic duy nhất** xử lý thành công. Nếu retry/redelivery xảy ra, một event có thể tạo nhiều lần đo. Muốn throughput nghiệp vụ thành công, cần lọc tag kết quả thực tế hoặc thêm counter idempotent cho event hoàn tất.

### 7.2. Thời gian trung bình

```promql
sum(rate(spring_rabbitmq_listener_seconds_sum[5m]))
/
sum(rate(spring_rabbitmq_listener_seconds_count[5m]))
```

Kết quả theo **giây trên một lần đo**. Chỉ nên diễn giải khi mẫu đủ nhiều; khi count-rate bằng 0, phép chia có thể không hữu ích cho dashboard.

### 7.3. P95 từ histogram

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(spring_rabbitmq_listener_seconds_bucket[5m])
  )
)
```

Đây là **ước lượng phân vị** từ histogram. Muốn truy vấn này hoạt động, phải thực sự có bucket phù hợp trong dữ liệu Prometheus. Không thể tính p95 chính xác chỉ từ `count` và `sum`. Đồng thời tránh gộp nhiều listener có đặc điểm rất khác nhau vào một biểu đồ p95 nếu mục tiêu là chẩn đoán từng loại tác vụ.

### 7.4. Quan sát riêng từng listener

Trong thực tế, các timer listener thường có tag nhận diện listener/queue. Sau khi xem tên tag tại `/actuator/metrics/spring.rabbitmq.listener` hoặc Prometheus, hãy lọc bằng **giá trị tag thật** thay vì tự suy đoán.

Ví dụ cú pháp minh họa nếu registry có label `listener_id`:

```promql
sum(
  rate(
    spring_rabbitmq_listener_seconds_count{
      listener_id="telemetry-order-listener"
    }[5m]
  )
)
```

**`listener_id` chỉ là tên label minh họa.** Tên label được xuất có thể khác, ví dụ được chuẩn hóa từ tag Micrometer gốc. Hãy kiểm tra một chuỗi mẫu trong `/actuator/prometheus` trước khi áp dụng bộ lọc vào dashboard.

## 8. Thiết kế tag: đủ phân loại, không làm nổ cardinality

Micrometer xác định một time series qua **tên meter + tập tag**. Nếu một tag nhận hàng triệu giá trị khác nhau, backend có thể phải lưu hàng triệu series.

| Tag | Có nên dùng? | Lý do |
|---|---|---|
| `listener` hoặc `listenerId` ổn định | Có | Phân biệt số lượng nhỏ các listener đã khai báo |
| `queue` đã biết | Có, với số queue được kiểm soát | Hỗ trợ tìm queue gây chậm |
| `operation` hữu hạn: `publish`/`consume` | Có | Phân biệt các hoạt động |
| `result`: `success`/`failure` | Có | Tính tỷ lệ thất bại |
| `exception_category` hữu hạn | Có thể | Ví dụ `validation`/`downstream`/`timeout` |
| `eventId`, `messageId`, `orderId` | **Không** | Giá trị gần như vô hạn, gây nổ time series |
| `correlationId` hoặc `traceId` | **Không** | Dùng cho tracing/log, không dùng làm metric label |
| `exception.getMessage()` | **Không** | Nhiều giá trị, có thể chứa dữ liệu nhạy cảm |
| `tenantId` nếu hàng chục nghìn tenant | Cần cân nhắc rất kỹ | Có thể tạo cardinality lớn; ưu tiên phân nhóm hữu hạn |

Một metric có 10 listener × 5 queue × 3 outcome × 4 môi trường đã có thể tạo hàng trăm series trước khi tính histogram bucket. Với nhiều bucket, số series tăng đáng kể. Vì vậy, histogram nên bật có chọn lọc cho những Timer thật sự cần đo p95/p99.

**Không lấy email, token, secret, ID người dùng hoặc toàn bộ routing key có giá trị động làm tag.** Các dữ liệu đó thuộc log/tracing đã che thông tin nhạy cảm, không thuộc nhãn metric.

## 9. Kết hợp Timer với metric broker và tracing

Timer ứng dụng không có toàn bộ góc nhìn của RabbitMQ. Để chẩn đoán bottleneck, nên kết hợp:

| Nguồn dữ liệu | Chỉ số/quan sát | Ví dụ kết luận |
|---|---|---|
| Timer `RabbitTemplate` | Thời lượng lệnh publish | Producer đang chậm trong gọi API client |
| Publisher confirm metric | Confirm latency, `ack`/`nack`, timeout | Broker/đường truyền đang chậm xác nhận publish |
| RabbitMQ broker | Queue ready, unacked, consumer count | Backlog tăng do thiếu consumer hoặc prefetch/ack bị nghẽn |
| Timer listener | Thời lượng thực thi listener | Một worker/loại event xử lý chậm |
| Timer downstream | DB/HTTP latency | Nguyên nhân là database hoặc API đối tác |
| Retry/DLQ | Retry rate, redelivery, dead-letter depth | Hệ thống có lỗi lặp hoặc poison messages |
| Trace + log theo `eventId` | Hành trình cụ thể của event | Khoanh vùng một trường hợp có độ trễ bất thường |

Ví dụ diễn giải:

```text
RabbitTemplate p95:       8 ms
Listener p95:           120 ms
Queue ready:            tăng nhanh
Consumer count:         1
External API p95:       110 ms

Nhận định sơ bộ:
Producer gửi nhanh, listener chờ API ngoài,
queue bắt đầu tích tụ vì consumer không theo kịp.
```

Không kết luận nguyên nhân chỉ dựa vào các số p95 cộng lại: đó là phân vị của những tập mẫu khác nhau, **không cộng tuyến tính** được. Khi cần điều tra cụ thể, sử dụng tracing để xem các đoạn xử lý trong cùng một sự kiện, cùng với timestamp được đo ở điểm thích hợp.

### Đo queue wait và end-to-end latency

Một cách tiếp cận là producer gắn thời điểm tạo sự kiện và consumer đo thời gian từ mốc đó tới lúc nhận/hoàn tất. Nhưng cần chú ý:

- Đồng hồ giữa các host có thể lệch; đo timestamp xuyên host có sai số clock skew.
- Một event có thể chờ trong producer outbox trước khi publish, hoặc được retry sau nhiều phút.
- Broker có thể redeliver event; cùng event có nhiều latency quan sát khác nhau.
- Nếu sự kiện đã tồn tại lâu vì batch/backfill, duration từ lúc tạo có thể không còn đại diện cho queue latency.

Muốn định nghĩa đúng SLI, hãy phân biệt **publish-to-receive**, **receive-to-done** và **event-created-to-done**. Không dùng một Timer mang tên “latency” mà không biết điểm đo.

## 10. Timer, lỗi và sự bảo đảm giao nhận

Khi listener có exception, Spring AMQP có thể retry, requeue hoặc dead-letter tùy cấu hình. Tác động đến metric:

1. **Lỗi validation:** Timer có thể ghi duration ngắn nhưng vẫn là thất bại; nên có metric kết quả/error classification.
2. **Lỗi downstream:** Timer dài nếu HTTP/database chậm; cần giám sát timeout và retry count.
3. **Redelivery:** cùng `eventId` được gọi lại, Timer tăng count; metric count không bằng số event độc nhất.
4. **Ack MANUAL:** method kết thúc và ghi Timer chưa chắc ack thành công; cần quan sát channel/requeue/unacked.
5. **Publisher confirm bất đồng bộ:** Timer template kết thúc nhưng broker chưa xác nhận; cần đo confirm riêng.
6. **DLQ:** số message đến DLQ là tín hiệu lỗi nghiệp vụ/vận hành, không thể suy từ latency Timer.

Nếu theo dõi retry và kết quả, nên tổ chức metric sao cho **kết quả của mỗi lần thử** và **kết quả cuối cùng của một event logic** được phân biệt. Ví dụ:

```text
eventId = evt-9001

attempt #1 -> listener failure, 150 ms
attempt #2 -> listener failure, 220 ms
attempt #3 -> listener success,  90 ms

Listener Timer count = 3 lần đo (trong mô hình mỗi attempt được đo)
Số event nghiệp vụ hoàn tất duy nhất = 1
```

Ngay cả ví dụ đếm ba lần cũng phụ thuộc cách retry được instrument; đây là tình huống minh họa để nhấn mạnh rằng **Timer không định nghĩa duy nhất một event nghiệp vụ**.

## 11. Cách kiểm thử instrumentation

Để biết metric có đúng ý nghĩa, cần kiểm tra cả kết quả thành công và thất bại. Không chỉ tìm thấy một meter và kết luận toàn bộ luồng đã được quan sát đúng.

### 11.1. Kiểm tra bằng `MeterRegistry` trong test

Mẫu kiểm tra mang tính định hướng (khi có Spring test context, broker và instrumentation tương ứng):

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import static org.assertj.core.api.Assertions.assertThat;

class RabbitMetricsIntegrationTest {
    @Autowired
    MeterRegistry registry;

    @Test
    void templateAndListenerMetersExistAfterTraffic() {
        // Bài test tích hợp phải gửi message và chờ listener xử lý trước.
        List<Timer> templateTimers =
                registry.find("spring.rabbitmq.template").timers();
        List<Timer> listenerTimers =
                registry.find("spring.rabbitmq.listener").timers();

        assertThat(templateTimers).isNotEmpty();
        assertThat(listenerTimers).isNotEmpty();
        assertThat(listenerTimers.stream()
                .mapToLong(Timer::count).sum()).isGreaterThan(0L);
    }
}
```

**Đây là phần khẳng định metric, không phải test chạy độc lập:** cần dependency test, test context, broker thực hoặc Testcontainers, một lần publish và cơ chế đợi listener hoàn tất; nếu không có traffic, meter có thể chưa được tạo. Với Observation mode, tên/registry cụ thể phải xác nhận rồi điều chỉnh assertion.

### 11.2. Ma trận thử nghiệm nên thực hiện

| Tình huống | Cần kiểm chứng |
|---|---|
| Gửi String message thành công | Template Timer có count tăng và duration hợp lệ |
| Listener xử lý xong | Listener Timer xuất hiện, nhận diện đúng listener |
| Listener ném exception | Có metric kết quả lỗi và hành vi ack/retry như cấu hình |
| Message được requeue/redeliver | Timer phản ánh số lần xử lý theo phạm vi đo, không đồng nhất với event duy nhất |
| Broker tạm thời mất kết nối | Template send failure/timeout được phản ánh đúng; consumer recovery có metric riêng nếu cần |
| Bật Observation | Không double-count timer cũ và metric Observation |
| Dùng `CompletableFuture` hoặc `Mono` trong listener | Xác nhận thời điểm kết thúc phép đo so với completion thật |
| Đặt histogram SLO buckets | Endpoint Prometheus xuất `_bucket` cho meter dự kiến |
| Có nhiều queue/listener | Tag phân biệt đúng, cardinality trong ngưỡng |
| Retry và DLQ | Dashboard cho thấy lỗi cùng dữ liệu broker; không chỉ nhìn p95 |

Nên thử trên môi trường có RabbitMQ thực để kiểm chứng instrumentation trong listener container. Gọi trực tiếp method Java ngoài container có thể tạo metric tự định nghĩa nhưng **không bảo đảm meter tích hợp `spring.rabbitmq.listener` được kích hoạt**.

## 12. Runbook khi không thấy Timer hoặc biểu đồ sai

1. **Kiểm tra dependency:** có Actuator, Micrometer registry phù hợp và Spring AMQP đúng phiên bản không?
2. **Tạo traffic thật:** đã gọi `RabbitTemplate` và có listener nhận ít nhất một message chưa?
3. **Kiểm tra tên meter:** xem `/actuator/metrics` hoặc `MeterRegistry.getMeters()`; không đoán rằng mọi phiên bản xuất cùng tên.
4. **Kiểm tra chế độ:** Timer truyền thống bị tắt hay Observation đang bật? Có vô tình instrument hai lần cùng một đoạn code?
5. **Kiểm tra exposure:** `/actuator/metrics` và `/actuator/prometheus` có được cho phép truy cập trong môi trường kiểm thử không?
6. **Kiểm tra tags/filters:** `MeterFilter` hoặc policy cardinality có từ chối meter không? Dashboard có dùng sai tên label sau khi chuẩn hóa không?
7. **Kiểm tra histogram:** có `_count`/`_sum` nhưng không có `_bucket` vì chưa bật phân phối phù hợp?
8. **Kiểm tra broker và app:** queue backlog tăng có phải do listener không còn consumer, hay do logic xử lý chậm?
9. **Kiểm tra kết quả:** Timer đếm attempts hay events? Có lọc sai `success`/`failure` hoặc gộp nhiều listener?
10. **Kiểm tra bảo mật:** endpoint metric chỉ dành cho hệ thống quan sát được ủy quyền, không mở rộng ra Internet để debug.

## 13. Một dashboard tối thiểu cho Spring AMQP

Một dashboard thực tế nên trả lời: producer có gửi được không, consumer có theo kịp không, lỗi có tăng không và thời gian xử lý nằm ở đâu?

| Biểu đồ | Nguồn | Mục đích |
|---|---|---|
| Publish call rate | `spring.rabbitmq.template` count/rate | Phát hiện bất thường ở phía producer |
| Publish call p95 | Template Timer histogram | Theo dõi hiệu năng lời gọi gửi |
| Confirm ack/nack và thời gian chờ | Metric confirm riêng | Xác định publish đã được broker phản hồi ra sao |
| Listener success/failure rate | Listener Timer tags hoặc counter nghiệp vụ | Đánh giá sức khỏe xử lý |
| Listener p95/p99 | Listener Timer histogram | Phát hiện xử lý chậm |
| Queue ready/unacked + consumer count | RabbitMQ metrics | Phân biệt backlog, thiếu consumer và in-flight |
| Retry/redelivery/DLQ | App + broker metrics | Đánh giá lỗi và nguy cơ xử lý lặp |
| DB/HTTP downstream p95 | Custom Timer hoặc HTTP client metrics | Tìm nguyên nhân gốc trong nghiệp vụ |

Cảnh báo nên gắn với **mức ảnh hưởng** chứ không chỉ một ngưỡng Timer. Ví dụ, p95 listener tăng nhưng throughput vẫn đạt yêu cầu có thể ít nghiêm trọng hơn backlog tăng liên tục, không có consumer và hàng nghìn message quá hạn xử lý.

### Câu hỏi tự kiểm tra

1. Vì sao Timer của `RabbitTemplate` không mặc nhiên đo đến khi nhận publisher confirm?
2. Timer listener có đo thời gian một message chờ trong queue không? Muốn biết thời gian đó cần dữ liệu gì?
3. Sự khác biệt giữa Timer `count` và số business event được xử lý duy nhất là gì khi có retry?
4. Vì sao không nên dùng `eventId` hoặc `orderId` làm tag Micrometer?
5. Khi chỉ có `_count` và `_sum`, có tính p95 đáng tin cậy được không?
6. Khi bật Micrometer Observation, vì sao cần kiểm tra trạng thái legacy Timer để tránh đếm trùng?
7. Vì sao phải theo dõi cả queue depth, publisher confirm và DLQ bên cạnh Timer template/listener?

**Ghi nhớ:** Micrometer Timer giúp đo **thời gian và số lần thực thi thao tác**. Với Spring AMQP, hãy phân biệt Timer của `RabbitTemplate` với publisher confirm latency, Timer của `@RabbitListener` với queue waiting và end-to-end latency. Kết hợp metric ứng dụng, metric broker, tracing và idempotency; đặt tags có cardinality thấp, cấu hình histogram có chọn lọc và kiểm chứng hành vi bằng traffic thực tế trước khi dùng chỉ số để ra quyết định vận hành.
