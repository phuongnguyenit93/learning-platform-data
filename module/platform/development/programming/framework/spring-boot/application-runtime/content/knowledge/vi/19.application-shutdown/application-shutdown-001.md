# Các đường dừng ứng dụng Spring Boot: close, JVM shutdown hook, tín hiệu hệ điều hành và lỗi

## 1. Bốn khái niệm cần phân biệt

Khi nói Spring Boot “dừng”, ta có thể đang nói đến các việc khác nhau:

- **Đóng ApplicationContext**: Spring ngừng các lifecycle bean và gọi destroy callbacks của những bean được container quản lý.
- **JVM shutdown**: Java Runtime chạy những shutdown hooks đã đăng ký rồi kết thúc máy ảo.
- **Tín hiệu từ hệ điều hành**: OS, terminal hoặc container yêu cầu JVM kết thúc, có thể kích hoạt shutdown hooks.
- **Dừng bất thường**: process crash, SIGKILL, Runtime.halt hoặc mất điện; không thể dựa vào callbacks để đảm bảo cleanup.

Câu quan trọng nhất: **ApplicationContext.close() không phải System.exit()**. Cái đầu đóng Spring container; cái sau yêu cầu cả JVM chấm dứt. Ngược lại, **System.exit() không phải SIGKILL**, bởi System.exit vẫn kích hoạt shutdown sequence và shutdown hooks.

Một ứng dụng web có thể tiếp tục sống sau khi main() trở về vì embedded server còn non-daemon threads. Một batch application có thể chủ động close context nhưng chưa chắc làm JVM thoát nếu còn thread khác ngoài container.

## 2. Bảng các đường dừng

| Đường | Bên khởi phát | JVM shutdown ngay? | Cleanup Spring |
| --- | --- | --- | --- |
| context.close() | Code hoặc test | Không | Đóng context trực tiếp |
| SpringApplication.exit(context) | Code ứng dụng | Không | Đóng context nếu có thể, trả exit code |
| System.exit(code) | Code | Có | Boot JVM hook đóng context nếu còn đăng ký |
| JVM tự hết non-daemon threads | JVM | Có | Chạy shutdown hooks |
| SIGTERM | OS/Docker/Kubernetes | Thông thường có | JVM hook có cơ hội đóng context |
| SIGINT/Ctrl+C | Terminal/OS | Thông thường có | Phụ thuộc môi trường và signal forwarding |
| SIGKILL/kill -9 | OS | Cưỡng bức | Không bảo đảm callback |
| Runtime.halt(code) | Code Java | Cưỡng bức, bỏ qua hooks | Không bảo đảm callback |
| Startup exception | SpringApplication.run | Không đồng nghĩa JVM shutdown | Boot xử lý startup failure và cố cleanup |
| Runtime exception sau Ready | Request/worker | Không mặc nhiên | Context có thể tiếp tục chạy |

Không suy luận từ bảng rằng signal và lifecycle luôn hoạt động như nhau trên Linux, Windows, IDE, shell wrapper và container. Phải kiểm tra môi trường thật.

## 3. Đường đóng trực tiếp bằng ApplicationContext.close()

ConfigurableApplicationContext cung cấp API close():

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);
context.close();
~~~

Đây là đoạn minh họa, cần lớp MyApplication thực. Trình tự normal close đơn giản hóa:

~~~text
ApplicationContext.close()
   ContextClosedEvent
   LifecycleProcessor.onClose()
     SmartLifecycle stop
     Thu tu stop phase cao truoc phase thap
   Destroy managed singleton beans
     @PreDestroy
     DisposableBean.destroy()
     Bean destroyMethod
   ApplicationContext closed
close() returns
~~~

**ContextClosedEvent** được phát khi context bắt đầu đường đóng bình thường; nó **không có nghĩa mọi resource đã dừng xong**. Spring sau đó điều phối lifecycle stop và bean destruction.

Các lưu ý:

1. **close() không tự gọi System.exit**. JVM còn phụ thuộc các non-daemon threads, các context khác và host runtime.
2. Nếu embedded web server do Spring sở hữu, close sẽ dừng server; có drain in-flight hay không phụ thuộc cấu hình graceful shutdown.
3. Resource ngoài Spring-managed beans phải được owner của nó đóng.
4. Email đã gửi, HTTP call bên ngoài, message đã publish hoặc dữ liệu đã commit không tự bị hoàn tác khi context close.
5. Bean cleanup nên chịu được lệnh dừng lặp và trạng thái resource đã đóng hoặc chưa khởi tạo hoàn toàn.

