# Mock web server để chạy cấu hình HTTP client thật

Khi một ứng dụng Spring gọi dịch vụ HTTP bên ngoài, bài kiểm thử cần xác nhận nhiều thứ hơn việc service trả về đúng object. Client có thể phải tạo đúng URL, method, query parameter, header xác thực, body JSON, timeout, retry và cách giải mã response. Nếu chỉ mock interface của HTTP client, các cấu hình này không thực sự chạy.

Một mock web server giải quyết vấn đề đó bằng cách mở một HTTP server nhỏ trên loopback interface và cổng ngẫu nhiên. Test cấu hình HTTP client trỏ đến server này, xếp sẵn response giả lập, rồi gửi request qua HTTP stack thật của ứng dụng. Server ghi lại request đã nhận để test xác nhận method, path, header và body.

Với Spring, cách này đặc biệt hữu ích khi kiểm thử `RestClient` hoặc `WebClient` cùng request factory, connector, codec, interceptor/filter và cấu hình timeout thực tế. Không cần gọi dịch vụ bên ngoài, nhưng request vẫn đi qua transport HTTP thật trên máy kiểm thử.

## 1. Vì sao dùng mock web server?

Giả sử `CatalogClient` gọi dịch vụ catalog. Một bài test chỉ mock `CatalogClient` có thể kiểm tra service nghiệp vụ đã gọi đúng method, nhưng không thể chứng minh HTTP request được tạo đúng. Một test chỉ mock request factory cũng có thể bỏ qua hành vi của HTTP connector hoặc cách serialize body.

Mock web server cho phép kiểm tra cả hai chiều:

```text
Ứng dụng / HTTP client thật
        |
        | GET /catalog/42
        | Accept: application/json
        v
HTTP stack của ứng dụng
        |
        | TCP loopback
        v
MockWebServer (localhost, cổng ngẫu nhiên)
        |
        +--> Trả response đã enqueue
        |
        +--> Ghi lại RecordedRequest
                     |
                     v
             Test kiểm tra request
```

Test có thể xác nhận:

- Client dùng đúng base URL và ghép path/query parameter chính xác.
- HTTP method và header được gửi đúng.
- Interceptor hoặc filter thêm token, correlation id hoặc user agent.
- Object được serialize thành JSON đúng định dạng.
- Response được decode thành DTO đúng kiểu.
- Client xử lý status lỗi, retry, timeout hoặc kết nối bị ngắt theo cấu hình.
- Request factory hoặc connector thật được dùng trong quá trình trao đổi.

Mock server không phải dịch vụ bên ngoài. Nó chỉ mô phỏng phía server và chạy trong tiến trình test hoặc một tiến trình cục bộ, thường lắng nghe trên loopback với cổng được cấp tự động.

## 2. Chọn mock web server hay mock request factory?

Spring cung cấp `MockRestServiceServer` cho một số kiểu kiểm thử HTTP client. Công cụ này chặn request tại tầng Spring request factory và so khớp expectation mà test khai báo. Nó rất hữu ích cho unit test tập trung vào cách ứng dụng xây dựng request.

Mock web server như OkHttp `MockWebServer` hoạt động ở tầng HTTP server. Client thực hiện kết nối mạng cục bộ, gửi request qua request factory hoặc connector đang cấu hình và nhận response qua HTTP transport.

| Tiêu chí | `MockRestServiceServer` | Mock web server |
|---|---|---|
| Vị trí chặn/nhận request | Tầng Spring request factory | Một HTTP server cục bộ |
| Có socket/HTTP transport thật | Không | Có, qua loopback |
| Kiểm tra request factory/connector thực tế | Không, vì request factory được thay bằng mock | Có |
| Kiểm tra serialize/deserialize qua HTTP | Kiểm tra được ở tầng Spring converter, tùy setup | Kiểm tra qua HTTP request/response thực tế |
| Kiểm tra timeout, disconnect, retry ở transport | Hạn chế | Phù hợp hơn |
| Setup | Thường gọn cho test Spring client | Cần khởi động và dừng server |

