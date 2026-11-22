# RabbitMQ trong container và công cụ kiểm thử của Spring AMQP

> **Module:** Spring Boot – testing  
> **Nhóm:** Messaging  
> **Đề bài:** RabbitMQ trong container và công cụ kiểm thử của Spring AMQP  
> **Mục tiêu:** Hiểu rõ các tầng kiểm thử producer, consumer, routing và broker thật; dùng Spring AMQP test utilities và RabbitMQ Testcontainers đúng mục đích; thiết lập ví dụ Java 17, Spring Boot 3.5, Maven với test bất đồng bộ ổn định.

## 1. Bức tranh tổng thể

Một lời gọi `rabbitTemplate.convertAndSend(exchange, routingKey, payload)` có thể chạy không lỗi trong unit test, nhưng chưa chứng minh message đã tới RabbitMQ broker, được route vào queue đúng, chuyển đổi payload thành công hay consumer đã xử lý nghiệp vụ.

```text
Producer
  |
  v
RabbitTemplate --AMQP--> RabbitMQ container
                         |
                      Exchange
                         |
               Routing key + binding
                         |
                        Queue
                         |
                 @RabbitListener container
                         |
                    Handler logic
                         |
                ACK/NACK + side effect
```

Những câu hỏi cần tách:

1. Producer có chọn đúng exchange, routing key và body không?
2. Exchange, queue, binding có tồn tại và đúng cấu hình trên broker không?
3. RabbitMQ có chấp nhận publication và route nó đúng không?
4. Listener container có nhận message, deserialization đúng và gọi đúng handler không?
5. Handler ghi trạng thái nghiệp vụ đúng, dù chạy trên thread khác test không?
6. ACK/NACK, retry, redelivery và DLQ hoạt động theo policy không?
7. CI có Docker daemon, networking, tài nguyên và cách dọn container phù hợp không?

**Mockito tốt để kiểm tra lời gọi; RabbitMQ Testcontainers để kiểm tra hành vi broker.** Hai công cụ không thay thế nhau.

### 1.1. Những khái niệm AMQP quan trọng

| Khái niệm | Vai trò | Điểm dễ sai |
| --- | --- | --- |
| Exchange | Nhận publication và chọn destination | Default exchange khác custom exchange |
| Queue | Chứa deliveries | Durability, auto-delete, queue arguments |
| Binding | Nối exchange tới queue | Routing key không trùng |
| Routing key | Publisher gửi tới exchange | Không phải lúc nào cũng bằng tên queue |
| RabbitTemplate | Gửi/nhận qua AMQP client | Call success chưa chứng minh route |
| RabbitAdmin | Declare broker resources | Có beans chưa chắc đã được declare |
| @RabbitListener | Consumer method | Chạy async, không trong test thread |
| Publisher confirm | Broker chấp nhận publication | Khác consumer ACK |
| Mandatory return | Unroutable publication được trả về | Phải bật returns/mandatory |
| Consumer ACK/NACK | Xác nhận hoặc từ chối delivery | Liên quan requeue/retry |
| DLX/DLQ | Đích nhận dead-lettered messages | Không tự được tạo chỉ vì listener throw |
| Redelivery | Broker gửi lại delivery | Handler cần idempotency |

### 1.2. Direct, topic và fanout exchange

Với direct exchange, binding key trùng chính xác routing key. Ví dụ:

```text
it.events.exchange
  "orders.created" -> it.orders.queue
  "orders.audit"   -> it.audit.queue
```

Topic exchange có patterns như `orders.*`, `orders.#`. Fanout exchange broadcast tới những queues bound, bỏ qua routing key. Một fake `Map` tự viết chưa chắc mô phỏng được các semantics này.

Publisher confirm ACK không chứng minh đã route tới queue. Consumer ACK không chứng minh transaction ở database ngoài broker đã commit. Business success cần assertion riêng.

## 2. Các tầng kiểm thử nên dùng

