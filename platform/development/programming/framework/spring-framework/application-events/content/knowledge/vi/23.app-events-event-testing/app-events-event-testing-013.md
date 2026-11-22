# Kiểm thử async listener không flaky trong Spring Framework Application Events

## 1. Vấn đề: async listener khiến test lúc xanh, lúc đỏ

Trong Spring Framework, application event thường được dùng để tách công việc như gửi thông báo, cập nhật chỉ số, audit hay gọi dịch vụ khác khỏi luồng nghiệp vụ chính. Khi listener chạy bất đồng bộ, lời gọi `applicationEventPublisher.publishEvent(event)` có thể **trả về trước khi listener hoàn tất**. Nếu test đọc ngay database, một `AtomicReference`, một log hoặc một mock mà không chờ tín hiệu phù hợp, kết quả phụ thuộc vào lịch chạy của hệ điều hành và tải CI.

Một test dễ flaky:

```java
publisher.publishEvent(new OrderPlaced("ORD-42"));
verify(notificationGateway).send("ORD-42"); // Có thể quá sớm!
```

Đây là **mẫu lỗi minh họa** với Mockito, không phải chương trình độc lập. Test có thể pass trên laptop vì executor chạy rất nhanh nhưng fail trên CI chậm. Thêm `Thread.sleep(1000)` không sửa nguyên nhân: 1 giây có thể quá ít hoặc lãng phí, trong khi test vẫn có race condition.

Trong nhóm **Kiểm thử event**, mục tiêu của bài **Kiểm thử async listener không flaky** là tạo test **đồng bộ hóa bằng một sự kiện quan sát được**, kiểm tra kết quả thật của handler, đảm bảo lỗi không bị nuốt, và dọn mọi thread/resource sau mỗi test.

Một test đáng tin phải phân biệt:

1. **Publisher đã gọi publishEvent**: lời gọi Java hoàn tất.
2. **Task đã được submit**: executor đã nhận việc, chưa chắc chạy.
3. **Listener đã bắt đầu**: handler đi tới điểm đánh dấu bắt đầu.
4. **Listener đã hoàn tất**: phần việc nằm trong phạm vi handler thật sự xong.
5. **Side effect ngoài handler đã hoàn tất**: chẳng hạn email thực sự được gửi; nếu handler chỉ enqueue job, trạng thái này thuộc một hệ thống khác.

Không được dùng một tín hiệu của mốc (1) để khẳng định mốc (4) hoặc (5).

## 2. Hai cách async thường gặp trong Spring Events

### 2.1. Asynchronous multicaster

Spring mặc định dùng `SimpleApplicationEventMulticaster` với cơ chế dispatch đồng bộ trong thread gọi `publishEvent`. Khi cấu hình `setTaskExecutor(...)`, các `ApplicationListener` có hỗ trợ asynchronous execution có thể chạy trong pool:

```java
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster eventMulticaster(
        ThreadPoolTaskExecutor eventExecutor) {

    SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventExecutor);
    return multicaster;
}
```

Đây là **đoạn cấu hình tích hợp** cần import Spring tương ứng. Nếu listener ném exception trên worker, exception không tự quay về publisher khi `publishEvent` đã trả về. Có thể cấu hình `SimpleApplicationEventMulticaster.setErrorHandler(...)` để nhận/ghi nhận lỗi, đồng thời thiết kế cơ chế retry riêng khi cần.

Từ Spring Framework 6.1, listener có thể quyết định hỗ trợ async execution hay không qua `ApplicationListener.supportsAsyncExecution()`. Một số listener phụ thuộc transaction synchronization cần đăng ký trong thread/context phù hợp và không đơn giản được dispatch bất đồng bộ bằng multicaster.

### 2.2. `@Async @EventListener`

Một phương thức bean cũng có thể được proxy để chạy bất đồng bộ:

```java
@Async("eventExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    notificationGateway.send(event.orderId());
}
```

Đây là **mẫu tích hợp**, cần `@EnableAsync`, executor tên `eventExecutor` và các bean liên quan. `@Async` đi qua Spring async proxy; executor thực tế dùng cho `@Async` có thể **khác** executor được cài trên multicaster.

Đối với async method trả về `void`, lỗi không có một future trả về caller để `get()`; cần `AsyncUncaughtExceptionHandler`, logging/metrics hoặc tín hiệu test tương ứng. Do vậy, test không nên viết:

```java
assertThrows(IllegalStateException.class,
    () -> publisher.publishEvent(new OrderPlaced("ORD-42")));
```

rồi kết luận listener async không lỗi chỉ vì `assertThrows` thất bại. Lỗi có thể xảy ra **sau** khi lời gọi publish trả về.

### Bảng phân biệt