Hãy dùng `MockRestServiceServer` khi cần test nhanh hợp đồng request của Spring client và không cần kiểm tra transport. Dùng mock web server khi mục tiêu là chạy cấu hình HTTP client thật, bao gồm request factory hoặc connector. Hai cách bổ sung cho nhau; không cần chọn một cách cho mọi test.

## 3. Thêm MockWebServer vào test dependencies

Ví dụ trong bài dùng OkHttp MockWebServer 4.x với package `okhttp3.mockwebserver`. Chỉ thêm thư viện ở test scope:

```groovy
dependencies {
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}
```

Nếu dự án dùng Maven:

```xml
<dependency>
    <groupId>com.squareup.okhttp3</groupId>
    <artifactId>mockwebserver</artifactId>
    <version>4.12.0</version>
    <scope>test</scope>
</dependency>
```

Chọn phiên bản tương thích với OkHttp đang có trong dependency graph của dự án. Nếu dependency management nội bộ đã quản lý phiên bản, hãy dùng phiên bản do dự án quy định thay vì thêm một phiên bản khác không cần thiết.

Các class thường dùng:

| Class | Vai trò |
|---|---|
| `MockWebServer` | Khởi động HTTP server cục bộ và quản lý response queue |
| `MockResponse` | Khai báo status, header, body hoặc chính sách socket cho response kế tiếp |
| `RecordedRequest` | Chứa request mà server đã nhận để test kiểm tra |
| `SocketPolicy` | Mô phỏng một số tình huống socket như đóng kết nối |

## 4. Vòng đời của mock server trong JUnit

Mỗi test nên có vòng đời server rõ ràng: khởi động trước khi client được cấu hình, enqueue response trước khi gửi request và shutdown sau khi test hoàn tất.

```java
import java.io.IOException;

import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class CatalogClientTests {

    private MockWebServer server;

    @BeforeEach
    void startServer() throws IOException {
        server = new MockWebServer();
        server.start();
    }

    @AfterEach
    void stopServer() throws IOException {
        server.shutdown();
    }
}
```

`start()` thường chọn một cổng trống tự động. Không hardcode `localhost:8080`, vì cổng đó có thể đã được ứng dụng hoặc test khác sử dụng. Lấy URL động bằng `server.url("/")`:

```java
String baseUrl = server.url("/").toString();
```

URL trả về có dạng `http://localhost:<port>/`. Dùng URL này làm base URL của client. Nếu client cần path prefix, hãy đặt prefix ở cấu hình client hoặc trong URL test một cách nhất quán.

Nếu test chạy song song, không chia sẻ một server có response queue giữa nhiều test độc lập trừ khi đã đồng bộ thứ tự request. Mỗi test instance với server riêng giúp response không bị test khác lấy mất.

## 5. Dùng RestClient với MockWebServer

`RestClient` là HTTP client đồng bộ của Spring Framework. Một adapter có thể nhận `RestClient` đã cấu hình và dùng nó để gọi dịch vụ:

```java
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

record CatalogItem(String id, String name) {
}

class CatalogClient {

    private final RestClient restClient;

    CatalogClient(RestClient.Builder builder, String baseUrl) {
        this.restClient = builder
                .baseUrl(baseUrl)
                .defaultHeader("Accept", MediaType.APPLICATION_JSON_VALUE)
                .build();
    }

    CatalogClient(RestClient restClient) {
        this.restClient = restClient;
    }

    CatalogItem findById(String id) {
        return restClient.get()
                .uri("/catalog/{id}", id)
                .retrieve()
                .body(CatalogItem.class);
    }
}
```

Test tạo mock server, enqueue response và khởi tạo client với URL do server cấp:

```java
import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogClientTests {

    private MockWebServer server;
    private CatalogClient catalogClient;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        catalogClient = new CatalogClient(
                RestClient.builder(), server.url("/").toString());
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void sendsRequestAndDecodesResponse() throws Exception {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                .setBody("""
                        {
                          "id": "42",
                          "name": "Spring in Action"
                        }
                        """));

        CatalogItem item = catalogClient.findById("42");

        assertThat(item).isEqualTo(
                new CatalogItem("42", "Spring in Action"));

        RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
        assertThat(request).isNotNull();
        assertThat(request.getMethod()).isEqualTo("GET");
        assertThat(request.getPath()).isEqualTo("/catalog/42");
        assertThat(request.getHeader("Accept"))
                .isEqualTo(MediaType.APPLICATION_JSON_VALUE);
    }
}
```

Test này thực hiện một request HTTP thật tới cổng loopback. `MockWebServer` trả JSON đã enqueue; `RestClient` dùng message converter để decode JSON thành `CatalogItem`. Sau đó `takeRequest(...)` lấy request server đã ghi nhận để xác nhận method, path và header.

`takeRequest(1, TimeUnit.SECONDS)` chờ tối đa một giây để nhận request. Dùng timeout hữu hạn giúp test thất bại rõ ràng nếu client không gửi request, thay vì chờ vô hạn. Kiểm tra `request` khác null trước khi đọc các thuộc tính.

## 6. Kiểm tra request body và header xác thực

Khi client gửi POST, có thể kiểm tra body thực tế server nhận được. Ví dụ client tạo đơn hàng:

```java
record CreateCatalogItem(String name) {
}

class CatalogAdminClient {

    private final RestClient restClient;

    CatalogAdminClient(RestClient.Builder builder, String baseUrl, String apiKey) {
        this.restClient = builder
                .baseUrl(baseUrl)
                .defaultHeader("X-Api-Key", apiKey)
                .build();
    }

    void create(CreateCatalogItem command) {
        restClient.post()
                .uri("/catalog")
                .contentType(MediaType.APPLICATION_JSON)
                .body(command)
                .retrieve()
                .toBodilessEntity();
    }
}
```

Test có thể xác nhận header và JSON body:

```java
server.enqueue(new MockResponse().setResponseCode(201));

catalogAdminClient.create(new CreateCatalogItem("Spring Guide"));

RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
assertThat(request).isNotNull();
assertThat(request.getMethod()).isEqualTo("POST");
assertThat(request.getPath()).isEqualTo("/catalog");
assertThat(request.getHeader("X-Api-Key")).isEqualTo("test-api-key");
assertThat(request.getHeader("Content-Type"))
        .contains(MediaType.APPLICATION_JSON_VALUE);
assertThat(request.getBody().readUtf8())
        .contains("\"name\":\"Spring Guide\"");
```

Thứ tự property hoặc khoảng trắng trong JSON có thể phụ thuộc message converter. Nếu thứ tự không phải hợp đồng, không so sánh raw JSON bằng chuỗi nguyên văn. Có thể parse JSON rồi so sánh field, hoặc dùng JSON assertion library.

Đối với token hoặc API key, chỉ dùng giá trị giả trong test. Request đã ghi nhận có thể chứa header và body; không log toàn bộ dữ liệu nhạy cảm trong môi trường chạy test thật.

## 7. Kiểm tra cấu hình RestClient được tạo trong Spring context

Ví dụ trước khởi tạo `RestClient.Builder` trực tiếp. Điều đó kiểm tra cách `CatalogClient` cấu hình builder, nhưng không nhất thiết kiểm tra các `RestClientCustomizer`, request factory, SSL hoặc interceptor được Spring Boot cung cấp.

