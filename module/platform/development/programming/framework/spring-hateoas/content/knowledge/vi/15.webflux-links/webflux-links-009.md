# MVC và WebFlux khác nhau

Spring HATEOAS hỗ trợ tạo hypermedia link cho cả Spring MVC và Spring WebFlux. Hai stack có thể dùng chung các kiểu representation như `RepresentationModel`, `EntityModel`, `CollectionModel` và `PagedModel`, nhưng cách tạo link và cách ghép kết quả vào controller khác nhau. Với Spring MVC, ứng dụng thường dùng `WebMvcLinkBuilder` để tạo `Link` đồng bộ. Với Spring WebFlux, ứng dụng dùng `WebFluxLinkBuilder`, vốn trả về `Mono<Link>` để có thể phân giải mapping và tạo link theo luồng reactive.

Điểm cần nhớ là chọn builder theo stack controller đang chạy. Không dùng `WebMvcLinkBuilder` trong WebFlux chỉ vì hai bên đều có annotation `@GetMapping`; cũng không dùng `WebFluxLinkBuilder` trong MVC. Phần còn lại của bài học giải thích khác biệt này và cách tổ chức assembler để response hypermedia hoạt động đúng với từng mô hình xử lý.

## 1. Spring MVC và Spring WebFlux là hai mô hình xử lý khác nhau

Spring MVC là web framework dựa trên Servlet API. Một request thường được xử lý theo mô hình imperative: handler gọi service, nhận kết quả và trả response. Ứng dụng có thể dùng các kiểu đồng bộ như DTO, `ResponseEntity<T>` và `List<T>`.

Spring WebFlux là web framework reactive dựa trên Reactive Streams và Reactor. Handler thường trả về `Mono<T>` cho kết quả không hoặc một phần tử, hoặc `Flux<T>` cho chuỗi nhiều phần tử. Pipeline có thể xử lý I/O không chặn khi các thành phần bên dưới cũng hỗ trợ non-blocking.

| Khía cạnh | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Mô hình xử lý | Imperative, thường đồng bộ | Reactive, bất đồng bộ và non-blocking khi toàn pipeline hỗ trợ |
| API web nền | Servlet API | Reactive Streams, Reactor và WebFlux runtime |
| Kiểu kết quả phổ biến | DTO, `ResponseEntity<T>`, `List<T>` | `Mono<T>`, `Flux<T>`, có thể bọc `ResponseEntity<T>` |
| Công cụ kiểm thử web | `MockMvc` | `WebTestClient` |
| Spring HATEOAS link builder | `WebMvcLinkBuilder` | `WebFluxLinkBuilder` |
| Kết quả tạo link | `Link` trực tiếp | `Mono<Link>` |

WebFlux thường được triển khai trên Netty, nhưng cũng có thể chạy trên một Servlet container tương thích. MVC thường chạy trên Servlet container. Điểm phân biệt quan trọng là mô hình xử lý và API được dùng, không chỉ là tên server.

Spring MVC cũng hỗ trợ một số kiểu trả về bất đồng bộ, bao gồm reactive types trong những tình huống nhất định. Điều đó không biến một ứng dụng MVC thành WebFlux. Cần xác định stack mà ứng dụng thực sự cấu hình và sử dụng.

## 2. Hai link builder trong Spring HATEOAS

Spring HATEOAS cung cấp builder riêng cho từng stack:

| Stack | Builder | Package |
| --- | --- | --- |
| Spring MVC | `WebMvcLinkBuilder` | `org.springframework.hateoas.server.mvc` |
| Spring WebFlux | `WebFluxLinkBuilder` | `org.springframework.hateoas.server.reactive` |

Với MVC, static import thường dùng:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
```

Với WebFlux:

```java
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;
```

Cả hai builder đều cho phép tham chiếu mapping của controller và handler thông qua `linkTo(...)` và `methodOn(...)`. Sự khác biệt thể hiện ở cách resolve mapping và kiểu kết quả. MVC tạo `Link` đồng bộ; WebFlux tạo `Mono<Link>` để có thể ghép vào reactive pipeline.

## 3. Tạo link trong Spring MVC

Ví dụ controller MVC trả về đối tượng đồng bộ:

```java
import java.util.UUID;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    Order get(@PathVariable UUID id) {
        return orderService.getRequired(id);
    }
}
```

Assembler MVC có thể tạo `EntityModel` và link ngay trong lời gọi:

```java
import org.springframework.hateoas.EntityModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

