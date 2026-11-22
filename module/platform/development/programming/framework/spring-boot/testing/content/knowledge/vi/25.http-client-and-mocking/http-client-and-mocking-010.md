# Khởi động stub ở port động, reset expectation và dọn sau test

## 1. Mục tiêu của bài

Trong module **Spring Boot - testing**, nhóm **HTTP client và giả lập**, kiểm thử một HTTP client không nên gọi thật tới API đối tác hoặc phụ thuộc một server cố định ở `localhost:8080`. Một HTTP stub server, ví dụ **WireMock**, cho phép mô phỏng response của API bên ngoài, kiểm tra URL, method, headers, body và error handling, đồng thời giữ test chạy độc lập với mạng đối tác.

Nhưng một stub server hoạt động tốt chỉ khi giải quyết đủ ba trách nhiệm:

1. **Khởi động ở port động:** tránh đụng port của developer/CI, lấy địa chỉ thật sau khi server start và truyền nó vào HTTP client đang được test.
2. **Reset expectation và request journal giữa các test:** mỗi test tự khai báo response/verification cần thiết; không thừa hưởng mappings, call count hoặc scenario state từ test trước.
3. **Dọn đúng vòng đời:** test methods kết thúc phải reset state; test class/context kết thúc phải stop server đúng lúc, tránh socket leak, stale URL trong Spring context cache hoặc background tasks gửi request muộn.

Ví dụ chính sử dụng **Java 17, Spring Boot 3.5.16, Spring `RestClient`, JUnit Jupiter và WireMock 3.13.2**. Toàn bộ HTTP giao tiếp qua loopback với một WireMockServer có `dynamicPort()`; không cần Docker, API key thật hoặc mạng Internet để thực hiện các ca test khi dependencies đã được tải.

Sau bài này, người học sẽ phân biệt chính xác:

- **WireMockServer** chạy HTTP thật trên một cổng cục bộ;
- **`@WireMockTest` / `WireMockExtension`** quản lý lifecycle và auto-reset theo JUnit;
- **`@DynamicPropertySource` / `DynamicPropertyRegistrar`** nối URL động vào Spring;
- **`resetAll()`, `resetRequests()`, `resetMappings()`, `resetScenarios()`** với các mức xóa state khác nhau;
- **`MockRestServiceServer`**: giả lập request trong Spring client, không mở HTTP listening port;
- **test isolation** khi một server/context được nhiều ca hoặc nhiều test class chia sẻ.

Không đặt mục tiêu “stub trả gì thì assert vậy” một cách hình thức; các test phải chứng minh **client thực sự phát request đúng** và xử lý cả response thành công, 404 hợp lệ và lỗi 503.

## 2. HTTP stub server khác mock method thế nào?

Giả sử ứng dụng cần gọi:

~~~http
GET /external/products/SKU-7 HTTP/1.1
Host: partner.example.invalid
X-Client: spring-demo
Accept: application/json
~~~

Có ba cấp độ kiểm thử:

| Cách test | Có TCP/HTTP thật? | Kiểm tra được gì? | Không chứng minh được gì? |
| --- | --- | --- | --- |
| Mockito mock một interface `PartnerGateway` | Không | Business caller có gọi đúng method/arguments không | HTTP encoding, headers, status, JSON transport |
| Spring `MockRestServiceServer` | Không mở network port | `RestClient`/`RestTemplate` request matchers, response decoding | TCP socket, TLS, network delay/fault như thật |
| WireMock/MockWebServer port động | **Có**, loopback HTTP | Request path, headers, method, JSON, status, một số transport behavior | Contract production backend thật, authentication/network topology thực tế |

**WireMock** là test double của upstream API, không phải bản sao đầy đủ của hệ thống đối tác. Các mapping phải có chủ đích, các ca lỗi quan trọng phải được kiểm tra riêng và các assumption về upstream contract nên được bổ sung contract tests hoặc staging integration tests khi cần.

Trong Spring Boot 3.5, `@RestClientTest` hỗ trợ `MockRestServiceServer` cho slice client. Khi muốn kiểm tra client có hoạt động với HTTP server thật trên port động (đặc biệt headers, fault injection, connection/timeout), **WireMock hoặc OkHttp MockWebServer** là lựa chọn phù hợp hơn.

## 3. Vì sao phải dùng port động?

Một ví dụ dễ lỗi:

~~~java
// Phản ví dụ: cố định port 8080 trên máy CI.
WireMockServer stub =
        new WireMockServer(wireMockConfig().port(8080));
stub.start();
~~~

Port 8080 có thể đã bị app khác sử dụng. Khi chạy test song song, hai test process có thể tranh nhau binding, làm một bên báo `Address already in use`. Không chữa bằng cách chọn port 8081 hay 9999 rồi hy vọng “chưa ai dùng”.

WireMock cho phép hệ điều hành chọn một port còn trống:

~~~java
WireMockServer stub =
        new WireMockServer(wireMockConfig().dynamicPort());

stub.start();
try {
    String baseUrl = stub.baseUrl();
    int port = stub.port();

    // baseUrl dạng http://localhost:<port động thực tế>
    // Truyền vào HTTP client đang được test.
} finally {
    stub.stop();
}
~~~

Đây là đoạn Java minh họa, cần imports:

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
~~~

Chỉ gọi `port()`/`baseUrl()` **sau `start()`** để lấy cổng đã được gán thực. Không tự giữ một port ngẫu nhiên bằng `new ServerSocket(0)` rồi đóng socket trước khi WireMock bind: khoảng hở giữa hai thao tác tạo race giành port (*TOCTOU*).

### Dynamic port không có nghĩa server chạy trên mạng công cộng

Stub được dùng cục bộ trong test; chỉ cấu hình bind/host phù hợp môi trường, không mở test API ra Internet. WireMock admin API có thể thêm/xóa mappings, vì vậy không expose một WireMock admin endpoint không bảo vệ ra mạng không tin cậy.

### Port động cần đi vào application config đúng thời điểm

Nếu HTTP client được tạo khi Spring context bắt đầu, **đừng tạo client với URL `localhost:8080` rồi sau đó chỉ thay một biến static**. RestClient có thể đã lưu base URL cũ. URL thật phải có mặt **trước khi bean `PartnerCatalogClient` được xây dựng**. Với Spring TestContext, cách chính là `@DynamicPropertySource` hoặc `DynamicPropertyRegistrar`.

## 4. Ba vòng đời phải xếp cho khớp

~~~text
JUnit test class load
     |
     +-- Start WireMockServer (port 0 -> port ngẫu nhiên)
     |
Spring TestContext chuẩn bị ApplicationContext
     |
     +-- @DynamicPropertySource công bố URL thật
     +-- RestClient.Builder tạo client trỏ đúng URL
     |
@BeforeEach -> reset mappings + request journal
     |
@Test -> đăng ký stub -> gọi client -> assert/verify
     |
@AfterEach -> reset state (dù assertion fail bình thường)
     |
... các test methods khác ...
     |
@AfterAll -> stop WireMockServer
     |
Spring TestContext -> loại bỏ cached context khi được đánh dấu dirty
~~~

