# RepresentationModelAssemblerSupport

`RepresentationModelAssemblerSupport<T, D>` là lớp cơ sở tiện ích trong Spring HATEOAS dành cho những assembler chuyển một domain object thành một representation model. Lớp này triển khai hợp đồng `RepresentationModelAssembler<T, D>` và cung cấp các phương thức hỗ trợ khởi tạo model cùng link `self` dựa trên controller và định danh tài nguyên.

Khi dùng `RepresentationModelAssembler` trực tiếp, ứng dụng tự tạo model và tự gắn các link cần thiết. Khi kế thừa `RepresentationModelAssemblerSupport`, assembler khai báo controller quản lý resource và kiểu model đích một lần; phương thức `createModelWithId(...)` giúp tạo model kèm self link. Cách này phù hợp khi URI item theo quy ước controller mapping và muốn giảm mã lặp trong từng assembler.

## Vai trò của assembler trong Spring HATEOAS

Assembler nằm giữa mô hình nghiệp vụ và representation HTTP:

1. Controller hoặc service lấy domain object, ví dụ `Order`.
2. Assembler chọn dữ liệu được công bố và chuyển nó thành model, ví dụ `OrderModel`.
3. Assembler bổ sung link `self` và những link quan hệ khác như `orders` hoặc `customer`.
4. Controller trả model; Spring HATEOAS và message converter serialize thành HAL JSON hoặc media type hypermedia đã chọn.

`RepresentationModelAssemblerSupport` hỗ trợ bước tạo model và self link. Nó không thay thế domain service, không quyết định quyền truy cập, không tự thực hiện nghiệp vụ và không tự định nghĩa toàn bộ link hành động của tài nguyên.

## Cấu trúc kiểu generic

Lớp có hai tham số kiểu:

| Tham số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `T` | Kiểu đối tượng nguồn, thường là domain entity hoặc DTO | `Order` |
| `D` | Kiểu representation model đích, phải kế thừa `RepresentationModel` | `OrderModel` |

Ví dụ, `RepresentationModelAssemblerSupport<Order, OrderModel>` nhận một `Order` và trả về `OrderModel`. `OrderModel` thường kế thừa `RepresentationModel<OrderModel>` để có thể mang các link hypermedia.

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;

public class OrderModel extends RepresentationModel<OrderModel> {

    private final UUID id;
    private final String status;
    private final BigDecimal total;

