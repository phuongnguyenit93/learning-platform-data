# Cấu hình async executor cho Spring Framework Application Events

## 1. Mục tiêu và điều cần hiểu trước

Trong Spring Framework, `ApplicationEventPublisher.publishEvent(...)` giúp một component thông báo sự kiện tới các listener. Cách phân phối mặc định trong `ApplicationContext` thường dùng `SimpleApplicationEventMulticaster` **đồng bộ**: listener thông thường chạy trên thread đã phát event và có thể kéo dài thời gian phản hồi request.

Khi listener gửi email, gọi HTTP, tạo báo cáo hoặc làm công việc không cần nằm trong đường phản hồi của publisher, ta có thể cấu hình **asynchronous executor** để tách việc xử lý ra khỏi thread phát event. Tuy nhiên, thay đổi này tác động tới timing, exception propagation, transaction context, thứ tự xử lý, retry và shutdown. Một hệ thống “publish nhanh hơn” không có nghĩa mọi nhiệm vụ đã hoàn tất thành công.

Sau bài này, bạn sẽ:

- Phân biệt **async multicaster** với `@Async` trên từng `@EventListener`.
- Cấu hình `ThreadPoolTaskExecutor` có core/max pool, queue capacity, thread prefix và lifecycle rõ ràng.
- Biết Spring tìm bean tên `applicationEventMulticaster` như thế nào.
- Hiểu mối quan hệ giữa pool size, queue size, saturation và rejection policy.
- Viết ví dụ Java 17+ chạy được với Spring Framework, không cần Kafka hay Spring Boot.
- Viết JUnit 5 test chứng minh publisher trả về trong khi handler còn chờ, kiểm tra sync mặc định và lỗi async.
- Xử lý đúng exception, `@Order`, `@TransactionalEventListener`, ThreadLocal/MDC, graceful shutdown và observability.
- Quyết định khi nào executor trong process là đủ, khi nào cần outbox/job table/broker bền vững.

**Quy tắc đầu tiên:** `publishEvent(...)` là bước **handoff** tới cơ chế phát sự kiện. Nó không cam kết listener được xử lý đồng bộ hay hoàn thành khi phương thức trả về. Cách xử lý thực tế phụ thuộc multicaster, listener, proxy, executor và các transaction synchronizations.

## 2. Kiến trúc mặc định: vì sao publish có thể chặn?

Với các bean:

~~~java
public record OrderPlaced(String orderId) {}

@EventListener
public void onOrderPlaced(OrderPlaced event) {
    notificationService.send(event.orderId());
}
~~~

Đây chỉ là **mã minh họa**, cần bean Spring, `notificationService` và imports phù hợp.

Luồng mặc định:

~~~text
request thread
    |
    +--> publisher.publishEvent(OrderPlaced)
             |
             +--> SimpleApplicationEventMulticaster
                       |
                       +--> listener A -> return
                       +--> listener B -> return
                       +--> listener C -> return
             |
    <-------- publishEvent returns
    |
    +--> service returns
~~~

Nếu A mất 40 ms, B mất 100 ms và C mất 200 ms, publish duration có thể gần 340 ms cộng dispatch overhead. Một listener chậm có thể làm publisher chậm. `@Order` có thể sắp xếp thứ tự gọi nhưng không tự chuyển các listener thành parallel workers.

Trong Spring, event thường là **in-process notification**, không phải message broker có storage, acknowledgment, delivery guarantee hoặc dead-letter queue. Đổi multicaster sang async chỉ đổi cơ chế thực thi bên trong JVM; nó không bổ sung độ bền sự kiện.

## 3. Hai con đường asynchronous chính

| Tiêu chí | Multicaster có `TaskExecutor` | `@Async` trên listener |
| --- | --- | --- |
| Bật ở đâu? | Bean `applicationEventMulticaster` | `@EnableAsync` và `@Async` trên method/bean |
| Phạm vi | Các listener phù hợp **hỗ trợ async multicasting** | Chỉ những method được đánh dấu `@Async` |
| Thread khác? | Multicaster submit task qua executor | Spring async proxy submit method invocation |
| Cần `@EnableAsync`? | Không, nếu chỉ dùng multicaster executor | Có để bật annotation proxy/interceptor |
| Có cần `@EventListener`? | Có nếu dùng annotation listener | Có, cộng thêm `@Async` |
| Exception async | `ErrorHandler` của multicaster có thể thấy lỗi callback do nó thực thi | `AsyncUncaughtExceptionHandler` cho method void; lỗi không trở lại publisher |
| Transaction-bound listener | Có thể từ chối async tại multicaster để đăng ký synchronization đúng thread | Nếu xử lý target async, phải kiểm tra phase/context cẩn thận |
| Ảnh hưởng listener mới | Có thể tự được dispatch qua executor | Listener không có `@Async` vẫn giữ cách gọi hiện tại |
| Phù hợp | Muốn chính sách dispatch chung, có đánh giá tương thích listener | Muốn chọn lọc một vài side-effect listeners |

**Không cần bật cả hai cùng lúc** để “async hơn”. Nếu dùng executor ở multicaster **và** `@Async` ở method, có thể xảy ra hai tầng task submission, tốn scheduling/queue, làm việc đo lỗi, timing và propagation khó hơn. Mỗi event pipeline nên có một quyết định rõ về nơi tách thread.

### 3.1. Phân biệt các khái niệm

- `ApplicationEventPublisher` là API phát event.
- `ApplicationEventMulticaster` là engine gọi listener.
- `TaskExecutor` là abstraction thực thi task.
- `ThreadPoolTaskExecutor` là một implementation Spring có thread pool và queue.
- `@Async` là AOP/proxy-based method execution.
- `@TransactionalEventListener` ràng buộc một callback với phase transaction.
- Broker/outbox là hạ tầng **lưu và vận chuyển công việc bền vững**; nó không tự xuất hiện khi bật executor.

Khi tối ưu, đo riêng `publisher latency`, `handler processing duration` và thời gian tới khi side effect thực sự được xác nhận. Một phép đo quanh `publishEvent` không còn là end-to-end latency khi xử lý đã chuyển async.

## 4. Cấu hình bean multicaster đúng tên

Spring `ApplicationContext` nhận multicaster tùy chỉnh thông qua bean có tên **`applicationEventMulticaster`**. Nếu không có, context tạo multicaster mặc định.

Mẫu cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
public class EventExecutionConfig {

    @Bean(name = "applicationEventMulticaster")
    ApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventTaskExecutor")
            ThreadPoolTaskExecutor executor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        return multicaster;
    }
}
~~~

Đây là **đoạn cấu hình minh họa**: cần khai báo bean `eventTaskExecutor` và imports Spring. Ví dụ hoàn chỉnh có đầy đủ bên dưới.

Một số nhầm lẫn:

1. Bean đặt tên `asyncMulticaster` nhưng không đúng tên đặc biệt có thể **không thay thế** multicaster của context.
2. `setTaskExecutor(...)` cần nhận một `Executor`/`TaskExecutor` hợp lệ được quản lý vòng đời; không tạo một executor mới trên mỗi event.
3. Không phải mọi listener đều được chuyển thread. Spring 6.1+ có `ApplicationListener.supportsAsyncExecution()`; listener transaction synchronization có thể yêu cầu gọi phần đăng ký ở thread gốc.
4. `SimpleApplicationEventMulticaster` không biến event thành record trong queue bền vững.
5. Khi executor từ chối task ngay lúc submit, lời gọi publish có thể ném exception (ví dụ `TaskRejectedException`); nó không bảo đảm mọi publish luôn trả về bình thường.

