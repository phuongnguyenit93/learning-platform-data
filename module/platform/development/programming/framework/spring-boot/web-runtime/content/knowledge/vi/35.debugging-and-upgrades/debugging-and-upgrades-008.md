# Chẩn đoán treo yêu cầu, cạn luồng, event loop bị chặn và timeout

## 1. Mục tiêu của bài Knowledge

Khi một API Spring Boot “quay mãi”, trả 504, không còn đáp ứng hoặc bỗng có p99 tăng mạnh, lỗi nhìn thấy từ phía người gọi chưa cho biết nguyên nhân. Có thể **không có thread nào thực sự deadlock**: request chỉ đang chờ connection từ pool, chờ downstream chậm, xếp hàng ở Tomcat hoặc bị blocking code chiếm Reactor Netty event loop.

Bài thuộc module **Spring Boot - web-runtime**, nhóm **Gỡ lỗi và nâng cấp**. Sau khi học, bạn có thể:

1. Phân biệt **request đang chạy lâu**, **kẹt hàng đợi**, **Servlet thread exhaustion**, **deadlock/lock contention**, **blocking event loop**, **pool acquisition timeout** và **client/proxy timeout**.
2. Xác định request đã tới server chưa bằng dấu mốc proxy, controller, correlation/trace ID và HTTP status.
3. Thu thập **metrics, thread dumps, Java Flight Recorder, CPU/GC, connection pool counters và traces** đúng lúc xảy ra lỗi.
4. Hiểu tại sao **`http.server.requests` chỉ có thể ghi nhận timing sau khi request hoàn tất**, khiến một request treo chưa tạo timer sample.
5. Dùng **Java 17 + Spring Boot 3.3.5** tái hiện 4 hiện tượng ở Spring MVC: Tomcat worker bị giữ, JDBC/Hikari pool hết chỗ, Java monitor contention và downstream chậm.
6. Chạy WebFlux lab để phân biệt **blocking trong `reactor-http-nio-*`** với pipeline non-blocking và offload sang boundedElastic.
7. Chọn timeout đúng tầng: TCP connect, HTTP response/read, client deadline, Hikari acquisition, SQL query, MVC asynchronous, reverse proxy và caller timeout.
8. Đánh giá tác động sau khi nâng Spring Boot/JDK/libraries và áp dụng phương án khắc phục có kiểm soát.

**Nguyên tắc xuyên suốt:** thu thập bằng chứng trước, tạo giả thuyết, thay **một biến** và đo lại. Tăng ngẫu nhiên `server.tomcat.threads.max`, số event-loop threads, Hikari max hoặc thời gian timeout thường chỉ chuyển nút thắt sang nơi khác.

## 2. “Treo” có thể nghĩa nhiều tình huống

Người dùng thấy spinner hoặc HTTP client báo timeout, nhưng các trạng thái thực tế có thể khác nhau:

| Hiện tượng | Bản chất | Bằng chứng cần lấy |
| --- | --- | --- |
| Handler đã vào nhưng chưa trả | Business code/I/O/lock chạy lâu | Request START log, spans, thread dump |
| Handler chưa vào | Connector/worker queue, proxy hoặc network | Proxy access logs, Tomcat busy/queue, server START không có |
| Worker đang chờ pool | Chưa lấy được JDBC/HTTP connection | Pool active/pending/acquire time |
| Worker giữ connection nhưng query chậm | DB query/lock hoặc remote dependency | SQL time, DB locks, outbound span |
| Deadlock thực sự | Chu trình chờ monitor/lock khiến threads không tiến | Nhiều thread dumps, lock owners, JVM deadlock detection |
| WebFlux event loop bị chặn | Ít event-loop threads phải chạy blocking code | `reactor-http-nio-*` stacks và latency của endpoint /fast |
| Client/proxy bỏ chờ | Deadline phía ngoài đã hết dù server vẫn xử lý | Status 504/499/client timeout, backend log FINISH sau đó |
| JVM stop-the-world/GC | Nhiều requests dừng đồng loạt trong pause | GC/JFR, heap, container CPU quota |
| Upstream không còn capacity | 429/503/5xx hoặc read timeout | `http.client.requests`, tracing, dependency metrics |
| Socket hoặc DNS/TLS lỗi | Request không vào controller hoặc fail khi connect | Client connect errors, gateway logs, network traces |

**Không đánh đồng:** “không có phản hồi trong 10 giây” với “thread deadlock” hoặc “CPU quá cao”. Một thread ở `TIMED_WAITING` do `Thread.sleep` có thể giữ Tomcat worker mà hầu như không tiêu thụ CPU. Một thread `RUNNABLE` không đồng nghĩa nó đang thực sự sử dụng một CPU core.

## 3. Nhìn toàn bộ đường đi của request

### 3.1. Spring MVC / Tomcat

~~~text
Caller
  |
  +-- DNS / TLS / client connection pool
  |
  +-- Load balancer / ingress / proxy timeout
  |
  +-- TCP accept / connector queue (Tomcat)
  |
  +-- Servlet worker thread
         |
         +-- Filter / Spring Security / DispatcherServlet
         |
         +-- Controller + service / CPU / lock
         |
         +-- Hikari JDBC connection acquisition
         |      '-- SQL / DB locks / DB server
         |
         '-- RestClient outbound connection / network
                '-- remote HTTP service / downstream DB
  |
  '-- HTTP response bytes -> caller
~~~

**MVC đồng bộ:** một Servlet worker thường bị giữ trong suốt đoạn xử lý blocking. Nếu 200 requests đến cùng lúc nhưng chỉ 20 workers sẵn sàng, một phần sẽ chờ. Nhưng ngay cả khi Tomcat busy=max, nút thắt gốc có thể là downstream 5 giây khiến mỗi worker bị giữ lâu.

### 3.2. Spring WebFlux / Reactor Netty

~~~text
Caller -> Reactor Netty event loop
                 |
                 +-- Handler publishes Mono/Flux
                 |       |
                 |       +-- non-blocking timers, WebClient, reactive DB
                 |       |
                 |       '-- Thread.sleep / JDBC / .block ?
                 |             blocking event loop -> nhiều sockets chậm
                 |
                 '-- write response khi publisher phát tín hiệu
~~~

Event loop dùng ít threads để phục vụ nhiều connections. Một `Thread.sleep(700)` bên trong reactive pipeline **được subscribe trên event-loop thread** có thể trì hoãn cả những requests khác. **Trả về `Mono` không tự làm callable trở thành non-blocking.**

### 3.3. Bảng định vị tài nguyên

| Tài nguyên | Vai trò | Khi quá tải |
| --- | --- | --- |
| Tomcat request worker | Chạy xử lý Servlet request | Busy≈max, request đến sau chờ |
| Java monitor/lock | Đồng bộ truy cập shared state | Threads `BLOCKED` hoặc lock wait |
| Hikari JDBC connection | Lease kết nối DB | Pending acquire tăng, timeout lấy connection |
| Reactor Netty event loop | I/O và reactive callbacks | Blocking code kéo chậm nhiều channels |
| Reactor Netty HTTP client pool | Lease kết nối outbound | Pending connections tăng |
| Remote dependency | Thực thi nghiệp vụ ngoài service | Outbound latency/error tăng |
| CPU/GC | Compute và memory management | Hot stacks, throttling, pauses |
| Proxy/client | Route, connection và deadline | 502/503/504 hoặc client timeout dù app còn chạy |

## 4. Quy trình điều tra 5 phút đầu tiên

**Bước 1 — ghi nhận triệu chứng:** route nào, từ lúc nào, tỷ lệ requests bị ảnh hưởng, p50/p95/p99, status 4xx/5xx, timeout text, RPS, concurrency, deploy gần nhất, một pod hay toàn cluster.

**Bước 2 — tìm boundary đầu tiên có độ trễ:** request đã tới ingress chưa, đến server chưa, controller bắt đầu chưa, outbound dependency nào đang chờ? So sánh timestamps/correlation IDs.

**Bước 3 — bảo toàn evidence:** metrics snapshot theo pod, ít nhất hai hoặc ba thread dumps khi vẫn lỗi, JFR nếu được phép, traces, Hikari gauges, CPU/GC và logs có timestamp.

**Bước 4 — xếp giả thuyết:** inbound worker queue, internal lock/CPU/GC, JDBC pool, outbound HTTP client pool, remote dependency hoặc event loop.

**Bước 5 — giảm tác động:** timeout/retry budget, rollback, giảm concurrency, isolate slow dependency, scale đúng tầng, traffic shedding. Đừng gây thêm tải production chỉ để chứng minh giả thuyết.

**Bước 6 — xác minh:** thực hiện lại workload có mức tải tương đương trên lab/staging hoặc sau mitigation có kiểm soát, đo tail latency/errors/saturation trước và sau.

### 4.1. Tìm timeline thay vì chỉ một status code

~~~text
12:00:00.000  client gửi GET /orders/123
12:00:00.010  ingress nhận
12:00:00.015  backend request START
12:00:00.025  chuẩn bị lấy Hikari connection
12:00:02.025  Hikari acquire timeout
12:00:02.030  backend trả 503 có chủ đích
~~~

