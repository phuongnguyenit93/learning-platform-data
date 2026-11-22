# Giới hạn của mock tại lớp Java so với server giả lập qua HTTP

## 1. Vấn đề: mock cho kết quả đúng nhưng HTTP client thật vẫn có thể hỏng

Hãy hình dung ứng dụng Spring Boot gọi một dịch vụ catalog bên ngoài để kiểm tra tồn kho trước khi bán hàng. Một unit test dùng Mockito có thể hoàn toàn xanh:

```java
when(catalogGateway.fetch("SKU-01"))
        .thenReturn(new ProductView(
                "SKU-01", "Máy ảnh", 5));

assertTrue(inventoryService.isInStock("SKU-01"));
```

Test đó chứng minh `InventoryService` dùng kết quả trả về từ `CatalogGateway` đúng như dự kiến. Nhưng nó **không gửi một HTTP request**: không kiểm tra URL, query parameter, encoding, HTTP method, header `Accept`/`Authorization`, JSON decoding, HTTP status 404/500, timeout, TLS hay request/response framing.

Trong production, một client có thể sai theo những cách Mockito ở interface Java không hề quan sát:

- Gọi `/v1/product` thay vì `/v1/products`.
- Gửi `GET` trong khi API contract yêu cầu `POST`.
- Để trống query parameter `sku`, hoặc mã hóa chuỗi chứa dấu cách/ký tự đặc biệt sai.
- Quên token/header, gửi `Content-Type` sai hoặc hiểu nhầm `Accept`.
- Parse JSON field sai tên/kiểu, ngầm default primitive thành 0.
- Nhận HTTP 404 nhưng trả về object rỗng thay vì domain exception.
- Retry một request không idempotent và tạo bản ghi trùng.
- Chỉ cấu hình timeout trong unit test, không thực sự kết nối socket.
- Xử lý 429/503 sai; không đọc `Retry-After` hoặc retry vô hạn.

Để kiểm tra **lớp HTTP client thực sự tạo request**, dùng một **HTTP stub server** như WireMock hoặc MockWebServer: nó mở cổng HTTP cục bộ, nhận request từ cùng HTTP client stack mà ứng dụng dùng, so khớp method/path/query/headers/body rồi trả một response được định nghĩa bởi test.

**Nhưng server giả lập qua HTTP cũng không phải dịch vụ thật.** WireMock có thể trả JSON/status do test dựng, không chứng minh provider ngoài thực sự triển khai đúng schema, auth/TLS, pagination hay business behavior. Bài này phân tách rõ **ba tầng bằng chứng**: Java mock → HTTP server giả lập → integration/contract test với dịch vụ thật.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt Mockito mock ở interface Java, `MockRestServiceServer` ở request-factory/client layer và WireMock/MockWebServer có **HTTP socket thật**.
2. Chỉ ra chính xác điều gì một `when(...).thenReturn(...)` có thể và không thể chứng minh.
3. Thiết kế ranh giới `InventoryService → CatalogGateway → HttpCatalogGateway → HTTP` rõ ràng.
4. Viết JUnit 5/Mockito unit test cho business rule mà không cần Spring context, server hoặc network.
5. Viết JUnit 5/WireMock test với `RestClient` thực, cổng ngẫu nhiên, stub mapping và request verification.
6. Kiểm tra method, URL path, query parameter, percent-encoding, `Accept`, custom header và response JSON mapping.
7. Phân biệt HTTP 404, 429, 500, 204, invalid JSON và I/O timeout.
8. Hiểu `RestClient.retrieve()` mặc định ném exceptions cho 4xx/5xx, nhưng không tự cung cấp business-specific retry/fallback.
9. Dùng `@SpringBootTest`/`@DynamicPropertySource` để cấp mock server base URL vào bean của Spring Boot.
10. Biết `@RestClientTest` cùng `MockRestServiceServer` khác gì WireMock về phạm vi network.
11. Giải thích contract tests, provider verification, consumer-driven contracts và nguy cơ **stub đúng theo kỳ vọng sai**.
12. Tạo tests độc lập: reset stubs/request journal, random port, timeout hữu hạn, dữ liệu giả và không gửi request ra Internet ngoài ý muốn.
13. Chọn đúng cách giả lập lỗi HTTP/transport và tránh các tests flaky vì sleep/retry ngẫu nhiên.
14. Thiết kế test pyramid có feedback nhanh nhưng vẫn bảo vệ những tích hợp đáng rủi ro.

## 3. So sánh các tầng giả lập

| Cách kiểm thử | Thứ được thay thế | Có TCP/HTTP socket? | Có serialize request + deserialize response thật không? | Mức bằng chứng |
| --- | --- | --- | --- | --- |
| Mockito mock `CatalogGateway` | Interface Java do app định nghĩa | Không | Không | Business logic với return/exception giả |
| Mockito mock `RestClient` hoặc builder | API Java của HTTP client | Không | Thường không | Client control flow, nhưng rất dễ mock chain sai |
| `@RestClientTest` + `MockRestServiceServer` | Request factory/transport trong Spring client | Không mở server socket | Có thể kiểm tra URI/method/headers/body và message converters | Spring HTTP request construction/decoding với fake response, không có network I/O |
| WireMock/MockWebServer trong cùng JVM | Remote HTTP server | **Có**, loopback TCP | **Có**, qua HTTP client stack thật | Request/response protocol, client codec, headers/status/transport ở phạm vi local |
| WireMock chạy process/container riêng | Remote HTTP server | **Có**, qua network/container routing | Có | Gần cấu hình deployment hơn về host/port, vẫn là stub behavior |
| Test với sandbox của provider thật | External service API | Có | Có | Provider contract thực trong sandbox được quản lý |
| Test với production-like service và dữ liệu test | Hạ tầng thật có giới hạn | Có | Có | Behavior của deployment cụ thể, khó cô lập hơn |

**Không dùng nhãn “mock HTTP” để gộp mọi công cụ làm một.** `MockRestServiceServer` có chữ “server” nhưng thực chất chặn request ở HTTP client abstraction; nó **không** mở một TCP listener như WireMock. Cả hai hữu ích, nhưng bắt được các lớp lỗi khác nhau.

### 3.1. Cần trả lời “đơn vị nào là thật?”

Trong test Mockito:

```text
InventoryService thật
        |
        v
CatalogGateway (Mockito mock)
        X
HttpCatalogGateway / RestClient / network / JSON
```

Trong test WireMock:

```text
HttpCatalogGateway thật
        |
        v
RestClient + HTTP request factory thật
        |
        v
localhost:<dynamic-port> qua HTTP socket
        |
        v
WireMock fake HTTP server
        |
        v
Response được test cấu hình
```

Trong provider sandbox test:

```text
HttpCatalogGateway thật
        |
        v
HTTP + DNS + TLS / network tùy cấu hình
        |
        v
Provider sandbox thật
        |
        v
Behavior của provider ở sandbox
```

Điểm quan trọng: mỗi test có **ranh giới hệ thống đang được xác minh**. Không tuyên bố một test MockMvc/WireMock đã chứng minh giao dịch tài chính hoặc dịch vụ bên ngoài thật đã hoạt động nếu chỉ có stub.

## 4. Mock ở lớp Java: lợi ích mạnh nhưng có trần

Mockito có thể điều khiển response/exception rất chính xác:

```java
when(catalogGateway.fetch("SKU-01"))
        .thenReturn(new ProductView(
                "SKU-01", "Camera", 5));

when(catalogGateway.fetch("MISSING"))
        .thenThrow(new CatalogNotFoundException(
                "MISSING", null));
```

Ưu điểm:

- Không cần network, không cần Spring context, phản hồi nhanh.
- Dễ kiểm tra nhánh business rule: stock > 0, không có product, rule fail.
- Dễ kích hoạt những lỗi hiếm/khó tái hiện: dependency throw, null response, state biên.
- `verify(...)` chứng minh collaborator method được gọi với tham số nào.
- Unit test thường determinisitic nếu không dùng shared mutable state/clock không kiểm soát.

Nhưng Mockito chỉ “biết” methods bạn mock. Nếu implementation HTTP thực gọi nhầm `/v2/items`, Mockito mock ở `CatalogGateway` **không quan sát** được. Nếu provider trả `"stock":"5"` là String nhưng client DTO mong int, mock vẫn có thể trả int 5 mà chẳng kiểm tra JSON. Khi service layer test không instantiate `HttpCatalogGateway`, không có serialization/deserialization nào chạy.

### 4.1. Mock sâu đến RestClient có tốt hơn không?

Bạn có thể mock `RestClient`, `RequestHeadersUriSpec`, `ResponseSpec` và chained calls. Nhưng:

- Tests dễ phụ thuộc implementation/call-chain details.
- Mockito có thể trả value đúng dù URI, headers hoặc message converter bị cấu hình sai.
- Những interfaces generic trong fluent API dễ làm stubbing rối.
- Không kiểm tra behavior của HTTP request factory, URI encoding hay response status parser trong điều kiện request thực.
- Càng mock sâu, càng có nguy cơ bạn đang kiểm thử **cách mình viết mock**, không phải HTTP protocol.

Vì vậy, thường tốt hơn là **mock interface domain** trong service unit tests, còn test client implementation riêng bằng HTTP stub server.

### 4.2. Interaction verification không thay thế state verification

`verify(gateway).fetch("SKU-01")` cho biết có một method call. Nó không chứng minh external server đã nhận GET hợp lệ. Ngược lại, WireMock `verify(getRequestedFor(...))` có thể chứng minh HTTP request đã thực sự đến server local và khớp method/path/headers, nhưng không chứng minh external provider thật phản hồi như stub.

