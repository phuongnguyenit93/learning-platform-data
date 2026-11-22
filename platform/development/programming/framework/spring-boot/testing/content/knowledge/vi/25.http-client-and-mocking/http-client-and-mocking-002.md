# @RestClientTest và cấu hình client được đưa vào slice

## 1. Bài học tập trung vào điều gì?

Một ứng dụng Spring Boot có thể gọi API bên ngoài để lấy sản phẩm, kiểm tra tồn kho, gửi email, tính vận chuyển hoặc tra cứu tỷ giá. HTTP client của ứng dụng cần tạo **URL, HTTP method, headers và JSON** đúng; đồng thời phải xử lý các response 200, 204, 400, 404, 429, 503 và lỗi decode theo hợp đồng. Nếu dùng Mockito mock chính lớp HTTP client, các test cấp service không phát hiện được đường dẫn sai, API key bị bỏ quên, JSON serialize sai tên field hay việc 404 bị hiểu nhầm thành response hợp lệ.

Spring Boot **3.3.5** cung cấp **`@RestClientTest`**, một test slice dành cho **outbound REST clients**. Nó auto-configures JSON infrastructure (Jackson/Gson/Jsonb), `RestTemplateBuilder`, `RestClient.Builder` và `MockRestServiceServer`; nhưng **không tự scan tất cả regular `@Component` và `@ConfigurationProperties`** như một full application context.

Bài này thuộc nhóm **HTTP client và giả lập**, đi thẳng vào đề bài **“@RestClientTest và cấu hình client được đưa vào slice”**:

1. Chọn đúng một client adapter với `@RestClientTest(TargetClass.class)`.
2. Đưa **production client configuration** vào slice qua `@Import`, không viết lại một client khác chỉ để test.
3. Đăng ký typed properties qua `@EnableConfigurationProperties` và cung cấp test-only configuration values.
4. Dùng `RestClient.Builder` do Spring Boot auto-configure để mock server intercept HTTP call.
5. Kiểm tra URL tuyệt đối, request headers, JSON body, response mapping và lỗi HTTP bằng `MockRestServiceServer`.
6. Phân biệt `RestClient.Builder` với `RestTemplateBuilder.rootUri` về cách xác định expected request URI.
7. Hiểu giới hạn: mock server **không mở TCP socket**, nên không kiểm tra DNS/TLS/connection timeout hoặc network proxy thực.

Ngôn ngữ: **Java 17+**. Project mẫu dùng **Spring Boot 3.3.5**, **Spring Framework 6.1**, Gradle/JUnit Jupiter và không cần kết nối mạng tới API đối tác trong test.

## 2. Kiến trúc của test slice

```text
JUnit Jupiter
    |
    +-- @RestClientTest(PartnerProductGateway.class)
           |
           +-- PartnerProductGateway (@Component được chọn rõ)
           |
           +-- @Import(PartnerRestClientConfiguration.class)
           |       |
           |       +-- @EnableConfigurationProperties
           |       |       PartnerClientProperties
           |       |
           |       +-- @Bean("partnerRestClient")
           |               RestClient.Builder của Boot
           |               baseUrl + default headers
           |
           +-- MockRestServiceServer
                   |
                   +-- expected URI / method / headers / body
                   +-- trả JSON hoặc HTTP lỗi đã cấu hình
```

Lớp `PartnerProductGateway` và `PartnerRestClientConfiguration` là **mã ứng dụng thật**. Dữ liệu response và “server” do test điều khiển. Khi Gateway gọi `RestClient.retrieve().body(...)`, Spring chuyển request qua mock request factory rồi đưa response cho HTTP message converter xử lý. Không có DNS lookup tới `api.partner.test` trong dòng test thành công.

### Nó khác gì @WebMvcTest?

| Phương án | Hướng HTTP | Đối tượng test | Công cụ |
| --- | --- | --- | --- |
| `@RestClientTest` | **Outbound**: ứng dụng gọi service khác | REST client/adapter | `MockRestServiceServer` |
| `@WebMvcTest` | **Inbound**: client gọi controller | Spring MVC controller | `MockMvc` |
| `@SpringBootTest` | Ứng dụng nhiều lớp | Wiring/integration rộng | Có thể kết hợp mock server |
| JUnit + Mockito | Không cần HTTP thật | Logic gọi dependency | Mockito mocks |
| WireMock/MockWebServer | Outbound qua local TCP | HTTP network boundary | Real local server |
| Contract tests | Producer ↔ consumer | API schema/compatibility | Provider/consumer verification |

Không dùng `@WebMvcTest` với `MockMvc` để kiểm chứng outbound client: đó là chiều HTTP ngược lại. Cũng không dùng `@MockBean` trên chính Gateway trong `@RestClientTest`, vì lúc ấy HTTP client thật không chạy và mock server không nhận request.

## 3. Những bean nào @RestClientTest tự cung cấp?

Trong Spring Boot 3.3, `@RestClientTest` bật tập auto-configuration nhỏ:

- `RestClient.Builder` phục vụ Spring Framework 6.1 blocking `RestClient`.
- `RestTemplateBuilder` cho blocking `RestTemplate`.
- JSON/message converters phù hợp classpath.
- `MockRestServiceServer` gắn với managed builders.
- Spring TestContext và JUnit Jupiter integration.

Nó **không tự nạp mọi `@Service`, `@Component`, `@Repository`, `@ConfigurationProperties`, DataSource hoặc controller**. Bạn phải nói rõ lớp được test bằng `value`/`components`, sau đó import những dependencies thật sự cần thiết.

Ví dụ:

```java
@RestClientTest(PartnerProductGateway.class)
@Import(PartnerRestClientConfiguration.class)
class PartnerProductGatewayTest {
}
```

Nếu chỉ thêm `@RestClientTest` mà không chọn adapter, một bean bình thường như `PartnerProductGateway` có thể không xuất hiện. Nếu chọn adapter nhưng không import config cần tạo `RestClient`, test có thể fail khi xây bean do thiếu dependency.

### @Import và @ImportAutoConfiguration

