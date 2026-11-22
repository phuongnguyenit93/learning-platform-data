# Giả lập phụ thuộc chậm, lỗi, mất kết nối hoặc trả dữ liệu không hợp lệ

## 1. Phạm vi bài học và lý do cần fault injection

Trong Spring Boot, một use case thường phải gọi hệ thống bên ngoài: REST API, cơ sở dữ liệu, cache, payment gateway, identity provider, message broker hoặc object storage. Một test chỉ mô phỏng trường hợp `200 OK` và dữ liệu đẹp sẽ bỏ sót những hành vi mà production cần xử lý:

- **Độ trễ:** đối tác accept connection nhưng phản hồi headers hoặc body quá chậm.
- **HTTP errors:** `400`, `401`, `404`, `409`, `429`, `500`, `502`, `503`, `504` với semantics khác nhau.
- **Mất kết nối:** connection refused, connect timeout, socket reset, premature EOF, DNS/TLS failure.
- **Payload lỗi:** body rỗng, JSON sai cú pháp, `Content-Type` không khớp, field thiếu hoặc sai kiểu.
- **Dữ liệu sai nghiệp vụ:** tồn kho âm, ID trong response không trùng ID được yêu cầu, timestamp quá cũ.
- **Phục hồi sai:** retry vô hạn, timeout không giới hạn, fallback trả dữ liệu giả, circuit breaker bị bỏ qua, POST retry tạo duplicate.
- **Lỗi quan sát:** mọi failure bị catch vào một `RuntimeException` chung, không có status/cause và không có chỉ báo về hệ thống nào bị lỗi.

Bài thuộc nhóm **Hợp đồng và khả năng phục hồi**, đề mục **“Giả lập phụ thuộc chậm, lỗi, mất kết nối hoặc trả dữ liệu không hợp lệ”**. Phiên bản ví dụ: **Java 17+**, **Spring Boot 3.3.5**, **Spring Framework 6.1** và **MockWebServer 4.12.0**. Trong phần runnable, ta xây một `CatalogGateway` dùng blocking `RestClient` và giả một HTTP partner bằng server trên `localhost` có cổng động. Đây không phải test gọi internet hoặc đối tác production.

### Những kỹ năng cần nắm

1. Chọn đúng mock layer: Mockito, `MockRestServiceServer`, MockWebServer/WireMock, Testcontainers, provider sandbox.
2. Phân biệt lỗi HTTP **có status** với lỗi mạng **không có HTTP response**.
3. Cấu hình connect/read timeout của HTTP request factory thực.
4. Giả status 404/429/400/503, delay headers, cổng không còn lắng nghe và disconnect giữa body.
5. Đọc JSON thành DTO, kiểm tra syntax/semantics, fail closed khi payload sai.
6. Map framework exceptions thành domain exceptions cho service/controller.
7. Assert đúng request path/method/header và request count.
8. Giữ từng test độc lập, có bounded wait và cleanup.
9. Đánh giá retry/idempotency/circuit breaker/fallback theo loại operation.
10. Phân biệt điều được chứng minh từ mã test với điều chỉ biết sau khi chạy Gradle thật.

## 2. Bốn boundary không được trộn

```text
Người dùng / service gọi CatalogGateway.find(sku)
             |
       [A] Input validation
             | invalid sku -> reject, không mở HTTP
             v
       [B] HTTP client/transport
             | connect, send, wait headers, stream body
             v
       [C] Remote HTTP protocol & JSON
             | status, headers, content type, schema
             v
       [D] Domain mapping
             | ItemMissing / RateLimited
             | RemoteUnavailable / BadRemotePayload
             v
       Caller policy: response, fallback, retry, alert
```

Nếu dùng Mockito để stub `CatalogGateway.find` thì test **không** kiểm tra serialization, URL, transport timeout hay HTTP statuses. Nếu dùng MockRestServiceServer để tạo response trực tiếp trong bộ nhớ, test **không** đi qua DNS/TCP/TLS của request factory. Nếu dùng local MockWebServer, request đi qua real HTTP socket nhưng vẫn không chứng minh provider thực có cùng hợp đồng hoặc cert/proxy production hoạt động.

Một bài kiểm thử tốt phải xác định **tầng nào là subject under test** và **cái gì là controlled test double**.

## 3. Ma trận lỗi và kết quả kỳ vọng

| Fault được mô phỏng | Nguồn lỗi | Kỳ vọng của Gateway ví dụ |
| --- | --- | --- |
| 200 JSON hợp lệ | HTTP body | `InventoryItem` đúng SKU/số lượng |
| 404 | HTTP client error | `ItemMissing` |
| 429 + Retry-After | HTTP rate limit | `RateLimited` giữ nguyên hint |
| 400 | HTTP rejected request | `RemoteRejected` |
| 502/503 | HTTP server error | `RemoteUnavailable` |
| 204 không body | Contract yêu cầu object | `BadRemotePayload` |
| 200 JSON sai cú pháp | JSON decoder | `BadRemotePayload` |
| 200 `available=-4` | Domain invariant | `BadRemotePayload` |
| 200 response SKU sai | Cross-request invariant | `BadRemotePayload` |
| 200 `text/plain` cho DTO | Message converter | `BadRemotePayload` |
| Delay headers vượt read timeout | I/O | `RemoteUnavailable` |
| Port đã đóng, không connect được | TCP | `RemoteUnavailable` |
| Disconnect giữa response | Transport/parser | Không được trả InventoryItem hợp lệ |
| Caller SKU sai | Trước I/O | `IllegalArgumentException`; 0 HTTP requests |
| HTTP 503 nhưng không cấu hình retry | Gateway policy | Chính xác một request |

**Đây là một lựa chọn policy minh họa**, không phải quy định chung cho mọi hệ thống. API khác có thể coi 404 là `Optional.empty()`; HTTP 429 có thể làm job được defer; 502 có thể đi qua fallback. Quyết định phải dựa vào hợp đồng của service thực.

## 4. Chọn công cụ mock phù hợp

| Công cụ | Real TCP? | Tốt nhất cho | Điểm mù |
| --- | --- | --- | --- |
| Mockito mock Gateway/repository | Không | Logic service, branch/retry policy | HTTP mapping/transport chưa chạy |
| `MockRestServiceServer` | Không | REST URL, method, headers, JSON/status | Không dùng socket I/O của client |
| **OkHttp MockWebServer** | **Có**, loopback | Delay, socket close, 429/503, body, request capture | Không đại diện TLS, DNS internet hoặc provider thật |
| WireMock | Có | Scenario state, templating, fault simulation | Nặng hơn một MockWebServer đơn giản |
| Testcontainers PostgreSQL/Kafka/Redis | Có | Driver/protocol/schema/commit thật | Cần container lifecycle và tài nguyên |
| Provider sandbox | Có | Tương thích provider thực | Secrets/rate limits/dữ liệu thay đổi |

