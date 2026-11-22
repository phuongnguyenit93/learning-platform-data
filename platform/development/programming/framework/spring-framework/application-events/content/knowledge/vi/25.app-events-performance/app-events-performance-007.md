# Độ trễ do nhiều listener nối tiếp trong Spring Framework Application Events

## 1. Vì sao một lời gọi publishEvent có thể chậm?

Một service có thể chỉ gọi `ApplicationEventPublisher.publishEvent(event)` để thông báo đơn hàng vừa tạo, nhưng request vẫn mất hàng trăm mili-giây hoặc vài giây trước khi trả về. Nguyên nhân thường là **nhiều listener được gọi nối tiếp trên chính thread của publisher**.

Spring Framework sử dụng `SimpleApplicationEventMulticaster` với cách thực thi đồng bộ mặc định nếu application context không được tùy chỉnh. Khi một event phù hợp với nhiều `@EventListener`, multicaster gọi từng listener; callback trước phải trả về thì callback kế tiếp mới được gọi trong lượt phát đồng bộ đó. Nếu có ba listener lần lượt tốn 60 ms, 90 ms và 120 ms, riêng phần chờ chủ động đã là 270 ms, chưa kể dispatch và các chi phí khác.

Bài này giúp bạn:

- Hiểu **cách nhiều listener làm tăng độ trễ** của một lượt phát event.
- Phân biệt tổng thời gian publish, thời gian từng listener, độ trễ queue và độ trễ hoàn thành nghiệp vụ.
- Nhận biết `@Order` chỉ điều khiển thứ tự gọi, không làm các listener tự chạy song song.
- Nắm tác động của exception, nested events, transaction và sự khác nhau giữa các publisher threads.
- Chạy một ví dụ Java 17+ với ba listener đồng bộ và đo thời gian.
- Viết JUnit 5 test xác nhận thứ tự, exception propagation và trường hợp async publisher trả về trước khi listener hoàn tất.
- Chọn giải pháp giảm latency mà không đánh đổi âm thầm tính đúng và độ bền của sự kiện.

**Ý chính:** Giảm số đo của `publishEvent` không nhất thiết giảm thời gian công việc thật sự hoàn tất. Đặc biệt, chuyển sang async có thể chỉ chuyển chi phí từ request thread sang worker/queue.

## 2. Cơ chế phân phối event mặc định

Các thành phần liên quan:

| Thành phần | Vai trò |
| --- | --- |
| `ApplicationEventPublisher` | API phát một event cho hạ tầng Spring |
| `ApplicationEventMulticaster` | Chọn, phân phối đến các listener phù hợp |
| `SimpleApplicationEventMulticaster` | Multicaster đơn giản; mặc định đồng bộ trên caller thread |
| `ApplicationListener<T>` | Listener viết dưới dạng interface |
| `@EventListener` | Khai báo listener trên phương thức của Spring bean |
| `@Order` | Xác định độ ưu tiên/thứ tự listener được gọi |
| `TaskExecutor`, `@Async` | Có thể đưa xử lý sang thread khác nếu được cấu hình |

Một phương thức service có thể phát event bằng:

~~~java
publisher.publishEvent(new OrderSubmitted(orderId));
~~~

Ba listener:

~~~java
@EventListener
public void updateInventory(OrderSubmitted event) {
    inventoryService.update(event.orderId());
}

@EventListener
public void calculateBilling(OrderSubmitted event) {
    billingService.calculate(event.orderId());
}

@EventListener
public void notifyCustomer(OrderSubmitted event) {
    notificationService.send(event.orderId());
}
~~~

Các đoạn mã trên **chỉ minh họa**; phải có class event, những bean service và import tương ứng. Ví dụ chạy đầy đủ nằm ở mục 8.

Với multicaster đồng bộ, đường đi thường là:

~~~text
request/service thread
     |
     +---> publishEvent(OrderSubmitted)
                |
                +---> updateInventory() -- return
                |
                +---> calculateBilling() -- return
                |
                +---> notifyCustomer() -- return
                |
                +---> publishEvent() returns
     |
     +---> service tiếp tục / HTTP response
~~~

Mỗi callback ở đây là một phần của **critical path của lời gọi publish**. Nếu listener chạy tác vụ I/O chậm, publisher chờ nó.

Cần hiểu chính xác: từ “nối tiếp” chỉ nói về **các listener trong một lượt phân phối đồng bộ**. Nó **không** tạo khóa toàn cục cho mọi event. Hai HTTP request threads riêng vẫn có thể đồng thời publish và chạy các callback trên hai thread đó; tài nguyên chung bên dưới (DB, lock, service) lại có thể tranh chấp nhau.

## 3. Mô hình tính độ trễ cộng dồn

Trong một trường hợp đơn giản:

~~~text
T_publish ≈ T_dispatch + T_listener1 + T_listener2 + ... + T_listenerN
~~~

