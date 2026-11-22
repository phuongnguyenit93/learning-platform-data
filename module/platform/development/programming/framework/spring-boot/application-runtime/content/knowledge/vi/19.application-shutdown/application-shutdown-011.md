# Khác biệt giữa nút Stop của IDE với tín hiệu dừng có kiểm soát — Spring Boot 3.3

## 1. Mục tiêu bài học

Trong lúc phát triển Spring Boot, lập trình viên thường bấm nút **Stop** trong IntelliJ IDEA, Eclipse, VS Code hoặc cửa sổ chạy/debug và thấy tiến trình Java biến mất. Nhưng **tiến trình biến mất** không có nghĩa ứng dụng đã thực hiện đầy đủ quy trình shutdown: dừng nhận HTTP requests, chờ request đang chạy, ngừng consumer, flush dữ liệu, đóng kết nối và chạy `@PreDestroy`.

Một tiến trình Java cũng có thể được dừng bằng `Ctrl+C`, `SIGTERM`, yêu cầu đóng `ApplicationContext`, lệnh của Docker/Kubernetes hoặc buộc kết thúc bằng `SIGKILL`. Những cách này khác nhau về khả năng kích hoạt JVM shutdown hooks và Spring lifecycle callbacks.

**Thông điệp chính:** *Nút Stop là thao tác của công cụ phát triển, không phải một hợp đồng dừng ứng dụng thống nhất.* Muốn kiểm thử shutdown có kiểm soát, phải xác định **IDE/OS/launcher gửi hành động gì đến JVM**, dùng tín hiệu phù hợp rồi quan sát **hành vi shutdown thực tế**. Không tự kết luận nút Stop luôn gửi `SIGTERM` hoặc luôn bỏ qua `@PreDestroy`.

Sau bài này bạn có thể:

1. Phân biệt **graceful shutdown**, **terminate** và **force kill**.
2. Hiểu khi nào JVM có cơ hội chạy shutdown hooks và khi nào không.
3. Giải thích vai trò của `SpringApplication`, `ApplicationContext.close()`, `ContextClosedEvent`, `SmartLifecycle.stop(Runnable)`, `@PreDestroy` và graceful web server.
4. Nêu rõ giới hạn nút Stop/Exit/Terminate của IDE theo phiên bản, run configuration, hệ điều hành và cơ chế launch.
5. Thử dừng một ứng dụng Spring Boot 3.3.13 chạy bằng JDK 21 với `SIGTERM` và phân biệt với `SIGKILL`.
6. Viết test shutdown xác định, không phụ thuộc cách IDE thực thi Stop.
7. Thiết kế shutdown production để request/job còn chạy không sử dụng tài nguyên đã đóng.

## 2. Ba kiểu dừng quan trọng

### 2.1. Dừng có kiểm soát (graceful shutdown)

Ứng dụng được thông báo nên ngừng hoạt động và **có cơ hội** thực hiện các bước:

```text
Yêu cầu dừng có kiểm soát
  |
  +-- Ngừng nhận công việc/traffic mới
  +-- Chờ request/job đang chạy với deadline
  +-- Dừng các lifecycle components
  +-- Flush / checkpoint / ACK nếu phù hợp
  +-- Destroy các Spring beans
  +-- Đóng tài nguyên và rời tiến trình
```

"Graceful" **không** đồng nghĩa bảo đảm 100% tất cả công việc sẽ hoàn tất. Nếu request bị treo hoặc vượt timeout, hệ thống vẫn có thể phải hủy công việc, trả lỗi hoặc bị nền tảng kill sau grace period.

### 2.2. Kết thúc thông thường (normal JVM shutdown)

Với JVM thông thường, các đường như:

- Phương thức `main` kết thúc và không còn non-daemon thread giữ tiến trình.
- Lời gọi `System.exit(status)`.
- Một tín hiệu kết thúc có xử lý bởi JVM, thường là `SIGTERM`/`SIGINT` trên hệ Unix-like.

có thể đưa JVM vào trình tự shutdown và chạy các **shutdown hooks đã đăng ký**, trong đó Spring Boot mặc định có cơ chế đóng context. Nhưng nếu tiến trình không có context Boot hợp lệ, đã tắt hook, lỗi runtime nghiêm trọng hoặc tín hiệu không đến JVM con, kết quả sẽ khác.

**Phân biệt:** Java shutdown hook là cơ chế của JVM; graceful shutdown HTTP là cơ chế cụ thể của Spring Boot được thực thi khi context đóng. Có JVM hook **chưa đủ** để kết luận mọi request/job được drain thành công.

### 2.3. Buộc kết thúc (forceful termination)

Một lệnh kết thúc tiến trình cưỡng bức thường không cho JVM chạy shutdown hooks, ví dụ:

- `SIGKILL` trên Linux/macOS (`kill -KILL` hoặc `kill -9`).
- `Runtime.getRuntime().halt(status)` trong JVM.
- Cơ chế hủy tiến trình cưỡng bức của OS/IDE/process manager.
- Mất điện, container bị kill bất ngờ, JVM crash nghiêm trọng.

