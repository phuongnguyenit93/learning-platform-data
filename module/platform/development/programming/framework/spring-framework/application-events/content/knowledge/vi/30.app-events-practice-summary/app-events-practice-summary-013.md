# Bài tập tổng hợp theo use case — Spring Framework Application Events

## 1. Mục tiêu và phạm vi thực hành

Đây là bài **Thực hành và tổng kết** của module **Spring Framework Application Events**. Người học sẽ không chỉ viết một `@EventListener` để in log, mà triển khai một use case có transaction, event payload, nhiều loại listener, đường lỗi, tác vụ nền và kiểm thử tích hợp. Mục tiêu là có khả năng **chọn đúng cơ chế event theo yêu cầu nghiệp vụ** và tự chứng minh bằng test.

Sau khi làm bài, bạn cần giải thích và thực hiện được:

1. Tạo **event contract bất biến** bằng Java record và phát sự kiện bằng `ApplicationEventPublisher`.
2. Phân biệt event đã được publish với thay đổi dữ liệu đã **commit**.
3. Đăng ký `@EventListener` đồng bộ, lọc event bằng `condition` SpEL và xác minh payload.
4. Chọn `@TransactionalEventListener(AFTER_COMMIT)` thay vì listener thường khi side effect phải chờ DB commit.
5. Dùng `@Async` và `ThreadPoolTaskExecutor` có giới hạn để tách công việc hậu kỳ khỏi luồng nghiệp vụ.
6. Hiểu phạm vi transaction/thread context và vì sao worker cần transaction mới khi ghi dữ liệu.
7. Tạo test `@RecordApplicationEvents`, assertions cho commit/rollback/invalid data, và chờ async completion bằng `CountDownLatch` thay vì sleep.
8. Nhận biết lúc nào Application Events trong RAM **không đủ độ tin cậy**, cần outbox, retry, idempotency hoặc broker.

Bài sử dụng Java 17+, Spring Framework 6.2.12, Spring JDBC, H2, Gradle và JUnit Jupiter. Không cần Spring Boot, HTTP server hay cài Kafka/RabbitMQ để chạy phần cốt lõi. Phần nâng cao giới thiệu cách thiết kế cho hệ thống thật.

## 2. Use case: Checkout và những phản ứng sau khi phát event

Một ứng dụng bán hàng có dịch vụ Checkout. Khi nhận yêu cầu, nó phải validate đầu vào, tạo đơn trong DB, phát `OrderPlaced`, rồi các thành phần khác phản ứng phù hợp:

- **AuditProbe:** ghi nhận những event được publish vào danh sách trong RAM để quan sát luồng đồng bộ.
- **PremiumProbe:** chỉ quan sát những event có tổng giá trị đơn từ **10.000** trở lên qua điều kiện SpEL.
- **PostCommitHandler:** bắt đầu công việc hậu kỳ **chỉ sau commit thành công**, chạy trên executor.
- **PostJobWriter:** ghi kết quả vào bảng DB trong một transaction độc lập.
- **Spring Test recorder:** xác minh event thực sự được publish, kể cả khi transaction cuối cùng rollback.

`AuditProbe` và `PremiumProbe` ở lab là quan sát kỹ thuật, **không phải nguồn chân lý nghiệp vụ**. Nếu cần một audit bền vững, phải thiết kế DB audit và transaction phù hợp, không dùng list in-memory.

### 2.1. Luồng thành công

```text
CheckoutService.checkout("O-1", "tenant-a", 2, 15000, false)
    |
    +-- Validate
    +-- BEGIN T1
    +-- INSERT purchase_orders
    +-- ApplicationEventPublisher.publishEvent(OrderPlaced)
    |      |
    |      +-- @EventListener audit (đồng bộ)
    |      +-- @EventListener(condition=...) premium (đồng bộ)
    |      +-- @TransactionalEventListener(AFTER_COMMIT)
    |                         đăng ký callback với T1
    |
    +-- COMMIT T1 thành công
    |      |
    |      +-- after-commit callback
    |               |
    |               +-- @Async submit vào capstoneExecutor
    |
    +-- service có thể trả về
                           |
                           +-- worker đọc order đã commit
                           +-- PostJobWriter.REQUIRES_NEW
                           +-- INSERT/UPSERT processed_post_jobs
                           +-- hoàn tất
```

### 2.2. Luồng rollback

```text
CheckoutService.checkout("O-2", ..., true)
    |
    +-- BEGIN T2
    +-- INSERT O-2
    +-- publish OrderPlaced(O-2)
    |      |
    |      +-- listener đồng bộ đã chạy
    |      +-- after-commit đăng ký chờ
    |
    +-- throw IllegalStateException
    +-- ROLLBACK T2
           |
           +-- DB không có O-2
           +-- AFTER_COMMIT không được kích hoạt
```

Một lỗi dễ mắc là nghĩ **transaction rollback làm event như chưa từng publish**. Không đúng: `@EventListener` đồng bộ đã chạy trong lúc `publishEvent` được gọi. Chỉ các side effect tham gia transaction đó mới có thể rollback tương ứng. Một thay đổi RAM hoặc HTTP/email đã gửi không tự bị thu hồi.

### 2.3. Đường invalid

