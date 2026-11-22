# Chờ event bất đồng bộ đúng cách trong kiểm thử Spring Application Events

Khi ứng dụng Spring dùng `@Async @EventListener` hoặc một `ApplicationEventMulticaster` cấu hình executor bất đồng bộ, lời gọi `ApplicationEventPublisher.publishEvent(...)` **không đồng nghĩa với việc mọi listener đã xử lý xong**. Test đọc trạng thái ngay sau khi publish có thể thất bại ngẫu nhiên: trên máy nhanh thì pass, trên CI chậm thì fail. Cách “sửa” bằng `Thread.sleep(1000)` chỉ làm bài kiểm thử chậm, dễ flaky và khó phát hiện lỗi thật.

**Chờ đúng cách** là: xác định kết quả quan sát được của listener, đăng ký phương tiện quan sát trước khi publish, chờ **có giới hạn thời gian**, phân biệt thành công/thất bại/timeout, và giải phóng tài nguyên dù assertion lỗi. Các công cụ thường dùng là `CountDownLatch`, `CompletableFuture`, `BlockingQueue` và thư viện `Awaitility` khi cần polling một trạng thái cuối. Mỗi công cụ phù hợp với một loại kiểm thử khác nhau.

Bài học giải thích ngữ nghĩa async event, cung cấp một bộ integration test Java 17+ với Spring Test/JUnit 5 chạy bằng `@Async @EventListener` thật, kiểm tra điều kiện hoàn tất và exception, đồng thời làm rõ các bẫy về thread, transaction, retry, thứ tự và test lifecycle.

## 1. Hiểu đúng điều mà publishEvent() xác nhận

Trong Spring Framework, `publishEvent(event)` là API phát sự kiện. Nó không trả `Future` đại diện cho việc **mọi listener** hoàn thành. Ngữ nghĩa phụ thuộc cấu hình:

| Cấu hình | Listener chạy ở đâu? | Khi `publishEvent` trả về, biết được gì? |
| --- | --- | --- |
| `@EventListener` thường; multicaster mặc định | Trên thread phát event | Những listener đồng bộ được gọi trong đợt multicast đã hoàn tất hoặc exception đã lan ra |
| `@Async @EventListener` với `@EnableAsync` | Method được submit tới `TaskExecutor` | Task thường đã được lên lịch; **chưa chắc listener hoàn tất** |
| Custom `SimpleApplicationEventMulticaster.setTaskExecutor(...)` | Các listener hỗ trợ async execution được executor chạy | Không thể coi return là hoàn tất tất cả listener |
| `@TransactionalEventListener(AFTER_COMMIT)` | Đăng ký callback theo pha transaction, có thể chạy muộn hơn | Nếu transaction chưa commit, listener chưa nhất thiết chạy |
| Event gửi sang broker/outbox | Ngoài Spring event bus hoặc ngoài tiến trình | Hoàn tất publish nội bộ không phải ack của downstream consumer |

Spring Framework mặc định dispatch đồng bộ. `@Async` là **một sự thay đổi cấu hình**; không có ý nghĩa “mọi application event mặc nhiên async”. Tương tự, khi custom multicaster dùng executor, không phải listener nào cũng có thể được đẩy sang thread khác; một số transactional listener cần giữ execution trên caller thread để đăng ký transaction synchronization.

~~~text
Test thread
   |
   +-- publishEvent(JobRequested)
   |       |
   |       +-- Spring listener adapter
   |               |
   |               +-- @Async proxy: submit task
   |                               |
   +-- publishEvent() returns     |       [TEST CHƯA ĐƯỢC KẾT LUẬN]
   |                               |
   +-- test chờ tín hiệu cụ thể    |
                                   +-- worker thread chạy listener
                                           |
                                           +-- ghi DB/call service
                                           +-- cập nhật kết quả
                                           +-- báo completed/failed
   |
   +-- assertion khi kết quả đã được quan sát
~~~

Một listener async cũng có thể ném exception mà caller của `publishEvent` **không thấy trực tiếp**. Với `@Async` method `void`, Spring chuyển exception chưa bắt tới `AsyncUncaughtExceptionHandler` hoặc cơ chế logging mặc định. Vì vậy test “publish không throw” **không** chứng minh listener thành công.

## 2. Năm nguyên tắc để test async không flaky

1. **Chọn tín hiệu đúng:** `started` nghĩa là listener đã bắt đầu, `completed` nghĩa là bước xử lý cần kiểm tra đã xong. Không đánh đồng hai tín hiệu.
2. **Đăng ký trước khi publish:** tạo latch/future/queue, spy hay bản ghi theo `eventId` **trước** khi gọi `publishEvent`, tránh listener chạy nhanh hơn lúc test chuẩn bị quan sát.
3. **Luôn có timeout hữu hạn:** `await(5, SECONDS)`, `future.get(5, SECONDS)`, hoặc `Awaitility.await().atMost(...)`; không dùng `get()`/`join()` vô thời hạn trong kiểm thử.
4. **Báo cả failure, không chỉ success:** một completion latch đặt trong `finally` chỉ chứng minh task đã kết thúc, không chứng minh xử lý thành công. Cần lưu exception và assert kết quả.
5. **Dọn trạng thái và giải phóng worker:** clear dữ liệu test, release gate trong `finally`/`@AfterEach`, đóng context/executor theo lifecycle để suite không giữ threads hoặc ảnh hưởng test khác.

