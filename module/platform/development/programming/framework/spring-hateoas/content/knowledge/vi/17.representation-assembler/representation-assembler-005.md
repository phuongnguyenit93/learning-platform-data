# Assembler cho collection

Một API quản lý đơn hàng thường trả về hai dạng representation: một đơn hàng và một tập hợp đơn hàng. Mỗi item cần dữ liệu cùng link `self`; collection cần link riêng để client nhận biết danh sách hiện tại, quay lại kết quả tìm kiếm hoặc khám phá thao tác áp dụng cho cả tập hợp. Nếu controller tự ánh xạ từng item và tự thêm link ở nhiều endpoint, logic dễ bị lặp và không nhất quán.

Spring HATEOAS cung cấp `RepresentationModelAssembler` để gom việc chuyển đổi một đối tượng miền thành representation model. Interface này có `toModel(...)` cho một item và `toCollectionModel(...)` cho một tập hợp. Khi cần bổ sung link ở cả cấp item lẫn cấp collection, có thể dùng `SimpleRepresentationModelAssembler<T>` với hai hook `addLinks(...)`. Nhờ vậy, controller chỉ cần lấy dữ liệu và yêu cầu assembler tạo representation cho collection.

## RepresentationModelAssembler làm nhiệm vụ gì?

`RepresentationModelAssembler<T, D>` là interface chuyển đổi một đối tượng nguồn kiểu `T` thành một representation model kiểu `D`, trong đó `D` kế thừa `RepresentationModel<?>`.

Interface có hai phương thức chính:

| Phương thức | Vai trò |
| --- | --- |
| `toModel(T entity)` | Chuyển một đối tượng nguồn thành representation model của một item. |
| `toCollectionModel(Iterable<? extends T> entities)` | Chuyển nhiều đối tượng nguồn thành các model item rồi bọc chúng trong `CollectionModel<D>`. |

`toCollectionModel(...)` là phương thức mặc định. Nó gọi `toModel(...)` cho từng phần tử và tạo `CollectionModel` chứa kết quả. Như vậy, logic ánh xạ item chỉ cần viết một lần và được tái sử dụng khi trả về collection.

Ví dụ, nếu assembler khai báo:

```java
RepresentationModelAssembler<Order, EntityModel<OrderView>>
```

thì kiểu nguồn là `Order`, kiểu model item là `EntityModel<OrderView>`, và kết quả của `toCollectionModel(...)` là `CollectionModel<EntityModel<OrderView>>`.

## Tách link của item và link của collection

Một collection representation có thể chứa hai cấp liên kết độc lập:

- **Link của item:** nằm trong từng `EntityModel` hoặc model tùy chỉnh, ví dụ `self` trỏ đến `/api/orders/{id}`.
- **Link của collection:** nằm trên `CollectionModel`, ví dụ `self` trỏ đến `/api/orders`, hoặc `search` trỏ đến điểm tìm kiếm.

Hai cấp này không tự động thay thế nhau. Việc mỗi item có link `self` không có nghĩa collection đã có link `self`. Ngược lại, link `self` của collection không giúp client mở chi tiết từng đơn hàng.

Ví dụ HAL rút gọn:

```json
{
  "_links": {
    "self": { "href": "/api/orders" }
  },
  "_embedded": {
    "orders": [
      {
        "id": "ord-1042",
        "_links": {
          "self": { "href": "/api/orders/ord-1042" }
        }
      },
      {
        "id": "ord-1043",
        "_links": {
          "self": { "href": "/api/orders/ord-1043" }
        }
      }
    ]
  }
}
```

Trong ví dụ, `._links.self` ở gốc là link của collection; `._embedded.orders[n]._links.self` là link của item thứ `n`.

## Cách 1: Dùng RepresentationModelAssembler<T, D>