`orderId` và `tenantId` phải không null/blank, `quantity > 0`, `totalCents >= 0`. Service validate trước khi INSERT và publish, vì vậy đầu vào sai không tạo `OrderPlaced` và không làm listener nào chạy.

## 3. Các bài tập trước khi xem lời giải

Có thể triển khai từng bài rồi so sánh với lời giải mục 5.

### Bài 1 — Event contract và publisher

Tạo record:

```java
public record OrderPlaced(
        String eventId,
        String orderId,
        String tenantId,
        int quantity,
        int totalCents) {}
```

Dùng constructor injection cho `ApplicationEventPublisher` và `JdbcTemplate`. Đặt `@Transactional` trên public method `CheckoutService.checkout(...)`, validate trước DB và phát event **sau INSERT nhưng trước khi transaction kết thúc**.

**Tiêu chí nghiệm thu:** event có đúng ID/tenant/quantity/total, một invocation chỉ publish một event; input invalid không publish. Trong bài, `eventId = "evt-" + orderId` để test có dữ liệu cố định; production cần một chiến lược uniqueness phù hợp với lifecycle của event.

### Bài 2 — Listener đồng bộ và condition

Tạo một `@EventListener` nhận tất cả `OrderPlaced`; tạo thêm listener:

```java
@EventListener(condition = "#a0.totalCents() >= 10000")
public void premium(OrderPlaced event) {
    // Thực thi chỉ khi giá trị đơn >= 10000.
}
```

`#a0` tham chiếu argument đầu tiên của listener, không phụ thuộc tên tham số Java có được giữ bằng `-parameters` hay không. Listener cần là **bean do Spring quản lý**.

**Tiêu chí:** event 15.000 vào cả hai listeners; event 5.000 chỉ vào listener chung. Event của transaction rollback cũng có thể đi vào listener đồng bộ trước rollback.

### Bài 3 — Transaction phase

Thêm listener:

```java
@Async("capstoneExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void processAfterCommit(OrderPlaced event) {
    // Chỉ xử lý sau commit; method body chạy trên worker.
}
```

**Tiêu chí:** thành công -> hậu kỳ bắt đầu sau commit; rollback -> không được gọi; gọi publish ngoài transaction -> mặc định bị bỏ qua vì `fallbackExecution=false`. Không bật `fallbackExecution=true` chỉ để test xanh nếu nghiệp vụ đòi hỏi đã commit.

### Bài 4 — Async completion và DB writer

Dùng `CountDownLatch` giữ worker chưa xử lý để chứng minh checkout có thể trả về trước khi hậu kỳ hoàn tất. Thêm bean riêng với `@Transactional(propagation = REQUIRES_NEW)` để ghi DB từ worker.

**Tiêu chí:** khi worker bị giữ, bảng hậu kỳ chưa có row; sau khi release + await completion, có đúng một row; worker query được order đã commit và tên thread có prefix executor.

### Bài 5 — Kiểm thử đủ bốn đường

Dùng Spring Test `@RecordApplicationEvents` để kiểm tra event được publish, kết hợp JUnit và query DB:

| Test | Nội dung cần chứng minh |
| --- | --- |
| Commit thành công | Event đúng type/payload; listener sync/premium chạy; hậu kỳ hoàn tất sau release |
| Rollback sau publish | Recorder vẫn thấy event, sync đã chạy, DB rollback, hậu commit không chạy |
| Invalid input | Không event, không DB row, không listener |
| Valid nhưng dưới ngưỡng | Có event và hậu commit; premium listener không chạy |

**Quy tắc:** Test event được publish **khác** test transaction outcome và **khác** test listener async hoàn tất. Mỗi thứ cần một bằng chứng riêng.

### Bài 6 — Thiết kế độ tin cậy

Không nhất thiết viết code ở bài chính, nhưng phải giải thích được: executor đầy, `TaskRejectedException`, retry trùng event, process chết sau commit, transaction outbox và idempotency key. Đây là bài nâng cao về kiến trúc production.

## 4. Tạo project Gradle

Cấu trúc:

```text
spring-events-use-case-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/EventUseCaseLab.java
    └── test/java/demo/EventUseCaseLabTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-events-use-case-lab'
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

    testImplementation 'org.springframework:spring-test:6.2.12'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'demo.EventUseCaseLab'
}

test {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

Spring Framework `spring-jdbc` kéo theo `spring-tx` cần thiết; toàn bộ các Spring modules ghim cùng nhánh 6.2.12. H2 chỉ cần runtime vì Java code sử dụng `DataSource`/Spring JDBC, không import trực tiếp H2 classes. `spring-test` + JUnit Jupiter cho phép dùng TestContext Framework trong integration tests.

Dự án này không kèm Gradle Wrapper; yêu cầu máy có Gradle 8+ và JDK 17+. Trong project thật, có thể tạo wrapper và dùng `./gradlew` hoặc `gradlew.bat`.

## 5. Lời giải tham khảo Java 17+

### 5.1. `src/main/java/demo/EventUseCaseLab.java`

```java
package demo;