**Tín hiệu nên phản ánh hành vi nghiệp vụ**. Nếu listener cập nhật bản ghi DB, kiểm tra trạng thái DB đã thực sự visible; nếu listener gọi một gateway, kiểm tra invocation hoặc acknowledgement của gateway; nếu listener xử lý logic không side effect, test có thể dùng `CompletableFuture<Result>` trong probe/fixture để báo kết quả.

## 3. CountDownLatch: đợi listener chạy hoặc mở một “cổng” điều khiển

Một latch thông dụng đợi listener báo xong:

~~~java
CountDownLatch done = new CountDownLatch(1);

@Async
@EventListener
public void onEvent(JobRequested event) {
    try {
        process(event);
    } finally {
        done.countDown();
    }
}
~~~

Đây là **trích đoạn minh họa**, không phải class Java độc lập. Với `finally`, test biết method đã tới cuối bất kể thành công hay thất bại. Nếu yêu cầu test xác nhận success, phải ghi riêng kết quả hoặc lỗi.

Trong test:

~~~java
publisher.publishEvent(new JobRequested("job-1"));
assertTrue(done.await(5, TimeUnit.SECONDS),
    "Async listener did not finish");
~~~

Không dùng:

~~~java
publisher.publishEvent(new JobRequested("job-1"));
Thread.sleep(1000);
assertEquals("DONE", repository.findStatus("job-1"));
~~~

Đoạn `Thread.sleep` là **anti-pattern**: chờ thừa nếu listener xong trong 10 ms, nhưng vẫn fail nếu CI cần 1500 ms. Sleep cũng không phân biệt task chưa được schedule, exception, deadlock hay timeout của downstream.

### Hai latch: started và release

Để chứng minh listener **thật sự chạy bất đồng bộ**, dùng một latch báo đã vào method và một latch làm cổng chờ:

~~~text
test: publish -> await(started) -> assert(!finished) -> release
                   ^                                     |
                   |                                     v
worker:        countDown(started) -> await(release) -> process -> complete
~~~

Điều này tránh một phép đo thời gian thiếu ổn định như “`publishEvent` phải trả trong dưới 20 ms”. Test kiểm soát rõ một điều kiện logic: **khi chưa release, listener không thể hoàn tất**. Bài test hoàn chỉnh ở mục 6 sử dụng kỹ thuật này.

## 4. CompletableFuture: biết được success, error và timeout

`CompletableFuture<T>` hữu ích khi muốn giữ cả kết quả cuối và nguyên nhân lỗi:

~~~java
CompletableFuture<String> result = new CompletableFuture<>();

// Trong listener:
try {
    String status = process(event);
    result.complete(status);
} catch (Exception ex) {
    result.completeExceptionally(ex);
    throw ex;
}

// Trong test, có timeout:
String actual = result.get(5, TimeUnit.SECONDS);
assertEquals("DONE", actual);
~~~

Đây là **trích đoạn**, giả định `process` ném `RuntimeException` hoặc cần xử lý checked exception phù hợp. Không nên tạo một shared `CompletableFuture` cho mọi event khi test phát nhiều event gần nhau: hãy gắn future với ID cụ thể.

Ba kết cục khi chờ bằng `get(timeout, unit)`:

| Kết quả | Ý nghĩa |
| --- | --- |
| Trả `T` | Future đã complete thành công |
| Ném `ExecutionException` | Future complete exceptionally; xem `getCause()` |
| Ném `TimeoutException` | Chưa hoàn tất trước timeout; **không tự khẳng định task đã thất bại** |
| Ném `InterruptedException` | Thread đang đợi bị interrupt; cần giữ nguyên contract ngắt |

**`CompletableFuture.join()` không có timeout truyền trực tiếp**; trong test thường ưu tiên `get(5, TimeUnit.SECONDS)`. `orTimeout(...)` có thể cấu hình giới hạn cho future, nhưng nó thay đổi trạng thái completion của future đó; không phải cách duy nhất và không thay thế xử lý cancellation/resource cleanup.

Lưu ý quan trọng: `@Async @EventListener` không khiến `ApplicationEventPublisher.publishEvent` tự trả `CompletableFuture`. Future trong ví dụ là **test probe/application contract do bạn thiết kế**, không phải giá trị trả về của event publisher. Spring cũng không hỗ trợ dùng **giá trị trả về của async event listener** để tự publish event mới; muốn làm vậy, gọi `ApplicationEventPublisher` tường minh trong listener.

## 5. Awaitility và eventual assertions: khi cần quan sát trạng thái cuối

Nếu listener ghi DB, cache hoặc trạng thái repository, đôi khi không nên đưa latch vào code nghiệp vụ chỉ để phục vụ test. Khi đó dùng **Awaitility** để lặp assertion cho tới khi trạng thái trở thành đúng:

~~~groovy
// dependency bổ sung cho test (trích đoạn build.gradle):
testImplementation 'org.awaitility:awaitility:4.2.0'
~~~

~~~java
// Trích đoạn trong một JUnit test:
await()
    .atMost(Duration.ofSeconds(5))
    .pollInterval(Duration.ofMillis(50))
    .untilAsserted(() ->
        assertEquals("DONE", statusRepository.findStatus("job-1"))
    );
~~~

Cần `import static org.awaitility.Awaitility.await;`, `java.time.Duration` và repository fixture. Mỗi lần polling phải là một phép đọc **ít hoặc không có side effect**. Không lặp một lệnh `submitOrder()` hoặc `publishEvent()` trong `untilAsserted`: như vậy test tự tạo nhiều event và có thể dẫn đến duplicate side effect.

### Chọn latch, future hay Awaitility

| Mục tiêu | Công cụ thích hợp | Cạm bẫy |
| --- | --- | --- |
| Đợi một tín hiệu “đã bắt đầu” | `CountDownLatch` | Started không đồng nghĩa succeeded |
| Đợi kết quả hoặc exception của một event | `CompletableFuture<T>` | Phải truyền/mapping result đúng `eventId` |
| Nhận từng phần tử từ stream event | `BlockingQueue<T>.poll(timeout)` | Một `poll` nhận một phần tử, không tự đợi tất cả |
| Đợi trạng thái cuối trong DB | `Awaitility.untilAsserted` | Tránh polling trong transaction nhìn snapshot cũ |
| Đợi N tác vụ đã biết | `CompletableFuture.allOf(...).get(timeout)` | Fail nhanh/late errors cần thu thập riêng |
| Cần giả lập thứ tự/đua tranh có kiểm soát | `started` + `release` latches | Phải nhả gate trong finally |
| Kiểm tra một lời gọi mock đã xảy ra | Mockito `verify(..., timeout(...))` | Invocation không chứng minh tác vụ đã hoàn tất |

`Awaitility` phù hợp khi business outcome có thể quan sát bên ngoài; latch/future hữu ích khi cần điều khiển **chính xác thời điểm thực thi** hoặc kiểm tra failure. Với integration test quan trọng, có thể kết hợp: future báo “listener đã hoàn tất”, rồi query database để xác minh dữ liệu thực tế.

## 6. Bộ integration test hoàn chỉnh Java 17+: @Async listener chạy thật

Ví dụ sau dùng **Spring Framework 6.2.x**, JUnit 5 và một `ThreadPoolTaskExecutor` có đúng **một worker thread** để kiểm soát thứ tự trong fixture. Nó **không** chuyển executor thành synchronous: listener thật sự chạy qua `@Async` proxy. Từng event có `eventId` riêng và một `Work` chứa tín hiệu started, cổng release, future completion và future ghi nhận uncaught error.

Có bốn test:

1. Publisher trả về trong khi listener còn bị chặn; sau release future hoàn tất.
2. Listener ném exception: publisher không nhận exception async, nhưng future và `AsyncUncaughtExceptionHandler` đều ghi lỗi.
3. Await có timeout được kiểm tra mà không làm treo suite; sau đó release và xác nhận hoàn tất.
4. Nhiều event: `CompletableFuture.allOf` đợi đủ các tác vụ và không dựa vào sleep.

### 6.1. settings.gradle và build.gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'async-event-waiting-tests'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
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
    testImplementation platform('org.springframework:spring-framework-bom:6.2.9')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-aop'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Framework có module `spring-context` chứa `ApplicationEventPublisher`, `@EventListener`, `@EnableAsync` và `ThreadPoolTaskExecutor`. `spring-aop` phục vụ async proxy, còn `spring-test` cung cấp `@SpringJUnitConfig`. Nếu dùng Spring Boot project, nên để Boot quản lý phiên bản Spring thay vì ép các module độc lập không tương thích.

