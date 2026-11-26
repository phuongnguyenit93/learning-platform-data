# spring-rabbit-test, @SpringRabbitTest và @RabbitListenerTest

Trong ứng dụng sử dụng **Spring AMQP**, việc kiểm thử message không giống kiểm thử một hàm đồng bộ thông thường. Producer có thể publish bằng `RabbitTemplate` rồi trả về trước khi `@RabbitListener` được gọi; broker còn phải định tuyến qua exchange, queue và binding; consumer có thể ACK, NACK, retry, dead-letter hoặc nhận lại message khi mất kết nối. Một bài test chỉ kiểm tra method của listener được gọi chưa đủ để kết luận hệ thống xử lý bất đồng bộ đáng tin cậy.

Thư viện **`spring-rabbit-test`** hỗ trợ nhiều mức kiểm thử: dựng hạ tầng Spring Rabbit gọn nhẹ bằng **`@SpringRabbitTest`**, theo dõi listener qua Mockito spy và invocation capture bằng **`@RabbitListenerTest`**, kiểm thử trực tiếp không cần broker với **`TestRabbitTemplate`**, hoặc kiểm thử tích hợp có broker thật nhờ **`@RabbitAvailable`** và các công cụ như Testcontainers.

Bài học nằm trong chương **Kiểm thử** của module **SPRING_AMQP**. Mục tiêu là hiểu chức năng và giới hạn của từng công cụ, xây ví dụ JUnit 5 kiểm chứng `@RabbitListener`, và biết khi nào bắt buộc chạy test có RabbitMQ thật để xác nhận routing, confirms, ACK/NACK, retry, dead-letter, transaction và recovery.

## 1. Chọn tầng kiểm thử trước khi chọn annotation

| Tầng kiểm thử | Chạy RabbitMQ thật? | Thành phần chính | Kiểm chứng được | Không chứng minh được |
|---|---|---|---|---|
| **Unit test** | Không | JUnit 5, Mockito, service/listener class | Validation, mapping, branching, exception và gọi dependency | Listener container, routing, ACK/NACK hay broker recovery |
| **Listener test không broker** | Không | `TestRabbitTemplate`, test context, listener beans | Adapter gọi listener, chuyển đổi payload và trả reply ở mức mô phỏng | Exchange routing, delivery thật, quorum/TTL/DLX và network |
| **Listener instrumentation** | Tùy cách dựng context | `@RabbitListenerTest` + `RabbitListenerTestHarness` | Spy, invocation arguments, result/exception, chờ callback async | Không tự có broker; không thay test end-to-end |
| **Spring Rabbit test context** | Chỉ cần nếu test thực sự kết nối | `@SpringRabbitTest` | Cung cấp `ConnectionFactory`, `RabbitTemplate`, `RabbitAdmin`, factory listener | Không tự dựng RabbitMQ broker |
| **Integration test** | **Có** | `@RabbitAvailable`, RabbitMQ Testcontainers hoặc môi trường CI riêng | Exchange/queue/binding, ACK/NACK, DLX, redelivery, publisher confirms | Không tự đại diện cho toàn bộ mạng và cluster production |
| **Fault/chaos test** | **Có** | Proxy mạng, stop/restart broker, container | Đứt kết nối, outcome chưa rõ, duplicate và khôi phục | Không bảo đảm mọi lịch chạy của hệ thống đã được bao phủ |

**Một annotation không thay thế được toàn bộ test pyramid.** `@SpringRabbitTest` giúp có Spring beans; `@RabbitListenerTest` giúp quan sát listener; chỉ khi thêm broker thực tế thì bạn mới kiểm chứng được hành vi RabbitMQ ở mức giao thức.

~~~mermaid
flowchart TB
    UNIT["Unit test: business rules"] --> MOCK["Listener adapter: TestRabbitTemplate"]
    MOCK --> HAR["Harness: spy + capture"]
    HAR --> INT["RabbitMQ integration: routing + ACK/DLX"]
    INT --> FAULT["Fault injection: reconnect + duplicate"]
~~~

Mỗi tầng nên có mục tiêu, tốc độ chạy và nguồn lỗi riêng. Unit test chạy thường xuyên; integration test kiểm tra hợp đồng giao tiếp; fault test bảo vệ những ranh giới khó tái hiện.

## 2. Cài dependency spring-rabbit-test

Thêm test dependency tương ứng với phiên bản Spring AMQP đang dùng. Nếu dự án dùng Spring Boot, thường nên để BOM quản lý phiên bản thay vì chọn riêng một version không tương thích.

### Maven

~~~xml
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
</dependencies>
~~~

### Gradle

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-amqp'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.amqp:spring-rabbit-test'
~~~

`spring-rabbit-test` cung cấp các utility dành cho **RabbitMQ listener với Spring AMQP**, không nên đưa vào runtime dependency của production nếu chỉ cần cho test. Mockito/JUnit 5 có thể được cung cấp bởi `spring-boot-starter-test`; khi dùng Spring Framework thuần, phải bổ sung chúng và cấu hình test engine thích hợp.

### Phân biệt package/import

| API | Package cần nhận biết | Vai trò |
|---|---|---|
| `@SpringRabbitTest` | `org.springframework.amqp.rabbit.test.context.SpringRabbitTest` | Thêm infrastructure beans vào Spring test context |
| `@RabbitListenerTest` | `org.springframework.amqp.rabbit.test.RabbitListenerTest` | Kích hoạt spy/capture listener |
| `RabbitListenerTestHarness` | `org.springframework.amqp.rabbit.test.RabbitListenerTestHarness` | Lấy spy, delegate và invocation data |
| `TestRabbitTemplate` | `org.springframework.amqp.rabbit.test.TestRabbitTemplate` | Gọi listener trực tiếp, không qua broker |
| `@RabbitAvailable` | `org.springframework.amqp.rabbit.junit.RabbitAvailable` | Điều kiện JUnit 5: chỉ chạy integration test khi broker có sẵn |