| Cơ chế | Listener chạy ở đâu? | Test cần chờ gì? |
| --- | --- | --- |
| Multicaster mặc định | Thread publisher | Có thể assert sau lời gọi nếu listener thật sự đồng bộ |
| `SimpleApplicationEventMulticaster` có `TaskExecutor` | Worker đối với listener hỗ trợ async | Tín hiệu listener hoàn tất và kênh báo lỗi |
| `@Async @EventListener` | Executor của Spring Async | Tín hiệu ở handler và `AsyncUncaughtExceptionHandler` hoặc future theo contract |
| `@TransactionalEventListener` | Gắn phase của transaction | Commit/rollback **thật**, sau đó kiểm tra callback |
| Handler chỉ enqueue job | Có thể xong rất nhanh | Phải chờ consumer/job nếu yêu cầu test là kết quả cuối |

**Quan trọng:** `@TransactionalEventListener(phase = AFTER_COMMIT)` không đồng nghĩa async. Nó nghĩa là callback gắn với phase commit. Muốn kiểm thử một handler vừa hậu commit vừa chuyển việc sang thread khác, phải kiểm tra **cả hai ranh giới**: commit thật và hoàn tất task async.

## 3. Vì sao Thread.sleep và assert ngay thường flaky?

### Anti-pattern 1: sleep cố định

```java
publisher.publishEvent(event);
Thread.sleep(500);
assertEquals(1, repository.count());
```

Đây là **mẫu lỗi minh họa**. Nếu máy CI quá tải hoặc downstream chậm trên 500 ms thì fail dù logic đúng. Nếu handler chỉ cần 5 ms thì test vẫn phí phần lớn thời gian ngủ. Sleep cũng không báo rõ **đang chờ điều kiện gì**.

### Anti-pattern 2: polling không có timeout

```java
while (!notificationGateway.isDone()) {
    // Chờ vô hạn nếu handler fail hoặc không được gọi.
}
```

Không có deadline, test có thể treo mãi; busy loop còn đốt CPU. Polling hợp lý phải có **điều kiện rõ, timeout hữu hạn, thông báo lỗi và memory visibility**. Awaitility là công cụ phổ biến cho trường hợp trạng thái cuối chưa có callback trực tiếp.

### Anti-pattern 3: chỉ verify publish

```java
verify(publisher).publishEvent(any(OrderPlaced.class));
```

Điều này chỉ chứng minh **tầng gọi publisher đã gửi lời gọi**, chưa chứng minh multicaster đăng ký listener, handler thực thi hoặc side effect hoàn tất.

### Anti-pattern 4: dùng mutable biến thường giữa threads

```java
boolean handled = false; // Không có đảm bảo visibility cross-thread.
// Worker đặt handled=true; test thread đọc ngay hoặc quay vòng.
```

Đây là **đoạn minh họa lỗi**. Không dùng field `boolean` không được đồng bộ như một tín hiệu giữa thread. Dùng `CountDownLatch`, `CompletableFuture`, `BlockingQueue`, `AtomicReference` hoặc abstraction có semantics đồng bộ phù hợp. Tín hiệu chỉ được phát **sau** khi trạng thái cần assert được ghi.

## 4. Ba công cụ test nên chọn đúng mục đích

| Công cụ | Phù hợp với | Ưu điểm | Lưu ý |
| --- | --- | --- | --- |
| `CountDownLatch` | Biết số lần handler phải tới một mốc | Chờ chính xác, `await(timeout)`, dễ điều khiển race | Không reset; tạo mới mỗi test, xử lý interrupt |
| `CompletableFuture<T>` | Muốn nhận cả kết quả hoặc exception của một event | `get(timeout)`, `completeExceptionally`, gắn kết event ID | Phải hoàn tất tương ứng cả success/fail, không tạo future bị quên |
| Awaitility | Kết quả cuối được quan sát qua DB/cache/mock/repository | `untilAsserted(...)` với deadline và polling hợp lý | Không tự chứng minh đường lỗi async; không chờ điều kiện không thể quan sát |
| `StepVerifier` | Reactive pipeline `Mono`/`Flux` | Kiểm tra subscription, terminal signal và virtual time cho logic phù hợp | Không thay thế kiểm thử side effect khác nằm ngoài pipeline |
| `BlockingQueue` | Event được xử lý nhiều lần hoặc cần lấy kết quả theo thứ tự | `poll(timeout)`, tránh shared unsynchronized data | Phải định nghĩa kỳ vọng về ordering nếu nhiều worker |

**Quy tắc:** dùng đồng bộ hóa **theo hành vi**, không theo thời gian ước đoán. Timeout là **giới hạn tối đa được phép chờ**, không phải delay bắt buộc trước assert. Nếu handler xong sau 10 ms, một `await(10, SECONDS)` thường trở về ngay; nó không ngủ đủ 10 giây.