### 6.2. File src/test/java/example/events/AsyncEventWaitingTest.java

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Method;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(AsyncEventWaitingTest.Config.class)
class AsyncEventWaitingTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired Probe probe;

    @AfterEach
    void releaseAnyBlockedWorkers() {
        // Nếu assertion fail giữa chừng, không giữ worker mắc kẹt.
        probe.releaseAll();
    }

    @Test
    void waitsForActualCompletionNotMerelyPublication() throws Exception {
        Work state = probe.register("one");

        try {
            publisher.publishEvent(new WorkRequested("one", false));

            assertTrue(state.started.await(5, TimeUnit.SECONDS));
            // Worker đã bắt đầu, nhưng đang chờ cổng release.
            assertFalse(state.completed.isDone());
        } finally {
            state.release.countDown();
        }

        String threadName = state.completed.get(5, TimeUnit.SECONDS);
        assertTrue(threadName.startsWith("events-"));
        assertFalse(state.uncaught.isDone());
    }

    @Test
    void asyncExceptionIsObservableWithoutEscapingPublisher()
            throws Exception {
        Work state = probe.register("fail");

        try {
            // Không throw lỗi từ thân listener lúc publish:
            // listener chỉ chạy sau khi release trên worker thread.
            publisher.publishEvent(new WorkRequested("fail", true));
            assertTrue(state.started.await(5, TimeUnit.SECONDS));
        } finally {
            state.release.countDown();
        }

        ExecutionException exception = assertThrows(
            ExecutionException.class,
            () -> state.completed.get(5, TimeUnit.SECONDS)
        );

        IllegalStateException root = assertInstanceOf(
            IllegalStateException.class,
            exception.getCause()
        );
        assertEquals("boom:fail", root.getMessage());

        Throwable asyncError = state.uncaught.get(5, TimeUnit.SECONDS);
        assertInstanceOf(IllegalStateException.class, asyncError);
        assertEquals("boom:fail", asyncError.getMessage());
    }

    @Test
    void timeoutIsBoundedAndDoesNotLeaveWorkerBlocked()
            throws Exception {
        Work state = probe.register("slow");
        publisher.publishEvent(new WorkRequested("slow", false));

        try {
            assertTrue(state.started.await(5, TimeUnit.SECONDS));
            // Cổng chưa mở nên completion chắc chắn chưa thể xảy ra.
            assertThrows(
                TimeoutException.class,
                () -> state.completed.get(100, TimeUnit.MILLISECONDS)
            );
        } finally {
            state.release.countDown();
        }

        assertTrue(state.completed.get(5, TimeUnit.SECONDS)
            .startsWith("events-"));
    }

    @Test
    void waitsForAllKnownEvents() throws Exception {
        Work first = probe.register("a");
        Work second = probe.register("b");

        try {
            publisher.publishEvent(new WorkRequested("a", false));
            publisher.publishEvent(new WorkRequested("b", false));

            // Fixture có một worker, event a đang giữ cổng.
            assertTrue(first.started.await(5, TimeUnit.SECONDS));
            first.release.countDown();

            assertTrue(second.started.await(5, TimeUnit.SECONDS));
            second.release.countDown();

            CompletableFuture.allOf(
                first.completed, second.completed
            ).get(5, TimeUnit.SECONDS);

            assertTrue(first.completed.isDone());
            assertTrue(second.completed.isDone());
        } finally {
            first.release.countDown();
            second.release.countDown();
        }
    }

    record WorkRequested(String id, boolean fail) { }

    static class Work {
        final CountDownLatch started = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);

        final CompletableFuture<String> completed =
            new CompletableFuture<>();

        final CompletableFuture<Throwable> uncaught =
            new CompletableFuture<>();
    }

    static class Probe {
        private final ConcurrentHashMap<String, Work> states =
            new ConcurrentHashMap<>();

        Work register(String id) {
            Work result = new Work();
            if (states.putIfAbsent(id, result) != null) {
                throw new IllegalArgumentException("duplicate id: " + id);
            }
            return result;
        }

        Work require(String id) {
            Work state = states.get(id);
            if (state == null) {
                throw new IllegalArgumentException("unknown id: " + id);
            }
            return state;
        }

        void releaseAll() {
            states.values().forEach(w -> w.release.countDown());
        }
    }

    static class AsyncWorkerListener {
        private final Probe probe;

        AsyncWorkerListener(Probe probe) {
            this.probe = probe;
        }

        @Async("eventsExecutor")
        @EventListener
        public void onWork(WorkRequested event) {
            Work state = probe.require(event.id());
            state.started.countDown();

            try {
                if (!state.release.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "gate timed out:" + event.id()
                    );
                }

                if (event.fail()) {
                    throw new IllegalStateException(
                        "boom:" + event.id()
                    );
                }

                state.completed.complete(
                    Thread.currentThread().getName()
                );
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                state.completed.completeExceptionally(ex);
                throw new IllegalStateException(
                    "listener interrupted", ex
                );
            } catch (RuntimeException ex) {
                state.completed.completeExceptionally(ex);
                throw ex;
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    static class Config implements AsyncConfigurer {

        // AsyncConfigurer được khởi tạo rất sớm. Không inject
        // phụ thuộc phức tạp vào cấu hình xử lý exception.
        private final Probe probe = new Probe();

        @Bean
        Probe probe() {
            return probe;
        }

        @Bean
        AsyncWorkerListener workerListener(Probe probe) {
            return new AsyncWorkerListener(probe);
        }

        @Bean("eventsExecutor")
        ThreadPoolTaskExecutor eventsExecutor() {
            ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(16);
            executor.setThreadNamePrefix("events-");
            return executor;
        }

        @Override
        public AsyncUncaughtExceptionHandler
                getAsyncUncaughtExceptionHandler() {
            return (Throwable ex, Method method, Object... args) -> {
                if (args.length == 1
                        && args[0] instanceof WorkRequested event) {
                    probe.require(event.id()).uncaught.complete(ex);
                }
            };
        }
    }
}
~~~

### 6.3. Chạy test và kết quả mong đợi

Với Gradle wrapper đã có trong project:

~~~bash
./gradlew test --tests "example.events.AsyncEventWaitingTest"
~~~

Trên Windows PowerShell:

~~~powershell
./gradlew.bat test --tests "example.events.AsyncEventWaitingTest"
~~~

**Không có stdout cố định do bốn test tự in ra**; điều quan trọng là các assertions JUnit 5. Kết quả mong đợi khi cấu hình hoạt động đúng:

| Test | Kết quả cần quan sát |
| --- | --- |
| `waitsForActualCompletionNotMerelyPublication` | Listener báo started, completion chưa có khi gate đóng; mở gate rồi future trả tên thread bắt đầu bằng `events-` |
| `asyncExceptionIsObservableWithoutEscapingPublisher` | Publish không ném lỗi của listener; future ném `ExecutionException` với cause `IllegalStateException("boom:fail")`; async uncaught handler cũng nhận lỗi |
| `timeoutIsBoundedAndDoesNotLeaveWorkerBlocked` | `get(100, MILLISECONDS)` ném `TimeoutException` khi gate chưa mở; sau release future hoàn tất |
| `waitsForAllKnownEvents` | `allOf(...).get(timeout)` hoàn tất sau khi hai work units đều được release và xử lý |

Các test không đo thời gian thực thi để suy luận async bằng ngưỡng milliseconds, không cần `Thread.sleep`, và không phụ thuộc vào log text. `@AfterEach` giải phóng mọi gate còn giữ khi một assertion lỗi, tránh làm worker giữ tài nguyên vô thời hạn.

**Vì sao dùng một worker trong fixture?** Để kết quả bài test nhiều event có trình tự điều khiển rõ ràng. Đây không phải cam kết production `@Async` luôn xử lý theo thứ tự. Nếu executor có nhiều workers, thứ tự bắt đầu và kết thúc có thể khác nhau. Thực tế nên kiểm tra **tập kết quả** hoặc tổng số thành công khi thứ tự không phải một yêu cầu nghiệp vụ.

**Vì sao không dùng Future trả về từ listener?** Method `@Async @EventListener` thường khai báo `void`; lời gọi `publishEvent` không thu kết quả của listener. `Probe` là kênh kiểm thử có chủ đích gắn `eventId` với các completion signals. Với mã production cần trả kết quả cho caller, một service method tường minh trả `CompletableFuture` có thể phù hợp hơn event-driven fire-and-forget.

## 7. Kiểm tra exception và tiêu chí hoàn tất thực sự

Một latch `done.countDown()` trong `finally` báo đã ra khỏi `try`, nhưng không cho biết `process()` có thành công hay không. Cần tránh test sau:

~~~java
// SAI về ngữ nghĩa nếu done đếm cả nhánh lỗi:
publisher.publishEvent(event);
assertTrue(done.await(5, TimeUnit.SECONDS));
// Từ đây KHÔNG được suy rằng email đã gửi hoặc DB đã cập nhật.
~~~

Trong bài test hoàn chỉnh, `completed.completeExceptionally(ex)` giúp JUnit xem `ExecutionException.getCause()`. Đồng thời `getAsyncUncaughtExceptionHandler()` chứng minh exception của method async `void` được xử lý **ngoài** đường return của publisher.

Hãy xác định **điểm hoàn tất thực tế**:

- `listener.started`: method đã vào thân.
- `repository.save(...)` được gọi: invocation đã xảy ra; chưa chắc transaction đã commit.
- `gateway.send(...)` trả về: chỉ có nghĩa theo contract của gateway; chưa chắc client cuối đã nhận.
- DB transaction commit: dữ liệu được ghi thành công theo isolation/transaction policy.
- Broker ack: broker đã xác nhận theo chế độ acks, chưa chắc consumer xử lý xong.
- Future complete success: kết quả ứng dụng tự định nghĩa đã hoàn tất.

Nếu listener có nhiều bước và chỉ bước đầu báo latch, test có thể pass khi bước sau vẫn lỗi. Vì vậy đặt tín hiệu `completed` **sau** tất cả thao tác cần chứng minh, đồng thời ghi exception ở mọi nhánh failure có thể xảy ra.

### Khi cần kiểm tra side effect qua Mockito

Một ví dụ JUnit/Mockito có thể dùng:

~~~java
verify(notificationGateway, timeout(5000))
    .sendReceipt("ORD-1");
~~~

Đây là **trích đoạn** cần mock `notificationGateway` đã inject và import `org.mockito.Mockito.timeout`. Cơ chế `timeout` của Mockito đợi cho đến khi invocation xảy ra (hoặc hết giới hạn), nhưng **invocation không bảo đảm method đã hoàn tất mọi side effect**. Nếu yêu cầu xác minh trạng thái cuối/ack, phải đợi observable outcome tương ứng.

## 8. @Transactional và @TransactionalEventListener làm thời điểm chờ phức tạp hơn

### 8.1. Publish trong transaction rồi chờ async listener có thể tạo deadlock

~~~text
test/service thread:
  BEGIN TX
  UPDATE order = PAID             [chưa commit]
  publish OrderPaid
  future.get(timeout)             [đợi listener]

async listener worker:
  SELECT order từ transaction khác
  chờ dữ liệu/lock hoặc đọc trạng thái cũ
  không thể hoàn thành đúng điều kiện test

test/service thread chưa commit vì còn đợi future
~~~

Lỗi ở đây không thể giải quyết chỉ bằng tăng timeout. Nếu side effect của listener cần dữ liệu đã commit, **không đợi nó bên trong transaction nguồn đang mở**. Hãy kết thúc transaction trước khi chờ; hoặc sử dụng transaction-phase listener và test transaction boundary một cách chủ động.

### 8.2. Đợi AFTER_COMMIT phải thực sự commit

Với `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`, callback được gắn với commit thành công. Trong Spring TestContext, một test gắn `@Transactional` thường **rollback ở cuối test**, nên callback after-commit không tự chạy trong lúc test còn nằm trong transaction đó.

Một pattern dùng `TransactionTemplate` trong test không mang `@Transactional`:

~~~java
transactionTemplate.executeWithoutResult(status -> {
    service.writeData();
    publisher.publishEvent(new OrderPaid("O-1"));
}); // transaction được commit tại đây nếu không có rollback

// Sau khi transaction đã commit, mới đợi observable async outcome:
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertEquals("SENT", deliveryRepository.findStatus("O-1"))
    );
