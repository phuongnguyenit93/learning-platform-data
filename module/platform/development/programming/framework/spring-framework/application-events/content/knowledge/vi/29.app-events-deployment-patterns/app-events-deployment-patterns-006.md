# Chạy tác vụ hậu kỳ bất đồng bộ trong Spring Framework Application Events

## 1. Bài toán và mục tiêu thiết kế

Trong nhóm **Mẫu triển khai** của chủ đề **Spring Framework Application Events**, “tác vụ hậu kỳ” thường là công việc **không cần hoàn tất trước khi một thao tác nghiệp vụ chính trả kết quả**:

- Gửi email hoặc thông báo sau khi tạo đơn hàng.
- Cập nhật search index, cache hoặc read model.
- Ghi nhật ký/audit bổ sung.
- Đồng bộ thông tin với CRM hoặc webhook.
- Tạo báo cáo, thumbnail hoặc những dữ liệu dẫn xuất.
- Kích hoạt một quy trình tiếp theo sau khi trạng thái chính đã được lưu.

Nếu những tác vụ này chạy đồng bộ ngay trong transaction tạo đơn hàng, thời gian chờ của người dùng tăng và một dịch vụ phụ tạm lỗi có thể kéo theo thất bại không cần thiết của nghiệp vụ chính.

Tuy nhiên, **“hậu kỳ” có ba nghĩa khác nhau**, cần chọn đúng:

1. **Sau thời điểm phát event:** một `@Async @EventListener` được submit vào executor khi publisher công bố event; listener có thể bắt đầu **trước khi transaction gốc commit**.
2. **Sau khi transaction commit thành công:** một `@TransactionalEventListener(phase = AFTER_COMMIT)` chỉ được kích hoạt khi transaction phát event hoàn tất bằng commit. Kết hợp `@Async` để chạy công việc trên worker.
3. **Sau khi HTTP response được trả về:** một công việc có thể vẫn chưa chạy, đang chạy hoặc đã hoàn tất trước khi response thực sự gửi; không được đồng nhất việc dùng `@Async` với một callback “chạy chính xác sau khi response flush”.

Một thiết kế tốt phải chỉ ra **mốc bắt đầu hợp lệ**, **độ bền công việc**, **cách xử lý lỗi**, **giới hạn executor**, **idempotency** và **cách kiểm thử**.

Bài này ưu tiên mô hình thường gặp: *đơn hàng commit thành công, rồi một worker thực hiện công việc bổ sung bất đồng bộ*, kèm ví dụ Java 17+ chạy được.

## 2. Chọn kiểu listener theo thời điểm nghiệp vụ

| Cách viết | Thời điểm có thể chạy | Phù hợp | Cần cảnh giác |
| --- | --- | --- | --- |
| `@EventListener` thường | Ngay khi publish, đồng bộ mặc định | Logic nội bộ nhanh, cần phản hồi tức thời | Kéo dài thời gian transaction/request |
| `@Async @EventListener` | Được submit ngay khi publish | Công việc độc lập, không cần chờ commit | Worker có thể đọc DB trước commit hoặc chạy dù transaction rollback |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau commit thành công, đồng bộ theo callback thông thường | Side effect phụ thuộc dữ liệu đã commit | Có thể chặn thread đang hoàn tất transaction |
| **`@Async @TransactionalEventListener(AFTER_COMMIT)`** | **Chỉ submit công việc sau commit**, xử lý trên executor | Notification, indexing, callback sau commit | Queue vẫn ở RAM, lỗi không rollback DB, cần giám sát và recovery |
| Transactional outbox + worker | Worker đọc yêu cầu xử lý đã commit bền vững | Công việc không được mất khi process crash | Phải thiết kế relay, retry, trạng thái và idempotency |
| Broker/durable queue | Phát công việc ra hệ thống messaging bên ngoài | Nhiều services/consumers, recovery và scale độc lập | Đồng bộ DB với message cần outbox/transaction strategy |

**Nguyên tắc:** Nếu listener chỉ cần một việc nhỏ, đồng bộ và không phụ thuộc commit, đừng thêm async vô cớ. Nếu phải lấy dữ liệu **đã commit**, dùng phase hậu commit hoặc persisted work item; không chỉ gắn `@Async` vào một listener được phát trong transaction.

## 3. Cơ chế `@Async` với Spring Application Events

Khi dùng hạ tầng `@Async`, Spring gọi method qua async proxy và submit invocation vào một `TaskExecutor`. Handler có thể tiếp tục chạy trên thread nền sau khi caller trở về.

```java
@Component
public class NotificationListener {

    @Async("postExecutor")
    @EventListener
    public void onOrderCreated(OrderCreated event) {
        notificationClient.send(event.orderId());
    }
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Cần Spring-managed bean, `@EnableAsync`, executor bean tên `postExecutor`, event type `OrderCreated` và `notificationClient`.

Cách này là asynchronous **kể từ lúc event được publish**, nhưng không có điều kiện commit. Ví dụ:

```text
Request thread                         Worker thread
  BEGIN transaction T1
      |
      +-- INSERT order
      +-- publishEvent(OrderCreated)
      |        |
      |        +-- submit async task -----> listener có thể chạy
      |                                          |
      |                                          +-- SELECT order
      |                                               chưa chắc thấy T1 commit
      |
      +-- một lỗi xảy ra
      +-- ROLLBACK T1
