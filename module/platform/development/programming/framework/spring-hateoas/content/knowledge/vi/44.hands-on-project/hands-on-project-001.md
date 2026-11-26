# Chọn API tài nguyên

Trước khi viết controller hoặc assembler, hãy quyết định API sẽ công bố những tài nguyên nào và client có thể khám phá chúng ra sao. Nếu chọn resource model không tốt, các bước sau thường dẫn đến URI phản ánh bảng database, endpoint CRUD cho mọi class, link khó hiểu hoặc một API mà client phải tự ghép đường dẫn để hoàn thành quy trình.

Bài thực hành này khởi tạo dự án Spring HATEOAS bằng một bài toán quản lý đơn hàng của cửa hàng trực tuyến. Mục tiêu là biến yêu cầu nghiệp vụ thành resource model có identity, trạng thái, quan hệ và các đường dẫn điều hướng rõ ràng. Kết quả của bài là bản thiết kế tài nguyên và URI để các bài sau có thể triển khai representation, link, collection, affordance và kiểm thử.

## Bối cảnh dự án

Cửa hàng cần một API cho các nhóm client sau:

- Ứng dụng web để nhân viên xem và xử lý đơn hàng.
- Ứng dụng của khách hàng để xem đơn, sản phẩm và tình trạng giao hàng.
- Dịch vụ kho vận để nhận đơn đã duyệt và cập nhật shipment.
- Dịch vụ thanh toán để ghi nhận payment và trạng thái hoàn tiền.

Các luồng chính:

1. Nhân viên tạo đơn hàng cho khách.
2. Nhân viên xem chi tiết đơn và các mặt hàng.
3. Người có quyền duyệt đơn thực hiện approve hoặc cancel khi trạng thái cho phép.
4. Sau khi duyệt, đơn có thể được giao cho kho vận và tạo shipment.
5. Khách hàng theo dõi đơn, shipment và payment của mình.
6. Nhân viên tìm đơn theo trạng thái, khách hàng, thời gian và phân trang.

Đây là phạm vi đủ để luyện tập resource modeling, nhưng không yêu cầu mô hình hóa mọi chi tiết của một hệ thống thương mại điện tử. Không cần đưa vào API các khái niệm nội bộ chưa có nhu cầu client rõ ràng.

## Bắt đầu từ nhu cầu client

Không bắt đầu bằng cách liệt kê các bảng database. Hãy ghi lại điều client muốn xem hoặc thực hiện:

| Nhu cầu | Câu hỏi cần trả lời |
| --- | --- |
| Xem các đơn hàng | Có collection resource để lọc và phân trang không? |
| Xem một đơn | Đơn có identity ổn định và self link không? |
| Xem mặt hàng trong đơn | Item có vòng đời riêng hay chỉ tồn tại trong phạm vi order? |
| Xem khách hàng | Customer có thể được truy cập độc lập từ nhiều luồng không? |
| Theo dõi giao hàng | Shipment có trạng thái và identity riêng không? |
| Xem thanh toán | Payment có lịch sử, trạng thái và thao tác riêng không? |
| Duyệt hoặc hủy đơn | Hành động nào hợp lệ ở từng trạng thái và ai được phép thực hiện? |

Từ mỗi nhu cầu, xác định client cần một representation có thể đọc, một collection để tìm kiếm, một resource có thể tham chiếu hoặc một hành động làm thay đổi state. Một danh từ xuất hiện trong domain chưa chắc phải trở thành top-level API resource.

## Tiêu chí chọn một resource

Một khái niệm phù hợp để công bố thành resource khi có một hoặc nhiều đặc điểm sau:

- **Identity:** client cần tham chiếu ổn định đến một đối tượng cụ thể.
- **Lifecycle:** đối tượng có trạng thái và vòng đời có ý nghĩa độc lập.
- **Addressability:** client cần đọc, theo dõi hoặc liên kết đến nó qua URI.
- **Ownership/relationship:** đối tượng có quan hệ rõ với resource khác.
- **Representation:** client cần một góc nhìn dữ liệu riêng, không chỉ một field trong resource cha.
- **Operations:** có các thao tác hoặc chuyển trạng thái riêng cần được công bố.

Resource API là mô hình công khai phục vụ client, không phải bản sao cấu trúc persistence. Một aggregate có thể được biểu diễn bằng nhiều resource; nhiều bảng có thể hợp thành một representation; một bảng join không nhất thiết cần URI riêng.

### Resource hay thuộc tính?