Với ứng dụng Spring Boot, vẫn có thể khai báo bean này trong `@Configuration`. Nếu Boot hay thư viện khác cũng khai báo multicaster tên đó, cần điều phối ownership; không tạo hai bean trùng tên rồi dựa vào việc override bean definition.

## 5. Chọn ThreadPoolTaskExecutor và quy mô ban đầu

Ví dụ cấu hình có giới hạn:

~~~java
@Bean("eventTaskExecutor")
ThreadPoolTaskExecutor eventTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(16);
    executor.setKeepAliveSeconds(30);
    executor.setThreadNamePrefix("spring-events-");
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(10);
    return executor;
}
~~~

Đây là **đoạn cấu hình**, cần imports `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` và `java.util.concurrent.ThreadPoolExecutor`. Khi method trả bean trong Spring context, container quản lý khởi tạo và shutdown; đừng vừa quản lý bean vừa tạo/đóng executor thủ công bừa bãi.

Ý nghĩa từng thông số:

| Thông số | Vai trò |
| --- | --- |
| `corePoolSize=2` | Mức worker lõi, thường được tạo dần khi có task |
| `maxPoolSize=4` | Giới hạn worker tối đa khi queue đã đầy và cần mở rộng |
| `queueCapacity=16` | Tối đa số task chờ trong hàng đợi của executor |
| `keepAliveSeconds=30` | Thời gian idle cho non-core threads trước khi thu hẹp |
| `threadNamePrefix` | Dễ nhận diện worker trong thread dump/log |
| `AbortPolicy` | Từ chối task khi bão hòa thay vì âm thầm bỏ |
| `waitForTasksToCompleteOnShutdown` | Cố gắng hoàn tất task đã nhận khi shutdown |
| `awaitTerminationSeconds` | Cho phép shutdown chờ giới hạn trước khi container tiếp tục |

**Điểm quan trọng của ThreadPoolExecutor:** thường nó dùng **core workers trước, rồi queue, rồi mới mở rộng tới maxPoolSize** khi queue đầy. Với core=2, max=4, queue=16, không nên nghĩ 4 threads được dùng ngay khi có 4 task. Với queue cực lớn hoặc unbounded, số threads có thể gần như không vượt core, dẫn đến backlog tăng.

### 5.1. Queue capacity bằng 0 và queue lớn

`queueCapacity=0` trong `ThreadPoolTaskExecutor` dùng kiểu handoff trực tiếp (`SynchronousQueue`), không lưu task chờ theo cách queue có buffer. Điều này dễ tạo non-core threads tới max khi burst, nhưng cũng dễ bị reject khi max workers đều bận.

`queueCapacity` dương thường tạo queue hữu hạn. Queue quá lớn giúp chịu burst ngắn nhưng tăng waiting time, memory retention và độ trễ completion. Queue unbounded có nguy cơ quá tải bộ nhớ và khiến `maxPoolSize` ít có tác dụng.

Giá trị “2/4/16” chỉ là **cấu hình minh họa**, không phải chuẩn chung. Hãy sizing theo arrival rate, processing time, downstream concurrency/rate limits và lượng task chờ mà nghiệp vụ chịu được.

### 5.2. Little’s Law để nhìn backlog

Nếu arrival rate trung bình là `λ` events/giây và mỗi event mất `W` giây trong hệ thống, số lượng work-in-progress trung bình có thể được mô hình hóa bằng `L ≈ λ × W` trong điều kiện ổn định phù hợp.

Ví dụ: 100 task/giây, thời gian tổng từ enqueue đến hoàn tất 0,2 giây, thì trung bình khoảng 20 tasks đồng thời/đang nằm trong hệ thống. Đây là **mô hình**; khi worker không theo kịp, queue sẽ tăng và hệ thống không còn ở trạng thái ổn định. Sizing còn phải tính phân phối duration, burst, retry và tài nguyên chia sẻ.

## 6. Ví dụ đầy đủ Java 17+: async multicaster và @Async theo lựa chọn

Ví dụ này dùng Spring Framework thuần để thể hiện hai chiến lược riêng:

1. `MulticasterConfig`: một `SimpleApplicationEventMulticaster` sử dụng `ThreadPoolTaskExecutor`.
2. `AnnotationAsyncConfig`: multicaster mặc định, chỉ listener gắn `@Async("notificationExecutor")` chạy trên executor.

Một `ProcessingProbe` chứa `CountDownLatch` để chờ listener **bắt đầu**, giữ nó chưa hoàn tất, rồi giải phóng. Nhờ vậy test và main có thể chứng minh async handoff mà không phụ thuộc vào timing vài mili-giây dễ sai trên máy CI.

Ví dụ không có broker, database hay transaction; đó là dụng ý để thấy rõ ranh giới thread. Khi cần delivery bền vững, các mục sau chỉ ra thiết kế mở rộng.

### 6.1. Cấu trúc dự án

~~~text
spring-event-executor-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           └── AsyncEventExecutorDemo.java
    └── test/
        └── java/
            └── demo/
                └── AsyncEventExecutorDemoTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'spring-event-executor-demo'
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
    mainClass = 'demo.AsyncEventExecutorDemo'
}

test {
    useJUnitPlatform()
}
~~~

`spring-context` cung cấp `AnnotationConfigApplicationContext`, `@EventListener` và `@EnableAsync` support thông qua các Spring dependencies. Ví dụ cố định Spring 6.2.15 để có baseline cụ thể; khi áp dụng Spring Boot, ưu tiên dependency management/BOM của Boot thay vì tự ghim phiên bản Spring khác nhau.

### 6.2. File Java hoàn chỉnh

