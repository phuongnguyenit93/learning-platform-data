# Kiểm tra contract của externalized event

> **Dự án thực hành — SPRING_MODULITH_VERIFICATION_TESTING.** Xây một bộ kiểm thử hợp đồng cho sự kiện `OrderPaid` được Spring Modulith đưa ra Apache Kafka. Bài tập kết hợp kiểm chứng ranh giới module bằng `ApplicationModules`, kiểm thử module bằng `@ApplicationModuleTest`, thử nghiệm transaction/DB với broker thực và đặt quality gate trong CI. Trọng tâm là **đối tượng bên ngoài thực sự nhìn thấy gì**, chứ không chỉ event nội bộ có được publish hay không.

Một ứng dụng Spring Modulith có thể ghi đơn hàng thành công, phát `OrderPaid` và vẫn gửi sai Kafka topic, sai message key, lộ thuộc tính nội bộ hoặc thay đổi cấu trúc JSON khiến dịch vụ khác không đọc được. `PublishedEvents` chỉ nhìn thấy Spring application event, còn contract externalization gồm ít nhất **selection, mapping, routing, serialization, transaction và khả năng phục hồi**. Dự án sử dụng Java 17+, JUnit Jupiter, Spring Modulith, Spring Data JDBC/JdbcTemplate và Kafka. Snippet broker/serializer bên dưới nhắm đến **Spring Boot 3.x + Spring Kafka 3.x + Spring Modulith 1.4.x**; dùng cùng BOM tương thích. Nếu chọn Spring Boot 4/Spring Kafka 4, cần chuyển cấu hình sang API `JacksonJsonSerializer` phù hợp với phiên bản đó.

## 1. Chốt đề bài và bảng tiêu chí nghiệm thu

Hệ thống `shop` gồm module `orders` (quản lý thanh toán), module `integration` (định nghĩa cách externalize) và consumer ngoài ứng dụng `analytics`. Khi một đơn hàng được trả tiền, `orders` phát sự kiện domain trong transaction ghi DB; chỉ khi commit thành công, hệ thống mới gửi bản tin ngoài. Dịch vụ `analytics` cần một contract ổn định:

| Thuộc tính contract | Giá trị cam kết | Phép kiểm chứng |
| --- | --- | --- |
| Sự kiện được chọn | Chỉ `OrderPaid` có `@Externalized`, event nội bộ khác bị loại | `EventExternalizationConfiguration.supports()` |
| Kafka topic | `orders.paid.v1` | `ConsumerRecord.topic()` |
| Kafka message key | `orderId` ở dạng UUID string | `ConsumerRecord.key()` |
| Payload | JSON, `schemaVersion = 1`, `eventId`, `orderId`, `occurredAt`, `amount`, `currency` | Đọc JSON từ Kafka, kiểm đủ field/kiểu |
| Trường bị cấm | `internalNote` không có trong wire payload | Assert JSON không có key này |
| Transaction | Commit mới gửi, rollback không gửi | Test DB + broker ở hai nhánh |
| Retry | Publication lỗi được theo dõi và xử lý lại; consumer chống duplicate | Kiểm tra registry và idempotency |

**Đầu ra cần nộp:** mã nguồn producer/config/DTO, bộ test chọn–map–route độc lập broker, test tích hợp tiêu thụ bản tin Kafka, test rollback, kiểm tra ranh giới module và cấu hình CI. Bài được coi là đạt khi thay đổi thử topic, key, field hoặc phase `AFTER_COMMIT` khiến ít nhất một test thất bại. Đừng tính việc assertion `PublishedEvents` xanh là hoàn thành contract.

## 2. Dựng cấu trúc module và hạ tầng test

Một cấu trúc đề xuất (các đường dẫn này là **đích triển khai của dự án học viên**, không phải file tạo thêm bởi tài liệu):

```text
src/main/java/com/acme/shop/
  ShopApplication.java                  # @SpringBootApplication + @EnableAsync
  orders/
    OrderPaid.java                       # public domain event
    PaymentService.java                  # @Transactional: persist + publish
  integration/
    OrderPaidV1.java                     # JSON contract công khai
    EventOutboundConfiguration.java      # selection, mapping, routing
src/main/resources/
  schema.sql                             # bảng paid_orders cho demo
src/test/java/com/acme/shop/
  ModulithArchitectureTest.java
  orders/PaymentEventTest.java
  integration/OrderPaidContractTest.java
  integration/OrderPaidKafkaIT.java
```