## 5. HTTP stub server như WireMock làm được gì?

WireMock có thể:

- Nghe HTTP/HTTPS trên port được cấu hình hoặc cấp động.
- Match method, URL path, query params, headers, cookies và request body.
- Trả HTTP status, headers, JSON/text/binary response.
- Ghi request journal để test verify số lần/chi tiết request.
- Cấu hình priority, stateful scenarios, response templating hoặc proxy/recording khi thích hợp.
- Mô phỏng response delay, malformed responses, connection resets và một số network fault modes.
- Reset stubs/requests để các tests không ảnh hưởng nhau.

Nhưng WireMock **không tự hiểu toàn bộ hợp đồng API của provider**. Một stub trả 200 khi test mong 200 có thể sai so với hệ thống thật nếu provider mới yêu cầu header `X-Request-Version` hoặc response schema đã thay đổi.

### 5.1. Stub và assertion không phải một thứ

Một stub:

```java
server.stubFor(
        get(urlPathEqualTo("/v1/products"))
                .withQueryParam("sku", equalTo("SKU-01"))
                .willReturn(okJson(
                        """
                        {"sku":"SKU-01","name":"Camera","stock":5}
                        """)));
```

nói rằng **nếu** server nhận GET có path/query phù hợp, nó trả JSON này.

Assertion:

```java
assertEquals(5, result.stock());

server.verify(
        1,
        getRequestedFor(urlPathEqualTo("/v1/products"))
                .withQueryParam("sku", equalTo("SKU-01")));
```

nói rằng client đã parse đúng dữ liệu **và** có một HTTP GET đúng điều kiện đến server. Nếu chỉ stub mà không gọi client/verify, test không chứng minh được gì.

### 5.2. Request journal cần được reset

WireMock giữ lại recorded requests/stubs (tùy cấu hình) giữa các methods nếu server dùng chung. Vì thế mỗi test nên dọn:

```java
server.resetAll();
```

khi server thuộc riêng test class. Reset làm sạch các mappings/requests cũ; trong môi trường dùng chung với test khác, resetAll có thể xóa stubs của test khác nên không được gọi vô tội vạ. Tốt nhất dùng server riêng theo class/test suite, hoặc namespace và lifecycle có kiểm soát.

### 5.3. Random port quan trọng

`new WireMockServer(options().dynamicPort())` tránh hardcode `8080`, `9090` đang bị chiếm trên máy developer/CI. Sau `server.start()`, lấy `server.baseUrl()` để xây REST client.

Không gọi `server.baseUrl()` để cấp cho application trước khi server đã start. Không dùng `http://localhost:8080` mặc định trong test nếu server được khởi động bằng cổng ngẫu nhiên.

## 6. Cơ chế HTTP client trong Spring Boot 3.3

Spring Framework 6.1 cung cấp `RestClient`, một fluent synchronous HTTP client:

```java
ProductView product = restClient.get()
        .uri(uriBuilder -> uriBuilder
                .path("/v1/products")
                .queryParam("sku", "SKU-01")
                .build())
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(ProductView.class);
```

Ở đây:

1. Java tạo URI từ path và query parameter.
2. `RestClient` chọn HTTP request factory theo cấu hình/classpath và gửi HTTP request.
3. `Accept: application/json` được gửi nếu đã cấu hình.
4. Server trả status, headers và JSON body.
5. Message converter (thường Jackson) convert JSON thành Java record.
6. Với HTTP 4xx/5xx, `retrieve()` mặc định ném `RestClientException` subclass, thay vì tự tạo `ProductView`.
7. `body(ProductView.class)` có thể trả `null` với body trống; client nên quyết định cách xử lý theo contract.

**Spring Boot có thể auto-configure một `RestClient.Builder`**. Nếu dùng builder được inject, nên kiểm tra context setup riêng với `@SpringBootTest` hoặc `@RestClientTest`; khi khởi tạo `RestClient.builder()` thủ công trong Java unit tests, bạn không tự động kiểm tra mọi customization của Boot auto-configured builder.

### 6.1. Những exception hữu ích

| Tình huống | Exception/hành vi thường gặp |
| --- | --- |
| 404 | `HttpClientErrorException.NotFound` |
| 400 | `HttpClientErrorException.BadRequest` |
| 429 | `HttpClientErrorException.TooManyRequests` |
| 500 | `HttpServerErrorException.InternalServerError` |
| Other 4xx/5xx | `RestClientResponseException` hoặc subclass |
| Không kết nối được / read timeout | `ResourceAccessException` (thường có nested I/O exception) |
| JSON không convert được | `RestClientException`/message conversion exception phù hợp |
| 204 No Content | Body có thể là `null` |
| 302 redirect | Tùy underlying HTTP client/redirect policy; không tự khẳng định mọi client sẽ follow |
| Retry | **Không mặc định là business-level retry**; phải cấu hình chính sách riêng |

Kiểu exception cụ thể phụ thuộc Spring Framework, request factory và cách custom status handler. Tests nên assert type đủ cụ thể cho contract nhưng không khóa vào string nội bộ của HTTP client.

### 6.2. RestClient vs WebClient vs RestTemplate

- `RestClient`: synchronous client mới của Spring Framework, phù hợp ví dụ Java 17/Boot 3.3.
- `RestTemplate`: synchronous API lâu đời, vẫn có hệ thống đang dùng.
- `WebClient`: reactive/nonblocking, dùng Reactor `Mono`/`Flux` và event loop.
- OpenFeign/HTTP interface clients: có cấu hình decoder/error decoder/retry riêng theo stack.

Nguyên tắc HTTP stub server áp dụng cả các client trên, nhưng cách setup bean, timeouts, request factory, exception và assertion phải theo **client thực dùng production**, không copy thử nghiệm `RestClient` rồi tuyên bố đã kiểm chứng WebClient.

## 7. Dự án runnable: Java 17 + Spring Boot 3.3.0 + Mockito + WireMock 3

Bộ ví dụ có **ba nhóm**:

1. **Java-level unit tests:** `InventoryServiceMockTest` mock interface `CatalogGateway` bằng Mockito. Không dùng Spring context hoặc HTTP.
2. **WireMock HTTP integration tests:** `HttpCatalogGatewayWireMockTest` tạo WireMock server port động và dùng `RestClient` gửi request thật.
3. **Spring wiring test:** `CatalogWiringSpringTest` dùng `@SpringBootTest` với `@DynamicPropertySource` cấp URL của server, sau đó assert `InventoryService` nhận được response qua bean `CatalogGateway` được Boot dựng.

Phiên bản minh họa: Java 17, Spring Boot **3.3.0**, WireMock **3.9.1**. Không coi các version này là lựa chọn production mới nhất; dùng chúng để giữ API/import nhất quán. Trong dự án thật, nâng version theo BOM/security policy.

### 7.1. Cây thư mục

```text
http-stub-boundary/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/httpclient/
    │   ├── DemoApplication.java
    │   ├── ProductView.java
    │   ├── CatalogGateway.java
    │   ├── CatalogNotFoundException.java
    │   ├── HttpCatalogGateway.java
    │   ├── CatalogClientConfiguration.java
    │   └── InventoryService.java
    └── test/java/example/httpclient/
        ├── InventoryServiceMockTest.java
        ├── HttpCatalogGatewayWireMockTest.java
        └── CatalogWiringSpringTest.java
```

Không có Maven/Gradle Wrapper binaries in trong cây; hãy tạo/commit wrapper theo version Gradle tương thích. Bộ test không cần Docker, database hay Internet khi dependencies đã có trong Gradle cache.

### 7.2. `settings.gradle`

```groovy
rootProject.name = 'http-stub-boundary'
```

### 7.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.wiremock:wiremock-standalone:3.9.1'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` cung cấp Spring MVC, `RestClient` và Jackson HTTP message converters. `spring-boot-starter-test` cung cấp JUnit Jupiter, Mockito và Spring Test. `wiremock-standalone` là artifact WireMock 3 bản đóng gói độc lập, giúp giảm xung đột transitive Jetty/Jackson dependency trong test classpath; không phải một Docker server.

**Tại sao dùng WireMock 3.9.1?** Đây là version có artifact `org.wiremock:wiremock-standalone:3.9.1` được công bố trên Maven Central. Version được cố định để ví dụ runnable theo API đã mô tả, không phải khuyến nghị rằng 3.9.1 còn là security baseline hiện hành.

## 8. Source Java: interface domain tách khỏi HTTP protocol

### 8.1. `DemoApplication.java`

**`src/main/java/example/httpclient/DemoApplication.java`:**

```java
package example.httpclient;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Ứng dụng này có một outbound HTTP client bean; nó **không** tự chạy mock server khi gọi `bootRun`. Muốn chạy full application ngoài test, cần cung cấp property `catalog.base-url` trỏ tới một provider/sandbox có chủ đích. Không dùng default URL production trong source.

### 8.2. `ProductView.java`

**`src/main/java/example/httpclient/ProductView.java`:**

```java
package example.httpclient;

public record ProductView(
        String sku,
        String name,
        int stock) {}
```

Java 17 record biểu diễn dữ liệu downstream API. Jackson của Spring Boot có thể deserialize JSON keys `sku`, `name` và `stock` vào record này. Đây là **client DTO**, không phải JPA entity hoặc domain validation hoàn chỉnh.

Với property `stock` kiểu primitive `int`, một JSON không có field này có thể bị map về 0 nếu Jackson được cấu hình dễ dãi. Do đó, một 200 response decode được **chưa tự chứng minh provider schema đầy đủ**; kiểm tra contract/Bean Validation hoặc cấu hình mapper strict nếu thiếu field là lỗi nghiêm trọng.

### 8.3. `CatalogGateway.java`

**`src/main/java/example/httpclient/CatalogGateway.java`:**

```java
package example.httpclient;

