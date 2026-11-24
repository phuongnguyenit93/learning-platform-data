# Ứng dụng Web

## Vòng lặp sự kiện và vòng đời một yêu cầu HTTP

Trong một ứng dụng web reactive, server có thể tiếp nhận nhiều kết nối HTTP mà không cần giữ một thread riêng cho mỗi yêu cầu trong suốt thời gian chờ I/O. Thay vào đó, các event-loop thread xử lý những sự kiện sẵn sàng như dữ liệu socket có thể đọc, socket có thể ghi hoặc một tác vụ đã hoàn tất. Khi một yêu cầu cần chờ cơ sở dữ liệu, dịch vụ khác hoặc timer, pipeline reactive có thể tạm ngừng phát tín hiệu và tiếp tục khi kết quả sẵn sàng.

Với Spring WebFlux chạy trên Reactor Netty, vòng lặp sự kiện là nền tảng của mô hình I/O non-blocking. Một yêu cầu HTTP đi qua server adapter, chuỗi filter, bộ điều phối handler, controller và các thành phần ghi response. Các bước này phối hợp bằng những kiểu như **Mono** và **Flux**. Hiểu luồng đi của yêu cầu và vai trò của event loop giúp tránh chặn thread quan trọng, quản lý cancellation và tận dụng backpressure khi đọc hoặc ghi dữ liệu.

### 1. Event loop xử lý nhiều kết nối bằng các sự kiện sẵn sàng

Event loop là vòng lặp liên tục chờ và xử lý các sự kiện I/O. Thay vì chặn một thread cho từng socket đang chờ dữ liệu, event loop theo dõi nhiều kết nối và chỉ xử lý kết nối có sự kiện cần phục vụ.

Mô hình khái quát:

~~~text
Nhiều kết nối HTTP
       |
       v
 Bộ theo dõi sự kiện I/O
       |
       v
  Event-loop thread
       |
       +---- đọc request A
       |
       +---- ghi response B
       |
       +---- tiếp tục request C
       |
       +---- xử lý sự kiện socket D
~~~

Một event-loop thread có thể luân phiên xử lý nhiều kết nối. Khi một request chờ I/O non-blocking, thread có thể quay lại xử lý sự kiện của request khác. Điều này giúp sử dụng thread hiệu quả khi ứng dụng có nhiều kết nối đồng thời và phần lớn thời gian dành cho chờ I/O.

Event loop không làm cho mọi công việc trở nên bất đồng bộ. Một phép tính CPU-bound kéo dài hoặc lời gọi JDBC blocking vẫn chiếm thread trong lúc thực thi. Nếu công việc đó chạy trên event-loop thread, các kết nối khác được gán cho cùng event loop có thể bị chậm theo.

### 2. Mô hình thread-per-request và mô hình event loop

Trong mô hình thread-per-request truyền thống, server thường gắn một thread xử lý với mỗi yêu cầu đang hoạt động. Khi thread gọi API blocking, nó chờ kết quả và không thể làm công việc khác trong khoảng thời gian đó.

Trong mô hình event loop, một số thread xử lý nhiều kết nối. Khi gặp thao tác I/O non-blocking, pipeline đăng ký tiếp tục khi kết quả sẵn sàng thay vì giữ event-loop thread chờ phản hồi.

| Đặc điểm | Thread-per-request với I/O blocking | Event loop với I/O non-blocking |
| --- | --- | --- |
| Phân bổ thread | Thường có thread xử lý cho mỗi request đang hoạt động | Một nhóm event-loop thread phục vụ nhiều kết nối |
| Khi chờ I/O | Thread request bị giữ trong trạng thái chờ | Event loop có thể xử lý sự kiện của kết nối khác |
| Tác vụ blocking | Có thể chặn thread của request | Nếu chạy trên event loop, có thể làm chậm nhiều request |
| Điều phối kết quả | Tiếp tục sau khi lời gọi blocking trả về | Callback/tín hiệu tiếp tục pipeline khi I/O sẵn sàng |
| Phù hợp | Ứng dụng đồng bộ và thư viện blocking | Ứng dụng có API non-blocking và pipeline reactive |

Hai mô hình đều có thể phục vụ HTTP. Reactive không tự động nhanh hơn trong mọi trường hợp; lợi ích phụ thuộc tỷ lệ chờ I/O, cách dùng thread, chi phí xử lý và khả năng mở rộng của các dịch vụ phụ thuộc.

### 3. Vòng đời một yêu cầu HTTP trong Spring WebFlux

