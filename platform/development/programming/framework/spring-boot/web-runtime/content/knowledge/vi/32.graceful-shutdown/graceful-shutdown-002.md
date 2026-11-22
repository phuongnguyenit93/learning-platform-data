# server.shutdown và khác biệt mặc định theo phiên bản Spring Boot

## 1. Mục tiêu và kết luận quan trọng nhất

Một HTTP request đang thực thi có thể bị cắt giữa chừng khi ứng dụng Spring Boot tắt vì deploy phiên bản mới, scale down, restart container hay vận hành thủ công. **Graceful shutdown** giúp embedded web server ngừng nhận requests mới, đồng thời cho những requests đang thực thi **cơ hội hoàn thành trong một ngân sách thời gian giới hạn**.

Spring Boot có property **`server.shutdown`** với hai giá trị:

- **`immediate`:** dừng embedded web server mà không chủ động drain HTTP requests đang chạy.
- **`graceful`:** dừng tiếp nhận requests mới và đợi các requests in-flight hoàn tất **đến khi hết grace period** rồi tiếp tục lifecycle shutdown.

**Mốc thay đổi cần thuộc:** Spring Boot **2.3–3.3 mặc định `immediate`**, trong khi **từ Spring Boot 3.4 mặc định `graceful`**. Phiên bản 2.3 là thời điểm tính năng graceful shutdown được giới thiệu cho embedded web servers; không được nhầm **bắt đầu hỗ trợ** với **đã bật mặc định**.

Bài thuộc nhóm **Dừng có kiểm soát** trong module **Spring Boot - web-runtime**. Sau khi học, bạn có thể:

1. Nêu chính xác giá trị mặc định của `server.shutdown` qua các đời Spring Boot.
2. Phân biệt shutdown **mode** với `spring.lifecycle.timeout-per-shutdown-phase`, HTTP client timeout, Kubernetes termination budget.
3. Mô tả quá trình đóng `ApplicationContext`, stop `SmartLifecycle` beans và shutdown hook.
4. Viết/chạy ứng dụng **Java 17 + Spring Boot 3.3.5** với một endpoint chậm, gửi `SIGTERM` lúc request đang chạy, đối chiếu immediate/graceful/default.
5. Chứng minh thay đổi mặc định ở **Spring Boot 3.4.0** bằng cách đổi Maven parent và chạy lại cùng phép thử.
6. Giải thích khác biệt ở Tomcat, Jetty, Reactor Netty và Undertow, cũng như external WAR container.
7. Thiết kế termination policy cho Kubernetes, readiness, preStop, proxy draining, streaming và background jobs.
8. Kiểm tra các sai lầm thường gặp: `SIGKILL`, IDE Stop, không forward signal, timeout thiếu, tưởng graceful bảo đảm exactly-once.

## 2. Điều gì xảy ra khi ứng dụng đang bận phải dừng?

~~~text
Client A gửi GET /api/work (xử lý 8s)
       |
       v
Spring Boot embedded server :8080
       |
       | Request đã được chấp nhận -> controller đang chạy
       |
Process nhận SIGTERM
       |
       +--> immediate: bắt đầu ngừng server không đợi drain riêng
       |        '--> request đang chạy có thể lỗi/đứt response
       |
       '--> graceful: ngừng nhận new requests
                |---> request A có thể hoàn tất trong grace window
                '---> khi không còn active requests hoặc hết timeout
                      mới tiếp tục đóng web server / context
~~~

**Request in-flight** là request đã được server tiếp nhận trước khi shutdown bắt đầu; **new request** là request đến sau thời điểm ngừng nhận traffic. Việc phân loại ở sát ranh giới thời gian có thể có race; TCP connection mới, HTTP keep-alive, request đã ở queue hoặc reverse proxy có thể không diễn biến giống nhau.

Trong mode graceful:

- Requests **đã chạy** có cơ hội trả HTTP response hoàn chỉnh.
- Requests **mới** bị từ chối theo cách phụ thuộc embedded server và network.
- Không bắt buộc dừng tròn đúng 20/30 giây; nếu mọi request xong sớm, server có thể dừng sớm.
- Khi hết ngân sách, server có thể đóng connections đang xử lý và client thấy reset, EOF hoặc response không đầy đủ.
- Không đảm bảo client vẫn còn chờ, DNS/proxy không lỗi, hay business side effect chưa/đã commit.

**Graceful ≠ bất tử, và immediate ≠ chắc chắn mọi request thất bại.** Graceful chỉ cải thiện xác suất hoàn tất HTTP exchange khi dừng **có chủ đích và đúng quy trình**.

## 3. Bảng phiên bản: sự thay đổi mặc định ở Boot 3.4

Đây là phần quan trọng nhất vì nhiều tutorial cũ đưa ra một mặc định khác tutorial mới:

| Spring Boot version | Tính năng embedded graceful shutdown | `server.shutdown` khi không cấu hình |
| --- | --- | --- |
| **2.2 trở xuống** | Chưa có property/tích hợp graceful chuẩn được giới thiệu từ 2.3 | Không áp dụng cùng cơ chế |
| **2.3.x** | Có; được giới thiệu ở 2.3 | **`immediate`** |
| **2.4–2.7** | Có | **`immediate`** |
| **3.0–3.3** | Có | **`immediate`** |
| **3.4.x** | Có; **đổi mặc định** trong 3.4 | **`graceful`** |
| **3.5.x** | Có | **`graceful`** |
| **4.0/4.1** | Có với embedded web servers được docs của phiên bản đó liệt kê | **`graceful`** |

Các tài liệu gốc:

- **Spring Boot 2.3 Release Notes** trình bày “Graceful shutdown” và yêu cầu bật bằng `server.shutdown=graceful`.
- **Spring Boot 3.3 Reference** ghi “To enable graceful shutdown” với cấu hình `server.shutdown=graceful`.
- **Spring Boot 3.3 Common Application Properties** ghi default của `server.shutdown` là **`immediate`**.
- **Spring Boot 3.4 Release Notes** thông báo embedded web-server graceful shutdown **“now enabled by default”**; có thể khôi phục hành vi cũ bằng `server.shutdown=immediate`.
- **Spring Boot 3.4 và 3.5 docs** ghi graceful “enabled by default”; common properties của 3.4 ghi default là **`graceful`**.
- **Spring Boot 4.x docs** tiếp tục mô tả mặc định graceful nhưng danh sách embedded web servers có thể khác 3.x; kiểm tra đúng nhánh.

**Các URLs được ghim phiên bản** nằm ở phần tham khảo, giúp tránh đọc nhầm trang `/reference/` của bản mới nhất rồi suy sang bản 3.3.

### 3.1. Hai câu có vẻ mâu thuẫn nhưng đều đúng theo thời điểm

- “Muốn graceful, hãy đặt `server.shutdown=graceful`”: đúng như hướng dẫn bật tính năng trong **Boot 2.3–3.3**.
- “Graceful đã bật mặc định”: đúng từ **Boot 3.4 trở lên**, khi ứng dụng dùng embedded server hỗ trợ và không có override.

