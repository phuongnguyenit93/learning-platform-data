# Path variable reactive

Trong Spring WebFlux, `@PathVariable` lấy một giá trị từ path của request và đưa vào tham số phương thức controller. Ví dụ route `/orders/{id}` nhận mã đơn hàng từ URL. Khi kết hợp Spring HATEOAS, giá trị path variable đó cũng được dùng để tạo link tới endpoint tương ứng.

Điểm khác biệt khi làm việc với WebFlux là quá trình dựng link có tính reactive. `WebFluxLinkBuilder` tạo link thông qua `Mono<Link>`, vì nó cần ngữ cảnh `ServerWebExchange` để xác định URI gốc của request. Do đó, hãy ghép việc tạo link vào pipeline Reactor bằng `flatMap`, `map` hoặc `Mono.zip`; không chặn pipeline bằng `block()`.

## Path variable trong WebFlux controller

Path variable là một phần của path, thường dùng để xác định một tài nguyên cụ thể:

```java
import java.util.UUID;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    Mono<OrderRepresentation> one(@PathVariable("id") UUID id) {
        return orderService.findById(id);
    }
}
```

Với request `GET /orders/8f2c...`, Spring WebFlux lấy đoạn path tương ứng với `{id}`, chuyển đổi sang `UUID` và truyền vào tham số `id`. Tên trong `@PathVariable("id")` phải khớp tên biến trong mapping. Có thể bỏ tên tường minh nếu tên tham số Java được giữ trong metadata biên dịch, nhưng chỉ định rõ tên giúp hợp đồng dễ đọc và ít phụ thuộc cấu hình build.

`@PathVariable` nhận giá trị đã được resolve trong quá trình xử lý request. Trong controller reactive, tham số này thường là kiểu Java thông thường như `UUID`, `Long` hoặc `String`; phần xử lý I/O và truy vấn dữ liệu mới trả về `Mono<T>` hoặc `Flux<T>`. Không cần bọc path variable vào `Mono` chỉ vì endpoint đang dùng WebFlux.

Path variable khác query parameter:

| Loại | Ví dụ | Công dụng |
| --- | --- | --- |
| Path variable | `/orders/42` | Xác định tài nguyên đơn hàng `42` |
| Query parameter | `/orders?status=PENDING` | Lọc hoặc điều chỉnh tập kết quả |

Một URI có thể kết hợp cả hai, ví dụ `/customers/7/orders?status=PENDING`: `7` xác định khách hàng, còn `status` lọc collection đơn hàng của khách hàng đó.

## Tạo link reactive với WebFluxLinkBuilder

Spring HATEOAS cung cấp `WebFluxLinkBuilder` trong package `org.springframework.hateoas.server.reactive`. Đây là builder dành cho Spring WebFlux. Nó đọc mapping của controller và các giá trị tham số để tạo link; `methodOn(...)` tạo một lời gọi mô phỏng nhằm ghi nhận phương thức và đối số, chứ không thực thi logic controller.

Các phương thức thường dùng:

| API | Vai trò |
| --- | --- |
| `methodOn(Controller.class).method(args...)` | Mô tả phương thức controller và các đối số cần đưa vào URI |
| `linkTo(invocation)` | Tạo builder từ lời gọi mô phỏng |
| `withSelfRel()` | Gắn relation `self` |
| `withRel(...)` | Gắn relation khác |
| `andAffordance(invocation)` | Gắn mô tả tương tác từ một phương thức controller khác |
| `toMono()` | Chuyển kết quả link thành `Mono<Link>` để ghép vào pipeline |

Ví dụ tạo self link cho một đơn hàng:

```java
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

import java.util.UUID;

import org.springframework.hateoas.Link;
import reactor.core.publisher.Mono;

Mono<Link> selfLink = linkTo(methodOn(OrderController.class).one(orderId))
    .withSelfRel()
    .toMono();
```

