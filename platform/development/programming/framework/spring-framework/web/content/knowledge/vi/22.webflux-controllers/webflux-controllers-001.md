# Ánh xạ controller bằng annotation trong Spring WebFlux và các điểm chung với Spring MVC

> **Phạm vi:** Spring Framework 6.2.x, Spring Boot 3.5.x, Java 17+, annotation-based WebFlux trên reactive HTTP stack. Bài giải thích `@Controller`, `@RestController`, `@RequestMapping`, `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, `@DeleteMapping`; match URL/HTTP method/params/headers/consumes/produces; đọc URI/query/header/body; trả `Mono`, `Flux`, `ResponseEntity`; validation, errors, content negotiation và kiểm thử bằng `WebTestClient`. Đồng thời đối chiếu **những annotation dùng chung** với MVC và **những khác biệt thực sự** về dispatching, request-body decoding, I/O, method signatures và threading. Spring Framework 7/Spring Boot 4 có thể thêm APIs (ví dụ version mapping) và đổi tên starter/test package; ví dụ hoàn chỉnh dưới đây cố định tại **Boot 3.5 + WebFlux**.

## 1. Cùng syntax annotation, khác hạ tầng xử lý

Nếu đã học Spring MVC, bạn sẽ nhận ra hầu hết annotation:

```java
@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{id}")
    Mono<BookView> find(@PathVariable long id) {
        return service.find(id);
    }

    @PostMapping
    Mono<BookView> create(@RequestBody Mono<CreateBook> input) {
        return input.flatMap(service::create);
    }
}
```

**Đây là snippet**, cần khai báo `service`, DTO và imports; phần demo runnable nằm ở mục 11. Những annotation trên từ `org.springframework.web.bind.annotation` cũng được dùng ở Spring MVC. Tuy nhiên WebFlux **không** dùng `DispatcherServlet` để chạy handler; nó dùng các thành phần reactive như `DispatcherHandler` và `HandlerMapping` trên `ServerWebExchange`.

```text
HTTP request
     |
Reactor Netty / Servlet nonblocking adapter / server runtime
     |
HttpHandler, WebFilter chain
     |
DispatcherHandler                  <-- WebFlux
     |
RequestMappingHandlerMapping      <-- chọn @RequestMapping method
     |
RequestMappingHandlerAdapter      <-- resolve method arguments
     |
@Controller/@RestController method
     |
Mono<T> / Flux<T> / ResponseEntity<T>
     |
HandlerResultHandler + HttpMessageWriter
     |
HTTP response
```

**Trong MVC** đường đi tương ứng là `DispatcherServlet` → `HandlerMapping` → `HandlerAdapter` → `HttpMessageConverter` → Servlet response. **Trong WebFlux**, đọc/ghi body bằng `HttpMessageReader`/`HttpMessageWriter` từ reactive codecs và request được xử lý qua reactive HTTP abstractions.

### 1.1. Những điểm chung đáng nhớ

Cả WebFlux và MVC đều hỗ trợ:
- `@Controller` và `@RestController` (`@Controller` + `@ResponseBody`);
- khai báo route bằng `@RequestMapping` và shortcut HTTP-method annotations;
- URI templates `/{id}`, regex path variables, `@PathVariable`;
- `@RequestParam`, `@RequestHeader`, `@CookieValue`;
- `@RequestBody` và `@ResponseBody`;
- `ResponseEntity`, `@ResponseStatus`;
- validation Bean Validation, `@ControllerAdvice`/`@ExceptionHandler`;
- `@CrossOrigin`/CORS, content negotiation và conversion;
- `@ModelAttribute` cho form/model binding (với khác biệt runtime).

Chúng chia sẻ nhiều annotations của **module spring-web**, khiến code điều khiển request nhìn rất giống nhau. **Đừng suy luận runtime chỉ từ tên annotation:** controller trả `Mono<T>` vẫn có thể đang chạy trên Servlet MVC nếu Boot chọn WebMvc stack.

### 1.2. Khác biệt cốt lõi

| Chủ đề | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| Mô hình web | Servlet API; có blocking I/O | Reactive Streams, non-blocking HTTP I/O khi runtime hỗ trợ |
| Server phổ biến | Tomcat/Jetty Servlet | Reactor Netty; cũng hỗ trợ adapter khác |
| Request abstraction | `HttpServletRequest` | `ServerWebExchange`/`ServerHttpRequest` |
| HTTP body đọc | `HttpMessageConverter` | `HttpMessageReader` reactive codecs |
| HTTP body ghi | `HttpMessageConverter`; Servlet output writes có thể blocking | `HttpMessageWriter` reactive |
| `@RequestBody Mono<T>` | Không phải cách đọc body reactive tương đương | **Được hỗ trợ** |
| Return `Mono/Flux` | Có hỗ trợ adapter và Servlet async | Native reactive pipeline |
| Blocking JDBC/JPA | Tương đối phù hợp với MVC thread model | Không nên block event-loop; cân nhắc R2DBC/boundedElastic |
| Functional API | `web.servlet.function` | `web.reactive.function.server` |

WebFlux không có nghĩa một phép toán Java bình thường tự trở thành async. `Flux.just(...)` và `Mono.just(...)` có thể phát ngay trên thread subscription; WebClient/reactive drivers mang async I/O thật. Hạ tầng sẽ không sửa một đoạn code `Thread.sleep(5000)` đặt trong controller.

## 2. @Controller và @RestController

### 2.1. @RestController dành cho API JSON/HTTP body

```java
@RestController
class HelloController {
    @GetMapping("/hello")
    Mono<String> hello() {
        return Mono.just("Hello WebFlux");
    }
}
```

Với `@RestController`, giá trị trả về được ghi vào response body; một `String` là nội dung, **không phải view name**. Kiểu `Mono<String>` được WebFlux subscribe rồi encode khi value phát.

### 2.2. @Controller dùng cho view rendering hoặc @ResponseBody

```java
@Controller
class PageController {
    @GetMapping("/welcome")
    String page(Model model) {
        model.addAttribute("title", "Welcome");
        return "welcome";
    }
}
```

Đây là snippet, cần view resolver và template `welcome`. Một `String` trả từ `@Controller` thông thường được hiểu là **tên view**, trừ khi method có `@ResponseBody`. Để trả JSON trên class `@Controller`:

```java
@ResponseBody
@GetMapping("/api/ping")
Mono<Map<String,String>> ping() {
    return Mono.just(Map.of("status", "ok"));
}
```

Không nhầm `@ResponseBody` với `@RequestBody`: cái đầu áp vào **response**, cái sau đọc **request**.

## 3. @RequestMapping trên class và method

`@RequestMapping` có thể khai báo:
- `path`/`value`;
- `method` (HTTP method);
- `params` (điều kiện query parameters);
- `headers`;
- `consumes` (request Content-Type);
- `produces` (response media type).

```java
@RestController
@RequestMapping("/api/books")
class BooksController {

