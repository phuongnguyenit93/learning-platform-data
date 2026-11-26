# Thiết kế resource

Khi xây dựng API quản lý đơn hàng, ta có thể bắt đầu bằng cách liệt kê các bảng trong cơ sở dữ liệu rồi tạo một endpoint cho mỗi bảng. Cách làm này nhanh ở giai đoạn đầu nhưng thường khiến API phản chiếu cấu trúc lưu trữ: client phải biết đơn hàng được ghép từ những bảng nào, phải gọi nhiều endpoint để hoàn thành một thao tác và dễ bị ảnh hưởng khi mô hình dữ liệu thay đổi.

Thiết kế resource trong REST bắt đầu từ những khái niệm mà client cần nhận biết và tương tác. Một đơn hàng, khách hàng, mặt hàng trong đơn, khoản thanh toán hoặc yêu cầu hủy có thể là resource nếu chúng có ý nghĩa trong miền nghiệp vụ và cần được truy cập qua API. Spring HATEOAS giúp biểu diễn các resource đó bằng dữ liệu cùng liên kết hypermedia, để client khám phá quan hệ và hành động tiếp theo.

## Resource là gì?

Resource là một khái niệm được định danh trong hệ thống và có thể được tham chiếu qua một URI. Resource có thể là một đối tượng cụ thể, một tập hợp, một khái niệm nghiệp vụ hoặc một kết quả tính toán. Resource không đồng nghĩa với một dòng trong cơ sở dữ liệu.

Ví dụ trong hệ thống bán hàng:

| Resource | Ý nghĩa với client | Ví dụ URI |
| --- | --- | --- |
| Danh sách đơn hàng | Tập hợp đơn hàng mà người dùng có quyền xem | `/api/orders` |
| Một đơn hàng | Thông tin và trạng thái của một đơn cụ thể | `/api/orders/ord-1042` |
| Khách hàng | Thông tin khách hàng được công khai qua API | `/api/customers/cus-73` |
| Các dòng hàng của đơn | Những mặt hàng và số lượng thuộc đơn hàng | `/api/orders/ord-1042/items` |
| Một yêu cầu hủy | Yêu cầu nghiệp vụ ghi nhận việc hủy đơn | `/api/orders/ord-1042/cancellations/can-19` |

URI giúp định danh resource. Representation là dữ liệu được trao đổi để mô tả resource tại một thời điểm và trong một ngữ cảnh cụ thể. Cùng một resource có thể có nhiều representation tùy media type, quyền của người gọi hoặc mục đích sử dụng. Ví dụ, chi tiết đơn hàng có thể được biểu diễn đầy đủ cho nhân viên hỗ trợ và ở dạng tóm tắt cho màn hình danh sách.

Resource cũng không nhất thiết phải có một đối tượng Java hoặc một bảng riêng. Một resource `monthly-sales-report` có thể được tổng hợp từ nhiều bảng; một resource `search-results` có thể là kết quả truy vấn tạm thời. Điều quan trọng là resource có ý nghĩa ổn định đối với client và có hợp đồng truy cập rõ ràng.

## Phân biệt resource, representation và entity

Ba khái niệm này thường bị dùng lẫn nhau nhưng phục vụ các vai trò khác nhau:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Resource | Client đang nói đến khái niệm nào? | Đơn hàng `ord-1042`. |
| Representation | API đang gửi cách mô tả nào của resource? | JSON gồm mã đơn, trạng thái, tổng tiền và `_links`. |
| Domain entity / persistence entity | Ứng dụng lưu trữ và thực thi quy tắc nghiệp vụ bằng cấu trúc nào? | Đối tượng `Order` trong domain hoặc entity JPA ánh xạ bảng `orders`. |

Không nên mặc định trả trực tiếp JPA entity làm representation. Entity lưu trữ có thể chứa quan hệ hai chiều, trường nội bộ, thông tin kiểm toán hoặc cấu trúc tối ưu cho truy vấn. Đưa nguyên trạng nó ra API làm hợp đồng bên ngoài phụ thuộc vào schema cơ sở dữ liệu và có thể vô tình công khai dữ liệu.

