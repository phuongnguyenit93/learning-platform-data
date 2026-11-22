# @GetExchange, @PostExchange và ánh xạ tham số phương thức trong Spring HTTP Service Client

## 1. Bài học giải quyết vấn đề gì?

Khi một service Java thường xuyên gọi HTTP API, cách viết thủ công với `RestClient.get().uri(...).retrieve()` hoặc `WebClient.post().bodyValue(...).retrieve()` có thể lặp lại ở nhiều nơi. **HTTP Service Client** của Spring Framework cho phép mô tả các endpoint bên ngoài bằng **Java interface có annotation**, sau đó Spring tạo proxy tự xây và thực hiện HTTP request mỗi khi bạn gọi phương thức tương ứng.

Trọng tâm bài này:

- `@GetExchange` biểu diễn request HTTP **GET**; `@PostExchange` biểu diễn HTTP **POST**.
- `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@CookieValue`, `@RequestBody` và `@RequestPart` quyết định tham số Java được đặt ở **đâu** trong HTTP request.
- `@HttpExchange` định nghĩa cấu hình chung, `HttpServiceProxyFactory` biến interface thành client chạy được, thông qua `RestClientAdapter` hoặc `WebClientAdapter`.
- Chọn giá trị trả về đồng bộ/reactive, xử lý lỗi, và tránh những hiểu lầm khi dùng các annotation giống annotation của Spring MVC controller.

Phạm vi ví dụ chính: **Java 17+, Spring Framework 6.1.x (Spring Boot 3.3.x)**. HTTP Service Client có từ Spring Framework 6.0; `RestClient` và cách khởi tạo `HttpServiceProxyFactory.builderFor(...)` được dùng dưới đây phù hợp với Spring 6.1+. Những tiện ích mới hơn của Spring 7 có thể khác; không cần chúng cho bài này.

## 2. Luồng hoạt động: interface → proxy → HTTP request

```text
Mã nghiệp vụ: notesApi.find(42, "vi", "req-123")
   │
   ▼
Proxy tạo bởi HttpServiceProxyFactory
   │  Đọc @GetExchange và annotation từng tham số
   ├─ GET + URL "/notes/{id}" → "/notes/42"
   ├─ @RequestParam("lang")   → "?lang=vi"
   └─ @RequestHeader("X-Trace-Id") → HTTP header
   │
   ▼
RestClientAdapter hoặc WebClientAdapter
   │
   ▼
RestClient / WebClient → HTTP transport → máy chủ
   │
   ▼
Response → decode → kiểu trả về khai báo trên interface
```

**Cần phân biệt:**

1. Annotation trên interface **mô tả yêu cầu HTTP**. Nó không tự mở socket hay chạy server.
2. `HttpServiceProxyFactory.createClient(YourInterface.class)` tạo đối tượng proxy; khi gọi phương thức, proxy sẽ tạo request từ metadata của phương thức và argument thực tế.
3. `RestClientAdapter` dùng API đồng bộ `RestClient`; `WebClientAdapter` dùng client reactive `WebClient`. Interface không bị khóa vào một thư viện HTTP cụ thể, nhưng **kiểu trả về** phải phù hợp adapter.
4. Các annotation `@GetExchange`, `@PostExchange` đều là dạng chuyên biệt của `@HttpExchange`. Đây là **client-side contract**; mặc dù Spring cho phép một số interface dùng chung cho controller, bài này tập trung vào phía **gọi API**.

## 3. Khai báo endpoint với @HttpExchange, @GetExchange và @PostExchange

Ví dụ một dịch vụ ghi chú:

```java
package demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

@HttpExchange(url = "/api/v1", accept = MediaType.APPLICATION_JSON_VALUE)
public interface NotesHttpClient {

    @GetExchange("/notes/{id}")
    NoteDto find(
            @PathVariable("id") long id,
            @RequestParam("lang") String language,
            @RequestHeader("X-Trace-Id") String traceId);

    @PostExchange(
            url = "/notes",
            contentType = MediaType.APPLICATION_JSON_VALUE)
    NoteDto create(
            @RequestBody CreateNoteRequest request,
            @RequestHeader("X-Trace-Id") String traceId);
}

record NoteDto(long id, String text) {}
record CreateNoteRequest(String text) {}
```