**Lưu ý về Spring TestContext cache:** Spring có thể giữ một `ApplicationContext` sau khi JUnit kết thúc một test class. Nếu bean `RestClient` của cached context vẫn trỏ tới port của WireMock đã stop, class tiếp theo dùng lại context sẽ bị `Connection refused`. Trong **mẫu manual static server** bên dưới, test dùng `@DirtiesContext(classMode = AFTER_CLASS)` để tránh reuse client đã cấu hình với một server JUnit/test-class-scoped đã dừng. Đây là lựa chọn correctness cho ví dụ nhỏ; test suite lớn muốn cache tốt hơn có thể quản lý **server bean cùng Spring context**, xem phần 14.

`@DirtiesContext` có chi phí dựng lại Spring context. Không gắn nó vô tội vạ vào mọi test nếu có thể thiết kế lifecycle bền hơn. Mục tiêu là URL và backend sống **ít nhất lâu bằng bean/client dùng chúng**.

## 5. Bảng so sánh các cách quản lý server

| Kỹ thuật | Start/stop | Reset giữa methods | Gắn với Spring context? | Rủi ro |
| --- | --- | --- | --- | --- |
| `@WireMockTest` | WireMock JUnit extension, class-scoped mặc định | **Tự reset trước mỗi test** | Không | Cache Spring có thể sống lâu hơn extension |
| Static `@RegisterExtension WireMockExtension` | JUnit extension, per class | **Tự reset**, trừ khi tắt | Không | Cache/parallel/state vẫn phải quan tâm |
| Instance `@RegisterExtension` | JUnit extension, per method | Server mới từng method | Không | Tốn startup, URI phải được đưa vào client mới |
| Manual `WireMockServer` + `@BeforeAll/@AfterAll` | Code của test | **Tự gọi reset** | Không | Quên stop/reset, URL context cache cũ |
| Spring-managed `@Bean(initMethod/ destroyMethod)` | Spring ApplicationContext | **Tự reset theo test** | **Có** | Cần dynamic property registrar đúng thứ tự |
| Docker WireMock/Testcontainers | JUnit/Spring hoặc mã riêng | Không tự reset theo cách tổng quát | Tùy setup | Docker/port mapping và resource lifecycle |

Không dùng `@WireMockTest` đồng thời với manual `WireMockServer.start()` cho **cùng một server instance**. Hãy chọn đúng một chủ thể quản lý start/stop.

## 6. Ví dụ chạy được: Spring Boot RestClient + WireMock 3

Dự án có cấu trúc:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/stubhttp/
  StubHttpApplication.java
  RemoteProduct.java
  PartnerCatalogClient.java
src/main/resources/
  application.properties
src/test/java/com/example/stubhttp/
  PartnerCatalogClientIntegrationTest.java
  PartnerCatalogClientExtensionTest.java
~~~

Ví dụ **không gọi thật tới đối tác**. Production chỉ được nối đến URL thật khi deploy qua environment; `example.invalid` trong properties là một domain dành riêng cho minh họa, không phải endpoint có thể dùng.

### settings.gradle

~~~groovy
rootProject.name = 'spring-http-stub-tests'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.wiremock:wiremock-standalone:3.13.2'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**Vì sao `wiremock-standalone`?** WireMock 3.x có bản JAR đầy đủ/shaded nhằm giảm xung đột dependencies (nhất là HTTP server/Jetty libs) khi test cùng Spring Boot; nó dùng được như test dependency, không cần chạy như process độc lập. WireMock 3.13.2 là bản 3.x đã phát hành được ghi rõ trong tài liệu chính thức. Không trộn import/API của WireMock 4.x beta với ví dụ 3.x nếu chưa migrate.

`spring-boot-starter-web` cung cấp Spring MVC/Jackson và auto-config `RestClient.Builder` trong Boot 3.5; `spring-boot-starter-test` mang JUnit Jupiter và AssertJ. Không cần Docker và không cần một server ứng dụng nghe port trong bài này vì ứng dụng **chỉ gọi HTTP ra ngoài**, test `@SpringBootTest(webEnvironment = NONE)`.

### src/main/resources/application.properties

~~~properties
partner.catalog.base-url=${PARTNER_CATALOG_BASE_URL:https://partner.example.invalid}
partner.catalog.client-name=spring-demo
~~~

Property `PARTNER_CATALOG_BASE_URL` là giá trị cấu hình môi trường; trong test, `@DynamicPropertySource` **ghi đè** `partner.catalog.base-url` bằng URL thật của stub. `partner.example.invalid` không nên nhận request khi test được cấu hình đúng; nếu test vô tình gọi tới URL đó, phải xem là lỗi wiring.

## 7. Class ứng dụng và DTO

**src/main/java/com/example/stubhttp/StubHttpApplication.java**

~~~java
package com.example.stubhttp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StubHttpApplication {

    public static void main(String[] args) {
        SpringApplication.run(StubHttpApplication.class, args);
    }
}
~~~

**src/main/java/com/example/stubhttp/RemoteProduct.java**

~~~java
package com.example.stubhttp;

public record RemoteProduct(
        String sku,
        String title,
        int quantity
) {
}
~~~

Spring Boot/Jackson có thể deserialize một JSON object tương ứng với các component của Java 17 record. Test sẽ kiểm tra cả giá trị field thực sau khi đi qua HTTP transport, thay vì trả một object đã stub trực tiếp từ Mockito.

## 8. Client thực dùng RestClient và phân biệt 404 với 503

**src/main/java/com/example/stubhttp/PartnerCatalogClient.java**

~~~java
package com.example.stubhttp;

import java.util.Optional;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

@Service
public class PartnerCatalogClient {
    private final RestClient http;

    public PartnerCatalogClient(
            RestClient.Builder builder,
            @Value("${partner.catalog.base-url}") String baseUrl,
            @Value("${partner.catalog.client-name}") String clientName
    ) {
        this.http = builder
                .baseUrl(baseUrl)
                .defaultHeader("X-Client", clientName)
                .defaultHeader(
                        HttpHeaders.ACCEPT, "application/json"
                )
                .build();
    }

    public Optional<RemoteProduct> find(String sku) {
        try {
            RemoteProduct product = http.get()
                    .uri("/external/products/{sku}", sku)
                    .retrieve()
                    .body(RemoteProduct.class);

            return Optional.ofNullable(product);
        } catch (HttpClientErrorException.NotFound e) {
            // 404 là business case: sản phẩm không tồn tại.
            return Optional.empty();
        }
    }
}
~~~

Các quyết định:

- `RestClient.Builder` được Spring Boot cấu hình; constructor nhận base URL qua configuration, không hard-code host/port.
- `.uri("/external/products/{sku}", sku)` thay path variable; với identifier phức tạp, chú ý URI encoding.
- Header `X-Client` được gửi qua actual client; stub sẽ match/verify.
- `.retrieve()` mặc định ném exception cho 4xx/5xx; code chỉ chuyển **404** thành `Optional.empty()`.
- **503** vẫn propagate, không bị nuốt như 404; test xác nhận.
- Không tạo `new RestClient` mỗi request và không dùng static `WireMock.configureFor` trong business code.

HTTP response `200` với JSON đúng phải decode thành `RemoteProduct`. Response `404` có thể là một nhánh nghiệp vụ hợp lệ; response `503` là lỗi hạ tầng cần được caller xử lý theo retry/circuit-breaker contract khác.

## 9. Integration test chính: server port động, URL động, cleanup rõ ràng

**src/test/java/com/example/stubhttp/PartnerCatalogClientIntegrationTest.java**

~~~java
package com.example.stubhttp;

import com.github.tomakehurst.wiremock.WireMockServer;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.client.HttpServerErrorException;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS
)
class PartnerCatalogClientIntegrationTest {