Khi dùng Reactor Netty làm server, một yêu cầu thường đi qua các chặng sau:

~~~text
Client gửi HTTP request
          |
          v
Reactor Netty nhận bytes từ socket
          |
          v
Chuyển thành ServerHttpRequest / ServerHttpResponse
          |
          v
HttpHandler và chuỗi WebFilter
          |
          v
DispatcherHandler
          |
          +--> HandlerMapping tìm handler
          |
          +--> HandlerAdapter gọi handler/controller
          |
          +--> HandlerResultHandler xử lý kết quả
          |
          v
Encode body và ghi response non-blocking
          |
          v
HTTP response hoàn tất hoặc kết thúc bằng lỗi
~~~

Các thành phần quan trọng:

- **Reactor Netty server:** nhận và gửi dữ liệu qua socket bằng mô hình I/O non-blocking.
- **HttpHandler:** điểm vào của Spring WebFlux để xử lý request/response.
- **WebFilter:** thành phần bao quanh quá trình xử lý, thường dùng cho xác thực, CORS, logging hoặc correlation ID.
- **DispatcherHandler:** điều phối request đến handler phù hợp.
- **HandlerMapping:** tìm controller hoặc handler dựa trên route và điều kiện request.
- **HandlerAdapter:** gọi handler đã tìm thấy, ví dụ phương thức controller.
- **HandlerResultHandler:** xử lý giá trị trả về và ghi response, bao gồm các kiểu reactive.

Chi tiết triển khai có thể khác khi WebFlux chạy trên server adapter khác. Tuy nhiên, vòng đời xử lý ở tầng Spring vẫn xoay quanh việc tìm handler, gọi handler, xử lý kết quả và ghi response.

### 4. Từ controller đến Publisher

Trong WebFlux, controller thường trả về một Publisher thay vì tự chờ kết quả rồi trả về đối tượng đồng bộ. **Mono** phù hợp với response có không hoặc một phần tử; **Flux** phù hợp với response có nhiều phần tử hoặc stream dữ liệu.

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
class OrderController {
    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/orders/{id}")
    Mono<OrderView> findOne(@PathVariable String id) {
        return orderService.findById(id);
    }

    @GetMapping("/orders")
    Flux<OrderView> findAll() {
        return orderService.findAll();
    }
}
~~~

Khi framework xử lý kết quả trả về, nó đăng ký vào Publisher và kết nối tín hiệu với quá trình tạo HTTP response. Controller không cần tự gọi **subscribe()**. Framework sở hữu subscription ở ranh giới HTTP và có thể điều phối vòng đời của response.

Nếu controller gọi **subscribe()** bên trong rồi trả về một response khác, công việc đó trở thành một subscription tách rời. Framework không còn điều khiển đầy đủ lỗi, cancellation và thời điểm hoàn tất của công việc phụ. Hãy trả Publisher từ controller và kết hợp các bước bằng toán tử reactive.

### 5. Khi nào request được xem là hoàn tất?

Một yêu cầu HTTP reactive chưa hoàn tất chỉ vì phương thức controller đã trả về một **Mono** hoặc **Flux**. Publisher có thể chưa phát dữ liệu, đang chờ I/O hoặc đang stream nhiều phần tử. Response chỉ có thể kết thúc sau khi quá trình ghi body hoàn tất, hoặc bị kết thúc bởi lỗi hay cancellation.

Với một **Mono**, vòng đời thường có dạng:

~~~text
HTTP request
    |
    v
Controller trả Mono<Response>
    |
    v
Framework subscribe
    |
    +---- onNext(response) ---> encode và ghi body
    |
    +---- onComplete ---------> hoàn tất response
    |
    +---- onError ------------> xử lý lỗi HTTP
~~~

Với **Mono.empty()**, không có phần tử response để ghi. Ứng dụng cần xác định ngữ nghĩa phù hợp, chẳng hạn trả 404 bằng cách chuyển thành lỗi domain hoặc dùng một response rỗng có status được chỉ định. Không nên giả định Mono rỗng tự động mang nghĩa HTTP 404.

Với **Flux**, framework có thể ghi nhiều phần tử. Nếu response là JSON thông thường, codec có thể tuần tự hóa các phần tử theo định dạng tương ứng. Nếu response là stream dài hạn như Server-Sent Events, kết nối có thể tiếp tục mở cho đến khi nguồn hoàn tất, lỗi hoặc client ngắt kết nối.

### 6. Đọc request body theo kiểu reactive

