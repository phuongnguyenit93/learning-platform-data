# Bật server.shutdown=graceful trong Spring Boot 3.3

## 1. Graceful shutdown giải quyết vấn đề gì?

Khi một Spring Boot web application được deploy phiên bản mới, scale down, rolling update hoặc quản trị viên yêu cầu dừng, các request HTTP vẫn có thể đang xử lý. Nếu server ngừng đột ngột, một request có thể bị cắt giữa lúc tính toán, gọi database, ghi dữ liệu hoặc trả response. Client thường không biết giao dịch đã hoàn thành hay chưa, nên retry có thể gây thêm lỗi nghiệp vụ.

**Graceful shutdown** là cách dừng embedded web server có kiểm soát: server **ngừng nhận request mới** và **cho các request đã được chấp nhận một khoảng thời gian để hoàn tất**. Sau khoảng chờ, ApplicationContext vẫn phải tiếp tục đóng các thành phần còn lại.

Với **Spring Boot 3.3**, bật tường minh trong application.properties:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Điểm chính xác theo phiên bản rất quan trọng: **server.shutdown mặc định là immediate trong Spring Boot 3.3**. Đừng áp dụng nhầm thông tin từ Spring Boot 3.4 trở lên, nơi graceful shutdown được bật theo mặc định trong các embedded server hỗ trợ. Tài liệu của Spring Boot 3.3 hướng dẫn người dùng **chủ động đặt server.shutdown=graceful**.

Spring Boot 3.3 hỗ trợ tính năng này với bốn embedded web servers: **Tomcat**, **Jetty**, **Undertow** và **Reactor Netty**, áp dụng cho mô hình servlet hoặc reactive phù hợp.

Graceful shutdown **không** có nghĩa mọi request chắc chắn thành công, mọi kết nối dài bị đóng đúng ý ứng dụng, hoặc mọi bean sẽ được dừng trong cùng một khoảng thời gian. Đó là một phần của **đường đóng ApplicationContext**, cần phối hợp với readiness, load balancer, timeouts của client và tài nguyên bên ngoài.

## 2. Phân biệt immediate và graceful

| Khía cạnh | immediate | graceful |
| --- | --- | --- |
| Mặc định của Spring Boot 3.3 | **Có** | Không; phải bật tường minh |
| Mục tiêu | Đóng web server trong đường shutdown không cung cấp giai đoạn drain tương ứng | Ngăn request mới và chờ request đã nhận hoàn tất trong giới hạn |
| Request HTTP đang xử lý | Có nguy cơ bị gián đoạn | Có cơ hội hoàn tất |
| Request mới đến khi shutdown | Không còn đường phục vụ bình thường | Bị từ chối bằng hành vi tùy embedded server |
| Timeout liên quan | Các cơ chế lifecycle khác vẫn tồn tại | Shutdown phase có thời gian chờ cho graceful web server |
| Đảm bảo không mất request | Không | **Cũng không tuyệt đối** |
| Tự dừng Kafka consumer/external tasks an toàn | Không | Không |
| Tự thay thế Kubernetes readiness | Không | Không |

**Không chỉ tăng timeout.** Ví dụ:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=90s
~~~

không tự kích hoạt graceful nếu **server.shutdown** vẫn là **immediate** trong Boot 3.3.

Ngược lại, bật graceful với thời hạn rất ngắn có thể khiến request dài không đủ thời gian hoàn tất.

### Mô tả bằng dòng thời gian

~~~text
T0    Request A bắt đầu xử lý (dự tính mất 8 giây)
T2    JVM nhận SIGTERM / context bắt đầu close
      |
      +--> server bắt đầu ngừng nhận request mới
      +--> request A được phép tiếp tục trong ngân sách chờ
      |
T8    Request A trả response thành công nếu không bị lỗi khác
      |
      +--> các SmartLifecycle phases khác tiếp tục dừng
      +--> bean destruction, tài nguyên và process exit
~~~

Các mốc là **ví dụ giả định**, không phải thời lượng được Spring Boot cam kết. Client timeout, proxy, database, lỗi ứng dụng hay JVM force-kill vẫn có thể ngắt luồng xử lý.

## 3. Hai property cần nhớ và các giá trị mặc định của Boot 3.3

### server.shutdown

~~~properties
server.shutdown=graceful
~~~

Giá trị được Spring Boot hỗ trợ:

- **immediate**: chế độ mặc định trong Boot 3.3.
- **graceful**: bật graceful shutdown cho embedded web server.

Spring Boot bind chuỗi này sang lựa chọn shutdown behavior của server do Boot quản lý. Đây là **cấu hình bootstrap**, nên thay đổi file khi JVM đang chạy không đồng nghĩa server hiện tại lập tức đổi cơ chế shutdown; cần có cơ chế reconfiguration hoặc restart thích hợp.

