# Bọc một tài nguyên

`EntityModel<T>` trong Spring HATEOAS dùng để bọc một đối tượng biểu diễn tài nguyên cùng các liên kết hypermedia của tài nguyên đó. Thay vì trả một DTO đơn lẻ, controller có thể trả `EntityModel<OrderView>` với liên kết `self`, liên kết quay lại tập hợp và các liên kết hành động đang khả dụng.

`EntityModel` phù hợp khi response đại diện cho một tài nguyên cụ thể. Nó giúp tách dữ liệu mà client đọc khỏi cách client điều hướng tới tài nguyên hoặc hành động tiếp theo. Đây là một thành phần cốt lõi khi xây dựng REST API có hypermedia bằng Spring HATEOAS.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vai trò của `EntityModel<T>` trong một representation hypermedia.
- Tạo `EntityModel` từ DTO và gắn một hoặc nhiều liên kết.
- Sinh URI từ mapping của controller bằng `linkTo` và `methodOn`.
- Trả `EntityModel` từ controller và xuất representation HAL.
- Dùng assembler để tách logic chuyển đổi tài nguyên khỏi controller.
- Kiểm thử nội dung và liên kết của một tài nguyên đơn lẻ.

## Vì sao cần bọc tài nguyên?

Giả sử API trả về thông tin đơn hàng theo cách thông thường:

```java
public record OrderView(long id, String status, long total) {
}

@GetMapping("/orders/{id}")
OrderView one(@PathVariable long id) {
    return orders.findById(id);
}
```

Client nhận được dữ liệu đơn hàng, nhưng response chưa cung cấp URI để lấy chính tài nguyên, quay lại danh sách hoặc thực hiện hành động tiếp theo. Client có thể phải tự biết rằng đường dẫn chi tiết là `/orders/{id}` và đường dẫn hủy là `/orders/{id}/cancellation`.

Với hypermedia, server có thể trả dữ liệu cùng các liên kết:

```json
{
  "id": 42,
  "status": "NEW",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/42"
    },
    "orders": {
      "href": "https://api.example.test/orders"
    },
    "cancel": {
      "href": "https://api.example.test/orders/42/cancellation"
    }
  }
}
```

Đây là representation theo HAL. Các trường mô tả đơn hàng nằm ở phần nội dung, còn `_links` chứa những quan hệ điều hướng. Client đọc URI trong `href` của relation cần dùng thay vì tự tạo URI từ ID và quy ước đường dẫn.

## `EntityModel<T>` là gì?

`EntityModel<T>` là một kiểu model của Spring HATEOAS kế thừa `RepresentationModel` và giữ một đối tượng nội dung kiểu `T`. Tham số `T` ở đây là kiểu content. Với `RepresentationModel<T>`, tham số generic là kiểu self của model để hỗ trợ API liên kết có kiểu trả về phù hợp; nó không phải kiểu content được bọc. Có thể hiểu `EntityModel` gồm hai phần:

- **Content:** dữ liệu của tài nguyên, thường là DTO hoặc projection dành cho API.
- **Links:** tập hợp liên kết mô tả tài nguyên và các hướng điều hướng liên quan.

Ví dụ tối giản:

```java
import org.springframework.hateoas.EntityModel;

OrderView order = new OrderView(42L, "NEW", 1_250_000L);

EntityModel<OrderView> model = EntityModel.of(order);
```

`EntityModel.of(content)` tạo model với nội dung đã cho. Có thể truyền liên kết ngay khi tạo model:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

EntityModel<OrderView> model = EntityModel.of(
    order,
    Link.of("https://api.example.test/orders/42", "self")
);
```

Trong ứng dụng Spring MVC, nên tạo liên kết từ mapping của controller để tránh lặp URI dưới dạng chuỗi. Các builder `linkTo` và `methodOn` đảm nhiệm việc đó.

## Tạo liên kết cho `EntityModel`

Giả sử có controller quản lý đơn hàng:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
class OrderLinkController {

    private final OrderService orders;

    OrderLinkController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable long id) {
        OrderView order = orders.findById(id);

        Link self = linkTo(methodOn(OrderLinkController.class).one(id))
            .withSelfRel();

        Link collection = linkTo(methodOn(OrderLinkController.class).all())
            .withRel("orders");

        return EntityModel.of(order, self, collection);
    }

    @GetMapping
    String all() {
        return "Danh sách đơn hàng";
    }
}
```

