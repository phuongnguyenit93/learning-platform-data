# Tránh đóng tài nguyên khi thành phần phụ thuộc còn hoạt động — Spring Boot 3.3

## 1. Bài toán và mục tiêu

Trong Spring Boot, những đối tượng như `DataSource`, HTTP client, Kafka/RabbitMQ connection, file stream, socket, task executor hoặc cache manager thường được chia sẻ cho nhiều thành phần. Khi một component đang thực thi công việc dựa trên resource A, việc đóng A quá sớm có thể làm hỏng tiến trình đang chạy.

Ví dụ:

```text
Một consumer vẫn đang xử lý message
   |
   +-- Dùng JDBC transaction và gửi ACK qua broker client
   |
Ứng dụng đóng context
   |
   +-- Broker client.close() quá sớm
   |
   +-- Consumer cố ACK => lỗi, có thể xử lý lại message
```

**Mục tiêu không phải giữ tài nguyên mở mãi, mà là dừng người tiêu thụ trước khi resource owner đóng tài nguyên.** Điều này đòi hỏi phân biệt:

- **Bean initialization/destroy**: Spring tạo và hủy các bean theo dependency graph.
- **Component running/stopping**: một consumer vẫn có thể thực hiện công việc dù bean đã bắt đầu shutdown.
- **Async task completion**: việc gửi yêu cầu dừng không chứng minh tất cả tác vụ đã thực sự dừng.
- **Resource ownership**: service mượn tài nguyên không được tự đóng tài nguyên chia sẻ.
- **Operational readiness**: service có thể ngừng nhận việc mới trước khi đóng hẳn.

Sau bài học bạn cần giải thích được `@PreDestroy`, `@DependsOn`, constructor injection, `SmartLifecycle.getPhase()`, `stop(Runnable)`, `ApplicationContext.close()`, Spring Boot graceful shutdown và cách phối hợp drain, timeout, retry trong code Java 21/Spring Boot 3.3.

## 2. Vòng đời khác nhau ở những điểm nào?

| Thời điểm | Ý nghĩa | Ngộ nhận cần tránh |
| --- | --- | --- |
| Constructor | Một instance Java đã được tạo | Chưa chắc resource đã sẵn sàng |
| Dependency injection | Tham chiếu tới dependency được cung cấp | Chưa chắc task nền đã xong |
| `@PostConstruct` | Callback khởi tạo của bean | Không tự chờ các future do nó khởi chạy |
| `SmartLifecycle.start()` | Component bắt đầu hoạt động | Có thể diễn ra trước các runner |
| `ApplicationReadyEvent` | Boot đã hoàn tất luồng startup thành công và các runners | Không tự chứng minh mọi background task đã hoàn thành |
| `SmartLifecycle.stop(Runnable)` | Dừng hoạt động, báo completion cho lifecycle processor | Không được gọi callback khi mới enqueue công việc dừng |
| `@PreDestroy` | Cleanup trong giai đoạn destroy bean | Không thay thế việc drain công việc đang chạy |
| `ApplicationContext.close()` | Đóng context, dừng lifecycle beans, destroy singleton | Context không thể start trở lại sau close |

Hai trạng thái dễ nhầm nhất là **“đã yêu cầu stop”** và **“đã stop xong”**.

```text
RUNNING
  |
  | ngừng nhận việc mới
  v
STOPPING
  |
  | chờ in-flight tasks; flush/checkpoint/ACK; cancel có kiểm soát
  v
STOPPED
  |
  | resource owner đóng resource
  v
CLOSED
```

`@PreDestroy` được gọi muộn hơn trong bean destruction, nhưng không bảo đảm tác vụ đang dùng resource sẽ kết thúc nếu consumer không phối hợp.

## 3. Ai được quyền đóng resource?

Có thể chia thành ba vai trò:

| Vai trò | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Owner** | Tạo, cấu hình, đóng resource | Spring-managed HikariDataSource, HTTP client bean, broker connection factory |
| **Borrower/consumer** | Sử dụng resource, trả lại tài nguyên mượn đúng hạn | Repository, message handler, report exporter |
| **Coordinator** | Dừng tiếp nhận, drain công việc, sắp thứ tự shutdown | SmartLifecycle, listener container, job controller |

