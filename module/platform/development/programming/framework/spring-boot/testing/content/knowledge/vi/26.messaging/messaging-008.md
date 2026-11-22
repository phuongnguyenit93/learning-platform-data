# Xác nhận xử lý bất đồng bộ bằng điều kiện có thời hạn

## 1. Mục tiêu bài học

Trong hệ thống Spring Boot dùng **Messaging** — RabbitMQ, Kafka, JMS hoặc một event bus — gửi message thành công và xử lý message thành công là **hai sự kiện khác nhau**. Producer có thể publish xong trước khi consumer bắt đầu xử lý; consumer có thể retry, chuyển vào dead-letter queue (DLQ), ghi dữ liệu trong transaction khác hoặc xử lý bằng nhiều worker threads.

Vì vậy, một bài test viết:

~~~java
publisher.publish(orderId);
assertEquals("COMPLETED", orderRepository.findStatus(orderId));
~~~

có thể **fail ngẫu nhiên**: assertion được chạy ngay lập tức, trong khi message chưa được listener tiêu thụ. Ngược lại:

~~~java
publisher.publish(orderId);
Thread.sleep(3000);
assertEquals("COMPLETED", orderRepository.findStatus(orderId));
~~~

chỉ thay race condition bằng **chờ mù**. Có lần worker xong sau 50 ms nhưng test vẫn chờ 3 giây; có lần CI chậm 4 giây thì test fail, dù nghiệp vụ cuối cùng hoạt động đúng.

Giải pháp thường dùng là **chờ tới khi một điều kiện nghiệp vụ có thể quan sát được trở thành đúng, nhưng giới hạn bằng một deadline rõ ràng**. Với Java/JUnit, **Awaitility** là một thư viện phổ biến; có thể kết hợp với Spring Boot, `@RabbitListener`, `KafkaListener`, repositories, cache hoặc các bất đồng bộ khác.

Bài thuộc phần **Messaging** của module **Spring Boot – testing**, đúng chủ đề **Xác nhận xử lý bất đồng bộ bằng điều kiện có thời hạn**. Nội dung đi từ cách xác định điều kiện đáng tin đến ví dụ RabbitMQ/Testcontainers chạy message thật và các bẫy liên quan đến ack, retry, isolation và parallel CI.

Sau khi học, bạn có thể:

1. Phân biệt **publish**, **broker accept**, **consumer receive**, **business side effect**, **transaction commit** và **ack/offset commit**.
2. Viết `await().atMost(...).untilAsserted(...)` để xác minh trạng thái cuối mà không dùng sleep cố định.
3. Chọn `pollInterval`, `pollDelay`, `atMost`, `during`, `atLeast`, `failFast` đúng mục đích.
4. Đặt điều kiện theo **message ID/correlation ID** thay vì đếm tổng số record hoặc queue size.
5. Kiểm cả **kết quả cuối** lẫn **số tác động nghiệp vụ** để phát hiện duplicate delivery.
6. Biết vì sao việc consumer đọc được message **không tự chứng minh** database transaction đã commit.
7. Dùng `ConditionTimeoutException` làm tín hiệu test thất bại có diagnostic, không phải nguyên nhân phải tăng sleep vô hạn.
8. Test RabbitMQ thật bằng `RabbitMQContainer`, `RabbitTemplate` và `@RabbitListener` trên Spring Boot 3.3.5.
9. Tạo các ca positive, business rejection, duplicate message, negative observation, fail-fast và expected timeout.
10. Tránh test flakes khi broker khởi động chậm, context caching, delayed delivery, retry/DLQ, nhiều consumer và parallel tests.
11. Đánh giá những lựa chọn khác: `CountDownLatch`, `CompletableFuture`, Mockito `timeout()`, `StepVerifier`, `KafkaTestUtils` và polling repository.
12. Thiết kế test có deadline nhưng vẫn phù hợp SLA/consistency model của hệ thống.

**Nguyên tắc:** Chờ **điều kiện có nghĩa nghiệp vụ** trong một **khoảng thời gian hữu hạn**, sau đó fail với trạng thái đã quan sát được. Đừng chờ bằng “đủ lâu chắc xong”, cũng đừng coi `RabbitTemplate.convertAndSend(...)` return là bằng chứng consumer đã xử lý.

## 2. Vì sao Messaging làm assertion đồng bộ dễ sai?

Hình dung order service publish một message `OrderPaid`:

~~~text
JUnit test thread
   |
   | publish(orderId = "o-123")
   v
RabbitTemplate / KafkaTemplate
   |
   | Broker nhận / route message
   v
RabbitMQ queue / Kafka topic
   |
   | Delay do scheduling / broker / prefetch
   v
Listener thread
   |
   | Validate, transform, gọi service
   v
Repository / database transaction
   |
   | COMMIT rồi update read model/cache
   v
Read API / query mà test quan sát được
~~~

Tại thời điểm producer return, worker có thể ở bất kỳ chặng nào. Do đó:

- Producer không nắm chắc thời điểm consumer tạo side effect.
- Khi broker durable/ack enabled, broker nhận message không đồng nghĩa database đã commit.
- Consumer có thể thất bại, retry, redeliver; **at-least-once delivery** khiến cùng event có thể được xử lý nhiều lần.
- Nếu test đọc từ replica/cache, trạng thái có thể chậm hơn transaction commit.
- Nếu test sử dụng cùng JPA persistence context, nó có thể nhìn thấy dữ liệu chưa commit hoặc cache cũ.
- Nếu test dùng `@Transactional`, transaction của test thread không bao phủ các listener threads khác.

Một bài test Messaging tốt phải chọn **mốc hoàn tất**. Ví dụ, nếu hợp đồng là “order được đánh dấu PAID trong DB”, điều kiện cần chờ là **query DB thấy PAID đã commit**, không phải “listener method đã được gọi” hoặc “queue còn 0 message”.

### Các mốc không tương đương

| Tín hiệu | Chứng minh gì? | Chưa chứng minh gì? |
| --- | --- | --- |
| Producer method return | Code gọi publish đã thực hiện xong theo API | Broker đã route/consumer đã xử lý |
| Publisher confirm (RabbitMQ) | Broker xác nhận publish theo cấu hình confirms | Listener hoàn tất side effect |
| Message xuất hiện trong queue/topic | Broker lưu/route message | Consumer đã consume và commit |
| Listener invocation counter | Listener được gọi ít nhất một lần | Transaction của business đã commit |
| Consumer ack / Kafka offset commit | Theo broker/consumer protocol, message đã được đánh dấu xử lý tiến độ | Mọi side effect ở hệ khác thành công nếu không có atomicity bảo đảm |
| DB row có trạng thái cuối | Nghiệp vụ được nhìn thấy trong DB tại lúc query | Có chắc đúng một lần hoặc downstream tiếp theo hoàn tất? |
| HTTP read model cập nhật | External observable state đã sẵn sàng | Không bảo đảm mọi subscriber khác xong |
| DLQ có message | Message vào đường xử lý lỗi | Chưa chứng minh quá trình recovery/alert hoàn thành |

**Chọn assert theo hợp đồng.** Nếu cần bảo đảm “chỉ một email được gửi”, chờ DB status PAID là chưa đủ. Cần kiểm idempotency/outbox/email gateway fake trong một môi trường test phù hợp.

## 3. Từ sleep sang chờ điều kiện có thời hạn

Mẫu yếu:

~~~java
publisher.publish(orderId);
Thread.sleep(2000);
assertEquals("COMPLETED", state.get(orderId));
~~~

Nhược điểm:

- **False negative:** worker hoàn tất sau 2,1 s -> test fail.
- **Lãng phí:** worker hoàn tất sau 30 ms -> test chờ thừa 1.970 ms.
- **Không có diagnostic:** không biết state đang PENDING, RETRYING hay FAILED.
- **Tăng sleep lan man:** các tests CI có thể chậm hàng phút.
- **Không kiểm đường lỗi:** worker có thể dead-letter ngay từ đầu nhưng test vẫn chờ hết.
- **Không kiểm correlation:** state của message test khác có thể thỏa assertion chung.

Mẫu tốt hơn:

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() ->
        assertEquals("COMPLETED", state.get(orderId)));
~~~

Đây là **snippet minh họa**, giả định `state` là một nguồn quan sát thread-safe và `await()` có static import từ Awaitility. Ý nghĩa:

1. Bắt đầu quan sát condition theo lịch polling.
2. Nếu assertion chưa đúng, thử lại.
3. **Dừng sớm** khi assertion thành công.
4. Nếu quá 10 giây, throw `ConditionTimeoutException`, khiến test fail.
5. Message cụ thể được nhận diện bằng `orderId`.

`atMost(10s)` là **trần chờ**, không phải “test luôn chờ 10 giây”. Nếu hệ thống xong sau 200 ms, test kết thúc gần lần poll sau thời điểm đó.

### Dùng `until` hay `untilAsserted`?

`until` phù hợp một predicate đơn giản:

~~~java
await().atMost(Duration.ofSeconds(5))
    .until(() -> repository.status(orderId) == Status.COMPLETED);
~~~

`untilAsserted` phù hợp khi cần **nhiều assertions** và thông tin lỗi rõ:

~~~java
await().atMost(Duration.ofSeconds(5))
    .untilAsserted(() -> {
        assertEquals(Status.COMPLETED,
                repository.status(orderId));
        assertEquals(1L,
                repository.countEffectsFor(orderId));
    });
~~~

`untilAsserted` thử lại khi assertions trong callback chưa pass. Khi timeout, Awaitility giữ thông tin assertion cuối cùng giúp debug. Không đặt các thao tác **gây side effect** trong callback polling; chúng có thể chạy nhiều lần.

## 4. Awaitility và đơn vị thời gian

Thư viện:

~~~groovy
testImplementation 'org.awaitility:awaitility'
~~~

Trong project Spring Boot 3.3.5, version Awaitility được quản lý bởi Spring Boot dependency management. Nếu test starter của dự án đã transitively đem Awaitility vào, khai báo trực tiếp vẫn có lợi vì source đang dùng API của nó.

Các import thường dùng:

~~~java
import java.time.Duration;
import static org.awaitility.Awaitility.await;
~~~

### `atMost`

~~~java
await()
    .atMost(Duration.ofSeconds(8))
    .until(() -> data.getState(id) == COMPLETED);
~~~

Nghĩa: chờ **tối đa** 8 giây. Nếu không đúng sẽ fail. Đặt deadline đủ để dung nạp startup/scheduling bình thường nhưng không che một consumer bị treo.