- `@Import(MyConfiguration.class)`: thêm một ordinary `@Configuration` hoặc bean cụ thể vào test context; phù hợp với client config ứng dụng.
- `@EnableConfigurationProperties(MyProperties.class)`: đăng ký typed properties được bind vào bean; có thể đặt trên config được import.
- `@ImportAutoConfiguration(...)`: cho **Spring Boot auto-configuration** cần thêm vào slice; không import các auto-config classes bừa bãi bằng ordinary `@Import`.
- `@TestConfiguration`: dùng khi cần test-specific collaborator/config, không nên thay thế toàn bộ production client config nếu mục tiêu là kiểm tra chính config ấy.

Đưa cấu hình vào slice là hành động có chủ đích, **không phải bật component scan cho toàn bộ ứng dụng** để tránh lỗi thiếu bean.

## 4. RestClient, RestTemplate và WebClient

| API | Đặc điểm | Test |
| --- | --- | --- |
| `RestClient` | Blocking, fluent, có từ Spring Framework 6.1 | `@RestClientTest` với `RestClient.Builder` |
| `RestTemplate` | Blocking, API lâu đời | `@RestClientTest` với `RestTemplateBuilder` |
| `WebClient` | Reactive, `Mono`/`Flux` | Strategy dành cho reactive WebClient, không mặc định coi là RestClient |
| Declarative HTTP interface | Proxy gọi qua RestClient/WebClient adapter | Cần cấu hình proxy và underlying client phù hợp |

Trong ví dụ chính, production config tạo **một `RestClient` bean** bằng `RestClient.Builder` auto-managed, rồi adapter inject RestClient ấy. Cách này có lợi khi client có base URL/API key riêng và app có nhiều outbound clients.

**Tránh `RestClient.create()` trong bean under test** nếu đang dựa vào auto mock từ slice: client tạo bằng factory độc lập có thể không nhận Boot customizers hoặc `MockRestServiceServer`. Dùng managed builder hoặc explicit mock binding theo cách đã được thiết kế.

## 5. Full project Java 17+ / Spring Boot 3.3.5

Cấu trúc:

```text
rest-client-slice/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/outbound/
│   ├── OutboundApplication.java
│   ├── PartnerClientProperties.java
│   ├── PartnerRestClientConfiguration.java
│   ├── PartnerItem.java
│   ├── CreateItemRequest.java
│   ├── PartnerProductGateway.java
│   └── LegacyHealthClient.java
└── src/test/java/com/example/outbound/
    ├── PartnerProductGatewayTest.java
    └── LegacyHealthClientTest.java
```

Project không cần controller, database, Docker hoặc API key thật.

### settings.gradle

```groovy
rootProject.name = 'rest-client-slice'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter-web` cung cấp Spring Web, RestClient/RestTemplate và Jackson. `spring-boot-starter-test` bao gồm JUnit Jupiter, Spring Test, `MockRestServiceServer` và Spring Boot test auto-configurations. Không cần chạy `bootRun` để thực hiện client slice test; class `@SpringBootApplication` chỉ là application root.

Nếu project chưa có Gradle Wrapper, dùng Gradle được cài phù hợp hoặc tạo Wrapper trước khi chạy `./gradlew`. Không nhầm “thiếu file gradlew” với lỗi unit test.

### OutboundApplication.java

`src/main/java/com/example/outbound/OutboundApplication.java`:

```java
package com.example.outbound;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OutboundApplication {
    public static void main(String[] args) {
        SpringApplication.run(OutboundApplication.class, args);
    }
}
```

Package application root `com.example.outbound` là package cha của adapter/config/test. Khi chạy **full application** ngoài test, client properties thực phải đến từ environment/secret manager; demo cung cấp test-only values trong annotation `@RestClientTest(properties=...)`.

## 6. Typed configuration: @ConfigurationProperties record

`src/main/java/com/example/outbound/PartnerClientProperties.java`:

```java
package com.example.outbound;

import java.net.URI;
import java.util.Objects;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "partner.catalog")
public record PartnerClientProperties(
        URI baseUrl,
        String apiKey
) {

    public PartnerClientProperties {
        Objects.requireNonNull(baseUrl, "baseUrl is required");

        if (!"https".equalsIgnoreCase(baseUrl.getScheme())) {
            throw new IllegalArgumentException(
                    "partner.catalog.base-url must be https");
        }

        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalArgumentException(
                    "partner.catalog.api-key is required");
        }
    }
}
```

Vì đây là Java 17 record có một canonical constructor, Spring Boot 3.3 dùng constructor binding tự nhiên. `partner.catalog.base-url` được relaxed-bound thành `baseUrl`, còn `partner.catalog.api-key` thành `apiKey`.

**Không hardcode secret thật.** Test chỉ dùng `test-key`, một chuỗi giả. Production nên dùng secret manager/environment properties, không đưa API key vào Git hoặc test logs.

### Tại sao không tự scan type này?

Một class có `@ConfigurationProperties` không mặc định là `@Component` trong test slice. Production thường dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`; slice cũng cần chính xác một cơ chế đăng ký. Project dùng `@EnableConfigurationProperties(PartnerClientProperties.class)` trên config được import, tránh phụ thuộc scan rộng.

Rule HTTPS trong compact constructor chỉ là policy của ví dụ. Nếu môi trường test dùng localhost HTTP thật, phải thiết kế policy/endpoint đúng thay vì disable TLS validation trong production để chiều test chạy được.

## 7. Configuration thật: tạo client từ Boot RestClient.Builder

`src/main/java/com/example/outbound/PartnerRestClientConfiguration.java`:

```java
package com.example.outbound;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PartnerClientProperties.class)
public class PartnerRestClientConfiguration {