Spring Framework hướng dẫn dùng mock web server như OkHttp MockWebServer/WireMock khi cần kiểm tra HTTP client thực, bởi các HTTP clients khác nhau có thể biểu hiện khác nhau ở network boundary. `MockRestServiceServer` vẫn tối ưu cho những contract assertions nhỏ, nhanh và không phụ thuộc socket.

### @RestClientTest và MockRestServiceServer

Ví dụ snippet:

```java
server.expect(requestTo(
        "https://api.example.invalid/v1/inventory/SKU-1"))
    .andExpect(method(HttpMethod.GET))
    .andRespond(withServerError());
```

Snippet này cần một `@RestClientTest` slice, `MockRestServiceServer server`, một client under test và static imports. Nó **không** nằm trong runnable project chính. Khi `RestClient.Builder` dùng trong slice, expected URI là full URL. Với `RestTemplateBuilder.rootUri`, matcher có semantics khác. Nếu production config override `ClientHttpRequestFactory` sau mock binding, client có thể thoát khỏi mock server; hãy kiểm chứng builder/request factory được dùng đúng.

**Không dùng `Thread.sleep` trong mock response creator để khẳng định read timeout của TCP client đã được test.** Với transport faults, dùng một local mock HTTP server thật.

## 5. Connect timeout, read timeout và request deadline

- **Connect timeout** chặn quá trình tạo TCP connection kéo dài. Nếu localhost port đã đóng, OS thường trả “connection refused” ngay; đó **không phải** bằng chứng connect timeout đã hết.
- **Read timeout** chặn một khoảng chờ socket data. Server nhận request nhưng trì hoãn headers là tình huống điển hình.
- **Total deadline** bao gồm connect + request + body + retries/backoffs; không mặc định có nếu chỉ cấu hình connect/read timeout.
- **Gateway/proxy timeout** có thể tạo HTTP 504, khác với Java `SocketTimeoutException`.
- **Read body timeout** phụ thuộc request factory và cách stream response.

Trong Spring Framework 6.1, `SimpleClientHttpRequestFactory` cho phép:

```java
SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory();

factory.setConnectTimeout(Duration.ofSeconds(2));
factory.setReadTimeout(Duration.ofMillis(900));
```

Giá trị trên là **test setup**, không phải SLO khuyến nghị production. Với URLConnection, timeout bằng zero có thể nghĩa là **không giới hạn**; không set zero để mô phỏng một deadline bằng 0.

### Không nên assert elapsed milliseconds chính xác

Nếu test dùng stopwatch và yêu cầu response failure đúng 900 ms ±10 ms, CI có thể fail vì CPU, GC hoặc scheduling. Thay vào đó, để server hoãn headers **3 giây** so với read timeout **900 ms**, và assert category lỗi. Đây là “wide margin”, không đo performance benchmark.

## 6. Cấu trúc project Java 17+ / Spring Boot 3.3.5

```text
catalog-fault-lab/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/faults/
│   ├── FaultLabApplication.java
│   ├── InventoryItem.java
│   ├── CatalogGateway.java
│   ├── RemoteCatalogProperties.java
│   └── RemoteCatalogConfiguration.java
└── src/test/java/com/example/faults/
    └── CatalogGatewayNetworkTest.java
```

Project có class `@SpringBootApplication` và production configuration, nhưng bộ test tạo Gateway qua **cùng factory method dùng trong production** và gọi MockWebServer thật tại localhost. Tests không chạy `@SpringBootTest` vì ta tập trung vào fault injection của HTTP adapter, không phải component scan/web server startup.

MockWebServer 4.12.0 sử dụng package `okhttp3.mockwebserver`. Cách dùng của MockWebServer 5.x có thể khác.

## 7. Gradle scripts

### settings.gradle

```groovy
rootProject.name = 'catalog-fault-lab'
```

### build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter-web` mang Spring Web/`RestClient` và Jackson. `spring-boot-starter-test` mang JUnit Jupiter/AssertJ/Spring Test. `mockwebserver:4.12.0` chỉ vào test classpath, không được thêm vào runtime production.

Nếu chưa có `gradlew`/`gradlew.bat`, dùng Gradle cài sẵn tương thích hoặc tạo Wrapper trước; không coi “script gradlew không tồn tại” là lỗi của bài test.

## 8. Boot application root

`src/main/java/com/example/faults/FaultLabApplication.java`:

```java
package com.example.faults;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FaultLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(FaultLabApplication.class, args);
    }
}
```

`@SpringBootApplication` sẽ scan `RemoteCatalogConfiguration` nếu app được chạy bình thường. Vì demo không chứa endpoint thực, muốn `bootRun` ngoài tests phải cấp `remote.catalog.base-url` và hai timeout properties. Trong test local, base URL đến từ `server.url("/")`, không có dữ liệu production hoặc internet.

## 9. InventoryItem: bảo vệ semantic contract bằng record

`src/main/java/com/example/faults/InventoryItem.java`:

```java
package com.example.faults;

public record InventoryItem(
        String sku,
        int available,
        String warehouse
) {
    public InventoryItem {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank");
        }
        if (available < 0) {
            throw new IllegalArgumentException(
                    "available must be non-negative");
        }
        if (warehouse == null || warehouse.isBlank()) {
            throw new IllegalArgumentException(
                    "warehouse must not be blank");
        }
    }
}
```

Một JSON có thể đúng cú pháp mà sai dữ liệu:

```json
{
  "sku": "SKU-1",
  "available": -4,
  "warehouse": "HCM"
}
```

Canonical constructor từ chối số lượng âm khi Jackson tạo record. Test kiểm tra lỗi này thay vì chỉ tin HTTP `200`.

**Giới hạn:** nếu trường `available` kiểu primitive `int` bị thiếu, Jackson ở một số configuration có thể gán default `0`, nên canonical constructor không tự phân biệt “thiếu field” với “field có giá trị 0”. Nếu hợp đồng cần bắt buộc có trường, dùng DTO có wrapper nullable, Jackson required creator property validation hoặc JSON schema validation theo version/config thật.

Tương tự, unknown JSON fields được ignore hay reject tùy ObjectMapper settings; không khẳng định một policy chỉ từ ví dụ record.

## 10. CatalogGateway: phân loại lỗi framework sang domain

`src/main/java/com/example/faults/CatalogGateway.java`:

```java
package com.example.faults;

import java.net.URI;
import java.time.Duration;
import java.util.Objects;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

public final class CatalogGateway {

    private final RestClient client;

    public CatalogGateway(RestClient client) {
        this.client = Objects.requireNonNull(client);
    }

    public static CatalogGateway forEndpoint(
            RestClient.Builder builder,
            URI baseUrl,
            Duration connectTimeout,
            Duration readTimeout) {

        Objects.requireNonNull(builder);
        Objects.requireNonNull(baseUrl);
        Objects.requireNonNull(connectTimeout);
        Objects.requireNonNull(readTimeout);

        if (connectTimeout.isZero()
                || connectTimeout.isNegative()
                || readTimeout.isZero()
                || readTimeout.isNegative()) {
            throw new IllegalArgumentException(
                    "timeouts must be positive");
        }

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();

        factory.setConnectTimeout(connectTimeout);
        factory.setReadTimeout(readTimeout);

        RestClient restClient = builder
                .baseUrl(baseUrl.toString())
                .requestFactory(factory)
                .build();

        return new CatalogGateway(restClient);
    }

    public InventoryItem find(String sku) {
        if (sku == null
                || !sku.matches("[A-Z0-9-]{2,32}")) {
            throw new IllegalArgumentException("invalid sku");
        }

        try {
            InventoryItem item = client.get()
                    .uri("/v1/inventory/{sku}", sku)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(InventoryItem.class);

            if (item == null) {
                throw new BadRemotePayload(
                        "partner returned empty body");
            }

            if (!sku.equals(item.sku())) {
                throw new BadRemotePayload(
                        "partner returned mismatched sku");
            }

            return item;

        } catch (HttpClientErrorException.NotFound e) {
            throw new ItemMissing(sku, e);

        } catch (HttpClientErrorException.TooManyRequests e) {
            HttpHeaders headers = e.getResponseHeaders();
            String retryAfter = headers == null
                    ? null
                    : headers.getFirst(HttpHeaders.RETRY_AFTER);
            throw new RateLimited(retryAfter, e);

        } catch (HttpServerErrorException e) {
            throw new RemoteUnavailable(
                    "partner HTTP " + e.getStatusCode().value(),
                    e);

        } catch (RestClientResponseException e) {
            throw new RemoteRejected(
                    "partner HTTP " + e.getStatusCode().value(),
                    e);

        } catch (ResourceAccessException e) {
            throw new RemoteUnavailable(
                    "partner transport failure", e);

        } catch (RestClientException e) {
            throw new BadRemotePayload(
                    "partner response cannot be decoded", e);
        }
    }

    public abstract static class PartnerFailure
            extends RuntimeException {
        protected PartnerFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class ItemMissing extends PartnerFailure {
        private ItemMissing(String sku, Throwable cause) {
            super("item not found: " + sku, cause);
        }
    }

    public static final class RateLimited extends PartnerFailure {
        private final String retryAfter;

        private RateLimited(String retryAfter, Throwable cause) {
            super("partner rate limited request", cause);
            this.retryAfter = retryAfter;
        }

        public String retryAfter() {
            return retryAfter;
        }
    }

    public static final class RemoteRejected extends PartnerFailure {
        private RemoteRejected(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class RemoteUnavailable extends PartnerFailure {
        private RemoteUnavailable(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class BadRemotePayload extends PartnerFailure {
        private BadRemotePayload(String message) {
            super(message, null);
        }

        private BadRemotePayload(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

### Thứ tự catch phải đúng

- `HttpClientErrorException.NotFound` → `ItemMissing`.
- `HttpClientErrorException.TooManyRequests` → `RateLimited` và giữ `Retry-After`.
- `HttpServerErrorException` cho status 5xx → `RemoteUnavailable`.
- `RestClientResponseException` cho HTTP status errors còn lại → `RemoteRejected`.
- `ResourceAccessException` cho I/O/transport → `RemoteUnavailable`.
- `RestClientException` khác, thường gồm lỗi message conversion → `BadRemotePayload`.

Nếu đặt `RestClientResponseException` trước các subclasses, các nhánh 404/429/5xx sẽ không được xử lý riêng. Nếu catch mọi `RuntimeException` rồi trả một `InventoryItem(sku,0,"UNKNOWN")`, hệ thống có thể đánh đồng “hết hàng” với “đối tác không thể cung cấp thông tin”; đó là một bug nghiệp vụ nguy hiểm.

### Lỗi domain ném sau khi decode

`BadRemotePayload` do body null hoặc SKU mismatch được ném trong `try` nhưng không thuộc các RestClient exceptions, vì vậy đi ra caller dưới đúng domain type. Lỗi Jackson khi parse JSON/record constructor thường được HTTP message converter wrap, rồi mapping sang `BadRemotePayload`.

### Không retry trong Gateway này

`find` chỉ thực hiện **một HTTP call**. Không có `@Retryable`, circuit breaker hay resilience decorator. Những chính sách ấy thuộc tầng riêng và phải có tests riêng. Việc đặt hai MockWebServer responses vào queue **không tự làm RestClient retry**.

### Không leak token hoặc raw upstream response

Domain error message chỉ nêu category/status, không lộ Authorization header, raw user data hoặc upstream response body. Cause có thể được giữ trong logs nội bộ có kiểm soát; API outward nên map thành error code ổn định, không trả stack trace.

## 11. Production-style configuration và properties

`src/main/java/com/example/faults/RemoteCatalogProperties.java`:

```java
package com.example.faults;

import java.net.URI;
import java.time.Duration;
import java.util.Objects;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "remote.catalog")
public record RemoteCatalogProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout
) {
    public RemoteCatalogProperties {
        Objects.requireNonNull(baseUrl, "baseUrl");
        Objects.requireNonNull(connectTimeout, "connectTimeout");
        Objects.requireNonNull(readTimeout, "readTimeout");
        if (!"http".equalsIgnoreCase(baseUrl.getScheme())
                && !"https".equalsIgnoreCase(baseUrl.getScheme())) {
            throw new IllegalArgumentException(
                    "base-url must be http or https");
        }
        if (connectTimeout.isZero() || connectTimeout.isNegative()
                || readTimeout.isZero() || readTimeout.isNegative()) {
            throw new IllegalArgumentException(
                    "timeouts must be positive");
        }
    }
}
```

`src/main/java/com/example/faults/RemoteCatalogConfiguration.java`:

```java
package com.example.faults;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RemoteCatalogProperties.class)
public class RemoteCatalogConfiguration {

    @Bean
    CatalogGateway catalogGateway(
            RestClient.Builder builder,
            RemoteCatalogProperties properties) {
        return CatalogGateway.forEndpoint(
                builder,
                properties.baseUrl(),
                properties.connectTimeout(),
                properties.readTimeout());
    }
}
```

Một đoạn **cấu hình minh họa cho ứng dụng dùng module** (không cần lưu vào project test) có thể là:

```yaml
remote:
  catalog:
    base-url: https://catalog.example.invalid
    connect-timeout: 2s
    read-timeout: 900ms