| Cấp độ | Công cụ | Có RabbitMQ broker? | Điều chứng minh |
| --- | --- | --- | --- |
| Unit producer | JUnit + Mockito RabbitTemplate | Không | Validation, exchange/key/payload args |
| Unit consumer | Gọi method trực tiếp | Không | Xử lý nghiệp vụ của handler |
| Listener wiring | TestRabbitTemplate | Không | Listener được gọi trực tiếp trong context |
| Listener spy/capture | @RabbitListenerTest, RabbitListenerTestHarness | Tùy cách gửi | Argument, return, exception |
| Broker available check | @RabbitAvailable | Dùng broker có sẵn | Broker reachable/queues tùy config |
| Integration routing | RabbitMQ Testcontainers + SpringBootTest | Có | Exchange, queue, bindings, AMQP network |
| Reliability | Broker test + confirms/returns/DLQ | Có | Routing failures, retry và redelivery |
| HA/security/perf | Staging cluster | Có topology thật | TLS/ACL/quorum/failover/load |

Không cần khởi động RabbitMQ trong mọi unit test. Nhưng test có mục tiêu xác nhận exchange routing hoặc ACK mà lại mock broker là sai mức bằng chứng.

## 3. `spring-rabbit-test` và những công cụ chuyên biệt

### 3.1. `@SpringRabbitTest`

`@SpringRabbitTest` giúp cung cấp AMQP infrastructure beans trong một Spring test context, chẳng hạn connection factory, RabbitTemplate, RabbitAdmin và listener factory. Nếu đã dùng `@SpringBootTest` và Spring Boot AMQP auto-configuration, những beans này thông thường đã có sẵn nên không cần thêm `@SpringRabbitTest` chỉ vì muốn autowire RabbitTemplate.

Annotation **không khởi động RabbitMQ broker**.

### 3.2. `TestRabbitTemplate` không gửi qua broker

`org.springframework.amqp.rabbit.test.TestRabbitTemplate` phát hiện listener containers trong Spring context và gọi listener trực tiếp theo **tên queue**, trong test process/thread. Nó hữu ích cho test wiring và một số request/reply scenarios.

Nhưng nó không chứng minh broker exchange/binding, message persistence, mandatory returns, publisher confirms hoặc consumer ACK thật. Ví dụ bean cấu hình **minh họa**, chưa phải project độc lập:

```java
@TestConfiguration
class NoBrokerListenerConfig {
    @Bean
    TestRabbitTemplate testRabbitTemplate(
            ConnectionFactory factory) {
        return new TestRabbitTemplate(factory);
    }
}
```

Cần import `TestConfiguration`, `Bean`, Spring Rabbit `ConnectionFactory`, `TestRabbitTemplate`. Khi test brokerless, cần cấu hình để ordinary listener containers không cố kết nối một broker không tồn tại.

### 3.3. `@RabbitListenerTest` và `RabbitListenerTestHarness`

`@RabbitListenerTest` được dùng trên `@Configuration`/`@TestConfiguration` để tạo listener test harness. Hai mode:

- `spy=true` (mặc định): Mockito spy được gắn với listener.
- `capture=true`: advice ghi nhận invocation arguments, result hoặc exception.

Để harness spy/capture được, listener phải có `@RabbitListener(id="...")`. Listener method `final` không thể được spy/advised.

API hữu ích:

```java
RabbitListenerTestHarness.InvocationData data =
        harness.getNextInvocationDataFor(
                "ordersListener", 10, TimeUnit.SECONDS);

assertThat(data).isNotNull();
assertThat(data.getArguments())
        .containsExactly("order-123");
assertThat(data.getThrowable()).isNull();
```

Đoạn code này cần harness đã autowire và publisher/broker hoặc một test dispatch phù hợp. `getNextInvocationDataFor` có timeout giúp tránh `Thread.sleep`.

### 3.4. `@RabbitAvailable` và availability policy

`@RabbitAvailable` được `RabbitAvailableCondition` xử lý trong JUnit 5. Nó kiểm tra một **broker đã chạy sẵn**:

- `queues`: test queues được declare/purge/delete theo lifecycle.
- `management`: cần management API.
- `purgeAfterEach` mặc định true.
- Khi broker không available, test có thể bị **skip**.
- Biến `RABBITMQ_SERVER_REQUIRED=true` theo tài liệu Spring AMQP cho phép fail khi broker là bắt buộc.