    private static final WireMockServer STUB =
            new WireMockServer(wireMockConfig().dynamicPort());

    // Start ngay khi class được khởi tạo để property supplier
    // luôn có endpoint đã bind trước khi Spring tạo client.
    static {
        STUB.start();
    }

    @DynamicPropertySource
    static void upstreamProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "partner.catalog.base-url",
                STUB::baseUrl
        );
    }

    @Autowired
    PartnerCatalogClient client;

    @Value("${partner.catalog.base-url}")
    String injectedBaseUrl;

    @BeforeEach
    void resetBeforeMethod() {
        // Mỗi method không kế thừa stub mappings hay requests.
        STUB.resetAll();
    }

    @AfterEach
    void clearAfterMethod() {
        // @AfterEach chạy cả khi @Test assertion ném lỗi bình thường.
        STUB.resetAll();
    }

    @AfterAll
    static void stopServer() {
        STUB.stop();
    }

    @Test
    void dynamicPortIsWiredIntoSpringClient() {
        assertThat(STUB.isRunning()).isTrue();
        assertThat(STUB.port()).isPositive();
        assertThat(injectedBaseUrl).isEqualTo(STUB.baseUrl());
    }

    @Test
    void matchingRequestReturnsRealJsonFromHttpStub() {
        STUB.stubFor(
                get(urlEqualTo("/external/products/SKU-7"))
                        .withHeader(
                                "X-Client", equalTo("spring-demo")
                        )
                        .willReturn(
                                aResponse()
                                        .withStatus(200)
                                        .withHeader(
                                                "Content-Type",
                                                "application/json"
                                        )
                                        .withBody(
                                                """
                                                {
                                                  "sku": "SKU-7",
                                                  "title": "Notebook",
                                                  "quantity": 4
                                                }
                                                """
                                        )
                        )
        );

        RemoteProduct product =
                client.find("SKU-7").orElseThrow();

        assertThat(product.sku()).isEqualTo("SKU-7");
        assertThat(product.title()).isEqualTo("Notebook");
        assertThat(product.quantity()).isEqualTo(4);

        STUB.verify(
                1,
                getRequestedFor(
                        urlEqualTo("/external/products/SKU-7")
                ).withHeader("X-Client", equalTo("spring-demo"))
        );
    }

    @Test
    void explicit404ResponseBecomesEmptyOptional() {
        STUB.stubFor(
                get(urlEqualTo("/external/products/MISSING"))
                        .willReturn(
                                aResponse().withStatus(404)
                        )
        );

        assertThat(client.find("MISSING")).isEmpty();

        STUB.verify(
                1,
                getRequestedFor(
                        urlEqualTo("/external/products/MISSING")
                )
        );
    }

    @Test
    void unavailablePartner503MustNotBeSilentlyConvertedTo404() {
        STUB.stubFor(
                get(urlEqualTo("/external/products/RETRY"))
                        .willReturn(
                                aResponse()
                                        .withStatus(503)
                                        .withBody("upstream unavailable")
                        )
        );

        assertThatThrownBy(
                () -> client.find("RETRY")
        ).isInstanceOf(
                HttpServerErrorException.ServiceUnavailable.class
        );

        STUB.verify(
                1,
                getRequestedFor(
                        urlEqualTo("/external/products/RETRY")
                )
        );
    }

    @Test
    void resetAllRemovesBothOldMappingAndRequestHistory() {
        STUB.stubFor(
                get(urlEqualTo("/external/products/OLD"))
                        .willReturn(
                                aResponse()
                                        .withStatus(200)
                                        .withHeader(
                                                "Content-Type",
                                                "application/json"
                                        )
                                        .withBody(
                                                """
                                                {
                                                  "sku": "OLD",
                                                  "title": "Old title",
                                                  "quantity": 1
                                                }
                                                """
                                        )
                        )
        );

        assertThat(client.find("OLD")).isPresent();

        STUB.verify(
                1,
                getRequestedFor(
                        urlEqualTo("/external/products/OLD")
                )
        );

        // Xóa stub 200 và request history vừa ghi.
        STUB.resetAll();

        // Không còn mapping -> WireMockServer trả 404 mặc định.
        // Client đã định nghĩa 404 thành Optional.empty().
        assertThat(client.find("OLD")).isEmpty();

        // Sau reset chỉ có request lần THỨ HAI trong journal.
        STUB.verify(
                1,
                getRequestedFor(
                        urlEqualTo("/external/products/OLD")
                )
        );
    }
}
~~~

### Năm ca test có phạm vi cụ thể

| Test method | Phần được xác nhận | Expected |
| --- | --- | --- |
| `dynamicPortIsWiredIntoSpringClient` | Server start + dynamic property | Port dương, URL trong Spring bằng URL của WireMock |
| `matchingRequestReturnsRealJsonFromHttpStub` | Header/path, response body Jackson mapping | SKU-7, Notebook, quantity=4, đúng 1 HTTP GET |
| `explicit404ResponseBecomesEmptyOptional` | 404 là nhánh business | `Optional.empty()`, đúng 1 GET |
| `unavailablePartner503MustNotBeSilentlyConvertedTo404` | 503 không bị nuốt | Exception `ServiceUnavailable`, đúng 1 GET |
| `resetAllRemovesBothOldMappingAndRequestHistory` | Xóa mapping và request journal | Lần đầu 200; sau reset 404; journal mới đếm 1 |

**Không có test order.** Trước mỗi method gọi `resetAll()`, cuối method cũng `resetAll()`; các test không phải biết method nào chạy trước. `@AfterAll` stop server sau khi mọi method đã hoàn tất. `@DirtiesContext` ngăn Spring dùng lại client/cache gắn với địa chỉ một server đã bị stop trong class này.

**Chưa có test nào chạy trên Docker**, vì đây là WireMock Java server chạy trong JVM test. Kiểm tra actual HTTP là thật qua loopback, nhưng không chứng minh DNS/TLS/latency production thật.

### Một bẫy quan trọng trong test reset

Sau `resetAll()`, WireMockServer không còn stub của `/external/products/OLD`, nên nó trả **default HTTP 404**. Trong demo, client map mọi 404 thành `Optional.empty()`. Vì vậy nếu chỉ assert “empty” thì chưa đủ để chứng minh mapping bị xóa; ta đã có **test đầu tiên nhận 200**, sau đó reset và **verify request journal chỉ còn 1 request mới**. Nếu app có phân biệt body/error codes của 404, test nên đăng ký và assert contract của 404 tường minh. Tránh vô tình xem một request **không match stub** là business 404 mà vẫn PASS.

