# Thời điểm đăng ký, hủy và truyền ngữ cảnh trong chuỗi xử lý

Trong **Spring Security OAuth 2.0 / OIDC Resource Server** viết bằng **Spring WebFlux**, một HTTP request không được xử lý theo đúng mô hình “mỗi request có một thread cố định từ đầu đến cuối”. Thay vào đó, ứng dụng xây dựng các chuỗi xử lý phản ứng (**reactive pipelines**) gồm `Mono`, `Flux`, các `WebFilter`, bước xác thực Bearer Access Token, phân quyền, truy vấn dữ liệu và ghi response.

Ba khái niệm quyết định tính đúng đắn của thiết kế:

1. **Subscription — thời điểm đăng ký:** Khi nào một Publisher thực sự được đăng ký để chạy? Điều gì chỉ mới được *mô tả* khi Java gọi method mà chưa được thực thi?
2. **Cancellation — hủy đăng ký:** Điều gì xảy ra nếu browser ngắt kết nối, request bị timeout hoặc một operator không còn cần dữ liệu? Làm sao dọn tài nguyên, giữ trạng thái giao dịch và không gây side effect ngoài dự kiến?
3. **Context propagation — truyền ngữ cảnh:** SecurityContext chứa principal và authorities của request được truyền qua các operator, scheduler, reactive database hoặc `WebClient` như thế nào khi không thể giả định một thread duy nhất?

Những khái niệm này ảnh hưởng trực tiếp đến bảo mật: một `Authentication` bị đọc sai thời điểm có thể trở thành `null`, một tác vụ chạy ngoài subscription có thể bỏ qua kiểm soát quyền, còn một request bị hủy không bảo đảm thao tác ghi trước đó được hoàn tác.

Bài học dùng **Java 17+, Spring Boot 3.x, Spring Framework 6.x, Spring Security 6.x, Reactor 3.x** và **WebFlux Resource Server nhận JWT Bearer Access Token**. Các ví dụ sử dụng domain đơn hàng minh họa; nếu phiên bản dự án khác, cần đối chiếu API cụ thể. Trọng tâm là **subscription, cancellation và Reactor Context trong chuỗi xử lý bảo mật**, không phải cấu hình OAuth 2.0 Authorization Server.

## 1. Bức tranh xử lý một HTTP request WebFlux

Giả sử client gọi:

~~~http
GET /api/orders/8a4f...
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
Accept: application/json
~~~

Trong WebFlux, request có thể đi theo luồng:

~~~text
Client / browser
       |
       | HTTP request + Bearer Access Token
       v
Reactive HTTP server (ví dụ Reactor Netty)
       |
       v
WebFilter chain
       |
       +-- Reactor/WebFlux context setup
       +-- Bearer authentication
       |      +-- JWT decoder / validators
       |      +-- Authentication: JwtAuthenticationToken
       |
       +-- HTTP authorization
       |      +-- SCOPE_orders.read?
       |
       v
Handler / Controller trả Mono<OrderDto>
       |
       v
Service / reactive repository / WebClient
       |
       +-- Domain authorization: owner / tenant?
       +-- Data access: Mono / Flux
       |
       v
Encode response -> HTTP client
~~~

Sơ đồ trên mô tả **các trách nhiệm** chứ không có nghĩa tất cả bước chạy trên một thread, hoặc chúng chạy ngay khi code Java khai báo đối tượng `Mono`.

| Thành phần | Trách nhiệm | Ranh giới cần chú ý |
| --- | --- | --- |
| `SecurityWebFilterChain` | Cấu hình các WebFlux security filters, Bearer auth và rules. | Chỉ bảo vệ các exchanges phù hợp với chain. |
| Reactive authentication | Kiểm tra Access Token và tạo `Authentication`. | Token sai không trở thành principal hợp lệ. |
| Reactor `Publisher` | Mô tả tín hiệu `onNext`, `onComplete`, `onError`. | Công việc thường bắt đầu khi **subscribe**. |
| `Subscriber` / subscription | Tiêu thụ dữ liệu, quản lý demand/cancel. | Có thể hủy khi request không còn cần dữ liệu. |
| `Reactor Context` | Mang metadata ở mức subscription. | Không đồng nhất với `ThreadLocal` hoặc HTTP headers. |
| `ReactiveSecurityContextHolder` | Đọc/ghi SecurityContext theo Reactor Context. | Phụ thuộc subscriber context của chuỗi hiện tại. |
| Reactive I/O | R2DBC/`WebClient`/streaming response. | Cancel propagation và transaction phải được thiết kế. |

## 2. Từ assembly đến subscription: hai thời điểm khác nhau

Trong Reactor, nhiều `Mono` và `Flux` là **cold publishers**: lời gọi method chỉ **tạo mô tả một chuỗi xử lý**; thao tác bên trong thường được thực hiện khi có subscriber.

### 2.1. Assembly: xây chuỗi xử lý

~~~java
Mono<String> pipeline = Mono.just("order-42")
    .map(id -> {
        System.out.println("Đang xử lý " + id);
        return id.toUpperCase();
    });

System.out.println("Đã tạo pipeline");
~~~

Ở thời điểm tạo `pipeline`, lambda trong `map` chưa nhất thiết chạy. Với ví dụ cold publisher này, kết quả trên console trước subscription chỉ là:

~~~text
Đã tạo pipeline
~~~

Vì **không có subscriber yêu cầu dữ liệu**, operator `map` chưa có lý do phát `onNext`.

### 2.2. Subscription: bắt đầu thực hiện chuỗi

~~~java
pipeline.subscribe(value ->
    System.out.println("Nhận kết quả: " + value));
~~~

Khi subscribe, publisher bắt đầu phát tín hiệu:

~~~text
Đang xử lý order-42
Nhận kết quả: ORDER-42
~~~

Nếu subscribe **lần thứ hai** vào cùng cold pipeline, các lambda có thể được thực thi **lần nữa**:

~~~java
pipeline.subscribe(System.out::println);
pipeline.subscribe(System.out::println);
~~~

Đây là điểm rất quan trọng với nghiệp vụ. Một Publisher dùng cho ghi database hoặc gọi HTTP **không thể mặc định xem là thao tác “chỉ thực hiện đúng một lần”** nếu có nhiều subscription hoặc retry. Tính **idempotent** và thiết kế side effect phải được xử lý độc lập.

### 2.3. Không phải mọi thứ đều lazy

Cần phân biệt:

~~~java
// value được tính trước khi Mono.just được gọi.
Mono<String> eager =
    Mono.just(expensiveSynchronousCalculation());

// Hàm được gọi lúc subscription.
Mono<String> lazy =
    Mono.fromCallable(() -> expensiveSynchronousCalculation());

// Publisher được tạo tại thời điểm subscription.
Mono<String> deferred =
    Mono.defer(() -> service.fetchName());
~~~

Trong ví dụ:

- `Mono.just(value)` giữ **giá trị đã có**; biểu thức tạo `value` có thể chạy ngay lúc assembly.
- `Mono.fromCallable(...)` trì hoãn một thao tác đồng bộ đến subscription.
- `Mono.defer(...)` trì hoãn **việc tạo Publisher** đến subscription, giúp lấy thông tin mới cho từng subscriber.

Nếu `expensiveSynchronousCalculation()` là hàm blocking, `Mono.fromCallable` **không tự làm thao tác trở thành non-blocking**; nó chỉ đổi thời điểm gọi. Với thư viện blocking bắt buộc phải dùng, cần cô lập hợp lý trên scheduler như `Schedulers.boundedElastic()` và cân nhắc timeout, giới hạn concurrency. Tốt hơn là dùng reactive driver/API khi có thể.

### 2.4. Hot publishers và shared publishers khác cold publishers

Không được khẳng định **mọi Publisher đều bắt đầu từ đầu khi subscribe**. Hot publisher, `Sinks.Many`, `share()`, một số cách `cache()` hoặc một nguồn sự kiện ngoài có thể phát trước hoặc chia sẻ dữ liệu giữa subscribers.

Trong API có JWT user-specific context, **không nên tự chia sẻ Publisher chứa principal hoặc dữ liệu cá nhân giữa nhiều HTTP requests** nếu chưa thiết kế ranh giới key, cache, expiry và authorization. Cùng một `Mono` hot/shared được dùng sai có thể gây **rò rỉ dữ liệu của request A sang request B**.

## 3. Ai gọi subscribe trong WebFlux?

Với annotated controller hoặc functional router của Spring WebFlux, framework thường là bên **subscribe vào Publisher trả về từ handler** để tạo HTTP response.

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class DemoController {

    @GetMapping("/api/demo")
    Mono<String> demo() {
        return Mono.defer(() -> {
            System.out.println("Executing reactive response");
            return Mono.just("ok");
        });
    }
}
~~~

