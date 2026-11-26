# Reactive controller link

Trong Spring WebFlux, controller thường trả về `Mono<T>` hoặc `Flux<T>` thay vì một đối tượng đồng bộ. Khi kết hợp với Spring HATEOAS, các link cũng cần được tạo theo luồng reactive để không chặn event loop và giữ được ngữ cảnh của request hiện tại. Spring HATEOAS cung cấp `WebFluxLinkBuilder` cho mục đích này. Khác với `WebMvcLinkBuilder`, API WebFlux trả kết quả link dưới dạng `Mono<Link>` và cung cấp `toMono()` để đưa việc tạo link vào pipeline.

Ví dụ, endpoint đọc một đơn hàng trả về `Mono<EntityModel<OrderDto>>`. Service đọc đơn hàng từ reactive repository; assembler tạo self link và link đến collection dòng hàng; controller kết hợp các kết quả đó rồi trả model cho WebFlux serialize thành HAL. Client nhận được cả dữ liệu và các URI để tiếp tục điều hướng.

## Vì sao link builder trong WebFlux có dạng reactive?

Trong Spring MVC, request được xử lý theo mô hình Servlet và `WebMvcLinkBuilder` có thể xây URI đồng bộ từ mapping controller. WebFlux dùng reactive pipeline, thường chạy trên event loop và truyền ngữ cảnh request qua Reactor Context. Việc phân giải link có thể cần thông tin của request hiện tại, vì vậy `WebFluxLinkBuilder` cung cấp kết quả bất đồng bộ.

| Thành phần | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Link builder | `WebMvcLinkBuilder` | `WebFluxLinkBuilder` |
| Kiểu kết quả tạo link | `Link` đồng bộ | `Mono<Link>` |
| Cách đưa vào xử lý | Gọi trực tiếp trong luồng đồng bộ | Dùng `toMono()` rồi compose bằng `map`, `flatMap`, `zip` hoặc operator phù hợp |
| Controller điển hình | Trả `EntityModel<T>` | Trả `Mono<EntityModel<T>>` hoặc `Flux<...>` tùy endpoint |

Không dùng `WebMvcLinkBuilder` trong controller WebFlux chỉ vì cú pháp trông tương tự. Hãy dùng `WebFluxLinkBuilder` để tạo link trong reactive request context. Cũng không gọi `block()` hoặc `subscribe()` bên trong controller để chờ link; việc đó phá vỡ cách framework điều phối subscription và có thể làm chặn event loop.

## Khai báo dependency và bật hypermedia

Một ứng dụng reactive dùng Spring Boot cần WebFlux và Spring HATEOAS. Với Gradle Kotlin DSL, dependency thường được khai báo như sau:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-hateoas")
}
```

Dùng phiên bản do Spring Boot dependency management quản lý để các thành phần Spring tương thích với nhau. Ứng dụng cần chạy trên WebFlux stack; tránh vô tình đưa cả starter Spring MVC vào classpath nếu không có chủ đích chuyển đổi ứng dụng sang mô hình Servlet.

Với cấu hình Spring cần bật hypermedia thủ công, có thể khai báo HAL:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {
}
```

Annotation này đăng ký hỗ trợ hypermedia tương ứng với loại ứng dụng và định dạng được chọn. Trong Spring Boot, hãy kiểm tra auto-configuration của phiên bản đang dùng trước khi thêm cấu hình tường minh để tránh đăng ký trùng. Client yêu cầu HAL bằng `Accept: application/hal+json`; response cần có `Content-Type` tương thích với media type đó.

## Dùng WebFluxLinkBuilder để tạo self link

`WebFluxLinkBuilder` nằm trong package `org.springframework.hateoas.server.reactive`. Cách gọi thường dùng là mô tả method controller bằng `methodOn(...)`, chuyển lời gọi đó thành link bằng `linkTo(...)`, đặt relation và kết thúc bằng `toMono()`:

```java
import java.util.UUID;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.reactive.WebFluxLinkBuilder;
import reactor.core.publisher.Mono;

Mono<Link> selfLink(UUID id) {
    return WebFluxLinkBuilder.linkTo(
            WebFluxLinkBuilder.methodOn(OrderController.class).one(id))
            .withSelfRel()
            .toMono();
}
```