### spring.lifecycle.timeout-per-shutdown-phase

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Property này là một **Duration**, chỉ **ngân sách chờ tối đa cho mỗi nhóm phase của SmartLifecycle**. Theo Spring Boot 3.3 Common Application Properties, giá trị mặc định là **30s**. Bài dùng 20s để dễ thử nghiệm, **không** nói 20s là default.

Giá trị có thể viết với hậu tố phù hợp như **ms**, **s**, **m**:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=45000ms
~~~

Giá trị 45.000 milliseconds tương đương 45 giây. Khi cấu hình trên Kubernetes, phải cân đối tổng shutdown budget, không lấy riêng con số này làm tổng thời gian JVM tối đa.

### spring.main.register-shutdown-hook

Spring Boot 3.3 mặc định:

~~~properties
spring.main.register-shutdown-hook=true
~~~

Thông thường không cần khai báo vì default đã là true. Tác dụng là đăng ký shutdown hook để đóng ApplicationContext khi JVM kết thúc theo đường shutdown bình thường. Nếu cấu hình này bị tắt, hoặc tín hiệu không tới đúng JVM, việc đặt **server.shutdown=graceful** chưa đủ để kích hoạt đường dừng bạn mong muốn.

### Properties hoặc YAML

File **src/main/resources/application.properties**:

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

File **src/main/resources/application.yml** tương đương:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Chọn một cách biểu diễn rõ ràng cho demo. Trong production, môi trường, command-line hoặc profile có thể override giá trị trong file. Nếu cần bật qua command line:

~~~bash
java -jar target/graceful-demo-0.0.1-SNAPSHOT.jar --server.shutdown=graceful --spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Tên JAR trong ví dụ đúng với POM ở phần 6; nếu artifact/version khác, thay đường dẫn tương ứng.

## 4. Cơ chế graceful shutdown trong ApplicationContext

Spring Boot thực hiện graceful shutdown như một phần của **ApplicationContext.close()**. Nó nằm ở **giai đoạn dừng sớm của các SmartLifecycle beans**. Mục tiêu là không để request mới tràn vào khi những dependency của chúng chuẩn bị bị đóng.

~~~text
Process nhận SIGTERM hoặc code chủ động đóng context
       |
       v
JVM shutdown hook / ApplicationContext.close()
       |
       v
DefaultLifecycleProcessor điều phối stop theo phase
       |
       +--> Graceful web server shutdown
       |      - Không tiếp nhận request mới theo cơ chế server
       |      - Chờ request đã nhận hoàn tất
       |      - Hết timeout chờ phase thì tiếp tục đường dừng
       |
       +--> Những SmartLifecycle groups khác
       |      - Consumer, scheduler, background workers...
       |
       v
Bean destruction callbacks
  @PreDestroy, DisposableBean.destroy(), custom close()
       |
       v
Đóng resources và JVM exit
~~~

Sơ đồ là mô hình khái niệm. Thứ tự chính xác giữa những infrastructure beans còn phụ thuộc phase, dependency và loại web server. Trong Spring, lifecycle start thường theo phase tăng dần, stop theo phase giảm dần. **Không tự gán một phase tùy ý** cho một tài nguyên đang được HTTP request sử dụng mà chưa hiểu thứ tự shutdown của web server.

### Timeout per phase không phải timeout toàn JVM

Ví dụ ba nhóm khác nhau:

~~~text
Phase HTTP graceful:        chờ tối đa 20 giây
Phase background workers:   chờ tối đa 20 giây
Phase infrastructure:       chờ tối đa 20 giây
Các bean destroy callbacks: thời gian riêng theo implementation
~~~

Nếu từng nhóm đều cần hết ngân sách, tổng shutdown có thể **lớn hơn 20 giây**, thậm chí chưa tính các callback khác. Trái lại, nếu tất cả công việc hoàn thành nhanh, Spring không cần chờ tới hết mỗi timeout.

Với một nhóm có 5 SmartLifecycle beans **cùng phase**, timeout 20s là thời gian chờ của **cả nhóm phase**, không phải 5 lần 20s. Hết timeout cũng không tự ngắt mọi thread hoặc đóng mọi tài nguyên bên ngoài.

### Ngừng HTTP trước khi destroy tài nguyên

Giả sử request đang dùng một HTTP client hoặc database connection pool. Nếu bean phụ thuộc bị đóng quá sớm, request có thể lỗi dù server đang cố drain. Cần đảm bảo:

- Tầng nhận request bắt đầu dừng trước.
- Những resources cần cho request đã nhận vẫn đủ thời gian hoạt động.
- Các tasks có timeouts và cancellation hợp lý.
- Cleanup không bị blocking vô hạn.
- Các SmartLifecycle.stop(Runnable) bất đồng bộ gọi callback **sau khi thật sự dừng**.

Graceful web shutdown không thể cứu một request bị lỗi vì application chủ động hủy dependency quá sớm.

## 5. Khác biệt giữa các embedded web servers

