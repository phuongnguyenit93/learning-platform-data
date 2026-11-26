# deprecation của link

Trong một REST API có hypermedia, cấu trúc URI và các quan hệ liên kết (*link relation*) có thể cần thay đổi theo thời gian. Một endpoint cũ có thể được thay thế bằng endpoint mới, hoặc một relation từng được công bố không còn là lựa chọn nên dùng cho client mới. Nếu xóa liên kết ngay, client đang sử dụng hợp đồng cũ có thể bị lỗi. Spring HATEOAS hỗ trợ đánh dấu một link là đã bị deprecated bằng metadata `deprecation`.

Với Spring HATEOAS, có thể gọi `Link.withDeprecation(...)` để gắn URI của tài liệu giải thích việc deprecation vào link. URI này giúp client hoặc người tích hợp tìm hiểu lý do, tác động và hướng chuyển đổi. Metadata mang tính thông báo; nó không tự vô hiệu hóa endpoint, không tự chuyển hướng request và không thay thế kế hoạch tương thích API.

## 1. Deprecation của link là gì?

Giả sử API ban đầu công bố relation `legacy-order` trỏ đến endpoint chi tiết đơn hàng cũ. Sau một thời gian, API cung cấp một endpoint mới với representation nhất quán hơn. Server có thể tiếp tục phát link cũ nhưng đánh dấu nó deprecated, đồng thời công bố link mới:

```json
{
  "id": "ORD-2048",
  "status": "PROCESSING",
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/ORD-2048"
    },
    "legacy-order": {
      "href": "https://api.example.test/v1/order-details/ORD-2048",
      "deprecation": "https://api.example.test/docs/deprecations/legacy-order"
    },
    "order": {
      "href": "https://api.example.test/orders/ORD-2048"
    }
  }
}
```

Trong ví dụ:

- `legacy-order` là relation của link cũ.
- `href` là URI mà link cũ đang trỏ đến.
- `deprecation` là URI dẫn đến tài liệu giải thích việc deprecation của link.
- `order` là relation của link mới mà client nên chuyển sang sử dụng.

`deprecation` ở đây là thuộc tính metadata của link. Nó không phải relation mà client theo để đến resource thay thế. Client cần đọc tài liệu deprecation hoặc sử dụng link thay thế được công bố riêng.

## 2. Gắn metadata bằng Spring HATEOAS

`Link` của Spring HATEOAS hỗ trợ phương thức `withDeprecation(String)` để tạo một link mới có thông tin deprecation. Các phương thức `withRel(...)`, `withTitle(...)` và `withType(...)` cũng tạo link mới với metadata tương ứng; vì vậy có thể kết hợp chúng khi xây dựng representation.

Ví dụ tạo representation đơn hàng có cả link mới và link cũ được đánh dấu:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

private static final String LEGACY_ORDER_DEPRECATION =
        "https://api.example.test/docs/deprecations/legacy-order";

