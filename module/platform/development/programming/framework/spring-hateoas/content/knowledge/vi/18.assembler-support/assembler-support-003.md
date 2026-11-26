# Khai báo model class cho RepresentationModelAssemblerSupport

Khi xây dựng API bằng Spring HATEOAS, một assembler chuyển domain object thành representation model mà client có thể đọc và điều hướng. Nếu muốn tự định nghĩa class biểu diễn tài nguyên, bạn cần khai báo class đó kế thừa `RepresentationModel` và chọn kiểu generic phù hợp. Với Spring MVC, `RepresentationModelAssemblerSupport<T, D>` có thể giảm phần mã lặp khi khởi tạo model và thêm self link dựa trên controller cùng mã định danh của tài nguyên.

Bài học này tập trung vào cách khai báo model class, cách truyền kiểu model vào assembler support, yêu cầu constructor, cách ghi đè `instantiateModel(...)` và cách dùng `createModelWithId(...)`. Ví dụ xuyên suốt là API đơn hàng. Mục tiêu là phân biệt domain entity với representation class và tạo một model có cấu trúc rõ ràng, self link chính xác.

## 1. Model class trong Spring HATEOAS là gì?

Model class là kiểu Java mô tả dữ liệu mà API muốn công bố cho client. Nó có thể chứa một phần dữ liệu từ domain object, dữ liệu tổng hợp từ nhiều nguồn hoặc các trường được thiết kế riêng cho hợp đồng API. Model class có thể mang các liên kết hypermedia thông qua `RepresentationModel`.

Ví dụ, domain object `Order` có thể chứa thông tin thanh toán, ghi chú nội bộ và quan hệ tới nhiều entity khác. Client chỉ cần mã đơn hàng, trạng thái và tổng tiền. Ta có thể khai báo một model riêng:

```java
public class OrderModel extends RepresentationModel<OrderModel> {

    private UUID id;
    private String status;
    private BigDecimal total;

    public OrderModel() {
    }

    public UUID getId() {
        return id;
    }

    public void setId(UUID id) {
        this.id = id;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
```

`OrderModel` kế thừa `RepresentationModel<OrderModel>`, vì vậy model có thể nhận `Link` và các phương thức quản lý liên kết của Spring HATEOAS. Các getter giúp Jackson đọc thuộc tính để serialize response. Đây là representation class, không phải entity JPA và không cần chứa toàn bộ cấu trúc domain.

## 2. Vì sao generic phải trỏ tới chính model class?

Khai báo `RepresentationModel<OrderModel>` sử dụng generic self type. Tham số kiểu cho Spring HATEOAS biết kiểu model cụ thể đang kế thừa lớp cơ sở. Điều này giúp các thao tác fluent như `add(...)` trả về kiểu `OrderModel` thay vì một kiểu cha chung.

Ví dụ:

```java
OrderModel model = new OrderModel();

OrderModel result = model.add(Link.of("/orders/42").withSelfRel());
```

Nếu khai báo model khác, hãy truyền kiểu của model đó:

```java
public class CustomerModel extends RepresentationModel<CustomerModel> {
    // Các thuộc tính representation của khách hàng.
}
```

Không dùng `RepresentationModel<OrderModel>` cho `CustomerModel`. Self type cần phản ánh class con thực tế để hệ thống kiểu giữ được quan hệ đúng.

## 3. Phân biệt model class, DTO và domain entity

Ba kiểu này có thể có một số trường giống nhau nhưng phục vụ những mục đích khác nhau:

| Kiểu | Trách nhiệm | Có nên chứa hypermedia link? |
| --- | --- | --- |
| Domain entity (`Order`) | Mô hình nghiệp vụ, trạng thái và quy tắc của ứng dụng. | Thông thường không. |
| DTO (`OrderView`) | Chuyển dữ liệu giữa các lớp hoặc xác định payload API. | Có thể được bọc trong `EntityModel`. |
| Model class (`OrderModel`) | Mô tả representation công khai và có thể mang link. | Có, thông qua `RepresentationModel`. |

Không nên trả trực tiếp entity JPA chỉ vì nó đã có các trường cần thiết. Làm vậy có thể khiến cấu trúc API phụ thuộc vào schema lưu trữ, làm lộ trường nội bộ hoặc kéo theo quan hệ lazy. Model class cho phép chọn trường cần công bố và kiểm soát liên kết độc lập với domain.

Nếu một DTO đã đáp ứng hoàn toàn hợp đồng và chỉ cần thêm link, `EntityModel<OrderView>` có thể đơn giản hơn. Model class riêng phù hợp khi cần kiểu representation chuyên biệt, thuộc tính tùy biến hoặc muốn dùng `RepresentationModelAssemblerSupport` với resource type cụ thể.

## 4. Khai báo kiểu generic của RepresentationModelAssemblerSupport