Theo **Spring Boot 3.3 Graceful Shutdown Reference**:

| Server | Cách ngăn request mới | Điều cần kiểm tra khi test |
| --- | --- | --- |
| **Tomcat** | Ngừng chấp nhận tại **network layer** | Client có thể thấy connection refused/reset |
| **Jetty** | Ngừng chấp nhận tại **network layer** | Hành vi mạng tùy thời điểm và connection |
| **Reactor Netty** | Ngừng chấp nhận tại **network layer** | Kiểm tra reactive requests và connection reuse |
| **Undertow** | Có thể tiếp tục nhận kết nối nhưng trả **HTTP 503 Service Unavailable** cho request mới | 503 là hành vi đặc trưng được tài liệu ghi nhận |

**Không mặc định mọi server trả 503**. Với Tomcat, client có thể không nhận được một HTTP response nào vì kết nối mới không được accept. Với persistent connections, HTTP/2 hay reverse proxy, cơ chế xử lý request còn phụ thuộc trạng thái transport hiện tại.

Thời điểm một request được coi là đã nhận rất quan trọng. Một request được client gửi ngay trước SIGTERM nhưng chưa được server accept có thể vẫn bị từ chối. Ngược lại, request gửi ngay sau SIGTERM nhưng trước khi listener hoàn tất bước ngừng accept có thể gặp race và được chấp nhận. Không dùng một phép thử mạng thiếu đồng bộ để khẳng định lỗi framework.

### Streaming và kết nối lâu

SSE, WebSocket, long polling, streaming downloads và các kết nối HTTP/2 dài hạn cần kiểm tra riêng. Graceful shutdown có thể áp dụng cách ngừng nhận request mới, nhưng không bảo đảm mọi kết nối sẽ kết thúc trong deadline. Khi thời gian sống của phiên kết nối dài hơn shutdown budget, cần protocol-specific close signaling, resumability hoặc client reconnect.

## 6. Dự án Maven Java 17+ có thể chạy để kiểm chứng

Phần này cung cấp **POM đầy đủ**, **Java class đầy đủ** và **application.properties** để thử với Spring Boot **3.3.13**, phiên bản thuộc nhánh 3.3. Dự án cố ý dùng **Spring MVC + embedded Tomcat** mặc định để có kết quả quan sát rõ.

### 6.1. Cấu trúc file

~~~text
graceful-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/demo/GracefulShutdownDemoApplication.java
        └── resources/application.properties
~~~

Nếu dùng Spring Initializr, dự án có thêm Maven Wrapper **mvnw** và **mvnw.cmd**. Ví dụ dưới đây cũng chạy được với Maven cài sẵn trên máy.

### 6.2. File pom.xml đầy đủ

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
    <artifactId>graceful-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**Giải thích:** parent quản lý các thư viện thích hợp với Boot 3.3; starter-web mang Spring MVC và Tomcat; plugin Maven tạo executable JAR. Không cần Actuator cho phép thử HTTP cơ bản. POM đã có version và cấu hình Java đủ để build trong một môi trường Maven/JDK 17+ có thể truy cập dependencies.

### 6.3. File application.properties

Tạo **src/main/resources/application.properties**:

~~~properties
server.port=8080

# Spring Boot 3.3 mặc định immediate, nên chọn graceful tường minh:
server.shutdown=graceful

# Chờ mỗi nhóm lifecycle phase tối đa 20 giây:
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Nếu port 8080 đã bị chương trình khác chiếm, đổi server.port và cập nhật URL curl cho khớp. Không thêm nhiều spring profiles khi chưa cần, để phép thử dễ lặp.

### 6.4. File Java đầy đủ

Tạo **src/main/java/com/example/demo/GracefulShutdownDemoApplication.java**:

~~~java
package com.example.demo;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class GracefulShutdownDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                GracefulShutdownDemoApplication.class, args);
    }

    @RestController
    static class WorkController {

        private final AtomicInteger inFlight = new AtomicInteger();

        @GetMapping("/ping")
        public String ping() {
            return "pong";
        }

        @GetMapping("/work")
        public ResponseEntity<String> work(
                @RequestParam(defaultValue = "8") int seconds) {

            if (seconds < 1 || seconds > 30) {
                return ResponseEntity.badRequest()
                        .body("seconds must be between 1 and 30");
            }

            int count = inFlight.incrementAndGet();
            System.out.println("WORK_BEGIN seconds=" + seconds
                    + " active=" + count);

            try {
                TimeUnit.SECONDS.sleep(seconds);
                return ResponseEntity.ok("completed=" + seconds);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return ResponseEntity.status(
                        HttpStatus.SERVICE_UNAVAILABLE)
                        .body("interrupted");
            } finally {
                int remaining = inFlight.decrementAndGet();
                System.out.println("WORK_END seconds=" + seconds
                        + " active=" + remaining);
            }
        }
    }
}
~~~

Đây là **file Java hoàn chỉnh** trong đúng dự án Spring Boot có POM trên.

