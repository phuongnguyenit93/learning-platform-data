# Giải phóng bộ thực thi, connection pool, tài nguyên Reactor và tệp tạm trong Spring Boot

Khi một Spring Boot web application dừng, Tomcat/Jetty/Reactor Netty ngừng nhận HTTP requests mới chưa có nghĩa toàn bộ tiến trình đã được giải phóng. Ứng dụng có thể còn **ExecutorService, ThreadPoolTaskExecutor, ScheduledExecutorService, Hikari connection pool, HTTP client sockets, Reactor schedulers, Netty event-loop threads, subscriptions, file streams và tệp tạm**. Nếu đóng sớm, các request đang chạy có thể lỗi. Nếu không đóng, JVM có thể treo vì threads sống, tiêu tốn connection/file descriptors hoặc để lại dữ liệu trên đĩa.

Bài thuộc **Spring Boot - web-runtime → Dừng có kiểm soát**, trình bày ba trụ cột **quyền sở hữu tài nguyên, thứ tự dừng và kiểm chứng cleanup**, rồi áp dụng vào bốn nhóm thực tế: **bộ thực thi, connection pool, Reactor, tệp tạm**. Ví dụ dùng **Java 17, Spring Boot 3.3.13, Spring MVC/Tomcat, HikariCP + H2, Reactor Core và Maven**. Phần WebClient/Reactor Netty có code riêng dành cho ứng dụng có spring-webflux; project demo chính không giả vờ chạy Netty. Các chính sách SIGTERM/Kubernetes, tệp orphan sau SIGKILL và kiểm thử lifecycle cũng được bao quát.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **graceful web shutdown** với dừng tasks nền và destroy Spring beans.
2. Giải thích **ApplicationContext, @PreDestroy, @Bean(destroyMethod), AutoCloseable, DisposableBean, SmartLifecycle, ContextClosedEvent**.
3. Dừng ExecutorService theo thứ tự **stop intake → shutdown() → awaitTermination() → shutdownNow() có điều kiện**.
4. Nhận biết **Spring-managed ThreadPoolTaskExecutor** khác executor do ứng dụng tự tạo.
5. Phân biệt Connection.close() trả JDBC connection về pool và HikariDataSource.close() đóng toàn pool.
6. Biết **Schedulers.newBoundedElastic(...).dispose()** khác shared Schedulers.boundedElastic().
7. Hiểu **WebClient, ReactorResourceFactory, ConnectionProvider, LoopResources, global Reactor Netty resources**.
8. Sử dụng try-with-resources và finally để xóa file ngay sau request/job, không chỉ chờ shutdown.
9. Xây dựng quy trình xử lý **SIGTERM, graceful drain, Kubernetes terminationGracePeriodSeconds và SIGKILL recovery**.
10. Viết ứng dụng runnable và tests chứng minh executor, custom Scheduler và owned workspace được dọn sau context.close.

## 2. Ai sở hữu thì người đó chịu trách nhiệm đóng

| Tài nguyên | Owner điển hình | Cách đóng thích hợp |
| --- | --- | --- |
| Embedded web server | Spring Boot ApplicationContext | server.shutdown=graceful và lifecycle stop. |
| ExecutorService tự tạo | @Service hoặc class new executor | shutdown, awaitTermination có deadline, shutdownNow khi cần. |
| ThreadPoolTaskExecutor bean | Spring container | lifecycle/destroy của bean và shutdown configuration. |
| JDBC Connection mượn từ pool | Scope transaction/request | Connection.close hoặc JdbcTemplate/@Transactional tự quản. |
| HikariDataSource | Boot auto-configured DataSource bean | Spring destroy bean, HikariDataSource.close một lần. |
| CloseableHttpClient custom | Client bean owner | close theo library API. |
| Reactor custom Scheduler | Bean tạo bằng Schedulers.new* | Scheduler.dispose. |
| Reactor global Scheduler | Reactor process-level shared factory | Không đóng từ từng component. |
| Reactor Netty event loops/connection pool | ReactorResourceFactory hoặc custom resource owner | Factory lifecycle/dispose. |
| File stream/channel | Scope mở stream | try-with-resources. |
| Tệp tạm riêng | Request/job | Files.deleteIfExists trong finally. |
| Thư mục tạm owned | Application component | Cleanup khi workers đã dừng; janitor khi crash. |

**Không đóng tài nguyên chung từ một controller chỉ vì một request lỗi.** Ngược lại, khi tạo ExecutorService bằng new trong một Spring singleton mà không có lifecycle, Spring không tự biết nó phải shutdown, trừ khi bean/chủ sở hữu thực hiện cleanup.

### 2.1. Không đóng trùng

Nếu @Bean của Spring đã được cấu hình destroyMethod=close hoặc Spring suy luận public close/shutdown, không nên có thêm một module khác chủ động close cùng resource trước khi bean destroy. Một số close() idempotent, nhưng không được coi mọi external client như vậy. Chọn một owner, xác định lúc các consumers ngừng và chỉ đóng khi resource không còn được dùng.

## 3. Thứ tự shutdown an toàn

~~~text
SIGTERM / context.close()
      |
      v
Kubernetes/Load Balancer ngừng routing traffic mới
      |
      v
Boot graceful web shutdown:
ngừng nhận request mới, đợi HTTP in-flight
      |
      v
Stop producers: HTTP admission, queue consumer, scheduler
      |
      v
Drain background tasks, cancel/finish subscriptions
      |
      v
Close Hikari/HTTP pools, custom schedulers,
Reactor Netty resources và file handles
      |
      v
Cleanup owned temporary workspace
      |
      v
Process exit
~~~

Đây là **mục tiêu kiến trúc**. Trong Spring, web server graceful shutdown diễn ra khi context đang đóng và trong các phase dừng SmartLifecycle. Nhiều resources khác được Spring destroy theo dependency/lifecycle. Bạn không thể mặc định thứ tự tuyệt đối giữa hai @PreDestroy không có quan hệ phụ thuộc, nên phải thiết kế rõ các bước dừng producers, workers và resources.

### 3.1. Bật graceful web shutdown

**application.yml:**

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Spring Boot 3.3 hỗ trợ graceful shutdown với Tomcat, Jetty, Reactor Netty và Undertow. Khi context đóng, web server có grace period cho requests đang xử lý. Tomcat/Jetty/Netty thường ngừng nhận requests mới ở lớp network; Undertow có thể trả 503 cho requests mới. Phương thức từ chối request mới còn phụ thuộc persistent connections và server implementation.

