# LinkRelation là gì

`LinkRelation` trong Spring HATEOAS biểu diễn **ý nghĩa của mối quan hệ giữa tài nguyên hiện tại và tài nguyên được liên kết**. Một liên kết có URI đích (`href`) và relation (`rel`). URI cho biết client có thể đi tới đâu; relation cho biết liên kết đó có ý nghĩa gì trong ngữ cảnh representation.

Ví dụ, một đơn hàng có thể chứa liên kết `self` trỏ về chính đơn hàng, `collection` trỏ về tập hợp đơn hàng và `cancel` trỏ tới endpoint xử lý hủy đơn. Spring HATEOAS dùng kiểu `LinkRelation` để biểu diễn relation một cách rõ ràng trong code, đồng thời cung cấp các relation chuẩn qua `IanaLinkRelations` và cơ chế xác định tên relation cho tài nguyên qua `LinkRelationProvider`.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt `rel` và `href` trong một liên kết hypermedia.
- Sử dụng `LinkRelation` và `IanaLinkRelations` trong Spring HATEOAS.
- Chọn relation chuẩn hoặc định nghĩa relation mở rộng cho nghiệp vụ.
- Dùng `LinkRelationProvider` và `@Relation` để xác định relation cho item và collection.
- Gắn relation vào `Link`, `EntityModel` và representation HAL.
- Kiểm thử relation để giữ ổn định hợp đồng API.

## Relation mô tả điều gì?

Một liên kết hypermedia có thể được hiểu qua hai thành phần cốt lõi:

| Thành phần | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| `href` | Client đi tới URI nào? | `/orders/42` |
| `rel` | Liên kết này có quan hệ gì với tài nguyên hiện tại? | `self`, URI relation `orders`, URI relation `cancel` |

Ví dụ một representation HAL:

```json
{
  "id": 42,
  "status": "NEW",
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/42"
    },
    "https://api.example.test/rels/orders": {
      "href": "https://api.example.test/orders"
    },
    "https://api.example.test/rels/order/cancel": {
      "href": "https://api.example.test/orders/42/cancellation"
    }
  }
}
```

`self` và hai URI relation còn lại là các tên quan hệ. Giá trị trong `href` là địa chỉ đích. Khi server đổi mapping từ `/orders/42` sang `/sales/orders/42`, client vẫn có thể tìm relation `self` và theo `href` mới. Vì vậy, relation nên có ý nghĩa ổn định trong hợp đồng API.

Relation không phải HTTP method. `cancel` có thể trỏ tới endpoint nhận `POST`, nhưng bản thân relation không cho client biết method, schema request body hoặc các trường bắt buộc. Nếu cần mô tả chi tiết hành động, hãy dùng affordance và media type có hỗ trợ mô tả thao tác, chẳng hạn HAL-FORMS.

## `LinkRelation` trong Spring HATEOAS

`org.springframework.hateoas.LinkRelation` là kiểu giá trị dùng để biểu diễn relation của một `Link`. Có thể tạo relation bằng `LinkRelation.of(...)`:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

LinkRelation selfRel = LinkRelation.of("self");
LinkRelation ordersRel = LinkRelation.of("https://api.example.test/rels/orders");

Link self = Link.of("https://api.example.test/orders/42", selfRel.value());
Link orders = Link.of("https://api.example.test/orders", ordersRel.value());
```

`LinkRelation` giúp tách giá trị relation khỏi chuỗi được dùng khi tạo liên kết. Điều này hữu ích khi relation được chia sẻ giữa assembler, controller và các thành phần kiểm thử. Khi cần lấy giá trị dạng chuỗi, dùng `value()`.

Spring HATEOAS cũng cho phép đặt relation trực tiếp trên link builder:

```java
Link self = linkTo(methodOn(OrderController.class).one(42L))
    .withSelfRel();

Link collection = linkTo(methodOn(OrderController.class).all())
    .withRel("https://api.example.test/rels/orders");
