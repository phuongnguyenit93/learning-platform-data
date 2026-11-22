# MockRestServiceServer cho client đồng bộ và máy chủ giả lập cho WebClient

## 1. Khi kiểm thử HTTP client cần giả lập điều gì?

Khi ứng dụng Spring gọi một dịch vụ HTTP bên ngoài, unit test của service thường không nên phụ thuộc API thật: mạng có thể mất, dữ liệu có thể thay đổi, authentication hết hạn, rate limit, chi phí và tốc độ sẽ làm test không ổn định. Bài toán là kiểm tra **mã HTTP client của chính ứng dụng** có tạo đúng request và diễn giải đúng response hay không, với một bên server được kiểm soát.

Một hợp đồng mẫu: ứng dụng gọi catalog API:
- **GET /api/books/7?lang=en**, header **X-Tenant: training**, Accept: application/json. Server đáp **200**, body **{"id":7,"title":"Spring"}**.
- **POST /api/books**, Content-Type: application/json, body **{"title":"New Book"}**; server đáp **201**, Location: /api/books/8 và JSON sách mới.
- Khi server đáp **404**, client phải đưa lỗi ra ngoài hoặc ánh xạ theo chính sách nghiệp vụ; test không nên luôn giả lập 200.

Ở đây ta kiểm tra **client gửi đi**. Đừng nhầm với **MockMvc** hoặc **WebTestClient.bindToController(...)**: hai API đó chuyên kiểm thử **server-side controller/handler**. Công cụ trong bài tác động lên phía client đang tạo outbound HTTP request.

### Hai hướng mô phỏng

1. **MockRestServiceServer** của Spring Test: gắn request factory giả vào **RestClient** hoặc **RestTemplate** đồng bộ. Client vẫn đi qua phần tạo URI, headers, serialization/deserialization của Spring, nhưng **không có kết nối HTTP thật**. Test khai báo kỳ vọng bằng **expect(...).andRespond(...)**, gọi code thực tế và **verify()**.
2. **Mock HTTP server chạy trên cổng loopback**: ví dụ **OkHttp MockWebServer** hoặc **WireMock**. Nó lắng nghe HTTP thật tại localhost, trả response được định sẵn và lưu request để test kiểm tra. **WebClient** gọi server giả qua HTTP client/connector thật, phù hợp hơn để thử encoding, timeout, network, connection behavior hoặc streaming.

Spring Framework chính thức khuyến nghị mock web server khi muốn kiểm thử transport/network đầy đủ; **MockRestServiceServer** vẫn hữu ích, nhanh và cô lập tốt cho RestTemplate/RestClient. Chọn công cụ theo điều muốn khẳng định, không dùng giả lập HTTP để thay thế tất cả bài kiểm thử nghiệp vụ.

## 2. So sánh phạm vi, tốc độ và độ tin cậy

| Tiêu chí | MockRestServiceServer | MockWebServer hoặc WireMock |
| --- | --- | --- |
| Đối tượng thường kiểm thử | RestClient, RestTemplate (đồng bộ) | WebClient, RestClient, RestTemplate, HTTP service proxy |
| HTTP socket thật | Không | Có: server giả mở cổng localhost |
| Client HTTP connector thật | Bị thay bằng mock request factory cho test | Có thể dùng giống cấu hình production |
| Khai báo hành vi | **expect** + **andRespond** | Enqueue/dispatcher/stub HTTP response |
| Kiểm tra request | Spring request matchers, số lượng và verify() | RecordedRequest / verification API của mock server |
| Kiểm thử serialization + headers | Có | Có |
| Kiểm thử connect/response timeout, transfer encoding | Không đầy đủ | Phù hợp hơn; phụ thuộc connector và fixture |
| Tài nguyên cần dọn | Expectation state giữa các test | Phải đóng server/port và request queue |
| Trường hợp lý tưởng | Test logic gọi đồng bộ nhanh, có tính quyết định | Test WebClient reactive và hành vi network |
| Giới hạn chung | Không xác minh API thật ngoài Internet | Vẫn không chứng minh API thật dùng đúng schema và deployment |

**Server giả** không đồng nghĩa **mock interface Java**. Khi mock một repository/client interface bằng Mockito, ta không biết URL, query, HTTP method, Content-Type có được mã hóa đúng không. Trong bài này, nên gọi **mã dùng RestClient/WebClient thật** để quan sát outbound HTTP contract.

## 3. MockRestServiceServer: gắn vào RestClient.Builder đúng thứ tự

Từ Spring Framework 6.1, **MockRestServiceServer.bindTo(RestClient.Builder)** hỗ trợ RestClient. Ví dụ:

~~~java
RestClient.Builder builder = RestClient.builder()
    .baseUrl("https://catalog.example.test");

MockRestServiceServer server =
    MockRestServiceServer.bindTo(builder).build();

RestClient client = builder.build();
~~~

**Điểm rất quan trọng:** dùng **cùng RestClient.Builder** để tạo mock server rồi mới **builder.build()**. Nếu gọi **build()** trước hoặc service tạo một builder/client độc lập, mock request factory có thể không nằm trên client mà code đang sử dụng. Địa chỉ **catalog.example.test** chỉ là host ví dụ, không hề được truy cập qua network trong bài test dùng MockRestServiceServer khi gắn đúng.

