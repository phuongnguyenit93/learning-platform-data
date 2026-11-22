# `bindToRouterFunction` cho endpoint chức năng

Spring WebFlux hỗ trợ xây dựng HTTP endpoint theo hai phong cách chính: annotated controller với `@RestController`, hoặc functional endpoint với `RouterFunction` và `HandlerFunction`. Khi ứng dụng dùng functional endpoint, `WebTestClient.bindToRouterFunction(...)` cho phép kiểm thử trực tiếp router bằng request và response giả lập trong bộ nhớ.

Cách này phù hợp khi muốn kiểm tra đường dẫn, HTTP method, request predicate, handler, body codec và response mà không cần khởi động một HTTP server thật. Test sử dụng API gần giống client HTTP: tạo request, gọi `exchange()`, rồi kiểm tra status, header và body.

## 1. Functional endpoint gồm router và handler

Trong mô hình functional của WebFlux, `RouterFunction` quyết định request nào được chuyển đến handler nào. `HandlerFunction` nhận `ServerRequest` và trả về `Mono<ServerResponse>`.

```text
WebTestClient request
        |
        v
RouterFunction<ServerResponse>
        |
        | request predicate khớp?
        v
HandlerFunction<ServerResponse>
        |
        | xử lý ServerRequest
        v
Mono<ServerResponse>
        |
        v
WebTestClient assertions
```

Một router có thể khai báo trực tiếp bằng `RouterFunctions.route(...)` hoặc dùng builder để nhóm nhiều route. Handler có thể là lambda hoặc method reference tới một class chuyên xử lý request.

Ví dụ endpoint chào người dùng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

class GreetingHandler {

    Mono<ServerResponse> greet(ServerRequest request) {
        String name = request.pathVariable("name");
        return ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("Hello, " + name);
    }
}

@Configuration(proxyBeanMethods = false)
class GreetingRoutes {

    @Bean
    GreetingHandler greetingHandler() {
        return new GreetingHandler();
    }

    @Bean
    RouterFunction<ServerResponse> greetingRouter(GreetingHandler handler) {
        return route(GET("/greetings/{name}"), handler::greet);
    }
}
```

`GET("/greetings/{name}")` là request predicate. Khi method và path khớp, router chuyển `ServerRequest` tới `handler.greet(...)`. Handler lấy path variable, tạo response và trả về reactive publisher `Mono<ServerResponse>`.

Trong một ứng dụng hoàn chỉnh, `GreetingHandler` cũng cần được đăng ký thành bean, ví dụ bằng `@Component` hoặc một phương thức `@Bean` trong cấu hình. Ví dụ trên tập trung vào quan hệ giữa router và handler.

## 2. `bindToRouterFunction` tạo môi trường kiểm thử nào?

`WebTestClient.bindToRouterFunction(routerFunction)` nhận một `RouterFunction<?>` và dựng một client kiểm thử gắn trực tiếp với router đó:

```java
WebTestClient client = WebTestClient
        .bindToRouterFunction(greetingRouter)
        .build();
