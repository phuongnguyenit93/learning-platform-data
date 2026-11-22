# HTTP tích hợp trong Spring Boot: cấu hình base URL từ RANDOM_PORT, không gắn cứng port

## 1. Vấn đề và mục tiêu

Integration test HTTP phải gửi request tới **embedded server thật** đang được Spring Boot khởi chạy, không chỉ gọi trực tiếp controller hoặc gửi request qua MockMvc. Nhiều ví dụ đơn giản viết `http://localhost:8080` vào test; cách này chỉ đúng khi server thật luôn chạy trên cổng 8080. Trong CI, các test có thể chạy song song, cổng 8080 có thể đang bị chiếm hoặc context chỉ được tạo cho môi trường test; kết quả là `Connection refused`, truy cập nhầm một ứng dụng khác, hoặc test phụ thuộc máy developer.

Giải pháp chuẩn là dùng:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApiHttpIntegrationTest {

    @LocalServerPort
    int port;
}
```

Spring Boot khởi động **server thật** với một cổng còn trống do hệ điều hành chọn; sau khi server đã chạy, `@LocalServerPort` cung cấp **số cổng thực tế** cho test. Từ đó test dựng base URL ở đúng vòng đời và đưa vào client HTTP: Java 17 `HttpClient`, `WebTestClient`, Rest Assured, hoặc dùng `TestRestTemplate` đã được Spring Boot cấu hình root URI sẵn.

### Kết quả cần đạt

- Chọn đúng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và lấy port runtime thay vì giả định 8080.
- Phân biệt `server.port=0` (yêu cầu chọn cổng ngẫu nhiên) với `local.server.port` (cổng thực tế sau khi mở server).
- Tạo base URI đúng **scheme + host + port + context path**, không ghép sai dấu `/` hoặc encode query string không an toàn.
- Biết dùng HTTP client tự tạo và client Spring Boot tự cấu hình.
- Viết test kiểm tra HTTP status, JSON body và lỗi 4xx qua socket thật; không chỉ assert context khởi động.
- Hiểu giới hạn của transaction rollback, context cache, management port, HTTPS và chạy song song.
- Không tạo test flaky bằng một lần gọi tới port cố định, không dùng `Thread.sleep` để “đợi server”.

Bài này có ví dụ **Java 17, Spring Boot 3.5.0, Maven, JUnit Jupiter** hoàn chỉnh và có thể chạy độc lập. Một số API của Spring Boot 4 được đề cập riêng vì hạ tầng HTTP test client của Boot 4 đã được tổ chức lại.

## 2. Vì sao RANDOM_PORT an toàn hơn 8080?

So sánh:

| Cấu hình | Server thật? | Cổng | Khi nào sử dụng |
| --- | --- | --- | --- |
| `@SpringBootTest` mặc định | **Không** (web environment `MOCK` nếu có web stack) | Không có HTTP listening port | Test context/wiring, có thể phối hợp MockMvc |
| `@SpringBootTest(webEnvironment=RANDOM_PORT)` | **Có** | Port do OS chọn khi server start | Integration test HTTP thật, nhất là CI |
| `@SpringBootTest(webEnvironment=DEFINED_PORT)` | **Có** | `server.port` đã cấu hình hoặc mặc định 8080 | Hệ thống yêu cầu thật sự một cổng xác định |
| `@SpringBootTest(webEnvironment=NONE)` | **Không** | Không có web server | Batch/non-web integration |
| `@WebMvcTest` + MockMvc | Không mở socket TCP | Không có real port | Controller/MVC slice |
| `@WebFluxTest` + WebTestClient mock-bound | Không mở socket TCP | Không có real port | WebFlux slice |

Spring Boot cung cấp `WebEnvironment.RANDOM_PORT` bằng cách yêu cầu server dùng `server.port=0`. Trong networking, cổng 0 là chỉ thị **hãy cấp một cổng còn trống**; đó **không phải** cổng mà client phải gọi.

**Sai:**

```java
// Không nên viết trong HTTP integration test:
URI url = URI.create("http://localhost:8080/api/ping");

// Cũng sai: server.port có thể là giá trị 0 để xin random port.
@Value("${server.port}")
int actualPort;
```

**Đúng:**

```java
@LocalServerPort
int port;  // Cổng HTTP đã được cấp sau khi server khởi động.

@BeforeEach
void initializeUrl() {
    String baseUrl = "http://127.0.0.1:" + port;
}
```

Hai đoạn sau chỉ minh họa cách cấu hình; project chạy được ở mục 8–11. `@LocalServerPort` nằm trong package `org.springframework.boot.test.web.server.LocalServerPort` ở Spring Boot 3.5 và là lối tắt tương đương với inject `@Value("${local.server.port}")`.

### Không khẳng định “random port khác 8080”

OS chọn cổng theo tình trạng máy. Trong đa số trường hợp bạn sẽ thấy số khác 8080, nhưng test **không được assert** `port != 8080` vì lựa chọn đó không nằm trong hợp đồng và vẫn có thể trùng. Chỉ cần xác nhận `port > 0`, request đến server vừa khởi động, response đúng contract.

### Lợi ích khi CI chạy song song

Nếu worker A và worker B đều khởi động ứng dụng ở port 8080, worker đến sau có thể fail khi bind socket. RANDOM_PORT để OS phân phối các cổng khác nhau cho các server **đang mở đồng thời**. Cách này giảm xung đột port, nhưng **không tự cô lập database, filesystem, message broker, static state hoặc server management port**. Các tài nguyên đó cần chính sách riêng.

## 3. Vòng đời @LocalServerPort: khi nào có giá trị?

Cơ chế ngắn gọn:

```mermaid
flowchart TD
    A[Test runner tạo Spring TestContext] --> B[SpringApplication tạo ApplicationContext]
    B --> C[Embedded server bind port = 0]
    C --> D[OS cấp một local TCP port thực tế]
    D --> E[Boot công bố local.server.port]
    E --> F[Inject @LocalServerPort vào test instance]
    F --> G[@BeforeEach xây URI và HTTP client]
    G --> H[Gửi HTTP request tới server]
    H --> I[Assert status, headers, JSON và side effects]
