# Phân biệt dừng từ IDE, tín hiệu hệ điều hành và tiến trình bị buộc kết thúc

Một ứng dụng Spring Boot đang xử lý request HTTP, ghi dữ liệu, chạy scheduled task hoặc tiêu thụ message từ broker có thể bị dừng theo nhiều cách: **nhấn Stop trong IDE**, **Ctrl+C ở terminal**, **gửi SIGTERM từ hệ điều hành**, **docker stop/kubectl delete pod**, hoặc **buộc kết thúc bằng SIGKILL, taskkill /F, crash hay mất điện**. Những thao tác này đều có thể làm ứng dụng “biến mất”, nhưng **không cùng bảo đảm về Spring ApplicationContext, lifecycle callbacks, HTTP connections và dữ liệu đang xử lý**.

Điểm cần phân biệt gồm **ba tầng độc lập**:

1. **Ai phát lệnh dừng và nó có tới đúng tiến trình JVM không?** IDE, shell, container runtime, Kubernetes hay hệ điều hành có thể gửi các signal/cơ chế terminate khác nhau.
2. **JVM và Spring có cơ hội đóng ứng dụng có trật tự không?** Shutdown hook, `ContextClosedEvent`, `SmartLifecycle.stop`, `@PreDestroy` và bean destruction chỉ có thể chạy khi runtime được cho phép.
3. **HTTP server có chờ request đang chạy kết thúc không?** Đây là *graceful web-server shutdown*, phải được cấu hình/kiểm tra phù hợp với **phiên bản Spring Boot**, timeout và hạ tầng.

**Cấu hình chính cho Spring Boot 3.3.x**:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

**Lưu ý về phiên bản:** Trong Spring Boot **3.3**, bật graceful shutdown bằng `server.shutdown=graceful`. **Spring Boot 3.4 trở đi đổi mặc định thành graceful** (có thể tắt bằng `server.shutdown=immediate`). Không sao chép kết luận “graceful mặc định” từ tài liệu Boot mới vào một dịch vụ Boot 3.3 chưa cấu hình. Đặt property tường minh trong bài giúp phép thử có kết quả dễ hiểu.

Bài này tập trung **Spring Boot 3.x, Java 17+, Spring MVC/Servlet và Tomcat nhúng**. Phần so sánh đề cập Jetty, Undertow, Reactor Netty, Docker, Linux/macOS, Windows, IDE và Kubernetes. Có demo Java 17+ chạy được, thí nghiệm HTTP request dài, các lệnh dừng an toàn chỉ nên thử ở local, ví dụ lifecycle callbacks và checklist triển khai.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích *graceful shutdown* khác *immediate shutdown* và *forced termination*.
- Phân biệt `Ctrl+C`, `SIGINT`, `SIGTERM`, `SIGKILL`, `System.exit`, `Runtime.halt` và thao tác Stop của IDE.
- Hiểu **Spring Boot có shutdown hook mặc định** nhưng hook chỉ giúp khi JVM bắt đầu shutdown sequence hợp lệ.
- Phân biệt `ContextClosedEvent`, `SmartLifecycle.stop(Runnable)`, `@PreDestroy` và thứ tự shutdown phases.
- Biết tại sao bean được destroy không tự chứng minh HTTP request đã trả xong.
- Cấu hình `server.shutdown` và `spring.lifecycle.timeout-per-shutdown-phase` theo Spring Boot 3.3.
- Chạy thí nghiệm một request kéo dài 8 giây, gửi `SIGTERM` và theo dõi response/log; đối chiếu với `SIGKILL`.
- Hiểu Docker StopSignal, stop timeout, PID 1 và exec-form `ENTRYPOINT`.
- Hiểu Kubernetes `preStop`, `terminationGracePeriodSeconds`, readiness, EndpointSlice và thời gian drain thực tế.
- Thiết kế queue consumers, DB transactions, cron jobs, SSE/WebSocket và distributed work an toàn trước crash.
- Kiểm thử khác biệt ở IDE, terminal, container và orchestrator mà không dựa vào một log line duy nhất.

## 2. Một bảng so sánh trước khi đi sâu

| Cách dừng | Lệnh/cơ chế thường gặp | JVM shutdown hook? | Có cơ hội chạy Spring callbacks? | Có chắc HTTP request hoàn tất? |
| --- | --- | --- | --- | --- |
| Nhấn Stop trong IDE | Tùy IDE/run configuration: gửi tín hiệu hoặc terminate process | **Không chắc** | **Không chắc** | **Không chắc**, phải kiểm tra |
| Ctrl+C trong terminal Unix | Thường gửi `SIGINT` tới foreground process group | Thường có nếu JVM xử lý tín hiệu | Thường có | Chỉ khi context đóng có trật tự và graceful server/timeouts phù hợp |
| Gửi `SIGTERM` trên Unix | `kill -TERM PID` | Thường có với JVM chuẩn | Thường có | Không tự động nếu Boot/version/config không hỗ trợ |
| `System.exit(code)` | Java chủ động khởi chạy JVM shutdown sequence | Có | Thường có nếu Boot hook/context được đăng ký | Phụ thuộc server graceful và deadline |
| `ApplicationContext.close()` | Đóng Spring context trực tiếp | Không cần JVM hook | Có trong context được đóng | Có thể có, nhưng JVM chưa chắc kết thúc |
| `docker stop` | Gửi stop signal (thường TERM), rồi KILL nếu quá hạn | Nếu tín hiệu tới JVM và còn thời gian | Có cơ hội | Phụ thuộc timeout Docker và Boot |
| Kubernetes pod termination | `preStop`, TERM, rồi KILL khi hết grace | Có cơ hội | Có cơ hội | Phụ thuộc drain, thời gian còn lại và app |
| `kill -9`/`SIGKILL` | Kernel buộc chấm dứt Unix process | **Không** | **Không** | **Không** |
| `docker kill` mặc định | Thường SIGKILL | **Không** | **Không** | **Không** |
| `taskkill /F`/TerminateProcess trên Windows | Buộc chấm dứt process | Không có bảo đảm chạy hook | Không có bảo đảm | Không |
| `Runtime.halt(code)` | JVM dừng ngay, không shutdown sequence | **Không** | **Không** | **Không** |
| Crash/JVM fatal error/host mất điện | Không có cửa sổ shutdown đáng tin | Không bảo đảm | Không bảo đảm | Không |

**Quy tắc:** đừng đánh đồng tên nút bấm hay command với kết quả thật. Hãy kiểm chứng **signal đến JVM, Spring context close, HTTP drain và dữ liệu được lưu/ACK** theo từng môi trường.

## 3. Ba tầng của một quá trình dừng ứng dụng

Một luồng dừng mong muốn:

```text
Operator / orchestrator yêu cầu dừng
                  |
                  v
Process JVM nhận TERM / cơ chế shutdown
                  |
                  v
JVM bắt đầu shutdown sequence
                  |
                  v
Spring Boot shutdown hook đóng ApplicationContext
                  |
                  v
ContextClosedEvent và lifecycle stop phases
                  |
                  +--> Graceful web server:
                  |      ngừng nhận request mới,
                  |      cho request đang chạy thời gian hoàn tất
                  |
                  +--> Stop workers / schedulers / consumers
                  |
                  v
Destroy managed beans (@PreDestroy, destroy())
                  |
                  v
JVM / process hoàn tất và rời khỏi hệ thống
```

Sơ đồ là **mô hình ý nghĩa**, không phải cam kết mọi callback luôn in theo đúng một thứ tự log cứng trên mọi server. Các phase `SmartLifecycle` có thứ tự, còn các hooks khác có quy tắc riêng; hệ thống đa thread có thể log đan xen.

Nếu quy trình bị cắt bởi `SIGKILL` hoặc hết thời gian orchestrator cho phép, phần còn lại **không được đảm bảo thực thi**. Hệ thống cần chịu được crash, không thể dựa hoàn toàn vào shutdown callbacks để giữ dữ liệu.

### 3.1. JVM shutdown sequence và Spring ApplicationContext

Theo Java Runtime, JVM có thể bắt đầu shutdown sequence khi:

- Chương trình gọi `System.exit`/`Runtime.exit`.
- Không còn non-daemon threads sống (với điều kiện runtime phù hợp).
- Một sự kiện ngoài, như interrupt/signal hệ điều hành được runtime xử lý.

Trong shutdown sequence, JVM bắt đầu những shutdown hooks đã đăng ký; thứ tự giữa các hooks **không được đảm bảo**. Spring Boot `SpringApplication` mặc định cấu hình `registerShutdownHook=true` để đóng `ApplicationContext` khi JVM shutdown bình thường. Do đó Spring-managed beans có cơ hội chạy lifecycle/destruction callbacks.

**Ngược lại:** `SIGKILL` và `Runtime.halt` không kích hoạt chuỗi shutdown thông thường; `finally`, try-with-resources, hook và `@PreDestroy` không có cơ hội chạy. Hãy phân biệt *một signal được JVM xử lý* với *lệnh cưỡng chế dừng process*.