Một thiết kế rõ ràng thường có lớp domain để thực thi nghiệp vụ, DTO hoặc projection để chọn dữ liệu cần công bố, và representation model của Spring HATEOAS để thêm liên kết. Các lớp này có thể được tổ chức gọn trong ứng dụng nhỏ, nhưng trách nhiệm của chúng vẫn nên được phân biệt.

## Xác định resource từ nghiệp vụ

Để tìm resource phù hợp, hãy xem xét các danh từ và khái niệm mà người dùng hoặc hệ thống bên ngoài cần tham chiếu, sau đó kiểm tra chúng bằng các câu hỏi:

1. Khái niệm này có ý nghĩa riêng trong nghiệp vụ hay chỉ là chi tiết triển khai?
2. Client có cần đọc, tạo, cập nhật, xóa hoặc theo dõi vòng đời của nó không?
3. Nó có định danh hoặc URI ổn định để client tham chiếu không?
4. Nó có quan hệ với resource khác cần được khám phá không?
5. Trạng thái hoặc quyền truy cập có làm thay đổi những hành động khả dụng không?

Ví dụ, `Order` thường là resource vì có mã định danh, trạng thái, lịch sử và nhiều thao tác nghiệp vụ. `OrderLine` có thể là resource con nếu client cần truy cập hoặc cập nhật từng dòng hàng. Ngược lại, một cột kỹ thuật như `row_version` thường chỉ là chi tiết lưu trữ; nó không nhất thiết cần một URI riêng.

Không phải mọi thao tác nghiệp vụ đều phải trở thành resource độc lập. Nếu thao tác tạo ra một kết quả có vòng đời và cần được theo dõi, chẳng hạn yêu cầu hủy, hoàn tiền hoặc đổi trả, có thể mô hình hóa kết quả đó thành resource. Nếu thao tác chỉ là một chuyển đổi trạng thái trên resource hiện tại, API có thể cung cấp affordance dẫn đến endpoint thực hiện chuyển đổi.

## Tổ chức URI cho resource

URI nên dễ đọc, nhất quán và có ý nghĩa định danh. Một quy ước thường dùng là đặt tên collection bằng danh từ số nhiều, sau đó dùng định danh để truy cập item:

```text
/api/orders
/api/orders/{orderId}
/api/orders/{orderId}/items
/api/orders/{orderId}/items/{itemId}
/api/customers/{customerId}
```

Một số nguyên tắc thực tế:

- **Dùng danh từ cho resource:** `/orders`, `/customers`, `/payments`. HTTP method thể hiện loại thao tác trên resource.
- **Phân biệt collection và item:** `/orders` đại diện tập hợp; `/orders/{id}` đại diện một đơn hàng.
- **Dùng quan hệ lồng nhau khi thể hiện ngữ cảnh sở hữu hoặc phạm vi:** `/orders/{id}/items` diễn tả các dòng hàng của đơn. Không lồng quá sâu nếu URI trở nên dài và lặp lại thông tin.
- **Giữ định danh ổn định:** tên hoặc trạng thái có thể thay đổi, nhưng ID của resource nên ổn định trong vòng đời của nó.
- **Dùng query parameter để lọc, sắp xếp và phân trang collection:** ví dụ `/orders?status=PENDING&page=0&size=20`.
- **Không đưa chi tiết lưu trữ vào URI:** tránh các đường dẫn phản ánh tên bảng, tên cột hoặc cấu trúc schema nội bộ.

URI lồng nhau có thể hữu ích để thể hiện phạm vi, nhưng không bắt buộc mọi quan hệ phải được mã hóa thành path. Ví dụ, khách hàng của một đơn hàng có thể được cung cấp bằng liên kết `customer` trong representation. Client không cần tự đoán rằng khách hàng nằm ở `/api/customers/{customerId}`.

