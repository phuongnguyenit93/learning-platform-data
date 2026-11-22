# Khác biệt cách từ chối kết nối giữa các máy chủ nhúng

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** Dừng có kiểm soát

## 1. Tình huống: cùng graceful shutdown nhưng phía client thấy lỗi khác nhau

Một hệ thống dùng Spring Boot triển khai nhiều replicas sau load balancer. Khi một pod nhận SIGTERM để cập nhật phiên bản, một số request đang chạy được tiếp tục hoàn thành, còn các request mới cần chuyển sang pod khỏe mạnh. Đội vận hành đã cấu hình:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Nhưng khi quan sát kết nối trực tiếp tới pod đang dừng, kết quả lại không giống nhau:

- Với **embedded Tomcat**, client mở kết nối HTTP mới có thể bị từ chối ở mức mạng: không nhận một HTTP status code hợp lệ.
- Với **embedded Jetty**, cách từ chối request mới cũng thuộc nhóm **network-level**.
- Với **Reactor Netty** (thường là embedded reactive server của WebFlux), request mới bị từ chối ở **tầng mạng**.
- Với **embedded Undertow**, trong **grace period** server còn tiếp nhận kết nối mới nhưng **trả ngay HTTP 503 Service Unavailable**.

Đây là khác biệt có chủ đích của các embedded web servers theo **Spring Boot 3.3**. Nó không có nghĩa server này graceful hơn server kia theo một thang điểm đơn giản. **Cùng một mục tiêu: cho in-flight requests cơ hội hoàn thành, ngăn công việc mới bắt đầu.** Khác nhau là **cơ chế từ chối và quan sát từ HTTP client, gateway, metrics**.

Theo tài liệu chính thức Spring Boot 3.3, Jetty, Reactor Netty và Tomcat ngừng tiếp nhận new requests tại network layer; Undertow nhận new connections nhưng trả 503. Tài liệu cũng nhấn mạnh **persistent connections** có thể làm behavior được quan sát khác đi. Vì vậy không được gán một loại network exception duy nhất cho tất cả Tomcat requests, cũng không bảo đảm Undertow luôn trả 503 khi tiến trình đã tắt xong.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Mô tả **ApplicationContext close**, **SmartLifecycle**, shutdown hook, timeout và grace period.
2. Phân biệt **network-level refusal**, **HTTP 503**, **502/504 do proxy**, **connection reset**, **timeout**, **EOF** và **connection refused**.
3. Giải thích bảng hành vi **Tomcat / Jetty / Reactor Netty / Undertow** của Spring Boot 3.3.
4. Xác định tác động của **HTTP keep-alive**, connection pooling, HTTP/2, WebSocket/SSE, proxy và load balancer.
5. Tạo một ứng dụng **Spring Boot 3.3 + Java 17+ chạy được**, đổi giữa Tomcat, Jetty và Undertow bằng Maven profiles.
6. Khởi động JAR, mở request chậm, gửi **SIGTERM** tới JVM và kiểm khác biệt bằng curl/Java client.
7. Thiết kế **readiness draining**, Kubernetes preStop/terminationGracePeriodSeconds và client retry/idempotency.
8. Phân biệt kết quả phía **direct client** so với **qua ingress**, biết khi nào việc quan sát 503 là do edge.
9. Theo dõi in-flight duration, rejection/error ratio và chẩn đoán các lỗi shutdown thường gặp.

## 2. Graceful shutdown trong Spring Boot vận hành khi nào?

Một quá trình dừng điển hình:

~~~text
Pod/Service RUNNING
     |
     | SIGTERM / ApplicationContext close
     v
Application starts graceful shutdown
     |
     +--> HTTP server stops admitting new work
     |
     +--> Existing in-flight requests can finish
     |     within the configured shutdown phase grace budget
     |
     +--> Readiness moves toward REFUSING_TRAFFIC
     |
     +--> SmartLifecycle beans stop across phases
     |
     v
Context closed / server stopped / process exits
~~~

**Gracious không có nghĩa giữ server hoạt động mãi.** Graceful shutdown là một khoảng cơ hội để hoàn tất công việc hiện tại. Khi **spring.lifecycle.timeout-per-shutdown-phase** hết hoặc host/orchestrator buộc process dừng, một request còn đang xử lý có thể bị cắt. Thời gian này là **timeout cho lifecycle shutdown phase**, không phải deadline riêng của từng HTTP request và không phải giới hạn tổng tuyệt đối của mọi cleanup trong tiến trình.

Trong Spring Boot 3.3:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Hoặc YAML tương đương:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

**server.shutdown=graceful** là cấu hình cần đặt rõ cho Spring Boot 3.3 để chọn kiểu dừng graceful. **server.shutdown=immediate** thực hiện dừng không có giai đoạn chờ request như trên.

**Không chép máy móc mặc định từ Spring Boot 3.5/4.x.** Ở các phiên bản mới, graceful shutdown có thể bật sẵn và danh sách embedded server được hỗ trợ có thể thay đổi. Trong một runbook phải ghi **phiên bản Spring Boot và embedded server thực tế**, không giả định hành vi của một tài liệu khác version.

### Vì sao tín hiệu dừng quan trọng?

**SIGTERM** trên Linux/container thường kích hoạt shutdown hook của JVM; Spring Boot đóng ApplicationContext theo luồng shutdown. **SIGKILL** không chạy cleanup/shutdown hook. Nút **Stop** trong IDE hoặc một process manager có thể kill cưỡng bức thay vì gửi tín hiệu phù hợp.

Những trường hợp có thể không kích hoạt behavior mong muốn:

- Dùng **kill -9** hoặc container bị OOMKilled.
- Chỉ kill **Maven launcher** trong khi một JVM forked khác đang chạy ứng dụng.
- Orchestrator hết termination grace period và phát SIGKILL.
- JVM crash hoặc mất điện.
- Không cấu hình server.shutdown=graceful trên nhánh Boot cần cấu hình.
- Web server/custom connector không chạy theo Spring Boot managed lifecycle.

Vì vậy bài thực nghiệm sẽ chạy **java -jar** và gửi SIGTERM trực tiếp tới **PID của JVM app**. Không dùng **mvn spring-boot:run** rồi đoán PID Maven là PID app.

## 3. Bảng so sánh bốn embedded server ở Spring Boot 3.3

| Embedded server | Web stack phổ biến | Từ chối request mới trong grace period | Quan sát client trực tiếp có thể gặp | Mấu chốt |
| --- | --- | --- | --- | --- |
| **Tomcat** | **Servlet/MVC** mặc định | Dừng nhận request mới ở **tầng mạng** | Connect failure, connection closed/reset, no HTTP response; tùy thời điểm | Không mặc định có HTTP 503 do ứng dụng cho request mới. |
| **Jetty** | **Servlet/MVC**, có thể reactive | Dừng nhận request mới ở **tầng mạng** | Network exception/EOF/timeout hoặc connection không tái sử dụng được | Không hứa hẹn một curl error code cố định. |
| **Reactor Netty** | **Reactive WebFlux** mặc định | Dừng nhận request mới ở **tầng mạng** | Network-level failure, closed connection, retryable transport errors tùy client | Không tự trở thành embedded server của MVC chỉ vì dùng WebClient. |
| **Undertow** | **Servlet/MVC**, cũng có reactive integration trong Boot 3.3 | Vẫn có thể nhận kết nối nhưng **trả HTTP 503 Service Unavailable** cho request mới | HTTP status 503 trong cửa sổ graceful; sau khi server đóng có thể là network error | HTTP response 503 là cơ chế từ chối ở server trong giai đoạn còn nhận kết nối. |