import java.util.List;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
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
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class EventUseCaseLab {

    // Snapshot giá trị tại thời điểm phát event.
    public record OrderPlaced(
            String eventId,
            String orderId,
            String tenantId,
            int quantity,
            int totalCents) {
    }

    // Test observer: chỉ dùng cho demo, không phải persistent state.
    public static class Probe {
        final CopyOnWriteArrayList<String> syncIds =
                new CopyOnWriteArrayList<>();
        final AtomicInteger premiumCalls = new AtomicInteger();
        final AtomicInteger asyncStarts = new AtomicInteger();
        final AtomicBoolean sawCommittedOrder =
                new AtomicBoolean(false);
        final AtomicReference<String> workerThread =
                new AtomicReference<>("");
        final AtomicReference<Throwable> workerError =
                new AtomicReference<>();

        final CountDownLatch workerStarted = new CountDownLatch(1);
        final CountDownLatch releaseWorker = new CountDownLatch(1);
        final CountDownLatch workerFinished = new CountDownLatch(1);
    }

    public static class CheckoutService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public CheckoutService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void checkout(
                String orderId,
                String tenantId,
                int quantity,
                int totalCents,
                boolean rollback) {

            if (orderId == null || orderId.isBlank()
                    || tenantId == null || tenantId.isBlank()
                    || quantity <= 0 || totalCents < 0) {
                throw new IllegalArgumentException("invalid checkout");
            }

            jdbc.update(
                    "insert into purchase_orders "
                    + "(order_id, tenant_id, quantity, total_cents) "
                    + "values (?, ?, ?, ?)",
                    orderId, tenantId, quantity, totalCents);

            publisher.publishEvent(new OrderPlaced(
                    "evt-" + orderId,
                    orderId,
                    tenantId,
                    quantity,
                    totalCents));

            if (rollback) {
                throw new IllegalStateException("forced rollback");
            }
        }
    }

    public static class PostWorkWriter {
        private final JdbcTemplate jdbc;

        public PostWorkWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void save(OrderPlaced event) {
            // H2-specific UPSERT; event_id giúp chống trùng DB.
            jdbc.update(
                    "merge into processed_jobs "
                    + "(event_id, order_id) key(event_id) "
                    + "values (?, ?)",
                    event.eventId(), event.orderId());
        }
    }

    public static class Handlers {
        private final JdbcTemplate jdbc;
        private final PostWorkWriter writer;
        private final Probe probe;

        public Handlers(JdbcTemplate jdbc,
                        PostWorkWriter writer,
                        Probe probe) {
            this.jdbc = jdbc;
            this.writer = writer;
            this.probe = probe;
        }

        // Đồng bộ, được gọi ngay cả nếu transaction sau đó rollback.
        @EventListener
        public void audit(OrderPlaced event) {
            probe.syncIds.add(event.orderId());
        }

        @EventListener(condition = "#a0.totalCents() >= 10000")
        public void highValue(OrderPlaced event) {
            probe.premiumCalls.incrementAndGet();
        }

        @Async("capstoneExecutor")
        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderPlaced event) {
            probe.asyncStarts.incrementAndGet();
            probe.workerThread.set(Thread.currentThread().getName());
            probe.workerStarted.countDown();

            try {
                if (!probe.releaseWorker.await(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "worker release timed out");
                }

                Integer found = jdbc.queryForObject(
                        "select count(*) from purchase_orders "
                        + "where order_id = ?",
                        Integer.class, event.orderId());
                probe.sawCommittedOrder.set(
                        found != null && found == 1);

                writer.save(event);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                probe.workerError.compareAndSet(null, ex);
            } catch (RuntimeException ex) {
                probe.workerError.compareAndSet(null, ex);
            } finally {
                probe.workerFinished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    @EnableTransactionManagement
    public static class Config {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");

            // Mỗi Spring context có database riêng để cô lập tests.
            String name = "events_"
                    + UUID.randomUUID().toString().replace("-", "");
            ds.setUrl("jdbc:h2:mem:" + name
                    + ";DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean("capstoneExecutor")
        ThreadPoolTaskExecutor capstoneExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("capstone-");
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
        CheckoutService checkoutService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new CheckoutService(jdbc, publisher);
        }

        @Bean
        PostWorkWriter postWorkWriter(JdbcTemplate jdbc) {
            return new PostWorkWriter(jdbc);
        }

        @Bean
        Handlers handlers(
                JdbcTemplate jdbc, PostWorkWriter writer, Probe probe) {
            return new Handlers(jdbc, writer, probe);
        }
    }

    public static void createTables(JdbcTemplate jdbc) {
        jdbc.execute(
                "create table purchase_orders ("
                + "order_id varchar(50) primary key, "
                + "tenant_id varchar(50) not null, "
                + "quantity integer not null, "
                + "total_cents integer not null)");
        jdbc.execute(
                "create table processed_jobs ("
                + "event_id varchar(100) primary key, "
                + "order_id varchar(50) not null)");
    }

    public static int orders(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "select count(*) from purchase_orders",
                Integer.class);
    }

    public static int completedJobs(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "select count(*) from processed_jobs",
                Integer.class);
    }

    public static void main(String[] args)
            throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            CheckoutService checkout =
                    context.getBean(CheckoutService.class);
            Probe probe = context.getBean(Probe.class);
            createTables(jdbc);

            // A: transaction commit -> callback hậu commit submit worker.
            checkout.checkout("O-1", "tenant-a", 2, 15000, false);
            try {
                if (!probe.workerStarted.await(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "async worker did not start");
                }

                // B: đã publish, nhưng transaction rollback.
                boolean rollbackCaught = false;
                try {
                    checkout.checkout(
                            "O-2", "tenant-a", 1, 20000, true);
                } catch (IllegalStateException ex) {
                    rollbackCaught = "forced rollback".equals(
                            ex.getMessage());
                }

                // C: validate fail trước INSERT và publish.
                boolean invalidCaught = false;
                try {
                    checkout.checkout(
                            "O-3", "tenant-a", 0, 5000, false);
                } catch (IllegalArgumentException ex) {
                    invalidCaught = "invalid checkout".equals(
                            ex.getMessage());
                }

                System.out.println(
                        "sync event ids=" + List.copyOf(probe.syncIds));
                System.out.println(
                        "premium count=" + probe.premiumCalls.get());
                System.out.println(
                        "orders committed=" + orders(jdbc));
                System.out.println(
                        "rollback caught=" + rollbackCaught);
                System.out.println(
                        "invalid caught=" + invalidCaught);
                System.out.println(
                        "async starts=" + probe.asyncStarts.get());
                System.out.println(
                        "jobs before release=" + completedJobs(jdbc));
            } finally {
                // Không giữ worker khi phần main gặp lỗi.
                probe.releaseWorker.countDown();
            }

            if (!probe.workerFinished.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "async worker did not finish");
            }
            if (probe.workerError.get() != null) {
                throw new IllegalStateException(
                        "async worker failed", probe.workerError.get());
            }

            System.out.println(
                    "jobs after release=" + completedJobs(jdbc));
            System.out.println(
                    "worker saw committed order="
                    + probe.sawCommittedOrder.get());
            System.out.println(
                    "worker used executor="
                    + probe.workerThread.get().startsWith("capstone-"));
        }
    }
}
```

### 5.2. Chạy và xem kết quả

Tại thư mục chứa `build.gradle`:

```bash
gradle -q run
```

Các dòng do chương trình chủ động in:

```text
sync event ids=[O-1, O-2]
premium count=2
orders committed=1
rollback caught=true
invalid caught=true
async starts=1
jobs before release=0
jobs after release=1
worker saw committed order=true
worker used executor=true
```

Đây là **10 dòng output mong đợi** của logic demo. Gradle/Spring có thể in thêm log riêng tùy môi trường; không dựa vào toàn bộ stdout tuyệt đối để kết luận.

### 5.3. Phân tích lần A — commit thành công

1. `CheckoutService` là bean do Spring quản lý. Caller lấy bean từ context và gọi public `checkout(...)` qua transaction proxy.
2. T1 bắt đầu, INSERT O-1 vào bảng `purchase_orders`.
3. `publishEvent(new OrderPlaced(...))` được gọi trong T1; với multicaster mặc định, `@EventListener` audit và high-value chạy ngay trên thread publisher.
4. High-value listener match vì `totalCents=15000 >= 10000`.
5. Transactional listener chưa làm hậu kỳ ngay; nó đăng ký callback để chờ T1 commit.
6. Khi T1 commit, callback `AFTER_COMMIT` kích hoạt lời gọi `@Async`, submit method vào `capstoneExecutor`.
7. Worker đặt tên thread, tăng counter, mở `workerStarted`, rồi bị giữ bởi `releaseWorker`. Tại thời điểm này bảng hậu kỳ vẫn có **0 rows**.
8. Sau khi main release, worker query thấy O-1 đã commit, gọi bean riêng `PostWorkWriter.save(event)`. Transaction mới mở, dùng H2 `MERGE` theo `event_id` và commit một row.
9. Main chỉ in kết quả cuối sau khi `workerFinished` được mở; tránh race trong assertion.

### 5.4. Phân tích lần B — publish trước rollback

1. T2 INSERT O-2 và publish `OrderPlaced` có `totalCents=20000`.
2. Listener audit thêm O-2 và high-value tăng counter ngay trong T2.
3. Service cố ý ném unchecked exception. Transaction interceptor rollback T2.
4. DB không còn O-2; `AFTER_COMMIT` của event B không chạy.
5. Danh sách audit trong RAM vẫn là `[O-1, O-2]`, **không** có nghĩa DB đã commit hai order.

Nếu listener đồng bộ đã cập nhật **cùng DB transaction T2** thay vì list RAM, update đó có thể rollback cùng T2. Những side effect ngoài DB hoặc cập nhật RAM không tự rollback.

### 5.5. Phân tích lần C — invalid input

Quantity bằng 0 nên service ném `IllegalArgumentException` trước INSERT và publish. Không có record cho O-3, không thêm event đồng bộ, không tạo task hậu kỳ.

**Lưu ý dữ liệu tenant:** Lab chỉ validate `tenantId` không trống để tập trung vào event mechanics. Ứng dụng thật phải lấy tenant identity từ nguồn đã xác thực và kiểm tra quyền; không tin raw header hay tham số client gửi.

## 6. Lời giải JUnit 5 với Spring Test

### 6.1. `src/test/java/demo/EventUseCaseLabTest.java`

```java
package demo;