Đây là mô hình **khi tất cả listener chạy đồng bộ, được gọi tới hết và không có exception cắt ngắn multicast**. `T_dispatch` có thể gồm overhead lọc loại event, tìm adapter, method invocation và các công việc nhỏ khác.

Ví dụ:

| Listener | Công việc | Thời gian giả định |
| --- | --- | --- |
| Inventory | Kiểm tra tồn kho | 40 ms |
| Billing | Tính và lưu hóa đơn | 120 ms |
| Notification | Gửi thông báo | 250 ms |
| Tổng thời gian callback | Ba tác vụ nối tiếp | 410 ms |

Nếu dispatch overhead nhỏ, thời gian đo quanh `publishEvent` gần 410 ms. Đây là **ví dụ số học**, không phải mốc hiệu năng do Spring đặt ra.

Timeline:

~~~text
Time →
Publish bắt đầu
|--- Inventory 40ms ---|
                       |------- Billing 120ms -------|
                                                  |---------- Notification 250ms ----------|
                                                                                             |
                                                                                      Publish trả về
~~~

Listener cuối **không thể bắt đầu** khi callback trước chưa trả về trong chế độ đồng bộ. Nếu notification timeout sau 5 giây, một event rất nhỏ vẫn có thể làm lời gọi publish mất 5 giây.

### 3.1. Request latency bị cộng vào như thế nào?

Giả sử service gồm validation 10 ms, SQL 30 ms, publish 410 ms, response mapping 5 ms. Request mất xấp xỉ **455 ms**, dù bản thân SQL khá nhanh.

~~~text
validate:         10 ms
database:         30 ms
publish:         410 ms  (bao gồm listener execution)
serialize:         5 ms
-----------------------
request:         455 ms
~~~

Đây không phải phép đo hệ thống thật. Với trace thực tế, callback có thể lồng event khác, query DB tranh chấp lock hoặc sử dụng transaction hiện tại khiến thời gian khác xa mô hình đơn giản.

### 3.2. Tail latency quan trọng hơn average

Nếu hai listener luôn nhanh nhưng một listener HTTP đôi khi mất vài giây, **p95/p99 của publish** và request có thể tăng mạnh. Một số đo trung bình từ local dev không thể chứng minh SLO production được đáp ứng.

Hãy thu thập cả throughput, duration distribution, active request threads, DB pool wait, downstream timeout và queue depth nếu có async.

## 4. @Order quyết định thứ tự, không song song hóa

Spring hỗ trợ:

~~~java
@EventListener
@Order(10)
public void inventory(OrderSubmitted event) {
    // ...
}

@EventListener
@Order(20)
public void billing(OrderSubmitted event) {
    // ...
}

@EventListener
@Order(30)
public void notification(OrderSubmitted event) {
    // ...
}
~~~

Đây là minh họa; các phương thức cần là thành viên của bean Spring.

Trong cấu hình đồng bộ, thứ tự gọi là inventory, billing, notification. Đổi `@Order(30)` thành `@Order(-100)` có thể làm notification được gọi trước, **nhưng không tự khiến các callback chạy đồng thời**. Tổng chi phí xử lý thường vẫn còn nếu tất cả cùng thực hiện.

Với cấu hình async, `@Order` có thể chi phối thứ tự **dispatch**, nhưng thứ tự **hoàn tất** phụ thuộc thread scheduling, thời gian mỗi handler và executor. Không dùng annotation order để bảo đảm rằng email hoàn tất sau khi billing commit khi hệ thống thực thi bất đồng bộ.

Nếu một listener thực sự phụ thuộc dữ liệu do listener khác tạo, nên xem xét một service workflow rõ ràng hoặc việc điều phối kết quả có contract, thay vì gắn chặt bằng thứ tự ngầm trong event bus.

## 5. Exception có thể làm publisher trả về sớm theo cách sai

Ở multicaster đồng bộ mặc định, nếu một listener ném `RuntimeException` chưa được xử lý, exception có thể dừng lượt multicasting và truyền về publisher.

~~~text
L1 -> success
L2 -> throws RuntimeException
L3 -> chưa được gọi
publisher -> nhận exception
~~~

Điều này dẫn đến tình huống lạ: publish duration **giảm** vì L3 chưa có cơ hội làm việc, nhưng đó **không phải tối ưu thành công**.

Hệ quả:

- L1 có thể đã thực hiện side effect, L2 lỗi, L3 chưa chạy.
- Nếu publisher retry toàn bộ event, L1 có thể chạy lần nữa.
- Trong transaction hiện hành, exception có thể khiến transaction rollback theo quy tắc applicable.
- Nếu L1 đã gửi email trước rollback, email không tự được thu hồi.
- Nếu cấu hình `ErrorHandler` nuốt lỗi, multicast có thể tiếp tục, nhưng phải chấp nhận rõ chính sách ghi lỗi/retry.

