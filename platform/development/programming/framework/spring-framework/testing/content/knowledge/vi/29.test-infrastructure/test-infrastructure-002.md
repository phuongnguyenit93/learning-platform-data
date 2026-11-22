# Container kiểm thử cho cơ sở dữ liệu và broker

Khi kiểm thử một ứng dụng Spring có dùng cơ sở dữ liệu hoặc message broker, H2 trong bộ nhớ và mock repository thường không tái hiện đầy đủ môi trường chạy thật. PostgreSQL có kiểu dữ liệu, transaction, constraint và cú pháp SQL riêng; Kafka, RabbitMQ hoặc Redis cũng có protocol, acknowledgement, consumer group và cách quản lý kết nối riêng. Một bài test chỉ dùng mock có thể bỏ sót lỗi cấu hình hoặc khác biệt hành vi ở những thành phần đó.

Testcontainers giải quyết vấn đề bằng cách khởi động các dịch vụ thật trong container dành riêng cho test. Ứng dụng Spring kết nối tới container qua cổng được ánh xạ động, thực hiện migration, truy vấn database hoặc gửi/nhận message như khi chạy production. Khi test hoàn tất, container được dừng theo vòng đời mà test khai báo.

Container kiểm thử nằm giữa unit test và kiểm thử triển khai đầy đủ: dịch vụ nền là thật, nhưng test vẫn kiểm soát được image, cấu hình, dữ liệu và vòng đời. Đây là cách hữu ích để xác nhận repository, transaction, migration, message publisher và consumer cùng hoạt động với công nghệ mà ứng dụng thực sự sử dụng.

## 1. Khi nào nên dùng container kiểm thử?

Một test dùng mock repository có thể xác nhận service gọi `save(...)`, nhưng không chứng minh câu SQL được sinh đúng, migration chạy được hoặc unique constraint trong PostgreSQL hoạt động như mong đợi. Tương tự, mock `KafkaTemplate` có thể xác nhận ứng dụng gọi `send(...)`, nhưng không chứng minh broker chấp nhận message, serializer tương thích hoặc consumer nhận được message.

Container kiểm thử cung cấp các dịch vụ thực để ứng dụng giao tiếp:

```text
JUnit / Spring Test
       |
       v
Spring ApplicationContext
       |
       +---------------------------+
       |                           |
       v                           v
DataSource / JPA              KafkaTemplate / RabbitTemplate
       |                           |
       | JDBC                      | AMQP / Kafka protocol
       v                           v
PostgreSQL container          Broker container
       |                           |
       +-------------+-------------+
                     |
                     v
              Assertions trong test
```

Nên cân nhắc Testcontainers khi cần kiểm tra:

- Repository và query trên đúng loại database production.
- Schema migration bằng Flyway hoặc Liquibase.
- Transaction, isolation, constraint, index và locking.
- Serialization, publish/consume, routing key, topic, partition hoặc acknowledgement.
- Cấu hình connection pool, driver, broker client và authentication.
- Hành vi khi dịch vụ khởi động chậm, tạm thời không sẵn sàng hoặc trả lỗi.

Unit test vẫn phù hợp để kiểm tra quy tắc nghiệp vụ thuần. Container test nên tập trung vào ranh giới tích hợp với database hoặc broker, nơi hành vi phụ thuộc sản phẩm thật.

## 2. Testcontainers hoạt động như thế nào?

Testcontainers là thư viện Java điều khiển container runtime. Trong test, ta khai báo image cần dùng, cổng, biến môi trường, volume, command và điều kiện sẵn sàng. Thư viện tạo container, chờ dịch vụ sẵn sàng rồi cung cấp địa chỉ và cổng được ánh xạ cho ứng dụng.

Vòng đời thường có dạng:

1. Test khai báo container và image.
2. Testcontainers yêu cầu Docker-compatible runtime khởi động container.
3. Container khởi chạy database hoặc broker và công bố cổng dịch vụ.
4. Test lấy host/cổng động từ container và cấu hình Spring.
5. Spring tạo connection pool hoặc broker client và chạy migration nếu có.
6. Test thực hiện hành vi ứng dụng và assertion trên dữ liệu/message thật.
7. Testcontainers dừng và dọn container theo lifecycle đã chọn.