import java.util.List;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(EventUseCaseLab.Config.class)
@RecordApplicationEvents
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class EventUseCaseLabTest {

    @Autowired
    EventUseCaseLab.CheckoutService checkout;

    @Autowired
    EventUseCaseLab.Probe probe;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void createSchema() {
        EventUseCaseLab.createTables(jdbc);
    }

    @Test
    void commitPublishesCorrectPayloadAndCompletesPostJob(
            ApplicationEvents events) throws InterruptedException {
        try {
            checkout.checkout(
                    "T-1", "tenant-test", 1, 12000, false);

            assertTrue(probe.workerStarted.await(30, TimeUnit.SECONDS));
            assertEquals(List.of(
                    new EventUseCaseLab.OrderPlaced(
                            "evt-T-1", "T-1", "tenant-test", 1, 12000)),
                    events.stream(EventUseCaseLab.OrderPlaced.class)
                            .toList());

            assertEquals(List.of("T-1"),
                    List.copyOf(probe.syncIds));
            assertEquals(1, probe.premiumCalls.get());
            assertEquals(1, EventUseCaseLab.orders(jdbc));
            assertEquals(0, EventUseCaseLab.completedJobs(jdbc));
        } finally {
            probe.releaseWorker.countDown();
        }

        assertTrue(probe.workerFinished.await(30, TimeUnit.SECONDS));
        assertNull(probe.workerError.get());
        assertTrue(probe.sawCommittedOrder.get());
        assertEquals(1, EventUseCaseLab.completedJobs(jdbc));
    }

    @Test
    void rollbackStillPublishesButSkipsAfterCommit(
            ApplicationEvents events) {
        assertThrows(IllegalStateException.class, () ->
                checkout.checkout(
                        "T-2", "tenant-test", 1, 15000, true));

        assertEquals(1L,
                events.stream(EventUseCaseLab.OrderPlaced.class)
                        .count());
        assertEquals(List.of("T-2"),
                List.copyOf(probe.syncIds));
        assertEquals(1, probe.premiumCalls.get());
        assertEquals(0, EventUseCaseLab.orders(jdbc));
        assertEquals(0, EventUseCaseLab.completedJobs(jdbc));
        assertEquals(0, probe.asyncStarts.get());
        assertEquals(1L, probe.workerStarted.getCount());
    }

    @Test
    void invalidCheckoutPublishesNoEvent(
            ApplicationEvents events) {
        assertThrows(IllegalArgumentException.class, () ->
                checkout.checkout(
                        "T-3", "tenant-test", 0, 5000, false));

        assertEquals(0L,
                events.stream(EventUseCaseLab.OrderPlaced.class)
                        .count());
        assertTrue(probe.syncIds.isEmpty());
        assertEquals(0, probe.premiumCalls.get());
        assertEquals(0, EventUseCaseLab.orders(jdbc));
    }

    @Test
    void belowThresholdSkipsPremiumButRunsPostCommit(
            ApplicationEvents events) throws InterruptedException {
        try {
            checkout.checkout(
                    "T-4", "tenant-test", 1, 5000, false);

            assertTrue(probe.workerStarted.await(30, TimeUnit.SECONDS));
            assertEquals(1L,
                    events.stream(EventUseCaseLab.OrderPlaced.class)
                            .count());
            assertEquals(0, probe.premiumCalls.get());
            assertEquals(List.of("T-4"),
                    List.copyOf(probe.syncIds));
        } finally {
            probe.releaseWorker.countDown();
        }

        assertTrue(probe.workerFinished.await(30, TimeUnit.SECONDS));
        assertNull(probe.workerError.get());
        assertEquals(1, EventUseCaseLab.completedJobs(jdbc));
    }
}
```

### 6.2. Chạy test

```bash
gradle clean test
```

Nếu dự án đã có Gradle Wrapper:

```bash
./gradlew clean test
```

Trên Windows:

```bat
gradlew.bat clean test
```

**Kỳ vọng:** JUnit Jupiter phát hiện và chạy **4 test methods**, tất cả assertions thành công. Gradle tạo báo cáo HTML tại `build/reports/tests/test/index.html`. Thời gian, thứ tự test và số dòng log phụ thuộc môi trường; chính kết quả build/assertions mới là bằng chứng.

Đây là một **ví dụ nguồn và kết quả mong đợi**, không phải báo cáo đã chạy thực tế trong môi trường người học.

### 6.3. Ý nghĩa của bốn test

- **Commit:** kiểm tra payload đầy đủ bằng `record.equals`, số event, listener đồng bộ, premium condition, DB commit và worker completion.
- **Rollback:** recorder thấy event **đã publish** nhưng DB không có order, listener hậu commit chưa được kích hoạt; tránh sai lầm “có event nghĩa là đã commit”.
- **Invalid:** validate fail trước publish, không có event và không có side effect.
- **Below threshold:** một event hợp lệ có thể đi qua audit và hậu commit nhưng **không** đi qua high-value filter.

`@DirtiesContext(AFTER_EACH_TEST_METHOD)` giúp mỗi test có context, singleton `Probe` và database H2 mới. `ApplicationEvents` cũng được Spring Test quản lý theo phạm vi test method, không dùng làm singleton event store.

### 6.4. Vì sao không thêm `@Transactional` ở test method?

Spring Test thường rollback test-managed transaction theo mặc định khi một test có `@Transactional`. Khi đó `@TransactionalEventListener(AFTER_COMMIT)` có thể không chạy do transaction của test chưa commit hoặc cuối cùng rollback. Trong code này, test method **không** mở transaction ngoài; transaction nằm ở service và commit/rollback ngay trong lời gọi qua proxy.

Nếu cần test-managed transaction thật, dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` khi có transaction hợp lệ, sau đó vẫn phải chờ async completion với latch/future. Không dùng kết quả `@RecordApplicationEvents` để suy luận rằng callback đã hoàn tất.

