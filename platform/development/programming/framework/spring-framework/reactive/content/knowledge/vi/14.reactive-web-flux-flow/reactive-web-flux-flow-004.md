# DispatcherHandler và cơ chế điều phối trong Spring WebFlux

> **Module:** Spring Framework – reactive · **Chủ đề cha:** Luồng xử lý WebFlux. Bài học đi theo vòng đời một HTTP request qua `DispatcherHandler`: từ `HttpHandler`, `WebFilter`, `HandlerMapping`, `HandlerAdapter`, `HandlerResult`, đến `HandlerResultHandler` và response writer. Có so sánh annotated controller với functional endpoint, xử lý lỗi, cấu hình, ví dụ Spring Boot 4.0.9 / Java 17+ chạy được và kiểm thử HTTP tích hợp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `DispatcherHandler` là **front controller** của Spring WebFlux và vai trò của nó trong chuỗi `WebHandler`.
2. Vẽ được vòng đời request: server adapter → `HttpHandler` → `WebExceptionHandler`/`WebFilter` → `DispatcherHandler` → mapping → adapter → result handler → HTTP response.
3. Phân biệt ba hợp đồng cốt lõi: `HandlerMapping`, `HandlerAdapter` và `HandlerResultHandler`.
4. Giải thích `HandlerResult`, `ServerWebExchange`, `Mono<Void>`, `HttpMessageReader` và `HttpMessageWriter` đóng vai trò gì.
5. Hiểu annotated controller (`@RestController`) và WebFlux.fn (`RouterFunction`/`HandlerFunction`) dùng **cùng cơ chế dispatch**, nhưng chọn mapping, adapter và result handler khác nhau.
6. Xác định exception xảy ra trước khi tìm được handler, trong lúc gọi handler hay khi ghi response được xử lý ở lớp nào.
7. Tùy biến WebFlux bằng `WebFluxConfigurer`, `WebFilter`, `WebExceptionHandler` và custom special bean đúng mức.
8. Chạy ứng dụng Java 17+ và kiểm thử các route, lỗi, 404 bằng HTTP integration test mà không cần gọi `subscribe()`/`block()` trong controller.

**Một câu dễ nhớ:** `DispatcherHandler` điều phối *ai xử lý request* và *ai chuyển kết quả thành response*; bản thân nó không chứa toàn bộ logic controller, codec hay server socket.

## 2. DispatcherHandler là gì?

Spring WebFlux dùng **Front Controller pattern**, tương tự ý tưởng `DispatcherServlet` trong Spring MVC. Một `DispatcherHandler` trung tâm nhận `ServerWebExchange`, tìm handler phù hợp, chọn adapter để gọi handler và chọn result handler để hoàn thiện response.

`DispatcherHandler`:
- Là một `WebHandler` trong package `org.springframework.web.reactive`.
- Implement `ApplicationContextAware` để đọc các delegate bean từ Spring `ApplicationContext`.
- Phát hiện các special bean theo hợp đồng WebFlux: `HandlerMapping`, `HandlerAdapter`, `HandlerResultHandler`.
- Thường được đăng ký với bean name **`webHandler`**, để `WebHttpHandlerBuilder` tìm thấy khi xây dựng chuỗi HTTP.
- Được cấu hình sẵn khi dùng WebFlux Config / `@EnableWebFlux`; Spring Boot tự cấu hình phần lớn hạ tầng khi có starter WebFlux.

Nó không phải `DispatcherServlet` được chuyển tên. WebFlux xử lý theo reactive contract: request/response dùng `ServerWebExchange`, handler thường trả `Mono`/`Flux`, quá trình hoàn tất biểu diễn bằng `Mono<Void>`, và server có thể chạy trên Reactor Netty hoặc các runtime được hỗ trợ. Không có một thread riêng bắt buộc cho mỗi request; tính non-blocking phụ thuộc cả connector lẫn việc code ứng dụng không khóa event-loop.

### 2.1. Chuỗi xử lý ở mức HTTP

Trước khi request đến `DispatcherHandler`, Spring xây dựng một chain bao quanh `WebHandler`:

~~~text
HTTP server (ví dụ Reactor Netty)
          |
          v
      HttpHandler
          |
          v
 WebExceptionHandler chain
          |
          v
    WebFilter chain
          |
          v
   DispatcherHandler
          |
          v
    HandlerMapping
          |
          v
    HandlerAdapter
          |
          v
      HandlerResult
          |
          v
  HandlerResultHandler
          |
          v
ServerHttpResponse / HttpMessageWriter
          |
          v
HTTP response
~~~

`WebHttpHandlerBuilder` có hai nhiệm vụ: ghép một target `WebHandler` với các `WebFilter`, sau đó với các `WebExceptionHandler`; và chuyển chuỗi đó thành `HttpHandler` cấp thấp để server adapter sử dụng. Ở chiều request, exception handlers bao quanh filter chain và target handler; response/error đi ngược qua các lớp bao ngoài theo cơ chế reactive.

**Phân biệt các lớp:**

| Thành phần | Trách nhiệm |
| --- | --- |
| `HttpHandler` | Abstraction HTTP cấp thấp, không phụ thuộc trực tiếp một server cụ thể. |
| `WebHandler` | Hợp đồng xử lý `ServerWebExchange`; `DispatcherHandler` là một implementation. |
| `WebFilter` | Chặn/bao quanh request-response trước và sau `WebHandler`, ví dụ security, CORS, correlation ID. |
| `WebExceptionHandler` | Xử lý exception phát sinh trong filter chain hoặc target `WebHandler`. |
| `DispatcherHandler` | Điều phối mapping, invocation và result handling. |
| Server adapter | Nối `HttpHandler` với runtime HTTP thực tế. |

`ServerWebExchange` là ngữ cảnh cho một HTTP request/response, gồm `ServerHttpRequest`, `ServerHttpResponse`, session, attributes, principal và các thông tin request đã được resolve. Các handler và filter dùng cùng exchange để phối hợp mà không cần truyền từng object qua hàng loạt method.

### 2.2. `DispatcherHandler` không phải nơi viết business logic

Không đưa truy vấn database, tính giá hay quy tắc nghiệp vụ trực tiếp vào một custom `DispatcherHandler`. Business logic thuộc service/domain; controller hoặc `HandlerFunction` gọi service rồi trả Publisher. `DispatcherHandler` giữ thuật toán điều phối chung để các kiểu handler khác nhau cùng hoạt động.

