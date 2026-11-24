# Xử lý lỗi, thời gian chờ và ngữ cảnh bảo mật của yêu cầu

Một yêu cầu WebFlux thường đi qua nhiều bước bất đồng bộ: xác thực người dùng, kiểm tra quyền, gọi dịch vụ hoặc database, biến đổi kết quả rồi ghi response. Bất kỳ bước nào cũng có thể thất bại hoặc chờ quá lâu. Trong lúc đó, metadata như principal, tenant ID và request ID cần tiếp tục gắn với đúng yêu cầu dù pipeline chuyển qua nhiều thread. Thiết kế tốt phải xử lý lỗi tại ranh giới HTTP, đặt deadline phù hợp và giữ ngữ cảnh bảo mật theo subscription.

Bài học thuộc chương **Ứng dụng Web** của module `REACTIVE_PROGRAMMING`. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là phối hợp xử lý lỗi, timeout và security context trong ứng dụng Spring WebFlux.

Sau bài học, bạn có thể:

- Phân biệt lỗi nghiệp vụ, lỗi hạ tầng, timeout và cancellation trong request reactive.
- Chuyển lỗi nội bộ thành HTTP response có cấu trúc bằng `@RestControllerAdvice`.
- Đặt timeout ở đúng ranh giới và hiểu khác biệt giữa deadline của `Mono`, idle timeout của `Flux` và timeout của HTTP client.
- Lấy principal từ Reactor Context thông qua Spring Security reactive.
- Giữ metadata bảo mật qua `publishOn` mà không dựa vào `ThreadLocal`.
- Tránh retry hoặc fallback làm suy yếu chính sách xác thực và quyền truy cập.
- Kiểm thử status code, timeout, security context và cancellation bằng `WebTestClient` cùng `StepVerifier`.

## 1. Vòng đời của một request WebFlux

Trong Spring WebFlux, request được xử lý bằng chuỗi filter và handler reactive. Handler thường trả về `Mono` cho một response đơn hoặc `Flux` cho response dạng stream. Các bước bên trong pipeline không nhất thiết chạy trên cùng một thread.

```text
HTTP request
    |
    v
WebFilter chain
    |
    +--> Authentication / Authorization
    |
    v
Controller / Handler
    |
    v
Service Publisher (Mono / Flux)
    |
    +--> database / WebClient / business rules
    |
    v
HTTP response
```

Ba nhóm thông tin cần được quản lý xuyên suốt:

- **Kết quả và lỗi:** dữ liệu, empty completion hoặc exception từ các bước xử lý.
- **Thời gian:** thời gian kết nối, thời gian chờ dịch vụ, deadline của request và thời gian không có tín hiệu trên stream.
- **Ngữ cảnh bảo mật:** authentication, principal, quyền và metadata gắn với request.

Các nhóm này liên quan với nhau nhưng có vai trò khác nhau. Timeout có thể khiến subscription bị hủy; cancellation phải được truyền đến nguồn để giải phóng tài nguyên. Security context phải tiếp tục đúng với subscription đang xử lý, kể cả khi thread thay đổi. Lỗi cần được ánh xạ thành HTTP response mà không làm lộ chi tiết nội bộ.

## 2. Phân loại lỗi trước khi ánh xạ thành HTTP status

Không nên chuyển mọi exception thành cùng một status hoặc trả nguyên văn thông điệp exception cho client. Hãy phân loại lỗi theo ý nghĩa của request:

| Loại lỗi | Ví dụ | HTTP response thường dùng |
|---|---|---|
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, sai định dạng | `400 Bad Request` hoặc `422 Unprocessable Content` theo hợp đồng API. |
| Không tìm thấy tài nguyên | ID không tồn tại hoặc không được hiển thị theo chính sách | `404 Not Found`. |
| Xung đột trạng thái | Cập nhật phiên bản cũ, trùng khóa nghiệp vụ | `409 Conflict`. |
| Chưa xác thực | Thiếu hoặc sai thông tin đăng nhập | `401 Unauthorized`. |
| Không đủ quyền | Đã xác thực nhưng không được phép thao tác | `403 Forbidden`. |
| Dịch vụ upstream timeout | WebClient chờ dịch vụ khác quá deadline | `504 Gateway Timeout` khi API đang đóng vai trò gateway cho upstream. |
| Dịch vụ tạm thời không khả dụng | Pool cạn, dependency đang bảo trì | `503 Service Unavailable` nếu server không thể phục vụ tạm thời. |
| Lỗi không dự kiến | Bug hoặc trạng thái hệ thống không xác định | `500 Internal Server Error`. |