```

`local.server.port` chỉ có ý nghĩa **sau khi embedded web server đã được khởi tạo**. Vì vậy:

- Dùng `@LocalServerPort` trong **test class**, và xây URI tại test method hoặc `@BeforeEach` là rõ ràng.
- Không tạo `static final String BASE_URL = "http://localhost:" + port;` từ một field chưa được inject.
- Không đọc `local.server.port` trong static initializer của application hoặc trong bean factory method chạy trước server start.
- Không dùng `@BeforeAll static` để tham chiếu instance field `port` theo giả định nó đã có sẵn.
- Không hard-code cổng in từ log lần chạy trước vào file cấu hình.
- Không dùng `@DynamicPropertySource` một cách ngây thơ để đọc cổng server ứng dụng qua static method **trước khi server khởi động**; cơ chế đó chủ yếu dành cho giá trị động của dependency như Testcontainers đã được chuẩn bị đúng lifecycle.

Có thể inject port qua constructor/test method parameter nếu Spring/JUnit test extension và annotation đúng, nhưng cách field + `@BeforeEach` dễ đọc hơn cho người mới.

### Phân biệt server.port và local.server.port

| Key | Ý nghĩa | Thời điểm |
| --- | --- | --- |
| `server.port` | Cổng ứng dụng **được yêu cầu** bind; `0` có nghĩa random | Trước lúc mở socket |
| `local.server.port` | Cổng ứng dụng **thực sự** bind được | Sau lúc embedded server đã start |
| `management.server.port` | Cổng management endpoint được yêu cầu (nếu cấu hình riêng) | Trước khi management server start |
| `local.management.port` | Cổng management server thực tế (khi có riêng) | Sau khi management server start |

Spring Boot có `@LocalManagementPort` để truy cập management port thực tế khi management server nằm trên port riêng (cần dependency/cấu hình Actuator). **Không** lấy `@LocalServerPort` rồi mặc định nó là port Actuator trong mọi cấu hình.

## 4. Base URL hợp lệ là gì?

Một base URL cho HTTP integration thường gồm:

```text
scheme://host:port[/context-path]
http://127.0.0.1:52741
https://localhost:54443
http://127.0.0.1:52741/shop
```

Các phần cần phân biệt:

| Thành phần | Nguồn | Lưu ý |
| --- | --- | --- |
| `scheme` | HTTP hay HTTPS được server test cấu hình | Nếu bật TLS thì dùng `https` và trust/cert phù hợp |
| `host` | Địa chỉ interface mà server bind | Với test local thường `localhost` hoặc `127.0.0.1` |
| `port` | `@LocalServerPort` | Không hard-code/đọc server.port=0 |
| `context path` | Servlet: `server.servlet.context-path` | Cần cộng path chính xác; không được mất `/shop` |
| `reactive base path` | WebFlux: `spring.webflux.base-path` khi cấu hình | Không nhầm với Servlet context path |
| `endpoint path` | Route của controller | Có hoặc không có dấu `/` đầu, tùy cách xây URI |
| Query values | Input của test | Encode qua URI builder hoặc công cụ tương đương |

Ví dụ servlet app cấu hình `server.servlet.context-path=/shop` thì route controller `/api/ping` phải gọi tại **`/shop/api/ping`**. Không dùng `URI.resolve("/api/ping")` trên base URI chứa `/shop/` nếu muốn giữ prefix `/shop`: một path bắt đầu bằng `/` trong `URI.resolve` sẽ thay phần path của base.

### URI.resolve và dấu gạch chéo

```java
URI root = URI.create("http://127.0.0.1:52741/shop/");

URI ok = root.resolve("api/ping");
// http://127.0.0.1:52741/shop/api/ping

URI losesPrefix = root.resolve("/api/ping");
// http://127.0.0.1:52741/api/ping
```

Đây là đoạn minh họa Java chuẩn, không cần Spring, và các URI trong comment thể hiện kết quả định dạng chuẩn. Để tránh lỗi, chuẩn hóa base URL ở một nơi và chọn một cách ghép path duy nhất, hoặc dùng `UriComponentsBuilder`.

### Encode query parameter

Sai:

```java
String name = "Lan & An";
// Dấu & bị hiểu thành phân tách query parameters nếu ghép thẳng.
String path = "/api/greet?name=" + name;
```

Một cách với Java 17:

```java
String encoded = URLEncoder.encode(
        "Lan & An", StandardCharsets.UTF_8);
URI uri = URI.create(baseUrl + "/api/greet?name=" + encoded);
```

`URLEncoder` dùng encoding kiểu HTML form, trong đó dấu cách thành `+`; với query parameter của Spring MVC thông thường, `+` được giải mã thành space. Nó **không** phải cách tổng quát để encode một path segment; nếu path có tên chứa `/`, `%` hay non-ASCII, dùng URI builder theo đúng cấu trúc path/query.

Với Spring URI builder:

```java
URI uri = UriComponentsBuilder
        .fromUriString(baseUrl)
        .path("/api/greet")
        .queryParam("name", "Lan & An")
        .build()
        .encode()
        .toUri();
