# Ứng xử với yêu cầu đang xử lý và yêu cầu mới ở mức vòng đời máy chủ Spring Boot

## 1. Bài toán: server đang phục vụ HTTP thì được yêu cầu dừng

Một instance Spring Boot đang nhận traffic, có request A đã vào controller và đang gọi database, trong khi request B vừa đến. Khi process nhận **SIGTERM**, ứng dụng phải giải quyết hai vấn đề khác nhau:

1. **Request đã được tiếp nhận (in-flight):** cố cho chúng hoàn tất trong một khoảng chờ có giới hạn.
2. **Request mới:** ngăn chúng bắt đầu thêm công việc trên instance chuẩn bị đóng.

Đây chính là mục đích của **graceful shutdown** ở mức vòng đời embedded web server. Nó giúp giảm các request bị cắt giữa chừng khi deploy, scale down hoặc restart, đồng thời không để server tiếp tục nhận vô hạn công việc mới.

~~~text
                 thời gian ---------------------------------->

Server RUNNING                   Server DRAINING          STOPPED
     |                                 |                      |
A ---+---- HTTP request đang xử lý ----+---- hoàn tất? --------+
     |                                 |    trong deadline
B ---+---- request kết thúc            |
     |                                 |
C ------------------------------------+---- request mới:
                                           bị chặn / từ chối
                                           theo kiểu server

               SIGTERM / ApplicationContext.close()
                                 |
                                 v
                   Graceful shutdown bắt đầu
~~~

**In-flight** không đồng nghĩa request đã được client gửi nhưng server chưa nhận; ở đây là request đã được web server tiếp nhận và đang được xử lý. Những request đến sát thời điểm shutdown có thể rơi vào một **race condition**, nên cần xác định chúng thuộc nhóm nào bằng mốc chấp nhận ở server, không chỉ bằng thời gian client bấm gửi.

**Kết luận sơ bộ:** graceful shutdown là **ngừng nhận mới + chờ đang xử lý trong thời hạn**; không phải cam kết mọi request đều thành công hoặc mọi client sẽ nhận HTTP 503.

Bài dùng **Spring Boot 3.3.13, Spring Framework 6.1 và Java 17+**. Phần ví dụ chạy bằng Spring MVC/Tomcat nhúng, sau đó so sánh với Jetty, Undertow và Reactor Netty.

## 2. Immediate shutdown và graceful shutdown khác nhau ở đâu?

### 2.1. Immediate: không chờ request cũ theo cơ chế drain

Trong **Spring Boot 3.3.x**, giá trị mặc định của **server.shutdown** là **immediate**. Khi context đóng, server được yêu cầu dừng mà không thực hiện pha chờ HTTP request in-flight theo cơ chế graceful của Boot.

~~~properties
server.shutdown=immediate
~~~

Điều này có thể làm request còn hoạt động mất kết nối hoặc thất bại giữa chừng. Nhưng không nên khẳng định mọi request đều chắc chắn thất bại: một request có thể đã hoàn tất trước khi hành động stop có hiệu lực.

### 2.2. Graceful: từ chối mới, chờ cũ

Để bật graceful shutdown trên **Boot 3.3.x**, cấu hình tường minh:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Spring Boot khởi động pha graceful khi **ApplicationContext.close()** được thực hiện và server vẫn đang hoạt động. Các request in-flight được cho cơ hội hoàn tất; request mới không còn được phục vụ bình thường.

**Điểm khác phiên bản:** từ **Spring Boot 3.4**, graceful shutdown đã trở thành mặc định. Khi học hoặc vận hành ứng dụng Boot **3.3**, không được suy diễn từ docs của Boot 3.4/3.5/4.x rằng graceful luôn bật sẵn.

### 2.3. Timeout là giới hạn, không phải bắt buộc ngủ đúng 20 giây

**spring.lifecycle.timeout-per-shutdown-phase=20s** đặt khoảng chờ tối đa **cho mỗi pha dừng của SmartLifecycle beans**.

- Nếu các request kết thúc sớm, server có thể drain xong trước 20 giây.
- Nếu một request kéo dài vượt hạn, shutdown sẽ tiếp diễn; request chưa xong có thể bị cắt hoặc thất bại.
- Không có bảo đảm một response HTTP cụ thể cho request vượt hạn.
- Đây **không phải tổng shutdown timeout** của mọi lifecycle phase, callback và container.
- Đây cũng **không phải timeout của HTTP client**, reverse proxy, database hoặc controller.

Một ứng dụng nhiều pha dừng có thể cần tổng thời gian **lớn hơn một timeout-per-phase**, cộng thời gian preStop và cleanup. Cần so sánh toàn bộ ngân sách với cấu hình của Docker/Kubernetes.

## 3. Vị trí của graceful shutdown trong ApplicationContext lifecycle

Spring Boot điều khiển embedded server thông qua **WebServer** abstraction và quản lý shutdown trong quá trình đóng **ApplicationContext**.

Với đường dừng JVM bình thường:

~~~text
SIGTERM / context.close()
     |
     v
JVM shutdown hook (nếu dừng qua shutdown của JVM)
     |
     v
ApplicationContext.close()
     |
     +-- ContextClosedEvent
     |
     +-- LifecycleProcessor / SmartLifecycle stop
     |      |
     |      +-- Pha sớm nhất: graceful web-server shutdown
     |      |       +-- ngăn tiếp nhận HTTP mới
     |      |       +-- chờ in-flight trong giới hạn
     |      |
     |      +-- các SmartLifecycle phases tiếp theo
     |
     +-- destroy beans / @PreDestroy / destroy methods
     |
     v
Tài nguyên được giải phóng và process có thể kết thúc
~~~

Theo tài liệu Spring Boot 3.3, graceful web-server shutdown diễn ra **ở pha sớm nhất của việc dừng các SmartLifecycle beans**. Điều đó quan trọng vì nhiều HTTP request còn xử lý sẽ cần các service, datasource, repository và các tài nguyên bean khác.

