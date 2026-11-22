# RouterFunction, RequestPredicate và khai báo tuyến lồng nhau trong Spring MVC

## 1. Functional MVC là gì?

Trong **Spring MVC**, bạn thường xây HTTP API bằng `@RestController` và `@GetMapping`:

~~~java
@RestController
class BookController {
    @GetMapping("/api/books")
    List<Book> books() {
        return bookService.findAll();
    }
}
~~~

Mã trên là fragment, vì `Book` và `bookService` chưa được định nghĩa. Spring MVC còn hỗ trợ mô hình **functional endpoints**, thường gọi **WebMvc.fn**. Thay vì gắn annotation vào từng handler method, bạn khai báo việc chọn handler như **hàm ánh xạ từ HTTP request tới handler**.

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route(
                RequestPredicates.GET("/api/health"),
                request -> ServerResponse.ok().body("OK"));
~~~

Đây là một route độc lập dùng API `org.springframework.web.servlet.function`. Nó kết nối:
- **`RequestPredicate`**: điều kiện nhận diện request, ví dụ method GET và path `/api/health`.
- **`HandlerFunction<ServerResponse>`**: xử lý request đã match, tạo `ServerResponse`.
- **`RouterFunction<ServerResponse>`**: tìm handler phù hợp với request.
- **`ServerRequest`**: đối tượng request kiểu functional, cung cấp path variables, query parameters, headers, body.
- **`ServerResponse`**: builder cho status, headers, body hoặc rendering response.

Các route được **xét theo thứ tự khai báo**: nếu route đầu match thì nó được chọn trước. Khác với annotation MVC nơi framework dùng độ đặc hiệu của mapping để chọn handler, trong functional routing thứ tự composition là một phần của thiết kế. Vì thế `/api/books/featured` phải được đặt trước route tổng quát `/api/books/{id}` nếu cả hai có thể match.

### Mục tiêu học tập

Sau bài này bạn có thể:
1. Phân biệt WebMvc.fn Servlet với WebFlux.fn reactive.
2. Hiểu `RouterFunction`, `HandlerFunction`, `RequestPredicate`, `ServerRequest` và `ServerResponse`.
3. Đọc và viết predicates theo HTTP method, path, `Accept`, `Content-Type`, header, query/form parameter.
4. Dùng `and`, `or`, `negate`, `andRoute`, `RouterFunctions.route()` builder và các phương thức `GET`/`POST`.
5. Khai báo route **lồng nhau** bằng `path(prefix, builder)` và `nest(predicate, builder)`, không lặp path và ràng buộc header.
6. Hiểu cách phân biệt handler không match, handler lỗi, request body không hợp lệ, thiếu quyền và exception mapping.
7. Xây ứng dụng Java 17+ Spring Boot 3.3.5 có BookStore, BookHandler, nested RouterFunction và MockMvc integration tests.
8. Biết khi nào nên dùng functional MVC, khi nào annotation controller dễ bảo trì hơn.

**Phiên bản:** WebMvc.fn có từ Spring Framework 5.2; ví dụ chạy trên Spring Boot 3.3.5 / Spring Framework 6.1.x. Một số tài liệu Spring Framework “current” đã chuyển sang các API mới hơn; ví dụ dưới chỉ dùng API hiện hữu ở dòng 6.1.

## 2. WebMvc.fn thuộc Servlet stack, không phải WebFlux.fn

Hai hệ có tên class rất giống, nhưng **package khác**:

| Servlet WebMvc.fn | Reactive WebFlux.fn |
| --- | --- |
| `org.springframework.web.servlet.function.RouterFunction` | `org.springframework.web.reactive.function.server.RouterFunction` |
| `org.springframework.web.servlet.function.ServerRequest` | `org.springframework.web.reactive.function.server.ServerRequest` |
| `org.springframework.web.servlet.function.ServerResponse` | `org.springframework.web.reactive.function.server.ServerResponse` |
| Handler thường trả `ServerResponse` đồng bộ | Handler thường trả `Mono<ServerResponse>` |
| Servlet container + `DispatcherServlet` | Reactive HTTP runtime và reactive adapters |
| `spring-boot-starter-web` | `spring-boot-starter-webflux` |

**Đừng để IDE tự import nhầm `org.springframework.web.reactive.function.server.*`** vào ứng dụng Spring MVC. Java generic signatures, body builders và test setup của WebFlux khác. Dùng WebMvc.fn không có nghĩa tất cả I/O trở nên non-blocking; `ServerRequest.body(Class)` và JDBC/HTTP client đồng bộ vẫn có thể blocking trên servlet thread.

Ứng dụng Spring Boot có thể dùng WebMvc.fn cùng `@RestController` nếu muốn, nhưng phải quản lý URL conflicts, mapping order, SecurityFilterChain, error handling và tài liệu API. Không biến việc chọn hai kiểu API thành một công cụ “tự chữa” lỗi route.

## 3. Luồng xử lý của một functional MVC endpoint

~~~text
HTTP client
   |
   v
Servlet container / filters / Spring Security (nếu có)
   |
   v
DispatcherServlet
   |
   v
RouterFunctionMapping
   |
   +-- RouterFunction #1: match RequestPredicate?
   |       | yes -> HandlerFunction
   |       + no
   |
   +-- RouterFunction #2: match?
   |       | yes -> HandlerFunction
   |       + no -> Các HandlerMapping khác / 404 theo cấu hình
   |
   v
HandlerFunctionAdapter / ServerRequest
   |
   v
HandlerFunction.handle(request)
   |
   v
ServerResponse (status + headers + body)
   |
   v
HTTP message converters / response writing
   |
   v
HTTP client
~~~

Sơ đồ giản lược: Spring MVC có nhiều `HandlerMapping` (annotated methods, functional routes, static resources...) và thứ tự `order` riêng. `RouterFunctionMapping` tìm handler từ router functions; `HandlerFunctionAdapter` gọi functional handler; response sau đó được viết qua MVC infrastructure. Không tuyên bố functional endpoints luôn thắng hoặc luôn thua mọi annotation controller ở mọi cấu hình — đặc biệt khi tự thay đổi order các mapping beans.

### Ba giai đoạn quan trọng

1. **Routing:** `RequestPredicate` quyết định request nào đi vào handler. Đây chưa phải authentication hay validation của body.
2. **Handling:** `HandlerFunction` đọc dữ liệu qua `ServerRequest`, gọi service và tạo một `ServerResponse`.
3. **Writing:** Spring Web MVC viết status, headers, body bằng các converter/view facilities phù hợp.

Nếu route **không match**, handler không chạy; một response 404/405/406/415 có thể đến từ cơ chế mapping hoặc error handling. Nếu route **đã match** nhưng handler ném exception, đó là nhánh khác và cần error mapping riêng. Đừng coi mọi 404 là cùng một lỗi.

## 4. `RequestPredicate` là gì?

`RequestPredicate` là điều kiện trên request; về ý tưởng nó giống `Predicate<ServerRequest>` nhưng Spring thêm khả năng hỗ trợ composition, path nesting và introspection. Các static factories từ `RequestPredicates`:

| Factory (Servlet MVC) | Dùng để |
| --- | --- |
| `GET("/path")` | Match GET và path |
| `POST("/path")` | Match POST và path |
| `PUT("/path")`, `PATCH("/path")`, `DELETE("/path")` | Match method + path |
| `method(HttpMethod.GET)` | Match method không ràng buộc path |
| `methods(GET,HEAD)` | Match một nhóm methods |
| `path("/api/**")` | Match URL path |
| `accept(MediaType.APPLICATION_JSON)` | Match Accept negotiation |
| `contentType(MediaType.APPLICATION_JSON)` | Match request Content-Type |
| `headers(h -> ...)` | Predicate tùy biến theo request headers |
| `param("view","summary")` | Match request parameter của WebMvc.fn |
| `all()` | Luôn match |
| `predicate.and(other)` | Cả hai phải đúng |
| `predicate.or(other)` | Ít nhất một đúng |
| `predicate.negate()` | Phủ định điều kiện |

**Lưu ý về tên API:** trong `org.springframework.web.servlet.function.RequestPredicates` có `param(...)`. Tài liệu `WebFlux.fn` có `queryParam(...)` nhưng **đừng copy `RequestPredicates.queryParam(...)` của reactive package vào Servlet WebMvc.fn 6.1**. `ServerRequest.param("name")` đọc request parameter; nó có thể bao gồm query/form parameters theo Servlet semantics.

### 4.1. Match method + path

~~~java
RequestPredicate findBook =
        RequestPredicates.GET("/api/books/{id}");
~~~

`GET("/api/books/{id}")` là tổ hợp kiểm method GET và path pattern. Khi handler được chọn, `request.pathVariable("id")` lấy giá trị đã match.

Không tự suy ra `{id}` là số: path variable bắt đầu là chuỗi; handler cần parse và validate kiểu/giới hạn.

### 4.2. Kết hợp predicate bằng `and`

~~~java
RequestPredicate onlyJson =
        RequestPredicates.GET("/api/books")
                .and(RequestPredicates.accept(MediaType.APPLICATION_JSON));
~~~

Route chỉ match nếu cả GET path và client Accept phù hợp JSON. `Accept` là yêu cầu định dạng **response**, không phải mô tả request body.

### 4.3. Kết hợp bằng `or` và `negate`

~~~java
RequestPredicate simpleReads =
        RequestPredicates.method(HttpMethod.GET)
                .or(RequestPredicates.method(HttpMethod.HEAD));

RequestPredicate notAdminPath =
        RequestPredicates.path("/admin/**").negate();
~~~

Đây là fragments cần imports tương ứng. `or`/`negate` thay đổi logic match, **không tạo security boundary**. Một `notAdminPath` route không thay Spring Security authorization cho `/admin/**`.

### 4.4. Header predicate

~~~java
RequestPredicate versionTwo = RequestPredicates.headers(
        headers -> "2".equals(headers.firstHeader("API-Version")));
~~~

Nếu browser từ origin khác gửi custom header `API-Version`, nó thường yêu cầu CORS preflight. Router match version header không tự cấu hình CORS hoặc cấp quyền user.

### 4.5. Request parameter predicate

~~~java
RequestPredicate summary = RequestPredicates.param("view", "summary");
~~~

Có thể kết hợp với path GET:

~~~java
RouterFunction<ServerResponse> route =
        RouterFunctions.route(
                RequestPredicates.GET("/api/books/featured").and(summary),
                handler::featured);
~~~

Nếu `view` thiếu, route này không match; một route tổng quát sau nó **có thể** match cùng path. Đó là lý do cần thứ tự hợp lý và fallback rõ, không giả định predicate không match tự sinh một lỗi 400 theo mong muốn.

### 4.6. Content-Type và Accept khác nhau

| HTTP header | Predicate | Ý nghĩa |
| --- | --- | --- |
| `Accept: application/json` | `accept(APPLICATION_JSON)` | Client muốn **nhận** JSON |
| `Content-Type: application/json` | `contentType(APPLICATION_JSON)` | Client đang **gửi body** JSON |

Với POST/PUT có JSON body, `contentType` thường hữu ích. Với GET trả JSON, `accept` thường phù hợp. Cả hai **chỉ là điều kiện routing**; nếu content là JSON sai syntax, handler/body converter vẫn có thể báo lỗi sau khi đã match.

## 5. Khai báo route bằng `RouterFunctions.route(predicate, handler)`

Cách tối giản:

~~~java
RouterFunction<ServerResponse> hello =
        RouterFunctions.route(
                RequestPredicates.GET("/hello"),
                request -> ServerResponse.ok().body("Hello MVC.fn"));
~~~

Trường hợp chỉ một route, cách này dễ đọc. Khi có nhiều handlers, dùng `RouterFunction.andRoute` để nối:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route(
                RequestPredicates.GET("/hello"),
                request -> ServerResponse.ok().body("Hello"))
            .andRoute(
                RequestPredicates.GET("/ping"),
                request -> ServerResponse.ok().body("pong"));
~~~

Các snippets ở đây chưa khai báo class/bean; để Spring Boot phát hiện routes cần đăng ký `RouterFunction<ServerResponse>` thành bean hoặc tích hợp theo cơ chế tương đương. Ví dụ đầy đủ ở mục 10 có `@Bean` rõ ràng.

### 5.1. Hàm router chọn handler, không tự thực thi logic nghiệp vụ

`RouterFunction.route(request)` trả về một `Optional<HandlerFunction<...>>` theo contract; handler mới thực hiện công việc khi MVC gọi nó. Tránh database/network call side-effect bên trong `RequestPredicate` hoặc lúc đăng ký route, vì predicate có thể được kiểm nhiều lần và không đại diện cho một business transaction.

### 5.2. Composition với `and`

~~~java
RouterFunction<ServerResponse> composed =
        firstRoutes.and(secondRoutes);
~~~

Đây là fragment giả định `firstRoutes`/`secondRoutes` đã được định nghĩa. `and` sẽ thử router đầu rồi tới router sau nếu cần, giữ thứ tự route. Có thể dùng `andRoute(predicate, handler)` để tiện thêm route đơn lẻ.

## 6. Builder DSL: `RouterFunctions.route()`

Khi nhiều path/methods, builder DSL sáng sủa hơn:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/api/health", handler::health)
                .GET("/api/books/{id}", handler::byId)
                .GET("/api/books", handler::all)
                .POST("/api/books",
                        RequestPredicates.contentType(
                                MediaType.APPLICATION_JSON),
                        handler::create)
                .build();
~~~

`handler` là bean ứng dụng có các methods `ServerResponse health(ServerRequest)`, `byId(...)`, `all(...)`, `create(...)`; đây là fragment rút gọn, code đầy đủ nằm trong mục 10.

Mỗi builder method thể hiện method, path, predicate bổ sung (nếu có), handler. Cuối cùng `build()` trả một `RouterFunction<ServerResponse>` hoàn chỉnh.

### 6.1. Thứ tự route là quy tắc bắt buộc

Ví dụ **sai**:

~~~java
RouterFunctions.route()
        .GET("/api/books/{id}", handler::byId)
        .GET("/api/books/featured", handler::featured)
        .build();
~~~

`/api/books/featured` có thể bị match bởi `{id}` ở route đầu. Nếu `byId` parse số, bạn có thể nhận lỗi NumberFormatException thay vì response featured.

Sửa lại:

~~~java
RouterFunctions.route()
        .GET("/api/books/featured", handler::featured)
        .GET("/api/books/{id}", handler::byId)
        .build();
~~~

**Quy tắc review:** route tĩnh/cụ thể trước, route variable/wildcard rộng sau; fallback hoặc catch-all phải đứng cuối. Điều này khác annotation-based mappings của `@RequestMappingHandlerMapping` vốn lựa chọn độ đặc hiệu theo các rule nội bộ.

