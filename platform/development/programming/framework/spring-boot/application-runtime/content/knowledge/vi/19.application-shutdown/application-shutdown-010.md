# SIGTERM, Ctrl+C và giới hạn cleanup khi tiến trình bị buộc kết thúc trong Spring Boot

Một ứng dụng Spring Boot cần có cơ chế **dừng có kiểm soát**: ngừng nhận việc mới, cho request hoặc tác vụ đang xử lý cơ hội hoàn tất, dừng consumer, trả connection và đóng tài nguyên. Nhưng không phải mọi cách kết thúc tiến trình đều cho phép các bước đó chạy.

**Ba điều phải phân biệt ngay:**

1. **`SIGTERM`** trên hệ Unix/Linux là yêu cầu kết thúc có thể được JVM xử lý để bắt đầu shutdown sequence. Trong cấu hình Java/Spring Boot thông thường, các shutdown hooks có cơ hội chạy, từ đó Spring đóng `ApplicationContext`.
2. **`Ctrl+C`** trong terminal Unix thường tạo `SIGINT` cho foreground process group; JVM HotSpot thông thường cũng có thể bắt đầu shutdown sequence. Trên Windows, console control event và cách IDE/terminal truyền tín hiệu khác Linux; cần kiểm chứng trong môi trường thực tế.
3. **`SIGKILL`** (ví dụ `kill -9`), `Runtime.halt(...)`, một số native crash hoặc sự cố nguồn điện có thể kết thúc tiến trình **ngay lập tức**. Java **không bảo đảm chạy shutdown hook, `@PreDestroy` hoặc `finally`**. Một container bị kill sau khi hết grace period cũng thuộc nhóm này.

Vì vậy **graceful shutdown là best effort có giới hạn thời gian, không phải bảo đảm hoàn tất mọi công việc**. Một thiết kế đúng vừa phải cleanup nhanh và có thể kiểm chứng khi nhận tín hiệu mềm, vừa phải **khôi phục chính xác sau khi bị giết đột ngột**.

Bài học thuộc mục **Dừng ứng dụng** của Spring Boot Application Runtime; ví dụ dùng Java 17+, Spring Boot 3.3.x, Linux/Kubernetes. Các hành vi phụ thuộc OS, JVM, web server và cơ chế chạy ứng dụng được nêu rõ thay vì suy luận một đường dừng duy nhất cho mọi môi trường.

## 1. Bản đồ các cách tiến trình kết thúc

| Tình huống | Điều xảy ra ở mức hệ thống | Khả năng chạy cleanup ứng dụng |
|---|---|---|
| `kill -TERM <PID>` trên Linux | Gửi SIGTERM; JVM thông thường bắt đầu shutdown sequence | Có cơ hội chạy JVM shutdown hooks → đóng Spring context → lifecycle callbacks |
| Nhấn `Ctrl+C` trong terminal Unix | Terminal gửi SIGINT tới foreground process group | JVM thông thường xử lý tín hiệu, nhưng tác động có thể khác khi chạy qua wrapper/IDE |
| `System.exit(code)` | Bắt đầu shutdown sequence của JVM | Chạy hooks theo hợp đồng Java, nếu JVM có thể tiếp tục |
| `SpringApplication.exit(context)` | Đóng context và tính exit code cho ứng dụng | Gọi lifecycle callbacks khi context đóng; **không tự đồng nghĩa kết thúc JVM** |
| `context.close()` | Đóng một Spring ApplicationContext | Gọi lifecycle callbacks của context; JVM có thể vẫn sống |
| `kill -KILL <PID>` hoặc `kill -9 <PID>` | SIGKILL không thể bị ứng dụng bắt hoặc bỏ qua | **Không chạy** Java cleanup như một bước chuẩn bị trước khi bị kill |
| `Runtime.getRuntime().halt(code)` | JVM kết thúc ngay, không thực hiện trình tự shutdown bình thường | Không chờ hooks, có thể làm mất cleanup |
| Container vượt quá termination grace period | Runtime buộc dừng phần tiến trình còn chạy, thường bằng SIGKILL | Cleanup đang chạy bị cắt ngang |
| Crash native nghiêm trọng / mất điện | Tiến trình hoặc máy ngừng ngoài khả năng điều phối bình thường | Không có bảo đảm hooks/finally |

Lệnh `kill` trong bảng chỉ là **minh họa trên Unix/Linux**, không dùng với PID thật của production khi chưa được phép. `<PID>` là placeholder cho PID tiến trình của **bài lab**.

**Lưu ý ngôn từ:** không gọi `SIGTERM` là “dừng chắc chắn thành công”. Đó là **tín hiệu yêu cầu** dừng. JVM còn cần thời gian để chạy hooks và ứng dụng còn phải phối hợp các bean đúng cách. Nếu JVM không phản hồi, hook treo hoặc hạ tầng hết thời gian chờ, hệ thống vẫn có thể buộc kết thúc.

## 2. JVM shutdown hooks hoạt động thế nào?

Java cung cấp:

~~~java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> {
            System.out.println("JVM shutdown hook");
        }, "my-shutdown-hook")
);
~~~

Đoạn này là minh họa Java 17+, không phải chương trình Spring Boot hoàn chỉnh. Khi JVM đi vào **shutdown sequence bình thường**, những shutdown hooks đã đăng ký sẽ được khởi chạy.

Những điểm quan trọng trong hợp đồng `java.lang.Runtime`:

- Hook phải là một `Thread` đã được tạo nhưng **chưa start** khi đăng ký.
- JVM khởi chạy các shutdown hooks theo **thứ tự không được bảo đảm**; các hooks có thể **chạy đồng thời**.
- Khi shutdown đã bắt đầu, không được tiếp tục đăng ký/hủy đăng ký hook; thao tác tương ứng có thể ném `IllegalStateException`.
- Hook cần kết thúc nhanh, an toàn với concurrency và tránh deadlock.
- Hook chạy lúc các dịch vụ khác cũng đang dừng; không nên giả định thread pool, logging, database hoặc những hook khác luôn còn hoạt động.
- Nếu hook chờ vô hạn thì shutdown sequence có thể không kết thúc. OS/container có thể không chờ nó mãi.
- Các hook có thể được chạy bởi `System.exit(...)`, kết thúc tự nhiên của JVM hoặc những tín hiệu OS mà JVM triển khai hỗ trợ.
- `SIGKILL`, `Runtime.halt(...)` và các tình huống abort không cho trình tự này một cơ hội đáng tin cậy.

**Không tự viết nhiều JVM hooks để điều khiển thứ tự đóng từng Spring bean.** Vì không có thứ tự giữa các hooks, việc một hook tự đóng JDBC pool còn hook Spring đang dừng request có thể gây lỗi: request vẫn sử dụng pool đã bị đóng.

Spring Boot vốn đã có cơ chế hook và lifecycle quản lý context. Hãy ưu tiên **`@PreDestroy`, `SmartLifecycle`, `DisposableBean` hoặc destroy method của `@Bean`** thay vì một hook mới dùng để gọi trực tiếp các tài nguyên thuộc Spring.

## 3. SpringApplication làm gì khi JVM được yêu cầu shutdown?

Theo cơ chế Spring Boot 3.3, `SpringApplication` mặc định đăng ký JVM shutdown hook để đóng `ApplicationContext` khi JVM kết thúc. Tùy chỉnh bằng:

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);

application.setRegisterShutdownHook(true);  // Mặc định là true.
application.run(args);
~~~

Đây là mã minh họa: class `MyApplication` cần là source cấu hình hợp lệ và có các import tương ứng. Mặc định `setRegisterShutdownHook(true)` được giữ, vì vậy một ứng dụng Spring Boot thông thường **không cần tự đăng ký hook để gọi `context.close()`**.

Đường đi rút gọn:

~~~text
SIGTERM / SIGINT được JVM xử lý / System.exit(...)
                    |
                    v
            JVM shutdown sequence
                    |
                    +-- Các JVM hooks được khởi chạy
                          (không có thứ tự bảo đảm giữa các hooks)
                    |
                    +-- Spring Boot shutdown hook:
                          đóng ApplicationContext
                                   |
                                   v
                      LifecycleProcessor.onClose()
                          - dừng SmartLifecycle
                          - graceful stop web server nếu bật
                                   |
                                   v
                         Hủy các singleton bean
                          - @PreDestroy
                          - DisposableBean.destroy()
                          - @Bean(destroyMethod=...)
                                   |
                                   v
                        Đóng tài nguyên do bean sở hữu
~~~

Đây là **sơ đồ ý niệm** về luồng đóng Spring context, không phải toàn bộ call stack nội bộ. Thứ tự chi tiết giữa bean phụ thuộc phase, dependency và cơ chế destroy; không nên dựa vào thứ tự log từ nhiều hooks của những hệ thống khác nhau.

### context.close khác System.exit

| Lời gọi | Tác dụng chủ yếu |
|---|---|
| `context.close()` | Đóng **context đó**. Nếu có nhiều context trong một JVM, các context khác không tự biến mất chỉ vì context này được đóng. |
| `SpringApplication.exit(context)` | Đóng context theo helper của Boot và trả về exit code được tính theo `ExitCodeGenerator`. |
| `System.exit(code)` | Bắt đầu quá trình kết thúc **cả JVM**, kích hoạt shutdown hooks. |
| `Runtime.getRuntime().halt(code)` | Kết thúc JVM ngay, không thực hiện shutdown hooks theo cách bình thường. |

Một ứng dụng console có thể chủ động:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

Đây là ví dụ **chỉ khi muốn kết thúc chủ động**, không nên đưa nguyên đoạn vào web server cần sống lâu. `SpringApplication.exit(context)` đã đóng context; `System.exit(code)` tiếp tục kết thúc JVM và có thể thực thi những hooks khác. Nếu chỉ gọi `SpringApplication.exit(...)` thì quá trình có thể vẫn còn các non-daemon threads giữ JVM sống.

Không gọi `System.exit(...)` tùy tiện từ một `@PreDestroy` hoặc chính shutdown hook để “dọn nhanh”; làm vậy dễ gây treo, vòng phụ thuộc hoặc làm gián đoạn shutdown sequence.

## 4. @PreDestroy và SmartLifecycle giải quyết hai lớp trách nhiệm

Có hai việc khác nhau:

1. **Ngừng hoạt động:** không tiếp nhận việc mới, dừng polling/message consumer, không tạo task mới, chờ một phần công việc đang chạy. `SmartLifecycle` hữu ích để quản lý start/stop và thứ tự phase.
2. **Hủy bean/tài nguyên:** đóng file, connection, client, cache hoặc object đã được bean sở hữu. `@PreDestroy`, `DisposableBean` và custom destroy method thể hiện bước cleanup khi bean bị hủy.

Ví dụ:

~~~java
@Component
public class RemoteClientOwner {

    private final ExternalClient client;

    public RemoteClientOwner(ExternalClient client) {
        this.client = client;
    }

    @PreDestroy
    public void close() {
        client.close();
    }
}
~~~