Một test hoàn chỉnh về ý tưởng:

~~~java
server.expect(requestTo(
        "https://catalog.example.test/api/books/7?lang=en"))
    .andExpect(method(HttpMethod.GET))
    .andExpect(header("X-Tenant", "training"))
    .andRespond(withSuccess(
        "{\"id\":7,\"title\":\"Spring\"}",
        MediaType.APPLICATION_JSON));

Book result = client.get()
    .uri("/api/books/{id}?lang={lang}", 7, "en")
    .header("X-Tenant", "training")
    .retrieve()
    .body(Book.class);

assertEquals(new Book(7, "Spring"), result);
server.verify();
~~~

Mẫu này cần static imports **MockRestRequestMatchers.requestTo/method/header**, **MockRestResponseCreators.withSuccess**, **Assertions.assertEquals** và các kiểu Spring liên quan.

### Quy trình nội bộ

~~~text
JUnit test
   |
   | đăng ký expect(requestTo(...)), andExpect(...), andRespond(...)
   v
MockRestServiceServer
   |
   | bindTo(RestClient.Builder), thay ClientHttpRequestFactory
   v
Mã ứng dụng gọi RestClient thật ở mức API
   |
   | build URI + headers + JSON encoding
   v
Mock ClientHttpRequestFactory
   |
   | so request với expectations, trả stub response
   v
RestClient decode response JSON thành DTO
   |
   v
JUnit assert DTO/exception + mockServer.verify()
~~~

Không có TCP/HTTP server thật trong dòng này. Vì vậy nếu muốn kiểm tra xử lý TLS, proxy, connect timeout hoặc sự khác nhau giữa HTTP clients (Reactor Netty, JDK, Apache), phải có test dùng mock web server hoặc môi trường tích hợp.

## 4. Khai báo expectation: URL, method, headers và body

Một expectation MockRestServiceServer thường gồm:
- **requestTo(String/URI)** hoặc matcher request theo logic tùy biến.
- **method(HttpMethod.GET/POST/PUT...)**.
- **header(...)**, **headerDoesNotExist(...)**, **queryParam(...)** (tùy phiên bản Spring), **content().contentType(...)**, **content().json(...)**, **content().string(...)**.
- **andRespond(withSuccess(...))**, **withStatus(HttpStatus...)**, **withServerError()** và response creator khác.

Ví dụ POST JSON:

~~~java
server.expect(requestTo(
        "https://catalog.example.test/api/books"))
    .andExpect(method(HttpMethod.POST))
    .andExpect(header("X-Tenant", "training"))
    .andExpect(content().contentType(MediaType.APPLICATION_JSON))
    .andExpect(content().json("{\"title\":\"New Book\"}"))
    .andRespond(withStatus(HttpStatus.CREATED)
        .contentType(MediaType.APPLICATION_JSON)
        .header("Location", "/api/books/8")
        .body("{\"id\":8,\"title\":\"New Book\"}"));
~~~

**Request header khác response header**:
- **.andExpect(header("X-Tenant","training"))** kiểm tra header mà **client gửi**.
- **.andRespond(... .header("Location", ...))** đặt header mà **server giả trả về**.
- Nếu code cần đọc **Location**, phải có logic đọc headers, ví dụ dùng **toEntity(Book.class)**, thay vì chỉ **body(Book.class)**.

**content().json(...)** so khớp JSON theo cấu trúc, tránh test fail chỉ vì thứ tự field hoặc whitespace. Với contract chặt, test thêm điều kiện về trường ngoài dự kiến/kiểu dữ liệu, hoặc dùng matcher strict nếu phiên bản Spring/Test dependency hỗ trợ.

### Kiểm tra số lần gọi và thứ tự

Mặc định **MockRestServiceServer** kỳ vọng các request theo thứ tự đăng ký (với một số ngoại lệ khi một expectation cho phép nhiều lần). Có thể chỉ định số lần:

~~~java
server.expect(ExpectedCount.times(2),
        requestTo("https://catalog.example.test/api/books/7?lang=en"))
    .andRespond(withSuccess(
        "{\"id\":7,\"title\":\"Spring\"}",
        MediaType.APPLICATION_JSON));
~~~

Khi thử retry hãy xác định đúng số request kỳ vọng. Nếu application gọi một lần nhưng kỳ vọng hai lần, **server.verify()** thất bại. Khi test các request độc lập thực sự không có thứ tự bắt buộc, builder hỗ trợ **ignoreExpectOrder(true)**; vẫn nên chứng minh không có request thừa/thiếu.

Nếu nhiều expectation dùng chung URL, headers/body cần phân biệt đủ rõ. Đừng dùng một matcher quá rộng (chỉ kiểm host) khiến test pass dù endpoint sai.

### Trả lỗi 404, 429, 500

~~~java
server.expect(requestTo(
        "https://catalog.example.test/api/books/404?lang=vi"))
    .andRespond(withStatus(HttpStatus.NOT_FOUND)
        .contentType(MediaType.APPLICATION_JSON)
        .body("{\"message\":\"Not found\"}"));