```

Đây là đoạn minh họa cần import `org.springframework.web.util.UriComponentsBuilder`. Trong project mẫu sẽ dùng cả query encoding với JDK và URI builder thông qua WebTestClient.

## 5. Ba lựa chọn HTTP client phổ biến

### 5.1. TestRestTemplate: đơn giản nhất cho Boot 3.x servlet integration

Spring Boot cung cấp `TestRestTemplate` và tự cấu hình khi `@SpringBootTest` khởi chạy embedded server. Ở Boot 3.5:

```java
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class ExampleTest {
    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void testEndpoint() {
        ResponseEntity<String> response =
                restTemplate.getForEntity("/api/ping", String.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
    }
}
```

Đây là đoạn minh họa; ví dụ chạy được có imports đầy đủ ở mục 10. Điểm cần nhớ: `"/api/ping"` là **relative URL**. `TestRestTemplate` đã được cấu hình hướng tới server test và cổng random, nên thông thường **không phải dựng base URL thủ công**.

`TestRestTemplate` còn có tính chất hữu ích: phản hồi 4xx/5xx **không tự động ném exception** theo cách error handler mặc định của `RestTemplate` thường làm; test nhận `ResponseEntity` và assert status/body. Đây là một điểm khác biệt quan trọng khi kiểm thử nhánh lỗi.

Không nên tạo `new TestRestTemplate()` thủ công rồi cho rằng instance tự biết port của Spring server. Khả năng tự cấu hình chỉ có khi dùng bean do test context cung cấp (hoặc bạn cấu hình root URI cho instance theo cách có chủ đích).

### 5.2. WebTestClient: fluent assertions, hỗ trợ MVC/server và reactive streams

Khi `spring-webflux` và các HTTP client dependencies phù hợp có trên test classpath, có thể dùng `WebTestClient`. Theo tài liệu Spring Boot 3.5, với `RANDOM_PORT` Boot có thể cung cấp `WebTestClient` đã hướng tới server để dùng relative path:

```java
@Autowired
WebTestClient client;

// Ví dụ:
client.get().uri("/api/ping")
        .exchange()
        .expectStatus().isOk();
```

Với **client tự tạo**, phải bind đúng server:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:" + port)
        .responseTimeout(Duration.ofSeconds(5))
        .build();
```

Không nhầm `WebTestClient.bindToServer()` với `bindToController(...)` hoặc `bindToApplicationContext(...)`. Hai cách sau có thể chạy qua mock exchange không mở network, nên **không chứng minh socket HTTP thật**.

Với Spring Boot servlet MVC, thêm `spring-boot-starter-webflux` **test scope** vào project nếu muốn có WebTestClient + Reactor Netty HTTP client; Spring Boot thường ưu tiên MVC khi cả MVC và WebFlux cùng nằm trên classpath. Đừng thêm WebFlux vào production chỉ vì cần client test.

### 5.3. Java 17 HttpClient: không phụ thuộc client test của Spring

Java `java.net.http.HttpClient` có sẵn từ Java 11, được dùng với Java 17:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create(baseUrl + "/api/ping"))
    .timeout(Duration.ofSeconds(5))
    .GET()
    .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
assertEquals(200, response.statusCode());
```

Đây là đoạn minh họa cần imports. `connectTimeout` giới hạn lúc thiết lập kết nối (không phải tất cả các bước HTTP); `HttpRequest.Builder.timeout` là timeout request; test vẫn cần assertion về nội dung và status.

JDK HttpClient hữu ích khi muốn tránh lệ thuộc package test client giữa Boot 3 và Boot 4. Nhưng phải tự xây URI, đặt headers, serialize JSON và xử lý response. Nếu có authentication, TLS, cookie hoặc redirect policy, hãy cấu hình rõ; không vô hiệu hóa TLS certificate verification để làm test PASS.

### So sánh nhanh

| Client | Port runtime được xử lý thế nào? | Điểm mạnh | Cần chú ý |
| --- | --- | --- | --- |
| `TestRestTemplate` auto-wired | Tự dùng root URI tới server test; gọi path `/api/...` | Đơn giản, 4xx không ném theo mặc định | Đây là API Boot 3.x, kiểm tra phiên bản khi nâng |
| `WebTestClient` auto-wired | Boot 3.5 có thể tự nối tới RANDOM_PORT khi classpath phù hợp | Fluent status/header/body assertions, streaming | Cần `spring-webflux`; phân biệt mock-bound và real-bound |
| `WebTestClient.bindToServer()` | Tự tạo `baseUrl("http://...:"+port)` | Kiểm soát timeout/client rõ ràng | Không dùng `bindToController` nếu muốn HTTP thật |
| JDK `HttpClient` | Tự tạo URI từ `@LocalServerPort` | Không thêm dependency test HTTP client | Tự decode JSON và xử lý status |
| Rest Assured | Gán `port(port)` hoặc base URI per request | Cú pháp DSL cho HTTP | Cần dependency, tránh global mutable `RestAssured.port` khi chạy song song |

## 6. Tạo base URL ở đúng lifecycle

Một cách thiết kế test rõ ràng:

```java
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class ProductHttpTest {
    @LocalServerPort
    int port;

    private String baseUrl;

    @BeforeEach
    void setUp() {
        assertTrue(port > 0);
        baseUrl = "http://127.0.0.1:" + port;
    }
}
```

Đây là đoạn minh họa. `@BeforeEach` chạy khi Spring test context và server đã được thiết lập, do đó có cổng runtime. Test instance mặc định của JUnit Jupiter được tạo theo method; mỗi method có thể tự xây URL/client mà không dựa vào trạng thái static.

Không khuyến nghị lưu URL và port vào **static global state** dùng chung suite rồi thay đổi chúng ở nhiều test classes. Khi context bị reload bằng `@DirtiesContext` hoặc chạy nhiều Spring applications cùng lúc, static URL cũ có thể trỏ tới một server đã đóng hoặc sang port của class khác.

### Dùng helper nhỏ thay vì copy/paste ghép port

```java
static URI baseUri(int port) {
    if (port <= 0 || port > 65535) {
        throw new IllegalArgumentException(
                "expected an allocated TCP port");
    }
    return URI.create("http://127.0.0.1:" + port);
}
```

Đây là hàm Java có thể copy vào test utility nếu nhiều tests cần. Nhưng test helper không nên tạo một server riêng hoặc tự tìm free port bằng `new ServerSocket(0)` rồi đóng socket và cố bắt ứng dụng dùng port đó: cách đó có **race condition** giữa lúc tìm port và lúc server bind. Giao việc cấp cổng cho embedded server/OS thông qua `RANDOM_PORT` an toàn hơn.

### Chọn localhost hay 127.0.0.1?

`localhost` có thể được resolve thành IPv4 `127.0.0.1` hoặc IPv6 `::1` tùy môi trường. Trong ví dụ này dùng `127.0.0.1` để biểu diễn IPv4 loopback và giả định embedded server test chấp nhận kết nối IPv4 (mặc định thường đúng). Nếu ứng dụng chỉ bind IPv6, interface cụ thể hoặc `server.address` khác, điều chỉnh base URI tương ứng. Với IPv6 literal phải dùng ngoặc vuông, ví dụ `http://[::1]:52741`.