`RepresentationModelAssemblerSupport<T, D>` là lớp cơ sở dành cho assembler trong Spring MVC. Hai tham số generic có ý nghĩa:

- `T`: kiểu domain object đầu vào, ví dụ `Order`.
- `D`: kiểu model đầu ra, phải kế thừa `RepresentationModel<?>`, ví dụ `OrderModel`.

Một khai báo assembler cơ bản:

```java
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
        model.setId(order.getId());
        model.setStatus(order.getStatus().name());
        model.setTotal(order.getTotal());
        return model;
    }
}
```

Constructor của lớp cơ sở nhận hai class:

- `OrderController.class` cho biết controller có mapping dùng để tạo URI self.
- `OrderModel.class` cho biết resource type cần được khởi tạo.

`createModelWithId(...)` tạo model và thêm self link dựa trên controller cùng ID. Sau đó assembler điền các trường dữ liệu công khai và trả về model.

## 5. Vai trò của constructor model class

Mặc định, `RepresentationModelAssemblerSupport` khởi tạo resource type bằng reflection và giả định model có no-argument constructor. Vì vậy, model class dùng cách khởi tạo mặc định cần có constructor không tham số có thể truy cập được theo cách reflection sử dụng.

Ví dụ:

```java
public class OrderModel extends RepresentationModel<OrderModel> {

    private UUID id;
    private String status;

    public OrderModel() {
    }

    // Getter và setter.
}
```

Nếu model chỉ khai báo constructor có tham số, Java không tự tạo constructor không tham số. Khi đó, cơ chế reflection mặc định có thể không khởi tạo được model. Bạn có hai lựa chọn: bổ sung no-arg constructor hoặc ghi đè `instantiateModel(...)` để tự tạo instance bằng constructor mong muốn.

Yêu cầu no-arg constructor ở đây liên quan tới cách assembler support khởi tạo model. Nó không có nghĩa mọi representation class trong mọi cách dùng Spring HATEOAS đều bắt buộc phải có constructor không tham số.

## 6. Ghi đè instantiateModel để dùng constructor riêng

Nếu muốn model bất biến với các trường `final`, có thể khai báo constructor đầy đủ và ghi đè `instantiateModel(T entity)`. Phương thức này nhận domain object và trả về instance của model class.

Model bất biến:

```java
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

Assembler khởi tạo model qua constructor:

```java
@Component
public class OrderModelAssembler
        extends RepresentationModelAssemblerSupport<Order, OrderModel> {

    public OrderModelAssembler() {
        super(OrderController.class, OrderModel.class);
    }

    @Override
    protected OrderModel instantiateModel(Order order) {
        return new OrderModel(
                order.getId(),
                order.getStatus().name(),
                order.getTotal()
        );
    }

    @Override
    public OrderModel toModel(Order order) {
        return createModelWithId(order.getId(), order);
    }
}
```

Trong trường hợp này, `createModelWithId(...)` gọi cơ chế khởi tạo model đã được ghi đè, sau đó thêm self link. `instantiateModel(...)` chỉ nên tạo và điền dữ liệu của model; không tự thêm self link ở đây vì `createModelWithId(...)` đã đảm nhiệm việc đó.

Ghi đè `instantiateModel` cũng giúp tránh việc tạo instance bằng reflection khi dự án muốn dùng constructor chuyên biệt. Chọn cách khởi tạo dựa trên cấu trúc model và nhu cầu kiểm soát dữ liệu.

## 7. Sử dụng createModelWithId để thêm self link

`createModelWithId(Object id, T entity)` là phương thức protected của `RepresentationModelAssemblerSupport`. Nó tạo model thông qua cơ chế `instantiateModel(...)` và thêm một link có relation `self` tới tài nguyên được định danh bởi ID.

Ví dụ:

```java
@Override
public OrderModel toModel(Order order) {
    OrderModel model = createModelWithId(order.getId(), order);
    model.add(Link.of("/customers/" + order.getCustomerId(), "customer"));
    return model;
}
```

Self link được tạo bởi `createModelWithId`; assembler chỉ bổ sung link `customer` tới tài nguyên liên quan. Trong ứng dụng thực tế, nên tạo link `customer` từ mapping controller tương ứng thay vì nối chuỗi URI thủ công.

Lớp cơ sở cũng có overload `createModelWithId(Object id, T entity, Object... parameters)` để truyền thêm tham số cho việc dựng link khi route cần chúng. Hãy kiểm tra URI được tạo trong test nếu controller có mapping phức tạp hoặc nhiều tham số. Với route không khớp mô hình controller mapping cộng ID đơn giản, có thể tạo link bằng `WebMvcLinkBuilder` trực tiếp trong assembler.

Không gọi `createModelWithId(...)` rồi lại thêm một link `self` thủ công cho cùng item. Làm vậy có thể tạo nhiều link cùng relation và khiến client khó xác định URI chính.

## 8. Mối quan hệ giữa controller class và model class

Constructor của `RepresentationModelAssemblerSupport` nhận class controller và class resource type. Hai class phục vụ hai nhiệm vụ riêng:

- Controller class cung cấp ngữ cảnh mapping để xây dựng self link.
- Model class xác định kiểu object được khởi tạo và trả về từ assembler.

Ví dụ controller:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderModel one(@PathVariable UUID id) {
        // Tải đơn hàng và trả representation.
    }
}
```