Status cụ thể là một phần của hợp đồng API. Ví dụ, một timeout do server xử lý quá tải có thể được quy định là `503`, trong khi timeout chờ một upstream thường phù hợp với `504`. Hãy thống nhất cách phân loại giữa controller, gateway và client.

### Empty không đồng nghĩa với lỗi

Một `Mono` hoàn tất mà không phát giá trị là empty completion. Nếu truy vấn không tìm thấy tài nguyên, ứng dụng có thể chuyển empty thành exception nghiệp vụ để ánh xạ `404`, hoặc trả `ResponseEntity.notFound()` ngay trong controller.

```java
Mono<Order> order = orderRepository.findById(orderId)
    .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)));
```

`switchIfEmpty` xử lý completion không có giá trị. `onErrorResume` xử lý `onError`. Không dùng `onErrorResume` để bắt trường hợp empty.

## 3. Chuyển lỗi nội bộ thành HTTP response

Service nên phát các exception có ý nghĩa với nghiệp vụ hoặc hạ tầng, thay vì tự tạo HTTP response ở mọi tầng. Controller advice có thể chuyển exception thành response thống nhất.

```java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    Mono<ResponseEntity<Map<String, String>>> notFound(
            OrderNotFoundException error) {
        return Mono.just(ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(Map.of(
                "code", "ORDER_NOT_FOUND",
                "message", "Không tìm thấy đơn hàng"
            )));
    }

    @ExceptionHandler(RequestDeadlineExceededException.class)
    Mono<ResponseEntity<Map<String, String>>> gatewayTimeout(
            RequestDeadlineExceededException error) {
        return Mono.just(ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
            .body(Map.of(
                "code", "UPSTREAM_TIMEOUT",
                "message", "Dịch vụ xử lý yêu cầu phản hồi quá thời hạn"
            )));
    }
}
```

Ví dụ dùng `Map` để giữ phần minh họa ngắn. API thực tế nên dùng DTO lỗi ổn định hoặc `ProblemDetail` nếu phiên bản Spring hỗ trợ và hợp đồng ứng dụng sử dụng định dạng đó. Không đưa stack trace, câu SQL, địa chỉ nội bộ, token hoặc thông tin xác thực vào response.

Controller chỉ cần xây dựng pipeline và để lỗi đi đến ranh giới xử lý HTTP:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final OrderService orderService;

    @GetMapping("/{orderId}")
    Mono<OrderDto> getOrder(@PathVariable String orderId) {
        return orderService.findById(orderId)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ));
    }
}
```

Lỗi không được xử lý trong controller sẽ đi tiếp đến cơ chế exception handling của WebFlux. `@RestControllerAdvice` phù hợp với lỗi ở tầng controller; `WebExceptionHandler` là một extension point thấp hơn trong WebFlux khi cần xử lý lỗi ở phạm vi web filter/handler rộng hơn.

### Dùng `onErrorMap` và `onErrorResume` đúng tầng

`onErrorMap` đổi một exception kỹ thuật thành exception có ý nghĩa với ứng dụng:

```java
Mono<OrderDto> order = orderClient.fetch(orderId)
    .onErrorMap(WebClientRequestException.class,
        error -> new OrderDependencyException(orderId, error));
```

`onErrorResume` thay nhánh lỗi bằng Publisher khác, ví dụ cache cho lỗi tạm thời đã xác định:

```java
Mono<OrderDto> order = orderClient.fetch(orderId)
    .onErrorResume(TemporaryDependencyException.class,
        error -> orderCache.find(orderId));
```

Chỉ dùng fallback khi dữ liệu cache đáp ứng được yêu cầu nhất quán của API. Không biến lỗi xác thực, lỗi phân quyền hoặc lỗi lập trình thành một giá trị mặc định. Khi fallback thành công, lỗi nguồn chính không còn đến downstream, vì vậy cần ghi metric hoặc log trước khi phục hồi.

```java
Mono<OrderDto> order = orderClient.fetch(orderId)
    .doOnError(error -> metrics.increment("order.upstream.failure"))
    .onErrorResume(TemporaryDependencyException.class,
        error -> orderCache.find(orderId));
