# Link là gì?

Trong REST API có hypermedia, một tài nguyên không chỉ trả về dữ liệu mà còn có thể chỉ ra những tài nguyên liên quan và các đường đi tiếp theo. Spring HATEOAS biểu diễn những mối quan hệ đó bằng Link. Mỗi link cung cấp một URI đích cùng relation mô tả ý nghĩa của mối quan hệ giữa tài nguyên hiện tại và tài nguyên đích.

Ví dụ, response của một đơn hàng có thể chứa link self để trỏ đến chính đơn hàng, link customer để dẫn đến khách hàng, link items để xem các dòng hàng và link cancel khi hành động hủy đang khả dụng. Client đọc relation để hiểu link có ý nghĩa gì rồi theo href để điều hướng.

Bài học này giới thiệu khái niệm Link, cấu trúc href và relation, các metadata thường gặp, relation chuẩn và relation tùy chỉnh, cách tạo Link bằng Spring HATEOAS, cách gắn link vào representation model và những giới hạn cần hiểu khi thiết kế hợp đồng hypermedia.

## 1. Link trong hypermedia là gì?

Link là một mối quan hệ được công bố từ một tài nguyên đến một đích. Trong một biểu diễn hypermedia, link giúp client khám phá API từ response hiện tại thay vì phải biết trước mọi URL.

Một link cơ bản có hai thành phần:

- **href**: URI của tài nguyên hoặc đích mà client có thể truy cập.
- **rel (relation)**: tên quan hệ mô tả ý nghĩa của link đối với tài nguyên hiện tại.

Ví dụ, tài nguyên đơn hàng có link:

~~~json
{
  "id": "ORD-42",
  "status": "PROCESSING",
  "_links": {
    "self": {
      "href": "/orders/ORD-42"
    },
    "customer": {
      "href": "/customers/CUS-7"
    },
    "items": {
      "href": "/orders/ORD-42/items"
    }
  }
}
~~~

Trong ví dụ:

- self trỏ đến chính đơn hàng ORD-42.
- customer chỉ ra tài nguyên khách hàng liên quan.
- items chỉ ra tập hợp các dòng hàng của đơn hàng.

Client không cần tự ghép chuỗi "/orders/" với mã đơn hoặc tự đoán endpoint khách hàng. Nó đọc relation và theo href mà server cung cấp.

Link không phải dữ liệu nghiệp vụ như trạng thái, tổng tiền hay tên khách hàng. Nó là thông tin điều hướng và quan hệ giữa các tài nguyên. Một response có thể chứa cả dữ liệu và link, nhưng hai phần có vai trò khác nhau.

## 2. Hai thành phần cốt lõi: href và rel

### 2.1. href xác định đích

href là URI mà client có thể sử dụng để truy cập đích của link. URI có thể là:

- Absolute URI, ví dụ https://api.example.com/orders/ORD-42.
- Relative URI, ví dụ /orders/ORD-42.
- URI template, ví dụ /orders{?status,page,size}.

Absolute URI chứa scheme và authority; relative URI được phân giải theo URI cơ sở của response hoặc ngữ cảnh client. Cả hai đều có thể xuất hiện trong API, tùy cách triển khai và cấu hình máy chủ.

Không nên mặc định mọi link luôn là URL tuyệt đối. Ứng dụng có thể sử dụng relative URI, context path hoặc reverse proxy. Client cần xử lý URI theo chuẩn và ngữ cảnh response thay vì tự nối chuỗi.

### 2.2. rel mô tả ý nghĩa của mối quan hệ

Relation cho biết link có ý nghĩa gì đối với tài nguyên đang được biểu diễn. Ví dụ:

| Relation | Ý nghĩa thường gặp |
|---|---|
| self | Tài nguyên hiện tại |
| collection | Tập hợp chứa tài nguyên |
| item | Một phần tử của tập hợp |
| next | Trang hoặc phần kết quả tiếp theo |
| prev | Trang hoặc phần kết quả trước |
| first | Trang đầu tiên |
| last | Trang cuối cùng |
| profile | Tài liệu mô tả profile của tài nguyên |
| describedby | Tài liệu mô tả tài nguyên hoặc đích liên quan |
| customer | Quan hệ nghiệp vụ do API định nghĩa |
| cancel | Hành động hủy được API công bố |

