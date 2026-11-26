# To-many association

**To-many association** là quan hệ trong đó một tài nguyên liên kết với không hoặc nhiều tài nguyên khác. Ví dụ, một đơn hàng có nhiều dòng hàng, một khách hàng có nhiều địa chỉ giao hàng, hoặc một bài viết có nhiều bình luận. Trong REST API dùng Spring HATEOAS, quan hệ này có thể được công bố bằng một link đến collection resource; client theo link để khám phá các phần tử liên quan.

Một response đơn hàng có thể cung cấp self link đến chính đơn hàng và relation `items` đến collection dòng hàng. Endpoint collection trả về `CollectionModel`, trong đó từng dòng hàng có thể có self link riêng. Nếu tập hợp lớn, API có thể trả `PagedModel` để bổ sung metadata và link phân trang.

To-many association mô tả quan hệ ở cấp tài nguyên và hợp đồng HTTP. Nó không đồng nghĩa với việc phải serialize trực tiếp một collection JPA hoặc nhúng mọi phần tử vào response cha. API cần quyết định quan hệ nào được công bố, tài nguyên con có định danh riêng hay không, cách phân trang, và thao tác thêm hoặc gỡ quan hệ.

Sau bài học, bạn có thể:

- Giải thích quan hệ to-many và cách biểu diễn nó trong REST API.
- Thiết kế collection endpoint cho các tài nguyên liên quan.
- Công bố association bằng link relation trong Spring HATEOAS.
- Dùng `CollectionModel`, `EntityModel` và `PagedModel` cho collection và item.
- Phân biệt tài nguyên con với tài nguyên liên kết có thuộc tính riêng.
- Chọn giữa embedded data và link đến collection.
- Thiết kế thao tác thêm, xóa và kiểm tra quyền trên association.
- Kiểm thử relation, URI, collection rỗng, phân trang và quy tắc nghiệp vụ.

## Quan hệ to-many là gì?

Trong mô hình miền, quan hệ to-many cho biết một đối tượng có thể liên kết với nhiều đối tượng khác. Một đơn hàng có thể có nhiều dòng hàng:

~~~text
Order 42
  |
  +-- OrderItem 101
  +-- OrderItem 102
  +-- OrderItem 103
~~~

Quan hệ này có thể có số phần tử bằng 0, 1 hoặc nhiều hơn. Ví dụ đơn hàng mới tạo có thể chưa có dòng hàng nào; đơn hàng đã xác nhận có thể có nhiều dòng.

Một số ví dụ khác:

| Tài nguyên cha | Quan hệ to-many | Ví dụ collection |
| --- | --- | --- |
| Customer | Addresses | /customers/7/addresses |
| Order | Order items | /orders/42/items |
| Blog post | Comments | /posts/18/comments |
| Project | Members | /projects/5/members |
| Product | Reviews | /products/900/reviews |

### To-many trong domain không quyết định cấu trúc JSON

Một quan hệ `@OneToMany` trong JPA có thể được biểu diễn bằng nhiều cách trong API:

- Một link đến collection resource.
- Một collection response riêng với embedded items.
- Một danh sách tóm tắt được nhúng trong representation cha.
- Một association resource độc lập nếu quan hệ có dữ liệu hoặc vòng đời riêng.

Không nên để cấu trúc persistence tự quyết định hợp đồng REST. API nên phản ánh ngữ nghĩa nghiệp vụ, nhu cầu của client và cách tài nguyên được quản lý.

### Quan hệ tài nguyên khác quan hệ bảng

REST/HATEOAS mô tả quan hệ giữa các tài nguyên có thể khám phá qua URI và relation. JPA mô tả quan hệ lưu trữ và cách ORM tải dữ liệu. Hai mô hình có thể tương ứng nhưng không bắt buộc giống nhau.