**Lưu ý về JUnit:** `@RabbitAvailable` được xử lý bởi `RabbitAvailableCondition` qua JUnit Jupiter (`@ExtendWith`), dù package chứa từ `junit` chứ không phải `junit.jupiter`. Đừng nhầm với JUnit 4 `@Rule` `BrokerRunning` trong tài liệu cũ; kiểm tra Javadoc của đúng nhánh Spring AMQP mà dự án đang dùng.

## 3. @SpringRabbitTest: test context tối thiểu cho RabbitMQ

`@SpringRabbitTest` (xuất hiện từ Spring AMQP **2.3**) dùng khi bạn muốn test qua **Spring TestContext** mà **không cần bật cả ứng dụng Spring Boot**. Annotation này thêm các bean hạ tầng:

| Bean được cung cấp | Tên bean thông thường | Chức năng |
|---|---|---|
| `CachingConnectionFactory` | `autoConnectionFactory` | Connection/channel caching phục vụ test |
| `RabbitTemplate` | `autoRabbitTemplate` | Producer và request/reply API |
| `RabbitAdmin` | `autoRabbitAdmin` | Khai báo topology RabbitMQ |
| `RabbitListenerContainerFactory` | `autoContainerFactory` | Tạo listener container |
| Hạ tầng `@EnableRabbit` | Các bean xử lý `@RabbitListener` | Phát hiện listener, đăng ký container |

Các bean này **không tạo một RabbitMQ broker trong JVM**. Lúc ứng dụng bắt đầu kết nối, broker phải có sẵn. Khi có `@RabbitAvailable`, connection factory của bài test có thể tận dụng cấu hình broker mà condition cung cấp.

### 3.1. Ví dụ JUnit 5 kiểm tra hạ tầng

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.rabbit.listener.RabbitListenerEndpointRegistry;
import org.springframework.amqp.rabbit.test.context.SpringRabbitTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(SpringRabbitInfrastructureTest.Config.class)
@SpringRabbitTest
class SpringRabbitInfrastructureTest {

    @Autowired RabbitTemplate template;
    @Autowired RabbitAdmin admin;
    @Autowired RabbitListenerEndpointRegistry registry;

    @Test
    void infrastructureBeansAreAvailable() {
        assertNotNull(template);
        assertNotNull(admin);
        assertNotNull(registry);
    }

    @Configuration
    static class Config {
        // Thêm bean listener, exchange/queue/binding nếu bài test cần.
    }
}
~~~

Test ở ví dụ trên chỉ xác minh **bean wiring**, chưa gửi message qua broker. Muốn kiểm tra routing/consume, cần khai báo topology, listener và một RabbitMQ thật. Đừng đánh đồng “test context khởi tạo thành công” với “broker đã hoạt động”.

### 3.2. Khi nào không dùng @SpringRabbitTest?

Trong `@SpringBootTest`, Spring Boot AMQP auto-configuration đã tạo hạ tầng RabbitMQ theo các property của ứng dụng. Tài liệu của `@SpringRabbitTest` **không khuyến khích** dùng annotation này cùng Spring Boot test để tránh hai cơ chế tạo bean chồng nhau. Với Boot test, sử dụng `@SpringBootTest` (hoặc context slice được thiết kế tường minh) và bổ sung `@RabbitListenerTest` khi cần instrumentation.

Có thể cấu hình container type cho `@SpringRabbitTest` bằng thuộc tính `containerType`; tuy nhiên **đổi SMLC/DMLC** không tự biến unit test thành integration test và không bảo đảm cùng semantics batching, transaction hoặc ACK.

## 4. @RabbitListenerTest: gắn spy và capture vào listener

`@RabbitListenerTest` đặt trên một class `@Configuration` để thay thế bộ xử lý `@RabbitListener` bình thường bằng **`RabbitListenerTestHarness`**. Nó đồng thời bật phát hiện `@RabbitListener` như `@EnableRabbit`. Khi test context được tạo, harness có thể:

1. **Spy:** bọc listener bằng **Mockito spy**, cho phép `verify(...)` hoặc cài `Answer` mà vẫn gọi method thật khi phù hợp.
2. **Capture:** ghi lại arguments, result và Throwable của mỗi lời gọi listener; test có thể chờ dữ liệu thay vì tự dùng `Thread.sleep`.

Hai lựa chọn được điều khiển độc lập:

~~~java
@Configuration
@RabbitListenerTest(spy = true, capture = true)
class ListenerHarnessConfiguration {
    // @Bean của các listener cần quan sát.
}
~~~

Mặc định của `@RabbitListenerTest` là **`spy=true`, `capture=false`**. Nếu chỉ cần ghi InvocationData mà không muốn Mockito spy, dùng `@RabbitListenerTest(spy=false, capture=true)`.

**Giới hạn cần ghi nhớ:** listener muốn spy/capture phải có **`id` tường minh** trong `@RabbitListener`; method listener **`final`** không thể được spy/advised theo cơ chế này. Proxy AOP, method overload, factory và lifecycle phức tạp cũng là những trường hợp nên xác minh trong integration test thay vì giả định Mockito nhìn thấy đúng method.

## 5. Thực hành với RabbitListenerTestHarness: chờ callback thay vì sleep

