# Giả lập phản hồi thành công, dữ liệu sai và mã lỗi trong kiểm thử HTTP client Spring Boot

## 1. Mục tiêu và phạm vi

Một ứng dụng Spring Boot thường gọi dịch vụ HTTP bên ngoài để lấy sản phẩm, giá, thông tin tài khoản hoặc trạng thái thanh toán. Kiểm thử nhánh “server trả 200” là chưa đủ: HTTP client còn phải xử lý **200 với JSON sai**, **body rỗng**, **4xx/5xx**, lỗi đường truyền và các trường hợp bị giới hạn tần suất. Một bài test chỉ mock phương thức Java, ví dụ `when(catalog.find(...)).thenReturn(...)`, không chứng minh rằng client xây đúng URL, gửi đúng header hay deserialize response đúng contract.

Chủ đề này tập trung vào ba nhóm:
1. **Phản hồi thành công hợp lệ:** HTTP status thích hợp, headers/body đúng schema, dữ liệu có ý nghĩa nghiệp vụ.
2. **Phản hồi dữ liệu sai:** status có thể vẫn là 200 nhưng JSON hỏng, thiếu field, type không khớp, giá trị vô lý hoặc body rỗng.
3. **Phản hồi mã lỗi:** 400/401/403/404/409/422/429/500/502/503/504, đồng thời phân biệt chúng với lỗi timeout, DNS hoặc connection reset khi chưa có HTTP response.

Bài cung cấp dự án **Java 17+, Spring Boot 3.5.x, JUnit 5** với `RestClient` + `MockRestServiceServer` và `WebClient` + OkHttp `MockWebServer` + Reactor `StepVerifier`. Có ví dụ đầy đủ, test cases và checklist, cùng cảnh báo về những giả định mà mock HTTP không thể chứng minh.

### 1.1. Hai tầng kiểm chứng độc lập

```text
Ứng dụng gọi CatalogClient
           |
           v
HTTP REQUEST CONTRACT
  GET /v1/products/{sku}
  Accept: application/json
  đúng baseUrl, path, query, headers, số lần gọi?
           |
           v
HTTP RESPONSE CONTRACT
  status + Content-Type + body + error headers
           |
      +----+-----+----------------+
      |          |                |
   200 hợp lệ  200 sai body     4xx/5xx/I-O
      |          |                |
  ProductDto  reject rõ lỗi    domain error /
                               HTTP exception
```

**Kết luận đầu tiên:** `200 OK` chỉ xác nhận server đã gửi một HTTP response có status 200; nó **không** bảo đảm dữ liệu đúng nghiệp vụ. Ngược lại, mất kết nối trước response không được gán tùy tiện thành `503` — vì không có status server xác nhận.

## 2. Phân loại lỗi phải chính xác

| Response thực tế | Điều test nên assert | Kết quả client minh họa |
|---|---|---|
| 200 + JSON đầy đủ, giá trị đúng | Decode và validate các trường | `Optional.of(ProductDto)` |
| 200 + `sku` không trùng request | Không chấp nhận nhầm record | `InvalidCatalogResponseException` |
| 200 + thiếu `name` hoặc `id` | Đừng tin primitive defaults/null | `InvalidCatalogResponseException` |
| 200 + `priceCents=-1` | Validate invariant domain | `InvalidCatalogResponseException` |
| 200 + JSON bị cắt/sai cú pháp | Message converter phải báo lỗi | `RestClientException` hoặc decoding exception |
| 200 + body rỗng | Contract GET yêu cầu DTO | Lỗi hợp đồng dữ liệu |
| 204 No Content | Hợp lệ với DELETE, **không hợp lệ cho GET có body bắt buộc** | Lỗi hợp đồng ở ví dụ |
| 404 Not Found | Contract product lookup cho phép absent | `Optional.empty()` |
| 400/401/403/422 | Không gộp vào “not found” | Trả hoặc map đúng HTTP error |
| 429 Too Many Requests | Kiểm tra `Retry-After` và retry budget | Giữ status/header |
| 503 Service Unavailable | Lỗi tạm thời của upstream | Giữ status/body, policy riêng |
| Socket timeout, DNS failure | Không có HTTP status đáng tin | Client transport exception |

Các mapping trong bảng là **hợp đồng thiết kế cho ví dụ**, không phải chính sách bắt buộc của mọi API. Chẳng hạn 404 có thể là protocol failure nếu endpoint yêu cầu resource luôn tồn tại; một endpoint DELETE có thể trả 204 bình thường.

### 2.1. Vì sao không catch mọi exception?

Anti-pattern:

```java
try {
    return Optional.of(callUpstream());
} catch (Exception anyProblem) {
    return Optional.empty();
}
```

Đây là đoạn minh họa, không phải một method runnable độc lập. Nó trộn lỗi `404`, `503`, JSON hỏng, `401` và timeout thành cùng một kết quả “không có dữ liệu”. Hậu quả có thể nghiêm trọng: ứng dụng hiển thị một sản phẩm “không tồn tại” trong khi thực tế catalog đang sập.

Chính sách đúng thường là **catch loại lỗi thật sự mang nghĩa domain** (ví dụ `HttpClientErrorException.NotFound`), để các lỗi khác lan truyền hoặc được map rõ ràng.

## 3. Chọn công cụ giả lập phù hợp