Khi đó `@PreDestroy`, `finally` hoặc cleanup trên worker threads **không được bảo đảm chạy**. Một bản ghi log có thể còn nằm trong buffer; thiếu log cũng chưa đủ để kết luận chính xác method nào đã/không chạy. Muốn không mất dữ liệu cần transaction, durable queues, idempotent retries và checkpoint.

## 3. So sánh IDE Stop và các hành động dừng

| Hành động | Ai khởi xướng? | Cơ hội chạy Spring shutdown? | Điều cần lưu ý |
| --- | --- | --- | --- |
| **IDE Stop** | Run/Debug tool window | **Phụ thuộc IDE, phiên bản, cấu hình, OS và launcher** | Có thể terminate nhẹ, mô phỏng interrupt hoặc force kill |
| **IDE Exit/Graceful Exit** (nếu IDE cung cấp) | IDE có hỗ trợ lối thoát êm | Có thể chủ động cho ứng dụng đi qua đường kết thúc bình thường | Không phải mọi IDE/phiên bản đều có cùng nút |
| **`Ctrl+C` trong terminal** | Người vận hành | Thường có, nếu tín hiệu/console event đến JVM đúng cách | Trên Unix-like thường là `SIGINT`; trong Windows là console control event |
| **`kill -TERM PID`** | OS Unix-like | Thường có, JVM có thể chạy shutdown hooks | Phải gửi đến PID của **JVM thực**, không nhầm wrapper |
| **`kill -KILL PID`** | OS Unix-like | **Không** | Bỏ qua shutdown hooks, cleanup |
| **`context.close()`** | Code trong ứng dụng | Có, thực thi Spring lifecycle trên context đó | Không nhất thiết kết thúc JVM nếu còn threads/context khác |
| **`SpringApplication.exit(context)`** | Code trong ứng dụng | Đóng context và tính exit code qua cơ chế Boot | Bản thân API không thay lệnh dừng OS trong mọi trường hợp |
| **`System.exit(code)`** | Code trong JVM | Thường kích hoạt JVM shutdown hooks | Không nên dùng tùy tiện trong business code |
| **`Runtime.halt(code)`** | Code trong JVM | **Không** | Kết thúc nhanh, không bảo đảm flush |
| **`docker stop` / Kubernetes graceful termination** | Nền tảng điều phối | Thường gửi tín hiệu dừng rồi chờ grace period | Hết hạn sẽ dùng cơ chế cưỡng bức; cần cấu hình và kiểm chứng |

**Không hiểu bảng như cam kết tuyệt đối:** launcher Maven/Gradle, process tree, debugger, script wrapper, terminal emulator, Windows hay container có thể thay đổi cách tín hiệu được gửi và chuyển tiếp.

### 3.1. Nút Stop không phải lệnh Java chuẩn

Java không định nghĩa một API tên "IDE Stop". IDE có thể chọn terminate process, gửi console interrupt, chạy script, tách debugger hoặc kill process tree. Trường hợp bạn bấm Stop cho **Maven/Gradle task**, thứ bị dừng ban đầu có thể là **build tool**, không phải JVM Spring Boot trực tiếp.

Ngay cả giữa các tài liệu/giao diện của một IDE, Stop, Exit, Kill Process và Debug Stop có thể có ngữ nghĩa khác nhau. **Đọc help của đúng phiên bản IDE/run configuration và kiểm tra bằng thí nghiệm** thay vì mang một quy tắc từ IntelliJ sang Eclipse hoặc VS Code.

### 3.2. Trường hợp IntelliJ IDEA

Tài liệu JetBrains có mô tả cả hành động **Stop**, **Exit** và **Kill Process** trong Run tool window; cũng mô tả tình huống Stop thực hiện soft kill trước khi có lựa chọn kill cưỡng bức. Ở những trang hướng dẫn khác, Stop được diễn giải như forceful termination có thể bỏ qua cleanup. Vì hành vi còn thay đổi theo phiên bản và bối cảnh chạy, không thể khẳng định **mọi** nút Stop của IntelliJ đều gửi `SIGTERM`, `SIGINT` hay đều chạy hooks.

Một cách kiểm tra thực tế là: chạy một ứng dụng có log `ContextClosedEvent`, `SmartLifecycle.stop` và `@PreDestroy`; bấm Stop **một lần**, quan sát log; sau đó lặp lại với **Exit** nếu có, hoặc chạy JAR trực tiếp trong terminal rồi gửi `SIGTERM`. Không bấm **Kill Process** nếu đang kiểm tra graceful behavior của một workload có dữ liệu quan trọng.

### 3.3. Eclipse, VS Code và IDE khác

Các nút **Terminate/Stop** thường nhằm điều khiển **process/debug session**. Không dùng tên nút để suy luận JVM đã thực thi shutdown hooks.

Đặc biệt, ứng dụng debug attach vào JVM có sẵn có thể chỉ bị **detach debugger**; tiến trình Spring Boot vẫn chạy. Ngược lại, một launcher cấu hình "terminate" có thể hủy tiến trình rất nhanh. Phải phân biệt dừng phiên debug, dừng task runner và dừng JVM thật.

## 4. Spring Boot xử lý một lần dừng có kiểm soát ra sao?