## 3. Ba delegate cốt lõi

`DispatcherHandler` tìm ba nhóm bean trong ApplicationContext. Mỗi nhóm có một hợp đồng riêng.

### 3.1. HandlerMapping — tìm handler cho request

Hợp đồng chính:

~~~java
Mono<Object> getHandler(ServerWebExchange exchange);
~~~

`HandlerMapping` nhận exchange và trả `Mono` chứa handler nếu tìm thấy, hoặc hoàn thành rỗng nếu mapping đó không phù hợp. Có nhiều cách tìm handler, ví dụ:
- `RequestMappingHandlerMapping`: tìm method trong `@Controller`/`@RestController` dựa trên `@RequestMapping`, `@GetMapping`, HTTP method, path, headers, params, `consumes`, `produces` và các điều kiện mapping khác.
- `RouterFunctionMapping`: tìm route khai báo bằng WebFlux.fn (`RouterFunction`).
- `SimpleUrlHandlerMapping`: ánh xạ URL pattern tới `WebHandler` cụ thể, thường dùng cho static resources và resource handlers.

`DispatcherHandler` hỏi các `HandlerMapping` theo thứ tự đã được sắp xếp; **mapping đầu tiên trả handler phù hợp được chọn**. Nếu mapping trả `Mono.empty()`, nó tiếp tục mapping kế tiếp. Vì vậy order của custom mapping có thể ảnh hưởng route nào thắng.

**Không phải cứ có URL gần giống là mapping được chọn.** Mapping còn kiểm tra method, header, media type, query parameter, path pattern, version hoặc điều kiện được cấu hình. CORS/preflight cũng có thể được kiểm tra trong quá trình mapping.

### 3.2. HandlerAdapter — gọi handler đã chọn

Hợp đồng:

~~~java
boolean supports(Object handler);

Mono<HandlerResult> handle(
    ServerWebExchange exchange, Object handler);
~~~

Một `HandlerAdapter` biết cách **invoke một loại handler cụ thể**, để `DispatcherHandler` không phải hiểu từng mô hình lập trình. Adapter kiểm tra `supports(handler)`, sau đó gọi handler và trả `Mono<HandlerResult>`. Adapter cũng có thể trả Mono rỗng nếu request đã được xử lý hoàn toàn và không cần bước result handling thông thường.

Một số adapter phổ biến:

| HandlerAdapter | Handler được hỗ trợ | Vai trò |
| --- | --- | --- |
| `RequestMappingHandlerAdapter` | Method handler từ annotated controller | Resolve argument, gọi controller method, xử lý return value reactive. |
| `HandlerFunctionAdapter` | `HandlerFunction<ServerResponse>` | Gọi handler function của WebFlux.fn. |
| `SimpleHandlerAdapter` | Handler kiểu `WebHandler` | Gọi trực tiếp một WebHandler được mapping. |
| `WebSocketHandlerAdapter` | `WebSocketHandler` | Chuyển giao xử lý WebSocket theo contract tương ứng. |

Adapter là ranh giới giúp cùng một dispatcher hỗ trợ annotation, functional endpoint, resource và các loại handler mở rộng.

### 3.3. HandlerResult — gói kết quả invocation

`HandlerResult` mang thông tin cần thiết để xử lý kết quả:
- Handler đã được gọi.
- Giá trị return thực tế (có thể là object hoặc reactive type).
- Kiểu return được khai báo qua `ResolvableType`/`MethodParameter`.
- `BindingContext` và model trong trường hợp cần data binding/view.
- Cơ chế `DispatchExceptionHandler` nếu adapter cung cấp xử lý lỗi cho kết quả bất đồng bộ.

**Khai báo kiểu trả về rất quan trọng.** `Mono<Item>`, `ResponseEntity<Mono<Item>>`, `Flux<Item>`, `String` hoặc `ServerResponse` có thể được result handler xử lý theo contract khác nhau. HandlerResult giữ cả return value lẫn metadata cần để lựa chọn.

### 3.4. HandlerResultHandler — biến HandlerResult thành response

Hợp đồng chính:

~~~java
boolean supports(HandlerResult result);

Mono<Void> handleResult(
    ServerWebExchange exchange, HandlerResult result);
~~~

Dispatcher tìm `HandlerResultHandler` đầu tiên nhận hỗ trợ result. Handler này ghi status/header/body trực tiếp hoặc render view; `Mono<Void>` hoàn tất khi việc xử lý response hoàn tất.

Các result handler mặc định thường gặp:

| HandlerResultHandler | Return value thường xử lý | Default order |
| --- | --- | ---: |
| `ResponseEntityResultHandler` | `ResponseEntity`, thường từ controller | 0 |
| `ServerResponseResultHandler` | `ServerResponse` từ functional endpoint | 0 |
| `ResponseBodyResultHandler` | `@ResponseBody`, `@RestController` | 100 |
| `ViewResolutionResultHandler` | `CharSequence`, `View`, `Model`, `Map`, `Rendering` hoặc model attribute | `Integer.MAX_VALUE` |

Order và `supports` phối hợp với nhau: hai result handler có thể cùng order nhưng nhận các kiểu kết quả khác nhau. `ResponseEntityResultHandler` xử lý status/header/body từ ResponseEntity; `ResponseBodyResultHandler` ghi body của `@ResponseBody`; `ServerResponseResultHandler` ghi ServerResponse; `ViewResolutionResultHandler` tìm View khi ứng dụng render HTML.

## 4. Luồng dispatch từng bước

Đây là trình tự khái quát cho một request bình thường:

1. **Server nhận request.** Reactor Netty hoặc server adapter nhận byte HTTP và gọi `HttpHandler`.
2. **Tạo Web exchange.** `HttpWebHandlerAdapter` chuyển request thành `ServerWebExchange`, tạo context cho request/response.
3. **WebExceptionHandler và WebFilter bao quanh.** Exception handlers thiết lập khả năng chuyển lỗi thành response; filters có thể xác thực, ghi log, thêm header hoặc từ chối request trước khi dispatch.
4. **DispatcherHandler nhận exchange.** Nó dùng danh sách `HandlerMapping` đã phát hiện từ ApplicationContext.
5. **Tìm handler.** Mỗi mapping được hỏi; kết quả phù hợp đầu tiên được dùng. Nếu không có mapping nào trả handler, request không có route phù hợp và mặc định đi tới lỗi 404.
6. **Chọn HandlerAdapter.** Dispatcher tìm adapter có `supports(handler)` đúng, rồi gọi `handle(exchange, handler)`.
7. **Tạo HandlerResult.** Adapter resolve tham số và invoke controller/function/WebHandler. Kết quả invocation được gói thành `HandlerResult`.
8. **Chọn HandlerResultHandler.** Dispatcher xét các result handler theo thứ tự và chọn handler hỗ trợ result.
9. **Ghi response.** Result handler đặt status/header và ghi body qua `ServerHttpResponse` hoặc `HttpMessageWriter`, có thể render view. `Mono<Void>` biểu diễn thời điểm response processing kết thúc.
10. **Filter chain hoàn tất.** Các operator/filter ở ngoài có thể quan sát status, thời gian, terminal signal và cleanup theo lifecycle.

~~~mermaid
flowchart TD
    A["HTTP server / HttpHandler"] --> B["WebExceptionHandler chain"]
    B --> C["WebFilter chain"]
    C --> D["DispatcherHandler"]
    D --> E["Hỏi HandlerMapping theo order"]
    E --> F{"Có handler phù hợp?"}
    F -- "Không" --> G["404 / dispatch error"]
    F -- "Có" --> H["Tìm HandlerAdapter.supports"]
    H --> I["Adapter.invoke → Mono<HandlerResult>"]
    I --> J["Tìm HandlerResultHandler.supports"]
    J --> K["Ghi status, headers, body hoặc render View"]
    K --> L["Mono<Void> hoàn tất response"]
    G --> M["Exception handling"]
~~~

Dispatcher không đợi một thread đồng bộ riêng cho toàn request. Mỗi bước có thể trả Publisher và chỉ thực thi khi subscription tiến triển; I/O reactive có thể hoàn thành sau đó. **Không gọi `block()` hoặc tự `subscribe()` trong controller/service** để chờ kết quả trước khi trả response.

## 5. Annotated controller đi qua DispatcherHandler như thế nào?

Với:

~~~java
@RestController
@RequestMapping("/api/items")
class ItemController {

    @GetMapping("/{id}")
    Mono<Item> get(@PathVariable String id) {
        return service.findById(id);
    }
}
~~~

Luồng điển hình:
1. `RequestMappingHandlerMapping` tìm method mapping tương ứng `/api/items/{id}` và GET.
2. `RequestMappingHandlerAdapter` chuẩn bị invocation: resolve `@PathVariable`, `@RequestBody`, `@RequestHeader`, `Principal`, `ServerWebExchange`, validation và các argument resolver phù hợp.
3. Adapter gọi method controller. Return value `Mono<Item>` được đặt trong HandlerResult cùng metadata kiểu trả về.
4. `ResponseBodyResultHandler` nhận return value của `@RestController`.
5. `HttpMessageWriter` phù hợp (ví dụ Jackson JSON encoder) ghi Item vào response; `Mono<Void>` kết thúc khi response được ghi.

**Điều quan trọng:** controller method có thể trả `Mono<Item>` ngay khi mới dựng pipeline. Giá trị Item được tạo sau đó khi service Publisher phát; adapter/result handler phối hợp theo reactive contract. Không cần controller chờ `Item` rồi trả object đồng bộ.

### 5.1. Các điều kiện mapping

Một method có thể được chọn theo nhiều điều kiện:

~~~java
@GetMapping(
    path = "/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE)
Mono<Item> getJson(@PathVariable String id) {
    return service.findById(id);
}
~~~

Các thuộc tính `path`, `method`, `params`, `headers`, `consumes`, `produces` và các điều kiện mapping được dùng để xác định method. Ví dụ:
- HTTP method không khớp có thể tạo lỗi method not allowed.
- `consumes` không phù hợp với Content-Type có thể dẫn đến 415.
- `produces` không phù hợp Accept có thể dẫn đến 406.
- Path không có handler phù hợp có thể thành 404.

Mapping cụ thể phụ thuộc cấu hình và các route cạnh tranh; không nên tạo hai method có điều kiện mơ hồ rồi dựa vào thứ tự khai báo trong file Java.

## 6. Functional endpoint cũng dùng DispatcherHandler

WebFlux.fn tách route khỏi handler. Thay vì khai báo `@GetMapping`, ta tạo `RouterFunction` và `HandlerFunction`:

~~~java
@Bean
RouterFunction<ServerResponse> itemRoutes(ItemHandler handler) {
    return RouterFunctions.route()
        .GET("/api/functional/items/{id}", handler::get)
        .build();
}
~~~

~~~java
@Component
class ItemHandler {
    Mono<ServerResponse> get(ServerRequest request) {
        String id = request.pathVariable("id");
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new Item(id, "Item " + id));
    }
}
~~~

Hai fragment trên cần Spring WebFlux, kiểu `Item` và bean `ItemHandler`. Cơ chế:
1. `RouterFunctionMapping` đánh giá RouterFunction và chọn `HandlerFunction`.
2. `HandlerFunctionAdapter` gọi function với `ServerRequest`.
3. Function trả `Mono<ServerResponse>`.
4. `ServerResponseResultHandler` nhận ServerResponse và ghi response.

**Functional endpoint không bỏ qua DispatcherHandler.** Nó chỉ thay mô hình khai báo handler; mapping, adapter, result handling và WebHandler chain vẫn dùng cùng nền tảng. Có thể dùng annotated controller và functional route trong cùng ứng dụng nếu route không xung đột.

### 6.1. So sánh hai mô hình

| Nội dung | Annotated controller | WebFlux.fn |
| --- | --- | --- |
| Khai báo route | `@RequestMapping`, `@GetMapping`, ... | `RouterFunction` / `RequestPredicate` |
| Handler | Method trên `@Controller` | `HandlerFunction<ServerResponse>` |
| Mapping mặc định | `RequestMappingHandlerMapping` | `RouterFunctionMapping` |
| Adapter mặc định | `RequestMappingHandlerAdapter` | `HandlerFunctionAdapter` |
| Result handler thường gặp | `ResponseEntityResultHandler`, `ResponseBodyResultHandler` | `ServerResponseResultHandler` |
| Lấy tham số | `@PathVariable`, `@RequestBody`, `@RequestHeader`... | `ServerRequest.pathVariable`, `bodyToMono`, headers... |
| Phù hợp | API controller quen thuộc, annotation/argument resolver | Route rõ ràng, composition functional, module route nhỏ |