| Công cụ | Cơ chế | Tốt cho | Không chứng minh |
|---|---|---|---|
| Mockito mock `CatalogClient` | Bỏ HTTP layer, trả object/throw trực tiếp | Logic service tiêu thụ kết quả | URI/headers/JSON conversion/timeout |
| `MockRestServiceServer` | Thay client HTTP request factory bằng stub | RestClient/RestTemplate request matching, body/status branch | Socket/TLS/proxy thật |
| `@RestClientTest` | Spring Boot slice dành cho HTTP client | DI, properties, JSON converters, RestClient builder, mock requests | Toàn bộ application/real upstream |
| `MockWebServer` | HTTP server thật trên cổng loopback ngẫu nhiên | Request/response qua network stack, WebClient, delay/disconnect | Contract của production server nếu fixtures không đúng |
| WireMock | HTTP stub server có mapping/scenarios/faults | Nhiều endpoints, scenarios phức tạp, retries | Upstream thực không thay đổi contract |
| Testcontainers backend | Khởi động server/database thật | Tích hợp protocol/dialect production-like | Bảo đảm toàn bộ deployment production |

`MockMvc` và `WebTestClient.bindToController` chủ yếu kiểm thử **phía server/controller** của ứng dụng. Chúng không tự kiểm tra một HTTP client gọi upstream. Tên của các thư viện tương tự nhưng đối tượng kiểm tra khác nhau.

**Hai tầng thực dụng:** test phần lớn tình huống response bằng `MockRestServiceServer` cho tốc độ, bổ sung một số test qua `MockWebServer` khi cần kiểm tra client network stack và Reactive pipeline.

## 4. Hợp đồng sản phẩm minh họa

HTTP request:

```http
GET /v1/products/SKU-101 HTTP/1.1
Accept: application/json
```

Response thành công:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":101,"sku":"SKU-101","name":"Keyboard","priceCents":250000}
```

Quy tắc domain:
- `id > 0`.
- `sku` phải khớp **chính xác** SKU được hỏi.
- `name` không được null hoặc blank.
- `priceCents >= 0` (cho phép sản phẩm miễn phí).
- 404 có nghĩa sản phẩm không tồn tại.
- GET này **luôn** phải có body khi status success.

Đây là một hợp đồng tường minh; nếu API sản phẩm thực tế dùng `BigDecimal`, currency code hoặc JSON schema version, cần thay đổi DTO/validation và test cho nhất quán. Không dùng `double` cho tiền nếu hệ thống yêu cầu số tiền chính xác.

## 5. Dự án Java 17+ Spring Boot 3.5 đầy đủ

Cấu trúc file:

```text
build.gradle
src/main/java/com/example/httpdemo/
    HttpDemoApplication.java
    ProductDto.java
    InvalidProductResponseException.java
    ProductContract.java
    CatalogClient.java
    ReactiveCatalogClient.java
src/test/java/com/example/httpdemo/
    CatalogClientMockTest.java
    CatalogClientSliceTest.java
    ReactiveCatalogClientTest.java
```

### 5.1. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`starter-web` cung cấp Spring MVC, `RestClient` và Jackson; `starter-webflux` cung cấp `WebClient`/Reactor Netty. Khi có cả hai starter, Boot 3.x thường chọn MVC làm **server-side application type**, nhưng cả hai HTTP clients vẫn dùng được. Ở đây ta chỉ kiểm tra clients.

MockWebServer 4.12.0 được khai báo version tường minh. Dự án thực tế nên chọn version đã được kiểm tra trong dependency tree và security policy. MockRestServiceServer nằm trong `spring-test`, có qua starter-test. Không cần Docker hoặc API Internet để chạy các test mock.

### 5.2. Application class

Tệp `src/main/java/com/example/httpdemo/HttpDemoApplication.java`:

```java
package com.example.httpdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpDemoApplication.class, args);
    }
}
```

Chúng ta không cần chạy main để kiểm tra HTTP client. Nếu chạy app thật, cần cung cấp property `catalog.base-url` (chẳng hạn biến môi trường `CATALOG_BASE_URL`); không dùng host production trong unit tests.

### 5.3. DTO và exception tách riêng

`src/main/java/com/example/httpdemo/ProductDto.java`:

```java
package com.example.httpdemo;

public record ProductDto(
        long id,
        String sku,
        String name,
        long priceCents) {
}
```

`src/main/java/com/example/httpdemo/InvalidProductResponseException.java`:

```java
package com.example.httpdemo;

public class InvalidProductResponseException
        extends RuntimeException {

    public InvalidProductResponseException(String message) {
        super(message);
    }
}
```

### 5.4. Validation sau khi JSON đã parse

`src/main/java/com/example/httpdemo/ProductContract.java`:

```java
package com.example.httpdemo;

import java.util.Objects;

public final class ProductContract {

    private ProductContract() {
    }

    public static ProductDto requireValid(
            String requestedSku, ProductDto product) {

        Objects.requireNonNull(requestedSku);

        if (product == null) {
            throw new InvalidProductResponseException(
                    "Expected response body");
        }
        if (product.id() <= 0) {
            throw new InvalidProductResponseException(
                    "Invalid product id");
        }
        if (!requestedSku.equals(product.sku())) {
            throw new InvalidProductResponseException(
                    "Response SKU differs from requested SKU");
        }
        if (product.name() == null ||
                product.name().isBlank()) {
            throw new InvalidProductResponseException(
                    "Missing or blank product name");
        }
        if (product.priceCents() < 0) {
            throw new InvalidProductResponseException(
                    "Negative price");
        }
        return product;
    }
}
```

**Điểm khác biệt:** JSON hợp lệ về cú pháp chưa đủ. Jackson có thể deserialize record với `name=null` hoặc `id=0` khi thiếu field trong một cấu hình thường gặp. `ProductContract` bảo vệ ranh giới nghiệp vụ bất kể DTO được deserialize bằng RestClient hay WebClient.

Không mặc định mọi ObjectMapper đều cho phép missing fields: các tùy chọn Jackson như `FAIL_ON_MISSING_CREATOR_PROPERTIES` hoặc strict coercion có thể khiến decode fail sớm hơn. Test **trên chính ObjectMapper/HTTP client configuration của ứng dụng** nếu contract phụ thuộc chi tiết đó.

### 5.5. RestClient thực: 404 empty, lỗi khác không bị nuốt

Tệp `src/main/java/com/example/httpdemo/CatalogClient.java`:

```java
package com.example.httpdemo;

