# Mono, Flux và các dạng giá trị trả về trong Spring WebFlux Controller

> **Module:** Spring Framework – reactive · **Chủ đề cha:** Controller. Bài học giải thích cách Spring WebFlux diễn giải giá trị trả về của `@Controller`/`@RestController`: từ `Mono<T>` và `Flux<T>` tới `ResponseEntity`, `HttpHeaders`, `ProblemDetail`, view/model, Server-Sent Events và các kiểu async khác.

## 1. Mục tiêu học tập

1. Phân biệt `Mono<T>` (0..1 giá trị), `Flux<T>` (0..N giá trị) và `Mono<Void>` (chỉ báo hoàn tất).
2. Hiểu vai trò của `@ResponseBody`, `HttpMessageWriter` và `ReactiveAdapterRegistry`.
3. Chọn đúng các dạng `ResponseEntity` theo thời điểm cần quyết định status/header/body.
4. Biết cách trả JSON, NDJSON, SSE, HTML view, `ProblemDetail`, `HttpHeaders` và `Mono<Void>`.
5. Kiểm thử endpoint bằng HTTP integration test, không gọi `block()`/`subscribe()` trong controller.

**Quy tắc:** kiểu trả về diễn đạt cardinality và thời điểm có kết quả; `ResponseEntity` diễn đạt status/header/body; `@ResponseBody` quyết định dữ liệu được ghi vào HTTP response thay vì dùng để tìm view.

## 2. Spring xử lý giá trị trả về ra sao?

Annotated controller được gọi qua `RequestMappingHandlerAdapter`. Kết quả invocation được chuyển tới `HandlerResultHandler` phù hợp. Với `@ResponseBody` hoặc `@RestController`, `ResponseBodyResultHandler` phối hợp `HttpMessageWriter` để encode và ghi body. Với `@Controller` trả view/model, `ViewResolutionResultHandler` xử lý view.

~~~text
HTTP request
    |
    v
RequestMappingHandlerMapping
    |
    v
RequestMappingHandlerAdapter
    |
    v
Controller method
    |
    v
HandlerResult
    |
    +-- @ResponseBody → HttpMessageWriter → HTTP body
    |
    +-- String / View / Model → ViewResolver → HTML
~~~

Spring Framework 7.0.8 liệt kê các kiểu return được hỗ trợ trong tài liệu WebFlux. Reactive types như Reactor và RxJava nhìn chung có thể bọc các dạng return value đó; Spring thích ứng chúng qua `ReactiveAdapterRegistry`.

### 2.1. @RestController và @ResponseBody

`@RestController` là composed annotation của `@Controller` và `@ResponseBody`. Vì vậy:

~~~java
@RestController
class GreetingController {
    @GetMapping("/greeting")
    String greeting() {
        return "Hello WebFlux";
    }
}
~~~

HTTP body là `Hello WebFlux`; Spring không tìm template có tên đó. Với `@Controller` thuần, `String` thường là logical view name:

~~~java
@Controller
class PageController {
    @GetMapping("/home")
    String home() {
        return "home";
    }
}
~~~

Muốn method trong `@Controller` trả body trực tiếp, đánh dấu `@ResponseBody` ở method hoặc class.

## 3. Mono và Flux: chọn theo số lượng giá trị

### 3.1. Mono<T>: không có hoặc một giá trị

`Mono<T>` biểu diễn một kết quả bất đồng bộ có 0 hoặc 1 `onNext`, sau đó complete; hoặc phát error.

~~~java
@GetMapping("/items/{id}")
Mono<Item> findOne(@PathVariable String id) {
    return repository.findById(id);
}
~~~

- Có item: downstream nhận một `Item`.
- Không có item: `Mono.empty()` complete mà không có body.
- Có lỗi: `Mono.error(...)` đi vào exception handling.

**`Mono.empty()` không tự động có nghĩa HTTP 404.** Nếu nghiệp vụ muốn 404, chuyển empty thành `ResponseEntity.notFound()` hoặc exception được map sang 404.