Trong ví dụ, `methodOn(OrderLinkController.class).one(id)` mô tả phương thức controller cần tham chiếu. `linkTo(...)` lấy thông tin mapping tương ứng và tạo URI. `withSelfRel()` đặt relation chuẩn `self`; `withRel("orders")` tạo relation tùy chỉnh `orders`.

`EntityModel.of(order, self, collection)` bọc DTO cùng hai liên kết. Nếu mapping thay đổi từ `/orders/{id}` sang một đường dẫn khác, URI được sinh từ mapping mới khi ứng dụng chạy. Client vẫn có thể đi theo `self` và `orders` miễn là ngữ nghĩa relation được giữ ổn định.

### Một số cách tạo và thêm liên kết

| API | Mục đích |
|---|---|
| `EntityModel.of(content)` | Tạo model chỉ có nội dung |
| `EntityModel.of(content, links...)` | Tạo model với nội dung và các liên kết ban đầu |
| `model.add(link)` | Thêm một liên kết sau khi tạo model |
| `linkTo(methodOn(...))` | Tạo builder từ mapping của phương thức controller |
| `withSelfRel()` | Gắn relation chuẩn `self` |
| `withRel("name")` | Gắn relation có tên được chỉ định |

Ví dụ thêm liên kết theo điều kiện nghiệp vụ:

```java
EntityModel<OrderView> model = EntityModel.of(order,
    linkTo(methodOn(OrderEntityController.class).one(order.id())).withSelfRel());

if (order.status().equals("NEW")) {
    model.add(linkTo(methodOn(OrderEntityController.class)
        .cancel(order.id())).withRel("cancel"));
}
```

Liên kết `cancel` chỉ được công bố khi đơn hàng đang ở trạng thái cho phép hủy. Điều kiện phải phản ánh quy tắc nghiệp vụ và quyền truy cập. Việc client nhận được liên kết không thay thế kiểm tra trạng thái và quyền ở server khi request thực tế được gửi.

## Trả `EntityModel` từ controller

Một ví dụ hoàn chỉnh hơn dùng DTO và service riêng:

```java
interface OrderService {
    OrderView findById(long id);
    void cancel(long id);
    boolean canCancel(long id);
}
```

Controller trả model cho một đơn hàng và công bố liên kết hủy nếu thao tác còn khả dụng:

```java
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
class OrderEntityController {

    private final OrderService orders;

    OrderEntityController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable long id) {
        OrderView order = orders.findById(id);

        EntityModel<OrderView> model = EntityModel.of(
            order,
            linkTo(methodOn(OrderEntityController.class).one(id)).withSelfRel()
        );

        if (orders.canCancel(id)) {
            model.add(linkTo(methodOn(OrderEntityController.class).cancel(id))
                .withRel("cancel"));
        }

        return model;
    }

    @PostMapping("/{id}/cancellation")
    void cancel(@PathVariable long id) {
        orders.cancel(id);
    }
}
```

Service chịu trách nhiệm quyết định đơn hàng có thể hủy hay không và xác thực lại điều kiện khi xử lý `cancel`. Trong ứng dụng có phân quyền, điều kiện công bố liên kết còn phải xét người dùng hiện tại. Có thể trả response chứa representation mới sau thao tác thay vì `void`, tùy hợp đồng API.

### Mô tả thêm thao tác bằng affordance

Một `Link` thông thường cung cấp URI và relation. Khi client cần biết thêm HTTP method hoặc dữ liệu đầu vào của hành động, có thể gắn affordance vào liên kết. Ví dụ, liên kết `self` có thể công bố affordance cho thao tác hủy:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;

Link self = linkTo(methodOn(OrderEntityController.class).one(id))
    .withSelfRel()
    .andAffordance(afford(methodOn(OrderEntityController.class).cancel(id)));

return EntityModel.of(order, self);
```

Affordance được suy ra từ mapping controller. Để client nhận mô tả hành động chi tiết, ứng dụng cần serialize bằng media type hỗ trợ affordance, chẳng hạn HAL-FORMS. HAL JSON thông thường chỉ có `_links` và `href`; sự hiện diện của liên kết đơn thuần không mô tả đầy đủ schema của request body.

## Tách logic tạo model bằng assembler

Khi controller có nhiều endpoint trả cùng một loại tài nguyên, việc tạo DTO và liên kết lặp lại sẽ khiến code khó bảo trì. Spring HATEOAS cung cấp `RepresentationModelAssembler` để đóng gói logic chuyển đổi domain object thành model.

```java
import java.util.List;