Đây là **minh họa contract**: DTO phải được đặt ở vị trí Java truy cập được; cần JSON codec/message converter (ví dụ Jackson) ở runtime. Chương trình chạy độc lập đầy đủ nằm tại mục 8.

Đọc declaration theo thứ tự:

- `@HttpExchange(url="/api/v1", accept="application/json")` ở **cấp interface** áp dụng cấu hình chung cho các phương thức: tiền tố đường dẫn và định dạng response mong đợi qua header `Accept`.
- `@GetExchange("/notes/{id}")` chọn HTTP method GET và nối đường dẫn với tiền tố. `{id}` là URI template variable cần điền từ `@PathVariable("id")`.
- `@PostExchange(url="/notes", contentType="application/json")` chọn POST, chỉ định `Content-Type` của request có body.
- `accept` diễn đạt định dạng **response muốn nhận**; `contentType` diễn đạt định dạng **request body gửi đi**. Hai thuộc tính không đồng nghĩa. Nếu bên nhận hỗ trợ nhiều dạng, `accept` có thể chứa nhiều media types.
- `@GetExchange(value="/notes/{id}")` và `@GetExchange(url="/notes/{id}")` tương đương về đường dẫn; `value` là alias của `url`. Tương tự cho `@PostExchange`.

Các HTTP shortcut khác gồm `@PutExchange`, `@PatchExchange` và `@DeleteExchange`. Khi cần HTTP method cụ thể, dùng shortcut tương ứng giúp interface tự mô tả hơn so với `@HttpExchange(method="GET")`.

**HTTP semantics:** GET dùng để lấy thông tin, thường phải an toàn và idempotent; POST thường tạo tài nguyên hoặc kích hoạt thao tác thay đổi trạng thái. Việc gắn annotation **không khiến backend tự tuân thủ semantics**: chính API server phải thực hiện đúng. Không dùng GET để thực hiện giao dịch có side effect chỉ vì dễ gọi.

## 4. Bảng ánh xạ tham số Java sang vị trí của HTTP request

| Khai báo trong interface | Thành phần HTTP | Minh họa kết quả |
| --- | --- | --- |
| `@PathVariable("id") long id` | Thay `{id}` trong URL path | `/notes/42` |
| `@RequestParam("lang") String lang` | Query string (thông thường) | `?lang=vi` |
| `@RequestParam("tag") List<String> tags` | Nhiều query/form values cùng tên | `?tag=java&tag=spring` |
| `@RequestHeader("X-Trace-Id") String id` | Request header | `X-Trace-Id: req-123` |
| `@CookieValue("session") String token` | Request cookie | `Cookie: session=...` |
| `@RequestBody CreateNoteRequest body` | Toàn bộ request body | JSON khi cấu hình JSON |
| `@RequestPart("file") Resource file` | Một phần trong multipart body | `multipart/form-data` |
| `@RequestAttribute("key") Object attr` | Request attribute nội bộ client | Không tự biến thành header/query |
| `URI uri` (không annotation) | URL động, override URL annotation | URL runtime |
| `UriBuilderFactory factory` (không annotation) | Factory tạo URI cho invocation | Điều khiển base URL/encoding |
| `HttpMethod method` (không annotation) | Override HTTP method | Chỉ dùng khi thực sự cần động |

Các giá trị `String`, số, enum có thể được convert theo cơ chế Spring. `@RequestParam` và `@RequestHeader` có thể nhận `Collection`, `Map`, `MultiValueMap` với quy tắc phù hợp; hãy kiểm tra server có chấp nhận nhiều giá trị cùng tên hay không. `@PathVariable` cũng hỗ trợ map chứa nhiều biến đường dẫn.

