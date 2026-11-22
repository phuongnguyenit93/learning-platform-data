# @MessageMapping và handler trả về Mono, Flux trong Spring RSocket

## 1. Mục tiêu bài học

RSocket là giao thức nhắn tin nhị phân, hướng reactive, hỗ trợ trao đổi hai chiều trên TCP, WebSocket và những transport dạng byte stream khác. Spring Framework cung cấp mô hình **annotated responder**: thay vì tự thao tác từng RSocket frame, ta viết `@Controller` với `@MessageMapping` và trả về `Mono<T>`, `Flux<T>` hoặc `Mono<Void>`.

Sau bài này, có thể:

- Xác định đúng ý nghĩa của `@MessageMapping`, route metadata và payload.
- Phân biệt bốn kiểu tương tác: request-response, request-stream, fire-and-forget và request-channel.
- Hiểu vì sao Spring xét **cardinality của cả input và output**, không chỉ kiểu trả về.
- Viết method nhận `@Payload T`, `Mono<T>`, `Flux<T>` và trả `Mono<R>`, `Flux<R>`, `Mono<Void>`.
- Gọi responder qua `RSocketRequester.route(...).data(...).retrieveMono(...)`, `retrieveFlux(...)` hoặc `send()`.
- Xử lý backpressure, completion, error và cancellation.
- Chạy một server Spring Boot RSocket TCP và client Java 17 để thử cả bốn interaction.

RSocket **khác** một HTTP REST controller hoặc một WebSocketHandler thuần. `@MessageMapping` của RSocket không tự tạo REST endpoint; route là metadata của một RSocket request. Mỗi kết nối RSocket có thể multiplex nhiều request stream.

## 2. Tổng quan giao thức RSocket

Bốn tương tác của RSocket:

| Interaction | Dữ liệu từ requester | Dữ liệu từ responder | Ví dụ |
| --- | --- | --- | --- |
| **Request-Response** | Tối đa một payload ban đầu | Một payload phản hồi | Tìm thông tin một sản phẩm |
| **Request-Stream** | Tối đa một payload ban đầu | Nhiều payload phản hồi | Stream tiến độ xử lý |
| **Fire-and-Forget** | Tối đa một payload ban đầu | Không có response data | Gửi event best-effort |
| **Request-Channel** | Stream payload từ requester | Không, một hoặc nhiều payload phản hồi | Chat, xử lý luồng sensor hai chiều |

Minh họa:

~~~text
REQUEST_RESPONSE
Requester   -- request --> Responder
Requester   <-- response -- Responder

REQUEST_STREAM
Requester   -- request --> Responder
Requester   <-- data 1 --- Responder
Requester   <-- data 2 --- Responder
Requester   <-- ... ------ Responder
Requester   <-- complete - Responder

FIRE_AND_FORGET
Requester   -- event ----> Responder
             (không có response payload)

REQUEST_CHANNEL
Requester   -- data 1 ---> Responder
Requester   <-- reply A -- Responder
Requester   -- data 2 ---> Responder
Requester   <-- reply B -- Responder
Requester   -- complete -> Responder
Requester   <-- complete - Responder
~~~

Không nên đồng nhất **fire-and-forget** với “server đã xử lý thành công”. Mono trả về từ thao tác gửi phía requester chỉ cho biết quá trình gửi được thực hiện theo contract, không phải một xác nhận nghiệp vụ từ responder.

### 2.1. Setup, route và MIME type

Một kết nối RSocket bắt đầu bằng frame SETUP. Các bên thương lượng data MIME type và metadata MIME type. Trên mỗi request, message thường mang:

- **Data**: payload nghiệp vụ, ví dụ String, JSON, CBOR hoặc Protobuf.
- **Metadata**: thông tin để định tuyến, xác thực hoặc ngữ cảnh khác.
- **Route**: đích logic, ví dụ `products.find`, thường nằm trong routing metadata.

`@MessageMapping("products.find")` được Spring chọn khi routing metadata của request chứa route phù hợp. Route không phải HTTP path và không dùng HTTP method GET/POST.

Nếu requester và responder sử dụng codec hoặc MIME không tương thích, route có thể đúng nhưng payload vẫn không được decode.

### 2.2. Backpressure xuyên biên giới mạng

Khi requester nhận request-stream hoặc channel, nó gửi demand cho responder. RSocket truyền demand bằng frame như `REQUEST_N`. Điều này giúp responder không phát vô hạn khi requester chỉ yêu cầu một số phần tử.

Trên Java, `Flux` và `Mono` triển khai các Reactive Streams semantics, nên cancellation, demand và error trong pipeline có thể lan đến tầng RSocket.

Tuy vậy, backpressure không thay thế giới hạn bộ nhớ hoặc bảo vệ khỏi một nguồn hot phát dữ liệu không tôn trọng demand.

## 3. @MessageMapping là gì?

`@MessageMapping` đánh dấu một method xử lý thông điệp RSocket theo route. Dạng cơ bản:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class ProductResponder {

    @MessageMapping("products.find")
    public Mono<String> findProduct(String productId) {
        return Mono.just("Product " + productId);
    }
}
~~~

Khi Spring Messaging RSocket infrastructure đã được cấu hình, `RSocketMessageHandler` tìm `@Controller` và các method annotated để chọn handler.

Đây là code minh họa về hình dạng handler. Để ràng buộc payload kiểu đơn giản như `String` một cách tường minh, ví dụ chạy độc lập ở phần sau dùng `@Payload`:

~~~java
@MessageMapping("products.find")
public Mono<String> findProduct(@Payload String productId) {
    return Mono.just("Product " + productId);
}
~~~

### 3.1. @MessageMapping không phải @GetMapping

| API | Giao thức | Điều định tuyến |
| --- | --- | --- |
| `@GetMapping("/products/{id}")` | HTTP | URL path và method GET |
| `@PostMapping("/products")` | HTTP | URL path và method POST |
| `@MessageMapping("products.find")` | RSocket | Route metadata trong RSocket message |
| `@ConnectMapping` | RSocket | SETUP hoặc METADATA_PUSH cấp kết nối |

Cùng tên annotation `@MessageMapping` còn xuất hiện trong Spring messaging cho STOMP/WebSocket. Bài này chỉ bàn về **Spring RSocket annotated responder**, không phải STOMP broker destination hoặc `@SendTo` của WebSocket messaging.

### 3.2. Method có thể nằm trong @Controller

Trong Spring Boot:

~~~java
@Controller
class CatalogController {

    @MessageMapping("catalog.greet")
    Mono<String> greet(@Payload String name) {
        return Mono.just("Hello " + name);
    }
}
~~~

