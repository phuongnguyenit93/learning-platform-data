# Đọc lỗi 404, 405, 406, 415, validation và ngoại lệ bất đồng bộ trong Spring Web

## 1. Mục tiêu: chẩn đoán từ HTTP request tới nơi Spring xử lý

Khi một API Spring MVC trả về lỗi, **HTTP status chỉ là triệu chứng**. Để tìm đúng nguyên nhân cần xem request đã đi tới bước nào: chọn handler, khớp method, kiểm tra media type, deserialize/bind tham số, validation, gọi controller, xử lý bất đồng bộ, hay ghi response.

Bài này sử dụng **Spring MVC / Servlet stack**, Java 17+, Spring Framework 6.x (ví dụ Spring Boot 3.x). Với Spring WebFlux, khái niệm HTTP tương tự nhưng exception classes và execution model có khác biệt được nêu cuối bài.

Một quy trình điều tra hữu ích:

1. Ghi nhận **method + URI + query string** mà client thật sự gửi; phân biệt endpoint của Spring với URL public sau proxy/context-path.
2. Ghi lại **`Content-Type`** (request body thuộc định dạng nào), **`Accept`** (client muốn nhận định dạng nào), `Origin` nếu có CORS, và chính xác body được gửi.
3. Xem HTTP status, response headers (`Allow`, `Accept`, `Content-Type`), response body/`ProblemDetail` và request/correlation ID.
4. Đối chiếu các điều kiện `@RequestMapping`/`@GetMapping`/`@PostMapping`: path, HTTP method, `params`, `headers`, `consumes` và `produces`.
5. Nếu request đã tới controller, xem lỗi chuyển đổi dữ liệu, Bean Validation, nghiệp vụ và exception resolver; nếu bất đồng bộ, xem cả **async dispatch**, timeout và exception phát sinh ở worker thread hoặc publisher.

Không đoán “404 là sai controller” hay “400 là validation” trước khi xác minh vị trí lỗi. Một vấn đề có thể bị thay đổi biểu hiện bởi Spring Security, filter, servlet container, proxy hoặc một `@ControllerAdvice` custom.

## 2. Sơ đồ đường đi request và bảng phân biệt nhanh

~~~text
HTTP client
  |
  v
Reverse proxy / Servlet filters / Spring Security
  |
  v
DispatcherServlet + HandlerMapping
  |-- không tìm handler/tài nguyên ----------------> 404
  |-- path đúng, HTTP method không phù hợp -------> 405
  |-- @RequestMapping consumes không khớp --------> 415
  |-- @RequestMapping produces không khớp --------> 406
  |
  v
HandlerAdapter + argument resolvers + converters
  |-- body JSON hỏng, thiếu tham số, type mismatch -> thường 400
  |-- @Valid, method validation thất bại ----------> thường 400
  |
  v
Controller / service
  |-- business exception -------------------------> advice/resolver
  |-- Callable / DeferredResult / Mono
  |      |-- deferred exception -------------------> async dispatch -> advice
  |      |-- timeout ------------------------------> timeout handling
  |
  v
ReturnValueHandlers + HttpMessageConverter
  |-- không tìm converter ghi theo Accept --------> 406 / write failure
  v
HTTP response
~~~

Đây là sơ đồ thường gặp, **không phải bảo đảm rằng exception luôn rơi đúng một loại**: thứ tự kiểm tra mapping có thể phụ thuộc các điều kiện khác và MVC configuration. Ví dụ lỗi serialization cuối response có thể gây `HttpMessageNotWritableException`, thường là lỗi server chứ không mặc định là 406.

| Status | Tình huống thường gặp | Exception/đầu mối trong MVC | Điều cần nhìn ngay |
| --- | --- | --- | --- |
| `404 Not Found` | Không có handler cho path; static resource không tồn tại; nghiệp vụ tự trả 404 | `NoHandlerFoundException` hoặc `NoResourceFoundException` khi resolver/handler tương ứng ném, hoặc ứng dụng chủ động trả 404 | URI sau rewrite, context path, mapping, static resource, security, custom advice |
| `405 Method Not Allowed` | Path có mapping nhưng HTTP method không được chấp nhận | `HttpRequestMethodNotSupportedException` | Method thực, `Allow` response header, `@GetMapping`/`@PostMapping` |
| `406 Not Acceptable` | Không thể cung cấp representation phù hợp `Accept`/`produces` | `HttpMediaTypeNotAcceptableException` | `Accept`, `produces`, converters, nội dung response |
| `415 Unsupported Media Type` | Request body `Content-Type` không được mapping/converter chấp nhận | `HttpMediaTypeNotSupportedException` | `Content-Type`, `consumes`, converter, charset |
| `400 Bad Request` | JSON sai cú pháp, thiếu field/param, conversion hoặc Bean Validation thất bại | `HttpMessageNotReadableException`, `MethodArgumentNotValidException`, `HandlerMethodValidationException`, `MethodArgumentTypeMismatchException`... | Body và constraint thực tế, binding/field errors |
| `500/503/other` | Lỗi nghiệp vụ/infra, exception async, timeout | Exception từ `Callable`, `DeferredResult.setErrorResult(...)`, `AsyncRequestTimeoutException`... | Exception root cause, async dispatch, timeout, response đã commit hay chưa |