Giả sử ứng dụng cần kiểm tra consumer nhận một lệnh từ queue `tests.order.created`. Ta viết một bài integration test ngắn với **`@SpringJUnitConfig`**, **`@SpringRabbitTest`**, **`@RabbitAvailable`** và **`@RabbitListenerTest`**.

### 5.1. Listener có id và method không final

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;

public class OrderCreatedListener {
    @RabbitListener(
            id = "orderCreatedListener",
            queues = "tests.order.created",
            containerFactory = "autoContainerFactory")
    public void handle(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        // Bài test đơn giản: logic nghiệp vụ thực tế có thể gọi service riêng.
    }
}
~~~

`containerFactory = "autoContainerFactory"` tham chiếu factory do `@SpringRabbitTest` tạo, **không phải tên factory mặc định của một ứng dụng Spring Boot đầy đủ**. Trong dự án Boot, thường dùng `rabbitListenerContainerFactory` hoặc tên bean factory thực tế của ứng dụng.

### 5.2. Test với spy và capture

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.verify;

import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.rabbit.junit.RabbitAvailable;
import org.springframework.amqp.rabbit.test.RabbitListenerTest;
import org.springframework.amqp.rabbit.test.RabbitListenerTestHarness;
import org.springframework.amqp.rabbit.test.context.SpringRabbitTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@RabbitAvailable(queues = "tests.order.created")
@SpringJUnitConfig(OrderListenerIntegrationTest.Config.class)
@SpringRabbitTest
class OrderListenerIntegrationTest {

    @Autowired
    RabbitTemplate rabbitTemplate;

    @Autowired
    RabbitListenerTestHarness harness;

    @Test
    void shouldCaptureListenerInvocation() throws Exception {
        rabbitTemplate.convertAndSend("tests.order.created", "order-42");

        RabbitListenerTestHarness.InvocationData data =
                harness.getNextInvocationDataFor(
                        "orderCreatedListener", 10, TimeUnit.SECONDS);

        assertNotNull(data, "Listener không được gọi trong 10 giây");
        assertEquals("order-42", data.getArguments()[0]);
        assertNull(data.getThrowable());

        OrderCreatedListener spy = harness.getSpy("orderCreatedListener");
        assertNotNull(spy);
        verify(spy).handle("order-42");
    }

    @Configuration
    @RabbitListenerTest(spy = true, capture = true)
    static class Config {
        @Bean
        OrderCreatedListener orderCreatedListener() {
            return new OrderCreatedListener();
        }
    }
}
~~~

Ví dụ này có **broker thật**, mặc định local theo điều kiện `@RabbitAvailable` trừ khi cấu hình địa chỉ thử nghiệm khác. Annotation `@RabbitAvailable(queues=...)` tạo và chuẩn bị queue trước test, mặc định **purge giữa các test** và dọn queue sau khi kết thúc suite tương ứng; không dùng với broker/vhost chứa dữ liệu production.

**Vì sao dùng `getNextInvocationDataFor`?** RabbitMQ listener chạy trên consumer thread. Nếu viết:

~~~java
rabbitTemplate.convertAndSend("tests.order.created", "order-42");
verify(spy).handle("order-42");  // Có thể chạy trước listener!
~~~

test dễ bị *flaky*: `convertAndSend` chỉ gửi message, không chờ consumer xử lý. `getNextInvocationDataFor(id, 10, SECONDS)` chờ invocation có giới hạn, khiến test xác nhận đúng một sự kiện quan sát được mà không cần `Thread.sleep(2000)` tùy ý.

### 5.3. Capture lỗi và kết quả trả về

`InvocationData` chứa:

| Phương thức | Nội dung | Cách dùng |
|---|---|---|
| `getArguments()` | Arguments truyền vào listener method | Kiểm tra payload, header hoặc đối tượng đã convert |
| `getResult()` | Giá trị listener method trả về (nếu có) | Kiểm tra request/reply hoặc kết quả method |
| `getThrowable()` | Exception phát sinh trong method được theo dõi | Kiểm tra đường validation/error |

Ví dụ sau gửi payload rỗng để listener ném exception:

~~~java
rabbitTemplate.convertAndSend("tests.order.created", "");

RabbitListenerTestHarness.InvocationData data =
        harness.getNextInvocationDataFor(
                "orderCreatedListener", 10, TimeUnit.SECONDS);

assertNotNull(data);
assertNotNull(data.getThrowable());
~~~

**Cảnh báo:** khi listener ném exception, container có thể mặc định requeue; điều đó khiến cùng một payload được gọi nhiều lần và test capture liên tiếp các invocation. Khi kiểm thử lỗi, cần cấu hình error handler, `defaultRequeueRejected` và DLX hoặc cơ chế retry **có giới hạn**, dùng queue riêng. Đừng vô tình tạo vòng lặp retry nóng trong suite.

Với listener trả về `CompletableFuture`/`Mono`, `getResult()` có thể là đối tượng async được trả từ method, **không đồng nghĩa tác vụ bên trong đã hoàn tất**. Test phải chờ completion hoặc kiểm tra tác dụng nghiệp vụ riêng, bao gồm lỗi phát ra sau khi method trả về.

## 6. Spy và Mockito Answer: chờ số lần gọi có kiểm soát

Khi `spy = true`, test có thể lấy listener spy:

~~~java
OrderCreatedListener spy =
        harness.getSpy("orderCreatedListener");

verify(spy).handle("order-42");
~~~

Khi cần chờ **hai lần gọi**, `spring-rabbit-test` cung cấp tiện ích `LatchCountDownAndCallRealMethodAnswer` được thiết kế riêng để làm việc với harness:

~~~java
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.springframework.amqp.rabbit.test.mockito.LatchCountDownAndCallRealMethodAnswer;