~~~

Với **RestClient.retrieve()**, response 4xx/5xx mặc định có thể thành **RestClientResponseException** (ví dụ **HttpClientErrorException.NotFound**). Cách assert:

~~~java
assertThrows(HttpClientErrorException.NotFound.class,
    () -> catalog.find(404, "vi"));
server.verify();
~~~

Để kiểm tra retry/bulkhead/circuit breaker, phải cấu hình thật ở client/service dưới test. MockRestServiceServer không tự retry và không tự biến lỗi 503 thành 200. Không nên lạm dụng mock phản hồi thành công nếu mục tiêu kiểm thử xử lý lỗi.

## 5. Vì sao WebClient nên dùng mock web server?

**WebClient** làm việc qua API reactive **Mono/Flux** và HTTP connector, ví dụ Reactor Netty. **MockRestServiceServer.bindTo(RestClient.Builder)** không móc trực tiếp vào WebClient như RestClient. Có thể thay ExchangeFunction của WebClient bằng mock thủ công, nhưng điều đó bỏ qua phần transport và có nguy cơ test chính mock thay vì request thực.

Một **mock HTTP server** nhận yêu cầu TCP/HTTP thực từ WebClient tại localhost; nó cho phép kiểm tra những phần sau:

1. URL/path/query encoding do WebClient tạo ra.
2. HTTP verb, headers, Content-Type, JSON request bytes.
3. Mã trạng thái và JSON response được WebClient codec giải mã.
4. Timeout, connection reset, chunked transfer hoặc delayed response nếu fixture được cấu hình.
5. Dạng stream NDJSON/SSE theo từng frame/chunk với giới hạn/thời gian có kiểm soát.

Spring Framework khuyến nghị **OkHttp MockWebServer** hoặc **WireMock** cho kiểm thử WebClient. Đừng nhầm **WebTestClient.bindToController**: công cụ đó dựng mock server framework để kiểm thử *code phía server*; nếu muốn kiểm thử một WebClient service như production, hãy tạo WebClient thật trỏ tới localhost của mock HTTP server.

## 6. MockWebServer: enqueue(response) và takeRequest()

**OkHttp MockWebServer 4.12.0** có API Java:

~~~java
MockWebServer server = new MockWebServer();
server.start();

try {
    server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"id\":7,\"title\":\"Spring\"}"));

    WebClient client = WebClient.builder()
        .baseUrl(server.url("/").toString())
        .build();

    Book book = client.get()
        .uri("/api/books/{id}?lang={lang}", 7, "en")
        .header("X-Tenant", "training")
        .retrieve()
        .bodyToMono(Book.class)
        .block(Duration.ofSeconds(5));

    RecordedRequest request =
        server.takeRequest(5, TimeUnit.SECONDS);

    assertNotNull(request);
    assertEquals("GET", request.getMethod());
    assertEquals("/api/books/7?lang=en", request.getPath());
    assertEquals("training", request.getHeader("X-Tenant"));
    assertEquals(new Book(7, "Spring"), book);
} finally {
    server.shutdown();
}
~~~

Các import gồm:
- **okhttp3.mockwebserver.MockWebServer**, **MockResponse**, **RecordedRequest**.
- **org.springframework.web.reactive.function.client.WebClient**.
- **java.time.Duration**, **java.util.concurrent.TimeUnit** và JUnit assertions.

**enqueue** định thứ tự các response stub sẽ được trả. **takeRequest** lấy và loại bỏ một recorded request từ queue; dùng bản có timeout tránh chờ vô hạn khi WebClient không gửi gì do quên subscribe. **server.url("/")** tạo URL chứa cổng localhost ngẫu nhiên đã cấp, tránh xung đột cổng cố định.

### Một điểm dễ sai: Mono chỉ chạy khi subscribe

~~~java
Mono<Book> pending = client.get()
    .uri("/api/books/7")
    .retrieve()
    .bodyToMono(Book.class);

// Chỉ tạo pipeline, chưa chắc đã có HTTP request.
~~~

Nếu gọi **takeRequest()** ngay sau đó mà không subscribe, test có thể treo/timeout vì request chưa hề gửi. Trong một test đồng bộ, dùng **block(Duration.ofSeconds(5))** tại ranh giới test hoặc **StepVerifier** khi thêm **reactor-test**:

~~~java
StepVerifier.create(pending)
    .expectNextMatches(book -> book.id() == 7)
    .verifyComplete();
~~~

StepVerifier chỉ là fragment khi đã có dependency và import **reactor.test.StepVerifier**. Với stream vô hạn, dùng take(n), thời hạn xác minh và cleanup subscription, không gọi collectList() một cách vô hạn.

### MockWebServer khác WebClient thực về cái gì?

MockWebServer đóng vai *remote HTTP server*. **WebClient vẫn dùng HTTP connector thật** và thực hiện HTTP call, codecs và lifecycle. Tuy vậy:
- Remote API production có thể yêu cầu TLS, OAuth, proxy và khác nội dung JSON.
- Fixture test chỉ đúng bằng response mà tác giả tạo.
- Localhost ít latency hơn Internet. Timeout test cần mô phỏng chậm thật có kiểm soát thay vì kỳ vọng network tự chậm.

