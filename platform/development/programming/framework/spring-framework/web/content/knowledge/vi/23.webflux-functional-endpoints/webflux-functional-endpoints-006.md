# Filter cho router, xử lý lỗi và tạo phản hồi thống nhất trong Functional WebFlux

> **Phạm vi:** Spring Framework 6.2.x, Spring Boot 3.5.x, Java 17+ và **WebFlux.fn** (package `org.springframework.web.reactive.function.server`). Bài học tập trung vào `RouterFunctions.Builder.before`, `after`, `filter`, `onError`, chuẩn hóa status/headers/JSON error bằng response factory và ranh giới giữa filter của một router với `WebFilter`/`ErrorWebExceptionHandler` toàn hệ thống. Demo hoàn chỉnh dùng `Mono<ServerResponse>`, Spring Reactive Web, cURL và WebTestClient. Không nhầm với **WebMvc.fn**: handler MVC trả `ServerResponse` đồng bộ và được chạy trên Servlet stack.

## 1. Vì sao router cần filter và error policy?

Khi API có nhiều handlers, những nhu cầu như request ID, log status, chặn request theo policy, phân loại input lỗi và trả error body thường bị viết lại ở từng method. Dùng filter và response factory giúp tránh lặp logic và tạo một HTTP contract dễ dùng cho mobile/web clients.

```text
HTTP request
     |
WebFilter / Spring Security            [toàn ứng dụng]
     |
DispatcherHandler
     |
RouterFunctionMapping
     |
RouterFunction + RequestPredicate     [chỉ khi route match]
     |
  before / filter
     |
  next.handle(ServerRequest)
     |
  Mono<ServerResponse>
     |
  onError -> Mono<ServerResponse>      [nếu lỗi trong scope]
     |
  after (quan sát response object)
     |
ServerResponseResultHandler + codecs
     |
HTTP response bytes
```

Sơ đồ là **mô hình trách nhiệm**, không phải cam kết mọi filter được gọi theo đúng thứ tự vẽ. Spring ghép các filter theo thứ tự đăng ký/builder scope; khi một thứ tự là requirement nghiệp vụ, hãy thể hiện nó rõ và kiểm thử. Hơn nữa, một `ServerResponse` đã dựng không đồng nghĩa body đã được chuyển xong tới client.

### 1.1. Kết quả mong muốn

- Thành công: giữ status đúng (200, 201, 204), response DTO/JSON phù hợp và `X-Request-Id`.
- Thất bại nghiệp vụ: HTTP 400/404/409 hoặc 5xx thực tế, body `application/problem+json` ổn định.
- Có mã lỗi máy đọc được (`code`) để frontend phân nhánh mà không parse tiếng Anh của `detail`.
- Không lộ raw exception, stack trace, mật khẩu, SQL connection string và tenant data trong response.
- Những lỗi từ đường dẫn không match, decoder, security hoặc quá trình stream phải có chiến lược **global** nếu muốn thống nhất trên toàn hệ thống.

**Chuẩn hóa response không có nghĩa luôn trả HTTP 200 với `{"success":false}`.** HTTP status là phần của hợp đồng và monitoring.

## 2. Nền tảng WebFlux.fn

Functional WebFlux mô tả routing và behavior bằng interfaces:

| Thành phần | Ý nghĩa | API tiêu biểu |
| --- | --- | --- |
| `RouterFunction<ServerResponse>` | Chọn handler khi request match | `RouterFunctions.route()` |
| `HandlerFunction<ServerResponse>` | Xử lý request, trả response reactive | `Mono<ServerResponse> handle(ServerRequest)` |
| `ServerRequest` | URI/method/headers/query/body/attributes | `pathVariable`, `queryParam`, `bodyToMono` |
| `ServerResponse` | Status, headers và response body | `status`, `ok`, `created`, `bodyValue`, `body` |
| `RequestPredicate` | Điều kiện route | `accept`, `contentType`, `method`, `path` |
| `HandlerFilterFunction` | Bao quanh handler chain | `filter((request, next) -> ...)` |

Ví dụ một router bean:

```java
@Bean
RouterFunction<ServerResponse> routes(BookHandler handler) {
    return RouterFunctions.route()
            .GET("/api/books", handler::list)
            .GET("/api/books/{id}", handler::get)
            .POST("/api/books", handler::create)
            .build();
}
```

Đây là snippet trong configuration class, cần `BookHandler` và các imports. Method trong handler có chữ ký:

```java
Mono<ServerResponse> get(ServerRequest request) {
    // Kết hợp dữ liệu và tạo ServerResponse bất đồng bộ.
}
```

Trong WebFlux.fn, **RouterFunctions được đánh giá theo thứ tự**, vì vậy route tĩnh như `/api/books/stats` nên đặt trước `/api/books/{id}`. Đừng dựa vào quy tắc comparator của annotated `@GetMapping` để giả định Spring tự đảo route.

## 3. Scope: Router filter và WebFilter khác nhau

| Công cụ | Hoạt động ở đâu? | Nên dùng |
| --- | --- | --- |
| `RouterFunctions.Builder.before` | Handler đã match thuộc builder | Bổ sung request metadata, request attributes |
| `RouterFunctions.Builder.after` | Response object từ routes trong builder | Logging/tracing response metadata |
| `RouterFunctions.Builder.filter` | Functional handler chain thuộc builder | Kiểm tra precondition, short-circuit, wrapper |
| `RouterFunctions.Builder.onError` | Lỗi phù hợp phát sinh trong handler/filter chain | Map domain exception sang HTTP error |
| `RouterFunction.filter(...)` | Một router function đã được tạo | Áp dụng reusable handler filter |
| `WebFilter` | Reactive HTTP handler chain toàn ứng dụng | Auth, request ID toàn cục, CORS, observation |
| `ErrorWebExceptionHandler` | Lỗi từ WebHandler chain chưa được giải quyết | Fallback, codec/routing errors |
| `@RestControllerAdvice` | Chủ yếu annotation-based controller methods | Annotation exception handling |