**Timeout-per-shutdown-phase không phải deadline toàn cục cho mọi @PreDestroy.** Một @PreDestroy block vô hạn vẫn có thể khiến tiến trình dừng chậm. Đặt timeout cụ thể cho executor.awaitTermination, network disposal, database pool drain và file cleanup.

### 3.2. Không đóng Hikari khi request còn in-flight

Ví dụ:

~~~text
Tomcat worker -> @Transactional service
-> borrowed Connection -> execute SQL -> commit
-> return Connection -> HTTP response
~~~

Nếu ContextClosedEvent listener tự gọi HikariDataSource.close trước khi web request hoàn tất, transaction hoặc query có thể thất bại. Với pool do Spring Boot quản lý, **để Spring destroy đúng thời điểm**. HTTP graceful shutdown giúp giảm nguy cơ, nhưng một detached job trả HTTP 202 trước khi làm xong sẽ không tự được Tomcat chờ.

### 3.3. Các loại dừng khác nhau

| Tình huống | Được đảm bảo @PreDestroy? | Chính sách |
| --- | --- | --- |
| ApplicationContext.close bình thường | Với beans đã tạo, Spring thực hiện destroy. | Deadline và cleanup callbacks. |
| SIGTERM được JVM xử lý | Thường có nếu còn đủ thời gian. | Readiness, web drain, resource teardown. |
| IDE dừng process | Phụ thuộc IDE gửi tín hiệu. | Thử qua SIGTERM thực. |
| SIGKILL, OOMKilled, crash, mất điện | Không | Durable queue, idempotency, orphan cleanup. |
| Startup lỗi giữa tạo resource | Không chắc mọi bean được đăng ký | Cleanup partial allocations khi khởi tạo lỗi. |

## 4. Spring lifecycle: @PreDestroy, destroyMethod, SmartLifecycle

### 4.1. @PreDestroy

Trong Spring Boot 3, dùng **jakarta.annotation.PreDestroy**:

~~~java
@Component
public class OwnedComponent {

    @PreDestroy
    public void cleanup() {
        // Chỉ giải phóng resources component này sở hữu.
    }
}
~~~

Một class tạo bằng **new OwnedComponent()** ngoài Spring container không tự nhận callback. Phương thức cleanup cần đồng bộ, có giới hạn và ghi lỗi rõ. Không chờ vô hạn hoặc cố hoàn thành cả workflow nghiệp vụ dài trong shutdown callback.

### 4.2. @Bean(destroyMethod) và AutoCloseable

~~~java
@Bean(destroyMethod = "dispose")
Scheduler ownedScheduler() {
    return Schedulers.newBoundedElastic(
            2, 32, "owned-scheduler");
}
~~~

Spring gọi dispose() khi bean bị destroy. Với @Bean có public close()/shutdown() hoặc AutoCloseable, Spring có thể suy luận destroy method; có thể khai báo tường minh cho rõ. **DisposableBean.destroy()** là callback khác nhưng liên kết domain code với Spring API. Tránh gắn đồng thời nhiều callbacks rồi thực hiện close trùng.

### 4.3. SmartLifecycle và phase

**SmartLifecycle** có start(), stop(Runnable callback), isRunning() và getPhase(). Khi start, phase thấp khởi động trước; khi stop, **phase cao dừng trước phase thấp**. Spring LifecycleProcessor chờ callback của một phase trong thời hạn timeout-per-shutdown-phase.

Phù hợp với **queue consumer → executor workers → database**. Stop consumer trước để không nhận thêm jobs, chờ workers, sau đó mới cho dependencies đóng. Đừng đoán getPhase()=100 chắc chắn dừng trước Boot web server nội bộ; chỉ nên dựa vào những phases bạn kiểm soát và đã test trên version cụ thể.

### 4.4. ContextClosedEvent không nghĩa mọi request đã xong

Listener ContextClosedEvent được thông báo khi context bắt đầu đóng. Nó có thể phát tín hiệu admission stop, nhưng không phải thời điểm thích hợp để mọi listener tùy ý đóng toàn bộ pool. Nên dùng lifecycle stop và @PreDestroy với dependency order rõ ràng.

## 5. ExecutorService: đóng theo hai giai đoạn

### 5.1. Ý nghĩa của các API

- **shutdown()**: dừng nhận task mới, các tasks đã nhận thường vẫn được chạy.
- **awaitTermination(timeout, unit)**: chờ trong một khoảng hữu hạn; true nếu executor đã kết thúc.
- **shutdownNow()**: cố interrupt tasks đang chạy, trả tasks chưa bắt đầu; **không bảo đảm giết được mọi thread**.
- **isTerminated()**: trạng thái executor đã hoàn toàn kết thúc.
- **Future.cancel(true)**: yêu cầu interruption nếu task đang chạy; không tự rollback external side effects.

### 5.2. Mẫu shutdown chuẩn Java 17

~~~java
executor.shutdown();
boolean terminated = false;

try {
    terminated = executor.awaitTermination(
            10, TimeUnit.SECONDS);

    if (!terminated) {
        executor.shutdownNow();
        terminated = executor.awaitTermination(
                2, TimeUnit.SECONDS);
    }
}
catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}

if (!terminated) {
    log.warn("Executor still active after deadline");
}
~~~

Đây là snippet, cần imports, ExecutorService executor và Logger. **Không dùng Thread.stop()**. Nếu task giữ monitor dài, chờ native I/O không thể interrupt hoặc bỏ qua flag, shutdownNow không ép nó dừng.

### 5.3. Ngừng producers trước khi shutdown

Nếu scheduler/Kafka listener/HTTP controller tiếp tục submit trong lúc executor.shutdown, sẽ xuất hiện **RejectedExecutionException**. Đặt cờ accepting=false, stop polling và xử lý race giữa kiểm tra cờ và submit. Với HTTP, có thể trả 503 nếu service đang drain; với message broker, dừng consume hoặc giữ record chưa ack để worker khác xử lý.

### 5.4. Detached task không nằm trong HTTP graceful drain