## 7. Nested routes bằng `path(prefix, builder)`

Nếu API có nhiều routes dưới cùng prefix:

~~~text
GET  /api/health
GET  /api/books
GET  /api/books/{id}
POST /api/books
~~~

Ta có thể tránh lặp `/api` và `/books`:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/api", api -> api
                        .GET("/health", handler::health)
                        .path("/books", books -> books
                                .GET("/{id}", handler::byId)
                                .GET("", handler::all)
                                .POST("", handler::create)))
                .build();
~~~

`path("/api", ...)` là một **path prefix grouping**. Trong nhánh này, đường dẫn con được diễn giải tương đối với prefix. `/api/books/{id}` vẫn là URL hoàn chỉnh client gọi; bạn **không gửi `/books/{id}`** chỉ vì trong builder lồng nhau viết vậy.

Điểm cần chú ý: khi có route động và route cụ thể ở cùng prefix, vẫn giữ độ cụ thể theo thứ tự. Để match đúng `GET /api/books`, builder con thường dùng `GET("", handler::all)` như ví dụ chính thức của Spring khi nest path.

### 7.1. Vì sao nested routes hữu ích?

- Tổ chức tuyến theo domain/module/resource.
- Giảm duplication prefix khi đổi `/api/v1` sang `/api/v2`.
- Áp dụng điều kiện chung (ví dụ `Accept`) cho một nhóm routes.
- Gắn filter logging/headers cho một nhánh thay vì toàn bộ API.
- Phân chia route theo module và ghép lại bằng `add` hoặc `path(prefix, supplier)`.

Nhược điểm: nesting quá sâu làm routing khó lần theo, đặc biệt khi có nhiều `nest` và filter scopes. Nên giữ cây route ngắn, đặt tên rõ và có tests chính xác cho từng URL.

### 7.2. Dùng `path` khác `nest(path(...))` như thế nào?

`path("/api", builder)` là tiện ích chuyên cho path prefix. `nest(RequestPredicates.path("/api"), builder)` cho phép nested routing bằng một predicate path. Với nhiều use cases chúng diễn đạt cùng mục tiêu, nhưng `nest` linh hoạt hơn vì có thể dùng **bất kỳ predicate** (headers, Accept...) không chỉ URL prefix.

Không nhầm `nest` với một lần Servlet FORWARD/HTTP redirect. Nó chỉ tổ chức việc route match và handler selection.

## 8. Nested routes bằng `nest(predicate, builder)`

Ngoài path, ta có thể đặt điều kiện dùng chung cho các GET trả JSON:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/api/books", books -> books
                        .nest(
                                RequestPredicates.accept(
                                        MediaType.APPLICATION_JSON),
                                json -> json
                                        .GET("/{id}", handler::byId)
                                        .GET("", handler::all))
                        .POST("",
                                RequestPredicates.contentType(
                                        MediaType.APPLICATION_JSON),
                                handler::create))
                .build();
~~~

Logic:
- Cả GET `/{id}` và GET `""` phải có Accept phù hợp JSON để match nhánh `nest(accept(...))`.
- POST nằm **ngoài nhánh Accept** nhưng vẫn trong `path("/api/books")`; chỉ yêu cầu Content-Type JSON.
- Nếu client gửi `Accept: text/html` mà không có route khác, GET có thể không match; HTTP status cuối phụ thuộc mapping/error infrastructure, không tự coi như handler trả 406 chắc chắn.
- Bật nested Accept **không** tự làm JSON object serialization; handler còn phải trả `ServerResponse` có body và converter phù hợp.
- Filter gắn vào nested builder có phạm vi khác filter gắn trên parent builder.

### 8.1. Kết hợp nested path và header

Ví dụ nếu một API thay đổi theo header:

~~~java
RouterFunctions.route()
        .path("/api", api -> api
                .nest(
                        RequestPredicates.headers(
                                h -> "2".equals(
                                        h.firstHeader("API-Version"))),
                        v2 -> v2
                                .GET("/books", handler::booksV2)))
        .build();
~~~

Fragment này cần method `booksV2` trong handler. Nếu còn một route `GET("/books")` v1 rộng đứng trước nhánh v2, route v1 có thể match trước; **điều kiện version cụ thể phải đứng trước fallback**. Với API lớn, dùng một chiến lược versioning tường minh và tests thay vì nhồi các predicates tùy biến vào mọi route.

## 9. HandlerFunction, ServerRequest và ServerResponse

### 9.1. `HandlerFunction<ServerResponse>`

Functional interface về bản chất nhận một `ServerRequest` và tạo `ServerResponse`:

~~~java
ServerResponse health(ServerRequest request) {
    return ServerResponse.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .body("OK");
}
~~~

Không cần `@GetMapping` trên handler method. Router bean liên kết URL với method bằng `handler::health`. Handler vẫn có thể nằm trong Spring-managed `@Component`/`@Service`, dùng constructor injection và gọi application services.

### 9.2. Đọc path và query parameter

~~~java
String rawId = request.pathVariable("id");
long id = Long.parseLong(rawId);

String page = request.param("page").orElse("1");
~~~

Đây là fragments minh họa trong method nhận `ServerRequest request`. `pathVariable` là giá trị path variable của route đã match, không tự là `long`. `param` trả Optional; nếu missing mà gọi `get()` ngay sẽ dẫn đến exception. Parse số và validate range trước khi gọi database.

### 9.3. Đọc headers

~~~java
String requestId = request.headers().firstHeader("X-Request-Id");
MediaType contentType = request.headers().contentType()
        .orElse(MediaType.APPLICATION_OCTET_STREAM);
~~~

`headers().contentType()` trả Optional cho request content type. Header `X-Request-Id` do client gửi không phải bằng chứng danh tính; nếu cần trace ID, nên validate/trust boundary thay vì đưa raw value làm metric label. Đừng log Authorization/Cookie để debug routing.

### 9.4. Đọc body

~~~java
CreateBook dto = request.body(CreateBook.class);
~~~

Đây là fragment cần record/class `CreateBook`, có thể ném lỗi Servlet/IO/conversion. Trong WebMvc.fn, JSON conversion sử dụng `HttpMessageConverter` của Spring MVC. **Chỉ có `contentType(APPLICATION_JSON)` trong route chưa kiểm mọi business rules**, và functional handler không mặc nhiên giống `@Valid @RequestBody` của annotated controller. Hãy validate DTO với code hoặc Jakarta Validator ở service/handler nếu cần.

### 9.5. Tạo response

~~~java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(book);
~~~

~~~java
return ServerResponse.created(URI.create("/api/books/3"))
        .contentType(MediaType.APPLICATION_JSON)
        .body(createdBook);
~~~

~~~java
return ServerResponse.noContent().build();
~~~

Các fragments giả định biến `book` và `createdBook` đã định nghĩa. `ServerResponse` cung cấp fluent builders cho status/headers/body; không trả `ResponseEntity` trực tiếp như kiểu return value chuẩn của WebMvc.fn handler. `ServerResponse.ok().body(...)` ở Servlet API là sync builder, khác `bodyValue(...)` ở WebFlux.fn reactive examples.

### 9.6. So sánh signature annotation và functional