Không nên nói “Spring Boot mặc định immediate” hoặc “Spring Boot mặc định graceful” mà bỏ qua version. Cả hai settings **vẫn hợp lệ** sau khi mặc định đổi; thay đổi ở default không xóa tùy chọn `immediate`.

### 3.2. Nâng phiên bản có thể thay đổi vận hành mà không đổi application.properties

Giả sử project dùng Boot 3.3.5, tệp config không có `server.shutdown`. Sau khi nâng parent/BOM lên 3.4.0, chính artifact mới có thể chọn graceful thay vì immediate. Một rollout có thể vì thế dừng chậm hơn, cần termination budget phù hợp, nhưng đổi lại giảm rủi ro cắt request.

Nếu shutdown behavior quan trọng, **nên cấu hình tường minh** thay vì phụ thuộc default, nhất là khi nâng version.

## 4. server.shutdown và spring.lifecycle.timeout-per-shutdown-phase khác nhau

Ví dụ cấu hình Boot 3.3.5 để bật graceful:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

| Property | Vai trò | Mặc định tiêu biểu |
| --- | --- | --- |
| `server.shutdown` | Chọn **immediate** hay **graceful** cho embedded web server | Boot ≤3.3: immediate; Boot ≥3.4: graceful |
| `spring.lifecycle.timeout-per-shutdown-phase` | Thời gian tối đa để dừng **mỗi phase** của nhóm `SmartLifecycle` beans | **30s** trong Boot 3.3/3.4 |
| `server.port` | HTTP listener port | Thường 8080 |
| `server.tomcat.connection-timeout` | Timeout một phần lifecycle của kết nối TCP/HTTP Tomcat | Không phải grace period |
| `spring.task.execution.shutdown.await-termination` | Cho executor auto-configured chờ jobs đang chạy | false ở Boot 3.3 |
| `spring.task.scheduling.shutdown.await-termination` | Cho scheduler auto-configured chờ jobs đang chạy | false ở Boot 3.3 |

`spring.lifecycle.timeout-per-shutdown-phase=20s` **không** có nghĩa:
- JVM luôn exit sau đúng 20 giây.
- Mọi HTTP request bình thường chỉ được tối đa 20 giây.
- Mỗi tác vụ DB, Kafka, RestClient/WebClient tự được timeout 20 giây.
- Tổng thời gian đóng tất cả phases/beans chắc chắn không quá 20 giây.

Nó là ngân sách **cho mỗi shutdown phase** của `LifecycleProcessor`. Các phases khác nhau và bean destruction có thể cộng thời gian. Grace period cũng không phải delay bắt buộc: nếu active requests không còn, phase có thể hoàn tất trước timeout.

### 4.1. application.yml

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

### 4.2. Command-line override

~~~bash
java -jar target/shutdown-lab-0.0.1-SNAPSHOT.jar \
  --server.shutdown=graceful \
  --spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Lệnh trên dành cho shell POSIX. Với Windows PowerShell, viết trên một dòng hoặc dùng cú pháp nối dòng riêng của PowerShell thay vì dấu gạch chéo ngược.

### 4.3. Environment variables

~~~bash
export SERVER_SHUTDOWN=graceful
export SPRING_LIFECYCLE_TIMEOUT_PER_SHUTDOWN_PHASE=20s
java -jar target/shutdown-lab-0.0.1-SNAPSHOT.jar
~~~

Spring Boot relaxed binding có thể map env vars vào properties. Nếu profile, CLI args hoặc một nguồn property ưu tiên cao hơn override, giá trị **effective** có thể khác những gì bạn đọc trong `application.properties`. Khi chẩn đoán production, kiểm tra cả Helm values, env, ConfigMap, command-line và runtime artifact.

### 4.4. Lựa chọn tường minh theo mục tiêu

~~~properties
# Policy muốn drain HTTP ở cả Boot 3.3 và 3.4:
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=25s
~~~

Hoặc:

~~~properties
# Cần phục hồi hành vi cũ ở Boot 3.4+:
server.shutdown=immediate
~~~

Đặt immediate có thể giúp dừng nhanh hơn nhưng có thể tăng lỗi từ requests đang chạy; phải chấp nhận trade-off sau khi đánh giá workload.

## 5. Spring Context và SmartLifecycle: shutdown hoạt động ở đâu?

Spring Boot ứng dụng thường đăng ký **JVM shutdown hook** cho `ApplicationContext`. Khi Java process nhận signal mà JVM có thể xử lý như `SIGTERM`, Spring tiến hành đóng context.

~~~text
SIGTERM -> Java shutdown hook
                |
                v
        Closing ApplicationContext
                |
                v
        Stop SmartLifecycle phases
                |
                +--> web server graceful drain
                |     (earliest phase of stopping)
                |
                +--> dừng các SmartLifecycle beans khác
                |
                v
        Bean destruction callbacks
        (@PreDestroy, DisposableBean, destroy methods)
                |
                v
        Resource cleanup và process exit
~~~

Sơ đồ trên mô tả tổng quan, **không cam kết order tuyệt đối của mọi custom bean**. Spring Boot docs nêu web-server graceful shutdown được thực hiện trong **earliest phase of stopping SmartLifecycle beans**. Khi có custom executors, consumer lifecycle hoặc clients, phải kiểm tra phase/dependency riêng.

### 5.1. Thứ tự phase và thời gian

`SmartLifecycle` có methods như `start()`, `stop(Runnable callback)` và `getPhase()`. Spring tổ chức stop theo phases; nhóm beans trong cùng phase có thể dừng song song/đồng thời theo semantics của lifecycle processor. **Timeout-per-shutdown-phase** giới hạn thời gian xử lý một phase, không giới hạn tổng số phases.

Ví dụ tưởng tượng:

~~~text
Phase web server drain:       12s
Phase message consumers:       8s
Bean/resource destruction:     3s
----------------------------------
Tổng thời gian đóng:          23s
~~~

Dù timeout-per-phase là 20s, tổng có thể **23s** nếu các phases không vượt ngân sách. Đây là ví dụ tính toán minh họa, không phải số đo thật hay contract rằng phase order cố định như bảng.

### 5.2. Graceful không dừng tất cả nghiệp vụ theo cùng policy

Ngay cả khi web requests đã được drain:
- Một `@Scheduled` job có thể vẫn chạy.
- Kafka/Rabbit consumers có lifecycle riêng.
- Custom thread pool có thể giữ threads.
- JDBC connection pool phải còn sống đủ lâu cho những requests đang dùng nó.
- Tracing/logging exporters có thể cần flush.
- Có thể tồn tại long-lived WebSocket/SSE connections hoặc streams.

Cần config shutdown cho những thành phần này **tách biệt** với `server.shutdown`, không dựa vào một flag để đảm bảo hết mọi công việc.

## 6. Embedded web servers: không phải tất cả đều trả HTTP 503

