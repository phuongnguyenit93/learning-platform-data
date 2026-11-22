# Kiểm thử thứ tự listener trong Spring Framework Application Events

## 1. Mục tiêu: kiểm tra thứ tự nào, trong điều kiện nào?

Spring cho phép nhiều listener cùng quan tâm đến một event. Chẳng hạn một `OrderPlaced` được gửi tới ba listener:

- `ValidateListener` kiểm tra điều kiện bổ sung;
- `AuditListener` ghi dấu vết;
- `NotificationListener` chuẩn bị thông báo.

Nếu cả ba là `@EventListener` bình thường, chạy bằng multicaster **đồng bộ mặc định**, ứng dụng có thể dùng `@Order` để quyết định **thứ tự gọi listener**. Tuy nhiên, một bộ kiểm thử đúng không nên đánh đồng ba khái niệm:

1. **Thứ tự được Spring chọn và gọi listener** — liên quan tới `@Order`, `Ordered` và registry listener.
2. **Thứ tự công việc thực sự hoàn thành** — có thể khác khi listener chạy `@Async`, có executor hoặc tự tạo tác vụ.
3. **Thứ tự transaction phase** — listener `@TransactionalEventListener` có thể được gọi tại `BEFORE_COMMIT`, `AFTER_COMMIT` hay `AFTER_ROLLBACK`, không phải ngay lúc `publishEvent`.

Bài này hướng dẫn kiểm thử cả ba, với ví dụ **Java 17+ / Spring Framework 6.2** và **JUnit 5**. Quan trọng nhất: viết test dựa trên một hợp đồng được Spring hỗ trợ, không dựa vào thứ tự tình cờ của reflection, tên class, thứ tự component scan hay độ nhanh của thread.

## 2. Quy tắc @Order với event listener đồng bộ

Spring hỗ trợ đặt `@Order` trên method `@EventListener`:

~~~java
@EventListener
@Order(-20)
public void validate(OrderPlaced event) {
    // Listener có độ ưu tiên cao hơn.
}

@EventListener
@Order(0)
public void audit(OrderPlaced event) {
    // Chạy sau listener có order -20, nếu đồng bộ.
}

@EventListener
@Order(20)
public void notifyCustomer(OrderPlaced event) {
    // Chạy sau listener có order 0, nếu đồng bộ.
}
~~~

Đoạn code trên chỉ minh họa annotation và giả định đã có kiểu `OrderPlaced` cùng bean chứa method.

**Giá trị `order` càng nhỏ thì ưu tiên càng cao.** Giá trị âm là hợp lệ. Với những listener cùng loại event, cùng một multicaster mặc định đồng bộ, thứ tự kỳ vọng là:

~~~text
@Order(-20) -> validate
@Order(0)   -> audit
@Order(20)  -> notifyCustomer
~~~

Những điểm cần hiểu đúng:

- Không có `@Order`, listener thường nhận giá trị ưu tiên mặc định tương đương `Ordered.LOWEST_PRECEDENCE`; **không nên kiểm thử thứ tự chính xác** giữa các listener cùng mức mặc định.
- Nếu **hai listener có cùng `order`**, không dựa vào vị trí bean registration hoặc cách reflection tìm method để coi thứ tự giữa chúng là một cam kết ổn định.
- Có thể dùng interface `Ordered` (đặc biệt với listener triển khai `ApplicationListener`) để khai báo độ ưu tiên; với method `@EventListener`, `@Order` là cách trực quan.
- `@Order` quyết định **độ ưu tiên invocation**; không tự bảo đảm transaction commit thành công, không tạo phụ thuộc nghiệp vụ và không chờ một công việc async chạy xong.
- Cơ chế sắp xếp cần được xác nhận trong **cấu hình multicaster thực tế**. Spring mặc định dùng `SimpleApplicationEventMulticaster` đồng bộ; ứng dụng có thể thay bằng multicaster riêng.

**Không nên dùng `@Order` để che một chuỗi phụ thuộc bắt buộc** kiểu “audit phải commit thành công mới được gửi email”. Khi có phụ thuộc như vậy, hãy tổ chức điều phối nghiệp vụ rõ ràng hoặc dùng các bước bền vững; listener vốn thích hợp với các subscriber tương đối độc lập.