```

Khi gọi `exchange()`, client chuyển request qua hạ tầng xử lý WebFlux trong bộ nhớ, router chọn handler, handler tạo response và client thu response để assertion. Không cần mở cổng TCP hoặc khởi động Netty/Tomcat.

Điểm này giúp test tập trung vào functional endpoint. Router được truyền vào chính là đầu vào quan trọng của bài test; test không cần dựng toàn bộ application context chỉ để kiểm tra một route.

`bindToRouterFunction` khác với các cách bind khác của `WebTestClient`:

| Cách bind | Thành phần được kiểm thử | Khi phù hợp |
|---|---|---|
| `bindToRouterFunction(router)` | Router function được cung cấp và handler mà nó định tuyến tới | Kiểm tra một nhóm functional endpoint độc lập |
| `bindToApplicationContext(context)` | WebFlux application context đã cấu hình | Cần kiểm tra nhiều bean, router, `WebFilter`, codec và cấu hình cùng được nạp trong context |
| `bindToServer()` | Một server đang chạy qua HTTP thật | Cần kiểm tra networking, server connector hoặc tích hợp triển khai |

Với `bindToRouterFunction`, các thành phần được cung cấp qua application context không tự động được đưa vào chỉ vì chúng tồn tại trong ứng dụng. Nếu test cần security filter chain, `WebFilter`, custom codec hoặc cấu hình toàn ứng dụng, hãy cân nhắc bind vào application context hoặc dựng đúng hạ tầng cần thiết cho test.

## 3. Test một route cơ bản

Có thể tạo router trực tiếp trong test để giữ ví dụ nhỏ và không cần khởi động Spring context:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.test.web.reactive.server.WebTestClient.bindToRouterFunction;
import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;
import static org.springframework.web.reactive.function.server.ServerResponse.ok;
import static org.springframework.http.MediaType.TEXT_PLAIN;

class GreetingRouterTests {

    private final RouterFunction<ServerResponse> router =
            route(GET("/greetings/{name}"), request ->
                    ok()
                            .contentType(TEXT_PLAIN)
                            .bodyValue("Hello, " + request.pathVariable("name")));

    private final WebTestClient client = bindToRouterFunction(router).build();

    @Test
    void returnsGreetingForPathVariable() {
        client.get()
                .uri("/greetings/Ada")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(TEXT_PLAIN)
                .expectBody(String.class)
                .isEqualTo("Hello, Ada");
    }
}
```

Các bước trong test tương ứng với một HTTP exchange:

1. `client.get()` tạo request GET.
2. `.uri(...)` đặt URI và path.
3. `.exchange()` gửi request qua router.
4. `expectStatus()` xác nhận status.
5. `expectHeader()` xác nhận response header.
6. `expectBody(String.class)` giải mã response body thành kiểu mong muốn.

Test này chứng minh router nhận đúng path, handler đọc đúng path variable và response có body cùng content type theo hợp đồng.

## 4. Nhóm nhiều route bằng RouterFunctions builder

Ứng dụng thường có nhiều endpoint cùng thuộc một nhóm. Có thể dùng builder để gom route và tái sử dụng handler:

```java
RouterFunction<ServerResponse> orderRoutes(OrderHandler handler) {
    return RouterFunctions.route()
            .GET("/orders/{id}", handler::findById)
            .POST("/orders", handler::create)
            .GET("/orders", handler::search)
            .build();
}
```

Hoặc nhóm route dưới một path prefix:

```java
RouterFunction<ServerResponse> apiRoutes(OrderHandler orderHandler,
                                          CustomerHandler customerHandler) {
    return RouterFunctions.route()
            .path("/api", builder -> builder
                    .GET("/orders/{id}", orderHandler::findById)
                    .POST("/orders", orderHandler::create)
                    .GET("/customers/{id}", customerHandler::findById))
            .build();
}
```

Test nên bind đúng router đã được nhóm để xác nhận route thực sự được ghép vào cây định tuyến:

```java
WebTestClient client = WebTestClient
        .bindToRouterFunction(apiRoutes(orderHandler, customerHandler))
        .build();
```

Nếu test chỉ dựng một router rút gọn khác với router production, nó có thể bỏ sót lỗi cấu hình khi ghép route, prefix hoặc filter. Với các route quan trọng, hãy dùng cùng bean `RouterFunction` mà ứng dụng đăng ký hoặc import cấu hình router tương ứng.

## 5. Kiểm thử request body và response JSON

Functional handler đọc body thông qua `ServerRequest`. Ví dụ tạo đơn hàng:

```java
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

record CreateOrderRequest(
        @jakarta.validation.constraints.NotBlank String productCode,
        @jakarta.validation.constraints.Min(1) int quantity) {
}

record OrderReceipt(String orderId, String productCode, int quantity) {
}

class OrderHandler {

    Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateOrderRequest.class)
                .flatMap(body -> {
                    OrderReceipt receipt = new OrderReceipt(
                            "ORD-100", body.productCode(), body.quantity());

                    return ServerResponse.accepted()
                            .contentType(MediaType.APPLICATION_JSON)
                            .bodyValue(receipt);
                });
    }
}
```