`SimpleApplicationEventMulticaster#setErrorHandler(...)` là một điểm mở rộng xử lý exception, **không tự cung cấp dead-letter queue, durable retry hoặc exactly-once delivery**. Không nuốt lỗi chỉ để báo “publisher nhanh”.

## 6. Sự khác nhau giữa nhiều listener và nhiều publisher

Ba listener của **một lượt publish đồng bộ** có thể chạy nối tiếp trên thread A. Trong khi đó, thread B vẫn có thể publish một event khác và kích hoạt chính các method listener ấy ở thời điểm chồng lấn.

~~~text
Thread A:  publish(E1) -> L1(E1) -> L2(E1) -> L3(E1)
Thread B:      publish(E2) -> L1(E2) -> L2(E2) -> L3(E2)
~~~

Trong thực tế:

- Một Spring singleton listener có thể được nhiều threads gọi cùng lúc. Nó phải **thread-safe** hoặc tránh mutable shared state.
- Database locks, thread pool, HTTP connection pool và rate limits có thể khiến hai lượt publish ảnh hưởng nhau.
- `@Order` không áp dụng một mutex bảo vệ thứ tự **toàn hệ thống** giữa E1 và E2.
- Nếu listener ghi chung một resource, contention làm thời gian tăng ngay cả khi từng method nhìn qua khá đơn giản.

Đừng dùng `synchronized` bừa bãi trên toàn bộ listener để “đảm bảo thứ tự”, vì cách này có thể serial hóa nhiều request threads và làm nghẽn throughput.

## 7. Những nguyên nhân thường làm listener chậm

| Nguyên nhân | Triệu chứng | Gợi ý điều tra |
| --- | --- | --- |
| N+1 JPA queries | Handler nhanh trên dữ liệu nhỏ, chậm theo kích thước order | SQL logs, query count, projection |
| HTTP dependency chậm | p99 request/publish tăng theo timeout | HTTP client timers, tracing, timeouts |
| DB lock / deadlock retry | Request chờ dù CPU thấp | Lock metrics, transaction duration |
| Serialization graph lớn | Allocation, CPU, GC tăng | JFR/heap profiler |
| I/O đồng bộ | Nhiều request threads ở WAITING | Thread dump, wall-clock profiler |
| Log quá nhiều | Hot path chậm khi logging sync hoặc đĩa nghẽn | Logging profiler, sampling |
| Listener publish event lồng | Độ trễ ngoài dự đoán, call stack sâu | Trace nested publish |
| Retry inline không giới hạn | Request treo lâu khi dependency lỗi | Retry policy, attempt count |
| Thiếu cache hoặc batch | DB/network nhiều round trips | Query planner, batching |
| Resource pool thiếu | Thread chờ connection dù handler logic ngắn | Pool usage và wait time |

Điều cần tối ưu không nhất thiết là số listener: có thể giữ ba callback nếu mỗi callback thực hiện công việc nhỏ. Ngược lại, chỉ một listener gọi HTTP timeout 30 giây cũng đủ kéo dài publish.

## 8. Ví dụ Java 17+ chạy được: ba listener nối tiếp

Ví dụ dùng Spring Framework 6.2.15 thuần và JUnit 5. Không cần web server, database hoặc Spring Boot. Để mô phỏng độ trễ quan sát được, ba listener dùng `Thread.sleep` ngắn với tổng 270 ms; **không dùng sleep như cách xử lý event production**.

### 8.1. Cấu trúc thư mục

~~~text
sequential-event-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           └── SequentialEventDemo.java
    └── test/
        └── java/
            └── demo/
                └── SequentialEventDemoTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'sequential-event-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'demo.SequentialEventDemo'
}

test {
    useJUnitPlatform()
}
~~~

### 8.2. Mã Java đầy đủ

