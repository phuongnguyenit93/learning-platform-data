# Đọc đầu vào, tạo phản hồi và sử dụng message converter trong Functional Spring MVC

> **Bối cảnh:** Spring Framework 6.2.x, Spring Boot 3.5.x, Java 17+, trên **Servlet stack**. Chủ đề này thuộc **Functional MVC (WebMvc.fn)**: xử lý request bằng `HandlerFunction<ServerResponse>` thay vì khai báo controller method với `@RequestMapping`, đọc dữ liệu từ `ServerRequest`, trả `ServerResponse` và dùng các **`HttpMessageConverter`** của Spring MVC để biến HTTP bytes thành Java objects hoặc ngược lại. Cần phân biệt với **WebFlux.fn**: WebMvc.fn sử dụng package `org.springframework.web.servlet.function`, các thao tác đọc body chính là `request.body(Class<T>)` / `request.body(ParameterizedTypeReference<T>)`, không phải `bodyToMono()` hay `HttpMessageReader` của WebFlux.

## 1. Functional MVC giải quyết điều gì?

Spring MVC có hai cách quen thuộc để khai báo HTTP endpoints:

**Annotation-based MVC:**

```java
@RestController
@RequestMapping("/api/books")
class BookController {

    @PostMapping
    public Book create(@RequestBody CreateBook input) {
        return service.create(input);
    }
}
```

**Functional MVC (WebMvc.fn):**

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .POST("/api/books", handler::create)
                .build();

// Trong class handler:
ServerResponse create(ServerRequest request) throws Exception {
    CreateBook input = request.body(CreateBook.class);
    Book saved = service.create(input);
    return ServerResponse.ok().body(saved);
}
```

Hai đoạn trên **là snippets minh họa**, yêu cầu `Book`, `CreateBook`, `service`, `handler` được định nghĩa. Functional MVC vẫn chạy bên trong **`DispatcherServlet`**, vẫn dùng Servlet request/response và các message converters; nó **không** tự biến web application thành reactive WebFlux stack.

Đối với yêu cầu “đọc đầu vào – tạo phản hồi – dùng converter”, mô hình WebMvc.fn là:

```text
HTTP request bytes
      |
Servlet container / DispatcherServlet
      |
RouterFunction<ServerResponse> chọn route
      |
HandlerFunction<ServerResponse>.handle(ServerRequest)
      |
ServerRequest.body(Class/ParameterizedTypeReference)
      |
HttpMessageConverter.read(...)  <-- JSON/text/form/binary
      |
Java DTO + validation/authorization/business logic
      |
ServerResponse.status(...).contentType(...).body(Java object)
      |
HttpMessageConverter.write(...) <-- serialize body theo type/media
      |
HTTP status + headers + response bytes
```

**Ghi nhớ:** Router quyết định **handler nào** chạy; Handler quyết định **đọc gì và trả gì**; converter quyết định **cách diễn dịch và serialize HTTP body**. Validation, authentication/authorization và giới hạn kích thước payload là trách nhiệm riêng; có Jackson không có nghĩa input tự an toàn.

## 2. Bốn thành phần của Functional MVC

| Thành phần | Package | Vai trò |
| --- | --- | --- |
| `RouterFunction<ServerResponse>` | `org.springframework.web.servlet.function` | Từ `ServerRequest` xác định handler tương ứng |
| `HandlerFunction<ServerResponse>` | `org.springframework.web.servlet.function` | Nhận `ServerRequest`, trả `ServerResponse`; có thể `throws Exception` |
| `ServerRequest` | `org.springframework.web.servlet.function` | Truy cập method/URI/header/query/path variables/body/cookies/Servlet request |
| `ServerResponse` | `org.springframework.web.servlet.function` | Tạo status/headers/cookies/body hoặc response trống, sau đó ghi qua converters |
| `HttpMessageConverter<T>` | `org.springframework.http.converter` | Chuyển đổi giữa Java value và HTTP request/response bytes |
| `RouterFunctionMapping` | `org.springframework.web.servlet.function.support` | Phát hiện RouterFunction beans và tìm route phù hợp |
| `HandlerFunctionAdapter` | `org.springframework.web.servlet.function.support` | Thực thi HandlerFunction bên trong MVC lifecycle |

Trong ứng dụng Spring Boot Web, Spring MVC infrastructure thường tự phát hiện `RouterFunction<?>` beans. **Không cần `@EnableWebMvc`** chỉ để dùng functional routes; bật nó tùy tiện có thể làm mất một số Boot MVC auto-configuration defaults.

### 2.1. Functional không đồng nghĩa với hoàn toàn thuần hàm

Các API request/response mô tả **hợp đồng mang tính immutable** cho việc xây dựng routes/response; nhưng handler vẫn có thể tương tác database, transaction, Servlet session và các Spring beans có trạng thái. `ServerRequest` có thể cho phép truy cập request attributes, body và underlying servlet request; do vậy vẫn phải có thiết kế thread-safety, validation và authorization.

### 2.2. Không nhầm với WebFlux.fn

| Vấn đề | WebMvc.fn | WebFlux.fn |
| --- | --- | --- |
| Import server request | `org.springframework.web.servlet.function.ServerRequest` | `org.springframework.web.reactive.function.server.ServerRequest` |
| Handler trả | `ServerResponse` | `Mono<ServerResponse>` hoặc Kotlin coroutine adapters |
| Đọc JSON DTO | `request.body(Dto.class)` | `request.bodyToMono(Dto.class)` |
| Đọc `List<T>` | `request.body(new ParameterizedTypeReference<List<T>>() {})` | `bodyToFlux(T.class)` hoặc `bodyToMono(...)` |
| Định dạng HTTP | MVC `HttpMessageConverter` | WebFlux reactive `HttpMessageReader/Writer` codecs |
| HTTP I/O | Servlet blocking foundation | Reactive stack, non-blocking I/O khi runtime hỗ trợ |
| Server entrypoint | `DispatcherServlet` | `DispatcherHandler` |

Nếu IDE báo không tìm thấy `bodyToMono()` trên `ServerRequest` mà dự án của bạn đang dùng `web.servlet.function`, **đó không phải thiếu import**: bạn đã đọc ví dụ của WebFlux.fn. Đổi đúng API thay vì thêm starter reactive chỉ để compiler nhận method không có trên kiểu MVC.

## 3. RouterFunction và HandlerFunction: đưa request tới đúng chỗ

Ví dụ:

```java
import static org.springframework.web.servlet.function.RouterFunctions.route;