Lưu **`src/main/java/demo/AsyncEventExecutorDemo.java`**:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class AsyncEventExecutorDemo {

    private AsyncEventExecutorDemo() {}

    public record OrderPlaced(String orderId) {}
    public record FailingSignal() {}

    public static final class ProcessingProbe {
        private final CountDownLatch started = new CountDownLatch(1);
        private final CountDownLatch release = new CountDownLatch(1);
        private final CountDownLatch finished = new CountDownLatch(1);
        private final AtomicInteger processed = new AtomicInteger();
        private final AtomicReference<String> workerThread =
                new AtomicReference<>("");

        public void handle(OrderPlaced event) {
            workerThread.set(Thread.currentThread().getName());
            started.countDown();

            try {
                if (!release.await(8, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Probe was not released");
                }
                processed.incrementAndGet();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Probe interrupted", ex);
            } finally {
                finished.countDown();
            }
        }

        public boolean awaitStarted(long seconds)
                throws InterruptedException {
            return started.await(seconds, TimeUnit.SECONDS);
        }

        public boolean awaitFinished(long seconds)
                throws InterruptedException {
            return finished.await(seconds, TimeUnit.SECONDS);
        }

        public void release() {
            release.countDown();
        }

        public int processedCount() {
            return processed.get();
        }

        public String workerThread() {
            return workerThread.get();
        }
    }

    // Dùng ở MulticasterConfig và SynchronousConfig.
    public static final class OrdinaryListener {
        private final ProcessingProbe probe;

        public OrdinaryListener(ProcessingProbe probe) {
            this.probe = probe;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            probe.handle(event);
        }
    }

    // Chỉ dùng ở AnnotationAsyncConfig.
    public static class AnnotatedAsyncListener {
        private final ProcessingProbe probe;

        public AnnotatedAsyncListener(ProcessingProbe probe) {
            this.probe = probe;
        }

        @EventListener
        @Async("notificationExecutor")
        public void onOrderPlaced(OrderPlaced event) {
            probe.handle(event);
        }
    }

    public static final class ErrorProbe {
        private final CountDownLatch observed = new CountDownLatch(1);
        private final AtomicInteger count = new AtomicInteger();

        public void record(Throwable error) {
            count.incrementAndGet();
            observed.countDown();
        }

        public boolean awaitError(long seconds)
                throws InterruptedException {
            return observed.await(seconds, TimeUnit.SECONDS);
        }

        public int errorCount() {
            return count.get();
        }
    }

    public static final class FailingListener {
        @EventListener
        public void fail(FailingSignal event) {
            throw new IllegalStateException("simulated listener failure");
        }
    }

    private static ThreadPoolTaskExecutor boundedExecutor(String prefix) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix(prefix);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Configuration(proxyBeanMethods = false)
    public static class MulticasterConfig {
        @Bean
        public ProcessingProbe processingProbe() {
            return new ProcessingProbe();
        }

        @Bean("eventTaskExecutor")
        public ThreadPoolTaskExecutor eventTaskExecutor() {
            return boundedExecutor("spring-events-");
        }

        // Tên bean đặc biệt do ApplicationContext tìm.
        @Bean(name = "applicationEventMulticaster")
        public ApplicationEventMulticaster applicationEventMulticaster(
                @Qualifier("eventTaskExecutor")
                ThreadPoolTaskExecutor executor) {
            SimpleApplicationEventMulticaster multicaster =
                    new SimpleApplicationEventMulticaster();
            multicaster.setTaskExecutor(executor);
            return multicaster;
        }

        @Bean
        public OrdinaryListener ordinaryListener(ProcessingProbe probe) {
            return new OrdinaryListener(probe);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SynchronousConfig {
        @Bean
        public ProcessingProbe processingProbe() {
            return new ProcessingProbe();
        }

        // Không khai báo custom multicaster: đồng bộ mặc định.
        @Bean
        public OrdinaryListener ordinaryListener(ProcessingProbe probe) {
            return new OrdinaryListener(probe);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    public static class AnnotationAsyncConfig {
        @Bean
        public ProcessingProbe processingProbe() {
            return new ProcessingProbe();
        }

        @Bean("notificationExecutor")
        public ThreadPoolTaskExecutor notificationExecutor() {
            return boundedExecutor("notify-");
        }

        @Bean
        public AnnotatedAsyncListener annotatedAsyncListener(
                ProcessingProbe probe) {
            return new AnnotatedAsyncListener(probe);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ErrorConfig {
        @Bean
        public ErrorProbe errorProbe() {
            return new ErrorProbe();
        }

        @Bean("errorExecutor")
        public ThreadPoolTaskExecutor errorExecutor() {
            return boundedExecutor("error-");
        }

        @Bean(name = "applicationEventMulticaster")
        public ApplicationEventMulticaster applicationEventMulticaster(
                @Qualifier("errorExecutor")
                ThreadPoolTaskExecutor executor,
                ErrorProbe errors) {
            SimpleApplicationEventMulticaster multicaster =
                    new SimpleApplicationEventMulticaster();
            multicaster.setTaskExecutor(executor);
            multicaster.setErrorHandler(errors::record);
            return multicaster;
        }

        @Bean
        public FailingListener failingListener() {
            return new FailingListener();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             MulticasterConfig.class)) {

            ProcessingProbe probe =
                    context.getBean(ProcessingProbe.class);

            context.publishEvent(new OrderPlaced("ORD-42"));

            try {
                if (!probe.awaitStarted(5)) {
                    throw new IllegalStateException(
                            "Listener did not start");
                }

                // publishEvent đã trả về, handler vẫn chờ release.
                System.out.println("publisher.returned=true");
                System.out.println(
                        "listener.uses.executor="
                        + probe.workerThread().startsWith("spring-events-"));
                System.out.println(
                        "processed.before.release=" + probe.processedCount());
            } finally {
                probe.release();
            }

            if (!probe.awaitFinished(5)) {
                throw new IllegalStateException(
                        "Listener did not finish");
            }

            System.out.println(
                    "processed.after.release=" + probe.processedCount());
        }
    }
}
~~~

### 6.3. Phân tích code và tính đúng

`ProcessingProbe` cố ý giữ listener ở một `CountDownLatch`. Nó signal đã bắt đầu rồi đợi `release`. Vì `main` chỉ gọi `awaitStarted` **sau khi `publishEvent` trả về**, ta biết nếu main đến được đây và listener còn đang chờ release, publisher không đợi handler hoàn tất.

- `MulticasterConfig` gắn executor vào `SimpleApplicationEventMulticaster`. `OrdinaryListener` **không có** `@Async` nhưng vẫn chạy trên worker.
- `SynchronousConfig` bỏ custom multicaster; cùng `OrdinaryListener` chạy đồng bộ trên publisher thread.
- `AnnotationAsyncConfig` giữ multicaster mặc định nhưng đánh dấu `@Async("notificationExecutor")` ở method; cần `@EnableAsync` để tạo proxy. `proxyTargetClass=true` giúp dùng CGLIB proxy cho class không có interface.
- `ErrorConfig` dùng `ErrorHandler` để ghi nhận exception ném từ handler được multicaster chạy trên worker, không để lỗi bị mất trong đường lỗi của demo.
- `boundedExecutor(...)` trả executor cho Spring container quản lý; mỗi context có executor riêng và được đóng khi context đóng.
- `finally` trong `main` bảo đảm release ngay cả khi assert/timing trong demo thất bại.

Để giữ mã minh họa gọn, `ProcessingProbe` không kiểm tra order ID và không nối nghiệp vụ thật. Trong ứng dụng thực, listener xử lý event data với error policy; latches chỉ nên xuất hiện ở kiểm thử, không được dùng để chặn hàng loạt worker trong production.

### 6.4. Chạy và stdout dự kiến

Trong thư mục `spring-event-executor-demo`, với JDK 17+ và Gradle:

~~~bash
gradle -q run
~~~

Nếu đã dùng Gradle Wrapper, có thể chạy `./gradlew -q run` (Linux/macOS) hoặc `gradlew.bat -q run` (Windows).

Các dòng do `main` chủ động in ra nếu listener bắt đầu và hoàn tất thành công:

~~~text
publisher.returned=true
listener.uses.executor=true
processed.before.release=0
processed.after.release=1
~~~

Đây là kết quả **logic dự kiến**, không phải stdout ghi nhận từ lần build đã thực thi trong môi trường của bài. Thời điểm nhận task phụ thuộc scheduling và tải hệ thống; vì vậy ví dụ dùng timeout 5 giây thay vì khẳng định event sẽ bắt đầu sau đúng 10 ms.

Nếu các task bị starvation, máy quá tải hoặc lỗi setup, chương trình có thể ném exception và không in đủ bốn dòng. Test không nên coi bất kỳ lỗi timeout nào là thành công.

## 7. JUnit 5: bốn bài test có kiểm soát

Tạo file **`src/test/java/demo/AsyncEventExecutorDemoTest.java`**:

~~~java
package demo;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AsyncEventExecutorDemoTest {

    @Test
    @Timeout(15)
    void multicasterAsyncHandoffCompletesAfterRelease()
            throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AsyncEventExecutorDemo.MulticasterConfig.class)) {

            var probe = context.getBean(
                    AsyncEventExecutorDemo.ProcessingProbe.class);

            context.publishEvent(
                    new AsyncEventExecutorDemo.OrderPlaced("A"));

            try {
                assertTrue(probe.awaitStarted(5));
                assertEquals(0, probe.processedCount());
                assertTrue(probe.workerThread()
                        .startsWith("spring-events-"));
            } finally {
                probe.release();
            }

            assertTrue(probe.awaitFinished(5));
            assertEquals(1, probe.processedCount());
        }
    }

    @Test
    @Timeout(15)
    void defaultMulticasterWaitsForListenerToFinish() throws Exception {
        ExecutorService publisherThread =
                Executors.newSingleThreadExecutor();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AsyncEventExecutorDemo.SynchronousConfig.class)) {

            var probe = context.getBean(
                    AsyncEventExecutorDemo.ProcessingProbe.class);

            Future<?> publication = publisherThread.submit(() ->
                    context.publishEvent(
                            new AsyncEventExecutorDemo.OrderPlaced("B")));

            try {
                assertTrue(probe.awaitStarted(5));

                // Lời gọi publish ở thread riêng vẫn đang chờ.
                assertFalse(publication.isDone());
            } finally {
                probe.release();
            }

            publication.get(5, TimeUnit.SECONDS);
            assertEquals(1, probe.processedCount());
        } finally {
            publisherThread.shutdownNow();
        }
    }

    @Test
    @Timeout(15)
    void annotationAsyncUsesNamedExecutor() throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AsyncEventExecutorDemo.AnnotationAsyncConfig.class)) {

            var probe = context.getBean(
                    AsyncEventExecutorDemo.ProcessingProbe.class);

            // Multicaster mặc định, chỉ listener này gắn @Async.
            context.publishEvent(
                    new AsyncEventExecutorDemo.OrderPlaced("C"));

            try {
                assertTrue(probe.awaitStarted(5));
                assertTrue(probe.workerThread().startsWith("notify-"));
                assertEquals(0, probe.processedCount());
            } finally {
                probe.release();
            }

            assertTrue(probe.awaitFinished(5));
            assertEquals(1, probe.processedCount());
        }
    }

    @Test
    @Timeout(15)
    void asyncListenerFailureGoesToMulticasterErrorHandler()
            throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AsyncEventExecutorDemo.ErrorConfig.class)) {

            var errors = context.getBean(
                    AsyncEventExecutorDemo.ErrorProbe.class);

            // Không kỳ vọng exception từ worker quay về caller.
            context.publishEvent(
                    new AsyncEventExecutorDemo.FailingSignal());

            assertTrue(errors.awaitError(5));
            assertEquals(1, errors.errorCount());
        }
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

