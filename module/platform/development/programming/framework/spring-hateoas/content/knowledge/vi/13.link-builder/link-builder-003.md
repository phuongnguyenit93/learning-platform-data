# methodOn

Khi một API trả về đơn hàng, response thường cần link `self` để mở lại chính đơn hàng đó. Đường dẫn chi tiết có thể được ánh xạ bằng `@GetMapping("/{id}")`, còn controller có thể được đổi prefix trong tương lai. Nếu viết URL bằng cách nối chuỗi, logic tạo link sẽ phải cập nhật mỗi khi mapping thay đổi.

Spring HATEOAS cung cấp `methodOn(...)` để tham chiếu một phương thức controller theo mapping đã khai báo. Khi kết hợp với `linkTo(...)`, lời gọi này giúp tạo URI từ annotation của controller và các tham số truyền vào, thay vì tự ghép đường dẫn. Đây là cách thường dùng để tạo link `self`, link đến resource liên quan hoặc link cho một hành động nghiệp vụ.

## methodOn là gì?

`methodOn(Class<T> controllerType)` là phương thức tĩnh trong `WebMvcLinkBuilder`. Nó tạo một proxy đặc biệt cho controller được chỉ định. Khi gọi một phương thức trên proxy, Spring HATEOAS ghi nhận phương thức và các đối số để xác định mapping cần dùng khi xây dựng link.

Ví dụ:

```java
linkTo(methodOn(OrderController.class).one(orderId)).withSelfRel();
```

Lời gọi trên thể hiện rằng link cần trỏ đến mapping của phương thức `one(...)` trong `OrderController`, với `orderId` là tham số tương ứng. `linkTo(...)` dùng thông tin invocation để tạo link builder; `withSelfRel()` gắn relation `self` cho link cuối cùng.

Điểm cần nhớ: `methodOn(...)` không gọi phương thức controller thật để thực hiện nghiệp vụ. Proxy chỉ ghi nhận lời gọi nhằm tìm metadata mapping. Service, truy vấn cơ sở dữ liệu và logic trong thân phương thức controller không chạy chỉ vì biểu thức `methodOn(...).one(...)` được dùng để tạo link.

## Vì sao dùng methodOn?

Giả sử controller ban đầu có mapping `/api/orders/{id}`. Sau đó nhóm phát triển chuyển prefix thành `/v2/orders/{id}`. Nếu các nơi tạo link đều nối chuỗi `"/api/orders/" + id`, mỗi nơi phải được tìm và sửa. Nếu link được tạo dựa trên phương thức controller, Spring HATEOAS có thể lấy đường dẫn từ mapping mới.

`methodOn` hữu ích vì:

- **Tái sử dụng mapping:** link được tạo từ `@RequestMapping`, `@GetMapping`, `@PostMapping` và các annotation mapping liên quan.
- **Gắn tham số đúng vị trí:** giá trị `@PathVariable` được dùng để điền phần biến trong path.
- **Giảm URL viết cứng:** controller và assembler không phải tự nối path bằng chuỗi.
- **Tăng tính nhất quán:** nhiều representation có thể tham chiếu cùng một phương thức controller để tạo link.
- **Hỗ trợ tiến hóa API:** khi mapping đổi, các link dựa trên mapping có thể cập nhật theo mà không phải sửa mọi nơi tạo link.

`methodOn` không tự bảo đảm mọi thay đổi API đều tương thích ngược. Nếu client phụ thuộc vào relation, cấu trúc dữ liệu hoặc quy tắc nghiệp vụ đã thay đổi, client vẫn có thể cần cập nhật. Nó giải quyết việc xây dựng URI theo mapping hiện có.

## Cách dùng cơ bản với linkTo

`methodOn(...)` thường được dùng cùng `linkTo(...)` qua static import:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
```

Giả sử controller có endpoint đọc một đơn hàng:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        OrderView order = orderService.get(id);
        return EntityModel.of(order);
    }
}
```

Tạo link `self` cho một đơn hàng:

```java
Link self = linkTo(methodOn(OrderController.class).one(order.id()))
    .withSelfRel();
```

Trong đó:

1. `OrderController.class` xác định controller có mapping cần tham chiếu.
2. `.one(order.id())` xác định phương thức controller và giá trị tham số.
3. `linkTo(...)` tạo link builder dựa trên mapping được tìm thấy.
4. `withSelfRel()` tạo `Link` với relation `self`.