import java.util.Objects;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

@Service
public class CatalogClient {

    private final RestClient client;

    public CatalogClient(
            RestClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
    }

    public Optional<ProductDto> findBySku(String sku) {
        Objects.requireNonNull(sku, "sku");
        try {
            ProductDto body = client.get()
                    .uri("/v1/products/{sku}", sku)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(ProductDto.class);

            return Optional.of(
                    ProductContract.requireValid(sku, body));
        } catch (HttpClientErrorException.NotFound ex) {
            return Optional.empty();
        }
    }
}
```

Khi dùng `retrieve()`, RestClient mặc định tạo **exception cho 4xx/5xx**. Chỉ 404 được catch thành `Optional.empty()`. Điều này **không tự động áp dụng** cho mọi endpoint: nếu contract 404 là một lỗi cần surface, bỏ mapping đó.

Nếu bạn đổi sang `RestClient.exchange(...)`, các status handlers thuộc `retrieve()` không được tự áp dụng; khi ấy code trong exchange callback cần kiểm tra status rõ ràng.

## 6. RestClient + MockRestServiceServer: phản hồi thành công, sai dữ liệu và mã lỗi

MockRestServiceServer gắn vào `RestClient.Builder` để các request từ `CatalogClient` được kiểm tra như HTTP request, nhưng **không mở socket ra Internet**. Nó có thể kiểm tra URI, method, headers, body và trả responses do test quy định.

### 6.1. Lớp JUnit hoàn chỉnh

Tệp `src/test/java/com/example/httpdemo/CatalogClientMockTest.java`:

```java
package com.example.httpdemo;