Controller trả **`Mono<String>`**. WebFlux quản lý subscription, demand, error và cancellation theo HTTP lifecycle.

### 3.1. Không tự gọi subscribe() trong controller/service

Đoạn sau là một lỗi kiến trúc phổ biến:

~~~java
// KHÔNG LÀM.
@PostMapping("/api/orders")
Mono<Void> createOrder(@RequestBody OrderCommand command) {
    orderService.save(command).subscribe();
    return Mono.empty();
}
~~~

Vấn đề:

1. `save(...).subscribe()` khởi chạy **subscription độc lập** với chuỗi request mà WebFlux đang quản lý.
2. Controller có thể trả response thành công **trước khi save hoàn tất**.
3. Lỗi save có thể không đi qua error handling của request.
4. Client ngắt kết nối không nhất thiết hủy được side effect độc lập đó.
5. Reactor Context/SecurityContext của request **không được bảo đảm truyền nguyên vẹn** đến chuỗi được subscribe thủ công.
6. Transaction, tracing và quota/rate-limit có thể bị áp không nhất quán.

Cách đúng là **trả về Publisher biểu diễn toàn bộ công việc**:

~~~java
@PostMapping("/api/orders")
Mono<Void> createOrder(@RequestBody OrderCommand command) {
    return orderService.save(command).then();
}
~~~

WebFlux đăng ký và quản lý subscription của Publisher đó. Nếu cần tạo một background job thật, thiết kế một **hệ thống job/queue độc lập**, có identity/service authorization, audit, retry và lifecycle riêng, thay vì bỏ `subscribe()` tùy ý vào handler.

### 3.2. Dùng flatMap để kết hợp bất đồng bộ

Sai:

~~~java
// KHÔNG LÀM: Mono<Mono<OrderDto>> và không diễn đạt chuỗi
// dữ liệu theo kiểu mong muốn.
Mono<Mono<OrderDto>> nested =
    Mono.just(orderService.findById(orderId));
~~~

Đúng:

~~~java
Mono<OrderDto> result =
    Mono.just(orderId)
        .flatMap(orderService::findById);
~~~

Hoặc trả trực tiếp:

~~~java
return orderService.findById(orderId);
~~~

`map` dùng khi biến đổi giá trị **đồng bộ**; `flatMap` giúp nối với **Publisher bất đồng bộ**. Việc kết hợp các Publishers trong cùng một pipeline giúp duy trì cancellation, error flow và Reactor Context theo thiết kế.

## 4. Subscription và backpressure

Reactive Streams mô tả giao thức giữa Publisher và Subscriber:

~~~text
Subscriber
    |
    | onSubscribe(Subscription)
    | request(n)  -> yêu cầu n phần tử
    | cancel()    -> không muốn nhận tiếp
    v
Publisher
    |
    | onNext(value)
    | onError(error)  hoặc  onComplete()
    v
Subscriber
~~~

Đối với `Mono`, thường phát tối đa một giá trị; `Flux` có thể phát nhiều giá trị. **Backpressure** giúp subscriber biểu đạt nhu cầu thay vì bắt nguồn dữ liệu luôn đẩy vô hạn.

Ví dụ trả danh sách lớn theo luồng:

~~~java
@GetMapping(
    value = "/api/events",
    produces = "text/event-stream")
Flux<EventDto> events() {
    return eventService.streamAuthorizedEvents();
}
~~~

Một nguồn sự kiện có thể tiếp tục tồn tại trong thời gian dài; **cancellation và cleanup** trở nên quan trọng khi browser đóng tab hoặc hủy kết nối. Tuy nhiên, việc tạm dừng/yêu cầu dữ liệu còn phụ thuộc vào driver và nguồn phát. Không giả định bất kỳ API bên ngoài nào cũng hỗ trợ backpressure đầy đủ chỉ vì được bọc bằng `Flux`.

## 5. Ba tín hiệu kết thúc: complete, error và cancel

Trong Reactor có thể xảy ra:

| Tình huống | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Complete** | Publisher hoàn tất bình thường. | Tìm được một bản ghi rồi kết thúc. |
| **Error** | Publisher kết thúc bằng lỗi. | Database lỗi, JWT invalid hoặc access denied được biểu diễn thành error. |
| **Cancel** | Subscriber thông báo không cần tiếp tục. | Browser ngắt request, `take(1)`, `timeout` hủy upstream. |

**Cancellation không phải một `onError`**. Khi cancel, publisher thường không nhận tín hiệu lỗi rồi chạy `onErrorResume` theo cách một exception thông thường xảy ra.

### 5.1. doOnSubscribe và doFinally

~~~java
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

Mono<String> operation = Mono.defer(() -> {
        System.out.println("Bắt đầu công việc tại subscription");
        return Mono.just("done");
    })
    .doOnSubscribe(subscription ->
        System.out.println("Đã đăng ký"))
    .doFinally(signalType ->
        System.out.println("Kết thúc bằng " + signalType));
~~~

`doOnSubscribe` được gọi khi có subscription ở vị trí operator tương ứng. `doFinally` quan sát kết thúc vì:

- `SignalType.ON_COMPLETE`
- `SignalType.ON_ERROR`
- `SignalType.CANCEL`

Không dùng `doOnComplete` để dọn cleanup cho mọi trường hợp, vì nó không chạy khi cancel. `doOnError` cũng không tự chạy chỉ vì subscriber cancel.

### 5.2. doOnCancel và doFinally khác nhau

~~~java
Flux<EventDto> stream = eventService.stream()
    .doOnCancel(() -> metrics.incrementCancellation())
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            metrics.recordClientOrOperatorCancellation();
        }
    });
~~~

`doOnCancel` là hook dành riêng cho cancel tại vị trí operator. `doFinally` quan sát nhiều loại termination và nhận nguyên nhân; callback `doFinally` chạy sau các đường kết thúc theo semantics của operator. Không dựa vào hook để **đảm bảo một giao dịch nghiệp vụ chưa có side effect**, vì hành động có thể đã xảy ra trước khi tín hiệu hủy tới nơi.

### 5.3. timeout có thể chuyển cancel thành error ở downstream

~~~java
Mono<OrderDto> result =
    orderService.load(orderId)
        .doFinally(signal ->
            metrics.recordUpstreamSignal(signal))
        .timeout(Duration.ofSeconds(2))
        .doOnError(TimeoutException.class,
            error -> metrics.recordTimeout());
~~~

Nếu timeout xảy ra, operator `timeout` có thể **cancel upstream** và phát `TimeoutException` cho downstream:

~~~text
Upstream: CANCEL
Downstream: onError(TimeoutException)
~~~

Vì vậy khi log/metrics, phải biết hook được đặt **trước hay sau `timeout`**. Một timeout trong API không có nghĩa thao tác database, remote HTTP hoặc thanh toán đã bị hủy thành công ở phía ngoài.

## 6. Khi nào HTTP request bị hủy?

Trong WebFlux, cancellation có thể xuất hiện khi:

1. Browser đóng tab, rời trang hoặc `AbortController.abort()`.
2. Client ngắt TCP/HTTP stream; server phát hiện kết nối không còn người nhận.
3. Một operator `take(1)`, `firstWithSignal`, `switchMap` không còn cần nguồn cũ.
4. `timeout(...)` quyết định không chờ nguồn upstream.
5. Bên gọi downstream hủy subscription hoặc giới hạn số phần tử.
6. Server shutdown hoặc ứng dụng dừng stream trong những điều kiện phù hợp.

Ví dụ frontend:

~~~javascript
const controller = new AbortController();

const promise = fetch("https://api.example.test/api/orders", {
  headers: {
    Authorization: "Bearer " + accessToken
  },
  signal: controller.signal
});

// Khi người dùng chuyển màn hình:
controller.abort();
~~~

Browser có thể ngừng chờ response; khi server phát hiện disconnect, WebFlux có thể truyền cancellation tới reactive publisher. **Độ nhanh và mức độ propagation phụ thuộc HTTP server, loại I/O, driver và thời điểm sự kiện**. Không nên khẳng định cancel luôn xảy ra ngay hoặc đã đi đến mọi thành phần từ xa.

### 6.1. Cancel không đồng nghĩa rollback mọi side effect

Giả sử request tạo đơn hàng:

~~~text
T0: API bắt đầu INSERT order
T1: Database commit thành công
T2: Browser đóng kết nối
T3: WebFlux thấy cancel, không thể gửi response
T4: Client tưởng thao tác chưa thành công
~~~

Đơn hàng vẫn có thể **đã được tạo** ở T1. Vì vậy:

- Dùng **idempotency key** hoặc cơ chế chống duplicate cho những thao tác tạo giao dịch quan trọng.
- Có endpoint tra trạng thái để client biết kết quả thật sau timeout/cancel.
- Không tự động retry thao tác ghi không idempotent mà không có quy tắc.
- Nếu có giao dịch phân tán, cần cơ chế nghiệp vụ như outbox/saga/compensation phù hợp.

