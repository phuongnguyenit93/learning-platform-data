# WebFluxLinkBuilder trong Spring HATEOAS

Khi xây dựng REST API bằng Spring WebFlux, việc tạo liên kết hypermedia cũng phải phù hợp với mô hình xử lý bất đồng bộ của WebFlux. **WebFluxLinkBuilder** là công cụ của Spring HATEOAS để tạo URI từ mapping của reactive controller. Khác với builder dành cho Spring MVC, các thao tác tạo link trong WebFlux trả về **Mono<Link>**, vì vậy chúng cần được kết hợp vào chuỗi reactive đang xử lý request.

Cách làm này cho phép controller trả về `Mono<EntityModel<T>>` hoặc `Mono<CollectionModel<T>>` sau khi đã tạo đủ các liên kết. Mã ứng dụng không cần chặn luồng để chờ link hoàn tất; thay vào đó, nó ghép các publisher bằng `map`, `flatMap`, `zip` hoặc các toán tử Reactor phù hợp.

## 1. WebFluxLinkBuilder là gì?

Spring HATEOAS cung cấp hai builder tương ứng với hai mô hình web phổ biến:

| Builder | Nền tảng | Kết quả tạo link |
|---|---|---|
| `WebMvcLinkBuilder` | Spring MVC, Servlet | `Link` đồng bộ |
| `WebFluxLinkBuilder` | Spring WebFlux, reactive | `Mono<Link>` |

Với WebFlux, URI được xây dựng dựa trên mapping của controller và ngữ cảnh request hiện tại. Do việc phân giải thông tin request diễn ra trong môi trường reactive, Spring HATEOAS trả về một publisher chứa Link thay vì trả Link trực tiếp.

Các thành phần thường dùng:

- `linkTo(...)`: bắt đầu xây dựng liên kết từ mapping controller.
- `methodOn(...)`: tham chiếu phương thức controller và các tham số của phương thức.
- `withSelfRel()`: hoàn tất liên kết với relation `self`.
- `withRel(...)`: hoàn tất liên kết với relation được chỉ định.

Khi dùng WebFlux, import các phương thức tĩnh từ package reactive:

~~~java
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;
~~~

Ví dụ:

~~~java
Mono<Link> selfLink = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel();
~~~

Biến `selfLink` có kiểu `Mono<Link>`. Nó sẽ phát ra Link khi framework phân giải xong mapping và ngữ cảnh request.

## 2. Cấu hình dependency cho ứng dụng WebFlux

Với Spring Boot, ứng dụng reactive thường dùng WebFlux starter và Spring HATEOAS starter:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-hateoas")
}
~~~

Nên để Spring Boot dependency management quản lý phiên bản tương thích của các thư viện. Không trộn cấu hình MVC và WebFlux tùy tiện trong cùng ứng dụng; hãy xác định stack web mà ứng dụng đang sử dụng và chọn builder tương ứng.

Controller WebFlux vẫn sử dụng các annotation quen thuộc như `@RestController`, `@GetMapping`, `@PathVariable` và `@RequestParam`. Điểm khác biệt nằm ở kiểu trả về và cách xử lý kết quả: thường là `Mono<T>` cho không hoặc một kết quả, và `Flux<T>` cho một luồng nhiều phần tử.

## 3. Tạo link self trong reactive controller

Giả sử service tìm đơn hàng trả về `Mono<Order>`. Controller có thể chuyển đơn hàng thành DTO, tạo link self rồi bọc cả hai trong `EntityModel`.

~~~java
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderMapper mapper;

    public OrderController(
            OrderService orderService,
            OrderMapper mapper) {
        this.orderService = orderService;
        this.mapper = mapper;
    }

    @GetMapping("/{orderId}")
    public Mono<EntityModel<OrderDto>> one(
            @PathVariable Long orderId) {

        return orderService.findById(orderId)
            .flatMap(order -> {
                OrderDto dto = mapper.toDto(order);

                return linkTo(
                    methodOn(OrderController.class).one(orderId)
                )
                    .withSelfRel()
                    .map(self -> EntityModel.of(dto, self));
            });
    }
}
~~~

Luồng xử lý diễn ra như sau:

1. `orderService.findById(orderId)` trả về `Mono<Order>`.
2. `flatMap` nhận Order khi publisher phát ra dữ liệu.
3. Mapper chuyển Order thành DTO.
4. `linkTo(methodOn(...))` tạo publisher `Mono<Link>`.
5. `map` chuyển Link thành `EntityModel<OrderDto>`.
6. Controller trả publisher cho WebFlux để framework gửi response khi dữ liệu sẵn sàng.

Dùng `flatMap` ở bước kết hợp với link builder vì thao tác tạo link cũng trả về một publisher. Dùng `map` để biến một giá trị đã có thành giá trị khác đồng bộ, chẳng hạn Link thành EntityModel.

## 4. Tạo link có path variable và query parameter

Cách tham chiếu phương thức controller tương tự Spring MVC: truyền các giá trị tương ứng với tham số của phương thức.

Ví dụ endpoint chi tiết mặt hàng:

~~~java
@GetMapping("/{orderId}/items/{itemId}")
public Mono<OrderItemDto> item(
        @PathVariable Long orderId,
        @PathVariable Long itemId) {
    return itemService.findById(orderId, itemId)
        .map(itemMapper::toDto);
}
~~~

Tạo link đến mặt hàng:

~~~java
Mono<Link> itemLink = linkTo(
    methodOn(OrderItemController.class).item(orderId, itemId)
).withSelfRel();
~~~

Với endpoint tìm kiếm có query parameter:

~~~java
@GetMapping("/search")
public Flux<OrderDto> search(
        @RequestParam(required = false) String status) {
    return orderService.search(status)
        .map(mapper::toDto);
}
~~~

Tạo link đến một truy vấn cụ thể:

~~~java
Mono<Link> paidOrders = linkTo(
    methodOn(OrderController.class).search("PAID")
).withRel("search");
~~~

Link được tạo từ mapping và giá trị tham số đã truyền vào. Nếu cần công bố một mẫu tìm kiếm tổng quát để máy khách tự cung cấp nhiều tham số, hãy dùng URI template; link đến truy vấn cụ thể không thay thế link template.

## 5. Kết hợp nhiều link bằng Mono.zip

Một representation có thể cần nhiều liên kết, chẳng hạn `self`, liên kết đến collection và liên kết đến tài nguyên liên quan. Vì mỗi lần gọi builder trả về `Mono<Link>`, có thể kết hợp các publisher bằng `Mono.zip`.

~~~java
Mono<Link> selfLink = linkTo(
    methodOn(OrderController.class).one(order.getId())
).withSelfRel();

Mono<Link> itemsLink = linkTo(
    methodOn(OrderItemController.class).all(order.getId())
).withRel("https://api.example.com/rels/order-items");

return Mono.zip(selfLink, itemsLink)
    .map(links -> EntityModel.of(
        orderDto,
        links.getT1(),
        links.getT2()
    ));
~~~

`Mono.zip` chờ các publisher thành phần phát ra giá trị rồi kết hợp chúng thành một tuple. `getT1()` và `getT2()` lấy hai Link đã tạo. Nếu một publisher lỗi, lỗi được truyền xuống chuỗi reactive.

Cách này phù hợp khi các link có thể được tạo độc lập. Nó giúp tránh lồng nhiều `flatMap` chỉ để đợi từng link hoàn tất.

Nếu có liên kết tùy chọn, ví dụ đơn hàng chỉ có payment khi đã thanh toán, cần xử lý publisher rỗng một cách tường minh. `Mono.zip` không phát ra tuple nếu một nguồn hoàn tất mà không phát giá trị.

~~~java
Mono<Link> selfLink = linkTo(
    methodOn(OrderController.class).one(order.getId())
).withSelfRel();

Mono<Link> paymentLink = order.getPaymentId() == null
    ? Mono.empty()
    : linkTo(methodOn(PaymentController.class)
        .one(order.getPaymentId()))
        .withRel("https://api.example.com/rels/payment");

return selfLink.flatMap(self ->
    paymentLink
        .map(payment -> EntityModel.of(orderDto, self, payment))
        .defaultIfEmpty(EntityModel.of(orderDto, self))
);
~~~