import java.net.SocketTimeoutException;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.client.response.ResponseCreator;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withNoContent;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class CatalogClientMockTest {

    private static final String BASE =
            "https://catalog.example.test";

    private MockRestServiceServer server;
    private CatalogClient catalog;

    @BeforeEach
    void setup() {
        RestClient.Builder builder = RestClient.builder();
        server = MockRestServiceServer.bindTo(builder).build();
        catalog = new CatalogClient(builder, BASE);
    }

    @AfterEach
    void verifyRequests() {
        server.verify();
    }

    private void expect(
            String sku, ResponseCreator response) {
        server.expect(
                    requestTo(BASE + "/v1/products/" + sku))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE))
                .andRespond(response);
    }

    @Test
    void success200DecodesExpectedData() {
        expect("SKU-101", withSuccess("""
                {"id":101,"sku":"SKU-101",
                 "name":"Keyboard","priceCents":250000}
                """, MediaType.APPLICATION_JSON));

        ProductDto product = catalog.findBySku("SKU-101")
                .orElseThrow();

        assertEquals(101, product.id());
        assertEquals("SKU-101", product.sku());
        assertEquals("Keyboard", product.name());
        assertEquals(250000, product.priceCents());
    }

    @Test
    void zeroPriceIsAcceptedIfContractAllowsIt() {
        expect("FREE", withSuccess("""
                {"id":1,"sku":"FREE",
                 "name":"Gift","priceCents":0}
                """, MediaType.APPLICATION_JSON));

        assertEquals(
                0L,
                catalog.findBySku("FREE")
                        .orElseThrow()
                        .priceCents());
    }

    @Test
    void successfulJsonWithMismatchedSkuIsRejected() {
        expect("ASKED", withSuccess("""
                {"id":2,"sku":"OTHER",
                 "name":"Wrong record","priceCents":100}
                """, MediaType.APPLICATION_JSON));

        assertThrows(
                InvalidProductResponseException.class,
                () -> catalog.findBySku("ASKED"));
    }

    @Test
    void missingNameIn200ResponseIsRejected() {
        expect("MISS", withSuccess("""
                {"id":3,"sku":"MISS","priceCents":100}
                """, MediaType.APPLICATION_JSON));

        assertThrows(
                InvalidProductResponseException.class,
                () -> catalog.findBySku("MISS"));
    }

    @Test
    void missingIdIn200ResponseIsRejected() {
        expect("ID", withSuccess("""
                {"sku":"ID","name":"Item","priceCents":100}
                """, MediaType.APPLICATION_JSON));

        assertThrows(
                InvalidProductResponseException.class,
                () -> catalog.findBySku("ID"));
    }

    @Test
    void negativePriceIn200ResponseIsRejected() {
        expect("NEG", withSuccess("""
                {"id":4,"sku":"NEG",
                 "name":"Item","priceCents":-1}
                """, MediaType.APPLICATION_JSON));

        assertThrows(
                InvalidProductResponseException.class,
                () -> catalog.findBySku("NEG"));
    }

    @Test
    void emptyBodyIsInvalidForThisGetContract() {
        expect("EMPTY",
                withSuccess("", MediaType.APPLICATION_JSON));

        assertThrows(
                InvalidProductResponseException.class,
                () -> catalog.findBySku("EMPTY"));
    }

    @Test
    void malformedJsonGivesDecodeErrorNotNotFound() {
        expect("JSON", withSuccess("""
                {"id":5,"sku":
                """, MediaType.APPLICATION_JSON));

        assertThrows(
                RestClientException.class,
                () -> catalog.findBySku("JSON"));
    }

    @Test
    void status204IsInvalidWhenGetRequiresBody() {
        expect("NOCONTENT", withNoContent());

        assertThrows(
                InvalidProductResponseException.class,
                () -> catalog.findBySku("NOCONTENT"));
    }

    @Test
    void notFound404BecomesEmptyOptional() {
        expect("ABSENT", withStatus(HttpStatus.NOT_FOUND));

        assertTrue(catalog.findBySku("ABSENT").isEmpty());
    }

    @Test
    void badRequest400IsNotMappedToEmpty() {
        expect("BAD", withStatus(HttpStatus.BAD_REQUEST));

        HttpClientErrorException.BadRequest error =
                assertThrows(
                        HttpClientErrorException.BadRequest.class,
                        () -> catalog.findBySku("BAD"));

        assertEquals(400, error.getStatusCode().value());
    }

    @Test
    void unauthorized401IsNotMappedToEmpty() {
        expect("AUTH", withStatus(HttpStatus.UNAUTHORIZED));

        HttpClientErrorException.Unauthorized error =
                assertThrows(
                        HttpClientErrorException.Unauthorized.class,
                        () -> catalog.findBySku("AUTH"));

        assertEquals(401, error.getStatusCode().value());
    }

    @Test
    void rateLimit429RetainsRetryAfter() {
        expect("RATE",
                withStatus(HttpStatus.TOO_MANY_REQUESTS)
                        .header(HttpHeaders.RETRY_AFTER, "15"));

        HttpClientErrorException.TooManyRequests error =
                assertThrows(
                        HttpClientErrorException.TooManyRequests.class,
                        () -> catalog.findBySku("RATE"));

        assertEquals(429, error.getStatusCode().value());
        assertEquals(
                "15", error.getResponseHeaders()
                        .getFirst(HttpHeaders.RETRY_AFTER));
    }

    @Test
    void serviceUnavailable503RetainsBodyAndStatus() {
        expect("DOWN",
                withStatus(HttpStatus.SERVICE_UNAVAILABLE)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body("""
                                {"code":"UPSTREAM_DOWN"}
                                """));

        HttpServerErrorException.ServiceUnavailable error =
                assertThrows(
                        HttpServerErrorException.ServiceUnavailable.class,
                        () -> catalog.findBySku("DOWN"));

        assertEquals(503, error.getStatusCode().value());
        assertTrue(error.getResponseBodyAsString()
                .contains("UPSTREAM_DOWN"));
    }

    @Test
    void syntheticTransportFailureIsNotHttp503() {
        expect("IO", withException(
                new SocketTimeoutException(
                        "synthetic timeout")));

        RestClientException error = assertThrows(
                RestClientException.class,
                () -> catalog.findBySku("IO"));

        assertFalse(error instanceof HttpServerErrorException);
    }
}
```

Trong lớp này có **15 phương thức `@Test`**, gồm cả status 200 hợp lệ, status 200 sai dữ liệu, JSON malformed, empty/204, 400/401/404/429/503 và lỗi I/O giả.

**Đọc đúng ý nghĩa của test:**

- `withSuccess(json, MediaType.APPLICATION_JSON)` trả một body JSON **được viết độc lập với DTO serializer**, giúp kiểm tra Jackson deserialization thật.
- `ProductContract.requireValid` được gọi **sau** parse JSON. Một payload syntactically valid nhưng sai SKU sẽ gây lỗi domain, không phải lỗi syntax parser.
- `MockRestServiceServer.bindTo(builder)` chỉ ảnh hưởng `RestClient` được build từ **builder ấy**. Nếu code production tự gọi `RestClient.create()` trong method, mock server này có thể không bắt được request.
- `server.verify()` buộc expectations phải được thực hiện. Nếu client không gửi request, test fail; nếu gửi sai method/URL/header, matcher fail.
- `withException(new SocketTimeoutException(...))` giả lỗi I/O tại request factory; nó **không** thử timeout của socket thực. Với lỗi transport real, dùng `MockWebServer`/WireMock.
- Test 429 kiểm tra header `Retry-After` nhưng **không tự retry**. Không bịa rằng `RestClient` có retry policy mặc định.
- `204` được coi là lỗi chỉ vì hợp đồng GET này bắt buộc body. Với DELETE/PUT, `204` có thể hoàn toàn hợp lệ.

### 6.2. Tại sao assert request quan trọng?

Test chỉ cấu hình:

```java
server.expect(requestTo("/v1/products/SKU-101"))
        .andRespond(withSuccess());
```

là không đủ nếu ứng dụng dùng base URL đầy đủ và contract còn yêu cầu method, Accept header hoặc authentication. Với nhiều request, bạn có thể dùng `ExpectedCount.times(n)` và matcher `content().json(...)` cho POST body. Test nên mô tả **request do client thật tạo**, không chỉ response giả.

## 7. @RestClientTest: kiểm tra Spring-managed client bean

Lớp trên khởi tạo `RestClient.Builder` thủ công. Nó phù hợp kiểm tra logic nhanh; để chắc chắn property/DI, JSON converters và builder do **Spring Boot** cung cấp đúng, dùng `@RestClientTest`.

Tệp `src/test/java/com/example/httpdemo/CatalogClientSliceTest.java`:

```java
package com.example.httpdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(CatalogClient.class)
@TestPropertySource(properties = {
        "catalog.base-url=https://catalog.example.test"
})
class CatalogClientSliceTest {

    @Autowired
    CatalogClient catalog;

    @Autowired
    MockRestServiceServer server;