OrderCreatedListener spy = harness.getSpy("orderCreatedListener");
LatchCountDownAndCallRealMethodAnswer answer =
        harness.getLatchAnswerFor("orderCreatedListener", 2);

doAnswer(answer).when(spy).handle(anyString());

rabbitTemplate.convertAndSend("tests.order.created", "order-1");
rabbitTemplate.convertAndSend("tests.order.created", "order-2");

assertTrue(answer.await(10), "Không nhận đủ hai callback");
assertTrue(answer.getExceptions() == null || answer.getExceptions().isEmpty());
~~~

`getLatchAnswerFor` thiết lập `Answer` sao cho vẫn gọi method thật, đếm số callback và ghi các exception, thay vì test chỉ stub method khiến logic nghiệp vụ không chạy. Có thể sử dụng `getLambdaAnswerFor(listenerId, callRealMethod, callback)` khi cần thay đổi kết quả trả về của method theo `InvocationOnMock`.

**Lưu ý:** khi tự viết một `Answer` phức tạp cho harness, cơ chế proxy và lời gọi delegate có thể khác spy Mockito thuần. Nếu cần gọi method gốc, nên dùng các helper do harness cung cấp; tài liệu cũng mô tả cách mở rộng `ForwardsInvocation` và `harness.getDelegate(id)` để tránh gọi vòng vào spy.

Test latch chỉ xác nhận method được gọi đủ lần, **không xác nhận broker đã ACK**, message đã bị xóa khỏi queue, hoặc database đã commit. Các kết quả đó cần assertion bổ sung ở đúng tầng kiểm thử.

## 7. TestRabbitTemplate: kiểm thử listener không cần RabbitMQ

`TestRabbitTemplate` là một công cụ khác trong `spring-rabbit-test`. Khi được đăng ký làm bean, nó tìm các listener containers trong context, lấy message listener rồi **gọi trực tiếp trên test thread**, không cần gửi qua broker.

Đặc tính cần hiểu:

- Nó hỗ trợ định tuyến **theo tên queue**. Đừng kỳ vọng nó mô phỏng exchange, routing key, headers exchange hoặc binding rules.
- Nó có thể dùng `convertAndSend` và một số thao tác request/reply để đi qua message adapter/converter và listener method.
- Mặc định logic gọi không tương đương một consumer chạy trên broker thật; callback thường xuất hiện ngay trong test thread.
- Nó không mô phỏng đầy đủ publisher confirms/returns, manual ACK, redelivery, retry TTL, dead-letter, transaction AMQP, quorum queue hay connection recovery.

### 7.1. Cấu hình một test không broker

~~~java
import static org.mockito.Mockito.mock;

import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.test.TestRabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
class NoBrokerRabbitConfig {

    @Bean
    ConnectionFactory connectionFactory() {
        return mock(ConnectionFactory.class);
    }