Không tự dùng `0.0.0.0` làm host client: đó là địa chỉ bind trên server, **không phải đích kết nối** cho HTTP client.

## 7. Cấu hình phục vụ test và an toàn môi trường

Trong Boot 3.5, có thể dùng:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class RealApiTest {
    // ...
}
```

Tệp `src/test/resources/application-test.properties`:

```properties
spring.main.banner-mode=off
logging.level.org.springframework.web=WARN
```

Không cần ghi `server.port=0` vào file test khi đã dùng `RANDOM_PORT` vì chính annotation đặt yêu cầu port random. Nếu viết property khác như `server.port=8080` ở một nguồn config có precedence cao làm thay đổi thực tế, hãy kiểm tra annotation/property sources và cổng **thực** qua `@LocalServerPort`, không suy đoán từ file.

**Không để app test kết nối production.** Khi ứng dụng có database, Redis, Kafka, payment gateway hoặc SMTP, cần test profile/tài nguyên giả lập/sandbox/Testcontainers phù hợp. Việc chạy server ở random local port không tự bảo vệ các outbound calls mà ứng dụng thực hiện.

### Scheme khi chạy HTTPS

Nếu bật `server.ssl.enabled=true` và chỉ chấp nhận HTTPS, base URL phải dùng `https://...:<port>`. Ngoài scheme, test client cần trust certificate đúng cách. Chứng chỉ self-signed có thể được cấu hình bởi test truststore; đừng tắt verify hostname/certificate một cách vô điều kiện.

### Context path

Nếu Servlet MVC app có:

```properties
server.servlet.context-path=/shop
```

thì URI hợp lệ sẽ là `http://127.0.0.1:<port>/shop/api/ping`. Base URL cho client tự tạo có thể là `http://127.0.0.1:<port>/shop/`, sau đó nối relative path `api/ping` (không có leading slash). Với WebFlux, base-path property là `spring.webflux.base-path`, không phải Servlet `server.servlet.context-path`.

**Không vô tình thêm prefix hai lần**. Có client tự thêm root URI và test lại nối toàn bộ URL? Chọn một cách rõ ràng: hoặc dùng TestRestTemplate relative path đã chứa context path cần thiết, hoặc dựng URI tuyệt đối bằng `@LocalServerPort` cho HTTP client tự tạo.

### Management port và Actuator

Spring Boot có thể chạy Actuator management endpoints trên port khác main application nếu `management.server.port` được cấu hình khác. Với RANDOM_PORT, management server có thể được cấp cổng ngẫu nhiên riêng. `@LocalServerPort` là cổng **application**, không phải luôn là cổng management. Khi test `/actuator/health`, kiểm tra cấu hình expose endpoint và dùng `@LocalManagementPort` nếu cần cổng quản lý riêng. Một test `/api/ping` trên app port không chứng minh Actuator endpoint hoạt động.

## 8. Project Maven/Java 17 hoàn chỉnh

Để tránh cấu hình database hoặc async infrastructure làm phân tán chủ đề, ứng dụng mẫu có ba endpoint **stateless**:

- `GET /api/ping` → HTTP 200, JSON `{"status":"up"}`.
- `GET /api/greet?name=Lan` → HTTP 200, JSON `{"message":"Xin chào, Lan"}`; nếu tên rỗng/whitespace trả 400.
- `POST /api/messages` với JSON `{"text":"  hello  "}` → HTTP 201, JSON `{"text":"hello"}`.

Trong project test, sẽ có ba lớp kiểm thử sử dụng cùng embedded server:

1. `TestRestTemplateRandomPortTest`: bean tự định tuyến root URL, relative request, nhánh HTTP 400.
2. `JdkHttpClientRandomPortTest`: lấy cổng thực tế, tạo base URI ở `@BeforeEach`, thử query có dấu cách/`&`/Unicode và POST JSON.
3. `WebTestClientRandomPortTest`: tự `bindToServer().baseUrl(...)`, kiểm tra status và JSON bằng fluent API.

### 8.1. Cây tệp

