# RouterFunction, HandlerFunction, ServerRequest và ServerResponse trong Spring WebFlux

## 1. WebFlux.fn là gì?

**WebFlux.fn** là mô hình khai báo endpoint theo hàm của Spring WebFlux. Thay vì gắn mapping lên method bằng `@GetMapping`, `@PostMapping` hoặc `@RequestMapping`, ta tạo các hàm xử lý request rồi khai báo quy tắc định tuyến bằng Java API.

Bốn hợp đồng trung tâm:

- **`RouterFunction<T extends ServerResponse>`**: xác định request nào được chuyển tới handler nào.
- **`HandlerFunction<T extends ServerResponse>`**: nhận một `ServerRequest` và trả về Publisher chứa `ServerResponse`.
- **`ServerRequest`**: cung cấp thông tin HTTP request và API đọc body theo kiểu reactive.
- **`ServerResponse`**: mô tả status, headers và body sẽ được ghi ra HTTP response.

WebFlux.fn vẫn chạy trên Reactive Core của Spring WebFlux. Nó không phải một HTTP server khác, không thay thế Reactor và không tự tạo thread mới. Điểm khác biệt chính là **cách tổ chức routing và handler**.

~~~text
HTTP request
    |
    v
DispatcherHandler
    |
    v
RouterFunctionMapping
    |
    +--> RouterFunction kiểm tra RequestPredicate
    |          |
    |          +--> match: HandlerFunction
    |          |
    |          +--> không match: thử route tiếp theo
    |
    v
HandlerFunction.handle(ServerRequest)
    |
    v
Mono<ServerResponse>
    |
    v
HandlerFunctionAdapter
    |
    v
ServerResponseResultHandler
    |
    v
HttpMessageWriter / response body
    |
    v
HTTP response
~~~

WebFlux.fn là lựa chọn phù hợp khi muốn tập trung quy tắc route trong một cấu hình rõ ràng, gom handler theo nhóm nghiệp vụ, tái sử dụng predicate/filter, hoặc xây API có nhiều route lồng nhau. Mô hình annotation vẫn phù hợp với controller có nhiều method và cấu trúc quen thuộc. Hai mô hình có thể cùng tồn tại trong một ứng dụng WebFlux.

## 2. Bốn hợp đồng cốt lõi

### 2.1. `RouterFunction`: ánh xạ request thành handler

Về khái niệm, hợp đồng có dạng:

~~~java
public interface RouterFunction<T extends ServerResponse> {
    Mono<HandlerFunction<T>> route(ServerRequest request);
}
~~~

Khi request khớp một route, `route(request)` trả về `Mono` chứa `HandlerFunction` tương ứng. Nếu không có route phù hợp, nó trả về `Mono.empty()` để cơ chế dispatch tiếp tục tìm handler khác hoặc kết thúc với 404.

Bạn hiếm khi cần tự triển khai interface này. Thông thường, dùng `RouterFunctions.route()` để xây route bằng builder:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/hello", request ->
        ServerResponse.ok().bodyValue("Hello WebFlux.fn"))
    .build();
~~~

Một `RouterFunction` có thể kết hợp với route khác bằng `and(...)` hoặc được tạo từ predicate và handler. Khi có nhiều route, thứ tự khai báo có ý nghĩa: route được xét lần lượt, vì vậy nên đặt route cụ thể trước route tổng quát có thể khớp cùng request.

### 2.2. `HandlerFunction`: xử lý một request đã được định tuyến

Hợp đồng:

~~~java
@FunctionalInterface
public interface HandlerFunction<T extends ServerResponse> {
    Mono<T> handle(ServerRequest request);
}
~~~

Một handler nhận request đã khớp route và trả về `Mono<ServerResponse>`. Nó có thể là lambda ngắn hoặc method reference trỏ tới method trong một class handler:

~~~java
HandlerFunction<ServerResponse> hello = request ->
    ServerResponse.ok().bodyValue("Hello");
~~~

Với ứng dụng thực tế, nên gom các handler cùng nghiệp vụ vào class riêng, ví dụ `ProductHandler`, `OrderHandler` hoặc `AccountHandler`. Cách này giữ router tập trung vào mapping và để handler tập trung vào logic HTTP/domain.

### 2.3. `ServerRequest`: đọc request một cách bất biến

`ServerRequest` là interface bất biến, cung cấp các thông tin như:

- `method()`, `methodName()`: HTTP method.
- `uri()`, `path()`: URI và path.
- `pathVariable(name)`: biến path đã được route khai báo.
- `queryParam(name)`: giá trị query parameter dạng `Optional<String>`.
- `headers()`, `cookies()`: headers và cookies.
- `remoteAddress()`: địa chỉ remote nếu có.
- `principal()`: Publisher chứa principal khi có tích hợp xác thực.
- `attributes()` và `attribute(name)`: thuộc tính gắn với request.
- `bodyToMono(Class)`, `bodyToFlux(Class)`: đọc và decode body thành Publisher.

Ví dụ đọc path và query:

~~~java
public Mono<ServerResponse> search(ServerRequest request) {
    String category = request.pathVariable("category");
    String keyword = request.queryParam("q").orElse("");

    return ServerResponse.ok()
        .bodyValue("category=" + category + ", q=" + keyword);
}
~~~

Nếu cần thay đổi request trước khi đưa tới handler, dùng `ServerRequest.from(request)` để tạo builder và build một request mới. Không sửa trực tiếp object request ban đầu.

### 2.4. `ServerResponse`: mô tả HTTP response