Một controller trả **202 Accepted** ngay sau submit job, khi job còn chạy, đã kết thúc HTTP request. Tomcat không chờ job đó vì nó không còn thuộc một in-flight servlet request. Nếu task có thể kéo dài hoặc bắt buộc hoàn tất, cần **durable job table/queue**, lease, checkpoint, retry idempotent và ownership. Không đặt niềm tin duy nhất vào JVM shutdown grace period.

### 5.5. Spring-managed executors

Nếu dùng **ThreadPoolTaskExecutor** hoặc ThreadPoolTaskScheduler, có lifecycle của Spring. Các settings như **setWaitForTasksToCompleteOnShutdown(true)** và **setAwaitTerminationSeconds(15)** hữu ích theo Spring Framework 6.1. Với @Async, kiểm tra executor thực sự được inject và không bị custom bean override auto-config. Java 21 virtual threads nhẹ hơn nhưng shutdown, cancellation và durability vẫn cần tương tự.

## 6. Connection pool: borrowed connection khác pool owner

### 6.1. HikariCP

~~~text
HikariDataSource (Spring bean)
    |
    +-- getConnection() -> pooled Connection C1
    |       |
    |       +-- query / commit / rollback
    |       +-- Connection.close() -> return to pool
    |
    +-- HikariDataSource.close() -> close pool
~~~

**Connection.close() trên pooled connection thường trả handle về pool**. Nó không tương đương HikariDataSource.close() phá toàn bộ pool. Tầng dùng connection cần trả về đúng scope, còn tầng sở hữu pool mới có quyền đóng khi context destroy.

### 6.2. JDBC resource scope

~~~java
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
             "select name from users where id = ?")) {

    ps.setLong(1, 42);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            return rs.getString(1);
        }
    }
}
~~~

Snippet thuộc method có DataSource và return type thích hợp. Với JdbcTemplate/@Transactional, Spring đã quản lý connection/transaction scope; không giữ Connection ở singleton field hoặc close trực tiếp HikariDataSource sau một SQLException.

### 6.3. Spring Boot JDBC/Hikari

**spring-boot-starter-jdbc** cùng H2 hoặc DB driver phù hợp khiến Boot auto-configure một DataSource, thường là Hikari. DataSource bean đóng theo Spring lifecycle. Hãy theo dõi **hikaricp.connections.active**, **idle**, **pending**, transaction duration và closure logs để xác minh.

Ngoài JDBC còn có **CloseableHttpClient**, Redis/Lettuce, MongoDB, R2DBC ConnectionPool; mỗi thư viện có close/dispose API riêng. Nếu client được tạo bên ngoài Spring, cần đăng ký Spring bean lifecycle hoặc quản lý thủ công. Không dùng một lệnh shutdown global khi chỉ một consumer ngừng.

## 7. Reactor Core: đóng đúng Scheduler và Subscription

### 7.1. Reactor Publishers không đồng nghĩa một pool

**Mono/Flux** mô tả pipeline. Một publisher như Mono.just không tự cần close; một subscription đang chạy lâu có thể cần cancel, và **Scheduler** custom có thể sở hữu threads.

| Đối tượng | Lifecycle |
| --- | --- |
| Mono.just/Flux.range | Không phải thread pool, thường không cần close. |
| Disposable từ subscribe() | Có thể dispose/cancel stream. |
| Schedulers.newBoundedElastic/newSingle/newParallel | Custom scheduler, owner gọi dispose(). |
| Schedulers.boundedElastic()/parallel()/single() | Shared Scheduler, không đóng tùy tiện. |
| Reactor Netty ConnectionProvider | Pool sở hữu sockets; dispose theo owner. |
| Reactor Netty LoopResources | Sở hữu event loop threads; dispose theo owner. |

### 7.2. Owned vs shared

~~~java
Scheduler shared = Schedulers.boundedElastic();

Scheduler owned = Schedulers.newBoundedElastic(
        4, 100, "background-adapter");
~~~

Đây là snippet với Reactor imports. **owned** do component tạo và nên dispose khi context đóng. **shared** thuộc Reactor process-level factory; không được gọi **Schedulers.shutdownNow()** từ một service để dọn riêng job của nó vì có thể khiến components khác bị reject.

### 7.3. Thứ tự dừng stream

Nếu một Flux đang nhận dữ liệu rồi dùng custom Scheduler và network client:

~~~text
Stop source/producer
    -> cancel hoặc drain active subscriptions
    -> dispose owned Scheduler
    -> close underlying HTTP/network pools
~~~

Không dispose scheduler sớm khi stream còn cần schedule operator. Cancellation không bảo đảm remote POST chưa có side effect; cần idempotency/reconciliation. Với file/reader được tạo khi subscribe, cân nhắc **Flux.using/usingWhen** để cleanup khi complete/error/cancel.

~~~java
Flux<String> lines = Flux.using(
        this::openReader,
        reader -> Flux.fromStream(reader.lines()),
        reader -> closeReader(reader));
~~~

Đây là snippet cần methods và imports; blocking reader cần offload khỏi event loop nếu chạy WebFlux.

## 8. WebClient/Reactor Netty: lifecycle của connection/event-loop resources

### 8.1. WebClient không tự là pool

**WebClient** là client API. Khi underlying connector là Reactor Netty, tài nguyên thật gồm **connection pools và event loops**. Trong Spring Boot 3.3, nên inject **WebClient.Builder** do Boot quản lý để giữ connector/codecs/resource sharing.

~~~java
@Service
public class PartnerClient {
    private final WebClient client;

    public PartnerClient(WebClient.Builder builder) {
        client = builder
                .baseUrl("https://partner.example.test")
                .build();
    }
}
~~~

Đây là snippet, chỉ dùng được khi spring-webflux trên classpath. WebClient object không có một close() chung đóng mọi Netty resources. **Không tạo WebClient.create() mới cho từng request** rồi giả định resources sẽ được quản như bean.

### 8.2. ReactorResourceFactory

Spring cung cấp **ReactorResourceFactory** để quản lý Reactor Netty resources cùng ApplicationContext.

- **Use global resources**: dùng global Reactor Netty HttpResources, thường chia sẻ trong process.
- **Use own resources**: setUseGlobalResources(false), factory tạo/đóng resource riêng; clients/server phải được wiring đúng.
- Spring Boot reactive Netty server có thể auto-configure ReactorResourceFactory; managed WebClient.Builder thường chia sẻ resources với server nếu cùng technology.