    @Bean
    SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setAutoStartup(false); // Không thử kết nối RabbitMQ.
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        return factory;
    }

    @Bean
    TestRabbitTemplate testRabbitTemplate(ConnectionFactory connectionFactory) {
        return new TestRabbitTemplate(connectionFactory);
    }

    @Bean
    EchoListener echoListener() {
        return new EchoListener();
    }

    static class EchoListener {
        @RabbitListener(queues = "tests.echo")
        public String reply(String payload) {
            return "echo:" + payload;
        }
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.test.TestRabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(NoBrokerRabbitConfig.class)
class NoBrokerListenerTest {

    @Autowired
    TestRabbitTemplate template;

    @Test
    void shouldReturnReplyWithoutBroker() {
        Object reply = template.convertSendAndReceive(
                "tests.echo", "hello");
        assertEquals("echo:hello", reply);
    }
}
~~~

Ví dụ dành cho **test listener/adapter ở phạm vi hẹp**. Khi dùng AMQP request/reply thật, message cần route đúng queue, listener container phải chạy và một reply message phải quay lại nơi đợi; `TestRabbitTemplate` không mô phỏng toàn bộ con đường đó.

Nếu muốn kiểm thử “lệnh gửi vào direct exchange với routing key `orders.created` tới queue `orders.q`”, hãy chuyển sang RabbitMQ integration test. Một test với `TestRabbitTemplate.convertAndSend("orders.q", ...)` không chứng minh binding đã được khai báo chính xác.

## 8. @RabbitAvailable: tích hợp có broker và quản lý vòng đời queue

`@RabbitAvailable` là JUnit 5 extension condition, kiểm tra broker có thể truy cập trước khi chạy integration test. Nếu broker không có sẵn, test mặc định bị **skip** thay vì thất bại vì connection refused.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.junit.RabbitAvailable;

@RabbitAvailable(
        queues = {"tests.integration.in", "tests.integration.dead"},
        purgeAfterEach = true)
class BrokerAvailableTest {
    @Test
    void brokerIsRequiredForThisScenario() {
        // Thêm các bước publish/consume thật.
    }
}
~~~

Các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| `queues` | Danh sách queue được tạo/chuẩn bị cho test, dọn sau test class |
| `purgeAfterEach` | Khi `true` (mặc định), purge test queues giữa các test methods |
| `management` | Khi `true`, condition còn yêu cầu RabbitMQ Management plugin |

**Không được dùng `@RabbitAvailable(queues=...)` trỏ đến broker/vhost production:** extension có thể **purge** những queue được nêu tên. Dùng broker hoặc vhost chuyên dụng cho test, với tên queue riêng biệt. Đừng cấp tài khoản CI quyền xóa queue nghiệp vụ.

### 8.1. Tránh “test xanh” do bị skip trên CI

Lúc phát triển cá nhân, skip khi RabbitMQ chưa chạy có thể chấp nhận được. Nhưng trên CI nightly hoặc pipeline release, ta thường muốn **fail** nếu integration tests không thực sự được chạy.

Đặt environment variable:

~~~bash
RABBITMQ_SERVER_REQUIRED=true
~~~

Khi biến này là `true`, `@RabbitAvailable` sẽ không âm thầm coi thiếu broker là lý do thành công của suite; test phải báo lỗi nếu broker không đáp ứng. CI cần phân biệt rõ:

- Bước unit tests: không cần broker, chạy trong mọi pull request.
- Bước integration tests: khởi động broker rồi chạy, **bắt buộc pass**.
- Bước fault tests: có thể cần điều kiện hạ tầng riêng, nhưng phải có lịch chạy và cảnh báo khi bị bỏ qua.

Các biến thử nghiệm như `RABBITMQ_TEST_HOSTNAME`, `RABBITMQ_TEST_PORT`, `RABBITMQ_TEST_USER` và `RABBITMQ_TEST_PASSWORD` có thể cấu hình kết nối. Nếu sử dụng Management API trong test, còn cần địa chỉ/credentials quản trị riêng. Không đẩy secret vào log.

## 9. Testcontainers: broker tạm thời, môi trường tái lập

Nếu môi trường CI hỗ trợ container, **RabbitMQ Testcontainers** giúp chạy broker thật với cổng được gán động. Nó giải quyết việc các máy developer dùng cấu hình RabbitMQ khác nhau và giảm nguy cơ test vô tình trỏ tới broker nghiệp vụ.

Ví dụ ở hệ Spring Boot có tích hợp Testcontainers (cần các test dependencies tương thích, bao gồm `spring-boot-testcontainers` và RabbitMQ Testcontainers module):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderRoutingIntegrationTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbitmq =
            new RabbitMQContainer("rabbitmq:4.1-management");

    @Autowired
    RabbitTemplate template;

    @Autowired
    RabbitAdmin admin;

    @Test
    void shouldRouteThroughRealExchangeAndBinding() {
        String suffix = java.util.UUID.randomUUID().toString();
        DirectExchange exchange =
                new DirectExchange("tests.orders.x." + suffix, false, true);
        Queue queue = QueueBuilder.nonDurable(
                "tests.orders.q." + suffix).autoDelete().build();

        admin.declareExchange(exchange);
        admin.declareQueue(queue);
        admin.declareBinding(
                BindingBuilder.bind(queue).to(exchange).with("orders.created"));

        try {
            template.convertAndSend(
                    exchange.getName(), "orders.created", "order-100");
            Object received =
                    template.receiveAndConvert(queue.getName(), 5_000);
            org.junit.jupiter.api.Assertions.assertEquals(
                    "order-100", received);
        } finally {
            admin.deleteQueue(queue.getName());
            admin.deleteExchange(exchange.getName());
        }
    }
}
~~~

Ví dụ này chứng minh **exchange/binding thật** nhận message qua producer và queue có thể được đọc trở lại, đồng thời dọn topology trong `finally`. Nó **chưa chứng minh listener nghiệp vụ đã xử lý và ACK**; muốn kiểm thử điều đó, đăng ký listener trong test context, publish vào queue của listener và chờ business state/capture. `@ServiceConnection` cấp broker cho Spring Boot test; image tag và Testcontainers imports cần tương thích với build.

Nếu không dùng `@ServiceConnection`, có thể đăng ký host/port thông qua `@DynamicPropertySource`:

~~~java
@DynamicPropertySource
static void rabbitProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.rabbitmq.host", rabbitmq::getHost);
    registry.add("spring.rabbitmq.port", rabbitmq::getAmqpPort);
}
~~~

Hai snippet minh họa **hai cách cung cấp connection properties**; trong dự án thực tế chọn một cách chính để tránh override khó hiểu. Với TLS, user/secret, vhost hoặc cluster topology phức tạp, phải bổ sung cấu hình riêng. `@ServiceConnection` không tự thay đổi ý nghĩa của ACK hay kết quả publish.

### 9.1. Một integration test phải assert toàn bộ hành trình

Khi bài toán là `OrderCreated`, tiêu chí đầy đủ có thể gồm:

~~~mermaid
flowchart TD
    TEST["JUnit test"] --> SEND["RabbitTemplate publish"]
    SEND --> EX["Exchange"]
    EX --> BIND["Routing key + binding"]
    BIND --> Q["Queue"]
    Q --> LISTENER["@RabbitListener"]
    LISTENER --> DB["Database / service fake"]
    DB --> ASSERT["Assert kết quả + ACK/DLQ/duplicate"]
~~~

Ví dụ test nên kiểm chứng **tác dụng nghiệp vụ**, không chỉ `Mockito.verify(listener)`:

~~~java
// Các bean repository/service là ví dụ nghiệp vụ của ứng dụng.
String eventId = "event-100";
rabbitTemplate.convertAndSend(
        "tests.orders.x", "orders.created", eventId);

// Awaitility có thể dùng nếu dự án thêm test dependency tương ứng.
await().atMost(java.time.Duration.ofSeconds(10))
       .untilAsserted(() ->
           assertEquals(1L, orderRepository.countByEventId(eventId)));
~~~

Đây là **đoạn trích test body**; `orderRepository`, queue/binding và `await()` cần được cung cấp bởi test context/import. Với at-least-once delivery, hãy kiểm tra **số lần thay đổi dữ liệu** hoặc unique business key, không chỉ số lần callback chạy.

## 10. Kiểm thử routing, publisher confirms và returns