**Ranh giới cần nhớ:** filter của router thường chỉ chạy nếu router **đã tìm thấy handler**. Request `GET /path-not-exist` có thể bypass cả `before`, `filter` và `onError` của router đó. Do đó không nên ghi README hoặc API spec rằng “mọi lỗi 404 đều có Problem Details giống router-local 404” nếu chưa có global error handling.

### 3.1. Nested filters chỉ áp dụng đúng nhóm

```java
RouterFunction<ServerResponse> router = RouterFunctions.route()
        .path("/api", api -> api
                .GET("/public", handler::publicData)
                .path("/private", secured -> secured
                        .GET("/account", handler::account)
                        .filter(privateFilter)))
        .filter(commonFilter)
        .build();
```

Đây là snippet, cần handlers và filters được định nghĩa. Filter bên trong nested private builder chỉ áp dụng private routes, còn filter bên ngoài có thể bao toàn bộ các routes của outer builder. Khi thêm route mới, phải review xem nó có nằm trong scope filter dự định hay không. Authentication/authorization production nên được đảm bảo bởi Spring Security reactive filter chain và object-level checks, không chỉ bởi một router-local lambda dễ bị bỏ sót.

## 4. before: biến đổi ServerRequest

`before` nhận function `ServerRequest -> ServerRequest`:

```java
.before(request -> ServerRequest.from(request)
        .header("X-Internal-Mode", "demo")
        .build())
```

Đây là snippet biến đổi request abstraction cho các handlers được match. Đừng tự sửa `Authorization`, `Host` hay `X-Forwarded-*` một cách tùy tiện rồi coi thông tin trở thành đáng tin. Request header vẫn có thể do client gửi.

### 4.1. Tạo request ID

`ServerRequest.attributes()` trả một mutable map của request attributes. Có thể dùng:

```java
.before(request -> {
    request.attributes().computeIfAbsent(
            "demoRequestId",
            ignored -> UUID.randomUUID().toString());
    return request;
})
```

Snippet này cần import `java.util.UUID`. Request ID được đặt vào map, nhưng **chưa tự động xuất hiện ở response header**. Response factory cần đọc và viết `X-Request-Id`. Khi có nhiều filters với thứ tự phức tạp, helper `computeIfAbsent` giúp cùng request nhận một ID nhất quán nếu trước đó chưa có.

### 4.2. Không block trong before

Đây là một anti-pattern:

```java
// Sai: chặn reactive event loop, consume body ngoài vòng đời chính.
.before(req -> {
    CreateBook body = req.bodyToMono(CreateBook.class).block();
    return req;
})
```

`before` nên làm thao tác metadata rẻ. Nếu cần decode JSON và validate, thực hiện trong handler reactive pipeline hoặc một filter được thiết kế để consume/decorate body **đúng một lần**. Không gọi `bodyToMono()` trong filter rồi lại đọc body lần hai tại handler mà không có cơ chế replay được thiết kế.

## 5. filter: bao quanh và có thể short-circuit

`filter` nhận một `HandlerFilterFunction`:

```java
.filter((request, next) -> {
    if (shouldReject(request)) {
        return ServerResponse.status(HttpStatus.SERVICE_UNAVAILABLE)
                .build();
    }
    return next.handle(request);
})
```

Đây là snippet: `shouldReject` phải được định nghĩa. Nếu không gọi `next.handle(request)`, business handler không chạy. `next.handle(...)` trả `Mono<ServerResponse>`; filter có thể compose bằng `map`/`flatMap`/`doFinally` mà không `block()`.

### 5.1. Một ví dụ short-circuit rõ ràng

```java
.filter((request, next) -> {
    if ("yes".equalsIgnoreCase(
            request.headers().firstHeader("X-Demo-Block"))) {
        return ApiHttp.problem(request,
                HttpStatus.SERVICE_UNAVAILABLE,
                "DEMO_BLOCKED",
                "Demo request was blocked");
    }
    return next.handle(request);
})
```

`X-Demo-Block` là header **được client tự kiểm soát** và chỉ để minh họa. Đừng dùng header này làm bằng chứng người dùng có quyền hoặc làm công tắc bảo trì production. Với maintenance thực, lấy trạng thái từ cấu hình tin cậy server-side.

### 5.2. Observation không đồng nghĩa đã gửi xong body

```java
.filter((request, next) -> {
    long begin = System.nanoTime();
    return next.handle(request)
            .doOnNext(response -> recordStatus(
                    response.statusCode().value()))
            .doFinally(signal -> recordTime(
                    System.nanoTime() - begin, signal));
})
```

Đây là snippet, cần hàm `recordStatus` và `recordTime`. Nó theo dõi lifecycle của **Mono dựng ServerResponse**, không chắc đo toàn bộ HTTP body transmission. Một SSE stream có thể tiếp tục phát hàng phút sau khi đã tạo response object. Metrics end-to-end nên tích hợp đúng tầng HTTP/server Observation.

### 5.3. Khi nào không dùng router filter?

Không thay Spring Security `SecurityWebFilterChain` bằng logic kiểm tra `X-Role` do client gửi. Các nhiệm vụ auth, session, CSRF và CORS nên ở global reactive web/security layer. Router filter phù hợp precondition route-specific, policy rõ phạm vi, logic logging và response preparation.

## 6. after: quan sát ServerResponse

`after` nhận `(ServerRequest, ServerResponse) -> ServerResponse`.

```java
.after((request, response) -> {
    System.out.printf("path=%s status=%d%n",
            request.path(),
            response.statusCode().value());
    return response;
})
```

Trong production dùng SLF4J/Micrometer thay stdout; log có redaction, không ghi token/cookie/body nhạy cảm. Không hiểu thời điểm `after` chạy như “client đã nhận tất cả bytes”.

