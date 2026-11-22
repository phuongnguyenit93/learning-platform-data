# Chọn event đồng bộ hay bất đồng bộ trong Spring Framework Application Events

## 1. Câu hỏi thực sự cần quyết định

Trong nhóm **Mẫu triển khai** của **Spring Framework Application Events**, việc chọn listener đồng bộ (synchronous) hay bất đồng bộ (asynchronous) không đơn thuần là đặt hoặc bỏ `@Async`. Quyết định đó làm thay đổi **thời điểm hoàn tất**, **thread thực thi**, **cách lỗi được truyền đi**, **ngữ cảnh transaction**, **thứ tự side effect** và **độ tin cậy khi quá tải**.

Giả sử một ứng dụng xử lý đơn hàng:

```text
POST /orders
   |
   +-- ValidateOrder
   +-- SaveOrder
   +-- SendEmail
   +-- RebuildSearchIndex
   +-- NotifyAnalytics
```

Không nên mặc định đưa tất cả bước trên vào cùng một kiểu listener. `ValidateOrder` là điều kiện trước khi nhận đơn; `SendEmail` có thể là tác vụ phụ sau commit; còn một yêu cầu tài chính phải bảo đảm eventual completion có thể cần **transactional outbox**, không chỉ `@Async`.

**Quy tắc quyết định ngắn:**

- **Cần kết quả/lỗi ngay để quyết định transaction hoặc response?** Ưu tiên xử lý **đồng bộ**, thường bằng **lời gọi service trực tiếp** nếu đây là invariant bắt buộc.
- **Được phép xử lý muộn, độc lập với luồng trả kết quả và có chính sách lỗi rõ ràng?** Cân nhắc `@Async @EventListener`.
- **Tác vụ chỉ hợp lệ sau khi dữ liệu được commit?** Dùng `@TransactionalEventListener(AFTER_COMMIT)`, thêm `@Async` nếu muốn thực thi ở thread nền.
- **Tác vụ bắt buộc không được mất khi JVM crash, executor đầy hoặc deploy?** Ghi **outbox/job bền vững** trong transaction, rồi cho worker xử lý theo capacity.

Bài này giải thích từng lựa chọn, có một ví dụ Java 17+ chạy được để so sánh listener đồng bộ, listener async và callback theo kết quả transaction.

## 2. Mặc định của Spring: đồng bộ

Theo cơ chế mặc định của Spring Framework, `ApplicationContext` dùng `SimpleApplicationEventMulticaster` xử lý listeners **đồng bộ trên thread đang publish event**.

```java
public record OrderChecked(String orderId) {}

@Component
public class AuditListener {

    @EventListener
    public void onChecked(OrderChecked event) {
        auditService.record(event.orderId());
    }
}
```

Đây là **mã minh họa**, cần `auditService`, các imports và một Spring-managed bean đã được đăng ký.

Khi caller gọi:

```java
publisher.publishEvent(new OrderChecked("O-42"));
```

với multicaster mặc định và listener thường:

1. Spring tìm các listener phù hợp event type.
2. Listener được gọi trên **chính thread của publisher**.
3. Caller phải chờ các listener đồng bộ hoàn thành trước khi `publishEvent(...)` trả về.
4. Nếu listener ném unchecked exception và không có error handler/cơ chế bắt lỗi khác, exception có thể lan về publisher.
5. Nếu publish xảy ra trong imperative transaction đang hoạt động, listener đồng bộ thường chạy trong **transaction context của publisher thread**.

**Đừng đồng nhất "đồng bộ" với "đã commit".** Listener thường có thể chạy **trước khi transaction commit**; nếu nó gọi API bên ngoài rồi transaction DB rollback, side effect bên ngoài không tự rollback cùng DB.

### Ưu điểm đồng bộ

- Luồng thực thi tuyến tính, dễ debug và test.
- Caller biết listener đã hoàn tất trước khi `publishEvent` trả về, theo cấu hình multicaster đồng bộ mặc định.
- Exception có thể được caller xử lý, chuyển thành lỗi nghiệp vụ hoặc khiến transaction rollback nếu transaction policy phù hợp.
- Trong một thread, thread-bound transaction, request context và logging context có thể đang khả dụng.
- Không có overhead submit task, queue executor hay chuyển thread cho các công việc rất nhỏ.

### Nhược điểm đồng bộ

- Tăng latency của caller và chiếm thread request/transaction lâu hơn.
- Nếu listener làm I/O chậm, downstream chậm có thể làm nghẽn cả nghiệp vụ chính.
- Một listener lỗi có thể ngăn các listener còn lại được gọi hoặc làm transaction rollback.
- Handler có side effect ngoài DB có thể đã chạy **trước khi commit**.
- Coupling thời gian thực thi cao: tác vụ phụ kéo dài thời gian xử lý đơn hàng dù người dùng không cần chờ.

## 3. Bất đồng bộ qua `@Async @EventListener`

Spring hỗ trợ `@Async` trên method listener:

```java
@Async("eventExecutor")
@EventListener
public void onOrderCreated(OrderCreated event) {
    searchIndexer.update(event.orderId());
}
```

Đây là **mã minh họa**, không phải chương trình độc lập. Cần `@EnableAsync`, một executor bean tên `eventExecutor` và listener thuộc Spring-managed bean được async proxy intercept.

Trong cơ chế này:

```text
Publisher thread
   |
   +-- publishEvent(OrderCreated)
         |
         +-- Spring tìm listener
         +-- async proxy submit task vào executor
   |
   +-- publishEvent có thể trả về
                         |
                         v
                   Executor worker
                         |
                         +-- onOrderCreated(...)
                         +-- hoàn tất hoặc gặp lỗi
```