Nếu đóng connection pool hoặc executor quá sớm, request cũ có thể thất bại dù server vẫn đang cố đợi nó. Vì vậy **lifecycle của các dependency** và **lifecycle của embedded server** phải phối hợp với nhau.

### 3.1. WebServer API và callback kết quả

Spring Boot 3.3 có API ở mức server:

~~~java
void shutDownGracefully(GracefulShutdownCallback callback);
void stop();
~~~

Đây là các chữ ký API minh họa, **không phải một chương trình Java độc lập**.

**shutDownGracefully(...)** yêu cầu server bắt đầu một lần thử shutdown mềm và gọi callback khi kết thúc. Enum **GracefulShutdownResult** của Spring Boot có:

| Giá trị | Ý nghĩa |
| --- | --- |
| **IDLE** | Không còn active request ở cuối lần thử graceful |
| **REQUESTS_ACTIVE** | Vẫn còn request đang hoạt động khi hết grace period |
| **IMMEDIATE** | Dừng ngay, không thử chờ active request |

**Đây là kết quả của quá trình shutdown ở tầng server, không phải HTTP response status gửi cho client**. Không đồng nhất **REQUESTS_ACTIVE** với 503 hoặc **IDLE** với mọi @Async job đã hoàn tất.

Trong ứng dụng Spring Boot bình thường **không nên tạo một HTTP endpoint công khai để gọi thẳng WebServer.stop() hoặc shutDownGracefully()**. Dùng ApplicationContext lifecycle và tín hiệu dừng chuẩn để các thành phần khác cũng được dừng đúng.

### 3.2. ApplicationReadyEvent không phải shutdown event

**ApplicationReadyEvent** diễn ra sau khi startup bình thường đã hoàn tất. Nó không phải sự kiện “server đã từ chối request mới”. Khi ứng dụng đang dừng, tín hiệu liên quan là **ContextClosedEvent** và trạng thái availability/lifecycle.

Đừng viết logic shutdown dựa vào việc ApplicationReadyEvent có từng được phát hay không. Startup readiness và shutdown draining là hai chặng khác nhau.

### 3.3. Không phải mọi cách kill process đều có graceful shutdown

- **SIGTERM** trong điều kiện JVM được phép shutdown bình thường: shutdown hook có cơ hội đóng context.
- **context.close()** trong code/lifecycle test: chủ động đóng Spring context theo cơ chế container.
- **Ctrl+C** ở console thích hợp: thường dẫn tới shutdown bình thường, nhưng tùy môi trường.
- **SIGKILL**, crash JVM, mất điện: không cho JVM hoàn tất shutdown hooks.
- **IDE Stop/Terminate**: có thể dùng hard stop, tùy IDE và cấu hình.

Vì vậy một thử nghiệm gửi **SIGKILL** rồi thấy request bị cắt **không chứng minh Spring graceful shutdown bị lỗi**.

## 4. Cách server xử lý request đã được tiếp nhận

Request in-flight có thể đang ở bất kỳ giai đoạn nào:

~~~text
TCP đã accept
    |
    +-- HTTP request được parse
    +-- Servlet filter / Security
    +-- DispatcherServlet / HandlerMapping
    +-- Controller -> Service -> Repository
    +-- Gọi database hoặc external HTTP API
    +-- Serialize response
    +-- Write/flush HTTP response
~~~

Khi graceful bắt đầu, server **cố cho request thuộc nhóm đang hoạt động hoàn thành**, đồng thời ngăn thêm request mới. Điều này giảm xác suất một request đang ghi transaction hoặc tạo response bị cắt ngang chỉ vì instance đang deploy.

Nhưng phải phân biệt các nguyên nhân thất bại:

- **Timeout ở tầng Spring web-server graceful**: server chỉ đợi tới thời hạn.
- **HTTP client timeout**: caller có thể ngừng chờ sớm hơn.
- **Reverse proxy/gateway timeout**: ingress có thể trả 504 ngay cả khi server vẫn đang xử lý.
- **Lỗi nghiệp vụ**: database rollback, external API thất bại, validation lỗi.
- **Mất kết nối giữa client và server**.
- **Bean/executor bị đóng sai thứ tự** trong application lifecycle.

Graceful shutdown **không biến một operation lỗi thành operation thành công**.

### 4.1. Trường hợp request hoàn tất trong thời hạn

Giả sử request A bắt đầu ở giây 0, dự kiến chạy sáu giây. SIGTERM đến ở giây 2. Grace period là 15 giây.

~~~text
t=0                  t=2                   t=6
 |                    |                     |
 +--- A đang chạy ----+--- A tiếp tục -------+--> response
                      |
                    SIGTERM
                  graceful drain
~~~

Trong điều kiện không có lỗi khác, request A có cơ hội hoàn tất và trả kết quả bình thường. Server có thể dừng ngay sau khi hết in-flight, không cần chờ đủ 15 giây.

### 4.2. Trường hợp request lâu hơn deadline

Nếu A còn 40 giây nhưng shutdown grace chỉ 10 giây, server **không cam kết chờ đủ 40 giây**. Sau khi hết giới hạn, server/container có thể đóng connection; client có thể gặp EOF, reset, timeout hoặc response lỗi từ proxy. Không tự bịa một mã HTTP cố định cho tình huống này.

Cần thiết kế request timeout thực tế theo SLO, xem xét p95/p99 latency và tránh kéo dài vô hạn vì chờ một remote service không có timeout.

### 4.3. Request đến sát ranh giới: race condition

~~~text
t0 client bắt đầu gửi request B
t1 connector có thể accept socket/headers
t2 JVM bắt đầu đóng context
t3 server chuyển sang graceful draining
t4 B đã là in-flight hay bị từ chối?
~~~