@Bean
RouterFunction<ServerResponse> booksRouter(BookHandler handler) {
    return route()
            .GET("/api/books", handler::list)
            .GET("/api/books/{id}", handler::get)
            .POST("/api/books", handler::create)
            .build();
}
```

Đây là một bean method minh họa trong `@Configuration` class, cần `BookHandler`, `@Bean` và `RouterFunction`/`ServerResponse` imports.

- `RouterFunctions.route()` tạo DSL builder.
- `.GET(path, handler)` và `.POST(path, handler)` gắn method/path với callback.
- `handler::get` là method reference; target method nhận `ServerRequest` và trả `ServerResponse`.
- `.build()` trả một `RouterFunction<ServerResponse>` cho Spring MVC đăng ký.
- Trong annotation MVC, metadata routing đến từ `@GetMapping`/`@PostMapping`; trong WebMvc.fn, metadata đến từ **function/builder**.

### 3.1. Predicate lọc Content-Type và Accept

Nếu chỉ muốn route POST xử lý JSON, có thể dùng:

```java
import static org.springframework.web.servlet.function.RequestPredicates.contentType;

RouterFunction<ServerResponse> router = route()
        .POST("/api/books", contentType(MediaType.APPLICATION_JSON),
                handler::create)
        .build();
```

Nếu muốn áp điều kiện `Accept: application/json`:

```java
import static org.springframework.web.servlet.function.RequestPredicates.accept;

RouterFunction<ServerResponse> router = route()
        .GET("/api/books", accept(MediaType.APPLICATION_JSON),
                handler::list)
        .build();
```

**Lưu ý quan trọng:** khi predicate không match, router có thể đơn giản không chọn handler và dẫn tới 404/hoặc xử lý của mappings khác, **không bắt buộc** giống status 415/406 của annotated controller. Nếu API cần contract lỗi chính xác cho sai Content-Type/Accept, thực hiện integration tests và một error policy rõ ràng. Ví dụ runnable ở mục 9 chủ động không dùng predicate `contentType(...)` để dễ quan sát lỗi body/converter.

### 3.2. Nested routes và filter function

```java
RouterFunction<ServerResponse> router = route()
        .path("/api", b -> b
                .GET("/health", handler::health)
                .POST("/books", handler::create))
        .build();
```

Đây là snippet với `handler` khác được định nghĩa. Nested routing giúp nhóm prefix/conditions. WebMvc.fn còn có `before`, `after`, `filter` và `onError` trong router builder. Khi đăng ký filter **bên trong nested route**, scope của filter không tự áp cho mọi route bên ngoài. Dùng chúng cho trách nhiệm cross-cutting phù hợp nhưng không dùng để thay Spring Security FilterChain.

## 4. Đọc metadata request trước khi đọc body

`ServerRequest` cung cấp API dễ dùng:

```java
String id = request.pathVariable("id");
Optional<String> q = request.param("q");
HttpMethod method = request.method();
URI uri = request.uri();
String accept = request.headers().firstHeader("Accept");
Map<String, Object> attrs = request.attributes();
```

Đây là snippet cần imports `java.net.URI`, `java.util.*` và `org.springframework.http.HttpMethod`. API có thể khác khi dùng Spring major version khác; trong Spring MVC 6.2 có `pathVariable`, `param`, `headers` và `attributes`.

- `request.pathVariable("id")` lấy path segment được RouterFunction match; có thể ném lỗi nếu route không có biến tương ứng.
- `request.param("q")` là `Optional<String>`; xử lý trường hợp không có thay vì gọi `.get()`.
- `request.params()` lấy danh sách query parameters trong `MultiValueMap<String,String>` (có thể gồm nhiều giá trị).
- `request.headers()` có các phương thức đọc typed header tiện lợi như `accept()` và `contentType()` tùy API.
- `request.servletRequest()` cho phép truy cập `HttpServletRequest` khi cần khả năng Servlet-specific; không dùng nó làm cách chính đọc toàn body rồi đọc thêm lần nữa.

### 4.1. PathVariable cần parse và validate

```java
long id;
try {
    id = Long.parseLong(request.pathVariable("id"));
} catch (NumberFormatException ex) {
    return ServerResponse.badRequest()
            .body("Invalid id");
}
```

Đây là snippet minh họa, nhưng JSON API nên dùng error DTO và `contentType(APPLICATION_JSON)` thay vì body text mặc định. Không chuyển lỗi `NumberFormatException` thành HTTP 500, cũng không dùng exception message thô làm body.

### 4.2. Query có default và range

```java
String rawLimit = request.param("limit").orElse("20");
int limit = Integer.parseInt(rawLimit);
if (limit < 1 || limit > 100) {
    throw new IllegalArgumentException("limit outside range");
}
```

Validate cả parse lỗi, giới hạn kích thước, semantic constraints và bất kỳ quyền lọc/tìm kiếm nào. Đối với pagination, dùng LIMIT ở repository/DB thay vì đọc toàn triệu records rồi `stream().limit(20)` trong app.

## 5. Đọc HTTP body: ServerRequest.body(Class<T>)

Cách ngắn nhất cho JSON object:

```java
CreateBook command = request.body(CreateBook.class);
```

Khi request có:

```http
POST /api/books HTTP/1.1
Content-Type: application/json

