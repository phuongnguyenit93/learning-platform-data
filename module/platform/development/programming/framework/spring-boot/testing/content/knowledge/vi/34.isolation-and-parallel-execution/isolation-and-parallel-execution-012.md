# Dọn executor, scheduler, connection và container khi test kết thúc

> Module: **Spring Boot – testing**  
> Nhóm: **Cách ly và chạy song song**  
> Đề bài: **Dọn executor, scheduler, connection và container khi test kết thúc**  
> Mục tiêu: Đóng đúng resource do test sở hữu, trả JDBC handles về pool, quản lý Spring-owned thread pools theo ApplicationContext, ngăn background tasks sống xuyên test classes, giữ Testcontainers đồng bộ với Spring TestContext cache, và xác nhận cleanup bằng assertions có timeout. Ví dụ Java 17, JUnit Jupiter, Spring Boot 3.5, PostgreSQL Testcontainers.

## 1. Vấn đề: assertions pass nhưng resources vẫn hoạt động

Một test có thể đã hoàn thành assertions nhưng Maven/Surefire vẫn không thoát vì thread pool chưa shutdown. Khi chạy cả suite, background scheduler tiếp tục ghi DB, connection pool vẫn giữ sockets, hoặc Testcontainers PostgreSQL bị dừng trong khi một Spring context cached còn giữ DataSource trỏ đến container cũ.

```java
@Test
void worksButLeaksPool() throws Exception {
    ExecutorService pool = Executors.newSingleThreadExecutor();
    Future<String> result = pool.submit(() -> "OK");

    assertThat(result.get()).isEqualTo("OK");
    // Không gọi shutdown(): thread pool vẫn sống!
}
```

Đây là **anti-pattern snippet**, chưa có imports. `Future.get()` chờ một task xong, nhưng **không** đóng executor. Nếu pool có non-daemon threads, nó có thể giữ JVM sống sau khi test kết thúc. Ngược lại, đóng một Spring-managed executor quá sớm ở `@AfterEach` cũng sai: test khác dùng chung cached context có thể nhận `RejectedExecutionException`.

### 1.1. Triệu chứng thường gặp

- `mvn test` in kết quả nhưng process không kết thúc.
- `pool-N-thread-M`, `scheduling-N`, `task-N` còn sống sau một class.
- Scheduled job chạy sau cleanup và sửa fixtures của test khác.
- `HikariPool ... connection leak detection triggered` hoặc active JDBC connections không về mức kỳ vọng.
- `Connection refused` khi context reuse kết nối tới một Testcontainer đã stop.
- Local HTTP stub bị `Address already in use` vì port hoặc server chưa giải phóng.
- Kafka consumer/Rabbit listener vẫn nhận message sau test, gây cạnh tranh.
- Docker resources tồn tại sau nhiều lượt CI, hoặc một cleanup global phá container của job khác.
- Thêm `@DirtiesContext` làm tests khác fail khi parallel vì đang sử dụng cùng context.
- `@Transactional` đã rollback DB test thread nhưng async task thread vẫn commit.

**Nguyên tắc:** Cleanup là một hợp đồng về **quyền sở hữu**, **thứ tự đóng**, **thời điểm đóng** và **bằng chứng termination**, không phải thêm bừa `close()` vào mọi test.

## 2. Sơ đồ ownership theo vòng đời

```text
CI job / Maven
  ├─ JVM fork 1
  │   ├─ JUnit class A
  │   │   ├─ method a() ─ owns ExecutorService A
  │   │   └─ method b() ─ owns HttpServer B
  │   ├─ JUnit class B
  │   └─ Spring TestContext cache
  │       └─ ApplicationContext X ─ owns:
  │          ├─ ThreadPoolTaskExecutor bean
  │          ├─ ThreadPoolTaskScheduler bean
  │          ├─ HikariDataSource bean
  │          ├─ listener containers
  │          └─ Spring-managed PostgreSQLContainer bean
  ├─ JVM fork 2 (static/cache khác)
  └─ External resources
      ├─ DB schemas/rows
      ├─ broker queues / Redis keys
      ├─ files / open ports
      └─ Docker daemon, network, volumes
```

Một `@Test` kết thúc không nhất thiết đóng `ApplicationContext`. Một JUnit class kết thúc không đồng nghĩa JVM fork exit. Spring TestContext có thể **cache** context giữa các classes cùng cấu hình. Hai JVMs có static state riêng nhưng vẫn chia sẻ Redis hoặc cùng Postgres DB nếu cấu hình trỏ tới một endpoint.

### 2.1. Bảng owner và cleanup

| Resource | Owner | Cách dọn đúng |
| --- | --- | --- |
| `Executors.newSingleThreadExecutor()` trong method | Method | `shutdown()` → bounded `awaitTermination()` → `shutdownNow()` nếu cần |
| `ScheduledExecutorService` của test | Method/class | Cancel `ScheduledFuture`, shutdown, bounded await |
| `ThreadPoolTaskExecutor` khai `@Bean` | Spring context | Context lifecycle destroy, không shutdown ở mỗi method |
| `ThreadPoolTaskScheduler` khai `@Bean` | Spring context | Cancel task đăng ký theo test khi cần; context close quản lý scheduler |
| `Connection` lấy từ Hikari pool | Borrower | `Connection.close()` trả pooled handle |
| `PreparedStatement` / `ResultSet` | Query caller | `try-with-resources` |
| `HikariDataSource` tạo thủ công | Test | `HikariDataSource.close()` ở owner teardown |
| `HikariDataSource` Boot auto-configured | Spring | Context destruction |
| Spring `JdbcTemplate` | Spring/client facade | Không “close pool” sau mỗi operation |
| `@Container static` Testcontainers | JUnit extension | Stop sau class |
| `@Container` instance | JUnit extension | Stop sau method |
| `@Bean PostgreSQLContainer` | Spring context | Stop sau các beans phụ thuộc khi context close |
| `HttpServer` test-created | Test | `server.stop(0)` |
| Kafka client tự tạo | Test | Stop poll loop/wakeup, `close()` |
| Rabbit listener/container do Spring tạo | Spring context | Spring lifecycle stop |
| `@TempDir` | JUnit | JUnit cleanup theo scope |
| External files/queues/DB rows | Test/CI job | Cleanup đúng namespace/ID của owner |

### 2.2. Resource close order ngược với dependency order

```text
Start:
  Postgres Testcontainer → Hikari pool → async worker/scheduler

Stop:
  Disable new work + cancel triggers
  → let in-flight work finish within deadline
  → shutdown workers/schedulers
  → close pooled connections/client beans
  → close DataSource
  → stop Postgres container
```

Nếu stop database trước khi worker đang thực hiện SQL kết thúc, worker có thể fail hoặc để lại kết quả transaction “unknown”. Với Spring-managed Testcontainers beans, Boot 3.5 hỗ trợ start container **trước** dependent beans và stop **sau** khi các dependent beans được destroy. Với custom owners, phải tự định nghĩa thứ tự này.

## 3. JUnit lifecycle: cleanup theo đúng scope

### 3.1. `@AfterEach` so với `@AfterAll`

- `@AfterEach`: chạy sau **mỗi** test method; phù hợp resource được mở ở `@BeforeEach` hoặc chính method.
- `@AfterAll`: chạy sau **tất cả** methods trong class; phù hợp resource class-owned.
- `@BeforeEach` setup và `@AfterEach` cleanup không tự tách những resources **ngoài test**, như Redis DB, shared connection factory hoặc Spring cached context.
- Một `@AfterEach` xóa toàn bộ bảng DB có thể phá dữ liệu test khác khi chạy parallel.
- Nếu cleanup có exception, **không nuốt** để test báo PASS giả.