### 7.1. Các điều được chứng minh

| Test | Điều kiểm chứng | Điều không được suy ra |
| --- | --- | --- |
| `multicasterAsyncHandoffCompletesAfterRelease` | Multicaster submit và worker còn chờ khi publish trả về | Task đã commit side effect ngoài ứng dụng |
| `defaultMulticasterWaitsForListenerToFinish` | Không có executor, publisher thread đợi listener release | Toàn bộ hệ thống chỉ có một publisher thread |
| `annotationAsyncUsesNamedExecutor` | `@Async` chạy trên executor tên `notificationExecutor` | Mọi listener khác tự async |
| `asyncListenerFailureGoesToMulticasterErrorHandler` | Lỗi từ callback chạy qua async multicaster được ErrorHandler ghi nhận | Lỗi `@Async` do proxy chạy sau đó cũng qua cùng handler |

Test sync cố ý chạy publisher trong một test-owned thread để test method còn điều khiển latch. Nó **không phải** cách cấu hình event sync trong production. Latches và timeout giúp tránh assertion theo thời gian tuyệt đối nhưng vẫn cần tài nguyên CI đủ để worker được scheduling.

### 7.2. Tại sao không assert mili-giây?

Một test đo `publishEvent` mất ít hơn 5 ms có thể fail trên CI chậm, dù async semantics đúng. Ngược lại, một timer 200 ms thấp cũng không bảo đảm handler được xử lý. Latch xác nhận **thời điểm tương đối**: handler đã bắt đầu nhưng chưa hoàn tất khi caller tiếp tục.

Muốn đánh giá hiệu năng thật, dùng load test/JFR/JMH phù hợp, thu p50/p95/p99, queue wait và completion latency ở tải đại diện.

## 8. Sizing executor theo workload

### 8.1. Phân biệt CPU-bound và I/O-bound

**CPU-bound** như tính toán mã hóa hoặc chuyển đổi dữ liệu lớn thường không được lợi khi tăng worker vượt xa số CPU khả dụng. **I/O-bound** như HTTP/DB wait có thể cần nhiều concurrency hơn, nhưng phải tính giới hạn connection pool, remote API rate limit và memory.

Cấu hình khởi đầu không phải công thức cứng. Hãy đo:

- Arrival rate: bao nhiêu event/s vào pipeline?
- Average, p95/p99 handler time.
- Số lượng destination và độ dài mỗi bước phụ thuộc.
- Số DB connections/HTTP connections còn trống.
- Queue capacity và mức backlog tối đa chấp nhận.
- Tỷ lệ retry, timeout, rejected tasks.
- SLA end-to-end, không chỉ thời gian publish.

### 8.2. Tác động của queue trước max threads

Với pool core=2/max=4/queue=16:

~~~text
1..2 tasks đồng thời:
    các core threads có thể đảm nhận

core busy, queue còn chỗ:
    task mới xếp hàng, không nhất thiết tạo worker thứ 3

queue đã đầy:
    executor có thể tăng lên worker thứ 3, thứ 4

pool=4 đang bận, queue=16 đầy:
    task mới bị reject theo chính sách
~~~

Điều này giải thích vì sao một cấu hình `core=2,max=32,queue=100000` có thể chỉ dùng 2 worker phần lớn thời gian và tạo hàng đợi chờ rất dài. Không gọi `maxPoolSize` là concurrency luôn có sẵn.

### 8.3. Nhiều listener, một pool hay nhiều pool?

Một event có thể kích hoạt inventory, billing, email và analytics. Nếu cùng một executor, một nhóm listener bị nghẽn có thể làm nhóm khác đói worker.

Các lựa chọn:

- **Một pool chung** khi workloads tương tự, cùng priority và cùng failure domain.
- **Pool riêng** theo loại side effect quan trọng nếu cần isolation (ví dụ email I/O và analytics CPU).
- **Pipeline/workflow rõ ràng** khi một handler phải chờ output của handler khác.
- **Broker/job table/outbox** nếu cần durable queue, retry và scheduling giữa processes.

Không tạo executor vô hạn theo từng listener; mỗi pool tiêu tốn threads, memory và connections. Chia pool phải dựa vào isolation và năng lực giám sát, không chỉ theo tên class.

## 9. Rejection policy và backpressure

Khi executor bão hòa, phải lựa chọn một hợp đồng minh bạch:

| Policy / hướng xử lý | Hành vi | Rủi ro |
| --- | --- | --- |
| `AbortPolicy` | Reject task, Spring có thể bọc thành `TaskRejectedException` | Caller phải xử lý lỗi; nếu bỏ qua có thể mất công việc |
| `CallerRunsPolicy` | Thread submit có thể chạy task | Publisher bất ngờ phải chờ handler, làm p99 tăng |
| `DiscardPolicy` | Có thể bỏ task âm thầm | Mất event mà thiếu tín hiệu, thường không phù hợp |
| `DiscardOldestPolicy` | Có thể bỏ task cũ | Phá thứ tự/tính đầy đủ của công việc |
| Giới hạn producer rate | Giảm lưu lượng trước executor | Cần cơ chế reject/backpressure API rõ |
| Persisted work/outbox | Lưu trước rồi worker xử lý theo năng lực | Phức tạp hơn, cần retry/idempotency |

**Lưu ý riêng về lỗi:** `SimpleApplicationEventMulticaster#setErrorHandler` xử lý exception của listener được multicaster gọi, nhưng **task submission rejection** có thể phát sinh ngay khi gọi `executor.execute(...)` và không nhất thiết được một handler lỗi listener bao quát. Test riêng đường queue saturation để biết lỗi quay về publisher thế nào.

Một application không nên tự chuyển sang `DiscardPolicy` chỉ để dashboard không còn báo rejected. Như vậy là che việc mất work, không phải cải thiện độ tin cậy.

### 9.1. Retry không được unbounded

Khi dependency bị lỗi, retry ngay trên cùng executor có thể làm tăng tải và giữ worker lâu hơn. Nếu cần retry:

- Chọn lỗi nào retryable.
- Dùng exponential backoff có jitter và giới hạn attempts.
- Có timeout cho mỗi attempt.
- Dùng idempotency key khi side effect có thể thực hiện lặp.
- Theo dõi retry backlog, age và eventual outcome.
- Đưa công việc không phục hồi vào dead-letter/quarantine theo chính sách.

Với async in-process executor, nếu process crash trước retry thì task vẫn có thể mất. Đừng suy diễn rằng retry loop tự tạo durability.

## 10. ErrorHandler của multicaster và AsyncUncaughtExceptionHandler

Hai đường lỗi khác nhau:

### 10.1. Async multicaster

Một listener thường:

~~~java
@EventListener
public void handle(OrderPlaced event) {
    if (shouldFail(event)) {
        throw new IllegalStateException("business listener failed");
    }
}
~~~

Khi multicaster submit việc gọi method này lên worker, exception của method có thể được xử lý bởi `SimpleApplicationEventMulticaster#setErrorHandler(...)`:

~~~java
multicaster.setErrorHandler(error -> {
    errorMetrics.increment();
    safeLogger.error("Event listener failed", error);
});
~~~

Các đoạn này là **minh họa**, cần bean và implementation metrics/logger. Nếu handler nuốt exception, publisher có thể không nhận biết lỗi; các công việc quan trọng cần retry/ack semantics riêng.

Trong demo `ErrorConfig`, `ErrorProbe` ghi nhận lỗi không in event payload và test chờ callback. `ErrorHandler` không thay thế hệ thống retry/dead-letter.

### 10.2. @Async trên listener

Khi Spring async proxy thực thi một method `@Async` trả `void` trên worker, exception không truyền trực tiếp về caller. Spring cung cấp `AsyncUncaughtExceptionHandler` để xử lý dạng này.

Ví dụ cấu hình độc lập:

~~~java
@Configuration
@EnableAsync
public class AsyncErrorConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (ex, method, params) -> {
            // Ghi metric/log an toàn, không in raw params chứa PII.
            auditError(ex.getClass().getSimpleName());
        };
    }
}
~~~

Đây là **đoạn minh họa**, cần import `AsyncConfigurer`, `AsyncUncaughtExceptionHandler` và implementation `auditError`; không thuộc file runnable mục 6. Với `Future`/`CompletableFuture`, cách nhận lỗi có thể thông qua future kết quả thay vì uncaught handler.

**Không giả định một `ErrorHandler` của multicaster sẽ thu mọi exception phát sinh sau đó trong `@Async` proxy.** Phải test chính đường lỗi đang sử dụng.

### 10.3. Outcome của publisher khác outcome của handler

~~~text
publishEvent returned normally
      |
      +--> task queued
             |
             +--> worker runs
                    |
                    +--> handler throws
~~~

`publishEvent` không ném lỗi trong trường hợp này không có nghĩa handler thành công. Nếu nghiệp vụ yêu cầu phản hồi dựa trên kết quả side effect, phải thay đổi contract cho rõ: chờ completion/future hoặc dùng workflow có trạng thái, thay vì trả “đã gửi email” ngay sau handoff.

## 11. @Order, listener phụ thuộc và tính đồng thời

`@Order` có thể quyết định thứ tự **dispatch/invocation** khi cùng phase. Khi có executor với nhiều workers, nó **không bảo đảm thứ tự hoàn tất**.

Ví dụ:

~~~text
@Order(10) Inventory    |---- 120 ms ----|
@Order(20) Billing      |--  40 ms --|
@Order(30) Notification |------ 200 ms ------|

Có thể Billing hoàn tất trước Inventory.
~~~

Nếu Billing cần inventory result, không nên chỉ thêm `@Order` rồi bật async. Hãy:

- Gộp những bước có quan hệ bắt buộc vào service orchestration rõ ràng.
- Dùng `CompletableFuture`/structured completion và timeout nếu cùng process.
- Dùng state machine/outbox/broker với sequence/version khi workflow dài hoặc bền vững.
- Nếu cần ordering theo aggregate, dùng serialization/partition key thích hợp thay vì trông cậy vào scheduling của thread pool.

Một event có ba listener không có nghĩa phải có ba threads. Pool có thể chỉ có một worker hoặc hai worker bận; completion time phụ thuộc queue, concurrency và tài nguyên chung.

## 12. @TransactionalEventListener: ngoại lệ quan trọng

Spring Framework 6.1+ có `ApplicationListener.supportsAsyncExecution()`. Các `TransactionalApplicationListener` cần đăng ký transaction synchronization **trong thread liên quan đến transaction**, nên không hỗ trợ async dispatch tại multicaster cho phần đăng ký đó. Phần target processing của chúng có thể có cơ chế bất đồng bộ riêng, nhưng không được bỏ qua phase lifecycle.

Ví dụ:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    emailService.send(event.orderId());
}
~~~

Đoạn này minh họa, cần bean, transaction manager và event class.

Với imperative JDBC/JPA transaction:

- Transaction context thường được gắn với thread thông qua `TransactionSynchronizationManager`.
- Khi `publishEvent` diễn ra trong transaction, listener transaction-bound cần đăng ký callback đúng nơi.
- `AFTER_COMMIT` chỉ xảy ra sau commit thành công; nếu rollback, callback này không chạy.
- Callback `AFTER_COMMIT` thông thường vẫn có thể chạy trên thread đang hoàn tất transaction và **vẫn block request**.
- Nếu không có transaction phù hợp và `fallbackExecution=false`, listener transaction-bound không được gọi.
- Truy cập database/side effect ở `AFTER_COMMIT` cần transaction semantics riêng; nếu ghi mới, thường cần `REQUIRES_NEW` qua proxy thích hợp.

**Bật executor cho multicaster không phải phép bảo đảm mọi transactional listener sẽ chạy async.** Đây là một lý do phải test transaction behavior sau khi thay cấu hình.

### 12.1. Gắn @Async vào transactional listener

Có các thiết kế gắn `@Async` lên phương thức `@TransactionalEventListener` để target listener chạy trên worker sau khi synchronization được kích hoạt. Nhưng:

- Phải xác nhận phase registration trên thread transaction.
- Async execution có thể không còn ThreadLocal transaction gốc.
- Exception worker không rollback transaction đã commit.
- Nếu cần ghi DB, mở transaction mới và kiểm thử.
- Không để logic chọn success/failure của transaction phụ thuộc vào task chưa hoàn thành.

Khi yêu cầu tính đúng cao, outbox hoặc persisted job thường đáng tin hơn giải pháp ghép annotation mà không kiểm tra crash/retry.

### 12.2. Reactive transaction

Reactive transaction sử dụng Reactor Context thay vì thread-local JDBC context. Spring hỗ trợ `TransactionalEventPublisher` để event mang transaction context phù hợp. Không lấy ví dụ JDBC `TransactionTemplate` rồi khẳng định nó kiểm tra được R2DBC reactive path.

Nếu xử lý event reactive, cần phân biệt `Mono` **được tạo** và `Mono` **được subscribe/hoàn tất**. Một listener trả về `Mono` mà Spring không subscribe không thực sự tạo side effect. Dùng reactive transaction operator/StepVerifier trong test phù hợp.

## 13. @EnableAsync, AOP proxy và lỗi self-invocation

Một cấu hình chọn lọc:

~~~java
@Configuration
@EnableAsync
class AsyncSupport {

    @Bean("notificationExecutor")
    ThreadPoolTaskExecutor notificationExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("notification-");
        return executor;
    }
}
~~~

Listener:

~~~java
@Component
class NotificationListener {

    @Async("notificationExecutor")
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        sendNotification(event);
    }
}
~~~

Hai đoạn là **minh họa** cần imports/bean và method `sendNotification`. `@EnableAsync` bật hỗ trợ annotation async. Để method chạy qua proxy, nên dùng public method trên một Spring-managed bean được gọi từ bên ngoài qua proxy; nếu cùng bean gọi `this.asyncMethod(...)` trực tiếp, self-invocation không đi qua proxy Spring AOP thông thường.

Nếu có nhiều executor, luôn chỉ rõ `@Async("notificationExecutor")` (bean name/qualifier) thay vì mặc định ngẫu nhiên chọn pool nào. Nếu không có executor phù hợp hoặc bean không được Spring quản lý, ứng dụng có thể dùng cơ chế fallback không như mong đợi hoặc không async như bạn nghĩ.

Một callback `@Async @EventListener` không thể tạo event mới bằng **return value** như một `@EventListener` đồng bộ; nếu muốn phát event tiếp theo, inject `ApplicationEventPublisher` và gọi `publishEvent` tường minh. Cần xử lý lỗi và completion của bước đó riêng.

## 14. Context propagation: trace, MDC, security và transaction

Trong sync listener, thread-local MDC và current trace context của publisher thường còn trên cùng thread. Khi chuyển qua worker:

~~~text
request thread:
   MDC["requestId"] = req-123
   publish event
   return

event executor worker:
   MDC["requestId"] = ?  (thường không tự có)
~~~

Đừng tự truyền toàn bộ `ThreadLocal` hay `SecurityContext` bằng một global mutable map, vì worker thread được tái sử dụng và có thể làm lộ context giữa người dùng.

Spring có `TaskDecorator` để bọc runnable trên executor. Với `ContextPropagatingTaskDecorator` và Micrometer Context Propagation được cấu hình phù hợp, các context hỗ trợ có thể được snapshot/restore:

~~~java
@Bean("eventTaskExecutor")
ThreadPoolTaskExecutor eventTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(32);
    executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator());
    return executor;
}
~~~

Đây là **biến thể minh họa**, không thêm trực tiếp vào Gradle demo; cần `org.springframework.core.task.support.ContextPropagatingTaskDecorator` và dependency `io.micrometer:context-propagation` phù hợp. Context propagation giúp các scope/log/trace được hỗ trợ, **không cấp quyền mới**, không bảo đảm authentication/authorization đúng cho mọi downstream và **không mang một JDBC transaction đang mở sang thread worker**.

Nếu event cần correlation ID nghiệp vụ để qua restart/queue/broker, đặt ID đó vào một event context immutable hoặc outbox record, không chỉ ở MDC. Sau khi worker xử lý, context phải được cleanup/restored để không rò dữ liệu sang task kế tiếp.

## 15. Graceful shutdown và deploy an toàn

Một lỗi khó thấy: ứng dụng nhận event, submit task và shutdown trước khi task hoàn tất. Nếu executor trong process chưa xả queue, công việc sẽ mất.

`ThreadPoolTaskExecutor` có một số cấu hình lifecycle:

- `setWaitForTasksToCompleteOnShutdown(true)`: cố gắng cho các task đã nhận tiếp tục hoàn tất thay vì hủy ngay.
- `setAwaitTerminationSeconds(n)`: thời gian chờ giới hạn trong giai đoạn shutdown container.
- Tên thread prefix hỗ trợ xem task còn chạy trong logs/thread dumps.
- Context lifecycle/phase của Spring 6.2 có ảnh hưởng đến thời điểm stop/close; cần test bằng cấu hình chính xác của ứng dụng.

**Đừng suy diễn shutdown hook = durable processing.** Process có thể bị kill -9, crash, OOM hoặc mất điện; không có cơ hội xả queue. Nếu nghiệp vụ không chấp nhận mất event, phải persist work trước khi trả success.

### 15.1. Deploy rolling restart

Khi chạy Kubernetes hoặc một orchestrator khác:

1. Ngừng nhận work mới theo readiness/traffic policy.
2. Cho worker xử lý phần queue đang nhận trong grace period.
3. Có metrics trên active/queued/rejected tasks.
4. Với task vượt grace period, dựa vào durable work store để recover.
5. Không dùng stop timeout vô hạn vì có thể làm deploy kẹt.
6. Kiểm tra trường hợp message đã gửi nhưng chưa được ACK/mark done, cần idempotency để không thực hiện side effect hai lần.

Nếu chỉ dùng in-memory executor, không thể cam kết zero-loss khi container bị kill cưỡng bức.

## 16. Quan sát async executor và listener latency

### 16.1. Metric nên tách

| Metric | Câu hỏi |
| --- | --- |
| `app.event.publish.duration` | Lời gọi `publishEvent` mất bao lâu? |
| `app.event.handler.duration` | Từng handler xử lý bao lâu? |
| `app.event.handler.outcome` | Handler thành công/thất bại bao nhiêu lần? |
| `app.event.start.delay` | Từ mốc tạo event đến lúc handler bắt đầu? |
| `app.event.executor.queue.depth` | Bao nhiêu task đang chờ? |
| `app.event.executor.active` | Bao nhiêu worker đang bận? |
| `app.event.executor.rejected` | Bao nhiêu task bị từ chối? |
| `app.event.business.complete` | Bao lâu tới khi side effect được xác nhận? |

Đây là **tên metric ứng dụng gợi ý**, không phải tất cả được Spring Framework tự xuất. `ThreadPoolTaskExecutor` có các chỉ số như `getActiveCount()`, `getPoolSize()` và `getThreadPoolExecutor().getQueue().size()` để quan sát nếu có quyền truy cập bean và API phiên bản phù hợp.

Micrometer `Timer` thích hợp đo duration, còn `Counter` thích hợp cho occurrence. Ví dụ:

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";

try {
    handler.process(event);
} catch (RuntimeException ex) {
    outcome = "error";
    throw ex;
} finally {
    sample.stop(Timer.builder("app.event.handler.duration")
            .tag("handler", "notification")
            .tag("outcome", outcome)
            .register(registry));
}
~~~