Khác với:

~~~text
12:00:00.000  client gửi GET /orders/123
12:00:00.010  ingress nhận
12:00:05.010  ingress trả 504 vì upstream deadline
12:00:06.000  backend mới log START (đã xếp hàng quá lâu)
12:00:06.100  backend hoàn tất, không còn client chờ
~~~

Đây là **timeline minh họa**, không phải một trace thật. Trường hợp thứ hai cho thấy **proxy timeout trước khi controller xử lý**. Chỉ tăng SQL query timeout ở backend không giải quyết được.

### 4.2. Một request có nhiều thời hạn

- **Caller deadline:** trình duyệt, mobile app, gateway, gRPC caller.
- **Proxy upstream timeout:** gateway/ingress chờ upstream.
- **TCP connect timeout:** client chờ kết nối tới remote host.
- **HTTP read/response timeout:** client đợi bytes/response từ remote.
- **Connection pool acquire timeout:** client chờ lease pool hoặc Hikari connection.
- **DB query/lock timeout:** DB/JDBC query hoặc lock waits.
- **MVC async request timeout:** thời gian xử lý request đã chuyển sang Servlet async.
- **Reactive total deadline:** `Mono.timeout`/application-specific timeout trên Publisher.

Chúng **không đồng nhất** và không tự kế thừa nhau. Phải xác định exception/log phát sinh ở đâu và thứ tự deadline nào ngắn hơn.

## 5. Metrics nên thu thập trong Spring Boot 3.3

Với `spring-boot-starter-actuator`, Spring Boot 3.3 dùng Micrometer/Observation. Các meters sau thường hữu ích, với điều kiện component tương ứng được khởi tạo và instrument:

| Meter | Dấu hiệu |
| --- | --- |
| `http.server.requests` | Count/latency HTTP requests đã được quan sát, phân theo uri/status/method |
| `http.client.requests` | Client-side latency khi dùng injected Boot-configured `RestClient.Builder`/`WebClient.Builder` |
| `tomcat.threads.busy` | Số Servlet request worker đang bận |
| `tomcat.threads.current` | Số Tomcat threads hiện có |
| `jvm.threads.live` | Tổng Java threads còn sống, không riêng worker |
| `jvm.gc.pause` | GC pause events |
| `process.cpu.usage` | CPU process, cần so CPU quota/cgroup |
| `jdbc.connections.active` | DataSource connections đang lease |
| `jdbc.connections.max` | Maximum DB pool connections |
| `hikaricp.connections.active` | Hikari leased connections |
| `hikaricp.connections.pending` | Số threads đang chờ connection Hikari |
| `hikaricp.connections.timeout` | Hikari timeout counter theo instrumentation |
| `reactor.netty.connection.provider.active.connections` | Client HTTP pool active connections khi metrics bật |
| `reactor.netty.connection.provider.pending.connections` | HTTP client pending acquire queue khi metrics bật |

**Không thấy meter ≠ giá trị bằng 0.** Ví dụ Tomcat metrics của Boot 3.3 yêu cầu:

~~~properties
server.tomcat.mbeanregistry.enabled=true
~~~

Nếu chưa bật MBean Registry, Boot **không tự đăng ký** các Tomcat meters. Reactor Netty client connection provider cũng cần bật metrics (thường `ConnectionProvider.builder(...).metrics(true)`) và có traffic thật mới mong thấy gauges. Không nhầm Reactor Netty **client pool** với inbound event-loop threads.

### 5.1. Bật Actuator cho lab, không công khai production

~~~properties
management.endpoints.web.exposure.include=health,metrics
server.tomcat.mbeanregistry.enabled=true
~~~

Ví dụ query local:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.pending
~~~

`/actuator/metrics` là một **diagnostic endpoint**, cần expose tường minh và được bảo vệ bằng auth/network policy. Không expose `threaddump`, `heapdump`, `env`, `configprops` hay metrics chi tiết tùy tiện trên Internet.

**Chú ý lấy mẫu:** khi tất cả Tomcat workers bị giữ, chính request tới `/actuator/metrics` cũng có thể bị xếp hàng và phản hồi muộn. Production cần metrics scraper/agent và thu thập lịch sử theo thời gian thay vì chỉ chạy `curl` sau sự cố.

### 5.2. Timer của request treo có thể chưa hiển thị đầy đủ

Micrometer `http.server.requests` là timer dựa trên observation lifecycle; sample của **một request chưa kết thúc** có thể chưa được ghi vào count/total duration của request hoàn tất. Vì vậy:

- p95 từ completed requests có thể chưa bao gồm những requests vẫn đang treo.
- Một request “rất dài” vẫn đang chạy có thể không xuất hiện trong current histogram cho tới lúc hoàn tất.
- Cần thêm **active requests/in-flight gauges hoặc long-task observations nếu được instrument**, thread dumps, queue depth và proxy timeouts.
- Khi instrument custom timers, phân biệt ongoing tasks với completed measurements.

**Không kết luận “`http.server.requests` p95 ổn nên không có request treo”.**

### 5.3. Route-level và tag cardinality

Các tags thường gồm method, outcome, status, uri template. Nên đo `/orders/{id}` thay vì raw `/orders/12345` theo mỗi customer — raw IDs tạo high-cardinality metrics và có thể lộ thông tin cá nhân. Tracing có thể dùng sampling/correlation ID nhưng không log tokens, authorization headers hoặc raw request bodies nhạy cảm.

## 6. Thread dump: bằng chứng khi worker bị giữ hoặc deadlock

### 6.1. Lấy JVM PID và vài snapshots

Trên JDK 17, đúng host/container namespace và đủ quyền:

~~~bash
jcmd -l
jcmd <PID> Thread.print -l > thread-1.txt
sleep 2
jcmd <PID> Thread.print -l > thread-2.txt
sleep 2
jcmd <PID> Thread.print -l > thread-3.txt
~~~

`<PID>` là placeholder cần thay bằng process ID thực. `jcmd` thường yêu cầu user/group tương thích với JVM đích; container/namespace có thể làm `jcmd -l` không thấy process ngoài namespace.

**Lấy nhiều snapshots** vì một stack ở `SocketInputStream.read` trong 20 ms có thể bình thường, còn cùng stack giữ nguyên nhiều giây với các requests đồng thời thì đáng điều tra. Không có lý do để chụp 100 dumps mỗi giây trên production.

### 6.2. Dấu hiệu phổ biến

| Trạng thái/stack | Cách diễn giải đúng |
| --- | --- |
| `http-nio-8080-exec-*` + `Thread.sleep` | Servlet worker đang bị giữ, thường ít dùng CPU |
| `HikariPool.getConnection` / `ConcurrentBag.borrow` | Request đang chờ JDBC pool; kiểm tra pending/acquire time |
| `SocketInputStream.read`, JDK HTTP client read | Chờ network/remote; kiểm tra outbound timeout và dependency |
| `java.lang.Object.wait` hoặc `LockSupport.park` | Chờ điều kiện/lock/pool; cần xem context/owner |
| Java state `BLOCKED` tại synchronized monitor | Chờ vào monitor, tìm thread đang sở hữu |
| `reactor-http-nio-*` + `Thread.sleep`/blocking JDBC | Có nguy cơ blocking event loop |
| GC/JVM threads hoạt động bất thường | Cần GC logs/JFR, không kết luận từ một tên thread |
| `RUNNABLE` | Có thể đang chạy CPU hoặc native I/O; cần CPU profile |

**Deadlock** là chu trình chờ khiến các threads không thể tiến. **Thread starvation** là không đủ workers vì nhiều requests đang giữ/chờ. **Lock contention** là nhiều threads chờ lock nhưng owner vẫn có thể hoàn tất; không mặc định là deadlock.

### 6.3. Ví dụ stack minh họa

~~~text
"http-nio-8080-exec-2" TIMED_WAITING
  at java.lang.Thread.sleep
  at com.example.mvc.DiagController.worker(...)

"http-nio-8080-exec-3" WAITING
  at ... HikariPool.getConnection(...)
  at com.example.mvc.DiagController.pool(...)

"reactor-http-nio-2" TIMED_WAITING
  at java.lang.Thread.sleep
  at com.example.reactive.LoopController.bad(...)
~~~

Stack là ví dụ **rút gọn**; thread names, Java line numbers và native frames thay đổi theo môi trường.

## 7. JFR, CPU/GC và blocking diagnostics

### 7.1. Java Flight Recorder (JFR)

Với JDK 17:

~~~bash
jcmd <PID> JFR.start name=incident settings=profile duration=30s filename=incident.jfr
~~~

Mở `incident.jfr` bằng Java Mission Control (JMC) hoặc công cụ JFR phù hợp. Tìm:

- CPU hotspots / repeated stack samples.
- Monitor/lock contention và thread parking.
- Socket read/write events, file I/O.
- GC pause/allocation spikes.
- Tương quan thời gian spikes với HTTP p99/errors.

Lưu ý JFR/profile có overhead nhất định, có thể chứa class names, file paths và metadata nhạy cảm; đặt giới hạn lưu trữ, quyền truy cập và retention. Không bật `settings=profile` vô thời hạn nếu chưa có policy.

