# Đăng ký client, connection pool và executor như tài nguyên do container quản lý

## 1. Vì sao tài nguyên dùng chung phải thuộc về ApplicationContext?

Một ứng dụng Spring Boot thường sở hữu nhiều tài nguyên có vòng đời vượt quá một lời gọi method: HTTP client duy trì connection pool, JDBC DataSource, client Redis hoặc message broker, executor chạy tác vụ nền, scheduler, file watcher, cache và thread do thư viện tạo. Tạo đối tượng chỉ là một nửa vấn đề; nửa còn lại là **ai sẽ dừng sử dụng, đợi công việc còn dở và đóng tài nguyên khi ứng dụng kết thúc?**

Nếu tài nguyên được tạo trong controller/service bằng lệnh `new` hoặc một factory tùy ý nhưng không có owner rõ ràng, chương trình có thể:

- Giữ thread non-daemon khiến JVM khó kết thúc.
- Tạo nhiều connection pools tới cùng database, hết số kết nối cho phép.
- Giữ HTTP response stream/socket không được trả về pool.
- Đóng client quá sớm khi một request khác còn đang sử dụng.
- Để background task chạy sau khi `DataSource` đã bị destroy.
- Rò classloader/thread qua nhiều lần tạo `ApplicationContext` trong test.
- Mất task khi shutdown dù đã trả HTTP 202 Accepted.
- Không thu hồi resource khi khởi tạo bean thất bại giữa chừng.

**Giải pháp ưu tiên trong Spring Boot:** đưa tài nguyên dùng chung vào **Spring-managed beans** hoặc tận dụng tài nguyên mà Spring Boot **auto-configure**; người dùng chỉ inject và mượn resource, còn Spring container nắm quyền điều phối lifecycle.

Điều đó không có nghĩa container sẽ tự đóng mọi thứ nằm trong field của một object. Bạn vẫn phải chọn **owner duy nhất**, khai báo cleanup callback, xác định chỗ đóng per-operation handles, thiết kế stop/await cho tác vụ nền và kiểm tra shutdown thực sự.

Bài học dùng **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**. Ví dụ hoàn chỉnh sẽ quản lý cùng lúc Apache HTTP client, HikariCP connection pool và `ThreadPoolTaskExecutor`.

## 2. Tư duy ownership: ai tạo, ai mượn, ai đóng?

Một resource thường có hai cấp vòng đời:

1. **Cấp ứng dụng:** pool và client được tạo một lần, chia sẻ cho nhiều service/request, đóng khi owner (thường là `ApplicationContext`) dừng.
2. **Cấp thao tác:** connection mượn từ pool, JDBC statement, HTTP response, file stream được đóng ngay khi thao tác kết thúc.

| Resource/handle | Phạm vi bình thường | Ai đóng? |
| --- | --- | --- |
| `CloseableHttpClient` / shared client pool | Singleton ứng dụng | Owner Spring bean khi context đóng |
| `HikariDataSource` | Singleton ứng dụng | Spring Boot/container khi context đóng |
| JDBC `Connection` mượn từ Hikari | Một thao tác/transaction | Người mượn hoặc transaction framework trả về pool |
| `Statement` / `ResultSet` | Một truy vấn | Code thao tác, thường qua try-with-resources |
| HTTP response/response body stream | Một HTTP call | Caller/response handler theo API client |
| `ThreadPoolTaskExecutor` | Singleton ứng dụng | Spring lifecycle/destroy callback |
| `ExecutorService` tạo riêng | Theo owner tự định nghĩa | Chính owner, dùng shutdown/await |
| `ThreadPoolTaskScheduler` | Singleton ứng dụng | Spring lifecycle/destroy callback |
| File stream | Một hoạt động đọc/ghi | try-with-resources |
| `JdbcTemplate`/repository | Bean facade dùng DataSource | Thường không đóng shared DataSource |

**Quan trọng:** gọi `connection.close()` trên connection lấy từ Hikari thường **trả connection về pool**, không phá hủy Hikari pool. Ngược lại, gọi `hikariDataSource.close()` là đóng **cả pool**, có thể làm những request khác thất bại.

### 2.1. One owner, many borrowers

Một client có thể được inject vào nhiều services, nhưng không vì thế mà mỗi service có quyền gọi `close()`. Đặt ownership ở:

- Bean resource riêng có destroy callback; hoặc
- Một wrapper bean duy nhất sở hữu resource bên trong; hoặc
- Auto-configuration của Spring Boot/ thư viện tích hợp.

**Không** vừa đăng ký raw client thành bean có destroy callback, vừa đăng ký wrapper cũng đóng **chính client đó**, trừ khi bạn thực sự xây dựng và kiểm chứng policy shared ownership đặc biệt.

### 2.2. Không dùng static global một cách tùy tiện

```java
private static final ExecutorService EXECUTOR =
        Executors.newFixedThreadPool(8);
```

Đây là snippet phản ví dụ. Pool static sống theo process, không gắn chặt với một Spring context. Khi test/redeploy tạo nhiều contexts trong cùng JVM, context nào sẽ đóng nó? Nếu một context đóng, các context khác dùng pool này có thể lỗi; nếu không ai đóng, thread có thể tiếp tục sống.

Dùng singleton **trong phạm vi ApplicationContext** sẽ rõ ràng hơn cho hầu hết service Spring Boot.

## 3. Spring quản lý lifecycle của bean qua những cơ chế nào?

```text
SpringApplication.run(...)
     |
Tạo ApplicationContext
     |
Nạp bean definitions
     |
ApplicationContext.refresh()
     |
Tạo singleton không lazy và inject dependencies
     |
Gọi init callbacks / BeanPostProcessors
     |
Bean được service/runner/controller sử dụng
     |
Ứng dụng shutdown
     |
Coordinated stop: SmartLifecycle / LifecycleProcessor
     |
Destroy các singleton beans
     |
@Bean(destroyMethod="close"), @PreDestroy, DisposableBean ...
     |
ApplicationContext.close() kết thúc
```