    @Bean("partnerRestClient")
    RestClient partnerRestClient(
            RestClient.Builder builder,
            PartnerClientProperties properties) {

        return builder
                .baseUrl(properties.baseUrl().toString())
                .defaultHeader(
                        "X-Partner-Key", properties.apiKey())
                .defaultHeader(
                        "X-Client-Tag", "catalog-gateway")
                .build();
    }
}
```

Đây là **config thuộc production source**. Trong test, `@Import(PartnerRestClientConfiguration.class)` đưa đúng configuration ấy vào slice. Vì `RestClient.Builder` do Boot cung cấp và được mock integration customize, server kỳ vọng có thể bắt request.

Ý nghĩa:

- `@Bean("partnerRestClient")`: tên bean tường minh, giúp nhiều clients cùng type `RestClient` không bị inject nhầm.
- `baseUrl(...)`: lấy endpoint từ configuration record, không viết cứng trong Gateway.
- `defaultHeader("X-Partner-Key",...)`: gắn test API key; production cần bảo vệ secret.
- `defaultHeader("X-Client-Tag",...)`: thêm một header của adapter, là điểm kiểm tra config import.
- `@EnableConfigurationProperties`: bảo đảm properties type xuất hiện trong slice.

**Đừng tự tạo `new RestClient`/`RestClient.create()` ở đây.** Khi bỏ Boot-managed builder, mock server có thể không được bind vào request factory, test vô tình gọi mạng ngoài.

### Kiểm tra configuration bằng behavior

Test chỉ assert `PartnerClientProperties.apiKey()` có giá trị **chưa đủ**: client có thể không đưa property vào request. Test chính sẽ assert **`X-Partner-Key` và `X-Client-Tag` trong HTTP request** và absolute URL từ baseUrl. Đây mới là bằng chứng client config được áp dụng.

## 8. DTO request/response

`src/main/java/com/example/outbound/PartnerItem.java`:

```java
package com.example.outbound;

public record PartnerItem(
        String sku,
        String name,
        int priceCents
) {
}
```

`src/main/java/com/example/outbound/CreateItemRequest.java`:

```java
package com.example.outbound;

public record CreateItemRequest(
        String sku,
        String name,
        int priceCents
) {
}
```

Jackson trong Boot 3.3 đọc/ghi Java records có fields này. `priceCents` dùng integer minor units để tránh floating-point precision issues. Records không tự validate null và giá âm; với product contract thật có thể thêm Bean Validation, constructor invariant và negative contract tests.

## 9. Client adapter thật: PartnerProductGateway

`src/main/java/com/example/outbound/PartnerProductGateway.java`:

```java
package com.example.outbound;

import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PartnerProductGateway {

    private final RestClient client;

    public PartnerProductGateway(
            @Qualifier("partnerRestClient") RestClient client) {
        this.client = client;
    }

    public PartnerItem findBySku(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }

        PartnerItem response = client.get()
                .uri("/v1/items/{sku}", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(PartnerItem.class);

        if (response == null) {
            throw new IllegalStateException(
                    "partner returned empty item body");
        }
        return response;
    }

    public PartnerItem create(CreateItemRequest request) {
        Objects.requireNonNull(request, "request");

        PartnerItem response = client.post()
                .uri("/v1/items")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .body(PartnerItem.class);

        if (response == null) {
            throw new IllegalStateException(
                    "partner returned empty create body");
        }
        return response;
    }
}
```

`@Component` giúp component scan trong full application; `@RestClientTest(PartnerProductGateway.class)` sẽ chọn riêng bean này trong slice. Adapter không biết URL và credentials literal; mọi HTTP config đến từ injected named RestClient bean.

### GET behavior

- Validate SKU để loại request sai trước HTTP.
- Tạo GET `/v1/items/{sku}` với URI template.
- Gửi `Accept: application/json`.
- Spring tự áp dụng default headers/base URL từ bean.
- Deserialize JSON thành `PartnerItem`.
- Với `204 No Content`, `body(...)` có thể trả null; adapter ném lỗi rõ ràng.
- Với HTTP 4xx/5xx, `retrieve()` mặc định ném HTTP client/server exceptions.

### POST behavior

- Từ chối request null bằng `Objects.requireNonNull`.
- Gửi POST `/v1/items` với JSON body của `CreateItemRequest`.
- Đặt `Content-Type` và `Accept` là JSON.
- Deserialize response JSON.
- Kiểm tra response body không null.

URI template được dùng thay vì tự nối chuỗi path do user kiểm soát. Với input có dấu slash, khoảng trắng hoặc Unicode, cần bổ sung test encoding theo contract và framework version; ví dụ tập trung vào SKU ASCII rõ ràng.

## 10. Bộ @RestClientTest với @Import và MockRestServiceServer

Tạo `src/test/java/com/example/outbound/PartnerProductGatewayTest.java`:

```java
package com.example.outbound;

import java.net.URI;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;

import static org.springframework.test.web.client.response.MockRestResponseCreators.withNoContent;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(
        value = PartnerProductGateway.class,
        properties = {
            "partner.catalog.base-url=https://api.partner.test",
            "partner.catalog.api-key=test-key"
        })
@Import(PartnerRestClientConfiguration.class)
class PartnerProductGatewayTest {

    @Autowired
    PartnerProductGateway gateway;

    @Autowired
    PartnerClientProperties properties;

    @Autowired
    @Qualifier("partnerRestClient")
    RestClient configuredClient;

    @Autowired
    MockRestServiceServer server;

    @BeforeEach
    void resetExpectations() {
        server.reset();
    }

    @Test
    void clientConfigurationIsLoadedIntoSlice() {
        assertNotNull(gateway);
        assertNotNull(configuredClient);
        assertEquals(
                URI.create("https://api.partner.test"),
                properties.baseUrl());
        assertEquals("test-key", properties.apiKey());
    }

    @Test
    void getUsesAbsoluteUriHeadersAndJson() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items/SKU-1"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        "X-Partner-Key", "test-key"))
                .andExpect(header(
                        "X-Client-Tag", "catalog-gateway"))
                .andExpect(header(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE))
                .andRespond(withSuccess("""
                    {
                      "sku": "SKU-1",
                      "name": "Keyboard",
                      "priceCents": 4999
                    }
                    """, MediaType.APPLICATION_JSON));