Trong **Spring Boot 3.3/3.5**, tài liệu graceful shutdown nêu bốn embedded servers: **Tomcat, Jetty, Reactor Netty, Undertow**. Khi graceful đang diễn ra, cách từ chối new requests có khác biệt:

| Server | Hành vi từ chối new requests theo docs Boot 3.x |
| --- | --- |
| **Tomcat** | Ngừng chấp nhận requests mới ở network layer |
| **Jetty** | Ngừng chấp nhận requests mới ở network layer |
| **Reactor Netty** | Ngừng chấp nhận requests mới ở network layer |
| **Undertow** | Có thể tiếp nhận connections mới nhưng trả **HTTP 503 Service Unavailable** ngay |

**Không kỳ vọng một status cố định cho tất cả.** Trên Tomcat/Jetty/Netty, curl có thể thấy connection refused, reset hoặc kết nối bị đóng thay vì HTTP response 503. Với Undertow ở nhánh hỗ trợ, có thể thấy 503. Nếu request đến đúng sát thời điểm shutdown, kết quả còn phụ thuộc race/network/proxy.

**Thận trọng với Spring Boot 4.x:** tài liệu hiện hành liệt kê Tomcat, Jetty và Reactor Netty trong mục graceful shutdown. Không copy ma trận Undertow của Boot 3.x để khẳng định có cùng support ở mọi version 4.x mà chưa xác minh module/container tương ứng.

### 6.1. Giới hạn của external WAR container

`server.shutdown` quản lý **embedded web server do Spring Boot sở hữu**. Khi triển khai WAR vào **external Tomcat/Jetty** do hệ thống ngoài quản lý, việc drain listener là trách nhiệm của container và hạ tầng đó. Chỉ đặt `server.shutdown=graceful` trong WAR không đủ để buộc external container ngừng nhận HTTP đúng policy; xem cấu hình app server/ingress riêng.

### 6.2. Keep-alive, HTTP/2 và reverse proxy

HTTP keep-alive connections có thể tồn tại trước shutdown. New HTTP request trên một connection cũ cũng có thể bị từ chối khi drain, tùy implementation. HTTP/2 có nhiều streams chia sẻ connection, nên ngữ nghĩa GOAWAY/stream draining khác HTTP/1.1. Proxy/ingress có kết nối tái sử dụng riêng, cần test ở thực tế nếu app phục vụ traffic qua load balancer.

## 7. SIGTERM, SIGINT và SIGKILL: điều kiện để graceful thực sự chạy

| Cách dừng | Khả năng chạy Spring/JVM cleanup | Ghi chú |
| --- | --- | --- |
| `SIGTERM` đến Java PID | Có theo đường lifecycle thông thường | Cách test đáng tin trong Linux/Unix/K8s |
| `SIGINT` hoặc `Ctrl+C` | Thường có, tùy terminal và runtime | Cần biết tool/process manager gửi signal gì |
| `SIGKILL` / `kill -9` | **Không** | JVM không chạy shutdown hooks |
| IDE Stop / Terminate | Tùy IDE | Có IDE kill process ngay, không graceful |
| Process crash/JVM fatal issue | Không bảo đảm | Có thể không cleanup |
| `ApplicationContext.close()` | Kích hoạt context lifecycle | Không hoàn toàn giống SIGTERM của deploy |
| Container stop | Thường TERM rồi KILL nếu hết grace budget | PID 1, wrapper, orchestrator ảnh hưởng |

SpringApplication mặc định đăng ký shutdown hook để đóng context. Nếu lập trình viên tắt hook hoặc process bị kill cưỡng bức, dù property ghi `graceful` vẫn có thể không drain.

### 7.1. Docker ENTRYPOINT và PID 1

Một Docker image nên chuyển signal tới Java đúng cách:

~~~dockerfile
# Phần cuối Dockerfile, khi image đã có JRE và app.jar:
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Trong khi shell form:

~~~dockerfile
# Dễ xảy ra vấn đề nếu shell không forward signal:
ENTRYPOINT java -jar /app/app.jar
~~~

có thể khiến Java chạy dưới shell PID 1 và không nhận TERM đúng kỳ vọng. Nếu cần wrapper script, dùng `exec java -jar ...` hoặc init/process manager phù hợp, rồi **kiểm thử thực tế**. Không suy từ một log “Starting” rằng TERM chắc chắn đến Java process.

### 7.2. Vì sao test bằng IDE có thể cho kết quả sai?

Spring Boot docs lưu ý IDE có thể dừng process bằng cơ chế không gửi proper `SIGTERM`, làm graceful không diễn ra như mong đợi. Vì vậy bài lab dưới đây build executable JAR rồi dùng `kill -TERM` gửi thẳng tới Java PID, thay vì chỉ bấm nút Stop và kết luận config sai.

## 8. Lab: Spring Boot 3.3.5, Java 17, request 8 giây

Tạo một project nhỏ có:
- `GET /api/ping` trả response nhanh.
- `GET /api/work?ms=8000` xử lý 8 giây bằng `Thread.sleep` (chỉ nhằm minh họa).
- `application.properties` **không có `server.shutdown`**, để kiểm tra default của Boot 3.3.
- Script Bash khởi động trực tiếp Java, đợi server ready, phát request chậm, gửi TERM giữa chừng, ghi kết quả curl và server log.

### 8.1. Cấu trúc tệp

~~~text
shutdown-lab/
├── pom.xml
├── run-case.sh
└── src/main/
    ├── java/com/example/shutdown/
    │   ├── ShutdownLabApplication.java
    │   └── WorkController.java
    └── resources/
        └── application.properties
~~~

Thực hành trên Linux/macOS/WSL với Bash/curl/Maven/JDK 17. Spring Boot 3.3.5 và 3.4.0 cùng chạy trên Java 17 cho phạm vi code của lab. Không thực hiện thí nghiệm dừng cưỡng bức trên production.

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>shutdown-lab</artifactId>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
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

`spring-boot-starter-web` mang MVC và embedded Tomcat. `spring-boot-starter-actuator` giúp probe health/readiness; không cần Actuator để property graceful hoạt động.

### 8.3. Main class

**Tệp `src/main/java/com/example/shutdown/ShutdownLabApplication.java`:**

~~~java
package com.example.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShutdownLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShutdownLabApplication.class, args);
    }
}
~~~

### 8.4. WorkController.java

**Tệp `src/main/java/com/example/shutdown/WorkController.java`:**

~~~java
package com.example.shutdown;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class WorkController {

    private final AtomicInteger sequence = new AtomicInteger();

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/work")
    public ResponseEntity<String> work(
            @RequestParam(defaultValue = "8000") int ms) {
        if (ms < 0 || ms > 30000) {
            return ResponseEntity.badRequest().body("invalid ms");
        }

        int id = sequence.incrementAndGet();
        System.out.printf(
                "START id=%d ms=%d at=%s thread=%s%n",
                id, ms, Instant.now(),
                Thread.currentThread().getName());

        try {
            Thread.sleep(ms); // CHỈ TRONG LAB.
            System.out.printf(
                    "FINISH id=%d at=%s%n",
                    id, Instant.now());
            return ResponseEntity.ok("completed:" + ms);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            System.out.printf(
                    "INTERRUPTED id=%d at=%s%n",
                    id, Instant.now());
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("interrupted:" + ms);
        }
    }
}
~~~

