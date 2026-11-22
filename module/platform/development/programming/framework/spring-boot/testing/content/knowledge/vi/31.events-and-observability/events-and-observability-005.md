# Kiểm thử listener đồng bộ, bất đồng bộ và nhánh xử lý lỗi

## 1. Vì sao event listener cần được kiểm thử theo hai mô hình thực thi?

Spring có cơ chế **application events** để các thành phần trong cùng một `ApplicationContext` có thể trao đổi tín hiệu mà không cần gọi trực tiếp nhau. Một service có thể công bố `OrderPlaced`; các listeners khác ghi audit, cập nhật projection hoặc kích hoạt notification. Cách làm này giảm coupling, nhưng khiến test dễ đưa ra kết luận sai về **thời điểm xử lý, luồng thực thi, phạm vi transaction, exception và retry**.

Ví dụ:

```java
publisher.publishEvent(new OrderPlaced("ORD-101"));
```

Với một `@EventListener` **đồng bộ mặc định**, listener chạy trong thread của caller; nếu listener ném runtime exception, `publishEvent(...)` có thể ném exception về caller và việc gửi sự kiện tới listener phía sau có thể bị dừng.

Với `@Async @EventListener`, xử lý được giao cho executor: caller có thể quay về trước khi listener hoàn tất. Exception từ method `void` bất đồng bộ **không được truyền về caller thông qua lời gọi `publishEvent` thông thường**. Muốn phát hiện lỗi phải kiểm tra một tín hiệu xử lý, error handler, log/metric hoặc business state. Ngoại lệ lúc **submit task** như executor bị từ chối vẫn có thể xảy ra tại thời điểm publish; không được đồng nhất điều đó với exception phát sinh *bên trong* worker.

Bài thuộc nhóm **Sự kiện và observability**, đề mục **“Kiểm thử listener đồng bộ, bất đồng bộ và nhánh xử lý lỗi”**. Phạm vi là Spring **application events trong cùng JVM**, không phải Kafka/RabbitMQ broker listeners. Ví dụ dùng **Java 17+**, **Spring Boot 3.3.5**, **Spring Framework 6.1**, JUnit Jupiter và `spring-boot-starter-test`.

### Mục tiêu sau khi học

- Phân biệt `ApplicationEventPublisher.publishEvent(...)`, `@EventListener`, `@Async` và `ApplicationEventMulticaster`.
- Test listener đồng bộ: đúng thứ tự, đúng thread, lỗi truyền về publisher, fan-out bị ngắt khi fail.
- Test listener bất đồng bộ: thread của executor, tín hiệu hoàn tất có timeout, lỗi không truyền trực tiếp về publisher.
- Cấu hình `@EnableAsync`, named `ThreadPoolTaskExecutor` và `AsyncUncaughtExceptionHandler`.
- Phân biệt error handler của `@Async` với `SimpleApplicationEventMulticaster.setErrorHandler(...)`.
- Test hai chính sách multicaster: mặc định propagate và custom suppress/record.
- Dùng `@RecordApplicationEvents`/`ApplicationEvents` để xác nhận **event đã được publish**, không nhầm với listener đã xử lý xong.
- Tránh `Thread.sleep`, kiểm tra elapsed time may rủi ro và những assertions phụ thuộc thứ tự scheduling.
- Nhận diện `@TransactionalEventListener`, `@Order`, retry/idempotency, observability và propagation của MDC/tracing context.
- Biết khi nào cần test integration với DB/outbox, broker hoặc hệ thống metrics thực.

## 2. Mô hình cần nắm trước khi viết test

```text
                         ApplicationEventPublisher
                               publishEvent(E)
                                     |
                             ApplicationEventMulticaster
                                     |
                      +--------------+-----------------+
                      |                                |
             @EventListener sync               @Async @EventListener
                      |                                |
                 caller thread                   eventExecutor pool
                      |                                |
                logic + side effect              logic + side effect
                      |                                |
          RuntimeException có thể về         void listener exception
          thẳng publisher                     -> AsyncUncaughtExceptionHandler
                      |                                |
            test assertThrows(...)              test chờ result/failure
            + assert state/order                với timeout
```

**Mặc định** `SimpleApplicationEventMulticaster` dispatch các listeners trong **thread của publisher**. Đây là một cơ chế đồng bộ, dù tên API có chữ “publish”. Spring có thể được cấu hình một task executor chung cho multicaster, nhưng **bài mẫu không làm vậy**: chúng ta giữ mặc định đồng bộ và dùng `@Async("eventExecutor")` **chỉ trên một listener cụ thể**. Nhờ đó test phân biệt hai nhánh chính xác.

| Tín hiệu | Nó chứng minh | Nó không tự chứng minh |
| --- | --- | --- |
| `publishEvent` được gọi | Publisher đã trao event cho cơ chế dispatch | Listener đã xử lý/commit |
| `publishEvent` trả về trong sync mặc định | Các listener đồng bộ đã được dispatch xong nếu không fail | Business side effect ngoài transaction đã bền vững |
| `publishEvent` trả về với @Async | Task đã được gửi đến executor theo cấu hình | Listener đã hoàn tất |
| Listener success callback/probe | Nhánh xử lý đã đi đến điểm báo success | Database/external broker commit nếu callback quá sớm |
| `AsyncUncaughtExceptionHandler` nhận lỗi | Method async void đã ném exception không xử lý | Caller đã nhận lỗi hoặc job sẽ tự retry |
| `ApplicationEvents` ghi nhận event | Sự kiện được công bố trong test | Một listener đã chạy trên thread khác |
| Business table/metric cập nhật | Side effect đã quan sát được | Exactly-once qua mọi failure/retry |

### Event trong JVM không phải hàng đợi bền vững

Spring `ApplicationEventPublisher` không mặc định lưu message trên disk, không có consumer offset và không có dead-letter queue. Nếu JVM chết ngay sau publish hoặc executor chưa xử lý xong, một application event không tự được replay. Nếu nghiệp vụ cần giao nhận bền vững sau DB commit, cân nhắc **transactional outbox**, broker hoặc cơ chế retry/idempotency riêng. Test application event không thay thế end-to-end tests cho những hệ thống đó.

## 3. Event listener đồng bộ: exception có thể làm publisher fail

Ví dụ hai listeners cùng nhận một record `SyncSignal`:

- Listener đầu có `@Order(10)`, ghi lại dấu vết, có thể ném `IllegalStateException` khi tín hiệu yêu cầu mô phỏng lỗi.
- Listener thứ hai có `@Order(20)`, ghi dấu vết tiếp theo.
- Khi thành công, hai listeners được gọi trong publisher thread, theo order.
- Khi listener đầu lỗi, với **multicaster mặc định không có custom ErrorHandler**, lỗi được truyền ngược tới publisher; listener phía sau có thể không được gọi.

```text
publish SyncSignal("A", false)
     -> first @Order(10)   [record "first"]
     -> second @Order(20)  [record "second"]
     -> return normally

publish SyncSignal("B", true)
     -> first @Order(10)   [record "first"; throw]
     -> publisher receives IllegalStateException
     -> second not called under default fail-fast dispatch
```

**Không khái quát hóa cho mọi event infrastructure.** Nếu ứng dụng tùy biến `ApplicationEventMulticaster` với executor hoặc `ErrorHandler`, chuyện propagate/tiếp tục dispatch thay đổi. Test phải phản ánh cấu hình thực tế.

### @Order không phải global ordering trong hệ thống async

`@Order` hỗ trợ quyết định thứ tự invocation cho listeners, nhưng với task executors nhiều threads, **thứ tự hoàn tất** có thể khác. Hai @Async listeners được schedule theo thứ tự không đồng nghĩa side effects của chúng sẽ commit theo thứ tự. Muốn bảo đảm ordering theo nghiệp vụ, cần serialize work theo key/partition hoặc thiết kế flow tường minh.

## 4. Listener bất đồng bộ: test kết quả, không test bằng sleep

`@Async` hoạt động thông qua Spring asynchronous method interception. Cần bật `@EnableAsync` và sử dụng bean được Spring quản lý; nếu gọi một async method bằng `this.someAsyncMethod()` (self-invocation), proxy-based interception có thể bị bypass.

Trong demo, một `@EventListener` có `@Async("eventExecutor")` và nhận `AsyncSignal`. Nó:

- Thành công → báo hoàn tất với `AsyncCompletion` chứa event ID và worker thread name.
- Thất bại → ném `IllegalStateException`.
- `AsyncUncaughtExceptionHandler` của cấu hình thu exception method `void`, ghi vào `AsyncFailure` theo event ID.
- Test chờ `CompletableFuture.get(5, TimeUnit.SECONDS)`, có deadline.
- Test tạo unique correlation ID trước khi publish, không phụ thuộc việc worker nhanh hay chậm.