### `pollInterval`

~~~java
await()
    .atMost(Duration.ofSeconds(8))
    .pollInterval(Duration.ofMillis(100))
    .until(() -> state.get(id) == COMPLETED);
~~~

Nghĩa: tần suất đọc condition. 100 ms là ví dụ thích hợp cho in-memory state/test-local DB; với remote database đắt đỏ, có thể tăng lên 250–500 ms hoặc dùng backoff. **Không poll hàng nghìn lần mỗi giây**.

### `pollDelay`

~~~java
await()
    .pollDelay(Duration.ofMillis(50))
    .pollInterval(Duration.ofMillis(100))
    .atMost(Duration.ofSeconds(8))
    .until(() -> state.get(id) == COMPLETED);
~~~

`pollDelay` cho phép trì hoãn lần kiểm đầu; thường không cần tăng nó nếu muốn kết thúc sớm. Defaults phụ thuộc phiên bản và cách chọn poll interval; để bài test rõ ràng, khai báo có chủ đích khi timing là một phần của logic.

### `alias`

~~~java
await()
    .alias("order " + orderId + " eventually completes")
    .atMost(Duration.ofSeconds(8))
    .untilAsserted(() ->
        assertEquals(COMPLETED, state.get(orderId)));
~~~

`alias` giúp thông báo timeout gắn với order/test cụ thể, nhất là khi class có nhiều awaits hoặc CI log chạy song song.

### `during`

~~~java
await()
    .during(Duration.ofMillis(300))
    .atMost(Duration.ofSeconds(2))
    .until(() -> state.get(unrelatedId) == UNKNOWN);
~~~

Ý nghĩa: điều kiện phải **duy trì đúng** trong một khoảng quan sát. Một lần `assertNull` ngay sau publish không đủ chứng minh một trạng thái không xuất hiện ngay sau đó. Tuy nhiên, **duy trì đúng 300 ms không chứng minh điều đó sẽ đúng mãi mãi**.

### `atLeast`

~~~java
await()
    .atLeast(Duration.ofMillis(200))
    .atMost(Duration.ofSeconds(2))
    .until(() -> observed.get());
~~~

`atLeast` không phải cách viết khác của `during`. Nó yêu cầu điều kiện **không được hoàn tất quá sớm**: nếu `observed` trở thành true trước ngưỡng tối thiểu, Awaitility coi đó là lỗi. Dùng khi hợp đồng thực sự có **minimum delay** (ví dụ một rule chống spam), không dùng để giả lập “test nên chờ ít nhất một lúc”.

### `failFast`

~~~java
await()
    .failFast("Order has terminal FAILED state",
        () -> status(id) == FAILED)
    .atMost(Duration.ofSeconds(10))
    .until(() -> status(id) == COMPLETED);
~~~

Nếu đã biết state **FAILED là terminal**, tiếp tục chờ hết 10 giây là lãng phí. `failFast` cho phép dừng test ngay khi quan sát trạng thái không thể hồi phục. Chỉ dùng khi **terminal thật**; nếu FAILED chỉ là một lần retry tạm, fail-fast sẽ tạo false negative.

### `ignoreExceptions`

Có thể dùng khi một lỗi cụ thể là trạng thái chuyển tiếp hợp lệ:

~~~java
await()
    .ignoreExceptionsMatching(error ->
        error instanceof TransientReadException)
    .atMost(Duration.ofSeconds(8))
    .until(() -> readModel.getStatus(id) == COMPLETED);
~~~

**Snippet minh họa:** `TransientReadException` phải do hệ thống định nghĩa; đoạn code không biên dịch độc lập. Không gọi `ignoreExceptions()` cho mọi exception để che authentication failure, schema mismatch, connection leak hoặc lỗi code. Một lỗi không thể phục hồi nên fail sớm thay vì bị nuốt và cuối cùng báo timeout vô nghĩa.

## 5. Thiết kế điều kiện kiểm thử có giá trị

Một điều kiện tốt có các thuộc tính:

- **Tương ứng một message/correlation ID**: không đọc một biến toàn cục dùng chung.
- **Observable**: test có thể truy vấn mà không ép listener chạy đồng bộ.
- **Thread-safe hoặc committed**: tránh data race giữa listener và JUnit.
- **Ổn định ở trạng thái cuối**: không thấy COMPLETED tạm thời rồi lại mất do transaction rollback.
- **Không tạo side effects**: polling không gửi thêm message, không xóa DB, không trigger retry.
- **Có deadline**: sẽ dừng và báo lỗi.
- **Phân biệt terminal failure**: không chờ vô ích nếu đã xác định DEAD_LETTERED/FAILED.
- **Có diagnostic**: trạng thái cuối, số attempts, queue/topic, message ID.
- **Có test isolation**: mỗi method dùng ID riêng, không phụ thuộc thứ tự test.

### Điều kiện yếu: queue trống

~~~java
await().until(() -> queueDepth() == 0);
~~~

Queue depth 0 **không chứng minh consumer đã commit**. Message có thể đã bị prefetch và đang **unacked**, đang retry, đã dead-letter hoặc bị consumer khác lấy. Queue metrics cũng có thể cập nhật trễ. Muốn chứng minh business completed, hãy chờ **business state**.

### Điều kiện yếu: listener được gọi

~~~java
verify(listener, timeout(5000)).onMessage(any());
~~~

Mockito timeout có thể hữu ích cho một collaboration test, nhưng:

- Không tự chứng minh listener được gọi qua **broker thật** nếu method được mock hoặc test gọi trực tiếp.
- Không bảo đảm listener transaction đã commit.
- `any()` có thể match event của test khác.
- Không kiểm side effect cuối khi listener gọi tiếp một async service.

Nếu dùng spy/mock để kiểm invocation, vẫn nên có một integration test quan sát state theo message ID.

### Điều kiện mạnh: persisted effect

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() -> {
        assertEquals(Status.COMPLETED,
                orderRepository.findStatus(orderId));
        assertEquals(1L,
                outboxRepository.countByOrderId(orderId));
    });
~~~

Đây là **snippet kiến trúc**; repository/entity chưa nằm trong project runnable. Khi có database thật, mỗi lần poll nên dùng transaction/connection có thể thấy **committed state**. Tránh dùng JPA `EntityManager`/session đã cache state cũ từ trước.

## 6. Ví dụ chạy được: Spring Boot, RabbitMQ Testcontainers và Awaitility

Để kiểm thực tế, ví dụ sẽ dùng **RabbitMQ chạy trong Testcontainers**, không mock `RabbitTemplate` hoặc gọi trực tiếp listener. Test gửi một string event vào RabbitMQ, listener chạy trên thread riêng của Spring AMQP, rồi cập nhật một `ProcessingLedger` thread-safe để test quan sát bằng Awaitility.

**Tại sao dùng in-memory ledger thay database trong ví dụ cơ bản?**

- Mục tiêu bài là **chờ bất đồng bộ đúng cách**, không phải triển khai JDBC transaction/outbox.
- Thread-safe `ConcurrentHashMap`/`AtomicInteger` giúp quan sát hành vi giữa threads mà không cần thêm database.
- Chúng ta có thể đếm **số lần delivery** và **số tác động logic** để minh họa idempotency.
- Bài sẽ nêu rõ giới hạn: cập nhật in-memory ledger **không chứng minh database commit hoặc broker ACK**. Production integration test nên thay ledger bằng repository/DB/read model thật nếu đó là hợp đồng nghiệp vụ.

Project dùng **Java 17, Spring Boot 3.3.5, Gradle Groovy DSL, spring-boot-starter-amqp, Awaitility, Testcontainers RabbitMQ và JUnit 5**. Cần Docker hoặc container runtime tương thích để chạy integration tests.

### Cấu trúc project

~~~text
messaging-await-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/messaging/
    │   ├── MessagingApplication.java
    │   ├── MessagingConfig.java
    │   ├── ProcessingLedger.java
    │   ├── OrderEventListener.java
    │   └── OrderPublisher.java
    └── test/java/com/example/messaging/
        └── RabbitAsyncAwaitTest.java
~~~

Gradle Wrapper scripts/JAR cần được tạo bằng Gradle phù hợp hoặc lấy từ repo, không tự viết nội dung binary JAR trong Markdown. Các source files bên dưới đủ để thực thi `gradlew test` sau khi project có Wrapper/JDK và Docker phù hợp.

### `settings.gradle`

~~~groovy
rootProject.name = 'messaging-await-lab'
~~~

### `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.awaitility:awaitility'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:rabbitmq'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Giải thích:

- `spring-boot-starter-amqp` đem `RabbitTemplate`, `@RabbitListener`, listener containers và Spring AMQP auto-configuration.
- `spring-boot-starter-test` chứa Spring TestContext/JUnit Jupiter và assertions.
- `org.awaitility:awaitility` cung cấp `await()`, `untilAsserted`, `during`, `failFast` và deadline.
- `org.testcontainers:junit-jupiter` cung cấp `@Testcontainers`, `@Container`.
- `org.testcontainers:rabbitmq` có `RabbitMQContainer` dùng AMQP broker thật.
- `useJUnitPlatform()` bắt buộc Gradle chạy JUnit Jupiter đúng.
- Các versions Testcontainers/Awaitility do Spring Boot BOM quản lý. Module `org.testcontainers:rabbitmq` là tọa độ thuộc dòng Testcontainers **1.x** phù hợp với Boot 3.3; dòng Testcontainers 2.x mới có module/group names khác, nên không tự copy dependency hiện đại vào build 3.3 mà không cập nhật tương thích.
- Không cần PostgreSQL/H2, Kafka, web server hoặc `@Async` để chứng minh logic Awaitility.
- Không có broker credentials production. Testcontainers cấp RabbitMQ test user/password riêng trong container tạm.

### `MessagingApplication.java`

~~~java
package com.example.messaging;

import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@EnableRabbit
public class MessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }
}
~~~

`@EnableRabbit` bật annotation listener endpoints một cách tường minh. Spring Boot thường auto-configure các Rabbit listener container factories khi có AMQP infrastructure. Application root đặt trong `com.example.messaging`, nên Spring Boot scan đủ các classes còn lại.

Project demo **không** đặt RabbitMQ URL mặc định trỏ production trong main resources. Các tests cấp endpoint RabbitMQ thông qua `@DynamicPropertySource` trước khi Spring tạo connection factory.

### `MessagingConfig.java`: queue test được khai báo bởi Spring AMQP