`orderId` được dùng làm giá trị cho path variable trong mapping `/{id}`. `toMono()` trả về `Mono<Link>` thay vì một `Link` đồng bộ. Khi có request WebFlux đang được xử lý, builder lấy `ServerWebExchange` từ Reactor Context để dựng URI đầy đủ theo request hiện tại.

Nếu gọi builder ngoài reactive request context, builder có thể chỉ tạo URI tương đối. Trong trường hợp đã có `ServerWebExchange`, có thể truyền exchange tường minh vào overload `linkTo(invocation, exchange)` để xác định URI gốc.

## Kết hợp path variable với dữ liệu reactive

Giả sử repository trả `Mono<Order>` và controller cần trả `EntityModel<OrderRepresentation>` có self link. Có thể kết hợp việc tìm đơn hàng và dựng link trong cùng pipeline:

```java
import java.util.UUID;

import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;
import reactor.core.publisher.Mono;

@GetMapping("/{id}")
Mono<EntityModel<OrderRepresentation>> one(@PathVariable("id") UUID id) {

    return orderRepository.findById(id)
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(HttpStatus.NOT_FOUND)))
        .flatMap(order -> linkTo(
                methodOn(OrderController.class).one(order.getId()))
            .withSelfRel()
            .toMono()
            .map(self -> EntityModel.of(toRepresentation(order), self)));
}
```

Ví dụ giả định `orderRepository.findById(id)` trả về `Mono<Order>`, `toRepresentation(order)` chuyển domain object thành DTO, và `OrderController.one(UUID)` là mapping của tài nguyên. Nếu không tìm thấy đơn hàng, `switchIfEmpty` phát ra lỗi 404. Nếu tìm thấy, `flatMap` tiếp tục bằng thao tác dựng link reactive; sau khi link sẵn sàng, `map` tạo `EntityModel`.

Không gọi `.block()` để lấy `Link` bên trong controller. `block()` có thể chặn thread xử lý request và làm mất lợi ích của mô hình non-blocking. Hãy giữ link dưới dạng `Mono<Link>` và kết hợp nó với dữ liệu bằng toán tử Reactor.

## Tạo nhiều link và affordance

Một representation có thể chứa nhiều link, ví dụ `self`, `orders` và `cancel`. Có thể dựng chúng đồng thời rồi ghép vào `EntityModel`:

```java
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import reactor.core.publisher.Mono;

Mono<EntityModel<OrderRepresentation>> toModel(Order order) {

    Mono<Link> self = linkTo(methodOn(OrderController.class).one(order.getId()))
        .withSelfRel()
        .toMono();

    Mono<Link> collection = linkTo(methodOn(OrderController.class).all())
        .withRel("orders")
        .toMono();

    return Mono.zip(self, collection)
        .map(links -> EntityModel.of(
            toRepresentation(order), links.getT1(), links.getT2()));
}
```

`Mono.zip` chờ cả hai link hoàn tất rồi phát một cặp kết quả. `getT1()` là self link, `getT2()` là link collection. Có thể dùng `EntityModel.of(content, links)` với danh sách link khi số link được tạo động.

Nếu muốn công bố affordance cho thao tác hủy, có thể gắn một lời gọi mô phỏng khác vào link:

```java
Mono<Link> selfWithCancel = linkTo(
        methodOn(OrderController.class).one(order.getId()))
    .withSelfRel()
    .andAffordance(methodOn(OrderController.class).cancel(order.getId()))
    .toMono();
```

`cancel(id)` cần là một mapping controller thực tế, ví dụ `@PostMapping("/{id}/cancel")`. Affordance cung cấp metadata về tương tác; việc nó được biểu diễn ra sao phụ thuộc media type hypermedia. Link và affordance không thay thế kiểm tra quyền hoặc trạng thái nghiệp vụ ở endpoint.

## Path variable lồng nhau

API có thể dùng nhiều path variable để biểu diễn quan hệ tài nguyên. Ví dụ `/customers/{customerId}/orders/{orderId}` xác định một đơn hàng thuộc một khách hàng:

```java
@RestController
@RequestMapping("/customers/{customerId}/orders")
class CustomerOrderController {

    @GetMapping("/{orderId}")
    Mono<EntityModel<OrderRepresentation>> one(
            @PathVariable UUID customerId,
            @PathVariable UUID orderId) {

        return orderRepository.findByCustomerIdAndId(customerId, orderId)
            .flatMap(order -> linkTo(methodOn(CustomerOrderController.class)
                    .one(customerId, orderId))
                .withSelfRel()
                .toMono()
                .map(self -> EntityModel.of(toRepresentation(order), self)));
    }
}
```

Khi gọi `methodOn(...).one(customerId, orderId)`, các đối số tương ứng với hai path variable được đưa vào URI theo mapping của controller. Cần kiểm tra quan hệ giữa chúng trong truy vấn: không được chỉ tìm `orderId` rồi trả về một đơn hàng thuộc khách hàng khác khi URL chứa `customerId` không khớp.

Nếu endpoint cần tạo link tới tài nguyên khách hàng hoặc collection đơn hàng của khách hàng, hãy dùng đúng mapping và relation cho từng đích. Tránh tạo URL bằng cách nối `customerId` và `orderId` thành chuỗi thủ công.

## Chuyển đổi và mã hóa path variable

Spring WebFlux chuyển giá trị path segment sang kiểu tham số thông qua cơ chế conversion. Nếu client gửi UUID sai định dạng cho endpoint nhận `UUID`, request thường bị từ chối với lỗi chuyển đổi trước khi logic truy vấn được thực hiện. Có thể dùng `String` nếu định dạng định danh do ứng dụng quản lý riêng, nhưng cần validate rõ ràng.

Giá trị path variable cũng phải được mã hóa đúng khi tạo URI. Dùng `WebFluxLinkBuilder` với đối số cho `methodOn(...)` giúp builder xử lý URI theo mapping và các quy tắc URI của Spring. Không tự nối một chuỗi chứa dấu `/`, `?`, `#` hoặc ký tự dành riêng vào path segment. Nếu một định danh có thể chứa dấu gạch chéo, hãy thiết kế định dạng ID phù hợp hoặc mã hóa nó thành một segment an toàn trước khi dùng làm path variable.

Không nhầm path variable với URI template variable. `@PathVariable("id")` khai báo biến trên route server; `methodOn(...).one(id)` cung cấp giá trị cụ thể để tạo link. Còn một link template như `/orders{/id}` công bố một biến chưa được điền để client mở rộng sau này.

## Tạo link khi cần ServerWebExchange tường minh

Thông thường, `WebFluxLinkBuilder` lấy `ServerWebExchange` từ Reactor Context. Nếu một thành phần có sẵn exchange và muốn truyền rõ ràng, có thể dùng overload tương ứng:

```java
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

import java.util.UUID;

import org.springframework.hateoas.Link;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

Mono<Link> selfLink(UUID id, ServerWebExchange exchange) {
    return linkTo(methodOn(OrderController.class).one(id), exchange)
        .withSelfRel()
        .toMono();
}
```

Đây là cách hữu ích khi logic dựng representation được gọi từ một thành phần không còn giữ ngữ cảnh Reactor ban đầu nhưng vẫn nhận được exchange. Không lưu `ServerWebExchange` vào biến dùng chung hoặc giữ nó sau vòng đời request; exchange thuộc về request đang xử lý.

## WebFlux và WebMvc dùng builder khác nhau

Spring HATEOAS có builder riêng cho hai mô hình web:

| Mô hình | Builder | Kết quả tạo link |
| --- | --- | --- |
| Spring MVC | `WebMvcLinkBuilder` | `Link` đồng bộ |
| Spring WebFlux | `WebFluxLinkBuilder` | `Mono<Link>` reactive |