Hãy tự hỏi: client có cần bookmark hoặc chia sẻ URI của khái niệm này không? Nó có trạng thái hoặc quyền truy cập riêng không? Nó có thể tồn tại sau khi resource cha thay đổi không? Nếu câu trả lời phần lớn là không, có thể nó chỉ là thuộc tính hoặc embedded item.

Ví dụ:

- Order.status là thuộc tính của order, không cần /statuses/{id} chỉ để biểu diễn giá trị trạng thái.
- OrderItem thường thuộc vòng đời của order. Nếu client chỉ thao tác với item trong phạm vi order, collection /orders/{orderId}/items là đủ.
- Shipment có mã theo dõi và trạng thái giao hàng độc lập. Client có lý do để theo một shipment resource riêng.
- Payment có transaction ID, trạng thái, thời gian và lịch sử riêng. Nó thường phù hợp với resource riêng.

## Lập resource inventory

Với bài toán cửa hàng, inventory ban đầu có thể như sau:

| Resource | Identity | Vòng đời | Cách công bố |
| --- | --- | --- | --- |
| Order | orderId | PENDING, APPROVED, SHIPPED, CANCELLED | Top-level item và collection. |
| Order item | itemId trong một order | Thường theo vòng đời order | Subresource của order hoặc embedded item. |
| Customer | customerId | Độc lập với order | Top-level item và collection. |
| Product | productId | Độc lập với order | Top-level item và collection. |
| Shipment | shipmentId | CREATED, IN_TRANSIT, DELIVERED, FAILED | Top-level item, liên kết từ order. |
| Payment | paymentId | PENDING, AUTHORIZED, CAPTURED, REFUNDED, FAILED | Top-level item, liên kết từ order. |

Order là aggregate quan trọng trong luồng đặt hàng. OrderItem thường được quản lý bên trong aggregate này: số lượng hoặc giá tại thời điểm mua thuộc snapshot của đơn. Product là catalog resource độc lập; không nên dùng một product hiện tại để thay thế giá hoặc tên đã chốt trong đơn cũ.

Shipment và Payment có vòng đời riêng, được cập nhật bởi các quy trình khác nhau. Vì vậy, order có thể liên kết đến chúng mà không cần nhúng toàn bộ lịch sử vào mọi response order.

Inventory này là giả thuyết thiết kế ban đầu. Nếu yêu cầu sản phẩm thay đổi, hãy điều chỉnh dựa trên nhu cầu client và ownership, không giữ resource chỉ vì nó đã xuất hiện trong bảng.

## Chọn collection, item, subresource và association

Bốn hình thức thường gặp:

| Hình thức | Dùng khi | Ví dụ |
| --- | --- | --- |
| Collection resource | Client cần tìm kiếm hoặc tạo nhiều item cùng loại | /api/orders |
| Item resource | Một đối tượng có identity riêng | /api/orders/{orderId} |
| Subresource | Dữ liệu thuộc phạm vi hoặc vòng đời resource cha | /api/orders/{orderId}/items |
| Association resource/view | Client cần điều hướng một quan hệ giữa hai resource | /api/customers/{customerId}/orders |

### Collection và item

Collection URI thường dùng danh từ số nhiều:

~~~http
GET /api/orders
~~~

Response collection có thể chứa embedded item và link tới từng item, cùng các link phân trang:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "o-42",
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "/api/orders/o-42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/api/orders?page=0&size=20"
    },
    "next": {
      "href": "/api/orders?page=1&size=20"
    }
  }
}
~~~

Item URI có identity ổn định:

~~~http
GET /api/orders/o-42
~~~

Không dùng index trong collection làm identity như /api/orders/0; thứ tự collection có thể thay đổi khi filter, sort hoặc có dữ liệu mới.

### Subresource

Order item thường chỉ có ý nghĩa trong một order. Client có thể lấy chúng qua:

~~~http
GET /api/orders/o-42/items
~~~

Nếu item không có lifecycle riêng, không cần tạo thêm /api/order-items/{itemId} chỉ để phản chiếu khóa database. Khi item thực sự cần được tham chiếu độc lập từ nhiều workflow hoặc có quyền và vòng đời riêng, hãy cân nhắc URI top-level.

Đường dẫn lồng nhau nên thể hiện quan hệ sở hữu hoặc phạm vi truy cập rõ ràng. Tránh lồng nhiều tầng như /customers/{id}/orders/{id}/items/{id}/discounts/{id}. Khi URI trở nên sâu, hãy cấp URI riêng cho resource có identity độc lập và nối chúng bằng link.