Không nên giả định dịch vụ luôn ở `localhost:5432`, `localhost:5672` hoặc `localhost:9092`. Testcontainers thường ánh xạ cổng container sang một cổng trống trên host. Luôn lấy địa chỉ từ API của container như `getJdbcUrl()`, `getAmqpPort()` hoặc `getBootstrapServers()`.

## 3. Dependencies cho JUnit và database

Ví dụ sau dùng Gradle. Nên quản lý phiên bản Testcontainers tập trung bằng BOM để các module cùng phiên bản:

```groovy
dependencies {
    testImplementation(platform("org.testcontainers:testcontainers-bom:1.20.6"))
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")

    testRuntimeOnly("org.postgresql:postgresql")
}
```

Nếu dự án dùng Maven, import BOM ở `dependencyManagement` và khai báo các module ở test scope:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>1.20.6</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>postgresql</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Các phiên bản trên minh họa một bộ dependency tương thích; dự án nên chọn một phiên bản Testcontainers được hỗ trợ và quản lý thống nhất. Module `junit-jupiter` cung cấp tích hợp annotation với JUnit 5. Module `postgresql` cung cấp `PostgreSQLContainer`; JDBC driver vẫn là dependency riêng của ứng dụng.

## 4. Khởi chạy PostgreSQL container bằng JUnit 5

`@Testcontainers` bật extension JUnit Jupiter. `@Container` đánh dấu container mà extension quản lý. Một field `static` được khởi động một lần cho cả test class và dừng sau class; field instance được khởi động và dừng cho từng test method.

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
class PostgreSqlContainerTests {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders")
                    .withUsername("test")
                    .withPassword("test");

    @Test
    void containerExposesJdbcConnectionDetails() {
        assertThat(POSTGRES.isRunning()).isTrue();
        assertThat(POSTGRES.getJdbcUrl()).contains("jdbc:postgresql:");
        assertThat(POSTGRES.getUsername()).isEqualTo("test");
    }
}
```

`PostgreSQLContainer` biết cách cấu hình image PostgreSQL, database, username/password và chờ database sẵn sàng. Test không cần tự viết shell script để khởi động database.

Hãy pin tag image cụ thể, ví dụ `postgres:16-alpine`, thay vì dùng `latest`. Nếu tag thay đổi bất ngờ, test có thể nhận phiên bản database khác với phiên bản production và cho kết quả không ổn định.

## 5. Kết nối Spring Boot tới container bằng DynamicPropertySource

Với Spring Boot, `@DynamicPropertySource` đăng ký các property động trước khi application context được tạo. Cách này hoạt động với nhiều loại container và không phụ thuộc Spring Boot có sẵn service connection factory cho dịch vụ đó hay không.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class OrderRepositoryIntegrationTests {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders")
                    .withUsername("test")
                    .withPassword("test");

    @Autowired
    OrderRepository orderRepository;

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }

    @Test
    void savesAndLoadsOrderUsingPostgres() {
        OrderEntity saved = orderRepository.save(
                new OrderEntity("ORD-100", "CREATED"));

        OrderEntity loaded = orderRepository.findById(saved.getId())
                .orElseThrow();

        assertThat(loaded.getOrderNumber()).isEqualTo("ORD-100");
        assertThat(loaded.getStatus()).isEqualTo("CREATED");
    }
}
```

Ví dụ giả định ứng dụng có `OrderRepository`, `OrderEntity` và schema phù hợp. `spring.datasource.url` nhận JDBC URL có cổng động mà container cung cấp. Username/password cũng lấy trực tiếp từ container.

Khi Spring tạo `DataSource`, Flyway hoặc Liquibase có thể chạy migration như lúc ứng dụng khởi động. Nhờ vậy, test còn xác nhận migration có thể áp dụng trên đúng loại database. Nếu dùng `@SpringBootTest`, bảo đảm test context quét đúng cấu hình repository, entity và migration của ứng dụng.

## 6. Dùng @ServiceConnection trong Spring Boot

Spring Boot 3.1 trở lên cung cấp `@ServiceConnection` để tự tạo `ConnectionDetails` từ một số loại container đã được hỗ trợ. Cách này giảm việc khai báo từng property bằng `@DynamicPropertySource`.

Thêm module testcontainers của Spring Boot:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
}
```

Sau đó đánh dấu container:

```java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;