Trong ứng dụng Boot khởi động bình thường, `SpringApplication` mặc định đăng ký shutdown hook để đóng `ApplicationContext` khi JVM đi qua trình tự shutdown thích hợp.

Khi context được đóng, các mốc quan trọng khái niệm là:

```text
JVM xử lý shutdown hợp lệ
   |
   +-- Shutdown hook của Spring Boot
         |
         +-- ConfigurableApplicationContext.close()
               |
               +-- Công bố ContextClosedEvent
               |
               +-- LifecycleProcessor.onClose()
               |     +-- Dừng SmartLifecycle theo phase/dependency
               |     +-- Web server graceful shutdown nếu được bật
               |     +-- stop(Runnable) có thể đợi callback/timeout
               |
               +-- Destroy singleton beans
                     +-- @PreDestroy / DisposableBean / destroy method
```

**Không nhầm thứ tự event:** `ContextClosedEvent` được phát khi bắt đầu đóng context, trước các bước stop/destroy thông thường. `@PreDestroy` diễn ra trong bean destruction, nên một component đang `stop()` không được mặc nhiên xem là đã `@PreDestroy`.

### 4.1. SmartLifecycle và deadline

`SmartLifecycle` mở rộng `Lifecycle` để Spring điều phối:

- `start()`, `stop()`, `isRunning()`;
- `isAutoStartup()`;
- `getPhase()`;
- `stop(Runnable callback)` khi cần biết thời điểm stop thực sự hoàn tất.

Thông thường phase lớn **start sau**, nhưng **stop trước** phase nhỏ. Quan hệ bean dependency được Spring biết có thể được ưu tiên hơn phase, vì dependent component phải dừng trước dependency của nó.

Callback `stop(Runnable)` phải được gọi khi việc dừng đã hoàn tất theo hợp đồng. Nếu listener container chỉ gửi yêu cầu stop async và gọi callback ngay, Spring có thể chuyển sang đóng tài nguyên bên dưới quá sớm.

### 4.2. Graceful HTTP shutdown chỉ là một phần

Spring Boot 3.3 có thuộc tính:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Với ứng dụng web có embedded server, graceful shutdown là một phần khi **đóng application context**. Nó cố giảm/không nhận requests mới và cho các requests hiện có hoàn thành trong thời gian chờ cấu hình. Boot hỗ trợ Tomcat, Jetty, Reactor Netty và Undertow; cơ chế từ chối requests mới phụ thuộc server/connection.

Một HTTP request có thể đã gửi một **background task** vào executor rồi trả response. Task này **không tự trở thành** một in-flight HTTP request cho graceful server shutdown; nếu cần, service quản lý task phải thiết kế stop/drain riêng.

### 4.3. Readiness và mốc ApplicationReadyEvent

`ApplicationReadyEvent` xảy ra **sau khi các runners hoàn tất** trong luồng startup thành công. Khi shutdown, điều cần quan tâm là **ngừng nhận traffic và jobs mới** rồi mới drain; đừng nhầm "đã từng ready" với "vẫn có thể nhận việc trong suốt shutdown".

Availability/readiness có thể được dùng để nói với orchestrator tạm từ chối traffic, nhưng `ReadinessState.REFUSING_TRAFFIC` **không tự đóng socket hoặc hủy tất cả tasks**. Để an toàn cần kết hợp platform routing, graceful server và consumer-specific lifecycle.

## 5. Ví dụ Spring Boot 3.3.13 + Java 21 đầy đủ

Ta xây một ứng dụng **web** để quan sát đồng thời:

1. Một HTTP request `/work` có thể đang chạy khi shutdown bắt đầu.
2. `ContextClosedEvent` được công bố.
3. Một `SmartLifecycle` dừng và báo callback.
4. Bean được destroy qua `@PreDestroy`.
5. Khi bấm Stop trong IDE hoặc gửi `SIGTERM`, có thể so sánh các dấu mốc.

Demo cố ý dùng `Thread.sleep` **chỉ để mô phỏng request chậm**; production phải dùng deadline, client timeouts và concurrency controls phù hợp.

### 5.1. Cấu trúc project

```text
shutdown-signal-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/shutdown/
    │   │   ├── ShutdownSignalApplication.java
    │   │   ├── ShutdownTrace.java
    │   │   ├── WorkController.java
    │   │   └── ShutdownWitness.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/shutdown/
            └── ShutdownContractTest.java
```

### 5.2. pom.xml

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
    <artifactId>shutdown-signal-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Chỉ dùng web starter và test starter; không cần database, Actuator hay broker để chạy ví dụ.

### 5.3. application.properties

Tệp `src/main/resources/application.properties`:

```properties
spring.application.name=shutdown-signal-demo
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

`server.shutdown=graceful` đặc biệt cần được bật khi dùng Spring Boot **3.3**. Không suy diễn mặc định của một phiên bản Boot mới hơn sang 3.3. Timeout 20 giây là ví dụ, không phải mức phù hợp mọi hệ thống.

### 5.4. ShutdownSignalApplication.java

```java
package com.example.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShutdownSignalApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShutdownSignalApplication.class, args);
    }
}
```

`SpringApplication.run(...)` giữ context/web server hoạt động. **Không** đóng context ngay sau khi `run()` trả về trong app server này; shutdown sẽ được kích hoạt khi JVM nhận yêu cầu dừng phù hợp hoặc ứng dụng chủ động đóng context.

### 5.5. ShutdownTrace.java

```java
package com.example.shutdown;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;