Khi một JVM tạo/destroy nhiều contexts (IDE dev tools, integration tests, WAR/external container), global Netty threads có thể tiếp tục sống sau context đóng nếu không quản đúng. **Không dispose global resources từ một client đơn lẻ**.

### 8.3. Cấu hình custom factory cho project WebFlux riêng

File **NettyClientResourcesConfiguration.java**, chỉ thêm khi có **spring-boot-starter-webflux / Reactor Netty**, không nằm trong project MVC demo tiếp theo:

~~~java
package com.example.shutdown.reactive;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.http.client.reactive.ReactorResourceFactory;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class NettyClientResourcesConfiguration {

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        ReactorResourceFactory factory =
                new ReactorResourceFactory();
        factory.setUseGlobalResources(false);
        return factory;
    }

    @Bean
    WebClient partnerWebClient(
            WebClient.Builder builder,
            ReactorResourceFactory resources) {

        ReactorClientHttpConnector connector =
                new ReactorClientHttpConnector(
                    resources,
                    client -> client.responseTimeout(
                            Duration.ofSeconds(3)));

        return builder
                .clientConnector(connector)
                .baseUrl("https://partner.example.test")
                .build();
    }
}
~~~

**API Spring Framework 6.x là setUseGlobalResources(false)**. Nếu dùng Netty web server và client trong cùng app, cân nhắc cùng một resource factory và kiểm tra Boot auto-configuration; việc khai báo custom factory có thể thay behavior mặc định. Placeholder hostname không dùng để thực hiện real call.

### 8.4. ConnectionProvider/LoopResources tự tạo

~~~java
ConnectionProvider provider =
        ConnectionProvider.builder("partner")
                .maxConnections(40)
                .build();

LoopResources loops =
        LoopResources.create("partner-io");
~~~

Snippet cần Reactor Netty imports; hai objects là custom resources với owner rõ. Disposal có thể dùng dispose() hoặc disposeLater() tùy API; nếu dùng disposeLater() trả Publisher, cần **subscribe/await với deadline** ngoài event loop, không chỉ tạo Mono rồi bỏ đó.

### 8.5. MVC dùng WebClient vẫn có Netty threads

Một ứng dụng Servlet MVC dùng WebClient cho outbound HTTP vẫn có thể mang Reactor Netty runtime, dù không có WebFlux server. Vì thế cần xem lifecycle của client connectors/resources, nhất là nếu context được đóng/mở nhiều lần trong cùng JVM. Việc không có Netty server không loại bỏ nhu cầu quản lý Netty HTTP client pool.

## 9. Tệp tạm: xóa khi hoàn tất, không chờ shutdown

### 9.1. Per-job finally

~~~java
Path file = Files.createTempFile(
        "task-", ".tmp");
try {
    Files.writeString(
        file, "temporary", StandardCharsets.UTF_8);
    // Xử lý file.
}
finally {
    Files.deleteIfExists(file);
}
~~~

Snippet Java 17 với imports cần thiết. Đóng InputStream/OutputStream/FileChannel trước khi delete bằng try-with-resources. Trên Windows file handles còn mở có thể gây AccessDeniedException.

### 9.2. Workspace riêng do app sở hữu

Tạo workspace bằng **Files.createTempDirectory("shutdown-demo-")**. Dọn per-task files trong finally; khi shutdown có thể xóa phần còn lại trong owned workspace, nhưng **chỉ sau khi không còn worker ghi file**. Không bao giờ recursive-delete toàn bộ /tmp, java.io.tmpdir, volume chung hoặc đường dẫn lấy từ request.

### 9.3. walkFileTree

~~~java
Files.walkFileTree(root,
    new SimpleFileVisitor<Path>() {
        @Override
        public FileVisitResult visitFile(
                Path file, BasicFileAttributes attrs)
                throws IOException {
            Files.deleteIfExists(file);
            return FileVisitResult.CONTINUE;
        }

        @Override
        public FileVisitResult postVisitDirectory(
                Path dir, IOException error)
                throws IOException {
            if (error != null) throw error;
            Files.deleteIfExists(dir);
            return FileVisitResult.CONTINUE;
        }
    });
~~~

Snippet với root do app sở hữu. Files.walkFileTree mặc định không theo symbolic links nếu không truyền FOLLOW_LINKS; tuy vậy với thư mục có quyền ghi của bên không tin cậy, vẫn cần chống race/path traversal và filesystem permissions.

### 9.4. Multipart upload

MultipartFile và container-managed temporary files có lifecycle request/container riêng. Nếu muốn xử lý upload sau khi HTTP response trả 202, copy vào owned staging area, ghi job state bền vững, đặt TTL/quota và cleanup. Không giữ request-scoped MultipartFile hoặc đường dẫn tạm mà container có thể dọn khi request kết thúc.

### 9.5. SIGKILL và orphan files

SIGKILL, OOMKilled hoặc node crash có thể khiến @PreDestroy không chạy. Cần janitor dựa trên **owner/active lease/TTL**, giới hạn bytes, giữ dữ liệu cần khôi phục và tránh xóa file của replica khác. Không dọn ngẫu nhiên mọi file quá 1 giờ trong thư mục dùng chung. Một cơ chế phục hồi thật phải an toàn khi hai workers cùng chạy.

## 10. Project Maven chạy được: executor, Hikari, Reactor và tệp tạm

Demo gồm:
- **GET /demo/work?value=hello**: submit work vào pool 4 threads, tạo/xóa file tạm, trả JSON.
- **GET /demo/db**: JdbcTemplate gọi H2 qua HikariCP Spring-managed.
- **GET /demo/reactor**: chạy một task trên Scheduler owned bean.
- **Spring @PreDestroy** dừng executor, chờ hoàn tất với deadline, xóa workspace nếu an toàn.
- **@Bean(destroyMethod="dispose")** dọn Reactor Scheduler.
- Tests qua HTTP và đóng một ApplicationContext nhỏ để chứng minh resources đã được giải phóng.

### 10.1. Cây thư mục

~~~text
shutdown-runtime-demo/
  pom.xml
  src/main/java/com/example/shutdown/
    ShutdownApplication.java
    OwnedWorkResources.java
    SchedulerConfiguration.java
    ReactorService.java
    DemoController.java
  src/main/resources/application.yml
  src/test/java/com/example/shutdown/
    ShutdownHttpTest.java
    ShutdownLifecycleTest.java
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>shutdown-runtime-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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
~~~