**Bẫy mất body:** nếu muốn thêm header, đừng vội làm `ServerResponse.from(response).header(...).build()`. Việc tạo response mới từ status/headers và gọi build mà không copy body publisher có thể làm mất payload. Trong demo sử dụng **response factories** đặt status/headers ngay khi xây từng response, thay vì sửa đối tượng response đã có.

### 6.1. Exception trong after

Nếu `after` ném exception, kết quả phụ thuộc filter composition, lỗi đã commit hay chưa. Logging/observation helper phải không phá response; tránh blocking I/O hoặc thao tác dễ ném error trong after. Test callback/filter order nếu môi trường thêm nhiều nested builders.

## 7. onError: phân loại ngoại lệ trong router scope

Một router-level error mapper:

```java
.onError(BadInputException.class,
        (ex, request) -> ApiHttp.problem(
                request, HttpStatus.BAD_REQUEST,
                "INVALID_INPUT", ex.getMessage()))
```

Chữ ký response provider trong **WebFlux.fn** là một hàm trả `Mono<ServerResponse>`. Với **WebMvc.fn** là `ServerResponse` đồng bộ. Đây là lý do rất phổ biến khiến code copy giữa hai module không compile.

### 7.1. Ba nhóm lỗi cần tách

```text
BadInputException          -> HTTP 400 + INVALID_INPUT
ItemMissingException       -> HTTP 404 + ITEM_NOT_FOUND
IllegalStateException      -> HTTP 500 + INTERNAL_ERROR (demo)
```

Đây là mapping do ứng dụng thiết kế, không phải Spring tự gán status cho custom exceptions. Với domain conflict có thể thêm `ConflictException -> 409`, nhưng cần một nguyên nhân cụ thể như resource name trùng, optimistic locking failure. Không mapping **mọi `IllegalArgumentException`** thành 400 ở production vì lỗi lập trình cũng có thể là IllegalArgumentException.

### 7.2. onError vs onErrorResume

- `onErrorResume` bên trong service/publisher xử lý một lỗi có ý nghĩa nghiệp vụ cụ thể: fallback remote source, chuyển missing value thành typed exception, cleanup có kiểm soát.
- `RouterFunctions.Builder.onError` biến lỗi trong functional handler chain thành **HTTP response nhất quán** cho nhóm routes.
- `ErrorWebExceptionHandler` xử lý **global** exceptions còn chưa xử lý từ web handler chain.

Ví dụ service fallback:

```java
return service.find(id)
        .onErrorResume(RemoteTimeoutException.class,
                ex -> cachedService.find(id))
        .flatMap(book -> ServerResponse.ok().bodyValue(book));
```

Snippet chỉ minh họa khi cached result thực sự được phép dùng. Không fallback dữ liệu quyền truy cập bằng giá trị mở rộng permissions và không tự `onErrorResume(ex -> Mono.empty())` cho mọi lỗi vì dễ gây partial result vô hình.

### 7.3. Lỗi đồng bộ và reactive

Một handler có thể ném `BadInputException` ngay khi parse query:

```java
long id = Long.parseLong(request.pathVariable("id"));
return service.find(id).flatMap(item -> ServerResponse.ok().bodyValue(item));
```

Hoặc nhận `Mono.error(...)` sau async operation:

```java
return service.find(id)
        .switchIfEmpty(Mono.error(new ItemMissingException()))
        .flatMap(item -> ServerResponse.ok().bodyValue(item));
```

Đó là hai thời điểm khác nhau. Route `onError` được thiết kế để xử lý lỗi từ chain của handler, nhưng luôn test cả synchronous exception và reactive error signal trên Spring version được sử dụng.

## 8. Một error contract thống nhất theo RFC 9457

**RFC 9457 Problem Details** quy định các thành phần tiêu chuẩn của error representation. Demo chọn record tự định nghĩa với các fields:

| Field | Vai trò |
| --- | --- |
| `type` | URI reference định danh loại lỗi; ví dụ `about:blank` |
| `title` | Tên lỗi ổn định, tương ứng HTTP status |
| `status` | Con số status phải trùng HTTP status |
| `detail` | Chi tiết an toàn cho client, không lộ secrets |
| `instance` | Đường dẫn resource/request gây lỗi |
| `code` | Mã lỗi tùy biến ổn định để client tự xử lý |
| `requestId` | ID tương quan cho log/support |

Response mẫu:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
X-Request-Id: <server-generated-id>

