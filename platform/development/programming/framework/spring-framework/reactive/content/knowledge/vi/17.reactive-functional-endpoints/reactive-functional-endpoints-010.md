# Tách logic nghiệp vụ khỏi định tuyến và chuyển đổi HTTP trong Spring WebFlux

## 1. Mục tiêu: giữ ranh giới rõ giữa HTTP và nghiệp vụ

Một endpoint nhận HTTP request, xác định thao tác cần chạy, đọc dữ liệu đầu vào, gọi nghiệp vụ và tạo HTTP response. Nếu tất cả các bước này nằm trong một hàm, code sẽ nhanh chóng gắn chặt quy tắc nghiệp vụ với URL, status code, JSON DTO và API của framework. Khi đổi cách định tuyến, thêm một giao diện khác hoặc kiểm thử use case mà không khởi động HTTP server, ta phải mang theo nhiều phụ thuộc không cần thiết.

Trong Spring WebFlux, mô hình functional endpoint (`WebFlux.fn`) giúp biểu diễn rõ ba trách nhiệm:

1. **Router**: nhận diện request theo path, HTTP method và predicate; chuyển request đến handler phù hợp.
2. **Handler**: làm việc ở biên HTTP. Handler đọc `ServerRequest`, giải mã body, chuyển HTTP DTO thành command, gọi application service, rồi chuyển kết quả thành `ServerResponse`.
3. **Application service / domain**: thực hiện use case và quy tắc nghiệp vụ. Lớp này không cần biết `ServerRequest`, `ServerResponse`, URL, HTTP status hay JSON.

Repository port và adapter lưu trữ có thể nằm phía sau service. Handler không nên tự truy vấn database hoặc tính toán nghiệp vụ; router không nên chứa logic của use case.

Bài học dùng ví dụ tạo và tra cứu đơn hàng. Cùng một use case có thể được gọi từ HTTP functional endpoint, message consumer, scheduler hoặc một use case khác mà không cần viết lại quy tắc tính giá và kiểm tra đơn hàng.

Sau bài này, bạn có thể:

- Phân biệt `RouterFunction`, `HandlerFunction`, `ServerRequest` và `ServerResponse`.
- Tổ chức router, handler, service, domain model và repository thành các lớp có trách nhiệm riêng.
- Chuyển đổi giữa HTTP DTO và command/result mà không làm rò kiểu HTTP vào nghiệp vụ.
- Đặt validation ở đúng tầng và ánh xạ lỗi nghiệp vụ thành HTTP response ở biên.
- Kiểm thử router/handler bằng `WebTestClient` và kiểm thử service bằng `StepVerifier`.
- Nhận biết các dấu hiệu cho thấy handler hoặc service đang ôm quá nhiều trách nhiệm.

## 2. Functional endpoint trong WebFlux.fn hoạt động ra sao?

Spring WebFlux hỗ trợ hai mô hình xây dựng HTTP endpoint:

- **Annotation-based**: `@RestController`, `@GetMapping`, `@PostMapping`, `@RequestBody`...
- **Functional endpoint (WebFlux.fn)**: `RouterFunction`, `HandlerFunction`, `ServerRequest`, `ServerResponse`.

Đây là hai cách khai báo HTTP endpoint trên cùng nền tảng reactive của WebFlux. Functional endpoint không phải một server khác và cũng không thay thế Reactor.

Trong WebFlux.fn:

- `RouterFunction<ServerResponse>` là hàm nhận `ServerRequest` và tìm một `HandlerFunction` phù hợp.
- `HandlerFunction<ServerResponse>` là hàm nhận `ServerRequest` và trả `Mono<ServerResponse>`.
- `ServerRequest` và `ServerResponse` là các abstraction HTTP có contract bất biến; body được biểu diễn bằng `Mono` hoặc `Flux`.
- `RequestPredicate` biểu diễn điều kiện định tuyến như path, method, `Accept`, `Content-Type` hoặc header.

Mô hình:

```text
HTTP request
     |
     v
RouterFunction
  path + method + predicates
     |
     v
HandlerFunction
  ServerRequest -> Mono<ServerResponse>
     |
     +--> decode HTTP body / read path and query values
     |
     +--> map HTTP DTO to application command
     |
     v
Application service / domain
  execute use case and business rules
     |
     v
Repository port -> persistence adapter
     |
     v
Domain result
     |
     v
Handler maps result to HTTP response
     |
     v
ServerResponse -> HTTP response
```

Router chỉ quyết định **request đi đâu**. Handler điều phối **chuyển đổi tại biên HTTP**. Service quyết định **nghiệp vụ phải làm gì**.

### Khai báo router ngắn

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/orders/{id}", handler::get)
                .POST("/orders", handler::create)
                .build();
```

`handler::get` và `handler::create` là method reference tới các handler có dạng `Mono<ServerResponse> method(ServerRequest request)`. Router không cần biết service tính tổng đơn hàng ra sao.

Các route được đánh giá theo thứ tự khai báo. Khi có route cụ thể và route tổng quát có thể cùng khớp, hãy đặt route cụ thể trước. Đây là điểm cần nhớ khi so sánh với annotation-based mapping, nơi Spring chọn mapping phù hợp nhất theo specificity.

## 3. Bốn lớp trách nhiệm và điều không nên đặt vào mỗi lớp

| Lớp | Trách nhiệm | Không nên làm |
|---|---|---|
| Router | Ghép path, method, request predicates và handler | Tính giá, kiểm tra tồn kho, truy vấn repository |
| HTTP handler | Đọc request, decode body, map DTO/command, gọi service, map result/status | Chứa quy tắc nghiệp vụ hoặc tự quản lý transaction |
| Application service / domain | Thực hiện use case, kiểm tra invariant và quy tắc nghiệp vụ | Nhận `ServerRequest`, trả `ServerResponse`, đọc header |
| Repository adapter | Lưu và truy xuất dữ liệu qua port | Quyết định HTTP status hoặc đọc query parameter |

Ví dụ cùng một quy tắc “số lượng mỗi mặt hàng phải từ 1 đến 100” có thể được áp dụng khi đơn hàng đến từ HTTP, message queue hoặc batch job. Nếu quy tắc nằm trong `OrderHandler`, các nguồn khác sẽ phải sao chép hoặc gọi nhầm code HTTP. Đặt nó trong service/domain giúp mọi đầu vào dùng cùng một quy tắc.

### Sự phụ thuộc nên đi theo hướng nào?

```text
Web adapter (Router + Handler)
             |
             v
      Application service
             |
             v
        Domain model
             ^
             |
     Repository port
             ^
             |
  Persistence adapter