Không viết:

```java
publisher.publishEvent(event);
Thread.sleep(1000);
assertEquals(1, output.size());
```

Đây là **phản ví dụ**: một giây có thể quá dài trên laptop nhưng quá ngắn trên CI đang chịu tải. Đừng tăng timeout tùy ý khi thiếu tín hiệu hoàn tất; thiết kế một observable condition đúng rồi chờ bounded.

### CompletableFuture trong ví dụ là test probe, không phải EventListener return value

`@Async @EventListener` không hỗ trợ cách phát event mới bằng return value như listener đồng bộ; ví dụ dùng **một `EventProbe` thread-safe** lưu futures theo ID để test chờ. Chúng ta **không** trả `CompletableFuture` từ event listener và không coi `publisher.publishEvent` là future của xử lý.

Trong production, tín hiệu kết quả nên được phản ánh qua state, DB, outbox, metric hoặc error infrastructure có ý nghĩa nghiệp vụ; probe trong lab chỉ minh họa kiểm thử deterministic.

## 5. Phân biệt ba loại lỗi

| Lỗi | Khi nào xảy ra | Ai có thể quan sát | Test nên làm gì |
| --- | --- | --- | --- |
| Listener sync ném `RuntimeException` | Trong dispatch trên publisher thread | Caller của `publishEvent` | `assertThrows` + kiểm tra listener sau có chạy không |
| Listener `@Async void` ném exception | Trong worker thread, sau submit | `AsyncUncaughtExceptionHandler`/logs/metrics | Chờ failure signal với timeout; assert cause/method/ID |
| Executor từ chối task | Ngay khi dispatch/submit hoặc khi shutdown/full queue | Publisher có thể nhận `TaskRejectedException` | Test saturation/rejection riêng, không nhầm với worker exception |
| Global multicaster `ErrorHandler` suppress | Listener thất bại trong dispatch nhưng handler nuốt lỗi | ErrorHandler | Assert publisher không ném và handler ghi nhận |
| Global multicaster propagate | Không có ErrorHandler hoặc handler rethrow | Publisher hoặc executor (tùy execution model) | Assert expected exception ở đúng boundary |
| Transactional listener AFTER_COMMIT lỗi | Sau transaction commit | Transaction callback/log/caller behavior tùy config | Test transaction/commit chính xác; không tuyên bố rollback đã xảy ra |
| Domain side effect lỗi nhưng bị catch | Listener code bắt và log/suppress | Metrics/error store/test probe | Test policy fail-closed/retry, không chỉ HTTP response |

Một ứng dụng có thể cần **failure isolation** (listener A lỗi không chặn listener B) hoặc **fail-fast** (sai audit thì rollback command). Không có chính sách đúng cho mọi hệ thống. Chọn có chủ đích rồi viết test bảo vệ lựa chọn ấy.

## 6. Cấu trúc project minh họa

Dự án này là một ứng dụng Spring Boot không mở web server, có hai loại events và hai policies error handling. Bộ mã chính chạy khi được Spring TestContext khởi tạo; không cần Kafka, RabbitMQ, database hoặc Redis.

```text
spring-event-listener-tests/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/events/
│   ├── EventLessonApplication.java
│   ├── SyncSignal.java
│   ├── AsyncSignal.java
│   ├── EventProbe.java
│   ├── EventCommandService.java
│   ├── FirstSyncListener.java
│   ├── SecondSyncListener.java
│   ├── AsyncSignalListener.java
│   └── EventAsyncConfiguration.java
└── src/test/java/com/example/events/
    ├── EventListenersTest.java
    └── MulticasterPolicyTest.java
```

Bộ test có hai lớp độc lập:

1. `EventListenersTest` dùng **real Spring context**, publisher, annotation listeners, `@EnableAsync`, named executor và error handler. Nó kiểm tra wiring thực.
2. `MulticasterPolicyTest` dùng **SimpleApplicationEventMulticaster trực tiếp**, không Spring Boot context, để cô lập hai chính sách ErrorHandler. Nó **không** khẳng định app production đã cấu hình global multicaster theo một trong hai cách.

### Thông số

- Java: 17+.
- Spring Boot: **3.3.5**.
- Spring Framework: 6.1.x do Boot BOM quản lý.
- Gradle plugin dependency management: 1.1.6.
- JUnit Jupiter và Mockito/AssertJ từ `spring-boot-starter-test`.
- Không có test assertion dựa trên milliseconds elapsed, ngẫu nhiên thứ tự scheduling hoặc real HTTP.

## 7. Cấu hình Gradle

### settings.gradle

```groovy
rootProject.name = 'spring-event-listener-tests'
```

### build.gradle

```groovy
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
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter` mang Spring Context, scheduling/async infrastructure cần thiết và logging. `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring TestContext, AssertJ và `@RecordApplicationEvents`. Không cần web starter vì bài dùng application events nội bộ.

**Nếu chưa có Gradle Wrapper** (dự án liệt kê chỉ hai Gradle scripts) hãy dùng Gradle phù hợp đã cài với `gradle test`, hoặc tạo Wrapper theo chuẩn dự án; đừng chạy `./gradlew` trên thư mục chưa có script này rồi nghĩ rằng test code sai.

## 8. Spring Boot application root

`src/main/java/com/example/events/EventLessonApplication.java`:

```java
package com.example.events;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EventLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(EventLessonApplication.class, args);
    }
}
```

Class root nằm trong package cha `com.example.events` để Spring scan các listeners, publisher service, probe và async configuration. Không có controller. Test dùng `@SpringBootTest(webEnvironment = NONE)` để bảo đảm không mở embedded HTTP port.

### Vì sao không viết một static event bus riêng?

Spring `ApplicationEventPublisher` đã tích hợp với ApplicationContext, `@EventListener` và các lifecycle facilities. Một static event bus custom có thể thiếu bean lifecycle, conditionals, proxies và test support. Muốn học/test Spring EventListener, dùng dispatcher thực của framework rồi làm giả **đầu ra/hạ tầng phụ trợ**, không mock toàn bộ `ApplicationEventPublisher` trong bài integration chính.

## 9. Hai event records có định danh riêng

`src/main/java/com/example/events/SyncSignal.java`:

```java
package com.example.events;

public record SyncSignal(String id, boolean fail) {
    public SyncSignal {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id is required");
        }
    }
}
```

`src/main/java/com/example/events/AsyncSignal.java`:

```java
package com.example.events;

public record AsyncSignal(String id, boolean fail) {
    public AsyncSignal {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id is required");
        }
    }
}
```

Java records là immutable message payloads. `id` giúp test phân biệt các executions, `fail` chỉ là công tắc **synthetic fault injection** cho bài học, không phải thiết kế production event schema. Với production, có thể dùng business event ID, correlation ID, payload version và timestamp theo hợp đồng.

`ApplicationEventPublisher.publishEvent(Object)` hỗ trợ POJO/record không kế thừa `ApplicationEvent`. Spring sẽ wrap object khi cần để dispatch nhưng listener method nhận đúng type record đã khai báo.

### Event ID khác trace ID

Correlation event ID giúp gắn outcome với input. Trace ID từ Micrometer/OpenTelemetry dùng để nối các spans trong observability. Chúng có thể liên hệ, nhưng **không đồng nhất**: một event có thể được xử lý/retry nhiều lần trong các traces khác nhau, và một trace có thể chứa nhiều events. Không thay unique business event ID bằng thread name hoặc trace ID.

## 10. EventProbe: quan sát có giới hạn, thread-safe

`src/main/java/com/example/events/EventProbe.java`:

```java
package com.example.events;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;

@Component
public class EventProbe {

    public record SyncCall(
            String stage,
            String threadName
    ) {
    }

    public record AsyncCompletion(
            String id,
            String threadName
    ) {
    }

    public record AsyncFailure(
            String id,
            String methodName,
            String exceptionType,
            String message,
            String threadName
    ) {
    }

    private final ConcurrentMap<String, List<SyncCall>>
            syncCalls = new ConcurrentHashMap<>();

    private final ConcurrentMap<String, CompletableFuture<AsyncCompletion>>
            successes = new ConcurrentHashMap<>();

    private final ConcurrentMap<String, CompletableFuture<AsyncFailure>>
            failures = new ConcurrentHashMap<>();

    public void markSync(String id, String stage) {
        syncCalls.computeIfAbsent(
                id,
                ignored -> new CopyOnWriteArrayList<>()
        ).add(new SyncCall(
                stage, Thread.currentThread().getName()));
    }