~~~java
Mono<ResponseEntity<Item>> findExplicit(String id) {
    return repository.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

### 3.2. Flux<T>: không hoặc nhiều giá trị

`Flux<T>` biểu diễn một chuỗi 0..N phần tử. Nó phù hợp danh sách, stream sự kiện và kết quả truy vấn nhiều bản ghi.

~~~java
@GetMapping("/items")
Flux<Item> findAll() {
    return repository.findAll();
}
~~~

Với `application/json`, nhiều phần tử có thể được encode thành JSON array; WebFlux xử lý phần tử khi chúng đến, không mặc định thu thập toàn bộ Flux vào List.

~~~java
@GetMapping(value = "/items.ndjson",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
Flux<Item> streamNdjson() {
    return repository.findAll();
}
~~~

`application/x-ndjson` biểu diễn mỗi object JSON trên một dòng.

### 3.3. Mono<Void>: chỉ cần hoàn tất

`Mono<Void>` thường dùng cho thao tác không trả dữ liệu:

~~~java
@DeleteMapping("/items/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
Mono<Void> delete(@PathVariable String id) {
    return repository.deleteById(id);
}
~~~

`@ResponseStatus(NO_CONTENT)` xác định status 204; `Mono<Void>` cho biết thời điểm thao tác hoàn tất.

## 4. Bảng cardinality

| Kiểu | Cardinality | Ý nghĩa |
| --- | --- | --- |
| `Item` | Một giá trị đồng bộ | Object có sẵn khi method return. |
| `Mono<Item>` | 0..1 | Một kết quả có thể đến sau. |
| `Flux<Item>` | 0..N | Nhiều phần tử có thể ghi dần. |
| `Mono<Void>` | 0 giá trị, terminal signal | Chỉ cần biết công việc complete/error. |
| `List<Item>` | Một collection đồng bộ | Toàn bộ list đã có trong memory. |
| `Mono<List<Item>>` | Một collection async | Đợi gom list rồi mới phát một giá trị. |
| `CompletableFuture<Item>` | Một kết quả async | Adapter hỗ trợ khi có trên classpath. |
| Kotlin `Flow<Item>` | 0..N | Dòng dữ liệu kiểu coroutine. |

Không dùng `collectList()` cho stream lớn hoặc vô hạn: nó chuyển `Flux<T>` thành `Mono<List<T>>` và giữ toàn bộ phần tử trong memory.


## 5. ResponseEntity: điều khiển status, header và body

`ResponseEntity<T>` khai báo status, headers và body. `HttpEntity<T>` tương tự nhưng không mang status.

### 5.1. ResponseEntity<T>: mọi thứ có sẵn ngay

~~~java
@GetMapping("/items/42")
ResponseEntity<Item> getItem() {
    Item item = new Item("42", "Keyboard");
    return ResponseEntity.ok()
        .header("X-Source", "catalog")
        .eTag("\"item-42-v1\"")
        .body(item);
}
~~~

### 5.2. ResponseEntity<Mono<T>>: status/header có ngay, body tới sau

~~~java
ResponseEntity<Mono<Item>> asyncBody() {
    return ResponseEntity.ok()
        .header("X-Response-Mode", "body-later")
        .body(repository.findById("42"));
}
~~~

Dùng khi status/header không phụ thuộc kết quả bất đồng bộ nhưng body đến sau. Nếu body Mono empty, status đã chọn vẫn được giữ; Spring không tự đổi 200 thành 404.

### 5.3. Mono<ResponseEntity<T>>: status/header/body quyết định bất đồng bộ

~~~java
Mono<ResponseEntity<Item>> lookup(String id) {
    return repository.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Dùng khi kết quả async quyết định cả status, header và body.

### 5.4. ResponseEntity<Flux<T>>: metadata có ngay, body stream

~~~java
ResponseEntity<Flux<Item>> stream() {
    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(repository.findAll());
}
~~~

### 5.5. Mono<ResponseEntity<Flux<T>>>: metadata async rồi body stream

~~~java
Mono<ResponseEntity<Flux<Item>>> delayedStream() {
    return repository.checkAccess()
        .map(allowed -> allowed
            ? ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_NDJSON)
                .body(repository.findAll())
            : ResponseEntity.status(HttpStatus.FORBIDDEN)
                .<Flux<Item>>build());
}
~~~

### 5.6. So sánh các hình dạng

| Return type | Khi biết status/header? | Khi body có? |
| --- | --- | --- |
| `ResponseEntity<T>` | Ngay | Ngay |
| `ResponseEntity<Mono<T>>` | Ngay | Sau |
| `ResponseEntity<Flux<T>>` | Ngay | Dần dần |
| `Mono<ResponseEntity<T>>` | Sau khi Mono phát | Sau |
| `Mono<ResponseEntity<Flux<T>>>` | Sau | Dần dần sau đó |

Không lồng Publisher tùy tiện; chọn hình dạng đơn giản nhất đáp ứng đúng lúc cần quyết định status/header và cardinality body.

## 6. Các return type khác được WebFlux hỗ trợ

| Kiểu | Ý nghĩa mặc định |
| --- | --- |
| `@ResponseBody` | Encode qua `HttpMessageWriter` và ghi response body. |
| `HttpEntity<B>`, `ResponseEntity<B>` | Headers và body; ResponseEntity có thêm status. |
| `HttpHeaders` | Trả headers, không có body. |
| `ErrorResponse`, `ProblemDetail` | Error response theo RFC 9457. |
| `String` | `@Controller`: view name; `@ResponseBody`: body. |
| `View` | Render một View với model. |
| `Map`, `Model` | Attributes của implicit model, view name thường suy ra từ request path. |
| `@ModelAttribute` | Đưa một model attribute vào model. |
| `Rendering` | Builder cho model/view rendering. |
| `FragmentsRendering`, `Flux<Fragment>`, `Collection<Fragment>` | Render nhiều HTML fragments. |
| `void` | Response đã xử lý, body rỗng hoặc default view tùy ngữ cảnh. |
| `Flux<ServerSentEvent<T>>` | Phát Server-Sent Events. |
| Kiểu khác | Thường là model attribute; simple type có thể không được resolve. |

### 6.1. HttpHeaders

~~~java
@GetMapping("/metadata")
HttpHeaders metadata() {
    HttpHeaders headers = new HttpHeaders();
    headers.setCacheControl(CacheControl.noStore());
    headers.set("X-Api-Version", "1");
    return headers;
}
~~~

Nếu cần status tùy chỉnh, dùng `ResponseEntity<Void>`.

### 6.2. ErrorResponse và ProblemDetail

~~~java
@GetMapping("/invalid")
Mono<Item> invalid() {
    return Mono.error(new IllegalArgumentException("Invalid item id"));
}

@RestControllerAdvice
class ApiExceptionHandler {
    @ExceptionHandler(IllegalArgumentException.class)
    ProblemDetail handleInvalid(IllegalArgumentException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST, exception.getMessage());
        problem.setTitle("Invalid request");
        problem.setProperty("errorCode", "ITEM_INVALID");
        return problem;
    }
}
~~~

Khi lỗi xảy ra trước response commit, exception handler có thể chuyển lỗi thành ProblemDetail và status 400. Nếu stream đã ghi một phần body, server không thể thay status hoặc ghi một response lỗi mới từ đầu.

### 6.3. String, View, Map và Model

~~~java
@Controller
class PageController {
    @GetMapping("/dashboard")
    String dashboard(Model model) {
        model.addAttribute("title", "Dashboard");
        return "dashboard";
    }

    @GetMapping("/report")
    Rendering report() {
        return Rendering.view("report")
            .modelAttribute("title", "Monthly report")
            .build();
    }
}
~~~

Trong `@Controller`, String là view name; trong `@RestController`, String là body. Map/Model trong HTML controller thêm model attributes; trong RestController, chúng thường được serialize thành JSON.

### 6.4. HTML fragments

`FragmentsRendering`, `Flux<Fragment>` và `Collection<Fragment>` render một hoặc nhiều HTML fragment, mỗi fragment có view và model riêng. Dùng cho server-rendered UI composition, không dùng cho JSON REST thông thường.

### 6.5. void và Mono<Void>

`void`, `Mono<Void>` hoặc `null` có thể được xem là response đã xử lý nếu method có `ServerHttpResponse`, `ServerWebExchange`, `@ResponseStatus`, hoặc positive ETag/Last-Modified check. Nếu không, `void` có thể nghĩa body rỗng trong REST controller hoặc default view trong HTML controller.

~~~java
@DeleteMapping("/items/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
Mono<Void> delete(@PathVariable String id) {
    return repository.deleteById(id);
}
~~~

### 6.6. Ghi response thủ công

~~~java
@GetMapping("/manual")
Mono<Void> manual(ServerHttpResponse response) {
    byte[] bytes = "done".getBytes(StandardCharsets.UTF_8);
    DataBuffer buffer = response.bufferFactory().wrap(bytes);
    response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
    return response.writeWith(Mono.just(buffer));
}
~~~

Đây là fragment cần imports Spring/Reactor. Không vừa tự ghi response vừa return một body khác.

## 7. SSE và streaming response

### 7.1. ServerSentEvent<T>

~~~java
@GetMapping(value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<String>> events() {
    return Flux.just(
        ServerSentEvent.<String>builder()
            .id("1").event("created").data("Item created").build(),
        ServerSentEvent.<String>builder()
            .id("2").event("updated").data("Item updated").build()
    );
}
~~~

SSE dùng `text/event-stream`. `ServerSentEvent` có thể chứa `id`, `event`, `retry`, `comment`, `data`. Nếu chỉ cần data, có thể bỏ wrapper:

~~~java
@GetMapping(value = "/messages",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<String> messages() {
    return Flux.just("first", "second", "third");
}
~~~

Client gửi `Accept: text/event-stream` hoặc mapping khai báo `produces`.

~~~bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/api/returns/events
~~~

SSE phù hợp push một chiều. Nếu cần hai chiều, cân nhắc WebSocket.

### 7.2. NDJSON và JSON stream

| Media type | Mô hình ghi | Dùng khi |
| --- | --- | --- |
| `application/json` | JSON object/array, Flux có thể ghi dần | API JSON thông thường. |
| `application/x-ndjson` | Mỗi object JSON trên một dòng | Xử lý từng record. |
| `text/event-stream` | SSE event | Push event tới browser. |
| `application/json+stream` | Ghi/flush từng giá trị | JSON stream liên tục. |

WebFlux mặc định xử lý phần tử Flux khi chúng đến, không gom toàn bộ stream thành List. Với media type streaming, giá trị có thể được ghi và flush riêng; cách flush cụ thể phụ thuộc writer/media type.

### 7.3. Lỗi khi stream đã bắt đầu

Nếu Flux đã ghi 20 phần tử rồi phần tử tiếp theo lỗi encode JSON, response có thể đã commit; server không thể đổi status 200 thành 500 và ghi ProblemDetail mới.

Nếu cần gom kết quả trước khi bắt đầu response:

~~~java
Mono<List<Item>> allItems = repository.findAll().collectList();
~~~

`collectList()` đổi Flux thành Mono<List> và giữ toàn bộ dữ liệu trong memory trước khi phát list. Tốn RAM và tăng time-to-first-byte; không dùng cho stream lớn/vô hạn.

### 7.4. Backpressure và client chậm

- Client chậm có thể làm tốc độ tiêu thụ giảm.
- Buffer, codec và connection vẫn dùng tài nguyên.
- Không dùng `collectList()` cho dữ liệu vô hạn.
- Đặt timeout/deadline và giới hạn kích thước.
- Client disconnect có thể cancel subscription; upstream cần cleanup.
- Không gọi `block()` để chờ stream trong controller.


## 8. ReactiveAdapterRegistry và các kiểu async khác

Spring không chỉ hiểu Reactor. `ReactiveAdapterRegistry` thích ứng nhiều loại async/reactive value thành Reactive Streams Publisher để WebFlux xử lý thống nhất. Các adapter mặc định phụ thuộc classpath, có thể bao gồm:
- Reactor `Mono`/`Flux`.
- Java `CompletableFuture` và `java.util.concurrent.Flow.Publisher`.
- RxJava 3.
- Kotlin Coroutines (`Deferred`, `Flow`, suspending functions) khi có dependency.
- SmallRye Mutiny khi thư viện tương ứng có trên classpath.
- Reactive type khác nếu ứng dụng đăng ký adapter.

**Không giả định adapter tồn tại nếu chưa thêm dependency.**

### 8.1. CompletableFuture

~~~java
@GetMapping("/future")
CompletableFuture<Item> future() {
    return CompletableFuture.completedFuture(
        new Item("f-1", "Future item"));
}
~~~

Đây là kết quả async đơn. Spring có thể adapt CompletableFuture khi registry có adapter phù hợp. `supplyAsync` mặc định dùng common ForkJoinPool; trong ứng dụng thật hãy chọn executor phù hợp cho tác vụ CPU/blocking và quản lý lifecycle.

### 8.2. RxJava và Mutiny

Nếu ứng dụng đã dùng RxJava hoặc Mutiny, các kiểu được adapter hỗ trợ có thể trả trực tiếp từ controller. Không nên trộn nhiều reactive library trong cùng module nếu không có lợi ích rõ ràng; mỗi library có semantics riêng về cardinality, cancellation, scheduler và error.

### 8.3. Kotlin Coroutines: suspend và Flow

Spring WebFlux hỗ trợ Kotlin suspending functions và `Flow` trong annotated controllers. Cần `kotlinx-coroutines-core` và `kotlinx-coroutines-reactor`.

~~~kotlin
@RestController
@RequestMapping("/api/kotlin")
class KotlinItemController(private val service: ItemService) {

    @GetMapping("/{id}")
    suspend fun one(@PathVariable id: String): Item =
        service.findOne(id)

    @GetMapping
    fun all(): Flow<Item> =
        service.findAll()
}
~~~

Mapping khái niệm:
- `Mono<Void>` → `suspend fun handler()`.
- `Mono<T>` → `suspend fun handler(): T` hoặc `T?` nếu có thể empty.
- `Flux<T>` → `fun handler(): Flow<T>`.
- `Flow<T>` tương tự Flux về cardinality, nhưng backpressure được biểu diễn qua suspension thay vì Reactive Streams request trực tiếp.

Đây là fragment Kotlin, không nằm trong project Java thực hành.

### 8.4. Raw Publisher và cardinality không rõ

Nếu trả về `org.reactivestreams.Publisher<T>` mà không có adapter cụ thể diễn đạt cardinality, Spring có thể xem nó như stream 0..N. Nếu biết nguồn chỉ có tối đa một phần tử, hãy chuyển rõ:

~~~java
Mono<Item> one = Mono.from(rawPublisher);
Flux<Item> many = Flux.from(rawPublisher);
~~~

`Mono.from(Publisher)` lấy tối đa một giá trị; `Flux.from(Publisher)` giữ semantics nhiều giá trị. Chọn wrapper đúng để writer hiểu đúng cardinality.

## 9. Chọn return type theo nhu cầu

| Nhu cầu | Return type phù hợp | Lý do |
| --- | --- | --- |
| Một object có sẵn | `Item` hoặc `ResponseEntity<Item>` | Đơn giản, status/header rõ. |
| Một object từ reactive repository | `Mono<Item>` | 0..1, non-blocking. |
| Không tìm thấy cần 404 | `Mono<ResponseEntity<Item>>` | Quyết định status sau kết quả async. |
| Thao tác xóa không body | `Mono<Void>` + `@ResponseStatus(NO_CONTENT)` | Chỉ cần complete. |
| Nhiều bản ghi | `Flux<Item>` | Phát từng phần tử, không gom List mặc định. |
| Snapshot nhỏ, đầy đủ | `Mono<List<Item>>` | Đợi đủ dữ liệu rồi serialize collection. |
| Header cố định, body đến sau | `ResponseEntity<Mono<Item>>` | Metadata có ngay. |
| Status phụ thuộc service | `Mono<ResponseEntity<Item>>` | Quyết định toàn response sau async call. |
| Stream với header cố định | `ResponseEntity<Flux<Item>>` | Metadata có trước, body stream sau. |
| Event stream cho browser | `Flux<ServerSentEvent<T>>` | SSE có id/event/data. |
| Một dòng JSON mỗi record | `Flux<T>` + `application/x-ndjson` | Client xử lý line-by-line. |
| Lỗi có cấu trúc | `ProblemDetail` / `ErrorResponse` | RFC 9457. |
| Render template HTML | `String`, `View`, `Rendering`, `Model` trong `@Controller` | View resolution. |
| HTML fragments | `FragmentsRendering` / `Flux<Fragment>` | Render nhiều fragment. |
| Một future từ SDK | `CompletableFuture<T>` hoặc `Mono<T>` | Adapter xử lý async result. |

**Chọn theo contract trước, cú pháp sau.** Đừng trả Flux chỉ vì service đang dùng Flux nếu endpoint cần snapshot nhỏ; cũng đừng `collectList()` chỉ để controller trông giống Spring MVC khi dữ liệu thực sự là stream lớn.

## 10. Lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `Flux<T>` cho một kết quả | Contract cardinality không rõ | Dùng `Mono<T>`. |
| Dùng `Mono<T>` nhưng thực tế có nhiều kết quả | Chỉ lấy tối đa một giá trị | Dùng `Flux<T>`. |
| Nghĩ `Mono.empty()` tự tạo HTTP 404 | API trả 200 rỗng ngoài ý muốn | Map empty thành `ResponseEntity.notFound()` hoặc exception. |
| Nghĩ `Mono<Void>` chứa null | Sai semantics Reactive Streams | Dùng `Mono<Void>` cho complete/error. |
| Dùng String trong `@Controller` và mong text body | Spring hiểu thành view name | Thêm `@ResponseBody` hoặc dùng `@RestController`. |
| Dùng Map trong `@Controller` và mong JSON | Map trở thành model attributes | Dùng `@ResponseBody` hoặc `@RestController`. |
| Dùng `ResponseEntity<Mono<T>>` khi status phụ thuộc kết quả | Status/header được chọn quá sớm | Dùng `Mono<ResponseEntity<T>>`. |
| Dùng `Mono<ResponseEntity<T>>` khi cần nhiều giá trị | Body cardinality không đúng | Dùng `Mono<ResponseEntity<Flux<T>>>` hoặc `ResponseEntity<Flux<T>>`. |
| `collectList()` cho stream lớn/vô hạn | Tăng RAM, mất streaming | Trả `Flux<T>` với media type phù hợp. |
| Nghĩ Flux JSON đợi đủ dữ liệu | Bỏ lỡ response có thể commit trước khi lỗi | Hiểu streaming và xử lý error trước khi ghi nếu cần. |
| Trả SSE mà không khai báo `text/event-stream` | Content negotiation/codec sai | Dùng `produces` hoặc Accept đúng. |
| Trả raw Publisher không rõ cardinality | Spring có thể xem là 0..N | Bọc `Mono.from` hoặc `Flux.from`. |
| Gọi `block()` trong controller | Có thể khóa event-loop | Compose Publisher và return cho framework. |
| Gọi `subscribe()` trong controller để tự ghi body | Tách lifecycle và lỗi khỏi request | Return Mono/Flux cho framework. |
| Nghĩ reactive type làm JDBC tự non-blocking | Vẫn block thread | Dùng reactive driver hoặc offload blocking source. |
| Trả null từ reactive chain | `onNext(null)` không hợp lệ | Dùng `Mono.empty()` hoặc `Mono.just(value)`. |

## 11. Cách debug khi response không như mong đợi

1. **Annotation:** method thuộc `@RestController` hay `@Controller`? Có `@ResponseBody` không?
2. **Cardinality:** method trả Mono, Flux, collection hay object đồng bộ? Source có empty/error không?
3. **Response shape:** status/header có phụ thuộc async result không? Chọn ResponseEntity tương ứng.
4. **Content negotiation:** kiểm tra Accept, produces, Content-Type.
5. **Codec:** HttpMessageWriter nào encode body? Jackson/codec có hỗ trợ type không?
6. **Streaming:** body có lỗi sau khi một phần đã gửi? Client đọc JSON array, NDJSON hay SSE?
7. **Lifecycle:** Publisher có complete không? Có `Mono.never()`/Flux vô hạn? Client disconnect có cancel source không?
8. **Blocking:** có block(), JDBC, Thread.sleep hoặc SDK blocking trong request path không?
9. **Exception:** lỗi xảy ra trước hay sau khi response commit? Có @ExceptionHandler phù hợp?
10. **HTTP test:** kiểm tra status, headers, body, media type và cancellation bằng test tích hợp.

## 12. Checklist production

- [ ] Return type phản ánh đúng cardinality: Mono cho 0..1, Flux cho 0..N.
- [ ] `@RestController`/`@ResponseBody` dùng đúng khi muốn ghi body; `@Controller` dùng cho view/model.
- [ ] Empty result có status contract rõ; không giả định empty tự thành 404.
- [ ] ResponseEntity có hình dạng phù hợp thời điểm quyết định status/header/body.
- [ ] Media type khai báo qua produces/Accept; codec hỗ trợ body type.
- [ ] Streaming có timeout, backpressure, cancellation và cleanup.
- [ ] Lỗi sau commit được xử lý theo stream protocol; không mong đổi status/body đã gửi.
- [ ] collectList chỉ dùng khi kích thước có giới hạn và buffer là chủ đích.
- [ ] ProblemDetail/ErrorResponse có status phù hợp, không lộ stack trace.
- [ ] Không gọi block()/subscribe() trong controller/service request path.
- [ ] Blocking library được thay bằng reactive API hoặc offload có giới hạn.
- [ ] Async adapter chỉ dùng khi dependency và adapter có sẵn.
- [ ] Integration test kiểm tra status, headers, body, media type, empty/error và SSE/stream.

## 13. Bài tập thực hành

**Bài 1 – Cardinality.** Viết ba endpoint trả Item, Mono<Item> và Flux<Item>. Thử trường hợp không tìm thấy dữ liệu; giải thích vì sao Mono.empty() không tự thành 404.

**Bài 2 – Chọn ResponseEntity.** Viết ResponseEntity<Mono<Item>> và Mono<ResponseEntity<Item>>. Cho repository trả empty; quan sát method nào quyết định 404 sau khi biết kết quả.

**Bài 3 – Mono<Void>.** Viết endpoint DELETE trả Mono<Void> với @ResponseStatus(NO_CONTENT). Kiểm tra status 204 và body rỗng.

**Bài 4 – Flux JSON và NDJSON.** Trả cùng Flux bằng application/json và application/x-ndjson. Viết client đọc từng phần tử; so sánh parser và flush.

**Bài 5 – SSE.** Trả Flux<ServerSentEvent<Item>> có id/event/data. Mở curl -N, ngắt client giữa chừng và kiểm tra upstream cleanup.

**Bài 6 – Lỗi khi stream.** Tạo Flux phát hai item rồi error. So sánh với collectList; chú ý RAM và time-to-first-byte.

**Bài 7 – Kotlin.** Chuyển Mono<Item> thành suspend fun one(): Item? và Flux<Item> thành Flow<Item>. Ghi dependency coroutines.

**Bài 8 – View và REST.** Tạo @Controller trả String và @RestController trả cùng String. Giải thích vì sao một bên resolve view còn bên kia ghi body.

## 14. Tài liệu tham khảo chính thức

1. Spring Framework 7.0.8 – Controller Return Values: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
2. Spring Framework – ResponseEntity: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html
3. Spring Framework – @ResponseBody: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html
4. Spring Framework – Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
5. Spring Framework – Reactive Core, codecs và streaming: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
6. Spring Framework – Kotlin Coroutines: https://docs.spring.io/spring-framework/reference/languages/kotlin/coroutines.html
7. Spring Framework – ReactiveAdapterRegistry Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ReactiveAdapterRegistry.html
8. Spring Boot – Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html

**Tự đánh giá:** Khi repository trả Mono.empty(), API có tự trả 404 không? Khi status phụ thuộc dữ liệu async, chọn ResponseEntity<Mono<T>> hay Mono<ResponseEntity<T>>? Vì sao Flux có thể commit response trước khi một phần tử lỗi encode? @RestController thay đổi ý nghĩa String ra sao?


## 9. Ví dụ Java 17+ chạy được với Spring Boot 4.0.9

Project minh họa các dạng return: `Item`, `Mono<Item>`, `Flux<Item>`, NDJSON, empty, `Mono<Void>`, các hình dạng `ResponseEntity`, `HttpHeaders`, `CompletableFuture`, SSE và `ProblemDetail`.

### 9.1. Cấu trúc dự án

~~~text
webflux-return-types/
├── pom.xml
├── src/main/java/com/example/returns/ReturnTypesApplication.java
├── src/main/java/com/example/returns/Item.java
├── src/main/java/com/example/returns/ItemController.java
├── src/main/java/com/example/returns/ApiExceptionHandler.java
└── src/test/java/com/example/returns/ReturnTypesIntegrationTest.java
~~~

### 9.2. pom.xml

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
    <artifactId>webflux-return-types</artifactId>
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

### 9.3. ReturnTypesApplication.java

~~~java
package com.example.returns;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReturnTypesApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReturnTypesApplication.class, args);
    }
}
~~~

### 9.4. Item.java

~~~java
package com.example.returns;

public record Item(String id, String name) {}
~~~

### 9.5. ItemController.java

~~~java
package com.example.returns;

import java.util.concurrent.CompletableFuture;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/returns")
public class ItemController {

    private Item item(String id) {
        return new Item(id, "Item " + id);
    }

    @GetMapping("/direct/{id}")
    public Item direct(@PathVariable String id) {
        return item(id);
    }

    @GetMapping("/mono/{id}")
    public Mono<Item> mono(@PathVariable String id) {
        return Mono.just(item(id));
    }

    @GetMapping("/flux")
    public Flux<Item> flux() {
        return Flux.just(item("1"), item("2"));
    }

    @GetMapping(value = "/ndjson",
                produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Item> ndjson() {
        return Flux.just(item("1"), item("2"));
    }

    @GetMapping("/empty")
    public Mono<Item> empty() {
        return Mono.empty();
    }

    @GetMapping("/void")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public Mono<Void> noContent() {
        return Mono.empty();
    }

    @GetMapping("/string")
    public String stringBody() {
        return "plain text";
    }

    @GetMapping("/headers")
    public HttpHeaders headers() {
        HttpHeaders headers = new HttpHeaders();
        headers.setCacheControl(CacheControl.noStore());
        headers.set("X-Api-Version", "1");
        return headers;
    }

    @GetMapping("/entity")
    public ResponseEntity<Item> entity() {
        return ResponseEntity.ok()
            .header("X-Response-Mode", "immediate")
            .body(item("entity"));
    }

    @GetMapping("/entity-async")
    public Mono<ResponseEntity<Item>> entityAsync() {
        return Mono.just(
            ResponseEntity.accepted().body(item("async-entity")));
    }

    @GetMapping("/body-async")
    public ResponseEntity<Mono<Item>> bodyAsync() {
        return ResponseEntity.ok()
            .header("X-Response-Mode", "body-later")
            .body(Mono.just(item("async-body")));
    }

    @GetMapping(value = "/entity-stream",
                produces = MediaType.APPLICATION_NDJSON_VALUE)
    public ResponseEntity<Flux<Item>> entityStream() {
        return ResponseEntity.ok()
            .header("X-Response-Mode", "stream")
            .contentType(MediaType.APPLICATION_NDJSON)
            .body(Flux.just(item("stream-1"), item("stream-2")));
    }

    @GetMapping(value = "/sse",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Item>> sse() {
        return Flux.just(
            ServerSentEvent.<Item>builder()
                .id("1").event("created").data(item("sse-1")).build(),
            ServerSentEvent.<Item>builder()
                .id("2").event("updated").data(item("sse-2")).build()
        );
    }

    @GetMapping("/future")
    public CompletableFuture<Item> future() {
        return CompletableFuture.completedFuture(item("future"));
    }

    @GetMapping("/problem")
    public Mono<Item> problem() {
        return Mono.error(new IllegalArgumentException("Invalid item"));
    }
}
~~~

### 9.6. ApiExceptionHandler.java

~~~java
package com.example.returns;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    public ProblemDetail invalidItem(IllegalArgumentException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST, exception.getMessage());
        problem.setTitle("Invalid request");
        problem.setProperty("errorCode", "ITEM_INVALID");
        return problem;
    }
}
~~~

### 9.7. ReturnTypesIntegrationTest.java

Test dùng `java.net.http.HttpClient` có sẵn trong JDK 17. `RANDOM_PORT` khởi động server thật; test đi qua HTTP connector, mapping, return value handling và message writer.

~~~java
package com.example.returns;

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
class ReturnTypesIntegrationTest {

    @Value("${local.server.port}")
    int port;

    private HttpResponse<String> get(String path, String accept)
            throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(
            URI.create("http://localhost:" + port + path))
            .GET();

        if (accept != null) {
            builder.header("Accept", accept);
        }

        return HttpClient.newHttpClient().send(
            builder.build(),
            HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void directAndMonoValuesBecomeJson() throws Exception {
        HttpResponse<String> direct = get(
            "/api/returns/direct/7", "application/json");
        HttpResponse<String> mono = get(
            "/api/returns/mono/7", "application/json");

        assertEquals(200, direct.statusCode());
        assertEquals(200, mono.statusCode());
        assertTrue(direct.body().contains("\"id\":\"7\""));
        assertTrue(mono.body().contains("\"name\":\"Item 7\""));
    }

    @Test
    void fluxWritesMultipleJsonValues() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/flux", "application/json");

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"id\":\"1\""));
        assertTrue(response.body().contains("\"id\":\"2\""));
    }

    @Test
    void ndjsonUsesStreamingMediaType() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/ndjson", "application/x-ndjson");

        assertEquals(200, response.statusCode());
        assertTrue(response.headers()
            .firstValue("Content-Type").orElse("")
            .startsWith("application/x-ndjson"));
        assertTrue(response.body().contains("\"id\":\"1\""));
        assertTrue(response.body().contains("\"id\":\"2\""));
    }

    @Test
    void emptyMonoHasNoBodyAndNoAutomaticNotFound() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/empty", "application/json");

        assertEquals(200, response.statusCode());
        assertTrue(response.body().isEmpty());
    }

    @Test
    void monoVoidCanRepresentNoContent() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/void", "application/json");

        assertEquals(204, response.statusCode());
        assertTrue(response.body().isEmpty());
    }

    @Test
    void stringInRestControllerIsResponseBody() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/string", "text/plain");

        assertEquals(200, response.statusCode());
        assertEquals("plain text", response.body());
    }

    @Test
    void httpHeadersReturnHasNoBody() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/headers", "application/json");

        assertEquals(200, response.statusCode());
        assertEquals("1", response.headers()
            .firstValue("X-Api-Version").orElseThrow());
        assertTrue(response.body().isEmpty());
    }

    @Test
    void responseEntitySetsStatusHeadersAndBody() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/entity", "application/json");

        assertEquals(200, response.statusCode());
        assertEquals("immediate", response.headers()
            .firstValue("X-Response-Mode").orElseThrow());
        assertTrue(response.body().contains("\"id\":\"entity\""));
    }

    @Test
    void monoResponseEntityCanChooseStatusAsynchronously()
            throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/entity-async", "application/json");

        assertEquals(202, response.statusCode());
        assertTrue(response.body().contains("async-entity"));
    }

    @Test
    void responseEntityMonoBodyKeepsImmediateHeaders()
            throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/body-async", "application/json");

        assertEquals(200, response.statusCode());
        assertEquals("body-later", response.headers()
            .firstValue("X-Response-Mode").orElseThrow());
        assertTrue(response.body().contains("async-body"));
    }

    @Test
    void responseEntityFluxBodyStreamsNdjson() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/entity-stream", "application/x-ndjson");

        assertEquals(200, response.statusCode());
        assertEquals("stream", response.headers()
            .firstValue("X-Response-Mode").orElseThrow());
        assertTrue(response.body().contains("stream-1"));
        assertTrue(response.body().contains("stream-2"));
    }

    @Test
    void serverSentEventsUseEventStreamContentType() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/sse", "text/event-stream");

        assertEquals(200, response.statusCode());
        assertTrue(response.headers()
            .firstValue("Content-Type").orElse("")
            .startsWith("text/event-stream"));
        assertTrue(response.body().contains("created"));
        assertTrue(response.body().contains("data:"));
    }

    @Test
    void completableFutureIsAdaptedToAsyncResponse() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/future", "application/json");

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"id\":\"future\""));
    }

    @Test
    void problemDetailIsReturnedForReactiveError() throws Exception {
        HttpResponse<String> response = get(
            "/api/returns/problem", "application/problem+json");

        assertEquals(400, response.statusCode());
        assertTrue(response.body().contains("Invalid item"));
        assertTrue(response.body().contains("ITEM_INVALID"));
    }
}
~~~