`ServerResponse` cũng là interface bất biến. Thay vì sửa object response tại chỗ, ta dùng builder để tạo response mới.

Các factory thường gặp:

| Factory | Ý nghĩa |
| --- | --- |
| `ServerResponse.ok()` | HTTP 200 |
| `ServerResponse.created(uri)` | HTTP 201 và Location |
| `ServerResponse.accepted()` | HTTP 202 |
| `ServerResponse.noContent()` | HTTP 204 |
| `ServerResponse.badRequest()` | HTTP 400 |
| `ServerResponse.notFound()` | HTTP 404 |
| `ServerResponse.status(code)` | Status tùy chọn |

Các cách hoàn tất builder:

- `bodyValue(value)`: ghi một object đã có.
- `body(publisher, elementClass)`: ghi body từ Publisher.
- `build()`: response không có body.
- `headers(...)`, `contentType(...)`, `header(...)`: thiết lập metadata trước khi build.

Ví dụ:

~~~java
return ServerResponse.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("status", "ready"));
~~~

`bodyValue` và `body` trả về `Mono<ServerResponse>`. Vì vậy handler có thể kết hợp kết quả này với `flatMap`, `switchIfEmpty`, `onErrorResume` hoặc các toán tử Reactor khác.

## 3. Khai báo route bằng `RouterFunctions.route()`

### 3.1. Route theo HTTP method và path

Builder cung cấp các shortcut dễ đọc:

~~~java
RouterFunction<ServerResponse> router = RouterFunctions.route()
    .GET("/products", handler::list)
    .GET("/products/{id}", handler::get)
    .POST("/products", handler::create)
    .PUT("/products/{id}", handler::update)
    .DELETE("/products/{id}", handler::delete)
    .build();
~~~

Mỗi method reference phải tương thích với `HandlerFunction<ServerResponse>`, tức method đích nhận `ServerRequest` và trả về `Mono<ServerResponse>`.

Đoạn trên là mapping minh họa; các method `list`, `get`, `create`, `update` và `delete` phải được triển khai trong class handler.

### 3.2. Kết hợp `RequestPredicate`

Một route có thể yêu cầu nhiều điều kiện ngoài method/path:

- `accept(MediaType...)`: kiểm tra header `Accept`.
- `contentType(MediaType...)`: kiểm tra `Content-Type`.
- `path(String)`: kiểm tra path.
- `method(HttpMethod)`: kiểm tra HTTP method.
- `queryParam(name, value)`: kiểm tra query parameter.
- `headers(Predicate<ServerRequest.Headers>)`: điều kiện trên headers.
- `GET(path)`, `POST(path)`, ...: predicate theo HTTP method.

Ví dụ:

~~~java
RouterFunction<ServerResponse> router = RouterFunctions.route()
    .GET("/products/{id}",
        accept(MediaType.APPLICATION_JSON),
        handler::get)
    .POST("/products",
        contentType(MediaType.APPLICATION_JSON),
        handler::create)
    .build();
~~~

Route GET chỉ nhận request có khả năng chấp nhận JSON; route POST yêu cầu body có `Content-Type` là JSON. Predicate không tự giải mã body hoặc xác thực nghiệp vụ. Nó chỉ quyết định request có khớp route hay không.

### 3.3. Kết hợp predicate bằng `and`, `or` và `negate`

~~~java
RequestPredicate jsonGet = method(HttpMethod.GET)
    .and(path("/reports/**"))
    .and(accept(MediaType.APPLICATION_JSON));

RequestPredicate reportRequest =
    path("/reports/**").or(path("/exports/**"));

RequestPredicate nonHealth = path("/health").negate();
~~~

- `and` yêu cầu cả hai predicate đều đúng.
- `or` chỉ cần một predicate đúng.
- `negate` đảo kết quả predicate.

Predicate giúp tránh lặp điều kiện và tạo route có ý nghĩa nghiệp vụ. Không nên nhét kiểm tra quyền phức tạp hoặc truy vấn database vào predicate đồng bộ; các việc đó phù hợp với filter hoặc handler reactive.

### 3.4. Thứ tự route rất quan trọng

Router function đánh giá các route theo thứ tự. Nếu route tổng quát khớp trước, route cụ thể phía sau có thể không bao giờ được dùng.

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/files/{id}", handler::getFile)
    .GET("/files/**", handler::listFilesUnderPath)
    .build();
~~~

Đặt `/files/{id}` trước `/files/**` nếu cả hai có thể khớp cùng request. Điều này khác với cách dispatch annotation, nơi Spring có quy tắc lựa chọn mapping cụ thể hơn.

Khi có nhiều bean `RouterFunction` trong application context, `RouterFunctionMapping` sắp xếp chúng theo order và kết hợp. Nếu nhiều router có path chồng lấn, thứ tự bean/router phải được thiết kế rõ ràng, không dựa vào thứ tự file Java hoặc thứ tự khởi tạo tình cờ.

## 4. Route lồng nhau bằng `path` và `nest`

### 4.1. Gom nhóm theo path prefix

`path("/api", builder -> ...)` cho phép nhóm các route cùng tiền tố:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .path("/api", api -> api
        .GET("/products", handler::list)
        .GET("/products/{id}", handler::get)
        .POST("/products", handler::create))
    .build();
~~~

Các path bên trong được hiểu tương đối với prefix `/api`. Nhóm route theo tài nguyên giúp cấu hình dễ đọc khi API có nhiều endpoint.

### 4.2. Nest theo điều kiện chung