public interface CatalogGateway {
    ProductView fetch(String sku);
}
```

Interface này là ranh giới do ứng dụng sở hữu. Service không cần biết URL, HTTP method hay Jackson; nó chỉ biết khi `fetch` thành công sẽ nhận `ProductView`, còn khi không thấy product sẽ nhận một domain exception.

Mockito unit test mock interface; WireMock test **không mock** interface mà chạy implementation `HttpCatalogGateway` thật.

### 8.4. `CatalogNotFoundException.java`

**`src/main/java/example/httpclient/CatalogNotFoundException.java`:**

```java
package example.httpclient;

public final class CatalogNotFoundException
        extends RuntimeException {
    public CatalogNotFoundException(
            String sku, Throwable cause) {
        super("Catalog item not found: " + sku, cause);
    }
}
```

Class này chuyển HTTP 404 thành khái niệm domain. Không ép mọi lỗi 4xx thành not found: 401, 403, 429 có ý nghĩa khác nhau và cần policy riêng.

### 8.5. `HttpCatalogGateway.java` — client implementation thực

**`src/main/java/example/httpclient/HttpCatalogGateway.java`:**

```java
package example.httpclient;

import org.springframework.http.MediaType;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

public final class HttpCatalogGateway
        implements CatalogGateway {
    private final RestClient client;

    public HttpCatalogGateway(RestClient client) {
        this.client = client;
    }

    @Override
    public ProductView fetch(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank");
        }

        try {
            ProductView result = client.get()
                    .uri(uriBuilder -> uriBuilder
                            .path("/v1/products")
                            .queryParam("sku", sku)
                            .build())
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(ProductView.class);

            if (result == null) {
                throw new IllegalStateException(
                        "Remote catalog returned no body");
            }

            return result;
        }
        catch (HttpClientErrorException.NotFound ex) {
            throw new CatalogNotFoundException(sku, ex);
        }
    }
}
```

Đây là phần mà Java-level mock test sẽ bỏ qua, còn WireMock HTTP test sẽ thực thi:

- `GET` HTTP.
- Path `/v1/products`.
- Query parameter `sku` từ user input (do URI builder xử lý encoding).
- `Accept: application/json`.
- HTTP status handling của `retrieve()`.
- Jackson message conversion JSON → Java record.
- Map 404 thành `CatalogNotFoundException`.
- 204/null body thành `IllegalStateException`.
- Với 500/429, để Spring `RestClient` exception đi lên (bài học chưa thêm retry/fallback).

**Chủ ý không dùng `new URL(baseUrl + "/...?" + sku)`** vì tự nối chuỗi dễ lỗi escaping, double slash và query injection. `UriBuilder` phù hợp hơn cho path/query.

### 8.6. `InventoryService.java`

**`src/main/java/example/httpclient/InventoryService.java`:**

```java
package example.httpclient;

import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final CatalogGateway gateway;

    public InventoryService(CatalogGateway gateway) {
        this.gateway = gateway;
    }

    public boolean isInStock(String sku) {
        return gateway.fetch(sku).stock() > 0;
    }
}
```

Business rule hiện tại cố ý nhỏ: stock dương nghĩa là sẵn hàng. Lớp này không biết HTTP. Vì vậy **unit test tốt nhất của nó không cần WireMock**; việc dùng Mockito để test nhánh sẵn/chưa sẵn là đủ.

Nếu service tương lai phải tính threshold, quantity reserve, fallback logic hoặc event publishing, unit tests có thể bao phủ phần Java ấy mà không kéo HTTP stack vào mọi case.

### 8.7. `CatalogClientConfiguration.java`

**`src/main/java/example/httpclient/CatalogClientConfiguration.java`:**

```java
package example.httpclient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean
    CatalogGateway catalogGateway(
            RestClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl) {
        RestClient client = builder
                .baseUrl(baseUrl)
                .build();

        return new HttpCatalogGateway(client);
    }
}
```

Property `catalog.base-url` **bắt buộc được cung cấp** khi khởi động full context. Trong `CatalogWiringSpringTest`, nó đến từ `@DynamicPropertySource` trỏ tới WireMock server đã start.

Spring Boot 3.3 có auto-configured `RestClient.Builder`. Bằng cách inject builder, config có thể nhận các customizers/converters/observability settings do Spring Boot quản lý. Test chỉ dùng `RestClient.builder()` trực tiếp **không kiểm tra hết** phần wiring này; đó là lý do có một Spring context test riêng.

## 9. Unit test Mockito: chứng minh business logic, không cần HTTP

**`src/test/java/example/httpclient/InventoryServiceMockTest.java`:**

```java
package example.httpclient;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class InventoryServiceMockTest {
    @Mock
    CatalogGateway gateway;

    @InjectMocks
    InventoryService service;

    @Test
    void availableWhenRemoteStockIsPositive() {
        when(gateway.fetch("SKU-01")).thenReturn(
                new ProductView(
                        "SKU-01", "Camera", 5));

        assertTrue(service.isInStock("SKU-01"));

        verify(gateway).fetch("SKU-01");
    }

    @Test
    void unavailableWhenStockIsZero() {
        when(gateway.fetch("SKU-02")).thenReturn(
                new ProductView(
                        "SKU-02", "Lens", 0));

        assertFalse(service.isInStock("SKU-02"));

        verify(gateway).fetch("SKU-02");
    }

    @Test
    void propagatesDomainNotFoundFailure() {
        when(gateway.fetch("MISSING")).thenThrow(
                new CatalogNotFoundException(
                        "MISSING", null));

        assertThrows(
                CatalogNotFoundException.class,
                () -> service.isInStock("MISSING"));
    }
}
```

Ba tests không tạo `RestClient`, không nạp Spring context và không mở network. **Chúng vẫn rất có giá trị**:

- Rule `stock > 0` đúng.
- Service dùng `sku` truyền vào gateway.
- Service không nuốt một domain failure đã được gateway chuẩn hóa.

Nhưng chúng **không thể khẳng định** implementation `HttpCatalogGateway` đang gọi đúng URL/header, xử lý JSON/HTTP status đúng hoặc TCP connection hoạt động.

### 9.1. Tại sao không @SpringBootTest cho ba test này?

Không cần. `MockitoExtension` đủ inject mock vào constructor của `InventoryService` trong JUnit. Nạp full Spring context làm test chậm hơn, thêm config ngoài phạm vi mà không tăng bằng chứng cho business rule này.

### 9.2. @Mock, @MockBean, @MockitoBean và phiên bản

- `@Mock` của Mockito tạo Java mock ngoài Spring context.
- Trong Spring Boot 3.3, `@MockBean` có thể thay/add bean mock trong `ApplicationContext` khi dùng Spring test; nó vẫn **thay bean Java**, không mở HTTP network.
- Từ Boot 3.4, `@MockBean` bị deprecate để chuyển sang Spring Framework `@MockitoBean`; những import/version migration cần xem riêng.
- `@MockitoBean` cũng là bean-level mock; việc đổi annotation **không tự biến** test thành HTTP transport integration.

Đừng nghĩ “@SpringBootTest + @MockBean HTTP gateway” đủ kiểm tra HTTP client. Nếu đã mock gateway bean, request thường dừng **trước** RestClient.

## 10. HTTP test WireMock: chạy client thật qua socket

**`src/test/java/example/httpclient/HttpCatalogGatewayWireMockTest.java`:**

```java
package example.httpclient;