Câu trả lời phụ thuộc chính xác B đã vào server ở mốc nào, loại connection và implementation. **Không thể quyết định chỉ bằng timestamp ở client**. Trong test nghiêm túc, ghi log marker khi controller bắt đầu hoặc dùng barrier/latch để chắc chắn request A đã active trước khi phát SIGTERM.

## 5. Request mới: sự khác biệt giữa bốn embedded server

Spring Boot 3.3 hỗ trợ graceful shutdown với cả **Servlet** và **reactive web applications** trên bốn embedded servers: **Tomcat, Jetty, Reactor Netty và Undertow**.

| Embedded server | Cách xử lý request mới trong graceful drain |
| --- | --- |
| **Tomcat** | Ngừng tiếp nhận request mới tại network layer |
| **Jetty** | Ngừng tiếp nhận request mới tại network layer |
| **Reactor Netty** | Ngừng tiếp nhận request mới tại network layer |
| **Undertow** | Có thể tiếp nhận connection mới nhưng phản hồi ngay **503 Service Unavailable** |

**Không phải cứ shutdown là server trả HTTP 503.** Đối với Tomcat, Jetty và Reactor Netty, request mới có thể không nhận được **bất kỳ HTTP response nào từ ứng dụng** vì socket bị từ chối/đóng ở tầng mạng.

### 5.1. Vì sao client có thể nhận 502, 503 hoặc 504?

Nếu request đi qua:

~~~text
Client -> Ingress/Load Balancer -> Spring Boot instance
~~~

có thể xảy ra:

- **Connection refused/reset** ở backend: proxy tự tạo 502 hoặc 503.
- **Backend không phản hồi trước deadline**: proxy tạo 504.
- **Proxy retry trên replica khác**: client vẫn nhận HTTP 200.
- **Undertow trực tiếp trả 503** cho request mới.
- **Client-side timeout**: không có HTTP status vì không nhận được response.

Khi debug, cần xác định **status được tạo bởi ứng dụng, embedded server, proxy hay client**. Không dùng số 503 làm bằng chứng duy nhất rằng server graceful hoạt động đúng.

### 5.2. HTTP keep-alive và persistent connections

HTTP/1.1 keep-alive có thể tái sử dụng connection; HTTP/2 có thể có nhiều streams trên cùng connection. Boot 3.3 lưu ý rằng **persistent connections ảnh hưởng cách từ chối request mới**.

Một request đã đi vào server từ trước có thể được tiếp tục xử lý trong khi **request mới trên connection đã có** bị từ chối/đóng theo cách server quyết định. Không khẳng định tất cả socket sẽ bị đóng ngay theo cùng một kiểu.

Với HTTP/2, có thể xuất hiện hành vi đóng stream hoặc GOAWAY tùy server. Hãy kiểm tra thật với HTTP version và proxy đang dùng; đừng lấy kết quả một lần **curl HTTP/1.1** làm hợp đồng cho mọi protocol.

### 5.3. Ngừng nhận mới ở server khác với ngừng gửi mới ở load balancer

Một instance đang draining từ chối request mới là đúng; ở cấp hệ thống, **load balancer nên dừng định tuyến đến instance đó** và chuyển traffic sang replica khỏe khác.

Nếu B nhận HTTP 200 thông qua ingress sau khi A nhận SIGTERM, có thể B thực tế đã được chuyển sang **instance C**. Cần instance ID, request ID hoặc log backend để phân biệt.

## 6. Cấu hình Boot 3.3 có thể dùng ngay

File **src/main/resources/application.properties**:

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=15s
~~~

Hoặc file YAML thay thế:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 15s
~~~

Không cần khai báo cả hai file. Giá trị có thể được ghi đè bằng CLI/environment theo precedence của Spring Boot.

**Chú ý đơn vị:** viết **15s** thay vì chỉ ghi **15** rồi mặc định đó là giây. Đây là một Spring duration property.

### 6.1. Một shutdown phase không phải toàn bộ shutdown

Các khoản có thể tiêu tốn thời gian:

~~~text
Thời gian thay đổi routing / preStop
+ thời gian server chờ HTTP in-flight (web-server stop phase)
+ các SmartLifecycle phases khác
+ cleanup / destroy callbacks
+ phần dự phòng cho OS, JVM, network
~~~

Đây là mô hình lập ngân sách, không phải công thức cố định bắt buộc mọi giai đoạn dùng hết thời gian. **spring.lifecycle.timeout-per-shutdown-phase** áp dụng theo pha; một shutdown nhiều pha có thể lâu hơn một giá trị đơn lẻ.

### 6.2. Chọn graceful timeout dựa trên gì?

Đo ít nhất:

1. Thời gian xử lý p95/p99 của endpoint.
2. Số lượng và độ dài request đang chạy khi scale down.
3. HTTP client timeout và ingress/gateway timeout.
4. Thời gian chạy của request có tải file, streaming hoặc gọi backend nặng.
5. Tốc độ ngừng routing của load balancer.
6. Thời gian stop executor/consumers và cleanup.
7. Tổng **terminationGracePeriodSeconds** ở Kubernetes.

Không chọn thời gian vô hạn để che việc request đang chờ một database/backend không có timeout.

## 7. Ví dụ Java 17+ chạy được: Tomcat drain request đang xử lý

Dự án sau tạo một Spring MVC server với:

- **GET /ping** trả về ngay.
- **GET /work?delayMs=8000** mô phỏng một request cần tám giây.
- **server.shutdown=graceful** và grace period 15 giây.
- Actuator readiness/liveness để quan sát trước shutdown.

**Thread.sleep chỉ dùng để mô phỏng thời gian xử lý trong bài học, không phải thiết kế production controller.**

### 7.1. Cấu trúc

~~~text
graceful-request-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/drain/GracefulRequestApplication.java
  src/test/java/com/example/drain/GracefulRequestApplicationTest.java
