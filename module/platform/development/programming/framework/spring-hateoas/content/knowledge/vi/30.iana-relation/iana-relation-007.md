# Relation related trong Spring HATEOAS

Một representation hypermedia có thể cung cấp nhiều link tới các tài nguyên liên quan. Khi quan hệ có vai trò cụ thể, API nên dùng relation diễn đạt rõ vai trò đó, chẳng hạn `customer`, `items` hoặc `invoice`. Nhưng đôi khi tài nguyên đích có liên quan tới tài nguyên hiện tại mà không có một relation chuyên biệt phù hợp. IANA link relation `related` được dùng cho trường hợp tổng quát này.

Spring HATEOAS cung cấp `IanaLinkRelations.RELATED` để tạo link theo relation đã đăng ký. Relation này cho client biết link đích trỏ tới một tài nguyên có liên quan tới ngữ cảnh hiện tại. Nó không tự xác định loại association, chiều quan hệ, HTTP method hay quy tắc nghiệp vụ. Bài học này giải thích semantics của `related`, cách tạo link trong Spring HATEOAS, cách phân biệt nó với relation chuyên biệt và cách kiểm thử representation HAL.

## 1. IANA link relation related là gì?

IANA đăng ký các link relation dùng chung trên Web. Relation `related` có mô tả ngắn: “Identifies a related resource.” Nó được đăng ký với tham chiếu RFC 4287 (Atom Syndication Format).

Trong một link, có thể hình dung:

- Context là tài nguyên đang chứa link.
- Target là tài nguyên được trỏ tới bởi `href`.
- Relation `related` mô tả mối quan hệ tổng quát giữa target và context.

Ví dụ, representation của một đơn hàng có thể liên kết tới một trang thông tin hỗ trợ liên quan:

```json
{
  "id": "order-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/order-42"
    },
    "related": {
      "href": "/support/orders/pending-delivery",
      "title": "Thông tin hỗ trợ về đơn hàng đang chờ giao"
    }
  }
}
```

Ở đây, link `related` chỉ ra tài nguyên hỗ trợ có liên quan đến đơn hàng. Client có thể theo URI đó nếu cần thông tin bổ sung. Relation không nói rằng tài nguyên hỗ trợ là cha, con, collection hay một bản thay thế của đơn hàng.

## 2. Ý nghĩa của related và những điều nó không khẳng định

`related` là relation rộng. Nó hữu ích khi server biết tài nguyên đích có liên quan, nhưng mối quan hệ không thuộc một loại đã đăng ký hoặc một relation nghiệp vụ cụ thể mà API muốn công bố.

Relation này **không tự khẳng định**:

- Tài nguyên đích là cha hoặc con của tài nguyên hiện tại.
- Tài nguyên đích là collection hay một item.
- Tài nguyên đích là bản thay thế, bản mô tả hoặc bản xem trước.
- Link tương ứng với thao tác GET, POST, PUT hay DELETE.
- Client có quyền truy cập tài nguyên đích.
- Tài nguyên đích phải được nhúng vào response hiện tại.

Client chỉ có thể suy ra rằng target có liên quan tới context. Nếu client cần phân biệt chính xác loại quan hệ để thực hiện logic, server nên công bố relation chuyên biệt hơn hoặc cung cấp metadata bổ sung.

## 3. Khi nào nên dùng related?

Chọn `related` khi quan hệ có thật và có ích cho việc điều hướng, nhưng không có một relation chuyên biệt phù hợp hơn.

Một số tình huống có thể dùng:

| Context | Target | Vì sao related phù hợp |
| --- | --- | --- |
| Đơn hàng | Trang hướng dẫn xử lý đơn hàng bị chậm | Tài liệu hỗ trợ có liên quan nhưng không phải chính sách, hóa đơn hay tài nguyên cha/con. |
| Hồ sơ nhân viên | Trang thông tin về chương trình phúc lợi liên quan | Trang đó có liên quan đến hồ sơ nhưng không phải một phần của hồ sơ. |
| Báo cáo | Tài nguyên giải thích dữ liệu nguồn | Có liên hệ ngữ cảnh nhưng không nhất thiết là tài liệu mô tả chính thức. |
| Sản phẩm | Một tài nguyên nội dung bổ trợ | Có liên quan tới sản phẩm nhưng không phải biến thể hoặc tài nguyên thay thế. |