### 3.2. “Có hook” không có nghĩa “request hoàn thành”

Ví dụ một Servlet request chạy 8 giây, trong khi SIGTERM tới. JVM có thể gọi Spring context close và `@PreDestroy`, nhưng HTTP server nếu shutdown ngay có thể cắt socket. Muốn request đang xử lý có thời gian hoàn tất, phải bật và kiểm tra **graceful web-server shutdown** theo đúng Boot version.

Một database transaction cũng cần bảo đảm riêng: connection có thể đóng, transaction rollback, hoặc caller không biết commit thành công hay chưa. Không dùng log `@PreDestroy invoked` làm bằng chứng mọi business operations đã hoàn tất.

### 3.3. “Có grace period” không có nghĩa “đợi vô hạn”

`spring.lifecycle.timeout-per-shutdown-phase=20s` là **timeout cho từng phase shutdown lifecycle**, không phải SLA bảo đảm mọi việc xong trong đúng 20 giây. Bên ngoài còn Docker timeout, Kubernetes termination grace, load balancer drain, network propagation và thời gian của các callbacks. Nếu phase quá hạn, framework có thể tiếp tục shutdown, yêu cầu còn hoạt động sẽ bị cắt; nếu orchestrator hết giờ, nó có thể buộc dừng toàn bộ process.

## 4. Dừng từ IDE: Stop không phải một giao thức

Khi chạy Java qua IntelliJ IDEA, Eclipse, VS Code, NetBeans hoặc một IDE khác, nút **Stop/Terminate** thường điều khiển một process hoặc process tree do IDE quản lý. Nhưng cách nó dừng Java khác nhau theo:

- OS: Linux/macOS hay Windows;
- IDE version và Run/Debug configuration;
- Chạy trực tiếp `java -jar`, qua Gradle `bootRun`, Maven `spring-boot:run` hay debugger;
- Java process nằm trong console/process group nào;
- IDE cho graceful stop lần đầu và force kill ở lần nhấn tiếp theo hay không;
- Tool có chạy Java trong container, WSL, remote dev hoặc SSH không.

**Không khẳng định “Stop IDE luôn gửi SIGTERM”.** Tài liệu Spring Boot 3.3 cảnh báo graceful shutdown trong IDE có thể không hoạt động nếu IDE không gửi SIGTERM thích hợp.

### 4.1. IDE Stop, Debug Disconnect và Force Terminate

- **Stop/Terminate**: yêu cầu dừng process theo cơ chế IDE. Có thể graceful hoặc abrupt; phải xem tài liệu và thử.
- **Disconnect debugger**: chỉ ngắt kênh debug trong một số trường hợp, Java process có thể tiếp tục chạy.
- **Force stop/Kill**: thường buộc process ngừng ngay, không bảo đảm hooks.
- **Stop Gradle task**: nếu IDE quản lý Gradle daemon/launcher, nó không nhất thiết gửi đúng signal tới JVM app. Kiểm tra process tree.

Các nút tương tự nhau về giao diện không nhất thiết có cùng semantics. Đừng lấy việc app biến mất khỏi Run panel làm chứng cứ đã đóng cleanly.

### 4.2. Cách xác minh IDE thật

Trong một ứng dụng thử nghiệm local:

1. Bật log `ContextClosedEvent` và `@PreDestroy`.
2. Bật web graceful shutdown ở phiên bản Boot đang dùng.
3. Mở một request đủ dài.
4. Nhấn Stop **một lần**, quan sát request có 200 hay bị cắt, lifecycle logs có đủ không, process có còn sống trong khoảng grace không.
5. Thử lại với Debug Stop và Force Terminate, ghi nhận khác biệt.
6. Xác minh phiên bản IDE, JVM, OS, launcher thay vì dựa vào tên nút.

**Tránh chạy thử trên production**: IDE shortcuts và remote debug commands không phải công cụ kiểm thử khả năng drain an toàn cho dịch vụ thật.

## 5. Các tín hiệu Unix thường gặp: TERM, INT, KILL

### 5.1. SIGTERM — yêu cầu kết thúc có cơ hội dọn dẹp

`SIGTERM` thường là signal mặc định khi gọi `kill PID` hoặc `kill -TERM PID` trên Linux/macOS. Nó thể hiện yêu cầu tiến trình dừng. Với JVM HotSpot thông thường và Spring Boot đã đăng ký shutdown hook, việc nhận TERM có thể dẫn đến đóng ApplicationContext và thực thi các callbacks.

```bash
kill -TERM 12345
```

`12345` là **PID giả dùng để minh họa**; phải lấy đúng PID của JVM đang thử và chỉ dừng process của chính bạn. Dùng `ps` hoặc `jps -l` để tìm. Không dùng PID minh họa trên máy thật.

TERM có thể bị chương trình/lớp wrapper xử lý khác, bị chặn/không chuyển tiếp hoặc không tới JVM. Nếu JVM là child của shell trong container, signal có thể tới shell chứ không tới Java. Trong mọi trường hợp, câu hỏi thực là **JVM có bắt đầu shutdown sequence và Spring context được close không?**

### 5.2. SIGINT — thường do Ctrl+C ở terminal

Trên Unix terminal, nhấn `Ctrl+C` thường gửi `SIGINT` đến foreground process group. Với ứng dụng Java thông thường, nó có thể khởi chạy shutdown sequence và chạy Spring hooks tương tự TERM.

Nhưng `Ctrl+C` không phải tên signal có cùng nghĩa ở mọi OS/tool: trên Windows console, đây là console control event; trong IDE hoặc embedded terminal có thể có lớp process khác nhận. Nếu Java chạy qua Gradle/Maven, signal có thể tới launcher và app JVM theo cách phụ thuộc tiến trình.

### 5.3. SIGKILL — cưỡng chế, không thể bắt hoặc trì hoãn

`SIGKILL`, thường là `kill -9 PID`, do kernel áp đặt. Ứng dụng không thể dùng Java handler hoặc `finally` để xử lý trước. **Không** chạy JVM shutdown hooks, `ContextClosedEvent`, `@PreDestroy` hoặc graceful HTTP drain theo con đường bình thường.

```bash
kill -KILL 12345
```

Đây là lệnh **chỉ dùng trong lab local** với PID đã được xác nhận, không sử dụng để dừng dịch vụ dữ liệu thật khi còn giải pháp nhẹ hơn.

### 5.4. Exit code không chứng minh cleanup thành công

Trên Unix/shell/container có quy ước exit code như `128 + signal number`: 130 thường gắn SIGINT, 143 gắn SIGTERM, 137 gắn SIGKILL. Nhưng đây là quy ước phụ thuộc wrapper/shell/runtime/orchestrator, **không phải bằng chứng độc lập** đã chạy hook hay đã hoàn tất request.

Ví dụ, một container có thể nhận TERM, chạy cleanup một phần, sau đó bị KILL khi quá hạn và báo exit 137. Ngược lại, một Java process có thể tự `System.exit(143)` mà không từng nhận SIGTERM. Cần xem timeline, event, logs, metrics và request outcomes.

## 6. Java System.exit, Runtime.halt và đóng Spring context

### 6.1. System.exit khởi động JVM shutdown sequence

```java
System.exit(0);
```

Trong Java, `System.exit` gọi `Runtime.exit` để bắt đầu shutdown sequence. Các shutdown hooks được chạy; Spring context nếu được đăng ký hook có cơ hội đóng. Đây **không phải** API nên gọi trực tiếp từ một controller production để tắt server: một request có thể làm JVM chết, đang xử lý transactions còn dang dở và không có drain/auth/audit phù hợp.

Một background batch/CLI Spring app đôi khi dùng:

```java
ConfigurableApplicationContext ctx =
        SpringApplication.run(BatchApplication.class, args);

int exitCode = SpringApplication.exit(ctx);
System.exit(exitCode);
```

Đây là **snippet cho batch application**, cần các imports và class `BatchApplication` trong project. `SpringApplication.exit(ctx)` đóng Spring context, tạo exit code từ `ExitCodeGenerator`/exception logic phù hợp; `System.exit` sau đó cho OS quan sát process exit. Không sao chép nguyên đoạn này vào REST controller hay app đang có requests.

### 6.2. ApplicationContext.close không luôn kết thúc JVM

```java
context.close();
```

Dòng này đóng Spring context và các managed beans, bất kể JVM đã nhận TERM hay chưa. Nhưng process có thể còn sống nếu còn non-daemon threads khác. Đó là lý do phân biệt **Spring context lifecycle** với **OS process lifecycle**.

### 6.3. Runtime.halt bỏ qua shutdown hooks

```java
Runtime.getRuntime().halt(1);
```