### Vì sao không dùng @BeforeAll.start()?

Ta có thể dùng `@BeforeAll` để start server, nhưng phải kiểm tra lifecycle ordering với Spring test extension, lúc nào `@DynamicPropertySource` supplier bị resolve và khi nào client bean được xây. Mẫu sử dụng **static initialization** để bảo đảm WireMock đã bind port trước khi bất kỳ Spring bean nào truy cập supplier.

Đây là một lựa chọn đơn giản cho demo, không phải giải pháp tối ưu cho mọi suite. Static initializer có rủi ro nếu class initialization fail đột ngột trước JUnit lifecycle; giải pháp quản lý bằng Spring bean/context được trình bày ở phần 14 phù hợp hơn khi có nhiều test classes tái sử dụng context.

## 10. Reset expectation: chính xác xóa những gì?

WireMockServer có nhiều loại state:

1. **Stub mappings/expectations:** request matcher và response definition (có thể gồm priority/delay).
2. **Request journal:** các HTTP requests đã nhận và matching status, dùng cho `verify(...)`.
3. **Scenario states:** state machine cho response có thứ tự như “lần 1: pending, lần 2: completed”.
4. **Global settings** hoặc file-backed default mappings, khi dùng cấu hình tương ứng.

| API trên `WireMockServer` | Tác động | Khi nên dùng |
| --- | --- | --- |
| `resetAll()` | Reset mappings và request journal, trở về trạng thái sạch; state liên quan scenarios được reset theo reset semantics | **Giữa hai test độc lập**, như mẫu chính |
| `resetRequests()` | Chỉ xóa request journal, **giữ mappings** | Nhiều phase trong cùng test dùng chung contract stubs |
| `resetMappings()` | Reset/delete stub mappings, không dùng để chứng minh request journal đã sạch | Khi chỉ muốn thay bộ stubs |
| `resetScenarios()` | Reset trạng thái của các scenarios đã cấu hình | Khi muốn chạy lại state machine với mappings giữ nguyên |
| `resetToDefaultMappings()` | Khôi phục mappings mặc định được nạp từ file khi có | Cần giữ file-based fixtures |
| `stop()` | Dừng server/listening socket | **Cuối lifecycle**, không thay cho reset giữa methods |

Tên API có thể khác chút giữa instance server và static client DSL: với instance `WireMockServer`, ví dụ có `resetRequests()`; với static DSL của `WireMock`, tài liệu có `resetAllRequests()`. Đừng copy tên method từ một kiểu object sang kiểu khác mà không kiểm API version.

### Reset không tự verify mọi expected request đã xảy ra

WireMock mappings mô tả **nếu request phù hợp thì trả response gì**, không tự kiểm tra rằng code *phải* gọi chúng. Một test đăng ký stub nhưng không gọi client vẫn có thể PASS nếu không có assertion/verification. Hãy dùng:

~~~java
STUB.verify(
        1,
        getRequestedFor(urlEqualTo("/external/products/SKU-7"))
);
~~~

Đây là snippet trong test class chính có `STUB` và imports. Nếu verification thất bại, WireMock ném exception phù hợp để test FAIL.

### Stub mapping khác Mockito verify

Mockito `verify(gateway).find("SKU-7")` chỉ chứng minh lời gọi method vào mock. WireMock `verify(1, getRequestedFor(...))` chứng minh client đã phát **HTTP GET thật tới stub server**. Nhưng cả hai vẫn là test double: không nên gắn nhãn “đã kiểm tra hợp đồng live upstream”.

## 11. @AfterEach reset hay @BeforeEach reset?

| Vị trí | Ưu điểm | Điều cần cân nhắc |
| --- | --- | --- |
| `@BeforeEach` gọi `resetAll()` | Mỗi test bắt đầu từ known clean state | Không tự dọn sau test nếu runner bị chấm dứt ngay trước test tiếp |
| `@AfterEach` gọi `resetAll()` | Dọn sau method kể cả khi assertion ném lỗi bình thường | Nếu trạng thái bẩn có trước method đầu tiên, chưa giải quyết |
| Cả hai | Ranh giới test rõ ràng, chống state sót từ method trước | Hơi thừa nhưng dễ hiểu cho bài học |
| JUnit WireMock extension mặc định | Auto-reset trước method, giảm boilerplate | Phải biết lifecycle extension và Spring context có khớp không |

Trong ví dụ, dùng cả `@BeforeEach` và `@AfterEach` là có chủ đích để làm rõ **setup sạch + teardown sạch**. Trong code production test suite lớn, bạn có thể chọn **một** cơ chế có chủ sở hữu rõ thay vì gọi reset khắp nơi; không cần tự reset thêm nếu extension đã auto-reset như thiết kế và mọi test bảo đảm isolation.

JUnit `@AfterEach` không phải cleanup process-level guaranteed tuyệt đối: JVM bị kill, SIGKILL hoặc machine crash thì method không chạy. Với test có external Docker process, shared files hay data production-like, cần thêm resource owner/teardown ngoài JVM. Với WireMock Java trong cùng JVM, khi process kết thúc thông thường, socket được hệ điều hành giải phóng, nhưng app vẫn nên stop đúng lifecycle.

## 12. WireMock JUnit 5: extension quản lý start/stop và auto-reset

Nếu không cần Spring `@DynamicPropertySource` và muốn test **client như một Java object** với base URL được truyền vào constructor, WireMock JUnit Jupiter extension là lựa chọn ít boilerplate.

**src/test/java/com/example/stubhttp/PartnerCatalogClientExtensionTest.java**

~~~java
package com.example.stubhttp;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.HttpServerErrorException;

import com.github.tomakehurst.wiremock.junit5.WireMockExtension;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PartnerCatalogClientExtensionTest {

    @RegisterExtension
    static WireMockExtension STUB = WireMockExtension.newInstance()
            .options(wireMockConfig().dynamicPort())
            .build();

    private PartnerCatalogClient newClient() {
        return new PartnerCatalogClient(
                RestClient.builder(),
                STUB.baseUrl(),
                "spring-demo"
        );
    }

    @Test
    void extensionAllocatesPortAndResetsAutomatically() {
        assertThat(STUB.port()).isPositive();

        STUB.stubFor(
                get(urlEqualTo("/external/products/BOOK"))
                        .willReturn(
                                aResponse()
                                        .withStatus(200)
                                        .withHeader(
                                                "Content-Type",
                                                "application/json"
                                        )
                                        .withBody(
                                                """
                                                {
                                                  "sku": "BOOK",
                                                  "title": "Guide",
                                                  "quantity": 2
                                                }
                                                """
                                        )
                        )
        );

        assertThat(newClient().find("BOOK").orElseThrow()
                .title()).isEqualTo("Guide");

        STUB.verify(
                1,
                getRequestedFor(
                        urlEqualTo("/external/products/BOOK")
                )
        );
    }

    @Test
    void secondMethodDeclaresItsOwn503Mapping() {
        STUB.stubFor(
                get(urlEqualTo("/external/products/FAIL"))
                        .willReturn(
                                aResponse().withStatus(503)
                        )
        );

        assertThatThrownBy(
                () -> newClient().find("FAIL")
        ).isInstanceOf(
                HttpServerErrorException.ServiceUnavailable.class
        );

        STUB.verify(
                1,
                getRequestedFor(
                        urlEqualTo("/external/products/FAIL")
                )
        );
    }
}
~~~