| Annotation MVC | Functional MVC |
| --- | --- |
| `@GetMapping("/{id}")` | `GET("/{id}", handler::byId)` |
| `@PathVariable long id` | `request.pathVariable("id")` rồi parse |
| `@RequestParam String q` | `request.param("q")` |
| `@RequestBody DTO input` | `request.body(DTO.class)` |
| `ResponseEntity.ok(dto)` | `ServerResponse.ok().body(dto)` |
| `@ControllerAdvice`, `@ExceptionHandler` | `onError(...)` trên router builder và MVC exception infrastructure tùy cấu hình |
| `HandlerInterceptor` | `before/after/filter` trên router builder, ngoài các Servlet filters |
| `@RequestMapping` grouping | `path(...)` và `nest(...)` |

Không có nghĩa functional model thiếu tích hợp với Spring Security, MVC message converters hoặc DI. Điểm khác là **cách khai báo routing và handler signature**.

## 10. Ví dụ Java 17 chạy được: API sách dùng nested RouterFunction

Ứng dụng nhỏ minh họa đầy đủ:
- `GET /api/health` → text `OK`.
- `GET /api/books` → JSON danh sách sách.
- `GET /api/books/{id}` → JSON một sách hoặc 404.
- `GET /api/books/featured?view=summary` → JSON sách nổi bật khi tham số khớp.
- `GET /api/books/featured` thiếu `view=summary` → 400 có mã lỗi minh họa.
- `POST /api/books` với JSON body tạo một sách ở in-memory store, HTTP 201 và Location.
- Route `GET` lồng điều kiện `Accept: application/json`, route POST lồng prefix nhưng ràng buộc `Content-Type: application/json`.
- Error mapping `onError(BookMissingException.class, ...)` và `onError(InvalidBookInputException.class, ...)`.

Demo chạy trên **Spring Boot 3.3.5 / Java 17**, sử dụng `spring-boot-starter-web` và không có Spring WebFlux dependency. Data trong bộ nhớ để thấy luồng HTTP; restart sẽ reset. Không coi đây là production database, audit hay authentication.

Cấu trúc:

~~~text
mvc-fn-books/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/mvcfn/
    │   ├── MvcFnBooksApplication.java
    │   ├── data/BookStore.java
    │   └── web/
    │       ├── BookHandler.java
    │       └── BookRoutes.java
    └── test/java/com/example/mvcfn/
        └── BookRoutesTest.java
~~~

### 10.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'mvc-fn-books'
~~~

`build.gradle`:

~~~groovy
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
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không thêm `spring-boot-starter-webflux` chỉ vì thấy tên RouterFunction. Trên Boot 3, các import từ `org.springframework.web.servlet.function` là quan trọng nhất.

### 10.2. Main application

`src/main/java/com/example/mvcfn/MvcFnBooksApplication.java`:

~~~java
package com.example.mvcfn;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcFnBooksApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcFnBooksApplication.class, args);
    }
}
~~~

### 10.3. BookStore: nguồn dữ liệu in-memory thread-safe

`src/main/java/com/example/mvcfn/data/BookStore.java`:

~~~java
package com.example.mvcfn.data;

import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

@Component
public class BookStore {

    public record Book(long id, String title) {}

    private final ConcurrentMap<Long, Book> books =
            new ConcurrentHashMap<>();

    private final AtomicLong ids = new AtomicLong(2);

    public BookStore() {
        books.put(1L, new Book(1L, "Spring Web"));
        books.put(2L, new Book(2L, "Functional MVC"));
    }

    public List<Book> all() {
        return books.values().stream()
                .sorted(Comparator.comparingLong(Book::id))
                .toList();
    }

    public Optional<Book> find(long id) {
        return Optional.ofNullable(books.get(id));
    }

    public Book create(String title) {
        long id = ids.incrementAndGet();
        Book book = new Book(id, title);
        books.put(id, book);
        return book;
    }
}
~~~

Đây là state in-memory dùng để chứng minh route/handler. `ConcurrentHashMap` và `AtomicLong` tránh lỗi phổ biến khi nhiều request tạo ID đồng thời **trong một JVM**. Chúng không chia sẻ dữ liệu giữa nhiều pods/nodes và không cung cấp persistence/transaction. Nếu triển khai sản phẩm thật, thay bằng repository/database, kiểm quyền truy cập, validation, unique constraints và transactions.

### 10.4. BookHandler: nơi xử lý HTTP request

`src/main/java/com/example/mvcfn/web/BookHandler.java`:

~~~java
package com.example.mvcfn.web;

import com.example.mvcfn.data.BookStore;
import com.example.mvcfn.data.BookStore.Book;
import java.net.URI;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@Component
public class BookHandler {

    public record NewBook(String title) {}
    public record ApiError(String code, String message) {}

    public static final class BookMissingException
            extends RuntimeException {
        public BookMissingException(long id) {
            super("Book not found: " + id);
        }
    }

    public static final class InvalidBookInputException
            extends RuntimeException {
        public InvalidBookInputException(String message) {
            super(message);
        }
    }

    private final BookStore store;

    public BookHandler(BookStore store) {
        this.store = store;
    }

    public ServerResponse health(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body("OK");
    }

    public ServerResponse all(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.all());
    }

    public ServerResponse byId(ServerRequest request) {
        String raw = request.pathVariable("id");
        long id;
        try {
            id = Long.parseLong(raw);
        } catch (NumberFormatException badId) {
            throw new InvalidBookInputException(
                    "id must be an integer");
        }

        if (id <= 0) {
            throw new InvalidBookInputException(
                    "id must be positive");
        }

        Book book = store.find(id)
                .orElseThrow(() -> new BookMissingException(id));

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(book);
    }

    public ServerResponse featured(ServerRequest request) {
        Book book = store.find(1L)
                .orElseThrow(() -> new BookMissingException(1L));
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(book);
    }

    public ServerResponse invalidFeatured(ServerRequest request) {
        throw new InvalidBookInputException(
                "featured requires view=summary");
    }

    public ServerResponse create(ServerRequest request)
            throws Exception {

        NewBook input = request.body(NewBook.class);
        if (input == null || input.title() == null ||
                input.title().isBlank()) {
            throw new InvalidBookInputException(
                    "title is required");
        }

        Book book = store.create(input.title().trim());
        return ServerResponse.created(
                        URI.create("/api/books/" + book.id()))
                .contentType(MediaType.APPLICATION_JSON)
                .body(book);
    }
}
~~~

Không phải mọi runtime sẽ gọi handler khi JSON body malformed; request conversion có thể ném exception trước khi có `NewBook`. Error mapping trong router ở dưới xử lý hai loại lỗi nghiệp vụ minh họa, không cố “catch tất cả” và che 500.

Các `ApiError` trong demo chỉ chứa thông tin an toàn. Không trả raw stack trace, SQL errors, credentials hoặc path filesystem từ exception vào JSON. Validation hoàn chỉnh có thể dùng Jakarta Bean Validation riêng với `Validator` hoặc validation trong service; **functional routing không tự thay một `@Valid @RequestBody` của annotated controller**.

### 10.5. BookRoutes: prefix path, nested Accept, parameter predicate và onError

`src/main/java/com/example/mvcfn/web/BookRoutes.java`:

~~~java
package com.example.mvcfn.web;

import static org.springframework.web.servlet.function.RequestPredicates.accept;
import static org.springframework.web.servlet.function.RequestPredicates.contentType;
import static org.springframework.web.servlet.function.RequestPredicates.param;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

@Configuration
public class BookRoutes {