### 3.1. Không đóng shared DataSource từ service

```java
@Service
class InvoiceReport {
    private final DataSource dataSource;

    InvoiceReport(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    void run() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            // Thực hiện thao tác SQL...
        }
    }
}
```

Đây là **đoạn minh họa không độc lập**, cần imports và logic truy vấn thật. `Connection.close()` thường trả connection được mượn lại cho pool. Nhưng service **không được gọi `dataSource.close()`** khi pool được dùng chung với những service khác: đóng pool là trách nhiệm của resource owner/container.

Ngược lại, nếu một method tự tạo stream riêng và chỉ sử dụng đồng bộ:

```java
try (InputStream input = Files.newInputStream(path)) {
    return parse(input);
}
```

thì `try-with-resources` phù hợp. **Sai** khi method truyền `input` sang worker thread rồi thoát block `try`, vì stream sẽ bị đóng trước khi worker kịp đọc.

### 3.2. Spring quản lý bean resource

Các cơ chế phổ biến:

- `@Component` + `@PreDestroy`.
- `@Bean` và destroy callback/destroy method tương ứng.
- `DisposableBean.destroy()` hoặc `AutoCloseable` được bean lifecycle quản lý phù hợp.
- `SmartLifecycle` để bật/tắt hoạt động và phối hợp start/stop với các thành phần khác.

Đừng để nhiều consumers tự động gọi `close()` trên cùng một object dùng chung. Nếu resource có idempotent close, điều đó chỉ giúp giảm lỗi double-close, **không** giải quyết lỗi close quá sớm.

## 4. Dependency graph và @DependsOn

### 4.1. Constructor injection diễn đạt dependency thật

```java
@Component
class AuditConsumer {
    private final SharedGateway gateway;

    AuditConsumer(SharedGateway gateway) {
        this.gateway = gateway;
    }
}
```

Đoạn này minh họa một bean `SharedGateway` chưa được khai báo. Vì consumer nhận gateway qua constructor, Spring biết consumer phụ thuộc gateway. Với singleton beans, quan hệ dependency được container biết giúp **destroy dependent bean trước dependency bean**.

Nếu B thực sự dùng API của A, constructor injection rõ ràng, type-safe và dễ test hơn việc giữ bean name dạng chuỗi.

### 4.2. Phụ thuộc gián tiếp và @DependsOn

Nếu B cần side effect initialization của A nhưng không inject A:

```java
@Component("startupRegistrar")
class StartupRegistrar {
}

@Component
@DependsOn("startupRegistrar")
class DependentWorker {
}
```

Đây là **mã minh họa**, cần imports. `@DependsOn` dùng **tên bean** `startupRegistrar`; nó yêu cầu Spring initialize A trước B. Với singleton beans, phụ thuộc này còn tạo thứ tự destroy đảo chiều: B bị destroy trước A.

Cần phân biệt: `@DependsOn` giúp thứ tự **bean initialization/destruction**, nhưng **không tự tạo ràng buộc đợi một async task đang dùng A**. Nếu `DependentWorker.@PreDestroy` chỉ enqueue một future rồi trả về, provider vẫn có thể đóng khi future chưa hoàn tất.

### 4.3. Vì sao @Order không đủ?

`@Order` thường dùng để sắp collection, runner hoặc callback ở những extension points hỗ trợ ordering. Nó **không phải hợp đồng shutdown** cho tất cả singleton beans. Muốn điều phối component start/stop, cần `SmartLifecycle.getPhase()` cùng dependency graph; muốn đợi async completion, cần future/latch/ack/stop callback hợp lệ.

## 5. SmartLifecycle và shutdown theo phase

Spring Framework 6.1 dùng `DefaultLifecycleProcessor` để điều phối `Lifecycle`/`SmartLifecycle` beans.

- Các components có **phase nhỏ start trước**.
- Các components có **phase lớn stop trước**.
- Quan hệ dependency được Spring biết có thể **được ưu tiên hơn phase**: một dependency sẽ start trước dependent và stop sau dependent.
- Các bean cùng phase nhưng không có dependency rõ ràng không nên được giả định có thứ tự theo alphabet.
- `SmartLifecycle.isAutoStartup()` mặc định là `true`: component có thể start trong `refresh()` trước `ApplicationRunner`.
- `SmartLifecycle.stop(Runnable)` cho phép báo khi shutdown async đã hoàn thành; callback phải được gọi sau khi xử lý stop theo policy.