Trong CLI/batch, dùng try-with-resources:

~~~java
try (ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args)) {
    executeJob(context);
}
~~~

Đây là minh họa với executeJob do ứng dụng định nghĩa. Nếu run trả về context thành công, Java tự close khi rời khối try. Nếu **SpringApplication.run ném exception trước khi trả context**, khối try chưa sở hữu resource và Spring Boot phải xử lý failure cleanup của context đang tạo.

## 4. SpringApplication.exit không giống System.exit

API Spring Boot:

~~~java
int exitCode = SpringApplication.exit(context);
~~~

SpringApplication.exit lấy mã thoát từ các **ExitCodeGenerator** và đóng context nếu có thể. Nó trả **int**, nhưng **không bắt buộc kết thúc JVM**.

Ví dụ chủ động dừng một ứng dụng CLI với mã khác 0:

~~~java
int exitCode = SpringApplication.exit(context, () -> 42);
System.exit(exitCode);
~~~

Lambda ở đây là ExitCodeGenerator, được truyền trực tiếp. Theo quy ước, 0 là thành công, mã khác 0 báo lỗi.

Sự khác nhau:

- **SpringApplication.exit**: xử lý phần Spring và trả exit code.
- **System.exit**: bắt đầu JVM shutdown sequence, chạy những shutdown hooks còn đăng ký và kết thúc JVM.
- **System.exit(0)** không tự tính exit code từ các bean ExitCodeGenerator; muốn có mã logic từ Spring thì lấy kết quả SpringApplication.exit.
- **ExitCodeExceptionMapper** và exception triển khai ExitCodeGenerator có thể tham gia đường xử lý lỗi startup; đây không phải là một lời gọi shutdown do code chủ động sau khi app ready.

Đối với web service, thường **không nên gọi System.exit từ một controller** chỉ vì một request thất bại. Nó tác động toàn bộ JVM và mọi request còn lại. Với CLI/batch, exit code là một hợp đồng hữu ích để scheduler, CI và shell biết kết quả.

## 5. JVM shutdown hook mặc định của Spring Boot

Theo Spring Boot 3.3, SpringApplication mặc định đăng ký một JVM shutdown hook để đóng ApplicationContext khi JVM dừng có trật tự:

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);
application.setRegisterShutdownHook(true);
application.run(args);
~~~

Đây là ví dụ minh họa; giá trị mặc định của setRegisterShutdownHook là **true**. Nếu cấu hình false, code sở hữu phải đảm bảo đóng context bằng đường thích hợp.

**Đừng nhầm ba cơ chế:**

| Cơ chế | Thuộc về | Khi nào xảy ra |
| --- | --- | --- |
| JVM shutdown hook | Java Runtime | Khi JVM bắt đầu shutdown |
| ContextClosedEvent | Spring ApplicationContext | Khi context đang được đóng |
| @PreDestroy/DisposableBean | Spring BeanFactory | Khi managed bean được destroy |

Một đường đi bình thường có thể là:

~~~text
OS SIGTERM
JVM shutdown sequence
Spring Boot shutdown hook
ApplicationContext.close()
ContextClosedEvent
SmartLifecycle stop
@PreDestroy va destroy callbacks
JVM exits
~~~

Nếu code gọi context.close() trực tiếp, ContextClosedEvent có thể xảy ra **mà JVM shutdown hook chưa được kích hoạt**.

### Không phụ thuộc thứ tự giữa các JVM hooks

Theo Java Runtime API, JVM bắt đầu các shutdown hooks theo **thứ tự không xác định**; chúng có thể chạy đồng thời. Do đó:

- Custom hook A không được bảo đảm chạy trước Boot hook B.
- Không gọi Spring Repository trong hook riêng với giả định context vẫn hoạt động.
- Hook phải thread-safe, nhanh, có timeout phù hợp.
- Không gọi **System.exit() từ trong shutdown hook**, vì việc gọi exit trong quá trình shutdown có thể chặn và làm shutdown không hoàn thành.
- Khi cần thứ tự dừng resource, dùng **SmartLifecycle.getPhase()** và bean dependencies bên trong Spring context.