Đây là **phản ví dụ về cưỡng chế kết thúc**, không dùng trong demo server hay production shutdown bình thường. Nó ngừng JVM ngay, không chờ hook/cleanup. Chỉ cần hiểu cơ chế để giải thích vì sao `finally`, `@PreDestroy` không phải hợp đồng bền vững khi process chết đột ngột.

### 6.4. Một Java 17 standalone probe để tách JVM khỏi Spring

Tạo `ShutdownSignalProbe.java`:

```java
import java.util.concurrent.CountDownLatch;

public final class ShutdownSignalProbe {

    public static void main(String[] args)
            throws InterruptedException {

        Runtime.getRuntime().addShutdownHook(
            new Thread(
                () -> System.out.println("JVM_SHUTDOWN_HOOK"),
                "demo-shutdown-hook"
            )
        );

        System.out.println(
            "READY pid=" + ProcessHandle.current().pid()
        );

        new CountDownLatch(1).await();
    }
}
```

Chạy bằng Java 17+:

```bash
javac ShutdownSignalProbe.java
java ShutdownSignalProbe
```

Output trước khi dừng có dạng:

```text
READY pid=12345
```

PID thay đổi. Trên Linux/macOS, gửi SIGTERM đúng PID trong terminal khác: thông thường sẽ có `JVM_SHUTDOWN_HOOK` trước khi JVM thoát. Nếu buộc `SIGKILL`, dòng hook sẽ không xuất hiện theo cơ chế shutdown bình thường. Trên Windows, Ctrl+C/process termination phụ thuộc console và hệ điều hành.

**Demo này không chứng minh HTTP graceful shutdown**, vì nó không tạo Spring context hay web server. Nó chỉ tách riêng lớp JVM hook để bạn nhận diện cơ chế.

## 7. Spring Boot lifecycle: ContextClosedEvent, SmartLifecycle và @PreDestroy

Khi `ApplicationContext` được đóng bình thường:

1. Spring phát `ContextClosedEvent` để các listeners có cơ hội biết context chuẩn bị ngừng.
2. Lifecycle processor stop các `Lifecycle`/`SmartLifecycle` beans theo phases và dependencies.
3. Spring destroy singleton beans, gọi `@PreDestroy` và các callbacks phù hợp như `DisposableBean.destroy()` hoặc custom destroy methods.
4. Các component bên ngoài JVM có thể đã bắt đầu rút traffic trước đó hoặc chưa hoàn tất; đừng suy ra kết quả network chỉ từ event order.

### 7.1. @EventListener(ContextClosedEvent.class)

```java
@Component
public class ShutdownTrace {
    private static final Logger log =
            LoggerFactory.getLogger(ShutdownTrace.class);

    @EventListener(ContextClosedEvent.class)
    public void onClosing() {
        log.info("LIFECYCLE_CONTEXT_CLOSING");
    }

    @PreDestroy
    public void beforeDestroy() {
        log.info("LIFECYCLE_BEAN_DESTROY");
    }
}
```

Đây là **class snippet** có thiếu imports, còn chương trình chạy đầy đủ nằm ở mục 9. Trong đó dùng các import:

```java
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
```

Log ContextClosedEvent cho biết một Spring context đang đóng; `@PreDestroy` cho biết bean được container destroy. Chúng **không** được gọi bởi SIGKILL, và **không** tự xác nhận số lượng jobs/messages đã hoàn thành.

### 7.2. SmartLifecycle và thứ tự phase

`SmartLifecycle` phù hợp với worker/scheduler/consumer có vòng đời rõ:

```java
@Component
public class ExampleWorkerLifecycle implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean();

    @Override
    public void start() {
        running.set(true);
    }

    @Override
    public void stop(Runnable callback) {
        try {
            running.set(false);
            // Dừng nhận work mới và hoàn tất work đang chạy
            // theo chính sách của ứng dụng (snippet minh họa).
        } finally {
            callback.run();
        }
    }

    @Override
    public void stop() {
        running.set(false);
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
```

Đây là **snippet** với imports `AtomicBoolean`, `SmartLifecycle`, `@Component` và cần được đặt vào project; phần “dừng work” chưa được cài vì phụ thuộc message broker. Không xem nó là full queue draining implementation.

Các quy tắc cốt lõi:

- Startup theo phase từ **thấp → cao**, shutdown theo **cao → thấp**.
- Quan hệ `depends-on` ảnh hưởng thứ tự, có ưu tiên so với phase khi phù hợp.
- `stop(Runnable callback)` phải gọi `callback.run()` khi hoàn tất stop. Không gọi có thể khiến lifecycle processor chờ đến timeout.
- Mỗi phase có timeout; “timeout-per-shutdown-phase” không có nghĩa toàn bộ application shutdown có một đồng hồ duy nhất.
- Trong tình huống khởi tạo lỗi hoặc shutdown bất thường, không dựa tuyệt đối vào giả định stop luôn chạy trước destroy. Callback cleanup cần idempotent.

Spring Boot graceful web-server shutdown tham gia lifecycle stop phases; mục tiêu của nó là ngừng nhận request mới và cho request đang chạy thời gian hoàn tất. Ứng dụng có thể còn schedulers, Kafka consumers, job threads, WebSocket sessions, connection pools cần vòng đời riêng.

### 7.3. Shutdown hooks không nên block vô hạn

Tránh sleep 10 phút hoặc chờ một queue vô hạn trong `@PreDestroy`. Orchestrator có thể KILL process trước khi xong. Cleanup nên nhanh, bounded và có timeout rõ: stop accepting work, flush cần thiết, release resources và ghi metric.

Nếu cần bảo đảm không mất event/payment, phải dùng persistent transactions, durable queues và idempotency thay vì hy vọng JVM luôn có thời gian đóng đúng.

## 8. Spring Boot 3.3: graceful HTTP shutdown

Theo [Spring Boot 3.3 Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html), Spring Boot hỗ trợ graceful shutdown với các embedded servers **Tomcat, Jetty, Reactor Netty và Undertow** ở Servlet/reactive stacks. Khi application context đóng, web server bắt đầu một phase shutdown, trong đó **ngừng nhận request mới** và cho **các request đang chạy** cơ hội kết thúc trong thời gian đã cấu hình.

### 8.1. Hai properties quan trọng

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

- `server.shutdown=graceful`: bật chế độ drain request ở web server cho Boot 3.3.
- `spring.lifecycle.timeout-per-shutdown-phase=20s`: timeout cho từng phase lifecycle stopping. Tối ưu theo request durations và budget hạ tầng.

Với `server.shutdown=immediate`, context vẫn có thể đóng và `@PreDestroy` vẫn chạy, **nhưng web server không đợi request đang xử lý theo cơ chế graceful**. Điều này phân biệt “Spring cleanup” với “HTTP draining”.

### 8.2. Khác biệt mặc định theo phiên bản

| Phiên bản | Trạng thái mặc định đáng chú ý | Khuyến nghị bài học |
| --- | --- | --- |
| Spring Boot 3.3.x | Graceful web shutdown không mặc định bật; cấu hình `server.shutdown=graceful` để kích hoạt | Đặt property tường minh |
| Spring Boot 3.4+ | Graceful web-server shutdown được bật mặc định theo release notes 3.4 | Vẫn kiểm tra/tune timeouts |
| Spring Boot mới hơn | Tài liệu mới có thể thay default/details theo server | Đọc tài liệu đúng version được deploy |

Không suy từ tài liệu Boot mới vào binary cũ. Đừng thay tên property ngẫu nhiên theo một snippet tìm được mà không kiểm tra dependency tree.

### 8.3. Server có cách từ chối request mới khác nhau

Theo Spring Boot 3.3 docs:

- Tomcat, Jetty và Reactor Netty ngừng nhận request mới ở network layer.
- Undertow có thể vẫn nhận connection nhưng trả HTTP **503 Service Unavailable** khi đang graceful shutdown.
- Persistent keep-alive connections có thể làm biểu hiện khác so với mở TCP mới.
- Một request mới trong lúc drain có thể thấy connection refused/reset, 503 hoặc response khác theo server/proxy; **không có một HTTP status duy nhất cho mọi stack**.

Không viết test bắt buộc “mọi request mới nhận 503” trên Tomcat vì có thể nó **không chấp nhận kết nối**.

### 8.4. Request đã bắt đầu không phải lúc nào cũng xong

Nếu request mất 30 giây nhưng timeout web-server phase là 20 giây, việc graceful shutdown có thể kết thúc khi hết hạn; request bị cắt, client thấy lỗi và app vẫn shutdown. Nếu Docker chỉ cho 10 giây rồi SIGKILL, Boot 20 giây cũng không có cơ hội đủ 20 giây.

Cần chọn timeout theo traffic thực tế, có giới hạn max request duration, cancellation và retry. Graceful không giải quyết tất cả slow clients, streaming vô hạn, task thất lạc hoặc network faults.

### 8.5. SSE, WebSocket và long polling cần chính sách riêng