Ví dụ tự quản lý executor:

```java
class ExecutorLifecycleExample {
    private ExecutorService pool;

    @BeforeEach
    void start() {
        pool = Executors.newSingleThreadExecutor();
    }

    @AfterEach
    void stop() throws InterruptedException {
        pool.shutdown();
        if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            assertThat(pool.awaitTermination(
                    2, TimeUnit.SECONDS)).isTrue();
        }
    }
}
```

Đây là snippet chưa có imports; phần project dùng wrapper `AutoCloseable` để giảm duplication và xử lý interruption.

### 3.2. `try-with-resources` và Java 17

`InputStream`, JDBC `Connection`, `Statement`, `ResultSet` và các resource implement `AutoCloseable` được đóng ngay khi ra khỏi block, kể cả assertion throw:

```java
try (InputStream in = Files.newInputStream(path)) {
    byte[] bytes = in.readAllBytes();
    assertThat(bytes).isNotEmpty();
}
```

**Điểm phiên bản:** Trong **Java 17**, `ExecutorService` **chưa implement `AutoCloseable`**, nên `try (ExecutorService pool = Executors.newSingleThreadExecutor())` không compile. Dùng `finally` hoặc wrapper implement `AutoCloseable`. Nếu đọc ví dụ Java 21+ về executor close, đừng copy nguyên xi vào project Java 17.

### 3.3. JUnit `@AutoClose`

JUnit Jupiter từ 5.11 hỗ trợ `@AutoClose` cho field resource có `close()`. Trên test class lifecycle `PER_METHOD` mặc định, non-static field sẽ được đóng sau mỗi method; static field được đóng sau toàn bộ class. `PER_CLASS` làm instance resource sống theo class.

```java
@AutoClose
AutoCloseable owned = () -> {
    // cleanup
};
```

Đây là snippet. Nếu hai resources phải được đóng theo thứ tự cụ thể, không phụ thuộc implicit field-close order; dùng composite owner gọi `close()` theo thứ tự rõ ràng. Ví dụ runnable `JupiterAutoCloseTest` sẽ assert cleanup ở `@AfterAll`.

### 3.4. `@TempDir` không tự đóng file streams đang mở

JUnit quản lý temp directory, nhưng nếu test giữ `Files.lines(...)` stream hoặc `Files.newInputStream(...)` chưa close, đặc biệt trên Windows, cleanup thư mục có thể fail. Dùng `try-with-resources` cho file handles, rồi để `@TempDir` dọn folder.

## 4. ExecutorService: shutdown đúng và tránh treo CI

### 4.1. Các bước cần nhớ

```java
pool.shutdown();
boolean done = pool.awaitTermination(
        2, TimeUnit.SECONDS);

if (!done) {
    pool.shutdownNow();
    done = pool.awaitTermination(
            2, TimeUnit.SECONDS);
}
assertThat(done).isTrue();
```

- `shutdown()`: ngừng nhận mới; queued/running tasks có thể hoàn thành.
- `awaitTermination`: chờ pool kết thúc **có deadline**.
- `shutdownNow()`: cố gắng interrupt running tasks và trả queued tasks; **không phải cách giết thread chắc chắn**.
- `Future.cancel(true)`: yêu cầu hủy **một task**; không đóng cả executor.
- `Future.get(timeout)`: chờ kết quả; không shutdown.
- `Thread.interrupt`: tín hiệu cooperative cancellation; task phải đáp ứng.

Một task `while(true)` catch `InterruptedException` rồi tiếp tục loop sẽ khiến forced shutdown không thành công. Không dùng deprecated/unsafe `Thread.stop()` để cưỡng bức. Sửa task để return/break khi có interrupt.

### 4.2. Không dùng `Thread.sleep` làm bằng chứng cleanup

```java
pool.shutdownNow();
Thread.sleep(100);
assertThat(Thread.activeCount()).isLessThan(10);
```

Đoạn trên là anti-pattern. JVM/JUnit/GC/Testcontainers có thể dùng thêm threads, nên `Thread.activeCount()` không đo đúng owner pool. `sleep` không chứng minh pool đã terminated.

Dùng:

```java
pool.shutdown();
assertThat(pool.awaitTermination(
        2, TimeUnit.SECONDS)).isTrue();
assertThat(pool.isTerminated()).isTrue();
```

Test muốn kiểm tra chính resource mình tạo, không assert toàn bộ JVM thread count phải bằng 0.

### 4.3. Cleanup khi test assertion fail

```java
ExecutorService owner =
        Executors.newSingleThreadExecutor();
try {
    // Có thể throw trước khi tới dòng shutdown...
}
finally {
    owner.shutdownNow();
    assertThat(owner.awaitTermination(
            2, TimeUnit.SECONDS)).isTrue();
}
```

Đây là snippet, chưa có imports; dùng code đặt cleanup trong `finally` hoặc `try-with-resources` wrapper để tránh rò ngay khi test fail.

### 4.4. Khi timeout vẫn chưa dừng

Nếu sau forced shutdown và second bounded await mà thread vẫn active:

1. Báo failure thay vì silent PASS.
2. Capture thread dump với PID **test JVM fork** đúng, không nhầm Maven parent process.
3. Kiểm tra blocking I/O, deadlocks, swallowed interruption và callback state.
4. Dùng CI job timeout như **last-resort containment**, không gọi `System.exit(0)` trong test để che lỗi.
5. Xác định task có thể tiếp tục thao tác external resource sau khi method kết thúc không.

## 5. Scheduler: cancel task khác shutdown scheduler

### 5.1. `ScheduledFuture`

```java
ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

try {
    ScheduledFuture<?> future = scheduler.schedule(
            () -> System.out.println("late"),
            1, TimeUnit.HOURS);

    assertThat(future.cancel(false)).isTrue();
}
finally {
    scheduler.shutdownNow();
    assertThat(scheduler.awaitTermination(
            2, TimeUnit.SECONDS)).isTrue();
}
```

Mốc một giờ giúp test cancellation không phụ thuộc timing. Cancel future ngăn **registration cụ thể** thực thi; shutdown scheduler giải phóng pool-owned threads. `cancel(false)` không interrupt task nếu nó đã bắt đầu; khi cần interrupt và method hỗ trợ, dùng `cancel(true)`.

### 5.2. Spring `@Scheduled`, `@EnableScheduling` và test context

Một `@Scheduled` method có thể được Spring tự đăng ký nếu `@EnableScheduling` active trong context. Nếu context cached, scheduler vẫn sống sau test class. Với tests không quan tâm scheduling, nên điều kiện hóa registration trước context refresh:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        name = "app.scheduling.enabled",
        havingValue = "true")