### 6.2. Thứ tự mapping trong Spring Boot

Trong cấu hình Spring Boot mặc định, order thường đặt:
1. `RouterFunctionMapping` cho các `RouterFunction` bean.
2. `RequestMappingHandlerMapping` cho `@Controller`/`@RestController`.
3. Một `RouterFunctionMapping` cho welcome page nếu có.

Vì `DispatcherHandler` chọn **match đầu tiên**, hai mô hình khai báo cùng một path/method có thể tạo route shadowing. Hãy tránh duplicate route hoặc cấu hình order có chủ ý; không giả định route annotation luôn thắng functional route. Với custom `HandlerMapping`, implement `Ordered`/`@Order` theo mục tiêu rõ ràng.

## 7. Result handling, body và codec

`HandlerResultHandler` quyết định cách diễn giải return value, còn codec chịu trách nhiệm chuyển dữ liệu Java ↔ byte HTTP.

| Chiều | Contract | Ví dụ |
| --- | --- | --- |
| Đọc request body | `HttpMessageReader` | JSON request → `Mono<CreateItemRequest>` |
| Ghi response body | `HttpMessageWriter` | `Mono<Item>` → JSON bytes |
| Ghi response tùy biến | `ServerHttpResponse` | Header/status/body trực tiếp |
| Render HTML | `ViewResolver` + `View` | logical view name → template |

Ví dụ controller:

~~~java
@PostMapping("/items")
Mono<ResponseEntity<Item>> create(
        @Valid @RequestBody Mono<CreateItemRequest> request) {
    return request
        .flatMap(service::create)
        .map(item -> ResponseEntity
            .created(URI.create("/api/items/" + item.id()))
            .body(item));
}
~~~

Đây là fragment cần kiểu `CreateItemRequest`, `Item`, service và import. `HttpMessageReader` decode request body; argument resolution cung cấp `Mono<CreateItemRequest>`; service tạo Item; result handler xử lý `ResponseEntity<Item>` để ghi status 201, Location và JSON body.

**Reactive return value:**
- `Mono<T>` biểu diễn tối đa một giá trị.
- `Flux<T>` biểu diễn nhiều giá trị; writer phù hợp có thể stream phần tử thay vì phải thu thập tất cả.
- `Mono<Void>` thường biểu diễn thao tác chỉ cần hoàn tất, không có body.
- `ResponseEntity<T>` mang status/header/body; có thể kết hợp với reactive body theo API hỗ trợ.
- `ServerResponse` là mô hình response của functional endpoint.

Content negotiation dựa vào `Accept`, `produces`, loại return value và codec hỗ trợ. Nếu response là stream (SSE, NDJSON hoặc media type phù hợp), writer có thể ghi dần và áp dụng backpressure. Nếu response đã bắt đầu ghi bytes rồi mới xảy ra lỗi, server không thể đơn giản thay toàn bộ body/status như một response chưa commit; xử lý stream error phải được thiết kế riêng.

## 8. Xử lý exception ở đâu?

Lỗi có thể xảy ra ở nhiều giai đoạn, nên cần chọn đúng tầng:

| Lỗi xảy ra | Cơ chế xử lý phù hợp |
| --- | --- |
| Trước khi handler được chọn: filter, mapping, dispatch | `WebExceptionHandler`; adapter có thể triển khai `DispatchExceptionHandler` cho một số lỗi dispatch |
| Khi gọi controller method | Adapter và exception handler của annotated controller, thường là `@ExceptionHandler`/`@ControllerAdvice` |
| Sau khi controller trả Mono/Flux và Publisher phát lỗi | Exception handler được gắn với HandlerResult có thể xử lý nếu response còn có thể thay đổi |
| Trong lúc result handler/codec ghi response | `DispatchExceptionHandler`/WebExceptionHandler tùy giai đoạn; nếu response đã commit thì không thể thay status/body đã gửi |
| Không tìm thấy handler | Dispatch mặc định dẫn tới 404 |

### 8.1. `@ControllerAdvice` không phải global handler cho mọi lỗi

`@ExceptionHandler` trong controller hoặc `@RestControllerAdvice` gắn với handler invocation và có thể xử lý cả lỗi deferred từ reactive return value theo cơ chế WebFlux. Tuy nhiên, **không dùng `@ControllerAdvice` làm cách duy nhất xử lý lỗi xảy ra trước khi handler được chọn**, ví dụ lỗi ở `WebFilter` hoặc `HandlerMapping`. Những lỗi đó thuộc WebHandler exception chain/`WebExceptionHandler` hoặc `DispatchExceptionHandler` phù hợp.

### 8.2. WebExceptionHandler

`WebExceptionHandler` xử lý exception trong chain của các `WebFilter` và target `WebHandler`. WebFlux Config có `ResponseStatusExceptionHandler`; `WebFluxResponseStatusExceptionHandler` cũng xét `@ResponseStatus` trên exception. Có thể đăng ký bean và dùng `@Order`/`Ordered` để kiểm soát thứ tự nếu nhiều handler cùng tham gia.

**Không bắt mọi Throwable rồi luôn trả 200.** Giữ đúng status, log/trace correlation ID, tránh lộ stack trace/bí mật, và không ghi response lần thứ hai sau khi response đã commit.

### 8.3. DispatchExceptionHandler

`DispatchExceptionHandler` cung cấp cách xử lý lỗi ở dispatch pipeline. `HandlerAdapter` có thể:
- Xử lý lỗi invocation ngay trong `handle`.
- Gắn exception handler vào `HandlerResult` để xử lý lỗi phát sinh muộn khi xử lý return value hoặc ghi response.
- Triển khai `DispatchExceptionHandler` để tham gia xử lý lỗi xảy ra trước khi handler được chọn, ví dụ lỗi mapping hoặc filter trước đó.

Đây là điểm khác quan trọng của WebFlux: lỗi từ `Mono`/`Flux` có thể xảy ra **sau khi method controller đã return**, vì vậy không thể chỉ dùng `try/catch` đồng bộ quanh lời gọi method để bắt mọi lỗi.