```

Sơ đồ thể hiện ý tưởng phụ thuộc: HTTP adapter gọi use case; service phụ thuộc abstraction repository; adapter persistence thực thi abstraction đó. Trong ứng dụng nhỏ, có thể chưa cần tách mọi interface và module, nhưng vẫn nên giữ nguyên ranh giới trách nhiệm.

Không nhất thiết phải tạo một class cho mỗi method hoặc một interface cho mọi object. Tách lớp khi có lý do rõ ràng: nhiều adapter cần cùng use case, logic cần test độc lập, hoặc thay đổi persistence không nên ảnh hưởng nghiệp vụ.

## 4. Router: chỉ định tuyến và ghép request predicates

Router mô tả cách HTTP request được chuyển tới handler. Nó có thể khai báo method/path:

```java
@Bean
RouterFunction<ServerResponse> orderRoutes(OrderHandler handler) {
    return RouterFunctions.route()
            .POST("/api/orders", handler::create)
            .GET("/api/orders/{id}", handler::get)
            .build();
}
```

Có thể thêm predicate cho `Accept` hoặc điều kiện khác:

```java
@Bean
RouterFunction<ServerResponse> orderRoutes(OrderHandler handler) {
    return RouterFunctions.route()
            .POST(
                    "/api/orders",
                    RequestPredicates.accept(MediaType.APPLICATION_JSON),
                    handler::create)
            .GET(
                    "/api/orders/{id}",
                    RequestPredicates.accept(MediaType.APPLICATION_JSON),
                    handler::get)
            .build();
}
```

Predicate được ghép bằng `and` hoặc `or`:

```java
RequestPredicate jsonOrText =
        RequestPredicates.accept(MediaType.APPLICATION_JSON)
                .or(RequestPredicates.accept(MediaType.TEXT_PLAIN));
```

Dùng predicate cho điều kiện HTTP có ý nghĩa định tuyến. Nếu cần kiểm tra dữ liệu của đơn hàng, đó là nhiệm vụ của service/domain. Không nên đưa truy vấn database hoặc logic “khách hàng có đủ hạn mức không” vào lambda router.

### Nested route cho prefix chung

Khi nhiều route có cùng prefix, có thể nhóm chúng:

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/api/orders", builder -> builder
                        .GET("/{id}", handler::get)
                        .POST(handler::create))
                .build();
```

Nested route hữu ích khi có path hoặc predicate chung. Hãy tránh lồng quá nhiều tầng khiến luồng định tuyến khó đọc; một nhóm route theo resource thường là đủ.

### Thứ tự route

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/api/orders/search", handler::search)
                .GET("/api/orders/{id}", handler::get)
                .GET("/api/{resource}/{id}", handler::genericGet)
                .build();
```

Route cụ thể nên được khai báo trước route tổng quát. Router function được đánh giá tuần tự; route đầu tiên phù hợp có thể xử lý request và ngăn route sau được xét.

### Router không phải nơi xử lý authentication

Có thể dùng `HandlerFilterFunction` để áp dụng hành vi chung ở biên route, nhưng xác thực và phân quyền production nên dựa trên Spring Security/WebFlux Security và security context. Predicate kiểm tra một header hiện diện không chứng minh người gửi đã được xác thực.

## 5. Handler: adapter giữa HTTP và application service

Handler là nơi HTTP đi vào và rời khỏi ứng dụng. Một handler điển hình thực hiện:

1. Đọc path variable, query parameter, header hoặc body từ `ServerRequest`.
2. Dùng codec để decode body thành request DTO.
3. Chuyển DTO thành command/query của application layer.
4. Gọi application service và trả về publisher.
5. Chuyển domain result thành response DTO.
6. Chọn HTTP status/header/body và ánh xạ lỗi phù hợp với API contract.

Handler không nên tự `.subscribe()` hoặc `.block()`. Nó trả `Mono<ServerResponse>` để WebFlux quản lý subscription và backpressure.

Ví dụ handler đọc body:

```java
@Component
public class OrderHandler {

    private final OrderService orderService;