**Cực kỳ quan trọng:** `@RequestParam` trong client không có nghĩa “tham số form” trong mọi tình huống. Với `Content-Type: application/x-www-form-urlencoded`, tham số được gửi ở **form body**; các request khác dùng query string. Không dựa vào tên annotation mà đoán vị trí vật lý.

### 4.1 @PathVariable: điền URI template

```java
@GetExchange("/users/{userId}/orders/{orderId}")
String getOrder(
        @PathVariable("userId") long userId,
        @PathVariable("orderId") String orderId);
```

Gọi `getOrder(15, "A-9")` tạo đường dẫn logic `/users/15/orders/A-9` (cộng tiền tố ở interface và base URL của client). Tên tham số `"userId"` và `"orderId"` phải khớp placeholder. Nếu mismatch, request có thể thất bại khi resolve URI; kiểm tra ngay trong test.

Nên **ghi rõ tên annotation** như `@PathVariable("userId")` thay vì `@PathVariable long userId` để không lệ thuộc cấu hình trình biên dịch giữ tên parameter (`-parameters`). Giá trị dynamic được URI template xử lý encoding; không tự nối chuỗi URL từ input tùy ý.

### 4.2 @RequestParam: query và form-urlencoded

GET thông dụng:

```java
@GetExchange("/books")
List<BookDto> search(
        @RequestParam("q") String keyword,
        @RequestParam("page") int page,
        @RequestParam(value = "lang", required = false) String language);
```

Gọi `search("spring web", 2, null)` có ý nghĩa query chứa `q=spring%20web&page=2` (biểu diễn percent-encoding thực tế tùy URI builder). `lang` không có khi giá trị được phép bỏ qua. Không khẳng định rằng mọi space nhất định được encode thành `%20`: một số chiến lược form/query có thể dùng `+`. Dùng `UriComponentsBuilder`/URI template thay cho nối `?q=` thủ công.

POST form:

```java
@PostExchange(
        url = "/oauth/token",
        contentType = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
String exchangeToken(
        @RequestParam("grant_type") String grantType,
        @RequestParam("code") String code);
```

Ở đây `grant_type` và `code` thuộc **body dạng form** (ví dụ `grant_type=authorization_code&code=abc`), **không phải JSON**. Với JSON body, dùng `@RequestBody` thay vì lạm dụng `@RequestParam`.

`@RequestParam("tag") List<String> tags` và `MultiValueMap<String, String>` hữu ích cho filter có nhiều giá trị; khả năng parse ở server phải được kiểm thử bằng request thật.

### 4.3 @RequestHeader và @CookieValue

```java
@GetExchange("/profile")
String profile(
        @RequestHeader("Authorization") String bearerToken,
        @RequestHeader("X-Request-Id") String requestId,
        @CookieValue("locale") String locale);
```

Header này **chỉ được gửi** theo argument khi gọi method; không có tự động đăng nhập. Ví dụ production thường thích cấu hình authorization trong `RestClient.Builder` interceptor hoặc `WebClient.Builder` filter / security integration, vì gửi raw token qua mọi method signature dễ lặp và dễ lộ trong log.

`@RequestHeader` trong HTTP interface có thể **thêm** giá trị vào header đã tồn tại ở client; đừng mặc định nó ghi đè header mặc định. Header lặp như `Authorization` có thể gây lỗi hoặc rủi ro; kiểm tra cấu hình thực tế. `@CookieValue` thêm Cookie phía client, không đọc cookie từ incoming request của server trừ khi ứng dụng chủ động chuyển tiếp.

### 4.4 @RequestBody: gửi toàn bộ entity

```java
record CreateUser(String name, String email) {}
record UserView(long id, String name) {}

@PostExchange(
        url = "/users",
        contentType = MediaType.APPLICATION_JSON_VALUE,
        accept = MediaType.APPLICATION_JSON_VALUE)
UserView createUser(@RequestBody CreateUser payload);
```

JSON serialized (với Jackson):

```http
POST /users HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Lan","email":"lan@example.org"}
```