~~~java
package com.example.messaging;

import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MessagingConfig {

    @Bean
    Queue ordersQueue(
            @Value("${demo.orders.queue}") String name) {

        return QueueBuilder.nonDurable(name)
                .autoDelete()
                .build();
    }
}
~~~

`QueueBuilder.nonDurable(name).autoDelete()` tạo queue dành cho test/demo, không phải quy tắc dùng cho production durable queues. Nó cho phép test gắn một tên queue duy nhất mà không trùng queue của suite khác.

Spring Boot/`RabbitAdmin` có thể tự khai báo `Queue` bean trên RabbitMQ khi connection được mở. Trong test bên dưới, ta gọi `AmqpAdmin.declareQueue(...)` tại `@BeforeEach` để chắc chắn queue có mặt trước khi publish. Khai báo lại **cùng tên/cùng thuộc tính** là idempotent theo giao thức broker; khai báo cùng tên nhưng khác durability/arguments có thể bị RabbitMQ từ chối bằng `PRECONDITION_FAILED`.

### `ProcessingLedger.java`: trạng thái thread-safe và đếm tác động

~~~java
package com.example.messaging;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
public class ProcessingLedger {

    public enum State {
        UNSEEN, COMPLETED, DECLINED
    }

    private final ConcurrentMap<String, State> states =
            new ConcurrentHashMap<>();

    private final ConcurrentMap<String, AtomicInteger> deliveries =
            new ConcurrentHashMap<>();

    private final ConcurrentMap<String, AtomicInteger> effects =
            new ConcurrentHashMap<>();

    private final Set<String> handledIds =
            ConcurrentHashMap.newKeySet();

    public void record(String eventId, State outcome) {
        deliveries.computeIfAbsent(
                eventId, id -> new AtomicInteger())
                .incrementAndGet();

        // Chặn lặp tác động logic theo eventId.
        if (handledIds.add(eventId)) {
            effects.computeIfAbsent(
                    eventId, id -> new AtomicInteger())
                    .incrementAndGet();
            states.put(eventId, outcome);
        }
    }

    public State state(String eventId) {
        return states.getOrDefault(eventId, State.UNSEEN);
    }

    public int deliveryCount(String eventId) {
        AtomicInteger value = deliveries.get(eventId);
        return value == null ? 0 : value.get();
    }

    public int effectCount(String eventId) {
        AtomicInteger value = effects.get(eventId);
        return value == null ? 0 : value.get();
    }
}
~~~

**Vì sao dùng concurrent collections?** JUnit thread đọc `states` trong khi RabbitMQ listener thread ghi. `HashMap` thường không cung cấp memory visibility/thread safety cần thiết. `ConcurrentHashMap` và `AtomicInteger` giúp test có cơ sở quan sát updates giữa threads.

**Vì sao `handledIds.add(eventId)`?** Cùng ID có thể được deliver nhiều lần (test gửi duplicate cố ý, hoặc broker redeliver). `Set.add` chỉ trả `true` cho lần đầu; demo chỉ tăng `effects` một lần. Điều này minh họa **idempotency theo event ID**.

**Giới hạn nghiêm trọng:** Set/in-memory ledger này **không** phải idempotency production. Nếu process chết sau khi đánh dấu handled nhưng trước khi ghi DB, hoặc có nhiều JVM instances, trạng thái không atomic/durable. Production nên dùng unique constraint/idempotency key trong database, inbox table, transaction hoặc outbox pattern phù hợp.

**Định nghĩa “deliveryCount”:** số lần method `record` được gọi trong demo. Nó không phải số lần broker quyết định deliver cho mọi consumer hoặc số lần producer gửi; chỉ quan sát những delivery đã đi đến business listener này.

### `OrderEventListener.java`: consumer chạy từ broker

~~~java
package com.example.messaging;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    private final ProcessingLedger ledger;

    public OrderEventListener(ProcessingLedger ledger) {
        this.ledger = ledger;
    }

    @RabbitListener(queues = "${demo.orders.queue}")
    public void receive(String payload) {
        int separator = payload.indexOf('|');

        if (separator <= 0
                || separator == payload.length() - 1) {
            throw new IllegalArgumentException(
                    "Expected TYPE|eventId");
        }

        String type = payload.substring(0, separator);
        String id = payload.substring(separator + 1);

        switch (type) {
            case "COMPLETE" ->
                    ledger.record(
                        id, ProcessingLedger.State.COMPLETED);

            case "DECLINE" ->
                    ledger.record(
                        id, ProcessingLedger.State.DECLINED);

            default ->
                    throw new IllegalArgumentException(
                        "Unknown event type: " + type);
        }
    }
}
~~~

Message payload được giữ **String** để tránh thêm JSON converter/schema vào bài Awaitility. `RabbitTemplate.convertAndSend` và `@RabbitListener(String)` sử dụng message converter phù hợp với string payload. Nếu production dùng JSON/Avro/Protobuf, hãy test serialization/deserialization riêng và dùng converters tương ứng.

**Trạng thái `DECLINED` trong demo là từ chối ở mức nghiệp vụ** — listener **xử lý thành công message** rồi ghi `State.DECLINED` và return bình thường. Nó **không phải lỗi kết nối broker**, không phải exception của listener, không phải message tự vào DLQ.

Trong Spring AMQP, listener container ở mode `AUTO` thường ACK khi listener return thành công; khi listener throw exception, requeue/retry/DLQ phụ thuộc cấu hình. Đừng suy luận có ACK chỉ vì ledger đã cập nhật — tại thời điểm Awaitility quan sát state, ACK có thể còn đang được gửi.

### `OrderPublisher.java`: producer thật qua RabbitTemplate

~~~java
package com.example.messaging;

import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final RabbitTemplate rabbitTemplate;
    private final Queue ordersQueue;

    public OrderPublisher(
            RabbitTemplate rabbitTemplate,
            Queue ordersQueue) {

        this.rabbitTemplate = rabbitTemplate;
        this.ordersQueue = ordersQueue;
    }

    public void publish(String type, String eventId) {
        String payload = type + "|" + eventId;

        // Exchange rỗng: AMQP default exchange.
        // Routing key trùng chính xác tên queue.
        rabbitTemplate.convertAndSend(
                "", ordersQueue.getName(), payload);
    }
}
~~~

Producer gửi vào **default exchange** của RabbitMQ với routing key là queue name. Khi queue đã được declare, RabbitMQ có default binding phù hợp. Đây là đường publish ngắn gọn cho bài, **không** thay thế cách quản lý exchanges/routing/bindings của production.

**`convertAndSend` return không chứng minh listener hoàn tất.** Nếu cần kiểm broker accept/routing, hãy viết một publisher confirms/returns test khác. Bài này tập trung **business state sau khi listener xử lý message**.

## 7. Bộ integration tests thật với RabbitMQ và Awaitility

**`src/test/java/com/example/messaging/RabbitAsyncAwaitTest.java`**

~~~java
package com.example.messaging;

import java.time.Duration;
import java.util.UUID;

import org.awaitility.core.ConditionTimeoutException;
import org.awaitility.core.TerminalFailureException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.amqp.core.AmqpAdmin;
import org.springframework.amqp.core.Queue;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(
    classes = MessagingApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.rabbitmq.listener.simple.acknowledge-mode=auto",
        "spring.rabbitmq.listener.simple.default-requeue-rejected=false"
    })
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class RabbitAsyncAwaitTest {

    @Container
    static final RabbitMQContainer broker =
            new RabbitMQContainer(
                    "rabbitmq:3.13-management-alpine")
                .withAdminUser("test_user")
                .withAdminPassword("test_password");

    private static final String QUEUE_NAME =
            "await.orders." +
            UUID.randomUUID().toString().replace("-", "");

    @DynamicPropertySource
    static void rabbitConnection(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host",
                broker::getHost);
        registry.add("spring.rabbitmq.port",
                broker::getAmqpPort);
        registry.add("spring.rabbitmq.username",
                broker::getAdminUsername);
        registry.add("spring.rabbitmq.password",
                broker::getAdminPassword);
        registry.add("demo.orders.queue",
                () -> QUEUE_NAME);
    }

    @Autowired
    private OrderPublisher publisher;

    @Autowired
    private ProcessingLedger ledger;

    @Autowired
    private Queue ordersQueue;

    @Autowired
    private AmqpAdmin admin;

    @BeforeEach
    void ensureQueueExistsBeforePublish() {
        admin.declareQueue(ordersQueue);
    }

    private String newEventId() {
        return "evt-" + UUID.randomUUID();
    }

    @Test
    void eventuallyCompletesMessageWithBoundedAwait() {
        String eventId = newEventId();

        assertEquals(
                ProcessingLedger.State.UNSEEN,
                ledger.state(eventId));

        publisher.publish("COMPLETE", eventId);

        await()
            .alias("complete event " + eventId)
            .atMost(Duration.ofSeconds(10))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() -> {
                assertEquals(
                    ProcessingLedger.State.COMPLETED,
                    ledger.state(eventId));
                assertEquals(1,
                    ledger.effectCount(eventId));
            });
    }

    @Test
    void businessDeclineIsACompletedConsumerOutcome() {
        String eventId = newEventId();

        publisher.publish("DECLINE", eventId);

        await()
            .alias("decline event " + eventId)
            .atMost(Duration.ofSeconds(10))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() -> {
                assertEquals(
                    ProcessingLedger.State.DECLINED,
                    ledger.state(eventId));
                assertEquals(1,
                    ledger.effectCount(eventId));
            });
    }

    @Test
    void duplicateMessagesHaveOnlyOneLogicalEffect() {
        String eventId = newEventId();

        publisher.publish("COMPLETE", eventId);
        publisher.publish("COMPLETE", eventId);

        await()
            .alias("both deliveries for " + eventId)
            .atMost(Duration.ofSeconds(10))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() -> {
                assertTrue(
                    ledger.deliveryCount(eventId) >= 2);
                assertEquals(1,
                    ledger.effectCount(eventId));
                assertEquals(
                    ProcessingLedger.State.COMPLETED,
                    ledger.state(eventId));
            });
    }

    @Test
    void anotherEventIdRemainsUnseenDuringObservationWindow() {
        String known = newEventId();
        String unrelated = newEventId();

        publisher.publish("COMPLETE", known);

        await()
            .atMost(Duration.ofSeconds(10))
            .until(() ->
                ledger.state(known)
                    == ProcessingLedger.State.COMPLETED);

        // Một lần assert ngay sau publish chưa đủ.
        // Chỉ chứng minh unrelated giữ nguyên trong 350 ms.
        await()
            .alias("unrelated event stays untouched")
            .during(Duration.ofMillis(350))
            .atMost(Duration.ofSeconds(3))
            .pollInterval(Duration.ofMillis(50))
            .until(() ->
                ledger.state(unrelated)
                    == ProcessingLedger.State.UNSEEN);
    }

    @Test
    void terminalDeclineCanAbortAWaitImmediately() {
        String eventId = newEventId();
        publisher.publish("DECLINE", eventId);

        TerminalFailureException failure = assertThrows(
            TerminalFailureException.class,
            () -> await()
                .alias("event should complete")
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(50))
                .failFast(
                    "DECLINED is terminal",
                    () -> ledger.state(eventId)
                        == ProcessingLedger.State.DECLINED)
                .until(() ->
                    ledger.state(eventId)
                        == ProcessingLedger.State.COMPLETED));

        assertTrue(failure.getMessage()
                .contains("DECLINED is terminal"));
    }

    @Test
    void unpublishedEventTimesOutWithinFiniteDeadline() {
        String eventId = newEventId();

        ConditionTimeoutException failure = assertThrows(
            ConditionTimeoutException.class,
            () -> await()
                .alias("no event was published")
                .atMost(Duration.ofMillis(350))
                .pollInterval(Duration.ofMillis(50))
                .until(() ->
                    ledger.state(eventId)
                        == ProcessingLedger.State.COMPLETED));

        assertNotNull(failure);
        assertEquals(
            ProcessingLedger.State.UNSEEN,
            ledger.state(eventId));
    }
}
~~~