## 7. Đọc lại cơ chế: event, transaction và thread

### 7.1. `publishEvent()` không phải durable queue

`ApplicationEventPublisher.publishEvent(...)` trả `void`. Trong context mặc định, các listener đồng bộ thường được gọi trên publisher thread. Nếu cấu hình multicaster executor hoặc method `@Async`, method body có thể tiếp tục ở thread khác.

Nó **không** tự:

- Persist message để replay qua restart.
- Cung cấp ACK cho tất cả async listeners.
- Chuyển transaction DB từ publisher thread sang worker thread.
- Đảm bảo email/HTTP side effect thành công.
- Retry khi executor bị đầy.
- Phân phối event cho một JVM/microservice khác.

Khi cần trao đổi giữa service, dùng broker/queue phù hợp; khi cần DB + việc phát message bền vững cùng commit, dùng outbox hoặc một cơ chế transaction được kiểm chứng.

### 7.2. `@TransactionalEventListener` không phải `@EventListener` đồng bộ bình thường

`@TransactionalEventListener(phase=AFTER_COMMIT)` gắn callback vào kết quả transaction. Nếu event được publish ngoài transaction, listener mặc định **không chạy** vì `fallbackExecution=false`. Nếu rollback, callback `AFTER_COMMIT` không chạy.

