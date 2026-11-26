# Khi nào dùng support

Spring HATEOAS có hai cách phổ biến để xây assembler: triển khai trực tiếp `RepresentationModelAssembler<T, D>` hoặc kế thừa `RepresentationModelAssemblerSupport<T, D>`. Lớp `RepresentationModelAssemblerSupport` hữu ích khi resource có một self URI theo quy ước đơn giản dựa trên controller và ID của entity. Nó cung cấp sẵn cách khởi tạo resource model và tạo self link, giúp assembler tập trung vào dữ liệu response cùng các link nghiệp vụ.

Không phải assembler nào cũng cần lớp support. Nếu URI có cấu trúc đặc biệt, phụ thuộc nhiều path variable, hoặc cần kiểm soát toàn bộ cách tạo self link, triển khai `RepresentationModelAssembler` trực tiếp thường rõ ràng hơn. Lựa chọn phụ thuộc vào quy ước URI của API và mức độ tự động hóa thực sự giúp giảm code.

## `RepresentationModelAssemblerSupport` giải quyết việc gì?

Một assembler thường phải thực hiện ba việc:

1. Tạo representation từ domain object.
2. Thêm self link trỏ đến resource được biểu diễn.
3. Thêm các link quan hệ hoặc link hành động phù hợp với trạng thái hiện tại.

Với `RepresentationModelAssembler<T, D>`, ứng dụng tự định nghĩa cả ba bước trong `toModel(T entity)`. `RepresentationModelAssemblerSupport<T, D>` là lớp cơ sở hỗ trợ trường hợp phổ biến: self link được xây theo controller class và ID của entity.

Lớp support nhận controller class và resource model class trong constructor. Nó cung cấp `createModelWithId(id, entity)` để khởi tạo model thông qua `instantiateModel(entity)` và thêm self link theo quy ước controller/resource ID. Assembler ghi đè `instantiateModel` để tạo đúng kiểu resource; sau đó `toModel` có thể bổ sung các link riêng của nghiệp vụ.

Mô hình này phù hợp khi controller có mapping collection và item theo quy ước dễ dự đoán, chẳng hạn:

```text
GET /api/orders
GET /api/orders/{id}
```

ID của domain object được dùng làm định danh trong self URI của item. Lớp support giúp tránh lặp lại đoạn `linkTo(methodOn(...).one(id)).withSelfRel()` ở mọi assembler có cùng quy ước.

## Ví dụ resource model

Giả sử API công bố đơn hàng với mã, trạng thái và tổng tiền. Resource model kế thừa `RepresentationModel` để mang các link:

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;

public class OrderModel extends RepresentationModel<OrderModel> {

    private final UUID id;
    private final String status;
    private final BigDecimal totalAmount;