```text
random-port-demo/
├── pom.xml
└── src/
    ├── main/java/example/randomport/
    │   ├── RandomPortApplication.java
    │   └── ApiController.java
    └── test/
        ├── resources/application-test.properties
        └── java/example/randomport/
            ├── TestRestTemplateRandomPortTest.java
            ├── JdkHttpClientRandomPortTest.java
            └── WebTestClientRandomPortTest.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>example</groupId>
    <artifactId>random-port-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <!-- Chỉ phục vụ WebTestClient trong test.
             Bao gồm client stack Reactor Netty. MVC vẫn được Boot ưu tiên. -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Lý do thêm `spring-boot-starter-webflux` ở **test scope**: trong Spring Boot 3.5, `WebTestClient` cần `spring-webflux` và HTTP client connector thực tế. Starter WebFlux kéo đầy đủ các phần cần thiết, còn production app vẫn chỉ phụ thuộc MVC starter. Nếu dự án chỉ dùng `TestRestTemplate` và `HttpClient`, bỏ dependency WebFlux test đi là hợp lý.

Cả Maven dependency versions đều do Boot parent/BOM quản lý. Khi nâng Boot major, không tự trộn Spring Framework hoặc Reactor version khác nhau.

### 8.3. Application class

`src/main/java/example/randomport/RandomPortApplication.java`:

```java
package example.randomport;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RandomPortApplication {
    public static void main(String[] args) {
        SpringApplication.run(RandomPortApplication.class, args);
    }
}
```

Đặt các lớp trong cùng package `example.randomport` hoặc package con để component scanning mặc định nhận controller. Với test classes cùng package, Boot sẽ tìm được application configuration.

### 8.4. ApiController.java

`src/main/java/example/randomport/ApiController.java`:

```java
package example.randomport;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class ApiController {

    public record PingResponse(String status) {}
    public record GreetingResponse(String message) {}
    public record MessageRequest(String text) {}
    public record MessageResponse(String text) {}

    @GetMapping("/ping")
    public PingResponse ping() {
        return new PingResponse("up");
    }

    @GetMapping("/greet")
    public GreetingResponse greet(@RequestParam String name) {
        if (name.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "name must not be blank");
        }
        return new GreetingResponse("Xin chào, " + name.strip());
    }

    @PostMapping("/messages")
    public ResponseEntity<MessageResponse> createMessage(
            @RequestBody MessageRequest request) {
        if (request.text() == null || request.text().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "text is required");
        }
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new MessageResponse(request.text().strip()));
    }
}
```

Mã dùng Java records để giảm boilerplate, tương thích Java 17/Jackson ở Boot 3.5. Tất cả endpoint là **stateless**, không có database để test không phụ thuộc thứ tự hoặc cleanup dữ liệu. HTTP 400 là chính sách controller định nghĩa; không khẳng định mọi input invalid trong Boot mặc nhiên có cùng body.

### 8.5. application-test.properties

`src/test/resources/application-test.properties`:

```properties
spring.main.banner-mode=off
logging.level.org.springframework.web=WARN
```

Cố ý **không** cấu hình `server.port=8080` hoặc `server.port=0` trong file. `@SpringBootTest(webEnvironment=RANDOM_PORT)` sẽ yêu cầu port random. Không có external services hoặc secrets.

## 9. TestRestTemplateRandomPortTest.java: dùng relative URL

`src/test/java/example/randomport/TestRestTemplateRandomPortTest.java`:

```java
package example.randomport;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class TestRestTemplateRandomPortTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void relativePathAutomaticallyUsesStartedServer() {
        assertTrue(port > 0);

        ResponseEntity<ApiController.PingResponse> response =
                restTemplate.getForEntity(
                        "/api/ping",
                        ApiController.PingResponse.class);

        assertEquals(200, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals("up", response.getBody().status());
    }

    @Test
    void badInputReturnsHttp400RatherThanThrowingClientError() {
        ResponseEntity<String> response =
                restTemplate.getForEntity(
                        "/api/greet?name=",
                        String.class);

        assertEquals(400, response.getStatusCode().value());
    }
}
```

**Giải thích:** bean `TestRestTemplate` được tự động cấu hình cho embedded server test đang chạy. Request dùng `"/api/ping"` và `"/api/greet?name="`, không nhắc số cổng trong source. Test vẫn nhận `@LocalServerPort` để minh họa **đã có cổng runtime**, nhưng không cần ghép nó vào URL vì bean đã giải quyết root URI.

`TestRestTemplate` mặc định không ném exception khi response là 4xx/5xx; method thứ hai kiểm tra đúng status. Đối với `RestTemplate` thông thường, error handler mặc định có thể ném `HttpClientErrorException` thay vì trả response bình thường; đừng lẫn hai client.

**Không** khẳng định `getRootUri()` của mọi `TestRestTemplate` luôn cung cấp đúng chuỗi base URL theo một format cố định: implementation có thể dùng `UriTemplateHandler` nội bộ. Điều nên kiểm chứng là một relative request thật sự đến ứng dụng đang chạy.

## 10. JdkHttpClientRandomPortTest.java: tự dựng URL

`src/test/java/example/randomport/JdkHttpClientRandomPortTest.java`:

```java
package example.randomport;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class JdkHttpClientRandomPortTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private String baseUrl;
    private HttpClient client;

    @BeforeEach
    void setUp() {
        assertTrue(port > 0);
        baseUrl = "http://127.0.0.1:" + port;
        client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    @Test
    void encodedQueryIsDeliveredToRealServer() throws Exception {
        String name = "Mỹ & An";
        String encoded = URLEncoder.encode(
                name, StandardCharsets.UTF_8);
        URI url = URI.create(
                baseUrl + "/api/greet?name=" + encoded);

        HttpRequest request = HttpRequest.newBuilder(url)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());

        JsonNode json = mapper.readTree(response.body());
        assertEquals("Xin chào, Mỹ & An",
                json.path("message").asText());
    }

    @Test
    void jsonPostReturns201OverRealHttp() throws Exception {
        URI url = URI.create(baseUrl + "/api/messages");
        HttpRequest request = HttpRequest.newBuilder(url)
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"text\":\"  hello  \"}"))
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(201, response.statusCode());

        JsonNode json = mapper.readTree(response.body());
        assertEquals("hello", json.path("text").asText());
    }

    @Test
    void unknownEndpointReturns404FromThisServer()
            throws Exception {
        URI url = URI.create(baseUrl + "/api/not-here");
        HttpRequest request = HttpRequest.newBuilder(url)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(404, response.statusCode());
    }
}
```

Lợi ích:

- Cả ba test dùng đúng cổng được `@LocalServerPort` inject sau startup.
- `URLEncoder` ngăn dấu `&` trong tên trở thành query separator; test xác minh server trả đúng Unicode.
- POST dùng JSON body thật, content type rõ và assert 201 + trường trong response.
- Test 404 xác minh server đã nhận request nhưng endpoint không tồn tại, không phải `Connection refused` do gọi sai port.
- `connectTimeout` và request `timeout` giúp CI fail có giới hạn thay vì chờ mãi khi server/connectivity có vấn đề.

Trong thực tế, có thể tạo một `HttpClient` dùng chung **cho mỗi test class** để giảm overhead, miễn không để headers/cookies/state gây ảnh hưởng giữa test methods. Bài này tạo client trong `@BeforeEach` để minh họa lifecycle rõ.

## 11. WebTestClientRandomPortTest.java: bindToServer với baseUrl

`src/test/java/example/randomport/WebTestClientRandomPortTest.java`:

```java
package example.randomport;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class WebTestClientRandomPortTest {

    @LocalServerPort
    int port;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        assertTrue(port > 0);

        client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    @Test
    void relativeGetUsesConfiguredBaseUrl() {
        client.get()
                .uri(uriBuilder -> uriBuilder
                        .path("/api/greet")
                        .queryParam("name", "Lan Anh")
                        .build())
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                            MediaType.APPLICATION_JSON)
                .expectBody()
                    .jsonPath("$.message")
                    .isEqualTo("Xin chào, Lan Anh");
    }

    @Test
    void postCanCheckStatusAndJsonWithoutHardcodedPort() {
        client.post()
                .uri("/api/messages")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(
                        new ApiController.MessageRequest("  hello  "))
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                    .jsonPath("$.text")
                    .isEqualTo("hello");
    }
}
```

`WebTestClient.bindToServer()` dùng kết nối HTTP thật; `baseUrl` lấy trực tiếp từ cổng được cấp. Nếu test chủ yếu dùng Spring WebFlux, cách tiếp cận này cũng áp dụng khi Spring Boot khởi động reactive server.

Vì demo có cả `spring-boot-starter-web` và WebFlux starter **test scope**, Spring Boot thường chọn Servlet MVC application type. WebTestClient chỉ là HTTP client, không biến controller MVC thành WebFlux controller. Trong Boot 3.5, nếu đủ WebFlux client dependencies, có thể `@Autowired WebTestClient` trong `RANDOM_PORT` test và dùng relative URI mà không cần tự `bindToServer`; ví dụ ở đây cố ý dựng thủ công để minh họa base URL.

Không gọi `WebTestClient.bindToController(...)` nếu mục tiêu là kiểm tra cổng của server thật: phương thức đó bind tới mock WebFlux exchange và sẽ không kiểm chứng network socket.

## 12. Chạy dự án và expected results

Yêu cầu **JDK 17+**, Maven và quyền tải dependencies từ repository lần đầu. Từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Chạy riêng từng nhóm:

```bash
mvn test -Dtest=TestRestTemplateRandomPortTest
mvn test -Dtest=JdkHttpClientRandomPortTest
mvn test -Dtest=WebTestClientRandomPortTest
```

Có **7 test methods**:

| Class | Số test | Điều kiểm chứng |
| --- | --- | --- |
| `TestRestTemplateRandomPortTest` | 2 | Relative URL tự tới random-port server; 400 trả dưới dạng response |
| `JdkHttpClientRandomPortTest` | 3 | URL runtime/Unicode query/JSON POST/404 qua HTTP thật |
| `WebTestClientRandomPortTest` | 2 | Explicit base URL bindToServer, GET/POST contract |
| **Tổng** | **7** | Không cần database, Docker hay port cố định |

Kết quả **dự kiến 7 PASS, 0 FAIL, 0 SKIPPED** với môi trường phù hợp. Đây là expected behavior theo source, không phải stdout được ghi cứng. Maven có thể in port dạng `Tomcat started on port 52741` hoặc một số khác **mỗi lần khởi động context**; không assert số cổng từ log. Các test không gọi `System.out.println`, vì vậy không có stdout ứng dụng cố định. Xem `target/surefire-reports` để xác nhận test count thật.

### Một ví dụ thành công

Giả sử OS cấp port 52741 (chỉ là ví dụ, không phải giá trị kỳ vọng cố định):

```text
Test context starts embedded server on http://127.0.0.1:52741
Test sends GET http://127.0.0.1:52741/api/ping
Response: HTTP 200
Body: {"status":"up"}
```

Điều duy nhất test cần biết là **response** từ server vừa được khởi động, không phải con số port. Context có thể được tái sử dụng trong cùng JVM test suite; port không nhất thiết đổi giữa các classes hay mỗi test method.

## 13. Test REST Assured nếu dự án đang dùng công cụ này

Rest Assured hỗ trợ DSL tiện cho HTTP integration. Một đoạn **minh họa**, cần `io.rest-assured:rest-assured` test dependency và imports:

```java
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class RestAssuredHttpTest {
    @LocalServerPort
    int port;

    @Test
    void checksPing() {
        given()
            .baseUri("http://127.0.0.1")
            .port(port)
        .when()
            .get("/api/ping")
        .then()
            .statusCode(200)
            .body("status", equalTo("up"));
    }
}
```

Ưu tiên **baseUri và port trên request specification** thay vì thay đổi biến global mutable `RestAssured.port = port` hay `RestAssured.baseURI` trong nhiều tests chạy song song. Nếu team dùng global config, phải có scope và teardown rõ ràng.

REST Assured có thể chạy qua HTTP thật nhưng không tự biết cổng từ `@SpringBootTest`. Bạn vẫn cần `@LocalServerPort`/inject runtime port hoặc một integration riêng có cơ chế tự cấu hình đã được chứng minh.

## 14. Dùng @BeforeEach, @BeforeAll hay constructor injection?

| Cách | Có nên dùng? | Điều cần chú ý |
| --- | --- | --- |
| `@LocalServerPort` field và build base URL ngay trong test method | Có | Đơn giản nhất, không có state dùng chung |
| `@BeforeEach` build base URL/client | Có | Sau Spring TestContext injection, rõ vòng đời |
| Test constructor nhận `@LocalServerPort int port` | Có thể | Cần đúng test extension/parameter resolver, phù hợp design class |
| `@BeforeAll static` đọc instance `port` | Không | Chưa có instance field hoặc không hợp lệ về Java |
| `static final` URL ghép từ port của test | Không | Port chưa được cấp lúc static initialization |
| Bean production dùng `@Value("${local.server.port}")` lúc startup | Không phù hợp | Actual port chỉ biết sau server initialization |
| Tự chọn port bằng cách lấy `ServerSocket(0)` rồi đóng trước khi start | Tránh | Race giữa “lấy free port” và bind thật |
| `@DirtiesContext` để đổi port sau từng method | Thường không cần | Tăng startup cost, không phải test isolation tự động |

### Context cache và nhiều classes

Spring TestContext cache context theo merged configuration. Nếu ba test classes trong demo có context key tương đương, có thể dùng chung một application context và cùng random port. Vì vậy:

- Không assert port khác nhau giữa `TestRestTemplateRandomPortTest` và `WebTestClientRandomPortTest`.
- Không lưu port vào static field rồi dùng ở một class khác vì cache eviction, fork JVM hoặc `@DirtiesContext` có thể làm nó thay đổi.
- Nếu test thay đổi bean/context thật sự và cần `@DirtiesContext`, client phải dựng lại URL sau context restart.
- Cache là tối ưu hiệu năng, **không** đồng nghĩa dữ liệu singleton/DB đã được reset.

Khi chạy Maven/Gradle với nhiều forks, mỗi JVM có thể có context cache riêng và tạo server trên port riêng. Đây là hành vi bình thường.

## 15. Transaction và dữ liệu khi gửi HTTP thật

Tài liệu Spring Boot lưu ý: với `RANDOM_PORT`/`DEFINED_PORT`, HTTP client và server xử lý ở các thread/transactions riêng. Nếu test method gắn `@Transactional`, rollback transaction trong **test thread** không rollback những thay đổi server đã commit.

Ví dụ cảnh báo:

```java
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Transactional
class UnsafeAssumptionTest {
    @Test
    void shouldNotAssumeServerWritesAreRolledBack() {
        // Gửi POST qua HttpClient tới server.
        // Transaction của server có thể commit độc lập.
        // Rollback test method KHÔNG tự xóa các rows đó.
    }
}
```

Đây là **đoạn minh họa, không phải test độc lập**. Dự án mẫu ở mục 8 cố ý stateless, nên không có database cleanup. Với ứng dụng thật:

- Test tạo dữ liệu có correlation ID riêng, rồi cleanup đúng record của chính test.
- Với transaction/DB test chạy cùng suite, dùng schema/database/container riêng hoặc transaction cleanup có kiểm soát.
- Không dùng `repository.deleteAll()` trong teardown nếu những tests khác có thể đang chia sẻ DB.
- Nếu request POST timeout trước khi client lấy được ID, server có thể đã commit; cleanup cần dựa vào test identifier chứ không phụ thuộc response duy nhất.
- Không dùng `@Rollback(false)` toàn suite mà thiếu cleanup.
- Nếu chỉ muốn kiểm tra controller mapping không cần HTTP thật, dùng `@WebMvcTest`/MockMvc để tránh setup server và transaction ngoài mục tiêu.

Điểm cốt lõi là **port đúng không có nghĩa môi trường test đã cô lập toàn bộ side effects**.

## 16. HTTPS, proxy và security

### HTTPS

Bài mẫu dùng HTTP local. Nếu app bật TLS:

- Base URL phải đổi sang `https://localhost:<port>` hoặc địa chỉ certificate phù hợp.
- Cần test keystore/truststore hợp lệ; HTTPS có thể FAIL vì trust certificate dù server đã mở đúng port.
- Không tắt hostname verification trên toàn bộ client chỉ vì chứng chỉ test chưa đúng.
- Nếu proxy/ingress là thành phần yêu cầu, `RANDOM_PORT` trên loopback chưa chứng minh hạ tầng đó làm việc đúng.