Spring có thể thực thi công việc ở thread khác, nên publisher **không chờ method body async hoàn tất**. Không được xem `publishEvent()` trả về bình thường là bằng chứng search index/email đã được cập nhật.

### Ưu điểm async

- Trả luồng publisher sớm hơn khi tác vụ phụ có thể chạy độc lập.
- Có thể chọn executor riêng cho email, analytics hoặc indexing để cách ly độ trễ.
- Tăng concurrency hữu ích với workload I/O-bound khi CPU, DB, HTTP client và rate limit cho phép.
- Có thể đặt timeout, queue capacity, metrics, retry/error path riêng theo workload.

### Nhược điểm async

- Exception của `void @Async` method không tự propagate về caller; cần `AsyncUncaughtExceptionHandler`/logging/trạng thái lỗi.
- Thread worker **không tự kế thừa** transaction, request attributes, MDC, security context hoặc thread-local tùy ý.
- Thứ tự task hoàn tất có thể khác thứ tự được submit.
- Queue in-memory có thể đầy hoặc mất khi crash.
- Test dễ flaky nếu assert ngay sau publish mà không chờ completion.
- `@Async` không bảo đảm event được đưa vào executor nếu executor shutdown/reject task.

**Cẩn thận với `@Async` trước commit:** một event được publish trong transaction T1 có thể khiến worker đọc DB **trước khi T1 commit**, hoặc phát side effect dù T1 về sau rollback. Muốn tránh hiện tượng này, cần listener transaction-bound hoặc outbox.

## 4. Quy trình ra quyết định thực tế

Có thể dùng flow sau:

```text
Tác vụ mới phát sinh
    |
    +-- Có cần kết quả ngay để tiếp tục nghiệp vụ?
    |      |
    |      +-- CÓ -> đồng bộ (ưu tiên gọi service trực tiếp)
    |      |
    |      +-- KHÔNG
    |             |
    |             +-- Có cần DB commit thành công trước khi làm?
    |             |      |
    |             |      +-- CÓ -> AFTER_COMMIT
    |             |      |            |
    |             |      |            +-- Được mất khi crash?
    |             |      |                  +-- CÓ -> có thể @Async AFTER_COMMIT
    |             |      |                  +-- KHÔNG -> outbox/job durable
    |             |      |
    |             |      +-- KHÔNG -> có thể @Async @EventListener
    |             |
    |             +-- Có phụ thuộc giữa các bước?
    |                     +-- CÓ -> orchestration/completion event
    |                     +-- KHÔNG -> xử lý độc lập, giới hạn capacity
```

Câu “được mất khi crash?” phải hiểu trong **hợp đồng nghiệp vụ**, không phải xem mất task là mong muốn. Với best-effort telemetry có thể chấp nhận mất một phần theo chính sách rõ ràng; với gửi hóa đơn bắt buộc, thanh toán, chuyển trạng thái hoặc đồng bộ kế toán thì không.

| Tình huống | Lựa chọn thường hợp lý | Vì sao |
| --- | --- | --- |
| Validate đơn trước khi nhận | Lời gọi service đồng bộ | Caller cần biết pass/fail ngay |
| Tính tổng tiền trong cùng transaction | Service đồng bộ | Có thể cần rollback cùng nghiệp vụ |
| Cập nhật read model nội bộ rất nhanh | Listener đồng bộ hoặc service trực tiếp | Overhead async có thể không đáng |
| Phát telemetry best-effort | `@Async @EventListener` | Có thể tách khỏi request, nhưng vẫn cần bounded capacity |
| Gửi email sau khi đơn hàng commit | `@Async @TransactionalEventListener(AFTER_COMMIT)` | Không gửi thông báo cho đơn rollback |
| Gửi hóa đơn bắt buộc, phải recovery qua crash | Transactional outbox + worker | Executor trong RAM không đủ guarantee |
| Update cache sau khi DB commit | `AFTER_COMMIT` đồng bộ/async tùy latency và guarantee | Tránh cache chứa dữ liệu chưa commit |
| Xử lý ảnh/upload lâu | Persist file/job trước, background worker | Request-scoped multipart data không tồn tại vô hạn |
| Một chuỗi A rồi B bắt buộc | Service orchestration hoặc `ACompleted` event | `@Order` không bảo đảm async completion |
| Consumer ở service khác | Broker/durable messaging | `ApplicationEventPublisher` không phải bus liên JVM |

## 5. Khi nào không nên dùng event?

Event giúp decouple publisher khỏi các listeners, nhưng **không phải mọi lời gọi service đều nên đổi thành event**.

Ví dụ nghiệp vụ phải kiểm tra hạn mức trước khi tạo lệnh:

```java
public Receipt submit(Command command) {
    limitService.ensureAllowed(command); // Cần biết kết quả ngay.
    Receipt receipt = commandService.save(command);
    return receipt;
}
```

Đây là **mã minh họa**, các class/service thuộc ứng dụng. Nếu thay `ensureAllowed` bằng một `@Async @EventListener` rồi trả về receipt trước khi validation hoàn tất, bạn đã thay đổi hợp đồng nghiệp vụ và có thể chấp nhận lệnh không hợp lệ.

Dùng service trực tiếp khi:

- Caller cần kết quả để quyết định bước tiếp theo.
- Hai bước phải nằm trong cùng transaction hoặc cùng critical section.
- Có quan hệ phụ thuộc chặt và cần trả lỗi cụ thể.
- Không có nhiều consumers hay yêu cầu tách module thực sự.
- Bạn cần API có `Future`/`CompletableFuture` để caller chờ và kết hợp kết quả.

Event phù hợp khi đó là **thông báo một sự thật nghiệp vụ** và bên nhận không cần quyết định giao dịch chính có được tiếp tục hay không.