Với `CountDownLatch`, `countDown()` và `await()` có quan hệ happens-before phù hợp, nên test thread nhìn thấy những cập nhật đã được thực hiện trước `countDown()` khi `await` trả về thành công.

## 5. Mô hình test có kiểm soát race condition

Một bài test async tốt thường có ba tín hiệu:

```text
Test thread                                      Executor thread
    |                                                   |
    +--> publishEvent(OrderPlaced)                      |
    |       |                                           |
    |       +--> submit task --------------------------> |
    |                                                   +--> entered.countDown()
    +--> entered.await(timeout)                         |
    |                                                   +--> release.await(timeout)
    +--> assert listener vẫn đang chờ (nếu cần)         |
    +--> release.countDown() --------------------------> +--> chạy business logic
    |                                                   +--> result được ghi
    |                                                   +--> finished.countDown()
    +--> finished.await(timeout)                        |
    +--> assert kết quả                                 |
```

Tín hiệu `entered` giúp test biết listener đã khởi chạy. Tín hiệu `release` là một **cổng điều khiển**: nó cho phép test kiểm tra “publisher đã trả về, listener vẫn chưa hoàn thành” mà không dùng sleep. Tín hiệu `finished` cho phép test đọc kết quả sau mốc hoàn thành.

Để tránh deadlock do assertion thất bại, **luôn giải phóng gate trong finally**; nếu không, test hỏng có thể giữ worker bị block và làm context shutdown treo. Bản demo ở mục 6 dùng một thread, gate hữu hạn và `try-with-resources` để dọn Spring context.

## 6. Ví dụ chạy được: JUnit 5 + Spring 6.1 + asynchronous multicaster

Chúng ta sẽ kiểm thử **asynchronous multicaster** một cách trực tiếp. Đây là dự án Java 17+ không dùng Spring Boot, không dùng database và không gọi service ngoài. Nó bao gồm:
- `SimpleApplicationEventMulticaster` chạy `@EventListener` trên `ThreadPoolTaskExecutor`.
- `Probe` có `CountDownLatch`, `AtomicReference` và mốc lỗi qua `ErrorHandler`.
- Test 1 xác minh handler chạy trên worker, còn bị chặn sau khi publish trả về, rồi hoàn tất đúng khi được giải phóng.
- Test 2 xác minh exception từ handler bất đồng bộ được nhìn thấy qua `ErrorHandler`, **không** giả định nó được ném trở lại publisher.

Mỗi test khởi tạo **application context riêng**. Nhờ vậy, latch và result của test trước không nhiễm sang test sau. Chúng ta không cần thay bean toàn cục hoặc gọi sleep.

### 6.1. Cấu trúc thư mục

```text
async-event-tests/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/AsyncEventListenerTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'async-event-tests'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.3'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

test {
    useJUnitPlatform()
}
```

### 6.2. File kiểm thử hoàn chỉnh

`src/test/java/demo/AsyncEventListenerTest.java`:

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.junit.jupiter.api.Assertions.*;

class AsyncEventListenerTest {

    record OrderPlaced(String eventId, boolean shouldFail) {}

    static final class Probe {
        final CountDownLatch entered = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
        final CountDownLatch finished = new CountDownLatch(1);
        final CountDownLatch errorReported = new CountDownLatch(1);

        final AtomicReference<String> processed = new AtomicReference<>();
        final AtomicReference<String> handlerThread = new AtomicReference<>();
        final AtomicReference<Throwable> error = new AtomicReference<>();

        void captureError(Throwable failure) {
            error.set(failure);
            errorReported.countDown();
        }
    }

    static final class OrderListener {
        private final Probe probe;

        OrderListener(Probe probe) {
            this.probe = probe;
        }

        @EventListener
        public void on(OrderPlaced event) {
            probe.handlerThread.set(Thread.currentThread().getName());
            probe.entered.countDown();

            try {
                if (!probe.release.await(15, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Listener gate timed out");
                }
                if (event.shouldFail()) {
                    throw new IllegalArgumentException("simulated failure");
                }
                probe.processed.set(event.eventId());
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                    "Listener was interrupted", interrupted
                );
            } finally {
                probe.finished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        OrderListener orderListener(Probe probe) {
            return new OrderListener(probe);
        }

        @Bean
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("event-worker-");
            return executor;
        }

        @Bean(name = "applicationEventMulticaster")
        ApplicationEventMulticaster applicationEventMulticaster(
                ThreadPoolTaskExecutor eventExecutor, Probe probe) {
            SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
            multicaster.setTaskExecutor(eventExecutor);
            multicaster.setErrorHandler(probe::captureError);
            return multicaster;
        }
    }

    @Test
    void waitsForRealCompletionWithoutSleeping() throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(TestConfig.class)) {

            Probe probe = context.getBean(Probe.class);
            try {
                context.publishEvent(new OrderPlaced("EVT-1", false));

                assertTrue(
                    probe.entered.await(10, TimeUnit.SECONDS),
                    "Listener did not start before timeout"
                );
                assertEquals(
                    1L, probe.finished.getCount(),
                    "Handler must still be blocked by release gate"
                );
                assertNull(probe.processed.get());
            } finally {
                // Release dù assert ở trên thất bại.
                probe.release.countDown();
            }

            assertTrue(
                probe.finished.await(10, TimeUnit.SECONDS),
                "Listener did not complete before timeout"
            );
            assertEquals("EVT-1", probe.processed.get());
            assertTrue(
                probe.handlerThread.get().startsWith("event-worker-")
            );
            assertNull(probe.error.get());
        }
    }

    @Test
    void recordsAsyncExceptionViaErrorHandler() throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(TestConfig.class)) {

            Probe probe = context.getBean(Probe.class);
            probe.release.countDown();

            // Không dùng assertThrows với publishEvent ở đây.
            context.publishEvent(new OrderPlaced("EVT-2", true));

            assertTrue(
                probe.finished.await(10, TimeUnit.SECONDS),
                "Failing listener did not finish"
            );
            assertTrue(
                probe.errorReported.await(10, TimeUnit.SECONDS),
                "Async failure did not reach ErrorHandler"
            );
            assertNotNull(probe.error.get());
            assertNull(probe.processed.get());
        }
    }
}
```

Chạy với JDK 17+ và Gradle đã cài:

```bash
gradle test
```

Kết quả mục tiêu là **2 tests thành công**. Không in stdout cố định vì JUnit/Gradle thay đổi format theo phiên bản và mức độ logging. Với cấu hình mặc định, Gradle báo task `test` thành công nếu cả hai method pass.

### 6.3. Vì sao ví dụ này không flaky theo kiểu race condition thông thường?

1. Bean `applicationEventMulticaster` dùng executor thay multicaster đồng bộ mặc định. `OrderListener` chỉ xử lý `OrderPlaced`, nên test không nhầm các Spring lifecycle events với event đang kiểm tra.
2. `Probe.entered` được count down khi handler bắt đầu; `Probe.release` làm handler dừng tại một cổng do test điều khiển. Vì vậy, sau `entered.await(...)` và trước `release.countDown()`, test biết handler chưa hoàn tất. Không có giả định “trong 100 ms chắc chắn handler sẽ chạy”.
3. Listener ghi `processed` trước khi `finished.countDown()`. Khi `finished.await(...)` thành công, test có thể đọc `processed` an toàn qua `AtomicReference` và synchronization của latch.
4. Exception từ async handler được multicaster chuyển đến `ErrorHandler`; test chờ riêng `errorReported` vì `finished.countDown()` nằm trong `finally` của handler, có thể chạy **trước** khi error handler nhận exception.
5. Cổng `release` được giải phóng trong `finally` ở test 1. Nếu assert ban đầu fail, executor không bị treo vô hạn. Bản thân handler cũng có timeout 15 giây cho gate, tránh deadlock vĩnh viễn.
6. `try-with-resources` đóng context; `ThreadPoolTaskExecutor` do Spring quản lý sẽ được shutdown theo lifecycle bean. Test không dùng static singleton probe, nên kết quả và latches không bị chia sẻ giữa các test.

**Timeout không bị loại bỏ hoàn toàn:** ngay cả test đúng vẫn cần timeout hữu hạn để tránh treo khi code lỗi. CI quá tải có thể làm timeout 10 giây không đủ. Nên chọn timeout dựa trên đặc tính môi trường, và khi thất bại phải biết đang chờ **mốc nào**. Sự khác biệt là deadline của await không tạo race có chủ đích như sleep rồi assert ngay.

### 6.4. Giới hạn của demo

- Demo kiểm tra lỗi async được **quan sát** bởi ErrorHandler; `setErrorHandler(probe::captureError)` không tự retry công việc. Production cần error handling, retry, idempotency và cảnh báo riêng.
- Test 2 không khẳng định loại exception chính xác trong mọi cấu hình proxy. Có thể kiểm tra root cause nếu hợp đồng hệ thống yêu cầu; ở đây assert đã nhận được một `Throwable` để tránh phụ thuộc cách framework wrap exception.
- Test không có DB; nó không chứng minh commit/rollback. Khi yêu cầu kiểm thử sau commit, phải có transaction integration test khác.
- Test kiểm chứng handler được gọi trên worker thread vì thread name có prefix `event-worker-` do executor đặt. Không dùng tên thread như một điều kiện nghiệp vụ production.
- Test chỉ có một listener một executor. Nếu nhiều listener cùng nghe event hoặc một listener tạo task con, phải bổ sung điểm quan sát cho từng nhánh thực sự cần hoàn tất.

## 7. Kiểm thử @Async @EventListener đúng cách

Với `@Async("eventExecutor") @EventListener`, test phải bật `@EnableAsync` và tạo đúng executor được proxy sử dụng. Nếu chỉ thêm annotation mà không kích hoạt Spring Async, method có thể chạy đồng bộ và test pass **không hề kiểm tra async**.

Cấu hình tích hợp:

```java
@Configuration
@EnableAsync
class AsyncConfig {
    @Bean(name = "eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor e = new ThreadPoolTaskExecutor();
        e.setCorePoolSize(2);
        e.setMaxPoolSize(2);
        e.setQueueCapacity(20);
        e.setThreadNamePrefix("async-listener-");
        return e;
    }
}

@Component
class EmailListener {
    @Async("eventExecutor")
    @EventListener
    public void on(OrderPlaced event) {
        emailGateway.send(event.orderId());
    }
}
```

Đây là **mẫu tích hợp**, chưa phải file chạy độc lập. Cần import `@Configuration`, `@EnableAsync`, `@Bean`, `@Component`, `@Async` và `@EventListener`; `OrderPlaced`, `EmailGateway` cũng phải được định nghĩa và tạo bean.

Khi test `@Async`:
- Tạo tín hiệu hoàn tất trong **điểm mà side effect xảy ra** (fake email gateway hoặc listener instrumentation), không chờ publisher return.
- Nếu async method trả về `void`, dùng `AsyncUncaughtExceptionHandler`/error recorder hoặc test-specific probe để quan sát failure; exception không tự trở thành exception của publisher.
- Nếu method được gọi qua Spring proxy và return type hợp lệ như `CompletableFuture`, có thể dùng `future.get(timeout, unit)` ở tầng có quyền nhận future; nhưng `@EventListener` callback không mặc nhiên trả future đó cho publisher.
- Tránh gọi trực tiếp method listener trên object mới bằng `new EmailListener(...)` rồi kết luận `@Async` đã được test: không có proxy thì annotation không hoạt động.
- Nếu dùng custom executor, cấu hình theo qualifier trong `@Async("...")`; không giả định đó là executor của `SimpleApplicationEventMulticaster`.

## 8. Kiểm thử bằng CompletableFuture theo event ID

Với nhiều event đồng thời, một `CountDownLatch(1)` dùng chung có thể báo pass quá sớm: event B hoàn tất trong khi test đang đợi event A. Hãy **gắn tín hiệu với từng event**.

Ví dụ test probe minh họa:

```java
public final class CompletionProbe {
    private final ConcurrentMap<String, CompletableFuture<String>> outcomes =
        new ConcurrentHashMap<>();

    public CompletableFuture<String> expect(String eventId) {
        CompletableFuture<String> fresh = new CompletableFuture<>();
        if (outcomes.putIfAbsent(eventId, fresh) != null) {
            throw new IllegalStateException("Duplicate expectation");
        }
        return fresh;
    }

    public void succeeded(String eventId, String result) {
        CompletableFuture<String> future = outcomes.get(eventId);
        if (future == null) {
            throw new IllegalStateException("Unexpected event: " + eventId);
        }
        future.complete(result);
    }

    public void failed(String eventId, Throwable cause) {
        CompletableFuture<String> future = outcomes.get(eventId);
        if (future == null) {
            throw new IllegalStateException("Unexpected event: " + eventId);
        }
        future.completeExceptionally(cause);
    }
}
```

Đây là **class tích hợp** cần import `java.util.concurrent.*` và lifecycle quản lý probe; không phải file chính của demo. Test đăng ký expectation **trước khi publish**:

```java
CompletableFuture<String> result = probe.expect("EVT-42");
publisher.publishEvent(new OrderPlaced("EVT-42", false));

assertEquals(
    "email-scheduled",
    result.get(10, TimeUnit.SECONDS)
);
```

Đoạn này giả định listener hoặc fake gateway gọi `probe.succeeded("EVT-42", "email-scheduled")` sau khi công việc đã đạt đến mốc cần test. Nếu listener lỗi, phải gọi `probe.failed(...)` hoặc có kênh lỗi được assert riêng; không để test chỉ hết timeout mà không có thông tin. Nên dọn map expectation sau test hoặc tạo probe riêng per test để tránh memory leak.

**Không nhầm future hoàn tất với giao email thật:** nếu listener chỉ enqueue email job, `"email-scheduled"` là kết quả enqueue. Muốn test delivery, cần một tín hiệu thực từ worker/transport ở tầng phù hợp.

## 9. Awaitility: chờ trạng thái cuối khi không có callback trực tiếp

Khi kết quả xuất hiện trong DB, cache hoặc fake repository, test có thể dùng Awaitility `untilAsserted(...)` thay vì sleep:

```java
await()
    .atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(50))
    .untilAsserted(() ->
        assertEquals("SENT", emailStatusRepository.findStatus("EVT-42"))
    );