```

Không bắt `Throwable` rồi trả `200 OK` cho mọi trường hợp. Điều đó che giấu lỗi hệ thống và làm client hiểu sai rằng request đã thành công.

## 4. Timeout có nhiều tầng

Một request web có thể chờ ở nhiều nơi: mở kết nối, gửi request, đợi response headers, đọc body hoặc đợi một Publisher nội bộ. Một timeout duy nhất ở controller không thay thế được mọi timeout của hạ tầng.

| Timeout | Phạm vi | Ví dụ mục tiêu |
|---|---|---|
| Connect timeout | Thiết lập kết nối tới upstream | Không chờ kết nối TCP quá lâu. |
| Response/read timeout | Chờ phản hồi hoặc dữ liệu từ upstream | Ngăn request phụ thuộc bị treo. |
| Publisher timeout | Chờ tín hiệu reactive trong một pipeline | Giới hạn thời gian chờ một kết quả hoặc khoảng im lặng. |
| Request deadline | Tổng thời gian API được phép tiêu thụ | Đảm bảo request không vượt ngân sách thời gian của hệ thống. |

Hãy phân bổ ngân sách từ deadline tổng. Ví dụ, nếu API có deadline 2 giây, không nên để từng dependency có timeout 2 giây nối tiếp nhau; tổng thời gian có thể vượt deadline. Có thể dành một phần cho xác thực, một phần cho dependency và phần còn lại cho serialize response.

### `timeout` với `Mono`

Với `Mono`, `timeout(Duration)` phát lỗi nếu Publisher không phát tín hiệu trong thời hạn quy định. Có thể chuyển lỗi timeout thành exception của ứng dụng:

```java
Mono<OrderDto> findOrder(String orderId) {
    return orderClient.fetch(orderId)
        .timeout(Duration.ofSeconds(2))
        .onErrorMap(TimeoutException.class,
            error -> new RequestDeadlineExceededException(orderId, error));
}
```

Ở đây, timeout bao quanh Publisher `orderClient.fetch`. Nếu nguồn không phát kết quả trong hai giây, Reactor phát `TimeoutException`; `onErrorMap` đổi nó thành exception mà controller advice nhận diện.

Một overload khác cho phép cung cấp Publisher thay thế khi timeout:

```java
Mono<OrderDto> findOrder(String orderId) {
    return orderClient.fetch(orderId)
        .timeout(
            Duration.ofSeconds(2),
            Mono.error(new RequestDeadlineExceededException(orderId))
        );
}
```

Publisher fallback được subscribe khi timeout xảy ra. Nó có thể là một nguồn dự phòng, nhưng cần cân nhắc ngân sách thời gian còn lại. Nếu fallback cũng chậm, hãy đặt deadline cho toàn bộ chuỗi thay vì để mỗi nhánh tiêu thụ thời gian không giới hạn.

### `timeout` với `Flux`: timeout giữa các tín hiệu

Với `Flux`, `timeout(Duration)` thường giới hạn khoảng thời gian chờ tín hiệu kế tiếp. Mỗi `onNext` có thể làm bộ đếm thời gian cho tín hiệu tiếp theo bắt đầu lại. Vì vậy, nó phù hợp với idle timeout của một stream, nhưng không mặc nhiên là giới hạn tổng thời lượng của cả stream.

```java
Flux<PriceUpdate> prices = priceFeed.stream()
    .timeout(Duration.ofSeconds(15));
```

Nếu price feed không phát cập nhật trong 15 giây, pipeline báo timeout. Nếu feed cứ phát đều mỗi 10 giây, stream có thể tiếp tục lâu hơn 15 giây tổng cộng.

Nếu nghiệp vụ cần giới hạn tổng thời gian stream, hãy thiết kế deadline tổng ở tầng request hoặc subscription. `take(Duration)` có semantics khác: nó hoàn tất luồng sau thời hạn thay vì phát lỗi timeout. Hãy chọn theo hợp đồng API; một stream kết thúc bình thường không giống một stream bị timeout.

### Timeout của WebClient

`timeout` trên một `Mono` bao quanh `WebClient` là giới hạn ở tầng Publisher. Cấu hình HTTP client còn có các timeout kết nối và phản hồi riêng. Ví dụ với Reactor Netty:

```java
HttpClient httpClient = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
    .responseTimeout(Duration.ofSeconds(2));