## 7. Dự án Java 17 có thể chạy: RestClient + MockRestServiceServer, WebClient + MockWebServer

Ví dụ này dùng **Spring Boot 3.5.0** (Spring Framework 6.2), **JDK 17+**, JUnit Jupiter, Spring Test và **MockWebServer 4.12.0**. Toàn bộ test tự tạo clients và mocks, không cần chạy Spring Boot server hay có Internet ở runtime (Maven vẫn cần tải dependencies lần đầu).

Cấu trúc:

~~~text
client-http-contract-tests/
├── pom.xml
├── src/main/java/demo/
│   ├── Book.java
│   ├── CreateBook.java
│   ├── CatalogRestClient.java
│   └── CatalogWebClient.java
└── src/test/java/demo/
    ├── CatalogRestClientTest.java
    └── CatalogWebClientTest.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>client-http-contract-tests</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

**src/main/java/demo/Book.java**:

~~~java
package demo;

public record Book(long id, String title) {}
~~~

**src/main/java/demo/CreateBook.java**:

~~~java
package demo;

public record CreateBook(String title) {}
~~~

**src/main/java/demo/CatalogRestClient.java**:

~~~java
package demo;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public final class CatalogRestClient {
    private final RestClient client;

    public CatalogRestClient(RestClient client) {
        this.client = client;
    }

    public Book find(long id, String lang) {
        return client.get()
            .uri("/api/books/{id}?lang={lang}", id, lang)
            .header("X-Tenant", "training")
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(Book.class);
    }

    public Book create(CreateBook body) {
        return client.post()
            .uri("/api/books")
            .header("X-Tenant", "training")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .body(body)
            .retrieve()
            .body(Book.class);
    }
}
~~~

**src/main/java/demo/CatalogWebClient.java**:

~~~java
package demo;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public final class CatalogWebClient {
    private final WebClient client;

    public CatalogWebClient(WebClient client) {
        this.client = client;
    }

    public Mono<Book> find(long id, String lang) {
        return client.get()
            .uri("/api/books/{id}?lang={lang}", id, lang)
            .header("X-Tenant", "training")
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .bodyToMono(Book.class);
    }

    public Mono<Book> create(CreateBook body) {
        return client.post()
            .uri("/api/books")
            .header("X-Tenant", "training")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(body)
            .retrieve()
            .bodyToMono(Book.class);
    }
}
~~~

Hai class này dùng DTO giống nhau nhưng khác semantics:
- **CatalogRestClient.find** đồng bộ, chờ response và trả Book.
- **CatalogWebClient.find** trả **Mono<Book>**; HTTP được thực thi khi có subscription.
- **create** gửi JSON nhờ converter/codec từ dependency Jackson do Spring WebFlux starter cung cấp.
- Lỗi HTTP 4xx/5xx của **retrieve()** mặc định thành exception/error signal, test phải xác minh đường lỗi.

### 7.1 Test đồng bộ bằng MockRestServiceServer