### Association view

Khách hàng có nhiều order, nhưng order không phải dữ liệu con được tạo mới mỗi lần đọc customer. Có thể công bố một association collection:

~~~http
GET /api/customers/c-7/orders
~~~

Đây là một góc nhìn các order liên quan đến customer. Mỗi item vẫn trỏ về URI canonical /api/orders/{orderId}. Không cần tạo bản sao order dưới URI nested nếu cùng một resource có thể được điều hướng qua link.

## Thiết kế URI ban đầu

Một URI map gọn cho dự án:

~~~text
/api
  /orders
    /{orderId}
      /items
      /approval
      /cancellation
  /customers
    /{customerId}
      /orders
  /products
    /{productId}
  /shipments
    /{shipmentId}
  /payments
    /{paymentId}
~~~

Ý nghĩa:

- /api là entry point để client khám phá các collection cấp cao.
- /api/orders là collection order; hỗ trợ filter, sort và pagination.
- /api/orders/{orderId} là canonical item resource.
- /api/orders/{orderId}/items là các item thuộc order.
- /api/orders/{orderId}/approval và /cancellation là target cho thao tác chuyển trạng thái trong ví dụ này.
- /api/customers/{customerId}/orders là association view.
- /api/products/{productId}, /api/shipments/{shipmentId} và /api/payments/{paymentId} là item resource độc lập.

Các URI là hợp đồng công khai. Không đưa tên bảng, schema, package Java hoặc tên microservice vào path. Dùng chữ thường, danh từ số nhiều cho collection và định danh không mang ý nghĩa nội bộ.

### Filter và pagination thuộc collection

Các tiêu chí tìm kiếm là query parameter của collection:

~~~http
GET /api/orders?status=PENDING&customerId=c-7&page=0&size=20&sort=createdAt,desc
~~~

Filter không làm thay đổi identity của order. URI trên biểu diễn một kết quả collection có điều kiện; item vẫn có self URI riêng. Khi server tạo link next, prev, first và last, hãy giữ lại các filter và sort cần thiết.

## Không biến mọi thao tác thành resource CRUD

HTTP method diễn tả cách client tương tác với resource:

| Nhu cầu | Hướng thiết kế |
| --- | --- |
| Đọc collection | GET /api/orders |
| Đọc một order | GET /api/orders/{orderId} |
| Tạo order | POST /api/orders |
| Sửa thuộc tính được phép | PATCH /api/orders/{orderId} hoặc hợp đồng cập nhật phù hợp |
| Duyệt order | Theo link approve trên order và gửi POST đến target được công bố |
| Hủy order | Theo link cancel khi state cho phép và gửi POST đến target được công bố |
| Xem shipment | Theo link shipment đến shipment resource |
| Xem payment | Theo link payments đến payment resource/collection |

Không tạo endpoint kiểu /getOrders, /createOrder, /approveOrder chỉ để tên path lặp lại HTTP method hoặc tên hàm. Cũng không nên cho client sửa trực tiếp field status bằng PATCH nếu chuyển trạng thái phải tuân theo quy tắc nghiệp vụ như kiểm tra tồn kho, quyền duyệt hoặc thanh toán.

Trong ví dụ, /approval và /cancellation là target của các command. Nếu thao tác tạo ra một bản ghi quyết định có identity và lịch sử riêng, có thể mô hình hóa Approval hoặc Cancellation thành resource được tạo bằng POST và trả Location của resource mới. Chọn cách biểu diễn dựa trên lifecycle và nhu cầu truy cập lịch sử.

Một link HAL thông thường chỉ cung cấp relation và href; nó không tự mô tả HTTP method hoặc schema của request. Nếu client cần khám phá method và input, hãy công bố affordance bằng định dạng phù hợp như HAL-FORMS hoặc mô tả rõ trong contract API. Dù link có xuất hiện hay không, server vẫn phải kiểm tra quyền và state khi nhận command.

## Mô hình trạng thái để quyết định link

Resource selection cần nhìn cả vòng đời. Với order, state machine ban đầu:

~~~text
Order:
          approve
PENDING ------------> APPROVED ------------> SHIPPED
   |
   | cancel
   v
CANCELLED

Shipment:
CREATED ----------> IN_TRANSIT ----------> DELIVERED
   |
   +-------------------------------------> FAILED
~~~