Một bài kiểm thử định tuyến cần xác nhận RabbitMQ hiểu đúng topology:

1. Declare direct/topic exchange, durable queue và binding tới routing key dự kiến.
2. Bật `publisher-confirm-type: correlated` và `publisher-returns: true`; dùng `mandatory=true` khi cần phát hiện message không route được.
3. Publish message với `CorrelationData`, chờ result và kiểm tra không có returned message.
4. Assert consumer/repository đã nhận nội dung mong đợi.
5. Gửi routing key sai và xác minh có returned message, **dù broker có thể ACK publish**.

Ví dụ configuration (test hoặc application profile):

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Ví dụ kiểm chứng publish result (điều kiện là topology/connection đã khai báo):

~~~java
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.springframework.amqp.rabbit.connection.CorrelationData;

CorrelationData correlation =
        new CorrelationData(UUID.randomUUID().toString());

rabbitTemplate.convertAndSend(
        "tests.orders.x", "orders.created", "order-100", correlation);

CorrelationData.Confirm confirm =
        correlation.getFuture().get(10, TimeUnit.SECONDS);

assertTrue(confirm.isAck(), "Broker NACK publish");
assertNull(correlation.getReturned(), "Message không route tới queue");
~~~

**Publisher confirm ACK chỉ xác nhận phía publish** theo tính chất broker/queue; nó không chứng minh listener đã xử lý hay ACK. Test routing nên bổ sung assertion ở consumer. Thử đường return có giá trị vì binding thiếu hoặc routing key sai là lỗi mà `TestRabbitTemplate` không phát hiện được.

## 11. Test ACK/NACK, retry, DLX và idempotency

Một integration test nghiêm túc phải đặt ra các tình huống **thành công, thất bại tạm thời, thất bại vĩnh viễn và lỗi tại ranh giới ACK**.

| Tình huống | Thiết lập thử | Assertion quan trọng |
|---|---|---|
| Listener thành công | Message hợp lệ, database đáp ứng | Tác dụng nghiệp vụ commit, message được ACK và rời queue |
| Lỗi validation vĩnh viễn | Payload sai schema hoặc rule | Message đi DLQ/parking queue, không requeue vô hạn |
| Lỗi DB tạm thời | Fake/service ném lỗi lần đầu, thành công lần sau | Retry đúng giới hạn; nghiệp vụ chỉ ghi một lần |
| Manual ACK | Listener `ackMode="MANUAL"`, gọi `basicAck` sau commit | Không ACK trước commit, redelivery được xử lý an toàn |
| Channel chết trước ACK | Ngắt kết nối sau commit và trước ACK | Broker có thể redeliver; unique key chặn tác dụng lặp |
| Publisher chưa nhận confirm | Ngắt đường mạng khi publish in-flight | Không xóa outbox; retry cùng `eventId` |
| DLQ không có binding | Cố ý sai topology trên môi trường test | Cảnh báo/phát hiện message không đến parking queue |
| Retry loop vô hạn | NACK requeue liên tục | Test phát hiện vượt ngưỡng lần gọi/thời gian |
| Message bị duplicate | Publish cùng `eventId` hai lần | Tác dụng nghiệp vụ xuất hiện đúng một lần |
| Consumer cạnh tranh | Nhiều consumer, payload xử lý chậm/nhanh | Không giả định thứ tự completion, kiểm tra nhất quán DB |
| Listener bất đồng bộ | Trả `CompletableFuture`/`Mono` | ACK sau completion thực, không nuốt exception |
| Batch listener | Gom nhiều message và ném lỗi một phần tử | Biết phạm vi retry/ACK của batch và xử lý idempotent |

### 11.1. Nguyên tắc khi test lỗi

Nếu listener lỗi và `defaultRequeueRejected=true`, cùng message có thể được giao lại ngay. Không nên chỉ để test chờ 10 giây rồi cho rằng “chưa thấy DLQ”. Hãy chủ động cấu hình DLX, cách ly queue lỗi, giới hạn retry và ghi nhận số lần gọi.

Ví dụ một topology có parking queue:

~~~java
@Bean
Queue testOrdersQueue() {
    return QueueBuilder.durable("tests.orders.q")
            .deadLetterExchange("tests.orders.dlx")
            .deadLetterRoutingKey("orders.failed")
            .build();
}

@Bean
DirectExchange testOrdersDlx() {
    return new DirectExchange("tests.orders.dlx", true, false);
}

@Bean
Queue testOrdersParkingQueue() {
    return QueueBuilder.durable("tests.orders.parking.q").build();
}

@Bean
Binding parkingBinding(
        @Qualifier("testOrdersParkingQueue") Queue queue,
        @Qualifier("testOrdersDlx") DirectExchange dlx) {
    return BindingBuilder.bind(queue).to(dlx).with("orders.failed");
}
~~~

Ví dụ giả định có imports tương ứng từ `org.springframework.amqp.core` và `org.springframework.beans.factory.annotation.Qualifier`; cũng cần declare exchange/queue/binding cho **đường gửi vào queue chính**. Sau lỗi với `requeue=false`, test nên chờ message đến parking queue và kiểm tra headers/payload, không mặc định `x-death` đếm mọi dạng retry.

### 11.2. Dùng database unique key để xác minh idempotency

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Listener/service ghi dấu event đã xử lý và tác dụng nghiệp vụ trong **cùng database transaction**. Một test có thể publish hai message mang cùng `eventId` rồi assert bảng nghiệp vụ chỉ tăng một record. Nếu service còn gọi HTTP API hoặc gửi email, unique key trong database **không tự bảo vệ** tác dụng ngoài database; cần kiểm chứng idempotency key hoặc outbox cho tác vụ tiếp theo.