Đây là **mã minh họa**, class `ExternalClient` và cách tạo/inject bean chưa được khai báo; không phải file chạy độc lập. Phương thức `@PreDestroy` chỉ chạy khi Spring **hủy bean được quản lý**, không phải cứ object bị GC là callback chạy.

Spring sẽ không tự cleanup một object được tạo ngoài container bằng `new` nếu bạn không tổ chức ownership rõ. Với **prototype scope**, destroy callback không được Spring tự quản lý toàn bộ sau khi đã giao prototype bean cho caller như với singleton; caller chịu trách nhiệm dọn tài nguyên theo hợp đồng.

### SmartLifecycle stop(Runnable) và giới hạn chờ

Một component có thể implement:

~~~java
@Override
public void stop(Runnable callback) {
    // Dừng nhận việc mới và chờ tác vụ hoàn tất.
    // CHỈ khi việc dừng thực sự hoàn tất:
    callback.run();
}
~~~

Đây là method minh họa thuộc một class đã implements `SmartLifecycle`. Khi container đóng, `LifecycleProcessor` có thể dùng `stop(Runnable)` để điều phối shutdown. Callback cần được gọi **sau khi dừng thành công hoặc hoàn tất chính sách dừng có kiểm soát**.

Không gọi callback ngay sau khi **chỉ phát yêu cầu stop bất đồng bộ** rồi cho rằng công việc đã hết. Ngược lại, nếu không bao giờ gọi callback, lifecycle processor có thể chờ tới khi timeout của phase và tiếp tục với các bước shutdown khác.

**Đừng kỳ vọng phase timeout sẽ luôn giết mọi task Java.** Nó giới hạn khoảng chờ của cơ chế Spring; các thread/task không hợp tác với interruption có thể vẫn chạy, khiến process tiếp tục sống hoặc bị platform kill khi hết hạn.

## 5. Graceful shutdown của HTTP server trong Spring Boot 3.3

Với Spring Boot 3.3.x, graceful shutdown của embedded HTTP server được bật tường minh bằng:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Spring Boot hỗ trợ graceful shutdown cho Tomcat, Jetty, Reactor Netty và Undertow theo tính năng của mỗi server. Khi context đóng, quá trình graceful stop được tích hợp với lifecycle của web server: hạn chế request mới, cho những request đang chạy cơ hội hoàn tất **trong một khoảng chờ**.

**Kết quả từ chối request mới có thể khác theo server:**

- Một server có thể ngừng nhận kết nối mới tại tầng mạng.
- Một server khác có thể phản hồi mã lỗi dịch vụ như HTTP 503.
- Keep-alive connections, proxy/load balancer và request đang chạy có thể làm hành vi ngoài mạng khác cách diễn giải đơn giản “tất cả request mới lập tức bị từ chối”.

`spring.lifecycle.timeout-per-shutdown-phase=20s` là **thời gian chờ trên mỗi shutdown phase** trong lifecycle processor, không phải bảo đảm toàn bộ JVM cleanup kết thúc trước 20 giây. Nếu có nhiều phase, `@PreDestroy` kéo dài, network close chậm hoặc preStop ở Kubernetes, tổng thời gian có thể lớn hơn. Vì vậy phải tính **ngân sách tổng của container** chứ không chỉ nhìn một property này.

### Cần dừng cái gì trước?

Một cách thiết kế:

~~~text
Bắt đầu dừng
   |
   v
Router/orchestrator không chuyển request mới đến instance
   |
   v
HTTP server graceful stop / dừng nhận message mới
   |
   v
Đợi request/job đang chạy có thời hạn và giới hạn
   |
   v
Dừng scheduler, consumer, executor theo dependency
   |
   v
Đóng DB pool, HTTP client, broker connection, file handles
   |
   v
Kết thúc process
~~~

Đây là **trình tự mong muốn**, không phải lời hứa các sự kiện luôn xảy ra tuần tự tuyệt đối. Ngữ nghĩa thực tế phụ thuộc Spring lifecycle phases, bean dependencies, container runtime, phía client và khả năng completion của job.

Ví dụ nếu message consumer vẫn nhận tin trong khi database pool đã đóng, cleanup đã sai thứ tự. Cần tổ chức `SmartLifecycle.getPhase()`, quan hệ dependency hoặc chính sách shutdown ở đúng component để dừng producers/consumers trước khi đóng các tài nguyên mà chúng còn dùng.

## 6. Ví dụ Spring Boot 3.3 chạy được: quan sát dừng mềm và dừng cưỡng bức

Demo này làm ba việc:

- Tạo một Spring Boot web application để JVM tiếp tục phục vụ request.
- Đăng ký **một bean `SmartLifecycle`** in log khi start/stop, kèm `@PreDestroy` trên chính bean đó.
- Có endpoint `GET /lab/slow` giả lập request dài có thời hạn, giúp quan sát graceful HTTP shutdown khi gửi SIGTERM.

### Cấu trúc

~~~text
shutdown-lab/
├── build.gradle
└── src/
    └── main/
        ├── java/com/example/shutdown/ShutdownLabApplication.java
        └── resources/application.properties
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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

springBoot {
    mainClass = 'com.example.shutdown.ShutdownLabApplication'
}

tasks.named('bootJar') {
    archiveFileName = 'shutdown-lab.jar'
}
~~~

### application.properties

Tạo `src/main/resources/application.properties`:

~~~properties
spring.application.name=shutdown-lab
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
logging.level.root=INFO
~~~

Trong ứng dụng production, không nhất thiết dùng 20 giây; hãy chọn theo latency/thời gian xử lý thực, số shutdown phases và budget của orchestrator.

### ShutdownLabApplication.java