Các relation chuẩn được đăng ký trong IANA Link Relation Types. API cũng có thể sử dụng relation mở rộng theo miền nghiệp vụ. Relation tùy chỉnh cần có tên ổn định, rõ nghĩa và được ghi nhận trong hợp đồng API để các client có thể hiểu nhất quán.

Relation không phải tên method Java hoặc tên endpoint. Ví dụ, relation customer có thể dẫn đến /customers/CUS-7 hôm nay và một URI khác trong phiên bản triển khai tương lai. Client dựa vào ý nghĩa customer để tìm link, không dựa vào cấu trúc đường dẫn.

## 3. Relation chuẩn và relation tùy chỉnh

Spring HATEOAS cung cấp IanaLinkRelations cho các relation chuẩn. Dùng hằng số thay vì viết chuỗi giúp tránh lỗi chính tả và làm rõ ý nghĩa:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of(
    "/orders/ORD-42",
    IanaLinkRelations.SELF
);

Link next = Link.of(
    "/orders?page=2",
    IanaLinkRelations.NEXT
);
~~~

Một số relation chuẩn thường dùng gồm SELF, COLLECTION, ITEM, NEXT, PREV, FIRST, LAST, PROFILE và DESCRIBEDBY. Danh sách hằng số có thể phụ thuộc phiên bản Spring HATEOAS; hãy kiểm tra API của phiên bản mà dự án đang dùng.

Khi API cần relation riêng theo nghiệp vụ, có thể dùng tên tùy chỉnh:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link customer = Link.of(
    "/customers/CUS-7",
    LinkRelation.of("customer")
);

Link cancel = Link.of(
    "/orders/ORD-42/cancellation",
    LinkRelation.of("cancel")
);
~~~

Relation tùy chỉnh phải thể hiện một ý nghĩa có thể hiểu được từ góc nhìn client. Nên chọn tên theo khái niệm nghiệp vụ và giữ ổn định qua các lần thay đổi implementation.

Nếu cần relation mở rộng có khả năng định danh toàn cầu, có thể dùng URI relation theo quy ước của Web Linking. Trong HAL, CURIE có thể giúp rút gọn URI relation dài thành dạng compact relation. CURIE là cơ chế ánh xạ tên rút gọn tới URI; nó không thay thế href của link.

## 4. Các metadata thường gặp của Link

Ngoài href và rel, một link có thể mang metadata bổ sung. Tùy định dạng hypermedia, các thuộc tính này giúp client hiểu thêm về đích hoặc cách sử dụng link.

| Metadata | Ý nghĩa |
|---|---|
| title | Nhãn hoặc mô tả ngắn cho link |
| type | Media type dự kiến của tài nguyên đích |
| hreflang | Ngôn ngữ của tài nguyên đích |
| deprecation | URI mô tả thông tin về việc relation hoặc link đã bị đánh dấu deprecated |
| name | Tên phân biệt link khi có nhiều link cùng relation |
| profile | URI tham chiếu profile mô tả ngữ nghĩa của tài nguyên |
| templated | Cho biết href là URI template cần được điền biến |

Ví dụ HAL:

~~~json
{
  "_links": {
    "manual": {
      "href": "/docs/orders",
      "title": "Hướng dẫn đơn hàng",
      "type": "text/html",
      "hreflang": "vi"
    },
    "search": {
      "href": "/orders{?status,page,size}",
      "templated": true
    }
  }
}
~~~

title hữu ích cho giao diện hiển thị link. type cho client biết media type dự kiến của đích, nhưng không bảo đảm server sẽ luôn trả đúng định dạng đó. hreflang mô tả ngôn ngữ của tài nguyên liên quan. templated cho biết client cần mở rộng URI template bằng các biến phù hợp trước khi gửi request.

Metadata giúp làm rõ hợp đồng, nhưng không thay thế việc đọc response thực tế hoặc xử lý lỗi HTTP. Đích của link vẫn có thể thay đổi trạng thái hoặc không còn truy cập được khi client theo link.

## 5. Tạo Link bằng Spring HATEOAS

Spring HATEOAS cung cấp lớp org.springframework.hateoas.Link để mô hình hóa liên kết. Có thể tạo Link trực tiếp từ URI và relation:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.IanaLinkRelations;