**src/test/java/demo/CatalogRestClientTest.java**:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class CatalogRestClientTest {

    private MockRestServiceServer server;
    private CatalogRestClient catalog;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://catalog.example.test");
        server = MockRestServiceServer.bindTo(builder).build();
        catalog = new CatalogRestClient(builder.build());
    }

    @Test
    void getAssertsMethodUrlHeaderAndParsesJson() {
        server.expect(requestTo(
                "https://catalog.example.test/api/books/7?lang=en"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header("X-Tenant", "training"))
            .andRespond(withSuccess(
                "{\"id\":7,\"title\":\"Spring\"}",
                MediaType.APPLICATION_JSON));

        Book book = catalog.find(7, "en");

        assertEquals(new Book(7, "Spring"), book);
        server.verify();
    }

    @Test
    void postAssertsJsonBodyAndParsesCreatedResponse() {
        server.expect(requestTo(
                "https://catalog.example.test/api/books"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(header("X-Tenant", "training"))
            .andExpect(content().contentType(MediaType.APPLICATION_JSON))
            .andExpect(content().json("{\"title\":\"New Book\"}"))
            .andRespond(withStatus(HttpStatus.CREATED)
                .contentType(MediaType.APPLICATION_JSON)
                .header("Location", "/api/books/8")
                .body("{\"id\":8,\"title\":\"New Book\"}"));

        Book created = catalog.create(new CreateBook("New Book"));

        assertEquals(new Book(8, "New Book"), created);
        server.verify();
    }

    @Test
    void notFoundPropagatesHttp404() {
        server.expect(requestTo(
                "https://catalog.example.test/api/books/404?lang=vi"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThrows(
            HttpClientErrorException.NotFound.class,
            () -> catalog.find(404, "vi"));
        server.verify();
    }
}
~~~

Đặc điểm:
- **@BeforeEach** tạo builder và mock server mới cho mỗi test, tránh expectation cũ lọt sang test tiếp theo.
- Bắt buộc **MockRestServiceServer.bindTo(builder)** *trước* **builder.build()** để client dùng mock request factory.
- **expect** assert request outbound, **andRespond** giả response inbound, **assertEquals** assert dữ liệu client giải mã, **verify()** xác nhận expectations được đáp ứng.
- Test POST có Location response nhưng **CatalogRestClient.create** hiện chỉ trả body; test mới không xác minh client có đọc Location. Nếu business thực sự dùng header này, thay implementation bằng **toEntity(Book.class)** hoặc loại phản hồi có headers và assert tương ứng.
- Test 404 kiểm tra đúng exception subtype trong cấu hình Spring ví dụ; custom status handler có thể đổi exception thành loại nghiệp vụ khác.

### 7.2 Test WebClient bằng MockWebServer thật trên loopback

**src/test/java/demo/CatalogWebClientTest.java**:

~~~java
package demo;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import static org.junit.jupiter.api.Assertions.*;

class CatalogWebClientTest {

    private MockWebServer server;
    private CatalogWebClient catalog;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        WebClient client = WebClient.builder()
            .baseUrl(server.url("/").toString())
            .build();

        catalog = new CatalogWebClient(client);
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void getUsesHttpTransportAndParsesJson() throws Exception {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"id\":7,\"title\":\"Spring\"}"));

        Book book = catalog.find(7, "en")
            .block(Duration.ofSeconds(5));

        assertEquals(new Book(7, "Spring"), book);

        RecordedRequest req = server.takeRequest(5, TimeUnit.SECONDS);
        assertNotNull(req);
        assertEquals("GET", req.getMethod());
        assertEquals("/api/books/7?lang=en", req.getPath());
        assertEquals("training", req.getHeader("X-Tenant"));
    }

    @Test
    void postEncodesJsonRequest() throws Exception {
        server.enqueue(new MockResponse()
            .setResponseCode(201)
            .addHeader("Content-Type", "application/json")
            .addHeader("Location", "/api/books/8")
            .setBody("{\"id\":8,\"title\":\"New Book\"}"));

        Book book = catalog.create(new CreateBook("New Book"))
            .block(Duration.ofSeconds(5));

        assertEquals(new Book(8, "New Book"), book);

        RecordedRequest req = server.takeRequest(5, TimeUnit.SECONDS);
        assertNotNull(req);
        assertEquals("POST", req.getMethod());
        assertEquals("/api/books", req.getPath());
        assertEquals("training", req.getHeader("X-Tenant"));
        assertTrue(req.getHeader("Content-Type")
            .startsWith("application/json"));
        assertEquals("{\"title\":\"New Book\"}",
            req.getBody().readUtf8());
    }

    @Test
    void notFoundProducesReactiveError() throws Exception {
        server.enqueue(new MockResponse().setResponseCode(404));

        assertThrows(
            WebClientResponseException.NotFound.class,
            () -> catalog.find(404, "vi")
                .block(Duration.ofSeconds(5)));

        RecordedRequest req = server.takeRequest(5, TimeUnit.SECONDS);
        assertNotNull(req);
        assertEquals("/api/books/404?lang=vi", req.getPath());
    }
}
~~~

**Lưu ý test này đang kiểm tra đúng HTTP request thực:**
- **server.start()** cấp cổng localhost ngẫu nhiên.
- **baseUrl(server.url("/").toString())** bảo đảm WebClient gửi đúng vào server giả, không gọi catalog.example.test.
- **server.enqueue** chuẩn bị response cho lần gọi tương ứng.
- **Mono.block(Duration)** subscribe và chờ kết quả trong *JUnit test thread*, không phải WebFlux event-loop.
- **takeRequest(5, TimeUnit.SECONDS)** tránh đợi vô hạn khi không có request.
- **getMethod, getPath, getHeader, getBody().readUtf8()** là dữ liệu HTTP server giả ghi lại sau khi thật sự nhận request.
- **@AfterEach** đóng socket của mock server, tránh rò rỉ cổng/thread.
- Với HTTP POST, kiểm soát cả **body request** lẫn **body response**: một test chỉ assert Book trả về có thể vẫn bỏ sót bug client gửi title sai.

Mã JUnit kiểm tra JSON body POST dưới dạng chuỗi chính xác vì DTO trong demo có một field ổn định và Jackson tạo JSON đơn giản. Với payload có nhiều field có thể thay đổi thứ tự, nên parse JSON bằng ObjectMapper/JsonNode rồi so sánh cấu trúc thay vì string raw.

### 7.3 Cách chạy và kết quả kỳ vọng

Trong thư mục **client-http-contract-tests**, cài JDK 17+ và Maven rồi chạy:

~~~bash
mvn test
~~~

Dự án có **6 phương thức @Test**, gồm ba test RestClient và ba test WebClient. Khi dependencies, JDK và network loopback khả dụng, test phải hoàn thành với **0 failures** và **0 errors**, Maven **BUILD SUCCESS**. Đây là tiêu chí kỳ vọng của ví dụ; không giả định đã chạy Maven trong bất kỳ môi trường nào chỉ vì code xuất hiện trong README.

Nếu test fail:
- Xem stacktrace JUnit xác định assertion/HTTP call đầu tiên thất bại.
- Với MockRestServiceServer, kiểm tra client có được xây dựng từ đúng RestClient.Builder đã bind không.
- Với MockWebServer, kiểm tra URL localhost, enqueue trước khi subscribe, timeout lấy RecordedRequest và response Content-Type.
- Kiểm tra Maven dependency và version Spring nếu phương thức API không có mặt.

## 8. Kiểm thử lỗi, timeout và retry một cách có kiểm soát

### 8.1 Error response từ server giả

RestClient test có thể dùng:

~~~java
server.expect(requestTo(
        "https://catalog.example.test/api/books/7?lang=en"))
    .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE)
        .contentType(MediaType.APPLICATION_JSON)
        .body("{\"error\":\"temporarily unavailable\"}"));