### 7.2. CPU usage thấp nhưng p99 cao

Đây là tín hiệu điều tra **waiting**, không phải “JVM không có vấn đề”. Kiểm tra:

- Tomcat busy gần max.
- Hikari pending hoặc HTTP client pool pending.
- Thread dumps có remote socket waits/locks/sleep.
- Downstream p95, DB slow queries và lock waits.
- Container CPU throttling (process CPU metric không đủ để phát hiện quota/cgroup mọi trường hợp).

### 7.3. CPU cao và throughput không tăng

Có thể là CPU-bound business code, serialization, regex, encryption, GC thrashing hoặc quá nhiều context switches. Dùng JFR/CPU sampling để xác định hot path. Tăng Tomcat threads hoặc event-loop count không giải quyết CPU-bound algorithm và có thể tăng context switching.

### 7.4. BlockHound chỉ là công cụ phụ

BlockHound có thể giúp phát hiện một số blocking methods trên Reactor non-blocking threads trong tests/dev, nhưng có yêu cầu tương thích JDK/instrumentation và không quan sát được mọi blocking. Không coi “BlockHound chưa cảnh báo” là bằng chứng không có blocking; kết hợp profiling, thread dumps, code review và comparison load tests.

## 8. Lab A — Spring MVC: tái hiện worker exhaustion, Hikari starvation, lock waits và downstream

Dự án **Java 17, Spring Boot 3.3.5, Maven** với embedded Tomcat chạy cổng `8080`. Cố ý hạn chế Tomcat workers và Hikari pool để dễ tái hiện. Để tránh nguy cơ ảnh hưởng hệ thống khác, lab bind `127.0.0.1`; không dùng endpoints sleep/lock này trong production.

### 8.1. Cấu trúc thư mục

~~~text
mvc-incident-lab/
├── pom.xml
├── downstream/
│   └── RemoteStub.java
├── tools/
│   └── load.py
└── src/main/
    ├── java/com/example/mvc/
    │   ├── MvcIncidentApplication.java
    │   └── DiagController.java
    └── resources/
        └── application.properties
~~~

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
    <artifactId>mvc-incident-lab</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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

`starter-web` sử dụng Servlet MVC/Tomcat trong lab. `starter-jdbc` mang HikariCP pool, H2 database chỉ phục vụ thí nghiệm lấy/giữ connection. `starter-actuator` giúp quan sát metrics.

### 8.3. application.properties

~~~properties
server.address=127.0.0.1
server.port=8080

# Cố ý giới hạn rất nhỏ: chỉ để mô phỏng.
server.tomcat.threads.max=6
server.tomcat.mbeanregistry.enabled=true

spring.datasource.url=jdbc:h2:mem:incident;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=2
spring.datasource.hikari.minimum-idle=2
spring.datasource.hikari.connection-timeout=800

app.remote.base-url=http://127.0.0.1:8091

management.endpoints.web.exposure.include=health,metrics
management.endpoint.health.show-details=never
~~~

**Đọc config đúng:** Hikari `connection-timeout=800` là thời gian chờ **lấy DB connection** (milliseconds), không phải query timeout hay JDBC socket timeout. `server.tomcat.threads.max=6` giới hạn request workers, không phải đặt timeout 6 giây. `server.tomcat.mbeanregistry.enabled=true` cần cho Tomcat meters ở Boot 3.3.

### 8.4. Main class

**`src/main/java/com/example/mvc/MvcIncidentApplication.java`:**

~~~java
package com.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcIncidentApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcIncidentApplication.class, args);
    }
}
~~~

### 8.5. Controller có bốn nguyên nhân

**`src/main/java/com/example/mvc/DiagController.java`:**

~~~java
package com.example.mvc;

import java.sql.Connection;
import java.sql.SQLException;
import java.time.Duration;
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@RestController
@RequestMapping("/api")
public class DiagController {

    private final DataSource dataSource;
    private final RestClient remote;
    private final Object oneSharedLock = new Object();

    public DiagController(
            DataSource dataSource,
            RestClient.Builder builder,
            @Value("${app.remote.base-url}") String baseUrl) {
        this.dataSource = dataSource;

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofMillis(500));
        factory.setReadTimeout(Duration.ofMillis(1200));
        this.remote = builder.baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }

    @GetMapping("/fast")
    public String fast() {
        return "fast-ok";
    }

    @GetMapping("/worker")
    public ResponseEntity<String> worker(
            @RequestParam(defaultValue = "1500") int ms) {
        if (ms < 0 || ms > 3000) {
            return ResponseEntity.badRequest().body("bad ms");
        }
        try {
            Thread.sleep(ms); // CỐ TÌNH giữ Servlet worker.
            return ResponseEntity.ok("worker:" + ms);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("interrupted");
        }
    }

    @GetMapping("/pool")
    public ResponseEntity<String> pool(
            @RequestParam(defaultValue = "1500") int ms) {
        if (ms < 0 || ms > 3000) {
            return ResponseEntity.badRequest().body("bad ms");
        }
        try (Connection c = dataSource.getConnection()) {
            // Giữ một Hikari lease trong lúc chờ: ANTI-PATTERN.
            Thread.sleep(ms);
            return ResponseEntity.ok("pool:" + ms);
        } catch (SQLException ex) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("db connection unavailable");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("interrupted");
        }
    }

    @GetMapping("/lock")
    public ResponseEntity<String> lock(
            @RequestParam(defaultValue = "1500") int ms) {
        if (ms < 0 || ms > 3000) {
            return ResponseEntity.badRequest().body("bad ms");
        }
        synchronized (oneSharedLock) {
            try {
                Thread.sleep(ms); // CỐ TÌNH chiếm Java monitor.
                return ResponseEntity.ok("lock:" + ms);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return ResponseEntity.status(
                        HttpStatus.SERVICE_UNAVAILABLE).body("interrupted");
            }
        }
    }

    @GetMapping("/remote/{kind}")
    public ResponseEntity<String> remote(
            @PathVariable String kind) {
        if (!("fast".equals(kind) ||
                "slow".equals(kind) ||
                "hang".equals(kind))) {
            return ResponseEntity.badRequest().body("bad kind");
        }
        try {
            String body = remote.get()
                    .uri("/remote/{kind}", kind)
                    .retrieve()
                    .body(String.class);
            return ResponseEntity.ok(body == null ? "" : body);
        } catch (RestClientException ex) {
            // Demo: network/read/remote errors được map thành 503.
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("remote unavailable");
        }
    }
}
~~~

**Chú ý tính diễn giải:**

- `/fast` không sleep, không JDBC, không remote; dùng làm **đối chứng**.
- `/worker` giữ Tomcat worker trong `TIMED_WAITING`, CPU có thể thấp.
- `/pool` vừa giữ Tomcat worker vừa giữ Hikari JDBC connection. Nếu active=2 và các requests khác pending, Hikari có thể timeout sau 800ms; code lab chọn HTTP **503** nhưng Hikari **không tự động áp HTTP status**.
- `/lock` dùng một Java monitor shared giữa requests. Các threads còn lại có thể ở `BLOCKED` chờ vào monitor; đó là contention, **không nhất thiết deadlock**.
- `/remote` dùng `RestClient.Builder` do Boot inject, nhờ đó client observations có thể có `http.client.requests`. `SimpleClientHttpRequestFactory` đặt connect/read timeout, nhưng bản thân factory này **không phải một outbound HTTP connection pool có pending gauges**.
- Không có dependency downstream hay `RestClient` trong `/fast`; nếu /fast cũng chậm khi chạy load /worker, xem resource dùng chung Tomcat workers.
- Không trả raw stack trace, hostnames/internal exception details ra response trong lab. Production phải log correlation IDs/error class có kiểm soát.

## 9. Stub downstream độc lập bằng JDK 17

Để tạo một remote dependency rõ ràng mà không cần thêm Maven project, dùng HTTP server có sẵn trong JDK.

**`downstream/RemoteStub.java`:**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;

public class RemoteStub {

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 8091), 0);
        server.createContext("/remote/", RemoteStub::handle);
        server.setExecutor(Executors.newFixedThreadPool(8));
        server.start();
        System.out.println("RemoteStub started at 127.0.0.1:8091");
    }

    private static void handle(HttpExchange exchange)
            throws IOException {
        String path = exchange.getRequestURI().getPath();
        String kind = path.substring("/remote/".length());

        long millis;
        switch (kind) {
            case "fast" -> millis = 0L;
            case "slow" -> millis = 900L;
            case "hang" -> millis = 3000L;
            default -> {
                exchange.sendResponseHeaders(404, -1);
                exchange.close();
                return;
            }
        }

        try {
            Thread.sleep(millis); // Giả lập dependency latency.
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }

        byte[] bytes = ("remote:" + kind)
                .getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(200, bytes.length);

        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }
}
~~~

Compile và chạy trong terminal A (từ thư mục root project):

~~~bash
cd downstream
javac --add-modules jdk.httpserver RemoteStub.java
java --add-modules jdk.httpserver RemoteStub
~~~