Đây là giản đồ khái niệm. Bean `@Lazy` chưa từng được tạo không nhất thiết có instance để destroy. Với executor/background jobs, coordinated stop và destroy có hợp đồng khác nhau.

### 3.1. @Bean(destroyMethod = "close")

```java
@Bean(destroyMethod = "close")
CloseableHttpClient httpClient() {
    return HttpClients.createDefault();
}
```

Snippet trong class `@Configuration`, cần import Apache HttpClient 5 và `@Bean`. Spring sẽ gọi `close()` khi bean này bị destroy. Với resource có method đúng, đây là cách biểu diễn contract rất rõ.

Spring Framework cũng hỗ trợ **inferred destroy method** đối với `@Bean`, thường nhận biết các method công khai như `close()` và `shutdown()` hoặc `AutoCloseable`. Tuy vậy ghi `destroyMethod` tường minh có thể khiến ownership dễ đọc, dễ review hơn.

### 3.2. @PreDestroy

```java
@Component
class ResourceOwner {

    private final ExecutorService pool =
            Executors.newFixedThreadPool(2);

    @PreDestroy
    void cleanup() {
        pool.shutdown();
    }
}
```

Đây là snippet trong Spring Boot 3.x, import `jakarta.annotation.PreDestroy`. Nó minh họa cách bean owner tự đóng private field. Nhưng `shutdown()` không đợi task kết thúc; để production-safe còn cần bounded await, cancellation policy và xử lý unfinished jobs.

### 3.3. DisposableBean và SmartLifecycle

`DisposableBean.destroy()` là callback của Spring, còn `SmartLifecycle.stop(Runnable callback)` cho phép tham gia **phối hợp dừng** theo phase trước destruction. Khi service có producer/consumer chạy liên tục, `SmartLifecycle` thường thể hiện việc dừng nhận công việc và báo đã dừng rõ hơn việc nhét tất cả vào `@PreDestroy`.

Tác vụ chạy trong executor có thể tiếp tục sau khi một service bean đã destroy nếu executor không được phối hợp. Vì vậy cấu hình bean destroy là **điều kiện cần**, không phải luôn đủ cho orderly graceful shutdown.

## 4. Đăng ký Apache HTTP client dùng chung như một bean

Apache HttpComponents 5 có `CloseableHttpClient`, có thể giữ connection manager/pool. Một cấu hình cơ bản:

```java
@Configuration(proxyBeanMethods = false)
class PartnerClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient partnerHttpClient() {
        PoolingHttpClientConnectionManager manager =
                PoolingHttpClientConnectionManagerBuilder.create()
                        .setMaxConnTotal(20)
                        .setMaxConnPerRoute(5)
                        .build();

        return HttpClients.custom()
                .setConnectionManager(manager)
                .build();
    }
}
```

Đây là **class snippet**, cần import `CloseableHttpClient`, `HttpClients`, `PoolingHttpClientConnectionManager`, `PoolingHttpClientConnectionManagerBuilder` và các Spring annotations. Phần thực hành sau có mã đầy đủ.

**Ý nghĩa:**

- `@Bean` để Spring quản lý một instance dùng chung.
- Pool giới hạn tổng connections và connections theo route.
- Với connection manager không bật chế độ shared, Apache client sở hữu manager theo contract thông thường.
- Spring gọi `client.close()` khi bean bị destroy, không phải sau từng HTTP request.
- Các service inject client; chúng chỉ đóng **response** theo đúng phạm vi.

### 4.1. Tránh double-close của connection manager

Có thể tách connection manager ra thành bean riêng nếu nhiều HTTP clients **cùng chia sẻ pool**. Nhưng khi đó phải quyết định **ai đóng manager** và client có dùng `setConnectionManagerShared(true)` hay không. Không đăng ký cả client và manager như hai tài nguyên đều sở hữu cùng một manager mà không hiểu contract.

Mô hình dễ dùng hơn cho đa số service: một client bean sở hữu một manager, client được container đóng đúng một lần.

### 4.2. Wrapper client cho domain service

Một `PartnerGateway` có thể cung cấp các method nghiệp vụ và sở hữu raw HTTP client bên trong:

```java
@Bean(destroyMethod = "close")
PartnerGateway partnerGateway() {
    CloseableHttpClient apacheClient = HttpClients.createDefault();
    return new PartnerGateway(apacheClient);
}
```

Snippet này giả định `PartnerGateway` triển khai `AutoCloseable` và `close()` đóng `apacheClient`. Nếu chọn phương án này, **không** đồng thời đăng ký `apacheClient` thành bean với một destroy callback thứ hai. Ví dụ hoàn chỉnh sẽ dùng chính wrapper pattern này, kèm connection manager có giới hạn.

### 4.3. Không mọi HTTP client trên mọi JDK đều có cùng close API

`java.net.http.HttpClient` của **Java 17** không có cùng contract `AutoCloseable.close()` như một số phiên bản JDK mới hơn. Đừng lấy mã sử dụng `try (HttpClient client = ...)` hoặc `destroyMethod="close"` từ tài liệu JDK mới rồi sao chép cho Java 17 mà không đối chiếu.

Điều cần làm là chọn đúng API lifecycle **của implementation và phiên bản đang dùng**. Trong bài này, `CloseableHttpClient` của Apache được chọn vì có contract đóng resource rõ ràng.

## 5. HikariCP DataSource: ưu tiên Spring Boot auto-configuration

Trong Spring Boot 3.3, `spring-boot-starter-jdbc` và `spring-boot-starter-data-jpa` thường kéo HikariCP vào runtime. Khi có JDBC driver và không khai báo một custom `DataSource` bean phù hợp, Boot có thể tự cấu hình pooling DataSource.

Lợi ích:

1. Một pool chủ sở hữu rõ ràng.
2. Config ngoài code qua `spring.datasource.*` và `spring.datasource.hikari.*`.
3. Các components inject `DataSource`, `JdbcTemplate` hoặc repository.
4. Framework quản lý transaction/connection theo contract.
5. Khi context đóng, HikariDataSource được destroy theo lifecycle.

Ví dụ service thông thường:

```java
@Service
class ProductRepository {

    private final JdbcTemplate jdbcTemplate;

    ProductRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    int numberOfProducts() {
        return jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM products", Integer.class);
    }
}
```

Snippet giả định bảng `products` tồn tại, cần import `@Service`, `JdbcTemplate`. Repository **không tự tạo pool** và không gọi `dataSource.close()` sau mỗi query.

### 5.1. Properties ví dụ

```properties
spring.datasource.url=jdbc:postgresql://db.example.internal:5432/catalog
spring.datasource.username=example_user
spring.datasource.password=example_secret

spring.datasource.hikari.maximum-pool-size=12
spring.datasource.hikari.minimum-idle=2
spring.datasource.hikari.connection-timeout=3000
spring.datasource.hikari.max-lifetime=1800000
```

Đây là cấu hình **minh họa**, không dùng username/password/hostname mẫu ở production. Đưa secrets vào biến môi trường/secret manager và hạn chế log. `maximum-pool-size` phải được tính **trên tổng số pods/instances**: 25 instances × 12 connections = tối đa 300 connections tới DB, chưa tính các dịch vụ khác.

Lưu ý: không tăng pool size vô hạn để sửa query chậm. Kiểm tra transaction duration, connection hold time, max connections của DB, timeouts và workload.

### 5.2. Đóng connection mượn, không đóng pool

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT id FROM products WHERE id = ?")) {

    statement.setLong(1, productId);

    try (ResultSet result = statement.executeQuery()) {
        if (result.next()) {
            process(result.getLong("id"));
        }
    }
}
```

Snippet giả định `dataSource`, `productId`, `process` và bảng `products` đã có. Khi try-with-resources kết thúc, JDBC handles được đóng; với Hikari, `Connection.close()` **trả kết nối mượn về pool** để tái sử dụng.

**Phản ví dụ:**

```java
// Không làm ở cuối một request:
((HikariDataSource) dataSource).close();
```

Đây là thao tác đóng **toàn Hikari pool**. Request khác dùng bean chung có thể thất bại. Pool thuộc container, không thuộc từng request.

### 5.3. Khi cần nhiều DataSource

Khi ứng dụng có primary/replica DB hoặc nhiều nguồn dữ liệu độc lập, có thể tạo nhiều `@Bean DataSource`, dùng `@Qualifier`/`@Primary` và transaction managers tương ứng. Cần đảm bảo **mỗi pool** có owner/destroy callback và xác định rõ service nào được inject vào pool nào.

Việc tạo custom `DataSource` bean có thể khiến Spring Boot **back off** đường auto-configuration mặc định. Tránh vô tình khởi tạo một pool thủ công trong một service trong khi còn một Hikari pool auto-configured khác không dùng.

## 6. Nếu phải tự cấu hình HikariDataSource

Trong module nhiều database, một custom Hikari bean có thể hợp lý:

```java
@Bean(destroyMethod = "close")
HikariDataSource auditDataSource() {
    HikariConfig config = new HikariConfig();
    config.setJdbcUrl("jdbc:h2:mem:audit;DB_CLOSE_ON_EXIT=FALSE");
    config.setUsername("sa");
    config.setPassword("");
    config.setMaximumPoolSize(3);
    return new HikariDataSource(config);
}
```

Snippet cần imports Hikari classes và H2 dependency. Đây là DB in-memory dùng học/test, **không** làm mẫu credentials production. Khi đóng context, Spring gọi `HikariDataSource.close()`.

### 6.1. Ba loại lỗi pool cần phân biệt

| Vấn đề | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Connection leak | Connection được mượn không trả, pool cạn | Try-with-resources, transaction management, timeout, leak detection |
| Pool leak | App/context đã ngừng nhưng pool vẫn sống | Container lifecycle/owner cleanup |
| Quá nhiều pools | Mỗi service/request tạo pool riêng | Reuse bean singleton và rà số pools mỗi instance |
| Pool nhỏ so với workload | Queue chờ connection, timeouts | Đo query/transaction/concurrency trước khi chỉnh size |
| Connection invalid/stale | Query fail sau network failover | Driver/pool validation/timeouts, retry phù hợp |

`leakDetectionThreshold` của Hikari hỗ trợ phát hiện connection giữ quá lâu, **không** thay thế việc đóng connection đúng và không tự sửa pool ownership.

## 7. ThreadPoolTaskExecutor như managed resource

Một executor giữ worker threads, queue, task state và các tham chiếu tới bean khác. Việc tạo pool trong controller là anti-pattern:

```java
@PostMapping("/reports")
String requestReport() {
    ExecutorService pool = Executors.newFixedThreadPool(4);
    pool.submit(this::generateReport);
    return "accepted";
}
```

Đây là snippet phản diện; method `generateReport` và imports chưa được định nghĩa. Mỗi request có thể tạo một pool mới, không có cleanup hoặc backpressure chung. Nếu các worker là non-daemon, JVM có thể không kết thúc.

Đưa executor thành bean:

```java
@Bean("managedWorkExecutor")
ThreadPoolTaskExecutor managedWorkExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(16);
    executor.setThreadNamePrefix("managed-work-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(5);
    return executor;
}
```

Method này thuộc `@Configuration` hoặc `@SpringBootApplication`, Spring tạo, khởi tạo và destroy bean. Không cần controller tự gọi `shutdown()` sau mỗi lần submit.

### 7.1. Queue hữu hạn và rejection policy

Khi `queueCapacity` hữu hạn, pool có thể tăng từ core tới max sau khi queue đầy, nhưng cuối cùng vẫn có giới hạn. Caller phải xử lý việc bị từ chối `TaskRejectedException`/`RejectedExecutionException` theo contract: trả lỗi thích hợp, retry bounded hoặc ghi công việc vào durable queue.

Khi queue unbounded, `maxPoolSize` có thể ít được dùng vì các task cứ được xếp vào queue. Điều đó có thể làm latency hoặc memory tăng mà thread count vẫn nhỏ.

### 7.2. ExecutorService JDK cần shutdown riêng nếu tự tạo

- `shutdown()`: dừng nhận công việc mới, cho phép task đã submit hoàn thành; **không chờ**.
- `awaitTermination(timeout, unit)`: chờ bounded sau shutdown.
- `shutdownNow()`: cố interrupt task đang chạy và trả danh sách chưa bắt đầu, **best effort**.
- `isShutdown()` không đồng nghĩa `isTerminated()`.
- `Future.cancel(true)` không tự đóng executor.
- `ExecutorService` trên **Java 17** chưa có `AutoCloseable.close()` theo API của JDK mới hơn.

Nếu buộc giữ `ExecutorService` trong private field, dùng một owner bean với `@PreDestroy`/`DisposableBean`, bounded await và xử lý unfinished task; không hy vọng GC tự đóng threads.

### 7.3. Scheduler có cùng trách nhiệm

`ThreadPoolTaskScheduler` do Spring quản lý hoặc Boot auto-configured `TaskScheduler` nên được ưu tiên cho `@Scheduled`. Scheduler có pool, task queue và shutdown policy; nó không tự cung cấp persistent job storage hoặc exactly-once delivery.

Khi job cần sống qua restart, một in-memory executor/scheduler không đủ. Cần durable queue, checkpoint và idempotent processing.

## 8. Shutdown phải tôn trọng dependency graph

```text
SIGTERM / application shutdown
    |