Tạo file `src/main/java/com/example/shutdown/ShutdownLabApplication.java`:

~~~java
package com.example.shutdown;

import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ShutdownLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShutdownLabApplication.class, args);
    }

    @Bean
    ShutdownObserver shutdownObserver() {
        return new ShutdownObserver();
    }

    public static final class ShutdownObserver implements SmartLifecycle {

        private final AtomicBoolean running = new AtomicBoolean(false);

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return 0;
        }

        @Override
        public boolean isRunning() {
            return running.get();
        }

        @Override
        public void start() {
            if (running.compareAndSet(false, true)) {
                System.out.println("observer: started");
            }
        }

        @Override
        public void stop() {
            if (running.compareAndSet(true, false)) {
                System.out.println("observer: stopped");
            }
        }

        @Override
        public void stop(Runnable callback) {
            try {
                stop();
            } finally {
                // Chỉ đúng vì stop() trong demo kết thúc đồng bộ.
                callback.run();
            }
        }

        @PreDestroy
        public void destroy() {
            System.out.println("observer: @PreDestroy");
        }
    }

    @RestController
    public static class LabController {

        @GetMapping("/lab/ping")
        public String ping() {
            return "pong";
        }

        @GetMapping("/lab/slow")
        public String slow(
                @RequestParam(defaultValue = "8000") long millis) {

            if (millis < 0 || millis > 15000) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "millis must be between 0 and 15000");
            }

            try {
                Thread.sleep(millis);
                return "completed";
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new ResponseStatusException(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        "request interrupted during shutdown", ex);
            }
        }
    }
}
~~~

**Vì sao chương trình này dễ kiểm chứng?**

- Bean `ShutdownObserver` được tạo qua `@Bean` và do Spring quản lý. Nó implement `SmartLifecycle` nên context sẽ gọi `start()` trong refresh và `stop(Runnable)` trong quá trình đóng khi bean đang chạy.
- `@PreDestroy` là một cleanup callback riêng của **cùng bean**. Trong một lần đóng context bình thường, Spring dừng lifecycle components trước pha destroy singleton tương ứng.
- `stop(Runnable)` gọi callback trong `finally` bởi vì `stop()` trong demo **chỉ đổi cờ** và kết thúc đồng bộ. Không sao chép nguyên cơ chế này cho một consumer phải chờ việc bất đồng bộ.
- Endpoint chậm mô phỏng request dài tối đa 15 giây, nhỏ hơn mức chờ graceful HTTP 20 giây trong kịch bản lab.
- Không tự tạo JVM shutdown hook trong code. Spring Boot quản lý việc đóng context theo cơ chế mặc định.

### Build và chạy trực tiếp

Với JDK 17+ và project có Gradle wrapper:

~~~bash
./gradlew bootJar
java -jar build/libs/shutdown-lab.jar
~~~

Trên Windows, dùng `.\gradlew.bat bootJar` rồi `java -jar build/libs/shutdown-lab.jar`. Nếu chưa có wrapper, cần chuẩn bị Gradle hoặc tạo project phù hợp trước. Đây là ứng dụng Spring Boot có dependency; không thể biên dịch độc lập bằng một lệnh `javac ShutdownLabApplication.java` trần.

Khi startup thành công, bên cạnh log Spring Boot, bạn sẽ thấy:

~~~text
observer: started
~~~

Để kiểm tra HTTP:

~~~bash
curl http://localhost:8080/lab/ping
~~~

Body kỳ vọng:

~~~text
pong
~~~

### Thử Ctrl+C

Khi ứng dụng đang chạy **trực tiếp** bằng `java -jar ...` ở một terminal tương tác, nhấn `Ctrl+C`. Với HotSpot JVM và terminal Unix thông thường, JVM nhận SIGINT, Spring shutdown hook có cơ hội đóng context.

Các dòng **do `ShutdownObserver` in** trong trường hợp shutdown hoàn tất bình thường:

~~~text
observer: stopped
observer: @PreDestroy
~~~

Spring/Tomcat cũng có thể ghi log shutdown; thời gian và các log khác xen vào không cố định. Nếu chạy qua Gradle task, IDE hoặc Windows console, hành vi của nút Stop/Ctrl+C **có thể khác**, vì công cụ quản lý có thể dừng JVM bằng đường riêng. Muốn xác minh chính xác tín hiệu, thử chạy JAR trực tiếp và ghi nhận process thật.

### Thử SIGTERM trên Linux trong môi trường lab

Mở terminal thứ nhất, chạy trong shell:

~~~bash
java -jar build/libs/shutdown-lab.jar > shutdown.log 2>&1 &
APP_PID=$!
echo "Lab JVM PID=$APP_PID"
~~~

Đợi server startup. Trong terminal khác, có thể gửi request chậm:

~~~bash
curl -v "http://localhost:8080/lab/slow?millis=8000"
~~~

Trong lúc request còn chạy, gửi TERM tới **đúng PID vừa chạy** (có thể chạy lệnh từ shell đã giữ biến `APP_PID`):

~~~bash
kill -TERM "$APP_PID"
wait "$APP_PID"
~~~

Nếu request đã được server chấp nhận trước khi shutdown bắt đầu, request 8 giây có thể có cơ hội hoàn tất trong ngân sách 20 giây. Phụ thuộc thời điểm gửi signal, connection, load balancer và những timeout khác, không cam kết từng HTTP request sẽ luôn thành công.

Kiểm tra `shutdown.log`: khi dừng mềm hoàn tất, các dòng của observer thường cho thấy `stopped` và `@PreDestroy`. **Không** lấy việc có log đó làm bằng chứng rằng mọi database transaction, message ack và dữ liệu đang ghi đã được commit bền vững.