### Test 1: Positive eventual processing

Trình tự:

1. Tạo `eventId` mới và kiểm trạng thái UNSEEN.
2. Gửi `COMPLETE|eventId` bằng **RabbitTemplate thật** vào RabbitMQ.
3. Listener thread nhận payload và gọi `ledger.record`.
4. Awaitility poll condition, tối đa 10 giây.
5. Khi `state == COMPLETED` **và** `effectCount == 1` thì test pass ngay.
6. Nếu không hoàn tất trước deadline thì `ConditionTimeoutException` khiến test fail.

Khác với sleep cố định, test kết thúc khi **state đạt hợp đồng**. Nếu RabbitMQ hoặc listener mất kết nối, condition không tự được “coi là đúng”.

### Test 2: Business rejection không phải infrastructure failure

Event `DECLINE` được listener xử lý và ghi `State.DECLINED`, đồng thời `effectCount == 1`. Bài test có thể xác minh một trường hợp “đơn bị từ chối” là **kết quả nghiệp vụ hợp lệ**, khác với consumer throw exception/poison message hoặc broker failure.

Nếu nghiệp vụ yêu cầu event bị từ chối phải vào DLQ, bạn cần thiết kế listener/error handling khác, và kiểm DLQ riêng. Đừng gọi mọi trạng thái DECLINED là “failed message”; có hệ thống từ chối là outcome bình thường.

### Test 3: At-least-once delivery và idempotency

Ta chủ động gửi **cùng eventId hai lần**. Kết quả:

- `deliveryCount(eventId) >= 2` chứng minh listener đã ghi nhận ít nhất hai delivery của event đó.
- `effectCount(eventId) == 1` chứng minh **demo logic** chỉ tính một logical effect cho key.
- `state(eventId) == COMPLETED` chứng minh kết quả cuối là hoàn tất.

Dùng `>=2` thay vì `==2` vì broker/consumer có thể redeliver thêm trong một số failure conditions. Test này chưa chứng minh idempotency multi-process/durable transaction; để làm điều đó, cần database unique constraints hoặc inbox/outbox integration tests.

**Chú ý race:** Concurrent listener có thể tăng `deliveryCount` trước khi `state` được lưu. Vì vậy block `untilAsserted` kiểm **cả ba** và thử lại cho tới khi chúng đồng thời đúng. Không tách thành “await count >=2” rồi assert effect ngay lập tức nếu effect vẫn đang cập nhật.

### Test 4: Quan sát điều kiện phủ định trong một khoảng thời gian

`unrelated` chưa được publish. Một `assertEquals(UNSEEN, ...)` ngay đầu test là đúng nhưng không kiểm **quãng thời gian**. `during(350ms)` kiểm condition được giữ trong 350 ms, với deadline 3 giây.

**Giới hạn logic:** Không có test hữu hạn nào chứng minh tuyệt đối một event sẽ không bao giờ được tạo trong tương lai. Nó chỉ bảo vệ khoảng thời gian quan sát đã xác định. Nếu yêu cầu là “không publish trước deadline 1 phút”, bạn cần thời gian quan sát đúng contract (và chấp nhận chi phí test), hoặc một contract/test seam kiểm scheduling policy trực tiếp.

### Test 5: Fail-fast khi state đã terminal

Test tạo `DECLINE` nhưng cố chờ `COMPLETED`. Vì `DECLINED` được coi là trạng thái terminal trong demo, `failFast` cần ném `TerminalFailureException` **trước khi hết deadline 10 giây**, khi trạng thái DECLINED được quan sát.

Test dùng `assertThrows(TerminalFailureException.class,...)` để **minh họa và xác nhận cơ chế fail-fast**. Trong business success test bình thường, exception này **không được bắt để coi là thành công**; nó nên làm test fail và báo nguyên nhân rõ.

### Test 6: Timeout là một kết quả của công cụ chờ, không phải lỗi broker giả

Test không publish event. Condition `state == COMPLETED` chắc chắn không xảy ra với eventId riêng. Awaitility throw `ConditionTimeoutException` sau khoảng deadline hữu hạn, và `assertThrows` biến đây thành một unit/integration test của **cơ chế chờ**.

Khi kiểm nghiệp vụ thực, **không bọc await bằng `assertThrows`** chỉ để suite xanh nếu consumer không xử lý. Ở các test production, timeout thường phải **fail test**, còn expected-timeout chỉ phù hợp với tình huống âm tính hoặc xác minh helper.

## 8. Kết quả dự kiến và cách chạy

Project có **6 phương thức `@Test`** trong `RabbitAsyncAwaitTest`. Đây là số test chính thức; `@BeforeEach` và helper `newEventId` không được tính là test methods.

| Test method | Điều kiện chờ | Kết quả mong đợi |
| --- | --- | --- |
| `eventuallyCompletesMessageWithBoundedAwait` | COMPLETED + effect=1 | PASS sớm khi xử lý xong |
| `businessDeclineIsACompletedConsumerOutcome` | DECLINED + effect=1 | PASS khi có business decline |
| `duplicateMessagesHaveOnlyOneLogicalEffect` | deliveries>=2 + effects=1 | PASS khi demo idempotency hoạt động |
| `anotherEventIdRemainsUnseenDuringObservationWindow` | ID khác giữ UNSEEN 350 ms | PASS trong observation window |
| `terminalDeclineCanAbortAWaitImmediately` | Fail-fast DECLINED khi chờ COMPLETED | PASS vì `TerminalFailureException` được kỳ vọng |
| `unpublishedEventTimesOutWithinFiniteDeadline` | Không publish → deadline 350 ms | PASS vì timeout được kỳ vọng và kiểm đúng |

Chạy từ project root với Gradle Wrapper và Docker/compatible container runtime:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy riêng class:

~~~bash
./gradlew test --tests 'com.example.messaging.RabbitAsyncAwaitTest'
~~~

Báo cáo Gradle thông thường:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    └── TEST-com.example.messaging.RabbitAsyncAwaitTest.xml
~~~

Khi JDK17, Boot3.3.5, Testcontainers1.x, Docker và image RabbitMQ tương thích, **kỳ vọng 6 tests pass**. Đây là **dự đoán từ code và semantics**, không phải tuyên bố đã chạy Gradle/Testcontainers trên máy người học. Startup RabbitMQ phụ thuộc máy/CI; log broker, port mapping và timings không cố định.

Nếu Gradle báo `UP-TO-DATE` hoặc `FROM-CACHE`, có thể test task được reuse. Muốn buộc chạy lại để chẩn đoán:

~~~bash
./gradlew test --rerun-tasks
~~~

Nếu chưa có Wrapper nhưng đã cài Gradle tương thích:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Lưu Wrapper scripts/JAR theo chính sách repository. Không tự nâng Gradle/Boot/test library versions của dự án thật chỉ vì tutorial dùng 3.3.5.

### Khi Docker không sẵn sàng

Testcontainers có thể fail với thông báo không tìm được Docker environment hoặc image pull failure. Đó là **lỗi hạ tầng**, không chứng minh business logic sai. Tránh “khắc phục” bằng cách bỏ broker integration tests hoặc chuyển sang mock rồi báo đã kiểm end-to-end Messaging. Thay vào đó, cấu hình runner có container runtime, quyền socket, image registry và network đúng.

## 9. Mốc nào đủ để nói “đã xử lý xong”?

Một hệ thống thường có nhiều định nghĩa **done**:

### A. Listener method đã chạy

Ví dụ test có `AtomicInteger` tăng tại đầu listener. Điều này chứng minh **đã vào handler**, chưa chứng minh validate/persist/commit thành công. Nếu listener throw exception sau khi tăng counter, test có thể xanh giả.

### B. Listener đã return thành công

Trong mode `AUTO` của Spring AMQP, listener return bình thường thường dẫn đến broker ACK do container quản lý. Tuy nhiên một assertion trên in-memory state được cập nhật **bên trong listener** có thể pass **trước khi listener return/ACK thực sự hoàn tất**.

### C. Business database commit thành công

Nếu listener gọi `@Transactional` service với `REQUIRED`, transaction thường commit khi service method return qua proxy; test nên đọc row từ **separate read-only transaction/connection** sau commit. Với JPA, `save`/`flush` bên trong transaction không tự chứng minh commit.

### D. Outbox được ghi và event downstream được gửi

Nếu workflow có các giai đoạn, trạng thái ở một service chỉ chứng minh một stage. Có thể cần chờ trạng thái tổng hợp gồm **record committed + outbox published + consumer projection updated**. Hợp đồng nào bắt buộc thì assert đủ hợp đồng đó.

### E. Message đã được ACK hoặc offset committed

Broker ACK/offset commit là một tín hiệu riêng. Nếu bạn cần kiểm chính xác ACK/offset behavior, phải có một test sử dụng broker management/client controls tương ứng, không chỉ quan sát state trong JVM.

