# ServerWebExchange.getSession và chuỗi xử lý phản ứng

Trong ứng dụng Spring WebFlux, session được truy cập qua `ServerWebExchange.getSession()`. Phương thức này trả về `Mono<WebSession>` thay vì `HttpSession` đồng bộ như ứng dụng Servlet. Sự khác biệt này ảnh hưởng trực tiếp đến cách đọc, cập nhật, lưu và kết thúc phiên: mọi thao tác phải nằm trong chuỗi reactive để được thực thi đúng thời điểm, lỗi được truyền về đúng nơi và response chỉ hoàn tất sau khi các công việc cần thiết đã được xử lý.

Spring Session có thể lưu WebSession trong kho dùng chung như Redis. Nhờ vậy, nhiều instance WebFlux có thể khôi phục cùng một phiên bằng cookie hoặc header session ID. API reactive giúp tránh chặn event-loop thread khi truy cập kho dữ liệu, nhưng chỉ khi ứng dụng giữ đúng mô hình non-blocking: không gọi `block()`, không tự `subscribe()` để tách thao tác khỏi request và không dùng session như một object đồng bộ có thể sửa tùy ý từ nhiều publisher đồng thời.

## 1. WebSession trong WebFlux khác HttpSession như thế nào?

Ứng dụng Servlet dùng `HttpServletRequest.getSession()` để lấy `HttpSession`. Ứng dụng WebFlux dùng `ServerWebExchange.getSession()` để lấy `WebSession` qua một publisher.

| Servlet | WebFlux |
|---|---|
| `HttpServletRequest` | `ServerWebExchange` |
| `HttpSession` | `WebSession` |
| `request.getSession()` | `exchange.getSession()` trả `Mono<WebSession>` |
| `session.invalidate()` | `session.invalidate()` trả `Mono<Void>` |
| `setMaxInactiveInterval(int)` | `setMaxIdleTime(Duration)` |
| Filter Servlet và `SessionRepositoryFilter` | WebFilter/WebSessionManager và reactive session repository |

`WebSession` là abstraction của Spring WebFlux. Nó cung cấp session ID, thời điểm tạo, thời điểm truy cập gần nhất, thời gian không hoạt động tối đa, map thuộc tính và các thao tác vòng đời như `start`, `save`, `invalidate` và `changeSessionId`.

Spring Session tích hợp với WebFlux qua các thành phần reactive. Repository triển khai `ReactiveSessionRepository` để tạo, tìm, lưu và xóa session bằng các kiểu trả về như `Mono` hoặc `Flux`. WebFlux quản lý việc lấy session cho request và lưu thay đổi theo vòng đời response. Controller không cần tự truy vấn Redis hoặc tự parse cookie.

## 2. Cấu hình Spring Session cho WebFlux

Với Redis, ứng dụng WebFlux có thể bật cấu hình reactive session bằng `@EnableRedisWebSession`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.server.EnableRedisWebSession;