Cancellation là tín hiệu của **demand/lifecycle subscription**, không phải lời hứa “không có thay đổi dữ liệu”.

### 6.2. Cancel với WebClient

~~~java
Mono<InventoryDto> remote = webClient.get()
    .uri("/inventory/{sku}", sku)
    .retrieve()
    .bodyToMono(InventoryDto.class)
    .timeout(Duration.ofSeconds(3));
~~~

Khi downstream cancel, Reactor Netty/`WebClient` có thể hủy chờ response và đóng/hủy hoạt động cục bộ. **Nhưng hệ thống inventory có thể đã nhận request và xử lý xong**; cancel ở client không bảo đảm rollback nghiệp vụ ở server bên kia.

Với HTTP GET thường không có side effect (theo hợp đồng), tác động có thể chỉ là tài nguyên và chi phí I/O. Với POST đến dịch vụ ngoài, phải thiết kế **idempotency, timeout, retry, transaction boundary**.

## 7. Dọn tài nguyên đúng khi cancel

Một pipeline có thể mở:

- Database connection/transaction.
- Streaming subscription đến message broker.
- File handle hoặc stream tải dữ liệu.
- Remote HTTP call.
- Một lock/lease hoặc resource pool slot.

Nếu chỉ cleanup trong `doOnComplete`, request bị cancel có thể giữ tài nguyên lâu hơn dự kiến.

### 7.1. usingWhen cho tài nguyên bất đồng bộ

Reactor cung cấp `usingWhen` để quản lý một tài nguyên với **cleanup không đồng bộ** trên các nhánh complete, error và cancel:

~~~java
import reactor.core.publisher.Mono;

// Giả định các method trả Publisher bất đồng bộ:
// Mono<Lease> acquireLease()
// Mono<OrderDto> readOrder(Lease lease, UUID orderId)
// Mono<Void> releaseLease(Lease lease)

Mono<OrderDto> loadWithLease(UUID orderId) {
    return Mono.usingWhen(
        acquireLease(),
        lease -> readOrder(lease, orderId),
        lease -> releaseLease(lease),             // complete
        (lease, error) -> releaseLease(lease),    // error
        lease -> releaseLease(lease)              // cancel
    );
}
~~~

Các method `acquireLease`, `readOrder`, `releaseLease` và lớp `Lease` là **minh họa cần triển khai**, không phải API có sẵn của Reactor. Điểm cốt lõi là cleanup được biểu diễn bằng **Publisher**, không gọi một thao tác blocking trong callback trên event loop.

Nếu cleanup thất bại, cần chính sách quan sát lỗi và trạng thái hệ thống rõ ràng. Không nuốt lỗi cleanup chỉ để trả một HTTP 200 sai sự thật. Không gọi thao tác release **hai lần** nếu resource lifecycle không idempotent; đảm bảo paths được thiết kế an toàn.

### 7.2. doFinally không thay usingWhen

~~~java
return source
    .doFinally(signal -> {
        logger.debug("Order stream finished: {}", signal);
    });
~~~

`doFinally` phù hợp với metrics, logging và side effects ngắn, **không phù hợp để `block()` chờ đóng một tài nguyên**. Muốn cleanup bất đồng bộ được phối hợp với lifecycle, sử dụng `usingWhen`, Reactive transaction management hoặc API resource tương đương.

### 7.3. R2DBC transaction và cancellation

Với database reactive, Spring quản lý transaction bằng **Reactor Context**, không dựa vào cùng một thread cố định. Một ví dụ:

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

class OrderApplicationService {

    private final OrderRepository orders;
    private final TransactionalOperator tx;

    OrderApplicationService(
            OrderRepository orders, TransactionalOperator tx) {
        this.orders = orders;
        this.tx = tx;
    }

    Mono<OrderEntity> updateNote(UUID id, String newNote) {
        return orders.findById(id)
            .switchIfEmpty(
                Mono.error(new IllegalArgumentException("Not found")))
            .flatMap(order -> {
                order.setNote(newNote);
                return orders.save(order);
            })
            .as(tx::transactional);
    }
}
~~~

Trong ví dụ, `OrderRepository` và `OrderEntity` là những thành phần minh họa. `TransactionalOperator` bao transaction lifecycle quanh Publisher được subscribe. Spring reactive transactions có cơ chế **rollback khi gặp lỗi và xử lý cancellation theo semantics của transaction manager/driver**; tuy vậy không nên kết luận rằng cancel sẽ **luôn** hoàn tác bất kỳ thay đổi nào đã commit.

Một `commit` đã hoàn tất không thể bị đảo ngược chỉ nhờ subscriber gửi cancel. Với thao tác quan trọng, cần thêm **transactional constraints, optimistic locking, idempotency key và audit**.

## 8. Reactor Context là gì?

`Reactor Context` là **dữ liệu gắn với subscriber/subscription**, có tính **immutable** theo mô hình API. Nó giúp truyền thông tin ngữ cảnh đi cùng chuỗi Reactor mà không phụ thuộc vào một thread cố định.

Ví dụ thông tin có thể đưa vào Context:

- Request correlation ID.
- Tracing metadata phù hợp.
- Locale hoặc tenant selection đã được kiểm chứng.
- SecurityContext của Spring Security.
- Reactive transaction context.

Không coi Context là nơi lưu mọi request data hoặc credential một cách tùy tiện. Context có thể được đọc bởi operators trong chuỗi; dữ liệu nhạy cảm cần được giới hạn đúng mục đích, không log/serialize nguyên context.

### 8.1. contextWrite để cung cấp context

~~~java
import reactor.core.publisher.Mono;

Mono<String> publisher =
    Mono.deferContextual(contextView -> {
        String requestId =
            contextView.getOrDefault("requestId", "unknown");
        return Mono.just(requestId);
    })
    .contextWrite(context ->
        context.put("requestId", "req-42"));
~~~

Khi có subscription, `Mono.deferContextual` đọc `requestId` từ Context.

~~~java
publisher.subscribe(System.out::println);
// req-42
~~~

Quan trọng:

- `contextWrite` tạo context mới, không sửa một `Map` toàn cục.
- Trong Reactor, thông tin context **truyền theo chiều từ subscriber lên các operators upstream**. Vị trí đặt `contextWrite` ảnh hưởng operator nào nhìn thấy giá trị.
- `deferContextual` giúp đọc context **ở thời điểm subscribe**, không đọc quá sớm lúc assembly.
- Một Context có thể được ghi đè bằng các `contextWrite` khác; nếu dùng key chung, phải xác định precedence rõ ràng.

### 8.2. Context không giống biến request toàn cục

Ví dụ:

~~~java
Mono<String> base = Mono.deferContextual(
    ctx -> Mono.just(ctx.get("requestId")));

Mono<String> one = base.contextWrite(
    ctx -> ctx.put("requestId", "request-A"));

Mono<String> two = base.contextWrite(
    ctx -> ctx.put("requestId", "request-B"));
~~~

Hai subscribers khác nhau có thể nhận **ngữ cảnh khác nhau** mà không phải sửa một biến static:

~~~text
Subscriber A -> request-A
Subscriber B -> request-B
~~~

Đó là tính chất thiết yếu của mô hình reactive: nhiều HTTP requests có thể được ghép trên cùng ít threads, nhưng không được lẫn principal hoặc correlation ID.

## 9. Reactor Context khác ThreadLocal và SecurityContextHolder

Trong ứng dụng Spring MVC Servlet truyền thống, nhiều developer dùng:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Trong WebFlux, một request có thể chuyển qua nhiều scheduler/threads. **`SecurityContextHolder` dựa vào chiến lược thread-bound truyền thống** không phải cách thích hợp để lấy security context trong reactive pipeline.

Thay vào đó, Spring Security cung cấp:

~~~java
ReactiveSecurityContextHolder.getContext()
~~~

để lấy **`Mono<SecurityContext>`** từ **Reactor Context**.

### 9.1. Vì sao ThreadLocal dễ sai?

~~~text
Request A bắt đầu ở thread-1
    |
    +-- publishOn(scheduler-X)
    |      -> operator tiếp theo chạy ở thread-7
    |
    +-- WebClient -> async callback/thread khác

Request B đồng thời dùng thread-1 hoặc thread-7
~~~

Nếu giữ `currentUser` trong một `ThreadLocal` tự quản lý:

- Operator có thể đọc **không thấy** user khi chuyển thread.
- Một ThreadLocal không được cleanup đúng có nguy cơ giữ **dữ liệu request trước**.
- Một callback chạy ở thread khác có thể thiếu tracing/security context.

Reactor Context đi cùng **subscription**, phù hợp hơn với chuỗi phản ứng. Không chỉ “copy ThreadLocal vào Reactor Context” một cách thủ công ở từng service, vì việc đó có thể đưa dữ liệu sai nguồn vào authorization.