@Component
public class ShutdownTrace {

    private final CopyOnWriteArrayList<String> events =
            new CopyOnWriteArrayList<>();

    public void record(String event) {
        events.add(event);
        System.out.println("DEMO " + event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
```

Bean này ghi dấu mốc lifecycle. `System.out.println` giúp minh họa, còn production nên dùng structured logging, metrics, trace IDs, flush policy và quan sát bên ngoài. **Chỉ có `System.out` không phải bằng chứng hoàn tất bền vững** vì stdout có thể được buffer hoặc process bị kill giữa chừng.

### 5.6. ShutdownWitness.java

```java
package com.example.shutdown;

import jakarta.annotation.PreDestroy;

import org.springframework.context.SmartLifecycle;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownWitness implements SmartLifecycle {

    private final ShutdownTrace trace;
    private volatile boolean running;

    public ShutdownWitness(ShutdownTrace trace) {
        this.trace = trace;
    }

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }
        running = true;
        trace.record("LIFECYCLE start");
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }
        trace.record("LIFECYCLE stop");
        running = false;
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

    @EventListener
    public void onClosing(ContextClosedEvent event) {
        trace.record("CONTEXT closing");
    }

    @PreDestroy
    void onDestroy() {
        trace.record("BEAN preDestroy");
    }
}
```

`SmartLifecycle.isAutoStartup()` mặc định `true`, nên `start()` được gọi trong refresh context. Khi context đóng qua đường hợp lệ, listener có thể thấy `ContextClosedEvent`; sau đó lifecycle processor gọi `stop(callback)` và cuối cùng bean destruction gọi `@PreDestroy`.

`stop(Runnable)` của demo đồng bộ, vì thế callback được gọi ngay **sau khi** `stop()` hoàn tất. Với consumer thật phải đợi/drain công việc, không gọi callback quá sớm.

**Thứ tự giữa `CONTEXT closing`, các request còn đang chạy và logs của web server có thể xen kẽ**. Không nên so toàn bộ console như một chuỗi tuyệt đối.

### 5.7. WorkController.java

```java
package com.example.shutdown;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class WorkController {

    private final ShutdownTrace trace;

    public WorkController(ShutdownTrace trace) {
        this.trace = trace;
    }

    @GetMapping("/work")
    public String work(@RequestParam(defaultValue = "8") int seconds)
            throws InterruptedException {

        if (seconds < 1 || seconds > 15) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "seconds must be 1..15");
        }

        trace.record("HTTP work begin");

        try {
            Thread.sleep(seconds * 1000L);
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            trace.record("HTTP work interrupted");
            throw ex;
        }

        trace.record("HTTP work complete");
        return "completed";
    }
}
```

Controller giả lập một request dài tối đa 15 giây. Trong sản phẩm thực tế, **không sử dụng `Thread.sleep` để thực hiện công việc nghiệp vụ**; điều này chỉ giúp tái hiện một in-flight HTTP request.

Để kiểm chứng graceful shutdown, chọn request 8 giây, grace period 20 giây và gửi tín hiệu dừng khi request vẫn đang chạy. Khi server và OS cho phép shutdown có kiểm soát, request có cơ hội trả `completed`; với kill cưỡng bức, kết nối có thể bị reset hoặc request bị ngắt.

### 5.8. Build và khởi động

Cần JDK 21, Maven và quyền tải dependencies.

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/shutdown-signal-demo-0.0.1-SNAPSHOT.jar
```

Trong lần chạy JAR bình thường, code `ShutdownWitness.start()` in:

```text
DEMO LIFECYCLE start
```

Các thông báo còn lại là log Spring Boot và container web. `LIFECYCLE start` xảy ra trong quá trình refresh, trước khi application ready theo lifecycle Boot.

## 6. Thực nghiệm dừng qua terminal thay vì dựa vào IDE

### 6.1. Thực nghiệm Linux/macOS: SIGTERM

**Terminal A:** chạy JAR bằng lệnh trực tiếp:

```bash
java -jar target/shutdown-signal-demo-0.0.1-SNAPSHOT.jar
```

**Terminal B:** tạo request kéo dài 8 giây:

```bash
curl -v "http://localhost:8080/work?seconds=8"
```

Trong khi request chưa hoàn tất, tìm **đúng PID của JVM demo**, ví dụ:

```bash
jps -l
```

Sau đó yêu cầu kết thúc có kiểm soát:

```bash
kill -TERM <PID_CUA_JVM_DEMO>
```

Thay phần `<PID_CUA_JVM_DEMO>` bằng số PID thực tế; không copy nguyên placeholder vào shell. **Không chọn nhầm JVM của IDE hoặc ứng dụng khác.** Lệnh `jps` cần JDK tools và danh sách có thể chứa nhiều tiến trình.

**Các dấu mốc cần quan sát** trong trường hợp shutdown hook và graceful web server được thực thi:

```text
DEMO HTTP work begin
DEMO CONTEXT closing
DEMO HTTP work complete
DEMO LIFECYCLE stop
DEMO BEAN preDestroy
```

**Đây là một kịch bản quan sát phù hợp, không phải thứ tự stdout tuyệt đối được bảo đảm cho mọi scheduling.** `CONTEXT closing` thường được in khi close bắt đầu, trong khi request còn có thể đang chạy. Điều quan trọng cần kiểm chứng là:

- Request đã bắt đầu và **có cơ hội** hoàn tất trong thời hạn.
- Spring context nhận quá trình close.
- `SmartLifecycle` được stop.
- Bean có `@PreDestroy` được destroy.
- Client nhận được response thành công hoặc một lỗi có lý do nếu bị timeout/interrupt.

Nếu request đã hoàn thành **trước khi** gửi SIGTERM, log `HTTP work complete` sẽ xuất hiện trước `CONTEXT closing`. Đó không phải lỗi; cần lặp lại thí nghiệm và gửi tín hiệu sớm hơn để thật sự quan sát in-flight draining.

### 6.2. Thực nghiệm Linux/macOS: SIGKILL

**Chỉ thử trên instance demo không có dữ liệu thật.** Khởi động lại JAR, gửi một request dài, rồi tìm lại **PID mới** và dùng:

```bash
kill -KILL <PID_CUA_JVM_DEMO>
```

Với `SIGKILL`, JVM không thể chạy shutdown hooks và Spring không có cơ hội thực thi trình tự `ContextClosedEvent`, `SmartLifecycle.stop` hoặc `@PreDestroy` do lệnh kill này gây ra.

Do đó thường sẽ **không thấy** các dấu mốc shutdown xuất hiện sau kill. Tuy nhiên, thiếu log từ console không phải một phương pháp kiểm chứng tuyệt đối: output có thể bị mất vì buffering hoặc transport. Cần quan sát phía client và tài nguyên ngoài tiến trình nếu muốn xác nhận hậu quả.

**Không dùng `kill -9` như thao tác shutdown thường ngày cho ứng dụng production.** Khi deadline đã cạn và force kill thật sự cần thiết, phải có cơ chế phục hồi nghiệp vụ sau crash.

### 6.3. Ctrl+C

Trên terminal Unix-like, `Ctrl+C` thường tạo `SIGINT` cho foreground process group. JVM thông thường có thể xử lý sự kiện này và chạy shutdown hooks; nhưng nếu JAR được chạy qua wrapper, terminal khác, IDE hoặc build tool, đừng giả định JVM con nhận đúng tín hiệu.

Trên Windows, `Ctrl+C` là console control event, **không phải POSIX SIGTERM**. Một console Java process thông thường có thể đi qua shutdown, nhưng `Stop-Process`, Task Manager và nút Stop của IDE không phải cách kiểm chứng tương đương. Với Windows, ưu tiên test in-process `context.close()` và đối chiếu shutdown behavior của launcher cụ thể trước khi dựa vào một cách dừng trong môi trường vận hành.

### 6.4. Vì sao nên chạy JAR trực tiếp?

Nếu chạy:

```bash
mvn spring-boot:run
```

hoặc chạy qua một Gradle task, terminal có thể đang điều khiển **Maven/Gradle launcher**, không phải PID của application JVM. Launcher có thể sinh child process, chuyển tiếp signals theo chính sách riêng hoặc terminate children. Để loại bớt biến số khi học cơ chế JVM shutdown, hãy chạy `java -jar` trực tiếp và gửi tín hiệu tới **đúng PID**.

### 6.5. Thực nghiệm với IDE Stop

Sau khi thử terminal:

1. Run application từ IDE theo cấu hình bạn thường dùng, chờ server lắng nghe.
2. Gọi `/work?seconds=8` từ terminal bên ngoài.
3. Khi request đang chạy, **bấm Stop một lần**.
4. Ghi nhận request kết thúc thành công hay lỗi; tìm các dấu mốc `DEMO CONTEXT closing`, `DEMO LIFECYCLE stop`, `DEMO BEAN preDestroy`.
5. Nếu IDE hỗ trợ lối **Exit/Graceful** khác Stop, thử lại để so sánh.
6. Ghi rõ IDE version, Run hay Debug, JDK, OS và loại run configuration.
7. Không bấm Kill Process lặp lại khi đang cố kiểm chứng graceful shutdown.

**Kết quả hợp lệ:** nếu trên IDE không xuất hiện các dấu mốc mà terminal SIGTERM có, điều đó chỉ ra đường dừng IDE/launcher không đi qua cùng trình tự cleanup hoặc log không được truyền; phải xem thêm tài liệu và thực nghiệm để phân biệt. Nếu có đủ dấu mốc, **vẫn** cần kiểm tra in-flight work và deadline chứ không chỉ thấy một dòng `@PreDestroy`.

## 7. JUnit kiểm thử lifecycle mà không cần OS signal

Một test đơn vị/integration nhỏ có thể đóng Spring context **trong cùng JVM**, không phụ thuộc IDE Stop hay tín hiệu hệ điều hành. Test sau xác minh thứ tự event → stop → destroy, còn HTTP graceful drain cần thí nghiệm thực tế ở mục 6.