## 9. WebFilter, HandlerInterceptor và mapping khác nhau thế nào?

- **WebFilter** bao quanh toàn bộ WebHandler chain. Dùng cho security, CORS, request ID, logging, metrics, cross-cutting concerns áp dụng rộng.
- **HandlerInterceptor** gắn với quá trình xử lý handler được chọn, thường theo `HandlerMapping`; thích hợp cho logic trước/sau handler cụ thể.
- **HandlerMapping** tìm handler; nó không phải nơi thực thi business method.
- **HandlerAdapter** invoke handler đã chọn; nó không quyết định route.
- **HandlerResultHandler** ghi/diễn giải kết quả; nó không chọn controller method.

Ví dụ filter ghi thời gian:

~~~java
@Component
class RequestTimingFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        long start = System.nanoTime();

        return chain.filter(exchange)
            .doFinally(signal -> {
                long elapsedMs =
                    (System.nanoTime() - start) / 1_000_000;
                System.out.printf("%s %s -> %s (%s, %d ms)%n",
                    exchange.getRequest().getMethod(),
                    exchange.getRequest().getURI().getPath(),
                    exchange.getResponse().getStatusCode(),
                    signal,
                    elapsedMs);
            });
    }
}
~~~

Đây là fragment component có thể thêm vào ứng dụng WebFlux. `doFinally` chạy với complete/error/cancel nên hữu ích để quan sát vòng đời exchange; `getStatusCode()` có thể chưa được đặt nếu lỗi xảy ra rất sớm. Callback phải nhanh, không block event-loop, không mở một subscription độc lập để ghi log.

## 10. Cấu hình WebFlux và các special bean

### 10.1. Spring Boot auto-configuration

Khi có `spring-boot-starter-webflux`, Boot cấu hình các bean mặc định: DispatcherHandler, HandlerMapping, HandlerAdapter, HandlerResultHandler, codecs, static resource handling và server integration. Với phần lớn ứng dụng, hãy bổ sung `WebFluxConfigurer` để tùy biến cần thiết.

**Nếu muốn giữ auto-configuration của Boot:** khai báo bean `WebFluxConfigurer` nhưng **không thêm `@EnableWebFlux`**. `@EnableWebFlux` cho ứng dụng quyền kiểm soát đầy đủ cấu hình WebFlux; khi đó Boot không còn áp dụng toàn bộ WebFlux auto-configuration theo mặc định. Chỉ chọn cách này khi chủ động tự quản lý hạ tầng.

### 10.2. Cấu hình codec

~~~java
@Configuration
class ApiWebConfig implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
            .maxInMemorySize(2 * 1024 * 1024);
    }
}
~~~

Fragment này giới hạn dung lượng buffer mặc định cho codec ở 2 MiB; giá trị phải theo payload và yêu cầu ứng dụng. Đây là một ví dụ WebFluxConfigurer giữ Boot auto-configuration. Không tăng buffer vô hạn để che lỗi payload quá lớn.

### 10.3. Custom HandlerMapping/Adapter/ResultHandler

Có thể khai báo custom special bean nếu cần kiểu route hoặc handler riêng. Trước khi tự viết, hãy kiểm tra:
- Có thể giải quyết bằng `RouterFunction`/controller annotation không?
- Custom `HandlerMapping` có xác định order và trả `Mono.empty()` đúng khi không match không?
- Custom `HandlerAdapter` có xử lý exception đồng bộ lẫn deferred reactive không?
- Custom `HandlerResultHandler` có implement `supports` chặt chẽ và trả `Mono<Void>` chỉ khi response đã được xử lý không?
- Có giữ backpressure, cancellation, codec và content negotiation đúng không?

Một custom mapping đứng quá sớm có thể shadow route mặc định; một result handler `supports` quá rộng có thể nhận nhầm return value của controller khác. Đây là extension point mạnh, nhưng nên dùng khi mô hình handler thực sự khác với mô hình chuẩn.

## 11. Ví dụ chạy được: Spring Boot 4.0.9 + Java 17

Ví dụ dưới đây có hai endpoint cùng hoạt động qua DispatcherHandler:
- `/api/annotated/{id}` dùng annotated controller.
- `/api/functional/{id}` dùng WebFlux.fn.
- `/api/annotated/fail` tạo lỗi để thấy `@RestControllerAdvice`.
- Một filter ghi request path, status và thời gian.

### 11.1. Cấu trúc dự án

~~~text
dispatcher-handler-demo/
├── pom.xml
├── src/main/java/com/example/dispatch/DispatchApplication.java
├── src/main/java/com/example/dispatch/Item.java
├── src/main/java/com/example/dispatch/ItemController.java
├── src/main/java/com/example/dispatch/FunctionalRoutes.java
├── src/main/java/com/example/dispatch/ApiExceptionHandler.java
├── src/main/java/com/example/dispatch/RequestTimingFilter.java
└── src/test/java/com/example/dispatch/DispatchIntegrationTest.java
~~~

### 11.2. pom.xml

Boot 4.0.9 yêu cầu Java 17 trở lên và Maven 3.6.3 trở lên. Starter WebFlux cung cấp reactive web stack và embedded server integration; Spring Boot quản lý phiên bản Spring Framework/Reactor tương thích.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>dispatcher-handler-demo</artifactId>
    <version>1.0.0</version>
    <name>dispatcher-handler-demo</name>

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

### 11.3. `DispatchApplication.java`

~~~java
package com.example.dispatch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DispatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(DispatchApplication.class, args);
    }
}
~~~

### 11.4. `Item.java`

~~~java
package com.example.dispatch;

public record Item(String id, String name) {}
~~~

### 11.5. `ItemController.java` — annotated route

~~~java
package com.example.dispatch;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/annotated")
public class ItemController {

    @GetMapping("/{id}")
    public Mono<Item> find(@PathVariable String id) {
        return Mono.just(new Item(id, "Item " + id));
    }

    @GetMapping("/fail")
    public Mono<Item> fail() {
        return Mono.error(new IllegalArgumentException("invalid item"));
    }
}
~~~