{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Item not found",
  "instance": "/api/items/999",
  "code": "ITEM_NOT_FOUND",
  "requestId": "<same-server-generated-id>"
}
```

Đây là shape minh họa, không phải một requestId cố định. Hai extension members `code`/`requestId` hợp lệ theo định hướng RFC 9457 nhưng cần được công bố trong API contract. Nếu không có problem type URI riêng, `about:blank` phù hợp.

### 8.1. Có nên dùng Spring ProblemDetail không?

Spring Framework cung cấp `org.springframework.http.ProblemDetail`, ví dụ:

```java
ProblemDetail pd = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND, "Item not found");
pd.setTitle("Not Found");
pd.setType(URI.create("about:blank"));
pd.setInstance(URI.create("/api/items/999"));
pd.setProperty("code", "ITEM_NOT_FOUND");
```

Đây là snippet, cần imports. Có thể ghi qua `ServerResponse.status(NOT_FOUND).contentType(APPLICATION_PROBLEM_JSON).bodyValue(pd)` với codec phù hợp. Demo sử dụng record `ApiProblem` để minh bạch JSON fields và không phụ thuộc Bean Validation/exception abstractions thêm.

### 8.2. Lỗi nội bộ phải được che ở HTTP edge

Không trả:

```json
{"error":"database at 10.0.0.5 refused connection; secret=..."}
```

Nên trả:

```json
{
  "type":"about:blank",
  "title":"Internal Server Error",
  "status":500,
  "detail":"Unexpected server error",
  "instance":"/api/items/boom",
  "code":"INTERNAL_ERROR",
  "requestId":"..."
}
```

Log exception đầy đủ (sau redaction) ở server tương quan với requestId. Không gửi stack trace, raw SQL, JWT hoặc connection details sang client.

## 9. Ranh giới: lỗi nào onError không bao hết?

Một request có thể fail **trước** hoặc **sau** functional handler:

| Nguồn lỗi | Thường qua router-local onError? | Cần chú ý |
| --- | --- | --- |
| Bad input từ matched handler | Có | Dùng typed exception 400 |
| Không tìm thấy record trong handler | Có | Typed exception 404 |
| Service failure trong returned Mono | Có thể trong router filter chain | 500 generic, không leak |
| Router không match URL | **Không** | Global 404 error handling |
| CORS/CSRF/auth fail trước router | **Không** | Reactive Security/CORS filters |
| Content-Type/Accept predicate mismatch | Có thể không có matched handler | Test 404/406/415 theo policy |
| JSON decoder malformed trong handler | Tùy nơi phát lỗi | Global codec handling hoặc typed mapping |
| Exception khi body writer đã flush data | Không thể chắc đổi status | Streaming error strategy |
| Client ngắt kết nối | Không luôn có body lỗi để gửi | Cancel/log/cleanup |

### 9.1. ErrorWebExceptionHandler

Spring WebFlux định nghĩa `ErrorWebExceptionHandler` làm global web exception boundary. Spring Boot có error handling tự cấu hình cho WebFlux, và có thể tùy biến `ErrorAttributes` hoặc dùng `AbstractErrorWebExceptionHandler` khi cần kiểm soát error response đồng nhất toàn ứng dụng. Ví dụ signature interface:

```java
// Signature tham khảo, không phải implementation đủ để compile.
Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
```

Triển khai thực sự phải set HTTP status, headers và ghi JSON bytes bằng reactive APIs/codecs **trước khi committed**, tôn trọng DataBuffer lifecycle, handler ordering và Boot default handler. Không tạo một global error handler nửa vời rồi tự `writeWith` buffer không release, gây leak/double write.

### 9.2. Error khác security policy

401 Unauthorized (chưa xác thực) và 403 Forbidden (không đủ quyền) thường do `SecurityWebFilterChain`/reactive exception handlers tạo, không phải business router. Muốn cùng schema `ApiProblem` cho security errors thì cấu hình `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler` của reactive Spring Security, đảm bảo không vô ý trả 200/400 thay 401/403.

### 9.3. Annotation advice không là universal router filter

`@RestControllerAdvice`/`@ExceptionHandler` đặc biệt hữu ích cho annotated WebFlux controllers; đừng giả định nó tự bao mọi functional router filter, CORS, static resources, security và những request không có handler. Phân biệt ranh giới lỗi trong kiến trúc và kiểm thử với WebTestClient.

### 9.4. Lỗi sau HTTP commit

Khi response SSE/NDJSON đã gửi headers và chunks đầu, HTTP status không thể đổi từ 200 sang 500 một cách đáng tin và không thể chèn một Problem JSON nguyên vẹn vào giữa stream. Với stream hãy có event protocol cho `event:app-error`, connection close, retry/backoff, resume ID và cancellation. Bộ lọc trên `Mono<ServerResponse>` không đồng nghĩa filter toàn bộ body publisher.

## 10. Request ID và không làm mất body response

Một helper dễ dùng:

```java
static String requestId(ServerRequest request) {
    return (String) request.attributes().computeIfAbsent(
            "demoRequestId",
            ignored -> UUID.randomUUID().toString());
}
```

Trong response factory, dùng một giá trị đã đọc:

```java
String id = requestId(request);
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .header("X-Request-Id", id)
        .bodyValue(value);
```

Do đó success và error đều ghi request ID ở thời điểm dựng response; không cần cố copy body vào response mới trong `after`.

**Lưu ý:** Nếu URL không match router, local requestId helper không được gọi, vì vậy global 404 từ Boot có thể thiếu header. Muốn trace ID mọi request kể cả authentication/rejected/no-route, tạo ID tại global `WebFilter` hoặc observability middleware thống nhất. Request ID không thay bearer token hoặc authorization.

## 11. Ứng dụng hoàn chỉnh: Spring Boot 3.5 và Java 17

API demo có:
- `GET /api/items` trả 200 list JSON;
- `GET /api/items/{id}` trả 200 hoặc 404;
- `POST /api/items` đọc JSON body và trả 201 + Location;
- `DELETE /api/items/{id}` trả 204 hoặc 404;
- `GET /api/items/boom` cố ý tạo lỗi 500, chỉ dùng để test;
- `before` cấp request ID;
- `filter` từ chối yêu cầu có `X-Demo-Block: yes` để minh họa short-circuit;
- `onError` map domain errors thành thống nhất `ApiProblem`;
- `after` log status object.

### 11.1. Spring Initializr/Maven

Tạo Maven project Java 17+, Spring Boot **3.5.x**, dependency **Spring Reactive Web** qua [Spring Initializr](https://start.spring.io/). `pom.xml` của project có fragment:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
</dependencies>
```

Spring Boot parent/BOM do Initializr tạo quản lý Reactor, Netty, Jackson và Spring Framework versions. Không thêm `spring-boot-starter-web` vào demo này, vì Boot 3.x thường ưu tiên Servlet MVC nếu có cả MVC và WebFlux starters.

Cấu trúc:

```text
src/main/java/com/example/demo/DemoApplication.java
src/test/java/com/example/demo/RouterErrorTest.java
```

### 11.2. Java source độc lập