Kết quả là một `Link` có `href` tương ứng với URI của đơn hàng và relation `self`. Không cần ghi cứng `/api/orders/` trong assembler hoặc controller.

## methodOn với PathVariable

Trường hợp phổ biến nhất là endpoint có biến đường dẫn:

```java
@GetMapping("/{orderId}")
EntityModel<OrderView> one(@PathVariable("orderId") UUID id) {
    OrderView order = orderService.get(id);
    return EntityModel.of(order);
}
```

Tạo link bằng đúng giá trị cần thay vào `orderId`:

```java
Link self = linkTo(methodOn(OrderController.class).one(order.id()))
    .withSelfRel();
```

Spring HATEOAS đọc mapping của phương thức và ánh xạ đối số `order.id()` vào path variable. Việc đặt tên rõ ràng trong `@PathVariable("orderId")` giúp mapping không phụ thuộc vào tên tham số được lưu trong bytecode.

Với nested resource, có thể truyền nhiều path variable:

```java
@GetMapping("/{orderId}/items/{itemId}")
EntityModel<OrderItemView> item(
        @PathVariable UUID orderId,
        @PathVariable UUID itemId) {
    return EntityModel.of(orderService.getItem(orderId, itemId));
}
```

Tạo link tới một dòng hàng cụ thể:

```java
Link itemLink = linkTo(methodOn(OrderController.class)
    .item(order.id(), item.id()))
    .withRel("item");
```

Thứ tự đối số trong lời gọi `methodOn` phải khớp với chữ ký phương thức Java. Khi có nhiều path variable cùng kiểu, hãy dùng tên annotation rõ ràng và truyền đúng thứ tự để tránh tạo link đến resource khác.

## methodOn với RequestParam

Một phương thức controller có thể nhận tham số query để lọc hoặc sắp xếp collection:

```java
@GetMapping
CollectionModel<OrderView> all(
        @RequestParam(required = false) String status,
        @RequestParam(defaultValue = "createdAt,desc") String sort) {
    List<OrderView> result = orderService.findAll(status, sort);
    return CollectionModel.of(result);
}
```

Có thể tham chiếu phương thức đó để tạo link collection:

```java
Link pendingOrders = linkTo(methodOn(OrderController.class)
    .all("PENDING", "createdAt,desc"))
    .withRel("pending-orders");
```

Các đối số được truyền cho lời gọi proxy giúp Spring HATEOAS xây URI theo mapping và các tham số request của phương thức. Nhờ vậy link có thể giữ filter và sort mà client cần. Khi tạo link cho chính collection đang được yêu cầu, hãy truyền các giá trị filter/sort hiện tại thay vì giá trị mặc định cố định.

Ví dụ, nếu response được tạo từ request `?status=SHIPPED&sort=createdAt,asc`, self link cần phản ánh đúng hai giá trị đó. Nếu link bỏ mất filter, client theo link sẽ nhận một collection khác với representation hiện tại.

## Kết hợp methodOn với class-level mapping

Controller thường có mapping ở cấp lớp và cấp phương thức:

```java
@RestController
@RequestMapping("/api/v2/orders")
class OrderController {

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        // ...
    }
}
```

Khi dùng:

```java
linkTo(methodOn(OrderController.class).one(orderId)).withSelfRel();
```

Spring HATEOAS kết hợp mapping cấp lớp `/api/v2/orders` với mapping cấp phương thức `/{id}`. Nếu prefix đổi, link builder dựa trên controller mapping sẽ lấy giá trị mới.

Mapping có thể bao gồm path prefix, nhiều path pattern hoặc cấu hình theo framework. Hãy để annotation mapping là nguồn sự thật cho endpoint và kiểm thử link sinh ra trong ứng dụng thực tế.

## Phân biệt methodOn với linkTo trực tiếp

`linkTo(...)` và `methodOn(...)` thường được dùng cùng nhau, nhưng có vai trò riêng:

| Cách viết | Ý nghĩa | Khi phù hợp |
| --- | --- | --- |
| `linkTo(OrderController.class)` | Tạo link builder từ mapping cấp controller | Cần link đến root mapping của controller hoặc tiếp tục bổ sung path theo cách có chủ đích. |
| `linkTo(methodOn(OrderController.class).one(id))` | Tạo link builder từ mapping của một phương thức cụ thể và đối số | Cần trỏ đến endpoint có method-level mapping và path/query parameters. |
| `linkTo(currentMethod)` | Tạo link builder từ đối tượng invocation đã được ghi nhận | Khi invocation đã được tạo trước và cần tái sử dụng. |

Ví dụ dùng `linkTo(OrderController.class).slash(id)` có thể tạo path theo cách nối thêm segment, nhưng không tham chiếu trực tiếp mapping phương thức như `methodOn`. Nếu endpoint có path phức tạp hoặc nhiều biến, `methodOn` thường diễn đạt rõ phương thức đích hơn.

## Dùng methodOn trong RepresentationModelAssembler

Logic tạo link thường được đặt trong assembler để controller không phải lặp lại mapping cho từng item.

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<OrderView, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(OrderView order) {
        return EntityModel.of(order,
            linkTo(methodOn(OrderController.class).one(order.id()))
                .withSelfRel(),
            linkTo(methodOn(OrderController.class).all(null, "createdAt,desc"))
                .withRel("orders"));
    }
}
```

Assembler trên tạo link `self` đến item và link `orders` đến collection. Ví dụ giả định controller có phương thức `all(String status, String sort)` như phần trước. Trong ứng dụng thật, không nên cố định filter/sort của collection nếu cần quay về đúng collection mà client đang xem; hãy truyền ngữ cảnh request hoặc để controller tạo link collection.

`methodOn` cũng hữu ích khi tạo affordance cho hành động. Ví dụ, một đơn hàng đang chờ có thể có affordance gắn với link `self` để mô tả phương thức hủy:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(methodOn(OrderController.class).one(order.id()))
    .withSelfRel();

if (order.status() == OrderStatus.PENDING) {
    self = self.andAffordance(
        afford(methodOn(OrderController.class).cancel(order.id())));
}
```

Trong trường hợp này, `methodOn` chỉ ra mapping của thao tác `cancel(...)`; `afford(...)` lấy thông tin mapping để mô tả affordance. Nó vẫn không gọi logic hủy đơn hàng. Server phải kiểm tra quyền và trạng thái khi request hủy thật sự đến endpoint.

## methodOn không thực thi nghiệp vụ

Một hiểu nhầm phổ biến là biểu thức:

```java
methodOn(OrderController.class).one(orderId)
```

sẽ gọi `one(orderId)` giống như gọi một object Java thông thường. Thực tế, `methodOn` tạo proxy ghi nhận invocation để Spring HATEOAS phân tích mapping. Thân phương thức controller không được thực thi như một request HTTP bình thường.

Do đó:

- Không đặt kỳ vọng side effect xảy ra khi tạo link.
- Không dùng giá trị trả về giả lập của lời gọi proxy làm dữ liệu nghiệp vụ.
- Không đặt logic quan trọng trong thân controller với giả định `methodOn` sẽ chạy nó.
- Chỉ dùng lời gọi proxy để chỉ ra phương thức mapping và các tham số cần tạo URI.

Nếu cần lấy dữ liệu, hãy gọi service thực sự trong request handler hoặc assembler theo thiết kế ứng dụng. `methodOn` chỉ giải quyết việc tham chiếu endpoint.

## Những giới hạn và lưu ý khi dùng methodOn

`methodOn` dựa vào metadata mapping và chữ ký phương thức. Vì vậy:

1. **Phương thức phải có mapping phù hợp:** một phương thức không được ánh xạ bằng annotation request mapping sẽ không cung cấp endpoint rõ ràng để tạo link.
2. **Truyền đúng tham số:** giá trị path variable, request parameter hoặc các đối số khác cần tương ứng với chữ ký và annotation của phương thức.
3. **Chú ý overload:** nếu controller có nhiều phương thức cùng tên, hãy gọi đúng overload với kiểu và thứ tự đối số rõ ràng.
4. **Không phụ thuộc vào thân phương thức:** lời gọi proxy không thực thi nghiệp vụ hoặc kiểm tra quyền.
5. **Xử lý URI công khai khi chạy sau proxy:** link builder sử dụng request context và cấu hình forwarded headers để tạo host/scheme đúng. Cấu hình sai có thể tạo URL nội bộ.
6. **Tránh gọi methodOn ngoài request context mà thiếu base URI:** khi tạo link trong batch job hoặc tiến trình nền, cần cung cấp base URI phù hợp hoặc dùng cơ chế tạo link tương ứng với ngữ cảnh đó.