Đây là **đoạn minh họa** cần Micrometer dependency, `MeterRegistry` và handler thực; không nằm trong Gradle demo mục 6. Đo trong phần thân handler, không chỉ quanh `publishEvent`.

### 16.2. Queue wait khác start delay

Nếu timestamp được lấy từ lúc tạo event, hiệu `handlerStart - eventCreated` gồm nhiều thành phần: tạo payload, dispatch, enqueue, queue wait và có thể transaction waiting. Nó **không phải queue wait thuần**.

Muốn queue wait chuẩn, instrument executor từ lúc task được enqueue (theo điểm đo được định nghĩa rõ) đến ngay lúc worker bắt đầu thực hiện. Với transport khác process, không truyền `System.nanoTime()` giữa các JVM để tính duration vì mốc monotonic không đồng bộ.

### 16.3. Tags và cardinality

Không đưa `eventId`, `orderId`, `userId`, `email`, trace ID hoặc payload làm metric tags. Dùng `event_type`, `handler`, `outcome`, `error_kind` với tập giá trị giới hạn. IDs có thể ở structured logs/traces theo chính sách dữ liệu, redaction, access control và retention.

### 16.4. Dashboards và alerts

Theo dõi cùng lúc:

- Publisher p95/p99 và request p95/p99.
- Handler p95/p99 theo tên listener.
- Queue depth và rejection rate.
- End-to-end completion latency.
- Số lượng task đã xử lý thành công, thất bại, retry.
- DB pool/HTTP connections và downstream error rate.

Nếu publisher nhanh nhưng queue tăng liên tục, việc xử lý không theo kịp. Nếu queue rỗng nhưng handler p99 tăng, kiểm tra dependency chậm/lock. Nếu rejection tăng, cần xử lý overload, không chỉ tăng pool vô hạn.

## 17. Bảo mật dữ liệu trong asynchronous queue

Async executor có thể giữ event object trong hàng đợi lâu hơn so với listener đồng bộ. Do đó:

- Không truyền nguyên `HttpServletRequest`, JPA entity lớn hoặc mutable object graph.
- Không truyền password, access token, session cookie, raw PII nếu listener không thực sự cần.
- Ưu tiên event record immutable chứa business IDs được phép và thuộc tính tối thiểu.
- Nếu listener cần ID thật để gọi service, kiểm tra authorization và data classification, không log toàn bộ event.
- Không đặt mã định danh nhạy cảm vào tên thread hoặc metric tag.
- Không gửi `SecurityContext` của request sang worker theo cách làm lộ quyền sau khi request kết thúc.
- Giới hạn queue capacity để tránh memory retention và GC pressure do payload lớn.
- Khi dùng broker/DLQ/outbox, metadata và payload có thể tồn tại nhiều ngày; thiết kế encryption/retention/ACL tương ứng.

Một `@Async` method có `void` return không tự tạo error channel hoặc audit record. Với công việc quan trọng, phải có đường ghi nhận outcome rõ thay vì chỉ log exception.

## 18. Async executor hay outbox: lựa chọn dựa trên độ tin cậy

| Yêu cầu | In-memory async executor | Durable outbox/queue |
| --- | --- | --- |
| Tách thread để publisher nhanh | Có | Có thể, qua worker sau commit |
| Công việc vẫn còn khi JVM chết | Không bảo đảm | Có nếu ghi bền vững/thiết kế đúng |
| Retry sau restart | Không tự có | Có thể thiết kế từ storage |
| DLQ/replay | Không tự có | Có thể có |
| Theo dõi backlog dài hạn | Chỉ trong memory | Có dữ liệu bền vững |
| Transaction với domain DB | Không có atomicity với task enqueue | Outbox row có thể commit cùng domain row |
| At-least-once delivery | Không tự bảo đảm | Có thể thiết kế, cần idempotency |
| Exactly-once side effect | Không | Cũng không tự động; cần domain idempotency |
| Độ phức tạp | Ít hơn | Nhiều hơn |

Một quy trình outbox:

~~~text
Domain transaction:
   INSERT business row
   INSERT outbox work item (same transaction)
   COMMIT
       |
       v
Outbox worker:
   claim pending item
   execute side effect
   record outcome / retry
   ACK / mark done
~~~

Dù outbox giúp tránh mất work giữa commit và send, worker có thể crash **sau side effect nhưng trước ACK**. Vì vậy consumer/side-effect cần idempotency hoặc reconciliation. Không coi outbox là “exactly once” tự động.

Một async executor trong process vẫn phù hợp cho cache refresh nhẹ, prefetch hoặc analytics best-effort nếu mất một task khi crash là chấp nhận được. Phải nói rõ mức tin cậy đó trong thiết kế.

## 19. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| Listener vẫn chạy trên request thread | Bean multicaster sai tên, chưa có executor hoặc listener không hỗ trợ async | Kiểm tra bean name và `supportsAsyncExecution()` |
| `@Async` không có tác dụng | Thiếu `@EnableAsync`, bean không do Spring quản lý, self-invocation | Bật annotation support, gọi qua proxy |
| Spring không chọn đúng executor | Nhiều pools nhưng không có qualifier | Dùng `@Async("notificationExecutor")` |
| Chỉ dùng 2 workers dù max=32 | Queue còn chỗ hoặc unbounded | Xem core/queue/max semantics |
| Publish đột ngột chậm khi tải cao | `CallerRunsPolicy` khiến caller xử lý task | Kiểm tra rejection policy, saturation |
| Event biến mất khi queue đầy | Discard policy hoặc exception bị nuốt | Reject minh bạch/persist work |
| Mọi listener completion đảo thứ tự | Multiworker scheduling không bảo đảm order | Workflow/ordering contract |
| Listener lỗi nhưng publisher không ném | Exception ở worker async | ErrorHandler/AsyncUncaughtExceptionHandler và outcome metrics |
| `@TransactionalEventListener` bị bỏ qua | Publish ngoài transaction, phase hoặc thread/context không phù hợp | Test transaction synchronization và commit/rollback |
| Cùng một listener bị enqueue hai lần | Cấu hình async cả multicaster lẫn proxy hoặc publish trùng | Đếm invocations, xác định ownership, idempotency |
| MDC/trace mất sau async | Không propagate context | TaskDecorator/context propagation |
| Tracing đầy PII | Baggage/log event payload không lọc | Data minimization/redaction |
| Shutdown mà còn task | Không có grace period hoặc task bị chặn | Test lifecycle và recovery |
| Pool tăng quá lớn gây nghẽn DB | Concurrency vượt connection/rate limits | Giảm pool, backpressure, optimize |
| JUnit flaky vì chờ 20 ms | Dùng sleep thay tín hiệu completion | Latch/future với timeout |
| Publish timer thấp nhưng request vẫn chậm | Transaction commit hoặc công việc đồng bộ khác | Trace toàn critical path |
| Publish timer thấp nhưng email đến muộn | Queue/backlog hoặc downstream latency | Đo start delay, handler duration, E2E |
| TaskExecutor bean bị đóng sớm | Tạo/đóng thủ công hoặc scope sai | Để Spring quản lý vòng đời |
| Async event có nhiều subscriber mà đòi count bằng publish | Một event có thể kích hoạt nhiều handler | Đếm theo event type + handler + outcome |
| Hệ thống chạy được local nhưng mất event sau restart | In-memory queue không durable | Outbox/job table/broker |