### Spring Security

Khi có `spring-boot-starter-security`, các endpoint có thể yêu cầu login/CSRF/token theo config. HTTP integration test dùng client thật phải gửi credentials đúng (header Bearer/Basic/cookie/CSRF nếu contract yêu cầu). Không tắt security để test pass rồi gọi đó là bằng chứng endpoint đã an toàn.

Với `TestRestTemplate` có cách cấu hình Basic Auth; với HttpClient có thể thêm headers; với WebTestClient có `headers(...)` hoặc mutators/test support phù hợp. Đặt credentials giả/sandbox trong test profile hoặc CI secrets, không hard-code production token.

### Host và network

Test `RANDOM_PORT` thường chạy trong cùng máy/process, nên `127.0.0.1` hợp lý. Nếu server được bind vào container/remote network, host và port có thể được ánh xạ lại; `@LocalServerPort` chỉ báo cổng của server trong môi trường Boot, không nhất thiết là **published port** nhìn từ host khác. Khi test ứng dụng trong Docker container từ một runner ở bên ngoài, dùng mapped port/host do Testcontainers hoặc môi trường cung cấp, không dùng một URL loopback sai không gian mạng.

## 17. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Connection refused localhost:8080` | Hard-code 8080 dù test chạy random port | Lấy `@LocalServerPort` hoặc dùng TestRestTemplate relative URL |
| `port=0` trong log/URI | Dùng `server.port` thay cho `local.server.port` | Inject cổng thực tế sau startup |
| `Could not resolve placeholder 'local.server.port'` | Test không có server thật hoặc đọc giá trị quá sớm | Dùng RANDOM_PORT, đọc ở test lifecycle |
| Null/zero port trong static initializer | Static khởi chạy trước DI/server | Dời sang `@BeforeEach` |
| `@LocalServerPort` không có hiệu lực | Dùng `@SpringBootTest` mặc định MOCK | Chọn RANDOM_PORT/DEFINED_PORT |
| `TestRestTemplate` không autowire được | Không chạy embedded-server test hoặc dependency không đúng | Dùng Boot 3 test starter và RANDOM_PORT |
| TestRestTemplate relative URL gọi sai path | Có context path chưa được thêm | Thêm prefix đúng hoặc dựng absolute URI |
| `WebTestClient` không compile | Thiếu `spring-webflux` test dependency | Thêm WebFlux test client dependencies phù hợp |
| WebTestClient chạy nhưng không mở server thật | Dùng `bindToController`/mock-bound client | `bindToServer` và runtime base URL |
| HTTP GET trả 404 ở path đã khai báo | Context path, prefix, route hoặc URL resolve sai | Kiểm tra endpoint path và base URI |
| Query chứa `&` bị tách thành nhiều params | Nối query string mà không encode | Dùng `URLEncoder`/URI builder |
| HTTPS request fail với certificate | Truststore/hostname không phù hợp | Cấu hình chứng chỉ test đúng |
| Test chạy riêng PASS, CI song song FAIL | Port cố định hoặc shared DB/file/static resource | RANDOM_PORT + isolation tài nguyên |
| `@Transactional` nhưng DB còn row sau POST | Server transaction tách test thread | Cleanup theo test-owned data |
| Test request timeout dù server đã start | Client đọc sai host/port hoặc server xử lý chậm | Kiểm tra URL runtime, timeouts và logs |
| Test fail do random port “không đổi” giữa methods | Context cache dùng lại server | Bỏ assert port phải thay đổi |
| `@LocalServerPort` trả app port, actuator ở port khác | Management server được cấu hình riêng | Dùng management port thực nếu test Actuator |
| Test Boot 4 dùng import TestRestTemplate cũ | Test clients reorganize | Dùng RestTestClient + focused test modules của Boot 4 |