Assembler khai báo:

```java
public OrderModelAssembler() {
    super(OrderController.class, OrderModel.class);
}
```

Khi `createModelWithId(order.getId(), order)` được gọi, lớp cơ sở dùng controller class và ID để tạo self link. Cấu trúc thông dụng là controller có mapping cấp lớp `/orders` và endpoint chi tiết nhận ID. Nếu controller có nhiều route phức tạp, mapping lồng nhau hoặc route chi tiết không theo cấu trúc dự kiến, hãy xác minh `href` thực tế và cân nhắc dùng `linkTo(methodOn(...))` để chỉ rõ method đích.

## 9. Thêm các relation khác sau khi khởi tạo model

`RepresentationModelAssemblerSupport` giúp tạo instance và self link; nó không quyết định các relation nghiệp vụ khác. Sau khi tạo model, assembler có thể thêm các link cần thiết:

```java
@Override
public OrderModel toModel(Order order) {
    OrderModel model = createModelWithId(order.getId(), order);

    if (order.canBeCancelled()) {
        model.add(linkTo(methodOn(OrderController.class)
                .cancel(order.getId())).withRel("cancel"));
    }

    model.add(linkTo(methodOn(CustomerController.class)
            .getCustomer(order.getCustomerId())).withRel("customer"));

    return model;
}
```

Ví dụ này giả định controller có các method mapping tương ứng. `cancel` chỉ được công bố khi domain object cho biết đơn hàng có thể hủy. Tuy nhiên endpoint hủy vẫn phải kiểm tra quyền và trạng thái khi request thực sự đến; sự hiện diện của link không phải cơ chế phân quyền.

Tách việc tạo self link khỏi relation nghiệp vụ giúp model class giữ vai trò mô tả representation, còn assembler điều phối cách dữ liệu và link được công bố.

## 10. toCollectionModel được kế thừa như thế nào?

`RepresentationModelAssemblerSupport` triển khai `RepresentationModelAssembler`, vì vậy assembler có thể dùng `toCollectionModel(...)` mà không cần tự viết vòng lặp chuyển đổi collection.

```java
@GetMapping
CollectionModel<OrderModel> all() {
    CollectionModel<OrderModel> collection =
            orderModelAssembler.toCollectionModel(orderService.findAll());

    collection.add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
    return collection;
}
```

Phương thức `toCollectionModel` dùng `toModel(...)` cho từng `Order`, vì vậy mỗi `OrderModel` nhận self link qua `createModelWithId(...)`. Controller thêm self link riêng cho collection. Không lặp qua từng item để thêm lại `self` nếu assembler đã tạo.

`toCollectionModel` không tự tạo metadata phân trang hoặc các link `prev` và `next`. Nếu dữ liệu đầu vào là `Page<Order>` và API cần metadata trang, hãy dùng `PagedResourcesAssembler` để tạo `PagedModel`.

## 11. Khi nào nên dùng RepresentationModelAssemblerSupport?

Lớp hỗ trợ này phù hợp khi:

- Ứng dụng dùng Spring MVC.
- Model class là một kiểu cụ thể kế thừa `RepresentationModel`.
- Controller mapping và ID của tài nguyên đủ để tạo self link theo quy ước.
- Muốn tái sử dụng cơ chế khởi tạo model và tạo self link.
- Muốn tùy chỉnh constructor bằng cách ghi đè `instantiateModel(...)`.

Nếu chỉ cần bọc một DTO, `EntityModel.of(dto, links...)` và một assembler triển khai `RepresentationModelAssembler` trực tiếp có thể đơn giản hơn. Nếu route cần tạo URI tùy chỉnh hoặc phụ thuộc nhiều tham số, `WebMvcLinkBuilder` với `linkTo(methodOn(...))` có thể diễn đạt chính xác hơn.

`RepresentationModelAssemblerSupport` nằm trong package `org.springframework.hateoas.server.mvc`, vì vậy đây là tiện ích cho Spring MVC. Với Spring WebFlux, dùng `ReactiveRepresentationModelAssembler` và `WebFluxLinkBuilder` thay vì đưa lớp hỗ trợ MVC vào controller reactive.

## 12. Kiểm thử model class và assembler support