`nest(predicate, builder -> ...)` áp dụng một predicate cho cả nhóm route:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .path("/api", api -> api
        .nest(accept(MediaType.APPLICATION_JSON), json -> json
            .GET("/products", handler::list)
            .GET("/products/{id}", handler::get))
        .POST("/products",
            contentType(MediaType.APPLICATION_JSON),
            handler::create))
    .build();
~~~

Hai route GET trong nhóm yêu cầu `Accept: application/json`. Route POST nằm ngoài nhóm `nest` đó và có predicate `Content-Type` riêng.

Không lạm dụng nhiều tầng `nest` khiến path và điều kiện khó theo dõi. Nếu một route chỉ có một điều kiện riêng, overload nhận predicate trực tiếp thường dễ đọc hơn.

### 4.3. Chia router thành nhiều module

Có thể xây các RouterFunction riêng theo miền nghiệp vụ:

~~~java
RouterFunction<ServerResponse> productRoutes = productRouter.routes();
RouterFunction<ServerResponse> orderRoutes = orderRouter.routes();

RouterFunction<ServerResponse> api = productRoutes.and(orderRoutes);
~~~

`and` tạo router kết hợp: khi router bên trái không tìm thấy handler, router bên phải được thử. Nếu có path trùng, router bên trái có thể thắng; do đó cần xác định thứ tự ghép.

Với ứng dụng Spring Boot, mỗi router có thể là một bean `RouterFunction<ServerResponse>`. Framework sẽ phát hiện, sắp xếp và kết hợp chúng thông qua `RouterFunctionMapping`.

## 5. Đọc request bằng `ServerRequest`

### 5.1. Path variable và query parameter

~~~java
public Mono<ServerResponse> getById(ServerRequest request) {
    String id = request.pathVariable("id");

    return repository.findById(id)
        .flatMap(product -> ServerResponse.ok().bodyValue(product))
        .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

`pathVariable` lấy biến đã khai báo trong route như `/products/{id}`. Với query parameter tùy chọn:

~~~java
String sort = request.queryParam("sort").orElse("name");
~~~

Nếu cần xử lý nhiều giá trị cùng tên, dùng API query parameters phù hợp thay vì giả định luôn chỉ có một giá trị.

### 5.2. Headers, cookies và principal

~~~java
String requestId = request.headers().firstHeader("X-Request-Id");
String userAgent = request.headers().firstHeader("User-Agent");
HttpCookie session = request.cookies().getFirst("SESSION");
~~~

`request.principal()` trả Publisher vì việc lấy principal có thể bất đồng bộ và phụ thuộc Spring Security. Không giả định request luôn có user đã đăng nhập; xử lý trường hợp Publisher rỗng.

Không dùng header do client gửi như bằng chứng xác thực nếu nó chưa được gateway đáng tin hoặc security layer xác minh. Router predicate có thể kiểm tra header kỹ thuật, nhưng phân quyền nên dùng Spring Security reactive.

### 5.3. Đọc body thành `Mono<T>`

~~~java
public Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateProduct.class)
        .flatMap(product -> repository.save(product))
        .flatMap(saved -> ServerResponse
            .created(URI.create("/products/" + saved.id()))
            .bodyValue(saved));
}
~~~

`bodyToMono` dùng codec để giải mã request body thành một object. Publisher chỉ được tiêu thụ khi subscription đi tới nó. Vì thế hãy ghép nó vào chuỗi Publisher handler trả về; không tự gọi `subscribe()`.

Nếu body có thể rỗng, xử lý bằng `switchIfEmpty` hoặc kiểm tra hợp đồng endpoint. Nếu JSON không hợp lệ hoặc media type không được hỗ trợ, lỗi decode đi vào reactive error path.

### 5.4. Đọc body thành `Flux<T>`

~~~java
public Mono<ServerResponse> importRows(ServerRequest request) {
    return request.bodyToFlux(ImportRow.class)
        .flatMap(repository::save, 8)
        .count()
        .flatMap(total -> ServerResponse.ok().bodyValue(
            Map.of("saved", total)));
}
~~~

`bodyToFlux` phù hợp khi request biểu diễn nhiều phần tử. `flatMap(..., 8)` giới hạn concurrency của thao tác lưu ở mức tối đa 8 inner Publisher đồng thời; nếu cần giữ thứ tự, cân nhắc `concatMap` hoặc `flatMapSequential`.

Không gom một stream lớn thành `collectList()` chỉ để thuận tiện nếu có thể xử lý từng item. Chọn codec và media type phù hợp với định dạng đầu vào, ví dụ NDJSON cho các object JSON phân tách theo dòng.

### 5.5. Request body thường chỉ tiêu thụ một lần

Body là stream dữ liệu gắn với HTTP request. Không nên tạo hai nhánh độc lập rồi subscribe vào cùng body Publisher. Hãy decode một lần và xử lý giá trị trong cùng chuỗi:

~~~java
return request.bodyToMono(CreateProduct.class)
    .flatMap(input ->
        repository.save(input)
            .flatMap(saved -> audit(saved)
                .thenReturn(saved)))
    .flatMap(saved -> ServerResponse.ok().bodyValue(saved));
~~~

Nếu cần dùng dữ liệu ở nhiều nơi, chia sẻ object đã decode trong cùng `flatMap` hoặc tạo một cấu trúc kết quả chứa các giá trị cần thiết. Chỉ cache body khi đã hiểu giới hạn bộ nhớ, số subscriber và lifecycle request.

## 6. Tạo response bằng `ServerResponse`

### 6.1. Response thành công với object

