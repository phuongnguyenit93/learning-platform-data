# Quản lý địa chỉ đích và giới hạn tài nguyên bằng cấu hình ngoài

> Mục tiêu: đưa tên queue, topic, destination và các giới hạn vận hành ra khỏi mã nguồn; cấu hình riêng theo môi trường; kiểm soát số consumer, lượng message đang xử lý, kích thước payload và các giới hạn khác để ứng dụng Spring Messaging vận hành ổn định.

## 1. Vì sao cần cấu hình ngoài?

Ứng dụng messaging thường chạy ở nhiều môi trường như local, test, staging và production. Mỗi môi trường có thể dùng broker, virtual host, queue, topic, exchange hoặc routing key khác nhau. Năng lực tài nguyên cũng khác nhau: production có thể cho phép nhiều consumer hơn, prefetch lớn hơn hoặc giới hạn payload khác môi trường phát triển.

Nếu ghi cứng các giá trị này trong mã nguồn, mỗi lần đổi tên destination hoặc điều chỉnh tải lại phải sửa mã và phát hành ứng dụng. Cấu hình ngoài giúp:

- Thay đổi địa chỉ đích mà không phải sửa logic nghiệp vụ.
- Đặt giới hạn phù hợp với CPU, bộ nhớ, database pool và năng lực broker.
- Dùng cùng một bản build cho nhiều môi trường.
- Kiểm tra cấu hình ngay khi khởi động và phát hiện giá trị sai sớm.
- Quản lý thay đổi vận hành qua cấu hình, quy trình triển khai và quyền truy cập riêng.

Trong Spring, cần phân biệt **tên destination bên ngoài** với **MessageChannel trong ứng dụng**. `MessageChannel` là abstraction gửi message; tùy cách cấu hình, nó có thể chỉ nối các bean trong cùng tiến trình. Queue, topic, exchange hoặc destination là tài nguyên của hệ thống messaging cụ thể. Một channel không tự động tương đương với một queue của broker.

## 2. Địa chỉ đích phụ thuộc vào nền tảng messaging

Tên gọi và cách định tuyến khác nhau theo công nghệ:

| Nền tảng | Địa chỉ hoặc tài nguyên thường cấu hình | Ý nghĩa |
|---|---|---|
| JMS | Queue hoặc Topic name | Destination mà producer gửi đến và consumer đăng ký nhận |
| RabbitMQ | Exchange, routing key, queue, binding | Exchange định tuyến message theo loại exchange và binding; queue lưu message cho consumer |
| Kafka | Topic và consumer group | Topic lưu các record; consumer group phối hợp chia partition cho consumer |
| Spring Messaging nội bộ | Bean name hoặc MessageChannel | Kênh trong ứng dụng để kết nối sender và handler |

Không nên gom mọi loại địa chỉ thành một khái niệm “queue”. Ví dụ, RabbitMQ producer thường publish đến exchange với routing key; Kafka producer ghi vào topic; JMS producer gửi đến queue hoặc topic. Cấu hình cần phản ánh đúng mô hình của broker đang dùng.

Tên destination có thể được khai báo trong file cấu hình, biến môi trường hoặc hệ thống quản lý cấu hình. Hạ tầng queue/topic thường cần được tạo trước bằng công cụ quản trị, IaC hoặc chính sách provisioning của broker. Đưa tên vào `application.yaml` không có nghĩa tài nguyên đó tự tồn tại trên broker.

## 3. Spring Boot externalized configuration

Spring Boot hỗ trợ lấy cấu hình từ nhiều nguồn như file `application.properties`, `application.yaml`, file theo profile, biến môi trường, Java system properties và tham số dòng lệnh. Các nguồn bên ngoài có thể ghi đè giá trị mặc định trong file đóng gói cùng ứng dụng theo quy tắc ưu tiên cấu hình của Spring Boot.

Ví dụ khai báo destination và một số giới hạn trong `application.yaml`:

```yaml
app:
  messaging:
    orders:
      destination: ${ORDERS_DESTINATION:orders.incoming}
      concurrency: ${ORDERS_CONCURRENCY:2-8}
      max-payload-bytes: ${ORDERS_MAX_PAYLOAD_BYTES:262144}
```

Ý nghĩa:

- `destination` chọn tên queue hoặc destination cho luồng đơn hàng.
- `concurrency` là khoảng số consumer đồng thời trong ví dụ JMS, tối thiểu 2 và tối đa 8.
- `max-payload-bytes` là giới hạn payload do ứng dụng quy định, ở đây mặc định 256 KiB.
- Cú pháp `${ENV_VAR:default}` cho phép dùng biến môi trường khi được khai báo; nếu không có thì dùng giá trị mặc định.

Production có thể cung cấp `ORDERS_DESTINATION=orders.prod.incoming` và các giới hạn khác qua môi trường triển khai. Profile cũng có thể dùng để tách giá trị development, test và production. Không đưa mật khẩu broker, token hoặc private key trực tiếp vào file cấu hình được commit; hãy lấy bí mật từ secret manager hoặc cơ chế bảo mật của môi trường chạy.

## 4. Gom cấu hình có kiểu bằng @ConfigurationProperties

Với một nhóm thuộc tính liên quan, `@ConfigurationProperties` thường dễ quản lý hơn nhiều chuỗi `@Value` rải rác. Nó gom cấu hình thành một object có kiểu, hỗ trợ relaxed binding và có thể kết hợp Bean Validation để kiểm tra giá trị.

Ví dụ dùng Spring Boot 3 và Jakarta Validation:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.messaging.orders")
public record OrdersMessagingProperties(
        @NotBlank String destination,
        @NotBlank
        @Pattern(regexp = "[1-9][0-9]*(?:-[1-9][0-9]*)?")
        String concurrency,
        @Min(1024) @Max(10485760) int maxPayloadBytes
) {
}
```

Đăng ký quét cấu hình trong ứng dụng:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class MessagingApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }
}
```

Các annotation kiểm tra destination không rỗng, định dạng concurrency và giới hạn payload từ 1 KiB đến 10 MiB. Regex cho concurrency chấp nhận dạng `2` hoặc `2-8`; nếu cần bảo đảm số tối thiểu không lớn hơn số tối đa, hãy bổ sung custom validator. Nếu validation thất bại, ứng dụng nên dừng khởi động để tránh chạy với cấu hình sai.

Nếu không dùng Spring Boot, có thể cấu hình các bean bằng Java configuration, `Environment` hoặc `@Value`; `@ConfigurationProperties` là tiện ích thuộc Spring Boot.

## 5. Dùng destination đã cấu hình trong Spring JMS

Với JMS, producer có thể gửi đến destination lấy từ properties. Listener cũng có thể dùng placeholder trong annotation `@JmsListener`.

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
class OrdersJmsConfiguration {
    @Bean("ordersListenerFactory")
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory,
            OrdersMessagingProperties properties) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency(properties.concurrency());
        return factory;
    }
}
```

Producer:

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
class OrdersPublisher {
    private final JmsTemplate jmsTemplate;
    private final OrdersMessagingProperties properties;

    OrdersPublisher(JmsTemplate jmsTemplate,
                    OrdersMessagingProperties properties) {
        this.jmsTemplate = jmsTemplate;
        this.properties = properties;
    }

    void publish(String jsonPayload) {
        jmsTemplate.convertAndSend(properties.destination(), jsonPayload);
    }
}
```

Listener:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrdersListener {
    @JmsListener(
            destination = "${app.messaging.orders.destination}",
            containerFactory = "ordersListenerFactory"
    )
    public void handle(String jsonPayload) {
        // Deserialize, validate và xử lý message.
    }
}
```

Tên destination trong producer và listener được lấy từ cùng một thuộc tính, giúp tránh trường hợp gửi vào một queue nhưng listener lại nghe queue khác. `DefaultJmsListenerContainerFactory.setConcurrency` cấu hình số consumer cho listener container; dạng `2-8` cho phép container điều chỉnh số consumer trong khoảng đó theo cơ chế của container.

Đoạn mã giả định ứng dụng đã cấu hình `ConnectionFactory`, `JmsTemplate`, message converter nếu cần và broker có destination tương ứng. Nếu broker yêu cầu queue/topic được provision trước, cần tạo tài nguyên đó ngoài ứng dụng.

## 6. Cấu hình ngoài cho RabbitMQ và Kafka

Cùng một nguyên tắc externalized configuration được áp dụng cho broker khác, nhưng tên thuộc tính và giới hạn phụ thuộc integration.

### RabbitMQ

Có thể đưa tên queue ra cấu hình ứng dụng:

```yaml
app:
  messaging:
    orders:
      queue: ${ORDERS_QUEUE:orders.incoming}