```

Domain `example.invalid` cố ý không phải endpoint production. Trong môi trường thực, URL được inject qua environment/secret configuration và dùng TLS/credentials phù hợp. Trong JUnit test, endpoint được tạo bằng `MockWebServer.url("/")` nên **không** phụ thuộc file YAML này.

### RestClient.Builder và request factory

Spring Boot cung cấp managed `RestClient.Builder` cho ứng dụng. Configuration gọi cùng static factory `CatalogGateway.forEndpoint(...)` mà test dùng. Ví dụ chủ động đặt `SimpleClientHttpRequestFactory` để tránh sự khác biệt khi classpath khiến RestClient chọn request factory khác. Nếu production chuyển sang Apache HttpClient, JDK HttpClient hoặc Reactor Netty, hãy viết test transport với **đúng factory production** trước khi suy rằng timeout/disconnect semantics tương đương.

### Vì sao không dùng @RestClientTest cho test timeout?

`@RestClientTest` + `MockRestServiceServer` thường gắn một mock `ClientHttpRequestFactory` vào builder. Trong ví dụ production factory tự đặt `SimpleClientHttpRequestFactory`, vì vậy một slice test không cấu hình đúng có thể **bỏ qua mock binding** và thật sự gọi URL bên ngoài. Bài dùng MockWebServer ở localhost để chạy HTTP request factory thực. Khi viết slice test riêng, import config và wiring mock đúng framework version.

## 12. CatalogGatewayNetworkTest.java: bộ kiểm thử fault injection

`src/test/java/com/example/faults/CatalogGatewayNetworkTest.java`:

```java
package com.example.faults;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import okhttp3.mockwebserver.SocketPolicy;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CatalogGatewayNetworkTest {

    private MockWebServer server;
    private CatalogGateway gateway;

    @BeforeEach
    void startServer() throws IOException {
        server = new MockWebServer();
        server.start();
        gateway = CatalogGateway.forEndpoint(
                RestClient.builder(),
                server.url("/").uri(),
                Duration.ofSeconds(2),
                Duration.ofMillis(900));
    }

    @AfterEach
    void shutdownServer() throws IOException {
        if (server != null) {
            server.shutdown();
        }
    }

    private MockResponse json(int status, String body) {
        return new MockResponse()
                .setResponseCode(status)
                .setHeader("Content-Type", "application/json")
                .setBody(body);
    }

    private String item(String sku, int available) {
        return """
                {
                  "sku": "%s",
                  "available": %d,
                  "warehouse": "HCM"
                }
                """.formatted(sku, available);
    }

    @Test
    void validResponseReturnsItemAndUsesExpectedRequest()
            throws Exception {
        server.enqueue(json(200, item("SKU-1", 12)));

        InventoryItem actual = gateway.find("SKU-1");

        assertEquals(
                new InventoryItem("SKU-1", 12, "HCM"), actual);

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/v1/inventory/SKU-1", request.getPath());
        assertEquals("application/json",
                request.getHeader("Accept"));
        assertEquals(1, server.getRequestCount());
    }

    @Test
    void notFoundHasItsOwnDomainError() {
        server.enqueue(json(404,
                "{\"error\":\"missing\"}"));

        CatalogGateway.ItemMissing error = assertThrows(
                CatalogGateway.ItemMissing.class,
                () -> gateway.find("SKU-2"));

        assertTrue(error.getMessage().contains("SKU-2"));
        assertEquals(1, server.getRequestCount());
    }

    @Test
    void rateLimitRetainsRetryAfterHint() {
        server.enqueue(
                json(429, "{\"error\":\"too_many\"}")
                        .setHeader("Retry-After", "120"));

        CatalogGateway.RateLimited error = assertThrows(
                CatalogGateway.RateLimited.class,
                () -> gateway.find("SKU-3"));

        assertEquals("120", error.retryAfter());
        assertEquals(1, server.getRequestCount());
    }

    @Test
    void serviceUnavailableIsNotReportedAsMissing() {
        server.enqueue(json(503,
                "{\"error\":\"unavailable\"}"));

        CatalogGateway.RemoteUnavailable error = assertThrows(
                CatalogGateway.RemoteUnavailable.class,
                () -> gateway.find("SKU-4"));

        assertTrue(error.getMessage().contains("503"));
    }

    @Test
    void badGateway502MapsToUnavailable() {
        server.enqueue(json(502, "{\"error\":\"bad_gateway\"}"));

        assertThrows(
                CatalogGateway.RemoteUnavailable.class,
                () -> gateway.find("SKU-5"));
    }

    @Test
    void client400IsNotTransientOutage() {
        server.enqueue(json(400,
                "{\"error\":\"invalid_input\"}"));

        CatalogGateway.RemoteRejected error = assertThrows(
                CatalogGateway.RemoteRejected.class,
                () -> gateway.find("SKU-6"));

        assertTrue(error.getMessage().contains("400"));
    }

    @Test
    void malformedJsonIsBadRemotePayload() {
        server.enqueue(json(200, "{\"sku\":"));

        CatalogGateway.BadRemotePayload error = assertThrows(
                CatalogGateway.BadRemotePayload.class,
                () -> gateway.find("SKU-7"));

        assertNotNull(error.getCause());
    }

    @Test
    void negativeAvailableQuantityIsRejected() {
        server.enqueue(json(200, item("SKU-8", -4)));

        assertThrows(
                CatalogGateway.BadRemotePayload.class,
                () -> gateway.find("SKU-8"));
    }

    @Test
    void wrongSkuInValidJsonIsRejected() {
        server.enqueue(json(200, item("DIFFERENT", 10)));

        CatalogGateway.BadRemotePayload error = assertThrows(
                CatalogGateway.BadRemotePayload.class,
                () -> gateway.find("SKU-9"));

        assertTrue(error.getMessage().contains("mismatched"));
    }

    @Test
    void empty204BodyIsRejected() {
        server.enqueue(new MockResponse().setResponseCode(204));

        assertThrows(
                CatalogGateway.BadRemotePayload.class,
                () -> gateway.find("SKU-10"));
    }

    @Test
    void wrongContentTypeCannotSilentlyMapToDto() {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "text/plain")
                .setBody(item("SKU-11", 7)));

        assertThrows(
                CatalogGateway.BadRemotePayload.class,
                () -> gateway.find("SKU-11"));
    }

    @Test
    void smallHeaderDelayFitsReadBudget() {
        server.enqueue(
                json(200, item("SKU-12", 5))
                        .setHeadersDelay(
                                100, TimeUnit.MILLISECONDS));

        assertEquals(
                new InventoryItem("SKU-12", 5, "HCM"),
                gateway.find("SKU-12"));
    }

    @Test
    void excessiveHeaderDelayBecomesUnavailable() {
        server.enqueue(
                json(200, item("SKU-13", 2))
                        .setHeadersDelay(3, TimeUnit.SECONDS));

        CatalogGateway.RemoteUnavailable error = assertThrows(
                CatalogGateway.RemoteUnavailable.class,
                () -> gateway.find("SKU-13"));

        assertNotNull(error.getCause());
        assertEquals(1, server.getRequestCount());
    }

    @Test
    void closedPortBecomesConnectionFailure()
            throws Exception {
        server.shutdown();
        server = null;

        CatalogGateway.RemoteUnavailable error = assertThrows(
                CatalogGateway.RemoteUnavailable.class,
                () -> gateway.find("SKU-14"));

        assertNotNull(error.getCause());
    }

    @Test
    void disconnectDuringBodyNeverProducesValidItem() {
        server.enqueue(
                json(200, item("SKU-15", 7))
                        .setSocketPolicy(
                            SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY));

        // I/O error hoặc lỗi JSON bị cắt tùy HTTP client.
        CatalogGateway.PartnerFailure error = assertThrows(
                CatalogGateway.PartnerFailure.class,
                () -> gateway.find("SKU-15"));

        assertTrue(
                error instanceof CatalogGateway.RemoteUnavailable
                || error instanceof CatalogGateway.BadRemotePayload);
    }

    @Test
    void invalidInputFailsBeforeAnyHttpRequest() {
        assertThrows(
                IllegalArgumentException.class,
                () -> gateway.find("../etc/passwd"));

        assertEquals(0, server.getRequestCount());
    }

    @Test
    void gatewayDoesNotRetry503ByItself() {
        server.enqueue(json(503,
                "{\"error\":\"temporary\"}"));
        server.enqueue(json(200, item("SKU-16", 100)));

        assertThrows(
                CatalogGateway.RemoteUnavailable.class,
                () -> gateway.find("SKU-16"));

        assertEquals(1, server.getRequestCount());
    }
}
```

**Bộ mã có 17 phương thức `@Test`**, không tính `@BeforeEach` và `@AfterEach`. Các tên SKU/response fixtures là dữ liệu tổng hợp, không phải tài khoản hoặc mã sản phẩm thực.

### Per-test server thay vì shared queue

Mỗi test tạo một `MockWebServer` riêng qua `@BeforeEach`, port động theo `server.start()`. `@AfterEach` đóng server để không leak sockets/threads. Nếu dùng một server static cho nhiều tests, responses trong queue và delayed requests có thể rò qua test khác gây flaky; đừng làm vậy nếu không có lifecycle/isolation rõ.

Trong test cổng đóng, ta dừng server và đặt field `server=null` để cleanup không gọi shutdown lại. `CatalogGateway` vẫn giữ URI loopback cũ; request sau đó nhận transport error, không gọi DNS/internet.

### Bounded request capture

`takeRequest(2, TimeUnit.SECONDS)` giới hạn thời gian chờ mock ghi nhận request. `getRequestCount()` giúp bảo vệ “không retry bất ngờ” hoặc “validate trước I/O”. Nếu test thật có retry từ HTTP implementation, số request có thể nhiều hơn mong đợi; cần biết đó là automatic transport retry hay resilience decorator.

### Delay và socket policy

- `setHeadersDelay(100, MILLISECONDS)`: vẫn trong budget 900 ms, mong thành công.
- `setHeadersDelay(3, SECONDS)`: vượt read timeout, mong `RemoteUnavailable`.
- `DISCONNECT_DURING_RESPONSE_BODY`: cắt body giữa chừng. URLConnection có thể ném I/O hoặc Jackson có thể gặp JSON bị cắt; bài assert fail-closed thay vì một low-level exception type cứng.
- `server.shutdown()` trước request: mô phỏng closed local port (connection refused) một cách có kiểm soát.

**Không dùng `Thread.sleep` trong test body.** MockWebServer điều khiển độ trễ ở HTTP server; client timeout điều khiển failure boundary.

## 13. Giải thích riêng từng nhánh quan trọng

### 13.1. 404, 429 và 503 là ba chuyện khác nhau

HTTP 404 là tài nguyên không có theo hợp đồng; 429 nghĩa là đang bị giới hạn; 503 nghĩa là dịch vụ không sẵn. Nếu map cả ba thành `RemoteUnavailable` rồi retry giống nhau, có thể tạo load storm, làm xấu UX và che lỗi điều kiện nghiệp vụ.

`RateLimited` giữ nguyên `Retry-After` **dạng String**. HTTP `Retry-After` có thể là số giây hoặc HTTP date; đừng parse mặc định bằng `Integer.parseInt`, đừng tin một hint vô lý và đừng sleep vô hạn. Một retry policy production phải clamp theo SLO/deadline và thêm jitter.

### 13.2. HTTP 400 có response, nhưng lỗi socket không có status

`RestClient.retrieve()` mặc định chuyển status 4xx/5xx thành HTTP exceptions. `HttpClientErrorException` chứa status/header/body. `ResourceAccessException` bao quanh những tình huống I/O như connect/read timeout. Không đọc `getStatusCode()` từ `ResourceAccessException` vì không có HTTP status nào được server trả một cách đáng tin.

### 13.3. 200 không đồng nghĩa một DTO hợp lệ

Có ba tầng:

1. **Content-type/codec**: decoder có đọc được body?
2. **Structure/semantics**: DTO có required fields, quantity hợp lệ?
3. **Consistency**: response có đúng `sku` request không?

`BadRemotePayload` bảo vệ cả body null, JSON hỏng và semantic mismatch. Trong hệ thống lớn có thể tách thêm `UpstreamSchemaViolation`, `UpstreamDataIntegrityViolation`, nhưng đừng trả một object giả khi không biết dữ liệu.

### 13.4. Error body không phải success body

Khi server trả 503 với JSON error envelope, `retrieve()` mặc định tạo status exception trước khi cố decode thành `InventoryItem`. Test không nên assert lỗi JSON parse của error body; việc kiểm tra upstream error schema là một contract riêng nếu app dùng error code từ provider.

### 13.5. Thời gian chậm và mất kết nối phải được phân biệt

Server trì hoãn headers tạo read timeout; port đóng gây connection refusal; socket bị cắt giữa response gây EOF/reset hoặc JSON parsing error. Cả ba có thể trở thành `RemoteUnavailable` hoặc `BadRemotePayload` theo policy nhưng metric/log nên giữ phân loại cause. HTTP 504 từ gateway lại là một **HTTP status response**, không phải low-level timeout trên client.

### 13.6. Không kiểm tra signature/TLS/proxy bằng localhost HTTP

MockWebServer trên `http://localhost` không xác nhận TLS truststore, proxy credentials, DNS caching, WAF hay real provider. Nếu cần TLS test, dùng local HTTPS test server và test certificate authority; không tắt certificate validation trong production để suite chạy xanh.