{"title":"Spring MVC"}
```

Spring MVC tìm `HttpMessageConverter` có thể đọc:
- Target Java type `CreateBook.class`;
- Request `Content-Type` là `application/json`;
- Dependency/converter đăng ký trong MVC.

Một JSON converter phù hợp (ví dụ Jackson, từ Spring Web starter) sẽ đọc bytes từ Servlet request input stream, deserialize thành `CreateBook`. `request.body(...)` có thể ném lỗi nếu JSON sai hoặc converter không phù hợp; handler method có thể khai báo `throws Exception`.

### 5.1. Body có thể bị tiêu thụ

Servlet request input stream bình thường **không phải stream có thể tua về đầu tùy ý**. Đừng làm:

```java
String raw = request.body(String.class);
CreateBook second = request.body(CreateBook.class);
```

Đây là anti-pattern: lần đọc thứ hai không nên được xem là một lần parse lại từ đầu. Tương tự, nếu custom Servlet Filter đã gọi `getInputStream().readAllBytes()` để log trước khi MVC đọc body, request có thể rỗng ở handler. Muốn quan sát body hãy dùng bounded caching wrapper và để downstream đọc theo lifecycle phù hợp; đừng coi cache-on-read là cơ chế replay mặc định.

### 5.2. Body conversion KHÔNG tự động là validation

Giả sử DTO:

```java
record CreateBook(String title) {
}
```

Jackson có thể tạo instance khi field `title` vắng mặt/null, nên application vẫn phải kiểm tra field bắt buộc, độ dài, giá trị hợp lệ và business constraints. Trong functional handler, bare `request.body(CreateBook.class)` không đồng nghĩa tự chạy Bean Validation của `@Valid @RequestBody` trong annotated method.

Cách tối thiểu:

```java
CreateBook input = request.body(CreateBook.class);
if (input == null || input.title() == null
        || input.title().isBlank()
        || input.title().length() > 120) {
    return ServerResponse.badRequest()
            .contentType(MediaType.APPLICATION_JSON)
            .body(new ApiError("invalid_title"));
}
```

Trong app lớn, dùng Spring `Validator`/Jakarta Bean Validation qua một lớp validation service rõ ràng, tái sử dụng DTO rules. Không đọc input rồi mapping thẳng vào JPA entity có các trường nhạy cảm như `isAdmin`/`ownerId`/`tenantId`.

### 5.3. Exception liên quan body đọc

Các lớp lỗi thường gặp:
- JSON cú pháp sai hoặc dữ liệu không deserialize được có thể gây `HttpMessageNotReadableException`.
- Không có converter phù hợp cho content type hoặc data format có thể gây `HttpMediaTypeNotSupportedException` / các exception tương ứng trong infrastructure.
- Định dạng sai/ràng buộc nghiệp vụ bị từ chối bởi code handler có thể thành `IllegalArgumentException` hoặc error DTO.
- `IOException`/`ServletException` có thể phát sinh từ tầng đọc HTTP body.
- Body quá lớn cần chính sách ingress/container/filter **độc lập**, không tự có hard cap chỉ vì converter được đăng ký.

Không gộp tất cả thành HTTP 400 nếu lỗi hệ thống. Một lỗi I/O từ client disconnect hoặc database outage không cùng ngữ nghĩa với JSON malformed.

## 6. Đọc kiểu generic: ParameterizedTypeReference<T>

Java generics bị type erasure. Để deserialize `List<CreateBook>` (mảng JSON các object) đúng generic element type, dùng:

```java
import org.springframework.core.ParameterizedTypeReference;

List<CreateBook> commands =
        request.body(new ParameterizedTypeReference<List<CreateBook>>() {});
```

Request tương ứng:

```json
[
  {"title":"Book A"},
  {"title":"Book B"}
]
```

Nếu dùng `request.body(List.class)`, converter thiếu generic element type và có thể tạo `List<LinkedHashMap>` thay vì `List<CreateBook>`. Việc cast trực tiếp phần tử thành `CreateBook` có thể ném `ClassCastException`.

### 6.1. Khi nào dùng Class, khi nào dùng ParameterizedTypeReference?

| Đầu vào | API nên dùng |
| --- | --- |
| JSON object của một DTO | `request.body(CreateBook.class)` |
| JSON string/plain text | `request.body(String.class)` với Content-Type phù hợp |
| JSON array có generic element | `request.body(new ParameterizedTypeReference<List<CreateBook>>() {})` |
| JSON nested map/list | `request.body(new ParameterizedTypeReference<Map<String, List<ValueDto>>>() {})` |
| Raw bytes | `request.body(byte[].class)` với converter phù hợp; cảnh báo memory |
| Form URL-encoded | `request.params()` / form handling hoặc `MultiValueMap` theo converter và request handling |
| Multipart upload | Dùng Servlet multipart parsing và binding được hỗ trợ; không giả định JSON converter đọc file binary |

### 6.2. ParameterizedTypeReference không đảm bảo mọi format

Nó cung cấp **type metadata**, không cài đặt converter. Với custom media type hoặc một object không được Jackson/MessageConverter hỗ trợ, bạn vẫn cần converter tương ứng và security/resource limits. Không tự tin rằng “dùng ParameterizedTypeReference thì JSON/XML/CSV đều parse được”.

### 6.3. Bảo vệ bộ nhớ khi nhận List lớn

Request chứa hàng triệu phần tử JSON có thể được deserialize thành một `List<CreateBook>` khổng lồ. Vì converter MVC thường đọc/deserialize body thành object graph, hãy:
- đặt giới hạn body tại reverse proxy/container hoặc counting input stream;
- giới hạn số phần tử và độ sâu JSON bằng policy/parser configuration khi phù hợp;
- cân nhắc gửi batch nhỏ/pagination hoặc streaming ingestion chuyên dụng cho big data;
- không dùng `readAllBytes()` để nhân đôi bộ nhớ.

Ví dụ demo chỉ cho phép tối đa 5 item trong batch, nhưng **validation sau deserialize chưa phải hard memory limit**. Phải chặn payload quá lớn từ tầng trước nếu threat model yêu cầu.

## 7. Tạo ServerResponse: status, headers và body

WebMvc.fn cung cấp static factories:

```java
ServerResponse.ok()
ServerResponse.created(URI.create("/api/books/42"))
ServerResponse.accepted()
ServerResponse.noContent()
ServerResponse.badRequest()
ServerResponse.notFound()
ServerResponse.status(HttpStatus.CONFLICT)
```

Những biểu thức trên trả builder hoặc response-building APIs; để tạo response hoàn chỉnh cần gọi `.body(value)` hoặc `.build()` tùy trường hợp.

### 7.1. HTTP 200 với JSON body

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(new Book(42L, "Spring MVC"));
```

Java object không được đưa nguyên vẹn qua network. Khi Spring ghi `ServerResponse`, một converter phù hợp serialize `Book` thành JSON bytes. Với Jackson mặc định, body tương tự:

```json
{"id":42,"title":"Spring MVC"}
```

Thứ tự fields/whitespace có thể khác theo Jackson/version, nên test JSON theo path thay vì so toàn chuỗi.

### 7.2. HTTP 201 Created và Location

```java
return ServerResponse.created(URI.create("/api/books/42"))
        .contentType(MediaType.APPLICATION_JSON)
        .body(new Book(42L, "Spring MVC"));
```

Kết quả có status **201 Created**, header `Location: /api/books/42` (relative URI là một URI hợp lệ cho Location), và JSON body. Đừng tự ghép absolute host từ raw `X-Forwarded-Host` để tạo Location nhạy cảm; proxy trust boundary và canonical public base URL phải được kiểm soát.

### 7.3. Không body: build()

```java
return ServerResponse.noContent().build();
```

Trả **204 No Content**; không dùng `.body(...)` trên 204 rồi mong browser nhận JSON. Với lệnh DELETE thành công hoặc update không cần representation, 204 là một lựa chọn thường gặp.

### 7.4. 400/404/409 và error DTO

```java
return ServerResponse.status(HttpStatus.CONFLICT)
        .contentType(MediaType.APPLICATION_JSON)
        .body(new ApiError("conflict"));
```

Với lỗi validation:

```java
return ServerResponse.badRequest()
        .contentType(MediaType.APPLICATION_JSON)
        .body(new ApiError("invalid_request"));
```

Với tài nguyên không tìm thấy:

```java
return ServerResponse.notFound().build();
```