- Public class, đường dẫn và package khớp.
- WorkController là nested static class có **@RestController**, được component scan phát hiện.
- GET /ping giúp kiểm tra web server hoạt động.
- GET /work nhận query parameter **seconds** và giới hạn từ 1 đến 30.
- **AtomicInteger** cho phép log số request đang thực thi.
- **TimeUnit.SECONDS.sleep** chỉ mô phỏng việc chờ; không phải mẫu nghiệp vụ xử lý database.
- **try/finally** giảm counter và in WORK_END ngay cả khi có interruption.
- Nhánh InterruptedException trả 503 do **chính controller quyết định**, không đại diện cho 503 mà Undertow có thể trả khi shutdown.
- Không sử dụng các Spring API không tồn tại trong Boot 3.3 và không phụ thuộc class từ module chưa khai báo.

### 6.5. Build JAR

~~~bash
java -version
mvn -version
mvn clean package
~~~

Nếu dùng Maven Wrapper:

~~~bash
# Linux/macOS:
./mvnw clean package

# Windows PowerShell hoặc cmd:
# .\mvnw.cmd clean package
~~~

Dựa trên artifactId/version trong POM, file được tạo là:

~~~text
target/graceful-demo-0.0.1-SNAPSHOT.jar
~~~

Nếu dùng project khác, hãy lấy đúng tên executable JAR được build, không đoán từ tài liệu.

### 6.6. Chạy ứng dụng và thử request bình thường

Trong terminal Linux/macOS thứ nhất (**Terminal A**):

~~~bash
java -jar target/graceful-demo-0.0.1-SNAPSHOT.jar &
APP_PID=$!
echo "Java PID=$APP_PID"
~~~

Đợi Spring Boot báo started. Lưu **APP_PID** trong chính terminal A để gửi SIGTERM tới **JVM thật**, không nhầm với PID của Maven khi chạy spring-boot:run.

Trong **Terminal B**:

~~~bash
curl -i http://localhost:8080/ping
~~~

Status/body dự kiến khi server đang chạy bình thường:

~~~text
HTTP/1.1 200
...
pong
~~~

Dấu **...** trong output minh họa nghĩa là đã bỏ qua một số header, không phải dữ liệu literal. Content-Type và headers thực tế phụ thuộc Tomcat/Spring MVC và client.

### 6.7. Bắt đầu một request dài rồi gửi SIGTERM

Trong **Terminal B**:

~~~bash
curl -i "http://localhost:8080/work?seconds=8"
~~~

Lệnh curl sẽ chờ response. Trong **Terminal A**, quan sát log ứng dụng:

~~~text
WORK_BEGIN seconds=8 active=1
~~~

Ngay sau khi thấy dòng này, trong **Terminal A** gửi:

~~~bash
kill -TERM "$APP_PID"
~~~

Trong một lần chạy thành công khi request đã được accept và có đủ thời gian 20s, các dòng do ứng dụng tự in dự kiến:

~~~text
WORK_BEGIN seconds=8 active=1
WORK_END seconds=8 active=0
~~~

Và kết quả chính từ curl có thể là:

~~~text
HTTP/1.1 200
...
completed=8
~~~

Maven, Spring Boot và Tomcat có log khác, và headers có thể thay đổi. Đừng dùng khối output trên như snapshot toàn bộ console. Kết quả **200** được kỳ vọng cho request đã bắt đầu và được xử lý trong deadline, chứ không phải cam kết bất kỳ lần gửi SIGTERM nào cũng luôn 200.

**Phép thử cần xác minh ba điều:** request đã thực sự bắt đầu trước signal; JVM nhận SIGTERM chứ không bị kill cưỡng bức; client nhận response hoàn chỉnh trong shutdown budget.

### 6.8. Request mới trong lúc server đang dừng

Nếu gửi:

~~~bash
curl -i --max-time 3 http://localhost:8080/ping
~~~

sau khi graceful shutdown bắt đầu, embedded Tomcat thường ngừng accept ở network layer. Client có thể gặp connection refused, connection reset hoặc lỗi khác tùy thời điểm/keep-alive.

**Không khẳng định chắc chắn trả HTTP 503 cho Tomcat.** Với Undertow, tài liệu Boot 3.3 mô tả request mới có thể được nhận rồi trả **503 Service Unavailable**. Nếu /ping vô tình được chấp nhận ngay trong race sát SIGTERM, điều đó không tự chứng minh rằng chế độ graceful bị tắt.

### 6.9. Thử trường hợp timeout không đủ

Đổi property:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=3s
~~~

Chạy lại, gửi **/work?seconds=8** và SIGTERM khi request đã bắt đầu.

Những hiện tượng có thể quan sát:

- Spring hết ngân sách đợi web server hoàn thành request.
- Shutdown tiếp tục sang các bước khác.
- Client có thể nhận lỗi connection hoặc response không đầy đủ.
- Thread xử lý request có thể còn chạy thêm tùy server và loại tác vụ.
- JVM có thể mất nhiều hơn 3 giây để thoát vì còn lifecycle phases hoặc cleanup khác.

**Không đưa một stdout hay status code cố định cho kịch bản cố ý vượt timeout.** Timeout theo phase không có nghĩa JVM lập tức interrupt mọi thread khi hết 3 giây.

### 6.10. Chạy trên Windows và IDE

Windows không cung cấp Unix SIGTERM trong terminal PowerShell theo cùng cách. Có thể thử trong Linux container hoặc WSL, hoặc viết integration test chủ động gọi **ConfigurableApplicationContext.close()** trong một chương trình kiểm soát vòng đời.

Lệnh **taskkill /F** là cưỡng bức kết thúc, không phải kịch bản tương đương SIGTERM graceful. Nút Stop của IDE cũng có thể kill process hoặc không gửi tín hiệu phù hợp. Spring Boot 3.3 Reference cảnh báo rằng graceful shutdown trong IDE có thể không hoạt động đúng nếu IDE không gửi một SIGTERM thích hợp.

## 7. Vì sao Spring Boot cần nhận đúng tín hiệu dừng?

Trong Linux, quy trình bình thường:

~~~text
Docker/Kubernetes/systemd gửi SIGTERM
             |
             v
JVM bắt đầu orderly shutdown
             |
             v
Spring Boot shutdown hook đóng ApplicationContext
             |
             v
Graceful web server + các bean lifecycle dừng
~~~

**SIGTERM** yêu cầu dừng lịch sự. **SIGKILL** ép process kết thúc ngay và không cho JVM chạy shutdown hooks. Vì vậy:

~~~bash
kill -TERM "$APP_PID"
~~~

là phép thử graceful hợp lệ, còn:

~~~bash
kill -KILL "$APP_PID"
~~~

là phép thử forced termination. Với SIGKILL, không thể bảo đảm @PreDestroy, SmartLifecycle.stop, request drain hay flush message.

### Docker ENTRYPOINT và PID

Dockerfile ví dụ khi đã có executable JAR:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/graceful-demo-0.0.1-SNAPSHOT.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là file Dockerfile minh họa cho một image có JDK/JRE và JAR phù hợp. **Exec form** giúp JVM nhận signal trực tiếp với tư cách tiến trình chính, tránh shell wrapper không chuyển tiếp SIGTERM.

Nếu một entrypoint script chạy **java -jar** mà không dùng **exec** hoặc không forward signals, JVM có thể không nhận yêu cầu dừng đúng cách. Trong môi trường container cần kiểm tra đúng PID/process tree, chứ không chỉ thấy property trong application.properties.

Ví dụ Docker stop:

~~~bash
docker stop --time 50 graceful-demo-container
~~~

Container tên **graceful-demo-container** chỉ là ví dụ. Docker gửi tín hiệu stop và có thể force kill khi hết thời gian. **50 giây là ngân sách của Docker**, không phải 50 giây riêng cho Spring graceful phase.

## 8. Kubernetes: terminationGracePeriodSeconds và readiness

Một ứng dụng container chạy trong Kubernetes thường có **terminationGracePeriodSeconds**. Nó là **tổng thời gian cho Pod kết thúc lịch sự**, bao gồm preStop (nếu có), tín hiệu tới process và phần chờ trước khi buộc kill. Nó **không đồng nghĩa** spring.lifecycle.timeout-per-shutdown-phase.

Fragment PodSpec:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: app
      image: registry.example.com/graceful-demo:0.0.1
      ports:
        - containerPort: 8080
~~~

Image chỉ minh họa; cần build/push image thật. Đây là fragment trong Pod template, không phải manifest Deployment hoàn chỉnh.

Trong rolling update, việc đưa Pod ra khỏi routing có độ trễ:

1. Pod được đánh dấu terminating.
2. Kubernetes/EndpointSlice/Service phản ánh Pod không còn ready để nhận traffic mới theo cơ chế cụ thể.
3. Ingress và external load balancer phải nhận cập nhật.
4. preStop hook có thể chạy, sau đó SIGTERM tới container.
5. Spring bắt đầu graceful web shutdown.
6. Request in-flight có cơ hội hoàn tất.
7. JVM đóng các nguồn lực khác trong grace budget.

Một load balancer hoặc proxy vẫn có thể giữ connection cũ trong thời gian ngắn. **Readiness và graceful shutdown bổ sung nhau**: readiness giúp điều phối traffic, còn graceful giúp xử lý kết nối/request ở chính instance được yêu cầu dừng.

### Tính tổng shutdown budget

Giả sử:

~~~text
Web graceful phase:  tối đa 20s
Worker drain phase:  tối đa 15s
Resource cleanup:    5s
preStop hook:         5s
Overhead:            thêm một khoảng an toàn
~~~