Ví dụ, `Order` có thể lưu `OrderItem` trong cùng aggregate của domain, nhưng API vẫn công bố collection `/orders/{id}/items`. Ngược lại, API có thể tổng hợp nhiều bảng thành một collection resource mà không có một collection JPA tương ứng.

## Biểu diễn to-many bằng collection resource

Một cách phổ biến là cung cấp endpoint cho collection thuộc tài nguyên cha:

~~~text
GET /orders/42
GET /orders/42/items
GET /orders/42/items/101
~~~

Ý nghĩa:

- `/orders/42` biểu diễn đơn hàng.
- `/orders/42/items` biểu diễn tập hợp dòng hàng thuộc đơn hàng 42.
- `/orders/42/items/101` biểu diễn một dòng hàng trong ngữ cảnh đơn hàng 42.

Response của đơn hàng công bố relation `items`:

~~~json
{
  "id": 42,
  "orderNumber": "ORD-0042",
  "status": "DRAFT",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "items": {
      "href": "/orders/42/items"
    }
  }
}
~~~

Client không cần tự ghép `/orders/{id}/items`. Nó tìm relation `items` trong `_links` rồi theo `href`.

Response collection có thể chứa các item dưới `_embedded`:

~~~json
{
  "_embedded": {
    "items": [
      {
        "id": 101,
        "sku": "KB-001",
        "quantity": 1,
        "_links": {
          "self": {
            "href": "/orders/42/items/101"
          }
        }
      },
      {
        "id": 102,
        "sku": "MS-008",
        "quantity": 2,
        "_links": {
          "self": {
            "href": "/orders/42/items/102"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/orders/42/items"
    },
    "order": {
      "href": "/orders/42"
    }
  }
}
~~~

Collection resource có self link riêng; mỗi item có self link riêng; link `order` giúp client quay lại tài nguyên cha. Relation `items` là quan hệ từ đơn hàng đến collection, còn relation `order` là quan hệ từ collection về đơn hàng.

## Chọn URI cho item trong association

Có hai cách phổ biến để đặt URI cho tài nguyên con:

| Kiểu URI | Ví dụ | Phù hợp khi |
| --- | --- | --- |
| URI lồng theo cha | /orders/42/items/101 | Item được quản lý trong ngữ cảnh một đơn hàng |
| URI độc lập | /order-items/101 | Item có định danh và vòng đời độc lập |

URI lồng giúp thể hiện ngữ cảnh và ranh giới sở hữu. URI độc lập hữu ích khi client cần tham chiếu item từ nhiều nơi hoặc item có thể tồn tại độc lập với collection cha.

Nếu dùng cả hai URI cho cùng một item, hãy xác định URI nào là self/canonical theo hợp đồng. Tránh để client phải đoán hai URI có cùng ý nghĩa hay không.

### Khi association có thuộc tính riêng

Một quan hệ có thể mang dữ liệu nghiệp vụ. Ví dụ dòng hàng trong đơn không chỉ là link đến sản phẩm mà còn có `quantity`, `unitPrice`, `discount` và `position`.

~~~text
Order 42
  |
  +-- OrderItem 101
        +-- product -> Product 900
        +-- quantity = 2
        +-- unitPrice = 125000
~~~

Trong trường hợp này, `OrderItem` là association resource có ý nghĩa riêng. Nó có thể có self link, các thuộc tính nghiệp vụ và link đến sản phẩm. Không nên chỉ biểu diễn quan hệ bằng một danh sách product ID vì như vậy sẽ làm mất dữ liệu của chính association.

Nếu quan hệ chỉ là membership không có thuộc tính riêng, một link đến tài nguyên thành viên có thể đủ. Nếu quan hệ có thuộc tính hoặc vòng đời riêng, hãy xem xét tạo association resource tường minh.

## Công bố to-many association bằng Spring HATEOAS

Spring HATEOAS cung cấp các model để biểu diễn tài nguyên và collection:

| Kiểu | Vai trò trong association |
| --- | --- |
| `EntityModel<T>` | Một tài nguyên con cùng các link riêng |
| `CollectionModel<T>` | Collection các tài nguyên con và link ở cấp collection |
| `PagedModel<T>` | Collection phân trang, có metadata và link điều hướng |
| `RepresentationModel<T>` | Model tùy chỉnh có thể mang links |

Trong response cha, thêm link đến collection endpoint. Trong endpoint collection, trả `CollectionModel` chứa item models.

### Domain và DTO

Ví dụ domain model:

~~~java
public record Order(Long id, String orderNumber, String status) {}

public record OrderItem(
    Long id,
    Long orderId,
    Long productId,
    String sku,
    int quantity,
    long unitPrice
) {}

public record OrderResponse(
    Long id,
    String orderNumber,
    String status
) {}

public record OrderItemResponse(
    Long id,
    String sku,
    int quantity,
    long unitPrice
) {}
~~~

Các kiểu trên chỉ minh họa dữ liệu cần cho bài học. Trong ứng dụng thực tế, domain entity có thể là class có hành vi và quan hệ; DTO được thiết kế riêng để công bố qua API.

### Assembler cho tài nguyên cha

Assembler của đơn hàng tạo self link và link đến collection items:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        OrderResponse content = new OrderResponse(
            order.id(), order.orderNumber(), order.status());

        return EntityModel.of(content,
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel(),
            linkTo(methodOn(OrderController.class).items(order.id()))
                .withRel("items"));
    }
}
~~~

Link `items` trỏ đến collection endpoint. Việc tạo link không tải các dòng hàng; nó chỉ công bố nơi client có thể khám phá chúng.

### Assembler cho item

Mỗi dòng hàng có thể có self link và link đến sản phẩm:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderItemModelAssembler
        implements RepresentationModelAssembler<OrderItem, EntityModel<OrderItemResponse>> {

    @Override
    public EntityModel<OrderItemResponse> toModel(OrderItem item) {
        OrderItemResponse content = new OrderItemResponse(
            item.id(), item.sku(), item.quantity(), item.unitPrice());

        return EntityModel.of(content,
            linkTo(methodOn(OrderController.class)
                .item(item.orderId(), item.id()))
                .withSelfRel(),
            linkTo(methodOn(ProductController.class)
                .one(item.productId()))
                .withRel("product"));
    }
}
~~~

Ví dụ giả định `OrderItem` cung cấp `orderId()` và `productId()`, còn `ProductController.one(id)` là endpoint sản phẩm. Nếu item không cần link sản phẩm, có thể bỏ relation `product`.

### Controller cho collection và item

~~~java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderAssembler;
    private final OrderItemModelAssembler itemAssembler;

    OrderController(
            OrderService orderService,
            OrderModelAssembler orderAssembler,
            OrderItemModelAssembler itemAssembler) {
        this.orderService = orderService;
        this.orderAssembler = orderAssembler;
        this.itemAssembler = itemAssembler;
    }

    @GetMapping("/{orderId}")
    EntityModel<OrderResponse> one(@PathVariable Long orderId) {
        Order order = orderService.findById(orderId)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        return orderAssembler.toModel(order);
    }

    @GetMapping("/{orderId}/items")
    CollectionModel<EntityModel<OrderItemResponse>> items(
            @PathVariable Long orderId) {
        orderService.requireOrder(orderId);

        List<EntityModel<OrderItemResponse>> content =
            orderService.findItems(orderId).stream()
                .map(itemAssembler::toModel)
                .toList();

        return CollectionModel.of(content,
            linkTo(methodOn(OrderController.class).items(orderId)).withSelfRel(),
            linkTo(methodOn(OrderController.class).one(orderId)).withRel("order"));
    }

    @GetMapping("/{orderId}/items/{itemId}")
    EntityModel<OrderItemResponse> item(
            @PathVariable Long orderId,
            @PathVariable Long itemId) {
        OrderItem item = orderService.findItem(orderId, itemId)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        return itemAssembler.toModel(item);
    }
}
~~~

