# Chọn kiểu model

Khi xây dựng API với Spring HATEOAS, cùng một loại dữ liệu có thể được trả về theo nhiều cách. Một endpoint đọc một đơn hàng cần biểu diễn một resource đơn; endpoint danh sách cần biểu diễn một collection; endpoint tìm kiếm có phân trang cần thêm metadata trang; còn một biểu diễn có cấu trúc riêng có thể cần lớp model do ứng dụng định nghĩa. Chọn đúng kiểu model giúp response có cấu trúc rõ ràng và các liên kết hypermedia được đặt ở đúng cấp.

Spring HATEOAS cung cấp bốn kiểu thường gặp: `RepresentationModel`, `EntityModel`, `CollectionModel` và `PagedModel`. Chúng có mục đích khác nhau. `RepresentationModel` là nền tảng để tạo biểu diễn tùy chỉnh; `EntityModel` bọc một đối tượng; `CollectionModel` bọc tập hợp; `PagedModel` mở rộng biểu diễn tập hợp với metadata phân trang.

## Bắt đầu từ hình dạng response

Trước khi chọn class, hãy xác định client cần nhận một đối tượng, nhiều đối tượng hay một trang dữ liệu. Đồng thời xác định representation có cần các trường riêng, link ở cấp phần tử hay link ở cấp collection.

| Nhu cầu API | Kiểu model thường phù hợp | Ví dụ |
| --- | --- | --- |
| Một DTO hoặc đối tượng đơn lẻ kèm link | `EntityModel<T>` | Chi tiết một đơn hàng |
| Một representation có trường riêng và link | Lớp kế thừa `RepresentationModel<T>` | Model đơn hàng có `statusLabel`, `canCancel` hoặc dữ liệu trình bày được tính toán |
| Một tập hợp phần tử không có metadata phân trang | `CollectionModel<T>` | Danh sách kết quả nhỏ hoặc danh sách trạng thái |
| Một tập hợp có trang hiện tại, kích thước và tổng số phần tử | `PagedModel<T>` | Danh sách đơn hàng có phân trang |

Các kiểu này không phải bốn lựa chọn thay thế hoàn toàn cho nhau. `EntityModel` và model tùy chỉnh phù hợp với một resource đơn; `CollectionModel` và `PagedModel` phù hợp với tập hợp. Một collection còn có thể chứa các `EntityModel` hoặc model tùy chỉnh để mỗi phần tử có link riêng.

## `EntityModel<T>`: bọc một đối tượng có sẵn

Chọn `EntityModel<T>` khi ứng dụng đã có DTO hoặc projection phù hợp và chỉ cần thêm hypermedia. Kiểu này giúp tránh tạo một lớp Java mới cho mỗi response đơn giản.

Giả sử API có DTO:

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

Controller có thể trả về `EntityModel<OrderView>`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping
    CollectionModel<OrderView> all() {
        return CollectionModel.of(orders.findAll(),
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        OrderView order = orders.get(id);

        return EntityModel.of(order,
            linkTo(methodOn(OrderController.class).one(id)).withSelfRel(),
            linkTo(methodOn(OrderController.class).all()).withRel("orders"));
    }
}
```

`EntityModel.of(content, links...)` giữ DTO làm phần dữ liệu và gắn các link vào model. Với HAL, dữ liệu thường xuất hiện ở các thuộc tính JSON thông thường còn liên kết nằm trong `_links`.

Nên chọn `EntityModel` khi:

- DTO đã thể hiện đầy đủ các trường client cần.
- Phần khác biệt của response chủ yếu là các link hypermedia.
- Không cần một kiểu representation riêng có hành vi hoặc trường trình bày bổ sung.
- Muốn tái sử dụng DTO ở nhiều endpoint mà không gắn logic link vào DTO.

Không nên bọc một model đã là `RepresentationModel` vào `EntityModel` lần nữa. Ví dụ, `EntityModel<OrderModel>` thường là một lớp bọc dư thừa nếu `OrderModel` đã kế thừa `RepresentationModel` và tự mang link. Chọn một lớp đại diện cho resource để tránh cấu trúc lồng nhau khó hiểu.

## `RepresentationModel<T>`: tạo representation tùy chỉnh

Chọn lớp kế thừa `RepresentationModel` khi response cần cấu trúc riêng ngoài việc bọc một DTO. Ví dụ, API muốn công bố `statusLabel`, số lượng dòng hàng hoặc một giá trị trình bày được tính toán từ dữ liệu nghiệp vụ.

`RepresentationModel` dùng generic tự tham chiếu, thường được gọi là *self type*. Tham số generic biểu thị chính lớp model để các phương thức như `add(Link...)` có thể trả về kiểu cụ thể. Nó không phải kiểu payload được bọc bên trong như generic của `EntityModel<T>`.

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;

public class OrderModel extends RepresentationModel<OrderModel> {

    private UUID id;
    private String status;
    private String statusLabel;
    private BigDecimal total;

    protected OrderModel() {
        // Constructor không tham số có thể hữu ích cho một số cấu hình serializer.
    }

    public OrderModel(UUID id, String status, String statusLabel,
                      BigDecimal total) {
        this.id = id;
        this.status = status;
        this.statusLabel = statusLabel;
        this.total = total;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public String getStatusLabel() {
        return statusLabel;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
```