### 9.8. Chạy ứng dụng

Yêu cầu JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Ứng dụng mặc định nghe ở cổng 8080. Request thử:

~~~bash
curl -i http://localhost:8080/api/returns/mono/7
curl -i http://localhost:8080/api/returns/flux
curl -i -H "Accept: application/x-ndjson" http://localhost:8080/api/returns/ndjson
curl -i http://localhost:8080/api/returns/empty
curl -i http://localhost:8080/api/returns/entity-async
curl -i -H "Accept: text/event-stream" http://localhost:8080/api/returns/sse
curl -i -H "Accept: application/problem+json" http://localhost:8080/api/returns/problem
~~~

**Kết quả chính cần quan sát:**

| Endpoint | Status | Body/headers |
| --- | ---: | --- |
| `/mono/7` | 200 | JSON object của Item 7 |
| `/flux` | 200 | JSON có hai Item |
| `/ndjson` | 200 | `application/x-ndjson`, hai dòng JSON |
| `/empty` | 200 | Body rỗng, không tự thành 404 |
| `/void` | 204 | Body rỗng |
| `/string` | 200 | `plain text` |
| `/headers` | 200 | `X-Api-Version: 1`, body rỗng |
| `/entity-async` | 202 | ResponseEntity được quyết định async |
| `/body-async` | 200 | Header có ngay, body Mono ghi sau |
| `/entity-stream` | 200 | NDJSON nhiều phần tử |
| `/sse` | 200 | `text/event-stream` |
| `/future` | 200 | JSON từ CompletableFuture |
| `/problem` | 400 | ProblemDetail JSON |

Trong SSE test, event có thể được encode thành các dòng `id:`, `event:` và `data:`; spacing/thứ tự phụ thuộc encoder. Test kiểm tra media type và nội dung thay vì toàn bộ byte output.