**Nguồn:** Spring Boot 3.3 Graceful Shutdown, phần nói rõ phương thức từ chối request mới. Các ví dụ network exceptions trong bảng là **khả năng quan sát**, không phải một output được Spring Boot bảo đảm cho từng OS/kernel/proxy.

**Quan trọng:** Spring Boot 3.3 Servlet stack chủ yếu dùng **Tomcat, Jetty, Undertow**. Reactor Netty thường là server của **WebFlux/reactive**, không phải một embedded Servlet container. So sánh bốn server là so sánh cơ chế graceful shutdown ở Boot 3.3, **không phải bốn Servlet containers tương đương nhau**.

### Cách chọn đúng server

- **spring-boot-starter-web** mặc định kéo **spring-boot-starter-tomcat**.
- Muốn thử **Jetty**, loại trừ Tomcat starter và thêm **spring-boot-starter-jetty**.
- Muốn thử **Undertow**, loại trừ Tomcat starter và thêm **spring-boot-starter-undertow**.
- **spring-boot-starter-webflux** mặc định kéo Reactor Netty cho reactive server. Nếu cùng có Spring MVC và WebFlux, Spring Boot thường ưu tiên Servlet MVC; việc có Reactor Netty libraries để dùng WebClient **không chứng minh server là Netty**.

Cần dùng dependency tree/startup logs để xác định web server thực tế. Đừng lấy tên class của HTTP client làm bằng chứng loại HTTP server đang lắng nghe port.

## 4. Network-level refusal khác HTTP 503 như thế nào?

### 4.1. Từ chối ở mạng

Mô hình network-level:

~~~text
Client                  Tomcat / Jetty / Reactor Netty
  |
  | TCP connect / request on connection
  |----------------------------------------->
  |             listener/accept path stopping
  |
  |<---------- close/refusal/reset/timeout ----
  |
  +--> may have NO valid HTTP response status
~~~

**Network-level** nghĩa là request mới không được xử lý như một HTTP request bình thường có response status do ứng dụng tạo. Nhưng kết quả cụ thể phụ thuộc cửa sổ thời gian và TCP/socket state:

- **Connection refused (ECONNREFUSED)**: không có listener nhận connect tại địa chỉ/port hoặc network stack trả RST.
- **Connection reset by peer (ECONNRESET)**: kết nối bị reset sau khi lập được hoặc khi đang gửi/nhận.
- **EOF / Empty reply from server**: socket đóng trước khi client nhận được response HTTP hợp lệ.
- **Timeout**: SYN, TLS handshake hoặc response không hoàn tất trước client deadline.
- **Connection closed**: client library phát hiện connection không thể tiếp tục hoặc keep-alive bị đóng.

Không phải mọi cơ chế ở trên đều luôn xảy ra với Tomcat. Cụm từ **network-layer refusal** là mô tả chính thức ở cấp behavior, không phải cam kết errno của Linux hay dòng curl cố định.

### 4.2. Từ chối bằng HTTP status 503

Mô hình Undertow:

~~~text
Client                          Undertow in grace period
  | TCP connect
  |-------------------------------------------->
  | TCP established
  |<--------------------------------------------|
  | GET /ping HTTP/1.1
  |-------------------------------------------->
  | HTTP/1.1 503 Service Unavailable
  |<--------------------------------------------|
~~~

**HTTP 503** là một HTTP response hợp lệ: request đã đến một HTTP handler/connector có khả năng trả status. Client có thể ghi response status, apply policy cho 503 và không nhầm nó với lỗi DNS/TCP.

Nhưng **503 không có nghĩa request nghiệp vụ đã được chạy hoặc chắc chắn chưa có side effect trên toàn hệ thống**. 503 có thể do Undertow shutdown, load balancer, gateway overload, upstream service, circuit breaker hoặc app tự trả. Muốn biết nguồn phải đối chiếu response headers, logs ở hops, readiness state và tracing.

**503 không phải bắt buộc có Retry-After**. Có thể kèm Retry-After nếu một layer đặt nó, nhưng Spring Boot Undertow graceful shutdown không được coi là tự động cam kết header đó. Client cần retry policy của riêng mình.

### 4.3. Nếu request đi qua ingress thì khác nữa

~~~text
Client ----> Load Balancer / Nginx ----> Pod shutting down
                      |
                      +--> maybe 502 / 503 / 504
                      +--> maybe TCP close
                      +--> maybe route to healthy pod
~~~

Nếu client truy cập qua gateway, HTTP **502 Bad Gateway** có thể là gateway không kết nối được upstream; **503** có thể là gateway hết healthy backends hoặc Undertow upstream trả 503; **504** có thể là upstream timeout ở gateway. Những status này **không cho biết trực tiếp embedded server thuộc nhóm nào**.

Để thực nghiệm cơ chế gốc, phải gửi request **trực tiếp tới listening port của JVM**, không đi qua CDN, ingress hoặc service mesh (trừ khi cố ý kiểm hành vi edge). Trong production không bỏ qua TLS/security để mở pod public: thực nghiệm trực tiếp chỉ ở local hoặc network test an toàn.

## 5. Thời điểm và keep-alive tạo ra kết quả khác nhau

Một graceful shutdown có nhiều thời điểm:

~~~text
T0: RUNNING; requests and new connections accepted
T1: request A enters /slow and is still in flight
T2: SIGTERM reaches JVM; context shutdown starts
T3: server begins rejecting new requests according to mechanism
T4: request A finishes, grace budget no longer needed
T5: connector and JVM stop; no HTTP listener
~~~

Ở **T1–T3**, nếu client mới kết nối trước khi shutdown logic thực sự áp dụng, request có thể vẫn được nhận. Ở **T3–T4**, Undertow thường có thể trả 503; Tomcat/Jetty/Netty có thể gây network-level failure. Sau **T5**, cả Undertow cũng không còn connector để trả 503. Vì thế một test chỉ gọi một lần sau khi app đã tắt **không chứng minh sự khác nhau**.

### Kết nối HTTP persistent / keep-alive

HTTP/1.1 mặc định có thể giữ connection. Một HTTP client có connection pool có thể tái sử dụng một socket đã mở trước shutdown. Cơ chế từ chối request khi có persistent connection **có thể khác** cơ chế từ chối một TCP connection mới—điểm này được Spring Boot docs nhấn mạnh.

Do đó:

- **New TCP connection** và **new HTTP request trên socket cũ** là hai test cases riêng.
- Một curl invocation mới tới localhost thường tạo client connection mới; thêm **Connection: close** giúp tránh giữ connection sau response.
- Với Apache HttpClient, Java HttpClient, WebClient hoặc load balancer, connection pools có thể vẫn giữ sockets cũ.
- **HTTP/2** multiplex nhiều streams trên một connection; một stream mới không phải TCP connection mới. Protocol và connector implementation có thể ảnh hưởng shutdown behavior.
- Long polling, SSE và WebSocket có lifecycle dài; không suy tương đương từ GET ngắn.

Khi kiểm thử, ghi rõ: **HTTP version**, direct/proxy path, connection reuse hay fresh, TLS, time từ SIGTERM và server version.

## 6. Timeout: cơ hội hoàn tất chứ không phải lời hứa 200 OK

Cấu hình:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

cho Spring Boot một **shutdown-phase timeout**. Một request bắt đầu trước shutdown và hoàn thành trong grace budget có cơ hội trả kết quả bình thường. Một request 60 giây có thể bị chấm dứt trước khi hoàn tất nếu thời gian grace chỉ 20 giây.

**Những điều KHÔNG được suy ra:**

- Không phải mọi request có 20 giây riêng.
- Không phải process luôn kết thúc chính xác ở giây thứ 20.
- Không phải request nào chạy trước SIGTERM cũng chắc chắn trả 200.
- Không phải WebSocket/SSE vô hạn được giữ sống cho tới khi client tự đóng.
- Không phải terminationGracePeriodSeconds của Kubernetes tự động bằng timeout Boot.
- Không phải hạ tầng ngừng route traffic ngay cùng thời điểm SIGTERM, vì có độ trễ cập nhật endpoint/proxy.

Thời gian stop của các SmartLifecycle beans và cleanup khác cũng cần ngân sách. Nếu pod bị kill sau 10 giây, việc app cấu hình grace 20 giây không giúp hoàn tất request dài 15 giây.

## 7. Demo Java 17+ so sánh Tomcat, Jetty và Undertow

Demo cố ý tạo hai loại endpoint:

- **GET /ping**: xử lý nhanh và trả văn bản **pong**.
- **GET /slow?delayMs=15000**: ngủ một thời gian cho phép, sau đó trả **done:15000**. Nó giúp giữ một **in-flight request** trong lúc gửi SIGTERM, để quan sát cửa sổ grace period trước khi JVM thoát.

Chúng ta sử dụng **Spring Boot 3.3.13**, **Java 17+**, Maven và Servlet Spring MVC. Đối với Reactor Netty, sẽ có phần riêng vì nó thuộc reactive server; không cố trộn Reactor Netty vào cùng các Servlet profiles.

Cấu trúc:

~~~text
graceful-server-demo/
  pom.xml
  src/main/
    java/com/example/graceful/
      GracefulServerApplication.java
    resources/
      application.properties
  src/test/
    java/com/example/graceful/
      HttpEndpointsTests.java
  NewRequestProbe.java
~~~

### 7.1. pom.xml hoàn chỉnh với ba Maven profiles

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>graceful-server-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
            <exclusions>
                <exclusion>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-tomcat</artifactId>
                </exclusion>
            </exclusions>
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

    <profiles>
        <profile>
            <id>tomcat</id>
            <activation>
                <activeByDefault>true</activeByDefault>
            </activation>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-tomcat</artifactId>
                </dependency>
            </dependencies>
        </profile>

        <profile>
            <id>jetty</id>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-jetty</artifactId>
                </dependency>
            </dependencies>
        </profile>

        <profile>
            <id>undertow</id>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-undertow</artifactId>
                </dependency>
            </dependencies>
        </profile>
    </profiles>

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

**Tại sao cần exclude Tomcat trong starter-web?** Nếu vừa có Tomcat vừa có Jetty/Undertow do thêm starter mà không loại trừ, classpath có nhiều Servlet containers; server được auto-configured có thể không phải loại bạn nghĩ. Bài dùng một profile để đưa vào **chỉ một starter container**.

**Maven activeByDefault:** tomcat được kích hoạt khi không có profile khác; chọn rõ **-Pjetty** hoặc **-Pundertow** sẽ thay default profile từ cùng POM. **Không kích hoạt đồng thời nhiều server profiles.**

Sau khi build, kiểm console startup logs hoặc dependency tree:

~~~bash
mvn -Pjetty dependency:tree
mvn -Pundertow dependency:tree
~~~

Không dùng tên image/tên service làm bằng chứng. Muốn so sánh container, phải xác định server thật trong process.

### 7.2. application.properties

Tạo **src/main/resources/application.properties**:

~~~properties
server.port=8080
spring.application.name=graceful-server-demo

# Spring Boot 3.3: bat graceful shutdown mot cach ro rang
server.shutdown=graceful

# Grace period cua lifecycle phase, khong phai timeout moi request
spring.lifecycle.timeout-per-shutdown-phase=20s

# Bật readiness/liveness endpoints khi demo local.
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health

logging.level.com.example.graceful=INFO
~~~

**/actuator/health/readiness** có thể được dùng để quan sát trạng thái ở giai đoạn ứng dụng hoạt động. Trong thời gian shutdown, HTTP connector có thể đã không tiếp nhận request mới, nên **không bảo đảm probe còn trả được JSON**. Thay vì phụ thuộc một lần gọi readiness sau SIGTERM, nên kết hợp application lifecycle events, access logs, connection errors và proxy metrics.

### 7.3. Java application hoàn chỉnh

Tạo **src/main/java/com/example/graceful/GracefulServerApplication.java**:

~~~java
package com.example.graceful;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class GracefulServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(GracefulServerApplication.class, args);
    }
}

@RestController
class WorkController {

    private static final Logger log =
            LoggerFactory.getLogger(WorkController.class);

    @GetMapping(value = "/ping", produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }

    @GetMapping(value = "/slow", produces = MediaType.TEXT_PLAIN_VALUE)
    public String slow(
            @RequestParam(name = "delayMs", defaultValue = "15000")
            int delayMs) throws InterruptedException {

        // Bao ve demo: chi cho request sleep 0..30000 ms.
        int bounded = Math.max(0, Math.min(delayMs, 30000));
        log.info("slow.begin delayMs={}", bounded);

        Thread.sleep(bounded);

        log.info("slow.end delayMs={}", bounded);
        return "done:" + bounded;
    }
}
~~~

**Đây là mã chạy được** với Java 17 và Spring Boot Servlet MVC. Chỉ main class public, WorkController package-private cùng package, được Spring component scan. Không có database hay service ngoài.

**Đặc điểm cố ý của demo:**

