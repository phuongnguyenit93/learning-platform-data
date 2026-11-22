# Timeout, chậm phản hồi, ngắt kết nối và giới hạn retry trong kiểm thử HTTP client

Một HTTP client Spring Boot có thể xử lý API trả `200 OK` rất tốt nhưng vẫn gây lỗi nghiêm trọng khi upstream **chậm**, **không trả response**, **đóng socket**, hoặc liên tục trả `429/503`. Test chỉ mock method Java của service để throw exception **không chứng minh** cấu hình timeout, transport network, số requests thật được gửi hay rủi ro request đã được server xử lý nhưng response bị mất.

Bài học thuộc nhóm **HTTP client và giả lập**, tập trung vào khả năng quan sát và kiểm thử bốn tình huống: **response delay**, **timeout**, **disconnect** và **bounded retry**. Ta phân biệt lỗi HTTP status với lỗi I/O; lựa chọn đúng tầng mock; thiết kế retry an toàn với thao tác GET so với POST; kiểm giới hạn `maxAttempts`; quản lý backoff, deadline, `Retry-After` và idempotency. Ví dụ chạy được bằng **Java 17 + Spring Boot 3.5 + Spring Framework 6.2 + Spring Retry 2.0 + JUnit Jupiter** sử dụng `RestClient` và **JDK HttpServer loopback**, không cần Docker hay Internet.

**Điểm quan trọng nhất:** timeout hoặc connection reset **không tự chứng minh upstream chưa commit**. Vì thế không tự động gửi lại request tạo thanh toán/đơn hàng nếu API chưa bảo đảm idempotency.

## 1. Bản đồ lifecycle của HTTP request

```text
HTTP CLIENT                                        HTTP SERVER
  |
  +---- DNS resolution -------> DNS resolver
  |      lỗi DNS / UnknownHost
  |
  +---- TCP connect ----------> listening port
  |      connect timeout / refused / route error
  |
  +---- TLS handshake -------> server (HTTPS)
  |      certificate / trust / handshake error
  |
  +---- HTTP request headers + body -------------->|
  |                                               +-- application processing
  |                                               +-- có thể đã commit DB
  |
  +<--- HTTP status + headers ---------------------| 200/400/429/503
  |
  +<--- HTTP response body ------------------------| có thể chậm/cắt giữa chừng
  |
  +---- Client decode / map response
```

| Hiện tượng | Client thường nhìn thấy | Server có thể đã xử lý chưa? | Mục tiêu test |
|---|---|---|---|
| Connect timeout | Không mở được TCP connection trong deadline | Thường chưa nhận HTTP request tại listener ấy | Kết nối bị drop/route delay; đúng connect timeout |
| Connection refused | Port đóng hoặc listener từ chối | Thường chưa có HTTP request tại listener | Không nhầm với connect timeout |
| Response chậm | Kết nối mở, headers/body đến muộn | Có thể đang xử lý hoặc đã commit | Deadline ngắn thì fail, deadline dài hơn thì pass |
| 503 | Có HTTP response `Service Unavailable` | Có thể đã xử lý một phần | Retry GET đúng số lần |
| 429 | Có HTTP response `Too Many Requests` | Phụ thuộc API | Throttle/Retry-After/budget |
| 400/401/403/404 | HTTP response cho lỗi request | Phụ thuộc nghiệp vụ | Fail fast, không retry cùng input |
| Disconnect trước headers | EOF/reset/transport error | **Chưa chắc biết** | Propagate I/O exception, không coi là 503 |
| Disconnect giữa body | Partial body/decoder exception | Thường đã xử lý request | Không coi partial payload là success |
| Mất response của POST | Timeout/EOF | **Có thể đã commit** | Idempotency/status lookup, không replay tùy tiện |

Trong `RestClient.retrieve()`, HTTP 4xx/5xx mặc định thường thành `HttpClientErrorException` hoặc `HttpServerErrorException`; lỗi I/O thường được Spring bọc vào `ResourceAccessException`. Root cause `IOException` có thể khác giữa JDK HttpClient, Apache HttpClient, Reactor Netty, hệ điều hành và thời điểm socket bị đóng. Không assert nguyên văn message như `Connection reset by peer` trong mọi test.

## 2. Connect timeout khác response timeout

### 2.1. Connect timeout

Ví dụ JDK 17 HTTP client:

```java
HttpClient jdk = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(1))
        .version(HttpClient.Version.HTTP_1_1)
        .build();
```

Snippet cần `java.net.http.HttpClient` và `java.time.Duration`. Connect timeout áp dụng khi **tạo kết nối mới**, không tự đặt deadline cho toàn bộ quá trình server xử lý. Nếu connection pool giữ kết nối sẵn, không có TCP connect mới mỗi request.

Không dùng một **localhost port không có listener** để chứng minh connect timeout: thường server trả `Connection refused` tức thì. Tạo connect timeout đáng tin cần Toxiproxy hoặc fault injection có kiểm soát (drop SYN, proxy stalled, network namespace); địa chỉ public/unroutable có thể thất bại tức thì vì mạng CI.

### 2.2. Read/response/request timeout

Spring Framework 6.2 hỗ trợ JDK request factory:

```java
JdkClientHttpRequestFactory factory =
        new JdkClientHttpRequestFactory(jdk);
factory.setReadTimeout(Duration.ofMillis(150));
```

Javadoc liên hệ `setReadTimeout(Duration)` với `java.net.http.HttpRequest.Builder.timeout(Duration)`. Với JDK backend, đây là **request timeout** của HTTP request; không đồng nhất với socket idle timeout của mọi transport. Apache/Jetty/Reactor có connect, response, idle và pool-acquire deadlines khác nhau.

Test response timeout nên có **HTTP server thật nhận request rồi cố tình chờ**: ví dụ stub đợi 900ms còn client deadline 150ms. Nếu test chỉ mock gateway method bằng Mockito rồi throw `SocketTimeoutException`, bạn kiểm **business handling**, chưa chứng minh HTTP transport được cấu hình 150ms.

**Không assert elapsed == 150ms.** CI scheduler, JVM warmup, CPU load và connection establishment có thể làm wall-clock lệch. Assertion mạnh hơn: client không nhận response 200 bị delay vượt deadline, thay vào đó throw transport timeout.

### 2.3. Tổng request budget

Giới hạn 3 attempts, mỗi lần tối đa 800ms, backoff 100ms/200ms:

```text
Worst-case riêng phần attempts + delay:
3 × 800ms + 100ms + 200ms = 2700ms
```

Đây chưa tính queue tại connection pool, DNS, proxy, serialization và các bước khác. Một business SLA 1 giây có thể bị vi phạm dù mỗi HTTP attempt obey timeout 800ms. Production cần **deadline end-to-end**, max attempts, max elapsed time và quyết định không retry khi còn quá ít thời gian.

## 3. MockRestServiceServer, WireMock, MockWebServer hay HTTP server thật?

| Công cụ | Đi qua network socket? | Chứng minh được |
|---|---|---|
| Mockito mock method gateway | Không | Service branch, error classification đơn giản |
| `MockRestServiceServer` | Không đi qua TCP thật | Method/path/headers/body/status mapping với RestClient/RestTemplate |
| WireMock chạy port động | **Có** | Fault HTTP, delays, resets, request journal |
| OkHttp `MockWebServer` | **Có** | Queue replies, `SocketPolicy`, recorded requests |
| JDK `HttpServer` | **Có** | Response status, delay, abrupt close qua HTTP loopback |
| Toxiproxy | Có network proxy | Drop, latency, bandwidth, disconnect ở tầng network |
| Testcontainers | Container backend thật | Gần cấu hình thực, nhưng khởi động tốn thời gian |

Tài liệu Spring Framework nhấn mạnh mock web server nhận request qua HTTP thật phù hợp khi muốn kiểm các khác biệt subtle giữa underlying HTTP clients. `MockRestServiceServer` tốt cho HTTP request contract, nhưng dùng custom fake request factory **không kiểm TCP timeout hay TLS handshake**.

Ví dụ dưới đây chọn **JDK HttpServer**: có thể chạy chỉ với JDK 17 + Spring dependencies, mở port 0 tránh xung đột, có script response queue, delay và close. Với các lỗi nâng cao như truncated chunk, TLS, half-open socket, hãy dùng WireMock/MockWebServer hoặc network fault proxy tùy mục tiêu.

## 4. Retry phải phân loại status và request semantics

| Trạng thái / lỗi | Chính sách thường phù hợp | Ngoại lệ cần xem |
|---|---|---|
| 200/201/204 | Thành công, không retry | Validate response contract |
| 400/422 | Không retry input y nguyên | Payload cần sửa |
| 401/403 | Không retry vô hạn | Credential refresh có policy riêng |
| 404 | Không retry mặc định | Có thể retry nếu eventual-consistency contract rõ |
| 408 | Có thể retry **idempotent** operation | Outcome chưa rõ |
| 409 | Không retry mù | CAS/optimistic conflict có thể cần read-modify-write |
| 425 | Cân nhắc replay safety | TLS early-data |
| 429 | Retry có giới hạn + `Retry-After` | Quota có thể đã hết |
| 500/502/503/504 | Thường retry read idempotent ngắn | Không phải mọi 5xx đều transient |
| Connect/response timeout | Retry có điều kiện | TLS/DNS/permanent failures không nên retry |
| Socket EOF/reset | Retry có điều kiện | Upstream có thể đã commit |
| JSON decode/schema error | Thường không retry | Contract mismatch |
| POST payment/order | Không retry mặc định | Chỉ retry nếu server có idempotency/dedup |

**Không bao giờ viết `while(true) { retry(); }` vô hạn cho upstream lỗi.** Một retry policy cần: số attempts, lỗi eligible, backoff, budget, operation safety, idempotency và cách báo lỗi khi hết giới hạn.

### Attempts và retries

```text
maxAttempts = 3
  Attempt 1 --> 503
  Retry   1 --> Attempt 2 --> 503
  Retry   2 --> Attempt 3 --> 200
  STOP: success

Nếu Attempt 3 vẫn 503 --> STOP: failure.
Không có Attempt 4.
```

Spring Retry `RetryTemplate.builder().maxAttempts(3)` nghĩa là **3 lần gọi tổng cộng** (1 ban đầu + 2 retries). Đây không phải “3 retries cộng thêm lần đầu”. Test exhaustion sẽ script **503, 503, 503, 200**, rồi assert response 200 thứ tư chưa bao giờ được lấy.

### Exponential backoff và jitter

```java
RetryTemplate policy = RetryTemplate.builder()
        .maxAttempts(3)
        .exponentialBackoff(100L, 2.0, 1000L, true)
        .retryOn(HttpServerErrorException.class)
        .build();
```

Đoạn trên là snippet, cần Spring Retry imports. Backoff giúp tránh retry storm khi nhiều callers cùng gặp 503, jitter làm dãn thời điểm retry. Ví dụ runnable sau dùng **`noBackoff()` chỉ cho JUnit** để kiểm số attempts rõ ràng, không phải khuyến nghị production.

## 5. Test matrix trước khi viết mã

| Kịch bản | Stub response | Bằng chứng phải assert |
|---|---|---|
| GET 200 | 200 | Body đúng, đúng 1 request |
| Phục hồi | 503, 503, 200 | 3 requests, cuối cùng thành công |
| Hết retry | 503, 503, 503, 200 | Throw sau 3, response thứ 4 còn nguyên |
| Client error | 400, 200 | 1 request, fail-fast |
| Not found | 404, 200 | 1 request, fail-fast |
| Rate limit | 429, 200 | 2 requests trong demo policy |
| Chậm nhưng chưa hết hạn | Delay 100ms, deadline 2s | 200 và 1 request |
| Chậm quá deadline | Delay 900ms, deadline 150ms | Transport exception, không nhận 200 |
| Ngắt kết nối trước headers | Close exchange | ResourceAccessException, không có HTTP status |
| POST không idempotent | 503, 200 | 1 request, **không retry tự động** |
| Server nhận POST và commit rồi mất response | State + disconnect | Unknown outcome; cần ID/status lookup |
| 429 Retry-After > deadline | Header + throttle | Không sleep vô hạn / fail đúng policy |

Đừng đặt assertion `socketRequests == retryAttempts` trong case disconnect một cách cứng nhắc: một số HTTP client (bao gồm JDK client) có **transparent retry ở transport layer** với một số connection failures. Cần tách số lần gửi HTTP trên wire, số application attempts ở RetryTemplate, và số business side effects của server.

## 6. Ví dụ đầy đủ Java 17 + Spring Boot 3.5 + JUnit Jupiter

Ví dụ xây `PartnerClient` dùng Spring `RestClient`:
- `GET /rate` có RetryTemplate max 3 attempts trên 5xx/429/network I/O.
- `POST /orders` **không dùng retry**, vì chưa có idempotency contract.
- Client sử dụng JDK HttpClient với connect timeout và JDK request factory với deadline.
- Test dùng JDK HTTP server localhost trên port động, một response queue, và đếm requests.
- Test hoàn toàn độc lập Internet; sau mỗi test dừng server + executor.

### 6.1. Cấu trúc

```text
http-client-fault-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/http/
    │   ├── HttpDemoApplication.java
    │   └── PartnerClient.java
    └── test/java/com/example/http/
        └── PartnerClientTest.java
```

### 6.2. Maven POM

File **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>http-client-fault-demo</artifactId>
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
            <groupId>org.springframework.retry</groupId>
            <artifactId>spring-retry</artifactId>
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
```

Spring Boot 3.5.0 BOM quản lý Spring Framework 6.2.x và Spring Retry 2.0.x. JDK `com.sun.net.httpserver.HttpServer` là API có trong Java 17; Maven classpath thông thường dùng được. Khi chạy project theo module-path đặc biệt, phải bảo đảm module `jdk.httpserver` được resolve.

### 6.3. Spring Boot application class

File **`src/main/java/com/example/http/HttpDemoApplication.java`**:

```java
package com.example.http;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpDemoApplication.class, args);
    }
}
```

Test không cần khởi động application context, vì mục tiêu là HTTP client behavior; tạo trực tiếp `PartnerClient` giúp mỗi test rõ URL, timeout và retry count. Trong ứng dụng thật có thể đưa client thành `@Bean` cùng `@ConfigurationProperties` và inject Boot `RestClient.Builder` để kế thừa cấu hình SSL/observability.

### 6.4. Định nghĩa PartnerClient

File **`src/main/java/com/example/http/PartnerClient.java`**:

```java
package com.example.http;

import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

public final class PartnerClient {

    private final RestClient rest;
    private final RetryTemplate retry;

    public PartnerClient(
            String baseUrl,
            Duration connectTimeout,
            Duration requestTimeout,
            int maxAttempts) {

        HttpClient jdk = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                .version(HttpClient.Version.HTTP_1_1)
                .build();

        JdkClientHttpRequestFactory factory =
                new JdkClientHttpRequestFactory(jdk);
        factory.setReadTimeout(requestTimeout);

        this.rest = RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();

        // noBackoff chỉ để JUnit không phải chờ; production
        // cần bounded exponential backoff/jitter/Retry-After.
        this.retry = RetryTemplate.builder()
                .maxAttempts(maxAttempts)
                .noBackoff()
                .retryOn(error ->
                        error instanceof ResourceAccessException
                        || error instanceof HttpServerErrorException
                        || (error instanceof HttpClientErrorException ex
                                && ex.getStatusCode().value() == 429))
                .build();
    }

    public String getRate() {
        return retry.execute(context ->
                rest.get()
                        .uri("/rate")
                        .retrieve()
                        .body(String.class));
    }

    // Không retry POST khi chưa có idempotency contract.
    public String createOrderWithoutRetry(String payload) {
        return rest.post()
                .uri("/orders")
                .contentType(MediaType.TEXT_PLAIN)
                .body(payload)
                .retrieve()
                .body(String.class);
    }
}
```

`RetryTemplate` nằm trong code rõ ràng, không cần AOP/`@EnableRetry`. Nếu dùng `@Retryable` để thay thế, hãy test **qua bean Spring proxy**, vì self-invocation thường bỏ qua advice. Predicate trên chỉ dành cho GET: 5xx, 429 và ResourceAccessException. Production phải phân tích cause: TLS/DNS permanent failures không nên retry; GET cũng có thể không an toàn nếu upstream API vi phạm HTTP semantics.

### 6.5. HTTP stub thật và 10 JUnit tests

File **`src/test/java/com/example/http/PartnerClientTest.java`**:

```java
package com.example.http;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PartnerClientTest {

    private HttpServer server;
    private ExecutorService executor;
    private final Queue<Reply> replies = new ConcurrentLinkedQueue<>();
    private final AtomicInteger received = new AtomicInteger();
    private volatile boolean disconnectEveryRequest;

    private record Reply(int status, String body, long delayMillis) {
        static Reply status(int status, String body) {
            return new Reply(status, body, 0);
        }
        static Reply slow(long millis, String body) {
            return new Reply(200, body, millis);
        }
    }

    @BeforeEach
    void startStub() throws IOException {
        executor = Executors.newFixedThreadPool(4, task -> {
            Thread t = new Thread(task, "http-stub");
            t.setDaemon(true);
            return t;
        });
        server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/rate", this::respond);
        server.createContext("/orders", this::respond);
        server.setExecutor(executor);
        server.start();
    }

    @AfterEach
    void stopStub() {
        if (server != null) {
            server.stop(0);
        }
        if (executor != null) {
            executor.shutdownNow();
        }
    }

    private void respond(HttpExchange exchange) throws IOException {
        received.incrementAndGet();

        try {
            if (disconnectEveryRequest) {
                // Đóng trước HTTP response headers.
                exchange.close();
                return;
            }

            Reply next = replies.poll();
            if (next == null) {
                next = Reply.status(503, "NO_STUB_RESPONSE");
            }

            if (next.delayMillis() > 0) {
                Thread.sleep(next.delayMillis());
            }

            byte[] bytes =
                    next.body().getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                    .set("Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(next.status(), bytes.length);

            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            exchange.close();
        } catch (IOException clientClosed) {
            // Nếu client timeout trước khi response được ghi,
            // lỗi broken pipe ở fake server là fault dự kiến.
            exchange.close();
        }
    }

    private void queue(Reply... values) {
        for (Reply reply : values) {
            replies.add(reply);
        }
    }

    private PartnerClient client(long deadlineMs, int attempts) {
        String base = "http://127.0.0.1:"
                + server.getAddress().getPort();
        return new PartnerClient(
                base,
                Duration.ofSeconds(1),
                Duration.ofMillis(deadlineMs),
                attempts);
    }

    @Test
    void successUsesOneRequest() {
        queue(Reply.status(200, "RATE-OK"));

        assertEquals("RATE-OK", client(2000, 3).getRate());
        assertEquals(1, received.get());
    }

    @Test
    void retry503TwiceThenSucceed() {
        queue(
                Reply.status(503, "busy1"),
                Reply.status(503, "busy2"),
                Reply.status(200, "RATE-READY"));

        assertEquals("RATE-READY", client(2000, 3).getRate());
        assertEquals(3, received.get());
    }

    @Test
    void retryLimitIsThreeNotFour() {
        queue(
                Reply.status(503, "busy1"),
                Reply.status(503, "busy2"),
                Reply.status(503, "busy3"),
                Reply.status(200, "SHOULD_NOT_RUN"));

        assertThrows(
                HttpServerErrorException.class,
                () -> client(2000, 3).getRate());

        assertEquals(3, received.get());
        assertEquals(1, replies.size());
    }

    @Test
    void status400FailsFast() {
        queue(
                Reply.status(400, "bad request"),
                Reply.status(200, "SHOULD_NOT_RUN"));

        assertThrows(
                HttpClientErrorException.BadRequest.class,
                () -> client(2000, 3).getRate());

        assertEquals(1, received.get());
    }

    @Test
    void status404FailsFast() {
        queue(
                Reply.status(404, "missing"),
                Reply.status(200, "SHOULD_NOT_RUN"));

        assertThrows(
                HttpClientErrorException.NotFound.class,
                () -> client(2000, 3).getRate());

        assertEquals(1, received.get());
    }

    @Test
    void status429Then200RetriesInDemo() {
        queue(
                Reply.status(429, "rate limited"),
                Reply.status(200, "RATE-OK"));

        assertEquals("RATE-OK", client(2000, 3).getRate());
        assertEquals(2, received.get());
    }

    @Test
    void slowButWithinDeadlineWorks() {
        queue(Reply.slow(100, "SLOW-OK"));

        assertEquals("SLOW-OK", client(2000, 1).getRate());
        assertEquals(1, received.get());
    }

    @Test
    void slowBeyondDeadlineFails() {
        queue(Reply.slow(900, "TOO-LATE"));

        assertThrows(
                ResourceAccessException.class,
                () -> client(150, 1).getRate());
        assertTrue(received.get() >= 1);
        // Không assert elapsed == 150ms trên CI.
    }

    @Test
    void disconnectBeforeHeadersIsTransportFailure() {
        disconnectEveryRequest = true;

        assertThrows(
                ResourceAccessException.class,
                () -> client(2000, 1).getRate());
        assertTrue(received.get() >= 1);
        // JDK có thể retry ở tầng wire bên dưới RetryTemplate.
    }

    @Test
    void unsafePostDoesNotRetry503() {
        queue(
                Reply.status(503, "busy"),
                Reply.status(200, "ORDER-CREATED"));

        assertThrows(
                HttpServerErrorException.class,
                () -> client(2000, 3)
                        .createOrderWithoutRetry("PAYMENT-REQUEST"));

        assertEquals(1, received.get());
        assertEquals(1, replies.size());
    }
}
```

### 6.6. Phân tích bằng chứng của các ca test

| Test | Bằng chứng |
|---|---|
| `successUsesOneRequest` | 200 và body đúng; 1 request |
| `retry503TwiceThenSucceed` | 503,503,200 được retry và cuối cùng thành công |
| `retryLimitIsThreeNotFour` | 3 attempts, response 200 thứ tư chưa bị tiêu thụ |
| `status400FailsFast` | 400 không retry cùng input |
| `status404FailsFast` | 404 không retry mặc định |
| `status429Then200RetriesInDemo` | 429 có retry trong policy demo (chưa kiểm Retry-After) |
| `slowButWithinDeadlineWorks` | Chậm hơn bình thường nhưng vẫn được response nếu trong deadline |
| `slowBeyondDeadlineFails` | Request timeout chuyển thành transport exception, không chấp nhận 200 muộn |
| `disconnectBeforeHeadersIsTransportFailure` | Socket đóng trước headers -> không có HTTP status; app nhận lỗi |
| `unsafePostDoesNotRetry503` | POST không gửi lần hai dù trong queue có 200 |

Với **HTTP status** 503/429, counter đo đúng network requests nhận tại stub. Với **disconnect**, JDK HttpClient có thể **transparent retry** một số lỗi I/O/connection, nên test không khẳng định đúng một wire request dù `RetryTemplate.maxAttempts=1`. Muốn chứng minh số business side effects, phải đo ở server bên cạnh application attempt count.

Mọi test dùng server trên `127.0.0.1` port **0** do OS tự cấp, tránh xung đột port 8080. `@AfterEach` dừng server và executor; handler có thể bị interrupt khi client timeout. Không có network call ra Internet và không cần tài khoản bên thứ ba.

### 6.7. Lệnh chạy

Cần Java 17+, Maven và khả năng bind HTTP loopback:

```bash
mvn test
mvn -Dtest=PartnerClientTest test
```

Nếu có Maven Wrapper: `./mvnw test` hoặc `mvnw.cmd test` trên Windows. Dự kiến **10 JUnit tests**, những ca lỗi mong đợi PASS khi `assertThrows` khớp. Không có stdout nghiệp vụ cố định; Maven Surefire/HTTP client log phụ thuộc môi trường.

Mã ví dụ được rà soát theo Spring Boot 3.5/Spring Framework 6.2/Spring Retry 2.0, **không phải tuyên bố đã chạy Maven trong lúc viết nội dung**. Khi áp dụng thực, cần chạy trong CI với JDK và HTTP transport giống production. Nếu local runner dùng module-path đặc biệt, cần đảm bảo `jdk.httpserver` được resolve.

## 7. Retry-After, jitter và tổng deadline

Rate limit response có thể chứa:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 3
Content-Type: text/plain

rate limited
```

`Retry-After` có thể là giây hoặc HTTP-date. Client production cần parse an toàn, giới hạn giá trị, đối chiếu **remaining business deadline**, và không retry khi user đã hết budget. Nếu caller chỉ còn 500ms mà server bảo đợi 3s, chờ 3s sẽ vi phạm SLA. Test thêm các trường hợp: header không hợp lệ, giá trị cực lớn, HTTP-date quá khứ, repeated 429, concurrent callers và rate limit quota exhausted.

**Demo dùng `noBackoff()` và không đọc Retry-After.** Đây là thiết kế để test classifier/attempts nhanh; không phải production retry policy. Khi triển khai thật dùng bounded exponential backoff + jitter, max elapsed time và circuit breaker/bulkhead/rate limiter.

Nếu A retry 3 lần vào service B và B lại retry 3 lần vào C, một user request có thể thành 9 calls tới C. Đừng lồng retries vô thức ở HTTP client, service, gateway và reactive operator. Một deadline end-to-end và retry budget xuyên hệ thống giúp tránh retry storm.

## 8. POST bị mất response: idempotency và unknown outcome

Hãy xem timeline:

```text
Client                               Payment server
  |
  +--- POST /charges ----------------->|
  |                                   +-- COMMIT charge A
  X response connection closed       |
  |                                   |
  +--- RETRY POST (nguy hiểm) ------->|
                                      +-- có thể COMMIT charge B
```

Client timeout không có nghĩa charge A chưa thực hiện. Nếu API hỗ trợ **Idempotency-Key**, client giữ một key ổn định qua các attempts:

```http
POST /charges HTTP/1.1
Idempotency-Key: order-9e4a
Content-Type: application/json

{"amountMinor":150000,"currency":"VND"}
```

Đây là payload minh họa. Server phải triển khai **deduplication thật**, lưu outcome/operation ID và quy định retry với key trùng, payload khác, TTL của key, concurrency của hai request cùng key. Chỉ thêm header không tự bảo đảm idempotency.

### Cách test POST đã commit nhưng mất response

1. Stub nhận POST với key K.
2. Stub ghi state `charge[K] = done` rồi cố đóng socket trước khi gửi response.
3. Client báo unknown outcome, không tự replay trừ khi contract hỗ trợ.
4. Client query `GET /operations/K` hoặc retry **cùng K** theo API chính thức.
5. Assert final charge count đúng **1**, không chỉ Mockito verify number of calls.
6. Thử duplicate key/concurrent requests và payload mismatch policy.

Stub ở phần 6 chỉ kiểm **disconnect trước headers** chứ chưa kiểm backend payment deduplication. Vì vậy không được suy từ test disconnect PASS rằng charge sẽ không bị lặp. Đó là trách nhiệm của **test stateful upstream/idempotency riêng**.

## 9. WebClient và @RestClientTest: khác tầng, khác timeout

### Reactive WebClient

```java
Mono<String> result = webClient.get()
        .uri("/rate")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(2))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                .filter(error ->
                        error instanceof WebClientResponseException.ServiceUnavailable
                        || error instanceof java.util.concurrent.TimeoutException));
```

Đây là snippet, không phải file Java độc lập: cần WebFlux/Reactor dependencies và biến `webClient` đã được cấu hình. `Retry.backoff(2, ...)` nghĩa là 2 **retries** sau attempt đầu, tổng 3 subscriptions. `.timeout()` đặt trước `.retryWhen()` có thể giới hạn từng attempt; đặt sau có thể giới hạn toàn pipeline. Khi cần kiểm backoff logic thuần Reactor, có thể dùng `StepVerifier.withVirtualTime` nhưng virtual time **không điều khiển TCP socket thật**.

### @RestClientTest và MockRestServiceServer

`@RestClientTest` có thể tạo client slice và `MockRestServiceServer` để kiểm method/path/header/status/JSON mapping mà không mở socket. Nó **không kiểm HTTP transport timeout** trừ khi test thực sự cấu hình mock web server listener bên ngoài. Nếu client dùng `RestClient.retrieve()`, default 4xx/5xx status handler phát exception; nếu chuyển sang `exchange((req,res)->...)`, status handlers của retrieve **không được áp dụng**, bạn phải kiểm status thủ công. Nếu quên, 503 có thể bị coi như success và RetryTemplate không được kích hoạt.

Với production đang dùng Apache HttpClient, Jetty, JDK HttpClient hoặc Reactor Netty, hãy chạy **network fault test đúng factory**. Thay dependency có thể đổi backend được Spring Boot tự chọn, làm timeout/reset semantics khác. Test fake method không nhận ra điều đó.

## 10. Chẩn đoán lỗi flaky và lỗi cấu hình retry

| Hiện tượng | Nguyên nhân thường gặp | Hướng sửa |
|---|---|---|
| Timeout pass local nhưng fail CI | Delay sát deadline, CPU contention | Chọn khoảng cách lớn và không assert exact milliseconds |
| Disconnect test thấy >1 wire request | Underlying JDK auto-retry connection | Tách app attempts và wire count |
| 503 retry 4 lần dù max 3 | Off-by-one, nested retries | Queue 503,503,503,200 và assert last response còn |
| 401/400 bị retry liên tục | Retry mọi RestClientException | Predicate rõ, fail-fast 4xx cố định |
| 429 retry ngay tạo retry storm | Không backoff/Retry-After | Rate limit, budget, bounded jitter |
| Client báo timeout nhưng upstream có order | Response mất sau COMMIT | Idempotency key + status reconciliation |
| MockRestServiceServer pass, socket test fail | Mock không đi qua network | Dùng loopback WireMock/HttpServer/MockWebServer |
| Test cố dùng port 8080 | Port có thể đang bị chiếm | Bind port 0, query actual port |
| Closed port được gọi là connect timeout | Connection refused xảy ra nhanh | Network drop/proxy phù hợp |
| Chỉ tăng timeout khi server trả 503 | 503 là HTTP status, không phải thời gian | Kiểm overload và retry classifier |
| POST payment bị gửi hai lần | Retry non-idempotent | Không replay khi chưa có dedup contract |
| Test ảnh hưởng suite tiếp theo | Không stop stub/executor | @AfterEach cleanup đúng |
| Thay HTTP library làm test exception khác | Root cause/wrapping khác | Assert đúng abstraction/cause, tránh message cứng |
| Nhiều service hops mỗi tầng retry | Request amplification | Đặt retry boundary và total deadline rõ |

Với production, log/metric nên có operation name, upstream alias, response status, error type, application attempt number, total duration, backoff decision, trace/correlation ID và rate limit. Không log Authorization, cookies, API keys, payment payload hoặc thông tin cá nhân. Nếu HTTP client ghi raw headers tại DEBUG/TRACE, cần redaction và giới hạn retention CI artifacts.

## 11. Checklist trước khi hoàn thành

- [ ] Phân biệt connect timeout, request timeout, response delay và deadline tổng.
- [ ] Không coi connection refused là connect timeout.
- [ ] Network fault tests chạy qua socket/proxy khi cần, không chỉ Mockito.
- [ ] Stub delay lệch rõ với deadline, không assert elapsed time tuyệt đối.
- [ ] Có test success và recover từ transient failures.
- [ ] Có test retry cap, response thứ tư **không được dùng** khi maxAttempts=3.
- [ ] 400/404 fail-fast và 429/5xx được phân loại theo policy.
- [ ] Tính đúng **total attempts** thay vì retries cộng thêm.
- [ ] Production có backoff+jitter, Retry-After khi cần, max elapsed time/deadline.
- [ ] GET/POST được retry dựa theo **ngữ nghĩa side effect thật**.
- [ ] POST payment/order không retry mù quáng khi outcome unknown.
- [ ] Nếu retry POST, server thật có idempotency key/dedup/status lookup.
- [ ] Không đếm application retry đồng nhất với wire requests khi transport auto-retry.
- [ ] Với WebClient, vị trí timeout/retryWhen phù hợp deadline mong muốn.
- [ ] MockRestServiceServer dùng cho client contract; socket test dùng listener thật.
- [ ] Stub bind port động và đóng server/thread sau test.
- [ ] Không gọi API production trong suite; secrets không bị log.
- [ ] Test chạy được trong CI với đúng underlying HTTP library.
- [ ] Kết luận giới hạn đúng: timeout/disconnect test không chứng minh upstream rollback.

**Kết luận:** Kiểm thử HTTP client cần đưa ra bằng chứng rõ ràng về **chậm phản hồi trong/ngoài deadline, transport disconnect, HTTP status và số attempts tối đa**. Retry phải có giới hạn và chỉ áp dụng cho operation có thể replay an toàn; mất response của POST là **unknown outcome**, không phải giấy phép gửi lại vô điều kiện.

### Tài liệu chính thức

- [Spring Framework — Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html)
- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html)
- [JdkClientHttpRequestFactory 6.2 — Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html)
- [Spring Retry — RetryTemplateBuilder API](https://docs.spring.io/spring-retry/docs/2.0.x/apidocs/spring.retry/org/springframework/retry/support/RetryTemplateBuilder.html)
- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html)
- [JDK 17 — HttpServer/HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html)
- [Reactor — Error Handling and Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