    public OrderHandler(OrderService orderService) {
        this.orderService = orderService;
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateOrderRequest.class)
                .map(this::toCommand)
                .flatMap(orderService::create)
                .flatMap(this::createdResponse);
    }
}
```

Đây là cấu trúc rút gọn; các hàm `toCommand` và `createdResponse` sẽ được định nghĩa bên dưới. `bodyToMono` là ranh giới HTTP decode; `orderService.create` là lời gọi use case.

### Đọc path/query/header

```java
public Mono<ServerResponse> get(ServerRequest request) {
    String id = request.pathVariable("id");

    return orderService.findById(id)
            .flatMap(this::okResponse)
            .switchIfEmpty(ServerResponse.notFound().build());
}
```

Handler lấy `id` từ path rồi chuyển vào service. Nếu `id` có định dạng domain phức tạp, có thể chuyển sang value object ở adapter hoặc service theo quy ước của ứng dụng. Không để domain phải biết `ServerRequest.pathVariable`.

### Chuyển DTO thành command

HTTP request DTO phản ánh contract của API:

```java
public record CreateOrderRequest(
        String customerId,
        List<Item> items) {

    public record Item(String sku, int quantity) {
    }
}
```

Command phản ánh nhu cầu của use case:

```java
public record CreateOrderCommand(
        String customerId,
        List<Item> items) {

    public record Item(String sku, int quantity) {
    }
}
```

Handler chuyển đổi:

```java
private CreateOrderCommand toCommand(CreateOrderRequest request) {
    List<CreateOrderCommand.Item> items =
            request.items() == null
                    ? null
                    : request.items().stream()
                            .map(item -> item == null
                                    ? null
                                    : new CreateOrderCommand.Item(
                                            item.sku(), item.quantity()))
                            .toList();

    return new CreateOrderCommand(request.customerId(), items);
}
```

Đây là mapping ở biên. Nếu API sau này đổi `customerId` thành một cấu trúc khác, application service vẫn có thể giữ command ổn định. Không nhất thiết phải tạo DTO và command riêng khi hai contract thực sự giống nhau và không có lý do tách; nhưng đừng để `ServerRequest` hoặc HTTP response object lọt vào service.

## 6. Application service và domain: giữ nghiệp vụ độc lập HTTP

Service nhận dữ liệu có ý nghĩa với use case, thực hiện quy tắc và trả kết quả. Service không cần biết request đến từ `POST /api/orders` hay từ một message consumer.

Ví dụ:

```java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Mono<Order> create(CreateOrderCommand command) {
        return Mono.defer(() -> {
            validate(command);

            Order order = buildOrder(command);
            return repository.save(order);
        });
    }

    public Mono<Order> findById(String id) {
        return repository.findById(id);
    }

    private void validate(CreateOrderCommand command) {
        // Business rules belong here.
    }

    private Order buildOrder(CreateOrderCommand command) {
        // Build domain result; no HTTP status or ServerRequest.
        throw new UnsupportedOperationException("Illustrative only");
    }
}
```

Đây là sơ đồ minh họa trách nhiệm, không phải class hoàn chỉnh có thể chạy vì phần `buildOrder` được để rút gọn. Chương trình đầy đủ ở mục 12 cung cấp implementation chạy được.

Điểm cần chú ý:

- `Mono.defer` trì hoãn việc validate/build order tới lúc subscribe, phù hợp khi muốn lỗi được phát thành reactive error.
- Service có thể trả `Mono<Order>` vì persistence reactive, nhưng không nên trả `Mono<ServerResponse>`.
- Domain exception biểu đạt vấn đề nghiệp vụ như `InvalidOrderException`; handler quyết định ánh xạ nó thành HTTP 422, 409 hoặc status khác theo API contract.
- Service không nên nhận `HttpStatus`, `ServerRequest`, `ResponseEntity` hoặc `ProblemDetail`.

### Vì sao service có thể phụ thuộc Reactor nhưng không phụ thuộc HTTP?

Một application service reactive thường trả `Mono<T>`/`Flux<T>` vì thao tác persistence hoặc downstream là non-blocking. Reactor mô tả cách kết quả được thực thi và phát ra; nó không phải HTTP protocol. Service có thể được gọi từ nhiều adapter reactive khác nhau.

Nếu muốn domain model thuần Java không phụ thuộc Reactor, có thể giữ domain method đồng bộ và đặt composition reactive trong application service. Chọn cách phù hợp với kiến trúc; điều quan trọng là không để domain rule phụ thuộc HTTP.

## 7. Repository port và adapter persistence

Service nên làm việc với abstraction mô tả nhu cầu lưu trữ:

```java
public interface OrderRepository {
    Mono<Order> save(Order order);
    Mono<Order> findById(String id);
}
```

Một adapter trong bộ nhớ:

```java
@Repository
public class InMemoryOrderRepository implements OrderRepository {

    private final Map<String, Order> orders = new ConcurrentHashMap<>();

    @Override
    public Mono<Order> save(Order order) {
        return Mono.fromSupplier(() -> {
            orders.put(order.id(), order);
            return order;
        });
    }

    @Override
    public Mono<Order> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(orders.get(id)));
    }
}
```

Trong ứng dụng thật, adapter có thể dùng R2DBC, MongoDB reactive hoặc WebClient tới service khác. Service vẫn gọi `OrderRepository`; không cần biết đó là `ConcurrentHashMap`, SQL hay remote API.

### Vì sao handler không gọi repository trực tiếp?

Nếu handler gọi repository và tự tính giá, kiểm tra khách hàng, lưu order, nó trở thành application service trá hình. Khi một message consumer cần tạo đơn hàng, logic đó phải bị sao chép. Handler chỉ nên chuyển HTTP request thành command rồi gọi use case.

Repository cũng không nên trả `ServerResponse.notFound()`. Không tìm thấy một order là kết quả của truy vấn/domain; việc nó trở thành HTTP 404 là quyết định của adapter HTTP.

## 8. Chuyển domain result thành HTTP response

Handler biến kết quả application thành response DTO và status phù hợp:

```java
private Mono<ServerResponse> createdResponse(Order order) {
    OrderResponse response = OrderResponse.from(order);

    return ServerResponse.created(
                    URI.create("/api/orders/" + order.id()))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(response);
}