@Configuration
@EnableRedisWebSession(maxInactiveIntervalInSeconds = 1800)
public class WebSessionConfiguration {
}
```

Ví dụ đặt thời gian không hoạt động tối đa là 1.800 giây. Ứng dụng vẫn cần cấu hình kết nối Redis hợp lệ, serializer và các thuộc tính bảo mật phù hợp. Với Spring Boot, auto-configuration có thể cấu hình session theo dependency và property của phiên bản đang dùng; không thêm annotation tường minh nếu nó tạo cấu hình trùng với auto-configuration hiện tại.

Trong WebFlux, cần dùng dependency và repository reactive tương thích với stack reactive. Một ứng dụng WebFlux không nên dùng repository Servlet đồng bộ rồi gọi `block()` trên event-loop để giả lập reactive. Kiểm tra dependency Spring Session, Spring Data Redis và Spring Boot BOM của cùng một thế hệ phiên bản.

Nếu cần thay đổi cookie hoặc cách truyền session ID, cấu hình resolver tương ứng với WebFlux. `WebSessionIdResolver` là abstraction phía WebFlux; `CookieWebSessionIdResolver` dùng cookie và có thể được cấu hình tên cookie, path, SameSite hoặc thuộc tính phù hợp. API cấu hình cụ thể phụ thuộc phiên bản Spring Session.

## 3. getSession() trả về publisher lazy

`ServerWebExchange.getSession()` trả về `Mono<WebSession>`. `Mono` mô tả một kết quả có thể xuất hiện sau này; việc tạo hoặc khôi phục session chỉ được thực thi khi publisher được subscribe bởi runtime reactive. Trong một controller WebFlux chuẩn, framework subscribe vào publisher được trả về từ handler để điều khiển request.

Ví dụ đọc session:

```java
@GetMapping("/api/session")
public Mono<Map<String, Object>> readSession(ServerWebExchange exchange) {
    return exchange.getSession()
            .map(session -> {
                String cartId = session.getAttribute("cartId");
                return Map.of("cartId", cartId == null ? "" : cartId);
            });
}
```

Publisher được trả về từ controller, nên WebFlux có thể thực thi nó trong chuỗi xử lý request. Không cần và không nên gọi `subscribe()` trong controller.

Đoạn code sau không thực hiện thao tác session theo cách mà request chờ đợi:

```java
@GetMapping("/api/session/bad")
public Mono<Void> bad(ServerWebExchange exchange) {
    exchange.getSession()
            .doOnNext(session -> session.getAttributes().put("seen", true));

    return Mono.empty();
}
```

Publisher `getSession()` ở đây không được nối vào publisher trả về hoặc subscribe, nên thao tác có thể không chạy. Hãy trả chính publisher hoặc kết hợp nó với publisher khác bằng `map`, `flatMap`, `then` hay toán tử phù hợp.

## 4. Tạo session và cập nhật thuộc tính

Khi cần tạo hoặc cập nhật trạng thái phiên, lấy `WebSession` rồi thay đổi attributes trong cùng chuỗi reactive:

```java
@PostMapping("/api/session/cart")
public Mono<Map<String, Object>> rememberCart(
        ServerWebExchange exchange,
        @RequestBody CartRequest request) {

    return exchange.getSession()
            .map(session -> {
                session.getAttributes().put("cartId", request.cartId());
                return Map.of("saved", true);
            });
}
```

`getAttributes()` trả về map thuộc tính của WebSession. Khi thêm hoặc sửa thuộc tính, session được đánh dấu đã bắt đầu theo cơ chế WebFlux session. WebSessionManager/Spring Session quản lý việc lưu thay đổi khi request hoàn tất và response được commit theo vòng đời của exchange.

Nếu endpoint chỉ cần đọc, không thay đổi thuộc tính, tránh khởi động session không cần thiết. Việc gọi `getSession()` cung cấp một WebSession cho request; một session mới thường chỉ trở thành session được lưu và phát định danh khi được start hoặc có thay đổi yêu cầu lưu. Không tạo session mới cho mọi request chỉ để đọc một giá trị tùy chọn.

Một cách khác là dùng `session.start()` khi có chủ đích tạo phiên rỗng, sau đó để framework lưu session trong vòng đời response. `start()` không thay thế việc đưa publisher chứa session vào chuỗi xử lý và không thay thế repository.

## 5. Đọc thuộc tính mà không tạo phiên mới ngoài ý muốn

`exchange.getSession()` là API chính để truy cập WebSession của request. Nếu session ID không có hoặc không tìm thấy, WebFlux có thể cung cấp một WebSession mới ở trạng thái chưa bắt đầu. Vì vậy, đọc một thuộc tính không đồng nghĩa session mới chắc chắn được lưu.

Ví dụ xử lý thuộc tính có thể không tồn tại:

```java
@GetMapping("/api/session/cart")
public Mono<Map<String, Object>> cart(ServerWebExchange exchange) {
    return exchange.getSession()
            .map(session -> {
                String cartId = session.getAttribute("cartId");
                if (cartId == null) {
                    return Map.of("hasCart", false);
                }
                return Map.of("hasCart", true, "cartId", cartId);
            });
}
```

Nếu endpoint yêu cầu principal đã đăng nhập, kiểm tra `Principal`/`SecurityContext` qua cơ chế reactive của Spring Security thay vì chỉ kiểm tra một thuộc tính session tùy ý. Session có thể tồn tại nhưng không đại diện cho một người dùng đã xác thực.

Không lưu `null` vào `Map.of` vì factory này không chấp nhận key hoặc value null. Xử lý trường hợp thiếu thuộc tính rõ ràng để tránh `NullPointerException` trong chuỗi reactive.

## 6. Kết hợp thao tác bất đồng bộ bằng flatMap

Khi thao tác session cần kết hợp với một dịch vụ reactive khác, dùng `flatMap` để nối các publisher theo thứ tự phụ thuộc:

```java
@PostMapping("/api/checkout")
public Mono<CheckoutView> checkout(ServerWebExchange exchange,
                                   @RequestBody CheckoutRequest request) {
    return exchange.getSession()
            .flatMap(session ->
                    checkoutService.createOrder(request)
                            .map(order -> {
                                session.getAttributes().put(
                                        "lastOrderId", order.id());
                                return new CheckoutView(order.id(), "created");
                            })
            );
}
```

`checkoutService.createOrder` trả publisher nên `flatMap` chờ publisher đó hoàn tất rồi mới tạo view và cập nhật session. Không gọi `block()` để lấy order đồng bộ. Nếu service thất bại, lỗi đi tiếp trong chuỗi và WebFlux có thể áp dụng exception handling.

Nếu thao tác tiếp theo chỉ cần chạy sau một publisher và không cần giá trị của nó, dùng `then`:

```java
return exchange.getSession()
        .flatMap(session -> cartService.loadCart(session))
        .then(ServerResponse.ok().build());