### 9.2. Scheduler chuyển thread nhưng Reactor Context vẫn theo pipeline

~~~java
Mono<String> result =
    Mono.deferContextual(ctx ->
            Mono.just(ctx.<String>get("requestId")))
        .publishOn(Schedulers.parallel())
        .map(id -> "processed:" + id)
        .contextWrite(ctx ->
            ctx.put("requestId", "req-100"));
~~~

`publishOn` thay đổi scheduler thực thi operators phía sau, nhưng **Reactor Context vẫn là ngữ cảnh của subscription** trong chain đó. Điều này khác với ThreadLocal không tự được kế thừa qua mọi thread.

Nếu ứng dụng tích hợp các thư viện chỉ hỗ trợ ThreadLocal (ví dụ MDC logging), có thể cần giải pháp **context propagation** được cấu hình đúng, chẳng hạn Micrometer context-propagation với Reactor; không tự cho rằng MDC luôn được sao chép chính xác.

### 9.3. Không đồng nhất Context với HTTP headers

Bearer token nằm trong HTTP header và được Spring Security authentication filter xử lý. **SecurityContext** sau đó là kết quả đã xác thực mà Spring Security đưa vào reactive context.

Không dùng:

~~~java
String user = request.getHeaders().getFirst("X-User");
~~~

thay cho SecurityContext, vì header do caller kiểm soát không phải bằng chứng xác thực. Nếu cần tenant ID, phải kiểm tra tenant claim đáng tin từ Access Token và membership/domain policy, không lấy `X-Tenant-ID` làm quyền mặc định.

## 10. Spring Security WebFlux lưu Authentication ở đâu?

Với **WebFlux Security**, SecurityContext được duy trì qua Reactor Context bằng các thành phần reactive security infrastructure. Trong Bearer JWT Resource Server, Authentication thành công có thể là `JwtAuthenticationToken`; authorities thường là `SCOPE_...` từ token claims được ánh xạ.

~~~text
HTTP Authorization: Bearer JWT
              |
              v
Reactive authentication web filter
              |
              v
ReactiveJwtDecoder
  - signature, issuer, audience, exp, nbf...
              |
              v
JwtAuthenticationToken
  - principal Jwt
  - authorities SCOPE_orders.read
              |
              v
SecurityContext
              |
              v
Reactor Context của subscription
              |
              v
ReactiveSecurityContextHolder.getContext()
              |
              v
Controller / Service / method authorization
~~~

Một token sai chữ ký hoặc audience phải bị từ chối **trước** khi trở thành `Authentication` hợp lệ. Việc code đọc được một `SecurityContext` không tự chứng minh caller có quyền trên order/tenant cụ thể; phải tiếp tục phân quyền.

### 10.1. Cấu hình SecurityWebFilterChain cho JWT

