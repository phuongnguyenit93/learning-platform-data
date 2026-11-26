# Checklist thiết kế link

Trong Spring HATEOAS, link là một phần của hợp đồng API. Nó cho client biết tài nguyên hiện tại liên quan tới tài nguyên nào, có thể tiếp tục điều hướng tới đâu và trong một số định dạng có thể thực hiện thao tác nào. Thiết kế link tốt giúp client khám phá API mà không phải tự ghép URI hoặc sao chép quy tắc định tuyến của server.

Một response có nhiều link chưa chắc đã tốt. Link dư thừa làm representation nặng, relation khó hiểu và client phải lọc nhiều lựa chọn. Ngược lại, thiếu link quan trọng khiến client phải hard-code URI hoặc gọi endpoint theo phỏng đoán. Checklist trong bài này giúp đánh giá link theo workflow, semantics, trạng thái, bảo mật và khả năng tiến hóa của API.

## Mô hình tư duy: link mô tả quan hệ

Một link có hai thành phần cốt lõi:

- `href`: URI hoặc URI template của đích.
- `rel`: link relation mô tả quan hệ giữa representation hiện tại và đích.

Ví dụ một đơn hàng có thể liên kết tới chính nó, khách hàng và thao tác hủy:

```json
{
  "id": "ORD-1001",
  "status": "OPEN",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/ORD-1001"
    },
    "customer": {
      "href": "https://api.example.com/customers/C-42"
    },
    "cancel": {
      "href": "https://api.example.com/orders/ORD-1001/cancellation"
    }
  }
}
```

`self` nhận diện resource hiện tại; `customer` biểu diễn quan hệ tới khách hàng; `cancel` chỉ ra capability mà server đang công bố. Client hiểu ý nghĩa của relation rồi theo `href` được cung cấp. Client không cần biết server đặt controller ở package nào hoặc URI được tạo từ quy tắc đặt tên nào.

Các tên ngắn `customer` và `cancel` trong JSON trên là cách viết minh họa dễ đọc. Khi dùng custom relation trong HAL, hãy công bố URI relation đầy đủ hoặc khai báo CURIE mapping để tên rút gọn có thể được mở rộng theo contract.

Trong Spring HATEOAS, `Link` biểu diễn liên kết và `RepresentationModel` giữ tập link. `EntityModel`, `CollectionModel` và `PagedModel` cung cấp các dạng representation phổ biến. Khi serialize theo HAL, link được đưa vào `_links`; khi dùng HAL-FORMS, affordance có thể được biểu diễn thành `_templates`.

## Checklist 1: xác định nhu cầu điều hướng trước khi tạo link

Trước khi viết `linkTo(...)`, hãy xác định client cần giải quyết workflow nào. Một link nên giúp client thực hiện ít nhất một trong các việc sau:

- Nhận diện hoặc quay lại resource hiện tại.
- Điều hướng tới một resource liên quan có vòng đời hoặc ngữ nghĩa độc lập.
- Đi tới collection, trang kế tiếp, trang trước hoặc kết quả tìm kiếm.
- Thực hiện một capability hợp lệ trong trạng thái hiện tại.
- Khám phá một form hoặc input cần thiết để thực hiện capability.
- Mở tài liệu trợ giúp hoặc profile giải thích contract.

Không tạo link chỉ vì controller có method tương ứng. Cũng không tạo một URI riêng cho từng field đơn giản như `status`, `createdAt` hoặc `total` nếu chúng chỉ là dữ liệu của resource hiện tại.

| Câu hỏi khi thiết kế | Dấu hiệu thiết kế tốt |
|---|---|
| Client có cần tải đích riêng không? | Link tới resource có ý nghĩa và quyền truy cập riêng |
| Client có cần dữ liệu ngay trong response không? | Embed phần nhỏ, thường xuyên dùng; link phần tải riêng |
| Đây là quan hệ hay hành động? | Relation mô tả đúng ngữ nghĩa; action có affordance nếu cần input/method |
| Link có cần xuất hiện trên mọi resource không? | Chỉ xuất hiện ở representation có liên quan |
| Client có thể theo link mà không biết cấu trúc URI không? | `href` do server tạo và client không tự ghép lại |