Hãy đặt câu hỏi: “Nếu client chỉ đọc relation, nó có cần biết chính xác loại association để hoạt động không?” Nếu câu trả lời là có, `related` có thể quá chung. Nếu client chỉ cần biết có một tài nguyên liên quan để tùy chọn khám phá, `related` có thể phù hợp.

## 4. Khi nào nên dùng relation chuyên biệt thay cho related?

Không dùng `related` như một nhãn mặc định cho mọi link không phải `self`. Relation chuyên biệt giúp client hiểu rõ vai trò của target.

| Ý nghĩa thực tế | Relation nên xem xét | Không nên dùng related khi… |
| --- | --- | --- |
| Chính tài nguyên hiện tại | `self` | Target chính là context. |
| Tài nguyên khách hàng của đơn hàng | `customer` (extension relation của API) | Client cần biết target là khách hàng. |
| Collection các dòng hàng | `items` (extension relation của API) | Client cần biết target là collection dòng hàng. |
| Tài nguyên cha trong hệ phân cấp | `up` | Quan hệ cha đã được xác định. |
| Tài nguyên mô tả context | `describedby` | Target cung cấp mô tả cho context. |
| Tài nguyên là chủ đề của context | `about` | Context đang nói về target. |
| Bản thay thế của context | `alternate` | Target là representation hoặc tài nguyên thay thế. |
| Tài nguyên đính kèm, có thể lớn | `enclosure` | Target là tài nguyên đính kèm cần xử lý đặc biệt. |
| Tài nguyên xem trước context | `preview` | Target là bản xem trước. |

Ví dụ, nếu đơn hàng có khách hàng sở hữu, dùng relation `customer` sẽ rõ hơn `related`. Nếu một tài liệu có trang hướng dẫn bổ sung nhưng không có khái niệm quan hệ cụ thể hơn, `related` có thể diễn đạt vừa đủ.

## 5. Dùng IanaLinkRelations.RELATED trong Spring HATEOAS

Spring HATEOAS biểu diễn relation bằng `LinkRelation`. Các relation IANA được cung cấp dưới dạng hằng trong `IanaLinkRelations`. Với `related`, dùng `IanaLinkRelations.RELATED` thay vì tự gõ chuỗi trong nhiều nơi.

Ví dụ tạo link tới tài nguyên hỗ trợ liên quan:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link relatedLink = linkTo(methodOn(SupportController.class)
        .orderHelp(order.getId()))
        .withRel(IanaLinkRelations.RELATED)
        .withTitle("Hướng dẫn hỗ trợ đơn hàng");
```

`methodOn(...)` tham chiếu method controller để Spring HATEOAS dựng URI từ mapping và tham số. Nó không thực thi endpoint `orderHelp(...)`. `withRel(IanaLinkRelations.RELATED)` gắn relation chuẩn IANA; `withTitle(...)` bổ sung nhãn dễ đọc cho link.

`IanaLinkRelations.RELATED` có kiểu `LinkRelation`. Nếu cần chuỗi tương ứng, Spring HATEOAS cũng cung cấp `IanaLinkRelations.RELATED_VALUE`, có giá trị `related`. Trong code tạo link, ưu tiên dùng hằng `LinkRelation` để tránh sai chính tả và giữ kiểu nhất quán.

## 6. Gắn related link vào RepresentationModel hoặc EntityModel

Một assembler có thể tạo model tài nguyên, thêm self link và thêm link related:

```java
@Component
class OrderModelAssembler {