## 12. Tránh flaky tests trong hệ thống bất đồng bộ

Một test thỉnh thoảng đỏ khi CI tải cao thường không phải do business logic sai. Nó có thể sai vì **chờ không đúng tín hiệu**, test chia sẻ queue, broker chưa sẵn sàng hoặc listener cũ của test khác vẫn chạy.

### 12.1. Không dùng Thread.sleep như điều kiện thành công

Đoạn code sau không xác định được consumer có xử lý xong hay không:

~~~java
rabbitTemplate.convertAndSend("tests.orders.q", "order-42");
Thread.sleep(500);
assertEquals(1, repository.countOrders());
~~~

Trên máy nhanh 500 ms có thể đủ, còn CI chạy song song thì không. Tốt hơn là chờ **một điều kiện có ý nghĩa**:

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> assertEquals(1, repository.countOrders()));
~~~

`await()` từ **Awaitility** chỉ có khi thêm thư viện test đó. Với listener instrumentation, dùng `harness.getNextInvocationDataFor(...)` hoặc `getLatchAnswerFor(...)` như các phần trước, rồi kiểm tra state sau khi callback đã đến.

### 12.2. Đừng dùng số lượng invocation làm bằng chứng “exactly once”

RabbitMQ thường được thiết kế theo **at-least-once** ở những luồng cần độ tin cậy: một delivery có thể được giao lại sau khi consumer commit DB nhưng ACK bị mất. Một test chỉ `verify(spy, times(1))` ở lần chạy bình thường không chứng minh logic không bị ghi trùng khi xảy ra redelivery.

Với business effect, assert bằng **database state** và constraint idempotency; với routing, assert message đến queue đích; với publisher, assert correlated confirm/return; với ACK, kiểm tra unacked/ready trạng thái phù hợp và test redelivery có chủ đích.

### 12.3. Cô lập tài nguyên giữa các test

Các biện pháp:

- Mỗi suite hoặc test class dùng queue/exchange prefix riêng như `tests.orders.`suite-id``, không dùng tên production.
- Với `@RabbitAvailable`, hiểu rõ `purgeAfterEach` và thời điểm extension tạo/xóa queue.
- Nếu dùng shared broker, tránh test song song tranh cùng queue; có thể tắt parallel execution cho nhóm integration test.
- Nếu giữ Spring TestContext cache, bảo đảm listener cũ không đọc message của test mới ngoài ý muốn; cân nhắc `@DirtiesContext` khi test thay đổi bean/container lifecycle.
- Sau một test lỗi, dọn broker topology/bảng DB thử nghiệm bằng cơ chế có kiểm soát; không purge queue production.
- Đừng dùng fixed port khi Testcontainers cung cấp port động; hãy truyền connection properties qua `@ServiceConnection` hoặc `@DynamicPropertySource`.

### 12.4. Phân biệt timeout test và timeout nghiệp vụ

Timeout `10 seconds` khi chờ callback chỉ là **giới hạn chờ của test**. Nó không thay đổi:

- RabbitMQ heartbeat hoặc connection timeout.
- Timeout của `RabbitTemplate` khi đợi reply.
- Retry interval/`backOff` của listener.
- TTL của retry queue hoặc dead-letter behavior.
- Thời gian xử lý `CompletableFuture`/`Mono` trong ứng dụng.

Đặt timeout test lớn hơn khoảng thời gian cần thiết cho kịch bản hợp lệ, nhưng đủ ngắn để báo lỗi nhanh. Không tăng timeout vô hạn để che một loop retry hoặc deadlock.

## 13. Bài thực hành tổng hợp: xác nhận đúng cấp độ kiểm thử

Giả sử yêu cầu nghiệp vụ:

> “Khi sự kiện `OrderCreated` được publish vào `orders.events.x` với routing key `orders.created`, invoice service tạo hóa đơn một lần. Nếu payload không hợp lệ, message cần đi tới parking queue. Nếu kết nối bị mất sau DB commit, lần giao lại không được tạo thêm hóa đơn.”

Nên phân chia test như sau:

| Bài test | Công cụ nên dùng | Assertion cốt lõi |
|---|---|---|
| Validate `orderId` rỗng | Mockito/JUnit unit test | Ném đúng exception và không gọi database |
| Chuyển payload String/JSON vào method listener | `TestRabbitTemplate` nếu không cần broker | Listener nhận kiểu/giá trị đúng |
| Listener đã được gọi 2 lần, lần cuối ném lỗi | `@RabbitListenerTest(capture=true)` | `InvocationData` chứa arguments, result/throwable |
| Exchange/binding route thành công | `@SpringRabbitTest` + broker hoặc `@SpringBootTest` + Testcontainers | Message đến queue đích, consumer xử lý |
| Routing key sai | Broker thật + correlated confirms/returns | Có publisher return, không đánh dấu thành công |
| Message lỗi tới parking | Broker thật, DLX/queue test riêng | Message được cách ly, không lặp vô hạn |
| Consumer chết trước ACK | Broker thật + fault injection | Redelivery và idempotent DB |
| Nâng version Spring AMQP hoặc RabbitMQ | Integration/fault suite trong pipeline | Không regression về converter, ACK/NACK, retry, recovery |

### Thứ tự triển khai hợp lý

1. Viết unit test service xử lý event, với database mock hoặc transaction test riêng.
2. Viết `TestRabbitTemplate` test cho listener adapter/converter nếu cần tốc độ nhanh.
3. Bật `@RabbitListenerTest(spy=true, capture=true)` trong context test để quan sát arguments, exception và async callback.
4. Dùng RabbitMQ thật qua `@RabbitAvailable` hoặc Testcontainers để kiểm tra routing, confirms, queue arguments, retry và DLQ.
5. Thêm kịch bản crash/reconnect để xác nhận duplicate handling và recovery.
6. Chạy cùng suite sau mỗi lần thay đổi dependency, queue type, retry policy hoặc listener concurrency.