EntityModel<OrderRepresentation> toModel(Order order) {
    return EntityModel.of(
            OrderRepresentation.from(order),
            linkTo(methodOn(OrderController.class)
                    .one(order.getId())).withSelfRel());
}
```

`linkTo(methodOn(...))` tham chiếu handler `one(...)` để tạo URI dựa trên mapping. `withSelfRel()` gắn relation `self`. Kết quả là `EntityModel<OrderRepresentation>` có thể được controller trả về trực tiếp.

Ở MVC, lời gọi `toModel(...)` trả về model ngay lập tức. Controller có thể gọi service đồng bộ, chuyển đổi dữ liệu và trả response mà không cần bọc từng bước trong `Mono` hoặc `Flux`.

## 4. Tạo link trong Spring WebFlux

Controller WebFlux thường trả về reactive type. Ví dụ service trả `Mono<Order>`:

```java
import java.util.UUID;

import reactor.core.publisher.Mono;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    Mono<Order> one(@PathVariable UUID id) {
        return orderService.findById(id);
    }
}
```

Với WebFlux, link builder trả về `Mono<Link>`. Ta dùng `toMono()` và tiếp tục xử lý bằng các operator Reactor:

```java
import org.springframework.hateoas.EntityModel;
import reactor.core.publisher.Mono;

import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

Mono<EntityModel<OrderRepresentation>> toModel(Order order) {
    return linkTo(methodOn(OrderController.class)
            .one(order.getId()))
            .withSelfRel()
            .toMono()
            .map(selfLink -> EntityModel.of(
                    OrderRepresentation.from(order), selfLink));
}
```

`toMono()` cung cấp một `Mono<Link>`. `map(...)` chuyển link đã được tạo thành `EntityModel`. Toàn bộ quá trình vẫn là một pipeline reactive; không cần chặn thread để đợi link.

Controller có thể ghép service và assembler bằng `flatMap(...)`:

```java
@GetMapping("/{id}")
Mono<EntityModel<OrderRepresentation>> one(@PathVariable UUID id) {
    return orderService.findById(id)
            .flatMap(orderAssembler::toModel);
}
```

`flatMap(...)` phù hợp vì `orderAssembler.toModel(...)` trả về `Mono<EntityModel<...>>`. Nếu dùng `map(...)` trong trường hợp này, kết quả sẽ thành `Mono<Mono<EntityModel<...>>>`, tức một reactive type lồng nhau không mong muốn.

## 5. Kết hợp nhiều link trong WebFlux

Một representation có thể cần nhiều liên kết, chẳng hạn `self`, `customer` và `items`. Mỗi lần tạo link bằng `WebFluxLinkBuilder` trả về một `Mono<Link>`. Có thể kết hợp chúng bằng `Mono.zip(...)`:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import reactor.core.publisher.Mono;

import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

Mono<EntityModel<OrderRepresentation>> toModel(Order order) {
    Mono<Link> self = linkTo(methodOn(OrderController.class)
            .one(order.getId()))
            .withSelfRel()
            .toMono();

    Mono<Link> customer = linkTo(methodOn(CustomerController.class)
            .one(order.getCustomerId()))
            .withRel("customer")
            .toMono();

    Mono<Link> items = linkTo(methodOn(OrderItemController.class)
            .allForOrder(order.getId()))
            .withRel("items")
            .toMono();

    return Mono.zip(self, customer, items)
            .map(links -> EntityModel.of(
                    OrderRepresentation.from(order),
                    links.getT1(), links.getT2(), links.getT3()));
}
```

`Mono.zip(...)` đợi các kết quả link được phát ra rồi tạo model với ba link. Ví dụ giả định `CustomerController.one(...)` và `OrderItemController.allForOrder(...)` là các handler WebFlux có mapping tương ứng. Nếu một publisher không phát ra giá trị mà hoàn tất rỗng, `zip` cũng có thể hoàn tất mà không tạo model; cần chọn cách xử lý phù hợp nếu việc thiếu một link là tình huống hợp lệ.