WebClient webClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .build();
```

Đây là ví dụ cấu hình minh họa; cần chọn giá trị phù hợp với deadline của API và phiên bản Reactor Netty đang dùng. Connect timeout giới hạn thời gian thiết lập kết nối; `responseTimeout` kiểm soát thời gian chờ phản hồi/dữ liệu theo semantics của client. Nếu cần giới hạn tổng thời gian một thao tác, có thể thêm `timeout` ở Publisher ngoài cùng.

Không nên đặt mọi timeout bằng cùng một con số mà không xét thứ tự. Timeout kết nối cần ngắn hơn deadline tổng; timeout dependency cũng phải để lại thời gian cho fallback, mapping lỗi và ghi response.

## 5. Retry và timeout phải có thứ tự rõ ràng

Vị trí của `retryWhen` so với `timeout` thay đổi ngân sách thời gian:

```java
// Mỗi lần thử có timeout riêng.
Mono<Response> perAttemptTimeout = client.call()
    .timeout(Duration.ofSeconds(1))
    .retryWhen(Retry.max(2)
        .filter(TransientNetworkException.class::isInstance));

// Một deadline bao trọn chuỗi retry.
Mono<Response> overallDeadline = client.call()
    .retryWhen(Retry.max(2)
        .filter(TransientNetworkException.class::isInstance))
    .timeout(Duration.ofSeconds(3));
```

Trong ví dụ thứ nhất, mỗi lần subscribe lại sẽ có timeout một giây. Tổng thời gian có thể dài hơn một giây do nhiều lần thử và delay. Trong ví dụ thứ hai, timeout ở ngoài bao trọn chuỗi retry; khi hết ba giây, toàn bộ chuỗi bị hủy.

Retry chỉ nên áp dụng với lỗi tạm thời và thao tác an toàn khi lặp. Không retry `401`, `403`, lỗi validate hoặc lỗi nghiệp vụ không thể tự hết. Với lệnh ghi, cần idempotency key hoặc cơ chế xác nhận trạng thái để tránh thực hiện trùng khi request đã tới upstream nhưng response bị mất.

## 6. Cancellation khi client ngắt kết nối

Trong WebFlux, khi client đóng kết nối hoặc không còn nhận response, subscription của response body có thể bị hủy. Cancellation nên truyền xuống các Publisher upstream để dừng công việc còn có thể dừng được.

```text
Client disconnect / request timeout
              |
              v
       cancel response stream
              |
              v
        controller Publisher
              |
              v
       service / WebClient
              |
              v
       resource cleanup
```

Cancellation không phải `onError`. Vì vậy, `onErrorResume` không tự chạy để tạo response dự phòng khi client đã ngắt kết nối. Không nên tiếp tục gọi dịch vụ chỉ để tạo một response mà không còn client nhận.

Nếu pipeline đang giữ tài nguyên, hãy gắn cleanup với lifecycle bằng `using` hoặc `usingWhen`. Với tài nguyên async như connection reactive, `usingWhen` cho phép khai báo cleanup riêng khi complete, error và cancel.

`doFinally` có thể quan sát `SignalType.CANCEL` để ghi metric:

```java
return orderService.streamOrders(customerId)
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            metrics.increment("orders.stream.cancelled");
        }
    });