Đặt tất cả nội dung sau vào `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    RouterFunction<ServerResponse> routes(ItemHandler handler) {
        return RouterFunctions.route()
                // Route cụ thể đặt trước /{id}.
                .GET("/api/items/boom",
                        req -> Mono.error(
                                new IllegalStateException("internal demo")))
                .GET("/api/items", handler::list)
                .GET("/api/items/{id}", handler::get)
                .POST("/api/items", handler::create)
                .DELETE("/api/items/{id}", handler::delete)

                .before(req -> {
                    ApiHttp.requestId(req);
                    return req;
                })

                // Kiểm tra quyền thực phải dùng Spring Security.
                .filter((req, next) -> {
                    if ("yes".equalsIgnoreCase(
                            req.headers().firstHeader("X-Demo-Block"))) {
                        return ApiHttp.problem(
                                req, HttpStatus.SERVICE_UNAVAILABLE,
                                "DEMO_BLOCKED", "Demo request was blocked");
                    }
                    return next.handle(req);
                })

                .onError(BadInputException.class,
                        (ex, req) -> ApiHttp.problem(
                                req, HttpStatus.BAD_REQUEST,
                                "INVALID_INPUT", ex.getMessage()))
                .onError(ItemMissingException.class,
                        (ex, req) -> ApiHttp.problem(
                                req, HttpStatus.NOT_FOUND,
                                "ITEM_NOT_FOUND", "Item not found"))
                .onError(IllegalStateException.class,
                        (ex, req) -> ApiHttp.problem(
                                req, HttpStatus.INTERNAL_SERVER_ERROR,
                                "INTERNAL_ERROR", "Unexpected server error"))

                .after((req, response) -> {
                    System.out.printf("route=%s status=%d%n",
                            req.path(), response.statusCode().value());
                    return response;
                })
                .build();
    }
}

record Item(long id, String name) {
}

record CreateItem(String name) {
}

record ApiProblem(
        String type,
        String title,
        int status,
        String detail,
        String instance,
        String code,
        String requestId) {
}

class BadInputException extends RuntimeException {
    BadInputException(String message) {
        super(message);
    }
}

class ItemMissingException extends RuntimeException {
}

final class ApiHttp {

    private ApiHttp() {
    }

    static String requestId(ServerRequest req) {
        return (String) req.attributes().computeIfAbsent(
                "demoRequestId",
                key -> UUID.randomUUID().toString());
    }

    static Mono<ServerResponse> ok(ServerRequest req, Object value) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", requestId(req))
                .bodyValue(value);
    }

    static Mono<ServerResponse> created(ServerRequest req, Item value) {
        return ServerResponse.created(
                        URI.create("/api/items/" + value.id()))
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", requestId(req))
                .bodyValue(value);
    }

    static Mono<ServerResponse> noContent(ServerRequest req) {
        return ServerResponse.noContent()
                .header("X-Request-Id", requestId(req))
                .build();
    }

    static Mono<ServerResponse> problem(
            ServerRequest req, HttpStatus status,
            String code, String safeDetail) {

        String id = requestId(req);
        ApiProblem body = new ApiProblem(
                "about:blank",
                status.getReasonPhrase(),
                status.value(),
                safeDetail,
                req.path(),
                code,
                id);

        return ServerResponse.status(status)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .header("X-Request-Id", id)
                .bodyValue(body);
    }
}

@Component
class ItemHandler {

    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, Item> items =
            new ConcurrentHashMap<>();

    Mono<ServerResponse> list(ServerRequest req) {
        int limit = parseLimit(req.queryParam("limit").orElse("20"));

        List<Item> result = items.values().stream()
                .sorted(Comparator.comparingLong(Item::id))
                .limit(limit)
                .toList();

        return ApiHttp.ok(req, result);
    }

    Mono<ServerResponse> get(ServerRequest req) {
        long id = parseId(req.pathVariable("id"));

        return Mono.defer(() -> Mono.justOrEmpty(items.get(id)))
                .switchIfEmpty(Mono.error(new ItemMissingException()))
                .flatMap(item -> ApiHttp.ok(req, item));
    }

    Mono<ServerResponse> create(ServerRequest req) {
        return req.bodyToMono(CreateItem.class)
                .switchIfEmpty(Mono.error(
                        new BadInputException("JSON body required")))
                .flatMap(input -> {
                    if (input.name() == null
                            || input.name().isBlank()
                            || input.name().length() > 80) {
                        return Mono.error(new BadInputException(
                                "Name must contain 1 to 80 characters"));
                    }

                    return Mono.fromSupplier(() -> {
                        long id = nextId.incrementAndGet();
                        Item created =
                                new Item(id, input.name().trim());
                        items.put(id, created);
                        return created;
                    });
                })
                .flatMap(item -> ApiHttp.created(req, item));
    }

    Mono<ServerResponse> delete(ServerRequest req) {
        long id = parseId(req.pathVariable("id"));

        return Mono.fromSupplier(() -> items.remove(id) != null)
                .flatMap(deleted -> deleted
                        ? ApiHttp.noContent(req)
                        : Mono.error(new ItemMissingException()));
    }

    private static long parseId(String raw) {
        try {
            long id = Long.parseLong(raw);
            if (id < 1) {
                throw new BadInputException("ID must be positive");
            }
            return id;
        } catch (NumberFormatException ex) {
            throw new BadInputException("ID must be numeric");
        }
    }

    private static int parseLimit(String raw) {
        try {
            int value = Integer.parseInt(raw);
            if (value < 1 || value > 100) {
                throw new BadInputException("Limit must be 1 to 100");
            }
            return value;
        } catch (NumberFormatException ex) {
            throw new BadInputException("Limit must be numeric");
        }
    }
}
```

### 11.3. Giải thích tính runnable và giới hạn

