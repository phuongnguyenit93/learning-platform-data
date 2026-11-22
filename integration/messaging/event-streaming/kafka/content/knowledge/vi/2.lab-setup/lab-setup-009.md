# Tổ chức dự án Java, cấu hình kết nối và dữ liệu thực hành

Một bài thực hành Kafka cần có môi trường broker chạy ổn định, một ứng dụng Java kết nối được đến broker, cấu hình producer/consumer nhất quán và dữ liệu mẫu đủ rõ để quan sát luồng sự kiện. Bài này dựng môi trường Kafka cục bộ bằng Docker Compose ở chế độ KRaft một node, tổ chức một dự án Spring Boot, cấu hình kết nối và tạo topic `orders.created` để gửi, nhận sự kiện đơn hàng.

Môi trường một node phù hợp cho học tập và phát triển trên máy cá nhân. Nó giúp người học thử producer, consumer, partition, consumer group và offset mà không cần dựng nhiều máy chủ. Cấu hình này không đại diện cho cụm production có replication và khả năng chịu lỗi.

Sau khi hoàn thành, người học có thể:

- Khởi động và kiểm tra broker Kafka cục bộ.
- Phân biệt địa chỉ kết nối từ ứng dụng chạy trên máy host và ứng dụng chạy trong Docker network.
- Tổ chức mã nguồn Java/Spring Kafka theo vai trò cấu hình, event, producer, consumer và API.
- Khai báo topic với số partition và replication factor phù hợp môi trường lab.
- Gửi dữ liệu JSON mẫu và xác nhận consumer nhận đúng key, payload, partition và offset.
- Dọn môi trường thực hành mà hiểu rõ dữ liệu nào sẽ bị xóa.

## 1. Chuẩn bị công cụ

Chuẩn bị các thành phần sau:

| Công cụ | Mục đích | Kiểm tra |
|---|---|---|
| JDK 17 trở lên | Biên dịch và chạy ứng dụng Spring Boot 3 | `java -version` |
| Maven hoặc Maven Wrapper | Quản lý dependency và chạy ứng dụng | `mvn -version` hoặc kiểm tra `mvnw.cmd` |
| Docker Desktop có Docker Compose | Chạy broker Kafka trong container | `docker version` và `docker compose version` |
| IDE hỗ trợ Java | Viết, chạy và debug ứng dụng | Mở được project Maven |
| Terminal | Chạy lệnh Docker và Kafka CLI | PowerShell, Windows Terminal hoặc shell tương đương |

Đảm bảo cổng `9092` trên máy host chưa bị một dịch vụ khác chiếm. Cổng `9093` được dùng cho controller KRaft bên trong container; ứng dụng Java không kết nối trực tiếp vào cổng controller này. Nếu máy đã có Kafka chạy trên `9092`, hãy dừng dịch vụ đó hoặc điều chỉnh đồng bộ cổng host trong Compose và địa chỉ bootstrap của ứng dụng.

Trong bài, các lệnh Docker được viết theo cú pháp dùng được trong PowerShell hiện đại. Nếu dùng Linux hoặc macOS, lệnh Maven Wrapper tương ứng là `./mvnw` thay cho `mvnw.cmd`.

## 2. Khởi động Kafka cục bộ bằng Docker Compose

Tạo thư mục làm việc, ví dụ `kafka-lab`, rồi tạo file `compose.yaml` ở thư mục gốc. Cấu hình sử dụng Kafka ở chế độ KRaft kết hợp broker và controller trên một node. Hai listener phục vụ hai kiểu client: ứng dụng chạy trên máy host dùng `localhost:9092`; ứng dụng chạy trong cùng Docker network dùng `kafka:29092`.

