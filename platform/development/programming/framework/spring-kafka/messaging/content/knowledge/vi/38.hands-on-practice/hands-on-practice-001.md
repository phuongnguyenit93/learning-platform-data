# Xây dựng producer phát hành OrderEvent

Trong bài thực hành này, chúng ta xây dựng một Spring Boot service nhận yêu cầu tạo sự kiện đơn hàng qua REST API rồi phát hành OrderEvent lên Kafka. Producer dùng KafkaTemplate, serialize payload thành JSON, đặt orderId làm record key và thêm event-id/correlation-id vào Kafka headers. API chỉ trả trạng thái đã phát hành sau khi broker xác nhận send thành công.

Bài lab tập trung vào producer trong module SPRING_KAFKA_MESSAGING: hiểu luồng từ request đến Kafka record, cấu hình serializer và độ tin cậy, quan sát metadata broker trả về, sau đó kiểm thử việc gửi/nhận thực tế bằng Embedded Kafka.

## 1. Kết quả cần đạt

Sau khi hoàn thành, bạn có thể:

- Tạo Spring Boot application có dependency Spring Kafka.
- Mô hình hóa OrderEvent và serialize event thành JSON.
- Cấu hình KafkaTemplate<String, OrderEvent> và ProducerFactory.
- Chọn topic, record key và Kafka headers phù hợp.
- Gửi record bất đồng bộ và xử lý kết quả từ CompletableFuture.
- Hiểu acks, producer idempotence, retry và giới hạn của chúng.
- Provision topic cho local/test và phân biệt với provisioning production.
- Kiểm thử record thực sự đến Kafka broker.

## 2. Bài toán và luồng dữ liệu

Service nhận yêu cầu xác nhận trạng thái đơn hàng. Mỗi yêu cầu tạo một event độc lập có eventId, orderId, trạng thái, tổng tiền, thời điểm phát sinh và correlation ID.

~~~mermaid
flowchart LR
    A[HTTP client] -->|POST /api/orders/{id}/events| B[OrderEventController]
    B --> C[OrderEventPublisher]
    C -->|KafkaTemplate.send| D[(orders.events)]
    D --> E[Broker ACK]
    E --> F[HTTP 202 + topic/partition/offset]
    D -.-> G[Consumer ở bài học sau]
~~~

Một Kafka record có các thành phần quan trọng:

| Thành phần | Giá trị trong bài lab | Vai trò |
|---|---|---|
| Topic | orders.events | Luồng lưu trữ event |
| Key | orderId | Chọn partition và giữ thứ tự tương đối cho cùng một order |
| Value | JSON OrderEvent | Payload nghiệp vụ |
| Headers | event-id, correlation-id | Truy vết và liên kết log giữa các service |

Producer gửi event và nhận broker acknowledgment. Điều đó xác nhận Kafka đã chấp nhận record theo cấu hình acks; nó chưa chứng minh consumer downstream đã xử lý event.

## 3. Chuẩn bị project

Ví dụ dùng Java 17, Spring Boot 3.4.x và Spring Kafka 3.x. Nếu project hiện tại đã có Spring Boot parent/BOM, hãy giữ version do project quản lý và chỉ bổ sung dependency cần thiết. Không trộn Spring Kafka 2.x với ví dụ API CompletableFuture trong bài này.

Cấu trúc package đề xuất:

~~~text
src/main/java/com/acme/orders/
  OrdersProducerApplication.java
  config/
    KafkaTopicProperties.java
    KafkaTopicConfiguration.java
  messaging/
    OrderEvent.java
    OrderStatus.java
    OrderEventPublisher.java
  web/
    OrderEventController.java
    PublishOrderRequest.java
    PublishOrderResponse.java
src/main/resources/
  application.yml
src/test/java/com/acme/orders/messaging/
  OrderEventPublisherIntegrationTest.java
~~~

Với Maven, các dependency tối thiểu:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.5</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
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
~~~

Version 3.4.5 ở parent là baseline minh họa để project chạy độc lập. Với repository đang dùng version khác, ưu tiên Spring Boot dependency management hiện có để Spring Kafka và Kafka client được đồng bộ.

## 4. Tạo application entry point

~~~java
package com.acme.orders;

import com.acme.orders.config.KafkaTopicProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(KafkaTopicProperties.class)
public class OrdersProducerApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersProducerApplication.class, args);
    }
}
~~~

EnableConfigurationProperties đăng ký cấu hình topic được bind từ application.yml. SpringBootApplication đặt ở package gốc để component scan tìm thấy controller, publisher và configuration bên dưới.

## 5. Khai báo cấu hình producer

Tạo src/main/resources/application.yml:

~~~yaml
server:
  port: 8080

app:
  kafka:
    topics:
      orders: orders.events

spring:
  application:
    name: orders-producer
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      retries: 2147483647
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        linger.ms: 5
        batch.size: 32768
        compression.type: snappy
~~~

Giải thích các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| bootstrap-servers | Địa chỉ broker để client khám phá cluster |
| StringSerializer | Serialize record key |
| JsonSerializer | Serialize object OrderEvent thành JSON |
| acks: all | Chờ acknowledgment theo ISR hiện tại của partition |
| enable.idempotence: true | Chống duplicate do producer retry trong một producer session |
| retries | Cho phép producer thử lại lỗi có thể retry |
| max.in.flight.requests.per.connection: 5 | Giữ giới hạn tương thích với idempotent producer |
| delivery.timeout.ms | Giới hạn tổng thời gian producer cố gắng gửi record |
| linger.ms và batch.size | Tạo cơ hội gom record thành batch |
| compression.type | Nén batch trước khi gửi broker |

acks=all không có nghĩa dữ liệu được nhân bản ra mọi broker trong cluster; broker chờ các replica đang nằm trong ISR. Trong production, phối hợp replication factor và min.insync.replicas phù hợp. Ví dụ topic RF=3 thường được bảo vệ tốt hơn với min.insync.replicas=2; local broker đơn có thể chỉ dùng RF=1/ISR=1 để thực hành.

Idempotent producer giúp xử lý retry của producer an toàn hơn trong phạm vi session và producer ID. Nó không bảo đảm một event nghiệp vụ chỉ được tạo một lần qua nhiều lần gọi API, nhiều instance hoặc sau khi ứng dụng khởi động lại. Dùng eventId ổn định và idempotency ở consumer nếu nghiệp vụ cần chống xử lý trùng.

## 6. Bind topic name từ cấu hình

Tạo KafkaTopicProperties.java:

~~~java
package com.acme.orders.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.kafka.topics")
public record KafkaTopicProperties(String orders) {
}
~~~

Không rải chuỗi orders.events trong controller và publisher. Một nguồn cấu hình giúp đổi topic theo môi trường mà không phải sửa code.

## 7. Provision topic cho môi trường thực hành

Với local/test, có thể khai báo NewTopic để Spring Kafka KafkaAdmin tạo topic khi application context khởi động:

~~~java
package com.acme.orders.config;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic ordersEventsTopic(KafkaTopicProperties topics) {
        return TopicBuilder.name(topics.orders())
                .partitions(3)
                .replicas(1)
                .build();
    }
}
~~~

Nếu broker không cho phép runtime identity tạo topic, hãy provision topic bằng Kafka CLI hoặc IaC trước khi chạy service. Ở production, topic thường cần được quản lý tập trung để kiểm soát partition, replication factor, retention, cleanup policy và ACL.

Lệnh tạo topic thủ công:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --create \
  --topic orders.events \
  --partitions 3 \
  --replication-factor 1

kafka-topics.sh --bootstrap-server localhost:9092 --describe \
  --topic orders.events
~~~

Trên Windows có thể dùng kafka-topics.bat. Đảm bảo CLI và ứng dụng cùng kết nối một cluster. Nếu topic đã tồn tại với ít partition hơn số được khai báo, KafkaAdmin có thể tăng partition count; Kafka không hỗ trợ giảm partition count. Không giả định NewTopic tự reconcile mọi topic config như retention hoặc cleanup policy. Quản lý các thay đổi đó bằng thao tác AdminClient/IaC có kiểm soát.