- Java 17 hỗ trợ record. File có một public class `DemoApplication`; các class/record khác cùng package là package-private.
- `@SpringBootApplication` scan `@Component ItemHandler` và bean `RouterFunction<ServerResponse>`.
- Tất cả imports của functional endpoints nằm trong `web.reactive.function.server`; WebMvc.fn sẽ không có cùng reactive method return signatures.
- `ApiHttp` tạo header và error body thống nhất; 204 dùng `noContent().build()` không có body.
- `before` cấp ID; `filter` có thể short-circuit; `onError` map typed errors; `after` chỉ log response object.
- `Mono.defer`/`Mono.fromSupplier` giữ operations lazy; nhưng không biến một blocking JDBC call thành non-blocking I/O. Store demo chỉ là các thao tác in-memory rất ngắn.
- Request body dùng Jackson codec từ WebFlux starter; manual validation kiểm tra field `name`.
- Demo không có authentication, authorization, CORS, CSRF, database durability, transactions, rate limiting; **không triển khai công khai**.
- `GET /api/items/boom` là endpoint mô phỏng lỗi server cần loại bỏ khi chuyển production.
- `X-Demo-Block` là test switch của client, không phải cơ chế security/maintenance production.

### 11.4. Chạy project

```bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell / CMD
mvnw.cmd spring-boot:run
```

Nếu không đặt `server.port`, server thường chạy trên `http://localhost:8080`.

### 11.5. GET danh sách thành công

```bash
curl -i 'http://localhost:8080/api/items?limit=10'
```

Khi store rỗng:
- HTTP 200;
- `Content-Type: application/json`;
- `X-Request-Id` có giá trị UUID của request;
- body `[]`.

### 11.6. POST tạo item

```bash
curl -i -X POST 'http://localhost:8080/api/items' \
  -H 'Content-Type: application/json' \
  --data-binary '{"name":"Spring WebFlux"}'
```

Nếu project mới khởi động, POST đầu tiên thường tạo ID 1:

```http
HTTP/1.1 201 Created
Location: /api/items/1
Content-Type: application/json
X-Request-Id: ...

{"id":1,"name":"Spring WebFlux"}
```

Header request ID và thứ tự header/JSON whitespace không cố định. Khi chạy nhiều lần, ID tăng; không hardcode ID trong tests.

### 11.7. GET item không tồn tại

```bash
curl -i 'http://localhost:8080/api/items/999999'
```

Dự kiến 404, `Content-Type: application/problem+json` và JSON gồm:

```json
{
  "type":"about:blank",
  "title":"Not Found",
  "status":404,
  "detail":"Item not found",
  "instance":"/api/items/999999",
  "code":"ITEM_NOT_FOUND",
  "requestId":"..."
}
```

`X-Request-Id` ở header và trường `requestId` trong cùng response phải bằng nhau.

### 11.8. Sai ID/limit

```bash
curl -i 'http://localhost:8080/api/items/abc'
curl -i 'http://localhost:8080/api/items?limit=0'
curl -i 'http://localhost:8080/api/items?limit=abc'
```

Dự kiến HTTP 400 Problem Details với `code=INVALID_INPUT`; detail được tạo an toàn bởi domain exceptions: “ID must be numeric”, “Limit must be 1 to 100”, “Limit must be numeric”.

### 11.9. Chặn bởi filter

```bash
curl -i 'http://localhost:8080/api/items' \
  -H 'X-Demo-Block: yes'
```

Dự kiến HTTP 503, Problem body với `code=DEMO_BLOCKED` và `X-Request-Id`. Filter trả response sớm, **không gọi `next.handle(req)`**, nên handler `list` không được thực thi.

### 11.10. Lỗi 500 an toàn

```bash
curl -i 'http://localhost:8080/api/items/boom'
```

Dự kiến HTTP 500 với `code=INTERNAL_ERROR`, `detail=Unexpected server error`. Error body không được xuất hiện raw message `internal demo`. Trong hệ thực, log nội bộ đã redacted cần giữ stacktrace/diagnostic metadata và requestId.

### 11.11. Body sai và decoder errors

```bash
curl -i -X POST 'http://localhost:8080/api/items' \
  -H 'Content-Type: application/json' \
  --data-binary '{"name":" "}'
```

Dự kiến 400 với `code=INVALID_INPUT`. Nhưng với JSON malformed như `{"name":` hoặc `Content-Type: text/plain`, lỗi có thể đến từ HTTP decoder/route matching; **không** khẳng định local onError luôn tạo cùng schema nếu chưa có global error handling.

### 11.12. DELETE và 204

```bash
curl -i -X DELETE 'http://localhost:8080/api/items/1'
```

Nếu item ID=1 tồn tại: status 204, không có body, header `X-Request-Id`. Lần tiếp theo: HTTP 404 Problem Details. Với test tự động hãy lấy ID từ Location của POST, không dựa vào store vừa khởi động.

### 11.13. PowerShell

```powershell
curl.exe -i "http://localhost:8080/api/items"
curl.exe -i "http://localhost:8080/api/items?limit=0"
curl.exe -i "http://localhost:8080/api/items/boom"
curl.exe -i -H "X-Demo-Block: yes" "http://localhost:8080/api/items"
```

Với POST JSON trên PowerShell, tạo file `request.json` UTF-8 chứa `{"name":"Spring WebFlux"}` rồi dùng `curl.exe -i -X POST ... -H "Content-Type: application/json" --data-binary "@request.json"`; cách này tránh khác biệt escape quotes giữa các shell.

## 12. Kiểm thử WebTestClient

Với Boot 3.5, thêm test dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

### 12.1. File test hoàn chỉnh