```

Worker có thể đã gửi email “đơn hàng được tạo” mặc dù transaction sau đó rollback. Đây không phải bug của Spring: `@Async` chỉ đổi thread, không mang contract commit.

### 3.1. Enable async và chọn executor rõ ràng

```java
@Configuration
@EnableAsync
public class AsyncConfig {

    @Bean("postExecutor")
    public ThreadPoolTaskExecutor postExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("post-");
        return executor;
    }
}
```

Đây là **đoạn cấu hình minh họa**; cần imports Spring tương ứng. Các con số chỉ là ví dụ, không phải thông số mặc định tối ưu. Nếu thiếu `@EnableAsync` hoặc code tự gọi `this.asyncMethod()` trong cùng bean, async advice có thể không được áp dụng. Dùng bean do Spring quản lý và gọi qua proxy.

`@Async("postExecutor")` tránh việc vô tình chạy trên một executor mặc định khác khi có nhiều executor trong hệ thống.

## 4. Mẫu quan trọng: `@Async` + `@TransactionalEventListener(AFTER_COMMIT)`

Mẫu chủ đạo:

```java
@Transactional
public void createOrder(String orderId) {
    repository.insert(orderId);
    publisher.publishEvent(new OrderCreated(orderId));
}

@Async("postExecutor")
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCommitted(OrderCreated event) {
    notificationService.send(event.orderId());
}
```

Đây là **mã minh họa**, gồm hai method thuộc những Spring-managed beans thích hợp; cần transaction manager, repository, publisher, executor và cấu hình annotation.

Vòng đời:

```text
Thread gọi OrderService
  |
  +-- BEGIN T1
  +-- INSERT order
  +-- publishEvent(OrderCreated)
  |     |
  |     +-- listener AFTER_COMMIT đăng ký chờ transaction T1
  |
  +-- Kết thúc phần thân service method
  +-- COMMIT T1 thành công
  |
  +-- AFTER_COMMIT callback
  |     |
  |     +-- async proxy SUBMIT task vào postExecutor
  |
  +-- cleanup và trả về caller
                           |
                           v
                    Executor worker
                           |
                           +-- nhận event DTO
                           +-- đọc dữ liệu đã commit
                           +-- thực hiện notification/indexing/audit
                           +-- ghi trạng thái hoặc xử lý lỗi riêng
```

**Điểm chính:** `AFTER_COMMIT` điều khiển **thời điểm event listener được kích hoạt**, còn `@Async` điều khiển **nơi method body chạy**. Chúng giải quyết hai vấn đề khác nhau.

Nếu T1 rollback, `AFTER_COMMIT` không được kích hoạt. Nếu event được publish **ngoài transaction**, listener transaction-bound mặc định **bị bỏ qua** (`fallbackExecution=false`), vì Spring không có transaction completion để chờ.

Không mặc định cho `fallbackExecution=true` chỉ để “chạy được”. Khi không có transaction, đó không còn là guarantee “sau commit”.

### 4.1. Vì sao listener không tự kế thừa transaction T1?

Trong ứng dụng Spring dùng imperative `PlatformTransactionManager`, transaction context thường được gắn vào thread. Worker executor chạy trên **thread khác**, nên không tự tham gia transaction T1.

Hơn nữa, T1 đã commit. Nếu worker cần ghi một bảng trạng thái, chạy trong **transaction mới**:

```java
@Service
public class JobStatusWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void markDone(String jobId) {
        // Update/insert trạng thái tác vụ trong DB.
    }
}
```

Đây là đoạn minh họa; `JobStatusWriter` nên là một Spring-managed bean **riêng** và được gọi qua proxy. Không dùng self-invocation `this.markDone(...)` nếu muốn `@Transactional` được intercept ở chế độ proxy mặc định.

Trong worker thread không có transaction đang hoạt động, một method `@Transactional` với propagation `REQUIRED` cũng có thể mở transaction mới. `REQUIRES_NEW` ở đây thể hiện **ý định tạo transaction độc lập** và tránh phụ thuộc vào bối cảnh caller; nó đặc biệt quan trọng với thao tác ghi từ callback hậu commit đồng bộ trên publisher thread khi tài nguyên T1 có thể còn bound trước cleanup.

## 5. Ví dụ hoàn chỉnh Java 17+: commit thành công mới chạy hậu kỳ async

Ví dụ không cần Spring Boot hay web server, dùng:

- JDK 17+.
- Spring Framework **6.2.12** (`spring-context`, `spring-jdbc`, `spring-tx` qua dependency transitives).
- H2 in-memory để mô phỏng transaction DB.
- `ThreadPoolTaskExecutor` có giới hạn queue và số thread.
- `@EnableAsync`, `@EnableTransactionManagement`.
- `@TransactionalEventListener(AFTER_COMMIT)` kết hợp `@Async`.
- Một writer bean `@Transactional(REQUIRES_NEW)` ghi kết quả hậu xử lý.
- `CountDownLatch` để chứng minh **service trả về khi tác vụ nền chưa hoàn thành**, không dùng thời gian chờ ngẫu nhiên.

### 5.1. Cấu trúc dự án

```text
spring-async-post-processing-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AfterCommitAsyncDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-async-post-processing-demo'
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
    mainClass = 'demo.AfterCommitAsyncDemo'
}
```

Đây là dự án Gradle dùng thư viện Spring Framework thuần. H2 in-memory/`DriverManagerDataSource` chỉ để học: ứng dụng production cần DB persistent, pool kết nối, timeout và quan sát trạng thái.

### 5.2. `src/main/java/demo/AfterCommitAsyncDemo.java`

```java
package demo;

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