Nếu dùng Testcontainers, thường không cần `@RabbitAvailable` vì JUnit `@Container` tự khởi động broker. Đừng để condition mặc định tìm localhost:5672 khi container publish cổng ngẫu nhiên rồi tưởng broker không hoạt động.

### 3.5. `@LongRunning`

Annotation Spring AMQP giúp chỉ chạy các tests dài khi environment flag phù hợp. Nếu một CI job quảng bá INTEGRATION PASS, hãy kiểm tra test đã thực thi thật, không bị skip do test condition.

## 4. RabbitMQ Testcontainers và Spring Boot

Spring Boot 3.5 hỗ trợ `@ServiceConnection` cho typed `RabbitMQContainer`, cung cấp `RabbitConnectionDetails` phù hợp với mapped AMQP host/port/credentials.

```java
@Testcontainers
@SpringBootTest
class RabbitContainerExample {
    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:4.1.8-management");
}
```

Đây là annotation skeleton; project test đầy đủ ở phần dưới. Spring Boot 3.5 parent quản lý Testcontainers 1.x, nên dùng Java import:

```java
import org.testcontainers.containers.RabbitMQContainer;
```

Với Testcontainers 2.x, artifact/package mới có thể chuyển sang `org.testcontainers:testcontainers-rabbitmq` và `org.testcontainers.rabbitmq.RabbitMQContainer`. Không trộn import của 2.x với dependency do Boot 3.5 quản lý khi chưa nâng BOM đồng bộ.

**Không hard-code localhost:5672.** Docker map container port 5672 sang một host port động. Management HTTP port 15672 riêng biệt, không phải AMQP port. Chỉ cần management UI/API khi test thực sự cần nó. Chọn image version gần production hoặc pin digest theo policy, đừng dùng `latest` tùy tiện.

### 4.1. `@ServiceConnection` so với `@DynamicPropertySource`

Khi không dùng service connection, có thể cấu hình dynamic properties:

```java
@DynamicPropertySource
static void rabbitProps(DynamicPropertyRegistry registry) {
    registry.add("spring.rabbitmq.host", rabbit::getHost);
    registry.add("spring.rabbitmq.port", rabbit::getAmqpPort);
    registry.add("spring.rabbitmq.username", rabbit::getAdminUsername);
    registry.add("spring.rabbitmq.password", rabbit::getAdminPassword);
}
```

Đoạn này cần một static container và imports từ `org.springframework.test.context`. Thông thường chọn một cách lấy connection details, tránh cấu hình chồng chéo.

### 4.2. Context cache và container lifecycle

JUnit static `@Container` có thể stop sau class nhưng Spring ApplicationContext vẫn nằm trong cache và được test class khác tái dùng. Khi đó RabbitTemplate có thể giữ connection factory tới container đã dừng. Với class-scoped container, dùng `@DirtiesContext(AFTER_CLASS)` có chủ đích; với suite cần share context, cân nhắc Spring-managed container bean sống cùng context.

`@DirtiesContext` quản lý Spring context, **không phải** lệnh purge RabbitMQ queues hay Docker resources.

## 5. Dự án Maven hoàn chỉnh — Java 17 và Spring Boot 3.5

Dự án demo có publisher, consumer, direct exchange, hai queues, observation sink bất đồng bộ. Test gồm 2 unit publisher, 1 unit consumer, 2 broker integration và 1 harness integration: **6 phương thức JUnit `@Test`**.

### 5.1. Cấu trúc

```text
rabbit-messaging-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/rabbitlab/
    │   ├── RabbitLabApplication.java
    │   ├── RabbitTopology.java
    │   ├── OrderPublisher.java
    │   ├── OrderConsumer.java
    │   └── ProcessedMessages.java
    └── test/java/com/example/rabbitlab/
        ├── OrderPublisherUnitTest.java
        ├── OrderConsumerUnitTest.java
        ├── RabbitBrokerIntegrationTest.java
        └── RabbitHarnessIntegrationTest.java
```

Tất cả Java files cùng package `com.example.rabbitlab`, public class có file trùng tên.

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>rabbit-messaging-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-amqp</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.amqp</groupId>
            <artifactId>spring-rabbit-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-testcontainers</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>rabbitmq</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Boot BOM quản lý Spring AMQP/Testcontainers/JUnit compatible versions. `spring-rabbit-test` thêm harness helpers; `spring-boot-testcontainers` thêm Spring service connections; `rabbitmq` Testcontainers module chạy broker.