## 6. Chương trình Java độc lập kiểm chứng shutdown hook

Tạo file **HookBasics.java**:

~~~java
public class HookBasics {
    public static void main(String[] args) {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("JVM_HOOK")));

        System.out.println("MAIN_BEGIN");

        if (args.length > 0 && args[0].equals("exit")) {
            System.exit(0);
        }

        System.out.println("MAIN_END");
    }
}
~~~

Chạy Java 17+:

~~~bash
javac HookBasics.java
java HookBasics
~~~

Các thông điệp được in:

~~~text
MAIN_BEGIN
MAIN_END
JVM_HOOK
~~~

Khi main kết thúc và không còn non-daemon threads, JVM tự shutdown, vì vậy hook được gọi.

Chạy nhánh System.exit:

~~~bash
java HookBasics exit
~~~

Thông điệp:

~~~text
MAIN_BEGIN
JVM_HOOK
~~~

MAIN_END không xuất hiện vì System.exit bắt đầu shutdown trước khi tới dòng đó. Chỉ có một hook trong ví dụ nên không có vấn đề thứ tự giữa nhiều hook. Chương trình này không có Spring context và không nói về @PreDestroy.

## 7. Tín hiệu từ hệ điều hành

### SIGTERM

Trên Linux/Unix với JVM thông thường, SIGTERM thường làm Java Runtime bắt đầu shutdown sequence. Nếu Boot hook vẫn đăng ký và JVM có đủ thời gian, context được đóng:

~~~bash
kill -TERM JAVA_PID
~~~

Chỉ dùng PID thật của **tiến trình Java**. Nếu chạy qua Gradle, IDE hoặc shell wrapper, PID bạn thấy ở terminal có thể thuộc wrapper chứ không phải JVM. Không gửi signal tùy ý tới process production.

### SIGINT/Ctrl+C

Ctrl+C thường phát SIGINT trong terminal. Trên Unix với JVM bình thường, SIGINT có thể kích hoạt JVM shutdown. Windows, IDE và container có cơ chế riêng; một nút Stop trong IDE có thể kết thúc process ngay thay vì mô phỏng SIGTERM.

### SIGKILL

~~~bash
kill -KILL JAVA_PID
~~~

SIGKILL là kết thúc cưỡng bức; JVM không có cơ hội hoàn tất hooks theo đường bình thường. **Không bảo đảm ContextClosedEvent, stop, @PreDestroy hoặc finally được thực thi**.

### Runtime.halt

~~~java
Runtime.getRuntime().halt(1);
~~~

Đây là ví dụ API nguy hiểm, không chạy trong bài thực hành. Runtime.halt kết thúc JVM ngay và **không bắt đầu shutdown sequence**. Nó khác System.exit.

Host crash, OOM kill, mất điện, lỗi native và node bị thu hồi cũng có thể bỏ qua cleanup. Vì vậy resource quan trọng cần transaction, idempotency, checkpoint và khôi phục khi khởi động lại, không dựa vào shutdown hook làm lớp bảo vệ duy nhất.

## 8. Graceful shutdown của server trong Spring Boot 3.3

**Phân biệt phiên bản:** trong **Spring Boot 3.3**, graceful shutdown được hỗ trợ nhưng cần bật rõ ràng:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Tài liệu Spring Boot 3.4+ mô tả mặc định khác, vì vậy không sử dụng mặc định của phiên bản mới để khẳng định với Boot 3.3.

Spring Boot 3.3 hỗ trợ graceful shutdown với các embedded web servers **Tomcat, Jetty, Reactor Netty, Undertow**. Khi context đóng, server ngừng nhận request mới theo cơ chế của nó và cho các request đang xử lý thêm thời gian hoàn tất.

- Tomcat/Jetty/Reactor Netty có thể ngừng nhận request mới ở network layer.
- Undertow có thể tiếp nhận kết nối mới nhưng phản hồi HTTP 503.
- Persistent connections, proxy, HTTP protocol và timing ảnh hưởng kết quả.
- **spring.lifecycle.timeout-per-shutdown-phase** là ngân sách chờ **mỗi shutdown phase**, không phải giới hạn tổng JVM luôn bằng đúng 20 giây.