EntityModel<OrderRepresentation> toModel(Order order) {
    Link currentLink = linkTo(methodOn(OrderController.class)
            .one(order.getId())).withRel("order");

    Link legacyLink = linkTo(methodOn(OrderController.class)
            .legacyDetails(order.getId()))
            .withRel("legacy-order")
            .withDeprecation(LEGACY_ORDER_DEPRECATION);

    return EntityModel.of(
            OrderRepresentation.from(order),
            linkTo(methodOn(OrderController.class)
                    .one(order.getId())).withSelfRel(),
            currentLink,
            legacyLink);
}
```

`legacyDetails(...)` là handler cũ được giả định còn tồn tại trong controller. Phương thức `one(...)` là handler mới. Ví dụ giữ link cũ để client có thời gian chuyển đổi và công bố link mới với relation `order`. Tên relation và đường dẫn cần được thống nhất trong hợp đồng API của ứng dụng.

`withDeprecation(...)` nhận URI của tài liệu giải thích việc deprecation, không nhận ngày ngừng hỗ trợ. Nếu cần công bố thời điểm ngừng cung cấp endpoint, hãy mô tả thời hạn trong tài liệu và dùng cơ chế HTTP phù hợp theo chính sách API. Không diễn giải giá trị `deprecation` thành ngày hoặc thời hạn tự động.

## 3. Ý nghĩa của URI deprecation

URI deprecation nên dẫn đến một tài liệu có thể truy cập và giải thích rõ việc thay đổi. Tài liệu đó thường nên cung cấp:

- Relation hoặc endpoint đang bị deprecated.
- Lý do thay đổi và vấn đề mà API muốn giải quyết.
- Link relation hoặc endpoint thay thế.
- Ví dụ request/response trước và sau khi chuyển đổi.
- Những thay đổi về dữ liệu, HTTP method, tham số hoặc quyền truy cập nếu có.
- Mốc thời gian dự kiến ngừng hỗ trợ, nếu đã được xác định.
- Hướng dẫn cho client cần thêm thời gian để chuyển đổi hoặc cần hỗ trợ.

Ví dụ, tài liệu tại `https://api.example.test/docs/deprecations/legacy-order` có thể giải thích rằng relation `legacy-order` sẽ được thay bằng `order`, chỉ ra URI mới, ví dụ response mới và mốc thời gian dự kiến ngừng endpoint cũ. URI này có thể trỏ đến trang HTML, tài liệu API hoặc tài nguyên mô tả deprecation mà đội phát triển duy trì.

Nên giữ URI deprecation ổn định trong suốt thời gian link cũ còn được công bố. Nếu URI đó trả về lỗi, client sẽ mất nơi tra cứu hướng chuyển đổi, làm giảm giá trị của metadata.

## 4. Phân biệt deprecation với xóa link

Đánh dấu deprecated và xóa link là hai bước khác nhau trong vòng đời API:

| Trạng thái | Cách server phản hồi | Ý nghĩa với client |
| --- | --- | --- |
| Đang được hỗ trợ | Công bố link bình thường | Client có thể sử dụng theo hợp đồng |
| Deprecated | Vẫn công bố link và thêm metadata `deprecation` | Client được thông báo nên lập kế hoạch chuyển đổi |
| Đã ngừng công bố | Link cũ không còn xuất hiện trong representation mới | Client cần sử dụng link thay thế |
| Endpoint đã ngừng hoạt động | Request đến URI cũ nhận phản hồi theo chính sách ngừng hỗ trợ | Client còn dùng endpoint cũ có thể không tiếp tục hoạt động |

Metadata `deprecation` không tự thay đổi trạng thái hoạt động của endpoint. Trong giai đoạn deprecated, server có thể tiếp tục phục vụ request cũ để client có thời gian chuyển đổi. Việc giữ endpoint trong bao lâu là quyết định vận hành và tương thích của đội API.

Client cũng có thể đang lưu một link cũ từ response trước đó. Vì vậy, việc xóa link khỏi response mới không đồng nghĩa mọi client đã ngừng sử dụng URI cũ. Trước khi ngừng endpoint, cần đánh giá mức độ sử dụng, thông báo lịch trình và cung cấp hướng xử lý phù hợp.

## 5. Quy trình chuyển đổi an toàn

Một quy trình deprecation có thể thực hiện theo các bước:

1. **Xác định thay đổi:** chọn link relation hoặc endpoint cần thay thế và xác định lý do.
2. **Thiết kế đích mới:** công bố URI và relation mới với ngữ nghĩa rõ ràng; giữ tương thích dữ liệu và quyền truy cập trong phạm vi có thể.
3. **Công bố deprecation:** tiếp tục phát link cũ, gắn `deprecation` trỏ đến tài liệu hướng dẫn, đồng thời phát link mới.
4. **Thông báo và theo dõi:** cập nhật tài liệu API, thông báo cho nhóm client và theo dõi lưu lượng đến endpoint cũ nếu hệ thống có telemetry.
5. **Đánh giá mức độ chuyển đổi:** xác nhận các client quan trọng đã chuyển sang link mới hoặc đã có phương án tương thích.
6. **Ngừng công bố rồi ngừng hỗ trợ:** bỏ link cũ khỏi representation mới và chỉ tắt endpoint theo lịch trình đã thông báo.