Không gọi `.block()` để lấy từng link rồi tiếp tục tạo model. Việc block làm mất lợi ích của reactive pipeline và có thể gây deadlock hoặc cạn thread trong môi trường event-loop.

## 6. Xử lý collection với Flux và CollectionModel

Một service WebFlux có thể trả `Flux<Order>`. Để tạo collection hypermedia, chuyển từng phần tử qua assembler, thu thập model và thêm link ở cấp collection:

```java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import reactor.core.publisher.Mono;

import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

@GetMapping
Mono<CollectionModel<EntityModel<OrderRepresentation>>> all() {
    Mono<java.util.List<EntityModel<OrderRepresentation>>> content =
            orderService.findAll()
                    .flatMap(orderAssembler::toModel)
                    .collectList();

    Mono<Link> self = linkTo(methodOn(OrderController.class)
            .all())
            .withSelfRel()
            .toMono();

    return Mono.zip(content, self)
            .map(result -> CollectionModel.of(
                    result.getT1(), result.getT2()));
}
```

Trong ví dụ, `Flux<Order>` được chuyển thành `Flux<EntityModel<OrderRepresentation>>` bằng `flatMap(...)`, sau đó `collectList()` gom các phần tử thành một `Mono<List<...>>`. Self link cấp collection cũng là một `Mono<Link>`. `Mono.zip(...)` kết hợp hai kết quả thành `CollectionModel`.

Với collection rất lớn, `collectList()` có thể giữ toàn bộ phần tử trong bộ nhớ. Nên dùng phân trang hoặc giới hạn kết quả theo nghiệp vụ. Với WebFlux và Spring Data reactive, có thể thiết kế API dựa trên `Flux`, `Slice` hoặc cơ chế cursor phù hợp; đừng biến một stream không giới hạn thành một list lớn chỉ để tạo representation.

## 7. MVC và WebFlux: cùng representation, khác cách lắp ghép

Các kiểu representation của Spring HATEOAS có thể được dùng trong cả hai stack. Ví dụ `EntityModel<OrderRepresentation>` không thay đổi chỉ vì controller là MVC hay WebFlux. Khác biệt chủ yếu nằm ở cách tạo link và kiểu kết quả mà assembler/controller trả về.

| Thành phần | MVC | WebFlux |
| --- | --- | --- |
| Assembler đơn resource | `EntityModel<T>` | `Mono<EntityModel<T>>` |
| Tạo link | `Link` | `Mono<Link>` |
| Kết hợp kết quả | Gọi trực tiếp, tạo model | `map`, `flatMap`, `zip` |
| Collection | `CollectionModel<T>` | Thường `Mono<CollectionModel<T>>` sau khi gom stream |
| Controller | Trả model hoặc `ResponseEntity` | Trả `Mono<Model>`, `Flux<T>` hoặc reactive response |
| Test | `MockMvc` | `WebTestClient` |

Đây là quy ước tổ chức phổ biến, không phải mọi handler bắt buộc phải có đúng một kiểu trả về. Ví dụ MVC có thể trả `ResponseEntity<RepresentationModel<?>>`, còn WebFlux có thể trả `Mono<ResponseEntity<...>>` tùy nhu cầu HTTP.

## 8. Không trộn hai link builder

Các builder có tên và mục đích tương tự nhưng gắn với hạ tầng mapping khác nhau:

- `WebMvcLinkBuilder` làm việc với mapping của Spring MVC.
- `WebFluxLinkBuilder` làm việc với mapping của Spring WebFlux và cung cấp API reactive.

Nếu dùng builder không đúng stack, ứng dụng có thể không resolve được handler mapping hoặc không tạo được link theo request context. Hãy kiểm tra import trong assembler, đặc biệt khi IDE tự động import class cùng tên từ package khác.

Với ứng dụng có cả dependency MVC và WebFlux, cần xác định web application type thực tế mà Spring Boot khởi tạo. Không nên suy luận stack chỉ từ việc classpath có cả hai starter. Chọn builder dựa trên controller runtime đang phục vụ request.

## 9. Blocking I/O trong WebFlux

WebFlux chỉ phát huy lợi ích non-blocking khi toàn bộ đường xử lý tránh chặn thread xử lý event. Nếu controller trả `Mono` nhưng bên trong gọi repository JPA đồng bộ hoặc thực hiện I/O blocking trực tiếp, request vẫn có thể chặn event-loop.