        PartnerItem result = gateway.findBySku("SKU-1");
        assertEquals(
                new PartnerItem("SKU-1", "Keyboard", 4999),
                result);
        server.verify();
    }

    @Test
    void postSerializesRequestAndReadsResponse() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header(
                        "X-Partner-Key", "test-key"))
                .andExpect(header(
                        "X-Client-Tag", "catalog-gateway"))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(content().json("""
                    {
                      "sku": "SKU-2",
                      "name": "Monitor",
                      "priceCents": 12900
                    }
                    """, true))
                .andRespond(withSuccess("""
                    {
                      "sku": "SKU-2",
                      "name": "Monitor",
                      "priceCents": 12900
                    }
                    """, MediaType.APPLICATION_JSON));

        PartnerItem result = gateway.create(
                new CreateItemRequest(
                        "SKU-2", "Monitor", 12900));

        assertEquals(
                new PartnerItem("SKU-2", "Monitor", 12900),
                result);
        server.verify();
    }

    @Test
    void response404IsHttpClientError() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items/MISSING"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        HttpClientErrorException.NotFound error =
                assertThrows(
                    HttpClientErrorException.NotFound.class,
                    () -> gateway.findBySku("MISSING"));

        assertEquals(HttpStatus.NOT_FOUND,
                error.getStatusCode());
        server.verify();
    }

    @Test
    void response503IsHttpServerError() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items/SKU-3"))
                .andRespond(withStatus(
                        HttpStatus.SERVICE_UNAVAILABLE));

        HttpServerErrorException.ServiceUnavailable error =
                assertThrows(
                    HttpServerErrorException
                        .ServiceUnavailable.class,
                    () -> gateway.findBySku("SKU-3"));

        assertEquals(HttpStatus.SERVICE_UNAVAILABLE,
                error.getStatusCode());
        server.verify();
    }

    @Test
    void invalidSkuDoesNotCauseHttpRequest() {
        assertThrows(
                IllegalArgumentException.class,
                () -> gateway.findBySku("  "));
        server.verify();
    }

    @Test
    void nullCreateRequestFailsBeforeSending() {
        assertThrows(
                NullPointerException.class,
                () -> gateway.create(null));
        server.verify();
    }

    @Test
    void empty204ResponseIsRejected() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items/SKU-4"))
                .andRespond(withNoContent());

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> gateway.findBySku("SKU-4"));

        assertEquals(
                "partner returned empty item body",
                error.getMessage());
        server.verify();
    }

    @Test
    void malformedJsonIsDecodingFailure() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items/BROKEN"))
                .andRespond(withSuccess(
                        "{\"sku\":",
                        MediaType.APPLICATION_JSON));

        assertThrows(
                RestClientException.class,
                () -> gateway.findBySku("BROKEN"));
        server.verify();
    }

    @Test
    void unprocessablePostRetains422Status() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items"))
                .andRespond(withStatus(
                        HttpStatus.UNPROCESSABLE_ENTITY));

        HttpClientErrorException error = assertThrows(
                HttpClientErrorException.class,
                () -> gateway.create(
                    new CreateItemRequest(
                            "SKU-5", "Invalid", 0)));

        assertEquals(HttpStatus.UNPROCESSABLE_ENTITY,
                error.getStatusCode());
        server.verify();
    }

    @Test
    void textPlainResponseCannotMapJsonDto() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items/SKU-6"))
                .andRespond(withSuccess(
                        "not json",
                        MediaType.TEXT_PLAIN));

        assertThrows(
                RestClientException.class,
                () -> gateway.findBySku("SKU-6"));
        server.verify();
    }

    @Test
    void twoSequentialCallsReadDifferentBodies() {
        server.expect(requestTo(
                        "https://api.partner.test/v1/items/SKU-A"))
                .andRespond(withSuccess("""
                    {
                      "sku": "SKU-A",
                      "name": "Alpha",
                      "priceCents": 100
                    }
                    """, MediaType.APPLICATION_JSON));

        server.expect(requestTo(
                        "https://api.partner.test/v1/items/SKU-B"))
                .andRespond(withSuccess("""
                    {
                      "sku": "SKU-B",
                      "name": "Beta",
                      "priceCents": 200
                    }
                    """, MediaType.APPLICATION_JSON));

        assertEquals(
                new PartnerItem("SKU-A", "Alpha", 100),
                gateway.findBySku("SKU-A"));
        assertEquals(
                new PartnerItem("SKU-B", "Beta", 200),
                gateway.findBySku("SKU-B"));

        server.verify();
    }
}
```

**Có 12 phương thức `@Test`** trong class này. `@BeforeEach` không phải một test, nó chỉ reset mock expectations trước mỗi method.

### Test nào chứng minh configuration được import?

`clientConfigurationIsLoadedIntoSlice` assert properties bean và named RestClient bean tồn tại. Nhưng test `getUsesAbsoluteUriHeadersAndJson` và `postSerializesRequestAndReadsResponse` mạnh hơn: chúng xác nhận configuration **đã tác động tới HTTP request** qua base URL và hai headers.

Nếu một developer vô tình bỏ `@Import`, bean `partnerRestClient` có thể mất. Nếu bỏ `@EnableConfigurationProperties` trong config, `PartnerClientProperties` có thể mất. Nếu Gateway tự tạo một client qua `RestClient.create()`, mock server có thể không intercept.

## 11. Các nhóm assertion chính

### 11.1. URL và HTTP method

Spring RestClient tạo URL tuyệt đối từ `baseUrl("https://api.partner.test")` cộng path `/v1/items/SKU-1`. Với `RestClient.Builder` trong Spring Boot 3.3, `MockRestServiceServer` expectation phải dùng **full URI**, ví dụ:

```java
server.expect(requestTo(
        "https://api.partner.test/v1/items/SKU-1"))
      .andExpect(method(HttpMethod.GET));