**Phân tích:**

1. `AtomicInteger` đánh ID cho requests (reset khi restart), giúp nhận diện trong log.
2. `/api/ping` là endpoint control để biết server đã ready.
3. `Thread.sleep(ms)` giữ một Tomcat worker **cố tình**. Trong production, không sleep trong controller để xử lý nghiệp vụ.
4. Nếu chờ xong, server log `FINISH` và cố trả body `completed:8000`.
5. Nếu thread bị interrupt, code log `INTERRUPTED` và cố trả 503; nếu connection đã đóng, client **không chắc nhận được body**. Không suy chỉ từ log FINISH rằng browser nhận đủ response.
6. `ms` bị giới hạn 0..30000 để tránh cho tham số demo giữ worker tùy ý trong thời gian quá dài; lab chỉ bind localhost.

### 8.5. application.properties

**Tệp `src/main/resources/application.properties`:**

~~~properties
server.address=127.0.0.1
server.port=8080

spring.lifecycle.timeout-per-shutdown-phase=20s

# CỐ Ý KHÔNG ĐẶT server.shutdown Ở ĐÂY.
# Test default của từng Boot version và CLI override.

management.endpoints.web.exposure.include=health,info
management.health.probes.enabled=true
management.endpoint.health.show-details=never
~~~

Không khai báo `server.shutdown` trong file chung để test default. Nếu thêm `server.shutdown=graceful` ở đây, case default 3.3 không còn thực sự dùng mặc định.

### 8.6. Maven build

Trong thư mục `shutdown-lab`:

~~~bash
mvn clean package
java -version
~~~

Artifact:

~~~text
target/shutdown-lab-0.0.1-SNAPSHOT.jar
~~~

Chạy executable JAR trực tiếp khi thử signal; `mvn spring-boot:run` có thể thêm một lớp process/plugin, khiến bạn khó chắc chắn signal đã tới đúng Java PID.

## 9. run-case.sh: tự động kiểm thử SIGTERM và in-flight request

**Tệp `run-case.sh`**, tạo cạnh `pom.xml`:

~~~bash
#!/usr/bin/env bash

# CASE nhận từ arg 1, nếu thiếu thì dùng default.
CASE=default
if [ "$#" -ge 1 ]; then
    CASE="$1"
fi

MODE_ARG=""
if [ "$CASE" = "graceful" ]; then
    MODE_ARG="--server.shutdown=graceful"
elif [ "$CASE" = "immediate" ]; then
    MODE_ARG="--server.shutdown=immediate"
elif [ "$CASE" != "default" ]; then
    echo "Usage: bash run-case.sh default|graceful|immediate" >&2
    exit 2
fi

JAR=target/shutdown-lab-0.0.1-SNAPSHOT.jar
if [ ! -f "$JAR" ]; then
    echo "Missing jar: run mvn clean package" >&2
    exit 2
fi

# Lệnh JAVA chạy background và lưu PID.
# Unquoted $MODE_ARG chỉ tạo một CLI arg hoặc không có arg.
java -jar "$JAR" $MODE_ARG \
    --spring.lifecycle.timeout-per-shutdown-phase=20s \
    > server.log 2>&1 &
APP_PID=$!

cleanup() {
    kill -TERM "$APP_PID" 2>/dev/null || true
}
trap cleanup EXIT

READY=no
for i in $(seq 1 60); do
    if curl -fsS --max-time 1 \
        http://127.0.0.1:8080/api/ping \
        > /dev/null 2>&1; then
        READY=yes
        break
    fi
    sleep 1
done

if [ "$READY" != "yes" ]; then
    echo "Server not ready; inspect server.log" >&2
    exit 1
fi

echo "App PID=$APP_PID case=$CASE ready"

# Đưa một request 8 giây vào server.
curl -sS --max-time 18 \
    -w '\nHTTP_STATUS=%{http_code}\nTOTAL_SECONDS=%{time_total}\n' \
    'http://127.0.0.1:8080/api/work?ms=8000' \
    > client.out 2> client.err &
CURL_PID=$!

# Cho controller bắt đầu, rồi gửi TERM vào JVM.
sleep 2
echo "Sending SIGTERM to Java PID=$APP_PID"
kill -TERM "$APP_PID"

# Không dùng set -e, để vẫn in kết quả dù curl fail.
wait "$CURL_PID"
CURL_EXIT=$?
echo "curl exit code=$CURL_EXIT"
echo "--- client.out ---"
cat client.out
echo "--- client.err ---"
cat client.err

wait "$APP_PID" 2>/dev/null
trap - EXIT

echo "--- app shutdown log excerpts ---"
grep -E 'START id=|FINISH id=|INTERRUPTED id=|Graceful' \
    server.log || true
~~~

Script đủ để chạy trên Bash/Linux/macOS/WSL với `curl`, `seq`, JDK 17, Maven. **Không chạy nhiều cases cùng lúc**, vì chúng dùng chung port 8080. Script tạo `server.log`, `client.out` và `client.err` và **ghi đè** ở lần chạy tiếp theo; đổi tên logs sau mỗi run nếu cần lưu bằng chứng.

**Cảnh báo về race:** `sleep 2` thường đủ để controller ghi `START` trên máy local bình thường. Trên máy quá tải, nếu chưa thấy START trong server.log trước SIGTERM, thử tăng độ trễ hoặc bổ sung đồng bộ test; không dùng một request chưa chạy để kết luận graceful không hoạt động.

### 9.1. Chạy 3 cases

~~~bash
mvn clean package

bash run-case.sh graceful
bash run-case.sh immediate
bash run-case.sh default
~~~

`CASE=default` giữ `MODE_ARG` rỗng nên app dùng default thật (nếu không có env/other property override). `CASE=graceful` và `CASE=immediate` truyền CLI arg tương ứng.

### 9.2. Kỳ vọng khi graceful trên Boot 3.3.5

Request `8000ms` đã START trước khi nhận TERM; grace period mỗi phase `20s`. Trong tình huống bình thường, server có thể drain thành công:

~~~text
START id=1 ms=8000 at=... thread=http-nio-8080-exec-...
FINISH id=1 at=...
~~~

Client response thường có:

~~~text
completed:8000
HTTP_STATUS=200
~~~

Timestamp/thread name/total time có thể khác. Nếu client/proxy tự timeout trước hoặc process bị force kill, kết quả có thể khác mặc dù đã bật graceful. Khi tất cả active requests đã hoàn tất, process thường đóng mà **không đợi hết 20 giây**.

### 9.3. Kỳ vọng khi immediate

Với server stop trước khi controller trả response, client có thể nhận `curl` error:

~~~text
curl: (52) Empty reply from server
~~~

hoặc:

~~~text
curl: (56) Recv failure: Connection reset by peer
~~~

hoặc một kết quả khác tùy hệ điều hành, container và race. Khi không có HTTP response, `HTTP_STATUS` từ curl có thể là `000`. Đây là **ví dụ khả dĩ**, không phải output deterministic; immediate chỉ không chủ động drain, không cam kết mọi request bắt buộc fail.

### 9.4. Case default trên 3.3.5

Khi `server.shutdown` không được khai báo, **Boot 3.3.5 mặc định immediate**, nên case default thường có diễn biến tương tự explicit immediate. Nếu không, kiểm tra `SERVER_SHUTDOWN`, command line, environment, profile, artifact version và request có START trước TERM hay chưa.

## 10. Lặp lại cùng lab trên Boot 3.4 để thấy default đổi

Cách kiểm chứng theo đúng version:

1. Copy dự án thành một bản lab khác hoặc ghi lại Git diff (đừng mất bản 3.3).
2. Trong `pom.xml`, sửa **chỉ phiên bản Spring Boot parent** `3.3.5` thành **`3.4.0`**.
3. Giữ Java controller và script giống hệt.
4. Không thêm `server.shutdown` vào `application.properties` và không đặt env override.
5. Build lại và chạy default, rồi explicit immediate:

~~~bash
mvn clean package
bash run-case.sh default
bash run-case.sh immediate
~~~

Trong `pom.xml` sau đổi:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.0</version>
    <relativePath/>
</parent>
~~~

**Kỳ vọng quan trọng:** trên **3.4.0**, case `default` hành xử giống `graceful` vì Boot 3.4 đổi mặc định; case `immediate` vẫn phục hồi cách dừng cũ. Điều này được xác nhận bởi Release Notes và config metadata của 3.4.

Trong thực tế, nâng 3.3 → 3.4 có nhiều thay đổi dependency/API khác. Đừng lấy lab đơn giản làm bằng chứng dự án production tự tương thích; cần test framework/security/data integrations và deployment.

## 11. Hết grace period thì sao?

Giả sử request cần 15 giây nhưng bạn đặt:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=3s
~~~

Nếu SIGTERM đến khi request mới chạy được 1 giây, web server chỉ có **khoảng 3 giây** ở phase drain để chờ. Nếu request chưa hoàn tất, shutdown sẽ tiếp tục; response có thể bị cắt, socket đóng, client báo lỗi. **Không có guarantee mọi request 15s đều được hoàn thành**.

Ngược lại, request 8s và phase limit 20s thường kịp. Đây là giới hạn **khi shutdown**; trong thời gian vận hành bình thường, request vẫn chịu HTTP/client/proxy timeouts riêng.

### 11.1. “20 giây” không phải deadline tổng của JVM

Nếu lifecycle có nhiều phases và resource cleanup, tổng thời gian stop có thể dài hơn 20s. Nếu có orchestrator `terminationGracePeriodSeconds=15` thì `SIGKILL` có thể xảy ra **trước khi** phase timeout 20s hết; cấu hình Spring không thể ép Kubernetes chờ lâu hơn chính sách của nó.

### 11.2. Nếu requests vô hạn: WebSocket/SSE/long polling

Một WebSocket có thể mở hàng giờ; một SSE/`Flux.never()` có thể không bao giờ complete. Nếu dựa vào graceful để chờ cho chúng tự hoàn thành, shutdown có thể hết timeout. Cần thiết kế:

- Chủ động đóng stream, báo sự kiện server-draining.
- Client reconnect/backoff và re-subscribe/recover dữ liệu.
- Checkpoint/offset/replay nếu cần không mất messages.
- Giới hạn session idle/max duration và xử lý cancellation.
- Không dựa vào `server.shutdown=graceful` làm cơ chế durable delivery.

## 12. Readiness và lifecycle trong Kubernetes

Một pod bị terminate không chỉ là một Java method được gọi:

~~~text
Kubernetes bắt đầu terminate Pod
       |
       +--> cập nhật trạng thái terminating/EndpointSlices
       |    các LB/ingress cần thời gian đồng bộ
       |
       +--> preStop hook (nếu có)
       |
       +--> gửi SIGTERM tới process trong container
       |
       +--> Spring đóng ApplicationContext
       |      +--> ReadinessState = REFUSING_TRAFFIC
       |      '--> web server ngừng nhận new HTTP requests
       |            và drain in-flight nếu graceful
       |
       +--> background components / resources shutdown
       |
       '--> nếu hết termination budget mà chưa exit: SIGKILL
~~~

**`terminationGracePeriodSeconds` bắt đầu tính từ lúc termination, bao gồm preStop hook**. Đừng cộng preStop 5s với grace 30s rồi quên rằng tổng Pod budget vẫn 30s. Nếu shutdown có nhiều phases, phải dự trù thêm thời gian.

### 12.1. Kubernetes YAML minh họa

Đây là **đoạn trong Pod template** chứ chưa phải Deployment manifest hoàn chỉnh:

~~~yaml
spec:
  terminationGracePeriodSeconds: 45
  containers:
    - name: app
      image: example/shutdown-lab:1.0
      ports:
        - name: http
          containerPort: 8080
      readinessProbe:
        httpGet:
          path: /actuator/health/readiness
          port: http
        periodSeconds: 5
        failureThreshold: 2
      livenessProbe:
        httpGet:
          path: /actuator/health/liveness
          port: http
        periodSeconds: 10
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 5"]
      env:
        - name: SERVER_SHUTDOWN
          value: graceful
        - name: SPRING_LIFECYCLE_TIMEOUT_PER_SHUTDOWN_PHASE
          value: 25s
~~~

Giải thích:

- `terminationGracePeriodSeconds:45` là tổng thời gian Pod được chờ trước force kill.
- `preStop sleep 5` dành một khoảng cho endpoint/ingress propagation **trước SIGTERM**; 5s này bị trừ khỏi tổng budget. Với distroless images thiếu shell/sleep, cần cách khác.
- `25s` là **timeout mỗi phase** ở Spring, không phải tổng thời gian dừng chắc chắn 25s.
- `image` chỉ minh họa, cần build/push image thật; `Spring Boot Actuator` cần nằm trong application để probe routes tồn tại.
- Chọn 45s chỉ là ví dụ: phải đo thời gian drain, các phase khác, preStop, readiness propagation và safety margin.
- Không public Actuator management endpoints không cần thiết; sử dụng network security và probe permissions hợp lý.

### 12.2. ReadinessState khi shutdown

Theo docs Spring Boot Actuator, khi app **Ready**, readiness là `ACCEPTING_TRAFFIC`; khi đang **graceful shutdown**, readiness chuyển `REFUSING_TRAFFIC`, new HTTP requests bị từ chối.

