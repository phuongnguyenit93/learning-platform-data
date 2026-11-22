# DispatcherHandler, HandlerMapping, HandlerAdapter và HandlerResultHandler trong Spring WebFlux

## 1. Mục tiêu bài học

Spring WebFlux dùng kiến trúc **front controller**: HTTP request đi qua hạ tầng reactive rồi được chuyển tới một bộ điều phối trung tâm là `DispatcherHandler`. Dispatcher không cần tự hiểu mọi kiểu controller/route hoặc cách viết JSON/HTML. Nó phối hợp ba nhóm SPI: `HandlerMapping` **tìm handler**, `HandlerAdapter` **gọi handler**, `HandlerResultHandler` **xử lý kết quả để tạo response**.

Đây là bài nền tảng trong mục **Hạ tầng WebFlux**, dành cho **Java 17+, Spring Framework 6.x và Spring Boot 3.x**. Mục tiêu cụ thể:

- Vẽ chính xác pipeline từ HTTP server/`HttpHandler` qua `WebFilter`, `DispatcherHandler` tới response.
- Phân biệt `WebHandler`, `HandlerMapping`, `HandlerAdapter`, `HandlerResult` và `HandlerResultHandler`; hiểu chữ “Handler” trong mỗi tên có nghĩa gì.
- Giải thích thuật toán *mapping đầu tiên khớp → adapter hỗ trợ → result handler hỗ trợ* và thứ tự ưu tiên.
- Nhận biết annotated controllers (`@RestController`, `@GetMapping`, `ResponseEntity`) so với functional routes (`RouterFunction`, `HandlerFunction`, `ServerResponse`).
- Biết tại sao body JSON, status, header và view rendering đi qua những result handlers khác nhau.
- Hiểu `Mono<Void>` hoàn thành HTTP response, nguồn `Mono/Flux` do ai subscribe, xử lý lỗi trước/sau khi response commit.
- Tạo ứng dụng Boot WebFlux nhỏ chạy cả hai mô hình route, quan sát `WebFilter`, in danh sách SPI beans, thử `curl` và `WebTestClient`.
- Tránh tùy tiện ghi đè SPI mặc định, gắn `@Order` sai, block event loop, hay hiểu nhầm `DispatcherHandler` với `DispatcherServlet` của Spring MVC.

**Phạm vi:** đây là **WebFlux reactive stack**, không phải Servlet MVC. Các lớp có tên tương tự ở Spring MVC nhưng nằm ở package khác và có kiểu trả về khác; không copy một interceptor/adapter của MVC sang WebFlux.

## 2. Sơ đồ tổng thể một HTTP request

```text
Client / HTTP request
         |
         v
Reactor Netty (hoặc reactive server adapter phù hợp)
         |
         v
HttpHandler / HttpWebHandlerAdapter
         |
         v
WebExceptionHandler chain / WebFilter chain
         |
         v
DispatcherHandler             (WebHandler trung tâm, bean "webHandler")
         |
         +--> HandlerMapping #1 --no match--+
         +--> HandlerMapping #2 --match----> handler object
         |                                    |
         |                                    v
         +--------------------------> HandlerAdapter hỗ trợ handler
                                              |
                                              v
                                         Mono<HandlerResult>
                                              |
                                              v
                                     HandlerResultHandler hỗ trợ
                                              |
                               +--------------+---------------+
                               |                              |
                         JSON / HTTP body                HTML view / khác
                               |                              |
                               +--------------+---------------+
                                              |
                                              v
                                       Mono<Void> hoàn tất
                                              |
                                              v
                                         HTTP response
```

Sơ đồ là mô hình logic, **không phải một thread/transaction riêng tại mỗi mũi tên**. Tất cả các đoạn có thể trả về một `Mono`; thực thi thật bắt đầu khi hạ tầng HTTP đăng ký vào chuỗi reactive. Bộ ghi response có thể phát nhiều `DataBuffer`/events, gặp backpressure hoặc cancellation khi client ngắt kết nối.

### Vai trò theo một câu

| Thành phần | Một câu giải thích |
| --- | --- |
| `DispatcherHandler` | Phối hợp pipeline chọn handler, gọi handler, chọn cách ghi result |
| `HandlerMapping` | “Request này dành cho handler object nào?” |
| `HandlerAdapter` | “Làm sao gọi object handler thuộc loại này?” |
| `HandlerResult` | Gói giá trị trả về cùng thông tin cần thiết để xử lý result |
| `HandlerResultHandler` | “Kết quả này phải được viết thành HTTP response như thế nào?” |

**Hai lần “handler” khác nhau:** *HandlerAdapter* gọi **request handler** đã tìm được; *HandlerResultHandler* xử lý **giá trị trả về** của việc gọi đó. Không thể thay nhóm này bằng nhóm kia.

## 3. HTTP server, HttpHandler và WebHandler nằm ở đâu?

WebFlux tách abstraction của server transport khỏi web application:

- `org.springframework.http.server.reactive.HttpHandler` là hợp đồng cấp HTTP server, xử lý `ServerHttpRequest` và `ServerHttpResponse`, trả về `Mono<Void>`.
- `org.springframework.web.server.WebHandler` là hợp đồng cấp web application, xử lý `ServerWebExchange`, trả về `Mono<Void>`.
- `ServerWebExchange` gói request/response cộng attributes, session, principal, locale, form/multipart access và trạng thái xử lý.
- `HttpWebHandlerAdapter` là một trong các lớp liên kết HTTP server adapter và `WebHandler` pipeline.
- `WebHttpHandlerBuilder.applicationContext(...)` có thể khám phá `WebFilter`, `WebExceptionHandler` và `WebHandler` tên `webHandler` để dựng chain.
- `DispatcherHandler` là một implementation trung tâm của `WebHandler`; Spring WebFlux configuration/Boot đăng ký nó thông thường.

Ví dụ chữ ký ở mức khái niệm:

```java
// Các API có sẵn trong Spring, KHÔNG tự tạo lại.
Mono<Void> HttpHandler.handle(
    ServerHttpRequest request,
    ServerHttpResponse response);

Mono<Void> WebHandler.handle(ServerWebExchange exchange);
```

Đây là **chữ ký minh họa**, không phải source Java hợp lệ đặt nguyên vào project. Các interfaces thực tế tồn tại trong Spring libraries.

**Điểm quan trọng:** `WebFilter` thường chạy **bao quanh** dispatcher và có thể can thiệp cả route annotation lẫn functional. Một functional `HandlerFilterFunction` lại bao quanh những `HandlerFunction` của router cụ thể; phạm vi khác nhau.

## 4. DispatcherHandler: front controller reactive

`org.springframework.web.reactive.DispatcherHandler` giữ thuật toán chung cho request routing và response processing. Nó khám phá SPI beans từ `ApplicationContext`:

1. Danh sách `HandlerMapping`.
2. Danh sách `HandlerAdapter`.
3. Danh sách `HandlerResultHandler`.

Các bean có thứ tự (`Ordered` hoặc `@Order`) có thể được ưu tiên theo cấu hình. `DispatcherHandler` là một Spring bean; trong cấu hình tiêu chuẩn nó có tên `webHandler` để `WebHttpHandlerBuilder` nhận diện.

### Thuật toán giản lược