- **Thread.sleep** mô phỏng một HTTP request đang xử lý. Đừng dùng Thread.sleep như business architecture production; chỉ dùng để mở cửa sổ quan sát.
- **delayMs=15000** nhỏ hơn grace timeout 20s, tạo cơ hội để request A hoàn tất. Điều đó vẫn không bảo đảm tuyệt đối nếu SIGTERM tới quá trễ hoặc container bị kill sớm.
- **Bounded delay** tránh một input vô hạn giữ Servlet worker quá lâu. Production cần async jobs/timeout/scheduler phù hợp.
- **Log slow.begin/slow.end** giúp xác định request đã vào controller **trước khi gửi SIGTERM**. Không test dựa thuần vào sleep 1 giây nếu server khởi động chậm.
- **/ping** được dùng làm new-request probe, không phải health/readiness management endpoint.

### 7.4. Test HTTP behavior trước khi kiểm shutdown

Tạo **src/test/java/com/example/graceful/HttpEndpointsTests.java**:

~~~java
package com.example.graceful;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpEndpointsTests {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();

    private String get(String path) throws Exception {
        HttpRequest req = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                req, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        return response.body();
    }

    @Test
    void pingWorks() throws Exception {
        assertEquals("pong", get("/ping"));
    }

    @Test
    void slowZeroReturnsImmediately() throws Exception {
        assertEquals("done:0", get("/slow?delayMs=0"));
    }
}
~~~

Chạy:

~~~bash
mvn -Ptomcat test
mvn -Pjetty test
mvn -Pundertow test
~~~

**JUnit tests trên xác minh các endpoints hoạt động với từng container**; chúng **không tự kiểm được cách từ chối request sau SIGTERM**, vì SpringBootTest khởi động/đóng application context trong process test và không tạo một process lifecycle/kết nối đối chứng như thí nghiệm. Muốn xác minh graceful shutdown phải test ở process-level qua **java -jar**, signal và client requests thật.

## 8. Thí nghiệm gửi SIGTERM: đo đúng giai đoạn đang drain

Thực hiện trên **Linux/macOS/WSL/Bash**. Ở Windows native PowerShell, tín hiệu/process control khác; dùng WSL/container để lặp đúng thí nghiệm SIGTERM. Không dùng IDE Stop vì có thể terminate cưỡng bức.

### Bước 1. Build một container variant

Ví dụ Tomcat:

~~~bash
mvn -Ptomcat -DskipTests clean package
~~~

Để thử Jetty hoặc Undertow, sau khi kết thúc lần đo trước, build lại JAR tương ứng:

~~~bash
mvn -Pjetty -DskipTests clean package
~~~

hoặc:

~~~bash
mvn -Pundertow -DskipTests clean package
~~~

**Mỗi lần chỉ chạy một variant**, vì JAR output được build lại với dependency classpath khác nhau. Đừng build Undertow rồi nói đang chạy Tomcat nếu không kiểm startup logs.

### Bước 2. Khởi động JVM trực tiếp

Trong terminal A, từ thư mục project:

~~~bash
java -jar target/graceful-server-demo-0.0.1-SNAPSHOT.jar > server.log 2>&1 &
APP_PID=$!
echo "$APP_PID"
~~~

Khi app đã chạy, trong terminal B:

~~~bash
curl -si http://127.0.0.1:8080/ping
curl -si http://127.0.0.1:8080/actuator/health/readiness
~~~

**/ping** trả **pong** khi bình thường. Readiness thường UP khi app đã sẵn sàng, nhưng nội dung health JSON có thể khác tùy auto-configuration. **APP_PID** phải là PID của Java process chạy JAR, không phải PID shell hay Maven.

### Bước 3. Giữ một request in flight

Trong terminal B:

~~~bash
curl -sS --max-time 30 \
  "http://127.0.0.1:8080/slow?delayMs=15000" > slow.out &
SLOW_PID=$!
echo "$SLOW_PID"
~~~

Kiểm **server.log** hoặc console đã xuất hiện **slow.begin delayMs=15000**. **Chỉ sau đó** mới gửi SIGTERM; nếu request chưa tới controller, nó có thể trở thành request mới và bị từ chối thay vì in-flight request.

### Bước 4. Gửi SIGTERM và ngay sau đó thử request mới

Tại terminal A:

~~~bash
kill -TERM "$APP_PID"
~~~

Trong terminal B, khi request slow còn đang chờ:

~~~bash
curl -v -i --http1.1 \
  --connect-timeout 2 --max-time 4 \
  -H 'Connection: close' \
  http://127.0.0.1:8080/ping
~~~

Lệnh curl mới tạo một client invocation mới và hướng tới new connection. **Không dùng curl -f/--fail** ở đây, vì HTTP 503 sẽ khiến curl nonzero và có thể làm khó phân biệt một HTTP response 503 hợp lệ với network error.

Sau đó:

~~~bash
wait "$SLOW_PID"
cat slow.out
~~~

Nếu /slow hoàn thành trong grace budget và không bị hạ tầng cắt, file có:

~~~text
done:15000
~~~

Đây là **kết quả kỳ vọng khi request chạy trọn vẹn**. Nếu process bị kill mạnh, timeout hoặc test sai thời điểm, file có thể rỗng/không đầy đủ; không giả mạo rằng kết quả này được bảo đảm trong mọi lần chạy.

### Bước 5. So sánh

- **Tomcat/Jetty**: request /ping đến sau khi graceful shutdown đã áp dụng thường **không nhận HTTP 503 trực tiếp từ server**, mà gặp network-level refusal/closed connection. Dòng curl lỗi có thể khác nhau giữa OS và timing.
- **Undertow**: trong grace period và khi vẫn đang giữ connector nhận requests, **/ping có thể trả HTTP/1.1 503 Service Unavailable**. Nếu test sau khi app đã thoát, cũng có thể chỉ thấy connection refused.
- **Request /slow**: có cơ hội trả **done:15000** vì bắt đầu trước khi dừng và nhỏ hơn grace timeout 20s. Kết quả thực tế phụ thuộc lúc signal đến so với tiến trình request.
- **No proxy**: việc truy cập 127.0.0.1 trực tiếp giúp tách lỗi app server khỏi 502/503 do ingress.

**Repeat:** thực hiện lại từng variant với cùng delay, grace timeout và client. Ghi timestamp từ lúc SIGTERM, duration, HTTP status hoặc network exception, loại server và OS. Đừng chỉ chạy một lần rồi khẳng định tính bất biến ở mọi phiên bản.

## 9. Java 17 client độc lập để phân loại HTTP status và lỗi mạng

Nếu muốn có phép đo lặp lại và in rõ **HTTP_RESPONSE** hay **NETWORK_FAILURE**, tạo file **NewRequestProbe.java** ở thư mục gốc. Nó là một Java program độc lập chỉ dùng JDK 17:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class NewRequestProbe {

    public static void main(String[] args)
            throws InterruptedException {

        URI uri = URI.create("http://127.0.0.1:8080/ping");

        for (int attempt = 1; attempt <= 8; attempt++) {

            // Client moi moi lan: giam kha nang reuse socket
            // trong chinh client, khong phu thuoc Java SDK cua Boot.
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            HttpRequest req = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(3))
                    .GET()
                    .build();

            try {
                HttpResponse<String> resp = client.send(
                        req, HttpResponse.BodyHandlers.ofString());

                System.out.println("attempt=" + attempt
                        + " HTTP_RESPONSE status="
                        + resp.statusCode());

            } catch (IOException ex) {
                System.out.println("attempt=" + attempt
                        + " NETWORK_FAILURE type="
                        + ex.getClass().getSimpleName());
            }

            Thread.sleep(400);
        }
    }
}
~~~