    public List<SyncCall> syncCalls(String id) {
        List<SyncCall> calls = syncCalls.get(id);
        return calls == null ? List.of() : List.copyOf(calls);
    }

    public CompletableFuture<AsyncCompletion> success(String id) {
        return successes.computeIfAbsent(
                id,
                ignored -> new CompletableFuture<>());
    }

    public CompletableFuture<AsyncFailure> failure(String id) {
        return failures.computeIfAbsent(
                id,
                ignored -> new CompletableFuture<>());
    }

    public void markAsyncSuccess(String id) {
        success(id).complete(
                new AsyncCompletion(
                        id, Thread.currentThread().getName()));
    }

    public void markAsyncFailure(
            String id, String method, Throwable exception) {

        failure(id).complete(
                new AsyncFailure(
                        id,
                        method,
                        exception.getClass().getSimpleName(),
                        exception.getMessage(),
                        Thread.currentThread().getName()));
    }
}
```

**Vì sao tách `success(id)` và `failure(id)`?** Test có thể đợi đúng outcome của event cụ thể. Listener thành công hoàn tất future success; khi listener ném exception thì async error handler hoàn tất future failure. Cả hai chứa correlation ID và thread name để kiểm tra đường đi.

`ConcurrentHashMap` và `CopyOnWriteArrayList` bảo vệ truy cập qua test thread và event worker. `CompletableFuture.complete(...)` có memory visibility thích hợp khi test thread gọi `get(...)`. Không cần `volatile boolean processed` hay `Thread.sleep`.

**Hạn chế:** đây là probe in-memory chỉ dành cho bài học, không phải job status store có persistence, retry hay giới hạn bộ nhớ. Các maps tăng theo số event IDs; một ứng dụng production phải quản lý lifecycle/eviction, telemetry và business state. Nếu code nghiệp vụ có DB transaction, việc `markAsyncSuccess` chạy **trước commit** sẽ không chứng minh commit; đặt tín hiệu ở điểm hợp đồng yêu cầu hoặc assert DB state riêng.

### Vì sao không xóa toàn bộ probe trong @BeforeEach?

Tests dùng ID mới từ `UUID.randomUUID()` nên không chia sẻ outcome. Xóa một map chung có thể va chạm với worker chưa hoàn tất từ test trước khi có test chạy song song. Trong project, mỗi test async đợi một completion/failure trước khi kết thúc. Nếu bật JUnit parallel execution hay chạy volume lớn, hãy isolate probe per test/class hoặc cleanup riêng theo ID có ownership.

## 11. Publish service thực

`src/main/java/com/example/events/EventCommandService.java`:

```java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class EventCommandService {

    private final ApplicationEventPublisher publisher;

    public EventCommandService(
            ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void publishSync(String id, boolean fail) {
        publisher.publishEvent(new SyncSignal(id, fail));
    }

    public void publishAsync(String id, boolean fail) {
        publisher.publishEvent(new AsyncSignal(id, fail));
    }
}
```

Service chỉ chịu trách nhiệm publish, không tự gọi listener hoặc biết thread pool. Trong ứng dụng thật, bạn có thể publish sau khi domain state thay đổi; nếu phát event khi transaction chưa commit và listener chạy đồng bộ, listener có thể quan sát uncommitted state qua cùng thread/transaction. Nếu yêu cầu chỉ chạy sau commit, dùng `@TransactionalEventListener` với test chuyên biệt (mục 24).

### Vì sao không mock service trong tests?

Test integration chính cần kiểm tra wiring `ApplicationEventPublisher → multicaster → @EventListener / @Async`. Nếu `EventCommandService` là Mockito mock, `publishEvent` thật không xảy ra và test không bảo vệ configuration. Giữ service và listeners thật; fake chỉ là probe quan sát, không có external side effect.

## 12. Listener đồng bộ thứ nhất: @Order(10), có nhánh lỗi

`src/main/java/com/example/events/FirstSyncListener.java`:

```java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
public class FirstSyncListener {

    private final EventProbe probe;

    public FirstSyncListener(EventProbe probe) {
        this.probe = probe;
    }

    @EventListener
    @Order(10)
    public void onSync(SyncSignal signal) {
        probe.markSync(signal.id(), "first");

        if (signal.fail()) {
            throw new IllegalStateException(
                    "sync rejected: " + signal.id());
        }
    }
}
```

Listener này ghi dấu vết trước khi ném lỗi để test thấy **đã được gọi nhưng xử lý thất bại**. Với `fail=false`, nó chạy xong bình thường.

### Exception ném từ listener sync

Một runtime exception như `IllegalStateException` thường được Spring `@EventListener` adapter truyền lại cho event multicaster. Mặc định `SimpleApplicationEventMulticaster` không có custom error handler và dispatch đồng bộ; exception sẽ trở về publisher. Nếu listener ném **checked exception**, adapter có thể wrap trong `UndeclaredThrowableException`; trong ví dụ dùng unchecked exception để tránh một lớp wrapping ngoài chủ đề.

**Không dựa vào exception message của framework** khi test có thể chạy qua nhiều versions. Ta assert message do chính code `FirstSyncListener` chủ động tạo, nên giá trị expected rõ ràng.

## 13. Listener đồng bộ thứ hai: @Order(20)

`src/main/java/com/example/events/SecondSyncListener.java`:

```java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
public class SecondSyncListener {

    private final EventProbe probe;

    public SecondSyncListener(EventProbe probe) {
        this.probe = probe;
    }

    @EventListener
    @Order(20)
    public void onSync(SyncSignal signal) {
        probe.markSync(signal.id(), "second");
    }
}
```

Bởi vì `@Order(10)` có precedence cao hơn `@Order(20)`, với sync dispatch mặc định ta mong thứ tự `first` → `second`. Khi first listener ném lỗi, Spring dừng xử lý danh sách listeners trong cùng lần dispatch (với no-suppress default). Bài test xác minh **second không chạy** trong failure scenario.

Nếu có `SimpleApplicationEventMulticaster.setErrorHandler(...)` được cấu hình để suppress, kết quả có thể khác. Điều này quan trọng vì việc chọn error policy ảnh hưởng đến side effects: một listener fail có nên cản notification/projection khác hay không?

## 14. Listener @Async: worker thread và exception

`src/main/java/com/example/events/AsyncSignalListener.java`:

```java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class AsyncSignalListener {

    private final EventProbe probe;

    public AsyncSignalListener(EventProbe probe) {
        this.probe = probe;
    }

    @Async("eventExecutor")
    @EventListener
    public void onAsync(AsyncSignal signal) {
        if (signal.fail()) {
            throw new IllegalStateException(
                    "async rejected: " + signal.id());
        }

        probe.markAsyncSuccess(signal.id());
    }
}
```

Những điểm cần lưu ý:

- `@Async("eventExecutor")` chỉ định **đúng bean executor**. Nếu bỏ qualifier, Spring chọn executor theo async infrastructure và bean names/config; test sẽ khó chứng minh thread của một pool cụ thể.
- `@EventListener` trên cùng method giúp Spring đăng ký listener theo event type `AsyncSignal`.
- Method trả `void`, nên lỗi không thể được trả về publisher như một `CompletableFuture` thông qua `publishEvent`.
- Nhánh success gọi `probe.markAsyncSuccess` đúng tại **điểm hoàn thành logic** của demo.
- Nhánh failure ném exception; custom `AsyncUncaughtExceptionHandler` sẽ record lỗi.
- Không thêm `try/catch` nuốt exception trong listener rồi tự khai xử lý thành công.

### Điều gì có thể làm @Async không thực thi bất đồng bộ?

- Quên `@EnableAsync`.
- Listener bị tạo thủ công bằng `new AsyncSignalListener(...)` ngoài Spring, không đi qua proxy.
- Method bị gọi trực tiếp từ cùng bean bằng `this.onAsync(...)`, bypass proxy-based advice.
- Executor được cấu hình chạy inline bằng `SyncTaskExecutor`.
- Async interceptor không được áp dụng vì thay đổi bean registration/proxy settings.
- Test chỉ gọi listener method trực tiếp, thay vì đi qua `ApplicationEventPublisher`.

Bài test xác minh worker thread name bắt đầu bằng prefix riêng `event-worker-` và khác publisher test thread. Test không dựa vào việc publish phải mất ít hơn vài milliseconds, vì CPU/CI scheduling không deterministic.

## 15. Cấu hình @EnableAsync và AsyncUncaughtExceptionHandler

`src/main/java/com/example/events/EventAsyncConfiguration.java`:

```java
package com.example.events;

import java.lang.reflect.Method;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class EventAsyncConfiguration implements AsyncConfigurer {

    private static final Logger log =
            LoggerFactory.getLogger(EventAsyncConfiguration.class);

    private final EventProbe probe;

    public EventAsyncConfiguration(EventProbe probe) {
        this.probe = probe;
    }

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("event-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);

        return executor;
    }

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {

        return (exception, method, args) -> {
            if (args.length == 1
                    && args[0] instanceof AsyncSignal signal) {

                probe.markAsyncFailure(
                        signal.id(),
                        method.getName(),
                        exception);

                log.warn(
                        "Async event listener {} failed for {}",
                        method.getName(),
                        signal.id(),
                        exception);
            } else {
                log.error(
                        "Unexpected async method failure: {}",
                        method.getName(),
                        exception);
            }
        };
    }
}
```

### Những điều config này bảo đảm

- `@EnableAsync` bật async method interception.
- `eventExecutor` là named `ThreadPoolTaskExecutor`, được Spring quản lý lifecycle; khi bean được initialize, executor khởi tạo worker pool theo nhu cầu.
- `setThreadNamePrefix("event-worker-")` giúp test kiểm tra worker execution mà không dựa vào tên thread của JUnit.
- `setCorePoolSize(2)`, `setMaxPoolSize(2)`, `setQueueCapacity(16)` đủ cho số events nhỏ trong lab; không phải cấu hình production throughput.
- Shutdown properties giúp context đóng trật tự hơn, không bảo đảm mọi external side effect transactional.
- `getAsyncUncaughtExceptionHandler()` xử lý lỗi **uncaught từ asynchronous method `void`**. Handler lấy original method/args để gắn lỗi với event ID.

### Hai caveats

**Caveat 1 — AsyncConfigurer được khởi tạo sớm.** Spring docs lưu ý `AsyncConfigurer` configuration class có thể được khởi tạo sớm trong ApplicationContext. Ở đây nó chỉ cần một `EventProbe` cực nhẹ không có proxies hay external connections. Trong production, tránh inject một graph phức tạp vào AsyncConfigurer khi nó có thể chưa được post-process đầy đủ; tách error sink đơn giản hoặc dùng lazy initialization thích hợp.

**Caveat 2 — log không thay thế failure policy.** Custom handler hiện ghi probe và log. Nó không retry, không gửi DLQ và không rollback lệnh publish trước đó. Nếu lỗi async cần phản hồi business, ứng dụng phải có một cơ chế durable failure handling, không chỉ một warning.

### Có nên khai báo getAsyncExecutor()?

Vì listener khai báo `@Async("eventExecutor")` nên nó tìm executor tên `eventExecutor` cụ thể; demo không cần override `AsyncConfigurer.getAsyncExecutor()` để chọn default. Nếu có các `@Async` methods khác không có qualifier, ứng dụng thật nên cấu hình default executor rõ thay vì vô tình dùng fallback. Test default executor là một bài khác với test named event listener này.

## 16. Bộ integration test: EventListenersTest.java

`src/test/java/com/example/events/EventListenersTest.java`:

```java
package com.example.events;

import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@RecordApplicationEvents
class EventListenersTest {

    @Autowired
    EventCommandService commands;

    @Autowired
    EventProbe probe;

    private String id(String prefix) {
        return prefix + "-" + UUID.randomUUID();
    }

    @Test
    void syncListenersRunInOrderOnPublisherThread() {
        String eventId = id("sync");
        String publisherThread =
                Thread.currentThread().getName();

        commands.publishSync(eventId, false);

        List<EventProbe.SyncCall> calls =
                probe.syncCalls(eventId);

        assertEquals(
                List.of("first", "second"),
                calls.stream()
                        .map(EventProbe.SyncCall::stage)
                        .toList());

        assertTrue(calls.stream().allMatch(call ->
                publisherThread.equals(call.threadName())));
    }

    @Test
    void syncExceptionPropagatesAndStopsLaterListener() {
        String eventId = id("sync-error");

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> commands.publishSync(eventId, true));

        assertEquals(
                "sync rejected: " + eventId,
                error.getMessage());

        assertEquals(
                List.of("first"),
                probe.syncCalls(eventId).stream()
                        .map(EventProbe.SyncCall::stage)
                        .toList());
    }

    @Test
    void twoSyncEventsKeepIndependentHistories() {
        String firstId = id("one");
        String secondId = id("two");

        commands.publishSync(firstId, false);
        commands.publishSync(secondId, false);

        assertEquals(2, probe.syncCalls(firstId).size());
        assertEquals(2, probe.syncCalls(secondId).size());
        assertTrue(probe.syncCalls("not-published").isEmpty());
    }

    @Test
    void asyncSuccessRunsOnNamedWorkerThread()
            throws Exception {

        String eventId = id("async-success");
        String publisherThread =
                Thread.currentThread().getName();

        CompletableFuture<EventProbe.AsyncCompletion>
                completion = probe.success(eventId);

        commands.publishAsync(eventId, false);

        EventProbe.AsyncCompletion observed =
                completion.get(5, TimeUnit.SECONDS);

        assertEquals(eventId, observed.id());
        assertTrue(observed.threadName()
                .startsWith("event-worker-"));
        assertNotEquals(publisherThread,
                observed.threadName());
    }

    @Test
    void asyncFailureDoesNotEscapePublishEvent()
            throws Exception {

        String eventId = id("async-error");
        CompletableFuture<EventProbe.AsyncFailure>
                failure = probe.failure(eventId);

        assertDoesNotThrow(() ->
                commands.publishAsync(eventId, true));

        EventProbe.AsyncFailure observed =
                failure.get(5, TimeUnit.SECONDS);

        assertEquals(eventId, observed.id());
        assertEquals(
                "IllegalStateException",
                observed.exceptionType());
    }

    @Test
    void asyncErrorHandlerRecordsMethodAndCause()
            throws Exception {

        String eventId = id("async-handler");
        CompletableFuture<EventProbe.AsyncFailure>
                failure = probe.failure(eventId);

        commands.publishAsync(eventId, true);

        EventProbe.AsyncFailure observed =
                failure.get(5, TimeUnit.SECONDS);

        assertEquals("onAsync", observed.methodName());
        assertEquals(
                "async rejected: " + eventId,
                observed.message());
        assertTrue(observed.threadName()
                .startsWith("event-worker-"));

        assertFalse(probe.success(eventId).isDone());
    }

    @Test
    void twoAsyncSignalsAreCorrelatedById()
            throws Exception {

        String firstId = id("async-A");
        String secondId = id("async-B");

        CompletableFuture<EventProbe.AsyncCompletion>
                first = probe.success(firstId);
        CompletableFuture<EventProbe.AsyncCompletion>
                second = probe.success(secondId);

        commands.publishAsync(firstId, false);
        commands.publishAsync(secondId, false);

        assertEquals(
                firstId,
                first.get(5, TimeUnit.SECONDS).id());
        assertEquals(
                secondId,
                second.get(5, TimeUnit.SECONDS).id());

        // Không assert completion order của hai tasks.
    }

    @Test
    void successfulAsyncEventHasNoFailureRecord()
            throws Exception {

        String eventId = id("async-no-failure");
        CompletableFuture<EventProbe.AsyncCompletion>
                success = probe.success(eventId);

        commands.publishAsync(eventId, false);

        assertEquals(
                eventId,
                success.get(5, TimeUnit.SECONDS).id());
        assertFalse(probe.failure(eventId).isDone());
    }

    @Test
    void publishedEventIsVisibleToApplicationEvents(
            ApplicationEvents events) {

        String eventId = id("recorded");

        commands.publishSync(eventId, false);

        long count = events.stream(SyncSignal.class)
                .filter(signal ->
                        eventId.equals(signal.id()))
                .count();

        assertEquals(1L, count);
        assertEquals(2, probe.syncCalls(eventId).size());
    }
}
```

**Có 9 phương thức `@Test`** trong `EventListenersTest`. Các event IDs ngẫu nhiên chỉ phục vụ cô lập test probe, không ảnh hưởng expected behavior. Test không khẳng định một số lượng mili-giây chính xác và không dùng thread sleeps.

### Những assertion quan trọng

**Sync success:** kiểm tra cả `List.of("first","second")` và tên thread của hai callbacks bằng tên publisher thread. Điều này bảo vệ default sync dispatch và `@Order`. Nếu ai đó đổi global multicaster sang async executor, test có thể phát hiện assumption thay đổi.

**Sync failure:** dùng `assertThrows` ở **publisher boundary** và assert chỉ có `first`; đây là fail-fast behavior của demo. Nếu một custom ErrorHandler suppress lỗi được thêm vào app, test phải thay để phản ánh policy mới, chứ không bỏ assertion ngẫu nhiên.

**Async success:** chờ bằng `CompletableFuture.get(5, SECONDS)`, assert worker prefix và khác publisher. Điều này phát hiện nhiều lỗi như quên `@EnableAsync` hoặc vô tình chạy sync.

**Async failure:** tạo future trước khi publish, để không bỏ lỡ kết quả; `assertDoesNotThrow(publishAsync(...))` kiểm tra exception trong listener không truyền trực tiếp về caller theo setup không saturated. Sau đó chờ failure future và assert class/method/message/thread. Nếu có executor rejection ở submission time, test khác phải bắt riêng; không kỳ vọng `assertDoesNotThrow` bất chấp mọi điều kiện tải.

**Nhiều events:** completion order không cố định nên assert theo correlation ID, không phải `first completed before second`. Một thread pool có hai workers có thể hoàn tất không theo publish order.

**ApplicationEvents:** `@RecordApplicationEvents` ghi nhận sự kiện test publish; `ApplicationEvents.stream(SyncSignal.class)` chứng minh **event đã được phát**, rồi probe xác minh listener xử lý. Với async, chỉ dựa vào event recorder không đủ để biết worker đã xong.

## 17. Test SimpleApplicationEventMulticaster và hai error policies

Spring có `SimpleApplicationEventMulticaster.setErrorHandler(...)`, xử lý exception từ listeners được multicast. Đây là **cơ chế khác** `AsyncUncaughtExceptionHandler` vốn phục vụ lỗi uncaught từ `@Async` void methods.

Tạo `src/test/java/com/example/events/MulticasterPolicyTest.java`:

```java
package com.example.events;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MulticasterPolicyTest {

    static final class ProbeEvent extends ApplicationEvent {
        ProbeEvent(Object source) {
            super(source);
        }
    }

    private SimpleApplicationEventMulticaster multicasterWithFailure() {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();

        multicaster.addApplicationListener(
                new ApplicationListener<ProbeEvent>() {
                    @Override
                    public void onApplicationEvent(ProbeEvent event) {
                        throw new IllegalStateException(
                                "multicaster listener failed");
                    }
                });

        return multicaster;
    }

    @Test
    void defaultMulticasterPropagatesListenerError() {
        SimpleApplicationEventMulticaster multicaster =
                multicasterWithFailure();

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> multicaster.multicastEvent(
                        new ProbeEvent(this)));

        assertEquals(
                "multicaster listener failed",
                error.getMessage());
    }

    @Test
    void customErrorHandlerCanRecordAndSuppressError() {
        SimpleApplicationEventMulticaster multicaster =
                multicasterWithFailure();
        AtomicReference<Throwable> observed =
                new AtomicReference<>();

        multicaster.setErrorHandler(observed::set);

        assertDoesNotThrow(() ->
                multicaster.multicastEvent(
                        new ProbeEvent(this)));

        Throwable error = observed.get();
        assertNotNull(error);
        assertInstanceOf(
                IllegalStateException.class, error);
        assertEquals(
                "multicaster listener failed",
                error.getMessage());
    }
}
```

**Có 2 phương thức `@Test`**. Tổng project là **11 test methods**: 9 integration event tests và 2 multicaster policy unit tests.

### Ý nghĩa của test multicaster trực tiếp

- Không có custom ErrorHandler → synchronous listener exception propagate ra `multicastEvent`.
- Gắn `setErrorHandler(observed::set)` → handler **ghi nhận và suppress** exception; lời gọi không ném.
- Test không tự thay đổi `ApplicationContext` production; nó chỉ chứng minh **cơ chế của SimpleApplicationEventMulticaster**.

Nếu thật sự muốn app dùng policy suppress, phải cấu hình **bean multicaster** tên mà Spring ApplicationContext nhận biết, và viết integration test bảo vệ behavior trong context đó. Thay đổi global multicaster là một quyết định kiến trúc cần review, không nên chỉnh chỉ để một test fail-fast chuyển xanh.

## 18. Ghi chú cho người muốn cấu hình global ErrorHandler

Trong Spring ApplicationContext, bean tên `applicationEventMulticaster` có ý nghĩa đặc biệt. Một cấu hình *minh họa*, **không thuộc project runnable chính**:

```java
@Configuration(proxyBeanMethods = false)
class MulticasterPolicyConfiguration {