```

Chọn `map` khi callback chuyển một giá trị đồng bộ thành giá trị khác; chọn `flatMap` khi callback trả về một publisher; chọn `then` khi chỉ quan tâm việc publisher trước hoàn tất. Dùng sai `map` với publisher lồng nhau dễ tạo `Mono<Mono<T>>` và làm chuỗi không thực thi như dự kiến.

## 7. Không block hoặc subscribe thủ công

Trong WebFlux, event-loop thread phục vụ nhiều request. Gọi `block()` trong controller/filter có thể chặn thread này, làm giảm khả năng xử lý đồng thời và gây deadlock hoặc timeout khi publisher cần cùng scheduler để hoàn tất.

Không nên viết:

```java
WebSession session = exchange.getSession().block();
String cartId = session.getAttribute("cartId");
```

Thay vào đó, giữ thao tác trong chuỗi:

```java
return exchange.getSession()
        .map(session -> session.getAttribute("cartId"));
```

Cũng tránh tự `subscribe()`:

```java
exchange.getSession().subscribe(session ->
        session.getAttributes().put("seen", true));
return Mono.just("ok");
```

Publisher được subscribe tách rời khỏi response. Request có thể trả về trước khi session được cập nhật hoặc lưu; exception có thể không được gửi về error handler của request; context bảo mật và tracing có thể không được truyền đúng. Trả publisher đã kết hợp để framework quản lý subscription và cancellation.

Nếu cần gọi thư viện blocking không có API reactive, cô lập thao tác đó trên scheduler phù hợp, chẳng hạn `Schedulers.boundedElastic()`, rồi nối kết quả trở lại chuỗi. Không chuyển toàn bộ controller sang scheduler blocking và không dùng `boundedElastic` để che giấu việc gọi repository reactive sai cách.

## 8. Lưu session và thời điểm hoàn tất response

Trong WebFlux, WebSession được quản lý theo vòng đời của `ServerWebExchange`. Session manager và store có thể lưu thay đổi trước khi response commit, đồng thời resolver phát hoặc xóa session ID theo trạng thái session. Điều này cho phép response chứa cookie/header mới khi session bắt đầu hoặc thay đổi ID.

Trong luồng thông thường, ứng dụng chỉ cần cập nhật attributes trong publisher của handler; không cần gọi `session.save()` thủ công sau mỗi `put`. Tuy nhiên, `WebSession.save()` trả về `Mono<Void>` và có thể được dùng khi có lý do rõ ràng để yêu cầu lưu tại một điểm cụ thể. Nếu gọi, phải nối publisher đó vào chuỗi:

```java
return exchange.getSession()
        .flatMap(session -> {
            session.getAttributes().put("workflow", "payment");
            return session.save()
                    .thenReturn(Map.of("saved", true));
        });