```

Đây là **đoạn tích hợp**, cần dependency `org.awaitility:awaitility` cùng imports `await()`, `Duration` và code repository. Việc polling có timeout giúp test fail nếu kết quả không đạt trạng thái mục tiêu. Chọn khoảng poll hợp lý và không đưa sleep tùy tiện vào business code để “giúp test pass”.

Một số lưu ý:
- Cần chờ **kết quả mà nghiệp vụ thực sự quan tâm**, không chỉ số lần gọi một mock nếu contract là DB đã được update.
- Nếu backend là transaction/DB, query trong một transaction riêng hoặc context phù hợp. Persistence context đang cache entity cũ có thể khiến test luôn đọc dữ liệu stale.
- Nếu error handler chỉ log mà không cập nhật trạng thái, Awaitility cuối cùng timeout nhưng không giải thích vì sao. Kết hợp error recorder, logs/traces và thông báo assertion.
- Polling nhanh quá có thể tạo tải không cần thiết, đặc biệt với hệ thống test container hoặc backend thật.
- Với event nhiều loại, bảo đảm điều kiện chờ thuộc **đúng event ID** để tránh một event khác làm test pass.

## 10. Transactional event listener: commit khác async

`@TransactionalEventListener` cho phép xử lý theo `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK` hoặc `AFTER_COMPLETION`. Đây là **phase của transaction**, không phải cam kết thread execution.

Một tình huống hay gây test “flaky” hoặc **luôn fail**:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPlaced event) {
    projectionService.update(event);
}
```

Đoạn trên cần transaction manager và beans tương ứng. Nếu test chạy với Spring Test `@Transactional` mà framework **tự rollback cuối test**, listener `AFTER_COMMIT` sẽ không chạy. Test không thiếu sleep; nó thiếu **commit thật**.

Để kiểm thử:
1. Tạo một transaction thật bằng `TransactionTemplate`, hoặc quản lý test transaction với `TestTransaction` khi dùng Spring Test.
2. Publish event **bên trong transaction**.
3. Kết thúc transaction bằng commit.
4. Sau commit, chờ side effect nếu nó được tách async; nếu chỉ là callback đồng bộ, assert sau khi commit method trả về.
5. Assert **cả trạng thái DB** và số lần/ý nghĩa listener xử lý.

Test rollback riêng: publish event rồi khiến transaction rollback; assert `AFTER_COMMIT` không chạy và `AFTER_ROLLBACK` (nếu có) chạy theo đúng contract. **Không bật `fallbackExecution=true` chỉ để test nhận event** nếu logic production yêu cầu “chỉ khi commit thành công”.

Một callback AFTER_COMMIT lỗi không thể rollback DB gốc đã commit. Nếu handler cần ghi DB mới sau commit, nó có thể cần transaction mới (ví dụ `REQUIRES_NEW` qua Spring proxy) thay vì nghĩ transaction cũ còn hoạt động đầy đủ.

### Reactive transaction

Với Spring 6.1 và reactive transaction, sự kiện gắn transaction phải có `TransactionContext` làm source, thường thông qua `TransactionalEventPublisher`. `StepVerifier` có thể kiểm tra signal của `Mono`/`Flux` và completion/rollback, nhưng không tự đợi một `subscribe()` tách rời do listener tự gọi. Tránh việc test pass nhờ một subscription được tạo thủ công không cùng transaction context.

## 11. Dữ liệu test, parallel execution và isolation

Một bài test dùng đúng latch vẫn có thể thất bại ngẫu nhiên nếu dữ liệu/test context bị chia sẻ sai.

### 11.1. Không dùng static mutable state chung

Nếu test class có `static CountDownLatch`, `static AtomicReference` hoặc `static List<Event>` được nhiều test cập nhật, chạy JUnit song song có thể làm phép assert của test này quan sát sự kiện test khác. Tạo **probe riêng cho mỗi test** hoặc phân vùng theo correlation/event ID và dọn dữ liệu đúng cách.

### 11.2. Mỗi event có identity riêng

Trong integration test, dùng `eventId` và `orderId` khác nhau cho mỗi test. Đừng assert kiểu “ít nhất một event đã xử lý” khi nhiều event có thể chạy. Chọn `CompletionProbe` theo `eventId` hoặc query DB theo khóa của test.

### 11.3. Chờ toàn bộ công việc thuộc scope test trước teardown

Nếu một async listener còn chạy khi Spring context/test container đóng, nó có thể ném exception khi dependency bị destroy. Nếu test tiếp theo mở cùng DB hoặc mock, task cũ có thể gây nhiễu.