`methodOn(OrderController.class).one(id)` mô tả method đọc chi tiết đơn hàng cùng tham số định tuyến. `linkTo(...)` dùng mapping của controller để tạo URI. `withSelfRel()` đặt relation `self`; `toMono()` trả link dưới dạng publisher để pipeline tiếp tục xử lý.

Việc tạo link nên diễn ra trong request pipeline đang xử lý. Khi `toMono()` được subscribe bởi WebFlux, builder có thể dùng ngữ cảnh reactive của request để tạo URI phù hợp với host, context path và cấu hình hiện tại. Không lấy một `Mono<Link>` rồi tự `block()` ở thread xử lý request.

## Xây assembler reactive cho một resource

Các model HATEOAS như `EntityModel<T>` vẫn là các đối tượng dữ liệu thông thường. Phần reactive nằm ở thao tác lấy entity và tạo link. Assembler có thể trả `Mono<EntityModel<OrderDto>>` để controller ghép trực tiếp vào pipeline:

DTO response có thể là một record nhỏ, tách khỏi domain entity:

```java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderDto(UUID id, String status, BigDecimal totalAmount) {
}
```

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.reactive.WebFluxLinkBuilder;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
class ReactiveOrderAssembler {

    Mono<EntityModel<OrderDto>> toModel(Order order) {
        OrderDto dto = new OrderDto(
                order.getId(),
                order.getStatus().name(),
                order.getTotalAmount());

        Mono<Link> self = WebFluxLinkBuilder.linkTo(
                WebFluxLinkBuilder.methodOn(OrderController.class)
                        .one(order.getId()))
                .withSelfRel()
                .toMono();

        Mono<Link> items = WebFluxLinkBuilder.linkTo(
                WebFluxLinkBuilder.methodOn(OrderItemController.class)
                        .allForOrder(order.getId()))
                .withRel("items")
                .toMono();

        return Mono.zip(self, items)
                .map(links -> EntityModel.of(dto, links.getT1(), links.getT2()));
    }
}
```

`OrderDto` là DTO response; `Order` là domain object. Ví dụ giả định `OrderController.one(UUID)` trả về `Mono<EntityModel<OrderDto>>` và `OrderItemController.allForOrder(UUID)` là endpoint collection dòng hàng. Hai link độc lập được tạo đồng thời bằng `Mono.zip`. Khi cả hai link sẵn sàng, assembler tạo `EntityModel` chứa dữ liệu và hai relation.

Nếu chỉ có một link, không cần dùng `Mono.zip`; có thể gọi `toMono().map(link -> EntityModel.of(dto, link))`. Nếu một link phụ thuộc vào kết quả của link khác, dùng `flatMap` để biểu diễn thứ tự phụ thuộc. Chọn operator theo quan hệ dữ liệu, không lồng `subscribe()` thủ công.

## Kết hợp assembler với reactive controller

Service trong WebFlux thường trả `Mono<Order>` cho một entity và `Flux<Order>` cho một luồng nhiều entity. Controller có thể compose các publisher đó cùng assembler:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService service;
    private final ReactiveOrderAssembler assembler;

    OrderController(OrderService service, ReactiveOrderAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    Mono<EntityModel<OrderDto>> one(@PathVariable UUID id) {
        return service.findById(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)))
                .flatMap(assembler::toModel);
    }
}
```

`switchIfEmpty` chuyển trường hợp không tìm thấy đơn hàng thành HTTP 404. `flatMap` gọi assembler vì `toModel` trả về `Mono<EntityModel<OrderDto>>`. Nếu dùng `map(assembler::toModel)`, kết quả sẽ thành `Mono<Mono<EntityModel<...>>>`, là publisher lồng nhau và không phải kiểu response mong muốn.

Controller trả publisher để framework subscribe và ghi response. Nó không tự gọi `subscribe()`; cũng không cần chờ kết quả bằng `block()`. Khi publisher hoàn tất, WebFlux serialize model qua codec phù hợp.

## Trả collection từ Flux