## 6. Mẫu lai: `@Async @TransactionalEventListener(AFTER_COMMIT)`

Khi tác vụ chỉ đúng **sau khi transaction commit**, dùng:

```java
@Transactional
public String createOrder(CreateOrder command) {
    String id = repository.insert(command);
    publisher.publishEvent(new OrderCreated(id));
    return id;
}
```

và listener:

```java
@Async("eventExecutor")
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderCreated event) {
    notificationService.send(event.orderId());
}
```

Đây là **các đoạn minh họa**, cần Spring-managed service/listener, transaction manager, `@EnableAsync`, executor và các dependency.

Diễn biến quan trọng:

```text
Thread publisher
  BEGIN T1
  INSERT Order
  publishEvent(OrderCreated)
       |
       +-- đăng ký callback transaction synchronization
  COMMIT T1
       |
       +-- callback AFTER_COMMIT
             |
             +-- submit vào executor
                   |
                   +--> worker xử lý sau commit
```

Điểm khác biệt:

- `@TransactionalEventListener` điều khiển **mốc transaction**, mặc định `AFTER_COMMIT`.
- `@Async` điều khiển **thread thực thi method body**.
- `@TransactionalEventListener` mặc định `fallbackExecution=false`: publish **ngoài transaction** sẽ **không gọi** listener đó.
- T1 rollback -> listener `AFTER_COMMIT` không chạy.
- T1 commit thành công rồi executor bị reject/crash -> T1 đã commit, không thể rollback để cứu hậu kỳ.
- Với imperative transaction, worker có thread riêng, nên không tự tiếp tục transaction cũ. Nếu ghi DB, hãy mở transaction phù hợp ở service bean riêng.

**Đừng coi `AFTER_COMMIT` là durable queue.** Callback được kích hoạt dựa trên completion của một transaction trong tiến trình; nó không tự lưu pending task qua crash.

## 7. Ví dụ chạy được Java 17+: đồng bộ, async và transaction phase

Ví dụ dùng **Java 17+**, **Spring Framework 6.2.12**, Spring JDBC, H2 in-memory và Gradle 8+. Không cần Spring Boot, HTTP server hoặc message broker.

Chương trình có ba luồng minh họa:

1. **Listener đồng bộ:** phát `CheckOrder`, xác nhận listener chạy xong trên publisher thread trước khi `publishEvent` trả về; nếu listener từ chối, exception tới caller.
2. **Listener bất đồng bộ:** phát `RebuildView`, worker bắt đầu rồi bị giữ bằng `CountDownLatch`; publisher tiếp tục trong khi side effect chưa hoàn tất.
3. **Transaction-bound listeners:** phát `OrderStored` trong một transaction commit và một transaction rollback; quan sát `AFTER_COMMIT` chỉ tăng cho commit, `AFTER_ROLLBACK` chỉ tăng cho rollback.

### 7.1. Cấu trúc

```text
spring-sync-or-async-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SyncAsyncChoiceDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-sync-or-async-demo'
```

`build.gradle`:

```groovy
plugins {
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
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.SyncAsyncChoiceDemo'
}
```

H2 và `DriverManagerDataSource` chỉ phù hợp demo ngắn; production nên dùng DB bền vững, connection pool và quan sát transaction/latency.