## 3. Vì sao nên kiểm thử trên ApplicationContext thật?

Một unit test chỉ gọi lần lượt:

~~~java
validationListener.onOrderPlaced(event);
auditListener.onOrderPlaced(event);
notificationListener.onOrderPlaced(event);
~~~

không kiểm chứng Spring có sắp xếp listener đúng hay không. Nó chỉ kiểm chứng thứ tự mà **test tự gọi**.

Để kiểm thử điều thực sự cần, hãy tạo một `ApplicationContext` có các listener, gọi:

~~~java
context.publishEvent(new OrderPlaced(101L));
~~~

và ghi lại lịch sử invocation vào một collector do test kiểm soát. Điều đó đi qua `ApplicationEventPublisher`, `ApplicationEventMulticaster` và bộ adapter của `@EventListener`.

Một kết quả dễ kiểm tra:

~~~text
validate:101
audit:101
notify:101
~~~

Khi dùng multicaster đồng bộ mặc định, `publishEvent(...)` không trở về cho tới khi các listener đồng bộ xử lý xong (trừ khi có exception ngắt chuỗi). Vì vậy, sau lời gọi publisher, test có thể assert toàn bộ danh sách **mà không cần `Thread.sleep()`**.

Để tránh test nhiễu:

- Đặt event riêng cho test, ví dụ `OrderPlaced`, thay vì gom mọi `ApplicationEvent` vào một listener chung.
- Khởi tạo context mới cho từng test hoặc chủ động reset collector giữa các lần publish.
- Không lẫn event startup như `ContextRefreshedEvent` vào lịch sử cần so sánh.
- Không assert thứ tự của listener **không có mức ưu tiên khác nhau**.
- Không dùng thời gian chạy đo bằng milliseconds để suy luận thứ tự invocation.

## 4. Dự án Java 17+ chạy được: main và ba test JUnit

Ví dụ dùng Spring Framework **6.2.19**, JUnit Jupiter **5.12.2**, Gradle và Java 17+. Không cần Spring Boot hoặc database. Dự án thể hiện ba nhánh:

1. Ba listener đồng bộ có `@Order` khác nhau.
2. Listener đồng bộ đầu tiên ném exception, khiến multicast dừng trước listener sau theo mặc định.
3. Listener có `@Async` được **lên lịch** theo độ ưu tiên nhưng có thể **hoàn thành** sau listener đồng bộ ưu tiên thấp hơn.

### Cấu trúc

~~~text
listener-order-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/ListenerOrderDemo.java
    └── test/java/demo/ListenerOrderDemoTest.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'listener-order-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ListenerOrderDemo'
}

test {
    useJUnitPlatform()
}
~~~

Dùng Gradle 8.x và JDK 17+ hoặc Gradle Wrapper phù hợp. Ví dụ không dùng các API Spring Boot nên không có dependency Boot.

### src/main/java/demo/ListenerOrderDemo.java

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class ListenerOrderDemo {

    private ListenerOrderDemo() {}

    public record OrderPlaced(long orderId) {}
    public record FailureEvent() {}
    public record AsyncEvent() {}

    // Collector dùng được từ cả thread publisher và worker.
    public static final class CallLog {
        private final CopyOnWriteArrayList<String> calls =
            new CopyOnWriteArrayList<>();

        public void add(String value) {
            calls.add(value);
        }

        public List<String> snapshot() {
            return List.copyOf(calls);
        }

        public void clear() {
            calls.clear();
        }
    }

    // --- Nhóm 1: listener đồng bộ, sắp xếp theo @Order ---

    @Configuration
    public static class OrderedConfig {
        @Bean
        CallLog callLog() {
            return new CallLog();
        }

        @Bean
        ValidateListener validateListener(CallLog log) {
            return new ValidateListener(log);
        }

        @Bean
        AuditListener auditListener(CallLog log) {
            return new AuditListener(log);
        }

        @Bean
        NotifyListener notifyListener(CallLog log) {
            return new NotifyListener(log);
        }
    }

    public static class ValidateListener {
        private final CallLog log;

        public ValidateListener(CallLog log) {
            this.log = log;
        }

        @EventListener
        @Order(-20)
        public void onOrderPlaced(OrderPlaced event) {
            log.add("validate:" + event.orderId());
        }
    }

    public static class AuditListener {
        private final CallLog log;

        public AuditListener(CallLog log) {
            this.log = log;
        }

        @EventListener
        @Order(0)
        public void onOrderPlaced(OrderPlaced event) {
            log.add("audit:" + event.orderId());
        }
    }

    public static class NotifyListener {
        private final CallLog log;

        public NotifyListener(CallLog log) {
            this.log = log;
        }

        @EventListener
        @Order(20)
        public void onOrderPlaced(OrderPlaced event) {
            log.add("notify:" + event.orderId());
        }
    }

    // --- Nhóm 2: exception của listener đồng bộ ---

    @Configuration
    public static class FailureConfig {
        @Bean
        CallLog callLog() {
            return new CallLog();
        }

        @Bean
        FirstFailingListener firstFailingListener(CallLog log) {
            return new FirstFailingListener(log);
        }

        @Bean
        LateListener lateListener(CallLog log) {
            return new LateListener(log);
        }
    }

    public static class FirstFailingListener {
        private final CallLog log;

        public FirstFailingListener(CallLog log) {
            this.log = log;
        }

        @EventListener
        @Order(-10)
        public void onFailure(FailureEvent event) {
            log.add("first-throws");
            throw new IllegalStateException("simulated failure");
        }
    }

    public static class LateListener {
        private final CallLog log;

        public LateListener(CallLog log) {
            this.log = log;
        }

        @EventListener
        @Order(10)
        public void onFailure(FailureEvent event) {
            log.add("late");
        }
    }

    // --- Nhóm 3: @Async làm completion order khác invocation order ---

    public static final class Gates {
        public final CountDownLatch started = new CountDownLatch(1);
        public final CountDownLatch release = new CountDownLatch(1);
        public final CountDownLatch completed = new CountDownLatch(1);
    }

    @Configuration
    @EnableAsync
    public static class AsyncConfig {
        @Bean
        CallLog callLog() {
            return new CallLog();
        }

        @Bean
        Gates gates() {
            return new Gates();
        }

        @Bean(name = "taskExecutor")
        ThreadPoolTaskExecutor taskExecutor() {
            var executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("listener-");
            return executor;
        }

        @Bean
        AsyncFirstListener asyncFirstListener(CallLog log, Gates gates) {
            return new AsyncFirstListener(log, gates);
        }

        @Bean
        SyncLaterListener syncLaterListener(CallLog log) {
            return new SyncLaterListener(log);
        }
    }

    public static class AsyncFirstListener {
        private final CallLog log;
        private final Gates gates;

        public AsyncFirstListener(CallLog log, Gates gates) {
            this.log = log;
            this.gates = gates;
        }

        @Async
        @EventListener
        @Order(-50)
        public void onAsyncEvent(AsyncEvent event) {
            gates.started.countDown();
            try {
                if (!gates.release.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("release timed out");
                }
                log.add("async");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            } finally {
                gates.completed.countDown();
            }
        }
    }

    public static class SyncLaterListener {
        private final CallLog log;

        public SyncLaterListener(CallLog log) {
            this.log = log;
        }

        @EventListener
        @Order(50)
        public void onAsyncEvent(AsyncEvent event) {
            log.add("sync");
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                OrderedConfig.class)) {

            CallLog log = context.getBean(CallLog.class);
            context.publishEvent(new OrderPlaced(101L));

            log.snapshot().forEach(System.out::println);
        }
    }
}
~~~

### src/test/java/demo/ListenerOrderDemoTest.java

~~~java
package demo;