## 8. Định nghĩa event contract

Tạo enum OrderStatus.java:

~~~java
package com.acme.orders.messaging;

public enum OrderStatus {
    CREATED,
    CONFIRMED,
    CANCELLED
}
~~~

Tạo OrderEvent.java:

~~~java
package com.acme.orders.messaging;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderEvent(
        UUID eventId,
        String orderId,
        OrderStatus status,
        BigDecimal total,
        String currency,
        Instant occurredAt,
        String correlationId
) {
}
~~~

Các trường có mục đích riêng:

- eventId: định danh duy nhất của event để log, deduplicate và truy vết.
- orderId: aggregate/business key; dùng làm Kafka record key.
- status, total, currency: dữ liệu nghiệp vụ consumer cần.
- occurredAt: thời điểm event phát sinh ở application.
- correlationId: liên kết log/trace qua nhiều service.

Event là contract giữa producer và consumer. Sau khi phát hành, tránh đổi tên hoặc đổi kiểu field tùy tiện. Khi cần thêm field, áp dụng quy tắc schema evolution đã học: default/optional, kiểm thử consumer cũ và rollout theo thứ tự tương thích.

## 9. Viết OrderEventPublisher với KafkaTemplate

Tạo OrderEventPublisher.java:

~~~java
package com.acme.orders.messaging;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;

import com.acme.orders.config.KafkaTopicProperties;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;
    private final KafkaTopicProperties topics;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate,
            KafkaTopicProperties topics) {
        this.kafkaTemplate = kafkaTemplate;
        this.topics = topics;
    }

    public CompletableFuture<SendResult<String, OrderEvent>> publish(
            OrderEvent event) {

        ProducerRecord<String, OrderEvent> record =
                new ProducerRecord<>(
                        topics.orders(),
                        event.orderId(),
                        event
                );

        record.headers().add(
                "event-id",
                event.eventId().toString().getBytes(StandardCharsets.UTF_8)
        );
        record.headers().add(
                "correlation-id",
                event.correlationId().getBytes(StandardCharsets.UTF_8)
        );

        return kafkaTemplate.send(record);
    }
}
~~~

ProducerRecord cho phép kiểm soát topic, key, value và headers trước khi gửi. Bài lab đặt orderId làm key để các event của cùng một order được route về cùng partition theo partitioner mặc định.

Nếu chỉ gọi kafkaTemplate.send(topic, value), key sẽ không được đặt theo order. Khi đó partition có thể được chọn theo logic khác và các event của cùng order không còn được bảo đảm đi cùng partition.

## 10. Vì sao dùng orderId làm key?

Kafka chỉ bảo đảm thứ tự record bên trong một partition. Nếu mọi event của order-1001 dùng cùng key và partition count/partitioner không đổi, chúng sẽ đi cùng partition và được đọc theo thứ tự append.

Ví dụ:

| Event | Key | Ý nghĩa |
|---|---|---|
| evt-1 | order-1001 | CREATED |
| evt-2 | order-1001 | CONFIRMED |
| evt-3 | order-2002 | CREATED |

evt-1 và evt-2 được route cùng partition; evt-3 có thể vào partition khác. Không có thứ tự toàn cục giữa các partition.

Lưu ý: tăng số partition có thể làm key-to-partition mapping thay đổi với partitioner mặc định. Nếu nghiệp vụ cần thứ tự tuyệt đối cho một key xuyên suốt thay đổi topology, phải có kế hoạch partitioning/migration phù hợp.

## 11. Tạo request và response cho REST API

Tạo PublishOrderRequest.java:

~~~java
package com.acme.orders.web;

import java.math.BigDecimal;

import com.acme.orders.messaging.OrderStatus;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public record PublishOrderRequest(
        @NotNull
        @DecimalMin("0.01")
        BigDecimal total,

        @NotNull
        @Pattern(regexp = "[A-Z]{3}")
        String currency,

        @NotNull
        OrderStatus status
) {
}
~~~

Tạo PublishOrderResponse.java:

~~~java
package com.acme.orders.web;

import java.util.UUID;

public record PublishOrderResponse(
        UUID eventId,
        String result,
        String topic,
        Integer partition,
        Long offset
) {
}
~~~

Response trả metadata từ RecordMetadata. Partition và offset hữu ích khi điều tra event, nhưng không nên dùng offset làm business identifier vì offset chỉ có ý nghĩa trong một topic-partition.

## 12. Tạo REST controller phát hành event

Tạo OrderEventController.java:

~~~java
package com.acme.orders.web;

import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

import com.acme.orders.messaging.OrderEvent;
import com.acme.orders.messaging.OrderEventPublisher;
import jakarta.validation.Valid;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderEventController {

    private static final Logger log =
            LoggerFactory.getLogger(OrderEventController.class);

    private final OrderEventPublisher publisher;

    public OrderEventController(OrderEventPublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping("/{orderId}/events")
    public CompletableFuture<ResponseEntity<PublishOrderResponse>> publish(
            @PathVariable String orderId,
            @Valid @RequestBody PublishOrderRequest request,
            @RequestHeader(name = "X-Correlation-Id", required = false)
                    String correlationId) {

        UUID eventId = UUID.randomUUID();
        String effectiveCorrelationId =
                correlationId == null || correlationId.isBlank()
                        ? eventId.toString()
                        : correlationId;

        OrderEvent event = new OrderEvent(
                eventId,
                orderId,
                request.status(),
                request.total(),
                request.currency(),
                Instant.now(),
                effectiveCorrelationId
        );

        return publisher.publish(event).handle((sendResult, exception) -> {
            if (exception != null) {
                log.error("Failed to publish OrderEvent: eventId={}, orderId={}",
                        eventId, orderId, exception);

                return ResponseEntity
                        .<PublishOrderResponse>status(
                                HttpStatus.SERVICE_UNAVAILABLE)
                        .body(new PublishOrderResponse(
                                eventId, "FAILED", null, null, null));
            }

            RecordMetadata metadata = sendResult.getRecordMetadata();
            log.info("Published OrderEvent: eventId={}, orderId={}, topic={}, partition={}, offset={}",
                    eventId,
                    orderId,
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset());

            return ResponseEntity.accepted().body(
                    new PublishOrderResponse(
                            eventId,
                            "PUBLISHED",
                            metadata.topic(),
                            metadata.partition(),
                            metadata.offset()
                    )
            );
        });
    }
}
~~~

Controller đợi kết quả future trước khi trả HTTP response. Khi broker xác nhận send thành công, API trả 202 Accepted cùng metadata. Nếu send thất bại, API trả 503 Service Unavailable và ghi exception để vận hành điều tra.

Trong hệ thống có lưu lượng lớn, cần cân nhắc timeout HTTP và delivery.timeout.ms: request có thể chờ đến khi producer hết thời gian giao record. Nếu API cần phản hồi ngay trước broker acknowledgment, phải thiết kế trạng thái accepted/pending và cơ chế theo dõi kết quả riêng; không được trả PUBLISHED khi chưa biết send có thành công hay không.

## 13. Chạy ứng dụng và phát hành OrderEvent

Đảm bảo Kafka broker đang chạy tại localhost:9092 hoặc đặt biến môi trường KAFKA_BOOTSTRAP_SERVERS đúng địa chỉ broker.

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Gửi yêu cầu:

~~~bash
curl -i -X POST http://localhost:8080/api/orders/order-1001/events \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: checkout-req-9001" \
  -d '{
    "total": 1250000,
    "currency": "VND",
    "status": "CREATED"
  }'
~~~

Response thành công có dạng:

~~~json
{
  "eventId": "7d7a4a0e-4db7-44b8-9120-30f9a54a8c10",
  "result": "PUBLISHED",
  "topic": "orders.events",
  "partition": 1,
  "offset": 0
}
~~~

eventId, partition và offset trong ví dụ là dữ liệu minh họa; giá trị thực do application và broker tạo ra.

## 14. Quan sát record trong Kafka

