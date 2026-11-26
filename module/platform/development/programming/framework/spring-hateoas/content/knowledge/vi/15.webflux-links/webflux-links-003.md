# Link trong Spring WebFlux với Spring HATEOAS

Spring WebFlux xử lý request theo mô hình reactive, thường dùng `Mono` và `Flux` để biểu diễn dữ liệu bất đồng bộ. Khi xây dựng API hypermedia trên WebFlux, việc tạo liên kết cũng cần phù hợp với luồng reactive. Spring HATEOAS cung cấp `WebFluxLinkBuilder` để tạo `Link` từ mapping controller và trả kết quả dưới dạng `Mono<Link>`, cùng `ReactiveRepresentationModelAssembler` để chuyển đổi dữ liệu thành representation model trong pipeline.

Bài học này tập trung vào cách tạo link cho endpoint WebFlux, kết hợp nhiều link bất đồng bộ, xây representation cho item và collection, sử dụng `ServerWebExchange`, cấu hình địa chỉ công khai khi chạy sau proxy và kiểm thử bằng `WebTestClient`. Ví dụ xuyên suốt dùng API quản lý đơn hàng.

## 1. Vì sao WebFlux cần cách tạo link riêng?

Trong Spring MVC, `WebMvcLinkBuilder` thường lấy thông tin request từ servlet request context để tạo URI. Spring WebFlux không dùng Servlet API; request được biểu diễn bằng `ServerWebExchange` và ngữ cảnh reactive của Reactor. Vì vậy, Spring HATEOAS cung cấp `WebFluxLinkBuilder` trong package `org.springframework.hateoas.server.reactive`.

Sự khác biệt chính nằm ở cách nhận thông tin request và kiểu kết quả:

| Spring MVC | Spring WebFlux |
| --- | --- |
| `WebMvcLinkBuilder` | `WebFluxLinkBuilder` |
| Dựa trên ngữ cảnh request của Servlet MVC. | Dựa trên `ServerWebExchange` trong Reactor Context hoặc exchange truyền tường minh. |
| Tạo `Link` trực tiếp. | Tạo link qua pipeline và kết thúc bằng `Mono<Link>`. |
| Thường dùng `RepresentationModelAssembler`. | Có thể dùng `ReactiveRepresentationModelAssembler`. |
| Kiểm thử HTTP thường dùng MockMvc. | Kiểm thử HTTP thường dùng WebTestClient. |

Không nên đưa `WebMvcLinkBuilder` vào một controller WebFlux. Hãy chọn builder theo đúng web stack của ứng dụng để tránh phụ thuộc vào Servlet API và giữ cách tạo URI tương thích với request reactive.

## 2. Khai báo endpoint WebFlux