Đây là một **test class runnable thứ hai** (2 methods) thuộc cùng project. Nó không cần Spring ApplicationContext; `RestClient.builder()` chạy trực tiếp, còn `PartnerCatalogClient` dùng constructor thông thường.

Theo tài liệu WireMock 3.13.x:

- Static `@RegisterExtension`: start trước methods, stop sau test class.
- Extension **tự reset stubs và requests trước mỗi test method**.
- Nếu field không phải static: lifecycle per method, mỗi method có server mới.
- `.resetOnEachTest(false)` (từ 3.13.0) cho phép tắt auto-reset; chỉ nên dùng khi thật sự muốn state liên tục giữa methods và đã biết rủi ro.
- Extension mặc định có **fail-on-unmatched requests**; test nhận 404 **có chủ đích** cần đăng ký stub cho 404. Có thể cấu hình `.failOnUnmatchedRequests(false)` khi cần, nhưng không làm mặc định chỉ để che lỗi mapping.

Trong test extension ở đây **không có request unmatched**, nên giữ cấu hình mặc định làm test chặt chẽ hơn.

### Annotation ngắn gọn @WireMockTest

~~~java
@WireMockTest
class SimpleWireMockTest {

    @Test
    void demo(WireMockRuntimeInfo info) {
        int port = info.getHttpPort();
        // port là giá trị động; info còn có WireMock DSL.
    }
}
~~~

Đây là **skeleton**, cần imports `com.github.tomakehurst.wiremock.junit5.WireMockTest`, `WireMockRuntimeInfo`, JUnit và assertion mới thành test độc lập. `@WireMockTest` mặc định tạo một WireMock HTTP server **port ngẫu nhiên**, auto-reset trước mỗi method. Không cần dùng port cố định nếu không có lý do đặc biệt.

**Lưu ý:** `@RegisterExtension`/`@WireMockTest` là lifecycle owner. Không thêm `@AfterAll STUB.stop()` khi extension đã chịu trách nhiệm stop, trừ khi đang kiểm soát một server khác. Dừng cùng một resource hai lần có thể che lỗi ownership.

## 13. JUnit extension + Spring @SpringBootTest: lỗi context cache cần tránh

Một số hướng dẫn ghép:

~~~java
@SpringBootTest
class CachedContextWithClassScopedServerTest {
    @RegisterExtension
    static WireMockExtension STUB = WireMockExtension.newInstance()
            .options(wireMockConfig().dynamicPort())
            .build();

    @DynamicPropertySource
    static void urls(DynamicPropertyRegistry registry) {
        registry.add("partner.catalog.base-url", STUB::baseUrl);
    }
}
~~~

**Đây là skeleton để thảo luận rủi ro**, không phải sample runnable. Nó có thể hoạt động khi lifecycle ordering phù hợp và context được tạo sau server startup, nhưng hãy kiểm chứng điều đó với test setup thực tế.

Nguy cơ ở đây: static WireMock extension stop server **khi class test kết thúc**; Spring cache có thể giữ `PartnerCatalogClient` đã build với URL cũ lâu hơn. Khi class khác reuse cached context, client tiếp tục trỏ port đã đóng.

Một số giải pháp theo nhu cầu:

- Đánh dấu context không reuse sau class: `@DirtiesContext(classMode=AFTER_CLASS)`; đơn giản nhưng tốn startup.
- Cấu hình stub **Spring-managed bean** để server sống theo lifecycle context; hữu ích khi muốn context cache qua nhiều classes.
- Cho test tự tạo HTTP client sau khi extension đã start, **không** dùng Spring context như class extension runnable ở phần 12.
- Nếu cần nhiều classes với nhiều base URLs, bảo đảm context cache keys khác nhau hoặc dùng config riêng; đừng giả định `@DynamicPropertySource` phân biệt mọi giá trị dynamic runtime của cùng method.

**Không** khai báo `@DynamicPropertySource` với một method không static hoặc gọi `STUB.port()` trước khi server start. Spring registry nhận `Supplier`, chỉ resolve khi property được truy cập; thời điểm resolve cần có server đang chạy.

## 14. Một cách khác tốt cho nhiều test classes: Spring-managed stub

Spring Framework 6.2 có interface **`DynamicPropertyRegistrar`**; Spring Boot 3.5 dùng Spring Framework 6.2. Bạn có thể định nghĩa WireMockServer là Spring bean và đăng ký URL động từ bean đó. Khi ấy **server và RestClient cùng thuộc một Spring ApplicationContext**.

Minh họa test config (dùng thay thế, **không** dùng đồng thời với static server/extension ở các mẫu trước):

~~~java
package com.example.stubhttp;

import com.github.tomakehurst.wiremock.WireMockServer;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistrar;

import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;

@TestConfiguration(proxyBeanMethods = false)
class ManagedStubConfig {

    @Bean(initMethod = "start", destroyMethod = "stop")
    WireMockServer managedStub() {
        return new WireMockServer(wireMockConfig().dynamicPort());
    }

    @Bean
    DynamicPropertyRegistrar upstreamUrl(WireMockServer managedStub) {
        return registry -> registry.add(
                "partner.catalog.base-url",
                managedStub::baseUrl
        );
    }
}
~~~

Đây là **một tệp Java compile được khi có đúng dependencies**, nhưng chưa phải cả integration test độc lập. Test class dùng:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(ManagedStubConfig.class)
class CatalogClientWithManagedStubTest {

    @Autowired WireMockServer stub;
    @Autowired PartnerCatalogClient client;

    @BeforeEach void reset() {
        stub.resetAll();
    }

    @AfterEach void cleanup() {
        stub.resetAll();
    }

    // @Test: khai báo stub, gọi client, verify request.
}
~~~

Đoạn class trên là **skeleton**, cần imports/tests để chạy. `DynamicPropertyRegistrar` được Spring TestContext phát hiện và khởi tạo sớm trước giai đoạn pre-instantiate singleton bình thường; việc nó inject `managedStub` khiến bean stub được tạo và `initMethod="start"` chạy trước lúc supplier base URL được sử dụng để xây client.

Khi context được cache và dùng lại trong các classes có **cùng cache key**, server vẫn sống theo context, thay vì dừng sau test class. Khi context đóng/evict, `destroyMethod="stop"` dừng server. Tuy nhiên, **mỗi test vẫn cần reset mappings và request journal**; context cache không reset state của WireMock.

**Quan trọng:** không có gì đảm bảo mọi test class tạo đúng một context; `@ActiveProfiles`, `@TestPropertySource`, `@MockitoBean`, `@Import` và các context customizers khác có thể tách cache keys. Chọn shared test config nhất quán nếu mục tiêu thật sự là reuse.

## 15. ResetAll khác resetRequests: ví dụ thực tế