    EntityModel<OrderView> toModel(Order order) {
        OrderView view = new OrderView(
                order.getId(),
                order.getStatus().name(),
                order.getTotal()
        );

        Link self = linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel();

        Link related = linkTo(methodOn(SupportController.class)
                .orderHelp(order.getId()))
                .withRel(IanaLinkRelations.RELATED)
                .withTitle("Thông tin hỗ trợ liên quan");

        return EntityModel.of(view, self, related);
    }
}
```

Trong ví dụ, `self` nhận diện representation đơn hàng; `related` dẫn tới tài nguyên hỗ trợ. Hai link có semantics khác nhau dù cùng xuất hiện trong `_links`.

Nếu model đã được tạo, có thể bổ sung link bằng `model.add(relatedLink)`. Cách này phù hợp khi assembler hoặc processor có thêm ngữ cảnh để quyết định có công bố link hay không.

## 7. Related trong HAL JSON

Với HAL JSON, link relation trở thành tên thuộc tính trong `_links`. Một response đơn giản có thể như sau:

```json
{
  "id": "order-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/order-42"
    },
    "related": {
      "href": "/support/orders/order-42",
      "title": "Thông tin hỗ trợ liên quan"
    }
  }
}
```

`href` là URI client theo khi muốn khám phá tài nguyên liên quan. `title` là nhãn tùy chọn; nó giúp con người hiểu link nhưng không thay thế semantics của relation. Nếu client cần logic máy dựa trên loại tài nguyên đích, hãy dùng relation rõ nghĩa thay vì dựa vào `title`.

HAL có thể biểu diễn một link dưới dạng object và nhiều link cùng relation dưới dạng mảng. Do đó client cần chấp nhận cả hai hình dạng khi một relation có thể xuất hiện nhiều lần.

## 8. Một context có thể có nhiều link related

Một tài nguyên có thể liên quan tới nhiều tài nguyên khác nhau. Ví dụ một đơn hàng có thể liên kết tới hướng dẫn giao hàng, chính sách đổi trả và trang hỗ trợ thanh toán. Nếu API không cần phân biệt các loại đó bằng relation riêng, có thể công bố nhiều link cùng relation `related`.

```java
EntityModel<OrderView> model = EntityModel.of(view, selfLink);

model.add(
        linkTo(methodOn(SupportController.class)
                .deliveryHelp(order.getId()))
                .withRel(IanaLinkRelations.RELATED)
                .withTitle("Hướng dẫn giao hàng"),
        linkTo(methodOn(SupportController.class)
                .returnPolicy(order.getId()))
                .withRel(IanaLinkRelations.RELATED)
                .withTitle("Chính sách đổi trả"),
        linkTo(methodOn(SupportController.class)
                .paymentHelp(order.getId()))
                .withRel(IanaLinkRelations.RELATED)
                .withTitle("Hỗ trợ thanh toán")
);
```

HAL response có thể biểu diễn nhiều link như một mảng:

```json
{
  "_links": {
    "related": [
      {
        "href": "/support/orders/order-42/delivery",
        "title": "Hướng dẫn giao hàng"
      },
      {
        "href": "/support/orders/order-42/returns",
        "title": "Chính sách đổi trả"
      },
      {
        "href": "/support/orders/order-42/payment",
        "title": "Hỗ trợ thanh toán"
      }
    ]
  }
}
```

Nếu client cần chọn một link dựa trên vai trò cụ thể, nhiều link cùng relation `related` có thể không đủ thông tin. Khi đó nên dùng relation chuyên biệt như `delivery-help`, `return-policy` hoặc `payment-help` theo quy ước extension relation của API. Có thể tiếp tục dùng `title` để hiển thị nhãn thân thiện.

## 9. Related link không phải embedded resource

Link và embedded resource có cách sử dụng khác nhau:

| Cách biểu diễn | Vị trí trong HAL | Ý nghĩa |
| --- | --- | --- |
| Related link | `_links.related` | Công bố URI của tài nguyên có liên quan. |
| Embedded resource | `_embedded` | Đưa representation của tài nguyên con vào response hiện tại. |

Ví dụ, `related` có thể dẫn tới trang hỗ trợ nhưng không đưa nội dung trang hỗ trợ vào response đơn hàng. Client chỉ tải tài nguyên đó khi cần.

Không nhúng tài nguyên chỉ vì nó có relation `related`. Việc embedding cần được quyết định theo nhu cầu client, kích thước dữ liệu, cache và ranh giới representation. Ngược lại, nếu một tài nguyên được nhúng, API vẫn có thể cung cấp link để client truy cập trực tiếp tài nguyên đó.

## 10. Related không mô tả HTTP method hay affordance

Relation cho biết mối quan hệ giữa link target và context. Nó không tự cho biết client phải gửi GET, POST, PATCH hay DELETE. Với link `related`, client thường theo URI để lấy tài nguyên, nhưng semantics của relation không đảm bảo method hoặc payload cụ thể.

Nếu link đại diện cho một hành động có thể thực hiện, hãy xem xét affordance của Spring HATEOAS để mô tả method, target và input metadata. Relation có thể là một tên hành động phù hợp với hợp đồng API, hoặc dùng relation chuẩn như `edit` khi đúng semantics. Không nên dùng `related` như cách thay thế chung cho mọi action link.

Ví dụ, tài nguyên đơn hàng có thể có link `related` tới hướng dẫn hỗ trợ và một affordance `cancel` mô tả thao tác hủy. Hai mục đích khác nhau nên không nên gộp vào cùng một relation.

## 11. Kết hợp related với các thuộc tính khác của Link

Spring HATEOAS `Link` hỗ trợ thêm thuộc tính theo Web Linking, tùy nhu cầu của API:

```java
Link related = linkTo(methodOn(SupportController.class)
        .orderHelp(order.getId()))
        .withRel(IanaLinkRelations.RELATED)
        .withTitle("Hướng dẫn xử lý đơn hàng")
        .withType(MediaType.TEXT_HTML_VALUE);
