# Tạo model tự động

Khi một REST API trả về tài nguyên có hypermedia, mỗi response thường cần chuyển domain object thành DTO, thêm liên kết `self` và công bố những quan hệ điều hướng phù hợp. Nếu lặp lại các bước này trong từng controller, logic tạo representation dễ bị phân tán và không nhất quán.

Spring HATEOAS cung cấp `RepresentationModelAssembler` để tập trung việc chuyển đổi một domain object thành representation model. Lớp cơ sở `RepresentationModelAssemblerSupport` hỗ trợ thêm bằng cách khởi tạo model và tạo liên kết `self` từ controller cùng ID của tài nguyên. Nhờ đó, controller có thể ủy thác việc tạo model cho assembler và tập trung vào điều phối request.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vai trò của `RepresentationModelAssembler` trong việc chuyển domain object thành representation.
- Dùng `toModel()` và `toCollectionModel()` để tạo model cho một tài nguyên hoặc một tập hợp.
- Kế thừa `RepresentationModelAssemblerSupport` để tự động khởi tạo model và thêm liên kết `self`.
- Tùy biến `instantiateModel()` và bổ sung các liên kết nghiệp vụ.
- Tích hợp assembler vào Spring MVC controller.
- Kiểm thử dữ liệu, relation và URI trong representation được tạo tự động.

## Vì sao cần assembler?

Giả sử API quản lý đơn hàng có domain object và DTO như sau:

```java
import java.util.List;

record Order(long id, String status, long total) {
    public boolean canCancel() {
        return status.equals("NEW") || status.equals("SUBMITTED");
    }
}

record OrderView(long id, String status, long total) {
    static OrderView from(Order order) {
        return new OrderView(order.id(), order.status(), order.total());
    }
}

interface OrderService {
    Order findById(long id);
    List<Order> findAll();
    void cancel(long id);
}
```

Nếu controller tự tạo response cho từng endpoint, nó có thể phải lặp lại việc chuyển `Order` thành `OrderView`, tạo liên kết `self`, thêm `orders` và thêm `cancel` khi trạng thái cho phép. Khi có thêm endpoint tìm kiếm, phân trang hoặc thao tác nghiệp vụ, phần chuyển đổi có thể bị sao chép ở nhiều nơi.

Assembler gom logic đó thành một thành phần có trách nhiệm rõ ràng:

```text
Order (domain object)
        |
        v
OrderViewAssembler
        |  chuyển đổi content
        |  tạo self link
        |  thêm relation theo trạng thái
        v
EntityModel<OrderView>
        |
        v
HAL representation
```

Controller chỉ cần lấy domain object rồi gọi assembler. Cùng một assembler có thể được tái sử dụng ở endpoint chi tiết, endpoint thao tác và endpoint danh sách.

## `RepresentationModelAssembler` là gì?

`RepresentationModelAssembler<T, D>` là interface của Spring HATEOAS dùng để chuyển đối tượng nguồn kiểu `T` thành representation model kiểu `D`. Kiểu `D` phải kế thừa `RepresentationModel`.

Hai phương thức quan trọng:

| Phương thức | Vai trò |
|---|---|
| `toModel(T entity)` | Chuyển một domain object thành representation model |
| `toCollectionModel(Iterable<? extends T> entities)` | Chuyển một tập hợp domain object thành `CollectionModel<D>` |