private Mono<ServerResponse> okResponse(Order order) {
    return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(OrderResponse.from(order));
}
```

`OrderResponse` là DTO dành cho API. Không bắt buộc trả thẳng domain entity; response DTO giúp kiểm soát field nào được công khai, định dạng dữ liệu và versioning.

Trong ứng dụng thực, khi tạo `Location`, nên dùng URI builder có xử lý base path/host theo cấu hình triển khai thay vì ghép URL tùy tiện. Ví dụ đầy đủ bên dưới dùng `ServerRequest.uriBuilder()` để giữ URI request hiện tại.

### Domain result không nên mang HTTP status

Không nên viết service kiểu:

```java
public Mono<ResponseEntity<Order>> create(...) {
    // Business use case returns HTTP response object.
}
```

Cách này buộc application layer biết Spring MVC/WebFlux HTTP API. Thay vào đó service trả `Mono<Order>`; handler quyết định `201 Created`, `200 OK`, `404 Not Found` hoặc lỗi.

## 9. Ánh xạ lỗi: giữ nguyên nguyên nhân, đổi biểu diễn ở biên

Nên phân biệt ba nhóm:

- **Input/transport error**: body JSON sai, body thiếu, media type không hỗ trợ hoặc path/query không hợp lệ. Framework/HTTP adapter thường xử lý nhóm này.
- **Domain/application error**: số lượng không hợp lệ, SKU không tồn tại, trạng thái nghiệp vụ không cho phép. Service phát domain exception hoặc kết quả lỗi có kiểu.
- **Unexpected infrastructure error**: database/network failure hoặc bug. Không nên biến tất cả thành 400/422.

Ví dụ service phát `InvalidOrderException` khi quy tắc đơn hàng bị vi phạm. Handler ánh xạ nó thành `422 Unprocessable Content` theo contract được chọn:

```java
private Mono<ServerResponse> invalidOrder(InvalidOrderException error) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.UNPROCESSABLE_ENTITY,
            error.getMessage());

    problem.setTitle("Invalid order");

    return ServerResponse.status(HttpStatus.UNPROCESSABLE_ENTITY)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .bodyValue(problem);
}
```

Có thể xử lý lỗi trong handler:

```java
return orderService.create(command)
        .flatMap(this::createdResponse)
        .onErrorResume(
                InvalidOrderException.class,
                this::invalidOrder);
```

Hoặc đặt xử lý chung ở filter/router boundary nếu nhiều route dùng cùng một chính sách. Dù chọn cách nào, application service vẫn chỉ phát lỗi domain; nó không tự chọn HTTP status.

### 400, 404, 409, 422 và 500

| Tình huống | Status có thể phù hợp | Nơi quyết định |
|---|---:|---|
| JSON sai cú pháp hoặc không decode được | 400 | HTTP adapter/framework |
| Resource không tồn tại | 404 | HTTP handler ánh xạ kết quả empty/not-found |
| Vi phạm trạng thái/xung đột với dữ liệu hiện có | 409 | HTTP handler theo domain error |
| Nội dung hiểu được nhưng không đáp ứng quy tắc nghiệp vụ | 422 | HTTP handler theo API contract |
| Lỗi không mong đợi | 500 | Error handling chung |

Không có quy tắc rằng mọi domain error đều phải là 422. Ví dụ SKU không tồn tại có thể là 422 nếu đó là dữ liệu tham chiếu không hợp lệ, hoặc 404 nếu SKU được xem là resource cần tìm. Chọn semantics nhất quán cho API.

## 10. Functional filters: xử lý cross-cutting concern đúng tầng

Router builder hỗ trợ `before`, `after` và `filter` để áp dụng hành vi chung cho các route:

- `before`: biến đổi/quan sát request trước handler.
- `after`: quan sát hoặc biến đổi response sau handler.
- `filter`: bọc handler tiếp theo bằng `HandlerFilterFunction`.

Ví dụ ghi nhận method/path ở biên:

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/health", request ->
                        ServerResponse.ok().bodyValue("ok"))
                .filter((request, next) -> {
                    log.info("method={} path={}",
                            request.method(), request.path());
                    return next.handle(request);
                })
                .build();
```

Đây là snippet cần logger và import tương ứng. Filter phù hợp với logging, correlation metadata hoặc một chính sách chung đơn giản. Đừng đặt quy tắc tính giá hay quyết định trạng thái đơn hàng vào filter.

### Filter không thay thế service

Một filter có thể từ chối request chưa được phép hoặc kiểm tra điều kiện cross-cutting. Nhưng authorization phụ thuộc user/resource nên tích hợp với Spring Security và use case policy phù hợp. Không chỉ kiểm tra `X-User-Id` do client tự gửi rồi tin đó là identity đã xác thực.

Filter ở functional route builder chỉ áp dụng cho các route thuộc builder tương ứng; với nested route, phạm vi filter phụ thuộc nơi filter được gắn. Khi chia nhiều router bean, hãy xác định rõ filter nào bao phủ route nào.

## 11. Kiểm thử theo ranh giới: route, handler và use case

Tách trách nhiệm giúp kiểm thử mỗi lớp với chi phí phù hợp.

### 11.1. Kiểm thử service/domain

Service test không cần HTTP server, JSON, route hay `WebTestClient`. Có thể tạo repository in-memory hoặc fake:

```java
StepVerifier.create(
        orderService.create(command))
        .assertNext(order -> {
            assertEquals("customer-1", order.customerId());
            assertEquals(new BigDecimal("26.20"), order.total());
        })
        .verifyComplete();
```

Test tập trung vào invariant và kết quả use case: số lượng, SKU, tính tổng, trạng thái, lưu dữ liệu. Đây là nơi xác nhận logic nghiệp vụ độc lập HTTP.

### 11.2. Kiểm thử functional route bằng `WebTestClient`

Có thể khởi động ứng dụng trên random port, gửi HTTP request thật tới route và kiểm tra:

- Path/method có tới đúng handler không?
- JSON có decode được không?
- Handler trả đúng status, header và response DTO không?
- Domain error được chuyển thành HTTP problem response như contract không?

`WebTestClient` cũng có thể bind trực tiếp vào `RouterFunction` trong test cô lập, nhưng khi test Spring Boot đầy đủ, dùng `@SpringBootTest` và random port giúp xác nhận cả cấu hình route và adapter.

### 11.3. Test handler có cần mock service?

Có thể mock application service để kiểm tra mapping HTTP DTO → command và result → response. Tuy nhiên, không cần kiểm thử mọi method handler bằng nhiều test trùng lặp nếu integration route đã xác nhận hợp đồng HTTP. Giữ test ở đúng tầng để tránh test implementation detail.