~~~java
return ServerResponse.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(product);
~~~

`bodyValue` nhận object đã có và framework chọn `HttpMessageWriter` để encode. Nếu object không có codec phù hợp, response có thể lỗi khi ghi.

### 6.2. Response body từ Publisher

~~~java
Flux<Product> products = repository.findAll();

return ServerResponse.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .body(products, Product.class);
~~~

`body` nhận Publisher và class phần tử để writer biết kiểu cần encode. Có thể dùng `Mono` hoặc `Flux`. Với JSON array, codec có thể aggregate; nếu muốn stream từng phần tử, chọn media type phù hợp như NDJSON hoặc SSE và kiểm thử writer thực tế.

### 6.3. Response không có body

~~~java
return ServerResponse.noContent().build();
~~~

Các trường hợp phổ biến:

~~~java
return ServerResponse.notFound().build();
return ServerResponse.accepted().build();
return ServerResponse.status(HttpStatus.CONFLICT).build();
~~~

Response không có body vẫn là một `Mono<ServerResponse>` và được framework ghi status/header theo lifecycle bình thường.

### 6.4. Response created và Location

~~~java
URI location = URI.create("/api/products/" + saved.id());

return ServerResponse.created(location)
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(saved);
~~~

`created(uri)` tạo response 201 và thiết lập Location. URI nên phản ánh resource vừa tạo và phù hợp với base path/public URL của ứng dụng. Nếu ứng dụng chạy sau reverse proxy với context path, cần cân nhắc cách dựng URI theo cấu hình deployment.

### 6.5. Headers và cookies

~~~java
return ServerResponse.ok()
    .header("X-Result-Source", "catalog")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(product);
~~~

Có thể thiết lập headers qua builder trước khi hoàn tất. Không cố sửa headers sau khi body đã bắt đầu ghi và response đã committed. Với cookie/session, cân nhắc API chuyên dụng và chính sách bảo mật như Secure, HttpOnly, SameSite.

## 7. Filter trong WebFlux.fn

Functional routing builder cung cấp ba cách can thiệp thường dùng: `before`, `after` và `filter`.

### 7.1. `before`: biến đổi request trước handler

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/hello", handler::hello)
    .before(request -> ServerRequest.from(request)
        .header("X-Route-Source", "functional")
        .build())
    .build();
~~~

`before` nhận request đã match route và trả về request mới để chuyển tiếp. Vì `ServerRequest` bất biến, dùng builder `ServerRequest.from(request)` thay vì sửa request ban đầu.

`before` hữu ích để bổ sung metadata hoặc chuẩn hóa request trong phạm vi router. Nếu cần áp dụng cho toàn bộ HTTP pipeline, kể cả controller annotation hoặc route khác, hãy cân nhắc `WebFilter`.

### 7.2. `after`: quan sát hoặc biến đổi response

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/hello", handler::hello)
    .after((request, response) -> {
        System.out.println(
            request.method() + " " + request.path()
            + " -> " + response.statusCode());
        return response;
    })
    .build();
~~~

`after` nhận request và response sau handler, có thể trả response khác nếu cần. Ở đây ta chỉ log status. Response vẫn là mô tả bất biến; nếu muốn thay đổi, dùng builder từ response phù hợp thay vì giả định có thể mutate trực tiếp.

Lưu ý: `after` quan sát đối tượng response ở tầng handler. Nó không phải xác nhận rằng toàn bộ byte đã được client nhận hoặc xử lý thành công.

### 7.3. `filter`: bao quanh HandlerFunction

`filter` nhận `ServerRequest` và handler kế tiếp. Nó có thể gọi handler, biến đổi kết quả hoặc short-circuit:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> authFilter =
    (request, next) -> {
        String token = request.headers().firstHeader("X-Api-Key");

        if ("demo-secret".equals(token)) {
            return next.handle(request);
        }

        return ServerResponse.status(HttpStatus.UNAUTHORIZED).build();
    };
~~~

Đây chỉ là ví dụ minh họa predicate kiểm tra key; không dùng secret hard-code như cơ chế xác thực production. Trong ứng dụng thực tế, dùng Spring Security reactive, token verifier và quy tắc authorization đáng tin cậy.

Có thể xử lý lỗi trong filter:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> badRequestFilter =
    (request, next) -> next.handle(request)
        .onErrorResume(IllegalArgumentException.class, error ->
            ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("error", error.getMessage())));
~~~

Filter trên chỉ ánh xạ `IllegalArgumentException`. Lỗi khác tiếp tục truyền ra ngoài để exception handling của framework xử lý.

### 7.4. Phạm vi của filter lồng nhau

Filter được khai báo ở builder nào sẽ áp dụng cho các route thuộc builder đó. Filter trong một nhóm nested route không tự động áp dụng cho route ở cấp ngoài hoặc một router độc lập.

Hãy đặt filter tại đúng cấp:

- Cross-cutting concern của toàn ứng dụng: `WebFilter`.
- Concern của một nhóm functional routes: filter ở builder nhóm đó.
- Concern của một handler đơn: xử lý ngay trong handler hoặc compose một hàm riêng.

CORS cho functional endpoint được hỗ trợ qua cơ chế CORS của WebFlux, thường dùng `CorsWebFilter` hoặc cấu hình tương ứng; không nên tự viết lại toàn bộ CORS bằng filter route nếu framework đã cung cấp chính sách.

## 8. Xử lý lỗi trong handler và route filter

### 8.1. Lỗi nghiệp vụ trong handler

Handler có thể trả Publisher lỗi:

~~~java
public Mono<ServerResponse> get(ServerRequest request) {
    return repository.findById(request.pathVariable("id"))
        .flatMap(product -> ServerResponse.ok().bodyValue(product))
        .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

Không tìm thấy dữ liệu được biểu diễn bằng response 404. Nếu lỗi là lỗi hệ thống hoặc nghiệp vụ cần xử lý riêng, có thể dùng `onErrorResume` trong pipeline hoặc để lỗi đi tới exception handling bên ngoài.

### 8.2. Ánh xạ lỗi bằng filter

Một filter có thể xử lý nhóm lỗi áp dụng cho một router:

~~~java
.filter((request, next) -> next.handle(request)
    .onErrorResume(ProductValidationException.class, error ->
        ServerResponse.badRequest()
            .bodyValue(Map.of("error", "INVALID_PRODUCT"))))
~~~

Không trả message nội bộ, SQL hoặc stack trace cho client. Dùng error code ổn định; log chi tiết phía server với correlation ID.

### 8.3. Phân biệt route filter, WebFilter và WebExceptionHandler

| Cơ chế | Phạm vi | Dùng khi |
| --- | --- | --- |
| `HandlerFilterFunction` | Các handler trong RouterFunction được gắn filter | Logic trước/sau handler functional, short-circuit, xử lý lỗi theo route |
| `WebFilter` | Toàn bộ chuỗi WebFlux web handler | Request ID, CORS, logging, security integration, logic toàn ứng dụng |
| `WebExceptionHandler` | Lỗi thoát ra ngoài filter/handler chain | Chuyển lỗi cấp web thành HTTP response hoặc chuyển tiếp lỗi |

Nếu lỗi phát sinh trong handler function và filter đã ánh xạ nó thành response, lỗi không đi tiếp tới WebExceptionHandler. Nếu filter không xử lý, lỗi tiếp tục theo reactive error path. Không dùng nhiều tầng cùng ghi một response cho cùng lỗi.

### 8.4. Không tìm thấy route và lỗi trong handler là hai việc khác nhau

Nếu không có RouterFunction nào khớp, framework không gọi handler của route đó; request thường kết thúc với 404. Nếu route đã khớp nhưng handler ném lỗi, đó là lỗi trong quá trình xử lý và đi theo error pipeline. Hãy phân biệt 404 do không có route với 404 do handler chủ động trả về khi không tìm thấy resource.

## 9. Kết hợp WebFlux.fn với Spring Boot

### 9.1. Khai báo RouterFunction bean

Trong ứng dụng Spring Boot, chỉ cần khai báo bean:

~~~java
@Configuration
public class ApiRoutes {

    @Bean
    RouterFunction<ServerResponse> routes(ProductHandler handler) {
        return RouterFunctions.route()
            .GET("/products", handler::list)
            .GET("/products/{id}", handler::get)
            .POST("/products", handler::create)
            .build();
    }
}
~~~

Spring Boot WebFlux starter cung cấp hạ tầng functional endpoint. Trong WebFlux Java configuration, các thành phần chính gồm:

- `RouterFunctionMapping`: tìm và kết hợp các bean `RouterFunction<?>`.
- `HandlerFunctionAdapter`: cho phép `DispatcherHandler` gọi `HandlerFunction` đã match.
- `ServerResponseResultHandler`: ghi kết quả `ServerResponse` vào HTTP response.

Do đó functional endpoint vẫn nằm trong lifecycle của `DispatcherHandler`. Có thể dùng chung với controller annotation trong cùng ứng dụng.

### 9.2. Không cần tự tạo HTTP server cho router

`RouterFunctions.toHttpHandler(router)` có thể chuyển RouterFunction thành `HttpHandler` để cài vào server adapter trong trường hợp cần dựng hạ tầng thủ công.

Nhưng trong ứng dụng Spring Boot thông thường, để router là bean là đủ. Boot và WebFlux Config sẽ ghép route với server đang dùng, ví dụ Reactor Netty. Tự tạo server hoặc `HttpHandler` thứ hai có thể khiến cấu hình phức tạp và route không nằm trong pipeline mà bạn mong đợi.

### 9.3. Dùng functional route cùng annotated controller

Hai mô hình cùng dựa trên Reactive Core và có thể cùng tồn tại:

- Controller annotation phù hợp khi muốn nhóm endpoint theo class và method mapping.
- WebFlux.fn phù hợp khi muốn route/handler được biểu diễn như object và function có thể compose.
- `WebFilter` và `WebExceptionHandler` vẫn có phạm vi toàn pipeline bất kể route dùng mô hình nào.

Nếu cùng khai báo hai endpoint trùng path/method trong hai mô hình, mapping có thể cạnh tranh. Hãy tránh overlap hoặc xác định rõ order để không phụ thuộc cấu hình ngẫu nhiên.

## 10. Ví dụ Spring Boot 3.5.7 + Java 17 hoàn chỉnh

Ví dụ xây API quản lý sản phẩm nhỏ bằng WebFlux.fn:

- `GET /api/products`: liệt kê sản phẩm.
- `GET /api/products/{id}`: lấy một sản phẩm.
- `POST /api/products`: tạo sản phẩm từ JSON.
- Route filter ánh xạ lỗi validation thành HTTP 400.
- `before` gắn header request cho nhóm route; `after` log status.

Dùng Spring Boot **3.5.7**, Java 17 và Maven. Project chỉ dùng `spring-boot-starter-webflux`; không thêm `spring-boot-starter-web` vì starter MVC có thể làm ứng dụng chọn sai web stack.

### 10.1. Cấu trúc thư mục

~~~text
webflux-functional-api/
├── pom.xml
└── src/main/java/example/functional/
    ├── FunctionalApiApplication.java
    ├── ProductHandler.java
    └── ProductRoutes.java
~~~

### 10.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-functional-api</artifactId>
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

### 10.3. `FunctionalApiApplication.java`

~~~java
package example.functional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FunctionalApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(FunctionalApiApplication.class, args);
    }
}
~~~