    public OrderModel(UUID id, String status, BigDecimal totalAmount) {
        this.id = id;
        this.status = status;
        this.totalAmount = totalAmount;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
```

`OrderModel` là representation dành cho API, không phải JPA entity. Nó chỉ công bố các trường cần thiết cho client và kế thừa cơ chế link từ `RepresentationModel`.

## Kế thừa RepresentationModelAssemblerSupport

Assembler khai báo controller và kiểu resource trong constructor:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.server.RepresentationModelAssemblerSupport;
import org.springframework.stereotype.Component;

@Component
public class OrderModelAssembler
        extends RepresentationModelAssemblerSupport<Order, OrderModel> {

    public OrderModelAssembler() {
        super(OrderController.class, OrderModel.class);
    }

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = createModelWithId(order.getId(), order);

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId())).withRel("cancel"));
        }

        model.add(linkTo(methodOn(OrderController.class)
                .all()).withRel("orders"));

        return model;
    }

    @Override
    protected OrderModel instantiateModel(Order order) {
        return new OrderModel(
                order.getId(),
                order.getStatus().name(),
                order.getTotalAmount());
    }
}
```

Điểm đáng chú ý:

- `super(OrderController.class, OrderModel.class)` cung cấp controller dùng để xây link và kiểu resource cần khởi tạo.
- `instantiateModel(Order order)` chịu trách nhiệm tạo nội dung resource model.
- `createModelWithId(order.getId(), order)` tạo model và self link theo quy ước controller cùng ID.
- `toModel` bổ sung link nghiệp vụ như `cancel` và link `orders`.

Trong ví dụ, `Order`, `OrderStatus` và `canBeCancelled()` là kiểu hoặc quy tắc domain do ứng dụng định nghĩa. Lớp support không tự biết nghiệp vụ hủy đơn; assembler chỉ công bố link dựa trên thông tin đã có trong entity.

## Controller theo quy ước URI

Lớp support phát huy tác dụng khi mapping controller khớp với quy ước self URI mà assembler cần tạo:

```java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    OrderModel one(@PathVariable UUID id) {
        return assembler.toModel(service.findById(id));
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    CollectionModel<OrderModel> all() {
        return assembler.toCollectionModel(service.findAll())
                .add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @PostMapping("/{id}/cancellation")
    void cancel(@PathVariable UUID id) {
        service.cancel(id);
    }
}
```

Controller điều phối HTTP và gọi service/assembler. `toCollectionModel` ánh xạ từng entity trong collection qua `toModel`; self link của collection được thêm riêng vì collection là một tài nguyên ở cấp khác với từng item. Link `cancel` được assembler thêm theo điều kiện domain.

Trong một ứng dụng thực tế, endpoint hủy thường trả `ResponseEntity<Void>` hoặc một representation phù hợp với hợp đồng API. Phần chữ ký `void` ở đây chỉ làm rõ mapping mà link builder tham chiếu. `methodOn` mô tả method controller để dựng URI; nó không gọi endpoint và không thực hiện thao tác hủy.

## Khi nào nên dùng lớp support?

Nên cân nhắc `RepresentationModelAssemblerSupport` khi các điều kiện sau đúng:

- Resource model là một kiểu cụ thể kế thừa `RepresentationModel`.
- Mỗi item có một ID ổn định được dùng trong URI.
- Self URI tuân theo quy ước controller và ID, ví dụ `/api/orders/{id}`.
- Nhiều assembler có cùng quy tắc tạo self link và muốn tái sử dụng cơ chế đó.
- Phần tùy biến chủ yếu nằm ở cách tạo resource model và các link bổ sung.

Ví dụ điển hình là API quản lý `Order`, `Customer` hoặc `Product`, mỗi loại có endpoint chi tiết theo ID và resource model tương ứng. Lớp support giảm boilerplate ở self link, đồng thời giữ phép chuyển đổi domain-to-resource trong assembler.

## Khi nào không nên dùng?

Không nên chọn lớp support chỉ vì nó có chữ `Support`. Nếu self URI của resource không theo quy ước controller + ID, phần tự động có thể che khuất logic cần thiết hoặc tạo link không đúng ý nghĩa.

| Tình huống | Lựa chọn phù hợp hơn | Lý do |
| --- | --- | --- |
| URI nested như `/orders/{orderId}/items/{itemId}` | Support với overload có URI variables nếu mapping phù hợp; nếu không thì assembler trực tiếp | Self link cần cả ID cha và ID con. |
| Resource có canonical URI khác mapping controller | Assembler trực tiếp hoặc abstraction link riêng | URI nhận diện không thể suy ra đơn giản từ controller + ID. |
| Một DTO được biểu diễn ở nhiều endpoint với self link khác nhau | Assembler riêng theo representation | Cùng dữ liệu nhưng ngữ cảnh link khác nhau. |
| Cần tạo URI từ query, tenant hoặc ngữ cảnh người dùng | Assembler trực tiếp và link builder tường minh | Link phụ thuộc nhiều tham số ngoài ID. |
| Chỉ bọc DTO bằng `EntityModel<DTO>` và muốn kiểm soát rõ từng link | `RepresentationModelAssembler` trực tiếp | Cách triển khai thẳng thường dễ đọc hơn. |

Với nested resource, `RepresentationModelAssemblerSupport` có overload `createModelWithId(id, entity, parameters...)` để truyền thêm URI variables cho mapping của controller. Nếu route phù hợp với quy ước này, vẫn có thể dùng support class. Nếu self URI cần logic riêng, nhiều nguồn tham số hoặc canonical URI khác mapping, assembler trực tiếp với `linkTo(methodOn(...))` sẽ dễ kiểm soát hơn.

Ví dụ, nếu controller có class-level mapping `/api/orders/{orderId}/items` và item dùng `/{itemId}`, parent ID có thể được truyền vào overload:

```java
OrderItemModel model = createModelWithId(item.getId(), item, orderId);
```

Đoạn gọi này tạo model và self link dựa trên controller mapping cùng URI variable bổ sung. Hãy kiểm thử href thực tế để xác nhận thứ tự và số lượng biến khớp với mapping.

## So sánh hai cách triển khai

| Tiêu chí | `RepresentationModelAssembler` | `RepresentationModelAssemblerSupport` |
| --- | --- | --- |
| Dạng triển khai | Implement interface | Extend abstract support class |
| Tạo resource | Tự tạo trong `toModel` | Override `instantiateModel` |
| Self link | Tự thêm bằng link builder | Có thể dùng `createModelWithId` theo controller và ID |
| Độ linh hoạt URI | Cao, kiểm soát từng tham số | Phù hợp nhất với quy ước controller/resource ID |
| Mức boilerplate | Nhiều hơn nếu lặp self link | Ít hơn với resource có URI chuẩn |
| Phù hợp | URI tùy biến, nhiều ngữ cảnh | CRUD resource có ID và mapping nhất quán |

Lớp support là một tiện ích trên nền assembler, không phải một kiến trúc bắt buộc. Hai cách đều có thể tạo resource model, collection và link. Hãy chọn cách làm cho ý nghĩa URI rõ ràng nhất với người đọc code.

## Dùng assembler thuần khi cần kiểm soát URI

Ví dụ dòng hàng thuộc một đơn hàng có self URI `/api/orders/{orderId}/items/{itemId}`. Vì URI cần cả hai ID, assembler có thể tự tạo link:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderItemAssembler
        implements RepresentationModelAssembler<OrderItem, EntityModel<OrderItemDto>> {

    @Override
    public EntityModel<OrderItemDto> toModel(OrderItem item) {
        OrderItemDto dto = new OrderItemDto(
                item.getId(), item.getProductCode(), item.getQuantity());

        return EntityModel.of(dto,
                linkTo(methodOn(OrderItemController.class)
                        .one(item.getOrder().getId(), item.getId())).withSelfRel(),
                linkTo(methodOn(OrderController.class)
                        .one(item.getOrder().getId())).withRel("order"));
    }
}
```

`OrderItemDto` có thể được định nghĩa riêng như sau:

```java
import java.util.UUID;

public record OrderItemDto(UUID id, String productCode, int quantity) {
}
```

Assembler thuần cho thấy rõ cả `orderId` và `itemId` tham gia vào URI. Đây là lựa chọn phù hợp khi mapping không thể biểu diễn gọn bằng overload của support class hoặc self URI cần được xây theo quy tắc riêng. Trong thực tế, nếu không muốn assembler truy cập quan hệ lazy của JPA, hãy truyền parent ID trong một projection hoặc input model đã được service chuẩn bị. Endpoint cũng phải xác minh item thực sự thuộc parent trước khi trả representation.

## Kiểm thử self link và link hành động

Kiểm thử HTTP xác nhận self link do `createModelWithId` tạo ra khớp URI mà API công bố. Ví dụ với MockMvc:

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
class OrderAssemblerSupportTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void supportAssemblerCreatesSelfLinkFromControllerAndId() throws Exception {
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

Fixture cần có đơn hàng với ID đã nêu. Nên có thêm test cho đơn hàng được phép và không được phép hủy để xác nhận relation `cancel` xuất hiện đúng điều kiện. Nếu ứng dụng triển khai sau reverse proxy hoặc có context path, kiểm tra URI được tạo trong cấu hình forwarded headers thực tế; không khóa test vào hostname cục bộ nếu hostname thay đổi theo môi trường.

## Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `createModelWithId(id, entity)` cho URI nested cần parent variable | Self link thiếu parent context hoặc sai route. | Truyền URI variables qua overload `createModelWithId(id, entity, parameters...)` hoặc tạo link tường minh. |
| Quên override `instantiateModel` | Không thể tạo resource model theo kiểu mong muốn. | Cài đặt phương thức khởi tạo model. |
| Controller mapping không theo quy ước ID | Self link tự động không khớp endpoint thực tế. | Kiểm tra mapping hoặc tự tạo link tường minh. |
| Nghĩ support tự thêm mọi link nghiệp vụ | Response chỉ có self link, thiếu relation cần thiết. | Tự thêm `cancel`, `items`, `customer` hoặc link phù hợp trong `toModel`. |
| Dùng support cho mọi assembler | Code bị ép vào một quy ước URI không phù hợp. | Chọn interface thuần khi cần kiểm soát URI hoặc ngữ cảnh. |
| Nhầm `methodOn` là gọi controller | Hiểu sai vòng đời hoặc tạo phụ thuộc bean. | Xem `methodOn` là mô tả mapping dùng để xây URI. |

## Nguyên tắc lựa chọn

- Dùng `RepresentationModelAssemblerSupport` khi self URI có thể tạo theo controller và ID một cách nhất quán.
- Override `instantiateModel` để tạo đúng resource representation.
- Dùng `createModelWithId` cho self link theo quy ước; thêm riêng các link nghiệp vụ trong `toModel`.
- Dùng overload `createModelWithId(id, entity, parameters...)` cho nested URI khi controller mapping và URI variables phù hợp; chuyển sang assembler trực tiếp khi cần logic link tùy biến.
- Không để assembler truy vấn database hay thực hiện quy tắc domain.
- Kiểm thử href thực tế, relation tùy điều kiện và media type HAL.

`RepresentationModelAssemblerSupport` phù hợp khi nó loại bỏ được phần lặp mà không che khuất quy tắc URI. Với resource có self path chuẩn theo controller và ID, lớp support làm assembler gọn hơn; một số nested route cũng có thể dùng overload truyền URI variables. Khi URI có logic riêng hoặc không khớp quy ước của lớp support, assembler trực tiếp giữ cho cách tạo link minh bạch và dễ kiểm soát.