### 7.2. `src/main/java/demo/SyncAsyncChoiceDemo.java`

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class SyncAsyncChoiceDemo {

    public record CheckOrder(String id) {}
    public record RejectOrder(String reason) {}
    public record RebuildView(String id) {}
    public record OrderStored(String id) {}

    public static class Probe {
        final AtomicBoolean syncDone = new AtomicBoolean();
        final AtomicReference<String> syncThread =
                new AtomicReference<>("");
        final AtomicBoolean asyncDone = new AtomicBoolean();
        final AtomicReference<String> asyncThread =
                new AtomicReference<>("");
        final AtomicReference<Throwable> asyncError =
                new AtomicReference<>();

        final CountDownLatch asyncStarted = new CountDownLatch(1);
        final CountDownLatch releaseAsync = new CountDownLatch(1);
        final CountDownLatch asyncFinished = new CountDownLatch(1);

        final AtomicInteger afterCommit = new AtomicInteger();
        final AtomicInteger afterRollback = new AtomicInteger();
    }

    public static class DemoListeners {
        private final Probe probe;

        public DemoListeners(Probe probe) {
            this.probe = probe;
        }

        // Listener mặc định đồng bộ.
        @EventListener
        public void check(CheckOrder event) {
            probe.syncThread.set(Thread.currentThread().getName());
            probe.syncDone.set(true);
        }

        // Exception đồng bộ theo multicaster mặc định tới publisher.
        @EventListener
        public void reject(RejectOrder event) {
            throw new IllegalArgumentException("rejected");
        }

        // Listener async: method body chạy trên executor thread.
        @Async("eventExecutor")
        @EventListener
        public void rebuild(RebuildView event) {
            probe.asyncThread.set(Thread.currentThread().getName());
            probe.asyncStarted.countDown();

            try {
                if (!probe.releaseAsync.await(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "async release timed out");
                }

                // Mô phỏng hoàn tất read model/indexing.
                probe.asyncDone.set(true);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                probe.asyncError.compareAndSet(null, ex);
            } catch (RuntimeException ex) {
                probe.asyncError.compareAndSet(null, ex);
            } finally {
                probe.asyncFinished.countDown();
            }
        }

        // Cả hai listener phase này được gọi tại transaction completion.
        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void onCommitted(OrderStored event) {
            probe.afterCommit.incrementAndGet();
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_ROLLBACK)
        public void onRolledBack(OrderStored event) {
            probe.afterRollback.incrementAndGet();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:choice_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean("eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(4);
            executor.setQueueCapacity(20);
            executor.setThreadNamePrefix("event-");
            executor.setRejectedExecutionHandler(
                    new ThreadPoolExecutor.AbortPolicy());
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(30);
            return executor;
        }

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        DemoListeners demoListeners(Probe probe) {
            return new DemoListeners(probe);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            Probe probe = context.getBean(Probe.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransactionTemplate tx =
                    context.getBean(TransactionTemplate.class);
            String publisherThread = Thread.currentThread().getName();

            jdbc.execute(
                    "create table orders ("
                    + "order_id varchar(40) primary key)");

            // 1) Đồng bộ: listener hoàn tất ngay trong publishEvent.
            context.publishEvent(new CheckOrder("O-1"));
            System.out.println("sync completed on return="
                    + probe.syncDone.get());
            System.out.println("sync on publisher thread="
                    + publisherThread.equals(probe.syncThread.get()));

            // Exception từ listener đồng bộ đến caller.
            boolean propagated = false;
            try {
                context.publishEvent(new RejectOrder("bad"));
            } catch (IllegalArgumentException ex) {
                propagated = "rejected".equals(ex.getMessage());
            }
            System.out.println("sync exception propagated="
                    + propagated);

            // 2) Async: worker chờ latch, caller vẫn tiếp tục.
            try {
                context.publishEvent(new RebuildView("O-1"));

                if (!probe.asyncStarted.await(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "async listener did not start");
                }

                System.out.println("async completed before release="
                        + probe.asyncDone.get());
                System.out.println("async on publisher thread="
                        + publisherThread.equals(probe.asyncThread.get()));

                // 3) Transaction commit và rollback.
                tx.executeWithoutResult(status -> {
                    jdbc.update(
                            "insert into orders (order_id) values (?)",
                            "O-1");
                    context.publishEvent(new OrderStored("O-1"));
                });

                tx.executeWithoutResult(status -> {
                    jdbc.update(
                            "insert into orders (order_id) values (?)",
                            "O-2");
                    context.publishEvent(new OrderStored("O-2"));
                    status.setRollbackOnly();
                });

                Integer committedRows = jdbc.queryForObject(
                        "select count(*) from orders", Integer.class);

                System.out.println("orders committed=" + committedRows);
                System.out.println("AFTER_COMMIT callbacks="
                        + probe.afterCommit.get());
                System.out.println("AFTER_ROLLBACK callbacks="
                        + probe.afterRollback.get());
            } finally {
                // Nếu main lỗi vẫn giải phóng worker trước shutdown.
                probe.releaseAsync.countDown();
            }

            if (!probe.asyncFinished.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "async listener did not finish");
            }
            if (probe.asyncError.get() != null) {
                throw new IllegalStateException(
                        "async worker failed", probe.asyncError.get());
            }

            System.out.println("async completed after release="
                    + probe.asyncDone.get());
        }
    }
}
```

### 7.3. Cách chạy

Tại thư mục dự án có `build.gradle`:

```bash
gradle -q run
```

Các dòng do chính chương trình in trong cấu hình demo:

```text
sync completed on return=true
sync on publisher thread=true
sync exception propagated=true
async completed before release=false
async on publisher thread=false
orders committed=1
AFTER_COMMIT callbacks=1
AFTER_ROLLBACK callbacks=1
async completed after release=true
```

Gradle hoặc logging Spring có thể in thêm thông báo khác. Chín dòng trên là stdout do các `System.out.println` trong chương trình tạo, không phải cam kết console tuyệt đối chỉ có chín dòng.

### 7.4. Tại sao kết quả xác định?

**Listener đồng bộ:**

- Context phát `CheckOrder` record.
- Bean `DemoListeners` có method `@EventListener` phù hợp. Với multicaster mặc định, nó chạy trên publisher thread và đặt `syncDone=true`.
- `publishEvent` trả về **sau khi** handler đó chạy, nên hai dòng đầu in `true`.
- Phát `RejectOrder` làm listener đồng bộ ném `IllegalArgumentException`. Không cấu hình custom error handler, nên exception lan tới caller; dòng ba in `true`.

**Listener async:**

- `@EnableAsync` đăng ký async interceptor. `@Async("eventExecutor")` chuyển `rebuild` sang worker của `ThreadPoolTaskExecutor`.
- Worker ghi tên thread, mở `asyncStarted` rồi chờ `releaseAsync`.
- Main chờ `asyncStarted` báo worker đã thật sự chạy; `asyncDone` vẫn `false` bởi worker chưa được release.
- Tên worker có prefix `event-`, khác publisher thread. Vì vậy dòng “async on publisher thread” là `false`.
- Sau phần transaction, main mở `releaseAsync` trong `finally`. Worker đặt `asyncDone=true`, mở `asyncFinished`; main chờ latch trước khi in dòng cuối.

**Transaction phase:**

- `TransactionTemplate.executeWithoutResult(...)` tạo transaction JDBC thật qua `DataSourceTransactionManager`.
- Trong transaction thứ nhất, code INSERT O-1 và publish `OrderStored`. `AFTER_COMMIT` chờ T1 commit rồi tăng counter.
- Trong transaction thứ hai, code INSERT O-2 và publish `OrderStored`, nhưng `status.setRollbackOnly()` khiến T2 rollback. `AFTER_ROLLBACK` tăng counter, `AFTER_COMMIT` không tăng.
- DB chỉ có O-1 sau cả hai transaction nên `orders committed=1`.

**Giới hạn:** Chương trình cố ý dùng `Probe`/latches và không thực hiện HTTP side effect thật. Nó minh họa semantics thread, exception và transaction phase; **không chứng minh** độ bền của queue khi JVM chết hoặc throughput thực tế của executor dưới tải.

## 8. Hiểu rõ bốn kiểu “thành công”

Một trong những sai lầm phổ biến là dùng từ “xử lý xong” cho bốn mốc khác nhau:

```text
Business code phát event
   |
   +-- publishEvent(...) được gọi
         |
         +-- Listener task được executor nhận (accepted)
               |
               +-- Listener bắt đầu (started)
                     |
                     +-- Side effect hoàn tất (completed)
                           |
                           +-- Kết quả được ghi bền vững (committed/acked)
```

- `publishEvent(...)` trả `void`, không trả số listeners thành công.
- Với listener đồng bộ mặc định, `publishEvent` đợi handler đó hoàn tất; nhưng external side effect do handler tự enqueue có thể còn chưa xong.
- Với `@Async`, publisher không tự biết trạng thái cuối của handler.
- Executor accepted không đồng nghĩa task đã bắt đầu.
- Task hoàn tất không đồng nghĩa kết quả được commit nếu handler không quản lý transaction/ACK đúng.
- Một message broker ACK không chứng minh mọi consumer đã hoàn tất nghiệp vụ.

Khi người gọi **thực sự cần đợi kết quả**, dùng một API trả `CompletableFuture`/`Future` do service kiểm soát, hoặc job ID/status bền vững. Đừng cố lấy future từ `ApplicationEventPublisher.publishEvent(...)`, vì API trả `void`.

## 9. Exception và rollback: sự khác biệt quan trọng

| Khía cạnh | Listener đồng bộ mặc định | `@Async @EventListener` | `@Async @TransactionalEventListener(AFTER_COMMIT)` |
| --- | --- | --- | --- |
| Caller chờ method body? | Có | Không | Không chờ phần body sau khi submit |
| Exception method body tới caller? | Thường có nếu không bị bắt/error handler xử lý | Không tự propagate | Không tự propagate từ async worker |
| Có thể cùng transaction publisher? | Có nếu publish trên thread có transaction | Không tự kế thừa transaction | Chỉ chạy sau transaction commit; body ở worker |
| Có thể làm T1 rollback? | Có thể nếu exception lan trong T1 trước commit và rollback rules áp dụng | Thường không do chạy ở worker khác | Không, T1 đã commit |
| Có thể chạy trước commit? | Có | Có | Không, với event được đăng ký trong T1 |
| Lưu queue qua crash? | Không phải queue | Không | Không |
| Thread context/MDC | Thường là thread publisher | Không tự propagate | Không tự propagate |

### 9.1. Listener đồng bộ lỗi không bảo đảm rollback mọi thứ

Nếu `@EventListener` đồng bộ ném exception, transaction interceptor có thể rollback DB nếu exception thoát ra và rollback policy phù hợp. Nhưng:

- Nếu publisher bắt exception và nuốt, transaction có thể tiếp tục hoặc đã bị đánh dấu rollback-only bởi thành phần khác.
- Nếu listener đã gửi email/HTTP thành công trước khi lỗi, external side effect không tự rollback.
- Nếu multicast có custom `ErrorHandler`, exception handling có thể khác mặc định.
- Nếu listener chạy ngoài transaction, không có DB transaction nào để rollback.

**Với invariant quan trọng trước khi commit, lời gọi service đồng bộ tường minh thường dễ diễn đạt hơn dùng event.**

### 9.2. Lỗi của `void @Async` method

```java
@Async("eventExecutor")
@EventListener
public void onEmailRequested(EmailRequested event) {
    mailClient.send(event.messageId());
}
```

Đây là **mã minh họa**. Nếu `mailClient.send(...)` ném exception trong worker, caller của `publishEvent(...)` không nhận exception đó theo đường gọi thông thường.

Spring hỗ trợ `AsyncUncaughtExceptionHandler`:

```java
@Configuration
@EnableAsync
public class AsyncErrorConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (ex, method, args) -> {
            System.err.println("async method failed: "
                    + method.getName() + ": " + ex.getMessage());
        };
    }
}
```

Đây là mã minh họa, cần imports `AsyncConfigurer`, `AsyncUncaughtExceptionHandler` và các annotation. Ở production nên có structured logging, trace/event ID, metrics, retry state và alert; chỉ in `System.err` không đủ nếu job bắt buộc xử lý.

Một `@Async @EventListener` **không hỗ trợ auto-publish event tiếp theo bằng giá trị return của method**. Nếu worker cần phát `EmailSent`, hãy inject publisher và gọi `publishEvent(new EmailSent(...))` sau khi đã hoàn thành, hoặc ghi event kết quả vào outbox nếu cần độ bền.

## 10. `@Order` và thứ tự hoàn thành

Với listener đồng bộ trong cùng multicaster, có thể dùng `@Order` để ưu tiên thứ tự **gọi**:

```java
@Order(0)
@EventListener
public void before(OrderChanged event) {
    // Listener được ưu tiên trước.
}