Một pattern an toàn:
- Publish.
- Chờ tín hiệu hoàn tất/exception cho **mọi** event thuộc test.
- Assert.
- Cuối cùng giải phóng gate, stop executor theo lifecycle context, đóng DB/test container.

Với executor, cân nhắc cấu hình `setWaitForTasksToCompleteOnShutdown(...)` khi thiết kế production/test infrastructure; đừng bật chờ vô hạn rồi bỏ quên task bị block. Timeout rõ ràng và cleanup trong `finally` quan trọng hơn một cấu hình shutdown duy nhất.

### 11.4. Không lạm dụng @DirtiesContext

`@DirtiesContext` có thể giúp khi state Spring context thật sự bị thay đổi giữa test nhưng làm suite chậm vì tạo lại context. Nó không sửa được data race, cache của persistence context, static state hoặc task còn chạy. Ưu tiên context/fixture isolation ở đúng tầng.

## 12. Mocking và xác nhận lỗi thực

Mockito có thể hữu ích khi fake gateway ghi nhận invocation. Tuy nhiên, đoạn này:

```java
publisher.publishEvent(event);
verify(gateway, times(1)).send(event);
```

là **sai với async listener** nếu verify chạy trước handler. Có thể dùng Mockito `timeout(...)` để đợi invocation nếu đây thực sự là contract test:

```java
publisher.publishEvent(event);
verify(gateway, timeout(10_000).times(1)).send(event);
```

Đây là **đoạn tích hợp** đòi hỏi Mockito. Nhưng `timeout(...)` chỉ chứng minh method đã được gọi, không nhất thiết I/O đã hoàn tất. Khi cần test state/result, dùng fake thực thi có completable future hoặc Awaitility trên trạng thái cuối.

**Negative assertions khó hơn positive assertions.** Ví dụ “listener không được gọi khi rollback” không nên kết luận chỉ vì chờ 200 ms và không thấy gì. Hãy có điểm đồng bộ như transaction đã rollback, executor đã xử lý xong các task liên quan, hoặc một invariant DB đáng tin, rồi mới assert không có side effect. Không có synchronization, một kết quả “chưa thấy” không đồng nghĩa “sẽ không bao giờ xảy ra”.

Với failure:
- Có thể instrument handler để ghi outcome vào `CompletableFuture` của test.
- Dùng `ErrorHandler` cho async multicaster khi handler ném exception.
- Dùng `AsyncUncaughtExceptionHandler` cho `@Async void`.
- Kiểm tra cả error signal và trạng thái không được persist sai.
- Đừng chỉ mong `assertThrows(...)` từ publisher sau khi listener đã được chuyển thread.

## 13. Test load/concurrency và thứ tự xử lý

Không phải mọi test async đều cần assert ordering. Với pool nhiều thread, hai listener có thể hoàn tất khác thứ tự publish. Nếu yêu cầu nghiệp vụ cần ordering:
- Mô hình hóa dependency hoặc dùng executor/queue bảo đảm thứ tự theo khóa phù hợp.
- Gắn sequence/aggregate version vào event khi cần.
- Test **contract về ordering** với cơ chế đồng bộ cụ thể, không dựa vào may mắn scheduler.
- Với Kafka/RabbitMQ hoặc hệ thống broker, ordering phụ thuộc partition/key, consumer group, retry và acknowledgment; đó là contract hạ tầng riêng.

Để test concurrency thực, có thể dùng `CyclicBarrier` hoặc `Phaser` cho nhiều worker bắt đầu cùng một phase; tuy nhiên phải đặt timeout và đảm bảo số participant đúng, nếu không test dễ deadlock. `CountDownLatch` phù hợp cho “đợi N tác vụ hoàn tất”, nhưng không tự bảo đảm chúng chạy đồng thời.

Đoạn minh họa đợi N sự kiện:

```java
CountDownLatch allDone = new CountDownLatch(eventIds.size());

for (String eventId : eventIds) {
    publisher.publishEvent(new OrderPlaced(eventId, false));
}

// Mỗi handler gọi allDone.countDown() sau khi hoàn tất.
// Đây là mẫu cấu trúc, cần cấp allDone đúng nơi và tránh double-count.
assertTrue(allDone.await(10, TimeUnit.SECONDS));
```

Nếu handler có retry, một logical event có thể tạo nhiều attempts. Cần quyết định latch đếm **attempts** hay **event đã hoàn thành**. Với event nhiều nhánh, một listener đếm xong không chứng minh toàn bộ workflow đã hoàn tất.

## 14. Khi nào nên dùng integration test và khi nào unit test?