### Dùng HTTP method theo ý nghĩa resource

| Request | Ý nghĩa thường gặp | Kết quả điển hình |
| --- | --- | --- |
| `GET /api/orders` | Đọc collection, có thể kèm lọc và phân trang | `200 OK` cùng danh sách representation và link điều hướng |
| `POST /api/orders` | Tạo một đơn hàng trong collection | `201 Created`, header `Location` và representation của đơn mới |
| `GET /api/orders/{id}` | Đọc một đơn hàng | `200 OK` cùng representation của item |
| `PUT /api/orders/{id}` | Thay thế representation theo hợp đồng endpoint | `200 OK` hoặc `204 No Content` |
| `PATCH /api/orders/{id}` | Cập nhật một phần nếu API hỗ trợ định dạng patch đã công bố | `200 OK` hoặc `204 No Content` |
| `DELETE /api/orders/{id}` | Xóa resource nếu nghiệp vụ cho phép | `204 No Content` hoặc kết quả phù hợp với hợp đồng |

Không phải mọi resource đều cần hỗ trợ mọi method. Ví dụ, đơn hàng đã thanh toán có thể không cho phép xóa. API nên phản ánh quy tắc đó qua status code, representation và các hành động khả dụng.

## Mô hình hóa quan hệ giữa resource

Các resource thường liên kết với nhau. Một đơn hàng thuộc về khách hàng, chứa nhiều dòng hàng và có thể có một hoặc nhiều khoản thanh toán. Quan hệ này có thể được biểu diễn bằng nested resource, link hoặc dữ liệu nhúng tùy nhu cầu client.

| Cách biểu diễn | Khi phù hợp | Điểm cần cân nhắc |
| --- | --- | --- |
| Nested URI | Client cần truy cập collection trong phạm vi resource cha | Không lồng quá sâu; xác định rõ resource con có định danh độc lập hay không. |
| Link relation | Client cần khám phá resource liên quan hoặc điều hướng đến nó | Đặt tên `rel` ổn định và mô tả ý nghĩa của quan hệ. |
| Embedded representation | Client thường xuyên cần dữ liệu liên quan cùng lúc và muốn giảm số request | Chọn trường được nhúng cẩn thận; payload có thể lớn và dữ liệu có thể thay đổi độc lập. |

Ví dụ, representation đơn hàng có thể chứa dữ liệu tóm tắt của khách hàng và link `customer` trỏ đến hồ sơ đầy đủ. Cách này cho phép màn hình đơn hàng hiển thị tên khách ngay, trong khi client vẫn có thể theo link để đọc thông tin chi tiết khi cần.

### Link relation mô tả quan hệ

Một link trong Spring HATEOAS thường có URI đích và relation (`rel`). `self` là relation chuẩn thường dùng để trỏ đến chính resource hiện tại. Những quan hệ như `orders`, `customer`, `items`, `next` hoặc `cancel` cho client biết liên kết có ý nghĩa gì.

Với relation chuẩn đã được đăng ký, có thể dùng hằng số trong `IanaLinkRelations`. Với relation riêng của ứng dụng, cần thống nhất tên và tài liệu hóa ngữ nghĩa. Trong API công khai hoặc hệ sinh thái nhiều bên, URI relation giúp định danh rõ hơn và tránh va chạm tên.

Không nên để client phụ thuộc vào thứ tự các link trong JSON hoặc suy ra ý nghĩa từ URL. Client nên đọc relation và theo `href` được cung cấp. Nếu một relation không xuất hiện, client phải xử lý trường hợp hành động hoặc quan hệ đó hiện không khả dụng.

## Biểu diễn resource bằng Spring HATEOAS

Spring HATEOAS cung cấp các lớp mô hình để gắn dữ liệu với liên kết mà không phải tự ghép cấu trúc JSON hypermedia.