Link self = Link.of(
    "/orders/ORD-42",
    IanaLinkRelations.SELF
);

Link customer = Link.of(
    "/customers/CUS-7",
    "customer"
);
~~~

Có thể tạo Link trước rồi thiết lập relation:

~~~java
Link cancel = Link.of("/orders/ORD-42/cancellation")
    .withRel("cancel");
~~~

Spring HATEOAS cung cấp các phương thức biến đổi Link như withRel(...), withSelfRel(), withTitle(...), withType(...), withHreflang(...), withDeprecation(...), withName(...) và withProfile(...). Các phương thức này tạo ra Link với metadata được cập nhật, vì vậy có thể dùng theo phong cách fluent.

Ví dụ:

~~~java
Link documentation = Link.of("/docs/orders")
    .withRel("describedby")
    .withTitle("Tài liệu API đơn hàng")
    .withType("text/html")
    .withHreflang("vi");
~~~

Link là value object dùng trong representation. Sau khi tạo, hãy sử dụng kết quả trả về từ các phương thức with... khi cần giữ phiên bản link đã được bổ sung metadata.

## 6. Tạo URI từ ánh xạ controller

Trong ứng dụng Spring MVC, nên dùng WebMvcLinkBuilder để tạo link từ mapping controller. Cách này giảm phụ thuộc vào chuỗi URL viết thủ công.

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
        // Trả representation đơn hàng
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderRepresentation>> all() {
        // Trả tập hợp đơn hàng
    }

    @PostMapping("/{id}/cancellation")
    public ResponseEntity<Void> cancel(@PathVariable UUID id) {
        // Thực hiện hủy đơn hàng
    }
}
~~~

Tạo link self và link orders:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel();

Link orders = linkTo(
    methodOn(OrderController.class).all()
).withRel("orders");
~~~

Tạo link cancel:

~~~java
Link cancel = linkTo(
    methodOn(OrderController.class).cancel(orderId)
).withRel("cancel");
~~~

methodOn(...) tạo lời gọi controller giả lập để Spring HATEOAS đọc metadata mapping và tham số URI. Nó không thực thi logic nghiệp vụ của handler. linkTo(...) sử dụng thông tin mapping đó để tạo URI builder; withSelfRel() hoặc withRel(...) xác định relation.

Nếu mapping đổi từ /orders/{id} sang một cấu trúc khác, link được tạo từ controller mapping có thể theo thay đổi đó mà không phải cập nhật từng chuỗi URL được viết thủ công.

Đối với Spring WebFlux, dùng WebFluxLinkBuilder và tạo link trong reactive pipeline. Không dùng WebMvcLinkBuilder trong ứng dụng WebFlux chỉ vì tên API có vẻ tương tự.

## 7. Gắn Link vào representation model

Link thường được gắn vào một lớp kế thừa RepresentationModel, chẳng hạn EntityModel hoặc model tự định nghĩa.

Ví dụ với EntityModel:

~~~java
OrderRepresentation body = new OrderRepresentation(
    order.getId(),
    order.getStatus(),
    order.getTotal()
);

EntityModel<OrderRepresentation> model = EntityModel.of(
    body,
    self,
    orders
);

if (order.canCancel()) {
    model.add(cancel);
}
~~~

EntityModel chứa nội dung OrderRepresentation và các link. Với model tự định nghĩa:

~~~java
public class OrderModel extends RepresentationModel<OrderModel> {

    private final UUID id;
    private final String status;

    public OrderModel(UUID id, String status) {
        this.id = id;
        this.status = status;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Có thể thêm link:

~~~java
OrderModel model = new OrderModel(order.getId(), order.getStatus());

model.add(self);
model.add(orders);

if (order.canCancel()) {
    model.add(cancel);
}
~~~

Các link có thể được thêm ngay khi tạo model hoặc sau đó bằng add(...). Một tài nguyên thường có một self link; có thể có nhiều link khác nhau với relation khác nhau. Khi có nhiều link cùng relation, hãy đặt name hoặc dùng cấu trúc phù hợp với media type nếu hợp đồng cần phân biệt chúng.

## 8. Link trong HAL JSON

HAL là một định dạng hypermedia được Spring HATEOAS hỗ trợ. Trong HAL JSON, các link được biểu diễn bên dưới thuộc tính _links.

Ví dụ:

~~~json
{
  "id": "ORD-42",
  "status": "PROCESSING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "/orders/ORD-42"
    },
    "orders": {
      "href": "/orders"
    },
    "customer": {
      "href": "/customers/CUS-7"
    },
    "cancel": {
      "href": "/orders/ORD-42/cancellation"
    }
  }
}
~~~