Dùng `@Controller`, không cần `@RestController`. Spring Boot với RSocket starter có thể tự cấu hình `RSocketMessageHandler` và `RSocketStrategies`. Không cần tự khởi tạo `RSocketMessageHandler` trong dự án Boot mẫu nếu auto-configuration đã hoạt động.

## 4. Quy tắc quyết định interaction type

Đây là điểm quan trọng nhất của `@MessageMapping`: Spring xét **số lượng phần tử tiềm năng của input payload và output**.

### 4.1. Input/output cardinality

| Cardinality | Kiểu thường gặp | Ý nghĩa |
| --- | --- | --- |
| 0 (input) | Không có tham số payload | Không cần dữ liệu request |
| 1 (input) | `T`, `Mono<T>` | Một payload đầu vào |
| Many (input) | `Flux<T>` | Stream payload đầu vào |
| 0 (output) | `void`, `Mono<Void>` | Không phát response value |
| 1 (output) | `T`, `Mono<T>` | Một response value |
| Many (output) | `Flux<T>` | Stream response values |

### 4.2. Bảng ánh xạ chuẩn

| Input | Output | Interaction RSocket |
| --- | --- | --- |
| 0 hoặc 1 | 0 | Fire-and-Forget **hoặc** Request-Response không có response data |
| 0 hoặc 1 | 1 | Request-Response |
| 0 hoặc 1 | Many | Request-Stream |
| Many | 0, 1 hoặc Many | Request-Channel |

Ví dụ:

~~~java
@MessageMapping("hello")
Mono<String> hello(@Payload String name) { ... }
// Input 1 -> Output 1 => Request-Response.

@MessageMapping("numbers")
Flux<String> numbers(@Payload String count) { ... }
// Input 1 -> Output Many => Request-Stream.

@MessageMapping("record")
Mono<Void> record(@Payload String event) { ... }
// Input 1 -> Output 0 => thường dùng Fire-and-Forget.

@MessageMapping("transform")
Flux<String> transform(@Payload Flux<String> values) { ... }
// Input Many -> Output Many => Request-Channel.
~~~

**Không suy luận “trả về Flux là request-channel”.** Handler chỉ nhận một payload và trả `Flux` là **request-stream**. Handler nhận `Flux` payload là **request-channel**, bất kể output cuối là 0, 1 hay nhiều phần tử.

### 4.3. Vì sao input Many quyết định channel?

Trong RSocket, một request thông thường như request-response hoặc request-stream chỉ có một initial request payload. Muốn requester tiếp tục gửi thêm nhiều payload cùng một interaction, giao thức cần request-channel.

Vì vậy, khi handler khai báo:

~~~java
Mono<String> summarize(@Payload Flux<String> lines) { ... }
~~~

đó là channel input Many, output 1; **không** phải request-response chỉ vì output là `Mono<String>`.

## 5. Handler trả Mono<T>: Request-Response

Dùng `Mono<T>` khi một request cần một phản hồi duy nhất.

~~~java
@MessageMapping("user.greet")
public Mono<String> greet(@Payload String name) {
    return Mono.just("Hello, " + name);
}
~~~

Client:

~~~java
Mono<String> reply = requester.route("user.greet")
        .data("Mai")
        .retrieveMono(String.class);
~~~

Giải thích:

1. `route("user.greet")` đưa routing metadata vào request.
2. `data("Mai")` chọn một payload đầu vào.
3. `retrieveMono(String.class)` yêu cầu một response value.
4. Subscription kích hoạt quá trình trao đổi; client nhận `onNext(reply)` rồi `onComplete()`, hoặc `onError()`.

`Mono.just(...)` phù hợp với giá trị đã có. Nếu công việc là asynchronous I/O, dùng Mono do service tạo ra:

~~~java
@MessageMapping("products.find")
public Mono<Product> find(@Payload String id) {
    return productService.findById(id);
}
~~~

Không gọi `block()` bên trong RSocket handler. Trả Mono để framework quản lý subscription và network lifecycle.

### 5.1. Đầu vào Mono<T>

Có thể khai báo payload reactive:

~~~java
@MessageMapping("products.normalize")
public Mono<String> normalize(@Payload Mono<String> input) {
    return input
            .map(String::trim)
            .map(String::toUpperCase);
}
~~~

Cách này cho phép xử lý payload trong chain, bao gồm lỗi decode và cancellation. Tuy nhiên, `Mono<T>` input vẫn có cardinality 1; nó không biến interaction thành request-channel.

### 5.2. Mono.empty() trong request-response

`Mono.empty()` hoàn tất không phát giá trị. Đây không phải String rỗng và không phải HTTP 204. Với requester đang mong đợi một giá trị, kết quả có thể là Mono rỗng hoặc có behavior theo contract của RSocket interaction. Hãy quy định rõ semantics của “không tìm thấy”:

- Có thể dùng một response DTO với trạng thái rõ.
- Có thể phát application error tương ứng.
- Chỉ dùng Mono.empty khi client được thiết kế để xử lý completion rỗng.

## 6. Handler trả Flux<T>: Request-Stream

Dùng `Flux<T>` khi một request đầu vào cần nhận một chuỗi response.

~~~java
@MessageMapping("numbers.generate")
public Flux<Integer> generate(@Payload Integer count) {
    if (count < 0 || count > 100) {
        return Flux.error(
                new IllegalArgumentException("count out of range"));
    }

    return Flux.range(1, count);
}
~~~

Client:

~~~java
Flux<Integer> numbers = requester.route("numbers.generate")
        .data(5)
        .retrieveFlux(Integer.class);
~~~

Khi subscriber yêu cầu 5 phần tử, responder có thể phát lần lượt 1, 2, 3, 4, 5 và complete. Request-stream hỗ trợ backpressure xuyên network.

Ví dụ dùng `Flux.interval`:

~~~java
@MessageMapping("ticks")
public Flux<Long> ticks(@Payload String topic) {
    return Flux.interval(Duration.ofSeconds(1))
            .take(5);
}
~~~

Đây là streaming hữu hạn. Nếu bỏ `take(5)`, stream có thể chạy lâu cho tới khi client cancel hoặc kết nối đóng. Nên có giới hạn tài nguyên hoặc chính sách idle/timeout theo contract.

### 6.1. Client hủy giữa stream

~~~java
requester.route("ticks")
        .data("system")
        .retrieveFlux(Long.class)
        .take(3)
        .doFinally(signal ->
                log.info("ticks ended: {}", signal))
        .subscribe();
~~~