Test gửi JSON body và kiểm tra response:

```java
@Test
void createsOrderFromJsonBody() {
    client.post()
            .uri("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("BOOK-01", 2))
            .exchange()
            .expectStatus().isAccepted()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.orderId").isEqualTo("ORD-100")
            .jsonPath("$.productCode").isEqualTo("BOOK-01")
            .jsonPath("$.quantity").isEqualTo(2);
}
```

`bodyValue(...)` yêu cầu codec của client serialize object thành request body. Ở phía handler, `bodyToMono(...)` dùng codec của WebFlux để deserialize body thành DTO. Test như vậy kiểm tra cả hai chiều chuyển đổi trong luồng functional endpoint.

Nếu muốn gửi raw JSON để kiểm tra trường hợp malformed body, có thể dùng `.bodyValue("{invalid-json")` cùng `contentType(APPLICATION_JSON)`. Khi đó handler thường nhận lỗi decode dưới dạng reactive error; test phải xác nhận cách router hoặc error handler ánh xạ lỗi đó.

## 6. Kiểm thử query parameter, path variable và header

`ServerRequest` cung cấp API để đọc dữ liệu request:

- `pathVariable("id")` đọc biến được khai báo trong route path.
- `queryParam("q")` trả về `Optional<String>` cho query parameter.
- `headers()` truy cập header đã gửi.
- `bodyToMono(...)` hoặc `bodyToFlux(...)` đọc request body theo reactive type.

Ví dụ handler tìm kiếm:

```java
class SearchHandler {

    Mono<ServerResponse> search(ServerRequest request) {
        String keyword = request.queryParam("q").orElse("");
        String language = request.headers()
                .firstHeader("Accept-Language");

        SearchResult result = new SearchResult(keyword, language);
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(result);
    }
}

record SearchResult(String keyword, String language) {
}
```

Test tạo query parameter và header:

```java
client.get()
        .uri(uriBuilder -> uriBuilder
                .path("/search")
                .queryParam("q", "spring webflux")
                .build())
        .header("Accept-Language", "vi-VN")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.keyword").isEqualTo("spring webflux")
        .jsonPath("$.language").isEqualTo("vi-VN");
```

Khi query parameter có ký tự đặc biệt, dùng `uriBuilder` hoặc URI template để mã hóa đúng giá trị. Tránh nối chuỗi URL thủ công vì dấu cách, dấu `&`, `?` và Unicode có thể làm request khác với điều mong muốn.

## 7. Kiểm tra route không khớp và request predicate

Router chỉ gọi handler khi request predicate phù hợp. Predicate có thể kiểm tra HTTP method, path, query parameter, header hoặc content type.

Ví dụ route chỉ nhận GET:

```java
RouterFunction<ServerResponse> router = route(
        GET("/status"),
        request -> ServerResponse.ok().bodyValue("ready"));
```

Test route đúng:

```java
client.get()
        .uri("/status")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("ready");
```

Test path không tồn tại:

```java
client.get()
        .uri("/missing")
        .exchange()
        .expectStatus().isNotFound();
```

Khi một request không khớp router nào, không có handler chức năng được gọi và WebFlux trả về kết quả không tìm thấy theo cơ chế xử lý mặc định hoặc cấu hình của ứng dụng. Nếu ứng dụng định nghĩa not-found handler riêng, test nên kiểm tra response của handler đó.

Đối với predicate kiểm tra header hoặc query parameter, nên viết ít nhất một test khớp và một test không khớp. Nếu router có nhiều route cùng prefix, test cũng cần xác nhận request được chuyển đến đúng handler khi nhiều predicate có thể cùng phù hợp.

## 8. Gắn filter cho RouterFunction và kiểm thử hiệu ứng

Functional endpoint có thể áp dụng `HandlerFilterFunction` để thực hiện logic trước hoặc sau handler. Filter có thể dùng cho logging, đo thời gian, kiểm tra request metadata hoặc chuyển đổi lỗi trong phạm vi router.