Readiness REFUSING_TRAFFIC, drain HTTP traffic
    |
Stop producer/scheduler/consumer nhận job mới
    |
Executor ngừng nhận task mới
    |
Await in-flight tasks (bounded)
    |
Commit/rollback/checkpoint/requeue unfinished jobs
    |
Đóng response/connection handles còn mượn
    |
Đóng HTTP client / DataSource pool / executor threads
    |
ApplicationContext.close() hoàn tất
```

Đây là **đường đi mong muốn**, không phải bảo đảm rằng Spring tự sắp đúng thứ tự cho mọi component tùy biến. Bean dependency/destruction order và `SmartLifecycle` phase có ảnh hưởng; một background task ngoài container vẫn có thể dùng tài nguyên đã bị destroy.

### 8.1. Vì sao không chỉ gọi close trong ContextClosedEvent?

`ContextClosedEvent` là một mốc của shutdown nhưng listener không thay thế được full lifecycle coordination. Nếu một listener đóng `DataSource` khi còn task đang chạy, task có thể lỗi giữa transaction. Với tài nguyên Spring-managed, ưu tiên destroy callback của đúng owner và coordinated stop cho producers/workers.

Trong context hierarchy, một listener ở parent còn có thể nhận event `ContextClosedEvent` của child; nếu không lọc context origin có thể đóng pool của parent nhầm lúc child đóng.

### 8.2. SmartLifecycle cho component sản xuất task

Một `SmartLifecycle` component có thể:

1. Khi `start()`: đăng ký nhận messages hoặc bắt đầu scheduling.
2. Khi `stop(Runnable callback)`: ngừng nhận messages, đợi in-flight work, rồi gọi callback.
3. Đặt phase phù hợp để producer dừng trước consumers/resources theo dependencies.

Callback **phải được gọi** khi stop hoàn tất, kể cả khi lỗi được xử lý, để lifecycle processor có thể tiếp tục. Không giữ callback vô thời hạn.

### 8.3. Time budget khi chạy trong Kubernetes

`server.shutdown=graceful` và `spring.lifecycle.timeout-per-shutdown-phase` áp dụng cho các pha phù hợp của Spring Boot/Framework. `ThreadPoolTaskExecutor` có await termination period riêng. Kubernetes còn có `terminationGracePeriodSeconds` trước khi gửi hard kill.

Nếu platform cho 30 giây nhưng executor chờ 90 giây, việc cleanup có thể bị cắt giữa chừng. Hãy thiết kế tổng budget, timeout network/DB, queue checkpoint và test SIGTERM trong staging.

## 9. Demo chạy được: HTTP client, Hikari pool và executor cùng được Spring quản lý

Ví dụ sau **chạy không cần database server hoặc HTTP server bên ngoài**. H2 in-memory dùng qua HikariCP auto-configured; Apache HTTP client được tạo nhưng không thực hiện network call; một task chạy trong managed `ThreadPoolTaskExecutor`. Khi `ApplicationContext` đóng, chương trình kiểm tra pool và executor đã ngừng.

### 9.1. Cấu trúc

```text
managed-resources/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/com/example/resources/
    ManagedResourcesApplication.java
    ResourceConfiguration.java
    PartnerGateway.java
```

### 9.2. settings.gradle

```groovy
rootProject.name = 'managed-resources'
```

### 9.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.apache.httpcomponents.client5:httpclient5'
    runtimeOnly 'com.h2database:h2'
}
```

Đây là build script Groovy DSL cho demo. BOM Spring Boot quản lý version Apache HttpClient5 và H2. Nếu chưa có Gradle Wrapper, tạo bằng Gradle tương thích hoặc dùng Spring Initializr.

### 9.4. application.properties

```properties
# H2 in-memory: tránh cơ chế H2 tự shutdown ngoài Spring.
spring.datasource.url=jdbc:h2:mem:managed;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

# Một Hikari pool do Spring Boot auto-configure.
spring.datasource.hikari.maximum-pool-size=4
spring.datasource.hikari.minimum-idle=0
spring.datasource.hikari.connection-timeout=3000

# Không mở HTTP server trong demo.
spring.main.web-application-type=none
```

H2 chỉ phục vụ ví dụ, không dùng làm persistent DB. `DB_CLOSE_ON_EXIT=FALSE` giúp tránh H2 auto-shutdown xung đột với lifecycle container. Hikari pool được Boot quản lý riêng.

### 9.5. PartnerGateway.java

```java
package com.example.resources;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;

import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;

public final class PartnerGateway implements AutoCloseable {

    private final CloseableHttpClient client;
    private final AtomicBoolean closed = new AtomicBoolean();

    public PartnerGateway(CloseableHttpClient client) {
        this.client = client;
    }

    public boolean isOpen() {
        return !closed.get();
    }

    @Override
    public void close() throws IOException {
        if (closed.compareAndSet(false, true)) {
            try {
                client.close();
            } finally {
                System.out.println("PARTNER_CLIENT_CLOSED");
            }
        }
    }
}
```