Biên dịch:

~~~bash
javac NewRequestProbe.java
java NewRequestProbe
~~~

**Cách dùng:** khởi động probe ngay sau khi SIGTERM được gửi, trong lúc /slow vẫn đang chạy. Lệnh có 8 attempts, mỗi lần cách 400ms cộng thời gian HTTP request. Nó giúp quan sát một chuỗi kết quả, nhưng không loại bỏ được toàn bộ race conditions của lifecycle.

Ví dụ **minh họa, không phải stdout cam kết** với Undertow:

~~~text
attempt=1 HTTP_RESPONSE status=503
attempt=2 HTTP_RESPONSE status=503
attempt=3 HTTP_RESPONSE status=503
attempt=4 NETWORK_FAILURE type=ConnectException
~~~

Với Tomcat/Jetty, bạn thường thấy các dòng **NETWORK_FAILURE** ở giữa grace window; nhưng class exception có thể khác (ConnectException, SocketException, HttpTimeoutException, IOException subclass khác). Cũng có thể có HTTP 200 ở lần đầu nếu probe khởi chạy trước khi shutdown áp dụng.

**Không coi một kết quả 200 là bằng chứng graceful shutdown thất bại** khi request đã được tiếp nhận trước thời điểm server đóng intake. Tương tự, không coi network failure sau khi Undertow đã thoát là bằng chứng Undertow không hỗ trợ cơ chế 503 lúc graceful period.

Java HttpClient có thể giữ connection pool hoặc sự kiện asynchronous; trong thí nghiệm ngắn mỗi attempt tạo client mới giảm reuse trong cùng client, nhưng không thể tuyên bố mọi hệ thống mạng/hop chắc chắn dùng một TCP connection mới. Phép đo direct curl cùng capture mạng nếu cần chính xác hơn.

## 10. Các lỗi phía client: phân loại và retry cho đúng

Một client tích hợp API cần phân biệt **HTTP response** và **transport failure**. Ví dụ:

| Kết quả | Nhận định | Retry thế nào? |
| --- | --- | --- |
| **HTTP 503** | Server/edge trả Service Unavailable; có status và có thể Retry-After | Có thể retry có backoff/jitter nếu nghiệp vụ an toàn. |
| **HTTP 502** | Gateway nhận lỗi từ upstream hoặc không kết nối được | Xem gateway, có retry policy và giới hạn. |
| **HTTP 504** | Gateway không nhận response kịp deadline | Có thể request đã chạy; retry phải xét idempotency. |
| **Connection refused** | Không kết nối được TCP tới target | Check endpoint readiness/network; retry tới healthy instance nếu phù hợp. |
| **Connection reset / EOF** | Kết nối bị cắt khi giao tiếp | Với write request, kết quả nghiệp vụ có thể không rõ. |
| **Connect/response timeout** | Không hoàn tất trong thời hạn client | Không biết chắc server đã xử lý hay chưa. |
| **HTTP 200** | Có HTTP response thành công | Không retry vô cớ. |

**Retry safety quan trọng hơn loại exception.** Một POST thanh toán có thể đã commit rồi response bị reset trong lúc shutdown. Client không được tự động POST lần nữa chỉ vì thấy ECONNRESET hoặc 504. Thiết kế **Idempotency-Key**, transaction deduplication, trạng thái giao dịch có thể tra cứu và retry bounded theo contract.

Những nguyên tắc:

- Chỉ retry GET/HEAD hoặc thao tác idempotent khi điều kiện nghiệp vụ cho phép; ngay cả GET cũng có thể có side effects trong hệ thống viết sai, nên cần hiểu contract.
- Với POST không idempotent, dùng request idempotency key và dedup bên server; không retry mù quáng.
- Có **exponential backoff + jitter** và tổng retry budget/deadline để tránh retry storm khi toàn cụm rollout.
- Tôn trọng **Retry-After** nếu một HTTP response đáng tin cậy có header ấy; đừng suy Undertow tự cung cấp header này.
- Tránh gửi retry tới pod đang terminating; load balancer/service discovery cần bỏ target không ready.
- Theo dõi response status và network exceptions riêng. Nếu chỉ đếm **http.server.requests{status="503"}**, bạn có thể bỏ sót network rejections vốn không tạo được HTTP response.
- Giới hạn connection pooling và xử lý stale keep-alive sockets theo HTTP client library.
- Khi phát hiện transient termination, ưu tiên route tới healthy instance hơn việc retry cùng target IP.

## 11. Kubernetes: readiness và drain phải đến trước ngắt kết nối

Graceful shutdown **ở trong JVM** chỉ là một phần của zero-downtime rollout. Hệ thống còn cần điều phối load balancer/ingress:

~~~text
Kubernetes decides to terminate Pod A
       |
       +--> Endpoint is marked terminating / traffic drain begins
       |
       +--> preStop hook (optional time for propagation)
       |
       +--> SIGTERM to application process
       |
       +--> Boot graceful shutdown (e.g. up to 20 s phase)
       |
       +--> existing requests finish if time permits
       |
       +--> container stops or Kubernetes sends SIGKILL at deadline
~~~

**Readiness** trong Spring Boot phản ánh AvailabilityState, với **ACCEPTING_TRAFFIC** khi chạy ổn định và **REFUSING_TRAFFIC** trong giai đoạn graceful shutdown. Tuy nhiên khi HTTP connector bắt đầu từ chối request mới, **probe HTTP có thể không nhận một JSON readiness response**. Kết quả đó không mâu thuẫn với trạng thái in-memory REFUSING_TRAFFIC.

Một phần Deployment manifest **minh họa các trường liên quan**, không phải YAML Deployment hoàn chỉnh:

~~~yaml
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 40
      containers:
        - name: app
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 2
            timeoutSeconds: 1
          lifecycle:
            preStop:
              exec:
                command:
                  - /bin/sh
                  - -c
                  - sleep 5
~~~

**Giải thích:**