Chạy Spring Boot ở terminal B:

~~~bash
cd mvc-incident-lab
mvn spring-boot:run
~~~

Lưu ý: lệnh `cd mvc-incident-lab` ở trên giả định terminal B bắt đầu tại **thư mục cha chứa project**; nếu terminal đã ở root project, chỉ chạy `mvn spring-boot:run`.

Ở terminal C:

~~~bash
curl -i http://127.0.0.1:8080/api/fast
curl -i "http://127.0.0.1:8080/api/worker?ms=1500"
curl -i "http://127.0.0.1:8080/api/pool?ms=1500"
curl -i "http://127.0.0.1:8080/api/lock?ms=1500"
curl -i http://127.0.0.1:8080/api/remote/fast
curl -i http://127.0.0.1:8080/api/remote/slow
curl -i http://127.0.0.1:8080/api/remote/hang
~~~

Kết quả với **một request**, remote stub hoạt động:

| Endpoint | Kỳ vọng thông thường |
| --- | --- |
| `/api/fast` | HTTP 200, body `fast-ok` |
| `/api/worker?ms=1500` | HTTP 200, body `worker:1500` sau ~1.5s |
| `/api/pool?ms=1500` | HTTP 200 nếu lấy connection kịp |
| `/api/lock?ms=1500` | HTTP 200 nếu không bị ngắt |
| `/api/remote/fast` | HTTP 200, body `remote:fast` |
| `/api/remote/slow` | HTTP 200 sau ~0.9s, nếu client không timeout |
| `/api/remote/hang` | Thường **HTTP 503** do client read timeout 1.2s |

Đây là kỳ vọng theo code/timeout trong lab, không phải cam kết thời gian cố định trên mọi máy. Nếu remote stub không chạy, `/remote/fast` cũng trả 503 vì connection refused/timeout. Đừng gọi `/remote/hang` “controller bị deadlock”: root là remote cố tình sleep quá client deadline.

## 10. Script tạo concurrent load và thu latency/status

**`tools/load.py`**, dùng Python 3 standard library, không cần pip:

~~~python
import concurrent.futures
import math
import sys
import time
import urllib.error
import urllib.request

if len(sys.argv) != 4:
    raise SystemExit("Usage: python3 tools/load.py URL COUNT CONCURRENCY")

url = sys.argv[1]
count = int(sys.argv[2])
concurrency = int(sys.argv[3])

if count < 1 or concurrency < 1 or concurrency > 40:
    raise ValueError("count >= 1 and 1 <= concurrency <= 40")

def one(_):
    begin = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            resp.read()
            status = str(resp.status)
    except urllib.error.HTTPError as ex:
        ex.read()
        status = str(ex.code)
    except Exception:
        status = "ERR"
    ms = (time.perf_counter() - begin) * 1000
    return ms, status

begin = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(
        max_workers=concurrency) as executor:
    results = list(executor.map(one, range(count)))
elapsed = time.perf_counter() - begin

latencies = sorted(ms for ms, _ in results)

def percentile(p):
    idx = max(0, math.ceil(len(latencies) * p) - 1)
    return round(latencies[idx], 1)

statuses = {}
for _, status in results:
    statuses[status] = statuses.get(status, 0) + 1

print("count=", count, "concurrency=", concurrency)
print("elapsed_s=", round(elapsed, 3))
print("throughput_rps=", round(count / elapsed, 2))
print("p50_ms=", percentile(0.50))
print("p95_ms=", percentile(0.95))
print("p99_ms=", percentile(0.99))
print("status_counts=", statuses)
~~~

Đây là **closed-loop load script**: mỗi worker gửi request tiếp theo khi request trước hoàn tất. Nó hữu ích để nhìn xu hướng nhưng **không thay** bài capacity test chuyên nghiệp với arrival rate, warm-up, rate limiting, timeout distribution và nhiều clients. Kết quả p99 từ vài chục samples không ổn định; không dùng một lần chạy làm SLO chính thức. Chỉ chạy trên app local/staging do bạn sở hữu.

## 11. Thí nghiệm A1: giữ Tomcat workers, CPU vẫn thấp

Ở root MVC project:

~~~bash
python3 tools/load.py \
  "http://127.0.0.1:8080/api/worker?ms=1500" 24 12
~~~

Tomcat chỉ có tối đa **6 workers**. Khi 12 concurrent calls đến, khoảng sáu workers có thể bị giữ 1.5 giây, requests còn lại chờ ở connector/queue. Vì các threads đang `Thread.sleep`, process CPU usage có thể thấp, nhưng p95/p99 tăng do thời gian chờ worker.

Trong khi batch chạy, thử `/api/fast` ở terminal khác:

~~~bash
curl -w "\nTOTAL=%{time_total}s CODE=%{http_code}\n" \
  -o /dev/null \
  http://127.0.0.1:8080/api/fast
~~~

`/api/fast` bình thường rất nhanh nhưng có thể chậm khi tất cả workers đang bị giữ. Đây là bằng chứng **resource dùng chung**; không phải code /fast tự nhiên chậm.

Đo metrics trong khi batch:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.current
curl -s http://127.0.0.1:8080/actuator/metrics/process.cpu.usage
~~~

Khi busy=max, chính Actuator HTTP call có thể bị queue. Nên thu bằng time-series scraper và so nhiều snapshots. Thread dump thường cho thấy các `http-nio-8080-exec-*` ở `Thread.sleep`.

### 11.1. “Tăng Tomcat max=500” có giải quyết không?

Có thể giảm queue nếu nguyên nhân thật sự chỉ là worker availability **và** downstream/CPU/heap còn headroom. Nhưng nếu workers bị giữ vì remote API 10s, tăng worker max có thể dồn nhiều hơn xuống remote, làm HTTP client/DB pool cạn, tăng memory và khiến hệ thống sụp nặng hơn.

Biện pháp đúng bắt đầu từ nguyên nhân giữ worker: đặt client timeout và concurrency budget, giảm slow calls, cache hợp lệ, bulkhead, async nếu phù hợp, scale đúng tầng. Tăng max threads **chỉ sau benchmark**.

## 12. Thí nghiệm A2: Hikari pool acquisition timeout

Chạy:

~~~bash
python3 tools/load.py \
  "http://127.0.0.1:8080/api/pool?ms=1500" 24 12
~~~

Lab Hikari có **maximum-pool-size=2**, `connection-timeout=800ms`, trong khi request giữ connection 1500ms. Thông thường:

1. Hai requests lấy hai DB connections và giữ.
2. Các requests khác chờ ở `dataSource.getConnection()`.
3. Một số chờ hơn 800ms và nhận `SQLException`, controller trả **503**.
4. CPU có thể thấp, Tomcat workers vẫn bị chiếm trong lúc chờ.
5. Khi giữ xong, `try-with-resources` trả connection về Hikari pool.

Đo:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.active
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.pending
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.timeout
~~~

**Pending là gauge tức thời.** Nếu đọc sau khi load dừng, pending có thể về 0 dù trước đó đã có 10 threads chờ. Cần scrape trong peak hoặc xem timeout counter/log timestamps.

### 12.1. Tại sao đây không phải “DB query chậm” thật?

Lab cố tình giữ JDBC connection rồi sleep; H2 không có query chậm. Trong hệ thống thật, pool exhaustion có thể do:

- SQL query/lock quá lâu.
- Transaction giữ connection trong lúc gọi HTTP remote.
- Connection leak (không close).
- Pool quá nhỏ so với concurrency và capacity DB.
- DB max connections/CPU/IO không chịu tải.
- Rất nhiều replicas mỗi cái có pool riêng.

Do đó cần đo **acquire wait**, **connection usage duration**, **SQL duration** và **DB locks**. `active=max` mà pending=0/acquire nhanh **chưa đủ** chứng minh pool starvation.

### 12.2. Hikari timeout không phải SQL timeout

`spring.datasource.hikari.connection-timeout` giới hạn **chờ lấy lease**. Nó không hủy SQL đang chạy sau khi có connection. Query timeouts có thể cấu hình ở driver/JDBC `Statement.setQueryTimeout`, transaction timeout, database server timeout hoặc framework access layer; semantics phụ thuộc driver/DB. Đừng chữa SQL lock waits bằng cách nâng acquisition timeout vô hạn.

## 13. Thí nghiệm A3: lock contention và deadlock khác nhau

Chạy:

~~~bash
python3 tools/load.py \
  "http://127.0.0.1:8080/api/lock?ms=1500" 24 12
~~~

Chỉ một thread vào `synchronized (oneSharedLock)` tại một thời điểm. Các requests khác chờ monitor; thread dump có thể cho thấy `BLOCKED` tại `DiagController.lock(...)`, trong khi thread sở hữu lock đang sleep.

Đây là **lock contention**, không phải **deadlock**: owner cuối cùng thoát synchronized và giải phóng lock. Deadlock thực sự yêu cầu vòng chờ (ví dụ thread 1 giữ lock A chờ B, thread 2 giữ B chờ A). Dùng nhiều thread dumps/JFR MonitorEnter và tìm lock owners/cycles để kết luận.