Ví dụ:

```text
ResourceGateway:   phase = 0
MessageConsumer:   phase = 100

START: ResourceGateway.start() -> MessageConsumer.start()
STOP:  MessageConsumer.stop(callback) -> ResourceGateway.stop(callback)
```

Đây là thiết kế phù hợp khi consumer cần gateway để flush/ack ở cuối, nhưng gateway phải tồn tại tới khi consumer không còn dùng nó.

### 5.1. stop() khác stop(Runnable)

Với `SmartLifecycle`:

```java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    }
    finally {
        callback.run();
    }
}
```

Đây là mẫu **dừng đồng bộ**. Callback ở `finally` giúp tránh lifecycle processor bị chờ mãi khi có lỗi, nhưng **không biến việc cleanup thất bại thành thành công**. Production phải log/metric lỗi, báo trạng thái và có fallback rõ ràng.

Nếu quá trình dừng bất đồng bộ, **không** làm:

```java
@Override
public void stop(Runnable callback) {
    executor.execute(this::drainAndClose);
    callback.run(); // SAI: công việc có thể chưa hoàn tất.
}
```

Đây là anti-pattern, không phải code độc lập; cần executor và method tương ứng. Callback cần được gọi sau khi `drainAndClose` thực sự xong, hoặc sau khi chính sách timeout/error đã xử lý đến trạng thái không thể tiếp tục đợi.

### 5.2. Vòng đời container và thời điểm close

`ConfigurableApplicationContext.stop()` yêu cầu dừng các lifecycle components đang chạy nhưng **không** destroy toàn bộ singleton; có thể start lại nếu implementation hỗ trợ.

`ConfigurableApplicationContext.close()` điều phối stop cho các lifecycle components rồi destroy beans. Context đã đóng không thể mở lại bằng `start()`.

Dù callbacks có thứ tự hợp lệ, `close()` không phải durable transaction và không bảo đảm task được lưu qua một lần crash hoặc `SIGKILL`.

## 6. Ví dụ Java 21 và Spring Boot 3.3.13 chạy được

Demo non-web gồm:

- `ResourceGateway`: resource owner mô phỏng, `SmartLifecycle` phase **0**, không cho gọi `use()` sau stop.
- `DependentConsumer`: inject `ResourceGateway`, `SmartLifecycle` phase **100**; trong stop nó còn dùng gateway để thực hiện final-drain rồi mới ngừng.
- `LifecycleTrace`: ghi các sự kiện vào danh sách.
- `SafeShutdownApplication`: khởi động, đóng context, in toàn bộ trace sau shutdown.
- `SafeShutdownTest`: kiểm tra thứ tự bằng JUnit, không phụ thuộc `Thread.sleep`.

Demo chỉ mô phỏng thao tác đồng bộ, giúp kiểm tra **hợp đồng thứ tự lifecycle** một cách xác định. Với background tasks thật, cần mở rộng bằng completion protocol ở mục 9.

### 6.1. Cấu trúc tệp

```text
safe-shutdown-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/shutdown/
    │   ├── SafeShutdownApplication.java
    │   ├── LifecycleTrace.java
    │   ├── ResourceGateway.java
    │   └── DependentConsumer.java
    └── test/java/com/example/shutdown/
        └── SafeShutdownTest.java
```

### 6.2. Maven pom.xml

```xml
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
    <artifactId>safe-shutdown-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
```

Java 21 chạy được với Boot 3.3.13; starter cơ bản cung cấp Spring context, lifecycle và Jakarta annotations. Test starter cung cấp JUnit Jupiter.

### 6.3. LifecycleTrace.java

```java
package com.example.shutdown;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.stereotype.Component;

@Component
public class LifecycleTrace {
    private final CopyOnWriteArrayList<String> steps =
            new CopyOnWriteArrayList<>();

    public void add(String step) {
        steps.add(step);
    }

    public List<String> snapshot() {
        return List.copyOf(steps);
    }
}
```

