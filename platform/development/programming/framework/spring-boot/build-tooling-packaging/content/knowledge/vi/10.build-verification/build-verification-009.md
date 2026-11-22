# Quản lý tài nguyên và tiến trình kiểm thử để bản dựng không bị treo

## 1. Mục tiêu bài học

Khi chạy `mvn test`, `mvn verify` hoặc `gradle test`, một bản dựng có thể **không kết thúc** dù không thấy lỗi biên dịch hay assertion. Có khi một test vẫn đợi socket, database hoặc kết quả bất đồng bộ; có khi **toàn bộ test đã PASS nhưng JVM kiểm thử vẫn không thoát** do thread hoặc tiến trình con còn sống; cũng có khi công cụ build đang tải dependency, chờ lock, đợi container hay gom báo cáo.

Trong dự án Spring Boot, tình huống này dễ gặp hơn vì integration tests có thể khởi tạo `ApplicationContext`, embedded server, connection pool, message consumer, scheduled tasks, Testcontainers và các dịch vụ ngoài.

Mục tiêu là **phòng ngừa, nhận diện và xử lý có hệ thống**, không chỉ đặt một timeout thật ngắn rồi bỏ qua lỗi.

Sau bài này, bạn có thể:

- Phân biệt test chậm, test deadlock, thao tác I/O bị treo và **forked JVM không thoát sau khi tests hoàn tất**.
- Thiết kế test có deadline, đóng `ExecutorService`, socket, files, HTTP connections và các tài nguyên `AutoCloseable`.
- Dùng JUnit Jupiter `@Timeout`, `Future.get(timeout)` và cấu hình timeout mặc định mà không tin rằng interrupt luôn giết được một tác vụ bất kỳ.
- Giới hạn tiến trình kiểm thử bằng Maven Surefire/Failsafe và Gradle `Test` task, tránh oversubscription CPU/RAM.
- Viết Spring Boot integration test dùng port ngẫu nhiên, quản lý `ApplicationContext`/Testcontainers đúng vòng đời.
- Thu thập thread dump và build reports **trước khi buộc dừng**, nhận diện thread vẫn sống và các tài nguyên bị giữ.
- Thiết lập thời hạn ở tầng test, worker process và CI job để build luôn có một kết quả quan sát được.

**Ngữ cảnh:** Java 17+, JUnit Jupiter, Maven/Gradle, Spring Boot 3.x. Bài thực hành Maven dùng Spring Boot `3.5.16` và Maven Surefire `3.5.5` như các version cụ thể đã phát hành; dự án thật phải chọn phiên bản tương thích với dòng Boot/JDK của mình.

## 2. Trước hết: “bị treo” có nhiều nguyên nhân khác nhau

Một màn hình console không đổi trong vài phút **chưa đủ** để kết luận tiến trình bị treo. Cần xác định **đang kẹt ở giai đoạn nào**.

| Dấu hiệu | Khả năng cao | Điều cần kiểm tra |
| --- | --- | --- |
| Chưa thấy thông báo test bắt đầu | Tải artifact/plugin, resolve dependencies, compile, lock Gradle, start daemon | Log build với `--info`/`-X`, repository, CPU/network |
| Đang chạy một test, log dừng ở HTTP/DB | I/O thiếu timeout, lock, lệnh SQL lâu, server không sẵn sàng | Test name, client timeout, thread dump, service logs |
| Test đợi `Future.get()` hoặc latch | Task chưa hoàn tất, deadlock, thread pool bị starvation | Worker stack traces, executor queue, deadlines |
| Hiển thị “Tests run: ... Failures: 0” nhưng Maven chưa thoát | Non-daemon thread, shutdown hook, fork JVM chưa kết thúc | Thread dump **forked test JVM**, Surefire reports |
| Gradle `:test` vẫn chạy sau test cuối | Test worker chưa thoát, task/finalizer chưa hoàn thành, daemon đang xử lý | Gradle `--info`, test worker PID, thread dump |
| CI hết giờ mà local chạy được | Chạy song song quá nhiều, thiếu CPU/RAM, service chậm, clock/timing và môi trường khác | Resource metrics, concurrency, env, logs và reports |
| Test có tính ngẫu nhiên: lúc pass lúc treo | Dùng port cố định, dữ liệu/thư mục chung, race condition, chưa chờ readiness | Port/test isolation, retries và scheduling |
| Test process biến mất với thông báo fork crashed | OOM, `System.exit`, JVM crash hoặc bị kill, không nhất thiết treo | `hs_err_pid*.log`, heap usage, fork dumps |

Một hướng chẩn đoán hiệu quả là phân biệt:

1. **Timeout bên trong thao tác**: HTTP connect/read, JDBC acquire, `Future.get`.
2. **Timeout của một test/lifecycle method**: JUnit `@Timeout`.
3. **Timeout của tiến trình chạy nhiều tests**: Surefire fork hoặc Gradle `Test` task.
4. **Timeout của toàn bộ pipeline/job**: CI provider hoặc process supervisor.

Bốn tầng **bổ sung** nhau; không có tầng nào thay thế hoàn toàn các tầng còn lại.

## 3. Vòng đời tài nguyên Java: mở ở đâu, đóng ở đó

### 3.1. Tài nguyên gây treo phổ biến

| Loại tài nguyên | Cách tạo | Cách kết thúc phù hợp |
| --- | --- | --- |
| File/socket/stream JDBC dùng `AutoCloseable` | `Files.newInputStream`, `Socket`, `Connection` | `try-with-resources`, hoặc lifecycle close rõ ràng |
| `ExecutorService` | `Executors.newSingleThreadExecutor()` | `shutdown()`, `awaitTermination()`; khi cần `shutdownNow()` |
| Thread tự tạo | `new Thread(...).start()` | Đặt stop flag/interrupt, `join(timeout)`, không để vòng lặp vô hạn |
| HTTP server tạm | Embedded server, `HttpServer`, `ServerSocket` | `stop`/`close`, chờ dừng |
| Spring ApplicationContext | `@SpringBootTest` hoặc tự `SpringApplication.run` | Theo Spring TestContext cache, hoặc `close` với context tự tạo |
| Container bên ngoài | Testcontainers, Docker Compose, process con | Quản lý đúng test/application lifecycle và stop/cleanup |
| Connection pool, scheduler, consumer | Spring bean quản lý hoặc tạo tay | `@PreDestroy`/bean destroy callback, đóng khi context thật sự kết thúc |
| ThreadLocal, static mutable state | Biến static hoặc thread pool dùng lại | Dọn state sau test, dùng `remove()` khi phù hợp |

Nguyên tắc:

- **Ownership rõ ràng:** ai tạo resource sẽ chịu trách nhiệm đóng, hoặc bàn giao ownership theo một API có hợp đồng rõ ràng.
- **Cleanup nằm trong `finally`/`try-with-resources` hoặc `@AfterEach`/`@AfterAll`**, không chỉ đặt cuối luồng “happy path”.
- **Không đánh đồng “test assertion hoàn tất” với “mọi resource đã dừng”.**
- **Không giết toàn bộ JVM của máy** khi chỉ một test worker đang kẹt; trước hết tìm đúng PID và ghi nhận bằng chứng.