## 14. MockRestServiceServer: nhanh nhưng khác bản chất

Một REST-client slice minh họa:

```java
@RestClientTest(SomeInventoryClient.class)
class InventoryClientSliceTest {
    @Autowired SomeInventoryClient client;
    @Autowired MockRestServiceServer mockServer;

    @Test
    void mapsHttp503() {
        mockServer.expect(requestTo(
                "https://partner.example.invalid/v1/inventory/SKU-1"))
                .andRespond(withServerError());

        assertThrows(
                SomeUnavailableException.class,
                () -> client.find("SKU-1"));
        mockServer.verify();
    }
}
```

**Đây là snippet kiến trúc, không thuộc runnable project**: các tên `SomeInventoryClient`/`SomeUnavailableException` là ví dụ minh họa cho một app khác. Để dùng thật phải định nghĩa component, import production client configuration, bean dependencies và static imports. Với `RestClient.Builder`, matcher nên dùng **full URL**; với `RestTemplateBuilder.rootUri` có sự khác nhau trong expectations.

`MockRestServiceServer` tuyệt vời để assert URL/method/headers/body/status, nhưng nó không mở socket và không bảo đảm HTTP client's timeout behavior. Nếu test yêu cầu disconnect/EOF hoặc proxy, dùng MockWebServer, WireMock hay network fault tool.

## 15. Nhớ rằng failure của server có thể bất định về exception lớp thấp