Không có ánh xạ duy nhất **“async exception = HTTP 500”**. Một `@ExceptionHandler` có thể chuyển thành 422/503; timeout MVC mặc định thường 503 nếu response chưa commit; một lỗi ứng dụng chưa xử lý có thể thành 500. Xem đúng cấu hình và mã đã chạy.

## 3. 404: phân biệt không có handler với resource và business not-found

Một endpoint mẫu:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {
    @GetMapping("/{id}")
    Book find(@PathVariable long id) {
        return repository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

Đoạn trên minh họa, cần cung cấp `repository` và các lớp nghiệp vụ. Có ít nhất ba kiểu 404 khác nhau:

- `GET /api/boks/42` (gõ sai `books`): request có thể không khớp controller nào; Spring trả 404 từ quá trình handler mapping/static-resource handling.
- `GET /api/books/42`: mapping đúng, nhưng service phát `BookNotFoundException` và advice chuyển thành 404.
- `GET /assets/logo.png`: nếu static handler có mapping nhưng file không tồn tại, có thể nhận `NoResourceFoundException` (Spring 6.1+) rồi 404.

`NoHandlerFoundException` **không xuất hiện trong mọi lần 404**. `DispatcherServlet` có thể gửi 404 trực tiếp, và default static resource mapping của Spring Boot có thể nhận path trước rồi báo `NoResourceFoundException`. Không xây `@ExceptionHandler(NoHandlerFoundException.class)` với giả định nó sẽ bắt tất cả 404 của ứng dụng.

Lệnh thử:

~~~bash
curl -i http://localhost:8080/api/boks/42
~~~

Khi kiểm tra 404, hãy xác nhận controller được scan, `@RequestMapping` ở class có prefix nào, proxy có cắt prefix không, trailing slash có được match hay không, API version có đúng không và đường dẫn có bị Spring Security hoặc gateway sửa. **404 từ gateway** không nhất thiết đi qua `DispatcherServlet` của ứng dụng.

Nếu yêu cầu là “không tìm thấy bản ghi” thì trả 404 từ logic nghiệp vụ là hợp lý. Nhưng không nên biến exception database/timeout thành 404 chỉ để client khỏi nhận 500: việc đó giấu nguyên nhân vận hành thực sự.

## 4. 405: đúng URI nhưng sai HTTP method

Ví dụ endpoint chỉ cho POST:

~~~java
@PostMapping(path = "/api/items")
ResponseEntity<Void> create(@RequestBody CreateItem command) {
    return ResponseEntity.noContent().build();
}
~~~

Request này có thể gây 405:

~~~http
GET /api/items HTTP/1.1
Accept: application/json
~~~

Spring có thể ném `HttpRequestMethodNotSupportedException` và ghi header `Allow` để cho biết method được chấp nhận, ví dụ `POST`. `Allow` là đầu mối quan trọng khi đọc lỗi 405.

Điểm cần kiểm tra:

- Frontend gửi `GET` hay `POST`? `fetch` mặc định là GET nếu không chỉ định `method`.
- HTML form hỗ trợ một số method giới hạn; có dùng `HiddenHttpMethodFilter` hoặc endpoint REST thực sự chờ PUT/PATCH/DELETE không?
- Reverse proxy có chuyển method hay preflight `OPTIONS` bị chặn trước khi tới endpoint không?
- `HEAD` thường được hỗ trợ dựa trên GET mapping; `OPTIONS` có thể được Spring xử lý tự động, vì vậy đừng gộp mọi method khác GET vào 405 khi kiểm thử.
- Nếu controller có `params`/`headers` conditions, request có thể thất bại theo điều kiện khác, không chỉ method.

Thử tương phản:

~~~bash
curl -i -X GET http://localhost:8080/api/items
curl -i -X POST http://localhost:8080/api/items -H "Content-Type: application/json" -d '{"name":"Pen"}'
~~~

Đọc cả `Allow`, không chỉ status. Đừng sửa bằng cách thêm `@GetMapping` cho thao tác ghi dữ liệu; sửa client hoặc API contract để method phù hợp.

## 5. 406: Accept yêu cầu dạng server không tạo được

`Accept` diễn tả các loại media type mà client có thể nhận. Controller:

~~~java
@GetMapping(
    path = "/api/items/1",
    produces = MediaType.APPLICATION_JSON_VALUE
)
Item get() {
    return new Item(1L, "Pen");
}
~~~

Nếu client gửi:

~~~http
GET /api/items/1 HTTP/1.1
Accept: application/xml
~~~

Trong khi endpoint chỉ sản xuất JSON, Spring có thể báo `406 Not Acceptable` với `HttpMediaTypeNotAcceptableException`. Đổi `Accept: application/json` thường giải quyết được khi endpoint thực sự trả JSON.

**Đừng nhầm `Accept` với `Content-Type`:**

- `Accept` mô tả **response representation** client mong muốn.
- `Content-Type` mô tả **request body** client đang gửi.
- `produces` ràng buộc khả năng **trả dữ liệu**.
- `consumes` ràng buộc khả năng **nhận body**.

Các tình huống 406 thường gặp:

1. Browser hoặc API client gửi `Accept: application/xml` nhưng server chỉ tạo JSON.
2. Endpoint `produces="application/json"` trong khi client giới hạn loại media không tương thích.
3. Response DTO/converter hoặc content negotiation được cấu hình không phù hợp; cần kiểm tra exception thực tế, vì lỗi converter ghi response có thể biểu hiện 500 thay vì 406.
4. Handler yêu cầu loại media cụ thể bằng `produces`, nhưng browser/WebClient gửi header khác.

Thử:

~~~bash
curl -i http://localhost:8080/api/items/1 -H "Accept: application/xml"
curl -i http://localhost:8080/api/items/1 -H "Accept: application/json"
~~~

Không nên đổi `produces` thành `*/*` chỉ để làm 406 biến mất nếu ứng dụng vẫn chỉ serialize được JSON. Khả năng sản xuất representation phải là contract rõ ràng.

## 6. 415: Content-Type hoặc định dạng body không được hỗ trợ

Endpoint:

~~~java
@PostMapping(
    path = "/api/items",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
Item create(@RequestBody CreateItem input) {
    return service.create(input);
}
~~~

Nếu client gửi dữ liệu dạng text nhưng endpoint chỉ nhận JSON:

~~~http
POST /api/items HTTP/1.1
Content-Type: text/plain
Accept: application/json

{"name":"Pen"}
~~~

thì Spring thường trả `415 Unsupported Media Type` với `HttpMediaTypeNotSupportedException`. **Body nhìn giống JSON không đủ**: request vẫn khai báo `text/plain`.

Với `Content-Type: application/json` nhưng JSON sai cú pháp:

~~~http
POST /api/items HTTP/1.1
Content-Type: application/json

{"name":
~~~

thường là **400** do `HttpMessageNotReadableException`, không phải 415 vì media type đã được chấp nhận và lỗi xảy ra ở bước parse.

Các lưu ý:

- `application/json`, `application/x-www-form-urlencoded` và `multipart/form-data` không thay thế tùy tiện.
- Multipart cần tên part phù hợp, parser, `@RequestPart`/`@RequestParam` và media type cho JSON part. Thiếu part hay parse lỗi có thể tạo lỗi 400; loại media của toàn request không khớp `consumes` thường là 415.
- Một charset hoặc custom vendor media type như `application/vnd.acme+json` có thể cần kiểm tra converter/compatibility; không đoán rằng Spring luôn chấp nhận.
- Nếu HTTP method/path đã sai, Spring có thể thất bại trước khi kiểm tra body media type. Khi debug, giữ các thành phần khác đúng và thay **một header** để định vị vấn đề.

## 7. Validation: nhiều loại lỗi cùng có thể thành 400

Validation thuộc nhiều giai đoạn khác nhau, nên cần phân biệt exception và vị trí xử lý.

### 7.1. @Valid @RequestBody và MethodArgumentNotValidException

~~~java
public record NewItem(
        @NotBlank String name,
        @Size(max = 80) String description) {}

@PostMapping("/api/items")
Item create(@Valid @RequestBody NewItem input) {
    return service.create(input);
}
~~~

Khi request JSON hợp lệ về cú pháp nhưng `name` rỗng hoặc `description` quá dài, Spring MVC thường ném `MethodArgumentNotValidException` nếu tham số command object được validate theo cấu hình hỗ trợ. Với Spring Boot 3.x, cần dependency Bean Validation tương thích (thường `spring-boot-starter-validation`). Import tương ứng là `jakarta.validation.Valid` và `jakarta.validation.constraints.*`, không phải `javax.validation.*` trên Boot 3.

Nếu tham số dùng `BindingResult`/`Errors` ngay sau argument để tự xử lý, controller có thể nhận lỗi thay vì exception tự động; test phải dựa vào controller signature thực tế.

### 7.2. Validation tham số method: HandlerMethodValidationException

Một endpoint kiểm tra trực tiếp query parameter:

~~~java
@GetMapping("/api/items")
List<Item> list(@RequestParam @Min(1) int page) {
    return service.findPage(page);
}
~~~

Với Spring Framework 6.1+, MVC có hỗ trợ method validation tích hợp; nếu signature cần validation trên parameter như `@Min` và request dùng `page=0`, có thể nhận `HandlerMethodValidationException` (thông thường 400 cho lỗi input, 500 cho lỗi validation ở return value). Cơ chế thực tế phụ thuộc cách cấu hình: class-level `@Validated` có thể kích hoạt AOP method validation khác, nên cần kiểm tra exception của app thay vì cứng hóa một class cho mọi phiên bản.

### 7.3. Conversion/parse khác validation

- `GET /api/items/not-a-number` với `@PathVariable long id`: type conversion thất bại, có thể thành `MethodArgumentTypeMismatchException`/`TypeMismatchException` → 400.
- Thiếu `@RequestParam(required=true)`: `MissingServletRequestParameterException` → thường 400.
- JSON sai cú pháp hay body không decode được: `HttpMessageNotReadableException` → thường 400.
- Thiếu `@RequestBody(required=true)`: cũng thường là 400 ở bước đọc body.
- Constraint của entity/database (unique key, foreign key) là vấn đề tầng lưu trữ; không tự động trở thành một lỗi validation HTTP 400 chuẩn nếu không có mapping nghiệp vụ phù hợp.

Muốn trả lỗi có thể dùng chung, hãy chuẩn hóa `ProblemDetail`, mã lỗi và danh sách field violations, nhưng **không trả nội dung nhạy cảm** từ exception nội bộ. Trả field name, code và message được duyệt thay vì stack trace.

Ví dụ payload lỗi ứng dụng tự thiết kế:

~~~json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Request validation failed",
  "code": "INVALID_INPUT",
  "errors": [
    {"field": "name", "message": "must not be blank"}
  ]
}
~~~

Đây là **mẫu contract tùy biến**, không phải cam kết rằng mọi project Spring tự trả đúng các trường này. Spring `ProblemDetail` hỗ trợ thuộc tính mở rộng, nhưng format phụ thuộc cấu hình error handling của ứng dụng.

## 8. Exception handling trong Spring MVC: ai xử lý?

Một exception thường được đưa tới chuỗi `HandlerExceptionResolver`, trong đó có:

1. `ExceptionHandlerExceptionResolver` tìm `@ExceptionHandler` trong controller hoặc `@ControllerAdvice`.
2. `ResponseStatusExceptionResolver` xử lý `@ResponseStatus`/`ResponseStatusException` và một số nguyên nhân tương ứng.
3. `DefaultHandlerExceptionResolver` chuyển các exception tiêu chuẩn Spring MVC thành status thích hợp.

`ResponseEntityExceptionHandler` là class nền hữu ích để tập trung xử lý các exception MVC đã biết; phiên bản Spring mới có hỗ trợ `ProblemDetail` theo RFC 9457 (trước đây thường gọi RFC 7807). Có thể dùng `@RestControllerAdvice` để tạo response JSON cho exception nghiệp vụ.

Ví dụ:

~~~java
@RestControllerAdvice
class ApiExceptionAdvice {
    @ExceptionHandler(DependencyUnavailable.class)
    ProblemDetail dependencyDown(DependencyUnavailable ex) {
        ProblemDetail p = ProblemDetail.forStatus(
                HttpStatus.SERVICE_UNAVAILABLE);
        p.setTitle("Dependency unavailable");
        p.setDetail("Please retry later");
        p.setProperty("code", "UPSTREAM_UNAVAILABLE");
        return p;
    }
}
~~~

Đây là snippet tích hợp: cần định nghĩa `DependencyUnavailable` và import `ProblemDetail`, `HttpStatus`, `ExceptionHandler`. Bản demo đầy đủ ở phần 10.

Trong Spring Boot 3.x, `spring.mvc.problemdetails.enabled=true` có thể bật xử lý `ProblemDetail` cho exception của MVC bằng auto-configuration; một `@ControllerAdvice` riêng phải cân nhắc **thứ tự ưu tiên** và lớp kế thừa `ResponseEntityExceptionHandler` để tránh handler chồng lấp. Không tạo một `@ExceptionHandler(Exception.class)` nuốt mọi exception và luôn trả 200/400: cách đó làm sai giao thức và che lỗi server.

### 404/405/406/415 với advice

Không nhất thiết tự viết handler cho tất cả. Có thể để Spring xử lý built-in exceptions và chỉ override khi cần contract lỗi cụ thể. Nếu override `handleHttpRequestMethodNotSupported` mà bỏ mất header `Allow`, client sẽ mất thông tin cần thiết. Tương tự, các lỗi media type có thể có headers liên quan; hãy giữ headers Spring cung cấp khi customize.

## 9. Ngoại lệ bất đồng bộ: request có thể kết thúc ở dispatch khác

Spring MVC sử dụng Servlet async với `Callable<T>`, `DeferredResult<T>`, `WebAsyncTask<T>` và adapter cho một số reactive return types. Lần đầu vào controller có thể trả về đối tượng đại diện cho công việc chưa hoàn tất; `DispatcherServlet` nhả servlet thread khi request ở trạng thái async. Khi có kết quả/lỗi, Servlet container thực hiện **ASYNC dispatch** để MVC hoàn tất response.

### 9.1. Callable: exception ném ở worker

~~~java
@GetMapping("/api/async/call")
Callable<String> call() {
    return () -> {
        // Thực thi sau trong AsyncTaskExecutor.
        throw new DependencyUnavailable();
    };
}
~~~

Exception ở bên trong `Callable` **không ném trực tiếp trong stack ban đầu của controller**. Spring MVC nhận kết quả exception và đưa qua cơ chế exception handling sau async dispatch. Một `@ExceptionHandler(DependencyUnavailable.class)` có thể tạo response phù hợp.

Tư duy đúng:

~~~text
GET /api/async/call
  -> DispatcherServlet ban đầu
  -> controller trả Callable
  -> startAsync; servlet request thread được giải phóng
  -> AsyncTaskExecutor chạy Callable
  -> Callable ném DependencyUnavailable
  -> asyncDispatch về MVC
  -> @RestControllerAdvice chuyển thành HTTP 503 ProblemDetail
~~~

### 9.2. DeferredResult: setErrorResult để chuyển lỗi vào MVC

~~~java
@GetMapping("/api/async/pending")
DeferredResult<String> pending() {
    DeferredResult<String> result = new DeferredResult<>(10_000L);
    taskRegistry.register(result);
    return result;
}

// Khi công việc bên ngoài thất bại:
result.setErrorResult(new DependencyUnavailable());
~~~

`taskRegistry` là thành phần minh họa. `setErrorResult(exception)` yêu cầu Spring hoàn tất async request bằng một error result và đưa exception qua resolver khi dispatch. **Đừng chỉ log lỗi ở callback rồi bỏ request trong trạng thái chưa hoàn tất**. Đồng thời cần hủy/dọn task/registry trong `onTimeout` và `onCompletion`.

### 9.3. Timeout khác lỗi business

Timeout có thể xảy ra ở nhiều tầng:

- `DeferredResult(timeoutMillis)` hoặc `WebAsyncTask`: giới hạn thời gian xử lý Servlet async request.
- `spring.mvc.async.request-timeout`: cấu hình timeout MVC async mặc định (nếu app dùng Boot có property tương ứng).
- HTTP client (WebClient/RestClient): connect/read/response timeout tới upstream, xảy ra độc lập với timeout MVC.
- Gateway/reverse proxy: có thể trả 504 trước khi Spring MVC kịp hoàn tất response.
- Reactive `Mono.timeout(...)` khi controller trả publisher: phát tín hiệu timeout của Reactor, có thể được map thành response khác.

Trong Spring MVC mặc định, `AsyncRequestTimeoutException` thường được xử lý thành **503 Service Unavailable** nếu response chưa commit. Custom `@ExceptionHandler` hoặc interceptor có thể biến thành response khác. Nếu client đã disconnect, stream đã gửi headers/body hoặc response đã commit, **không thể tùy tiện thay status/body** nữa.

Đừng cho rằng thấy 503 là chắc chắn async timeout: 503 cũng có thể do server tự báo bảo trì, quá tải hoặc app-specific mapping. Xác định exception class và thời gian thực thi.

### 9.4. Một số lỗi xử lý bất đồng bộ phổ biến

- **Không gọi `asyncDispatch` trong test:** `MockMvc` báo initial request đã bắt đầu async nhưng test không quan sát HTTP status cuối cùng.
- **Block ở event-loop:** nếu controller MVC trả `Mono` dùng WebClient, gọi `block()` trong Reactor event-loop có thể gây `IllegalStateException`. Phối hợp publisher bằng `flatMap`/`zip`, chỉ block ở ranh giới imperative trên thread được phép.
- **Đã timeout nhưng worker vẫn chạy:** timeout của HTTP request không nhất thiết hủy công việc bên ngoài hoặc rollback remote operation; cần cancellation/idempotency rõ ràng.
- **Mất MDC/trace ID:** request có thể qua thread/dispatch khác. Dùng tracing/context propagation được hỗ trợ, không mặc định `ThreadLocal` giữ nguyên mọi nơi.
- **Filter chỉ chạy REQUEST:** trong Servlet async, có thể cần mapping cho dispatcher type `ASYNC` để xử lý đúng tracing/security, theo cấu hình cụ thể.

## 10. Demo Spring Boot 3.x và kiểm thử MockMvc

Demo dùng Spring Boot 3.x, Java 17+, Spring MVC, JUnit 5 và Bean Validation. Các endpoint chủ động tạo điều kiện để quan sát từng status và một business exception xảy ra trong cả `Callable` lẫn `DeferredResult`.

Cấu trúc Maven:

~~~text
spring-web-errors/
├── pom.xml
├── src/main/java/demo/ErrorDemoApplication.java
├── src/main/java/demo/DiagnosticController.java
├── src/main/java/demo/ApiErrorAdvice.java
└── src/test/java/demo/DiagnosticControllerTest.java
~~~

### 10.1. pom.xml

~~~xml
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
    <groupId>demo</groupId>
    <artifactId>spring-web-errors</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 10.2. src/main/java/demo/ErrorDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorDemoApplication.class, args);
    }
}
~~~