Tạo `src/main/java/demo/SequentialEventDemo.java`:

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class SequentialEventDemo {

    public record OrderSubmitted(String orderId) {}

    public static final class Trace {
        private final CopyOnWriteArrayList<String> stages =
                new CopyOnWriteArrayList<>();

        public void add(String stage) {
            stages.add(stage);
        }

        public List<String> snapshot() {
            return List.copyOf(stages);
        }
    }

    public static final class Handlers {
        private final Trace trace;

        public Handlers(Trace trace) {
            this.trace = trace;
        }

        @EventListener
        @Order(10)
        public void inventory(OrderSubmitted event) {
            simulate("inventory", 60);
        }

        @EventListener
        @Order(20)
        public void billing(OrderSubmitted event) {
            simulate("billing", 90);
        }

        @EventListener
        @Order(30)
        public void notification(OrderSubmitted event) {
            simulate("notification", 120);
        }

        private void simulate(String name, long durationMillis) {
            System.out.println("begin:" + name);

            try {
                Thread.sleep(durationMillis);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Interrupted in " + name, ex);
            }

            trace.add(name);
            System.out.println("end:" + name);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public Trace trace() {
            return new Trace();
        }

        @Bean
        public Handlers handlers(Trace trace) {
            return new Handlers(trace);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            Trace trace = context.getBean(Trace.class);

            System.out.println("publisher:begin");
            long start = System.nanoTime();

            context.publishEvent(new OrderSubmitted("ORD-7"));

            long duration = System.nanoTime() - start;
            System.out.println("publisher:return");
            System.out.println(
                    "trace=" + String.join(",", trace.snapshot()));
            System.out.printf(
                    "publish.duration.ms=%.1f%n",
                    duration / 1_000_000.0);
        }
    }
}
~~~

### 8.3. Chạy demo và đọc stdout

Trong thư mục dự án, với JDK 17+ và Gradle:

~~~bash
gradle -q run
~~~

Nếu đã có Gradle Wrapper, thay bằng `./gradlew -q run` trên Linux/macOS hoặc `gradlew.bat -q run` trên Windows.

Những dòng có nội dung và thứ tự xác định:

~~~text
publisher:begin
begin:inventory
end:inventory
begin:billing
end:billing
begin:notification
end:notification
publisher:return
trace=inventory,billing,notification
publish.duration.ms=<giá trị thay đổi>
~~~

**Dòng cuối là ký hiệu để giải thích**, không phải literal được mã `printf` in ra. Trong lần chạy thật, nó là một số thập phân, có thể xấp xỉ hoặc lớn hơn 270 ms. Giá trị chính xác tùy scheduler, CPU, GC, logging và tải máy; không hứa một con số cố định. Phần stdout cũng có thể có thêm log Gradle/framework.

Kết quả chứng minh: `publisher:return` chỉ xuất hiện **sau** ba `end:...`; các callback được gọi nối tiếp và cả ba hoàn tất trước khi `publishEvent` trả về.

Lưu ý: `@Order` khiến thứ tự có thể dự đoán trong demo, còn việc publisher đợi đến cuối là do **multicaster đồng bộ**. Không đồng nhất hai vai trò này.

## 9. JUnit 5: test synchronous, exception và asynchronous

Tạo `src/test/java/demo/SequentialEventDemoTest.java`. Không dùng Mockito để giả lập event bus: các bài test dựng `AnnotationConfigApplicationContext` thật và phát event qua Spring.

Test thứ ba sử dụng một executor và `CountDownLatch` để chứng minh trong cấu hình async, publisher có thể trả về trong khi handler còn đang chờ. Không dùng `Thread.sleep` để đoán khi nào worker xong.

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SequentialEventDemoTest {

    @Test
    void syncPublishWaitsForAllThreeHandlers() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             SequentialEventDemo.Config.class)) {

            SequentialEventDemo.Trace trace =
                    context.getBean(SequentialEventDemo.Trace.class);

            assertTrue(trace.snapshot().isEmpty());

            context.publishEvent(
                    new SequentialEventDemo.OrderSubmitted("A"));

            // Không cần sleep sau publish: 3 listener đã hoàn tất.
            assertEquals(
                    List.of("inventory", "billing", "notification"),
                    trace.snapshot());
        }
    }

    public record FailureRequested() {}

    public static final class FailureHandlers {
        private final CopyOnWriteArrayList<String> calls =
                new CopyOnWriteArrayList<>();

        @EventListener
        @Order(10)
        public void first(FailureRequested event) {
            calls.add("first");
            throw new IllegalStateException("listener failed");
        }

        @EventListener
        @Order(20)
        public void second(FailureRequested event) {
            calls.add("second");
        }

        public List<String> snapshot() {
            return List.copyOf(calls);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class FailureConfig {

        @Bean
        public FailureHandlers failureHandlers() {
            return new FailureHandlers();
        }
    }

    @Test
    void exceptionStopsLaterListenerInSyncMode() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             FailureConfig.class)) {

            FailureHandlers handlers =
                    context.getBean(FailureHandlers.class);

            assertThrows(
                    IllegalStateException.class,
                    () -> context.publishEvent(new FailureRequested()));

            assertEquals(List.of("first"), handlers.snapshot());
        }
    }

    public record HoldRequested() {}

    public static final class BlockingListener {
        final CountDownLatch started = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
        final CountDownLatch finished = new CountDownLatch(1);

        @EventListener
        public void onHold(HoldRequested event) {
            started.countDown();

            try {
                if (!release.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Listener was not released");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Interrupted while waiting", ex);
            } finally {
                finished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AsyncConfig {

        @Bean
        public ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();

            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("event-demo-");
            return executor;
        }

        @Bean(name = "applicationEventMulticaster")
        public ApplicationEventMulticaster applicationEventMulticaster(
                ThreadPoolTaskExecutor eventExecutor) {

            SimpleApplicationEventMulticaster multicaster =
                    new SimpleApplicationEventMulticaster();

            multicaster.setTaskExecutor(eventExecutor);
            return multicaster;
        }

        @Bean
        public BlockingListener blockingListener() {
            return new BlockingListener();
        }
    }

    @Test
    void asyncPublisherReturnsBeforeHandlerIsReleased()
            throws InterruptedException {

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AsyncConfig.class)) {

            BlockingListener listener =
                    context.getBean(BlockingListener.class);

            context.publishEvent(new HoldRequested());

            try {
                assertTrue(listener.started.await(5, TimeUnit.SECONDS));

                // Handler đang đợi release; publish đã trả về.
                assertEquals(1L, listener.finished.getCount());
            } finally {
                listener.release.countDown();
            }

            assertTrue(listener.finished.await(5, TimeUnit.SECONDS));
        }
    }
}
~~~