**Lưu ý:** readiness HTTP endpoint có thể **không truy cập được từ bên ngoài ngay khi web server bắt đầu từ chối requests**, vì bản thân probe là một HTTP request mới. Không kết luận readiness chưa cập nhật chỉ vì `curl /actuator/health/readiness` sau TERM bị connection refused. Hãy nhìn logs, actuator availability events trước đó, EndpointSlice state và proxy metrics.

### 12.3. preStop và rollout readiness không thay thế nhau

- Kubernetes có thể đánh dấu Pod terminating để endpoints consumers ngừng chọn backend.
- Ingress/service mesh/LB có thể cập nhật chậm hoặc giữ connections đã mở.
- Một preStop delay có thể giúp giảm race trong topology nhất định, nhưng không đảm bảo mọi proxy đã hết connection.
- Embedded graceful drain vẫn cần nếu còn request đang xử lý.
- Rolling update phải giữ đủ healthy pods sẵn sàng để nhận traffic mới.

### 12.4. Lập ngân sách dựa trên đo đạc

Ví dụ giả định:

| Thành phần | Thời gian đo |
| --- | ---: |
| preStop/route propagation | 5s |
| request drain p99 | 12s |
| các lifecycle phases, producer flush | 7s |
| safety margin | 8s |
| **Tổng ước lượng** | **32s** |

Bạn có thể thử Pod budget 45s và Spring shutdown phase timeout 20–25s, sau đó kiểm chứng dưới workload thật. Đây không phải con số production mặc định đúng cho mọi service: image startup, proxy, số phases, long polling, Kafka flush và database đều có thể thay đổi.

## 13. @Async, @Scheduled, message consumers và DB pool là bài toán riêng

`server.shutdown` **không trực tiếp điều khiển** mọi task trong ứng dụng. Ví dụ:

- Một `@Scheduled` job chạy 60 giây.
- Một message consumer đang xử lý Kafka record.
- Một `@Async` method gọi API bên ngoài.
- Một custom ExecutorService có threads chưa dừng.
- Một JDBC transaction đang commit.
- Một tracing exporter/log appender đang flush buffers.

Nếu chỉ bật web graceful mà đóng DB pool/producer/executor trước khi công việc cần chúng hoàn thành, app vẫn có thể lỗi dữ liệu.

### 13.1. Properties cho executor/scheduler auto-configured ở Boot 3.3

~~~properties
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=20s

spring.task.scheduling.shutdown.await-termination=true
spring.task.scheduling.shutdown.await-termination-period=20s
~~~

Các properties này áp dụng cho **task executor / scheduler được Boot quản lý theo cơ chế phù hợp**, không tự đóng mọi `Executors.newFixedThreadPool` tự tạo trong code. Mặc định `await-termination=false` ở Boot 3.3; cần tính tổng timeouts/lifecycle phases.

Nếu tự tạo executor, hãy:

1. Ngừng nhận tasks mới.
2. Gọi `shutdown()` thay vì `shutdownNow()` ngay từ đầu nếu cần drain.
3. Chờ có timeout.
4. Hủy/rollback/compensate phần còn lại khi hết budget.
5. Đặt resource/bean shutdown ordering đúng; không đóng DB/HTTP client khi jobs còn cần chúng.

### 13.2. Exactly-once và idempotency không đến từ graceful

Một payment POST có thể đã commit thành công nhưng response bị mất khi Pod restart. Client không nhận 200 và retry -> có nguy cơ **double charge**. Bật graceful giúp giảm rủi ro nhưng không bảo đảm exactly-once. Cần `Idempotency-Key`/unique constraints, transaction boundaries, outbox/ack policies phù hợp.

Tương tự, consumer ack trước khi commit có thể mất message; consumer ack sau commit nhưng trước shutdown có thể tạo duplicate khi redeliver. Cần at-least-once/idempotent design, không coi `server.shutdown` giải quyết queue semantics.

## 14. MVC synchronous, MVC async, WebFlux và streaming

Tài liệu Boot 3.3 mô tả graceful với embedded web servers ở Servlet và reactive web apps; tuy nhiên cách giữ công việc là khác nhau.

| Stack/kiểu request | Khi request đang chạy | Điều cần test |
| --- | --- | --- |
| Spring MVC sync | Tomcat worker xử lý, có thể chờ blocking I/O | Đủ grace window và downstream timeout |
| Spring MVC async | `Callable`/`DeferredResult`/`WebAsyncTask` có executor riêng | Executor lifecycle, timeout, cancellation |
| Spring WebFlux | `Mono/Flux` publishers và Netty event loops | Không block event loop, cleanup khi cancel |
| SSE/streaming | Response có thể kéo dài vô hạn | Finite drain period và resume/replay |
| WebSocket | Session có thể mở nhiều giờ | Close/reconnect policy, connection drain |
| HTTP/2 | Nhiều streams trên một connection | GOAWAY/streams/new traffic semantics |

### 14.1. WebFlux snippet độc lập về ví dụ, không phải project đầy đủ

~~~java
package com.example.reactive;

import java.time.Duration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class SlowReactiveController {

    @GetMapping("/reactive-work")
    public Mono<String> work(
            @RequestParam(defaultValue = "8") int seconds) {
        if (seconds < 0 || seconds > 30) {
            return Mono.error(new IllegalArgumentException(
                    "seconds out of range"));
        }
        return Mono.delay(Duration.ofSeconds(seconds))
                .thenReturn("completed:" + seconds);
    }
}
~~~

Đoạn này cần một **WebFlux project riêng** với `spring-boot-starter-webflux`, main class và cấu hình, không dán vào MVC lab để so API route. `Mono.delay` không chặn event loop như `Thread.sleep`. Default graceful/immediate vẫn thuộc **Boot version/config**, không phải đặc tính riêng của WebFlux.

### 14.2. Vì sao timeout quá ngắn không sửa được streaming?

Nếu request trả `Flux.interval(...)` liên tục không kết thúc, graceful timeout 20s không làm stream tự “hoàn tất”. Hệ thống cần phát đóng stream, dùng checkpoint/event ID/resume, đóng WebSocket bình thường và buộc client reconnect tới pod mới. Không tăng timeout lên vài giờ để né việc thiết kế session lifecycle.

## 15. Actuator shutdown endpoint KHÁC property server.shutdown

Hai tên gần giống nhưng chức năng khác nhau:

- **`server.shutdown`** là setting của embedded web server khi **context bị đóng**. Nó không tạo API mới.
- **`/actuator/shutdown`** là endpoint Actuator có thể yêu cầu application shutdown **nếu được enable, expose và authorize** theo config. Endpoint này **disabled by default**.

Do đó:

~~~properties
server.shutdown=graceful
~~~

không có nghĩa HTTP request sau được tự chấp nhận:

~~~bash
curl -X POST http://localhost:8080/actuator/shutdown
~~~

Spring Boot 3.4 còn có thay đổi mô hình endpoint access so với bản cũ, nên không copy hướng dẫn bật Actuator endpoint qua các bản mà không kiểm tra security/authorization. Lab của bài **không cần** bật endpoint này; dùng SIGTERM là đường kiểm tra gần deployment nhất.