### Phạm vi test đề xuất

| Tầng | Kiểm thử | Không cần phụ thuộc |
|---|---|---|
| Domain/service | Quy tắc, kết quả, lỗi use case, reactive composition | HTTP server, URL, `ServerResponse` |
| Repository adapter | Truy vấn/lưu trữ, mapping persistence, lỗi database | Router và HTTP DTO |
| Handler | DTO mapping, status/header/body, error translation | Quy tắc domain phức tạp |
| Router | Path/method/predicate, route order, handler được gọi | Database thật |
| End-to-end | Hợp đồng HTTP quan trọng, serialization và wiring | Không nên bao phủ mọi nhánh logic nhỏ |

## 12. Dự án Java 17+ chạy được: tạo và tra cứu đơn hàng

Ví dụ sau là một ứng dụng Spring Boot WebFlux nhỏ, dùng functional endpoint. Business rules nằm trong `OrderService`; Router chỉ định tuyến; `OrderHandler` chuyển đổi HTTP; repository in-memory lưu dữ liệu để chương trình có thể chạy mà không cần database.

### 12.1. Cấu trúc dự án

```text
webflux-order-boundaries/
├── pom.xml
└── src/
    ├── main/java/edu/demo/orders/
    │   ├── OrderApplication.java
    │   ├── OrderRoutes.java
    │   ├── OrderHandler.java
    │   ├── OrderService.java
    │   ├── OrderRepository.java
    │   ├── InMemoryOrderRepository.java
    │   ├── Order.java
    │   ├── CreateOrderCommand.java
    │   ├── CreateOrderRequest.java
    │   ├── OrderResponse.java
    │   └── InvalidOrderException.java
    └── test/java/edu/demo/orders/
        ├── OrderServiceTest.java
        └── OrderRoutesTest.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webflux-order-boundaries</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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
```

### 12.3. `OrderApplication.java`

```java
package edu.demo.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

### 12.4. `Order.java`

```java
package edu.demo.orders;

import java.math.BigDecimal;
import java.util.List;

public record Order(
        String id,
        String customerId,
        List<Line> items,
        BigDecimal total) {

    public Order {
        items = List.copyOf(items);
    }

    public record Line(
            String sku,
            int quantity,
            BigDecimal unitPrice) {
    }
}
```

Domain object giữ dữ liệu đơn hàng và các dòng hàng. Nó không biết request JSON, HTTP status hay `ServerResponse`.

### 12.5. `CreateOrderCommand.java`

```java
package edu.demo.orders;

import java.util.List;

public record CreateOrderCommand(
        String customerId,
        List<Item> items) {

    public record Item(String sku, int quantity) {
    }
}
```

Command là input của use case. Nó mô tả điều application cần để tạo đơn hàng, không chứa header, URL hoặc body HTTP.

### 12.6. `CreateOrderRequest.java`

```java
package edu.demo.orders;

import java.util.List;

public record CreateOrderRequest(
        String customerId,
        List<Item> items) {

    public record Item(String sku, int quantity) {
    }
}
```

Request DTO phản ánh JSON API. Có thể thay đổi contract này mà không cần thay đổi command/domain nếu handler giữ mapping phù hợp.

### 12.7. `OrderResponse.java`

```java
package edu.demo.orders;

import java.math.BigDecimal;
import java.util.List;

public record OrderResponse(
        String id,
        String customerId,
        List<Item> items,
        BigDecimal total) {

    public record Item(
            String sku,
            int quantity,
            BigDecimal unitPrice) {
    }

    public static OrderResponse from(Order order) {
        List<Item> items = order.items().stream()
                .map(line -> new Item(
                        line.sku(),
                        line.quantity(),
                        line.unitPrice()))
                .toList();

        return new OrderResponse(
                order.id(),
                order.customerId(),
                items,
                order.total());
    }
}
```

Response DTO xác định dữ liệu được công khai qua API. Nếu sau này domain có thêm dữ liệu nội bộ, nó không tự động xuất hiện trong response.

### 12.8. `InvalidOrderException.java`

```java
package edu.demo.orders;

public class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Exception biểu đạt lỗi nghiệp vụ. Nó không chứa HTTP status; adapter HTTP quyết định biểu diễn lỗi này cho client.

### 12.9. `OrderRepository.java`

```java
package edu.demo.orders;

import reactor.core.publisher.Mono;

public interface OrderRepository {

    Mono<Order> save(Order order);

    Mono<Order> findById(String id);
}
```

Đây là repository port mà application service sử dụng. Trong ví dụ, API reactive cho phép service composition mà không phải block.

### 12.10. `InMemoryOrderRepository.java`

```java
package edu.demo.orders;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class InMemoryOrderRepository implements OrderRepository {

    private final Map<String, Order> orders =
            new ConcurrentHashMap<>();

    @Override
    public Mono<Order> save(Order order) {
        return Mono.fromSupplier(() -> {
            orders.put(order.id(), order);
            return order;
        });
    }

    @Override
    public Mono<Order> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(orders.get(id)));
    }
}
```

Adapter này chỉ dùng bộ nhớ của một process để minh họa. Khi ứng dụng restart, dữ liệu mất; production cần adapter database phù hợp.

### 12.11. `OrderService.java`