### 10.3. src/main/java/demo/DiagnosticController.java

~~~java
package demo;

import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
public class DiagnosticController {
    private final AtomicReference<DeferredResult<Item>> pending =
            new AtomicReference<>();

    public record Item(long id, String name) {}
    public record NewItem(@NotBlank String name) {}

    @GetMapping(
            path = "/api/items/1",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Item getItem() {
        return new Item(1, "Pen");
    }

    @PostMapping(
            path = "/api/items",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Item create(@Valid @RequestBody NewItem input) {
        return new Item(2, input.name());
    }

    @GetMapping("/api/quantity")
    public String quantity(@RequestParam @Min(1) int amount) {
        return "amount=" + amount;
    }

    @GetMapping("/api/async/callable")
    public Callable<Item> fromCallable() {
        return () -> {
            throw new DependencyUnavailable();
        };
    }

    @GetMapping("/api/async/deferred")
    public DeferredResult<Item> fromDeferred() {
        DeferredResult<Item> result = new DeferredResult<>(10_000L);
        pending.set(result);
        result.onCompletion(() -> pending.compareAndSet(result, null));
        return result;
    }

    // Chỉ là hook có phạm vi package để demo test điều khiển sự kiện.
    void failPending() {
        DeferredResult<Item> current = pending.get();
        if (current == null) {
            throw new IllegalStateException("No pending request");
        }
        current.setErrorResult(new DependencyUnavailable());
    }
}

class DependencyUnavailable extends RuntimeException {}
~~~

Trong `fromDeferred()`, ứng dụng thật không nên giữ **duy nhất một pending request trong AtomicReference** nếu có nhiều client đồng thời; cần registry riêng theo request ID, cleanup khi hoàn tất/timeout và giới hạn số task. Cấu trúc demo chỉ để test một request tại một thời điểm.

### 10.4. src/main/java/demo/ApiErrorAdvice.java

~~~java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorAdvice {
    @ExceptionHandler(DependencyUnavailable.class)
    public ProblemDetail dependencyUnavailable(DependencyUnavailable error) {
        ProblemDetail detail = ProblemDetail.forStatus(
                HttpStatus.SERVICE_UNAVAILABLE);
        detail.setTitle("Dependency unavailable");
        detail.setDetail("Please retry later");
        detail.setProperty("code", "UPSTREAM_UNAVAILABLE");
        return detail;
    }
}
~~~

Advice này chỉ xử lý **một exception nghiệp vụ**, để Spring MVC tự phát những status built-in như 405, 406, 415 và 400 do validation. Vì return `ProblemDetail` mang status 503, Spring MVC dùng status tương ứng cho response. Không đưa stack trace hoặc thông tin nội bộ vào body.

### 10.5. src/test/java/demo/DiagnosticControllerTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(DiagnosticController.class)
class DiagnosticControllerTest {
    @Autowired MockMvc mvc;
    @Autowired DiagnosticController controller;

    @Test
    void missingRouteIs404() throws Exception {
        mvc.perform(get("/api/does-not-exist"))
            .andExpect(status().isNotFound());
    }

    @Test
    void wrongHttpMethodIs405() throws Exception {
        mvc.perform(post("/api/items/1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"X\"}"))
            .andExpect(status().isMethodNotAllowed())
            .andExpect(header().string(
                    HttpHeaders.ALLOW, containsString("GET")));
    }

    @Test
    void unacceptableAcceptIs406() throws Exception {
        mvc.perform(get("/api/items/1")
                .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isNotAcceptable());
    }

    @Test
    void unsupportedContentTypeIs415() throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Pen\"}"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void validRequestSucceeds() throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Pen\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(2))
            .andExpect(jsonPath("$.name").value("Pen"));
    }