### 5.3. `RabbitLabApplication.java`

```java
// src/main/java/com/example/rabbitlab/RabbitLabApplication.java
package com.example.rabbitlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RabbitLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(RabbitLabApplication.class, args);
    }
}
```

### 5.4. `RabbitTopology.java`

```java
// src/main/java/com/example/rabbitlab/RabbitTopology.java
package com.example.rabbitlab;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RabbitTopology {

    public static final String EXCHANGE = "it.events.exchange";
    public static final String ORDERS_QUEUE = "it.orders.queue";
    public static final String AUDIT_QUEUE = "it.audit.queue";
    public static final String ORDER_KEY = "orders.created";
    public static final String AUDIT_KEY = "orders.audit";

    @Bean
    DirectExchange eventsExchange() {
        return new DirectExchange(EXCHANGE, false, false);
    }

    @Bean
    Queue ordersQueue() {
        return new Queue(ORDERS_QUEUE, false);
    }

    @Bean
    Queue auditQueue() {
        return new Queue(AUDIT_QUEUE, false);
    }

    @Bean
    Binding orderBinding(
            @Qualifier("ordersQueue") Queue q,
            DirectExchange exchange) {
        return BindingBuilder.bind(q).to(exchange)
                .with(ORDER_KEY);
    }

    @Bean
    Binding auditBinding(
            @Qualifier("auditQueue") Queue q,
            DirectExchange exchange) {
        return BindingBuilder.bind(q).to(exchange)
                .with(AUDIT_KEY);
    }
}
```

Hai queues dùng `durable=false` chỉ cho **broker test ephemeral**, không phải durability policy production. `@Qualifier` phân biệt hai Queue beans. Spring RabbitAdmin khi auto-declare được bật sẽ tạo queue/exchange/binding trên broker khi connection sẵn sàng. Nếu tắt declaration hoặc queue name đã tồn tại với khác arguments, có thể xảy ra `NOT_FOUND`/`PRECONDITION_FAILED`.

### 5.5. `ProcessedMessages.java`

```java
// src/main/java/com/example/rabbitlab/ProcessedMessages.java
package com.example.rabbitlab;

import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class ProcessedMessages {

    private final BlockingQueue<String> values =
            new LinkedBlockingQueue<>();

    public void add(String value) {
        values.add(value);
    }

    public String await(Duration timeout)
            throws InterruptedException {
        return values.poll(
                timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public void clear() {
        values.clear();
    }
}
```

`BlockingQueue` giúp test thread chờ observation do listener thread tạo, không dùng fixed sleep. Đây là state trong JVM; ứng dụng thật nên assert business side effect trong DB test-only hoặc downstream service.

### 5.6. `OrderPublisher.java`

```java
// src/main/java/com/example/rabbitlab/OrderPublisher.java
package com.example.rabbitlab;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final RabbitTemplate template;

    public OrderPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void publish(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }

        template.convertAndSend(
                RabbitTopology.EXCHANGE,
                RabbitTopology.ORDER_KEY,
                orderId);
    }
}
```

Dùng String giúp tập trung vào routing. Với JSON events thực, producer/consumer phải dùng converter phù hợp và nên có schema version/compatibility tests.

### 5.7. `OrderConsumer.java`

```java
// src/main/java/com/example/rabbitlab/OrderConsumer.java
package com.example.rabbitlab;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    private final ProcessedMessages processed;

    public OrderConsumer(ProcessedMessages processed) {
        this.processed = processed;
    }

    @RabbitListener(
            id = "ordersListener",
            queues = RabbitTopology.ORDERS_QUEUE)
    public void receive(String orderId) {
        processed.add(orderId);
    }
}
```

Listener method public, non-final và có stable id `ordersListener` nên harness có thể capture. SimpleMessageConverter mặc định hỗ trợ String body. Trong mode AUTO, container ACK theo lifecycle sau handler return; test quan sát `ProcessedMessages` không trực tiếp chứng minh AMQP ACK frame đã được gửi.