Tạo `src/test/java/com/example/demo/RouterErrorTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class RouterErrorTest {

    @Autowired
    WebTestClient client;

    @Test
    void listHasRequestIdAndJsonBody() {
        client.get().uri("/api/items")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().exists("X-Request-Id")
                .expectBody()
                .json("[]");
    }

    @Test
    void invalidLimitHasStandardProblemBody() {
        client.get().uri("/api/items?limit=0")
                .exchange()
                .expectStatus().isBadRequest()
                .expectHeader().contentType(
                        MediaType.APPLICATION_PROBLEM_JSON)
                .expectHeader().exists("X-Request-Id")
                .expectBody()
                .jsonPath("$.status").isEqualTo(400)
                .jsonPath("$.code").isEqualTo("INVALID_INPUT");
    }

    @Test
    void missingItemReturnsProblem404() {
        client.get().uri("/api/items/999999")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.status").isEqualTo(404)
                .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");
    }

    @Test
    void filterCanShortCircuitWith503() {
        client.get().uri("/api/items")
                .header("X-Demo-Block", "yes")
                .exchange()
                .expectStatus().isEqualTo(503)
                .expectBody()
                .jsonPath("$.code").isEqualTo("DEMO_BLOCKED");
    }

    @Test
    void internalErrorUsesSafeMessage() {
        client.get().uri("/api/items/boom")
                .exchange()
                .expectStatus().is5xxServerError()
                .expectBody()
                .jsonPath("$.status").isEqualTo(500)
                .jsonPath("$.code").isEqualTo("INTERNAL_ERROR")
                .jsonPath("$.detail")
                .isEqualTo("Unexpected server error");
    }

    @Test
    void postCreatesResourceWithLocation() {
        client.post().uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"name\":\"demo item\"}")
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectHeader().exists("X-Request-Id")
                .expectBody()
                .jsonPath("$.name").isEqualTo("demo item");
    }

    @Test
    void blankNameIsRejected() {
        client.post().uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"name\":\"  \"}")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_INPUT");
    }
}
```

Test này chỉ xác nhận các đường đi **match router** và logic được khai báo. Chưa bảo đảm cùng JSON format cho `/not-a-route`, preflight CORS, Spring Security 401/403, unsupported media type hay malformed JSON nếu các lỗi đến từ tầng khác. Cần integration tests bổ sung khi áp dụng global error policy.

### 12.2. So header và JSON requestId

Có thể lấy `EntityExchangeResult<byte[]> result = ...expectBody().returnResult()` rồi dùng Jackson `ObjectMapper` parse `requestId`; assert giá trị bằng `result.getResponseHeaders().getFirst("X-Request-Id")`. Đây là một **test extension** cần viết thêm, không phải method đã có trong file ở trên. Không hardcode UUID hoặc lấy ID request trước.

### 12.3. Router-only vs HTTP integration test

`WebTestClient.bindToRouterFunction(router).build()` cho phép test routing/filter nhanh mà không cần mở socket. Tuy vậy không chứng minh Netty/proxy/security chain/global error behavior. Với API public cần cả HTTP integration tests của Boot và end-to-end tests qua gateway/ingress.

### 12.4. Chạy

```bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
```

Các ví dụ ở đây được biên soạn theo Spring Boot 3.5.x/Spring Framework 6.2.x; thao tác xây README không tương đương việc thực sự khởi động server và chạy test trong một Maven project.

## 13. Production: thiết kế error boundaries theo lớp

Một kiến trúc thực tế có thể tổ chức:

```text
Incoming HTTP request
       |
Global WebFilter: request ID + observation + CORS
       |
SecurityWebFilterChain: 401/403
       |
Routing
  |          \
  |           \ no route -> global error 404
  v
Router-local filters + typed domain onError
       |
Reactive handlers and services
       |
Codec/body write
       |
Client/network
       |
Late write error -> logs/cancel/stream event protocol
```

### 13.1. Một contract, nhiều producers

Có thể dùng chung một error model/problem factory ở tầng các producers:
- Router onError cho domain failures;
- Global ErrorWebExceptionHandler cho fallback/unmatched routes/codec;
- Security exception entry point và denied handler cho 401/403;
- Gateway/proxy contract nếu infrastructure tự tạo lỗi 413/429/502/503.

**Đừng tạo circular dependency:** global handler có thể không có `ServerRequest` từ functional API vì không có match; khi đó factory nên nhận một context-neutral request path/request ID/status thay vì ép mọi lỗi đi qua RouterFunction.

### 13.2. Thứ tự và double write

Nếu tự đăng ký global ErrorWebExceptionHandler, phải xác định priority so với Boot mặc định, kiểm tra response `isCommitted()` và chỉ viết một lần. Khi filter đồng thời ghi error rồi trả Mono.error, một handler khác cố ghi tiếp có thể làm response hỏng. Một khi đã tạo error response thành công, terminal path nên kết thúc có kiểm soát.

### 13.3. Problem title/detail i18n

Mã lỗi máy đọc nên ổn định; localized client message nên được phân tách hoặc được quốc tế hóa bằng policy. Không dùng raw detail làm identifier. Cần giới hạn độ dài/path/parameter echoes trong error body để tránh log injection, reflected content và gửi PII.

### 13.4. Bảo mật và backpressure

- Input DTO phải validate allowed fields, string lengths, batch size, request body limits.
- WebFlux codec buffering có thể cấu hình qua `spring.codec.max-in-memory-size` trong Boot 3.5 cho một số tình huống; nó **không phải** giới hạn tất cả request streaming.
- Không `block()` hoặc gọi JDBC blocking trực tiếp trên event loop.
- Các nguồn `Flux` lớn cần limits/backpressure, tránh `collectList()` vô hạn.
- Body đã stream một phần thì phải báo lỗi bằng application-level semantics hoặc đóng kết nối.
- Không dùng custom error filter để thay authorization checks.