- Grace của Kubernetes **40s** phải đủ cho thời gian **preStop 5s + Spring Boot grace phase 20s + startup/shutdown overhead và network drain margin**. Đây là số minh họa, không phải chuẩn cố định.
- preStop sleep có thể giúp load balancer/endpoint controllers có thời gian cập nhật target trước khi gửi SIGTERM. Nó không tự đảm bảo mọi proxy cập nhật trong đúng 5 giây và không tự đổi AvailabilityState của app ngay lập tức.
- Kubernetes có cơ chế đánh dấu endpoint đang terminating; traffic routing/discovery behavior còn phụ thuộc phiên bản, EndpointSlice/ingress implementation và connection reuse.
- Nếu container entrypoint là một shell wrapper không chuyển tiếp SIGTERM tới JVM, graceful shutdown có thể không xảy ra đúng cách. Nên chạy Java process với signal forwarding/PID 1 đúng.
- Nếu app có request dài hơn 20s, phải cân nhắc service-level timeout/retry, điều chỉnh grace theo SLO hoặc chuyển tác vụ dài sang queue/job.
- Khi dùng **management.server.port** riêng, probe vào management port có thể UP trong khi cổng app bị lỗi; cần cân nhắc additional-probes trên main port hoặc endpoint kết hợp khi deployment cần.
- **Không dùng liveness** để đánh dấu không ready khi rollout một cách sai; liveness báo process cần restart, readiness báo có thể nhận traffic. Nhầm hai loại probe có thể gây restart loops.

**Readiness không loại bỏ được race hoàn toàn.** Gateway có thể đã chọn upstream trước khi target bị loại hoặc đang reuse một keep-alive connection. Vì vậy client vẫn cần xử lý graceful rejection.

## 12. Reactor Netty cần được thử bằng dự án reactive riêng

**Reactor Netty** là embedded HTTP server phổ biến của Spring WebFlux. Trong Spring Boot 3.3, nó thuộc nhóm **ngừng nhận request mới ở network layer** khi graceful shutdown. Nhưng demo Servlet ở phần 7 không có Reactor Netty profile vì:

- **Reactor Netty không phải Servlet container**.
- **spring-boot-starter-webflux** tự đưa Reactor Netty vào reactive server path.
- Việc thêm WebFlux dependency chỉ để dùng WebClient trong dự án MVC **không chứng minh server đổi sang Netty**.
- So sánh runtime cần test đúng stack, đúng classpath và application type.

Một demo WebFlux minimal khác có thể có Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Với pom riêng và không có **spring-boot-starter-web**, server mặc định thường là Reactor Netty. REST controller hoặc RouterFunction reactive và chính sách shutdown properties tương tự có thể phục vụ /ping và /slow, nhưng **không copy Thread.sleep trên Reactor Netty event loop**. Delay bất đồng bộ nên dùng Reactor **Mono.delay(Duration.ofMillis(...))**, trả Mono<String>, bảo đảm pipeline không block.

Ví dụ **snippet controller method reactive** trong một @RestController WebFlux riêng:

~~~java
@GetMapping(value = "/slow", produces = "text/plain")
public Mono<String> slow() {
    return Mono.delay(Duration.ofSeconds(15))
            .map(ignored -> "done:15000");
}
~~~

Nó cần import **reactor.core.publisher.Mono**, **java.time.Duration**, **org.springframework.web.bind.annotation.GetMapping** và class @RestController, không phải một chương trình độc lập. Muốn so sánh với Servlet demo, cần viết project reactive chạy được với đúng environment/proxy/persistence, không trộn hai stacks trong một benchmark rồi suy ra khác biệt chỉ do connector.

## 13. Long-lived requests: SSE, WebSocket, streaming và HTTP/2

Gracious shutdown thường dễ nhận thấy với request ngắn. Nhưng **long-lived connections** làm vấn đề phức tạp:

- **SSE**: HTTP response có thể mở nhiều phút/giờ. Grace timeout có thể hết trước khi stream kết thúc.
- **WebSocket**: sau handshake là kết nối hai chiều dài; protocol có close frames và yêu cầu reconnect/resubscribe. Không coi WebSocket giống một GET trả body hữu hạn.
- **HTTP streaming/long polling**: response chưa kết thúc, ảnh hưởng drain budget.
- **HTTP/2**: nhiều streams trên một connection, việc nhận stream mới và đóng connection có semantics riêng.
- **Connection pools** ở client/proxy: socket có từ trước có thể tồn tại vào thời điểm graceful starts.

**Chiến lược:** đặt giới hạn session/stream lifetime, thông báo server draining cho clients khi hợp lý, chủ động close đúng protocol, reconnect với backoff/jitter và khôi phục subscription/state. Nếu cần không mất message, có event IDs, offset/cursor, ack và durable broker. Graceful shutdown không tự cung cấp replay hoặc exact-once delivery.

**Không tăng grace timeout lên vô hạn** để “giữ WebSocket luôn sống”. Nếu orchestrator có deadline, cuối cùng pod vẫn bị kill; cần thiết kế reconnect.

## 14. Quan sát đúng ở từng lớp

Nếu chỉ xem HTTP **503 count** của Spring Boot app, server Tomcat đang graceful có thể từ chối ở network layer và **không phát bất cứ response 503 nào**. Vậy một dashboard chỉ nhìn server-side HTTP 5xx có thể báo “không có lỗi” trong khi upstream client liên tục gặp connection errors.

Đo kết hợp:

| Vị trí | Tín hiệu | Giúp phân biệt |
| --- | --- | --- |
| Spring Boot process | Lifecycle shutdown begin/end, log graceful shutdown, active requests | Shutdown có thật sự được kích hoạt không? |
| Embedded connector | Connection accept/close, threads, active connections, HTTP status | New work bị từ chối ở tầng nào? |
| Client HTTP library | ConnectException/SocketException/EOF/timeout, HTTP status, retries | Có nhận HTTP response không? |
| Ingress / API Gateway | 502/503/504 by upstream, healthy endpoint count, target draining | Edge tự trả status hay pass-through từ Undertow? |
| Kubernetes | Pod deletion timestamp, readiness, terminating endpoints, SIGTERM/SIGKILL, restart reason | Grace period có đủ, có bị kill sớm không? |
| Distributed traces | In-flight spans durations, outbound spans and exit status | Requests nào kịp hoàn thành? |
| Load balancer | Connection reuse, queue, failover, target selection | Tại sao client còn gửi tới terminating pod? |

**Micrometer Actuator** có thể phát metric **http.server.requests** cho HTTP requests được xử lý qua observation pipeline và **http.client.requests** cho clients tương thích. Nhưng network-level rejection trước handler thường không tạo server HTTP request metric. Phải kiểm **client-side errors/edge metrics**.

**Log status 503 ở Undertow không tự chứng minh root cause là shutdown.** Cross-correlate với **timestamp, pod, lifecycle event, request ID/traceId và upstream status origin**. Không log Authorization/Cookie/body khi điều tra.

Nên dùng metric tags low-cardinality: service, method, route template, status/outcome, dependency. Không đưa raw URI/session ID/request ID vào metric label.

## 15. Sự khác biệt tại application, container và gateway

Các tầng liên quan:

~~~text
End user
   |
   | request / response
   v
CDN / WAF / Ingress / Load balancer
   |
   | fresh / reused upstream connection
   v
Tomcat / Jetty / Undertow / Reactor Netty
   |
   | when accepted
   v
Spring MVC or WebFlux handler
   |
   v
Business transaction / DB / downstream
~~~