Ví dụ, assembler có thể chuyển `Order` thành `EntityModel<OrderView>`:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderViewAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        EntityModel<OrderView> model = EntityModel.of(
            OrderView.from(order),
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel()
        );

        model.add(linkTo(methodOn(OrderController.class).all())
            .withRel("orders"));

        if (order.canCancel()) {
            model.add(linkTo(methodOn(OrderController.class).cancel(order.id()))
                .withRel("cancel"));
        }

        return model;
    }
}
```

Trong ví dụ, `toModel()` thực hiện ba việc:

1. Chuyển `Order` thành DTO `OrderView` để xác định dữ liệu công khai.
2. Tạo liên kết `self` tới endpoint chi tiết bằng `linkTo(methodOn(...))`.
3. Thêm relation `orders` và relation `cancel` khi đơn hàng có thể hủy.

`RepresentationModelAssembler` không tự suy ra mọi quy tắc nghiệp vụ. Bạn quyết định trường nào được công bố và liên kết nào xuất hiện trong representation. Nếu liên kết phụ thuộc quyền người dùng, hãy kiểm tra policy tương ứng trước khi thêm link.

## Dùng `toCollectionModel()` cho tập hợp

Interface cung cấp `toCollectionModel()` để chuyển từng phần tử qua `toModel()` và bọc kết quả trong `CollectionModel`. Controller có thể sử dụng như sau:

```java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orders;
    private final OrderViewAssembler assembler;

    OrderController(OrderService orders, OrderViewAssembler assembler) {
        this.orders = orders;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable long id) {
        return assembler.toModel(orders.findById(id));
    }

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        return assembler.toCollectionModel(orders.findAll())
            .add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @PostMapping("/{id}/cancellation")
    void cancel(@PathVariable long id) {
        orders.cancel(id);
    }
}
```

`toCollectionModel()` tạo representation cho các phần tử. Liên kết ở cấp collection như `self`, `search` hoặc `create` vẫn cần được thêm theo hợp đồng của endpoint. Đừng nhầm liên kết cấp collection với liên kết `self` của từng phần tử: assembler đã tạo các liên kết của item, còn controller hoặc một assembler cấp collection chịu trách nhiệm cho liên kết của tập hợp.

`CollectionModel` phù hợp với tập hợp không có metadata phân trang. Nếu API cần `page`, `size`, `totalElements`, `totalPages` và các liên kết `next`/`prev`, hãy dùng `PagedModel` cùng cơ chế assembler phân trang.

## Tạo model tự động bằng `RepresentationModelAssemblerSupport`

`RepresentationModelAssemblerSupport<T, D>` là lớp cơ sở trừu tượng triển khai `RepresentationModelAssembler`. Constructor nhận class controller và class model. Lớp cơ sở cung cấp `createModelWithId(...)` để khởi tạo model và thêm liên kết `self` dựa trên mapping controller cùng ID tài nguyên.

Đây là lựa chọn hữu ích khi API có quy ước item resource rõ ràng, chẳng hạn `GET /orders/{id}`. Ví dụ:

```java
import org.springframework.hateoas.server.mvc.RepresentationModelAssemblerSupport;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        extends RepresentationModelAssemblerSupport<Order, OrderModel> {

    OrderModelAssembler() {
        super(OrderController.class, OrderModel.class);
    }

    @Override
    protected OrderModel instantiateModel(Order order) {
        return new OrderModel(order.id(), order.status(), order.total());
    }

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = createModelWithId(order.id(), order);

        model.add(linkTo(methodOn(OrderController.class).all())
            .withRel("orders"));

        if (order.canCancel()) {
            model.add(linkTo(methodOn(OrderController.class).cancel(order.id()))
                .withRel("cancel"));
        }

        return model;
    }
}
```

Model đích kế thừa `RepresentationModel`:

```java
import org.springframework.hateoas.RepresentationModel;

class OrderModel extends RepresentationModel<OrderModel> {

    private final long id;
    private final String status;
    private final long total;

    OrderModel(long id, String status, long total) {
        this.id = id;
        this.status = status;
        this.total = total;
    }