## Checklist 2: chọn relation rõ ràng và ổn định

Relation là phần ngữ nghĩa của hợp đồng. Một relation nên diễn tả mối quan hệ, không nên phản chiếu tên method Java, tên controller, tên bảng database hoặc tên route nội bộ.

### Ưu tiên relation chuẩn khi đúng semantics

Spring HATEOAS có `IanaLinkRelations` cho các relation phổ biến. Ví dụ:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of(
        "https://api.example.com/orders/ORD-1001",
        IanaLinkRelations.SELF
);

Link next = Link.of(
        "https://api.example.com/orders?page=2",
        IanaLinkRelations.NEXT
);
```

Dùng relation chuẩn như `self`, `next`, `prev`, `first`, `last`, `collection`, `item`, `search` hoặc `help` khi ngữ nghĩa của link thực sự tương ứng. Không chọn relation chỉ vì tên nghe gần giống.

### Định nghĩa custom relation khi domain cần ngữ nghĩa riêng

Nếu không có relation chuẩn phù hợp, dùng URI relation do API sở hữu và tài liệu hóa:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link cancel = Link.of(
        "https://api.example.com/orders/ORD-1001/cancellation",
        LinkRelation.of("https://api.example.com/rels/cancel-order")
);
```

URI relation định danh ngữ nghĩa `cancel-order`. URI này nên ổn định qua các lần refactor route hoặc đổi tên method. Tài liệu tại URI có thể mô tả khi nào relation xuất hiện, client dùng nó ra sao và request cần dữ liệu gì.

### Tránh relation alias

Không tạo nhiều relation đồng nghĩa cùng trỏ tới một URI:

```json
{
  "_links": {
    "cancel": { "href": "/orders/ORD-1001/cancellation" },
    "cancelOrder": { "href": "/orders/ORD-1001/cancellation" },
    "remove": { "href": "/orders/ORD-1001/cancellation" }
  }
}
```

Client sẽ không biết relation nào là contract chính. Mỗi alias còn trở thành cam kết tương thích cần duy trì. Chọn một relation có semantics rõ ràng; nếu cần tên ngắn cho custom relation, có thể dùng CURIE và công bố mapping.

### Checklist relation

- [ ] Relation diễn tả ý nghĩa, không phải tên implementation.
- [ ] Đã kiểm tra relation chuẩn trước khi tạo custom relation.
- [ ] Custom relation có URI ổn định và được tài liệu hóa.
- [ ] Không có alias trùng nghĩa chỉ để hỗ trợ nhiều cách đặt tên.
- [ ] Relation chỉ được tái sử dụng khi semantics thực sự giống nhau.
- [ ] Client có thể bỏ qua relation chưa biết mà không làm hỏng workflow chung.

## Checklist 3: tạo href từ mapping, không tự ghép URI

Hard-code URI trong assembler dễ tạo lỗi khi đổi context path, API prefix, controller mapping hoặc triển khai sau reverse proxy. Với Spring MVC, dùng `WebMvcLinkBuilder` để tạo link theo mapping controller:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(methodOn(OrderController.class).one(order.id()))
        .withSelfRel();