### 3.2. try-with-resources

Với Java 17, `AutoCloseable` giúp giải phóng resource ngay cả khi có exception:

~~~java
package com.example.build;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class FileReadExample {
    private FileReadExample() {}

    public static long countBytes(Path path) throws IOException {
        try (var input = Files.newInputStream(path)) {
            long count = 0;
            byte[] buffer = new byte[4096];
            int n;
            while ((n = input.read(buffer)) != -1) {
                count += n;
            }
            return count;
        }
    }
}
~~~

Đây là class Java 17+ hoàn chỉnh nhưng không có `main`. Hàm trả số byte thực tế trong file khi đọc thành công; nếu file không tồn tại hoặc không được phép đọc, nó ném `IOException` và stream đã mở sẽ được đóng.

**Giới hạn:** `try-with-resources` bảo đảm gọi `close` trong đường thoát control flow, **không tự giải quyết** một `read()` kẹt mãi không trả về. Đối với network I/O, phải có connect/read/request timeouts cụ thể.

### 3.3. ExecutorService trong Java 17

Không viết `try (ExecutorService executor = ...)` trong project bị khóa Java 17: trong Java 17, `ExecutorService` **chưa triển khai `AutoCloseable`**. Cách nhất quán với Java 17 là `shutdown`/`awaitTermination` trong `finally` hoặc test teardown.

Một kiểu cleanup có giới hạn:

~~~java
executor.shutdown();
if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
    executor.shutdownNow();
    if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
        throw new IllegalStateException("Executor chưa dừng");
    }
}
~~~

Đây là **đoạn code nằm trong một method** có `ExecutorService executor` và có thể khai báo `throws InterruptedException`; không phải file Java hoàn chỉnh. `shutdownNow()` chỉ **yêu cầu interrupt** các task đang chạy, không cam kết giết được task bỏ qua interrupt hoặc kẹt trong native I/O. Nếu thread thực sự không dừng, test/build cần báo lỗi và tầng process/CI timeout phải xử lý tiếp.

Không giữ thread pool tĩnh chia sẻ vô hạn giữa tests nếu không có owner/lifecycle rõ ràng.

## 4. Chặn các chờ đợi vô hạn ngay tại nguồn

### 4.1. Future, latch và điều kiện đồng bộ

Những lời gọi như `future.get()`, `latch.await()`, `thread.join()` khi dùng dạng **không deadline** có thể chờ mãi nếu tác vụ không bao giờ hoàn thành.

Ưu tiên:

~~~java
String value = future.get(2, TimeUnit.SECONDS);
boolean completed = latch.await(2, TimeUnit.SECONDS);
worker.join(2000);
~~~

Ba dòng là **đoạn minh họa API** với biến đã được khai báo tương ứng. `Future.get(timeout)` ném `TimeoutException` nếu chưa hoàn tất; `CountDownLatch.await(timeout)` trả `false` khi hết thời gian; `Thread.join(timeout)` chỉ ngừng đợi khi hết thời gian nhưng không chứng minh worker đã kết thúc, nên tiếp tục kiểm tra `worker.isAlive()`.

Với async workflows cần polling readiness, luôn có **deadline tổng**, delay hợp lý giữa các lần check và thông báo lỗi đủ cụ thể. Không dùng `while (!ready) { Thread.sleep(100); }` mà không có giới hạn.

### 4.2. HTTP connect và request timeout

Java 17 có `java.net.http.HttpClient`. Ví dụ helper độc lập:

~~~java
package com.example.build;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class BoundedHttpClient {
    private BoundedHttpClient() {}

    public static String get(String url)
            throws IOException, InterruptedException {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response =
                client.send(request, HttpResponse.BodyHandlers.ofString());
        return response.body();
    }
}
~~~

Đây là class Java 17+ hợp lệ dùng JDK HTTP API, không cần Spring Web dependency. Nó chỉ trả body khi gọi thành công; **không có stdout cố định** và không giả định endpoint luôn sẵn. `connectTimeout` giới hạn giai đoạn kết nối phù hợp, `HttpRequest.timeout` giới hạn request, còn DNS/OS/native operations và môi trường đặc biệt có thể có hành vi khác. Với các client/framework khác (RestClient, WebClient, JDBC), cấu hình timeout theo API thực tế của chính client đó.

### 4.3. Database và connection pool

Nếu test cần database, đừng để pool chờ connection rất lâu hoặc vô hạn. Ví dụ với HikariCP khi Spring Boot thực sự cấu hình Hikari DataSource:

~~~properties
spring.datasource.hikari.connection-timeout=3000
spring.datasource.hikari.validation-timeout=1000
~~~

Hai giá trị biểu thị **milliseconds** theo các setting Hikari: connection acquisition tối đa khoảng 3 giây và validation khoảng 1 giây. Chúng **không phải** timeout cho mọi SQL query đang chạy. Query timeout, JDBC driver socket/read timeout và transaction timeout là những tầng cần cấu hình theo database/driver/framework thực tế.

Nếu test dùng dữ liệu giả/mock, không khởi tạo full database và connection pool chỉ để kiểm tra một hàm tính toán thuần túy.

### 4.4. Server/socket chờ accept

`ServerSocket.accept()` là thao tác blocking. Có thể giới hạn bằng `setSoTimeout` và đóng socket khi kết thúc. Không dùng port cố định `8080` hay `5432` cho nhiều test chạy song song nếu service có thể cấp port động.

Trong Spring Boot HTTP integration test, ưu tiên `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` khi thực sự cần embedded HTTP server. Đây là **phạm vi test**, không phải thiết lập production server port.

## 5. Dự án Maven mẫu kiểm chứng timeout và cleanup

Ví dụ hoàn chỉnh dưới đây **có thể biên dịch/chạy test** với Java 17+, Maven 3.9+ và repository có thể tải Spring Boot/JUnit dependencies. Không cần Docker, database hay HTTP server thật để chạy các test cơ bản.

### 5.1. Cấu trúc file

~~~text
bounded-build/
├── pom.xml
├── mvnw                  # Nếu sinh bằng Spring Initializr / Maven Wrapper
├── mvnw.cmd
└── src/
    ├── main/java/com/example/build/
    │   └── BoundedBuildApplication.java
    └── test/
        ├── java/com/example/build/
        │   ├── BoundedExecutorTest.java
        │   └── ApplicationContextTest.java
        └── resources/
            └── junit-platform.properties
~~~

Có thể tạo Maven Spring Boot project bằng Spring Initializr với Java 17, Maven, `spring-boot-starter` và `spring-boot-starter-test` rồi thay source tương ứng. Nếu tự tạo cây file không có wrapper thì dùng `mvn` thay cho `./mvnw`.

### 5.2. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>bounded-build</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.5</version>
                <configuration>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                    <forkedProcessTimeoutInSeconds>900</forkedProcessTimeoutInSeconds>
                    <forkedProcessExitTimeoutInSeconds>30</forkedProcessExitTimeoutInSeconds>
                    <argLine>-Xmx512m</argLine>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích `maven-surefire-plugin`:

- `forkCount=1`: một forked test JVM đồng thời cho module này; với Maven reactor đa module hoặc Maven `-T`, tổng process có thể cao hơn.
- `reuseForks=true`: reuse fork để chạy nhiều test classes; tiết kiệm startup time nhưng cũng có nguy cơ tích tụ state/thread leak của test trước.
- `forkedProcessTimeoutInSeconds=900`: giới hạn **thời gian sống của một forked test process**, không phải “900 giây cho từng test method”. Nếu cả suite trong một fork bình thường cần hơn 900 giây, cấu hình này quá thấp: phải chọn từ số đo thực tế.
- `forkedProcessExitTimeoutInSeconds=30`: sau khi các tests hoàn tất, cho fork tối đa khoảng 30 giây để hoàn tất thủ tục shutdown. **Khác** timeout trong lúc tests đang chạy.
- `argLine=-Xmx512m`: đặt heap tối đa cho forked test JVM; giá trị này phải cân nhắc với memory container/CI và các process khác, không phải thông số universal.

**Quan trọng:** Surefire timeout không tự bảo đảm thu dọn database/container/thread tốt. Nó cung cấp biên bảo vệ cho fork; khi hết giờ có thể dừng test process và làm build fail. Ngưỡng thời gian nên dựa trên benchmark, không sao chép số minh họa vào mọi project.

Khi dùng Spring Boot starter parent, nhiều plugin versions và test dependencies đã được quản lý. Ví dụ chủ động pin Surefire `3.5.5` để chỉ rõ cấu hình; dự án thực tế phải review tương thích, không ghi đè plugin được team quản lý khi chưa cần.

### 5.3. Ứng dụng Spring Boot chính

Tạo `src/main/java/com/example/build/BoundedBuildApplication.java`:

~~~java
package com.example.build;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundedBuildApplication {

    public static void main(String[] args) {
        SpringApplication.run(BoundedBuildApplication.class, args);
    }
}
~~~

Đây là class Java hoàn chỉnh của module ví dụ. Không có Spring Web starter nên ứng dụng không tự khởi động HTTP server và không chiếm cổng 8080 khi chạy `@SpringBootTest`.

### 5.4. JUnit: Future có deadline và Executor luôn được dọn

Tạo `src/test/java/com/example/build/BoundedExecutorTest.java`:

~~~java
package com.example.build;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BoundedExecutorTest {

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    @AfterEach
    void tearDown() throws InterruptedException {
        executor.shutdownNow();
        assertTrue(executor.awaitTermination(2, TimeUnit.SECONDS),
                "Executor không kết thúc sau 2 giây");
    }

    @Test
    @Timeout(value = 5, unit = TimeUnit.SECONDS)
    void resultArrivesBeforeDeadline() throws Exception {
        Future<Integer> answer = executor.submit(() -> 40 + 2);
        assertEquals(42, answer.get(1, TimeUnit.SECONDS).intValue());
    }
}
~~~

Các lớp được import đầy đủ, Java 17+ biên dịch được với `spring-boot-starter-test` ở test classpath.

**Kết quả kỳ vọng:** một test pass; giá trị `Future` nhận là **42**. Test này **không tự in 42 ra stdout**; Maven/JUnit hiển thị thông tin chạy test tùy provider và version. Các timeout đóng vai trò kiểm soát lỗi khi code thay đổi.

Có ba lớp bảo vệ:

1. `Future.get(1, TimeUnit.SECONDS)` giới hạn **đợi kết quả**.
2. `@Timeout(5s)` giới hạn khoảng thời gian của **test method** theo JUnit.
3. `@AfterEach` gọi `shutdownNow` và chờ tối đa 2 giây; nếu worker không hợp tác, test fail và tầng fork process timeout có thể tiếp tục bảo vệ.

`shutdownNow` không bảo đảm mọi task dừng tức khắc. Trong ứng dụng thật, task nên xử lý `InterruptedException` đúng cách và tránh nuốt cờ interrupt vô ý.

### 5.5. JUnit + Spring: test khởi tạo context

Tạo `src/test/java/com/example/build/ApplicationContextTest.java`:

~~~java
package com.example.build;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationContextTest {

    @Test
    @Timeout(30)
    void applicationContextStarts() {
        // Test pass nếu Spring context khởi tạo thành công.
    }
}
~~~

**Lưu ý quan trọng:** `@Timeout` trên **test method** không phải hard timeout cho mọi thao tác xảy ra **trước khi method được gọi**. Spring TestContext có thể khởi tạo `ApplicationContext` trong giai đoạn extension/lifecycle trước khi vào method, nên startup bị treo có thể không được giới hạn như mong đợi bởi annotation trên method này. Vì vậy cần timeout cho I/O/dependency startup, JUnit lifecycle/extension khi thích hợp và timeout của test process/CI.

Với project này `@SpringBootTest` mặc định dùng mock web environment, không tạo real web server. Nếu muốn test endpoint HTTP thật, dùng `webEnvironment = RANDOM_PORT` ở project có web starter, rồi cấp timeout cho HTTP client.

### 5.6. JUnit timeout mặc định

Tạo `src/test/resources/junit-platform.properties`:

~~~properties
junit.jupiter.execution.timeout.test.method.default = 30 s
junit.jupiter.execution.timeout.beforeeach.method.default = 30 s
junit.jupiter.execution.timeout.aftereach.method.default = 30 s
junit.jupiter.execution.timeout.beforeall.method.default = 60 s
junit.jupiter.execution.timeout.afterall.method.default = 60 s
junit.jupiter.execution.timeout.mode = enabled
~~~

JUnit Jupiter đọc file này trên **test runtime classpath**. Các giá trị chỉ là điểm khởi đầu; nhiều integration tests cần ngưỡng cao hơn theo SLO thực tế. `@Timeout` trực tiếp trên method/class có thể ghi đè default phù hợp.

Có thể đặt `junit.jupiter.execution.timeout.default = 30 s` cho mọi testable/lifecycle methods rồi override cụ thể hơn; trong ví dụ chọn các cài đặt tường minh để phân biệt các giai đoạn.

**Timeout không phải phép kết thúc thread tuyệt đối:** trong chế độ same-thread, JUnit có thể interrupt thread đang chạy, nhưng code bị kẹt ở lời gọi không phản hồi interrupt vẫn có thể tiếp tục. Còn `@BeforeAll`, Spring extension hay shutdown hook cũng có vòng đời riêng. Vì thế cần thêm giới hạn ở tầng JVM fork/job.

Khi debug có breakpoint, timeout ngắn có thể gây fail giả. JUnit có `junit.jupiter.execution.timeout.mode=disabled_on_debug` nếu team muốn tắt timeout khi attach debugger; tránh đổi cấu hình CI để che lỗi treo.

### 5.7. Chạy trên Linux/macOS và Windows

Linux/macOS khi project có Maven Wrapper:

~~~bash
./mvnw clean test
./mvnw -Dtest=BoundedExecutorTest test
./mvnw verify
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd clean test
.\mvnw.cmd "-Dtest=BoundedExecutorTest" test
.\mvnw.cmd verify
~~~

Nếu tạo project hoàn toàn thủ công chưa có Wrapper, dùng `mvn` thay cho `./mvnw` hoặc `.\mvnw.cmd`. `verify` cũng thực hiện các phases trước đó, trong đó có `test`; khi có Failsafe plugin được bind, verify còn thực thi integration tests tương ứng.

**Nơi đọc kết quả Surefire:** `target/surefire-reports/` chứa text/XML reports và các diagnostic files nếu test provider/forged process tạo chúng. Kiểm tra lớp/tên test cuối cùng có tiến triển, không chỉ nhìn dòng `BUILD SUCCESS`/`BUILD FAILURE`.

## 6. Vì sao @Timeout không đủ?

Có bốn trường hợp thường gặp:

1. **I/O không phản hồi interrupt:** test thread được interrupt nhưng network client/driver không ngừng theo kỳ vọng. Cần timeout API và giới hạn tiến trình.
2. **Thao tác nằm ngoài test method:** `@BeforeAll`, Spring context startup, extension callback, process shutdown hoặc Docker readiness xảy ra trước/sau body. Dùng timeout đúng tầng lifecycle, startup/readiness và CI.
3. **Spawn thread không daemon:** test method trả về và assertion pass, nhưng một thread còn sống giữ JVM. Cần cleanup đúng resource ownership; Surefire `forkedProcessExitTimeoutInSeconds` đóng vai trò phòng vệ cuối.
4. **External process/container không chịu quản lý:** Java test kết thúc nhưng process con vẫn chiếm port/file; job tiếp theo có thể treo hoặc fail. Cần đóng theo lifecycle và CI job cleanup.

### 6.1. Deadlock và thread pool starvation

Ví dụ khái niệm deadlock: thread A giữ lock X rồi đợi Y; thread B giữ Y rồi đợi X. Thread dump có thể chỉ ra `BLOCKED` và quan hệ lock. Một kiểu **thread starvation** khác: executor chỉ có 1 worker, task đang chạy lại `get()` chờ task thứ hai cũng được submit vào **chính executor đó**. Task thứ hai không bao giờ được scheduling.

Đừng chỉ tăng số threads để “chữa” deadlock/starvation: cần sửa dependency giữa tasks, bỏ nested blocking `get()` hoặc thiết kế async flow không chiếm worker khi đang chờ task khác.

### 6.2. Không dùng Thread.stop hoặc System.exit để chữa test

`Thread.stop` đã deprecated và không an toàn vì có thể phá vỡ invariants của shared state. `System.exit` trong test có thể giết fork JVM và làm Surefire/Gradle báo process terminated unexpectedly, mất reports hoặc phá CI. Hãy dùng cancellation/interrupt có kiểm soát và đóng tài nguyên.

### 6.3. Dùng thread daemon không phải lời giải tổng quát

Chuyển worker thread thành daemon có thể khiến JVM thoát, nhưng một daemon thread còn chạy có thể bị dừng đột ngột mà chưa flush logs, commit transaction hoặc dọn file. Chọn **ownership + graceful shutdown + timeout** thay cho việc biến tất cả threads thành daemon.

## 7. Spring Boot Test và vòng đời ApplicationContext

Spring Boot tests thường sử dụng **Spring TestContext Framework**, có cơ chế cache ApplicationContext giữa các test classes có cấu hình tương đương. Điều này giúp giảm startup cost nhưng cũng tạo bài toán vòng đời.

### 7.1. @SpringBootTest có nhất thiết mở server không?

Không. `@SpringBootTest` với web environment mặc định là `MOCK`: nếu có web stack, nó tạo mock web environment nhưng **không khởi động embedded HTTP server**. Khi thực sự muốn kiểm tra HTTP request qua TCP, sử dụng:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpIntegrationTest {
    // Test thực hiện HTTP request có timeout tới port được cấp động.
}
~~~

Đây là đoạn minh họa class, **không phải một test đầy đủ**. Cần web starter và test client được cấu hình trong project thực tế. `RANDOM_PORT` tránh chiếm cổng cố định giữa các build/test workers, nhưng vẫn phải cấu hình connect/request timeout cho HTTP client.

`DEFINED_PORT` có thể gây conflict trên CI nếu nhiều test JVM cùng dùng 8080 hoặc `server.port` cố định. Dùng port động khi không có yêu cầu đặc biệt.

### 7.2. Bean lifecycle, executor và client

Nếu một executor, scheduler hoặc connection pool là **Spring bean**, Spring có thể gọi destroy callback khi `ApplicationContext` đóng — nếu bean và destroy method được cấu hình phù hợp. Nhưng **context cache có thể giữ context sống qua nhiều test classes**, vì vậy đừng giả định `@AfterEach` đồng nghĩa toàn bộ Spring beans đã được dừng.

Ngược lại, executor/HTTP client/socket được tạo **trực tiếp trong test** nên được đóng bởi test `@AfterEach`/`@AfterAll` hoặc try-with-resources, không trông chờ Spring tự biết để cleanup.

Không dùng `@DirtiesContext` đại trà chỉ để “reset cho chắc”: annotation này làm Spring context bị loại khỏi cache và phải khởi tạo lại, có thể khiến toàn bộ suite rất chậm. Chỉ dùng khi test thật sự làm thay đổi context state không thể reset bằng cách khác.

### 7.3. Testcontainers và Docker

Khi integration test dùng Testcontainers, phải phân biệt:

- Container sống theo **JUnit extension** (ví dụ `@Testcontainers` + `@Container`), thường dừng theo vòng đời test class/method tương ứng.
- Container được **Spring quản lý** (container bean hay cơ chế tích hợp tương ứng), có thể sống theo vòng đời cached ApplicationContext.
- Container/process được bạn tạo thủ công: bạn phải có hook stop/close, nhất là khi test fail hoặc timeout.

Một bẫy: Spring context cache còn tham chiếu một datasource đã bind vào container, nhưng JUnit-managed container đã dừng khi class kết thúc. Test sau tái sử dụng context đó có thể không kết nối được hoặc treo ở retry/readiness. Nếu context cần sống cùng container, ưu tiên quản lý lifecycle nhất quán theo hướng dẫn Spring Boot; không giữ static container bên ngoài framework mà không hiểu cache.

**Không dùng thời gian chờ container không giới hạn.** Chờ container health/readiness có timeout thực tế; khi lỗi hãy lưu Docker/service logs và nhận diện container ID đúng của job, tránh stop toàn bộ containers trên máy shared runner.

### 7.4. Transactions và teardown

Trong Spring tests, `@Transactional` trên test method thường rollback transaction của **thread test** sau khi chạy. Khi HTTP integration test dùng `RANDOM_PORT` hoặc `DEFINED_PORT`, server-side request xử lý trên thread khác và transaction của nó **không được tự rollback** bởi transaction của test client. Vì vậy cần cleanup dữ liệu test rõ ràng hoặc database/schema tách biệt.