**Readiness không đồng nghĩa graceful shutdown.** Readiness probe giúp orchestrator ngừng định tuyến traffic mới. Web graceful shutdown giúp embedded server drain in-flight requests. HTTP readiness **không tự pause Kafka/RabbitMQ consumer hay scheduler**; các thành phần đó cần vòng đời stop/pause/ack riêng.

## 9. SmartLifecycle và destroy callback

Spring-managed resources có thể dùng:

- **@PreDestroy** từ jakarta.annotation trong Spring Boot 3.
- **DisposableBean.destroy()**.
- **@Bean(destroyMethod="close")** hoặc destroy method được suy ra phù hợp.
- **SmartLifecycle.stop(Runnable)** cho component chạy liên tục, có thể cần chờ dừng bất đồng bộ.
- **ContextClosedEvent** cho log/metric nhẹ khi đóng bắt đầu.

Trong normal close, Spring thực hiện lifecycle stop rồi destroy managed singleton beans. Với SmartLifecycle, shutdown theo phase **cao trước, thấp sau**, giúp consumer dừng lấy việc mới trước resource nền. Nếu stop bất đồng bộ, callback phải được gọi sau khi hoàn tất thật:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    } finally {
        callback.run();
    }
}
~~~

Không gọi callback ngay sau khi chỉ submit lệnh stop async. Nếu callback không xảy ra, lifecycle processor có thể chờ tới timeout của phase.

Nếu bean có cả ba cơ chế destroy trên các method khác nhau, thứ tự thông thường là **@PreDestroy, DisposableBean.destroy(), custom destroyMethod**. Nhưng không nên đóng cùng connection ở ba nơi khác nhau nếu chưa có lý do rõ; tránh double close, race và resource ownership mơ hồ.

**Lỗi trong factory method:** nếu tạo client/socket rồi ném exception trước khi Spring nhận được bean, @PreDestroy không đảm bảo được gọi. Resource đã mở dở cần được đóng ngay trong catch/finally của nơi tạo, đồng thời giữ exception gốc để chẩn đoán.

## 10. Ví dụ Spring Boot 3.3/Java 17: bốn đường dừng

Project minh họa các mode:

- **close**: main trực tiếp đóng context.
- **exit**: SpringApplication.exit rồi System.exit.
- **signal**: embedded Tomcat tiếp tục chạy cho tới khi OS gửi SIGTERM.
- **fail**: runner ném exception trong startup, ApplicationFailedEvent quan sát lỗi.

### 10.1. Cấu trúc project

~~~text
shutdown-paths-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        example/
          ShutdownPathsDemo.java
      resources/
        application.properties
~~~

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'shutdown-paths-demo'
~~~

Tệp **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

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
}
~~~

Cần JDK 17+, Gradle tương thích và dependency có sẵn qua repository/cache.

Tệp **src/main/resources/application.properties**:

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
spring.main.banner-mode=off
spring.main.log-startup-info=false
~~~

### 10.2. Source Java

Tệp **src/main/java/example/ShutdownPathsDemo.java**:

~~~java
package example;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ShutdownPathsDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ShutdownPathsDemo.class);

        app.addListeners(
                (ApplicationListener<ApplicationFailedEvent>) event ->
                        System.out.println("APPLICATION_FAILED"));

        ConfigurableApplicationContext context = app.run(args);
        String mode = context.getEnvironment()
                .getProperty("demo.mode", "signal");

        switch (mode) {
            case "close" -> {
                System.out.println("CALL_CLOSE");
                context.close();
                System.out.println("CLOSE_RETURNED");
            }
            case "exit" -> {
                System.out.println("CALL_EXIT");
                int code = SpringApplication.exit(context, () -> 0);
                System.out.println("EXIT_CODE=" + code);
                System.exit(code);
            }
            case "signal" -> System.out.println("WAIT_SIGNAL");
            default -> {
                context.close();
                throw new IllegalArgumentException(
                        "Unknown mode: " + mode);
            }
        }
    }

    @Bean
    ApplicationRunner startupRunner() {
        return args -> {
            System.out.println("RUNNER");
            if (args.containsOption("demo.fail")) {
                throw new IllegalStateException("Demo startup failure");
            }
        };
    }
}

@Component
class ManagedWorker implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        System.out.println("WORKER_START");
    }

    @Override
    public void stop() {
        if (running) {
            running = false;
            System.out.println("WORKER_STOP");
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }

    @PreDestroy
    public void destroy() {
        System.out.println("WORKER_PRE_DESTROY");
    }
}