Một test có hai phase liên tiếp:

~~~java
// Đoạn trong một @Test có WireMockServer STUB đang chạy.
STUB.stubFor(
        get(urlEqualTo("/heartbeat"))
                .willReturn(aResponse().withStatus(200))
);

// Phase A: đã gửi 3 requests.
STUB.resetRequests();

// Phase B: mappings /heartbeat vẫn còn;
// request verification chỉ tính những request sau resetRequests.
~~~

Dùng `resetRequests()` khi muốn giữ stub mappings trong **cùng một kịch bản**, nhưng cần đếm số request của một phase. Nếu mục tiêu **test method B không thừa hưởng expectations của A**, dùng `resetAll()` mới hợp lý.

### Các cách reset qua Admin API

WireMock cung cấp Admin endpoints:

| HTTP tới WireMock Admin API | Hành vi |
| --- | --- |
| `POST /__admin/reset` | Reset stub mappings + request journal |
| `DELETE /__admin/requests` | Xóa request journal |
| `DELETE /__admin/mappings` | Xóa mappings |
| `POST /__admin/scenarios/reset` | Đưa scenario states về trạng thái ban đầu |
| `POST /__admin/mappings/reset` | Khôi phục default file-based mappings |

Dùng API trên khi stub chạy ngoài JVM như Docker/remote test stub. Với `WireMockServer` Java trong cùng JVM, gọi methods trên instance đơn giản hơn và ít nhầm port/admin path hơn.

Khi reset file-based mappings, cần phân biệt `resetAll` (xóa mappings) với `resetToDefaultMappings` (khôi phục defaults), tránh vô tình làm mất những fixture file mà suite dùng chung. Không reset server chung của test khác khi hai suites đang chạy song song.

## 16. Scenario state: expectation “lần 1 khác lần 2”

WireMock hỗ trợ stateful behavior qua `inScenario(...)`, `whenScenarioStateIs(...)` và `willSetStateTo(...)`. Dùng khi mock một upstream có tiến trình:

~~~text
GET /jobs/42 lần 1 -> 202 Accepted, state=RUNNING
GET /jobs/42 lần 2 -> 200 OK, state=COMPLETED
~~~

Nếu không reset **scenario state** giữa test, test B có thể bắt đầu ở `COMPLETED` dù đang kỳ vọng `STARTED`.

Đoạn DSL minh họa:

~~~java
STUB.stubFor(
        get(urlEqualTo("/jobs/42"))
                .inScenario("job-flow")
                .whenScenarioStateIs("Started")
                .willSetStateTo("RUNNING")
                .willReturn(aResponse().withStatus(202))
);

STUB.stubFor(
        get(urlEqualTo("/jobs/42"))
                .inScenario("job-flow")
                .whenScenarioStateIs("RUNNING")
                .willReturn(aResponse().withStatus(200))
);
~~~

Đây là **snippet minh họa** trong test đã có `STUB` và imports. Hai requests tới `/jobs/42` sẽ nhận response theo scenario khi không có race/concurrent requests. Sau test gọi `resetAll()` hoặc reset scenario rõ ràng. Nếu cần kiểm tra retry/backoff, **không** dựa vào `Thread.sleep` tùy tiện; inject Clock/scheduler hoặc use bounded Awaitility/test-specific timing strategy khi cần.

**Đừng dùng stateful stub làm nguồn chân lý về workflow thật**: nó chỉ giúp ép client qua những nhánh expected. State machine của đối tác phải được bảo đảm bằng contract/integration test riêng.

## 17. Timeout, slow response và network faults

Khi HTTP client đã thật sự mở TCP socket tới WireMock, bạn có thể mô phỏng:

- Trả `503` hoặc `429` để kiểm tra retry policy.
- Trả JSON sai schema để kiểm tra deserialize failure.
- Delay response để kiểm tra read timeout.
- Fault/connection reset để kiểm tra transport errors.
- Header thiếu hoặc bị thay đổi để kiểm tra robust parsing.
- Query parameter/encoding với ký tự Unicode hoặc special characters.

Ví dụ delay ở WireMock:

~~~java
STUB.stubFor(
        get(urlEqualTo("/slow"))
                .willReturn(
                        aResponse()
                                .withStatus(200)
                                .withFixedDelay(500)
                )
);
~~~

Đây là snippet minh họa. Nếu ứng dụng được cấu hình **read timeout 100 ms**, kỳ vọng request đến `/slow` có thể timeout. Nhưng **không** chép y nguyên rồi tuyên bố test timeout PASS nếu chưa cấu hình `RestClient` request factory và exception type phù hợp. Apache HttpClient, JDK HttpClient và `SimpleClientHttpRequestFactory` có hành vi timeout/exception khác nhau.

Test timeout tốt nên cấu hình timeout **rõ ràng và ngắn nhưng có biên độ ổn định**, kiểm tra exception phù hợp, và tránh thổi phồng CI latency. Một integration test có delay không nên chạy hàng chục giây khi chỉ cần chứng minh mapping logic.

### HTTPS và certificate

`dynamicHttpsPort()` chỉ mở HTTPS endpoint; Java HTTP client cần tin certificate phù hợp. Không tắt certificate verification toàn production để làm test xanh. Tạo trust store/test SSL config riêng hoặc dùng HTTP loopback khi mục tiêu không phải TLS.

### Unmatched request trả 404 có thể nguy hiểm

Một WireMockServer mặc định trả 404 cho đường dẫn không có mapping. Nếu service cũng dùng 404 làm business “không tồn tại”, một URL bị gõ sai có thể trả `Optional.empty()` và test xanh. Hãy **verify method, URL, header, expected count** và dùng WireMockExtension với unmatched-request detection khi có thể. Với manual server, có thể kiểm tra journal unmatched requests để phát hiện mapping thiếu. Đừng viết test chỉ assert 404 mà không tạo mapping 404 có chủ đích.

## 18. Chạy song song và reset: nguy cơ race giữa các test

Khi hai tests dùng cùng WireMockServer và chạy parallel:

~~~text
Test A: stub GET /products/A -> 200
Test B: resetAll()
Test A: gọi /products/A -> 404 (mapping đã bị B xóa)
Test B: stub GET /products/B -> 503
Test A: verify(1, GET /products/A) -> journal bị reset, FAIL
~~~

**ResetAll không thread-local.** Nó xóa **state của cả server instance**. Nếu muốn chạy song song, cần một trong những chiến lược:

1. **Mỗi test method sở hữu WireMockServer riêng**, dùng instance extension hoặc manual `@BeforeEach start` + `@AfterEach stop`, và tự tạo client dùng base URL riêng.
2. Nếu cần một server per class, giữ JUnit methods trong class **sequential**.
3. Tách mỗi Spring ApplicationContext per test class hoặc sử dụng Spring-managed server bean với dữ liệu/endpoint namespace riêng và **không reset toàn server trong lúc test khác đang dùng**.
4. Với nhiều Gradle forks/CI shards, mỗi JVM/server binding dùng **port động** và không dùng shared remote stub có global resets.
5. Nếu không thể tách server, serialize các test cần reset toàn server; `@ResourceLock` của JUnit chỉ điều phối trong cùng JVM/JUnit engine, **không khóa qua nhiều processes**.