    @Bean(name = "applicationEventMulticaster")
    ApplicationEventMulticaster applicationEventMulticaster() {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();

        multicaster.setErrorHandler(
                TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER);

        return multicaster;
    }
}
```

Cần imports `Configuration`, `Bean`, `ApplicationEventMulticaster`, `SimpleApplicationEventMulticaster` và `org.springframework.scheduling.support.TaskUtils`. Nếu đưa cấu hình này vào app, **sync failure policy sẽ khác project**: error có thể bị log/suppress và listener phía sau có thể tiếp tục, tùy dispatch/handler. Khi ấy phải sửa tests theo policy mong muốn chứ không cho hai configs mâu thuẫn tồn tại.

**Không thay EventAsyncConfiguration bằng đoạn trên** rồi kết luận AsyncUncaughtExceptionHandler đã được thử. Hai error hooks xử lý ở những lớp khác nhau:

- Global multicaster ErrorHandler bao quanh invocation/dispatch của listener (trên thread tương ứng).
- `AsyncUncaughtExceptionHandler` nhận lỗi từ **asynchronous void method** khi executor thực thi listener đó.

Khi listener có `@Async`, exception được xử lý bởi async interceptor sau khi dispatch đã trao task đi; global multicaster ErrorHandler có thể không thấy exception bên trong worker. Ngược lại, lỗi submit/rejection có thể xuất hiện ngay trên path dispatch.

## 19. Vì sao exception trong @Async không thể assertThrows trực tiếp?

Một test sai:

```java
assertThrows(IllegalStateException.class, () -> {
    publisher.publishEvent(new AsyncSignal("A", true));
});
```

Trong demo, listener dùng `@Async("eventExecutor")` và trả `void`. `publishEvent` thường chỉ lập lịch xử lý rồi quay về, vì vậy lỗi listener phát sinh trên worker thread, không được ném ngược vào lambda của `assertThrows`. Test trên có thể fail dù listener thực sự đã ném exception và error handler đã ghi nhận.

Test phù hợp:

```java
String id = "case-123";
CompletableFuture<EventProbe.AsyncFailure>
        observed = probe.failure(id);