## 6. Unit tests không cần Docker

### 6.1. `OrderPublisherUnitTest.java`

```java
// src/test/java/com/example/rabbitlab/OrderPublisherUnitTest.java
package com.example.rabbitlab;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class OrderPublisherUnitTest {

    @Test
    void sendsToExpectedExchangeAndKey() {
        RabbitTemplate template = mock(RabbitTemplate.class);
        OrderPublisher publisher = new OrderPublisher(template);

        publisher.publish("order-123");

        verify(template).convertAndSend(
                RabbitTopology.EXCHANGE,
                RabbitTopology.ORDER_KEY,
                "order-123");
    }

    @Test
    void rejectsBlankPayloadWithoutSending() {
        RabbitTemplate template = mock(RabbitTemplate.class);
        OrderPublisher publisher = new OrderPublisher(template);

        assertThatThrownBy(() -> publisher.publish(" "))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("orderId must not be blank");

        verifyNoInteractions(template);
    }
}
```

Hai tests chứng minh Java validation/interaction, không chứng minh broker có queue/binding.

### 6.2. `OrderConsumerUnitTest.java`

```java
// src/test/java/com/example/rabbitlab/OrderConsumerUnitTest.java
package com.example.rabbitlab;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class OrderConsumerUnitTest {

    @Test
    void directlyHandlesPayload() throws Exception {
        ProcessedMessages sink = new ProcessedMessages();
        OrderConsumer listener = new OrderConsumer(sink);

        listener.receive("order-321");

        assertThat(sink.await(Duration.ofMillis(100)))
                .isEqualTo("order-321");
    }
}
```

Test này gọi handler trực tiếp, không dùng Spring listener container hay AMQP network.

## 7. RabbitMQ Testcontainers integration test

### 7.1. `RabbitBrokerIntegrationTest.java`

```java
// src/test/java/com/example/rabbitlab/RabbitBrokerIntegrationTest.java
package com.example.rabbitlab;

import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.test.annotation.DirtiesContext;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class RabbitBrokerIntegrationTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:4.1.8-management");

    @Autowired
    OrderPublisher publisher;

    @Autowired
    RabbitTemplate template;

    @Autowired
    ProcessedMessages processed;

    @BeforeEach
    void clearState() {
        processed.clear();
    }

    @Test
    void messageTravelsThroughBrokerToListener()
            throws Exception {
        String value = "order-" + UUID.randomUUID();

        publisher.publish(value);

        assertThat(processed.await(Duration.ofSeconds(10)))
                .isEqualTo(value);
    }

    @Test
    void auditKeyRoutesToAuditQueue() {
        String value = "audit-" + UUID.randomUUID();

        template.convertAndSend(
                RabbitTopology.EXCHANGE,
                RabbitTopology.AUDIT_KEY,
                value);

        Object received = template.receiveAndConvert(
                RabbitTopology.AUDIT_QUEUE, 5_000);

        assertThat(received).isEqualTo(value);
    }
}
```

Test đầu đi qua publisher → real broker → direct exchange/binding/queue → listener container → observed side effect. Test thứ hai đi qua audit binding rồi dùng RabbitTemplate nhận trực tiếp từ audit queue không có listener. Không dùng một queue depth assertion ngắn hạn vì active listener có thể consume trước khi test đo.

### 7.2. Một test topology tùy chọn

Nếu cần xác minh queue đã declare qua broker, thêm một test nhận `RabbitTemplate` và gọi passive declaration (minh họa, không thuộc 6 methods đã đếm):

```java
Integer count = template.execute(channel ->
        channel.queueDeclarePassive(
                RabbitTopology.ORDERS_QUEUE)
                .getMessageCount());

assertThat(count).isNotNull();
assertThat(count).isGreaterThanOrEqualTo(0);
```

AMQP passive declaration thất bại khi queue không có. Nó kiểm tra broker resource thật, không chỉ Java bean.

## 8. `RabbitListenerTestHarness` với broker thật

### 8.1. `RabbitHarnessIntegrationTest.java`