Dùng HTTP status phản ánh semantics chứ không trả 200 với `{"error":...}`. Đừng đưa raw exception stack trace, token hoặc internal filesystem paths vào response.

### 7.5. Header, cache, content negotiation

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .header("X-Request-Tag", "demo")
        .header("Cache-Control", "no-store")
        .body(book);
```

Các API của response builder cũng có hỗ trợ cookies, ETag/Last-Modified và headers khi cần. Cẩn thận:
- `Content-Type` mô tả kiểu bytes trả ra, không phải Java class.
- `Accept` của client cho biết kiểu representation client chấp nhận.
- Nếu bạn ép `contentType(APPLICATION_JSON)` dù client chỉ chấp nhận XML, không tự mặc định handler sẽ thương lượng giống annotation `produces`; cần router predicates, infrastructure, và tests 406/serialization đúng.
- `Content-Length` phải tính theo **bytes đã encode**, không theo `String.length()`; thông thường để container/converter xử lý.
- Khi ghi response xong/committed, không thể thay status/header một cách chắc chắn.

## 8. HttpMessageConverter thực sự làm gì?

Spring MVC `HttpMessageConverter<T>` là cầu nối:

```text
Read:
application/json bytes -> Jackson JSON converter -> Java DTO

Write:
Java DTO -> Jackson JSON converter -> application/json bytes

Read:
text/plain bytes -> StringHttpMessageConverter -> String

Write:
byte[] -> ByteArrayHttpMessageConverter -> application/octet-stream bytes

Read form:
application/x-www-form-urlencoded -> FormHttpMessageConverter
                                         -> MultiValueMap<String, String>
```

Converter quyết định khả năng đọc/ghi dựa trên Java type, `Content-Type` / `MediaType`, dependency có trên classpath, và thứ tự converters đã đăng ký.

### 8.1. Các converter thường gặp

| Converter | Kiểu Java thường gặp | Media type |
| --- | --- | --- |
| `StringHttpMessageConverter` | `String` | `text/plain` / text media |
| `MappingJackson2HttpMessageConverter` | POJO/record/List/Map | `application/json` và các dạng JSON tương thích |
| `ByteArrayHttpMessageConverter` | `byte[]` | Thường `application/octet-stream` |
| `ResourceHttpMessageConverter` | `Resource` | Binary/stream resource |
| `FormHttpMessageConverter` | `MultiValueMap<String,String>` | `application/x-www-form-urlencoded` (đọc/ghi), multipart (ghi trong phạm vi được hỗ trợ) |
| XML converters | JAXB/Jackson XML types | `application/xml` hoặc `text/xml` nếu dependency/cấu hình có |

**Đừng nhầm `HttpMessageConverter` với `Converter<S,T>` trong `ConversionService`.** ConversionService thường phục vụ chuyển String path/query/form field thành primitive/enum/type; HttpMessageConverter đọc/ghi **HTTP body**.

### 8.2. Converter không thay validation

Quá trình deserialize thành `CreateBook` không xác nhận user có quyền tạo sách, không giới hạn title theo nghiệp vụ, không sanitize HTML script và không chặn owner spoofing. Cần DTO riêng, bean validation/manual validation và domain service authorization.

### 8.3. Converter không bảo đảm an toàn với untrusted payload

Một JSON parser có thể bị gây áp lực CPU/memory bởi payload quá lớn/sâu. Multipart/XML/file upload có thêm rủi ro riêng. Cấu hình:
- giới hạn request body và header sizes tại proxy/container;
- parser constraints/phần tử/depth và multipart limits;
- validation DTO/schema, allowlist fields;
- authentication/authorization, rate limits;
- logging có redaction, không dump raw body theo mặc định.

### 8.4. Request và response converters trong WebMvc.fn

`ServerRequest.messageConverters()` cho biết converters phục vụ đọc request body. Khi ghi `ServerResponse`, infrastructure dùng danh sách converters trong response context để chọn cách serialize body. Spring Boot MVC auto-configuration cung cấp các converters mặc định dựa theo classpath.

Nếu bạn thêm một custom converter chỉ vào một phần infrastructure nhưng endpoint không thấy, cần kiểm tra cấu hình MVC và thứ tự converters; đừng mặc định mọi custom Jackson `ObjectMapper`/codec đều áp dụng cho tất cả routes.

## 9. Ví dụ chạy được: Java 17 + Spring Boot 3.5, WebMvc.fn

Ứng dụng minh họa **không dùng `@RestController`**; chỉ có:
- Một `RouterFunction<ServerResponse>` bean;
- Một handler class (Spring component) làm việc với `ServerRequest`/`ServerResponse`;
- Một in-memory store tách khỏi HTTP routing.

Các endpoints:
- `GET /api/books?limit=10` — đọc query, trả JSON array;
- `GET /api/books/{id}` — đọc path variable, trả JSON hoặc 404;
- `POST /api/books` — dùng `body(CreateBook.class)`, validate, trả 201 + Location + JSON;
- `POST /api/books/batch` — dùng `body(ParameterizedTypeReference<List<CreateBook>>)`, validate và trả JSON array.
- Lỗi `IllegalArgumentException` do input tự kiểm tra được router `onError` map thành 400 JSON.

**Đây là ví dụ học tập:** dùng in-memory concurrent map; không có database, user auth, CSRF, CORS hoặc persistent storage. Những bảo vệ ấy phải bổ sung trong production. `CREATE` trong demo có thể được gọi không xác thực; tuyệt đối không triển khai công khai như service production.

### 9.1. POM/Dependencies

Tạo Maven project tại [Spring Initializr](https://start.spring.io/) với:
- Spring Boot 3.5.x, Java 17+;
- Dependency **Spring Web** (`spring-boot-starter-web`).

Fragment `pom.xml` do Initializr quản lý version:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

Spring Web starter mang Spring MVC, Jackson JSON converter và embedded Tomcat mặc định. Không cần `spring-boot-starter-webflux`; functional MVC dùng `web.servlet.function`.

### 9.2. Một file Java đầy đủ

Tạo file:

```text
src/main/java/com/example/demo/DemoApplication.java
```

Toàn bộ nội dung:

```java
package com.example.demo;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    RouterFunction<ServerResponse> bookRoutes(BookHandler handler) {
        return RouterFunctions.route()
                .GET("/api/books", handler::list)
                .GET("/api/books/{id}", handler::get)
                .POST("/api/books", handler::create)
                .POST("/api/books/batch", handler::createBatch)
                .onError(IllegalArgumentException.class,
                        (ex, request) -> ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .body(new ApiError("invalid_request")))
                .build();
    }
}

record Book(long id, String title) {
}

record CreateBook(String title) {
}

record ApiError(String error) {
}

@Component
class BookHandler {

    private final AtomicLong nextId = new AtomicLong();
    private final Map<Long, Book> books = new ConcurrentHashMap<>();