```yaml
services:
  kafka:
    image: apache/kafka:3.9.1
    container_name: kafka-lab
    ports:
      - "9092:9092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093,DOCKER://:29092
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092,DOCKER://kafka:29092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,DOCKER:PLAINTEXT
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@localhost:9093
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_LOG_DIRS: /tmp/kraft-combined-logs
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
      KAFKA_NUM_PARTITIONS: 3
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "false"
    volumes:
      - kafka_data:/tmp/kraft-combined-logs

volumes:
  kafka_data:
```

Các thiết lập đáng chú ý:

- `KAFKA_PROCESS_ROLES=broker,controller` chạy cả hai vai trò trên cùng một node theo KRaft.
- `KAFKA_LISTENERS` khai báo các địa chỉ mà tiến trình Kafka lắng nghe. `PLAINTEXT` dành cho ứng dụng chạy trên host, `DOCKER` dành cho container khác trong cùng network, còn `CONTROLLER` phục vụ điều phối metadata của KRaft.
- `KAFKA_ADVERTISED_LISTENERS` là địa chỉ broker công bố cho client sau khi kết nối bootstrap. Địa chỉ này phải truy cập được từ chính môi trường chạy client.
- `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR` và các thiết lập transaction được đặt bằng `1` vì lab chỉ có một broker.
- Volume `kafka_data` giữ dữ liệu Kafka qua lần dừng và khởi động lại container.
- Tắt tự tạo topic để bài thực hành tạo topic có chủ đích và kiểm tra cấu hình trước khi gửi dữ liệu.

Khởi động dịch vụ tại thư mục chứa `compose.yaml`:

```powershell
docker compose up -d
docker compose ps
```

Xem log khởi động khi cần:

```powershell
docker compose logs -f kafka
```

Khi broker đã sẵn sàng, lệnh `docker compose ps` cho thấy container đang chạy. Có thể kiểm tra broker trả lời metadata request bằng Kafka CLI:

```powershell
docker exec kafka-lab /opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092
```

Nếu lệnh chưa kết nối được ngay sau khi `up -d`, xem log và đợi broker hoàn tất khởi động rồi thử lại. Trạng thái container `running` chỉ cho biết tiến trình còn chạy, chưa luôn đồng nghĩa broker đã sẵn sàng nhận request.

## 3. Tổ chức dự án Java

Tách phần kết nối và cấu hình Kafka khỏi mã xử lý nghiệp vụ giúp ứng dụng dễ đọc, kiểm thử và mở rộng. Một cấu trúc Maven đơn giản cho bài lab:

```text
kafka-lab/
├── compose.yaml
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/kafkalab/
    │   │   ├── KafkaLabApplication.java
    │   │   ├── config/
    │   │   │   └── KafkaTopicConfig.java
    │   │   ├── event/
    │   │   │   └── OrderCreatedEvent.java
    │   │   ├── producer/
    │   │   │   └── OrderEventPublisher.java
    │   │   ├── consumer/
    │   │   │   └── OrderCreatedListener.java
    │   │   └── api/
    │   │       ├── CreateOrderRequest.java
    │   │       └── OrderEventController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/kafkalab/
```

Vai trò của từng phần:

| Thành phần | Trách nhiệm |
|---|---|
| `config` | Khai báo topic và các cấu hình dùng chung |
| `event` | Định nghĩa cấu trúc sự kiện trao đổi qua Kafka |
| `producer` | Đóng gói thao tác gửi sự kiện |
| `consumer` | Nhận và xử lý sự kiện từ topic |
| `api` | Cung cấp điểm gọi thử từ HTTP để phát sự kiện |
| `application.yml` | Cấu hình kết nối, serializer và consumer group |
| `compose.yaml` | Khởi động broker dùng trong môi trường lab |

Lớp khởi động đặt ở package gốc để Spring component scan nhận được các package con:

`KafkaLabApplication.java`:

```java
package com.example.kafkalab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KafkaLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(KafkaLabApplication.class, args);
    }
}
```