```java
// src/test/java/com/example/rabbitlab/RabbitHarnessIntegrationTest.java
package com.example.rabbitlab;

import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.test.RabbitListenerTest;
import org.springframework.amqp.rabbit.test.RabbitListenerTestHarness;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.DirtiesContext;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
@Import(RabbitHarnessIntegrationTest.HarnessConfig.class)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class RabbitHarnessIntegrationTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:4.1.8-management");

    @Autowired
    OrderPublisher publisher;

    @Autowired
    RabbitListenerTestHarness harness;

    @Test
    void capturesListenerInvocation() throws Exception {
        String value = "harness-" + UUID.randomUUID();

        publisher.publish(value);

        RabbitListenerTestHarness.InvocationData call =
                harness.getNextInvocationDataFor(
                        "ordersListener", 10, TimeUnit.SECONDS);

        assertThat(call).isNotNull();
        assertThat(call.getArguments())
                .containsExactly(value);
        assertThat(call.getThrowable()).isNull();
    }

    @TestConfiguration(proxyBeanMethods = false)
    @RabbitListenerTest(spy = false, capture = true)
    static class HarnessConfig {
    }
}
```

`@Import(HarnessConfig.class)` đưa annotation test vào đúng Spring context. `spy=false,capture=true` bật advice capture invocation. ID phải trùng với listener `ordersListener`. Bounded wait 10s giúp không dùng sleep cố định. Harness capture arguments/exception nhưng không tự xác nhận ACK frame hoặc commit của transaction ngoài broker.

### 8.2. Spy/latch là lựa chọn khác

Có thể dùng `@RabbitListenerTest(spy=true,capture=false)`, lấy `harness.getSpy("ordersListener")`, rồi Mockito verify với Awaitility hoặc harness latch answer. Listener method không được final. Đây là hướng mở rộng, không nằm trong project mẫu đã đếm.

## 9. Chạy Maven và dự kiến kết quả

```bash
java -version
mvn -version

# 3 unit tests không cần Docker:
mvn -B -ntp -Dtest=OrderPublisherUnitTest,OrderConsumerUnitTest test

# 3 integration tests cần RabbitMQ container:
docker info
mvn -B -ntp -Dtest=RabbitBrokerIntegrationTest,RabbitHarnessIntegrationTest test

# Toàn bộ:
mvn -B -ntp test
```

Theo source, project có **6 JUnit test methods**: 3 unit, 2 broker integration, 1 harness integration. Đây là expected structure, **không phải log thực tế đã chạy**. Maven cần tải dependencies nếu cache chưa có; Testcontainers cần Docker runtime/image registry và có thể pull RabbitMQ image lần đầu.

## 10. Reliability: confirm, return, ACK, retry, DLQ

### 10.1. Publisher confirms và returns

Spring Boot có thể cấu hình:

```properties
spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true
```

Ba properties này **chưa tự tạo một test**. Kiểm thử thực phải gửi message có routing key đúng rồi đợi correlated confirm, sau đó gửi key không có binding và đợi return callback. Kiểm tra routing key, exchange, return code/body/correlation id; không chỉ assert `convertAndSend` không throw.

Broker confirm ACK và consumer ACK khác nhau. Confirm có thể báo broker accept publication nhưng chưa bảo đảm queue routing hoặc handler success.

### 10.2. ACK modes

`AUTO` thường cho container ACK sau successful listener method, `MANUAL` yêu cầu application xử lý `basicAck`/`basicNack`/`basicReject`, `NONE` thường là automatic acknowledgement ở broker; không diễn giải NONE thành “không bao giờ ACK”.

Khi handler throw, retry/requeue phụ thuộc listener container/error handler policy. Một poison message có thể redeliver mãi nếu không giới hạn retry.

### 10.3. DLQ cần cả topology

Ví dụ property:

```properties
spring.rabbitmq.listener.simple.default-requeue-rejected=false
```

Nó **không tự tạo dead-letter exchange/queue**. Muốn test DLQ:

1. Khai source queue với DLX/routing policy, tạo DLQ và binding đúng.
2. Gửi một payload lỗi với correlation id riêng.
3. Bật retry hữu hạn và xác nhận cuối cùng message vào DLQ.
4. Đọc DLQ với bounded timeout, assert body/headers/reason theo contract.
5. Kiểm tra không có business effect sai hoặc duplicate.
6. Cleanup chỉ broker/queue thuộc test run.

