# Kết hợp với EntityModel

Trong Spring HATEOAS, `EntityModel<T>` là wrapper dùng để biểu diễn một resource đơn lẻ cùng các hypermedia link của nó. `T` là nội dung representation, thường là DTO hoặc view model mà API muốn công bố. `EntityModel` cho phép giữ dữ liệu và các liên kết trong cùng một đối tượng response, nhờ đó client vừa đọc được thông tin resource vừa khám phá được các đường dẫn liên quan.

Khi xây dựng assembler, ứng dụng thường chuyển domain object thành DTO trước, sau đó bọc DTO bằng `EntityModel` và gắn các link như `self`, `customer`, `items` hoặc `cancel`. Cách tổ chức này tách dữ liệu công khai khỏi chi tiết persistence, đồng thời gom quy tắc tạo hypermedia vào một nơi có thể tái sử dụng.

## 1. EntityModel là gì?

`EntityModel<T>` thuộc package `org.springframework.hateoas`. Đây là một kiểu con của `RepresentationModel`, được thiết kế để chứa nội dung của một resource và các link đi kèm.

Một representation đơn giản có thể gồm dữ liệu đơn hàng:

```json
{
  "id": "ORD-2048",
  "status": "PROCESSING",
  "total": 890000
}
```

Khi bọc nội dung đó bằng `EntityModel` và thêm link, response HAL có thể có dạng:

```json
{
  "id": "ORD-2048",
  "status": "PROCESSING",
  "total": 890000,
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/ORD-2048"
    },
    "customer": {
      "href": "https://api.example.test/customers/C-105"
    },
    "items": {
      "href": "https://api.example.test/orders/ORD-2048/items"
    }
  }
}
```

Trong HAL, nội dung của entity được serialize ở cấp resource cùng với `_links`. `EntityModel` không bọc DTO trong một thuộc tính tên `content`; nó cung cấp một representation có thể mang nội dung và link.

## 2. Phân biệt EntityModel với DTO và domain object

Ba kiểu đối tượng này có trách nhiệm khác nhau:

| Kiểu | Vai trò | Ví dụ |
| --- | --- | --- |
| Domain object | Mô hình nghiệp vụ và quy tắc miền | `Order` có trạng thái, tổng tiền và `canBeCancelled()` |
| DTO / representation | Dữ liệu được chọn để công bố qua API | `OrderRepresentation` có `id`, `status`, `total` |
| `EntityModel<T>` | Bọc representation cùng hypermedia link | `EntityModel<OrderRepresentation>` có `self`, `customer`, `items` |

Không bắt buộc `T` phải là entity JPA. Trong API thực tế, nên cân nhắc dùng DTO hoặc view model để kiểm soát trường nào được công bố. Trả trực tiếp entity persistence có thể làm lộ trường nội bộ, gây serialize quan hệ ngoài ý muốn hoặc khiến hợp đồng API phụ thuộc cấu trúc database.

Ví dụ DTO:

```java
import java.util.UUID;

public record OrderRepresentation(
        UUID id,
        String status,
        long total) {

    static OrderRepresentation from(Order order) {
        return new OrderRepresentation(
                order.getId(),
                order.getStatus().name(),
                order.getTotal());
    }
}
```

`OrderRepresentation.from(...)` chuyển dữ liệu cần công bố từ domain object. Sau đó assembler có thể bọc DTO này bằng `EntityModel` mà không đưa logic HTTP vào domain model.

## 3. Tạo EntityModel bằng factory method

Spring HATEOAS cung cấp các factory method để tạo `EntityModel`:

```java
import org.springframework.hateoas.EntityModel;

OrderRepresentation representation = OrderRepresentation.from(order);

EntityModel<OrderRepresentation> model = EntityModel.of(representation);
```

Đoạn code tạo một model chứa nội dung, chưa thêm link. Có thể thêm link sau khi khởi tạo:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

model.add(linkTo(methodOn(OrderController.class)
        .one(order.getId())).withSelfRel());
```

Hoặc truyền các link ngay khi gọi `EntityModel.of(...)`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

EntityModel<OrderRepresentation> model = EntityModel.of(
        representation,
        linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel(),
        linkTo(methodOn(CustomerController.class)
                .one(order.getCustomerId())).withRel("customer"));
```