Đây là cách linh hoạt khi item cần DTO riêng hoặc model tùy chỉnh. Assembler triển khai `toModel(...)`; phương thức mặc định `toCollectionModel(...)` sẽ tái sử dụng logic đó cho mọi phần tử.

Giả sử ứng dụng có DTO dành cho API:

```java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderView(
    UUID id,
    String status,
    BigDecimal total
) {
}
```

Assembler chuyển `Order` thành `EntityModel<OrderView>`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        OrderView view = new OrderView(
            order.getId(),
            order.getStatus().name(),
            order.getTotal());

        return EntityModel.of(view,
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel());
    }
}
```

Assembler chỉ chịu trách nhiệm biểu diễn một item. Link `self` được tạo từ mapping của `OrderController`, còn DTO chọn những trường cần công bố ra API. Domain entity không bị trả trực tiếp ra ngoài.

Controller có thể gọi `toCollectionModel(...)`, sau đó thêm link ở cấp collection:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping
CollectionModel<EntityModel<OrderView>> all() {
    CollectionModel<EntityModel<OrderView>> collection =
        assembler.toCollectionModel(orderService.findAll());

    collection.add(
        linkTo(methodOn(OrderController.class).all()).withSelfRel());

    return collection;
}
```

Mỗi item được ánh xạ qua `toModel(...)`; sau đó controller thêm self link cho collection. Cách này phù hợp khi collection link phụ thuộc vào ngữ cảnh request như filter, sort hoặc phân trang, vì controller đang nắm các tham số của endpoint.

## Cách 2: Dùng SimpleRepresentationModelAssembler<T>

Nếu representation item chỉ cần bọc chính đối tượng nguồn bằng `EntityModel<T>`, có thể dùng `SimpleRepresentationModelAssembler<T>`. Interface này mở rộng `RepresentationModelAssembler<T, EntityModel<T>>` và cung cấp hai hook:

| Hook | Khi được dùng | Mục đích |
| --- | --- | --- |
| `addLinks(EntityModel<T> resource)` | Khi tạo representation cho từng item | Thêm link vào từng item. |
| `addLinks(CollectionModel<EntityModel<T>> resources)` | Khi tạo representation cho collection | Thêm link ở cấp collection. |

Các phương thức mặc định `toModel(...)` và `toCollectionModel(...)` gọi những hook tương ứng. Điều này cho phép assembler tập trung cả link item và link collection mà controller không cần tự bổ sung từng link chung.