| Mục tiêu | Test phù hợp |
| --- | --- |
| Logic thuần của handler khi có event | Unit test gọi thẳng handler với fake dependencies, không nhất thiết async |
| Listener được Spring đăng ký đúng kiểu event | Spring context integration test |
| Multicaster thực sự dispatch async và error handler đúng | Context test với executor như mục 6 |
| `@Async` proxy và qualifier executor hoạt động | Spring test bật `@EnableAsync` |
| DB commit rồi AFTER_COMMIT kích hoạt | Transaction integration test với commit thật |
| Giao nhận qua queue/broker, retry và dead-letter | Integration test với broker/test container hoặc fake theo hợp đồng |
| Reactive chain và transaction context | `StepVerifier`, test integration theo `Publisher` |
| End-to-end HTTP → DB → event → side effect | End-to-end test có ID riêng và tín hiệu completion đúng mốc |

**Không bắt mọi unit test phải dùng async thật.** Test logic của handler trực tiếp thường nhanh và dễ debug. Chỉ cần số lượng integration test đủ để đảm bảo cấu hình Spring, dispatch, thread và error channel hoạt động như production.

## 15. Chẩn đoán một test async bị flaky

Khi test lúc pass lúc fail, đi theo thứ tự:

1. **Có thực sự async không?** Kiểm tra executor bean, `@EnableAsync`, proxy và thread name; đừng đoán từ annotation.
2. **Test đang assert trước khi listener hoàn tất?** Chuyển sang `CountDownLatch`, future hoặc Awaitility theo outcome.
3. **Có error bị che không?** Kiểm tra ErrorHandler/AsyncUncaughtExceptionHandler và ghi failure test-side.
4. **Có task rò giữa tests?** Đảm bảo đợi completion trước teardown, đóng context và executor.
5. **State chia sẻ có thread-safe không?** Tránh field thường/static global không đồng bộ.
6. **Có race register-before-publish không?** Với future theo event ID, đăng ký expectation **trước khi** gửi.
7. **Có DB transaction chưa commit hoặc test tự rollback không?** Đặc biệt với `AFTER_COMMIT`.
8. **Có stale data khi đọc DB?** Làm sạch persistence context hoặc dùng transaction/query phù hợp.
9. **Timeout có đủ cho CI không?** Dựa trên SLO của test infra, có diagnostics, không tăng vô hạn.
10. **Có dependency bên ngoài chập chờn không?** Dùng fake/test container khi phù hợp; network thật nên thuộc suite riêng.
11. **Mỗi event có ID riêng chưa?** Không để event cũ vô tình làm điều kiện của test mới đạt.
12. **Test đang khẳng định không xảy ra điều gì?** Cần mốc “đã xử lý hết” để kết luận negative assertion.

Thêm log có `eventId`, tên listener và thread name để debug, nhưng không dựa vào stdout order làm điều kiện pass nếu runtime đa luồng. Nếu muốn chụp thread dump khi timeout, cấu hình test tooling/CI sao cho failure có thông tin về blocked threads và pending tasks.

## 16. Checklist cho pull request

- [ ] Có xác nhận rõ test đang kiểm tra sync multicaster, async multicaster hay `@Async`?
- [ ] Có assertion trên **kết quả thực**, không chỉ publishEvent được gọi?
- [ ] Mọi chờ đợi có tín hiệu observable và timeout hữu hạn?
- [ ] Không dùng `Thread.sleep(...)` để cố đoán listener xong?
- [ ] Có cách nhận lỗi async mà không chỉ dựa vào exception publisher?
- [ ] Nếu dùng gate, release trong `finally` kể cả assertion thất bại?
- [ ] Không chia sẻ latch/future/static mutable state giữa các test?
- [ ] Test có event ID riêng và expectation được đăng ký trước publish?
- [ ] Listener ghi kết quả trước khi phát tín hiệu completion?
- [ ] Executor/context/DB được đóng, không để task cũ lọt sang test kế tiếp?
- [ ] Với AFTER_COMMIT, đã commit thật và test rollback riêng?
- [ ] Không coi một job được enqueue là side effect cuối cùng đã hoàn thành?
- [ ] Test không giả định ordering giữa nhiều worker nếu contract không bảo đảm?
- [ ] Dùng unit test cho logic đơn giản; integration test cho dispatch/proxy/transaction?

**Ghi nhớ:** một test async listener không flaky không cố dự đoán “sau 500 ms chắc chắn xử lý xong”. Nó **điều khiển hoặc quan sát một trạng thái hoàn tất có thật**, chờ bằng primitive có happens-before và timeout hữu hạn, nhận cả lỗi của worker, rồi dọn mọi resource. Với Spring Application Events, cần biết rõ cơ chế async nào đang được dùng, vì mỗi cơ chế có đường dispatch và báo lỗi khác nhau.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.1.21 API — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.1.21 API — ApplicationListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationListener.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [JUnit 5 User Guide — Writing Tests](https://junit.org/junit5/docs/current/user-guide/)
- [Java 17 API — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Java 17 API — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Awaitility Documentation](https://github.com/awaitility/awaitility/wiki/Usage)