Đây là mô hình rút gọn. Trạng thái giao hàng chi tiết thuộc Shipment; Order chỉ giữ trạng thái tổng hợp phù hợp với nghiệp vụ cửa hàng. Hãy quyết định rõ source of truth để không có hai resource cùng sở hữu một trạng thái chi tiết và cập nhật mâu thuẫn.

Các action link được công bố theo state và quyền:

| Order state | Link có thể công bố | Ghi chú |
| --- | --- | --- |
| PENDING, người có quyền duyệt | approve, cancel | Chỉ khi điều kiện nghiệp vụ còn đúng. |
| PENDING, người chỉ xem | Không có approve/cancel | Vẫn có self, customer, items. |
| APPROVED | Link tới shipment hoặc hành động tạo shipment nếu đủ điều kiện | Không còn approve. |
| SHIPPED | shipment, có thể có track | Theo dõi trạng thái ở Shipment. |
| CANCELLED | self, customer, items | Không công bố hành động duyệt hoặc giao hàng. |

Client không cần đoán state tiếp theo bằng cách tự tạo URL. Nó quan sát các relation hiện có rồi theo link tương ứng. Không có link là tín hiệu rằng hành động hiện không được công bố; endpoint vẫn phải xác thực và từ chối request trái phép.

## Định nghĩa relation cho API

Relation cho biết ý nghĩa của link, không chỉ tên của endpoint. Ưu tiên relation chuẩn khi semantics khớp:

| Relation | Ý nghĩa |
| --- | --- |
| self | Representation hiện tại. |
| collection | Collection chứa item. |
| item | Một item trong collection. |
| next, prev, first, last | Điều hướng trang. |

Các relation như customer, items, shipment, payments, approve và cancel mang semantics riêng của domain. Hãy định nghĩa relation URI ổn định hoặc dùng CURIE để rút gọn khi serialize HAL. Tài liệu relation nên nêu mục đích, target, HTTP method hoặc affordance liên quan và điều kiện xuất hiện.

Ví dụ HAL cho order đang chờ duyệt:

~~~json
{
  "id": "o-42",
  "status": "PENDING",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "/api/orders/o-42"
    },
    "collection": {
      "href": "/api/orders"
    },
    "curies": [
      {
        "name": "ex",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      }
    ],
    "ex:customer": {
      "href": "/api/customers/c-7"
    },
    "ex:items": {
      "href": "/api/orders/o-42/items"
    },
    "ex:approve": {
      "href": "/api/orders/o-42/approval"
    },
    "ex:cancel": {
      "href": "/api/orders/o-42/cancellation"
    }
  }
}
~~~

Khi order đã APPROVED, representation có thể bỏ ex:approve và thêm ex:shipment nếu shipment đã được tạo. Không giữ một action link cũ chỉ vì route vẫn tồn tại.

Ví dụ JSON dùng CURIE ex để rút gọn relation URI. Khi triển khai Spring HATEOAS, cần cấu hình CurieProvider tương ứng; nếu chưa cấu hình, hãy serialize relation bằng URI đầy đủ hoặc dùng relation đã đăng ký. Các constant LinkRelation trong assembler dùng URI đầy đủ để giữ semantics ổn định.

## Ánh xạ resource model vào Spring HATEOAS

Sau khi chốt resource inventory và URI, mới bắt đầu tạo representation. Ví dụ DTO của order:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderSummary(
        UUID id,
        UUID customerId,
        String status,
        BigDecimal total) {
}
~~~

Assembler biến DTO thành EntityModel và tạo link bằng controller mapping:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler implements
        RepresentationModelAssembler<OrderSummary, EntityModel<OrderSummary>> {

    private static final LinkRelation CUSTOMER =
            LinkRelation.of("https://api.example.com/rels/customer");
    private static final LinkRelation ITEMS =
            LinkRelation.of("https://api.example.com/rels/items");
    private static final LinkRelation APPROVE =
            LinkRelation.of("https://api.example.com/rels/approve");
    private static final LinkRelation CANCEL =
            LinkRelation.of("https://api.example.com/rels/cancel");

    @Override
    public EntityModel<OrderSummary> toModel(OrderSummary order) {
        EntityModel<OrderSummary> model = EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class)
                        .one(order.id())).withSelfRel(),
                linkTo(methodOn(OrderController.class)
                        .all()).withRel(IanaLinkRelations.COLLECTION));

        model.add(linkTo(methodOn(CustomerController.class)
                .one(order.customerId())).withRel(CUSTOMER));
        model.add(linkTo(methodOn(OrderController.class)
                .items(order.id())).withRel(ITEMS));

        if ("PENDING".equals(order.status())) {
            model.add(linkTo(methodOn(OrderController.class)
                    .approve(order.id())).withRel(APPROVE));
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.id())).withRel(CANCEL));
        }

        return model;
    }
}
~~~