Dùng console consumer để đọc record:

~~~bash
kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic orders.events \
  --from-beginning \
  --property print.key=true \
  --property print.headers=true
~~~

Bạn cần quan sát:

- Key bằng order-1001.
- Value là JSON chứa eventId, orderId, status, total, currency, occurredAt và correlationId.
- Header event-id và correlation-id có mặt.
- Topic/partition/offset khớp metadata trong response API.

JsonSerializer của Spring Kafka mặc định có thể thêm type information header. Khi nhiều service dùng ngôn ngữ hoặc package khác nhau, không nên để consumer phụ thuộc class name Java của producer; hãy thống nhất schema/contract và cấu hình type mapping hoặc deserializer target type rõ ràng.

## 15. Kiểm thử producer với Embedded Kafka

Unit test mock KafkaTemplate có thể kiểm tra lời gọi send, nhưng không chứng minh serializer và broker hoạt động đúng. Integration test sau gửi event qua publisher rồi đọc lại từ broker nhúng.

~~~java
package com.acme.orders.messaging;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.serializer.JsonDeserializer;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

@SpringBootTest(properties = {
        "spring.kafka.bootstrap-servers=${spring.embedded.kafka.brokers}",
        "app.kafka.topics.orders=orders.events"
})
@EmbeddedKafka(partitions = 3, topics = "orders.events")
class OrderEventPublisherIntegrationTest {

    @Autowired
    private EmbeddedKafkaBroker embeddedKafka;

    @Autowired
    private OrderEventPublisher publisher;

    @Test
    void publishesJsonEventWithKeyAndHeaders() throws Exception {
        Map<String, Object> consumerProperties =
                KafkaTestUtils.consumerProps(
                        "orders-producer-integration-test",
                        "false",
                        embeddedKafka
                );
        consumerProperties.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
                "earliest"
        );

        JsonDeserializer<OrderEvent> valueDeserializer =
                new JsonDeserializer<>(OrderEvent.class, false)
                        .trustedPackages("com.acme.orders.messaging");

        try (Consumer<String, OrderEvent> consumer =
                     new DefaultKafkaConsumerFactory<>(
                             consumerProperties,
                             new StringDeserializer(),
                             valueDeserializer
                     ).createConsumer()) {

            embeddedKafka.consumeFromAnEmbeddedTopic(
                    consumer,
                    "orders.events"
            );

            OrderEvent event = new OrderEvent(
                    UUID.randomUUID(),
                    "order-1001",
                    OrderStatus.CREATED,
                    new BigDecimal("1250000"),
                    "VND",
                    Instant.now(),
                    "checkout-req-9001"
            );

            var sendResult = publisher.publish(event)
                    .get(10, TimeUnit.SECONDS);

            ConsumerRecord<String, OrderEvent> received =
                    KafkaTestUtils.getSingleRecord(
                            consumer,
                            "orders.events",
                            Duration.ofSeconds(10)
                    );

            assertThat(received.key()).isEqualTo("order-1001");
            assertThat(received.value()).isEqualTo(event);
            assertThat(new String(
                    received.headers().lastHeader("event-id").value(),
                    java.nio.charset.StandardCharsets.UTF_8
            )).isEqualTo(event.eventId().toString());
            assertThat(new String(
                    received.headers().lastHeader("correlation-id").value(),
                    java.nio.charset.StandardCharsets.UTF_8
            )).isEqualTo(event.correlationId());
            assertThat(sendResult.getRecordMetadata().topic())
                    .isEqualTo("orders.events");
            assertThat(sendResult.getRecordMetadata().offset())
                    .isEqualTo(received.offset());
        }
    }
}
~~~

Test tạo topic ba partition để khớp với NewTopic bean của ứng dụng, nhưng không hard-code partition index vì partitioner chọn partition dựa trên key. KafkaTestUtils.getSingleRecord chờ record với timeout; tránh dùng Thread.sleep để đoán thời điểm record đến.

Giữ partition count của Embedded Kafka và NewTopic bean đồng nhất để test không phát sinh thao tác tăng partition ngoài ý muốn trong lúc Spring context khởi động.