Tệp `src/test/java/com/example/shutdown/ShutdownContractTest.java`:

```java
package com.example.shutdown;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ShutdownContractTest {

    @Test
    void contextCloseInvokesLifecycleAndDestroy() {
        ShutdownTrace trace;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             ShutdownTrace.class, ShutdownWitness.class)) {
            trace = context.getBean(ShutdownTrace.class);
            assertTrue(context.getBean(ShutdownWitness.class).isRunning());
        }

        assertEquals(List.of(
                "LIFECYCLE start",
                "CONTEXT closing",
                "LIFECYCLE stop",
                "BEAN preDestroy"
        ), trace.snapshot());
    }
}
```

`AnnotationConfigApplicationContext` tạo và refresh bean context thật, `SmartLifecycle` được auto-start, còn `try-with-resources` đóng context đúng đường Spring. `@EventListener(ContextClosedEvent.class)` và `@PreDestroy` được Spring xử lý khi context đóng.

Chạy:

```bash
mvn test
```

Kỳ vọng lớp test này có **một test thành công** khi dự án biên dịch đúng. Test không mở web server, không bắt tín hiệu OS và không chứng minh IDE Stop gửi loại tín hiệu nào; nó chỉ kiểm chứng **hợp đồng đóng context**.

## 8. Khi một request hoặc background task còn đang chạy

### 8.1. Graceful HTTP shutdown và background executor

Giả sử request nhận lệnh tạo báo cáo:

```java
@GetMapping("/submit")
public String submit() {
    taskExecutor.execute(this::generateReport);
    return "accepted";
}
```

**Đoạn minh họa, không phải phần của project chạy được ở mục 5.** Khi response `"accepted"` được trả về, HTTP request đã kết thúc nhưng `generateReport` có thể vẫn ở queue hoặc đang xử lý. Do đó web server đã drain hết HTTP requests **không** đồng nghĩa task nền hoàn tất.

Một `SmartLifecycle` hoặc job coordinator cần:

- Dừng việc chấp nhận task mới.
- Chờ/cancel có kiểm soát các queued/running tasks.
- Ghi checkpoint hoặc retry state.
- Giữ DB/client/resource mở tới khi task không còn dùng.
- Báo `stop(Runnable callback)` hoàn tất **sau** khi các bước thật sự xong.

### 8.2. stop(Runnable) không được báo hoàn tất quá sớm

Anti-pattern:

```java
@Override
public void stop(Runnable callback) {
    executor.execute(this::drainPendingWork);
    callback.run(); // Sai: task mới được enqueue.
}
```

Đây là mã minh họa. Khi callback gọi ngay, lifecycle processor có thể chuyển sang đóng resource ở phase tiếp theo, khiến `drainPendingWork` sử dụng đối tượng đã đóng.

Mẫu đúng về ý nghĩa:

```java
@Override
public void stop(Runnable callback) {
    stopAcceptingNewWork();
    CompletionStage<Void> draining = drainWithDeadline();
    draining.whenComplete((ignored, failure) -> {
        if (failure != null) {
            recordFailure(failure);
            applyRecoveryPolicy();
        }
        markStopped();
        callback.run();
    });
}
```

**Mã trên là mẫu kiến trúc không biên dịch độc lập**, cần các methods, imports và cơ chế đồng bộ/cancellation cụ thể. Ngoài lỗi ở stage, cần xử lý cả exception xảy ra **trước khi** tạo stage. Callback không được bỏ quên, nhưng cũng không được báo đã drain thành công nếu công việc còn tiếp tục sử dụng tài nguyên.

### 8.3. Chờ có timeout chứ không chờ vô hạn

`Future.get(timeout, unit)`, `CountDownLatch.await(timeout, unit)` hoặc completion stage có deadline giúp giới hạn shutdown. Timeout **không tự làm** remote I/O dừng hoặc rollback; cần request cancellation, JDBC/HTTP client timeouts, checkpoint và idempotency/retry.

Không gọi blocking `future.get()` trên **chính worker thread duy nhất** mà tác vụ cần chờ cũng đang queue ở executor đó: điều này có thể gây deadlock.

## 9. Thử nghiệm dừng trong container và production

### 9.1. Docker và Kubernetes

Với một container Spring Boot:

```text
Orchestrator yêu cầu dừng
   |
   +-- Thông báo SIGTERM / termination intent
   +-- Cho thời gian grace period
   |      +-- context close
   |      +-- web graceful shutdown
   |      +-- lifecycle stop/drain
   |      +-- bean destruction
   |
   +-- Nếu quá hạn: force kill
```

Thực tế phụ thuộc entrypoint, PID 1, signal propagation, shell wrapper và cách process được khởi chạy. Nếu `java` là child của một shell script không chuyển tiếp tín hiệu, JVM có thể **không nhận được** lệnh dừng mà orchestration gửi đến PID 1. Cần kiểm tra container entrypoint và quy trình terminate thực tế.

### 9.2. Grace period phải thống nhất