Để externalizer và các module listener dùng `@Async` chạy theo đúng ngữ nghĩa bất đồng bộ, bật async support trong application:

```java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Khai báo theo BOM Spring Modulith và dependency management của Spring Boot, không gắn version riêng lẻ trái BOM:

```xml
<!-- Runtime -->
<dependency>
  <groupId>org.springframework.modulith</groupId>
  <artifactId>spring-modulith-events-api</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.modulith</groupId>
  <artifactId>spring-modulith-events-kafka</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.modulith</groupId>
  <artifactId>spring-modulith-starter-jdbc</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
<!-- Test -->
<dependency>
  <groupId>org.springframework.modulith</groupId>
  <artifactId>spring-modulith-starter-test</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.springframework.kafka</groupId>
  <artifactId>spring-kafka-test</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>com.h2database</groupId>
  <artifactId>h2</artifactId>
  <scope>test</scope>
</dependency>
```

Đặt bảng demo trong `src/main/resources/schema.sql` (hoặc migration Flyway/Liquibase của ứng dụng):

```sql
CREATE TABLE IF NOT EXISTS paid_orders (
    order_id VARCHAR(36) PRIMARY KEY,
    event_id VARCHAR(36) NOT NULL UNIQUE
);
```

Trong môi trường test, cho phép Spring Modulith tạo bảng Event Publication Registry, ví dụ `spring.modulith.events.jdbc.schema-initialization.enabled=true`. Production nên quản lý schema bằng migration rõ ràng. Nếu dùng PostgreSQL ngoài CI, thay cú pháp DDL và dữ liệu mẫu cho phù hợp. Kafka topic phải được tạo trước, không dựa vào broker tự tạo topic sai chính tả.

## 3. Thiết kế event domain và DTO wire tách biệt

Event ở API công khai của module `orders` có annotation để được chọn externalization; trường `internalNote` chỉ dùng trong ứng dụng, tuyệt đối không gửi ra ngoài:

```java
// src/main/java/com/acme/shop/orders/OrderPaid.java
package com.acme.shop.orders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.springframework.modulith.events.Externalized;

@Externalized("orders.paid.v1")
public record OrderPaid(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        BigDecimal amount,
        String currency,
        String internalNote) {}
```

Xác định **schema được phép công bố** ở một record khác, độc lập với việc refactor entity/domain:

```java
// src/main/java/com/acme/shop/integration/OrderPaidV1.java
package com.acme.shop.integration;

import java.math.BigDecimal;

public record OrderPaidV1(
        int schemaVersion,
        String eventId,
        String orderId,
        String occurredAt,
        BigDecimal amount,
        String currency) {}
```

Quy ước: `eventId` xác định một sự kiện duy nhất để consumer deduplicate; `orderId` xác định thực thể và làm partition key; `occurredAt` ở ISO-8601 UTC; `amount` là JSON number biểu diễn `BigDecimal`; `currency` là mã ISO 4217. Cần quy định rõ với consumer ý nghĩa của `amount` (đơn vị tiền chính, không phải số đơn vị nhỏ nhất). Tăng `schemaVersion` và định nghĩa topic/version mới khi có thay đổi phá vỡ khả năng đọc của consumer cũ.

## 4. Cấu hình selection → mapping → routing một cách kiểm thử được

Sử dụng cấu hình chính thức `EventExternalizationConfiguration`. Annotation chỉ chọn event và cố định topic; `routeKey` xác định Kafka key từ event gốc; `mapping` tạo wire DTO. Routing mặc định dựa trên **event trước mapping**, vì vậy key vẫn được lấy từ `OrderPaid`.

```java
// src/main/java/com/acme/shop/integration/EventOutboundConfiguration.java
package com.acme.shop.integration;

import com.acme.shop.orders.OrderPaid;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.events.EventExternalizationConfiguration;

@Configuration
public class EventOutboundConfiguration {