Một controller WebFlux thường trả về `Mono<T>` cho một kết quả hoặc `Flux<T>` cho một luồng nhiều phần tử. Ví dụ endpoint đọc một đơn hàng:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    Mono<OrderView> getOrder(@PathVariable UUID id) {
        return orderService.findById(id)
                .map(order -> new OrderView(
                        order.getId(),
                        order.getStatus().name(),
                        order.getTotal()
                ));
    }
}
```

Trong ví dụ, `orderService.findById(id)` trả về `Mono<Order>`. Controller ánh xạ domain object sang DTO bằng `map`, không chặn luồng để chờ dữ liệu. Khi thêm hypermedia, ta sẽ bọc `OrderView` trong `EntityModel` và bổ sung link.

## 3. Tạo self link bằng WebFluxLinkBuilder

`WebFluxLinkBuilder` cung cấp hai phương thức tĩnh quan trọng:

- `methodOn(Controller.class).method(...)` tạo tham chiếu tới method controller và tham số cần thiết để phân tích mapping.
- `linkTo(...)` tạo builder từ lời gọi method đó. Có thể gọi `withSelfRel()` hoặc `withRel(...)`, sau đó dùng `toMono()` để nhận `Mono<Link>`.

Các static import thường dùng:

```java
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;
```

Ví dụ tạo self link cho đơn hàng:

```java
Mono<Link> selfLink = linkTo(
        methodOn(OrderController.class).getOrder(orderId)
).withSelfRel().toMono();
```

`toMono()` trả về `Mono<Link>` vì việc dựng link cần thông tin từ môi trường WebFlux. Trong request đang được xử lý, `WebFluxLinkBuilder` có thể tìm `ServerWebExchange` từ Reactor Context và kết hợp nó với annotation mapping của Spring Web để tạo URI đầy đủ. Nếu không có exchange trong context, builder có thể tạo URI tương đối.

`methodOn` tạo một tham chiếu để đọc metadata mapping; nó không gọi method controller để truy vấn database hoặc thực thi nghiệp vụ. Hãy dùng service để lấy dữ liệu, còn builder để tạo URI.

## 4. Kết hợp dữ liệu và link trong Mono

Sau khi lấy được dữ liệu, có thể tạo link bất đồng bộ rồi ánh xạ thành `EntityModel`:

```java
@GetMapping("/{id}")
Mono<EntityModel<OrderView>> getOrder(@PathVariable UUID id) {
    return orderService.findById(id)
            .flatMap(order -> linkTo(
                    methodOn(OrderController.class).getOrder(id)
            ).withSelfRel().toMono()
             .map(self -> {
                 OrderView view = new OrderView(
                         order.getId(),
                         order.getStatus().name(),
                         order.getTotal()
                 );

                 return EntityModel.of(view, self);
             }));
}
```

Ở đây:

- `findById` trả về `Mono<Order>`.
- `flatMap` được dùng vì bước tiếp theo trả về một publisher khác là `Mono<Link>`.
- `toMono()` tạo link trong luồng reactive.
- `map` chuyển link và DTO thành `EntityModel<OrderView>`.
- Kết quả cuối cùng là `Mono<EntityModel<OrderView>>`, phù hợp với controller WebFlux.

Nếu chỉ chuyển đổi một object đồng bộ, dùng `map`. Khi gọi một thao tác trả về `Mono` hoặc `Flux`, dùng `flatMap`, `concatMap` hoặc toán tử kết hợp phù hợp. Không gọi `.block()` để lấy `Link` đồng bộ trong controller; làm vậy sẽ phá vỡ tính non-blocking của pipeline và có thể gây nghẽn event loop.

## 5. Tạo nhiều link cho cùng một representation

Một item có thể cần self link và link tới tài nguyên liên quan. Mỗi lời gọi `WebFluxLinkBuilder` trả về một publisher, vì vậy có thể kết hợp bằng `Mono.zip`:

```java
@GetMapping("/{id}")
Mono<EntityModel<OrderView>> getOrder(@PathVariable UUID id) {
    return orderService.findById(id)
            .flatMap(order -> {
                Mono<Link> self = linkTo(
                        methodOn(OrderController.class).getOrder(id)
                ).withSelfRel().toMono();

                Mono<Link> customer = linkTo(
                        methodOn(CustomerController.class)
                                .getCustomer(order.getCustomerId())
                ).withRel("customer").toMono();

                OrderView view = new OrderView(
                        order.getId(),
                        order.getStatus().name(),
                        order.getTotal()
                );

                return Mono.zip(self, customer)
                        .map(links -> EntityModel.of(
                                view,
                                links.getT1(),
                                links.getT2()
                        ));
            });
}
```

`Mono.zip` đợi cả hai link hoàn thành rồi tạo một model. Relation `self` trỏ tới GET endpoint của đơn hàng; `customer` trỏ tới GET endpoint của khách hàng liên quan. Relation riêng như `customer` cần được định nghĩa và duy trì nhất quán trong hợp đồng API.

Nếu một link phụ thuộc vào kết quả của link khác, hãy dùng `flatMap` theo thứ tự. Nếu nhiều link độc lập, `Mono.zip` giúp kết hợp chúng trong cùng pipeline. Khi một publisher không phát ra giá trị, hành vi của `zip` cần được xem xét; các link bắt buộc nên tạo ra một giá trị hoặc có cách xử lý lỗi phù hợp.

## 6. Tạo collection model từ Flux

Một endpoint danh sách có thể đọc dữ liệu bằng `Flux<Order>`. Nếu muốn trả về một collection representation có link ở cấp collection và link riêng cho từng item, hãy chuyển từng phần tử thành `EntityModel`, gom chúng thành danh sách rồi bọc bằng `CollectionModel`.

```java
@GetMapping
Mono<CollectionModel<EntityModel<OrderView>>> listOrders() {
    return orderService.findAll()
            .concatMap(order -> {
                OrderView view = new OrderView(
                        order.getId(),
                        order.getStatus().name(),
                        order.getTotal()
                );

                return linkTo(methodOn(OrderController.class)
                        .getOrder(order.getId()))
                        .withSelfRel()
                        .toMono()
                        .map(self -> EntityModel.of(view, self));
            })
            .collectList()
            .flatMap(items -> linkTo(
                    methodOn(OrderController.class).listOrders()
            ).withSelfRel().toMono()
             .map(collectionSelf -> CollectionModel.of(items, collectionSelf)));
}
```

`concatMap` chuyển đổi từng đơn hàng và giữ thứ tự phần tử theo nguồn `Flux`. `collectList()` tạo danh sách các representation; sau đó link `self` của collection được tạo và gắn vào `CollectionModel`.

Nếu API chỉ trả `Flux<EntityModel<OrderView>>`, client có thể nhận một luồng các phần tử nhưng không có một collection envelope rõ ràng để chứa link cấp danh sách. Dùng `Mono<CollectionModel<...>>` khi cần công bố `self`, `next`, `prev` hoặc relation khác ở cấp collection.

Với danh sách lớn hoặc streaming response, cần cân nhắc chi phí gom toàn bộ phần tử vào bộ nhớ. Một collection representation hoàn chỉnh thường cần biết các phần tử và link cấp collection trước khi serialize. Nếu cần streaming từng phần tử, hãy xác định rõ media type và hợp đồng mà client sẽ nhận.

## 7. Sử dụng ReactiveRepresentationModelAssembler

Spring HATEOAS cung cấp `ReactiveRepresentationModelAssembler<T, D>` trong package `org.springframework.hateoas.server.reactive`. Đây là biến thể reactive của `RepresentationModelAssembler`:

- `toModel(T entity, ServerWebExchange exchange)` trả về `Mono<D>`.
- `toCollectionModel(Flux<? extends T> entities, ServerWebExchange exchange)` trả về `Mono<CollectionModel<D>>`.

Ví dụ assembler cho đơn hàng:

```java
@Component
class OrderModelAssembler
        implements ReactiveRepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public Mono<EntityModel<OrderView>> toModel(
            Order order,
            ServerWebExchange exchange) {

        OrderView view = new OrderView(
                order.getId(),
                order.getStatus().name(),
                order.getTotal()
        );

        return WebFluxLinkBuilder.linkTo(
                methodOn(OrderController.class).getOrder(order.getId()),
                exchange
        ).withSelfRel().toMono()
         .map(self -> EntityModel.of(view, self));
    }
}
```

Assembler nhận `ServerWebExchange` tường minh và truyền nó vào overload `linkTo(invocation, exchange)`. Cách này hữu ích khi logic tạo representation được tách khỏi controller và cần dùng request hiện tại để dựng URI. `toCollectionModel(...)` mặc định sử dụng `toModel(...)` để chuyển các phần tử trong `Flux` thành collection model.

Nếu cần tự kiểm soát link cấp collection, có thể bổ sung link sau khi `toCollectionModel(...)` hoàn thành:

```java
@GetMapping
Mono<CollectionModel<EntityModel<OrderView>>> listOrders(ServerWebExchange exchange) {
    return assembler.toCollectionModel(orderService.findAll(), exchange)
            .flatMap(collection -> WebFluxLinkBuilder.linkTo(
                    methodOn(OrderController.class).listOrders(null), exchange
            ).withSelfRel().toMono()
             .map(link -> collection.add(link)));
}
```

Trong ví dụ, `exchange` được truyền tường minh vào assembler và builder. `null` trong `methodOn(...).listOrders(null)` là placeholder cho tham số `ServerWebExchange` do WebFlux cung cấp lúc xử lý request; nó không trở thành path variable hoặc query parameter trong URI. Một lựa chọn khác là thiết kế method route không nhận exchange và dựa vào Reactor Context khi link được tạo trong request pipeline.

`SimpleReactiveRepresentationModelAssembler<T>` là biến thể tiện lợi khi chỉ cần bọc dữ liệu trong `EntityModel<T>` và bổ sung link đồng bộ qua các phương thức `addLinks(...)`. Khi việc tạo link cần kết hợp publisher bất đồng bộ, triển khai trực tiếp `ReactiveRepresentationModelAssembler` giúp kiểm soát pipeline rõ ràng hơn.

## 8. Dùng ServerWebExchange tường minh

`WebFluxLinkBuilder.linkTo(invocation)` kiểm tra Reactor Context để tìm `ServerWebExchange`. Trong phần lớn luồng xử lý của một request WebFlux, cách này thuận tiện vì exchange được truyền qua reactive context.

Builder cũng có overload:

```java
WebFluxLinkBuilder.linkTo(invocation, exchange)
```

Overload này hữu ích khi:

- Một assembler hoặc service nhận `ServerWebExchange` như tham số và cần tạo link dựa trên request đó.
- Việc tạo representation được gọi từ một thành phần mà Reactor Context không còn chứa exchange.
- Bạn muốn truyền rõ request context cần dùng khi tạo URI.

Không nên lưu `ServerWebExchange` vào field của singleton service hoặc assembler. Exchange thuộc về một request cụ thể; hãy truyền nó qua tham số hoặc sử dụng Reactor Context theo đúng vòng đời của request.

Nếu builder không tìm thấy exchange, tài liệu API cho biết nó có thể quay về URI tương đối. Vì vậy, khi cần URI tuyệt đối hoặc cần phản ánh host công khai, hãy kiểm tra response thực tế và cân nhắc truyền exchange tường minh.

## 9. Link cho query parameter và URI template

WebFlux controller có thể nhận query parameter qua `@RequestParam`. Khi tạo link tới một method có tham số lọc hoặc phân trang, hãy dùng `methodOn` để Spring HATEOAS phân tích mapping và tham số.

Ví dụ endpoint tìm đơn hàng:

```java
@GetMapping("/search")
Mono<CollectionModel<EntityModel<OrderView>>> searchOrders(
        @RequestParam(required = false) OrderStatus status,
        @RequestParam(defaultValue = "0") int page) {
    // Tìm đơn hàng theo trạng thái và trang.
}
```

Tạo link tìm kiếm với giá trị đã biết:

```java
Mono<Link> pendingPage = linkTo(
        methodOn(OrderController.class)
                .searchOrders(OrderStatus.PENDING, 0)
).withRel("pending-orders").toMono();
```

Nếu client cần tự chọn giá trị lọc, có thể công bố URI template thay vì một URI đã điền sẵn:

```java
Link search = Link.of("/orders/search{?status,page}", "search");
```

Client sẽ đọc `templated: true` trong HAL và mở rộng template bằng giá trị mong muốn. Hãy kiểm tra link được sinh ra để bảo đảm tên query parameter khớp với controller, các tham số lọc/sort được giữ khi chuyển trang và giá trị có ký tự đặc biệt được mã hóa đúng.

## 10. Cấu hình hypermedia và HAL cho WebFlux

Các model như `EntityModel`, `CollectionModel` và class kế thừa `RepresentationModel` có thể được trả trực tiếp từ WebFlux controller. Khi ứng dụng hỗ trợ HAL và client gửi `Accept: application/hal+json`, Spring HATEOAS serialize các liên kết dưới `_links` và các phần tử collection dưới `_embedded`.

Ví dụ response cho một đơn hàng:

```json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "customer": {
      "href": "/customers/7"
    }
  }
}
```

Trong ứng dụng Spring Boot có starter và auto-configuration phù hợp, phần hỗ trợ hypermedia thường được thiết lập theo web stack hiện tại. Với ứng dụng cấu hình thủ công, hãy kích hoạt hỗ trợ hypermedia cho media type cần dùng, chẳng hạn HAL, theo cấu hình Spring HATEOAS của phiên bản đang sử dụng.

Kiểm tra cả `Content-Type` và cấu trúc JSON. Một response JSON thông thường không chứng minh HAL đã được cấu hình. Client cần nhận đúng media type và có thể tìm relation trong `_links`.

## 11. Reverse proxy và URI công khai trong WebFlux

Ứng dụng WebFlux có thể chạy phía sau reverse proxy, ingress hoặc load balancer. Request nội bộ có thể dùng host, port hoặc scheme khác địa chỉ công khai. Nếu forwarded header không được xử lý, link được tạo có thể chứa địa chỉ nội bộ mà client không truy cập được.

Spring HATEOAS hướng dẫn dùng `ForwardedHeaderTransformer` cho WebFlux:

```java
@Bean
ForwardedHeaderTransformer forwardedHeaderTransformer() {
    return new ForwardedHeaderTransformer();
}
```

Transformer xử lý các header `X-Forwarded-*` để thông tin request phản ánh địa chỉ gốc do proxy chuyển tiếp. Chỉ bật xử lý forwarded header khi ứng dụng nằm sau proxy đáng tin cậy và proxy được cấu hình kiểm soát các header này. Không để client tùy ý quyết định host hoặc scheme của URI được server công bố.

Hãy kiểm thử self link qua môi trường gần với triển khai để xác nhận scheme, host, port và context path đúng. Đây là bước quan trọng khi API trả URI tuyệt đối.

## 12. Giới hạn cần biết khi dùng WebFlux

Một số API hỗ trợ Spring MVC chưa có implementation mặc định tương đương trong WebFlux. Tài liệu Spring HATEOAS hiện nêu `EntityLinks` và các implementation của nó chưa được cung cấp sẵn cho Spring WebFlux vì SPI ban đầu được thiết kế quanh Spring MVC và chưa xét đầy đủ Reactor types.

Vì vậy, trong WebFlux bạn thường tạo link bằng `WebFluxLinkBuilder` và tham chiếu controller method. Nếu ứng dụng cần một abstraction độc lập với controller để tạo link theo loại entity, có thể xây dựng thành phần riêng hoặc implementation phù hợp với kiến trúc reactive của dự án.

Ngoài ra:

- `WebMvcLinkBuilder` không phải lựa chọn cho controller WebFlux.
- `WebFluxLinkBuilder` tạo link bất đồng bộ; không gọi `.block()` trong request pipeline.
- `ReactiveRepresentationModelAssembler` yêu cầu `ServerWebExchange` khi chuyển đổi entity.
- `Flux<T>` không tự tạo collection envelope có link cấp collection; dùng `CollectionModel` khi hợp đồng cần điều hướng ở cấp danh sách.
- Nếu không có `ServerWebExchange` trong Reactor Context, builder có thể tạo URI tương đối.
- Không lưu exchange của request vào singleton hoặc chia sẻ giữa nhiều request.

## 13. Kiểm thử link WebFlux

Có thể kiểm thử pipeline tạo link bằng `StepVerifier`. Ví dụ khi chạy trong ngữ cảnh phù hợp:

```java
StepVerifier.create(
        linkTo(methodOn(OrderController.class).getOrder(orderId))
                .withSelfRel()
                .toMono()
)
    .assertNext(link -> {
        assertThat(link.getRel()).isEqualTo(IanaLinkRelations.SELF);
        assertThat(link.getHref()).endsWith("/orders/" + orderId);
    })
    .verifyComplete();
