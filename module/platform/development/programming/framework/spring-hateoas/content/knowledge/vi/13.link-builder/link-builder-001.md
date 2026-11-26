# WebMvcLinkBuilder

`WebMvcLinkBuilder` là công cụ của Spring HATEOAS dùng để tạo liên kết hypermedia từ mapping của Spring MVC controller. Thay vì tự ghép chuỗi URI, bạn có thể tham chiếu controller và phương thức xử lý request để tạo `Link` có đúng đường dẫn, path variable và các tham số request tương ứng.

Trong một REST API, liên kết cần phản ánh mapping đang được ứng dụng công bố. Nếu đường dẫn của controller thay đổi, các liên kết được tạo từ mapping sẽ tự cập nhật theo cấu hình mới. `WebMvcLinkBuilder` thường được dùng cùng `EntityModel`, `CollectionModel` và `RepresentationModelAssembler` để tạo representation có thể điều hướng.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vai trò của `WebMvcLinkBuilder` trong Spring HATEOAS.
- Dùng `linkTo(Class<?>)` để tạo liên kết từ mapping cấp controller.
- Dùng `slash(...)` để bổ sung path segment.
- Dùng `methodOn(...)` để tạo liên kết theo mapping của một phương thức controller.
- Kết hợp builder với `EntityModel` và assembler.
- Kiểm thử URI được tạo và xử lý context path hoặc reverse proxy phù hợp.

## Vì sao nên tạo link từ controller mapping?

Giả sử endpoint chi tiết đơn hàng có mapping:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    OrderView one(@PathVariable long id) {
        // Đọc đơn hàng theo ID.
        return OrderView.from(orders.findById(id));
    }
}
```

Một cách tạo liên kết thủ công là nối chuỗi:

```java
String href = "/orders/" + orderId;
```

Cách này lặp lại cấu trúc URI ở nhiều nơi. Nếu mapping đổi thành `/sales/orders/{id}`, code nối chuỗi cũ vẫn tạo `/orders/42` và có thể trả về liên kết không còn hợp lệ.

`WebMvcLinkBuilder` đọc metadata mapping từ Spring MVC để tạo URI. Nhờ vậy, controller vẫn là nguồn định nghĩa đường dẫn, còn assembler hoặc service biểu diễn tài nguyên có thể tham chiếu mapping đó mà không phải sao chép chuỗi URI.

## Các API chính

Các lớp và phương thức thường dùng nằm trong package `org.springframework.hateoas.server.mvc`:

| API | Vai trò |
|---|---|
| `WebMvcLinkBuilder.linkTo(Class<?>)` | Tạo builder từ mapping cấp controller |
| `WebMvcLinkBuilder.linkTo(methodOn(...))` | Tạo builder từ lời gọi proxy mô tả phương thức controller |
| `WebMvcLinkBuilder.methodOn(Class<T>)` | Tạo proxy để mô tả lời gọi controller và các tham số |
| `slash(Object)` | Bổ sung một path segment vào builder |
| `withSelfRel()` | Hoàn tất link với relation chuẩn `self` |
| `withRel(String)` | Hoàn tất link với relation được chỉ định |
| `toUri()` | Lấy URI cụ thể từ builder |

Trong đa số trường hợp, cách đọc và bảo trì dễ nhất là `linkTo(methodOn(...).method(args))`, vì code chỉ rõ endpoint cần tham chiếu và các tham số của nó.

Các ví dụ đơn hàng trong bài sử dụng những kiểu dữ liệu và service contract tối giản sau:

```java
import java.util.List;

record Order(long id, String status) {
    boolean canCancel() {
        return status.equals("NEW");
    }
}

record OrderView(long id, String status) {
    static OrderView from(Order order) {
        return new OrderView(order.id(), order.status());
    }
}

interface OrderService {
    List<Order> findAll();
    Order findById(long id);
    List<Order> search(String status, int page);
    void cancel(long id);
}
```

## Tạo link từ mapping cấp controller với `linkTo(Class<?>)`

`linkTo(OrderController.class)` tạo builder dựa trên mapping ở cấp class, ví dụ `@RequestMapping("/orders")`:

```java
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;

Link orders = linkTo(OrderController.class).withRel("orders");
```

Nếu controller có mapping `/orders`, liên kết sẽ trỏ đến URI tương ứng với mapping đó. Cách này phù hợp khi muốn tham chiếu endpoint gốc của controller.

### Bổ sung path segment bằng `slash(...)`

Builder có thể thêm một segment bằng `slash(...)`:

```java
Link order = linkTo(OrderController.class)
    .slash(42)
    .withSelfRel();
```

Với mapping cấp class `/orders`, link được tạo trỏ tới `/orders/42`. Có thể thêm nhiều segment liên tiếp:

```java
Link cancel = linkTo(OrderController.class)
    .slash(42)
    .slash("cancellation")
    .withRel("cancel");