~~~

WebClient test có thể dùng:

~~~java
server.enqueue(new MockResponse()
    .setResponseCode(503)
    .addHeader("Content-Type", "application/json")
    .setBody("{\"error\":\"temporarily unavailable\"}"));
~~~

Kỳ vọng mặc định là lỗi HTTP đi vào đường exception/error signal. Nếu application có logic retry **503**, test nên enqueue chuỗi đáp ứng (503 rồi 200), assert số lần gọi, và dùng policy retry có giới hạn. Không thiết kế test chạy retry vô tận.

### 8.2 Network timeout và phản hồi chậm

MockRestServiceServer thay transport bằng mock request factory, nên **không phù hợp để khẳng định TCP connect timeout hoặc read timeout thật**. MockWebServer có thể mô phỏng phản hồi chậm:

~~~java
server.enqueue(new MockResponse()
    .setResponseCode(200)
    .setBody("{\"id\":7,\"title\":\"Spring\"}")
    .setBodyDelay(2, TimeUnit.SECONDS)
    .addHeader("Content-Type", "application/json"));
~~~

Đây là fragment để minh họa **setBodyDelay**; để test xác định, phải cấu hình timeout trên **WebClient HTTP connector hoặc pipeline Reactor** ở mức nhỏ hơn delay, rồi assert đúng error type. Nếu không có timeout ở ứng dụng, server chậm hai giây vẫn có thể trả thành công. Tránh dùng **Thread.sleep()** chỉ để đoán network conditions; mock server đã có khả năng điều khiển độ trễ.

Một ví dụ WebClient pipeline với application timeout:

~~~java
Mono<Book> result = catalog.find(7, "en")
    .timeout(Duration.ofMillis(200));
~~~

Lúc subscribe có thể xuất hiện **TimeoutException** (được Reactor bọc vào hệ thống error signal) khi không có giá trị trong 200 ms. Nhưng thời gian ngắn có thể flaky trên CI chậm; dùng margin rõ ràng và timeout ở network connector khi muốn test đúng tầng. Cần huỷ tác vụ và cleanup server sau test.

### 8.3 Retry và idempotency

Nếu retry là một phần hợp đồng, ví dụ GET idempotent:

~~~java
Mono<Book> result = catalog.find(7, "en")
    .retryWhen(
        Retry.backoff(1, Duration.ofMillis(100))
            .filter(error ->
                error instanceof WebClientResponseException.ServiceUnavailable));
~~~

Fragment này cần import **reactor.util.retry.Retry**, **java.time.Duration**, và loại WebClientResponseException. Khi dùng MockWebServer, enqueue **503** và **200** theo thứ tự rồi assert có đúng **hai RecordedRequest**. Với RestClient, retry thường ở service layer, Resilience4j hoặc HTTP client policy; MockRestServiceServer có **ExpectedCount.times(2)** để kiểm số request nếu ứng dụng thật sự retry.

Không retry POST tạo tài nguyên vô điều kiện: remote server có thể đã tạo resource nhưng client mất kết nối trước khi nhận response. Cần idempotency key hoặc cơ chế chống trùng trước khi thử retry.

## 9. Kiểm chứng JSON và headers ở cả hai phía

Có bốn lớp assertions không nên trộn lẫn:

| Lớp | Khi dùng MockRestServiceServer | Khi dùng MockWebServer |
| --- | --- | --- |
| Request method + URI | method(...), requestTo(...) | RecordedRequest.getMethod(), getPath() |
| Request headers | header(...), content().contentType(...) | RecordedRequest.getHeader(...) |
| Request JSON body | content().json(expected) | RecordedRequest.getBody() và JSON parser |
| Response status/headers/body | andRespond(...) tạo stub; client assert kết quả/exception | enqueue(...) tạo stub; client assert kết quả/exception |

**Nhớ chiều dữ liệu**:
- **Expect/RecordedRequest** là những gì client **gửi đến server**.
- **Stub response** là những gì server giả **trả về client**.
- **Assert kết quả Java** chứng minh code client đã giải mã response/hành xử theo status.

Ví dụ test status 201 và Location chỉ thực sự bảo vệ việc client đọc Location nếu client trả cả **ResponseEntity<T>** hay expose response header. Nếu implementation chỉ **body(T.class)**, test có thể xác nhận HTTP POST body và DTO nhưng **không thể** khẳng định Location đã được ứng dụng sử dụng.

### JSON có field động