## 16. Những gì producer acknowledgment bảo đảm

Khi KafkaTemplate.send() future hoàn tất thành công, producer nhận metadata của record đã được broker chấp nhận theo cấu hình producer. Mức durability còn phụ thuộc:

- acks được đặt là 0, 1 hay all.
- Replication factor và min.insync.replicas.
- Trạng thái ISR khi record được ghi.
- Broker/cluster storage và replication policy.

enable.idempotence=true giảm nguy cơ duplicate do retry của producer client. Nó không thay thế:

- Idempotency key ở tầng nghiệp vụ khi client gọi REST lặp lại.
- Transactional outbox nếu cần đồng bộ database commit và event publish.
- Consumer deduplication nếu event có thể được giao lại.
- Kafka transaction nếu cần atomic consume-process-produce trong Kafka.

## 17. Các lỗi thường gặp khi thực hành

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| TimeoutException khi send | Broker không reachable, metadata hoặc network chậm | Kiểm tra bootstrap server, broker log và network |
| UnknownTopicOrPartitionException | Topic sai tên/chưa được tạo | Dùng kafka-topics --list/--describe |
| SerializationException | DTO không serialize được hoặc serializer sai | Kiểm tra JsonSerializer, field và stack trace |
| API trả 503 | Future hoàn tất với exception | Đọc log exception gốc và producer metrics |
| Record có key null | Publisher dùng overload không truyền key | Gửi ProducerRecord với orderId |
| Consumer khác không deserialize được | Type header hoặc schema không tương thích | Kiểm tra JsonDeserializer/type mapping/schema |
| Event xuất hiện nhiều lần | REST retry, producer retry ngoài session hoặc business publish lặp | Dùng event ID/idempotency và kiểm tra producer semantics |

## 18. Bài tập mở rộng

1. Gửi ba event liên tiếp cho cùng orderId; xác minh chúng cùng partition và offset tăng dần.
2. Gửi event cho nhiều orderId; quan sát key được phân phối qua các partition.
3. Thay đổi linger.ms và batch.size; đo throughput, request rate và p95 latency bằng workload lặp lại.
4. Thử compression.type là none, gzip và snappy; so sánh bytes gửi và CPU.
5. Tắt broker trong lúc gửi; quan sát future thất bại và log của API.
6. Bổ sung idempotency key từ HTTP request để hai lần gọi cùng request không phát hai event nghiệp vụ.
7. Viết consumer nhỏ để kiểm tra JSON, key và headers nhận được.
8. Tách topic provisioning khỏi application runtime bằng Kafka CLI hoặc IaC.

Khi so sánh tuning, chỉ thay một nhóm tham số mỗi lần và dùng cùng workload. Không đánh giá cấu hình chỉ qua một lần gửi đơn lẻ vì batching cần lưu lượng đủ lớn mới thể hiện tác dụng.

## 19. Checklist hoàn thành

- [ ] Project khởi động với Java/Spring Boot version tương thích.
- [ ] Broker address được cấu hình qua environment.
- [ ] Topic orders.events tồn tại với partition/replication phù hợp.
- [ ] KafkaTemplate<String, OrderEvent> được inject thành công.
- [ ] JSON serializer hoạt động với OrderEvent.
- [ ] orderId được dùng làm Kafka key.
- [ ] Event ID và correlation ID có trong headers.
- [ ] Send future được xử lý cả success và failure.
- [ ] API chỉ báo PUBLISHED sau broker acknowledgment.
- [ ] Console consumer đọc được key, JSON payload và headers.
- [ ] Embedded Kafka integration test xác minh round-trip.
- [ ] Đã hiểu giới hạn của acks và idempotent producer.

Sau bài lab, bạn đã có producer phát hành OrderEvent hoàn chỉnh từ REST API đến Kafka broker. Các phần quan trọng là contract rõ ràng, key ổn định theo aggregate, metadata để truy vết và xử lý kết quả send bất đồng bộ. Đây là nền tảng để bài thực hành tiếp theo xây dựng consumer nhận và xử lý cùng event.
