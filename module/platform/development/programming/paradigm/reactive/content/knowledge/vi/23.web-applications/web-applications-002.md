# Controller và handler trả về Mono hoặc Flux

Trong ứng dụng Spring WebFlux, controller hoặc handler thường trả về `Mono<T>` hay `Flux<T>` thay vì chờ một đối tượng rồi trả ngay. Publisher trở thành phần thân của quá trình xử lý HTTP: framework đăng ký subscription, nhận tín hiệu dữ liệu, ghi response và quản lý việc hủy khi client ngắt kết nối. Cách thiết kế này giúp request đi qua một pipeline reactive thống nhất từ tầng web tới service và repository.

`Mono` phù hợp với response có tối đa một kết quả hoặc chỉ biểu diễn hoàn tất. `Flux` phù hợp với nhiều phần tử, đặc biệt khi muốn phát dữ liệu theo luồng. Tuy nhiên, kiểu trả về chỉ mô tả số phần tử; nó không tự quyết định status HTTP, content type, cách mã hóa body hay việc response có được stream hay không. Controller cần kết hợp publisher với hợp đồng HTTP một cách rõ ràng.

## 1. Controller trả Mono cho một kết quả

Một endpoint đọc theo ID thường trả tối đa một đối tượng:

```java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<OrderView>> findById(@PathVariable String id) {
        return orderService.findById(id)
            .map(OrderView::from)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
```

Service trả `Mono<Order>`. Controller chuyển payload thành `OrderView`, bọc thành HTTP 200 và ánh xạ trường hợp publisher hoàn tất rỗng thành HTTP 404. Framework subscribe vào publisher khi xử lý request; controller không cần gọi `subscribe()`.

Một endpoint tạo tài nguyên có thể trả `Mono<ResponseEntity<OrderView>>` để xác định status và header sau khi có kết quả:

```java
@PostMapping
Mono<ResponseEntity<OrderView>> create(@RequestBody Mono<CreateOrder> body) {
    return body
        .flatMap(orderService::create)
        .map(OrderView::from)
        .map(view -> ResponseEntity
            .created(URI.create("/orders/" + view.id()))
            .body(view));
}
```

Body request cũng là publisher. Dùng `flatMap` để nối dữ liệu request với thao tác tạo đơn hàng; toàn bộ quy trình chỉ được thực thi trong subscription do framework quản lý. Nếu request body không hợp lệ hoặc service phát lỗi, lỗi được chuyển tới cơ chế xử lý lỗi của WebFlux.

## 2. Khi nào dùng Mono, Flux và Mono<Void>?

Chọn kiểu publisher theo hợp đồng dữ liệu của endpoint:

| Kiểu trả về | Ý nghĩa thường gặp | Ví dụ HTTP |
| --- | --- | --- |
| `Mono<T>` | Tối đa một payload | Lấy một đơn hàng hoặc một hồ sơ |
| `Mono<Void>` | Chỉ báo hoàn tất hoặc lỗi, không có payload | Xóa tài nguyên hoặc ghi nhận một thao tác |
| `Flux<T>` | Không, một hoặc nhiều payload | Danh sách, feed hoặc luồng sự kiện |
| `Mono<ResponseEntity<T>>` | Một payload cùng status/header được quyết định bất đồng bộ | 200, 201, 404 tùy kết quả |
| `ResponseEntity<Flux<T>>` | Status/header có sẵn, body là một luồng nhiều phần tử | Streaming endpoint với metadata cố định |

Ví dụ xóa tài nguyên:

```java
@DeleteMapping("/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
Mono<Void> delete(@PathVariable String id) {
    return orderService.delete(id);
}
```

`Mono<Void>` hoàn tất bình thường thì WebFlux trả HTTP 204 theo `@ResponseStatus`; nếu publisher phát lỗi, cơ chế xử lý lỗi sẽ quyết định response phù hợp. Không dùng `map` để tạo body từ `Mono<Void>` vì nguồn không phát `onNext`. Nếu cần trả một payload xác nhận, dùng `thenReturn` hoặc trả một kiểu kết quả cụ thể.