Trong khi đó `@EventListener` bình thường chạy khi publish, kể cả trong transaction có thể rollback. Không đổi `AFTER_COMMIT` thành `@EventListener` để “sửa” một test đang rollback mà chưa hiểu semantics.

### 7.3. `@Async` không tự làm việc sau commit

Một listener `@Async @EventListener` có thể bắt đầu **trước khi transaction commit**. Nếu cần giữ đúng dữ liệu đã commit, dùng `@TransactionalEventListener(AFTER_COMMIT)` hoặc outbox.

Exception trong `void @Async` method không tự truyền về caller; cấu hình `AsyncUncaughtExceptionHandler`, logging/metrics và failure/retry path. Trong demo, `Probe.workerError` chỉ là test observer, không thay thế durable error handling.

### 7.4. Return-as-event không dùng cho async listener

Spring cho phép một listener đồng bộ trả event khác để Spring publish tiếp trong những trường hợp được hỗ trợ. Nhưng **asynchronous event listeners không hỗ trợ phát event tiếp thông qua giá trị trả về**. Muốn có `PostJobDone`, phải inject `ApplicationEventPublisher` và gọi tường minh sau khi hoàn thành, hoặc ghi vào outbox nếu cần độ tin cậy.

### 7.5. `@Order` chỉ giải quyết thứ tự gọi trong phạm vi phù hợp

`@Order` có thể ảnh hưởng thứ tự dispatch của các listeners, nhưng không bảo đảm async task A **hoàn tất** trước async task B. Khi có dependency, dùng completion event, gọi service tuần tự hoặc workflow/state machine với trạng thái bền vững.

## 8. Bài nâng cao A — Thiết kế chuỗi Inventory rồi Payment

**Use case:** Một đơn chỉ được thanh toán sau khi giữ hàng thành công.

Phản ví dụ:

```java
@Async("capstoneExecutor")
@Order(0)
@EventListener
public void reserve(OrderPlaced e) {
    inventory.reserve(e.orderId());
}

@Order(10)
@EventListener
public void pay(OrderPlaced e) {
    payment.authorize(e.orderId());
}
```

Đây là **mã minh họa sai nếu payment phụ thuộc vào reservation**. `@Order` chỉ sắp thứ tự lời gọi/submit, không chờ công việc async hoàn tất.

Thiết kế hợp lý hơn:

```text
OrderPlaced
    |
    +-- ReserveInventory
          |
          +-- SUCCESS -> InventoryReserved(orderId, reservationId)
                           |
                           +-- PaymentService.authorize(...)
                                  |
                                  +-- SUCCESS -> PaymentAuthorized
                                  +-- FAILED  -> PaymentFailed
          |
          +-- FAILURE -> InventoryReservationFailed
```

**Acceptance test:** dùng latch giữ inventory worker, assert payment chưa chạy; sau khi reservation thành công mới publish `InventoryReserved`, payment mới có thể chạy. Khi reservation lỗi, không publish success event. Nếu toàn bộ workflow phải tồn tại qua crash, dùng persisted state/saga/outbox thay vì chỉ events trong RAM.

## 9. Bài nâng cao B — Từ async best-effort sang transactional outbox

**Use case:** Đơn đã commit phải được gửi hóa đơn, ngay cả khi JVM chết ngay sau commit.

`@Async @TransactionalEventListener(AFTER_COMMIT)` **không đủ guarantee**: process có thể crash trước callback/submit, executor có thể reject task hoặc job bị mất khi shutdown.

**Thiết kế transactional outbox:**