```text
handle(exchange):
  handler = first HandlerMapping that produces a handler
  if no handler:
      signal response status 404 / error pathway as configured
  else:
      adapter = first HandlerAdapter where supports(handler) is true
      result = adapter.handle(exchange, handler)
      if result emitted:
          resultHandler = first handler where supports(result) is true
          resultHandler.handleResult(exchange, result) -> Mono<Void>
      if adapter completes empty:
          response may already be fully handled
  finish on completion/error/cancel
```

Đây là **pseudocode**, không phải Java implementation nội bộ từng dòng. Trong thực tế còn có CORS preflight, metadata của exchange, dispatch exception handling, special no-handler behavior, WebExceptionHandlers và reactive operator composition.

### Tại sao chỉ chọn một HandlerMapping?

Mappings được duyệt theo thứ tự ưu tiên; ứng viên đầu tiên phát ra handler quyết định đường xử lý. Một mapping đứng trước và *phát lỗi* vì điều kiện HTTP method/media type không khớp có thể chấm dứt lookup; không được suy “nếu mapping trước có vấn đề thì luôn thử mapping sau”. Điều này khác với ý tưởng thử tất cả route tới khi trả được 200.

**Không dùng @Order để giải quyết hai endpoints trùng nhau một cách mù quáng.** Chọn path/predicate không chồng lấn, test các trường hợp GET/POST/Accept/Content-Type và audit thứ tự thực tế trong application context.

## 5. HandlerMapping: từ request tới handler object

Hợp đồng reactive mapping có thể nhìn như:

```java
Mono<Object> getHandler(ServerWebExchange exchange);
```

Đây là chữ ký của interface Spring `org.springframework.web.reactive.HandlerMapping` (chỉ trích để học). `Mono.empty()` thường nghĩa là mapping này không tìm thấy handler phù hợp; không nhất thiết phải tạo HTTP response. Error signal có thể được phát khi request không đáp ứng điều kiện, tùy implementation.

Những implementations quan trọng:

| Mapping | Đặc trưng | Handler object được chọn |
| --- | --- | --- |
| `RequestMappingHandlerMapping` | Dò `@RequestMapping`, `@GetMapping`, `@PostMapping` của annotated controllers | `HandlerMethod` biểu diễn method Java đã được ánh xạ |
| `RouterFunctionMapping` | Dò beans `RouterFunction<?>`, kết hợp các route functional | `HandlerFunction<?>` |
| `SimpleUrlHandlerMapping` | Ánh xạ URL pattern trực tiếp tới đối tượng handler đã đăng ký | Chẳng hạn một `WebHandler` |
| Resource mappings | Phục vụ tài nguyên tĩnh theo WebFlux config | Handler phù hợp resource infrastructure |

**Không đánh đồng HandlerMapping với URL string comparison đơn thuần.** Annotated mapping còn xét HTTP method, path variables, query params, headers, `consumes`, `produces`, content negotiation và các điều kiện cụ thể khác.

### 5.1. Annotated request mapping

```java
@RestController
@RequestMapping("/api")
class ExampleController {

    @GetMapping(path = "/products/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<ProductDto> one(@PathVariable String id) {
        return service.find(id);
    }
}
```

Đây là **snippet** yêu cầu `service`/`ProductDto` và imports. `RequestMappingHandlerMapping` phát hiện annotation, tạo metadata mapping cho method. Khi `GET /api/products/42` tới, handler object là một `HandlerMethod`, không phải trực tiếp `Mono<ProductDto>`.

### 5.2. Functional route mapping

```java
@Bean
RouterFunction<ServerResponse> routes() {
    return RouterFunctions.route()
        .GET("/fn/ping",
             request -> ServerResponse.ok().bodyValue("pong"))
        .build();
}
```

Đây là **snippet** trong class `@Configuration` có imports. `RouterFunctionMapping` tìm `RouterFunction` và chọn một `HandlerFunction`; functional route không cần `@RestController`. Để invocation tạo HTTP response, pipeline còn dùng `HandlerFunctionAdapter` và `ServerResponseResultHandler`.

### 5.3. HandlerMapping ordering

Một hệ thống có cả annotation và functional routes hoạt động được vì mỗi kiểu có mapping tương ứng. Nếu hai mappings khác nhau nhận **cùng một URL/method**, kết quả có thể phụ thuộc thứ tự mappings. Không khẳng định “functional luôn ưu tiên annotation” hay ngược lại trên mọi Spring version/configuration. Phương pháp an toàn: tạo paths không trùng, dùng test xác minh và chỉ can thiệp order khi thực sự có nhu cầu hạ tầng.

## 6. HandlerAdapter: gọi handler bất kể kiểu nào

Interface `org.springframework.web.reactive.HandlerAdapter` có hai operations cốt lõi:

```java
boolean supports(Object handler);

Mono<HandlerResult> handle(
        ServerWebExchange exchange, Object handler);
```

Đây là **chữ ký minh họa**, không phải class compile độc lập. `supports` quyết định adapter có hiểu handler object đó không. `handle` gọi handler và cung cấp `Mono<HandlerResult>` cho dispatcher.

Những adapters điển hình:

- `RequestMappingHandlerAdapter`: gọi `HandlerMethod` trong annotated controller; giải quyết `@PathVariable`, `@RequestParam`, `@RequestBody`, validation, return value và exception-handling metadata.
- `HandlerFunctionAdapter`: gọi functional `HandlerFunction<ServerResponse>` với `ServerRequest` thích hợp.
- `SimpleHandlerAdapter`: hỗ trợ những handler kiểu `WebHandler` đơn giản.

### Controller invocation không phải response serialization

Ví dụ annotated method:

```java
@GetMapping("/data")
Mono<MyDto> data() {
    return service.load();
}
```

`RequestMappingHandlerAdapter` gọi method và nhận giá trị trả về (ở đây là `Mono<MyDto>`) dưới dạng metadata trong `HandlerResult`; adapter **không phải luôn là thành phần cuối cùng tự gửi JSON**. `ResponseBodyResultHandler`, HTTP message writers/codecs và response layer mới chịu trách nhiệm serialization/writing.

Một adapter cũng có thể tự xử lý toàn bộ request và hoàn thành với `Mono.empty()` trong những tình huống hỗ trợ; đừng xây middleware giả định luôn có một `HandlerResult`.

## 7. HandlerResult: kết quả chưa phải bytes HTTP

`org.springframework.web.reactive.HandlerResult` gói:

- **Handler** đã tạo ra result.
- **Return value** (có thể là regular object hoặc reactive wrapper).
- **Return type metadata** như `MethodParameter`/`ResolvableType` để quyết định xử lý.
- **Model** nếu phù hợp cho view rendering.
- **Exception handling** reference tùy adapter, ví dụ `DispatchExceptionHandler` cho lỗi phát sinh muộn.

Với controller:

```java
@GetMapping("/users/{id}")
Mono<ResponseEntity<UserDto>> user(@PathVariable long id) {
    return userService.find(id)
        .map(ResponseEntity::ok);
}
```

Đây là snippet với `userService`/`UserDto`. Adapter có thể trả `HandlerResult` chứa một giá trị reactive được khai báo là `Mono<ResponseEntity<UserDto>>` và return type metadata. **Đừng nghĩ mỗi `onNext` từ Mongo/DB tạo một HandlerResult mới**: HandlerResult là kết quả của việc gọi handler, còn Publisher bên trong là nguồn values được result handler consume để viết body.