Kiểm thử nên xác nhận model được khởi tạo đúng, dữ liệu công khai đúng và self link được tạo đúng một lần.

Ví dụ kiểm thử assembler:

```java
@Test
void createsOrderModelWithSelfLink() {
    Order order = anOrderWithId(orderId);

    OrderModel model = assembler.toModel(order);

    assertThat(model.getId()).isEqualTo(orderId);
    assertThat(model.getStatus()).isEqualTo(order.getStatus().name());
    assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue();
    assertThat(model.getRequiredLink(IanaLinkRelations.SELF).getHref())
            .endsWith("/orders/" + orderId);
}
```

`anOrderWithId` đại diện cho fixture hoặc factory của dự án. Nếu assembler dùng mapping MVC để tạo URI, hãy thiết lập request context phù hợp trong unit test hoặc kiểm tra URI đầy đủ bằng kiểm thử web.

Kiểm thử collection:

```java
@Test
void createsACollectionOfOrderModels() {
    CollectionModel<OrderModel> result =
            assembler.toCollectionModel(List.of(firstOrder, secondOrder));

    assertThat(result.getContent()).hasSize(2);
    assertThat(result.getContent()).allSatisfy(model ->
            assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue()
    );
}
```

Kiểm thử HTTP bằng MockMvc để xác nhận serialization HAL:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.id").value(orderId.toString()))
    .andExpect(jsonPath("$._links.self.href")
            .value(endsWith("/orders/" + orderId)));
```

Ngoài ra, nên kiểm tra collection rỗng, item có ID khác nhau, URI không bị trùng và response qua reverse proxy nếu ứng dụng tạo URI tuyệt đối.

## 13. Các lỗi thường gặp khi khai báo model class

**Truyền sai kiểu generic.** Tham số `D` của assembler phải là model class thực tế. Nếu model là `OrderModel`, khai báo `RepresentationModelAssemblerSupport<Order, OrderModel>`.

**Quên generic self type.** Dùng `RepresentationModel<OrderModel>` để các thao tác fluent giữ kiểu cụ thể.

**Không có no-arg constructor khi dùng reflection mặc định.** `RepresentationModelAssemblerSupport` mặc định giả định constructor không tham số. Nếu model dùng constructor khác, hãy ghi đè `instantiateModel(...)`.

**Thêm self link hai lần.** `createModelWithId(...)` đã thêm relation `self`; không thêm cùng relation thủ công lần nữa.

**Thêm link trong instantiateModel.** Phương thức này nên tạo model và điền dữ liệu. Để `createModelWithId(...)` đảm nhiệm self link.

**Nhầm controller class với model class.** Controller class dùng để dựng URI; resource type dùng để khởi tạo representation.

**Dùng assembler MVC trong WebFlux.** Lớp hỗ trợ này thuộc package MVC. Dùng reactive assembler cho WebFlux.

**Đưa entity JPA trực tiếp vào representation.** Hãy chọn trường API cần công bố và chuyển đổi sang model class để tránh ràng buộc hợp đồng với cấu trúc lưu trữ.

## 14. Bài tập thực hành và tiêu chí hoàn thành

Hãy tạo model và assembler cho API đơn hàng:

1. Khai báo `OrderModel extends RepresentationModel<OrderModel>` với các trường `id`, `status`, `total`.
2. Tạo `OrderModelAssembler extends RepresentationModelAssemblerSupport<Order, OrderModel>`.
3. Gọi `super(OrderController.class, OrderModel.class)` trong constructor.
4. Triển khai `toModel` bằng `createModelWithId(order.getId(), order)`.
5. Thử model có no-arg constructor và model bất biến dùng constructor tham số.
6. Ghi đè `instantiateModel` cho phiên bản model bất biến.
7. Bổ sung link nghiệp vụ như `customer` hoặc `cancel` sau khi tạo self link.
8. Dùng `toCollectionModel` để chuyển danh sách và thêm self link riêng cho collection.
9. Viết test xác nhận trường dữ liệu, self link và response HAL.
10. Thử đổi mapping controller và kiểm tra URI được tạo từ mapping mới.

Bạn đã nắm được cách khai báo model class khi có thể chọn đúng kiểu generic, tách representation khỏi domain entity, hiểu yêu cầu constructor của assembler support, ghi đè `instantiateModel(...)` khi cần và dùng `createModelWithId(...)` để tạo self link nhất quán. Đây là nền tảng để xây dựng assembler Spring HATEOAS rõ ràng và dễ bảo trì.

## Tài liệu tham khảo chính thức

- [Spring HATEOAS Reference Documentation – Representation model assembler](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.representation-model-assembler)
- [RepresentationModelAssemblerSupport API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/RepresentationModelAssemblerSupport.html)
- [RepresentationModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/RepresentationModel.html)