`@RequestBody` xác định toàn bộ HTTP payload, không rải từng thuộc tính object thành query parameter. Payload `record` được encode bởi HTTP message converters (RestClient) hoặc codecs (WebClient). Nếu thiếu JSON codec, sai `Content-Type` hoặc server trả JSON không tương thích DTO, lỗi encode/decode có thể xuất hiện.

Với WebClient, `@RequestBody Mono<CreateUser>` cũng có thể gửi dữ liệu reactive; nhưng không dùng publisher/reactive return types với `RestClientAdapter` rồi kỳ vọng nó tự chuyển thành reactive.

### 4.5 @RequestPart: multipart upload

```java
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.service.annotation.PostExchange;

// Fragment bên trong HTTP service interface
@PostExchange(
        url = "/attachments",
        contentType = MediaType.MULTIPART_FORM_DATA_VALUE)
String upload(
        @RequestPart("description") String description,
        @RequestPart("file") Resource file);
```

`@RequestPart` ánh xạ *một phần* của multipart body, mỗi part có tên và có thể có Content-Type riêng. `Resource` thường đại diện file; `HttpEntity<?>` giúp đặt header riêng cho part; client hỗ trợ cũng có thể nhận `MultipartFile` hay Spring `Part` tùy adapter và phiên bản. Không dùng `@RequestBody` JSON thuần đồng thời với nhiều `@RequestPart` rồi kỳ vọng Spring tự ghép thành multipart. Cần kiểm tra giới hạn file size, streaming, bộ đệm và bảo vệ filename thực tế.

### 4.6 Tham số tùy chọn và giá trị null

Tham số không được tự do truyền `null`: framework cần biết annotation nào cho phép `required=false` hoặc tham số được xác định là optional (ví dụ `Optional<T>`). Nếu một field là tùy chọn, thể hiện rõ contract:

```java
@GetExchange("/books")
String list(@RequestParam(value = "category", required = false)
            String category);
```

Khi người dùng không chọn category, phương thức có thể nhận `null` và **bỏ qua** parameter này. Với dữ liệu bắt buộc, validate ở business boundary trước khi gọi HTTP client để phát hiện sớm hơn thay vì trông đợi proxy giải quyết ràng buộc nghiệp vụ.

## 5. Từ interface thành HTTP client thật với HttpServiceProxyFactory

HTTP interface **không được triển khai bằng `new NotesHttpClient()`**; cần proxy. Với Spring Framework 6.1 và `RestClient`:

```java
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

RestClient restClient = RestClient.builder()
        .baseUrl("https://notes.example.org")
        .defaultHeader("X-App", "learning")
        .build();

RestClientAdapter adapter = RestClientAdapter.create(restClient);
HttpServiceProxyFactory factory =
        HttpServiceProxyFactory.builderFor(adapter).build();

NotesHttpClient notes = factory.createClient(NotesHttpClient.class);
NoteDto note = notes.find(42L, "vi", "req-123");
```

Đây là fragment dành cho project đã có `NotesHttpClient` và `NoteDto` ở mục 3; `notes.example.org` chỉ là host minh họa, không chạy thật. **Lưu ý `builderFor(adapter)`:** đây là cách khởi tạo phù hợp Spring 6.1+, thay cho `HttpServiceProxyFactory.builder(adapter)` đã deprecated ở 6.1.

Trong Spring Boot, có thể đăng ký client proxy làm bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration
class RemoteNotesConfiguration {

    @Bean
    NotesHttpClient notesHttpClient(RestClient.Builder builder) {
        RestClient client = builder
                .baseUrl("https://notes.example.org")
                .build();

        return HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(client))
                .build()
                .createClient(NotesHttpClient.class);
    }
}
```

Đây là **Spring configuration fragment**. Inject `RestClient.Builder` do Boot quản lý để tận dụng các tùy chỉnh chung nếu có. Tái sử dụng bean proxy và underlying client; không dựng lại factory cho mỗi lần gọi. Chỉ định rõ base URL theo environment/configuration thực tế, timeout, TLS, authentication, log/metrics và retry phù hợp.

### Chọn WebClient khi cần reactive

```java
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;
import reactor.core.publisher.Mono;