**Bảo mật:** không mở Actuator shutdown cho Internet; nếu dùng trong workflow quản trị phải có authentication/authorization/network policy nghiêm ngặt.

## 16. Những lỗi vận hành phổ biến

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Boot 3.3 dừng ngay dù không cấu hình | Default immediate | Bật `server.shutdown=graceful` |
| Nâng Boot 3.3 → 3.4 thì pod dừng lâu hơn | Default đổi sang graceful | Đo drain, tăng termination budget hợp lý hoặc override có chủ đích |
| Graceful vẫn cắt requests trong IDE | IDE Stop không gửi proper SIGTERM | Dùng `java -jar` + `kill -TERM` |
| Dùng `kill -9` mà không thấy cleanup | SIGKILL không chạy hooks | Dùng TERM + budget |
| Container không thấy Java shutdown logs | PID 1 shell không forward signal | Exec-form ENTRYPOINT hoặc wrapper `exec` |
| Grace window 20s nhưng JVM dừng 35s | Có nhiều lifecycle phases/destruction | Đo phases, resource shutdown |
| Grace window 20s nhưng client fail sau 5s | Client/proxy timeout 5s hoặc connection reset | So client/proxy deadlines |
| Tomcat không trả 503 khi shutdown | Network-layer rejection | Đây là server-specific expected behavior |
| Undertow trả 503 cho new requests | Behavior Boot 3.x Undertow | Không coi 503 là lỗi graceful |
| `/actuator/health/readiness` không truy cập được sau TERM | Web listener từ chối new traffic | Quan sát availability/endpoint state external |
| `@Scheduled` bị ngắt khi HTTP graceful | Scheduler lifecycle riêng | Cấu hình await termination và job recovery |
| `@Async` chưa finish mà context đóng | Executor shutdown budget không phù hợp | Điều chỉnh executor/lifecycle |
| WAR trên external Tomcat không drain như mong muốn | Container không thuộc quyền Boot | Cấu hình external server draining |
| Nhiều payments duplicate sau restart | Retry side effect không idempotent | Thêm idempotency/transactional handling |
| WebSocket/SSE chặn shutdown lâu | Long-lived streams chưa có close policy | Chủ động đóng/reconnect/resume |
| Tăng grace period nhưng vẫn bị KILL | K8s terminationGracePeriodSeconds ngắn | Sắp xếp preStop + phases + cleanup dưới deadline |
| Cấu hình ghi graceful nhưng app immediate | Env/CLI/profile override, sai artifact | Xác minh effective property/Boot version |
| Test client chưa START trước TERM | Test race | Đồng bộ theo START log hoặc tăng delay |

### 16.1. Quy trình debug theo thứ tự

1. Xác nhận **Maven BOM / JAR runtime version** thực sự 3.3, 3.4 hay mới hơn.
2. Xác nhận **effective server.shutdown** sau khi merge properties/env/CLI.
3. Xác nhận process nhận **SIGTERM**, không bị SIGKILL/IDE terminate cưỡng bức.
4. Xác nhận request đã được controller **START** trước signal.
5. Xác nhận embedded web server type, không external WAR.
6. Xác nhận `spring.lifecycle.timeout-per-shutdown-phase`, proxy/client timeouts và Pod termination budget.
7. Xem logs graceful start/complete và client HTTP response **cả status lẫn body**.
8. Kiểm tra `SmartLifecycle` phases khác, executors, DB, messaging.
9. Test dưới một workload có concurrency, keep-alive, long-lived connections.
10. Chỉ sửa một biến mỗi lần và đo lại error rate, latency, duration shutdown.

## 17. Vì sao version default có ý nghĩa khi rolling update?

**Với Boot 3.3 default immediate:** khi Pod nhận SIGTERM, request trong flight dễ bị cắt nếu app không bật graceful. Nếu client tự retry, có thể thêm tải và gây duplicate non-idempotent operations.

**Với Boot 3.4 default graceful:** Pod có thể tiếp tục tồn tại thêm thời gian trong grace window để xử lý requests đang chạy. Nếu HPA/rollout chỉ dựa vào thời gian dừng ngắn trước đây, việc nâng version có thể làm rollout chậm hơn hoặc gặp giới hạn terminationGracePeriodSeconds.

**Với config explicit:** operator biết chắc policy mong muốn. Cách làm có thể gồm:
- Viết `server.shutdown=graceful` tường minh ngay cả trên 3.4.
- Chọn phase timeout theo request SLO và các lifecycle phases.
- Tính termination budget đầy đủ và không để SIGKILL xảy ra trước khi drain xong.
- Đảm bảo luôn đủ số healthy replicas để phục vụ traffic mới trong rolling update.
- Có dashboards/alerts cho 5xx, client resets và shutdown duration.

Không có giải pháp “chỉ bật graceful là zero downtime”; phải phối hợp application, client retry/idempotency, ingress, load balancer và orchestration.

## 18. Bài tập thực hành bổ sung

### Bài tập A — đổi duration

Chạy server `graceful` nhưng với `spring.lifecycle.timeout-per-shutdown-phase=3s`, đồng thời gửi `/api/work?ms=15000` trước TERM. Dự đoán client bị đứt response hoặc reset, và giải thích vì sao property không hủy business transaction một cách an toàn.

### Bài tập B — kiểm tra requests mới khi draining

Trong thời gian request chậm đang chạy, gửi SIGTERM rồi thử:

~~~bash
curl -v --max-time 2 http://127.0.0.1:8080/api/ping
~~~

Khi Tomcat đã bắt đầu graceful drain, request mới thường bị từ chối ở network layer. Trên Undertow 3.x khi được cấu hình tương đương, docs mô tả new requests có thể nhận 503. Không kỳ vọng deterministic nếu Java process đã exit hoặc request race với shutdown.

### Bài tập C — thay đổi default qua Maven parent

Build cùng code trên `3.3.5` và `3.4.0`, **không** khai báo `server.shutdown`. Thử `bash run-case.sh default` và `bash run-case.sh immediate` cho mỗi version. Đối chiếu log và client response; giải thích vì sao explicit setting thắng default.

### Bài tập D — check env/CLI precedence

~~~bash
export SERVER_SHUTDOWN=immediate

java -jar target/shutdown-lab-0.0.1-SNAPSHOT.jar \
  --server.shutdown=graceful
~~~

Trong config binding thông thường của Boot, command-line property `--server.shutdown=graceful` có ưu tiên cao hơn environment variable `SERVER_SHUTDOWN=immediate`. Sau thử nghiệm:

~~~bash
unset SERVER_SHUTDOWN
~~~

Trong hệ thống dùng config sources đặc biệt, xác minh effective value theo môi trường thực.

### Bài tập E — dừng job nền

Bật scheduler hoặc async task dài và so sánh:

~~~properties
spring.task.scheduling.shutdown.await-termination=false
~~~

với:

~~~properties
spring.task.scheduling.shutdown.await-termination=true
spring.task.scheduling.shutdown.await-termination-period=15s
~~~