~~~

Đây là **trích đoạn** cần `transactionTemplate`, `service`, `publisher`, `deliveryRepository` và Awaitility. Nếu dùng test-managed transaction, Spring có `TestTransaction.flagForCommit()` và `TestTransaction.end()` khi phù hợp, nhưng phải kiểm soát rõ ranh giới commit.

**Chú ý:** cấu hình custom multicaster executor không có nghĩa mọi `@TransactionalEventListener` được gọi trên pool thread. Một số listener transactional cần chạy trên caller thread để đăng ký synchronization. Muốn xử lý business work bất đồng bộ **sau commit**, thiết kế callback/async executor và security/tracing context riêng, rồi kiểm thử đường thực thi cuối.

### 8.3. Async không tự mang transaction, SecurityContext hoặc MDC

JDBC transaction, `SecurityContextHolder` và MDC thường gắn thread trong môi trường imperative. `@Async` chuyển sang executor thread khác; chúng không tự truyền đầy đủ nếu không có cơ chế propagation. Nếu listener kiểm tra quyền của người dùng, cân nhắc `DelegatingSecurityContextAsyncTaskExecutor`; nếu cần trace correlation, dùng context propagation phù hợp hoặc event payload có correlation ID đã kiểm chứng.

Với reactive stack, Reactor subscriber Context và `TransactionalEventPublisher` có cơ chế riêng; không thể sao chép assumption về JDBC thread-local sang R2DBC.