Ví dụ:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.SimpleRepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements SimpleRepresentationModelAssembler<OrderView> {

    @Override
    public void addLinks(EntityModel<OrderView> resource) {
        OrderView order = resource.getContent();

        resource.add(linkTo(methodOn(OrderController.class).one(order.id()))
            .withSelfRel());
    }

    @Override
    public void addLinks(CollectionModel<EntityModel<OrderView>> resources) {
        resources.add(
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }
}
```

Với assembler này, controller chỉ cần:

```java
@GetMapping
CollectionModel<EntityModel<OrderView>> all() {
    return assembler.toCollectionModel(orderService.findAllViews());
}
```

Khi `toCollectionModel(...)` chạy, assembler tạo `EntityModel` cho từng `OrderView`, gọi `addLinks(EntityModel<T>)` để thêm link item, bọc các model vào `CollectionModel`, rồi gọi `addLinks(CollectionModel<...>)` để thêm link collection.

`SimpleRepresentationModelAssembler` phù hợp khi representation item chính là đối tượng nguồn. Nếu cần chuyển `Order` thành `OrderView` với cấu trúc khác, dùng `RepresentationModelAssembler<Order, EntityModel<OrderView>>` sẽ linh hoạt hơn.

## Chọn giữa hai kiểu assembler

| Tiêu chí | `RepresentationModelAssembler<T, D>` | `SimpleRepresentationModelAssembler<T>` |
| --- | --- | --- |
| Kiểu item model | Bất kỳ kiểu `D` kế thừa `RepresentationModel<?>` | Cố định là `EntityModel<T>` |
| Ánh xạ DTO | Có thể chuyển domain entity sang DTO hoặc custom model | Thường bọc trực tiếp đối tượng nguồn `T` |
| Link item | Viết trong `toModel(...)` | Viết trong `addLinks(EntityModel<T>)` |
| Link collection | Thêm sau khi gọi `toCollectionModel(...)`, hoặc override phương thức này | Viết trong `addLinks(CollectionModel<EntityModel<T>>)`. |
| Khi nên chọn | Cần kiểm soát kiểu model đích hoặc cấu trúc dữ liệu | Item đơn giản, chỉ cần bọc nguồn và thêm link. |

Không cần tạo một assembler phức tạp nếu DTO đã phù hợp và chỉ cần thêm vài link. Ngược lại, không nên ép `SimpleRepresentationModelAssembler` khi cần custom model hoặc chuyển đổi domain object đáng kể.

## Tùy chỉnh toCollectionModel trong RepresentationModelAssembler

`toCollectionModel(...)` là phương thức mặc định nên có thể override khi mọi collection do assembler tạo đều cần cùng một nhóm link cấp collection.

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;

class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        OrderView view = OrderView.from(order);

        return EntityModel.of(view,
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel());
    }

    @Override
    public CollectionModel<EntityModel<OrderView>> toCollectionModel(
            Iterable<? extends Order> orders) {

        CollectionModel<EntityModel<OrderView>> collection =
            RepresentationModelAssembler.super.toCollectionModel(orders);

        collection.add(
            linkTo(methodOn(OrderController.class).all()).withSelfRel());

        return collection;
    }
}
```

Lời gọi `RepresentationModelAssembler.super.toCollectionModel(orders)` dùng triển khai mặc định để ánh xạ từng item qua `toModel(...)`. Sau đó assembler thêm link cấp collection. Cách này tránh viết lại vòng lặp ánh xạ item.

Chỉ nên override khi link cấp collection là quy tắc chung cho mọi lần dùng assembler. Nếu self link cần giữ filter, sort, page hoặc cursor riêng của request hiện tại, controller thường là nơi phù hợp hơn để bổ sung link vì assembler không tự biết đầy đủ ngữ cảnh request.

## Tích hợp với controller và service

Một controller thường có ba trách nhiệm rõ ràng:

1. Nhận tham số request và xác định truy vấn cần thực hiện.
2. Gọi service để lấy dữ liệu domain hoặc DTO.
3. Dùng assembler để tạo representation model rồi trả response.

Ví dụ controller:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        return assembler.toCollectionModel(orderService.findAll());
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        return assembler.toModel(orderService.get(id));
    }
}
```

Ví dụ giả định `OrderService.findAll()` trả về `Iterable<Order>` và `get(...)` trả về `Order`. Nếu dùng `SimpleRepresentationModelAssembler<OrderView>`, controller truyền `Iterable<OrderView>` tương ứng. Chữ ký generic của assembler phải khớp với kiểu dữ liệu thực tế mà service trả về.

## Link collection có ngữ cảnh truy vấn

Assembler có thể thêm link collection chung, nhưng link `self` của request có filter hoặc sort cần giữ đúng tham số hiện tại. Ví dụ:

```java
@GetMapping
CollectionModel<EntityModel<OrderView>> all(
        @RequestParam(required = false) String status,
        @RequestParam(defaultValue = "createdAt,desc") String sort) {

    Iterable<Order> result = orderService.findAll(status, sort);
    CollectionModel<EntityModel<OrderView>> collection =
        assembler.toCollectionModel(result);

    collection.add(linkTo(methodOn(OrderController.class).all(status, sort))
        .withSelfRel());

    return collection;
}
```

Trong trường hợp này, controller thêm self link theo tham số request thay vì dùng một link mặc định không có filter. Nếu assembler đã thêm self link chung, tránh tạo hai link cùng relation `self` với các URI khác nhau; hãy thống nhất nơi chịu trách nhiệm tạo link collection.

Các link khác ở cấp collection như `search`, `create` hoặc `profile` có thể được thêm trong assembler nếu chúng luôn có cùng ý nghĩa và điều kiện. Link phụ thuộc quyền người dùng, trạng thái hoặc tham số request nên được tạo tại nơi có đủ ngữ cảnh.

## Collection rỗng và fallback type

Collection rỗng vẫn là representation hợp lệ. Khi gọi `toCollectionModel(...)` với iterable không có phần tử, assembler không có item nào để ánh xạ nhưng vẫn có thể tạo collection model và thêm link cấp collection.

```java
CollectionModel<EntityModel<OrderView>> empty =
    assembler.toCollectionModel(List.of());