```

`methodOn(...)` tạo proxy invocation để Spring HATEOAS đọc mapping method; method controller không được thực thi để lấy dữ liệu. `linkTo(...)` dùng mapping đã khai báo để tạo URI.

Với WebFlux, dùng link builder tương ứng của Spring HATEOAS WebFlux. Tránh trộn builder MVC vào ứng dụng reactive.

### Kiểm tra host và reverse proxy

Trong môi trường production, ứng dụng có thể chạy sau ingress, load balancer hoặc reverse proxy. Link tuyệt đối cần phản ánh public scheme, host, port và context path mà client truy cập. Chỉ tin forwarded headers từ proxy được kiểm soát; không để client tùy ý giả mạo host public bằng header không được xác thực.

Checklist href:

- [ ] Link được tạo từ controller mapping hoặc URI builder phù hợp.
- [ ] Không nối chuỗi URI bằng ID hoặc query string thủ công nếu có thể dùng builder.
- [ ] Không để lộ hostname nội bộ, port container hoặc context path không công khai.
- [ ] Reverse proxy/forwarded header được cấu hình theo trust boundary.
- [ ] Path variable và query parameter được encode đúng.
- [ ] Link không chứa token, password hoặc dữ liệu nhạy cảm trong query string.
- [ ] `self` trỏ tới representation/resource hiện tại theo contract.

## Checklist 4: đặt link ở đúng cấp representation

Link có thể thuộc về resource đơn, item trong collection hoặc collection tổng thể. Đặt link đúng cấp giúp tránh lặp dữ liệu và giúp client hiểu phạm vi quan hệ.

| Cấp | Link thường phù hợp | Ví dụ |
|---|---|---|
| Resource đơn | `self`, resource liên quan, capability của resource | `customer`, `invoice`, `cancel` |
| Collection | `self`, `search`, `first`, `prev`, `next`, `last` | `/orders?page=1` |
| Item trong collection | `self`, quan hệ hoặc capability riêng của item | `self`, `approve` |
| API root | Entry point tới collection và nhóm tài nguyên | `orders`, `customers`, `profile` |

Ví dụ `CollectionModel` có link ở cấp collection:

```java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

CollectionModel<EntityModel<OrderRepresentation>> collection =
        CollectionModel.of(orderModels)
                .add(linkTo(methodOn(OrderController.class).all())
                        .withSelfRel())
                .add(linkTo(methodOn(OrderController.class).search(null, null))
                        .withRel("search"));
```

Đoạn code minh họa; `all()` và `search(...)` là mapping của controller trong ứng dụng. Không lặp link `search` hoặc link collection trên mọi item nếu item không cần quan hệ đó.

### Link phân trang

Với collection phân trang, link cần phản ánh trang có thể điều hướng:

- `first`: trang đầu.
- `prev`: trang trước nếu tồn tại.
- `self`: trang hiện tại.
- `next`: trang sau nếu tồn tại.
- `last`: trang cuối nếu biết được.

Khi tạo link trang mới, phải giữ các filter, sort và tham số truy vấn có ảnh hưởng tới kết quả. Ví dụ client đang lọc `status=OPEN` và `sort=createdAt,desc`, link `next` cần duy trì các điều kiện đó. Không tạo `prev` ở trang đầu hoặc `next` ở trang cuối.

### Nhiều link cùng relation

Một relation có thể có nhiều đích cùng ngữ nghĩa, ví dụ một giỏ hàng chứa nhiều link `item`. HAL có thể serialize nhiều link cùng relation thành array. Client cần xử lý cả trường hợp relation có một link dạng object và nhiều link dạng array; không mặc định mỗi relation luôn có đúng một đích.

Checklist cấp representation:

- [ ] Link collection/search/pagination nằm ở collection level khi phù hợp.
- [ ] Mỗi item có link riêng cần thiết cho workflow của item.
- [ ] Không lặp link dùng chung trên mọi item nếu không tăng khả năng điều hướng.
- [ ] Link phân trang giữ filter và sort.
- [ ] Không tạo link tới trang không tồn tại.
- [ ] Client có thể xử lý relation chứa một hoặc nhiều link.

## Checklist 5: chỉ công bố capability hợp lệ theo trạng thái

Action link nên phản ánh thao tác có thể thực hiện trong trạng thái hiện tại. Ví dụ:

| Trạng thái đơn hàng | `cancel` | `approve` | `ship` | `refund` |
|---|---|---|---|---|
| `OPEN` | Có thể có | Có thể có | Không | Không |
| `APPROVED` | Theo policy | Không | Không | Không |
| `PAID` | Không | Không | Có thể có | Có thể có |
| `SHIPPED` | Không | Không | Không | Theo policy |
| `CANCELLED` | Không | Không | Không | Không |

Đây là ví dụ; quy tắc thực tế phụ thuộc domain. Không công bố mọi endpoint chỉ vì controller có method tương ứng.

Spring HATEOAS hỗ trợ thêm link có điều kiện bằng `RepresentationModel.addIf(...)`:

```java
model.addIf(order.isCancellable(), () ->
        linkTo(methodOn(OrderController.class).cancel(order.id(), null))
                .withRel(LinkRelation.of(
                        "https://api.example.com/rels/cancel-order")));