    @Bean
    EventExternalizationConfiguration eventExternalizationConfiguration() {
        return EventExternalizationConfiguration.defaults("com.acme.shop")
            .mapping(OrderPaid.class, event -> new OrderPaidV1(
                1,
                event.eventId().toString(),
                event.orderId().toString(),
                event.occurredAt().toString(),
                event.amount(),
                event.currency()
            ))
            .routeKey(OrderPaid.class, event -> event.orderId().toString())
            .build();
    }
}
```

`defaults("com.acme.shop")` giữ nguyên nguyên tắc chỉ chọn event có `@Externalized` nằm trong base package. Nếu cấu hình riêng dùng `externalizing().select(...)`, phải kiểm tra rằng predicate không vô tình chọn mọi event. Trường hợp muốn route theo DTO đã mapping, có `routeMapped()`; không bật nếu logic key vẫn cần field của domain event.

Ngoài Kafka, Modulith còn có adapter AMQP, JMS và Spring Messaging. **Ý nghĩa routing key phụ thuộc broker:** với Kafka nó là message key; với AMQP là routing key. Bài dùng Kafka cố định để có một contract thực nghiệm.

## 5. Viết unit test xác minh selector, topic, key và mapping

Lớp test sau dùng đúng bean config của production nên chạy nhanh, không cần Spring context hay Kafka. Với mỗi thay đổi routing/mapping, phép thử phải thất bại ở giá trị cụ thể.

```java
// src/test/java/com/acme/shop/integration/OrderPaidContractTest.java
package com.acme.shop.integration;

import static org.assertj.core.api.Assertions.assertThat;
import com.acme.shop.orders.OrderPaid;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.events.EventExternalizationConfiguration;
import org.springframework.modulith.events.RoutingTarget;

class OrderPaidContractTest {

    private final EventExternalizationConfiguration contract =
        new EventOutboundConfiguration().eventExternalizationConfiguration();

    private final ObjectMapper json = new ObjectMapper();

    private OrderPaid event() {
        return new OrderPaid(
            UUID.fromString("00000000-0000-0000-0000-000000000001"),
            UUID.fromString("00000000-0000-0000-0000-000000000002"),
            Instant.parse("2026-01-10T11:30:00Z"),
            new BigDecimal("125.50"), "VND", "never-externalize");
    }

    @Test
    void selectsOnlyMarkedEvents() {
        assertThat(contract.supports(event())).isTrue();
        assertThat(contract.supports(new InternalEvent("audit"))).isFalse();
    }

    @Test
    void routesToPublicTopicAndStablePartitionKey() {
        RoutingTarget route = contract.determineTarget(event());
        assertThat(route.getTarget()).isEqualTo("orders.paid.v1");
        assertThat(route.getKey()).isEqualTo(event().orderId().toString());
    }

    @Test
    void mapsOnlyPublicFieldsWithStableTypes() {
        assertThat(contract.map(event())).isInstanceOf(OrderPaidV1.class);
        JsonNode node = json.valueToTree(contract.map(event()));
        assertThat(node.size()).isEqualTo(6);
        assertThat(node.path("schemaVersion").asInt()).isEqualTo(1);
        assertThat(node.path("eventId").asText()).isEqualTo(event().eventId().toString());
        assertThat(node.path("orderId").asText()).isEqualTo(event().orderId().toString());
        assertThat(node.path("occurredAt").asText()).isEqualTo("2026-01-10T11:30:00Z");
        assertThat(node.path("amount").decimalValue())
            .isEqualByComparingTo(new BigDecimal("125.50"));
        assertThat(node.path("currency").asText()).isEqualTo("VND");
        assertThat(node.has("internalNote")).isFalse();
    }