```java
import org.springframework.web.reactive.function.server.HandlerFilterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;

HandlerFilterFunction<ServerResponse, ServerResponse> errorFilter =
        (request, next) -> next.handle(request)
                .onErrorResume(OrderNotFoundException.class, ex ->
                        ServerResponse.status(HttpStatus.NOT_FOUND)
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new ApiError("ORDER_NOT_FOUND")));

record ApiError(String code) {
}

class OrderNotFoundException extends RuntimeException {
}

class FailingOrderHandler {
    Mono<ServerResponse> findById(ServerRequest request) {
        return Mono.error(new OrderNotFoundException());
    }
}
```

Áp dụng filter vào router:

```java
RouterFunction<ServerResponse> router = route(
        GET("/orders/{id}"),
        new FailingOrderHandler()::findById)
        .filter(errorFilter);
```

Test cần kích hoạt đúng lỗi và xác nhận filter đã chuyển nó thành response công khai:

```java
client.get()
        .uri("/orders/404")
        .exchange()
        .expectStatus().isNotFound()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.code").isEqualTo("ORDER_NOT_FOUND");
```

Ví dụ này giả định `orderHandler.findById(...)` trả về một `Mono` lỗi với `OrderNotFoundException` khi không tìm thấy đơn hàng. Filter chỉ xử lý lỗi trong luồng handler mà nó bọc. Một `WebExceptionHandler` ở cấp WebFlux có phạm vi rộng hơn và xử lý lỗi ở tầng web handler; hãy chọn đúng cơ chế theo phạm vi cần kiểm thử.

`HandlerFilterFunction` không giống `WebFilter`. Handler filter gắn với RouterFunction và các handler mà router chọn. `WebFilter` thuộc chuỗi filter của WebFlux application, thường được kiểm thử cùng application context hoặc WebTestClient được cấu hình với context.

## 9. Kiểm thử validation trong functional endpoint

Functional endpoint không sử dụng tham số method được Spring bind như annotated controller. Handler nhận `ServerRequest` và chủ động gọi `bodyToMono(...)`; do đó không nên mặc định rằng `@Valid` trên một record hoặc annotation trên handler method sẽ tự chạy giống `@RequestBody` trong `@RestController`.

Một cách rõ ràng là inject Jakarta `Validator` và gọi sau khi decode DTO:

```java
import jakarta.validation.Validator;
import java.util.Set;

class CreateOrderHandler {

    private final Validator validator;

    CreateOrderHandler(Validator validator) {
        this.validator = validator;
    }

    Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateOrderRequest.class)
                .flatMap(body -> {
                    Set<jakarta.validation.ConstraintViolation<CreateOrderRequest>> violations =
                            validator.validate(body);

                    if (!violations.isEmpty()) {
                        return ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new ApiError("VALIDATION_FAILED"));
                    }

                    return ServerResponse.accepted().build();
                });
    }
}
```

Test gửi DTO vi phạm constraint và xác nhận response lỗi:

```java
client.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateOrderRequest("BOOK-01", 0))
        .exchange()
        .expectStatus().isBadRequest()
        .expectBody()
        .jsonPath("$.code").isEqualTo("VALIDATION_FAILED");
```

Trong ví dụ, DTO, `ApiError`, handler và validator phải được cung cấp cho test theo đúng cấu hình. Có thể dùng validator thật để kiểm tra constraint hoặc mock một dependency nghiệp vụ khác. Nếu muốn kiểm tra validation như một thành phần riêng, hãy test validator ở unit test và dùng WebTestClient để kiểm tra mapping từ violation sang response.

## 10. Kiểm thử body rỗng, lỗi decode và response lỗi

Một handler đọc body qua `bodyToMono(...)` có thể nhận lỗi decode khi body không hợp lệ. Cách lỗi được biểu diễn phụ thuộc codec và nơi ứng dụng bắt lỗi.

Ví dụ, nếu handler chuyển lỗi decode thành response `400` bằng `onErrorResume`, test có thể gửi JSON sai:

```java
client.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("{ invalid json")
        .exchange()
        .expectStatus().isBadRequest();
```