**Khi Tomcat đóng intake**, application controller không có cơ hội tự trả 503 cho một request chưa đi vào framework. **Khi Undertow trả 503 ở connector khi graceful**, controller bình thường có thể không được gọi. Đừng gắn @ControllerAdvice để kỳ vọng nó sẽ bắt mọi network refusal và tạo JSON 503.

Nếu gateway muốn chuẩn hóa behavior, nó có thể convert kết quả upstream connection failure thành HTTP 502/503 và retry tới healthy pod. Khi làm vậy, phải:

1. Phân biệt retries an toàn và không an toàn.
2. Không retry vô hạn, không nhân bão tải.
3. Không trộn status originating từ upstream với status do proxy phát trong metrics.
4. Không giả định raw HTTP 503 luôn chứa body/header domain.
5. Ghi correlation/traces đủ để đối chiếu client/gateway/app, không log secrets.
6. Kiểm TLS/HTTP version/keep-alive semantics và connection draining của chính proxy.

**HTTP 503 từ Undertow chưa chắc đến được end user.** Gateway có thể nuốt hoặc thay status theo policy, hoặc chọn một healthy replica khác và user chỉ thấy 200.

## 16. Những hiểu lầm cần tránh

**Hiểu lầm 1: "Nếu server graceful thì request mới luôn trả 503."**  
Sai. Theo Boot 3.3, Tomcat, Jetty, Reactor Netty từ chối ở network layer; Undertow có thể trả 503 trong grace period.

**Hiểu lầm 2: "Connection refused chắc chắn server chết bất thường."**  
Sai. Một server được thiết kế ngừng accept mới khi graceful có thể tạo hiện tượng tương tự phía client.

**Hiểu lầm 3: "HTTP 503 chứng minh Undertow đang chạy."**  
Sai. Proxy, app overload, circuit breaker hoặc nhiều hệ thống khác cũng có thể trả 503. Cần nhìn origin.

**Hiểu lầm 4: "Nếu Undertow trả 503, mọi lần gọi sau SIGTERM đều là 503."**  
Sai. Sau khi connector/process đã đóng, client sẽ gặp network failure; giữa các thời điểm còn có races.

**Hiểu lầm 5: "server.shutdown=graceful bảo đảm mọi request hoàn tất."**  
Sai. Timeout, SIGKILL, JVM crash, long-lived connections hoặc external resource failures vẫn có thể cắt request.

**Hiểu lầm 6: "spring.lifecycle.timeout-per-shutdown-phase=20s là deadline riêng cho từng request."**  
Sai. Nó là timeout theo shutdown phase, không phải thời gian tối đa của mỗi request.

**Hiểu lầm 7: "Đã bật readiness probe thì không bao giờ có new request lúc shutdown."**  
Sai. Endpoint propagation/connection reuse và cạnh tranh thời điểm có thể làm request vẫn tới pod đang drain.

**Hiểu lầm 8: "Một POST gặp reset thì cứ retry."**  
Sai. Server có thể đã commit transaction nhưng response mất. Dùng idempotency keys và biết outcome trước khi retry.

**Hiểu lầm 9: "Có WebClient nghĩa là embedded server Netty."**  
Sai. Spring MVC vẫn thường chạy Tomcat nếu không thay server web application type/classpath.

**Hiểu lầm 10: "Bật Actuator readiness và gọi sau SIGTERM phải luôn trả REFUSING_TRAFFIC JSON."**  
Sai. HTTP connector đã có thể ngừng nhận request; readiness internal state không bảo đảm probe HTTP còn phục vụ.

## 17. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Cách xác minh |
| --- | --- | --- |
| Tomcat trả connection refused thay vì HTTP 503 | Network-level shutdown rejection là behavior bình thường | Đo trực tiếp fresh connection trong grace window, đọc logs. |
| Undertow không thấy 503 | Đo quá muộn, không có in-flight giữ grace, gateway che, hoặc server không phải Undertow | Kiểm startup server, timing T2–T4, curl localhost trực tiếp. |
| Jetty thử nghiệm lại thấy HTTP 200 | Request tới trước khi shutdown áp dụng hoặc socket cũ | Ghi timestamp, dùng new client, xem log shutdown bắt đầu. |
| 502 ở Nginx khi Tomcat stopping | Nginx không kết nối được upstream | So sánh direct curl với proxy, access/error logs edge. |
| HTTP 503 ở gateway nhưng server Tomcat | Gateway tự trả 503/no backends | Ghi status origin, healthy targets và policy gateway. |
| In-flight /slow không hoàn tất | timeout phase, SIGKILL, signal quá sớm, interrupted sleep | Kiểm slow.begin/slow.end, signal, clocks, grace budgets. |
| Graceful không kích hoạt | server.shutdown=immediate, kill -9, JVM PID sai, IDE Stop force | Kiểm config, process signals, lifecycle logs. |
| CORS/authorization gây 403 khi đo | Request bị security/filter từ chối trước khi shutdown | Dùng /ping public local test, không trộn test auth. |
| Probe readiness không trả response sau SIGTERM | HTTP connector đã ngừng accept | Dùng readiness state/lifecycle logs trước signal hoặc orchestrator metrics. |
| Có Reactor Netty library nhưng startup Tomcat | WebClient dependency, MVC vẫn chọn Servlet | Kiểm actual web server factory/startup logs. |
| Requests bị cắt dù timeout 20s | Orchestrator termination grace ngắn hơn hoặc user code lỗi | Kiểm preStop + Boot grace + overhead và pod events. |
| Không thấy HTTP 503 trong app metrics dù client lỗi | Reject trước HTTP handler | Xem client connect errors và edge metrics. |
| POST bị gửi hai lần khi rollout | Unbounded retry on reset/503 | Thêm idempotency key và dedup. |
| WebSocket không giữ qua pod termination | Connection dài hơn grace budget | Thiết kế close/reconnect/resubscribe và durable replay. |
| Shutdown phase kéo dài hơn 20s | Có nhiều lifecycle phases/cleanup khác | Đo từng phase, không coi timeout-per-phase là process total timeout. |

## 18. Bài tập thực hành

**Bài tập 1 — Direct Tomcat:** build profile Tomcat, gọi /slow 15s, gửi SIGTERM khi slow.begin đã log, rồi dùng một curl process mới gọi /ping. Phân loại kết quả HTTP status hay network failure; không coi một dòng lỗi cụ thể là bắt buộc.

**Bài tập 2 — Undertow:** lặp lại với Maven profile Undertow. Dùng cùng 20s grace, cùng 15s in-flight và đo trong 2 giây sau SIGTERM. Quan sát có thể có HTTP 503 trong grace period, rồi network refusal sau khi server tắt.

**Bài tập 3 — Jetty:** lặp với Jetty, so sánh với Tomcat: cả hai network-level rejection nhưng exception/timing có thể không trùng.

**Bài tập 4 — Grace budget:** thử /slow?delayMs=30000 với grace 20s. Đo kết quả, giải thích vì sao in-flight request không nhất thiết hoàn tất; không dùng hard kill để giả lập graceful.