Controller tạo model tùy chỉnh rồi thêm link:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

OrderModel model = new OrderModel(
    order.id(),
    order.status().name(),
    statusLabel(order.status()),
    order.total());

model.add(linkTo(methodOn(OrderController.class).one(order.id()))
    .withSelfRel());

return model;
```

Ở đây `OrderModel` sở hữu các trường của representation và các link. Client nhận một cấu trúc được thiết kế cho API mà không cần biết domain entity được tổ chức ra sao.

Nên chọn model tùy chỉnh khi:

- Representation có trường tổng hợp hoặc trường trình bày không thuộc DTO hiện tại.
- Nhiều endpoint cần dùng chung một hình dạng response ổn định.
- Muốn kiểm soát rõ trường nào được công bố và cách đặt tên trường.
- Có nhu cầu tạo một kiểu model có ý nghĩa trong hợp đồng API.

Không nên tạo lớp riêng chỉ để thay đổi tên biến nội bộ hoặc thêm một link đơn lẻ. Những trường hợp đó thường có thể dùng DTO kết hợp `EntityModel`.

## `CollectionModel<T>`: biểu diễn tập hợp

Chọn `CollectionModel<T>` khi response chứa nhiều phần tử và cần có thể thêm link ở cấp collection. Một collection có thể rỗng mà vẫn mang các link như `self`, `create` hoặc `search`.

Ví dụ, danh sách đơn hàng có thể chứa `EntityModel<OrderView>` để mỗi phần tử có link riêng:

```java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping
CollectionModel<EntityModel<OrderView>> all() {
    List<EntityModel<OrderView>> items = orders.findAll().stream()
        .map(this::toModel)
        .toList();

    return CollectionModel.of(items,
        linkTo(methodOn(OrderController.class).all()).withSelfRel());
}
```

`toModel` ở đây là phương thức chuyển một `OrderView` thành `EntityModel<OrderView>`. Cấu trúc generic `CollectionModel<EntityModel<OrderView>>` nói rõ rằng collection chứa các phần tử có model riêng, còn collection cũng có link riêng.

Có thể dùng `CollectionModel<OrderView>` nếu từng phần tử không cần link riêng:

```java
CollectionModel<OrderView> model = CollectionModel.of(
    orders.findAll(),
    linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Lựa chọn giữa hai dạng phụ thuộc vào hợp đồng cần công bố. Nếu client cần điều hướng từ từng đơn hàng đến chi tiết hoặc thao tác tương ứng, hãy bọc từng phần tử bằng `EntityModel` hoặc model tùy chỉnh. Nếu collection chỉ là danh sách dữ liệu tham chiếu đơn giản, model cho từng phần tử có thể không cần thiết.

## `PagedModel<T>`: biểu diễn tập hợp có phân trang

Chọn `PagedModel<T>` khi API trả về một trang trong collection lớn. Ngoài các phần tử, response cần công bố metadata như kích thước trang, số trang hiện tại, tổng số phần tử và tổng số trang. Các link điều hướng giúp client chuyển trang mà không cần tự ghép URL.

`PagedModel<T>` là một dạng collection model có thêm metadata trang. Generic `T` chỉ kiểu phần tử trong trang; ví dụ `PagedModel<EntityModel<OrderView>>` là một trang mà từng đơn hàng có representation và link riêng.

Có thể tạo `PagedModel` trực tiếp từ phần tử và `PageMetadata`:

```java
import java.util.List;

import org.springframework.hateoas.PagedModel;
import org.springframework.hateoas.EntityModel;

List<EntityModel<OrderView>> content = page.getContent().stream()
    .map(this::toModel)
    .toList();

PagedModel.PageMetadata metadata = new PagedModel.PageMetadata(
    page.getSize(),
    page.getNumber(),
    page.getTotalElements(),
    page.getTotalPages());

return PagedModel.of(content, metadata,
    linkTo(methodOn(OrderController.class).all(pageable)).withSelfRel());
```

Ví dụ giả định `page` là một `Page<Order>` hoặc `Page<OrderView>` từ Spring Data, `pageable` là tham số phân trang và `toModel` tạo `EntityModel<OrderView>`. Trong ứng dụng Spring Data, `PagedResourcesAssembler` (tên API vẫn được dùng trong Spring Data) có thể chuyển `Page` thành `PagedModel` và sử dụng `RepresentationModelAssembler` để ánh xạ phần tử. Cách đó giúp giảm mã tạo metadata và các link phân trang.

Khi thiết kế response phân trang, cần thống nhất quy tắc `page` bắt đầu từ 0 hay 1, `size` tối đa, thứ tự sắp xếp và ý nghĩa `totalElements`. Client nên theo link `next` hoặc `prev` mà server cung cấp, thay vì tự đoán cấu trúc URL.

## Chọn generic đúng cho từng model

Các kiểu generic trong Spring HATEOAS có ý nghĩa khác nhau. Đây là điểm dễ nhầm khi mới sử dụng thư viện:

| Khai báo | Generic biểu thị | Cách đọc |
| --- | --- | --- |
| `RepresentationModel<OrderModel>` | Kiểu self của lớp model | `OrderModel` là một representation tùy chỉnh có link. |
| `EntityModel<OrderView>` | Kiểu dữ liệu được bọc | Một `OrderView` được bọc cùng link. |
| `CollectionModel<EntityModel<OrderView>>` | Kiểu của mỗi phần tử trong collection | Collection gồm nhiều đơn hàng, mỗi đơn có model riêng. |
| `PagedModel<EntityModel<OrderView>>` | Kiểu phần tử trong trang | Một trang đơn hàng, mỗi phần tử có link riêng. |
| `RepresentationModelAssembler<Order, EntityModel<OrderView>>` | Kiểu nguồn và kiểu model đích | Chuyển một đối tượng `Order` thành `EntityModel<OrderView>`. |

Ví dụ, generic trong `RepresentationModel<OrderModel>` không chứa `OrderView`. Nếu cần giữ dữ liệu `OrderView` mà không tạo lớp model mới, dùng `EntityModel<OrderView>`. Nếu cần trường riêng, tạo `OrderModel extends RepresentationModel<OrderModel>` và khai báo trực tiếp các trường đó.

## Dùng assembler khi cần chọn model nhất quán

Khi nhiều endpoint cùng trả một loại resource, `RepresentationModelAssembler` giúp gom logic ánh xạ. Kiểu nguồn `S` thường là domain object hoặc DTO; kiểu đích `D` là một kiểu kế thừa `RepresentationModel`.

Ví dụ assembler bọc DTO bằng `EntityModel`:

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
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel(),
            linkTo(methodOn(OrderController.class).all()).withRel("orders"));
    }
}
```

Controller có thể tiêm assembler qua constructor rồi sử dụng `toModel(...)` cho một phần tử. Với collection, có thể dùng `toCollectionModel(...)` hoặc tạo `CollectionModel` thủ công nếu cần link riêng ở cấp collection. Với trang dữ liệu, kết hợp assembler với `PagedResourcesAssembler` để giữ cách biểu diễn phần tử nhất quán.

Assembler cũng có thể trả về model tùy chỉnh:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.server.RepresentationModelAssembler;

class OrderModelAssembler
        implements RepresentationModelAssembler<Order, OrderModel> {

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = new OrderModel(
            order.getId(),
            order.getStatus().name(),
            statusLabel(order.getStatus()),
            order.getTotal());

        model.add(linkTo(methodOn(OrderController.class)
            .one(order.getId())).withSelfRel());

        return model;
    }
}
```