### 10.4. `ProductHandler.java`

~~~java
package example.functional;

import java.net.URI;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class ProductHandler {

    public record Product(String id, String name, int price) {}

    public record CreateProduct(String name, int price) {}

    private final List<Product> products =
        new CopyOnWriteArrayList<>(List.of(
            new Product("1", "Keyboard", 120),
            new Product("2", "Mouse", 45)
        ));

    private final AtomicLong sequence = new AtomicLong(2);

    public Mono<ServerResponse> list(ServerRequest request) {
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(Flux.fromIterable(products), Product.class);
    }

    public Mono<ServerResponse> get(ServerRequest request) {
        String id = request.pathVariable("id");

        return Mono.justOrEmpty(
                products.stream()
                    .filter(product -> product.id().equals(id))
                    .findFirst())
            .flatMap(product -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(product))
            .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateProduct.class)
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Request body is required")))
            .flatMap(input -> {
                if (input.name() == null || input.name().isBlank()
                        || input.price() < 0) {
                    return Mono.error(new IllegalArgumentException(
                        "name is required and price must be non-negative"));
                }

                Product saved = new Product(
                    Long.toString(sequence.incrementAndGet()),
                    input.name(),
                    input.price()
                );
                products.add(saved);

                URI location = URI.create("/api/products/" + saved.id());

                return ServerResponse.created(location)
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(saved);
            });
    }
}
~~~

Danh sách trong ví dụ dùng `CopyOnWriteArrayList` để demo đọc/ghi đơn giản với số lượng nhỏ. Nó không phải lựa chọn tối ưu cho workload ghi nhiều; ứng dụng thật nên dùng repository/database reactive hoặc cấu trúc lưu trữ phù hợp.

### 10.5. `ProductRoutes.java`

~~~java
package example.functional;

import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.web.reactive.function.server.RequestPredicates.accept;
import static org.springframework.web.reactive.function.server.RequestPredicates.contentType;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.HandlerFilterFunction;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class ProductRoutes {

    @Bean
    RouterFunction<ServerResponse> productRouter(ProductHandler handler) {
        HandlerFilterFunction<ServerResponse, ServerResponse> badRequestFilter =
            (request, next) -> next.handle(request)
                .onErrorResume(IllegalArgumentException.class, error ->
                    ServerResponse.badRequest()
                        .contentType(APPLICATION_JSON)
                        .bodyValue(Map.of("error", error.getMessage())));

        return RouterFunctions.route()
            .path("/api", api -> api
                .nest(accept(APPLICATION_JSON), json -> json
                    .GET("/products", handler::list)
                    .GET("/products/{id}", handler::get))
                .POST("/products",
                    contentType(APPLICATION_JSON),
                    handler::create)
                .filter(badRequestFilter))
            .before(request -> ServerRequest.from(request)
                .header("X-Functional-Route", "products")
                .build())
            .after((request, response) -> {
                System.out.println(
                    request.method() + " " + request.path()
                    + " -> " + response.statusCode());
                return response;
            })
            .build();
    }
}
~~~

Các điểm cần quan sát:

1. `path("/api", ...)` gom các route có prefix chung.
2. `nest(accept(APPLICATION_JSON), ...)` áp dụng điều kiện Accept cho hai route GET.
3. Route POST kiểm tra `Content-Type` JSON riêng.
4. `HandlerFilterFunction` chuyển lỗi validation thành response 400.
5. `before` tạo request mới có header `X-Functional-Route`.
6. `after` quan sát status sau handler và trả response tiếp tục tới writer.

### 10.6. Chạy ứng dụng

Cài JDK 17+ và Maven, từ thư mục chứa `pom.xml` chạy:

~~~bash
mvn spring-boot:run
~~~

Lấy một sản phẩm:

~~~bash
curl -i http://localhost:8080/api/products/1 -H "Accept: application/json"
~~~

Response body dự kiến:

~~~json
{"id":"1","name":"Keyboard","price":120}
~~~

Liệt kê:

~~~bash
curl -i http://localhost:8080/api/products -H "Accept: application/json"
~~~

Body chứa hai sản phẩm ban đầu. Thứ tự từ list ban đầu là Keyboard rồi Mouse.

Tạo sản phẩm:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"Pen","price":15}'
~~~

Response dự kiến có status `201 Created`, header `Location` trỏ tới `/api/products/3` và body:

~~~json
{"id":"3","name":"Pen","price":15}
~~~

Thử dữ liệu không hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"","price":-1}'
~~~

Response dự kiến là HTTP 400 với body tương tự:

~~~json
{"error":"name is required and price must be non-negative"}
~~~

Thử id không tồn tại:

~~~bash
curl -i http://localhost:8080/api/products/999
~~~

Handler trả HTTP 404 với body rỗng.

## 11. Kiểm thử functional endpoint với `WebTestClient`

Có thể kiểm thử toàn ứng dụng đang chạy bằng `@SpringBootTest` và `WebTestClient`:

~~~java
package example.functional;