**Bài tập 5 — Client pool:** dùng Java HTTP client giữ connection và gửi request tiếp theo trên socket cũ, so với new HttpClient mỗi lần. Ghi rõ mỗi tình huống HTTP version/pooling.

**Bài tập 6 — Proxy:** đưa app sau Nginx/Ingress local test, gửi SIGTERM rồi so kết quả direct-vs-edge. Nếu edge trả 502/503, xác định nó tự tạo status hay pass-through từ Undertow.

**Bài tập 7 — Kubernetes:** đặt 40s termination grace, 5s preStop và 20s Boot grace, thực hiện rolling update. Đo pod events, failed request rate, readiness và logs; nếu vẫn có 5xx, kiểm propagation và connection reuse.

**Bài tập 8 — Retry safety:** viết client POST có Idempotency-Key, giả lập reset sau commit và kiểm lần retry không nhân đôi transaction. Không coi curl GET probe là đủ để xác minh tính an toàn của thanh toán.

## 19. Checklist triển khai và review

- [ ] Ghi rõ **Spring Boot version** và **embedded server implementation/version**.
- [ ] Với Boot 3.3, bật **server.shutdown=graceful** nếu cần drain.
- [ ] Đặt **spring.lifecycle.timeout-per-shutdown-phase** theo latency/SLO và request workloads.
- [ ] Bảo đảm **SIGTERM tới đúng JVM**; không dùng SIGKILL để mong graceful.
- [ ] Xác minh Tomcat/Jetty/Reactor Netty khác Undertow về **network-level refusal vs HTTP 503**.
- [ ] Không viết alert/retry logic chỉ dựa vào 503; xem network/client errors.
- [ ] Kiểm cả **fresh TCP connection** và **request trên keep-alive connection**.
- [ ] Kiểm trực tiếp tới pod và qua ingress để phân biệt origin của 502/503/504.
- [ ] Có readiness, endpoint drain và Kubernetes terminationGracePeriodSeconds đủ lớn.
- [ ] Tính cả preStop, lifecycle phase timeout và cleanup overhead.
- [ ] Dùng HTTP status và network errors metrics bên phía client/proxy.
- [ ] Không log credentials/cookies/body khi chẩn đoán shutdown.
- [ ] Với POST/PUT/DELETE, có idempotency/retry semantics rõ ràng.
- [ ] Với WebSocket/SSE, có reconnect/close/resubscribe và replay khi cần.
- [ ] Test SIGTERM trên packaged JAR, không chỉ MockMvc unit test.
- [ ] Quan sát in-flight request completion và server graceful shutdown logs.
- [ ] Lặp lại tests khi đổi Tomcat/Jetty/Undertow/Reactor Netty hoặc nâng Spring Boot.
- [ ] Tránh dùng default behavior từ Boot 4.x để mô tả một app Boot 3.3.

## 20. Câu hỏi tự kiểm tra

**1. Vì sao Tomcat không nhất thiết trả HTTP 503 khi graceful shutdown?**  
Vì Boot 3.3 mô tả nó ngừng tiếp nhận request mới ở network layer; nhiều request mới không tới HTTP handler để tạo response.

**2. Server nào thuộc nhóm có thể trả HTTP 503 ngay trong grace period?**  
Undertow trên Spring Boot 3.3.

**3. Ba server nào thuộc nhóm network-level refusal?**  
Tomcat, Jetty, Reactor Netty.

**4. Reactor Netty có phải embedded Servlet container?**  
Không. Nó thường là reactive server WebFlux; Tomcat/Jetty/Undertow là các Servlet server thường dùng.

**5. server.shutdown=graceful có ý nghĩa gì?**  
Cho server giai đoạn ngừng nhận work mới nhưng cho in-flight requests cơ hội hoàn thành khi context dừng.

**6. 20s timeout per shutdown phase có bảo đảm mọi request kết thúc trước 20s không?**  
Không. Đó là grace budget của lifecycle phase, không phải SLA mỗi request.

**7. Vì sao Undertow cũng có thể cho ConnectException sau SIGTERM?**  
Vì sau khi server đã tắt xong, nó không còn listener để trả 503.

**8. Nếu gateway trả HTTP 502 trong khi Tomcat stopping, lỗi từ đâu?**  
Thường là gateway không nhận được HTTP response từ upstream, nhưng phải kiểm logs để xác minh.

**9. Có thể kết luận server type từ một HTTP 503 không?**  
Không. 503 có thể từ Undertow, load balancer, application hoặc component khác.

**10. Vì sao so sánh cần test fresh connection và keep-alive riêng?**  
Vì socket tồn tại trước shutdown có thể xử lý khác kết nối mới, đặc biệt với HTTP/2/pools.

**11. Tại sao không test bằng kill -9?**  
SIGKILL bỏ qua shutdown hooks/cleanup nên không mô phỏng graceful shutdown.

**12. Với Kubernetes preStop 5s, Spring grace 20s, đặt termination grace 20s có đủ không?**  
Không đáng tin, vì chưa có margin cho preStop, request drain và shutdown overhead.

**13. HTTP request không nhận response sau reset có chắc chưa được xử lý không?**  
Không. Business side effect có thể đã commit rồi response bị mất.

**14. Khi Actuator readiness không trả JSON sau SIGTERM, có phải Boot không phát REFUSING_TRAFFIC không?**  
Không nhất thiết. HTTP connector có thể đã dừng nhận request mới.

**15. Có thể dùng WebClient trong MVC rồi kết luận app chạy Reactor Netty server không?**  
Không. Cần xem actual embedded server startup/factory.

## 21. Tài liệu chính thức và tài liệu vận hành

- **Spring Boot 3.3 – Graceful Shutdown:** https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html — cơ chế từ chối khác nhau giữa Tomcat/Jetty/Reactor Netty và Undertow, server.shutdown, timeout-per-shutdown-phase, IDE SIGTERM.
- **Spring Boot 3.3 – Embedded Web Servers:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html — đổi embedded server và starter dependencies cho Servlet/reactive.
- **Spring Boot 3.3 – Servlet Web Applications:** https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html — Tomcat/Jetty/Undertow MVC, ServletWebServerFactory và runtime.
- **Spring Boot 3.3 – Actuator Endpoints / Kubernetes Probes:** https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html — readiness/liveness và lifecycle khi shutdown.
- **Spring Boot 3.3 – Reactor Netty/WebFlux:** https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html — reactive runtime và connector.
- **Spring Framework – SmartLifecycle:** https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html — phase/order và lifecycle stop callback.
- **Kubernetes – Pod Lifecycle:** https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/ — SIGTERM, preStop, grace periods, terminating endpoints.
- **Kubernetes – Container Lifecycle Hooks:** https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/ — preStop và shutdown orchestration.
- **RFC 9110 – HTTP Semantics (503):** https://www.rfc-editor.org/rfc/rfc9110.html — Service Unavailable và Retry-After semantics.
- **RFC 9112 – HTTP/1.1:** https://www.rfc-editor.org/rfc/rfc9112.html — connection management, persistent connections.