### 9.1. Chạy test

~~~bash
gradle test
~~~

Kỳ vọng có **3 bài test JUnit 5** thành công nếu dependencies được giải quyết và thời gian chờ không bị môi trường CI làm gián đoạn. Gradle thường tạo báo cáo tại `build/reports/tests/test/index.html`. Đây là **kỳ vọng logic**, không phải kết quả của một lần test đã thực thi tại đây.

### 9.2. Ý nghĩa mỗi test

- `syncPublishWaitsForAllThreeHandlers`: ngay sau khi `publishEvent` trả về, trace đã có ba stage theo `@Order`. Kiểm chứng **Spring wiring** và đồng bộ thật.
- `exceptionStopsLaterListenerInSyncMode`: lỗi runtime của listener đầu được truyền về publisher; listener thứ hai không được gọi với cấu hình mặc định.
- `asyncPublisherReturnsBeforeHandlerIsReleased`: listener bắt đầu trên executor và chờ latch. Publisher đã trả về nhưng `finished` chưa được đếm xuống; sau khi release, handler thoát.

Test async chủ động tách `AsyncConfig`, không áp dụng executor vào test sync. Executor có một worker với queue bounded; nó **không chứng minh chạy song song nhiều listener**, chỉ chứng minh sự khác biệt về thời điểm publisher trả về.

## 10. Chuyển sang async: giảm publish wait nhưng chưa chắc giảm completion time

Có thể cung cấp bean multicaster với tên đặc biệt `applicationEventMulticaster`:

~~~java
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster eventMulticaster(
        ThreadPoolTaskExecutor executor) {

    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();

    multicaster.setTaskExecutor(executor);
    return multicaster;
}
~~~

Đây là đoạn cấu hình minh họa; trong file test đã có `AsyncConfig` hoàn chỉnh. Với listener thông thường hỗ trợ async, multicaster sẽ submit công việc tới executor thay vì gọi toàn bộ callback ngay trong thread publisher.

So sánh mô hình lý tưởng:

~~~text
SYNCHRONOUS:
    L1: 60 ms
           L2: 90 ms
                     L3: 120 ms
    Publisher wait ≈ 270 ms + overhead

ASYNCHRONOUS với đủ worker và độc lập:
    L1: 60 ms
    L2: 90 ms
    L3: 120 ms
    All done ≈ 120 ms + queue/dispatch/overhead
    Publish may return shortly after submission
~~~

Các mô hình trên là **giả định tải lý tưởng**, không phải bảo đảm của executor. Nếu pool chỉ có một worker, ba handler vẫn có thể nối tiếp trong queue. Publisher trả về sớm hơn nhưng thời gian tất cả callback hoàn tất có thể gần tổng thời gian cũ hoặc còn lâu hơn nếu backlog.

**Cần đo hai thứ riêng:** `publish latency` và `business completion latency`. Thay đổi async có thể làm số thứ nhất giảm mạnh trong khi số thứ hai không cải thiện.

## 11. Tác dụng phụ của async: queue, thứ tự, lỗi và transaction

| Vấn đề | Điều cần hiểu |
| --- | --- |
| Queue chờ | Nếu publish nhanh hơn xử lý, queue depth và start delay tăng |
| Memory retention | Event/payload còn được giữ bởi queued task |
| Rejection | Queue đầy có thể gây lỗi submit hoặc fallback theo policy |
| `CallerRunsPolicy` | Khi bão hòa, task có thể chạy trên publisher thread và làm publish chậm lại |
| Order | `@Order` không bảo đảm thứ tự **hoàn tất** khi nhiều threads |
| Exception | Lỗi worker không tự quay về publisher như sync callback |
| Transaction context | JDBC/JPA ThreadLocal transaction không tự theo worker |
| Security/MDC/trace | Cần context propagation riêng nếu cần |
| Crash | In-memory queue mất task nếu process chết |
| Shared resources | Nhiều worker có thể tranh chấp DB pool/rate limit |

Từ Spring 6.1, `ApplicationListener.supportsAsyncExecution()` cho phép một số listener **từ chối thực thi async tại multicaster**. Ví dụ các transaction-synchronized listener cần đăng ký callback trong thread liên quan tới transaction. Không suy luận chỉ vì cấu hình executor thì mọi callback đều chuyển thread.