Các cách trên tạo cùng loại kết quả: một `EntityModel` có content và các link. Dùng factory method giúp code thể hiện rõ kiểu model được tạo và tránh phải tự quản lý cấu trúc link trong DTO.

## 4. Gắn self link và link đến resource liên quan

Một resource thường có link `self` trỏ đến chính nó và các relation trỏ đến resource liên quan. Ví dụ đơn hàng có thể liên kết đến khách hàng và danh sách dòng hàng:

```java
import org.springframework.hateoas.EntityModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

EntityModel<OrderRepresentation> toModel(Order order) {
    return EntityModel.of(
            OrderRepresentation.from(order),
            linkTo(methodOn(OrderController.class)
                    .one(order.getId())).withSelfRel(),
            linkTo(methodOn(CustomerController.class)
                    .one(order.getCustomerId())).withRel("customer"),
            linkTo(methodOn(OrderItemController.class)
                    .allForOrder(order.getId())).withRel("items"));
}
```

`withSelfRel()` gắn relation chuẩn `self`. `withRel("customer")` và `withRel("items")` gắn các relation nghiệp vụ. Client có thể dựa vào relation để hiểu ý nghĩa của link mà không cần tự ghép URI từ ID.

Các controller và handler được tham chiếu trong ví dụ là thành phần của ứng dụng giả định. `methodOn(...)` tạo proxy mô tả lời gọi handler để dựng URI; nó không thực thi truy vấn hoặc logic nghiệp vụ trong controller.

Relation nên có tên ổn định và được dùng nhất quán trên toàn API. Với relation chuẩn đã có ý nghĩa phù hợp, có thể dùng hằng số trong `IanaLinkRelations`, ví dụ `IanaLinkRelations.SELF` hoặc `IanaLinkRelations.NEXT`.

## 5. Thêm link theo trạng thái resource

Các hành động có thể thực hiện thường phụ thuộc trạng thái nghiệp vụ. Ví dụ, đơn hàng ở trạng thái `DRAFT` có thể được hủy hoặc xóa, trong khi đơn hàng đã giao không còn khả năng đó. `EntityModel` cho phép thêm link có điều kiện:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

EntityModel<OrderRepresentation> model = EntityModel.of(
        OrderRepresentation.from(order),
        linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel());

if (order.canBeCancelled()) {
    model.add(linkTo(methodOn(OrderController.class)
            .cancel(order.getId())).withRel("cancel"));
}
```

Representation hiện tại sẽ chỉ quảng bá link `cancel` khi quy tắc nghiệp vụ cho phép. Client có thể dựa vào link để quyết định có hiển thị thao tác hủy hay không.

Việc ẩn link không phải cơ chế phân quyền. Client có thể lưu link từ response cũ hoặc tự gửi request đến URI mà nó biết. Endpoint vẫn phải xác thực người gọi, kiểm tra quyền và xác nhận trạng thái resource ở thời điểm xử lý request.

## 6. Kết hợp EntityModel với RepresentationModelAssembler

Khi nhiều endpoint cần biểu diễn cùng một loại resource, nên gom logic tạo `EntityModel` vào `RepresentationModelAssembler`. Interface này chuyển một đối tượng đầu vào thành một representation kế thừa `RepresentationModel`, vì vậy `EntityModel<T>` là kiểu trả về phù hợp.

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        EntityModel<OrderRepresentation> model = EntityModel.of(
                OrderRepresentation.from(order),
                linkTo(methodOn(OrderController.class)
                        .one(order.getId())).withSelfRel(),
                linkTo(methodOn(CustomerController.class)
                        .one(order.getCustomerId())).withRel("customer"));

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId())).withRel("cancel"));
        }

        return model;
    }
}
```

Assembler đảm nhận việc:

- Chuyển `Order` thành `OrderRepresentation`.
- Bọc DTO bằng `EntityModel`.
- Thêm `self` và link đến khách hàng.
- Thêm `cancel` khi trạng thái đơn hàng cho phép.