### So sánh với SIGKILL — chỉ làm trong môi trường test

Chạy lại ứng dụng trong một lab process riêng:

~~~bash
java -jar build/libs/shutdown-lab.jar > forced.log 2>&1 &
LAB_PID=$!
~~~

Sau khi server đã lên, trong cùng shell:

~~~bash
kill -KILL "$LAB_PID"
wait "$LAB_PID" || true
~~~

Không dùng lệnh này cho ứng dụng người khác, process production hoặc bất kỳ PID nào chưa kiểm chứng.

**Kết quả bản chất:** SIGKILL chấm dứt tiến trình ngay; nó không cho JVM thực thi shutdown hooks và không có bảo đảm `observer: stopped` hay `observer: @PreDestroy` xuất hiện. Nếu dòng log đã được ghi trước lúc kill vì một sự kiện khác, chỉ dựa vào sự hiện diện của dòng log là chưa đủ kết luận. Hãy chạy mỗi lần trong process mới, với kịch bản được kiểm soát.

OS sẽ thu hồi nhiều tài nguyên cục bộ của tiến trình đã chết như file descriptors/socket handles, nhưng những tác vụ nghiệp vụ dở dang **không tự được hoàn tất**. Ví dụ transaction có thể rollback tùy hệ thống và trạng thái kết nối; message chưa ack có thể được gửi lại; một file đã ghi dở có thể còn trên đĩa.

## 7. finally có phải luôn chạy không?

Không. `finally` là cơ chế của **luồng điều khiển Java đang unwind qua khối try**, chứ không phải một hợp đồng chống mọi cách giết process.

Ví dụ:

~~~java
try {
    updateExternalSystem();
} finally {
    releaseLocalResource();
}
~~~

Đây là đoạn minh họa với các method đã tồn tại. Nếu method trả về hoặc ném exception trong quá trình chạy Java bình thường, `finally` thường được thực hiện khi control thoát khối `try`. Tuy nhiên:

- Nếu JVM bị SIGKILL, code có thể bị cắt ngay giữa `try` hoặc giữa `finally`.
- Nếu JVM bị `Runtime.halt()` hoặc gặp native crash, không có bảo đảm cleanup Java.
- Nếu một thread bị chặn vô hạn và không đi ra khỏi `try`, `finally` không tự chạy chỉ vì thời gian đã trôi qua.
- Nếu process bị kill khi đang ghi external side effect, việc `finally` trước đó có chạy **không** chứng minh side effect đã hoàn tất bền vững.

**Tương tự, `@PreDestroy` không phải hàm “chắc chắn chạy trước khi tiến trình biến mất”.** Nó chạy trong luồng đóng bean có kiểm soát, và chỉ nếu quá trình đóng context thực sự tiến tới callback đó.

Vì vậy, tài nguyên cần cleanup thì vẫn phải có `finally`/`try-with-resources`/`@PreDestroy`; nhưng tính đúng đắn nghiệp vụ phải được đảm bảo bằng **cơ chế phục hồi sau gián đoạn**.

## 8. Kubernetes: terminationGracePeriodSeconds là một ngân sách tổng

Khi Pod bị xóa hoặc thay trong rollout, kubelet thông thường cố cho container dừng mềm:

~~~text
Pod được đánh dấu Terminating
      |
      +-- EndpointSlice thay đổi trạng thái serving/ready
      |   để traffic mới dần được rút
      |
      +-- Nếu có preStop hook, kubelet chạy preStop
      |   (thời gian của hook tính trong grace period)
      |
      +-- Runtime gửi TERM tới process chính của container
      |
      +-- Chờ container thoát trong tổng ngân sách
      |
      +-- Nếu hết thời gian và còn chạy -> SIGKILL
~~~

Mặc định Kubernetes thường dùng **`terminationGracePeriodSeconds: 30`** nếu không cấu hình khác. Tại thời điểm Pod được đánh dấu terminating, grace period đã bắt đầu; **`preStop` không được cấp thêm một khoảng thời gian miễn phí ngoài budget**. Nếu `preStop` mất 15 giây trong budget 30 giây, ứng dụng chỉ còn phần thời gian còn lại để xử lý TERM và cleanup (trừ một số hành vi mở rộng ngắn đặc biệt của kubelet).

Đoạn YAML minh họa trong cấu hình Pod/Deployment:

~~~yaml
spec:
  terminationGracePeriodSeconds: 45
  containers:
    - name: spring-app
      image: example.invalid/shutdown-lab:demo
      ports:
        - containerPort: 8080
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 5"]
~~~

Đây là **đoạn Pod spec minh họa**, không phải manifest chạy được nguyên vẹn; `example.invalid/...` chỉ là tên image placeholder và image thực tế phải được thay thế theo môi trường. `sleep 5` chỉ minh họa rằng preStop **chiếm năm giây** của tổng grace period. Không coi việc sleep là phương án drain traffic hoàn chỉnh.

Các bước drain phụ thuộc Kubernetes Service, EndpointSlice, ingress/gateway, thời gian propagation và kết nối keep-alive. Readiness chuyển sang NotReady cũng không làm **mọi kết nối có sẵn biến mất tức thì**.

### Phối hợp hai loại timeout

Nếu Spring Boot có:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

và Pod có:

~~~yaml
terminationGracePeriodSeconds: 45
~~~

thì vẫn cần xem tổng thời gian của:

1. preStop.
2. Thời gian drain routing và request đang xử lý.
3. Các shutdown phases của Spring (mỗi phase có timeout riêng).
4. Hủy bean: `@PreDestroy`, đóng datasource, HTTP client, broker, file...
5. Phần chênh dự phòng do CPU throttling, GC pause, network và log flushing.

**Không có công thức an toàn** kiểu `45 >= 20` nên mọi thứ chắc chắn hoàn tất. Nhiều phase hoặc cleanup chậm có thể tiêu hết 45 giây. Hãy đo shutdown latency p95/p99 trong staging và đặt budget với khoảng đệm phù hợp.

### Đừng quên tín hiệu tới PID 1

Trong container Linux, runtime gửi tín hiệu dừng tới process chính/PID 1 (theo cấu hình runtime/image). Nếu PID 1 là shell wrapper không chuyển tiếp TERM, JVM có thể **không nhận tín hiệu như dự kiến**.

Prefer dạng exec của Dockerfile:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Hoặc nếu cần shell script entrypoint, cuối script nên bàn giao bằng:

~~~sh
exec java -jar /app/app.jar
~~~

Với `exec`, shell được thay bằng process Java; TERM đến đúng JVM. Với `sh -c "java -jar ..."` mà không xử lý/chuyển tiếp signal rõ ràng, phải kiểm tra ai là PID 1 và signal delivery thực tế.

Lưu ý: một số image/runtime dùng init process hoặc signal proxy nên cách chạy khác; đừng chỉ nhìn Dockerfile rồi suy luận, hãy kiểm chứng container process tree và events.

## 9. Tại sao Ctrl+C và SIGTERM có thể khác khi chạy qua Gradle, IDE hoặc Windows?

Một câu lệnh `java -jar app.jar` chạy trực tiếp có đường nhận tín hiệu khác với:

- `./gradlew bootRun` (Gradle có process của riêng nó, có thể fork JVM con).
- IDE Stop button (có thể gửi signal, terminate process hoặc force kill).
- Windows PowerShell/cmd/terminal với console control event thay vì Unix signal.
- Docker/Kubernetes gửi TERM tới process chính của container.
- Windows service manager, systemd hay một process supervisor khác.

Một thao tác “Stop” trong UI **không bảo đảm** tương đương `SIGTERM`. Ví dụ khi IDE force kill JVM, bạn có thể không thấy `@PreDestroy` dù code đúng.

Để phân tích:

1. Xác nhận **PID JVM thật**, không nhầm PID Gradle, wrapper hoặc process giám sát.
2. Xác nhận tín hiệu/lệnh terminate mà công cụ gửi.
3. Quan sát Spring shutdown lifecycle logs và các resource metrics trước/sau.
4. Chạy JAR trực tiếp như đối chứng.
5. Lặp lại trong môi trường triển khai tương ứng trước khi kết luận production sẽ giống local.

**Không dùng `-Xrs` tùy tiện** khi phụ thuộc vào JVM signal handling, vì tuỳ chọn này làm giảm việc JVM sử dụng một số OS signals và có thể thay đổi cơ chế shutdown hooks. Cấu hình và JVM vendor cụ thể phải được kiểm tra theo môi trường.

## 10. Graceful HTTP shutdown không đồng nghĩa mọi background job đã xong

Web request, message consumer, scheduler, executor, database transaction và job queue có **owner và điều kiện hoàn tất riêng**.

| Thành phần | Cần xử lý khi shutdown | Nguy cơ khi bị SIGKILL |
|---|---|---|
| HTTP server | Ngừng nhận mới, cho in-flight requests thời gian có hạn | Request đứt giữa chừng, client retry. |
| `@Scheduled` jobs | Dừng trigger mới, xử lý job đang chạy | Job bị cắt, tick kế tiếp có thể bị bỏ. |
| `@Async` / executor | Ngừng submit, chờ/cancel worker theo deadline | Queue trong bộ nhớ mất, task chưa hoàn tất. |
| Kafka/Rabbit/message consumer | Ngừng nhận, xử lý rồi ack/commit theo hợp đồng | Có thể redelivery, duplicate, rebalancing. |
| JDBC transaction | Commit/rollback đúng ranh giới, không giữ connection vô hạn | Transaction in-flight có thể abort/rollback hoặc client không biết outcome. |
| External HTTP call | Timeout, ngắt/hoàn tất, xử lý idempotency | Remote side effect có thể đã thực hiện nhưng caller chưa nhận phản hồi. |
| File export | Flush/close và publish kết quả atomically nếu có thể | File tạm hoặc file dở có thể còn trên disk. |
| Metrics/logging | Flush trong thời gian giới hạn | Mất log/metrics cuối, nhất là buffer bất đồng bộ. |

Một shutdown hook kéo dài 30 giây để đợi toàn bộ công việc **không bảo đảm** việc dừng sẽ tốt hơn. Nếu deadline Pod chỉ 20 giây, hạ tầng có thể kill process trước khi cleanup tới các bước quan trọng.

Nên thiết kế **giới hạn thời gian cho từng nhóm**: ví dụ ngừng nhận event ngay, đợi task in-flight 10 giây, sau đó cancel hoặc cho phép retry trên hệ thống durable. Quyết định đúng tùy yêu cầu mất dữ liệu, semantics queue và khả năng idempotency.

### Cần tránh “đóng connection pool trước khi dừng công việc”

Một trình tự nguy hiểm:

~~~text
Close DataSource
     |
     v
Background worker còn chạy SQL
     |
     v
SQLException / lỗi giữa transaction
~~~