Với response chứa timestamp, request ID hoặc array không bảo đảm thứ tự:
- Assert những trường bắt buộc, kiểu và constraints có ý nghĩa.
- Tránh hard-code timestamp thực, random UUID hoặc request ID thay đổi.
- Với request body, sử dụng **ObjectMapper.readTree(...)** để so sánh JSON structural nếu thứ tự keys không quan trọng.
- Với binary/multipart, so sánh Content-Type, part names, boundary và bytes theo hợp đồng; đừng chuyển file tùy tiện thành String UTF-8.

## 10. Nhiều request, concurrency và isolation

### MockRestServiceServer

- **Một mock server/RestClient.Builder riêng cho mỗi test** giúp tránh expectation state bị tái sử dụng.
- **server.verify()** phải được gọi để xác nhận đủ số lần request, kể cả khi kết quả Java đã đúng.
- Mặc định test sắp xếp expectations theo thứ tự; nếu concurrency làm thứ tự không có contract, dùng **ignoreExpectOrder(true)** hoặc test cô lập từng luồng.
- **ExpectedCount** xác định số lần request, nhưng không dùng nó để thay thế việc kiểm tra headers và body mỗi loại request.

### MockWebServer

- **Một instance per test** (hoặc per test class với cleanup nghiêm ngặt), đóng socket bằng **shutdown()**.
- Enqueue responses theo thứ tự; test gọi song song nhiều request có thể tiêu thụ response queue theo thứ tự khác với dự đoán. Khi cần routing theo path/header, dùng **Dispatcher** tùy biến hoặc WireMock stubs.
- Tránh giữ request cũ trong queue sang test mới. Luôn **takeRequest** với timeout hữu hạn.
- Một test dùng HTTP server giả vẫn có race/timing nếu thiếu subscription hoặc chọn timeout quá thấp. Cần quản lý publisher lifecycle rõ ràng.
- Nếu test nhiều network failures, WebClient có thể retry hoặc connector tự reconnect tùy cấu hình: xác minh **số request thật** để phân biệt logic bị gọi dư.

### Đặt server giả vào base URL thế nào?

Một anti-pattern thường gặp:

~~~java
WebClient client = WebClient.create("https://api.company.com");
// Sau đó mới khởi tạo MockWebServer ở localhost.
// WebClient này vẫn gọi api.company.com, không tự chuyển hướng.
~~~

Cách đúng: tạo mock server trước, lấy URL của nó và truyền vào **WebClient.Builder.baseUrl(...)**. Trong Spring Boot project thật, inject base URL qua **@ConfigurationProperties** để cả production và test sử dụng cùng factory, test chỉ thay giá trị property.

Không buộc test lệ thuộc port 8080 hoặc chạy external service. Một port localhost ngẫu nhiên cho mỗi test giúp CI ổn định và cho phép nhiều test suites chạy song song.

## 11. Mock HTTP server với WireMock

**WireMock** cũng tạo HTTP mock server và mạnh về matching request, scenario/state, mapping theo query/header/JSON, fault simulation và recording. Hữu ích khi:
- Cần nhiều endpoint/stubs và HTTP body phức tạp.
- Mock API theo tiêu chí path/query/auth rất chi tiết.
- Muốn quản lý fixtures JSON riêng, scenario 429 → 200, hoặc tích hợp vào các test suites.
- Test RestClient và WebClient với cùng một HTTP stub server, thay vì dùng MockRestServiceServer chỉ cho RestClient.

Ví dụ minh họa WireMock style:

~~~java
stubFor(get(urlPathEqualTo("/api/books/7"))
    .withQueryParam("lang", equalTo("en"))
    .withHeader("X-Tenant", equalTo("training"))
    .willReturn(okJson("{\"id\":7,\"title\":\"Spring\"}")));
~~~

Đây là **fragment**, cần dựng WireMockServer, cấu hình base URL của WebClient trỏ tới server đó, import DSL đúng phiên bản WireMock và dọn tài nguyên khi xong. Không copy nguyên fragment vào demo MockWebServer ở mục 7 vì đó là hai thư viện độc lập. Khi test cần verification:

~~~java
verify(getRequestedFor(urlPathEqualTo("/api/books/7"))
    .withQueryParam("lang", equalTo("en")));
~~~

WireMock giả lập HTTP response thật ở localhost nên có đặc tính transport tương tự hướng MockWebServer. Chọn một công cụ mock server chính cho một test suite để tránh hai nguồn fixture chồng chéo.

## 12. HTTP service interface cũng kiểm thử được

Nếu ứng dụng Spring dùng declarative **@HttpExchange** interface tạo bằng **HttpServiceProxyFactory**, vẫn nên kiểm tra HTTP contract:

~~~java
@HttpExchange(url = "/api/books")
interface BookApi {
    @GetExchange("/{id}")
    Book find(@PathVariable("id") long id);
}
~~~

Với sync interface:
1. Tạo **RestClient.Builder** và bind **MockRestServiceServer** trước khi build RestClient.
2. Tạo **RestClientAdapter.create(restClient)**, **HttpServiceProxyFactory.builderFor(adapter)** và proxy **createClient(BookApi.class)**.
3. Đăng ký expectations, gọi proxy, assert Book và **verify()**.