```java
package edu.demo.orders;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderService {

    private static final Map<String, BigDecimal> CATALOG = Map.of(
            "BOOK", new BigDecimal("12.50"),
            "PEN", new BigDecimal("1.20")
    );

    private final OrderRepository repository;
    private final AtomicLong ids = new AtomicLong();

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Mono<Order> create(CreateOrderCommand command) {
        return Mono.defer(() -> {
            if (command == null
                    || command.customerId() == null
                    || command.customerId().isBlank()) {
                return Mono.error(
                        new InvalidOrderException("Customer is required"));
            }

            if (command.items() == null || command.items().isEmpty()) {
                return Mono.error(
                        new InvalidOrderException("At least one item is required"));
            }

            List<Order.Line> lines = new ArrayList<>();
            BigDecimal total = BigDecimal.ZERO;

            for (CreateOrderCommand.Item item : command.items()) {
                if (item == null
                        || item.sku() == null
                        || item.sku().isBlank()) {
                    return Mono.error(
                            new InvalidOrderException("SKU is required"));
                }

                if (item.quantity() < 1 || item.quantity() > 100) {
                    return Mono.error(
                            new InvalidOrderException(
                                    "Quantity must be between 1 and 100"));
                }

                String sku = item.sku()
                        .trim()
                        .toUpperCase(Locale.ROOT);

                BigDecimal price = CATALOG.get(sku);
                if (price == null) {
                    return Mono.error(
                            new InvalidOrderException("Unknown SKU: " + sku));
                }

                lines.add(new Order.Line(sku, item.quantity(), price));
                total = total.add(
                        price.multiply(BigDecimal.valueOf(item.quantity())));
            }

            Order order = new Order(
                    Long.toString(ids.incrementAndGet()),
                    command.customerId().trim(),
                    lines,
                    total);

            return repository.save(order);
        });
    }

    public Mono<Order> findById(String id) {
        return repository.findById(id);
    }
}
```

Toàn bộ quy tắc customer, số lượng, SKU và tính tổng nằm trong service. Không có `ServerRequest`, `ServerResponse`, `HttpStatus` hay JSON mapping trong class này.

`Mono.defer` đảm bảo việc kiểm tra và tạo order diễn ra trong subscription. Khi rule thất bại, service trả reactive error; handler sẽ ánh xạ nó thành HTTP response.

### 12.12. `OrderHandler.java`

```java
package edu.demo.orders;

import java.net.URI;
import java.util.ArrayList;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.server.ServerWebInputException;

import reactor.core.publisher.Mono;

@Component
public class OrderHandler {

    private final OrderService orderService;

    public OrderHandler(OrderService orderService) {
        this.orderService = orderService;
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateOrderRequest.class)
                .switchIfEmpty(Mono.error(
                        new ServerWebInputException("Request body is required")))
                .map(this::toCommand)
                .flatMap(orderService::create)
                .flatMap(order -> {
                    URI location = request.uriBuilder()
                            .path("/{id}")
                            .build(order.id());

                    return ServerResponse.created(location)
                            .contentType(MediaType.APPLICATION_JSON)
                            .bodyValue(OrderResponse.from(order));
                })
                .onErrorResume(
                        InvalidOrderException.class,
                        error -> problem(
                                HttpStatus.UNPROCESSABLE_ENTITY,
                                "Invalid order",
                                error.getMessage()))
                .onErrorResume(
                        ServerWebInputException.class,
                        error -> problem(
                                HttpStatus.BAD_REQUEST,
                                "Invalid request",
                                "Request body could not be read."));
    }

    public Mono<ServerResponse> get(ServerRequest request) {
        String id = request.pathVariable("id");

        return orderService.findById(id)
                .flatMap(order -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(OrderResponse.from(order)))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    private CreateOrderCommand toCommand(CreateOrderRequest request) {
        List<CreateOrderCommand.Item> items = null;

        if (request.items() != null) {
            items = new ArrayList<>();

            for (CreateOrderRequest.Item item : request.items()) {
                items.add(item == null
                        ? null
                        : new CreateOrderCommand.Item(
                                item.sku(), item.quantity()));
            }
        }

        return new CreateOrderCommand(request.customerId(), items);
    }

    private Mono<ServerResponse> problem(
            HttpStatus status,
            String title,
            String detail) {

        ProblemDetail body =
                ProblemDetail.forStatusAndDetail(status, detail);
        body.setTitle(title);

        return ServerResponse.status(status)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .bodyValue(body);
    }
}
```

Handler chuyển đổi HTTP request DTO thành command, gọi service và map domain result thành response. Domain exception được chuyển thành `422`; lỗi đọc body được chuyển thành `400`. Đây là chính sách của ví dụ, ứng dụng có thể chọn status khác theo API contract.

`get` trả 404 khi repository không có order. Service chỉ trả `Mono.empty()`; nó không cần biết khái niệm HTTP 404.

### 12.13. `OrderRoutes.java`

```java
package edu.demo.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class OrderRoutes {

    @Bean
    RouterFunction<ServerResponse> orderRoutes(OrderHandler handler) {
        return RouterFunctions.route()
                .POST(
                        "/api/orders",
                        RequestPredicates.accept(MediaType.APPLICATION_JSON),
                        handler::create)
                .GET(
                        "/api/orders/{id}",
                        RequestPredicates.accept(MediaType.APPLICATION_JSON),
                        handler::get)
                .build();
    }
}
```

Router chỉ nối HTTP method/path/Accept predicate với handler. Không có logic tạo order, tính giá hoặc truy vấn persistence.

### 12.14. `OrderServiceTest.java`

```java
package edu.demo.orders;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderServiceTest {

    private final OrderService service =
            new OrderService(new InMemoryOrderRepository());

    @Test
    void createsOrderAndCalculatesTotal() {
        CreateOrderCommand command = new CreateOrderCommand(
                "customer-1",
                List.of(
                        new CreateOrderCommand.Item("BOOK", 2),
                        new CreateOrderCommand.Item("PEN", 1)));

        StepVerifier.create(service.create(command))
                .assertNext(order -> {
                    assertEquals("customer-1", order.customerId());
                    assertEquals(
                            new BigDecimal("26.20"),
                            order.total());
                    assertEquals(2, order.items().size());
                })
                .verifyComplete();
    }

    @Test
    void rejectsInvalidQuantity() {
        CreateOrderCommand command = new CreateOrderCommand(
                "customer-1",
                List.of(new CreateOrderCommand.Item("BOOK", 0)));

        StepVerifier.create(service.create(command))
                .expectError(InvalidOrderException.class)
                .verify();
    }
}
```