import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.options;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HttpCatalogGatewayWireMockTest {
    private static WireMockServer server;

    private HttpCatalogGateway gateway;

    @BeforeAll
    static void startServer() {
        server = new WireMockServer(
                options().dynamicPort());
        server.start();
    }

    @AfterAll
    static void stopServer() {
        if (server != null) {
            server.stop();
        }
    }

    @BeforeEach
    void resetAndCreateClient() {
        server.resetAll();

        gateway = new HttpCatalogGateway(
                RestClient.builder()
                        .baseUrl(server.baseUrl())
                        .build());
    }

    @Test
    void sendsRealGetWithQueryAndAcceptAndReadsJson() {
        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("SKU-01"))
                        .withHeader(
                                "Accept",
                                containing("application/json"))
                        .willReturn(okJson(
                                """
                                {
                                  "sku":"SKU-01",
                                  "name":"Camera",
                                  "stock":5
                                }
                                """)));

        ProductView actual = gateway.fetch("SKU-01");

        assertEquals("SKU-01", actual.sku());
        assertEquals("Camera", actual.name());
        assertEquals(5, actual.stock());

        server.verify(
                1,
                getRequestedFor(
                        urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("SKU-01"))
                        .withHeader(
                                "Accept",
                                containing("application/json")));
    }

    @Test
    void uriBuilderEncodesSpacesInQueryParameter() {
        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("USB C"))
                        .willReturn(okJson(
                                """
                                {
                                  "sku":"USB C",
                                  "name":"Adapter",
                                  "stock":2
                                }
                                """)));

        ProductView product = gateway.fetch("USB C");

        assertEquals("USB C", product.sku());

        server.verify(
                1,
                getRequestedFor(
                        urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("USB C")));
    }

    @Test
    void mapsHttp404IntoDomainNotFoundException() {
        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("MISSING"))
                        .willReturn(aResponse()
                                .withStatus(404)
                                .withBody(
                                        "{\"error\":\"not found\"}")));

        CatalogNotFoundException thrown =
                assertThrows(
                        CatalogNotFoundException.class,
                        () -> gateway.fetch("MISSING"));

        assertTrue(
                thrown.getMessage().contains("MISSING"));

        server.verify(
                1,
                getRequestedFor(
                        urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("MISSING")));
    }

    @Test
    void keepsHttp500AsServerFailure() {
        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("BROKEN"))
                        .willReturn(aResponse()
                                .withStatus(500)
                                .withHeader(
                                        "Content-Type",
                                        "application/json")
                                .withBody(
                                        "{\"error\":\"temporary\"}")));

        assertThrows(
                HttpServerErrorException.class,
                () -> gateway.fetch("BROKEN"));
    }

    @Test
    void http429IsNotAutomaticallyRetried() {
        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("LIMITED"))
                        .willReturn(aResponse()
                                .withStatus(429)
                                .withHeader("Retry-After", "3")));

        HttpClientErrorException.TooManyRequests ex =
                assertThrows(
                        HttpClientErrorException
                                .TooManyRequests.class,
                        () -> gateway.fetch("LIMITED"));

        assertEquals(429, ex.getStatusCode().value());
        assertEquals(
                "3",
                ex.getResponseHeaders()
                        .getFirst("Retry-After"));

        server.verify(
                1,
                getRequestedFor(
                        urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("LIMITED")));
    }

    @Test
    void malformedJsonCannotBecomeProductView() {
        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("INVALID"))
                        .willReturn(aResponse()
                                .withStatus(200)
                                .withHeader(
                                        "Content-Type",
                                        "application/json")
                                .withBody(
                                        "{\"sku\":\"INVALID\",")));

        assertThrows(
                RestClientException.class,
                () -> gateway.fetch("INVALID"));
    }

    @Test
    void noContentIsNotTreatedAsAnAvailableItem() {
        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("EMPTY"))
                        .willReturn(aResponse()
                                .withStatus(204)));

        IllegalStateException ex = assertThrows(
                IllegalStateException.class,
                () -> gateway.fetch("EMPTY"));

        assertTrue(
                ex.getMessage().contains("no body"));
    }

    @Test
    void rejectsBlankSkuBeforeAnyNetworkRequest() {
        assertThrows(
                IllegalArgumentException.class,
                () -> gateway.fetch("  "));

        server.verify(
                0,
                getRequestedFor(
                        urlPathEqualTo("/v1/products")));
    }

    @Test
    void sendsExplicitClientHeaderWhenConfigured() {
        HttpCatalogGateway withHeader =
                new HttpCatalogGateway(
                        RestClient.builder()
                                .baseUrl(server.baseUrl())
                                .defaultHeader(
                                        "X-Catalog-Key",
                                        "demo-test-key")
                                .build());

        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("SKU-KEY"))
                        .withHeader(
                                "X-Catalog-Key",
                                equalTo("demo-test-key"))
                        .willReturn(okJson(
                                """
                                {
                                  "sku":"SKU-KEY",
                                  "name":"Cable",
                                  "stock":7
                                }
                                """)));

        assertEquals(
                7,
                withHeader.fetch("SKU-KEY").stock());

        server.verify(
                1,
                getRequestedFor(
                        urlPathEqualTo("/v1/products"))
                        .withHeader(
                                "X-Catalog-Key",
                                equalTo("demo-test-key")));
    }
}
```

**Có 9 test methods** trong class WireMock trên. HTTP server được khởi động một lần cho cả class, reset mappings/request journal trước từng method, và dừng sau khi hoàn tất.

### 10.1. Những gì test 200 chứng minh

`sendsRealGetWithQueryAndAcceptAndReadsJson`:

1. `RestClient` tạo HTTP GET thật, không gọi Mockito.
2. WireMock nhận đúng `/v1/products`.
3. Query parameter `sku=SKU-01` được gửi.
4. Header `Accept` chứa `application/json`.
5. Server trả JSON có keys `sku`/`name`/`stock`.
6. Spring HTTP message converter deserialize JSON vào Java record.
7. Test assert giá trị object và request count bằng 1.

**Đây là bằng chứng transport/codec tại loopback HTTP**, không phải bằng chứng external catalog provider thật trả JSON đó.

### 10.2. Test encoding chứng minh điều gì?

`uriBuilderEncodesSpacesInQueryParameter` dùng input `"USB C"`. HTTP request URI phải được xử lý hợp lệ để server có thể giải mã query param thành giá trị đó. Test WireMock match parsed query parameter `USB C`, giảm nguy cơ tự nối URI thành chuỗi có dấu cách không hợp lệ.

Để kiểm tra chính xác byte-level percent encoding `%20` so với `+`, có thể đọc recorded raw URL và assert theo contract. Nhưng đừng áp đặt một encoding representation chỉ vì bạn thích: server thường parse chúng về cùng logical query value tùy quy tắc của query parser. Khi ký tự `+`, `%`, `&`, Unicode hoặc path segment slash quan trọng, bổ sung boundary cases riêng.

### 10.3. Test 404 chứng minh xử lý lỗi ở client

Spring `retrieve()` mặc định ném `HttpClientErrorException.NotFound` khi response 404. `HttpCatalogGateway` bắt và chuyển thành `CatalogNotFoundException`.

Trong Mockito service test, `CatalogNotFoundException` được **tự tạo và ném từ mock**; chỉ WireMock test mới chứng minh sự chuyển đổi **HTTP 404 → Spring exception → domain exception** thật sự chạy.

### 10.4. 429 và Retry-After không đồng nghĩa đã retry

Trong `http429IsNotAutomaticallyRetried`, fake server trả HTTP 429 và header `Retry-After: 3`. Test assert exception có status 429 và header, request count bằng **1**.

Vì client chưa tích hợp policy retry, test **không** được kết luận “RestClient sẽ retry sau 3 giây”. Nếu có Spring Retry/Resilience4j hoặc custom interceptor, viết test riêng cho số attempts, backoff bounded và hành vi khi hết retries. Đặc biệt tránh tự retry `POST`/payment call không idempotent nếu không có idempotency key và hợp đồng provider rõ.

### 10.5. 204 và JSON lỗi

- `204 No Content` thường không có body. Client bài mẫu chủ động ném `IllegalStateException` thay vì tạo ProductView giả stock 0.
- HTTP 200 + malformed JSON phải thất bại khi decode, không tự trở thành một product hợp lệ.

Một JSON **hợp lệ nhưng thiếu field** có thể không ném lỗi do Jackson defaults. Test schema cần thêm validation/strict mapping phù hợp; không đánh đồng “deserialize được” với “provider contract hoàn hảo”.

### 10.6. Header test không phải security test hoàn chỉnh

`X-Catalog-Key: demo-test-key` là giá trị giả. WireMock chứng minh header được gửi tới local server; nó không chứng minh provider thật chấp nhận token, signature algorithm đúng, token hết hạn được refresh hay TLS bảo vệ header trên Internet.

Không log production tokens hoặc dùng secrets thật trong fake HTTP tests.

## 11. Spring Boot wiring test: config thực trỏ vào HTTP fake

Bây giờ kiểm tra thêm Spring Boot có inject `catalog.base-url` vào đúng `CatalogGateway` bean hay không.

**`src/test/java/example/httpclient/CatalogWiringSpringTest.java`:**

```java
package example.httpclient;

import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.options;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class CatalogWiringSpringTest {
    private static final WireMockServer SERVER =
            new WireMockServer(
                    options().dynamicPort());

    // Start before Spring evaluates DynamicPropertySource.
    static {
        SERVER.start();
    }

    @DynamicPropertySource
    static void catalogProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
                "catalog.base-url",
                SERVER::baseUrl);
    }

    @Autowired
    InventoryService inventoryService;

    @BeforeEach
    void resetStubState() {
        SERVER.resetAll();
    }

    @AfterAll
    static void shutDown() {
        SERVER.stop();
    }

    @Test
    void actualSpringBeanUsesHttpServerUrl() {
        SERVER.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("WIRE-01"))
                        .willReturn(okJson(
                                """
                                {
                                  "sku":"WIRE-01",
                                  "name":"Keyboard",
                                  "stock":3
                                }
                                """)));

        assertTrue(
                inventoryService.isInStock("WIRE-01"));

        SERVER.verify(
                1,
                getRequestedFor(
                        urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("WIRE-01")));
    }
}
```

Bài mẫu chủ ý start WireMock trong **static initializer** trước khi Spring context có thể đọc dynamic property. Vì vậy `SERVER::baseUrl` cung cấp một URL hợp lệ khi bean `CatalogClientConfiguration` được dựng. Sau test class, `@AfterAll` dừng server.

**Cảnh báo context cache:** Spring TestContext có thể cache `ApplicationContext` sau khi class kết thúc, còn WireMock ở đây đã dừng. Nếu một class khác tái sử dụng context/cache key chứa client đang trỏ tới server cũ, test có thể fail. Demo có **một Spring wiring class** để minh họa; suite lớn nên quản lý lifecycle server chung với Spring context hoặc dùng context isolation một cách có chủ đích, không share server tùy tiện.

### 11.1. Khác với test WireMock không dùng Spring context

- `HttpCatalogGatewayWireMockTest` tự gọi `RestClient.builder()` và constructor. Nó kiểm tra HTTP client behavior một cách hẹp và nhanh.
- `CatalogWiringSpringTest` nạp Spring Boot context, inject `RestClient.Builder` auto-configured, đọc `catalog.base-url`, tạo bean `CatalogGateway`, inject `InventoryService` và gọi tới fake server.
- Không có Spring MVC inbound server do `webEnvironment=NONE`; chỉ có **outbound HTTP** đến WireMock. Đó là đúng phạm vi mà bài cần kiểm tra.

### 11.2. Khi nào cần full application HTTP test?

Nếu muốn kiểm tra cả inbound API controller lẫn outbound HTTP client, dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)`, gửi request vào controller bằng HTTP client thật, rồi verify WireMock nhận outbound request. Bài đó phức tạp hơn và cần tách hai cổng:

1. Cổng Spring Boot inbound server.
2. Cổng WireMock outbound fake server.

Không gọi đó là “một HTTP server” và không dùng `@LocalServerPort` của Spring Boot thay cho WireMock port.

## 12. Lệnh chạy và số lượng test

Từ thư mục có Gradle Wrapper tương thích với Boot 3.3/JDK 17 (ví dụ Gradle 8.7):

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.httpclient.InventoryServiceMockTest
./gradlew test --tests example.httpclient.HttpCatalogGatewayWireMockTest
./gradlew test --tests example.httpclient.CatalogWiringSpringTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.httpclient.HttpCatalogGatewayWireMockTest
```

Dự kiến:

| Class | Số methods | Spring context? | HTTP network? |
| --- | ---: | --- | --- |
| `InventoryServiceMockTest` | 3 | Không | Không |
| `HttpCatalogGatewayWireMockTest` | 9 | Không | Có, localhost |
| `CatalogWiringSpringTest` | 1 | Có | Có, localhost |
| **Tổng** | **13** | Tùy class | Tùy class |

Khi dependencies và môi trường phù hợp, cả 13 test methods **dự kiến pass**; Gradle thường báo `BUILD SUCCESSFUL`. Các số trên là **expected**, không phải tuyên bố đã thực thi Gradle trong bài viết. Ví dụ không có business stdout cố định. Mỗi test class có thể được chạy độc lập, không yêu cầu Docker.

### 12.1. Có thể chạy `bootRun` không?

Main application yêu cầu property `catalog.base-url`. Nếu bạn có một provider sandbox hoặc WireMock server đang chạy tại địa chỉ được kiểm soát, có thể cấp:

```bash
./gradlew bootRun --args='--catalog.base-url=http://127.0.0.1:8089'
```

Đây là ví dụ command cấu hình, **không tự khởi động WireMock trên port 8089**. Nếu không có external server hoặc property, app có thể fail context startup hoặc HTTP call không kết nối được. Phạm vi runnable của bài là `./gradlew test`, nơi fake server được tests khởi động và URL được cấp tự động.

### 12.2. Không in request/response secrets

Trong CI, HTTP client logs có thể chứa `Authorization` header, API key, cookie, PII hoặc body dữ liệu người dùng. Dùng synthetic data và che secrets trước khi log, đặc biệt trong test failures khi WireMock in unmatched requests.

## 13. `@RestClientTest` + `MockRestServiceServer`: giải pháp ở client layer

Spring Boot 3.3 có `@RestClientTest` để test REST clients theo **test slice**. Nó auto-configure JSON codecs, `RestClient.Builder` và hỗ trợ `MockRestServiceServer`:

```java
@RestClientTest(CatalogHttpClientComponent.class)
class CatalogClientSliceTest {
    @Autowired
    MockRestServiceServer server;
    // ...
}
```

Đây là **minh họa cấu trúc, không runnable với project mẫu** vì không có class `CatalogHttpClientComponent`. Mục đích là so sánh, không yêu cầu bạn tạo class này trong lab.

`MockRestServiceServer` cho phép thiết lập HTTP expectations và synthetic responses mà **không mở HTTP socket**:

```java
RestClient.Builder builder = RestClient.builder();

MockRestServiceServer fake =
        MockRestServiceServer.bindTo(builder).build();

RestClient client = builder
        .baseUrl("https://catalog.example.invalid")
        .build();

fake.expect(requestTo(
        "https://catalog.example.invalid/v1/products?sku=SKU-01"))
    .andExpect(method(HttpMethod.GET))
    .andRespond(withSuccess(
        """
        {"sku":"SKU-01","name":"Camera","stock":5}
        """,
        MediaType.APPLICATION_JSON));

ProductView actual = client.get()
        .uri("/v1/products?sku=SKU-01")
        .retrieve()
        .body(ProductView.class);

assertEquals(5, actual.stock());
fake.verify();
```

Snippet này **cần imports và test method context**, không là một file hoàn chỉnh. Các helper đến từ `org.springframework.test.web.client.MockRestServiceServer`, `MockRestRequestMatchers.*` và `MockRestResponseCreators.*`; `HttpMethod`/`MediaType` là Spring HTTP.

**Điểm đáng nhớ:** request factory được thay bằng fake ở tầng client, nên bạn có thể kiểm tra URI/method/headers/body/codec khi dùng Spring `RestClient`, nhưng **không** kiểm tra connection refused, TLS handshake, OS socket behavior hoặc một TCP peer thật.

### 13.1. Chọn MockRestServiceServer khi nào?

- Bạn cần test `RestClient` serialization/message converter, URI, method và response mapping.
- Không cần low-level network characteristics.
- Muốn Spring test slice nhanh, ít hạ tầng.
- Không cần chia sẻ fake server với client khác chạy trong process khác.
- Muốn expectation-based test gọn ngay trong JUnit.

### 13.2. Chọn WireMock/MockWebServer khi nào?

- Muốn chạy **HTTP request qua socket thật**.
- Muốn quan sát request journal từ server độc lập với HTTP client abstraction.
- Muốn test code dùng Java HttpClient, OkHttp, Apache HttpClient, Feign, RestTemplate, WebClient hoặc nhiều clients khác nhau.
- Cần mô phỏng response delays, connection fault, redirects, content encoding hoặc HTTP status behavior ở mức transport.
- Muốn cho ứng dụng test chạy trong container/process khác kết nối fake server nếu networking được cấu hình.
- Muốn chạy consumer-driven contract stubs hoặc mock HTTP services cho test end-to-end.

**Không suy diễn** WireMock test mạnh hơn mọi MockRestServiceServer test. Lựa chọn tốt là mức thấp nhất vẫn bắt được lỗi ở boundary cần kiểm tra.

## 14. Giới hạn thực chất của HTTP stub server

### 14.1. Stub chỉ đúng theo kỳ vọng của người viết test

Nếu consumer nghĩ provider trả:

```json
{"sku":"SKU-01","name":"Camera","stock":5}
```

nhưng API thật nay trả:

```json
{"product_id":"SKU-01","display_name":"Camera","inventory":{"available":5}}
```

WireMock vẫn xanh khi nó phục vụ response đầu. Test bảo vệ **contract giả định**, không xác nhận provider còn triển khai contract ấy.

Giải pháp:

- Duy trì API contract có version (OpenAPI/JSON Schema/Pact).
- Dùng **provider verification** kiểm tra provider thật có đáp ứng consumer expectations.
- Nếu có API sandbox, chạy một số smoke/contract tests với sandbox.
- Khi thay đổi schema, update provider và consumer cùng quy trình.
- Không record production traffic có PII/secrets rồi commit thẳng làm fixtures.

### 14.2. TLS/PKI không được kiểm tra đầy đủ bằng localhost HTTP

WireMock default HTTP loopback không chứng minh:

- TLS certificate trust chain hoặc hostname validation.
- mTLS client certificates.
- TLS protocol/cipher compatibility.
- Corporate proxy/network policy.
- DNS/load-balancer behavior production.

WireMock có thể hỗ trợ HTTPS để test một phần client TLS config, nhưng self-signed/local certificate không giống CA chain/rotation thật. Những yêu cầu đó cần test riêng trong môi trường phù hợp.

### 14.3. Authentication chỉ là header trừ khi fake server có logic riêng

WireMock match `Authorization: Bearer test-token` hoặc `X-Api-Key` chứng minh request gửi đúng header. Nó không xác nhận server thật kiểm tra OAuth scopes, JWT signature, expiration, mTLS identity hoặc IAM.

Nếu auth là rủi ro quan trọng, test token acquisition/refresh và provider auth behavior riêng, không dùng “stub trả 200 khi header có mặt” làm proof security.

### 14.4. Business effects của provider không được thực thi

Một fake payment API trả:

```json
{"transactionStatus":"AUTHORIZED"}
```

không chứng minh tiền đã được giữ hay reconciliation hoạt động. Tương tự, fake email provider trả 202 không chứng minh email đã được deliver, và fake Kafka REST proxy trả success không chứng minh consumer đã nhận message.

Đừng gắn tên “end-to-end” cho một test mà upstream provider bị stub ở ranh giới quan trọng. Hãy gọi nó là **consumer integration against HTTP stub**.

### 14.5. HTTP/2, connection pooling, redirects, streaming

Một fake server thường chạy HTTP/1.1 local, trong khi production có HTTP/2, reverse proxy, compression, streaming response hoặc connection pooling.

- Nếu client phụ thuộc HTTP/2/multiplexing, cần server/harness thực sự hỗ trợ và test riêng.
- Redirect behavior phụ thuộc request factory; không giả định mọi client follow 302.
- Chunked responses, slow streaming và large bodies có thể cần test chuyên dụng.
- Test request count với retries/concurrency cần phân biệt logical action và physical HTTP attempts.
- WireMock request journal có thể thiếu một số thông tin low-level connection negotiation.

## 15. Status code phải là phần của contract, không chỉ body

| Response | Ý nghĩa hay gặp | Điều client phải quyết định |
| --- | --- | --- |
| 200 OK | Có response body thành công | Parse DTO, validate required fields |
| 201 Created | Resource mới | Đọc Location/body, idempotency nếu retry |
| 202 Accepted | Xử lý bất đồng bộ | Poll/callback, không coi là hoàn tất |
| 204 No Content | Không có response body | Không ép deserialize DTO |
| 301/302/307/308 | Redirect | Redirect policy, auth header leakage, method preservation |
| 400 Bad Request | Input vi phạm contract | Không retry không điều kiện |
| 401 Unauthorized | Chưa xác thực | Refresh token/chặn loops theo policy |
| 403 Forbidden | Không đủ quyền | Không tự coi là NotFound |
| 404 Not Found | Resource không tồn tại hoặc endpoint sai | Domain mapping đúng, phát hiện stub mismatch |
| 409 Conflict | Trạng thái xung đột | Business compensation/idempotency |
| 422 Unprocessable Entity | Validation/domain failure | Trả lỗi có ý nghĩa |
| 429 Too Many Requests | Rate limit | `Retry-After`, backoff, bounded retry |
| 500 Internal Server Error | Server failure | Retry theo idempotency/circuit breaker policy |
| 502/503/504 | Gateway/upstream unavailable | Timeout/backoff/fallback có kiểm soát |

**Không chỉ stub happy-path 200.** HTTP client thường thất bại trong các trạng thái không lý tưởng. Test status mapping theo những nhánh mà ứng dụng có trách nhiệm xử lý.

## 16. Negative HTTP tests phải phân biệt lỗi của client với lỗi của stub

Một bẫy phổ biến: WireMock **không tìm thấy mapping phù hợp** và tự trả HTTP 404. Client test nhận 404, chuyển thành `CatalogNotFoundException` và người viết tưởng đã test “provider trả not found”.

Trong test 404 của lab, ta **cố ý stub `sku=MISSING` trả status 404** và verify request đúng. Nếu mapping sai (ví dụ queryParam khác), WireMock cũng có thể trả unmatched 404; test assertion exception alone có thể xanh nhầm.

Để tránh false positive:

1. Verify request method/path/query/headers đã tới server.
2. Kiểm tra stub đã được match, không chỉ status cuối.
3. Dùng unique response header/body marker cho từng scenario nếu cần.
4. Kiểm tra unmatched request journal/near misses khi test fail.
5. Reset stubs/request journal giữa methods.
6. Tránh global catch-all stubs trả 200 cho mọi URL trong suite.
7. Dùng URL path match chính xác, không regex quá rộng.

Với những case quan trọng, có thể thêm header `X-Scenario: not-found` vào stub và assert response details trước khi mapping domain exception; cần design client hỗ trợ quan sát header/cause phù hợp.

### 16.1. Stub priority và overlapping mappings

WireMock có thể có nhiều stubs match cùng request; priority/registration ordering có thể chọn response ngoài ý muốn. Nếu tests dùng wildcard `urlMatching(".*")`, một stub “default 200” có thể che path sai. Tạo stub cụ thể và reset trước test để không kế thừa mapping mơ hồ.

### 16.2. Không test “400” bằng cách gửi request sai đến URL không stub

Nếu muốn HTTP 400, hãy đặt một stub **trả 400** cho đúng request rồi assert error mapping. Một request không match stub thường dẫn tới 404 và làm test sai mục tiêu.

## 17. Timeout, connection reset, delay và fault injection

Mockito có thể được cấu hình:

```java
when(gateway.fetch("SKU-SLOW"))
        .thenThrow(new RuntimeException("timeout"));