Nếu cleanup DB sử dụng cùng connection pool đang kẹt, teardown cũng có thể treo. Cần dành connection timeout và dữ liệu/transaction isolation hợp lý.

## 8. Maven Surefire: forks, timeouts và báo cáo

### 8.1. Forked test JVM là gì?

Maven Surefire có thể chạy tests trong một hoặc nhiều **JVM riêng** thay vì chạy trực tiếp trong Maven JVM. Điều này giúp cô lập classpath, memory và lifecycle. Tham số quan trọng:

| Tham số Surefire | Ý nghĩa | Rủi ro khi đặt sai |
| --- | --- | --- |
| `forkCount` | Số JVM tests được fork song song **trong module** | Tăng quá cao gây tranh chấp CPU/RAM/port |
| `reuseForks` | Dùng lại fork cho nhiều test classes hay tạo fork mới | Reuse có thể tích tụ leak; không reuse làm startup chậm |
| `forkedProcessTimeoutInSeconds` | Giới hạn thời gian chạy **một forked JVM** | Quá thấp làm fail suite hợp lệ; 0 là không giới hạn |
| `forkedProcessExitTimeoutInSeconds` | Timeout khi fork kết thúc sau khi hoàn thành tests | Che/leak nếu chỉ dùng kill thay cleanup |
| `argLine` | JVM args cho fork, ví dụ `-Xmx`, diagnostics | Heap quá lớn khiến CI OOM |
| `systemPropertyVariables` | JVM system properties truyền cho tests | Dễ lộ cấu hình nhạy cảm nếu hard-code |

**Không nhầm `forkedProcessTimeoutInSeconds` với timeout từng test.** Khi `reuseForks=true`, một fork có thể chạy nhiều test classes; một giới hạn vài chục giây có thể vô tình giết một suite hợp lệ. Chọn test-level `@Timeout` cho từng thao tác, fork-level timeout theo **thời gian hợp lệ của cả fork**, và CI timeout cho toàn job.

**Không đặt `forkCount=0`** nếu bạn cần khả năng kill test JVM riêng khi treo: `forkCount=0` chạy tests trong Maven process, khiến quá trình cô lập và timeout fork không còn ý nghĩa như khi fork.

### 8.2. Dùng ít fork trước khi tăng tốc

Nếu CI CPU giới hạn 2 vCPU, build multi-module với Maven `-T` nhiều module + `forkCount=4` + integration DB containers có thể làm hàng chục JVM/containers tranh nhau tài nguyên. Một suite bình thường 3 phút có thể biến thành 20 phút hoặc báo hết memory/connection/port.

Khi đang chẩn đoán treo:

1. Tạm chạy **tuần tự** để xác định lỗi tương tác giữa tests.
2. Dùng `forkCount=1` và `reuseForks=true` để có baseline.
3. Nếu nghi leak xuyên test classes, thử `reuseForks=false` trong môi trường chẩn đoán để cô lập class; chấp nhận tốc độ chậm hơn, **không coi đó là cách chữa leak**.
4. Chỉ tăng forks sau khi đo CPU/RAM, database max connections, số container và giới hạn runner.

### 8.3. Chạy riêng test nghi vấn

Linux/macOS:

~~~bash
./mvnw -Dtest=BoundedExecutorTest test
./mvnw -Dtest=BoundedExecutorTest#resultArrivesBeforeDeadline test
./mvnw -e test
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd "-Dtest=BoundedExecutorTest" test
.\mvnw.cmd "-Dtest=BoundedExecutorTest#resultArrivesBeforeDeadline" test
.\mvnw.cmd -e test
~~~

`-Dtest` là selector của Surefire. `-e` yêu cầu Maven hiện exception details; `-X` là debug log rất dài, chỉ dùng khi có mục tiêu cụ thể và không đẩy credentials lên log công khai.

Đọc `target/surefire-reports/`, nhất là test cuối cùng được đánh dấu đang chạy. Một process có thể hang sau test cuối nhưng trước khi Maven thoát; cần **thread dump của forked JVM**, không chỉ xem Maven console.

### 8.4. Maven Failsafe cho integration tests

Với integration tests thực sự cần các dịch vụ ngoài, có thể dùng **maven-failsafe-plugin** để chạy ở phases `integration-test` và `verify`. Đoạn cấu hình minh họa bên trong `<build><plugins>`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.5</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <forkCount>1</forkCount>
        <forkedProcessTimeoutInSeconds>1800</forkedProcessTimeoutInSeconds>
        <forkedProcessExitTimeoutInSeconds>30</forkedProcessExitTimeoutInSeconds>
    </configuration>
</plugin>
~~~

Đây **không phải POM hoàn chỉnh**. Giới hạn 1800 giây chỉ là ví dụ cho worker integration test, phải đo thực tế. Failsafe thường nhận diện tên test như `*IT.java` hoặc `*ITCase.java`, khác quy ước mặc định của Surefire. Hãy chạy `mvn verify` để hoàn tất toàn bộ vòng đời integration test và kiểm tra kết quả; không dừng ở `mvn integration-test` khi dự án cần phase `verify`/post-integration-test cho cleanup và báo lỗi đúng cách.

Reports thường nằm tại `target/failsafe-reports/`. Nếu một pre-integration-test step khởi tạo service ngoài, phải có bước dừng phù hợp và fallback CI cleanup để tránh orphan process.

## 9. Gradle Test: giới hạn worker, memory và task timeout

Gradle chạy `Test` task trong các **forked JVMs**. Các thuộc tính quan trọng:

- `maxParallelForks`: số fork chạy test classes song song trong một task (mặc định thường là 1).
- `forkEvery`: số test classes tối đa trước khi tạo process mới; `0` là reuse, `1` là mỗi class một JVM (rất tốn thời gian).
- `maxHeapSize`/`jvmArgs`: giới hạn memory và JVM options cho test worker.
- `timeout`: **task-level timeout**, giới hạn khoảng thời gian của cả Gradle Test task, không phải từng test.
- `--max-workers`: giới hạn tổng Gradle workers trên build, có thể ảnh hưởng số test forks thực tế.
- JUnit `@Timeout` vẫn cần khi muốn giới hạn riêng test method.

### 9.1. Gradle Groovy DSL

Với project Java/Spring Boot áp dụng Java plugin và JUnit Jupiter:

~~~groovy
import java.time.Duration

tasks.withType(Test).configureEach {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0
    maxHeapSize = '512m'
    timeout = Duration.ofMinutes(15)

    testLogging {
        events 'failed', 'skipped'
    }
}
~~~

Đây là **đoạn build.gradle**, không phải file build hoàn chỉnh; nó giả định đã có dependency JUnit engine qua `spring-boot-starter-test` hoặc các dependencies JUnit tương thích. `timeout` giới hạn thời gian task, `maxParallelForks` giới hạn fork song song trong task.

### 9.2. Gradle Kotlin DSL

Trong `build.gradle.kts`:

~~~kotlin
import java.time.Duration
import org.gradle.api.tasks.testing.Test

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0
    maxHeapSize = "512m"
    timeout.set(Duration.ofMinutes(15))
    testLogging {
        events("failed", "skipped")
    }
}
~~~

Đây là DSL configuration, không phải chương trình Kotlin chạy độc lập. Nếu Gradle/plugin version của bạn có API khác, đối chiếu tài liệu `Test`/`Task.timeout` theo version build.

### 9.3. Chạy và lọc test

Linux/macOS:

~~~bash
./gradlew test --info
./gradlew test --tests 'com.example.build.BoundedExecutorTest'
./gradlew test --stacktrace
./gradlew --max-workers=2 test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --info
.\gradlew.bat test "--tests=com.example.build.BoundedExecutorTest"
.\gradlew.bat test --stacktrace
.\gradlew.bat --max-workers=2 test
~~~

`--info` giúp thấy task progress và test process, `--stacktrace` hiển thị stack của Gradle failure; **đây không phải thread dump của một JVM đang bị kẹt**. Nếu task không ra lỗi, cần công cụ Java process diagnosis để lấy stack của test worker.

Gradle HTML report thường ở `build/reports/tests/test/index.html`; XML results tại `build/test-results/test/`. Trong dự án multi-module, đường dẫn nằm dưới module tương ứng.

### 9.4. Cảnh báo về parallel

Một Gradle build có nhiều `Test` tasks ở các modules vẫn có thể sử dụng nhiều resources nếu `--parallel`/workers cao. `maxParallelForks=1` cho **mỗi task** không bảo đảm chỉ một JVM test trong **toàn bộ build**. Đối với CI ít tài nguyên, đo concurrency tổng cộng: Gradle daemon/build JVM + các test JVMs + database/container workers.

JUnit Jupiter cũng có cơ chế method/class parallelism riêng. **Gradle forks** và **JUnit threads bên trong một fork** là hai tầng song song khác nhau; nếu bật cả hai, tổng concurrency có thể cao hơn tưởng tượng.

## 10. Thiết kế test độc lập để có thể chạy song song

### 10.1. Port động thay port cố định

Đối với HTTP integration tests, dùng `RANDOM_PORT` khi có thể. Đối với `ServerSocket` tự tạo, dùng `new ServerSocket(0)` để hệ điều hành chọn port trống rồi lấy `getLocalPort()`. Tuy nhiên, đừng đóng socket rồi dùng lại port đó trong process khác mà không có cơ chế đồng bộ: có thể phát sinh race condition giữa lúc release và bind.

### 10.2. File system riêng cho từng test

JUnit Jupiter hỗ trợ `@TempDir` để cấp thư mục tạm riêng. Ví dụ:

~~~java
package com.example.build;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;

class IsolatedFileTest {

    @TempDir
    Path workDir;

    @Test
    void writesIntoItsOwnDirectory() throws Exception {
        Path file = workDir.resolve("result.txt");
        Files.writeString(file, "ok", StandardCharsets.UTF_8);
        assertEquals("ok", Files.readString(file, StandardCharsets.UTF_8));
    }
}
~~~

Đây là class Java 17+ hoàn chỉnh, dùng JUnit Jupiter từ Spring Boot test dependency. Giá trị file là chuỗi `ok`; test không in stdout. JUnit quản lý `@TempDir` theo lifecycle phù hợp, tránh việc nhiều tests cùng sửa `./result.txt`.

Đối với database, dùng schema riêng, database test riêng hoặc cơ chế cleanup/idempotency có ranh giới rõ. Đối với broker/topic, dùng naming unique theo test run hoặc worker. Một test **không nên phụ thuộc vào test khác chạy trước**, trừ khi test suite được thiết kế có stateful lifecycle một cách chủ ý.

### 10.3. Tránh Thread.sleep cố định để chờ startup

Không dùng `Thread.sleep(10000)` với kỳ vọng database/consumer “chắc chắn đã sẵn sàng”. Trên máy nhanh, nó lãng phí 10 giây; trên CI chậm, 10 giây có thể vẫn chưa đủ. Dùng health check/polling có deadline và fail message rõ ràng. Ví dụ ý tưởng:

~~~text
deadline = now + 30s
while service not ready:
    if now >= deadline:
        fail with last error and service logs
    sleep for small backoff
~~~

Đây là **pseudocode**, không phải Java source. Một utility như Awaitility có thể giúp polling condition có timeout, nhưng phải thêm dependency phù hợp; không ngụ ý package này có sẵn ở mọi project.

## 11. CI: timeout, cleanup và lưu bằng chứng

Ngay cả test suite có `@Timeout` tốt vẫn cần **job-level timeout**. CI cần ngăn trường hợp JVM stuck ngoài khả năng interrupt hoặc build system treo khi giải quyết tài nguyên.

### 11.1. Phân tầng deadline đề xuất

Đây là **ví dụ lập kế hoạch**, không phải thông số bắt buộc:

| Tầng | Ví dụ budget | Mục đích |
| --- | --- | --- |
| HTTP connect | 2 giây | Fail sớm khi service không reachable |
| HTTP request | 5 giây | Không chờ endpoint quá lâu |
| `Future.get` | 1–3 giây | Không chờ mãi kết quả async |
| JUnit test method | 30 giây | Bắt test chạy quá thời gian kỳ vọng |
| Maven fork / Gradle Test task | 15–30 phút tùy suite | Ngăn cả worker/task bị kẹt |
| CI job | Cao hơn tổng các phases hợp lệ | Bảo vệ toàn bộ pipeline |

Nếu 100 test methods mỗi cái tối đa 30 giây, không thể đặt thời hạn **cả fork** là 30 giây rồi kỳ vọng suite luôn pass. Ngoài ra, phases download dependencies, code generation, compiler, integration setup và packaging cũng tiêu thụ thời gian CI.

### 11.2. Ví dụ GNU timeout trên runner Linux

Trong môi trường Linux có `coreutils timeout`, có thể đặt lớp bảo vệ ngoài cho lệnh Maven:

~~~bash
timeout --signal=TERM --kill-after=30s 25m ./mvnw verify
~~~

Nếu lệnh vượt 25 phút, `timeout` gửi tín hiệu TERM trước; nếu còn chạy sau 30 giây, nó có thể gửi KILL theo cơ chế của coreutils. Lệnh **không có mặc định trên mọi macOS hoặc Windows**, và việc signal có xử lý toàn bộ descendants/container hay không phụ thuộc process groups/CI runtime. Không dùng `timeout` như cơ chế cleanup tài nguyên duy nhất.

Khi CI provider có **job timeout** và post-step/finally/cleanup hooks, ưu tiên cấu hình đó để tự động lưu logs, reports và dừng service/container thuộc job.

### 11.3. Luôn giữ lại reports khi fail hoặc timeout

Những artifacts nên thu thập:

- Maven: `target/surefire-reports/**`, `target/failsafe-reports/**`.
- Gradle: `build/test-results/**`, `build/reports/tests/**`.
- Thread dumps của đúng test worker (nếu có).
- Logs từ ứng dụng, database, message broker/container test.
- CI memory/CPU/OOM diagnostics, thời điểm test cuối chạy và process exit code.