`spring.lifecycle.timeout-per-shutdown-phase=20s` không bảo đảm pod được cấp 20 giây nếu nền tảng kill tiến trình sớm hơn; mỗi phase cũng có thể tiêu tốn thời gian riêng. Thiết kế tổng shutdown budget phải bao gồm:

- Thời gian load balancer ngừng gửi việc mới.
- Thời gian hoàn tất các HTTP requests còn sống.
- Thời gian ngừng consumer/scheduler.
- Thời gian drain background tasks, flush, checkpoint.
- Thời gian đóng connection pools, logger và tài nguyên khác.

Không nhân một số timeout cho từng phase mà không tính tổng deadline của nền tảng.

### 9.3. Khi ứng dụng tự quyết định dừng

Một internal coordinator được ủy quyền có thể gọi `context.close()` hoặc sử dụng API `SpringApplication.exit(context)` khi phù hợp. Ưu điểm là đi qua Spring lifecycle có chủ đích, có thể đặt breakpoint và kiểm thử mà không phụ thuộc một nút UI.

**Cẩn trọng:** không mở một HTTP endpoint `/shutdown` công khai chỉ để thử nghiệm. Nếu cần administrative shutdown, phải có authentication/authorization, audit, network restriction và phương án vận hành chính thức. Không dùng một endpoint không bảo vệ để cho phép người ngoài dừng service.

### 9.4. SIGKILL và tính bền vững

Ngay cả khi xây dựng graceful shutdown tốt, ứng dụng vẫn phải xử lý kịch bản bị crash/force-kill:

- Dữ liệu nghiệp vụ quan trọng được ghi bằng transaction.
- Consumer xử lý message **idempotent**.
- Job đang làm có checkpoint hoặc trạng thái retry.
- Outbox hoặc durable queue bảo đảm message không mất khi process chết.
- Lần startup tiếp theo có thể phát hiện unfinished work và xử lý lại an toàn.

**Không xây thiết kế "không mất việc" dựa duy nhất vào `@PreDestroy` hay JVM shutdown hook.**

## 10. Các ngộ nhận thường gặp

| Ngộ nhận | Thực tế | Cách xử lý |
| --- | --- | --- |
| "Bấm Stop IDE luôn gọi @PreDestroy" | Tùy cơ chế IDE/launcher/OS | Kiểm chứng mốc `ContextClosedEvent`, stop và destroy |
| "Bấm Stop IDE luôn là SIGTERM" | Nhiều IDE dùng Stop/Exit/Kill có ngữ nghĩa khác | Đọc docs phiên bản đang dùng; test trực tiếp |
| "JVM bị terminate là mọi hook đã chạy" | Force kill có thể bỏ qua hooks | Phân biệt graceful và kill cưỡng bức |
| "SIGKILL có thể được catch để cleanup" | SIGKILL không cho JVM xử lý hooks | Thiết kế khôi phục sau crash |
| "Có @PreDestroy là graceful shutdown" | Chưa chứng minh HTTP requests và jobs đã drain | Graceful web + lifecycle job drain |
| "ContextClosedEvent nghĩa là resource đã đóng" | Event được phát đầu quá trình close | Quan sát mốc stop/destroy riêng |
| "Đã bấm Stop thì process chắc chắn chết" | IDE có thể chỉ detach debug hoặc soft-stop bị chặn | Kiểm tra PID và process tree |
| "Dừng Maven task luôn dừng Spring child JVM đúng cách" | Launcher có thể không forward signal | Thử `java -jar` trực tiếp |
| "Ctrl+C và SIGTERM giống nhau ở mọi OS" | Windows console event khác POSIX signal | Test theo OS và launcher thật |
| "HTTP không còn request là job nền đã xong" | Job có thể đã tách request thread | Quản lý in-flight jobs riêng |
| "20s shutdown timeout là chắc chắn hết jobs" | Task có thể chậm/không hợp tác | Timeout + cancellation + retry/checkpoint |
| "Tăng grace period càng lớn càng tốt" | Có thể vượt deadline deploy, làm service trì hoãn quá lâu | Đo và đặt budget phù hợp |
| "`System.exit` là cách dừng mọi service request" | Có thể cắt traffic/other contexts bất ngờ | Dùng managed orchestration/close phù hợp |
| "Log thiếu @PreDestroy chứng minh Java chưa gọi" | Console có thể mất output khi kill | Đối chiếu thêm test, exit code, external metrics |
| "Nút Stop debug giống nút Detach" | Một thao tác có thể chỉ tách debugger, thao tác khác terminate process | Xác định hành động cụ thể và kiểm tra process |

## 11. Checklist chẩn đoán khi Stop IDE không graceful