Ví dụ thứ hai giả định domain `Order` có các getter tương ứng và `OrderModel` đã được định nghĩa ở phần trước. Khi dùng model tùy chỉnh, assembler trả trực tiếp `OrderModel`; không cần bọc nó vào `EntityModel<OrderModel>`.

## Cấu trúc HAL theo kiểu model

Các kiểu model khác nhau tạo ra những hình dạng response khác nhau. Với HAL, link được đặt trong `_links`; collection thường dùng `_embedded` để chứa các phần tử nhúng.

`EntityModel<OrderView>` có dạng đơn giản:

```json
{
  "id": "ord-1042",
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": { "href": "/api/orders/ord-1042" },
    "orders": { "href": "/api/orders" }
  }
}
```

`CollectionModel<EntityModel<OrderView>>` có thể được biểu diễn như sau:

```json
{
  "_embedded": {
    "orderViewList": [
      {
        "id": "ord-1042",
        "status": "PENDING",
        "total": 125000,
        "_links": {
          "self": { "href": "/api/orders/ord-1042" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/api/orders" }
  }
}
```

Tên relation trong `_embedded` có thể được cấu hình qua `@Relation` hoặc cơ chế relation provider. Không nên để client phụ thuộc vào tên mặc định được suy ra từ class Java nếu tên đó không phải hợp đồng đã thống nhất. Hãy công bố và kiểm thử relation nhúng.