**Lưu ý bảo mật:** thread dump, environment dump và test logs có thể chứa URL có credential, user data hoặc token trong stack/local context. Chỉ lưu ở nơi có kiểm soát quyền truy cập, lọc secrets trước khi chia sẻ.

### 11.4. Cleanup khi job bị hủy

Nếu test có start Docker container/process con, dùng tool hoặc framework có ownership để stop chúng ở cleanup hook. Job timeout có thể không chạy mọi hook nếu runner bị kill đột ngột; cần biện pháp cleanup ở cấp runner/container orchestration khi cần.

Đừng dùng lệnh “kill tất cả java” hay “docker rm -f mọi container” trên runner dùng chung. Điều này có thể ảnh hưởng jobs hoặc dịch vụ của người khác.

## 12. Điều tra một bản dựng đang treo

### 12.1. Quy trình không phá bằng chứng

1. Ghi lại **lệnh build**, JDK, Maven/Gradle version, thời gian bắt đầu và tên test/phase cuối có log.
2. Tìm **đúng PID** của Maven/Gradle process và **forked JVM chạy test**; không suy đoán PID từ tên process duy nhất.
3. Khi process còn sống, **thu thread dump**, nếu có thể vài mẫu cách nhau 5–10 giây để thấy stack có tiến triển.
4. Kiểm tra trạng thái threads: `RUNNABLE`, `WAITING`, `TIMED_WAITING`, `BLOCKED` và các stack frames thuộc HTTP, JDBC, lock, executor, native I/O.
5. Đối chiếu các test reports và logs service/container; tìm chủ resource chưa được close hoặc thao tác chờ thiếu deadline.
6. Sau khi lưu bằng chứng, thử dừng graceful đúng process; nếu không phản hồi, dùng timeout/supervisor kill theo chính sách CI.
7. Sửa nguyên nhân rồi kiểm tra cả case đơn lẻ, full suite, chạy song song và CI.

### 12.2. Công cụ JDK: jcmd, jstack

Trên Linux/macOS có JDK tools phù hợp:

~~~bash
jcmd -l
jcmd 12345 Thread.print -l
~~~

Trên Windows PowerShell:

~~~powershell
jcmd -l
jcmd 12345 Thread.print -l
~~~

**PID `12345` là ví dụ**, phải thay bằng PID thật của test JVM. `jcmd Thread.print -l` yêu cầu quyền attach và JDK tool tương thích; không phải mọi container/CI image đều có đầy đủ JDK tools hoặc cho phép attach.

Một lựa chọn khi được hỗ trợ:

~~~bash
jstack -l 12345
~~~

Trên Unix, khi không thể attach nhưng có quyền gửi tín hiệu, `kill -3 12345` thường yêu cầu HotSpot JVM dump stacks ra stdout/stderr của **target process**. Chỉ dùng cho đúng PID và biết nơi logs target được lưu; `kill -3` khác `kill -9`. Trong Windows, `jcmd` là lựa chọn dễ kiểm soát hơn.

### 12.3. Đọc thread dump

Một số mô hình thường gặp:

- **`java.net.SocketInputStream` / `SocketDispatcher` / JDBC driver:** thread đang đợi network; xác minh socket/read/query timeout và service availability.
- **`CompletableFuture.get` / `FutureTask.get`:** thread đang chờ kết quả async; tìm task nào sẽ complete future và executor nào chạy task đó.
- **`LockSupport.park` / `AbstractQueuedSynchronizer`:** có thể chờ lock, condition hoặc queue; tìm owner/expected wakeup trước khi kết luận deadlock.
- **`BLOCKED` cùng lock ownership:** có thể contention hoặc deadlock; kiểm tra JVM báo deadlock nếu có và các thread liên quan.
- **Một thread non-daemon sau khi tests pass:** truy về thread factory/executor/scheduler chưa đóng; sửa test/bean lifecycle.
- **GC/CPU cao:** có thể memory pressure hoặc vòng lặp bận (busy loop), không phải lock wait; kiểm tra CPU/heap metrics.

Thread dump là **ảnh chụp tại một thời điểm**. Một thread ở `WAITING` chưa chắc lỗi; nhiều thread pool workers bình thường cũng waiting. Cần đối chiếu deadlines, state thay đổi và log.

### 12.4. Gradle daemon không phải Gradle test worker

`./gradlew --stop` yêu cầu Gradle dừng các daemons phù hợp với phiên bản Gradle được gọi; đây không phải công cụ chữa mọi test hang, cũng không bảo đảm dọn được mọi external process mà tests đã tạo. Khi debug, phân biệt:

- JVM chạy Gradle daemon/build.
- JVM test worker do `Test` task fork.
- App server/container/DB child processes do test tạo.

Muốn biết lý do test không thoát, cần dump **đúng worker/process** và nhìn resource ownership. Chỉ dừng daemon nếu có lý do liên quan đến daemon state hoặc sau khi đã thu thập bằng chứng.

## 13. Anti-patterns và cách sửa

### 13.1. Dùng skip tests để làm CI xanh

Maven:

~~~bash
./mvnw package -DskipTests
~~~

hoặc Gradle:

~~~bash
./gradlew build -x test
~~~

có thể hữu ích **chỉ để khoanh vùng chẩn đoán** xem hang có nằm trong tests hay không, nhưng **không phải cách sửa**. Build qua được khi bỏ test không chứng minh artifact an toàn; không đưa cấu hình skip vào release pipeline chỉ để giấu vấn đề.

Trong Maven, `-DskipTests` thường bỏ **thực thi test** nhưng vẫn biên dịch test, còn `-Dmaven.test.skip=true` có thể bỏ cả test compilation; hậu quả khác nhau tùy plugin. Đừng vô tình thay đổi contract kiểm thử của pipeline.

### 13.2. Tăng timeout vô hạn

Nếu một test treo do deadlock, nâng từ 1 phút lên 1 giờ chỉ kéo dài thời gian thất bại. Trước khi tăng budget phải xem stack traces/metrics và xác định nguồn tài nguyên nào thật sự cần thời gian lâu. Timeout nên bảo vệ một **SLO** có cơ sở, có ghi nhận số đo.

### 13.3. Retry vô hạn khi service không sẵn sàng

Code retry thiếu deadline có thể khiến test fail thành “treo”. Nếu service khởi động bị lỗi, retries vô hạn không chữa được. Đặt retry count hoặc deadline, backoff và báo **last cause**. Không nuốt exception rồi loop tiếp mà không ghi log.

### 13.4. Tạo shared executor/static context cho mọi test

Một `static ExecutorService` mà test A tạo có thể giữ thread sống sang test B; thứ tự test run và `reuseForks` làm lỗi khó tái hiện. Dùng executor trong scope test hoặc bean có lifecycle rõ, reset shared state; nếu buộc chia sẻ, có owner + close ở `@AfterAll` hoặc suite-level teardown đáng tin.