`@Execution(SAME_THREAD)` hoặc cấu hình `junit.jupiter.execution.parallel.mode.default=same_thread` giúp giữ methods trong class tuần tự trong một số cấu hình; cần xem cả class-level parallel. Không khẳng định `@BeforeEach`/`@AfterEach` đủ an toàn khi có tests chạy đồng thời trên cùng server.

### Background requests làm bẩn journal

Nếu service có retry hoặc `@Async`, nó có thể gửi request sau khi test body kết thúc, đúng lúc `@AfterEach` đang reset. Khi đó verification có thể flake hoặc log của test sau bị nhiễm. Test phải **await completion** của các futures/tasks, dừng scheduler hợp lệ và chỉ cleanup khi không còn request in flight.

Đối với client retry/backoff, hãy tạo expectation bao gồm số lần request và bounded waiting; đừng test bằng sleep đoán mò hoặc dựa vào thứ tự chạy các test class.

## 19. Tránh dùng global static WireMock.configureFor khi có nhiều stub servers

WireMock có static client DSL:

~~~java
configureFor("localhost", STUB.port());
stubFor(get("/ping").willReturn(ok()));
~~~

Đây là snippet trong test có `STUB` và WireMock static imports. Nó thay configuration của **static WireMock client** dùng bởi các helper static, dễ gây nhầm server khi hai test suites chạy song song.

Trong mẫu chính, ta dùng:

~~~java
STUB.stubFor(
        get(urlEqualTo("/ping"))
                .willReturn(aResponse().withStatus(200))
);
STUB.verify(
        1,
        getRequestedFor(urlEqualTo("/ping"))
);
~~~

Đoạn thứ hai chỉ phù hợp sau khi request đã diễn ra. Các instance methods rõ ràng target đúng server object, giảm global state. Khi có hai upstreams, hãy giữ **hai WireMockServer instances** và ghi mappings qua đúng instance.

Không gọi static `WireMock.reset()` rồi tưởng đã reset mọi server trong JVM; nó chỉ điều khiển instance mà static DSL đang cấu hình tới.

## 20. So sánh với MockRestServiceServer trong @RestClientTest

Nếu bạn **không cần port động/TCP thật** mà chỉ muốn kiểm tra Spring `RestClient` gửi request đúng và decode status/body, `@RestClientTest` có thể nhẹ hơn:

~~~java
@RestClientTest(PartnerCatalogClient.class)
@TestPropertySource(properties = {
        "partner.catalog.base-url=http://partner.example.invalid",
        "partner.catalog.client-name=spring-demo"
})
class PartnerClientSliceExample {

    @Autowired
    PartnerCatalogClient client;

    @Autowired
    MockRestServiceServer mockServer;

    @BeforeEach
    void resetExpectations() {
        mockServer.reset();
    }

    @Test
    void callsExpectedEndpoint() {
        mockServer.expect(
                requestTo(
                        "http://partner.example.invalid/external/products/SKU-7"
                )
        ).andRespond(
                withSuccess(
                        """
                        {"sku":"SKU-7","title":"Notebook","quantity":4}
                        """,
                        MediaType.APPLICATION_JSON
                )
        );

        assertThat(client.find("SKU-7").orElseThrow().title())
                .isEqualTo("Notebook");
        mockServer.verify();
    }

    @AfterEach
    void cleanup() {
        mockServer.reset();
    }
}
~~~

Đây là **một class minh họa** với tên `PartnerClientSliceExample`; cần imports của Spring Boot test auto-config, `@TestPropertySource`, Spring `MockRestServiceServer`, `MediaType` và JUnit/AssertJ, nên **không coi đoạn này là một tệp độc lập trong project chính**. Mẫu đã thể hiện rõ:

- `mockServer.expect(...)` định nghĩa **expectation**.
- `mockServer.verify()` xác minh những expectations đã được thỏa mãn.
- `mockServer.reset()` xóa expectations và recorded requests.
- **Không có listening port**: request factory của client được thay bằng mock infrastructure.

Với Boot 3.5, import `@RestClientTest` là `org.springframework.boot.test.autoconfigure.web.client.RestClientTest`; Boot 4.x có module/package test riêng nên cần đối chiếu release docs. Không nhầm `MockRestServiceServer.reset()` với `WireMockServer.resetAll()`, dù cùng mục tiêu isolation.

Spring Framework hiện khuyến nghị mock web servers khi cần test transport layer/network conditions thực hơn; nhưng `MockRestServiceServer` vẫn rất hữu ích cho client slice unit/integration nhẹ.

## 21. Nếu dùng MockWebServer của OkHttp thay WireMock?

OkHttp `MockWebServer` cũng có thể bind port tự động, enqueue responses và cung cấp `RecordedRequest` để xác minh đường dẫn/header/body.

Mô hình:

~~~text
MockWebServer.start() -> lấy server.url("/")
        |
        v
HTTP client dùng baseUrl mới
        |
        v
server.enqueue(MockResponse)
        |
        v
client gọi -> server.takeRequest(timeout) -> assert
        |
        v
server.shutdown()
~~~

Với OkHttp MockWebServer, các response thường được enqueue theo thứ tự; vì vậy nếu muốn reset expectation, có thể phù hợp hơn là **tạo server mới mỗi test** và shutdown rõ ràng, thay vì giả định có `resetAll()` cùng API WireMock. Chọn framework phù hợp yêu cầu: WireMock mạnh về request matching/scenarios/verification/admin API; MockWebServer có response queue và recorded requests đơn giản.

Không “port” một test giữa hai framework bằng cách chỉ đổi tên class; lifecycle, request recording và reset semantics khác.