```

Chỉ assert response DTO mà bỏ URL/method sẽ không bảo vệ lỗi gọi nhầm endpoint hoặc POST thay GET.

### 11.2. Headers

GET test assert `X-Partner-Key`, `X-Client-Tag` và `Accept: application/json`; POST test assert API key/tag và `Content-Type: application/json`. `Content-Type` chủ yếu áp dụng cho request có body; GET không cần set JSON content-type chỉ để “đẹp”.

### 11.3. JSON body

`content().json(expected, true)` so sánh cấu trúc JSON. Không cần whitespace hoặc property order giống hệt, nhưng strict mode giới hạn fields ngoài expected theo comparison semantics. Những fixture literal này bảo vệ API contract, không chỉ test serializer và deserializer tự round-trip với nhau.

### 11.4. Response mapping

Jackson đọc JSON string thành Java record `PartnerItem`. Test kiểm tra toàn bộ fields (`sku`, `name`, `priceCents`), không chỉ `assertNotNull`. Một test chỉ kiểm tra client không ném exception có thể bỏ qua việc map thiếu price.

### 11.5. Negative HTTP status

`RestClient.retrieve()` mặc định ném lỗi cho HTTP 4xx/5xx. Test kiểm tra 404 bằng `HttpClientErrorException.NotFound`, 503 bằng `HttpServerErrorException.ServiceUnavailable` và POST 422 bằng `HttpClientErrorException` với status chính xác. Nếu app có `onStatus(...)` custom, expected exception cần phản ánh domain mapping thật.

### 11.6. Empty và malformed body

`withNoContent()` trả 204, nên `body(PartnerItem.class)` có thể null; Gateway ném `IllegalStateException` với message rõ. Một response JSON hỏng gây `RestClientException`/converter failure. Chọn assertion type đủ cụ thể theo contract, tránh `assertThrows(RuntimeException.class)` vì một NullPointerException bất ngờ cũng có thể làm test pass giả.

### 11.7. Nhiều requests và server.verify()

Mỗi `expect` đăng ký một request cần xảy ra. Sau khi client gọi, `server.verify()` khẳng định mọi expected requests được đáp ứng. `server.reset()` trong `@BeforeEach` loại state từ method trước; test không phụ thuộc thứ tự JUnit.

Khi client gọi nhiều requests đồng thời, ordering semantics cần manager phù hợp. Bộ ví dụ gọi hai GET theo thứ tự đã khai báo, nên dùng default request expectation manager là hợp lý.

## 12. Legacy RestTemplateBuilder.rootUri: một khác biệt quan trọng

Tài liệu Spring Boot 3.3 cho biết khi dùng `RestTemplateBuilder.rootUri(String)`, mock server expectation có thể **bỏ root URI** và chỉ dùng relative path. Đây là hành vi dễ nhầm với `RestClient.Builder`.

### LegacyHealthClient.java

`src/main/java/com/example/outbound/LegacyHealthClient.java`:

```java
package com.example.outbound;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
public class LegacyHealthClient {

    private final RestTemplate template;

    public LegacyHealthClient(RestTemplateBuilder builder) {
        this.template = builder
                .rootUri("https://legacy.partner.test")
                .build();
    }

    public String ping() {
        return template.getForObject(
                "/health", String.class);
    }
}
```

### LegacyHealthClientTest.java

`src/test/java/com/example/outbound/LegacyHealthClientTest.java`:

```java
package com.example.outbound;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(LegacyHealthClient.class)
class LegacyHealthClientTest {

    @Autowired
    LegacyHealthClient client;

    @Autowired
    MockRestServiceServer server;

    @Test
    void rootUriIsOmittedFromRequestExpectation() {
        server.expect(requestTo("/health"))
                .andRespond(withSuccess(
                        "ok", MediaType.TEXT_PLAIN));

        assertEquals("ok", client.ping());
        server.verify();
    }
}
```

**Có 1 `@Test`** ở legacy class; tổng project là **13 phương thức `@Test`** (12 + 1).

### Bảng so sánh URI expectation

| Client | Cách thiết lập | MockRestServiceServer expectation trên Boot 3.3 |
| --- | --- | --- |
| `RestClient.Builder` | `baseUrl("https://api.partner.test")` | Full URL: `https://api.partner.test/v1/items/SKU-1` |
| `RestTemplateBuilder` | `rootUri("https://legacy.partner.test")` | Relative: `/health` |
| `RestTemplateBuilder` không `rootUri` | Gọi URI tuyệt đối | Full URL |
| HTTP client tự tạo request factory ngoài builder của Boot | Tùy implementation | Cần bind mock riêng hoặc real HTTP server |

Đừng tự động chuyển expectation từ RestTemplate sang RestClient mà không xem tài liệu theo version. `rootUri` cũng là API khác `baseUrl` của RestClient: cùng ý tưởng domain nền nhưng test binding path có behavior khác.

## 13. @ConfigurationProperties được đưa vào slice như thế nào?

Project dùng:

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PartnerClientProperties.class)
public class PartnerRestClientConfiguration {
    // @Bean partnerRestClient(...)
}
```

Test dùng:

```java
@RestClientTest(
    value = PartnerProductGateway.class,
    properties = {
        "partner.catalog.base-url=https://api.partner.test",
        "partner.catalog.api-key=test-key"
    })
@Import(PartnerRestClientConfiguration.class)
class PartnerProductGatewayTest {
}
```

Đây là ba trách nhiệm:

1. `properties` cung cấp **giá trị** từ Spring Environment.
2. `@EnableConfigurationProperties` đăng ký **bean typed** và bind từ Environment.
3. `@Import` khiến configuration tạo **RestClient bean thật** được đưa vào test slice.

Nếu bạn chỉ đặt test properties mà không enable/bind type, class phụ thuộc `PartnerClientProperties` có thể vẫn thiếu bean. Nếu enable type nhưng quên config tạo RestClient, Gateway cũng có thể thiếu dependency. Test failure ở startup là tín hiệu wiring chưa đủ, không phải lỗi DNS.

### Nếu dùng @ConfigurationPropertiesScan?

Một ứng dụng production có thể đặt `@ConfigurationPropertiesScan` trên main configuration để tìm các properties types. `@RestClientTest` chủ động giới hạn scan; lựa chọn ổn định là import config và enable properties cụ thể. Đừng nạp toàn bộ config của ứng dụng chỉ để có hai test property values.

## 14. @Import vs @TestConfiguration

**@Import production config** thích hợp khi muốn kiểm tra chính config được deploy: base URL binding, default headers, client builder và codecs.

**@TestConfiguration** phù hợp nếu cần test-only collaborator:

```java
@TestConfiguration(proxyBeanMethods = false)
class TestOnlyClientFlagsConfig {