Ở đây `RequestMappingHandlerMapping` chọn method; `RequestMappingHandlerAdapter` resolve `@PathVariable` và gọi method; `ResponseBodyResultHandler` ghi `Mono<Item>` thành JSON. Method `fail()` trả một Mono lỗi bất đồng bộ, để WebFlux exception handling xử lý theo handler context.

### 11.6. `FunctionalRoutes.java` — functional route

~~~java
package com.example.dispatch;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> itemRoutes() {
        return RouterFunctions.route()
            .GET("/api/functional/{id}", request -> {
                String id = request.pathVariable("id");
                Item item = new Item(id, "Item " + id);
                return ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(item);
            })
            .build();
    }
}
~~~

`RouterFunctionMapping` tìm route; `HandlerFunctionAdapter` gọi lambda; `ServerResponseResultHandler` ghi `ServerResponse`. Hai endpoint annotated/functional được phục vụ bởi cùng DispatcherHandler và cùng HTTP server.

### 11.7. `ApiExceptionHandler.java`

~~~java
package com.example.dispatch;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> badRequest(
            IllegalArgumentException exception) {
        return ResponseEntity.badRequest().body(
            Map.of("error", exception.getMessage()));
    }
}
~~~

Advice này xử lý lỗi từ controller/handler invocation. Nếu lỗi xảy ra trong WebFilter trước khi handler được chọn, cần `WebExceptionHandler` ở lớp WebHandler chain; không kỳ vọng advice này bao phủ mọi lỗi của server.

### 11.8. `RequestTimingFilter.java`

~~~java
package com.example.dispatch;

import org.springframework.core.annotation.Order;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.LOWEST_PRECEDENCE)
public class RequestTimingFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        long start = System.nanoTime();

        return chain.filter(exchange)
            .doFinally(signal -> {
                long elapsedMs =
                    (System.nanoTime() - start) / 1_000_000;
                String status = exchange.getResponse().getStatusCode() == null
                    ? "unset"
                    : String.valueOf(
                        exchange.getResponse().getStatusCode().value());

                System.out.printf("%s %s -> %s (%s, %d ms)%n",
                    exchange.getRequest().getMethod(),
                    exchange.getRequest().getURI().getPath(),
                    status,
                    signal,
                    elapsedMs);
            });
    }
}
~~~

Filter được áp dụng quanh dispatcher. `LOWEST_PRECEDENCE` ở đây chỉ là một lựa chọn cho demo; ứng dụng có Spring Security, CORS hoặc filter khác cần thiết kế order theo chính sách bảo mật và thứ tự thực tế. Không đặt log hoặc metrics callback thành thao tác blocking.

### 11.9. Chạy ứng dụng

Ở thư mục chứa `pom.xml`, kiểm tra:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Mặc định ứng dụng nghe cổng 8080 nếu không đổi cấu hình.

Thử annotated endpoint:

~~~bash
curl -i http://localhost:8080/api/annotated/42
~~~

Body JSON dự kiến:

~~~json
{"id":"42","name":"Item 42"}
~~~

Thử functional endpoint:

~~~bash
curl -i http://localhost:8080/api/functional/42
~~~

Body JSON dự kiến:

~~~json
{"id":"42","name":"Item 42"}
~~~

Thử lỗi do controller:

~~~bash
curl -i http://localhost:8080/api/annotated/fail
~~~

Status dự kiến là `400 Bad Request`; body có trường `"error":"invalid item"` (các trường JSON có thể có thứ tự khác nhau).

Thử URL không được mapping:

~~~bash
curl -i http://localhost:8080/api/not-found
~~~

Status dự kiến `404 Not Found`. Boot error handler mặc định có thể thêm JSON/HTML body theo Accept và cấu hình error attributes; đừng phụ thuộc chính xác vào body nếu chưa tùy biến.

**Ví dụ log do filter in ra** (thời gian thay đổi theo máy):

~~~text
GET /api/annotated/42 -> 200 (ON_COMPLETE, 3 ms)
GET /api/functional/42 -> 200 (ON_COMPLETE, 2 ms)
GET /api/annotated/fail -> 400 (ON_COMPLETE, 4 ms)
~~~

Các giá trị ms ở trên chỉ minh họa; không phải stdout cố định. `ON_COMPLETE` là tín hiệu của filter chain sau khi response đã được xử lý; lỗi controller đã được advice chuyển thành response 400 nên chain có thể hoàn tất bình thường.

## 12. Kiểm thử HTTP integration với JUnit 5

Không chỉ unit test method controller: một HTTP integration test kiểm chứng route được mapping, adapter gọi đúng handler, result handler ghi đúng response và filter/server chain tham gia.

**src/test/java/com/example/dispatch/DispatchIntegrationTest.java**

~~~java
package com.example.dispatch;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class DispatchIntegrationTest {

    @Value("${local.server.port}")
    int port;

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + path))
            .GET()
            .build();

        return HttpClient.newHttpClient().send(
            request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void annotatedControllerIsDispatchedAndWrittenAsJson()
            throws Exception {
        HttpResponse<String> response = get("/api/annotated/42");

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"id\":\"42\""));
        assertTrue(response.body().contains("\"name\":\"Item 42\""));
    }

    @Test
    void functionalEndpointUsesTheSameHttpPipeline()
            throws Exception {
        HttpResponse<String> response = get("/api/functional/42");

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"id\":\"42\""));
        assertTrue(response.body().contains("\"name\":\"Item 42\""));
    }

    @Test
    void controllerAdviceMapsReactiveHandlerError()
            throws Exception {
        HttpResponse<String> response = get("/api/annotated/fail");

        assertEquals(400, response.statusCode());
        assertTrue(response.body().contains("invalid item"));
    }

    @Test
    void unmappedPathReturnsNotFound() throws Exception {
        HttpResponse<String> response = get("/api/not-found");

        assertEquals(404, response.statusCode());
    }
}
~~~

Test dùng `java.net.http.HttpClient` có sẵn từ JDK 11 nên không phụ thuộc API test client cụ thể. `RANDOM_PORT` khởi chạy server thật trên cổng ngẫu nhiên; test kiểm tra HTTP status và JSON body. Khi chạy:

~~~bash
mvn test
~~~

Nếu test fail, kiểm tra log startup trước khi kết luận dispatcher lỗi: port không mở, dependency server thiếu, mapping xung đột hoặc response codec có thể là nguyên nhân khác nhau.