Một SSE stream hoặc WebSocket có thể sống hàng giờ. Không thể đợi các kết nối này hoàn tất tự nhiên trong mọi rolling deployment:

- Đánh dấu instance draining và ngừng tạo subscriptions mới.
- Chủ động gửi tín hiệu ứng dụng để client reconnect/resubscribe khi thích hợp.
- Đóng các stream/socket đang hoạt động trong budget, dọn subscriber maps/brokers.
- Client reconnect với backoff/jitter và tiếp tục từ cursor nếu cần không mất dữ liệu.
- Không dựa vào một HTTP 200 hoặc `@PreDestroy` để kết luận toàn bộ event stream đã hoàn tất.
- Streaming requests có thể giữ graceful shutdown chờ tới timeout; đo connection lifetime và cancellation.

## 9. Dự án Spring Boot Java 17+ chạy được để quan sát shutdown

Demo gồm:

- `GET /quick`: response ngay.
- `GET /work?seconds=8`: một blocking HTTP request có thời gian xử lý có thể điều chỉnh.
- `ShutdownTrace`: log context close và bean destroy.
- `ExampleLifecycle`: in lifecycle start/stop và gọi callback đúng hợp đồng.
- Actuator health/readiness để quan sát trong môi trường local.
- Properties bật graceful shutdown 20 giây.

Ví dụ **không có authentication, DB, Kafka hoặc queue thật**. Dùng để thử local hoặc container riêng, không deploy làm service public. `Thread.sleep` trong handler chỉ là công cụ tạo request dài có thể nhìn thấy; production không nên chặn servlet threads vô ích như vậy.

### 9.1. Tạo project