Spring Boot BOM quản lý version Hikari, Reactor, H2 và Spring Framework. Project dùng Java 17, không cần Java 21 hay WebFlux starter. **Spring Boot 3.3.13 là mốc bài học**, deployment mới cần phiên bản được hỗ trợ và cập nhật bảo mật.

### 10.3. ShutdownApplication.java

~~~java
package com.example.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShutdownApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShutdownApplication.class, args);
    }
}
~~~

### 10.4. OwnedWorkResources.java

~~~java
package com.example.shutdown;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.Locale;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OwnedWorkResources {

    private static final Logger log =
            LoggerFactory.getLogger(OwnedWorkResources.class);

    private final ExecutorService executor =
            Executors.newFixedThreadPool(4);

    private final AtomicBoolean accepting =
            new AtomicBoolean(true);

    private final Path workspace;

    public OwnedWorkResources() throws IOException {
        workspace = Files.createTempDirectory("shutdown-demo-");
    }

    public String transform(String input)
            throws InterruptedException,
                   ExecutionException,
                   TimeoutException {

        if (!accepting.get()) {
            throw new RejectedExecutionException(
                    "Shutdown in progress");
        }

        Future<String> future = executor.submit(() -> {
            Path file = Files.createTempFile(
                    workspace, "job-", ".txt");
            try {
                Files.writeString(
                    file, input, StandardCharsets.UTF_8);
                return Files.readString(
                    file, StandardCharsets.UTF_8)
                    .toUpperCase(Locale.ROOT);
            }
            finally {
                Files.deleteIfExists(file);
            }
        });

        try {
            return future.get(3, TimeUnit.SECONDS);
        }
        catch (TimeoutException ex) {
            future.cancel(true);
            throw ex;
        }
        catch (InterruptedException ex) {
            future.cancel(true);
            Thread.currentThread().interrupt();
            throw ex;
        }
    }

    public Path workspaceForTest() {
        return workspace;
    }

    public boolean terminatedForTest() {
        return executor.isTerminated();
    }

    @PreDestroy
    public void shutdown() {
        accepting.set(false);
        executor.shutdown();

        boolean terminated = false;
        try {
            terminated = executor.awaitTermination(
                    5, TimeUnit.SECONDS);
            if (!terminated) {
                log.warn("Worker drain timed out");
                executor.shutdownNow();
                terminated = executor.awaitTermination(
                        2, TimeUnit.SECONDS);
            }
        }
        catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }

        if (!terminated) {
            // Một task vẫn có thể đang ghi; không xóa directory.
            log.error("Worker still active; leave workspace {}",
                    workspace);
            return;
        }

        try {
            deleteWorkspace(workspace);
            log.info("Owned resources released");
        }
        catch (IOException ex) {
            log.warn("Workspace cleanup failed: {}",
                    workspace, ex);
        }
    }

    private static void deleteWorkspace(Path root)
            throws IOException {
        if (!Files.exists(root)) {
            return;
        }

        Files.walkFileTree(root,
            new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs)
                        throws IOException {
                    Files.deleteIfExists(file);
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException failure)
                        throws IOException {
                    if (failure != null) throw failure;
                    Files.deleteIfExists(dir);
                    return FileVisitResult.CONTINUE;
                }
            });
    }
}
~~~

**Cơ chế:**
1. Spring singleton tạo executor và owned workspace đúng một lần.
2. Mỗi task có file riêng, xóa trong finally ngay sau xử lý.
3. accepting=false trước executor.shutdown hạn chế task mới; vẫn bắt RejectedExecutionException vì submit race.
4. Future.get có timeout 3s; cancel(true) chỉ yêu cầu interrupt.
5. @PreDestroy chờ pool dừng 5s, fallback shutdownNow và 2s nữa.
6. Nếu pool vẫn active, giữ workspace thay vì xóa trong lúc task có thể còn ghi.
7. Chỉ xóa directory do component tạo, không dọn java.io.tmpdir chung.
8. Các thời hạn chỉ để lab, production phải cân đối với Kubernetes termination budget.
9. Class này không sở hữu Hikari hoặc Reactor Scheduler, nên không tự đóng hai resources đó.
10. File delete fail có thể khiến Future trả ExecutionException; application cần log/alert cleanup failure.

### 10.5. SchedulerConfiguration.java

~~~java
package com.example.shutdown;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
public class SchedulerConfiguration {
    @Bean(destroyMethod = "dispose")
    public Scheduler applicationScheduler() {
        return Schedulers.newBoundedElastic(
                2, 32, "shutdown-adapter");
    }
}
~~~

Đây là custom Scheduler do Spring bean sở hữu; destroyMethod=dispose đảm bảo cleanup khi context đóng, không dừng global Schedulers.

### 10.6. ReactorService.java

~~~java
package com.example.shutdown;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;

@Service
public class ReactorService {

    private final Scheduler scheduler;

    public ReactorService(
            @Qualifier("applicationScheduler")
            Scheduler scheduler) {
        this.scheduler = scheduler;
    }

    public String execute() {
        return Mono.fromCallable(() -> "reactor-ok")
                .subscribeOn(scheduler)
                .block(Duration.ofSeconds(2));
    }
}
~~~

Block() ở đây được gọi **từ MVC worker thread**, không phải từ WebFlux Netty event loop. Trên reactive event loop, dùng block() là anti-pattern; cần compose Mono/Flux hoặc offload blocking adapter phù hợp.

### 10.7. DemoController.java

~~~java
package com.example.shutdown;

import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeoutException;

import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DemoController {

    private final OwnedWorkResources workers;
    private final JdbcTemplate jdbc;
    private final ReactorService reactor;

    public DemoController(
            OwnedWorkResources workers,
            JdbcTemplate jdbc,
            ReactorService reactor) {
        this.workers = workers;
        this.jdbc = jdbc;
        this.reactor = reactor;
    }

    @GetMapping("/demo/work")
    public Map<String, String> work(
            @RequestParam(defaultValue = "hello")
            String value) {

        if (!value.matches("[A-Za-z0-9-]{1,50}")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid input");
        }

        try {
            return Map.of("result", workers.transform(value));
        }
        catch (RejectedExecutionException ex) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Worker is draining", ex);
        }
        catch (TimeoutException ex) {
            throw new ResponseStatusException(
                    HttpStatus.GATEWAY_TIMEOUT,
                    "Work timed out", ex);
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Work interrupted", ex);
        }
        catch (ExecutionException ex) {
            throw new ResponseStatusException(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    "Worker failed", ex);
        }
    }

    @GetMapping("/demo/db")
    public Map<String, Integer> database() {
        Integer answer =
                jdbc.queryForObject("select 1", Integer.class);
        return Map.of("answer", answer);
    }

    @GetMapping("/demo/reactor")
    public Map<String, String> reactor() {
        return Map.of("result", reactor.execute());
    }
}
~~~