    @Test
    void malformedJsonIs400() throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void invalidBeanValidationIs400() throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void invalidMethodParameterIs400() throws Exception {
        mvc.perform(get("/api/quantity")
                .param("amount", "0"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void callableErrorIsResolvedAfterAsyncDispatch() throws Exception {
        MvcResult pending = mvc.perform(get("/api/async/callable"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.code").value("UPSTREAM_UNAVAILABLE"))
            .andExpect(jsonPath("$.detail").value("Please retry later"));
    }

    @Test
    void deferredErrorIsResolvedAfterAsyncDispatch() throws Exception {
        MvcResult pending = mvc.perform(get("/api/async/deferred"))
                .andExpect(request().asyncStarted())
                .andReturn();

        controller.failPending();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.code").value("UPSTREAM_UNAVAILABLE"));
    }
}
~~~

`@WebMvcTest(DiagnosticController.class)` load MVC controller và các `@ControllerAdvice` trong slice nếu chúng được component scan vào web slice. Nếu project tùy biến component scanning, cần `@Import(ApiErrorAdvice.class)` hoặc cấu hình slice cụ thể để advice có mặt; test có thể xác minh bằng response 503 chứa `code`.

**Điều quan trọng nhất khi kiểm thử async:** `mvc.perform(get(...))` đầu tiên **chưa phải response cuối** khi method trả `Callable`/`DeferredResult`. Dùng `request().asyncStarted()`, lấy `MvcResult`, kích hoạt kết quả giả lập nếu cần, sau đó `asyncDispatch(...)` để assert HTTP status/body cuối cùng. Nếu thiếu bước thứ hai, test dễ cho kết luận sai về việc advice có hoạt động.

### 10.6. Chạy Maven và kiểm tra kết quả

Dùng JDK 17+ và Maven trong thư mục chứa `pom.xml`:

~~~bash
mvn test
~~~

Nếu các lớp nằm đúng package và dependency như trình bày, kỳ vọng Maven kết thúc `BUILD SUCCESS`, 10 bài test pass, không có test failure. Đây là **kỳ vọng từ mã minh họa**, không phải output đã được đo thực tế trong môi trường này. Nếu một test lỗi, đọc `target/surefire-reports` để xem exception và cấu hình thực tế; đừng chỉnh expected status mà không hiểu nguồn lỗi.

Chạy API thật:

~~~bash
mvn spring-boot:run
~~~

Thử nhanh:

~~~bash
curl -i http://localhost:8080/api/does-not-exist
curl -i -X POST http://localhost:8080/api/items/1 -H "Content-Type: application/json" -d '{"name":"X"}'
curl -i http://localhost:8080/api/items/1 -H "Accept: application/xml"
curl -i -X POST http://localhost:8080/api/items -H "Content-Type: text/plain" -d '{"name":"Pen"}'
curl -i -X POST http://localhost:8080/api/items -H "Content-Type: application/json" -d '{"name":""}'
~~~

Trong thứ tự trên, status kỳ vọng là **404, 405, 406, 415, 400**. Các endpoint async ném exception sẽ trả `503` do `ApiErrorAdvice`, nếu request hoàn tất trước timeout và response chưa bị commit.

Lệnh `curl` ví dụ dùng cú pháp CLI thường gặp của Bash; ở Windows PowerShell nên dùng `curl.exe` và quy tắc quote chuỗi JSON của shell đó.

## 11. Quan sát log đúng cách thay vì đoán theo status

Khi xử lý sự cố thực, thu thập các trường sau cho mỗi request:

| Nhóm | Ví dụ | Tại sao cần |
| --- | --- | --- |
| Request | method, URI, query, `Accept`, `Content-Type` | Phân biệt mapping/converter errors |
| Response | status, `Allow`, media type, duration | Chỉ ra 405/406/415 và độ trễ |
| Trace | request ID, trace ID, span ID | Liên kết gateway → MVC → upstream |
| Exception | class, root cause, stack trace ở server log | Phân biệt validation, async timeout, upstream failure |
| Async | dispatcher type `REQUEST`/`ASYNC`, timeout config, completion | Biết request đã chuyển thread/dispatch chưa |
| Backend | database, HTTP client status/latency, thread pool/queue | Biết lỗi thực sự nằm ở tầng nào |

Không log token, mật khẩu, nội dung riêng tư hoặc toàn bộ multipart file chỉ để debug 400/415. Khi gặp `HttpMessageNotReadableException`, log an toàn đủ để tái hiện schema/body mẫu đã ẩn dữ liệu nhạy cảm.

Một luồng điều tra cụ thể:

1. Nếu **404**, xác nhận gateway routing, controller scan, path variables và static mappings; so với đường dẫn từ request logs.
2. Nếu **405**, lấy `Allow` rồi xem method trong request thực, bao gồm request do browser preflight `OPTIONS` hay client gửi.
3. Nếu **406**, in `Accept`, `produces` và danh sách converter được app hỗ trợ.
4. Nếu **415**, in `Content-Type`, `consumes` và body shape; thử lại với header đúng.
5. Nếu **400 validation**, đọc field/type/constraint errors và phân biệt lỗi JSON parser.
6. Nếu **5xx/timeout async**, theo dõi initial dispatch, worker/publisher, async dispatch và advice; kiểm tra response đã commit, proxy timeout và external service.

Trong Spring Boot có thể dùng Actuator HTTP server metrics và tracing nếu đã cấu hình, kết hợp request correlation IDs. Đừng bật DEBUG/TRACE toàn bộ traffic dài hạn trên production khi chứa dữ liệu nhạy cảm.

## 12. Các ngộ nhận thường gặp

### 12.1. “404 nghĩa là @ExceptionHandler của tôi không bắt được business exception”

Có thể endpoint chưa được route đến controller, hoặc static resource handler phát 404. Phân biệt bằng trace, handler mapping và loại exception; không phải mọi 404 đều là business exception.

### 12.2. “405 là controller không tồn tại”

405 thường có nghĩa path được nhận diện nhưng method không phù hợp. Kiểm tra response `Allow` và phương thức request, rồi đối chiếu `@GetMapping`/`@PostMapping`.

### 12.3. “JSON body đúng thì không thể bị 415”

Media type do `Content-Type` khai báo quyết định bước `consumes`/converter. JSON text gắn `text/plain` vẫn có thể bị 415; JSON hỏng nhưng content type đúng thường ra 400.

### 12.4. “Accept: application/xml mà nhận 406 là do không có dữ liệu”

406 nói về response representation, không phải bản ghi bị thiếu. Khi muốn báo bản ghi không tồn tại, nghiệp vụ trả 404 độc lập với việc client chọn media type hợp lệ.

### 12.5. “Mọi 400 đều do @Valid”

Thiếu parameter, sai kiểu path variable, body JSON hỏng cũng là 400 phổ biến. Đọc exception class và test từng biên lỗi.

### 12.6. “Exception xảy ra trong CompletableFuture/Callable thì @ControllerAdvice không chạy”

Với các async return types được Spring MVC hỗ trợ và exception được **đưa vào lifecycle MVC** (ví dụ `Callable` ném hoặc `DeferredResult.setErrorResult(exception)`), request được async-dispatch và xử lý bằng exception resolvers bình thường. Nhưng exception bị nuốt trong một fire-and-forget thread/`@Async void` không tự đi vào response request đã kết thúc.

### 12.7. “Async request timeout nhất định là HTTP 504”

MVC mặc định thường trả 503 cho `AsyncRequestTimeoutException` khi chưa commit; 504 thường xuất hiện ở gateway/proxy hoặc mapping tùy biến. Xem tầng nào đã trả response.

### 12.8. “Test chỉ cần assert exception của controller method”

Với MVC, lỗi có thể xảy ra **trước khi method được gọi** (mappings, converter, binding) hoặc **sau initial dispatch** (async). `MockMvc` kiểm tra cả request pipeline và cần `asyncDispatch` cho kết quả bất đồng bộ.

## 13. Lưu ý với WebFlux và reactive errors

Trong Spring WebFlux, thay vì Servlet `DispatcherServlet` là reactive `DispatcherHandler` và các thành phần `WebFilter`/`WebExceptionHandler`. HTTP semantics vẫn là 404/405/406/415/400 nhưng exception classes thường thuộc package reactive/server khác, ví dụ `ResponseStatusException`, `ServerWebInputException` hoặc `WebExchangeBindException` cho binding/validation. Không áp dụng nguyên xi danh sách exception MVC lên WebFlux.

Với controller trả `Mono`/`Flux`:

~~~java
@GetMapping("/api/reactive/item")
Mono<Item> reactive() {
    return webClient.get()
            .uri("/upstream/item")
            .retrieve()
            .bodyToMono(Item.class)
            .onErrorMap(WebClientRequestException.class,
                    error -> new DependencyUnavailable());
}
~~~

Đây là snippet tích hợp (cần `webClient` và class `Item`/`DependencyUnavailable`). Nếu exception là **reactive error signal** từ publisher được Spring WebFlux subscribe trong request lifecycle, có thể được xử lý bằng exception handler; nếu ứng dụng tự gọi `subscribe()` rồi trả response 200 ngay, lỗi phát sinh ngoài lifecycle không tự đổi status đã gửi. Tương tự, không block Reactor event-loop khi chữa lỗi async; compose publishers bằng operators.

Dùng `WebTestClient` hoặc integration test reactive để khẳng định status/body thực tế, và phân biệt lỗi từ `WebClientResponseException` (upstream có HTTP response lỗi) với `WebClientRequestException` (request/network failure). Nếu muốn truyền nguyên status upstream sang client, phải có quyết định nghiệp vụ rõ ràng thay vì trả mặc định 500.

## 14. Checklist thực hành

- [ ] Ghi đúng method, URL, `Content-Type`, `Accept`, query, payload shape và request ID trước khi sửa code.
- [ ] Với 404: xác minh mapping, resources và business not-found riêng.
- [ ] Với 405: đọc `Allow`; kiểm tra method HTTP và mapping.
- [ ] Với 406: kiểm tra `Accept`, `produces` và message converter phía response.
- [ ] Với 415: kiểm tra `Content-Type`, `consumes` và converter đầu vào.
- [ ] Với 400: phân biệt parse/binding/validation; báo field errors có kiểm soát.
- [ ] Với `Callable`/`DeferredResult`: bảo đảm exception đi qua async result và dùng `asyncDispatch` trong MockMvc.
- [ ] Với timeout: xác minh timeout ở MVC, HTTP client hay gateway; xem response đã commit chưa.
- [ ] Với `@ControllerAdvice`: giữ status/headers chuẩn và kiểm tra conflict/thứ tự handlers, không nuốt mọi lỗi.
- [ ] Có tests âm tính/biên, request correlation, log an toàn và thống kê tỉ lệ lỗi theo nhóm.

**Nguyên tắc quan trọng:** xác định **request thất bại ở bước nào** trước khi đổi controller/advice. 404/405 là đầu mối routing, 406/415 là negotiation/converter, validation thường là 400, còn async exception cần lần dispatch tiếp theo và một chính sách xử lý lỗi minh bạch.

## 15. Tài liệu tham khảo chính thức

- Spring Framework — Mapping Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — REST Error Responses và `ProblemDetail`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework — MVC Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — Method Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — Exception Handling: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework — MockMvc: https://docs.spring.io/spring-framework/reference/testing/mockmvc.html
- Spring Framework — MockMvc Async Requests: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110.html