@SpringBootTest
@Testcontainers
class OrderRepositoryServiceConnectionTests {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Spring Boot nhận diện loại container và cung cấp connection details cho auto-configuration tương ứng. Không cần khai báo thủ công `spring.datasource.url`, username và password nếu service connection factory phù hợp được nạp.

`@ServiceConnection` chỉ hoạt động với loại service mà Spring Boot có hỗ trợ connection details. Với container tùy biến hoặc property riêng của ứng dụng, dùng `@DynamicPropertySource` vẫn là lựa chọn linh hoạt. Có thể kết hợp hai cách: dùng service connection cho datasource, còn dynamic property cho một endpoint hoặc broker không có factory phù hợp.

## 7. Kiểm thử migration và tính năng riêng của database

Một lợi ích quan trọng của container là chạy migration trên cùng engine với production. Ví dụ, Flyway có thể dùng cú pháp PostgreSQL mà H2 không hỗ trợ hoặc xử lý khác.

Với Spring Boot, nếu migration được cấu hình trong ứng dụng, khởi tạo context thường sẽ chạy Flyway trước khi test method thực thi. Test có thể kiểm tra schema sau migration:

```java
import org.springframework.jdbc.core.JdbcTemplate;

@Autowired
JdbcTemplate jdbcTemplate;

@Test
void migrationCreatesExpectedIndex() {
    Integer count = jdbcTemplate.queryForObject("""
            select count(*)
            from pg_indexes
            where schemaname = 'public'
              and indexname = 'idx_orders_order_number'
            """, Integer.class);

    assertThat(count).isEqualTo(1);
}
```

Ví dụ truy vấn catalog `pg_indexes` đặc thù PostgreSQL. Đây là điều mà H2 không thể chứng minh tương đương. Tuy nhiên, không nên viết mọi test repository bằng SQL catalog nội bộ; chỉ dùng khi mục tiêu là xác nhận migration hoặc cấu trúc database cụ thể.

Container cũng hữu ích để kiểm tra unique constraint, foreign key, JSONB, sequence, collation, timezone, locking và isolation. Hãy chọn assertion gắn với rủi ro thực tế của ứng dụng thay vì lặp lại mọi tính năng của database.

## 8. Cách ly dữ liệu giữa các test

Container riêng không tự bảo đảm dữ liệu sạch giữa các test nếu nhiều method dùng chung một static container. Database sẽ giữ lại row do test trước tạo.

Một số cách quản lý dữ liệu:

| Cách | Phạm vi | Khi phù hợp |
|---|---|---|
| `@Transactional` và rollback sau test | Transaction của test | Test repository/service chạy trong transaction Spring và không cần commit để thành phần khác đọc |
| Xóa dữ liệu trong `@BeforeEach` | Bảng hoặc tập dữ liệu cụ thể | Test cần kiểm soát fixture rõ ràng |
| Tạo schema/database riêng cho test | Một nhóm test hoặc tenant | Test migration hoặc nhiều test chạy song song |
| Container instance cho mỗi test method | Container riêng cho từng method | Cần isolation cao, chấp nhận thời gian khởi động lớn hơn |
| Dùng key dữ liệu duy nhất | Mỗi test | Test song song hoặc test cần giữ dữ liệu đã commit |

`@Transactional` có thể tự rollback transaction do test quản lý, nhưng không phải lúc nào cũng đủ. Nếu ứng dụng mở transaction riêng ở thread khác, dùng `REQUIRES_NEW`, publish message sau commit hoặc thực hiện async processing, transaction test có thể không rollback phần thay đổi đó. Test cần kiểm tra hành vi commit thật nên chủ động quản lý transaction thay vì dựa vào rollback mặc định.

Với Flyway hoặc Liquibase, không nên chạy migration lại trong mỗi method nếu không cần thiết. Thường container được khởi động một lần cho class, migration chạy khi Spring context tạo, còn mỗi test quản lý dữ liệu của nó.

## 9. Vòng đời container và Spring context cache

Vòng đời JUnit và vòng đời Spring `ApplicationContext` là hai cơ chế riêng. Spring Test có thể cache context để dùng lại giữa nhiều test class. Nếu context chứa `DataSource` hoặc broker client trỏ tới một container đã bị dừng sau class đầu tiên, test class sau có thể thất bại khi tái sử dụng context cũ.

Một số nguyên tắc:

- Dùng static `@Container` khi muốn container sống suốt test class.
- Tránh shutdown container trước khi Spring context đang dùng nó không còn được sử dụng.
- Nếu nhiều class chia sẻ cùng context, cân nhắc một container singleton có lifecycle tương thích với toàn bộ test suite hoặc dùng cùng test configuration để Spring nhận diện context giống nhau.
- Không dùng chung response queue hoặc broker state giữa các test song song mà không có isolation.
- Đừng tạo container mới trong mỗi method nếu thời gian startup không cần thiết; việc này có thể làm test suite chậm đáng kể.

Có thể dùng singleton container pattern bằng static field trong một lớp base hoặc utility test. Tuy nhiên, pattern này cần được thiết kế cẩn thận vì JUnit extension `@Container` quản lý vòng đời theo class. Nếu tự start container trong static initializer hoặc `@BeforeAll`, chính test code phải chịu trách nhiệm dừng container ở thời điểm phù hợp.

## 10. Container cho RabbitMQ

Với broker AMQP như RabbitMQ, Testcontainers có module riêng:

```groovy
dependencies {
    testImplementation("org.testcontainers:rabbitmq")
}
```

Container có thể tạo user riêng cho test và mở cổng AMQP:

```java
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class RabbitMessagingIntegrationTests {

    @Container
    static final RabbitMQContainer RABBIT =
            new RabbitMQContainer("rabbitmq:3.13-management-alpine")
                    .withUser("test", "test", "/")
                    .withPermission("/", "test", ".*", ".*", ".*");

    @DynamicPropertySource
    static void rabbitProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", RABBIT::getHost);
        registry.add("spring.rabbitmq.port", RABBIT::getAmqpPort);
        registry.add("spring.rabbitmq.username", () -> "test");
        registry.add("spring.rabbitmq.password", () -> "test");
    }
}
```

`RabbitMQContainer` chờ broker sẵn sàng và cung cấp host cùng cổng AMQP được ánh xạ. Dùng user riêng tránh phụ thuộc tài khoản mặc định `guest`, vốn thường bị giới hạn kết nối từ host bên ngoài container.

Giả sử ứng dụng có một queue `orders.events` và `RabbitTemplate` được auto-configure:

```java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class RabbitTestConfiguration {

    @Bean
    Queue ordersQueue() {
        return new Queue("orders.events", false);
    }
}
```

Test có thể publish message và đọc message từ broker:

```java
import java.time.Duration;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
class RabbitTemplateIntegrationTests {

    @Container
    static final RabbitMQContainer RABBIT =
            new RabbitMQContainer("rabbitmq:3.13-management-alpine")
                    .withUser("test", "test", "/")
                    .withPermission("/", "test", ".*", ".*", ".*");

    @Autowired
    RabbitTemplate rabbitTemplate;

    @DynamicPropertySource
    static void rabbitProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", RABBIT::getHost);
        registry.add("spring.rabbitmq.port", RABBIT::getAmqpPort);
        registry.add("spring.rabbitmq.username", () -> "test");
        registry.add("spring.rabbitmq.password", () -> "test");
    }

    @Test
    void publishesMessageToRabbitQueue() {
        rabbitTemplate.convertAndSend("orders.events", "order-42");

        String received = awaitMessage();
        assertThat(received).isEqualTo("order-42");
    }

    private String awaitMessage() {
        long deadline = System.nanoTime() + Duration.ofSeconds(5).toNanos();
        while (System.nanoTime() < deadline) {
            Object message = rabbitTemplate.receiveAndConvert("orders.events");
            if (message != null) {
                return message.toString();
            }
            try {
                Thread.sleep(50);
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new AssertionError("Interrupted while waiting for message", ex);
            }
        }
        throw new AssertionError("No message arrived in orders.events");
    }
}
```

Đây là ví dụ kiểm tra publish và consume qua broker thật. Queue phải được khai báo trước khi gửi; có thể dùng bean `Queue` như cấu hình trên hoặc khai báo topology bằng cấu hình ứng dụng. Vòng lặp có deadline chờ message trong khoảng hữu hạn để tránh phụ thuộc vào tốc độ scheduling. Với test cần chờ listener bất đồng bộ xử lý message, nên dùng Awaitility hoặc một latch/condition đồng bộ thay vì polling trực tiếp queue.

## 11. Container cho Kafka

Kafka cần bootstrap server mà producer và consumer có thể truy cập. Module Testcontainers Kafka cung cấp container chuyên dụng:

```groovy
dependencies {
    testImplementation("org.testcontainers:kafka")
}
```

Ví dụ dùng image Apache Kafka:

```java
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class KafkaIntegrationTests {

    @Container
    static final KafkaContainer KAFKA = new KafkaContainer(
            DockerImageName.parse("apache/kafka-native:3.8.0"));

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.kafka.bootstrap-servers",
                KAFKA::getBootstrapServers);
    }
}
```

`getBootstrapServers()` trả địa chỉ mà test process có thể dùng để kết nối tới broker. Không tự ghép `localhost:9092`, vì Testcontainers có thể ánh xạ broker sang cổng khác và cấu hình advertised listener phụ thuộc container.

Với Spring Kafka, `KafkaTemplate` và listener container có thể được tạo từ `spring.kafka.bootstrap-servers`. Một test publisher có thể gửi message:

```java
@Autowired
KafkaTemplate<String, String> kafkaTemplate;

@Test
void publishesOrderEvent() throws Exception {
    kafkaTemplate.send("orders", "order-42", "CREATED")
            .get(10, TimeUnit.SECONDS);
}
```

Đoạn này xác nhận producer hoàn tất việc gửi theo future, nhưng để chứng minh broker lưu message và consumer đọc được, cần tạo consumer test hoặc kiểm tra listener ứng dụng. Consumer cần group id riêng, cấu hình `auto.offset.reset=earliest` nếu muốn đọc message đã publish trước khi consumer được gán partition, và đóng consumer sau test.

Khi test listener bất đồng bộ, không chỉ kiểm tra `KafkaTemplate.send(...)` đã hoàn tất. Việc broker nhận record và listener đã xử lý record là hai sự kiện khác nhau. Dùng latch, Awaitility hoặc một trạng thái quan sát được trong database để đợi kết quả listener, với timeout hữu hạn.

## 12. Dùng database và broker trong cùng một test

Nhiều luồng nghiệp vụ vừa ghi database vừa publish message. Container cho phép kiểm thử tích hợp qua cả hai ranh giới:

```java
@Testcontainers
@SpringBootTest
class OrderPublicationIntegrationTests {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Container
    static final RabbitMQContainer RABBIT =
            new RabbitMQContainer("rabbitmq:3.13-management-alpine")
                    .withUser("test", "test", "/")
                    .withPermission("/", "test", ".*", ".*", ".*");

    @DynamicPropertySource
    static void infrastructureProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("spring.rabbitmq.host", RABBIT::getHost);
        registry.add("spring.rabbitmq.port", RABBIT::getAmqpPort);
        registry.add("spring.rabbitmq.username", () -> "test");
        registry.add("spring.rabbitmq.password", () -> "test");
    }

    // Inject OrderService, OrderRepository and a message consumer/observer.
}
```

Test gọi use case tạo đơn hàng, sau đó xác nhận row đã được lưu trong PostgreSQL và event tương ứng xuất hiện trong RabbitMQ hoặc được consumer xử lý. Nếu ứng dụng dùng transactional outbox, test nên xác nhận outbox record được ghi cùng transaction, rồi kiểm tra publisher chuyển record đó thành message theo cơ chế thực tế.

Đối với transaction giữa database và broker, không nên giả định hai hệ thống tự động commit nguyên tử với nhau. Nếu ứng dụng dùng `@TransactionalEventListener`, outbox, retry hoặc publisher confirm, test cần xác nhận đúng cơ chế đó. Container test giúp quan sát hành vi tích hợp thật nhưng không tự cung cấp distributed transaction.

## 13. Chờ dịch vụ sẵn sàng và cấu hình readiness

Container ở trạng thái `running` chưa chắc ứng dụng bên trong đã sẵn sàng nhận request. Testcontainers module chuyên biệt thường đã định nghĩa wait strategy phù hợp, chẳng hạn chờ cổng hoặc log thông báo database khởi động.

Với `GenericContainer`, hãy khai báo readiness rõ ràng:

```java
GenericContainer<?> service = new GenericContainer<>("some-service:1.2.3")
        .withExposedPorts(8080)
        .waitingFor(Wait.forHttp("/health").forStatusCode(200));
```

Có thể dùng `Wait.forListeningPort()` hoặc `Wait.forLogMessage(...)` tùy dịch vụ. Không nên dùng `Thread.sleep(5000)` để đoán container đã sẵn sàng. Wait strategy có timeout và điều kiện cụ thể nên test báo lỗi rõ hơn khi dịch vụ không khởi động.

Nếu image có thời gian bootstrap dài, hãy kiểm tra log container và cấu hình wait strategy. Đừng tăng timeout vô hạn để che giấu lỗi khởi động hoặc cấu hình sai.

## 14. Pin image, dữ liệu và cấu hình để test lặp lại được

Container test vẫn có thể không ổn định nếu image, dữ liệu hoặc cấu hình thay đổi tùy ý.

**Pin phiên bản image.** Dùng tag cụ thể, tốt hơn nữa là digest trong pipeline cần khả năng tái lập nghiêm ngặt. Tránh `latest`.

**Dùng dữ liệu khởi tạo rõ ràng.** Tạo schema bằng migration và dữ liệu fixture bằng builder hoặc SQL test. Không phụ thuộc dữ liệu còn sót lại từ lần chạy trước.

**Tách thông tin xác thực test.** Dùng username/password riêng cho container, không đưa secret production vào test.

**Đặt timezone và locale có chủ đích.** Nếu logic phụ thuộc timezone, khai báo rõ cấu hình database và JVM để test không thay đổi theo máy developer hoặc CI.

**Kiểm soát resource.** Đặt giới hạn timeout và tránh chạy quá nhiều container nặng đồng thời trên runner có ít CPU/RAM.

## 15. Chạy Testcontainers trong CI

Máy chạy test cần có Docker-compatible container runtime mà Testcontainers có thể truy cập. Trên developer machine, Docker Desktop hoặc Docker Engine thường cung cấp môi trường đó. Trên CI, runner cần quyền truy cập Docker daemon/socket hoặc một cấu hình remote runtime được hỗ trợ.

Các điểm cần chuẩn bị trong pipeline:

- Bảo đảm container runtime hoạt động trước khi chạy test.
- Cấp quyền truy cập daemon cho process chạy Gradle/Maven.
- Cho phép tải image hoặc cấu hình registry mirror/cache phù hợp.
- Cấp đủ CPU, RAM và disk cho database/broker image.
- Dùng timeout CI phù hợp với thời gian pull image và bootstrap dịch vụ.
- Thu thập log container khi test thất bại để tìm lỗi readiness hoặc cấu hình.
- Dọn container sau job, kể cả khi test bị hủy.

Nếu CI không cho phép Docker hoặc container runtime, Testcontainers không thể khởi động dịch vụ theo cách thông thường. Khi đó có thể dùng service container do CI cung cấp sẵn, một môi trường test dùng chung có quản lý, hoặc chạy các test container trong job/runner chuyên dụng. Đừng silently bỏ qua integration test quan trọng chỉ vì runner thiếu runtime; hãy biểu diễn rõ nhóm test đó trong pipeline.

## 16. Dùng container reuse và singleton có cân nhắc

Khởi động PostgreSQL hoặc Kafka có thể tốn thời gian. Testcontainers hỗ trợ reuse container trong một số môi trường phát triển, nhưng reuse không phải mặc định phù hợp cho CI vì dữ liệu và trạng thái có thể tồn tại giữa các lần chạy.

Nếu bật reuse, test phải tự bảo đảm database schema, queue/topic và dữ liệu được reset đúng cách. Không dựa vào thứ tự test hoặc giả định container luôn mới. Với CI, lifecycle do test quản lý thường dễ tái lập hơn.

Singleton container có thể giảm startup khi nhiều test class dùng cùng dịch vụ. Tuy nhiên, nó làm tăng rủi ro state dùng chung và tương tác với Spring context cache. Hãy chỉ dùng khi có lý do đo được và có quy ước isolation rõ ràng.

## 17. Khi nào dùng @ServiceConnection, DynamicPropertySource hoặc cấu hình riêng?

| Cách cấu hình | Ưu điểm | Hạn chế |
|---|---|---|
| `@ServiceConnection` | Ít boilerplate, Spring Boot tự tạo connection details | Chỉ áp dụng cho loại container/service được Boot hỗ trợ |
| `@DynamicPropertySource` | Linh hoạt, có thể ánh xạ mọi property từ container | Phải khai báo tên property và getter thủ công |
| `ApplicationContextInitializer` | Có thể thay đổi environment trước khi context refresh | Nhiều code hơn, thường không cần cho trường hợp đơn giản |
| Property file riêng cho test | Dễ đọc với giá trị cố định | Không phù hợp cổng động do container cấp |

Với database phổ biến trong Spring Boot, `@ServiceConnection` thường là lựa chọn gọn. Với broker, dịch vụ tùy biến hoặc nhiều property đặc thù, `@DynamicPropertySource` là cách tường minh và dễ kiểm soát.

## 18. Lỗi thường gặp khi dùng container kiểm thử

| Cách làm | Vấn đề | Cách làm phù hợp hơn |
|---|---|---|
| Dùng cổng cố định như `5432` hoặc `9092` | Cổng host có thể được ánh xạ khác hoặc đang bận | Lấy JDBC URL, AMQP port hoặc bootstrap server từ container |
| Dùng H2 để thay PostgreSQL rồi coi là tương đương | SQL, kiểu dữ liệu, transaction và constraint có thể khác | Chạy integration test trên cùng engine production |
| Chỉ mock repository hoặc KafkaTemplate | Không kiểm tra driver, protocol, serializer hoặc broker | Dùng container cho test ở ranh giới tích hợp |
| Dùng image `latest` | Test có thể đổi hành vi khi image được cập nhật | Pin tag hoặc digest |
| Không dọn dữ liệu giữa các method | Test phụ thuộc thứ tự hoặc dữ liệu cũ | Transaction rollback, fixture cleanup hoặc schema riêng |
| Dừng container khi Spring context còn được cache | Bean vẫn giữ URL tới dịch vụ đã dừng | Đồng bộ container lifecycle với context lifecycle |
| Chỉ kiểm tra producer future hoàn tất | Chưa chứng minh consumer đã xử lý message | Chờ và xác nhận kết quả ở consumer |
| Dùng `Thread.sleep` để đợi startup | Test chậm và không ổn định | Dùng wait strategy, Awaitility hoặc latch |
| Chạy quá nhiều broker/database song song | CI thiếu CPU/RAM và test chậm bất thường | Giới hạn parallelism hoặc chia nhóm test |
| Dùng reuse mà không reset state | Kết quả phụ thuộc lần chạy trước | Tắt reuse trong CI hoặc quản lý reset rõ ràng |

## 19. Quy trình xây dựng integration test với database và broker

1. Xác định công nghệ thật mà ứng dụng dùng: PostgreSQL, MySQL, Kafka, RabbitMQ hoặc dịch vụ khác.
2. Chọn module Testcontainers tương ứng và pin image version.
3. Khai báo container bằng `@Container`, chọn static hay instance theo isolation cần thiết.
4. Cấu hình Spring bằng `@ServiceConnection` hoặc `@DynamicPropertySource`.
5. Để migration và cấu hình production liên quan được nạp trong test context.
6. Chuẩn bị dữ liệu/queue/topic fixture có thể lặp lại.
7. Thực hiện use case qua bean ứng dụng, không gọi trực tiếp driver hoặc broker API nếu mục tiêu là kiểm tra integration layer.
8. Assertion kết quả trong database hoặc quan sát message từ broker/consumer.
9. Với async messaging, chờ điều kiện hoàn tất bằng timeout hữu hạn.
10. Dọn dữ liệu và dừng container theo lifecycle tương thích với Spring context cache.
11. Bảo đảm CI có container runtime, tài nguyên và quyền pull image.

## 20. Tài liệu tham khảo

- [Testcontainers for Java — Documentation](https://java.testcontainers.org/): khái niệm, lifecycle, JUnit Jupiter integration và các module dịch vụ.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): cấu hình `PostgreSQLContainer` và JDBC connection details.
- [Testcontainers — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/): cấu hình RabbitMQ container.
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/): Kafka container và bootstrap server.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): tích hợp Testcontainers và `@ServiceConnection`.
- [Spring Framework — DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): đăng ký property động cho test context.

Container kiểm thử giúp ứng dụng Spring làm việc với database và broker thật trong một môi trường cục bộ có thể tái tạo. Hãy dùng đúng image và phiên bản, lấy địa chỉ từ container, kết nối Spring bằng service connection hoặc dynamic properties, rồi kiểm tra hành vi ở ranh giới tích hợp. Quản lý lifecycle và dữ liệu rõ ràng để test có thể chạy độc lập trên máy developer lẫn CI.