```text
BEGIN T1
  +-- INSERT purchase_orders
  +-- INSERT post_jobs(
          jobId, orderId, type=SEND_INVOICE,
          status=NEW, attempts=0
      )
COMMIT T1
    |
    +-- Worker poll/claim jobs theo batch + lease
           |
           +-- send invoice with stable idempotency key
           +-- success -> DONE
           +-- transient failure -> RETRY/backoff
           +-- permanent failure -> FAILED/alert/DLQ
```

Schema minh họa:

```sql
CREATE TABLE post_jobs (
    job_id VARCHAR(80) PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL,
    job_type VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempts INT NOT NULL,
    next_attempt_at TIMESTAMP,
    last_error VARCHAR(1000)
);
```

**Tiêu chí nghiệm thu:** transaction rollback không để lại order/job; commit làm cả hai tồn tại; worker có thể khôi phục pending sau restart; một message gửi lại không gây invoice/side effect trùng.

**Tại sao cần idempotency?** Nếu external API đã xử lý thành công nhưng worker crash trước khi mark DONE, retry sẽ gọi lại. Outbox giúp không mất **ý định gửi**, không tự bảo đảm exactly-once side effect. Consumer/remote API cần idempotency key và dedupe.

Trong phần giải thích nên dùng chính thuật ngữ **transactional outbox** và **idempotency** để phân biệt độ bền với tốc độ thực thi.

## 10. Bài nâng cao C — Executor capacity và backpressure

Một cấu hình có giới hạn:

```java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(4);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(100);
executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy());
```

Đây là mã minh họa; nếu tạo ngoài bean Spring-managed, cần initialize và shutdown executor đúng lifecycle. Các số 4/8/100 **không phải cấu hình tối ưu chung**.

**Câu hỏi:**

1. Core threads bận, task tiếp theo vào queue hay pool mở ngay tới max?
2. Khi queue đầy và max threads cũng đầy, event có được xử lý không?
3. Rejection xảy ra sau commit thì có thể rollback đơn đã commit không?
4. `CallerRunsPolicy` thay đổi latency hoặc transaction/thread context ra sao?
5. Khi `queueCapacity` không giới hạn, backlog có thể tăng tới mức nào?
6. Cần đo metric gì để biết business work thực sự hoàn tất?

**Đáp án hướng dẫn:** Với `ThreadPoolExecutor` thường, sau khi đạt core, task sẽ được queue trước; khi queue đầy mới tăng worker tới max. Khi cả max và queue đầy, `AbortPolicy` reject; Spring có thể ném `TaskRejectedException` ở submit path. Hậu commit đã xảy ra thì không thể rollback T1. `CallerRunsPolicy` có thể chạy task trên caller thread và kéo dài latency. Queue không giới hạn che giấu overload, có thể làm memory/latency tăng. Theo dõi published, submitted, accepted, completed, failed, rejected, queue wait và oldest pending age.

**Test:** giữ một số workers bằng latch, lấp đầy queue rồi assert rejection. Không dùng `Thread.sleep(50)` để đoán scheduler đã đưa task vào queue.

## 11. Bài nâng cao D — Bảo vệ tenant và dữ liệu nhạy cảm

Trong demo `tenantId` là một field minh họa. Ở sản phẩm thực:

- Lấy tenant/user identity từ authentication/authorization đã được kiểm chứng.
- Nếu dữ liệu đa tenant, query/update phải có tenant scope hoặc cơ chế kiểm tra phù hợp. Không dựa hoàn toàn vào `orderId` nếu không globally unique.
- Không chứa `HttpServletRequest`, `HttpSession`, cookie, bearer token, database connection hoặc JPA lazy entity trong event async.
- Không logging toàn bộ payload nếu có PII/secrets.
- Với collection nested trong Java record, cần defensive copy cả phần tử mutable khi cần snapshot bất biến sâu.
- Worker có thread riêng nên không tự kế thừa `RequestContextHolder`, security context, MDC/tracing hay imperative transaction.
- `TaskDecorator`/context propagation có thể giúp observability nhưng không kéo dài vòng đời request hoặc biến thread worker thành transaction thread gốc.

Bài test nâng cao: giả lập hai tenants có cùng local order ID và bảo đảm worker của tenant A không thể query/ghi dữ liệu tenant B.

## 12. Ma trận lựa chọn cơ chế

| Nhu cầu | Cơ chế | Cảnh báo |
| --- | --- | --- |
| Kiểm tra invariant bắt buộc trước commit | Service đồng bộ | Không dùng async event để quyết định hợp lệ |
| Notification nội bộ không critical | `@EventListener` hoặc `@Async` tùy độ trễ | Kiểm tra transaction/time |
| Chỉ xử lý sau khi DB commit | `@TransactionalEventListener(AFTER_COMMIT)` | Không tự bảo đảm job bền vững |
| Hậu commit không block thread nghiệp vụ | Thêm `@Async` và executor | Queue có thể reject/crash |
| Event cho process khác | Broker / external adapter | `ApplicationEventPublisher` chỉ trong context/JVM |
| Công việc không được mất | Outbox/job persistent + retry worker | Vẫn cần idempotency |
| B chỉ sau A thành công | Completion event/orchestrator | `@Order` không đảm bảo async completion |
| Test publisher type/payload | Mockito `ArgumentCaptor` hoặc Spring Test recorder | Mock không chứng minh actual dispatch |
| Test publish thật trong context | `@RecordApplicationEvents` | Recorder không chứng minh commit/completion |
| Test listener async hoàn tất | Latch/future + DB effect | Không dùng sleep |
| Event schema thay đổi | Versioning/compatibility tests | Không serialize nguyên entity |