spring:
  rabbitmq:
    listener:
      simple:
        concurrency: 2
        max-concurrency: 8
        prefetch: 20
```

Listener có thể tham chiếu tên queue:

```java
@RabbitListener(queues = "${app.messaging.orders.queue}")
public void handle(OrderMessage message) {
    // Xử lý message.
}
```

Các thuộc tính `spring.rabbitmq.listener.simple.*` áp dụng cho simple listener container do Spring Boot cấu hình tự động. `prefetch` giới hạn số message chưa được xác nhận mà broker có thể gửi trước cho mỗi consumer theo cơ chế RabbitMQ. Tên queue, exchange, routing key và binding vẫn cần được cấu hình đúng với topology thực tế.

### Kafka

Ví dụ cấu hình topic và giới hạn poll:

```yaml
app:
  messaging:
    orders:
      topic: ${ORDERS_TOPIC:orders.events}

spring:
  kafka:
    consumer:
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000
    listener:
      concurrency: 3
```

Listener có thể dùng topic lấy từ cấu hình:

```java
@KafkaListener(topics = "${app.messaging.orders.topic}")
public void handle(OrderEvent event) {
    // Xử lý record.
}
```

`max.poll.records` giới hạn số record trả về trong một lần poll. `max.poll.interval.ms` quy định khoảng thời gian tối đa giữa các lần poll trước khi consumer có thể bị xem là không còn tiến triển và bị loại khỏi group. Listener concurrency phải phù hợp với số partition và năng lực xử lý; tăng concurrency vượt số partition được gán không tự tạo thêm mức song song hữu ích.

Không sao chép nguyên cấu hình JMS sang RabbitMQ hoặc Kafka. Hãy chọn đúng thuộc tính của integration và broker đang sử dụng.

## 7. Các loại giới hạn tài nguyên cần quản lý

### 7.1. Số consumer và luồng xử lý đồng thời

Concurrency quyết định có bao nhiêu consumer hoặc listener worker xử lý cùng lúc. Tăng số consumer có thể tăng throughput khi broker, CPU và database còn khả năng đáp ứng; nhưng cũng làm tăng số kết nối, luồng, giao dịch và yêu cầu đồng thời lên hệ thống phụ thuộc.

Hãy đặt giới hạn dựa trên:

- Số lõi CPU và thời gian xử lý CPU-bound hoặc I/O-bound.
- Số kết nối database có thể dành cho listener sau khi trừ phần dùng bởi HTTP request và tác vụ khác.
- Số partition hoặc khả năng chia tải của queue/topic.
- Khả năng chịu tải của API hoặc dịch vụ mà consumer gọi tiếp.
- Dung lượng bộ nhớ cho các message đang được giữ trong tiến trình.

Nếu mỗi consumer cần một kết nối database, cấu hình 20 consumer trong khi connection pool chỉ có 8 kết nối có thể khiến phần lớn consumer chờ connection. Concurrency nên nằm trong ngân sách tài nguyên tổng thể của ứng dụng.

### 7.2. Prefetch, batch và số message đang chờ xử lý

Prefetch là số message broker có thể chuyển trước cho consumer khi các message trước chưa được xác nhận, tùy broker và giao thức. Prefetch lớn có thể giảm round trip nhưng cũng làm tăng lượng message đang nằm trong bộ nhớ consumer và có thể ảnh hưởng công bằng giữa các consumer.

Một ước lượng ban đầu cho lượng message đang được phân phối nhưng chưa xác nhận trong RabbitMQ là:

\[\text{in-flight messages} \approx \text{consumer count} \times \text{prefetch per consumer}\]

Đây là ước lượng cho một nhóm consumer và một phạm vi cấu hình cụ thể; số thực tế còn phụ thuộc số queue, subscription, message đã được nhận và cách broker phân phối. Không xem đây là giới hạn bộ nhớ toàn hệ thống.

Với Kafka, `max.poll.records` giới hạn số record trả về mỗi lần poll, còn kích thước batch và partition ảnh hưởng lượng dữ liệu mà consumer xử lý trong một chu kỳ. Hãy cân đối thời gian xử lý batch với `max.poll.interval.ms`.

### 7.3. Kích thước payload và bộ nhớ

Một message lớn tiêu thụ bộ nhớ ở producer, broker, network buffer, consumer và có thể cả bản sao sau khi deserialize. Nên xác định giới hạn kích thước ở nhiều lớp:

- **Producer/application:** kiểm tra kích thước dữ liệu trước khi gửi.
- **Broker:** cấu hình giới hạn message hoặc record theo khả năng của broker.
- **Consumer:** từ chối hoặc chuyển xử lý riêng các payload vượt giới hạn ứng dụng.
- **Schema:** tránh nhúng cả file lớn hoặc object đồ sộ; có thể lưu file ở object storage rồi gửi reference có quyền truy cập phù hợp.

Giới hạn ở ứng dụng và broker là hai kiểm soát khác nhau. Một thuộc tính `maxPayloadBytes` trong Java không tự cấu hình giới hạn của broker. Cần thống nhất đơn vị đo, encoding và cách xử lý message vượt ngưỡng.

### 7.4. Queue depth, thời gian lưu và tốc độ tiêu thụ

Queue có thể hấp thụ tải đột biến nhưng không có dung lượng vô hạn. Theo dõi queue depth, tuổi của message cũ nhất, tốc độ publish/consume, số lần redelivery và dead-letter. Nếu tốc độ gửi liên tục cao hơn tốc độ xử lý, độ dài queue và độ trễ sẽ tăng theo thời gian.

Cân nhắc giới hạn độ dài queue, message TTL, retention, chính sách overflow và cảnh báo. Khi queue đầy, cần xác định producer sẽ bị chặn, bị từ chối hay message được xử lý theo chính sách khác của broker.

### 7.5. Kết nối, executor và retry

Ngoài concurrency và prefetch, hãy quản lý connection pool, số session, thread pool, queue capacity của executor, timeout và retry backoff. Tránh executor có hàng đợi không giới hạn nếu message có thể đến nhanh hơn tốc độ xử lý; hàng đợi tăng vô hạn sẽ biến áp lực tải thành lỗi bộ nhớ.

Retry nên có giới hạn, backoff và dead-letter hoặc quy trình xử lý message lỗi. Retry liên tục không giới hạn có thể chiếm toàn bộ consumer và làm message mới bị đói. Đừng retry lỗi dữ liệu vĩnh viễn như schema không hợp lệ theo cùng cách với lỗi kết nối tạm thời.

## 8. Kiểm tra giới hạn payload trong ứng dụng

Ví dụ listener nhận chuỗi JSON và kiểm tra kích thước UTF-8 trước khi xử lý:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.stereotype.Component;

@Component
class OrdersPayloadValidator {
    private final OrdersMessagingProperties properties;

    OrdersPayloadValidator(OrdersMessagingProperties properties) {
        this.properties = properties;
    }

    void validate(String jsonPayload) {
        int payloadBytes = jsonPayload.getBytes(StandardCharsets.UTF_8).length;
        if (payloadBytes > properties.maxPayloadBytes()) {
            throw new IllegalArgumentException(
                    "Order message exceeds configured payload limit");
        }
    }
}
```