Trong ví dụ, OrderController cần có các mapping one(UUID), all(), items(UUID), approve(UUID) và cancel(UUID); CustomerController cần có mapping one(UUID). Các DTO và controller này thuộc ứng dụng của bạn.

Không tạo URL bằng cách nối chuỗi "/api/orders/" + id trong assembler nếu có thể dùng WebMvcLinkBuilder. Cách gọi methodOn(...) giữ liên kết với mapping controller khi path thay đổi. Các relation tùy chỉnh vẫn cần semantics ổn định và tài liệu tương ứng.

Khung controller cần phản ánh URI map đã chọn:

~~~java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders/{id}")
    EntityModel<OrderSummary> one(@PathVariable UUID id) {
        throw new UnsupportedOperationException("Triển khai query và assembler");
    }

    @GetMapping("/api/orders")
    CollectionModel<EntityModel<OrderSummary>> all() {
        throw new UnsupportedOperationException("Triển khai collection query");
    }

    @GetMapping("/api/orders/{id}/items")
    CollectionModel<OrderItemModel> items(@PathVariable UUID id) {
        throw new UnsupportedOperationException("Triển khai item query");
    }

    @PostMapping("/api/orders/{id}/approval")
    ResponseEntity<Void> approve(@PathVariable UUID id) {
        throw new UnsupportedOperationException("Triển khai approval command");
    }

    @PostMapping("/api/orders/{id}/cancellation")
    ResponseEntity<Void> cancel(@PathVariable UUID id) {
        throw new UnsupportedOperationException("Triển khai cancellation command");
    }
}
~~~

Đây là khung chữ ký để làm rõ mapping; các thân hàm ném UnsupportedOperationException phải được thay bằng lời gọi application service trước khi chạy ứng dụng. OrderItemModel là DTO do dự án định nghĩa. Không đặt toàn bộ logic nghiệp vụ vào assembler; assembler quyết định representation và link dựa trên dữ liệu/policy đã được cung cấp. Controller nhận request, gọi application service và trả representation hoặc status phù hợp.

## API root để client khám phá tài nguyên

Client nên bắt đầu từ một entry point đã biết, sau đó khám phá collection bằng relation:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.RepresentationModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

class ApiRootModel extends RepresentationModel<ApiRootModel> {
}

@RestController
class ApiRootController {

    @GetMapping("/api")
    ApiRootModel root() {
        ApiRootModel model = new ApiRootModel();

        model.add(linkTo(methodOn(OrderController.class)
                .all()).withRel(
                        LinkRelation.of("https://api.example.com/rels/orders")));
        model.add(linkTo(methodOn(CustomerController.class)
                .all()).withRel(
                        LinkRelation.of("https://api.example.com/rels/customers")));
        model.add(linkTo(methodOn(ProductController.class)
                .all()).withRel(
                        LinkRelation.of("https://api.example.com/rels/products")));

        return model;
    }
}
~~~

Đây là root tối thiểu. Khi dự án triển khai shipment và payment, bổ sung relation tương ứng. Client biết /api theo cấu hình ban đầu; các URI tiếp theo được lấy từ link. Nếu dùng CURIE, khai báo CURIE provider phù hợp để client có thể hiểu các relation mở rộng.

## Chốt thiết kế trước khi triển khai

Trước khi viết thêm controller, hãy hoàn thành các đầu ra sau:

### 1. Resource inventory

Ghi tên resource, identity, owner, lifecycle và lý do client cần truy cập độc lập. Đánh dấu khái niệm nào chỉ là field hoặc embedded item.

### 2. URI map

Liệt kê collection, item, subresource và association view. Mỗi URI cần một mục đích rõ ràng, không chỉ phản ánh bảng database.

### 3. Relation catalog

Với từng relation, ghi:

| Thuộc tính | Nội dung cần xác định |
| --- | --- |
| Relation name/URI | Tên chuẩn hoặc URI mở rộng. |
| Source | Resource nào công bố link. |
| Target | Link dẫn đến collection, item hay command target nào. |
| Điều kiện | State, quyền hoặc dữ liệu nào làm link xuất hiện. |
| Semantics | Client có thể làm gì khi theo link. |
| Method/input | HTTP method và request metadata nếu là action. |