@Order(10)
@EventListener
public void after(OrderChanged event) {
    // Listener được ưu tiên sau.
}
```

Đây là mã minh họa.

Nhưng nếu listener `@Order(0)` dùng `@Async`, thì dispatcher có thể **submit** công việc của nó rồi gọi listener `@Order(10)` **trước khi công việc async đã xong**. Đừng dùng `@Order` như cơ chế bảo đảm side effect B sau side effect A.

Nếu B chỉ được làm **sau khi A thành công**, có thể:

1. Gọi service A rồi service B trực tiếp theo thứ tự, nếu workflow cần tuyến tính.
2. Worker A phát **`ACompleted`** sau khi xử lý thành công; B lắng nghe event kết quả.
3. Dùng state machine/workflow engine và persistent state khi cần retry, compensation, nhiều tiền đề hoặc qua nhiều service.
4. Với transaction DB, publish event kết quả đúng trong transaction tương ứng và xử lý hậu commit theo contract.

Đừng dùng `Thread.sleep(...)`, một biến boolean static hay tăng số worker để “đảm bảo” thứ tự.

## 11. Thread context và payload: điều gì không được tự truyền sang worker?

Trong Spring MVC/security applications, nhiều ngữ cảnh gắn với thread:

- `RequestContextHolder` và request-scoped beans;
- `SecurityContextHolder` theo chiến lược mặc định;
- MDC/tracing context nếu không cấu hình propagation;
- imperative `PlatformTransactionManager` transaction resources;
- `EntityManager`/Hibernate persistence context theo transaction.

Một event xấu:

```java
public record OrderChanged(
        String orderId,
        HttpServletRequest request) {}