Với WebFlux, nên ưu tiên các client và data access API reactive, chẳng hạn WebClient và reactive database driver khi phù hợp. Nếu phải tích hợp thư viện blocking, cần cô lập thao tác đó trên scheduler phù hợp thay vì chạy trực tiếp trên event-loop. Không dùng `.block()` trong handler hoặc assembler chỉ để biến một `Mono<Link>` thành `Link` đồng bộ.

## 10. Kiểm thử MVC và WebFlux

Với MVC, `MockMvc` có thể xác nhận link được serialize trong HAL:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists());
```

Với WebFlux, dùng `WebTestClient`:

```java
webTestClient.get()
        .uri("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$._links.self.href").exists();
```

Test WebFlux có thể chạy với application context hoặc bind trực tiếp vào controller/router theo cấu hình test. Cần bảo đảm HAL encoder/decoder và các bean cần thiết được cấu hình giống ứng dụng. Ví dụ dùng `MediaTypes.HAL_JSON` để tránh gõ sai media type; import:

```java
import org.springframework.hateoas.MediaTypes;
```

Ngoài việc kiểm tra link tồn tại, nên xác nhận:

- `href` phản ánh mapping controller và path variable đúng.
- Relation `self`, `customer`, `items` có tên và ý nghĩa nhất quán.
- Link ở cấp collection khác với link của từng item.
- WebFlux assembler trả kết quả reactive mà không block.
- Filter, sort và page được giữ trong link phân trang nếu endpoint hỗ trợ.
- Response dùng đúng media type mà client yêu cầu.
- Các trường hợp resource không tồn tại hoặc không có quyền được xử lý đúng.

## 11. Lỗi thường gặp

**Dùng `WebMvcLinkBuilder` trong WebFlux:** hai stack có builder riêng. Dùng `WebFluxLinkBuilder` cho controller WebFlux.

**Quên gọi `toMono()`:** WebFlux builder trả một builder có bước chuyển thành `Mono<Link>`. Cần đưa publisher vào pipeline trước khi tạo representation.

**Dùng `map` thay cho `flatMap`:** khi hàm chuyển đổi trả `Mono<Model>`, dùng `flatMap` để tránh tạo `Mono<Mono<Model>>`.

**Gọi `.block()` để lấy link:** thao tác này chặn pipeline và có thể gây vấn đề trên event-loop. Kết hợp publisher bằng `map`, `flatMap` hoặc `zip`.

**Giả định trả `Mono` là đã non-blocking:** service hoặc driver blocking vẫn có thể chặn thread. Chọn reactive I/O hoặc cô lập phần blocking.

**Nhầm kiểu representation giữa hai stack:** `EntityModel`, `CollectionModel` và `PagedModel` có thể dùng chung; khác biệt chính là cách tạo link và cách bọc kết quả trong reactive type.

## 12. Checklist lựa chọn và triển khai

- Xác định controller đang chạy trên Spring MVC hay Spring WebFlux.
- MVC dùng `WebMvcLinkBuilder`; WebFlux dùng `WebFluxLinkBuilder`.
- MVC tạo `Link` đồng bộ; WebFlux gọi `toMono()` và ghép `Mono<Link>` vào pipeline.
- Dùng `flatMap` khi assembler trả reactive type; dùng `map` khi chuyển đổi đồng bộ.
- Kết hợp nhiều link reactive bằng `Mono.zip(...)` khi cần.
- Không gọi `.block()` trong reactive request pipeline.
- Dùng chung representation HATEOAS phù hợp như `EntityModel` và `CollectionModel`.
- Kiểm tra relation, URI, context path và media type trong response.
- Dùng `MockMvc` cho MVC và `WebTestClient` cho WebFlux.
- Tránh I/O blocking trực tiếp trên event-loop của WebFlux.

Spring HATEOAS giữ nguyên mục tiêu công bố resource và quan hệ hypermedia trong cả MVC lẫn WebFlux. Khi chọn đúng link builder và ghép kết quả theo mô hình xử lý của stack, ứng dụng có thể tạo representation nhất quán mà vẫn giữ được đặc tính đồng bộ của MVC hoặc reactive của WebFlux.