    @Bean
    RouterFunction<ServerResponse> bookRouter(BookHandler handler) {
        return RouterFunctions.route()
                .path("/api", api -> api
                        .GET("/health", handler::health)
                        .path("/books", books -> books
                                .nest(accept(MediaType.APPLICATION_JSON),
                                        json -> json
                                                .GET("/featured",
                                                        param("view", "summary"),
                                                        handler::featured)
                                                .GET("/featured",
                                                        handler::invalidFeatured)
                                                .GET("/{id}", handler::byId)
                                                .GET("", handler::all))
                                .POST("",
                                        contentType(MediaType.APPLICATION_JSON),
                                        handler::create)))
                .onError(BookHandler.BookMissingException.class,
                        (ex, request) ->
                                ServerResponse.status(404)
                                        .contentType(
                                                MediaType.APPLICATION_JSON)
                                        .body(new BookHandler.ApiError(
                                                "BOOK_NOT_FOUND",
                                                "Book does not exist")))
                .onError(BookHandler.InvalidBookInputException.class,
                        (ex, request) ->
                                ServerResponse.badRequest()
                                        .contentType(
                                                MediaType.APPLICATION_JSON)
                                        .body(new BookHandler.ApiError(
                                                "INVALID_BOOK_INPUT",
                                                ex.getMessage())))
                .build();
    }
}
~~~

**Kiểm thứ tự quan trọng:**
1. `path("/api", ...)` gom root API.
2. `GET("/health")` không có điều kiện Accept JSON vì trả text.
3. `path("/books", ...)` gom resource.
4. `nest(accept(JSON), ...)` áp một điều kiện Accept chung cho **toàn nhóm GET**; không áp điều kiện này lên POST nằm ngoài.
5. `GET("/featured", param("view","summary"),...)` phải đứng trước `GET("/featured",...)` fallback.
6. Cả hai featured routes phải đứng trước `GET("/{id}", ...)`; nếu không “featured” bị hiểu là ID.
7. `GET("", ...)` chỉ match danh sách tại prefix `/api/books`.
8. `POST("", contentType(JSON),...)` chỉ match request POST tại prefix với Content-Type JSON phù hợp.
9. `onError` ở router builder map hai exception types được handler ném thành JSON với mã máy đọc.
10. `build()` tạo một `RouterFunction<ServerResponse>` duy nhất và Spring Boot phát hiện bean.

**Đừng giả định `onError` là thay thế tất cả global error handlers.** Nó xử lý các exception đi qua router filter chain của những routes này; exception do security filter, Servlet container hoặc những components khác tạo có thể đi theo error path khác. Phải test đầy đủ cả HTTP stack khi có Spring Security.

### 10.6. Request → route → handler → response

| Request | Route match | Handler | Expected HTTP |
| --- | --- | --- | --- |
| GET `/api/health` | `/api` + `/health` | health | 200 text `OK` |
| GET `/api/books`, Accept JSON | `/api` + `/books` + nested Accept + GET empty | all | 200 JSON list |
| GET `/api/books/1`, Accept JSON | GET `/{id}` | byId | 200 book 1 |
| GET `/api/books/999`, Accept JSON | GET `/{id}` | byId + onError | 404 JSON code `BOOK_NOT_FOUND` |
| GET `/api/books/not-a-number`, Accept JSON | GET `/{id}` | byId + onError | 400 JSON code `INVALID_BOOK_INPUT` |
| GET `/api/books/featured?view=summary`, Accept JSON | parameter-aware featured | featured | 200 JSON book 1 |
| GET `/api/books/featured`, Accept JSON | featured fallback | invalidFeatured | 400 JSON |
| POST `/api/books`, Content-Type JSON | POST empty + Content-Type | create | 201 JSON + Location |
| GET `/api/books`, Accept text/html | nested Accept không match | không phải all | Response phụ thuộc mapping/error path, không giả định JSON 200 |
| POST `/api/books`, Content-Type text/plain | POST Content-Type không match | không phải create | Routing/error status phụ thuộc Spring MVC config |

Bảng minh họa cách đi qua nested routing, không bao hàm authentication, CORS hoặc production validation. Demo không thêm Spring Security starter nên mọi GET/POST được gọi mà không đăng nhập; **điều đó không an toàn cho dữ liệu người dùng thật**.

## 11. Chạy thử với curl

Ở project có Gradle wrapper tương thích Java 17:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 11.1. Health

~~~bash
curl -i http://localhost:8080/api/health
~~~

Dự kiến:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

OK
~~~

`charset`, transfer headers và thứ tự HTTP headers có thể khác theo server; phần cần kiểm là HTTP 200, response text `OK`.

### 11.2. Danh sách sách

~~~bash
curl -i 'http://localhost:8080/api/books' \
  -H 'Accept: application/json'
~~~

Dự kiến 200:

~~~json
[
  {"id":1,"title":"Spring Web"},
  {"id":2,"title":"Functional MVC"}
]
~~~

JSON formatting thật thường là một dòng. Nếu trước đó POST thêm sách, danh sách sẽ có thêm sách mới; ở request sau khi restart sạch, hai sách mặc định trên luôn có mặt.

### 11.3. Chi tiết và 404

~~~bash
curl -i 'http://localhost:8080/api/books/1' \
  -H 'Accept: application/json'

curl -i 'http://localhost:8080/api/books/999' \
  -H 'Accept: application/json'
~~~

Trường hợp ID 1 trả 200:

~~~json
{"id":1,"title":"Spring Web"}
~~~

ID 999 trả 404:

~~~json
{"code":"BOOK_NOT_FOUND","message":"Book does not exist"}
~~~

ID không phải số:

~~~bash
curl -i 'http://localhost:8080/api/books/abc' \
  -H 'Accept: application/json'
~~~

Dự kiến 400:

~~~json
{"code":"INVALID_BOOK_INPUT","message":"id must be an integer"}
~~~

### 11.4. Route nổi bật có param và fallback

~~~bash
curl -i 'http://localhost:8080/api/books/featured?view=summary' \
  -H 'Accept: application/json'
~~~

Dự kiến 200, sách ID 1. Nếu thiếu param:

~~~bash
curl -i 'http://localhost:8080/api/books/featured' \
  -H 'Accept: application/json'
~~~

Dự kiến 400 với `INVALID_BOOK_INPUT`. Nhờ fallback đứng **trước** `/{id}`, chuỗi `featured` không bị parse như một ID.

### 11.5. POST JSON tạo sách

~~~bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"MVC.fn Handbook"}'
~~~

Trên một instance mới chưa POST trước, status 201, header `Location: /api/books/3` và body:

~~~json
{"id":3,"title":"MVC.fn Handbook"}
~~~

Kiểm lại:

~~~bash
curl -i 'http://localhost:8080/api/books/3' \
  -H 'Accept: application/json'
~~~

Dự kiến 200 với sách vừa tạo. ID thật tăng theo số lượt POST, không cố định 3 nếu application đã chạy lâu. Đây là dữ liệu memory-local; restart mất sách mới.

Nếu POST body có title rỗng:

~~~bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"   "}'
~~~

Dự kiến 400 và `INVALID_BOOK_INPUT`. Mã route chỉ bắt loại exception này; JSON syntax hỏng có thể dẫn đến một error response khác tùy Spring MVC converter/container config.

## 12. MockMvc: kiểm route lồng nhau và thứ tự match