```

Không gọi `session.save().subscribe()` tách rời. Lưu thủ công và cơ chế lưu tự động của WebSessionManager cần được hiểu theo repository/version; gọi save nhiều lần có thể tạo thêm I/O nhưng không làm thao tác nghiệp vụ trở thành transaction nguyên tử.

Nếu response đã bắt đầu commit hoặc streaming body, ứng dụng không thể tùy ý thêm header session ID mới. Hãy hoàn tất thao tác tạo/cập nhật session trước khi bắt đầu ghi stream hoặc flush response. Với `Flux` phát dữ liệu dài hạn, đừng trì hoãn việc khởi tạo session đến callback chạy sau khi response đã commit.

## 9. Kết thúc session bằng invalidate

`WebSession.invalidate()` trả về `Mono<Void>`. Đây là thao tác bất đồng bộ, vì vậy phải được nối vào publisher trả về. Ví dụ:

```java
@PostMapping("/api/logout")
public Mono<ResponseEntity<Void>> logout(ServerWebExchange exchange) {
    return exchange.getSession()
            .flatMap(WebSession::invalidate)
            .thenReturn(ResponseEntity.noContent().build());
}
```

Khi invalidate hoàn tất, session không còn được chấp nhận theo repository và resolver có thể phát tín hiệu hết hạn cho client qua cookie/header. Nếu không có session trước đó, WebFlux vẫn có thể cung cấp một WebSession chưa bắt đầu; việc invalidate cần được xử lý an toàn theo implementation đang dùng.

Với Spring Security WebFlux, dùng logout handler và security context repository tương ứng. Không chỉ xóa token phía client; phải invalidate session ở server để một bản sao session ID cũ không thể tiếp tục truy cập phiên.

Không trả response thành công trước khi publisher invalidate hoàn tất. Nếu gọi `subscribe()` riêng rồi trả `200`, client có thể nhận xác nhận logout trước khi repository xóa phiên hoặc trước khi lỗi được phát hiện.

## 10. Thay đổi session ID và thời hạn không hoạt động

`WebSession` cung cấp các phương thức reactive cho thay đổi định danh và lưu trữ. Ví dụ, `changeSessionId()` trả `Mono<Void>`:

```java
return exchange.getSession()
        .flatMap(session -> session.changeSessionId())
        .thenReturn(ResponseEntity.noContent().build());
```

Trong luồng đăng nhập, nên để cơ chế session fixation protection của Spring Security WebFlux quản lý việc đổi ID. Không tự tạo ID bằng UUID hoặc tự ghi đè header/cookie vì ID phải do Spring Session và repository quản lý.

Thời gian không hoạt động của WebSession dùng `Duration`:

```java
return exchange.getSession()
        .map(session -> {
            session.setMaxIdleTime(Duration.ofMinutes(15));
            return session.getMaxIdleTime();
        });
```

Đây là metadata timeout của session. Repository reactive cần lưu và áp dụng thời hạn tương ứng. Cookie lifetime hoặc thời gian client giữ header session ID là chính sách riêng; cookie còn tồn tại không có nghĩa session phía server còn hiệu lực.

## 11. Xử lý lỗi trong chuỗi reactive

Lỗi khi đọc hoặc ghi session có thể đến từ Redis, timeout, serializer, dữ liệu không tương thích hoặc lỗi trong code callback. Vì publisher biểu diễn công việc chưa hoàn tất, lỗi có thể được phát sau khi controller đã trả về `Mono` nhưng trước khi response được commit.

Có thể xử lý lỗi ở cấp handler hoặc service bằng các toán tử reactive:

```java
return exchange.getSession()
        .flatMap(session -> session.save())
        .thenReturn(ResponseEntity.noContent().build())
        .onErrorMap(SessionStoreUnavailableException.class,
                ex -> new ResponseStatusException(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        "Session store is unavailable", ex));