## 14. Những hiểu lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
|---|---|
| “`spring-rabbit-test` là một RabbitMQ broker nhúng” | Nó là **test support library**, không tạo broker thật |
| “`@SpringRabbitTest` đủ để test end-to-end” | Chỉ đăng ký infrastructure beans; gửi/nhận thật vẫn cần broker |
| “Dự án có `@SpringBootTest` thì phải thêm `@SpringRabbitTest`” | Spring Boot đã có AMQP auto-configuration, tránh tạo bean trùng |
| “`@RabbitListenerTest` cần broker để spy” | Harness instrument listener trong context; broker chỉ cần khi bạn muốn kiểm tra delivery thật |
| “Spy luôn lấy được listener không có id” | Harness cần `@RabbitListener(id=...)` để định danh |
| “Final listener method vẫn spy/capture được” | Method `final` không được spy/advised theo cơ chế này |
| “Capture thành công nghĩa là ACK đã tới broker” | Invocation được ghi khi method chạy; ACK là chuyện riêng của container/broker |
| “`TestRabbitTemplate` mô phỏng exchange binding” | Nó route trực tiếp theo **queue name**, bỏ qua routing thực của broker |
| “Gửi message rồi verify ngay là ổn” | Consumer là async; cần wait/capture/latch với timeout |
| “`@RabbitAvailable` không tìm thấy broker thì build lỗi” | Mặc định skip; CI có thể đặt `RABBITMQ_SERVER_REQUIRED=true` để fail |
| “`@RabbitAvailable` dùng an toàn với broker production” | Extension có thể tạo/purge/xóa test queues, phải cách ly môi trường |
| “Chỉ test happy path chứng minh exactly once” | Cần test duplicate sau DB commit và ACK chưa được ghi nhận |
| “Tăng thời gian sleep khắc phục flaky test” | Cần chờ điều kiện nghiệp vụ, cô lập queue và kiểm soát lifecycle |

## 15. Checklist trước khi chấp nhận một RabbitMQ test suite

1. **Đúng phiên bản:** `spring-rabbit-test` tương thích với `spring-rabbit` và Spring Boot BOM.
2. **Đúng loại test:** unit, no-broker listener, spy/capture hay integration/fault test.
3. **Test context:** không chồng `@SpringRabbitTest` với auto-configuration Boot không cần thiết.
4. **Listener instrumentation:** có `id`, không `final` và kích hoạt `spy/capture` đúng mục đích.
5. **Đồng bộ hóa test:** dùng invocation capture, latch hoặc await theo điều kiện; không chỉ `sleep`.
6. **Môi trường broker:** dedicated vhost/container, không động chạm queue nghiệp vụ.
7. **CI thực sự chạy:** thiếu broker không được âm thầm thành “xanh” ở pipeline bắt buộc integration tests.
8. **Routing:** test exchange/queue/binding thật, kể cả routing key sai và publisher return.
9. **Delivery:** test ACK/NACK, retry hữu hạn, DLX và parking queue.
10. **Sự cố:** test connection loss, redelivery, publish outcome chưa rõ và event ID ổn định.
11. **Idempotency:** kiểm tra tác dụng nghiệp vụ bằng state/unique constraint, không chỉ số lần listener được gọi.
12. **Dọn dẹp:** queue, container, test database và listener lifecycle được xử lý rõ ràng.

### Tài liệu chính thức để đối chiếu theo phiên bản

- [Spring AMQP — Testing Support](https://docs.spring.io/spring-amqp/reference/testing.html): `spring-rabbit-test`, `@SpringRabbitTest`, `@RabbitListenerTest`, `TestRabbitTemplate` và JUnit conditions.
- [Spring AMQP Javadoc — SpringRabbitTest](https://docs.spring.io/spring-amqp/docs/current/api/org/springframework/amqp/rabbit/test/context/SpringRabbitTest.html): infrastructure beans và `containerType`.
- [Spring AMQP Javadoc — RabbitListenerTest](https://docs.spring.io/spring-amqp/docs/current/api/org/springframework/amqp/rabbit/test/RabbitListenerTest.html): `spy` và `capture`.
- [Spring AMQP Javadoc — RabbitListenerTestHarness](https://docs.spring.io/spring-amqp/docs/current/api/org/springframework/amqp/rabbit/test/RabbitListenerTestHarness.html): `getSpy`, `getNextInvocationDataFor` và Mockito answers.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): chạy infrastructure container và cấu hình connection trong test.

**Kết luận:** `spring-rabbit-test` giúp kiểm thử ứng dụng **SPRING_AMQP** ở nhiều mức nhưng mỗi công cụ có phạm vi rõ ràng: dùng **`@SpringRabbitTest`** để có hạ tầng RabbitMQ gọn nhẹ trong Spring TestContext; dùng **`@RabbitListenerTest` + `RabbitListenerTestHarness`** để spy/capture listener; dùng **`TestRabbitTemplate`** khi muốn test adapter không có broker; và **RabbitMQ thật** khi cần khẳng định routing, confirms, ACK/NACK, retry, dead-letter và phục hồi kết nối. Kết hợp chờ điều kiện có timeout, tài nguyên test riêng và kiểm tra idempotency sẽ tạo bộ test vừa ít flaky vừa phản ánh đúng hành vi xử lý message bất đồng bộ.