Dùng [Spring Initializr](https://start.spring.io/) hoặc tạo Gradle project cho **Java 17 + Spring Boot 3.3.13**. Trong `settings.gradle`:

```groovy
rootProject.name = 'shutdown-lab'
```

`build.gradle` đầy đủ ở mức cấu hình cốt lõi:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Initializr cung cấp `gradlew`, `gradlew.bat` và thư mục `gradle/wrapper`. Nếu tự viết project rỗng mà chưa có Gradle Wrapper, dùng một Gradle phiên bản tương thích để sinh wrapper, hoặc tạo project từ Initializr rồi thay các file. Không giả định `gradlew` luôn tồn tại trong một thư mục chỉ có `build.gradle`.

Cấu trúc:

```text
settings.gradle
build.gradle
gradlew
gradlew.bat
gradle/wrapper/...
src/
  main/
    java/demo/
      ShutdownLabApplication.java
      SlowController.java
      ShutdownTrace.java
      ExampleLifecycle.java
    resources/
      application.properties
  test/
    java/demo/
      SlowControllerTest.java
```

### 9.2. ShutdownLabApplication.java

File `src/main/java/demo/ShutdownLabApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShutdownLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShutdownLabApplication.class, args);
    }
}
```

Theo Boot 3.3, `SpringApplication` mặc định đăng ký shutdown hook cho context. Không cần tự gọi `Runtime.getRuntime().addShutdownHook(...)` chỉ để Spring chạy `@PreDestroy`; việc tự thêm nhiều hooks còn làm order và trách nhiệm phức tạp hơn.

### 9.3. SlowController.java: request hữu hạn đủ lâu để thử

File `src/main/java/demo/SlowController.java`:

```java
package demo;

import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SlowController {

    private static final Logger log =
            LoggerFactory.getLogger(SlowController.class);

    @GetMapping("/quick")
    public String quick() {
        return "quick-ok\n";
    }

    @GetMapping("/work")
    public ResponseEntity<String> work(
            @RequestParam(defaultValue = "8") int seconds) {

        if (seconds < 0 || seconds > 25) {
            return ResponseEntity.badRequest()
                    .body("seconds must be between 0 and 25\n");
        }

        log.info("WORK_START seconds={}", seconds);

        try {
            TimeUnit.SECONDS.sleep(seconds);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            log.warn("WORK_INTERRUPTED");
            return ResponseEntity.status(
                    HttpStatus.SERVICE_UNAVAILABLE)
                    .body("interrupted\n");
        }

        log.info("WORK_DONE seconds={}", seconds);
        return ResponseEntity.ok("work-done\n");
    }
}
```

**Giải thích:**

- `/quick` trả một chuỗi cố định cho probe thủ công.
- `/work?seconds=8` chặn một servlet worker thread trong 8 giây để thấy một request đang chạy lúc JVM nhận TERM.
- Giới hạn 0..25 giây tránh biến endpoint test thành sleep vô hạn; đừng mở nó ra public Internet.
- `WORK_START` và `WORK_DONE` giúp phân biệt xử lý nghiệp vụ trên server với kết quả HTTP ở client.
- Nếu thread bị interrupt, code trả 503; điều này không bảo đảm response luôn được gửi thành công khi process đang shutdown.
- **WORK_DONE không chứng minh client đã nhận đủ bytes**: server còn có bước serialization/write và network.
- Không có database; nếu muốn chứng minh commit/rollback thì phải thêm transaction test riêng.

### 9.4. ShutdownTrace.java: hai loại callback

File `src/main/java/demo/ShutdownTrace.java`:

```java
package demo;

import jakarta.annotation.PreDestroy;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownTrace {

    private static final Logger log =
            LoggerFactory.getLogger(ShutdownTrace.class);

    @EventListener(ContextClosedEvent.class)
    public void onClosing() {
        log.info("LIFECYCLE_CONTEXT_CLOSING");
    }

    @PreDestroy
    public void beforeDestroy() {
        log.info("LIFECYCLE_BEAN_DESTROY");
    }
}
```

`ContextClosedEvent` chỉ được phát khi context được đóng theo con đường framework; `@PreDestroy` chỉ chạy nếu Spring đi đến giai đoạn destroy bean. Khi process bị SIGKILL, không trông chờ hai dòng trên.

### 9.5. ExampleLifecycle.java: SmartLifecycle demo

File `src/main/java/demo/ExampleLifecycle.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class ExampleLifecycle implements SmartLifecycle {

    private static final Logger log =
            LoggerFactory.getLogger(ExampleLifecycle.class);

    private final AtomicBoolean running = new AtomicBoolean();

    @Override
    public void start() {
        running.set(true);
        log.info("LIFECYCLE_WORKER_STARTED");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            running.set(false);
            log.info("LIFECYCLE_WORKER_STOPPED");
        } finally {
            callback.run();
        }
    }

    @Override
    public void stop() {
        running.set(false);
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
```

Bean này không chạy background task thật, chỉ minh họa startup/stop callback. Với một queue consumer thật, `stop(Runnable)` cần ngừng nhận messages, chờ các công việc đang chạy có giới hạn, commit/ACK theo protocol rồi mới gọi callback. Nếu callback không được gọi, lifecycle processor có thể đợi tới timeout của phase.

`getPhase()=0` chỉ là chọn cho demo; web server graceful shutdown có phase do Boot quản lý. Không hardcode thứ tự các dòng của nhiều components dựa vào chính một con số phase nếu có dependencies hoặc framework updates.

### 9.6. application.properties

File `src/main/resources/application.properties`:

```properties
server.port=8080

# Explicit cho Spring Boot 3.3.x
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s

# Dùng health probes trong local lab.
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never

logging.level.demo=INFO
```

**Không cần bật Actuator shutdown endpoint**. Nó bị disabled theo mặc định vì có thể dừng ứng dụng qua HTTP. Đừng thêm `management.endpoint.shutdown.enabled=true` hay expose `shutdown` chỉ để thay thế TERM; việc expose endpoint vận hành phá hủy cần identity/network/audit cực kỳ nghiêm ngặt.

### 9.7. Build và chạy

Trong root project có Gradle Wrapper:

```bash
./gradlew clean bootJar
```

Windows:

```powershell
.\gradlew.bat clean bootJar
```

JAR dự kiến có tên `build/libs/shutdown-lab-0.0.1-SNAPSHOT.jar` khi `settings.gradle` và `version` đúng như đã viết. Trên Linux/macOS, chạy trực tiếp process JVM:

```bash
java -jar build/libs/shutdown-lab-0.0.1-SNAPSHOT.jar
```

Đợi ứng dụng startup. Output logs có dòng gần giống `LIFECYCLE_WORKER_STARTED` và server listening port 8080; các dòng Spring Boot khác phụ thuộc môi trường. Dùng chính `java -jar` để biết signal đến **JVM app**, không thử `kill` PID của Gradle daemon rồi kết luận về Spring.

### 9.8. HTTP thử nhanh

Terminal thứ hai:

```bash
curl -i http://localhost:8080/quick
curl -i 'http://localhost:8080/work?seconds=1'
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
```

`GET /quick` trả body:

```text
quick-ok
```

`GET /work?seconds=1` trả:

```text
work-done
```

Health probes thường trả `UP` khi app sẵn sàng, nhưng trạng thái/HTTP code có thể khác khi app bắt đầu dừng, không sẵn sàng hoặc có lỗi. Nếu probes không tồn tại, kiểm tra Actuator dependency/property, không mặc định route được bật trong mọi môi trường.

## 10. Thí nghiệm A: gửi SIGTERM khi HTTP request đang chạy

### 10.1. Chuẩn bị hai terminal

**Terminal A:** chạy JVM như mục 9.7, để ứng dụng tiếp tục xử lý.

**Terminal B:** mở request dài 8 giây:

```bash
curl -v --no-buffer 'http://localhost:8080/work?seconds=8'
```

Server log khi controller bắt đầu:

```text
WORK_START seconds=8
```

**Terminal C:** tìm đúng Java PID:

```bash
jps -l
```

`jps` là công cụ JDK, không luôn có trong image chỉ chứa JRE. Có thể dùng `ps -ef` và xác minh command line chứa `shutdown-lab-0.0.1-SNAPSHOT.jar`. Khi đã xác nhận, gửi:

```bash
kill -TERM 12345
```

**`12345` là PID minh họa; phải thay bằng PID đúng đã xác minh**. Thao tác này dành cho ứng dụng local do bạn sở hữu, không chạy trên production.

### 10.2. Kết quả kỳ vọng khi request còn trong grace period

Với Boot 3.3 `server.shutdown=graceful`, request còn khoảng 6–8 giây và timeout phase 20 giây, ứng dụng **có cơ hội** để `/work` trả 200/body `work-done` trước khi context đóng xong.

Server có thể ghi:

```text
WORK_START seconds=8
LIFECYCLE_CONTEXT_CLOSING
... graceful shutdown commencing ...
WORK_DONE seconds=8
... graceful shutdown complete ...
LIFECYCLE_WORKER_STOPPED
LIFECYCLE_BEAN_DESTROY
```

Đây là **minh họa các event**, không cam kết thứ tự log/số dòng/wording. `SmartLifecycle` phases, server logs và threads có thể làm thứ tự khác. Những điểm cần kiểm chứng là:

1. Request bắt đầu trước khi có TERM.
2. JVM có nhận TERM và Spring context bắt đầu close?
3. Controller đã chạy đến `WORK_DONE`?
4. Client có thật sự nhận HTTP 200 và body hoàn chỉnh?
5. Process có thoát trong timeout của orchestrator/OS?
6. Có request mới được chấp nhận sau khi drain bắt đầu không?

**Quan trọng:** Nếu server trả reset cho một request mới trong lúc drain, đó không nhất thiết là bug. Tomcat thường ngừng nhận mới ở network layer, không cam kết 503.

### 10.3. Khi request dài hơn grace period

Giữ `spring.lifecycle.timeout-per-shutdown-phase=20s`, rồi gọi:

```bash
curl -v --no-buffer 'http://localhost:8080/work?seconds=25'
```

Gửi SIGTERM ngay sau khi request bắt đầu. Request có thể bị cắt khi hết thời gian phase; client có thể thấy connection reset/empty reply hoặc lỗi khác, không bảo đảm luôn có một response 503. Một số code có thể tiếp tục chạy trong JVM đến khi process bị dừng; **đừng xem WORK_DONE là bằng chứng khách hàng nhận được body**.

Do bài mẫu có giới hạn tối đa 25 giây, test này giúp quan sát timeout mà không phải tạo request vô tận. Khi test, tắt các health dashboards đang gọi liên tục nếu chúng làm nhiễu logs.

### 10.4. Kiểm chứng lỗi bị tạo bởi launcher

Nếu chạy bằng:

```bash
./gradlew bootRun
```

thì PID của `gradlew`/Gradle daemon không nhất thiết là PID của Java web app, nhất là khi build tool forked JVM. Gửi TERM đến Gradle wrapper có thể khiến app dừng theo cách khác. Để thí nghiệm tín hiệu chính xác, dùng `java -jar` trực tiếp hoặc kiểm tra PID tree và kết quả thật.

## 11. Thí nghiệm B: SIGKILL và ranh giới không thể cleanup

Khởi chạy app lại trên một terminal mới. Mở request dài:

```bash
curl -v --no-buffer 'http://localhost:8080/work?seconds=8'
```

Ở terminal khác xác minh PID, rồi gửi **chỉ trên process local demo**:

```bash
kill -KILL 12345
```

Khi kernel buộc dừng JVM:

- Client thường bị mất kết nối trước khi nhận body hoàn chỉnh.
- Không trông chờ `LIFECYCLE_CONTEXT_CLOSING`, `LIFECYCLE_WORKER_STOPPED` hoặc `LIFECYCLE_BEAN_DESTROY`.
- Không có HTTP graceful drain.
- App không thể gọi `finally`, `@PreDestroy` hay Java shutdown hooks để hoàn tất công việc.
- Log buffers có thể chưa flush; không thấy log nào đó **không tự chứng minh** code đã/không đã chạy trước thời điểm chết.

Điều quan trọng là **thiết kế dữ liệu chịu được crash**, vì production có thể bị OOMKill, node failure, forced rollout, disk/CPU faults hoặc mất điện. Graceful shutdown giảm xác suất gián đoạn trong các tình huống bình thường, không thay thế transaction, retry và idempotency.

### 11.1. Đừng làm thí nghiệm SIGKILL trên dữ liệu thật

Hạn chế test trong project demo có in-memory state và không có external dependencies. Nếu muốn test database/queue, dùng sandbox, fixture và tài khoản có phạm vi riêng; buộc dừng một tiến trình xử lý thanh toán hay consumer production có thể gây duplication hoặc mất tín hiệu ACK.

## 12. Thí nghiệm C: IDE Stop và Windows

### 12.1. IDE trên Linux/macOS

Mở project trong IDE, chạy `ShutdownLabApplication`, khởi động `/work?seconds=8` từ terminal. Nhấn Stop một lần rồi so sánh:

| Quan sát | Có thể suy ra | Chưa thể kết luận |
| --- | --- | --- |
| Có `ContextClosedEvent` | Spring context bắt đầu đóng | Mọi HTTP response đã xong |
| Có `@PreDestroy` | Bean được destroy theo Spring | Không có request nào bị gián đoạn |
| Request trả 200 hoàn chỉnh | Một request hoàn tất | Mọi request/job đều hoàn tất |
| App biến mất khỏi IDE | IDE không còn quản lý process | JVM đã cleanup đủ |
| Không có shutdown logs | Có thể termination abrupt hoặc log chưa flush | Không xác định signal nếu không xem PID/log OS |

Một số IDE Stop buttons gửi TERM khi đủ điều kiện, một số dùng force termination hoặc kill process tree. Khi chạy debug, Stop/Disconnect cũng khác nhau. Hãy ghi rõ môi trường thử: IDE version, OS, JDK, launcher, Spring Boot version và kết quả network.

### 12.2. Windows console không phải Unix signals y hệt

Trong Windows, `Ctrl+C` là console control event; cơ chế Java shutdown hooks phụ thuộc JVM và cách console/tool gửi/nhận event. Lệnh PowerShell `Stop-Process` hoặc `taskkill /F` có thể kết thúc tiến trình mà **không** cho Spring chạy graceful close. Không coi một lệnh Windows có tên “stop” là tương đương `kill -TERM`.

Để thử, chạy trong PowerShell:

```powershell
java -jar build/libs/shutdown-lab-0.0.1-SNAPSHOT.jar
```

Trong một PowerShell khác:

```powershell
curl.exe -i "http://localhost:8080/work?seconds=8"
```

Nhấn Ctrl+C trong console **chứa Java**, quan sát log và HTTP response. Sau đó chạy lại và thử IDE Stop hoặc `Stop-Process` trên **đúng demo PID**. Nếu bị buộc dừng và không có `@PreDestroy`, đó là hành vi cần ghi nhận của cách terminate đó.

### 12.3. Không kết luận từ process exit code

Windows Process Exit Code và Unix exit status không có mapping thống nhất. Mã 137/143 thường là quy ước container/shell Linux; đừng áp trực tiếp vào Windows. Quan trọng hơn là timeline, application events và tính đúng đắn dữ liệu sau restart.

## 13. Docker stop: TERM → chờ → KILL

Docker cung cấp hai hành vi dễ bị nhầm:

- `docker stop`: gửi **stop signal** tới main process trong container (mặc định thường SIGTERM), chờ khoảng thời gian cấu hình rồi gửi SIGKILL nếu chưa dừng.
- `docker kill`: mặc định gửi **SIGKILL** ngay, trừ khi chỉ định signal khác.

Timeout Docker không phải timeout Spring Boot. Với Linux containers, Docker daemon mặc định thường dùng **10 giây** khi chưa có stop-timeout khác; Windows containers có mặc định khác. Nếu `spring.lifecycle.timeout-per-shutdown-phase=20s` nhưng Docker dừng cưỡng chế sau 10 giây, request 15 giây không thể trông đợi hoàn tất.

### 13.1. Dockerfile exec-form ENTRYPOINT

Sau khi build JAR ở mục 9, tạo `Dockerfile`:

```dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app
COPY build/libs/shutdown-lab-0.0.1-SNAPSHOT.jar /app/app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

**Exec form** giúp JVM trở thành main process trong container và nhận stop signal trực tiếp từ runtime. Tránh shell-form:

```dockerfile
# Không khuyến nghị khi cần signal forwarding rõ ràng:
ENTRYPOINT java -jar /app/app.jar
```

Với shell-form, shell có thể là PID 1 và không forward TERM đến child Java như bạn kỳ vọng. Nếu bắt buộc dùng shell script làm entrypoint, script nên `exec java -jar ...` để thay shell bằng JVM, đồng thời xử lý PID 1/process reaping theo môi trường.

### 13.2. Chạy và dừng container lab

```bash
docker build -t shutdown-lab:dev .
docker run -d --name shutdown-lab -p 8080:8080 shutdown-lab:dev
docker logs -f shutdown-lab
```

Trong terminal khác mở request `/work?seconds=8`, rồi:

```bash
docker stop --time 25 shutdown-lab
```

Với timeout 25 giây, Spring Boot 20 giây phase thường có đủ thời gian hơn so với mặc định 10 giây, nhưng nếu nhiều lifecycle phases hoặc pre/post work kéo dài, vẫn phải đo thật. `docker logs` cho thấy lifecycle events; `curl` cho thấy client đã nhận body hay chưa.

Khi dừng xong:

```bash
docker rm shutdown-lab
```

Nếu muốn thấy sự khác biệt cưỡng chế, tạo lại container demo, phát request mới rồi dùng `docker kill shutdown-lab`. **Chỉ thử với container tự tạo**, không kill shared infrastructure hay database thực.

### 13.3. docker compose cũng có thời gian dừng riêng

Compose hỗ trợ cấu hình `stop_grace_period` để điều chỉnh thời gian chờ trước khi cưỡng chế dừng, và `stop_signal` để chọn signal. Ví dụ snippet:

```yaml
services:
  api:
    image: shutdown-lab:dev
    ports:
      - "8080:8080"
    stop_signal: SIGTERM
    stop_grace_period: 35s
```

Đây là **compose snippet**; không cần nếu chạy Docker CLI theo mục trước. Chỉ tăng timeout mà vẫn dùng shell-form entrypoint không forward TERM thì JVM có thể vẫn không nhận signal. Cần cả signal path và grace budget.

### 13.4. PID 1 và Java app

Trong container, PID 1 có hành vi signal/reaping cần lưu ý. Dùng Java trực tiếp bằng exec-form ENTRYPOINT giúp đường signal rõ ràng hơn; nếu có process supervisor/tini, phải xác minh nó forward signal và reap children. Không dùng `sh -c "java -jar ..."` với hy vọng Docker tự tìm child Java để gửi TERM.

## 14. Kubernetes: preStop, TERM và terminationGracePeriodSeconds

Khi một Pod bị delete/replace trong rollout, kubelet thường cố gắng dừng container có trật tự:

```text
Pod được đánh dấu terminating
                |
                v
EndpointSlice / Service routing cập nhật bất đồng bộ
                |
                v
Kubelet chạy preStop hook (nếu có)
                |
                v
Container runtime gửi TERM đến container process
                |
                v
JVM / Spring Boot graceful shutdown
                |
                v
Process exit trước deadline?
          /                   \
        Có                    Không
        |                       |
        v                       v
  Pod kết thúc           Runtime gửi KILL
```

**Kubernetes grace timer tính cả thời gian preStop**, không phải được cộng thêm hoàn toàn vào sau preStop. Default `terminationGracePeriodSeconds` là **30 giây** nếu không tùy chỉnh. Nếu `preStop` ngủ 10 giây mà deadline là 30 giây, JVM còn khoảng 20 giây hoặc ít hơn để dọn.

Kubelet đôi khi đề nghị extension rất ngắn cho preStop còn chạy khi grace hết, nhưng không nên dựa vào đó làm shutdown budget.

### 14.1. Ví dụ Deployment snippet

Đây là **manifest minh họa các trường liên quan shutdown**, cần bổ sung registry, image pull secrets và policies khi dùng thực tế:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shutdown-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: shutdown-lab
  template:
    metadata:
      labels:
        app: shutdown-lab
    spec:
      terminationGracePeriodSeconds: 40
      containers:
        - name: api
          image: registry.example.test/shutdown-lab:dev
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
```

Ví dụ cho 40 giây termination grace, trong đó `preStop` tiêu tốn ~5 giây. App có `spring.lifecycle.timeout-per-shutdown-phase=20s`, còn lại để JVM stop và overhead. **40s chỉ là số demo**, không phải giá trị khuyến nghị chung cho mọi service; phải đo p99 durations, queue drains, multiple phases, load balancer propagation và orchestrator behavior.

`preStop sleep` là mẹo tạo một khoảng thời gian rút traffic cho môi trường cụ thể, **không đảm bảo** mọi ingress/load balancer đều ngừng gửi request đúng 5 giây. Không sleep cứng trong mọi dự án nếu không cần; dùng readiness/connection draining và rollout tests thực tế.

### 14.2. Readiness và liveness khác shutdown signal

- **Readiness** trả lời “Pod có sẵn sàng nhận traffic không?”. Khi Pod terminating, Kubernetes đánh dấu endpoints liên quan không còn ready cho traffic bình thường, nhưng propagation qua EndpointSlices/kube-proxy/ingress là bất đồng bộ.
- **Liveness** trả lời “Container có cần restart vì bị kẹt không?”. Không nên cố tình cho liveness fail chỉ để làm graceful rollout, vì có thể khiến restart vòng lặp.
- **preStop** là lifecycle hook của container, thực hiện trước khi TERM theo termination flow; không phải Java `@PreDestroy`.
- **terminationGracePeriodSeconds** là giới hạn từ góc nhìn kubelet, không phải `spring.lifecycle.timeout-per-shutdown-phase`.
- **SIGKILL** khi quá hạn không cho Java callbacks chạy nốt.

Nếu app có readiness endpoint `/actuator/health/readiness`, cần đảm bảo nó được expose và reachable trong mạng nội bộ; nếu Spring Security chặn probe 401, Pod có thể never ready. Một management port riêng có thể không phản ánh main app port, cần kiểm tra lựa chọn probe paths phù hợp.

### 14.3. Nguyên tắc rút traffic trước khi dừng

Một quy trình tốt:

1. Pod/instance nhận tín hiệu drain và ngừng trở thành endpoint nhận traffic mới.
2. Ingress/load balancer/clients có đủ thời gian nhận thay đổi routing.
3. Web server ngừng nhận request mới và đợi request đang chạy trong giới hạn.
4. Background consumers dừng nhận việc mới, hoàn tất/ghi ACK có kiểm soát.
5. Trạng thái nghiệp vụ quan trọng được commit/idempotent.
6. Connections đóng và beans destroy.
7. Process exit trước deadline.

Không giả định sequence network và application là một transaction atomic. Có độ trễ cập nhật endpoint, long-lived keep-alive connection, retries, client timeout và quá trình load balancing.

### 14.4. Crash và OOMKilled vẫn cần phục hồi

Pod có thể bị OOMKilled, node đột ngột mất điện, container runtime kill hoặc Pod force-delete. Trong các trường hợp đó, không dựa vào `@PreDestroy`. Dùng message redelivery, database transactions, distributed leases/TTL, idempotent side effects và recovery logic khi startup.

## 15. Graceful shutdown với background tasks và queue consumers

### 15.1. Scheduled tasks

Một scheduled job đang chạy có thể bị cắt khi context đóng hoặc executor ngừng nhận tasks mới. Trong Spring Framework 6.1, task executors/schedulers có chính sách shutdown tham gia lifecycle; chi tiết `waitForTasksToCompleteOnShutdown`, `awaitTerminationSeconds` và `acceptTasksAfterContextClose` ảnh hưởng hành vi.

Không mặc định `@Scheduled` job dài sẽ được đợi hoàn tất chỉ nhờ `server.shutdown=graceful` vì property đó chủ yếu điều khiển **web server requests**. Với worker dài, dùng `SmartLifecycle`/executor stop policy và giới hạn thời gian rõ ràng.

### 15.2. Message broker consumer

Consumer RabbitMQ/Kafka/Redis Streams cần:

1. Stop poll/receive new messages.
2. Chờ xử lý các message đã nhận có giới hạn.
3. Commit offsets/ACK **sau** khi business side effects an toàn.
4. Nếu không xong trước deadline, cho phép broker redeliver hoặc resume.
5. Consumer phải idempotent để tránh xử lý lặp.

Nếu ACK trước commit DB, crash có thể mất công việc. Nếu DB commit xong nhưng ACK chưa ghi, broker có thể phát lại, nên idempotency key hoặc unique constraints cần ngăn duplicate effects. **Shutdown hook không thể tạo exactly-once business effect**.

### 15.3. Không phụ thuộc cleanup để đảm bảo consistency

Một payment request đang trong quá trình commit khi SIGKILL đến có thể đã hoàn tất ở database nhưng HTTP client chưa nhận response. Client retry có thể tạo giao dịch trùng nếu service không có idempotency key. Hãy thiết kế kết quả giao dịch và retry semantics từ đầu; graceful shutdown chỉ giảm khả năng sự cố, không loại bỏ hoàn toàn.

### 15.4. Connection pools và đóng tài nguyên

`@PreDestroy` nên release database connections, HTTP clients, schedulers và resources đã được Spring quản lý. Không gọi remote service chậm trong callback nếu có thể tránh; shutdown deadline hữu hạn và dependencies cũng có thể đang được dừng. Tốt nhất từng resource có close method idempotent với timeout, còn dữ liệu quan trọng được commit khi xử lý nghiệp vụ chứ không dồn tới bước shutdown.

## 16. Timeout budget: tính từ phía ngoài vào

Ví dụ một dịch vụ có:

| Hạn mức | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| p99 HTTP business duration | 8 giây | Nhiều requests hoàn tất trước 8s |
| Spring lifecycle timeout/phase | 20 giây | Thời gian tối đa chờ mỗi phase |
| preStop hook | 5 giây | Tiêu tốn một phần Pod grace |
| Kubernetes Pod grace | 40 giây | Deadline tổng cho Pod termination |
| Docker stop timeout nếu dùng riêng | 25 giây | Deadline riêng cho container Docker |
| LB drain propagation | Vài giây đo thực tế | Không luôn đồng bộ tức thì |

Một cấu hình lành mạnh cần để hạ tầng cho app đủ thời gian xử lý trong điều kiện dự kiến, nhưng không đợi vô hạn. Không cộng hoặc so sánh các số này máy móc vì **per-phase timeouts và shutdown callbacks có thể cộng dồn**, request durations thay đổi, health check và network latency bất định.

### 16.1. Chiến lược chọn thời gian

- Đo p95/p99/max (có giới hạn) của requests và background jobs.
- Đặt request timeouts/cancellation và giới hạn long-running workloads.
- Quy định grace budget cho những gì thực sự cần hoàn tất.
- Đặt Kubernetes `terminationGracePeriodSeconds` bao phủ preStop + Spring phases + safety margin.
- Với Docker/Compose, đảm bảo stop timeout không ngắn hơn app cần.
- Giữ shutdown callbacks bounded; đánh giá worst-case dependency failures.
- Thử trên môi trường thật với concurrent load và rolling updates.
- Với streams vô hạn, thiết kế client reconnect/resume thay vì kéo dài grace vô hạn.

### 16.2. Vì sao tăng grace lên 10 phút có thể phản tác dụng?

Một request hoặc worker deadlock có thể khiến rollout chậm, giữ connections/resources cũ, tăng số pods đồng thời và làm deployment không kịp deadline. Grace dài không làm code an toàn nếu không có cancellation, bounded queues và idempotency. Tìm nguyên nhân hang thay vì mặc định tăng timeout.

## 17. Kiểm thử tự động: phần nào phù hợp unit/integration tests?

### 17.1. Test endpoint, không giả lập SIGKILL bằng @SpringBootTest

Dùng Spring Boot Test để xác minh `/quick` và `/work` hoạt động. Tạo `src/test/java/demo/SlowControllerTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SlowControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void quickIsAvailable() throws Exception {
        mvc.perform(get("/quick"))
                .andExpect(status().isOk())
                .andExpect(content().string("quick-ok\n"));
    }

    @Test
    void workCompletesNormally() throws Exception {
        mvc.perform(get("/work").param("seconds", "0"))
                .andExpect(status().isOk())
                .andExpect(content().string("work-done\n"));
    }

    @Test
    void rejectsOverlongRequest() throws Exception {
        mvc.perform(get("/work").param("seconds", "26"))
                .andExpect(status().isBadRequest());
    }
}
```

Chạy:

```bash
./gradlew test
```

Test chỉ kiểm tra HTTP behavior bình thường, **không** chứng minh process sẽ chạy hook khi SIGTERM hay SIGKILL. Muốn test OS shutdown, cần chạy JAR trong process độc lập, mở request thật, gửi signal rồi quan sát network/process/logs. Không thể kết luận “graceful pass” chỉ bằng một unit test của controller.

### 17.2. Integration test cho SIGTERM

Một harness hợp lý:

1. Start JAR như child process; lưu PID chính xác và health-check ready.
2. Mở HTTP request mất 8 giây, xác minh đã bắt đầu.
3. Gửi TERM tới đúng JVM PID.
4. Ghi timestamp gửi signal, HTTP completion, context logs và process exit.
5. Assert request trả body đúng **nếu được đặt trong grace budget**.
6. Assert process thoát trước orchestrator deadline.
7. Khởi chạy app lại, test SIGKILL và xác minh không dựa vào callbacks để giữ dữ liệu.
8. Test nhiều concurrent requests với duration khác nhau, keep-alive, streaming và slow client nếu service hỗ trợ.

Một test harness phải xử lý race: nếu TERM tới **trước** khi request vào handler, kết quả có thể là connection refused và không nói lên graceful draining. Chờ một marker server-side như `WORK_START` hoặc barrier dành riêng cho test trước khi gửi signal.

### 17.3. Các phép thử thực sự cần ở production-like environment

- IDE Stop khi chạy trực tiếp vs Gradle runner.
- SIGTERM/SIGINT/SIGKILL với JVM độc lập.
- Docker stop timeout ngắn vs dài; Dockerfile shell vs exec-form.
- Kubernetes rolling update với preStop, readiness, EndpointSlice và ingress.
- Request nhanh/chậm, HTTP keep-alive, SSE/WebSocket, uploads/long polling.
- DB transaction giữa chừng, Kafka/RabbitMQ consumer ACK/commit, scheduler đang chạy.
- Crash/OOMKill và startup recovery.
- Metrics active requests, connection counts, shutdown duration và forced kills.

## 18. Quan sát shutdown bằng metrics và logs

Các thông tin nên thu thập:

- Thời điểm nhận yêu cầu drain/SIGTERM từ orchestrator nếu nền tảng hỗ trợ.
- Thời điểm `ContextClosedEvent` được phát.
- Thời điểm web server bắt đầu/ngừng graceful phase.
- Active requests đang chạy tại thời điểm dừng và hoàn tất/gián đoạn.
- Thread-pool active jobs, queued tasks, consumer lag/inflight messages.
- Số connections SSE/WebSocket còn mở, reconnect rate.
- Thời gian từng shutdown phase và thời gian process exit.
- Exit code/reason từ container/pod (`OOMKilled`, `Error`, `Completed`...).
- HTTP client errors/connection resets trong rollout.
- Tỷ lệ retry, duplicate operations, timeout và transaction failures sau restart.

**Không** log request body/credentials để “biết có request nào mất”. Sử dụng request ID, trace ID, route template, duration, status và idempotency key đã được quản lý an toàn. Một request có `WORK_DONE` nhưng chưa có client 200 vẫn cần xem network và application semantics.

### 18.1. Exit code và logs thiếu không đủ kết luận

Nếu không thấy `@PreDestroy` trong log, có thể do force kill, IDE dừng khác cách, logger đã tắt, log collector chưa flush hoặc callback không được đăng ký. Ngược lại, có log `@PreDestroy` cũng không đảm bảo request payload, HTTP response hoặc message ACK đã hoàn tất. Kết hợp nhiều tín hiệu.

### 18.2. Không biến shutdown logging thành điểm nghẽn

Khi shutting down, logging appender/network sink có thể cũng đang đóng. Tránh gọi endpoint remote hoặc ghi khối lượng log lớn từ shutdown hook. Logs ngắn, có cấu trúc, không bí mật và best-effort; business durability phải được đảm bảo ở bước xử lý chính.

## 19. Những hiểu lầm thường gặp

| Nhận định sai | Sự thật |
| --- | --- |
| “Nhấn Stop ở mọi IDE đều gửi SIGTERM.” | Tùy IDE, OS, launcher và run/debug mode; phải thử. |
| “Có @PreDestroy nghĩa là mọi HTTP response đã gửi xong.” | Bean destruction khác request completion/network delivery. |
| “SIGTERM và SIGKILL chỉ khác số signal.” | TERM cho JVM cơ hội shutdown; KILL buộc dừng không chạy hook. |
| “Ctrl+C luôn bằng kill -9.” | Ctrl+C Unix thường là SIGINT, không phải SIGKILL. |
| “System.exit bỏ qua JVM hooks.” | System.exit khởi chạy shutdown sequence; Runtime.halt mới bypass. |
| “ApplicationContext.close luôn tắt cả OS process.” | Context có thể đóng nhưng JVM còn non-daemon threads. |
| “Boot 3.3 graceful shutdown mặc định bật.” | Boot 3.3 cần `server.shutdown=graceful`; Boot 3.4 đổi default. |
| “graceful=20s luôn chờ 20s rồi thoát.” | Nó có thể thoát sớm khi xong; timeout áp dụng theo phase. |
| “Tomcat phải trả 503 khi shutdown.” | Có thể ngừng nhận connection ở network layer; không cam kết 503. |
| “docker stop lúc nào cũng cho 20s như Boot.” | Docker stop timeout riêng, thường ngắn hơn nếu không cấu hình. |
| “Docker gửi TERM cho Java bất kể ENTRYPOINT.” | Shell wrapper/PID 1 có thể không forward signal. |
| “Kubernetes preStop 5s được cộng thêm ngoài 30s grace.” | preStop nằm trong grace budget. |
| “Pod readiness false lập tức rút mọi traffic.” | Endpoint/ingress propagation bất đồng bộ. |
| “Thêm 60s grace đảm bảo không mất message.” | Crash/SIGKILL/network vẫn có; cần durable queue và idempotency. |
| “Exit 143 chứng minh mọi @PreDestroy chạy.” | Exit code là dấu hiệu, không là bằng chứng cleanup. |
| “Controller WORK_DONE nghĩa là client nhận 200.” | Network/write có thể thất bại sau khi controller xong. |
| “Khi JVM chết, finally luôn chạy.” | Với SIGKILL/Runtime.halt/fatal termination không đảm bảo. |

## 20. Câu hỏi tự kiểm tra

**1.** Vì sao nhấn Stop IDE không đủ kết luận Spring Boot graceful shutdown?  
**Đáp án:** IDE có thể gửi signal khác hoặc buộc terminate process/launcher; cần xác minh JVM nhận cơ chế gì, callbacks và HTTP request outcome.

**2.** Spring Boot 3.3 đã có shutdown hook, có cần `server.shutdown=graceful` không?  
**Đáp án:** Có nếu muốn web server chờ các request đang chạy theo grace period; hook đóng context và graceful HTTP là hai tầng khác nhau.

**3.** Spring Boot 3.4 khác Boot 3.3 ở điểm nào?  
**Đáp án:** Boot 3.4 đổi graceful web-server shutdown thành mặc định; Boot 3.3 cần cấu hình tường minh.

**4.** SIGTERM tới đúng JVM thì `@PreDestroy` chắc chắn chạy?  
**Đáp án:** Có cơ hội trong shutdown bình thường, nhưng không tuyệt đối nếu signal bị chặn/không được xử lý, JVM crash hoặc bị SIGKILL trước khi callback tới lượt.

**5.** `kill -9` có cho Java shutdown hook vài giây để chạy không?  
**Đáp án:** Không. SIGKILL buộc kernel kết thúc, JVM không chạy shutdown sequence.

**6.** `System.exit(0)` và `Runtime.halt(0)` giống nhau?  
**Đáp án:** Không. System.exit kích hoạt shutdown hooks; halt kết thúc ngay không chạy hooks.

**7.** Tomcat ngừng nhận request mới khi graceful shutdown. Curl phải nhận HTTP 503?  
**Đáp án:** Không. Nó có thể không mở được kết nối; Undertow có biểu hiện 503 trong tài liệu Boot 3.3.

**8.** Docker mặc định chờ 10s, Spring grace 20s. Request 15s chắc hoàn tất?  
**Đáp án:** Không. Docker có thể gửi KILL sau 10s; phải điều chỉnh Docker stop timeout và kiểm thử.

**9.** Dockerfile `ENTRYPOINT java -jar ...` có thể gặp vấn đề gì?  
**Đáp án:** Shell-form có thể làm shell là PID 1 và không forward TERM; dùng exec form hoặc `exec` trong script.

**10.** Pod có `terminationGracePeriodSeconds=30` và `preStop sleep 10`. JVM còn mặc định 30s?  
**Đáp án:** Không. preStop tiêu thụ grace budget; JVM thường còn ~20s hoặc ít hơn.

**11.** Một Kafka consumer đã commit DB nhưng chưa ACK khi bị SIGKILL. Điều gì có thể xảy ra?  
**Đáp án:** Broker redeliver; cần idempotency hoặc dedup để không tạo business side effect lặp.

**12.** Một request ghi `WORK_DONE` rồi client gặp connection reset; dữ liệu đã chắc an toàn chưa?  
**Đáp án:** Không thể suy từ log. Cần xem transaction commit, idempotency và response delivery separately.

**13.** Vì sao không chờ WebSocket tồn tại mãi trong graceful shutdown?  
**Đáp án:** Kết nối có thể sống hàng giờ; nên đóng có kiểm soát và client reconnect/resubscribe với cursor.

**14.** Test `MockMvc` pass có chứng minh SIGTERM drain đúng không?  
**Đáp án:** Không. Cần live process integration test gửi OS signal và quan sát request qua TCP.

## 21. Checklist trước khi rollout

- [ ] Xác định đúng Spring Boot version và default `server.shutdown`; Boot 3.3 có `server.shutdown=graceful` rõ ràng.
- [ ] Đặt `spring.lifecycle.timeout-per-shutdown-phase` theo active requests/jobs và đo thực tế.
- [ ] IDE Stop được test, không suy đoán signal từ tên nút.
- [ ] Phân biệt graceful context close, HTTP drain và process termination.
- [ ] Có logs/context events/SmartLifecycle/@PreDestroy để quan sát, không dùng chúng làm bằng chứng duy nhất.
- [ ] Callbacks bounded, idempotent và không block vô hạn; `SmartLifecycle.stop(Runnable)` gọi callback.
- [ ] Các HTTP requests hữu hạn có timeout/cancellation phù hợp.
- [ ] SSE/WebSocket/streaming có kế hoạch close/reconnect/resume.
- [ ] Dockerfile dùng exec-form ENTRYPOINT; PID 1 nhận stop signal đúng.
- [ ] Docker/Compose stop timeout đủ budget cho shutdown phases.
- [ ] Kubernetes readiness, EndpointSlice, ingress drain và preStop đã được kiểm tra.
- [ ] `terminationGracePeriodSeconds` bao phủ preStop + Spring phases + margin thực tế.
- [ ] Queue consumers dừng nhận công việc mới và commit/ACK hợp lý; xử lý retry/dedup.
- [ ] DB transactions/idempotency không dựa vào @PreDestroy để đảm bảo consistency.
- [ ] Có integration tests SIGTERM và forced termination trên môi trường giống production.
- [ ] Không dùng exit code hay một dòng log để suy đoán tất cả request hoàn thành.
- [ ] Có metrics shutdown duration, client errors, active requests, consumer lag và forced kills.
- [ ] Actuator shutdown endpoint không mở công khai; quyền điều khiển dừng app được giới hạn.
- [ ] Có playbook phục hồi khi JVM/node chết bất ngờ, restart và retry phải an toàn.

## Tài liệu tham khảo chính thức

1. [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
2. [Spring Boot 3.4 — Release Notes, Graceful Shutdown Default](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes)
3. [Spring Boot 3.3 — SpringApplication.setRegisterShutdownHook Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
4. [Spring Framework 6.1 — SmartLifecycle Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html)
5. [Spring Framework — Bean Lifecycle and Destruction Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
6. [Java 17 — Runtime Shutdown Hooks and halt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html)
7. [Docker — docker container stop](https://docs.docker.com/reference/cli/docker/container/stop/)
8. [Docker — docker container kill](https://docs.docker.com/reference/cli/docker/container/kill/)
9. [Docker — docker container run, stop-signal and stop-timeout](https://docs.docker.com/reference/cli/docker/container/run/)
10. [Docker Compose — Stop Grace Period](https://docs.docker.com/compose/compose-file/05-services/#stop_grace_period)
11. [Kubernetes — Pod Lifecycle: Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#termination-of-pods)
12. [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)
13. [Kubernetes — Deployment Rolling Updates](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
14. [Spring Boot 3.3 — Actuator Health Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

**Kết luận:** **IDE Stop** là thao tác giao diện, semantics phụ thuộc tool/OS; **SIGTERM/SIGINT** thường cho JVM cơ hội chạy shutdown hooks và Spring callbacks; **SIGKILL/Runtime.halt/force terminate** không cho cơ hội đó. **Graceful HTTP shutdown** là lớp riêng giúp request đang chạy hoàn tất trong deadline, không được đồng nhất với `@PreDestroy`. Muốn dừng an toàn trong production, phải kết hợp **signal forwarding, phiên bản Boot đúng, budget thời gian, rút traffic, lifecycle của background work và thiết kế chịu crash/idempotency**.