### F. Đã có side effect ở hệ ngoài

Với email, payment gateway, HTTP partner, S3/file/object storage, cần stub/spy *đúng boundary* và kiểm sự kiện thực. Một row status trong DB có thể được ghi trước khi external call thành công.

**Lời khuyên:** Đặt tên method test theo **observable outcome**: `eventuallyUpdatesOrderProjection` tốt hơn `consumerReceivedMessage`. Naming giúp reviewer biết bằng chứng test đang bảo vệ điều gì.

## 10. Test với database thật thay cho in-memory ledger

Trong ứng dụng có Spring Data JPA/JDBC, điều kiện mong muốn thường là:

~~~java
publisher.publish(new OrderPaidEvent(orderId));

await()
    .alias("Order " + orderId + " committed as PAID")
    .atMost(Duration.ofSeconds(12))
    .pollInterval(Duration.ofMillis(200))
    .untilAsserted(() -> {
        OrderEntity order =
                orderRepository.findById(orderId).orElseThrow();
        assertEquals(OrderStatus.PAID, order.getStatus());
        assertEquals(1L,
                paymentOutboxRepository.countByOrderId(orderId));
    });
~~~

**Đây là snippet kiến trúc, không độc lập runnable**: project mẫu chỉ có `ProcessingLedger`, không có `OrderEntity`/JPA repositories. Với test DB thật:

- `findById` cần quan sát commit mới, không query trong transaction snapshot cũ.
- Nếu test class gắn `@Transactional`, việc JUnit giữ transaction riêng có thể che state mới hoặc gây lock.
- Không dùng EntityManager đã cache entity từ trước khi message xử lý.
- Nếu cần, clear persistence context, dùng transaction `REQUIRES_NEW` read-only phù hợp hoặc truy vấn JDBC connection mới.
- Query DB/read model phải trỏ đúng datasource/tenant và được cô lập với test khác.
- Khi ứng dụng có replica lag, deadline phải phản ánh consistency promise thực.

### Lỗi phổ biến với `@Transactional` trên JUnit test

~~~java
@SpringBootTest
@Transactional
class AsyncMessagingTest {
    // Listener chạy trên thread khác.
}
~~~

Transaction do Spring TestContext quản lý trên test thread **không lan tự động** sang Rabbit listener thread. Nếu test mở và giữ một transaction chưa commit rồi publish event chứa ID record mới, listener thread có thể **không nhìn thấy row** do isolation; nó sẽ retry/fail. Test sleep 10 giây vẫn không sửa được một transaction chưa commit.

Cách thiết kế đúng thường là:

1. Tạo fixture trong transaction đã commit trước khi publish, hoặc dùng `TransactionTemplate` commit chủ động.
2. Publish message sau khi fixture sẵn sàng cho listener thread.
3. Chờ database state cuối qua một connection/transaction riêng.
4. Cleanup dữ liệu đã commit sau test bằng transaction thực sự commit.
5. Không mặc định test-managed rollback sẽ xóa dữ liệu mà listener thread đã commit.

### Khi cần tạo dữ liệu đầu vào trước test

Một kỹ thuật là `@BeforeTransaction` để chuẩn bị dữ liệu đã commit khi test class transactional; hoặc dùng `TransactionTemplate` trong một test không `@Transactional`. Nhưng cần hiểu các transaction boundaries và thiết kế cleanup — không phải cứ gắn `@BeforeEach` vào transactional test thì row sẽ thấy được từ listener thread.

## 11. Điều kiện tốt cho retry, DLQ và poison messages

Trong thực tế, consumer không phải lúc nào cũng xử lý thành công lần đầu. Mô hình:

~~~text
NEW -> ENQUEUED -> PROCESSING
                       |
                       +-- COMPLETED
                       |
                       +-- RETRYING -> PROCESSING
                       |
                       +-- DEAD_LETTERED / FAILED_FINAL
~~~

Nếu hợp đồng cho phép retry, đừng `failFast` chỉ vì thấy state `RETRYING` hoặc lỗi tạm thời. Chỉ fail fast khi thấy **trạng thái thực sự terminal**, ví dụ DEAD_LETTERED mà không có recovery tự động trong test.

### Chờ thành công với fail-fast

~~~java
await()
    .alias("event " + eventId + " reaches terminal outcome")
    .atMost(Duration.ofSeconds(15))
    .failFast(
        "event dead-lettered",
        () -> statusRepository.status(eventId)
                == Status.DEAD_LETTERED)
    .untilAsserted(() ->
        assertEquals(
            Status.COMPLETED,
            statusRepository.status(eventId)));
~~~

**Snippet minh họa**; `statusRepository`/`Status` phải được định nghĩa trong hệ thống thực. Khi fail-fast, test cung cấp thông tin trực tiếp về lý do không thể thành công, thay vì chỉ “condition timed out”.

### Kiểm DLQ

Một test DLQ có thể:

- Gửi message cố ý invalid với một eventId riêng.
- Cấu hình consumer reject/no-requeue hoặc giới hạn retries đúng như production.
- Chờ message xuất hiện ở DLQ hoặc persistence error state có correlation ID.
- Assert retry count, metadata, original payload và error reason theo contract.
- Cleanup queue/messages test, không đọc hoặc xóa broker production.

**Đừng dùng `queue.size()==0` làm bằng chứng DLQ xử lý xong**. Poison message có thể được chuyển sang DLQ nên main queue trống nhưng workflow vẫn FAILED.

### Spring AMQP ACK mặc định và requeue

Với Spring AMQP listener containers, `AcknowledgeMode.AUTO` thường ACK khi listener return; nếu listener ném exception, broker requeue hay reject tùy `defaultRequeueRejected`, retry interceptors và error handler. Default behavior có thể retry vô hạn trong cấu hình nhất định nếu không được điều chỉnh.

Project demo đặt `spring.rabbitmq.listener.simple.default-requeue-rejected=false` để tránh vòng requeue vô hạn nếu payload bất hợp lệ. **Nó không tự tạo DLQ**: muốn message được route tới DLQ cần broker topology với dead-letter exchange/binding hoặc policy phù hợp.

Nếu dùng `AcknowledgeMode.MANUAL`, listener phải ACK/NACK đúng delivery tag/channel, và tests cần bảo vệ đường ACK riêng. Không sao chép `AUTO` assertions sang manual-ack app mà không xét transaction/reliability semantics.

## 12. Đừng bỏ qua “polling callback phải thuần quan sát”

Awaitility gọi predicate/assertion nhiều lần. Những việc **không nên** làm trong callback:

~~~java
await().until(() -> {
    publisher.publish("COMPLETE", eventId);
    return repository.status(eventId) == COMPLETED;
});
~~~

Mỗi lần điều kiện chưa đạt, test lại publish một message, làm thay đổi stimulus; kết quả duplicate deliveries và race khó giải thích. Publish **một lần trước await**.

Cũng tránh:

- `repository.deleteAll()` trong condition.
- Tự `Thread.sleep` dài trong condition.
- `listener.process(event)` trực tiếp trong condition.
- Mở JDBC connections không đóng ở mỗi poll.
- Ghi toàn bộ payload/credentials vào logs mỗi 50 ms.
- Gọi một REST endpoint mutate state khi chỉ muốn kiểm trạng thái.
- Gọi `assertThrows` để nuốt những exception quan trọng.
- Tạo mới `EntityManager` không đóng hoặc JDBC resource leak.

Một predicate an toàn nên chỉ đọc state/metrics/test DB và đưa ra kết quả nhanh. Nếu query có latency 2 giây, đừng đặt `pollInterval(10ms)` rồi kỳ vọng tổng thời gian đúng 2 giây — polling overhead/timeout semantics phức tạp hơn.

## 13. Dữ liệu đồng thời và memory visibility

Một vấn đề thường bị bỏ sót:

~~~java
class UnsafeObserver {
    boolean completed;
}
~~~

JUnit thread poll `completed` nhưng worker thread set `completed = true`. Không có `volatile`, lock, atomic hoặc một concurrent collection, Java Memory Model **không bảo đảm** thread quan sát update kịp thời. Test có thể fail dù worker đã set value.

Các lựa chọn phù hợp:

- `AtomicBoolean` hoặc `AtomicReference<State>`.
- `volatile` khi chỉ cần visibility của một value độc lập.
- `ConcurrentHashMap`/`ConcurrentMap` và `AtomicInteger`.
- `CountDownLatch` để signaling có happens-before theo API.
- Database transactions có isolation/commit semantics.
- Message queues và thread-safe observability collectors.

`Awaitility` **không tự làm biến Java bất kỳ thread-safe**. Nó cung cấp polling/wait API; ứng dụng/test phải bảo đảm synchronization/visibility của trạng thái được quan sát.

### Nhiều fields phải nhất quán

Nếu listener ghi:

~~~java
status = COMPLETED;
effects.incrementAndGet();
~~~

test poll có thể quan sát `status == COMPLETED` **trước** khi `effects == 1`. Vì vậy `untilAsserted` nên kiểm cả hai sau cùng; hoặc mô hình production cập nhật các trường trong cùng database transaction. Không giả định hai ConcurrentMap updates riêng lẻ có atomic snapshot tự nhiên.

### Dùng `AtomicReference` trong unit test

~~~java
AtomicReference<State> observed =
        new AtomicReference<>(State.PENDING);

someExecutor.submit(() -> observed.set(State.COMPLETED));

await()
    .atMost(Duration.ofSeconds(2))
    .until(() -> observed.get() == State.COMPLETED);
~~~

**Snippet ngắn**, cần `State`/`someExecutor` và cleanup executor. Nó minh họa visibility nhưng **không kiểm broker**. Không gọi mọi test có worker thread là messaging integration test.

## 14. Đếm đúng: processed, delivered, acknowledged và side effects

Một số tests dùng số đếm:

~~~java
assertEquals(1, processedCount.get());
~~~

Điều này chưa đủ nếu:

- Counter tăng ngay đầu listener rồi business logic lỗi.
- Event được deliver hai lần, nhưng business side effect vẫn chỉ một lần.
- Event retry và cuối cùng thành công ở lần 3; delivery count sẽ 3 dù business effect1.
- Listener hoàn tất nhưng ack bị mất, broker redeliver sau đó.
- Test đọc counter dùng chung giữa các methods/classes.

Bài demo tách:

- `deliveryCount(eventId)`: listener đã gọi `record` bao nhiêu lần.
- `effectCount(eventId)`: logic demo thực hiện tác động idempotent bao nhiêu lần.
- `state(eventId)`: kết quả nghiệp vụ cuối.