@EnableScheduling
class SchedulingSwitch {
}
```

Đây là snippet. `app.scheduling.enabled` là **custom property** do ứng dụng quản lý. Đừng thêm `spring.task.scheduling.enabled=false` rồi giả định Boot 3.5 có universal switch đó. `spring.task.scheduling.pool.size` điều chỉnh pool size, không phải disable switch.

### 5.3. Spring `ThreadPoolTaskScheduler`

Khi tạo `ThreadPoolTaskScheduler` bean:

- `setPoolSize(1)` chọn số worker scheduler threads.
- `setThreadNamePrefix("lab-scheduler-")` giúp debug ownership.
- `setRemoveOnCancelPolicy(true)` gỡ canceled tasks khỏi queue của `ScheduledThreadPoolExecutor` nếu hỗ trợ.
- `setWaitForTasksToCompleteOnShutdown(...)` chọn graceful wait vs task interruption/queue handling.
- `setAwaitTerminationSeconds(int)` giới hạn chờ khi shutdown.

Nếu `ScheduledFuture` thuộc riêng một test, nên cancel nó ở cleanup nếu context vẫn sống. Nếu `ThreadPoolTaskScheduler` là singleton Spring bean, **không gọi `scheduler.shutdown()` trong `@AfterEach`** khi test khác sẽ reuse same context.

### 5.4. Boot 3.5 shutdown properties

```properties
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=5s

spring.task.scheduling.shutdown.await-termination=true
spring.task.scheduling.shutdown.await-termination-period=5s

spring.task.execution.thread-name-prefix=task-
spring.task.scheduling.thread-name-prefix=scheduling-
```

Đây là documented Boot 3.5 property names. Chúng áp dụng cho **auto-configured** executors/schedulers liên quan. Nếu ứng dụng tự khai custom `ThreadPoolTaskExecutor` hoặc `ThreadPoolTaskScheduler`, những properties này **không nhất thiết** được apply; cấu hình shutdown của chính bean hoặc dùng Boot builders phù hợp.

Nuance Spring Framework 6.2: `waitForTasksToCompleteOnShutdown(true)` có thể khiến executor bỏ qua coordinated lifecycle stop phase và đợi ở destruction phase. `acceptTasksAfterContextClose`/`strictEarlyShutdown` cũng ảnh hưởng acceptance và shutdown ordering. Không bật flags tùy tiện khi tasks còn dùng DB/broker đang được destroy.

### 5.5. Virtual threads (không thuộc project Java 17)

Với Java 21+ và `spring.threads.virtual.enabled=true`, Boot có thể auto-configure `SimpleAsyncTaskExecutor`/`SimpleAsyncTaskScheduler` thay vì pool-based implementations, và một số pool properties không còn hiệu lực. Hãy kiểm tra executor thực tế; không dùng assertions dựa trên `ThreadPoolTaskExecutor` cho mọi runtime.

## 6. Spring ApplicationContext lifecycle và TestContext cache

### 6.1. Beans do Spring sở hữu

Spring gọi destruction callbacks (`@PreDestroy`, `DisposableBean.destroy`, configured destroy methods) khi context **thực sự đóng**. `ThreadPoolTaskExecutor` và `ThreadPoolTaskScheduler` là framework-managed components có lifecycle shutdown.

```java
@Configuration(proxyBeanMethods = false)
class ThreadConfig {

    @Bean
    ThreadPoolTaskExecutor worker() {
        ThreadPoolTaskExecutor pool =
                new ThreadPoolTaskExecutor();
        pool.setThreadNamePrefix("worker-test-");
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        return pool;
    }
}
```

Đây là snippet; phần file đầy đủ ở project mẫu. Nếu bean là Spring-managed, không cần/không nên một JUnit method tự đóng nó trong shared context.

### 6.2. `@DirtiesContext` không tự động là cleanup mọi thứ

`@DirtiesContext(classMode = AFTER_CLASS)` đánh dấu context dirty và yêu cầu loại khỏi cache/close sau test class. Nhưng:

- Nó không rollback records đã commit ở thread khác.
- Nó không xóa Redis keys/queues/files ngoài context.
- Nó có thể tăng chi phí Spring restart; không gắn cho mọi test.
- Khi các Spring tests chạy parallel và dùng chung context, dirtying có thể va chạm với class khác.
- Nó không thay việc dừng executor thủ công ngoài context.
- Không assert tại `@AfterAll` rằng context đã được đóng theo `AFTER_CLASS` nếu lifecycle listener đóng **sau** `@AfterAll`.

Khi muốn kiểm tra direct context-close behavior, tạo `AnnotationConfigApplicationContext` **bên trong một JUnit method** và dùng try-with-resources, như `SpringPoolLifecycleTest`.

### 6.3. Thứ tự bean destruction

Nếu một background task phụ thuộc DB, phải dừng producer/worker trước khi đóng DataSource. Dùng constructor dependencies, Spring `SmartLifecycle`, phối hợp phases hoặc explicit cleanup owner khi thực sự cần. Không cho một `@PreDestroy` bean gửi message qua connection factory đã destroy.

Context-owned beans được đóng theo dependency/lifecycle mechanics, không phải mặc định theo thứ tự field injection trong test.

## 7. JDBC: Connection.close() khác HikariDataSource.close()

### 7.1. Trả borrowed connection về pool

```java
try (Connection conn = dataSource.getConnection();
     PreparedStatement st =
             conn.prepareStatement("SELECT 1");
     ResultSet rs = st.executeQuery()) {

    assertThat(rs.next()).isTrue();
    assertThat(rs.getInt(1)).isEqualTo(1);
}
```

Với HikariCP pooled connection, `Connection.close()` trên **borrowed proxy** trả connection về pool (trên thường trình, physical connection có thể vẫn sống cho lần borrow tiếp). Nó **không đóng toàn bộ HikariDataSource**.

`PreparedStatement`/`ResultSet` cũng nên close trực tiếp. Không ỷ lại “đóng connection sẽ tự dọn hết child handles” khi lexical ownership đã rõ.

### 7.2. `JdbcTemplate`

`JdbcTemplate` tự quản lý JDBC resource acquisition/release theo Spring JDBC và transaction synchronization:

```java
Integer one = jdbc.queryForObject(
        "SELECT 1", Integer.class);
assertThat(one).isEqualTo(1);
```

Đây là snippet. `JdbcTemplate` không đồng nghĩa test tự sở hữu một pool. Nếu Spring Boot tạo `HikariDataSource` bean, hãy để context destroy pool; không gọi `hikari.close()` trong mỗi test method.

### 7.3. Hikari pool owner

Nếu test tạo HikariDataSource riêng:

```java
HikariDataSource pool = new HikariDataSource();
try {
    // cấu hình test URL, borrow, use, close Connection handles...
}
finally {
    pool.close();
}
```

Nếu Spring tự tạo pool qua `spring-boot-starter-jdbc`, chính context đóng pool. Đóng sớm ở một method có thể khiến class sau dùng cached context nhận `HikariPool ... has been closed`.

### 7.4. Hikari leak detection và MXBean

`HikariPoolMXBean.getActiveConnections()` giúp kiểm tra số borrowed connections còn active trong pool. Dùng nó làm assertion trong **môi trường cô lập**, không ở shared pool có scheduler/listener/parallel requests. Leak detection logs chỉ cảnh báo một connection được giữ quá lâu; không tự close leak và có thể cảnh báo false positive khi SQL chậm.

### 7.5. Transaction không thay resource cleanup

`@Transactional` test method thường rollback test-managed transaction ở test thread, nhưng không dọn executor, broker, HTTP client, container hay file handles. Async worker trên thread khác không tự tham gia transaction ấy. JUnit preemptive separate-thread timeout còn có thể làm code chạy ngoài test-managed transaction.

## 8. Testcontainers: class-owned khác context-owned

### 8.1. JUnit extension lifecycle

```java
@Testcontainers
class ExamplePostgresTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