### Debug từng bước, không đoán

1. Xác nhận test có `@SpringBootTest(webEnvironment=RANDOM_PORT)`.
2. Xác nhận embedded server đã khởi động thành công; nếu context fail, đọc deepest `Caused by`.
3. Kiểm tra `port > 0` sau injection, không ghi vào source config.
4. Kiểm tra **scheme, host, context path và endpoint path** đã đúng.
5. Tách lỗi connect/socket khỏi response HTTP 404/400/500: nhận HTTP status chứng tỏ **có server** đã phản hồi, nhưng phải kiểm tra server đúng bằng response contract.
6. Kiểm tra client deadline/truststore, authentication và headers.
7. Kiểm tra build tool có chạy test thật và dependency test client tương thích.
8. Với lỗi flake, thử chạy nhiều test classes cùng suite/parallel để tìm static state/shared resources thay vì đổi sang fixed port.

## 18. Spring Boot 4: không copy nguyên test client từ Boot 3

Các đoạn runnable trong bài nhắm **Spring Boot 3.5.0**. Ở Spring Boot 4, reference hiện hành hướng tới `RestTestClient` (Spring Framework) kết hợp `@AutoConfigureRestTestClient` và các focused test starters, thay vì mặc định hướng dẫn `TestRestTemplate` như Boot 3.x. Những điều sau vẫn giữ nguyên về mặt ý nghĩa:

- `@SpringBootTest(webEnvironment=RANDOM_PORT)` khởi động server thật, cổng do OS cấp.
- `@LocalServerPort` lấy cổng ứng dụng ở runtime.
- Client được Boot auto-config có thể dùng relative URI theo đúng test setup.
- Client tự tạo vẫn phải bind base URL theo cổng thực tế.
- Bài kiểm tra HTTP thật cần phân biệt transaction client/server.

Khi nâng version, kiểm tra test dependency, package/import của client, Boot test auto-configuration và JUnit/Spring Framework versions. **Không** chỉ đổi `<version>3.5.0</version>` thành 4.x rồi giả định `TestRestTemplate`/WebTestClient imports hoạt động giống hệt.

JDK `HttpClient` trong bài vẫn là lựa chọn độc lập với các module test client của Spring, nên hữu ích để phân biệt vấn đề Boot bootstrap với vấn đề URL.

## 19. Checklist kiểm tra cuối bài

- [ ] Test cần HTTP thật và có `@SpringBootTest(webEnvironment=RANDOM_PORT)`?
- [ ] Không sử dụng `localhost:8080` hoặc fixed port trong test request?
- [ ] Hiểu `server.port=0` chỉ là yêu cầu random, không phải actual port?
- [ ] `@LocalServerPort` được inject sau server startup?
- [ ] Base URL dựng ở `@BeforeEach` hoặc test method, không ở static initializer?
- [ ] Scheme HTTP/HTTPS, host, port và context path được kết hợp chính xác?
- [ ] Query/path chứa Unicode hoặc dấu `&`/`/` được encode đúng?
- [ ] Với TestRestTemplate, biết khi nào dùng relative URI và cách kiểm tra 4xx?
- [ ] Với WebTestClient, phân biệt bindToServer và bindToController/bindToApplicationContext?
- [ ] Với HttpClient, dùng request timeout và assert status/body thật?
- [ ] Không assert port thay đổi giữa mỗi method/class vì context cache?
- [ ] Không assert cổng ngẫu nhiên nhất định phải khác 8080?
- [ ] Management port riêng được phân biệt với application port?
- [ ] Nếu có database, HTTP-server commit không bị giả định rollback theo test thread?
- [ ] Data/file/broker ngoài được cô lập hoặc cleanup có chủ đích?
- [ ] Không kết nối production từ test profile hoặc làm lộ credentials?
- [ ] Test không tắt TLS/security chỉ để lấy status 200?
- [ ] CI có test count thật, port không conflict và không chờ vô hạn?
- [ ] Khi dùng Boot 4, đã cập nhật HTTP test client/module/import đúng phiên bản?

## 20. Tài liệu tham khảo chính thức

1. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, webEnvironment, random port, `@LocalServerPort`, TestRestTemplate/WebTestClient, transaction caveat.
2. [Spring Boot 3.5 — @LocalServerPort API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/server/LocalServerPort.html): injection thông qua `local.server.port`.
3. [Spring Boot 3.5 — WebEnvironment API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.WebEnvironment.html): RANDOM_PORT, MOCK, DEFINED_PORT, NONE.
4. [Spring Boot 3.5 — TestRestTemplate API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html): fault-tolerant HTTP client, status 4xx/5xx và relative URIs.
5. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): `bindToServer`, `baseUrl`, response assertions.
6. [Spring Framework — UriComponentsBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html): dựng URI/query/path an toàn.
7. [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): so sánh HTTP clients được khuyến nghị trên Boot 4.
8. [JUnit Jupiter User Guide](https://docs.junit.org/5.13.4/writing-tests/): `@BeforeEach`, test lifecycle, assertions và reports.
9. [Java 17 HTTP Client API](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `HttpClient`, `HttpRequest` và `HttpResponse`.

**Ghi nhớ:** `RANDOM_PORT` yêu cầu Spring Boot mở HTTP server trên **cổng do OS cấp**; `@LocalServerPort` cung cấp **cổng thực tế sau startup**. Với client tự tạo, dựng base URL từ cổng này; với `TestRestTemplate` auto-wired của Boot 3.5, có thể dùng relative URL vì Boot đã cấu hình root URI. Kiểm thử thành công là test gửi request đến **đúng server vừa khởi động** và assert **status/body/side effects**, không phải chỉ in được một số port.