Nếu mục tiêu là kiểm tra client bean production, hãy load đúng application context và chỉ thay đổi base URL để trỏ đến mock server. Ví dụ cấu hình bean:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogHttpClientConfiguration {

    @Bean
    CatalogClient catalogClient(
            RestClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl) {

        RestClient restClient = builder
                .baseUrl(baseUrl)
                .defaultHeader(HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();

        return new CatalogClient(restClient);
    }
}
```

Trong ứng dụng Spring Boot, `RestClient.Builder` được auto-configure và có thể được các customizer của ứng dụng điều chỉnh. Test dùng `@SpringBootTest` để nạp cùng cấu hình production, còn `@DynamicPropertySource` cung cấp base URL động:

```java
import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class CatalogClientContextTests {

    private static final MockWebServer SERVER = startServer();

    @Autowired
    CatalogClient catalogClient;

    private static MockWebServer startServer() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        }
        catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry registry) {
        registry.add("catalog.base-url", () -> SERVER.url("/").toString());
    }

    @AfterAll
    static void stopServer() throws IOException {
        SERVER.shutdown();
    }

    @Test
    void usesConfiguredCatalogClientBean() throws Exception {
        SERVER.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("""
                        {"id":"7","name":"Reactive Systems"}
                        """));

        CatalogItem item = catalogClient.findById("7");

        assertThat(item.name()).isEqualTo("Reactive Systems");
        RecordedRequest request = SERVER.takeRequest(1, TimeUnit.SECONDS);
        assertThat(request).isNotNull();
        assertThat(request.getPath()).isEqualTo("/catalog/7");
    }
}
```

Ví dụ này giả định ứng dụng có một `@SpringBootApplication` quét `CatalogHttpClientConfiguration`, và `CatalogClient` có phương thức `findById(...)` như phần trước. Nếu cấu hình của bạn không dùng Spring Boot, hãy khai báo `RestClient.Builder` và các customizer cần thiết trong test context.

Mock server được khởi động trong static initializer để sẵn sàng khi Spring tạo context và đọc dynamic property. `@AfterAll` dừng server sau khi test class hoàn tất. Với context được cache qua nhiều test class, hãy thiết kế vòng đời server tương thích với thời gian context còn sử dụng client; không shutdown server trong khi context đó vẫn được tái sử dụng.

## 8. Dùng MockWebServer với WebClient

`WebClient` là HTTP client reactive của Spring WebFlux. MockWebServer vẫn có thể dùng được vì nó nhận HTTP request qua socket; khác biệt nằm ở cách test tiêu thụ kết quả reactive.

```java
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class ReactiveCatalogClient {

    private final WebClient webClient;

    ReactiveCatalogClient(WebClient.Builder builder, String baseUrl) {
        this.webClient = builder
                .baseUrl(baseUrl)
                .defaultHeader("Accept", "application/json")
                .build();
    }

    Mono<CatalogItem> findById(String id) {
        return webClient.get()
                .uri("/catalog/{id}", id)
                .retrieve()
                .bodyToMono(CatalogItem.class);
    }
}
```

Test dùng Reactor Test để chờ publisher hoàn tất:

```java
import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class ReactiveCatalogClientTests {

    private MockWebServer server;
    private ReactiveCatalogClient catalogClient;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();
        catalogClient = new ReactiveCatalogClient(
                WebClient.builder(), server.url("/").toString());
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void sendsRequestAndReceivesReactiveResponse() throws Exception {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("{\"id\":\"9\",\"name\":\"WebFlux\"}"));

        StepVerifier.create(catalogClient.findById("9"))
                .expectNext(new CatalogItem("9", "WebFlux"))
                .verifyComplete();

        RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
        assertThat(request).isNotNull();
        assertThat(request.getMethod()).isEqualTo("GET");
        assertThat(request.getPath()).isEqualTo("/catalog/9");
    }
}
```

`StepVerifier` subscribe vào `Mono`, chờ response và xác nhận giá trị phát ra. Sau khi publisher hoàn tất, test đọc `RecordedRequest` để xác nhận HTTP request thực tế. Trong Spring Boot, nếu muốn kiểm tra `WebClient.Builder` và các `WebClientCustomizer` production, hãy load application context và override base URL giống ví dụ `RestClient`.

`WebClient` cần một `ClientHttpConnector`. Connector thực tế được chọn theo dependency và cấu hình ứng dụng. Nếu muốn kiểm tra Reactor Netty, bảo đảm test dùng đúng connector Reactor Netty mà ứng dụng sử dụng; đừng thay connector bằng một mock chỉ để test chạy được.

## 9. Mô phỏng status lỗi và xác nhận error handling

Mock server có thể trả bất kỳ status nào để kiểm tra client xử lý lỗi:

```java
server.enqueue(new MockResponse()
        .setResponseCode(404)
        .addHeader("Content-Type", "application/json")
        .setBody("""
                {"code":"ITEM_NOT_FOUND"}
                """));