## 13. Những lỗi thường gặp khi debug dispatch

| Triệu chứng | Nơi nên kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Route trả 404 dù controller có annotation | Component scan, `RequestMappingHandlerMapping`, path/base path | Kiểm tra package scan, HTTP method, path và điều kiện mapping. |
| Route functional không chạy | Bean `RouterFunction`, `RouterFunctionMapping`, order | Đảm bảo bean được đăng ký và không bị mapping trước shadow. |
| Functional và annotated route trùng URL | Thứ tự HandlerMapping | Tránh duplicate; nếu cần, cấu hình order rõ. |
| Handler được tìm thấy nhưng lỗi khi invoke | HandlerAdapter, argument resolver, validation, controller | Kiểm tra `supports`, kiểu tham số, body reader và lỗi method. |
| Controller trả Mono nhưng response treo | Publisher không phát/không complete, service I/O | Kiểm tra timeout, subscription, backpressure, remote dependency; không block. |
| JSON không ghi được | HandlerResultHandler, `HttpMessageWriter`, codec/classpath | Kiểm tra return type, content type, Jackson/codec và response đã commit chưa. |
| `@ControllerAdvice` không bắt lỗi filter | Lỗi trước handler selection | Dùng `WebExceptionHandler` phù hợp. |
| Exception xuất hiện sau khi stream đã gửi một phần | Response đã commit | Thiết kế stream error protocol; không kỳ vọng đổi status/body đã gửi. |
| Static resource không tìm thấy | `SimpleUrlHandlerMapping`, resource location | Kiểm tra classpath `/static`, resource pattern và cấu hình resource. |
| WebFlux chạy như MVC ngoài dự kiến | Dependencies và Boot web application type | Tránh thêm cả `spring-boot-starter-web` nếu muốn reactive server; nếu cố ý dùng cả hai, cấu hình application type rõ. |
| Event-loop bị chậm | Blocking trong handler/service/filter | Dùng reactive client/driver hoặc offload blocking nguồn đúng cách; đo event-loop latency. |
| Filter không chạy theo thứ tự mong muốn | `Ordered`, `@Order`, Security filter chain | Kiểm tra toàn bộ filter order và security chain. |
| 406/415 dù endpoint tồn tại | `produces`, `consumes`, `Accept`, `Content-Type` | Đối chiếu media type với mapping và codec. |
| HandlerResultHandler không hỗ trợ return value | Kiểu return và result handler `supports` | Trả kiểu WebFlux được hỗ trợ hoặc thêm result handler có contract cụ thể. |

### 13.1. Debug theo đúng tầng

Đừng sửa controller ngay khi thấy HTTP 404. Lần lượt kiểm tra:
1. Server có nhận request không?
2. Filter nào có thể dừng request trước dispatcher?
3. Mapping nào được hỏi và có trả handler không?
4. Handler được chọn thuộc kiểu nào; adapter nào support?
5. Adapter resolve argument và invoke có thành công không?
6. HandlerResult có return value/type như mong đợi không?
7. Result handler nào support và writer/codec nào được chọn?
8. Response đã commit chưa; exception handler nào xử lý lỗi?

Đặt breakpoint hoặc log ở đúng contract giúp tìm nguyên nhân nhanh hơn việc bật log quá rộng cho toàn framework.

## 14. Tùy biến mà không phá pipeline

**Thường nên bắt đầu bằng các extension point cấp cao:**
- `WebFluxConfigurer`: codecs, CORS, formatters, view resolver, path matching và API versioning.
- `WebFilter`: cross-cutting concern cho mọi request.
- `@ControllerAdvice`: exception/validation cho annotated controller.
- `RouterFunction`: route functional cho một nhóm endpoint.
- `WebExceptionHandler`: lỗi ở cấp WebHandler chain.
- Custom `HandlerMapping`/`HandlerAdapter`/`HandlerResultHandler`: chỉ khi cần loại handler/return contract mới.

Không tự tạo `DispatcherHandler` bean khác khi Boot đã cấu hình sẵn, trừ khi hiểu đầy đủ hạ tầng và có mục tiêu thay thế cụ thể. Nhiều bean trùng có thể làm thay đổi mapping/adapter order hoặc khiến request đi sai handler.

### 14.1. WebFlux Config và `@EnableWebFlux`

| Cách cấu hình | Phù hợp |
| --- | --- |
| Spring Boot starter + `WebFluxConfigurer` | Giữ auto-configuration, chỉ tùy biến codec/CORS/format... |
| `@EnableWebFlux` | Tự kiểm soát WebFlux infrastructure và không muốn Boot mặc định cấu hình thay mình |
| Custom special beans | Cần mapping/adapter/result contract mới, đã hiểu order/lifecycle |

Nếu cần một handler global để ghi correlation ID, hãy ưu tiên filter. Nếu cần thay cách serialize JSON, hãy cấu hình codec/writer. Đừng viết lại DispatcherHandler cho một nhu cầu có extension point nhỏ hơn.

## 15. Reactive execution, backpressure và cancellation ở giai đoạn dispatch