Trong ví dụ, `selfLink` luôn phải có. `paymentLink` chỉ phát ra Link khi có mã thanh toán. `defaultIfEmpty` tạo representation không có link payment khi publisher tùy chọn hoàn tất rỗng.

## 6. Tạo link cho collection từ Flux

Service WebFlux thường trả về `Flux<Order>` khi truy vấn nhiều đơn hàng. Mỗi phần tử có thể được chuyển thành một `EntityModel`, sau đó gom lại thành `CollectionModel`.

~~~java
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@GetMapping
public Mono<CollectionModel<EntityModel<OrderDto>>> all() {

    Flux<Order> orders = orderService.findAll();

    return orders
        .concatMap(order -> assembler.toModel(order))
        .collectList()
        .flatMap(models ->
            linkTo(methodOn(OrderController.class).all())
                .withSelfRel()
                .map(self -> CollectionModel.of(models, self))
        );
}
~~~

Ví dụ giả định `assembler.toModel(order)` trả về `Mono<EntityModel<OrderDto>>`.

- `concatMap` chuyển từng Order thành representation bất đồng bộ và giữ thứ tự phần tử nguồn.
- `collectList` gom các representation thành một `List`.
- Link self của collection được tạo bất đồng bộ.
- `CollectionModel.of(...)` bọc danh sách cùng link collection.

Có thể dùng `flatMap` nếu thứ tự phát ra không quan trọng. Khi thứ tự của danh sách phải được giữ, `concatMap` hoặc `flatMapSequential` phù hợp hơn.

Với dữ liệu lớn, không nên gom một luồng vô hạn hoặc tập hợp không giới hạn vào `collectList`. Hãy dùng phân trang hoặc giới hạn kết quả để response có kích thước kiểm soát được.

## 7. Tổ chức assembler reactive

Để controller gọn hơn, có thể tạo một assembler có phương thức trả về `Mono<EntityModel<OrderDto>>`. Phương thức này chịu trách nhiệm ánh xạ dữ liệu và xây dựng các link cần thiết.

~~~java
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class OrderReactiveAssembler {

    private final OrderMapper mapper;

    public OrderReactiveAssembler(OrderMapper mapper) {
        this.mapper = mapper;
    }

    public Mono<EntityModel<OrderDto>> toModel(Order order) {
        OrderDto dto = mapper.toDto(order);

        Mono<Link> self = linkTo(
            methodOn(OrderController.class).one(order.getId())
        ).withSelfRel();

        Mono<Link> collection = linkTo(
            methodOn(OrderController.class).all()
        ).withRel(IanaLinkRelations.COLLECTION);

        return Mono.zip(self, collection)
            .map(links -> EntityModel.of(
                dto,
                links.getT1(),
                links.getT2()
            ));
    }
}
~~~

Controller chỉ cần gọi assembler trong chuỗi reactive:

~~~java
@GetMapping("/{orderId}")
public Mono<EntityModel<OrderDto>> one(@PathVariable Long orderId) {
    return orderService.findById(orderId)
        .flatMap(assembler::toModel);
}
~~~

Assembler không thực thi nghiệp vụ thay cho service. Nó nhận dữ liệu đã được truy xuất, chuyển thành DTO và tạo representation hypermedia. Service vẫn chịu trách nhiệm tìm kiếm, kiểm tra trạng thái và áp dụng quy tắc nghiệp vụ.

Nếu cần chuẩn hóa nhiều assembler, có thể định nghĩa một interface nội bộ với phương thức trả về `Mono` của kiểu representation cụ thể, chẳng hạn `Mono<EntityModel<OrderDto>>`. Dù tổ chức theo cách nào, kiểu trả về cần giữ tính reactive và không chặn luồng.

## 8. Ngữ cảnh request trong reactive chain

Việc tạo link trong WebFlux có thể cần thông tin của request hiện tại, chẳng hạn scheme, host, port, context path và mapping đang được xử lý. WebFlux vận chuyển ngữ cảnh request qua Reactor Context.

Vì vậy, hãy tạo link bên trong chuỗi reactive gắn với request:

~~~java
return orderService.findById(orderId)
    .flatMap(order ->
        linkTo(methodOn(OrderController.class).one(orderId))
            .withSelfRel()
            .map(link -> EntityModel.of(mapper.toDto(order), link))
    );
~~~

Tránh tạo link bằng cách gọi builder ở một đoạn mã tách khỏi ngữ cảnh request rồi lưu publisher để dùng lại ở nơi khác. Một Link phụ thuộc request hiện tại không nên được cache như một giá trị dùng chung cho mọi request, vì host hoặc context path có thể khác nhau.

Trong tác vụ nền không có request WebFlux, không có ngữ cảnh request để builder suy ra host hiện tại. Nếu cần URI trong tác vụ nền, hãy dùng một URI gốc đã được cấu hình rõ ràng hoặc một cơ chế tạo URI độc lập với request.

## 9. Không block hoặc tự subscribe trong controller

Một sai lầm quan trọng là gọi `block()` để lấy Link đồng bộ:

~~~java
// Không nên: chặn luồng đang xử lý request reactive.
Link link = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel().block();
~~~

`block()` làm mất lợi ích bất đồng bộ, có thể chặn event-loop thread và gây nghẽn khi tải tăng. Cũng không nên gọi `subscribe()` bên trong controller để tự khởi chạy công việc rồi trả về response trước khi công việc hoàn tất.

Thay vào đó, trả về publisher và kết hợp các bước bằng Reactor:

| Mục đích | Toán tử thường dùng |
|---|---|
| Chuyển đổi một giá trị đồng bộ | `map` |
| Chuyển đổi sang Mono/Flux khác | `flatMap` |
| Kết hợp nhiều Mono độc lập | `Mono.zip` |
| Xử lý tuần tự từng phần tử bất đồng bộ | `concatMap` |
| Gom Flux hữu hạn thành danh sách | `collectList` |
| Cung cấp giá trị thay thế khi Mono rỗng | `defaultIfEmpty` |

Khi builder phát sinh lỗi, publisher lỗi sẽ truyền lỗi qua chuỗi reactive. Hãy xử lý lỗi ở tầng phù hợp bằng cơ chế exception handling của WebFlux hoặc các toán tử Reactor như `onErrorResume` khi có chính sách fallback rõ ràng.

## 10. Phân biệt WebFluxLinkBuilder với WebMvcLinkBuilder

Không nên dùng hai builder thay thế nhau chỉ vì chúng cùng tạo Link.

| Tiêu chí | WebMvcLinkBuilder | WebFluxLinkBuilder |
|---|---|---|
| Stack | Spring MVC | Spring WebFlux |
| Mô hình xử lý | Servlet, đồng bộ | Reactive, bất đồng bộ |
| Kết quả tạo link | `Link` | `Mono<Link>` |
| Kết hợp trong controller | Gắn trực tiếp vào model | Dùng `map`, `flatMap`, `zip` |
| Ngữ cảnh request | Servlet request context | Reactor Context và WebFlux request context |

Nếu controller trả về `Mono` hoặc `Flux` trong một ứng dụng WebFlux, hãy ưu tiên `WebFluxLinkBuilder`. Dùng builder MVC trong reactive controller có thể không sử dụng đúng ngữ cảnh request và làm mất lợi ích của cách tạo link bất đồng bộ.

## 11. HAL serialization trong WebFlux

Sau khi reactive chain tạo xong `EntityModel` hoặc `CollectionModel`, Spring HATEOAS tuần tự hóa model thành định dạng hypermedia đã chọn. Với HAL JSON, các liên kết nằm trong `_links`.

Ví dụ response:

~~~json
{
  "id": 42,
  "status": "PAID",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "collection": {
      "href": "https://api.example.com/orders"
    }
  }
}
~~~

Máy khách yêu cầu HAL bằng header:

~~~http
Accept: application/hal+json
~~~

WebFluxLinkBuilder chỉ tạo Link; việc tuần tự hóa representation thành HAL do cấu hình hypermedia và message writer của Spring đảm nhiệm. Nếu ứng dụng có custom codec hoặc cấu hình message writer, cần bảo đảm media type hypermedia được hỗ trợ.

## 12. Kiểm thử link với WebTestClient