import java.util.List;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ListenerOrderDemoTest {

    @Test
    void invokesSynchronousListenersInOrder() {
        try (var context = new AnnotationConfigApplicationContext(
                ListenerOrderDemo.OrderedConfig.class)) {

            var log = context.getBean(ListenerOrderDemo.CallLog.class);

            context.publishEvent(new ListenerOrderDemo.OrderPlaced(101L));

            assertEquals(
                List.of("validate:101", "audit:101", "notify:101"),
                log.snapshot()
            );
        }
    }

    @Test
    void preservesConfiguredOrderForEachPublishedEvent() {
        try (var context = new AnnotationConfigApplicationContext(
                ListenerOrderDemo.OrderedConfig.class)) {

            var log = context.getBean(ListenerOrderDemo.CallLog.class);

            context.publishEvent(new ListenerOrderDemo.OrderPlaced(1L));
            context.publishEvent(new ListenerOrderDemo.OrderPlaced(2L));

            assertEquals(
                List.of(
                    "validate:1", "audit:1", "notify:1",
                    "validate:2", "audit:2", "notify:2"
                ),
                log.snapshot()
            );
        }
    }

    @Test
    void failingSynchronousListenerStopsLaterListenerByDefault() {
        try (var context = new AnnotationConfigApplicationContext(
                ListenerOrderDemo.FailureConfig.class)) {

            var log = context.getBean(ListenerOrderDemo.CallLog.class);

            assertThrows(
                IllegalStateException.class,
                () -> context.publishEvent(
                    new ListenerOrderDemo.FailureEvent())
            );

            assertEquals(
                List.of("first-throws"),
                log.snapshot()
            );
        }
    }

    @Test
    void asyncPriorityDoesNotGuaranteeCompletionOrder()
            throws InterruptedException {

        try (var context = new AnnotationConfigApplicationContext(
                ListenerOrderDemo.AsyncConfig.class)) {

            var log = context.getBean(ListenerOrderDemo.CallLog.class);
            var gates = context.getBean(ListenerOrderDemo.Gates.class);

            try {
                context.publishEvent(new ListenerOrderDemo.AsyncEvent());

                // Chờ xác nhận method async thực sự đã bắt đầu.
                assertTrue(gates.started.await(10, TimeUnit.SECONDS));

                // Async listener đang chờ release.
                // Sync listener được gọi sau nhưng hoàn thành trước.
                assertEquals(List.of("sync"), log.snapshot());
            } finally {
                // Luôn mở cổng để test không giữ executor bị treo.
                gates.release.countDown();
            }

            assertTrue(gates.completed.await(10, TimeUnit.SECONDS));
            assertEquals(List.of("sync", "async"), log.snapshot());
        }
    }
}
~~~

### Chạy và đối chiếu

~~~bash
gradle test
gradle run --quiet
# Nếu có Gradle Wrapper: ./gradlew test
# Trên Windows nếu có wrapper: gradlew.bat test
~~~

`gradle test` phải kết thúc thành công với **4 bài test pass**, không phải chỉ “không in ra gì”. Nếu thất bại, đọc test report tại `build/reports/tests/test/index.html`. Dòng `System.out` do `main` chủ động in ra khi chạy `gradle run --quiet`:

~~~text
validate:101
audit:101
notify:101
~~~

Kết quả test thứ ba chứng minh **exception đồng bộ có thể ngắt multicast** theo cấu hình mặc định. Test thứ tư **cố tình chặn** listener `async` bằng `CountDownLatch` để chứng minh một listener ưu tiên cao hơn có thể **hoàn thành sau** listener khác; nó không khẳng định mọi lần chạy async đều có thứ tự này.

**Giới hạn:** đây là code được viết để chạy với các dependency đã nêu; đầu ra `gradle test` của Gradle còn phụ thuộc môi trường, cache và phiên bản Gradle. Các log lifecycle Spring hoặc log executor không được xem là một phần của stdout khẳng định. Trong hệ thống thật, nên cố định dependency/Gradle Wrapper bằng quy trình build của dự án.

## 5. Phân tích bốn bài test: điều gì đang được chứng minh?

### Test 1 — Thứ tự invocation khi đồng bộ

Hai yếu tố cùng xuất hiện:

- Spring sắp listener với các giá trị `@Order(-20)`, `@Order(0)`, `@Order(20)`.
- Multicaster mặc định gọi listener trên cùng thread của `publishEvent`.

Vì vậy sau khi `publishEvent` trả về, danh sách đã có đủ cả ba mục theo thứ tự. Test dùng `assertEquals(List.of(...), ...)`, không kiểm tra một collection không có thứ tự như `Set`.