Tạo project Spring Boot với phiên bản Spring Boot 3.x và JDK 17 trở lên. Dùng dependency management do Spring Boot cung cấp để các thư viện Spring Kafka và Kafka client có phiên bản tương thích. Các dependency cần có trong `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Nếu project đã có parent hoặc BOM Spring Boot, không cần tự đặt version riêng cho từng dependency được quản lý. Tránh nâng riêng `kafka-clients` hoặc `spring-kafka` khi chưa kiểm tra ma trận tương thích của phiên bản Spring Boot đang dùng.

## 4. Cấu hình địa chỉ kết nối và serializer

Tạo `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  application:
    name: kafka-lab
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: orders-lab
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.kafkalab.event
        spring.json.value.default.type: com.example.kafkalab.event.OrderCreatedEvent
        spring.json.use.type.headers: false
```

`bootstrap-servers` là địa chỉ dùng để khởi đầu kết nối và lấy metadata của cluster. Giá trị mặc định `localhost:9092` phù hợp khi Spring Boot chạy trực tiếp trên máy host. Có thể thay bằng biến môi trường `KAFKA_BOOTSTRAP_SERVERS` khi chạy ở môi trường khác.

Nếu Spring Boot cũng chạy trong Docker Compose cùng network với broker, đặt biến môi trường thành `kafka:29092`. Không đặt `localhost:9092` cho ứng dụng nằm trong container: `localhost` khi đó trỏ về chính container ứng dụng, không phải container Kafka. Tương tự, broker không nên quảng bá địa chỉ chỉ có thể truy cập từ một môi trường khác với client.

Producer dùng `StringSerializer` cho key để mã đơn hàng được dùng làm partition key, và `JsonSerializer` cho event. Consumer dùng `JsonDeserializer` với kiểu mặc định là `OrderCreatedEvent`; `trusted.packages` giới hạn package được phép deserialize. Cấu hình `use.type.headers: false` giúp consumer dựa vào kiểu mặc định đã khai báo thay vì yêu cầu type header trong record. Trong hệ thống nhiều loại event, cần thiết kế type mapping hoặc schema rõ ràng thay vì ép mọi payload về một lớp.

`auto-offset-reset: earliest` chỉ có hiệu lực khi group chưa có committed offset hợp lệ hoặc offset đã lưu không còn trong log. Nó không tự reset một group đã chạy về đầu topic.

## 5. Khai báo topic và mô hình dữ liệu

Tạo package `event` và định nghĩa một sự kiện đơn hàng. Một event nên có định danh riêng để consumer có thể phát hiện xử lý trùng, mã thực thể nghiệp vụ làm key, dữ liệu cần thiết cho bên nhận và thời điểm phát sinh.

`OrderCreatedEvent.java`:

```java
package com.example.kafkalab.event;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal amount,
        Instant occurredAt
) {
}
```

Tạo topic `orders.created` có ba partition và replication factor bằng một cho môi trường một broker. Đặt retention bảy ngày để có đủ thời gian thực hành đọc lại dữ liệu:

`KafkaTopicConfig.java`:

```java
package com.example.kafkalab.config;

import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.common.config.TopicConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaTopicConfig {

    @Bean
    public NewTopic ordersCreatedTopic() {
        return TopicBuilder.name("orders.created")
                .partitions(3)
                .replicas(1)
                .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
                .build();
    }
}
```

Spring Boot tự cấu hình Kafka admin từ `spring.kafka.bootstrap-servers` và dùng bean `NewTopic` để tạo topic khi ứng dụng khởi động. Nếu topic đã tồn tại, Kafka admin không tự ý thay đổi mọi cấu hình hiện hữu chỉ vì bean khai báo khác; hãy kiểm tra topic bằng CLI và chủ động alter khi cần. Với môi trường nhiều broker, replication factor phải nhỏ hơn hoặc bằng số broker khả dụng và được thiết kế theo yêu cầu chịu lỗi. Không dùng replication factor `1` của bài lab làm cấu hình production.

## 6. Viết producer và consumer

Producer gửi event vào topic `orders.created`, dùng `orderId` làm key. Các sự kiện của cùng một đơn hàng vì thế được định tuyến theo cùng key trong điều kiện partitioner và số partition không thay đổi.

`OrderEventPublisher.java`:

```java
package com.example.kafkalab.producer;