```

Một lưu ý nâng cao: `RepresentationModelProcessor` thường được chọn dựa trên kiểu model và kiểu phần tử. Với collection rỗng, do Java type erasure, hạ tầng có thể không suy ra kiểu payload từ item; processor cho collection có thể không được gọi theo mặc định. Nếu ứng dụng phụ thuộc vào processor cho collection rỗng, hãy khai báo fallback payload type bằng API `withFallbackType(...)` hoặc khởi tạo collection model với fallback type thích hợp.

Đây là vấn đề liên quan đến việc lựa chọn processor theo generic, không phải lý do để collection rỗng mất link. Nếu link `self` là bắt buộc, assembler vẫn nên thêm link trực tiếp hoặc controller bổ sung nó trước khi trả response.

## Phân trang: khi nào cần PagedModel?

`toCollectionModel(...)` nhận một `Iterable` và tạo `CollectionModel`. Nó không tự thêm metadata phân trang như số trang hiện tại, kích thước trang, tổng số phần tử hoặc tổng số trang.

Nếu service trả về `Page<Order>`, hãy dùng `PagedResourcesAssembler` của Spring Data để tạo `PagedModel` và tận dụng cùng item assembler:

```java
@GetMapping
PagedModel<EntityModel<OrderView>> all(Pageable pageable) {
    Page<Order> page = orderService.findAll(pageable);
    return pagedResourcesAssembler.toModel(page, assembler);
}
```

Ví dụ giả định `assembler` triển khai `RepresentationModelAssembler<Order, EntityModel<OrderView>>` và controller được tiêm `PagedResourcesAssembler<Order>`. Paged assembler dùng item assembler để tạo từng phần tử, đồng thời thêm metadata và link điều hướng trang.

Không nên gọi `toCollectionModel(page.getContent())` rồi trả như một collection đầy đủ nếu client cần biết trang hiện tại và cách đi đến trang kế tiếp. Làm như vậy sẽ mất thông tin phân trang trong hợp đồng.

## Relation cho embedded collection

Khi serialize thành HAL, `CollectionModel` thường biểu diễn các phần tử bên trong `_embedded`. Tên relation của tập hợp nhúng nên ổn định và dễ hiểu, chẳng hạn `orders`.

Có thể cấu hình relation cho model bằng `@Relation`:

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderView(UUID id, String status, BigDecimal total) {
}
```

`itemRelation` mô tả tên relation cho từng phần tử khi nhúng; `collectionRelation` mô tả tên collection trong `_embedded`. Tên này khác với link relation trong `_links`. Hãy kiểm thử JSON HAL thực tế để bảo đảm client dùng đúng tên đã công bố.

## Kiểm thử assembler cho collection

Nên kiểm tra riêng hai lớp hành vi: ánh xạ item và tạo collection. Unit test assembler giúp xác nhận mỗi item có dữ liệu và link phù hợp, collection có link riêng.

Ví dụ kiểm tra bằng AssertJ:

```java
CollectionModel<EntityModel<OrderView>> model =
    assembler.toCollectionModel(List.of(order1, order2));

assertThat(model.getContent()).hasSize(2);
assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue();

for (EntityModel<OrderView> item : model.getContent()) {
    assertThat(item.hasLink(IanaLinkRelations.SELF)).isTrue();
}
```

Test trên giả định assembler chịu trách nhiệm thêm self link cho cả collection và item. Nếu controller mới thêm collection self link, hãy kiểm tra link đó trong test controller thay vì kỳ vọng assembler tự tạo.

Với MockMvc, kiểm tra response HAL đã serialize:

```java
mockMvc.perform(get("/api/orders")
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
```

`orders` là embedded relation minh họa; nếu ứng dụng dùng tên khác hoặc collection rỗng, điều chỉnh JSON path theo hợp đồng. Ngoài ra, nên kiểm thử collection rỗng, filter/sort, link không khả dụng theo quyền và trường hợp phân trang.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Viết logic ánh xạ item trong từng controller | Các endpoint tạo representation và link không nhất quán. | Đưa logic dùng chung vào `RepresentationModelAssembler`. |
| Nghĩ `toCollectionModel()` tự tạo mọi link collection | Collection có thể chỉ chứa item links mà thiếu `self` cấp tập hợp. | Bổ sung collection links trong hook, override hoặc controller. |
| Nhầm link item với link collection | Client không có URI đúng cho tập hợp hoặc từng item. | Kiểm tra link ở cả hai cấp representation. |
| Dùng `SimpleRepresentationModelAssembler` dù cần DTO khác | Kiểu model bị ép thành `EntityModel<T>` và khó chuyển đổi dữ liệu. | Dùng `RepresentationModelAssembler<T, D>` với kiểu đích phù hợp. |
| Thêm self link ở cả assembler và controller | Response có thể có nhiều link cùng relation `self` với URI khác nhau. | Chọn một nơi tạo self link collection và giữ quy tắc nhất quán. |
| Dùng CollectionModel cho Page mà bỏ metadata | Client không biết tổng số phần tử hoặc trang kế tiếp. | Dùng `PagedResourcesAssembler` và `PagedModel`. |
| Không kiểm thử collection rỗng | Lỗi chỉ xuất hiện khi không có item hoặc processor không được gọi. | Kiểm thử empty collection và khai báo fallback type nếu cần processor. |
| Dựa vào tên embedded relation mặc định | Thay đổi kiểu Java có thể làm đổi cấu trúc HAL. | Cấu hình `@Relation` và kiểm thử hợp đồng JSON. |

## Ghi nhớ

- `RepresentationModelAssembler<T, D>` chuyển một đối tượng nguồn thành model item qua `toModel(...)`.
- `toCollectionModel(...)` mặc định gọi `toModel(...)` cho từng item rồi bọc kết quả trong `CollectionModel<D>`.
- Link của item và link của collection nằm ở hai cấp khác nhau; cần tạo cả hai nếu hợp đồng yêu cầu.
- `SimpleRepresentationModelAssembler<T>` có hook `addLinks(...)` cho item và collection khi dùng `EntityModel<T>`.
- Override `toCollectionModel(...)` khi mọi collection cần cùng quy tắc link; giữ link phụ thuộc request trong controller.
- Collection rỗng vẫn cần được biểu diễn và có thể cần fallback type nếu dùng `RepresentationModelProcessor`.
- Dùng `PagedResourcesAssembler` và `PagedModel` khi cần metadata và link phân trang.
- Kiểm thử cả model trong unit test lẫn response HAL đã serialize bằng MockMvc.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Representation Model Assembler](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.representation-model-assembler)
- [Spring HATEOAS API – RepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [Spring HATEOAS API – SimpleRepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/SimpleRepresentationModelAssembler.html)
- [Spring HATEOAS API – CollectionModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html)
- [Spring HATEOAS API – RepresentationModelProcessor](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelProcessor.html)