Đoạn mã minh họa kiểm tra chuỗi sau khi message đã được chuyển thành `String`. Nếu ứng dụng deserialize payload trước khi gọi validator, bộ nhớ đã được dùng để tạo object. Với yêu cầu bảo vệ nghiêm ngặt trước payload quá lớn, cần kiểm tra kích thước ở tầng nhận/serialization hoặc cấu hình broker trước khi deserialize. Exception từ listener có thể dẫn đến redelivery tùy transaction, acknowledgement và cấu hình broker; cần kết hợp retry có giới hạn và dead-letter.

## 9. Theo dõi và điều chỉnh cấu hình

Không nên chọn giới hạn chỉ dựa trên một con số mặc định. Hãy đo trong tải thử nghiệm và theo dõi production:

- Throughput: số message gửi và xử lý mỗi giây.
- Latency: thời gian từ publish đến consume và thời gian xử lý của consumer.
- Queue depth và age of oldest message.
- Số consumer hoạt động, số thread bận và thời gian chờ connection pool.
- CPU, heap, garbage collection và lượng message đang in-flight.
- Retry, redelivery, timeout và dead-letter rate.

Điều chỉnh từng nhóm cấu hình có kiểm soát. Nếu tăng concurrency, kiểm tra database pool và downstream service trước. Nếu tăng prefetch, kiểm tra heap và fairness. Nếu tăng max payload, kiểm tra giới hạn broker, network và bộ nhớ. Thay đổi một tham số có thể chuyển điểm nghẽn sang thành phần khác.