| Kiểu | Cách sử dụng |
| --- | --- |
| `RepresentationModel<T>` | Lớp cơ sở cho representation tùy chỉnh có các link. |
| `EntityModel<T>` | Bọc một DTO hoặc đối tượng đơn lẻ cùng các link. |
| `CollectionModel<T>` | Bọc collection các representation và link ở cấp collection. |
| `PagedModel<T>` | Biểu diễn kết quả phân trang, bao gồm metadata trang và link điều hướng. |
| `Link` | Mô tả URI đích và relation. |
| `RepresentationModelAssembler<S, D>` | Chuyển đối tượng nguồn thành representation model, gom logic ánh xạ và link. |

### Dùng EntityModel cho resource đơn

Giả sử service trả về DTO thay vì JPA entity:

```java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderView(
    UUID id,
    String status,
    BigDecimal total,
    UUID customerId
) {
}
```

Controller có thể bọc DTO bằng `EntityModel` và thêm các liên kết đến chính đơn hàng, collection đơn hàng và khách hàng:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        List<EntityModel<OrderView>> items = orders.findAll().stream()
            .map(this::toModel)
            .toList();

        return CollectionModel.of(items,
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        return toModel(orders.get(id));
    }

    @PostMapping("/{id}/cancellation")
    EntityModel<OrderView> cancel(@PathVariable UUID id) {
        return toModel(orders.cancel(id));
    }

    private EntityModel<OrderView> toModel(OrderView order) {
        UUID id = order.id();
        Link self = linkTo(methodOn(OrderController.class).one(id)).withSelfRel();
        Link collection = linkTo(methodOn(OrderController.class).all()).withRel("orders");
        Link customer = linkTo(methodOn(CustomerController.class).one(order.customerId()))
            .withRel("customer");

        if ("PENDING".equals(order.status())) {
            self = self.andAffordance(
                afford(methodOn(OrderController.class).cancel(id)));

            return EntityModel.of(order, self, collection, customer,
                linkTo(methodOn(OrderController.class).cancel(id)).withRel("cancel"));
        }

        return EntityModel.of(order, self, collection, customer);
    }
}
```

Đoạn code giả định `OrderService` có các phương thức `get`, `findAll` và `cancel`, còn `CustomerController.one(...)` trả về hồ sơ khách hàng. `methodOn(...)` giúp tham chiếu mapping của controller khi tạo link. Việc tạo link không gọi phương thức controller thật để thực hiện nghiệp vụ.

### Dùng CollectionModel cho collection

Một collection cần có representation ở cấp collection, kể cả khi không có phần tử. `CollectionModel` giúp thêm link `self` và các link điều hướng hoặc chức năng chung:

```java
@GetMapping
CollectionModel<EntityModel<OrderView>> all() {
    List<EntityModel<OrderView>> items = orders.findAll().stream()
        .map(this::toModel)
        .toList();

    return CollectionModel.of(items,
        linkTo(methodOn(OrderController.class).all()).withSelfRel());
}
```

Trong ví dụ này, `toModel` là phương thức ánh xạ một `OrderView` thành `EntityModel<OrderView>`. Khi collection lớn, nên hỗ trợ phân trang và cung cấp liên kết `first`, `prev`, `self`, `next`, `last` phù hợp với trang hiện tại. Không nên trả toàn bộ collection không giới hạn.

### Tách mapping sang RepresentationModelAssembler

Khi logic tạo link được dùng ở nhiều endpoint, có thể đưa nó vào assembler:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.stereotype.Component;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<OrderView, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(OrderView order) {
        return EntityModel.of(order,
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel(),
            linkTo(methodOn(OrderController.class).all()).withRel("orders"));
    }
}
```

Controller nhận assembler qua constructor và gọi `toModel(...)` hoặc `toCollectionModel(...)`. Nhờ đó, quy tắc biểu diễn resource được tổ chức tập trung và dễ kiểm thử. Với resource có trạng thái khác nhau, assembler cũng có thể bổ sung link theo trạng thái nghiệp vụ, miễn là endpoint vẫn tự kiểm tra quyền và điều kiện khi nhận request.