```

Đây là hook quan sát đồng bộ. Không dùng `doFinally` làm nơi duy nhất để thực hiện cleanup bất đồng bộ cần được chờ.

## 7. Security context trong ứng dụng WebFlux

Spring Security reactive lưu `SecurityContext` trong Reactor Context của subscription. Điều này cho phép principal tiếp tục có mặt khi pipeline chuyển qua scheduler khác, thay vì phụ thuộc vào `ThreadLocal` của một thread.

Trong cấu hình WebFlux, `SecurityWebFilterChain` xác thực request và đặt security context vào reactive context. Service có thể đọc context bằng `ReactiveSecurityContextHolder`:

```java
Mono<OrderDto> findForCurrentUser(String orderId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(authentication ->
            orderRepository.findVisibleTo(
                orderId,
                authentication.getName()
            )
        );
}
```

`getContext()` trả về `Mono<SecurityContext>`. Nếu request không có security context, Publisher có thể hoàn tất empty. Trong ứng dụng thực tế, route security nên yêu cầu xác thực trước khi handler được gọi; không nên coi việc không có context là một user mặc định.

### Authentication khác authorization

- **Authentication** trả lời người gọi là ai.
- **Authorization** trả lời người gọi có được phép thực hiện hành động này trên tài nguyên cụ thể không.

Có security context không có nghĩa người dùng được phép đọc mọi đơn hàng. Cần kiểm tra quyền ở route, method hoặc tầng truy cập dữ liệu. Ví dụ, method security reactive có thể bảo vệ service:

```java
@PreAuthorize("hasAuthority('order:read')")
public Mono<OrderDto> findOrder(String orderId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(authentication ->
            orderRepository.findVisibleTo(orderId, authentication.getName())
        );
}
```

Ứng dụng cần bật reactive method security trong cấu hình tương ứng, ví dụ `@EnableReactiveMethodSecurity`. Biểu thức quyền phải phù hợp với mô hình authority của ứng dụng. Kiểm tra quyền theo chủ sở hữu tài nguyên vẫn cần được thực hiện; một authority chung không nhất thiết cấp quyền đọc mọi bản ghi.

### Không dùng ThreadLocal để giữ principal

Đoạn code sau không an toàn trong reactive pipeline:

```java
// Không nên: ThreadLocal không gắn với subscription.
String username = SecurityContextHolder.getContext()
    .getAuthentication()
    .getName();
```

`SecurityContextHolder` theo mặc định thường dùng ThreadLocal trong mô hình servlet. Nếu gọi trực tiếp trong WebFlux, thread hiện tại có thể không chứa context của request hoặc có thể chứa dữ liệu của tác vụ khác. Dùng `ReactiveSecurityContextHolder` cho reactive code.

Không tự ghi principal lấy từ header tùy ý vào Reactor Context. Security context phải được thiết lập bởi cơ chế xác thực đáng tin cậy của Spring Security. Context chỉ vận chuyển danh tính đã được xác minh; nó không thay thế bước xác thực hoặc kiểm tra quyền.

## 8. Security context qua `publishOn` và `flatMap`

Reactor Context thuộc subscription nên không bị gắn với một thread cụ thể. Khi Spring Security đã thiết lập context, các operator reactive có thể đọc nó sau khi chuyển scheduler:

```java
Mono<String> auditMessage = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(authentication -> authentication.getName())
    .publishOn(Schedulers.parallel())
    .map(username -> "request by " + username);
```

`publishOn` chuyển nơi xử lý tín hiệu downstream. Nó không làm mất Reactor Context của subscription. Tương tự, Publisher con được tạo trong `flatMap` có thể đọc context của subscription hiện tại:

```java
Mono<OrderDto> loadOrder(String orderId) {
    return Mono.deferContextual(context -> {
        String requestId = context.get("requestId");
        return orderRepository.findById(orderId)
            .doOnNext(order -> log.info(
                "requestId={} orderId={}", requestId, order.id()
            ));
    });
}

Mono<OrderDto> request = loadOrder(orderId)
    .contextWrite(context -> context.put("requestId", requestId));