`HandlerResult` không phải `ServerResponse` của WebFlux.fn. `ServerResponse` là một loại **return value** có thể nằm trong `HandlerResult` để được `ServerResponseResultHandler` xử lý.

## 8. HandlerResultHandler: biến result thành HTTP response

Hợp đồng Spring `org.springframework.web.reactive.HandlerResultHandler`:

```java
boolean supports(HandlerResult result);

Mono<Void> handleResult(
        ServerWebExchange exchange, HandlerResult result);
```

`supports` xác nhận có thể xử lý return value + metadata, `handleResult` cập nhật status/headers, chọn body writer hay view và hoàn tất reactive operation. `Mono<Void>` đại diện cho thời điểm response-writing kết thúc, **không** phải body rỗng bắt buộc.

Spring WebFlux 6.x config cung cấp những nhóm chính:

| Result handler | Giá trị được hỗ trợ | Default order được tài liệu Spring nêu |
| --- | --- | --- |
| `ResponseEntityResultHandler` | `ResponseEntity` từ annotated controller | **0** |
| `ServerResponseResultHandler` | `ServerResponse` của functional endpoints | **0** |
| `ResponseBodyResultHandler` | `@ResponseBody` / `@RestController` ordinary body | **100** |
| `ViewResolutionResultHandler` | View name, `View`, model, `Rendering`, ... | **Integer.MAX_VALUE** |

Hai result handlers có cùng order 0 **không** đồng nghĩa tranh nhau cùng value. Mỗi handler có `supports(...)` để nhận đúng contract. Không ghi đè order nhằm ép mọi `Mono<Dto>` đi qua `ResponseEntityResultHandler`.

### 8.1. ResponseEntityResultHandler

Annotated method trả:

```java
@GetMapping("/accepted")
Mono<ResponseEntity<Message>> accepted() {
    return Mono.just(ResponseEntity.accepted()
        .header("X-Example", "yes")
        .body(new Message("queued")));
}
```

Snippet với `Message` record/imports đã có. `ResponseEntityResultHandler` xử lý metadata status **202**, header và body `Message` qua message writer. Nó không chuyển 202 thành “job đã được thực thi”; đó là semantic của ứng dụng.

### 8.2. ResponseBodyResultHandler

`@RestController` trả `Mono<Message>` hoặc `Flux<Message>` được xử lý theo `@ResponseBody` semantics. Với `application/json`, phù hợp message writer/codecs (thường Jackson) encode DTO. Với `text/event-stream`, codec streaming được dùng; không suy một Reactor element bằng một TCP packet.

### 8.3. ServerResponseResultHandler

Functional `HandlerFunction` trả `Mono<ServerResponse>`. Result handler nhận `ServerResponse` và gọi logic `writeTo(...)` của response, sử dụng message writers/handler strategies thích hợp. Không bắt annotated controller trả `ServerResponse` chỉ vì cả hai đều gọi là “response”; đó là contract riêng của WebFlux.fn.

### 8.4. ViewResolutionResultHandler

Với annotated `@Controller` trả logical view name và có view resolver engine, handler có thể tạo HTML (Thymeleaf/Freemarker tùy dependencies/config). Nếu không có view technology, không tự giả định template luôn render được. Nếu method có `@ResponseBody`, một `String` thường là **HTTP response body**, không phải tên view.

## 9. Bốn con đường trên cùng một DispatcherHandler

```text
GET /api/hello/Ana
  RequestMappingHandlerMapping -> HandlerMethod
  RequestMappingHandlerAdapter -> HandlerResult(Mono<Greeting>)
  ResponseBodyResultHandler -> 200 JSON

GET /api/status
  RequestMappingHandlerMapping -> HandlerMethod
  RequestMappingHandlerAdapter -> HandlerResult(Mono<ResponseEntity<Greeting>>)
  ResponseEntityResultHandler -> 202 JSON

GET /fn/hello/Ana
  RouterFunctionMapping -> HandlerFunction
  HandlerFunctionAdapter -> HandlerResult(Mono<ServerResponse>)
  ServerResponseResultHandler -> 200 JSON

GET /pages/home   (khi có view template config)
  RequestMappingHandlerMapping -> HandlerMethod
  RequestMappingHandlerAdapter -> HandlerResult("home")
  ViewResolutionResultHandler -> rendered HTML
```

Sơ đồ diễn tả các luồng **theo contract chuẩn**, không phải trace được thu từ app thật. Những phần như annotation metadata, content negotiation và response writing có thêm bước nội bộ. Mục đích là thấy Dispatcher **không đổi thuật toán** dù kết quả do các result handlers khác nhau xử lý.

## 10. Message readers, writers và content negotiation

`HandlerAdapter` cần đọc/bind parameters/body; `HandlerResultHandler` thường phải chọn cách ghi response. Với WebFlux, codec infrastructure gồm `HttpMessageReader`, `HttpMessageWriter` và `ServerCodecConfigurer`.

- `Content-Type` của request cho biết loại body client gửi. Một endpoint `consumes="application/json"` có thể bị từ chối bằng **415 Unsupported Media Type** nếu client gửi loại không hỗ trợ.
- `Accept` cho biết loại representation client chấp nhận. Một endpoint chỉ trả JSON có thể bị từ chối bằng **406 Not Acceptable** khi không có representation phù hợp.
- `produces` trong annotation/request predicate là điều kiện route; message writer cũng phải hỗ trợ encode kiểu dữ liệu/định dạng đó.
- Đọc request body `Mono<Dto>` cần decoder phù hợp; malformed JSON có thể tạo **400 Bad Request**.
- `@ResponseBody` + String không tự thành view; `@Controller` + String không mặc định là raw body.
- Server-Sent Events và NDJSON có streaming semantics khác JSON array thông thường, cần cấu hình media type đúng.

**Không viết một HandlerResultHandler mới chỉ để thêm field vào JSON DTO.** Nếu nhu cầu là validation/serialization, xem Jackson, controller advice, `CodecCustomizer`, WebFlux config hoặc message writers trước khi tự tạo SPI.

## 11. Reactive response completion và backpressure

Mặc dù tên class giống Spring MVC, WebFlux dùng reactive types:

```text
Adapter.handle(...)          -> Mono<HandlerResult>
ResultHandler.handleResult() -> Mono<Void>
Response body Publisher      -> Mono<T> / Flux<T>
```

Điểm dễ nhầm:

- `Mono<HandlerResult>` không đảm bảo xử lý synchronous: handler có thể đọc body hoặc xử lý async để tạo result.
- `Mono<Void>` hoàn thành khi công việc ghi response tương ứng hoàn tất/được xử lý; không có nghĩa response body luôn rỗng.
- HTTP infrastructure subscribe vào Publisher được tạo từ request chain; **controller không tự gọi `subscribe()`** để làm result handler chạy.
- Một stream có thể bị **cancel** khi HTTP client ngắt; cleanup tài nguyên phải xử lý cả complete/error/cancel.
- Một result handler có thể gọi codecs và phối hợp flow control; `onNext` không nhất thiết tương ứng một lần TCP write.
- Khi response đã commit header/body, không đảm bảo chuyển một lỗi stream muộn thành JSON lỗi mới cùng status khác.