```

Một số thuộc tính có thể hữu ích:

| Thuộc tính | Mục đích |
| --- | --- |
| `title` | Nhãn mô tả link cho người dùng. |
| `type` | Gợi ý media type của representation tại target. |
| `hreflang` | Gợi ý ngôn ngữ của tài nguyên đích. |
| `name` | Phân biệt các link cùng relation trong một số định dạng/ứng dụng. |
| `deprecation` | URI cung cấp thông tin về việc relation/link bị deprecated. |
| `profile` | Tham chiếu profile mô tả semantics của representation đích. |

Các thuộc tính này bổ sung thông tin cho link; chúng không thay đổi định nghĩa của IANA relation `related`. Ví dụ `title` không biến `related` thành `customer`, và `type` không bảo đảm server sẽ luôn trả media type đó.

## 12. Dùng related có điều kiện theo trạng thái hoặc dữ liệu

Không phải tài nguyên nào cũng có cùng các liên kết liên quan. Có thể chỉ công bố link khi target tồn tại hoặc khi nó hữu ích với trạng thái hiện tại.

```java
EntityModel<OrderView> model = EntityModel.of(view, selfLink);

if (order.getSupportCaseId() != null) {
    model.add(linkTo(methodOn(SupportCaseController.class)
            .one(order.getSupportCaseId()))
            .withRel(IanaLinkRelations.RELATED)
            .withTitle("Vụ hỗ trợ liên quan"));
}
```

Nếu không có vụ hỗ trợ, không tạo link tới một URI giả. Nếu link phụ thuộc quyền của người dùng, hãy quyết định công bố theo policy phù hợp. Tuy nhiên, endpoint đích vẫn phải tự xác thực và phân quyền khi request tới; việc link xuất hiện không cấp quyền truy cập.

Khi nhiều loại tài nguyên khác nhau cùng được công bố bằng `related`, client cần có cách phân biệt nếu quy trình yêu cầu. Có thể dùng relation chuyên biệt, `name`, `title` hoặc metadata tài nguyên, tùy mức độ tự động hóa mà client cần.

## 13. Kiểm tra related link trong model bằng Java

Spring HATEOAS cho phép truy vấn link theo relation:

```java
assertThat(model.hasLink(IanaLinkRelations.RELATED)).isTrue();

List<Link> relatedLinks = model.getLinks(IanaLinkRelations.RELATED);
assertThat(relatedLinks).hasSize(2);
```

`getLinks(...)` trả về tất cả link mang relation được chỉ định. Điều này hữu ích khi một model có nhiều link `related`. Nếu chỉ cần một link, có thể dùng `getLink(...)` để nhận `Optional<Link>`; không nên giả định relation chỉ xuất hiện một lần nếu hợp đồng cho phép nhiều target.

Kiểm thử nên xác nhận cả `href` lẫn relation. Một link có thể có relation đúng nhưng URI sai, hoặc URI đúng nhưng relation bị đặt nhầm thành `self` hay `customer`.

## 14. Kiểm thử related trong HAL bằng MockMvc

Một integration test có thể xác nhận relation và URI được serialize đúng:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
            .value(endsWith("/orders/" + orderId)))
    .andExpect(jsonPath("$._links.related.href")
            .value(endsWith("/support/orders/" + orderId)));
```