Các thuộc tính được bind khi ứng dụng khởi động thường không tự cập nhật mọi listener container khi file cấu hình thay đổi. Cách vận hành phổ biến là triển khai/restart instance với cấu hình mới; nếu dùng cơ chế refresh hoặc cập nhật container động, phải xác nhận integration hỗ trợ và kiểm thử vòng đời consumer.

## 10. Những lỗi cấu hình thường gặp

- **Ghi cứng destination trong nhiều class:** producer và consumer có thể lệch tên queue khi đổi môi trường. Gom giá trị vào một nhóm cấu hình dùng chung.
- **Nhầm tên channel với tên queue:** channel nội bộ của Spring không tự tạo tài nguyên trên broker.
- **Tăng concurrency không giới hạn:** có thể làm cạn connection pool, CPU hoặc downstream capacity.
- **Đặt prefetch quá cao:** consumer có thể giữ nhiều message chưa xử lý, tăng heap và làm phân phối tải kém cân bằng.
- **Chỉ giới hạn payload trong Java:** broker vẫn có thể nhận hoặc từ chối message ở một giới hạn khác; cần cấu hình đồng bộ các lớp.
- **Không validate cấu hình:** tên destination rỗng, concurrency sai định dạng hoặc giới hạn bằng 0 có thể gây lỗi khó hiểu lúc vận hành.
- **Đổi destination nhưng không provision queue/topic:** ứng dụng có thể khởi động nhưng gửi/nhận thất bại khi tài nguyên không tồn tại hoặc không có quyền.
- **Dùng cấu hình chứa secret trong repository:** credential có thể bị lộ qua lịch sử Git và log triển khai.
- **Giả định sửa file cấu hình sẽ cập nhật listener đang chạy:** nhiều thuộc tính chỉ được áp dụng khi container được tạo; cần quy trình restart hoặc refresh được hỗ trợ.

## 11. Quy trình triển khai an toàn

1. Xác định loại destination thực tế: JMS queue/topic, Rabbit exchange/queue/routing key, Kafka topic hay channel nội bộ.
2. Khai báo tên destination và giới hạn trong một nhóm cấu hình có namespace rõ ràng.
3. Dùng biến môi trường hoặc config source của môi trường để ghi đè giá trị mặc định.
4. Bind cấu hình vào object có kiểu và validate giá trị khi khởi động.
5. Provision queue, topic, exchange, binding và quyền truy cập bằng công cụ hạ tầng phù hợp.
6. Đặt concurrency, prefetch/batch, payload size, timeout và retry dựa trên ngân sách tài nguyên.
7. Đo throughput, latency, queue depth, heap và downstream saturation trong tải thử nghiệm.
8. Triển khai thay đổi có theo dõi; xác nhận listener đã dùng cấu hình mới và có phương án quay lại.

## 12. Kết luận

Địa chỉ đích và giới hạn tài nguyên là cấu hình vận hành, nên được tách khỏi logic nghiệp vụ và quản lý theo môi trường. Spring Boot cung cấp externalized configuration và `@ConfigurationProperties` để bind, validate và sử dụng các giá trị đó; các integration như JMS, RabbitMQ và Kafka có bộ thuộc tính riêng cho destination và listener.

Hãy cấu hình đúng loại địa chỉ theo broker, giới hạn concurrency, prefetch/batch, payload và queue dựa trên tài nguyên thực tế. Một cấu hình tốt phải được kiểm tra khi khởi động, quan sát qua metrics và thay đổi theo quy trình triển khai có kiểm soát.