### 13.1. Dấu hiệu cần phân biệt

- **BLOCKED**: JVM thread chờ vào intrinsic monitor. Có thể bình thường khi contention ngắn.
- **WAITING/TIMED_WAITING**: `wait/park/sleep` hoặc pool wait; không đồng nghĩa deadlock.
- **Deadlock detection**: có thể nhận thông báo về Java-level deadlocks trong thread dump/tooling, nhưng cũng cần hiểu loại lock và môi trường.
- **Starvation**: một nhóm threads không được phục vụ vì pool/executor quá ít hoặc bị tasks khác chiếm; không yêu cầu vòng chờ.

**Khắc phục:** rút ngắn critical section, tránh giữ lock lúc I/O, giảm shared mutable state, dùng concurrency primitives phù hợp. Không dùng `synchronized` quanh remote HTTP hoặc SQL transaction dài.

## 14. Thí nghiệm A4: downstream chậm và caller timeout

Khởi chạy `RemoteStub` trước. So sánh:

~~~bash
python3 tools/load.py \
  http://127.0.0.1:8080/api/remote/fast 24 8

python3 tools/load.py \
  http://127.0.0.1:8080/api/remote/slow 24 8

python3 tools/load.py \
  http://127.0.0.1:8080/api/remote/hang 24 8
~~~

Stub xử lý `fast` ngay, `slow` ~900ms và `hang` ~3000ms. `RestClient` trong MVC có read timeout 1200ms, nên `hang` thường gây exception rồi controller map 503. **HTTP 503 ở đây là chính sách của lab**, không phải behavior tự động của mọi `RestClient`.

Lấy:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics/http.client.requests
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
~~~

Khi sử dụng injected `RestClient.Builder`, Spring Boot có thể instrument outbound HTTP với `http.client.requests`. Nếu ứng dụng tự tạo `RestClient.create()` và bỏ qua Boot observation customizers, client spans/meters có thể không có.

### 14.1. Trường hợp HTTP 504 tại gateway

Nếu NGINX/ingress chờ upstream 1 giây trong khi backend vẫn chạy 3 giây, gateway có thể trả **504 Gateway Timeout** cho client. Backend vẫn có thể log “completed” khi caller đã rời đi. **Không suy ra chính controller Spring Boot đã phát 504** chỉ từ HTTP status phía ngoài.

Ngược lại, HTTP 503 do lab controller chủ động trả sau read timeout là **một response từ backend**, không phải proxy 504. Đối chiếu headers, proxy access/error logs và trace ID để xác định nguồn status.

### 14.2. Request đã bị hủy nhưng server vẫn ghi DB?

Có thể. Trong MVC sync, việc client ngắt kết nối **không mặc định rollback mọi transaction hoặc interrupt ngay thread đang làm việc**. Nếu business side effect đã commit và client retry POST không có idempotency key, có nguy cơ duplicate transaction. Cần xử lý timeout/deadline/idempotency ở business contract.

## 15. Lab B — Spring WebFlux: event loop bị chặn hay reactive non-blocking?

Tạo **project Maven riêng**, không thêm `spring-boot-starter-web` vào dự án WebFlux. Cùng một API chờ 700ms có thể tiêu thụ tài nguyên khác nhau tùy cách viết:

- `/loop/bad`: `Mono.fromCallable` chứa `Thread.sleep`, cố tình block khi subscribe trên event loop.
- `/loop/good`: `Mono.delay` non-blocking timer.
- `/loop/offload`: thực thi blocking callable trên `Schedulers.boundedElastic()`, để event loop không bị giữ.
- `/loop/ping`: endpoint control không chờ.

### 15.1. Cấu trúc

~~~text
webflux-incident-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/loop/
    │   ├── LoopApplication.java
    │   └── LoopController.java
    └── resources/
        └── application.properties
~~~

### 15.2. pom.xml

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
    <artifactId>webflux-incident-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### 15.3. application.properties

~~~properties
server.address=127.0.0.1
server.port=8082
management.endpoints.web.exposure.include=health,metrics
~~~

### 15.4. Main class

**`src/main/java/com/example/loop/LoopApplication.java`:**

~~~java
package com.example.loop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoopApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoopApplication.class, args);
    }
}
~~~

### 15.5. LoopController.java

~~~java
package com.example.loop;

import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/loop")
public class LoopController {

    @GetMapping("/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/bad")
    public Mono<String> bad(
            @RequestParam(defaultValue = "700") int ms) {
        if (ms < 0 || ms > 2000) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid ms"));
        }

        // Anti-pattern: blocking code chạy khi Publisher được subscribe.
        return Mono.fromCallable(() -> {
            Thread.sleep(ms);
            return "bad:" + Thread.currentThread().getName();
        });
    }

    @GetMapping("/good")
    public Mono<String> good(
            @RequestParam(defaultValue = "700") int ms) {
        if (ms < 0 || ms > 2000) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid ms"));
        }

        // Timer reactive: không giữ event-loop thread trong lúc chờ.
        return Mono.delay(Duration.ofMillis(ms))
                .map(tick -> "good:" + Thread.currentThread().getName());
    }

    @GetMapping("/offload")
    public Mono<String> offload(
            @RequestParam(defaultValue = "700") int ms) {
        if (ms < 0 || ms > 2000) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid ms"));
        }

        return Mono.fromCallable(() -> {
            Thread.sleep(ms);
            return "offload:" + Thread.currentThread().getName();
        }).subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

**Tính đúng đắn:**

1. `Mono.fromCallable` không tự chạy thread riêng. Khi được WebFlux subscribe trực tiếp trên event loop, blocking `Thread.sleep` có thể giữ `reactor-http-nio-*`.
2. `Mono.delay` dùng Reactor scheduler non-blocking, không tiêu thụ event-loop trong toàn bộ thời gian chờ. Thread name của `map` không phải API contract.
3. `boundedElastic` dùng bounded pool/queue để offload legacy blocking calls, **không phải unlimited threads**. Khi pool/queue saturated, nó cũng có thể bị delay hoặc reject.
4. Trên WebFlux, `Mono.block()` trên non-blocking event-loop có thể gây error hoặc blocking, tùy context; không dùng như phương pháp chuyển reactive thành synchronous trong controller.
5. Nếu bạn đưa `spring-boot-starter-web` vào cùng project, Boot thường ưu tiên MVC/Servlet khi có cả hai, làm test không còn đo Netty event loop như dự định.

### 15.6. Chạy WebFlux test

Từ thư mục `webflux-incident-lab`:

~~~bash
mvn clean package
java -jar target/webflux-incident-lab-0.0.1-SNAPSHOT.jar
~~~

Trong terminal khác:

~~~bash
curl -i http://127.0.0.1:8082/loop/ping
curl -i http://127.0.0.1:8082/loop/bad
curl -i http://127.0.0.1:8082/loop/good
curl -i http://127.0.0.1:8082/loop/offload
~~~

Cả ba endpoint có `ms=700` thường đáp ứng sau khoảng 700ms khi chỉ có một call, nhưng khác về nơi thực thi và khả năng phục vụ nhiều connections cùng lúc.

Dùng script load từ project MVC (điều chỉnh relative path nếu layout khác):

~~~bash
python3 ../mvc-incident-lab/tools/load.py \
  http://127.0.0.1:8082/loop/bad 40 20

python3 ../mvc-incident-lab/tools/load.py \
  http://127.0.0.1:8082/loop/good 40 20

python3 ../mvc-incident-lab/tools/load.py \
  http://127.0.0.1:8082/loop/offload 40 20
~~~

**Để giảm số event-loop threads cho lab có thể tái hiện rõ hơn**, dừng process và chạy một **process lab khác** bằng:

~~~bash
java -Dreactor.netty.ioWorkerCount=2 \
  -jar target/webflux-incident-lab-0.0.1-SNAPSHOT.jar
~~~

Property `reactor.netty.ioWorkerCount` là Reactor Netty system property; không đặt nó như một Spring Boot timeout. Không thay số event-loop workers của production tùy tiện. Khi chạy trên máy nhiều CPU, kết quả khác nếu worker count khác; kết luận phải dựa trên thread stacks, request latency và controls, không phải p95 một vòng chạy.

### 15.7. Quan sát /loop/ping khi /loop/bad đang chạy

Trong lúc đang tạo tải `/loop/bad`, thử:

~~~bash
curl -w "\nCODE=%{http_code} TOTAL=%{time_total}s\n" \
  -o /dev/null \
  http://127.0.0.1:8082/loop/ping
~~~

Nếu event loops bị các blocking call giữ, ngay cả `/loop/ping` cũng có thể chậm, dù bản thân ping không sleep. Với `/loop/good` và `/loop/offload`, event-loop có thể tiếp tục phục vụ sockets; nhưng tổng latency vẫn phụ thuộc boundedElastic capacity, CPU, network và scheduling.

Dùng thread dump trong lúc load để thấy `reactor-http-nio-*` ở `Thread.sleep` (bad case), còn offload thường chạy trên `boundedElastic-*`. **Tên thread chỉ là dấu hiệu**, cần stack/correlation/time-series để xác nhận.