```

Nhưng đây **không** là real socket timeout: không đo xem request factory đã áp dụng read timeout hay client có buộc ngắt kết nối.

WireMock có thể mô phỏng:

```java
server.stubFor(
    get(urlPathEqualTo("/v1/products"))
        .withQueryParam("sku", equalTo("SLOW"))
        .willReturn(aResponse()
            .withStatus(200)
            .withFixedDelay(1500)
            .withHeader("Content-Type", "application/json")
            .withBody(
                "{\"sku\":\"SLOW\",\"name\":\"Demo\",\"stock\":1}")));
```

Đây là **mảnh code minh họa**, không nằm trong 13 test methods runnable. Để kiểm tra timeout, client phải có timeout được cấu hình rõ **ngắn hơn** delay, ví dụ 300 ms; khi request factory phát read timeout, Spring thường wrap thành `ResourceAccessException`.

Trong Spring, request factory là yếu tố quyết định. Ví dụ ý tưởng với `SimpleClientHttpRequestFactory`:

```java
SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory();

factory.setConnectTimeout(300);
factory.setReadTimeout(300);

RestClient client = RestClient.builder()
        .requestFactory(factory)
        .baseUrl(server.baseUrl())
        .build();
```

Snippet cần import `org.springframework.http.client.SimpleClientHttpRequestFactory`; nó phụ thuộc client/OS socket implementation, không phải lời hứa test sẽ luôn hoàn tất đúng 300 ms. Trong lab chính không thêm một timing-sensitive test để tránh flaky CI.

### 17.1. Cách viết timeout test ít flaky

- Config connect/read timeout thật trên HTTP client dùng production hoặc test variant.
- Dùng delayed response/fault injection phù hợp, không dùng một `Thread.sleep` tự do.
- Dùng timeout hữu hạn, assertions dựa vào **exception và request count**, không assert elapsed time đúng từng millisecond.
- Dành biên thời gian đủ giữa read timeout và fake server delay.
- Giữ test không phụ thuộc trạng thái shared thread pool.
- Cleanup server/client resources sau test; tránh leaked threads/connections.
- Khi cần kiểm tra retry/backoff, dùng fake clock/scheduler hoặc Resilience4j test utilities nếu stack hỗ trợ.
- Không retry vô hạn để “chữa” timing tests.

### 17.2. Connect timeout khác read timeout

- **Connect timeout:** không thiết lập kết nối TCP tới endpoint trong giới hạn.
- **Read timeout:** kết nối đã được thiết lập nhưng chờ dữ liệu phản hồi quá lâu.
- **Server returning HTTP 504:** đây là **HTTP response**, không phải client socket read timeout.
- **Connection refused/reset:** lỗi transport, thường không có HTTP status code.

Nếu mock Java chỉ ném `RuntimeException("timeout")`, nó không phân biệt bốn trường hợp trên. Server giả lập HTTP có thể giúp kiểm tra một phần transport, nhưng DNS/TLS/network-chaos thật còn cần hạ tầng riêng.

## 18. Authentication, cookies, content type và compression

Một outbound HTTP request có nhiều hợp đồng ngoài JSON body:

- `Authorization` bearer/API key, scopes, refresh/expiry.
- `Accept` mô tả response formats client chấp nhận.
- `Content-Type` mô tả format body được gửi, đặc biệt với POST/PUT.
- `User-Agent`, `X-Correlation-ID`, trace headers, idempotency key.
- Cookies/session/CSRF (đặc biệt với APIs dùng browser-like auth).
- Gzip/deflate `Content-Encoding` và `Accept-Encoding`.
- Caching headers `ETag`, `If-None-Match`, `Cache-Control`.
- Location header và URI encoding/redirect.
- HTTP request/body size limits.

WireMock có thể match headers/body để phát hiện lỗi request construction. Nhưng server stub **không** kiểm tra provider security implementation; nếu contract quan trọng, cần provider verification/sandbox tests.

### 18.1. Không trộn Accept với Content-Type

Trong GET không body, client nên gửi `Accept: application/json` khi mong JSON response. `Content-Type` nói về **request body**, nên GET có thể không cần `Content-Type`. Với POST JSON, cần cả serialization và `Content-Type: application/json`; test nên verify cả payload/schema và header.

### 18.2. Query param encoding và injection

Dùng URI builder giúp tránh raw string concatenation:

```java
client.get()
    .uri(b -> b.path("/v1/products")
        .queryParam("sku", "USB C")
        .build())
```

Khi input có `?`, `&`, `+`, `%` và Unicode, việc encode/interpret đúng còn phụ thuộc URI builder/default encoding mode. Test các trường hợp theo contract, không chỉ “Hello World”.

## 19. MockRestServiceServer không có socket: lợi ích và giới hạn

Một số người cho rằng **WireMock luôn tốt hơn** `MockRestServiceServer`. Điều đó không đúng:

- Với một `RestClient` dùng message converters/URI builder chuẩn, `MockRestServiceServer` đã có thể phát hiện sai method/path/header/JSON mapping.
- Nó khởi tạo nhanh, ít cổng/tài nguyên và giúp test isolation.
- Nó ít kiểm tra đúng transport behavior: TCP connect, socket close, TLS, HTTP version, connection pooling, wire-level chunking.
- Nếu ứng dụng dùng một Java HTTP client khác (ví dụ Java 17 `HttpClient`), `MockRestServiceServer` không tự intercept client đó; WireMock qua HTTP socket hỗ trợ rộng hơn.
- Nếu Spring Boot client bean dùng custom `ClientHttpRequestFactory`, test MockRestServiceServer có thể thay request factory bằng mock và vô tình **không kiểm tra chính custom factory**.

Chọn mức phù hợp:

```text
Cần test logic thuần của service?
    -> Mockito mock gateway Java.

Cần test Spring RestClient request/JSON/status
mà không cần socket?
    -> @RestClientTest + MockRestServiceServer.

Cần test HTTP client thật gửi qua localhost TCP,
status/headers/transport behavior?
    -> WireMock/MockWebServer.

Cần chứng minh provider vẫn đáp ứng contract?
    -> Consumer/provider contract verification hoặc sandbox.

Cần chứng minh TLS/ingress/auth/HA production?
    -> Deployment/staging test có hạ tầng phù hợp.