Khi dùng `DISCONNECT_DURING_RESPONSE_BODY`:

- Có HTTP clients kiểm tra `Content-Length`/stream EOF và ném I/O.
- Có clients cung cấp body bị cắt cho JSON parser, tạo decode error.
- Có client tự retry một safe GET trước khi application thấy error, tùy chính sách internal retry.

Vì vậy unit/integration test **cấp domain** nên bảo vệ “không trả dữ liệu thành công khi response bị cắt”. Nếu hệ thống yêu cầu tách chính xác `RemoteUnavailable` với `BadRemotePayload`, hãy khóa HTTP implementation/version/config và viết **transport adapter test** riêng để bảo đảm classification, thay vì ràng buộc behavior không portable vào mọi HTTP client.

Đừng tự động retry một POST payment/reservation sau premature EOF: server có thể đã tạo side effect trước khi client mất response. Cần idempotency key, status inquiry/reconciliation hoặc outbox.

## 16. Timeout budget và retry policy

Một operation có deadline 2 giây không thể cho phép mỗi request retry 3 lần × read timeout 2 giây + backoff rồi vẫn mong trả trong 2 giây.

| Policy | Nên cân nhắc |
| --- | --- |
| GET idempotent gặp 503 | Có thể retry ít lần, backoff/jitter, còn deadline |
| GET gặp 429 | Tôn trọng Retry-After nếu budget cho phép |
| GET gặp 404 | Thường không retry |
| GET gặp JSON sai schema | Thường không retry; alert contract |
| POST không có idempotency key | Không retry mù khi network uncertainty |
| Circuit breaker OPEN | Fail fast, không gửi request |
| Fallback cached inventory | Dữ liệu có TTL/tenant/freshness rõ |
| Long-running batch job | Retry/reconciliation theo job/item identity |

Một design hợp lý có thể dùng Resilience4j Retry, CircuitBreaker, TimeLimiter hoặc Bulkhead; các library này **không tự có trong project mẫu**. Nếu thêm chúng, test riêng:
- số attempts;
- thời gian/total budget;
- exception predicates;
- circuit transitions;
- bulkhead saturation;
- idempotency và không duplicate side effects.

**Đừng gọi MockWebServer.enqueue(503), enqueue(200) là “đã test retry”** nếu code không có retry. Test `gatewayDoesNotRetry503ByItself` xác minh request count bằng 1, dù mock đã xếp response thứ hai.

## 17. Những trường hợp JSON cần bổ sung

| Payload | Câu hỏi |
| --- | --- |
| JSON malformed | Converter có từ chối? |
| JSON object thiếu `sku` | Constructor/validation có chặn? |
| `available=-1` | Domain invariant có chặn? |
| `available=null` | Jackson primitive config có âm thầm dùng 0? |
| `available="not-a-number"` | Decoder có từ chối type mismatch? |
| `warehouse=""` | Domain invariant có chặn? |
| SKU khác request | Cross-request check có chặn? |
| Field extra | Có cho phép backward-compatible extension? |
| Response là array thay object | Converter có từ chối wrong shape? |
| JSON rất lớn/deep | Có size/nesting limit để tránh memory pressure? |
| Timestamp cũ | Cache/freshness policy có kiểm tra? |
| Currency hoặc price precision | Có dùng BigDecimal/minor units đúng? |

**Không nên dựa vào việc serialize rồi deserialize cùng DTO để chứng minh provider contract**: hai phía của test có thể cùng hiểu sai field name. Dùng literal JSON fixtures lấy từ versioned schema/provider contract, và test negative examples.

## 18. Fault injection với các dependencies ngoài HTTP

### Database

Nếu dependency là PostgreSQL, simulate:
- constraint violation bằng schema/fixtures;
- deadlock bằng concurrency được điều khiển bởi barriers;
- DB disconnect bằng dedicated Testcontainer/Toxiproxy;
- query timeout bằng driver/server timeout phù hợp;
- transaction rollback bằng business DB assertions.

Không dùng MockWebServer để kiểm tra JDBC. `DataAccessException`/driver exception hierarchy khác RestClient exceptions. Không stop database chung của đồng nghiệp hoặc CI suite.

### Kafka/RabbitMQ

Kafka producer ACK không chứng minh consumer đã xử lý; RabbitMQ publisher confirm khác consumer ACK. Simulate broker disconnect, nack, deserialization failure, retry/rebalance hoặc DLQ bằng test broker/containers riêng. Với non-durable publish, message có thể mất; cần idempotency/durable outbox để bảo vệ business contract.

### Redis/cache

Phân biệt **cache miss** với Redis unavailable. Test fail-open/fail-closed theo nghiệp vụ. Toxiproxy giúp tiêm latency/disconnect vào connection tới dedicated Redis container. Không trả giá trị cache mặc định giả rồi coi là miss hợp lệ nếu data correctness quan trọng.

### Reactive/WebClient

`WebClient` dùng `WebClientResponseException` cho HTTP status lỗi và `WebClientRequestException` cho transport lỗi, không dùng lại `RestClientException` mapping một cách máy móc. Với Reactor `timeout`/retry/backoff, `StepVerifier.withVirtualTime` có thể test operator timing; nhưng virtual time **không thay thế** TCP socket timeout thực ở Netty. MockWebServer/WireMock vẫn hữu ích cho network tests.

## 19. Observability cho downstream failures

Một Gateway production nên phát metrics/logs/traces có **labels bounded**:

- dependency logical name: `catalog`;
- operation: `getInventory`;
- outcome: `success`, `not_found`, `throttled`, `http_5xx`, `timeout`, `connection_error`, `bad_payload`;
- HTTP status khi có response;
- attempt count/retry reason;
- duration, circuit breaker state;
- trace/correlation ID an toàn.

**Không gắn SKU/order ID/full URL/query token thành metric tags** vì high cardinality và nguy cơ PII leak. Nếu có `ObservationRegistry` hoặc `MeterRegistry` thật, test có thể inject test registry rồi assert metric sau controlled fault. Bộ mã hiện tại không instrument metrics, nên không được nói test đã xác minh telemetry.

## 20. Kết quả trả cho caller không phải lúc nào giống downstream status

| Gateway domain failure | Inbound API policy khả dĩ | Cẩn trọng |
| --- | --- | --- |
| `ItemMissing` | 404 | Chỉ khi phù hợp domain |
| `RateLimited` | 429/503 | Upstream quota có thể khác user quota |
| `RemoteUnavailable` | 503 | Không leak nội bộ |
| `RemoteRejected` | 502 hoặc lỗi cấu hình | Upstream 401 không phải user unauthenticated |
| `BadRemotePayload` | 502 | Không trả stock=0 |
| Input invalid | 400 | Validate trước HTTP |

Một `@RestControllerAdvice` có thể map domain exceptions sang `ProblemDetail`/structured error code có correlation ID. Hãy test controller mapping riêng với `MockMvc`. Đừng trả raw body/headers/token của upstream vào response người dùng cuối.

## 21. Không đồng nhất lỗi business với lỗi network