import com.example.kafkalab.event.OrderCreatedEvent;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

import java.util.concurrent.CompletableFuture;

@Service
public class OrderEventPublisher {
    private static final String TOPIC = "orders.created";

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {
        return kafkaTemplate.send(TOPIC, event.orderId(), event);
    }
}
```

Consumer lắng nghe cùng topic. Log key, partition và offset để quan sát cách Kafka phân phối record:

`OrderCreatedListener.java`:

```java
package com.example.kafkalab.consumer;

import com.example.kafkalab.event.OrderCreatedEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {
    private static final Logger log = LoggerFactory.getLogger(OrderCreatedListener.class);

    @KafkaListener(topics = "orders.created")
    public void onOrderCreated(
            OrderCreatedEvent event,
            @Header(KafkaHeaders.RECEIVED_KEY) String key,
            @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
            @Header(KafkaHeaders.OFFSET) long offset) {

        log.info("Received eventId={}, orderId={}, key={}, partition={}, offset={}",
                event.eventId(), event.orderId(), key, partition, offset);
    }
}
```

Group ID `orders-lab` được lấy từ cấu hình consumer. Nếu chạy hai instance của ứng dụng với cùng group ID, Kafka chia các partition giữa hai instance. Nếu muốn một ứng dụng phân tích đọc độc lập toàn bộ sự kiện, ứng dụng đó cần một group ID riêng.

## 7. Tạo endpoint gửi dữ liệu mẫu

Để phát event mà không phải viết một chương trình producer riêng, tạo request nhận thông tin đơn hàng qua HTTP.

`CreateOrderRequest.java`:

```java
package com.example.kafkalab.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import java.math.BigDecimal;

public record CreateOrderRequest(
        @NotBlank String orderId,
        @NotBlank String customerId,
        @NotNull @Positive BigDecimal amount
) {
}
```

`OrderEventController.java`:

```java
package com.example.kafkalab.api;

import com.example.kafkalab.event.OrderCreatedEvent;
import com.example.kafkalab.producer.OrderEventPublisher;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

@RestController
@RequestMapping("/lab/orders")
public class OrderEventController {
    private final OrderEventPublisher publisher;