    public ServerResponse list(ServerRequest request) {
        int limit = Integer.parseInt(
                request.param("limit").orElse("10"));

        if (limit < 1 || limit > 50) {
            throw new IllegalArgumentException("limit out of range");
        }

        List<Book> result = books.values().stream()
                .sorted(Comparator.comparingLong(Book::id))
                .limit(limit)
                .toList();

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .header("Cache-Control", "no-store")
                .body(result);
    }

    public ServerResponse get(ServerRequest request) {
        long id = Long.parseLong(request.pathVariable("id"));
        Book found = books.get(id);

        if (found == null) {
            return ServerResponse.notFound().build();
        }

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(found);
    }

    public ServerResponse create(ServerRequest request)
            throws Exception {

        // HttpMessageConverter đọc JSON -> CreateBook.
        CreateBook command = request.body(CreateBook.class);
        validate(command);

        long id = nextId.incrementAndGet();
        Book created = new Book(id, command.title().trim());
        books.put(id, created);

        // Location dùng URI tương đối, không tin raw Host headers.
        return ServerResponse.created(
                        URI.create("/api/books/" + id))
                .contentType(MediaType.APPLICATION_JSON)
                .body(created);
    }

    public ServerResponse createBatch(ServerRequest request)
            throws Exception {

        // Giữ generic type List<CreateBook> cho JSON converter.
        List<CreateBook> commands = request.body(
                new ParameterizedTypeReference<List<CreateBook>>() {});

        if (commands == null
                || commands.isEmpty()
                || commands.size() > 5) {
            throw new IllegalArgumentException("invalid batch size");
        }

        // Validate tất cả trước khi ghi vào map.
        commands.forEach(this::validate);

        List<Book> created = commands.stream()
                .map(command -> {
                    long id = nextId.incrementAndGet();
                    Book book = new Book(id, command.title().trim());
                    books.put(id, book);
                    return book;
                })
                .toList();

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(created);
    }

    private void validate(CreateBook command) {
        if (command == null
                || command.title() == null
                || command.title().isBlank()
                || command.title().length() > 120) {
            throw new IllegalArgumentException("invalid title");
        }
    }
}
```

### 9.3. Kiểm tra tính độc lập của ví dụ

Đoạn code nằm **trong một Java file** với một public class `DemoApplication` và các class/record khác package-private. JDK 17 hỗ trợ `record`, method references và `Stream.toList()`. `RouterFunctions.route()` gọi đúng package của Servlet MVC. Body input parse bằng `ServerRequest.body(...)`, output viết bằng `ServerResponse.body(...)`. Jackson converter từ Spring Web starter có thể serialize các record.

Logic store dùng `AtomicLong` và `ConcurrentHashMap` để tránh trùng ID khi nhiều requests đồng thời; **không** có atomic transaction cho toàn batch và không có persistence khi restart. Trong production, dùng transactional service/repository và kiểm tra quyền/constraints trước khi ghi.

Handler không catch JSON parsing exceptions để làm chúng biến thành success. Router `onError(IllegalArgumentException.class,...)` chỉ xử lý loại exception tương ứng. Lỗi JSON malformed/converter không đọc được có thể được Spring exception resolvers xử lý với status tương ứng tùy MVC config, nhưng nếu cần một JSON lỗi thống nhất phải thêm error handling có chủ đích.

**Vấn đề routing:** `POST /api/books/batch` và `GET /api/books/{id}` không xung đột vì HTTP method khác. Nếu sau này bổ sung `GET /api/books/batch`, phải đánh giá static path vs variable path và thứ tự/độ cụ thể, tránh mapping ambiguity.

### 9.4. Chạy ứng dụng

Ở root project:

```bash
# Linux / macOS
./mvnw spring-boot:run

# Windows PowerShell / CMD
mvnw.cmd spring-boot:run
```

Server mặc định `http://localhost:8080` nếu chưa thay `server.port` hoặc Servlet context path.

### 9.5. Test 1: GET danh sách rỗng

```bash
curl -i 'http://localhost:8080/api/books'
```

Dự kiến:
- Status `200 OK`.
- `Content-Type: application/json`.
- Body:

```json
[]
```

Store ban đầu không có sách; không có lý do trả 404 cho một danh sách hợp lệ nhưng rỗng. `Cache-Control: no-store` được handler đặt ở list response.

### 9.6. Test 2: POST JSON object thành Book

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":"Spring MVC.fn"}'
```

Dự kiến:

```http
HTTP/1.1 201
Location: /api/books/1
Content-Type: application/json

{"id":1,"title":"Spring MVC.fn"}
```

Lưu ý `1` là ID đầu tiên khi app vừa khởi động và chưa có POST nào khác; chạy test khác trước sẽ tạo ID khác. Spring/Jackson có thể thêm headers hoặc serialize JSON whitespace khác, nên xem status, Location và JSON fields thay vì so nguyên string.

### 9.7. Test 3: GET theo ID

```bash
curl -i 'http://localhost:8080/api/books/1'
```

Khi record ID 1 tồn tại, status 200, JSON:

```json
{"id":1,"title":"Spring MVC.fn"}
```

Gọi ID không tồn tại:

```bash
curl -i 'http://localhost:8080/api/books/99999'
```

Dự kiến status **404 Not Found**. Response body với `ServerResponse.notFound().build()` có thể rỗng, tùy error dispatch/container; không khẳng định một JSON lỗi nhất định.

### 9.8. Test 4: POST generic JSON array

```bash
curl -i -X POST 'http://localhost:8080/api/books/batch' \
  -H 'Content-Type: application/json' \
  --data-binary '[{"title":"Java"},{"title":"Spring"}]'
```

Dự kiến status **200 OK**, JSON array có hai object với ID tiếp theo:

```json
[
  {"id":2,"title":"Java"},
  {"id":3,"title":"Spring"}
]
```

Con số ID như trên giả định chỉ có POST từ bước 2 trước đó. Đây là ví dụ điển hình chứng minh converter cần biết generic element type để tạo `List<CreateBook>`.

### 9.9. Test 5: sai query limit

```bash
curl -i 'http://localhost:8080/api/books?limit=0'
```

`list()` ném `IllegalArgumentException` và router `onError(...)` trả **400 Bad Request**, body:

```json
{"error":"invalid_request"}
```

Tương tự `limit=abc` cũng gây `NumberFormatException`, là subclass của `IllegalArgumentException`, nên được router error handler xử lý. Không đưa nội dung exception gốc lên client.

### 9.10. Test 6: DTO validation

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":"  "}'
```

Dự kiến **400** với error DTO, vì `title.isBlank()` là true. Trong ví dụ, logic validation là manual Java checks; ứng dụng thật nên dùng shared Bean Validation/Validator khi cần rules phức tạp.