Test này chỉ có ý nghĩa nếu router hoặc handler đã định nghĩa cách ánh xạ decode exception. Nếu không có error mapping, lỗi có thể đi tới `WebExceptionHandler` mặc định và tạo response khác. Hãy kiểm tra status, content type và body theo cấu hình thực tế.

Đối với request body tùy chọn, handler có thể xử lý `Mono.empty()` hoặc dùng `switchIfEmpty(...)`. Hãy phân biệt body không có dữ liệu với body JSON chứa `null`; hai trường hợp này có thể đi qua codec theo cách khác nhau.

## 11. Kiểm thử response reactive và streaming

`ServerResponse.bodyValue(...)` phù hợp với một object hoặc một giá trị đơn. Khi handler trả một `Flux<T>`, response có thể phát nhiều phần tử theo dạng streaming hoặc encode thành collection tùy cách cấu hình.

Với response hữu hạn, `expectBodyList(...)` giúp kiểm tra toàn bộ danh sách đã được thu thập:

```java
client.get()
        .uri("/orders")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(OrderView.class)
        .hasSize(2);
```

Nếu cần kiểm tra thứ tự hoặc từng phần tử, có thể lấy body thành `List<OrderView>` rồi assertion trên danh sách.

Với stream mà cần kiểm tra tín hiệu reactive, dùng `returnResult(...)` và Reactor Test `StepVerifier`:

```java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

record EventView(String type) {
}

Flux<EventView> responseBody = client.get()
        .uri("/events")
        .exchange()
        .expectStatus().isOk()
        .returnResult(EventView.class)
        .getResponseBody();

StepVerifier.create(responseBody)
        .expectNextMatches(event -> event.type().equals("CREATED"))
        .expectNextMatches(event -> event.type().equals("UPDATED"))
        .verifyComplete();
```

Với stream vô hạn như server-sent events, không gọi `verifyComplete()` vì stream được thiết kế không kết thúc. Hãy xác nhận số phần tử hoặc điều kiện cần thiết rồi `thenCancel()` để hủy subscription. Test streaming cần chú ý timeout để tránh chờ vô hạn khi handler không phát dữ liệu.

## 12. Khi nào `bindToRouterFunction` chưa đủ?

`bindToRouterFunction` phù hợp để kiểm tra router và handler trong phạm vi được truyền vào. Tuy nhiên, nó không tự chứng minh toàn bộ ứng dụng đã cấu hình đúng.

| Yêu cầu kiểm tra | Cách bind phù hợp |
|---|---|
| Predicate, path, handler và response của một RouterFunction | `bindToRouterFunction(router)` |
| Nhiều router được đăng ký qua cấu hình ứng dụng | `bindToApplicationContext(context)` |
| `WebFilter`, security configuration hoặc bean codec được nạp trong context | Thường dùng `bindToApplicationContext(context)` |
| HTTP server, connector, TLS, network và port thực tế | `bindToServer()` |
| Hành vi business handler với dependency mock | `bindToRouterFunction(...)` với handler được tạo bằng test fixture |
| Mapping route của cả ứng dụng sau khi compose | Bind router bean cuối cùng hoặc application context |

Nếu custom codec hoặc filter được đăng ký trong application context, test router độc lập có thể bỏ qua chúng. Nếu đó chính là điều cần xác nhận, hãy dùng context-based test. Với yêu cầu về network, server connector hoặc TLS, cần một server thật và `bindToServer()`.

## 13. Tổ chức test để giữ router và handler dễ bảo trì

Một cấu trúc thường dễ đọc là chia thành ba phần:

```text
orders/
  OrderHandler.java       xử lý ServerRequest và tạo ServerResponse
  OrderRouter.java        khai báo RouterFunction và request predicates
  OrderHandlerTests.java  kiểm thử handler qua WebTestClient
```

Handler tập trung vào việc đọc request, gọi nghiệp vụ và tạo response. Router tập trung vào path, method, predicate và filter. Test bind router production hoặc một router fixture được tạo từ handler test.