**Chỉ return Flux/Mono là chưa đủ để mọi thứ non-blocking.** Nếu controller gọi JDBC blocking trước khi return Mono hoặc dùng `block()` trên Netty event loop, có thể gây thread starvation/error. Dùng reactive drivers hoặc chuyển legacy blocking work sang bounded scheduler với quản lý capacity.

## 12. Xử lý lỗi ở các lớp khác nhau

Không phải mọi lỗi đều xảy ra ở một chỗ. Phân biệt:

| Giai đoạn | Ví dụ | Cơ chế xử lý thường gặp |
| --- | --- | --- |
| `WebFilter` trước dispatcher | Authentication/rate/error | Security filter, `WebExceptionHandler` |
| `HandlerMapping` | Không có route, method sai, mismatch predicates | Not-found/status exception hoặc mapping error theo cấu hình |
| `HandlerAdapter` khi bind | Query sai kiểu, JSON body hỏng, validation | Exception resolver của annotated controller hoặc WebExceptionHandler |
| Business logic reactive | `Mono.error(ex)` từ service | `@ExceptionHandler`/`@ControllerAdvice` khi phù hợp |
| Result handling | Không có codec, serialize lỗi, view thiếu | Exception handling trước commit nếu khả thi |
| Sau response commit | Streaming error/client disconnect | Cleanup/metrics, thường không thay status đã gửi |

Spring Framework 6.x có `DispatchExceptionHandler` để hỗ trợ chuyển một `Throwable` thành `HandlerResult` cho một số tình huống. `RequestMappingHandlerAdapter` hỗ trợ exception handling của annotated controllers; `HandlerResult` có thể mang exception handler dùng cho **deferred errors** hoặc lỗi trong result rendering.

Ở cấp web chain, `WebExceptionHandler` xử lý errors từ filters/target handler; Spring Boot còn có auto-configured error handling. **`@RestControllerAdvice` không phải bắt mọi exception trước/ngoài dispatcher** và không bảo đảm can thiệp sau khi bytes đã gửi tới client.

### Không có mapping và HTTP status

Một route không tồn tại thường nhận 404. Nhưng:

- Đường dẫn đúng mà HTTP method không hỗ trợ có thể thành **405 Method Not Allowed**.
- `consumes` mismatch có thể thành 415.
- `produces`/Accept mismatch có thể thành 406.
- Security filter có thể trả 401/403 trước mapping.
- Custom error handlers/proxy có thể thay body hoặc status.

Vì vậy không khẳng định mọi request không chạy vào controller đều là 404 hoặc mọi 404 đều do `HandlerMapping` cụ thể.

## 13. WebFilter khác HandlerMapping và ControllerAdvice thế nào?

Một `WebFilter` có contract:

```java
Mono<Void> filter(
    ServerWebExchange exchange, WebFilterChain chain);
```

Đây là chữ ký của interface Spring, không phải mã class hoàn chỉnh. Nó có thể xử lý trước/sau `chain.filter(exchange)`, thêm response header, lấy correlation ID, thiết lập context hoặc từ chối request sớm.

| Công cụ | Phạm vi | Nên dùng cho |
| --- | --- | --- |
| `WebFilter` | Bao ngoài request xử lý qua WebHandler pipeline | Authn/authz trong Spring Security, tracing, request metrics |
| `HandlerMapping` | Tìm endpoint/handler theo request | Annotation routes, functional routes, custom routing |
| `HandlerAdapter` | Gọi một kiểu handler object | Extension của programming model |
| `HandlerResultHandler` | Xử lý return values | HTTP body/result/view strategy |
| `@RestControllerAdvice` | Exception/binding response thuộc annotated controller model | Domain/validation error mapping |
| `WebExceptionHandler` | Errors xuyên WebFilter/WebHandler chain | Lỗi ngoài annotated method hoặc infrastructure |
| Functional `HandlerFilterFunction` | Bao các handler functions thuộc router | Logic chung cho một nhóm functional routes |

Một `WebFilter` có thể set header trước khi route được chọn; nó **không phải** là một HandlerMapping. Nếu WebFilter từ chối request và tự complete response, DispatcherHandler có thể không được gọi.

## 14. Config WebFlux và khả năng mở rộng SPI

Trong project bình thường, **để Spring Boot và WebFlux Config tạo SPI mặc định** là lựa chọn tốt. Các entrypoint tùy chỉnh thường là:

- `WebFluxConfigurer` (cấu hình formatters, codecs, CORS, view resolvers, resource handlers...).
- Custom `WebFilter` cho logic cắt ngang ở request chain.
- Bean `RouterFunction<ServerResponse>` hoặc annotated `@RestController` cho routes nghiệp vụ.
- Global exception handling, codecs, validation và functional filters.
- Custom implementations của `HandlerMapping`, `HandlerAdapter` hoặc `HandlerResultHandler` **chỉ khi thêm một programming model thực sự mới**.

**Đừng mặc định thêm `@EnableWebFlux` trong Spring Boot rồi kỳ vọng Boot autoconfiguration vẫn hoạt động nguyên như trước.** Khi tự chiếm quyền WebFlux configuration, một số Boot conveniences có thể thay đổi/không được áp dụng theo cách cũ; hãy đọc đúng tài liệu Boot version hiện tại. Trong ví dụ runnable ở dưới **không dùng `@EnableWebFlux`**.

Một adapter nhận mọi `Object` hoặc result handler luôn `supports(...) == true` với order rất cao có thể chiếm request/result của các thành phần chuẩn. Nếu cần custom SPI, hãy viết `supports` **chặt chẽ**, dùng order có chủ đích, kiểm tra coexistence với annotated và functional routes và test cả no-match.

## 15. Project Spring Boot 3 Java 17+ runnable

Tạo Maven project từ Spring Initializr với **Java 17+**, Spring Boot **3.x**, dependencies:

- `spring-boot-starter-webflux`.
- `spring-boot-starter-test` (scope test).
- `io.projectreactor:reactor-test` (scope test nếu starter test của bản được dùng chưa cung cấp).

**Không thêm `spring-boot-starter-web`** nếu muốn Boot tự chọn reactive WebFlux server application type khi hai starters cùng xuất hiện. Nếu có cả MVC và WebFlux, Boot thường ưu tiên MVC trừ khi application type được chọn riêng. Project này dùng WebFlux thuần.

Cấu trúc source:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  ApiController.java
  FunctionalRoutes.java
  TraceWebFilter.java
  PipelineInspector.java
src/test/java/com/example/demo/
  PipelineHttpTest.java