    @Test
    void springBeanUsesConfiguredBaseUrl() {
        server.expect(requestTo(
                "https://catalog.example.test/v1/products/BOOT"))
                .andRespond(withSuccess("""
                        {"id":50,"sku":"BOOT",
                         "name":"Spring Client","priceCents":5000}
                        """, MediaType.APPLICATION_JSON));

        ProductDto p = catalog.findBySku("BOOT")
                .orElseThrow();

        assertEquals(50L, p.id());
        assertEquals("Spring Client", p.name());
        server.verify();
    }
}
```

`@RestClientTest(CatalogClient.class)` là một **client-focused test slice**, không khởi động web server thật và thường không nạp controller, service khác, datasource hay toàn ứng dụng. Nó hữu ích khi cần kiểm tra Spring DI, `@Value`, `RestClient.Builder`, JSON message converters và các customizers của Boot.

`@TestPropertySource` cung cấp base URL giả; không gửi request đến domain đó vì `MockRestServiceServer` đã được bind. `MockRestServiceServer` tự động có sẵn khi test slice phù hợp với builder do Boot quản lý.

## 8. WebClient: mock HTTP qua socket thật

`WebClient` trả `Mono`/`Flux` lazy. Chỉ `assertNotNull(webClient.get()...)` là chưa kiểm tra gì; cần một **subscription**. `MockWebServer` là một local HTTP server thật, phát status/headers/body và ghi lại request đã nhận. Kết hợp `StepVerifier` giúp kiểm chứng `onNext`, `onError` và `onComplete` chính xác.

### 8.1. ReactiveCatalogClient

Tệp `src/main/java/com/example/httpdemo/ReactiveCatalogClient.java`:

```java
package com.example.httpdemo;

import java.util.Objects;
import java.util.Optional;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Mono;

public class ReactiveCatalogClient {

    private final WebClient web;

    public ReactiveCatalogClient(WebClient web) {
        this.web = Objects.requireNonNull(web);
    }

