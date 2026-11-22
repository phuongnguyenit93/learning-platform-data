# Tìm điểm nghẽn ở luồng xử lý, event loop, connection pool hoặc dịch vụ phụ thuộc

## 1. Mục tiêu bài học và nguyên tắc điều tra

Một API Spring Boot đang trả lời chậm. Nguyên nhân có thể nằm ở **luồng xử lý request**, **Reactor Netty event loop**, **connection pool** của HTTP client hoặc database, hoặc **dịch vụ phụ thuộc** (downstream). Tăng `server.tomcat.threads.max`, Hikari pool hay số kết nối HTTP mà chưa đo đạc có thể khiến hệ thống chậm hơn.

**Điểm nghẽn (bottleneck)** là tài nguyên/giai đoạn giới hạn thông lượng hoặc làm tăng thời gian chờ khi tải tăng. Bài thuộc nhóm **Hiệu năng và giới hạn** của Spring Boot web-runtime. Sau bài này, bạn có thể:

1. Tách một lần gọi API thành các chặng: hàng đợi nhận request, xử lý controller, chờ DB pool, chờ HTTP client pool, chờ remote service và ghi response.
2. Phân biệt **CPU saturation**, **Servlet worker thread starvation**, **blocking event loop**, **pool exhaustion** và **downstream latency** qua các dấu hiệu đo được.
3. Dùng Spring Boot 3.3 Actuator/Micrometer, thread dump `jcmd`, Java Flight Recorder, distributed tracing và phép thử tải để thu thập bằng chứng.
4. Chạy hai lab **Java 17 + Spring Boot 3.3.5**: MVC có giới hạn Tomcat worker/Hikari/downstream; WebFlux có blocking vs non-blocking endpoint.
5. Biết cách xác định nút thắt bằng A/B experiment có kiểm soát, kiểm tra queue time, throughput, p95/p99, error rate và saturation.
6. Chọn biện pháp đúng: tối ưu code/query, giảm blocking, bounded offload, điều chỉnh pool theo sức chịu tải, giới hạn concurrency, timeout, circuit breaker, cache hoặc cải thiện downstream.
7. Không nhầm “tăng latency” với “hỏng server”, “WAITING” với CPU load, “nhiều connections” với throughput tốt, hay “WebFlux” với tự động không blocking.

**Quy trình chuẩn:** xác định triệu chứng → đo từng chặng → tạo giả thuyết → thí nghiệm thay **một yếu tố** → xác nhận bằng metrics/traces → kiểm thử lại dưới tải tương đương. Không chẩn đoán chỉ từ một con số CPU hoặc một ảnh thread dump.

## 2. Một request đi qua những nơi nào?

### 2.1. Spring MVC, gọi JDBC và HTTP downstream

~~~text
HTTP client / browser
        |
        v
Network / load balancer / reverse proxy
        |
        v
Tomcat listening socket + accept/request queue
        |
        v
Servlet worker thread
        |
        +--> Controller / service / validation / JSON
        |
        +--> JDBC DataSource / Hikari pool
        |         |
        |         +--> chờ lấy connection
        |         '--> SQL query / DB locks / database CPU
        |
        +--> RestClient / outbound HTTP connection pool
                  |
                  +--> chờ pool lease
                  +--> DNS / TCP connect / TLS
                  '--> downstream network + server + DB
        |
        v
Serialize HTTP response -> browser
~~~

Controller thực thi code Java, nhưng tổng độ trễ request còn gồm **thời gian chờ tài nguyên** và **thời gian ở các hệ thống khác**. Một Tomcat worker đang chờ JDBC có thể không dùng CPU đáng kể dù latency cao. Ngược lại, endpoint CPU-bound có thể chiếm CPU nhưng không cần chờ pool.

### 2.2. Spring WebFlux, Reactor Netty

~~~text
Incoming socket
      |
      v
Reactor Netty event-loop thread
      |
      v
WebFlux reactive handler
      |
      +--> non-blocking operators / async I/O
      |
      +--> WebClient with event-loop / connection provider
      |        |
      |        +--> pending acquire / DNS / TLS / downstream
      |        '--> response signal
      |
      +--> blocking library?  <-- NGUY CƠ nếu chạy trực tiếp trên event loop
      |
      v
Publisher emits -> write response
~~~

Event loop thường có **ít threads** hơn số request đồng thời: một thread phục vụ nhiều sockets bằng non-blocking I/O. Nếu code `Thread.sleep()`, `Future.get()`, JDBC blocking, `RestClient.retrieve().body()` hoặc `Mono.block()` chạy trên event loop, các kết nối khác có thể không được phục vụ kịp, gây **head-of-line blocking**.

**Điểm cần nhớ:** MVC blocking không tự là lỗi; WebFlux reactive không tự loại bỏ mọi blocking. Quan trọng là mô hình thực thi và giới hạn concurrency phù hợp với tác vụ.

## 3. Bắt đầu bằng triệu chứng thay vì chỉnh cấu hình

| Triệu chứng | Giả thuyết đáng thử | Bằng chứng phân biệt |
| --- | --- | --- |
| p95/p99 tăng nhưng CPU thấp | Thread chờ, DB/HTTP pool pending, downstream chậm | Thread states, queue metrics, spans chờ, connection acquire |
| CPU gần mức quota, throughput không tăng | CPU-bound service, JSON, crypto, GC hoặc quá nhiều context switching | CPU per process/thread, JFR CPU profile, GC |
| Tomcat busy workers ≈ max và requests xếp hàng | Worker thread exhaustion/synchronous blocking | `tomcat.threads.busy`, thread dump, active requests, queue/latency |
| WebFlux chậm hàng loạt dù downstream nhanh | Blocking Reactor event loop | Thread name `reactor-http-nio-*`, BlockHound/JFR/thread dump, baseline so sánh |
| Hikari active=max, pending tăng | Chờ JDBC connection | `hikaricp.connections.active` và `.pending`, acquisition timeout, slow SQL |
| Reactor Netty client active=max, pending connections tăng | Outbound HTTP pool saturation | Reactor Netty connection-provider gauges và pending acquire timer |
| HTTP client latency tăng trước server latency | Remote dependency bị chậm | Client span, dependency RPS/p95, remote metrics |
| Gateway trả 503/504 khi service chính vẫn sống | Connect/read timeout, DNS, TLS, pool wait hoặc remote down | Outbound errors, trace, dependency health |
| Throughput không tăng dù thêm threads/connections | Nút thắt ở DB/CPU/downstream hoặc contention | Capacity curve và metrics từng tài nguyên |
| Latency tăng theo thời gian, GC pauses tăng | Memory pressure, allocation, heap/GC hoặc leak | `jvm.gc.pause`, heap occupancy, JFR allocations |
| Chỉ một endpoint chậm | Query, lock, serialization hoặc một dependency cụ thể | Route-level metrics và traces, query plan |
| Tất cả endpoints kể cả /fast chậm | Shared resource như event loop, CPU, request queue hoặc proxy | So sánh /fast với /slow, process and infrastructure metrics |

**Một metric không đủ kết luận.** Ví dụ Hikari active=max có thể hợp lý nếu queries rất nhanh và không ai pending; chỉ khi acquisition wait/error/latency tăng mới có cơ sở coi pool là nút thắt.

## 4. Những số đo tối thiểu phải thu thập

### 4.1. Latency, throughput, error và saturation

Theo mô hình thực hành **RED/USE**:

- **Rate:** requests/s hoặc transactions/s theo route, client dependency.
- **Errors:** 4xx/5xx, timeout, failed pool acquire, connect reset, rejected tasks, 429.
- **Duration:** p50, p95, p99, maximum trong một cửa sổ có ý nghĩa; đo server và outbound call riêng.
- **Utilization:** CPU, heap, threads busy, active pool connections.
- **Saturation:** queue depth/pending acquires, queue delay, blocked requests, executor rejections.
- **Resource errors:** OOM, socket/file descriptor exhaustion, TLS/handshake failures, GC pause.

### 4.2. Tổng thời gian không bằng CPU time

Phân rã ước lượng:

\[
T_{\text{end-to-end}}
 = T_{\text{proxy/queue}}
 + T_{\text{controller}}
 + T_{\text{pool-wait}}
 + T_{\text{remote}}
 + T_{\text{response}}
\]

Đây là sơ đồ thành phần thực hành, **không phải công thức cộng không điều kiện** cho mọi hệ thống. Khi có parallel fan-out hoặc overlapping asynchronous work, phải dùng **critical path** thay vì cộng mọi span durations. Network time, retries, pool acquire và instrumentation overhead có thể nằm lồng trong spans khác nhau; tránh double-count.

Ví dụ request 800 ms, trong đó DB acquire 500 ms, query 20 ms, serialization 3 ms: tối ưu code Java 3 ms không giải quyết phần chờ chính. Ngược lại, nếu CPU profile cho thấy 80% mẫu tập trung ở JSON transformation, tăng Hikari pool khó giúp cải thiện.

### 4.3. So baseline với tải cao

Ghi rõ:

| Trường hợp | Concurrency | Rate | p95 | Errors | Saturation |
| --- | --- | --- | --- | --- | --- |
| Baseline không tải | Thấp | Thấp | Đo thực tế | Đo | Đo |
| Tải vừa | Tăng có kiểm soát | Đo | Đo | Đo | Đo |
| Gần ngưỡng | Tăng tiếp | Đo | Đo | Đo | Đo |
| Sau một thay đổi | Giữ cùng workload | So với trước | So | So | So |

Không tự điền số “đẹp” vào bảng; cần **kết quả đo thực** từ cùng build, máy/quota, request mix, upstream health, thời gian warm-up và network conditions. Kiểm thử tải sản xuất phải có phân quyền, rate limits và kế hoạch rollback; lab chạy local.

## 5. Actuator và Micrometer trong Spring Boot 3.3

Spring Boot Actuator 3.3 cung cấp metrics qua Micrometer khi có starter phù hợp. Ví dụ tên meter thường dùng:

| Meter / endpoint name | Ý nghĩa | Điều kiện quan trọng |
| --- | --- | --- |
| `http.server.requests` | Latency/count HTTP requests do MVC/WebFlux xử lý | Server observation/instrumentation |
| `http.client.requests` | Các outbound calls từ RestClient/RestTemplate/WebClient | **Dùng Boot auto-configured builder** hoặc customizer |
| `tomcat.threads.busy` | Số Tomcat request threads bận | `server.tomcat.mbeanregistry.enabled=true` |
| `tomcat.threads.current` | Số Tomcat threads hiện có | Tomcat MBean registry enabled |
| `jdbc.connections.active` | JDBC connections đang sử dụng | DataSource instrumentation/pool metadata |
| `jdbc.connections.max` | Giới hạn connections JDBC | DataSource pool instrumentation |
| `hikaricp.connections.active` | Hikari active connections | HikariCP đang dùng và được instrument |
| `hikaricp.connections.pending` | Threads đang chờ Hikari pool | Phải có traffic đang chờ; đọc sau khi tải dừng có thể 0 |
| `jvm.threads.live` | Số Java live threads | JVM metrics có mặt |
| `jvm.gc.pause` | Thời gian dừng GC | Micrometer JVM instrumentation |
| `process.cpu.usage` | CPU process ratio | Theo runtime và exporter |
| `system.cpu.usage` | CPU hệ thống | Có thể khác CPU quota/container |
| `reactor.netty.connection.provider.pending.connections` | Requests chờ lấy outbound Reactor Netty connection | **Phải bật metrics** của connection provider thích hợp |
| `reactor.netty.connection.provider.active.connections` | Active connections trong HTTP client pool | Cần đúng provider/metrics configuration |

**Các metric không xuất hiện là bình thường nếu chưa có component hoặc chưa bật instrumentation.** Spring Boot 3.3 tài liệu nêu Tomcat instrumentation chỉ được tự động kích hoạt khi **MBean Registry** được bật; mặc định registry không bật. Reactor Netty pool gauges cần pool metrics được kích hoạt và có pool thực sự phát traffic. Đừng tự cho rằng không thấy meter nghĩa là pool bằng 0.

### 5.1. Các endpoint Actuator dùng trong lab

Thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Cấu hình **chỉ cho môi trường lab**:

~~~properties
management.endpoints.web.exposure.include=health,info,metrics
server.tomcat.mbeanregistry.enabled=true
~~~

Thử:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.pending
~~~

`/actuator/metrics` liệt kê meter names **đã đăng ký trong process**. Một số tên chỉ xuất hiện **sau khi có request tạo sample** hoặc component/pool được khởi tạo. HTTP response của metrics là JSON với `measurements`, `availableTags`; không suy diễn p95 trực tiếp từ một snapshot timer `TOTAL_TIME`.

**Bảo mật:** exposure endpoint metrics có thể tiết lộ topology/traffic; giữ lab bind `127.0.0.1`. Trong production, đặt management endpoint sau security/network policy, chỉ expose phần cần thiết. `health` cũng có thể lộ thông tin nếu cho `show-details=always` công khai.

### 5.2. Histogram và p95 trong Prometheus

Khi sử dụng Micrometer Prometheus registry, có thể bật histogram cho server timer:

~~~properties
management.metrics.distribution.percentiles-histogram.http.server.requests=true
~~~

Ví dụ PromQL với bucket metrics khi exporter/histogram đã bật:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Tên cụ thể của metric/tags phụ thuộc registry và version; Prometheus thường chuyển dấu chấm thành dấu gạch dưới và timer seconds. Histogram từ distribution statistics **không tự xuất hiện** nếu chưa bật và dùng registry hỗ trợ. Dùng **URI template** thay vì full user-controlled URL để tránh tăng metric cardinality.

## 6. Lab A — Spring MVC: worker, Hikari pool và downstream

Ta xây một app Spring Boot 3.3.5/Java 17 có ba endpoint cố ý gây chậm:

- `GET /api/worker?ms=1200`: giữ Tomcat worker bằng `Thread.sleep` để mô phỏng blocking call.
- `GET /api/db?ms=1200`: lấy Hikari JDBC connection rồi giữ trong lúc sleep, mô phỏng slow query/transaction chiếm pool.
- `GET /api/remote/{kind}`: dùng `RestClient` gọi server phụ thuộc chạy riêng ở port 8091 (fast, slow hoặc hang).

**Các hành vi sleep là cố tình xấu để học cách nhận diện bottleneck**, không phải mẫu code nghiệp vụ production. Để tránh lạm dụng, app chỉ bind localhost, thời gian sleep bị giới hạn, và lab không có public network exposure.

### 6.1. Cấu trúc project

~~~text
mvc-bottleneck-lab/
├── pom.xml
├── downstream/
│   └── RemoteStub.java
├── tools/
│   └── load.py
└── src/main/
    ├── java/com/example/perf/
    │   ├── PerfMvcApplication.java
    │   └── ProbeController.java
    └── resources/
        └── application.properties
~~~

Dự án Maven chỉ chứa Spring Boot app. `RemoteStub` là Java HTTP server JDK 17 độc lập, có thể chạy/stop riêng để quan sát downstream; `load.py` dùng Python 3 tiêu chuẩn để tạo đồng thời nhiều request, không cần package bên ngoài.

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>mvc-bottleneck-lab</artifactId>
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

**Lưu ý:** `spring-boot-starter-jdbc` sử dụng HikariCP mặc định trong điều kiện tương ứng; H2 là embedded SQL database cho demo. `starter-actuator` để quan sát meters. Không cần WebFlux starter trong project MVC này.

### 6.3. application.properties

**Tệp `src/main/resources/application.properties`:**

~~~properties
server.address=127.0.0.1
server.port=8080

# Giới hạn ít worker để dễ thấy dấu hiệu queueing.
server.tomcat.threads.max=8
server.tomcat.mbeanregistry.enabled=true

# H2 in-memory và Hikari pool rất nhỏ cho thí nghiệm.
spring.datasource.url=jdbc:h2:mem:perfdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=2
spring.datasource.hikari.minimum-idle=2
spring.datasource.hikari.connection-timeout=700

# Downstream service ở terminal riêng.
app.remote.base-url=http://127.0.0.1:8091

management.endpoints.web.exposure.include=health,info,metrics
management.endpoint.health.show-details=never
~~~

- Tomcat max=8 **không phải** khuyến nghị production; dùng để thấy nghẽn dưới tải local.
- Hikari max=2 và connection timeout 700 ms dùng để quan sát **pending acquire**/timeout, không tối ưu cho mọi database.
- `spring.datasource.hikari.connection-timeout` là **timeout chờ lấy connection** từ Hikari; khác với SQL query timeout.
- `server.tomcat.mbeanregistry.enabled=true` giúp actuator có Tomcat metrics theo Boot 3.3.
- Không mở actuator ra public network. Một số metrics chỉ xuất hiện khi có traffic/connection.

### 6.4. Main class

**Tệp `src/main/java/com/example/perf/PerfMvcApplication.java`:**

~~~java
package com.example.perf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PerfMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(PerfMvcApplication.class, args);
    }
}
~~~

### 6.5. Controller tạo ba kiểu chậm

**Tệp `src/main/java/com/example/perf/ProbeController.java`:**

~~~java
package com.example.perf;

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
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@RestController
@RequestMapping("/api")
public class ProbeController {

    private final DataSource dataSource;
    private final RestClient client;

    public ProbeController(
            DataSource dataSource,
            RestClient.Builder builder,
            @Value("${app.remote.base-url}") String baseUrl) {
        this.dataSource = dataSource;

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofMillis(500));
        factory.setReadTimeout(Duration.ofMillis(1500));

        this.client = builder
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }

    @GetMapping("/fast")
    public String fast() {
        return "fast-ok";
    }

    @GetMapping("/worker")
    public ResponseEntity<String> worker(
            @RequestParam(defaultValue = "1200") int ms) {
        if (ms < 0 || ms > 3000) {
            return ResponseEntity.badRequest().body("invalid ms");
        }

        try {
            Thread.sleep(ms); // CỐ TÌNH blocking để minh họa.
            return ResponseEntity.ok("worker:" + ms);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("worker interrupted");
        }
    }

    @GetMapping("/db")
    public ResponseEntity<String> db(
            @RequestParam(defaultValue = "1200") int ms) {
        if (ms < 0 || ms > 3000) {
            return ResponseEntity.badRequest().body("invalid ms");
        }

        try (Connection connection = dataSource.getConnection()) {
            // Đang GIỮ JDBC connection: cố tình mô phỏng query chậm.
            Thread.sleep(ms);
            return ResponseEntity.ok("db:" + ms);
        } catch (SQLException ex) {
            // Demo gộp lỗi SQL/pool; production cần phân loại cụ thể.
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("db connection unavailable");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("db request interrupted");
        }
    }

    @GetMapping("/remote/{kind}")
    public ResponseEntity<String> remote(@PathVariable String kind) {
        if (!("fast".equals(kind) ||
              "slow".equals(kind) ||
              "hang".equals(kind))) {
            return ResponseEntity.badRequest().body("invalid kind");
        }

        try {
            String body = client.get()
                    .uri("/remote/{kind}", kind)
                    .retrieve()
                    .body(String.class);
            return ResponseEntity.ok(body == null ? "" : body);

        } catch (ResourceAccessException ex) {
            // Connect/read timeout hoặc network errors.
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("remote unavailable");
        } catch (RestClientResponseException ex) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body("remote HTTP error");
        } catch (RestClientException ex) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body("remote response error");
        }
    }
}
~~~

Các điểm quan trọng:

1. `/fast` là endpoint không có `sleep`, `DB` hay HTTP downstream; nó đóng vai trò **control group**.
2. `/worker` cố tình giữ **Tomcat request thread**. CPU usage có thể thấp vì thread đang ở trạng thái `TIMED_WAITING`, trong khi số Tomcat busy workers vẫn cao.
3. `/db` giữ Hikari JDBC connection trong khi chờ. Nếu hai connections đã active, requests tiếp theo **chờ pool**; chờ quá 700 ms có thể ném `SQLException` (thường `SQLTransientConnectionException` từ Hikari). Controller map 503 trong lab; đó **không** là status tự động của mọi Hikari timeout.
4. `/remote/{kind}` phát **outbound HTTP call** qua `RestClient`, dùng builder do Spring Boot inject để giữ client observations. `SimpleClientHttpRequestFactory` giúp timeout rõ ràng nhưng **không tạo Apache/Netty connection pool riêng có metrics pending**.
5. `readTimeout=1500ms` không phải overall request deadline. Vì vậy `hang` của downstream thường timeout trong lab; `slow` khoảng 900 ms thường thành công.
6. DTO trả là text cho đơn giản; timing đo cả Tomcat và HTTP client không chỉ thời gian sleep.
7. `Thread.sleep` bên trong transaction/giữ connection là **anti-pattern có chủ đích**. Không dùng trực tiếp trong business code.
8. HTTP status và exception handling đã được chuẩn hóa để client test có thể đếm lỗi, không gửi raw stack trace/internal host ra response.

## 7. Stub service để cô lập lỗi downstream

**Tệp `downstream/RemoteStub.java`:**

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
        System.out.println("RemoteStub listening on 127.0.0.1:8091");
    }

    private static void handle(HttpExchange exchange)
            throws IOException {
        String kind = exchange.getRequestURI().getPath()
                .substring("/remote/".length());
        long waitMs;

        if ("fast".equals(kind)) {
            waitMs = 0;
        } else if ("slow".equals(kind)) {
            waitMs = 900;
        } else if ("hang".equals(kind)) {
            waitMs = 3000;
        } else {
            waitMs = 0;
        }

        System.out.println("DOWNSTREAM kind=" + kind);
        try {
            Thread.sleep(waitMs);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }

        String response = "remote:" + kind;
        byte[] bytes = response.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(200, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }
}
~~~

Đây là server downstream thật chạy **process riêng** ở port `8091`, không thuộc Maven project. Thực tế, remote có thể chậm do DB, I/O, queue, GC hoặc network; `Thread.sleep` chỉ giả lập chậm để có tính lặp lại. Khi gateway timeout và đóng socket trước, stub có thể gặp lỗi khi gửi response; đó là hệ quả của client ngừng chờ.

Compile/run với JDK 17 trong terminal A (từ thư mục dự án):

~~~bash
cd downstream
javac --add-modules jdk.httpserver RemoteStub.java
java --add-modules jdk.httpserver RemoteStub
~~~

Chạy gateway trong terminal B, từ thư mục `mvc-bottleneck-lab`:

~~~bash
mvn spring-boot:run
~~~

Nếu đang ở `downstream`, quay về thư mục gốc trước khi chạy Maven. Đừng mở nhiều instances cùng port.

Kiểm tra bằng terminal C:

~~~bash
curl -i http://127.0.0.1:8080/api/fast
curl -i http://127.0.0.1:8080/api/worker?ms=1200
curl -i http://127.0.0.1:8080/api/db?ms=1200
curl -i http://127.0.0.1:8080/api/remote/fast
curl -i http://127.0.0.1:8080/api/remote/slow
curl -i http://127.0.0.1:8080/api/remote/hang
~~~

Kỳ vọng:

| Endpoint | Kết quả với một request ở trạng thái bình thường |
| --- | --- |
| `/api/fast` | HTTP 200, `fast-ok` |
| `/api/worker?ms=1200` | HTTP 200, `worker:1200`, khoảng 1,2 s + overhead |
| `/api/db?ms=1200` | HTTP 200, `db:1200` nếu lấy connection kịp |
| `/api/remote/fast` | HTTP 200, `remote:fast` nếu stub chạy |
| `/api/remote/slow` | HTTP 200, `remote:slow`, khoảng 0,9 s + overhead |
| `/api/remote/hang` | Trong lab thường 503 `remote unavailable` do read timeout 1,5 s |

Thời gian không phải output tuyệt đối: có thread scheduling, JIT, container, network loopback, cold start và pool initialization. Chỉ body/status đã được quyết định bởi code sau các điều kiện tương ứng.

## 8. Tạo tải lặp lại có kiểm soát

Dùng một script Python 3 standard library để đo latency, status và throughput từng endpoint, không lệ thuộc benchmark tool ngoài.

**Tệp `tools/load.py`:**

~~~python
import concurrent.futures
import math
import sys
import time
import urllib.error
import urllib.request

if len(sys.argv) != 4:
    print("Usage: python3 tools/load.py URL REQUESTS CONCURRENCY")
    sys.exit(2)

url = sys.argv[1]
requests = int(sys.argv[2])
concurrency = int(sys.argv[3])
if requests < 1 or concurrency < 1 or concurrency > 64:
    raise ValueError("requests>=1 and 1<=concurrency<=64 required")

def once(_):
    begin = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            response.read()
            status = str(response.status)
    except urllib.error.HTTPError as exc:
        exc.read()
        status = str(exc.code)
    except Exception:
        status = "ERR"
    latency_ms = 1000 * (time.perf_counter() - begin)
    return latency_ms, status

begin = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(
        max_workers=concurrency) as pool:
    results = list(pool.map(once, range(requests)))
elapsed = time.perf_counter() - begin

values = sorted(latency for latency, _ in results)
def percentile(fraction):
    index = max(0, math.ceil(fraction * len(values)) - 1)
    return round(values[index], 1)

by_status = {}
for _, status in results:
    by_status[status] = by_status.get(status, 0) + 1

print("requests=", requests, "concurrency=", concurrency)
print("total_seconds=", round(elapsed, 3))
print("throughput_rps=", round(requests / elapsed, 2))
print("p50_ms=", percentile(0.5), "p95_ms=", percentile(0.95),
      "p99_ms=", percentile(0.99))
print("status_counts=", by_status)
~~~

**Chú ý đo đạc:** `ThreadPoolExecutor` thực hiện một số lượng requests hữu hạn; `throughput_rps` là thông lượng quan sát trong batch, bao gồm scheduling và warm-up của client. Đây **không** phải load generator closed-loop tốc độ cố định, không đo server queue depth trực tiếp, và không thay thế k6/Gatling/wrk trong bài kiểm thử capacity chính thức. Với phân phối rất ít mẫu, percentile có độ tin cậy thấp; tăng sample và lặp nhiều vòng khi cần kết luận production.

Các lệnh chạy từ gốc project:

~~~bash
python3 tools/load.py http://127.0.0.1:8080/api/fast 50 8
python3 tools/load.py "http://127.0.0.1:8080/api/worker?ms=1200" 24 16
python3 tools/load.py "http://127.0.0.1:8080/api/db?ms=1200" 24 12
python3 tools/load.py http://127.0.0.1:8080/api/remote/slow 24 8
~~~

Trên Windows, nếu lệnh `python3` không có, có thể dùng `py tools/load.py ...`. Không chạy tải dồn vào production URL hoặc hệ thống không thuộc quyền kiểm soát.

**Đừng khẳng định một con số p95 cụ thể trước khi chạy thực tế.** Kết quả phụ thuộc CPU, OS, JIT, người dùng đang dùng máy và phiên bản thư viện.

## 9. Thí nghiệm 1 — tìm nghẽn Tomcat request workers

### 9.1. Chạy 16 concurrent calls, Tomcat max 8

~~~bash
python3 tools/load.py "http://127.0.0.1:8080/api/worker?ms=1200" 24 16
~~~

Mỗi request giữ Tomcat worker khoảng 1,2 s, trong khi cấu hình chỉ có tối đa 8 workers. Với 16 concurrent requests và 24 total requests:

- Một nhóm request có worker và đang sleep.
- Những request chưa có worker phải chờ ở các lớp queue/connector/socket; phản ứng cụ thể phụ thuộc Tomcat và OS.
- p95/p99 có thể tăng theo “đợt” chờ, dù CPU vẫn thấp.
- `/api/fast` cũng có thể chậm nếu thử **đúng lúc** workers đang bận bởi `/api/worker`: đây là dấu hiệu tài nguyên inbound dùng chung.

### 9.2. Đo trong khi tải đang chạy

Trong terminal khác:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.current
curl -s http://127.0.0.1:8080/actuator/metrics/process.cpu.usage
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
~~~

**Khi Tomcat bận hết**, request dùng để đọc actuator metrics cũng cần worker, có thể bị xếp hàng và **trả muộn**. Vì vậy giám sát production nên có time-series scrape và metrics agent/out-of-band phù hợp; đừng lấy việc endpoint metrics chậm làm bằng chứng metrics sai.

### 9.3. Thread dump sẽ cho thấy gì?

Tìm JVM PID:

~~~bash
jcmd -l
~~~

Lấy dump:

~~~bash
jcmd <PID> Thread.print
~~~

`<PID>` chỉ là placeholder cần thay bằng PID thực. Những stack frames thường thấy quanh:

~~~text
java.lang.Thread.sleep
com.example.perf.ProbeController.worker
... http-nio-8080-exec-...
~~~

Khi thread đang sleep, trạng thái thường là `TIMED_WAITING`. **Đây là luồng chiếm worker nhưng không nhất thiết đang tiêu thụ CPU.** Không áp kết luận “thread bị deadlock” chỉ vì nó đang `WAITING` hoặc `TIMED_WAITING`.

### 9.4. Cách khắc phục đúng

- Xác định **vì sao worker bị chiếm**: remote calls, JDBC, lock, file I/O hay business CPU.
- Với blocking MVC, đặt timeout và concurrency budget; khi upstream chậm, giảm việc giữ worker vô hạn.
- Nếu nhu cầu cao, cân nhắc async request handling, virtual threads theo đúng JDK/Boot và stack, hoặc reactive design khi thực sự phù hợp.
- Tăng max worker threads **chỉ khi** CPU/heap/downstream đủ năng lực và tải cho thấy bottleneck là worker availability; tăng vô hạn có thể làm Hikari/HTTP pool/DB sụp.
- Đặt rate limiting, queue/bulkhead limits và overload response phù hợp.

## 10. Thí nghiệm 2 — Hikari connection pool exhaustion

### 10.1. Vì sao nó khác Tomcat thread starvation?

Ở `/api/db`, code:

~~~java
try (Connection connection = dataSource.getConnection()) {
    Thread.sleep(ms);
}
~~~

lấy connection từ Hikari và **giữ nó** suốt thời gian sleep. Pool chỉ có `maximum-pool-size=2`. Nếu 12 requests gọi đồng thời, thường:

- Hai requests giữ hai connections.
- Các requests còn lại chờ `getConnection()` với `connection-timeout=700ms`.
- Một số requests có thể nhận `SQLException` do timeout và trả 503.
- Tomcat threads của chúng bị giữ trong khi **chờ pool**, dù database H2 và CPU không quá tải.
- Sau khi request đầu hoàn tất, `try-with-resources` trả connection về pool.

### 10.2. Chạy test

~~~bash
python3 tools/load.py "http://127.0.0.1:8080/api/db?ms=1200" 24 12
~~~

Trong khi tải chạy, quan sát:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.active
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.pending
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.max
curl -s http://127.0.0.1:8080/actuator/metrics/jdbc.connections.active
~~~

`hikaricp.connections.pending` có thể bằng 0 **sau khi batch kết thúc**; cần scrape đúng khoảng cao điểm hoặc theo dõi dashboard time-series. Vì các metrics có tag `pool` hoặc `name`, cần kiểm tra `availableTags` nếu có nhiều Hikari pools.

### 10.3. Dấu hiệu trong thread dump

Thread stack có thể chứa:

~~~text
com.zaxxer.hikari.pool.HikariPool.getConnection
com.zaxxer.hikari.HikariDataSource.getConnection
com.example.perf.ProbeController.db
~~~

Nhưng thread đang giữ connection và sleep sẽ có stack khác (đang trong `Thread.sleep`). Cần phân biệt:

- **Hikari active/max**: có connection lease.
- **Pending**: threads chờ lấy lease.
- **Acquire time**: thời gian chờ lấy.
- **Usage time**: thời gian giữ lease.
- **SQL/DB time**: thời gian remote DB thực thi query.

Không gọi `hikaricp.connections.active=max` là pool starvation nếu pending ~0, acquisition latency thấp và throughput đạt target.

### 10.4. Vì sao tăng maximum-pool-size chưa chắc đúng?

Giả sử DB chỉ xử lý tốt khoảng 10 queries song song; tăng Hikari max từ 10 lên 100 có thể gây quá nhiều concurrent SQL, lock contention, CPU/IO pressure và làm queries chậm hơn. Pool nên được sizing theo **DB capacity, transaction duration, concurrency và số app replicas**, không theo số Tomcat threads. Quan trọng hơn là:

- Giảm thời gian giữ connection; không sleep/call remote HTTP trong transaction.
- Tối ưu SQL plans, indexes, lock duration.
- Đảm bảo `Connection.close()`/`try-with-resources` trả về pool.
- Đặt acquisition timeout, leak detection khi thích hợp, không “vô hạn chờ”.
- Giám sát aggregate connections từ **tất cả replicas**, vì mỗi pod có pool riêng.

## 11. Thí nghiệm 3 — downstream chậm, không phải code controller chậm

### 11.1. So sánh fast, slow và hang

~~~bash
curl -i http://127.0.0.1:8080/api/remote/fast
curl -i http://127.0.0.1:8080/api/remote/slow
curl -i http://127.0.0.1:8080/api/remote/hang
~~~

Stub có `fast=0ms`, `slow=900ms` và `hang=3000ms`. MVC RestClient có `readTimeout=1500ms`, nên thường:

- `fast` thành công nhanh.
- `slow` thành công nhưng làm gateway giữ worker ~0,9 s.
- `hang` gây timeout, gateway map thành 503, trong khi downstream có thể vẫn đang sleep/xử lý.

Lấy metrics:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics/http.client.requests
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
~~~

Khi dùng Boot injected `RestClient.Builder`, Spring Boot Actuator có thể instrument HTTP client với meter `http.client.requests`. Nếu bạn dùng `RestClient.create()` độc lập mà không áp Boot customizer, đừng mặc định meter HTTP client có đủ. Với nhiều dependencies, cần tag/trace xác định remote host/URI template; không chỉ nhìn tổng thời gian tất cả HTTP client calls.

### 11.2. Dừng downstream server

Dừng terminal chạy `RemoteStub` bằng `Ctrl+C` nhưng giữ Spring Boot gateway chạy. Gọi:

~~~bash
curl -i http://127.0.0.1:8080/api/remote/fast
curl -i http://127.0.0.1:8080/api/fast
~~~

Tình huống đáng quan sát:

- `/api/remote/fast` thường thành 503 do connection refused hoặc timeout.
- `/api/fast` vẫn trả 200 vì không cần downstream.
- Nếu bắn nhiều requests remote cùng lúc, workers bị giữ và `/api/fast` có thể bị ảnh hưởng gián tiếp khi worker pool bị chiếm.

**Kết luận đúng:** gateway HTTP server vẫn sống, nhưng một dependency outbound bị lỗi. Chỉ nhìn readiness/HTTP 200 của `/api/fast` không đủ chứng minh mọi chức năng nghiệp vụ đang khỏe.

### 11.3. Bằng chứng từ distributed tracing

Ví dụ trace minh họa, không phải log tự động của lab:

~~~text
SERVER GET /api/remote/slow    944 ms
  |
  '-- CLIENT GET /remote/slow  915 ms
       |
       '-- REMOTE server work 900 ms
~~~

Nếu phần lớn time ở client span, hãy điều tra remote/network/client pool. Nếu client span ngắn nhưng server span dài, điều tra code trước/sau call, thread queue hoặc serialization. Khi call song song, xem **critical path** và thời gian chờ pool, không cộng mọi child span để suy ra wall-clock latency.

## 12. Lab B — WebFlux và blocking event loop

Lab này là **project Spring Boot riêng**, không thêm các class vào project MVC. Nó so sánh:

- `GET /loop/bad`: **cố ý** gọi `Thread.sleep(700)` bên trong reactive pipeline **không offload**, có thể chặn event-loop subscriber thread.
- `GET /loop/good`: dùng `Mono.delay`, không chặn thread chờ 700ms.
- `GET /loop/offload`: offload blocking task lên `Schedulers.boundedElastic()` để minh họa giải pháp chuyển tiếp khi chưa thể thay thư viện blocking.

### 12.1. Project và pom.xml

~~~text
webflux-loop-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/loop/
    │   ├── LoopApplication.java
    │   └── LoopController.java
    └── resources/
        └── application.properties
~~~

**Tệp `pom.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-loop-lab</artifactId>
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

Không thêm `spring-boot-starter-web`: khi có cả hai starters, Spring Boot 3.3 thông thường ưu tiên Servlet MVC, làm thí nghiệm event loop khác dự kiến.

### 12.2. Cấu hình và main

**`src/main/resources/application.properties`:**

~~~properties
server.address=127.0.0.1
server.port=8082
management.endpoints.web.exposure.include=health,metrics
~~~

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

### 12.3. Controller so sánh ba cách chờ

**`src/main/java/com/example/loop/LoopController.java`:**

~~~java
package com.example.loop;

import java.time.Duration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/loop")
public class LoopController {

    @GetMapping("/bad")
    public Mono<String> bad() {
        // CỐ TÌNH SAI: blocking khi publisher được subscribe.
        return Mono.fromCallable(() -> {
            Thread.sleep(700);
            return "bad:" + Thread.currentThread().getName();
        });
    }

    @GetMapping("/good")
    public Mono<String> good() {
        // Không chiếm thread trong lúc đợi 700ms.
        return Mono.delay(Duration.ofMillis(700))
                .map(tick ->
                        "good:" + Thread.currentThread().getName());
    }

    @GetMapping("/offload")
    public Mono<String> offload() {
        // Cần cho code blocking chưa thể thay thế.
        return Mono.fromCallable(() -> {
                    Thread.sleep(700);
                    return "offload:" +
                            Thread.currentThread().getName();
                })
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

**Điểm phân biệt:**

1. `bad()` trả `Mono`, nhưng `fromCallable` vẫn là **blocking code khi được subscribe**. Trong đường xử lý WebFlux/Reactor Netty thông thường, subscription có thể chạy trên event-loop thread nếu chưa có scheduler boundary; sleep chiếm event loop và trì hoãn xử lý sockets khác.
2. `good()` dùng timer `Mono.delay`, không giữ một event-loop thread bị sleep suốt 700 ms. Callback kết quả có thể chạy trên Reactor scheduler thread khác; thread name không được dùng làm API contract.
3. `offload()` đưa code blocking vào scheduler `boundedElastic` có số threads/queue hữu hạn. Đây là biện pháp chuyển tiếp; nếu đặt quá nhiều blocking tasks, boundedElastic cũng có thể **bão hòa**, xuất hiện queueing/latency.
4. Cả ba trả text có thread name để hỗ trợ quan sát. Tên như `reactor-http-nio-2` hay `boundedElastic-1` phụ thuộc runtime và concurrency; không nên hardcode expected name.
5. Thí nghiệm cố ý không có WebClient/DB để **cô lập** event-loop blocking khỏi network/downstream latency.

### 12.4. Chạy thí nghiệm

Trong `webflux-loop-lab`:

~~~bash
mvn spring-boot:run
~~~

Ở terminal khác:

~~~bash
curl -i http://127.0.0.1:8082/loop/bad
curl -i http://127.0.0.1:8082/loop/good
curl -i http://127.0.0.1:8082/loop/offload
~~~

Đợi khoảng 700 ms ở cả ba endpoint nhưng **khác nhau về loại tài nguyên bị giữ trong lúc chờ**. Chạy load script `tools/load.py` từ project MVC hoặc copy nó vào thư mục WebFlux nếu muốn:

~~~bash
python3 ../mvc-bottleneck-lab/tools/load.py \
  http://127.0.0.1:8082/loop/bad 40 20

python3 ../mvc-bottleneck-lab/tools/load.py \
  http://127.0.0.1:8082/loop/good 40 20

python3 ../mvc-bottleneck-lab/tools/load.py \
  http://127.0.0.1:8082/loop/offload 40 20
~~~

**Không ép kết luận chỉ từ một vòng chạy.** Số event-loop workers phụ thuộc CPU count và runtime; trên máy nhiều lõi, 20 requests có thể được phân phối khác máy ít lõi. Để xác nhận blocking, kết hợp sampling/JFR, thread names, latency của một endpoint control không blocking và số event-loop threads bận. Có thể thử `-Dreactor.netty.ioWorkerCount=2` trong **một process lab riêng** khi cần tái hiện, nhưng thay đổi event-loop threads là biến thí nghiệm, không phải mẹo performance production.

### 12.5. Vì sao không được gọi .block() trên event loop?

~~~java
// ANTI-PATTERN trong WebFlux reactive handler:
String result = webClient.get()
        .uri("/remote")
        .retrieve()
        .bodyToMono(String.class)
        .block();
~~~

Snippet minh họa **không phải Java class chạy độc lập**. `block()` đợi kết quả đồng bộ, có thể chặn event-loop; Reactor còn có các bảo vệ phát hiện blocking trên một số non-blocking schedulers. Không sửa bằng cách tăng vô hạn event-loop threads.

Đúng hơn, giữ pipeline:

~~~java
// Trong reactive service đã có WebClient:
Mono<String> result = webClient.get()
        .uri("/remote")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(2));
~~~

Nếu thư viện bên thứ ba chỉ có JDBC/IO blocking, offload với `Schedulers.boundedElastic()` trong giới hạn hợp lý, hoặc cân nhắc stack MVC/virtual threads. **Không đồng nhất boundedElastic với unlimited thread pool.**

## 13. Outbound HTTP connection pool: khác DB pool và Tomcat workers

Một request WebFlux dùng WebClient có thể cần **lease một outbound HTTP connection** từ Reactor Netty `ConnectionProvider`:

~~~text
WebFlux event loop
      |
      v
WebClient request
      |
      v
ConnectionProvider (HTTP client pool)
      |    active / idle / total
      |    pending acquire queue
      v
Remote host:port
      |
      v
HTTP response
~~~

Nếu pool active đạt giới hạn và pending tăng, request phải chờ lease hoặc timeout. **Điều này có thể xảy ra ngay cả khi CPU và event-loop threads đang rảnh.**

### 13.1. Dấu hiệu với Reactor Netty

Các gauges/timers khi pool metrics bật:

~~~text
reactor.netty.connection.provider.active.connections
reactor.netty.connection.provider.idle.connections
reactor.netty.connection.provider.total.connections
reactor.netty.connection.provider.max.connections
reactor.netty.connection.provider.pending.connections
reactor.netty.connection.provider.pending.connections.time
~~~

Đây là **Reactor Netty connection provider metrics**, không phải metrics Tomcat hay Hikari. Nếu backend dùng HTTP/2, còn có khái niệm active/pending **streams** trong các phiên bản phù hợp; không luôn suy số request đồng thời từ số TCP connections.

### 13.2. Ví dụ cấu hình WebClient pool có giới hạn

Snippet **độc lập về class** dưới đây dùng trong **project WebFlux có Reactor Netty + Micrometer**. Cần đặt vào package được scan và thay base URL service thật:

~~~java
package com.example.loop;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class WebClientPoolConfig {

    @Bean
    ConnectionProvider dependencyConnections() {
        return ConnectionProvider.builder("dependency")
                .maxConnections(10)
                .pendingAcquireMaxCount(20)
                .pendingAcquireTimeout(Duration.ofSeconds(1))
                .metrics(true)
                .build();
    }

    @Bean
    WebClient dependencyWebClient(
            WebClient.Builder builder,
            ConnectionProvider dependencyConnections) {
        HttpClient httpClient = HttpClient.create(dependencyConnections)
                .responseTimeout(Duration.ofSeconds(2));
        return builder
                .baseUrl("http://127.0.0.1:8091")
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
~~~

**Không copy code này vào MVC lab chỉ để mong tạo Tomcat pool.** Nó cấu hình **outbound Reactor Netty HTTP client** ở WebFlux project, không phải inbound Netty event-loop worker pool.

- `maxConnections(10)`: số active connections tối đa của provider theo mô hình pooling/remote address thực.
- `pendingAcquireMaxCount(20)`: giới hạn số acquisitions chờ, giúp tránh hàng đợi vô hạn.
- `pendingAcquireTimeout(1s)`: chờ quá hạn có thể fail acquire.
- `metrics(true)`: bật pool gauges khi Micrometer có mặt.
- `responseTimeout(2s)`: timeout HTTP response ở client, khác pool wait và overall business deadline.
- `WebClient.Builder` injected từ Boot giữ observations `http.client.requests` ở nơi tương ứng.
- `ConnectionProvider` tự tạo cần được quản lý lifecycle; khi đóng application, tùy custom resource cần dispose nếu không được framework quản lý. Có thể cấu hình bean `@Bean(destroyMethod="dispose")` hoặc quản lý qua Reactor Netty resource factory tùy thiết kế; tránh leak resources.
- Một HTTP/2 connection có thể multiplex nhiều streams; client/provider metrics cần được diễn giải theo protocol, không quy mọi active connections thành một request duy nhất.

**Không dùng mọi defaults từ tài liệu “latest” cho Boot 3.3 mà không đối chiếu version:** Reactor Netty `maxConnections`/pending defaults có thể thay đổi theo bản, CPU count và resource config. Hãy quan sát giá trị max meter thực khi chẩn đoán.

### 13.3. Biện pháp khi pending connections tăng

1. Xác định pool nào, remote address nào và acquisition wait bao lâu.
2. Xem remote latency: nếu service chậm, tăng pool có thể chỉ **đẩy nhiều tải hơn xuống service đang yếu**.
3. Giữ connections sống/tái sử dụng; tránh tạo `WebClient`/provider tùy tiện per request.
4. Đặt queue size/timeout, concurrency limit và circuit breaker hợp lý.
5. Cân nhắc tăng pool có kiểm soát nếu downstream và network còn capacity, kiểm tra lại throughput/p95/errors.
6. Với DB pool, điều tra query/locks; với HTTP client pool, điều tra per-host connections, HTTP/2 multiplexing, remote rate limit — **không đánh đồng hai pool**.

## 14. Phân biệt worker, event loop, JDBC pool và client pool

| Tài nguyên | Thuộc về | Khi cạn sẽ xảy ra | Quan sát |
| --- | --- | --- | --- |
| Tomcat request worker | Inbound MVC | Request mới chờ worker, latency tăng | `tomcat.threads.busy`, thread dump |
| Reactor Netty event loop | Inbound/async I/O WebFlux | Nhiều sockets bị chậm khi có blocking task | Event-loop thread stack/CPU, latency /fast, JFR |
| Hikari JDBC connection | Database outbound | Threads chờ `getConnection()`, acquire timeout | Hikari active/pending/timeout, slow queries |
| Reactor Netty HTTP client connection | Remote HTTP outbound | Requests pending lease, acquire timeout | ConnectionProvider active/pending |
| DB server worker/lock | Downstream database | Query latency/lock wait tăng dù Hikari pool còn connection | DB dashboard, query plan/lock stats |
| Remote HTTP service worker | Dependency | HTTP client latency/p95 tăng, 429/5xx | Client spans và remote metrics |
| CPU cores / cgroup quota | Host/container | CPU runnable threads xếp hàng | CPU usage/throttling, profiler |
| Heap/GC | JVM | Pause, allocation pressure, latency spikes | `jvm.gc.pause`, heap, JFR |

**Một hệ thống có thể bị nghẽn nhiều tầng cùng lúc**: downstream chậm → HTTP client pool lease lâu → MVC workers chờ → Tomcat queue tăng → frontend timeout. Khi ấy “Tomcat bận” là **triệu chứng thứ cấp**; gốc có thể là dependency. Cần tìm *bottleneck đầu tiên* trong critical path, không chỉ nơi thấy alert đầu tiên.

## 15. Little’s Law và giới hạn concurrency

Trong trạng thái ổn định:

\[
L = \lambda W
\]

- `L`: số công việc đang ở trong hệ thống/trong chặng được đo.
- `λ`: arrival/throughput rate (công việc mỗi giây) tại cùng boundary.
- `W`: average time một công việc tồn tại trong boundary đó.

Ví dụ giả định: outbound call rate `100 requests/s`, thời gian mỗi call trung bình `0,2s` → số calls đang thực hiện trung bình khoảng `20`. Nếu dependency chậm lên `0,8s` ở cùng throughput, concurrency trung bình có thể tăng lên khoảng `80`.

**Đây là phép tính minh họa**, không phải khuyến nghị set pool=20 hay 80. Cần xem queue, tail latency, HTTP/2 multiplexing, replica counts và capacity downstream. Trong hệ thống có feedback/backpressure, throughput cũng có thể giảm khi saturation, nên không thể giữ `λ` cố định tùy ý.

### 15.1. Queueing và điểm gãy

Khi utilization của một resource gần 100%, thời gian chờ có thể tăng **phi tuyến**, nhất là khi arrival không đều. Vì thế:

- Hikari connection active=max **và pending tăng** là tín hiệu nguy hiểm hơn active=max đơn lẻ.
- Tomcat busy=max **và request queue tăng/p95 xấu** là tín hiệu worker saturation.
- CPU≈100% **và run queue tăng** cho thấy compute pressure.
- HTTP client pool pending tăng nhưng remote latency cũng tăng: pool pressure có thể là hậu quả của remote.

Không đặt “mục tiêu 100% pool utilization” cho mọi thời điểm. Một hệ thống cần headroom để chịu bursts, GC, reconnect và retries.

## 16. Thread dump, JFR và profiler dùng thế nào?

### 16.1. Thread dump — snapshot, không phải kết luận cuối

Đầu tiên tìm PID Java:

~~~bash
jcmd -l
~~~

Sau đó:

~~~bash
jcmd <PID> Thread.print
~~~

Lấy **vài snapshots trong khoảng bị chậm**, cách nhau vài giây, để phân biệt luồng tạm chờ với trạng thái kéo dài. Trong output, tìm:

- `http-nio-...-exec-*` của Tomcat và controller service method stack.
- `reactor-http-nio-*` của Reactor Netty: có `Thread.sleep`/JDBC/`block()` hay không.
- `HikariPool.getConnection`: request đang chờ pool acquire.
- Socket read/HTTP client stack: đang chờ network, không nhất thiết lỗi code.
- `BLOCKED` trên monitor/lock: có contention, cần xác định owner của lock.
- CPU hot threads: cần CPU samples, không đo CPU từ một line stack.

`WAITING`, `TIMED_WAITING` và `RUNNABLE` là JVM thread states **không đồng nghĩa 1:1 với mức dùng CPU**; OS scheduling và native I/O vẫn ảnh hưởng.

### 16.2. Java Flight Recorder (JFR)

Trên JDK 17 hỗ trợ Flight Recorder, có thể bắt một bản ghi ngắn **ở môi trường được phép**:

~~~bash
jcmd <PID> JFR.start name=perf settings=profile duration=30s filename=perf.jfr
~~~

Sau khi file hoàn thành, xem trong JDK Mission Control hoặc công cụ tương thích. Các tín hiệu hữu ích:

- CPU method sampling/hot stacks.
- Lock contention và thread park.
- Socket read/write events và file I/O.
- Allocation pressure và GC pauses.
- Thread scheduling và các thời điểm latency spikes.

**JFR/profiling có overhead nhất định.** Chọn sampling period, duration, dữ liệu nhạy cảm và tải phù hợp; không vô cớ bật verbose profiling vĩnh viễn trên production. Nếu muốn theo dõi CPU quota/throttling của container, cần metrics từ host/cgroup ngoài JVM.

### 16.3. BlockHound cho reactive blocking

BlockHound có thể hỗ trợ phát hiện một số blocking calls trên Reactor non-blocking threads trong test/lab; nhưng nó là dependency/công cụ bổ sung và có yêu cầu tương thích JDK/runtime. **Không tự xem việc chưa có cảnh báo BlockHound là chứng minh không có blocking.** Kết hợp code review, thread dump, tracing và event-loop latency.

### 16.4. Database-specific evidence

Khi nghi ngờ Hikari cạn, hỏi:

1. Có bao nhiêu connections đang active/pending?
2. Mỗi connection bị giữ bao lâu?
3. DB đang chạy query nào, có lock wait, full scan, thiếu index hoặc transaction quá dài không?
4. Có connection leak không? Có đóng `Connection`/`ResultSet` và trả về pool không?
5. Mỗi replica dùng pool bao nhiêu? Tổng connections có vượt `max_connections` của DB không?

Chỉ có `hikaricp.connections.pending` không phân biệt “pool quá nhỏ” với “query quá chậm”; cần thêm SQL time và query plan.

## 17. Tracing từng hop: tìm critical path

Một trace có thể mô tả:

~~~text
Browser request total: 1400ms
  |
  +-- inbound controller / authentication: 20ms
  |
  +-- DB connection acquire: 500ms
  +-- DB query: 30ms
  |
  +-- outbound HTTP client: 800ms
  |     '-- remote service processing: 760ms
  |
  '-- encode response: 10ms
~~~

Các số ở trên **chỉ minh họa**; đừng cộng nếu span nested hoặc các calls song song. Trong một trace thật cần phân biệt **server span**, **client span**, custom span đo pool/SQL và thời gian đầu-cuối.

Để có distributed tracing cần cấu hình Micrometer Tracing/OpenTelemetry bridge, exporter, tracing context propagation, sampling và instrumentation thích hợp. Spring Boot Actuator cơ bản **không tự xuất mọi span end-to-end vào tracing backend** nếu thiếu dependencies/config.

**Câu hỏi tìm gốc:**

- Server span dài nhưng client/DB spans ngắn? Có queuing, CPU, serialization hoặc uninstrumented blocking?
- Client span dài, remote server span ngắn? Có connect/queue/network, proxy, TLS, retries hoặc instrumentation gap?
- Remote server span cũng dài? Điều tra resource/DB của remote service.
- Một số endpoints chậm vì cùng dependency? Phân tách dependency tag và per-route metrics.

Không log raw tokens/cookies/PII hay query parameters nhạy cảm; dùng URI templates và sampling.

## 18. Sửa đúng nút thắt, không chỉ tăng tài nguyên

| Gốc đã được xác nhận | Biện pháp ưu tiên | Điều phải kiểm tra sau thay đổi |
| --- | --- | --- |
| MVC worker chờ I/O quá lâu | Timeout, concurrency limit, async handling hoặc stack phù hợp | Busy workers, p95, remote errors |
| Blocking WebFlux event loop | Dùng non-blocking API, offload bounded blocking work | Event-loop latency, boundedElastic queue, p99 |
| DB query chậm | SQL/index/query plan, transaction ngắn, DB capacity | Query time, locks, Hikari usage |
| Hikari acquisition pending | Rút ngắn connection hold, sizing pool theo DB, giới hạn load | Pending acquire, DB CPU, total connections |
| HTTP client pool pending | Reuse client, optimize remote, cap queue, adjust pool có kiểm soát | Pending acquire, remote latency, error rate |
| Downstream chậm/429 | Cache khi hợp lệ, bulkhead, timeout, rate limit, circuit breaker | Remote p95/429, fallback rate, user SLA |
| CPU saturation | Tối ưu hot path, allocations, serialization, caching, scale | CPU p95, GC, throughput |
| GC pressure | Giảm allocations/buffers, tune heap/GC dựa trên JFR | GC pause time, memory retention |
| Proxy/network | TLS, DNS, routing, keepalive, idle timeout tuning | Client connect time, resets, latency |
| Load burst / queue overload | Admission control, bounded queue, fast rejection | Tail latency, drop/reject rate, recovery |

**Tăng threads hoặc pool không phải giải pháp mặc định.** Ví dụ tăng Hikari max sẽ tăng số queries đồng thời lên DB; nếu DB đã saturated, latency còn xấu hơn. Tăng HTTP connections khi remote đã 429/503 cũng làm tình trạng tệ hơn.

### 18.1. Retry, timeouts và circuit breaker

- Retry chỉ cho failures tạm thời, có giới hạn attempts, exponential backoff/jitter và deadline tổng.
- Không retry POST tạo payment/order nếu không có idempotency key và duplicate protection.
- Circuit breaker giúp tránh dồn requests lên một dependency đang lỗi; không tự sửa remote service.
- Bulkhead cô lập resource/concurrency theo dependency để tránh lỗi lan ra toàn gateway.
- Rate limiting/load shedding trả lỗi nhanh khi vượt capacity, thay vì để queue vô hạn và timeout hàng loạt.
- Cache/fallback chỉ khi dữ liệu stale/partial được business contract cho phép.

### 18.2. Khi nào scale out?

Scale application replicas khi CPU/threads của **chính app** bị nghẽn và downstream/DB còn headroom. Nếu bottleneck nằm tại DB hoặc dependency, thêm app replicas có thể **nhân** số Hikari connections và outbound RPS làm sự cố nặng hơn. Sizing phải xem toàn hệ thống, không chỉ một pod.

## 19. Quy trình incident 10 bước

1. **Xác định phạm vi:** toàn bộ routes hay một endpoint, mới xảy ra hay kéo dài; bản deploy/config nào vừa đổi?
2. **Số liệu client:** p95/p99, error, deadline, traffic mix, concurrency, geography; có proxy/CDN?
3. **Số liệu server:** `http.server.requests` theo URI template/status; CPU, GC, threads.
4. **MVC vs WebFlux:** xác minh actual runtime (Tomcat/Servlet hay Reactor Netty WebFlux), không đoán từ dependency `WebClient`.
5. **Các pools:** Tomcat busy workers, Hikari active/pending, HTTP client provider active/pending, executor queue.
6. **Downstream:** `http.client.requests`, remote p95/errors, remote CPU/DB saturation, TCP/TLS/DNS failures.
7. **Chụp evidence:** thread dumps/JFR/traces ở thời điểm đang chậm; tránh chỉ chụp sau khi sự cố đã hết.
8. **Xếp giả thuyết:** chọn tầng đầu tiên tạo queue/latency tăng, phân biệt gốc và hệ quả.
9. **Thay một yếu tố:** tối ưu query, giảm blocking, tạm giới hạn concurrency, sửa timeout hoặc rollback release; giữ workload đủ giống.
10. **Xác thực & ghi nhận:** so baseline, p99, error, throughput, saturation, chi phí và regression; ghi lại runbook/alert hữu ích.

Trong sự cố production, ưu tiên giảm tác động người dùng (giảm tải/rollback/rate limit) song song với thu thập evidence; không cố ý gây tải hoặc thay nhiều cấu hình cùng lúc chỉ để thử giả thuyết.

## 20. Trò chơi tình huống: chọn bằng chứng trước khi sửa

### Tình huống A: API MVC p99 5 giây, CPU 15%

- Tomcat busy workers đạt max.
- Thread dumps có nhiều `SocketInputStream.read` trong outbound HTTP.
- Client span tới inventory tăng từ 100 ms lên 4 s.

**Giả thuyết ưu tiên:** inventory/network chậm giữ Tomcat threads; worker saturation là hậu quả. Cần xem timeout, inventory health, retries và bulkhead trước khi tăng Tomcat max.

### Tình huống B: Hikari pending 40, SQL p95 2 giây

- Pool max=20, active=20.
- Queries có lock wait/slow SQL.
- Tăng pool thành 50 dự đoán có thể tăng lock contention.

**Ưu tiên:** query/transaction/DB locks, giữ connection ngắn, không tăng pool như bước đầu tiên.

### Tình huống C: WebFlux app CPU thấp nhưng /fast cũng chậm

- Reactor Netty thread dump thấy `Thread.sleep` và blocking JDBC.
- Mọi socket share vài event-loop threads.

**Ưu tiên:** bỏ blocking trên event loop, chuyển qua reactive driver hoặc offload với giới hạn, rồi load test lại.

### Tình huống D: Reactor Netty active connections=max và pending tăng

- HTTP remote p95 1,8s, pool acquisition timeout liên tục.
- Remote trả 429 vì quota.

**Ưu tiên:** giảm concurrency/rate, retries, hỏi capacity/quota của remote. Chỉ tăng pool khi remote có headroom và phép đo xác nhận.

### Tình huống E: CPU 100% với p95 tăng, pools còn trống

- JFR samples tập trung ở JSON serialization và một thuật toán tạo bảng lớn.

**Ưu tiên:** tối ưu hot path, kích thước response, caching, pagination và đo heap/GC. Tăng DB pool không giải quyết CPU-bound serialization.

### Tình huống F: một pod chậm, các pod còn lại bình thường

- Pod chậm có GC pauses và heap occupancy cao.
- Không thấy Hikari pending hay client latency khác biệt.

**Ưu tiên:** memory pressure, allocation hotspot, cgroup/quota, GC, traffic skew hoặc connection imbalance; tránh kết luận từ tổng metrics theo cluster làm che mất pod cá biệt.

## 21. Lỗi thường gặp khi phân tích

| Nhầm lẫn | Vì sao sai | Cách đúng |
| --- | --- | --- |
| CPU thấp nghĩa là server không nghẽn | Luồng có thể đang chờ I/O hoặc pool | Đo queue, pending và client latency |
| CPU cao nghĩa là code Java lỗi | Có thể do GC/serialization/load hợp lệ hoặc container throttling | CPU profile, quotas, GC metrics |
| Hikari active=max nghĩa pool thiếu | Không biết pending và acquisition latency | Kết hợp pending, SQL duration, DB capacity |
| Tomcat busy=max nghĩa tăng threads là xong | Worker có thể đang chờ remote | Thread dump và downstream span |
| WebFlux tự bảo đảm non-blocking | Blocking code vẫn có thể chạy trên event loop | Review blocking APIs/schedulers |
| Nhiều event-loop threads luôn nhanh hơn | More threads không sửa blocking/library latency | Remove/offload blocking và benchmark |
| HTTP client pool lớn sẽ luôn nhanh | Remote có thể quá tải, tạo 429/5xx | Căn theo remote budget và load test |
| `http.server.requests` đủ để tìm nguyên nhân | Chỉ cho end-to-end request timer | Thêm client/DB spans, pool metrics, profiler |
| Metrics meter chưa xuất hiện → giá trị 0 | Instrumentation có thể chưa bật hoặc chưa có sample | Xem Actuator names, dependencies/config |
| Chỉ chạy một request và đo p95 | Percentile một mẫu không ổn định | Warm-up, lấy nhiều samples, test concurrency |
| Gọi `sleep()` trong DB transaction không sao | Giữ connection/locks, gây pool starvation | Giữ transaction ngắn, không call remote trong transaction |
| Retry thêm giúp bớt timeout | Thường tăng tải và queue trong outage | Retry budget, backoff, idempotency |
| Tăng pool ở tất cả replicas độc lập | Tổng DB connections bị nhân theo số replicas | Tính aggregate capacity và quota |
| `/actuator/metrics` không phản hồi nghĩa Actuator lỗi | Tomcat workers có thể đều đang bận | Quan sát từ scraper/agent và thread dump |
| Có WebClient nên app là WebFlux | MVC vẫn có thể dùng WebClient | Xác nhận server runtime/classpath |
| Latency child spans cộng bằng parent | Spans có thể nested/parallel | Đo critical path, không double-count |

## 22. Bài tập tự kiểm tra

**Câu 1.** Một endpoint p99 tăng gấp 10, process CPU vẫn 10%. Nêu ít nhất bốn nơi cần kiểm tra trước khi tăng threads.

**Câu 2.** Vì sao hai requests giữ Hikari connection có thể làm 10 requests khác timeout dù Tomcat còn workers và DB không dùng CPU nhiều?

**Câu 3.** Trong MVC lab, `/api/worker` và `/api/db` đều có `Thread.sleep`. Vì sao hai endpoint gây nghẽn khác nhau?

**Câu 4.** Trong WebFlux lab, `Mono.fromCallable(Thread.sleep)` có bảo đảm non-blocking chỉ vì trả Mono không?

**Câu 5.** Khi dùng WebClient Reactor Netty, meter `reactor.netty.connection.provider.pending.connections` nói về tài nguyên nào? Có phải Hikari pool không?

**Câu 6.** Vì sao `RestClient.create()` tự phát có thể khiến `http.client.requests` không được instrument như injected Boot builder?

**Câu 7.** Tại sao đọc `hikaricp.connections.pending` sau khi tải dừng có thể bằng 0 dù vừa có pool exhaustion?

**Câu 8.** Spring Boot 3.3 cần cấu hình nào để Tomcat-specific metrics được đăng ký tự động?

**Câu 9.** Client span tới remote chậm nhưng remote server span nhanh. Những giai đoạn nào ở giữa cần kiểm tra?

**Câu 10.** Tại sao tăng Hikari max ở từng pod có thể làm DB chậm hơn khi scale replicas?

**Câu 11.** Little’s Law `L=λW` có được dùng để chốt maxConnections mà không đo p95, queue và remote capacity không?

**Câu 12.** Vì sao fire-and-forget load test hoặc một request đơn lẻ chưa đủ kết luận capacity?

**Câu 13.** Khi thread dump có trạng thái `WAITING`, điều đó có nghĩa thread đang chiếm CPU không?

**Câu 14.** Nếu downstream chậm gây MVC worker exhaustion, nên điều tra nguyên nhân trực tiếp ở đâu trước?

**Đáp án định hướng:**

1. Tomcat workers/queue, Hikari pending, outbound HTTP pool pending, downstream latency, locks, network hoặc GC.
2. Hai connections bị lease, requests khác phải chờ lấy connection, có acquisition timeout dù CPU rảnh.
3. `/worker` giữ Tomcat request thread; `/db` còn giữ Hikari JDBC connection, có thể gây pool starvation trước khi threads max.
4. Không. Khi được subscribe trên event loop, blocking callable vẫn chặn thread.
5. Chờ lease outbound HTTP connections của Reactor Netty, không phải JDBC/Hikari pool.
6. Boot instrumentation thường gắn qua auto-configured RestClient.Builder/customizers; tự tạo client có thể bỏ qua.
7. Pending là trạng thái tức thời; phải scrape trong lúc tải hoặc xem time-series/exception counters.
8. `server.tomcat.mbeanregistry.enabled=true`, với Actuator và Tomcat.
9. HTTP client pool acquisition, DNS, TCP connect, TLS, proxy, network, retries và observation gaps.
10. Pool mỗi pod nhân lên, có thể vượt DB connection limit hoặc tạo quá nhiều concurrent SQL/lock contention.
11. Không, chỉ là quan hệ average cùng boundary; cần test queue/tail/capacity.
12. Không đo concurrency/queue/tail latency đúng và không tái hiện production workload mix.
13. Không. WAITING/TIMED_WAITING có thể là sleep/park/chờ I/O; phải đo CPU samples và stack.
14. Remote service latency, outbound HTTP client timeouts/retries/connection pool; Tomcat busy là triệu chứng thứ cấp.

## 23. Checklist chẩn đoán production

- [ ] Đã ghi baseline request rate, p50/p95/p99, errors, traffic mix và CPU/GC.
- [ ] Biết app đang chạy MVC/Tomcat hay WebFlux/Reactor Netty thật sự.
- [ ] Có `http.server.requests` theo route template và `http.client.requests` theo dependency.
- [ ] Đã bật đúng Tomcat MBean registry nếu cần Tomcat metrics.
- [ ] Có Hikari/JDBC active, max, pending, acquire time và slow SQL evidence.
- [ ] Có HTTP client connection pool metrics và pending acquire time nếu dùng pooling.
- [ ] Có thread dump/JFR từ **lúc chậm**, không chỉ từ sau sự cố.
- [ ] Biết code blocking đang chạy ở đâu, đặc biệt trên event loops.
- [ ] Có downstream trace/latency/errors để tách gốc với triệu chứng.
- [ ] Xác định critical path trong fan-out, không cộng lặp nested spans.
- [ ] Timeout/connection acquire/retry budgets được giới hạn theo deadline.
- [ ] DB pool max và HTTP pool max được sizing với capacity tổng của downstream và số replicas.
- [ ] Có rate limit/bulkhead/circuit breaker phù hợp để chống cascading failure.
- [ ] Không tăng số threads/pool đồng loạt khi chưa kiểm thử so sánh A/B.
- [ ] Có kế hoạch bảo mật metrics endpoint và giới hạn tải trong test.
- [ ] Đã đo lại p95/p99, error, throughput, saturation sau khi sửa và ghi runbook.

## 24. Tài liệu tham khảo

- Spring Boot 3.3 — Metrics Actuator, JVM/System/MVC/WebFlux/HTTP-client/Tomcat/DataSource/Hikari: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot 3.3 — Actuator Endpoints: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — Observability/HTTP client instrumentation: https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html
- Spring Boot 3.3 — Calling REST Services: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
- Spring Boot 3.3 — Embedded web servers/Tomcat thread and connector config: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Reactor Netty — HTTP Client Reference, ConnectionProvider metrics: https://projectreactor.io/docs/netty/1.1.23/reference/index.html
- Reactor Netty — Current HTTP Client Reference, configuration and pool metrics (đối chiếu version): https://projectreactor.io/docs/netty/release/reference/http-client.html
- Project Reactor — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- HikariCP — Configuration and connectionTimeout: https://github.com/brettwooldridge/HikariCP
- Java 17 — jcmd diagnostic command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Java 17 — Java Flight Recorder runtime guide: https://docs.oracle.com/en/java/javase/17/jfapi/
- Micrometer — Meter concepts, timers and distributions: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- OpenTelemetry — Traces and spans/critical path observations: https://opentelemetry.io/docs/concepts/signals/traces/