## 3. Phân biệt empty completion với lỗi HTTP

`Mono.empty()` là hoàn tất bình thường không có payload. Nó không tự động có nghĩa là 404. Controller hoặc handler phải quyết định empty biểu diễn điều gì trong hợp đồng HTTP:

```java
@GetMapping("/{id}/summary")
Mono<ResponseEntity<SummaryView>> summary(@PathVariable String id) {
    return summaryService.find(id)
        .map(SummaryView::from)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

Nếu empty có nghĩa tài nguyên không tồn tại, ánh xạ sang 404 là hợp lý. Nếu empty có nghĩa truy vấn thành công nhưng không có nội dung, endpoint có thể dùng 204 hoặc một response rỗng theo hợp đồng. Nếu nguồn phát `onError`, hãy chuyển lỗi thành status phù hợp qua `@ExceptionHandler`, `@RestControllerAdvice` hoặc `onErrorMap` ở tầng nghiệp vụ.

Không dùng `onErrorResume(error -> Mono.empty())` một cách tổng quát để biến lỗi thành 404. Làm vậy che mất lỗi hệ thống như timeout hoặc database unavailable và khiến client hiểu nhầm rằng tài nguyên không tồn tại. Chỉ chuyển một loại lỗi cụ thể khi nghiệp vụ xác định rõ cách ánh xạ.

## 4. Controller trả Flux cho nhiều phần tử

Một endpoint danh sách có thể trả `Flux<T>` trực tiếp:

```java
@GetMapping
Flux<OrderView> findRecent() {
    return orderService.findRecent()
        .map(OrderView::from);
}
```

Framework tiêu thụ các phần tử của `Flux` và ghi response theo content negotiation cùng codec được chọn. Với nguồn hữu hạn, response có thể được mã hóa thành JSON array. Với nguồn dài hạn hoặc cần gửi từng phần tử khi có dữ liệu, hãy chọn media type hỗ trợ streaming như NDJSON hoặc Server-Sent Events.

Không nên gọi `collectList()` chỉ để biến mọi `Flux` thành một danh sách trước khi trả response. Việc thu thập buộc ứng dụng giữ toàn bộ phần tử cho tới khi nguồn hoàn tất, làm tăng bộ nhớ và trì hoãn byte đầu tiên. Chỉ thu thập khi endpoint thực sự có hợp đồng trả một collection hữu hạn và kích thước đã được giới hạn hợp lý.

## 5. Streaming bằng NDJSON hoặc Server-Sent Events

NDJSON gửi mỗi đối tượng JSON trên một dòng. Đây là lựa chọn phù hợp cho feed dữ liệu một chiều:

```java
@GetMapping(value = "/events", produces = MediaType.APPLICATION_NDJSON_VALUE)
Flux<EventView> events() {
    return eventService.stream()
        .map(EventView::from);
}
```

Server-Sent Events (SSE) gửi các sự kiện theo định dạng SSE qua HTTP. Có thể trả `Flux<ServerSentEvent<T>>`:

```java
@GetMapping(value = "/notifications", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<NotificationView>> notifications() {
    return notificationService.streamForCurrentUser()
        .map(notification -> ServerSentEvent.builder(
                NotificationView.from(notification))
            .id(notification.id())
            .event("notification")
            .build());
}
```

`text/event-stream` cho client biết response là luồng sự kiện. Có thể thêm `id`, `event`, `retry` hoặc comment heartbeat theo nhu cầu. Với nguồn không kết thúc như stream notification, kết nối HTTP có thể được giữ mở lâu; cần xác định timeout, heartbeat, xác thực, giới hạn kết nối và cách client reconnect.

`Flux<T>` không tự bảo đảm dữ liệu được gửi từng phần ngay lập tức. Cách encode và flush phụ thuộc media type, codec và server adapter. Dùng NDJSON hoặc SSE khi muốn hợp đồng streaming rõ ràng; kiểm thử bằng client thực tế để xác minh từng phần tử đến trước khi nguồn hoàn tất.

## 6. ResponseEntity và thời điểm commit response

Có hai kiểu tổ chức response thường gặp:

```java
// Chờ publisher tạo metadata và body trước khi tạo ResponseEntity.
Mono<ResponseEntity<OrderView>> oneOrder(String id) {
    return service.findById(id)
        .map(order -> ResponseEntity.ok(OrderView.from(order)))
        .defaultIfEmpty(ResponseEntity.notFound().build());
}

// Metadata được xác định trước; body tiếp tục phát nhiều phần tử.
ResponseEntity<Flux<EventView>> eventFeed() {
    Flux<EventView> body = eventService.stream().map(EventView::from);
    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(body);
}
```

Với `Mono<ResponseEntity<T>>`, status và header có thể phụ thuộc vào kết quả publisher trước khi response được tạo. Với `ResponseEntity<Flux<T>>`, metadata được xác định ngay, còn body tiếp tục được subscribe và ghi sau đó.

Khi body đã bắt đầu được gửi và response đã commit, lỗi xảy ra ở giữa luồng thường không thể đổi status HTTP thành 500 hoặc gửi một response JSON lỗi mới. Kết nối có thể bị đóng hoặc stream kết thúc theo cách transport hỗ trợ. Vì vậy, hãy xác thực và thực hiện các bước có thể thất bại trước khi commit response nếu cần trả lỗi HTTP chuẩn; với stream dài hạn, xác định giao thức biểu diễn lỗi trong chính luồng hoặc yêu cầu client reconnect.

## 7. Functional endpoints cũng trả publisher

Spring WebFlux hỗ trợ functional routing với `RouterFunction` và `HandlerFunction`. Handler trả `Mono<ServerResponse>`; body có thể là `Mono<T>` hoặc `Flux<T>`:

```java
@Bean
RouterFunction<ServerResponse> orderRoutes(OrderHandler handler) {
    return RouterFunctions.route()
        .GET("/functional/orders/{id}", handler::findById)
        .GET("/functional/events", handler::events)
        .build();
}

class OrderHandler {
    private final OrderService service;

    OrderHandler(OrderService service) {
        this.service = service;
    }

    Mono<ServerResponse> findById(ServerRequest request) {
        String id = request.pathVariable("id");
        return service.findById(id)
            .flatMap(order -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(OrderView.from(order)))
            .switchIfEmpty(ServerResponse.notFound().build());
    }

    Mono<ServerResponse> events(ServerRequest request) {
        Flux<EventView> body = service.streamEvents()
            .map(EventView::from);
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_NDJSON)
            .body(body, EventView.class);
    }
}
```

Functional endpoint vẫn dùng cùng nguyên tắc: handler trả publisher cho framework; không tự subscribe. `ServerResponse` mô tả status, header và body. `bodyValue` phù hợp với một giá trị đã có; `body(publisher, elementClass)` phù hợp với body reactive.

## 8. Giữ controller mỏng và compose ở tầng service

Controller nên tập trung vào HTTP: đọc path/query/header/body, gọi service, ánh xạ DTO và chọn status/content type. Quy tắc nghiệp vụ, phối hợp nhiều nguồn và xử lý lỗi miền nên nằm trong service để có thể tái sử dụng và kiểm thử độc lập.

```java
@GetMapping("/{id}/details")
Mono<ResponseEntity<OrderDetailsView>> details(@PathVariable String id) {
    return orderService.loadDetails(id)
        .map(OrderDetailsView::from)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

Service có thể dùng `Mono.zip`, `flatMap`, timeout hoặc fallback để tổng hợp dữ liệu. Controller không cần biết các bước nội bộ đó. Nếu service trả `Mono<Void>`, controller có thể gắn `@ResponseStatus` hoặc chuyển thành `ResponseEntity<Void>` nếu status/header phụ thuộc vào kết quả.

Không tạo subscription mới trong controller bằng `subscribe()`. Khi controller tự subscribe, framework không thể chờ kết quả, quản lý lỗi, gắn response với vòng đời publisher hoặc truyền cancellation khi client ngắt kết nối. Luôn trả publisher cho framework.

## 9. Xử lý lỗi tập trung

Có thể ánh xạ lỗi miền nghiệp vụ thành response bằng `@RestControllerAdvice`:

```java
@RestControllerAdvice
class ApiErrorHandler {
    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> notFound(OrderNotFoundException error) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError("ORDER_NOT_FOUND", error.getMessage()));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ApiError> badRequest(IllegalArgumentException error) {
        return ResponseEntity.badRequest()
            .body(new ApiError("INVALID_REQUEST", error.getMessage()));
    }
}
```

WebFlux hỗ trợ exception handler đồng bộ và reactive. Nếu cần thực hiện thêm công việc reactive để tạo response lỗi, handler có thể trả `Mono<ResponseEntity<ApiError>>`. Hãy ánh xạ loại lỗi cụ thể và tránh để chi tiết nội bộ như SQL, token hoặc stack trace lộ ra response công khai.

Lỗi xảy ra trước khi response commit có thể được ánh xạ thành status và body theo cơ chế exception handling. Lỗi phát sinh khi đang stream body cần được xử lý riêng vì header/status có thể đã gửi. Với SSE, một số ứng dụng có thể biểu diễn lỗi miền nghiệp vụ thành một event có kiểu rõ ràng trước khi kết thúc stream; lỗi transport hoặc lỗi không phục hồi vẫn có thể đóng kết nối.

## 10. Validation và body request reactive

Body request có thể được nhận dưới dạng một đối tượng hoặc publisher. Khi dùng `Mono<CreateOrder>`, có thể nối validation và service bằng `flatMap`:

```java
@PostMapping
Mono<ResponseEntity<OrderView>> create(
        @Valid @RequestBody Mono<CreateOrder> command) {
    return command
        .flatMap(orderService::create)
        .map(OrderView::from)
        .map(view -> ResponseEntity
            .created(URI.create("/orders/" + view.id()))
            .body(view));
}
```

Codec giải mã body thành đối tượng và lỗi giải mã/validation được chuyển thành tín hiệu lỗi theo cấu hình WebFlux. Với request body lớn hoặc dạng streaming, có thể nhận `Flux<T>` nếu định dạng và codec hỗ trợ; cần xác định giới hạn kích thước, cách xử lý phần tử lỗi và việc có chấp nhận xử lý từng phần trước khi toàn body hợp lệ hay không.

Không dùng `collectList()` cho body streaming lớn chỉ để thuận tiện nếu nghiệp vụ không cần toàn bộ collection cùng lúc. Việc gom toàn bộ body làm tăng bộ nhớ và có thể tạo điểm nghẽn. Nếu phải xác thực toàn bộ trước khi tạo tác dụng phụ, hãy dùng giới hạn kích thước rõ ràng hoặc cơ chế staging phù hợp.

## 11. Cancellation gắn với vòng đời HTTP request

Khi client ngắt kết nối hoặc framework không còn cần body, subscription của response có thể bị hủy. Cancellation truyền qua pipeline tới publisher nguồn và các inner publisher theo khả năng hỗ trợ của chúng. Đây là lý do controller nên trả publisher thay vì tự subscribe: framework có thể gắn vòng đời xử lý với request.

Cancellation không bảo đảm mọi công việc bên dưới dừng tức thời. Một API blocking không hỗ trợ interrupt có thể tiếp tục chạy trên worker thread; một dịch vụ ngoài có thể đã nhận request trước khi cancellation đến. Với streaming, hãy giải phóng listener, cursor hoặc subscription tới broker khi downstream cancel. Với tác vụ blocking, cấu hình timeout ở chính client và cô lập trên scheduler phù hợp.

Có thể dùng `doFinally` để ghi nhận kết thúc subscription:

```java
@GetMapping(value = "/events", produces = MediaType.APPLICATION_NDJSON_VALUE)
Flux<EventView> events() {
    return eventService.stream()
        .map(EventView::from)
        .doFinally(signal -> metrics.recordStreamTermination(signal));
}
```

Hook này phù hợp cho metric/log complete, error hoặc cancel. Nếu cần giải phóng tài nguyên, hãy bảo đảm nguồn hoặc service dùng cơ chế cleanup như `using`/`usingWhen`; không dùng hook quan sát thay cho cleanup bất đồng bộ.

## 12. Không chặn event loop

Controller WebFlux nên giữ các bước xử lý non-blocking. Không gọi `.block()`, JDBC đồng bộ hoặc thư viện blocking trực tiếp trên event-loop thread:

```java
// Tránh gọi trực tiếp trong controller WebFlux.
Order order = blockingJdbcRepository.findById(id);
```

Nếu chưa thể thay thư viện blocking, bọc lời gọi bằng `Mono.fromCallable` và chuyển nguồn sang `boundedElastic` ở tầng adapter:

```java
Mono<Order> findBlocking(String id) {
    return Mono.fromCallable(() -> blockingJdbcRepository.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

Controller chỉ gọi service reactive như bình thường. Hãy giới hạn concurrency và cấu hình timeout cho thư viện blocking; `boundedElastic` cô lập thread bị chặn chứ không biến API đồng bộ thành non-blocking.

## 13. Kiểm thử controller bằng WebTestClient

`WebTestClient` kiểm thử hợp đồng HTTP của WebFlux mà không cần tự subscribe vào publisher của controller:

```java
@WebFluxTest(OrderController.class)
class OrderControllerTest {
    @Autowired
    WebTestClient client;

    @MockBean
    OrderService orderService;

    @Test
    void returnsOrderWhenFound() {
        given(orderService.findById("42"))
            .willReturn(Mono.just(new Order("42", "PAID")));

        client.get()
            .uri("/orders/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody(OrderView.class)
            .value(view -> assertEquals("42", view.id()));
    }

    @Test
    void returnsNotFoundWhenPublisherIsEmpty() {
        given(orderService.findById("missing"))
            .willReturn(Mono.empty());

        client.get()
            .uri("/orders/missing")
            .exchange()
            .expectStatus().isNotFound();
    }
}
```

Với streaming endpoint, kiểm tra content type và nhiều phần tử body. Nếu cần xác minh dữ liệu được gửi từng phần trước khi nguồn hoàn tất, dùng nguồn test điều khiển được thời điểm phát và tiêu thụ response theo streaming API của `WebTestClient`; chỉ kiểm tra một JSON array cuối cùng chưa chứng minh response thực sự stream.

Ở tầng service, dùng `StepVerifier` để kiểm tra `Mono`/`Flux` về giá trị, lỗi, complete và cancellation. Kết hợp test service với test HTTP giúp phân biệt lỗi trong pipeline nghiệp vụ với lỗi ánh xạ status, header hoặc codec.

## 14. Chọn kiểu trả về theo hợp đồng HTTP

| Yêu cầu endpoint | Kiểu trả về gợi ý | Điều cần quyết định |
| --- | --- | --- |
| Tìm một tài nguyên | `Mono<T>` hoặc `Mono<ResponseEntity<T>>` | Empty là 404, 204 hay response khác? |
| Tạo tài nguyên | `Mono<ResponseEntity<T>>` | Status 201, `Location` và body |
| Xóa hoặc thao tác không payload | `Mono<Void>` | Status thành công và cách ánh xạ lỗi |
| Trả danh sách hữu hạn | `Flux<T>` hoặc `Mono<List<T>>` | Stream phần tử hay cố ý gom thành collection? |
| Feed sự kiện liên tục | `Flux<T>` với NDJSON/SSE | Reconnect, timeout, heartbeat và cancellation |
| Functional endpoint | `Mono<ServerResponse>` | Status, header và body publisher |

Hãy để controller hoặc handler mô tả hợp đồng HTTP và trả publisher cho framework sở hữu subscription. Dùng `Mono` cho một kết quả hoặc completion-only, `Flux` cho nhiều phần tử; chọn media type và codec để xác định cách body được gửi; ánh xạ empty và error theo ý nghĩa nghiệp vụ; và giữ các thao tác blocking ở adapter có scheduler phù hợp. Khi response, subscription và vòng đời request được nối với nhau đúng cách, ứng dụng WebFlux có thể xử lý I/O bất đồng bộ mà vẫn giữ status, lỗi, cancellation và backpressure trong một pipeline nhất quán.