publisher.publishEvent(new AsyncSignal(id, true));

EventProbe.AsyncFailure failure =
        observed.get(5, TimeUnit.SECONDS);

assertEquals("IllegalStateException",
        failure.exceptionType());
```

Đây là **snippet** cần `publisher`/`probe` đã inject vào class, imports `CompletableFuture`, `TimeUnit` và JUnit assertions. Nó không phải file standalone ngoài project. Timeout giúp phân biệt handler không chạy với test treo vô hạn.

**Cẩn thận lỗi submit:** nếu executor đã shutdown hoặc queue đầy, `publishEvent` có thể ném `TaskRejectedException` trước khi worker được chạy. Đó là nhánh lỗi khác; bài chính không chủ động gây saturation, vì test cần deterministic.

## 20. Thread pool exhaustion, backpressure và rejection

ThreadPoolTaskExecutor có nhiều settings cần hiểu:

| Setting | Ảnh hưởng |
| --- | --- |
| `corePoolSize` | Số threads lõi |
| `maxPoolSize` | Upper bound threads khi queue policy cần |
| `queueCapacity` | Nơi giữ tasks chờ worker |
| `threadNamePrefix` | Hỗ trợ chẩn đoán/logging |
| `RejectedExecutionHandler` | Policy khi không nhận task mới |
| Shutdown/await settings | Context stop và task completion |

Với cấu hình nhỏ trong demo (`core=2, max=2, queue=16`), nếu ứng dụng gửi hàng trăm events khi worker đang block, task submissions có thể bị từ chối. **Không coi @Async là durable queue**: một bounded executor không tự persist/retry task.

Một integration test riêng cho rejection có thể dùng executor cố ý nhỏ, một task chặn bằng `CountDownLatch`, bảo đảm worker/queue đã đầy bằng synchronization rồi submit thêm và assert `TaskRejectedException`. Sau đó release latch và đóng executor. Không dùng `Thread.sleep` để “đoán” pool đã full. Nếu áp dụng vào production, rejection policy phải quyết định fail caller, drop task, caller-runs hay backpressure theo SLA.

### Lỗi phổ biến với CallerRunsPolicy

Nếu một executor dùng `CallerRunsPolicy` để chạy task ngay trên publisher thread khi quá tải, `@Async` có thể có trường hợp logic xử lý **thực thi trong caller thread**. Khi đó assumption “@Async luôn chạy ở thread khác” không còn tuyệt đối. Bài demo dùng executor default rejection policy, không bật CallerRunsPolicy, và chỉ phát vài tasks.

## 21. @Order và nhiều listeners cùng event

`@Order` có nghĩa với thứ tự dispatch trong nhiều trường hợp, nhưng không phải transaction coordinator:

- Hai synchronous listeners dùng default multicaster → thứ tự invocation theo `@Order`.
- Listener thứ nhất throw unchecked exception, không custom ErrorHandler → thường dừng dispatch phía sau.
- Custom ErrorHandler suppress → những listeners sau có thể tiếp tục.
- Hai `@Async` listeners → invocation/submission có ordering, **completion** không bảo đảm.
- Mixed synchronous/async listeners → async listener có thể chưa hoàn tất trong khi sync listener sau đã chạy.
- Có custom multicast TaskExecutor → toàn bộ assumption thread/order phải được kiểm chứng lại.
- `@TransactionalEventListener` có transaction synchronization semantics riêng, xem mục 24.

Nếu có business dependency “phải tạo báo cáo trước khi gửi email”, không nên dựng hai độc lập async listeners rồi hy vọng `@Order` bảo đảm. Nên orchestration rõ ràng, transactional outbox hoặc một workflow có acknowledgment.

## 22. @RecordApplicationEvents dùng khi nào?

Spring TestContext hỗ trợ:

```java
@RecordApplicationEvents
@SpringBootTest
class PublishingTest {