Client có thể tìm link theo relation:

- Đọc _links.self.href để xác định URI của đơn hàng.
- Đọc _links.customer.href để truy cập khách hàng.
- Đọc _links.cancel.href nếu hành động hủy được công bố.

Nếu controller công bố HAL JSON, client có thể gửi Accept: application/hal+json. Spring HATEOAS và message converter sẽ chuyển representation model thành định dạng tương ứng.

HAL cũng hỗ trợ URI template. Ví dụ search relation có thể cung cấp href dạng /orders{?status,page,size} cùng thuộc tính templated: true. Client cần mở rộng template bằng các biến truy vấn phù hợp trước khi gọi endpoint.

## 9. Link và hành động khả dụng

Một link cơ bản mô tả relation và URI đích. Nó không tự mô tả đầy đủ HTTP method, request body, schema đầu vào hoặc tất cả điều kiện để thực hiện thao tác.

Ví dụ relation cancel cho biết server công bố một đường dẫn hủy đơn. Nhưng chỉ từ href và rel, client không thể luôn suy ra chắc chắn thao tác cần POST hay PATCH hoặc cần gửi trường nào trong request body.

Nếu cần mô tả thao tác phong phú hơn, Spring HATEOAS có cơ chế affordance. Affordance bổ sung thông tin về thao tác có thể thực hiện tại một link và có thể được biểu diễn bởi media type hỗ trợ, chẳng hạn HAL-FORMS.

Dù có affordance, server vẫn phải kiểm tra lại quyền và điều kiện nghiệp vụ khi nhận request. Link chỉ phản ánh khả năng được công bố tại thời điểm response được tạo; client có thể đang giữ một response cũ.

Ví dụ, assembler chỉ thêm cancel khi trạng thái hiện tại cho phép:

~~~java
if (order.canCancel()) {
    model.add(
        linkTo(methodOn(OrderController.class).cancel(order.getId()))
            .withRel("cancel")
    );
}
~~~

Endpoint cancel vẫn cần kiểm tra lại trạng thái và quyền trước khi thay đổi đơn hàng. Việc link xuất hiện không phải là giấy phép thực thi.

## 10. Link và HTTP Link header

Cần phân biệt Link model của Spring HATEOAS với HTTP Link header.

- Spring HATEOAS Link là đối tượng Java dùng để xây dựng representation hypermedia.
- HTTP Link header là một header của thông điệp HTTP, được định nghĩa trong Web Linking, có cú pháp riêng để truyền quan hệ link ở tầng header.
- HAL JSON thường biểu diễn các link trong body dưới _links.

Cả hai cùng diễn đạt quan hệ giữa tài nguyên và đích, nhưng vị trí truyền và cách tiêu thụ khác nhau. Việc ứng dụng dùng Spring HATEOAS Link không có nghĩa response tự động phát ra HTTP Link header. Nếu hợp đồng cần header, ứng dụng phải cấu hình hoặc tạo header tương ứng.

## 11. Thiết kế relation ổn định

Relation là một phần hợp đồng công khai. Client có thể dựa vào relation để tìm đúng link ngay cả khi URI thay đổi.

Một số nguyên tắc:

1. Chọn relation theo ý nghĩa nghiệp vụ hoặc chuẩn IANA phù hợp.
2. Giữ cách viết relation ổn định giữa các response và phiên bản API.
3. Không dùng tên method Java, tên class hoặc tên bảng dữ liệu làm relation nếu chúng không phản ánh ngữ nghĩa API.
4. Không yêu cầu client tự tạo URL từ mã tài nguyên.
5. Chỉ công bố link hành động khi hành động thực sự có thể được xem xét trong ngữ cảnh hiện tại.
6. Ghi nhận relation tùy chỉnh trong tài liệu API, nhất là khi nhiều client độc lập cần hiểu relation đó.
7. Khi relation cũ cần thay thế, có kế hoạch chuyển tiếp và thông tin deprecation rõ ràng.