    @GetMapping("/{id}")
    Mono<BookView> get(@PathVariable long id) {
        // ...
    }

    @PostMapping(consumes="application/json",
                 produces="application/json")
    Mono<BookView> create(@RequestBody Mono<CreateBook> body) {
        // ...
    }
}
```

Các mapping ở method kế thừa prefix `/api/books` từ type level:
- GET `/api/books/10`;
- POST `/api/books` với Content-Type JSON, có thể trả JSON khi client Accept phù hợp.

**Không dùng `@RequestMapping` trống `method` khi chỉ muốn GET**, vì annotation đó mặc định không giới hạn HTTP method. Với REST, ưu tiên `@GetMapping`/`@PostMapping`/... để giảm bề mặt không mong muốn.

### 3.1. Shortcut annotations

| Annotation | HTTP method | Ý nghĩa ứng dụng |
| --- | --- | --- |
| `@GetMapping` | GET | Đọc dữ liệu |
| `@PostMapping` | POST | Tạo/chạy hành động |
| `@PutMapping` | PUT | Thay thế representation |
| `@PatchMapping` | PATCH | Thay đổi một phần |
| `@DeleteMapping` | DELETE | Xóa |
| `@RequestMapping(method=RequestMethod.HEAD)` | HEAD | Nếu cần custom HEAD route |

Chúng là **composed annotations** dựa trên `@RequestMapping`. Tránh đặt **hai mapping annotations** trên cùng một element (ví dụ `@GetMapping` và `@PostMapping` cùng method) vì Spring chỉ lấy một mapping và có thể cảnh báo. Nếu muốn một method phục vụ nhiều verbs, khai báo một `@RequestMapping(method={RequestMethod.GET, RequestMethod.POST})` với lý do rõ ràng hoặc tách methods.

### 3.2. HTTP HEAD và OPTIONS

Theo Spring WebFlux reference:
- `@GetMapping` hỗ trợ HEAD tương ứng mà thường không cần định nghĩa method riêng; response xử lý `Content-Length` và **không gửi body**.
- OPTIONS mặc định có thể trả `Allow` thể hiện methods được ánh xạ trên URL, trừ khi ứng dụng có handling riêng.
- Với `@RequestMapping` không khai báo method, Allow có thể bao gồm nhiều HTTP verbs ngoài ý định; vì vậy nên định danh verb thật.

Đừng dùng response GET thông thường rồi khẳng định HEAD sẽ có cùng body; HEAD chỉ mang metadata. CORS preflight OPTIONS còn liên quan CORS configuration/security filter khác.

## 4. URI templates và path patterns

### 4.1. Đọc path variables

```java
@GetMapping("/{bookId}")
public Mono<BookView> get(
        @PathVariable("bookId") long bookId) {
    return repository.findById(bookId)
            .map(BookView::from);
}
```

Snippet yêu cầu reactive repository/DTO. Nếu URL `/api/books/42`, `bookId=42`. String được chuyển sang `long` thông qua type conversion; path `/api/books/abc` gây lỗi conversion, không tự trở thành `0`.

Khai báo tên cụ thể `@PathVariable("bookId")` hữu ích nếu project không compile với `-parameters` hoặc Java variable có tên khác trong URI template.

### 4.2. PathPatternParser của WebFlux

Spring WebFlux dùng `PathPattern`/`PathPatternParser`. Một số mẫu:

| Pattern | Match ví dụ | Không match / lưu ý |
| --- | --- | --- |
| `/books/{id}` | `/books/42` | `/books/42/reviews` |
| `/files/*.png` | `/files/a.png` | `/files/a/b.png` |
| `/books/{name:[a-z-]+}` | `/books/spring-web` | `/books/Spring123` |
| `/assets/**` | `/assets/a/b.png` | Catch-all nên ít cụ thể hơn |
| `/assets/{*path}` | `/assets/a/b.png`, capture phần đuôi | Catch-all đặt ở cuối pattern |

Không dùng `/**/info` hoặc catch-all ở **giữa** như một pattern hợp lệ theo PathPattern rules. Nếu nhiều mappings có thể match, Spring so độ cụ thể; static paths thường được ưu tiên hơn variable/catch-all tương ứng. Tránh những mappings mơ hồ có cùng độ ưu tiên khiến ứng dụng không thể chọn handler.

### 4.3. Không mặc định suffix matching

WebFlux không áp kiểu suffix path matching cổ như `/person` tự match `/person.json`. Dùng `Accept`, `produces` hoặc query param được công bố nếu cần representation khác. Không coi phần `.json` trong URL là content negotiation an toàn một cách mặc định.

### 4.4. Prefix ở reverse proxy

Nếu proxy publish `/portal/api/books` nhưng backend chỉ match `/api/books`, đó là vấn đề proxy route rewrite/path prefix, không phải `@GetMapping` tự biết external prefix. Cấu hình gateway và forwarded headers theo trust boundary; không tự lấy raw `X-Forwarded-Prefix` do client gửi rồi ghép URI. Test URL public thực tế và link/redirect khi có prefix.

## 5. Điều kiện params, headers, consumes và produces

### 5.1. params: điều kiện để chọn method, không phải argument value

```java
@GetMapping(path = "/search", params = "mode=featured")
Mono<List<BookView>> featured() {
    return service.featured().collectList();
}
```

Mapping trên chỉ được xét khi query có `mode=featured`. Tương tự:
- `params="q"`: phải có query param q;
- `params="!q"`: không có q;
- `params="mode=featured"`: giá trị đúng cụ thể.

Trong khi đó:

```java
@GetMapping("/search")
Mono<List<BookView>> search(
        @RequestParam(name = "q", required = false) String q) {
    return service.search(q).collectList();
}
```

`@RequestParam` ở tham số **đọc giá trị**; nếu `required=true`, thiếu tham số gây lỗi argument resolution. Hai khái niệm “mapping điều kiện params” và “binding @RequestParam” liên quan nhưng không đồng nhất. Nếu có hai mappings chồng lấn, Spring sẽ chọn mapping cụ thể theo bộ so sánh điều kiện, chứ không đơn giản “method khai báo trước thắng”.

### 5.2. headers

```java
@GetMapping(path="/internal-report",
            headers="X-Client-Type=partner")