## 20. Checklist triển khai và bài tập thực hành

### Checklist trước khi merge

- [ ] Đã xác định listener nào thật sự được phép async.
- [ ] Đã chọn **một nơi** tách thread: multicaster hoặc `@Async` có chủ đích.
- [ ] Multicaster custom có tên bean chính xác `applicationEventMulticaster`.
- [ ] `@EnableAsync` được bật khi dùng `@Async`.
- [ ] `@Async` method là Spring-managed, public/proxy-invocable và dùng executor qualifier đúng.
- [ ] Core/max/queue capacity và rejection policy đã được chọn theo workload.
- [ ] Queue có giới hạn và không âm thầm discard task quan trọng.
- [ ] Có xử lý exception riêng cho đường multicaster và annotation async.
- [ ] Không kỳ vọng exception async quay về publisher để rollback.
- [ ] Đã kiểm tra `@TransactionalEventListener`, phase, thread context và `REQUIRES_NEW` nếu ghi DB sau commit.
- [ ] Không phụ thuộc `@Order` để bảo đảm thứ tự hoàn tất async.
- [ ] ThreadLocal/MDC/security/trace context được propagate theo chính sách.
- [ ] Graceful shutdown có timeout; nếu cần không mất work đã có durable storage.
- [ ] Có metrics queue depth, active workers, rejection, handler duration/outcome và E2E.
- [ ] Payload event không chứa secret/PII không cần thiết.
- [ ] JUnit dùng latches/futures để kiểm tra behavior, không dùng timing tuyệt đối.
- [ ] Load test trước/sau với workload tương tự và xác minh business correctness.

### Bài tập 1 — Queue đầy

Thử cấu hình core=1, max=1, queue=1 và ba task bị chặn. Dùng latches để giữ worker/task chờ và kiểm tra một lần submit mới bị từ chối. Phân biệt exception khi submit và exception do logic listener ném.

### Bài tập 2 — CallerRunsPolicy

Đổi `AbortPolicy` thành `CallerRunsPolicy` trong một test riêng. Khi pool/queue bão hòa, xác nhận task mới có thể chạy ở publisher thread và làm `publishEvent` block. Giải thích vì sao p99 publish có thể tăng đột biến khi quá tải.

### Bài tập 3 — Transaction-bound listener

Tạo transaction JDBC thật, publish `OrderPlaced` trong `TransactionTemplate`, dùng một listener `AFTER_COMMIT`. Kiểm tra listener không chạy trước commit, không chạy sau rollback. So sánh behavior khi custom multicaster có executor.

### Bài tập 4 — Async failure

Viết `AsyncUncaughtExceptionHandler` cho `@Async @EventListener void` và test ghi nhận lỗi qua latch. So sánh với `SimpleApplicationEventMulticaster#setErrorHandler` ở ví dụ chính.

### Bài tập 5 — Context propagation

Dùng `ContextPropagatingTaskDecorator` cùng Micrometer Context Propagation để chuyển một trace/log context được hỗ trợ sang worker. Kiểm tra context không còn sót lại ở task tiếp theo. Không cố truyền JDBC transaction ThreadLocal như một cách mở rộng transaction xuyên thread.

### Bài tập 6 — Outbox

Viết một job table trong H2 hoặc PostgreSQL, ghi job và order trong cùng transaction, cố ý kill worker rồi restart. Xác nhận job chưa xử lý vẫn tồn tại, có retry và idempotency. So sánh mức tin cậy với queue trong memory.

### Bài tập 7 — Performance

Chạy 1.000 event ở các mức concurrency khác nhau, đo p95/p99 publish và listener completion, queue length, DB pool wait. Kết luận lựa chọn pool/queue phù hợp dựa trên dữ liệu, không chỉ duration một event.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Bật `setTaskExecutor` trên `SimpleApplicationEventMulticaster` có cần `@EnableAsync` không?

**Đáp án:** Không. `@EnableAsync` phục vụ annotation-driven `@Async`; multicaster có thể trực tiếp submit vào executor.

**Câu 2.** `@Async("notificationExecutor")` có làm mọi listener tự chạy nền không?

**Đáp án:** Không. Nó áp dụng cho method được đánh dấu và gọi qua proxy; các listener khác vẫn có execution model riêng.

**Câu 3.** Core=2, max=20, queueCapacity=10000. Vì sao ứng dụng ít khi dùng hơn 2 workers?

**Đáp án:** ThreadPoolExecutor ưu tiên enqueue khi core đã đủ; chỉ mở non-core threads khi queue đầy, nên max không đồng nghĩa concurrency tức thời.

**Câu 4.** Khi pool/queue đầy và dùng CallerRunsPolicy, `publishEvent` có chắc trả về nhanh không?

**Đáp án:** Không. Task có thể chạy ngay trên caller thread, khiến publisher phải đợi handler.

**Câu 5.** Vì sao một `@TransactionalEventListener(AFTER_COMMIT)` không tự async chỉ vì multicaster có executor?

**Đáp án:** Transaction-synchronized listener cần đăng ký synchronization trong transaction context và có thể từ chối async dispatch; phase registration và target processing là hai phần khác nhau.

**Câu 6.** Handler void `@Async` ném exception. Caller publish có nhất thiết nhận được exception không?

**Đáp án:** Không. Lỗi xảy ra trên worker; xử lý bằng async error handler hoặc một cơ chế outcome/ack rõ ràng.

**Câu 7.** Có nên tăng pool tới 500 workers nếu database chỉ có 20 connections?

**Đáp án:** Thường không; concurrency lớn có thể tăng contention, queue tại DB pool, timeout và tail latency. Cần sizing theo dependency.

**Câu 8.** Khi event cần gửi email chắc chắn kể cả JVM crash, executor có đủ không?

**Đáp án:** Không. Dùng durable job/outbox/broker với retry, idempotency và cơ chế phục hồi.

**Câu 9.** Một test ngủ 100 ms rồi assert listener đã xong có đáng tin không?

**Đáp án:** Không. Scheduling không deterministic; dùng CountDownLatch/Future hoặc completion signal với timeout.

**Câu 10.** Đã bật async, publish duration giảm còn 2 ms nhưng backlog tăng liên tục. Có thể tuyên bố toàn workflow nhanh hơn không?

**Đáp án:** Không. Producer chỉ handoff nhanh; handler completion có thể ngày càng chậm. Cần đo end-to-end, saturation và error rates.

## 22. Tài liệu tham khảo

- Spring Framework 6.2 — Standard and Custom Events, asynchronous event listeners và `@Order`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — `SimpleApplicationEventMulticaster` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — `ApplicationEventPublisher` Javadoc (handoff semantics): https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 — `ApplicationListener.supportsAsyncExecution()` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationListener.html
- Spring Framework 6.2 — `TransactionalApplicationListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/event/TransactionalApplicationListener.html
- Spring Framework 6.2 — Task Execution and Scheduling, `ThreadPoolTaskExecutor` sizing và `@Async`: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 — `ThreadPoolTaskExecutor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.2 — `ContextPropagatingTaskDecorator` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
- Spring Framework — Observability and `@EventListener`: https://docs.spring.io/spring-framework/reference/integration/observability.html
- Spring Framework — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Micrometer — Timers: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Micrometer — Context Propagation: https://docs.micrometer.io/context-propagation/reference/
- Java 17 — `ThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- JUnit 5 — Testing framework user guide: https://junit.org/junit5/docs/current/user-guide/