    @Bean
    ClientFlags clientFlags() {
        return new ClientFlags(false);
    }
}
```

Đây là snippet kiến trúc không thuộc project runnable: `ClientFlags` là type giả định của một app khác, cần được định nghĩa trước. Nếu một service trong slice thực sự cần flags, có thể import test config hoặc mock collaborator. Nhưng đừng thay toàn bộ PartnerRestClientConfiguration bằng fake config rồi tuyên bố production headers đã được kiểm tra.

### Khi nào dùng @ImportAutoConfiguration?

Nếu cần mở thêm một Spring Boot auto-configuration class vốn không nằm trong slice, dùng `@ImportAutoConfiguration` theo hướng dẫn của Boot. Ordinary production `@Configuration` như `PartnerRestClientConfiguration` là trường hợp `@Import` thông thường. Không “import mọi auto config” vì nó làm context nặng và dễ tạo bean collisions.

## 15. Multi-client context cần server binding có chủ đích

Ví dụ chính chỉ tạo một bean RestClient và một builder được Boot cung cấp. Khi ứng dụng có nhiều outbound clients:

- Một `RestClient.Builder` có thể được clone/chỉnh khác nhau.
- `MockServerRestClientCustomizer` có thể giữ mock servers gắn với từng builder.
- Một `MockRestServiceServer` inject tự động có thể chỉ đại diện một builder.
- Một test class cho mỗi outbound adapter thường dễ kiểm soát hơn.
- Nếu nhiều adapters cần chạy trong cùng integration test, có thể lấy server theo builder qua customizer và set expectations độc lập, hoặc dùng WireMock cho host-specific routing.

Không giả định một injected mock server bắt **mọi HTTP client của JVM**; nó chỉ intercept những clients được build/bind đúng.

### RestClientCustomizer và cấu hình toàn cục

Spring Boot có `org.springframework.boot.web.client.RestClientCustomizer` để tùy biến Boot-managed builders. Ví dụ snippet:

```java
@Bean
RestClientCustomizer addApplicationHeader() {
    return builder ->
            builder.defaultHeader(
                    "X-App-Version", "1");
}
```

Đây là snippet ngoài project runnable, cần imports `Bean` và `RestClientCustomizer`. Nếu production có customizer thật, test cần import config cung cấp customizer và assert request. Nhưng đừng đưa API key của một đối tác vào **global customizer** vì các clients khác có thể vô tình gửi cùng credential.

**Đặc biệt:** một customizer đặt `ClientHttpRequestFactory` sau khi mock binder đã gắn có thể làm request vượt qua mock server. Nếu test bất ngờ gọi mạng, kiểm tra thứ tự builder/customizers và request factory thay vì tắt assertions.

## 16. Timeout, TLS và retry: giới hạn mock layer

`MockRestServiceServer` không mở TCP socket. Vì vậy nó không chứng minh:

- DNS lookup hoạt động.
- HTTPS certificate/truststore đúng.
- Proxy authentication hoặc connection pooling.
- Socket read/connect timeout.
- TCP reset, partial response hoặc redirect do network stack xử lý.
- Retry xảy ra với timing thật.

Nếu client phải kiểm tra transport timeout, dùng **real local HTTP server** trên random port (WireMock hoặc OkHttp MockWebServer), delay response có kiểm soát và bounded test timeout. Những thư viện đó không được thêm vào demo build.gradle vì bài tập trung vào `@RestClientTest`.

Một retry policy được định nghĩa rõ có thể test số lần gọi bằng mock request expectations, nhưng timing/backoff cần clock/scheduler test utilities hoặc integration environment phù hợp. Không thêm retry mù quáng cho POST tạo tài nguyên: timeout có thể xảy ra sau khi server đã xử lý request, cần idempotency key/contract.

### Default retrieve() không tự retry

Trong Gateway mẫu, `retrieve()` mặc định ném `HttpServerErrorException` khi response 503; nó **không tự retry**. Test `response503IsHttpServerError` bảo vệ đúng behavior này. Khi thêm retry, phải cập nhật tests theo behavior mới và kiểm tra số attempts, không chỉ assert cuối cùng trả 200.

## 17. JSON và content negotiation

Ba khái niệm khác nhau:

| Trường | Ai gửi | Ý nghĩa |
| --- | --- | --- |
| Request `Content-Type` | Client | Format của **request body** |
| Request `Accept` | Client | Format response mong đợi |
| Response `Content-Type` | Server/mock | Format body mà decoder dùng |

GET không có body trong ví dụ, nên chỉ đặt `Accept: application/json`. POST gửi record body, nên đặt `Content-Type: application/json` và `Accept: application/json`.

Test `textPlainResponseCannotMapJsonDto` trả `text/plain` thay vì JSON, minh họa converter mismatch. Test malformed JSON kiểm tra codec không lặng lẽ bỏ lỗi cú pháp. Khi ứng dụng cần custom Jackson `Module` hoặc `@JsonComponent`, hãy import config/converter phù hợp vào slice và bảo vệ exact JSON contract.

### Không suy từ JSON round-trip rằng API đúng

Nếu serialize request rồi deserialize lại cùng object, cả hai phía có thể mắc một lỗi cùng kiểu mà round-trip vẫn PASS. Dùng literal JSON fixture với field names/types đúng như partner contract, đồng thời assert request content-type, response type và lỗi invalid input.

### Decimal và timestamp

Với money, dùng integer minor units hoặc `BigDecimal` theo API contract, không dùng double nếu cần decimal precision. Với timestamp, quy định zone/offset/format như RFC 3339 và test deterministic values. Không dựa vào default timezone của CI.

## 18. HTTP error mapping và domain semantics

Trong adapter hiện tại, default `retrieve()` behavior:

| Status | Kết quả |
| --- | --- |
| 200 JSON hợp lệ | Java `PartnerItem` |
| 204 | Null body, rồi `IllegalStateException` do Gateway chủ động kiểm tra |
| 404 | `HttpClientErrorException.NotFound` |
| 422 | `HttpClientErrorException` subtype, status 422 |
| 503 | `HttpServerErrorException.ServiceUnavailable` |
| 200 JSON hỏng | `RestClientException` do decode |
| 200 text/plain cho DTO | `RestClientException` do converter |

Một production adapter có thể muốn `findBySku` trả `Optional.empty()` khi 404 thay vì exception, hoặc map 429 thành RetryableRemoteException. Điều đó cần `onStatus(...)` hoặc error handling riêng **và test tương ứng**. Không catch tất cả `RestClientException` rồi trả null: timeout, 401, 404 và malformed JSON là những vấn đề khác nhau.

**Đừng đưa exact full exception message vào assertion** nếu nó phụ thuộc vào thư viện/client implementation. Assert subtype, HTTP status và domain error code khi contract yêu cầu. Chỉ assert custom message do chính Gateway tạo (như empty body) khi đó là behavior bạn chủ động kiểm soát.

## 19. Bảo vệ URI construction

Không nối `"https://api.partner.test/v1/items/" + sku` một cách tùy tiện khi user input có whitespace, `/`, `?`, `#` hoặc Unicode. Dùng URI template, `UriBuilder` hoặc `UriComponentsBuilder`; test case path variables đặc biệt theo contract.