    // Record không có @Externalized: phải không vượt qua selector.
    record InternalEvent(String kind) {}
}
```

Unit test này đo quy tắc cấu hình, **chưa đo bytes trên Kafka**: serializer thực tế có thể dùng converter khác, thêm metadata hoặc không được wiring đúng. Vì vậy cần thêm test qua broker ở mục 8. Với thông điệp dài hạn, lưu thêm một fixture JSON "golden" được consumer chấp nhận và so sánh compatibility có chủ đích, tránh snapshot quá cứng với thứ tự property hoặc cách biểu diễn số tương đương.

## 6. Gắn publish với transaction ghi DB để không gửi sự kiện chưa commit

Producer demo ghi dữ liệu vào bảng `paid_orders` và phát event trong **cùng một transaction**. Không gắn `@Transactional` vào chính method JUnit test rồi để auto rollback, bởi transactional listener `AFTER_COMMIT` sẽ không được kích hoạt. Các method service phải được gọi qua Spring proxy.

```java
// src/main/java/com/acme/shop/orders/PaymentService.java
package com.acme.shop.orders;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentService {

    private final JdbcTemplate jdbc;
    private final ApplicationEventPublisher publisher;

    public PaymentService(JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
        this.jdbc = jdbc;
        this.publisher = publisher;
    }

    @Transactional
    public void markPaid(OrderPaid event) {
        persistAndPublish(event);
    }

    @Transactional
    public void markPaidThenRollback(OrderPaid event) {
        persistAndPublish(event);
        throw new IllegalStateException("simulate business rollback");
    }

    private void persistAndPublish(OrderPaid event) {
        jdbc.update("INSERT INTO paid_orders (order_id, event_id) VALUES (?, ?)",
            event.orderId().toString(), event.eventId().toString());
        publisher.publishEvent(event);
    }
}
```

`spring-modulith-events-kafka` đăng ký externalizer nhận những event được chọn. Với chế độ mặc định dựa trên module listener, nó phản ứng khi transaction gốc commit và gửi tới broker; Event Publication Registry lưu dấu tiến trình nếu đã cấu hình starter lưu trữ (ví dụ JDBC). Transaction commit thành công không có nghĩa Kafka đã gửi xong, và lỗi gửi Kafka xảy ra sau commit không thể rollback lại bản ghi `paid_orders`.

## 7. Tách test phát event nội bộ khỏi test externalization

Test module của `orders` cần chắc rằng producer phát **đúng domain event**. Nó bổ sung bằng chứng, nhưng không được nhận là bằng chứng đủ cho topic/key/JSON của broker:

```java
// src/test/java/com/acme/shop/orders/PaymentEventTest.java
package com.acme.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

@ApplicationModuleTest
class PaymentEventTest {

    @Autowired PaymentService payments;

    @Test
    void publishesEventWithBusinessIdentity(PublishedEvents published) {
        OrderPaid event = new OrderPaid(
            UUID.randomUUID(), UUID.randomUUID(), Instant.now(),
            new BigDecimal("125.50"), "VND", "internal");

        payments.markPaid(event);

        assertThat(published.ofType(OrderPaid.class)
            .matching(OrderPaid::eventId, event.eventId()))
            .hasSize(1);
    }
}
```

`@ApplicationModuleTest` có scope theo module chứa test; chế độ mặc định `STANDALONE` có thể không khởi động module `integration`. Đó là chủ ý: producer test kiểm tra đúng sự kiện nội bộ. Test broker sau dùng `@SpringBootTest` để khởi động đầy đủ externalizer, producer, transaction manager và hạ tầng Kafka. Nếu muốn kiểm tra cấu trúc phụ thuộc bằng code, thêm:

```java
// src/test/java/com/acme/shop/ModulithArchitectureTest.java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModulithArchitectureTest {
    @Test
    void modulesObeyDeclaredBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Chú ý `verify()` chỉ xác nhận các quy tắc kiến trúc; nó không thể phát hiện đổi topic từ `orders.paid.v1` thành `orders.paid.v2`. Hai nhóm test phải cùng có mặt trong CI.

## 8. Kiểm tra bản tin thực nhận từ Kafka bằng JUnit

Đây là phần **trọng tâm**: chạy Spring Boot context, broker nhúng từ `spring-kafka-test`, transaction manager và registry JDBC. Tạo Kafka topic với **một partition** để đơn giản hóa ví dụ; cấu hình serializer dưới đây cố ý bỏ type headers Java để contract không bị ràng buộc tên lớp trong ứng dụng.