Trong ứng dụng WebFlux, `WebTestClient` là lựa chọn phù hợp để kiểm thử endpoint reactive. Có thể xác nhận status, media type, dữ liệu DTO và link HAL trong cùng một request.

~~~java
webTestClient.get()
    .uri("/orders/42")
    .accept(MediaTypes.HAL_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
        .contentTypeCompatibleWith(MediaTypes.HAL_JSON)
    .expectBody()
    .jsonPath("$.id").isEqualTo(42)
    .jsonPath("$._links.self.href").exists()
    .jsonPath("$._links.collection.href").exists();
~~~

Nên bổ sung các trường hợp:

- Link self trỏ đúng mapping và ID.
- Link đến controller khác được tạo đúng URI.
- Query parameter được đưa vào URI theo đúng giá trị.
- Link hành động chỉ xuất hiện khi trạng thái nghiệp vụ cho phép.
- Publisher rỗng được xử lý đúng khi không tìm thấy tài nguyên.
- Lỗi khi tạo link hoặc truy xuất dữ liệu được chuyển thành response lỗi theo hợp đồng.
- Collection giữ thứ tự phần tử nếu thứ tự là một phần của yêu cầu.
- Link phản ánh đúng host và context path khi ứng dụng chạy sau reverse proxy.

Khi kiểm thử link phụ thuộc request context, hãy thực hiện qua request WebFlux thực tế bằng WebTestClient thay vì chỉ khởi tạo builder trong một unit test không có ngữ cảnh request.

## 13. Lỗi thường gặp khi tạo link với WebFlux

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng WebMvcLinkBuilder trong reactive controller | Không dùng đúng mô hình request reactive | Dùng WebFluxLinkBuilder |
| Coi kết quả builder là Link trực tiếp | Sai kiểu dữ liệu và không ghép được publisher | Xử lý `Mono<Link>` |
| Gọi `block()` trong request | Chặn event loop và giảm khả năng mở rộng | Dùng `map`, `flatMap`, `zip` |
| Gọi `subscribe()` trong controller | Response có thể hoàn tất trước công việc tạo link | Trả publisher từ controller |
| Dùng `Mono.zip` với publisher tùy chọn rỗng | Tuple không được phát ra | Xử lý publisher tùy chọn bằng `defaultIfEmpty` hoặc nhánh riêng |
| Dùng `flatMap` khi cần giữ thứ tự | Kết quả có thể phát ra khác thứ tự nguồn | Dùng `concatMap` hoặc `flatMapSequential` |
| Tạo link ngoài request context | Không xác định đúng host hoặc context path | Tạo link trong reactive chain của request |
| Cache link phụ thuộc request | Link có thể chứa host hoặc đường dẫn của request khác | Chỉ cache dữ liệu độc lập request |

## 14. Quy trình triển khai WebFlux links

Khi tạo link cho ứng dụng Spring WebFlux, hãy thực hiện theo trình tự:

1. Xác định controller và phương thức đích có mapping rõ ràng.
2. Dùng `WebFluxLinkBuilder.methodOn(...)` để tham chiếu phương thức và tham số.
3. Dùng `linkTo(...)` cùng `withSelfRel()` hoặc `withRel(...)` để tạo `Mono<Link>`.
4. Kết hợp publisher link với dữ liệu bằng `map`, `flatMap` hoặc `Mono.zip`.
5. Bọc DTO và link trong `EntityModel` hoặc `CollectionModel`.
6. Với `Flux`, chuyển đổi từng phần tử và gom kết quả có giới hạn hoặc dùng phân trang.
7. Giữ việc tạo link trong request reactive context; tránh `block()` và `subscribe()` trong controller.
8. Kiểm thử response hypermedia bằng `WebTestClient`, gồm link, media type và các nhánh nghiệp vụ.

WebFluxLinkBuilder đưa việc tạo liên kết vào đúng mô hình bất đồng bộ của Spring WebFlux. Khi coi mỗi link là một `Mono<Link>` và kết hợp nó bằng các toán tử Reactor, controller có thể trả về representation hypermedia hoàn chỉnh mà không chặn event loop. Điều đó giúp các link self, collection và related resources được tạo nhất quán theo mapping controller và ngữ cảnh request hiện tại.