```

`withSelfRel()` tạo relation chuẩn `self`. `withRel(...)` đặt relation tùy chỉnh. Nếu relation đã được biểu diễn dưới dạng `LinkRelation`, có thể truyền giá trị của nó bằng `.withRel(relation.value())`.

## Relation chuẩn và `IanaLinkRelations`

IANA duy trì danh mục các link relation chuẩn dùng chung trên Web. Spring HATEOAS cung cấp lớp `IanaLinkRelations` với các hằng số tương ứng để tránh gõ lại tên relation và giảm lỗi chính tả.

Một số relation thường gặp:

| Hằng số Spring | Giá trị relation | Ý nghĩa thường dùng |
|---|---|---|
| `IanaLinkRelations.SELF` | `self` | Tài nguyên hiện tại |
| `IanaLinkRelations.NEXT` | `next` | Trang hoặc mục kế tiếp |
| `IanaLinkRelations.PREV` | `prev` | Trang hoặc mục trước |
| `IanaLinkRelations.FIRST` | `first` | Trang đầu tiên của tập hợp phân trang |
| `IanaLinkRelations.LAST` | `last` | Trang cuối cùng của tập hợp phân trang |
| `IanaLinkRelations.ALTERNATE` | `alternate` | Biểu diễn hoặc tài nguyên thay thế |
| `IanaLinkRelations.RELATED` | `related` | Tài nguyên có liên quan |

Ví dụ sử dụng relation chuẩn:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of("/orders/42", IanaLinkRelations.SELF.value());
Link next = Link.of("/orders?page=1", IanaLinkRelations.NEXT.value());
Link previous = Link.of("/orders?page=0", IanaLinkRelations.PREV.value());
```

Trong code tạo link từ controller, có thể dùng trực tiếp builder tương ứng như `withSelfRel()` hoặc dùng `withRel(IanaLinkRelations.NEXT.value())` khi relation được chọn động.

Nên ưu tiên relation chuẩn khi ý nghĩa liên kết đã được IANA định nghĩa. Client có thể hiểu `self`, `next` hoặc `related` theo ngữ nghĩa phổ biến mà không cần một định nghĩa riêng của từng API.

## Relation mở rộng cho nghiệp vụ

API thường có các quan hệ riêng của miền nghiệp vụ như `approve`, `cancel`, `submit`, `shipment` hoặc `invoice`. Nếu relation không thuộc danh mục chuẩn, nên định danh relation mở rộng bằng một URI tuyệt đối do tổ chức API kiểm soát.

Ví dụ:

```java
import org.springframework.hateoas.LinkRelation;

final class OrderRelations {

    static final LinkRelation CANCEL = LinkRelation.of(
        "https://api.example.test/rels/order/cancel"
    );

    static final LinkRelation APPROVE = LinkRelation.of(
        "https://api.example.test/rels/order/approve"
    );

    private OrderRelations() {
    }
}
```

Assembler sử dụng relation đã đặt tên:

```java
record Order(long id, String status) {
    boolean canCancel() {
        return status.equals("NEW");
    }

    boolean canApprove() {
        return status.equals("SUBMITTED");
    }
}

record OrderView(long id, String status) {
    static OrderView from(Order order) {
        return new OrderView(order.id(), order.status());
    }
}

interface OrderService {
    Order findById(long id);
    void cancel(long id);
    void approve(long id);
}
```

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler {

    EntityModel<OrderView> toModel(Order order) {
        EntityModel<OrderView> model = EntityModel.of(
            OrderView.from(order),
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel()
        );

        if (order.canCancel()) {
            model.add(linkTo(methodOn(OrderController.class).cancel(order.id()))
                .withRel(OrderRelations.CANCEL.value()));
        }

        if (order.canApprove()) {
            model.add(linkTo(methodOn(OrderController.class).approve(order.id()))
                .withRel(OrderRelations.APPROVE.value()));
        }

        return model;
    }
}
```

Controller khai báo các phương thức được assembler tham chiếu để Spring HATEOAS có thể lấy mapping và sinh URI:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orders;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orders, OrderModelAssembler assembler) {
        this.orders = orders;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable long id) {
        return assembler.toModel(orders.findById(id));
    }

    @PostMapping("/{id}/cancellation")
    void cancel(@PathVariable long id) {
        orders.cancel(id);
    }

    @PostMapping("/{id}/approval")
    void approve(@PathVariable long id) {
        orders.approve(id);
    }

    @GetMapping
    String all() {
        return "orders";
    }
}
```