    public Mono<Optional<ProductDto>> findBySku(String sku) {
        Objects.requireNonNull(sku, "sku");

        return web.get()
                .uri("/v1/products/{sku}", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(ProductDto.class)
                .switchIfEmpty(Mono.error(
                        new InvalidProductResponseException(
                                "Expected response body")))
                .map(dto -> Optional.of(
                        ProductContract.requireValid(sku, dto)))
                .onErrorResume(
                        WebClientResponseException.NotFound.class,
                        ex -> Mono.just(
                                Optional.<ProductDto>empty()));
    }
}
```

Ở đây `retrieve()` biến HTTP 4xx/5xx thành `WebClientResponseException`; chỉ `NotFound` được recover. JSON malformed sinh **decode error** (khác HTTP status error); 200 body rỗng sinh lỗi hợp đồng từ `switchIfEmpty`. Không gọi `.subscribe()` bên trong adapter để không mất error propagation của caller.

### 8.2. JUnit test dùng MockWebServer

Tệp `src/test/java/com/example/httpdemo/ReactiveCatalogClientTest.java`:

```java
package com.example.httpdemo;

import java.io.IOException;
import java.util.Optional;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.codec.DecodingException;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveCatalogClientTest {

    private MockWebServer server;
    private ReactiveCatalogClient catalog;

    @BeforeEach
    void start() throws IOException {
        server = new MockWebServer();
        server.start();

        String root = server.url("/").toString();
        String baseUrl = root.substring(0, root.length() - 1);

        catalog = new ReactiveCatalogClient(
                WebClient.builder().baseUrl(baseUrl).build());
    }

    @AfterEach
    void stop() throws IOException {
        server.shutdown();
    }

    private void enqueue(int status, String body) {
        server.enqueue(new MockResponse()
                .setResponseCode(status)
                .addHeader(
                        "Content-Type",
                        MediaType.APPLICATION_JSON_VALUE)
                .setBody(body));
    }

    @Test
    void success200AndRequestContract()
            throws InterruptedException {
        enqueue(200, """
                {"id":80,"sku":"WEB",
                 "name":"Web Item","priceCents":8000}
                """);

        StepVerifier.create(catalog.findBySku("WEB"))
                .assertNext(result -> {
                    ProductDto p = result.orElseThrow();
                    assertEquals(80L, p.id());
                    assertEquals("WEB", p.sku());
                })
                .verifyComplete();

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/v1/products/WEB", request.getPath());
        assertEquals(
                MediaType.APPLICATION_JSON_VALUE,
                request.getHeader("Accept"));
    }

    @Test
    void successWithWrongDataSignalsDomainError() {
        enqueue(200, """
                {"id":1,"sku":"OTHER",
                 "name":"Wrong","priceCents":100}
                """);

        StepVerifier.create(catalog.findBySku("ASKED"))
                .expectError(
                        InvalidProductResponseException.class)
                .verify();
    }

    @Test
    void malformedJsonSignalsDecodingError() {
        enqueue(200, """
                {"id":99,"sku":
                """);

        StepVerifier.create(catalog.findBySku("BADJSON"))
                .expectError(DecodingException.class)
                .verify();
    }

    @Test
    void emptySuccessBodyIsRejected() {
        enqueue(200, "");

        StepVerifier.create(catalog.findBySku("EMPTY"))
                .expectError(
                        InvalidProductResponseException.class)
                .verify();
    }

    @Test
    void notFound404BecomesEmptyOptional() {
        enqueue(404, """
                {"code":"NOT_FOUND"}
                """);

        StepVerifier.create(catalog.findBySku("NONE"))
                .expectNext(Optional.empty())
                .verifyComplete();
    }

    @Test
    void serviceUnavailable503RemainsHttpError() {
        enqueue(503, """
                {"code":"UPSTREAM_UNAVAILABLE"}
                """);

        StepVerifier.create(catalog.findBySku("DOWN"))
                .expectErrorSatisfies(error -> {
                    WebClientResponseException.ServiceUnavailable ex =
                            assertInstanceOf(
                                    WebClientResponseException
                                            .ServiceUnavailable.class,
                                    error);
                    assertEquals(503, ex.getStatusCode().value());
                    assertTrue(ex.getResponseBodyAsString()
                            .contains("UPSTREAM_UNAVAILABLE"));
                })
                .verify();
    }
}
```

Trong lớp có **6 test methods**. Test thành công còn kiểm chứng `RecordedRequest` từ TCP server thật, không chỉ response. `takeRequest(2, TimeUnit.SECONDS)` ngăn test chờ vô hạn nếu client chưa gửi request.

Khi test nhiều responses/retries, MockWebServer có queue trả lần lượt và request journal. Khởi tạo server mới cho mỗi test, start trên port động và `shutdown()` trong `@AfterEach` tránh test order dependence.

## 9. Cách thử “200 nhưng dữ liệu sai” sâu hơn

Một status 200 có thể chứa:

```json
{
  "id": 101,
  "sku": "SKU-WRONG",
  "name": "Keyboard",
  "priceCents": -100
}
```

Jackson có thể đọc được tất cả field, nhưng **cả SKU và giá đều vi phạm contract**. Điều cần assert là kết quả ở ranh giới adapter, không chỉ equality giữa `ProductDto` và object mong đợi.

### 9.1. Missing, null, blank và default số

```json
{"sku":"SKU-101","priceCents":250000}
```

Nếu client DTO dùng `long id`, một cấu hình Jackson có thể mặc định `id=0` khi thiếu field; `name=null`. Vì thế test có ca `missingId` và `missingName`. Nếu thực sự cần Jackson fail ngay khi thiếu field, cấu hình strict deserialization và viết tests **đúng với ObjectMapper production**.

```json
{"id":101,"sku":null,"name":"Keyboard","priceCents":250000}
```

Java `ProductDto.sku()` có thể là null; `requestedSku.equals(product.sku())` không ném NPE mà trả false, dẫn tới lỗi hợp đồng. Nhưng khi `ProductDto` dùng constructor `Objects.requireNonNull` hoặc Bean Validation, thời điểm lỗi có thể chuyển sớm hơn. Không hard-code test exception type ngoài những rules thực sự được thiết kế.

### 9.2. JSON sai cú pháp vs sai kiểu

```text
{"id":101,"sku":
```

Body này không thể deserialize do JSON chưa kết thúc. Một body khác:

```json
{"id":"not-a-number","sku":"SKU-101","name":"A","priceCents":100}
```

có thể gây conversion error vì `id` là `long`. Trong cả hai trường hợp, lỗi decode **khác** response 404. Nếu client log lỗi, nên ghi mã lỗi loại `UPSTREAM_BAD_JSON` và request correlation ID được redacted, không log toàn bộ payload chứa PII.

### 9.3. Wrong Content-Type/charset

Body JSON có thể đi kèm `Content-Type: text/plain`, khiến converter JSON không được chọn. Test cần phản hồi có header **sai thực tế**, không chỉ truyền String vào method mock; dùng `withSuccess(json, MediaType.TEXT_PLAIN)` và assert kiểu conversion error trong setup client thật.

Với UTF-8, tên sản phẩm tiếng Việt nên có test ký tự Unicode để tránh lỗi encoding. Nếu test sinh body từ chính DTO/ObjectMapper của client, cả hai có thể cùng sai một tên field mà test vẫn pass; nên dùng **fixture JSON độc lập** hoặc provider contract samples.

## 10. Kiểm thử HTTP status theo semantics, không gom chung 4xx/5xx

| Status | Ý nghĩa thường gặp | Chính sách cần test |
|---|---|---|
| `201 Created` | Tạo resource | `Location`/body/ID theo contract |
| `202 Accepted` | Đã nhận xử lý async | Không coi là workflow hoàn tất |
| `204 No Content` | Thành công không body | Hợp lệ với endpoint thích hợp |
| `400 Bad Request` | Request không hợp lệ | Không retry vô hạn |
| `401 Unauthorized` | Authentication failure | Không log token, refresh policy có giới hạn |
| `403 Forbidden` | Thiếu quyền | Không tự đổi thành 404 nếu contract không nói |
| `404 Not Found` | Không có resource/endpoint | Optional.empty chỉ theo lookup contract |
| `409 Conflict` | Trạng thái/version conflict | Domain error rõ, kiểm tra idempotency |
| `422 Unprocessable Content` | Dữ liệu sai quy tắc xử lý | Lỗi validation/domain rõ |
| `429 Too Many Requests` | Rate limit | Kiểm tra `Retry-After`, số lần retry |
| `500 Internal Server Error` | Upstream lỗi | Giữ trạng thái, alert/log đã redacted |
| `502 Bad Gateway` | Upstream/gateway response hỏng | Phân biệt client timeout |
| `503 Service Unavailable` | Service tạm down | Retry/circuit breaker/fallback nếu policy cho |
| `504 Gateway Timeout` | Gateway chờ upstream quá lâu | Không đồng nhất với `SocketTimeoutException` của client |

**Lưu ý:** `Retry-After` có thể là số giây hoặc HTTP-date, không nhất thiết là số nguyên. Nếu dùng chính sách retry, phải có giới hạn số lần và tổng thời gian; với POST thanh toán/đơn hàng không idempotent, retry khi kết quả chưa xác định có thể tạo side effect lặp.

Một test 503 có body:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 15

{"code":"UPSTREAM_UNAVAILABLE"}
```

nên assert status, header nếu policy đọc, và error code nếu client parse body. Không giả định mọi error body là JSON; reverse proxy có thể trả HTML hoặc empty response.

### 10.1. Application/problem+json

Khi upstream theo RFC 9457, lỗi có thể dùng `application/problem+json`:

```json
{
  "type": "https://errors.example.test/not-allowed",
  "title": "Request rejected",
  "status": 422,
  "detail": "SKU format is not supported"
}
```

Test cần xác minh cách client map problem details khi đó là **contract đã thỏa thuận**. Đừng để một exception mapper bắt mọi lỗi và tự tạo cùng một `ProblemDetail` chung nếu caller cần phân biệt lỗi authorization, validation và upstream failure.

## 11. Giả lập lỗi network/timeout khác gì giả lập 503?

**HTTP status** là một response từ server. Trong các tình huống sau có thể **không có HTTP response**:
- DNS name không được resolve.
- TCP connect timeout/connection refused.
- TLS handshake thất bại.
- Socket bị reset giữa request/response.
- Read timeout trước khi đọc đủ response.
- Reactive subscriber cancel request.

`MockRestServiceServer.withException(new SocketTimeoutException("synthetic"))` là cách thử code xử lý **IOException ở request factory**, nhanh và deterministic. Nhưng nó không đo socket read timeout đã cấu hình đúng hay không.

Để kiểm tra network stack thực, sử dụng `MockWebServer`/WireMock trên cổng loopback và mô phỏng delay, connection drop, throttled body hoặc response streaming. Khi test timeout:
- Cấu hình timeout phía HTTP client rõ ràng.
- Cho server trì hoãn hơn timeout dự kiến.
- Assert loại lỗi và thời gian không vượt budget đã định, tránh test flaky quá sát ngưỡng.
- Đóng server/client resources kể cả khi assertion fail.
- Không kết luận một lỗi timeout luôn tương đương status HTTP 504.

Khi dùng `RestClient`, loại exception network có thể là `ResourceAccessException` hay subtype khác của `RestClientException` tùy request factory. Giữ test ở loại ổn định theo contract nếu code không định nghĩa mapping cụ thể.

## 12. Retry, backoff, circuit breaker và số lần gọi

Một client test tốt không chỉ kiểm tra response cuối cùng; nếu có retry, cần kiểm tra **số attempts** và policy.

Ví dụ mục tiêu “GET retry tối đa hai lần sau 503” nghĩa là **tối đa ba requests**: request đầu + hai retries. Một mock server có thể được enqueue `503, 503, 200`; test phải xác nhận caller nhận dữ liệu và mock server ghi đúng **ba requests**. Nếu library retry nằm sau AOP proxy, gọi `new CatalogClient(...)` trong test sẽ không tự kích hoạt proxy advice; test policy cần khởi tạo **Spring-managed bean** hoặc retry wrapper thật.

Các yếu tố cần test:
- Retry đúng status 429/503 hoặc transport errors được phép, không retry 400/401/403.
- Giới hạn số attempts và tổng timeout budget.
- Backoff/jitter tránh đồng loạt retry gây thundering herd.
- `Retry-After` được parse đúng và bị giới hạn theo SLA.
- Phương thức có side effect cần idempotency key và dedup.
- Khi hết attempts, lỗi cuối giữ status và thông tin có thể quan sát.

**Không có retry mặc định trong code `CatalogClient` của bài.** Test 429/503 chỉ gửi một request. Đừng tuyên bố hệ thống đã retry an toàn nếu chưa cấu hình và test thực tế.

## 13. Test requests cũng phải đúng

Response có thể hoàn toàn hợp lệ nhưng client **đã gửi request sai**:
- Sai `HttpMethod` hoặc path `/v1`.
- Thiếu `Accept: application/json` hoặc `Authorization`.
- Query param bị encode hai lần; path param có space, slash hoặc `?` sai URI encoding.
- POST body JSON bị thiếu field.
- Retry làm mất `Idempotency-Key`.
- Client mới bypass interceptor/timeout/tracing do không dùng builder của Boot.

Với MockRestServiceServer, dùng `requestTo(...)`, `method(...)`, `header(...)` và `content().json(...)` khi cần body assertions. Cuối test gọi `verify()`. Với MockWebServer, đọc `RecordedRequest` sau subscription và assert method/path/headers/body thực tế.

Khi test authorization, không log bearer token thật trong assertions. Hãy dùng test token giả và chỉ kiểm tra header format/presence nếu cần.

## 14. Chống false positive trong fixture và contract

Những lỗi thiết kế test thường gặp:

**Mock client quá sâu:** dùng `@MockBean CatalogClient` hoặc Mockito mock RestClient internal method rồi chỉ assert service logic; không có request HTTP nào được thử. Khi cần test adapter, dùng **adapter thật + fake server**.

**Response JSON tự sinh từ DTO mới:** nếu developer đổi `priceCents` thành `amount` trong DTO rồi test dùng `ObjectMapper.writeValueAsString(dto)` để tạo response, cả client và mock có thể cùng sai với upstream. Dùng JSON fixture độc lập từ OpenAPI/provider contract.

**Chỉ assert `!= null`:** một DTO có `id=0`, `sku=null` có thể vượt qua. Assert semantic contract.

**Không verify requests:** mock đã đăng ký nhưng code không gọi endpoint vẫn có thể tạo kết quả local. Dùng `MockRestServiceServer.verify()` hoặc `MockWebServer.takeRequest`.

**Chỉ test 200:** 404/429/503 có thể bị map sai hoặc dẫn đến retry không kiểm soát. Tạo mỗi status một mục tiêu assertion rõ.

**Test timeout bằng 503:** HTTP status error không có nghĩa TCP timeout. Dùng loại fault đúng.

**Tất cả lỗi trả empty:** che sự cố upstream và gây sai nghĩa dữ liệu.

**Test reactive không subscribe:** `Mono` chỉ là mô tả pipeline. Dùng StepVerifier hoặc một subscriber phù hợp.

**Cấu hình test khác production:** `RestClient.builder()` trong unit test có thể khác Boot-configured builder. Nếu test SSL/interceptor/codecs, dùng `@RestClientTest` hoặc integration config thật.

## 15. Tổ chức fixture, chạy test và xác minh report

Chạy bằng Gradle wrapper trong Linux/macOS:

```bash
./gradlew test --tests "com.example.httpdemo.CatalogClientMockTest"
./gradlew test --tests "com.example.httpdemo.CatalogClientSliceTest"
./gradlew test --tests "com.example.httpdemo.ReactiveCatalogClientTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.httpdemo.CatalogClientMockTest"
.\gradlew.bat test --tests "com.example.httpdemo.CatalogClientSliceTest"
.\gradlew.bat test --tests "com.example.httpdemo.ReactiveCatalogClientTest"
```

Nếu project dùng Maven wrapper với dependencies tương đương:

```bash
./mvnw -Dtest=CatalogClientMockTest test
./mvnw -Dtest=CatalogClientSliceTest test
./mvnw -Dtest=ReactiveCatalogClientTest test
```

Dự án ví dụ gồm **15 ca MockRestServiceServer, 1 ca Spring Boot @RestClientTest và 6 ca MockWebServer/WebClient**: tổng **22 ca được thiết kế**. Đây là mã nguồn/expected behavior, **không phải bằng chứng thực thi** trong máy hiện tại.

`build.gradle` không tự tạo wrapper; dự án cần Gradle wrapper sẵn hoặc Gradle tương thích. Với Maven cần `pom.xml` và Maven Surefire tương đương. Đọc `build/reports/tests/test/index.html` (Gradle) hoặc `target/surefire-reports/` (Maven) để xác nhận test thực sự chạy, không bị `NO-SOURCE`, skip hoặc chỉ trả cached result.

Nếu có `NoSuchBeanDefinitionException` khi dùng `@RestClientTest`, kiểm tra `RestClient.Builder` từ Boot, test slice scope và `catalog.base-url`. Nếu WebClient test fail `Connection refused`, kiểm tra mock server `start()` và baseUrl đã lấy **sau** lúc start; không hard-code port 8080.

## 16. Checklist QA trước khi kết luận HTTP client đúng

- [ ] Có hợp đồng request: method, URL/path/query, headers và body nếu có.
- [ ] 200 hợp lệ được decode và validate các trường quan trọng.
- [ ] Có 200 **sai ngữ nghĩa** như SKU không khớp, missing/blank name, giá âm.
- [ ] Có JSON sai cú pháp hoặc sai kiểu, phân biệt decode error với domain invalid.
- [ ] Có test body rỗng/204 theo contract của endpoint.
- [ ] Chỉ 404 được map `Optional.empty()` khi nghiệp vụ đã cho phép.
- [ ] 400/401/403/409/422/429 không bị gộp thành một not-found fallback.
- [ ] 429 giữ `Retry-After`, 5xx giữ status/body nếu cần.
- [ ] Lỗi I/O/timeout không bị gán status HTTP tưởng tượng.
- [ ] Fake server verify request thực và số lần gọi.
- [ ] Với WebClient, StepVerifier đã subscribe và assert signals.
- [ ] Fixtures JSON độc lập với DTO serializer của client.
- [ ] Khi có retry, assert attempts, backoff, idempotency và budget.
- [ ] Timeout/TLS/redirect được test bằng transport-level mock nếu yêu cầu.
- [ ] Không đưa token thật, PII hoặc public production API vào tests.
- [ ] Đã chạy đúng test runner, kiểm tra JUnit reports rồi mới tuyên bố runtime PASS.

## 17. Tài liệu tham khảo

- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): `RestClient`, `retrieve`, status handlers và message conversion.
- [Spring Framework — Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): `MockRestServiceServer`, request matchers, response creators và `verify`.
- [Spring Framework — MockRestResponseCreators Javadoc](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/test/web/client/response/MockRestResponseCreators.html): `withSuccess`, `withStatus`, `withException`, `withNoContent`.
- [Spring Framework — Testing WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html): sử dụng `MockWebServer`/WireMock.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@RestClientTest` và client test setup.
- [OkHttp MockWebServer](https://github.com/square/okhttp/tree/master/mockwebserver): HTTP mock server/recorded requests.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP status và method semantics.
- [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457): error body `application/problem+json`.

**Kết luận:** Giả lập HTTP client hiệu quả không dừng ở việc trả JSON 200. Phải kiểm tra **request contract**, parse và validate dữ liệu, phân loại rõ **200 sai body**, **4xx/5xx** và **lỗi truyền tải**, cùng retry/fallback policy khi có. `MockRestServiceServer`/`@RestClientTest` phù hợp cho RestClient test nhanh và chính xác; `MockWebServer`/`StepVerifier` bổ sung kiểm tra WebClient qua HTTP socket thật. Bài test chỉ đáng tin khi đã gửi request đúng hợp đồng và chứng minh outcome phù hợp với từng tình huống.