Với `@Async` trên một listener riêng, cũng cần `@EnableAsync`, executor, cơ chế xử lý lỗi async và hợp đồng side effect rõ ràng. `@Async` có thể là giải pháp ít ảnh hưởng hơn thay đổi toàn bộ multicaster, nhưng không tạo durable delivery.

## 12. @TransactionalEventListener không tự loại bỏ request latency

Một service:

~~~java
@Transactional
public void placeOrder(String id) {
    repository.save(new Order(id));
    publisher.publishEvent(new OrderPlaced(id));
}
~~~

Với `@EventListener` đồng bộ thông thường, callback chạy **bên trong transaction hiện tại**, có thể kéo dài thời gian giữ connection/lock và gây rollback nếu ném unchecked exception qua transaction boundary.

Đổi thành:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendReceipt(OrderPlaced event) {
    notificationService.send(event.id());
}
~~~

chỉ chuyển thời điểm xử lý sang sau commit thành công; callback vẫn có thể chạy **trên thread đang hoàn tất transaction** và kéo dài thời gian trước khi service trả về. Nó không có nghĩa “đã background” hoặc “không block request”.

Sau commit, một lỗi side effect không thể hoàn nguyên bản ghi đã commit. Nếu cần ghi DB từ callback sau commit, phải xác định transaction mới thích hợp; không giả định resource cũ sẽ commit các thay đổi mới.

Muốn công việc gửi email chắc chắn còn sau crash, dùng một persisted job hoặc transactional outbox được ghi cùng transaction business, rồi worker xử lý sau commit. Spring application event nội bộ không mặc nhiên có durable queue, replay hoặc exactly-once delivery.

## 13. Nested event làm độ trễ khó thấy hơn

Nếu một listener đồng bộ tự publish một event khác:

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    publisher.publishEvent(new InvoiceRequested(event.id()));
}
~~~

thì callback đó có thể **chưa trả về** cho tới khi toàn bộ listener đồng bộ của `InvoiceRequested` kết thúc. Đây là mã minh họa cần publisher và các record.

~~~text
publish(OrderPlaced)
   |
   +--> inventory()
   |
   +--> billing()
           |
           +--> publish(InvoiceRequested)
                      |
                      +--> generateInvoice()
                      +--> auditInvoice()
           |
           +--> return
   |
   +--> notification()
   |
   +--> publish returns
~~~

Vì vậy, latency của event gốc có thể bao gồm **cả cây các event lồng nhau**. Với recursive publish không có điều kiện dừng, còn có nguy cơ stack overflow hoặc duplicate processing. Khi tracing, đánh dấu từng event type và quan hệ parent-child theo contract, không gộp mọi công việc vào một con số “publisher slow”.

## 14. Đo đúng publish và processing latency

### 14.1. Publisher timer

~~~java
long started = System.nanoTime();

try {
    publisher.publishEvent(event);
} finally {
    long elapsedNanos = System.nanoTime() - started;
    metrics.recordPublish(elapsedNanos);
}
~~~

Đây là đoạn minh họa, cần `metrics` implementation. `finally` đo cả trường hợp lỗi. `System.nanoTime()` là monotonic duration clock trong cùng JVM; không dùng hai giá trị `nanoTime` từ các process khác nhau để tính transit latency.

### 14.2. Per-listener timer

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    long started = System.nanoTime();
    String outcome = "success";

    try {
        inventoryService.reserve(event.id());
    } catch (RuntimeException ex) {
        outcome = "error";
        throw ex;
    } finally {
        metrics.recordHandler(
                "inventory", outcome, System.nanoTime() - started);
    }
}
~~~

Đoạn trên là minh họa, cần bean `metrics` và inventory service. Nó giữ nguyên semantics ném lỗi, không che lỗi chỉ để đo duration.

### 14.3. Micrometer Timer.Sample

Nếu có `MeterRegistry`:

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";

try {
    inventoryService.reserve(event.id());
} catch (RuntimeException ex) {
    outcome = "error";
    throw ex;
} finally {
    sample.stop(Timer.builder("app.event.process")
            .tag("event", "order_placed")
            .tag("listener", "inventory")
            .tag("outcome", outcome)
            .register(registry));
}
~~~

Đây là **đoạn minh họa** cần Micrometer dependency, imports và các bean; không thuộc Gradle demo mục 8. Spring Framework không tự sinh Observation cho mọi `@EventListener` chỉ vì bạn dùng annotation. Nếu cần instrumentation, phải cấu hình/đặt timer đúng nơi.

### 14.4. Các metric cần tách

| Metric | Đo gì? |
| --- | --- |
| Publish Timer | Duration của `publishEvent`, không nhất thiết hoàn tất async |
| Handler Timer | Duration bên trong từng listener |
| Publish-to-start delay | Từ lúc tạo event tới lúc handler bắt đầu |
| Queue wait | Từ lúc task enqueue đến worker bắt đầu, nếu instrument executor |
| Inflight Gauge | Bao nhiêu callback đang xử lý |
| Error Counter | Bao nhiêu callback lỗi theo loại hữu hạn |
| Queue depth / rejected | Executor saturation |
| Business completion Timer | Tới khi side effect có xác nhận đúng hợp đồng |