public class AfterCommitAsyncDemo {

    public record OrderCreated(String orderId) {}

    public static class Probe {
        final CountDownLatch workerStarted = new CountDownLatch(1);
        final CountDownLatch releaseWork = new CountDownLatch(1);
        final CountDownLatch workerFinished = new CountDownLatch(1);

        final AtomicInteger listenerStarts = new AtomicInteger();
        final AtomicBoolean committedOrderVisible =
                new AtomicBoolean(false);
        final AtomicReference<String> workerName =
                new AtomicReference<>("");
        final AtomicReference<Throwable> error =
                new AtomicReference<>();
    }

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void create(String orderId, boolean forceRollback) {
            jdbc.update(
                    "insert into purchase_orders (order_id) values (?)",
                    orderId);
            publisher.publishEvent(new OrderCreated(orderId));

            if (forceRollback) {
                throw new IllegalStateException("rollback requested");
            }
        }
    }

    public static class PostWorkWriter {
        private final JdbcTemplate jdbc;

        public PostWorkWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        // Ghi hậu kỳ trong một transaction độc lập.
        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void recordCompleted(String orderId) {
            jdbc.update(
                    "insert into completed_post_work "
                    + "(order_id, result) values (?, ?)",
                    orderId, "DONE");
        }
    }

    public static class PostCommitListener {
        private final JdbcTemplate jdbc;
        private final PostWorkWriter writer;
        private final Probe probe;

        public PostCommitListener(
                JdbcTemplate jdbc,
                PostWorkWriter writer,
                Probe probe) {
            this.jdbc = jdbc;
            this.writer = writer;
            this.probe = probe;
        }

        @Async("postExecutor")
        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void onCreated(OrderCreated event) {
            probe.listenerStarts.incrementAndGet();
            probe.workerName.set(Thread.currentThread().getName());
            probe.workerStarted.countDown();

            try {
                // Worker đã bắt đầu nhưng chủ động chờ lệnh từ main.
                if (!probe.releaseWork.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "worker release timed out");
                }

                Integer found = jdbc.queryForObject(
                        "select count(*) from purchase_orders "
                        + "where order_id = ?",
                        Integer.class, event.orderId());

                probe.committedOrderVisible.set(
                        found != null && found == 1);

                writer.recordCompleted(event.orderId());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                probe.error.compareAndSet(null, ex);
            } catch (RuntimeException ex) {
                probe.error.compareAndSet(null, ex);
            } finally {
                probe.workerFinished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    @EnableAsync
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl(
                    "jdbc:h2:mem:post_work;DB_CLOSE_DELAY=-1");
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

        @Bean("postExecutor")
        ThreadPoolTaskExecutor postExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(4);
            executor.setQueueCapacity(50);
            executor.setThreadNamePrefix("post-");
            executor.setRejectedExecutionHandler(
                    new ThreadPoolExecutor.AbortPolicy());
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(10);
            return executor;
        }

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        OrderService orderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        PostWorkWriter postWorkWriter(JdbcTemplate jdbc) {
            return new PostWorkWriter(jdbc);
        }

        @Bean
        PostCommitListener postCommitListener(
                JdbcTemplate jdbc,
                PostWorkWriter writer,
                Probe probe) {
            return new PostCommitListener(jdbc, writer, probe);
        }
    }

    private static int count(JdbcTemplate jdbc, String sql) {
        return jdbc.queryForObject(sql, Integer.class);
    }

    public static void main(String[] args)
            throws InterruptedException {

        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService orders = context.getBean(OrderService.class);
            Probe probe = context.getBean(Probe.class);

            jdbc.execute(
                    "create table purchase_orders ("
                    + "order_id varchar(40) primary key)");

            jdbc.execute(
                    "create table completed_post_work ("
                    + "order_id varchar(40) primary key, "
                    + "result varchar(20) not null)");

            String workCountSql =
                    "select count(*) from completed_post_work";
            String orderCountSql =
                    "select count(*) from purchase_orders";

            // T1 commit: callback sau commit submit async task.
            orders.create("A", false);

            if (!probe.workerStarted.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "async listener did not start");
            }

            // Worker A đang chờ releaseWork, chưa ghi hậu kỳ.
            System.out.println("service A returned=true");
            System.out.println("post work before release="
                    + count(jdbc, workCountSql));

            try {
                // T2 rollback: AFTER_COMMIT không submit task B.
                boolean rollbackCaught = false;
                try {
                    orders.create("B", true);
                } catch (IllegalStateException ex) {
                    rollbackCaught = true;
                }

                System.out.println("rollback B caught="
                        + rollbackCaught);
                System.out.println("orders after rollback="
                        + count(jdbc, orderCountSql));
                System.out.println("listener starts before release="
                        + probe.listenerStarts.get());
            } finally {
                // Đảm bảo worker A được giải phóng dù main bị lỗi.
                probe.releaseWork.countDown();
            }

            if (!probe.workerFinished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "post-processing did not finish");
            }
            if (probe.error.get() != null) {
                throw new IllegalStateException(
                        "post-processing failed", probe.error.get());
            }

            int aCompleted = jdbc.queryForObject(
                    "select count(*) from completed_post_work "
                    + "where order_id = ?",
                    Integer.class, "A");

            System.out.println("post work after release="
                    + count(jdbc, workCountSql));
            System.out.println("only A completed=" + (aCompleted == 1));
            System.out.println("worker saw committed A="
                    + probe.committedOrderVisible.get());
            System.out.println("worker thread is postExecutor="
                    + probe.workerName.get().startsWith("post-"));
        }
    }
}
```

### 5.3. Chạy và kết quả

Trong thư mục dự án:

```bash
gradle -q run
```

Tám dòng **do chương trình chủ động in**, theo thứ tự:

```text
service A returned=true
post work before release=0
rollback B caught=true
orders after rollback=1
listener starts before release=1
post work after release=1
only A completed=true
worker saw committed A=true
worker thread is postExecutor=true
```

**Chú ý:** Đoạn trên thực tế có **chín dòng** `System.out.println`; chính chín dòng là output mong đợi. Gradle hoặc logging Spring có thể in thêm thông báo khác. Không lấy tổng dòng console tuyệt đối làm assertion khi logging configuration thay đổi.

### 5.4. Phân tích kỹ từng bước

**Bước A — commit rồi mới submit:**

1. `context.getBean(OrderService.class)` trả service do Spring quản lý; lời gọi `create("A", false)` đi qua transaction advice.
2. T1 bắt đầu. `JdbcTemplate` INSERT order A; service phát `OrderCreated("A")` **trong T1**.
3. `@TransactionalEventListener(AFTER_COMMIT)` không gọi handler ngay; nó đăng ký xử lý với kết quả transaction.
4. T1 commit thành công. Khi callback hậu commit được kích hoạt, async proxy submit handler vào `postExecutor`.
5. Worker thread `post-*` bắt đầu, tăng `listenerStarts` và mở `workerStarted`, nhưng **chưa** ghi bảng hậu kỳ vì đang đợi `releaseWork`.
6. Service đã trả về main, nhưng bảng `completed_post_work` vẫn có **0 dòng**. Đây là bằng chứng công việc hậu kỳ có thể chưa hoàn tất khi caller trở về.

**Bước B — rollback không kích hoạt hậu commit:**

1. `orders.create("B", true)` INSERT B và publish event B trong T2.
2. Service cố tình ném unchecked exception. Transaction interceptor rollback T2.
3. Listener có phase `AFTER_COMMIT` không xử lý event B. Trong trạng thái đang giữ worker A, counter `listenerStarts` vẫn bằng 1; DB `purchase_orders` chỉ có A.

**Bước C — worker độc lập ghi DB:**

1. Main mở latch `releaseWork`, worker tiếp tục.
2. Worker query order A đã commit, thấy một dòng.
3. Worker gọi bean riêng `PostWorkWriter.recordCompleted("A")`. `@Transactional(REQUIRES_NEW)` mở transaction T3 độc lập cho INSERT vào `completed_post_work`, rồi commit.
4. `workerFinished` được mở sau khi writer trả về. Main chờ latch, kiểm tra nếu có exception và chỉ lúc đó in kết quả.
5. Bảng `completed_post_work` có đúng một dòng thuộc A, không có B. Tên thread bắt đầu bằng `post-`, cho thấy handler chạy trên executor được đặt tên.

`CountDownLatch`, `AtomicBoolean`, `AtomicInteger` và `AtomicReference` làm việc trao đổi giữa các thread có visibility phù hợp, thay vì kiểm tra một biến thường qua `Thread.sleep(...)`.

### 5.5. Giới hạn của chương trình mẫu

- Ví dụ **chứng minh mốc commit và cơ chế async**, không giả định email hoặc external API ngoài đã thành công.
- H2 `mem:` không tồn tại sau khi JVM dừng; các record này không đại diện cho một hệ thống job bền vững.
- `Probe` là test instrumentation trong RAM, không phải job state store.
- Handler dùng latch để mô phỏng delay, không phải cách xử lý công việc ở production.
- Ví dụ chỉ có một post-job hợp lệ, nên không chứng minh throughput, fairness hoặc ordering ở tải lớn.
- `recordCompleted` chèn một dòng và không có retries; khi lỗi DB, chương trình mẫu chỉ giữ error trong `AtomicReference` để main phát hiện.
- Bên ngoài demo, không nên giữ một transaction DB mở suốt thời gian gọi HTTP API chậm nếu không cần; tách ranh giới ghi trạng thái ngắn khỏi I/O.

## 6. Vì sao nên tách business event khỏi yêu cầu chạy job?

Một event domain:

```java
public record OrderCreated(
        String orderId,
        long aggregateVersion,
        String correlationId) {}