Không dùng `WebMvcLinkBuilder` trong controller WebFlux chỉ vì cú pháp `linkTo(methodOn(...))` trông tương tự. `WebFluxLinkBuilder` có thể lấy request context từ Reactor Context và cần được ghép vào pipeline. Nếu dùng sai builder, link có thể thiếu base URI hoặc không phản ánh đúng request hiện tại.

Trong Spring Boot, bảo đảm ứng dụng có Spring WebFlux và Spring HATEOAS tương thích với phiên bản Spring Boot đang dùng. Controller WebFlux có thể trả trực tiếp kiểu dựa trên `RepresentationModel`, hoặc bọc trong `Mono`/`Flux`; Spring HATEOAS tích hợp với WebFlux để serialize hypermedia representation. Với HAL JSON, client thường gửi `Accept: application/hal+json`.

## Kiểm thử path variable và self link

Nên kiểm thử response HTTP thực tế để xác nhận path variable được bind đúng và link trỏ tới đúng tài nguyên. Với `WebTestClient`:

```java
import static org.hamcrest.Matchers.endsWith;

import org.springframework.hateoas.MediaTypes;

webTestClient.get()
    .uri("/orders/{id}", orderId)
    .accept(MediaTypes.HAL_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaTypes.HAL_JSON)
    .expectBody()
    .jsonPath("$.id").isEqualTo(orderId.toString())
    .jsonPath("$._links.self.href").value(endsWith("/orders/" + orderId));
```

Test nên bao gồm các trường hợp:

- ID hợp lệ và tài nguyên tồn tại: response có dữ liệu và self link chứa đúng ID.
- ID hợp lệ nhưng không có tài nguyên: response trả 404 theo chính sách endpoint.
- ID sai định dạng: request bị từ chối khi chuyển đổi path variable.
- Tài nguyên lồng nhau: `customerId` và `orderId` phải cùng thuộc một quan hệ hợp lệ.
- URI chạy sau reverse proxy hoặc có context path: self link phải dùng base URI công khai đã cấu hình.

Nếu endpoint trả collection bằng `Flux`, kiểm tra từng phần tử có self link đúng và link collection cũng trỏ tới endpoint tương ứng. Không chỉ kiểm tra số lượng phần tử; cần kiểm tra relation và `href` trong representation HAL.

## Lỗi thường gặp

- **Dùng sai builder:** dùng `WebMvcLinkBuilder` trong WebFlux và nhận link không có request context đúng.
- **Quên `toMono()`:** không đưa kết quả `WebFluxLink` về `Mono<Link>` để ghép vào pipeline.
- **Gọi `block()`:** chặn luồng reactive chỉ để lấy link đồng bộ.
- **Sai tên path variable:** mapping khai báo `{orderId}` nhưng annotation hoặc tham số dùng tên khác.
- **Truy vấn không kiểm tra quan hệ lồng nhau:** bỏ qua `customerId` có thể làm lộ tài nguyên thuộc khách hàng khác.
- **Tự nối URL:** dễ tạo URI sai khi có context path, reverse proxy hoặc ký tự đặc biệt.
- **Coi link là quyền truy cập:** endpoint vẫn phải xác thực và phân quyền khi nhận request.

`@PathVariable` trong WebFlux giúp controller nhận định danh từ path; `WebFluxLinkBuilder` dùng chính giá trị đó để tạo link một cách reactive. Khi giữ `Mono`/`Flux` xuyên suốt pipeline, dùng `methodOn(...)` theo mapping thật và kiểm thử HAL response qua `WebTestClient`, API có thể công bố self link chính xác mà không chặn luồng xử lý bất đồng bộ.

## Tài liệu tham khảo

- [Spring HATEOAS API – WebFluxLinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/WebFluxLinkBuilder.html)
- [Spring HATEOAS – WebFlux support and reactive link building](https://spring.io/blog/2019/03/05/spring-hateoas-1-0-m1-released/)