Trong ứng dụng thật, nên chọn **business artifact** làm tiêu chí: một unique DB row, outbox event, settlement transaction hoặc email sandbox request; counter trong JVM chỉ giúp debug.

### Cảnh báo đúng một lần

Messaging thường cho **at-least-once delivery**. Từ việc test thấy `effectCount==1` trên một event duplicate, đừng suy ra broker/provider có exactly-once end-to-end. Cần xác định:

1. Producer có khả năng gửi lại không?
2. Broker có khả năng redeliver sau mất ACK không?
3. Nhiều consumers có cùng event ID không?
4. Consumer dedupe key lưu ở đâu?
5. DB write và ACK có atomic không?
6. Outbox/inbox/transaction có chống partial failure không?

Chính sách **idempotent consumer** thường thực tế hơn lời hứa “broker chỉ giao message một lần”.

## 15. `CountDownLatch`, `CompletableFuture`, Mockito và Awaitility

### `CountDownLatch`

~~~java
CountDownLatch latch = new CountDownLatch(1);

// Listener sau khi xử lý:
latch.countDown();

// Test:
assertTrue(latch.await(5, TimeUnit.SECONDS));
~~~

Snippet giả định test và listener chia sẻ **cùng latch instance** hợp lệ. Latch giúp chờ signal, nhưng có nhược điểm:

- Nếu listener gọi `countDown()` **trước khi DB commit**, latch pass nhưng dữ liệu chưa committed.
- Nếu signal bị mất do test reset latch sau publish, test timeout.
- Dễ rò state giữa methods nếu latch static dùng chung.
- Không thay được assertions chi tiết về trạng thái/business effect.
- Latch có count cố định; multi-stage event workflow cần thiết kế rõ.

Latch phù hợp khi **chính signal ấy là contract** và được phát ở đúng thời điểm. Với repository/read-model, Awaitility polling điều kiện thường diễn đạt tự nhiên hơn.

### `CompletableFuture`

~~~java
CompletableFuture<Result> future = service.submitAsync(command);

Result result = future.get(5, TimeUnit.SECONDS);
assertEquals(Result.OK, result);
~~~

Snippet minh họa, không có `service`/`Result` runnable trong lab. Future có timeout rõ và là lựa chọn tốt nếu API **trả về future thể hiện chính completion**. Nhưng producer gửi message đến broker thường return mà **không trả future** cho việc consumer xử lý xong; `CompletableFuture` của send không thể tự chứng minh downstream DB state.

### Mockito `timeout()`

~~~java
verify(notificationAdapter, timeout(5000))
    .notify(eq(orderId));
~~~

Dùng được cho một interaction cần verify trong unit/integration seam có spy. Tuy nhiên:

- Lệnh gọi mock xảy ra có thể chưa đồng nghĩa transaction commit.
- Spy bean có thể làm test setup phức tạp và thay class proxy.
- Không chứng minh RabbitMQ/Kafka hoạt động nếu test không gửi broker event thật.
- Tên annotation Boot mới/khác nhau theo version (`@MockBean`, `@MockitoBean`) cần kiểm riêng, không nhập nhằng từ tài liệu Boot 4 vào Boot 3.3.

### Awaitility

Chọn khi trạng thái mong muốn là **eventually observable**, có API read-only, có thể poll một cách an toàn. Phù hợp DB query, cache, HTTP GET read model, in-memory concurrent state, message count có scope.

### Reactor `StepVerifier`

Nếu code trả `Mono`/`Flux`, dùng `StepVerifier` kiểm stream signals. Nhưng một `Mono<Void>` producer publish xong không tự biểu thị consumer đã commit. Để kiểm **downstream eventual state**, vẫn có thể cần Awaitility trên repository hoặc stream/tracing thích hợp.

## 16. Kafka và JMS: nguyên tắc chung, semantics riêng

### Kafka

Với `@KafkaListener` và `KafkaTemplate`, test có thể:

1. Tạo topic/test broker bằng `@EmbeddedKafka` hoặc Kafka Testcontainers.
2. Publish event có `eventId` vào topic.
3. Chờ business projection/repository tới status mong muốn.
4. Kiểm consumer group/offset/retry/DLT riêng khi đó là contract.

Bẫy Kafka:

- Offset commit và database commit không nhất thiết atomic.
- Kafka partition ordering chỉ bảo đảm trong một partition, không bảo đảm mọi consumers/global order.
- Test dùng chung consumer group có thể làm một test “ăn” event của test khác.
- Consumer có thể được assign partition muộn; timeout bao gồm startup/join latency.
- Retry topics và DLT có thể làm main topic consumer tiến độ mà business chưa done.
- `KafkaTestUtils` giúp đọc records từ test consumer, nhưng consumer đọc thấy event **không đồng nghĩa listener khác hoàn tất**.

Snippet kiến trúc:

~~~java
kafkaTemplate.send("order-events", orderId, event);

await()
    .atMost(Duration.ofSeconds(15))
    .untilAsserted(() ->
        assertEquals("DONE",
            readModel.findStatus(orderId)));
~~~

Đây là snippet không độc lập; cần Kafka dependencies, topic và read model đã định nghĩa. Với Kafka, không tùy tiện áp dụng RabbitMQ `@RabbitListener` ACK semantics sang Kafka offsets.

### JMS

Với `@JmsListener` và `JmsTemplate`, kiến trúc chờ condition giống nhau, nhưng ACK modes, transacted sessions và redelivery policies thuộc JMS provider. Một test JMS gửi message xong vẫn phải chờ **business outcome** nếu xử lý ở listener thread. Kết quả “queue empty” cũng chưa bảo đảm external side effects đã commit.

### Spring application events

`@Async @EventListener` hoặc `@TransactionalEventListener` có thể chạy bất đồng bộ trong JVM mà **không cần broker**. Awaitility vẫn hữu ích cho eventual state, nhưng không nên gọi đó là RabbitMQ/Kafka integration coverage nếu không có broker thật.

## 17. Thời hạn chờ: chọn bao nhiêu là đủ?

Đặt `atMost(Duration.ofSeconds(10))` không phải một con số thần kỳ. Deadline nên tính từ:

- Hệ thống có message delivery/processing SLA bao nhiêu?
- Startup container/listener đã diễn ra **trước** hay **sau** lúc bắt đầu await?
- CI có CPU/IO scheduling chậm hơn laptop không?
- Có retry/backoff được phép, ví dụ 3 attempts x 2 s?
- DB commit/projection lag điển hình là bao lâu?
- Bao nhiêu tests có thể chạy parallel và tranh tài nguyên?
- Một test chậm được cho phép tối đa bao lâu trước khi báo lỗi thật?

Ví dụ:

~~~text
Event processing budget trong test:
  broker dispatch + scheduling  < 1.0 s
  business logic               < 0.5 s
  retry/backoff (nếu có)       < 4.0 s
  DB commit/read model lag     < 1.0 s
  CI jitter allowance          < 2.0 s
  ------------------------------------
  atMost được chọn             = 9-10 s
~~~

Con số chỉ minh họa cách lập budget, **không phải SLA chung cho RabbitMQ**. Test production nên đo baseline/percentiles và đặt threshold có lý do.

### Deadline và polling frequency độc lập

Một timeout 10 s với poll interval 100 ms tạo tối đa khoảng 100 lần đánh giá (thực tế phụ thuộc poll delay, callback duration và scheduling). Nếu predicate là DB query nặng mất 500 ms, đặt poll 10 ms không làm test nhanh hơn tương ứng; nó có thể tăng load, pool contention và flakiness.

### Không tăng timeout vô hạn

Nếu một test fail vì consumer không được khởi động, queue name sai hoặc broker không route, tăng `atMost` từ 10 s lên 60 s chỉ trì hoãn thất bại. Trước khi tăng deadline, phải xác minh lỗi gốc:

- Producer có publish đúng exchange/topic/routing key?
- Queue/topic có thực sự tồn tại?
- Listener container có running/assigned?
- Conversion/validation có throw?
- Message có bị requeue hoặc DLQ?
- Test đang poll đúng datasource/tenant/event ID?
- Transaction input đã commit để consumer thấy?
- State observer có thread safety?
- Có resource starvation/connection pool exhaustion?

## 18. Quản lý lifecycle của RabbitMQ Testcontainers

Trong runnable project:

- `@Container static RabbitMQContainer broker`: container khởi động theo **class scope** bởi JUnit Testcontainers extension.
- `@DynamicPropertySource`: đăng ký host, mapped AMQP port, username/password và queue name vào Spring Environment.
- `@SpringBootTest` tạo full ApplicationContext dùng RabbitMQ thật.
- `@DirtiesContext(AFTER_CLASS)`: tránh Spring cache giữ connection factory/listener tới container đã dừng.
- `@BeforeEach`: gọi `AmqpAdmin.declareQueue` trước khi publish.
- Mỗi test sinh `eventId` riêng; không cần reset `ProcessingLedger` toàn cục giữa methods.
- Container tạm và auto-delete queue phù hợp cho demo, không dùng credentials hoặc queue production.

### Vì sao static container?

Một instance `@Container` có thể khởi động/dừng theo mỗi method, trong khi Spring ApplicationContext thường cache qua methods/classes. Nếu container thay host port giữa các methods nhưng `ConnectionFactory` đã được tạo từ port cũ, tests có thể fail random `Connection refused`.

Static container giữ một endpoint ổn định trong phạm vi class. Nếu muốn chia sẻ container qua nhiều classes, phải quản lý **lifetime tương ứng với context cache** và tránh để Testcontainers extension tự stop nó trong lúc context khác còn dùng. Không copy singleton container hack mà không hiểu teardown/parallel semantics.

### Vì sao dynamic queue name?

Nếu mọi CI jobs dùng `orders.queue` trên cùng RabbitMQ broker, chúng có thể trộn messages, người này consume message của test khác. Trong lab, queue name chứa UUID mới theo class để tách tài nguyên. Với Testcontainers mỗi class có broker riêng, đây vẫn là thực hành bảo vệ trước khi chuyển sang shared test broker.

### `@DirtiesContext` không dọn broker thay cho test

`@DirtiesContext` làm Spring TestContext evict cached context. Nó **không tự xóa những message đã commit/delivered**, không thay DLQ cleanup và không dọn database external. Đừng dùng nó làm “magic cleanup” cho mọi side effects.

## 19. Test chạy song song: tránh race và state leakage