```

Đặt tất cả file trong package `com.example.demo`. Không cần database, security hoặc template engine. Sau khi chạy, WebFlux sẽ có cả annotated routes `/api/*` lẫn functional route `/fn/*`, tránh trùng URL để test deterministic.

### 15.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 15.2. ApiController.java

```java
package com.example.demo;

import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping(path = "/hello/{name}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Greeting> hello(@PathVariable String name) {
        return Mono.just(new Greeting("annotated", name));
    }

    @GetMapping(path = "/status",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Greeting>> status() {
        return Mono.just(ResponseEntity.status(
                HttpStatus.ACCEPTED)
            .body(new Greeting("responseEntity", "ok")));
    }

    @GetMapping(path = "/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<Greeting> events() {
        return Flux.range(1, 3)
            .map(i -> new Greeting("event", Integer.toString(i)))
            .delayElements(Duration.ofMillis(60));
    }

    @GetMapping("/missing")
    public Mono<Greeting> missing() {
        return Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "not found"));
    }

    public record Greeting(String style, String name) {}
}
```

Các endpoint:

- `/api/hello/{name}`: annotated route trả `Mono<Greeting>`; `ResponseBodyResultHandler` và JSON writer xử lý result.
- `/api/status`: annotated route trả `Mono<ResponseEntity<Greeting>>`; `ResponseEntityResultHandler` xử lý 202, body JSON.
- `/api/events`: annotated route trả `Flux<Greeting>` với `text/event-stream`; body writer phát SSE.
- `/api/missing`: phát error trước response commit; `ResponseStatusException` dẫn tới 404 theo error handling tiêu chuẩn.

Controller không gọi `subscribe()` hoặc `block()`. Các Mono/Flux synchronous/lazy/scheduled theo từng operator; framework giữ subscription và response writing lifecycle. `delayElements` không cam kết thời gian chính xác 60ms trong môi trường tải cao.

### 15.3. FunctionalRoutes.java

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class FunctionalRoutes {

    @Bean
    public RouterFunction<ServerResponse> greetingRoutes() {
        return RouterFunctions.route()
            .GET("/fn/hello/{name}", request ->
                ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(new ApiController.Greeting(
                        "functional", request.pathVariable("name"))))
            .build();
    }
}
```

Không dùng `@RestController` cho functional route. `RouterFunctionMapping` chọn `HandlerFunction`, `HandlerFunctionAdapter` gọi lambda, `ServerResponseResultHandler` ghi `ServerResponse`. Functional `ServerResponse.ok().bodyValue(...)` tạo `Mono<ServerResponse>` theo contract, controller function không tự ghi bytes bằng tay.

### 15.4. TraceWebFilter.java

```java
package com.example.demo;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(-100)
public class TraceWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        // Demo: thêm header trước khi WebFlux ghi response.
        exchange.getResponse().getHeaders()
                .add("X-Pipeline", "webflux");

        return chain.filter(exchange);
    }
}
```

Filter đơn giản áp dụng cả hai route families. Không dùng header này làm tín hiệu xác thực/bảo mật; production tracing cần correlation ID đáng tin và sanitize. Nếu security filter hoặc gateway kết thúc request trước filter này do thứ tự chain khác, header có thể không xuất hiện — đừng dùng nó như bằng chứng duy nhất route đã chạy.

### 15.5. PipelineInspector.java

Để **quan sát SPI beans được Boot/WebFlux config tạo**, dùng một `ApplicationRunner` in class names khi app khởi động:

```java
package com.example.demo;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.HandlerAdapter;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.HandlerResultHandler;

@Component
public class PipelineInspector implements ApplicationRunner {

    private final List<HandlerMapping> mappings;
    private final List<HandlerAdapter> adapters;
    private final List<HandlerResultHandler> resultHandlers;

    public PipelineInspector(
            List<HandlerMapping> mappings,
            List<HandlerAdapter> adapters,
            List<HandlerResultHandler> resultHandlers) {
        this.mappings = mappings;
        this.adapters = adapters;
        this.resultHandlers = resultHandlers;
    }

    @Override
    public void run(ApplicationArguments args) {
        mappings.forEach(x ->
            System.out.println("mapping=" +
                x.getClass().getSimpleName()));

        adapters.forEach(x ->
            System.out.println("adapter=" +
                x.getClass().getSimpleName()));

        resultHandlers.forEach(x ->
            System.out.println("result=" +
                x.getClass().getSimpleName()));
    }
}
```

Output **có thể** có các dòng:

```text
mapping=RequestMappingHandlerMapping
mapping=RouterFunctionMapping
adapter=RequestMappingHandlerAdapter
adapter=HandlerFunctionAdapter
result=ResponseEntityResultHandler
result=ServerResponseResultHandler
result=ResponseBodyResultHandler
```

Đây là **danh sách ví dụ**, không phải stdout đầy đủ, cố định về thứ tự/số bean. Version Spring, auto-config, static resources và các beans khác có thể tạo thêm dòng; danh sách phụ thuộc context. Tool này introspect SPI mặc định, **không sửa `@Order` hoặc override behavior**.

### 15.6. Chạy chương trình

Bên trong thư mục project Maven Boot có wrapper:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Server mặc định thường ở port 8080 nếu chưa đổi `server.port`. Không biên dịch từng controller bằng `javac ApiController.java` khi thiếu Spring/Reactor/Jackson classpath; ví dụ là **ứng dụng Maven**, không phải một file JDK thuần.

## 16. curl: từng đường đi qua result handler khác nhau

### Annotated route → response body

```bash
curl -i 'http://localhost:8080/api/hello/Ana'
```

Dự kiến:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Pipeline: webflux

{"style":"annotated","name":"Ana"}
```

Các headers tự động khác, casing và thứ tự có thể tùy web server. `X-Pipeline` được filter demo thêm trước dispatcher; JSON object được Jackson serialize.

### ResponseEntity → status/headers/body

```bash
curl -i 'http://localhost:8080/api/status'
```

Dự kiến HTTP **202 Accepted**, body:

```json
{"style":"responseEntity","name":"ok"}
```

Không phải response 202 tự chứng minh một background job đã được enqueue; endpoint chỉ minh họa `ResponseEntityResultHandler` đọc status từ `ResponseEntity`.

### Functional route → ServerResponse

```bash
curl -i 'http://localhost:8080/fn/hello/Ana'
```

Dự kiến HTTP **200**:

```json
{"style":"functional","name":"Ana"}
```

Đây là đường `RouterFunctionMapping → HandlerFunctionAdapter → ServerResponseResultHandler`. Cùng dispatcher, khác bộ delegates so với annotated route.

### SSE → streaming body writer

```bash
curl -N -i 'http://localhost:8080/api/events'
```

Ví dụ phần body:

```text
data:{"style":"event","name":"1"}

data:{"style":"event","name":"2"}

data:{"style":"event","name":"3"}

```

`curl -N` tắt buffering ở curl để dễ quan sát events. Định dạng body theo SSE writer, nhưng thời gian flush/packet boundaries khác nhau. Đừng khẳng định event thứ ba đến chính xác sau 180ms.

### Error status và no-match

```bash
curl -i 'http://localhost:8080/api/missing'
curl -i 'http://localhost:8080/not-found'
```

Cả hai thường trả **404**, nhưng cơ chế phát hiện khác nhau: endpoint `/api/missing` được route tới method rồi phát error; `/not-found` không có handler phù hợp. Error body có thể khác tùy Spring Boot/problem-details config; không assert một JSON chi tiết chưa cấu hình.

## 17. WebTestClient: kiểm tra luồng HTTP thực

Tệp `src/test/java/com/example/demo/PipelineHttpTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class PipelineHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void annotatedControllerProducesJson() {
        client.get().uri("/api/hello/Ana")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Pipeline", "webflux")
            .expectBody()
            .jsonPath("$.style").isEqualTo("annotated")
            .jsonPath("$.name").isEqualTo("Ana");
    }

    @Test
    void responseEntityControlsStatus() {
        client.get().uri("/api/status")
            .exchange()
            .expectStatus().isAccepted()
            .expectBody()
            .jsonPath("$.style").isEqualTo("responseEntity");
    }

    @Test
    void functionalRouteUsesServerResponse() {
        client.get().uri("/fn/hello/Ana")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Pipeline", "webflux")
            .expectBody()
            .jsonPath("$.style").isEqualTo("functional");
    }

    @Test
    void controllerErrorsAndUnknownRoutesYield404() {
        client.get().uri("/api/missing")
            .exchange().expectStatus().isNotFound();

        client.get().uri("/does-not-exist")
            .exchange().expectStatus().isNotFound();
    }

    @Test
    void streamEmitsThreeEvents() {
        Flux<ApiController.Greeting> events =
            client.get().uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(ApiController.Greeting.class)
                .getResponseBody();

        StepVerifier.create(events)
            .expectNext(new ApiController.Greeting("event", "1"))
            .expectNext(new ApiController.Greeting("event", "2"))
            .expectNext(new ApiController.Greeting("event", "3"))
            .verifyComplete();
    }
}
```

**Test caveat:** WebTestClient có các codecs do Spring Test/WebFlux cấu hình. Trong một số phiên bản/client settings, SSE JSON cần decode qua `ServerSentEvent<Greeting>` hoặc một `ParameterizedTypeReference` rõ kiểu thay vì DTO trực tiếp; điều chỉnh test nếu codec không map thẳng. Việc dùng `returnResult` và `StepVerifier` giúp xác minh **stream signals**, không nhầm với TCP chunks. Nếu bật Spring Security, cần mock identity/CSRF hoặc client credentials theo test profile; security có thể chặn trước handler.

Chạy:

```bash
./mvnw test
```

Trên PowerShell:

```powershell
.\mvnw.cmd test
```

Đây là code mẫu cho project Spring Boot 3 có dependencies tương ứng, **không phải tuyên bố tests đã chạy trong repository của người dùng**. Khi muốn xác minh trên Netty/proxy thật, dùng `RANDOM_PORT`/HTTP và test qua đúng ingress production, không chỉ dùng mock exchange.

## 18. Java 17 thuần: mô phỏng ba trách nhiệm với stdout cố định

Phần này **không giả lập Reactor hay implement Spring SPI**; nó chỉ làm lộ rõ ba trách nhiệm bằng Java 17 độc lập, để đối chiếu khi đọc các interfaces thật.

Tệp `PipelineRolesDemo.java`:

```java
public class PipelineRolesDemo {

    interface Mapping {
        String map(String path);
    }

    interface Adapter {
        String invoke(String handler);
    }

    interface ResultWriter {
        void write(String result);
    }

    public static void main(String[] args) {
        Mapping mapping = path ->
            "/hello".equals(path) ? "helloHandler" : null;

        Adapter adapter = handler ->
            "helloHandler".equals(handler) ? "Xin chào" : "unknown";

        ResultWriter writer = result ->
            System.out.println("HTTP body: " + result);

        String handler = mapping.map("/hello");
        System.out.println("handler=" + handler);
        String result = adapter.invoke(handler);
        System.out.println("result=" + result);
        writer.write(result);
    }
}
```

Chạy không cần Spring:

```bash
javac PipelineRolesDemo.java
java PipelineRolesDemo
```

Stdout **chính xác**:

```text
handler=helloHandler
result=Xin chào
HTTP body: Xin chào
```

Điều mô phỏng này bỏ qua `ServerWebExchange`, reactive Publishers, HTTP status, codecs, errors và real SPI contracts. Khi đọc code WebFlux, đổi từ interface demo `Mapping/Adapter/ResultWriter` sang `HandlerMapping/HandlerAdapter/HandlerResultHandler` với signatures đúng và kết quả `Mono`.

## 19. Thử nghiệm routing nâng cao và thứ tự ưu tiên

Nếu cần chẩn đoán một route không chạy:

1. Xem `HandlerMapping` beans hiện diện trong context: có `RequestMappingHandlerMapping` và `RouterFunctionMapping` hay không.
2. Kiểm tra method, path, headers, consumes/produces và path variables, không chỉ URL.
3. Xem thứ tự mappings (`Ordered`), nhưng đừng dựa vào số order được truyền miệng từ Spring version khác.
4. Nếu mapping đúng mà controller không được gọi, kiểm `WebFilter`/Spring Security, preflight CORS, exception trước adapter.
5. Nếu controller được gọi mà status/body không đúng, xét **return value type** và result handler tương ứng.
6. Nếu body không serialize, kiểm media type, codec registration và DTO/Jackson configuration.
7. Nếu response là HTML view thay vì string body, kiểm `@Controller` vs `@RestController`/`@ResponseBody`.
8. Nếu exception không vào `@ExceptionHandler`, xác định lỗi xảy ra ở layer filter, mapping, adapter hay **sau response commit**.
9. Kiểm tra startup logs/mapping introspection, test HTTP thực rồi mới cân nhắc custom SPI.

### Custom HandlerMapping chỉ khi cần programming model khác

Một custom mapping triển khai `HandlerMapping.getHandler(ServerWebExchange)` và trả handler object, nhưng **phải có HandlerAdapter biết gọi kiểu object đó**. Nếu bạn trả custom object không adapter nào `supports`, dispatcher không thể tự đoán cách invoke.

### Custom HandlerAdapter phải trả kết quả hợp contract

Một adapter custom phải:

- `supports(Object)` chặt chẽ, tránh nuốt HandlerMethod/HandlerFunction của Spring.
- `handle(exchange, handler)` trả `Mono<HandlerResult>` hoặc complete empty nếu đã tự handle response.
- Không block event loop khi gọi I/O.
- Tôn trọng cancellation/error và lưu exception handling strategy khi phù hợp.
- Có `HandlerResultHandler` hỗ trợ kiểu return value mới nếu default handlers không biết cách ghi.
- Có tests cho cả custom route và **mọi route tiêu chuẩn** cùng tồn tại.

### Custom HandlerResultHandler phải cẩn thận với order

Một result handler `supports` mọi thứ và `@Order(-1000)` có thể nhận cả `ResponseEntity`/`ServerResponse`, phá semantics HTTP. Nếu muốn hỗ trợ một specialized return type, giới hạn `supports` theo metadata/type và dùng `Mono<Void>` trả về từ response writer đúng reactive contract; kiểm error/commit/backpressure.

**Không viết custom SPI chỉ để đáp ứng một endpoint JSON thông thường.** Annotated controller hoặc RouterFunction đã hỗ trợ gần như toàn bộ use cases HTTP nghiệp vụ phổ biến.

## 20. Khi nào chọn annotated hay functional endpoints?

| Tiêu chí | Annotated controllers | Functional endpoints |
| --- | --- | --- |
| Entry | `@RestController`/`@RequestMapping` | `RouterFunction`/`HandlerFunction` |
| Mapping | `RequestMappingHandlerMapping` | `RouterFunctionMapping` |
| Adapter | `RequestMappingHandlerAdapter` | `HandlerFunctionAdapter` |
| Result | `ResponseBodyResultHandler`/`ResponseEntityResultHandler`/view... | `ServerResponseResultHandler` |
| Truy cập request | Method args và binding/validation annotations | `ServerRequest` |
| Response | Return DTO/Mono/Flux/ResponseEntity | `Mono<ServerResponse>` |
| Shared concerns | `@ControllerAdvice`, filters, codecs | Router-specific filters, `WebFilter`, codecs |
| Sở thích | API domain + validation annotations | Routing tập trung và functional composition |

Có thể phối hợp hai phong cách trong **một WebFlux app**. Chọn dựa trên team/style/khả năng kiểm thử, không vì một kiểu “non-blocking hơn” kiểu kia: cả hai đều dùng cùng Reactor/HTTP infrastructure. **Spring MVC functional `RouterFunction` thuộc package Servlet khác với WebFlux.fn**, cần imports chính xác.

## 21. Bảo mật, CORS và thứ tự xử lý

`DispatcherHandler` không phải lớp chịu trách nhiệm duy nhất về bảo mật:

- Spring Security WebFlux sử dụng `SecurityWebFilterChain`/WebFilters để authenticate/authorize request theo policy.
- `WebFilter` có thể reject trước routing, nhưng route metadata và matcher policy phải nhất quán để tránh bypass.
- CORS preflight có đường xử lý đặc biệt; Spring MVC `CorsFilter` Servlet không được dùng làm thay thế cho WebFlux CORS config.
- Không cho phép custom routing dựa raw client headers/path không canonicalized mà bỏ kiểm tra quyền trên resource.
- `@RestControllerAdvice` xử lý domain errors, **không** thay authorization policy ở filter chain.
- Error response không tiết lộ Java stack trace, internal handler bean names, session tokens hoặc SQL details.
- Không biến default result handler thành “send raw HTML” cho untrusted data: XSS cần output encoding/content policy.
- WebFlux reactive Context và security context không nên được thay bằng một ThreadLocal tự tạo trên Netty event loop.
- Với streaming, cần giới hạn số events, kích thước buffers và cleanup subscriptions khi disconnect.

Một `WebFilter` tự ghi status/body sớm có thể làm dispatcher không chạy; điều này phải có chủ ý và test, không coi là lỗi HandlerMapping nếu controller không được gọi.

## 22. Hiệu năng và observability theo từng lớp

Pipeline WebFlux rất nhanh khi đi qua các SPI mặc định, nhưng bottleneck thường ở service/database/network hoặc response body writer hơn là việc dò mapping.

Những tín hiệu nên đo:

| Metric / trace | Diễn giải |
| --- | --- |
| Request route match / no match | Route conditions có đúng không? |
| 404/405/406/415 | URI, method, Accept/Content-Type hoặc codec mismatch |
| Controller/service latency | Thời gian thực hiện business logic |
| Async body emit / write latency | Backpressure, client chậm, serialization |
| Reactor Netty event-loop blocking | Có gọi JDBC/`block()`/file IO trên event loop? |
| JSON encode/error rates | DTO, codec, payload shape |
| WebFilter/security failures | Lỗi trước dispatcher |
| Client cancellations | Connection đóng, cleanup resources |
| Memory buffers/queues | Streaming có accumulation không giới hạn? |
| Exception stage | Mapping, adapter, service, result writing, filter |

Nếu có tracing/metrics, nên gắn cùng trace ID xuyên request (dùng Reactor Context/observability đúng), không giả định một HTTP request luôn nằm trên một Java thread. Đừng log raw Authorization headers, credentials hoặc private response body để debug.

Tự in toàn bộ HandlerResult/handler object vào logs có thể lộ dữ liệu và gây chi phí; startup inspector chỉ nên in class names, và production có thể bỏ/giới hạn logs.

## 23. Bảng phân biệt với Spring MVC

| Đặc điểm | Spring WebFlux | Spring MVC |
| --- | --- | --- |
| Front controller | `DispatcherHandler` | `DispatcherServlet` |
| Core API | `WebHandler`, `ServerWebExchange`, `Mono<Void>` | `HttpServletRequest`/`HttpServletResponse` và Servlet dispatch |
| Mapping SPI | `org.springframework.web.reactive.HandlerMapping` | `org.springframework.web.servlet.HandlerMapping` |
| Adapter SPI | `org.springframework.web.reactive.HandlerAdapter` | `org.springframework.web.servlet.HandlerAdapter` |
| Result handling | `HandlerResultHandler` với `Mono<Void>` | MVC return-value handling/message converters/view resolvers |
| HTTP server | Reactor Netty hoặc reactive adapters | Servlet container |
| Programming models | Annotated + WebFlux.fn | Annotated + MVC.fn |
| I/O model | Reactive/non-blocking end-to-end nếu dependencies hỗ trợ | Servlet request model (có async support) |

Spring MVC cũng có `@Controller`, `@RestController`, `ResponseEntity` và hỗ trợ reactive return values trong những tình huống nhất định. Vì vậy tên annotation giống nhau **không chứng minh app chạy WebFlux**. Xem dependencies, Boot `WebApplicationType`, actual server và packages.

## 24. Các anti-pattern hay gặp

1. **Nhầm DispatcherHandler với DispatcherServlet**: khác stack và packages.
2. **Nghĩ DispatcherHandler tự gọi mọi method controller bằng reflection mà không cần adapter**.
3. **Nghĩ HandlerMapping vừa tìm vừa ghi JSON**: mapping chỉ tìm handler.
4. **Nghĩ HandlerAdapter đồng nghĩa HandlerResultHandler**.
5. **Nghĩ HandlerResult là body được ghi xong**: thực tế còn return type/metadata và writer.
6. **Nghĩ cùng default order=0 khiến ResponseEntity và ServerResponse tranh nhau**: `supports` phân biệt.
7. **Tạo custom HandlerResultHandler catch-all và order quá cao**: phá default routing/response semantics.
8. **Gắn @EnableWebFlux tùy tiện trên Boot app**: có thể thay đổi Boot customization.
9. **Thêm spring-boot-starter-web rồi tưởng app chắc chắn chạy reactive stack**.
10. **Trùng URL annotation và functional không kiểm order**: khó dự đoán route nào thắng.
11. **Chỉ kiểm URL path, quên method/consumes/produces/headers**: dẫn tới 405/415/406.
12. **Tự subscribe trong controller**: mất error/cancel/HTTP lifecycle.
13. **Gọi block() trên event loop**: chặn non-blocking processing.
14. **Dùng String return của @Controller và tưởng là raw body**: có thể là view name.
15. **Dùng @RestControllerAdvice để bắt mọi WebFilter exception**: không bao phủ mọi tầng.
16. **Cố ghi JSON lỗi sau khi SSE đã commit bytes**: status không thể luôn đổi.
17. **Coi mỗi Flux element là TCP packet**: codecs/buffering khác nhau.
18. **Không cleanup khi client cancel stream**: memory/connection leak.
19. **Dùng custom mapping không có matching adapter**: Dispatcher không thể invoke.
20. **Cho custom adapter supports mọi Object**: nuốt handler chuẩn.
21. **Không test body writer phù hợp DTO/Accept**: serialization error.
22. **Bỏ Spring Security/WebFilter khi xét flow routing**: request có thể bị chặn trước dispatcher.
23. **Dựa theo log tên SPI rồi kết luận thứ tự runtime cố định**: order phụ thuộc config.
24. **Không phân biệt reactive service thực với blocking I/O bọc trong Mono**.
25. **Tự sửa hạ tầng vì một route không được match** thay vì xem predicate/error stage.
26. **Không kiểm thử annotated và functional khi cùng app**: regression sau custom config.
27. **Không phân biệt Mono.empty do handler đã xử lý với no-handler**: adapter result và mapping là hai giai đoạn khác.
28. **Dùng status HTTP như bằng chứng DB mutation thành công** khi timeout/cancel còn race.
29. **Đặt handler logging lộ user context/headers**: rủi ro bảo mật.
30. **Bắt mọi Throwable và trả 200 để tránh lỗi log**: giấu error và khiến client nhận dữ liệu sai.

## 25. Checklist code review/production

### Routing

- [ ] Dự án thật sự dùng WebFlux starter/application type, không nhầm MVC?
- [ ] `DispatcherHandler` do WebFlux config/Boot quản lý, không tự tạo bản thứ hai?
- [ ] `HandlerMapping` đúng cho annotated và functional endpoints?
- [ ] Routes không trùng ngoài ý muốn, predicates method/headers/consumes/produces rõ?
- [ ] Custom mapping có order và no-match semantics được test?
- [ ] Security/CORS kiểm trước hoặc cùng route theo chính sách?

### Invocation và return values

- [ ] `HandlerAdapter` phù hợp handler type được mapping phát ra?
- [ ] Handler method không block event loop với JDBC/`block()`/sleep?
- [ ] `HandlerResultHandler` đúng với ResponseEntity, body DTO, ServerResponse và view?
- [ ] JSON codecs/HTTP message writers hỗ trợ DTO/media type?
- [ ] Không tự `subscribe()` trong controller?
- [ ] Streaming xử lý backpressure/cancel/cleanup đúng?
- [ ] Errors trước/sau response commit được phân biệt?

### Validation/operation

- [ ] `curl`/`WebTestClient` kiểm cả annotation lẫn functional paths?
- [ ] Test 202 ResponseEntity/status và 200 functional JSON?
- [ ] Test 404 no-route vs 404 từ handler, 405/406/415 khi áp dụng?
- [ ] Test WebFilter trước dispatcher và lỗi ngoài controller khi cần?
- [ ] Test SSE/stream completion và client disconnect với HTTP thực?
- [ ] Có metrics routing/error/codec/serialization/event-loop blocking?
- [ ] Không tùy tiện bật @EnableWebFlux/custom SPI trong Boot mà thiếu integration tests?

## 26. Câu hỏi tự kiểm tra

**1.** DispatcherHandler làm nhiệm vụ chính gì?

**Đáp án:** Là WebFlux front controller phối hợp HandlerMapping chọn request handler, HandlerAdapter gọi handler, HandlerResultHandler ghi result thành HTTP response.

**2.** HandlerMapping trả về object gì cho annotated controller?

**Đáp án:** Thường là `HandlerMethod` đại diện Java controller method đã được match, không phải JSON hay DTO.

**3.** Tại sao DispatcherHandler cần HandlerAdapter?

**Đáp án:** Handler object có nhiều kiểu như HandlerMethod, HandlerFunction, WebHandler; adapter che chi tiết cách gọi từng kiểu.

**4.** `HandlerAdapter.handle(...)` trả kiểu gì?

**Đáp án:** `Mono<HandlerResult>`, hoặc có thể hoàn thành empty khi request đã xử lý theo contract.

**5.** `HandlerResultHandler.handleResult(...)` trả kiểu gì?

**Đáp án:** `Mono<Void>` đại diện reactive operation hoàn tất việc xử lý response, không đồng nghĩa body rỗng.

**6.** Hai endpoints trả `Mono<Greeting>` và `Mono<ResponseEntity<Greeting>>` thường đi qua result handlers nào?

**Đáp án:** `ResponseBodyResultHandler` cho ordinary `@ResponseBody`, `ResponseEntityResultHandler` cho ResponseEntity.

**7.** Functional RouterFunction dùng adapter/result handler gì?

**Đáp án:** `HandlerFunctionAdapter` và `ServerResponseResultHandler` sau `RouterFunctionMapping`.

**8.** Nếu result handler cho ServerResponse và ResponseEntity đều order 0 thì xử lý thế nào?

**Đáp án:** `supports(result)` phân biệt type/metadata; không tranh mọi result chỉ vì cùng order.

**9.** Có cần tự subscribe Mono trong WebFlux controller không?

**Đáp án:** Không. Trả Mono/Flux cho HTTP infrastructure quản lý demand, serialization, error và cancellation.

**10.** Lỗi trong WebFilter có chắc vào @RestControllerAdvice không?

**Đáp án:** Không. Tùy vị trí/chain, lỗi ngoài annotated controller có thể do WebExceptionHandler xử lý.

**11.** Tại sao HTTP 404 có thể xuất hiện sau khi route đã match?

**Đáp án:** Controller/service có thể cố ý phát `ResponseStatusException(HttpStatus.NOT_FOUND)`; khác với route không tồn tại.

**12.** Có thể ghi JSON error mới sau khi streaming response đã commit không?

**Đáp án:** Không đảm bảo; phải cleanup, log/tracing, và có cơ chế báo lỗi qua stream protocol nếu cần.

**13.** Khi một custom HandlerMapping trả custom handler nhưng không adapter nào supports, chuyện gì xảy ra?

**Đáp án:** Dispatcher không có cách gọi kiểu handler đó; cần một HandlerAdapter tương ứng hoặc dùng programming model chuẩn.

**14.** Khi nào cần custom HandlerResultHandler?

**Đáp án:** Khi thực sự bổ sung return type/response strategy mới mà handlers mặc định không hỗ trợ, và đã cân nhắc codecs/ResponseEntity/ServerResponse trước.

**15.** Có thể vừa dùng annotated controller vừa dùng RouterFunction trong một WebFlux app không?

**Đáp án:** Có. Chúng cùng DispatcherHandler nhưng có mapping/adapter/result contract khác nhau.

## 27. Tài liệu tham khảo

- Spring Framework 6.2 — DispatcherHandler, SPI and result-handling order: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html
- Spring Framework 6.2 — Reactive Core / WebHandler API, filters and errors: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.2 — Functional Endpoints and infrastructure beans: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html
- Spring Framework 6.2 — WebFlux Overview: https://docs.spring.io/spring-framework/reference/6.2/web/webflux.html
- Spring Framework — DispatcherHandler Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/DispatcherHandler.html
- Spring Framework — HandlerMapping Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/HandlerMapping.html
- Spring Framework — HandlerAdapter Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/HandlerAdapter.html
- Spring Framework — HandlerResultHandler Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/HandlerResultHandler.html
- Spring Framework — HandlerResult Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/HandlerResult.html
- Spring Framework — DispatchExceptionHandler Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/DispatchExceptionHandler.html
- Spring Framework — WebFlux configuration: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html
- Spring Framework — WebFlux annotated return values: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Project Reactor documentation: https://projectreactor.io/docs/core/release/reference/