```

Đoạn code cần import `org.springframework.hateoas.LinkRelation`.

Supplier chỉ được gọi khi điều kiện đúng. Nếu nhiều link phụ thuộc cùng một policy, hãy tính capability một lần để tránh gọi lặp permission check:

```java
OrderCapabilities capabilities = policy.capabilitiesFor(order, currentUser);

model.addIf(capabilities.canCancel(), () -> cancelLink(order));
model.addIf(capabilities.canApprove(), () -> approveLink(order));
model.addIf(capabilities.canRefund(), () -> refundLink(order));
```

`OrderCapabilities` là kiểu do ứng dụng định nghĩa. Nó gom kết quả policy để assembler tạo representation nhất quán.

### Link không thay thế authorization

Không công bố link `delete` cho người dùng không có quyền giúp client không hiển thị thao tác đó. Nhưng người dùng vẫn có thể gửi request trực tiếp tới URI đã biết, sử dụng response cache cũ hoặc tự tạo request.

Vì vậy:

1. Assembler chỉ công bố capability phù hợp với trạng thái và quyền hiện tại.
2. Controller/service vẫn xác thực principal, quyền, tenant, ownership và trạng thái trước khi thực hiện thao tác.
3. Endpoint không tin dữ liệu do client suy ra từ affordance.
4. Permission được tính theo đúng user context; không dùng kết quả cache chung giữa nhiều người dùng.

Checklist state/security:

- [ ] Link hành động chỉ xuất hiện khi state cho phép.
- [ ] Policy và endpoint dùng chung quy tắc nghiệp vụ.
- [ ] Authorization được kiểm tra lại khi nhận request.
- [ ] Không coi việc ẩn link là bảo vệ dữ liệu hoặc endpoint.
- [ ] Link không tiết lộ thao tác quản trị hay tài nguyên nội bộ.

## Checklist 6: dùng affordance khi client cần mô tả thao tác

Một link đơn thuần cung cấp `href` và `rel`. Nếu client cần biết HTTP method, input, content type hoặc form property, hãy mô tả affordance.

Ví dụ gắn affordance vào link `self`:

```java
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(methodOn(OrderController.class).one(order.id()))
        .withSelfRel();