    @Test
    void publishesOrderEvent(ApplicationEvents events) {
        // Gọi service publish...
        long count = events.stream(SyncSignal.class)
                .filter(e -> "ORDER-1".equals(e.id()))
                .count();
        assertEquals(1L, count);
    }
}
```

Đây là **snippet cấu trúc**; nó cần service/publisher và event tương ứng để thực sự publish "ORDER-1". Bộ project đã có một method hoàn chỉnh sử dụng `ApplicationEvents`. Annotation là `org.springframework.test.context.event.RecordApplicationEvents`, còn parameter là `org.springframework.test.context.event.ApplicationEvents`.

### Nó đo điều gì?

`ApplicationEvents` ghi lại events đã được công bố trong phạm vi một test, hữu ích khi muốn kiểm tra service có publish đúng event type/payload hay không. Nó không tự chứng minh:

- Listener đã hoàn tất.
- Async handler đã tiêu thụ message trên worker.
- Business DB transaction đã commit.
- Downstream Kafka message đã được ACK.
- Event được persist để replay.

Trong test event async, recorder và listener có thể có thread-local/context khác nhau. Vì vậy cách chắc chắn hơn để assert **xử lý** là bounded probe/business outcome. Không dùng `ApplicationEvents.stream(...).count()==1` làm bằng chứng một async callback đã chạy thành công.

### Nên mock publisher khi nào?

Nếu unit test service chỉ cần chứng minh `publisher.publishEvent(new MyEvent(...))` được gọi với đúng payload, mock `ApplicationEventPublisher` bằng Mockito có thể là lựa chọn nhanh. Nhưng không dùng mock publisher trong bài đang kiểm tra Spring `@EventListener` wiring, vì lúc ấy dispatch thật không xảy ra.

## 23. Exception contract và nhánh xử lý lỗi ở mức nghiệp vụ

Một thiết kế producer/consumer event tốt cần trả lời:

1. Nếu listener đồng bộ lỗi, **lệnh nghiệp vụ** có phải thất bại không?
2. Nếu nhiều listeners độc lập, listener A fail có nên ngăn listener B?
3. Nếu một async listener fail, ai chịu trách nhiệm retry/alert?
4. Có yêu cầu timeout, deduplication hoặc exactly-once side effects không?
5. Event được publish trước hay sau database commit?
6. Có thể mất event khi JVM shutdown/crash không?
7. Phải theo dõi event ID/tenant/trace ID bằng cách nào?
8. Những loại lỗi nào cần fail fast, loại nào retryable?

### Một số chính sách điển hình

| Use case | Chính sách có thể phù hợp | Test bắt buộc |
| --- | --- | --- |
| Domain validation đồng bộ trước commit | Fail fast | Lỗi propagate; không commit business data |
| Best-effort metrics/audit noncritical | Suppress sau khi record/alert | Publisher vẫn thành công, error signal tồn tại |
| Email notification async | Retry/outbox khi cần độ tin cậy | Failure recorded + retry/idempotency |
| Compliance audit bắt buộc | Transactional/outbox, không silent drop | Không cho nghiệp vụ “thành công” nếu audit không bảo đảm |
| Cache invalidation | Async và eventual consistency | Bounded wait state update, recovery on fail |
| Projection/event sourcing | Durable event store | Ordering/version/concurrency + replay tests |

**Không biến mọi exception thành log-only**. Một lỗi compliance hoặc data integrity không nên bị xử lý như best-effort performance metric. Chính sách phải dựa trên yêu cầu sản phẩm, rồi test bảo vệ kết quả.

## 24. @TransactionalEventListener: nhánh theo commit hoặc rollback

`@TransactionalEventListener` khác `@EventListener` thường. Nó đăng ký callback gắn với transaction phase:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    // Side effect chỉ sau successful transaction commit.
}
```

Đây là **snippet**, không thuộc runnable project vì project không có DataSource/transaction manager. Thực tế có bốn phases thường gặp:

| Phase | Khi nào chạy |
| --- | --- |
| `BEFORE_COMMIT` | Trước khi transaction commit |
| `AFTER_COMMIT` | Sau khi commit thành công (mặc định) |
| `AFTER_ROLLBACK` | Sau khi rollback |
| `AFTER_COMPLETION` | Sau khi transaction hoàn tất, bất kể commit/rollback |

Mặc định, nếu không có active transaction, transactional listener **không được gọi** khi `fallbackExecution=false`. Khi bật `fallbackExecution=true`, listener có thể được gọi ngay cả ngoài transaction; test phải xác định policy kỳ vọng, không dùng fallback để che một sai sót transactional boundary.

### Phép kiểm thử chuẩn cho AFTER_COMMIT

- Dùng test DB/transaction manager thật.
- Công bố event **bên trong transaction**.
- Trước commit: listener AFTER_COMMIT chưa chạy.
- Commit transaction: listener được gọi.
- Trong scenario rollback: listener AFTER_COMMIT không chạy, có thể có AFTER_ROLLBACK listener.
- Dùng `TransactionTemplate` hoặc chương trình điều khiển commit/rollback tường minh; không giả định `@Transactional` trên test method (vốn thường rollback cuối test) sẽ kích hoạt after-commit callback.
- Assert business side effect tại transaction boundary phù hợp.

Một snippet với `TransactionTemplate`:

```java
transactionTemplate.executeWithoutResult(status -> {
    publisher.publishEvent(
            new OrderPlaced("ORDER-100"));
});

// Sau khi template commit, kiểm tra AFTER_COMMIT outcome.
```

Đây là snippet cần `OrderPlaced` class và injected `transactionTemplate/publisher`, không runnable độc lập. Khi DB transaction rollback, `AFTER_COMMIT` không chạy theo cấu hình mặc định. **Không tạo một transaction giả rồi chỉ assert listener callback** nếu câu hỏi thực sự là commit behavior.

### Kết hợp @Async + @TransactionalEventListener

Có thể đưa `@Async` lên một transactional listener để xử lý **sau commit** ở worker, nhưng transaction context thread-bound của publisher không tự chuyển sang worker. Handler không nên dựa vào một JPA entity lười load ngoài session hoặc nghĩ mình còn ở transaction cũ. Với transaction-bound listeners và custom global multicaster executor, Spring 6.1 có semantics bảo vệ transaction synchronization đặc biệt, cần test theo đúng version. Khi cần reliability cao, outbox thường rõ ràng hơn một after-commit callback không durable.

## 25. Observability: logs, metrics, tracing và correlation

Tên nhóm có chữ **observability**, nên ngoài câu hỏi “listener có chạy không?” cần thiết kế cách quan sát trong production:

- **Structured logs**: event type, correlation/business ID, outcome, retry count, elapsed time, lỗi được phân loại. Không log payload PII/credentials.
- **Metrics**: event published, listener succeeded/failed, executor active/queued/rejected, processing duration, retry/dead-letter counts.
- **Distributed tracing**: span hoặc observation cho một xử lý nghiệp vụ cần theo dõi; liên kết producer/handler/HTTP/DB nếu có.
- **Audit state**: khi nghiệp vụ yêu cầu, record durable outcome thay vì chỉ một metric có thể bị mất.
- **Alerts**: tỷ lệ thất bại tăng, queue bão hòa, processing latency vượt SLO, worker shutdown chậm.

### Spring không tự tạo Observation cho mỗi @EventListener