interface ReactiveNotesClient {
    @GetExchange("/notes/{id}")
    Mono<String> find(@org.springframework.web.bind.annotation.PathVariable("id")
                      long id);
}

WebClient webClient = WebClient.builder()
        .baseUrl("https://notes.example.org")
        .build();

ReactiveNotesClient reactive =
        HttpServiceProxyFactory
                .builderFor(WebClientAdapter.create(webClient))
                .build()
                .createClient(ReactiveNotesClient.class);

Mono<String> publisher = reactive.find(42L);
```

Fragment trên dùng trong phương thức Java (không thể đặt các lệnh tạo biến rời rạc trực tiếp tại cấp file). Cần `spring-webflux` và HTTP connector phù hợp. `Mono<String>` là publisher: request thực tế chạy khi subscribe. Trong WebFlux handler, trả publisher; không tự `block()` trên event-loop. Với `RestClientAdapter`, signature kiểu `String`, `List<T>`, `ResponseEntity<T>` hoặc `void` là tự nhiên; với `WebClientAdapter`, hỗ trợ cả `Mono<T>` và `Flux<T>`.

## 6. Ánh xạ tham số: các tình huống dễ hiểu nhầm

| Tình huống | Code ý định | HTTP được sinh | Cách xử lý đúng |
| --- | --- | --- | --- |
| GET item theo id | `@GetExchange("/items/{id}")` + `@PathVariable("id")` | GET `/items/7` | Khớp chính xác tên biến |
| GET filter | `@RequestParam("sort")` | Query `?sort=newest` | Encode user input, không nối raw URL |
| POST JSON | `@PostExchange(contentType="application/json")` + `@RequestBody` | JSON ở body | Có JSON codec |
| POST HTML form | `@PostExchange(contentType="application/x-www-form-urlencoded")` + `@RequestParam` | Các cặp key=value ở body | Server phải parse form |
| POST upload | `@PostExchange(contentType="multipart/form-data")` + `@RequestPart` | Multipart body | Chỉ định part names đúng |
| Header động | `@RequestHeader("X-Trace-Id")` | HTTP header | Tránh duplicate / log secret |
| URL động | `URI uri` | URI runtime thay url tĩnh | Validate target host trước |

**Không nên suy luận các annotation giống hệt cơ chế xử lý argument của Spring MVC controller.** Đây là chiều **gửi request**, nên `@RequestBody` serialize để gửi (không deserialize request từ client); `@RequestHeader` thêm request header gửi đi (không đọc incoming header). Ngoài ra, không phải mọi annotation server-side như `@ModelAttribute` hay `@RequestMapping` có cùng ý nghĩa trên HTTP Service Client.

### Dynamic URI và method (trường hợp nâng cao)

```java
import java.net.URI;
import org.springframework.http.HttpMethod;
import org.springframework.web.service.annotation.HttpExchange;