record OrderAggregate(long id, String status, long total) {
    boolean canCancel() {
        return status.equals("NEW") || status.equals("PROCESSING");
    }
}

record OrderRepresentation(long id, String status, long total) {
    static OrderRepresentation from(OrderAggregate order) {
        return new OrderRepresentation(order.id(), order.status(), order.total());
    }
}

interface OrderQueryService {
    OrderAggregate getOrder(long id);
    List<OrderAggregate> findAll();
    OrderAggregate cancel(long id);
}
```

Biến thể assembler dưới đây dùng `OrderAggregate` và `OrderRepresentation` để thể hiện rõ domain object và DTO của riêng ví dụ này.

```java
import java.util.List;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<OrderAggregate, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(OrderAggregate order) {
        EntityModel<OrderRepresentation> model = EntityModel.of(
            OrderRepresentation.from(order),
            linkTo(methodOn(AssembledOrderController.class).one(order.id())).withSelfRel()
        );

        model.add(linkTo(methodOn(AssembledOrderController.class).all())
            .withRel("orders"));

        if (order.canCancel()) {
            model.add(linkTo(methodOn(AssembledOrderController.class).cancel(order.id()))
                .withRel("cancel"));
        }

        return model;
    }
}
```

Trong ví dụ này, `OrderAggregate` là kiểu domain object và `OrderRepresentation` là DTO được công bố. Phương thức `OrderRepresentation.from(order)` chuyển đổi domain object sang DTO. Assembler chịu trách nhiệm thêm `self`, `orders` và `cancel` theo trạng thái tài nguyên.

Controller có thể dùng assembler như sau:

```java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class AssembledOrderController {

    private final OrderQueryService orders;
    private final OrderModelAssembler assembler;

    AssembledOrderController(OrderQueryService orders, OrderModelAssembler assembler) {
        this.orders = orders;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<OrderRepresentation> one(@PathVariable long id) {
        return assembler.toModel(orders.getOrder(id));
    }

    @GetMapping
    CollectionModel<EntityModel<OrderRepresentation>> all() {
        return assembler.toCollectionModel(orders.findAll());
    }

    @PostMapping("/{id}/cancellation")
    EntityModel<OrderRepresentation> cancel(@PathVariable long id) {
        return assembler.toModel(orders.cancel(id));
    }
}
```

Đây là đoạn minh họa cách sử dụng assembler; `OrderQueryService` cung cấp `getOrder`, `findAll` và `cancel`. `toCollectionModel` là phương thức tiện ích được cung cấp bởi `RepresentationModelAssembler` để chuyển tập hợp domain object thành collection model.

## `EntityModel` và các kiểu model khác

Spring HATEOAS có nhiều kiểu model vì response có thể đại diện cho một tài nguyên, một tập hợp hoặc một representation tùy biến.

| Kiểu model | Khi sử dụng | Ví dụ |
|---|---|---|
| `EntityModel<T>` | Một tài nguyên cùng các liên kết | Chi tiết đơn hàng 42 |
| `CollectionModel<T>` | Tập hợp các model hoặc tài nguyên | Danh sách đơn hàng |
| `RepresentationModel<T>` | Lớp cơ sở để tự định nghĩa representation có liên kết; `T` là kiểu self | Một view tổng hợp nhiều phần dữ liệu |
| `PagedModel<T>` | Tập hợp có thông tin phân trang | Trang 2 của danh sách đơn hàng |

Không nên bọc một danh sách vào `EntityModel` chỉ vì muốn thêm liên kết. Với tập hợp, dùng `CollectionModel` hoặc kiểu phân trang tương ứng để cấu trúc response thể hiện đúng ý nghĩa. Nếu cần các trường tổng hợp riêng ngoài một content object đơn lẻ, có thể tạo class kế thừa `RepresentationModel`.

## HAL representation

Khi ứng dụng dùng Spring Boot và `spring-boot-starter-hateoas`, Spring HATEOAS tích hợp với message converter để tuần tự hóa các model theo media type hypermedia. Client có thể yêu cầu HAL bằng header:

```http
GET /orders/42 HTTP/1.1
Host: api.example.test
Accept: application/hal+json
```

Response minh họa:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
```

```json
{
  "id": 42,
  "status": "NEW",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/42"
    },
    "orders": {
      "href": "https://api.example.test/orders"
    },
    "cancel": {
      "href": "https://api.example.test/orders/42/cancellation"
    }
  }
}
```

Các liên kết được serialize vào `_links`. `self` định danh representation hiện tại, `orders` điều hướng về tập hợp, còn `cancel` mô tả hành động có thể thực hiện. Quan hệ tùy chỉnh như `orders` và `cancel` cần được tài liệu hóa hoặc định danh theo URI relation để client hiểu ý nghĩa ổn định.

`EntityModel` chỉ cung cấp cấu trúc bọc content và links. Nó không tự quyết định quy tắc nghiệp vụ, không tự cấp quyền và không tự bảo đảm mọi liên kết đều hợp lệ. Controller hoặc assembler cần thêm đúng các liên kết dựa trên dữ liệu và policy của ứng dụng.

## Kiểm thử `EntityModel` bằng MockMvc

Kiểm thử endpoint nên xác nhận media type, content và các relation quan trọng:

```java
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderEntityController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orders;

    @Test
    void returnsOrderAsHalEntityModel() throws Exception {
        given(orders.findById(42L))
            .willReturn(new OrderView(42L, "NEW", 1_250_000L));
        given(orders.canCancel(42L)).willReturn(true);

        mockMvc.perform(get("/orders/{id}", 42).accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.status").value("NEW"))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.orders.href").exists())
            .andExpect(jsonPath("$._links.cancel.href").exists());
    }
}
```

Ví dụ kiểm thử dùng phiên bản controller trực tiếp tạo `EntityModel` và service có các phương thức `findById`, `canCancel`. Nếu controller dùng assembler, test slice cần import assembler và mock các dependency mà assembler sử dụng. Có thể bổ sung test cho trường hợp không thể hủy để xác nhận `_links.cancel` không xuất hiện.

Một kiểm thử client tích hợp nên đọc `href` từ `_links.self` hoặc `_links.cancel` trong response rồi gọi URI đó. Kiểm thử như vậy xác nhận client có thể điều hướng theo hợp đồng hypermedia, thay vì chỉ xác nhận một đường dẫn viết cứng.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Trả DTO thuần khi client cần điều hướng | Client phải tự biết các URI tiếp theo | Trả `EntityModel<T>` với các relation phù hợp |
| Đưa toàn bộ entity persistence vào content | Dễ lộ trường nội bộ và phụ thuộc cấu trúc lưu trữ | Chuyển đổi sang DTO hoặc projection |
| Tự nối chuỗi URI | Mapping thay đổi có thể làm sai liên kết | Dùng `linkTo` và `methodOn` |
| Bọc danh sách trong `EntityModel` | Kiểu response không thể hiện đúng ý nghĩa tập hợp | Dùng `CollectionModel` hoặc `PagedModel` |
| Công bố liên kết hành động không điều kiện | Client thấy thao tác không phù hợp trạng thái hoặc quyền | Kiểm tra business rule và policy trước khi thêm link |
| Nghĩ rằng có link đồng nghĩa request chắc chắn thành công | Trạng thái hoặc quyền có thể đổi trước lúc request đến | Server kiểm tra lại ở tầng nghiệp vụ |
| Đổi tên relation tùy tiện | Client không tìm thấy quan hệ đã sử dụng | Giữ relation ổn định và quản lý thay đổi hợp đồng |

## Ghi nhớ

`EntityModel<T>` bọc một đối tượng content cùng các liên kết hypermedia để biểu diễn một tài nguyên đơn lẻ. Dùng `EntityModel.of(...)` để tạo model, `add(...)` để thêm liên kết và `linkTo(methodOn(...))` để sinh URI từ mapping của controller. Trong ứng dụng có nhiều endpoint, `RepresentationModelAssembler` giúp tập trung logic chuyển đổi domain object thành representation. Khi được serialize thành HAL, content nằm trong JSON và các relation được đưa vào `_links`, cho phép client khám phá tài nguyên và hành động tiếp theo theo hợp đồng API.