Các phương thức `canCancel()` và `canApprove()` đại diện cho quy tắc nghiệp vụ của ví dụ. Trong ứng dụng thực tế, điều kiện công bố liên kết còn có thể phụ thuộc quyền của principal hiện tại. Service vẫn phải xác thực lại trạng thái và quyền khi client gọi endpoint.

Không nên dùng tên relation ngắn tùy ý như `cancel` làm hợp đồng công khai nếu không có quy ước namespace rõ ràng. Hai API độc lập có thể vô tình gán ý nghĩa khác nhau cho cùng tên. URI relation giúp tránh xung đột namespace và có thể trỏ tới tài liệu mô tả quan hệ.

## `LinkRelationProvider` và quan hệ item/collection

Spring HATEOAS cung cấp `LinkRelationProvider` để xác định relation dùng cho một tài nguyên đơn lẻ và một tập hợp tài nguyên. Điều này đặc biệt hữu ích khi tạo `CollectionModel`, nơi HAL cần một relation cho từng phần tử trong `_embedded`.

Interface `LinkRelationProvider` cung cấp các phương thức chính:

- `getItemResourceRelFor(Class<?>)`: lấy relation cho một phần tử.
- `getCollectionResourceRelFor(Class<?>)`: lấy relation cho tập hợp phần tử.
- `supports(Class<?>)`: kiểm tra provider có hỗ trợ kiểu được hỏi hay không.

Ví dụ, một assembler có thể nhận provider qua dependency injection:

```java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.LinkRelationProvider;
import org.springframework.stereotype.Component;

@Component
class OrderRelationNames {

    private final LinkRelationProvider relations;

    OrderRelationNames(LinkRelationProvider relations) {
        this.relations = relations;
    }

    LinkRelation itemRelation() {
        return relations.getItemResourceRelFor(OrderModel.class);
    }

    LinkRelation collectionRelation() {
        return relations.getCollectionResourceRelFor(OrderModel.class);
    }
}
```

Spring HATEOAS có provider mặc định dùng quy tắc số ít/số nhiều để suy ra tên relation. Tuy nhiên, suy luận tự động không phải lúc nào cũng đúng với từ bất quy tắc hoặc thuật ngữ nghiệp vụ. Có thể khai báo tường minh bằng annotation `@Relation`.

```java
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(
    itemRelation = "https://api.example.test/rels/order",
    collectionRelation = "https://api.example.test/rels/orders"
)
public class OrderModel extends RepresentationModel<OrderModel> {

    private final long id;
    private final String status;

    public OrderModel(long id, String status) {
        this.id = id;
        this.status = status;
    }

    public long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }
}
```

Với annotation trên, relation của một phần tử và relation collection đều được định danh bằng URI. `LinkRelationProvider` đọc metadata này để trả relation phù hợp. Nếu representation có tên nghiệp vụ không tuân theo quy tắc số nhiều thông thường, khai báo rõ ràng giúp tránh phụ thuộc vào cách suy luận.

## Dùng relation khi tạo collection model

Khi trả tập hợp, relation collection xác định tên thuộc tính trong `_embedded`. Có thể tạo `CollectionModel` cùng liên kết tới endpoint collection:

```java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.LinkRelationProvider;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

class OrderCollectionAssembler {

    private final LinkRelationProvider relations;

    OrderCollectionAssembler(LinkRelationProvider relations) {
        this.relations = relations;
    }

    CollectionModel<OrderModel> toCollectionModel(List<OrderModel> orders) {

        LinkRelation collectionRel = relations
            .getCollectionResourceRelFor(OrderModel.class);

        Link self = linkTo(methodOn(OrderController.class).all())
            .withRel(collectionRel.value());

        return CollectionModel.of(orders, self);
    }
}
```

Trong một API thực tế, `RepresentationModelAssembler` có thể chuyển từng domain object thành `EntityModel`, sau đó `CollectionModel` bọc các phần tử và thêm liên kết cấp collection. Với phân trang, `PagedResourcesAssembler` tạo `PagedModel` cùng metadata và các relation điều hướng trang như `first`, `prev`, `next`, `last`.

## Relation trong HAL