Đây là bean ghi các bước lifecycle. Trong demo các events chạy tuần tự, nhưng `CopyOnWriteArrayList` cũng hỗ trợ trường hợp phát trace từ threads khác khi mở rộng.

### 6.4. ResourceGateway.java

```java
package com.example.shutdown;

import jakarta.annotation.PreDestroy;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class ResourceGateway implements SmartLifecycle {

    private final LifecycleTrace trace;
    private volatile boolean running;

    public ResourceGateway(LifecycleTrace trace) {
        this.trace = trace;
    }

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }
        running = true;
        trace.add("RESOURCE start");
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }
        running = false;
        trace.add("RESOURCE stop");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
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
        return 0;
    }

    public synchronized void use(String taskName) {
        if (!running) {
            throw new IllegalStateException("Resource is already closed");
        }
        trace.add("RESOURCE used: " + taskName);
    }

    @PreDestroy
    void destroy() {
        trace.add("RESOURCE destroy");
    }
}
```

`start()`/`stop()` mô phỏng mở/đóng resource; `use()` từ chối nếu resource đã stop. Đây không phải một connection pool thật: mọi lần gọi đều đồng bộ và có thể kiểm chứng thứ tự.

`@PreDestroy` ghi nhận bước destroy sau khi lifecycle stop. Với resource thật, đây có thể là bước giải phóng cuối cùng; phải đảm bảo component khác không còn sử dụng.

### 6.5. DependentConsumer.java

```java
package com.example.shutdown;

import jakarta.annotation.PreDestroy;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class DependentConsumer implements SmartLifecycle {

    private final ResourceGateway gateway;
    private final LifecycleTrace trace;
    private volatile boolean running;

    public DependentConsumer(ResourceGateway gateway, LifecycleTrace trace) {
        this.gateway = gateway;
        this.trace = trace;
    }

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }
        if (!gateway.isRunning()) {
            throw new IllegalStateException("Gateway must start first");
        }
        running = true;
        trace.add("CONSUMER start");
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }
        gateway.use("final-drain");
        running = false;
        trace.add("CONSUMER stop");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
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

    @PreDestroy
    void destroy() {
        trace.add("CONSUMER destroy");
    }
}
```

`DependentConsumer` inject `ResourceGateway` bằng constructor: **Spring biết dependency thật**, không cần thêm `@DependsOn` chỉ để diễn đạt lại một object đã inject. Consumer start ở phase 100; provider phase 0 đã running.

Khi đóng context, consumer thực hiện `gateway.use("final-drain")` khi gateway vẫn còn mở, rồi báo đã stop. Sau đó provider mới stop. `@PreDestroy` của consumer sẽ chạy trước `@PreDestroy` của provider theo quan hệ singleton dependency.

**Lưu ý:** ví dụ không tự động đợi một task async nào khác, bởi nó không tạo task nền. Trong production, việc gọi `gateway.use()` cuối chỉ được thực hiện sau khi dừng nhận việc mới và xử lý in-flight jobs đúng policy.

### 6.6. SafeShutdownApplication.java

```java
package com.example.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class SafeShutdownApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(SafeShutdownApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = app.run(args);
        LifecycleTrace trace = context.getBean(LifecycleTrace.class);

        try (context) {
            ResourceGateway resource = context.getBean(ResourceGateway.class);
            DependentConsumer consumer =
                    context.getBean(DependentConsumer.class);

            trace.add("MAIN resource=" + resource.isRunning()
                    + " consumer=" + consumer.isRunning());
        }

        trace.snapshot().forEach(System.out::println);
    }
}
```

`try (context)` đóng context có kiểm soát sau khi startup thành công. Trace được in sau khi destroy callbacks đã chạy. Do đó không cần đoán thứ tự log xen giữa banner và thông báo Spring Boot.

### 6.7. Chạy và đọc output