- Static `@Container`: start một lần trước methods, stop sau class.
- Instance `@Container`: start/stop mỗi method.
- JUnit extension quản lý lifecycle riêng; Spring TestContext cache có thể sống **lâu hơn class**.
- Testcontainers JUnit extension documentation cảnh báo các tình huống parallel execution chưa được hỗ trợ như một hợp đồng mặc định; không tự parallelize container lifecycles không có isolation.

### 8.2. Bẫy stopped-container + cached Spring context

```text
Class A:
  JUnit starts static Postgres A
  Spring context X creates DataSource → A
  Test A PASS
  JUnit stops A after class

Class B:
  Spring cache reuses context X
  DataSource still points to A's old port
  JDBC query → Connection refused
```

Cách tránh:

1. Class-owned `@Container` kết hợp `@DirtiesContext(AFTER_CLASS)` khi context phụ thuộc container đó.
2. Khi Spring context được cache qua classes, ưu tiên container được khai như Spring bean, để lifecycle gắn với context.
3. Suite-wide singleton Testcontainer có thể start thủ công, nhưng **không** đồng thời đánh dấu `@Container` khiến JUnit stop sau class.
4. Không gọi `stop/start` trên shared container giữa methods và suy ra mapped port không đổi.
5. Không đóng container khi còn Spring beans dùng endpoint của nó.

### 8.3. Spring-managed container bean

Spring Boot 3.5 hỗ trợ:

```java
@TestConfiguration(proxyBeanMethods = false)
class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgres() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
```

Đây là snippet, file đầy đủ ở phần 9. Boot sẽ start container bean trước dependent beans và stop sau khi dependent beans được destroy. `@ServiceConnection` cung cấp dynamic JDBC connection details, không hard-code `localhost:5432`.

**Lưu ý:** Không đặt `@Testcontainers`/`@Container` trên cùng Spring-managed bean; đừng để cả JUnit extension và Spring cố quản lý một resource theo hai lifecycle khác nhau.

### 8.4. `@DirtiesContext(AFTER_CLASS)` với Spring-managed container

Trong bài mẫu có một integration class và annotation đó để context, Hikari pool và container được cleanup khi class kết thúc. Nếu suite lớn cần reuse context qua nhiều classes, bỏ dirty context khi phù hợp và để container bean sống cùng cached context. `@DirtiesContext` không phải cách xóa fixtures/rows thay cho scoped cleanup.

### 8.5. Không dùng Docker global cleanup

Không dùng `docker system prune --volumes` hoặc `docker rm -f` mọi containers trên shared runner. Resource ownership phải dựa vào container IDs/labels của test job. Nếu process bị kill, `@AfterAll` có thể không chạy; Testcontainers resource reaper/CI cleanup policy giúp dọn orphan resources theo môi trường nhưng không nên bị tắt chỉ để test xanh.

## 9. Dự án runnable-design Java 17 + Spring Boot 3.5

Bộ mẫu gồm **10 JUnit `@Test` methods**: 4 executor/scheduler JDK tests, 2 Spring pool lifecycle tests, 1 JUnit `@AutoClose` test, 3 PostgreSQL JDBC integration tests.

### 9.1. Cấu trúc

```text
resource-cleanup-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/cleanup/
    │   ├── CleanupLabApplication.java
    │   ├── LabThreadConfig.java
    │   └── OwnedExecutor.java
    ├── main/resources/
    │   ├── application.properties
    │   └── schema.sql
    └── test/java/com/example/cleanup/
        ├── OwnedExecutorTest.java
        ├── SpringPoolLifecycleTest.java
        ├── JupiterAutoCloseTest.java
        ├── PostgresTestConfig.java
        └── JdbcResourceIntegrationTest.java
```

Mọi public Java top-level type ở file cùng tên, package `com.example.cleanup`. Các tests không cần real HTTP server hoặc RabbitMQ; project dùng real PostgreSQL Testcontainers khi kiểm tra connection lifecycle. Không cần cloud credentials.

### 9.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>resource-cleanup-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-testcontainers</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>postgresql</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Boot 3.5 BOM quản lý JUnit Jupiter, Spring Framework 6.2, HikariCP và Testcontainers 1.x. Không trộn imports và Maven coordinates từ Testcontainers 2.x khi vẫn dùng BOM Testcontainers 1.x.

### 9.3. `CleanupLabApplication.java`

```java
// src/main/java/com/example/cleanup/CleanupLabApplication.java
package com.example.cleanup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CleanupLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CleanupLabApplication.class, args);
    }
}
```

Không bật `@EnableScheduling` ở sample. Có scheduler bean không có nghĩa Spring tự động scan và đăng ký `@Scheduled` methods.

### 9.4. `LabThreadConfig.java`

```java
// src/main/java/com/example/cleanup/LabThreadConfig.java
package com.example.cleanup;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
public class LabThreadConfig {

    @Bean("labExecutor")
    ThreadPoolTaskExecutor labExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("lab-executor-");
        executor.setWaitForTasksToCompleteOnShutdown(false);
        executor.setAwaitTerminationSeconds(2);
        return executor;
    }

    @Bean("labScheduler")
    ThreadPoolTaskScheduler labScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("lab-scheduler-");
        scheduler.setRemoveOnCancelPolicy(true);
        scheduler.setWaitForTasksToCompleteOnShutdown(false);
        scheduler.setAwaitTerminationSeconds(2);
        return scheduler;
    }
}
```

Hai beans do Spring context sở hữu. Các tests có thể tạo `AnnotationConfigApplicationContext` riêng rồi close và kiểm tra shutdown. Cấu hình không dùng `@Scheduled` cron, nên không có background job không mong muốn.

### 9.5. `OwnedExecutor.java` — wrapper AutoCloseable cho Java 17

```java
// src/main/java/com/example/cleanup/OwnedExecutor.java
package com.example.cleanup;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class OwnedExecutor implements AutoCloseable {

    private final ExecutorService executor;
    private final Duration timeout;

    public OwnedExecutor(Duration timeout) {
        this.timeout = Objects.requireNonNull(timeout);
        if (timeout.isNegative() || timeout.isZero()
                || timeout.toMillis() == 0) {
            throw new IllegalArgumentException(
                    "timeout must be positive milliseconds");
        }
        executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "owned-lab-worker"));
    }

    public <T> Future<T> submit(Callable<T> task) {
        return executor.submit(task);
    }

    public Future<?> submit(Runnable task) {
        return executor.submit(task);
    }

    public boolean isTerminated() {
        return executor.isTerminated();
    }

    @Override
    public void close() {
        executor.shutdown();
        try {
            long millis = timeout.toMillis();
            if (!executor.awaitTermination(
                    millis, TimeUnit.MILLISECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(
                        millis, TimeUnit.MILLISECONDS)) {
                    throw new IllegalStateException(
                            "Executor did not terminate");
                }
            }
        }
        catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted during shutdown", ex);
        }
    }
}
```

`close()` có hai pha bounded await: tối đa gần **2 × timeout**, nếu chưa tính scheduling overhead. Khi thread không hợp tác, test nhận cleanup failure rõ. Không cho rằng `shutdownNow()` chắc chắn dừng task đang block I/O hoặc nuốt interrupt.

### 9.6. `OwnedExecutorTest.java` — 4 tests