HAL biểu diễn các liên kết trong thuộc tính `_links`. Tên key bên trong `_links` chính là relation; mỗi relation có một hoặc nhiều link object tùy cấu trúc response.

Ví dụ:

```json
{
  "id": 42,
  "status": "NEW",
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/42"
    },
    "https://api.example.test/rels/order/cancel": {
      "href": "https://api.example.test/orders/42/cancellation"
    }
  }
}
```

Relation mở rộng dạng URI có thể dài. HAL hỗ trợ CURIE (Compact URI) để biểu diễn URI relation bằng tên rút gọn, nếu API khai báo CURIE tương ứng trong liên kết `curies`. Khi dùng CURIE, client cần hiểu cách mở rộng tên rút gọn thành URI relation gốc. Không được thay đổi ý nghĩa của CURIE prefix hoặc relation đã công bố mà không quản lý tương thích hợp đồng.

## Kiểm thử relation

Kiểm thử nên xác nhận relation cần thiết có mặt và relation không khả dụng không xuất hiện. Ví dụ với MockMvc:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.mockito.BDDMockito.given;
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
class OrderRelationControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orders;

    @Test
    void publishesSelfAndCancelRelationsForCancellableOrder() throws Exception {
        given(orders.findById(42L)).willReturn(new Order(42L, "NEW"));

        mockMvc.perform(get("/orders/{id}", 42).accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links['https://api.example.test/rels/order/cancel'].href")
                .exists());
    }
}
```

Trong ví dụ, `@Import` đăng ký assembler trong test slice và mock `OrderService` trả về đơn hàng `NEW`, vì vậy assembler công bố relation `cancel`. Nếu API dùng CURIE, kiểm thử cả `curies` và tên relation rút gọn mà client nhận được.

Nên có các kiểm thử bổ sung:

- Relation chuẩn `self` luôn trỏ tới URI tài nguyên hiện tại.
- Collection relation dùng đúng tên đã khai báo trong `@Relation`.
- Relation hành động chỉ xuất hiện khi trạng thái và quyền cho phép.
- Relation tùy chỉnh giữ nguyên URI hoặc CURIE đã công bố.
- Client có thể tìm relation theo ngữ nghĩa và đi theo `href` mà không ghép URI.

## Tiến hóa hợp đồng và các lỗi thường gặp

Relation là một phần của hợp đồng hypermedia. Đổi `rel` có thể làm client cũ không còn tìm thấy liên kết, ngay cả khi `href` vẫn hoạt động. Ngược lại, đổi `href` nhưng giữ nguyên relation có thể tương thích với client biết khám phá liên kết.

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm `rel` với `href` | Client coi tên quan hệ như địa chỉ truy cập | Dùng `rel` để hiểu ý nghĩa và `href` để điều hướng |
| Dùng relation chuẩn sai ngữ nghĩa | Client diễn giải sai liên kết | Chọn relation IANA đúng nghĩa hoặc định nghĩa relation mở rộng |
| Dùng tên tùy chỉnh ngắn không có namespace | Dễ xung đột giữa các API | Dùng URI relation tuyệt đối hoặc CURIE có quy ước |
| Đổi tên relation mà không quản lý phiên bản | Client cũ không tìm được hành động | Giữ relation ổn định hoặc công bố chuyển tiếp tương thích |
| Cho rằng relation mô tả HTTP method | Client không biết cách gửi request | Dùng affordance/media type phù hợp khi cần mô tả thao tác |
| Để provider tự suy luận tên không phù hợp | Relation item/collection sai ngữ nghĩa | Khai báo `@Relation` rõ ràng |

## Ghi nhớ

`LinkRelation` biểu diễn ý nghĩa của liên kết; `href` mới là URI đích. Dùng `IanaLinkRelations` cho các relation chuẩn như `self`, `next`, `prev`, `first` và `last`. Với quan hệ nghiệp vụ riêng, nên dùng URI relation ổn định và quản lý namespace. `LinkRelationProvider` xác định relation cho item và collection; `@Relation` giúp khai báo rõ tên số ít và số nhiều. Khi serialize HAL, relation trở thành key trong `_links` hoặc tên collection trong `_embedded`, vì vậy cần kiểm thử và giữ ổn định ngữ nghĩa để client có thể tiến hóa cùng API.