### 9.11. Test 7: lỗi JSON malformed

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":'
```

Jackson converter không thể parse; request phải bị từ chối, không có book mới. Status thực tế thường thuộc nhóm **4xx** do MVC exception handling, nhưng định dạng error body cụ thể cần kiểm thử với Boot/Spring version và global exception configuration. Nếu API contract yêu cầu JSON lỗi cố định, đăng ký error handler cho `HttpMessageNotReadableException` và trả 400. Đừng test mong `{"error":"invalid_request"}` của router `onError(IllegalArgumentException)`, vì parse error không nhất thiết thuộc kiểu đó.

### 9.12. Windows PowerShell

Dùng `curl.exe` (không dùng alias `curl` khi muốn cú pháp curl truyền thống):

```powershell
curl.exe -i "http://localhost:8080/api/books"
curl.exe -i "http://localhost:8080/api/books?limit=5"
```

Khi gửi JSON phức tạp, cách đáng tin là tạo file `request.json` UTF-8:

```json
{"title":"Spring MVC.fn"}
```

Sau đó:

```powershell
curl.exe -i -X POST "http://localhost:8080/api/books" -H "Content-Type: application/json" --data-binary "@request.json"
```

Cách này tránh các biến thể escape dấu quote của native commands giữa các phiên bản PowerShell.

## 10. Test chức năng bằng MockMvc

Với Spring Boot 3.5.x, thêm test starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Test ở `src/test/java/com/example/demo/FunctionalBookTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FunctionalBookTest {

    @Autowired
    MockMvc mvc;

    @Test
    void canCreateAndReadThroughFunctionalRoutes() throws Exception {
        MvcResult created = mvc.perform(
                        post("/api/books")
                                .contentType("application/json")
                                .content("{\"title\":\"Demo\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().exists("Location"))
                .andExpect(jsonPath("$.title").value("Demo"))
                .andReturn();

        String location =
                created.getResponse().getHeader("Location");

        mvc.perform(get(location))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Demo"));
    }

    @Test
    void invalidInputIsHandledAs400() throws Exception {
        mvc.perform(post("/api/books")
                        .contentType("application/json")
                        .content("{\"title\":\"   \"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("invalid_request"));
    }

    @Test
    void genericBatchReadsTypedList() throws Exception {
        mvc.perform(post("/api/books/batch")
                        .contentType("application/json")
                        .content(
                                "[{\"title\":\"A\"},{\"title\":\"B\"}]"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].title").value("A"))
                .andExpect(jsonPath("$[1].title").value("B"));
    }
}
```

Các tests không giả định ID tuyệt đối vì store dùng `AtomicLong` và application context có thể tái sử dụng giữa tests. Test chỉ kiểm tra route, converter, status/body và Location; cần thêm tests cho:
- Sai/mất Content-Type;
- Accept không tương thích và 406/route predicate;
- Malformed JSON;
- Path ID không phải số;
- Batch rỗng, batch quá 5 items;
- Authorization/CSRF/rate limits trong production;
- Concurrency và persistence nếu dùng database.

Chạy:

```bash
# Linux / macOS
./mvnw test

# Windows
mvnw.cmd test
```

## 11. Cấu hình message converters khi mặc định chưa đủ

Spring Boot auto-register converters từ classpath. Với API JSON thông thường, ưu tiên giữ auto-config và cấu hình Jackson qua các phương tiện được Spring Boot hỗ trợ. Chỉ tùy biến converters khi có nhu cầu rõ như media type độc quyền, codec dữ liệu nhị phân hoặc serialization đặc biệt.

### 11.1. extendMessageConverters thay vì thay toàn danh sách

```java
@Configuration
class MvcConversionConfig implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        // Kiểm tra thứ tự/type, thêm hoặc điều chỉnh converter
        // mà vẫn giữ các defaults cần thiết.
    }
}
```

Đây là **snippet cấu hình**, cần imports `@Configuration`, `WebMvcConfigurer`, `HttpMessageConverter`, `List`. Khi dùng `configureMessageConverters(...)` (kiểu cấu hình đời Spring 6.x), bạn có thể **thay thế cấu hình defaults** nếu không thêm lại converters. Tùy phiên bản Spring 7 có API config dạng builder mới, nên không copy chữ ký giữa các major versions.

**Đề xuất:** nếu chỉ muốn đổi format Jackson date hoặc field naming, nên cấu hình Jackson thay vì tự thay converter list. Nếu cần CSV, có thể viết custom `HttpMessageConverter` có canRead/canWrite/MediaType rõ ràng, nhưng phải tính đến security, streaming và format parsing.

### 11.2. Converter selection và content negotiation

Khi đọc request body:

```text
Target: CreateBook.class
Content-Type: application/json
Converter candidate: Jackson JSON
-> canRead(CreateBook.class, application/json)
-> deserialize
```

Khi viết response:

```text
Body: Book record
Response contentType: application/json
Converter candidate: Jackson JSON
-> canWrite(Book.class, application/json)
-> serialize
```

Khi không có converter phù hợp, MVC không thể thành công chỉ bằng cách gọi `.body(value)`. Error có thể là 415 cho request media type không được hỗ trợ, 406 cho response negotiation, hoặc server-side converter failure/500 tùy vị trí lỗi và error handler. **Test status và error contract thực tế**, không mặc định mọi route predicate failure đều tạo 415/406.

### 11.3. Form data không giống JSON body

Đối với `application/x-www-form-urlencoded`:

```http
POST /api/forms
Content-Type: application/x-www-form-urlencoded

name=Lan&city=Hanoi
```

Form fields thường được expose qua request parameters, khác với JSON object body. Với `ServerRequest.bind(...)` (Spring 6.1+), có thể bind request parameters, URI variables hoặc headers theo DataBinder. Ví dụ:

```java
CreateProfile form = request.bind(
        CreateProfile.class,
        binder -> binder.setAllowedFields("displayName", "city"));
```

Đây là snippet: cần `CreateProfile` có kiểu bindable và customizer phù hợp. `setAllowedFields(...)` chỉ ràng buộc trường cho DataBinder, không tự làm JSON allowlist khi handler dùng `request.body(CreateProfile.class)` với Jackson. **Không** bind trực tiếp JPA entity chứa quyền admin/billingId.

### 11.4. Multipart file upload

File upload không nên được đối xử như một JSON DTO chứa byte array khổng lồ. Đối với Servlet MVC multipart, kiểm tra Spring multipart resolver, `MultipartFile`/`Part`, request size limits, metadata validation và private storage. Với Functional MVC, có thể cần truy cập Servlet multipart API hoặc request binding được framework hỗ trợ; không mặc định `request.body(MyDto.class)` tự xử lý file/stream như JSON.

Ví dụ cấu hình Spring Boot 3.x:

```properties
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
```

Những thuộc tính trên dành cho multipart, **không phải universal hard cap** cho JSON/mọi request payload. Bảo vệ JSON lớn cần thêm cấu hình edge/container hoặc bounded read policy.

## 12. Xử lý lỗi trong Functional MVC

### 12.1. Router-level onError

```java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .GET("/api/items/{id}", handler::get)
        .onError(IllegalArgumentException.class,
                (ex, request) -> ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(new ApiError("invalid_request")))
        .build();
```

Đây là snippet dùng `handler` đã định nghĩa. `onError(Class<? extends Throwable>, ...)` áp dụng cho exception phù hợp xuất hiện trong scope router builder. Đây không phải thay thế cho security error handling hay toàn bộ Servlet container exception handling. Một exception nảy sinh **trước** khi route được tìm thấy hoặc từ Servlet Filter ngoài MVC không mặc định đi qua router onError.

### 12.2. Bọc conversion exceptions có chọn lọc

Nếu contract yêu cầu JSON 400 cho malformed JSON, có thể bổ sung error handler cho `HttpMessageNotReadableException`:

```java
.onError(HttpMessageNotReadableException.class,
        (ex, request) -> ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ApiError("malformed_json")))
```

Đây là **fragment** thêm vào router builder và cần import `org.springframework.http.converter.HttpMessageNotReadableException`. Không cho generic error handler bắt mọi exception và trả 400, vì lỗi của service/DB phải được phân loại khác.

### 12.3. Handler trả lỗi thay vì throw

Nếu kiểm tra input đơn giản, trả ServerResponse rõ ràng có thể dễ hơn:

```java
if (input == null || input.title() == null) {
    return ServerResponse.badRequest()
            .contentType(MediaType.APPLICATION_JSON)
            .body(new ApiError("title_required"));
}
```

Nếu có nhiều endpoints, dùng shared validation/service để tránh lặp các quy tắc. Error responses nên nhất quán với API contract, ví dụ RFC 9457 Problem Details khi phù hợp; WebMvc.fn không tự bắt mọi domain exception và biến thành đúng DTO bạn muốn.

### 12.4. @ControllerAdvice và WebMvc.fn có giống nhau không?

`@ControllerAdvice` được dùng mạnh nhất với annotated controllers (global `@ExceptionHandler`, `@InitBinder`, `@ModelAttribute`). Functional routing có cơ chế **`before/after/filter/onError` riêng**. Không được giả định mọi `@ControllerAdvice @ExceptionHandler` lập tức bao trọn functional handler theo cùng thứ tự/semantics với `@RequestMapping` methods. Nên kiểm thử framework exception resolvers, functional `onError` và security filter riêng theo đúng Spring version đang chạy.

### 12.5. Response committed

Khi `ServerResponse` đã bắt đầu ghi body và response committed, không thể chắc chắn đổi status hay viết một JSON error object mới. Với streaming/file output, cần xác định trước validation, headers, authorization, timeout, và cách báo lỗi khi stream dang dở. Đối với DTO JSON nhỏ, lỗi serialize có thể xảy ra lúc converter ghi; đừng giả định toàn quá trình luôn xử lý được bằng status 400.

## 13. Các lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân điển hình | Hướng sửa |
| --- | --- | --- |
| Import sai `web.reactive.function.server` | Copy ví dụ WebFlux.fn | Dùng `web.servlet.function` |
| Không tìm thấy `request.bodyToMono()` | WebMvc.fn có `body(Class)`, không có bodyToMono | Dùng đúng API, không thêm WebFlux vô cớ |
| Handler không được gọi | `RouterFunction` không đăng ký bean, route/predicate sai | Tạo `@Bean RouterFunction<ServerResponse>` và test |
| POST JSON trả 404 | Path/method/predicate không match | Kiểm tra routing và contentType/accept predicates |
| `request.body(List.class)` trả `List<Map>` | Generic type erasure | Dùng `ParameterizedTypeReference<List<Dto>>` |
| JSON lỗi thành 500/response không như mong muốn | Converter exception không được map đúng | Route/onError/global error config phù hợp |
| `@Valid` đặt đâu đó không chạy | Bare `request.body(...)` không tự chạy validation như annotation MVC | Gọi Validator/manual validation |
| `String` bị serialize không đúng kiểu | Converter/media type không phù hợp | Kiểm tra Content-Type và converter ordering |
| 415 Unsupported Media Type | Request Content-Type không được converter hỗ trợ | Gửi đúng media type/thêm converter đúng |
| 406 Not Acceptable | Client Accept không khớp representation | Cấu hình produces/negotiation rõ |
| PUT/POST đọc body rỗng | Servlet filter đã tiêu thụ stream | Không đọc thô trước, dùng bounded cache-on-read |
| 201 thiếu Location | Response chỉ trả status 201 | Dùng `ServerResponse.created(uri)` |
| 204 mà client mong JSON | `noContent().build()` cố tình không có body | Chọn 200/201 nếu cần representation |
| Request JSON quá lớn gây heap pressure | Converter tạo object graph lớn | Payload size limit/streaming strategy |
| Batch ghi một phần trước khi validate xong | Validate và mutate xen kẽ | Validate cả batch trước, dùng transaction |
| Multipart upload path traversal | Tin original filename của client | Server-generated key/private storage |
| Security bypass | Có router route nhưng không có auth | Spring Security FilterChain + object ACL |
| @ControllerAdvice không bắt như tưởng tượng | Functional router có error processing riêng | Dùng router `onError` hoặc test resolver |
| Code dùng `@EnableWebMvc` làm mất Boot defaults | Tự quản lý MVC config không cần thiết | Giữ Boot auto-config và WebMvcConfigurer |
| Response lớn bị cache/log toàn byte[] | Dùng `readAllBytes`/response wrapper không giới hạn | Streaming + quotas + bounded observation |

## 14. Bảo mật và giới hạn tài nguyên

WebMvc.fn mang cùng bề mặt tấn công với annotated MVC endpoints:

1. **Authorization:** cả `GET /api/books/{id}` lẫn `POST /api/books` phải kiểm tra quyền theo resource/action; RouterFunction không tự cung cấp authentication.
2. **Mass assignment:** JSON body chỉ bind vào **DTO tối thiểu**, không bind nguyên domain entity nhạy cảm.
3. **DoS/payload:** giới hạn body size, số phần tử batch, chiều sâu JSON, thời gian đọc và concurrent requests ở proxy/container/parser.
4. **CSRF/CORS:** khi dùng session cookies hoặc cross-origin frontend, áp Spring Security CSRF và CORS allowlist đúng; HTTP router không tự giải quyết.
5. **Error exposure:** không trả raw stack trace, SQL fragments, filesystem paths hoặc tokens trong lỗi.
6. **Content type:** chặn binary/HTML/XML không nằm trong hợp đồng, kiểm tra sniffing và file upload riêng.
7. **Logging:** chỉ log metadata đã lọc/redact, tránh raw Authorization/Cookie/body chứa PII.
8. **Transactions:** một handler có thể gọi service `@Transactional`; bản thân `RouterFunction` không tự tạo giao dịch nguyên tử.
9. **Timeout/streaming:** với body lớn hoặc asynchronous publishers, xác định chính sách timeout/error/response commit; WebMvc.fn trên Servlet stack không tự biến socket writes thành non-blocking WebFlux I/O.
10. **Cache:** nếu response theo user, chọn `Cache-Control: private/no-store` và không để shared caches trộn dữ liệu qua cookies/headers.

**Không coi tên Functional là không có side effects:** handler có thể thay DB, ghi tệp, gửi email. Những side effects vẫn cần idempotency, validation, permissions và error recovery như mọi HTTP endpoint khác.

## 15. Checklist QA và code review

- [ ] Đúng Spring MVC stack; tất cả imports chính thuộc `web.servlet.function`.
- [ ] RouterFunction đã là Spring bean và route path/method/predicates đã test.
- [ ] Handler dùng `ServerRequest.body(Class)` hoặc `body(ParameterizedTypeReference)` để parse DTO.
- [ ] JSON `Content-Type` hợp lệ, JSON converter có mặt và các custom converters không phá defaults.
- [ ] Query/path params được parse và giới hạn giá trị.
- [ ] Validation tách khỏi converter; DTO không chứa trường bị client kiểm soát ngoài hợp đồng.
- [ ] Response status, `Content-Type`, `Location`, `Cache-Control` và body hợp lệ.
- [ ] Có 400/404/409/415/406/error policy tùy use case, không làm mọi lỗi thành 200.
- [ ] Batch input có size/quota và transaction nếu có nhiều writes.
- [ ] CORS/CSRF/auth/ACL nằm trong security architecture, không dựa vào route name.
- [ ] Kiểm thử MockMvc cả success, malformed body, generic list, negative cases.
- [ ] Không đọc cùng Servlet body hai lần hoặc log toàn payload không giới hạn.
- [ ] Không nhầm `ServerResponse.body(Object)` với `WebFlux.fn bodyValue/publisher-based API`.
- [ ] Với file/stream, kiểm soát response committed, buffering và timeout.
- [ ] Khi nâng Spring Boot 4/Spring Framework 7, kiểm tra lại các method signatures, starter/test packages và converter configuration APIs.

## 16. Tự kiểm tra kiến thức

**Câu 1.** Trong WebMvc.fn, đọc JSON body thành `CreateBook` bằng API nào?

**Đáp án:** `request.body(CreateBook.class)`. Converter phù hợp (thường Jackson) deserialize bytes; cần validation riêng.

**Câu 2.** Muốn đọc JSON array thành `List<CreateBook>` nhưng tránh bị `List<Map>`, làm gì?

**Đáp án:** `request.body(new ParameterizedTypeReference<List<CreateBook>>() {})` để giữ generic element type.

**Câu 3.** Trả `201 Created` kèm Location và JSON body?

**Đáp án:** `ServerResponse.created(URI.create("/api/books/42")).contentType(APPLICATION_JSON).body(book)`.

**Câu 4.** Trả `204 No Content`?

**Đáp án:** `ServerResponse.noContent().build()`. Không có JSON body theo 204 semantics.

**Câu 5.** `ServerResponse.ok().body(myPojo)` tự biến Java object thành JSON nếu không có converter không?

**Đáp án:** Không. Cần converter ghi tương thích với body type và media type.

**Câu 6.** Vì sao `request.body(List.class)` không lý tưởng cho `List<Book>`?

**Đáp án:** Type erasure làm mất generic element metadata; converter có thể tạo maps thay Book instances.

**Câu 7.** WebMvc.fn có dùng `bodyToMono()` không?

**Đáp án:** Không phải API chính của Servlet WebMvc.fn; đó là API WebFlux.fn. MVC dùng `body(Class)` và `body(ParameterizedTypeReference)`.

**Câu 8.** Có `request.body(Dto.class)` rồi thì Bean Validation/ACL tự chạy không?

**Đáp án:** Không. Converter parse data, còn validation và authorization phải được áp dụng rõ ràng.

**Câu 9.** Nếu predicate `contentType(APPLICATION_JSON)` không match thì chắc chắn server trả 415?

**Đáp án:** Không. Predicate có thể khiến router không tìm được handler, do đó HTTP status tùy mappings/error handling. Cần integration test nếu muốn 415/406 chính xác.

**Câu 10.** Vì sao nên test create endpoint rồi GET theo `Location` thay vì hardcode ID = 1?

**Đáp án:** In-memory store/DB sequence có thể đã tăng do tests khác. Header Location phản ánh ID thực của resource vừa tạo.

## 17. Tài liệu chính thức

- [Spring Framework 6.2 — Functional Endpoints (WebMvc.fn)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html): tổng quan RouterFunction/HandlerFunction/ServerRequest/ServerResponse, filters, nested routes và chạy trong DispatcherServlet.
- [Spring Framework 6.2 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/servlet/function/ServerRequest.html): `body(Class)`, `body(ParameterizedTypeReference)`, params, headers, bind.
- [Spring Framework 6.2 — ServerResponse.BodyBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/function/ServerResponse.BodyBuilder.html): `body(Object)`, generic body, response-building.
- [Spring Framework 6.2 — RouterFunctions.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/function/RouterFunctions.Builder.html): GET/POST, before/after/filter/onError.
- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html): converters, JSON/text/form/binary, configuration.
- [Spring Framework 6.2 — MVC Config Message Converters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html): `WebMvcConfigurer` và converter customization.
- [Spring Framework 6.2 — Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): HTTP errors và ProblemDetail.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): Spring MVC auto-configuration, HTTP converters và routing support.
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): để đối chiếu `bodyToMono` và HTTP message codecs, **không** copy WebFlux-specific imports vào Servlet MVC.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter chain, authentication, authorization và request processing.

**Kết luận:** trong Spring WebMvc.fn, `RouterFunction` tìm route, `HandlerFunction` xử lý `ServerRequest` và trả `ServerResponse`, còn `HttpMessageConverter` chuyển request/response body giữa bytes và Java values. Đọc DTO bằng `body(Class)`, đọc generic list bằng `body(ParameterizedTypeReference)`, tạo status/headers/body bằng `ServerResponse` và test thực tế bằng MockMvc. Phải tách bạch conversion với validation/security, đặt payload limits và không nhầm Servlet Functional MVC với Reactive WebFlux.fn.
