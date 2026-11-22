# Timeout, fallback và circuit breaker theo cấu hình ứng dụng

Trong nhóm **Hợp đồng và khả năng phục hồi** của module **Spring Boot - testing**, cần kiểm tra ứng dụng phản ứng ra sao khi một upstream HTTP chậm, không kết nối được, trả 429 hoặc 5xx và khi nó phục hồi. Ba cơ chế liên quan nhưng **không thể thay thế nhau**:

- **Timeout:** client ngừng chờ sau một thời hạn; không chứng minh upstream đã rollback hoặc dừng xử lý.
- **Circuit breaker:** ghi nhận kết quả các lời gọi trong sliding window; khi tỷ lệ lỗi vượt ngưỡng và đủ mẫu, nó chuyển OPEN để **chặn lời gọi mới**.
- **Fallback:** hành vi suy giảm có chủ đích, chỉ áp dụng với một số lỗi được phép; không biến một tác vụ thất bại thành dữ liệu đúng và không được che lỗi auth/validation.

Bài dùng **Java 17, Spring Boot 3.5, JUnit Jupiter, JDK HttpClient và Resilience4j CircuitBreaker 2.3.0**. Có các file nguồn và Gradle dependencies, test chạy thật cho breaker, ma trận `@ConfigurationProperties`, HTTP loopback test với timeout thực và `MockMvc` test cho HTTP response. Một demo Java SE không phụ thuộc Spring có lệnh `javac/java` và stdout chính xác.

**Hợp đồng ví dụ:** ứng dụng GET catalog từ upstream. Khi success, trả data thật với `degraded=false`. Với HTTP timeout/429/5xx hoặc circuit OPEN, nếu fallback bật thì trả thông báo `Catalog temporarily unavailable` với `degraded=true` và HTTP **503**, không giả vờ có catalog thật. Với upstream 4xx khác 429, không fallback mà trả lỗi 502 trong hợp đồng gateway demo. Đây là cách xử lý dữ liệu catalog **không quan trọng về tiền/quyền**; các hệ thống thanh toán, auth hoặc kiểm kê tồn kho cần chính sách an toàn nghiêm ngặt hơn.

## 1. Bốn ranh giới phải kiểm tra riêng

```text
HTTP inbound
    |
    v
CatalogController
    |
    v
CatalogService
    |        (circuitEnabled=false -> gọi thẳng port)
    +---- CircuitBreaker.decorateSupplier
    |         |
    |         +-- CLOSED/HALF_OPEN -> CatalogPort.fetch
    |         |                         |
    |         |                         v
    |         |                   HttpCatalogAdapter
    |         |                         |
    |         |                JDK HttpClient timeout
    |         |                         |
    |         |                         v
    |         |                      Upstream
    |         |
    |         +-- OPEN -> CallNotPermittedException
    |
    +-- primary success -> CatalogResult(body, false)
    +-- permitted failure + fallback -> CatalogResult(message, true)
    +-- unsupported failure -> exception/advice
```

**Test boundary map:**

| Test layer | Chứng minh | Không chứng minh |
| --- | --- | --- |
| JUnit + fake `CatalogPort` | Business fallback, circuit OPEN/HALF_OPEN và số lần gọi | HTTP timeout thật |
| `ApplicationContextRunner` | Property binding, breaker bean construction, invalid config | HTTP/Servlet hoạt động |
| JDK `HttpServer` trên loopback | TCP/HTTP status, UTF-8 và request timeout | Circuit state nếu chỉ gọi adapter |
| `@WebMvcTest` + MockMvc | Response status/headers/JSON khi success/degraded | Upstream, network, breaker logic |
| Full application/E2E | Đi qua toàn bộ beans/infrastructure trong môi trường dựng | Mọi sự cố production chưa giả lập |

Chỉ gọi một method và mock exception không được gọi là network timeout test. Chỉ test HTTP 200 không chứng minh breaker OPEN đúng. Và một test green ở fake fallback không chứng minh production cache stale là an toàn.

## 2. Connect timeout khác request timeout và deadline

```text
Incoming API deadline (example): 2000 ms
  |
  +-- connection setup <= 500 ms
  +-- HTTP attempt <= 300 ms
  +-- optional retry/backoff (not implemented in this lesson)
  +-- fallback/serialization time
```

- `HttpClient.Builder.connectTimeout(Duration)` áp cho thiết lập connection theo JDK client, không phải toàn request.
- `HttpRequest.Builder.timeout(Duration)` áp cho request, gồm việc đợi response theo semantics của JDK HttpClient. Nó không bảo đảm upstream chưa làm side effect.
- **Pool acquisition timeout** là thời gian chờ lấy connection/permit, khác network I/O timeout.
- **TimeLimiter** trong Resilience4j có ý nghĩa với CompletionStage/async wait, nhưng cancel Future không tự hủy mọi blocking network operation hoặc remote transaction.
- **Overall deadline** phải được propagation qua retries/downstream calls; không thể chỉ cộng các timeout rồi cho rằng có một hard deadline.
- Cần phân biệt timeout của **JUnit test** như `Future.get(5, SECONDS)` với timeout của **HTTP client**. Nếu Future timeout vì thread bị kẹt, không được kết luận HttpRequest.timeout đã làm việc.

**Khi retry request ghi dữ liệu:** client timeout không có nghĩa server chưa commit. Dùng stable idempotency key, outbox/inbox, reconciliation và trạng thái pending/unknown theo nghiệp vụ. Với hệ thông điệp **at-least-once delivery**, duplicate cũng có thể xảy ra; đừng tuyên bố exactly-once nhờ breaker hoặc retry.

## 3. CircuitBreaker state machine và các thông số

```text
       failure rate >= threshold after minimum calls
CLOSED ----------------------------------------------> OPEN
  ^                                                     |
  |                                                     | waitDurationInOpenState
  |                                                     | elapsed + next permission
  |                                                     | request (auto transition off)
  |                                                     v
  +-------------------- enough healthy probes ------ HALF_OPEN
                                failed probes --------> OPEN
```

- **CLOSED:** tất cả calls được phép; breaker ghi kết quả, không giới hạn concurrency.
- **OPEN:** `CallNotPermittedException` với các lời gọi **mới**; gateway không được gọi. Những calls đã được phép trước đó có thể vẫn chạy.
- **HALF_OPEN:** chỉ cho một số probe calls. Đủ successful probes → CLOSED; failed probe với threshold tương ứng → OPEN.
- `slidingWindowType=COUNT_BASED` và `slidingWindowSize=4` có nghĩa nhìn **4 calls gần nhất**, không phải 4 giây.
- `minimumNumberOfCalls=4` nghĩa sau 1–3 lỗi đầu tiên breaker chưa tự OPEN theo failure rate.
- `failureRateThreshold=50` nghĩa 2 failures trên 4 recorded calls đủ ngưỡng 50%.
- `waitDurationInOpenState` là thời gian OPEN trước khi có thể thử HALF_OPEN. Mặc định không buộc tự động chuyển chỉ vì đã sleep xong: có thể cần một lần gọi acquire permission.
- `permittedNumberOfCallsInHalfOpenState=2` giới hạn hai probes trong phase thăm dò.

**Khác nhau:** CircuitBreaker không phải Retry, Bulkhead hoặc RateLimiter. Nó không dừng call cũ và không hạn chế pool thread; phải phối hợp HTTP timeouts và resource limits. Các trạng thái đặc biệt như `DISABLED`, `METRICS_ONLY`, `FORCED_OPEN` có semantics khác CLOSED/OPEN/HALF_OPEN.

## 4. Lỗi nào bị breaker ghi nhận? Lỗi nào được fallback?

| Kết quả từ upstream/adapter | Exception | Breaker | Fallback |
| --- | --- | --- | --- |
| HTTP 200 | Không | Success | Không |
| HTTP 500/503 hoặc 429 | `CatalogPort.Unavailable` | Failure | Có nếu bật |
| IOException/DNS/connection fail | `Unavailable` | Failure | Có nếu bật |
| Request timeout | `Unavailable` | Failure | Có nếu bật |
| HTTP 400/401/403/404 | `Rejected` | Ignored | Không |
| Interrupted thread | `Cancelled` | Ignored | Không |
| Breaker OPEN | `CallNotPermittedException` | Not permitted, không gọi upstream | Có nếu bật |
| NullPointerException/bug code | Lỗi bất thường | Không fallback theo chính sách này | Không |

Một 401/403 không nên làm fallback tự cấp quyền; lỗi validation cũng không nên làm breaker nhận định upstream đang hỏng. Ví dụ dùng `recordExceptions(Unavailable.class)` và `ignoreExceptions(Rejected.class, Cancelled.class)`. Chính sách thật có thể map 404 thành một result `Optional.empty()` thay vì exception; phải viết contract/test theo từng endpoint.

**Điểm quan trọng:** fallback phải ở **ngoài decorator**, để breaker nhìn thấy thất bại primary call, không phải success của fallback.

## 5. Cấu hình bằng properties của ứng dụng

```properties
app.catalog.breaker-enabled=true
app.catalog.fallback-enabled=true
app.catalog.endpoint=http://127.0.0.1:9999/catalog
app.catalog.connect-timeout-ms=500
app.catalog.request-timeout-ms=300
app.catalog.sliding-window-size=4
app.catalog.minimum-calls=4
app.catalog.failure-rate-threshold=50
app.catalog.open-wait-ms=30000
app.catalog.half-open-calls=2
```

**Đây là namespace `app.catalog.*` do ví dụ tự định nghĩa**, không phải Resilience4j Spring Boot starter namespace. Nếu sử dụng starter với annotations `@CircuitBreaker`, properties có dạng `resilience4j.circuitbreaker.instances.<name>.*` và cần Spring AOP/proxy integration; không copy lẫn lộn.

Ma trận bắt buộc:

| breaker-enabled | fallback-enabled | Primary outcome | Kỳ vọng |
| --- | --- | --- | --- |
| true | true | Success | Primary, degraded=false |
| true | true | Timeout | Fallback, degraded=true |
| true | false | Timeout | Unavailable propagates |
| false | true | Timeout | Fallback, breaker không ghi |
| false | false | Timeout | Unavailable propagates |
| true | true | 4xx Rejected | Không fallback |
| true | true | Threshold reached | OPEN, lần tiếp theo không tới gateway |
| true | false | OPEN | CallNotPermittedException |
| true | true | HALF_OPEN healthy | CLOSED |
| true | true | HALF_OPEN unhealthy | OPEN |
| bất kỳ | bất kỳ | Invalid config | Context startup failure |

**Cần test cả default/missing property.** Đừng thay `System.setProperty(...)` giữa tests vì state global bị rò; dùng `ApplicationContextRunner.withPropertyValues` tạo một context cho mỗi vector.

## 6. Cấu trúc project và Gradle dependencies

```text
src/
├── main/java/example/resilience/
│   ├── ResilienceApplication.java
│   ├── CatalogSettings.java
│   ├── CatalogPort.java
│   ├── HttpCatalogAdapter.java
│   ├── CatalogResult.java
│   ├── CatalogService.java
│   ├── CatalogConfiguration.java
│   ├── CatalogController.java
│   ├── CatalogErrorAdvice.java
│   └── PolicyDecisionDemo.java
├── main/resources/application.properties
└── test/java/example/resilience/
    ├── CatalogServiceTest.java
    ├── CatalogConfigurationTest.java
    ├── HttpCatalogAdapterTest.java
    └── CatalogControllerTest.java
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là Gradle build file của demo cho Java17/Boot3.5/Resilience4j 2.3.0. Chạy Gradle cần wrapper đã cài hoặc Gradle tương thích. Không cần Docker, database, AWS hoặc cloud credentials. HTTP test dùng `com.sun.net.httpserver.HttpServer` trong module `jdk.httpserver` của JDK 17, bind cổng loopback được OS cấp.

## 7. CatalogSettings.java: typed configuration

Tạo `src/main/java/example/resilience/CatalogSettings.java`:

```java
package example.resilience;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.catalog")
public record CatalogSettings(
        @DefaultValue("true") boolean breakerEnabled,
        @DefaultValue("true") boolean fallbackEnabled,
        @DefaultValue("500") int connectTimeoutMs,
        @DefaultValue("300") int requestTimeoutMs,
        @DefaultValue("4") int slidingWindowSize,
        @DefaultValue("4") int minimumCalls,
        @DefaultValue("50") float failureRateThreshold,
        @DefaultValue("30000") long openWaitMs,
        @DefaultValue("2") int halfOpenCalls,
        @DefaultValue("http://127.0.0.1:9999/catalog")
        String endpoint) {
}
```

Spring Boot binder hỗ trợ record constructor binding và `@DefaultValue`. Các keys kebab-case bind vào accessors như `requestTimeoutMs()`. `@EnableConfigurationProperties(CatalogSettings.class)` trong configuration bên dưới đăng ký bean, không cần tự gọi constructor trong production.

**Validation:** endpoint phải là HTTP(S) URI hợp lệ; timeout/window/minimum/half-open > 0; `minimumCalls <= slidingWindowSize`; threshold trong [1,100]. Các rules được kiểm tra trong factory để fail startup rõ. Endpoint localhost:9999 là **demo default không trỏ production**; khi chạy application thực phải cấu hình endpoint của môi trường.

## 8. CatalogPort.java: ranh giới mạng

Tạo `src/main/java/example/resilience/CatalogPort.java`:

```java
package example.resilience;

public interface CatalogPort {
    String fetch();

    final class Unavailable extends RuntimeException {
        public Unavailable(String message) {
            super(message);
        }

        public Unavailable(String message, Throwable cause) {
            super(message, cause);
        }
    }

    final class Rejected extends RuntimeException {
        public Rejected(String message) {
            super(message);
        }
    }