## 14. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Router filter không chạy với URL lạ | Không có route match | Global WebFilter/ErrorWebExceptionHandler |
| 401/403 không có cùng Problem schema | Security chặn trước router | Custom reactive entry point/denied handler |
| `onError` không compile sau khi copy MVC code | WebMvc.fn trả response đồng bộ | WebFlux.fn trả Mono<ServerResponse> |
| Filter chặn request nhưng handler vẫn chạy | Vẫn gọi `next.handle(req)` | Return early từ filter |
| Filter không bảo vệ router module khác | Scope chỉ một RouterFunction | Ghép đúng router hoặc WebFilter toàn cục |
| `after` log trước khi SSE kết thúc | Chỉ thấy response object | HTTP network instrumentation |
| Sửa headers làm mất body | Tạo response mới bằng from(...).build() | Header trong response factory |
| 400 thay cho lỗi DB 500 | Catch quá rộng hoặc status mapping sai | Typed exceptions, generic 500 fallback |
| Trả stacktrace trong detail | Copy raw error message | Client-safe details và internal logs |
| `Mono.empty()` không ra 404 | Không map absence | switchIfEmpty typed missing exception |
| JSON malformed không theo schema | Codec error khác domain error | Global codec/error policy |
| Content-Type sai ra 404 | Predicate không match route | Test 404/415/406 contract |
| Không có X-Request-Id trên global 404 | Request ID chỉ sinh local before | Global trace WebFilter |
| Body 204 không rỗng | Trả thêm response DTO | noContent().build() |
| X-Demo-Block bị lạm dụng | Test header do client tự điều khiển | Gỡ production |
| HTTP error sau SSE event đầu không thành JSON | Response committed | Stream error/cancel/reconnect |
| Router `subscribe()` thủ công | Work tách HTTP lifecycle | Return Mono/Flux |
| MDC/tenant trace rơi giữa threads | Reactive context khác ThreadLocal | Context propagation |
| Tests phụ thuộc UUID/ID cứng | Dữ liệu sinh mỗi request | Assert pattern/Location thay số cứng |

## 15. Checklist hoàn thiện

1. [ ] Đúng stack WebFlux, imports thuộc `web.reactive.function.server`.
2. [ ] Router functions theo thứ tự, static path trước variable path.
3. [ ] Scope nested/builder filter được kiểm tra khi thêm endpoints.
4. [ ] `before` xử lý metadata nhanh, không consume body/bật blocking I/O.
5. [ ] `filter` return Mono và short-circuit không gọi next khi cần.
6. [ ] `after` chỉ log response metadata, không tưởng là network complete.
7. [ ] `onError` xử lý typed domain errors; unknown 500 không leak.
8. [ ] Mỗi status/body/header đúng semantics 200/201/204/400/404/500/503.
9. [ ] Error body `application/problem+json` hợp contract RFC9457; `code` ổn định.
10. [ ] Request ID trong body/header trùng nhau và không chứa thông tin nhạy cảm.
11. [ ] Global error policy bao unknown route, codec và security failures.
12. [ ] SecurityWebFilterChain, CORS/CSRF, tenant ACL/rate-limit rõ.
13. [ ] Không có Mono.block/Thread.sleep/JDBC blocking event loop.
14. [ ] Streaming errors sau commit có protocol, cleanup/cancel và retry policy.
15. [ ] WebTestClient test success, bad input, missing item, 500, filter 503, header correlation.
16. [ ] Tests riêng cho global 404/401/403/415, malformed JSON và proxy CORS.
17. [ ] Gỡ test-only `/api/items/boom` và `X-Demo-Block` khi production.
18. [ ] Khi nâng Spring Framework 7/Boot 4, xác minh starter/test imports mới trước khi reuse code.

## 16. Câu hỏi ôn tập

**1. WebFlux.fn filter khác WebFilter ở đâu?** Router filter chỉ áp vào functional routes đã matched trong scope; WebFilter nằm ở HTTP handler chain toàn ứng dụng.

**2. before trả kiểu gì?** `ServerRequest`; không trả `Mono<ServerRequest>` trong Java builder API 6.2.

**3. filter trả kiểu gì?** `Mono<ServerResponse>`, có thể gọi `next.handle(req)` hoặc trả response sớm.

**4. after có nghĩa response body đã gửi hết không?** Không; nó xử lý `ServerResponse` object, còn body publisher có thể stream sau.

**5. onError trong WebFlux.fn trả kiểu gì?** Response provider trả `Mono<ServerResponse>`, khác WebMvc.fn đồng bộ.

**6. Có nên map mọi Exception thành 400 không?** Không; cần phân loại lỗi client/domain/server/security và giữ status tương ứng.

**7. Vì sao một URL không match không nhận local request ID?** Vì local before/filter chưa chạy; cấp request ID ở global WebFilter khi cần bao mọi route.

**8. HTTP 204 có body JSON lỗi thành công không?** Không; response 204 không có body.

**9. Lỗi sau khi một SSE event đã gửi có đổi HTTP status thành 500 không?** Không bảo đảm vì headers đã committed; dùng stream protocol/connection close.

**10. `X-Request-Id` có phải authentication không?** Không. Nó phục vụ correlation và hỗ trợ gỡ lỗi.

## 17. Tài liệu chính thức

- [Spring Framework 6.2 — Functional WebFlux Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): before/after/filter, nested scopes, RouterFunction/HandlerFunction.
- [Spring Framework 6.2 — RouterFunctions.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.Builder.html): methods `filter`/`onError`/`before`/`after`.
- [Spring Framework 6.2 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html): mutable attributes, headers, bodyToMono.
- [Spring Framework 6.2 — ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): status, headers, bodyValue, body.
- [Spring Framework 6.2 — Reactive Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html): ProblemDetail/RFC9457, ErrorResponse, annotation-handling boundary.
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): starter, error configuration, routing.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): reactive SecurityWebFilterChain, 401/403.
- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): CorsWebFilter.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): Mono error signaling, doFinally, cancellation.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): standardized error JSON body and extension fields.

**Kết luận:** `before` bổ sung request metadata, `filter` bao/short-circuit handler, `after` quan sát response object, và `onError` chuyển domain exceptions thành `Mono<ServerResponse>`. Hãy dùng một response factory để có HTTP status, headers và Problem JSON nhất quán; đồng thời phải hiểu local router filters **không thay** global error/security handling. Error sau khi body đã được gửi một phần còn cần chiến lược streaming riêng.