`PagedModel` bổ sung phần metadata trang và các link điều hướng. Hình dạng JSON cụ thể phụ thuộc cấu hình serializer và media type đang dùng. Client nên dựa trên các field metadata và relation mà API công bố thay vì phụ thuộc vào cách thư viện nội bộ tuần tự hóa class.

## Quy trình quyết định

Khi thiết kế một endpoint mới, có thể chọn model theo trình tự sau:

1. **Endpoint trả về một resource?** Nếu có DTO phù hợp và chỉ cần thêm link, chọn `EntityModel<DTO>`.
2. **Representation có các trường riêng?** Nếu có, tạo lớp kế thừa `RepresentationModel<YourModel>`.
3. **Endpoint trả về nhiều phần tử?** Chọn `CollectionModel<T>` và xác định mỗi phần tử có cần link riêng hay không.
4. **Collection có phân trang?** Chọn `PagedModel<T>` hoặc dùng `PagedResourcesAssembler` với `Page` của Spring Data.
5. **Logic ánh xạ được dùng ở nhiều nơi?** Tách sang `RepresentationModelAssembler<S, D>`.
6. **Có hành động phụ thuộc trạng thái?** Thêm link hoặc affordance có điều kiện trong assembler/model builder; vẫn kiểm tra điều kiện ở endpoint.

Quyết định nên dựa trên hợp đồng client cần dùng, không dựa trên số lượng class muốn tạo trong code. Model đơn giản giúp API dễ đọc; model tùy chỉnh chỉ nên xuất hiện khi nó giải quyết nhu cầu biểu diễn cụ thể.

## Kiểm thử lựa chọn model và hợp đồng response