```

Đây là **phản ví dụ**, không phải khuyến nghị. `HttpServletRequest` là object thuộc vòng đời HTTP request và có thể mutable. Worker chạy sau response không nên giữ request, session, `MultipartFile` hoặc input stream.

Nên capture **immutable snapshot** từ dữ liệu đã validate và authorized:

```java
public record OrderChanged(
        String orderId,
        String eventId,
        String verifiedActorId,
        String verifiedTenantId) {}
```

DTO trên không phụ thuộc Servlet request. Nếu có collection, phải defensive copy và làm immutable cả nested elements khi cần. Không lấy raw tenant/user ID từ header không đáng tin mà dùng như quyền truy cập.

Nếu chỉ cần log/tracing context, có thể cân nhắc `TaskDecorator`/Micrometer Context Propagation, với cấu hình accessor và cleanup phù hợp. **Context propagation không làm request object bền vững hay biến transaction T1 thành transaction trên worker thread.**

## 12. `@Async` trên listener khác executor của multicaster

Có hai điểm cấu hình async độc lập:

### 12.1. `@Async` trên từng method

```java
@Async("mailExecutor")
@EventListener
public void sendMail(MailRequested event) {
    // Chỉ listener này được đưa vào mailExecutor.
}
```

Ưu điểm: cách ly executor theo workload, dễ kiểm soát capacity. Phải có `@EnableAsync` và Spring-managed bean proxy. Self-invocation `this.sendMail(...)` không qua async proxy mặc định.

### 12.2. Executor toàn context trên `SimpleApplicationEventMulticaster`

```java
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster applicationEventMulticaster(
        @Qualifier("eventExecutor") TaskExecutor executor) {

    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(executor);
    return multicaster;
}
```

Đây là **đoạn minh họa**, cần imports `ApplicationEventMulticaster`, `SimpleApplicationEventMulticaster`, `TaskExecutor`, `Qualifier`, `Bean`.

Cách này có thể ảnh hưởng **nhiều listeners** cùng lúc; không phải listener nào cũng được phép chạy async trên multicaster. Spring Framework có `ApplicationListener.supportsAsyncExecution()`, và các listener transaction-synchronized cần thread phù hợp để đăng ký synchronization.

**Không bật cả `@Async` và executor của multicaster cho cùng một listener mà không hiểu double scheduling.** Hai lớp enqueue có thể làm tăng latency, khiến đo queue phức tạp, phân tán lỗi/rejection và khó quản lý thread context.

Mặc định đồng bộ của Spring chính là một đặc điểm có chủ đích để tránh tự phát thay đổi semantics transaction/context khi ứng dụng chỉ cần events nội bộ.

## 13. Capacity và overload: async không phải throughput vô hạn

Một executor phải có giới hạn:

```java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(12);
executor.setQueueCapacity(200);
executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy());
```

Đây là đoạn minh họa, không phải thông số tối ưu cho mọi máy. Dùng `ThreadPoolTaskExecutor`; imports theo Spring/Java concurrency.

### 13.1. Hiểu core, max và queue

Với cơ chế `ThreadPoolExecutor` thông thường:

1. Khi số worker chưa đạt `corePoolSize`, executor có thể mở core worker.
2. Khi đủ core, executor thường **đưa task vào queue** trước.
3. Khi queue đầy, executor mới mở thêm worker tới `maxPoolSize`.
4. Khi cả max threads và queue đều đầy, rejection policy quyết định hành vi.

`ThreadPoolTaskExecutor` có queue capacity mặc định rất lớn/không giới hạn. Nếu không cấu hình queue hữu hạn, `maxPoolSize` có thể ít khi phát huy tác dụng; backlog/memory/queue wait tăng mà không thấy rejection rõ ràng.

### 13.2. Rejection không phải chuyện nhỏ

| Rejection policy | Hành vi khi đầy | Hệ quả |
| --- | --- | --- |
| `AbortPolicy` | Ném rejection exception | Caller/bridge phải xử lý; dễ quan sát overload |
| `CallerRunsPolicy` | Caller có thể tự chạy task khi chưa shutdown | Tạo backpressure nhưng làm tăng request latency/thay đổi thread semantics |
| `DiscardPolicy` | Bỏ task | Có thể mất tác vụ im lặng |
| `DiscardOldestPolicy` | Loại task cũ trong queue | Có thể phá yêu cầu ordering/độ tin cậy |

Với `ThreadPoolTaskExecutor`, rejection thường được phản ánh dưới dạng `TaskRejectedException` ở đường submit phù hợp. **Đặc biệt với AFTER_COMMIT:** khi task bị reject thì transaction gốc đã commit; không thể rollback đơn hàng chỉ vì gửi email chưa được chấp nhận.

### 13.3. Định cỡ dựa trên tải

Một ước lượng thô cho concurrency bận:

\[
C_{\text{busy}} \approx \lambda S
\]

trong đó \(\lambda\) là event đến/giây và \(S\) là service time trung bình tính bằng giây/event.

Ví dụ: 120 event/s, handler tốn trung bình 0,05 giây -> khoảng 6 worker bận **theo mô hình lý tưởng**. Nếu dùng đúng 6 worker và chạy gần 100% utilization, một burst sẽ nhanh chóng gây queue. Phải có headroom và đo p95/p99 latency, CPU, HTTP client/DB pool, rate limits; đừng chỉ cộng threads theo công thức rồi mặc định hệ thống đủ throughput.

Với CPU-bound jobs, tăng threads vượt tài nguyên CPU có thể chỉ tăng context switches. Với I/O-bound jobs, số threads hữu ích có thể cao hơn nhưng bị chặn bởi connection pool và downstream concurrency.

## 14. Độ tin cậy: khi nào async chưa đủ và cần outbox?

`@Async @TransactionalEventListener(AFTER_COMMIT)` là một mẫu đơn giản cho **best-effort post-processing**, nhưng vẫn có cửa sổ mất việc:

```text
T1 COMMIT
   |
   +-- JVM crash trước khi callback submit task
   |
   +-- executor queue đầy và reject
   |
   +-- task được accept nhưng JVM crash trước khi xử lý
   |
   +-- worker gọi external API thành công nhưng crash trước ghi DONE