REST controller demo giới hạn input, không nhận path tùy ý từ user và không expose workspace location. HTTP 503 minh họa khi worker đã ngừng nhận việc. Hikari pool được dùng gián tiếp bởi JdbcTemplate, không được controller đóng.

### 10.8. application.yml

~~~yaml
spring:
  application:
    name: shutdown-runtime-demo
  lifecycle:
    timeout-per-shutdown-phase: 20s
  datasource:
    generate-unique-name: true
    hikari:
      maximum-pool-size: 4
      connection-timeout: 2000

server:
  port: 8080
  shutdown: graceful

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics"
  endpoint:
    health:
      show-details: never
~~~

H2 được auto-configure khi có starter-jdbc và H2 runtime dependency. HikariCP bean có lifecycle do Spring Boot quản lý; không có code thủ công close Hikari. Actuator metrics chỉ expose trong lab; production cần hạn chế network/auth.

### 10.9. Chạy và output

Linux/macOS:

~~~bash
mvn clean package
java -jar target/shutdown-runtime-demo-0.0.1-SNAPSHOT.jar
~~~

Windows:

~~~text
mvn.cmd clean package
java -jar target/shutdown-runtime-demo-0.0.1-SNAPSHOT.jar
~~~

Thử:

~~~bash
curl -i "http://localhost:8080/demo/work?value=hello"
curl -i http://localhost:8080/demo/db
curl -i http://localhost:8080/demo/reactor
curl -i http://localhost:8080/actuator/health
~~~

**Kỳ vọng** 200 và body:

~~~text
/demo/work?value=hello  -> {"result":"HELLO"}
/demo/db                -> {"answer":1}
/demo/reactor           -> {"result":"reactor-ok"}
/actuator/health        -> {"status":"UP"}
~~~

Đó là cấu trúc output, không khẳng định HTTP Date/Content-Length/header order cố định. Sau /demo/work, file job-*.txt đã bị xóa, nhưng workspace directory có thể còn tới shutdown.

Trên Linux, để gửi SIGTERM:

~~~bash
ps -ef | grep shutdown-runtime-demo
kill -TERM PID_THUC_TE
~~~

Thay PID_THUC_TE bằng process ID. Đừng dùng kill -9 nếu muốn kiểm tra graceful shutdown. Quan sát Tomcat graceful logs, OwnedWorkResources cleanup, HikariPool shutdown và process exit.

## 11. Tests qua HTTP và đóng context

### 11.1. ShutdownHttpTest.java

~~~java
package com.example.shutdown;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ShutdownHttpTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void canUseExecutorDatabaseAndReactor() {
        String work = http.getForObject(
                "/demo/work?value=hello", String.class);
        String db = http.getForObject(
                "/demo/db", String.class);
        String reactor = http.getForObject(
                "/demo/reactor", String.class);

        assertThat(work).contains("HELLO");
        assertThat(db).contains("\"answer\":1");
        assertThat(reactor).contains("reactor-ok");
    }

    @Test
    void rejectsInvalidInput() {
        var response = http.getForEntity(
                "/demo/work?value=%21", String.class);
        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
    }
}
~~~

RANDOM_PORT gửi request qua embedded Tomcat thực, không chỉ MockMvc. Nó chứng minh API hoạt động **trước shutdown**, chưa chứng minh resources đã được giải phóng.

### 11.2. ShutdownLifecycleTest.java

~~~java
package com.example.shutdown;

import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import reactor.core.scheduler.Scheduler;

import static org.assertj.core.api.Assertions.assertThat;

class ShutdownLifecycleTest {

    @Test
    void executorAndWorkspaceAreReleased()
            throws Exception {

        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();
        context.registerBean(OwnedWorkResources.class);
        context.refresh();

        OwnedWorkResources worker =
                context.getBean(OwnedWorkResources.class);
        Path dir = worker.workspaceForTest();

        try {
            assertThat(Files.isDirectory(dir)).isTrue();
            assertThat(worker.transform("hello"))
                    .isEqualTo("HELLO");

            try (var files = Files.list(dir)) {
                assertThat(files.count()).isZero();
            }
        }
        finally {
            context.close();
        }

        assertThat(worker.terminatedForTest()).isTrue();
        assertThat(Files.exists(dir)).isFalse();
    }

    @Test
    void customSchedulerIsDisposed() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    SchedulerConfiguration.class);
        Scheduler scheduler = context.getBean(
                "applicationScheduler", Scheduler.class);

        try {
            assertThat(scheduler.isDisposed()).isFalse();
        }
        finally {
            context.close();
        }

        assertThat(scheduler.isDisposed()).isTrue();
    }
}
~~~

AnnotationConfigApplicationContext tạo một Spring context **riêng**, đăng ký callbacks và destroy beans khi close. Không đóng shared @SpringBootTest context trong một test vì có thể làm những tests khác fail. Test đầu chứng minh executor và workspace được cleanup; test thứ hai chứng minh custom Scheduler dispose. Để xác minh HikariPool.close cần test full Boot context closure hoặc SIGTERM integration test riêng; không dùng test này để tuyên bố Hikari đã được khởi tạo ở context nhỏ.

Chạy:

~~~bash
mvn test
~~~

**Chưa có Maven runtime execution trong tài liệu**: đây là project và tests để người học sao chép và chạy. Tất cả public classes, packages và paths đã được liệt kê khớp cấu trúc project.

## 12. SmartLifecycle cho queue consumer trước worker pool

Một hệ thống ngoài HTTP có thể dùng pipeline:

~~~text
Kafka/Rabbit consumer polling
    -> executor task
    -> JDBC transaction / external HTTP POST
~~~