```

nên nói **điều gì đã xảy ra** trong nghiệp vụ. Một hậu xử lý có thể được đại diện bằng một `PostProcessingJob`/outbox row với lifecycle riêng:

```text
OrderCreated(orderId=O-42, version=7)
    |
    +-- NotifyCustomerJob(orderId=O-42, status=NEW)
    +-- IndexOrderJob(orderId=O-42, status=NEW)
```

Điều này có ích khi cần:

- Một event kích hoạt nhiều tác vụ với chính sách retry khác nhau.
- Phân biệt đơn hàng đã được tạo với email đang chờ gửi.
- Giới hạn capacity riêng của email API và indexing service.
- Quan sát trạng thái tác vụ `NEW`, `RUNNING`, `RETRY`, `DONE`, `FAILED`.
- Retry từng bước hậu kỳ mà **không tạo lại đơn hàng**.

Không đặt mọi side effect trong một listener khổng lồ khi mỗi loại cần timeout, failure policy và SLO khác nhau. Nhưng cũng không cần chia thành hàng chục event cho một thao tác đồng bộ nhỏ nếu không có giá trị kiến trúc.

## 7. Lỗi trong listener async: publisher không nhận kết quả thành công

Một lỗi thường gặp là:

```java
@Async("postExecutor")
@EventListener
public void sendEmail(OrderCreated event) {
    throw new IllegalStateException("mail server unavailable");
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Với `void @Async`, exception được ném trên **worker thread**. Nó không tự quay về request thread để caller nhận như exception đồng bộ.

Spring cho phép cấu hình `AsyncUncaughtExceptionHandler`:

```java
@Configuration
@EnableAsync
public class AsyncErrorsConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (ex, method, args) -> {
            System.err.println(
                    "async handler failed: " + method.getName()
                    + ": " + ex.getMessage());
        };
    }
}
```

Đây là **mã minh họa**, cần imports `AsyncConfigurer`, `AsyncUncaughtExceptionHandler`, `Configuration`, `EnableAsync`; production nên sử dụng structured logs, tracing, metrics và failure state bền vững thay vì chỉ `System.err`.

### 7.1. Có nên nuốt exception trong listener?

Chỉ nên bắt lỗi khi bạn biết **phải làm gì** với nó:

```java
@Async("postExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCreated(OrderCreated event) {
    try {
        mailClient.send(event.orderId());
    } catch (TransientMailException ex) {
        retryWriter.schedule(
                event.orderId(), ex.getMessage());
    }
}
```

Đây là mã minh họa; `TransientMailException`, `mailClient` và `retryWriter` do ứng dụng định nghĩa. `retryWriter` nên lưu một **bản ghi yêu cầu retry** trong transaction riêng được quản lý đúng cách.

Nếu lỗi retryWriter cũng xảy ra thì task vẫn có thể mất. `catch (Exception)` rồi chỉ log không cung cấp guarantee phục hồi sau process crash.

**Đặc biệt:** `@TransactionalEventListener(AFTER_COMMIT)` trong Spring Framework imperative được kích hoạt qua completion callback. Nếu việc **submit vào executor bị từ chối** ở thời điểm callback sau commit, T1 đã commit và không thể rollback. Exception ở callback có thể được Spring log mà không propagate tới caller, tùy đường xử lý. Không chỉ nhìn response 200 rồi khẳng định worker chắc chắn đã được nhận vào pool.

### 7.2. Có thể dùng `CompletableFuture` không?

Với một service async được **gọi tường minh** qua Spring proxy, có thể thiết kế:

```java
@Async("postExecutor")
public CompletableFuture<SendResult> send(String orderId) {
    SendResult result = mailClient.send(orderId);
    return CompletableFuture.completedFuture(result);
}
```

Đây là đoạn minh họa, cần `SendResult`, `mailClient` và import `CompletableFuture`. Caller giữ `CompletableFuture` rồi kết hợp `whenComplete`, `handle`, `allOf` hoặc `join` tùy nhu cầu.

Nhưng `ApplicationEventPublisher.publishEvent(...)` **không trả về future của các listeners**, nên không có cách đơn giản để viết:

```java
CompletableFuture<?> done = publisher.publishEvent(event);
```

Đây là **phản ví dụ không biên dịch** vì `publishEvent` trả `void`. Nếu caller thực sự cần await job, hãy dùng một API async service với future, hoặc persisted job ID/status. Không giả lập future từ một Application Event không có completion contract.

### 7.3. Async listener không phát event tiếp bằng return value

Với synchronous `@EventListener`, Spring hỗ trợ một số kiểu return để publish event tiếp theo. **Cơ chế return-as-event không hỗ trợ async listeners**. Nếu thành công ở worker cần phát `NotificationSent`, dùng:

```java
publisher.publishEvent(
        new NotificationSent(event.orderId()));
```

Đây là mã minh họa; `NotificationSent` là event class do ứng dụng định nghĩa. Nếu event kết quả phải tồn tại qua crash, cần bền vững hóa qua DB/outbox thay vì chỉ publish trong RAM.

## 8. Capacity, backpressure và shutdown của executor

Một executor cần giới hạn theo tải:

```java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(6);
executor.setQueueCapacity(100);
executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy());
```

Đây là đoạn minh họa; phải đặt trên bean `ThreadPoolTaskExecutor` khi cấu hình. Với thread pool kiểu `ThreadPoolExecutor`, sau khi có đủ core workers, task thường vào queue; pool chỉ mở rộng tới max khi queue đầy. Một **queue không giới hạn** thường khiến `maxPoolSize` không phát huy tác dụng; backlog có thể lớn không kiểm soát.

### 8.1. Khi executor đầy

- `AbortPolicy` khiến việc submit bị từ chối; Spring `ThreadPoolTaskExecutor` thường biểu diễn bằng `TaskRejectedException`.
- `CallerRunsPolicy` có thể thực thi task trên **thread publisher** khi pool quá tải, làm thay đổi latency/thread context và có thể ảnh hưởng transaction. Với listener transaction-bound, phải hiểu chính xác thời điểm callback.
- `DiscardPolicy` và `DiscardOldestPolicy` có thể **bỏ task**, không phù hợp công việc quan trọng nếu thiếu recovery.
- Queue in-memory không tồn tại qua process crash.

Nếu job bắt buộc được xử lý, hãy **persist intent trước**, rồi worker đọc theo capacity. Không coi việc tăng queue vô hạn là cơ chế backpressure.

### 8.2. Theo dõi các chỉ số nào?

| Chỉ số | Ý nghĩa |
| --- | --- |
| Events published/s | Lưu lượng event đầu vào, **không phải** số job hoàn tất |
| Task submit/accepted/s | Công việc được executor chấp nhận |
| Active threads | Worker đang bận |
| Queue depth/capacity | Backlog và áp lực gần rejection |
| Queue wait p95/p99 | Độ trễ từ lúc enqueue đến lúc handler bắt đầu |
| Handler duration p95/p99 | Thời gian tác vụ thực thi |
| Completed/s | Throughput thực tế |
| Rejected/s | Tỷ lệ task không được chấp nhận |
| Failed/retried/s | Sức khỏe downstream và retry pressure |
| Oldest pending job age | Việc tồn đọng lâu nhất, đặc biệt với outbox |
| DB/HTTP connection pool utilization | Nút cổ chai ngoài executor |

Đo **thời gian từ event được nhận đến side effect hoàn tất**, không chỉ đo `publishEvent` return nhanh thế nào.

### 8.3. Graceful shutdown không phải durable recovery

`setWaitForTasksToCompleteOnShutdown(true)` và `setAwaitTerminationSeconds(...)` giúp shutdown có trật tự trong những điều kiện được hỗ trợ. Nhưng JVM có thể chết do `SIGKILL`, OOM hoặc mất điện; các task chỉ nằm trong queue RAM sẽ mất.

Với deployment/kubernetes cần xem termination grace period, readiness/draining, timeout của external APIs và recovery từ persisted job store. **Nếu công việc là bắt buộc, không nên để in-memory async executor là nguồn chân lý duy nhất**.

## 9. Transactional outbox cho tác vụ hậu kỳ không được mất

`@Async @TransactionalEventListener(AFTER_COMMIT)` là lựa chọn đơn giản, nhưng có **cửa sổ lỗi**:

```text
T1 COMMIT
   |
   +-- process crash trước khi callback/submit
   |
   +-- executor queue đầy, rejection
   |
   +-- task được accept nhưng JVM crash trước khi chạy
   |
   +-- worker chạy xong external API nhưng crash trước khi ghi DONE
```

Với việc quan trọng, trong **chính T1** ghi yêu cầu hậu kỳ:

```text
BEGIN T1
  +-- INSERT order
  +-- INSERT outbox(
          eventId, orderId, type=SEND_CONFIRMATION,
          status=NEW, attempt=0
      )
COMMIT T1
      |
      +-- worker poll/claim outbox theo capacity
            |
            +-- gọi email/HTTP/broker với idempotency key
            +-- success -> mark DONE
            +-- transient failure -> RETRY với backoff
            +-- permanent failure -> FAILED/DLQ + alert
```

Nếu T1 rollback, order và outbox cùng rollback. Nếu process chết sau commit, row outbox còn để xử lý lại.

### 9.1. Các thuộc tính nên có ở job/outbox

Một mô hình có thể gồm:

```sql
CREATE TABLE post_jobs (
    job_id VARCHAR(80) PRIMARY KEY,
    order_id VARCHAR(40) NOT NULL,
    job_type VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempts INT NOT NULL,
    next_attempt_at TIMESTAMP,
    last_error VARCHAR(1000)
);
```

Đây là **DDL minh họa**, điều chỉnh theo database và kiểu timestamp thực tế. Khi có nhiều workers, cần cơ chế claim/lease/locking/unique constraints để không có hai workers cùng xử lý một job ngoài ý muốn.

Idempotency key nên dựa trên **job ID hoặc operation ID ổn định**, không tạo UUID mới cho mỗi retry. Nếu external system đã gửi email hoặc ghi payment nhưng client timeout, retry có thể gửi trùng nếu không có dedupe/idempotency.

### 9.2. Tránh retry toàn bộ command đã commit

Nếu `orders.create("A")` đã commit nhưng notification thất bại, **không** tự động gọi lại `create("A")` chỉ để gửi lại email. Retry đúng mục tiêu: `sendConfirmation(jobId, orderId)`, không tạo lại order/đơn hàng khác.

Tách trạng thái:

```text
Order: CREATED
Post-job: RETRY_PENDING
```

Thông điệp API có thể nói “đơn hàng đã được tạo; xác nhận đang được xử lý” thay vì đồng nhất thành công của email với việc tạo order.

## 10. Không giữ object gắn request/thread trong event async

Không nên:

```java
public record OrderCreated(
        String orderId,
        HttpServletRequest request) {}
```

Đây là **mã minh họa không nên áp dụng**. `HttpServletRequest` có vòng đời gắn HTTP request, attribute mutable, stream/session context và không có contract an toàn để giữ sau khi request kết thúc.

Không tự kế thừa vào worker:

- `RequestContextHolder`;
- Spring Security context mặc định;
- MDC/logging/tracing context nếu chưa cấu hình propagation;
- JDBC transaction của request thread;
- JPA EntityManager/lazy-loaded entity.

Thay vào đó, chụp một **payload bất biến**:

```java
public record OrderCreated(
        String orderId,
        String eventId,
        String verifiedTenantId,
        String actorId) {}
```

Đây là định nghĩa minh họa riêng, không thay `OrderCreated` một field trong project runnable. `verifiedTenantId` và `actorId` phải lấy từ cơ chế xác thực/ủy quyền phù hợp, không tin trực tiếp header client. Nếu dùng `List`/`Map`, cần defensive copy và immutable nested objects.

Muốn bảo toàn trace/MDC, cân nhắc `TaskDecorator` hoặc Micrometer Context Propagation theo cấu hình, với cleanup đúng. Nhưng context propagation **không làm Servlet request tồn tại lâu hơn** và không thay thế payload nghiệp vụ.

## 11. Ordering khi nhiều tác vụ hậu kỳ có phụ thuộc

Giả sử ba bước:

```text
OrderCreated
  |
  +-- reserve inventory
  |
  +-- authorize payment
  |
  +-- send invoice
```

Nếu invoice chỉ được gửi sau khi inventory và payment thành công, cho cả ba listener `@Async` nghe cùng `OrderCreated` không đủ. `@Order` sắp thứ tự **dispatch/invocation**, không bảo đảm từng async worker **hoàn thành** trước worker kế tiếp.

Cách tốt hơn:

```text
OrderCreated
    |
    +-- InventoryReserved (chỉ phát sau khi giữ hàng thành công)
            |
            +-- PaymentAuthorized
                    |
                    +-- InvoiceRequested
```

Hoặc dùng một orchestrator với trạng thái durable (saga/workflow) khi có nhiều tiền đề và failure recovery. Với các event cùng aggregate, cần eventId/sequence, idempotency và ordering per aggregate khi có nhiều workers/brokers.

Không dùng `Thread.sleep(100)` để “chờ” tác vụ đầu tiên. Nếu caller cần một kết quả rõ ràng trong cùng request, cân nhắc gọi service trực tiếp với `CompletableFuture` và composition, hoặc đồng bộ khi contract thực sự yêu cầu.

## 12. Kiểm thử đúng ranh giới publish, commit và completion

Một bộ test tốt nên tách ba điều:

1. **Publisher có gọi đúng event?** Mockito `ArgumentCaptor<OrderCreated>` trên `ApplicationEventPublisher` để kiểm tra type/payload/count.
2. **Event có được Spring công bố?** Spring Test `@RecordApplicationEvents` với `ApplicationEvents.stream(OrderCreated.class)` để xác minh event được publish trong context.
3. **Listener hậu commit async có hoàn tất đúng không?** Latch/future/DB state với timeout; kiểm tra **sau commit thật** và sau worker completion.

### 12.1. Những test nên có

| Kịch bản | Assertion |
| --- | --- |
| T1 commit | Listener `AFTER_COMMIT` được kích hoạt và worker ghi hậu kỳ |
| T1 rollback | Listener `AFTER_COMMIT` không chạy cho event đó |
| Event publish ngoài transaction | Listener mặc định bỏ qua nếu `fallbackExecution=false` |
| Listener async chờ I/O | Caller có thể trở về trước khi side effect hoàn tất |
| Worker ném exception | Có error log/metric/failure state; transaction gốc vẫn commit |
| Executor queue đầy | Rejection được quan sát; job critical có đường recovery |
| Process crash/restart | Job/outbox persistent được phục hồi |
| Two workers + one job | Lock/claim hoặc idempotency ngăn side effect trùng |
| Duplicate event | Job/result không bị nhân đôi |
| Event chứa mutable DTO | Snapshot trong worker không đổi khi source thay đổi |

### 12.2. Bẫy trong Spring Test `@Transactional`

Test method được Spring Test bọc bởi `@Transactional` thường **rollback mặc định** khi test kết thúc. Nếu test publish event trong transaction rồi assert `AFTER_COMMIT` **trước khi commit**, listener chưa chạy. Nếu test kết thúc bằng rollback, listener sẽ không chạy.

Khi cần commit thật trong một test được Spring quản lý transaction, có thể:

```java
TestTransaction.flagForCommit();
TestTransaction.end();

// Sau đó mới chờ async completion và assert DB state.
```

Đây là đoạn minh họa, cần Spring Test và một transaction đang hoạt động trong test. Lưu ý `TestTransaction.end()` chỉ kết thúc test-managed transaction; nó không tự chờ worker async xong. Vì vậy phải kết hợp latch/observable state.

Một cách khác là không annotate test method bằng `@Transactional`, để lời gọi service qua transaction proxy tự commit trước khi assert hậu kỳ.

### 12.3. Vì sao không test bằng `Thread.sleep`?

```java
service.create("A", false);
Thread.sleep(100);
assertEquals(1, countCompletedJobs());
```

Đây là **phản ví dụ**. Máy CI có thể chạy chậm hoặc executor bận, làm test flaky. Ví dụ mục 5 dùng `workerStarted`, `releaseWork` và `workerFinished` để **điều khiển thứ tự một cách xác định** và xác minh completion bằng tín hiệu thật.

## 13. Bảng chẩn đoán sự cố

| Dấu hiệu | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| `@Async` listener vẫn chạy trên request thread | Thiếu `@EnableAsync`, sai bean/proxy, self-invocation | Kiểm tra executor bean, proxy và tên thread |
| Listener `AFTER_COMMIT` không chạy | Event publish ngoài transaction, T1 rollback, listener chưa đăng ký | Publish trong transaction service thật, kiểm tra phase |
| Worker không thấy order vừa tạo | Dùng `@Async @EventListener` nên worker chạy trước commit | Đổi sang `@TransactionalEventListener(AFTER_COMMIT)` hoặc outbox |
| Worker không có RequestContextHolder/MDC | ThreadLocal không tự propagate | Capture immutable payload; TaskDecorator cho observability |
| Method `REQUIRES_NEW` không mở transaction | `this.method()` bỏ qua transaction proxy | Gọi Spring bean riêng qua proxy |
| Caller nhận thành công nhưng notification thất bại | Async exception ở worker, không propagate | Async error handler, metrics, persisted failure/retry |
| Hậu commit task bị reject nhưng order đã tạo | Executor đầy **sau khi** T1 commit | Outbox/persisted queue, capacity và admission control |
| Tăng max threads nhưng queue vẫn chờ dài | Queue chưa đầy nên pool không tăng vượt core | Bounded queue, sizing theo throughput/latency |
| Retry tạo thêm đơn hàng | Retry toàn bộ nghiệp vụ thay vì post-job | Stable job ID, retry riêng side effect |
| Email được gửi hai lần | Timeout ambiguous, duplicate delivery, thiếu idempotency | Idempotency key hoặc dedupe |
| Sau deploy mất các task chưa chạy | Executor queue nằm trong RAM | Durable outbox/queue và worker recovery |
| Test lúc pass lúc fail | Assert ngay sau publish hoặc dùng `Thread.sleep` | Latch/Awaitility/future với timeout |
| DB insert trong post-commit callback không lưu | Tài nguyên transaction cũ có thể còn bound | Gọi transaction mới đúng proxy, kiểm tra commit |
| `@Order` không bảo đảm job B sau A | Async completion order khác dispatch order | Event ACompleted/workflow orchestration |

## 14. Checklist trước khi đưa mẫu hậu kỳ async vào production

- [ ] Tác vụ có thật sự **không cần hoàn tất** trước khi response/business method trả về?
- [ ] Yêu cầu là “sau publish” hay “chỉ sau commit thành công”?
- [ ] Event có được publish **bên trong transaction** phù hợp nếu dùng `AFTER_COMMIT`?
- [ ] Listener là Spring-managed bean, có `@EnableAsync` và executor được chỉ rõ?
- [ ] Payload là immutable snapshot/ID, không giữ request/entity/lazy proxy?
- [ ] Worker có transaction DB riêng cho thao tác ghi nếu cần?
- [ ] Có xử lý exception, retry/backoff và idempotency cho side effect ngoài hệ thống?
- [ ] Executor core/max/queue/rejection/shutdown được sizing và giám sát?
- [ ] Tác vụ bắt buộc có persisted outbox hoặc durable queue thay vì RAM-only?
- [ ] Đã test commit, rollback, async completion, executor saturation và crash/restart?
- [ ] Có metric `submitted/accepted/completed/failed/rejected`, queue age, retry age và SLA/SLO?
- [ ] Nếu có phụ thuộc giữa các bước, đã dùng completion event/state machine thay cho `@Order`?

**Kết luận:** Đối với tác vụ hậu kỳ *best-effort* trong ứng dụng Spring, `@Async("postExecutor")` kết hợp `@TransactionalEventListener(phase = AFTER_COMMIT)` là mẫu dễ hiểu để **chỉ bắt đầu sau khi DB commit và không chiếm thread nghiệp vụ trong lúc worker xử lý**. Nó không tự bảo đảm executor nhận task, không tự retry lỗi và không lưu công việc qua JVM crash. Với tác vụ quan trọng, bền vững hóa yêu cầu bằng **transactional outbox + idempotent worker**, dùng executor chỉ để giới hạn và thực thi các job đã được lưu.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — ApplicationContext Events, Asynchronous Listeners và `@Order`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — Task Execution and Scheduling, `@Async`](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — `ThreadPoolTaskExecutor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2 — `@TransactionalEventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework 6.2 — `TransactionSynchronization` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework 6.2 — Transaction Propagation (`REQUIRES_NEW`)](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework 6.2 — Testing Application Events](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html)