```java
// src/test/java/com/acme/shop/integration/OrderPaidKafkaIT.java
package com.acme.shop.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import com.acme.shop.orders.OrderPaid;
import com.acme.shop.orders.PaymentService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;

@SpringBootTest(properties = {
    "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.producer.value-serializer=org.springframework.kafka.support.serializer.JsonSerializer",
    "spring.kafka.producer.properties[spring.json.add.type.headers]=false",
    "spring.modulith.events.jdbc.schema-initialization.enabled=true"
})
@EmbeddedKafka(
    partitions = 1, topics = "orders.paid.v1",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderPaidKafkaIT {

    private static final String TOPIC = "orders.paid.v1";

    @Autowired PaymentService payments;
    @Autowired EmbeddedKafkaBroker broker;
    @Autowired JdbcTemplate jdbc;
    private final ObjectMapper json = new ObjectMapper();

    private OrderPaid event() {
        return new OrderPaid(UUID.randomUUID(), UUID.randomUUID(),
            Instant.parse("2026-01-10T11:30:00Z"),
            new BigDecimal("125.50"), "VND", "private-note");
    }

    private Consumer<String, String> observerAtTopicEnd() {
        Map<String, Object> props = KafkaTestUtils.consumerProps(
            "contract-" + UUID.randomUUID(), "false", broker);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        var consumer = new KafkaConsumer<String, String>(
            props, new StringDeserializer(), new StringDeserializer());

        TopicPartition partition = new TopicPartition(TOPIC, 0);
        consumer.assign(List.of(partition));
        consumer.seekToEnd(List.of(partition));
        consumer.position(partition); // chốt offset trước khi kích hoạt nghiệp vụ
        return consumer;
    }

    @Test
    void exposesOnlyThePublicWireContractAfterCommit() throws Exception {
        OrderPaid paid = event();
        try (Consumer<String, String> consumer = observerAtTopicEnd()) {
            payments.markPaid(paid); // transaction producer commit khi method trả về

            ConsumerRecord<String, String> record =
                KafkaTestUtils.getSingleRecord(
                    consumer, TOPIC, Duration.ofSeconds(15));
            JsonNode payload = json.readTree(record.value());

            assertThat(record.topic()).isEqualTo(TOPIC);
            assertThat(record.key()).isEqualTo(paid.orderId().toString());
            assertThat(payload.size()).isEqualTo(6);
            assertThat(payload.path("schemaVersion").asInt()).isEqualTo(1);
            assertThat(payload.path("eventId").asText())
                .isEqualTo(paid.eventId().toString());
            assertThat(payload.path("orderId").asText())
                .isEqualTo(paid.orderId().toString());
            assertThat(payload.path("occurredAt").asText())
                .isEqualTo("2026-01-10T11:30:00Z");
            assertThat(payload.path("amount").decimalValue())
                .isEqualByComparingTo(new BigDecimal("125.50"));
            assertThat(payload.path("currency").asText()).isEqualTo("VND");
            assertThat(payload.has("internalNote")).isFalse();
            assertThat(record.headers().lastHeader("__TypeId__")).isNull();
            assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM paid_orders WHERE order_id = ?",
                Integer.class, paid.orderId().toString())).isEqualTo(1);
        }
    }

    @Test
    void neverExternalizesARolledBackBusinessOperation() {
        OrderPaid paid = event();
        try (Consumer<String, String> consumer = observerAtTopicEnd()) {
            assertThatThrownBy(() -> payments.markPaidThenRollback(paid))
                .isInstanceOf(IllegalStateException.class);

            var observed = consumer.poll(Duration.ofSeconds(3));
            assertThat(observed.records(TOPIC))
                .noneMatch(record ->
                    record.value().contains(paid.eventId().toString()));
            assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM paid_orders WHERE order_id = ?",
                Integer.class, paid.orderId().toString())).isZero();
        }
    }
}
```

**Giải thích cách quan sát:** observer cố định offset ở cuối topic **trước khi** gọi producer; vì thế test không đọc lại sự kiện của test trước. Test positive chờ theo deadline, không dùng `Thread.sleep`. Test rollback xác nhận không xuất hiện event của chính mình trong cửa sổ quan sát **và** bảng `paid_orders` không còn `orderId` sau rollback. Cửa sổ âm tính không phải chứng minh toán học tuyệt đối; kết hợp nó với transactional registry và test phase `AFTER_COMMIT` ở mục 9.

Nếu chạy nhiều test Kafka song song, dùng topic riêng hoặc broker riêng để tránh giao thoa; `getSingleRecord` giả định đúng một record mới trong cửa sổ đó. Với dự án Spring Boot 4, có thể dùng `spring-boot-starter-kafka-test` theo BOM; trên Spring Boot 3, `spring-kafka-test` là lựa chọn thông dụng. Hãy kiểm tra starter phù hợp phiên bản project thực tế.

## 9. Kiểm thử rollback, broker outage và publication registry

Hợp đồng giao dịch của externalization không dừng ở bản tin happy path. Thực hiện tối thiểu ba tình huống gây lỗi có kiểm soát:

| Fault injection | Trạng thái DB/registry cần thấy | Broker/consumer cần thấy |
| --- | --- | --- |
| Transaction `markPaidThenRollback` ném exception | Không có `paid_orders` mới; publication gốc không được commit | Không có bản tin `eventId` đó |
| DB commit nhưng Kafka tạm không khả dụng | `paid_orders` đã tồn tại; publication có thể chưa hoàn tất | Không có xác nhận gửi thành công; sau khi broker phục hồi, retry đưa event tới topic |
| Broker nhận event nhưng tiến trình chết trước khi xác nhận hoàn tất publication | DB gốc đã commit; publication có thể được gửi lại | Consumer có thể nhận trùng; xử lý theo `eventId` phải idempotent |

Với starter JDBC/JPA cho Event Publication Registry, mỗi transactional listener/externalizer nhận publication được theo dõi riêng; khi listener gửi thành công, registry đánh dấu completed theo completion mode. Test failure phải **chờ publication rơi vào trạng thái quan sát được** rồi mới assert, vì việc gửi có thể bất đồng bộ. Đối chiếu theo `eventId` và target listener, không chỉ theo tổng số publication của cả suite. Tính năng tự phát lại lúc startup hoặc resubmit theo lịch phải được **cấu hình rõ ràng**; không suy đoán rằng mọi lỗi broker đều được retry vô hạn.

Tập kiểm chứng bổ sung (chạy broker Testcontainers ở tầng fault test nếu muốn dừng/khởi động broker) nên mô phỏng:

```text
1. Broker available; gửi event A -> consumer nhận đúng 1 lần.
2. Broker unavailable; commit event B -> DB có B, registry có B chưa completed.
3. Broker recover; chủ động resubmit B bằng API phù hợp version.
4. Consumer nhận B; registry của B eventually completed.
5. Resubmit/redeliver B lần nữa; consumer không tạo side effect thứ hai.
```

Ví dụ DB inbox của consumer: `processed_events(event_id PRIMARY KEY, processed_at)`; việc ghi inbox và cập nhật read model cần nằm trong một transaction của consumer. Dùng `INSERT ... ON CONFLICT DO NOTHING` (PostgreSQL) hoặc kỹ thuật tương đương theo DB; khóa unique bảo vệ khi hai lượt giao event đến đồng thời. Spring Modulith đảm bảo quản lý publication ở producer nhưng **không cam kết exactly-once side effect xuyên hệ thống**.

## 10. Chống thay đổi schema làm vỡ consumer

Contract không chỉ là JSON hợp lệ; consumer cũ phải đọc được version mới theo chính sách đã công bố. Đối với `orders.paid.v1`, giữ nguyên kiểu và ý nghĩa của sáu field bắt buộc; thêm field tùy chọn có thể tương thích nếu consumer bỏ qua unknown fields. Tuy nhiên một consumer cấu hình strict JSON schema có thể từ chối field mới: tiêu chí tương thích phải được thống nhất trong repo hoặc schema registry.

Viết thêm consumer contract test với fixture `order-paid-v1.json` do bên dùng API duy trì, kiểm tra:

```java
// Consumer compatibility test (mô tả phép kiểm tra độc lập broker).
// mapper là ObjectMapper có cấu hình giống consumer thực.
JsonNode json = mapper.readTree(wirePayload);
assertThat(json.path("schemaVersion").asInt()).isEqualTo(1);
assertThat(json.path("eventId").isTextual()).isTrue();
assertThat(json.path("orderId").isTextual()).isTrue();
assertThat(json.path("occurredAt").isTextual()).isTrue();
assertThat(json.path("amount").isNumber()).isTrue();
assertThat(json.path("currency").isTextual()).isTrue();
```

Trong snippet này `mapper` và `wirePayload` là fixture của consumer, cần định nghĩa trong test consumer thật. Đặt test phía consumer để bắt các thay đổi như `amount` từ number sang string hoặc `orderId` đổi thành object. Thử ba mutation có chủ ý để thấy gate hoạt động: đổi topic thành `orders.paid.v2` (route test fail), chuyển key thành `eventId` (key test fail), thêm `internalNote` vào DTO (wire test fail). Thêm mutation bỏ `@Externalized` để selector test fail.