Không để test poison event tạo infinite requeue loop.

### 10.4. Idempotency

Consumer có thể cập nhật database xong nhưng crash trước ACK; RabbitMQ redeliver và handler xử lý lại. Một Spring DB transaction và RabbitMQ ACK không mặc nhiên là atomic distributed transaction. Với nghiệp vụ nhạy cảm cần event id, inbox/outbox hoặc deduplication, và test redelivery trên DB test-only.

Không tuyên bố exactly-once chỉ vì một message được xử lý một lần trong broker sạch.

## 11. Test bất đồng bộ ổn định và CI

### 11.1. Bounded wait thay fixed sleep

```java
publisher.publish("order-1");
assertThat(processed.await(Duration.ofSeconds(10)))
        .isEqualTo("order-1");
```

Ví dụ này dựa trên test context có `processed` và throws Exception. Bounded poll trả sớm khi message đến, fail khi timeout. Fixed `Thread.sleep(5000)` dễ flaky và lãng phí thời gian. Với side effects qua database, dùng Awaitility và assert database state có thời gian chờ giới hạn.

### 11.2. Test isolation

- Mỗi test group nên có container/vhost/queue namespace riêng.
- Dùng event ID/UUID tránh trùng fixtures.
- Không purge queues của shared dev/production broker.
- `ProcessedMessages.clear()` phù hợp cho test methods tuần tự; nếu bật parallel phải tách state theo event id.
- Listener thread không tự chia sẻ transaction của JUnit test thread.
- Context cache và container lifecycle phải đồng bộ; `@DirtiesContext` trong mẫu tránh tái dùng context trỏ broker đã dừng.
- Đừng bật Testcontainers reusable containers trên mandatory CI nếu muốn broker sạch theo job.

### 11.3. GitHub Actions minh họa

```yaml
name: RabbitMQ testing
on: [push, pull_request]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Check Docker
        run: |
          docker version
          docker info --format 'Engine={{.ServerVersion}}'
      - name: Run tests
        run: mvn -B -ntp test
      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: surefire
          path: target/surefire-reports/
          if-no-files-found: ignore
```

Job cần Docker-compatible daemon, quyền tạo containers, pull image, CPU/RAM/disk đủ cho RabbitMQ Erlang VM và JVM. `@ServiceConnection` lấy mapped host/AMQP port, không hard-code `localhost:5672`. Trên Docker executor, Maven container và Docker host có networking khác; cần cấu hình `DOCKER_HOST`/host override đúng topology.

Không mount rootful docker.sock của shared host vào untrusted PR job. Không tắt Ryuk vô điều kiện hoặc dùng global Docker prune trên daemon có workloads khác. CI mandatory integration không dùng `mvn test || true` và không silently skip tests khi thiếu runtime.

## 12. Troubleshooting thường gặp

| Triệu chứng | Khả năng | Hành động |
| --- | --- | --- |
| Docker environment không tìm thấy | Không có daemon/socket | Kiểm tra Docker API và quyền |
| RabbitMQ image không pull | Registry/network/tag | Image pin/auth/proxy |
| Connection refused localhost:5672 | Mapped port khác | @ServiceConnection, Docker networking |
| `NOT_FOUND - no queue` | RabbitAdmin chưa declare | Queue beans, dynamic declaration |
| `PRECONDITION_FAILED inequivalent arg` | Queue flags khác | Fresh test broker, topology consistency |
| `MessageConversionException` | Content type/converter sai | Test serialization end-to-end |
| Listener timeout | Binding/key/consumer không đúng | RabbitMQ/Spring listener logs |
| Harness không capture | Thiếu config/id hoặc final method | Import @RabbitListenerTest, id ổn định |
| Publisher call success nhưng event mất | Unroutable key | Confirms/mandatory returns |
| Handler throw liên tục | Retry/requeue loop | Bounded retry và DLQ |
| Queue trống nhưng nghiệp vụ chưa xong | Delivered/unacked | Assert business outcome |
| Suite fail từ class thứ hai | Context reused stopped container | Context-managed lifecycle hoặc DirtiesContext |
| CI OOM/exit 137 | Runner quá tải | CPU/RAM/disk/parallelism |