Thời gian giữa các bước phụ thuộc số lượng client, khả năng kiểm soát client và mức độ ảnh hưởng của thay đổi. API công khai cho nhiều tổ chức thường cần thời gian chuyển đổi dài hơn API nội bộ có thể phối hợp trực tiếp.

## 6. Công bố link thay thế

Metadata `deprecation` chỉ chỉ đến tài liệu giải thích, vì vậy representation nên cung cấp link thay thế nếu API đã có đích mới. Ví dụ:

```java
EntityModel<OrderRepresentation> model = EntityModel.of(
        OrderRepresentation.from(order),
        linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel(),
        linkTo(methodOn(OrderController.class)
                .one(order.getId())).withRel("order"),
        linkTo(methodOn(OrderController.class)
                .legacyDetails(order.getId()))
                .withRel("legacy-order")
                .withDeprecation(LEGACY_ORDER_DEPRECATION));
```

Ở đây, client cũ có thể tiếp tục nhận diện relation `legacy-order`, trong khi client mới sử dụng `order`. Không nên đổi ý nghĩa của một relation đã công bố mà không có kế hoạch tương thích. Nếu giữ nguyên relation nhưng đổi URI đích, client hypermedia có thể theo URI mới mà không cần biết cấu trúc URL; tuy nhiên, thay đổi representation hoặc hành vi endpoint vẫn cần được đánh giá tương thích riêng.

Nếu chưa có endpoint thay thế, tài liệu deprecation cần nói rõ lựa chọn hiện tại, chẳng hạn client nên dùng relation khác đã tồn tại, ngừng gọi hành động đó hoặc chờ phiên bản API mới. Tránh phát link deprecated mà không cung cấp hướng dẫn có thể thực hiện.

## 7. Deprecation của Link khác với @Deprecated

Các khái niệm sau có phạm vi khác nhau:

| Cơ chế | Phạm vi | Tác dụng |
| --- | --- | --- |
| `Link.withDeprecation(uri)` | Một hypermedia link trong representation | Đính kèm URI tài liệu giải thích deprecation của link |
| `@Deprecated` trong Java | Class, method, field hoặc API ở mức mã nguồn | Báo cho lập trình viên rằng phần tử Java không còn được khuyến nghị sử dụng |
| HTTP `Deprecation` response header | HTTP response của một resource | Công bố thông tin deprecation ở mức HTTP theo quy ước header |

Gắn `deprecation` cho link không tự đánh dấu method Java là `@Deprecated`. Ngược lại, thêm `@Deprecated` vào một handler cũng không tự đưa metadata deprecation vào representation hypermedia. Nếu cần cả hai, phải triển khai từng cơ chế phù hợp với mục đích của nó.

## 8. Client nên xử lý link deprecated thế nào?

Client hypermedia có thể chọn cách xử lý theo mức độ quan trọng của hành động và khả năng nâng cấp:

- Khi phát hiện thuộc tính `deprecation`, client có thể ghi log hoặc phát telemetry để đội vận hành biết client đang sử dụng link cũ.
- Ứng dụng dành cho người dùng có thể ẩn hoặc đánh dấu hành động cũ, tùy theo chính sách sản phẩm.
- SDK hoặc client tự động có thể hiển thị cảnh báo cho nhà phát triển và cung cấp đường dẫn đến tài liệu deprecation.
- Client có thể ưu tiên relation thay thế khi đã hỗ trợ hợp đồng mới.
- Nếu client không hiểu metadata deprecation, nó vẫn có thể xử lý `href` và relation như trước, miễn endpoint còn được hỗ trợ.