1. IDE nào, version nào, Run hay Debug, Stop/Exit/Terminate/Kill Process?
2. JDK vendor và version nào, OS nào?
3. JVM chạy trực tiếp hay qua Maven/Gradle, shell script, debugger hoặc container?
4. Sau khi bấm Stop, **PID của JVM** có biến mất không?
5. `ContextClosedEvent` được ghi lại không?
6. Có `SmartLifecycle.stop(Runnable)` và callback completion không?
7. Có `@PreDestroy` / destroy methods chạy không?
8. Có cấu hình `server.shutdown=graceful` đúng phiên bản Boot 3.3 không?
9. `spring.lifecycle.timeout-per-shutdown-phase` có đủ và có thống nhất với platform grace period?
10. Request đang chạy có hoàn tất hay bị cắt? Có biết lỗi phía client không?
11. Task nền nào vẫn dùng executor/DataSource sau khi context đóng?
12. Có custom shutdown hook nào treo hoặc race với hook khác không?
13. JVM có nhận đúng `SIGTERM` nếu thử từ terminal tới PID trực tiếp không?
14. Console output có thể bị buffer hoặc mất log không?
15. Có điểm nào kích hoạt force kill (bấm lần 2, timeout orchestrator, process manager) không?
16. Có retry, checkpoint, durable state khi tiến trình chết đột ngột không?

Nếu thử `java -jar` + `SIGTERM` thấy đầy đủ stop/destroy, còn IDE Stop không có, hãy ưu tiên **kiểm tra đường terminate của IDE và launcher**; đừng vội sửa annotation Spring hoặc tăng timeout khi thực chất JVM không có cơ hội đóng context.

## 12. Bài tập thực hành

1. Nêu khác biệt giữa một IDE Stop action và POSIX `SIGTERM`.
2. Vì sao `SIGKILL` không gọi được `@PreDestroy`?
3. Vẽ timeline `ContextClosedEvent` → `SmartLifecycle.stop` → `@PreDestroy`.
4. Khi nào một `@PreDestroy` log xuất hiện nhưng HTTP requests vẫn chưa được xử lý đúng?
5. Trong demo, vì sao cần bật `server.shutdown=graceful` trên Boot 3.3?
6. Dùng hai terminal chạy `/work?seconds=8` và gửi `SIGTERM`; ghi nhận request hoàn tất hay bị ngắt.
7. Chạy lại JAR, gửi `SIGKILL` tới đúng PID demo; giải thích kết quả.
8. Thử Stop/Exit trên IDE đang sử dụng, ghi rõ version và OS. Nó có đi qua same lifecycle không?
9. Vì sao nên khởi động JAR trực tiếp khi so sánh signal behavior thay vì chạy qua `mvn spring-boot:run`?
10. Trong Windows, vì sao không thể dùng lệnh `kill -TERM` của Unix như một phép thử mặc định?
11. Viết test `AnnotationConfigApplicationContext` xác nhận `SmartLifecycle.stop` và `@PreDestroy` mà không cần gửi OS signal.
12. Nếu request đã trả response nhưng async job còn chạy, graceful HTTP shutdown có đợi job không?
13. Vì sao `stop(Runnable callback)` không được gọi callback ngay khi enqueue task drain?
14. Tại sao `Future.get(timeout)` không tự hủy một HTTP call đang block?
15. Nếu Kubernetes kill pod trước khi Spring hết timeout, tác động gì tới pending jobs?
16. Một message consumer cần làm gì trước khi connection factory bị destroy?
17. Viết kế hoạch test shutdown với một request chạy 5 giây, grace period 20 giây và lần thử force kill.
18. Nêu các cơ chế bảo đảm an toàn khi JVM crash bất ngờ: transaction, outbox, queue, retry, idempotency.
19. Phân biệt `System.exit`, `Runtime.halt` và `context.close`.
20. Vì sao không nên mở endpoint shutdown không bảo vệ chỉ để debug?
21. Nếu quan sát `DEMO CONTEXT closing` nhưng thiếu `DEMO BEAN preDestroy`, bạn cần điều tra gì tiếp?
22. Nếu `Ctrl+C` trong terminal chạy Maven không dừng đúng JVM con, bạn cần kiểm tra gì?
23. Đề xuất một runbook cho shutdown production gồm traffic drain, worker drain, resource close và timeout fallback.
24. So sánh loại thông tin chứng minh được qua test đóng context với thí nghiệm SIGTERM trên tiến trình thật.
25. Giải thích vì sao một hệ thống vẫn cần xử lý force kill dù mọi service đều có graceful shutdown.

**Tiêu chí đạt:** không đồng nhất IDE Stop với graceful shutdown; biết dùng tín hiệu dừng có kiểm soát ở đúng OS/JVM; đọc được log `ContextClosedEvent`, `SmartLifecycle` và `@PreDestroy`; hiểu shutdown timeout, HTTP drain và job drain là các khái niệm khác nhau; thiết kế được phương án xử lý khi process không thể cleanup.

## 13. Tài liệu chính thức và nguồn tham khảo

- Spring Boot 3.3 — Graceful Shutdown, cấu hình timeout và cảnh báo shutdown trong IDE: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — SpringApplication và vòng đời application events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework 6.1 — SmartLifecycle API và stop(Runnable): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — AbstractApplicationContext.close(): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Java 21 — JVM shutdown hooks, Runtime API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html
- JetBrains IntelliJ IDEA — Run tool window, Stop/Exit/Kill Process: https://www.jetbrains.com/help/idea/run-tool-window.html
- JetBrains IntelliJ IDEA — Running Applications, Stop vs Exit: https://www.jetbrains.com/help/idea/running-applications.html
- Linux man-pages — signal(7), SIGTERM/SIGKILL: https://man7.org/linux/man-pages/man7/signal.7.html