## Thiết kế hành động như một phần của resource

Resource thường có trạng thái và các chuyển đổi hợp lệ. Ví dụ, đơn hàng có thể đi qua các trạng thái `PENDING`, `CONFIRMED`, `SHIPPED`, `DELIVERED` hoặc `CANCELLED`. Không phải mọi chuyển đổi đều hợp lệ ở mọi thời điểm.

API có thể biểu diễn các hành động khả dụng bằng link và affordance:

- Đơn hàng `PENDING` có thể cung cấp link relation `cancel`.
- Đơn hàng `CONFIRMED` có thể cung cấp link relation `ship` cho người dùng có quyền tương ứng.
- Đơn hàng `DELIVERED` có thể cung cấp link `returns` nếu chính sách đổi trả cho phép.

Ví dụ gắn affordance hủy vào link `self` và công bố link `cancel` riêng:

```java
private EntityModel<OrderView> toModel(OrderView order) {
    UUID id = order.id();
    Link self = linkTo(methodOn(OrderController.class).one(id)).withSelfRel();
    Link orders = linkTo(methodOn(OrderController.class).all()).withRel("orders");

    if ("PENDING".equals(order.status())) {
        self = self.andAffordance(
            afford(methodOn(OrderController.class).cancel(id)));

        return EntityModel.of(order, self, orders,
            linkTo(methodOn(OrderController.class).cancel(id)).withRel("cancel"));
    }

    return EntityModel.of(order, self, orders);
}
```

Affordance cho biết cách tương tác mà controller công bố, chẳng hạn HTTP method và thông tin đầu vào. Khi sử dụng media type phù hợp như HAL-FORMS, metadata affordance có thể được biểu diễn thành template để client biết cách gửi request. HAL cơ bản chủ yếu biểu diễn liên kết trong `_links`; client không nên suy ra HTTP method và request body chỉ từ một `href`.

Việc không phát link `cancel` giúp client hiểu hành động hiện không được cung cấp. Đây không phải cơ chế phân quyền. Người gọi có thể gửi request trực tiếp đến endpoint, do đó server vẫn phải kiểm tra vai trò, quyền sở hữu resource và trạng thái hiện tại trước khi thực hiện chuyển đổi.

## Ví dụ representation HAL

Một đơn hàng có thể được trả về dưới dạng HAL như sau:

```json
{
  "id": "ord-1042",
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/ord-1042"
    },
    "orders": {
      "href": "https://api.example.com/api/orders"
    },
    "customer": {
      "href": "https://api.example.com/api/customers/cus-73"
    },
    "cancel": {
      "href": "https://api.example.com/api/orders/ord-1042/cancellation"
    }
  }
}
```

Client đọc dữ liệu và các relation để khám phá resource liên quan hoặc hành động. Nếu API thay đổi path nội bộ nhưng vẫn giữ ngữ nghĩa relation, client có thể tiếp tục theo link mới do server cung cấp. Client vẫn phải hiểu cấu trúc dữ liệu và các relation mà nó sử dụng; hypermedia không loại bỏ nhu cầu về hợp đồng API.

## Tiến hóa thiết kế resource

Một API thường sống lâu hơn một phiên bản ứng dụng client. Thiết kế resource nên cho phép thay đổi cấu trúc bên trong mà vẫn giữ các hợp đồng bên ngoài có ý nghĩa.