```

Khi kiểm thử link tuyệt đối, cần thiết lập request context hoặc truyền `ServerWebExchange` tường minh. Nếu không, builder có thể tạo URI tương đối; assertion cần phản ánh chính sách URI mà ứng dụng lựa chọn.

Với kiểm thử endpoint HTTP, dùng `WebTestClient`:

```java
webTestClient.get()
        .uri("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaTypes.HAL_JSON)
        .expectBody()
        .jsonPath("$._links.self.href")
        .value(endsWith("/orders/" + orderId));
```

Kiểm thử collection nên xác nhận self link cấp collection và self link riêng trên từng item. Với nhiều link, kiểm tra relation và `href`; không phụ thuộc thứ tự link trong JSON. Cũng cần kiểm thử lỗi từ repository hoặc service để bảo đảm publisher lỗi được chuyển thành HTTP error theo chính sách của ứng dụng.

## 14. Những lỗi thường gặp

**Dùng WebMvcLinkBuilder trong WebFlux.** Hai builder dựa trên web stack khác nhau. Dùng `WebFluxLinkBuilder` cho controller reactive.

**Gọi block để lấy Link.** `toMono()` đã cung cấp link dưới dạng publisher. Hãy kết hợp bằng `flatMap`, `map` hoặc `Mono.zip`; không chặn event loop.

**Dùng map cho một publisher lồng nhau.** Nếu callback trả về `Mono<Link>`, dùng `flatMap` hoặc `Mono.zip` để tránh tạo `Mono<Mono<...>>`.

**Chỉ trả Flux item khi cần link collection.** Một luồng item không tự tạo collection representation. Hãy bọc bằng `CollectionModel` khi cần relation ở cấp collection.

**Bỏ qua ServerWebExchange.** Khi tạo link ngoài request context hoặc trong assembler, truyền exchange tường minh để builder tạo URI theo request cần dùng.

**Giả định EntityLinks có sẵn.** Tài liệu hiện tại nêu API này chưa có implementation mặc định cho WebFlux. Dùng WebFluxLinkBuilder hoặc xây abstraction reactive riêng.

**Tin forwarded header không kiểm soát.** Cấu hình `ForwardedHeaderTransformer` cùng proxy đáng tin cậy để tránh công bố URI giả mạo.

## 15. Bài tập thực hành và tiêu chí hoàn thành

Hãy chuyển một API đơn hàng sang Spring WebFlux và bổ sung hypermedia:

1. Tạo controller trả `Mono<OrderView>` cho GET chi tiết và `Flux<Order>` cho service đọc danh sách.
2. Dùng `WebFluxLinkBuilder` tạo self link từ mapping GET chi tiết.
3. Kết hợp dữ liệu và link thành `Mono<EntityModel<OrderView>>` mà không gọi `block()`.
4. Tạo link `customer` bằng một publisher riêng và kết hợp bằng `Mono.zip`.
5. Chuyển từng item trong `Flux` thành `EntityModel`, gom vào `CollectionModel` và thêm self link collection.
6. Thử triển khai `ReactiveRepresentationModelAssembler` để tách logic chuyển đổi.
7. So sánh cách builder lấy exchange từ Reactor Context với overload nhận `ServerWebExchange` tường minh.
8. Yêu cầu HAL JSON và kiểm tra `_links`, `_embedded` cùng content type bằng WebTestClient.
9. Cấu hình `ForwardedHeaderTransformer` trong môi trường proxy thử nghiệm và xác nhận URI công khai được sinh đúng.
10. Kiểm tra lỗi service, collection rỗng và nhiều item để bảo đảm pipeline reactive hoàn tất hoặc phát lỗi đúng cách.

Bạn đã nắm được link trong WebFlux khi có thể tạo `Mono<Link>` từ mapping controller, kết hợp publisher với dữ liệu mà không chặn luồng, dùng reactive assembler cho item và collection, truyền `ServerWebExchange` đúng lúc và kiểm thử response HAL bằng WebTestClient. Đây là nền tảng để xây dựng REST API reactive có điều hướng hypermedia bằng Spring HATEOAS.

## Tài liệu tham khảo chính thức

- [Spring HATEOAS API: WebFluxLinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/WebFluxLinkBuilder.html)
- [Spring HATEOAS API: ReactiveRepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/ReactiveRepresentationModelAssembler.html)
- [Spring HATEOAS API: SimpleReactiveRepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/SimpleReactiveRepresentationModelAssembler.html)
- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