Ví dụ giả định `OrderService.requireOrder` kiểm tra đơn hàng tồn tại và `findItems` chỉ trả các item thuộc đơn hàng được chỉ định. `findItem(orderId, itemId)` cũng phải giới hạn theo cả hai ID để không cho truy cập item thuộc đơn hàng khác bằng cách thay path parameter.

Controller trả `CollectionModel<EntityModel<OrderItemResponse>>`. Khi serialize thành HAL, serializer đặt các item dưới `_embedded` theo collection relation và giữ link riêng của từng item.

Tên relation trong `_embedded` phụ thuộc `LinkRelationProvider` và kiểu representation. Nếu muốn tên cố định là `items`, dùng model tùy chỉnh có `@Relation(collectionRelation = "items")` như ví dụ ở phần tiếp theo, hoặc cấu hình relation provider tương ứng cho kiểu representation đang dùng.

## Đặt tên relation cho collection

Tên relation là một phần của hợp đồng hypermedia. Với link từ đơn hàng đến collection, ví dụ dùng `items`. Với response collection, relation nhúng có thể được suy ra từ kiểu model hoặc được cấu hình rõ.

Nếu dùng model tùy chỉnh cho item:

~~~java
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(value = "orderItem", collectionRelation = "items")
public class OrderItemModel extends RepresentationModel<OrderItemModel> {