MockMvc chạy qua Spring MVC handler mappings mà không cần mở port HTTP. Vì ta đăng ký một `RouterFunction<ServerResponse>` bean, `RouterFunctionMapping` nhận route thật và test có thể gọi giống HTTP client.

`src/test/java/com/example/mvcfn/BookRoutesTest.java`:

~~~java
package com.example.mvcfn;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookRoutesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void healthIsOutsideJsonAcceptNest() throws Exception {
        mvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(content().string("OK"));
    }

    @Test
    void nestedBookListMatchesJsonGet() throws Exception {
        mvc.perform(get("/api/books")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(1))
                .andExpect(jsonPath("$[0].title").value("Spring Web"));
    }

    @Test
    void dynamicIdMatchesAfterSpecificRoutes() throws Exception {
        mvc.perform(get("/api/books/2")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(2))
                .andExpect(jsonPath("$.title").value("Functional MVC"));
    }

    @Test
    void featuredWithParamBeatsVariableRoute() throws Exception {
        mvc.perform(get("/api/books/featured")
                        .param("view", "summary")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1));
    }

    @Test
    void featuredWithoutParamGetsExplicitBadRequest() throws Exception {
        mvc.perform(get("/api/books/featured")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_BOOK_INPUT"));
    }

    @Test
    void invalidNumericIdGetsBadRequest() throws Exception {
        mvc.perform(get("/api/books/not-a-number")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_BOOK_INPUT"));
    }

    @Test
    void unknownBookGets404FromRouterOnError() throws Exception {
        mvc.perform(get("/api/books/99999")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("BOOK_NOT_FOUND"));
    }

    @Test
    void postJsonCreatesResourceAndLocation() throws Exception {
        mvc.perform(post("/api/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"New MVC.fn Book\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location",
                        startsWith("/api/books/")))
                .andExpect(jsonPath("$.title").value("New MVC.fn Book"));
    }

    @Test
    void postBlankTitleGets400() throws Exception {
        mvc.perform(post("/api/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"   \"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_BOOK_INPUT"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

**Điều test chứng minh:** route prefix nesting, JSON Accept predicate, query/form param predicate, route order, handler, custom error response và POST Content-Type. Đừng suy luận MockMvc chứng minh reverse proxy URL rewrite, CORS preflight, cookie policy, TLS hay database transactions.

Bộ test tạo book memory-local trong một method; các test đọc ID 1 và 2 là ổn định vì store không xóa dữ liệu cũ. Nếu cần assert số lượng chính xác ở mọi test, hãy reset store hoặc tạo application context/store riêng theo test; tránh phụ thuộc thứ tự chạy của JUnit.

### 12.1. Test thứ tự bằng negative case

Một bài kiểm thử regression có giá trị là `featuredWithoutParamGetsExplicitBadRequest`: nếu ai đổi thứ tự để `/{id}` đứng trước `/featured` fallback, request có thể bị xử lý nhầm như ID chuỗi. Error code/status ở ví dụ vẫn có thể là 400 vì cả hai nhánh đều map 400; để bắt chính xác **handler** bị chọn, hãy assert thêm message `"featured requires view=summary"` thay vì chỉ status/code.

Trong sản phẩm thật, các tests cần xác nhận **nội dung phản hồi và handler semantics**, không chỉ HTTP status.

## 13. Filters trong RouterFunction Builder

Functional MVC cho phép các filters quanh handler:
- `before(Function<ServerRequest,ServerRequest>)`: biến đổi request trước handler.
- `after(BiFunction<ServerRequest,ServerResponse,ServerResponse>)`: biến đổi/quan sát response sau handler.
- `filter(HandlerFilterFunction<ServerResponse,ServerResponse>)`: bao quanh handler và gọi `next.handle(request)`.
- `onError(Predicate<Throwable>, BiFunction<Throwable,ServerRequest,ServerResponse>)` hoặc `onError(Class<? extends Throwable>,...)`: tạo alternate response cho các exception match.

Ví dụ fragment logging:

~~~java
RouterFunction<ServerResponse> route =
        RouterFunctions.route()
                .GET("/hello", request ->
                        ServerResponse.ok().body("Hello"))
                .filter((request, next) -> {
                    long start = System.nanoTime();
                    try {
                        return next.handle(request);
                    } finally {
                        long elapsed = System.nanoTime() - start;
                        // Ghi metric elapsed với nhãn được allowlist.
                    }
                })
                .build();
~~~

Một `HandlerFilterFunction` chỉ bao quanh **những routes trong builder** mà nó được gắn. Khi gắn trên nested builder, phạm vi có thể giới hạn trong nhánh; khi gắn trên parent, có thể bao trùm cả các routes con. Đây là khác biệt quan trọng khi viết audit/logging, correlation IDs hoặc filters trả response phụ.

### 13.1. Filter ở WebMvc.fn không thay Servlet Filter/Spring Security

`filter((request,next)->...)` không thay authentication/authorization của Spring Security. Nó chỉ áp dụng cho các functional routes được build tại vị trí đó, không phải tất cả MVC controllers/Servlet endpoints. Security protection thường thuộc `SecurityFilterChain` và được áp dụng trước `DispatcherServlet`. Với kiểm soát quyền theo object/tenant, vẫn cần service/domain rules.

Không đưa credentials raw vào tracing logs. Không đo riêng handler duration rồi gọi đó là “HTTP response latency” nếu response writing/network time không nằm trong khoảng đo.

### 13.2. `before` không biến body đã đọc thành unread

Nếu một request filter tự đọc toàn bộ `ServerRequest.body(...)`, handler sau đó có thể không đọc lại được input stream tùy implementation. Tốt hơn là validate metadata/header ở route filter, hoặc dùng một wrapper/caching request body được thiết kế đúng nếu ứng dụng bắt buộc cần kiểm body hai lần. Cũng cần tránh mutate header `Authorization` hoặc user identity trong before filter một cách không an toàn.

### 13.3. `onError` và exception scopes

`RouterFunctions.Builder.onError(...)` giúp tạo response cụ thể khi handler/filter ném exception thuộc phạm vi phù hợp. Nhưng:
- Error phát sinh **trước** khi đến router (auth filter, CORS preflight) thường nằm ngoài handler filter.
- Error khi response body đang stream/đã commit có thể không sửa status được.
- Catch-all `onError(Throwable.class,...)` có thể giấu lỗi programming quan trọng; dùng typed exceptions và default 500 + logging an toàn.
- Một handler có thể tự tạo `ServerResponse.status(400)` thay vì ném exception, lúc đó `onError` không cần chạy.
- Các nhánh error từ message conversion và global HandlerExceptionResolver có hành vi theo implementation/version; hãy test dạng lỗi cụ thể.

## 14. `@ControllerAdvice` và functional endpoints

Trong annotated MVC, `@RestControllerAdvice`/`@ExceptionHandler` thường được sử dụng cho exception mapping. Với functional MVC, `onError` trên router builder là nơi rất rõ để bao một nhóm functional routes; các MVC exception resolvers khác vẫn tồn tại và tham gia theo cách Spring xử lý request.

Không giả định:
- Mọi `@ControllerAdvice` chỉ chọn annotated handler và bỏ qua functional route.
- Hoặc một advice bất kỳ sẽ luôn bắt mọi lỗi ném từ RouterFunction, kể cả lỗi ở Security filter.
- Hay một catch-all `onError` có thể trả lỗi JSON ngay cả khi network body đã gửi một phần.

Hãy viết integration tests cho HTTP response cuối của từng lỗi cụ thể. Khi muốn một ProblemDetail schema thống nhất giữa annotated MVC, functional MVC và Spring Security, thiết kế shared error model nhưng cấu hình đúng **từng** error entry point/handler layer.

## 15. RouterFunctions và Spring Security/CORS

### 15.1. SecurityFilterChain vẫn cần thiết

Dù route được khai báo bằng `RouterFunction` thay vì `@RestController`, request vẫn đi qua Servlet filters và Spring Security nếu có dependency/config. Ví dụ security policy ở conceptual layer:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/health").permitAll()
    .requestMatchers("/api/books/**").authenticated()
    .anyRequest().denyAll())
~~~

Fragment này cần SecurityConfig và `HttpSecurity`. Nó **không** tự có trong demo không-security của mục 10. Nếu muốn POST/DELETE cần CSRF token đối với cookie-authenticated browser clients, không được bỏ qua chỉ vì handler là functional.

### 15.2. CORS khi có frontend khác origin

Browser khác origin gửi `POST /api/books` với `Content-Type: application/json` thường phải thực hiện preflight OPTIONS. Predicate `contentType(APPLICATION_JSON)` của POST **không** xử lý CORS thay browser/framework. CORS cần cấu hình ở filter/MVC/Security layer phù hợp, cho đúng origin/method/header, và actual request vẫn kiểm authentication/authorization/CSRF.

Nếu một OPTIONS chỉ khớp route GET/POST không rõ ràng, đừng tạo một fallback `all()` tự echo mọi origin tùy ý. Dùng Spring MVC CORS infrastructure hoặc cấu hình Security `cors()` đúng, và test với browser/MockMvc.

### 15.3. Functional handlers và user identity

Một `ServerRequest` có truy cập Servlet request/principal APIs tương ứng; identity nên được lấy từ authentication context tin cậy, không từ `?user=...` do client tự gửi. Nếu route xử lý `/api/books/{id}` theo owner/tenant, phải kiểm quyền với dữ liệu thực trước khi trả body, kể cả ở GET.

## 16. Functional MVC và annotation MVC: khi nào chọn?

| Khía cạnh | Functional MVC | Annotation MVC |
| --- | --- | --- |
| Khai báo route | Bean `RouterFunction`, predicate DSL | `@RequestMapping`/`@GetMapping` trên method |
| Gom prefix | `path/nest` | `@RequestMapping` trên class |
| Điều kiện media/header | `accept/contentType/headers` | `produces/consumes/headers` |
| Thứ tự match | Theo thứ tự compose | Chọn mapping đặc hiệu theo framework |
| Handler signature | `ServerRequest -> ServerResponse` | Tham số có thể `@PathVariable`, `@RequestBody`, `Model`... |
| Binding/validation | Chủ động dùng `ServerRequest.body/bind` và validator | Argument resolvers, `@Valid`... |
| Filter theo nhóm route | `before/after/filter/onError` | Servlet filters/interceptors/advice |
| OpenAPI/codegen ecosystem | Có thể cần explicit docs/metadata | Nhiều tools suy ra tốt từ annotations |
| Phù hợp | Routing DSL, composition, chia module | CRUD controllers thông dụng, DI/validation quy ước |

Đừng thay tất cả controllers sang WebMvc.fn chỉ vì functional syntax ngắn hơn. Nếu phần lớn code dùng `@Valid`, `@RequestBody`, Springdoc metadata, annotated method security, annotation controllers có thể dễ hiểu hơn. Nếu cần compose nhiều routes từ modules, filter theo nhóm, tách routing declarations khỏi handlers, functional MVC là lựa chọn đáng cân nhắc.

Một codebase có thể phối hợp hai mô hình, nhưng route ownership phải rõ và test overlaps để không tạo behavior bất ngờ.

## 17. Tách router thành nhiều module

Một ứng dụng lớn có thể định nghĩa:
- `BookRoutes` cho `/books`.
- `AuthorRoutes` cho `/authors`.
- `HealthRoutes` cho `/health`.

Sau đó ghép lại bằng `RouterFunctions.Builder.add(...)` hoặc `RouterFunction.and(...)`, và đặt prefix bằng `path(...)`. Ví dụ conceptual fragment:

~~~java
RouterFunction<ServerResponse> combined =
        RouterFunctions.route()
                .path("/api/books", bookRoutes::routes)
                .path("/api/authors", authorRoutes::routes)
                .build();
~~~

Ở đây `bookRoutes.routes()` và `authorRoutes.routes()` phải trả đúng `RouterFunction<ServerResponse>` với child paths tương đối, và handler beans được inject. Fragment không chạy riêng vì chưa có hai classes. Khi có nhiều `RouterFunction` beans, hãy kiểm thứ tự bean registration/order và tránh overlapping catch-all routes; không giả định thứ tự file/source hoặc tên bean là business contract.

### 17.1. Không lồng logic nghiệp vụ vào Router bean

`@Bean RouterFunction` được tạo khi ứng dụng startup, không phải khi từng HTTP request chạy. Vì thế:
- Đừng query database lấy sách khi đang xây DSL và giữ cố định kết quả cho mọi request.
- Đừng dùng `System.currentTimeMillis()` trong routing configuration để quyết định policy theo request.
- Đừng tạo new service/thread pool trong handler lambda mỗi request.
- Nên inject handler/service với constructor, dễ test và bảo trì.
- Route predicates nên thuần, rẻ, không có side effects; business logic ở handler/service.

## 18. Path pattern và nguy cơ route rộng

Spring Framework 6.x dùng path matching infrastructure có `PathPattern`. Path variable `/{id}` có thể match nhiều chuỗi, không nhất thiết chỉ numeric. Path wildcard `/**` có thể match phạm vi lớn; nếu đứng trước routes cụ thể trong functional chain, nhiều request đi nhầm handler.

Ví dụ anti-pattern:

~~~java
RouterFunctions.route()
        .GET("/api/{anything}", handler::catchAll)
        .GET("/api/health", handler::health)
        .build();
~~~

Với thứ tự này, `/api/health` có thể bị route đầu match. Sửa bằng cách đưa route cụ thể lên trước. Nếu chức năng catch-all thật sự cần thiết, đặt nó cuối, kiểm URL normalization, encoded segments, trailing slash và method matching theo framework/server version.

Không tự giả định functional routes và annotation mappings có cùng ưu tiên khi cả hai đăng ký cùng path; phải test với full Spring application context.

## 19. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân hay gặp | Hướng kiểm |
| --- | --- | --- |
| `RouterFunction` không chạy trong MVC | Import nhầm `web.reactive.function.server` | Dùng `web.servlet.function`, starter Web |
| GET `/featured` bị parse làm `id` | Route `/{id}` đứng trước route cụ thể | Đảo thứ tự |
| Nested route luôn 404 | Prefix bị lặp/thiếu hoặc child path sai | Vẽ full path từ các `path` |
| GET JSON không match | `Accept` không tương thích nested predicate | Kiểm Accept và nhóm `nest` |
| POST JSON không match | Thiếu/nhầm Content-Type | Kiểm contentType predicate |
| Handler không đọc được body lần hai | Filter/interceptor đã consume input stream | Tránh đọc hai lần, dùng caching wrapper đúng |
| `param("view","summary")` không match | Thiếu param hoặc giá trị khác | Kiểm request parameter thực, fallback |
| `queryParam(...)` không biên dịch | Dùng API WebFlux.fn ở Servlet package | Dùng `param(...)` |
| `ServerResponse.bodyValue(...)` không có | Copy builder của WebFlux.fn | Dùng `ServerResponse.ok().body(...)` |
| Không serialize JSON record | Thiếu Jackson converter hoặc sai Content-Type | Kiểm starter, converter và response |
| `@Valid` không tự chạy | Functional body decode không tương đương annotated resolver | Gọi validator/validate tại service |
| 404/406/415 khác dự đoán | Route không match; các mapping/resolvers xử lý khác | Test actual response/mapping context |
| Catch-all `onError` che 500 | Nuốt mọi exception | Typed exceptions và safe default logging |
| Route chạy được nhưng không bảo mật | Nhầm predicate với authorization | Spring Security + domain auth |
| Browser báo CORS ở POST | Preflight OPTIONS chưa cấu hình | CORS/Security filter integration |
| Test GET pass nhưng POST tạo dữ liệu trùng | In-memory IDs, state dùng chung giữa tests | Test isolation và persistence đúng |
| API Docs không tìm functional endpoint | Tool chỉ introspect annotations | Explicit OpenAPI mappings/config |
| Một request chạy hai route | Hiểu sai composition | Router chọn route đầu match, rà side effects |
| Lỗi khi phối hợp annotation routes | HandlerMapping order/overlap | Kiểm mappings, integration tests |
| Dùng blocking JDBC trong WebMvc.fn tưởng reactive | Nhầm programming model | MVC Servlet vẫn blocking |
| Nhiều routers beans có thứ tự không rõ | Registration/order không tường minh | Compose rõ và test |

### Quy trình debug có thứ tự

1. Xác nhận dependency Spring Web/Boot và **imports Servlet WebMvc.fn**.
2. Xác nhận bean `RouterFunction<ServerResponse>` được tạo trong Spring context.
3. Vẽ full path từ tất cả `path(prefix)`/`nest(path)`.
4. Kiểm thứ tự: static/cụ thể trước variable/wildcard.
5. Ghi method, path, Accept, Content-Type, query/form params và custom headers thực sự gửi.
6. Kiểm nested Accept/Content-Type/header predicates có làm route không match không.
7. Phân biệt không match route và exception trong handler; kiểm đúng status/error code.
8. Nếu có Security, xác minh filter chain/CORS/CSRF trước MVC.
9. Kiểm message converters và body validation.
10. Thêm MockMvc tests cho positive, negative và route ordering, sau đó E2E với proxy/gateway nếu có.

## 20. Checklist review trước production

- [ ] Sử dụng đúng package `org.springframework.web.servlet.function`.
- [ ] Bean RouterFunction được Spring quản lý, handlers inject qua constructor.
- [ ] Routes cụ thể đặt trước wildcard/variable; fallback cuối cùng.
- [ ] Nested path prefixes chính xác, child paths không trùng prefix.
- [ ] `accept`/`contentType` dùng đúng ý nghĩa HTTP, không thay validation.
- [ ] `RequestPredicates.param` đúng Servlet API, không lẫn `queryParam` của WebFlux.
- [ ] Input path/query/body được parse, validate và giới hạn trước domain operations.
- [ ] Error mapping 400/404/500 an toàn, không leak exception details.
- [ ] SecurityFilterChain, CSRF/CORS, tenant/object authorization được áp dụng đúng.
- [ ] Các filters ở router có scope rõ; không tự thay Spring Security.
- [ ] API docs/OpenAPI có thể mô tả routes chức năng; có contract tests.
- [ ] Đo performance của handler và converter, không tự cho rằng functional MVC non-blocking.
- [ ] MockMvc kiểm nesting, param/header/media predicates, conflicts, status và response body.
- [ ] Integration tests qua proxy/gateway nếu route cần rewrite.
- [ ] Module lớn được compose có thứ tự rõ, không có catch-all che route quan trọng.

### Câu hỏi tự kiểm tra

**1.** `RouterFunction` khác `HandlerFunction` thế nào?

**Trả lời:** RouterFunction tìm một HandlerFunction phù hợp request; HandlerFunction xử lý ServerRequest và trả ServerResponse.

**2.** Tại sao route `GET("/books/{id}")` không nên đứng trước `GET("/books/featured")`?

**Trả lời:** Functional routes được xét theo thứ tự, `{id}` có thể nhận `featured`, khiến handler sai được chọn.

**3.** `path("/api", ...)` và `nest(accept(JSON), ...)` khác nhau gì?

**Trả lời:** path nhóm URL prefix; nest áp RequestPredicate bất kỳ (ở đây Accept) lên routes con.

**4.** `Content-Type` và `Accept` ảnh hưởng predicates nào?

**Trả lời:** Content-Type của body request dùng `contentType`; Accept mô tả response client mong muốn dùng `accept`.

**5.** Trong WebMvc.fn Servlet, dùng `param` hay `queryParam`?

**Trả lời:** Dùng `RequestPredicates.param` của `org.springframework.web.servlet.function`. Không nhầm API `queryParam` của WebFlux.fn.

**6.** Nested Accept JSON có tự serialize DTO sang JSON không?

**Trả lời:** Không. Nó chỉ kiểm điều kiện match; `ServerResponse` và MVC HttpMessageConverter mới tạo response body.

**7.** Router filter có thay `SecurityFilterChain` không?

**Trả lời:** Không. Router filter thuộc các routes chức năng, còn Spring Security là bảo vệ HTTP requests qua Servlet filter chain và service/domain authorization.

**8.** Vì sao không chỉ assert HTTP 200 khi test functional routing?

**Trả lời:** Có thể match sai handler nhưng status vẫn 200. Cần assert body/headers và trường hợp route tương phản.

**9.** WebMvc.fn có tự dùng non-blocking I/O như WebFlux.fn không?

**Trả lời:** Không. Nó là Servlet MVC programming model, vẫn có thể block trên JDBC hoặc đồng bộ network I/O.

## 21. Tài liệu chính thức

- [Spring Framework 6.2 — Functional Endpoints (Spring MVC)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html): handler functions, request predicates, router functions, nested routing, filtering.
- [Spring Framework 6.1 — RouterFunctions Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/function/RouterFunctions.html): route/nest API.
- [Spring Framework 6.1 — RouterFunctions.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/servlet/function/RouterFunctions.Builder.html): `GET/POST/path/nest/onError/filter`.
- [Spring Framework 6.1 — RequestPredicates Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/servlet/function/RequestPredicates.html): `GET/POST/path/param/headers/accept/contentType`.
- [Spring Framework 6.1 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/servlet/function/ServerRequest.html): path variables, parameters, headers, body.
- [Spring Framework 6.1 — ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/function/ServerResponse.html): response status, headers, body builders.
- [Spring Framework 6.2 — MVC DispatcherServlet](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet.html): overall MVC handler mapping and adapter pipeline.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): integration-style MVC test without opening a server port.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request authorization independent of router syntax.
- [Spring Framework — CORS trong Servlet MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): cross-origin request policies.

**Ghi nhớ:** WebMvc.fn dùng `RouterFunction` để chọn `HandlerFunction` qua `RequestPredicate` rồi trả `ServerResponse`. `path` gom prefix, `nest` gom điều kiện chung, còn **thứ tự route phải được thiết kế chủ động**. Chỉ dùng predicate để chọn tuyến — bảo mật, validation, error semantics và dữ liệu nghiệp vụ vẫn cần lớp riêng và kiểm thử HTTP đầy đủ.