Không đặt `eventId`, `userId`, email, exception message, raw URL hay payload vào metric tags: chúng tạo high cardinality và tăng chi phí TSDB. Dùng tag giá trị hữu hạn như event type, handler name, outcome/error kind. Correlation ID nên ở structured log/trace với bảo vệ dữ liệu phù hợp.

## 15. Khi nào tối ưu đồng bộ, khi nào thay đổi kiến trúc?

Trước khi chuyển async, hãy xác định **critical path** và nhu cầu nghiệp vụ:

1. **Listener có bắt buộc trước khi trả success không?** Nếu là validation/invariant phải được bảo đảm, không chuyển nền chỉ để giảm latency.
2. **Listener chỉ làm side effect thứ cấp?** Email/analytics có thể xử lý sau commit.
3. **Có thể tối ưu query hoặc I/O?** Projection, batch, cache hợp lý và giảm N+1 thường giảm tổng công việc.
4. **Có thể loại trừ xử lý trùng?** Hai listener cùng truy vấn một object graph hoặc cùng serialize payload có thể được thiết kế lại.
5. **Có phụ thuộc thứ tự?** Nếu có, không chạy song song tùy tiện.
6. **Có cần retry/replay sau crash?** Nếu có, persisted job/outbox/broker tốt hơn queue chỉ trong JVM.
7. **Có giới hạn tốc độ downstream?** Tăng concurrency có thể làm p99 và error rate tệ hơn.

Một ma trận lựa chọn:

| Nhu cầu | Hướng xử lý |
| --- | --- |
| Ba listener đều nhẹ và bắt buộc | Có thể giữ sync, tối ưu phần code |
| Một listener I/O chậm nhưng không bắt buộc response đợi | `@Async` hoặc worker, với error handling và transaction phù hợp |
| Nhiều listener độc lập và có đủ tài nguyên | Multicaster executor, pool bounded, đo completion |
| Work quan trọng không được mất khi restart | Persisted job/outbox + worker |
| Nhiều services cần event bền vững | Broker + schema + retry/DLQ/idempotency |
| Các bước có phụ thuộc nghiệp vụ | Workflow/service orchestration rõ ràng thay vì reliance on `@Order` |

Nếu dùng executor với queue unbounded, có thể nhanh ở lúc ít tải và gây OOM khi burst. Bounded concurrency/backpressure, timeout, saturation metrics và load testing phải được thiết kế cùng thay đổi async.

## 16. Chiến lược kiểm thử hiệu năng thực tế

Bộ JUnit ở mục 9 kiểm chứng **wiring và contract thực thi**, không thay thế benchmark.

Một benchmark/load test tốt nên:

- Warm up JVM và hệ thống phụ thuộc.
- Phát đủ số event để có distribution p50/p95/p99, không chỉ một lần.
- Đo per-listener duration, publisher duration và business completion.
- Quan sát DB pool, HTTP connection pool, CPU, GC, queue depth, rejected tasks.
- Test failure modes: listener throw, HTTP timeout, executor overload, process shutdown.
- Giữ workload tương đương khi so sánh sync và async.
- Kiểm tra correctness và số side effect cuối cùng, không chỉ latency.
- Đặt SLO từ yêu cầu nghiệp vụ; Spring không có “publishEvent phải dưới 10ms” chung.

Có thể dùng JFR, async-profiler, Micrometer + Actuator/Prometheus và OpenTelemetry/tracing tùy dự án. CPU profiler không nhất thiết thấy toàn bộ **wall-clock wait** của network; cần xem thread state hoặc timer tại dependency.

### Một test quan trọng khi nhiều listener

Giả sử một event có ba listener nhưng một trong ba bị skip bởi `condition` hoặc lỗi dừng multicast. Tổng `process.count` không chắc bằng ba lần `publish.count`. Hãy thống kê **theo listener/event/outcome** thay vì dùng phép chia thiếu ngữ cảnh để tuyên bố delivery thành công.