    private final Long id;
    private final String sku;
    private final int quantity;

    public OrderItemModel(Long id, String sku, int quantity) {
        this.id = id;
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

`@Relation` cho phép xác định relation của item bằng `value` và relation của collection bằng `collectionRelation`. `LinkRelationProvider` của Spring HATEOAS sử dụng metadata này khi xác định relation cho representation.

Chọn relation theo ngữ nghĩa API, không chỉ theo tên class Java. Nếu client đã phụ thuộc vào `items`, đổi relation thành `orderItems` có thể làm client không còn khám phá được association dù URI vẫn tồn tại.

## Collection rỗng và association không có phần tử

Một association to-many có thể hợp lệ khi không có phần tử. Ví dụ đơn hàng nháp chưa có dòng hàng. Cần phân biệt:

- Collection tồn tại nhưng hiện có 0 item.
- Association không được công bố hoặc không áp dụng cho tài nguyên đó.
- Tài nguyên cha không tồn tại.
- Người dùng không có quyền xem collection.

Nếu đơn hàng tồn tại nhưng chưa có dòng hàng, endpoint collection thường trả `200 OK` cùng collection rỗng và self link:

~~~json
{
  "_links": {
    "self": { "href": "/orders/42/items" },
    "order": { "href": "/orders/42" }
  }
}
~~~

Không nên trả `404 Not Found` chỉ vì collection không có phần tử. `404` phù hợp khi tài nguyên cha hoặc collection endpoint không tồn tại theo hợp đồng. Collection rỗng vẫn là một representation hợp lệ.

Với collection model rỗng, serializer có thể cần fallback type để xác định embedded relation. Có thể cung cấp fallback type:

~~~java
CollectionModel<OrderItemModel> empty =
    CollectionModel.<OrderItemModel>empty()
        .withFallbackType(OrderItemModel.class)
        .add(linkTo(methodOn(OrderController.class).items(orderId)).withSelfRel());
~~~

Hãy kiểm thử response rỗng để bảo đảm relation và links vẫn ổn định.

## Phân trang cho to-many association

Một association có thể chứa hàng nghìn phần tử. Không nên luôn tải toàn bộ collection chỉ vì quan hệ được mô hình hóa là to-many.

Khi cần page-based pagination, thay method collection ở ví dụ controller phía trên bằng phiên bản nhận `Pageable` và dùng `PagedResourcesAssembler`:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.PagedModel;

@GetMapping("/{orderId}/items")
PagedModel<EntityModel<OrderItemResponse>> items(
        @PathVariable Long orderId,
        Pageable pageable,
        PagedResourcesAssembler<OrderItem> pagedAssembler) {

    Page<OrderItem> page = orderService.findItems(orderId, pageable);
    return pagedAssembler.toModel(page, itemAssembler);
}
~~~

Ví dụ giả định `OrderItemModelAssembler` triển khai `RepresentationModelAssembler<OrderItem, EntityModel<OrderItemResponse>>` và service trả `Page<OrderItem>`. `PagedResourcesAssembler` chuyển page thành `PagedModel`, tạo metadata và links điều hướng.

Khi thay chữ ký method collection bằng phiên bản phân trang, cập nhật lời gọi `methodOn(OrderController.class).items(...)` trong assembler của đơn hàng cho khớp chữ ký mới, hoặc dùng link builder phù hợp để tạo URI collection mặc định. Không giữ hai method có cùng `@GetMapping` và cùng path chỉ khác tham số Java vì chúng sẽ xung đột mapping ở runtime.

Client nên theo các relation `self`, `next`, `prev`, `first` hoặc `last` do server cung cấp thay vì tự ghép query parameter. Nếu không cần tổng số phần tử, có thể dùng `Slice` hoặc cursor-based collection với link `next`.

## Embed association hay chỉ cung cấp link?

To-many association không bắt buộc phải nhúng toàn bộ phần tử vào response cha. Có thể chọn:

| Cách | Response cha | Khi phù hợp |
| --- | --- | --- |
| Link đến collection | Có `_links.items` | Collection lớn, được tải riêng hoặc cần phân trang |
| Embed summary | Có dữ liệu tóm tắt của các item | Client thường cần một số trường nhỏ ngay lập tức |
| Embed full collection | Có toàn bộ biểu diễn các item | Collection nhỏ, giới hạn rõ và thường được đọc cùng cha |

Ví dụ link-first:

~~~json
{
  "id": 42,
  "status": "DRAFT",
  "_links": {
    "self": { "href": "/orders/42" },
    "items": { "href": "/orders/42/items" }
  }
}
~~~

Ví dụ một DTO có trường `items` dạng array không tự động trở thành HAL embedded resource. Đó có thể chỉ là dữ liệu JSON lồng nhau. Embedded resource theo HAL được serializer biểu diễn dưới `_embedded` theo relation. Nếu cần HAL embedded collection, hãy trả representation model phù hợp và kiểm tra cấu trúc HAL thực tế.

Link đến collection thường là lựa chọn linh hoạt cho quan hệ lớn hoặc cần phân trang. Embed giúp giảm request nhưng làm response cha lớn hơn và có thể làm dữ liệu nhúng cũ khi tài nguyên con thay đổi.

## Thêm phần tử vào association

Một collection resource thường cung cấp endpoint để thêm phần tử. Với order items, API có thể nhận lệnh thêm dòng hàng:

~~~java
public record AddOrderItemRequest(
    Long productId,
    int quantity
) {}
~~~

Controller có thể khai báo:

~~~java
import java.net.URI;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;

@PostMapping("/{orderId}/items")
ResponseEntity<EntityModel<OrderItemResponse>> addItem(
        @PathVariable Long orderId,
        @RequestBody AddOrderItemRequest request) {

    OrderItem created = orderService.addItem(orderId, request);
    EntityModel<OrderItemResponse> body = itemAssembler.toModel(created);

    return ResponseEntity
        .created(URI.create(body.getRequiredLink("self").getHref()))
        .body(body);
}
~~~

Ví dụ giả định service xác minh sản phẩm tồn tại, đơn hàng còn cho phép thay đổi, số lượng hợp lệ và người dùng có quyền chỉnh sửa. Các import `PostMapping`, `RequestBody`, `ResponseEntity` và `URI` cần được khai báo trong controller.

Một response đơn hàng có thể công bố link `items` đến collection; client theo link và gửi POST đến collection endpoint nếu hợp đồng cho phép thêm item. Nếu muốn mô tả method và request fields cho client, có thể gắn affordance vào link và thương lượng media type hỗ trợ affordance.

## Xóa phần tử và phân biệt xóa item với gỡ association

`DELETE` cần có semantics rõ ràng:

- Xóa association có nghĩa là bỏ liên kết giữa tài nguyên cha và tài nguyên con.
- Xóa tài nguyên con có nghĩa là tài nguyên đó không còn tồn tại.

Hai hành động này không giống nhau. Nếu một sản phẩm được dùng trong nhiều đơn hàng, xóa dòng hàng khỏi một đơn hàng không được xóa sản phẩm.

Với `OrderItem` là association resource thuộc đơn hàng, endpoint:

~~~http
DELETE /orders/42/items/101
~~~

có thể mang nghĩa xóa dòng hàng 101 khỏi đơn hàng 42. Service phải kiểm tra item thực sự thuộc đơn hàng 42, đơn hàng còn cho phép chỉnh sửa và người dùng có quyền thực hiện.

Nếu association chỉ là membership giữa hai tài nguyên độc lập, có thể dùng endpoint riêng cho quan hệ, ví dụ `/projects/5/members/12`, để semantics xóa chỉ gỡ membership. Hãy tài liệu hóa rõ điều gì bị xóa.

## Bảo mật và tính toàn vẹn của association

Không nên dựa vào link đã công bố để kết luận client được quyền thao tác. Server cần kiểm tra:

- Người dùng có quyền truy cập tài nguyên cha không?
- Tài nguyên con có thuộc tài nguyên cha không?
- Người dùng có quyền xem hoặc thay đổi association không?
- Trạng thái hiện tại có cho phép thêm hoặc gỡ phần tử không?
- Thao tác có vi phạm giới hạn nghiệp vụ như số lượng tối đa hoặc trùng thành viên không?
- Tenant hoặc chủ sở hữu của hai phía có phù hợp không?

Đặc biệt, endpoint dạng `/orders/{orderId}/items/{itemId}` phải kiểm tra cả hai định danh. Nếu chỉ tìm item theo `itemId` mà bỏ qua `orderId`, client có thể dùng path của đơn hàng này để truy cập item thuộc đơn hàng khác.

Với dữ liệu nhạy cảm, kiểm tra quyền ở cấp item trước khi đưa item vào collection. Việc không hiển thị link hoặc không embed không thay thế authorization.

## Hiệu năng và tính nhất quán

To-many association có thể tạo ra response lớn và truy vấn tốn kém. Hãy cân nhắc:

- Dùng projection/DTO chỉ chứa trường client cần.
- Tránh N+1 khi tải item và quan hệ liên quan; dùng batch query hoặc fetch strategy phù hợp.
- Phân trang collection lớn.
- Đặt giới hạn page size để client không yêu cầu quá nhiều dữ liệu.
- Dùng sort ổn định, có tie-breaker duy nhất, để giảm việc item lặp hoặc mất khi dữ liệu thay đổi.
- Xem xét cache và ETag nếu collection được đọc thường xuyên.
- Xác định cách cập nhật collection khi tài nguyên cha hoặc item thay đổi.

Nếu collection thay đổi liên tục, client duyệt page theo offset có thể thấy phần tử dịch chuyển giữa các trang. Với dữ liệu lớn hoặc cập nhật liên tục, cursor pagination có thể phù hợp hơn.

Nếu nhiều người cùng sửa association, cần xác định quy tắc xung đột. Có thể dùng ETag/If-Match cho tài nguyên cha hoặc association resource, transaction và ràng buộc ở tầng domain/database.

## Kiểm thử to-many association

Kiểm thử nên bao phủ link từ tài nguyên cha, collection response, item links và các quy tắc nghiệp vụ.

Ví dụ với Spring MVC Test:

~~~java
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
class OrderAssociationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void orderExposesItemsCollectionLink() throws Exception {
        mockMvc.perform(get("/orders/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.items.href")
                .value(endsWith("/orders/42/items")));
    }

    @Test
    void itemsCollectionEmbedsEachItemWithSelfLink() throws Exception {
        mockMvc.perform(get("/orders/{orderId}/items", 42)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._embedded.items").isArray())
            .andExpect(jsonPath("$._embedded.items[0]._links.self.href").exists());
    }
}
~~~

Ví dụ giả định đơn hàng 42 tồn tại, có ít nhất một dòng hàng và relation collection được cấu hình là `items`. Nếu relation mặc định của ứng dụng khác, điều chỉnh JSONPath theo hợp đồng thực tế.

Các trường hợp nên kiểm thử:

1. Tài nguyên cha công bố relation đến collection đúng URI.
2. Collection chứa đúng các item thuộc tài nguyên cha.
3. Mỗi item có self link trỏ đến đúng endpoint.
4. Collection rỗng trả response hợp lệ với self link.
5. Collection lớn trả metadata và link phân trang đúng.
6. Item không thuộc cha không thể truy cập qua endpoint lồng.
7. Thêm item hợp lệ trả status và Location phù hợp.
8. Gỡ association không vô tình xóa tài nguyên độc lập.
9. Người dùng không có quyền không thể đọc hoặc sửa association.
10. Relation và schema không thay đổi ngoài ý muốn khi refactor tên class hoặc controller.

## Những sai lầm thường gặp

**Serialize trực tiếp collection JPA.** Cách này có thể làm lộ cấu trúc persistence, tạo vòng lặp serialization hoặc tải dữ liệu ngoài ý muốn. Hãy dùng DTO, assembler và model HATEOAS.

**Nghĩ to-many luôn phải embed.** Quan hệ có nhiều phần tử thường phù hợp với collection endpoint riêng và link từ tài nguyên cha.

**Nhầm association với tài nguyên con.** Nếu quan hệ có thuộc tính như quantity hoặc role, chính association có thể cần là một resource độc lập.

**Dùng ID để client tự ghép URI.** Công bố relation và href để client khám phá collection, item và thao tác.

**Trả 404 khi collection rỗng.** Nếu cha tồn tại và collection hợp lệ nhưng chưa có phần tử, trả collection rỗng thay vì coi collection không tồn tại.

**Không kiểm tra item có thuộc cha.** Luôn xác minh cả parent ID và item ID ở endpoint lồng.

**Nhầm gỡ association với xóa tài nguyên.** Xác định semantics của DELETE để tránh xóa nhầm tài nguyên được dùng ở nơi khác.

**Không phân trang collection lớn.** Payload lớn và truy vấn sâu có thể làm API chậm. Dùng PagedModel, Slice hoặc cursor phù hợp.

**Coi link là quyền truy cập.** Server phải xác thực, phân quyền và kiểm tra trạng thái khi xử lý request.

## Kết luận

To-many association biểu diễn quan hệ từ một tài nguyên đến không hoặc nhiều tài nguyên liên quan. Trong REST/HATEOAS, cách linh hoạt là công bố link relation từ tài nguyên cha đến collection endpoint, trả collection bằng CollectionModel hoặc PagedModel, và cung cấp self link cho từng item. Khi association có dữ liệu hoặc vòng đời riêng, hãy xem nó như một association resource.

Hãy quyết định rõ URI của item, tên relation, chính sách embed/link, phân trang và semantics của thao tác thêm hoặc gỡ quan hệ. Dùng assembler để tạo representation, kiểm tra quyền ở cả parent và item, tránh N+1 và kiểm thử collection rỗng, item links cùng các trường hợp xung đột. Cách thiết kế này giúp client khám phá quan hệ mà không phụ thuộc vào cấu trúc JPA hay quy tắc URL tự ghép.
