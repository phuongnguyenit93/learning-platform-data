# Self link cho entity

Một response đại diện cho một tài nguyên thường cần cho client biết URI để truy cập lại chính tài nguyên đó. Trong HATEOAS, quan hệ này được biểu diễn bằng link có relation `self`. Với Spring HATEOAS, có thể gắn self link vào `EntityModel` bằng `withSelfRel()` và tạo URI từ mapping của controller bằng `linkTo(...)` kết hợp `methodOn(...)`.

Self link là một phần quan trọng của hợp đồng hypermedia. Client có thể dùng nó để mở lại tài nguyên, làm mới dữ liệu, lưu tham chiếu hoặc tiếp tục khám phá các quan hệ khác. Client không cần tự ghép URL từ mã entity và quy ước route của server.

## `self` biểu thị điều gì?

Một link có hai thông tin chính:

- `rel` mô tả quan hệ giữa link và tài nguyên đang được biểu diễn.
- `href` cung cấp URI đích để client đi theo quan hệ đó.

Với relation `self`, URI đích nhận diện chính tài nguyên hiện tại. Ví dụ, response của đơn hàng có thể chứa:

```json
{
  "id": "7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042",
  "status": "PENDING",
  "totalAmount": 125000,
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042"
    }
  }
}
```

`id` là dữ liệu định danh mà API công bố; `self.href` là địa chỉ để client truy cập tài nguyên. Hai thông tin có liên quan nhưng không thay thế nhau. Client có thể hiển thị mã đơn hàng từ `id`, đồng thời theo `self` để lấy representation mới nhất.

`self` cũng không đồng nghĩa với mọi thao tác có thể thực hiện trên tài nguyên. Ví dụ, `self` thường dẫn đến endpoint đọc tài nguyên; hành động hủy đơn nên được công bố bằng relation riêng như `cancel`. Việc có self link không có nghĩa người dùng được quyền gọi mọi phương thức trên URI đó.

## Tạo self link từ mapping của controller

Spring HATEOAS cung cấp `WebMvcLinkBuilder` để tạo URI theo mapping Spring MVC. Hai API thường dùng là:

- `methodOn(Controller.class).method(arguments)` mô tả method controller và các tham số định tuyến.
- `linkTo(...)` chuyển mô tả method thành link theo mapping đã khai báo.
- `withSelfRel()` gán relation chuẩn `self` cho link.

Giả sử controller công bố endpoint chi tiết đơn hàng tại `GET /api/orders/{id}`:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    public OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    public EntityModel<OrderDto> one(@PathVariable UUID id) {
        Order order = service.findById(id);
        return assembler.toModel(order);
    }
}
```

Assembler tạo dữ liệu response và self link:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderDto>> {

    @Override
    public EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = new OrderDto(
                order.getId(),
                order.getStatus().name(),
                order.getTotalAmount());

        return EntityModel.of(dto,
                linkTo(methodOn(OrderController.class)
                        .one(order.getId())).withSelfRel());
    }
}
```

`OrderDto` là response DTO, còn `Order` là đối tượng domain được service trả về. Có thể định nghĩa DTO bằng record:

```java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderDto(
        UUID id,
        String status,
        BigDecimal totalAmount
) {
}
```

Khi `toModel` được gọi, assembler lấy ID từ entity để gọi đúng method controller. Spring HATEOAS phân tích mapping `/api/orders` và `/{id}`, sau đó tạo URI chứa ID tương ứng. Nếu route đổi, link builder sử dụng mapping mới mà assembler không phải tự sửa chuỗi URL.

## Gắn self link trực tiếp vào EntityModel

Nếu không cần assembler riêng, có thể tạo `EntityModel` ngay trong controller hoặc một mapper nhỏ:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;

EntityModel<OrderDto> model = EntityModel.of(dto);
model.add(linkTo(methodOn(OrderController.class)
        .one(order.getId())).withSelfRel());
```

`EntityModel.of(content, links...)` cũng cho phép truyền link ngay khi khởi tạo:

```java
EntityModel<OrderDto> model = EntityModel.of(
        dto,
        linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel());
```

Cả hai cách đều tạo ra một `EntityModel` chứa dữ liệu và link. Cách khởi tạo cùng link ngắn gọn khi số link ít; gọi `add(...)` hữu ích khi các link được thêm theo điều kiện hoặc qua nhiều bước. Với ứng dụng có nhiều endpoint trả về cùng loại tài nguyên, assembler giúp giữ quy tắc tạo self link nhất quán.

## Self link cho collection và phần tử

Collection và từng entity trong collection là hai tài nguyên ở hai cấp khác nhau. Collection có self link đến chính collection; mỗi phần tử có self link đến tài nguyên chi tiết của phần tử đó.

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

public CollectionModel<EntityModel<OrderDto>> all() {
    List<EntityModel<OrderDto>> orders = service.findAll().stream()
            .map(assembler::toModel)
            .toList();

    return CollectionModel.of(orders,
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
}
```