Đây là bài tập **mở rộng cần thêm `@EnableScheduling` và một scheduled method trong project riêng**; lab gốc không có scheduled job. Hãy giải thích vì sao graceful HTTP khác với bảo đảm job đã commit và vì sao cần tính thêm shutdown phases.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Boot bắt đầu hỗ trợ graceful shutdown từ bản nào và bắt đầu **bật mặc định** từ bản nào?

**Câu 2.** Boot 3.3.5 không khai báo `server.shutdown` sẽ dừng kiểu gì? Boot 3.4.0 thì sao?

**Câu 3.** Có thể tắt graceful ở Boot 3.4+ bằng property nào?

**Câu 4.** `timeout-per-shutdown-phase=20s` có bảo đảm JVM exit trong đúng 20s không?

**Câu 5.** Tại sao đặt `server.shutdown=graceful` không tự tạo HTTP endpoint `/actuator/shutdown`?

**Câu 6.** Trên Tomcat graceful, new request có nhất thiết nhận HTTP 503 không?

**Câu 7.** Tại sao `SIGKILL` và một số IDE Stop khiến graceful không chạy?

**Câu 8.** K8s preStop 5s và terminationGracePeriodSeconds 30s còn nguyên 30s cho Java không?

**Câu 9.** Tại sao FINISH log không chứng minh client đã nhận đầy đủ response?

**Câu 10.** Graceful HTTP có đảm bảo `@Scheduled` jobs, Kafka consumers và JDBC transactions hoàn tất không?

**Câu 11.** Vì sao graceful không đảm bảo exactly-once payment processing?

**Câu 12.** Khi upgrade 3.3 → 3.4, vì sao rollout có thể chậm hơn dù code controller không đổi?

**Câu 13.** Có thể dùng `server.shutdown` để cấu hình listener của external WAR container không?

**Câu 14.** Vì sao readiness probe có thể không truy cập được khi app đang graceful?

**Câu 15.** Nêu ít nhất năm thước đo cần có trước khi chọn shutdown timeout production.

**Đáp án định hướng:**

1. Tính năng từ **2.3**; default graceful từ **3.4**.
2. **3.3.5 immediate**, **3.4.0 graceful** nếu không bị override.
3. `server.shutdown=immediate`.
4. Không; là ngân sách cho mỗi SmartLifecycle phase, không phải tổng thời gian stop hay delay cố định.
5. Property là web server shutdown policy; Actuator endpoint bị disable mặc định và có access/exposure riêng.
6. Không, Tomcat thường từ chối ở network layer; Undertow 3.x có thể trả 503.
7. SIGKILL không chạy shutdown hooks; IDE có thể kill process hoặc không gửi proper TERM.
8. Không. preStop nằm trong tổng Pod termination budget.
9. Socket/proxy/client có thể đã đóng trước khi bytes response được chuyển hết.
10. Không. Mỗi component cần lifecycle, executor/consumer policy riêng.
11. Side effect có thể đã commit dù client mất response; cần idempotency key/unique constraints và giao dịch đúng.
12. Default graceful mới có thể chờ requests in-flight thay vì stop ngay; cần budget đúng.
13. Không chỉ bằng Boot embedded server property; external container controls listener.
14. Trong graceful, web server từ chối new HTTP requests, bao gồm probe HTTP.
15. In-flight p99, stream durations, preStop, total phases, background jobs, proxy/client timeouts, Pod budget, resource cleanup, disconnect/error rate.

## 20. Checklist sản xuất

- [ ] Đã xác định Boot version thực của artifact; không dựa vào “latest docs” khi project dùng 3.3.
- [ ] Hiểu mốc 2.3 hỗ trợ graceful, 3.4 đổi default từ immediate sang graceful.
- [ ] Cấu hình `server.shutdown` **tường minh** cho workload quan trọng.
- [ ] Đã lựa chọn `spring.lifecycle.timeout-per-shutdown-phase` bằng số liệu thật, không đoán.
- [ ] Phân biệt per-phase timeout, HTTP client/server timeout và total JVM shutdown time.
- [ ] JVM nhận proper SIGTERM; Docker ENTRYPOINT/PID1 forward signals đúng.
- [ ] Không test graceful bằng kill -9 hoặc IDE Stop không rõ cơ chế.
- [ ] Đã test in-flight request với client status/body, không chỉ FINISH log.
- [ ] Đã test new requests bị reject ở đúng server implementation.
- [ ] Đã đo hiệu ứng keep-alive, HTTP/2, WebSocket, SSE hoặc long-polling nếu dùng.
- [ ] Có lifecycle riêng cho `@Async`, `@Scheduled`, consumers và custom executors.
- [ ] DB/HTTP pools không bị đóng trước khi business work cần chúng hoàn tất.
- [ ] Có idempotency cho operations không an toàn khi client retry.
- [ ] Có readiness/liveness probes, drain policy ở ingress/LB và rolling update headroom.
- [ ] Pod termination budget đủ cho preStop + Spring phases + cleanup + margin.
- [ ] Không expose Actuator shutdown endpoint ra Internet.
- [ ] Đã test trước/sau nâng Boot version và ghi nhận shutdown duration, resets, error rate.

## 21. Tài liệu tham khảo

1. **Spring Boot 2.3 Release Notes** — giới thiệu graceful shutdown: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.3-Release-Notes
2. **Spring Boot 3.3 Graceful Shutdown** — hướng dẫn bật `server.shutdown=graceful`, phân biệt web server: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
3. **Spring Boot 3.3 Common Application Properties** — `server.shutdown` mặc định `immediate`, shutdown phase timeout `30s`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
4. **Spring Boot 3.4 Release Notes** — graceful shutdown enabled by default: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes
5. **Spring Boot 3.4 Graceful Shutdown** — cơ chế mặc định graceful: https://docs.spring.io/spring-boot/3.4/reference/web/graceful-shutdown.html
6. **Spring Boot 3.4 Common Application Properties** — default `server.shutdown=graceful`: https://docs.spring.io/spring-boot/3.4/appendix/application-properties/
7. **Spring Boot 3.5 Graceful Shutdown** — default graceful: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html
8. **Spring Boot 4.x Graceful Shutdown** — tài liệu hiện hành và danh sách embedded servers: https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html
9. **Spring Boot 3.3 Actuator Endpoints** — ApplicationAvailability, readiness trong shutdown: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
10. **Spring Boot 3.3 Task Execution and Scheduling** — executor/scheduler lifecycle: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
11. **Spring Boot 3.3 SpringApplication API** — shutdown hook: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
12. **Spring Framework SmartLifecycle** — phase và stop callbacks: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
13. **Kubernetes Container Lifecycle Hooks** — preStop: https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/
14. **Kubernetes Pod Termination** — grace budget/SIGKILL: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination
15. **Kubernetes Probes** — liveness/readiness/startup: https://kubernetes.io/docs/concepts/workloads/pods/probes/