```

Với `RestClient.retrieve()`, response 4xx/5xx mặc định dẫn tới exception thuộc họ `RestClientResponseException`, trừ khi ứng dụng đăng ký status handler riêng. Có thể kiểm tra status và body lỗi:

```java
import org.springframework.web.client.HttpClientErrorException;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

assertThatThrownBy(() -> catalogClient.findById("missing"))
        .isInstanceOf(HttpClientErrorException.NotFound.class);
```

Với `WebClient.retrieve()`, response 4xx/5xx mặc định được biểu diễn bằng `WebClientResponseException`. Test reactive có thể xác nhận error signal:

```java
import org.springframework.web.reactive.function.client.WebClientResponseException;

StepVerifier.create(catalogClient.findById("missing"))
        .expectErrorSatisfies(error -> {
            assertThat(error)
                    .isInstanceOf(WebClientResponseException.NotFound.class);
        })
        .verify();
```

Nếu client có retry hoặc fallback, test cần enqueue chuỗi response tương ứng. Ví dụ enqueue `503` rồi `200`, gọi client một lần và xác nhận kết quả cuối cùng; sau đó lấy hai request từ server để chứng minh retry đã thực hiện đúng số lần. Không dùng `Thread.sleep(...)` để chờ retry nếu có thể điều khiển thời gian bằng scheduler hoặc cơ chế retry test của ứng dụng.

## 10. Kiểm thử timeout và kết nối bị ngắt

MockWebServer hỗ trợ mô phỏng một số tình huống transport mà mock request factory khó tái hiện.

### Response chậm

Có thể cấu hình response trì hoãn body:

```java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"id\":\"1\",\"name\":\"Slow item\"}")
        .setBodyDelay(2, TimeUnit.SECONDS));
```

Sau đó chạy client với read/response timeout ngắn hơn thời gian server trì hoãn và xác nhận timeout được xử lý theo hợp đồng. Timeout chính xác phụ thuộc request factory hoặc connector, nên cấu hình timeout trong test phải là cấu hình thực tế mà ứng dụng dùng.

### Server đóng kết nối

Có thể mô phỏng server ngắt socket bằng `SocketPolicy`:

```java
import okhttp3.mockwebserver.SocketPolicy;

server.enqueue(new MockResponse()
        .setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST));
```

Client sẽ nhận lỗi I/O hoặc lỗi connector tương ứng. Nếu ứng dụng có retry, hãy kiểm tra request được gửi lại và response cuối cùng được xử lý. Loại exception cụ thể có thể khác giữa JDK HTTP client, Apache HttpClient và Reactor Netty; test hợp đồng ứng dụng nên ưu tiên kiểm tra fallback/retry hoặc loại lỗi công khai mà adapter cam kết.

Không nên tạo timeout test dựa vào thời gian thực quá sát. Đặt khoảng cách đủ lớn giữa response delay và timeout, hoặc dùng một cơ chế clock/scheduler có thể điều khiển nếu logic retry/timeout của ứng dụng hỗ trợ điều đó.

## 11. Kiểm tra retry và thứ tự request

MockWebServer dùng response queue: mỗi request tiếp theo lấy một `MockResponse` đã enqueue. Điều này thuận tiện cho retry:

```java
server.enqueue(new MockResponse().setResponseCode(503));
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"id\":\"42\",\"name\":\"Recovered\"}"));