Snippet (chưa nằm trong client mẫu):

```java
client.get()
      .uri(builder -> builder
          .path("/v1/items")
          .queryParam("active", true)
          .queryParam("limit", 10)
          .build())
      .retrieve()
      .body(String.class);
```

Request URL expectation cần ghi đúng query params/encoding. Nếu cần dynamic `orderBy` hoặc hostname từ user, dùng allowlist; không cho client quyết định arbitrary URL từ request payload vì có thể mở SSRF risk trong ứng dụng thật.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `No qualifying bean for PartnerProductGateway` | Không chọn target bean | `@RestClientTest(PartnerProductGateway.class)` |
| `No bean named partnerRestClient` | Config bị slice loại | `@Import(PartnerRestClientConfiguration.class)` |
| `No bean of PartnerClientProperties` | Chưa enable typed binding | `@EnableConfigurationProperties` |
| Base URL null/không phải HTTPS | Test props thiếu/sai | Kiểm tra keys và record constructor |
| Mock server không thấy request | Client tạo ngoài Boot builder | Dùng managed `RestClient.Builder` hoặc explicit binding |
| Expect URI sai với RestClient | Dùng relative `/v1/items` | Dùng full URL |
| Expect URI sai với RestTemplate rootUri | Dùng full URL nhưng mock match path | Dùng `requestTo("/health")` |
| Header `X-Partner-Key` thiếu | Config không import hoặc client khác | Assert bean và request headers |
| POST JSON khác contract | Record/converter/mapper sai | `content().json(...)` |
| 404 được xử lý sai | Catch rộng hoặc custom status handler | Assert domain policy + status |
| 503 không retry | Không có retry policy | Test policy riêng nếu cần |
| 204 trả null | Body rỗng hợp lệ ở HTTP nhưng domain không cho | Kiểm tra explicit empty-body policy |
| Malformed JSON test fail khác expected | Codec khác hoặc body khác | Assert phù hợp `RestClientException` |
| Test chỉ PASS khi chạy riêng | Không reset expectations, shared state | `@BeforeEach server.reset()` |
| Nhiều clients dùng chung injected server | Mỗi builder có mock server khác | Tách test hoặc bind server đúng |
| Slice cố load DB/service ngoài | Import config quá rộng | Thu hẹp config/client dependencies |
| Tests PASS nhưng TLS production lỗi | Mock không đi mạng | Thêm real local network integration |
| Dùng import Spring Boot 4 trong Boot 3 | Package khác | Dùng Boot 3.3 API tương ứng |

### Quy trình debug

1. Xác nhận Java 17, Spring Boot 3.3.5 và dependencies.
2. Đọc root cause từ `ApplicationContext`, không chỉ thông báo outer wrapper.
3. Kiểm tra `@RestClientTest` có target class.
4. Kiểm tra config thật được `@Import` và properties type được enable.
5. Inspect test properties bean bằng assertion.
6. Xác nhận RestClient được build từ managed `RestClient.Builder`.
7. Thêm một mock expectation cho absolute GET URL và trả JSON nhỏ.
8. Assert method/header/DTO và gọi `server.verify()`.
9. Thêm negative response tests: 404, 503, malformed JSON.
10. Nếu client đã chuyển sang networking thật ngoài ý muốn, xem request factory/customizer.
11. Nếu lỗi chỉ xảy ra trên real HTTPS/TLS, viết integration test qua network.
12. Chạy toàn suite để phát hiện expectation leakage/context issues.

## 21. Chạy và đánh giá đúng số test

Theo code mẫu:

| Test class | Số phương thức `@Test` | Mục tiêu |
| --- | ---: | --- |
| `PartnerProductGatewayTest` | 12 | Config, RestClient GET/POST, headers, body, errors |
| `LegacyHealthClientTest` | 1 | RestTemplateBuilder.rootUri expectation |
| **Tổng** | **13** | HTTP client slice tests |

Khi project có Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.outbound.PartnerProductGatewayTest'
./gradlew test --tests 'com.example.outbound.LegacyHealthClientTest'
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Không có Wrapper nhưng máy đã cài Gradle phù hợp:

```bash
gradle test
```

Gradle/JUnit report thường nằm tại:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

**13 là số methods trong source**, không phải khẳng định 13 PASS đã được quan sát. Chưa có lần chạy Gradle thật trong bài soạn này. Nếu một test fail, xem request matcher/actual URI/header/body và root cause trước khi sửa expected values.

## 22. Khi nào mở rộng sang HTTP server thật?

Một bộ integration test bổ sung có thể chạy WireMock hoặc OkHttp MockWebServer tại `localhost:randomPort`, rồi truyền base URL động vào `PartnerClientProperties` bằng `@DynamicPropertySource`. Lúc đó client thực đi qua TCP/HTTP stack và có thể kiểm tra timeout, proxy, TLS (nếu mock server hỗ trợ), redirects và streaming.

Không gọi API đối tác thật trong test unit-ish mặc định, vì bên ngoài có thể rate limit, outage, trả dữ liệu thay đổi hoặc cần secret. Nếu cần provider contract verification, dùng môi trường/suite chuyên biệt và dữ liệu synthetic.

### Test configuration không được lấn át production wiring

Nếu test chỉ tạo một mock RestClient bean với response hardcoded, nó không thực thi `PartnerRestClientConfiguration` nên không biết production builder đã bị chỉnh sai. Điều tốt nhất của bài này là **import production config và mock chỉ server response**.