Ví dụ test fixture có thể dựng router trực tiếp từ handler:

```java
OrderHandler handler = new OrderHandler();

RouterFunction<ServerResponse> router = RouterFunctions.route()
        .POST("/orders", handler::create)
        .build();

WebTestClient client = WebTestClient.bindToRouterFunction(router).build();
```

Nếu test tạo lại path và predicate bằng tay thay vì sử dụng router production, nó chỉ chứng minh fixture hoạt động. Với route mapping là điều quan trọng, hãy bind bean router thực tế hoặc import cấu hình tạo router.

## 14. Lỗi thường gặp khi dùng `bindToRouterFunction`

| Cách làm | Vấn đề | Cách làm phù hợp hơn |
|---|---|---|
| Dùng `bindToRouterFunction` nhưng mong mọi bean trong application context xuất hiện | Router binding không tự nạp toàn bộ context của ứng dụng | Bind vào application context khi cần cấu hình toàn cục |
| Test router fixture khác router production | Có thể bỏ sót lỗi ghép route hoặc prefix | Bind router bean cuối cùng hoặc import cấu hình route |
| Chỉ kiểm tra status | Không xác nhận body và header theo hợp đồng | Kiểm tra status, content type và các field response |
| Gọi `.exchange()` rồi giả định handler đã trả kết quả đồng bộ | Reactive handler có thể chưa hoàn tất tại thời điểm đầu | Dùng assertion body hoặc `StepVerifier` để tiêu thụ publisher |
| Dùng `verifyComplete()` với stream vô hạn | Test sẽ chờ đến timeout | Kiểm tra số phần tử rồi `thenCancel()` |
| Mong `@Valid` tự chạy trên DTO trong handler function | Functional handler tự đọc body và không có argument resolver của annotated controller | Gọi `Validator` hoặc dùng cơ chế validation tường minh |
| Mong `@RestControllerAdvice` xử lý mọi lỗi của RouterFunction | Functional handler và annotated controller có đường xử lý khác nhau | Dùng filter hoặc `WebExceptionHandler` phù hợp với router |
| Dùng router test để kết luận server/TLS hoạt động đúng | Không có network connector thật | Bổ sung test với server đang chạy |

## 15. Quy trình viết một test cho functional endpoint

1. Xác định `RouterFunction` thực tế cần kiểm tra và các handler mà nó tham chiếu.
2. Chọn phạm vi: router độc lập, toàn application context hay HTTP server thật.
3. Dựng `WebTestClient.bindToRouterFunction(router).build()` khi chỉ cần router và handler.
4. Gửi request bằng method, URI, header, query parameter và body đúng với client thực.
5. Gọi `exchange()` rồi kiểm tra status, response header và body.
6. Với route predicate, kiểm tra cả trường hợp khớp và không khớp.
7. Với handler filter hoặc error mapping, tạo đúng tình huống để quan sát hiệu ứng của filter.
8. Với reactive stream, dùng `expectBodyList`, `returnResult` hoặc `StepVerifier` tùy loại response.
9. Chuyển sang context/server binding khi test cần các thành phần không có trong router độc lập.

## 16. Tài liệu tham khảo

- [Spring Framework Reference — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): cách thiết lập client và gửi request kiểm thử.
- [Spring Framework Reference — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): RouterFunction, HandlerFunction, ServerRequest và ServerResponse.
- [Spring Framework Reference — RouterFunction](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html#webflux-fn): cách khai báo và compose functional routes.
- [Spring Framework Javadoc — `WebTestClient`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.html): các phương thức bind và API request/response assertion.
- [Reactor Test — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): kiểm thử tín hiệu của publisher reactive.

`bindToRouterFunction` tạo một ranh giới kiểm thử gọn cho functional endpoint: request đi qua router và handler đã chọn, response được thu lại để kiểm tra bằng `WebTestClient`. Hãy bind router production khi cần bảo vệ mapping thật, kiểm tra body và header theo hợp đồng, và dùng context/server binding khi yêu cầu vượt ra ngoài phạm vi của một RouterFunction.