## 16. Outbound HTTP connection pool cũng có thể “treo” WebClient

Khi WebFlux dùng WebClient/HTTP Reactor Netty, request có thể chờ **lease một connection từ ConnectionProvider** trước khi remote HTTP call thực sự bắt đầu. Trường hợp này khác **inbound event loop blocking**.

### 16.1. Metrics conditional

Các gauges/timers React Netty ConnectionProvider thường có:

~~~text
reactor.netty.connection.provider.active.connections
reactor.netty.connection.provider.idle.connections
reactor.netty.connection.provider.max.connections
reactor.netty.connection.provider.pending.connections
reactor.netty.connection.provider.pending.connections.time
~~~

Chúng chỉ xuất hiện khi **outbound pool được instrument** và có traffic. Không thấy pending meter không chứng minh không có chờ, và số connections không luôn bằng requests (đặc biệt khi HTTP/2 multiplexing).

### 16.2. Ví dụ cấu hình client pool riêng

Đây là class có thể thêm vào **project WebFlux lab**; để tạo traffic thực còn phải inject bean `backendClient` vào một controller/service gọi downstream:

~~~java
package com.example.loop;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
public class BackendHttpConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider backendProvider() {
        return ConnectionProvider.builder("backend")
                .maxConnections(2)
                .pendingAcquireMaxCount(4)
                .pendingAcquireTimeout(Duration.ofMillis(500))
                .metrics(true)
                .build();
    }

    @Bean
    WebClient backendClient(
            WebClient.Builder builder,
            ConnectionProvider backendProvider) {
        HttpClient client = HttpClient.create(backendProvider)
                .responseTimeout(Duration.ofSeconds(2));

        return builder
                .baseUrl("http://127.0.0.1:8091")
                .clientConnector(new ReactorClientHttpConnector(client))
                .build();
    }
}
~~~

**Những timeouts khác nhau:**

- `pendingAcquireTimeout(500ms)`: chờ lease từ pool tối đa theo policy.
- `responseTimeout(2s)`: thời hạn chờ response theo Reactor Netty semantics sau request/outbound exchange, không phải mọi phase tổng hợp.
- `maxConnections(2)`: giới hạn pool connections, **không** phải event-loop threads.
- `pendingAcquireMaxCount(4)`: giới hạn số acquisitions đợi để tránh hàng đợi vô tận.
- `metrics(true)`: bật pool meters khi Micrometer có mặt.
- `@Bean(destroyMethod="dispose")`: cho Spring đóng provider khi context shutdown.
- `WebClient.Builder` auto-configured giúp giữ observations của Boot.

Nếu remote chậm hoặc trả 429/503, tăng pool không nhất thiết giúp; nó có thể chỉ tăng concurrency dồn vào dependency đã quá tải. Kết hợp pending acquire, remote p95/errors và per-host budgets trước khi đổi `maxConnections`.

### 16.3. Client total deadline bằng Mono.timeout

Trong một **reactive service** có WebClient bean đã cấu hình:

~~~java
Mono<String> result = backendClient.get()
        .uri("/remote/slow")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(3));
~~~

Đây là **snippet trong scope có biến `backendClient`**, không phải class runnable độc lập. `Mono.timeout` giúp đặt deadline cho publisher chain, trong khi connect/response/pool timeouts vẫn cần cấu hình ở đúng tầng để tránh chờ vô hạn hoặc exceptions khó phân loại.

**`timeout` không nhất thiết ngắt được một JDBC blocking call đang chạy** trên thread khác; cancellation là cooperative tùy source/driver. Với write side effects, idempotency/transaction semantics vẫn là trách nhiệm ứng dụng.

## 17. Bảng timeout — cấu hình đúng tầng, đúng tác dụng

| Timeout / limit | Áp dụng cho | Không dùng để |
| --- | --- | --- |
| `server.tomcat.connection-timeout` | Thời gian Tomcat chờ request URI line sau khi accept connection | Giới hạn controller sync chạy 30s |
| `server.tomcat.keep-alive-timeout` | Chờ HTTP request mới trên keep-alive connection | Tổng thời gian xử lý business |
| `spring.mvc.async.request-timeout` | MVC Servlet **asynchronous request processing** | Tự ngắt một sync `@GetMapping` bị `Thread.sleep` |
| `spring.datasource.hikari.connection-timeout` | Chờ **lấy JDBC connection** từ Hikari | Giới hạn SQL query sau khi có connection |
| JDBC `Statement.setQueryTimeout` | JDBC statement execution (driver/DB semantics) | Kết nối TCP, Hikari acquire wait |
| `SimpleClientHttpRequestFactory#setConnectTimeout` | RestClient connect stage | Remote server xử lý xong toàn bộ |
| `SimpleClientHttpRequestFactory#setReadTimeout` | Chờ đọc dữ liệu HTTP từ remote | TCP connect/entire application deadline |
| Reactor Netty `CONNECT_TIMEOUT_MILLIS` | TCP connect | HTTP response/body time |
| Reactor Netty `responseTimeout(Duration)` | HTTP response wait theo client implementation | Pool acquire và overall user deadline |
| Reactor Netty `pendingAcquireTimeout` | Chờ lấy outbound client connection | Remote server compute time |
| Reactor `Mono.timeout` | Deadline trên Publisher chain | Bảo đảm ngắt một blocking/native side effect |
| Proxy/gateway upstream timeout | Chờ backend trả response | Điều khiển Java handler/server thread |
| Client `curl --max-time` | Tổng thời gian curl request theo option | Thay đổi server policy |
| `spring.lifecycle.timeout-per-shutdown-phase` | Graceful lifecycle shutdown phase | Runtime HTTP request timeout khi app hoạt động |

### 17.1. Hai bẫy Spring Boot hay gặp

**Bẫy A:** đặt `server.tomcat.connection-timeout=10s` rồi nghĩ controller đang gọi DB 120 giây sẽ bị ngắt sau 10 giây. Sai: property này liên quan connector chờ request URI line, không phải execution deadline.

**Bẫy B:** đặt `spring.mvc.async.request-timeout=10s` nhưng controller trả String đồng bộ và gọi `Thread.sleep(120000)`. Timeout đó chủ yếu áp dụng **Servlet async requests** như `Callable`/`DeferredResult`; không tự biến sync handler thành async hoặc kill thread đang ngủ.

### 17.2. Server không tự trả HTTP 504 cho mọi timeout

Nếu client nhận 504, nhiều khả năng gateway/proxy trả vì upstream deadline. Application Spring Boot có thể tự map `TimeoutException` thành 504 qua `@ControllerAdvice` hoặc filter, nhưng đó là code/config cụ thể, **không phải kết quả mặc định chung của mọi timeout**.

### 17.3. Chọn deadline theo budget

Ví dụ giả định: user SLA 4 giây, gateway timeout 3.5s, backend gọi remote service.

~~~text
client total deadline          4.0s
proxy upstream deadline       3.5s
backend business deadline     3.0s
remote HTTP timeout           2.0s
pool acquire timeout          0.3s
retry/backoff within budget   bounded
~~~

Đây là **minh họa**, không phải cấu hình phổ quát. Remote connect/read/pool timeouts có thể cộng theo stages hoặc overlap; cần đảm bảo tổng critical-path latency và retries nằm dưới caller deadline. Đừng đặt mỗi dependency timeout bằng 30s nếu caller chỉ chờ 3s.

## 18. Correlation ID, structured logs và tracing

Trong một incident, điều khó nhất là nối các logs từ client, ingress, app, HTTP client và DB.

### 18.1. Ghi những gì?

- Timestamp UTC với độ chính xác đủ cho từng hop.
- Request ID/trace ID/span ID nếu có.
- HTTP method/URI **template**, status, duration.
- Pod/instance ID và app version.
- Downstream logical service name, outcome/timeout class.
- Hikari/client pool acquire/SQL/remote duration được instrument đúng.
- Start/finish/cancel markers cho work dài hoặc lifecycle async.

**Không log** raw Authorization headers, passwords, session cookies, user PII, entire body, access tokens. Tránh user-supplied URL path làm metric label high-cardinality.

### 18.2. Ví dụ correlation timeline

~~~text
trace=abc request_id=r-1 ingress_start=12:00:01.000
trace=abc request_id=r-1 mvc_start=12:00:01.020
trace=abc request_id=r-1 hikari_acquire_begin=12:00:01.040
trace=abc request_id=r-1 hikari_acquire_end=12:00:01.540
trace=abc request_id=r-1 db_query_end=12:00:01.600
trace=abc request_id=r-1 downstream_end=12:00:02.900
trace=abc request_id=r-1 mvc_finish=12:00:02.950
~~~

Các dòng là minh họa. Chú ý định nghĩa span/interval rõ ràng; đừng cộng durations của **nested** hoặc **parallel child spans** rồi tưởng bằng total latency. Dùng **critical path** cho fan-out.

### 18.3. Tracing không tự đầy đủ chỉ vì có Actuator

Spring Boot Actuator cung cấp observations/metrics, nhưng để có **distributed traces** cần dependencies/config Micrometer Tracing/OpenTelemetry bridge, exporter, context propagation và sampling. Outbound HTTP observations thường cần dùng injected `RestClient.Builder`/`WebClient.Builder` của Boot hoặc áp customizers phù hợp; tự tạo raw clients có thể mất instrumentation.

Đồng hồ giữa các machines có thể lệch; dùng tracing durations và NTP/clock sync khi so timestamps cross-host.

## 19. Quy trình chẩn đoán theo triệu chứng

### 19.1. “Đột nhiên toàn bộ APIs bị chậm”

1. Kiểm tra ingress status/response times và traffic spike.
2. Kiểm tra CPU quota/throttling, GC pause, heap memory.
3. MVC: Tomcat busy≈max? Worker thread stacks đang làm gì?
4. WebFlux: event-loop threads có blocking stack? `/ping` cũng chậm?
5. Kiểm tra shared resources: DB pool, HTTP client pool, log appender lock.
6. Kiểm tra rollout/version config và downstream health cùng thời gian.

Nếu chỉ một endpoint chậm mà /ping bình thường, nghi ngờ business route/downstream riêng. Nếu /ping cũng chậm, nghĩ tới shared worker/event loop/CPU/proxy trước.

### 19.2. “CPU 10%, 504 tăng”

Nghi ngờ waiting: Tomcat workers giữ socket reads, JDBC pool pending, downstream latency, proxy routing/caller deadline. Dùng thread dump + outbound spans + pool gauges, **không tăng CPU limits chỉ vì 504**.

### 19.3. “Hikari pending tăng, DB CPU thấp”

Có thể DB locks, long-lived transactions, connection leak hoặc application giữ connection lúc chờ remote. Kiểm tra actual SQL/query plans, connection hold times, tx boundaries và total replicas, không chỉ pool max.

### 19.4. “WebFlux p99 tăng sau khi tích hợp SDK blocking”

Kiểm tra stack traces của `reactor-http-nio-*`. Tìm `Thread.sleep`, JDBC, blocking HTTP client, `Future.get`, file I/O, `.block()`. Thay bằng async APIs hoặc bounded offload; đừng tăng event-loop count vô hạn.

### 19.5. “Actuator metrics endpoint cũng timeout”

Khi Tomcat workers cạn hoặc Reactor event loop bị chặn, endpoint Actuator **cùng server port** cũng có thể không phản hồi. Điều này không chứng minh Actuator hỏng. Dùng external scrape history, JFR, thread dumps, alternate management port/agent nếu architecture cho phép. Đặt management server port khác **không bảo đảm** toàn bộ process/heap/DB vẫn healthy; nó chỉ giúp phân tách một phần request path.

### 19.6. “Sau nâng cấp, lỗi mới xuất hiện”

Đối chiếu artifact/JDK/library versions, web stack thực tế, client connection pool defaults và HTTP timeouts, metrics names/observations, security filters, virtual-thread configuration và deployment topology. Chạy canary dưới cùng traffic mix, so p95/p99 và saturation trước/sau. Một lần đổi Boot BOM có thể thay Reactor Netty, Tomcat, Hikari và instrumentation versions; không mặc định giữ nguyên tuning đã dựa trên implementation cũ.

## 20. Nâng cấp Spring Boot mà không làm mất khả năng chẩn đoán

Bài dùng **Boot 3.3.5 + Java 17** để code có imports/config ổn định. Khi nâng cấp:

- **Boot 2.x → 3.x:** Servlet APIs chuyển từ `javax.servlet.*` sang `jakarta.servlet.*`; filters/interceptors/custom servlet code phải kiểm tra imports, versions. Bài lab sử dụng `javax.sql.DataSource` (Java SE), **không phải javax.servlet**, nên import đó vẫn đúng.
- **Boot 3.3 → 3.4+:** graceful shutdown default đổi từ `immediate` sang `graceful`; cần đánh giá rollout/termination budget, không liên quan trực tiếp request runtime timeout nhưng ảnh hưởng in-flight traffic khi deploy.
- **Reactor Netty upgrade:** connection provider defaults/metrics và event-loop behavior có thể đổi theo version/platform; không sao chép số max pending/connections từ docs “latest” vào Boot 3.3 nếu chưa đối chiếu.
- **Micrometer/Observation upgrade:** một số meters/tags có thể khác và cần bật instrumentation; đừng xem “metric biến mất” là utilization=0. Kiểm tra canonical meter names trong `/actuator/metrics` và backend naming normalization.
- **Java 21 virtual threads:** Boot có thể dùng virtual threads trong phù hợp Servlet/task execution khi config version hỗ trợ, nhưng **không tự biến JDBC/remote service thành non-blocking** hoặc bảo đảm WebFlux event loop khỏi blocking. Virtual threads có trade-offs về pinning/lock contention/memory.
- **Web stack:** có `starter-web` và `starter-webflux` cùng classpath, Boot thường chọn MVC; cần xác minh logs/web application type, không nhận diện runtime chỉ từ việc ứng dụng dùng WebClient outbound.
- **Timeout config:** đừng đổi một property dựa trên tên giống nhau; xem docs từng phiên bản và kiểm tra behavior bằng integration tests.

### 20.1. Regression test sau nâng cấp

| Trường hợp | Điều cần assert |
| --- | --- |
| 1 request nhanh | 200 và latency trong baseline |
| 20 requests chậm song song | Tail latency và busy workers dưới giới hạn |
| DB pool cạn giả lập | Request fail nhanh/expected status, không treo vô hạn |
| Remote timeout | Error mapping đúng, client không retry storm |
| WebFlux blocking guard | Không chạy known blocking library trên event loop |
| Graceful shutdown | In-flight behavior và deadline phù hợp release |
| Error/metrics/tracing | Request IDs, client/server meters và dashboards vẫn có |
| Pod scaling | Total DB connections và downstream rate không vượt budget |

**Không dùng lab stress endpoints trong production**: chúng là anti-pattern cố ý để nhận diện, không phải mẫu triển khai nghiệp vụ.

## 21. Sửa đúng nút thắt và tránh cascading failure

| Gốc được chứng minh | Hành động ưu tiên | Dữ liệu xác minh |
| --- | --- | --- |
| Tomcat worker bị giữ bởi downstream | HTTP client deadlines, bulkhead, giảm retries, async nếu phù hợp | Busy workers, p99, timeout/errors |
| Lock contention | Giảm critical section, tránh I/O dưới lock | Thread BLOCKED, lock wait time |
| Real Java deadlock | Sửa lock acquisition order, tránh cyclic locking | Thread dumps hết deadlock |
| Hikari acquire pending | Rút ngắn tx/SQL, giới hạn concurrency, sizing theo DB | Pending/acquire time/DB locks |
| WebFlux blocking event loop | Reactive I/O hoặc bounded offload | Event-loop responsiveness, JFR, p99 |
| Outbound client pool pending | Reuse WebClient/provider, fix remote, bound queue, adjust pool có đo | Pending time, remote errors |
| Downstream 429/5xx | Rate limit, circuit breaker, jitter retry budget, cache hợp lệ | Remote p95/429, drop/retry rate |
| Proxy timeout ngắn | Đồng bộ deadline budgets hoặc giảm backend critical path | Proxy 504 vs backend finish |
| CPU saturation | Tối ưu hot path, serialization, scale CPU đúng | CPU profiling, throughput, GC |
| GC pressure | Allocation/heap/GC investigation | JFR GC pause/heap metrics |

### 21.1. Bulkhead và backpressure

Nếu một remote service chậm và ứng dụng cho phép vô hạn requests xếp hàng, mỗi retry có thể đẩy thêm tải xuống nơi đang lỗi. Nên có:

- Giới hạn concurrency per dependency.
- Bounded queue/pending acquires; overload response rõ (429/503 tùy contract).
- Circuit breaker và request deadline.
- Retry chỉ cho transient errors, có exponential backoff + jitter + overall budget.
- Idempotency key cho non-idempotent writes.
- Cache/fallback chỉ nếu business chấp nhận dữ liệu stale hoặc partial.

Không đặt pool size bằng số request workers một cách máy móc: DB/server capacity và số replicas mới quyết định concurrency thực sự có ích.

### 21.2. Sau mitigation, đo lại

Không chỉ so average response time; cần đo p95/p99, error rate, request count, throughput, queue/pending, CPU/GC, memory, downstream concurrency và resource cost. Lưu cùng traffic mix/build/quota/window để có so sánh đáng tin.

## 22. Những bẫy chẩn đoán phổ biến

| Nhầm lẫn | Vì sao sai |
| --- | --- |
| CPU thấp là server khỏe | Threads có thể chờ pool/I/O/lock |
| `http.server.requests` p95 thấp là không có request treo | Timer của in-flight request có thể chưa hoàn tất |
| Tomcat `threads.busy=max` chắc chắn phải tăng max | Worker có thể đang chờ remote/DB |
| Hikari active=max nghĩa DB pool quá nhỏ | Cần pending, acquire/SQL duration và DB capacity |
| `server.tomcat.connection-timeout` là controller timeout | Nó chờ request URI line sau accept |
| `spring.mvc.async.request-timeout` tự cắt sync handler | Chỉ tác động async request processing |
| WebFlux Mono luôn non-blocking | Callable/JDBC/Thread.sleep vẫn block nếu chạy trên event loop |
| Tăng event-loop workers vô hạn sẽ chữa .block() | Không sửa blocking code và có thể tăng contention |
| `WAITING` trong thread dump nghĩa deadlock | Có thể đợi I/O/condition/connection bình thường |
| Status 504 chắc chắn do Spring controller | Có thể do proxy/gateway |
| Cứ tăng Hikari max là throughput tăng | DB có thể bị overwhelm và lock contention |
| Một timeout 30s áp dụng mọi layer | Mỗi timeout có phase/boundary riêng |
| Client đóng socket sẽ rollback mọi DB write | Side effect có thể đã commit |
| Actuator không phản hồi là nó bị lỗi | Có thể dùng chung worker/event-loop đang bão hòa |
| `@DirtiesContext`/restart là cách chữa hung request | Chỉ tạm xóa dấu vết; cần phân tích nguyên nhân |
| Một lần load test và p99 đã đủ chứng minh | Samples nhỏ, client/tool bias, warm-up và machine noise |
| Có WebClient nghĩa inbound server chạy WebFlux | MVC app vẫn có thể sử dụng WebClient |
| Virtual threads tự loại bỏ mọi loại blocking | DB/locks/downstream vẫn có capacity limits |
| Tăng retry khi remote chậm là tốt | Retry storm có thể làm outage nặng hơn |

## 23. Tình huống tự luận và câu hỏi tự kiểm tra

**Câu 1.** Backend Spring MVC nhận 100 RPS, p99 từ 200ms lên 8s, CPU chỉ 15%, Tomcat busy=max. Nêu ít nhất ba giả thuyết và metrics cần phân biệt.

**Câu 2.** Hikari max=2, active=2, pending=8, connection-timeout=800ms. Vì sao pool có thể timeout dù database CPU thấp?

**Câu 3.** Hàng chục threads ở `BLOCKED` chờ cùng một lock; có đủ bằng chứng khẳng định deadlock không?

**Câu 4.** Thread dump của `reactor-http-nio-2` có `Thread.sleep` trong một `Mono.fromCallable`. Vì sao request `/ping` khác có thể chậm?

**Câu 5.** `spring.mvc.async.request-timeout=3s` sẽ có hiệu lực thế nào nếu controller MVC là synchronous và gọi `Thread.sleep(10000)`?

**Câu 6.** `server.tomcat.connection-timeout=3s` có chấm dứt một slow SQL query đang chạy 20s không?

**Câu 7.** Vì sao client thấy HTTP 504 trong khi backend log FINISH thành công?

**Câu 8.** `RestClient` dùng Boot injected builder có lợi gì khi thu metrics?

**Câu 9.** `reactor.netty.connection.provider.pending.connections` đo inbound Netty event-loop threads hay outbound HTTP pool?

**Câu 10.** `Mono.timeout` có bảo đảm hủy một JDBC blocking statement đã gửi tới database không?

**Câu 11.** Nếu app có 8 replicas, mỗi replica Hikari max=20, tổng tối đa được cấp từ tất cả pools là bao nhiêu, và vì sao phải cân nhắc DB limit?

**Câu 12.** Tại sao một HTTP request chưa hoàn tất có thể chưa làm tăng sample count `http.server.requests`?

**Câu 13.** Các thread dumps nên chụp lúc nào và tại sao cần nhiều snapshots?

**Câu 14.** Với Boot 3.3, muốn thấy Tomcat metrics cần bật property nào?

**Câu 15.** Có thể dùng `spring.threads.virtual.enabled=true` trên Java 17 để sửa WebFlux event loop không?

**Câu 16.** Sau upgrade, nếu không còn metric `tomcat.threads.busy` thì phải kiểm tra gì?

**Câu 17.** Khi remote service đang 429, tăng HTTP client connection pool từ 20 lên 200 có thể gây điều gì?

**Câu 18.** Nêu bốn loại deadline khác nhau trên một request MVC gọi DB và remote HTTP service.

**Đáp án định hướng:**

1. Worker chờ downstream/DB, Hikari pool pending, lock contention hoặc GC; lấy thread dumps, outbound spans, Hikari/Tomcat metrics.
2. Connections đang bị lease lâu, requests khác chờ; DB CPU thấp không nói connection usage duration.
3. Không; monitor contention có thể hoàn tất. Cần lock owners/cycle và nhiều snapshots.
4. Event-loop ít threads phục vụ nhiều sockets; blocking chiếm event loop được dùng chung.
5. Không tự ngắt sync handler; property áp dụng Servlet asynchronous request processing.
6. Không; connection-timeout của Tomcat chỉ chờ request line sau khi accept.
7. Proxy/caller deadline hết sớm hơn backend response; backend tiếp tục xử lý sau disconnect.
8. Boot observation auto-config/instrumentation cho `http.client.requests`/tracing.
9. Outbound HTTP ConnectionProvider pool khi metrics bật; không phải inbound event-loop count.
10. Không; cancellation của blocking/native call không luôn dừng work ở external service.
11. Tối đa khoảng 160 connections nếu mọi replicas đạt max; còn tổng DB connections từ clients khác, jobs, admin.
12. Timer ghi nhận completed observation; in-flight requests cần gauges/tracing/dumps riêng.
13. Lúc đang bị chậm, vài snapshots cách nhau giây để phân biệt transient waiting và stuck lâu.
14. `server.tomcat.mbeanregistry.enabled=true` và Actuator instrumentation phù hợp.
15. Không; Java 17 không hỗ trợ virtual threads chuẩn Java 21, và WebFlux event loop vẫn phải không blocking.
16. Kiểm tra server thực (Tomcat hay Netty), MBean Registry, dependencies, metric names/tags sau upgrade.
17. Dồn thêm concurrent load xuống remote đang throttle, làm outage/retry storm nặng hơn.
18. Hikari acquire timeout, SQL query timeout, HTTP connect/read timeout, gateway/client total deadline (còn nhiều).
 
## 24. Checklist điều tra production

- [ ] Có correlation/trace ID nối client, ingress, app, DB và dependency.
- [ ] Có timestamp cho request arrival, controller START, outbound calls, FINISH/cancel.
- [ ] Phân biệt request chưa tới app, đang xếp hàng, đã vào handler và đã ra response.
- [ ] Biết app chạy MVC/Tomcat hay WebFlux/Reactor Netty **thật**.
- [ ] Thu p50/p95/p99, RPS, errors, 429/502/503/504 và in-flight count nếu available.
- [ ] Có Tomcat `threads.busy`/current khi MBean registry enabled.
- [ ] Có Hikari active/pending/acquisition timeout và SQL/lock evidence.
- [ ] Có HTTP client metrics và pending acquisition nếu dùng connection pool.
- [ ] Có CPU/quota/throttling, GC pause, heap/threads/FD counts.
- [ ] Có 2–3 thread dumps/JFR **khi sự cố đang xảy ra**, với access controls.
- [ ] Không chỉ suy nguyên nhân từ `WAITING`/`BLOCKED`, đã kiểm tra lock owners.
- [ ] Tìm blocking Java/JDBC/HTTP calls trên Reactor event-loop threads.
- [ ] Kiểm tra proxy/client deadlines trước khi quy 504 cho backend.
- [ ] Không nhầm Tomcat connector timeout với sync controller timeout.
- [ ] Đặt Hikari acquire, HTTP connect/read, reactive deadline theo từng boundary.
- [ ] Không retry quá deadline, có jitter/bulkhead/rate limit/idempotency nếu cần.
- [ ] Không expose debug/threaddump/heapdump/env endpoints ra Internet.
- [ ] Không chạy các endpoint anti-pattern của lab trong production.
- [ ] Sau thay đổi, đo lại tail latency/errors/queue/pool/CPU cùng workload.
- [ ] Khi upgrade, so dependencies/web stack/metrics/config và có rollback canary.

## 25. Tài liệu chính thức

1. Spring Boot 3.3 — Actuator Metrics: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
2. Spring Boot 3.3 — Common Application Properties (Tomcat connection timeout, MVC async timeout, Hikari): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
3. Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
4. Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
5. Spring Boot 3.3 — Observability and Tracing: https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html
6. Spring Boot 3.3 — Calling REST Services: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
7. Spring Framework 6.1 — WebClient Configuration and Timeouts: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
8. Reactor Core — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
9. Reactor Core — Wrapping Synchronous Blocking Calls: https://projectreactor.io/docs/core/release/reference/faq.html
10. Reactor Netty 1.1 — HTTP Client, ConnectionProvider Metrics and Pool: https://projectreactor.io/docs/netty/1.1.23/reference/index.html
11. Java 17 — jcmd Thread.print / JFR.start diagnostic command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
12. Micrometer — Timers and percentiles: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
13. OpenTelemetry — Trace context and spans: https://opentelemetry.io/docs/concepts/signals/traces/
14. HikariCP — Connection timeout and pool configuration: https://github.com/brettwooldridge/HikariCP