~~~

### 7.2. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>graceful-request-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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
            <artifactId>spring-boot-starter-actuator</artifactId>
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

### 7.3. application.properties

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=15s

management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Với Actuator, hai property probes cho phép truy cập **/readyz** và **/livez** trên cổng HTTP chính theo cơ chế Spring Boot 3.3. Khi server bắt đầu từ chối new requests, probe HTTP có thể không kết nối được; không dựa vào probe trong grace để luôn có JSON phản ánh state nội bộ.

### 7.4. File Java hoàn chỉnh

**src/main/java/com/example/drain/GracefulRequestApplication.java**:

~~~java
package com.example.drain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class GracefulRequestApplication {

    public static void main(String[] args) {
        SpringApplication.run(GracefulRequestApplication.class, args);
    }
}

@RestController
class DemoController {

    @GetMapping("/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/work")
    String work(
            @RequestParam(name = "delayMs", defaultValue = "5000")
            long delayMs) {

        if (delayMs < 0 || delayMs > 20000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "delayMs must be between 0 and 20000");
        }

        System.out.println("BEGIN work delayMs=" + delayMs);

        try {
            Thread.sleep(delayMs);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            System.out.println("INTERRUPTED work delayMs=" + delayMs);
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "work interrupted",
                    ex);
        }

        System.out.println("END work delayMs=" + delayMs);
        return "completed:" + delayMs;
    }
}
~~~

**Tại sao mã hợp lệ?**

- Một tệp Java có một public top-level class **GracefulRequestApplication** và một package-private class **DemoController** cùng package.
- Spring Boot component scan tìm thấy **@RestController**.
- **spring-boot-starter-web** chọn Spring MVC và Tomcat nhúng theo mặc định.
- **@RequestParam** chỉ rõ tên **delayMs**, không phụ thuộc compiler giữ tên tham số.
- Delay được giới hạn từ 0 đến 20.000 ms để tránh nhận độ dài tùy ý trong demo.
- Controller in dòng BEGIN trước khi sleep để test biết request đã thực sự vào handler.
- Khi hoàn tất, controller in END và trả body **completed:8000** cho delay 8 giây.
- Khi thread bị interrupt, code bảo toàn interrupt flag và trả lỗi. **Không giả định Tomcat luôn interrupt request worker lúc graceful timeout**; block catch chỉ là xử lý phòng trường hợp đó xảy ra.

### 7.5. Build và chạy

Từ thư mục dự án:

~~~bash
mvn -q -DskipTests package
java -jar target/graceful-request-demo-1.0.0.jar
~~~

Giữ terminal này mở, gọi là **Terminal A**.

Từ Terminal B:

~~~bash
curl -i http://localhost:8080/ping
~~~

Body của HTTP 200 là:

~~~text
pong
~~~

HTTP headers có thể thay đổi, nên không assert nguyên văn toàn bộ response headers.

### 7.6. Tạo in-flight request A

Ở Terminal B, chạy:

~~~bash
curl -v --no-buffer "http://localhost:8080/work?delayMs=8000"
~~~

Terminal A sẽ in:

~~~text
BEGIN work delayMs=8000
~~~

**Chỉ gửi tín hiệu dừng sau khi thấy BEGIN.** Nếu bạn gửi SIGTERM trước khi request thật sự vào controller, bạn đang thử một **new request bị từ chối**, không phải một **in-flight request được drain**.

### 7.7. Gửi SIGTERM trong khi A đang chạy

Trên Linux/macOS, tại Terminal C dùng:

~~~bash
jps -l
~~~

Xác định đúng PID của tiến trình JAR, rồi:

~~~bash
kill -TERM <java_pid>
~~~

**<java_pid> là placeholder phải thay bằng PID thật.** Chỉ gửi tín hiệu cho process demo, không gửi nhầm PID ứng dụng khác. Trong một terminal trực tiếp, Ctrl+C cũng có thể kích hoạt shutdown bình thường nếu console/JVM nhận tín hiệu phù hợp.

**Không dùng kill -9 để thử graceful.** SIGKILL cắt mất cơ hội thực thi shutdown hooks.

Trên Windows, **Stop-Process** có thể kết thúc process theo cơ chế terminate không tương đương SIGTERM POSIX; tốt nhất test trong Linux/container hoặc một tích hợp có khả năng gọi **ApplicationContext.close()** được kiểm soát.

### 7.8. Request A sẽ thế nào?

Với request tám giây và grace 15 giây, nếu SIGTERM đến sau dòng BEGIN và không có lỗi khác, request A thường có cơ hội hoàn tất.

Terminal A có dòng:

~~~text
END work delayMs=8000
~~~

Terminal B nhận body:

~~~text
completed:8000
~~~

và HTTP 200. Logs của Spring Boot/Tomcat có thể xen giữa BEGIN và END; không có một trình tự stdout duy nhất cho mọi môi trường.

**Không bảo đảm tuyệt đối HTTP 200:** request vẫn có thể lỗi do client timeout, proxy, network hoặc business logic. Demo dùng Thread.sleep để giảm những nguồn lỗi phụ này và quan sát riêng behavior server.

### 7.9. Request B mới trong lúc draining

Sau khi SIGTERM đã kích hoạt graceful drain, thử tại Terminal C:

~~~bash
curl -v --max-time 3 http://localhost:8080/ping
~~~

Với **Tomcat**, request mới thường không được tiếp nhận tại network layer. Client có thể thấy lỗi kết nối, reset/EOF hoặc hành vi tùy thời điểm. **Không assert HTTP 503 từ Tomcat.** Với **Undertow**, docs Boot 3.3 mô tả hành vi trả 503 cho new requests.