Với endpoint collection, mỗi entity cần được chuyển thành một resource model. `concatMap` thực hiện phép chuyển đổi reactive theo thứ tự nguồn; sau đó `collectList()` tạo danh sách để bọc trong `CollectionModel`:

```java
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/order-catalog")
class OrderCollectionController {

    private final OrderService service;
    private final ReactiveOrderAssembler assembler;

    OrderCollectionController(OrderService service, ReactiveOrderAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    Mono<CollectionModel<EntityModel<OrderDto>>> all() {
        Mono<Link> self = linkTo(methodOn(OrderCollectionController.class).all())
                .withSelfRel()
                .toMono();

        Mono<java.util.List<EntityModel<OrderDto>>> orders = service.findAll()
                .concatMap(assembler::toModel)
                .collectList();

        return Mono.zip(orders, self)
                .map(result -> CollectionModel.of(result.getT1(), result.getT2()));
    }
}
```

`Flux<Order>` được chuyển thành `Flux<EntityModel<OrderDto>>` bằng `concatMap`, rồi gom thành `List` để tạo `CollectionModel`. Self link của collection được tạo thành `Mono<Link>` và ghép với danh sách bằng `Mono.zip`. Nếu không cần giữ thứ tự nguồn và muốn cho phép nhiều phép tạo model chạy đồng thời, có thể cân nhắc `flatMap` hoặc `flatMapSequential` với giới hạn concurrency phù hợp.

`collectList()` lưu toàn bộ kết quả trong bộ nhớ. Với collection lớn, không nên phát toàn bộ dữ liệu thành một HAL document duy nhất; hãy dùng phân trang, giới hạn kích thước hoặc endpoint con để kiểm soát payload. Reactive không tự làm cho một collection không giới hạn trở nên an toàn về bộ nhớ.

## Dùng URI và query parameter trong reactive link

`WebFluxLinkBuilder` cũng tạo link theo mapping có path variable và query parameter. Ví dụ endpoint tìm kiếm có thể nhận từ khóa và trang:

```java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.server.reactive.WebFluxLinkBuilder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import reactor.core.publisher.Mono;

@GetMapping(value = "/search", produces = MediaTypes.HAL_JSON_VALUE)
Mono<CollectionModel<EntityModel<OrderDto>>> search(
        @RequestParam("q") String query,
        @RequestParam(name = "page", defaultValue = "0") int page) {
    Mono<List<EntityModel<OrderDto>>> orders = service.search(query, page)
            .concatMap(assembler::toModel)
            .collectList();

    Mono<Link> self = WebFluxLinkBuilder.linkTo(
            WebFluxLinkBuilder.methodOn(OrderCollectionController.class)
                    .search(query, page))
            .withSelfRel()
            .toMono();

    return Mono.zip(orders, self)
            .map(result -> CollectionModel.of(result.getT1(), result.getT2()));
}
```

Khi tạo link:

```java
Mono<Link> searchLink = WebFluxLinkBuilder.linkTo(
        WebFluxLinkBuilder.methodOn(OrderCollectionController.class)
                .search(query, page))
        .withRel("search")
        .toMono();
```

Builder dùng mapping và giá trị tham số để dựng URI, giúp giữ tên query parameter theo khai báo controller. Với link phân trang, hãy giữ lại filter và sort hiện tại, chỉ thay giá trị page cần điều hướng. Nếu client cần tự cung cấp query sau đó, có thể công bố URI template với các biến query thay vì một URI đã điền giá trị.

## Xử lý lỗi trong pipeline

Reactive controller cần xử lý trường hợp publisher rỗng và lỗi theo cách nhất quán với HTTP API. Ví dụ:

```java
return service.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND)))
        .flatMap(assembler::toModel)
        .onErrorMap(OrderAccessDeniedException.class,
                ex -> new ResponseStatusException(HttpStatus.FORBIDDEN));
```

Không tạo link hành động khi nghiệp vụ không cho phép thao tác hoặc người dùng hiện tại không có quyền. Tuy vậy, sự vắng mặt của link không thay thế kiểm tra quyền tại endpoint. Khi client theo link, server vẫn phải xác thực, phân quyền và kiểm tra trạng thái hiện tại.