`take(3)` hoàn tất sau ba phần tử và hủy upstream nếu stream chưa kết thúc. RSocket truyền cancellation tương ứng. Đây là snippet minh họa; trong controller/service, tránh tạo subscription rời rạc nếu caller đã có lifecycle owner.

### 6.2. Không collectList() trên stream vô hạn

Không làm:

~~~java
// Sai với stream vô hạn: không có completion để collectList trả kết quả.
requester.route("events")
        .retrieveFlux(Event.class)
        .collectList();
~~~

`collectList()` giữ mọi phần tử trong memory và chỉ phát List khi stream complete. Với stream liên tục, dùng `subscribe` ở application boundary hoặc compose pipeline theo event, hạn chế concurrency, bảo vệ memory.

## 7. Handler trả Mono<Void>: Fire-and-Forget

Với một sự kiện không cần response data:

~~~java
@MessageMapping("audit.record")
public Mono<Void> record(@Payload AuditEvent event) {
    return auditService.save(event);
}
~~~

`auditService.save(...)` phải trả `Mono<Void>` (hoặc một Mono khác được chuyển bằng `then()`). Spring sẽ subscribe kết quả trong lifecycle handler.

Client gọi:

~~~java
Mono<Void> sent = requester.route("audit.record")
        .data(event)
        .send();
~~~

**Phân biệt rất rõ:**

- `send()` ở phía requester thực hiện fire-and-forget. `Mono<Void>` của nó **không xác nhận rằng business logic trên server đã lưu event xong**.
- `Mono<Void>` ở phía responder mô tả công việc được ứng dụng xử lý, giúp framework nắm completion/error.
- Nếu nghiệp vụ cần xác nhận, ví dụ “lưu audit thành công hay thất bại”, nên dùng request-response với acknowledgment DTO.

### 7.1. Đừng subscribe bên trong handler

Không nên:

~~~java
@MessageMapping("audit.record")
public Mono<Void> record(@Payload AuditEvent event) {
    auditService.save(event).subscribe(); // Anti-pattern.
    return Mono.empty();
}
~~~

Lý do: side effect bị tách khỏi error/cancellation và lifecycle của request. Hãy trả thẳng `auditService.save(event)` hoặc compose bằng `then()`.

### 7.2. Output 0 không đồng nghĩa luôn là fire-and-forget

Theo bảng cardinality chính thức, input 0/1 và output 0 có thể tương ứng **fire-and-forget hoặc request-response không có response data**. Interaction thực tế được requester lựa chọn bằng API như `send()` hoặc `retrieveMono(...)` và phải tương thích với handler.

Không cố kết luận chỉ từ method signature rằng tất cả request-response bắt buộc phải có payload trả về.

## 8. Handler nhận Flux<T>: Request-Channel

Request-channel là kênh stream hai chiều trong cùng một RSocket interaction.

~~~java
@MessageMapping("texts.upper")
public Flux<String> upper(@Payload Flux<String> inputs) {
    return inputs
            .map(String::trim)
            .map(String::toUpperCase);
}
~~~

Client:

~~~java
Flux<String> requests = Flux.just(
        "alpha", "beta", "gamma");

Flux<String> replies = requester.route("texts.upper")
        .data(requests, String.class)
        .retrieveFlux(String.class);
~~~

RSocket xử lý cả hai luồng:

- Requester gửi các phần tử của `requests`.
- Responder nhận chúng dưới dạng `Flux<String>`.
- Responder phát các phần tử đã chuyển đổi.
- Requester nhận `replies` dưới dạng `Flux<String>`.

Cả hai hướng có thể hoạt động đồng thời. Không cần đợi gửi hết toàn bộ request mới bắt đầu nhận response.

### 8.1. Input Flux<T>, output Mono<R>

Channel không nhất thiết phải trả Flux.

~~~java
@MessageMapping("readings.sum")
public Mono<Long> sum(@Payload Flux<Long> readings) {
    return readings
            .reduce(0L, Long::sum);
}
~~~

Input Many, output 1 vẫn là request-channel. Nhưng đây là stream hữu hạn: `reduce` chỉ phát kết quả khi inbound stream complete. Với stream vô hạn, kết quả sẽ không bao giờ đến nếu không có giới hạn/windowing.

### 8.2. Input Flux<T>, output Mono<Void>

~~~java
@MessageMapping("readings.store")
public Mono<Void> store(@Payload Flux<Reading> readings) {
    return readings
            .concatMap(readingService::save)
            .then();
}
~~~

Input Many, output 0 vẫn là request-channel. Client cần lựa chọn interaction tương thích và hiểu rằng channel completion có thể là một sự kiện giao thức, không phải bản tin acknowledgment theo nghiệp vụ.

### 8.3. Khi nào dùng concatMap, flatMap, limitRate?

| Operator | Tác dụng | Khi dùng |
| --- | --- | --- |
| `map` | Chuyển đổi đồng bộ từng phần tử | Logic CPU nhẹ |
| `concatMap` | Chạy từng publisher con theo thứ tự | Cần bảo toàn thứ tự, tránh ghi đè state |
| `flatMap` | Chạy publisher con đồng thời | Các message độc lập |
| `flatMapSequential` | Xử lý concurrent nhưng phát kết quả theo thứ tự | Cần throughput và ordering |
| `limitRate` | Điều chỉnh pattern yêu cầu demand lên upstream | Cần phân phối demand có kiểm soát |

Ví dụ xử lý I/O trong channel, giới hạn concurrency:

~~~java
@MessageMapping("items.enrich")
public Flux<EnrichedItem> enrich(@Payload Flux<Item> items) {
    return items.flatMap(
            enrichmentService::enrich,
            8);
}
~~~

Chọn concurrency dựa trên năng lực downstream. Không dùng `flatMap` không giới hạn cùng nguồn hot khi mỗi message có side effect lớn.

## 9. Các tham số được @MessageMapping hỗ trợ

Theo Spring RSocket annotated responders, method có thể nhận:

| Tham số | Ý nghĩa |
| --- | --- |
| `@Payload T` | Payload được decode thành kiểu Java |
| `@Payload Mono<T>` | Một payload được bọc trong Mono |
| `@Payload Flux<T>` | Chuỗi payload; interaction channel |
| `RSocketRequester` | Requester trỏ tới peer hiện tại, hỗ trợ server gọi client |
| `@DestinationVariable` | Biến trích từ route pattern |
| `@Header` | Metadata đã được đăng ký để trích xuất |
| `@Headers Map<String,Object>` | Các metadata values đã được extractor đăng ký |