Trong trường hợp xấu, cần **hơn 45 giây**. Chọn terminationGracePeriodSeconds=20 có thể khiến Pod bị kill trước khi cleanup hoàn tất, dù web graceful phase được cấu hình 20s. Số liệu trong ví dụ chỉ minh họa, phải đo bằng môi trường thật.

**Đừng thêm preStop sleep vô hạn hoặc một khoảng chờ dài không có cơ sở**. preStop cũng tiêu tốn grace period; nếu Kubernetes đã dùng cơ chế endpoint termination/drain phù hợp, sleep không nhất thiết giúp nhiều.

### Readiness probe tùy chọn qua Actuator

Demo phần 6 chỉ dùng starter-web, nên **không tự có** /actuator/health/readiness. Nếu muốn Kubernetes gọi probe tương ứng, thêm dependency vào POM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Đây là **fragment đặt bên trong dependencies**, không phải một POM đầy đủ khác.

Khi cần bật probes ngay cả ngoài môi trường Kubernetes:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
~~~

Sau đó có thể gọi các health groups:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Fragment readinessProbe cho container:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2
~~~

Với management port riêng, cân nhắc:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

để cung cấp thêm **/livez** và **/readyz** trên main HTTP port. Điều này giúp probe kiểm tra đường HTTP gần với traffic thật thay vì chỉ đo một management connector vẫn còn healthy.

**Lưu ý:** khi web server đã ngừng accept, readiness endpoint có thể không truy cập được; không bắt buộc phải quan sát được HTTP 503 mới kết luận web server đã bắt đầu shutdown.

## 9. Graceful shutdown và những tác vụ không thuộc HTTP

**server.shutdown=graceful không tự dừng tất cả phần mềm background đúng nghiệp vụ.** Một vài ví dụ:

| Thành phần | Tính năng graceful HTTP đã đủ chưa? | Cần bổ sung |
| --- | --- | --- |
| Request REST đã nhận | Hỗ trợ trong giới hạn server/deadline | Client timeouts, xử lý lỗi |
| Kafka/RabbitMQ consumer | Chưa | Dừng nhận mới, ack/checkpoint, retry |
| @Scheduled task dài | Chưa | Scheduler lifecycle, cancellation |
| CompletableFuture chạy nền | Chưa | Await/timeout, executor shutdown |
| Database transaction | Có cơ hội hoàn tất nếu request tiếp tục | Transaction timeout/rollback |
| HTTP client outbound | Không tự quản lý tất cả | Connection pool close, connect/read timeout |
| SSE/WebSocket | Phụ thuộc protocol và web server | Draining/reconnect contract |
| Distributed lock/lease | Không | Release/expiry và idempotency |
| Shared cache | Không | Cache flush/invalidation tùy bài toán |
| JVM bị SIGKILL | Không | Durable recovery |

Nếu một request còn chạy trong khi resource cần thiết bị đóng, request có thể thất bại dù web server đang cố chờ. Nên thiết kế thứ tự quiesce → drain → release trong các SmartLifecycle components, và đặt bounded timeouts trên network calls.

## 10. An toàn dữ liệu: graceful không thay thế idempotency

Xét API **POST /payments**:

~~~text
Client gửi payment
    |
Server ghi DB và commit thành công
    |
SIGTERM / network cắt response trước khi client nhận
    |
Client timeout và retry
    |
Có nguy cơ ghi payment trùng nếu không idempotent
~~~

Graceful giảm tần suất những sự cố do shutdown bình thường nhưng không thể bảo đảm mạng, client hoặc JVM không đột ngột lỗi. Với tác vụ có side effects:

- Dùng **idempotency key** và unique constraint khi phù hợp.
- Thiết lập transaction boundary rõ ràng.
- Thiết kế retries an toàn, backoff/jitter và timeout.
- Với DB + message broker, cân nhắc transactional outbox hoặc durable event log.
- Đảm bảo request có thể khôi phục khi worker bị kill ở bất kỳ checkpoint nào.
- Không dựa hoàn toàn vào @PreDestroy để commit dữ liệu nghiệp vụ.

**Một request trả HTTP 200 sau SIGTERM không chứng minh toàn bộ hệ thống có exactly-once processing.** Đó chỉ là bằng chứng cho đường HTTP được thử trong điều kiện cụ thể.

## 11. Những nhầm lẫn phổ biến và cách xử lý