Nếu bean producer/consumer có lifecycle phức tạp, sử dụng `SmartLifecycle.getPhase()` hoặc quản lý dependency rõ ràng. Khi start, component phase thấp được start trước phase cao; khi stop, phase cao được dừng trước phase thấp. Nhưng dependency được khai báo tường minh có thể ảnh hưởng thứ tự, và destroy callbacks của bean còn tuân theo semantics riêng.

Đừng dựa vào **thứ tự các JVM shutdown hooks độc lập** để orchestrate đóng từng service Spring.

## 11. Thiết kế công việc chịu được force kill

Vì `SIGKILL` có thể xuất hiện ngay giữa tác vụ, cleanup không được là tuyến phòng thủ duy nhất. Những nguyên tắc sau quan trọng hơn “hứa sẽ luôn hoàn tất trước khi tắt”:

### 11.1 Idempotency

Nếu client không nhận được phản hồi vì server bị kill, client có thể retry. Một thao tác như tạo thanh toán hoặc gửi email phải có **idempotency key** hoặc cơ chế chống áp dụng lặp.

Ví dụ:

~~~text
Client -> POST tạo giao dịch (idempotency-key=abc)
Server gửi yêu cầu xử lý đến downstream
Server bị kill trước khi trả HTTP response
Client retry với cùng key
Hệ thống nhận diện key đã xử lý hoặc đang xử lý
Không tạo giao dịch trùng
~~~

Đây là flow minh họa; triển khai thực tế cần **lưu trạng thái idempotency bền vững** và kiểm soát cạnh tranh, không phải một `ConcurrentHashMap` chỉ tồn tại trong JVM.

### 11.2 Ack/commit sau khi công việc đã bền vững

Với message queue:

~~~text
Nhận message
   |
   v
Xử lý nghiệp vụ theo transaction/idempotency
   |
   v
Commit kết quả bền vững
   |
   v
Ack/commit offset theo semantics của broker
~~~

Nếu ack trước khi dữ liệu được lưu bền vững, force kill sau ack có thể làm mất việc. Nếu commit nghiệp vụ xong nhưng kill trước ack, broker có thể phát lại, nên logic xử lý phải chịu được duplicate.

Không khẳng định có “exactly once” chỉ vì dùng transactional code hoặc `@PreDestroy`: cần hiểu hợp đồng của broker, database và external side effects.

### 11.3 Checkpoint và resume

Với batch import/export:

- Đặt job ID và trạng thái bền vững.
- Lưu checkpoint sau mỗi nhóm dữ liệu hoặc giai đoạn.
- Khi restart, resume hoặc retry từ checkpoint đã commit.
- Dùng file tạm, kiểm tra integrity và thao tác rename/publish phù hợp để tránh phát hành file dở.
- Không chỉ dựa vào trạng thái in-memory của executor.

### 11.4 Timeout và cancellation

Không dùng `Thread.sleep(9999999)` hoặc I/O call không timeout trong cleanup. Tác vụ cần biết deadline còn lại, dừng nhận việc mới và hợp tác với interruption khi có yêu cầu dừng.

Tuy nhiên, interruption của Java **không phải SIGKILL**. Interruption là tín hiệu hợp tác ở cấp thread; SIGKILL của OS chấm dứt process mà không chờ tác vụ phản ứng.

## 12. Lỗi thường gặp

**Lỗi 1 — “SIGTERM là SIGKILL, đều không thể cleanup”.** Sai. TERM là tín hiệu mềm có thể được JVM xử lý; KILL không thể bị ứng dụng bắt hoặc xử lý.

**Lỗi 2 — “Ctrl+C luôn tương đương kill -9”.** Sai. Trong terminal Unix thông thường, Ctrl+C tạo SIGINT và JVM có cơ chế shutdown hooks. IDE/wrapper/Windows có thể khác.

**Lỗi 3 — “Có @PreDestroy là chắc chắn close khi process chết”.** Không. Callback chỉ được thực hiện nếu Spring context đi qua vòng đóng hợp lệ; force kill không bảo đảm.

**Lỗi 4 — “finally luôn chạy, kể cả SIGKILL”.** Sai. SIGKILL có thể ngắt JVM ngay giữa bytecode và không cho thread unwind stack.

**Lỗi 5 — “Các shutdown hooks chạy theo thứ tự đăng ký”.** Không. Java không bảo đảm thứ tự, hooks có thể chạy đồng thời. Muốn sắp thứ tự bean, dùng Spring lifecycle.

**Lỗi 6 — “Chỉ đặt spring.lifecycle.timeout-per-shutdown-phase=20s là JVM chắc chắn thoát trước 20 giây”.** Sai. Đây là budget **mỗi phase**, chưa tính preStop và các bước khác.

**Lỗi 7 — “preStop mất 10 giây được cộng thêm vào Kubernetes grace period”.** Sai. PreStop tiêu thụ cùng tổng grace period.

**Lỗi 8 — “Dùng sh -c java -jar là JVM luôn nhận SIGTERM”.** Không. Shell có thể là PID 1 và không forward signal như mong muốn; dùng exec form/exec rõ ràng hoặc init/supervisor phù hợp.

**Lỗi 9 — “Graceful shutdown làm mọi request đang chạy hoàn tất vô thời hạn”.** Không. Có timeout, client disconnect và nguy cơ force kill.

**Lỗi 10 — “System.exit và SpringApplication.exit giống nhau”.** Không. SpringApplication.exit đóng context và trả exit code; System.exit bắt đầu JVM shutdown.

**Lỗi 11 — “Kubernetes xóa Pod đồng nghĩa mọi kết nối bị cắt ngay”.** Không hẳn. Endpoint status/drain và active connections có hành vi riêng; cần kiểm tra ingress và graceful HTTP server.