## 9. Tránh test ngẫu nhiên khi nhiều event và nhiều listener

### 9.1. Mỗi event dùng một ID

Một test có thể publish cùng loại event nhiều lần. Nếu dùng một `CountDownLatch` hoặc future toàn cục, tín hiệu event trước có thể làm test event sau “pass giả”. Gắn `eventId` độc lập để mọi kết quả traceable:

~~~text
event-101 -> future-101
event-102 -> future-102
event-103 -> future-103
~~~

Trong môi trường nhiều test chạy song song, dùng ID duy nhất trong phạm vi suite hoặc tạo context/probe tách biệt. Không dùng `Thread.sleep` để “đợi event cũ chạy hết” trước khi test tiếp.

### 9.2. Không giả định thứ tự khi executor có nhiều thread

`@Order` sắp xếp thứ tự invocation của listeners cho cùng một event theo dispatch semantics, **không bảo đảm thứ tự hoàn thành async work**. Nếu nhiều listeners viết vào cùng state, cần định nghĩa behavior khi chúng chạy đồng thời. Test nên chờ mọi task liên quan và so sánh tập kết quả khi thứ tự không quan trọng.

Nếu nghiệp vụ **thực sự yêu cầu thứ tự**, hãy bảo đảm ở cơ chế xử lý: single-thread executor/partition per key, sequencer hoặc workflow orchestration phù hợp, không chỉ chỉnh test để kỳ vọng một thứ tự ngẫu nhiên.

### 9.3. Đếm đúng số event hoàn tất

Với N công việc đã biết, `CountDownLatch(N)` có thể đợi N lần complete. Nhưng nếu listener bị gọi thừa N lần, latch xuống 0 và test vẫn có thể pass nếu không kiểm tra **đúng event IDs, uniqueness và side effects**. Tương tự, `allOf` chỉ theo dõi các future đã đăng ký, không tự chứng minh event ngoài dự kiến không xảy ra.

Khi cần kiểm tra “chỉ đúng một invocation”, dùng mock invocations/counters theo event ID và xem `verifyNoMoreInteractions` hay cơ chế assertion tương ứng; nhớ rằng một listener async khác có thể còn đang chạy, nên phải có điều kiện suite ổn định trước khi kiểm tra không có thêm event.

## 10. Timeout, cancellation và cleanup: ba việc khác nhau

Một timeout không tự động dừng listener.