Không nên mặc định mọi client đều hiểu hoặc tự động chuyển sang URI trong tài liệu deprecation. Đây là metadata hướng dẫn; hành vi chuyển đổi phụ thuộc logic của client và hợp đồng mới.

## 9. Kiểm thử link deprecation

Kiểm thử cần xác nhận link cũ vẫn được công bố trong giai đoạn chuyển đổi, metadata `deprecation` chứa đúng URI tài liệu và link thay thế có mặt. Với Spring MVC và HAL, có thể dùng `MockMvc`:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.legacy-order.href").exists())
    .andExpect(jsonPath("$._links.legacy-order.deprecation")
            .value("https://api.example.test/docs/deprecations/legacy-order"))
    .andExpect(jsonPath("$._links.order.href").exists());
```

Test thực tế cần cấu hình controller, dữ liệu và HAL converter phù hợp. Ngoài response JSON, nên kiểm tra:

- URI trong `deprecation` dẫn đến tài liệu còn truy cập được.
- Link cũ vẫn hoạt động trong giai đoạn chuyển đổi theo chính sách đã công bố.
- Link mới trỏ đến đúng resource hoặc hành động thay thế.
- Các response khác nhau vẫn sử dụng relation và metadata nhất quán.
- Sau khi kết thúc giai đoạn chuyển đổi, việc bỏ link và ngừng endpoint tuân thủ lịch trình API.

Không chỉ kiểm tra chuỗi metadata xuất hiện trong JSON; cần xác nhận nội dung tài liệu deprecation và hành vi endpoint thực tế cũng phù hợp.

## 10. Lỗi thường gặp

**Nhầm URI deprecation với URI thay thế:** `deprecation` trỏ đến tài liệu giải thích thay đổi. URI thay thế cần được công bố bằng một link relation riêng.

**Nghĩ rằng metadata tự ngừng endpoint:** `withDeprecation(...)` chỉ gắn thông tin vào link. Endpoint vẫn hoạt động hoặc bị tắt theo logic triển khai của server.

**Xóa link ngay khi đánh dấu deprecated:** client cũ có thể mất khả năng khám phá link mà nó đang dùng. Nên có giai đoạn chuyển đổi và công bố link mới.

**Không giữ tài liệu deprecation ổn định:** client và đội tích hợp không thể tra cứu lý do hoặc hướng nâng cấp nếu URI tài liệu bị xóa quá sớm.

**Thay đổi relation mà không thông báo:** relation là một phần hợp đồng hypermedia. Đổi tên hoặc đổi ý nghĩa relation có thể ảnh hưởng client ngay cả khi URI vẫn hoạt động.

**Cho rằng client sẽ tự chuyển đổi:** metadata không bắt buộc client tải tài liệu hoặc chọn link mới. Hãy thông báo và hỗ trợ nâng cấp theo khả năng của hệ thống.

## 11. Checklist deprecation cho Spring HATEOAS

- Xác định chính xác link relation hoặc endpoint cần deprecated.
- Dùng `Link.withDeprecation(...)` để gắn URI tài liệu giải thích.
- Duy trì tài liệu deprecation ổn định, có lý do và hướng dẫn chuyển đổi.
- Công bố link relation thay thế khi đã có đích mới.
- Giữ link cũ trong giai đoạn chuyển đổi theo chính sách tương thích.
- Theo dõi mức độ sử dụng link hoặc endpoint cũ.
- Phân biệt metadata link với `@Deprecated` và HTTP response header.
- Kiểm thử `href`, `deprecation`, relation thay thế và hành vi endpoint.
- Chỉ ngừng công bố hoặc ngừng phục vụ link cũ theo lịch trình đã thông báo.

`Link.withDeprecation(...)` giúp API công bố thông tin về một liên kết không còn được khuyến nghị sử dụng mà vẫn hỗ trợ quá trình chuyển đổi có kiểm soát. Khi metadata đi kèm tài liệu rõ ràng và link thay thế, client có thể nhận biết thay đổi, lập kế hoạch nâng cấp và tiếp tục khám phá API qua hợp đồng hypermedia.