CatalogItem item = retryingCatalogClient.findById("42");

assertThat(item.name()).isEqualTo("Recovered");
RecordedRequest first = server.takeRequest(1, TimeUnit.SECONDS);
RecordedRequest second = server.takeRequest(1, TimeUnit.SECONDS);
assertThat(first).isNotNull();
assertThat(second).isNotNull();
assertThat(first.getPath()).isEqualTo("/catalog/42");
assertThat(second.getPath()).isEqualTo("/catalog/42");
```

Ví dụ giả định `retryingCatalogClient` có retry policy xử lý `503`. Nếu không có retry, request đầu tiên sẽ nhận lỗi và request thứ hai không được gửi. Test nên xác nhận cả kết quả lẫn số request để tránh một fallback che giấu việc retry không chạy.

Với nhiều request đồng thời, không giả định thứ tự response queue gắn với thứ tự hoàn tất của các publisher. Nếu cần kiểm tra concurrency, hãy dùng request path hoặc header riêng để phân biệt từng request và đọc các `RecordedRequest` tương ứng.

## 12. Kiểm tra URI, encoding và redirect

Một trong những lỗi phổ biến ở HTTP client là ghép URL hoặc encode query parameter sai. Vì mock server ghi nhận path thực tế, test có thể kiểm tra request line:

```java
RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
assertThat(request.getPath())
        .isEqualTo("/search?q=spring%20framework&page=2");