1. **Giữ định danh và relation ổn định:** không thay đổi ý nghĩa của `self`, `orders`, `customer` hoặc relation nghiệp vụ mà không có kế hoạch tương thích.
2. **Thêm trường theo hướng tương thích:** client cũ nên bỏ qua trường chưa biết; tránh đổi kiểu hoặc ý nghĩa của trường hiện có mà không quản lý phiên bản.
3. **Ưu tiên link do server cung cấp:** client theo `href` thay vì tự nối path hoặc đoán cấu trúc URI của resource liên quan.
4. **Tách representation khỏi schema lưu trữ:** đổi bảng, tách aggregate hoặc chuyển sang service khác không nhất thiết phải làm thay đổi DTO và relation công khai.
5. **Công bố hành động theo trạng thái và quyền:** client xử lý được trường hợp link không xuất hiện; server vẫn kiểm tra lại điều kiện khi request đến.
6. **Quản lý collection có quy mô:** phân trang, lọc và sắp xếp cần có quy tắc ổn định; cung cấp link điều hướng để client không phải tự tính URL trang tiếp theo.
7. **Kiểm thử quan hệ và hành vi:** xác nhận link `self`, link liên quan, action link, affordance, media type và các trường hợp resource không tồn tại hoặc không đủ quyền.

Không phải mọi thay đổi đều có thể tương thích ngược. Đổi ý nghĩa của resource, relation hoặc quy tắc nghiệp vụ có thể buộc client cập nhật. Khi thay đổi lớn, cần có kế hoạch phiên bản hoặc thời gian chuyển tiếp phù hợp.

## Lỗi thường gặp khi thiết kế resource

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Xem mỗi bảng là một resource | API phản chiếu schema và để lộ chi tiết lưu trữ. | Mô hình hóa theo khái niệm và hành vi nghiệp vụ mà client cần. |
| Dùng động từ cho mọi URI | Endpoint trở thành danh sách RPC và khó áp dụng ngữ nghĩa HTTP nhất quán. | Dùng danh từ cho resource; dùng method và affordance để thể hiện thao tác. |
| Lồng URI quá sâu | Đường dẫn dài, lặp ID và phụ thuộc cấu trúc cha-con cứng nhắc. | Dùng link relation cho quan hệ có thể điều hướng độc lập. |
| Trả JPA entity trực tiếp | Rò rỉ dữ liệu và gắn hợp đồng API với schema. | Chọn DTO/representation riêng rồi bọc bằng Spring HATEOAS model. |
| Chỉ trả `self` link | Client vẫn phải tự biết các bước nghiệp vụ tiếp theo. | Bổ sung relation có ý nghĩa và hành động khả dụng. |
| Coi action link là bảo mật | Người dùng có thể gọi endpoint trực tiếp dù link không xuất hiện. | Kiểm tra quyền và trạng thái tại server cho mọi request. |
| Trả collection không giới hạn | Payload lớn, tốn tài nguyên và khó điều hướng. | Dùng phân trang, lọc và link điều hướng. |

## Ghi nhớ

- Resource là khái niệm có thể định danh và truy cập qua URI; nó không đồng nghĩa với một bảng hoặc JPA entity.
- Representation là cách mô tả resource được trao đổi; một resource có thể có nhiều representation theo nhu cầu và quyền truy cập.
- Thiết kế URI nhất quán cho collection và item, giữ định danh ổn định, dùng query parameter cho lọc và phân trang.
- Quan hệ giữa resource có thể được biểu diễn bằng nested URI, link relation hoặc embedded data.
- Spring HATEOAS cung cấp `EntityModel`, `CollectionModel`, `PagedModel`, `RepresentationModel` và assembler để xây representation cùng hypermedia.
- Link và affordance giúp client khám phá quan hệ, hành động; server vẫn phải thực thi kiểm tra quyền và quy tắc nghiệp vụ.
- Thiết kế resource tốt tách hợp đồng công khai khỏi cấu trúc lưu trữ và hỗ trợ API tiến hóa có kiểm soát.

## Tài liệu tham khảo

- [Roy Fielding – Architectural Styles and the Design of Network-based Software Architectures](https://www.ics.uci.edu/~fielding/pubs/dissertation/top.htm)
- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – EntityModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)
- [Spring HATEOAS API – RepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [HAL – Hypertext Application Language](https://stateless.group/hal_specification.html)
