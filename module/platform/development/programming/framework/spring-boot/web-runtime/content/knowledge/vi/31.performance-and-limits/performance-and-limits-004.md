# Phối hợp thời gian chờ giữa máy khách, proxy, máy chủ và dịch vụ phía sau

> **Module:** Spring Boot – web-runtime → **Hiệu năng và giới hạn**. Bài học xây dựng cách phối hợp **timeouts** và **end-to-end deadlines** khi request đi từ browser hoặc API client qua reverse proxy/load balancer, tới Spring Boot MVC/Tomcat hay WebFlux/Netty, rồi gọi database và HTTP downstream. Ví dụ dùng **Java 17+, Spring Boot 3.3.x, Spring Framework 6.1.x**, NGINX và curl; tất cả thời lượng là số minh họa, cần hiệu chỉnh theo SLO và phép đo hệ thống thật.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **connect**, **TLS handshake**, **pool acquire**, **request send**, **read inactivity**, **async processing**, **keepalive idle**, **per-attempt request timeout** và **overall deadline**.
2. Xác định ai là người thực thi timeout: client, NGINX/ingress, Spring MVC/Tomcat, Spring WebFlux/Reactor Netty, HTTP client outbound, DB/driver hoặc downstream.
3. Giải thích đúng `proxy_read_timeout` của NGINX chỉ giới hạn khoảng giữa các lần đọc, `server.tomcat.connection-timeout` không giới hạn thời gian controller, và `spring.mvc.async.request-timeout` dành cho MVC asynchronous request.
4. Thiết kế time budget sao cho downstream call kết thúc trước khi caller bỏ cuộc, vẫn còn margin để trả error response.
5. Thiết lập một ví dụ `RestClient` với JDK HttpClient connect/request timeout, và biết cấu hình `WebClient` với Reactor Netty cùng `Mono.timeout`.
6. Phân biệt các HTTP status 408, 502, 503, 504 với NGINX access log `499` và client timeout không có HTTP response.
7. Hiểu vì sao **timeout không bảo đảm hủy công việc** của server, DB transaction hoặc downstream.
8. Kết hợp retry budget, concurrency, connection pool, cancellation, streaming/SSE và observability.
9. Chạy và kiểm chứng một ứng dụng Spring Boot Java 17+ có downstream giả lập nhanh/chậm/lỗi; xác định error owner qua curl/NGINX logs.

## 2. Request đi qua nhiều tầng

~~~text
Browser / Mobile / API Client
       |
       | HTTP client overall timeout
       v
CDN / API Gateway / NGINX
       |
       | connect timeout tới upstream
       | read/send inactivity timeout
       | total request deadline nếu gateway hỗ trợ riêng
       v
Spring Boot HTTP server
       | Tomcat / Reactor Netty
       | request parse, queue, security, controller
       | async processing deadline (nếu async)
       v
Application service
       |
       | outbound HTTP RestClient / WebClient
       | connection pool -> DNS -> TCP -> TLS
       | write request -> read response
       v
Downstream REST API / Database
       |
       | query/operation/transaction timeout
       v
Response trở lại qua mỗi hop
~~~

Timeout là chính sách của **từng tầng**. Không có một property Spring Boot tự động khiến mọi HTTP client, reverse proxy, DB query và browser dùng chung deadline.

Ví dụ xung đột:

- Browser chờ 2 giây, NGINX đợi 30 giây, app chờ downstream 60 giây: user đã bỏ cuộc nhưng thread/socket vẫn có thể bị giữ.
- NGINX chờ 1 giây không có upstream bytes, app đặt timeout 3 giây: gateway có thể phát 504 **trước** khi app kịp trả error JSON.
- Outbound client timeout 1 giây rồi retry 5 lần, thêm backoff: tổng processing time vượt API client timeout 3 giây.
- Upstream streaming gửi một chunk mỗi 1 giây, NGINX `proxy_read_timeout=2s`: stream có thể sống lâu hơn 2 giây vì timer là **idle between reads**, không phải total response duration.
- Team đặt `server.tomcat.connection-timeout=2s` để giới hạn controller 2s: property này chủ yếu liên quan phase **nhận request line** sau khi accept connection, không giải quyết business processing.

**Mục tiêu:** thiết kế một budget toàn tuyến và chọn timeout **đúng loại**, không chỉ đặt mọi biến tên “timeout” về cùng con số.

## 3. Từ vựng timeout và phạm vi chính xác

| Timeout | Đo khoảng nào | Ai thường điều khiển | Không phải |
|---|---|---|---|
| DNS resolution | Phân giải hostname | Client resolver/OS/runtime | Không luôn nằm trong TCP connect timeout |
| TCP connect | Tạo kết nối mới tới peer | JDK HttpClient, Reactor Netty, proxy | Không giới hạn cả body response |
| TLS handshake | Chờ handshake + certificate validation | TLS connector/HTTP client | Không thay application deadline |
| Pool acquire | Chờ lấy connection đang rảnh | HTTP connection pool, JDBC pool | Không tự gồm connect/read time |
| Request-header receive | Chờ phía client gửi đủ headers | NGINX/Tomcat | Không giới hạn controller |
| Request-body receive | Thời gian hoặc khoảng ngừng đọc upload | NGINX/HTTP server | Không nhất thiết là total upload time |
| Proxy request send | Các lần proxy ghi tới upstream | NGINX `proxy_send_timeout` | Không phải whole request operation |
| Upstream read inactivity | Khoảng giữa upstream reads | NGINX `proxy_read_timeout` | Không phải total response deadline |
| Client response/request timeout | Timeout theo HTTP implementation | JDK/Jackson connector/Netty | Không tự bao gồm multi-attempt retry |
| MVC async request | Lifecycle của async Servlet request | `spring.mvc.async.request-timeout` | Không tự áp cho synchronous @GetMapping |
| Keepalive idle | Kết nối rảnh giữa các requests | `server.tomcat.keep-alive-timeout` | Không phải business handler duration |
| End-to-end deadline | Tổng thời gian xử lý operation từ caller | Client/gateway/app policy | Khác idle, connect và keepalive |
| DB query/transaction | Một query hoặc transaction | Driver/DB/transaction manager | Không thay HTTP client deadline |

Cùng từ `readTimeout` chưa chắc cùng semantics. Trong Spring Framework 6.1, `JdkClientHttpRequestFactory.setReadTimeout(Duration)` đặt timeout thông qua JDK `HttpRequest.Builder.timeout(Duration)` cho request; một `URLConnection.setReadTimeout` thường liên quan timeout chờ network reads. **Luôn đọc đúng tài liệu connector/version** trước khi quy đổi thời gian.

Ba câu hỏi cần hỏi mỗi khi đọc một timeout setting: **(1) timer bắt đầu khi nào; (2) điều gì reset nó; (3) khi hết hạn, ai đóng socket/cancel task hay tạo HTTP error?**

## 4. Thiết kế một ngân sách thời gian toàn tuyến

Giả sử caller yêu cầu một REST JSON response trong tối đa **3.500 ms** tính từ lúc bắt đầu:

| Thành phần | Mức ví dụ | Vai trò |
|---|---:|---|
| Browser/API client overall | 3.500 ms | User-facing upper bound |
| Gateway có **hard total request deadline** nếu có | 3.200 ms | Thất bại trước client để còn hiển thị HTTP error |
| Spring application overall budget | 2.800 ms | Còn margin serialize/error/egress |
| Outbound call operation budget | 2.100 ms | Dependency bị cắt sớm |
| Validation, queue, serialization, network margin | Khoảng 400–700 ms tùy route | Dự phòng tail latency và error delivery |

**Đây là time budget về mặt thiết kế, không phải cấu hình NGINX 3.2s tự sinh ra khi bạn đặt `proxy_read_timeout=3.2s`.** NGINX directive này đo inactivity, không đo tổng. Nếu gateway không hỗ trợ hard deadline, application phải có policy tương ứng ở code/orchestration; đồng thời không dùng một Boot property tưởng tượng cho toàn synchronous MVC handler.

~~~text
t = 0 ms                                      3500 ms
Client:  |----------------------------------------|
Gateway: |-----------------------------------|     3200, nếu có hard deadline
App:     |------------------------------|          2800, logical deadline
B call:  |---------------------|                   2100, maximum operation
                          ^ app còn thời gian xử lý và trả lỗi
~~~

### Tính theo critical path

Một workflow gọi service B rồi C **tuần tự** có thời gian gần bằng tổng hai calls + overhead. Một workflow gọi B/C **song song** có critical path gần bằng nhánh lâu nhất + merge/serialization, nhưng còn có queue, scheduler, pool contention và cancellation.

Ví dụ tuần tự:

~~~text
Read/auth/local work   <= 200ms
B attempt              <= 850ms
C attempt              <= 900ms
Serialize+send reserve <= 250ms
--------------------------------
Plan                  ~2.200ms
~~~

Nếu B đã dùng hết 850ms, C phải nhận **remaining time** thay vì cứ được một timeout mới đầy đủ, khiến tổng vượt caller deadline. Chừa thời gian cho public error response là một yêu cầu thực tế, không chỉ phép cộng toán học.

### Một biểu thức để review

~~~text
T_total ≈ T_queue + T_auth + Σ T_attempts
        + Σ T_backoffs + T_DB + T_local
        + T_serialize + T_network_egress

Yêu cầu: T_total <= remaining caller budget
~~~

Số hạng nào chạy song song thì phải tính theo dependency graph/critical path chứ không cộng mù quáng. Jitter/GC pause/OS scheduling có thể khiến latency vượt kỳ vọng; timeout không phải SLA tuyệt đối từng mili-giây.

## 5. NGINX: connect, send và read khác nhau

Ví dụ một NGINX server thử nghiệm trước Spring Boot ở cổng 8080:

~~~nginx
server {
    listen 8081;

    location /api/ {
        proxy_pass http://127.0.0.1:8080;

        proxy_connect_timeout 500ms;
        proxy_send_timeout 2s;
        proxy_read_timeout 2s;

        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;
    }
}
~~~

Cấu hình này thuộc **NGINX**, không phải `application.properties`. Trong một môi trường Kubernetes Ingress, phải dùng annotations/resources đúng với ingress controller/version, không giả định raw NGINX config có thể dán thẳng.

- `proxy_connect_timeout 500ms` giới hạn kết nối mới từ NGINX tới upstream HTTP server.
- `proxy_send_timeout 2s` giới hạn **khoảng giữa các lần ghi request** từ proxy sang upstream; không phải tổng thời gian gửi request.
- `proxy_read_timeout 2s` giới hạn **khoảng giữa các lần đọc response** từ upstream; không phải thời gian từ request start đến response complete.
- `proxy_http_version 1.1` chỉ chọn version ở hop proxy→upstream; không tạo WebSocket hoặc HTTP/2 end-to-end.
- `X-Request-ID` có thể dùng tương quan logs nếu được policy cho phép; server cần xử lý request ID từ trusted hop, tránh client tự tạo giá trị tùy ý dùng làm bằng chứng.

### Nếu upstream đã gửi header rồi mới treo

Một upstream có thể gửi `HTTP/1.1 200 OK` và một phần body trước khi im lặng quá 2s. Lúc này proxy **có thể đã commit response** cho browser; khi timeout, không thể luôn đổi thành 504 JSON. Client có thể thấy truncated response, EOF hoặc JSON parse failure. Vì thế test timeout **trước first byte** và **giữa streaming chunks** là hai case riêng.

### Client-facing timeout của NGINX

Các directives `client_header_timeout`, `client_body_timeout`, `send_timeout` và `keepalive_timeout` thuộc các pha khác:

- `client_header_timeout`: chờ nhận đầy đủ request header, có thể phát 408 khi hết hạn.
- `client_body_timeout`: chờ giữa các lần nhận upload body.
- `send_timeout`: chờ khi gửi response về client theo semantics NGINX.
- `keepalive_timeout`: connection rảnh chờ request tiếp theo.

Một large upload có dữ liệu liên tục có thể kéo dài hơn timeout per-read; muốn giới hạn total upload time phải có chính sách riêng. Đặt 2s cho REST JSON không chứng minh nó phù hợp SSE, video, file upload hoặc long polling.

## 6. Spring Boot MVC/Tomcat: không nhầm timeout của connector

Một số property Boot 3.3:

~~~properties
server.port=8080

# Tomcat chờ request URI line sau khi accept connection.
server.tomcat.connection-timeout=5s

# Tomcat giữ kết nối rảnh giữa các HTTP requests.
server.tomcat.keep-alive-timeout=15s

# Spring MVC asynchronous request processing.
spring.mvc.async.request-timeout=2800ms
~~~

**Không** suy ra controller đồng bộ có deadline 5s hoặc 2.8s từ ba dòng trên. Ví dụ:

~~~java
// Chỉ là method minh họa trong một @RestController MVC.
@GetMapping("/slow")
public String slow() throws InterruptedException {
    Thread.sleep(10000);
    return "done";
}
~~~

Controller này có thể chiếm Servlet worker thread 10 giây bất kể `server.tomcat.connection-timeout=5s`. Nếu client/nginx bỏ cuộc ở giây 3, chính method có thể vẫn tiếp tục sleep cho đến khi xong hoặc gặp một cơ chế hủy thực sự khác.

### MVC async request timeout

Nếu controller trả `Callable`, `DeferredResult` hay một dạng async response được MVC hỗ trợ, `spring.mvc.async.request-timeout` hoặc timeout per-request có thể ảnh hưởng quá trình **chờ response async**:

~~~java
// Snippet trong MVC controller:
@GetMapping("/async")
public Callable<String> work() {
    return () -> {
        Thread.sleep(3000);
        return "done";
    };
}
~~~

Spring MVC async timeout không bảo đảm Java computation/DB query bên dưới được giết tức thì. Với `DeferredResult`, hãy xử lý `onTimeout`/`onCompletion` cùng cancel logic/executor sizing. Đừng tạo vô hạn blocking tasks trong async executor chỉ để tránh chiếm Servlet request thread.

### WebFlux server

Nếu dùng Spring WebFlux/Reactor Netty, các cài đặt như `server.netty.idle-timeout` áp cho network/channel idle theo connector, không phải `spring.mvc.async.request-timeout`. Có thể dùng Reactor `timeout(Duration)` cho reactive pipeline theo route, nhưng phải test cancellation, error signaling và response commit. Không cấu hình Tomcat rồi nghĩ nó có hiệu lực trên Netty.

## 7. Spring RestClient: timeout của outbound request

Spring Framework 6.1+ có `RestClient` fluent blocking HTTP client. Có thể chọn JDK HttpClient làm transport:

~~~java
// Snippet trong @Configuration:
HttpClient javaHttp = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(250))
        .build();

JdkClientHttpRequestFactory requestFactory =
        new JdkClientHttpRequestFactory(javaHttp);

requestFactory.setReadTimeout(Duration.ofMillis(700));

RestClient client = RestClient.builder()
        .baseUrl("https://partner.example.test")
        .requestFactory(requestFactory)
        .build();
~~~

- `HttpClient.connectTimeout` ảnh hưởng **connection establishment** mới; không áp tương tự lên một connection đã reuse.
- `JdkClientHttpRequestFactory.setReadTimeout(Duration)` trong Spring 6.1 gắn với JDK `HttpRequest.Builder.timeout(Duration)`, timeout của request; không nên diễn giải như interval read timeout của NGINX.
- DNS/TLS/pool acquire có thể mang semantics khác theo connector.
- Nếu request có retries, một attempt timeout 700ms không tự làm cả 3 attempts hoàn thành dưới 700ms.

Thư viện HTTP client khác như Apache HttpClient 5, Reactor Netty hoặc JDK URLConnection có phương thức timeout khác. Việc sao chép cùng số 700ms giữa clients không đủ chứng minh hành vi tương đương.

### Khi dùng WebClient và Reactor Netty

~~~java
// Snippet cần Reactor Netty, Spring WebClient connector imports.
HttpClient netty = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 250)
        .responseTimeout(Duration.ofMillis(700));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(netty))
        .build();
~~~

`responseTimeout` theo ngữ nghĩa Reactor Netty HTTP client, không tự là deadline của một workflow gồm retry/backoff/DB processing. Có thể thêm:

~~~java
// Snippet minh họa, OrderDto và id do ứng dụng định nghĩa.
Mono<OrderDto> operation = webClient.get()
        .uri("/orders/{id}", id)
        .retrieve()
        .bodyToMono(OrderDto.class)
        .timeout(Duration.ofMillis(900));
~~~

`Mono.timeout` tính từ subscription và timeout reactive publisher nếu không hoàn thành đúng hạn. Khi lỗi, subscription có thể bị cancel; nhưng downstream service **không được bảo đảm** dừng processing/transaction. Với DataBuffer streaming và pooled memory, cancellation còn cần cleanup theo API contract.

## 8. Ví dụ chạy được: Spring Boot 3.3 Java 17 và fake downstream

Mục đích lab: tạo **hai HTTP hops** trong một process nhưng có outbound HTTP request thật. HTTP server vẫn là Servlet MVC/Tomcat, không cần WebFlux:

~~~text
curl GET /api/relay/fast|slow|error
       |
       v
Spring MVC ProxyController A :8080
       |
       | RestClient (JDK HttpClient)
       | connect 250ms, request 700ms
       v
FakeDownstream B :8080
       |
       +-- delay 100ms -> JSON 200
       +-- delay 1200ms -> chậm hơn timeout A
       +-- error -> 503 + internal marker
~~~

Đặt fake B trong cùng process chỉ để lab self-contained. Trên production nó phải là service khác với URL/cert/network policy hợp lệ. Bị timeout ở A **không** có nghĩa `Thread.sleep` của B đã được interrupt.

### 8.1. Cấu trúc

~~~text
timeout-budget-demo/
  pom.xml
  src/main/java/example/timeout/TimeoutBudgetDemoApplication.java
  src/main/resources/application.properties
~~~

### 8.2. Maven pom.xml

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
    <groupId>example</groupId>
    <artifactId>timeout-budget-demo</artifactId>
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

Không có database, WebSocket hoặc messaging broker. Spring Boot BOM quản lý versions cho Spring Web 6.1 và Tomcat phù hợp. `RestClient` có sẵn trong Spring Web của starter-web; Spring Boot cấu hình `RestClient.Builder` để ứng dụng có thể inject.

### 8.3. application.properties

~~~properties
server.port=8080

# Không phải controller total timeout:
server.tomcat.connection-timeout=5s
server.tomcat.keep-alive-timeout=15s

# Hạn chế default Boot errors vô tình lộ stacktrace:
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-exception=false
~~~

### 8.4. Một file Java đầy đủ

Tạo `src/main/java/example/timeout/TimeoutBudgetDemoApplication.java`:

~~~java
package example.timeout;

import java.net.SocketTimeoutException;
import java.net.http.HttpClient;
import java.net.http.HttpTimeoutException;
import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@SpringBootApplication
public class TimeoutBudgetDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TimeoutBudgetDemoApplication.class,
                args);
    }

    @Configuration
    static class ClientConfig {

        @Bean
        RestClient destinationClient(RestClient.Builder builder) {
            HttpClient jdkClient = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofMillis(250))
                    .build();

            JdkClientHttpRequestFactory factory =
                    new JdkClientHttpRequestFactory(jdkClient);

            // Trên JDK client, mapping request timeout:
            factory.setReadTimeout(Duration.ofMillis(700));

            return builder
                    .baseUrl("http://localhost:8080")
                    .requestFactory(factory)
                    .build();
        }
    }

    @RestController
    static class FakeDestination {

        @GetMapping("/target/delay")
        public Map<String, Object> delay(
                @RequestParam(defaultValue = "0") int ms)
                throws InterruptedException {

            if (ms < 0 || ms > 2000) {
                throw new IllegalArgumentException("Invalid delay");
            }

            Thread.sleep(ms);
            return Map.of("source", "downstream",
                          "delayMs", ms);
        }

        @GetMapping(value = "/target/error",
                    produces = MediaType.TEXT_PLAIN_VALUE)
        public ResponseEntity<String> error() {
            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("INTERNAL_DB_HOST=db.private.lan");
        }
    }

    @RestController
    static class ApiController {
        private final RestClient client;

        ApiController(RestClient destinationClient) {
            this.client = destinationClient;
        }

        @GetMapping("/api/relay/{scenario}")
        public ResponseEntity<?> relay(
                @PathVariable String scenario) {

            String uri = switch (scenario) {
                case "fast" -> "/target/delay?ms=100";
                case "slow" -> "/target/delay?ms=1200";
                case "error" -> "/target/error";
                default -> null;
            };

            if (uri == null) {
                return problem(HttpStatus.BAD_REQUEST,
                        "Kịch bản thử nghiệm không hợp lệ.");
            }

            try {
                Map<?, ?> data = client.get()
                        .uri(uri)
                        .retrieve()
                        .onStatus(HttpStatusCode::isError,
                            (request, response) -> {
                                // Không copy upstream error body
                                // tới client.
                                throw new UpstreamStatus(
                                    response.getStatusCode().value());
                            })
                        .body(Map.class);

                if (data == null) {
                    return problem(HttpStatus.BAD_GATEWAY,
                            "Phản hồi dịch vụ đích không hợp lệ.");
                }

                return ResponseEntity.ok(Map.of("result", data));

            } catch (UpstreamStatus ex) {
                return problem(
                    ex.code == 503
                        ? HttpStatus.SERVICE_UNAVAILABLE
                        : HttpStatus.BAD_GATEWAY,
                    "Dịch vụ đích hiện không sẵn sàng.");

            } catch (ResourceAccessException ex) {
                return isTimeout(ex)
                    ? problem(HttpStatus.GATEWAY_TIMEOUT,
                        "Dịch vụ đích phản hồi quá chậm.")
                    : problem(HttpStatus.BAD_GATEWAY,
                        "Không thể kết nối dịch vụ đích.");

            } catch (RestClientException ex) {
                return problem(HttpStatus.BAD_GATEWAY,
                        "Không xử lý được phản hồi dịch vụ đích.");
            }
        }

        private static boolean isTimeout(Throwable ex) {
            for (Throwable cause = ex; cause != null;
                    cause = cause.getCause()) {
                if (cause instanceof HttpTimeoutException
                        || cause instanceof SocketTimeoutException) {
                    return true;
                }
            }
            return false;
        }

        private static ResponseEntity<ProblemDetail> problem(
                HttpStatus status, String detail) {
            ProblemDetail body =
                    ProblemDetail.forStatusAndDetail(status, detail);
            body.setTitle("Lỗi gọi dịch vụ đích");

            return ResponseEntity.status(status)
                    .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                    .cacheControl(CacheControl.noStore())
                    .body(body);
        }

        private static final class UpstreamStatus
                extends RuntimeException {
            final int code;

            UpstreamStatus(int code) {
                super("upstream status");
                this.code = code;
            }
        }
    }
}
~~~

### 8.5. Tại sao ví dụ đúng trọng tâm?

- `/target/delay` giả lập service B với response time có kiểm soát.
- `/api/relay` là service A thực hiện **một outbound HTTP call** qua RestClient, không chỉ gọi method cùng class.
- `connectTimeout(250ms)` không liên quan đến Tomcat controller 250ms; nó điều khiển thiết lập TCP connection tới B.
- `factory.setReadTimeout(700ms)` qua JDK client là timeout của một HTTP request; response B sau 1.200ms thường bị A từ chối.
- `onStatus` ném exception chỉ chứa status khi B trả lỗi; không đọc/log/echo nội dung `INTERNAL_DB_HOST` cho public client. Trong hệ production, error body lớn có thể ảnh hưởng connection reuse; cần đọc contract HTTP client và đặt size/overall limits.
- `ResourceAccessException` có thể bọc timeout hoặc lỗi connection khác. Mã tìm `HttpTimeoutException` và `SocketTimeoutException` trong cause chain, nhưng những HTTP client khác có kiểu exception khác; thực tế phải log sanitized failure category.
- Public errors dùng `ProblemDetail` và `Cache-Control: no-store`, không đưa raw exception message ra response.
- Demo **chưa áp hard total app deadline** cho mọi controller route, chỉ thực thi outbound request timeout 700ms; đây là phân biệt cần chủ động giữ, không tuyên bố quá khả năng của ví dụ.

**Giới hạn của mô phỏng:** downstream Thread.sleep vẫn có thể hoàn tất sau khi caller bị timeout. Trong production muốn ngăn orphaned work cần deadline/cancellation protocol và idempotency cho mutations.

### 8.6. Chạy trên máy có Java 17 và Maven

Trong thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Terminal khác:

~~~bash
curl -i --max-time 3 http://localhost:8080/api/relay/fast
curl -i --max-time 3 http://localhost:8080/api/relay/slow
curl -i --max-time 3 http://localhost:8080/api/relay/error
curl -i --max-time 3 http://localhost:8080/api/relay/unknown
~~~

Dự kiến (có thể có warmup/OS jitter trên máy quá tải):

| URL | Trạng thái | Lý do |
|---|---:|---|
| `/api/relay/fast` | 200 | B trả trong ~100ms < 700ms |
| `/api/relay/slow` | 504 | B chờ 1.200ms > request timeout 700ms |
| `/api/relay/error` | 503 | B trả 503 và app map lỗi công khai |
| `/api/relay/unknown` | 400 | Chỉ cho phép scenarios đã khai báo |

Body 200 minh họa, không hứa thứ tự JSON keys:

~~~json
{
  "result": {
    "source": "downstream",
    "delayMs": 100
  }
}
~~~

Body 504 minh họa:

~~~json
{
  "type": "about:blank",
  "title": "Lỗi gọi dịch vụ đích",
  "status": 504,
  "detail": "Dịch vụ đích phản hồi quá chậm."
}
~~~

Nếu test slow bất ngờ thất bại vì environment rất chậm ngay cả trong fast path, kiểm app đã startup ổn, CPU contention, JVM warmup và cổng localhost rồi chạy lại. Không thay 700ms bằng timeout vô hạn để biến test thành “pass”.

### 8.7. Client timeout **trước** app timeout

~~~bash
curl -i --max-time 0.3 http://localhost:8080/api/relay/slow
~~~

Khi curl chỉ chờ 300ms, nó có thể kết thúc với **exit code 28** trước khi A kịp trả HTTP 504 sau outbound timeout 700ms. Client không nhận HTTP status 504 trong case đó; backend/outbound work vẫn có thể tồn tại.

Cần phân biệt một lỗi **do caller tự abort** với một response HTTP 504 **được application/gateway thực sự trả**. Để thấy 504 của app, dùng curl overall 3 giây lớn hơn outbound timeout.

### 8.8. Test qua NGINX nếu đã có proxy

Dùng cấu hình thử nghiệm ở mục 5, proxy từ port 8081 sang app 8080:

~~~bash
curl -i --max-time 3 http://localhost:8081/api/relay/fast
curl -i --max-time 3 http://localhost:8081/api/relay/slow
~~~

Với `proxy_read_timeout 2s`, app 504 ở khoảng 700ms thường được NGINX forward; đây là **504 do Spring tạo**. Nếu một controller trực tiếp không gửi upstream response bytes trong hơn 2s, NGINX có thể tạo **504 của NGINX** khi upstream còn chạy; NGINX logs là nguồn giúp phân biệt.

## 9. Timeout trong các retry attempts

Một outbound HTTP operation có thể có nhiều lần thử:

~~~text
attempt 1: timeout tối đa 800ms
backoff:                 200ms
attempt 2: timeout tối đa 800ms
app overhead:            150ms
--------------------------------
tổng xấp xỉ:           1950ms
~~~

Nếu chỉ có `per-attempt timeout=800ms` nhưng retry 10 lần, tổng operation có thể vượt outer deadline hàng giây. Cần:

1. **Per-attempt timeout:** chặn mỗi HTTP request quá lâu.
2. **Overall operation deadline:** chặn cả retry sequence + backoff + local processing.
3. **Retry budget:** số attempts/backoff và cost phải nằm trong remaining time.
4. **Idempotency:** không retry mutations tùy tiện; timeout có thể xảy ra **sau khi B đã commit**.

### Reactor operator order minh họa

~~~java
// Snippet, call và isRetryable do ứng dụng định nghĩa:
Mono<ResultDto> bounded = call
    .timeout(Duration.ofMillis(700))
    .retryWhen(Retry.backoff(1, Duration.ofMillis(100))
        .filter(this::isRetryable))
    .timeout(Duration.ofMillis(1800));
~~~

Ở đây inner timeout có thể áp cho mỗi lần resubscribe (mỗi attempt), outer timeout bao phủ toàn retry/backoff sequence. Cần import Reactor Retry và định nghĩa ResultDto/call/isRetryable; đây không phải file Java độc lập. Với response streaming hoặc side effects, retry semantics còn phức tạp hơn; phải test số attempts thực.

Đừng cho cả gateway, service mesh và app **cùng retry** vô hạn, vì 3 retries ở hai tầng có thể khiến số downstream calls bị nhân. Retry 400/401/403, TLS certificate invalid hoặc oversized body thường không hợp lý; 429/503 có thể retry có chọn lọc với `Retry-After` đáng tin, jitter và deadline còn lại.

## 10. Remaining-time budget và deadline propagation

Cần giảm thời gian cho downstream theo những gì đã dùng:

~~~text
App budget:                       2800ms
Already elapsed:                   500ms
Remaining:                        2300ms
Reserve for serialize/network:     300ms
Max B operation:                  2000ms
~~~

Một helper Java minh họa monotonic time:

~~~java
// Snippet đặt trong class hợp lệ, không phải Java file độc lập.
record Deadline(long expiresAtNanos) {
    static Deadline after(Duration limit) {
        return new Deadline(System.nanoTime()
                + limit.toNanos());
    }

    Duration remaining() {
        return Duration.ofNanos(Math.max(0L,
                expiresAtNanos - System.nanoTime()));
    }
}
~~~

`System.nanoTime()` dùng để đo elapsed time **trong cùng process**, không phải UTC epoch để gửi thẳng giữa machines. Với deadline ngắn và duration hợp lệ, cách tính này minh họa ý tưởng; production cần xử lý validation/overflow và lifecycle.

~~~java
Duration budget = deadline.remaining()
        .minus(Duration.ofMillis(300));

if (budget.isZero() || budget.isNegative()) {
    throw new TimeoutException("Budget exhausted");
}

Duration attempt = budget.compareTo(
        Duration.ofMillis(700)) < 0
        ? budget : Duration.ofMillis(700);
~~~

Cần dùng `attempt` vào actual HTTP client request/connector config thay vì chỉ tính rồi bỏ đó. Nếu có nhiều outbound operations, mỗi bước phải tính lại remaining budget, không reset. Với clients không hỗ trợ per-request dynamic timeout, có thể chọn request factory khác hoặc toàn-operation cancellation control.

### Truyền deadline qua HTTP

Có thể tự định nghĩa header nội bộ:

~~~http
X-Request-Timeout-Ms: 1900
X-Request-ID: req-842f...
~~~

Đây là **custom contract**, không phải một header Spring Boot/NGINX tự thực thi. Định nghĩa rõ unit, range, trusted caller và clamp vào server-side max. Không cho public client gửi giá trị cực lớn để biến server thành vô hạn timeout. Nếu dùng absolute timestamps, xử lý clock skew; trong cùng JVM nên dùng monotonic timers. Distributed tracing propagation giúp quan sát đường đi nhưng **không tự bật deadline enforcement**.

Một call B→C phải tiếp tục truyền **remaining budget**, không copy nguyên budget mà A đã giao lúc đầu.

## 11. Browser deadline qua AbortController

Một frontend JavaScript có thể dùng:

~~~javascript
async function loadReport() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 3500);

  try {
    const response = await fetch("/api/report", {
      method: "GET",
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error("HTTP " + response.status);
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}
~~~

Khi timer kích hoạt, fetch có thể reject với `AbortError`. Browser có thể hỗ trợ `AbortSignal.timeout(3500)` trong những môi trường mới hơn. Việc abort ở browser **không đồng nghĩa** server rollback DB transaction hoặc downstream task đã bị cancel.

Với `POST /payments`, caller timeout có thể xảy ra **sau khi server commit**. Client không nên gửi lại POST cùng dữ liệu vô điều kiện; cần idempotency key và status reconciliation. Deadline là hạn mức chờ, không phải bằng chứng không có side effect.

## 12. Cancellation không tự chảy xuyên qua từng hop

Một chuỗi có thể diễn ra:

1. Client abort ở t=2s.
2. NGINX thấy client đóng connection, access log ghi 499 nếu đi qua NGINX.
3. Servlet controller tiếp tục đợi `RestClient`.
4. HTTP client A→B có thể bị timeout/cancel, nhưng B vẫn xử lý request.
5. B có thể đã ghi DB hoặc tạo job.
6. Khi A cố trả response, socket phía client đã đóng: broken pipe/reset có thể xuất hiện.

### MVC synchronous

Synchronous controller gọi blocking SDK không được bảo đảm bị interrupt khi client disconnect. Cần bounded outbound timeouts, database query timeouts, bounded thread pools và xử lý task cancellation nếu API hỗ trợ. Tự tạo `CompletableFuture` mà không quản lý executor/cancel có thể làm tình hình xấu hơn.

### MVC async

`DeferredResult`/`Callable` có async timeout lifecycle riêng. `DeferredResult.onTimeout`/`onCompletion` có thể dùng để cleanup, nhưng phải đảm bảo task thực sự có cơ chế cancel/interruption phù hợp. Một async timeout response không đồng nghĩa kill thread/DB query.

### WebFlux/reactive

`Mono.timeout` thường dẫn tới cancellation signal trên reactive subscription, có thể làm connectors đóng/dispose response resources. Nhưng nếu operator gọi blocking code hoặc downstream không hiểu cancellation, công việc vẫn có thể tiếp tục. Với pooled `DataBuffer`, viết pipeline đúng ownership/release/discard theo APIs. Không tuyên bố “reactive luôn dừng công việc ngay tức thì”.

### Database/transactions

Driver statement query timeout, transaction timeout và DB server limit không thay HTTP deadline. B có thể commit trước khi A mất response; retry cần idempotency/transactional reconciliation. Việc cancel một query có thể mất thời gian rollback hoặc cleanup connections.

## 13. Connection pool và thời gian chờ trong hàng đợi

Một HTTP client có connection pool giới hạn. Khi pool đầy, request mới có thể chờ **pending acquire** trước khi TCP connect/read. Nếu bạn chỉ đặt responseTimeout 700ms nhưng request chờ connection 2s, toàn operation có thể vượt budget nếu không có hard total deadline.

Tương tự HikariCP có `connectionTimeout` cho việc lấy DB connection; nó không bằng query execution timeout. Một lệnh query timeout 1s không ngăn DB pool acquisition đã chờ 3s trước đó.

Khi throughput tăng, gần đúng Little's Law:

~~~text
L = arrival_rate × average_time_in_system

100 requests/s × 10 seconds ≈ 1000 in-flight requests
~~~

Đây là phép tính xấp xỉ khi điều kiện ổn định, không phải con số dự báo cho mọi hệ. Độ trễ chờ đợi tăng sẽ làm in-flight requests tăng, gây thread exhaustion, retries và timeout storms.

**Không tăng Tomcat threads và HTTP timeouts như phản xạ đầu tiên.** Trước hết xem worker pool, outgoing connection pool, DB pool, queuing, GC, CPU, slow downstream và retries. Bổ sung bulkhead/concurrency limits, circuit breaker và load shedding nếu phù hợp.

## 14. HTTP 408, 499, 502, 503 và 504 khác nhau

| Dấu hiệu | Thành phần có thể phát | Ý nghĩa phổ biến |
|---|---|---|
| `408 Request Timeout` | Server/proxy nhận request | Client chưa gửi đủ request đúng hạn; không đồng nghĩa downstream chậm |
| `499` | **NGINX access log** | Client đóng connection trước khi NGINX trả response; không phải chuẩn HTTP status gửi cho client |
| `502 Bad Gateway` | Proxy/app làm gateway | Không có valid upstream response, connection reset, protocol error hoặc lỗi giao tiếp tùy config |
| `503 Service Unavailable` | App/proxy | Dịch vụ tạm quá tải/không khả dụng, dependency unavailable theo contract |
| `504 Gateway Timeout` | Proxy hoặc app làm gateway | Upstream không phản hồi đúng timeout policy; cần xác định owner |
| curl `exit code 28` | Caller dùng curl | Curl tự hết hạn; có thể **không có HTTP status** |
| Browser `AbortError` | Browser/JS | Fetch bị abort; backend có thể vẫn đang chạy |

Nếu Spring chủ động map outbound JDK timeout thành 504, NGINX chỉ forward 504 từ Spring. Nếu NGINX tạo 504 vì `proxy_read_timeout` trước khi Spring trả headers, body có thể là HTML do NGINX tạo, không phải ProblemDetail của app. Nếu client abort sớm, có thể không thấy response HTTP. Cần correlation ID và logs/traces ở tất cả hops.

HTTP `408` thường liên quan thời gian **nhận request từ client**, khác `504` khi gateway **chờ upstream**. Không dùng một catch-all “mọi timeout → HTTP 500” khi có semantics chính xác hơn.

## 15. Error contract an toàn cho timeout

Một error do Spring app sinh ra có thể là:

~~~http
HTTP/1.1 504 Gateway Timeout
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Dịch vụ tạm thời chậm",
  "status": 504,
  "detail": "Không nhận được phản hồi kịp thời."
}
~~~

Đây là JSON **minh họa** do application tạo, không phải body mặc định của NGINX. Error nội bộ không nên expose raw stack trace, hostname, database URL, access token hay exception message. Với service-to-service authentication failure, upstream 401/403 không nhất thiết là 401/403 của public caller; cần map theo API contract.

Nếu streaming body đã bắt đầu được gửi, response có thể **đã commit**; khi timeout không phải lúc nào còn cơ hội đổi HTTP status sang 504 hoặc gửi ProblemDetail nguyên vẹn. Thiết kế streaming error protocol/cancel handling riêng.

## 16. SSE, WebSocket và long-running jobs

### SSE / server streaming

Server-Sent Events có thể giữ HTTP response mở trong nhiều phút:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: progress
data: 10

: heartbeat

event: progress
data: 20
~~~

`: heartbeat` là comment trong SSE framing, có thể giúp giữ hoạt động cho các inactivity timers nếu bytes thật sự được flush tới proxy. Nếu NGINX `proxy_read_timeout=30s`, chọn heartbeat interval nhỏ hơn 30s theo cấu hình thực, đồng thời kiểm proxy buffering và client reconnect. Không áp hard 3-second REST JSON deadline lên một SSE stream được chủ đích giữ lâu.

### WebSocket

WebSocket cần handshake và connection lifecycle riêng. Ping/pong, heartbeat, idle timeout, max lifetime, number of connections và auth/origin policies phải thiết kế theo clients/proxies. Không cho rằng `server.tomcat.keep-alive-timeout` của HTTP requests thay thế mọi WebSocket idle handling.

### File upload/download

Upload/download vài GiB có thể kéo dài nhiều phút. `client_body_timeout`/`proxy_send_timeout` của NGINX là interval progress controls; còn cần total upload limit, byte quota, temporary storage cleanup, bandwidth/concurrency policy. Đừng đặt mọi API timeout thành 30 phút chỉ để hỗ trợ một file upload route.

### Long job: đừng giữ synchronous request vô hạn

Thay vì giữ HTTP connection 2 phút để tạo report, có thể thiết kế:

~~~text
POST /jobs -> 202 Accepted, trả jobId
GET /jobs/{jobId} -> status pending/running/done/failed
GET /jobs/{jobId}/result -> kết quả khi hoàn tất
~~~

`202` chỉ là API response; cần durable queue/worker/job-state system, idempotency và authorization. Đây thường là giải pháp đúng hơn việc tăng client/gateway/app/downstream timeout khắp nơi cho một tác vụ vốn kéo dài.

## 17. Retry, circuit breaker và backoff trong budget

Retry có thể giúp khi lỗi mạng tạm thời hoặc HTTP 429/503 theo policy phù hợp, nhưng phải tính tổng:

- Mỗi attempt có timeout riêng.
- Số attempts tối đa phải hữu hạn.
- Backoff + jitter ăn vào overall time budget.
- Các tầng app/gateway/mesh không nên tự nhân retries không kiểm soát.
- Không retry 400/401/403 hoặc TLS certificate invalid như transient errors.
- Không retry POST/PUT mutation không idempotent nếu không có idempotency protocol.
- Circuit breaker/bulkhead giảm traffic tới dependency đang hỏng; **không thay timeout**.

Một retry policy có thể dùng `Retry-After` khi downstream gửi giá trị hợp lệ, nhưng không để một giá trị quá lớn khiến request vượt deadline của caller. Nếu đủ thời gian cho zero attempts tiếp theo, fail fast và trả error thay vì cứ cố gọi.

## 18. Nhận diện timeout bằng logs và traces

Để điều tra 504, cần cả **proxy-side** và **app-side** metrics. NGINX có thể log:

~~~nginx
log_format upstream_timing
    '$request_id status=$status '
    'rt=$request_time '
    'uct=$upstream_connect_time '
    'uht=$upstream_header_time '
    'urt=$upstream_response_time';

access_log /var/log/nginx/upstream_timing.log upstream_timing;
~~~

`$request_time` phản ánh duration phía NGINX theo semantics riêng; `$upstream_connect_time`, `$upstream_header_time` và `$upstream_response_time` mô tả những pha upstream. Khi có nhiều upstream attempts, biến timing có thể có nhiều giá trị hoặc là `-`. Không suy ra 504 owner chỉ từ một con số thiếu logs.

Trong Spring Boot có Micrometer/Actuator observations (khi được cấu hình), đo server requests và outbound HTTP client timing, exception categories, status, pool saturation, retries, cancellation, DB/connection-acquire duration. Metric names thay đổi theo version/instrumentation; dùng actual registry thay vì hardcode tên không được kiểm chứng.

Đề xuất thêm structured trace fields an toàn:

~~~text
requestId=...
routeTemplate=GET /api/relay/{scenario}
service=downstream-catalog
statusFamily=5xx
outboundTimeout=true
elapsedMs=...
attempt=1
remainingBudgetMs=...
~~~

Không log raw Authorization/Cookie, signed URLs, request body chứa PII hay upstream stacktrace vào public telemetry. Correlation IDs cần lifecycle/trust policy.

### Cần phân biệt trạng thái ở các tầng

- NGINX 504 nhưng app còn chạy 5 giây: có thể proxy timeout sớm.
- Spring trả 504 sau outbound 700ms, NGINX chỉ forward: HTTP client/dependency timeout.
- Curl exit 28 ở 300ms, app ghi 504 ở 700ms: caller timeout trước.
- NGINX 499 thường có nghĩa client đóng connection, không đủ bằng chứng app bị lỗi.
- Một 502 có thể do upstream reset/protocol failure, không chắc do timeout.

## 19. Bảng kiểm thử với fault injection

| Case | Thiết lập | Quan sát mong muốn |
|---|---|---|
| Fast dependency | Fake downstream 100ms | 200 trước caller deadline |
| Slow dependency | Fake downstream 1200ms, client timeout 700ms | App map 504 có kiểm soát |
| Upstream HTTP 503 có internal marker | Fake /target/error | Public 503 không chứa nội bộ |
| Client nhanh hết hạn | curl `--max-time 0.3` | Curl exit 28, không đòi HTTP 504 |
| Proxy idle read timeout | NGINX 2s, upstream không gửi bytes >2s | Proxy 504 hoặc truncated response tùy commit |
| Chunked response vẫn có tiến triển | Mỗi chunk dưới read-idle window | Có thể vượt overall 2s; test semantics |
| Upload client gửi nhỏ giọt | Chèn gaps vượt client_body_timeout | NGINX có thể trả 408 |
| SSE heartbeat | Gửi đúng interval, disable buffering phù hợp | Stream giữ sống theo policy |
| WebSocket idle | Tắt ping/pong hoặc heartbeat | Connection đóng theo server/proxy policy |
| DB pool cạn | Saturate active connections | Pool acquire timeout được phân biệt query timeout |
| Downstream TCP refused | Đóng service B | Public 502/503 theo contract, không leak |
| TLS invalid | Certificate sai SAN/chain | Fail có kiểm soát, không tắt verification |
| Retry vượt budget | Delays + backoff có chủ đích | Overall deadline dừng retry |
| Client abort sau mutation | POST commit rồi cắt response | Idempotency/status reconciliation |
| Peak concurrency | Load 50/100 requests và slow B | Thread/pool/queue/cancel metrics ổn |
| Long async task | Async controller/DeferredResult timeout | Cleanup callbacks và worker lifecycle |
| Proxy generated 504 | Handler chưa trả headers | Gateway error owner được nhận diện |
| Response đã commit | Stream body một phần rồi treo | EOF/truncation handling, không hứa JSON 504 |

Đừng assert timeout chính xác `700 ± 1ms` trong automated test; scheduling, GC/JIT, network và timer resolution làm wall-time dao động. Dùng khoảng cách rõ, ví dụ 100ms vs 1200ms với limit 700ms. Kiểm **status + exception category + cleanup + resources** chứ không chỉ response message.

## 20. Troubleshooting theo triệu chứng

| Triệu chứng | Nguồn có thể | Hướng kiểm tra |
|---|---|---|
| NGINX 504 sau ~2s, Spring xử lý ~5s | Proxy read inactivity ngắn hơn app work | NGINX logs + app trace + proxy_read_timeout |
| Spring direct và qua proxy đều 504 ~700ms | RestClient outbound timeout | JDK HttpClient cause, downstream latency |
| Browser AbortError ~3s, server 200 sau 8s | Browser tự abort sớm | Client timeout, app deadline, cancellation |
| NGINX 499 nhiều dưới tải | Client disconnect khi waiting | Client timeouts, retries, server queue |
| Timeout tăng sau deploy | Dependencies, pool, GC, new retry policy | Compare dependency graph/metrics/traces |
| SSE đóng sau 60s không events | Proxy idle read hoặc browser/network idle | Heartbeat, buffering, proxy policy |
| Upload fail chập chờn | Client-body timeout/size/slow network | Upload route policy, network gap, quota |
| Chỉ POST xảy ra duplicate sau timeout | Retry không idempotent | Idempotency keys, durable operation status |
| 502 thay vì 504 | Upstream disconnect/invalid response | Proxy error logs, TCP/TLS diagnostics |
| Query timeout 1s nhưng request mất 5s | Pool wait/transaction/serialization | DB acquire time và end-to-end spans |

**Quy trình:** xác định error owner → xem timeline/trace → phân loại timeout semantics → đo critical path và remaining budget → sửa đúng tầng → load/cancel tests → monitor sau rollout. Không thay 10 timeouts cùng lúc, vì như vậy không biết sự cố được giải quyết bởi setting nào.

## 21. Anti-pattern cần tránh

| Sai lầm | Vì sao sai | Hướng tốt hơn |
|---|---|---|
| Tưởng `server.tomcat.connection-timeout` giới hạn controller | Chỉ phục vụ request line/connector phase | App/SDK operation deadline |
| Tưởng `proxy_read_timeout` là hard total | Chỉ inactivity giữa upstream reads | Gateway total deadline nếu hỗ trợ |
| Client 2s, downstream 60s | Orphaned work và pool saturation | Budget từ ngoài vào trong |
| Mỗi retry reset whole budget | Backoff/attempts vượt deadline | Total outer deadline |
| Tăng mọi timeout để “sửa 504” | Che bottleneck, tài nguyên bị giữ lâu | Phân loại owner, đo SLO và pools |
| Gọi blocking SDK trong WebFlux event loop | Nghẽn reactor event loop | Dùng reactive client hoặc offload có giới hạn |
| Coi AbortController rollback DB | Cancellation không bảo đảm undo mutation | Idempotency/status query |
| Dùng chung timeout REST và SSE | Ngắt streaming hợp lệ | Route-specific idle/lifetime policy |
| Tin custom deadline header từ internet | Có thể bypass resource policy | Trusted proxy + clamp |
| Log raw exception/headers | Lộ secret/PII | Sanitized ProblemDetail + secure telemetry |
| Chỉ kiểm 200 happy path | Bỏ 499/502/504/cancel cases | Fault injection đa tầng |
| Cho retries ở gateway và app không giới hạn | Retry amplification | Một retry owner/budget |
| Tăng thread pool khi DB đã cạn | Tăng queue/load lên DB | Bulkhead/load shedding |
| Xem curl exit 28 là HTTP 504 | Client có thể không nhận status | Tách caller timeout và server error |

## 22. Checklist triển khai production

1. Vẽ sơ đồ client → CDN/ingress → server → DB/downstream.
2. Lập inventory mọi timeout có **definition và owner** rõ.
3. Chọn user-facing SLO và client overall deadline từ dữ liệu latency.
4. Xác định gateway hỗ trợ hard total deadline hay chỉ connect/read/send inactivity.
5. Thiết kế app operation budget nhỏ hơn outer deadline, chừa margin gửi response.
6. Đặt per-attempt HTTP timeouts theo remaining budget; tính retry/backoff.
7. Đặt TCP connect/TLS/pool acquire/response idle và DB query limits riêng.
8. Bảo đảm timeout classification phù hợp 408/502/503/504, ghi nhận 499 ở NGINX.
9. Không dùng async/reactive để lờ việc blocking thread hoặc cancellation khó.
10. Có idempotency và status reconciliation cho mutations khi caller có thể timeout.
11. Tách long jobs/SSE/WebSocket/uploads khỏi request ngắn và có lifetime/idle/size policies.
12. Tạo tracing/logging/metrics correlation ở proxy/app/downstream không chứa secrets.
13. Test proxy-generated vs app-generated 504, client abort, response commit và retry storm.
14. Theo dõi pools/queues/GC/CPU, p95/p99/p99.9 và tỉ lệ timeout sau rollout.
15. Có canary, rollback, owner và tài liệu quy định lý do từng timeout.

**Nguyên tắc nhớ:** *Một request có ngân sách thời gian toàn tuyến; mỗi hop cần timeout đúng ngữ nghĩa; dependency phải dừng trước khi caller bỏ cuộc; timeout không tự bảo đảm hủy được những công việc đã thực hiện.*

## 23. Câu hỏi tự kiểm tra

**1. NGINX proxy_read_timeout=5s có nghĩa response phải hoàn thành trong 5s?**  
Không. Nó giới hạn khoảng giữa hai upstream reads.

**2. server.tomcat.connection-timeout=5s có hủy controller sleep 10s không?**  
Không. Property này không phải total controller duration.

**3. spring.mvc.async.request-timeout có áp cho tất cả synchronous MVC controller?**  
Không. Nó dành cho async request processing.

**4. Browser chờ 3s, downstream nên chờ 30s?**  
Thường không. Phải xét remaining budget và hủy/cancel phù hợp.

**5. TCP connect timeout có bao trùm body response?**  
Không. Nó chủ yếu chờ thiết lập connection mới.

**6. JdkClientHttpRequestFactory.setReadTimeout(Duration) của Spring 6.1 sử dụng cơ chế nào?**  
Nó dùng JDK HttpRequest.Builder.timeout(Duration) cho request.

**7. NGINX 499 là status HTTP tiêu chuẩn client nhận được?**  
Không. Nó là access-log status đặc thù khi client đóng connection.

**8. HTTP 408 và 504 khác nhau?**  
408 thường là server chờ client gửi request; 504 là gateway chờ upstream quá hạn.

**9. Curl exit code 28 có bằng chứng app trả HTTP 504?**  
Không. Curl có thể timeout trước khi nhận status.

**10. Client timeout có đảm bảo DB transaction rollback?**  
Không. Server/downstream có thể đã commit.

**11. SSE được giữ mở lâu có bị NGINX read timeout 2s chặn ngay khi có heartbeat mỗi giây?**  
Không nhất thiết; phải kiểm buffering/flush và inactivity semantics.

**12. Per-attempt timeout 1s với 3 retries có tổng timeout 1s?**  
Không. Cần outer total operation deadline.

**13. Hikari connection acquisition timeout và JDBC query timeout giống nhau?**  
Không. Một cái chờ pool, một cái hạn chế query.

**14. Khi client abort POST, có nên retry ngay?**  
Không nếu chưa xác minh idempotency/transaction state.

**15. Vì sao error proxy 504 khác app 504 dù có cùng status?**  
Vì owner/điều kiện lỗi khác nhau; proxy có thể tạo HTML còn app trả ProblemDetail.

**16. Tại sao không truyền System.nanoTime() qua mạng làm deadline?**  
Đó là monotonic clock của process, không phải UTC timestamp chung giữa hosts.

**17. Làm sao biết 504 do NGINX hay Spring?**  
So NGINX upstream timings, access/error logs, app traces/metrics và error response owner.

**18. Có nên đặt timeout bằng đúng healthy p99 không?**  
Không máy móc; cần cân bằng false timeouts, tail latency, peak load và user SLO.

## 24. Tài liệu chính thức

- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): server.tomcat.connection-timeout, keepalive, spring.mvc.async.request-timeout.
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): Tomcat/Netty và server settings.
- [Spring Framework 6.1 – JdkClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.6/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html): setReadTimeout và JDK request timeout.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, client factories và HTTP error handling.
- [Spring Framework – Spring MVC Async](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): Callable/DeferredResult và async timeout.
- [Spring Framework – WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): connector và HTTP client configuration.
- [Reactor Netty – HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): connection pool, TCP connect và response timeout.
- [Project Reactor – Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): timeout/cancellation/retry semantics.
- [NGINX – ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): proxy_connect_timeout, proxy_send_timeout, proxy_read_timeout.
- [NGINX – ngx_http_core_module](https://nginx.org/en/docs/http/ngx_http_core_module.html): client_header_timeout, client_body_timeout, send_timeout.
- [NGINX – Log Module](https://nginx.org/en/docs/http/ngx_http_log_module.html): request_time và upstream timing logs.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP 408, 502, 503, 504.
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): public error contracts.
- [MDN – AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController): fetch cancellation ở browser.
- [OWASP – Error Handling](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html): không làm lộ internals qua lỗi.
