# Kiểm thử retry có giới hạn và số lần bên đích thực nhận

Khi `order-service` gọi `catalog-service` qua **Spring Cloud LoadBalancer**, HTTP client hoặc tầng resilience có thể gửi lại một request sau lỗi tạm thời. Cấu hình “retry tối đa hai lần” nghe đơn giản, nhưng kiểm thử chỉ xác nhận response cuối là HTTP 200 chưa đủ. Một request có thể được thử ba lần nhưng chỉ hai lần vào handler của backend vì một attempt không kết nối được. Hoặc ngược lại, hai tầng retry chồng nhau khiến backend nhận nhiều lần hơn ngân sách dự kiến.

Bài thuộc chương **Kiểm thử tự động** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Ta sẽ phân biệt một **thao tác nghiệp vụ**, số **HTTP attempts**, số lần **LoadBalancer chọn ServiceInstance**, số request **backend thực nhận** và số **tác dụng phụ đã commit**. Sau đó xây một bộ integration test với hai HTTP server thật, RestClient `@LoadBalanced`, các lỗi 503/400 có kiểm soát và bộ đếm đặt ngay tại HTTP handler. Phần cuối mở rộng sang WebClient, OpenFeign, retry/timeout, idempotency và quan sát lỗi.

> Nguyên tắc: **đếm retry ở caller không chứng minh backend đã nhận từng đó request; đếm request backend nhận cũng không chứng minh nghiệp vụ đã commit từng đó lần**. Cần assert tại đúng ranh giới mà yêu cầu kiểm thử muốn bảo đảm.

## 1. Năm loại số đếm phải tách riêng

| Số đếm | Định nghĩa | Nơi đo |
|---|---|---|
| **Logical operations** | Số ý định nghiệp vụ từ caller | Entry point business service |
| **HTTP attempts** | Số lần retry policy/HTTP transport thử thực hiện một request | Retry wrapper và client instrumentation |
| **Instance selections** | Số lần LoadBalancer tìm/chọn một `ServiceInstance` | LoadBalancer lifecycle/tracing |
| **Backend received** | Số request thực sự vào HTTP handler của instance đích | Counter, access log hoặc stub server |
| **Business side effects** | Số giao dịch/tác dụng phụ đã hoàn tất | Database, ledger, outbox hoặc provider |

Ví dụ:

~~~text
logicalOperations = 1
maxAttempts       = 3
httpAttempts      = 3
lbSelections      = có thể là 3, phụ thuộc tầng retry
backendReceived   = 2, nếu một attempt lỗi trước khi đến HTTP handler
businessWrites    = 0, nếu request là GET chỉ đọc
~~~

**Không coi `httpAttempts == backendReceived` là bất biến chung.** Một attempt có thể lỗi trước khi gửi HTTP. Một request đã được xử lý có thể mất response khiến caller retry. Một gateway hoặc transport còn có thể retry bên trong mà caller không nhìn thấy từng lần.

Quy ước trong bài:

- `maxAttempts = 3` nghĩa là tối đa **ba lần thử bao gồm attempt đầu tiên**.
- `maxRetries = 2` nghĩa là tối đa **hai lần thử lại sau attempt đầu**.
- **Received** trong lab được xác định khi handler của server thực sự được gọi.
- **Success** ở caller chỉ được xác định khi nhận response hợp lệ theo contract.

~~~mermaid
flowchart LR
    O["1 business operation"] --> A1["Attempt 1"]
    A1 -->|503| A2["Attempt 2"]
    A2 -->|503| A3["Attempt 3"]
    A3 -->|200| OK["Caller success"]
    A1 --> H["Backend received counter"]
    A2 --> H
    A3 --> H
~~~

Với kịch bản trên, nếu cả ba attempts đều đi vào handler, backend counter phải bằng **3**. Đó là kết luận từ **kịch bản lỗi 503 được tạo tại backend**, không phải kết luận chung cho mọi lỗi mạng.

## 2. Request đi qua những lớp nào?

~~~mermaid
flowchart TD
    O["Business code gọi catalog"] --> R["Retry policy / deadline"]
    R --> A["HTTP attempt n"]
    A --> LB{"LoadBalancer chọn được instance?"}
    LB -->|Không| NI["Lỗi no-instance: chưa vào backend"]
    LB -->|Có| NET{"Kết nối và gửi HTTP thành công?"}
    NET -->|Không| IO["Connect refused / TLS / network"]
    NET -->|Có| HANDLER["Backend handler: received++"]
    HANDLER --> EXEC["Xử lý nghiệp vụ, có thể commit"]
    EXEC --> RESP{"Response về caller đúng hạn?"}
    RESP -->|2xx| OK["Thành công"]
    RESP -->|503/429| RE["Có thể retry nếu policy cho phép"]
    RESP -->|Timeout/mất response| UN["Outcome UNKNOWN nếu có side effect"]
    NI --> RE
    IO --> RE
    RE --> R
~~~

`ServiceInstanceListSupplier` lấy tập ứng viên từ discovery/cache/health; chính sách chọn một instance. HTTP client sau đó mới mở kết nối và gửi request. Nếu không có instance, request không vào backend. Nếu connect refused, cũng chưa có HTTP handler nào nhận. Nếu handler trả 503, chắc chắn backend đã nhận request đó.

**LoadBalancer selection** và **HTTP transport attempt** có thể không theo quan hệ một-một: một số tầng retry có thể giữ instance cũ hoặc thực hiện lại phía dưới LoadBalancer. Vì vậy cần đo cả selected instance lẫn tổng received ở A/B thay vì đo mỗi biến.

## 3. Ma trận lỗi và nơi đặt assertion

| Failure window | Kết quả ở caller | Backend handler có được gọi? | Assertion hữu ích |
|---|---|---|---|
| Không có instance | Lỗi LoadBalancer hoặc response tổng hợp tùy integration | Không | Backend count = 0 |
| Cổng không lắng nghe | Connect exception/refused | Không | Backend count = 0 |
| Handler trả HTTP 503 | Exception/status 503 | Có | Counter tăng một cho mỗi request thực nhận |
| Handler trả 400 | Exception/status 400 | Có | Counter = 1 nếu policy không retry |
| Handler trả 503, 503, 200 | Thành công sau retries | Có cả ba | Counter tổng = 3 |
| Handler trả 503 liên tục | Lỗi khi hết budget | Có từng attempt tới server | Count không vượt maxAttempts của lab |
| Server commit rồi response mất | Read timeout/reset | Có | Counter có thể tăng, số commit cần đo riêng |
| WebClient chưa subscribe | Không có I/O | Không | Counter = 0 |
| Gateway tự retry | Caller có thể chỉ thấy một call | Backend có thể nhận nhiều | Counter tại gateway và backend |

Phân biệt thêm HTTP `503` thực sự do backend trả với một lỗi `503` được tạo ở gateway/LoadBalancer khi không còn instance: **status trùng không đồng nghĩa nguồn phát ra trùng**.

## 4. Bộ kiểm thử phải chứng minh điều gì?

Một policy có giới hạn phải thỏa cả các trường hợp:

1. **Phục hồi:** hai lần `503` rồi một `200` làm caller thành công ở attempt thứ ba; backend nhận đúng ba requests khi cả ba đến handler.
2. **Dừng:** backend luôn `503`; caller dừng đúng `maxAttempts`, không lặp vô hạn.
3. **Không retry lỗi không phù hợp:** `400`, `401`, `403` hoặc lỗi validation theo contract không bị gửi lại máy móc.
4. **Phân biệt lỗi trước HTTP:** không có instance/connect refused không làm tăng backend handler count.
5. **Không nhân retry:** các tầng client, LoadBalancer, gateway, service mesh không cùng vượt budget tổng.
6. **Thao tác ghi:** số business side effects có thể phải là 1 ngay cả khi có nhiều requests thực nhận.

Unit test chỉ mock `RestClient.get()` hoặc `Mono.defer` chứng minh wrapper gọi lại bao nhiêu lần, **không chứng minh HTTP thực đến server**.

## 5. Chọn cấp độ test

| Cấp độ | Công cụ | Chứng minh được | Chưa chứng minh |
|---|---|---|---|
| Unit | Mockito, fake delegate, `Mono.defer` | Retry decision, số invocation | HTTP request tới backend |
| HTTP integration | JDK HttpServer, WireMock, MockWebServer | Method, path, status và handler count | LoadBalancer nếu client gọi host trực tiếp |
| LoadBalancer integration | `@LoadBalanced` + discovery + 2 servers | Service ID, chọn instance, tổng received | DB commit nếu chỉ mock handler |
| End-to-end fault | Hai tiến trình, DB, gateway/fault proxy | Network failures và side effects thực | Không bao quát mọi failure window chỉ bằng một lần chạy |

Lab sau dùng **JDK HttpServer** chạy hai cổng động trong JUnit. Mỗi server có counter tại handler, còn Retry wrapper ở client có counter attempts riêng. Do đó test mạnh hơn chỉ `verify(mock, times(3))`.

## 6. Thiết kế lab xác định với hai backend

Cả hai HTTP servers cung cấp `GET /api/items/42`:

~~~text
A: http://127.0.0.1:<cổng động A>
B: http://127.0.0.1:<cổng động B>

totalReceived = receivedA + receivedB
failFirst     = số lượt backend nhận đầu sẽ bị trả 503
forcedStatus  = nếu khác 0, mọi lượt nhận trả status đó
~~~

Khi `failFirst = 2`:

~~~text
Backend request #1 -> 503
Backend request #2 -> 503
Backend request #3 -> 200, body "OK"
~~~

Dùng **cổng động** tránh xung đột CI. Không assert chính xác A nhận lượt 1, B nhận lượt 2, vì điều đó thuộc chính sách chọn instance và concurrency, không phải yêu cầu retry.

### Dependencies

Ví dụ Gradle với Spring Boot/Spring Cloud BOM tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`com.sun.net.httpserver.HttpServer` có trong JDK; với dự án cấu hình JPMS đặc biệt, đảm bảo có module `jdk.httpserver`.

> Các đoạn mã trong bài là tài liệu hướng dẫn. Theo STEP 4, **chưa chạy Gradle/JUnit hoặc vòng Content QA**; các kết quả ở dưới là **kỳ vọng của kịch bản**, không phải số đo đã thực thi.

## 7. Một retry wrapper tường minh, chỉ retry 503

Để số lượng attempts của test dễ xác minh, dùng duy nhất một policy retry bên ngoài RestClient. Tắt retry tự động của LoadBalancer trong cấu hình test ở phần sau.

~~~java
package demo.retry;

import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestClient;

record CallResult(String body, int attempts) {}

final class BoundedCatalogCaller {

    private static final int MAX_ATTEMPTS = 3;
    private final RestClient client;

    BoundedCatalogCaller(RestClient client) {
        this.client = client;
    }

    CallResult fetchItem42() {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try {
                String body = client.get()
                    .uri("/api/items/42")
                    .retrieve()
                    .body(String.class);

                return new CallResult(body, attempt);
            } catch (HttpServerErrorException.ServiceUnavailable ex) {
                // Chỉ retry khi HTTP status là 503.
                if (attempt == MAX_ATTEMPTS) {
                    throw ex;
                }
            }
        }

        throw new IllegalStateException("Unreachable");
    }
}
~~~

Điểm thiết kế:

- `maxAttempts=3` có nghĩa **một lần đầu và tối đa hai retry**.
- Catch chỉ áp dụng cho HTTP 503 được `RestClient.retrieve()` chuyển thành `HttpServerErrorException.ServiceUnavailable`.
- HTTP 400, lỗi decode, connect refused hoặc không chọn được instance **không** được wrapper này retry.
- Không có backoff để test đếm request không phụ thuộc vào wall-clock sleep. Production cần backoff/jitter, deadline và cơ chế kiểm soát tải.
- Một wrapper không thể tự biết backend đã nhận requests; vì vậy ta sẽ đo riêng ở server.

Đoạn code này là **policy thử nghiệm**, không phải khuyến nghị retry tất cả 503 bất kể contract và SLO.

## 8. Khởi động hai HTTP servers với counter tại handler

Tạo file test class `BoundedRetryTest`. Các đoạn `9` và `10` tiếp tục được thêm **vào cùng class này**, không phải ba class khác nhau.

~~~java
package demo.retry;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
    classes = BoundedRetryTest.TestApp.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.main.web-application-type=none",
        "spring.cloud.loadbalancer.retry.enabled=false"
    }
)
@Execution(ExecutionMode.SAME_THREAD)
class BoundedRetryTest {

    private static final AtomicInteger totalReceived =
        new AtomicInteger();

    private static final AtomicInteger receivedA =
        new AtomicInteger();

    private static final AtomicInteger receivedB =
        new AtomicInteger();

    private static volatile int failFirst;
    private static volatile int forcedStatus;

    private static final HttpServer serverA =
        startServer(receivedA);

    private static final HttpServer serverB =
        startServer(receivedB);

    private static HttpServer startServer(AtomicInteger localCounter) {
        try {
            HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

            server.createContext("/api/items/42", exchange -> {
                int ordinal = totalReceived.incrementAndGet();
                localCounter.incrementAndGet();

                int status = forcedStatus != 0
                    ? forcedStatus
                    : ordinal <= failFirst ? 503 : 200;

                byte[] body = (status == 200 ? "OK" : "ERROR")
                    .getBytes(StandardCharsets.UTF_8);

                exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");

                exchange.sendResponseHeaders(status, body.length);

                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(body);
                }

                exchange.close();
            });

            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    // Tiếp tục với discovery, bean và test methods ở dưới.
}
~~~

**Lý do đặt counter ở handler:** `totalReceived.incrementAndGet()` được thực hiện sau khi HTTP server đã tiếp nhận request đến đúng route; attempt không đến backend sẽ không làm tăng counter. `ordinal` là thứ tự **handler thực nhận** trong lab, không phải attempt number do caller tự khai.

Hai server cùng JVM chia sẻ `totalReceived` để tạo lỗi đầu vào có thứ tự ổn định. Trong production, replica độc lập không chia sẻ một biến Java như vậy.

## 9. Đăng ký hai URI động vào SimpleDiscoveryClient

Bổ sung các method vào `BoundedRetryTest`:

~~~java
@DynamicPropertySource
static void discovery(DynamicPropertyRegistry registry) {
    registry.add(
        "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri",
        () -> "http://127.0.0.1:" + serverA.getAddress().getPort()
    );

    registry.add(
        "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri",
        () -> "http://127.0.0.1:" + serverB.getAddress().getPort()
    );
}

@BeforeEach
void resetBackendState() {
    totalReceived.set(0);
    receivedA.set(0);
    receivedB.set(0);
    failFirst = 0;
    forcedStatus = 0;
}

@AfterAll
static void stopServers() {
    serverA.stop(0);
    serverB.stop(0);
}
~~~

Cấu hình `@DynamicPropertySource` được Spring Test đưa vào context trước khi các bean discovery bắt đầu chạy. `@Execution(ExecutionMode.SAME_THREAD)` giúp tránh hai test methods trong class cùng thay bộ đếm nếu ứng dụng bật JUnit parallel execution.

Không dùng cổng cố định `18081` và `18082` trong test này; môi trường CI có thể đang sử dụng các cổng đó. Không gọi `Thread.sleep` chỉ để đợi counter thay đổi: test đồng bộ sẽ chờ response/exception từ RestClient trước khi assert.

## 10. Bean RestClient dùng Spring Cloud LoadBalancer

Bổ sung vào cùng class `BoundedRetryTest`:

~~~java
@Autowired
BoundedCatalogCaller caller;

@SpringBootConfiguration
@EnableAutoConfiguration
static class TestApp {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient catalogClient(
        @Qualifier("loadBalancedBuilder")
        RestClient.Builder builder
    ) {
        return builder.baseUrl("http://catalog-service").build();
    }

    @Bean
    BoundedCatalogCaller boundedCaller(RestClient catalogClient) {
        return new BoundedCatalogCaller(catalogClient);
    }
}
~~~

Như vậy caller không gọi trực tiếp các port động. Nó gửi tới service ID `catalog-service`, lấy danh sách instance qua `SimpleDiscoveryClient` rồi để Spring Cloud LoadBalancer chọn một endpoint thực.

**Lưu ý điều kiện của lab:** `spring.cloud.loadbalancer.retry.enabled=false` được đặt trong `@SpringBootTest` để tránh Spring Cloud retry cùng lúc với vòng lặp tường minh. Ngoài ra, test không nên có gateway/service mesh retry ẩn. Khi chạy trên version Spring cụ thể, cần xác minh các bean đã được auto-configured như dự kiến.

Đừng dùng `RestClient.create("http://catalog-service")` để thay bean được đánh dấu `@LoadBalanced`: client đó có thể cố phân giải tên logic qua DNS và không sử dụng supplier/LoadBalancer của module.

## 11. Ba test tự động cốt lõi

Các method sau cũng đặt **trong cùng `BoundedRetryTest`**, sử dụng state và bean đã khai báo.

### 11.1. Hai lần 503 rồi thành công

~~~java
@Test
void retriesTwiceThenSucceedsWithThreeBackendReceipts() {
    failFirst = 2;

    CallResult result = caller.fetchItem42();

    assertThat(result.body()).isEqualTo("OK");
    assertThat(result.attempts()).isEqualTo(3);

    assertThat(totalReceived.get()).isEqualTo(3);
    assertThat(receivedA.get() + receivedB.get()).isEqualTo(3);
}
~~~

Test chứng minh trong thiết lập cụ thể: một operation, ba HTTP attempts, backend thực nhận ba request (không chỉ mock bị gọi ba lần), hai response `503` và response cuối `200`.

### 11.2. Lỗi liên tục phải dừng ở attempt thứ ba

~~~java
@Test
void stopsAfterThreeAttemptsWhenBackendAlwaysReturns503() {
    failFirst = 100;

    assertThatThrownBy(caller::fetchItem42)
        .isInstanceOf(
            HttpServerErrorException.ServiceUnavailable.class
        );

    assertThat(totalReceived.get()).isEqualTo(3);
    assertThat(receivedA.get() + receivedB.get()).isEqualTo(3);
}
~~~

Test này phát hiện retry vượt giới hạn. Chỉ test “503, 503, 200” **không phát hiện** vòng lặp vô hạn nếu backend luôn thành công ở request thứ ba.

### 11.3. HTTP 400 không được retry

~~~java
@Test
void doesNotRetryBadRequest() {
    forcedStatus = 400;

    assertThatThrownBy(caller::fetchItem42)
        .isInstanceOf(HttpClientErrorException.BadRequest.class);

    assertThat(totalReceived.get()).isEqualTo(1);
}
~~~

HTTP 400 đi qua handler một lần và bị `RestClient.retrieve()` chuyển thành exception. Wrapper của ta chỉ bắt 503 nên dừng ngay.

| Test | Backend response sequence | Expected outcome | Backend received |
|---|---|---|---:|
| Retry phục hồi | 503 → 503 → 200 | Success ở attempt 3 | **3** |
| Retry hết budget | 503 → 503 → 503 | Throw 503 | **3** |
| Không retry 400 | 400 | Throw 400 | **1** |

**Đây là kỳ vọng từ cấu hình test; chưa phải kết quả JUnit đã chạy trong STEP 4.** Thứ tự request được mô tả theo tổng counter, không khẳng định thứ tự A/B. Nếu muốn kiểm thử thuật toán Round Robin thì đó là một bộ test khác với topology và concurrency được kiểm soát riêng.
## 12. Không có ServiceInstance: backend nhận 0 request

Nếu `ServiceInstanceListSupplier` trả danh sách rỗng cho service ID, Spring Cloud LoadBalancer không thể định tuyến request đến hai server trong lab. Đây là trường hợp khác hoàn toàn với việc backend trả HTTP 503.

~~~text
business operation      = 1
candidate instances     = 0
successful selection    = 0
backend received total  = 0
actual backend HTTP 503 = 0
~~~

Trong một test riêng, có thể tạo RestClient từ **builder được LoadBalancer quản lý** nhưng dùng service ID chưa đăng ký:

~~~java
// Đoạn minh họa: inject RestClient.Builder có @LoadBalanced.
RestClient missingClient = loadBalancedBuilder
    .baseUrl("http://missing-service")
    .build();
~~~

Gọi `missingClient.get().uri("/api/items/42")` sẽ thất bại ở bước phân giải instance theo cách tích hợp cụ thể; **không hardcode rằng mọi phiên bản đều ném cùng một class exception**. Assertion quan trọng:

- Backend A và B **không có request mới**.
- Service ID `missing-service` không có ứng viên.
- Failure được phân loại là **no-instance**, không phải “catalog backend thật đã trả 503”.

Một số integration có thể biểu diễn no-instance bằng exception hoặc response lỗi được tạo ở tầng LoadBalancer; chỉ từ HTTP status cuối cùng chưa biết được nguồn gốc.

## 13. Connect refused: attempts có thể lớn hơn received

Giả sử registry vẫn có bản sao B nhưng process B đã dừng. Nếu LoadBalancer chọn B, TCP connect có thể thất bại **trước khi HTTP handler được gọi**:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant LB as LoadBalancer
    participant A as Backend A
    participant B as Port B không lắng nghe

    C->>LB: Attempt 1
    LB-->>C: Chọn B
    C-xB: TCP connect refused
    Note over B: HTTP handler received = 0
    C->>LB: Attempt 2 (nếu retry)
    LB-->>C: Có thể chọn A
    C->>A: GET /api/items/42
    A-->>C: 200 OK
    Note over C: Attempts = 2; backend received = 1
~~~

Không dùng assertion `backendReceived == maxAttempts` cho mọi lỗi. Nếu muốn test ổn định, tạo một server hoặc fault proxy có thể điều khiển cổng/connection lifecycle; đừng giả định một cổng “có vẻ trống” trên máy CI sẽ không bị tiến trình khác sử dụng.

Khi instance B chết, retry **có thể** chọn A nếu các supplier và chính sách retry cho phép; không có bảo đảm retry luôn đổi sang instance khác.

## 14. Cấu hình retry của Spring Cloud LoadBalancer cần được test thực

Spring Cloud LoadBalancer cung cấp những thuộc tính phổ biến:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retryable-status-codes:
          - 503
        retry-on-all-operations: false
~~~

**Không áp dụng YAML này trong cùng bài test dùng `BoundedCatalogCaller` ở phần 7–11**: những test đó đã bật retry tường minh và đặt `spring.cloud.loadbalancer.retry.enabled=false` để đo một tầng duy nhất.

| Thuộc tính | Mục đích |
|---|---|
| `retry.enabled` | Bật/tắt cơ chế retry của LoadBalancer khi dependency/integration phù hợp |
| `max-retries-on-same-service-instance` | Số retry trên instance đã chọn, có semantics theo từng instance |
| `max-retries-on-next-service-instance` | Số lần thử lại có lựa chọn instance kế tiếp |
| `retryable-status-codes` | Các HTTP status đủ điều kiện retry |
| `retryable-exceptions` | Các exception đủ điều kiện retry |
| `retry-on-all-exceptions` | Điều chỉnh phạm vi exception được retry |
| `retry-on-all-operations` | Cho phép retry cả thao tác ngoài GET; phải xét idempotency |
| `retry.backoff.*` | Backoff và jitter trong những integration hỗ trợ |

**Đừng tính số backend requests chỉ bằng công thức `1 + same + next`** mà không đọc semantics theo instance, version và điều kiện lỗi. Một attempt có thể bị từ chối trước khi tới backend; request có thể không thuộc method được retry; retry-aware supplier có thể chọn cùng hoặc khác instance tùy danh sách còn lại.

Tài liệu Spring Cloud Commons mô tả retry cho non-reactive `RestTemplate` với Spring Retry trên classpath và retry reactive của `WebClient`; RestClient, Feign và các transport có tích hợp/điều kiện riêng tùy release train. **Chỉ thấy thuộc tính `enabled=true` không chứng minh retry đã thực thi**.

Khi kiểm thử một cơ chế retry framework thật:

1. Chọn **một HTTP client implementation** và một Spring Cloud release train cụ thể.
2. Kiểm tra dependency/bean thực sự kích hoạt retry.
3. Tắt retry ở các lớp khác để không nhân attempts.
4. Cố ý cho backend trả 503, rồi đo số request thực nhận.
5. Ghi instance được chọn cho từng attempt nếu mục tiêu là xác minh same/next instance.
6. Kiểm tra lỗi ngoài allowlist, POST khi `retry-on-all-operations=false` và hết budget.
7. Kiểm tra cả response lỗi và lỗi trước khi có HTTP response.

Tài liệu tham khảo: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html và https://docs.spring.io/spring-cloud-commons/reference/configprops.html.

## 15. Retry chồng tầng có thể nhân số requests

Giả sử wrapper nghiệp vụ cho tối đa **3 attempts**, trong khi HTTP client nền còn cho tối đa **2 sends cho mỗi attempt wrapper**:

~~~text
business wrapper: tối đa 3 lần gọi client
    mỗi lần gọi: transport thử gửi tối đa 2 lần
    hệ quả xấu nhất theo giả định này: 3 × 2 = 6 sends
~~~

~~~mermaid
flowchart TB
    O["1 operation"] --> W["Wrapper: tối đa 3 client calls"]
    W --> C1["Client call #1"]
    W --> C2["Client call #2"]
    W --> C3["Client call #3"]
    C1 --> S1["Transport retries ≤ 2 sends"]
    C2 --> S2["Transport retries ≤ 2 sends"]
    C3 --> S3["Transport retries ≤ 2 sends"]
    S1 --> B["Backend"]
    S2 --> B
    S3 --> B
~~~

Nếu gateway hoặc service mesh cũng retry, số backend requests có thể tăng thêm. Với mỗi lớp, cần phân biệt “retry” với “attempt”, và khi tính số gửi phải cộng cả lần thử ban đầu. Trong production, cách tính tổng còn phụ thuộc loại lỗi và quyền retry của mỗi lớp.

**Một policy chỉ an toàn khi tổng ngân sách retry trên cả đường đi nằm trong kiểm soát**, không phải khi từng component có `maxRetries` riêng. Test kết quả cuối 200 có thể bỏ sót retry storm; counter ở backend mới giúp phát hiện.

## 16. WebClient: retry subscriptions chưa chứng minh backend requests

Với WebClient, `retryWhen` sẽ resubscribe khi publisher phát lỗi được policy chấp nhận.

Unit test kiểm tra số subscription:

~~~java
import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

import static org.assertj.core.api.Assertions.assertThat;

class ReactorRetryUnitTest {

    @Test
    void retriesTwiceThenCompletes() {
        AtomicInteger subscriptions = new AtomicInteger();

        Mono<String> operation = Mono.defer(() -> {
            int attempt = subscriptions.incrementAndGet();

            if (attempt <= 2) {
                return Mono.error(
                    new IOException("temporary network failure")
                );
            }

            return Mono.just("OK");
        }).retryWhen(
            Retry.max(2)
                .filter(ex -> ex instanceof IOException)
        );

        StepVerifier.create(operation)
            .expectNext("OK")
            .verifyComplete();

        assertThat(subscriptions.get()).isEqualTo(3);
    }
}
~~~

**Không có HTTP trong ví dụ này.** Kết quả `subscriptions=3` chứng minh chỉ logic resubscribe của Reactor, không chứng minh có ba requests đã vào backend.

Để kiểm chứng giao tiếp thật, dùng WebClient `@LoadBalanced` tới hai server của lab, tắt retry framework khác và áp dụng:

~~~java
Mono<String> result = catalogWebClient.get()
    .uri("http://catalog-service/api/items/42")
    .retrieve()
    .bodyToMono(String.class)
    .retryWhen(
        Retry.max(2).filter(error ->
            error instanceof
                org.springframework.web.reactive.function.client
                    .WebClientResponseException.ServiceUnavailable
        )
    );
~~~

Sau `StepVerifier.create(result).expectNext("OK").verifyComplete()`, đọc counters tại backend. Trình tự “503, 503, 200” trong test server giúp liên kết subscription với **request thật**. Nhưng một lần resubscribe không bảo đảm lần retry được gửi tới instance khác.

Với `Mono.timeout`, tín hiệu có thể là `TimeoutException`, không phải `WebClientResponseException`. Test phải dùng lỗi thực tế theo connector. Nếu chưa subscribe, WebClient chưa thực hiện request; đọc counter trước subscription sẽ thấy 0.

## 17. OpenFeign: phải xác minh Retryer và ErrorDecoder đang dùng

Ví dụ interface:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {
    @GetMapping("/api/items/42")
    String getItem42();
}
~~~

Spring Cloud OpenFeign có thể cấu hình mặc định `Retryer.NEVER_RETRY` trong một số release train, khác hành vi mặc định của Feign core. `ErrorDecoder` có thể chuyển HTTP 503 thành loại exception khác và làm thay đổi eligibility của retry.

Do đó test Feign cần:

- Xác nhận `Retryer` áp dụng cho đúng client/service ID.
- Xác nhận HTTP transport thực tế (HC5/OkHttp hoặc transport khác).
- Kiểm tra response 503 có đi qua retry path dự định hay không.
- Đếm request thực ở backend A/B chứ không chỉ verify Feign proxy invocation.
- Kiểm tra HTTP 400 hoặc 404 không bị retry sai.
- Phân biệt Feign có `url` cố định (có thể bypass LB) với `name` dùng service ID.
- Tắt wrapper retry ngoài Feign nếu đang đo riêng Retryer.

Không thể kết luận “Feign tự retry ba lần” chỉ từ `@FeignClient`. Số requests phải có bằng chứng tại backend stub.

## 18. HTTP 429, Retry-After và deadline tổng

HTTP status chỉ là một điều kiện đầu vào; không nên retry mọi status giống nhau.

| Response hoặc lỗi | Cần kiểm thử | Ý nghĩa |
|---|---|---|
| 503 tạm thời | 503, 503, 200 | Phục hồi trong budget |
| 503 liên tục | Nhiều 503 | Dừng đúng số attempts |
| 429 + `Retry-After` | 429, sau đó 200 | Cân nhắc chờ theo header và deadline |
| 400/401/403 | Một response | Không retry cùng input/credentials máy móc |
| 404 theo contract | Một response | Không có resource hoặc route sai |
| 409 idempotency conflict | Một response | Sửa sử dụng key/body thay vì retry |
| 500 sau side effect | Có response lỗi | Có thể đã commit, outcome cần xác minh |
| Read timeout | Không nhận đủ response | Có thể phải xử lý UNKNOWN với POST |

Nếu `Retry-After` là 120 giây nhưng deadline caller chỉ còn 2 giây, policy phải dừng hoặc trả trạng thái phù hợp thay vì chờ quá SLO.

Số attempts thực tế có thể **nhỏ hơn maxAttempts** do deadline tổng hoặc circuit breaker. Test giới hạn cần đảm bảo **không vượt trần**, không ép mọi lỗi phải retry đến đủ trần.

## 19. Timeout sau khi backend commit: tách received khỏi side effects

Với thao tác ghi như POST tạo reservation, backend có thể lưu thành công rồi response bị mất. Caller chỉ biết timeout, có thể retry sang instance khác.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant LB as LoadBalancer
    participant A as Instance A
    participant DB as Shared DB
    participant B as Instance B

    C->>LB: POST operation K, attempt 1
    LB-->>C: Chọn A
    C->>A: Idempotency-Key=K
    A->>DB: COMMIT reservation #101
    A--xC: Response bị mất
    Note over C: Outcome UNKNOWN
    C->>LB: Retry same K, attempt 2
    LB-->>C: Có thể chọn B
    C->>B: POST key=K
    B->>DB: Tra cứu shared key K
    DB-->>B: Đã COMMITTED #101
    B-->>C: Trả biên nhận #101
~~~

Các assertion không được gộp:

~~~text
logicalOperations = 1
httpAttempts      = số lần thực sự thử
backendReceived   = tổng handler invocation across replicas
businessWrites(K) = 1
idempotencyKey    = cùng K trên mọi attempt
~~~

**Backend nhận hai POST không có nghĩa đã tạo hai bản ghi.** Ngược lại, nếu mỗi instance chỉ có in-memory map riêng, retry sang instance khác có thể tạo hai bản ghi. Muốn chứng minh idempotency nhiều replica, test phải dùng shared durable store với unique constraint/transaction hoặc cơ chế tương đương.

Read timeout, connection reset hay HTTP 504 không chứng minh server đã rollback. Khi outcome chưa xác định, dùng operation ID/key và endpoint tra cứu trạng thái trước khi gửi lại một ý định nghiệp vụ mới.

## 20. Hai instance: kiểm tra tổng count trước, phân phối sau

Giả sử:

~~~text
receivedA = 2
receivedB = 1
total     = 3
~~~

Nếu mục tiêu là **retry budget**, assertion thiết yếu trong lab là tổng `total=3`. Việc `A=2, B=1` không nên thành một assertion cứng khi bộ chọn, sức khỏe instance, retry-aware supplier hoặc concurrency có thể thay đổi thứ tự.

Nếu mục tiêu riêng là kiểm thử **Round Robin**, hãy cố định danh sách ứng viên, trạng thái health, số lượng callers và thứ tự thực hiện. Đó là một **bộ test thuật toán chọn instance**, không nên trộn lẫn với kiểm thử retry.

Khi có retry chuyển instance, phải cộng counter từ **tất cả replicas có thể được chọn**, không chỉ server đầu tiên. Nếu backend còn gateway/sidecar, cần đo ở từng hop để biết request đã đi bao xa.

## 21. WireMock, MockWebServer và fault proxy

JDK HttpServer tạo một lab tự chứa; trong dự án thật có thể chọn:

- **WireMock:** scenario 503 → 503 → 200, kiểm tra số lần HTTP path/method/header cụ thể được stub server nhận.
- **MockWebServer:** enqueue các response và đọc `RecordedRequest`; hữu ích để quan sát request chính xác.
- **Testcontainers:** chạy backend, registry và database gần môi trường triển khai, kiểm thử across process.
- **Toxiproxy** hoặc fault proxy tương đương: tạo connect failures, latency, reset hoặc mất response có kiểm soát.

Ví dụ khi đã có `WireMockServer` được khởi động và stub đúng endpoint:

~~~java
// Minh họa DSL: cần WireMock dependencies và imports tương ứng.
wireMock.verify(
    3,
    getRequestedFor(urlEqualTo("/api/items/42"))
);
~~~

Phép đếm này chứng minh **WireMock nhận ba GET tới path đó**. Nếu caller gọi trực tiếp WireMock URL, nó **không tự chứng minh** LoadBalancer chọn instance theo service ID; cần thêm một integration test qua `@LoadBalanced` hoặc Feign.

## 22. Observability: operation ID và attempt ID

Một operation cần được liên kết xuyên các attempts và instances:

| Trường | Ý nghĩa | Nguồn |
|---|---|---|
| `operationId` | Một ý định nghiệp vụ | Caller |
| `attemptNumber` | Attempt thứ mấy | Retry wrapper |
| `serviceId` | Downstream logic | LB |
| `selectedInstance` | Instance được chọn | LB/trace |
| `retryReason` | Điều kiện nào kích hoạt retry | Retry policy |
| `httpStatus` | Response đã nhận | Client/backend |
| `exceptionCause` | Connect, timeout, decode... | Client |
| `backendReceivedAt` | Handler bắt đầu nhận | Backend |
| `sideEffectId` | Transaction/result đã commit | DB/ledger |
| `remainingDeadlineMs` | Ngân sách còn lại | Caller |
| `dedupOutcome` | NEW/REPLAY/CONFLICT | Backend idempotency |

Ví dụ log mong muốn:

~~~text
caller op=op42 attempt=1 service=catalog-service selected=A
backend-A op=op42 received=true status=503
caller op=op42 retry=1 reason=HTTP_503
caller op=op42 attempt=2 service=catalog-service selected=B
backend-B op=op42 received=true status=503
caller op=op42 retry=2 reason=HTTP_503
caller op=op42 attempt=3 service=catalog-service selected=A
backend-A op=op42 received=true status=200
caller op=op42 outcome=SUCCESS attempts=3
~~~

Đây là format minh họa, không phải log mặc định của Spring Cloud LoadBalancer. Không đưa operation ID/idempotency key raw vào metric tags có cardinality cao; dùng logs/traces có kiểm soát và metrics tổng hợp theo service, status và retry reason. Không log Authorization hoặc payload nhạy cảm.

## 23. Những lỗi test retry thường gặp

1. Chỉ assert response cuối là 200, không đếm backend thực nhận.
2. Đếm mock invocation rồi coi đó là số HTTP requests.
3. Đếm ở một instance khi LoadBalancer có thể đổi sang instance khác.
4. Bật cùng lúc retry của wrapper, LoadBalancer, Feign, gateway hoặc mesh.
5. Nhầm `maxAttempts` với `maxRetries`, lệch một lần gửi.
6. Cố định thứ tự A/B dù topology/concurrency không được khóa.
7. Dùng connect refused nhưng mong backend handler count tăng.
8. Không test 503 kéo dài, nên không phát hiện retry vượt giới hạn.
9. Retry mọi HTTP 4xx, kể cả validation/authentication/conflict.
10. Dùng `Thread.sleep` hoặc cổng cố định khiến test flaky trên CI.
11. Không reset/cô lập counter giữa các test hoặc bật parallel trên shared state.
12. Kiểm thử POST mà không đếm business writes.
13. Tạo idempotency key mới cho mỗi retry của cùng operation.
14. Không có deadline tổng; tổng thời gian có thể tăng qua nhiều attempts.
15. Nhầm no-instance với 503 do backend/gateway phát ra.
16. Quên subscribe `Mono`, khiến WebClient chưa gửi request.
17. Chỉ đo requests ở gateway, không đo backend cuối.
18. Health probes làm nhiễu counter nếu không lọc theo path/method.
19. Không kiểm tra retry configuration thật của client/version đang chạy.
20. Không có cơ chế dừng test khi server/fault proxy bị treo.

## 24. Checklist đưa test vào CI

- Định nghĩa rõ **một business operation**, một attempt và tổng retries được phép.
- Chứng minh success-on-first-attempt, 503 rồi success, 503 kéo dài và 400 không retry.
- Có assertion **server handler count** cho lỗi 503 được tạo tại backend.
- Tách counter caller attempts, LB selections, backend receives và business writes khi cần.
- Tắt các tầng retry ngoài phạm vi đang test hoặc đặt budget hệ thống chung.
- Đảm bảo client gọi **service ID qua LoadBalancer** chứ không bypass bằng URL trực tiếp.
- Dùng cổng động, state test cô lập và không dựa vào sleep/timing tùy ý.
- Tạo đúng loại fault: connect failure, response timeout, HTTP status, no-instance.
- Với POST, cùng idempotency key qua attempts và side effect chỉ được commit theo contract.
- Với WebClient, có subscription và await completion; với Feign, kiểm tra Retryer/ErrorDecoder.
- Khi topology có nhiều instance, cộng backend counters trên tất cả instances.
- Có log/trace correlation, retry reason, selected instance và timeout cause an toàn.
- Đặt timeout cho bản thân test runner, không để một lần lỗi treo cả CI.
- Ghi tên assertion chính xác là **số requests backend handler nhận**, không nhãn mơ hồ “số gửi”.

## 25. Tổng kết

**Kiểm thử retry đúng không chỉ là thấy response cuối cùng thành công.** Cần chứng minh policy **dừng khi hết ngân sách**, **chỉ retry lỗi đủ điều kiện** và kiểm tra **số HTTP requests backend thực sự nhận** tại đúng ranh giới. Lab `BoundedRetryTest` dùng hai HTTP servers, lỗi `503` có kiểm soát và counter trong handler để xác minh trường hợp xác định: **503 → 503 → 200** tạo ba requests thực nhận, **503 liên tục** dừng sau ba attempts, còn **400** chỉ tới backend một lần.

Với Spring Cloud LoadBalancer, một attempt có thể thất bại ở discovery, chọn `ServiceInstance` hoặc transport trước khi tới server. RestClient, WebClient và OpenFeign có những cơ chế retry/exception khác nhau, nên cần kiểm tra tích hợp thực, tránh retry chồng tầng, và tách **received requests** khỏi **committed side effects** đối với thao tác ghi. Khi có đủ bằng chứng cho **logical operation, HTTP attempt, LoadBalancer selection, backend receipt và kết quả nghiệp vụ**, retry mới được kiểm soát như một cơ chế tăng độ ổn định thay vì nguồn gây quá tải hoặc ghi trùng.

## Tài liệu tham khảo

- Spring Cloud Commons – Common Abstractions / Retrying Failed Requests: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Spring Cloud Commons – Configuration Properties: https://docs.spring.io/spring-cloud-commons/reference/configprops.html
- Spring Cloud Commons – LoadBalancer: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html
- Spring Framework – RestClient: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Reactor Core – Error Handling / Retry: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html