```

Đây là ví dụ minh họa; exception cụ thể phụ thuộc repository và lớp chuyển đổi lỗi của ứng dụng. Không chuyển mọi lỗi thành `401 Unauthorized` hoặc coi lỗi Redis như session không tồn tại. Nếu repository không truy cập được, ứng dụng chưa thể xác định phiên có hợp lệ hay không.

`onErrorResume` có thể cung cấp fallback, nhưng chỉ dùng khi fallback đúng với hợp đồng nghiệp vụ. Ví dụ, endpoint đọc trạng thái giao diện có thể trả nội dung mặc định trong một tình huống được chấp nhận; endpoint yêu cầu xác thực không nên tạo phiên rỗng rồi tiếp tục như người dùng đã đăng nhập.

Dùng `doOnError` để ghi log/metric không nhạy cảm; không ghi session ID, cookie hoặc thuộc tính cá nhân. Để lỗi tiếp tục đi đến error handler khi cần response thất bại. Tránh nuốt lỗi bằng `onErrorComplete()` nếu thao tác lưu session là điều kiện cần của request.

## 12. Context reactive và bảo mật

Spring Security WebFlux lưu và truy xuất `SecurityContext` theo mô hình reactive context. Khi xử lý principal, dùng các API reactive như `ReactiveSecurityContextHolder` hoặc method argument `Principal` được WebFlux hỗ trợ, thay vì dựa vào `SecurityContextHolder` dạng ThreadLocal như trong ứng dụng Servlet.

Ví dụ lấy principal từ reactive context:

```java
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

Reactive pipeline có thể đổi thread hoặc scheduler. Không giả định một thread cố định sở hữu session hay security context. Giữ các thao tác trong cùng chuỗi reactive để context propagation được framework quản lý.

Session ID vẫn là bearer credential. Bảo vệ cookie/header bằng HTTPS, cấu hình resolver đúng, giới hạn CORS, bảo vệ chống XSS/CSRF theo cách client gửi định danh và không ghi ID vào log. Nếu dùng cookie cho browser, cân nhắc `HttpOnly`, `Secure` và `SameSite`; nếu dùng header, client phải tự bảo vệ giá trị đó.

## 13. Request đồng thời và mutable session attributes

Reactive không có nghĩa một session chỉ được truy cập bởi một request tại một thời điểm. Hai request cùng mang session ID có thể chạy đồng thời trên các event loop hoặc instance khác nhau. Map attributes của WebSession không tự cung cấp transaction nghiệp vụ hoặc cơ chế merge object.

Ví dụ hai request cùng đọc `cart`, mỗi request thay đổi object trong bộ nhớ riêng rồi lưu. Request ghi sau có thể ghi đè snapshot của request trước. `flatMap` trong từng request chỉ điều khiển chuỗi publisher của request đó; nó không khóa session trên toàn cụm.

Với dữ liệu cần nhất quán như số lượng hàng, số dư, hạn mức hoặc trạng thái đơn hàng, lưu dữ liệu trong kho nghiệp vụ có transaction/atomic update và giữ mã tham chiếu trong session. Tránh dùng mutable object lớn làm nguồn dữ liệu chuẩn. Nếu phải phối hợp nhiều thao tác, thiết kế optimistic locking, version hoặc cơ chế cập nhật nguyên tử phù hợp.

## 14. Streaming và chuỗi xử lý dài hạn

WebFlux hỗ trợ `Flux` và streaming response. Khi response bắt đầu gửi dữ liệu, header có thể đã được commit. Nếu session cần được tạo, đổi ID hoặc cập nhật metadata trước khi gửi stream, hãy hoàn tất thao tác đó trước khi trả publisher body dài hạn.

Ví dụ về thứ tự xử lý:

```java
@GetMapping(value = "/api/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Mono<ResponseEntity<Flux<ServerSentEvent<String>>>> events(
        ServerWebExchange exchange) {

    return exchange.getSession()
            .map(session -> {
                session.getAttributes().put("streamStarted", true);
                Flux<ServerSentEvent<String>> body = eventService.events()
                        .map(value -> ServerSentEvent.builder(value).build());
                return ResponseEntity.ok().body(body);
            });
}
```

Ví dụ thể hiện việc cập nhật session trước khi body stream được tiêu thụ. Trong ứng dụng thật, cần kiểm tra response commit lifecycle và lưu session theo cấu hình đang dùng. Không gọi `getSession()` từ callback phát event sau khi stream đã bắt đầu.

Đối với stream chạy lâu, không giữ transaction database mở trong toàn bộ thời gian stream. Session chỉ nên cung cấp thông tin cần thiết để xác thực và khởi động stream; trạng thái lâu dài nên nằm ở dịch vụ hoặc kho dữ liệu phù hợp.

## 15. Cấu hình cookie/header và CORS trong WebFlux

WebFlux sử dụng `WebSessionIdResolver` để giải quyết session ID. Cookie resolver phù hợp với trình duyệt; header resolver có thể phù hợp với API client chủ động quản lý định danh. Cấu hình resolver phải nhất quán trên mọi instance và gateway phải chuyển tiếp header/cookie.

Nếu frontend khác origin và dùng header tùy chỉnh, CORS cần cho phép request header đó và expose response header để JavaScript đọc được. Nếu dùng cookie cross-origin, cần cấu hình credentials, origin cụ thể và thuộc tính SameSite/Secure phù hợp. Không mở CORS wildcard cùng credentials.

Session ID không được truyền qua URL. Log ở ingress, gateway, WebFlux access logging và tracing phải che giá trị cookie/header. Client phải xóa định danh khi nhận tín hiệu hết hạn từ resolver hoặc khi logout thành công.

## 16. Kiểm thử chuỗi getSession và repository reactive

Kiểm thử cần xác minh publisher thực sự được subscribe qua request lifecycle và session được lưu/khôi phục đúng:

| Ca kiểm thử | Cách thực hiện | Kết quả cần xác nhận |
|---|---|---|
| Đọc session | Gửi request có session ID | `getSession()` khôi phục đúng thuộc tính |
| Tạo session | Gửi request tạo thuộc tính mới | Session được start/lưu và response phát định danh |
| Publisher lazy | Gọi `getSession()` nhưng không nối vào chain trong test riêng | Không kỳ vọng thao tác chạy nếu publisher không được subscribe |
| Cập nhật thuộc tính | Dùng `map`/`flatMap` và đọc ở request sau | Thuộc tính đã lưu được khôi phục |
| Không block | Chạy dưới tải và kiểm tra event-loop thread | Không có blocking call trong request path |
| Logout | Gọi `invalidate()` và chờ publisher hoàn tất | Session bị xóa và định danh được expire |
| Lỗi repository | Mô phỏng Redis timeout | Lỗi truyền qua chain và được xử lý đúng status |
| Streaming | Cập nhật session trước khi body bắt đầu | Header/session state sẵn sàng trước response commit |
| Request đồng thời | Hai request cùng cập nhật một thuộc tính | Xác định hành vi race và áp dụng quy tắc nghiệp vụ |
| Nhiều instance | Tạo session ở A, đọc ở B | Repository reactive dùng chung khôi phục được session |

Ví dụ với WebTestClient:

```java
EntityExchangeResult<byte[]> created = webTestClient.post()
        .uri("/api/session/cart")
        .bodyValue(new CartRequest("cart-123"))
        .exchange()
        .expectStatus().isOk()
        .expectHeader().exists("Set-Cookie")
        .expectBody()
        .returnResult();
```

Test cần lấy cookie session từ response, gửi lại trong request kế tiếp và xác nhận thuộc tính được khôi phục. Tên cookie có thể khác theo resolver. Để kiểm tra Redis thực, dùng integration test với Redis test và hai application context/instance cùng trỏ đến một kho. Mock repository không chứng minh TTL, serialization hoặc chia sẻ phiên.