if (order.isCancellable()) {
    self = self.andAffordance(afford(
            methodOn(OrderController.class).cancel(order.id(), null)
    ));
}
```

Với HAL-FORMS, affordance có thể được serialize thành `_templates` chứa method, target, content type và property. Client có thể đọc template để xây form hoặc tạo request mà không phải tự đoán payload.

Checklist affordance:

- [ ] Controller method tồn tại và mapping đúng HTTP method.
- [ ] `@RequestBody`, `consumes` và DTO phản ánh input thật.
- [ ] Validation annotation mô tả các ràng buộc phù hợp.
- [ ] Affordance chỉ xuất hiện khi thao tác hợp lệ.
- [ ] Template name và custom relation ổn định theo contract.
- [ ] Client vẫn phải xử lý validation/error response khi gửi request.
- [ ] HAL và HAL-FORMS được phân biệt bằng đúng media type.

## Checklist 7: chọn embed, link và URI template có chủ đích

`_embedded` và `_links` giải quyết hai nhu cầu khác nhau:

- Embed dữ liệu khi client thường xuyên cần nó cùng representation hiện tại và payload vẫn hợp lý.
- Dùng link khi resource liên quan có thể được tải độc lập, lớn, có vòng đời riêng hoặc chỉ một số client cần.
- Dùng URI template khi client cần khám phá tham số tìm kiếm/lọc có hỗ trợ.

Không embed toàn bộ object graph rồi đồng thời tạo link lặp tới cùng dữ liệu nếu không có use case. Cũng không tạo link riêng cho mọi field chỉ để phản chiếu cấu trúc entity.

URI template nên chứa các biến công khai, có semantics ổn định và thực sự được endpoint hỗ trợ:

```json
{
  "_links": {
    "search": {
      "href": "/api/orders{?status,from,to,page,size,sort}",
      "templated": true
    }
  }
}
```

Không đưa tham số nội bộ như `debug`, `internalFlag` hoặc biến chỉ dùng trong implementation vào template công khai. Khi số tham số quá lớn, hãy cân nhắc tách các use case tìm kiếm khác nhau thành relation riêng.

## Checklist 8: giữ representation và link tương thích khi API tiến hóa

Khi thay đổi API, hãy xem cả payload lẫn link contract:

- Thêm một relation mới thường là thay đổi có thể tương thích nếu client bỏ qua relation chưa biết.
- Đổi semantics của relation có thể phá vỡ client dù `href` không đổi.
- Đổi `href` có thể chấp nhận được nếu client luôn theo link server công bố và workflow vẫn đúng.
- Đổi media type hoặc profile cần được công bố rõ.
- Link trong representation v1 nên tiếp tục dẫn tới tài nguyên v1 nếu client cần giữ hợp đồng v1.
- Custom relation URI nên ổn định qua refactor route.

Nếu dùng URI versioning, API root có thể công bố collection của các version. Dùng `version-history`, `latest-version`, `predecessor-version` hoặc `successor-version` đúng semantics khi cần biểu diễn quan hệ giữa các version resource.

## Checklist 9: cân nhắc cache cho link động

Representation HATEOAS có thể thay đổi khi trạng thái đơn hàng, quyền người dùng, embedded data hoặc mapping thay đổi. Vì vậy, cache freshness và validator phải phản ánh cả links/capabilities, không chỉ field nghiệp vụ.

- Response công khai, giống nhau giữa người dùng có thể dùng `public` và `max-age` phù hợp.
- Response cá nhân hóa thường cần `private`; dữ liệu không nên được lưu có thể cần `no-store`.
- `no-cache` cho phép lưu nhưng yêu cầu revalidate trước khi dùng lại.
- ETag phải thay đổi khi relation, `href`, affordance hoặc embedded resource làm representation thay đổi.
- Nếu representation phụ thuộc `Accept`, `Accept-Language` hoặc API version header, dùng `Vary` phù hợp.
- Endpoint thao tác vẫn kiểm tra state và authorization; link trong cache cũ không cấp quyền thực hiện hành động.

Không đặt TTL dài chỉ vì response ít thay đổi về field. Một link `cancel` có thể trở nên không hợp lệ ngay khi trạng thái đơn hàng chuyển từ `OPEN` sang `PAID`.

## Checklist 10: biểu diễn lỗi mà không nhầm với HAL

Response lỗi có thể dùng Problem Details (`application/problem+json`) với `type`, `title`, `status`, `detail` và `instance`. Đây là một error representation riêng, không tự động là HAL và không tự có `_links`.

Nếu client cần tài liệu trợ giúp hoặc tài nguyên liên quan, có thể công bố link qua HTTP `Link` header, ví dụ relation `help`, hoặc dùng extension member đã được tài liệu hóa. Không gắn nhãn `application/hal+json` cho một body Problem Details không tuân theo HAL.

Checklist error link:

- [ ] HTTP status phản ánh đúng kết quả request.
- [ ] Problem Details dùng `application/problem+json`.
- [ ] `type` định danh loại lỗi ổn định; `instance` định danh occurrence nếu cần.
- [ ] Link trợ giúp dùng relation phù hợp và không lộ thông tin nội bộ.
- [ ] Client không phải phân loại lỗi bằng cách so sánh chuỗi `detail`.

## Checklist 11: kiểm soát số lượng link và payload

Không có ngưỡng link cố định cho mọi API. Hãy xem số lượng link theo loại resource, số item trong collection, payload size và workflow client.

| Dấu hiệu | Rủi ro | Cách xử lý |
|---|---|---|
| Mỗi item lặp link collection/search giống nhau | Payload tăng theo số item | Đặt link dùng chung ở collection level nếu phù hợp |
| Mọi endpoint đều được công bố trên mọi resource | Client phải lọc action không hợp lệ | Dùng capability theo state/policy |
| Nhiều relation alias cùng URI | Contract khó hiểu | Chọn một relation chính |
| Embed object graph quá sâu | Response lớn và tốn serialize | Embed phần cần ngay, link phần tải riêng |
| URI template có quá nhiều biến | Client khó biết biến nào cần dùng | Giới hạn theo use case |
| Nhiều affordance ít dùng | Tăng metadata và complexity | Chỉ mô tả thao tác client thực sự cần |

Khi điều tra performance, đo số link, số embedded item, payload bytes và thời gian serialize. Không loại bỏ link có giá trị nghiệp vụ chỉ để giảm vài byte; ưu tiên xóa lặp, link chết và link không có semantics.

## Checklist 12: kiểm thử link contract

Test nên kiểm tra cả link cần xuất hiện lẫn link cần vắng mặt. Ví dụ MockMvc:

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/ORD-1001")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.customer.href")
            .value(containsString("/customers/")))
    .andExpect(jsonPath("$._links.cancel.href").exists());
```