DispatcherHandler điều phối Publisher chứ không biến code đồng bộ thành non-blocking. Một controller có thể trả `Mono<Item>` nhưng bên trong gọi JDBC đồng bộ hoặc `Thread.sleep`; khi đó request vẫn bị block ở thread thực thi method. Hãy dùng reactive repository/WebClient hoặc bridge legacy blocking bằng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` với giới hạn tải.

`HandlerResultHandler` ghi `Flux<T>` theo writer phù hợp. Khi client chậm, backpressure và network flow control ảnh hưởng tốc độ ghi. Với streaming response:
- Đặt timeout và cleanup phù hợp.
- Xử lý cancel khi client disconnect.
- Không giữ buffer vô hạn.
- Đừng coi việc client mất kết nối là rollback của business operation.
- Nếu response đã ghi một phần, lỗi tiếp theo thường kết thúc stream/kết nối; không thể gửi lại status code ban đầu.

`Mono<Void>` từ `WebHandler`/`HandlerResultHandler` biểu diễn **quá trình xử lý request/response hoàn tất**. Nó không phải thread đang đợi hoặc một `void` đồng bộ; framework subscribe và theo dõi terminal signal.

## 16. Bảng tổng hợp nhanh

| Câu hỏi | Câu trả lời |
| --- | --- |
| Ai nhận request và điều phối? | `DispatcherHandler` |
| Ai tìm controller/route? | `HandlerMapping` |
| Ai gọi loại handler đã chọn? | `HandlerAdapter` |
| Kết quả invocation được đóng gói ở đâu? | `HandlerResult` |
| Ai ghi body/status hoặc render view? | `HandlerResultHandler` |
| Annotated mapping dùng bean nào? | `RequestMappingHandlerMapping` |
| Functional mapping dùng bean nào? | `RouterFunctionMapping` |
| Annotated method được gọi qua adapter nào? | `RequestMappingHandlerAdapter` |
| Functional handler được gọi qua adapter nào? | `HandlerFunctionAdapter` |
| `Mono<Item>` trong `@RestController` thường được xử lý bởi? | `ResponseBodyResultHandler` |
| `ServerResponse` từ WebFlux.fn được xử lý bởi? | `ServerResponseResultHandler` |
| Filter chung chạy ở đâu? | `WebFilter` trong chain bao quanh `DispatcherHandler` |
| Lỗi trước khi chọn handler? | `WebExceptionHandler`/`DispatchExceptionHandler` phù hợp |
| Lỗi trong controller? | Adapter/`@ExceptionHandler`/`@ControllerAdvice` |
| Không có mapping? | 404 mặc định |
| Server chain hoàn tất bằng kiểu nào? | `Mono<Void>` |

## 17. Bài tập thực hành

**Bài 1 – Trace một request annotated.** Gửi GET `/api/annotated/42`; ghi tên HandlerMapping, HandlerAdapter và HandlerResultHandler được dùng. **Đáp án:** RequestMappingHandlerMapping → RequestMappingHandlerAdapter → ResponseBodyResultHandler.

**Bài 2 – Trace functional endpoint.** Gửi GET `/api/functional/42`; so sánh với Bài 1. **Đáp án:** RouterFunctionMapping → HandlerFunctionAdapter → ServerResponseResultHandler. Cả hai vẫn đi qua DispatcherHandler.

**Bài 3 – Tạo route conflict.** Khai báo cùng path/method trong RouterFunction và annotated controller. Quan sát mapping nào được chọn với order mặc định của Boot. **Đáp án:** RouterFunctionMapping được xếp trước RequestMappingHandlerMapping theo default order được Boot công bố; tránh dựa vào sự trùng route trong ứng dụng thực.

**Bài 4 – Lỗi trước handler.** Tạo một WebFilter phát `Mono.error(...)` trước `chain.filter(exchange)`. Xác định vì sao `@ControllerAdvice` không phải nơi duy nhất bắt lỗi. **Đáp án:** lỗi xảy ra trước khi controller được chọn; cần WebExceptionHandler trong WebHandler chain.

**Bài 5 – Lỗi deferred.** Controller trả `Mono.error(...)`. Thử `@RestControllerAdvice`; so sánh với lỗi được ném trực tiếp trong filter. **Đáp án:** lỗi reactive của handler có thể được xử lý bởi cơ chế exception handler của handler; lỗi filter thuộc WebExceptionHandler chain.

**Bài 6 – Custom codec.** Giảm `maxInMemorySize`, gửi body lớn và quan sát lỗi đọc request. **Đáp án:** HttpMessageReader/codec áp dụng giới hạn; điều chỉnh giới hạn theo yêu cầu nhưng tránh tăng vô hạn.

**Bài 7 – Response streaming.** Trả `Flux<ServerSentEvent<String>>`, ngắt client giữa chừng và theo dõi cancellation/cleanup. **Đáp án:** response subscription có thể bị cancel; cleanup nguồn cần được gắn đúng lifecycle và external side effect vẫn có thể đã chạy.

## 18. Checklist production

- [ ] Tôi hiểu chuỗi `HttpHandler → WebExceptionHandler → WebFilter → DispatcherHandler`.
- [ ] Mỗi route có mapping phù hợp và không bị route khác shadow.
- [ ] Tôi biết mapping nào đứng trước; custom `Ordered` có chủ đích.
- [ ] HandlerAdapter phù hợp loại handler và argument resolver/codecs đã được cấu hình.
- [ ] Return type được HandlerResultHandler phù hợp xử lý; response writer/codec tương ứng tồn tại.
- [ ] Lỗi trước mapping, trong controller và lỗi deferred có đúng exception boundary.
- [ ] Không dùng `@ControllerAdvice` làm global handler cho mọi lỗi filter/dispatch.
- [ ] Không block hoặc tự subscribe trong controller/service/filter.
- [ ] Backpressure, timeout, streaming cancel và cleanup được kiểm thử.
- [ ] Không sửa status/body sau khi response đã commit.
- [ ] WebFlux Boot auto-configuration được giữ nếu chỉ cần tùy biến nhỏ; `@EnableWebFlux` chỉ dùng khi muốn tự kiểm soát hạ tầng.
- [ ] Integration test đi qua HTTP server xác nhận route annotated, functional, error và 404.

## 19. Tài liệu tham khảo chính thức

1. Spring Framework – `DispatcherHandler`: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
2. Spring Framework – WebFlux Reactive Core / `WebHandler` API: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
3. Spring Framework – Functional Endpoints: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
4. Spring Framework – Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
5. Spring Framework Javadoc – `HandlerMapping`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/HandlerMapping.html
6. Spring Framework Javadoc – `HandlerAdapter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/HandlerAdapter.html
7. Spring Framework Javadoc – `HandlerResult` / `HandlerResultHandler`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/HandlerResultHandler.html
8. Spring Framework Javadoc – `WebHttpHandlerBuilder`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/adapter/WebHttpHandlerBuilder.html
9. Spring Boot 4.0 – Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
10. Spring Boot 4.0 – System Requirements: https://docs.spring.io/spring-boot/4.0/system-requirements.html

**Tự kiểm tra cuối:** Khi một request đến `/api/functional/42`, ai tìm route, ai gọi function, ai ghi `ServerResponse`? Nếu request không match mapping thì sao? Nếu controller trả `Mono.error`, exception có thể được xử lý ở đâu? Nếu WebFilter lỗi trước mapping thì dùng cơ chế nào? Khi trả lời được bốn câu hỏi đó, bạn đã hiểu luồng dispatch trung tâm của Spring WebFlux.