import static org.springframework.http.MediaType.APPLICATION_JSON;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ProductRoutesIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void getsExistingProduct() {
        client.get()
            .uri("/api/products/1")
            .accept(APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.name").isEqualTo("Keyboard");
    }

    @Test
    void createsProduct() {
        client.post()
            .uri("/api/products")
            .contentType(APPLICATION_JSON)
            .bodyValue(new ProductHandler.CreateProduct("Pen", 15))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists("Location")
            .expectBody()
            .jsonPath("$.name").isEqualTo("Pen");
    }

    @Test
    void mapsInvalidInputToBadRequest() {
        client.post()
            .uri("/api/products")
            .contentType(APPLICATION_JSON)
            .bodyValue(new ProductHandler.CreateProduct("", -1))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.error")
            .isEqualTo("name is required and price must be non-negative");
    }

    @Test
    void returnsNotFoundForUnknownId() {
        client.get()
            .uri("/api/products/999")
            .accept(APPLICATION_JSON)
            .exchange()
            .expectStatus().isNotFound();
    }
}
~~~

Đây là test tích hợp dùng server random port. Có thể kiểm thử RouterFunction độc lập bằng `WebTestClient.bindToRouterFunction(router).build()` khi muốn test routing mà không dựng toàn bộ ApplicationContext. Kiểm thử tích hợp vẫn có ích để xác minh bean discovery, codec, handler adapter và response writer cùng hoạt động.

Chạy test:

~~~bash
mvn test
~~~

Các assertion tập trung vào HTTP contract: status, headers và JSON body. Không nên kiểm tra thứ tự thread hoặc thời gian tuyệt đối của một pipeline reactive trong các test routing thông thường.

## 12. Phân biệt WebFlux.fn với annotation controller

| Tiêu chí | WebFlux.fn | Annotated controller |
| --- | --- | --- |
| Khai báo route | `RouterFunction` + predicate | `@RequestMapping`, `@GetMapping`, ... |
| Handler | `HandlerFunction` hoặc class handler | Method trong `@Controller` |
| Request | `ServerRequest` | Tham số method được resolver cung cấp |
| Response | `ServerResponse` | Return value được HandlerResultHandler xử lý |
| Nhóm route | `path`, `nest`, composition | Class/package/controller structure |
| Filter theo route | `HandlerFilterFunction`, before/after | `WebFilter`, interceptor/advice theo phạm vi |
| Hợp với | Routing composition, functional style, endpoint module | CRUD/controller truyền thống, annotation và argument resolver |

Cả hai đều dùng `Mono`/`Flux`, codec, backpressure, WebFilter và server runtime của WebFlux. Chọn một mô hình theo cách tổ chức code và yêu cầu dự án; không có quy tắc rằng functional endpoint luôn nhanh hơn hoặc luôn tốt hơn controller.

## 13. Lỗi phổ biến và cách phòng tránh

**Lỗi 1 — Nhầm `RouterFunction` với handler xử lý body.** Router chỉ quyết định route nào phù hợp và cung cấp handler; logic đọc body/ghi response nằm ở `HandlerFunction`.

**Lỗi 2 — Handler trả object trực tiếp thay vì Publisher.** `HandlerFunction` trả `Mono<ServerResponse>`. Dùng `ServerResponse.ok().bodyValue(value)` hoặc `body(publisher, type)`.

**Lỗi 3 — Quên build router.** Builder chỉ mô tả route; cần gọi `build()` để nhận `RouterFunction` hoàn chỉnh.

**Lỗi 4 — Route tổng quát đứng trước route cụ thể.** Router xét tuần tự; route tổng quát có thể bắt request trước. Đặt mapping cụ thể trước.

**Lỗi 5 — Nhầm `Accept` với `Content-Type`.** Accept mô tả định dạng client muốn nhận; Content-Type mô tả định dạng body request đang gửi. Dùng `accept(...)` cho điều kiện response và `contentType(...)` cho request body.

**Lỗi 6 — Đọc body hai lần.** Body thường là stream một lần. Decode một lần rồi ghép các thao tác vào cùng pipeline.

**Lỗi 7 — Gọi `subscribe()` trong handler.** Tạo subscription ngoài lifecycle response, dễ làm response trả trước khi nghiệp vụ hoàn tất. Trả Publisher cho framework.

**Lỗi 8 — Gọi `block()` để lấy dữ liệu.** Chặn thread non-blocking của WebFlux. Compose bằng `map`, `flatMap`, `then` và trả Publisher.

**Lỗi 9 — Dùng `bodyValue` cho Publisher và mong nó stream như `body`.** `bodyValue` nhận một giá trị đã có; `body(publisher, elementClass)` dành cho body reactive.

**Lỗi 10 — Quên xử lý body rỗng.** `bodyToMono` có thể complete rỗng. Dùng `switchIfEmpty` khi request body là bắt buộc.

**Lỗi 11 — Không phân biệt lỗi decode với lỗi nghiệp vụ.** JSON sai có thể lỗi trước khi handler nhận object. Validation nghiệp vụ xảy ra sau khi decode; có thể xử lý qua filter hoặc error pipeline phù hợp.

**Lỗi 12 — Dùng route filter thay cho security framework.** `HandlerFilterFunction` hữu ích cho logic theo router nhưng không thay thế authentication/authorization đầy đủ. Dùng Spring Security reactive.

**Lỗi 13 — Đặt filter sai cấp nested builder.** Filter trong nhóm route chỉ áp dụng cho phạm vi đó. Đặt filter toàn ứng dụng ở `WebFilter`.