Ví dụ, relation orders có thể ổn định trong khi URI tập hợp thay đổi. Client chỉ cần tìm relation orders từ response hiện tại rồi theo href mới.

## 12. Kiểm thử Link

Kiểm thử hypermedia nên xác nhận cả relation và href. Với Spring MVC, MockMvc có thể kiểm tra cấu trúc HAL JSON:

~~~java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.orders.href").exists())
    .andExpect(jsonPath("$._links.customer.href").exists());
~~~

Nếu đơn hàng không thể hủy, xác nhận link cancel không xuất hiện:

~~~java
mockMvc.perform(get("/orders/{id}", deliveredOrderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.cancel").doesNotExist());
~~~

Có thể kiểm thử Link object riêng:

~~~java
Link link = Link.of("/orders/ORD-42", IanaLinkRelations.SELF);

assertThat(link.getHref()).isEqualTo("/orders/ORD-42");
assertThat(link.getRel()).isEqualTo(IanaLinkRelations.SELF);
~~~

Nên kiểm tra relation và phần URI có ý nghĩa thay vì khóa cứng host tuyệt đối trong tất cả test. Host, scheme, context path hoặc reverse proxy có thể thay đổi theo môi trường. Với link template, kiểm tra cả href và thuộc tính templated.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ cung cấp href mà không có relation có ý nghĩa | Client khó hiểu link dẫn đến loại tài nguyên hoặc quan hệ nào | Chọn relation rõ ràng |
| Dùng relation tùy chỉnh không ổn định | Client phụ thuộc vào cách đặt tên thay đổi liên tục | Xác định relation như hợp đồng API |
| Tự nối chuỗi URL ở client | Client phụ thuộc cấu trúc endpoint | Theo href server cung cấp |
| Cho rằng link cancel mô tả HTTP method | Client có thể gọi sai method hoặc thiếu request body | Dùng hợp đồng hoặc affordance phù hợp |
| Công bố link là đã cấp quyền | Request cũ hoặc giả mạo có thể được gửi | Kiểm tra lại quyền và trạng thái tại endpoint |
| Dùng WebMvcLinkBuilder cho WebFlux | Không phù hợp với request context của reactive stack | Dùng WebFluxLinkBuilder |
| Nghĩ Link object tự phát HTTP Link header | Hợp đồng header không được tạo như mong đợi | Cấu hình header riêng nếu cần |
| Không kiểm thử link tùy chọn | Response có thể công bố hành động sai trạng thái | Kiểm thử cả trường hợp link xuất hiện và vắng mặt |

## 14. Quy trình tạo Link

Khi thiết kế một representation có hypermedia, có thể đi theo trình tự:

1. Xác định tài nguyên hiện tại và các tài nguyên hoặc hành động liên quan.
2. Chọn relation chuẩn hoặc relation tùy chỉnh có ý nghĩa.
3. Tạo href từ controller mapping hoặc URI builder phù hợp.
4. Bổ sung metadata như title, type, hreflang hoặc deprecation khi hợp đồng cần.
5. Gắn link vào RepresentationModel, EntityModel hoặc CollectionModel.
6. Chỉ công bố link tùy chọn khi trạng thái và quyền hiện tại cho phép.
7. Dùng affordance nếu client cần mô tả thao tác chi tiết hơn href và relation.
8. Kiểm thử relation, href, metadata và trường hợp link không khả dụng.

Link là nền tảng điều hướng của API hypermedia. Khi relation thể hiện ngữ nghĩa rõ ràng và href được tạo từ cấu hình server, client có thể khám phá tài nguyên theo response mà không phụ thuộc vào cấu trúc URL nội bộ. Kết hợp Link với representation model và affordance giúp API công bố các quan hệ và hành động theo một hợp đồng có thể tiến hóa.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Link API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [LinkRelation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
- [IanaLinkRelations API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [Web Linking – RFC 8288](https://www.rfc-editor.org/rfc/rfc8288)
- [URI Template – RFC 6570](https://www.rfc-editor.org/rfc/rfc6570)