```java
// src/test/java/com/example/cleanup/OwnedExecutorTest.java
package com.example.cleanup;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class OwnedExecutorTest {

    @Test
    void completedTaskDoesNotLeakExecutor() throws Exception {
        OwnedExecutor owner =
                new OwnedExecutor(Duration.ofMillis(250));
        try (owner) {
            assertThat(owner.submit(() -> "OK")
                    .get(2, TimeUnit.SECONDS))
                    .isEqualTo("OK");
        }
        assertThat(owner.isTerminated()).isTrue();
    }

    @Test
    void blockedWorkerStopsOnInterruption() throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch gate = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();

        OwnedExecutor owner =
                new OwnedExecutor(Duration.ofMillis(150));

        try (owner) {
            owner.submit(() -> {
                started.countDown();
                try {
                    gate.await();
                }
                catch (InterruptedException ex) {
                    interrupted.set(true);
                    Thread.currentThread().interrupt();
                }
            });
            assertThat(started.await(
                    2, TimeUnit.SECONDS)).isTrue();
        }

        assertThat(interrupted.get()).isTrue();
        assertThat(owner.isTerminated()).isTrue();
    }

    @Test
    void closedExecutorRejectsNewWork() {
        OwnedExecutor owner =
                new OwnedExecutor(Duration.ofMillis(250));
        owner.close();

        assertThat(owner.isTerminated()).isTrue();
        assertThatThrownBy(
                () -> owner.submit(() -> { }))
                .isInstanceOf(RejectedExecutionException.class);
    }

    @Test
    void cancelledFutureAndSchedulerBothCleanUp()
            throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        try {
            ScheduledFuture<?> future = scheduler.schedule(
                    () -> { throw new AssertionError(
                            "must not run"); },
                    1, TimeUnit.HOURS);

            assertThat(future.cancel(false)).isTrue();
            assertThat(future.isCancelled()).isTrue();
        }
        finally {
            scheduler.shutdownNow();
            assertThat(scheduler.awaitTermination(
                    2, TimeUnit.SECONDS)).isTrue();
        }
        assertThat(scheduler.isTerminated()).isTrue();
    }
}
```

Không dùng `Thread.sleep`. `CountDownLatch` bảo đảm worker đã chạy trước khi thử shutdown, sau đó forced phase interrupt `gate.await()`. Task cooperative cancellation rời worker; pool `isTerminated()` khẳng định không còn active worker của owner.

### 9.7. `SpringPoolLifecycleTest.java` — 2 tests

```java
// src/test/java/com/example/cleanup/SpringPoolLifecycleTest.java
package com.example.cleanup;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

import static org.assertj.core.api.Assertions.assertThat;

class SpringPoolLifecycleTest {

    @Test
    void contextCloseShutsDownBothSpringPools()
            throws Exception {
        ThreadPoolTaskExecutor worker;
        ThreadPoolTaskScheduler scheduler;

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        LabThreadConfig.class)) {
            worker = context.getBean(
                    "labExecutor", ThreadPoolTaskExecutor.class);
            scheduler = context.getBean(
                    "labScheduler", ThreadPoolTaskScheduler.class);

            CountDownLatch executed = new CountDownLatch(1);
            worker.execute(executed::countDown);

            assertThat(executed.await(
                    2, TimeUnit.SECONDS)).isTrue();
            assertThat(worker.getThreadPoolExecutor()
                    .isShutdown()).isFalse();
        }

        assertThat(worker.getThreadPoolExecutor()
                .isShutdown()).isTrue();
        assertThat(scheduler.getScheduledThreadPoolExecutor()
                .isShutdown()).isTrue();
    }

    @Test
    void canceledTaskIsRemovedFromSchedulerQueue() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        LabThreadConfig.class)) {
            ThreadPoolTaskScheduler scheduler =
                    context.getBean(
                            "labScheduler",
                            ThreadPoolTaskScheduler.class);

            ScheduledFuture<?> future = scheduler.schedule(
                    () -> { },
                    Instant.now().plus(Duration.ofHours(1)));

            assertThat(future).isNotNull();
            assertThat(future.cancel(false)).isTrue();

            assertThat(scheduler.getScheduledThreadPoolExecutor()
                    .getQueue()).isEmpty();
        }
    }
}
```

Spring tự init/destroy beans do context sở hữu. `setRemoveOnCancelPolicy(true)` khiến canceled delayed task rời queue. Test không assume toàn Spring TestContext cache tự close sau mỗi JUnit method; nó tự tạo **context riêng** rồi close có chủ đích.

### 9.8. `JupiterAutoCloseTest.java` — 1 test

```java
// src/test/java/com/example/cleanup/JupiterAutoCloseTest.java
package com.example.cleanup;

import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AutoClose;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class JupiterAutoCloseTest {

    private static final AtomicBoolean CLOSED =
            new AtomicBoolean();

    @AutoClose
    AutoCloseable owned = () -> CLOSED.set(true);

    @BeforeAll
    static void reset() {
        CLOSED.set(false);
    }

    @Test
    void resourceRemainsOpenDuringMethod() {
        assertThat(CLOSED.get()).isFalse();
        assertThat(owned).isNotNull();
    }

    @AfterAll
    static void closureWasCalled() {
        assertThat(CLOSED.get()).isTrue();
    }
}
```

`@AutoClose` instance field được đóng sau method trong JUnit `PER_METHOD` lifecycle, nên `@AfterAll` có thể kiểm tra flag. Không dùng static mutable flag làm cross-class fixture trong ứng dụng lớn; đây chỉ là demo một class/one method và reset ở `@BeforeAll`.

### 9.9. `application.properties`, `schema.sql`

```properties
# src/main/resources/application.properties
spring.sql.init.mode=always
```

```sql
-- src/main/resources/schema.sql
CREATE TABLE lab_notes (
    note_id VARCHAR(72) PRIMARY KEY,
    body VARCHAR(200) NOT NULL
);
```

`spring.sql.init.mode=always` là lựa chọn lab khi dùng real PostgreSQL container. Project production nên dùng migrations có kiểm soát, không áp schema-create script tùy tiện lên DB thật.

### 9.10. `PostgresTestConfig.java` — Spring-owned Testcontainer

```java
// src/test/java/com/example/cleanup/PostgresTestConfig.java
package com.example.cleanup;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgres() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
```

Không dùng `@Testcontainers` hoặc `@Container`: PostgreSQL là **Spring bean**. Boot 3.5 quản lý start trước dependent beans và stop sau khi dependent beans được destroy, tránh mismatch giữa JUnit class-scoped container và cached ApplicationContext.

### 9.11. `JdbcResourceIntegrationTest.java` — 3 tests