Trong Spring WebFlux dùng **`SecurityWebFilterChain`** và **`ServerHttpSecurity`**, không phải `SecurityFilterChain` và `HttpSecurity` của Servlet MVC.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class WebFluxSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            // Phù hợp API thuần Bearer header, không dùng cookie session
            // làm credential. Không sao chép cho web OIDC Login.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(
                    HttpMethod.GET, "/api/public/ping").permitAll()
                .pathMatchers(
                    HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(
                    HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Trong `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/demo
          audiences:
            - orders-api
~~~

Trên phiên bản Spring Boot hỗ trợ `audiences`, thuộc tính trên yêu cầu Access Token dành cho `orders-api`; nếu không hỗ trợ, cần cấu hình reactive JWT decoder/validator audience tương ứng. **Phải kiểm tra chữ ký, issuer, audience và thời hạn** trước khi tin principal.

Ví dụ `csrf.disable()` chỉ dành cho **API stateless dùng Bearer trong header** và không sử dụng cookie/session làm cách tự động xác thực. Với web session/OIDC Login cần CSRF strategy phù hợp.

### 10.2. Thứ tự security filters và reactive lifecycle

`SecurityWebFilterChain` gồm nhiều `WebFilter` thực hiện authentication, authorization, exception translation và các chính sách khác. Chúng phối hợp qua **Publisher**; không nên tự chèn một đoạn code blocking hoặc `subscribe()` vào WebFilter để “đợi token”.

Khi một custom `WebFilter` cần thông tin user, hãy **composed** các reactive operations và dùng `ReactiveSecurityContextHolder`. Tùy **vị trí filter** trong chain, Authentication có thể chưa được thiết lập; không nên lấy `null` lúc đầu rồi cache làm user cho cả request.

## 11. Đọc SecurityContext đúng thời điểm trong Mono/Flux

Ví dụ một service muốn lấy subject từ JWT đã xác thực:

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CurrentSubjectService {

    public Mono<String> currentSubject() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .filter(Authentication::isAuthenticated)
            .ofType(JwtAuthenticationToken.class)
            .map(auth -> auth.getToken().getSubject())
            .filter(subject ->
                subject != null && !subject.isBlank())
            .switchIfEmpty(Mono.error(
                new AccessDeniedException(
                    "Authenticated JWT principal required")));
    }
}
~~~

Điểm quan trọng:

- **Không gọi `block()`** để cố lấy SecurityContext trong request xử lý non-blocking.
- `ReactiveSecurityContextHolder.getContext()` trả **Mono**, để Spring Security lấy từ subscriber context khi được subscribe.
- `JwtAuthenticationToken` là loại Authentication phù hợp **khi cấu hình JWT**. Opaque Resource Server có thể sử dụng loại Authentication khác.
- Không tự tạo `Authentication` giả nếu không thấy context.
- `switchIfEmpty` trong ví dụ từ chối khi không có principal phù hợp; HTTP status cụ thể phụ thuộc exception handling.

### 11.1. Controller trả Publisher dùng SecurityContext

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

record MyProfile(String subject) {}

@RestController
class MeController {

    private final CurrentSubjectService currentSubjectService;

    MeController(CurrentSubjectService currentSubjectService) {
        this.currentSubjectService = currentSubjectService;
    }

    @GetMapping("/api/me")
    Mono<MyProfile> me() {
        return currentSubjectService.currentSubject()
            .map(MyProfile::new);
    }
}
~~~

Nếu mở `/api/me`, cần thêm HTTP rule:

~~~java
.pathMatchers(HttpMethod.GET, "/api/me").authenticated()
~~~

trước `anyExchange().denyAll()`. Đoạn controller và service minh họa cách **dùng SecurityContext mà không tự subscribe**. Endpoint sản phẩm thật cần quyết định dữ liệu nào được phép trả và có cần local user mapping hay không.

### 11.2. Không lấy SecurityContext một lần ở constructor

Sai:

~~~java
// KHÔNG LÀM.
@Service
class UnsafeIdentityService {

    private final Authentication current =
        SecurityContextHolder.getContext()
            .getAuthentication();

    // Singleton service có thể giữ Authentication null/cũ
    // và không gắn với request hiện tại.
}
~~~

Spring `@Service` thường singleton, trong khi Authentication là **theo request/subscription**. Không cache principal của request vào field singleton hoặc static. Với WebFlux, phải lấy nó **trong chain** và tại thời điểm cần dùng, không ghi vào biến toàn cục.

### 11.3. defer và deferContextual cho dữ liệu request

~~~java
Mono<String> requestId =
    Mono.deferContextual(contextView -> {
        String id =
            contextView.getOrDefault("requestId", "unknown");
        return Mono.just(id);
    });
~~~

`deferContextual` phù hợp với **custom Reactor Context keys**. Đối với principal/authorities đã xác thực, **ưu tiên `ReactiveSecurityContextHolder`**, không tự cài một map `currentUser` ngoài security infrastructure để thay Spring Security.

## 12. contextWrite và vị trí operator

Reactor Context có hướng truyền **từ downstream subscriber lên upstream**. Ví dụ:

~~~java
Mono<String> source =
    Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("requestId", "missing")));

Mono<String> result =
    source.contextWrite(context ->
        context.put("requestId", "abc-123"));
~~~

Khi subscribe vào `result`, `source` thấy `requestId=abc-123`.

### 12.1. Context không phải state mutability

~~~java
Mono<String> resultA = source.contextWrite(
    context -> context.put("requestId", "A"));

Mono<String> resultB = source.contextWrite(
    context -> context.put("requestId", "B"));
~~~

Không có thao tác sửa một `Map` global; mỗi subscription có context riêng. Nếu cần thay một giá trị trong pipeline, dùng `contextWrite` và truyền đúng publisher, không ghi vào shared singleton field.

### 12.2. contextWrite không cứu chuỗi subscribe thủ công

Sai:

~~~java
Mono<String> result = Mono.deferContextual(
    ctx -> Mono.just(ctx.get("requestId")));

result.subscribe(value -> audit(value)); // Subscription riêng

return Mono.empty()
    .contextWrite(ctx -> ctx.put("requestId", "req-42"));
~~~

Subscription được tạo bởi `result.subscribe()` **không phải subscriber** của Publisher được trả về ở dòng cuối; `contextWrite` của Publisher cuối **không tự áp dụng** cho subscription trước đó.

Cách đúng là giữ **một chuỗi Publisher**:

~~~java
return result
    .flatMap(value -> auditReactive(value))
    .contextWrite(ctx -> ctx.put("requestId", "req-42"))
    .then();
~~~

Trong ví dụ, `auditReactive(value)` phải trả một `Publisher` và không blocking. Với security context, dùng context do Spring Security thiết lập thay vì tự gán giá trị user do client cung cấp.

## 13. Vì sao thread switch không làm mất Reactor Context, nhưng CompletableFuture có thể?

Khi sử dụng:

~~~java
return reactiveRepository.findById(id)
    .publishOn(Schedulers.parallel())
    .flatMap(this::transformAsync);
~~~

Reactor Context đi cùng chuỗi Publisher nếu mọi thao tác tiếp tục dùng các operators Reactor đúng cách. **Không phải** vì `SecurityContextHolder` ThreadLocal được tự động copy, mà vì context là một phần của subscriber.

### 13.1. subscribeOn vs publishOn

| Operator | Mục tiêu thường gặp | Liên quan Context |
| --- | --- | --- |
| `subscribeOn(scheduler)` | Điều khiển scheduler dùng cho subscription/upstream work theo semantics của Reactor. | Reactor Context tiếp tục theo subscriber chain. |
| `publishOn(scheduler)` | Chuyển execution context của downstream operators. | Reactor Context tiếp tục theo chain; ThreadLocal không được bảo đảm. |
| `flatMap(publisherFunction)` | Nối Publisher bất đồng bộ. | Reactor có cơ chế truyền subscriber context vào các inner subscriptions. |
| `subscribe()` thủ công | Tạo subscription mới. | **Không bảo đảm** nhận context của request đang chạy. |
| `CompletableFuture.supplyAsync(...)` | Chạy công việc ngoài Reactor. | Không tự động đọc Reactor Context trong callback. |

Nếu phải dùng thư viện `CompletableFuture`, nên tạo Publisher qua `Mono.fromFuture` hoặc adapter thích hợp, đồng thời **truyền rõ ngữ cảnh cần thiết dưới dạng dữ liệu bất biến** khi đi qua boundary không hiểu Reactor Context. Đừng mong `ReactiveSecurityContextHolder.getContext()` tự hoạt động trong mọi callback Java nằm ngoài subscription.

### 13.2. Truyền principal dưới dạng dữ liệu đã được kiểm soát

Một pattern rõ ràng:

~~~java
record VerifiedUser(String subject, String tenantId) {}

Mono<OrderDto> loadForCurrentUser(UUID orderId) {
    return currentUserService.verifiedUser()
        .flatMap(user ->
            orderRepository.findForUser(
                orderId, user.subject(), user.tenantId()));
}
~~~

Trong ví dụ, `verifiedUser()` phải được triển khai để lấy principal từ Spring Security và kiểm tra token/domain contract. `findForUser` phải ràng buộc owner/tenant bằng dữ liệu database. Đây là **truyền dữ liệu rõ ràng sau xác thực**, không phải tạo một security context mới hoặc tin `userId` do client gửi.

## 14. Reactive method security và thời điểm kiểm tra quyền

Spring Security hỗ trợ method authorization cho WebFlux:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
~~~

Ví dụ:

~~~java
import java.util.UUID;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderReader {

    private final OrderRepository orders;

    public OrderReader(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderDto> read(UUID orderId) {
        return orders.findById(orderId)
            .map(OrderDto::fromEntity);
    }
}
~~~

Spring Security thực hiện reactive method authorization dựa trên **SecurityContext của subscription**. Với phương thức trả `Mono`/`Flux`, các quyền cần được kiểm tra **trong chuỗi được subscribe**, không dựa vào ThreadLocal ở thời điểm assembly. Ngoài ra, annotation/proxy chỉ có tác dụng khi method được gọi **qua Spring-managed proxy** tương ứng.

### 14.1. Tại sao phải tránh side effect eager trong method được bảo vệ?

Không nên viết:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.write')")
public Mono<OrderDto> create(OrderCommand command) {
    externalSystem.sendSynchronously(command); // Không nên!
    return reactiveOrders.save(command);
}
~~~

`sendSynchronously` có thể là side effect **ngay lúc Java method body được gọi**, thay vì được biểu diễn đầy đủ trong Publisher. Trong kiến trúc reactive, phải tránh để side effect nằm ngoài cơ chế authorization/transaction/cancellation.

Thiết kế phù hợp hơn:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.write')")
public Mono<OrderDto> create(OrderCommand command) {
    return validateReactive(command)
        .then(reactiveOrders.save(command));
}
~~~

`validateReactive` và `reactiveOrders.save` là các phương thức minh họa trả Publisher. Khi có external side effect không thể rollback, cần thêm idempotency và workflow safeguards. Đừng dùng `doOnNext` như chỗ ghi thanh toán một cách không kiểm soát, vì `retry` hoặc multiple subscriptions có thể làm side effect chạy lại.

### 14.2. Self-invocation vẫn là vấn đề

Nếu method `@PreAuthorize` nằm trong một Spring bean nhưng method khác của **cùng instance** gọi qua `this`, proxy có thể bị bỏ qua. Ví dụ:

~~~java
@Service
class UnsafeService {

    Mono<Void> process(UUID id) {
        return delete(id); // Self-invocation có thể bypass proxy
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.delete')")
    public Mono<Void> delete(UUID id) {
        return Mono.empty();
    }
}
~~~

Không nên dựa vào annotation đơn lẻ nếu có đường gọi nội bộ không đi qua proxy. Tách method cần bảo vệ sang bean khác, bảo vệ entrypoints và đặt domain checks gần thao tác ghi. Cần test được cả đường gọi qua WebFlux controller và đường gọi từ service khác.

### 14.3. Argument của method vẫn là dữ liệu chưa đáng tin

`@PreAuthorize("hasAuthority('SCOPE_orders.read')")` chỉ kiểm tra quyền đọc chung. Nếu method nhận `orderId`, domain vẫn cần kiểm tra bản ghi thuộc user/tenant hiện tại. Không dùng path/query hoặc body `ownerId` như bằng chứng quyền; phải dùng thông tin principal từ token đã xác minh và dữ liệu database.

## 15. Một ví dụ WebFlux service sử dụng security context trong pipeline

Giả sử một API `GET /api/orders/{orderId}` cần kiểm tra:

1. JWT Access Token đã được Resource Server xác thực.
2. Caller có `SCOPE_orders.read`.
3. User có local account ACTIVE và đơn hàng thuộc tenant/user đó.

HTTP rule chặn thiếu scope trước:

~~~java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Service tiếp tục ràng buộc dữ liệu:

~~~java
import java.net.URI;
import java.util.UUID;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class AuthorizedOrderService {

    private final LocalIdentityService identities;
    private final OrderRepository orders;

    public AuthorizedOrderService(
            LocalIdentityService identities,
            OrderRepository orders) {
        this.identities = identities;
        this.orders = orders;
    }

    public Mono<OrderDto> findAuthorized(UUID orderId) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .ofType(JwtAuthenticationToken.class)
            .flatMap(auth -> {
                URI issuer = auth.getToken().getIssuer();
                String subject = auth.getToken().getSubject();
                Object rawTenant =
                    auth.getToken().getClaims().get("tenant_id");

                if (issuer == null
                        || subject == null
                        || subject.isBlank()
                        || !(rawTenant instanceof String tenant)
                        || tenant.isBlank()) {
                    return Mono.error(new AccessDeniedException(
                        "Account context unavailable"));
                }

                return identities.findActiveUserId(
                        issuer.toString(), subject)
                    .switchIfEmpty(Mono.error(
                        new AccessDeniedException(
                            "Account context unavailable")))
                    .flatMap(userId ->
                        orders.findByIdAndTenantIdAndOwnerUserId(
                            orderId, tenant, userId))
                    .switchIfEmpty(Mono.error(
                        new AccessDeniedException(
                            "Order access not permitted")))
                    .map(OrderDto::fromEntity);
            })
            .switchIfEmpty(Mono.error(
                new AccessDeniedException(
                    "Authenticated JWT principal required")));
    }
}
~~~

Ở đây:

- `LocalIdentityService.findActiveUserId(issuer, subject)` là **interface nghiệp vụ minh họa** trả `Mono<UUID>`, phải tra mapping bằng **cặp (issuer, subject)** và chỉ trả account ACTIVE.
- `OrderRepository.findByIdAndTenantIdAndOwnerUserId` là reactive repository method minh họa trả `Mono<OrderEntity>`; query thật phải ràng buộc owner/tenant trong database.
- `OrderDto.fromEntity` là mapper của ứng dụng.
- Một response bị từ chối dùng `AccessDeniedException`; HTTP status cần được cấu hình/test qua WebFlux exception handling.
- Không dùng `block()`, `subscribe()`, static user field hoặc request header tự khai để tìm principal.

### 15.1. Vì sao pipeline này giữ đúng subscription context?

Khi WebFlux subscribe vào `findAuthorized(...)`, nó sử dụng subscriber context do security filters thiết lập. `ReactiveSecurityContextHolder.getContext()` đọc Authentication trong context đó, rồi `flatMap` chuyển thông tin đã xác thực vào những Publisher truy vấn database. Nếu client hủy request, cancellation có thể truyền vào các publisher này theo khả năng driver.

Một method Java gọi `findAuthorized(...)` **chưa tự xác thực lại token** hay chạy query ngay tại assembly. Token đã được xử lý ở WebFlux security filter chain; method chỉ lấy principal từ context của subscription khi tiếp tục xử lý request.

### 15.2. Đừng tạo Publisher chung chứa user từ request A

Sai:

~~~java
// KHÔNG LÀM: singleton cache dễ giữ dữ liệu người dùng sai ngữ cảnh.
private Mono<String> cachedCurrentSubject;

public Mono<String> subject() {
    if (cachedCurrentSubject == null) {
        cachedCurrentSubject =
            currentSubjectService.currentSubject().cache();
    }
    return cachedCurrentSubject;
}
~~~

Nếu `cache()` trên publisher đọc SecurityContext được dùng chung trong singleton, **giá trị của subscriber đầu tiên** có thể bị phát lại cho những requests khác. Đó là nguy cơ cross-user data leakage.

Không cache trực tiếp `Authentication` hoặc current user ở singleton. Nếu cần cache tài nguyên, thiết kế key theo identity/tenant/resource và phiên bản chính sách, TTL, invalidation, rồi vẫn kiểm tra quyền theo request.

## 16. Context và WebClient: cùng process khác với gọi một service từ xa

Khi một WebFlux service gọi `WebClient`:

~~~java
Mono<InventoryDto> inventory =
    webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryDto.class);
~~~

Publisher `WebClient` được kết hợp trong cùng Reactor pipeline có thể dùng Reactor Context của caller **trong process hiện tại**. Nhưng **Reactor Context không tự đi qua HTTP network sang service B**.

### 16.1. Không tự động relay mọi Bearer token

Giả sử Access Token được cấp với:

~~~json
{
  "iss": "https://identity.example.test/realms/demo",
  "sub": "person-123",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

API **orders-api** nhận token đó, rồi gọi **inventory-api**. Không nên tự:

~~~text
Authorization: Bearer <original orders-api token>
~~~

cho mọi downstream service. Token có `aud=orders-api`, **không nhất thiết được phép dùng tại inventory-api**. Nếu truyền nguyên token, downstream phải kiểm tra audience/token profile và từ chối khi không phù hợp.

Khi cần delegated access/on-behalf-of:

- Sử dụng **OAuth 2.0 Token Exchange** hoặc flow được Authorization Server hỗ trợ để lấy token dành cho downstream audience, nếu đó là mô hình sản phẩm.
- Với service-to-service không đại diện user, dùng client credentials/service identity phù hợp.
- Truyền identity/context tối thiểu trong payload nội bộ chỉ khi có trust boundary và chữ ký/xác thực service phù hợp; đừng tin `X-User-Id` do client tự gửi.
- Không log Access Token trong `WebClient` filters, tracing hoặc HTTP diagnostics.

### 16.2. WebClient call vẫn phải nằm trong pipeline

Sai:

~~~java
// KHÔNG LÀM.
webClient.post()
    .uri("/audit")
    .retrieve()
    .bodyToMono(Void.class)
    .subscribe();

return orderRepository.save(order);
~~~

Audit call là subscription tách rời: không có bảo đảm về thứ tự/transaction/cancellation/context với save. Cách nối Publisher có chủ đích:

~~~java
return orderRepository.save(order)
    .flatMap(saved ->
        auditClient.recordCreated(saved)
            .thenReturn(saved));
~~~

`auditClient.recordCreated` phải trả `Mono<Void>` hoặc Publisher thích hợp. Tuy vậy, **save database và POST audit qua HTTP vẫn không tự nằm trong một distributed transaction**. Với yêu cầu audit không thể mất, cân nhắc transactional outbox hoặc event-driven design; cancellation giữa hai bước cần được xử lý bằng idempotency/recovery.

## 17. ThreadLocal MDC và trace context: đừng nhầm với SecurityContext

Trong logging truyền thống, nhiều thư viện sử dụng **MDC (Mapped Diagnostic Context)** dựa trên ThreadLocal:

~~~java
MDC.put("requestId", requestId);
~~~

Nhưng request WebFlux có thể đổi thread, nên MDC có thể:

- Không thấy `requestId` ở operator sau `publishOn`.
- Giữ dữ liệu cũ nếu callback quên cleanup.
- Nhầm user/request khi thread được tái sử dụng.

### 17.1. Dùng Reactor Context cho dữ liệu request

~~~java
Mono<String> work = Mono.deferContextual(context -> {
    String requestId =
        context.getOrDefault("requestId", "unknown");
    logger.info("requestId={}", requestId);
    return Mono.just("ok");
});
~~~

Giá trị `requestId` được đọc từ subscription context, không yêu cầu tất cả operators ở cùng thread.

### 17.2. Khi phải tích hợp thư viện dùng ThreadLocal

Tùy Reactor/Micrometer version, có thể dùng **context-propagation** integration để capture/restore một số ThreadLocal values theo phạm vi phù hợp. Đây là vấn đề vận hành và cấu hình ứng dụng, **không phải bằng chứng mọi ThreadLocal tự hoạt động trong WebFlux**.

Không bật global automatic propagation chỉ để “sửa” một chỗ `SecurityContextHolder` đang bị dùng sai mà không đánh giá ảnh hưởng đến performance, scheduling và cleanup. Đối với authorization, ưu tiên **`ReactiveSecurityContextHolder`** và truyền dữ liệu đã xác minh một cách tường minh khi vượt ra khỏi reactor chain.

## 18. Chuyển context qua boundary của custom WebFilter

Một custom reactive `WebFilter` có thể cung cấp correlation ID cho downstream:

~~~java
import java.util.UUID;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.WebFilter;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            org.springframework.web.server.ServerWebExchange exchange,
            org.springframework.web.server.WebFilterChain chain) {

        // ID do server tạo; không dùng header tùy ý làm identity.
        String requestId = UUID.randomUUID().toString();
        exchange.getResponse().getHeaders()
            .set("X-Request-ID", requestId);

        return chain.filter(exchange)
            .contextWrite(context ->
                context.put("requestId", requestId));
    }
}
~~~

**Điểm cần phân biệt:** `requestId` chỉ là metadata phục vụ tracing/correlation; nó **không phải Authentication**. Không dùng `contextWrite(ctx -> ctx.put("user", request.getHeader("X-User")))` để cấp quyền cho request. Authentication phải do **Spring Security xác minh token** và đặt vào Reactive SecurityContext.

Khi xây custom WebFilter:

- Trả `chain.filter(exchange)`, **không gọi `subscribe()`**.
- Đảm bảo filter order phù hợp với security infrastructure.
- Đừng cố đọc authentication **trước khi authentication filters chạy** rồi xem giá trị rỗng là “anonymous forever”.
- Không dùng `block()` trong WebFilter.
- Với request ID do client gửi, chỉ tin sau khi validate/normalize theo chính sách hạ tầng; request ID không cấp bất kỳ quyền nào.

## 19. Cancellation và HTTP status: đừng trộn với authentication errors

Khi Spring Security phát hiện:

- Không có Bearer token trên endpoint cần xác thực → thường **401 Unauthorized**.
- JWT sai chữ ký/issuer/audience/expired → thường **401 invalid_token**.
- JWT hợp lệ nhưng thiếu scope → thường **403 insufficient_scope**.
- JWT hợp lệ, scope đủ nhưng sai owner/tenant → thường **403/404** theo policy.

Những tình huống trên là **security decisions** được biểu diễn trong error/response pipeline.

**Cancellation lại khác:** client đã hủy subscription hoặc kết nối. Server có thể không còn khả năng gửi HTTP status/body đến client. Không tự map `SignalType.CANCEL` thành **401**, **403** hoặc một kết luận token invalid.

### 19.1. doFinally để quan sát, không để cấp quyền

~~~java
return orderService.load(orderId)
    .doFinally(signal -> {
        switch (signal) {
            case CANCEL -> metrics.recordCancelledRequest();
            case ON_ERROR -> metrics.recordErrorTermination();
            case ON_COMPLETE -> metrics.recordCompletedRequest();
            default -> { }
        }
    });
~~~

Hook trên dùng metrics cho pipeline, **không** biến một cancel thành response 401 hoặc principal giả. Nếu browser đã disconnect, đừng kỳ vọng có thể trả JSON error body tới client.

### 19.2. Không “recover” mọi lỗi bảo mật bằng dữ liệu mặc định

Sai:

~~~java
// KHÔNG LÀM.
return orderService.load(orderId)
    .onErrorResume(error ->
        Mono.just(OrderDto.publicFallback()));
~~~

Nếu `orderService.load` ném `AccessDeniedException`, đoạn `onErrorResume` bắt **mọi lỗi** sẽ có thể chuyển một request bị từ chối thành HTTP 200 chứa dữ liệu fallback, hoặc che dấu lỗi bảo mật. Chỉ recover **những lỗi được phép**, ví dụ lỗi remote lookup theo chính sách đã thiết kế, và tuyệt đối không mặc nhiên nuốt authentication/authorization exceptions.

### 19.3. Retry có thể tạo nhiều subscription

~~~java
Mono<OrderDto> result = orderService.createOrder(command)
    .retry(2);
~~~

Với cold Publisher, `retry(2)` có thể **resubscribe** và gọi lại thao tác tạo đơn. Nếu lần đầu đã commit DB nhưng response lỗi, retry có thể tạo **bản ghi trùng**.

Vì vậy với thao tác ghi:

- Không retry tùy tiện chỉ vì `Mono` trả error.
- Có **idempotency key**, unique constraint hoặc deduplication phù hợp.
- Không retry các lỗi **401/403** như lỗi network transient.
- Giữ transaction boundary và domain invariants.
- Khi retry downstream HTTP, hiểu operation có idempotent hay không.

## 20. Reactive transaction context khác reactive security context

Cả Spring Security và Spring Reactive Transactions có thể sử dụng Reactor Context, nhưng mỗi thành phần quản lý **loại dữ liệu và lifecycle riêng**.

| Context | Ai tạo/quản lý? | Dùng để làm gì? | Không được nhầm |
| --- | --- | --- | --- |
| **SecurityContext** | Spring Security WebFlux. | Principal, authorities, request authentication. | Không chứng minh owner/tenant tự động. |
| **Transaction context** | ReactiveTransactionManager / TransactionalOperator. | Gắn transaction/resource với subscription. | Không phải user identity. |
| **Tracing/correlation context** | Observability filters/instrumentation. | Truy vết request và logs. | Không cấp quyền. |
| **Custom application context** | Ứng dụng chủ động khai báo. | Metadata ngắn hạn như request ID, locale. | Không thay JWT validation. |

Với một method trả `Mono` được gọi qua Spring-managed service, những context này có thể cùng tồn tại trong chain nhưng **không hoán đổi được**. Việc tự ghi key `authenticated=true` vào Reactor Context không biến request thành Spring Security Authentication hợp lệ.

### 20.1. Transaction boundary phải bao toàn bộ công việc cần đồng bộ

~~~java
return orderRepository.save(order)
    .flatMap(saved ->
        itemRepository.saveItems(saved.getId(), items)
            .thenReturn(saved))
    .as(transactionalOperator::transactional);
~~~

Trong ví dụ, transaction bao gồm hai database operations cùng một reactive transaction manager phù hợp. Nếu sau đó ứng dụng gọi một external HTTP service, transaction database **không mặc nhiên bao phủ HTTP call**.

Với cancellation, transaction manager có thể yêu cầu rollback khi Publisher bị hủy, nhưng race với commit và giới hạn của driver vẫn tồn tại. **Không viết logic nghiệp vụ dựa trên giả định hủy subscription là rollback toàn hệ thống.**

## 21. Kiểm thử subscription và cancellation bằng StepVerifier

**Reactor Test** cung cấp `StepVerifier` để kiểm thử Publisher, tín hiệu hoàn tất/lỗi/hủy và nội dung Reactor Context. Thêm dependency:

~~~groovy
testImplementation 'io.projectreactor:reactor-test'
~~~

### 21.1. Test lazy execution tại subscription

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SubscriptionTest {

    @Test
    void deferRunsOnSubscription() {
        AtomicInteger invoked = new AtomicInteger();

        Mono<String> pipeline = Mono.defer(() -> {
            invoked.incrementAndGet();
            return Mono.just("ok");
        });

        // Chưa có subscription: chưa chạy body defer.
        assertEquals(0, invoked.get());

        StepVerifier.create(pipeline)
            .expectNext("ok")
            .verifyComplete();

        assertEquals(1, invoked.get());

        StepVerifier.create(pipeline)
            .expectNext("ok")
            .verifyComplete();

        // Cold pipeline chạy lại khi subscribe lần 2.
        assertEquals(2, invoked.get());
    }
}
~~~

Test này chỉ kiểm tra **semantics subscription**, không test JWT signature hay SecurityContext.

### 21.2. Test cancellation với doFinally

~~~java
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CancellationTest {

    @Test
    void cancellationIsNotOnError() {
        AtomicReference<SignalType> terminal =
            new AtomicReference<>();

        Flux<Long> infinite = Flux.interval(
                java.time.Duration.ofMillis(10))
            .doFinally(terminal::set);

        StepVerifier.create(infinite)
            .expectNext(0L)
            .thenCancel()
            .verify();

        assertEquals(SignalType.CANCEL, terminal.get());
    }
}
~~~

Đây là ví dụ kiểm thử cancel với stream phát định kỳ. Đối với test phụ thuộc scheduler/timing, có thể dùng `StepVerifier.withVirtualTime` để tránh đợi thời gian thực và tăng tính ổn định. Điều cần chứng minh là **cancel kích hoạt nhánh cleanup/metrics**, không tự phát một `onError` được trả cho subscriber.

### 21.3. Test Reactor Context với StepVerifier

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactorContextTest {

    @Test
    void subscriberContextIsVisible() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.get("requestId")));

        StepVerifier.create(
                source.contextWrite(ctx ->
                    ctx.put("requestId", "req-test-1")))
            .expectNext("req-test-1")
            .verifyComplete();
    }
}
~~~

Nếu bỏ `contextWrite`, `ctx.get("requestId")` sẽ không có giá trị; tùy cách đọc, Publisher có thể thất bại vì không tìm thấy key. Trong code production có thể dùng `getOrDefault` hoặc thiết kế key bắt buộc theo contract.

## 22. Kiểm thử SecurityContext trong một reactive service

Không cần ký JWT thật để test riêng **service đang đọc ReactiveSecurityContextHolder đúng cách**. Có thể dùng một Authentication giả lập trong Reactor Context của test.

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import reactor.test.StepVerifier;

class ReactiveSecurityContextTest {

    @Test
    void serviceReadsAuthenticationFromSubscriberContext() {
        Instant now = Instant.now();

        Jwt jwt = new Jwt(
            "synthetic-test-token",
            now,
            now.plusSeconds(600),
            Map.of("alg", "RS256"),
            Map.of(
                "iss", "https://identity.example.test/realms/demo",
                "sub", "person-A",
                "aud", List.of("orders-api")));

        JwtAuthenticationToken auth =
            new JwtAuthenticationToken(jwt, List.of(
                new SimpleGrantedAuthority("SCOPE_orders.read")));

        CurrentSubjectService service =
            new CurrentSubjectService();

        StepVerifier.create(
                service.currentSubject()
                    .contextWrite(
                        ReactiveSecurityContextHolder
                            .withAuthentication(auth)))
            .expectNext("person-A")
            .verifyComplete();
    }
}
~~~

Phương thức `ReactiveSecurityContextHolder.withAuthentication(auth)` được sử dụng **trong test** để đưa Authentication giả vào subscriber context. **Không sử dụng nó trên API production để tạo Authentication từ HTTP headers chưa xác thực.**

Đây là test **context propagation**, **không** chứng minh JWT chữ ký, issuer, audience hoặc scopes thực sự được `ReactiveJwtDecoder` kiểm tra. Muốn kết luận Resource Server đã xác thực token an toàn phải có integration test riêng.

### 22.1. Hai subscribers không được lẫn principal

Một bài test nên tạo:

~~~text
Subscriber A -> JWT subject person-A
Subscriber B -> JWT subject person-B
~~~

Sau đó subscribe cả hai vào cùng service method tạo Publisher và xác nhận mỗi subscriber nhận đúng subject. Nếu code sử dụng biến static, singleton field hoặc `cache()` sai cách, test này có thể bộc lộ lỗi rò rỉ principal giữa requests.

### 22.2. Dùng WebTestClient cho WebFlux HTTP security

Với `spring-security-test`, WebFlux có thể dùng test configurer để tạo JWT Authentication giả:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

Đoạn trên minh họa authorization test **khi đã có handler/test data cho order 42 và principal được phép đọc nó**. `mockJwt()` tạo authentication giả trong test, **không xác minh JWS thật**.

Một kiểm thử HTTP đầy đủ cần các trường hợp:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Không có Bearer token vào endpoint bảo vệ | **401**. |
| JWT ký sai, hết hạn, issuer/audience sai | **401** từ decoder thật. |
| JWT hợp lệ thiếu `SCOPE_orders.read` | **403** ở HTTP authorization. |
| JWT hợp lệ có scope, order thuộc người khác | **403/404** theo domain policy. |
| JWT hợp lệ đúng quyền, order thuộc user | Thành công theo handler. |
| Client cancel request streaming | Subscription cleanup phù hợp, không lộ/leak resource. |
| Có `publishOn`/scheduler switch trong service | ReactiveSecurityContextHolder vẫn đọc đúng principal. |
| Hai requests đồng thời với hai principals khác nhau | Không lẫn Authentication/context. |
| `retry` thao tác tạo đơn | Không tạo duplicate khi có idempotency policy. |

Đối với JWT end-to-end, tạo test key pair, ký JWT và cấu hình `ReactiveJwtDecoder` cùng validators thật, rồi gửi Bearer token qua WebTestClient. Test này khác với `mockJwt()`.

## 23. Kiểm thử cancel của HTTP request và downstream

StepVerifier giúp kiểm thử Publisher, còn **WebTestClient**, Reactor Netty test server hoặc client test có thể giúp quan sát lifecycle HTTP.

Ví dụ chiến lược:

1. Dựng endpoint `Flux` phát nhiều phần tử với một `AtomicInteger` hoặc metrics để ghi nhận **`doFinally(CANCEL)`**.
2. Client subscribe vào response stream.
3. Client nhận phần tử đầu rồi hủy subscription.
4. Kiểm tra server nhận cancellation khi transport và test setup hỗ trợ.
5. Kiểm tra tài nguyên upstream được giải phóng và không còn tác vụ tự subscribe chạy riêng.

Cần phân biệt:

- **Unit test publisher:** bạn điều khiển cancellation chính xác qua StepVerifier.
- **HTTP integration test:** thời điểm disconnect, buffering và server transport có thể ảnh hưởng lúc cancellation đến ứng dụng.
- **Business behavior:** cancel subscription không chứng minh remote transaction đã bị rollback.

Với request ghi dữ liệu, test cả trường hợp **commit thành công nhưng client mất kết nối trước response**. Xác nhận client có thể retry an toàn bằng idempotency key hoặc truy vấn trạng thái mà không gây duplicate.

## 24. Các tình huống dễ sai trong thực tế

| Sai lầm | Hậu quả | Cách phù hợp |
| --- | --- | --- |
| Gọi `subscribe()` trong controller. | Detached work, lỗi/cancel/context không đi cùng request. | Trả một Publisher hoàn chỉnh cho WebFlux. |
| Gọi `block()` trong event-loop. | Có thể làm nghẽn xử lý non-blocking, gây timeout. | Dùng `flatMap`, reactive drivers; isolate blocking khi bắt buộc. |
| Dùng `SecurityContextHolder` ThreadLocal như Spring MVC. | Không thấy hoặc nhầm Authentication khi đổi thread. | Dùng `ReactiveSecurityContextHolder`. |
| Đọc current user trong singleton constructor. | Giá trị null/cũ bị giữ qua nhiều requests. | Lấy principal trong Publisher của từng subscription. |
| Cache một `Mono` chứa current user cho mọi request. | Rò rỉ subject/tenant giữa users. | Không share principal publishers; phân quyền cache theo request/resource. |
| Dùng `Mono.just(blockingCall())`. | Hàm chạy eager ngay tại assembly. | `fromCallable` + boundedElastic khi cần, hoặc API reactive thật. |
| Dùng `doOnComplete` để cleanup mọi trường hợp. | Không cleanup trên cancel/error. | `usingWhen`, reactive transaction lifecycle, `doFinally` cho quan sát. |
| Coi cancel là một exception thông thường. | Metrics/cleanup/error handling sai. | Phân biệt `CANCEL`, `ON_ERROR`, `ON_COMPLETE`. |
| Cho rằng cancel luôn rollback remote POST. | Gây retry trùng hoặc trạng thái lệch. | Idempotency, transactional constraints, audit/reconciliation. |
| `retry` thao tác ghi không idempotent. | Có thể chạy nhiều lần sau resubscribe. | Retry theo policy, deduplication và idempotency key. |
| Tin `X-User-Id` thay SecurityContext. | Client giả mạo danh tính. | Dùng token đã xác thực và domain identity mapping. |
| Dùng `@PreAuthorize` trên self-invoked method mà không có domain guard. | Có thể bypass proxy. | Gọi qua Spring bean/proxy và bảo vệ thao tác thật. |
| Cho rằng Reactor Context tự đi sang HTTP service B. | Downstream không có credential phù hợp. | OAuth client/service credentials hoặc token exchange đúng audience. |
| Forward JWT của orders-api tới inventory-api. | Token sai audience và lộ credential không cần thiết. | Dùng token dành cho downstream resource. |
| Đọc MDC như thể luôn theo subscription. | Log sai request hoặc mất correlation ID. | Dùng Reactor Context/context-propagation tích hợp. |
| Bắt mọi `onError` thành fallback success. | Có thể nuốt `AccessDeniedException`. | Recover có chọn lọc, fail closed với security errors. |
| Test chỉ bằng `mockJwt()` rồi kết luận JWT verifier an toàn. | Test bỏ qua chữ ký/issuer/audience. | Có test `ReactiveJwtDecoder` ký thật riêng. |

## 25. Một lộ trình triển khai WebFlux Resource Server

1. **Xác định stack đúng:** Dùng `spring-boot-starter-webflux`, `SecurityWebFilterChain`, `ServerHttpSecurity` và `ReactiveJwtDecoder`; không nhầm với Servlet `HttpSecurity`.
2. **Xác minh token tại security boundary:** JWT signature, issuer, audience, thời hạn và scope authorities. Không tạo Authentication từ headers chưa xác thực.
3. **Giữ một chuỗi Publisher từ controller tới I/O:** Không tự `subscribe()` hoặc `block()` trong WebFlux request path.
4. **Hiểu thời điểm thực thi:** Assembly tạo mô tả; subscription thường kích hoạt công việc của cold Publisher; `Mono.just` không trì hoãn việc tạo value.
5. **Dùng ReactiveSecurityContextHolder:** Đọc principal/authorities trong reactive chain; không cache context vào singleton.
6. **Truyền context có chủ đích:** Dùng `contextWrite`/`deferContextual` cho metadata, để Spring Security quản lý authentication context, kiểm soát boundary với ThreadLocal/CompletableFuture.
7. **Tách quyền chung khỏi quyền dữ liệu:** HTTP scope và method security chỉ là một lớp; domain service vẫn kiểm tra local account, tenant, owner và state.
8. **Thiết kế cancellation và cleanup:** `usingWhen`, reactive transactions, `doFinally`, resource timeouts; hiểu rằng cancel không tự rollback remote side effects.
9. **Thiết kế retry/idempotency:** Với POST hoặc transaction quan trọng, có idempotency key và cách truy vấn kết quả sau client disconnect.
10. **Không relay token tùy ý:** Reactor Context chỉ đi trong process; token cho downstream phải đúng audience, scope và OAuth flow được phê duyệt.
11. **Kiểm thử subscription/cancel/context:** StepVerifier cho lazy/defer/cancel/context; WebTestClient cho security và HTTP; decoder ký thật cho JWT validation.
12. **Quan sát mà không lộ credential:** Log request ID, signal type và nhóm lỗi; không log Bearer Access Token, nguyên SecurityContext hoặc JWT claims nhạy cảm.

**Ghi nhớ:** Trong WebFlux, **xây Publisher chưa đồng nghĩa công việc đã chạy**; **subscription** thường là lúc cold pipeline thực thi. **Cancel** là tín hiệu lifecycle riêng với complete/error và không bảo đảm đảo ngược side effect đã commit. **SecurityContext của Spring Security được truyền bằng Reactor Context theo subscription**, nên hãy dùng `ReactiveSecurityContextHolder`, giữ các thao tác trong một reactive chain và không dựa vào `ThreadLocal` hoặc `subscribe()` thủ công để duy trì danh tính.

## Tài liệu tham khảo

- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html).
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html).
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html).
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html).
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
- [Spring Framework — Programmatic Reactive Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html).
- [Project Reactor — Reactor 3 Reference Guide](https://projectreactor.io/docs/core/release/reference/).
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
- [Project Reactor — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html).
- [Reactive Streams Specification](https://www.reactive-streams.org/).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693).