    public long getId() { return id; }
    public String getStatus() { return status; }
    public long getTotal() { return total; }
}
```

Trong assembler:

- `super(OrderController.class, OrderModel.class)` đăng ký controller tạo URI và kiểu model cần khởi tạo.
- `instantiateModel(Order entity)` tạo model từ domain object. Mặc định lớp cơ sở dùng constructor không tham số; override phương thức này khi model cần constructor riêng hoặc muốn tránh khởi tạo bằng reflection.
- `createModelWithId(order.id(), order)` khởi tạo model và tự thêm liên kết `self` tới item resource theo quy ước controller.
- `toModel()` bổ sung các liên kết nghiệp vụ khác rồi trả model hoàn chỉnh.

`instantiateModel()` nhận chính entity nguồn và cần trả về model đã được tạo từ dữ liệu đó. Ví dụ dùng constructor của `OrderModel`, nên không cần constructor rỗng. Nếu model có constructor không tham số, có thể bỏ override để lớp cơ sở khởi tạo model bằng reflection.

Lớp cơ sở giả định controller có mapping item phù hợp để tạo URI từ ID. Nếu endpoint item dùng cấu trúc lồng phức tạp hoặc cần tham số bổ sung ngoài ID, hãy dùng `RepresentationModelAssembler` trực tiếp và tạo link bằng `linkTo(methodOn(...))` để kiểm soát đầy đủ mapping.

## So sánh hai cách triển khai

| Tiêu chí | `RepresentationModelAssembler` | `RepresentationModelAssemblerSupport` |
|---|---|---|
| Loại | Interface | Lớp cơ sở trừu tượng |
| Khởi tạo model | Tự triển khai trong `toModel()` | Có `instantiateModel(T entity)` và `createModelWithId()` |
| Liên kết `self` | Tự tạo bằng link builder | Có thể được thêm qua `createModelWithId()` |
| Mức độ linh hoạt | Toàn quyền chọn cách tạo representation | Theo quy ước controller và item ID |
| Khi nên dùng | Mapping phức tạp hoặc muốn kiểm soát toàn bộ link | Mapping item theo quy ước, cần tự động hóa việc tạo model và self link |

Không bắt buộc phải dùng lớp cơ sở. Với API nhỏ hoặc mapping không theo quy ước, triển khai interface trực tiếp thường dễ hiểu hơn. Dùng `RepresentationModelAssemblerSupport` khi quy ước tạo item URI phù hợp với cấu trúc controller và muốn tái sử dụng cơ chế thêm `self`.

## Tổ chức assembler trong ứng dụng

Assembler thường là Spring bean không giữ trạng thái request. Có thể đánh dấu bằng `@Component` và inject qua constructor vào controller:

Trong controller đã khai báo ở phần trước, constructor nhận `OrderViewAssembler` và lưu vào field `final`. Handler chi tiết chỉ cần gọi `assembler.toModel(orders.findById(id))`; handler danh sách gọi `assembler.toCollectionModel(orders.findAll())` rồi thêm liên kết cấp collection. Như vậy, các endpoint dùng chung một quy tắc chuyển đổi mà không cần khai báo lại DTO hoặc logic tạo relation.

Nên để service trả domain object hoặc projection phù hợp, assembler chịu trách nhiệm chuyển sang representation, còn controller chịu trách nhiệm nhận request và chọn endpoint. Cách phân chia này giúp cùng một quy tắc representation được sử dụng nhất quán ở nhiều luồng xử lý.

Không nên đặt logic truy vấn dữ liệu phức tạp hoặc thay đổi trạng thái nghiệp vụ trong assembler. Assembler nên tập trung vào việc chuyển đổi và liên kết. Nếu việc xác định hành động cần công bố cần kiểm tra quyền, hãy dùng policy hoặc service chuyên trách để lấy thông tin cần thiết và tránh lặp lại quy tắc bảo mật.

## Kiểm thử assembler và response

Có thể kiểm thử assembler độc lập để xác nhận content và relation:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

class OrderModelAssemblerTest {

    private final OrderModelAssembler assembler = new OrderModelAssembler();

    @BeforeEach
    void bindRequestContext() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setScheme("http");
        request.setServerName("localhost");
        request.setServerPort(8080);
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
    }

    @AfterEach
    void clearRequestContext() {
        RequestContextHolder.resetRequestAttributes();
    }

    @Test
    void createsModelWithSelfAndCancelLinksForNewOrder() {
        Order order = new Order(42L, "NEW", 1_250_000L);

        OrderModel model = assembler.toModel(order);

        assertThat(model.getId()).isEqualTo(42L);
        assertThat(model.getStatus()).isEqualTo("NEW");
        assertThat(model.getLink("self")).isPresent();
        assertThat(model.getLink("orders")).isPresent();
        assertThat(model.getLink("cancel")).isPresent();
    }

    @Test
    void doesNotCreateCancelLinkForShippedOrder() {
        Order order = new Order(42L, "SHIPPED", 1_250_000L);

        OrderModel model = assembler.toModel(order);

        assertThat(model.getLink("self")).isPresent();
        assertThat(model.getLink("cancel")).isEmpty();
    }
}
```