```

## 20. Đừng mock RestClient rồi gọi đó là HTTP integration

Một anti-pattern là mock toàn bộ fluent chain:

```java
// Chỉ minh họa anti-pattern: các generic fluent interfaces
// trong code thật còn cần mocking/stubbing chi tiết hơn.
when(responseSpec.body(ProductView.class))
        .thenReturn(new ProductView(
                "SKU-01", "Camera", 5));
```

Đoạn không độc lập, vì không có declarations cho `responseSpec` và `RestClient` chain. Điều nó thể hiện là: nếu mock body converter trả object mong muốn, không có HTTP response bytes, không có JSON parse, không có status handling thật.

Nếu mục tiêu là service logic, hãy mock `CatalogGateway`. Nếu mục tiêu là client serialization/transport, hãy dùng `MockRestServiceServer` hoặc WireMock, không thêm hàng chục chained stubs để tạo cảm giác giống HTTP.

## 21. Contract drift và consumer-driven contract testing

Một hệ thống sử dụng API ngoài thường có **consumer** và **provider**:

- Consumer muốn một số endpoints, request fields, headers và response schemas nhất định.
- Provider thực thi service API và có thể thay đổi.
- WireMock stubs biểu diễn **kỳ vọng của consumer**.
- Một contract verifier như Pact/Spring Cloud Contract có thể kiểm tra provider có thật sự đáp ứng các expectations ấy hay không, tùy công cụ và workflow.

Không có provider verification, hai bên có thể cùng “pass” tests riêng nhưng vẫn không tương thích khi triển khai.

### 21.1. Một quy trình contract hợp lý

1. Consumer định nghĩa interaction quan trọng: method/path/query/header/body/status/schema.
2. Consumer test gọi client implementation thật against HTTP stub.
3. Contract artifact được versioned/published nếu dùng framework contract.
4. Provider CI verify contract against provider code hoặc sandbox chuẩn.
5. Chỉ promote/merge deployment có compatibility proof phù hợp.
6. Khi provider thay contract, consumer tests/stubs và provider verifier được cập nhật có review.

**Lưu ý:** một `stubFor(...).willReturn(...)` tự viết **không tự biến thành Pact contract được provider verify**. Phải có contract tooling/process riêng.

### 21.2. Stub drift kiểm tra bằng OpenAPI/schema

Nếu API dùng OpenAPI, có thể kiểm tra synthetic WireMock responses phù hợp schema và request definitions. Nhưng schema validation không chứng minh provider latency, auth behavior hay business effects. Tách hợp đồng dữ liệu, protocol và runtime reliability.

### 21.3. Contract vs E2E

Một test consumer against WireMock là **integration test của consumer**. Một test consumer → provider sandbox thật chứng minh một phần provider compatibility. Một end-to-end production-like test cần các thành phần liên quan thực sự tham gia theo scope; không gọi mọi bài có HTTP là E2E.

## 22. Stateful scenarios: khi stub cần phản ánh chuỗi requests

Một fake server có thể phản hồi khác nhau theo trạng thái:

1. Lần GET đầu trả 503.
2. Lần GET thứ hai trả 200.
3. Client retry thành công theo policy.
4. WireMock verify đúng **2 attempts**.

WireMock có stateful scenarios, ví dụ các transitions từ `STARTED` sang một state khác. Tuy nhiên, bài runnable không tự thêm retry; không có lý do dựng scenario giả vờ client sẽ retry.

Khi triển khai:

- Định nghĩa retry policy theo status/exception và idempotency.
- Match requests bằng path/query/body cụ thể.
- Reset scenario state trước từng method.
- Assert attempt count, outcome, bounded backoff.
- Không tạo test phụ thuộc thứ tự methods.
- Với async clients, dùng deadline/polling thay vì sleep vô hạn.

### 22.1. Idempotency khi POST

Một POST create/payment call có thể được xử lý thành công ở server, nhưng response mất giữa đường. Client retry không có idempotency key có thể tạo tác dụng hai lần. HTTP stub có thể mô phỏng “connection dropped after accept” ở mức nhất định, nhưng **chỉ provider thật** mới xác nhận business idempotency implementation.

Kiểm thử retries phải xét đồng thời request method, idempotency key, duplicate detection và side effects.

## 23. Record/playback và nguy cơ fixture sai

WireMock hỗ trợ proxy/recording một số traffic để tạo stub mappings. Điều này tiện khi cần khám phá provider API, nhưng có rủi ro:

- Recorded responses chứa PII, API keys, cookies, tokens.
- IDs/timestamps động làm test giòn.
- Provider contract thay đổi sau khi snapshot.
- Response recording không nhất thiết bao phủ 429/500/timeouts.
- Traffic sample thực không bao phủ mọi edge case.
- Recording có thể thu data production trái policy nếu không xin phép.

Quy trình an toàn: record từ sandbox hợp lệ, scrub dữ liệu nhạy cảm, làm fixture deterministic, review contract và liên tục verify với provider. Không commit raw HTTP captures chứa secrets vào repository.

## 24. Khi nào cần server chạy ở container riêng?

WireMock chạy trong cùng JVM là đủ cho phần lớn client HTTP contract tests. Nhưng có thể cần fake server chạy process/container riêng khi:

- App under test cũng chạy trong Docker/Kubernetes.
- Consumer là service không viết bằng Java hoặc process khác.
- Cần test DNS/service discovery và container network routing.
- CI dùng sidecars hoặc Docker Compose.
- Muốn một fake server phục vụ nhiều client technologies.

Khi đó, URL của fake server không nhất thiết là `localhost` trong app container. Phải dùng network aliases/host mapping phù hợp. Cổng mà WireMock nghe bên trong container khác host mapped port; không hardcode nhầm.

**Mặc dù server chạy trong Docker, nó vẫn là fake HTTP service**, không biến thành provider thật. Testcontainers có thể quản lý một WireMock container, nhưng mục tiêu vẫn là kiểm tra consumer protocol behavior against stub.

## 25. Test isolation: tránh flaky từ cổng, trạng thái và parallel

Một test suite có thể fail do vấn đề bản thân fake server:

- Dùng port 8080 cố định, xung đột với dev server.
- Stubs từ test trước còn tồn tại, match sai scenario.
- Recorded request count không reset.
- Tests chạy parallel cùng reset một WireMockServer.
- Server stop trước khi một async client hoàn tất request.
- Spring TestContext cache trỏ fake server đã dừng.
- Shared static `RestClient` giữ base URL của một server khác.
- Request/response timeout quá ngắn theo CPU load.
- Match URL quá rộng nên wrong endpoint vẫn trả 200.
- Dùng hardcoded IDs/clock/random values không kiểm soát.

Checklist khắc phục:

1. Dùng random port và lấy base URL sau khi server start.
2. Mỗi test class có server riêng hoặc lifecycle/isolation hợp lý.
3. Reset stubs/requests/scenarios trước mỗi method.
4. Không bật parallel tests chia sẻ mutable server state mà thiếu đồng bộ/cô lập.
5. Dùng fixture ngắn, synthetic, có positive/negative examples.
6. Match request method/path/query/headers theo hợp đồng thật.
7. Khi async/retry, dùng awaiting với timeout có hạn.
8. Stop server/client resources có kiểm soát.
9. Không lưu WireMock stubs production-specific URLs hardcoded trong code.
10. Khi Spring context cache, thống nhất lifecycle fake server và context.

## 26. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Mockito test xanh, HTTP test fail 404 | URL/path/query sai hoặc stub không match | Verify recorded HTTP request và stub |
| `Connection refused` | WireMock chưa start, base URL/port sai | Start trước client, dynamic port |
| `RestClientResponseException` 4xx | Provider/stub từ chối request | Xem status/headers và request |
| `HttpClientErrorException.NotFound` | HTTP 404 thật hoặc unmatched WireMock stub | Kiểm tra request journal để phân biệt |
| 200 nhưng JSON decode fail | Body/Content-Type/DTO mapping sai | Assert response schema, converter |
| 204 làm code NPE | Client giả định body luôn có | Xử lý null/empty response rõ |
| 429 không retry | Chưa có retry policy | Định nghĩa retry riêng, kiểm tra idempotency |
| Delay test flaky | Timeout/delay quá sát nhau | Timeouts bounded, test faults riêng |
| Header auth test pass nhưng sandbox 401 | Fake chỉ match header presence | Provider auth test riêng |
| `NoSuchBeanDefinitionException RestClient.Builder` | Boot auto-config không nạp/scan như dự kiến | Xem app context, Boot version, slice config |
| `Could not resolve placeholder catalog.base-url` | Test chưa cấp property hoặc server chưa start | `@DynamicPropertySource` đúng thời điểm |
| Test riêng pass, suite fail | Shared WireMock state/context cache | Reset/lifecycle/isolation |
| WireMock server chạy nhưng không có requests | App dùng sai host URL hoặc gateway bị mock | Inspect bean wiring/request journal |
| Test pass với body không hợp schema | Fixture thiếu strict validation | Schema/DTO contract tests |
| `SSLHandshakeException` trên provider thật | TLS/CA/hostname issue | Test TLS đúng môi trường, fake HTTP không đủ |
| Proxy/redirect behavior sai | Request factory khác production | Dùng đúng client configuration và transport tests |
| Consumer stub pass, provider đổi schema | Contract drift | Provider verification/contract pipeline |

### 26.1. Đọc lỗi theo tầng

**Lỗi Java mock:** exception do Mockito stubbing/matching, không nhất thiết liên quan network.

**Lỗi HTTP construction:** WireMock không match request hoặc verify báo sai method/path/query/header. Inspect request journal/near misses.

**Lỗi transport:** connection refused, TLS handshake, read timeout. Thường có cause I/O.

**Lỗi HTTP response:** 401/404/429/500, có status và headers.

**Lỗi codec:** body JSON/Content-Type không khớp DTO/message converter.

**Lỗi provider contract:** consumer assumptions không được provider thực xác nhận, dù WireMock pass.

Truy nguyên đúng tầng trước khi sửa assertion. Không “chữa” một WireMock 404 bằng cách tạo catch-all stub 200 nếu mục tiêu là kiểm tra URL chính xác.

## 27. Bài tập thực hành

### Bài 1 — Cố ý làm sai path

Đổi `HttpCatalogGateway` từ `/v1/products` thành `/v1/product` trong sandbox. Mockito service test vẫn xanh vì gateway bị mock. WireMock test 200 phải fail (không match stub). Khôi phục.

**Bài học:** Java-level mock không quan sát URI path.

### Bài 2 — Xóa header Accept

Bỏ `.accept(MediaType.APPLICATION_JSON)` trong client. Test WireMock có `withHeader("Accept", containing("application/json"))` phải fail hoặc request verification không match. Khôi phục.

### Bài 3 — Query parameter chứa dấu cách

Chạy `uriBuilderEncodesSpacesInQueryParameter` rồi thử input chứa `+`, `&` và Unicode. Xem cách WireMock parse giá trị. Không nối URL raw string để sửa assertion.

### Bài 4 — 404 thật và unmatched stub 404

Cố tình stub sai query key, ví dụ `product` thay `sku`. So sánh HTTP 404 do WireMock unmatched với 404 stubbed có chủ đích. Thiết kế thêm response marker/unmatched request check để phân biệt.

### Bài 5 — 429 và retry

Thêm một retry policy có giới hạn trong một branch riêng: retry khi 429/503 đối với GET idempotent, đọc `Retry-After` theo contract, giới hạn attempts và thời gian. Dùng WireMock verify count, không assert exact milliseconds và không retry mãi.

### Bài 6 — 204 No Content

Đổi 204 thành 200 body trống. Client `body(ProductView.class)` có trả null/exception theo message converter không? Test behavior thực, không mặc định một quy luật cho mọi HTTP client.

### Bài 7 — JSON schema drift

Đổi stub body từ `"stock":5` sang `"available_qty":5`. Vì `ProductView.stock` là primitive, xem test có âm thầm đọc 0 hay không. Đề xuất strict DTO validation/JsonProperty hoặc API contract verifier.

### Bài 8 — Spring Boot bean wiring

Bỏ `@DynamicPropertySource` trong `CatalogWiringSpringTest`. Context phải fail do thiếu `catalog.base-url` hoặc client trỏ sai endpoint nếu có default config. Sửa bằng property của fake server, không hardcode production URL.

### Bài 9 — REST client slice

Tạo một `@RestClientTest` với `MockRestServiceServer`, dùng cùng `HttpCatalogGateway` và test GET/JSON. So sánh với WireMock test về tốc độ, phạm vi và khả năng mô phỏng socket read timeout.

### Bài 10 — WebClient vs RestClient

Thay implementation bằng `WebClient` trong một branch, viết `StepVerifier` hoặc block chỉ trong test ngoài event loop. Dùng cùng WireMock server để xác minh HTTP request. Không kết luận một Mockito mock `Mono.just(...)` đã kiểm tra Reactor Netty transport.

### Bài 11 — POST idempotency

Thiết kế một endpoint tạo đơn với `Idempotency-Key`, dùng WireMock mô phỏng 503/timeout và retries. Giải thích vì sao chỉ provider thật mới xác nhận duplicate prevention; fake chỉ kiểm tra client gửi key/retry đúng.

### Bài 12 — Contract verification

Đưa request/response examples từ WireMock test vào một contract artifact có version. Chạy provider verification với API sandbox hoặc service code thật. Kết luận phần nào được xác nhận bởi stub, phần nào được xác nhận bởi provider.

## 28. Checklist review trước khi đánh dấu QA PASS

- [ ] Biết mình đang mock **Java method**, **HTTP request factory** hay **HTTP server**.
- [ ] Mockito tests chỉ khẳng định business logic với fake outputs.
- [ ] Client implementation có tests riêng cho URL/method/query/headers/body/status.
- [ ] Nếu cần network behavior, dùng WireMock/MockWebServer qua socket thật.
- [ ] Đã phân biệt `MockRestServiceServer` không mở TCP listener.
- [ ] Sử dụng HTTP client configuration gần production cho tests quan trọng.
- [ ] Fake server dùng random port, client lấy base URL sau khi start.
- [ ] Reset WireMock stubs/request journal/scenarios theo test lifecycle.
- [ ] Không để @MockBean/@MockitoBean thay client/gateway trong test muốn kiểm tra outbound HTTP.
- [ ] Assertions gồm response mapping **và** request verification.
- [ ] Tests có happy path và các status 404/429/500 quan trọng.
- [ ] Có test 204/malformed JSON khi contract liên quan.
- [ ] Query/path encoding được kiểm tra với input có ký tự đặc biệt.
- [ ] Không coi một unmatched stub 404 là provider not-found mà không xem request journal.
- [ ] Khi có retry, assert attempts/idempotency và bounded timeout.
- [ ] Test timeout phân biệt transport failure và HTTP error response.
- [ ] Không coi fake header acceptance là provider authentication validation.
- [ ] Không coi stub JSON hợp lệ là proof provider schema hiện hành.
- [ ] Có contract/provider verification khi dịch vụ ngoài thay đổi độc lập.
- [ ] Không gọi consumer fake-server test là E2E với provider thật.
- [ ] Không log tokens/cookies/PII hoặc record production traffic vào fixtures không scrub.
- [ ] Context cache và fake server lifecycle đồng bộ ở suite lớn.
- [ ] Không phụ thuộc fixed port, test order, natural timing hoặc shared mutable stubs.
- [ ] Biết giới hạn TLS, DNS, HTTP/2, proxy và managed infrastructure chưa được bao phủ.
- [ ] Báo rõ test executed vs skipped và những thành phần được giả lập.

## 29. Quy tắc lựa chọn cuối cùng

```text
Điều cần chứng minh là gì?
      |
      +-- Domain rule khi collaborator trả X/throw Y?
      |     -> Mockito ở CatalogGateway interface.
      |
      +-- RestClient tạo URI/header/JSON/status đúng?
      |     -> @RestClientTest + MockRestServiceServer,
      |        không cần server socket.
      |
      +-- HTTP client thực qua TCP, request journal,
      |   response delays/faults?
      |     -> WireMock hoặc MockWebServer.
      |
      +-- Spring Boot config có trỏ client tới đúng
      |   fake provider qua property/DI?
      |     -> @SpringBootTest + @DynamicPropertySource
      |        + WireMock (lifecycle rõ).
      |
      +-- Provider hiện tại còn đáp ứng schema/status?
      |     -> Consumer-driven contract + provider verification,
      |        hoặc sandbox test được quản lý.
      |
      +-- TLS/auth/ingress/failover/real business effects?
            -> Staging/deployment/integration với hạ tầng
               và service thật tương ứng.