Nếu quá trình tạo một link thất bại, publisher chứa model cũng thất bại. Hãy để lỗi đi qua pipeline tới cơ chế xử lý lỗi WebFlux đã cấu hình, hoặc chuyển nó thành response lỗi phù hợp. Không bắt lỗi rồi âm thầm trả model thiếu self link nếu self link là phần bắt buộc của hợp đồng.

## Kiểm thử bằng WebTestClient

Với ứng dụng WebFlux, `WebTestClient` là lựa chọn tích hợp phù hợp để kiểm tra controller reactive và response HAL. Ví dụ:

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderWebFluxControllerTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void detailReturnsHalWithSelfAndItemsLinks() {
        UUID id = UUID.fromString("7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042");

        webTestClient.get()
                .uri("/api/orders/{id}", id)
                .accept(MediaTypes.HAL_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaTypes.HAL_JSON)
                .expectBody()
                .jsonPath("$._links.self.href").exists()
                .jsonPath("$._links.items.href").exists();
    }
}
```

Ví dụ giả định test context đã nạp cấu hình WebFlux/HAL, fixture có đơn hàng với UUID đã nêu và service trả về dữ liệu tương ứng. Trong test thực tế, chỉ giữ các import cần dùng; phần code tập trung vào request và các assertion JSONPath. Có thể kiểm thử thêm response 404 khi repository trả `Mono.empty()` và collection rỗng khi service trả `Flux.empty()`.

Một số điều cần kiểm tra trong test:

- Response có `Content-Type` tương thích với `application/hal+json`.
- Self link và các relation cần thiết xuất hiện trong `_links`.
- Href chứa đúng path variable và query parameter.
- Publisher rỗng tạo HTTP 404 với endpoint chi tiết.
- Collection rỗng vẫn trả representation hợp lệ và self link của collection.
- Các link phụ thuộc quyền chỉ xuất hiện khi người dùng được phép thực hiện thao tác.

## Lỗi thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `WebMvcLinkBuilder` trong WebFlux | Phụ thuộc request context Servlet hoặc tạo URI không phù hợp. | Dùng `WebFluxLinkBuilder`. |
| Quên `toMono()` | Không đưa kết quả link vào reactive pipeline. | Kết thúc builder bằng `toMono()` và compose publisher. |
| Dùng `map` cho hàm trả `Mono` | Tạo publisher lồng nhau như `Mono<Mono<T>>`. | Dùng `flatMap` hoặc `Mono.zip` tùy quan hệ. |
| Gọi `block()` hoặc `subscribe()` trong controller | Chặn event loop hoặc tách subscription khỏi vòng đời response. | Trả `Mono`/`Flux` cho framework quản lý. |
| Tạo link ngoài request context | Không có đủ thông tin để dựng URI theo request hiện tại. | Tạo link trong pipeline của request WebFlux. |
| `collectList()` với collection không giới hạn | Dùng nhiều bộ nhớ và tạo response quá lớn. | Phân trang hoặc giới hạn số phần tử. |
| Không cấu hình HAL codec | Response không được serialize theo media type mong đợi. | Kiểm tra starter và hypermedia configuration. |

## Nguyên tắc thiết kế

- Dùng `WebFluxLinkBuilder` cho controller reactive và kết thúc bằng `toMono()`.
- Kết hợp link với dữ liệu bằng `map`, `flatMap`, `zip` hoặc operator phù hợp; tránh nested publisher.
- Để WebFlux quản lý subscription bằng cách trả `Mono`/`Flux` từ controller.
- Tạo link trong reactive request context để giữ đúng host, context path và mapping.
- Dùng assembler trả publisher khi việc tạo resource cần link bất đồng bộ.
- Giới hạn collection, phân trang dữ liệu lớn và giữ thứ tự khi client phụ thuộc thứ tự item.
- Kiểm thử media type, relation, href và các trường hợp publisher rỗng bằng `WebTestClient`.

Spring HATEOAS trong WebFlux cho phép controller reactive trả về representation giàu liên kết mà vẫn giữ luồng xử lý bất đồng bộ. Khi link builder, assembler và controller cùng tham gia một reactive pipeline, server có thể công bố self link và các quan hệ điều hướng theo mapping hiện tại mà không chặn event loop.