@Component
class CloseEvents {

    @EventListener
    public void ready(ApplicationReadyEvent event) {
        System.out.println("APPLICATION_READY");
    }

    @EventListener
    public void closed(ContextClosedEvent event) {
        System.out.println("CONTEXT_CLOSED");
    }
}

@RestController
class SlowController {
    @GetMapping("/slow")
    public String slow() throws InterruptedException {
        Thread.sleep(4_000);
        return "DONE";
    }
}
~~~

**Kiểm tra:** chỉ ShutdownPathsDemo là class public; các class còn lại package-private cùng package. SmartLifecycle được implement đầy đủ; @PreDestroy dùng Jakarta. ApplicationFailedEvent được đăng ký trước run để nhận lỗi startup dù context chưa hoàn chỉnh. SlowController chỉ mô phỏng một in-flight HTTP request, không phải pattern cho production.

## 11. Chạy và đối chiếu kết quả

### 11.1. Đường close()

~~~bash
./gradlew bootRun --args="--demo.mode=close"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--demo.mode=close"
~~~

Các dòng do code demo in ra theo thứ tự:

~~~text
WORKER_START
RUNNER
APPLICATION_READY
CALL_CLOSE
CONTEXT_CLOSED
WORKER_STOP
WORKER_PRE_DESTROY
CLOSE_RETURNED
~~~

Spring Boot/Tomcat/Gradle còn có log riêng. Với normal close, ContextClosedEvent đến trước lifecycle stop, sau đó bean destroy và close trả về.

### 11.2. Đường SpringApplication.exit + System.exit

~~~bash
./gradlew bootRun --args="--demo.mode=exit"
~~~

Dòng do code in:

~~~text
WORKER_START
RUNNER
APPLICATION_READY
CALL_EXIT
CONTEXT_CLOSED
WORKER_STOP
WORKER_PRE_DESTROY
EXIT_CODE=0
~~~

Sau đó System.exit(0) đưa JVM vào shutdown. Context đã đóng nên không mong có callback destroy lặp lần hai. Nếu thay generator bằng 42, OS process có thể trả code 42 và Gradle có thể xem bootRun thất bại.

### 11.3. Đường SIGTERM

Để nhận đúng PID Java, đóng gói và chạy trực tiếp:

~~~bash
./gradlew bootJar
java -jar build/libs/shutdown-paths-demo-1.0.0.jar --demo.mode=signal
~~~

Các dòng trước signal:

~~~text
WORKER_START
RUNNER
APPLICATION_READY
WAIT_SIGNAL
~~~

Từ terminal Linux/macOS khác, xác định PID thật của Java rồi gửi:

~~~bash
kill -TERM JAVA_PID
~~~

Nếu JVM xử lý SIGTERM và hook Spring chạy được, các dòng cleanup thường xuất hiện:

~~~text
CONTEXT_CLOSED
WORKER_STOP
WORKER_PRE_DESTROY
~~~

Không cam kết stdout toàn bộ process chỉ có các dòng trên; log web server, signal forwarding và khả năng flush tùy runtime. Khi test Windows có thể dùng Ctrl+C; không đồng nhất với cách IDE dừng process.

### 11.4. Thử graceful HTTP drain

Trong mode signal, ở terminal A:

~~~bash
curl -i http://localhost:8080/slow
~~~

Khi server đã nhận request và còn đang chờ khoảng bốn giây, gửi SIGTERM từ terminal khác. Với graceful được bật và timeout phase 20 giây, request đã tiếp nhận **có cơ hội hoàn tất**. Request mới có thể bị từ chối. Kết quả phụ thuộc thời điểm signal, networking, keep-alive và client; không hứa mọi lần chạy đều ra 200.

### 11.5. Đường startup failure

~~~bash
./gradlew bootRun --args="--demo.fail"
~~~

Các dòng trước lỗi thường gồm:

~~~text
WORKER_START
RUNNER
APPLICATION_FAILED
~~~

Runner ném IllegalStateException trước khi SpringApplication.run trả về. Không có APPLICATION_READY trong nhánh startup thành công; main cũng không in CALL_CLOSE/CALL_EXIT/WAIT_SIGNAL. Boot sẽ xử lý lỗi và cố cleanup context nếu có. **Thứ tự tất cả callback trong nhánh failure không nên xem là stdout cố định**, nhất là khi context lỗi từ rất sớm.