### 13.5. Bắt InterruptedException rồi bỏ qua

Cách xấu:

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException ignored) {
    // Nuốt interrupt, tiếp tục làm việc như cũ.
}
~~~

Đây là đoạn trong method, không phải class hoàn chỉnh. Khi interrupt được dùng để hủy công việc, thường cần dừng task/cleanup và có thể khôi phục interrupt flag:

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Đoạn thứ hai giả định method trả `void`; trong method trả giá trị phải xử lý control flow phù hợp. Khi đang hủy test, việc nuốt interrupt có thể khiến `@Timeout` và shutdown không hiệu lực như mong đợi.

### 13.6. Không phân biệt timeout “hết thời gian” với “đã dọn xong”

Một `@Timeout` thất bại không bảo đảm mọi thread/process và external resources đã bị dừng. Sau test timeout cần teardown/cancellation; sau worker timeout cần process-level cleanup; sau CI cancellation cần runner-level cleanup. Càng có nhiều layers, càng phải xác định ai sở hữu việc đóng từng resource.

## 14. Tình huống thực hành và đáp án

**Tình huống 1 — Tests pass nhưng Maven không thoát.** Bạn thấy `Tests run: 120, Failures: 0` và terminal đứng im. Một test tạo `Executors.newSingleThreadExecutor()` nhưng không shutdown.

- **Nguyên nhân có thể:** worker thread không daemon của executor vẫn sống hoặc fork đang chờ shutdown.
- **Xử lý:** lấy thread dump của fork, kiểm tra tên/stacks; thêm shutdown/awaitTermination trong `@AfterEach`/`finally`. `forkedProcessExitTimeoutInSeconds` là safety net, không thay cleanup.

**Tình huống 2 — Gradle test hang khi bật parallel.** Các tests dùng chung database/schema và ghi cùng `./tmp/results.json`.

- **Nguyên nhân có thể:** race/file lock/transaction contention giữa test workers.
- **Xử lý:** tạm `maxParallelForks=1` để khoanh vùng; chuyển sang `@TempDir`, unique schemas/ports và resource isolation. Không mặc định “tăng CPU” giải quyết concurrency bug.

**Tình huống 3 — @Timeout(10) không chặn kẹt khi Spring context startup.**

- **Nguyên nhân có thể:** lỗi xảy ra trong startup/extension callback trước test method hoặc I/O ignore interrupt.
- **Xử lý:** đặt deadline cho DB/HTTP/Testcontainers readiness, kiểm tra lifecycle timeout và fork/task/CI safeguards. Đừng dựa vào `@Timeout` của method như hard process kill.

**Tình huống 4 — Surefire fork timeout 60 giây nhưng một suite 200 test bình thường cần 90 giây.**

- **Nguyên nhân:** timeout áp lên fork process (khi reuseForks), không phải chỉ test mắc kẹt.
- **Xử lý:** đo suite duration; giữ test method timeout nhỏ phù hợp, nâng worker-level budget dựa trên worst-case hợp lệ và CI budget.

**Tình huống 5 — HTTP integration tests dùng `DEFINED_PORT` và CI chạy song song.**

- **Nguyên nhân có thể:** port conflict làm server fail start hoặc test chờ endpoint không đúng.
- **Xử lý:** dùng `RANDOM_PORT` và client lấy port runtime, đảm bảo connect/read timeouts; chỉ dùng fixed port khi có coordination.

**Tình huống 6 — Testcontainers dừng container nhưng Spring cached context vẫn giữ datasource.**

- **Nguyên nhân:** lifecycle của container và cache của Spring TestContext không đồng bộ.
- **Xử lý:** quản lý container theo lifecycle context hoặc cấu hình test isolation phù hợp; không bắt toàn bộ suite cùng dùng một container bị stop sớm.

**Tình huống 7 — Maven build bị treo trong CI, bạn thấy một Java PID và định dùng kill -9 ngay.**

- **Cách tốt hơn:** xác minh PID thuộc JVM nào, lưu logs và `jcmd Thread.print`/thread dump trước, thử graceful termination, chỉ dùng forced kill nếu cần theo time budget. Không kill Java processes của job khác.

## 15. Checklist trước khi merge build/test changes

- [ ] Mọi I/O quan trọng (HTTP, DB, socket, external service) có timeout cụ thể và fail message rõ.
- [ ] Mọi Future/latch/polling có deadline; không có loop chờ vô hạn.
- [ ] ExecutorService, socket, stream, temp files, container và process có owner cùng lifecycle cleanup.
- [ ] Các test methods/lifecycle phù hợp có JUnit timeouts; biết `@Timeout` không phải hard-kill process.
- [ ] Surefire/Failsafe fork timeouts và exit timeouts được chọn theo **thời gian của cả fork**, không nhầm per-test.
- [ ] Gradle test workers, JVM heap và `timeout` được đặt theo CPU/RAM/CI thực tế.
- [ ] Tests song song có port/temp dir/schema/data isolation; không dùng state shared tùy tiện.
- [ ] Spring `@SpringBootTest`/ApplicationContext/Testcontainers có lifecycle tương thích, không lạm dụng `@DirtiesContext`.
- [ ] CI có job timeout, cleanup hooks và artifacts reports/thread dumps khi fail.
- [ ] Đã thử chạy từng test nghi vấn, toàn suite, và chạy liên tiếp nhiều lần để phát hiện leak.
- [ ] Không che lỗi bằng `skipTests` hoặc retry vô hạn.
- [ ] Lệnh dừng process luôn nhắm **đúng PID/resource**; không tác động job hoặc dịch vụ khác.

## 16. Tài liệu chính thức

- JUnit Jupiter `@Timeout` và timeout configuration: https://docs.junit.org/5.12.1/user-guide/index.html
- Maven Surefire Plugin — test goal configuration: https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html
- Maven Surefire — forked JVM shutdown: https://maven.apache.org/surefire/maven-surefire-plugin/examples/shutdown.html
- Maven Failsafe Plugin — integration-test và verify: https://maven.apache.org/surefire/maven-failsafe-plugin/
- Gradle — Testing in Java & JVM Projects: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Controlling Task Execution / Task timeouts: https://docs.gradle.org/current/userguide/controlling_task_execution.html
- Gradle Test API (`maxParallelForks`, `forkEvery`, `maxHeapSize`): https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/Test.html
- Spring Boot — Testing Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Boot — Testcontainers integration: https://docs.spring.io/spring-boot/reference/testing/testcontainers.html

**Kết luận:** Một bản dựng đáng tin cậy phải **hoàn tất hoặc thất bại có thông tin chẩn đoán**, không chờ vô hạn. Để đạt được điều đó, cần kết hợp **đóng tài nguyên đúng vòng đời**, **deadline sát từng thao tác**, **JUnit test/lifecycle timeouts**, **Maven/Gradle worker protection** và **CI-level timeout/cleanup**. Khi gặp treo, thu thread dump và reports của đúng process trước khi cưỡng bức dừng; sửa nguyên nhân thay vì chỉ tăng thời gian hoặc bỏ qua kiểm thử.