### 9.1. @Payload

`@Payload` dùng để đánh dấu tham số chứa request data:

~~~java
@MessageMapping("orders.accept")
Mono<OrderResult> accept(@Payload OrderCommand command) {
    return orderService.accept(command);
}
~~~

Annotation có thể được lược bỏ cho một số tham số payload object không đơn giản; dùng tường minh giúp tránh nhầm với route variable hoặc metadata, đặc biệt với `String` và numeric types.

### 9.2. @DestinationVariable

Route có thể chứa biến:

~~~java
@MessageMapping("orders.{orderId}.status")
public Mono<String> status(
        @DestinationVariable("orderId") String orderId,
        @Payload String request) {

    return Mono.just(orderId + ":" + request);
}
~~~

Client gửi route với một biến cụ thể:

~~~java
requester.route("orders.{orderId}.status", "ORD-42")
        .data("read")
        .retrieveMono(String.class);
~~~

Biến route không thay thế payload. Ở đây `ORD-42` nằm trong routing metadata, còn `read` là data payload. Hãy kiểm tra quyền truy cập tới orderId theo user được xác thực; route variable là dữ liệu từ peer, không phải bằng chứng được phép đọc tài nguyên.

### 9.3. @Header và @Headers

RSocket không dùng HTTP headers cho từng message. `@Header` trong RSocket đọc metadata đã được Spring `MetadataExtractor` đăng ký.

Ví dụ cấu trúc:

~~~java
@MessageMapping("orders.submit")
Mono<String> submit(
        @Header("traceId") String traceId,
        @Payload OrderCommand command) {

    return orderService.submit(command, traceId);
}
~~~

Để đoạn này hoạt động với custom metadata MIME type, phải cấu hình metadata extractor và encoder/decoder phù hợp. Không mặc định rằng bất kỳ metadata entry nào cũng tự biến thành một @Header.

### 9.4. Nhận RSocketRequester

~~~java
@MessageMapping("peer.ask")
Mono<String> handle(
        @Payload String question,
        RSocketRequester peer) {

    return peer.route("client.answer")
            .data(question)
            .retrieveMono(String.class);
}
~~~

Đây là ví dụ bidirectional requester/responder, chỉ hoạt động nếu client cũng đăng ký một responder cho route `client.answer`. Một kết nối RSocket có hai bên đối xứng: server có thể phát request tới client, không chỉ trả lời.

Cần quản lý kết nối, quyền truy cập và deadline khi gọi lại client.

## 10. @ConnectMapping khác @MessageMapping như thế nào?

`@ConnectMapping` xử lý event cấp kết nối:

- SETUP frame khi bắt đầu kết nối.
- METADATA_PUSH frame trong thời gian kết nối.

Ví dụ:

~~~java
@Controller
class SetupController {

    @ConnectMapping
    public Mono<Void> connected(RSocketRequester requester) {
        return Mono.fromRunnable(() ->
                System.out.println("RSocket SETUP accepted"));
    }
}
~~~

Khác biệt quan trọng:

- `@ConnectMapping` chỉ có thể trả `void` hoặc `Mono<Void>`, không trả payload data.
- Nếu xử lý SETUP phát error, kết nối mới có thể bị từ chối.
- Khi dùng `RSocketRequester` để server chủ động gọi client ở thời điểm SETUP, không thực hiện synchronous request và chờ trong cùng handler SETUP vì kết nối chưa hoàn tất bước khởi tạo; cần decouple tác vụ đó.
- `@MessageMapping` dành cho các request interaction có route, được gửi sau khi connection setup.

Nếu cần xác thực từ lúc SETUP, nên dùng cơ chế authentication/authorization chính thức của Spring Security RSocket thay vì tự tin tưởng token chỉ vì nó xuất hiện trong metadata.

## 11. RSocketRequester phía client

`RSocketRequester` là facade cấp Spring để tạo request, encode data/metadata và decode response.

### 11.1. Tạo requester TCP

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .tcp("127.0.0.1", 7000);
~~~

Connection được thiết lập theo nhu cầu khi request thực sự chạy; builder tạo requester gắn với endpoint và cho phép chia sẻ connection giữa nhiều stream.

Trong Spring Boot, nên inject `RSocketRequester.Builder` do Boot auto-configure để có đúng `RSocketStrategies` và codec:

~~~java
@Service
public class PartnerRSocketClient {

    private final RSocketRequester requester;

    public PartnerRSocketClient(RSocketRequester.Builder builder) {
        this.requester = builder.tcp("partner.internal", 7000);
    }

    public Mono<String> greet(String name) {
        return requester.route("greet")
                .data(name)
                .retrieveMono(String.class);
    }
}
~~~

Boot cung cấp builder kiểu prototype vì builder có trạng thái. Không dùng chung một builder mutable để cấu hình nhiều requester với các setup khác nhau.

### 11.2. Tạo requester qua WebSocket transport

~~~java
URI address = URI.create("ws://localhost:8080/rsocket");

RSocketRequester requester = RSocketRequester.builder()
        .webSocket(address);
~~~

Server phải thật sự cấu hình RSocket qua WebSocket. Đây vẫn là **giao thức RSocket chạy trên WebSocket transport**, khác với WebFlux WebSocketHandler thuần.

### 11.3. API gọi tương ứng

| Nhu cầu | Requester API | Handler thường thấy |
| --- | --- | --- |
| Một request, một response | `route(...).data(x).retrieveMono(T.class)` | `Mono<T> handler(T)` |
| Một request, nhiều response | `route(...).data(x).retrieveFlux(T.class)` | `Flux<T> handler(T)` |
| Gửi không cần response data | `route(...).data(x).send()` | `Mono<Void> handler(T)` |
| Stream input và output | `route(...).data(flux, T.class).retrieveFlux(R.class)` | `Flux<R> handler(Flux<T>)` |

Chỉ định kiểu dữ liệu đầu vào cho một Publisher bằng overload `data(Publisher, Class)` (hoặc dạng ParameterizedTypeReference tương ứng) để Spring chọn encoder.

### 11.4. Sử dụng metadata

~~~java
requester.route("secure.profile")
        .metadata(token, tokenMimeType)
        .data(userId)
        .retrieveMono(Profile.class);
~~~

`metadata(value, mimeType)` thêm metadata theo MIME type. Nếu dùng composite metadata, mỗi entry có MIME type riêng. Client và server phải thỏa thuận metadata MIME type lúc SETUP.

Đừng ghi token vào log. Với production, dùng TLS và security middleware phù hợp.

## 12. Spring Boot RSocket auto-configuration