**Lỗi 14 — Nghĩ `after` chứng minh client đã nhận response.** Nó quan sát `ServerResponse` ở tầng handler; byte vẫn phải qua writer, server, network và client.

**Lỗi 15 — Trả lỗi nội bộ trực tiếp cho client.** Không lộ stack trace, SQL hoặc token. Dùng error code ổn định và log an toàn ở server.

**Lỗi 16 — Khai báo route trùng với annotated controller.** Mapping có thể cạnh tranh và gây kết quả khó dự đoán. Tránh overlap hoặc cấu hình order có chủ đích.

**Lỗi 17 — Tạo nhiều router bean có path overlap mà không kiểm tra order.** Spring kết hợp router theo thứ tự; quản lý order và composition rõ ràng.

**Lỗi 18 — Dùng functional endpoint nhưng tự dựng HTTP server không cần thiết.** Trong Boot, router bean đã được tích hợp vào DispatcherHandler. Chỉ dùng `RouterFunctions.toHttpHandler` khi thật sự tự quản lý server adapter.

## 14. Bài tập tự kiểm tra

1. `RouterFunction` nhận gì và trả gì về mặt khái niệm? **Nhận `ServerRequest`, trả `Mono<HandlerFunction>`; rỗng nếu không match.**
2. `HandlerFunction` nhận kiểu nào và trả kiểu nào? **Nhận `ServerRequest`, trả `Mono<ServerResponse>`.**
3. Hai interface `ServerRequest` và `ServerResponse` có thể mutate trực tiếp không? **Không; hợp đồng bất biến, dùng builder để tạo instance mới.**
4. Khi nào dùng `accept(APPLICATION_JSON)`? **Khi route yêu cầu client chấp nhận response JSON.**
5. Khi nào dùng `contentType(APPLICATION_JSON)`? **Khi route yêu cầu request body gửi lên có Content-Type JSON.**
6. Nếu hai route có thể cùng match, route nào được thử trước? **Route được khai báo/ghép trước trong thứ tự router.**
7. `request.bodyToMono(Product.class)` có đọc body ngay khi gọi method không? **Nó tạo Publisher; body được tiêu thụ khi subscription đi tới Publisher đó.**
8. `ServerResponse.ok().bodyValue(product)` khác `body(flux, Product.class)` thế nào? **Một bên ghi object đơn; bên kia ghi body từ Publisher.**
9. `before` và `after` làm việc ở đâu? **Trước handler để biến đổi request và sau handler để quan sát/biến đổi response trong router.**
10. `HandlerFilterFunction` có thể chặn request mà không gọi handler kế tiếp không? **Có; nó có thể trả response trực tiếp.**
11. Filter route có tự áp dụng cho annotated controller không? **Không; nó gắn với RouterFunction cụ thể. Dùng WebFilter cho toàn pipeline.**
12. Functional endpoint có thể dùng chung với annotated controller không? **Có, cả hai chạy trong cùng DispatcherHandler infrastructure.**
13. Không có RouterFunction nào match thì sao? **Không có handler cho request; thông thường kết quả là 404.**
14. Vì sao không tự subscribe trong handler? **Để framework quản lý lỗi, cancellation và response lifecycle trong cùng subscription.**
15. Cách kiểm thử functional router phổ biến là gì? **`WebTestClient.bindToRouterFunction` cho router độc lập hoặc `@SpringBootTest`/`WebTestClient` cho tích hợp.**
16. Có nên dùng `HandlerFilterFunction` làm toàn bộ cơ chế phân quyền production? **Không; dùng Spring Security reactive và chỉ dùng route filter cho phần cross-cutting phù hợp.**

## 15. Ghi nhớ và tài liệu tham khảo

- **`RouterFunction`** định tuyến `ServerRequest` tới `HandlerFunction`; route không khớp trả Publisher rỗng.
- **`HandlerFunction`** xử lý request và trả `Mono<ServerResponse>`.
- **`ServerRequest`** và **`ServerResponse`** là các hợp đồng bất biến, hỗ trợ body reactive và backpressure.
- Dùng `RouterFunctions.route()`, predicate, `path` và `nest` để tạo route rõ ràng.
- Dùng `bodyToMono`/`bodyToFlux` để đọc request và `bodyValue`/`body` để ghi response.
- `before`, `after` và `HandlerFilterFunction` áp dụng logic trong phạm vi router; `WebFilter` bao phủ toàn pipeline.
- Trong Spring Boot, RouterFunction bean được tích hợp qua `RouterFunctionMapping`, `HandlerFunctionAdapter` và `ServerResponseResultHandler`.
- Framework quản lý subscription; không tự subscribe/block trong handler.

Tài liệu chính thức:

1. [Spring Framework Reference — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): mô hình tổng thể, HandlerFunction, ServerRequest, ServerResponse, RouterFunction, predicates, nested routes, filter và cách chạy server.
2. [Spring Framework Reference — Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): nền tảng reactive, backpressure và cách WebFlux xử lý Publisher.
3. [Spring Framework Javadoc — RouterFunction](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/RouterFunction.html): hợp đồng route và composition.
4. [Spring Framework Javadoc — HandlerFunction](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/HandlerFunction.html): hợp đồng xử lý ServerRequest.
5. [Spring Framework Javadoc — ServerRequest](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html) và [ServerResponse](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): API đọc request, body và xây response.
6. [Spring Framework Javadoc — HandlerFilterFunction](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/HandlerFilterFunction.html): filter trong functional handler chain.
7. [Spring Boot Reference — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): cách Spring Boot tự cấu hình WebFlux và functional endpoint.