## 17. Những lỗi và ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| `publishEvent` luôn nhanh vì chỉ thông báo | Mặc định multicaster thường gọi listener sync trên caller thread |
| Nhiều `@EventListener` đồng nghĩa nhiều threads | Không; mặc định callback nối tiếp trong một lượt publish |
| `@Order` làm các listener chạy parallel | Không; nó điều khiển thứ tự gọi |
| Tổng latency luôn là max(listener durations) | Chỉ gần đúng ở một thiết kế parallel đủ tài nguyên; sync thường gần tổng |
| Listener thứ ba luôn được gọi dù listener thứ hai throw | Không với sync mặc định không ErrorHandler nuốt lỗi |
| Bật async là business đã hoàn tất khi publish trả về | Return thường chỉ xác nhận handoff/task submission |
| Dùng executor một worker làm mọi listener nhanh hơn | Có thể vẫn nối tiếp trong queue |
| Async không có cost | Queue, memory, scheduling, context propagation và retry đều có cost |
| `@Order` bảo đảm thứ tự hoàn tất async | Không có bảo đảm tổng quát |
| `@TransactionalEventListener(AFTER_COMMIT)` chắc chắn không block request | Callback vẫn có thể chạy trong transaction completion thread |
| Executor tự truyền JDBC transaction ThreadLocal | Không được giả định như vậy |
| `@Async` là hàng đợi bền vững | Không; task có thể mất khi process chết |
| Publisher throw nghĩa là toàn bộ side effect đã rollback | Side effect đã thực hiện trước đó có thể không đảo ngược được |
| Hai requests không thể publish đồng thời | “Nối tiếp” chỉ nói về listeners trong một lượt phát |
| Duration của một lần demo là SLO production | Cần histogram/load test, đo p95/p99 |
| Tăng pool càng lớn càng tốt | Có thể làm DB pool/rate limit quá tải |
| `Thread.sleep` là giải pháp performance | Trong demo chỉ để mô phỏng latency |
| Spring tự có Timer cho mọi `@EventListener` | Cần instrumentation phù hợp với sync/async semantics |

## 18. Checklist áp dụng và câu hỏi tự kiểm tra

**Checklist:**

- [ ] Đã xác nhận multicaster mặc định hay custom executor.
- [ ] Có thời lượng publish và per-listener timers.
- [ ] Các listener đồng bộ chậm đã được xác định bằng profiling.
- [ ] Không dùng `@Order` làm giải pháp giảm tổng work.
- [ ] Có kiểm tra exception path và tác dụng phụ đã hoàn tất một phần.
- [ ] Đã xem transaction duration, lock và connection usage.
- [ ] Biết critical listener nào phải giữ sync.
- [ ] Khi đổi sang async, có queue bounded, error policy, saturation monitoring.
- [ ] Không giả định async callback có transaction/security context của request.
- [ ] Nếu cần delivery bền vững, có outbox/job/broker và idempotency.
- [ ] Test sync/async rõ ràng, chờ async completion bằng latch/future chứ không sleep may rủi.
- [ ] Đo request latency **và** thời gian side effect hoàn tất dưới tải.
- [ ] Không dùng ID/event payload làm metric tag cardinality cao.
- [ ] Có rollout/rollback plan và so sánh failure rate trước/sau tối ưu.

**Câu hỏi 1.** Ba listener đồng bộ cần 40, 70 và 100 ms. Nếu dispatch overhead nhỏ, publish duration gần bao nhiêu?

**Đáp án:** Khoảng 210 ms, không phải 100 ms, vì các callback nối tiếp.

**Câu hỏi 2.** Đổi `@Order` có làm thời gian ba listener tự giảm không?

**Đáp án:** Không. Nó đổi thứ tự gọi; tổng công việc vẫn phải thực hiện.

**Câu hỏi 3.** Publisher async trả về trong 2 ms, listener gửi HTTP mất 600 ms. Có thể tuyên bố email hoàn thành trong 2 ms không?

**Đáp án:** Không. 2 ms là handoff; cần đo handler completion và side effect.

**Câu hỏi 4.** Vì sao test JUnit sync không cần `Thread.sleep` sau `publishEvent`?

**Đáp án:** Trong multicaster sync, method trả về sau khi listener được gọi xong nếu không có exception. Có thể assert dấu vết ngay sau lời gọi.

**Câu hỏi 5.** Khi nào tăng worker có thể làm chậm hơn?

**Đáp án:** Khi tranh chấp DB/CPU/locks, giới hạn pool hoặc downstream rate limits làm p99 tăng.

**Câu hỏi 6.** `AFTER_COMMIT` có luôn chạy ngoài request thread không?

**Đáp án:** Không. Callback transaction synchronization có thể chạy trên thread hoàn tất commit; nó chỉ chọn phase, không tự tạo worker.

**Câu hỏi 7.** Một listener đồng bộ throw khiến listener sau bị skip; publish nhanh hơn, có phải cải thiện hiệu năng thành công?

**Đáp án:** Không. Đó có thể là lỗi chức năng, cần quan sát exception và các side effect đã chạy một phần.

## 19. Tài liệu tham khảo

- Spring Framework — Standard and Custom Events, `@EventListener`, `@Order`, asynchronous listeners: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — `SimpleApplicationEventMulticaster`, đồng bộ mặc định và task executor: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — `ApplicationEventPublisher` và hợp đồng handoff: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 — `ApplicationListener.supportsAsyncExecution()`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationListener.html
- Spring Framework 6.2 — `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework Reference — Observability for Application Events: https://docs.spring.io/spring-framework/reference/integration/observability.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Micrometer — Timers: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Micrometer — Histograms and Percentiles: https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html
- Java 17 — `System.nanoTime()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/