| Điều xảy ra trong test | Hệ quả |
| --- | --- |
| `future.get(timeout)` ném `TimeoutException` | Thread test ngừng đợi; worker có thể vẫn chạy |
| `latch.await(timeout)` trả `false` | Không đủ tín hiệu trước deadline; task có thể hoàn thành muộn |
| `future.cancel(true)` | Có thể gửi interrupt/cancellation; tác vụ không nhất thiết đã dừng |
| Executor shutdown | Tùy cấu hình, có thể đợi hoặc ngắt tác vụ đang chạy |
| Task exception | Cần ghi nhận và assert; không tự suy nó là timeout |

Đặt release/cleanup trong `finally`, tránh để cả suite treo khi một assertion thất bại. Nếu test dùng latch bên trong listener, cần bảo đảm listener không giữ thread mãi khi test context bị đóng. Trong production, cũng phải có timeout cho I/O của client (HTTP, JDBC, broker) chứ không chỉ timeout của test.

**Không dùng `assertTimeoutPreemptively` một cách máy móc với transaction/context thread-bound.** JUnit có thể thực thi mã kiểm thử trong thread riêng, làm mất ngữ cảnh Spring TestContext transaction hoặc security `ThreadLocal`. Với event async, thường rõ ràng hơn khi đặt timeout trực tiếp lên tín hiệu đang chờ và cho phép framework dọn lifecycle bình thường.

## 11. RecordApplicationEvents có giải quyết việc chờ listener không?

Spring TestContext hỗ trợ `@RecordApplicationEvents` và `ApplicationEvents` để kiểm tra những application events được publish trong quá trình test. Chúng hữu ích để xác nhận **event đã được phát** và inspect payload.

Tuy nhiên, event đã xuất hiện trong danh sách record **không chứng minh listener async đã kết thúc xử lý**. Thí dụ một test có thể assert rằng `OrderCreated` được publish, trong khi listener `@Async` gửi email vẫn đang chờ pool scheduling. Vì vậy:

- **Kiểm tra phát event:** dùng `ApplicationEvents`, event spy hoặc publisher fixture thích hợp.
- **Kiểm tra xử lý async:** chờ completion/side effect với timeout.
- **Kiểm tra commit:** chủ động kết thúc transaction trước khi xác nhận after-commit behavior.
- **Kiểm tra lỗi:** chờ một error channel/handler, không chỉ kiểm tra `publishEvent` không throw.

Nếu cần chứng minh cả bốn giai đoạn, viết các assertion riêng có tên rõ để khi fail biết vấn đề nằm ở publication, scheduling, business handling hay transaction.

## 12. Khác nhau giữa deterministic test và fake synchronous executor

Một cách làm test đơn giản là thay executor bằng `SyncTaskExecutor`. Cách này có thể hữu ích cho unit test business logic tách riêng, nhưng nó **đổi ngữ nghĩa thực thi**:

~~~java
@Bean("eventsExecutor")
TaskExecutor eventsExecutor() {
    return new SyncTaskExecutor();
}
~~~

Đây là trích đoạn **chỉ dành cho test mode**, yêu cầu import `TaskExecutor` và `SyncTaskExecutor`. Khi áp dụng, async work có thể chạy trên caller thread; `publishEvent` có thể chặn đến lúc xử lý xong, exception/transaction/security context có thể khác production. Không dùng test executor đồng bộ làm **bằng chứng** rằng pipeline async thật không có race, không bị deadlock, đã propagate context hoặc không mất event.

Một chiến lược kiểm thử tốt thường gồm:

1. Unit test business logic thuần túy, không cần async.
2. Integration test dùng executor bất đồng bộ thật và tín hiệu có timeout (như mục 6).
3. Kiểm thử hệ thống có database/broker thật hoặc test containers khi yêu cầu observability/durability cao, kiểm tra failure, retry, duplicate và shutdown.

## 13. Bảng chẩn đoán khi test async event bị flaky

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Assert DB ngay sau `publishEvent` lúc pass lúc fail | Listener chưa xong | Await một trạng thái cuối, có timeout |
| Test treo vô hạn | `get()`/`join()` không deadline hoặc gate không được release | Dùng `get(timeout)`, `finally`, kiểm tra deadlock |
| Publish trả về nhưng email không gửi | Async listener fail hoặc task bị mất | Kiểm tra `AsyncUncaughtExceptionHandler`, outcome/queue và delivery contract |
| Latch báo done nhưng assertion business fail | `countDown` trong finally báo kết thúc cả khi lỗi | Ghi failure riêng, assert success |
| Test `@Transactional` không thấy after-commit listener | Test transaction chưa commit, mặc định rollback | Commit chủ động với `TransactionTemplate`/`TestTransaction` |
| Test pass với `SyncTaskExecutor` nhưng fail trên production pool | Thread/timing semantics khác | Dùng executor async thật ở integration tests |
| Listener không async dù có `@Async` | Thiếu `@EnableAsync`, self-invocation, method không qua proxy | Kiểm tra bean/proxy/executor thread |
| Listener có lỗi nhưng `assertThrows` quanh publisher không bắt | Exception xảy ra trên worker thread | Expose result/error future hoặc AsyncUncaughtExceptionHandler |
| Hai event liên tiếp trả kết quả lẫn nhau | Dùng shared probe/global latch không gắn ID | Per-event correlation key, reset fixture |
| Test phụ thuộc thứ tự completion của hai listeners | Pool scheduling không có ordering guarantee | Assert theo tập kết quả hoặc thiết kế ordering thực |
| `await().untilAsserted(...)` vẫn không thấy DB | Test đang giữ transaction snapshot/lock | Đọc sau commit, kiểm tra isolation và transaction boundary |
| Runtime lúc shutdown có tasks bị reject | Executor queue full/shutting down | Test chính sách rejection, logging và draining |