## 13. Bài tập và câu hỏi tự kiểm tra

**Bài tập 1.** Chạy unit publisher trước rồi broker integration; giải thích vì sao mock không chứng minh binding thật.

**Bài tập 2.** Cố ý gửi key không tồn tại; thiết kế test mandatory returned message và so với publisher confirms.

**Bài tập 3.** Chuyển String event sang DTO JSON có eventId/schemaVersion; kiểm tra converter producer/consumer qua RabbitMQ thật.

**Bài tập 4.** Tạo dead-letter exchange/queue và một poison event; kiểm tra không requeue vô hạn.

**Bài tập 5.** Tạo test consumer idempotency với database test-only và mô phỏng redelivery.

**Câu 1.** Mockito verify RabbitTemplate có chứng minh RabbitMQ nhận message? **Không.**

**Câu 2.** TestRabbitTemplate có dùng exchange routing thật? **Không**, nó gọi listener trực tiếp.

**Câu 3.** @RabbitAvailable có tự start Docker container không? **Không**, nó kiểm tra broker có sẵn.

**Câu 4.** Harness muốn capture listener cần gì? **Listener id và method không final**.

**Câu 5.** Publisher confirm ACK có tương đương consumer ACK không? **Không.**

**Câu 6.** Queue depth bằng 0 có bảo đảm DB commit? **Không.**

**Câu 7.** Tại sao dùng bounded waits? **Để xử lý async timing thay vì fixed sleep.**

**Câu 8.** Docker không có nhưng CI skip broker tests có phải integration PASS? **Không.**

## 14. Checklist QA

- [ ] Xác định đúng unit/consumer/listener-wiring/harness/broker test level.
- [ ] Có `spring-rabbit-test` khi dùng test utilities.
- [ ] Không nhầm TestRabbitTemplate với RabbitMQ thật.
- [ ] Broker container image/version phù hợp, không hard-code host port.
- [ ] Exchange/queue/binding được declare với tên/flags đúng.
- [ ] @ServiceConnection cấp Rabbit connection details.
- [ ] Listener có ID và non-final khi dùng harness.
- [ ] Asynchronous waits bounded, không fixed sleeps.
- [ ] Assert handler outcome, không chỉ queue depth.
- [ ] Phân biệt publisher confirm, mandatory returns và consumer ACK.
- [ ] Retry/DLQ policy có giới hạn, tránh poison loop.
- [ ] Handler idempotent nếu có thể redeliver.
- [ ] Test isolation/cleanup không chạm broker production.
- [ ] Spring TestContext cache khớp Testcontainers lifecycle.
- [ ] CI có Docker/API quyền/tài nguyên phù hợp, không silently skip mandatory tests.

## 15. Tài liệu chính thức

- [Spring AMQP Testing Support](https://docs.spring.io/spring-amqp/reference/testing.html): SpringRabbitTest, TestRabbitTemplate, RabbitListenerTest, RabbitAvailable.
- [RabbitListenerTestHarness 3.2 API](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/test/RabbitListenerTestHarness.html): spy/capture/latch.
- [InvocationData 3.2 API](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/test/RabbitListenerTestHarness.InvocationData.html): invocation arguments, result, throwable.
- [Spring Boot 3.5 Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): RabbitMQContainer/RabbitConnectionDetails.
- [Testcontainers RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/): Java dependencies và container API.
- [Testcontainers JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): Container lifecycle.
- [RabbitMQ Publisher Confirms and Consumer Acknowledgements](https://www.rabbitmq.com/docs/confirms): các loại xác nhận.
- [RabbitMQ Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): DLX/DLQ behavior.
- [RabbitMQ Official Docker Image](https://hub.docker.com/_/rabbitmq): version và management image.

**Kết luận:** Kiểm thử RabbitMQ chính xác phải tách lời gọi publisher, broker routing, listener invocation, ACK/recovery và business effect. Mockito giữ unit tests nhanh; Spring AMQP helpers hỗ trợ listener wiring/capture; RabbitMQ Testcontainers kiểm chứng broker thật. Tránh kết luận delivery guaranteed từ một `convertAndSend` không throw hoặc một test mock xanh.