Trong ví dụ này, `assembler.toModel` tạo self link riêng cho từng đơn hàng. `CollectionModel.of` thêm self link cho collection. Do đó, client có thể theo self link của collection để truy cập danh sách và theo self link của một phần tử để mở chi tiết của đơn hàng đó.

## Đọc self link trong HAL

Khi response được serialize dưới dạng HAL, Spring HATEOAS đặt link trong `_links`. Relation là tên thuộc tính bên trong vùng này:

```json
{
  "id": "7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042"
    }
  }
}
```

Client nên tìm `_links.self.href` theo relation thay vì giả định URI luôn có dạng `/api/orders/{id}`. Khi server chuyển route sang `/v2/purchases/{id}`, client tuân theo self link vẫn có thể lấy URI mới từ response. Đây là một trong những lợi ích của hypermedia: server kiểm soát địa chỉ, còn client dựa vào quan hệ được công bố.

Với relation chuẩn, Spring HATEOAS cũng cung cấp hằng `IanaLinkRelations.SELF`. `withSelfRel()` là cách viết trực tiếp và dễ đọc khi tạo self link; hằng relation hữu ích khi cần so sánh hoặc tra cứu relation trong code.

## Self link và các quan hệ khác

Một representation thường có nhiều link với ý nghĩa riêng. Ví dụ:

| Relation | Ý nghĩa trong tài nguyên đơn hàng |
| --- | --- |
| `self` | URI của chính đơn hàng hiện tại. |
| `orders` | Collection đơn hàng. |
| `customer` | Khách hàng liên quan đến đơn hàng. |
| `invoice` | Hóa đơn của đơn hàng. |
| `cancel` | Endpoint hoặc affordance hủy đơn nếu thao tác khả dụng. |

Assembler có thể tạo nhiều link cùng lúc:

```java
EntityModel<OrderDto> model = EntityModel.of(dto,
        linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel(),
        linkTo(methodOn(OrderController.class)
                .all()).withRel("orders"));

if (order.canBeCancelled()) {
    model.add(linkTo(methodOn(OrderController.class)
            .cancel(order.getId())).withRel("cancel"));
}
```

Self link xác định tài nguyên hiện tại; các relation khác mở ra những tài nguyên hoặc khả năng liên quan. Không nên gán `self` cho link đến collection hoặc thao tác. Mỗi relation cần phản ánh đúng quan hệ của link với representation đang trả về.

## Kiểm thử self link

Kiểm thử qua HTTP xác nhận controller trả đúng media type, có self link và link trỏ đến đúng entity. Ví dụ với MockMvc:

```java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void detailContainsSelfLinkToRequestedOrder() throws Exception {
        String id = "7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042";

        mockMvc.perform(get("/api/orders/{id}", id)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href")
                        .value(endsWith("/api/orders/" + id)));
    }
}
```

Test cần có dữ liệu đơn hàng với UUID tương ứng trong fixture hoặc database kiểm thử. Nếu ứng dụng chạy sau reverse proxy hoặc dùng context path, hãy cấu hình forwarded headers phù hợp và kiểm thử URI sinh ra trong môi trường triển khai. Tránh khóa test vào hostname cục bộ nếu hostname có thể thay đổi; kiểm tra phần path hoặc kiểm tra URI theo cấu hình môi trường.

Các lỗi thường gặp khi tạo self link:

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không có `_links.self` | Chỉ trả DTO thuần hoặc quên thêm link vào model. | Trả `EntityModel`/`RepresentationModel` và thêm self link. |
| Self link trỏ đến collection | Dùng method `all()` thay vì method chi tiết khi tạo link cho entity. | Dùng `methodOn(...).one(entity.getId())`. |
| URI chứa ID sai | Lấy nhầm ID, truyền nhầm tham số hoặc ánh xạ sai controller method. | Dùng ID của entity đang chuyển đổi và kiểm thử href. |
| URL bị sai khi đổi route | Nối chuỗi URL bằng tay. | Tạo link từ mapping với `linkTo` và `methodOn`. |
| Self link bị coi là quyền truy cập | Client suy luận rằng có link nghĩa là luôn được phép gọi. | Kiểm tra xác thực, quyền và trạng thái tại endpoint mỗi lần request. |

## Nguyên tắc thiết kế

- Mỗi resource representation nên có một self link nhận diện đúng tài nguyên đó.
- Tạo href từ mapping controller để URI theo kịp thay đổi route.
- Dùng `withSelfRel()` cho relation `self`; dành relation riêng cho collection và hành động.
- Tạo self link cho từng item và self link riêng cho collection khi trả danh sách.
- Kiểm thử cả sự tồn tại lẫn đích của self link trong response HAL.
- Xem self link là thông tin điều hướng; endpoint vẫn chịu trách nhiệm xác thực và kiểm tra quyền.

Khi `EntityModel` có self link chính xác, client có thể khám phá URI của entity từ response và tiếp tục làm việc với tài nguyên mà không phải biết trước cấu trúc route nội bộ của server. Điều đó làm hợp đồng API rõ ràng hơn và giúp server có thể tổ chức lại URI trong khi vẫn giữ nguyên ý nghĩa của relation `self`.