### Test 2 — Hai event không làm trộn lịch sử trong mô hình đồng bộ

Khi publish `OrderPlaced(1)` rồi `OrderPlaced(2)` trên cùng thread, mỗi lời gọi phải hoàn tất chuỗi listener đồng bộ trước khi phương thức publish tiếp theo được gọi. Kỳ vọng là:

~~~text
validate:1, audit:1, notify:1,
validate:2, audit:2, notify:2
~~~

Nếu chính listener có logic phát **event lồng nhau** hoặc ứng dụng có nhiều thread publish đồng thời, thứ tự toàn cục có thể khác; không tổng quát hóa test này cho mọi kiến trúc.

### Test 3 — Exception có thể ngắt listener phía sau

Với `SimpleApplicationEventMulticaster` mặc định **không gắn ErrorHandler**, exception từ listener đồng bộ được truyền về publisher và có thể khiến các listener còn lại không được gọi. Vì thế:

~~~text
first-throws
# Không có "late".
~~~

Không viết test ngược rằng “mọi listener luôn chạy dù listener trước đã lỗi”. Nếu ứng dụng cấu hình `ErrorHandler` để **log và suppress** exception, cả kiểu lỗi và callback tiếp theo có thể thay đổi. Hãy kiểm thử theo cấu hình thật, và nhớ rằng việc suppress lỗi không tự đồng nghĩa nghiệp vụ đã xử lý thành công.

### Test 4 — @Async thay đổi thứ tự hoàn thành

`AsyncFirstListener` có `@Order(-50)` và `SyncLaterListener` có `@Order(50)`. Spring có thể gọi adapter async trước; adapter đó giao công việc cho executor rồi trở lại. Trong test, listener async bắt đầu nhưng **chờ một cổng `release`**, nên listener đồng bộ hoàn tất trước. Khi test mở cổng, async mới hoàn tất.

Bài học: `@Order` trong cấu hình bất đồng bộ không phải “barrier” bắt người sau **đợi** người trước làm xong.

Khi test async, dùng:

- `CountDownLatch` hoặc tín hiệu hoàn tất có giới hạn thời gian;
- `CompletableFuture` và `await` phù hợp nếu listener/API có trả kết quả;
- công cụ kiểm thử concurrency như Awaitility khi dự án đã dùng;
- assertion về **tập kết quả** hoặc dependency thực sự được bảo đảm, không ép total order không có contract.

**Tránh `Thread.sleep(1000)`**: máy CI nhanh/chậm khác nhau có thể tạo test *flaky*. Một latch có timeout rõ ràng tạo điều kiện quan sát đáng tin hơn.

## 6. Khi hai listener có cùng @Order thì test thế nào?

Giả sử:

~~~java
@EventListener
@Order(10)
void handleA(OrderPlaced e) { ... }

@EventListener
@Order(10)
void handleB(OrderPlaced e) { ... }
~~~

Cả hai cùng mức ưu tiên. Spring có thể giữ thứ tự thực tế nhất quán trong **một lần chạy cụ thể**, nhưng bạn **không có contract đủ mạnh** để assert A luôn trước B trên mọi phiên bản cấu hình.

Nếu **không cần thứ tự**, hãy assert cả hai đã xử lý:

~~~java
assertEquals(
    Set.of("A", "B"),
    new HashSet<>(log.snapshot())
);
~~~

Đây là **đoạn minh họa trong JUnit**, cần import `Set` và `HashSet`, cùng biến `log`. Chỉ dùng cách này nếu mỗi listener được gọi đúng một lần: so sánh `Set` có thể che lỗi trùng, nên với yêu cầu đếm chính xác có thể dùng `assertEquals(2, log.snapshot().size())` thêm vào.

Nếu **cần thứ tự**, hãy gán độ ưu tiên khác nhau và kiểm thử explicit:

~~~java
@Order(10)  // A trước
@Order(20)  // B sau
~~~

Nếu B phụ thuộc dữ liệu A đã commit, `@Order` có thể vẫn chưa đủ; đưa phụ thuộc sang service orchestration, transaction boundary hoặc workflow thích hợp.

## 7. Kiểm thử @TransactionalEventListener: phase quan trọng hơn số thứ tự