Spring Framework observability docs chỉ ra rằng **application event publication/listener không mặc nhiên đóng vai trò một observation riêng**. Listener đồng bộ mặc định chạy cùng thread nên ThreadLocals/MDC có thể thấy cùng context với publisher. Khi dispatch chuyển sang executor/thread khác, MDC/tracing context **không tự được bảo đảm**.

Nếu dự án dùng Micrometer Context Propagation, có thể cân nhắc `ContextPropagatingTaskDecorator` (Spring Framework 6.1) trên TaskExecutor tương ứng và thêm dependency cần thiết; test đúng trace ID/log context trước và sau async boundary. TaskDecorator có overhead; không bật chỉ để thấy log đẹp mà chưa đánh giá hiệu năng và propagation policy.

**Trong project lab** chỉ assert thread ID và event ID, không giả vờ một Micrometer ObservationRegistry đã được cấu hình. Muốn test spans/metrics thật, thêm Actuator/Micrometer test setup và assert vào registry test hoặc observation handlers được cấu hình tường minh.

### Metrics không phải proof of business commit

Một counter `listener.success` tăng trước khi DB write commit có thể gây hiểu nhầm. Đặt metric ở điểm tương ứng với semantic, phân biệt `received`/`started`/`completed`/`committed`/`failed`. Test vừa đo metric vừa assert business state quan trọng nếu nó quyết định correctness.

## 26. Logging context xuyên @Async và security context

ThreadLocals, MDC (Mapped Diagnostic Context) và SecurityContext có lifecycle gắn với thread:

- Synchronous listener mặc định chạy trong caller thread, nên có thể thấy MDC và transaction thread-local hiện tại.
- `@Async` listener thực thi trên worker pool, **không mặc nhiên mang toàn bộ thread-local context**.
- Nếu cần SecurityContext propagation, dùng `DelegatingSecurityContextAsyncTaskExecutor` hoặc cơ chế tương đương của Spring Security với policy rõ.
- Nếu cần trace/MDC propagation, dùng Micrometer context-propagation TaskDecorator hoặc giải pháp logging/tracing được hỗ trợ đúng phiên bản.
- Không tự copy mutable thread-local object vào worker mà không cleanup; thread pool reuse có thể rò context giữa requests/users.
- Với reactive app, context thường nằm trong Reactor Context thay vì ThreadLocal; event listener test cần strategy khác.

Không viết unit test “truyền context thành công” chỉ bằng cách assert một thread name hoặc đưa trace ID vào record; đó là hai câu hỏi khác nhau. Event ID trong payload là **business correlation**, còn trace/MDC context propagation là infrastructure concern.

## 27. Event publication, asynchronous transaction và idempotency

Một event có thể được publish nhiều lần do:

- Caller retry command sau timeout.
- Transaction rollback rồi service publish lại.
- Event callback được đăng ký trùng.
- Một listener tự publish một event khác.
- Test/ApplicationContext tạo duplicate listener beans.
- Restart/replay từ external broker/outbox.

Vì application events bản thân không có event deduplication, idempotency cần được xây **tại side-effect boundary** nếu có khả năng phát lại. Với giao dịch tài chính, email/notification có thể dùng dedup key; với DB writes cần unique constraints hoặc processed-event ledger theo business policy.

### Kiểm thử duplicate events

Một test domain-level có thể publish cùng event ID hai lần rồi assert chỉ một side effect **nếu implementation có idempotency guard**. Project lab **không** có idempotency guard, nên không gắn expected “exactly once” vào các test hiện tại. Nếu muốn nâng cấp, thêm repository/store, xử lý race của cùng ID khi hai worker chạy đồng thời, rồi test uniqueness.

### Retry không tự xuất hiện nhờ @Async

`@Async` nghĩa là schedule method, không tự retry khi method throw. `AsyncUncaughtExceptionHandler` không phải retry orchestrator. Nếu cần retry, dùng Spring Retry/Resilience4j hoặc queue/outbox có retry policy, và test số attempts/backoff/idempotency. Đừng dùng repeated publish trong test rồi gọi đó là framework retry.

## 28. Các tình huống lỗi nên test ngoài project lab

| Tình huống | Điều cần chứng minh | Công cụ |
| --- | --- | --- |
| Listener sync ném runtime exception | Publisher nhận lỗi; later listener có/không chạy theo policy | `assertThrows` + trace stages |
| Listener async void throw | Handler nhận lỗi đúng ID/cause | CompletableFuture/latch có timeout |
| Executor reject | Caller nhận error phù hợp và không silent drop | Controlled saturation bằng latch |
| Context shutdown lúc còn pending tasks | Dọn resources/await policy | Test lifecycle + bounded shutdown |
| Handler tự catch và suppress lỗi | Metrics/error sink vẫn ghi nhận | Fake error sink + assertions |
| Async listener mất tracing MDC | Propagation config thực thi đúng | Test TaskDecorator/context |
| Transaction rollback | AFTER_COMMIT không chạy | Real transaction manager + TransactionTemplate |
| Transaction commit | AFTER_COMMIT chạy sau commit | Real DB transaction + observable result |
| DB write fail sau event “success” | Outcome đo đúng điểm commit | Repository state + transaction semantics |
| Duplicate event ID | Idempotency policy được áp dụng | Real DB constraint/dedup store |
| Listener @Order sai | Sync order thay đổi | Recording probe stages |
| Có hai @Async listeners | Không suy completion order | Correlation-aware outcome |
| Custom global ErrorHandler | Suppress/propagate theo policy | Multicaster policy test + context test |
| Publish event trong controller transaction | Exception status mapping/rollback đúng | MVC + transactional integration |
| Global multicaster executor + transactional listener | Transaction semantics không bị phá | Correct Spring version test + DB |

Bộ lab kiểm chứng những trục quan trọng nhất với 11 tests, không giả bộ cover tất cả topology/network/infrastructure combinations.

## 29. Các lỗi thường gặp và cách giải quyết

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra/giải pháp |
| --- | --- | --- |
| Listener không được gọi | Bean không được scan, event type khác, context khác | Kiểm tra package, `@Component`, `@EventListener` |
| Test sync không thấy exception | Custom global `ErrorHandler` suppress | Đọc multicaster configuration/policy |
| Async listener chạy trong test thread | Quên `@EnableAsync`, proxy bypass, executor inline | Named pool + thread prefix assertion |
| Test `assertThrows` cho async fail | Exception ném trên worker, không về caller | Error signal/handler có timeout |
| Test thỉnh thoảng timeout | Dùng sleep, thread pool bão hòa, deadlock | Bounded future + diagnostics |
| Test PASS nhưng handler chưa xử lý | Chỉ assert `publishEvent` return | Await outcome/side effect |
| `@RecordApplicationEvents` có event nhưng business không đổi | Recorder chỉ biết publish | Assert listener/business output |
| @Order đúng nhưng async completion đảo | Scheduler/threads không có global order | Assert theo correlation ID |
| Throwable bị log mà không retry | `AsyncUncaughtExceptionHandler` không là retry system | Thiết kế retry/outbox |
| Lỗi ở worker nhưng application vẫn 200 | Caller đã trả response trước khi async xử lý | Phù hợp semantics hay cần sync? |
| Executor shutdown làm reject | Context/test lifecycle không đồng bộ | Dùng managed executor, bounded shutdown |
| EventProbe có record cũ | Chia sẻ ID/probe qua tests | UUID/fixture isolation; cleanup theo ID |
| Transactional listener ngoài transaction không chạy | `fallbackExecution=false` | Test trong real transaction |
| AFTER_COMMIT listener không chạy trong test @Transactional rollback | Không commit | Dùng TransactionTemplate commit |
| Log MDC mất trong worker | ThreadLocal không propagate tự động | TaskDecorator/context propagation |
| Failed metric tăng nhưng không có error logs | Async handler swallow/log policy | Assert error sink và logging settings |
| Payload event lỗi serialization | POJO internal event không cần JSON serialization mặc định | Không nhầm với broker transport |
| Spring listener “xử lý hai lần” | Duplicate bean/listener registration | Kiểm tra context/components và events |
| @Async listener return event không được publish | Async @EventListener không hỗ trợ return-value event publication | Inject publisher và publish tường minh |
| Checked exception bị wrapped | Adapter không thể propagate checked directly | Assert đúng wrapper theo API |
| @Async nghe event nhưng không có executor | Default executor selection khác ý định | Dùng `@Async("eventExecutor")` |
| Test quá ràng buộc elapsed milliseconds | CI scheduling không deterministic | Assert thread/outcome, bounded timeout |

### Quy trình debug 8 bước