Với reactive pipeline, dùng `StepVerifier` cho service/publisher thuần khi cần kiểm tra thứ tự, completion và error signal. Dùng `WebTestClient` để kiểm tra HTTP lifecycle, cookie/header và response commit. Không chỉ gọi `subscribe()` trong test rồi kiểm tra ngay trạng thái vì thao tác bất đồng bộ có thể chưa hoàn tất.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Session không được tạo hoặc thuộc tính không lưu | Publisher `getSession()` không được nối vào chuỗi hoặc không được subscribe | Trả publisher từ controller và dùng `map`/`flatMap` |
| Controller trả thành công nhưng session chưa cập nhật | Gọi `subscribe()` tách rời khỏi request | Kết hợp thao tác session vào publisher trả về |
| Event-loop bị chặn | Gọi `block()`, JDBC đồng bộ hoặc thư viện blocking trên event loop | Dùng reactive repository hoặc cô lập blocking work trên scheduler phù hợp |
| Request sau không thấy thuộc tính | Session chưa start/lưu, response không phát định danh hoặc repository save lỗi | Kiểm tra response cookie/header, lifecycle và log repository |
| Logout trả về trước khi session bị xóa | `invalidate()` được subscribe tách rời | Nối `Mono<Void>` invalidate vào chuỗi response |
| Lỗi Redis bị trả thành 401 | Exception hạ tầng bị chuyển thành session missing | Phân biệt repository unavailable với session không tồn tại |
| Cookie/header không được cập nhật | Resolver sai, CORS/gateway bỏ header hoặc response đã commit | Kiểm tra resolver, CORS, proxy và response lifecycle |
| Hai request ghi đè session attributes | Cập nhật đồng thời trên snapshot khác nhau | Đưa dữ liệu quan trọng vào kho nghiệp vụ có cập nhật nguyên tử |
| SecurityContext bị mất trong callback | Dùng ThreadLocal hoặc tách subscription khỏi reactive chain | Dùng reactive security context và giữ pipeline liên tục |

## 18. Nguyên tắc triển khai

- Dùng `ServerWebExchange.getSession()` và làm việc với `WebSession`, không dùng `HttpSession` trong WebFlux handler.
- Xem `Mono<WebSession>` là publisher lazy; nối nó vào chuỗi trả về từ controller/handler.
- Dùng `map` cho biến đổi đồng bộ, `flatMap` cho publisher lồng nhau và `then` khi chỉ cần chờ completion.
- Không gọi `block()` hoặc tự `subscribe()` trong request path.
- Để WebSessionManager/Spring Session quản lý save theo response lifecycle; chỉ gọi `save()` tường minh khi cần và phải nối publisher.
- Nối `invalidate()` vào chuỗi trước khi trả response logout.
- Dùng reactive repository và dependency tương thích với WebFlux; không bọc repository đồng bộ bằng `block()` trên event loop.
- Phân biệt lỗi repository với session không tồn tại; không chuyển mọi lỗi thành phiên rỗng.
- Xử lý request đồng thời ở tầng dữ liệu nghiệp vụ; reactive không tự cung cấp khóa session phân tán.
- Kiểm thử bằng `WebTestClient`, `StepVerifier` và backend thật cho cookie/header, TTL, logout, streaming và nhiều instance.

`ServerWebExchange.getSession()` là điểm vào reactive để lấy WebSession trong WebFlux. Khi publisher được nối đúng vào chuỗi xử lý, ứng dụng có thể đọc và cập nhật thuộc tính, để WebFlux/Spring Session lưu thay đổi theo vòng đời response, rồi khôi phục phiên ở request tiếp theo hoặc instance khác. Giữ toàn bộ thao tác trong reactive pipeline giúp tránh chặn event loop, truyền lỗi đúng cách và bảo đảm logout, cập nhật cũng như phát định danh được hoàn tất theo đúng thứ tự.