## 22. Bảng chẩn đoán lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `Address already in use` | Dùng cố định `8080/9090` | `wireMockConfig().dynamicPort()` |
| `Connection refused` khi tạo client | URL lấy trước khi server start hoặc đã stop | Start trước property resolve, quản lý lifecycle đúng |
| Client gọi production/staging thật | Quên override base URL trong test | `@DynamicPropertySource` + assert URL injected |
| Stub mapping đã đăng ký nhưng request bị 404 | Sai path/header/query hoặc client trỏ server khác | In unmatched requests, verify URL và header |
| Test method đầu PASS, method sau FAIL | Không reset mappings/journal | `resetAll()` trong lifecycle hoặc WireMockExtension auto-reset |
| `verify(1, ...)` đếm thành 2 | Journal chứa request của test trước | Reset request journal trước method |
| Sau reset vẫn match default stub | File-based default mappings hoặc resetToDefault semantics | Phân biệt resetAll/default mappings |
| Scenario bắt đầu ở state cũ | Chưa reset scenarios | `resetScenarios()`/`resetAll()` đúng owner |
| `@AfterAll` đã stop nhưng Spring class sau dùng URL cũ | Cached ApplicationContext lâu hơn server | `@DirtiesContext` hoặc Spring-managed server bean |
| `@Value` nhận placeholder literal | Chưa đăng ký dynamic property hoặc sai key | Kiểm tra property key, static registry method |
| `@DynamicPropertySource` dùng non-static method | Sai Spring API contract | Method static nhận `DynamicPropertyRegistry` |
| Test JUnit extension fail vì request unmatched | Stub thiếu hoặc URL không đúng | Viết expectation đúng, đừng tắt fail-on-unmatched ngay |
| Test 404 PASS dù path gõ sai | WireMock default 404 bị xem là business result | Đăng ký explicit 404 + verify request |
| Tests song song bị mất mapping | Một test gọi resetAll trên shared server | Isolate server/method, serialize hoặc namespace |
| Request đến sau `@AfterEach` | Retry/async chưa hoàn tất | Await request lifecycle trước reset |
| Timeout test flaky | Client timeout chưa cấu hình hoặc delay sát ngưỡng | Pin request factory/timeouts, có margin |
| SSL handshake fail | Test certificate không được trust | Cấu hình truststore/test SSL phù hợp |
| MockRestServiceServer không có port | Đây là client-side mock request factory | Dùng WireMock/MockWebServer nếu cần TCP |
| Body JSON deserialize fail | Content-Type/schema/record fields sai | Response JSON/headers thật trong test |
| JVM thoát nhưng stub Docker còn sống | Process/lifecycle ngoài JVM | Cleanup resource owner, không chỉ @AfterEach |
| Port 0 trong application log | Đang đọc config trước khi start | Query `port()` sau `start()` |

**Đừng sửa tất cả lỗi bằng `Thread.sleep(1000)`.** Mỗi lỗi thuộc một loại: lifecycle/binding, property wiring, request matching, transaction/async hoặc network behavior. Sửa theo nguyên nhân và thêm assertion chứng minh nguyên nhân đó đã được khắc phục.

## 23. Checklist QA trước khi xem test là độc lập

- [ ] HTTP client production nhận base URL từ cấu hình/constructor, không hard-code host?
- [ ] Stub khởi động trên **dynamic port**, không chọn cố định 8080/9090?
- [ ] Đã `start()` server trước khi client resolve base URL?
- [ ] Trong Spring test, URL dùng `@DynamicPropertySource`/`DynamicPropertyRegistrar` đúng lifecycle?
- [ ] Có assertion xác nhận client đang trỏ URL của test stub, không trỏ production?
- [ ] Stub từng test khai báo **method/path/header/body** đúng và không quá rộng?
- [ ] Có `verify(expectedCount, ...)` sau call, không chỉ assert response?
- [ ] 404 intended được stub tường minh, tránh test xanh nhờ unmatched default 404?
- [ ] 5xx, malformed JSON và timeout được test theo nghiệp vụ nếu có rủi ro?
- [ ] Reset mappings + request journal trước/giữa methods?
- [ ] Nếu dùng scenarios, đã reset state để test sau bắt đầu từ STARTED?
- [ ] `@AfterEach` teardown đúng dù assertion fail thông thường?
- [ ] Server dừng ở `@AfterAll` hoặc bởi JUnit extension/Spring context, không bị hai owners stop cùng lúc?
- [ ] Không leak WireMock static client config khi có nhiều stub servers?
- [ ] Không tái dùng cached Spring HTTP client sau khi class-scoped stub server stop?
- [ ] Test song song không reset server mà test khác đang sử dụng?
- [ ] Retry/async requests hoàn tất trước verify/reset/stop?
- [ ] Port mapping, network và TLS được mô phỏng đúng phạm vi, không expose admin API ra public?
- [ ] Test data không phụ thuộc thứ tự JUnit methods?
- [ ] Build pin WireMock/Spring Boot versions nhất quán, không trộn version 4 beta API với 3.x?
- [ ] Đã phân biệt `MockRestServiceServer` (không TCP) với WireMock/MockWebServer (HTTP thật)?
- [ ] Có lệnh chạy JUnit, mô tả expected, không tuyên bố đã chạy khi chỉ review code?

## 24. Chạy test, kết quả dự kiến và tổng kết

Với JDK 17+, Gradle Wrapper và quyền tải dependencies:

~~~bash
./gradlew test --tests "com.example.stubhttp.PartnerCatalogClientIntegrationTest"
./gradlew test --tests "com.example.stubhttp.PartnerCatalogClientExtensionTest"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.stubhttp.PartnerCatalogClientIntegrationTest"
.\gradlew.bat test --tests "com.example.stubhttp.PartnerCatalogClientExtensionTest"
~~~

Dự án có **5 JUnit methods** ở Spring integration test và **2 JUnit methods** ở WireMock Jupiter extension test, tổng **7**. Khi Spring Boot 3.5/JDK 17/WireMock 3.13.2 tương thích và không có vấn đề môi trường, expected behavior là:

~~~text
Dynamic URL:     http://localhost:<cổng hệ điều hành cấp>
200 matched:     SKU-7 / Notebook / quantity=4; GET count=1
404 explicit:    Optional.empty(); GET count=1
503 explicit:    ServiceUnavailable; GET count=1
resetAll():      mapping 200 bị xóa, request log cũ bị xóa
AfterEach:       không còn expectation/request history trong stub
AfterAll:        WireMockServer được stop
~~~

Đây là **dữ liệu/kết quả mong đợi theo mã ví dụ**, **không phải stdout thực tế**. Không có `System.out.println` trong mã; port thật, Gradle/JUnit logging và stack traces thay đổi theo môi trường. Bài soạn được kiểm tra cú pháp, API và logic theo tài liệu; việc chạy Gradle/JUnit thực tế vẫn cần environment Java/Gradle.

**Kết luận:** Một stub server chỉ làm test đáng tin khi **URL động được truyền vào client đúng thời điểm**, **mappings/request journal/scenarios được reset đúng phạm vi** và **server được stop bởi đúng lifecycle owner**. WireMock Jupiter extension giúp giảm boilerplate, nhưng với Spring context cache phải lưu ý độ dài vòng đời của client. Khi test song song, một lệnh `resetAll()` trên server chia sẻ có thể phá expectation của ca khác; vì vậy isolation vẫn là yêu cầu cốt lõi.

### Tài liệu tham khảo chính thức

- [WireMock 3.x — JUnit 5/Jupiter extension, dynamic port, automatic reset](https://wiremock.org/docs/junit-jupiter/)
- [WireMock 3.x — Java configuration và dynamicPort](https://wiremock.org/docs/configuration/)
- [WireMock 3.x — Plain Java WireMockServer start/stop](https://wiremock.org/docs/java-usage/)
- [WireMock 3.x — Stubbing, default 404 và reset](https://wiremock.org/docs/stubbing/)
- [WireMock 3.x — Verifying và request journal](https://wiremock.org/docs/verifying/)
- [WireMock 3.x — Scenario states và reset](https://wiremock.org/docs/stateful-behaviour/)
- [WireMock — Download/install, 3.13.2 dependencies](https://wiremock.org/docs/download-and-installation/)
- [Spring Framework — DynamicPropertySource và DynamicPropertyRegistrar](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Framework — HTTP client testing / MockRestServiceServer](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications / RestClientTest](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — Context caching / DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html)