Đây là test application service độc lập HTTP. Nó kiểm tra business rule và tổng tiền mà không khởi động WebFlux server hoặc tạo `ServerRequest`.

### 12.15. `OrderRoutesTest.java`

```java
package edu.demo.orders;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderRoutesTest {

    @Autowired
    WebTestClient client;

    @Test
    void createsAndThenFindsOrder() {
        CreateOrderRequest request = new CreateOrderRequest(
                "customer-1",
                List.of(new CreateOrderRequest.Item("BOOK", 2)));

        OrderResponse created = client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(request)
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectBody(OrderResponse.class)
                .returnResult()
                .getResponseBody();

        assertNotNull(created);

        client.get()
                .uri("/api/orders/{id}", created.id())
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.customerId").isEqualTo("customer-1")
                .jsonPath("$.total").isEqualTo(25.00);
    }

    @Test
    void invalidBusinessRuleBecomes422() {
        CreateOrderRequest request = new CreateOrderRequest(
                "customer-1",
                List.of(new CreateOrderRequest.Item("BOOK", 0)));

        client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(request)
                .exchange()
                .expectStatus().isEqualTo(422)
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.title").isEqualTo("Invalid order");
    }

    @Test
    void malformedJsonBecomes400() {
        client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue("{")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void missingOrderBecomes404() {
        client.get()
                .uri("/api/orders/does-not-exist")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isNotFound();
    }
}
```

Test tích hợp kiểm tra route, HTTP decode, response status, header và body. Test service riêng xác nhận nghiệp vụ. Cách chia này giúp khi test service thất bại, ta biết lỗi thuộc use case; khi test route thất bại, ta điều tra HTTP mapping hoặc adapter.

### 12.16. Chạy ứng dụng và test

Từ thư mục dự án:

```bash
mvn test
```

Khởi động server:

```bash
mvn spring-boot:run
```

Tạo đơn hàng:

```bash
curl -i -X POST "http://localhost:8080/api/orders" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"customerId":"customer-1","items":[{"sku":"BOOK","quantity":2},{"sku":"PEN","quantity":1}]}'
```

Response thành công có status `201 Created`, header `Location` và JSON tương tự:

```json
{
  "id": "1",
  "customerId": "customer-1",
  "items": [
    {"sku":"BOOK","quantity":2,"unitPrice":12.50},
    {"sku":"PEN","quantity":1,"unitPrice":1.20}
  ],
  "total": 26.20
}
```

ID là số tăng theo instance trong bộ nhớ; nó có thể khác nếu ứng dụng đã tạo order trước đó.

Tra cứu order:

```bash
curl -i \
  -H "Accept: application/json" \
  "http://localhost:8080/api/orders/1"
```

Khi chưa có order tương ứng, endpoint trả `404 Not Found`.

Gửi số lượng bằng 0 sẽ đi qua route và decode thành công, nhưng service từ chối theo business rule; handler ánh xạ thành `422 Unprocessable Content` với `application/problem+json`.

Chương trình minh họa đầy đủ cấu trúc và lệnh chạy. Các lệnh Maven ở đây là hướng dẫn để người học thực thi; không khẳng định bộ test đã được chạy trong môi trường biên soạn tài liệu.

## 13. Vì sao cách tách này dễ thay đổi hơn?

### Đổi đường dẫn mà không đổi nghiệp vụ

Nếu API chuyển từ `/api/orders` sang `/v2/orders`, chỉ cần thay router hoặc thêm route mới trỏ tới handler. `OrderService.create` và các quy tắc tính giá không đổi.

### Thêm một adapter khác

Giả sử có message consumer nhận sự kiện tạo order. Consumer có thể chuyển message thành `CreateOrderCommand` rồi gọi `OrderService.create`. Không cần tạo `ServerRequest`, không cần giả lập HTTP status.

### Đổi JSON contract

Nếu API đổi `customerId` từ chuỗi sang object chứa `id`, chỉ handler mapping `CreateOrderRequest` thành `CreateOrderCommand` cần cập nhật. Domain/service tiếp tục nhận command ổn định.

### Đổi database

Thay `InMemoryOrderRepository` bằng R2DBC adapter thực thi `OrderRepository`. Service không cần biết SQL, row mapping hoặc connection pool.

### Test nghiệp vụ nhanh hơn

Service test không phải khởi động server hoặc dựng request JSON. Test chỉ truyền command và xác nhận kết quả. Điều này làm test ít phụ thuộc vào framework và tập trung vào hành vi nghiệp vụ.

## 14. Những dấu hiệu cho thấy ranh giới đang bị phá vỡ

| Dấu hiệu | Vấn đề | Hướng sửa |
|---|---|---|
| Router gọi repository hoặc tính giá | Định tuyến đang chứa use case | Chuyển lời gọi qua handler và service |
| Handler có hàng trăm dòng rule nghiệp vụ | HTTP adapter ôm domain | Tách use case/domain service |
| Service trả `ServerResponse` hoặc `ProblemDetail` | Application layer phụ thuộc HTTP | Trả domain result/exception |
| Domain object chứa `ServerRequest` hoặc header | Domain biết transport | Chuyển dữ liệu cần thiết thành command/value object |
| Service tự chọn HTTP 404/422 | Lỗi nghiệp vụ bị gắn status | Phát kết quả/exception; adapter ánh xạ |
| Handler tự `subscribe()` | Tách pipeline khỏi lifecycle của request | Compose và return `Mono<ServerResponse>` |
| Handler gọi `.block()` | Chặn thread WebFlux | Dùng reactive repository/client và compose publisher |
| DTO HTTP được dùng làm domain model ở mọi nơi | API contract và domain thay đổi cùng nhau | Tạo command/result/domain model khi cần ranh giới |
| Mỗi route có logic validation trùng nhau | Quy tắc không có chủ sở hữu | Đặt invariant trong service/domain; input shape ở adapter |
| Service biết URL, query string hoặc JSON field name | Use case phụ thuộc contract transport | Chuyển request sang command trước khi gọi service |
| Repository trả `ServerResponse` | Persistence phụ thuộc HTTP | Repository trả entity/domain result hoặc publisher |
| Mọi lỗi đều thành 400 | Che lỗi domain/server | Phân loại input, domain conflict và unexpected error |