interface DynamicClient {
    @HttpExchange(method = "GET", url = "/fallback")
    String exchange(URI uri, HttpMethod method);
}
```

Spring nhận `URI` và `HttpMethod` như hai parameter đặc biệt cho phép override URL/method đã khai báo. **Đừng đưa URI tùy ý từ client cuối vào thẳng method**: nguy cơ SSRF, gửi credential đến host lạ hoặc bỏ qua base URL dự kiến. Chỉ dùng khi endpoint cần chọn linh hoạt và có allowlist/validation.

### Khi cần custom argument mapping

Một tham số nghiệp vụ dạng `SearchCriteria` không mặc nhiên được Spring biến thành nhiều query fields. Có thể khai rõ từng `@RequestParam`, hoặc cài `HttpServiceArgumentResolver` trong `HttpServiceProxyFactory.Builder` khi pattern thực sự lặp lại. Một custom resolver phải nhận diện kiểu của tham số, chuyển thành dữ liệu request trên `HttpRequestValues.Builder` và trả `true` nếu đã xử lý; nếu không thì trả `false`. Đó là extension của **proxy**, không phải thay thế controller argument resolver.

## 7. Return type, lỗi HTTP và lifecycle

### 7.1 Return type theo adapter

| Loại backend | Return type HTTP Service method | Ý nghĩa |
| --- | --- | --- |
| `RestClientAdapter` | `String`, `BookDto`, `List<BookDto>` | Gọi đồng bộ và giải mã body |
| `RestClientAdapter` | `ResponseEntity<BookDto>` | Có status, headers, body |
| `RestClientAdapter` | `ResponseEntity<Void>` hoặc `void` | Chỉ quan tâm status/không cần body |
| `WebClientAdapter` | `Mono<BookDto>` | Một giá trị reactive |
| `WebClientAdapter` | `Flux<BookDto>` | Nhiều phần tử/stream reactive |
| `WebClientAdapter` | `Mono<ResponseEntity<BookDto>>` | Status/headers/body reactive |

Không khai báo `Flux<T>` với synchronous RestClient rồi trông chờ tự stream; không khai báo signature đồng bộ rồi gọi trên thread event-loop và kỳ vọng sẽ không block.

### 7.2 HTTP status và network failure

Mặc định `RestClient`/`WebClient` thường chuyển **4xx/5xx** thành lỗi khi HTTP Service method xử lý response. Với RestClient, có thể đặt `defaultStatusHandler(...)`; với WebClient, cấu hình `defaultStatusHandler(...)` hoặc filter trên client nền. Các lỗi DNS, connect, timeout, TLS là **transport failure**, không phải response 404/500 và cần chiến lược xử lý khác.

Hãy chú ý:

- 404 đôi khi là “không tìm thấy” bình thường; dùng `ResponseEntity` hoặc status handler khi contract cần trả empty/null thích hợp thay vì lan mọi lỗi.
- Không retry mù quáng POST tạo tài nguyên khi chưa có idempotency key; có thể tạo trùng nếu request đầu tiên đã thành công nhưng response bị mất.
- Timeout, connection pool, proxy, TLS, logging và observability nằm ở cấu hình underlying RestClient/WebClient/HTTP engine, **không phải** thuộc tính của `@GetExchange`.
- `@RequestHeader("Authorization")` và `@CookieValue` có thể chứa secret. Không ghi toàn bộ method arguments/URI vào log.
- Nếu API bên ngoài thay đổi field JSON hay status, proxy không tự “sửa” schema; cần contract/integration test.

## 8. Ví dụ Java 17+ chạy độc lập: chứng minh GET, POST và parameter mapping

Ví dụ này dùng JDK `HttpServer` làm HTTP server chạy trên localhost, `RestClient` làm client và HTTP interface `@GetExchange`/`@PostExchange`. **Không cần tài khoản hay kết nối Internet để gọi API**; Gradle tải dependency Maven lần đầu nếu chưa cache.

Cấu trúc thư mục:

```text
http-service-demo/
├── build.gradle
└── src/main/java/demo/HttpInterfaceDemo.java
```

`build.gradle` (bản chạy tham chiếu Spring Boot 3.3.13 → Spring Framework 6.1.21):

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web:3.3.13'
}

application {
    mainClass = 'demo.HttpInterfaceDemo'
}
```

`src/main/java/demo/HttpInterfaceDemo.java`:

```java
package demo;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

public class HttpInterfaceDemo {

    @HttpExchange("/v1")
    public interface NotesApi {
        @GetExchange("/notes/{id}")
        String get(
                @PathVariable("id") long id,
                @RequestParam("lang") String language,
                @RequestHeader("X-Trace-Id") String traceId);

        @PostExchange(
                url = "/notes",
                contentType = MediaType.TEXT_PLAIN_VALUE,
                accept = MediaType.TEXT_PLAIN_VALUE)
        String post(
                @RequestBody String text,
                @RequestHeader("X-Trace-Id") String traceId);
    }

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/notes", HttpInterfaceDemo::handle);
        server.start();

        try {
            String baseUrl =
                    "http://127.0.0.1:" + server.getAddress().getPort();

            RestClient restClient = RestClient.builder()
                    .baseUrl(baseUrl)
                    .build();

            NotesApi notes = HttpServiceProxyFactory
                    .builderFor(RestClientAdapter.create(restClient))
                    .build()
                    .createClient(NotesApi.class);

            System.out.println(notes.get(42, "vi", "T-01"));
            System.out.println(notes.post("Spring Client", "T-02"));
        } finally {
            server.stop(0);
        }
    }

    private static void handle(com.sun.net.httpserver.HttpExchange exchange) throws IOException {
        try {
            String method = exchange.getRequestMethod();
            String trace =
                    exchange.getRequestHeaders().getFirst("X-Trace-Id");
            String result;

            if ("GET".equals(method)) {
                result = "GET " + exchange.getRequestURI().getRawPath()
                        + "?" + exchange.getRequestURI().getRawQuery()
                        + " trace=" + trace;
            } else if ("POST".equals(method)) {
                String body = new String(
                        exchange.getRequestBody().readAllBytes(),
                        StandardCharsets.UTF_8);
                result = "POST body=" + body + " trace=" + trace;
            } else {
                exchange.sendResponseHeaders(405, -1);
                return;
            }

            byte[] bytes = result.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }
}
```

Chạy:

```bash
gradle run
```

Nếu project đã có Gradle Wrapper: macOS/Linux `./gradlew run`; Windows PowerShell `.\gradlew.bat run`. Với Java 17+ và dependency đúng, hai dòng chương trình in ra là:

```text
GET /v1/notes/42?lang=vi trace=T-01
POST body=Spring Client trace=T-02
```

Đó là **stdout do `System.out.println` sinh ra**; Gradle có thể in thêm log build. Server dùng cổng loopback ngẫu nhiên, do đó không hard-code port. Đường dẫn `/v1` từ `@HttpExchange` cấp interface, `/notes/{id}` từ `@GetExchange`, giá trị 42 thay `{id}`, `lang=vi` đến từ `@RequestParam`, `X-Trace-Id` thành header. POST gửi đúng chuỗi `Spring Client` làm body text/plain.

Lưu ý chương trình không khởi động `SpringApplication` và không tạo MVC controller. Điều này chứng minh HTTP interface hoạt động thông qua proxy và một HTTP client thật, không cần Spring IoC container để chạy.

### Đổi POST từ text/plain sang JSON

Trong ứng dụng thực tế, có thể thay khai báo bằng:

```java
record CreateNoteRequest(String text) {}
record NoteDto(long id, String text) {}

@PostExchange(
        url = "/notes",
        contentType = MediaType.APPLICATION_JSON_VALUE,
        accept = MediaType.APPLICATION_JSON_VALUE)
NoteDto create(@RequestBody CreateNoteRequest request);
```

Đây là **fragment**; server tương ứng phải hiểu JSON, trả JSON và project phải có codec/message converters JSON. Khác với demo, bạn sẽ cần một handler tạo note và response DTO thật.

## 9. Những lỗi phổ biến và cách tránh