```

Trong ứng dụng Spring Security, không cần tự đưa principal vào Context bằng `contextWrite` nếu security filter chain đã thiết lập nó. Có thể dùng Context bổ sung cho request ID hoặc tenant metadata. Tránh ghi đè các key nội bộ mà framework sử dụng.

### Context không phải payload

Security context phù hợp để cung cấp principal và authentication metadata cho các bước cần đến chúng. Dữ liệu nghiệp vụ như `Order`, `Customer` hoặc kết quả tính toán vẫn nên được truyền qua `onNext`. Không lưu payload lớn hoặc trạng thái mutable dùng chung trong Reactor Context.

## 9. Giữ lỗi bảo mật tách biệt khỏi fallback dữ liệu

Một lỗi xác thực hoặc phân quyền không nên được xử lý như lỗi mạng tạm thời. Ví dụ, nếu service trả về `AccessDeniedException`, không được chuyển sang cache rồi trả dữ liệu như thể request thành công.

```java
Mono<OrderDto> loadOrder(String orderId) {
    return orderClient.fetch(orderId)
        .onErrorResume(TemporaryDependencyException.class,
            error -> orderCache.find(orderId));
}
```

Chỉ lỗi dependency đã xác định mới kích hoạt cache. Các lỗi security tiếp tục truyền xuống cơ chế xử lý bảo mật của ứng dụng. Spring Security có các handler riêng cho authentication entry point và access denied; hãy cấu hình chúng trong `SecurityWebFilterChain` để trả status phù hợp.

Các nguyên tắc cần giữ:

- Không retry authentication failure hoặc authorization failure.
- Không dùng fallback để vượt qua kiểm tra quyền.
- Không trả dữ liệu cache nếu chưa áp dụng cùng chính sách tenant/ownership như nguồn chính.
- Không ghi token, cookie, mật khẩu hoặc toàn bộ principal nhạy cảm vào log.
- Không tiết lộ sự tồn tại của tài nguyên nếu chính sách bảo mật yêu cầu che giấu; một số API có thể trả `404` thay cho `403` theo hợp đồng đã định.

## 10. Kiểm thử timeout và ánh xạ lỗi

`StepVerifier` giúp kiểm thử timeout ở tầng Publisher mà không cần chờ thời gian thực:

```java
StepVerifier.withVirtualTime(() ->
        Mono.<OrderDto>never()
            .timeout(Duration.ofSeconds(2))
            .onErrorMap(TimeoutException.class,
                error -> new RequestDeadlineExceededException("order-7", error))
    )
    .thenAwait(Duration.ofSeconds(2))
    .expectError(RequestDeadlineExceededException.class)
    .verify();
```

Pipeline được tạo bên trong supplier của `withVirtualTime` để Reactor áp dụng scheduler ảo. Kiểm thử xác nhận timeout được chuyển thành exception ứng dụng.

Với `Flux`, hãy kiểm thử semantics idle timeout:

```java
StepVerifier.withVirtualTime(() ->
        Flux.concat(
            Mono.delay(Duration.ofSeconds(1)).thenReturn("first"),
            Mono.delay(Duration.ofSeconds(5)).thenReturn("second")
        ).timeout(Duration.ofSeconds(2))
    )
    .thenAwait(Duration.ofSeconds(1))
    .expectNext("first")
    .thenAwait(Duration.ofSeconds(2))
    .expectError(TimeoutException.class)
    .verify();
```

Sau phần tử đầu tiên, tín hiệu tiếp theo không đến trong hai giây nên stream timeout. Kiểm thử này không phải tổng deadline của cả Flux; nó kiểm tra khoảng im lặng giữa các tín hiệu.

## 11. Kiểm thử HTTP response bằng WebTestClient

`WebTestClient` kiểm thử handler WebFlux qua giao thức HTTP mà không cần mở server thật trong mọi trường hợp.

```java
webTestClient.get()
    .uri("/api/orders/missing")
    .exchange()
    .expectStatus().isNotFound()
    .expectBody()
    .jsonPath("$.code").isEqualTo("ORDER_NOT_FOUND");
```

Kiểm thử xác nhận exception nghiệp vụ được ánh xạ thành `404` và response có mã lỗi ổn định.

Với timeout, giả lập service trả về `Mono.never()` hoặc một Publisher chậm hơn deadline:

```java
webTestClient.get()
    .uri("/api/orders/slow")
    .exchange()
    .expectStatus().isEqualTo(HttpStatus.GATEWAY_TIMEOUT)
    .expectBody()
    .jsonPath("$.code").isEqualTo("UPSTREAM_TIMEOUT");
```

Để kiểm thử security, Spring Security Test cung cấp các request post-processor dành cho WebFlux. Ví dụ với một route yêu cầu authority:

```java
webTestClient.mutateWith(mockUser().authorities(
        new SimpleGrantedAuthority("order:read")
    ))
    .get()
    .uri("/api/orders/order-7")
    .exchange()
    .expectStatus().isOk();
```

Hãy bổ sung các trường hợp không có authentication và có authentication nhưng thiếu authority. Kết quả mong đợi thường là `401` cho request chưa xác thực và `403` cho request đã xác thực nhưng không đủ quyền, trừ khi API có chính sách che giấu tài nguyên bằng `404`.

### Kiểm thử service đọc security context

Khi kiểm thử một service độc lập, có thể cung cấp authentication qua Reactor Context:

```java
Authentication authentication =
    new UsernamePasswordAuthenticationToken("alice", "n/a", authorities);