```java
// src/test/java/com/example/cleanup/JdbcResourceIntegrationTest.java
package com.example.cleanup;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.UUID;

import com.zaxxer.hikari.HikariDataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Import(PostgresTestConfig.class)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class JdbcResourceIntegrationTest {

    @Autowired
    HikariDataSource hikari;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void borrowedConnectionIsReturnedToPool()
            throws Exception {
        Connection borrowed = hikari.getConnection();

        try (borrowed) {
            assertThat(borrowed.isClosed()).isFalse();
            assertThat(borrowed.getMetaData()
                    .getDatabaseProductName())
                    .isEqualTo("PostgreSQL");
        }

        assertThat(borrowed.isClosed()).isTrue();
        assertThat(hikari.getHikariPoolMXBean()
                .getActiveConnections()).isZero();
        assertThat(hikari.isClosed()).isFalse();
    }

    @Test
    void closesStatementResultSetAndConnection()
            throws Exception {
        try (Connection connection = hikari.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement("SELECT 7");
             ResultSet rows = statement.executeQuery()) {
            assertThat(rows.next()).isTrue();
            assertThat(rows.getInt(1)).isEqualTo(7);
            assertThat(rows.next()).isFalse();
        }

        assertThat(hikari.getHikariPoolMXBean()
                .getActiveConnections()).isZero();
    }

    @Test
    void cleansOnlyItsOwnCommittedRow() {
        String id = UUID.randomUUID().toString();

        try {
            jdbc.update(
                    "INSERT INTO lab_notes(note_id, body) "
                            + "VALUES (?, ?)",
                    id, "test-owned");

            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM lab_notes "
                            + "WHERE note_id = ?",
                    Integer.class, id);

            assertThat(count).isEqualTo(1);
        }
        finally {
            jdbc.update(
                    "DELETE FROM lab_notes WHERE note_id = ?", id);
        }

        Integer remaining = jdbc.queryForObject(
                "SELECT COUNT(*) FROM lab_notes "
                        + "WHERE note_id = ?",
                Integer.class, id);

        assertThat(remaining).isZero();
        assertThat(hikari.isClosed()).isFalse();
    }
}
```

Không gọi `hikari.close()` trong tests vì pool thuộc Spring context. `@DirtiesContext(AFTER_CLASS)` đóng context khi class kết thúc; Spring Boot managed container shutdown chạy sau bean destruction. `getActiveConnections()==0` được dùng trong **demo cô lập** (JUnit methods không chạy parallel, không có background DB client); không copy vào shared pool có active listeners.

### 9.12. Tổng số test và lệnh chạy

| Test class | Số `@Test` methods | Cần Docker? | Hợp đồng |
| --- | ---: | --- | --- |
| `OwnedExecutorTest` | 4 | Không | Bounded shutdown/cancellation |
| `SpringPoolLifecycleTest` | 2 | Không | Spring bean shutdown, scheduler queue |
| `JupiterAutoCloseTest` | 1 | Không | JUnit resource field close |
| `JdbcResourceIntegrationTest` | 3 | Có | JDBC borrowed handles, pool, data cleanup |
| **Tổng** | **10** | Full suite cần Docker | Method/context/container cleanup |

```bash
java -version
mvn -version

# 7 JUnit methods không cần Docker:
mvn -B -ntp -Dtest=OwnedExecutorTest,SpringPoolLifecycleTest,JupiterAutoCloseTest test

# 3 JDBC/PostgreSQL integration tests cần Docker:
docker version
docker info
mvn -B -ntp -Dtest=JdbcResourceIntegrationTest test

# 10 methods:
mvn -B -ntp test
```

Đây là hướng dẫn **để người học tự chạy**, không phải báo cáo rằng Maven/Docker đã thực thi trong lúc soạn bài. Không dựng console log `BUILD SUCCESS` giả; output phụ thuộc JDK, CI runner và image pull.

## 10. Các client/connection khác phải được dọn đúng owner

### 10.1. RabbitMQ và Spring AMQP

Nếu Spring context tạo `CachingConnectionFactory` và listener containers, để context quản lý. Nếu test tự tạo connection factory, nó phải destroy/close factory khi toàn bộ listeners đã stop.

Thứ tự:

```text
stop new message production (if test owns it)
  → stop listener container
  → bounded wait for in-flight handlers/ACKs
  → close test-owned client/connection factory
  → clean test-owned queue/vhost
  → stop broker container at owner lifecycle
```

Không đóng shared Spring connection factory ở `@AfterEach` khi class khác còn sử dụng context. `RabbitTemplate.convertAndSend` không bảo đảm consumer đã xử lý message, nên việc “send xong” không phải cleanup guarantee.

### 10.2. Kafka producers/consumers

`KafkaConsumer` không thread-safe cho arbitrary concurrent calls. Consumer thread thường sở hữu `poll()` và `close()` trong `finally`; thread khác có thể `wakeup()` để đánh thức `poll()`. Sau đó join bounded; producer có `flush()`/`close(Duration)` khi test tự tạo.

Nếu Spring Kafka quản lý `KafkaMessageListenerContainer` và producer factory, context là owner. Không tự đóng broker của test khác trước khi listener stop. Dữ liệu message/topic/consumer group offsets có external lifecycle riêng: stop client không xóa topics/offsets.

### 10.3. HTTP client, server, Reactor Netty

- `com.sun.net.httpserver.HttpServer` tạo trong test: `server.stop(0)` ở `@AfterEach` hoặc `finally`.
- Apache `CloseableHttpClient` do test tạo: `close()`.
- Java `HttpClient` trên Java 17 không có lifecycle close giống các API mới; kiểm tra JDK implementation, đừng copy code của Java 21+.
- Reactor Netty `ConnectionProvider`/`LoopResources` do test tự tạo: `dispose()` hoặc await `disposeLater()` theo API/version.
- Spring-managed `WebClient` thường chia sẻ Reactor resources và không phải owner của global event loops; đừng dispose global resources trong method nếu classes khác còn dùng.
- Local HTTP stub dùng port 0 và dynamic URL, tránh hard-code port 8080/9999.

### 10.4. Redis và R2DBC

`RedisConnectionFactory` Spring-managed tự destroy theo context; borrowed `RedisConnection` hoặc cursor/stream phải close theo API. Không dùng `FLUSHALL` như cleanup cho một test trên Redis shared.

R2DBC `Connection.close()` trả reactive Publisher, không phải JDBC `AutoCloseable`; phải subscribe/verify completion theo reactive contract. `StepVerifier` hoàn thành subscription không đồng nghĩa network connection pool/container đã đóng. Phân biệt release connection lease và close pool owner.

### 10.5. Filesystem và object store

- Dùng `@TempDir`/unique filename, không một `./target/report.json` cho mọi tests concurrent.
- Close streams trước khi dọn thư mục.
- Với S3/object store, prefix theo CI run ID/test ID và cleanup đúng prefix, không delete toàn bucket.
- Retry cleanup nếu external API eventual consistency phù hợp, nhưng không dùng retry vô hạn hoặc che lỗi quyền.

## 11. Parallel tests và cached contexts: các tình huống nguy hiểm

### 11.1. `@DirtiesContext` với parallel classes

Một class có thể đóng cached context trong lúc class khác vẫn dùng nếu chạy song song không điều phối. Spring TestContext docs khuyến cáo cẩn trọng với `@DirtiesContext`, bean overrides/`@MockitoBean`, global state và shared external resources. Nếu cần context-close after-class, serialize các classes liên quan hoặc tách context identity.

### 11.2. `@ResourceLock` không phải distributed lock

JUnit `@ResourceLock` có thể phối hợp tests trong cùng Jupiter test plan, nhưng không khóa giữa Surefire JVM forks, Maven parallel modules hay CI jobs. Dùng namespace/IDs riêng để cleanup files/DB rows/queue đúng owner.

### 11.3. Connection leak vs data leak

- Một test insert rows rồi `Connection.close()`: connection đã trả pool nhưng data có thể **đã commit** và vẫn ở database.
- Một test xóa rows trong `@AfterEach` nhưng quên `Connection.close()`: data sạch nhưng pool leak.
- Một test `@Transactional` rollback nhưng background scheduler gửi broker message: DB test thread rollback **không** cancel message.
- Một test `@DirtiesContext` nhưng static `ExecutorService` tạo bằng `new` ngoài Spring vẫn sống: context close không biết resource đó.