    final class Cancelled extends RuntimeException {
        public Cancelled(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

Service không biết `HttpClient` hay `IOException`, chỉ biết primary call có success hay một typed error. `Unavailable` (network/timeout/5xx/429) được ghi breaker failure; `Rejected` (4xx khác 429) và `Cancelled` (interrupt) bị ignore; fallback không che hai loại lỗi này. Đây là policy minh họa, không tự áp cho mọi upstream API.

## 9. HttpCatalogAdapter.java: JDK HttpClient timeout

Tạo `src/main/java/example/resilience/HttpCatalogAdapter.java`:

```java
package example.resilience;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class HttpCatalogAdapter implements CatalogPort {
    private final HttpClient http;
    private final CatalogSettings settings;

    public HttpCatalogAdapter(
            HttpClient http, CatalogSettings settings) {
        this.http = http;
        this.settings = settings;
    }

    @Override
    public String fetch() {
        HttpRequest request = HttpRequest.newBuilder(
                        URI.create(settings.endpoint()))
                .timeout(Duration.ofMillis(
                        settings.requestTimeoutMs()))
                .GET()
                .build();

        try {
            HttpResponse<String> response = http.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            int status = response.statusCode();
            if (status == 200) {
                return response.body();
            }
            if (status == 429 || status >= 500) {
                throw new Unavailable("upstream unavailable");
            }
            throw new Rejected("upstream rejected request");
        } catch (HttpTimeoutException error) {
            throw new Unavailable("upstream timed out", error);
        } catch (IOException error) {
            throw new Unavailable(
                    "upstream transport error", error);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new Cancelled(
                    "upstream interrupted", error);
        }
    }
}
```

**Giới hạn:**

- Đây là **blocking** HTTP call, phù hợp demo Servlet MVC, không gọi trực tiếp trên reactive WebFlux event loop.
- Kết quả success chỉ HTTP 200; 3xx và 4xx (khác 429) thành Rejected. Trong production có thể xử lý redirect/304/404 riêng.
- Adapter không tự retry. Timeout là **request timeout thật** nhờ JDK HttpRequest; breaker chỉ quan sát kết quả.
- `InterruptedException` giữ interrupt flag và không bị fallback nuốt.
- Exception message không tiết lộ raw URI/token/body upstream.

## 10. CatalogResult và CatalogService: fallback ngoài decorator

Tạo `src/main/java/example/resilience/CatalogResult.java`:

```java
package example.resilience;

public record CatalogResult(
        String body, boolean degraded) {
}
```

Tạo `src/main/java/example/resilience/CatalogService.java`:

```java
package example.resilience;

import java.util.function.Supplier;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;

public class CatalogService {
    private final CatalogPort port;
    private final CircuitBreaker breaker;
    private final CatalogSettings settings;

    public CatalogService(
            CatalogPort port,
            CircuitBreaker breaker,
            CatalogSettings settings) {
        this.port = port;
        this.breaker = breaker;
        this.settings = settings;
    }

    public CatalogResult load() {
        Supplier<String> primary = port::fetch;

        if (settings.breakerEnabled()) {
            primary = CircuitBreaker.decorateSupplier(
                    breaker, primary);
        }

        try {
            return new CatalogResult(primary.get(), false);
        } catch (CallNotPermittedException
                 | CatalogPort.Unavailable error) {
            if (!settings.fallbackEnabled()) {
                throw error;
            }

            return new CatalogResult(
                    "Catalog temporarily unavailable",
                    true);
        }
    }
}
```

Code kiểm tra chính xác ba điều:

1. Breaker enabled → wrap primary. Breaker disabled → call port trực tiếp, nhưng request timeout của adapter vẫn còn.
2. `Unavailable` hoặc `CallNotPermittedException` được fallback nếu flag bật, không fallback khi flag tắt.
3. `Rejected`, `Cancelled` và bug code không catch; client nhận lỗi đúng.

**Không** bọc toàn bộ CatalogService.load trong CircuitBreaker nếu muốn fallback nằm ngoài metrics. Nếu fallback được trả ở bên trong đoạn được đo, breaker có thể thấy success, không OPEN dù upstream lỗi.

## 11. CatalogConfiguration.java: Bean lifecycle, threshold, validation

Tạo `src/main/java/example/resilience/CatalogConfiguration.java`:

```java
package example.resilience;

import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogSettings.class)
public class CatalogConfiguration {

    @Bean
    HttpClient catalogHttpClient(CatalogSettings settings) {
        validate(settings);

        return HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(
                        settings.connectTimeoutMs()))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Bean
    CircuitBreaker catalogBreaker(CatalogSettings settings) {
        validate(settings);

        CircuitBreakerConfig config =
                CircuitBreakerConfig.custom()
                        .slidingWindowType(
                                CircuitBreakerConfig.SlidingWindowType
                                        .COUNT_BASED)
                        .slidingWindowSize(
                                settings.slidingWindowSize())
                        .minimumNumberOfCalls(
                                settings.minimumCalls())
                        .failureRateThreshold(
                                settings.failureRateThreshold())
                        .waitDurationInOpenState(
                                Duration.ofMillis(
                                        settings.openWaitMs()))
                        .permittedNumberOfCallsInHalfOpenState(
                                settings.halfOpenCalls())
                        .recordExceptions(
                                CatalogPort.Unavailable.class)
                        .ignoreExceptions(
                                CatalogPort.Rejected.class,
                                CatalogPort.Cancelled.class)
                        .build();

        return CircuitBreaker.of("catalog", config);
    }

    @Bean
    CatalogPort catalogPort(
            HttpClient catalogHttpClient,
            CatalogSettings settings) {
        return new HttpCatalogAdapter(
                catalogHttpClient, settings);
    }

    @Bean
    CatalogService catalogService(
            CatalogPort catalogPort,
            CircuitBreaker catalogBreaker,
            CatalogSettings settings) {
        return new CatalogService(
                catalogPort, catalogBreaker, settings);
    }

    private static void validate(CatalogSettings s) {
        if (s.connectTimeoutMs() <= 0
                || s.requestTimeoutMs() <= 0
                || s.slidingWindowSize() <= 0
                || s.minimumCalls() <= 0
                || s.minimumCalls() > s.slidingWindowSize()
                || s.failureRateThreshold() < 1
                || s.failureRateThreshold() > 100
                || s.openWaitMs() <= 0
                || s.halfOpenCalls() <= 0) {
            throw new IllegalArgumentException(
                    "invalid catalog resilience configuration");
        }

        final URI uri;
        try {
            uri = URI.create(s.endpoint());
        } catch (IllegalArgumentException error) {
            throw new IllegalArgumentException(
                    "invalid catalog URI", error);
        }

        String scheme = uri.getScheme();
        if (scheme == null || uri.getHost() == null
                || (!scheme.equalsIgnoreCase("http")
                    && !scheme.equalsIgnoreCase("https"))) {
            throw new IllegalArgumentException(
                    "catalog URI must be HTTP(S)");
        }
    }
}
```

**Quan trọng:** breaker bean có **một owner theo ApplicationContext**, không tạo lại mỗi request. Nếu mỗi request tạo `CircuitBreaker.of(...)` mới, failure history bị mất; breaker khó đạt threshold. Spring Boot Record config tạo một bean bằng `@EnableConfigurationProperties` và factory validate trước khi bật client.

**Feature flag** `breakerEnabled=false` ở code chỉ bypass decorate. Nó không tự chuyển breaker sang state `DISABLED`. Nếu cần dynamic enable/disable giữa các deployments, xác định lifecycle/state/metrics và test mới, không sửa Environment sau khi context đã refresh rồi cho rằng bean cập nhật.

## 12. HTTP response contract của ứng dụng

Tạo `src/main/java/example/resilience/CatalogController.java`:

```java
package example.resilience;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {
    private final CatalogService service;

    public CatalogController(CatalogService service) {
        this.service = service;
    }

    @GetMapping("/catalog")
    public ResponseEntity<CatalogResult> catalog() {
        CatalogResult data = service.load();

        return ResponseEntity.status(
                        data.degraded()
                                ? HttpStatus.SERVICE_UNAVAILABLE
                                : HttpStatus.OK)
                .header(
                        "X-Degraded",
                        Boolean.toString(data.degraded()))
                .body(data);
    }
}
```

Tạo `src/main/java/example/resilience/CatalogErrorAdvice.java`:

```java
package example.resilience;

import java.util.Map;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class CatalogErrorAdvice {

    @ExceptionHandler({
            CatalogPort.Unavailable.class,
            CatalogPort.Cancelled.class,
            CallNotPermittedException.class
    })
    public ResponseEntity<Map<String, String>> unavailable() {
        return ResponseEntity.status(
                        HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("error", "catalog unavailable"));
    }

    @ExceptionHandler(CatalogPort.Rejected.class)
    public ResponseEntity<Map<String, String>> rejected() {
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(Map.of("error", "upstream rejected request"));
    }
}
```

**Fallback kết quả không phải HTTP success:** body chỉ là thông báo, nên HTTP 503 + `X-Degraded: true`. Với cache data thật, ứng dụng có thể hợp đồng 200 kèm stale marker và TTL rõ; không áp điều đó khi data là text tự tạo. Advice trả 503 khi fallback disabled, 502 với Rejected và không lộ raw exception.

Tạo `src/main/java/example/resilience/ResilienceApplication.java`:

```java
package example.resilience;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResilienceApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                ResilienceApplication.class, args);
    }
}
```

Tạo `src/main/resources/application.properties` là bảng properties trong mục 5. Đây là ví dụ web app không phụ thuộc database/broker. Nếu muốn chạy ứng dụng thật, phải cấu hình URI upstream reachable phù hợp.

## 13. CatalogServiceTest.java: JUnit state machine không sleep

Tạo `src/test/java/example/resilience/CatalogServiceTest.java`:

```java
package example.resilience;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CatalogServiceTest {

    private static CatalogSettings settings(
            boolean breakerOn, boolean fallbackOn) {
        return new CatalogSettings(
                breakerOn, fallbackOn,
                500, 300, 4, 4, 50f, 30_000L, 2,
                "http://127.0.0.1:9999/catalog");
    }

    private static CircuitBreaker breaker(
            int window, int minCalls, int halfOpenCalls) {
        return CircuitBreaker.of(
                "test-catalog",
                CircuitBreakerConfig.custom()
                        .slidingWindowSize(window)
                        .minimumNumberOfCalls(minCalls)
                        .failureRateThreshold(50f)
                        .waitDurationInOpenState(
                                Duration.ofMinutes(10))
                        .permittedNumberOfCallsInHalfOpenState(
                                halfOpenCalls)
                        .recordExceptions(
                                CatalogPort.Unavailable.class)
                        .ignoreExceptions(
                                CatalogPort.Rejected.class,
                                CatalogPort.Cancelled.class)
                        .build());
    }

    @Test
    void primarySuccess() {
        CatalogService service = new CatalogService(
                () -> "fresh",
                breaker(2, 2, 2),
                settings(true, true));

        assertEquals(
                new CatalogResult("fresh", false),
                service.load());
    }

    @Test
    void enoughFailuresOpenBreakerAndSkipGateway() {
        AtomicInteger calls = new AtomicInteger();
        CatalogPort port = () -> {
            calls.incrementAndGet();
            throw new CatalogPort.Unavailable("offline");
        };

        CircuitBreaker cb = breaker(2, 2, 2);
        CatalogService service = new CatalogService(
                port, cb, settings(true, true));

        assertTrue(service.load().degraded());
        assertTrue(service.load().degraded());
        assertEquals(CircuitBreaker.State.OPEN, cb.getState());
        assertEquals(2, calls.get());

        assertTrue(service.load().degraded());
        assertEquals(2, calls.get());
    }

    @Test
    void minimumCallsPreventPrematureOpen() {
        CatalogPort port = () -> {
            throw new CatalogPort.Unavailable("one");
        };

        CircuitBreaker cb = breaker(4, 4, 2);
        CatalogService service = new CatalogService(
                port, cb, settings(true, true));

        assertTrue(service.load().degraded());
        assertEquals(
                CircuitBreaker.State.CLOSED, cb.getState());
    }

    @Test
    void disabledFallbackPropagatesFailure() {
        CatalogPort port = () -> {
            throw new CatalogPort.Unavailable("down");
        };

        CatalogService service = new CatalogService(
                port, breaker(2, 2, 2),
                settings(true, false));

        assertThrows(CatalogPort.Unavailable.class, service::load);
    }

    @Test
    void disabledBreakerBypassesOpenState() {
        AtomicInteger calls = new AtomicInteger();
        CatalogPort port = () -> {
            calls.incrementAndGet();
            return "primary";
        };

        CircuitBreaker cb = breaker(2, 2, 2);
        cb.transitionToOpenState();

        CatalogService service = new CatalogService(
                port, cb, settings(false, true));

        assertFalse(service.load().degraded());
        assertEquals(1, calls.get());
        assertEquals(CircuitBreaker.State.OPEN, cb.getState());
    }

    @Test
    void rejectedIsNotFallbackOrBreakerFailure() {
        CatalogPort port = () -> {
            throw new CatalogPort.Rejected("invalid");
        };

        CircuitBreaker cb = breaker(2, 2, 2);
        CatalogService service = new CatalogService(
                port, cb, settings(true, true));

        assertThrows(CatalogPort.Rejected.class, service::load);
        assertEquals(CircuitBreaker.State.CLOSED, cb.getState());
        assertEquals(0, cb.getMetrics().getNumberOfFailedCalls());
    }

    @Test
    void successfulHalfOpenProbesCloseCircuit() {
        AtomicInteger calls = new AtomicInteger();
        CatalogPort port = () -> {
            calls.incrementAndGet();
            return "recovered";
        };

        CircuitBreaker cb = breaker(2, 2, 2);
        cb.transitionToOpenState();
        cb.transitionToHalfOpenState();

        CatalogService service = new CatalogService(
                port, cb, settings(true, true));

        assertEquals("recovered", service.load().body());
        assertEquals("recovered", service.load().body());
        assertEquals(2, calls.get());
        assertEquals(CircuitBreaker.State.CLOSED, cb.getState());
    }

    @Test
    void failedHalfOpenProbeReopensCircuit() {
        CatalogPort port = () -> {
            throw new CatalogPort.Unavailable(
                    "still unhealthy");
        };

        CircuitBreaker cb = breaker(2, 2, 1);
        cb.transitionToOpenState();
        cb.transitionToHalfOpenState();

        CatalogService service = new CatalogService(
                port, cb, settings(true, true));

        assertTrue(service.load().degraded());
        assertEquals(CircuitBreaker.State.OPEN, cb.getState());
    }
}
```

**Tám test methods**, không dùng Spring context/network. Chúng chứng minh breaker thu thập lỗi (2/2 opens), OPEN không gọi gateway, minimum calls, fallback bật/tắt, breaker bypass, 4xx không fallback, HALF_OPEN healthy closes và HALF_OPEN failure reopens.

**Không nhầm manual transition với thời gian thật:** `transitionToHalfOpenState()` giúp test state machine mà không ngủ 10 phút, nhưng không xác nhận chính xác thời gian `waitDurationInOpenState`. Muốn kiểm tra timeout của breaker clock thì cần một test với fake Clock/advance-time theo API phiên bản; không suy diễn từ `Thread.sleep(30_000)`. Mặc định `automaticTransitionFromOpenToHalfOpenEnabled=false`, nên sau khi wait elapsed thường cần một lần acquire permission để chuyển trạng thái.

## 14. CatalogConfigurationTest.java: property matrix và startup failure

Tạo `src/test/java/example/resilience/CatalogConfigurationTest.java`:

```java
package example.resilience;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CatalogConfigurationTest {
    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            CatalogConfiguration.class);

    @Test
    void defaultsAreBoundAndBreakerCreated() {
        runner.run(context -> {
            assertNull(context.getStartupFailure());
            CatalogSettings s =
                    context.getBean(CatalogSettings.class);
            CircuitBreaker cb =
                    context.getBean(CircuitBreaker.class);

            assertTrue(s.breakerEnabled());
            assertTrue(s.fallbackEnabled());
            assertEquals(500, s.connectTimeoutMs());
            assertEquals(300, s.requestTimeoutMs());
            assertEquals(4, s.slidingWindowSize());
            assertEquals(4, s.minimumCalls());
            assertEquals(50f,
                    cb.getCircuitBreakerConfig()
                            .getFailureRateThreshold());
        });
    }

    @Test
    void customValuesConfigureClientAndBreaker() {
        runner.withPropertyValues(
                        "app.catalog.breaker-enabled=false",
                        "app.catalog.fallback-enabled=false",
                        "app.catalog.connect-timeout-ms=900",
                        "app.catalog.request-timeout-ms=250",
                        "app.catalog.sliding-window-size=6",
                        "app.catalog.minimum-calls=3",
                        "app.catalog.failure-rate-threshold=75",
                        "app.catalog.open-wait-ms=1200",
                        "app.catalog.half-open-calls=1")
                .run(context -> {
                    assertNull(context.getStartupFailure());
                    CatalogSettings s =
                            context.getBean(CatalogSettings.class);
                    CircuitBreaker cb =
                            context.getBean(CircuitBreaker.class);

                    assertFalse(s.breakerEnabled());
                    assertFalse(s.fallbackEnabled());
                    assertEquals(900, s.connectTimeoutMs());
                    assertEquals(250, s.requestTimeoutMs());
                    assertEquals(6,
                            cb.getCircuitBreakerConfig()
                                    .getSlidingWindowSize());
                    assertEquals(3,
                            cb.getCircuitBreakerConfig()
                                    .getMinimumNumberOfCalls());
                    assertEquals(75f,
                            cb.getCircuitBreakerConfig()
                                    .getFailureRateThreshold());
                    assertEquals(1200L, s.openWaitMs());
                    assertEquals(1, s.halfOpenCalls());
                });
    }

    @Test
    void flagsHaveFourIndependentCombinations() {
        String[][] matrix = {
            {"true", "true"}, {"true", "false"},
            {"false", "true"}, {"false", "false"}
        };

        for (String[] values : matrix) {
            runner.withPropertyValues(
                            "app.catalog.breaker-enabled="
                                    + values[0],
                            "app.catalog.fallback-enabled="
                                    + values[1])
                    .run(context -> {
                        assertNull(context.getStartupFailure());
                        CatalogSettings s =
                                context.getBean(CatalogSettings.class);

                        assertEquals(
                                Boolean.parseBoolean(values[0]),
                                s.breakerEnabled());
                        assertEquals(
                                Boolean.parseBoolean(values[1]),
                                s.fallbackEnabled());
                    });
        }
    }

    @Test
    void invalidWindowAndThresholdFailStartup() {
        runner.withPropertyValues(
                        "app.catalog.sliding-window-size=2",
                        "app.catalog.minimum-calls=3")
                .run(context ->
                        assertNotNull(context.getStartupFailure()));

        runner.withPropertyValues(
                        "app.catalog.failure-rate-threshold=0")
                .run(context ->
                        assertNotNull(context.getStartupFailure()));
    }

    @Test
    void derivedRunnerDoesNotMutateBaseline() {
        runner.withPropertyValues(
                        "app.catalog.fallback-enabled=false")
                .run(context -> {
                    assertNull(context.getStartupFailure());
                    assertFalse(context.getBean(
                            CatalogSettings.class)
                            .fallbackEnabled());
                });

        runner.run(context -> {
            assertNull(context.getStartupFailure());
            assertTrue(context.getBean(
                    CatalogSettings.class)
                    .fallbackEnabled());
        });
    }
}
```

**Năm test methods**: kiểm tra defaults, overridden timeout/threshold, bốn tổ hợp breaker × fallback, hai invalid configurations và context isolation. Trong method ma trận, mỗi `runner.withPropertyValues(...).run(...)` tạo **context mới**. Không dùng mutable `System.setProperty` toàn cục.

Một lưu ý về test âm tính: kiểm tra context không có bean chưa đủ nếu thực ra startup đã fail. Với case dự kiến thành công phải assert `context.getStartupFailure()==null`; với invalid config phải assert startup failure khác null. Đây là kiểm thử config factory, không phải HTTP transport.

## 15. HttpCatalogAdapterTest.java: HTTP timeout thật trên loopback

Để thực sự kiểm tra `HttpRequest.timeout(...)`, dùng HTTP server cục bộ thuộc JDK 17, cổng ephemeral. Không chỉ mock `CatalogPort.fetch()` cho throw exception.

Tạo `src/test/java/example/resilience/HttpCatalogAdapterTest.java`:

```java
package example.resilience;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HttpCatalogAdapterTest {
    private HttpServer server;
    private ExecutorService serverWorkers;

    private void start(HttpHandler handler) throws IOException {
        server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        serverWorkers = Executors.newSingleThreadExecutor();
        server.setExecutor(serverWorkers);
        server.createContext("/catalog", handler);
        server.start();
    }

    private CatalogPort adapter(int timeoutMs) {
        CatalogSettings s = new CatalogSettings(
                true, true, 500, timeoutMs,
                4, 4, 50f, 30_000L, 2,
                "http://127.0.0.1:"
                        + server.getAddress().getPort()
                        + "/catalog");

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(
                        Duration.ofMillis(s.connectTimeoutMs()))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        return new HttpCatalogAdapter(client, s);
    }

    private static HttpHandler reply(
            int code, String body) {
        return exchange -> {
            byte[] bytes = body.getBytes(
                    StandardCharsets.UTF_8);

            try (exchange) {
                exchange.sendResponseHeaders(code, bytes.length);
                exchange.getResponseBody().write(bytes);
            }
        };
    }

    @AfterEach
    void cleanup() {
        if (server != null) {
            server.stop(0);
        }
        if (serverWorkers != null) {
            serverWorkers.shutdownNow();
        }
    }

    @Test
    void status200ReturnsUtf8Body() throws Exception {
        start(reply(200, "Dữ liệu 😀"));
        assertEquals("Dữ liệu 😀", adapter(2000).fetch());
    }

    @Test
    void status500IsUnavailable() throws Exception {
        start(reply(500, "error"));
        assertThrows(
                CatalogPort.Unavailable.class,
                () -> adapter(2000).fetch());
    }

    @Test
    void status400IsRejected() throws Exception {
        start(reply(400, "bad request"));
        assertThrows(
                CatalogPort.Rejected.class,
                () -> adapter(2000).fetch());
    }

    @Test
    void stalledResponseTriggersRequestTimeout()
            throws Exception {
        CountDownLatch received = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        start(exchange -> {
            received.countDown();

            try (exchange) {
                try {
                    if (!release.await(
                            5, TimeUnit.SECONDS)) {
                        return;
                    }
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    return;
                }

                byte[] bytes = "late".getBytes(
                        StandardCharsets.UTF_8);
                try {
                    exchange.sendResponseHeaders(200, bytes.length);
                    exchange.getResponseBody().write(bytes);
                } catch (IOException ignored) {
                    // Client có thể đóng socket do timeout.
                }
            }
        });

        ExecutorService caller =
                Executors.newSingleThreadExecutor();

        try {
            Future<String> result =
                    caller.submit(() -> adapter(1200).fetch());

            assertTrue(received.await(3, TimeUnit.SECONDS));

            ExecutionException failure = assertThrows(
                    ExecutionException.class,
                    () -> result.get(4, TimeUnit.SECONDS));

            assertTrue(failure.getCause()
                    instanceof CatalogPort.Unavailable);
        } finally {
            release.countDown();
            caller.shutdownNow();
        }
    }
}
```

**Bốn HTTP integration tests:** 200 Unicode, 500, 400 và response bị giữ lại. Test timeout cuối dùng `CountDownLatch` để chứng minh server đã nhận request, sau đó kiểm tra JDK client kết thúc bằng `Unavailable`; không dùng `Thread.sleep`. Timeout của `Future.get(4s)` bảo vệ JUnit tránh treo, **khác** timeout của HTTP request (1.200ms). Test server và threads được dọn bằng `finally/@AfterEach`.

**Giới hạn:** đây là loopback, không kiểm tra DNS remote, TLS/mTLS, proxy, packet loss, load balancer hoặc cloud latency. Ở CI quá tải, các timeouts có thể cần ngân sách phù hợp; không assert elapsed milliseconds chính xác.

## 16. CatalogControllerTest.java: MockMvc HTTP contract

Tạo `src/test/java/example/resilience/CatalogControllerTest.java`:

```java
package example.resilience;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CatalogController.class)
class CatalogControllerTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    CatalogService service;

    @Test
    void primary200IsNotDegraded() throws Exception {
        when(service.load()).thenReturn(
                new CatalogResult("fresh", false));

        mvc.perform(get("/catalog"))
                .andExpect(status().isOk())
                .andExpect(
                        header().string("X-Degraded", "false"))
                .andExpect(jsonPath("$.body").value("fresh"))
                .andExpect(
                        jsonPath("$.degraded").value(false));
    }

    @Test
    void fallback503HasDegradedMarker() throws Exception {
        when(service.load()).thenReturn(
                new CatalogResult(
                        "Catalog temporarily unavailable", true));

        mvc.perform(get("/catalog"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(
                        header().string("X-Degraded", "true"))
                .andExpect(
                        jsonPath("$.degraded").value(true));
    }

    @Test
    void rejection502DoesNotLeakPrivateReason()
            throws Exception {
        when(service.load()).thenThrow(
                new CatalogPort.Rejected("secret reason"));

        mvc.perform(get("/catalog"))
                .andExpect(status().isBadGateway())
                .andExpect(
                        jsonPath("$.error").value(
                                "upstream rejected request"));
    }
}
```

**Ba MockMvc tests** dùng `@WebMvcTest` và `@MockitoBean` để mock **service**: đúng với mục tiêu chỉ test controller/advice. Nếu đang kiểm tra state machine/fallback implementation, phải dùng **real CatalogService + Resilience4j**, không mock nó. Test này không mở upstream và không chứng minh timeout xảy ra.

## 17. Tổng hợp JUnit methods và cách chạy

| Test class | Methods | Boundary |
| --- | ---: | --- |
| `CatalogServiceTest` | 8 | Real breaker, fake port |
| `CatalogConfigurationTest` | 5 | Context runner + properties |
| `HttpCatalogAdapterTest` | 4 | HTTP loopback thật |
| `CatalogControllerTest` | 3 | MockMvc response contract |
| **Tổng** | **20** | |

Linux/macOS:

```bash
./gradlew test --tests example.resilience.CatalogServiceTest
./gradlew test --tests example.resilience.CatalogConfigurationTest
./gradlew test --tests example.resilience.HttpCatalogAdapterTest
./gradlew test --tests example.resilience.CatalogControllerTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.resilience.CatalogServiceTest"
.\gradlew.bat test --tests "example.resilience.CatalogConfigurationTest"
.\gradlew.bat test --tests "example.resilience.HttpCatalogAdapterTest"
.\gradlew.bat test --tests "example.resilience.CatalogControllerTest"
```

**Số lượng 20 methods là số định nghĩa trong mã**, không phải lời khẳng định chúng đã được chạy trên máy người học. Gradle/JUnit logs không có stdout cố định vì versions và runner khác nhau. Java SE demo phần sau mới có stdout chính xác.

## 18. Demo Java SE độc lập, không cần Spring

Tạo `src/main/java/example/resilience/PolicyDecisionDemo.java`:

```java
package example.resilience;

public class PolicyDecisionDemo {
    enum Outcome {
        OK, TIMEOUT, OPEN, BAD_REQUEST
    }

    static String decide(
            Outcome outcome, boolean fallback) {
        if (outcome == Outcome.OK) {
            return "PRIMARY/200";
        }
        if (outcome == Outcome.BAD_REQUEST) {
            return "ERROR/502";
        }
        return fallback ? "DEGRADED/503" : "ERROR/503";
    }

    public static void main(String[] args) {
        System.out.println("ok=" + decide(Outcome.OK, true));
        System.out.println(
                "timeout=" + decide(Outcome.TIMEOUT, true));
        System.out.println(
                "open=" + decide(Outcome.OPEN, true));
        System.out.println(
                "4xx=" + decide(Outcome.BAD_REQUEST, true));
        System.out.println(
                "fallback-off="
                        + decide(Outcome.TIMEOUT, false));
    }
}
```

Lệnh Java 17+:

```bash
javac -d out src/main/java/example/resilience/PolicyDecisionDemo.java
java -cp out example.resilience.PolicyDecisionDemo
```

Stdout **chính xác**:

```text
ok=PRIMARY/200
timeout=DEGRADED/503
open=DEGRADED/503
4xx=ERROR/502
fallback-off=ERROR/503
```

Đây là **mô hình Java SE** để đọc policy kết quả, không khởi động breaker thật, không có HTTP hoặc Spring. Đừng chạy nó rồi tuyên bố CircuitBreaker đã mở đúng; JUnit tests của CatalogService mới kiểm tra state machine.

## 19. Vì sao không kiểm tra HALF_OPEN bằng Thread.sleep?

Một test viết:

```java
assertEquals(CircuitBreaker.State.OPEN, cb.getState());
Thread.sleep(30_000);
assertEquals(CircuitBreaker.State.HALF_OPEN, cb.getState());
```

là không đúng với mặc định Resilience4j: `automaticTransitionFromOpenToHalfOpenEnabled=false` nghĩa là breaker có thể cần **một permission request mới** sau `waitDurationInOpenState` để chuyển HALF_OPEN. Chỉ sleep rồi đọc state không khẳng định được transition.

Chiến lược đúng:

1. **Configuration test:** assert `openWaitMs` đã bind đúng; breaker factory xây config đúng.
2. **State test:** dùng `transitionToOpenState()` và `transitionToHalfOpenState()` chủ động; test số probe calls, success/failure transitions.
3. **Clock test nếu business contract yêu cầu:** dùng Clock injection/fake time theo API Resilience4j 2.3.x hoặc bounded integration có trigger permission phù hợp. Không biến một bài kiểm thử hàng chục giây thành flaky CI test.
4. **Timeout HTTP thật** không thể thay bằng fake clock của breaker; vẫn cần transport integration test.

Như vậy test HALF_OPEN của ví dụ chứng minh trạng thái dưới điều khiển JUnit, **không** chứng minh thời gian thực tế tới HALF_OPEN luôn đúng đến từng millisecond.

## 20. Retry, bulkhead, TimeLimiter và idempotency

**Retry:** chỉ retry lỗi transient, không retry mọi exception. Đặt max attempts, backoff+jitter, total deadline và budget tải; cân nhắc `Retry-After` cho HTTP 429. Đối với POST/PUT có side effects, dùng idempotency key hoặc recovery flow. Không retry circuit-open rejection vô hạn.

**Bulkhead:** giới hạn số calls đồng thời/threads/permits. Breaker CLOSED vẫn cho phép lượng lớn calls, vì thế một HTTP connection pool có thể cạn trước khi breaker OPEN.

**TimeLimiter:** có thể giới hạn CompletionStage/async wait; nó không đảm bảo blocking task hay server đã dừng. Cancellation/interrupt cần được propagate và test theo client cụ thể.

**Order:** `Retry(CircuitBreaker(Gateway))` có thể khiến mỗi attempt được breaker ghi; `CircuitBreaker(Retry(Gateway))` có thể chỉ tính kết quả cuối của chuỗi. Khi dùng annotation-based Resilience4j starter, AOP decorator order/proxy làm khác behavior.

**At-least-once:** trong messaging/retry network, một logical event hoặc request có thể được xử lý lặp; consumer/process phải idempotent. Không tuyên bố exactly-once chỉ vì retry cuối thành công. Với payment/DB/S3, cân nhắc stable eventId, inbox/outbox, reconciliation/compensation.

Bộ code chính **không bật retry/TimeLimiter/Bulkhead**, nên tests không được diễn giải là đã kiểm tra những feature chưa hiện thực.

## 21. Fallback không được che sai lệch nghiệp vụ

Fallback hợp lệ có thể là thông báo 503, một cache có TTL rõ hoặc một chức năng optional tạm bị tắt. Những fallback nguy hiểm:

- Thanh toán được trả “success” sau timeout nhưng provider đã hoặc chưa trừ tiền.
- Phân quyền trả allow khi identity provider không có phản hồi.
- Dùng giá/tồn kho cũ để nhận đơn hàng mà không khóa/kiểm tra ràng buộc.
- Trả dữ liệu cache thuộc tenant khác khi upstream 401.
- Ghi event/payment thất bại rồi giả vờ durable write thành công.

Nếu fallback cache có thật, phải định nghĩa TTL/max stale age, cache key theo tenant/user, schema version, provenance, quyền truy cập, response status, X-Degraded marker, staleAgeMillis và chính sách cache miss. Một `CatalogResult(degraded=true)` chỉ là **tín hiệu suy giảm**, không tự biến dữ liệu thành hợp lệ.

## 22. Spring Boot annotation-based Resilience4j khác core API

Dự án dùng Resilience4j starter có thể viết:

```java
@CircuitBreaker(
        name = "catalog",
        fallbackMethod = "fallbackCatalog")
public String getCatalog() {
    return remoteCatalogClient.fetch();
}
```

Đây là **snippet không độc lập**: cần starter/API annotation, import, AOP proxy và fallback method signature đúng version. Khi dùng nó, phải test qua **Spring-managed bean proxy**, không dùng `new Service()` hoặc self-invocation `this.getCatalog()` khiến advice không chạy. Tên breaker trong annotation phải khớp instance config như `resilience4j.circuitbreaker.instances.catalog.*`.

Trong code bài này, chính `CatalogConfiguration` tạo breaker và `CatalogService` gọi `decorateSupplier` trực tiếp, nên **không có AOP aspect giả định**. Đừng thêm annotation rồi bỏ việc kiểm tra Spring proxy.

Với WebFlux, `Mono/Flux`, `WebClient` và Reactor timeout/cancellation là chủ đề riêng. Không gọi blocking `HttpClient.send()` trực tiếp trên event-loop rồi xem nó là nonblocking.

## 23. Telemetry, health và CI

Các metrics nên tách:

| Tín hiệu | Cần quan sát |
| --- | --- |
| Breaker state | CLOSED/OPEN/HALF_OPEN |
| Failure/slow-call rate | Primary dependency health |
| Not-permitted calls | Số call bị breaker chặn |
| HTTP timeouts | Transport timeout thật |
| Fallback count/rate | Trải nghiệm degrade của user |
| 429/5xx upstream | Rate limit/server outage |
| Retry attempts/backoff | Load amplification |
| HTTP pool/bulkhead saturation | Resources bị nghẽn |
| p95/p99 latency | End-to-end user impact |
| Cache stale age | Chất lượng fallback cache |

Nếu thêm Spring Boot Actuator/Micrometer + Resilience4j metrics integration, có thể expose metrics/tracing/health. **Build file của bài chưa thêm các modules đó**, không tuyên bố có sẵn `/actuator/metrics` hoặc health indicators.

**Liveness/readiness:** một optional upstream breaker OPEN không nhất thiết làm liveness fail. Nếu startup/readiness gắn sai vào dependency không cốt lõi, orchestration có thể restart loop trong outage. Quyết định dựa vào khả năng phục vụ chức năng thiết yếu, không theo thói quen.

**CI:** chạy unit/config/MVC tests nhanh trên mỗi commit; loopback HTTP test ở integration job nếu tài nguyên không ổn định. Test không dựa production URL, không hardcode TCP port, không lưu credentials, không bỏ qua timeouts hoặc tự skip những test bắt buộc. Với lỗi timeout, log breaker state, upstream status, elapsed times, config version và thread/connection pool metrics an toàn.

## 24. Debug theo triệu chứng

**A. Request treo mà breaker CLOSED:** breaker không cắt thời gian; kiểm tra connect/request timeout, pool acquisition, DNS/TLS.

**B. Breaker không OPEN sau một lỗi:** `minimumCalls` và failure rate threshold yêu cầu đủ mẫu; kiểm tra window và exception classification.

**C. OPEN nhưng upstream vẫn có request:** những calls đã vào trước khi OPEN có thể còn chạy, hoặc code path bypass breaker/flag off.

**D. Cứ OPEN vĩnh viễn:** kiểm tra open wait, permission trigger, half-open probe kết quả và automatic transition setting.

**E. Fallback luôn trả dù upstream lỗi 401/403:** catch quá rộng; phân loại `Rejected` và auth error.

**F. Breaker không nhận ra lỗi:** fallback bị áp trước breaker hoặc mỗi request tạo breaker mới.

**G. Tests riêng xanh, full suite đỏ:** shared static breaker, context cache, global System properties, HTTP server/executor chưa cleanup.

**H. HTTP server test timeout không đúng:** server có thể chưa nhận request hoặc handler không bị giữ; kiểm tra latch và finite Future get.

**I. Spring AOP annotation không hoạt động:** self-invocation, bean không qua proxy, thiếu starter/AOP hoặc fallback signature sai.

**J. Property override không có tác dụng:** đã tạo bean trước khi sửa config, dùng wrong namespace hoặc Spring context cache.

**K. Retry storm trong production:** max attempts/backoff/deadline/permissions chưa đúng hoặc mọi replica retry cùng lúc.

**L. Degraded response trả giá không hợp lệ:** fallback cache stale không được gắn TTL/authorization, cần fail closed.

## 25. Các lỗi phổ biến

1. Coi circuit breaker là timeout; quên đặt HTTP client timeout.
2. Coi client timeout là bằng chứng server rollback.
3. Bắt mọi exception và fallback 200, che bug/auth lỗi.
4. Đặt fallback bên trong phần breaker đo khiến metrics chỉ thấy success.
5. Mỗi request tạo breaker mới khiến sliding window không tích lũy.
6. Quên minimum calls/threshold; assert OPEN sau một failure.
7. Dùng Thread.sleep để chờ HALF_OPEN mà không hiểu permission transition.
8. Nhầm COUNT_BASED window là số giây.
9. Dùng breaker OPEN như lệnh hủy in-flight requests.
10. Retry `CallNotPermittedException` liên tục.
11. Không có bulkhead/connection pool limit, gây resource exhaustion.
12. Retry write API thiếu idempotency key; tạo side effect trùng.
13. Chỉ dùng Mockito ném timeout rồi gọi là integration HTTP test.
14. Chỉ test request success mà không test 429/5xx/4xx/timeout.
15. Không có ma trận breaker-enabled × fallback-enabled.
16. Config invalid window, minimum, duration được silently accepted.
17. Test annotation-based breaker bằng lời gọi trực tiếp bỏ qua AOP proxy.
18. Nhầm properties custom `app.catalog.*` với Resilience4j starter config.
19. Trả giá/tồn kho/authorization fallback không kiểm chứng.
20. Không gắn degraded marker, stale timestamp hoặc HTTP policy.
21. Dùng cổng loopback cố định trong tests, đụng parallel CI.
22. Không cleanup HTTP server/executor và release latch khi test fail.
23. Assert elapsed time chính xác vài millisecond, gây flaky.
24. Cho rằng fallback thành công nghĩa upstream đã khỏe lại.
25. Thiếu metrics fallback, timeout, open state và breaker not-permitted calls.

## 26. Checklist QA cuối bài

**Kiến trúc và cấu hình:** Có port riêng cho upstream? Timeout đặt trên JDK HttpClient? Breaker bean có lifecycle dài hơn một request? Config record được bind đúng qua `@EnableConfigurationProperties`? Có validate minCalls/window, threshold và duration? Tests cover defaults và overrides?

**Test circuit breaker:** Đủ calls mới OPEN? OPEN không gọi port? HALF_OPEN probes success/fail được kiểm tra? 4xx/cancellation có ignore theo policy? Fallback nằm ngoài breaker decorator? Không dùng sleep và không lẫn state test với thời gian thật?

**Test HTTP:** Có loopback server thật, ephemeral port và request timeout? Có Unicode 200, 500, 400 và stalled response? Có finite timeout và cleanup server/executor/latch? Không tuyên bố client timeout là remote rollback?

**Test fallback/API:** Có flag bật/tắt độc lập? 503 + X-Degraded true và JSON body? Không che 4xx/auth? Không trả dữ liệu cũ có rủi ro? Có typed error advice không lộ secrets? MockMvc test đúng boundary, không nhận nhầm là full E2E?

**Vận hành:** Retry có backoff/deadline/idempotency? Có bulkhead và pool limits? Có p95/p99, breaker state/timeout/fallback metrics? Health/readiness có tránh restart loop? CI không dùng upstream production và không có state leakage?

**Kết luận:** **Timeout** quản lý thời hạn chờ, **circuit breaker** bảo vệ upstream bằng việc dừng các cuộc gọi **mới** khi số liệu xấu, còn **fallback** là phản ứng nghiệp vụ suy giảm có điều kiện. Dùng JUnit kiểm tra state machine không phụ thuộc thời gian, `ApplicationContextRunner` để kiểm tra ma trận cấu hình, loopback HTTP để kiểm tra timeout thật và MockMvc để bảo vệ HTTP contract. Chỉ kết luận trong ranh giới đã thực sự kiểm thử; không suy diễn tính nhất quán, exactly-once hoặc bảo mật từ một kết quả màu xanh.

## 27. Tài liệu tham khảo

- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): states, sliding windows, failure rate, decorators và permission.
- [Resilience4j CircuitBreakerConfig source](https://github.com/resilience4j/resilience4j/blob/master/resilience4j-circuitbreaker/src/main/java/io/github/resilience4j/circuitbreaker/CircuitBreakerConfig.java): builder, failure classification, time configuration.
- [Resilience4j 2.3.0 artifact](https://mvnrepository.com/artifact/io.github.resilience4j/resilience4j-circuitbreaker/2.3.0): version được dùng.
- [Spring Boot 3.5 — External Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): ConfigurationProperties và DefaultValue.
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): ApplicationContextRunner, MockMvc, test slices.
- [Java SE 17 HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): connectTimeout và synchronous send.
- [Java SE 17 HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): request timeout.
- [Java SE 17 HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback test server.
- [Spring Framework MockitoBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): test bean override.