Nếu endpoint có nhiều tham số phức tạp hoặc request body, hãy kiểm tra link sinh ra trong response và dùng affordance/media type phù hợp khi client cần biết cách thực hiện thao tác. Không phải mọi thông tin request đều nên được mã hóa vào URI.

## Kiểm thử link được tạo bằng methodOn

Kiểm thử nên xác nhận link cuối cùng có đúng relation và URI. Với MockMvc, có thể kiểm tra response HAL:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
        .value(org.hamcrest.Matchers.endsWith("/api/orders/" + orderId)));
```

Kiểm tra này giúp phát hiện trường hợp mapping hoặc path variable bị sai. Nếu API có prefix `/api/v2`, hãy xác nhận link chứa prefix công khai đó theo hợp đồng.

Với unit test cho assembler, có thể kiểm tra relation và URI của model:

```java
EntityModel<OrderView> model = assembler.toModel(order);

assertThat(model.getRequiredLink(IanaLinkRelations.SELF).getHref())
    .endsWith("/api/orders/" + order.id());
```

Để tránh test phụ thuộc hostname động, có thể kiểm tra path suffix hoặc cấu hình base URI cố định trong test. Với test tích hợp, nên xác nhận cả host, scheme và path khi ứng dụng chạy sau reverse proxy.

Ngoài ra, hãy kiểm thử khi:

- Path variable có giá trị đặc biệt cần được encode.
- Mapping cấp lớp hoặc cấp phương thức thay đổi.
- Controller có nhiều method mapping hoặc overload.
- Query parameter có filter/sort và self link cần giữ ngữ cảnh.
- Relation hành động chỉ xuất hiện theo trạng thái nghiệp vụ.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nối URL bằng chuỗi thay vì tham chiếu mapping | Link dễ sai khi controller đổi path. | Dùng `linkTo(methodOn(...))`. |
| Nghĩ methodOn gọi controller thật | Kỳ vọng sai về side effect hoặc giá trị trả về. | Xem nó là proxy ghi nhận invocation, chỉ dùng để tạo URI. |
| Truyền nhầm thứ tự path variable | Link trỏ đến resource sai hoặc URI không đúng. | Giữ thứ tự tham số theo chữ ký và khai báo tên `@PathVariable` rõ ràng. |
| Bỏ filter/sort khi tạo self link collection | Client theo link nhận tập kết quả khác. | Truyền giá trị truy vấn hiện tại vào lời gọi `methodOn`. |
| Dùng linkTo(controller).slash(...) cho mapping phức tạp | Path có thể không phản ánh đầy đủ mapping của phương thức. | Tham chiếu method-level mapping bằng `methodOn`. |
| Tạo link trong tác vụ nền nhưng giả định có request context | URI có thể thiếu host/scheme hoặc không tạo được. | Dùng base URI cấu hình hoặc cơ chế tạo link phù hợp ngữ cảnh. |
| Không kiểm thử URI cuối cùng | Sai mapping hoặc prefix có thể lọt vào response. | Kiểm tra `href`, `rel` và media type trong test. |

## Ghi nhớ

- `methodOn(...)` tạo proxy để ghi nhận lời gọi phương thức controller và các đối số; nó không thực thi thân phương thức.
- Kết hợp `linkTo(methodOn(...))` để tạo link từ mapping controller.
- Dùng `methodOn` để điền path variable, tham chiếu query parameter và tạo link cho method-level mapping.
- `withSelfRel()`, `withRel(...)` và `andAffordance(...)` bổ sung quan hệ hoặc mô tả hành động cho link.
- Dùng trong assembler để tái sử dụng logic tạo link, nhưng giữ đúng ngữ cảnh filter/sort của collection.
- Chú ý thứ tự tham số, overload, request context và forwarded headers.
- Kiểm thử URI cuối cùng cùng relation trong response HAL để bảo vệ hợp đồng hypermedia.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – WebMvcLinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)
- [Spring HATEOAS API – Link](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [Spring HATEOAS API – RepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