Cần kiểm thử **từng loại state/resource riêng**, không gộp chúng thành một flag “test sạch”.

### 11.4. Thứ tự stop khi DB/broker tham gia

Khi worker còn có thể gọi DB/broker:

1. Disable new work/cron trigger.
2. Cancel/stop listeners và producers.
3. Await bounded in-flight work.
4. Shutdown executor/scheduler và xác nhận.
5. Close client/pool connections.
6. Stop backing container.
7. Cleanup test-owned external data theo ownership policy trước container stop nếu cần truy cập lại provider.

Spring Boot managed containers hỗ trợ order của dependent bean destruction, nhưng task tự tạo ngoài Spring cần explicit cleanup.

## 12. Chẩn đoán rò resource và test hanging

| Triệu chứng | Nguyên nhân có thể | Bằng chứng/khắc phục |
| --- | --- | --- |
| Maven không thoát | Non-daemon thread chưa shutdown | Thread dump test JVM, executor `isTerminated` |
| Spring task vẫn tick | Cached context hoặc manually created scheduler | Cancel ScheduledFuture, disable registration, context lifetime |
| `TaskRejectedException` class kế tiếp | Method trước shutdown shared Spring executor | Dùng owner context, không close ở `@AfterEach` |
| `Connection refused` sau class A | @Container stopped nhưng cached context reused | Spring-managed container hoặc dirty context |
| Hikari active count tăng | Borrowed JDBC handles chưa close | Try-with-resources, Hikari MXBean test-only |
| Hikari pool đã closed | Test method gọi `hikari.close()` quá sớm | Let Spring destroy bean |
| JVM connection/socket leak | HTTP/Kafka/gRPC clients không close | Explicit client owner teardown |
| Docker containers còn lại | Resource reaper/lifecycle thất bại | Test-owned IDs/labels, không global prune |
| `@AfterAll` không thấy pool shutdown | Spring context vẫn sống trong cache | Manual context close test |
| Tests chỉ fail khi chạy parallel | Shared context/resource cleanup race | Unique namespace, selective serialization |
| Teardown timeout | Task không cooperative | bounded await + diagnostic, fix worker |
| Broker listener vẫn nhận sau test | Context/listener still active | Stop listener, await in-flight |
| File không xóa được | Open stream/file handle | Close handle trước TempDir cleanup |

### 12.1. Khi cần thread dump

Dùng `jcmd <test-JVM-PID> Thread.print` hoặc `jstack <test-JVM-PID>` (trên JVM hỗ trợ) để tìm thread name do app/test tạo. Maven Surefire có thể fork JVM; PID của Maven parent không phải PID test worker. Không dùng `System.exit(0)` trong JUnit chỉ để “test process thoát”.

### 12.2. `shutdownNow()` có thể không cứu được task

Task chờ I/O không interruption-aware hoặc deadlock có thể sống sau forced shutdown. Sau bounded timeout, fail test và cung cấp diagnostic. CI timeout có thể kill whole fork như tuyến phòng vệ cuối, nhưng đó không phải bằng chứng graceful cleanup.

### 12.3. Leak detection không tự sửa lỗi

Hikari leak detection cảnh báo borrowed connection giữ quá lâu, không tự đóng connection đó. Một query chậm có thể trigger warning rồi cuối cùng release hợp lệ; quan sát stack/checkout duration và pool active state trước khi kết luận.

### 12.4. Docker orphan cleanup phải scoped

Nếu job bị kill cứng, `@AfterAll` không thể bảo đảm chạy. Testcontainers resource reaper và CI cleanup policy theo owner IDs/labels có thể hỗ trợ. Không chạy `docker system prune --volumes` trên shared Docker daemon và không xóa volumes/containers của người khác.

## 13. CI và khả năng vận hành

### 13.1. Các cấp tài nguyên

```text
Method resources → close in @AfterEach/try-with-resources
Class resources  → close in @AfterAll
Spring beans     → close on ApplicationContext destruction
Container bean   → stop after dependent Spring beans
CI job resources → cleanup after test process/timeout
External data    → delete only test-owned namespace/IDs
```

### 13.2. GitHub Actions minh họa

```yaml
name: Resource Cleanup Tests

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 20

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Docker preflight
        run: |
          docker version
          docker info --format 'Engine={{.ServerVersion}}'
      - name: JUnit + PostgreSQL integration
        run: mvn -B -ntp test
      - name: Upload Surefire reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: cleanup-reports
          path: target/surefire-reports/
          if-no-files-found: ignore
```

Container integration job cần Docker-compatible daemon, mapped ports và quyền tạo container. Nếu thiếu Docker, mandatory integration tests là **environment failure**, không silent skip. Với untrusted PR, tránh chia sẻ privileged Docker socket/secrets ngoài policy.

### 13.3. Forks và CI shards

`forkCount=2` nghĩa là hai JVM có Spring cache/static riêng, nhưng vẫn có thể dùng chung external database nếu cấu hình trỏ cùng URL. `@ResourceLock` của JUnit không khóa xuyên fork. Với external DB/broker/Redis trên CI, dùng namespace theo run ID/fork/test ID và scoped cleanup.

### 13.4. Mức độ sạch có thể đo được

Một suite tốt không chỉ pass business assertions mà còn:

- JUnit worker không giữ non-daemon executors do test tạo.
- Spring-owned pools có thể shutdown khi context close.
- Pool connections đã borrowed được trả về.
- Test-specific scheduler tasks được cancel.
- Container lifecycle không lệch context cache.
- Temp files/queues/rows nằm trong owner namespace.
- Không gọi production endpoints hoặc xóa tài nguyên shared.
- Khi cleanup fail, báo rõ FAIL/ERROR thay vì nuốt exceptions.

## 14. Các lỗi cần tránh

**Lỗi 1: `Future.get()` xong là pool đã đóng.** Sai; `get` chỉ chờ task, không shutdown.

**Lỗi 2: `shutdownNow()` chắc chắn giết mọi thread.** Sai; best-effort interrupt, worker phải cooperative.

**Lỗi 3: Dùng `Thread.sleep(500)` rồi `Thread.activeCount()`.** Không đo owner resource, timing flaky.

**Lỗi 4: Gọi shutdown Spring executor bean ở `@AfterEach`.** Cached context/test khác vẫn cần bean.

**Lỗi 5: `@DirtiesContext` tự dọn Redis/DB data.** Nó đóng/loại context, không dọn mọi external side effect.

**Lỗi 6: `Connection.close()` đóng toàn Hikari pool.** Với borrowed proxy, close trả connection về pool.

**Lỗi 7: Đóng Hikari pool sau mỗi query.** Pool là Spring singleton được context quản lý, sẽ làm tests sau fail.

**Lỗi 8: `@Transactional` thay thế shutdown broker/executor.** DB rollback không quản lý external thread/socket.

**Lỗi 9: Static `@Container` sống tới hết JVM.** Với JUnit extension nó stop sau class.

**Lỗi 10: Spring context luôn close sau class.** Context cache có thể reuse giữa classes.

**Lỗi 11: Spring-managed container vừa gắn `@Container`.** Hai lifecycle owners mâu thuẫn.

**Lỗi 12: `@AfterAll` assert Spring-managed pool shutdown trước listener đóng context.** Cần kiểm tra lifecycle timing hoặc dùng manual context close test.

**Lỗi 13: Cleanup toàn bộ DB/queue để “chắc sạch”.** Có thể xóa dữ liệu test khác đang chạy parallel.