Mono<ReportView> report() {
    return service.report();
}
```

Đây là snippet; yêu cầu header `X-Client-Type: partner` để route match. **Không phải bảo mật:** client có thể tự đặt header; không dùng nó thay authentication, role hoặc tenant authorization. Dùng Spring Security và object-level ACL.

### 5.3. consumes: request Content-Type

```java
@PostMapping(path="/api/books",
             consumes=MediaType.APPLICATION_JSON_VALUE)
Mono<Void> ingest(@RequestBody Mono<CreateBook> command) {
    return command.flatMap(service::save).then();
}
```

`consumes` hẹp theo Content-Type (ví dụ application/json). Gửi `text/plain` tới route chỉ chấp nhận JSON thường dẫn đến **415 Unsupported Media Type**, tùy các mappings/error handling khác. Đừng dùng `consumes` để kiểm tra response type.

### 5.4. produces: response Accept

```java
@GetMapping(path="/api/books",
            produces=MediaType.APPLICATION_JSON_VALUE)
Flux<BookView> books() {
    return service.findAll();
}
```

`produces` nói controller có thể tạo JSON; client có `Accept: application/json` hoặc `*/*` thường match. Nếu client chỉ chấp nhận `application/xml` trong khi API chỉ hỗ trợ JSON, HTTP có thể là **406 Not Acceptable**. `produces` ảnh hưởng mapping/negotiation, nhưng không tự cài thêm XML codec hay đảm bảo Java type serialize thành JSON.

### 5.5. Mối quan hệ consumes và produces

| Client header | Controller mapping | Mục đích |
| --- | --- | --- |
| `Content-Type: application/json` | `consumes="application/json"` | Đọc request JSON |
| `Accept: application/json` | `produces="application/json"` | Trả response JSON |
| `Content-Type: text/plain` | JSON-only consumes | Thường 415 |
| `Accept: application/xml` | JSON-only produces | Thường 406 |
| `X-Mode: admin` | `headers="X-Mode=admin"` | Chỉ là điều kiện routing, không phải quyền |

Trong `@RequestMapping`, `consumes`/`produces` ở method-level có thể **override**, không nhất thiết gộp như các mapping conditions khác từ class-level. Với `headers` và `params`, hiểu các kết hợp điều kiện theo quy tắc framework và test bằng HTTP requests thực để tránh nhầm precedence.

## 6. Đọc request input qua WebFlux annotated arguments

Các annotation đọc URI, query, header và cookie có **cú pháp quen thuộc với MVC**. Trong WebFlux, đối số `ServerWebExchange` và reactive body arguments thể hiện sự khác biệt rõ nhất:

| Nhu cầu | Phương thức WebFlux hợp lý | Phân biệt với MVC |
| --- | --- | --- |
| ID từ URI | `@PathVariable("id") long id` | Đọc route metadata, không cần bọc `Mono<Long>` |
| Query, header, cookie | `@RequestParam`, `@RequestHeader`, `@CookieValue` | WebFlux `@RequestParam` chỉ đọc **query**, không ngầm hợp nhất form/multipart như Servlet request parameters |
| Nhìn toàn HTTP exchange | `ServerWebExchange` / `ServerHttpRequest` | Không tiêm `HttpServletRequest` của MVC vào WebFlux annotated handler |
| JSON request body | `@RequestBody Mono<Command>` | Sử dụng `HttpMessageReader`/decoder theo publisher khi WebFlux thực sự active |
| Form/multipart | `exchange.getFormData()`, `@RequestPart`, `FilePart` | Đường parser riêng; không coi form/multipart là một JSON request body |
| Principal | `Mono<Principal>`, `exchange.getPrincipal()` | Identity phải do security chain xác thực, không tin `X-User` client gửi |

Ví dụ giữ cơ chế routing và body ở một method:

```java
@PostMapping(path = "/api/books", consumes = "application/json")
Mono<BookView> create(
        @RequestHeader(name = "X-Trace", required = false) String trace,
        @RequestBody Mono<CreateBook> body) {
    // Trace là metadata chưa đáng tin, không được dùng làm credential.
    return body.flatMap(service::create);
}
```

Đây là **snippet**, cần `service`, DTO và imports. Trong WebFlux, `@RequestBody Mono<CreateBook>` được framework decode từ publisher của HTTP body; nó không phải cách binding dùng chung với Servlet MVC. Ngược lại, `@PathVariable`/`@RequestParam` được resolve từ URI/query metadata, nên không bọc tùy tiện vào reactive publisher.

Bài chuyên về **`ServerWebExchange` và tham số** trong chương giải thích đầy đủ repeated query values, attributes, principal, session, form/multipart APIs và những lỗi binding. Bài này tập trung vào **mapping chọn đúng handler trước** khi từng argument được resolve.

## 7. Chọn reactive return type và HTTP response

Kiểu trả về cũng là một phần hợp đồng API. Trong annotated WebFlux, publisher biểu diễn **sự sẵn sàng của data**, nhưng status/headers có thể được xác định ở thời điểm khác:

| Kiểu trả về | Điều được quyết định khi nào? | Nên dùng |
| --- | --- | --- |
| `BookView` / `Mono<BookView>` | Thông thường body được encode khi có kết quả | 200 với một DTO |
| `Flux<BookView>` | 0..N giá trị, codec phụ thuộc media type | Collection hoặc reactive stream |
| `ResponseEntity<BookView>` | Status/headers/body đã biết ngay | 201, 204, headers rõ ràng |
| `Mono<ResponseEntity<BookView>>` | Status/headers được chọn **sau** async lookup | 200/404 theo dữ liệu |
| `ResponseEntity<Flux<BookView>>` | Status/headers sớm, stream body tiếp theo | SSE, NDJSON, chuỗi data |
| `Mono<Void>` | Hoàn tất/error mà không phát value | Operation không trả representation |

Hai kiểu dễ nhầm nhất:

```java
// 200 hoặc 404 chỉ được quyết định khi lookup phát kết quả.
Mono<ResponseEntity<BookView>> deferred = service.find(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());

// 202 được quyết định ngay; Mono chỉ đại diện body sẽ phát sau.
ResponseEntity<Mono<BookView>> immediate =
        ResponseEntity.accepted().body(service.find(id));
```

Đây là snippets dùng `service`/`id` đã có. `Mono.empty()` **không có nghĩa tự động trả 404** trong mọi contract; API muốn 404 thì map thành `ResponseEntity.notFound()` hoặc phát một `ResponseStatusException` thích hợp. `Flux` cũng **không bảo đảm** mỗi phần tử được browser nhận ngay: media type (JSON array/SSE/NDJSON), codec, server và proxy buffering quyết định tính streaming thực tế.

Ví dụ `201 + Location`:

```java
return service.create(command)
        .map(saved -> ResponseEntity
                .created(URI.create("/api/books/" + saved.id()))
                .body(saved));
```

Chỉ xây public URL tuyệt đối từ origin/proxy đã được tin cậy, không từ raw `Host` hay `X-Forwarded-Host`. Bài `@RequestBody với Mono/Flux và ResponseEntity` chuyên sâu hơn về JSON/NDJSON wire format, backpressure, cancellation, error operators và tính chất của từng tổ hợp publisher.

## 8. Validation và lỗi HTTP trong annotated WebFlux

Annotation route **không xác minh nội dung đầu vào**. `@Valid @RequestBody Mono<Dto>` có thể kích hoạt Bean Validation sau khi decoder tạo DTO nếu project có validation provider và constraints, ví dụ `@NotBlank`. Spring WebFlux 6.1+ phân biệt lỗi validation của một argument (thường `WebExchangeBindException`) với method validation (thường `HandlerMethodValidationException`). Khi không có validator/constraints, chỉ thêm `@Valid` không tạo policy.

```java
@PostMapping("/api/books")
Mono<ResponseEntity<BookView>> create(
        @Valid @RequestBody Mono<CreateBook> body) {
    return body.flatMap(service::create)
            .map(saved -> ResponseEntity
                    .created(URI.create("/api/books/" + saved.id()))
                    .body(saved));
}
```

Đây là method minh họa trong controller có `service`, DTO và imports. **Bản chạy được ở mục 11** chủ động dùng manual validation, nên không cần thêm validation starter; muốn áp đoạn `@Valid` trên phải cung cấp annotations/validation provider tương ứng.

Xử lý lỗi HTTP nên có **tầng sở hữu rõ ràng**:

- Request JSON malformed, sai Content-Type, conversion thất bại hoặc thiếu field: phân biệt lỗi decoder/binding trước business logic, thường là 400/415 phù hợp.
- Không tìm thấy entity: map `Mono.empty()` thành 404 theo API contract, không dùng 200 rỗng nếu caller cần nhận diện absence.
- Nghiệp vụ ném exception có ý nghĩa: dùng `Mono.error(...)` hoặc `ResponseStatusException`, và `@ExceptionHandler`/`@RestControllerAdvice` nếu cần error representation thống nhất.
- Filter, authentication, gateway và response stream đã commit có **error boundaries khác**; advice ở controller không tự đảm bảo bắt tất cả.
- Không đưa exception message chứa secret, raw user input, stacktrace hoặc internal path vào JSON lỗi.

Bài về **binding/Bean Validation** phân tích các loại lỗi đầu vào và groups/custom validators; bài về **ProblemDetail/@RestControllerAdvice** phân tích RFC 9457, phạm vi error handling và status sau khi response commit. Ở bài routing này, chỉ cần nhớ mapping, decoding, validation và business failure là **những pha khác nhau**.

## 9. Quy tắc chọn handler khi có nhiều mappings

Các mapping conditions cùng tác động:
- URL path matching;
- HTTP verb;
- query params;
- headers;
- consumes/request Content-Type;
- produces/Accept.

Cùng một path có thể có GET và POST riêng. Hai GET cùng `/books` có thể phân biệt bằng `params="view=full"` hoặc `produces`; tuy nhiên ambiguous overlap vẫn có thể xảy ra nếu conditions không đủ tách biệt. Spring dùng một comparator có quy tắc specificity, **không dựa vào thứ tự methods trong source code**.

### 9.1. Static path vs variable path

```java
@GetMapping("/api/books/featured")
Mono<List<BookView>> featured() {
    return service.featured().collectList();
}

@GetMapping("/api/books/{id}")
Mono<BookView> byId(@PathVariable long id) {
    return service.find(id);
}
```

Nếu GET `/api/books/featured`, static path thường cụ thể hơn variable path. Dù thế, không nên để endpoint variable mong `id` là số nhưng không có regex khi dùng nhiều aliases; có thể ràng buộc:

```java
@GetMapping("/api/books/{id:\\d+}")
Mono<BookView> byNumericId(@PathVariable long id) {
    return service.find(id);
}
```

Trong Java string phải escape backslash thành `\\d+` để pattern nhận `\d+`. Ví dụ này là snippet; nếu copy trong IDE, đảm bảo literal đúng dấu escape.

### 9.2. Ambiguous mapping

Nếu hai methods cùng `@GetMapping("/api/books")` và không có conditions phân biệt, có thể gây startup failure hoặc lỗi chọn handler tùy thời điểm/framework config. Cách sửa không phải dựa vào tên class/file, mà xác định route contract cụ thể: tách path, method, params/headers/media type hoặc xóa duplicate.

### 9.3. @RequestMapping trên interface

Spring hỗ trợ annotation trên controller interface trong nhiều trường hợp, nhưng proxying (JDK vs class-based), mix annotation ở implementation/interface và cách detect handler có lưu ý. Nếu định nghĩa API contract ở Java interface, đặt annotation mapping/parameter annotations nhất quán và kiểm thử handler detection, không tùy tiện copy cùng annotation chồng lên implementation.

### 9.4. API versioning

Spring Framework 7 cung cấp attribute `version` trên request mappings và khả năng cấu hình API version resolver cho WebFlux. **Không dùng API mới này trong Spring Framework 6.2 / Boot 3.5**, vì mã không compile. Với stack 6.2, version routes thường là `/api/v1/books`, header conditions, media types hoặc custom strategy. Nếu nâng Spring 7, đọc lại API version strategy/version deprecation docs tương ứng thay vì chỉ thêm `version="1.0"` vào project cũ.

## 10. Những ranh giới quan trọng giữa WebFlux và MVC

### 10.1. Thêm WebFlux starter không chắc đã kích hoạt WebFlux server

Spring Boot 3.5 docs nêu: nếu project có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot **ưu tiên auto-configure Spring MVC** vì nhiều người dùng WebClient trong app MVC. Để demo WebFlux đúng nghĩa, chỉ dùng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Nếu dự án cố tình cần reactive web type dù có cả starters, có thể cấu hình `SpringApplication.setWebApplicationType(WebApplicationType.REACTIVE)`, nhưng không coi đó là giải pháp thay việc phân tích dependencies/config. Cần xác nhận DispatcherHandler/WebFlux codecs thực sự được sử dụng.

### 10.2. Không chạy blocking operations trên event-loop

```java
// Anti-pattern trong WebFlux controller.
@GetMapping("/blocking")
Mono<BookView> bad() {
    return Mono.just(jdbcRepository.findBook(42));
}
```

Lời gọi `jdbcRepository.findBook(42)` chạy **trước** khi Mono được tạo, có thể block request event-loop. Tương tự, `Mono.fromCallable(...)` không tự chuyển threads. Bridge có giới hạn:

```java
Mono<BookView> safer = Mono
        .fromCallable(() -> jdbcRepository.findBook(42))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây chỉ là adapter cho blocking code, không làm JDBC non-blocking. Với ứng dụng chủ yếu JPA/JDBC, Spring MVC có thể đơn giản và phù hợp hơn. Với WebFlux high concurrency, ưu tiên reactive HTTP client/driver, cân nhắc boundedElastic quotas và overload protection.

### 10.3. Servlet filters và WebFilter

Trong MVC, authentication/tracing có thể dùng `jakarta.servlet.Filter` và `OncePerRequestFilter`. Trong WebFlux, dùng `org.springframework.web.server.WebFilter` và Spring Security **reactive SecurityWebFilterChain** theo stack. Không sao chép một Servlet Filter rồi kỳ vọng tự chạy trong Netty WebFlux app.

### 10.4. ThreadLocal không tự truyền qua reactive boundaries

`SecurityContextHolder`, MDC, LocaleContextHolder và request-scoped ThreadLocal của MVC không tự bảo đảm hiện diện trên các Reactor schedulers. WebFlux thường dùng Reactor Context/context propagation và Spring Security reactive context; dữ liệu principal/tenant phải được truy cập theo API phù hợp. Không cho phép client tự chọn tenant ID từ header khi thiếu authorization.

### 10.5. Data binding khác body JSON decoding

`@ModelAttribute` bind request parameters/URI variables trong model; `@RequestBody` deserialize HTTP body bằng codec. Dùng DTO rõ ràng và chỉ chấp nhận fields thuộc contract; Spring Boot/WebFlux có khả năng constructor binding và validator, nhưng **không nên bind JPA entity trực tiếp** chứa `role`, `ownerId`, `price` do server quản lý.

## 11. Demo đầy đủ: Spring Boot 3.5 / Java 17 / WebFlux

Tạo REST API sách bằng annotation WebFlux, với:
- GET `/api/books`: trả Flux JSON;
- GET `/api/books/{id}`: trả Mono<ResponseEntity<BookView>>, chọn 200/404;
- GET `/api/books/search?mode=featured`: mapping có `params`;
- POST `/api/books`: nhận `@RequestBody Mono<CreateBook>`, validate và trả 201 + Location;
- PUT `/api/books/{id}`: thay title, trả 200/404;
- DELETE `/api/books/{id}`: trả 204/404.

Store là ConcurrentHashMap in-memory, đủ minh họa route/binding/response; không phải giải pháp persistence/auth production.

### 11.1. Project dependency

Từ [Spring Initializr](https://start.spring.io/), tạo Maven project **Spring Boot 3.5.x**, **Java 17+**, dependency **Spring Reactive Web**. Trong `pom.xml` do Initializr sinh có dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Đây là **POM fragment**, Initializr cung cấp parent/BOM/plugins đầy đủ. Reactor Core/Jackson/WebFlux/Reactor Netty được kéo vào theo starter. Không cần thêm `spring-boot-starter-web`.

### 11.2. File DemoApplication.java độc lập

Lưu **toàn bộ** đoạn sau vào `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

record BookView(long id, String title) {}
record CreateBook(String title) {}

@Service
class BookStore {

    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, BookView> books =
            new ConcurrentHashMap<>();

    Flux<BookView> list(int limit) {
        return Flux.defer(() -> Flux.fromIterable(
                books.values().stream()
                        .sorted(Comparator.comparingLong(BookView::id))
                        .limit(limit)
                        .toList()));
    }

    Mono<BookView> find(long id) {
        return Mono.defer(() -> Mono.justOrEmpty(books.get(id)));
    }

    Mono<BookView> create(CreateBook command) {
        return Mono.fromSupplier(() -> {
            long id = nextId.incrementAndGet();
            BookView saved = new BookView(
                    id, command.title().trim());
            books.put(id, saved);
            return saved;
        });
    }

    Mono<BookView> replace(long id, CreateBook command) {
        return Mono.defer(() -> Mono.justOrEmpty(
                books.computeIfPresent(
                        id,
                        (key, previous) ->
                                new BookView(id, command.title().trim()))));
    }

    Mono<Boolean> delete(long id) {
        return Mono.fromSupplier(() -> books.remove(id) != null);
    }
}

@RestController
@RequestMapping(path = "/api/books")
class BookController {

    private final BookStore store;

    BookController(BookStore store) {
        this.store = store;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<BookView> list(
            @RequestParam(name = "limit", defaultValue = "20") int limit) {

        if (limit < 1 || limit > 100) {
            return Flux.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "limit must be 1..100"));
        }

        return store.list(limit);
    }

    @GetMapping(path = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<BookView>> get(
            @PathVariable("id") long id) {

        return store.find(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping(path = "/search", params = "mode=featured",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<BookView> featured() {
        // Query param mode=featured là điều kiện chọn mapping.
        return store.list(5);
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<BookView>> create(
            @RequestBody Mono<CreateBook> body) {

        return body
                .switchIfEmpty(Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "JSON body required")))
                .flatMap(command -> {
                    validate(command);
                    return store.create(command);
                })
                .map(saved -> ResponseEntity
                        .created(URI.create("/api/books/" + saved.id()))
                        .body(saved));
    }

    @PutMapping(path = "/{id}",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<BookView>> replace(
            @PathVariable("id") long id,
            @RequestBody Mono<CreateBook> body) {

        return body
                .switchIfEmpty(Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "JSON body required")))
                .flatMap(command -> {
                    validate(command);
                    return store.replace(id, command);
                })
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @DeleteMapping("/{id}")
    public Mono<ResponseEntity<Void>> delete(
            @PathVariable("id") long id) {
        return store.delete(id)
                .map(deleted -> deleted
                        ? ResponseEntity.<Void>noContent().build()
                        : ResponseEntity.<Void>notFound().build());
    }

    private static void validate(CreateBook command) {
        if (command == null
                || command.title() == null
                || command.title().isBlank()
                || command.title().length() > 120) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "title is required (1..120 characters)");
        }
    }
}
```

### 11.3. Giải thích tính chạy được và giới hạn

- Một Java file có đúng một public class `DemoApplication`; các `record` và component classes còn lại là package-private, hợp lệ với Java 17.
- `@SpringBootApplication` component-scan thấy `BookStore`/`BookController` vì cùng package.
- Project dùng `spring-boot-starter-webflux` và không có MVC starter nên mặc định chạy WebFlux server (thường Reactor Netty).
- `BookStore` dùng `ConcurrentHashMap` và `AtomicLong`; đó là in-memory synchronization phục vụ demo, **không phải reactive database**. Mọi operation ở đây rất nhỏ, không block I/O; `Mono.defer/Mono.fromSupplier` chỉ trì hoãn công việc đến subscription, **không tự làm IO non-blocking**.
- `GET /api/books` sử dụng `Flux.defer` tạo snapshot list tại subscription, sắp xếp theo ID; database production nên dùng reactive repository/R2DBC với pagination.
- `@RequestBody Mono<CreateBook>` minh họa API đặc thù của WebFlux. Chỉ có JSON DTO tối thiểu; không bind trực tiếp entity có fields nhạy cảm.
- `Mono<ResponseEntity<BookView>>` cho phép quyết định 200 hoặc 404 dựa trên async result.
- `POST` dùng `ResponseEntity.created(...)` tạo status 201 + Location tương đối.
- `PUT` thay một title trên một record in-memory; đó là ví dụ **replace một representation đơn giản**, không có ETag/If-Match. Nếu nhiều clients cùng sửa, cần optimistic versioning ở DB để tránh lost update.
- Không có authentication, CSRF, CORS, database, transaction hoặc metrics; **không deploy demo như production API công khai**.
- Tất cả methods đều dùng explicit HTTP annotations; `@RequestMapping` class-level chỉ làm prefix.

### 11.4. Chạy server

Trong root của project do Initializr tạo:

```bash
# Linux / macOS
./mvnw spring-boot:run

# Windows (PowerShell/CMD)
mvnw.cmd spring-boot:run
```

Nếu không đổi port, server nghe ở `http://localhost:8080`.

### 11.5. GET danh sách rỗng

```bash
curl -i -H 'Accept: application/json' \
  'http://localhost:8080/api/books?limit=10'
```

Dự kiến status 200, JSON body:

```json
[]
```

List rỗng là một response hợp lệ; không cần 404. Header Content-Type JSON được xác định qua `produces` và codec.

### 11.6. POST tạo sách

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '{"title":"Spring WebFlux"}'
```

Dự kiến sau khởi động mới, chưa có create khác:

```http
HTTP/1.1 201 Created
Location: /api/books/1
Content-Type: application/json

{"id":1,"title":"Spring WebFlux"}
```

Các header như Date/Transfer-Encoding và JSON whitespace có thể khác theo runtime. Nếu đã tạo sách khác, ID không nhất thiết 1. HTTP Location nên đọc từ header thật.

### 11.7. GET theo ID, 404

```bash
curl -i 'http://localhost:8080/api/books/1'
curl -i 'http://localhost:8080/api/books/9999'
```

Với ID 1 tồn tại, response 200 JSON `{"id":1,"title":"Spring WebFlux"}`. Với ID 9999 chưa có, status **404** vì `defaultIfEmpty(ResponseEntity.notFound().build())`.

Đây là điểm khác với việc return `Mono.empty()` đơn giản: API đã chỉ rõ status 404.

### 11.8. GET search theo params condition

```bash
curl -i 'http://localhost:8080/api/books/search?mode=featured'
```

Route `/search` có điều kiện query `mode=featured` và static path cụ thể. Handler trả tối đa 5 bản ghi. Nếu không có `mode=featured`, mapping đó không thỏa; status thực tế tùy các mappings còn lại và error handling, không giả định response từ `featured()` sẽ được gọi.

### 11.9. PUT thay nội dung

```bash
curl -i -X PUT 'http://localhost:8080/api/books/1' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '{"title":"WebFlux Updated"}'
```

Nếu ID tồn tại: status **200**, body JSON title mới. Nếu ID không tồn tại: status **404**. Nếu title blank hoặc hơn 120 ký tự: **400** do manual validation.

**Về nghiệp vụ:** ví dụ không có If-Match/ETag nên có thể lost update trong concurrent edits. Với project thật, bổ sung version/CAS/optimistic lock thay vì dựa vào reactive return type để ngăn race.

### 11.10. DELETE

```bash
curl -i -X DELETE 'http://localhost:8080/api/books/1'
```

Lần đầu nếu ID 1 tồn tại: **204 No Content**. Gửi lại cùng ID sau khi đã xóa: **404 Not Found** theo contract demo. Đừng kỳ vọng body JSON trên 204.

### 11.11. Các trường hợp lỗi

**Sai limit:**

```bash
curl -i 'http://localhost:8080/api/books?limit=0'
```

Dự kiến status 400 (range check). Với `limit=xyz`, argument conversion có thể trả 400 trước khi vào method.

**JSON thiếu title:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary '{}'
```

Dự kiến 400. Validation manual trong `validate` không phụ thuộc bean-validation starter.

**Content-Type sai:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: text/plain' \
  --data-binary 'hello'
```

Vì `@PostMapping(consumes="application/json")`, response thường là **415** nếu không có mapping khác.

**Accept không hỗ trợ:**

```bash
curl -i -H 'Accept: application/xml' \
  'http://localhost:8080/api/books'
```

Mapping `produces="application/json"` không chấp nhận chỉ XML, nên thường **406 Not Acceptable**, nếu không có route XML khác.

### 11.12. Windows PowerShell và curl

PowerShell có thể alias `curl` thành cmdlet riêng. Dùng `curl.exe`:

```powershell
curl.exe -i "http://localhost:8080/api/books?limit=10"
curl.exe -i "http://localhost:8080/api/books/9999"
```

Với request JSON, tạo file `request.json` UTF-8:

```json
{"title":"Spring WebFlux"}
```

Gửi:

```powershell
curl.exe -i -X POST "http://localhost:8080/api/books" -H "Content-Type: application/json" -H "Accept: application/json" --data-binary "@request.json"
```

Tránh lỗi escape dấu quote native process args khác nhau giữa các phiên bản PowerShell.

## 12. Kiểm thử WebFlux bằng WebTestClient

### 12.1. Dependencies

Thêm test starter cho Spring Boot **3.5**:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Đây là fragment POM. Với code Boot 4 phải xem modular test starter và package imports mới; không trộn tùy tiện imports Boot 3 vào Boot 4.

### 12.2. WebTestClient integration test

Lưu `src/test/java/com/example/demo/BookControllerTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BookControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void canCreateAndRead() {
        String location = client.post()
                .uri("/api/books")
                .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .accept(org.springframework.http.MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":\"WebFlux Test\"}")
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectBody()
                .jsonPath("$.title").isEqualTo("WebFlux Test")
                .returnResult()
                .getResponseHeaders()
                .getLocation()
                .toString();

        client.get().uri(location)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("WebFlux Test");
    }

    @Test
    void missingBookReturns404() {
        client.get().uri("/api/books/999999")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void badTitleReturns400() {
        client.post().uri("/api/books")
                .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":\"   \"}")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void wrongContentTypeIsRejected() {
        client.post().uri("/api/books")
                .contentType(org.springframework.http.MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isEqualTo(415);
    }

    @Test
    void wrongAcceptIsRejected() {
        client.get().uri("/api/books")
                .accept(org.springframework.http.MediaType.APPLICATION_XML)
                .exchange()
                .expectStatus().isEqualTo(406);
    }

    @Test
    void badLimitReturns400() {
        client.get().uri("/api/books?limit=0")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

**Lưu ý quan trọng về test này:** API `EntityExchangeResult<byte[]> result = ...expectBody().returnResult()` có method `getResponseHeaders()` để đọc Location. `getLocation()` trả URI khi header tồn tại; nếu test không có Location, assertion trước sẽ báo. Các tests không giả định ID=1 vì store in-memory có thể đã có các test POST khác cùng context.

`WebTestClient` có thể hoạt động với server thật như test RANDOM_PORT hoặc bind-to-controller/router; trong ví dụ dùng RANDOM_PORT để kiểm tra network/server/reactive codecs đầy đủ.

### 12.3. Điều cần kiểm tra thêm

- `GET /api/books/search?mode=featured` match đúng và không bị variable path nuốt.
- Duplicate/conflicting mappings không xảy ra.
- HEAD/OPTIONS behaviors theo WebFlux contract.
- JSON malformed và request quá lớn không được trả 200.
- Params/header conditions: có/không có/wrong value.
- Query/path conversion errors và error body.
- Validation Bean Validation (nếu thêm `@Valid`/constraints).
- Authentication/authorization/CORS/CSRF khi bảo vệ endpoints.
- SSE/NDJSON theo `produces` và response streaming/cancellation.
- Concurrency writes và optimistic versioning trong DB, không chỉ kiểm tra in-memory map.

### 12.4. Chạy tests

```bash
# Linux/macOS
./mvnw test

# Windows
mvnw.cmd test
```

Nếu CI có tests chạy song song và dùng chung in-memory state, đừng assert ID cứng hoặc xóa tài nguyên thuộc test khác. Dùng test fixture/isolated context hoặc test database rollback/cleanup phù hợp.

## 13. Lỗi thường gặp khi chuyển controller MVC sang WebFlux

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Controller trông giống WebFlux nhưng đang chạy MVC | Project có cả web và webflux starters | Kiểm tra web application type, chọn WebFlux server rõ |
| `@RequestBody Mono<T>` không hoạt động | Servlet MVC đang handle request | Dùng WebFlux đúng stack hoặc DTO đồng bộ cho MVC |
| `HttpServletRequest` không resolve | WebFlux không dùng Servlet API làm abstraction chung | Dùng `ServerWebExchange`/`ServerHttpRequest` |
| `@GetMapping` không match | Class path + method path sai, version, path pattern | Test URI thực, method và conditions |
| GET/POST bị match sai | Dùng bare `@RequestMapping` quá rộng | Shortcut mapping theo verb |
| Path regex trong Java sai escape | `\d+` chưa escape trong string literal | Dùng `\\d+` trong Java |
| `GET /books/featured` vào `/{id}` | Overlapping paths/conversion | Static path/regex route, test specificity |
| Sai Content-Type với POST | `consumes` không thỏa | Gửi JSON hoặc khai báo đúng media |
| `Accept: xml` trả 406 | `produces` chỉ JSON | Thống nhất client Accept/API representation |
| Mono.empty trả 200 rỗng | Không map absence thành HTTP 404 | ResponseEntity.notFound/switchIfEmpty |
| Có `Flux<T>` nhưng output không như kỳ vọng | Codecs/media type/stream flush | Test JSON/SSE/NDJSON đúng media |
| `@Valid` không phát huy | Thiếu validation provider/constraints | Khai báo constraints/validation starter và test |
| @ControllerAdvice không bắt đúng lỗi | Copy loại exception của MVC | WebExchangeBindException/HandlerMethodValidationException |
| WebFlux response bị nghẽn | Dùng JDBC/JPA/Thread.sleep/block() trên event loop | Reactive I/O hoặc boundedElastic có giới hạn |
| CORS preflight bị chặn | Không có CORS/security cấu hình đúng | @CrossOrigin/Global CORS/SecurityWebFilterChain |
| Controller trả sai mã 201/404/204 | Chỉ return body value | Dùng ResponseEntity/ResponseStatusException |
| Mapping duplicate startup fail | Methods cùng path/verb/conditions | Tách routes/conditions, test |
| Controller tạo Location domain giả | Tin Host/X-Forwarded-Host thô | Canonical public base URL + trusted proxy |
| Header điều kiện bị xem như authorization | Client tự gửi được custom headers | Spring Security + ACL |
| Memory quá lớn với Flux | collectList() trên nguồn lớn/infinite | Pagination/bounded streaming |
| HTTP error sau SSE committed | Không thể đổi response status đã gửi | Event protocol/close/reconnect |

## 14. CORS, Security và trách nhiệm API

Annotation mapping **chỉ quyết định route**, không xác thực người gọi. Cần:
1. Spring Security reactive `SecurityWebFilterChain` để kiểm soát authentication và endpoint authorization.
2. Kiểm tra object ownership/tenant/ACL trong service; `@PathVariable id` không tự đảm bảo được phép truy cập.
3. CSRF phù hợp khi browser dùng cookie/session credentials cho state-changing POST/PUT/DELETE.
4. CORS allowlist origin/headers/methods; `@CrossOrigin` không thay authentication.
5. DTO input allowlist, validation và chống mass assignment; không cho client tự đặt `role`, `ownerId` hoặc `price` server-managed.
6. Payload size/codec max in-memory, file upload limits, quota, rate limiting và request timeout.
7. Fail closed khi permission service lỗi; đừng fallback quyền mở bằng `onErrorReturn(true)`.
8. Chống open redirect/Host-header poisoning khi tạo absolute link trong Location.
9. Error responses không tiết lộ stacktrace/secrets/SQL/tenant data.
10. Logging/tracing reactive context propagation; không để token/PII trong URL/log.

### 14.1. Giới hạn codec buffer

WebFlux có max-in-memory-size cho codecs và Spring Boot hỗ trợ cấu hình, ví dụ trong Boot 3.5:

```properties
spring.codec.max-in-memory-size=256KB
```

Đây là một **codec buffering limit**, không phải hard cap cho mọi HTTP bytes, request streaming, file upload hoặc toàn hệ thống. Với large request bodies phải có chính sách bổ sung tại gateway/server/decoder và không tự gọi `collectList()` trên stream không giới hạn.

### 14.2. @CrossOrigin

```java
@CrossOrigin(origins="https://frontend.example.test")
@GetMapping("/api/public")
Mono<String> publicEndpoint() {
    return Mono.just("ok");
}
```

Đây là snippet minh họa allowlist origin. Origin này là host ví dụ, không phải domain thật. Nếu có Spring Security, CORS integration/phương thức OPTIONS phải được cấu hình nhất quán. Không phản chiếu tùy tiện mọi Origin kèm credentials.

## 15. Checklist QA trước khi phát hành

- [ ] Project thực sự chạy WebFlux reactive server, không vô ý auto-config MVC do hai starters.
- [ ] Có class-level prefix và method-level verbs đúng; không dùng `@RequestMapping` không giới hạn method ngoài ý định.
- [ ] Các path variables/regex và catch-all patterns dùng PathPatternParser hợp lệ.
- [ ] Params, headers, consumes, produces được xác định và test.
- [ ] `Content-Type` nói về request; `Accept` nói về response.
- [ ] `@RequestBody Mono<Dto>` được decode bằng WebFlux codecs; DTO không chứa field nhạy cảm.
- [ ] `@Valid`/manual validation và HTTP lỗi 400/404/406/415 theo contract.
- [ ] Return `Mono<ResponseEntity<T>>` khi status/headers phụ thuộc kết quả async.
- [ ] Có thể stream Flux/SSE/NDJSON đúng media type; cancellation/errors sau commit được xử lý.
- [ ] Không đặt blocking JDBC/Thread.sleep/Mono.block trong event loop.
- [ ] SecurityWebFilterChain/CORS/CSRF/ACL/rate limits phù hợp cả GET/POST/PUT/DELETE.
- [ ] Không ghép Host/Forwarded headers thô thành Location/callback URLs.
- [ ] Test bằng WebTestClient với JSON, route specificity, error cases và wrong media.
- [ ] Nếu cần API version mapping, phân biệt Spring Framework 7 với 6.2.
- [ ] Metrics/logs theo dõi latency, codec buffer memory, 4xx/5xx, active requests, client disconnect.
- [ ] Data race/update đồng thời giải quyết trong repository/transaction, không dựa vào Reactor return types.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `@RestController` trong MVC và WebFlux có cùng ý nghĩa cơ bản không?

**Đáp án:** Có. Nó tương đương `@Controller` + `@ResponseBody`; nhưng bên dưới dùng hạ tầng request/response khác.

**Câu 2.** `@RequestMapping("/api/books")` không chỉ định HTTP method trên method handler có thể nguy hiểm chỗ nào?

**Đáp án:** Nó có thể match nhiều HTTP methods thay vì chỉ GET; nên dùng `@GetMapping`/`@PostMapping`/... khi muốn route hẹp.

**Câu 3.** Nếu client gửi JSON tới POST, annotation nào kiểm tra kiểu input, annotation nào thể hiện kiểu response?

**Đáp án:** `consumes="application/json"` kiểm tra request Content-Type, `produces="application/json"` cho response Accept/representation.

**Câu 4.** Khi nào dùng `@RequestBody Mono<CreateBook>`?

**Đáp án:** Khi chạy WebFlux reactive stack và muốn decode request body bất đồng bộ; không coi đó là signature tương đương được MVC hỗ trợ.

**Câu 5.** `Mono.empty()` có phải luôn trả 404 không?

**Đáp án:** Không. Dùng `switchIfEmpty(Mono.error(new ResponseStatusException(404)))` hoặc `Mono<ResponseEntity<T>>` với notFound.

**Câu 6.** WebFlux và MVC cùng hỗ trợ `@GetMapping`, vậy WebFlux có dùng `DispatcherServlet` không?

**Đáp án:** Không. WebFlux dùng `DispatcherHandler` trên reactive stack.

**Câu 7.** Có cả `spring-boot-starter-web` và `spring-boot-starter-webflux` trong Boot 3.5 thì mặc định nghiêng về framework nào?

**Đáp án:** Spring MVC, trừ khi chủ động ép reactive web application type.

**Câu 8.** `@RequestHeader("X-Role") String role` có chứng minh user là admin không?

**Đáp án:** Không. Header do client tự gửi; phải xác thực/ủy quyền bằng security framework và quyền nguồn dữ liệu.

**Câu 9.** `@Valid` với WebFlux có thể dẫn đến loại exception nào?

**Đáp án:** `WebExchangeBindException` cho argument validation, `HandlerMethodValidationException` khi method validation áp dụng; kiểm tra theo signature và Spring version.

**Câu 10.** Làm sao xác minh annotation route hoạt động đúng?

**Đáp án:** Dùng WebTestClient integration tests cho path, method, params, headers, Content-Type, Accept, đúng status/body và negative cases.

## 17. Tài liệu chính thức

- [Spring Framework 6.2 — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller.html): mô hình @Controller/@RestController, method signatures.
- [Spring Framework — Mapping Requests (WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html): class/method mappings, URI patterns, params/headers/consumes/produces, HEAD/OPTIONS.
- [Spring Framework 6.2 — Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/arguments.html): @PathVariable, @RequestParam, @RequestHeader, ServerWebExchange và reactive arguments.
- [Spring Framework 6.2 — Request Body](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html): @RequestBody Mono/Flux, HttpMessageReader, validation.
- [Spring Framework 6.2 — Return Values](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html): Publisher, ResponseEntity, HTTP response writing.
- [Spring Framework 6.2 — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html): @Valid, WebExchangeBindException, HandlerMethodValidationException.
- [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux.html): nonblocking reactive architecture và MVC comparison.
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): dependency, starter choice, WebFlux config/codecs.
- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): @CrossOrigin, global CORS.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): SecurityWebFilterChain và reactive authentication/authorization.
- [Spring Framework — Spring MVC Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html): nguồn để đối chiếu annotations dùng chung và Servlet differences.

**Kết luận:** học controller WebFlux từ nền tảng MVC là hợp lý vì cú pháp `@RestController`/`@RequestMapping`/`@GetMapping`/`@RequestBody` rất tương đồng. Nhưng để xây ứng dụng reactive đúng, cần nhận biết `DispatcherHandler`, `ServerWebExchange`, `HttpMessageReader/Writer`, `@RequestBody Mono<T>` và native `Mono/Flux` return semantics; tuyệt đối không block event-loop, không bỏ security/validation, và phải kiểm thử route matching lẫn content negotiation bằng HTTP thực. **Giống annotation không có nghĩa giống runtime I/O**.