| Nhầm lẫn / lỗi | Giải thích đúng |
| --- | --- |
| "Spring Boot 3.3 tự bật graceful." | Sai; **server.shutdown mặc định immediate** |
| "Đặt shutdown phase timeout là đã bật graceful." | Sai; phải đặt **server.shutdown=graceful** |
| "Timeout 20s thì JVM phải thoát trong 20s." | Sai; timeout áp dụng **mỗi phase**, còn cleanup khác |
| "Mọi HTTP request mới sẽ trả 503." | Sai; Tomcat/Jetty/Netty thường từ chối ở network layer |
| "SIGKILL cũng chạy @PreDestroy." | Sai; kill cưỡng bức bỏ qua Java shutdown hooks |
| "Nhấn Stop trong IDE luôn là graceful." | Không bảo đảm; xem cách IDE dừng JVM |
| "curl tới /ping sau SIGTERM thấy success tức graceful lỗi." | Có thể do timing/race hoặc connection reuse |
| "JVM còn sống sau timeout nghĩa là property không có tác dụng." | Phase wait không tự kill mọi thread hay hủy resource blocking |
| "server.shutdown đóng mọi Kafka consumer." | Chỉ là lựa chọn web server; consumers cần lifecycle riêng |
| "Có readinessProbe là không cần graceful." | Readiness quản lý routing, graceful giúp drain in-flight |
| "Bật graceful là zero downtime." | Còn phụ thuộc replicas, load balancer, client, dependencies |
| "Dùng taskkill /F để thử graceful trên Windows." | Đó là forced kill |
| "Các request rất dài sẽ được chờ vô hạn." | Shutdown phase có deadline |
| "Graceful bảo đảm không có duplicate POST." | Cần idempotency/transaction/retry policy |
| "Actuator readiness có sẵn chỉ với starter-web." | Cần thêm Actuator và cấu hình probes |
| "Nhánh Spring Boot mới nhất có default giống 3.3." | Phải tra tài liệu đúng phiên bản |

## 12. Kiểm thử theo nhiều kịch bản trước khi triển khai

Một bài kiểm thử tốt nên xác minh:

1. **Request ngắn không có shutdown:** GET /work?seconds=2 trả body completed=2.
2. **Request đang chạy, deadline đủ:** GET /work?seconds=8, nhận SIGTERM sau khi WORK_BEGIN; quan sát body completed=8 nếu không có lỗi ngoài.
3. **Deadline quá ngắn:** timeout=3s, request=8s; không gán status cố định, theo dõi connection và log.
4. **Request mới sau tín hiệu:** thử /ping với Tomcat và ghi nhận loại lỗi kết nối.
5. **So sánh immediate:** đổi server.shutdown=immediate và chạy lại cùng phép thử, quan sát sự khác biệt.
6. **Docker:** gửi docker stop, kiểm tra JVM thực nhận SIGTERM.
7. **Kubernetes:** scale down hoặc rollout, đo thời gian unready, graceful drain và Pod exit.
8. **Multiple requests:** một request 3s, một request 12s, budget 20s; kiểm tra cả hai trước exit.
9. **Dependency chậm:** request bị kẹt do DB/API, xem client timeout và resource close.
10. **Forced kill:** SIGKILL để kiểm thử khả năng khôi phục và idempotency.
11. **Long-lived protocol:** SSE/WebSocket/download lớn, xem server-specific connection behavior.
12. **Traffic thực:** đo lỗi 502/503/504 tại ingress, không chỉ log ứng dụng.

### Nên thu thập những số liệu nào?

- Timestamp SIGTERM/ApplicationContext.close bắt đầu.
- In-flight HTTP request count và response durations.
- Thời điểm server ngừng accept request mới.
- Thời gian web graceful phase chờ callback.
- Thời gian stop những SmartLifecycle phases khác.
- Thời gian @PreDestroy và client/executor cleanup.
- Pod readiness, EndpointSlice/Ingress routing events.
- Thời điểm JVM exit và exit code.
- Số client errors, request retries và duplicate business operations.

Log không nên chứa credentials, access tokens hoặc dữ liệu nhạy cảm. Trong demo, counter AtomicInteger chỉ dùng để quan sát chứ không phải hệ thống metric production.

## 13. Bài tập tự kiểm tra

**Câu 1.** Trong Spring Boot 3.3, khi không đặt server.shutdown thì default là gì? Viết hai dòng cấu hình để bật graceful với timeout 15s.

**Câu 2.** Vì sao spring.lifecycle.timeout-per-shutdown-phase=20s không bảo đảm tổng thời gian JVM đóng tối đa 20s?

**Câu 3.** Với Tomcat, request mới sau SIGTERM có buộc phải nhận HTTP 503 không? Vì sao?

**Câu 4.** Với Undertow, điều gì có thể xảy ra cho request mới trong thời gian graceful shutdown?

**Câu 5.** Một HTTP request đã bắt đầu và cần thêm 8 giây; JVM nhận SIGTERM với shutdown phase budget 20s. Graceful shutdown cố đạt điều gì? Điều gì vẫn có thể làm request fail?

**Câu 6.** Tại sao chạy java -jar phù hợp để thử signal hơn việc chỉ lấy PID của mvn spring-boot:run?

**Câu 7.** Vì sao taskkill /F hoặc kill -KILL không chứng minh gì về việc graceful shutdown có hoạt động không?