```

Với mapping cấp class `/orders`, ví dụ tạo URI `/orders/42/cancellation`. `slash(...)` nối các thành phần của path. Nó không phải công cụ tạo query parameter. Với mapping có nhiều biến, mapping phức tạp hoặc tham số query, hãy tham chiếu trực tiếp phương thức controller bằng `methodOn(...)` để Spring HATEOAS xử lý theo metadata của mapping.

## Tạo link theo phương thức với `methodOn(...)`

`methodOn(...)` tạo một proxy mô tả controller. Khi gọi phương thức trên proxy, Spring HATEOAS ghi nhận phương thức và các tham số để xác định mapping. Phương thức controller thật không được thực thi trong quá trình tạo link.

```java
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(methodOn(OrderController.class).one(42L))
    .withSelfRel();
```

Spring HATEOAS đọc mapping `@RequestMapping("/orders")` ở cấp class và `@GetMapping("/{id}")` ở cấp phương thức, sau đó mở rộng path variable `id` bằng giá trị `42`. Kết quả là liên kết tới tài nguyên `/orders/42`.

`methodOn(...)` hữu ích vì không cần ghi lại đường dẫn và không cần gọi trực tiếp service chỉ để lấy URI. Phương thức được tham chiếu cần là handler mapping của Spring MVC, có annotation mapping mà Spring HATEOAS có thể phân tích.

### Controller với nhiều endpoint

Ví dụ controller có endpoint danh sách, chi tiết và hủy đơn hàng:

```java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orders;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orders, OrderModelAssembler assembler) {
        this.orders = orders;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        List<EntityModel<OrderView>> items = orders.findAll().stream()
            .map(assembler::toModel)
            .toList();

        return CollectionModel.of(
            items,
            linkTo(methodOn(OrderController.class).all()).withSelfRel()
        );
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable("id") long id) {
        return assembler.toModel(orders.findById(id));
    }

    @GetMapping("/search")
    CollectionModel<EntityModel<OrderView>> search(
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "0") int page) {
        List<EntityModel<OrderView>> items = orders.search(status, page).stream()
            .map(assembler::toModel)
            .toList();

        return CollectionModel.of(
            items,
            linkTo(methodOn(OrderController.class).search(status, page)).withSelfRel()
        );
    }

    @PostMapping("/{id}/cancellation")
    ResponseEntity<Void> cancel(@PathVariable("id") long id) {
        orders.cancel(id);
        return ResponseEntity.noContent().build();
    }
}
```

Các kiểu `Order`, `OrderView` và `OrderService` là domain model, DTO và service contract do ứng dụng cung cấp. Assembler chuyển một đơn hàng thành representation có các liên kết:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        EntityModel<OrderView> model = EntityModel.of(
            OrderView.from(order),
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel()
        );

        if (order.canCancel()) {
            model.add(linkTo(methodOn(OrderController.class).cancel(order.id()))
                .withRel("cancel"));
        }

        return model;
    }
}
```

Assembler tạo liên kết `self` tới phương thức `one(id)`. Nếu nghiệp vụ cho phép hủy, assembler thêm relation `cancel` tới phương thức `cancel(id)`. Khi mapping của endpoint thay đổi, builder lấy mapping mới và tạo URI phù hợp. Server vẫn phải kiểm tra lại trạng thái và quyền khi nhận request hủy.

## Path variable và query parameter

Khi phương thức controller có `@PathVariable`, Spring HATEOAS dùng tham số tương ứng để tạo path cụ thể:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@GetMapping("/{id}")
OrderView one(@PathVariable("id") long id) {
    return OrderView.from(orders.findById(id));
}

Link detail = linkTo(methodOn(OrderController.class).one(42L))
    .withSelfRel();
```

Với `@RequestParam`, builder có thể dùng lời gọi phương thức và giá trị tham số để tạo query string theo mapping:

```java
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/search")
List<OrderView> search(
        @RequestParam(required = false) String status,
        @RequestParam(defaultValue = "0") int page) {
    return orders.search(status, page).stream()
        .map(OrderView::from)
        .toList();
}

Link search = linkTo(methodOn(OrderController.class)
    .search("NEW", 0))
    .withRel("search");
```

Liên kết tìm kiếm được tạo theo mapping `/orders/search` cùng các query parameter đã truyền. Nếu tham số tùy chọn được để `null`, Spring HATEOAS có thể bỏ giá trị tương ứng khi xây URI; hãy xác nhận hành vi mong muốn bằng kiểm thử, nhất là khi endpoint có nhiều tham số tùy chọn hoặc giá trị mặc định.

Khi cần công bố một template cho client tự chọn giá trị query, có thể tạo link URI template riêng. `WebMvcLinkBuilder` thường phù hợp hơn để tạo URI cụ thể cho một lời gọi đã có tham số.

## Chuyển builder thành `Link` hoặc `URI`

Builder có thể hoàn tất thành `Link` bằng relation:

```java
Link self = linkTo(methodOn(OrderController.class).one(42L))
    .withSelfRel();