    public OrderEventController(OrderEventPublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping
    public CompletableFuture<ResponseEntity<Void>> create(
            @Valid @RequestBody CreateOrderRequest request) {

        var event = new OrderCreatedEvent(
                UUID.randomUUID().toString(),
                request.orderId(),
                request.customerId(),
                request.amount(),
                Instant.now()
        );

        return publisher.publish(event)
                .thenApply(result -> ResponseEntity.accepted().<Void>build());
    }
}
```

Endpoint trả HTTP `202 Accepted` sau khi future gửi Kafka hoàn tất thành công. Nếu gửi thất bại, future hoàn tất exceptional và Spring MVC trả lỗi thay vì báo đã nhận thành công. Ở ứng dụng nghiệp vụ, cần chuẩn hóa cách ánh xạ lỗi, timeout và correlation ID theo API contract.

## 8. Tạo topic và kiểm tra bằng Kafka CLI

Có thể để Spring Kafka tạo topic từ bean `NewTopic` khi ứng dụng khởi động. Để luyện thao tác quản trị độc lập, hãy tạo topic bằng CLI trước khi chạy ứng dụng. Nếu topic đã được Spring tạo, dùng lệnh `--describe` để kiểm tra thay vì tạo lại.

```powershell
docker exec kafka-lab /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic orders.created --partitions 3 --replication-factor 1
```

Xem số partition, leader và replica:

```powershell
docker exec kafka-lab /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders.created
```

Kết quả cần thể hiện topic `orders.created` có ba partition. Vì cluster chỉ có một broker nên replica của mỗi partition đều nằm trên broker đó. Điều này giúp kiểm tra luồng dữ liệu nhưng không chứng minh khả năng chịu lỗi khi broker dừng.

Để quan sát record bằng console consumer, mở một terminal riêng:

```powershell
docker exec -it kafka-lab /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic orders.created --from-beginning --property print.key=true --property print.partition=true --property print.offset=true
```

Console consumer hiển thị value cùng key, partition và offset. Vì nó đọc raw JSON, có thể dùng để kiểm tra payload ngay cả khi ứng dụng Spring Boot không chạy.

## 9. Gửi dữ liệu thực hành

Khởi động Spring Boot từ thư mục dự án:

```powershell
.\mvnw.cmd spring-boot:run
```

Khi ứng dụng đã khởi động, gửi request tạo đơn hàng bằng PowerShell:

```powershell
$body = @{
    orderId = "ORD-1001"
    customerId = "CUS-01"
    amount = 125000.00
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8080/lab/orders" `
    -ContentType "application/json" `
    -Body $body
```

Consumer trong ứng dụng sẽ ghi log tương tự:

```text
Received eventId=..., orderId=ORD-1001, key=ORD-1001, partition=1, offset=0
```

Partition và offset cụ thể phụ thuộc trạng thái topic tại thời điểm gửi. Khi gửi thêm các event có cùng `orderId`, chúng sẽ được định tuyến đến cùng partition trong cấu hình hiện tại. Thử gửi các đơn hàng khác nhau để quan sát chúng có thể nằm ở partition khác.

Có thể gửi trực tiếp JSON bằng console producer để kiểm tra broker mà không cần chạy REST API. Mở terminal:

```powershell
docker exec -it kafka-lab /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic orders.created --property parse.key=true --property key.separator=:
```

Nhập mỗi record trên một dòng theo định dạng `key:value`:

```text
ORD-2001:{"eventId":"evt-2001","orderId":"ORD-2001","customerId":"CUS-02","amount":89000.00,"occurredAt":"2026-11-20T09:00:00Z"}
ORD-2002:{"eventId":"evt-2002","orderId":"ORD-2002","customerId":"CUS-03","amount":215000.00,"occurredAt":"2026-11-20T09:01:00Z"}
```

Console producer gửi value dưới dạng chuỗi JSON và không tự thêm type header của Spring Kafka. Cấu hình consumer trong bài đặt `spring.json.use.type.headers: false` và kiểu mặc định là `OrderCreatedEvent`, nên các record này vẫn có thể được deserialize thành event. Dừng console producer bằng `Ctrl+C` sau khi nhập xong.

## 10. Kiểm tra consumer group và dữ liệu

Xem tiến độ của group `orders-lab`:

```powershell
docker exec kafka-lab /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group orders-lab
```

Quan sát các cột `CURRENT-OFFSET`, `LOG-END-OFFSET` và `LAG`. Consumer đã xử lý và commit đến đâu sẽ thể hiện trong offset của group; log end offset cho biết vị trí cuối log của partition. Lag lớn kéo dài có thể cho thấy consumer chưa theo kịp tốc độ ghi.

Nếu group chưa xuất hiện, hãy xác nhận ứng dụng consumer đã kết nối, listener đã subscribe topic và không có lỗi deserialize. Consumer group thường được broker ghi nhận khi consumer tham gia và bắt đầu sử dụng group.

Các câu hỏi tự kiểm tra:

1. Vì sao Spring Boot chạy trên host dùng `localhost:9092`, còn ứng dụng chạy trong Docker network dùng `kafka:29092`?
2. Nếu tạo topic với một partition, điều gì giới hạn khả năng xử lý song song của một consumer group?
3. Vì sao các event có cùng `orderId` được dùng làm key?
4. Nếu đổi `auto-offset-reset` từ `latest` sang `earliest` sau khi group đã có committed offset, consumer có tự đọc lại từ đầu không?
5. Vì sao replication factor bằng một chỉ phù hợp với broker lab một node?

## 11. Sự cố thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
|---|---|---|
| `Connection to node ... could not be established` | Broker chưa sẵn sàng, sai cổng hoặc advertised listener không truy cập được | Xem `docker compose logs kafka`; xác nhận client dùng đúng `localhost:9092` hoặc `kafka:29092` |
| Container chạy nhưng app không kết nối | App trong container đang dùng `localhost` | Đổi bootstrap server thành `kafka:29092` |
| `Topic ... does not exist` | Topic chưa được tạo và auto-create đang tắt | Chạy `kafka-topics.sh --create` hoặc khởi động app có bean `NewTopic` |
| Consumer báo lỗi deserialize | JSON sai cấu trúc, sai kiểu mặc định hoặc package chưa được tin cậy | Kiểm tra payload, `spring.json.value.default.type` và `spring.json.trusted.packages` |
| HTTP trả lỗi khi gửi event | Producer chưa kết nối broker hoặc Kafka từ chối record | Xem nguyên nhân trong log ứng dụng và log broker |
| Consumer không thấy record cũ | Group có committed offset ở cuối log hoặc record đã hết retention | Kiểm tra group offset; dùng group mới hoặc reset offset khi có chủ đích |
| Không tạo được topic với replication factor 3 | Cluster lab chỉ có một broker | Dùng replication factor 1 trong lab; cần nhiều broker để thực hành replication |
| Cổng 9092 đã được sử dụng | Một dịch vụ khác chiếm cổng host | Dừng dịch vụ đó hoặc đổi port mapping và advertised listener tương ứng |

Khi kiểm tra kết nối, hãy phân biệt lỗi bootstrap và lỗi advertised listener. Client có thể kết nối được bootstrap address ban đầu nhưng sau đó thất bại nếu broker trả về địa chỉ quảng bá không thể truy cập từ client. Đây là lý do cấu hình riêng listener cho host và Docker network trong file Compose.

## 12. Dừng và đặt lại môi trường

Dừng container nhưng giữ volume dữ liệu:

```powershell
docker compose down
```

Khởi động lại bằng `docker compose up -d`; topic, record và offset đã lưu trong volume vẫn còn. Điều này hữu ích khi tạm dừng bài học.

Nếu muốn xóa toàn bộ dữ liệu lab và tạo cluster sạch, chạy:

```powershell
docker compose down -v
```

Tùy chọn `-v` xóa named volume `kafka_data`, do đó xóa cả topic, record và metadata lưu trong volume của lab. Chỉ dùng khi chủ động muốn làm lại từ đầu. Không dùng lệnh này với volume đang chứa dữ liệu cần giữ.

## 13. Kết quả cần đạt

Môi trường được xem là sẵn sàng khi:

- Docker Compose khởi động được broker KRaft và Kafka CLI truy vấn được broker.
- Topic `orders.created` tồn tại với ba partition và replication factor một.
- Ứng dụng Spring Boot kết nối qua `localhost:9092` khi chạy trên host.
- REST API gửi được event có key là `orderId` và consumer nhận được event.
- Console consumer quan sát được payload, key, partition và offset.
- Lệnh `kafka-consumer-groups.sh --describe` hiển thị group `orders-lab` cùng tiến độ đọc.

Ở các bài tiếp theo, có thể mở rộng lab này thành nhiều broker để thực hành replication và phục hồi, thêm nhiều consumer instance để quan sát rebalance, rồi cấu hình retry, dead-letter topic và transaction. Giữ file Compose, cấu trúc project và dữ liệu mẫu nhất quán sẽ giúp các bài thực hành sau tập trung vào hành vi Kafka cần học.