Nếu partner trả 404 cho một SKU không tồn tại, đó không nhất thiết là degradation. Nếu partner trả HTTP 200 chứa số âm, đây là **contract violation** dù network khỏe. Nếu partner trả 503, API của app có thể fail sớm hoặc trả stale cache có nhãn rõ, tùy UX; không nên suy thành “không còn hàng”.

Với payment/order workflow, network timeout có thể là **unknown outcome**: một server có thể đã commit giao dịch nhưng response bị cắt. Policy phải có idempotency key, payment status query hoặc reconciliation, không đơn giản retry rồi nhận double charge.

## 22. Làm sao để test timeout không flaky?

1. Dùng mock server trên loopback và port do OS cấp, không host internet.
2. Mock delay **cách xa** client timeout (trong ví dụ 3s vs 900ms).
3. Không dùng `Thread.sleep` trong test thread.
4. Không assert exact elapsed milliseconds của OS/JDK.
5. Đóng server trong `@AfterEach` ngay cả khi assertion fail.
6. Nếu setup server fail do CI policy, phân biệt failure môi trường với failure domain.
7. Không để vô hạn `NO_RESPONSE` khi read timeout chưa được set.
8. Nếu test chạy parallel, mỗi test có response queue/server riêng.
9. Không dùng shared mutable static request counters.
10. Không tự sửa system-wide proxy/firewall/DNS cho một test nhỏ.
11. Nếu kiểm tra connect timeout thật, cần môi trường kiểm soát network blackhole/SYN drop; closed port chỉ xác minh **connection refused**.
12. Với body/chunk timeout, dùng `setBodyDelay`/`throttleBody` và request factory thực.
13. Luôn giới hạn tổng request deadline và retry budget của production code.

### SocketPolicy không phải mọi kiểu lỗi đều giống nhau

MockWebServer có `DISCONNECT_AT_START`, `DISCONNECT_DURING_RESPONSE_BODY` và `NO_RESPONSE`. Một HTTP client có thể tự retry safe methods hoặc wrap EOF thành decoder error. Vì vậy test phải xác định muốn bảo vệ **network classification** hay **fail-closed outcome**, và tránh ràng buộc mọi transport implementation vào cùng một class IOException.

## 23. Provider contract verification cần tồn tại ngoài consumer mock

MockWebServer trả đúng những bytes mà test author viết; nếu author hiểu sai provider API thì test vẫn có thể xanh. Với hợp đồng thực:

- Dùng OpenAPI/JSON Schema/AsyncAPI/Pact nếu thích hợp.
- Verify provider responses/headers/error semantics ở provider CI hoặc sandbox.
- Pin API version và test backward compatibility.
- Không dùng production secrets hoặc PII trong fixtures.
- Test unknown fields/new enum values theo policy rõ.
- Có incident tests cho key rotation/auth failures nếu service dùng OAuth/TLS.
- Kiểm tra server-side schema và consumer mapping ở các tầng khác nhau.

Fault-injection tests trả lời: “Khi dependency vi phạm/không đáp ứng, **ứng dụng của ta** có phản ứng an toàn và đúng chính sách không?” Chúng không tự chứng minh đối tác luôn cung cấp schema mà ta giả lập.

## 24. Debug failures theo thứ tự

1. Xác nhận test đang thực sự dùng `server.url("/")` từ MockWebServer.
2. Kiểm tra `RestClient.Builder` và `SimpleClientHttpRequestFactory` được cấu hình/khởi tạo đúng.
3. Đảm bảo `server.enqueue(...)` xảy ra trước `gateway.find(...)`.
4. Kiểm tra actual request path/method/Accept qua `RecordedRequest`.
5. Phân biệt HTTP status error với `ResourceAccessException`.
6. Kiểm tra catch-order của 404/429/5xx.
7. Với JSON lỗi, xem media type/converter/record constructor.
8. Với negative quantities/mismatched IDs, kiểm tra domain invariant không bị bypass.
9. Với delayed response, kiểm tra delay là header hay body.
10. Với closed port, xác nhận server đã shutdown trước khi gateway gọi.
11. Với mid-body disconnect, xem cause chain và policy fail-closed.
12. Với retry unexpected, xem underlying HTTP client internal retries và resilience decorator.
13. Nếu test chỉ fail trên CI, xem resource/socket limits và test parallelism.
14. Nếu production khác local test, so sánh HTTP implementation, proxy, TLS và contract version.
15. Đọc JUnit report thật, không đổi expected assertion để “cho xanh” khi chưa hiểu lỗi.

## 25. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân | Giải pháp |
| --- | --- | --- |
| Timeout test trả 200 | Delay quá nhỏ hoặc sai phase | setHeadersDelay vượt read timeout với biên đủ rộng |
| Test treo vô hạn | NO_RESPONSE mà không có timeout | Bounded deadline và cleanup |
| MockRestServiceServer không tái hiện TCP reset | Không real socket | MockWebServer/WireMock |
| Mockito test pass nhưng timeout production không có | Mock sai tầng | Test request factory thực |
| Closed port bị hiểu thành 503 | Không có HTTP response | Map ResourceAccessException riêng |
| 404 bị retry liên tục | Predicate retry quá rộng | Phân loại status |
| 429 bỏ qua Retry-After | Không giữ/parse header | Test hint và clamp budget |
| Stock “0” khi partner down | Dangerous fallback | Unknown/unavailable domain state |
| JSON lỗi nhưng test vẫn pass | Chỉ kiểm tra HTTP status | Decode và domain validation |
| DTO quantity âm được chấp nhận | Thiếu invariant | Record constructor/validation |
| Payload SKU không khớp | Không check consistency | Assert requested SKU |
| Disconnect trả hai loại lỗi tùy HTTP client | I/O/parse boundary khác | Fail-closed + transport test riêng |
| Test không chạy trên CI | Không tạo socket được, deps không tải | Environmental diagnosis |
| Test pass riêng nhưng fail cả suite | Shared mock server/response queue | Per-test setup/teardown |
| Retry POST tạo duplicates | Không có idempotency | Key, dedup, status reconciliation |
| Log rò Authorization header | Raw request logging | Redact/truncate structured logs |
| Circuit-breaker flaky | Wall-clock sleeps | Controllable clock/state tests |
| Test chính xác exception message OS | OS/JDK khác | Assert domain type/cause class |

## 26. Ma trận test của project