## 23. Quy tắc an toàn và bảo mật

- Không dùng production API key trong test source.
- Không log credentials hoặc full authorization headers trên CI.
- Dùng base URL giả `https://api.partner.test` cho mock-only test.
- Không cho arbitrary user URL được truyền trực tiếp vào RestClient để tránh SSRF.
- Không biến một lỗi TLS thành thành công bằng cách tắt certificate validation.
- Nếu test network real, chạy local server do test quản lý và bounded timeouts.
- Với retry POST, cần idempotency rules để không tạo duplicate resource.
- Tách HTTP client configuration khỏi database/message configs để test slice nhỏ và ít side effects.
- Với nhiều REST clients, đặt named beans hoặc qualifiers rõ.
- Bảo vệ JSON contract với fixture không chứa PII.
- Tài liệu test cần ghi rõ điều **chưa** kiểm tra: socket/TLS/production provider behavior.

## 24. Checklist QA trước khi merge

1. `@RestClientTest` đã chọn đúng client class?
2. Client under test thật, không bị Mockito mock chính nó?
3. Configuration client thật được `@Import`?
4. `@ConfigurationProperties` bean có được enable đúng?
5. Test properties chỉ dùng fake credentials và deterministic URL?
6. Client có dùng managed `RestClient.Builder` hoặc `RestTemplateBuilder`?
7. Named bean/`@Qualifier` có tránh inject nhầm client?
8. `MockRestServiceServer` có bind đúng builder?
9. GET/POST có assert URL, method, header và body?
10. `Accept` và `Content-Type` có được hiểu đúng chiều?
11. JSON response được kiểm tra đủ fields, không chỉ non-null?
12. Có test 404/422/503, malformed JSON, 204 nếu contract cần?
13. `server.verify()` có được gọi?
14. Expectations có được reset giữa test methods?
15. Với `RestClient.Builder` có dùng full URI expectation?
16. Với `RestTemplateBuilder.rootUri` có dùng relative URI khi phù hợp?
17. Không dùng global customizer để gửi secret của một partner tới mọi client?
18. Không nhầm mock server với TCP/TLS network integration test?
19. Test không vô tình gọi production endpoint hoặc internet?
20. Project dùng imports tương ứng Spring Boot 3.3?
21. CI/test report thật có xác nhận status không, thay vì suy từ số methods?
22. Nếu custom converter/status mapping thay đổi, test contract có được cập nhật đúng?

## 25. Bài tập thực hành

1. Chạy Gateway test, xác nhận không cần HTTP server `api.partner.test` thật.
2. Bỏ `@Import(PartnerRestClientConfiguration.class)` để thấy lỗi missing bean.
3. Bỏ `@EnableConfigurationProperties` và đọc root cause binding.
4. Đổi default header `X-Client-Tag` và kiểm tra request matcher phát hiện sai khác.
5. Đổi test base URL sang host giả khác, kiểm tra expected URI cần cập nhật khi contract đổi.
6. Thử `RestClient.create()` trong sandbox và quan sát mock server không được bind tự động.
7. Bỏ `accept(MediaType.APPLICATION_JSON)` ở GET và quan sát header assertion.
8. Bỏ `contentType(APPLICATION_JSON)` ở POST và xem serialization/content-type contract.
9. Đổi field `priceCents` thành `price` trong request record, để literal JSON matcher bắt regression.
10. Trả malformed JSON và phân biệt lỗi decoding với HTTP status error.
11. Trả 401/403/429, thiết kế mapping policy rồi test.
12. Thêm `onStatus(...)` cho 404 và test domain exception theo contract mới.
13. Thêm query parameters và assert URI encoding.
14. Chạy `LegacyHealthClientTest`, giải thích vì sao expected `/health` là relative.
15. Tạo client thứ hai, tìm cách bind đúng server cho mỗi builder.
16. Dùng WireMock/MockWebServer cho một integration test connection timeout riêng.
17. Nếu production có global RestClientCustomizer, import đúng config và test header/interceptor effect.
18. Chạy mỗi test method độc lập và toàn suite, xác nhận không phụ thuộc order.
19. Đọc Gradle report để đối chiếu số methods và failure reasons.
20. Kiểm tra secret fake không bị thay bằng token thật trong commit.

## 26. Tài liệu chính thức

- [Spring Boot 3.3 — Auto-configured REST Client Tests](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@RestClientTest`, builders, MockRestServiceServer, slice scanning, absolute/relative expectations.
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): `@ConfigurationProperties`, binding, property sources.
- [Spring Boot 3.3 — RestClientTest API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/client/RestClientTest.html): annotation attributes.
- [Spring Boot 3.3 — MockServerRestClientCustomizer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/client/MockServerRestClientCustomizer.html): mock binding với RestClient.Builder.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`/`RestTemplate` APIs.
- [Spring Framework — MockRestServiceServer](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): expectations, matchers, response creators và verification.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): `@Test`, `@BeforeEach` và test lifecycle.

## 27. Tổng kết

**`@RestClientTest`** là slice chuyên kiểm tra outbound HTTP client thật trong Spring Boot, với `MockRestServiceServer` làm giả phía server mà không dùng TCP network. Trong Boot 3.3, slice cấu hình `RestClient.Builder`, `RestTemplateBuilder` và JSON support, nhưng **không tự scan mọi ordinary config/`@ConfigurationProperties`**.

Để kiểm tra **cấu hình client được đưa vào slice**, import đúng `PartnerRestClientConfiguration` bằng `@Import`, đăng ký `PartnerClientProperties` bằng `@EnableConfigurationProperties` và tạo RestClient từ **Spring-managed builder**. Test các request cuối cùng: URL tuyệt đối, method, API key/header, JSON body, response DTO, status errors và null/malformed body. Với `RestClient.Builder` kỳ vọng full URL; với `RestTemplateBuilder.rootUri` có thể kỳ vọng relative path theo tài liệu Boot 3.3. Bổ sung real HTTP integration test khi cần chứng minh DNS/TLS/socket behavior — đừng nhầm test mock server đã kiểm tra mọi tầng network.