Trong thư mục project:

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/safe-shutdown-demo-0.0.1-SNAPSHOT.jar
```

Các dòng được `LifecycleTrace` in sau khi context đóng:

```text
RESOURCE start
CONSUMER start
MAIN resource=true consumer=true
RESOURCE used: final-drain
CONSUMER stop
RESOURCE stop
CONSUMER destroy
RESOURCE destroy
```

Lý giải:

1. Resource phase 0 start trước consumer phase 100.
2. Khi `SpringApplication.run()` trả về, cả hai components đang running.
3. Consumer cần resource cho bước drain cuối nên `RESOURCE used: final-drain` xuất hiện trước `CONSUMER stop`.
4. Provider chỉ stop **sau** consumer, nhờ phase và dependency.
5. Consumer singleton được destroy trước provider singleton vì constructor dependency.
6. Nếu resource đóng quá sớm, `gateway.use(...)` sẽ throw thay vì hoàn thành mốc drain.

**Không nhầm** output này với bằng chứng cho async task completion: demo chỉ minh họa một operation đồng bộ đã hoàn thành trước callback stop.

## 7. JUnit test xác minh thứ tự

Tệp `src/test/java/com/example/shutdown/SafeShutdownTest.java`:

```java
package com.example.shutdown;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SafeShutdownTest {

    @Test
    void dependentStopsBeforeResourceCloses() {
        LifecycleTrace trace;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             LifecycleTrace.class,
                             ResourceGateway.class,
                             DependentConsumer.class)) {
            trace = context.getBean(LifecycleTrace.class);
            assertTrue(context.getBean(ResourceGateway.class).isRunning());
            assertTrue(context.getBean(DependentConsumer.class).isRunning());
        }

        assertEquals(List.of(
                "RESOURCE start",
                "CONSUMER start",
                "RESOURCE used: final-drain",
                "CONSUMER stop",
                "RESOURCE stop",
                "CONSUMER destroy",
                "RESOURCE destroy"
        ), trace.snapshot());
    }
}
```

`AnnotationConfigApplicationContext` cũng có lifecycle processor và annotation configuration processors cần thiết. Test chạy với beans trực tiếp, không phải khởi động web server. Assertion kiểm tra thứ tự toàn bộ vòng đời mà **không có `Thread.sleep`**.

`mvn test` kỳ vọng **một JUnit test** thành công cho class này khi dependencies đúng; `mvn package` cũng chạy các tests theo cấu hình Maven mặc định.

## 8. Khi có tác vụ async thật: stop phải đợi completion

### 8.1. Anti-pattern: callback quá sớm

```java
@Override
public void stop(Runnable callback) {
    executor.execute(this::drainOutstandingJobs);
    callback.run(); // SAI: mới enqueue, chưa chắc công việc xong.
}
```

Đây là **mã minh họa, không độc lập**; cần executor và drain method. Spring lifecycle processor có thể tiến tới stop resource ở phase tiếp theo trong khi task còn đợi worker thread.

Một sequence lỗi:

```text
T0: consumer.stop(callback) bắt đầu
T1: consumer submit "drain" vào thread pool
T2: callback.run() báo đã dừng
T3: provider.stop/close
T4: thread pool chạy drain, gọi provider.flush() -> resource closed
```

### 8.2. Completion callback đúng thời điểm

Ví dụ **mô tả kiến trúc**, không phải file biên dịch độc lập:

```java
@Override
public void stop(Runnable callback) {
    stopAcceptingNewJobs();

    CompletionStage<Void> drain = drainJobsWithDeadline();
    drain.whenComplete((unused, failure) -> {
        if (failure != null) {
            reportShutdownFailure(failure);
            applyTimeoutOrRetryPolicy();
        }
        markStopped();
        callback.run();
    });
}
```

Trong code thật phải xử lý cả lỗi ném ra **trước khi** `drainJobsWithDeadline()` trả stage. Callback phải chạy đúng một lần khi đã xử lý hết trách nhiệm shutdown theo policy; không được gọi trước khi jobs vẫn vô tình sử dụng resource.

Nếu drain thất bại và vẫn còn job chạy, không được lặng lẽ đánh dấu “an toàn”. Phải có timeout, cancellation/acknowledgment, lưu job state và cách xử lý resource close rõ ràng.

### 8.3. Không chỉ đếm in-flight mà quên admission race

Một logic sai thường gặp:

```java
if (accepting.get()) {
    inFlight.incrementAndGet();
    try {
        processJob();
    }
    finally {
        inFlight.decrementAndGet();
    }
}
```

Đây là **đoạn minh họa**. Race có thể xảy ra khi task đã đọc `accepting=true` nhưng chưa increment; lúc đó thread stop đặt accepting=false, thấy inFlight=0 và đóng resource trước khi task dùng nó.

Để khắc phục, **đăng ký task và kiểm tra admission phải atomic với thao tác chuyển sang STOPPING**: dùng lock/condition, state machine, semaphore có cơ chế đóng, hoặc framework container hỗ trợ pause/drain chính thức.

### 8.4. Tránh deadlock do chờ trên cùng executor

Giả sử executor chỉ có một worker:

```text
Worker duy nhất:
    stop() -> submit(flushTask) vào cùng executor
           -> future.get() đợi flushTask