| Test method | Điều bảo vệ |
| --- | --- |
| `validResponseReturnsItemAndUsesExpectedRequest` | 200, DTO, GET path, Accept |
| `notFoundHasItsOwnDomainError` | 404 → ItemMissing |
| `rateLimitRetainsRetryAfterHint` | 429, Retry-After |
| `serviceUnavailableIsNotReportedAsMissing` | 503 → Unavailable |
| `badGateway502MapsToUnavailable` | 502 → Unavailable |
| `client400IsNotTransientOutage` | 400 → RemoteRejected |
| `malformedJsonIsBadRemotePayload` | JSON syntax lỗi |
| `negativeAvailableQuantityIsRejected` | Semantic quantity |
| `wrongSkuInValidJsonIsRejected` | Cross-response ID |
| `empty204BodyIsRejected` | Không body |
| `wrongContentTypeCannotSilentlyMapToDto` | MIME mismatch |
| `smallHeaderDelayFitsReadBudget` | Delay vừa phải |
| `excessiveHeaderDelayBecomesUnavailable` | Read timeout |
| `closedPortBecomesConnectionFailure` | Connection refused |
| `disconnectDuringBodyNeverProducesValidItem` | Premature EOF fail closed |
| `invalidInputFailsBeforeAnyHttpRequest` | Validate trước HTTP |
| `gatewayDoesNotRetry503ByItself` | Không implicit application retry |

**Tổng 17 phương thức `@Test`** tính từ mã nguồn. Kết quả 200/error types ở bảng là expected assertions, **không phải các lần test đã được thực thi thành công**.

## 27. Chạy dự án

Nếu project có Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.faults.CatalogGatewayNetworkTest'
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu chỉ có Gradle tương thích đã cài:

```bash
gradle test
```

JUnit/Gradle reports thường xuất hiện tại:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

Các test không gọi `System.out.println` và không có stdout nghiệp vụ cố định. Không bịa ra output “17 PASSED” khi chưa chạy. Đọc số passed/failed/skipped thật từ report khi thực hành.

## 28. Bài tập thực hành

1. Chạy một test thành công và dùng `RecordedRequest` kiểm tra request URI/header.
2. Đổi response 200 thành 404, xác nhận ItemMissing không bị retry.
3. Trả 429 với Retry-After dạng HTTP-date; triển khai parser an toàn có clamp.
4. Mô phỏng 503 rồi 200; thêm retry policy 2 attempts cho GET và kiểm tra requestCount.
5. Gắn idempotency key vào POST giả, test uncertainty sau disconnect.
6. Đổi read timeout và mock headers delay, không assert exact elapsed ms.
7. Dùng `setBodyDelay` thay `setHeadersDelay` để kiểm tra body read.
8. Dùng `NO_RESPONSE` có bounded timeout để thử read deadline.
9. Thử `DISCONNECT_DURING_RESPONSE_BODY` với Apache HttpClient, so sánh cause.
10. Thêm JSON thiếu `sku` và xác nhận domain validation.
11. Thêm JSON thiếu primitive `available`, cải thiện DTO required-field policy.
12. Thêm JSON extra field, quyết định forward-compatible hay strict.
13. Dùng WireMock scenario mô phỏng service lỗi 503 rồi recover 200.
14. Viết `@RestClientTest` riêng chỉ assert URL/method/status, so sánh không có TCP.
15. Thêm `@RestControllerAdvice` trả `ProblemDetail` cho gateway errors.
16. Dùng SimpleMeterRegistry đo downstream outcome labels.
17. Thêm cache fallback có freshness TTL; test data quá cũ bị từ chối.
18. Test database down bằng dedicated Testcontainer/Toxiproxy, không tắt DB chung.
19. Viết WebClient version với `WebClientRequestException` và `StepVerifier`.
20. Chạy cả suite và đọc Gradle reports, phân tích case flaky theo root cause.

## 29. Checklist QA trước khi merge

- [ ] Đã chọn đúng mock boundary và nêu rõ điều test không thể chứng minh?
- [ ] Có success + request method/path/header assertions?
- [ ] Có HTTP 404, 429, 400 và 5xx tests?
- [ ] Có chặn body rỗng, JSON hỏng, data semantic invalid và ID mismatch?
- [ ] Có test Content-Type mismatch?
- [ ] Có test timeout bằng delayed headers/body trên real local HTTP server?
- [ ] Có test server closed/connection failure và mid-response drop?
- [ ] Có bounded client timeouts, không sleep vô hạn?
- [ ] Có phân biệt connect timeout, read timeout và total deadline?
- [ ] Có domain error types không rò raw response/secrets?
- [ ] Có test không retry ngoài policy?
- [ ] Có idempotency strategy cho non-idempotent operations?
- [ ] Có test fallback không biến unknown data thành giá trị hợp lệ?
- [ ] Có per-test mock server/response isolation?
- [ ] Không gọi production endpoint/Internet từ tests?
- [ ] Không assert exact low-level IOException text hoặc wall-clock latency?
- [ ] Nếu có circuit breaker/retry, có tests cho state/attempt/deadline?
- [ ] Nếu metrics là requirement, có instrument registry thật?
- [ ] Có provider contract verification riêng khi cần?
- [ ] CI tests không dùng chung DB/broker để inject outage?
- [ ] Đã đọc report thực tế trước khi nói PASS?

## 30. Tài liệu chính thức

- [Spring Framework — Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): MockRestServiceServer và mock web server trên real network.
- [Spring Framework 6.1 — SimpleClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html): connect/read timeout với Duration.
- [Spring Framework — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): request, response và status exception handling.
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @RestClientTest, RestClient.Builder và MockRestServiceServer.
- [OkHttp MockWebServer](https://square.github.io/okhttp/4.x/mockwebserver/): request capture, MockResponse, delays và SocketPolicy.
- [MockWebServer 4.12.0 artifact](https://central.sonatype.com/artifact/com.squareup.okhttp3/mockwebserver/4.12.0): dependency coordinates.
- [HTTP Semantics — RFC 9110](https://www.rfc-editor.org/rfc/rfc9110): HTTP status/idempotency/Retry-After.
- [HTTP 429 — RFC 6585](https://www.rfc-editor.org/rfc/rfc6585): Too Many Requests.
- [JSON — RFC 8259](https://www.rfc-editor.org/rfc/rfc8259): JSON syntax.
- [Resilience4j](https://resilience4j.readme.io/docs): retry, circuit breaker, bulkhead.
- [Testcontainers Toxiproxy](https://java.testcontainers.org/modules/toxiproxy/): network faults trong dedicated containers.
- [JUnit Jupiter](https://junit.org/junit5/docs/current/user-guide/): lifecycle/assertions.

## 31. Kết luận

**Giả lập phụ thuộc lỗi phải kiểm tra hợp đồng thất bại, không chỉ tạo ra một exception tùy ý.** Với Java 17+/Spring Boot 3.3.5, `MockRestServiceServer` phù hợp cho REST client slice kiểm tra HTTP contract nhanh, còn `MockWebServer` phù hợp khi cần quan sát network I/O thật tới localhost: server chậm, connection refused, response bị cắt hoặc không trả body.

Mẫu `CatalogGateway` phân loại rõ 404, 429, 400, 5xx, transport và invalid JSON thành domain errors có ý nghĩa. Các tests kiểm tra status mapping, timeout, socket disconnect fail-closed, semantic validation và việc không retry ngoài policy. Khi đưa vào production, hãy bổ sung retry budgets, idempotency, circuit breaker/fallback có kiểm soát, observability và provider contract verification theo yêu cầu thật. **Không suy kết quả Gradle PASS từ số phương thức test trong tài liệu; phải thực thi và kiểm tra report thực tế.**