1. Xác nhận event record/class, publisher và listener nằm trong cùng Spring ApplicationContext.
2. Kiểm tra `@EventListener` method signature nhận đúng event type.
3. Xem app có custom `applicationEventMulticaster`, TaskExecutor hoặc ErrorHandler không.
4. Với async, xác nhận `@EnableAsync`, Spring-managed bean/proxy và `@Async("eventExecutor")`.
5. Kiểm tra listener có được gọi bằng event ID/log/tracing, không chỉ status response.
6. Tách failure xảy ra trên publisher thread, lúc submit task hay trong worker.
7. Với async, await completion/error signal có timeout và root cause đúng.
8. Với transaction/outbox/broker, assert commit/retry/durable state bằng integration test, không suy từ in-memory probe.

## 30. Chạy test và cách đọc kết quả đúng

Khi project có Gradle Wrapper đã được tạo:

```bash
./gradlew test --tests 'com.example.events.EventListenersTest'
./gradlew test --tests 'com.example.events.MulticasterPolicyTest'
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Khi máy đã có Gradle tương thích nhưng chưa có Wrapper:

```bash
gradle test
```

Các báo cáo JUnit/Gradle thường nằm ở:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

Mã ví dụ có **11 phương thức `@Test`**, gồm 9 integration tests và 2 standalone multicaster tests. Đây là **số lượng phương thức trong source**, không phải số PASS đã quan sát. Trong quá trình soạn bài chưa chạy Gradle; không tuyên bố bộ test pass thực tế.

### Không có một stdout cố định

Test không gọi `System.out.println`. Spring Boot/Gradle logs và worker thread IDs khác nhau giữa môi trường. Kết quả đáng tin là test report ghi số test successful/failed/skipped sau khi chạy thật và assertions không bị fail. Nếu timeout, report stack trace cần chỉ ra event ID và future đang chờ; không tăng sleep để chữa.

## 31. Bài tập thực hành

1. Chạy `syncListenersRunInOrderOnPublisherThread`, xác minh cả hai handlers ở caller thread.
2. Bỏ `@Order` khỏi listeners ở sandbox, tìm hiểu vì sao một assertion order có thể không ổn định.
3. Đổi `fail=true` và xem `assertThrows` ở publisher với synchronous listener.
4. Cấu hình global multicaster `setErrorHandler(TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER)` trong một test context **riêng**, so sánh policy với mặc định.
5. Bỏ `@EnableAsync` trong sandbox, dùng test thread-prefix để tìm regression.
6. Bỏ qualifier `"eventExecutor"` trên `@Async` và kiểm tra executor thực nào được chọn.
7. Thay `@Async` listener method bằng một invocation trực tiếp từ chính bean, phân tích self-invocation và proxy.
8. Gửi một event async thành công, chờ future, assert correlation ID/thread.
9. Gửi một event async thất bại, xác nhận `AsyncUncaughtExceptionHandler` ghi method/cause.
10. Thử dùng `assertThrows` ngay trên `publishAsync` và giải thích vì sao nó không bắt worker exception.
11. Cấu hình pool nhỏ, chặn tasks bằng latch, tạo rejection có kiểm soát và assert `TaskRejectedException`.
12. Thêm một async listener thứ hai, kiểm tra không suy từ `@Order` rằng completion order cố định.
13. Thêm một `@TransactionalEventListener(AFTER_COMMIT)` với H2 và `TransactionTemplate`, xác minh chỉ chạy sau commit.
14. Thử `fallbackExecution=true` và publish ngoài transaction, kiểm tra policy mới.
15. Test after-rollback event với transaction thực và quan sát đúng listener.
16. Bổ sung business DB state và tránh coi `EventProbe.markAsyncSuccess` là transaction commit.
17. Thêm `@RecordApplicationEvents` vào một test publisher, phân biệt record được phát với listener đã hoàn tất.
18. Dùng `ApplicationEvents.stream(...)` assert payload event có ID đúng nhưng không dùng nó làm async completion gate.
19. Thêm TaskDecorator/context propagation và test MDC/trace ID qua event-worker thread.
20. Thêm idempotency layer với unique event ID và chạy hai events trùng ID concurrently.
21. Thử shut down context/executor khi còn pending task để tìm failure behavior cần theo dõi.
22. Chạy từng test và cả suite, đọc JUnit reports thực tế thay vì dự đoán PASS.

## 32. Checklist QA trước khi merge

- [ ] Đã phân biệt synchronous `@EventListener`, `@Async @EventListener` và custom multicaster executor?
- [ ] Event publisher và listeners thật được Spring quản lý?
- [ ] `@EnableAsync` được bật cho methods muốn async?
- [ ] Named executor được chọn tường minh khi cần?
- [ ] Sync test kiểm tra callback, order và caller thread?
- [ ] Sync failure test assert exception ở publisher boundary?
- [ ] Có test later listener bị chặn/tiếp tục theo ErrorHandler policy?
- [ ] Async test chờ completion/error với timeout hữu hạn?
- [ ] Không dùng `Thread.sleep`/timing threshold làm readiness gate?
- [ ] Async failure test **không** đợi exception được ném trực tiếp bởi publishEvent?
- [ ] AsyncUncaughtExceptionHandler ghi nhận cause/method/event ID đúng?
- [ ] Có phân biệt task rejection và worker exception?
- [ ] Test không giả định global completion order của @Async listeners?
- [ ] Có test bao quát success và error branches của từng event type quan trọng?
- [ ] @RecordApplicationEvents chỉ được dùng để assert publication, không phải processing?
- [ ] Correlation ID không trùng giữa tests?
- [ ] Test probe không làm thay đổi business semantics hoặc che DB rollback?
- [ ] Nếu có TransactionalEventListener, đã test commit/rollback/no-transaction?
- [ ] Không áp dụng @Transactional test rollback rồi mong AFTER_COMMIT chạy?
- [ ] Nếu app có retries, test số attempts/idempotency/recovery policy riêng?
- [ ] Không dùng static mutable state/global System properties gây test pollution?
- [ ] Với global multicaster ErrorHandler, đã test suppress/propagate riêng?
- [ ] Micrometer observations/metrics được instrument thật nếu cần test, không giả định tự có?
- [ ] Trace/MDC/SecurityContext propagation giữa threads được kiểm tra nếu thuộc SLA?
- [ ] Logs/metrics/error probes không phát tán secrets/PII?
- [ ] Đã đối chiếu Spring Framework 6.1/Boot 3.3 APIs?
- [ ] Đã chạy Gradle/CI thật trước khi khẳng định tests PASS?

## 33. Tài liệu tham khảo chính thức

- [Spring Framework 6.1 — Application Events and Listeners](https://docs.spring.io/spring-framework/reference/6.1/core/beans/context-introduction.html): event publishing, `@EventListener`, synchronous listeners, `@Async` và ordering.
- [Spring Framework 6.1 — EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/EventListener.html): exceptions, async limitations, listener return values.
- [Spring Framework 6.1 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): default thread, `setTaskExecutor` và `setErrorHandler`.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableAsync`, `@Async`, `AsyncConfigurer` và executor options.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, transaction phases và fallbackExecution.
- [Spring Framework — Application Events Testing](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html): `@RecordApplicationEvents` và `ApplicationEvents`.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): Spring application events and observation semantics, context propagation.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): SpringBootTest, test lifecycle và dependency management.
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): pool settings và lifecycle.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): `@Test`, assertions và independent test methods.

## 34. Kết luận

**Kiểm thử event listener phải xác định chính xác nơi sự kiện được xử lý và nơi lỗi xuất hiện.** Với `@EventListener` đồng bộ mặc định, publisher và listener chạy cùng thread; `assertThrows` ở publisher có thể kiểm tra exception, `@Order`/probe có thể kiểm tra thứ tự và nhánh dừng. Với `@Async @EventListener`, xử lý diễn ra ở executor; hãy test bằng completion/error signal theo event ID và **timeout hữu hạn**, sử dụng `AsyncUncaughtExceptionHandler` cho lỗi từ asynchronous void methods, không tìm exception trong lời gọi publisher thông thường.

Đừng nhầm **AsyncUncaughtExceptionHandler** với global **ApplicationEventMulticaster ErrorHandler**, hoặc nhầm `@RecordApplicationEvents` (đã publish) với business processing completed. Nếu event gắn transaction, cần test `@TransactionalEventListener` theo commit/rollback thực. Nếu production cần tracing, MDC và durable error/retry handling, bổ sung context propagation, metrics và outbox/broker integration tests phù hợp. Bộ mã Java17+/Spring Boot3.3.5 cung cấp 11 phương thức test minh họa làm nền tảng, nhưng số PASS thực phải được xác nhận bằng Gradle/CI report chứ không được suy từ nội dung bài.