1. **Không tạo proxy:** annotation interface không tự thành bean. Tạo bằng `HttpServiceProxyFactory` hoặc cấu hình cơ chế auto-registration tương thích phiên bản.
2. **Trộn annotation server/client:** `@RequestParam` trên HTTP service *đang tạo outgoing request*; không tự đọc query từ request đi vào server Spring MVC.
3. **Quên @PathVariable tên rõ ràng:** `{id}` và `@PathVariable("userId")` không khớp sẽ lỗi. Giữ tên consistent.
4. **Đẩy JSON qua @RequestParam:** với POST JSON, dùng `@RequestBody` và đúng `contentType`; form-urlencoded là tình huống khác.
5. **Gửi body với @GetExchange:** API GET không nên phụ thuộc request body; nhiều proxy/cache/server không hỗ trợ hoặc không có semantics ổn định.
6. **Thử khai báo @RequestPart nhưng Content-Type là application/json:** multipart cần `multipart/form-data` và format từng part được server hỗ trợ.
7. **Không biết tham số null có hợp lệ hay không:** khai rõ `required=false`/`Optional` với tham số optional; validate đầu vào bắt buộc.
8. **Gửi trùng Authorization do defaultHeader + @RequestHeader:** kiểm tra cơ chế cộng header và tránh biến token thành header list ngoài ý muốn.
9. **Dùng @PostExchange cho thao tác non-idempotent rồi auto-retry:** có thể tạo dữ liệu trùng. Xác định idempotency key và chính sách retry.
10. **Đổi RestClient ↔ WebClient nhưng giữ return type bất hợp lý:** chọn kiểu sync/reactive phù hợp adapter; không block trong WebFlux event loop.
11. **Bỏ qua mã lỗi và timeout:** status 400/500 khác lỗi mạng; cấu hình handler, logging có kiểm soát và timeout ở underlying client.
12. **Cho phép dynamic URI không kiểm soát:** có thể gửi request tới host ngoài phạm vi hoặc SSRF. Validate scheme, host, port và mạng đích.
13. **Cho rằng Accept là Content-Type:** `Accept` mô tả response mong muốn; `Content-Type` mô tả payload request.
14. **Viết test chỉ assert interface method return mock:** nên có test thực gửi request tới server giả/local để xác minh URL, headers, query/body và HTTP status.

## 10. Tự luyện và kiểm tra hiểu bài

**Bài 1 – Đọc request.**

```java
@HttpExchange("/api")
interface ProductApi {
    @GetExchange("/products/{id}")
    String find(
            @PathVariable("id") int id,
            @RequestParam("region") String region,
            @RequestHeader("X-Client") String client);
}
```

Giả sử base URL là `https://shop.example.org`, gọi `find(9, "vn", "portal")`. Kết quả về mặt cấu trúc là:

```http
GET /api/products/9?region=vn HTTP/1.1
Host: shop.example.org
X-Client: portal
```

Không có JSON request body. Dòng HTTP trên là biểu diễn request logic; HTTP transport thực tế có thể dùng HTTP/2 hoặc thêm các header khác.

**Bài 2 – Sửa ánh xạ.** Code sau gửi POST JSON đúng chưa?

```java
@PostExchange(url = "/customers", contentType = "application/json")
String create(@RequestParam("name") String name);
```

**Đáp án:** Chưa đúng nếu server đòi JSON body. Dùng một DTO/record và `@RequestBody`. `@RequestParam` ở đây thêm query parameter do content type không phải form-urlencoded.

**Bài 3 – Optional.** Nếu HTTP service interface có tham số `@RequestParam(value="sort", required=false) String sort`, có thể gọi với `null` không? **Đáp án:** Có; Spring được phép bỏ qua tham số không bắt buộc. Với param required, cần truyền giá trị hoặc cơ chế optional phù hợp.

**Bài 4 – Chọn adapter.** Giao diện trả `Mono<BookDto>` nên dùng gì? **Đáp án:** `WebClientAdapter` / reactive backend; còn các return type sync kiểu `BookDto`/`ResponseEntity<BookDto>` là tự nhiên với `RestClientAdapter`.

**Bài 5 – Phân biệt header.** `@PostExchange(contentType="application/json", accept="application/json")` tạo những header nào? **Đáp án:** `Content-Type: application/json` để mô tả body gửi đi và `Accept: application/json` để cho biết client muốn nhận JSON.

## Tài liệu tham khảo chính thức

- [Spring Framework — REST Clients: HTTP Service Clients, Method Parameters, Return Values](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-http-interface)
- [Spring Framework 6.1 — @HttpExchange Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/service/annotation/HttpExchange.html)
- [Spring Framework 6.1 — @GetExchange Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/service/annotation/GetExchange.html)
- [Spring Framework 6.1 — @PostExchange Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/service/annotation/PostExchange.html)
- [Spring Framework 6.1 — HttpServiceProxyFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html)