Với đơn hàng đã thanh toán, kiểm tra action không còn:

```java
mockMvc.perform(get("/api/orders/ORD-1002")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.cancel").doesNotExist());
```

Với HAL-FORMS, kiểm tra `_templates` có đúng method, target và property. Với collection, kiểm tra `next`/`prev`, query parameter được giữ và nhiều link cùng relation được biểu diễn đúng.

### Ma trận kiểm thử đề xuất

| Nhóm | Điều cần kiểm tra |
|---|---|
| Resource detail | `self`, relation tới resource liên quan, href đúng |
| Collection | Link collection, search và pagination |
| State | Action link chỉ xuất hiện ở trạng thái hợp lệ |
| Authorization | Principal khác nhau nhận capability phù hợp; endpoint vẫn chặn request trái quyền |
| Relation | Tên relation ổn định, không alias hoặc trùng nghĩa |
| URI template | `templated=true`, biến công khai và query được encode |
| HAL-FORMS | Method, target, content type và properties đúng |
| Versioning | Link trong version không vô tình chuyển client sang contract khác |
| Caching | ETag/Vary và cache policy phản ánh biến thể representation |
| Error | Status, media type và help link đúng contract |

## Checklist review trước khi phát hành

Sử dụng danh sách sau trong pull request hoặc buổi review API:

### Semantics và discoverability

- [ ] API có entry point hoặc URI khởi đầu rõ ràng.
- [ ] `self` được tạo đúng cho resource hiện tại.
- [ ] Mỗi link có relation diễn tả đúng quan hệ/capability.
- [ ] Relation chuẩn được ưu tiên khi đúng nghĩa; custom relation có tài liệu.
- [ ] Client có thể đi theo link mà không tự dựng URI.
- [ ] Link collection, item và pagination nằm đúng cấp.

### State, security và input

- [ ] Action link phù hợp với trạng thái resource.
- [ ] Link không thay thế authorization tại endpoint.
- [ ] Affordance mô tả đúng method, target và input.
- [ ] DTO và validation phản ánh contract request.
- [ ] Không có URI hoặc property nội bộ bị công bố ngoài ý muốn.