### 4. State transition map

Liệt kê trạng thái hợp lệ, command được phép và relation tương ứng. Không để client phải suy ra một thao tác từ field status rồi tự ghép URL.

### 5. Client traversal

Viết một luồng điều hướng không hard-code các URI con:

1. GET /api.
2. Theo relation orders.
3. Theo relation item trong collection.
4. Theo self link của order.
5. Theo customer hoặc items khi cần.
6. Nếu có relation approve, gửi request theo method/input đã được công bố.
7. Sau khi duyệt, đọc representation mới và khám phá shipment link nếu có.

## Bài tập thực hành

Hãy tự hoàn thành resource model cho dự án bằng cách trả lời:

1. Resource nào có identity và lifecycle độc lập?
2. Khái niệm nào nên là field hoặc embedded item?
3. Collection nào cần filter và pagination?
4. Association nào cần link riêng?
5. Command nào làm thay đổi state và điều kiện nào quyết định link khả dụng?
6. Relation nào dùng IANA relation, relation nào cần URI mở rộng?
7. Client bắt đầu từ URI nào và đi qua những relation nào để hoàn thành luồng duyệt/giao hàng?

Sau khi trả lời, tạo một bảng inventory và URI map của riêng bạn. So sánh với phương án tham khảo trong bài, ghi lại mọi khác biệt và lý do. Không cần giữ nguyên phương án mẫu nếu yêu cầu client của dự án chứng minh một resource model khác hợp lý hơn.

## Tiêu chí nghiệm thu

Thiết kế tài nguyên được xem là sẵn sàng cho bài triển khai tiếp theo khi:

- Mỗi top-level resource có identity và mục đích truy cập độc lập.
- Collection, item, subresource và association view được phân biệt rõ.
- URI dùng danh từ, ổn định và không để lộ cấu trúc persistence.
- Order item không bị tách thành resource độc lập nếu không có nhu cầu lifecycle/addressability.
- Product, customer, shipment và payment được tham chiếu bằng link khi phù hợp.
- Action link chỉ xuất hiện khi state và policy cho phép.
- Relation tùy chỉnh có semantics và URI tài liệu ổn định.
- API root cung cấp entry point để khám phá các collection.
- Client có thể đi theo link do server trả về mà không tự ghép URI.
- Authorization vẫn được kiểm tra tại endpoint, kể cả khi client đã nhận action link.

## Những sai lầm cần tránh

| Sai lầm | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Tạo một resource cho mỗi bảng | API phản ánh persistence và công bố khái niệm client không cần. | Bắt đầu từ nhu cầu và lifecycle của client. |
| Dùng endpoint theo tên hàm như /getOrders | URI lặp lại method và khó tiến hóa. | Dùng collection/item URI và HTTP method. |
| Dùng index collection làm ID | Link thay đổi khi sort/filter hoặc có item mới. | Dùng identity ổn định. |
| Lồng URI quá sâu | Client phụ thuộc cấu trúc quan hệ nội bộ. | Cấp URI riêng cho resource độc lập và điều hướng bằng link. |
| Nhúng toàn bộ shipment/payment vào mọi order | Response lớn và dữ liệu trùng lặp, khó freshness. | Link tới resource có lifecycle riêng. |
| Công bố mọi action cho mọi trạng thái | Client thấy thao tác chắc chắn bị từ chối. | Tạo link theo state và authorization. |
| Xem việc ẩn link là authorization | Client có thể tự gọi endpoint. | Kiểm tra quyền và state ở server. |
| Dùng relation related1, action2 | Client không biết semantics. | Dùng relation chuẩn hoặc URI relation có tài liệu. |
| Để client tự ghép /api/orders/{id}/approval | Client phụ thuộc route implementation. | Công bố action link/affordance trong representation. |

## Kết quả của bài

Sau bài này, dự án có một resource inventory, URI map, relation catalog, state transition map và luồng client traversal ban đầu. Đây là nền tảng để triển khai RepresentationModel, EntityModel, CollectionModel, assembler và controller ở các phần tiếp theo.

Việc chọn API tài nguyên tốt giúp Spring HATEOAS thể hiện đúng các khái niệm mà client cần, đồng thời giữ quyền thay đổi cách lưu trữ và tổ chức service ở phía server. Hãy chốt resource và semantics trước khi mở rộng code; mọi link được công bố sau đó cần phản ánh đúng identity, quan hệ, state và hành động mà API cam kết.