Không phải mọi controller/handler ngắn đều cần thêm abstraction. Nếu một endpoint chỉ trả health status tĩnh, không cần tạo service và repository giả. Tách lớp để bảo vệ logic có giá trị, không phải để tăng số file.

## 15. Checklist thiết kế endpoint chức năng

Trước khi đưa route vào production, hãy kiểm tra:

- Router chỉ chứa path, method, predicate và liên kết handler.
- Route cụ thể được khai báo trước route tổng quát.
- Handler đọc `ServerRequest`, decode và map DTO sang command.
- Handler trả `Mono<ServerResponse>` và không tự subscribe/block.
- Service không phụ thuộc `ServerRequest`, `ServerResponse`, `HttpStatus` hoặc URL.
- Business invariants được kiểm tra tại service/domain, không chỉ ở một route.
- Repository port không phụ thuộc HTTP; adapter persistence triển khai port.
- Response DTO chỉ công khai field cần thiết.
- Domain/application errors được ánh xạ ở HTTP boundary.
- Unexpected errors không bị đổi thành 400 một cách vô điều kiện.
- Request body decode failure được phân biệt với business validation.
- Cross-cutting logging/security được đặt ở filter/security layer phù hợp.
- Service tests không cần HTTP server; route tests xác nhận hợp đồng HTTP.
- Có test cho success, invalid input, domain error và resource not found.
- Reactive chain được compose; cancellation và lỗi có thể truyền qua pipeline.

## 16. Bài tập tự kiểm tra

**Bài 1.** Một router nhận `POST /orders`, kiểm tra khách hàng có đủ hạn mức hay không rồi chọn handler. Phần kiểm tra hạn mức nên đặt ở đâu?

**Đáp án:** Trong application service/domain policy được use case gọi. Router chỉ chọn handler dựa trên HTTP request.

**Bài 2.** Handler nhận `ServerRequest`, decode JSON thành `CreateOrderRequest`, sau đó chuyển thành `CreateOrderCommand`. Đây có phải business logic không?

**Đáp án:** Không. Đây là chuyển đổi tại HTTP boundary. Business rules như số lượng, giá và quyền đặt hàng thuộc service/domain.

**Bài 3.** `OrderService.create` trả `Mono<ServerResponse>`. Vì sao đây là ranh giới sai?

**Đáp án:** Service phụ thuộc HTTP representation. Nên trả `Mono<Order>` hoặc kết quả use case; handler quyết định status, header và response body.

**Bài 4.** Cùng use case tạo order được gọi từ HTTP và message consumer. Logic tính tổng nên đặt ở đâu?

**Đáp án:** Service/domain. Mỗi adapter chuyển input riêng thành command và gọi cùng use case.

**Bài 5.** Một order không tồn tại. Repository trả gì và HTTP handler quyết định gì?

**Đáp án:** Repository/service có thể trả `Mono.empty()`. HTTP handler chuyển empty thành `404 Not Found`; message consumer có thể xử lý kết quả đó theo contract khác.

**Bài 6.** Khi đổi path `/api/orders` thành `/v2/orders`, có cần sửa `OrderService` không?

**Đáp án:** Không, nếu command và nghiệp vụ không đổi. Cập nhật router hoặc HTTP adapter.

**Bài 7.** Vì sao không nên gọi `.subscribe()` trong handler?

**Đáp án:** Nó tạo subscription tách khỏi response pipeline. WebFlux không còn điều khiển đầy đủ lỗi, cancellation và thời điểm hoàn tất của công việc đó.

**Bài 8.** Một `InvalidOrderException` nên chứa `HttpStatus.UNPROCESSABLE_ENTITY` không?

**Đáp án:** Không cần. Exception nên mô tả lỗi nghiệp vụ; HTTP adapter quyết định status theo API contract. Cùng lỗi đó có thể được biểu diễn khác ở message consumer hoặc batch adapter.

## 17. Ghi nhớ

- **Router** chọn handler dựa trên path, HTTP method và request predicates.
- **Handler** là HTTP adapter: đọc request, decode, map DTO/command, gọi service và tạo response.
- **Application service/domain** thực thi use case và quy tắc nghiệp vụ; không phụ thuộc HTTP.
- **Repository port/adapter** tách nhu cầu lưu trữ khỏi công nghệ persistence.
- `Mono`/`Flux` có thể đi qua application service vì đây là reactive composition; không đồng nghĩa service phải biết HTTP.
- Domain exception/result được chuyển thành HTTP status tại boundary.
- Kiểm thử service bằng `StepVerifier`; kiểm thử route/HTTP bằng `WebTestClient`.
- Đừng tách lớp máy móc: giữ code nhỏ khi không có logic cần bảo vệ hoặc tái sử dụng.

Khi đọc một endpoint, hãy hỏi: **đoạn này đang định tuyến, chuyển đổi HTTP hay quyết định nghiệp vụ?** Nếu một method trả lời cả ba câu hỏi, đó là tín hiệu nên tách trách nhiệm.

## Tài liệu chính thức

- Spring Framework, **Functional Endpoints (WebFlux.fn)**: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Framework 6.2, **Functional Endpoints**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html
- Spring Framework, **WebFlux `ServerRequest` và `ServerResponse`**: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Framework, **WebFlux Handler Filters**: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Framework, **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Project Reactor, **Testing with StepVerifier**: https://projectreactor.io/docs/core/3.6.6/reference/testing.html