Một suite Messaging có thể fail không nhất quán vì:

- Hai test methods dùng cùng eventId/orderId.
- Một test drain queue chung trong khi test khác chờ message của mình.
- Một test reset shared map/counter, làm mất state test khác.
- Shared listener/executor pool bị một test blocking lâu.
- Consumer group/queue name bị trùng.
- Fixture DB được tạo trong test transaction chưa commit.
- Một test stop/restart broker khi context khác vẫn có connection.
- Awaility predicate có side effect hoặc đọc field không thread-safe.
- Polling dùng repository với stale EntityManager cache.

Biện pháp:

1. Sinh **correlation ID** riêng per test.
2. Dùng thread-safe state/DB committed read model.
3. Cô lập broker/queue/topic/consumer group khi có thể.
4. Không reset toàn bộ state nếu tests có thể chạy concurrent.
5. Bảo đảm listener không giữ static mutable global state.
6. Tách business retry, publish retry và test polling — đừng để polling tạo lại stimulus.
7. Với đa consumer, không assert total order nếu broker chỉ bảo đảm order theo partition/queue policy cụ thể.
8. Nếu cần resource lock, dùng JUnit serialization/`@ResourceLock` theo module test, không dựa vào Thread.sleep.
9. Không rò JPA sessions/JDBC connections trong condition.
10. Cleanup resources sau test bằng scoped key, transaction đúng và container teardown.

### Vì sao Awaitility không loại bỏ mọi flakiness?

Awaitility loại bỏ **sleep cố định và early assertion race**, nhưng không thể chữa:

- State observer không thread-safe.
- Hệ thống bị deadlock thật.
- Broker/container bị restart giữa lúc test.
- Producer gửi sai routing key.
- Assertion kiểm sai consumer group/datasource.
- External service lỗi thật.
- Timeout đặt thấp hơn latency hợp lệ của môi trường.
- Business contract không có điểm hoàn tất có thể quan sát.

Nó làm test có **deadline và điều kiện rõ**, nhưng thiết kế integration harness vẫn quyết định chất lượng cuối.

## 20. Error diagnostics: đừng chỉ thấy “condition timed out”

Một log QA hữu ích khi timeout nên có:

~~~text
eventId=evt-...
queue=await.orders.<uuid>
expected=COMPLETED
observedState=UNSEEN / DECLINED / RETRYING / FAILED
deliveryCount=0/1/2...
effectCount=0/1/...
listenerRunning=true/false (nếu có metric)
lastConsumerError=<sanitized type + message>
deadLetterCount=<if available>
elapsedMs=<observed>
~~~

Đây là **mẫu diagnostic**, không phải stdout cố định của project. Không nên log message payload có PII, full credentials, tokens hoặc thông tin khách hàng.

### Assertion có diagnostic bằng `untilAsserted`

~~~java
await()
    .alias("event " + eventId + " eventually completed")
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() -> {
        assertEquals(COMPLETED, ledger.state(eventId),
                "state for eventId=" + eventId);
        assertEquals(1, ledger.effectCount(eventId),
                "unique effect count for " + eventId);
    });
~~~

Snippet có `ledger`/imports trong project. Khi timeout, assertion cuối có thể giúp thấy actual state, không chỉ một boolean false. Tại lúc đọc lỗi, nhớ phân biệt **timeout chờ condition** với **connect timeout đến broker** — chúng thuộc hai tầng khác nhau.

### `ConditionEvaluationListener` cho test khó

Awaitility có condition evaluation listener để log trạng thái sau mỗi poll, phù hợp debug race timing:

~~~java
await()
    .conditionEvaluationListener(
        new ConditionEvaluationLogger())
    .atMost(Duration.ofSeconds(5))
    .until(() -> ledger.state(eventId) == COMPLETED);
~~~

Đây là snippet mở rộng, cần import `org.awaitility.core.ConditionEvaluationLogger` và các biến phù hợp. Không bật log mọi poll trên toàn suite nếu hàng nghìn tests; CI logs sẽ quá lớn. Khi cần, chỉ log event ID và trạng thái đã sanitize.

### Deadline theo trạng thái

Một workflow có nhiều stage có thể dùng:

~~~text
await QUEUED within 3s
await PROCESSING within 5s
await COMPLETED within 15s
~~~

Nhưng nếu trạng thái PROCESSING xuất hiện nhanh rồi mất trước một lần poll, test có thể fail dù workflow đúng. **Không bắt buộc chờ từng transient state** trừ khi contract thực sự yêu cầu khả năng quan sát chúng. Thường chỉ cần chờ **terminal business state**.

## 21. Anti-patterns cần tránh

### Anti-pattern 1: Sleep cố định

~~~java
Thread.sleep(5000);
assertEquals(COMPLETED, status(id));
~~~

Vừa chậm vừa flake. Thay bằng await có deadline và condition.

### Anti-pattern 2: Không có deadline

~~~java
while (status(id) != COMPLETED) {
    // busy wait
}
~~~

Test có thể treo vô hạn và chiếm CPU. Mọi wait của integration test phải hữu hạn.

### Anti-pattern 3: Không dùng ID riêng

~~~java
await().until(() -> totalProcessedCount() > 0);
~~~

Nếu event cũ đã được xử lý từ test trước, test pass ngay dù message hiện tại không được tiêu thụ. Dùng exact correlation ID.

### Anti-pattern 4: Chỉ kiểm QueueDepth 0

~~~java
await().until(() -> brokerQueueSize() == 0);
~~~

Message có thể unacked, failed hoặc route sang DLQ. Queue empty không phải business success.

### Anti-pattern 5: Predicate có side effect

~~~java
await().until(() -> {
    rabbitTemplate.convertAndSend(queue, message);
    return status(id) == COMPLETED;
});
~~~

Mỗi poll publish lại message. Tách publish khỏi chờ.

### Anti-pattern 6: Lạm dụng `ignoreExceptions`

Nếu test ignore mọi exception, một `SQLSyntaxErrorException` lặp lại sẽ bị che thành timeout; debug khó hơn. Chỉ ignore lỗi transient rõ ràng.

### Anti-pattern 7: Dùng flag không volatile

Worker set biến trong thread A, JUnit poll thread B, nhưng không có happens-before. Dùng concurrent collection/atomic/volatile hoặc DB commit.

### Anti-pattern 8: Bắt `ConditionTimeoutException` rồi coi là pass

~~~java
try {
    await().atMost(Duration.ofSeconds(5))
        .until(() -> status(id) == COMPLETED);
} catch (ConditionTimeoutException ignored) {
    // KHÔNG làm thế trong success test.
}
~~~

Đây là **ví dụ sai**, không copy. Test sẽ xanh dù listener không bao giờ xử lý. Chỉ dùng `assertThrows` cho case **cố tình kiểm timeout behavior** như method thứ sáu của lab.

### Anti-pattern 9: Trộn retry ứng dụng và test polling

Awaitility retry **đọc điều kiện**, không tự retry broker publish. Nếu test publisher có retry, consumer có retry, và test callback lại publish, rất khó xác định attempt count. Đặt stimulus một lần và quan sát.

### Anti-pattern 10: Coi listener invocation là DB commit

Nếu listener gọi service `@Transactional` rồi throw trước commit, invocation đã diễn ra nhưng data rollback. Chờ database state committed khi đó là hợp đồng.

### Anti-pattern 11: Transaction fixture chưa commit

JUnit `@Transactional` tạo order row rồi publish message; listener ở thread khác không thấy row; timeout giả. Commit fixture trước khi gửi.

### Anti-pattern 12: Tăng timeout mọi khi test flake

Không tăng 10s lên 120s trước khi kiểm listener startup, routing, DLQ, thread safety, DB isolation, logs. Timeouts phải phục vụ SLA, không che lỗi.

## 22. So sánh kiểm thử HTTP async với Messaging async

Cùng dùng Awaitility nhưng boundary khác:

- HTTP async endpoint trả `202 Accepted` nghĩa server nhận request, có thể chưa xử lý xong.
- Messaging publish return/confirm nghĩa producer/broker đạt mốc riêng.
- Với HTTP `202`, có thể poll `GET /jobs/{id}` đến `SUCCEEDED`.
- Với Messaging, có thể poll database/read model theo event ID đến `COMPLETED`.
- Nếu cả hai hệ thống dùng outbox, cần phân biệt job accepted, event published, consumer processed và projection updated.

Ví dụ API polling (minh họa):

~~~java
submitJob(jobId); // HTTP 202

await()
    .atMost(Duration.ofSeconds(15))
    .pollInterval(Duration.ofMillis(200))
    .untilAsserted(() ->
        assertEquals("SUCCEEDED", api.readStatus(jobId)));
~~~

Mục tiêu không phải "poll luôn là hay nhất": nếu một service trả `CompletionStage` phản ánh chính completion, có thể await future thay vì polling endpoint; nếu là event stream, có thể subscribe và verify event. **Chọn signal tương ứng observable contract**.

## 23. Quy trình chẩn đoán khi test Messaging bị timeout

| Triệu chứng | Khả năng | Hướng xử lý |
| --- | --- | --- |
| Producer publish nhưng event luôn UNSEEN | Sai queue/routing key, listener chưa ready | Xem topology, listener startup, RabbitAdmin declarations |
| Consumer log nhận message nhưng condition sai | Sai eventId/tenant hoặc state observer | Kiểm payload parse/correlation, DB commit visibility |
| Event có state FAILED/DECLINED nhưng test cứ chờ | Đường lỗi terminal | Thêm fail-fast hoặc assert terminal outcome đúng |
| DeliveryCount=1, effectCount=0 | Handler chưa xong hoặc lỗi giữa chừng | Kiểm listener stack trace, transaction |
| DeliveryCount>1, effectCount>1 | Side effect không idempotent | Thêm inbox key/unique constraint trong DB |
| QueueDepth=0 nhưng DB status chưa đúng | Message unacked/in-flight/failed | Poll committed state thay vì queue depth |
| Chạy riêng pass, suite fail | Shared queue, state, container lifetime | Unique IDs/queues, lifecycle, context cache |
| CI fail chậm, laptop pass | Broker startup, CI CPU/IO load | Xem timing metrics; chọn deadline phù hợp |
| Context fail trước test | Docker/broker connection/credentials | Sửa infrastructure; Awaitility chưa được chạy |
| Listener không start vì missing Queue | Queue bean hoặc declaration sai | Khai báo queue đúng tên và flags; admin declare |
| Requeue vô hạn | Listener throw, default requeue | Config retry/dead-letter; không tăng timeout |
| Kafka test fail vì consumer chưa assigned | Consumer group setup/partition assignment | Chờ readiness, dùng isolated group |
| Database test đọc stale data | Transaction snapshot/JPA cache/replica lag | Query committed state trên đúng connection |
| Timeout test pass dù worker chết | Test bắt exception rồi bỏ | Không nuốt ConditionTimeoutException |
| Negative test pass ngay nhưng event đến sau | Chỉ assert một thời điểm | Dùng `during` hoặc kiểm schedule contract |
| Tests tốn nhiều phút | Poll fixed sleeps quá dài | Dùng await kết thúc sớm, cân nhắc scope |
| Polling gây quá tải DB | pollInterval quá nhỏ | Tăng interval, giảm query cost, dùng index/test scope |
| Condition luôn đúng từ data cũ | Không filter theo event ID | Unique correlation key, cleanup fixtures |
| Manual ACK gây redelivery không ngờ | ACK/NACK sai tag hoặc chưa ack | Kiểm ack mode/channel và broker protocol |
| Mockito timeout xanh nhưng broker không chạy | Verify mock invocation chứ không có integration | Chạy broker container thật |
| Test DLQ fail | Chưa cấu hình DLX/binding/policy | Kiểm topology, routing và retry outcome |