`@TransactionalEventListener` không giống `@EventListener` thông thường. Method của nó **được gắn với phase của một transaction**, ví dụ:

~~~java
// Hai method minh họa cần bean, transaction manager
// và import Spring transaction phù hợp.
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
@Order(-10)
public void beforeA(OrderPlaced event) {
    steps.add("before-A");
}

@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
@Order(10)
public void beforeB(OrderPlaced event) {
    steps.add("before-B");
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Order(-10)
public void afterA(OrderPlaced event) {
    steps.add("after-A");
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Order(10)
public void afterB(OrderPlaced event) {
    steps.add("after-B");
}
~~~

Một bài test **có transaction imperative thật** có thể kỳ vọng:

~~~text
before-A
before-B
# Database commit thành công
after-A
after-B
~~~

Nhưng cần nhớ:

1. `@Order` có thể sắp xếp callback **trong nhóm cùng phase** (và giữa những transaction synchronizations khác theo order). Không dùng `order=-10` của `AFTER_COMMIT` để yêu cầu chạy **trước** một callback `BEFORE_COMMIT`: phase khác thời điểm.
2. Nếu T1 **rollback**, `@TransactionalEventListener(AFTER_COMMIT)` không chạy. Một listener `AFTER_ROLLBACK` có thể chạy nếu event đã được publish trong transaction.
3. Nếu **không có transaction**, mặc định `fallbackExecution=false`, listener transaction-bound bị bỏ qua; test cần chủ động tạo transaction.
4. `AFTER_COMMIT` diễn ra sau commit thật. Một listener có thể thấy transaction resource đang trong cleanup, nhưng **không được hiểu là có transaction mới để ghi DB**. Khi cần ghi hậu commit, thiết kế transaction mới rõ ràng, thường `REQUIRES_NEW` với imperative.
5. Với reactive transaction, ngữ cảnh nằm trong Reactor Context; cần dùng công bố phù hợp như `TransactionalEventPublisher` và kiểm thử **subscription + commit/rollback** bằng reactive API.

### Mẫu integration test với transaction manager thật

Một cách ổn định là dùng `TransactionTemplate` với `PlatformTransactionManager` và publisher để kiểm soát chính xác thời điểm commit:

~~~java
// Đoạn minh họa integration test; cần bean transactionManager,
// applicationEventPublisher và collector steps trong test context.
var template = new TransactionTemplate(transactionManager);

template.executeWithoutResult(status -> {
    applicationEventPublisher.publishEvent(new OrderPlaced(101L));

    // Chưa tới BEFORE_COMMIT / AFTER_COMMIT.
    assertEquals(List.of(), steps.snapshot());
});

// Sau khi executeWithoutResult trả về, transaction đã hoàn tất.
assertEquals(
    List.of("before-A", "before-B", "after-A", "after-B"),
    steps.snapshot()
);
~~~

Đây không phải file chạy độc lập. Nó phải đi cùng cấu hình `@EnableTransactionManagement` (nếu dùng `@Transactional`), manager thực (ví dụ `DataSourceTransactionManager` với H2), bean listener thật và transaction của test **được tạo đúng lúc**. Với `TransactionTemplate` có thể tự quản lý boundary mà không cần method proxy `@Transactional`.

### Cẩn thận với @Transactional trên lớp test

Trong Spring Test, một method test được đánh dấu `@Transactional` thường bị **rollback mặc định** khi kết thúc. Nếu chỉ publish event trong test đó và assert ngay lập tức, `AFTER_COMMIT` **chưa chạy**; nếu test rollback, callback ấy sẽ không chạy.

Để thực sự kiểm thử after-commit, có thể:

- Chạy transaction bên trong test bằng `TransactionTemplate` như trên, không bọc method test trong một outer transaction mà nó join.
- Dùng Spring Test `TestTransaction.flagForCommit()` rồi `TestTransaction.end()` khi test được quản lý bằng test transaction thích hợp.
- Sau commit, dùng readback DB độc lập để xác minh dữ liệu; tránh dùng assert dựa trên log “đã gọi service” khi transaction chưa hoàn tất.

Ngoài thứ tự callback, test nên assert **đúng phase** và **đúng kết quả DB**. Không biến `@Order` thành công cụ thay thế kiểm thử commit/rollback.

## 8. Đừng suy diễn thứ tự giữa hai loại listener khác nhau

Những tổ hợp sau phải được đánh giá riêng:

| Tổ hợp | Có thể assert gì? | Không nên assert gì? |
| --- | --- | --- |
| Nhiều `@EventListener` đồng bộ, khác `order` | Invocation/completion theo mức ưu tiên | Bảo đảm nghiệp vụ đã commit |
| Nhiều `@EventListener` cùng `order` | Tất cả đã được gọi, số lần đúng | Thứ tự A/B cố định nếu không có contract |
| `@Async @EventListener` và sync listener | Eventual completion, kết quả từng handler | `Order` là thứ tự **hoàn thành** |
| Custom multicaster + executor | Kết quả sau khi các task hoàn tất | Submission order đồng nghĩa completion order |
| Nhiều `@TransactionalEventListener` cùng phase | Thứ tự callback theo `@Order` trong cấu hình kiểm thử | Phase khác nhau cùng chạy tại thời điểm publish |
| Listener ở parent và child contexts | Event của child có thể được xử lý ở child rồi lan lên parent | Một `Order` toàn cục sắp mọi context |
| Một listener phát event lồng nhau | Thứ tự trong từng event theo cơ chế dispatch tương ứng | Mọi event được xử lý tuần tự theo thứ tự xuất hiện ban đầu |

**Parent–child context:** Spring truyền event từ child lên parent. Mỗi context có registry listener và multicaster riêng. Giá trị `@Order` không tạo **một bảng thứ tự xuyên tất cả context**.

**Event lồng nhau:** listener của event A có thể gọi `publishEvent(B)`; với multicaster đồng bộ, listener của B có thể chạy **trong lúc** listener của A chưa hoàn tất, trước khi Spring tiếp tục các listener còn lại của A. Test không nên giả định danh sách tổng luôn “tất cả listener của A, rồi tất cả listener của B”.

## 9. Mockito InOrder có dùng được không?

Có, khi muốn xác minh **thứ tự lời gọi giữa các mock**:

~~~java
// Đoạn minh họa, không phải file độc lập.
// Các mock được inject vào listener beans thực của test context.
InOrder ordered = Mockito.inOrder(auditRepository, notificationClient);

ordered.verify(auditRepository).save(any());
ordered.verify(notificationClient).enqueue(any());
~~~

Ưu điểm: xác minh tương tác với dependency. Tuy nhiên:

- Nếu test **tự gọi** listener trước, test không kiểm chứng event multicaster.
- Nếu listener hoạt động async, `InOrder` chạy ngay sau publish có thể thiếu lời gọi; cần đợi đúng tín hiệu hoàn tất.
- Nếu lệnh ghi DB và gọi API mạng đều phụ thuộc vào nhau, nên cân nhắc chuyển logic sang application service để phụ thuộc được định nghĩa rõ, thay vì dựa vào thứ tự listener.
- Mockito verify không thay thế việc assert dữ liệu thực tế khi có transaction/rollback.

Collector `CallLog` trong ví dụ được ưu tiên cho bài học này vì không cần thêm dependency mock, dễ kiểm tra thứ tự toàn chuỗi và hoạt động với real Spring context.

## 10. Những lỗi test thường gặp

**Lỗi 1 — Assert theo thứ tự đăng ký bean.** Viết `@Bean a()` trước `@Bean b()` không thay cho `@Order`, vì mục tiêu là contract của event listeners chứ không phải cách Spring quét class hoặc dựng bean.

**Lỗi 2 — Dùng hai listener không `@Order` rồi mong luôn có thứ tự.** Test có thể tình cờ pass trên máy local nhưng hỏng khi đổi Spring version, proxy, auto-config hoặc classpath.

**Lỗi 3 — Dùng `Thread.sleep(...)` để chờ `@Async`.** Test flaky trên CI. Thay bằng `CountDownLatch`, Future hoặc signal đáng tin.

**Lỗi 4 — Kiểm tra thứ tự hoàn thành khi hệ thống chỉ bảo đảm thứ tự dispatch.** `Order(-10)` của async handler không bảo đảm việc xử lý xong trước `Order(10)`.

**Lỗi 5 — Test bằng mock publisher thay vì real ApplicationContext.** Mock publisher chỉ ghi nhận `publishEvent` được gọi, không tự thực hiện việc multicaster sắp listener. Chọn mock khi unit test service; chọn context thật khi muốn test listener ordering.

**Lỗi 6 — Assert listener cuối được gọi dù listener đầu đã ném lỗi.** Với `SimpleApplicationEventMulticaster` đồng bộ mặc định và không có `ErrorHandler`, exception có thể dừng multicast. Test cả nhánh lỗi và chính sách error handling.

**Lỗi 7 — Quên reset collector.** Event ở `ContextRefreshedEvent` hoặc event của test trước dễ làm lịch sử “thừa”. Dùng event type cụ thể và context riêng cho mỗi test.

**Lỗi 8 — Không chờ transaction kết thúc.** `AFTER_COMMIT` chạy sau commit; assert ngay trong thân `@Transactional` dễ sai. Dùng `TransactionTemplate` hoặc Spring Test transaction control.

**Lỗi 9 — Test toàn cục phụ thuộc vào nhiều context.** Parent và child có multicaster riêng. Test đúng topology nếu ứng dụng dùng nhiều context.

**Lỗi 10 — Xem `@Order` là cơ chế bảo đảm exactly-once hay durable ordering.** Application event cục bộ không tự thay thế message broker/outbox, cũng không bảo đảm recover sau crash.

## 11. Checklist thiết kế test listener ordering

1. **Xác định chính xác event type và các listener cần kiểm tra.**
2. **Viết contract:** cần invocation order, completion order hay transaction-phase order?
3. **Chỉ định `@Order` rõ ràng** cho listener mà thứ tự thật sự là yêu cầu.
4. **Dùng real Spring `ApplicationContext`** để kiểm chứng event multicaster, không tự gọi tuần tự các handler.
5. **Thu lịch sử vào collector thread-safe** và assert toàn bộ danh sách khi đường chạy đồng bộ.
6. **Không ép thứ tự giữa các listener cùng priority** trừ khi ứng dụng bổ sung contract riêng.
7. **Đối với async, đợi tín hiệu có timeout**, kiểm tra kết quả cuối thay vì thời gian sleep.
8. **Test exception** từ listener ưu tiên cao và xác định cấu hình `ErrorHandler` có cho tiếp tục hay không.
9. **Đối với transaction-bound listener**, test commit/rollback thực và phân biệt phase với `@Order`.
10. **Kiểm thử topology parent–child/nested events** nếu thực tế có, thay vì suy ra thứ tự toàn cục.
11. **Tách yêu cầu phụ thuộc nghiệp vụ khỏi event ordering** khi kết quả A phải được commit trước B.
12. **Giữ test độc lập và repeatable**: không lệ thuộc thread scheduling, startup order hay clock.

### Ghi nhớ

~~~text
@Order(-20)  -> ưu tiên gọi listener cao hơn @Order(20)
@EventListener + multicaster đồng bộ
             -> thứ tự invocation có thể kiểm thử bằng List

@Async       -> order không bảo đảm completion order
               dùng CountDownLatch / Future / await

@TransactionalEventListener
             -> phase quyết định lúc chạy
               @Order chỉ ưu tiên trong các callback phù hợp

SimpleApplicationEventMulticaster mặc định
             -> listener sync ném lỗi có thể dừng multicast

Test đáng tin
             -> real ApplicationContext + event + log + assert
~~~

**Kết luận:** Khi kiểm thử thứ tự listener, hãy xác minh một hợp đồng nhỏ và rõ: **listener đồng bộ với `@Order` khác nhau được gọi theo ưu tiên**. Khi chuyển sang async, transactional phases, parent–child hoặc nested events, phải đổi chiến lược kiểm thử theo thời điểm thực thi và mức bảo đảm của Spring; không thể dùng một phép so sánh danh sách cho tất cả.

## Tài liệu chính thức

- [Spring Framework 6.2 — Standard and Custom Events / Ordering Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [JUnit 5 — Writing Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests)