```

Kết quả encoding phụ thuộc cách client và URI builder xử lý ký tự. Hãy xác nhận theo hợp đồng của upstream server, đặc biệt với dấu cách, dấu `+`, Unicode, dấu `/` trong path variable và các giá trị có nhiều lần xuất hiện.

MockWebServer cũng có thể trả redirect bằng status `301`, `302`, `307` hoặc `308` cùng header `Location`. Hành vi theo redirect phụ thuộc request factory/connector và cấu hình follow redirect. Test nên xác nhận client có hoặc không theo redirect đúng như ứng dụng yêu cầu, và dùng `RecordedRequest` để kiểm tra server có nhận request thứ hai ở path mới hay không.

## 13. Kiểm tra TLS hoặc xác thực mTLS

MockWebServer hỗ trợ cấu hình HTTPS bằng `useHttps(...)` với `SSLSocketFactory`. Điều này hữu ích khi client có cấu hình trust store, hostname verification hoặc client certificate và test cần kiểm tra handshake thật.

Một test TLS cần chuẩn bị certificate test, trust material và có thể cả key material phía client. Không tắt hostname verification hoặc trust tất cả certificate chỉ để làm test qua. Cấu hình test nên phản ánh chính sách bảo mật cần kiểm tra, nhưng sử dụng chứng thư giả dành riêng cho test.

Nếu chỉ cần kiểm tra header `Authorization` hoặc API key, HTTP loopback thường đủ; không cần thêm TLS complexity. Nếu mục tiêu là kiểm tra trust store, certificate rotation hoặc mTLS, hãy dùng HTTPS mock server và xác nhận handshake thực sự diễn ra.

## 14. MockWebServer và WireMock

OkHttp MockWebServer phù hợp khi cần một HTTP server nhỏ, response queue, ghi nhận request và mô phỏng socket behavior. WireMock cung cấp DSL phong phú hơn cho request matching, scenario state, verification và stub phức tạp.

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Enqueue response theo thứ tự và lấy request đã nhận | MockWebServer |
| Kiểm tra transport và request factory/connector thực | MockWebServer hoặc WireMock chạy server thật |
| Stub dựa trên JSONPath, header và query phức tạp | WireMock |
| Kịch bản nhiều trạng thái, mapping được tái sử dụng | WireMock |
| Test Spring `RestClient` ở tầng request factory, không cần socket | `MockRestServiceServer` |

Chọn công cụ nhỏ nhất đáp ứng mục tiêu. Với một client chỉ cần xác nhận URL, header, JSON và response, MockWebServer thường đủ.

## 15. Các lỗi thường gặp

| Cách làm | Vấn đề | Cách làm phù hợp hơn |
|---|---|---|
| Hardcode cổng như `8080` | Cổng có thể bận hoặc xung đột khi chạy song song | Dùng `server.start()` và `server.url(...)` |
| Không gọi `shutdown()` | Server và socket có thể còn chạy sau test | Dừng server trong `@AfterEach` hoặc `@AfterAll` |
| Enqueue response sau khi gửi request | Request có thể chờ response hoặc nhận response không mong muốn | Enqueue trước khi gọi client |
| Không đọc `RecordedRequest` | Chỉ kiểm tra response, bỏ qua URL/header/body đã gửi | Xác nhận request server nhận được |
| Mock request factory rồi kết luận transport thật đúng | Mock thay thế tầng transport cần kiểm tra | Dùng mock web server để nhận HTTP qua socket |
| Dùng server chung cho test chạy song song | Response queue có thể bị test khác tiêu thụ | Tạo server riêng hoặc đồng bộ rõ ràng |
| So sánh JSON raw theo chuỗi khi không cần thứ tự | Test phụ thuộc format và thứ tự property | Parse JSON và so sánh field |
| Timeout quá sát response delay | Kết quả dễ dao động trên CI | Dùng khoảng thời gian đủ cách biệt và timeout hữu hạn |
| Tắt TLS verification để test dễ chạy | Không kiểm tra đúng chính sách bảo mật | Dùng certificate test và trust configuration đúng |

## 16. Quy trình thiết kế test HTTP client

1. Xác định cấu hình client nào cần được chạy thật: base URL, request factory/connector, timeout, converter/codec, interceptor/filter, TLS hoặc retry.
2. Chọn công cụ: MockWebServer cho HTTP transport thật, `MockRestServiceServer` cho request factory mock hoặc WireMock cho stub phức tạp.
3. Khởi động mock server trên cổng ngẫu nhiên trước khi tạo client hoặc Spring context.
4. Override duy nhất endpoint upstream để trỏ client production tới mock server; giữ các customizer và transport cần kiểm tra.
5. Enqueue response phù hợp trước khi gửi request.
6. Gọi phương thức của client ứng dụng như khi chạy production.
7. Assertion kết quả đã decode hoặc exception/fallback mà client công bố.
8. Lấy `RecordedRequest` để xác nhận method, path, query, header và body thực tế.
9. Với retry, timeout hoặc disconnect, kiểm tra cả số request và kết quả cuối.
10. Shutdown server và bảo đảm vòng đời server tương thích với Spring context cache hoặc test parallelism.

## 17. Tài liệu tham khảo

- [Spring Framework Reference — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, `WebClient`, request factory và cấu hình HTTP client.
- [Spring Framework Reference — Testing REST Clients](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): kiểm thử client Spring và `MockRestServiceServer`.
- [OkHttp MockWebServer](https://github.com/square/okhttp/tree/master/mockwebserver): thư viện mock HTTP server, response queue và recorded requests.
- [Spring Boot Reference — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): cấu hình và sử dụng REST client trong Spring Boot.

Mock web server giúp test chạy cấu hình HTTP client thật mà không phụ thuộc dịch vụ bên ngoài. Hãy trỏ client production tới một server cục bộ có cổng động, enqueue response, gọi client như bình thường và kiểm tra cả kết quả lẫn request đã được server nhận. Cách này cung cấp bằng chứng về request factory hoặc connector, codec và chính sách HTTP mà mock ở tầng interface không thể thay thế.