```

**Thông điệp cốt lõi:** Mock ở lớp Java rất tốt để cô lập và kiểm tra business decisions, nhưng **không chạy HTTP client implementation**. Server giả lập qua HTTP cho phép kiểm chứng client gửi request qua network socket và xử lý status, headers, URI, JSON/transport trong điều kiện được kiểm soát. Tuy nhiên, vì fake server vẫn trả kết quả do test định nghĩa, nó **không tự chứng minh hợp đồng của provider thật**. Một chiến lược tốt kết hợp unit tests nhanh, client tests qua HTTP fake, provider contract verification và một số integration/deployment tests đúng rủi ro — thay vì coi mọi loại “mock” là cùng mức bằng chứng.

## 30. Tài liệu chính thức và tham khảo

- Spring Framework — Testing client applications, so sánh HTTP mock server với `MockRestServiceServer`: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html
- Spring Framework 6.1 — `RestClient` và xử lý HTTP response: https://docs.spring.io/spring-framework/reference/6.1/integration/rest-clients.html
- Spring Boot 3.3 — Testing applications, `@RestClientTest` và `MockRestServiceServer`: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Auto-configured REST clients: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
- Spring Framework — `@DynamicPropertySource`: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- WireMock — Download and installation: https://wiremock.org/docs/download-and-installation/
- WireMock — Stubbing: https://wiremock.org/docs/stubbing/
- WireMock — Request matching: https://wiremock.org/docs/request-matching/
- WireMock — Verifying requests: https://wiremock.org/docs/verifying/
- WireMock — Java configuration/random ports: https://wiremock.org/docs/configuration/
- WireMock — JUnit Jupiter extension: https://wiremock.org/docs/junit-jupiter/
- WireMock — Simulating faults: https://wiremock.org/docs/simulating-faults/
- WireMock — Stateful scenarios: https://wiremock.org/docs/stateful-behaviour/
- Maven Central — `org.wiremock:wiremock-standalone:3.9.1`: https://central.sonatype.com/artifact/org.wiremock/wiremock-standalone/3.9.1
- Mockito — Documentation: https://site.mockito.org/
- Spring Cloud Contract — Consumer-driven contracts: https://docs.spring.io/spring-cloud-contract/reference/
- Pact — Consumer driven contract testing: https://docs.pact.io/
- JUnit Jupiter — User guide: https://docs.junit.org/current/user-guide/