Khi shutdown, dừng consumer poll trước để ngừng nhận jobs mới; hoàn tất/checkpoint in-flight work; sau đó mới đóng JDBC/HTTP pools. Một skeleton SmartLifecycle:

~~~java
@Component
public class IntakeGate implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
    }

    @Override
    public void stop() {
        running = false;
    }

    @Override
    public void stop(Runnable callback) {
        try {
            running = false;
        }
        finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
~~~

Snippet cần imports Spring SmartLifecycle/@Component, chưa là consumer thật. **Phase 100 không tự bảo đảm dừng trước Boot web server internal phase**. Khi có async stop logic, phải gọi callback sau khi stop hoàn tất, không gọi ngay rồi producer vẫn tiếp tục enqueue.

## 13. Kubernetes readiness và terminationGracePeriodSeconds

### 13.1. Pod termination

~~~text
Pod marked terminating / EndpointSlices update
    -> optional preStop
    -> JVM receives SIGTERM
    -> readiness REFUSING_TRAFFIC
    -> web server graceful drain
    -> custom task drain and resource close
    -> JVM exit
    -> if deadline exceeded: SIGKILL
~~~

Các bước có thể chồng lấp vì load balancer propagation delay. Readiness=false không chặn direct Pod IP traffic như firewall; cần retry/idempotency cho connections đang mở.

### 13.2. Deployment YAML

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shutdown-runtime-demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: shutdown-runtime-demo
  template:
    metadata:
      labels:
        app: shutdown-runtime-demo
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: example.invalid/shutdown-runtime-demo:1.0
          ports:
            - name: http
              containerPort: 8080
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
~~~

Đây là mẫu, image example.invalid không tồn tại và cần thay; phải thêm Service, resource limits, security policy khi deploy. Spring Boot 3.3 thường auto-enable liveness/readiness groups trong Kubernetes; local có thể đặt **management.endpoint.health.probes.enabled=true**. Nếu management.server.port riêng, cân nhắc additional paths /livez và /readyz trên main port.

**45 giây không phải con số tốt nhất cho mọi hệ thống**. Cần đo tổng thời gian web drain (20s trong lab), executor wait (tối đa khoảng 7s), Hikari/Reactor/file cleanup, preStop và ingress overhead. Nếu Pod bị SIGKILL trước cleanup, phải có durable recovery.

### 13.3. Task kéo dài hơn deadline

Không thiết kế background job nhiều phút phải hoàn thành hoàn toàn bên trong Kubernetes grace period. Dùng durable queue, checkpoint, lease, idempotent retry và status persistence. Stop accepting new jobs trước; những jobs chưa hoàn tất được giao lại hợp lệ khi worker khởi động lại.

## 14. Giám sát cleanup

| Metric/log | Ý nghĩa |
| --- | --- |
| Shutdown duration | SIGTERM đến exit có nằm trong grace budget? |
| HTTP in-flight/connection drain | Server có chờ request dài thành công? |
| Executor active/queue/rejections | Tasks đang chờ, bị hủy hay bị từ chối? |
| Hikari active/idle/pending | Connections chưa trả hoặc pool nghẽn? |
| Reactor Scheduler pending/disposed | Có tasks bị reject sau dispose? |
| Netty active/idle connections, event loops | Global/custom resources có được dọn? |
| Temporary file count/bytes | File leak hoặc orphan backlog? |
| JVM threads/file descriptors | Có non-daemon thread/socket/file handle còn sống? |
| Kubernetes exit reason/OOMKilled | Shutdown bình thường hay force kill? |
| Cleanup exceptions | Có IO/security errors, retry policy? |

Với Actuator có thể xem:

~~~bash
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/metrics/hikaricp.connections.active
curl -i http://localhost:8080/actuator/metrics/hikaricp.connections.pending
~~~

Metrics chưa xuất hiện trước khi pool được sử dụng hoặc khi configuration khác; không kết luận leak chỉ dựa vào 404 metric. Để quan sát custom executor queue/temp file count, phải instrument riêng. Không log file contents, credentials, Authorization headers hoặc thông tin cá nhân.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| JVM không thoát sau SIGTERM | Executor tự tạo giữ non-daemon threads | Thread dump, thêm owner shutdown. |
| HTTP dừng, task vẫn chạy | Detached job ngoài HTTP graceful lifecycle | Await/persist/queue transfer. |
| SQL lỗi giữa shutdown | Hikari đóng trước request hoặc job hoàn tất | Ownership Spring DataSource, drain trước. |
| RejectedExecutionException | Producer submit sau shutdown | Stop intake và xử lý race. |
| shutdownNow không dừng task | Task bỏ qua interrupt hoặc native blocking | Timeout, checkpoint, cooperative cancel. |
| Pod SIGKILL trước cleanup | Shutdown vượt grace | Cân đối phase deadlines và durable jobs. |
| Hikari connections pending tăng | DB pool cạn hoặc connections bị giữ | Trace transaction/SQL/try-with-resources. |
| WebClient vẫn giữ Netty threads | Context lifecycle chưa quản resources global | ReactorResourceFactory và shared ownership. |
| Custom Scheduler tasks bị reject | dispose trước khi subscription xong | Cancel/drain rồi dispose. |
| Global Reactor code bị lỗi | Schedulers.shutdownNow gọi sai scope | Chỉ dispose owned schedulers. |
| Tệp tạm tăng liên tục | Chỉ xóa ở @PreDestroy | finally per job, quota và janitor. |
| Windows không xóa được file | Stream/channel chưa close | try-with-resources trước Files.deleteIfExists. |
| Cleanup xóa file khác | Xóa directory chung hoặc path từ input | Owned workspace, không recursive-delete /tmp. |
| @PreDestroy không chạy | Direct new, context chưa close, SIGKILL | Bean management và recovery. |
| Test suite bị lỗi sau test shutdown | Test đóng shared SpringBootTest context | Dùng isolated lifecycle context. |

## 16. Quy trình điều tra

1. Kiểm tra process nhận SIGTERM hay đã bị SIGKILL.
2. Xác minh Boot server.shutdown=graceful và timeout-per-shutdown-phase.
3. Đếm HTTP requests đang xử lý và background queue tasks.
4. Liệt kê owners của custom executors, schedulers, clients và temp dirs.
5. Thread dump để tìm non-daemon workers, deadlocks và blocking calls.
6. Đo Hikari active/pending connections, transaction duration.
7. Kiểm tra Reactor subscriptions, Scheduler dispose và Netty pool owner.
8. Kiểm tra file handles và workspace cleanup logs.
9. Đối chiếu Kubernetes grace period, ingress propagation, OOMKilled.
10. Test lại trên staging có request dài và Pod rollover; lập runbook với owner, deadline, remediation.

## 17. Bài tập

### Bài 1 — Executor drain
Tạo task mất hai giây trong bản sao lab, SIGTERM khi task còn chạy. Quan sát shutdown/await/shutdownNow và file cleanup. Giải thích vì sao không nên đặt awaitTermination vô hạn.

### Bài 2 — JDBC pool
Gọi /demo/db nhiều lần và quan sát Hikari metrics. Giải thích sự khác biệt giữa Connection.close() với HikariDataSource.close(), và hậu quả của việc đóng pool khi một transaction còn chạy.

### Bài 3 — Reactor lifecycle
Dùng @Bean custom Scheduler, đóng ApplicationContext riêng và assert isDisposed=true. So với shared Schedulers.boundedElastic, tránh shutdownNow global.

### Bài 4 — Reactor Netty
Trong một project WebFlux riêng, dùng managed WebClient.Builder và ReactorResourceFactory, khởi động/đóng context lặp lại và đếm Netty threads/sockets. Đảm bảo custom factory được cùng client/server dùng đúng.

### Bài 5 — Temporary files
Thử 100 requests, xác nhận không còn job-*.txt giữa requests; sau context.close workspace biến mất. Tạo orphan file giả lập và thiết kế TTL+lease cleanup, không xóa /tmp.

### Bài 6 — Durable jobs
Chuyển /demo/work sang POST /jobs trả 202, rồi thiết kế durable state/queue/lease, retry idempotent sau SIGKILL để không mất tác vụ hoặc làm lặp side effects.

### Bài 7 — Kubernetes rollout
Gửi request dài trên staging trong lúc rolling restart. Đo graceful completion, connection drain, resource cleanup, process exit time, và điều chỉnh terminationGracePeriodSeconds theo số đo thật.

## 18. Checklist trước production

- [ ] Mỗi resource có owner, init, users, stop-intake, close API và deadline.
- [ ] Web server graceful shutdown và request drain được kiểm chứng.
- [ ] Executors có bounded shutdown/await và task cancellation policy.
- [ ] Background detached jobs có durable persistence khi cần.
- [ ] Spring-managed Hikari DataSource không bị đóng quá sớm.
- [ ] Connection/Statement/ResultSet được trả đúng transaction/request scope.
- [ ] HTTP client connection pools có ownership rõ.
- [ ] Custom Reactor Scheduler được dispose; shared Scheduler không shutdown sai.
- [ ] ReactorResourceFactory/Netty resources được dùng và đóng nhất quán.
- [ ] Subscriptions được drain/cancel trước khi đóng dependencies.
- [ ] Tệp tạm xóa trong finally, streams/channels đóng trước delete.
- [ ] Chỉ dọn owned workspace sau khi workers dừng.
- [ ] Có orphan recovery khi SIGKILL, OOMKilled, restart.
- [ ] Lifecycle callbacks không trùng hoặc block vô hạn.
- [ ] Context-close tests và staging SIGTERM tests đều có.
- [ ] Kubernetes grace period, readiness, ingress propagation được đo.
- [ ] Metrics/logs có resource leaks, failures, duration, không lộ secrets.

## 19. Câu hỏi tự kiểm tra

**1. server.shutdown=graceful có tự đóng ExecutorService tự tạo không?** Không. Nó chỉ giải quyết web server graceful drain; custom pool phải có owner.

**2. shutdownNow() bảo đảm dừng mọi tasks?** Không, đó là best-effort interruption.

**3. Connection.close() có đóng Hikari pool?** Không; pooled connection thường được trả về pool.

**4. @PreDestroy có chạy sau SIGKILL?** Không được bảo đảm. Cần crash recovery.

**5. Vì sao không xóa thư mục tạm khi vừa nhận SIGTERM?** Worker có thể còn ghi file. Stop/await trước, delete sau.

**6. Khi nào dùng SmartLifecycle?** Khi cần stop có phase và callback điều phối producer/worker/dependencies.

**7. Schedulers.newBoundedElastic và Schedulers.boundedElastic khác nhau?** new tạo Scheduler riêng, boundedElastic là shared; không đóng shared từ component con.

**8. WebClient có close() duy nhất đóng mọi Netty resources?** Không. Cleanup phải theo resource factory/connector owner.

**9. HTTP 202 đã gửi có nghĩa background job được graceful web server chờ?** Không. Detached work cần drain/durable queue riêng.

**10. Timeout-per-shutdown-phase giới hạn toàn bộ @PreDestroy?** Không, cần deadline riêng cho cleanup.

## 20. Tài liệu tham khảo

1. [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): server.shutdown, phase timeout và hành vi web servers.
2. [Spring Framework — Bean Destruction](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): @PreDestroy, destroy methods, lifecycle callbacks và SmartLifecycle.
3. [Spring Boot 3.3 — SQL Databases](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html): DataSource/Hikari, embedded H2 và pooling.
4. [Spring Boot 3.3 — Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): managed WebClient.Builder và HTTP resources.
5. [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): ReactorResourceFactory và Netty sharing.
6. [Spring Framework — WebClient Resources](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): global/managed Reactor Netty resources.
7. [Reactor — Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): custom/shared schedulers.
8. [Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown và awaitTermination.
9. [Java 17 — Files API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): createTempFile, deleteIfExists, walkFileTree.
10. [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#termination-of-pods): SIGTERM, preStop, deadline và SIGKILL.

**Kết luận:** Dừng ứng dụng đúng là **ngừng tiếp nhận việc mới, drain việc đang xử lý, giải phóng những tài nguyên do mình sở hữu theo thứ tự**, và xác minh kết quả. Spring Boot graceful shutdown xử lý HTTP nhưng không tự đóng mọi executor hoặc file tạm; để container đóng Hikari đúng lúc, dispose chỉ Reactor resources riêng, và luôn dọn tệp per-job bằng finally. Vì SIGKILL có thể cắt ngang mọi callbacks, hệ thống production cần durable recovery, deadline và monitoring thay vì chỉ tin vào @PreDestroy.