**Lỗi 14: Kafka consumer `close()` từ bất kỳ thread khi `poll()` đang dùng client.** Phải có ownership/`wakeup` và bounded join.

**Lỗi 15: Tắt Testcontainers resource reaper để né lỗi Docker.** Có thể để orphan resources.

**Lỗi 16: Dùng `@Timeout` thay cleanup.** Timeout không bảo đảm stop unresponsive worker/container.

**Lỗi 17: Không close stream trước dọn `@TempDir`.** Dễ fail trên Windows do open file handles.

**Lỗi 18: Dùng Boot task properties rồi nghĩ custom pool tự nhận.** Custom bean phải cấu hình trực tiếp hoặc dùng builder đúng.

## 15. Bài tập thực hành

1. Bỏ `close()` của `OwnedExecutor` trong nhánh demo và quan sát thread còn sống; khôi phục wrapper để không treo runner.
2. Viết task blocked ở `CountDownLatch.await()`, kiểm tra `shutdownNow` đánh dấu interrupted và `isTerminated`; không dùng sleep cố định.
3. Dùng `ScheduledFuture.cancel(false)` trên task đặt một giờ sau, kiểm tra queue với/không có `setRemoveOnCancelPolicy(true)`.
4. Tạo `AnnotationConfigApplicationContext` và assert Spring-owned pool shutdown **sau** `close()`, không trước.
5. Borrow 1 JDBC connection, dùng try-with-resources, assert Hikari active 0. Thử cố tình giữ handle (chỉ trên container test-only) để hiểu pool exhaustion.
6. Đóng một Spring-managed HikariDataSource sớm trong nhánh demo và quan sát các lần query sau thất bại; khôi phục đúng owner.
7. Thử static `@Container` và context reuse mismatch ở hai classes; chuyển sang managed `@Bean` container hoặc `@DirtiesContext` đúng scope.
8. Tạo Rabbit listener test và stop listener trước khi đóng broker container; assert không còn handler chạy sau teardown.
9. Chạy hai HTTP stubs cùng lúc trên port 0, stop đúng từng server; không hard-code port chung.
10. Tạo Kafka consumer worker và dùng `wakeup` để dừng `poll`; join bounded và close trên owning thread.
11. Tách integration job và unit job trong CI; báo “Docker unavailable” là lỗi môi trường, không biến thành PASS.
12. Bật Surefire 2 forks và dùng run/fork namespace để external cleanup không xóa resources của fork khác.

## 16. Câu hỏi tự kiểm tra

**1.** `Future.get()` xong có làm executor tự shutdown? — **Không.**

**2.** `shutdownNow()` luôn terminate task? — **Không; task cần hỗ trợ interrupt/cancellation.**

**3.** Java 17 `ExecutorService` dùng được try-with-resources trực tiếp không? — **Chưa; dùng wrapper/finally.**

**4.** Spring-owned `ThreadPoolTaskExecutor` đóng ở `@AfterEach`? — **Không, context là owner.**

**5.** `Connection.close()` trên Hikari borrowed handle làm gì? — **Trả về pool; không close HikariDataSource.**

**6.** `@Transactional` rollback có dừng scheduler thread? — **Không.**

**7.** `@DirtiesContext` có tự xóa rows đã commit? — **Không.**

**8.** Static `@Container` với JUnit extension stop khi nào? — **Sau test class.**

**9.** Spring-managed `@Bean PostgreSQLContainer` stop khi nào? — **Khi context close, sau dependent beans.**

**10.** `@AutoClose` instance field với `PER_METHOD` close khi nào? — **Sau mỗi method.**

**11.** Vì sao `Thread.activeCount()==0` không phải goal? — **JVM/JUnit/GC threads vẫn có thể sống.**

**12.** Nếu teardown fail nhưng test assertion pass, nên báo gì? — **Cleanup failure, không silent PASS.**

**13.** Một container bị stop trước cached DataSource gây gì? — **Stale connection/connection refused ở class sau.**

**14.** Vì sao không global Docker prune trong cleanup? — **Có thể xóa resources của jobs khác.**

## 17. Checklist trước khi merge

- [ ] Mọi executor/scheduler/connection/container có owner xác định.
- [ ] Test-created executor shutdown + bounded await.
- [ ] Cleanup still runs khi assertion throw.
- [ ] Task xử lý interruption thay vì nuốt rồi loop.
- [ ] Future scheduler test-owned được cancel khi không cần.
- [ ] Spring-managed pool không bị đóng sớm bởi method khác.
- [ ] Context cache và `@DirtiesContext` được dùng có chủ đích.
- [ ] Không nhầm auto-configured task shutdown properties với custom beans.
- [ ] JDBC borrowed handles, statements, result sets được close bằng try-with-resources.
- [ ] Hikari pool owner đúng: Spring vs test-created.
- [ ] Transaction rollback không bị coi là cleanup cho external resources.
- [ ] Testcontainers lifecycle khớp context: class-owned vs Spring-managed.
- [ ] Spring-managed container được stop sau dependent beans.
- [ ] Không mix `@Container` extension với managed bean owner.
- [ ] Không stop resource khi class khác/fork khác đang sử dụng.
- [ ] External data cleanup scoped theo UUID/namespace.
- [ ] HTTP mocks đóng server và dùng random port.
- [ ] Kafka/Rabbit listeners stopped/awaited trước client/container shutdown.
- [ ] Không dùng `Thread.sleep` hoặc global thread count làm bằng chứng chính.
- [ ] Bounded cleanup timeout có failure diagnosis rõ.
- [ ] CI không dùng production credentials, không global prune.
- [ ] Unit/integration/skipped/environment failures được phân biệt.
- [ ] Không tuyên bố code đã chạy nếu mới chỉ soạn project sample.

## 18. Tài liệu chính thức

- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): executor/scheduler implementations.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.task.execution.shutdown.*` và `spring.task.scheduling.shutdown.*`.
- [Spring Framework 6.2 — ExecutorConfigurationSupport](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html): shutdown/drain/await.
- [Spring Framework 6.2 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): managed executor lifecycle.
- [Spring Framework 6.2 — ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html): scheduled futures và remove-on-cancel.
- [Spring Framework — TestContext Cache](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): reused contexts và JVM scope.
- [Spring Framework — Parallel Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html): dirty/shared contexts và parallelism.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection`, managed container beans và shutdown order.
- [Testcontainers — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): static vs instance `@Container` lifecycle.
- [JUnit 5.12 — User Guide](https://docs.junit.org/5.12.0/user-guide/): lifecycle callbacks, `@AutoClose`.
- [Java 17 — ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown/await.
- [Java 17 — ScheduledExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): scheduling/cancellation.
- [Java 17 — Connection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): JDBC `AutoCloseable`.
- [HikariCP repository/documentation](https://github.com/brettwooldridge/HikariCP): pool lifecycle/metrics/leak detection.

**Kết luận:** Đóng đúng resource được quyết định bởi *ai sở hữu nó và ai còn dùng nó*, không phải đóng càng nhiều càng tốt. Test tạo executor phải shutdown/await bounded; test hẹn lịch cần cancel future; JDBC caller trả borrowed handles; Spring context đóng Hikari/executor/scheduler beans; container Spring-managed dừng **sau** các dependent beans. Kết hợp ownership-scoped cleanup, assertions về termination/connection state và lifecycle đồng bộ với TestContext cache để suite không treo, không dùng stale connections, không phá data của tests chạy song song.