## 12. Lỗi startup khác lỗi runtime

**Startup failure** có thể xảy ra khi khởi tạo bean, refresh context, bind port, SmartLifecycle.start hoặc runner. Spring Boot có **ApplicationFailedEvent**, FailureAnalyzer và cleanup theo khả năng. Context của ApplicationFailedEvent có thể là null nếu lỗi xảy ra trước khi context được tạo. Không mặc định rằng mọi @PreDestroy được gọi trong một lần refresh thất bại giữa chừng.

**Runtime failure** sau Ready có thể là exception trong HTTP controller, @Async task, scheduled method hoặc message listener. Những lỗi này **thường không tự đóng cả SpringApplication**. Mỗi infrastructure có retry, error handler, circuit breaker và chính sách xử lý riêng. ApplicationFailedEvent không phải một event chung cho mọi lỗi nghiệp vụ sau Ready.

Nếu một runtime error thực sự làm service không thể phục vụ, cần thiết kế chính sách: đổi readiness, dừng nhận việc mới, chờ/drain task, yêu cầu orchestrator restart hoặc thoát JVM với code khác 0. Không chỉ in stack trace rồi kỳ vọng hệ thống tự biết đây là lỗi fatal.

**Resource tạo dở:** nếu constructor/factory method mở socket rồi lỗi trước khi bean hoàn tất, cleanup cần thực hiện ngay trong try/finally/catch tại chỗ. Spring không thể tự biết mọi resource bên ngoài mà code đang giữ. Không dùng @PreDestroy như thay thế transaction và idempotency.

## 13. Kubernetes/Docker và ngân sách dừng

Một đường đi thường gặp:

~~~text
Pod termination requested
preStop hook neu co
SIGTERM den Java process
JVM shutdown hooks
Spring Boot context.close()
Web graceful drain
SmartLifecycle stop
Bean destroy callbacks
Process exits
Neu het grace period: SIGKILL
~~~

Sơ đồ mang tính khái niệm; trình tự cập nhật routing, preStop và signal còn phụ thuộc nền tảng.

**Checklist:**

1. Signal phải đến đúng **Java PID**, đặc biệt nếu entrypoint có shell wrapper. Dùng exec java hoặc init/signal forwarding đúng.
2. **terminationGracePeriodSeconds** phải đủ cho preStop, web drain, worker shutdown và cleanup.
3. **spring.lifecycle.timeout-per-shutdown-phase** là per phase, không phải tổng thời gian OS cho phép.
4. Với Boot 3.3, **server.shutdown=graceful** cần bật.
5. Readiness probe giúp hạn chế traffic mới, nhưng cập nhật routing có độ trễ.
6. Consumer Kafka/RabbitMQ cần ngừng poll, ack/nack/requeue hoặc xử lý in-flight theo semantics riêng.
7. Executor/task nền phải có ownership và cancellation/timeout.
8. SIGKILL khi hết deadline có thể cắt ngang transaction và I/O; cần retry/idempotency/checkpoint.
9. Exit code cuối cùng có thể bị shell wrapper hoặc orchestrator ảnh hưởng, không khẳng định mọi SIGTERM đều là một con số cố định.

## 14. Những lỗi thường gặp

**1.** Gọi context.close() rồi tưởng JVM luôn thoát ngay. **Sai:** JVM có thể còn non-daemon threads.

**2.** Gọi SpringApplication.exit rồi quên dùng exit code khi CLI cần trả trạng thái. **Sai:** method chỉ trả int.

**3.** Tưởng System.exit bỏ qua JVM hooks. **Sai:** Runtime.halt mới không thực hiện shutdown sequence.

**4.** Tưởng SIGKILL chạy @PreDestroy. **Sai:** không có cơ hội đảm bảo cleanup.

**5.** Thêm custom JVM hook và dựa vào thứ tự đăng ký với Boot hook. **Sai:** hooks có thể chạy đồng thời.

**6.** Tưởng ContextClosedEvent nghĩa là tất cả bean đã được destroy. **Sai:** nó được phát trước phần stop/destroy bình thường.

**7.** Không bật graceful web shutdown ở Boot 3.3 nhưng kỳ vọng drain in-flight. **Cần:** server.shutdown=graceful.