Queue:
    flushTask đang chờ worker rảnh
```

Task không thể chạy vì worker duy nhất đang chờ chính task ấy. Dừng từ coordinator thread phù hợp, hoặc dùng completion callback và executor khác khi cần. Không blocking chờ tương lai trên một thread cần cho tương lai đó.

### 8.5. Timeout và cancellation

`Future.get(timeout, unit)` hoặc `CountDownLatch.await(timeout)` chỉ cung cấp **deadline để chờ**; timeout không tự xóa tác vụ khỏi mọi hệ thống.

- `cancel(false)` không interrupt task đang chạy.
- `cancel(true)` yêu cầu interrupt nhưng task phải hợp tác để dừng.
- External HTTP/DB operations cần client-side timeout.
- Tác vụ có side effect phải có idempotency/retry hoặc compensation.
- Mất tiến trình đột ngột cần durable store nếu không được phép mất dữ liệu.

## 9. Web graceful shutdown và background jobs

Trong Spring Boot 3.3, một ứng dụng web có thể cấu hình:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Graceful shutdown của web server diễn ra khi đóng application context, cố gắng không tiếp nhận requests mới và cho các requests đang xử lý hoàn tất trong grace period. Cách từ chối requests mới tùy server implementation, proxy và connection mode.

**Giới hạn:** nếu HTTP request từng submit một task vào executor và trả response, task ấy đã **tách khỏi vòng đời HTTP request**. Web graceful shutdown không tự biết rằng job phải được chờ. Component sở hữu jobs phải có lifecycle drain riêng, với deadline phù hợp thời gian chờ shutdown của orchestrator.

Trong Kubernetes:

1. Readiness/routing chuyển sang chế độ giảm traffic.
2. Context nhận shutdown có kiểm soát (thường qua SIGTERM).
3. Web requests và background jobs được dừng/drain theo policy.
4. Tài nguyên được đóng sau các consumers.
5. Nếu quá grace period, container có thể bị kill.

`SIGKILL`/JVM crash không bảo đảm `@PreDestroy` hay `SmartLifecycle.stop()` chạy. Muốn job phục hồi sau crash phải lưu trạng thái bền vững, không chỉ dựa vào lifecycle hooks.

## 10. Những tình huống thực tế

### 10.1. Kafka/RabbitMQ consumer

Ưu tiên dùng lifecycle stop chính thức của listener container: pause/unsubscribe, đợi in-flight handlers, acknowledge/commit offsets hoặc rollback theo policy, rồi đóng broker connection. Đừng đóng shared connection factory từ handler đang chạy. Nếu một message có thể được redeliver sau crash, phải xử lý idempotently.

### 10.2. Shared HTTP client

Một `WebClient`/HTTP client hoặc SDK channel được dùng nhiều nơi không nên bị đóng bởi một service borrower. Dừng các producers trước, chờ pending requests, rồi để owner đóng connection pool. Khi resource đóng giữa request, callback có thể thất bại với connection reset hoặc cancellation.

### 10.3. JDBC connection pool

Các transactions đang chạy cần được cho kết thúc hoặc bị rollback có kiểm soát trước khi đóng pool. Client code nên đóng những `Connection` đã mượn theo `try-with-resources`, nhưng không được đóng cả DataSource dùng chung.

### 10.4. Scheduled task

Một `@Scheduled` job đã bắt đầu có thể chạy tiếp ngay cả khi bạn cancel future của các lần chạy tương lai. Nếu job sử dụng repository/client, phải dừng và drain job trước khi dependency bị destroy. Hãy phân biệt **ngừng đăng ký lịch mới** với **lần chạy hiện tại đã hoàn tất**.

### 10.5. File export bất đồng bộ

Nếu method mở stream rồi giao stream sang worker, rời `try-with-resources` sẽ đóng stream quá sớm. Tốt hơn: chuyển immutable payload/đường dẫn cho worker, và để worker tự mở/đóng stream trong toàn bộ phạm vi nó sở hữu.

### 10.6. Shared ThreadPoolTaskExecutor

Một service không tự gọi shutdown trên executor bean dùng chung. Pool owner hoặc Spring context điều phối shutdown; cần chặn submits mới, theo dõi cả queued/running tasks, rồi mới đóng dependencies. `setWaitForTasksToCompleteOnShutdown(true)` có thể giúp đợi tasks, nhưng không đủ nếu client/database bị destroy trong lúc tasks vẫn sử dụng.

## 11. Exception, log và observability

Shutdown failures thường khó tái hiện vì chỉ xuất hiện khi deploy/restart. Nên theo dõi:

- Số jobs đã nhận, đang chạy, queued và còn lại khi STOPPING.
- Thời gian drain, tỷ lệ timeout/cancel.
- Mốc `consumer.stop()` bắt đầu, hoàn thành; `resource.close()` bắt đầu, hoàn thành.
- Errors như `Connection is closed`, `RejectedExecutionException`, `TaskRejectedException`, `IllegalStateException`.
- Context ID/instance ID, message ID/job ID, nhưng tránh log secrets.
- Shutdown phase timeout và thời gian mà Kubernetes cấp cho pod.

Không chỉ log “shutdown requested” rồi coi đó là “shutdown completed”. Hai mốc phải được tách biệt khi có công việc bất đồng bộ.

Nếu cleanup có lỗi, đừng `catch(Exception ignored)`: log actionable reason, xác định có thể retry/cancel, và vẫn bảo đảm lifecycle processor không bị chờ vô hạn vì thiếu callback.

## 12. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Consumer đóng shared DataSource | Các consumers khác không thể kết nối | Owner/container đóng pool, consumer đóng borrowed connection |
| `@PreDestroy` enqueue async rồi return | Resource bị destroy sớm | `SmartLifecycle.stop(Runnable)` và completion protocol |
| Callback stop chạy ngay lúc submit | Provider dừng khi consumer còn hoạt động | Gọi callback sau drain thật sự |
| `@Order` được dùng để ép thứ tự đóng | Không xác lập lifecycle dependency | `getPhase()` và DI/`@DependsOn` |
| Provider phase cao hơn dependent nhưng không mô tả dependency | Provider có nguy cơ stop trước | Mô tả dependency và sửa phase phù hợp |
| `@Lazy` dùng để “giữ bean sống lâu” | Không giải quyết shutdown order | Đồ thị phụ thuộc và lifecycle |
| `inFlight==0` được đọc không đồng bộ admission | Race, task vẫn vào sau khi stop | Atomic admission protocol |
| Stop chờ task trên cùng single-thread pool | Deadlock | Tách coordinator/worker và dùng async completion |
| Resource close ngay khi readiness chuyển refusing | In-flight jobs còn dùng | Readiness trước, drain sau, close cuối |
| Chỉ dựa vào HTTP graceful shutdown | Background tasks vẫn chạy | Worker-specific stop/drain |
| Timeout quá dài | Deployment bị treo hoặc bị kill | Deadline hữu hạn, checkpoint/retry |
| JVM crash nhưng mong `@PreDestroy` | Callback không được chạy | Durable jobs, idempotency |
| Test dựa vào `Thread.sleep` | Không chứng minh thứ tự/completion | Latches, futures, trace assertions |

## 13. Checklist trước khi triển khai

1. Ai tạo tài nguyên, ai sở hữu, ai được quyền đóng?
2. Có bao nhiêu consumers, thread pools hoặc callbacks cùng sử dụng?
3. Constructor injection đã mô tả quan hệ thật chưa?
4. Có dependency gián tiếp cần `@DependsOn`?
5. Resource provider và consumer có SmartLifecycle phase phù hợp?
6. `stop(Runnable)` có đợi drain completion hay chỉ submit?
7. Admission và kiểm tra in-flight có atomic với chuyển sang STOPPING?
8. Có queued tasks chưa bắt đầu?
9. Có transactions, HTTP requests hoặc message acknowledgments chưa xong?
10. Có timeout hữu hạn, cancellation policy và retry state?
11. Executor dùng để dừng có bị chính shutdown stop trước?
12. Có nguy cơ deadlock do chờ trên cùng worker?
13. `@PreDestroy` có chạy sau ngừng hoạt động hay lại mở thêm công việc?
14. Thời gian grace period của platform có đủ và đồng nhất?
15. Có test khi shutdown bị lỗi hoặc resource không phản hồi?
16. Có thể phục hồi jobs sau restart/crash không?
17. Có metrics/log đủ phân biệt shutdown requested và completed?
18. Có kiểm chứng thứ tự resource destroy sau consumer destroy không?

## 14. Bài tập thực hành

1. Nêu sự khác biệt giữa `@PostConstruct`, `SmartLifecycle.start()` và `ApplicationReadyEvent`.
2. Vì sao một bean đã destroy không đồng nghĩa mọi task nó submit đã xong?
3. Trong demo, vì sao resource phase 0 start trước consumer phase 100?
4. Vì sao consumer stop trước gateway và còn có thể gọi `use("final-drain")`?
5. Vì sao dùng constructor injection tốt hơn truy cập resource qua `static`?
6. Khi nào dùng `@DependsOn` thay cho constructor dependency?
7. Vì sao `@Order(1)` không phải cách chắc chắn để đóng resource sau cùng?
8. Nếu `stop(Runnable)` chỉ enqueue việc dừng rồi callback ngay, bug nào có thể xảy ra?
9. Thêm một `CountDownLatch` cho task đang dùng gateway, xác nhận gateway chưa đóng trước khi callback hoàn tất.
10. Viết test cho trường hợp resource `use()` ném lỗi sau stop.
11. Cho resource phase 100 và consumer phase 0 nhưng vẫn có constructor dependency; Spring có thể ưu tiên quan hệ dependency thế nào?
12. Khi context chỉ `stop()` mà chưa `close()`, singleton resource đã bị `@PreDestroy` chưa?
13. Trong `InvoiceReport`, tại sao nên đóng borrowed Connection nhưng không đóng DataSource?
14. Tại sao `try-with-resources` ở caller có thể sai khi truyền stream cho worker async?
15. Thiết kế state machine `RUNNING → STOPPING → STOPPED` với admission không có race.
16. Tại sao `inFlight.incrementAndGet()` sau `accepting.get()` vẫn có race?
17. Với consumer chỉ có một worker, vì sao submit cleanup và đợi trên chính worker đó gây deadlock?
18. Đề xuất policy khi jobs không hoàn tất trước shutdown timeout.
19. Tại sao graceful HTTP shutdown chưa chắc đợi tác vụ mà request đã submit?
20. Thiết kế shutdown cho Kafka consumer: pause, drain, ACK, đóng connection.
21. Giải thích giới hạn của `Future.cancel(true)` và interrupt.
22. Vì sao resource còn live trong `@PreDestroy` không đảm bảo sẽ còn live cho async callback chạy muộn?
23. Cần quan sát metric nào để phát hiện resource bị đóng trước consumer?
24. Nếu pod bị kill -9, callback nào không được bảo đảm?
25. Khi nào cần durable queue/outbox thay vì chỉ dựa vào in-memory executor?

**Tiêu chí đạt:** chạy được ví dụ Spring Boot, hiểu ownership và dependency graph, giải thích đúng thứ tự start–drain–stop–destroy, biết phối hợp SmartLifecycle callback với công việc đang chạy và không ngộ nhận graceful shutdown là bảo đảm không mất dữ liệu.

## 15. Tài liệu chính thức

- Spring Framework 6.1 — Using depends-on: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html
- Spring Framework 6.1 — `@DependsOn`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/DependsOn.html
- Spring Framework 6.1 — `SmartLifecycle`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework 6.1 — PostConstruct & PreDestroy: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html
- Spring Boot 3.3 — Graceful shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — Application Availability and events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