### Debug theo thứ tự

1. Xác định chính xác **event ID, producer, queue/topic và consumer group**.
2. Kiểm broker/container có running và connection config đúng.
3. Kiểm publisher có route message đúng exchange/routing key.
4. Kiểm listener container đã start, payload deserialize được.
5. Kiểm listener có exception/requeue/retry/DLQ.
6. Kiểm transaction từ input fixture đã commit trước publish.
7. Kiểm business state cuối được commit và observable từ test.
8. Kiểm correlation ID filter, không đếm event test khác.
9. Kiểm memory visibility hoặc JPA cache staleness.
10. Kiểm deadline/poll frequency so với retry/SLA hợp lệ.
11. Chẩn đoán context caching/parallel test interference.
12. Chỉ khi đã loại trừ vấn đề mới điều chỉnh timeout theo dữ liệu.

## 24. Bài tập thực hành

**Bài A — bỏ Awaitility:** Trong `eventuallyCompletesMessageWithBoundedAwait`, thay await bằng assertion ngay sau publish. Chạy nhiều lần và giải thích race condition. Hoàn nguyên.

**Bài B — sleep cố định:** Thay await bằng `Thread.sleep(3000)` rồi đo suite duration. So sánh với await khi listener xử lý trong vài chục mili giây.

**Bài C — deadline nhỏ:** Đặt `atMost(Duration.ofMillis(1))` cho success test. Quan sát failure và giải thích vì sao deadline không phản ánh scheduling/CI.

**Bài D — alias/diagnostic:** Thêm `alias("order "+eventId)` và nhiều assertions trong `untilAsserted`, quan sát message khi timeout.

**Bài E — correlation:** Thay trạng thái theo `eventId` bằng một `AtomicInteger` tổng, gửi một event cũ từ test khác. Mô tả nguy cơ test pass sai.

**Bài F — duplicate:** Bỏ `handledIds.add(eventId)` và luôn tăng effect. Test duplicate phải fail vì `effectCount` thành 2. Hoàn nguyên.

**Bài G — decline:** Sửa listener khi `DECLINE` trả trạng thái `COMPLETED`. Test business decline phải phát hiện sai logic.

**Bài H — fail-fast:** Trong ca terminal decline, bỏ `failFast`. Test sẽ chờ hết deadline rồi ném `ConditionTimeoutException` thay vì `TerminalFailureException`. Thêm lại để chẩn đoán nhanh.

**Bài I — during:** Đổi negative assertion từ `during(350ms)` thành assert một lần ngay. Giải thích vì sao không kiểm được một khoảng quan sát.

**Bài J — không có publish:** Sửa test expected timeout để publish event thật, rồi quan sát expected `ConditionTimeoutException` không còn đúng. Điều này chứng minh ca âm tính được thiết kế có chủ đích.

**Bài K — RabbitMQ retry:** Tạo một listener branch cố ý throw; cấu hình bounded retries và DLQ trên broker test riêng, assert terminal DLQ state bằng eventId. Không để requeue vô hạn.

**Bài L — JDBC commit:** Thay in-memory ledger bằng Spring Data JDBC/JPA repository; listener cập nhật một row trong transaction. Awaitility query từ connection mới và assert committed state.

**Bài M — @Transactional test:** Tạo fixture order trong test-managed transaction chưa commit rồi publish. Phân tích vì sao consumer thread không nhìn thấy row; thiết kế commit fixture đúng boundary.

**Bài N — Kafka:** Viết một KafkaListener tương ứng với topic Testcontainers, publish event và await projection DB. Không dùng offset commit đơn lẻ làm business success.

**Bài O — CountDownLatch:** Thêm latch vào listener, thử `countDown` ở đầu handler rồi tại cuối handler. Phân tích vị trí nào thực sự thể hiện contract.

**Bài P — điều kiện chuyển tiếp:** Tạo states `QUEUED -> PROCESSING -> COMPLETED` trong demo. Kiểm chỉ terminal COMPLETED để tránh miss các trạng thái xuất hiện ngắn.

**Bài Q — parallel:** Bật JUnit parallel execution, dùng UUID correlation per test. Đảm bảo không reset global ledger/queue trong lúc method khác đang chờ.

**Bài R — observer lỗi:** Đổi `ConcurrentHashMap` thành `HashMap` không đồng bộ trong một bản sao lab, mô tả data race/memory visibility. Không dùng kết quả chạy nhất thời để kết luận HashMap an toàn.

## 25. Checklist code review cho asynchronous Messaging tests

- [ ] Test chờ **business outcome**, không chỉ producer return hoặc queue empty?
- [ ] Mọi `await` đều có `atMost`/deadline hữu hạn và có lý do?
- [ ] Có `pollInterval` hợp lý, không busy polling?
- [ ] Dùng `untilAsserted` khi cần nhiều assertions?
- [ ] Chỉ đọc condition, không publish/mutate state trong polling callback?
- [ ] Mỗi test dùng eventId/orderId/correlation ID riêng?
- [ ] Observer thread-safe hoặc truy vấn database committed state?
- [ ] Không nhầm listener invocation/ACK với business transaction commit?
- [ ] Nếu có retry, timeout bao phủ hợp đồng retry và không quá rộng?
- [ ] Nếu có terminal failure/DLQ, test biết fail fast hoặc kiểm outcome âm tính?
- [ ] Nếu kiểm “không có event”, có observation window/semantics rõ, không khẳng định mãi mãi?
- [ ] Nếu kiểm duplicate delivery, có assertion tác động nghiệp vụ chỉ một lần?
- [ ] Biết broker delivery có thể at-least-once, không hứa exactly-once khi chưa có thiết kế?
- [ ] Fixture DB đã commit trước khi publish cho listener thread khác?
- [ ] Không dùng test-managed `@Transactional` để giả định rollback mọi listener side effects?
- [ ] Broker Testcontainers/queues/consumer groups được tách đúng phạm vi?
- [ ] Spring ApplicationContext cache không giữ connection tới container đã dừng?
- [ ] Có cấu hình retry/requeue/DLQ có giới hạn, không poison-loop?
- [ ] Timeout/failure có diagnostic event ID, state, attempts, queue?
- [ ] Test không nuốt `ConditionTimeoutException` trong success cases?
- [ ] Không log secrets/payload nhạy cảm?
- [ ] CI có Docker/container runtime nếu chạy integration tests?
- [ ] Tests có thể chạy song song mà không reset state/cùng queue của nhau?
- [ ] Đã phân biệt Awaitility poll với ứng dụng retry/publish retry?
- [ ] Assertions phản ánh API/DB/business contract chứ không lấy expected từ chính SUT?
- [ ] Test report chứng minh các JUnit methods thực thi, không chỉ task `UP-TO-DATE`?

## 26. Tài liệu tham khảo chính thức

Bài chọn **Spring Boot 3.3.5/Java 17** để examples có imports/dependencies thống nhất. Tài liệu của Spring AMQP/Awaitility/Testcontainers ở phiên bản mới có thể khác defaults và module naming; kiểm phù hợp với dependency BOM của project đang học.

- [Awaitility — Usage (4.x)](https://github.com/awaitility/awaitility/wiki/Usage): `until`, `untilAsserted`, `atMost`, `during`, `pollInterval`, `failFast` và caveats về thread safety.
- [Awaitility — Java API](https://www.javadoc.io/doc/org.awaitility/awaitility/4.2.2/): ConditionFactory, timeout exceptions và polling.
- [Spring Boot 3.3 — AMQP](https://docs.spring.io/spring-boot/3.3/reference/messaging/amqp.html): RabbitTemplate, `@RabbitListener`, auto-declare queue và listener container factory.
- [Spring AMQP — Asynchronous Consumer](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): Rabbit listener containers, prefetch, concurrency.
- [Spring AMQP — Listener Container Properties](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): `AcknowledgeMode.AUTO/MANUAL/NONE`, requeue, retry và errors.
- [Spring AMQP — RabbitTemplate](https://docs.spring.io/spring-amqp/reference/amqp/template.html): publishing, broker confirms/returns và distinction với downstream consumer processing.
- [Spring AMQP — Enable Rabbit Listeners](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable.html): `@EnableRabbit`, listener endpoint configuration.
- [Testcontainers Java — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/): `RabbitMQContainer`, AMQP port mapping và lifecycle.
- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container`.
- [Spring Framework — DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): host/port động và Spring test contexts.
- [Spring Framework — TestContext Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transaction và rollback giới hạn theo thread.
- [JUnit Jupiter — Assertions](https://docs.junit.org/5.10.2/user-guide/): `assertThrows`, lifecycle và test methods.

**Ghi nhớ:** Với Messaging, điều kiện “producer đã gửi” và “consumer đã hoàn tất nghiệp vụ” khác nhau. Hãy tạo sự kiện có **correlation ID duy nhất**, publish **một lần**, chờ **business state/side effect** bằng `Awaitility.atMost(...).untilAsserted(...)`, và phân biệt rõ các trạng thái retry/terminal failure. Deadline hữu hạn giúp test không treo; polling thích hợp giúp test kết thúc sớm; idempotency/transaction/isolation và diagnostics mới khiến kết quả QA thực sự đáng tin.