Kiểm thử nên xác nhận cấu trúc response mà client sử dụng, bao gồm dữ liệu, relation và metadata phân trang. Ví dụ với `MockMvc`, kiểm tra endpoint đơn hàng trả về HAL có `self` và `orders`:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(orderId.toString()))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.orders.href").exists());
```

Với collection, kiểm tra link ở cấp collection và phần tử nhúng:

```java
mockMvc.perform(get("/api/orders")
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orderViewList").isArray());
```

Với trang dữ liệu, kiểm tra metadata và link điều hướng theo cấu trúc đã công bố, ví dụ:

```java
mockMvc.perform(get("/api/orders?page=0&size=10")
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.size").value(10))
    .andExpect(jsonPath("$.page.number").value(0))
    .andExpect(jsonPath("$._links.self.href").exists());
```

Tên embedded relation và đường dẫn metadata trong ví dụ cần khớp với cấu hình thực tế của ứng dụng. Hãy kiểm tra response đã serialize và cố định hợp đồng mong muốn trong test; không sao chép các JSON path ví dụ nếu serializer của dự án công bố cấu trúc khác.

Ngoài cấu trúc, cần kiểm thử các trường hợp collection rỗng, trang đầu/trang cuối, resource không tồn tại và hành động không khả dụng theo trạng thái. Nếu dùng assembler, kiểm thử riêng việc ánh xạ domain object sang model để phát hiện link sai hoặc trường dữ liệu bị lộ.

## Lỗi thường gặp khi chọn model

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `EntityModel` cho một collection | Một wrapper đơn bị dùng sai mục đích, khó biểu diễn link ở cấp tập hợp. | Dùng `CollectionModel` hoặc `PagedModel`. |
| Dùng `CollectionModel` cho trang dữ liệu lớn | Client thiếu metadata trang và link điều hướng chuẩn. | Dùng `PagedModel` hoặc `PagedResourcesAssembler`. |
| Hiểu generic của `RepresentationModel<T>` là payload | Khai báo self type sai hoặc cố bọc dữ liệu theo cách không cần thiết. | Dùng generic tự tham chiếu là lớp model; dùng `EntityModel<T>` nếu cần generic payload. |
| Bọc model tùy chỉnh trong `EntityModel` thêm lần nữa | Representation lồng nhau và có thể sinh JSON khó hiểu. | Trả trực tiếp lớp kế thừa `RepresentationModel`. |
| Trả `List<DTO>` khi cần hypermedia ở cấp collection | Không có nơi rõ ràng để đặt link `self`, `next` hoặc action ở cấp collection. | Trả `CollectionModel` hoặc `PagedModel`. |
| Đưa logic tạo link vào nhiều controller | Relation và URL dễ không nhất quán giữa các endpoint. | Dùng `RepresentationModelAssembler` hoặc một model builder dùng chung. |
| Kiểm thử class Java thay vì response thực tế | Lỗi serializer, embedded relation hoặc media type không được phát hiện. | Dùng MockMvc/WebTestClient kiểm tra response HAL đã serialize. |

## Ghi nhớ

- `EntityModel<T>` bọc một đối tượng có sẵn cùng link; generic `T` là kiểu payload.
- `RepresentationModel<T>` là nền tảng cho model tùy chỉnh; generic `T` là self type của model.
- `CollectionModel<T>` biểu diễn một tập hợp và link ở cấp collection; từng phần tử có thể là DTO, `EntityModel` hoặc model tùy chỉnh.
- `PagedModel<T>` biểu diễn tập hợp có metadata phân trang và link điều hướng.
- `RepresentationModelAssembler<S, D>` giúp ánh xạ một kiểu nguồn thành kiểu representation đích một cách nhất quán.
- Chọn model dựa trên hình dạng response và hợp đồng client cần sử dụng; tránh bọc lồng nhau hoặc tạo lớp riêng không cần thiết.
- Kiểm thử JSON HAL đã serialize, relation, link, embedded data và metadata trang để bảo vệ hợp đồng API.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – RepresentationModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/RepresentationModel.html)
- [Spring HATEOAS API – EntityModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)
- [Spring HATEOAS API – CollectionModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html)
- [Spring HATEOAS API – PagedModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/PagedModel.html)
- [Spring Data – PagedResourcesAssembler](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html)