Dependency chính:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-rsocket</artifactId>
</dependency>
~~~

Starter này cung cấp RSocket implementation và các thành phần mã hóa/giải mã cần thiết. Spring Boot có thể:

- Auto-configure `RSocketStrategies`.
- Auto-configure `RSocketMessageHandler` để tìm annotated responder.
- Tạo RSocket server độc lập nếu có cấu hình port.
- Cung cấp `RSocketRequester.Builder` cho client.
- Đăng ký codec CBOR hoặc JSON theo dependency và cấu hình.

### 12.1. TCP server độc lập

~~~properties
spring.application.name=rsocket-demo
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
~~~

Khi không cấu hình HTTP server, RSocket vẫn có thể chạy độc lập với TCP server của nó. HTTP `server.port` không phải cổng RSocket TCP.

### 12.2. RSocket trên WebSocket trong WebFlux server

Với ứng dụng WebFlux và Reactor Netty:

~~~yaml
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
~~~

Tầng web cần được cấu hình như ứng dụng reactive WebFlux. RSocket sẽ chạy qua endpoint WebSocket dưới path đã cấu hình. Khi này client dùng `RSocketRequester.Builder.webSocket(URI)`.

Không phải mọi WebSocket client đều nói được RSocket. Browser `new WebSocket(...)` thuần chưa tạo RSocket SETUP frame và không thể trực tiếp gọi `@MessageMapping`; cần client RSocket-over-WebSocket phù hợp.

### 12.3. MIME và codec

Một requester có `dataMimeType(MimeType)` và `metadataMimeType(MimeType)`. Server và client phải thống nhất. Dự án Java chạy ở phần sau dùng `text/plain` cùng String để đơn giản hóa codec.

Với DTO, dùng JSON/CBOR/Protobuf theo RSocketStrategies. Không chỉ thêm DTO Java là đủ nếu connection chọn MIME không có decoder phù hợp.

## 13. Ví dụ Spring Boot Java 17+ chạy được: cả bốn interaction

Dự án gồm một RSocket TCP server với `@MessageMapping` và một Java client chạy từ command line. Toàn bộ ví dụ chỉ sử dụng `String` để tránh phụ thuộc cấu hình JSON khác nhau giữa các môi trường.

**Yêu cầu:** JDK 17+, Maven 3.6.3+ và Spring Boot **4.1.2**. Đây là bản Spring Boot stable được công bố ngày 23/10/2026; các dependency tương thích do Spring Boot BOM quản lý.

### 13.1. Cấu trúc thư mục

~~~text
rsocket-message-mapping-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/example/rsocket/RSocketDemoApplication.java
  src/main/java/example/rsocket/RSocketLessonController.java
  src/main/java/example/rsocket/RSocketClientDemo.java
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>rsocket-message-mapping-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-rsocket</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 13.3. Cấu hình TCP server

**src/main/resources/application.properties**

~~~properties
spring.application.name=rsocket-message-mapping-demo
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
~~~

### 13.4. Entry point

**src/main/java/example/rsocket/RSocketDemoApplication.java**

~~~java
package example.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RSocketDemoApplication.class, args);
    }
}
~~~

### 13.5. Annotated controller

**src/main/java/example/rsocket/RSocketLessonController.java**

~~~java
package example.rsocket;

import java.util.Locale;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class RSocketLessonController {

    // Request-Response: một String vào, một String ra.
    @MessageMapping("greet")
    public Mono<String> greet(@Payload String name) {
        return Mono.just("Hello, " + name);
    }

    // Request-Stream: một String vào, nhiều String ra.
    @MessageMapping("count")
    public Flux<String> count(@Payload String rawCount) {
        int count;
        try {
            count = Integer.parseInt(rawCount);
        }
        catch (NumberFormatException error) {
            return Flux.error(
                    new IllegalArgumentException(
                            "count must be an integer", error));
        }

        if (count < 0 || count > 100) {
            return Flux.error(new IllegalArgumentException(
                    "count must be between 0 and 100"));
        }

        return Flux.range(1, count)
                .map(index -> "n=" + index);
    }

    // Request-Channel: Flux vào, Flux ra.
    @MessageMapping("upper")
    public Flux<String> upper(@Payload Flux<String> input) {
        return input.map(text ->
                "UPPER:" + text.toUpperCase(Locale.ROOT));
    }

    // Fire-and-Forget: một event vào, không trả response data.
    @MessageMapping("audit")
    public Mono<Void> audit(@Payload String event) {
        return Mono.fromRunnable(() ->
                System.out.println("AUDIT:" + event));
    }

    // Request-Response với route variable.
    @MessageMapping("greet.{lang}")
    public Mono<String> greetWithLanguage(
            @DestinationVariable("lang") String lang,
            @Payload String name) {

        String prefix = "vi".equals(lang)
                ? "Xin chao, "
                : "Hello, ";

        return Mono.just(prefix + name);
    }
}
~~~

Giải thích:

- `greet` nhận một String và phát một String: **request-response**.
- `count` nhận một String số lượng và phát nhiều String: **request-stream**.
- `upper` nhận `Flux<String>` và trả `Flux<String>`: **request-channel**.
- `audit` trả `Mono<Void>`: dùng như **fire-and-forget** từ client.
- `greetWithLanguage` minh họa cách đọc biến `lang` từ route metadata.

Ví dụ giới hạn count tối đa 100 để tránh một yêu cầu không hợp lệ gây phát lượng dữ liệu quá lớn. Logic production cần authorization, rate limit và quotas theo nghiệp vụ.

### 13.6. Client Java gọi các route

**src/main/java/example/rsocket/RSocketClientDemo.java**

~~~java
package example.rsocket;

import java.time.Duration;
import java.util.List;

import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;

public class RSocketClientDemo {

    public static void main(String[] args) {
        RSocketRequester requester = RSocketRequester.builder()
                .dataMimeType(MimeTypeUtils.TEXT_PLAIN)
                .tcp("127.0.0.1", 7000);

        try {
            // 1. Request-Response
            String greeting = requester.route("greet")
                    .data("RSocket")
                    .retrieveMono(String.class)
                    .block(Duration.ofSeconds(5));

            System.out.println("response=" + greeting);

            // 2. Request-Stream
            List<String> stream = requester.route("count")
                    .data("3")
                    .retrieveFlux(String.class)
                    .collectList()
                    .block(Duration.ofSeconds(5));

            System.out.println("stream=" + stream);

            // 3. Request-Channel
            List<String> channel = requester.route("upper")
                    .data(
                            Flux.just("one", "two", "three"),
                            String.class)
                    .retrieveFlux(String.class)
                    .collectList()
                    .block(Duration.ofSeconds(5));

            System.out.println("channel=" + channel);

            // 4. Route variable
            String localized = requester
                    .route("greet.{lang}", "vi")
                    .data("Ban")
                    .retrieveMono(String.class)
                    .block(Duration.ofSeconds(5));

            System.out.println("route-variable=" + localized);

            // 5. Fire-and-Forget
            requester.route("audit")
                    .data("opened")
                    .send()
                    .block(Duration.ofSeconds(5));

            System.out.println("fnf=sent");
        }
        finally {
            requester.dispose();
        }
    }
}
~~~