WebFlux có thể biểu diễn request body thành **Mono** hoặc **Flux**. Với một body JSON đơn lẻ, controller thường nhận một đối tượng đã được codec giải mã:

~~~java
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@PostMapping("/orders")
Mono<OrderView> create(@RequestBody Mono<CreateOrder> request) {
    return request.flatMap(orderService::create);
}
~~~

Body được giải mã và chuyển thành Mono. **flatMap** nối kết quả giải mã với thao tác tạo đơn hàng, giữ nguyên pipeline bất đồng bộ. Controller không cần block để lấy đối tượng request.

Với dữ liệu lớn hoặc luồng nhiều phần tử, có thể nhận body dạng Flux:

~~~java
@PostMapping("/events/import")
Mono<ImportSummary> importEvents(
    @RequestBody Flux<IncomingEvent> events
) {
    return importService.process(events);
}
~~~

Khi service tiêu thụ Flux theo demand, việc đọc body có thể được điều tiết theo khả năng downstream. Tránh chuyển toàn bộ luồng thành một danh sách trong bộ nhớ nếu dữ liệu lớn và có thể xử lý từng phần tử.

### 7. Ghi response và backpressure

Khi response body là một Flux, tốc độ tạo dữ liệu có thể khác tốc độ client nhận dữ liệu. Backpressure giúp các Publisher tuân theo Reactive Streams phối hợp demand từ downstream. Khi tầng ghi response chưa sẵn sàng, nhu cầu được truyền ngược qua pipeline để điều tiết việc phát phần tử tiếp theo.

Ví dụ một endpoint stream sự kiện:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
class EventController {
    private final EventService eventService;

    EventController(EventService eventService) {
        this.eventService = eventService;
    }

    @GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    Flux<ServerSentEvent<EventView>> events() {
        return eventService.stream()
            .map(event -> ServerSentEvent.builder(event).build());
    }
}
~~~

Trong endpoint SSE, mỗi phần tử Flux có thể trở thành một event được gửi đến client. Kết nối thường tồn tại lâu hơn một response JSON thông thường. Nguồn cần có chính sách giới hạn hàng đợi và xử lý client chậm; nếu adapter nguồn không hỗ trợ demand, cần chọn chiến lược buffer, drop hoặc latest phù hợp.

Backpressure không bảo đảm client luôn đọc dữ liệu nhanh. Nó giúp các thành phần reactive phối hợp demand, nhưng các nguồn không tuân theo giao thức hoặc các hàng đợi do ứng dụng tự tạo vẫn cần giới hạn. Với stream lâu dài, cần xem xét heartbeat, timeout, reconnect và chính sách replay theo yêu cầu sản phẩm.

### 8. WebFilter nằm ở đâu trong vòng đời request?

**WebFilter** bao quanh việc xử lý request. Filter có thể đọc metadata, xác thực, ghi log hoặc bổ sung thông tin vào Reactor Context. Một filter reactive trả về **Mono<Void>** biểu diễn quá trình xử lý tiếp theo và hoàn tất khi response chain kết thúc.

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
class RequestTraceFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        String requestId =
            exchange.getRequest().getId();

        return chain.filter(exchange)
            .contextWrite(context ->
                context.put("requestId", requestId)
            );
    }
}
~~~

Filter không nên block để xác thực hoặc truy vấn metadata. Nếu cần gọi một dịch vụ xác thực reactive, hãy kết hợp Publisher đó với **flatMap** trước khi gọi chain. Nếu dùng thư viện blocking, cần trì hoãn lời gọi và điều phối trên scheduler phù hợp.

Thứ tự các filter ảnh hưởng thứ tự bao quanh request. Một filter có thể thực hiện công việc trước khi gọi chain, sau đó quan sát completion hoặc lỗi của chain bằng các toán tử như **doOnSuccess**, **doOnError** hoặc **doFinally**. Không nên xem callback hoàn tất là thời điểm dữ liệu đã được client xử lý hoàn toàn; nó phản ánh vòng đời xử lý ở phía server.

### 9. Xử lý lỗi và ánh xạ thành HTTP response

Lỗi trong pipeline có thể xuất hiện khi gọi dịch vụ, truy cập dữ liệu, giải mã request hoặc xử lý nghiệp vụ. WebFlux cho phép xử lý lỗi trong pipeline bằng **onErrorResume**, hoặc ánh xạ lỗi tập trung bằng **WebExceptionHandler** và **@ExceptionHandler** trong **@ControllerAdvice**.