Đối với event trong cùng aggregate, sử dụng key `orderId` giúp Kafka giữ thứ tự **trên cùng partition** của topic, với điều kiện producer/broker và retry không chủ động đảo thứ tự. Không mặc định xem toàn bộ event nhiều đơn hàng là có total order. Nếu thứ tự là contract cứng, bổ sung `aggregateVersion` hoặc sequence và test việc bỏ qua bản tin cũ.

## 11. Tạo quality gate CI và checklist bàn giao

Phân lớp kiểm thử để nhận diện nhanh nguyên nhân lỗi:

| Gate | Công cụ | Thất bại khi |
| --- | --- | --- |
| Kiến trúc | `ApplicationModules.of(...).verify()` | Phụ thuộc Java vượt ranh giới module |
| Selector/map/route | `OrderPaidContractTest`, JUnit + AssertJ | Chọn sai event; đổi topic/key; lộ field; sai kiểu dữ liệu |
| Domain producer | `@ApplicationModuleTest` + `PublishedEvents` | Producer không phát event có business identity chính xác |
| Kafka integration | `OrderPaidKafkaIT` + `@EmbeddedKafka` + JDBC transaction | JSON/topic/key sau commit không đúng, hoặc rollback vẫn gửi |
| Recovery & consumer | Test fault injection + registry + inbox unique | Lỗi gửi mất dấu, retry không hoạt động, xử lý trùng gây side effect |

Trong Maven, cấu hình Surefire chạy `*Test` và Failsafe chạy `*IT`; `mvn -B verify` thực hiện hai tập test khi plugin đã được khai báo. Với Spring Boot parent quản lý version plugin, thêm vào phần `build/plugins`:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-failsafe-plugin</artifactId>
  <executions>
    <execution>
      <goals>
        <goal>integration-test</goal>
        <goal>verify</goal>
      </goals>
    </execution>
  </executions>
</plugin>
```

Trong GitHub Actions/Jenkins/GitLab CI, chạy gate trên pull request trước khi cho merge. Ví dụ workflow GitHub Actions (điều chỉnh Java version theo BOM của project):

```yaml
name: externalized-event-contract
on: [pull_request]
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - run: ./mvnw -B verify
```

Không để `OrderPaidKafkaIT` bị loại khỏi CI do tên lớp kết thúc `IT` mà chưa có Failsafe. Nếu phần fault injection sử dụng Testcontainers, runner phải có Docker và cấu hình chạy container tương ứng.

```bash
# Sau khi cấu hình Maven Surefire/Failsafe và project thực tế:
./mvnw -B verify
```

**Checklist nghiệm thu**

- [ ] Annotation `@Externalized` chỉ áp dụng cho event được phê duyệt; selector có test phủ định.
- [ ] Wire DTO chỉ có sáu trường công khai; `internalNote` không tồn tại trong JSON.
- [ ] Kafka topic và message key ổn định, được assert từ `ConsumerRecord`.
- [ ] Producer cập nhật DB và publish trong cùng transaction thật.
- [ ] Commit tạo record hợp lệ; rollback không tạo record broker/DB.
- [ ] Test consumer nhận message bằng broker test, không chỉ mock `KafkaTemplate`.
- [ ] Gửi lỗi được quan sát qua publication registry; đã thử phục hồi.
- [ ] Consumer deduplicate bằng `eventId`, không dựa vào giả định exactly-once.
- [ ] Kiểm chứng ranh giới module và consumer schema compatibility cùng chạy trên CI.
- [ ] Các mutation đổi topic, key và DTO đều làm đúng gate đỏ.

**Tiêu chí hoàn thành:** trình bày được hai kết quả test đối chứng (commit gửi đúng, rollback không gửi), ảnh/log report CI chạy đủ gate, và mô tả được hành vi sau khi broker lỗi. Việc viết tài liệu không đồng nghĩa các ví dụ đã được biên dịch/chạy trong repository này; khi ghép vào project thật cần dùng BOM đã chọn, setup Kafka/JDBC và lifecycle test isolation tương ứng.

### Tài liệu kỹ thuật dùng để đối chiếu

- [Spring Modulith — Externalizing Events, configuration, Event Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html).
- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html).
- [Spring Modulith — `EventExternalizationConfiguration` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/EventExternalizationConfiguration.html).
- [Spring Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html).
- [Spring Boot — Testing with Embedded Kafka](https://docs.spring.io/spring-boot/reference/messaging/kafka.html).