**Lưu ý:** `block(Duration)` chỉ dùng ở entry point command-line cho demo để đợi kết quả; trong Spring reactive service/handler không gọi block. `dispose()` đóng requester ở cuối chương trình.

### 13.7. Chạy server và client

Mở terminal thứ nhất tại thư mục dự án:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

Khi server đã lắng nghe TCP port 7000, mở terminal thứ hai:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.rsocket.RSocketClientDemo
~~~

**Các dòng stdout nghiệp vụ dự kiến của client:**

~~~text
response=Hello, RSocket
stream=[n=1, n=2, n=3]
channel=[UPPER:ONE, UPPER:TWO, UPPER:THREE]
route-variable=Xin chao, Ban
fnf=sent
~~~

Maven có thể in thêm log tùy cấu hình. Thứ tự các dòng nghiệp vụ client là như trên vì client chờ từng request hoàn tất trước khi thực hiện request kế tiếp.

**Server có thể in:**

~~~text
AUDIT:opened
~~~

Dòng `AUDIT:opened` ở server là side effect của fire-and-forget; thời điểm nó xuất hiện so với dòng `fnf=sent` ở client không được bảo đảm. `fnf=sent` chỉ xác nhận thao tác gửi theo client API, không xác nhận event đã được xử lý bền vững.

### 13.8. Khi nào nên thay String bằng DTO?

Với API thực tế, hãy dùng record Java và codec JSON/CBOR:

~~~java
public record FindProductRequest(String productId) {
}

public record ProductReply(String id, String name) {
}

@MessageMapping("products.find")
public Mono<ProductReply> find(
        @Payload FindProductRequest request) {

    return productService.findById(request.productId());
}
~~~

Đây là đoạn mở rộng, cần service do ứng dụng định nghĩa và codec tương ứng. Spring Boot RSocket starter hỗ trợ cấu hình codec, nhưng hai bên cần thống nhất MIME tại SETUP. Không giả định server sẽ hiểu bất kỳ DTO nào khi client đang gửi text/plain.

## 14. Xử lý lỗi reactive trong @MessageMapping

### 14.1. Error là terminal signal

~~~java
@MessageMapping("orders.find")
public Mono<Order> find(@Payload String id) {
    return orderRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(id)));
}
~~~

Nếu publisher phát error, framework chuyển lỗi vào RSocket error semantics của interaction. Client nhận error signal ở `retrieveMono` hoặc `retrieveFlux`.

Đừng trả một Object lỗi như thể nó là response thành công nếu contract không có field phân biệt. Nên chuẩn hóa mã lỗi, cách deserialize và chính sách retry.

### 14.2. Validation trong reactive flow

~~~java
@MessageMapping("count.safe")
public Flux<Integer> safeCount(@Payload String raw) {
    return Mono.fromCallable(() -> Integer.parseInt(raw))
            .flatMapMany(count -> {
                if (count < 1 || count > 1000) {
                    return Flux.error(new IllegalArgumentException(
                            "count must be between 1 and 1000"));
                }
                return Flux.range(1, count);
            });
}
~~~

`Mono.fromCallable` trì hoãn parsing tới lúc subscribe và chuyển exception thành error signal. Không cần tạo thread riêng cho phép toán parsing nhỏ như vậy.

Với validation DTO bằng Bean Validation, cần có dependency và argument validation configuration phù hợp. Không coi @Payload một mình là đủ để xác thực input.

### 14.3. Xử lý lỗi có thể khôi phục bên trong channel

~~~java
@MessageMapping("texts.safeUpper")
public Flux<String> safeUpper(@Payload Flux<String> input) {
    return input.concatMap(text -> {
        if (text.length() > 256) {
            return Mono.just("ERROR:too-long");
        }
        return Mono.just(text.toUpperCase(Locale.ROOT));
    });
}
~~~

Nếu lỗi thuộc một message và protocol cho phép trả error value rồi tiếp tục, xử lý ở inner publisher để không làm cả channel phát terminal error.

Ngược lại, lỗi authentication hoặc protocol nguy hiểm nên được truyền ra như terminal error và kết thúc stream.

### 14.4. Không nuốt mọi exception

Không nên:

~~~java
return service.call(input)
        .onErrorResume(error -> Mono.empty());
~~~

Dòng này làm client mất phân biệt giữa “không có dữ liệu” và “service hỏng”. Chỉ dùng fallback với exception cụ thể khi nghiệp vụ có quy định, đồng thời giữ metric/log đủ để điều tra.

## 15. Demand, timeout, cancellation và backpressure

### 15.1. Giới hạn phần tử ở requester

~~~java
Flux<String> firstThree = requester.route("events")
        .data("topic-a")
        .retrieveFlux(String.class)
        .take(3);
~~~

Requester chỉ cần ba phần tử; sau đó `take` hủy upstream stream chưa hoàn tất. RSocket có cơ chế `CANCEL` để thông báo tới responder.

### 15.2. Giới hạn time

~~~java
Mono<ProductReply> result = requester.route("products.find")
        .data(request)
        .retrieveMono(ProductReply.class)
        .timeout(Duration.ofSeconds(3));
~~~

Timeout ở Reactor Publisher có thể cancel request phía client; server có thể vẫn đã thực hiện side effect trước khi cancellation tới. Với action ghi dữ liệu, thiết kế idempotency key và retry policy phù hợp.

Với `Flux.timeout(Duration)`, timer theo khoảng chờ giữa các phần tử; không phải deadline tổng của stream vô hạn. Không nhầm với timeout connect/SETUP hoặc keepalive của connector.

### 15.3. Stream vô hạn và nguồn hot

RSocket request-stream/channel hỗ trợ demand xuyên network, nhưng một upstream hot source có thể phát nhanh hơn việc xử lý demand. Dùng queue hữu hạn hoặc policy drop/coalesce phù hợp:

- Dữ liệu trạng thái có thể chỉ cần bản mới nhất.
- Event bắt buộc không được mất cần persistence/replay.
- Command có side effect cần giới hạn concurrency và reject rõ ràng khi quá tải.
- Không dùng `onBackpressureBuffer()` không giới hạn cho hàng nghìn client.

### 15.4. Bảo toàn thứ tự

`concatMap` giữ thứ tự request khi mỗi phần tử phải xử lý I/O. `flatMap` có thể đổi thứ tự kết quả. Chọn operator dựa trên contract, không chỉ vì throughput.

Với channel hai chiều, không tự giả định một response phải tương ứng vị trí một input nếu responder xử lý concurrent. Nếu cần request-response correlation trong cùng channel, đưa `requestId` vào payload và echo lại trong response DTO.

## 16. Kết nối, quản lý tài nguyên và bảo mật

### 16.1. Một connection, nhiều request

Sau SETUP, một TCP/WebSocket connection có thể mang nhiều request stream. Không tạo connection mới cho từng business request nếu không có lý do. Reuse requester và quản lý lifecycle phù hợp:

- Tạo requester khi cấu hình service.
- Tái sử dụng cho các call.
- Dispose requester khi component/application shutdown, không phải sau mỗi call nếu nó là shared bean.
- Thiết kế reconnect/backoff, keepalive, resume và leasing theo yêu cầu vận hành.

### 16.2. @ConnectMapping và server gọi client

Server có thể nhận tham số `RSocketRequester` trong annotated handler để gọi lại client. Nhưng client phải có responder route tương ứng. Không gọi và đợi synchronous round-trip trong SETUP handler trước khi SETUP hoàn tất.

Nếu muốn server chủ động push, cần định nghĩa rõ route, quyền truy cập và lifecycle của connected requester; khi connection bị đóng, dọn registry và cancel stream.

### 16.3. Authentication và authorization

- Dùng TLS khi truyền credential hoặc dữ liệu nhạy cảm.
- Thiết lập authentication phù hợp với Spring Security RSocket và metadata authentication.
- Authorize mỗi route và resource, không chỉ dựa vào route name.
- Không tin `@DestinationVariable` hoặc payload ID là bằng chứng được phép truy cập.
- Kiểm soát thông tin nào được đưa vào logs/tracing.
- Đặt giới hạn kích thước frame, payload, số request stream và throughput.
- Không expose TCP RSocket port công khai nếu không cần.

Một route như `orders.{id}.find` phải kiểm tra user được phép truy cập order đó. CORS là browser policy cho HTTP/WebSocket và không thể thay cho RSocket authentication/authorization ở transport phù hợp.

### 16.4. Codec và buffer

Nếu dùng low-level `io.rsocket.Payload` hoặc buffer của Netty, phải quản lý reference counting. Spring annotated responders với DTO và codec thông thường giúp tránh thao tác buffer thủ công. Nếu giữ pooled buffer qua async boundary, tuân thủ ownership, retain/release theo API.

## 17. Kiểm thử @MessageMapping

Một bộ test có ý nghĩa nên có:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Request-Response hợp lệ | Mono phát một value đúng kiểu, complete |
| Request-Stream hữu hạn | Flux phát đúng thứ tự và số phần tử |
| Fire-and-Forget | Requester send hoàn tất; xác nhận business side effect riêng |
| Request-Channel | Flux input được responder nhận, Flux output trả đúng contract |
| Route variable | Giá trị trích từ route metadata đúng |
| Route không tồn tại | Requester nhận lỗi route/handler phù hợp |
| Payload sai MIME | Decoder báo lỗi, không xử lý nhầm dữ liệu |
| Input không hợp lệ | Phát application error rõ ràng |
| Client cancel stream | Responder ngừng phát và dọn tài nguyên |
| Slow requester | Demand không gây buffer vô hạn |
| Connection drop/keepalive | Reconnect hoặc error theo policy |
| Authentication/authorization | Unauthorized route bị từ chối |
| Side effect khi retry | Idempotency bảo vệ dữ liệu khỏi lặp |

Có thể dùng `StepVerifier` để test publisher của service, ví dụ:

~~~java
StepVerifier.create(
        Flux.range(1, 3).map(value -> "n=" + value))
        .expectNext("n=1", "n=2", "n=3")
        .verifyComplete();
~~~

Đây là unit-test snippet; cần `reactor-test` ở test scope. Kiểm thử thực tế RSocket nên gọi bằng `RSocketRequester` qua TCP/WebSocket để xác nhận routing metadata, SETUP, codec và interaction đúng trên network.

### 17.1. Vì sao không chỉ test method Java trực tiếp?

Gọi `controller.greet("Mai")` như một method thông thường chỉ xác nhận logic Java. Nó không kiểm tra:

- Route metadata có match `@MessageMapping` hay không.
- Client có chọn đúng interaction type không.
- Codec có decode được payload không.
- Setup MIME có tương thích không.
- RSocket request-stream/channel có propagate demand và cancellation không.

Vì vậy, dùng cả unit test cho domain logic và integration test qua requester.

## 18. Các lỗi phổ biến khi dùng @MessageMapping, Mono và Flux

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi @MessageMapping là REST endpoint | Không có HTTP GET/POST route tương ứng | Gọi bằng RSocketRequester với route metadata |
| Chỉ nhìn Flux return để kết luận channel | Nhầm request-stream với request-channel | Xem cardinality input và output |
| Nhận Flux input nhưng client gọi request-response | Sai interaction model | Dùng request-channel với data(Publisher, Class) |
| Trả Mono<Void> rồi cho rằng requester đã nhận ACK | FNF không xác nhận business success | Dùng request-response với ACK DTO |
| Gọi subscribe() trong handler | Tách công việc khỏi lifecycle và lỗi | Trả Mono/Flux trực tiếp |
| Gọi block() trong handler | Chặn reactive event-loop | Compose publisher |
| Dùng collectList cho stream vô hạn | Tích lũy bộ nhớ và không hoàn tất | Process từng phần tử |
| Dùng flatMap cho command phụ thuộc thứ tự | Có thể đảo thứ tự side effect | Dùng concatMap |
| Cho phép Flux.range với count không giới hạn | Có thể gây tải quá lớn | Validate và đặt limits |
| Quên dataMimeType hoặc codec | Không encode/decode được DTO | Đồng bộ MIME và RSocketStrategies |
| Đặt String route trong payload | Responder không tìm được route | Dùng route(...) metadata |
| Đọc @Header như HTTP header | Thiếu metadata extractor/mime | Cấu hình metadata extractor |
| Gọi requester trong @ConnectMapping và block | Có thể deadlock/chặn SETUP | Decouple asynchronous post-setup |
| Dùng một mutable requester builder cho nhiều cấu hình | Lẫn codec/setup/route | Dùng Boot prototype builder |
| Retry POST-like action sau timeout không idempotency | Có thể tạo tác dụng phụ trùng | Dùng idempotency key |
| Tin route variable là quyền truy cập | Lộ dữ liệu của user khác | Authorize từng resource |
| Buffer infinite event stream | Memory pressure/leak | Bounded queue/backpressure policy |
| Quên dispose requester ở CLI | Giữ connection/tài nguyên | Dispose ở boundary shutdown |
| Chỉ unit test method annotated | Bỏ sót route/codec/interaction | Integration test qua RSocketRequester |