Ví dụ chuyển lỗi domain thành status HTTP:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {
    @ExceptionHandler(OrderNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    ErrorBody handleNotFound(OrderNotFoundException error) {
        return new ErrorBody("ORDER_NOT_FOUND", error.getMessage());
    }
}
~~~

Với cách xử lý tập trung, controller có thể giữ pipeline nghiệp vụ rõ ràng và để exception handler ánh xạ loại lỗi đã biết thành response phù hợp. Lỗi không được xử lý vẫn đi đến cơ chế xử lý lỗi mặc định của framework/server.

Không nên bắt mọi lỗi rồi trả HTTP 200 với body rỗng. Cần giữ phân biệt giữa lỗi xác thực, lỗi không tìm thấy, lỗi xung đột, lỗi giới hạn tốc độ và lỗi hệ thống. Cũng cần tránh đưa stack trace hoặc thông tin nhạy cảm vào response công khai.

### 10. Blocking trên event loop làm ảnh hưởng nhiều request

Một ứng dụng WebFlux có thể dùng event-loop thread để xử lý request. Nếu controller hoặc service gọi API blocking trực tiếp, thread đang xử lý có thể bị giữ lại:

~~~java
// Không phù hợp trên event-loop thread:
Order order = jdbcRepository.findById(orderId);
return Mono.just(toView(order));
~~~

Đoạn mã trên thực hiện truy vấn JDBC trước khi tạo Mono. Dù sau đó bọc kết quả bằng **Mono.just**, lời gọi blocking vẫn đã xảy ra. Khi chạy trên event loop, nó có thể làm chậm các request khác được xử lý trên cùng nhóm thread.

Nếu chưa thể thay JDBC bằng R2DBC hoặc một client non-blocking, hãy trì hoãn lời gọi và chuyển nó sang scheduler phù hợp:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<OrderView> findOrder(String orderId) {
    return Mono.fromCallable(() ->
            jdbcRepository.findById(orderId)
        )
        .subscribeOn(Schedulers.boundedElastic())
        .map(this::toView);
}
~~~

**fromCallable** trì hoãn lời gọi cho đến khi có subscription và chuyển exception thành **onError**. **subscribeOn(boundedElastic())** điều phối subscription đến nguồn blocking trên scheduler phù hợp. Đây là giải pháp tích hợp chuyển tiếp; khi có thể, dùng driver reactive thật để tránh giữ thread cho thao tác chờ I/O.

Không dùng **publishOn** sau khi lời gọi blocking đã xảy ra để kỳ vọng chuyển lời gọi đó sang scheduler khác. Scheduler phải được đặt quanh nguồn lazy để thao tác blocking được thực hiện ở đúng nơi.

### 11. Cancellation khi client ngắt kết nối

Client có thể hủy request bằng cách đóng kết nối, hủy subscription ở client hoặc ngừng nhận stream. Khi server nhận biết response không còn được tiêu thụ, cancellation có thể được truyền ngược qua pipeline reactive.

Điều này giúp dừng các Publisher còn hoạt động, giải phóng tài nguyên và tránh tiếp tục tính toán cho một response không còn người nhận. Tuy nhiên, cancellation không phải rollback: một lệnh ghi dữ liệu đã được database commit hoặc một thông báo đã gửi ra ngoài có thể không thể thu hồi.

Các thao tác có tài nguyên cần gắn cleanup với vòng đời Publisher, ví dụ dùng **usingWhen** cho tài nguyên reactive. Với lời gọi blocking không hỗ trợ interrupt hoặc cancellation, yêu cầu hủy không nhất thiết dừng công việc đang chạy ngay lập tức. Vì vậy, cần timeout ở tầng client/driver và giới hạn thời gian thực thi phù hợp.

Với SSE hoặc WebSocket, client có thể kết nối lâu dài. Cần xác định chính sách khi client mất kết nối, có cho phép reconnect hay không, và consumer mới có thể replay dữ liệu từ đâu. Đối với sự kiện quan trọng, nguồn bền vững hoặc broker thường phù hợp hơn việc giữ toàn bộ lịch sử trong bộ nhớ của server.

### 12. Reactor Context trong vòng đời HTTP

Reactor Context gắn với subscription và có thể mang metadata xuyên suốt pipeline mà không phụ thuộc thread hiện tại. Trong ứng dụng web, context thường chứa correlation ID, tenant ID hoặc thông tin quan sát request. WebFilter là một vị trí phù hợp để bổ sung metadata lấy từ request.

~~~java
import reactor.core.publisher.Mono;

Mono<String> currentRequestId =
    Mono.deferContextual(context ->
        Mono.just(context.get("requestId"))
    );
~~~

Vì Context đi cùng subscription, nó vẫn có thể được đọc sau khi pipeline chuyển scheduler. Điều này khác với việc dựa vào **ThreadLocal**, vốn gắn với thread và không tự động theo tín hiệu khi pipeline chuyển thread. Không nên lưu đối tượng request mutable hoặc dữ liệu nhạy cảm tùy tiện trong Context; chỉ đưa vào metadata cần thiết và quản lý vòng đời phù hợp.

### 13. Kiểm thử vòng đời HTTP

**WebTestClient** cho phép kiểm thử endpoint WebFlux mà không cần khởi động server thật trong nhiều trường hợp. Có thể xác minh status, header và body của response:

~~~java
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient client =
    WebTestClient.bindToController(new OrderController(orderService))
        .build();

client.get()
    .uri("/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo("42");
~~~

Với pipeline service, **StepVerifier** kiểm tra các tín hiệu độc lập với tầng HTTP:

~~~java
import reactor.test.StepVerifier;

StepVerifier.create(orderService.findById("42"))
    .expectNextMatches(order -> order.id().equals("42"))
    .verifyComplete();
~~~

Nên kiểm thử riêng các trường hợp quan trọng:

- Request hợp lệ trả đúng status, header và body.
- Request không hợp lệ được ánh xạ thành lỗi HTTP phù hợp.
- Publisher rỗng có hành vi HTTP được xác định rõ.
- Lỗi từ dịch vụ phụ thuộc không làm lộ thông tin nội bộ.
- Client hủy stream thì nguồn được cancellation và cleanup phù hợp.
- Endpoint stream không giữ hàng đợi vô hạn khi client tiêu thụ chậm.

Kiểm thử controller bằng WebTestClient xác minh hợp đồng HTTP; kiểm thử service bằng StepVerifier xác minh hợp đồng Publisher. Kết hợp hai mức giúp phân biệt lỗi ở tầng ánh xạ HTTP với lỗi trong pipeline reactive.

### 14. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
| --- | --- |
| Dùng WebFlux là mọi code tự động non-blocking | Chỉ các API non-blocking mới không giữ thread trong lúc chờ; JDBC hoặc **Thread.sleep** vẫn blocking |
| Trả về Mono là request đã hoàn tất | Framework còn phải subscribe, nhận tín hiệu và ghi response |
| Một event-loop thread chỉ xử lý một request | Event loop có thể luân phiên xử lý nhiều kết nối |
| **Mono.just(blockingCall())** làm lời gọi trở nên lazy | Lời gọi đã chạy trước khi Mono được tạo |
| Cancellation rollback công việc đã thực hiện | Cancellation dừng công việc còn hoạt động nếu nguồn hỗ trợ; side effect đã commit vẫn tồn tại |
| Backpressure bảo vệ mọi hàng đợi | Nguồn ngoài hoặc buffer không giới hạn vẫn có thể làm tăng bộ nhớ |
| **ThreadLocal** luôn theo request qua các thread | Context gắn với subscription phù hợp hơn cho metadata reactive |

### 15. Cách đọc và thiết kế vòng đời một request

Khi phân tích một endpoint WebFlux, hãy lần theo các câu hỏi:

1. Server adapter nào nhận request và thread nào xử lý I/O?
2. Filter nào chạy trước handler, và metadata nào được bổ sung vào Context?
3. Handler/controller trả về Mono hay Flux; Publisher bắt đầu công việc ở thời điểm nào?
4. Nguồn dữ liệu có non-blocking hay đang gọi thư viện blocking?
5. Scheduler nào được dùng cho nguồn blocking và các bước CPU-bound?
6. Framework/codec ghi response như thế nào và demand được truyền đến nguồn ra sao?
7. Lỗi được ánh xạ thành HTTP status nào?
8. Khi client ngắt kết nối, cancellation và cleanup đi qua những thành phần nào?

Trong module REACTIVE_PROGRAMMING, event loop và vòng đời HTTP cho thấy cách các khái niệm Publisher–Subscriber hoạt động trong một ứng dụng web thực tế. Event loop xử lý sự kiện I/O cho nhiều kết nối; WebFlux kết nối request với pipeline Mono/Flux; framework quản lý subscription và ghi response; backpressure, cancellation và scheduler phối hợp để sử dụng tài nguyên có kiểm soát. Thiết kế tốt đòi hỏi giữ event loop không bị blocking và gắn vòng đời của nguồn dữ liệu với vòng đời thật của HTTP request.