Nếu response có nhiều link `related`, kiểm tra từng phần tử trong mảng hoặc parse JSON thành `JsonNode` rồi duyệt `related`. Không viết test phụ thuộc thứ tự mảng nếu API không cam kết thứ tự các link.

Các trường hợp nên kiểm thử:

- Model có một link related.
- Model có nhiều link cùng relation.
- Target liên quan không tồn tại nên link không được thêm.
- Link chỉ được công bố khi policy cho phép.
- Relation chuyên biệt được dùng khi client cần phân biệt loại target.
- `_links.related` không bị nhầm thành `_embedded`.
- Link đích hoạt động và endpoint vẫn thực hiện authorization độc lập.

## 15. Các lỗi thường gặp khi dùng relation related

**Dùng related cho mọi association.** Nếu client cần biết target là khách hàng, dòng hàng hoặc hóa đơn, hãy dùng relation chuyên biệt như `customer`, `items` hoặc `invoice`.

**Dùng related thay cho self.** Link trỏ tới chính tài nguyên hiện tại cần relation `self`.

**Cho rằng related xác định quan hệ cha/con.** Relation này chỉ nói target có liên quan; dùng `up` hoặc relation chuyên biệt nếu cấu trúc phân cấp đã được xác định.

**Cho rằng related là action.** Relation không mô tả HTTP method hoặc payload. Dùng affordance khi cần công bố cách thực hiện thao tác.

**Nhầm related link với embedded resource.** `_links.related` chỉ công bố URI; `_embedded` chứa representation được nhúng.

**Dùng title thay cho semantics.** `title` là nhãn hiển thị; client cần semantics ổn định nên dựa vào relation chuyên biệt.

**Giả định chỉ có một link related.** Một context có thể liên kết tới nhiều tài nguyên cùng relation; client và test cần hỗ trợ dạng mảng HAL.

**Coi link là quyền truy cập.** Endpoint đích vẫn phải xác thực và phân quyền mỗi request.

## 16. Bài tập thực hành và tiêu chí hoàn thành

Hãy bổ sung link liên quan cho API quản lý đơn hàng:

1. Tạo `OrderModelAssembler` trả `EntityModel<OrderView>` với self link.
2. Tạo endpoint hỗ trợ đơn hàng và thêm link tới endpoint đó bằng `IanaLinkRelations.RELATED`.
3. Bổ sung `title` để client có nhãn hiển thị.
4. Tạo hai hoặc ba tài nguyên hỗ trợ liên quan và thử nhiều link cùng relation.
5. Kiểm tra HAL biểu diễn một link và nhiều link trong `_links.related`.
6. Thử một association có relation chuyên biệt như `customer` và so sánh khả năng hiểu của client với `related`.
7. Xác nhận related link không tạo embedded resource ngoài ý muốn.
8. Chỉ công bố link khi tài nguyên đích tồn tại và người dùng được phép khám phá.
9. Viết unit test bằng `hasLink`/`getLinks` và integration test bằng MockMvc.
10. Kiểm tra endpoint đích vẫn bảo vệ tài nguyên bằng authorization độc lập với link.

Bạn đã hiểu relation `related` khi có thể giải thích ý nghĩa tổng quát của nó, chọn đúng tình huống cần liên kết tới tài nguyên có liên quan, sử dụng `IanaLinkRelations.RELATED`, phân biệt nó với `self` và relation chuyên biệt, xử lý nhiều link cùng relation và kiểm thử response HAL. Dùng `related` đúng phạm vi giúp API cung cấp đường điều hướng bổ sung mà không gán cho quan hệ một ý nghĩa cụ thể sai lệch.

## Tài liệu tham khảo chính thức

- [IANA Link Relations Registry](https://www.iana.org/assignments/link-relations)
- [RFC 4287 – Atom Syndication Format, link relation types](https://www.rfc-editor.org/rfc/rfc4287)
- [Spring HATEOAS Reference Documentation – Link relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.link-relations)
- [IanaLinkRelations API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [LinkRelation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