`PartnerGateway` là wrapper sở hữu duy nhất Apache client trong demo. `isOpen()` chỉ phản ánh flag của wrapper, **không phải health check HTTP/network**. Có `AtomicBoolean` để wrapper không tự gọi close lặp trong các lần cleanup, nhưng trách nhiệm dừng/chờ request in-flight vẫn thuộc thiết kế ứng dụng.

### 9.6. ResourceConfiguration.java

```java
package com.example.resources;

import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class ResourceConfiguration {

    @Bean(destroyMethod = "close")
    PartnerGateway partnerGateway() {
        PoolingHttpClientConnectionManager manager =
                PoolingHttpClientConnectionManagerBuilder.create()
                        .setMaxConnTotal(20)
                        .setMaxConnPerRoute(5)
                        .build();

        CloseableHttpClient httpClient = HttpClients.custom()
                .setConnectionManager(manager)
                .build();

        return new PartnerGateway(httpClient);
    }

    @Bean("managedWorkExecutor")
    ThreadPoolTaskExecutor managedWorkExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("managed-work-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);

        return executor;
    }
}
```

**Ownership trong file này:**

- Spring quản lý bean `PartnerGateway` và gọi `close()` khi destroy. Gateway đóng Apache `CloseableHttpClient`. Không đăng ký manager/client làm bean thứ hai có destroy callback.
- Spring quản lý bean `ThreadPoolTaskExecutor` và gọi lifecycle/shutdown tương ứng. Không gọi `executor.initialize()` thủ công trong `@Bean`.
- File **không** tạo HikariDataSource: việc đó do Boot auto-configuration từ starter JDBC và properties.

### 9.7. ManagedResourcesApplication.java

```java
package com.example.resources;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import javax.sql.DataSource;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
public class ManagedResourcesApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ManagedResourcesApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        HikariDataSource pool;
        ThreadPoolTaskExecutor executor;

        try (ConfigurableApplicationContext context = app.run(args)) {
            pool = context.getBean(HikariDataSource.class);
            executor = context.getBean(
                    "managedWorkExecutor", ThreadPoolTaskExecutor.class);

            System.out.println("CONTEXT_ACTIVE=" + context.isActive());
        }

        System.out.println("DB_POOL_CLOSED=" + pool.isClosed());
        System.out.println("EXECUTOR_TERMINATED="
                + executor.getThreadPoolExecutor().isTerminated());
    }

    @Bean
    ApplicationRunner exercise(
            DataSource dataSource,
            PartnerGateway gateway,
            @Qualifier("managedWorkExecutor")
            ThreadPoolTaskExecutor executor) {

        return args -> {
            try (Connection connection = dataSource.getConnection();
                 Statement statement = connection.createStatement();
                 ResultSet rs = statement.executeQuery("SELECT 1")) {

                rs.next();
                System.out.println("DB_RESULT=" + rs.getInt(1));
            }

            System.out.println("PARTNER_CLIENT_OPEN=" + gateway.isOpen());

            Future<String> future = executor.submit(() -> "processed");
            System.out.println("TASK_RESULT="
                    + future.get(3, TimeUnit.SECONDS));
        };
    }
}
```

Phân tích từng bước:

1. Spring Boot tạo `ApplicationContext` non-web và HikariDataSource từ properties.
2. Một `PartnerGateway` bean được tạo, bên trong có Apache closable HTTP client.
3. Một `ThreadPoolTaskExecutor` bean được tạo và quản lý bởi Spring.
4. Sau refresh, `ApplicationRunner` lấy JDBC connection, thực hiện `SELECT 1` trên H2, trả handles bằng try-with-resources.
5. Runner kiểm tra flag Gateway mà không gọi mạng bên ngoài.
6. Runner submit task rất ngắn, chờ `Future` tối đa ba giây; task hoàn thành trước khi runner return.
7. `SpringApplication.run(...)` hoàn tất. `main` lấy HikariDataSource và executor để quan sát, in active.
8. Thoát `try-with-resources` trên **ConfigurableApplicationContext** gọi `context.close()`, container chạy shutdown và destroy callbacks.
9. Sau context.close, main kiểm tra `HikariDataSource.isClosed()` và trạng thái thread pool.

### 9.8. Lệnh chạy

```bash
./gradlew bootRun
```

Windows CMD: `gradlew.bat bootRun`; PowerShell: `.\gradlew.bat bootRun`. Nếu dự án có nhiều main classes, cấu hình `springBoot.mainClass` trong Gradle thay vì giả định plugin tự chọn đúng.

### 9.9. Các dòng output do demo tự in

Bỏ qua banner, log của Spring/Hikari và Gradle. Trong đường chạy thành công bình thường:

```text
DB_RESULT=1
PARTNER_CLIENT_OPEN=true
TASK_RESULT=processed
CONTEXT_ACTIVE=true
PARTNER_CLIENT_CLOSED
DB_POOL_CLOSED=true
EXECUTOR_TERMINATED=true
```

Đường code này không gửi network request và không có task dài, nên dọn dẹp nhanh. `PARTNER_CLIENT_CLOSED` chạy trong bean destroy; nó xuất hiện sau `CONTEXT_ACTIVE` và trước hai dòng kiểm tra sau `close()`. **Không mặc định thứ tự log destroy của những bean khác** khi bạn mở rộng ứng dụng.

Nếu startup hoặc query ném exception, những dòng thành công không nhất thiết xuất hiện; đó là trường hợp cần xử lý lỗi và kiểm thử riêng.

## 10. Vì sao không tạo client/pool/executor trực tiếp trong service?

```java
@Service
class UnsafeService {
    private final CloseableHttpClient http =
            HttpClients.createDefault();
    private final ExecutorService workers =
            Executors.newFixedThreadPool(4);

    void performAsync(Runnable job) {
        workers.submit(job);
    }
}
```