**Không tăng timeout lên rất lớn để che một race/deadlock xác định được.** Timeout hợp lý nên đủ cho CI bình thường, còn lý do fail phải được log và mô tả rõ; thời gian chờ dài chỉ khiến nguyên nhân khó tìm hơn.

## 14. Checklist áp dụng

- [ ] Đã phân biệt listener đồng bộ, `@Async` và custom multicaster executor.
- [ ] Có `@EnableAsync` và listener thực sự được Spring proxy xử lý.
- [ ] Đăng ký latch/future/spy trước khi publish, gắn với event ID duy nhất.
- [ ] Assert đúng điều kiện hoàn tất (result, DB state, gateway ack), không chỉ listener started.
- [ ] Dùng timeout hữu hạn; không dùng `Thread.sleep` làm phương thức đồng bộ kiểm thử.
- [ ] Phân biệt success, exceptional completion và timeout.
- [ ] Không để task bị kẹt khi assertion fail: release trong finally và đóng executor theo lifecycle.
- [ ] Không giả định thứ tự completion khi nhiều worker threads.
- [ ] Không đợi after-commit work bên trong transaction nguồn chưa commit.
- [ ] Có kiểm tra exception async qua handler/observable outcome.
- [ ] Test không vô tình chạy dưới một executor đồng bộ khác production.
- [ ] Với eventual state, polling là read-only và chạy sau commit phù hợp.
- [ ] Không xem `ApplicationEvents` ghi nhận publication là bằng chứng consumer đã hoàn tất.
- [ ] Không suy rằng `@Async` làm event có retry hoặc durability.

## 15. Câu hỏi tự kiểm tra

**Câu 1:** Vì sao `publishEvent(...)` trả về không chứng minh `@Async @EventListener` đã chạy xong?

Vì publisher thường chỉ gửi invocation tới async proxy/executor, còn worker tiếp tục xử lý sau đó. Spring không trả một Future tổng hợp của các listener.

**Câu 2:** Vì sao `Thread.sleep(1000)` không phải chiến lược đợi đúng?

Vì 1000 ms có thể quá dài khi task nhanh, quá ngắn khi CI chậm. Nó không báo lý do thất bại và gây flaky tests.

**Câu 3:** Latch `done` được countDown trong `finally` có chứng minh listener thành công?

Không. Nó có thể giảm về 0 cả khi exception xảy ra. Cần một result/error channel như `CompletableFuture` hoặc kiểm tra side effect.

**Câu 4:** `CompletableFuture.get(5, SECONDS)` khác `join()` ở điểm nào?

`get(timeout, unit)` cho giới hạn chờ và phân biệt `TimeoutException`, `ExecutionException`; `join()` không nhận trực tiếp tham số timeout và ném `CompletionException` khi future thất bại.

**Câu 5:** Tại sao không nên await listener after-commit trong một test `@Transactional` chưa kết thúc?

Vì callback cần transaction commit trước khi thực thi, trong khi test có thể đang giữ transaction mở và chờ chính callback đó. TestContext thường rollback sau test.

**Câu 6:** Khi nào Awaitility tốt hơn latch?

Khi muốn quan sát trạng thái cuối (ví dụ DB status `SENT`) mà không đưa test-only latch vào code nghiệp vụ. Polling assertion nên side-effect-free và có timeout.

**Câu 7:** Bật `SyncTaskExecutor` trong test có đủ chứng minh hệ thống async an toàn không?

Không. Nó bỏ qua nhiều đặc tính thread, transaction/context và race của production executor. Cần ít nhất một integration test với async executor thật.

**Ghi nhớ:** **Chờ event bất đồng bộ đúng cách nghĩa là đợi một tín hiệu hoàn tất có thể kiểm chứng, với timeout và đường báo lỗi rõ ràng.** `CountDownLatch` điều khiển thời điểm, `CompletableFuture` mang kết quả/lỗi, `Awaitility` quan sát eventual state. Không lấy return của `publishEvent` hoặc một khoảng sleep tùy ý làm bằng chứng listener đã thành công.

## Tài liệu tham khảo

- [Spring Framework – Application Events và Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework – Task Execution and Scheduling, @Async](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework – EnableAsync và AsyncConfigurer API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html)
- [Spring Framework – SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework – TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework – Test Execution Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/test-execution-events.html)
- [Awaitility documentation](https://github.com/awaitility/awaitility/wiki/Usage)