```

Nếu tác vụ **bắt buộc được thực hiện**, hãy đưa ý định xử lý vào **DB cùng transaction với nghiệp vụ chính**:

```text
BEGIN T1
  +-- INSERT order
  +-- INSERT outbox(eventId, aggregateId, type, payload, status=NEW)
COMMIT T1
   |
   +-- worker relay đọc outbox theo batch/lease
         |
         +-- thực hiện tác vụ có idempotency key
         +-- success -> mark DONE
         +-- transient failure -> RETRY/backoff
         +-- permanent failure -> FAILED/DLQ/alert
```

Outbox row đã commit tồn tại qua restart. Nhưng relay có thể gửi lại khi crash sau side effect thành công trước khi mark DONE, nên cần consumer/operation **idempotent**. Outbox giúp bảo đảm **không mất ý định** khi transaction commit, không tự tạo exactly-once external side effect.

Các bảng `post_jobs`/outbox thực tế nên có `eventId/jobId`, `aggregateId`, `status`, `attempts`, `nextAttemptAt`, `lastError`, timestamps/lease fields và các unique indexes phù hợp. Không dùng `Thread.sleep(...)` trong executor worker để chờ retry dài; scheduler/persistent queue sẽ hiệu quả hơn.

Nếu công việc phải giao sang service khác, một broker như Kafka/RabbitMQ/JMS có thể phù hợp, nhưng **việc đồng bộ DB commit với gửi broker vẫn cần giải pháp riêng**, ví dụ outbox + relay.

## 15. Theo dõi: đo completion thay vì chỉ đo publish

Để chọn và duy trì giải pháp đúng, cần quan sát:

| Metric | Câu hỏi |
| --- | --- |
| Publish rate | Có bao nhiêu event được tạo? |
| Accepted/submitted rate | Bao nhiêu task được executor chấp nhận? |
| Active threads | Pool đang bận đến mức nào? |
| Queue depth/capacity | Backlog hiện tại và còn headroom không? |
| Queue wait p95/p99 | Event chờ bao lâu trước khi bắt đầu? |
| Handler latency p95/p99 | Xử lý thực tế mất bao lâu? |
| Completed/s | Bao nhiêu task hoàn tất thành công? |
| Rejected/s | Bao nhiêu task không được nhận vào pool? |
| Failure/retry count | Bao nhiêu task lỗi hoặc phải thử lại? |
| Oldest pending job age | Một job có bị kẹt quá lâu? |
| DB/HTTP downstream utilization | Nút cổ chai nằm ở executor hay dependency khác? |

**Một API trả 200 nhanh không chứng minh email/indexing đã thành công.** Nếu nghiệp vụ cần biết trạng thái, cung cấp job ID và trạng thái xử lý rõ ràng. Với best-effort, tối thiểu vẫn cần lỗi/queue metrics để tránh mất task âm thầm.

## 16. Kiểm thử lựa chọn sync/async đúng cách

### 16.1. Kiểm thử đồng bộ

- Mock `ApplicationEventPublisher` kiểm tra service phát đúng loại/payload/count.
- Với context thật, gọi `publishEvent` và assert handler đồng bộ đã cập nhật state khi lời gọi trả về.
- Phát event gây exception và xác minh caller nhận lỗi theo cấu hình mặc định.
- Nếu listener hoạt động trong transaction, test rollback để xác minh state DB đúng; không suy luận rollback từ sự xuất hiện/không xuất hiện log.

### 16.2. Kiểm thử bất đồng bộ

Không viết:

```java
publisher.publishEvent(new RebuildView("O-1"));
Thread.sleep(100);
assertTrue(indexUpdated);
```

Đây là **phản ví dụ**, vì độ trễ scheduler, CI load hoặc downstream khác nhau làm test không ổn định.

Dùng `CountDownLatch`, `CompletableFuture`, Awaitility hoặc test executor có kiểm soát:

1. Chặn worker ở một latch để chứng minh caller có thể tiếp tục.
2. Quan sát callback bắt đầu bằng một latch riêng.
3. Thả latch sau khi kiểm tra trạng thái trước completion.
4. Chờ completed latch và kiểm tra side effect cuối cùng.
5. Kiểm tra timeout/failure/rejection path.

Ví dụ mục 7 dùng ba latch `asyncStarted`, `releaseAsync`, `asyncFinished` để tránh đoán từ `Thread.sleep`.

### 16.3. Kiểm thử phase transaction

Spring Test hỗ trợ `@RecordApplicationEvents` cùng `ApplicationEvents.stream(EventType.class)` để xác minh event **đã được publish** trong context. Tuy nhiên recorder không chứng minh listener async hoàn tất hay transaction đã commit.

Với `@TransactionalEventListener`:

- Commit thật -> `AFTER_COMMIT` chạy đúng.
- Rollback -> `AFTER_COMMIT` không chạy, `AFTER_ROLLBACK` có thể chạy.
- Publish ngoài transaction -> listener mặc định bỏ qua nếu `fallbackExecution=false`.
- Spring Test method annotate `@Transactional` thường rollback khi test kết thúc. Nếu cần commit trong test, dùng `TestTransaction.flagForCommit(); TestTransaction.end();` trong một test-managed transaction hợp lệ.
- Sau khi commit, vẫn cần chờ async completion riêng; `TestTransaction.end()` không tự chờ worker.

### 16.4. Load test và crash test

Với production, test cả sustained load, burst, executor queue saturation, downstream timeout, retry storm, deploy/shutdown, JVM restart và duplicate. Nếu một job quan trọng chỉ có trong RAM, crash test sẽ bộc lộ lỗ hổng kiến trúc mà unit test không thể chữa bằng cách thay `@Order` hay tăng max threads.

## 17. Bảng chẩn đoán lỗi phổ biến

| Triệu chứng | Nguyên nhân đáng xem | Cách xử lý |
| --- | --- | --- |
| Request chậm khi publish event | Listener đồng bộ thực hiện I/O tốn thời gian | Chuyển tác vụ phụ sang async/outbox nếu nghiệp vụ cho phép |
| Event async chạy trên publisher thread | Chưa `@EnableAsync`, method bị self-invocation, proxy không áp dụng | Kiểm tra bean/proxy/executor và thread name |
| Worker đọc order nhưng DB chưa thấy record | Async listener chạy trước commit | Dùng `AFTER_COMMIT` hoặc outbox |
| Listener `AFTER_COMMIT` không chạy | Publish ngoài transaction hoặc T1 rollback | Kiểm tra transaction active lúc publish và phase |
| Email gửi dù DB rollback | Dùng `@Async @EventListener` không ràng buộc commit | Chuyển sang hậu commit nếu cần |
| Caller không nhận lỗi trong worker | `void @Async` exception nằm ở thread khác | `AsyncUncaughtExceptionHandler`, failure state/metrics |
| Tăng `maxPoolSize` nhưng queue vẫn tích tụ | Queue không giới hạn nên pool đứng gần core | Bounded queue và load-test sizing |
| Queue đầy, order đã lưu nhưng notification mất | Rejection xảy ra sau commit | Outbox/durable recovery path |
| Event có `@Order` nhưng side effect chạy đảo | Async completion khác invocation order | Dùng completion event/orchestration |
| Listener thiếu MDC/RequestContext | ThreadLocal không tự propagate | Payload bất biến và context propagation cho observability |
| Worker dùng entity JPA lazy gây lỗi | Persistence context không còn hoặc không cùng thread | Chụp DTO/ID, mở transaction riêng để query |
| App restart làm mất pending work | Task chỉ nằm trong executor memory | Durable job store/outbox |
| Test async lúc pass lúc fail | Assertion quá sớm hoặc `Thread.sleep` | Latch/future với timeout |
| Async handler trả event nhưng không thấy event mới | Async listener không hỗ trợ auto-publish bằng return value | Gọi `ApplicationEventPublisher` tường minh |

## 18. Checklist chọn sync hay async

- [ ] Caller có cần kết quả **trước khi trả response/commit** không?
- [ ] Tác vụ là invariant bắt buộc hay notification độc lập?
- [ ] Nếu đồng bộ, một listener chậm/lỗi có làm hỏng nghiệp vụ chính không?
- [ ] Nếu async, event có thể chạy **trước commit** không? Điều đó có an toàn không?
- [ ] Nếu cần hậu commit, event có được publish **trong transaction đúng** không?
- [ ] Event chứa immutable DTO/ID, không giữ request/session/JPA entity mutable?
- [ ] Có `@EnableAsync` và executor bean cụ thể, queue/rejection policy rõ ràng?
- [ ] Có error handling, retries, idempotency và trạng thái thành công/thất bại?
- [ ] Nếu không được mất task khi JVM crash, đã dùng durable outbox/queue chưa?
- [ ] Nếu có thứ tự/phụ thuộc, đã dùng completion event/orchestration thay vì chỉ `@Order`?
- [ ] Có metric queue wait, completed, failed, rejected và latency p95/p99?
- [ ] Test đã tách **publish**, **transaction commit** và **async completion** chưa?

**Kết luận:** Chọn **đồng bộ** khi caller phải biết kết quả/lỗi ngay và thời gian xử lý chấp nhận được; nếu đây là invariant bắt buộc, gọi service trực tiếp thường rõ ràng hơn event. Chọn **`@Async @EventListener`** cho tác vụ phụ có thể xử lý muộn và không phụ thuộc commit. Chọn **`@Async @TransactionalEventListener(AFTER_COMMIT)`** khi tác vụ chỉ hợp lệ sau DB commit. Nếu tác vụ không được mất qua crash, executor trong RAM không đủ: cần **transactional outbox/job bền vững**, retry/idempotency và quan sát trạng thái.

## Tài liệu tham khảo

- [Spring Framework 6.2 — ApplicationContext Events, synchronous mặc định, async listeners và `@Order`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — Task Execution and Scheduling, `@Async`](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — `SimpleApplicationEventMulticaster`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — `ThreadPoolTaskExecutor`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2 — Transaction Propagation and `REQUIRES_NEW`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework 6.2 — Testing Application Events](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html)
- [Java SE 17 — `ThreadPoolExecutor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