Đây là **phản ví dụ** thiếu lifecycle callbacks và imports. Vì `UnsafeService` là một bean, Spring quản lý bean đó, **không có nghĩa mọi private field là một managed bean**. Không có `@PreDestroy` hay owner logic, workers và HTTP client có thể tồn tại sau khi service bị destroy.

**Ưu tiên:** đăng ký riêng các bean resources qua `@Configuration` và inject vào service. Nếu bắt buộc sở hữu resource nội bộ, viết bean owner có `@PreDestroy` và cleanup hợp tác.

### 10.1. Ví dụ owner bean với ExecutorService JDK

```java
@Component
class OwnedJobs {

    private final ExecutorService executor =
            Executors.newFixedThreadPool(2);

    void submit(Runnable task) {
        executor.submit(task);
    }

    @PreDestroy
    void stop() {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

Đây là **class minh họa** cần imports `Component`, `PreDestroy`, `ExecutorService`, `Executors`, `TimeUnit`. Để dùng production, phải tiếp tục theo dõi tasks chưa bắt đầu, xác nhận executor terminated hoặc ghi lỗi/cancel/checkpoint phù hợp. `shutdownNow()` là best effort, không phải bảo đảm hoàn thành shutdown.

Đối với phần lớn công việc Spring, `ThreadPoolTaskExecutor` bean với lifecycle do container quản lý sẽ ít phải viết boilerplate hơn.

## 11. Không đóng hai lần và không đóng sai đối tượng

Các lỗi phổ biến:

- `PartnerGateway.close()` tự đóng Apache client, đồng thời một bean `CloseableHttpClient` khác có destroy callback trên **cùng instance**.
- Service gọi `dataSource.close()` sau mỗi request trong khi datasource là singleton.
- Controller gọi `executor.shutdown()` sau khi submit để “dọn”, khiến request tiếp theo bị từ chối.
- `@PreDestroy` đóng resource, rồi `@Bean(destroyMethod="close")` cũng đóng lại cùng resource mà không có idempotence.
- HTTP client đóng pool, nhưng code còn giữ response stream chưa được xử lý.
- Spring parent context sở hữu resource, child context đóng rồi tự gọi cleanup của parent.

Giải pháp: **một owner, một lifecycle policy**, đồng thời phân biệt per-call handle cleanup với shared resource shutdown.

### 11.1. Inferred destroy method không giải quyết mọi trường hợp

Với `@Bean`, Spring có thể suy luận method `close`/`shutdown`. Nhưng nếu object nằm trong private field, không phải bean riêng và owner không gọi cleanup, Spring không có đủ thông tin để tự đóng field đó.

Ngược lại, một facade đơn thuần như `RestTemplate` thường **không phải chính resource có pool**. Hãy xác định underlying client/request factory nào sở hữu resource, thay vì thêm `destroyMethod="close"` vào class không có method đó.

### 11.2. Bean lazy chưa instantiate

Một bean `@Lazy` chưa bao giờ được tạo không có instance để destroy. Điều này không phải resource leak nếu bean chưa mở resource. Nhưng nếu resource được tạo ở một utility/static field ngoài BeanFactory, metadata `@Lazy` không khiến Spring biết về resource đó.

## 12. Nếu startup lỗi giữa lúc xây dựng resource?

Một lỗi tinh vi:

```java
@Bean
PartnerGateway partnerGateway() {
    CloseableHttpClient raw = HttpClients.createDefault();

    validateConfiguration(); // Có thể ném exception.

    return new PartnerGateway(raw);
}
```

Đây là snippet minh họa: `validateConfiguration()` chưa được định nghĩa. Nếu validation ném exception **sau khi client được tạo nhưng trước khi method return bean**, Spring chưa có bean instance để gọi destroy. Tài nguyên raw có thể bị rò.

**Giải pháp:**

- Validate cấu hình trước khi mở resource.
- Dùng `try/catch`, đóng những resources đã tạo nếu phần khởi tạo tiếp theo lỗi.
- Nếu mở nhiều resources, bàn giao ownership từng bước rõ ràng.
- Kiểm thử startup failure, không chỉ happy path.

Một mẫu:

```java
@Bean(destroyMethod = "close")
PartnerGateway partnerGateway() throws IOException {
    validateConfiguration(); // Fail sớm trước khi mở client.

    CloseableHttpClient raw = HttpClients.createDefault();
    try {
        return prepareGateway(raw);
    } catch (RuntimeException ex) {
        raw.close();
        throw ex;
    }
}
```

Đây là **snippet**, cần helper `validateConfiguration`/`prepareGateway` có thật; mục đích là minh họa exception-safe factory, không phải file chạy độc lập.

## 13. ThreadPoolTaskExecutor và task đang chạy khi shutdown

Nếu task dùng `PartnerGateway` và `DataSource`, đóng chúng trước khi task hoàn thành có thể làm task lỗi giữa chừng. Nhưng chờ vô hạn cũng có thể khiến Kubernetes kill pod trước khi cleanup hoàn tất.

Một chiến lược có trách nhiệm:

1. Công bố readiness refusing hoặc ngừng nhận traffic mới khi phù hợp.
2. Dừng scheduler, consumer, producer submit tasks.
3. Executor chuyển sang không nhận job mới.
4. Chờ tasks đang chạy trong deadline.
5. Nếu quá hạn, cancel/rollback/checkpoint/requeue theo contract.
6. Giải phóng JDBC/HTTP handles còn mượn.
7. Đóng underlying pools/clients khi không còn consumer hợp lệ.
8. Đo shutdown duration và số tasks chưa hoàn tất.

Spring `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler` hỗ trợ shutdown policies, nhưng **không tự biến task thành durable transactions**.

### 13.1. setWaitForTasksToCompleteOnShutdown và awaitTermination

`setWaitForTasksToCompleteOnShutdown(true)` có thể để executor xử lý queued work thay vì chủ động interrupt chúng ngay khi shutdown. `setAwaitTerminationSeconds(5)` giới hạn thời gian container chờ trong phase shutdown tương ứng. Đừng hiểu rằng kết hợp hai tùy chọn tự đảm bảo mọi task dừng trong năm giây; nếu task kẹt hoặc queue còn dài, cần báo lỗi/handling khác.

Khi dùng `SmartLifecycle` để dừng producer, chú ý policy executor có thể thay đổi việc chấp nhận tasks sau `ContextClosedEvent`. Spring Framework 6.1 có thay đổi default coordinated shutdown, nên hãy kiểm tra version JavaDoc khi bật các flag cùng nhau.

### 13.2. Phối hợp với graceful shutdown

Với web server, Spring Boot hỗ trợ `server.shutdown=graceful` và `spring.lifecycle.timeout-per-shutdown-phase`. Kubernetes còn có `terminationGracePeriodSeconds`. Tổng thời gian drain+await+cleanup phải vừa trong hạn hạ tầng.

Một worker đang ghi dữ liệu cần có transaction/offset checkpoint/retry, không chỉ tăng timeout. Nếu task quan trọng phải tồn tại qua restart, hãy dùng durable queue/job store.

## 14. Cấu hình Boot có áp dụng cho custom executor không?

Spring Boot 3.3 auto-configures `AsyncTaskExecutor` khi không có `Executor` bean làm auto-config back off. Trên Java 17, implementation thông thường là `ThreadPoolTaskExecutor`. Các properties như:

```properties
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=64
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=10s
```

tác động tới executor được **Boot auto-configure theo điều kiện thích hợp**, không tự chỉnh mọi custom bean được tạo bằng `new ThreadPoolTaskExecutor()` hay `Executors.newFixedThreadPool(...)`.

Khi ứng dụng có nhiều executor beans, chọn đúng pool:

```java
@Async("managedWorkExecutor")
public CompletableFuture<String> compute() {
    return CompletableFuture.completedFuture("done");
}
```

Đây là method minh họa thuộc Spring bean, cần `@EnableAsync`, `@Async` và gọi qua proxy; self-invocation `this.compute()` có thể bypass proxy. `managedWorkExecutor` phải là bean có tên như cấu hình, không chỉ là biến local.

Đừng mặc định Spring MVC async, GraphQL và `@Async` tất cả sẽ chọn cùng executor khi có custom pools; Spring Boot có quy tắc chọn theo bean type/name, ví dụ `applicationTaskExecutor` cho một số web integrations.

## 15. Nhiều ApplicationContext và parent-child contexts

Spring có thể có nhiều contexts trong integration tests, hierarchy hoặc các ứng dụng chạy cùng JVM. Nếu parent context sở hữu Hikari pool còn child chỉ dùng, đóng child **không** có nghĩa pool của parent phải được đóng.

Các quy tắc:

- Resource bean thuộc context nào thì lifecycle owner là context đó.
- Child có thể inject bean từ parent, nhưng không được đóng resource của parent sau một request.
- Listener `ContextClosedEvent` ở parent có thể nhận event child; phải phân biệt origin nếu tự thao tác shutdown.
- Tránh static executor/global client dùng chung cho nhiều contexts mà không có owner cấp JVM rõ ràng.
- TestContext cache có thể tái sử dụng cùng application context; không đóng manual resource trong test làm các test sau thất bại.

Nếu cần kiểm tra close, tạo một context độc lập và đóng nó trong integration test, thay vì gọi close trên bean trong cached context chung.

## 16. Kiểm thử lifecycle: không chỉ kiểm tra ứng dụng chạy

Bộ test nên bao gồm:

**Creation:**
- Mỗi resource singleton được tạo một lần cho mỗi context như thiết kế.
- Service inject đúng bean qua `@Qualifier` nếu nhiều clients/pools.
- Hikari pool size đúng profile, không có DataSource trùng ngoài ý muốn.
- Executor queue/rejection policy đúng workload.

**Per-call:**
- JDBC connection trả về pool kể cả khi query ném exception.
- HTTP response/stream được đóng đúng API.
- Một request không gọi close shared client/executor.
- Tasks nhận lỗi/rejection theo contract; không báo accepted giả.

**Shutdown:**
- Context.close() gọi đúng resource destroy callbacks.
- HikariDataSource.isClosed() true sau context close.
- Executor terminated sau khi không còn task dài.
- HTTP client wrapper close đúng một lần.
- Producer không submit sau khi pool shutdown.
- Khi task kẹt, deadline và failure path được xử lý.
- Khi startup fail giữa chừng, những resources tạo trước failure được cleanup.

**Vận hành:**
- Lặp nhiều lần tạo/đóng context không tăng thread count.
- Rollout nhiều pods không vượt max DB connections.
- SIGTERM cho đủ thời gian drain/chờ/cleanup.
- Hệ thống không mất task quan trọng khi pod restart.
- Không ghi secret trong log/startup exception.

### 16.1. Một test với ApplicationContextRunner

`ApplicationContextRunner` từ `spring-boot-test` có thể hữu ích để tạo context cấu hình nhỏ rồi đóng theo phạm vi test. Nhưng với demo có JDBC auto-configuration và đầy đủ starters, `@SpringBootTest`/integration test có thể phù hợp hơn.

Không dùng unit test mock `CloseableHttpClient` để kết luận Hikari pool thật đóng; mỗi assertion chỉ chứng minh đúng tầng được test. Một số resource cần integration test trong context thật.

## 17. Monitoring và quan sát tài nguyên

| Resource | Metric/triệu chứng | Điều cần xử lý |
| --- | --- | --- |
| Hikari | Active/idle/pending connections, timeout | Connection bị giữ, pool nhỏ hoặc DB quá tải |
| HTTP client | Leased/pending/available connections, response timeout | Response chưa đóng, pool cạn, external API chậm |
| Executor | Active threads, queue size, rejected tasks | Overload, backlog lớn, caller bị chặn |
| Scheduler | Job duration, overlaps, failures | Job không idempotent, không dừng đúng shutdown |
| JVM | Live thread count, open file descriptors | Thread/socket leak hoặc resources giữ ngoài scope |
| Spring | Startup/shutdown duration | Destroy callback chậm, task kẹt |
| Deployment | Restart count, rollout readiness delay | Grace period quá ngắn, dependencies chưa sẵn sàng |

`ThreadPoolTaskExecutor` có `getActiveCount()`, `getPoolSize()`, `getQueueSize()`. Hikari có metric/JMX/Micrometer integration phù hợp; Apache connection manager có pool statistics. Không coi mọi metric tự xuất hiện chỉ vì có bean; kiểm tra Actuator/Micrometer config thực tế.

## 18. Các lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| JVM không thoát sau context.close | Executor tự tạo không shutdown, non-daemon threads | Spring-managed executor hoặc owner @PreDestroy |
| Đóng context rồi vẫn giữ DB connections | Hikari pool ngoài container không close | Tạo DataSource managed bean/auto-config |
| Lỗi client already closed ở request tiếp theo | Đóng HTTP client singleton per-request | Chỉ đóng response, không đóng shared client |
| Hikari báo pool exhausted | Connection không trả, query lâu, quá nhiều requests | Try-with-resources, transaction tuning, pool metrics |
| Có hai HTTP client cleanup paths | Raw client và wrapper đều là owners | Chỉ một owner, quy định manager shared nếu cần |
| Một client được tạo trong mỗi request | Không reuse bean | Singleton client bean và inject |
| Task chạy sau khi DB đóng | Không dừng producer/await trước resource teardown | SmartLifecycle, bounded wait và order |
| @PreDestroy có nhưng app vẫn không thoát | Task không phản hồi interrupt, executor chưa terminated | Timeout/cancellation, thread dump |
| Startup fail sau new client | Factory chưa trả bean, container chưa sở hữu | Validate trước, catch/finally cleanup |
| Nhiều DB pools bất ngờ | Custom DataSource và auto-config cùng/khác path | Rà BeanFactory và qualifiers |
| Executor reject nhưng HTTP trả Accepted | Bỏ qua TaskRejectedException | Trả lỗi đúng, durable queue khi cần |
| Pool max cao nhưng threads không mở rộng | Unbounded queue giữ toàn bộ backlog | Bounded queue, quan sát rejection |
| Test thứ hai lỗi vì pool đóng | Test đóng bean trong cached context | Scope test độc lập, để context owner đóng |
| Mất task khi pod restart | Executor in-memory không durable | Queue/job store/checkpoint |
| Chỉ sửa connection-timeout để hết lỗi | Căn nguyên là connection leak/query chậm | Profile query và transaction lifecycle |
| Java 17 code dùng HttpClient.close | API nhầm phiên bản | Dùng đúng JDK/API client cụ thể |

## 19. Checklist thêm một tài nguyên mới vào Spring Boot

1. Xác định class thực sự sở hữu socket/thread/pool/file.
2. Chọn scope: application singleton, per-tenant, per-request hay process.
3. Ưu tiên Boot auto-config nếu có và phù hợp.
4. Nếu tạo custom bean, khai báo đúng `destroyMethod`/`@PreDestroy`/`DisposableBean`.
5. Chỉ một owner đóng mỗi resource.
6. Tránh tạo pool/client trong controller hoặc mỗi request.
7. Với HTTP, đóng response/stream theo API sau mỗi call.
8. Với JDBC, trả Connection về pool; không đóng DataSource per call.
9. Thiết lập pool/queue/concurrency/timeout hợp lý.
10. Có policy rejection/backpressure cho executor.
11. Biết cách dừng producer và chờ in-flight tasks.
12. Có bounded shutdown deadline phù hợp hạ tầng.
13. Khi task không xong, có cancel/requeue/checkpoint strategy.
14. Tránh resource đóng trước khi consumers đã ngừng dùng.
15. Với factory startup, dọn resource nếu lỗi trước khi return bean.
16. Kiểm tra nested resource có owner hay không.
17. Không dùng static/global pool nếu context scope mới là mong muốn.
18. Test nhiều contexts/restarts để phát hiện leak.
19. Phân biệt readiness/liveness với availability của client và DB.
20. Không để credentials, tokens, endpoint nhạy cảm trong logs.
21. Có metrics threads/queue/connections và shutdown time.
22. Test shutdown khi có load, không chỉ ứng dụng idle.
23. Không dùng Java API của JDK mới nếu dự án chạy Java 17.
24. Ghi rõ ở documentation bean nào được inject và ai chịu trách nhiệm đóng.

## 20. Tóm tắt

```text
               SPRING APPLICATION CONTEXT
                           |
       +-------------------+--------------------+
       |                   |                    |
   HTTP CLIENT         JDBC DataSource      TASK EXECUTOR
   PartnerGateway      HikariCP             ThreadPoolTaskExecutor
       |                   |                    |
   shared client       getConnection()      shared worker pool
       |                   |
   close RESPONSE      close CONNECTION
   sau mỗi call        => trả về pool
       |                   |                    |
       +-------------------+--------------------+
                           |
              APPLICATION SHUTDOWN
                           |
         Stop producers / drain in-flight tasks
                           |
             Spring destroy managed beans
                           |
       Close HTTP client, DataSource pool, Executor
```

**Quy tắc trọng tâm:** hãy **đăng ký client, connection pool và executor như tài nguyên có một owner rõ ràng**; dùng dependency injection để chia sẻ, đóng *handle* sau mỗi thao tác và để container đóng *resource chung* khi context dừng. Spring Boot hỗ trợ lifecycle nhưng không tự giải quyết tất cả bài toán cancel, backpressure, transaction, timeout hoặc durable jobs. Những thứ đó vẫn phải được thiết kế, cấu hình và kiểm thử.

## Tài liệu chính thức

- [Spring Boot 3.3 — SQL Databases / DataSource / HikariCP](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html)
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Framework — Bean lifecycle and destroy methods](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework 6.1 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.1 — ExecutorConfigurationSupport API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html)
- [Apache HttpClient 5 — Connection Management](https://hc.apache.org/httpcomponents-client-5.6.x/connection-management.html)
- [Java 17 — ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