## 19. Checklist production

- [ ] Định nghĩa route RSocket nhất quán theo namespace.
- [ ] Ghi rõ interaction type cho mỗi route trong API contract.
- [ ] Phân biệt cardinality input và output trước khi chọn Mono/Flux.
- [ ] Dùng @Payload, @DestinationVariable và metadata đúng trách nhiệm.
- [ ] Không dùng @MessageMapping như HTTP route.
- [ ] Đặt RSocket server port/transport rõ trong configuration.
- [ ] Đồng bộ dataMimeType/metadataMimeType và codecs.
- [ ] Tái sử dụng RSocketRequester và dispose theo application lifecycle.
- [ ] Không block hoặc subscribe thủ công trong annotated handlers.
- [ ] Giới hạn count, payload size, concurrency và stream duration theo SLA.
- [ ] Chọn concatMap khi thứ tự quan trọng.
- [ ] Không aggregate stream vô hạn.
- [ ] Có backpressure và bounded queue cho hot sources.
- [ ] Truyền và xử lý error/cancel đúng.
- [ ] Fire-and-forget không bị nhầm với business acknowledgment.
- [ ] Có timeout, retry/backoff và idempotency phù hợp.
- [ ] Có authentication, authorization, TLS và quota.
- [ ] Không log token hay payload nhạy cảm.
- [ ] Test bốn interaction type bằng client qua transport thật.
- [ ] Theo dõi connection count, request count, latency, errors, cancellation và queue depth.

## 20. Tự kiểm tra

**Câu 1.** `@MessageMapping` trong RSocket định tuyến theo gì?

Theo routing metadata của RSocket request, không theo HTTP URL/method.

**Câu 2.** Handler nhận `String`, trả `Mono<String>` thuộc interaction nào?

Request-response vì input có một payload và output có một response value.

**Câu 3.** Handler nhận `String`, trả `Flux<String>` thuộc interaction nào?

Request-stream vì input một payload, output nhiều phần tử.

**Câu 4.** Handler nhận `Flux<String>`, trả `Flux<String>` thuộc interaction nào?

Request-channel vì input là stream.

**Câu 5.** Handler nhận `Flux<String>`, trả `Mono<Long>` có phải request-response không?

Không. Input Many nên đây là request-channel, dù output chỉ một phần tử.

**Câu 6.** Fire-and-forget requester dùng method gì?

`send()`, trả `Mono<Void>` biểu diễn gửi, không xác nhận business processing.

**Câu 7.** Dùng API nào để client nhận nhiều response?

`retrieveFlux(ResponseType.class)`.

**Câu 8.** Tại sao `@Payload` hữu ích với String?

Nó đánh dấu rõ tham số là data payload, tránh nhầm với route variable hoặc metadata.

**Câu 9.** `@DestinationVariable` đọc dữ liệu từ đâu?

Từ biến trong route pattern đã match, nằm trong routing metadata.

**Câu 10.** `@Header` có đọc HTTP headers không?

Không. Trong RSocket nó đọc metadata đã được MetadataExtractor đăng ký.

**Câu 11.** `@ConnectMapping` xử lý sự kiện nào?

SETUP và METADATA_PUSH; handler chỉ trả void hoặc Mono<Void>.

**Câu 12.** Vì sao không gọi block trong RSocket handler?

Vì block làm nghẽn reactive thread và phá cơ chế xử lý bất đồng bộ.

**Câu 13.** Backpressure trong RSocket request-stream hoạt động thế nào?

Requester báo demand; responder phát theo demand và RSocket truyền thông tin đó qua các control frame như REQUEST_N.

**Câu 14.** Khi client dùng `take(3)` trên stream, điều gì có thể xảy ra?

Sau ba phần tử, client cancel upstream stream; cancellation được truyền tới responder.

**Câu 15.** Server trả Mono.empty nghĩa là gì?

Hoàn tất mà không phát response data, không phải string rỗng hay HTTP status.

**Câu 16.** Vì sao phải có integration test qua RSocketRequester?

Để kiểm tra route metadata, SETUP, MIME/codec, interaction model, demand và transport chứ không chỉ logic method Java.

## 21. Tài liệu tham khảo chính thức

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): protocol overview, RSocketRequester, annotated responders, @MessageMapping, @ConnectMapping và bảng cardinality.
- [Spring Framework — RSocketRequester JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html): route, data, retrieveMono, retrieveFlux, send, dispose.
- [Spring Framework — RSocketMessageHandler JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html): phát hiện controller và xử lý annotated RSocket messages.
- [Spring Framework — MessageMapping JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/MessageMapping.html): message route mapping và method-level contract.
- [Spring Framework — ConnectMapping JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/ConnectMapping.html): xử lý RSocket SETUP/METADATA_PUSH.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/4.1/reference/messaging/rsocket.html): starter, auto-configuration, TCP/WebSocket server, RSocketRequester.Builder và codecs.
- [Spring Boot 4.1.2 Release Announcement](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/): bản stable ngày 23/10/2026.
- [RSocket Protocol — Interaction Models](https://rsocket.io/about/protocol/): request-response, request-stream, request-channel, fire-and-forget và REQUEST_N/CANCEL.
- [Reactor Core — Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): stream, backpressure, concatMap, flatMap, cancellation.
- [Reactor Core — Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): single-value publisher, error và completion.

**Ghi nhớ:** `@MessageMapping` định tuyến request RSocket theo metadata. Handler `Mono<T>` với input đơn thường là request-response; handler `Flux<T>` với input đơn là request-stream; `Mono<Void>` thường dùng cho fire-and-forget; và **bất kỳ handler nhận `Flux<T>` payload đều thuộc request-channel**. Hãy xác định input/output cardinality, dùng đúng `RSocketRequester` API, để framework quản lý subscription, và bảo vệ stream bằng validation, backpressure, timeout, cancellation và authorization.