Link related = linkTo(methodOn(OrderController.class).all())
    .withRel("orders");
```

Nếu cần một `URI` cụ thể, có thể gọi `toUri()`:

```java
var uri = linkTo(methodOn(OrderController.class).one(42L)).toUri();
```

Trong API hypermedia, thường nên giữ kết quả dưới dạng `Link` để gắn relation và đưa vào `EntityModel`. Chỉ chuyển thành `URI` khi cần dùng địa chỉ trong một API khác hoặc trong logic nội bộ.

## URI tuyệt đối, context path và reverse proxy

`WebMvcLinkBuilder` xây URI dựa trên servlet request hiện tại và mapping của controller. Vì vậy, link có thể chứa scheme, host, port và context path của request đang xử lý. Trong môi trường triển khai có reverse proxy hoặc load balancer, ứng dụng cần được cấu hình để Spring nhận đúng forwarded headers nếu muốn link công bố host và scheme bên ngoài.

Ví dụ, client truy cập qua `https://api.example.test/app`, trong khi ứng dụng phía sau proxy chạy HTTP ở một cổng nội bộ. Nếu forwarded headers không được xử lý đúng, link tuyệt đối có thể phản ánh địa chỉ nội bộ thay vì địa chỉ mà client truy cập được. Hãy kiểm thử link trong môi trường có cùng proxy/context path với môi trường triển khai.

Không nên tạo link dựa trên request hiện tại trong tác vụ nền không có servlet request context. Với công việc chạy ngoài HTTP request, hãy dùng một base URI được cấu hình rõ ràng hoặc cơ chế tạo URI phù hợp với ngữ cảnh đó.

## Kiểm thử link được tạo

Có thể kiểm tra response bằng MockMvc để xác nhận relation và URI được tạo theo mapping:

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
@Import(OrderModelAssembler.class)
class OrderControllerLinkTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orders;

    @Test
    void publishesSelfLinkForOrder() throws Exception {
        given(orders.findById(42L))
            .willReturn(new Order(42L, "NEW"));

        mockMvc.perform(get("/orders/{id}", 42).accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").value("http://localhost/orders/42"));
    }
}
```

Ví dụ giả định `Order` có constructor `(long id, String status)` và `OrderService.findById` trả về đối tượng đó. URI tuyệt đối trong assertion phụ thuộc cấu hình MockMvc và servlet context của test; nếu test cấu hình context path hoặc host khác, hãy điều chỉnh assertion theo cấu hình. Khi có thể, kiểm tra cả relation và phần path cần thiết thay vì khóa cứng host/port của môi trường.

Nên bổ sung kiểm thử cho các trường hợp:

- `self` được tạo từ mapping của phương thức chi tiết.
- Relation `cancel` chỉ xuất hiện khi đơn hàng có thể hủy.
- Link danh sách dùng đúng mapping cấp controller.
- Path variable và query parameter được mở rộng đúng.
- Context path và forwarded headers tạo ra URL phù hợp môi trường.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Tự ghép chuỗi URI trong assembler | Mapping thay đổi làm link cũ sai | Dùng `linkTo` và `methodOn` |
| Dùng `linkTo(Controller.class)` cho endpoint con | Link chỉ phản ánh mapping cấp class | Dùng `methodOn(...).method(args)` hoặc bổ sung segment có chủ đích |
| Dùng `slash(...)` để tạo query string | Query bị nối như path segment | Dùng mapping có `@RequestParam` hoặc URI template |
| Nghĩ `methodOn(...)` gọi phương thức controller thật | Nhầm lẫn việc tạo URI với xử lý nghiệp vụ | `methodOn` tạo proxy để đọc mapping và tham số |
| Công bố link hành động không kiểm tra trạng thái | Client thấy hành động không hợp lệ | Kiểm tra business rule và quyền trước khi thêm link |
| Không xử lý forwarded headers phía sau proxy | Link tuyệt đối có thể chứa host hoặc scheme nội bộ | Cấu hình forwarded headers và kiểm thử ở môi trường tương ứng |
| Gọi builder ngoài request context | Không có thông tin servlet request để tạo URI tuyệt đối | Dùng base URI được cấu hình cho tác vụ nền |

## Ghi nhớ

`WebMvcLinkBuilder` tạo liên kết từ mapping của Spring MVC. `linkTo(Controller.class)` tham chiếu mapping cấp controller; `slash(...)` bổ sung path segment; `methodOn(Controller.class).method(args)` mô tả một handler cụ thể và cho phép Spring HATEOAS mở rộng path variable hoặc query parameter theo mapping. Kết quả có thể được hoàn tất thành `Link` với `withSelfRel()` hoặc `withRel(...)`, rồi gắn vào `EntityModel` hay `CollectionModel`. Dùng builder thay cho việc tự ghép URI giúp liên kết bám sát controller mapping và dễ tiến hóa khi API thay đổi.