Các test này kiểm tra logic tạo model và relation. Khi dùng `WebMvcLinkBuilder`, test cần chạy trong ngữ cảnh có request để tạo URI tuyệt đối; nếu chỉ kiểm tra sự hiện diện của relation, có thể so sánh relation mà không phụ thuộc host/port.

Kiểm thử endpoint bằng MockMvc giúp xác nhận model được serialize thành HAL:

```java
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(OrderViewAssembler.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orders;

    @Test
    void returnsAssembledOrderAsHal() throws Exception {
        given(orders.findById(42L))
            .willReturn(new Order(42L, "NEW", 1_250_000L));

        mockMvc.perform(get("/orders/{id}", 42).accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.cancel.href").exists());
    }
}
```

Test slice cần đăng ký assembler và mock service. Nếu assembler dùng `RepresentationModelAssemblerSupport`, hãy bảo đảm `OrderModel` và mapping item của controller tương thích với cách lớp cơ sở tạo liên kết `self`. Có thể thêm test cho trạng thái không cho phép hủy để xác nhận relation `cancel` bị loại khỏi response.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Lặp chuyển DTO và tạo link trong nhiều controller | Representation thiếu nhất quán và khó bảo trì | Tập trung logic trong assembler |
| Nhầm domain type với representation type | API có thể lộ cấu trúc nội bộ của entity | Dùng DTO hoặc model chuyên cho API |
| Quên thêm link cấp collection | Client chỉ có link từng item, thiếu điều hướng tập hợp | Bổ sung relation ở cấp `CollectionModel` |
| Nghĩ `toCollectionModel()` tự thêm mọi link collection | Response thiếu `self`, `search` hoặc `create` | Tự thêm các link cấp collection theo hợp đồng |
| Dùng `RepresentationModelAssemblerSupport` khi mapping không theo quy ước | Link `self` được tạo sai hoặc không tạo được | Triển khai interface và dùng `linkTo(methodOn(...))` |
| Override `instantiateModel()` nhưng không chuyển dữ liệu nguồn | Model trả về thiếu content | Khởi tạo model từ entity được truyền vào |
| Đưa logic nghiệp vụ và truy vấn phức tạp vào assembler | Assembler khó kiểm thử và khó tái sử dụng | Để service xử lý nghiệp vụ, assembler chỉ chuyển đổi representation |
| Chỉ kiểm tra content mà bỏ qua relation | Hợp đồng hypermedia có thể bị phá vỡ | Kiểm thử cả `_links` và điều kiện xuất hiện link |

## Ghi nhớ

`RepresentationModelAssembler<T, D>` tập trung việc chuyển một domain object hoặc một tập hợp thành representation model. Dùng `toModel()` cho tài nguyên đơn lẻ và `toCollectionModel()` cho tập hợp; các link cấp collection cần được bổ sung theo hợp đồng API. Khi controller có mapping item theo quy ước, `RepresentationModelAssemblerSupport` giúp tạo model và thêm `self` qua `createModelWithId()`, còn `instantiateModel()` cho phép tùy biến cách khởi tạo DTO/model. Tách assembler khỏi controller giúp representation nhất quán, dễ kiểm thử và dễ tiến hóa khi API thay đổi.

## Tài liệu tham khảo

- [Spring HATEOAS – Representation model assembler](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.representation-model-assembler)
- [RepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [RepresentationModelAssemblerSupport API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/RepresentationModelAssemblerSupport.html)