## 13. Chẩn đoán những lỗi phổ biến

| Hiện tượng | Nguyên nhân có thể | Hướng khắc phục |
| --- | --- | --- |
| Listener không được gọi | Bean không trong context/scan, `@Lazy`, sai type | Kiểm tra bean registrations, tránh lazy listener |
| Listener synchronous nhận event của order rollback | Event publish trước rollback | Dùng AFTER_COMMIT cho side effect cần business fact đã commit |
| Listener premium không chạy | `condition` false hoặc sai SpEL | Kiểm tra totalCents và `#a0` |
| `@Async` không bất đồng bộ | Thiếu `@EnableAsync`, sai executor, self-invocation | Gọi qua Spring proxy; kiểm tra thread |
| Hậu commit không chạy | Publish ngoài transaction hoặc rollback | Kiểm tra active transaction và phase |
| Test annotation `@Transactional` làm hậu commit không chạy | Test rollback mặc định | Commit test bằng `TestTransaction` hoặc không bọc test transaction |
| Worker không thấy row vừa INSERT | Worker chạy trước commit | Dùng AFTER_COMMIT hoặc outbox |
| Worker không có request/security context | ThreadLocal không auto-propagate | Event chứa immutable validated snapshot |
| `REQUIRES_NEW` không tạo transaction mới | Gọi method cùng bean, bypass proxy | Gọi Spring bean writer riêng |
| `void @Async` lỗi nhưng caller nhận success | Exception ở worker | AsyncUncaughtExceptionHandler + failure state |
| App deploy làm pending job biến mất | Queue in-memory | Persistent outbox + recovery |
| Event bị xử lý trùng | Retry, broker redelivery, crash sau effect | Stable eventId, idempotent consumer |
| Test thỉnh thoảng fail | Race, assert trước worker completion | Latch/future với timeout |
| Dùng `@Order` nhưng hai async tasks chạy đảo | Ordering chỉ ở dispatch | Completion event/orchestration |
| Async queue đầy | Producer nhanh hơn consumer | Backpressure, bounded capacity, scale có đo |

## 14. Checklist tự đánh giá

- [ ] Event định nghĩa được bằng record bất biến với payload cần thiết?
- [ ] Service validate trước publish và chạy qua Spring transaction proxy?
- [ ] Listener đồng bộ có thể chạy trong T1 trước commit?
- [ ] Condition SpEL dùng đúng field và loại event?
- [ ] Test rollback chứng minh event đã publish nhưng DB không commit?
- [ ] `AFTER_COMMIT` chỉ kích hoạt khi transaction commit?
- [ ] `@Async` dùng đúng executor bean và có bounded queue?
- [ ] Worker có transaction riêng cho việc ghi DB?
- [ ] Test chỉ chờ async bằng latch/future có timeout?
- [ ] `@RecordApplicationEvents` kiểm tra payload chứ không chỉ số lượng?
- [ ] Không coi `publishEvent` là biên nhận giao hàng bền vững?
- [ ] Có phương án outbox nếu job không được mất qua crash?
- [ ] Có idempotency key nếu retry có thể gửi lại?
- [ ] Có metrics completed/rejected/failed và queue backlog?
- [ ] Payload không chứa request/session hoặc mutable entity gây lỗi cross-thread?
- [ ] Hiểu lúc nào nên dùng service trực tiếp thay vì event choreography?

## 15. Tổng kết

Một capstone về Application Events không chỉ yêu cầu tạo `OrderPlaced` và thấy listener chạy. Bạn cần chứng minh được **đúng loại/payload**, **đúng thời điểm**, **đúng transaction phase**, **đúng số lần xử lý** và **đúng cơ chế phục hồi** khi công việc quan trọng.

Trong lời giải:

- `@EventListener` đồng bộ nhìn thấy O-1 và O-2 vì cả hai event được publish, dù T2 sau đó rollback.
- `condition` chỉ cho high-value handler nhận event có `totalCents >= 10000`.
- `@TransactionalEventListener(AFTER_COMMIT)` không xử lý O-2 vì DB rollback.
- `@Async` thực thi hậu kỳ O-1 trên executor, nhưng caller có thể tiếp tục trước completion.
- `@RecordApplicationEvents` kiểm tra các event đã công bố; query DB và `CountDownLatch` xác minh commit và completion.
- **transactional outbox** + **idempotency** là bước tiếp theo nếu công việc không được mất qua JVM crash, broker outage hoặc executor rejection.

Từ đây, có thể áp dụng cùng phương pháp cho use cases gửi email, đồng bộ CRM, indexing, cập nhật cache, inventory reservation, phát message cho microservices hoặc audit; điểm chung là xác định chính xác **business contract và failure boundary** trước khi chọn annotation.

## 16. Tài liệu tham khảo

- [Spring Framework 6.2 — ApplicationContext Events và `@EventListener`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — `ThreadPoolTaskExecutor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2 — Testing Application Events](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html)
- [Spring Framework 6.2 — `@RecordApplicationEvents`](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-recordapplicationevents.html)
- [Spring Framework 6.2 — Transaction Propagation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)