**Câu 8.** Kubernetes có terminationGracePeriodSeconds=10 nhưng web graceful phase timeout=20s. Có rủi ro gì?

**Câu 9.** ReadinessProbe khác graceful shutdown về trách nhiệm khi rolling deploy như thế nào?

**Câu 10.** Một message consumer vẫn nhận việc trong khi web server đang graceful shutdown. Property web có tự ngăn consumer không?

**Câu 11.** Nếu database đã commit nhưng client không nhận được 200 vì connection lỗi, cơ chế nào giúp tránh tạo dữ liệu trùng sau retry?

**Câu 12.** Một IDE Stop ngay process. Nên thử lại bằng cách nào?

**Đáp án gợi ý:**

1. Immediate; đặt **server.shutdown=graceful** và **spring.lifecycle.timeout-per-shutdown-phase=15s**.
2. Có nhiều phase, destroy callbacks và tài nguyên ngoài web server.
3. Không; Tomcat ngừng accept ở network layer, client có thể gặp connection error.
4. Undertow có thể nhận rồi trả **503 Service Unavailable**.
5. Cố cho request đã được nhận hoàn tất; vẫn có network/client/downstream/app failures.
6. PID Java rõ ràng, Maven có thể là process trung gian.
7. Force kill bỏ qua orderly JVM shutdown hooks.
8. Kubelet có thể force-kill container trước khi drain hoàn tất.
9. Readiness giúp rút traffic khỏi Pod; graceful xử lý in-flight và web server stop.
10. Không; consumer cần lifecycle stop/ack/drain riêng.
11. Idempotency key, unique constraint và transaction/retry policy.
12. Dùng SIGTERM tới JVM thực trên Linux/WSL/container hoặc test gọi context.close có kiểm soát.

## 14. Checklist triển khai Spring Boot 3.3

- [ ] Đã xác nhận đúng **3.3.x** và default **server.shutdown=immediate**?
- [ ] Đã bật **server.shutdown=graceful** tường minh?
- [ ] Shutdown phase timeout đủ cho thời gian request hợp lệ?
- [ ] Không nhầm timeout per phase với deadline toàn JVM?
- [ ] Embedded web server đang dùng là Tomcat, Jetty, Undertow hay Reactor Netty?
- [ ] Test đúng hành vi network-layer reject hay 503 theo server?
- [ ] JVM nhận SIGTERM/ApplicationContext.close, không bị IDE/Docker wrapper kill ngay?
- [ ] **spring.main.register-shutdown-hook** không bị tắt ngoài chủ ý?
- [ ] Docker ENTRYPOINT chuyển tín hiệu trực tiếp tới Java?
- [ ] Kubernetes termination grace đủ cho preStop + lifecycle + cleanup?
- [ ] Có readiness/probe/load balancer drain phù hợp?
- [ ] HTTP clients/proxies có timeout tương thích với long requests?
- [ ] Background consumers, executors và schedulers có stop riêng?
- [ ] Database/business operations có idempotency/recovery?
- [ ] Đã test SIGTERM và forced termination trong staging?
- [ ] Có metrics in-flight requests, shutdown latency và client errors?
- [ ] Không hứa zero downtime chỉ nhờ một property?

## 15. Kết luận và tài liệu tham khảo

Với Spring Boot 3.3, cấu hình trọng tâm là:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

**Spring Boot 3.3 mặc định immediate**, vì vậy cần chủ động bật graceful. Spring ngừng tiếp nhận request HTTP mới theo cơ chế của embedded server và dành thời gian cho request đang xử lý hoàn tất trong quá trình dừng ApplicationContext. Thời gian chờ thuộc **SmartLifecycle shutdown phase**, không phải bảo đảm tổng thời gian mọi tài nguyên đều dừng.

Để giảm lỗi khi triển khai thực tế, phải phối hợp với **SIGTERM đúng JVM**, **readiness/load balancer draining**, **Kubernetes terminationGracePeriodSeconds** và các chính sách **timeout, retry, idempotency**. Không phải mọi web server đều trả 503 cho request mới khi ngừng nhận kết nối.

### Nguồn chính thức, đúng nhánh 3.3

1. Spring Boot 3.3 — Graceful Shutdown, server hỗ trợ và cấu hình: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
2. Spring Boot 3.3 — Common Application Properties, server.shutdown default immediate và lifecycle timeout default 30s: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
3. Spring Boot 3.3 — SpringApplication, startup/shutdown và availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
4. Spring Boot 3.3 — Actuator health/readiness probes: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
5. Spring Framework 6.1 — Lifecycle/SmartLifecycle: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-nature.html
6. Kubernetes — Pod termination: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination

**Phiên bản của ví dụ:** Java 17+, Spring Boot 3.3.13, Spring MVC/Tomcat mặc định. Khi nâng cấp lên Boot 3.4+, kiểm tra lại defaults và semantics trên tài liệu phiên bản mục tiêu, thay vì sao chép nguyên giả định của 3.3.