Nếu request đã được server nhận **trước mốc drain**, nó có thể vẫn hoàn tất; nếu process đã kết thúc, bạn chỉ thấy server không còn chạy. Để phân tích đúng, cần ghi timestamps/instance IDs và biết thời điểm drain có hiệu lực.

### 7.10. Request kéo dài quá grace

Chạy lại ứng dụng, tạo:

~~~bash
curl -v --no-buffer "http://localhost:8080/work?delayMs=20000"
~~~

Đợi BEGIN, rồi gửi SIGTERM. Grace period được cấu hình là 15 giây. Lần này không có cam kết request 20 giây sẽ được server chờ đủ. Client có thể gặp connection closure, timeout hoặc một phản hồi không hoàn chỉnh.

**Không đưa một status code cụ thể vào expected output của case quá deadline.** Tình trạng thực tế phụ thuộc server, thread, TCP socket, proxy và thời điểm kết nối bị đóng.

## 8. Kiểm thử JUnit và kiểm thử process-level

### 8.1. Kiểm tra endpoint hoạt động trước shutdown

File **src/test/java/com/example/drain/GracefulRequestApplicationTest.java**:

~~~java
package com.example.drain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GracefulRequestApplicationTest {

    @Autowired
    private TestRestTemplate client;

    @Test
    void pingReturnsPong() {
        String body = client.getForObject("/ping", String.class);
        assertEquals("pong", body);
    }

    @Test
    void completedWorkReturnsItsDelay() {
        String body = client.getForObject(
                "/work?delayMs=0",
                String.class);
        assertEquals("completed:0", body);
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Test dùng RANDOM_PORT để không chiếm cổng 8080 của ứng dụng khác. **Nó xác nhận controller/routing hoạt động**, chưa xác nhận server drain. Không được lấy một **@SpringBootTest contextLoads** hoặc unit test gọi controller trực tiếp làm bằng chứng graceful shutdown đúng.

### 8.2. Process-level smoke test mới xác minh hành vi shutdown

Một test đầy đủ cần:

1. Build JAR và khởi động nó trong một child JVM/process riêng.
2. Đợi server ready.
3. Gửi request A dài, **đợi log/marker xác nhận đã vào controller**.
4. Gửi SIGTERM hoặc gọi close context theo phương pháp đã kiểm soát.
5. Gửi request B mới sau khi drain có hiệu lực; ghi lại cả HTTP status **lẫn lỗi transport**.
6. Xác minh A hoàn tất nếu thời gian còn lại ngắn hơn grace, trong điều kiện không có lỗi khác.
7. Đo tổng thời gian từ signal đến process exit.
8. Dọn dẹp child process bằng deadline; không để test treo.
9. So sánh với immediate shutdown và với request dài hơn grace.

Có thể dùng **ProcessBuilder**, **Process.isAlive()**, **Process.waitFor(timeout, TimeUnit.SECONDS)** trong Java để quản lý child process. Tuy nhiên **Process.destroy()** có semantics khác nhau theo OS; nếu cần kiểm tra chính xác POSIX SIGTERM, chạy trên Linux/container và gửi đúng tín hiệu. Không biến một test phụ thuộc Thread.sleep mù quáng thành bằng chứng request đã active.

### 8.3. Test trực tiếp instance và test qua load balancer là hai bài khác nhau

**Test embedded server:** gửi request trực tiếp đến instance A, quan sát A từ chối new request và drain in-flight.

**Test hệ thống phân tán:** gửi qua ingress/load balancer, quan sát B được chuyển sang instance còn ready. Nếu B nhận 200, có thể là từ instance B khác; đừng kết luận instance A đã chấp nhận new requests.

## 9. Readiness, liveness và trạng thái nhận traffic

Spring Boot có **ApplicationAvailability** với **LivenessState** và **ReadinessState**. Ở trạng thái chạy bình thường, readiness thường là **ACCEPTING_TRAFFIC**.

Tài liệu Actuator Spring Boot mô tả:

| Mốc | ReadinessState | Hành vi HTTP server |
| --- | --- | --- |
| Chạy bình thường | **ACCEPTING_TRAFFIC** | Nhận request |
| Graceful shutdown | **REFUSING_TRAFFIC** | Từ chối new requests, drain in-flight |
| Shutdown xong | Không còn endpoint phục vụ | Server đã dừng |

**Đừng cho rằng GET /actuator/health/readiness chắc chắn trả một JSON REFUSING_TRAFFIC khi graceful đã bắt đầu.** Khi HTTP connector từ chối new requests, probe không nhất thiết truy cập được server. **Trạng thái availability nội bộ và khả năng đọc trạng thái qua HTTP là hai khái niệm khác nhau.**

### 9.1. Readiness điều phối traffic, graceful bảo vệ in-flight

~~~text
Kubernetes / Ingress / Load Balancer
        |
        +-- ngừng định tuyến request mới vào Pod A
        |
        v
Pod A / Spring Boot
        |
        +-- graceful stop:
                +-- ngừng nhận new request ở server
                +-- chờ in-flight request cũ trong budget
~~~

Readiness không tự bảo đảm load balancer cập nhật ngay lập tức; trong một khoảng trễ, request mới vẫn có thể tới Pod A. Vì thế **server-side refusal** và **routing-level removal** bổ trợ nhau.

### 9.2. Probes trên cổng HTTP chính

Với Actuator, Boot 3.3 có thể expose health probes:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Thao tác này tạo **/livez** và **/readyz** trên cổng ứng dụng. Nếu probes chỉ chạy trên một management port riêng, management context có thể vẫn phản hồi khỏe trong khi cổng HTTP ứng dụng chính đã gặp vấn đề. Đặt probes trên cổng chính giúp kiểm tra đường hạ tầng gần với traffic thực hơn.

Không công khai toàn bộ Actuator endpoint nhạy cảm. Riêng shutdown endpoint không nên mở cho Internet; nó là một luồng điều khiển có tác động lớn.

## 10. Kubernetes: SIGTERM, preStop và terminationGracePeriodSeconds

Một rollout/scale-down thường có các bước:

~~~text
Pod bắt đầu terminating
     |
     +-- Endpoint/routing được cập nhật (không tức thời)
     +-- preStop hook nếu có
     +-- kubelet gửi SIGTERM
     |       |
     |       +-- JVM shutdown hook
     |       +-- Spring context close
     |       +-- graceful web server drain
     |
     +-- hết tổng termination grace:
             kubelet có thể gửi SIGKILL
~~~

**Kubernetes terminationGracePeriodSeconds là tổng thời gian tối đa được cấp cho quá trình termination**, bao gồm cả thời gian preStop. Không có mặc định thêm một ngân sách đầy đủ thứ hai sau preStop.

Snippet PodSpec minh họa:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: app
      image: example/graceful-request-demo:1.0.0
      ports:
        - containerPort: 8080
      readinessProbe:
        httpGet:
          path: /readyz
          port: 8080
        periodSeconds: 3
        timeoutSeconds: 2
      lifecycle:
        preStop:
          exec:
            command:
              - /bin/sh
              - -c
              - sleep 5
~~~

**Đây là một PodSpec snippet**, không phải Deployment manifest đầy đủ. Image phải thực sự có **/bin/sh** và **sleep**; với distroless image, snippet này không chạy nếu thiếu shell.

### 10.1. preStop sleep có thay thế graceful không?

Không. PreStop có thể được dùng để chờ thông tin loại Pod ra khỏi routing lan truyền, nhưng trong thời gian nó sleep, server **có thể vẫn tiếp nhận request** trước khi SIGTERM được gửi. Sau đó Boot vẫn phải graceful drain.

Một sleep cố định **không bảo đảm** toàn bộ load balancer đều đã cập nhật. Cần chọn thời gian theo thực nghiệm hoặc dùng cơ chế điều phối có tín hiệu tốt hơn.

### 10.2. Tính ngân sách hợp lý

Nếu có:

- preStop sleep.
- graceful web-server phase.
- các SmartLifecycle phases khác.
- executor shutdown/bean destruction.
- thời gian trễ tín hiệu hoặc container scheduling.

thì tổng thời gian có thể vượt một con số **timeout-per-shutdown-phase**. Đừng cấu hình Spring chờ 60 giây trong khi Kubernetes chỉ cho 30 giây tính từ lúc bắt đầu terminating.

### 10.3. Tín hiệu phải đến được JVM

Nếu container chạy:

~~~sh
sh -c "java -jar app.jar"
~~~

cần kiểm tra shell có chuyển tiếp tín hiệu và PID 1 có phản ứng đúng hay không. Một lựa chọn thường phù hợp là:

~~~sh
exec java -jar app.jar
~~~

để JVM thay thế shell process khi chạy script. Không làm giả định rằng mọi Docker image/entrypoint luôn tự forward SIGTERM đúng.

## 11. Long-lived request: WebSocket, SSE, HTTP/2 và MVC async

### 11.1. WebSocket

Sau khi HTTP upgrade sang WebSocket, kết nối có thể duy trì trong hàng giờ. Không tự cho rằng **server.shutdown=graceful** sẽ gửi application-specific close frame, lưu session state hoặc buộc mọi client reconnect đúng cách.

Với WebSocket, ứng dụng có thể cần:

- Ngừng chấp nhận session mới.
- Thông báo sắp dừng bằng message phù hợp.
- Đóng session theo protocol.
- Cho client reconnect tới instance khác.
- Lưu trạng thái cần phục hồi.

Kiểm thử bằng đúng server và implementation WebSocket đang dùng.

### 11.2. Server-Sent Events (SSE) và streaming response

SSE có thể giữ response mở vô hạn. Server không thể chờ mãi nếu grace period có giới hạn. Nên thiết kế cancellation/completion, reconnection và resume semantics (ví dụ Last-Event-ID khi phù hợp) ở tầng ứng dụng.

Tương tự, file upload/download rất dài có thể vượt deadline. Cần chunking, resumability hoặc job-based transfer thay vì tăng grace vô hạn.

### 11.3. HTTP/2 multiplexing

Một TCP connection HTTP/2 có nhiều streams. Một stream có thể đã in-flight trong khi stream mới được tạo sát mốc drain. Cách ngăn streams mới và đóng connection tùy HTTP/2 implementation, có thể liên quan GOAWAY. Đừng dùng một kết quả HTTP/1.1 keep-alive để suy ra HTTP/2/gRPC.

### 11.4. Spring MVC async

Controller MVC trả **Callable**, **DeferredResult** hoặc **CompletableFuture** có thể giải phóng thread servlet ban đầu trong lúc response vẫn đang chờ. Điều đó **không đồng nghĩa HTTP request đã hoàn tất**. Server-side drain phải xem trạng thái request ở Servlet layer.

Nếu executor dùng để hoàn tất future đã bị đóng sớm, request có thể hỏng dù server đang graceful. Vì vậy executor lifecycle cần phù hợp với thời gian drain.

### 11.5. WebFlux/Reactor Netty

Reactor Netty có hỗ trợ graceful ở tầng embedded server. Với một reactive stream lâu dài, completion và timeout phụ thuộc publisher/server. Không block Reactor Netty event loop để “giữ request sống” và đừng giả định stream vô hạn hoàn tất trước grace.

## 12. HTTP graceful không bảo đảm mọi background task được drain

**server.shutdown=graceful** tập trung vào HTTP web server. Nó không phải durable queue và không tự đợi tất cả:

- **@Async** fire-and-forget tasks.
- **@Scheduled** jobs.
- Kafka/RabbitMQ/message consumers.
- Batch jobs không gắn với HTTP response.
- WebSocket application state.
- Outbound I/O còn hoạt động sau khi response HTTP đã kết thúc.

Các thành phần này cần chính sách shutdown/lifecycle riêng. Ví dụ cấu hình executor:

~~~java
@Bean
ThreadPoolTaskExecutor reportExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("report-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(10);
    return executor;
}
~~~

**Đây là snippet**, yêu cầu imports **@Bean**, **ThreadPoolTaskExecutor** và vị trí khai báo trong Spring configuration. Nó không tạo đảm bảo bền vững khi JVM crash. Thời gian chờ executor còn tiêu tốn shutdown budget riêng.

Một request HTTP đang drain có thể cần executor hoặc DB. Nếu tắt dependency trước khi request hoàn tất, graceful không cứu được request đó. Cần định nghĩa thứ tự stop rõ và tránh phóng thích resource quá sớm.

### 12.1. Giao dịch đang commit khi client mất kết nối

Một HTTP request ghi database có thể đã **commit** nhưng client bị mất connection và không biết kết quả. Khi client retry, nguy cơ trùng operation vẫn tồn tại. Dùng **idempotency key**, transaction boundary và trạng thái công việc để xử lý trường hợp kết quả không rõ.

Graceful shutdown giảm xác suất ngắt ngang nhưng **không tự bảo đảm exactly-once**.

### 12.2. Request hoàn tất trước khi tác vụ nền xong

Một API có thể trả 202 Accepted rồi giao một task nền. Đối với embedded web server, HTTP response đã kết thúc, nên task nền **không còn là in-flight HTTP request**. Shutdown vẫn có thể làm task chưa hoàn thành bị mất nếu chỉ lưu trong memory.

Với công việc bắt buộc hoàn tất, sử dụng queue/broker, outbox, Spring Batch hoặc persistence để recover sau crash/restart.

## 13. Lỗi phổ biến và cách chẩn đoán

### 13.1. “Graceful bảo đảm tất cả request cũ trả 200”

Không. Graceful cho thời gian chờ, không loại trừ timeout của client/proxy, lỗi DB, error handling hoặc grace deadline.

### 13.2. “Request mới luôn nhận HTTP 503”

Không. Trong Boot 3.3, Tomcat/Jetty/Reactor Netty chặn tại network layer, Undertow có thể trả 503.

### 13.3. “Boot 3.3 mặc định graceful”

Sai. Boot 3.3 mặc định immediate; default đổi ở Boot 3.4. Kiểm tra đúng version trước khi triển khai.

### 13.4. “Đặt timeout-per-shutdown-phase=20s là tổng toàn process”

Sai. Nhiều SmartLifecycle phases/bean cleanup và preStop có thể cộng thêm thời gian; container có grace tổng riêng.

### 13.5. “Đã có readiness probe thì không cần graceful”

Sai. Load balancer cập nhật routing có trễ; request in-flight vẫn cần được server chờ. Hai cơ chế bổ trợ nhau.

### 13.6. “Đang drain thì GET /readyz bắt buộc trả JSON REFUSING_TRAFFIC”

Không. Khi web server từ chối new connections, probe có thể không tới được endpoint.

### 13.7. “preStop sleep là graceful shutdown”

Không. PreStop chỉ giúp routing có thời gian thay đổi, không khiến Boot immediate mode đợi in-flight.

### 13.8. “SIGKILL vẫn chạy @PreDestroy”

Sai. SIGKILL không cho JVM chạy shutdown hooks/cleanup thông thường.

### 13.9. “HTTP graceful đợi cả @Async/@Scheduled jobs”

Sai. Các task không gắn với HTTP request cần lifecycle và completion/durability riêng.

### 13.10. “HTTP 200 sau SIGTERM chứng minh Pod A vẫn nhận mới”

Không nhất thiết. Có thể request đã in-flight hoặc proxy chuyển nó sang Pod B.

### 13.11. “Giữ connection keep-alive nghĩa server phải nhận tất cả request mới trên đó”

Không. Persistent connection ảnh hưởng chi tiết drain nhưng không tạo hợp đồng request mới luôn được nhận.

### 13.12. “Chỉ cần tăng grace thật dài”

Không phải giải pháp chung. Timeout quá lớn có thể làm rollout chậm, vượt Kubernetes grace và che dependency treo. Đo tail latency, cải thiện client retry, cancellation/resume và tính idempotent.

### 13.13. “ApplicationContext.close() và WebServer.stop() tương đương”

Không hoàn toàn. Context.close phối hợp lifecycle các bean; gọi stop trực tiếp có thể bỏ qua cơ chế orchestration của ứng dụng.

### 13.14. “Controller sleep trả 200 chứng minh production hoàn toàn an toàn”

Không. Demo chỉ kiểm tra request thuần tính toán/sleep; production có DB, outbound HTTP, streaming, queues, transaction và proxies cần kiểm thử riêng.

## 14. Ma trận kiểm thử nên có

| Kịch bản | Kỳ vọng cần đánh giá |
| --- | --- |
| Graceful + A kết thúc trước grace | A có cơ hội trả response bình thường |
| Immediate + A đang chạy | Không có chờ drain theo cơ chế graceful |
| Graceful + A vượt deadline | Server không chờ vô hạn; client có thể thất bại |
| B mới sau khi drain bắt đầu | Instance đang dừng không phục vụ B như traffic bình thường |
| B đến sát ranh giới | Nhận diện race, không dùng một HTTP code làm kết luận |
| Tomcat vs Undertow | Không áp một expected status giống nhau |
| Traffic qua load balancer | Request mới chuyển sang replica ready |
| HTTP keep-alive/HTTP2 | Quan sát reuse, close và stream behavior |
| SSE/WebSocket | Có drain/reconnect strategy riêng |
| @Async job chưa xong | Có lifecycle/durable recovery riêng |
| SIGTERM | Shutdown hooks/context close có cơ hội hoạt động |
| SIGKILL | Không có bảo đảm cleanup |
| Kubernetes rollout | Termination grace bao gồm preStop và các phases |

### 14.1. Metrics và log nên quan sát

- Active HTTP requests lúc bắt đầu shutdown.
- Số request hoàn thành trong grace và số request còn active khi hết deadline.
- Thời lượng từ SIGTERM đến web server stopped.
- Thời lượng đóng context tổng.
- Connection refusal/reset và HTTP 502/503/504 ở từng tầng.
- Instance ID, request ID và route để phân biệt replica.
- Các task/executor còn hoạt động khi cleanup.
- Retry và duplicate operations sau rollout.

Không khẳng định mọi chỉ số này tự có sẵn trong Boot; tùy monitoring stack có thể cần Actuator/Micrometer, access logs và custom instrumentation.

## 15. Checklist production

- [ ] Đã cố định version Spring Boot và biết default server.shutdown.
- [ ] Với Boot 3.3, bật **server.shutdown=graceful** tường minh.
- [ ] Có timeout-per-shutdown-phase bằng duration rõ như **15s**.
- [ ] Hiểu timeout áp dụng từng lifecycle phase, không phải tổng.
- [ ] Biết p95/p99/tail latency và các request long-running.
- [ ] Có timeout cho HTTP/DB calls, không chờ vô hạn.
- [ ] Có readiness probe phù hợp; ưu tiên kiểm tra trên cổng chính nếu cần.
- [ ] Load balancer ngừng route tới instance draining trong thời gian hợp lý.
- [ ] Kubernetes terminationGracePeriodSeconds lớn hơn ngân sách shutdown đã dự trù.
- [ ] preStop không vô tình tiêu hết grace period.
- [ ] JVM nhận SIGTERM đúng, không bị wrapper shell nuốt tín hiệu.
- [ ] Không dùng SIGKILL để đánh giá graceful behavior.
- [ ] Có test in-flight request hoàn thành trong grace.
- [ ] Có test request mới bị từ chối và không ép status 503 trên Tomcat.
- [ ] Có test request vượt deadline.
- [ ] Có test WebSocket/SSE/HTTP2 nếu dùng.
- [ ] Không giải phóng datasource/executor trước khi request in-flight cần chúng đã xong.
- [ ] Background tasks có shutdown policy và persistence khi quan trọng.
- [ ] APIs có side effects hỗ trợ retry/idempotency.
- [ ] Có monitoring ở server, proxy và client thay vì chỉ một tầng.
- [ ] Có đủ replicas ready khi rolling deployment.

## 16. Câu hỏi tự kiểm tra

**1. Boot 3.3 đã bật graceful mặc định chưa?** Chưa. Phải đặt **server.shutdown=graceful**; Boot 3.4 thay đổi default.

**2. In-flight khác new request ở đâu?** In-flight đã được server tiếp nhận và đang xử lý trước mốc drain; new request đến sau khi server từ chối nhận mới.

**3. Graceful 15s có bảo đảm request 8s trả 200 không?** Không tuyệt đối; chỉ cho cơ hội hoàn tất nếu không có lỗi client, proxy, network hoặc business.

**4. Tomcat trả 503 trực tiếp cho mọi new request sau drain?** Không. Tomcat ngăn tại network layer; Undertow có hành vi trả 503.

**5. Timeout 20s per phase có buộc toàn JVM thoát trong 20s?** Không, các phase khác và cleanup còn có thể tốn thời gian.

**6. Vì sao GET /readyz có thể không trả JSON khi draining?** Vì connector đang ngăn new requests, probe có thể không kết nối được.

**7. preStop sleep thay thế graceful được không?** Không; nó không tự khiến server đợi in-flight.

**8. HTTP graceful có tự chờ @Scheduled/@Async?** Không, background tasks cần cơ chế shutdown riêng.

**9. Nếu process bị SIGKILL, @PreDestroy có chắc chạy?** Không.

**10. Có nên dùng cùng một test HTTP/1.1 để suy luận WebSocket/HTTP2?** Không, kết nối và stream có semantics khác.

**11. Vì sao client nhận 200 sau SIGTERM chưa chứng minh instance cũ nhận new request?** Vì proxy có thể chuyển sang instance khác hoặc request đã được tiếp nhận trước drain.

**12. Cần gì cho endpoint ghi dữ liệu có thể bị mất response sau commit?** Idempotency key, transaction boundaries, retry và khả năng truy xuất trạng thái operation.

## 17. Kết luận

Ở mức vòng đời máy chủ, **graceful shutdown giải quyết hai nhóm công việc khác nhau**: ngăn request mới vào server và chờ request in-flight trong một khoảng thời gian có giới hạn.

Với Spring Boot 3.3:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=15s
~~~

Tomcat, Jetty và Reactor Netty ngăn request mới ở tầng mạng; Undertow có thể trả HTTP 503. Request đang xử lý có cơ hội hoàn tất trước deadline, nhưng không được bảo đảm thành công vô điều kiện. Tại môi trường production, phải kết hợp graceful web shutdown với readiness/routing, SIGTERM, Kubernetes grace period, timeout, retry/idempotency và lifecycle của background tasks.

Để xác minh thật, hãy tạo in-flight request, đợi marker BEGIN, gửi SIGTERM đúng process, quan sát A hoàn tất và thử request mới sau mốc drain; sau đó thử lại với request vượt deadline, qua load balancer và với protocol thực tế.

## 18. Tài liệu chính thức

- Spring Boot 3.3.13 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3.13 — Actuator: Application Lifecycle and Probe States: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3.13 — SpringApplication và Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — WebServer.shutDownGracefully API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/server/WebServer.html
- Spring Boot 3.3.13 — GracefulShutdownResult API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/server/GracefulShutdownResult.html
- Spring Framework — SmartLifecycle và vòng đời bean: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot 3.4 release notes — default graceful shutdown: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes