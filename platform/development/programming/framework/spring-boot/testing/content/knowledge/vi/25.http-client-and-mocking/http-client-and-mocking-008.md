# Spring Boot Testing: Fallback, circuit breaker và tránh gọi lặp ngoài dự kiến

## 1. Bài toán và tiêu chí hoàn thành

Ứng dụng Spring Boot thường phải gọi một dịch vụ HTTP bên ngoài: báo giá, vận chuyển, thanh toán, kiểm tra tồn kho hoặc thông tin người dùng. Khi upstream trả 503, mất kết nối, lỗi định dạng response hay quá chậm, nhiều cơ chế có thể cùng xuất hiện: retry, circuit breaker, fallback, cache và HTTP client middleware.

Một bài test chỉ kiểm tra `result != null` là chưa đủ. Nó có thể PASS ngay cả khi ứng dụng gọi upstream ba lần thay vì một, tiếp tục gọi khi mạch OPEN, nuốt lỗi 404, hoặc fallback trả một giá trị giả khiến nghiệp vụ sai.

Bài này yêu cầu kiểm đồng thời:

1. **Kết quả**: trả đúng giá thật hoặc trạng thái degraded được xác định rõ.
2. **Circuit breaker**: chuyển trạng thái CLOSED → OPEN → HALF_OPEN → CLOSED/OPEN theo điều kiện.
3. **Remote attempts**: đúng **số HTTP request thực tế**, kể cả trường hợp **không được gọi lần nào**.
4. **Phân loại lỗi**: 5xx/lỗi mạng, 4xx, invalid body và lỗi lập trình không bị gom chung.
5. **Tính an toàn của fallback/retry**: không tạo request lặp ngoài chính sách hoặc side effect trùng.
6. **Tính ổn định của test**: không phụ thuộc `Thread.sleep()`, internet thật, thứ tự chạy hay trạng thái circuit breaker của test trước.

Ví dụ use case lấy giá sản phẩm `SKU-1` từ `GET /prices/SKU-1`. Nếu vendor trả giá 125.50, ứng dụng trả `REMOTE`. Nếu vendor không sẵn sàng, ứng dụng trả `UNAVAILABLE` **và amount=null**, không tự bịa giá 0. Nếu breaker đã OPEN, lời gọi mới dùng fallback **trước khi gửi HTTP**.

### Mục tiêu học tập

Bạn sẽ biết xây dựng test cho `RestClient`, `MockRestServiceServer` và Resilience4j; kiểm chính xác request count; hiểu failure rate/sliding window/half-open; kiểm lỗi 404 không bị fallback che; biết khi nào dùng WireMock/MockWebServer; nhận diện double retry do Spring AOP và HTTP client; thiết kế timeout, backoff, idempotency và observability.

## 2. Phân biệt các cơ chế resilience

| Cơ chế | Vai trò chính | Không tự đảm bảo |
| --- | --- | --- |
| Fallback | Trả kết quả thay thế hoặc trạng thái unavailable | Không giảm số HTTP requests nếu vẫn gọi upstream |
| Circuit breaker | Từ chối cuộc gọi mới khi dependency đã lỗi quá ngưỡng | Không tự dừng một HTTP attempt đang treo |
| Retry | Thực hiện lại transient failure theo giới hạn | Không ngăn duplicate side effects |
| Timeout | Giới hạn thời gian chờ theo client/operation | Không tự thay thế fallback hoặc retry |
| Bulkhead | Giới hạn số concurrent calls, cô lập resource | Không tự xác định upstream healthy |
| Rate limiter | Giới hạn tốc độ gọi | Không phải circuit breaker |
| Cache | Trả giá trị có thể đã lưu trước đó | Không bảo đảm dữ liệu còn mới/phù hợp |
| Idempotency key | Làm lặp request ghi an toàn hơn khi server hỗ trợ | Không giảm số network attempts |

Có ba con số riêng biệt:

- **Logical calls**: người dùng/use case gọi vào application bao nhiêu lần.
- **HTTP attempts**: client thật gửi lên upstream bao nhiêu requests.
- **Fallback invocations**: application trả kết quả dự phòng bao nhiêu lần.

Một logical call có thể tạo ba HTTP attempts vì retry, nhưng vẫn chỉ trả một kết quả. Ngược lại, breaker OPEN có thể tạo một fallback invocation mà không tạo HTTP attempt nào.

### 2.1 Sơ đồ đúng phạm vi

~~~text
Controller / scheduled worker / message consumer
     |
     +--> validate input, authentication, business policy
     |
     v
Application facade
     |
     +--> CircuitBreaker acquires permission
     |       |
     |       +-- OPEN -> CallNotPermittedException -> FALLBACK
     |       |
     |       +-- CLOSED / permitted HALF_OPEN
     |                    |
     |                    v
     |                Retry policy (nếu có)
     |                    |
     |                    v
     |                Spring RestClient
     |                    |
     |                    v
     |                HTTP upstream
     |                    |
     |                    +-- 200 / 404 / 429 / 503 / timeout
     |
     +--> classify outcome, record metrics, selective FALLBACK
     |
     v
Result có trạng thái rõ: REMOTE / UNAVAILABLE / STALE
~~~

**Quan trọng:** thứ tự `Retry` và `CircuitBreaker` có thể khác tùy sử dụng programmatic decorators hoặc Spring AOP aspects. Không lấy thứ tự annotation xuất hiện trong Java source làm bằng chứng thứ tự runtime.

## 3. Circuit breaker: trạng thái và ngưỡng

| State | Cho phép gọi upstream? | Hành vi |
| --- | --- | --- |
| `CLOSED` | Có | Ghi nhận failure/success/slow call metrics |
| `OPEN` | Không | Từ chối trước khi chạy protected supplier |
| `HALF_OPEN` | Chỉ một số probe | Cho phép thử phục hồi với giới hạn |
| `FORCED_OPEN` | Không | Trạng thái ép mở theo quản trị |
| `DISABLED` | Có | Không áp dụng state machine như bình thường |
| `METRICS_ONLY` | Có | Đo metrics, không chuyển OPEN vì ngưỡng |

Thông số thường gặp trong Resilience4j:

- `slidingWindowType`: `COUNT_BASED` (số cuộc gọi) hoặc `TIME_BASED` (cửa sổ thời gian).
- `slidingWindowSize`: kích thước cửa sổ.
- `minimumNumberOfCalls`: số mẫu tối thiểu trước khi tính tỷ lệ lỗi.
- `failureRateThreshold`: ngưỡng phần trăm failures để OPEN.
- `slowCallRateThreshold`, `slowCallDurationThreshold`: mở mạch vì quá nhiều cuộc gọi chậm.
- `waitDurationInOpenState`: thời gian phải đợi trước khi cho phép trạng thái HALF_OPEN.
- `permittedNumberOfCallsInHalfOpenState`: số probes được phép ở HALF_OPEN.
- `automaticTransitionFromOpenToHalfOpenEnabled`: có cần tự chuyển mà không chờ request mới không.

Ví dụ để test:

~~~text
slidingWindowType                  COUNT_BASED
slidingWindowSize                  2
minimumNumberOfCalls              2
failureRateThreshold              50%
permittedNumberOfCallsInHalfOpen  1
waitDurationInOpenState           10 minutes
~~~

Với **hai lời gọi đầu cùng lỗi 503**, breaker đạt đủ 2 mẫu và 100% failure rate → OPEN. Lời gọi thứ ba bị chặn và không sinh HTTP request mới. Với **một lỗi 503 đầu tiên**, breaker vẫn CLOSED vì chưa đủ `minimumNumberOfCalls=2`.

### 3.1 OPEN không có nghĩa hệ thống đã phục hồi

Mạch OPEN dùng để **giảm tải vào upstream đang hỏng**, không chứng minh upstream vẫn hỏng hoặc đã lành. Sau thời gian chờ, trạng thái HALF_OPEN cho một số probes. Probe thành công đủ điều kiện có thể đưa mạch về CLOSED; probe lỗi có thể mở mạch lại.

Đối với test logic, tránh `Thread.sleep(Duration...)`. Ta có thể dùng các phương thức Resilience4j `transitionToOpenState()` và `transitionToHalfOpenState()` để ép state **trong test**, rồi kiểm đúng request count. Production không nên dùng các phương thức này tùy tiện trong luồng business.

### 3.2 Số calls bị chặn phải được đo riêng

`CircuitBreaker.Metrics.getNumberOfNotPermittedCalls()` tăng khi lời gọi bị từ chối vì OPEN (hoặc giới hạn tương ứng). Đó **không phải** một HTTP 503 response từ server; server **chưa được gọi**.

Một bộ test đáng tin cần kiểm cả:

~~~text
breaker.state = OPEN
breaker.metrics.notPermitted = 1
HTTP attempts vẫn giữ nguyên
fallback result đúng contract
~~~

Nếu chỉ thấy fallback UNAVAILABLE, không thể biết HTTP vẫn bị gửi hay không.

## 4. Fallback: không phải catch Exception rồi bịa dữ liệu

Một policy an toàn cho API đọc giá:

| Điều kiện | Xử lý |
| --- | --- |
| 200 + body có amount hợp lệ | `Origin.REMOTE` và amount thật |
| 500/502/503/504 | Breaker failure, trả `UNAVAILABLE` |
| IOException/connect/read timeout | Breaker failure, trả `UNAVAILABLE` |
| OPEN/CallNotPermittedException | Fallback, **không gửi HTTP** |
| 200 nhưng amount null/âm | Validate payload trong protected call rồi fallback theo policy |
| 400/404 | Propagate hoặc map thành domain validation/not-found |
| 401/403 | Không che lỗi auth/permission bằng fallback |
| 429 | Có policy riêng cho `Retry-After`/rate limit |
| Bug không mong đợi | Không catch chung để che lỗi |

Trả **0.00** làm giá fallback có thể gây đơn hàng giá 0. Ví dụ dùng `amount=null` cộng trạng thái `UNAVAILABLE`, buộc caller không xem đó là giá hợp lệ.

Nếu fallback đọc cache last-known-good, kết quả nên có `origin=STALE`, `asOf` và TTL; giới hạn nghiệp vụ nào chấp nhận stale. Với thanh toán hoặc quyết định bảo mật, “giả thành công” thường nguy hiểm hơn trả lỗi tạm thời.

### 4.1 Fallback không được gọi lại cùng upstream

Anti-pattern:

~~~text
fetchPrice()
    -> upstream 503
    -> fallback()
         -> retry fetchPrice()  // cùng dependency bị lỗi
            -> upstream 503
            -> fallback()...
~~~

Fallback phải độc lập với đường failure hoặc có circuit breaker/timeout riêng nếu dựa vào dependency khác. Test `ExpectedCount.once()` có thể bắt trực tiếp việc fallback tạo request thứ hai.

### 4.2 Không dùng catch Exception chung chung

~~~java
// Anti-pattern: che cả 404, lỗi auth và bug lập trình.
try {
    return remote.fetch(sku);
} catch (Exception ignored) {
    return BigDecimal.ZERO;
}
~~~

Hãy bắt **loại exception thực sự được chấp nhận cho degradation**. Nếu application có `InvalidUpstreamPayload` riêng thì kiểm nó, không mặc định bỏ qua mọi lỗi JSON parse/coding.

## 5. Mock HTTP client thế nào cho đúng?

Có ba mức độ:

1. **Mockito mock service/port interface**: nhanh cho business logic, nhưng không chứng minh URL, HTTP method, headers, transport errors hoặc số HTTP requests rời khỏi adapter.
2. **Spring MockRestServiceServer**: thay request factory của `RestClient`/`RestTemplate` và cho phép `expect(once/times(N))`, status/body/error simulation. Không đi qua socket thật.
3. **WireMock hoặc OkHttp MockWebServer**: chạy một HTTP server trên localhost, client thực kết nối TCP; test request journal, delay, connection reset, redirect, compression và timeout tốt hơn.

Với chủ đề này, bài runnable dùng **`RestClient` + `MockRestServiceServer` + Resilience4j Core**. Nó kiểm request chính xác mà không gọi ra internet.

### 5.1 Bind vào đúng builder trước build()

~~~java
RestClient.Builder builder = RestClient.builder()
        .baseUrl("https://vendor.example.test");

MockRestServiceServer mockServer =
        MockRestServiceServer.bindTo(builder).build();

RestClient client = builder.build();
~~~

Nếu mock server bind vào Builder A nhưng code production nhận RestClient tạo từ Builder B, test có thể không kiểm được request thật, thậm chí truy cập network ngoài ý muốn.

### 5.2 Exact count

~~~java
mockServer.expect(
        ExpectedCount.once(),
        requestTo("https://vendor.example.test/prices/SKU-1"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                "{\"amount\":125.50}", MediaType.APPLICATION_JSON));

PriceResult actual = priceClient.getPrice("SKU-1");

mockServer.verify();
~~~

Đây là **mẫu minh họa có imports và setup ở test class phía dưới**. `ExpectedCount.once()` kiểm đúng một attempt. `ExpectedCount.times(2)` kiểm hai attempts. Đừng thay bằng `manyTimes()` chỉ vì test hiện tại fail: nó có thể che retry ngoài chính sách.

### 5.3 MockRestServiceServer không kiểm TLS/DNS/connection pool thật

Nó mock `ClientHttpRequestFactory`. Khi điều quan trọng là behavior socket, pool, redirect hoặc timeout, bổ sung WireMock/MockWebServer trên dynamic localhost port. Dùng chính request factory production trong test TCP; nếu không, bạn có thể bỏ sót retry ngầm của một HTTP client implementation.

## 6. Ví dụ chạy được Java 17+ / Spring Boot 3.5.x

Bộ ví dụ dùng **programmatic CircuitBreaker**, không cần Spring AOP hoặc ApplicationContext để chạy JUnit tests. Cách này giúp cô lập state và nhìn rõ số HTTP calls. Bài có hai Java source files, Gradle configuration và **10 phương thức JUnit Jupiter**.

~~~text
http-client-resilience-demo/
  settings.gradle
  build.gradle
  src/
    main/java/example/httpclient/PriceClient.java
    test/java/example/httpclient/PriceClientTest.java
~~~

### 6.1 settings.gradle

~~~groovy
rootProject.name = 'http-client-resilience-demo'
~~~

### 6.2 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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
    implementation 'io.github.resilience4j:resilience4j-circuitbreaker:2.3.0'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là file `build.gradle` dùng cho các tests của module client, với các phiên bản minh họa được cố định — **không tuyên bố là phiên bản mới nhất**. Spring starter-web mang `RestClient` và Jackson, starter-test mang JUnit Jupiter và `MockRestServiceServer`. Core Resilience4j không cần Boot AOP starter.

Project không khai báo `@SpringBootApplication` vì chỉ chạy component tests; lệnh `./gradlew test` là mục tiêu. Nếu muốn tạo executable Boot JAR, bổ sung main class/config hoặc biến module thành Java library đúng mục đích.

## 7. Production source: PriceClient.java

File `src/main/java/example/httpclient/PriceClient.java`:

~~~java
package example.httpclient;

import java.math.BigDecimal;
import java.util.Objects;
import java.util.regex.Pattern;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

public final class PriceClient {

    public enum Origin {
        REMOTE, UNAVAILABLE
    }

    public record PriceResult(
            String sku,
            BigDecimal amount,
            Origin origin) {
    }

    public record PricePayload(BigDecimal amount) {
    }

    public static final class InvalidUpstreamPayload
            extends RuntimeException {
        public InvalidUpstreamPayload(String message) {
            super(message);
        }
    }

    private static final Pattern VALID_SKU =
            Pattern.compile("[A-Z][A-Z0-9-]{0,19}");

    private final RestClient restClient;
    private final CircuitBreaker circuitBreaker;

    public PriceClient(
            RestClient restClient,
            CircuitBreaker circuitBreaker) {
        this.restClient = Objects.requireNonNull(restClient);
        this.circuitBreaker =
                Objects.requireNonNull(circuitBreaker);
    }

    public PriceResult getPrice(String sku) {
        if (sku == null
                || !VALID_SKU.matcher(sku).matches()) {
            throw new IllegalArgumentException("Invalid SKU");
        }

        try {
            return circuitBreaker.executeSupplier(() -> {
                PricePayload payload = restClient.get()
                        .uri("/prices/{sku}", sku)
                        .retrieve()
                        .body(PricePayload.class);

                if (payload == null
                        || payload.amount() == null
                        || payload.amount().signum() < 0) {
                    throw new InvalidUpstreamPayload(
                            "Missing or invalid amount");
                }

                return new PriceResult(
                        sku, payload.amount(), Origin.REMOTE);
            });

        } catch (HttpServerErrorException
                | ResourceAccessException
                | CallNotPermittedException
                | InvalidUpstreamPayload ex) {
            // Fallback KHÔNG gửi thêm HTTP request.
            return new PriceResult(
                    sku, null, Origin.UNAVAILABLE);
        }
    }
}
~~~

Giải thích:

- Validate SKU **trước** breaker và HTTP để lỗi input không làm circuit breaker chịu trách nhiệm.
- `retrieve()` mặc định ném subclass `RestClientException` trên 4xx/5xx.
- 5xx thường là `HttpServerErrorException`; lỗi request I/O thường là `ResourceAccessException`.
- 200 mà amount null/âm tạo `InvalidUpstreamPayload` **bên trong protected supplier**, để breaker ghi nhận lỗi.
- OPEN tạo `CallNotPermittedException` **trước khi gọi supplier**.
- Fallback chỉ trả `UNAVAILABLE`, `amount=null` và không thử lại upstream.
- 404 tạo `HttpClientErrorException`, **không được catch trong fallback**; caller xử lý theo domain policy.
- Không có Retry trong class này nên một logical CLOSED call có tối đa một HTTP attempt.

Trong production, circuit breaker nên được tạo **một lần cho cùng dependency** qua bean/registry. Nếu tạo breaker mới trong mỗi `getPrice()`, metrics không tích đủ để chuyển OPEN.

## 8. PriceClientTest.java: mười bài JUnit Jupiter

File `src/test/java/example/httpclient/PriceClientTest.java`:

~~~java
package example.httpclient;

import java.io.IOException;
import java.math.BigDecimal;
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.ExpectedCount.times;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class PriceClientTest {

    private static final String URL =
            "https://vendor.example.test/prices/SKU-1";

    private MockRestServiceServer server;
    private CircuitBreaker breaker;
    private PriceClient client;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://vendor.example.test");

        server = MockRestServiceServer.bindTo(builder).build();

        CircuitBreakerConfig config =
                CircuitBreakerConfig.custom()
                        .slidingWindowType(
                                CircuitBreakerConfig
                                        .SlidingWindowType.COUNT_BASED)
                        .slidingWindowSize(2)
                        .minimumNumberOfCalls(2)
                        .failureRateThreshold(50)
                        .permittedNumberOfCallsInHalfOpenState(1)
                        .waitDurationInOpenState(
                                Duration.ofMinutes(10))
                        .recordExceptions(
                                HttpServerErrorException.class,
                                ResourceAccessException.class,
                                PriceClient.InvalidUpstreamPayload.class)
                        .ignoreExceptions(
                                HttpClientErrorException.class)
                        .build();

        breaker = CircuitBreaker.of("pricing-test", config);
        client = new PriceClient(builder.build(), breaker);
    }

    @AfterEach
    void verifyExpectedHttpRequests() {
        server.verify();
    }

    @Test
    @DisplayName("200: một request và giá thật")
    void successExactlyOnce() {
        server.expect(once(), requestTo(URL))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"amount\":125.50}",
                        MediaType.APPLICATION_JSON));

        PriceClient.PriceResult result =
                client.getPrice("SKU-1");

        assertEquals(PriceClient.Origin.REMOTE, result.origin());
        assertEquals(0, result.amount()
                .compareTo(new BigDecimal("125.50")));
        assertEquals(CircuitBreaker.State.CLOSED,
                breaker.getState());
    }

    @Test
    @DisplayName("503 đầu tiên fallback nhưng chưa mở mạch")
    void firstServerFailureFallsBack() {
        server.expect(once(), requestTo(URL))
                .andRespond(
                        withStatus(HttpStatus.SERVICE_UNAVAILABLE));

        assertUnavailable(client.getPrice("SKU-1"));
        assertEquals(CircuitBreaker.State.CLOSED,
                breaker.getState());
        assertEquals(1,
                breaker.getMetrics().getNumberOfFailedCalls());
    }

    @Test
    @DisplayName("Hai 503 mở mạch, lần ba không gọi HTTP")
    void twoFailuresOpenAndThirdIsBlocked() {
        server.expect(times(2), requestTo(URL))
                .andRespond(
                        withStatus(HttpStatus.SERVICE_UNAVAILABLE));

        assertUnavailable(client.getPrice("SKU-1"));
        assertUnavailable(client.getPrice("SKU-1"));
        assertEquals(CircuitBreaker.State.OPEN,
                breaker.getState());

        // Thứ ba KHÔNG được phát HTTP.
        assertUnavailable(client.getPrice("SKU-1"));
        assertEquals(CircuitBreaker.State.OPEN,
                breaker.getState());
        assertEquals(1,
                breaker.getMetrics()
                        .getNumberOfNotPermittedCalls());
    }

    @Test
    @DisplayName("OPEN thủ công: zero HTTP calls")
    void openStateNeverInvokesRemote() {
        breaker.transitionToOpenState();

        // Không đăng ký server.expect(...).
        assertUnavailable(client.getPrice("SKU-1"));

        assertEquals(CircuitBreaker.State.OPEN,
                breaker.getState());
        assertEquals(1,
                breaker.getMetrics()
                        .getNumberOfNotPermittedCalls());
    }

    @Test
    @DisplayName("HALF_OPEN probe 200 -> CLOSED")
    void halfOpenRecoveryCloses() {
        breaker.transitionToOpenState();
        breaker.transitionToHalfOpenState();

        server.expect(once(), requestTo(URL))
                .andRespond(withSuccess(
                        "{\"amount\":125.50}",
                        MediaType.APPLICATION_JSON));

        PriceClient.PriceResult result =
                client.getPrice("SKU-1");

        assertEquals(PriceClient.Origin.REMOTE, result.origin());
        assertEquals(CircuitBreaker.State.CLOSED,
                breaker.getState());
    }

    @Test
    @DisplayName("HALF_OPEN probe 503 -> OPEN")
    void halfOpenFailureReopens() {
        breaker.transitionToOpenState();
        breaker.transitionToHalfOpenState();

        server.expect(once(), requestTo(URL))
                .andRespond(
                        withStatus(HttpStatus.SERVICE_UNAVAILABLE));

        assertUnavailable(client.getPrice("SKU-1"));
        assertEquals(CircuitBreaker.State.OPEN,
                breaker.getState());

        // Extra logical call bị từ chối, không có request thứ hai.
        assertUnavailable(client.getPrice("SKU-1"));
    }

    @Test
    @DisplayName("404 không bị fallback che")
    void notFoundIsPropagated() {
        server.expect(once(), requestTo(URL))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThrows(HttpClientErrorException.class,
                () -> client.getPrice("SKU-1"));

        assertEquals(CircuitBreaker.State.CLOSED,
                breaker.getState());
        assertEquals(0,
                breaker.getMetrics().getNumberOfFailedCalls());
    }

    @Test
    @DisplayName("Invalid SKU không gọi remote")
    void validationRejectsBeforeHttp() {
        assertThrows(IllegalArgumentException.class,
                () -> client.getPrice("../wrong"));

        assertEquals(CircuitBreaker.State.CLOSED,
                breaker.getState());
    }

    @Test
    @DisplayName("200 thiếu amount vẫn là upstream failure")
    void malformedPayloadIsRecorded() {
        server.expect(once(), requestTo(URL))
                .andRespond(withSuccess(
                        "{\"amount\":null}",
                        MediaType.APPLICATION_JSON));

        assertUnavailable(client.getPrice("SKU-1"));
        assertEquals(1,
                breaker.getMetrics().getNumberOfFailedCalls());
    }

    @Test
    @DisplayName("IOException ở transport có fallback")
    void ioFailureIsRecorded() {
        server.expect(once(), requestTo(URL))
                .andRespond(withException(
                        new IOException("connection reset")));

        assertUnavailable(client.getPrice("SKU-1"));
        assertEquals(1,
                breaker.getMetrics().getNumberOfFailedCalls());
    }

    private static void assertUnavailable(
            PriceClient.PriceResult result) {
        assertEquals(PriceClient.Origin.UNAVAILABLE,
                result.origin());
        assertEquals("SKU-1", result.sku());
        assertNull(result.amount());
    }
}
~~~

**Có 10 phương thức `@Test`.** Mỗi `@BeforeEach` tạo một mock server, một RestClient và một CircuitBreaker mới. Không dùng Spring context cache, không gọi vendor, không chờ thời gian thực, không phụ thuộc state từ test trước.

### 8.1 Bảng kỳ vọng

| Test | HTTP attempts | State cuối | Kết quả |
| --- | ---: | --- | --- |
| `successExactlyOnce` | 1 | CLOSED | REMOTE, amount 125.50 |
| `firstServerFailureFallsBack` | 1 | CLOSED | UNAVAILABLE, failedCalls=1 |
| `twoFailuresOpenAndThirdIsBlocked` | 2 cho 3 logical calls | OPEN | UNAVAILABLE, rejectedCalls=1 |
| `openStateNeverInvokesRemote` | 0 | OPEN | UNAVAILABLE |
| `halfOpenRecoveryCloses` | 1 | CLOSED | REMOTE |
| `halfOpenFailureReopens` | 1 cho 2 logical calls | OPEN | UNAVAILABLE |
| `notFoundIsPropagated` | 1 | CLOSED | HTTP client error được throw |
| `validationRejectsBeforeHttp` | 0 | CLOSED | IllegalArgumentException |
| `malformedPayloadIsRecorded` | 1 | CLOSED | UNAVAILABLE, failedCalls=1 |
| `ioFailureIsRecorded` | 1 | CLOSED | UNAVAILABLE, failedCalls=1 |

### 8.2 Vì sao assert metric chưa đủ?

`getNumberOfNotPermittedCalls()==1` chứng minh breaker từ chối một lần, nhưng nếu fallback lại gửi HTTP theo đường khác, remote attempts vẫn tăng. `MockRestServiceServer` cần verify zero **extra requests**.

Ngược lại, chỉ đếm zero requests khi OPEN mà không assert state cũng chưa đủ: có thể code vô tình bỏ luôn lời gọi remote vì validation/cache. Hai loại assertion hỗ trợ lẫn nhau.

### 8.3 Không dùng manyTimes()

`server.expect(manyTimes(), ...)` tạo điều kiện để retry thừa vẫn PASS. Khi business policy cho tối đa một attempt, dùng `once()`. Khi có retry hợp lệ hai attempts, dùng `times(2)`. Kiểm chính xác operation HTTP (method, URL, headers/body nếu quan trọng), không chỉ một counter ở facade.

## 9. Cách chạy và kết quả kỳ vọng

Linux/macOS:

~~~bash
./gradlew test --tests example.httpclient.PriceClientTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.httpclient.PriceClientTest
~~~

**Kỳ vọng:** JUnit Jupiter chạy 10 tests, tất cả PASS khi đúng phiên bản/dependencies và file paths nêu trên. `test` không cần khởi động HTTP server hay mạng ngoài. Đây là **kỳ vọng sau rà soát cấu trúc**, không phải log từ một lần chạy Gradle đã được xác nhận. Không cam kết stdout cụ thể; Gradle/IDE có thể ghi `BUILD SUCCESSFUL` và báo cáo trong `build/reports/tests/test/index.html`.

Nếu môi trường đang dùng Spring Boot 4.x hoặc Resilience4j release khác, kiểm starter names/Javadoc tương ứng; ví dụ này chủ đích dùng Boot 3.5.x và Resilience4j Core 2.3.0.

## 10. Vì sao không đặt @CircuitBreaker annotation ngay trong demo?

Programmatic API giúp test từng bước:

~~~java
CircuitBreaker breaker =
        CircuitBreaker.of("pricing-test", config);

return breaker.executeSupplier(
        () -> restClient.get().uri(...).retrieve().body(...));
~~~

Khi dùng annotation như `@CircuitBreaker(name="pricing", fallbackMethod="fallback")`, còn có Spring AOP proxy, bean lifecycle, aspect order, starter configuration và potential self-invocation. Mục tiêu của demo là **chứng minh HTTP attempt counts trước**, sau đó có thể bổ sung integration tests cho annotation wiring.

### 10.1 Fallback method signature khi dùng Resilience4j annotations

Mẫu ý tưởng:

~~~java
@CircuitBreaker(name = "pricing", fallbackMethod = "fallback")
public PriceResult find(String sku) {
    return remote.fetch(sku);
}

private PriceResult fallback(
        String sku, CallNotPermittedException ex) {
    return unavailable(sku);
}
~~~

Đây là **đoạn minh họa**, không thuộc source runnable: cần Resilience4j Spring Boot 3 starter, AOP support, imports, domain classes và bean nằm trong Spring context. Fallback thường phải có **các parameters gốc + một exception parameter cuối** và return type tương thích. Có thể có overload theo loại exception; Resilience4j chọn match cụ thể hơn.

Đừng dùng một fallback nhận `Exception` chung rồi vô tình che 404, bad credentials, invalid SKU và programming errors.

### 10.2 Cẩn thận với self-invocation

~~~java
@Service
class PricingFacade {
    public PriceResult outer(String sku) {
        return protectedCall(sku); // cùng bean, có thể bypass AOP proxy
    }

    @CircuitBreaker(name = "pricing")
    public PriceResult protectedCall(String sku) {
        // ...
    }
}
~~~

Đây là đoạn mô tả cơ chế proxy, không phải class trong demo. Với Spring proxy mode thông thường, gọi `this.protectedCall` không đi qua proxy nên breaker annotation có thể **không áp dụng**. Tách protected adapter sang bean khác hoặc dùng programmatic CircuitBreaker khi muốn boundary rõ.

### 10.3 Cấu hình mẫu cho starter (không dành cho Core demo)

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      pricing:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Đây là **YAML cho Resilience4j Spring Boot integration**, không được auto-load bởi `CircuitBreaker.of(...)` trong ví dụ Core. Nếu dùng annotation, tên `pricing` phải khớp cấu hình/registry instance và integration dependencies phải được khai báo đúng version.

## 11. Retry: nguồn chính gây request lặp ngoài dự kiến

Retry có thể đến từ nhiều nơi:

- Resilience4j `@Retry` ở service.
- Spring Retry `@Retryable` ở adapter.
- Feign Retryer hoặc SDK-specific middleware.
- Apache/JDK HTTP client automatic retry (tùy cấu hình).
- Spring Cloud LoadBalancer hoặc proxy/gateway.
- Code tự gọi lại trong catch/for/while.
- Message redelivery, duplicate subscriptions trong reactive code.

Một logical request có thể tạo N×M attempts nếu có **hai retryers chồng nhau**. Ví dụ service retry tối đa 3 lần và underlying SDK cũng retry 3 lần → một số nhánh lỗi có thể tạo **9 remote attempts**.

### 11.1 maxAttempts bao gồm lần đầu

Với nhiều retry libraries, `maxAttempts=3` nghĩa là **tối đa ba attempts**, không phải ba retries cộng thêm một attempt. Phải xác minh semantics của đúng library đang dùng, vì tên config khác nhau giữa frameworks.

### 11.2 Retry policy theo HTTP status

| Tình huống | Retry? | Lý do |
| --- | --- | --- |
| GET gặp 502/503, upstream transient | Có thể, có giới hạn | Idempotent read và hạ tầng có thể phục hồi |
| Connect timeout trước request | Có thể | Tùy transport và deadline |
| Read timeout | Cẩn trọng | Server có thể đã xử lý, dù client không nhận response |
| 429 | Theo Retry-After/quotas | Tránh làm upstream càng quá tải |
| 400 invalid input | Không | Retry nguyên input thường không sửa được |
| 401/403 | Không retry mù | Auth policy/refresh có kiểm soát |
| 404 | Thường không | Có thể ngoại lệ nếu eventual consistency có contract |
| POST payment/order | Không mặc định | Cần idempotency key và server-side dedupe |
| Pool exhausted | Không retry vô hạn | Có thể gây retry storm |

Retry cần có **backoff + jitter**, giới hạn attempts, overall deadline và phân loại lỗi. Đừng chỉ đặt timeout mỗi attempt rồi cho retry vô hạn.

### 11.3 Aspect order ảnh hưởng số attempts và breaker metrics

Resilience4j Spring Boot integration có default aspect order điển hình:

~~~text
Retry ( CircuitBreaker ( RateLimiter ( TimeLimiter ( Bulkhead ( Function ) ) ) ) )
~~~

Nếu Retry **bao ngoài** CircuitBreaker, mỗi attempt có thể được circuit breaker ghi nhận thành một event. Nhưng nếu fallback bên trong breaker đã bắt exception rồi trả kết quả bình thường, outer Retry có thể xem outcome thành công và **không retry**. Khi đảo thứ tự, breaker có thể ghi một logical call với nhiều attempts bên trong.

Đừng giả định aspect order theo **thứ tự chú thích trong Java**. Khi dùng `@Retry`/`@CircuitBreaker` cùng method, test bean được Spring proxy thật, verify HTTP attempts và breaker metrics. Resilience4j cung cấp các thuộc tính cấu hình `resilience4j.retry.retryAspectOrder` và `resilience4j.circuitbreaker.circuitBreakerAspectOrder` khi cần can thiệp; hành vi thực phụ thuộc version.

### 11.4 Fallback sau retry, không nuốt lỗi quá sớm

Một flow có chủ đích:

~~~text
Logical call
    |
    v
Breaker permission
    |
    v
Retry (nếu operation cho phép)
    |
    v
HTTP client
    |
    +-- success -> REMOTE
    |
    +-- attempts hết -> exception / breaker event
                           |
                           v
                       one fallback
~~~

Đây là flow **khái niệm**, không tuyên bố nó là default wiring của Resilience4j annotations. Khi implementation dùng functional chaining hoặc AOP, hãy kiểm lại thứ tự.

## 12. Fallback đúng domain và vấn đề idempotency

Nếu request **ghi** có thể được retry, phải xác định duplicate side effects. Ví dụ HTTP:

~~~http
POST /payments
Idempotency-Key: order-123-payment
Content-Type: application/json

{"orderId":"123","amount":100}
~~~

Đây là **protocol minh họa**; header `Idempotency-Key` chỉ có tác dụng khi server thực thi đúng. Server phải chống race giữa concurrent attempts, lưu key và kết quả với transaction consistency, và trả lại cùng kết quả cho duplicate request.

Bài test riêng cần chứng minh:

~~~text
one logical payment request
two HTTP attempts có thể xảy ra
same Idempotency-Key trên mọi attempt
server tạo chính xác một charge
client không trả giả thành công khi không rõ trạng thái
~~~

Với báo giá GET, duplication ít nguy hiểm hơn nhưng vẫn tăng latency, chi phí và vượt rate limit.

### 12.1 Fallback cache cần TTL

Một cache last-known-good có thể trả giá stale. Kiểm:

- Cache có dữ liệu → trả `STALE` với timestamp.
- Cache quá TTL → trả `UNAVAILABLE`, không dùng stale quá cũ.
- Cache không có key → UNAVAILABLE.
- Cache là dependency riêng: nếu cache down, fallback không được loop.
- Dữ liệu critical như authorization, charge amount: policy có thể không cho stale.
- Log/counter riêng cho degraded/stale, không ghi như upstream success.

## 13. Timeout không phải circuit breaker

Circuit breaker hạn chế **cuộc gọi mới**, không tự buộc một `RestClient` synchronous call đang treo kết thúc. Cần timeout ở HTTP transport/client.

Ví dụ `SimpleClientHttpRequestFactory` của Spring Framework 6.2:

~~~java
SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory();
factory.setConnectTimeout(Duration.ofSeconds(2));
factory.setReadTimeout(Duration.ofSeconds(3));

RestClient client = RestClient.builder()
        .requestFactory(factory)
        .baseUrl("https://vendor.example.test")
        .build();
~~~

Đây là **đoạn minh họa**, cần imports và không phải phần của demo tests. Nếu production dùng Apache HttpComponents/JDK/Jetty, cấu hình factory/pool timeout phù hợp client thật.

**Deadline end-to-end** phải tính cả thời gian attempts, backoff, queue/pool wait và fallback, không chỉ timeout mỗi attempt. Ba attempts × ba giây có thể vượt SLO 5 giây của controller.

### 13.1 Breaker không tự cancel in-flight calls

Ngay cả khi breaker OPEN sau hai failures, các requests đã bắt đầu trước đó có thể vẫn đang chạy. Test ngắt mạch với supplier đồng bộ không chứng minh cancellation của async calls hoặc WebClient. Với async/Reactive, cần test cancellation, timeout và concurrency riêng.

## 14. Khi nào dùng WireMock / MockWebServer?

`MockRestServiceServer` là lựa chọn nhanh để kiểm URL/method/status/response và exact count ở client component level. Nhưng nó không mở socket TCP.

Nếu bug nghi do:

- DNS/connect timeout, connection reset;
- HTTP redirects/retries theo client implementation;
- TLS, proxy, connection pooling;
- header/body streaming, chunking và compression;
- race khi nhiều requests concurrent;

hãy dùng WireMock hoặc OkHttp MockWebServer, random port, client request factory giống production, rồi kiểm request journal.

Mẫu **minh họa không độc lập**:

~~~java
@RegisterExtension
static WireMockExtension mock =
        WireMockExtension.newInstance()
                .options(wireMockConfig().dynamicPort())
                .build();

// Sau khi stub và gọi SUT, kiểm đúng số request:
mock.verify(2, getRequestedFor(
        urlEqualTo("/prices/SKU-1")));
~~~

Đây là pattern WireMock 3.x, cần dependency/imports và client base URL lấy từ port động. Đừng hardcode localhost:8080 khiến CI song song xung đột.

Một TCP mock server vẫn không phải vendor thật, và không chứng minh toàn bộ proxy/TLS production environment.

## 15. WebClient, @HttpExchange và nhiều subscription

Với `WebClient`, một `Mono`/`Flux` có thể là publisher lạnh: **mỗi subscription** có thể phát HTTP call mới. Hai lần subscribe cùng publisher không nhất thiết dùng cùng network response.

~~~java
Mono<Price> result = webClient.get()
        .uri("/prices/{sku}", sku)
        .retrieve()
        .bodyToMono(Price.class);

result.subscribe();
result.subscribe(); // có thể phát HTTP lần thứ hai
~~~

Đây là **mẫu giải thích**, không nằm trong demo. Khi reactive client được bảo vệ bằng circuit breaker, decorator phải được áp dụng tại **subscription/execution boundary**, không chỉ khi xây Mono. Dùng Reactor `StepVerifier`, virtual time và HTTP mock server phù hợp.

Với Spring declarative `@HttpExchange`/`@GetExchange`, mock proxy interface bằng Mockito không đủ để chứng minh request counts của actual transport. Nên kiểm ở HTTP mock layer bên dưới.

## 16. Số requests không chỉ do Retry

Các nguồn duplication khác:

1. Controller gọi adapter hai lần khi cùng xử lý một response.
2. Callback trong một stream được gọi hai lần.
3. Message consumer bị redelivery sau ack timeout.
4. Scheduler chạy trên hai replicas.
5. UI double-click gửi hai operations.
6. Tự xử lý 503 trong catch rồi gọi lần nữa, đồng thời retry library cũng hoạt động.
7. SDK hoặc API gateway retry ngầm.
8. Cache loader bị nhiều threads gọi đồng thời.
9. GraphQL DataLoader/batch mapping cấu hình sai.
10. Transaction retry chạy lại một block đã publish event ngoài DB.

Do đó cần kiểm **network attempt count** và **business side effect count** ở đúng tầng. Với GET, `MockRestServiceServer.expect(once)` đủ cho một component test. Với payment/order, cần integration test có idempotency store thật và hai requests đồng thời.

## 17. Metrics và logging để phát hiện lỗi ngoài test

Quan sát:

| Metric/trace | Ý nghĩa |
| --- | --- |
| Circuit breaker state | CLOSED/OPEN/HALF_OPEN |
| Failure rate | Tỷ lệ lỗi trong window |
| Not-permitted calls | Số lời gọi bị chặn trước HTTP |
| Upstream HTTP requests | Attempts thực tế |
| Retry attempts | Số lần retry mỗi logical operation |
| Fallback result | Tỷ lệ degraded/unavailable |
| HTTP status | 2xx/4xx/5xx, 429/503 |
| End-to-end latency | Bao gồm attempts và backoff |
| Upstream latency | Theo mỗi HTTP attempt |
| Logical request ID | Ghép trace qua tất cả attempts |

Nếu fallback trả HTTP 200 ở application layer, monitoring chỉ dựa vào 5xx của application sẽ không báo lỗi. Cần metric degraded/unavailable, alert theo SLO, và logs có correlation ID mà **không lộ credentials, bearer tokens hoặc PII**.

Ví dụ log **minh họa, không phải stdout test**:

~~~text
trace=abc1 logicalCall=pricing-1 attempt=1 status=503
trace=abc1 logicalCall=pricing-1 fallback=UNAVAILABLE
trace=abc2 logicalCall=pricing-2 breaker=OPEN upstreamAttempt=0
~~~

## 18. Các lỗi phổ biến và cách sửa

**1. Chỉ assert fallback trả được object.**  
Thêm assertion breaker state, metrics và exact HTTP attempts.

**2. Một lỗi 503 mà đòi breaker OPEN ngay.**  
Kiểm `minimumNumberOfCalls` và sliding window.

**3. Dùng Thread.sleep để chờ HALF_OPEN.**  
Flaky; dùng state transition thủ công trong logic tests hoặc custom Clock ở suite riêng.

**4. Dùng cùng circuit breaker giữa các test methods.**  
State rò; tạo mới trong `@BeforeEach`.

**5. Tạo breaker mới mỗi production request.**  
Không bao giờ tích đủ failures; dùng registry/bean shared theo dependency.

**6. Fallback gọi lại upstream đang hỏng.**  
Làm breaker mất tác dụng; exact count test sẽ bắt.

**7. Catch Exception rồi trả 0.00.**  
Che 404/auth/bug và có thể làm nghiệp vụ sai.

**8. 404 bị tính như 503.**  
Cần exception classifier/domain policy cụ thể.

**9. 429 retry tức thì vô hạn.**  
Tôn trọng Retry-After, quota, backoff+jitter và deadline.

**10. Đặt cả Retry ở service và HTTP client.**  
Có thể sinh số attempts bội số; đo tại network boundary.

**11. Aspect order suy theo thứ tự annotation trên method.**  
Không đáng tin; verify Spring AOP configuration và actual attempts.

**12. @CircuitBreaker self-invocation.**  
Proxy không intercept; tách bean hoặc dùng programmatic core.

**13. Thiếu Resilience4j Spring starter/AOP.**  
Annotation compile không có nghĩa aspect chạy; kiểm qua Spring context.

**14. Breaker OPEN nhưng HTTP vẫn được gửi.**  
Sai instance/wiring hoặc đường gọi bypass; test OPEN + verify zero requests.

**15. Dùng manyTimes() trong mock.**  
Che extra attempts; dùng once/times(N) theo policy.

**16. Không gọi mockServer.verify().**  
Không biết expectation được dùng đầy đủ hay không.

**17. Mock service mà tuyên bố test được HTTP status/URL.**  
Mock service chỉ chứng minh lời gọi service, không chứng minh transport.

**18. HTTP mock factory PASS nhưng lỗi thật nằm ở TCP/pool.**  
Thêm WireMock/MockWebServer sử dụng client factory production.

**19. Không có timeout ở HTTP client.**  
Breaker không tự ngắt supplier đang treo.

**20. Retry POST mà không có idempotency.**  
Timeout không chứng minh server chưa xử lý; bảo vệ side effects ở server.

**21. Fallback ghi như success trong breaker metrics.**  
Ném lỗi bên trong protected supplier, thực hiện fallback bên ngoài decorator.

**22. Không test HALF_OPEN probe thất bại.**  
Breaker phải mở lại và chặn calls tiếp.

**23. Fallback dùng cache quá TTL.**  
Có thể trả dữ liệu sai; kiểm thời gian, origin và domain constraints.

**24. Chỉ kiểm số Mockito invocations trên facade.**  
Một facade call có thể tạo nhiều HTTP attempts; kiểm HTTP boundary.

**25. Không quan sát tỷ lệ degraded trong production.**  
Application có thể luôn trả 200 nhưng người dùng không nhận được giá fresh.

## 19. Quy trình thiết kế test chống gọi lặp

1. Định nghĩa logical operation và upstream endpoint.
2. Phân loại lỗi có fallback, retry, bypass và propagate.
3. Xác định chính xác **max HTTP attempts** cho một logical call.
4. Xác định breaker window/minimumCalls/threshold và expected state transitions.
5. Đặt validation trước HTTP/breaker.
6. Dùng một RestClient.Builder được bind MockRestServiceServer **trước build**.
7. Khởi tạo breaker mới cho mỗi test.
8. Kiểm happy path bằng `once()`.
9. Kiểm một lỗi 503: fallback đúng, breaker chưa OPEN khi thiếu mẫu.
10. Kiểm đủ lỗi mở mạch và lời gọi tiếp theo không phát HTTP.
11. Kiểm HALF_OPEN success/failure bằng transition điều khiển, không ngủ.
12. Kiểm 404/400/auth không bị nuốt.
13. Kiểm invalid input/payload, lỗi I/O, error classification.
14. Nếu thêm retry, cập nhật exact expected attempts và đảm bảo không có tầng retry ngầm.
15. Nếu request ghi, kiểm idempotency và side-effect count trong DB/service integration.
16. Nếu bug thuộc network, bổ sung TCP mock server.
17. Quan sát metrics và logging theo logical operation vs attempts.
18. Chạy CI nhiều lần để phát hiện state/timing leak, không dùng vendor thật.

### Checklist cuối

- [ ] Result fallback có trạng thái degraded rõ ràng.
- [ ] Không dùng giá 0 làm giá thật khi upstream down.
- [ ] Breaker CLOSED/OPEN/HALF_OPEN có assertions.
- [ ] OPEN không gửi thêm HTTP, verified bằng mock server.
- [ ] Minimum calls/failure rate đúng ngưỡng.
- [ ] 404 và các HTTP client errors có policy riêng.
- [ ] HTTP 429 không bị retry ồ ạt.
- [ ] Exact attempts được xác minh, không có manyTimes để che lỗi.
- [ ] Fallback không gọi lại cùng upstream.
- [ ] Tests cô lập breaker/registry state.
- [ ] Không dùng Thread.sleep cho state assertions.
- [ ] Timeout và overall deadline được cấu hình rõ.
- [ ] Không có retry trùng giữa các layers.
- [ ] Spring AOP/aspect order được kiểm nếu dùng annotations.
- [ ] API ghi có idempotency/duplicate side-effect tests.
- [ ] Mock HTTP level phù hợp mục tiêu (factory vs TCP).
- [ ] Có observability cho degraded, OPEN, retry attempts và request count.

## 20. Câu hỏi tự kiểm tra

**1.** Fallback trả UNAVAILABLE sau 503 có chứng minh breaker OPEN?  
**Không.** Lỗi đầu tiên có thể chưa đạt minimumNumberOfCalls.

**2.** Vì sao test OPEN phải verify zero HTTP requests?  
Vì fallback có thể chạy sau khi đã gửi request; phải chứng minh supplier bị chặn trước transport.

**3.** 404 có nên trả fallback 0.00?  
Thông thường không: đó là not-found/client policy, không phải bằng chứng vendor outage.

**4.** `Thread.sleep` để chờ HALF_OPEN có nhược điểm gì?  
Dễ flaky do scheduler/CI; dùng manual transition hoặc controlled clock trong test.

**5.** Retry hai tầng max 3 có thể tạo bao nhiêu HTTP attempts?  
Trong một số đường lỗi, tới 9 cho một logical operation.

**6.** Breaker có thay thế connect/read timeout?  
Không. Nó chủ yếu cho phép/từ chối calls và ghi outcome.

**7.** Vì sao mock RestClient factory khác WireMock qua TCP?  
MockRestServiceServer không đi socket, WireMock giúp test transport thật hơn.

**8.** Nếu supplier tự catch 503 rồi trả fallback thành công, breaker ghi nhận gì?  
Có thể ghi success thay vì failure; nên để exception tới breaker trước khi fallback.

**9.** Payment POST timeout có chắc server chưa xử lý?  
Không. Retry phải có idempotency policy và server-side deduplication.

**10.** Tại sao code production không tạo CircuitBreaker.of(...) trong mỗi request?  
Vì mỗi instance mới không tích đủ metrics và không nhớ trạng thái OPEN chung.

## 21. Kết luận

Với HTTP client tích hợp trong Spring Boot, kiểm fallback đúng **không** đồng nghĩa đã kiểm circuit breaker và càng không chứng minh không có duplicate requests. Một bộ test mạnh phải khẳng định **đúng result, đúng breaker state và đúng số remote HTTP attempts**. Dùng `RestClient` + `MockRestServiceServer` để kiểm các ranh giới này, Resilience4j Core cho state deterministic, rồi bổ sung Spring AOP/WireMock và idempotency tests khi production dùng retry, annotations hoặc network transport phức tạp.

**Nguyên tắc then chốt:** khi mạch OPEN, fallback phải chạy **mà không gọi lại upstream**; khi retry được phép, số attempts phải được **định nghĩa và test chính xác**, đặc biệt với các operations có side effects.

### Tài liệu tham khảo chính thức

- [Spring Framework — Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): `MockRestServiceServer`, `ExpectedCount`, RestClient/RestTemplate.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, default status errors và onStatus.
- [Spring Framework 6.2 — MockRestServiceServer Java API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html): bindTo(RestClient.Builder), expect và verify.
- [Resilience4j — Circuit Breaker](https://resilience4j.readme.io/docs/circuitbreaker): trạng thái, failure rates, thresholds và sliding windows.
- [Resilience4j — Spring Boot 3 Getting Started](https://resilience4j.readme.io/docs/getting-started-3): @CircuitBreaker, fallbackMethod và aspect order.
- [Resilience4j — CircuitBreaker API source](https://github.com/resilience4j/resilience4j/blob/master/resilience4j-circuitbreaker/src/main/java/io/github/resilience4j/circuitbreaker/CircuitBreaker.java): decorateSupplier, executeSupplier, state transitions.
- [Resilience4j — CircuitBreakerConfig API source](https://github.com/resilience4j/resilience4j/blob/master/resilience4j-circuitbreaker/src/main/java/io/github/resilience4j/circuitbreaker/CircuitBreakerConfig.java): minimumNumberOfCalls, recordExceptions/ignoreExceptions, custom clock.
- [WireMock — JUnit Jupiter](https://wiremock.org/docs/junit-jupiter/): HTTP mock server extension, dynamic port và request journal.