    public OrderModel(UUID id, String status, BigDecimal total) {
        this.id = id;
        this.status = status;
        this.total = total;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
```

Model này chỉ công bố mã, trạng thái và tổng tiền. Domain entity có thể chứa thêm quan hệ persistence, dữ liệu nội bộ hoặc logic nghiệp vụ; assembler quyết định trường nào được đưa vào representation.

## Khai báo RepresentationModelAssemblerSupport

Assembler kế thừa `RepresentationModelAssemblerSupport` và gọi constructor với hai lớp:

- Controller expose tài nguyên.
- Kiểu representation model mà assembler tạo ra.

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.server.mvc.RepresentationModelAssemblerSupport;
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

        model.add(linkTo(methodOn(OrderController.class).all())
            .withRel("orders"));

        return model;
    }

    @Override
    protected OrderModel instantiateModel(Order order) {
        return new OrderModel(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );
    }
}
```

`createModelWithId(order.getId(), order)` tạo một `OrderModel` bằng `instantiateModel(...)` và thêm link `self` dựa trên controller cùng ID. Sau đó assembler bổ sung link `orders` trỏ tới collection. `instantiateModel(...)` được override để tạo model bằng constructor có tham số; cách này không phụ thuộc vào constructor rỗng của model.

Trong ví dụ, `Order`, `OrderController` và các getter là thành phần của ứng dụng. `OrderController` cần có mapping item tương ứng, thường là `GET /orders/{id}`, và mapping collection `GET /orders`. `methodOn(...)` tạo lời gọi mô phỏng để Spring HATEOAS đọc mapping; nó không thực thi phương thức controller.

## createModelWithId() hoạt động thế nào?

`createModelWithId(...)` là phương thức tiện ích quan trọng của lớp support. Về mặt sử dụng, nó thực hiện hai việc:

1. Tạo instance của kiểu model đích thông qua `instantiateModel(entity)`.
2. Thêm link `self` tới item resource dựa trên controller đã khai báo trong constructor và ID được truyền vào.

Có hai dạng thường dùng:

```java
OrderModel model = createModelWithId(order.getId(), order);
```

Khi route item chỉ cần ID của tài nguyên, dùng dạng này.

```java
OrderModel model = createModelWithId(order.getId(), order, customerId);
```

Overload có tham số bổ sung dành cho controller mapping cần thêm path variable, chẳng hạn route nằm dưới `/customers/{customerId}/orders/{id}`. Các giá trị bổ sung phải khớp với các biến của mapping controller và thứ tự mà API của phiên bản Spring HATEOAS sử dụng để mở rộng URI. Hãy kiểm tra `href` được tạo trong test khi route có nhiều biến.

Phương thức này chỉ tạo self link theo quy ước controller và ID. Nó không tự thêm link collection, link `customer`, link `cancel` hoặc affordance nghiệp vụ. Những link đó cần được assembler bổ sung rõ ràng.

## Vai trò của instantiateModel()

`instantiateModel(T entity)` là điểm mở rộng cho cách tạo model đích. Cơ chế mặc định khởi tạo kiểu model bằng constructor mặc định; khi model chỉ có constructor có tham số hoặc cần ánh xạ trường theo quy tắc riêng, hãy override phương thức này.

Ví dụ:

```java
@Override
protected OrderModel instantiateModel(Order order) {
    return new OrderModel(
        order.getId(),
        order.getStatus().name(),
        order.getTotal()
    );
}
```

Việc tách `instantiateModel` khỏi `toModel` giúp hai trách nhiệm rõ ràng:

- `instantiateModel` tạo representation model từ dữ liệu nguồn.
- `toModel` quyết định cách hoàn thiện representation, bao gồm self link và các link quan hệ bổ sung.

Không nên đặt truy vấn database hoặc thay đổi trạng thái nghiệp vụ trong `instantiateModel`. Assembler nên tập trung vào việc ánh xạ dữ liệu và xây dựng hypermedia.

## Tích hợp assembler vào controller

Controller inject assembler và trả model đã được tạo:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.UUID;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.hateoas.CollectionModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderRepository repository;
    private final OrderModelAssembler assembler;

    OrderController(OrderRepository repository, OrderModelAssembler assembler) {
        this.repository = repository;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    OrderModel one(@PathVariable UUID id) {
        Order order = repository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
        return assembler.toModel(order);
    }

    @GetMapping
    CollectionModel<OrderModel> all() {
        List<OrderModel> models = repository.findAll().stream()
            .map(assembler::toModel)
            .collect(Collectors.toList());

        return CollectionModel.of(models,
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }
}
```

Đoạn controller minh họa endpoint item và collection. `OrderRepository` và `OrderNotFoundException` thuộc ứng dụng. Ví dụ dùng `Collectors.toList()` để tương thích với các phiên bản Java trước khi có `Stream.toList()`.

Mỗi phần tử trong collection được ánh xạ qua cùng assembler, do đó có self link riêng. Collection có link `self` của chính nó. Nếu endpoint cần phân trang, có thể dùng `PagedResourcesAssembler` để tạo `PagedModel` và các link trang; `RepresentationModelAssemblerSupport` vẫn có thể được dùng để ánh xạ từng phần tử.

## Mapping controller và đường dẫn lồng nhau

Constructor của `RepresentationModelAssemblerSupport` nhận controller class vì lớp support cần biết controller expose item resource. Mapping controller phải nhất quán với cách `createModelWithId` xây self URI.

Ví dụ route lồng:

```java
@RestController
@RequestMapping("/customers/{customerId}/orders")
class CustomerOrderController {

    @GetMapping("/{id}")
    OrderModel one(@PathVariable UUID customerId, @PathVariable UUID id) {
        // Truy vấn đơn hàng thuộc đúng khách hàng.
        return orderService.findModel(customerId, id);
    }
}
```

Assembler có thể truyền thêm giá trị path variable cho `createModelWithId`:

```java
@Override
public OrderModel toModel(Order order) {
    OrderModel model = createModelWithId(
        order.getId(), order, order.getCustomerId());
    return model;
}
```

Ở ví dụ này, `customerId` là path variable bổ sung của route cha. Cần kiểm tra mapping và URI kết quả trong integration test, đặc biệt khi controller có nhiều biến path, base path hoặc API version. Nếu cấu trúc URI quá đặc biệt hoặc không phù hợp với quy ước của lớp support, có thể dùng `RepresentationModelAssembler` trực tiếp cùng `WebMvcLinkBuilder` để kiểm soát link tường minh.

## So sánh với RepresentationModelAssembler trực tiếp

Hai cách đều tạo representation model nhưng có mức hỗ trợ khác nhau:

| Tiêu chí | `RepresentationModelAssembler` | `RepresentationModelAssemblerSupport` |
| --- | --- | --- |
| Cách dùng | Implement interface | Kế thừa lớp cơ sở |
| Khởi tạo model | Tự viết trong `toModel` | Có thể override `instantiateModel` |
| Tạo self link | Tự thêm link | Có `createModelWithId` hỗ trợ |
| Phụ thuộc controller | Không bắt buộc | Khai báo controller trong constructor |
| Mức kiểm soát | Tường minh, linh hoạt | Tiện lợi theo quy ước controller/item ID |
| Trường hợp phù hợp | URI đặc biệt, nhiều chiến lược link, logic biểu diễn riêng | Controller mapping rõ ràng và item URI theo ID |

Chọn lớp support khi quy ước controller và ID đủ để tạo self link một cách nhất quán. Chọn interface trực tiếp khi muốn kiểm soát hoàn toàn việc khởi tạo model, URI, relation hoặc khi link không thể suy ra từ một controller mapping đơn giản.

`RepresentationModelAssemblerSupport` nằm trong package `org.springframework.hateoas.server.mvc` và được thiết kế quanh cơ chế tạo link cho Spring MVC. Với controller WebFlux, nên implement `RepresentationModelAssembler` trực tiếp và dùng `WebFluxLinkBuilder`, vì builder reactive trả `Mono<Link>` và cần được kết hợp trong pipeline Reactor. Không đưa `WebMvcLinkBuilder` của lớp support vào một controller WebFlux chỉ để dùng lại cùng kiểu assembler.

## Kiểm thử RepresentationModelAssemblerSupport

Nên kiểm tra cả model được tạo và HTTP response sau serialization. Unit test có thể xác nhận dữ liệu và self link:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.hateoas.IanaLinkRelations;

Order order = new Order(orderId, OrderStatus.PENDING, total);

OrderModel model = assembler.toModel(order);

assertThat(model.getId()).isEqualTo(orderId);
assertThat(model.getStatus()).isEqualTo("PENDING");
assertThat(model.getLink(IanaLinkRelations.SELF)).isPresent();
assertThat(model.getLink("orders")).isPresent();
```

Với integration test dùng MockMvc và HAL JSON:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(orderId.toString()))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.orders.href").exists());
```

Test cần xác nhận self link kết thúc ở đúng route item và ID; collection link trỏ tới đúng collection; dữ liệu được công bố không chứa trường nội bộ; và các path variable bổ sung được mở rộng chính xác. Nếu ứng dụng chạy sau reverse proxy hoặc có context path, hãy kiểm tra base URI công khai trong cấu hình triển khai.

## Lỗi thường gặp

- **Khai báo sai controller class:** self link được tạo theo controller không quản lý tài nguyên.
- **Model không thể khởi tạo:** kiểu model cần constructor tham số nhưng không override `instantiateModel` theo cách phù hợp.
- **Quên gọi `createModelWithId`:** assembler tự tạo model nhưng không có self link như mong đợi.
- **Giả định có collection link tự động:** `createModelWithId` hỗ trợ self link; các relation khác cần được thêm riêng.
- **Thiếu path variable bổ sung:** route lồng nhau cần `customerId` nhưng chỉ truyền ID item.
- **Đưa nghiệp vụ vào assembler:** assembler truy vấn hoặc thay đổi dữ liệu thay vì chỉ ánh xạ representation.
- **Lặp link:** assembler tự thêm self link lần nữa sau khi `createModelWithId` đã thêm.
- **Dùng lớp support cho URI quá đặc biệt:** khi quy tắc URI không phù hợp với controller mapping, nên dùng assembler trực tiếp và builder tường minh.

`RepresentationModelAssemblerSupport` là lựa chọn tiện lợi khi mỗi domain type có controller expose rõ ràng và URI item có thể được tạo từ ID cùng mapping. Kết hợp `createModelWithId`, override `instantiateModel` khi cần, bổ sung các relation còn lại và kiểm thử response HAL giúp assembler tạo representation nhất quán mà không lặp lại logic dựng self link ở mọi nơi.