Controller không cần biết chi tiết cách dựng từng link:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
        return assembler.toModel(orderService.getRequired(id));
    }
}
```

Controller lấy domain object từ service rồi chuyển cho assembler. Assembler trả về `EntityModel<OrderRepresentation>` để Spring MVC serialize thành response theo media type đã cấu hình.

## 7. EntityModel trong collection

`EntityModel` biểu diễn một resource đơn lẻ. Khi trả về nhiều resource, có thể bọc từng phần tử bằng `EntityModel` rồi đặt chúng trong `CollectionModel`:

```java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

List<EntityModel<OrderRepresentation>> orders = orderService.findAll().stream()
        .map(orderAssembler::toModel)
        .collect(Collectors.toList());

CollectionModel<EntityModel<OrderRepresentation>> collection =
        CollectionModel.of(orders,
                linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Ví dụ giả định `OrderController` có handler `all()` được ánh xạ đến collection endpoint `/orders`. Nếu dự án dùng phân trang, hãy tạo `PagedModel` và các link trang từ kết quả phân trang thay vì thu thập toàn bộ danh sách như ví dụ đơn giản này.

Mỗi phần tử có các link riêng do assembler tạo; `CollectionModel` có thể có link `self`, `next` hoặc `prev` ở cấp tập hợp. Không nên dùng một `EntityModel` để đại diện cho cả danh sách nhiều resource. Hãy chọn kiểu wrapper phù hợp với cấp representation:

| Kiểu | Dùng cho |
| --- | --- |
| `EntityModel<T>` | Một resource có content và link |
| `CollectionModel<T>` | Một tập hợp representation có thể có link cấp collection |
| `PagedModel<T>` | Một tập hợp có metadata phân trang và link điều hướng |

## 8. Cấu trúc HAL khi serialize EntityModel

Khi ứng dụng xuất HAL, content của `EntityModel` được serialize cùng `_links`. Ví dụ:

```json
{
  "id": "ORD-2048",
  "status": "PROCESSING",
  "total": 890000,
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/ORD-2048"
    },
    "customer": {
      "href": "https://api.example.test/customers/C-105"
    },
    "cancel": {
      "href": "https://api.example.test/orders/ORD-2048/cancellation"
    }
  }
}
```

Đây là representation của một resource đơn lẻ nên content nằm ở root object. `_embedded` thường được dùng khi HAL biểu diễn resource liên quan được nhúng hoặc phần tử của collection. Không nên nhầm cấu trúc HAL của `EntityModel` với cấu trúc của `CollectionModel`.

Client có thể yêu cầu HAL bằng header:

```http
GET /orders/ORD-2048 HTTP/1.1
Host: api.example.test
Accept: application/hal+json
```

Spring Boot với starter HATEOAS thường tự cấu hình hỗ trợ HAL. Với cấu hình Spring thuần, ứng dụng cần bật hypermedia support và cấu hình converter phù hợp. Content negotiation quyết định representation được serialize theo media type nào.

## 9. EntityModel không thay thế Link hay RepresentationModel

Các kiểu trong Spring HATEOAS có quan hệ kế thừa và vai trò khác nhau:

- `Link` mô tả một liên kết, gồm URI đích và relation cùng metadata liên quan.
- `RepresentationModel<T>` là lớp cơ sở cho representation có thể chứa link.
- `EntityModel<T>` bọc một content object cùng các link.
- `CollectionModel<T>` bọc một tập hợp representation cùng link cấp collection.

Nếu response cần một kiểu dữ liệu tùy chỉnh có link, có thể kế thừa `RepresentationModel` trực tiếp. Nếu chỉ cần bọc một DTO hiện có cùng link, `EntityModel` thường ngắn gọn hơn.

Không nên thêm các trường `selfUrl`, `customerUrl` vào DTO chỉ để mô tả link. Cách đó trộn dữ liệu nghiệp vụ với cơ chế điều hướng HTTP và khiến client phụ thuộc vào cấu trúc DTO. Dùng `EntityModel` giúp link được biểu diễn theo cấu trúc hypermedia mà media type hỗ trợ.

## 10. Kiểm thử EntityModel

Có thể kiểm thử assembler ở mức unit bằng cách gọi `toModel(...)` và xác nhận content cùng các relation:

```java
import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;

import static org.assertj.core.api.Assertions.assertThat;

class OrderModelAssemblerTest {

    private final OrderModelAssembler assembler = new OrderModelAssembler();

    @Test
    void createsRepresentationWithSelfAndCustomerLinks() {
        Order order = OrderFixture.pendingOrder();

        EntityModel<OrderRepresentation> model = assembler.toModel(order);

        assertThat(model.getContent().id()).isEqualTo(order.getId());
        assertThat(model.getLink(IanaLinkRelations.SELF)).isPresent();
        assertThat(model.getLink("customer")).isPresent();
        assertThat(model.getLink("cancel")).isPresent();
    }
}
```

`OrderFixture.pendingOrder()` là fixture minh họa, cần tạo đơn hàng ở trạng thái có thể hủy. Nếu assembler phụ thuộc vào `EntityLinks` hoặc service khác, hãy inject mock phù hợp thay vì khởi tạo assembler bằng constructor rỗng. Test cũng nên có một trường hợp đơn hàng không thể hủy và xác nhận link `cancel` không xuất hiện.

Kiểm thử tích hợp với `MockMvc` xác nhận model được serialize thành HAL đúng cấu trúc:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").exists())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.customer.href").exists());
```

Test thực tế cần chuẩn bị dữ liệu hoặc mock service và cấu hình HAL. Nên xác nhận cả giá trị `href`, relation và content quan trọng, thay vì chỉ kiểm tra link tồn tại.

## 11. Lỗi thường gặp

**Trả DTO trực tiếp khi cần hypermedia:** DTO thuần không có API của Spring HATEOAS để gắn link. Bọc DTO bằng `EntityModel` nếu response cần link.

**Dùng domain entity làm content mà không kiểm soát:** có thể làm lộ trường persistence hoặc quan hệ nội bộ. Chuyển sang DTO/representation phù hợp trước khi bọc.

**Nhầm EntityModel với CollectionModel:** `EntityModel` dành cho một resource; collection nhiều resource nên dùng `CollectionModel` hoặc `PagedModel`.

**Đưa URL vào DTO:** điều này trộn dữ liệu với điều hướng và tạo hợp đồng riêng không cần thiết. Dùng link relation trong `EntityModel`.

**Thêm link mà không kiểm tra trạng thái:** link hành động cần phản ánh khả năng tại thời điểm response được tạo. Endpoint vẫn phải kiểm tra lại khi nhận request.

**Lặp logic tạo link ở nhiều controller:** assembler giúp tập trung cách chuyển đổi và gắn link cho cùng một loại resource.

**Chỉ kiểm tra content mà bỏ qua link:** representation HATEOAS gồm cả dữ liệu và khả năng điều hướng. Test cần xác nhận cả hai.

## 12. Checklist triển khai

- Chọn DTO hoặc representation làm kiểu content `T` của `EntityModel<T>`.
- Chuyển domain object sang dữ liệu công khai trước khi bọc.
- Dùng `EntityModel.of(content)` hoặc `EntityModel.of(content, links...)` để tạo model.
- Thêm `self` link và các relation có ý nghĩa bằng `add(...)` hoặc factory method.
- Dùng `RepresentationModelAssembler` khi logic dựng model được tái sử dụng.
- Chỉ công bố link hành động khi trạng thái và quyền hiện tại cho phép.
- Dùng `CollectionModel` hoặc `PagedModel` cho tập hợp, không dùng `EntityModel` thay thế collection.
- Xác nhận HAL serialize content ở root cùng `_links`.
- Kiểm thử content, relation, `href` và các trường hợp hành động khả dụng/không khả dụng.
- Giữ kiểm tra quyền và quy tắc nghiệp vụ ở endpoint/service.

`EntityModel` là cách trực tiếp để kết hợp một representation dữ liệu với hypermedia link trong Spring HATEOAS. Khi content được chọn rõ ràng, relation có ý nghĩa ổn định và assembler chịu trách nhiệm dựng model, controller có thể trả về tài nguyên giàu khả năng điều hướng mà vẫn giữ ranh giới rõ giữa dữ liệu nghiệp vụ và hợp đồng HTTP.