**Lỗi 12 — “Sau khi SIGKILL, hệ điều hành không đóng bất kỳ tài nguyên nào”.** Không đúng. OS thu hồi nhiều tài nguyên cục bộ của process, nhưng business state, remote side effects, file dở và message ack không được đảm bảo hoàn tất.

**Lỗi 13 — “Chỉ cần tăng terminationGracePeriodSeconds lên rất lớn là đủ”.** Không. Một task treo vô hạn vẫn không tự xong. Cần timeout, recovery/idempotency và giới hạn cleanup hợp lý.

**Lỗi 14 — “@Scheduled/@Async chỉ có một thread, context close sẽ luôn đợi mọi task”.** Không đúng. Cần xem loại executor/scheduler, cấu hình shutdown, queue, interruption và thời gian còn lại.

## 13. Quy trình kiểm chứng trong môi trường staging

Không kiểm thử `kill -9` trên production hoặc process không thuộc quyền quản lý. Với một bản chạy staging riêng:

1. **Đo baseline:** số in-flight requests, active JDBC connections, consumer lag, executor queued tasks, file descriptors, uptime.
2. **Gửi SIGTERM tới đúng JVM PID:** xác nhận Spring context đóng và cleanup callbacks chạy; đo thời gian từ signal đến process exit.
3. **Thử Ctrl+C trực tiếp trên JAR:** đối chiếu với SIGTERM. Sau đó thử Gradle/IDE riêng để hiểu đường signal khác.
4. **Chạy một request dài có giới hạn:** gửi TERM sau khi request đã được nhận; kiểm tra có hoàn tất trong grace period không.
5. **Thử container TERM và preStop:** xác minh JVM thật nhận TERM, preStop tiêu thời gian bao nhiêu và endpoint có được drain hay chưa.
6. **Thử buộc kết thúc sau deadline:** trong môi trường lab, gửi SIGKILL và xác nhận hệ thống có thể khởi động lại, phát hiện/retry công việc dở.
7. **Đối chiếu persistence:** job table, queue ack, idempotency keys, file tạm, DB transactions. Đừng chỉ nhìn log @PreDestroy.
8. **Đo shutdown tail latency:** p50/p95/p99 của thời gian dừng, kể cả GC pause, CPU throttling, network timeout.
9. **Xem cấu hình tổng:** Spring shutdown phases + preStop + application cleanup + orchestrator budget + buffer.
10. **Viết automated integration test:** kết thúc child process bằng TERM, chờ có timeout, đối chiếu log/exit code/state; test force kill độc lập và kiểm tra recovery.

### Exit codes: tham khảo, không dùng làm bằng chứng duy nhất

Trên nhiều shell Unix, exit status **143** thường tương ứng với quy ước `128 + 15` cho SIGTERM, và **137** thường tương ứng `128 + 9` cho SIGKILL. Tuy nhiên wrapper, shell, JVM, container runtime, custom exit code và termination mechanism có thể làm giá trị bạn quan sát khác đi.

Không kết luận “OOMKilled” chỉ vì thấy exit code 137; cần xem Kubernetes container state, reason, events và memory pressure. Tương tự, không kết luận cleanup hoàn tất chỉ vì process trả exit code 0.

## 14. Checklist vận hành

- Mỗi Spring ApplicationContext có owner và được đóng khi đến cuối vòng đời.
- Không tắt `SpringApplication` JVM shutdown hook nếu không có lý do và cơ chế thay thế đáng tin.
- `@PreDestroy`/destroy methods ngắn, idempotent, có timeout và xử lý lỗi hợp lý.
- `SmartLifecycle.stop(Runnable)` chỉ gọi callback khi dừng thực sự hoàn tất theo hợp đồng.
- Phối hợp thứ tự: ngừng request/message mới trước, dừng worker trước khi đóng shared dependencies.
- Web server cấu hình `server.shutdown=graceful` nếu cần drain request trên Spring Boot 3.3.
- `spring.lifecycle.timeout-per-shutdown-phase` được hiểu là budget **mỗi phase**, không phải tổng lifecycle.
- Kubernetes `terminationGracePeriodSeconds` đủ cho preStop + shutdown phases + cleanup + buffer, được đo thực nghiệm.
- Java process nhận đúng TERM: kiểm tra PID 1, entrypoint, signal forwarding, IDE/process wrapper.
- Có timeout cho DB/HTTP/broker và không chờ công việc vô hạn trong shutdown.
- Task quan trọng có persistence, retry, idempotency, checkpoint, ack semantics phù hợp khi force kill.
- Quan sát signals, readiness/EndpointSlice, in-flight requests, active tasks, pool closing và restart events.
- Có test cả SIGTERM/Ctrl+C **lẫn** forced termination trong môi trường tách biệt.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — SpringApplication, Application Exit: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — SpringApplication#setRegisterShutdownHook: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Java 17 — Runtime, shutdown hooks và halt: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html
- Kubernetes — Pod Lifecycle, Termination of Pods: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Kubernetes — Container Lifecycle Hooks / PreStop: https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/

**Kết luận:** SIGTERM và Ctrl+C **thường cho JVM cơ hội** đóng Spring ApplicationContext và chạy `SmartLifecycle`/`@PreDestroy`; `SIGKILL`, `halt` và sự cố đột ngột **không bảo đảm** các bước này. Spring graceful shutdown có timeout, Kubernetes có **một tổng grace period** bao gồm cả preStop. Muốn hệ thống an toàn, phải phối hợp **cleanup có giới hạn thời gian** với **dữ liệu bền vững, idempotency và recovery khi tiến trình chết giữa chừng**.