Với reactive interface trả **Mono<Book>**:
1. Tạo **MockWebServer** hoặc WireMock.
2. Tạo **WebClient** với base URL của server giả và **WebClientAdapter.create(webClient)**.
3. Tạo proxy cho interface reactive, subscribe/StepVerifier, kiểm **RecordedRequest** và giá trị response.

Như vậy test vẫn xác nhận **annotation mapping, URI template, headers và JSON** do proxy sinh ra. Mock trực tiếp BookApi bằng Mockito chỉ kiểm tra business logic gọi interface, chưa xác minh annotation/proxy transport.

## 13. Các lỗi thường gặp và cách khắc phục

| Dấu hiệu | Nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| MockRestServiceServer không nhận được request | RestClient được build trước khi bind hoặc từ builder khác | Bind đúng RestClient.Builder trước build |
| Test chạm Internet dù tưởng đã mock | URL/client chưa trỏ mock server đúng | In/kiểm baseUrl, xác nhận RecordedRequest |
| **verify()** báo expected but not executed | Không gọi code thực sự hoặc số lần kỳ vọng sai | Gọi service, assert số request |
| Test POST fail JSON dù semantics đúng | So raw JSON string và thứ tự fields/whitespace khác | Dùng content().json hoặc parse JsonNode |
| MockWebServer **takeRequest** timeout | Mono không subscribe, URL sai hoặc connector lỗi | block/StepVerifier, server.url, kiểm exception |
| WebClient nhận Codec/JSON decode error | Response thiếu Content-Type JSON hoặc schema sai | Thêm header đúng, tạo body phù hợp DTO |
| HTTP 404 bị xem như giá trị null | Mặc định retrieve() phát lỗi status | Test exception/error signal và custom handler nếu có |
| Test timeout không bao giờ xảy ra | Chỉ delay server nhưng không đặt timeout client | Đặt timeout ở connector hoặc Reactor phù hợp |
| Test timeout flaky | Timeout quá ngắn, CI chậm, test dùng sleep | Dùng mock delay có margin và bounded wait |
| Test nhận sai response giả | Nhiều concurrent requests tiêu thụ enqueue khác thứ tự | Dùng Dispatcher/WireMock matching theo URI |
| HTTP request dư sau retry | Client có retry hoặc logic bị gọi nhiều lần | Verify call counts, inspect recorded requests |
| Không đọc được response Location | Implementation chỉ bodyToMono/body(...), bỏ headers | Dùng toEntity/ResponseEntity |
| Mất kết nối sau test | Không gọi server.shutdown | Dùng @AfterEach/finally |
| Test nhanh pass nhưng production vẫn fail TLS | MockRestServiceServer không có transport; localhost khác prod | Thêm kiểm thử integration/cấu hình TLS khi cần |

## 14. Checklist triển khai trong dự án

1. Xác định điều đang kiểm: logic client, URI/headers/JSON, status handling hay network conditions.
2. Với **RestClient/RestTemplate đồng bộ**, ưu tiên **MockRestServiceServer** cho HTTP contract test nhanh, xác định.
3. Với **WebClient**, dùng **MockWebServer/WireMock** để chạy HTTP transport thật ở localhost.
4. Cấu hình cùng **RestClient.Builder** trước khi build; WebClient phải lấy base URL từ URL động của mock server.
5. Khai báo expectation/stub response trước khi gọi service; với WebClient phải có subscription.
6. Kiểm tra đầy đủ request method, URL/query, header, content-type và body, rồi assert response DTO/status/error.
7. Verify số lần gọi, retry, headers và cleanup tài nguyên. Đừng chỉ assert kết quả Java.
8. Tạo test 2xx, 4xx, 5xx, malformed JSON và network delay theo chính sách nghiệp vụ.
9. Tách HTTP mock test khỏi end-to-end environment test; mock server không thể chứng minh remote API production luôn tuân hợp đồng.

### Câu hỏi ôn tập

- Tại sao MockRestServiceServer.bindTo(RestClient.Builder) phải được gọi trước khi builder.build()?
- Vì sao test WebClient có thể timeout ở takeRequest khi ta đã tạo Mono nhưng chưa subscribe?
- MockRestServiceServer khác MockWebServer về lớp transport như thế nào?
- Nếu POST trả JSON chính xác nhưng Location sai, test hiện tại có bắt được lỗi không? Vì sao?
- Làm sao kiểm tra WebClient retry một GET sau 503 mà không cho retry vô hạn?
- Khi nhiều request song song tới MockWebServer, vì sao enqueue FIFO có thể thành source of flakiness?
- Nếu mock một HTTP service interface bằng Mockito, những phần nào của @HttpExchange chưa được kiểm thử?

## Tài liệu chính thức

- [Spring Framework – Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html)
- [Spring Framework – Testing WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html)
- [MockRestServiceServer Javadoc 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html)
- [RestClient (Spring Framework)](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [WebClient (Spring Framework)](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [OkHttp MockWebServer 4.12.0 (Maven Central)](https://central.sonatype.com/artifact/com.squareup.okhttp3/mockwebserver/4.12.0)
- [WireMock Documentation](https://wiremock.org/docs/)