### Compatibility và vận hành

- [ ] Relation và semantics được giữ ổn định qua refactor.
- [ ] Versioned links dẫn tới đúng version.
- [ ] Cache policy và validator phản ánh thay đổi link/affordance.
- [ ] Media type thành công và lỗi được công bố chính xác.
- [ ] Số link và payload phù hợp với workflow và hiệu năng.

### Kiểm thử

- [ ] Test xác nhận link bắt buộc xuất hiện.
- [ ] Test xác nhận link có điều kiện vắng khi không hợp lệ.
- [ ] Test kiểm tra href, relation và URI template.
- [ ] Test kiểm tra HAL/HAL-FORMS media type.
- [ ] Test kiểm tra request trực tiếp vẫn bị từ chối khi sai state/quyền.
- [ ] Test collection bao phủ pagination và repeated relation nếu có.

## Ví dụ assembler áp dụng checklist

Đoạn assembler dưới đây kết hợp link `self`, link tới customer và affordance hủy đơn. Các link được tạo từ controller mapping; action chỉ được thêm khi policy cho phép.

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    private final OrderPolicy policy;

    public OrderModelAssembler(OrderPolicy policy) {
        this.policy = policy;
    }

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        var id = order.getId();

        Link self = linkTo(methodOn(OrderController.class).one(id))
                .withSelfRel();

        if (policy.canCancel(order)) {
            self = self.andAffordance(afford(
                    methodOn(OrderController.class).cancel(id, null)
            ));
        }

        EntityModel<OrderRepresentation> model = EntityModel.of(
                OrderRepresentation.from(order), self);

        model.addIf(order.getCustomerId() != null, () ->
                linkTo(methodOn(CustomerController.class)
                        .one(order.getCustomerId()))
                        .withRel(LinkRelation.of(
                                "https://api.example.com/rels/customer")));

        return model;
    }
}
```

`Order`, `OrderRepresentation`, `OrderPolicy`, `OrderController` và `CustomerController` là kiểu của ứng dụng minh họa. Controller `cancel` phải khai báo đúng request body và HTTP method để affordance có metadata đầu vào. Nếu custom relation `customer` không thuộc vocabulary chuẩn của API, hãy định nghĩa URI relation và tài liệu tương ứng. Nếu bật HAL-FORMS, affordance được serialize theo cấu hình media type; nếu chỉ trả HAL JSON, client không nhận được form template đầy đủ.

## Kết luận

Thiết kế link tốt bắt đầu từ workflow và semantics, không bắt đầu từ danh sách endpoint. Mỗi relation cần có ý nghĩa ổn định; mỗi `href` cần được tạo từ mapping phù hợp; link cần nằm đúng cấp resource/collection và chỉ công bố capability hợp lệ trong trạng thái hiện tại. Affordance bổ sung method và input khi client cần mô tả thao tác; authorization vẫn phải được kiểm tra tại endpoint. Khi tính cả versioning, cache, error representation, payload size và contract tests, checklist này giúp API Spring HATEOAS dễ khám phá, nhất quán và có thể tiến hóa.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Links](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.links): cấu trúc link, relation và URI template.
- [Spring HATEOAS Reference – Representation Models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models): `RepresentationModel`, `EntityModel`, `CollectionModel` và `PagedModel`.
- [Spring HATEOAS Reference – Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances): mô tả thao tác qua controller method.
- [Spring HATEOAS – RepresentationModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/RepresentationModel.html): `addIf`, `addAllIf` và quản lý link.
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html): mô hình Web Linking và relation type.
- [IANA Link Relations Registry](https://www.iana.org/assignments/link-relations/link-relations.xhtml): danh sách relation chuẩn đã đăng ký.
- [RFC 9111 – HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): cache freshness, validation và `Vary`.
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html): định dạng lỗi HTTP và extension members.