StepVerifier.create(
        service.findForCurrentUser("order-7")
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(authentication)
            )
    )
    .expectNextMatches(order -> order.owner().equals("alice"))
    .verifyComplete();
```

Trong kiểm thử tích hợp, ưu tiên request post-processor của Spring Security để xác minh toàn bộ filter chain. Kiểm thử service trực tiếp với `withAuthentication` phù hợp khi chỉ cần xác nhận service đọc principal đúng từ Reactor Context.

## 12. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Chuyển mọi exception thành `500` | Client không phân biệt được lỗi đầu vào, not found và dependency timeout. | Phân loại exception và ánh xạ status theo hợp đồng API. |
| Dùng `onErrorResume` để xử lý empty | Empty không phát `onError`, nên fallback không chạy. | Dùng `switchIfEmpty` hoặc `defaultIfEmpty`. |
| Đặt `timeout` ở controller và cho rằng mọi I/O đã có deadline | Kết nối hoặc response body của upstream có thể có timeout riêng. | Cấu hình timeout cho HTTP client và deadline Publisher theo từng tầng. |
| Xem `Flux.timeout` là tổng thời lượng stream | Một stream phát đều có thể chạy lâu hơn duration. | Hiểu đây là timeout chờ tín hiệu kế tiếp; thiết kế deadline tổng riêng. |
| Retry `401` hoặc `403` | Lặp request không thể thành công và có thể tạo tải không cần thiết. | Chỉ retry lỗi tạm thời, không retry lỗi bảo mật. |
| Dùng `ThreadLocal` để lấy principal trong WebFlux | Context có thể mất khi đổi thread hoặc bị đọc nhầm. | Dùng `ReactiveSecurityContextHolder`. |
| Cho rằng có security context nghĩa là được phép truy cập tài nguyên | Authentication không thay thế authorization theo tài nguyên. | Kiểm tra authority, tenant và quyền sở hữu ở đúng tầng. |
| Đưa token hoặc principal nhạy cảm vào log | Rò rỉ thông tin xác thực hoặc dữ liệu cá nhân. | Chỉ log ID tương quan và metadata tối thiểu đã được phép. |
| Bỏ qua cancellation khi client ngắt kết nối | Công việc và tài nguyên có thể tiếp tục bị giữ. | Truyền cancellation, dùng `usingWhen` và đo cancellation. |
| Fallback cache không áp dụng quyền như nguồn chính | Có thể trả dữ liệu chéo tenant hoặc vượt quyền. | Bảo vệ cả nguồn cache bằng cùng chính sách security. |

## 13. Checklist trước khi đưa request WebFlux vào production

- Lỗi nghiệp vụ, lỗi hạ tầng và lỗi bảo mật đã có kiểu riêng chưa?
- `404`, `409`, `401`, `403`, `503`, `504` và `500` có ánh xạ nhất quán với hợp đồng API không?
- Response lỗi có cấu trúc ổn định và không lộ stack trace hoặc bí mật không?
- Timeout kết nối, response và deadline Publisher đã được phân tầng chưa?
- Với `Flux`, đã phân biệt idle timeout với tổng deadline chưa?
- Retry chỉ áp dụng cho lỗi tạm thời và thao tác an toàn khi lặp chưa?
- Client disconnect có truyền cancellation đến nguồn và cleanup tài nguyên không?
- Security context được lấy bằng API reactive và tiếp tục đúng qua scheduler boundary không?
- Authentication và authorization được kiểm tra riêng, bao gồm tenant/ownership không?
- Cache fallback có tuân thủ cùng chính sách quyền như nguồn chính không?
- Kiểm thử đã bao gồm status code, timeout, thiếu quyền, principal và cancellation chưa?

Một request WebFlux an toàn cần giữ đúng ba hợp đồng: lỗi được chuyển thành response có ý nghĩa, thời gian chờ bị giới hạn theo ngân sách của từng tầng, và security context đi cùng subscription thay vì phụ thuộc thread. Khi kết hợp exception mapping, timeout, cancellation và `ReactiveSecurityContextHolder` đúng vị trí, pipeline `Mono`/`Flux` có thể xử lý request bất đồng bộ mà vẫn giữ được khả năng quan sát, bảo vệ dữ liệu và giải phóng tài nguyên.