**8.** Đặt timeout-per-shutdown-phase=20s rồi kết luận mọi JVM tắt đúng 20 giây. **Sai:** nhiều phase và OS grace còn ảnh hưởng.

**9.** Cho @PreDestroy gọi remote API không timeout. **Hậu quả:** treo shutdown hoặc bị OS kill trước khi xong.

**10.** Tin rằng HTTP graceful tự pause scheduler, Kafka hoặc RabbitMQ. **Sai:** mỗi workstream cần stop policy riêng.

**11.** Cho mọi resource cùng bị close ở JVM hook, listener ContextClosedEvent và @PreDestroy. **Hậu quả:** double-close và race.

**12.** Coi exception của request sau Ready là ApplicationFailedEvent. **Sai:** startup event khác runtime error.

**13.** Bật custom setRegisterShutdownHook(false) nhưng quên close context thủ công. **Hậu quả:** mất cleanup ở JVM shutdown.

**14.** Bắt RuntimeException của runner rồi chỉ log dù startup condition bắt buộc chưa đạt. **Hậu quả:** service có thể ready sai.

**15.** Không xử lý restart/crash idempotently. **Hậu quả:** những side effect chưa hoàn tất có thể lặp hoặc mất khi shutdown cưỡng bức.

## 15. Câu hỏi tự kiểm tra

**Câu 1:** context.close() có mặc định tương đương System.exit(0) không?  
**Đáp án:** Không. Nó chỉ đóng Spring context.

**Câu 2:** SpringApplication.exit(context) trả về gì?  
**Đáp án:** Exit code int; đồng thời đóng context nếu có thể.

**Câu 3:** Boot 3.3 có tự đăng ký JVM shutdown hook không?  
**Đáp án:** Có, setRegisterShutdownHook mặc định true.

**Câu 4:** Hai custom JVM shutdown hooks có chạy theo thứ tự đã đăng ký không?  
**Đáp án:** Không có bảo đảm; chúng có thể đồng thời.

**Câu 5:** SIGTERM và SIGKILL khác nhau thế nào?  
**Đáp án:** SIGTERM thường kích hoạt JVM shutdown hooks; SIGKILL kết thúc cưỡng bức.

**Câu 6:** Muốn drain request trên Spring Boot 3.3 cần gì?  
**Đáp án:** Bật server.shutdown=graceful và chọn shutdown timeout thích hợp.

**Câu 7:** ContextClosedEvent được phát trước hay sau @PreDestroy thông thường?  
**Đáp án:** Trước phần destroy bean trong normal close.

**Câu 8:** stop(Runnable) của SmartLifecycle phải gọi callback lúc nào?  
**Đáp án:** Khi việc dừng thực sự hoàn tất.

**Câu 9:** ApplicationRunner ném exception thì ApplicationReadyEvent có xuất hiện ở đường thành công không?  
**Đáp án:** Không.

**Câu 10:** Một HTTP request ném exception có tự đóng JVM không?  
**Đáp án:** Thông thường không.

**Câu 11:** Shutdown hook có bảo đảm chạy khi host mất điện?  
**Đáp án:** Không.

**Câu 12:** Container có terminationGracePeriodSeconds nhưng vẫn kill -9, nguyên nhân?  
**Đáp án:** Có thể hết deadline hoặc runtime/orchestrator buộc dừng; cleanup chưa hoàn tất.

**Kết luận:** Muốn dừng Spring Boot đúng, phân biệt rõ **đóng context**, **JVM shutdown** và **kết thúc cưỡng bức**. **context.close** đóng tài nguyên managed; **SpringApplication.exit** trả exit code; **System.exit/SIGTERM** thường đưa JVM qua shutdown hooks; **SIGKILL/halt/crash** bỏ qua cleanup đáng tin cậy. Trên **Spring Boot 3.3**, bật **server.shutdown=graceful** và cấu hình thời gian đủ cho SmartLifecycle, HTTP drain và resource cleanup. Luôn thiết kế idempotency/recovery vì không thể giả định shutdown callback sẽ chạy trong mọi tình huống.

### Tài liệu tham khảo

- [Spring Boot 3.3 — Application Exit, Startup Failure và Events](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
- [Spring Framework — Lifecycle/Destruction Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Java SE 21 — Runtime Shutdown Hooks](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html)
