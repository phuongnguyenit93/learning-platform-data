# Kiểm tra relation

Một response HAL của API đơn hàng có thể chứa các liên kết `self`, `orders`, `customer` và `next`. Client cần biết liên kết nào trỏ đến chính đơn hàng, liên kết nào dẫn về danh sách, liên kết nào mở hồ sơ khách hàng và liên kết nào chuyển sang trang kế tiếp. Thông tin đó nằm ở **link relation** (`rel`). Trong Spring HATEOAS, `LinkRelation` biểu diễn tên quan hệ, còn `Link` chứa relation cùng URI đích và metadata khác.

Kiểm tra relation là việc xác nhận một liên kết mang đúng quan hệ mà hợp đồng API mong đợi. Có thể kiểm tra trực tiếp trong Java bằng `LinkRelation`, `IanaLinkRelations` và các phương thức của `RepresentationModel`, hoặc kiểm tra JSON HAL đã serialize bằng MockMvc. Việc này giúp phát hiện trường hợp link vẫn tồn tại nhưng bị gắn sai `rel`, khiến client điều hướng sai hoặc không nhận ra chức năng.

## Relation mô tả điều gì?

Một link biểu diễn mối quan hệ giữa resource hiện tại và một resource đích. Link thường có các thành phần:

| Thành phần | Câu hỏi | Ví dụ |
| --- | --- | --- |
| `rel` | Đích có quan hệ gì với resource hiện tại? | `self`, `next`, `orders`, `customer` |
| `href` | Client truy cập đích ở đâu? | `/api/orders/ord-1042` |
| `title` | Có thể mô tả link bằng nhãn nào? | `Chi tiết đơn hàng` |
| `type` | Media type nào được mong đợi ở đích? | `application/hal+json` |

`rel` là phần ngữ nghĩa của link. Ví dụ, hai liên kết có thể có URI rất khác nhau nhưng cùng relation `orders`, vì cả hai đều dẫn đến collection đơn hàng trong những ngữ cảnh khác nhau. Ngược lại, hai link có URI gần giống nhau vẫn có thể mang quan hệ khác nhau.

Client nên nhận biết link bằng relation và theo `href` được cung cấp. Không nên suy luận quan hệ chỉ từ path, title hoặc vị trí của link trong JSON. URI có thể thay đổi khi server tổ chức lại endpoint; relation vẫn có thể giữ ngữ nghĩa ổn định để client tiếp tục hoạt động.

## LinkRelation trong Spring HATEOAS

`LinkRelation` là kiểu giá trị đại diện cho một relation. Nó tách định danh quan hệ khỏi đối tượng `Link`, giúp mã ứng dụng so sánh và xử lý quan hệ mà không cần thao tác chuỗi ở mọi nơi.

Có thể tạo relation riêng bằng `LinkRelation.of(...)`:

```java
import org.springframework.hateoas.LinkRelation;

LinkRelation ordersRelation = LinkRelation.of("orders");
```

Một link có thể được tạo với relation đó:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

LinkRelation ordersRelation = LinkRelation.of("orders");

Link orders = Link.of("/api/orders")
    .withRel(ordersRelation.value());
```

`Link.getRel()` trả về `LinkRelation`; `value()` lấy chuỗi relation để log, hiển thị hoặc tích hợp với API cần chuỗi. Khi so sánh trong mã Java, ưu tiên so sánh đối tượng relation thay vì tự chuẩn hóa chuỗi.

```java
boolean isOrdersLink = orders.getRel().equals(ordersRelation);
```

Quan hệ là một phần của hợp đồng hypermedia. Tên relation nên được thống nhất giữa server và client, có ngữ nghĩa rõ ràng và không bị tái sử dụng cho một ý nghĩa khác.

## Relation chuẩn IANA và relation mở rộng

Một số relation phổ biến đã được IANA đăng ký trong registry Web Link Relations. Spring HATEOAS cung cấp `IanaLinkRelations` với các hằng số cho những relation chuẩn. Dùng các hằng số này giúp tránh gõ sai tên và làm rõ ý định trong code.

Một số relation thường gặp:

| Hằng số Spring HATEOAS | Giá trị relation | Ý nghĩa thường dùng |
| --- | --- | --- |
| `IanaLinkRelations.SELF` | `self` | Resource hiện tại |
| `IanaLinkRelations.NEXT` | `next` | Trang hoặc phần tiếp theo |
| `IanaLinkRelations.PREV` | `prev` | Trang hoặc phần trước |
| `IanaLinkRelations.FIRST` | `first` | Trang đầu tiên |
| `IanaLinkRelations.LAST` | `last` | Trang cuối cùng |
| `IanaLinkRelations.RELATED` | `related` | Resource có liên quan |
| `IanaLinkRelations.SEARCH` | `search` | Điểm tìm kiếm liên quan |
| `IanaLinkRelations.EDIT` | `edit` | Liên kết chỉnh sửa theo ngữ nghĩa của media type/hợp đồng |

Ví dụ tạo link trang tiếp theo:

```java
Link next = Link.of("/api/orders?page=2")
    .withRel(IanaLinkRelations.NEXT.value());
```

Relation nghiệp vụ như `orders`, `customer` hoặc `cancel` có thể là relation mở rộng do API định nghĩa. `LinkRelation.of("orders")` cho phép Spring HATEOAS biểu diễn tên ngắn này. Tuy nhiên, theo quy tắc Web Linking, một extension relation dùng như relation type cần được định danh bằng URI tuyệt đối; HAL có thể dùng CURIE để biểu diễn URI relation ở dạng ngắn. Với API công khai hoặc cần liên thông giữa nhiều tổ chức, hãy ưu tiên URI relation có tài liệu ngữ nghĩa ổn định. Nếu dùng tên ngắn nội bộ, cần thống nhất rõ quy ước giữa server và client.

Không tự tạo tên riêng trùng với relation IANA đã đăng ký nhưng mang ý nghĩa khác. Khi cần relation mở rộng, tài liệu API nên giải thích quan hệ đó, đối tượng đích và cách client sử dụng.

## Kiểm tra một Link riêng lẻ

Vì `Link.getRel()` trả về `LinkRelation`, có thể so sánh với relation mong đợi:

```java
Link self = Link.of("/api/orders/ord-1042").withSelfRel();

boolean isSelf = self.getRel().equals(IanaLinkRelations.SELF);
boolean isNext = self.getRel().equals(IanaLinkRelations.NEXT);
```

Trong ví dụ, `isSelf` là `true` và `isNext` là `false`. Kiểm tra relation không xác nhận đích URI đúng; nếu hợp đồng yêu cầu cả hai, cần kiểm tra `getHref()` riêng.

```java
assertThat(self.getRel()).isEqualTo(IanaLinkRelations.SELF);
assertThat(self.getHref()).isEqualTo("/api/orders/ord-1042");
```

Với relation mở rộng, tạo `LinkRelation` mong đợi rồi so sánh:

```java
LinkRelation customerRelation = LinkRelation.of("customer");

assertThat(customerLink.getRel()).isEqualTo(customerRelation);
```

Không nên kiểm tra title để kết luận relation đúng. Title có thể được dịch hoặc thay đổi câu chữ mà không thay đổi relation.

## Kiểm tra relation trong RepresentationModel

Các model của Spring HATEOAS như `EntityModel`, `CollectionModel` và lớp kế thừa `RepresentationModel` đều có thể chứa link. `RepresentationModel` cung cấp những phương thức tiện ích để kiểm tra và lấy link theo relation.

Ví dụ với `EntityModel<OrderView>`:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;

EntityModel<OrderView> model = orderAssembler.toModel(order);

boolean hasSelf = model.hasLink(IanaLinkRelations.SELF);

model.getLink(IanaLinkRelations.SELF).ifPresent(link -> {
    System.out.println("Self URI: " + link.getHref());
});
```

`hasLink(...)` phù hợp khi chỉ cần biết quan hệ có tồn tại hay không. `getLink(...)` trả về `Optional<Link>`, phù hợp khi link có thể không xuất hiện theo trạng thái hoặc quyền của người gọi.

Nếu hợp đồng bắt buộc phải có link `self`, có thể dùng `getRequiredLink(...)`. Phương thức này thể hiện rõ rằng thiếu link là một lỗi hợp đồng và sẽ ném ngoại lệ nếu không tìm thấy:

```java
Link self = model.getRequiredLink(IanaLinkRelations.SELF);
```

Chỉ dùng `getRequiredLink(...)` khi thiếu relation thực sự là lỗi. Với link tùy chọn như `cancel`, `next` hoặc `returns`, nên dùng `hasLink(...)` hoặc `getLink(...)` để xử lý trường hợp không khả dụng.

## Duyệt và kiểm tra nhiều link

Một model có thể có nhiều liên kết với các relation khác nhau. Có thể duyệt tập link để kiểm tra các relation được công bố:

```java
for (Link link : model.getLinks()) {
    System.out.printf("rel=%s href=%s%n",
        link.getRel().value(),
        link.getHref());
}
```

Ví dụ này hữu ích khi debug response hoặc kiểm tra tập relation. Trong code nghiệp vụ, nên truy vấn relation cụ thể bằng `hasLink(...)` hoặc `getLink(...)` thay vì phụ thuộc vào thứ tự link.

Nếu API cho phép nhiều link có cùng relation, đừng giả định mỗi relation luôn có đúng một đích. Khi cần xử lý mọi link, duyệt `model.getLinks()` và lọc theo `link.getRel()`. Điều này hữu ích cho các liên kết tài liệu, nhiều biến thể tải xuống hoặc nhiều tài nguyên liên quan cùng loại.

## Relation trong CollectionModel

Với collection, có thể có relation ở hai cấp:

- **Relation cấp collection:** `self`, `search`, `create`, `next` hoặc `profile`.
- **Relation của từng phần tử:** `self`, `customer`, `cancel` hoặc relation khác được thêm vào từng `EntityModel`.

Ví dụ kiểm tra link cấp collection và link cấp item:

```java
CollectionModel<EntityModel<OrderView>> collection =
    orderAssembler.toCollectionModel(orders);

assertThat(collection.hasLink(IanaLinkRelations.SELF)).isTrue();

EntityModel<OrderView> first = collection.getContent().iterator().next();
assertThat(first.hasLink(IanaLinkRelations.SELF)).isTrue();
```

Collection có thể rỗng, vì vậy không nên gọi `iterator().next()` nếu chưa kiểm tra có phần tử. Trong test thực tế, kiểm tra collection link độc lập với việc collection có item hay không; chỉ kiểm tra link cấp item khi có phần tử.

Một khái niệm dễ nhầm là relation của `_embedded` trong HAL. `@Relation` và cấu hình relation provider có thể điều khiển tên collection được dùng khi nhúng các phần tử. Tên đó không đồng nghĩa với link relation trong `_links`. Ví dụ, `_embedded.orders` đặt tên cho tập phần tử nhúng, còn `_links.orders` là một link relation có `href` riêng.

## Kiểm tra relation trong HAL JSON

Khi response dùng HAL (`application/hal+json`), relation trở thành tên khóa trong object `_links`. Ví dụ:

```json
{
  "id": "ord-1042",
  "_links": {
    "self": {
      "href": "/api/orders/ord-1042"
    },
    "orders": {
      "href": "/api/orders"
    },
    "customer": {
      "href": "/api/customers/cus-73"
    }
  }
}
```

Trong response này, `self`, `orders` và `customer` là relation. `href` là giá trị của link. Client đọc đúng relation để quyết định liên kết nào cần theo.

Với MockMvc, có thể kiểm tra relation bằng JSON path:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.orders.href").exists())
    .andExpect(jsonPath("$._links.customer.href").exists());
```

Nếu relation `cancel` chỉ xuất hiện khi đơn hàng đang `PENDING`, hãy kiểm tra cả hai trạng thái:

```java
mockMvc.perform(get("/api/orders/{id}", pendingOrderId)
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.cancel.href").exists());

mockMvc.perform(get("/api/orders/{id}", shippedOrderId)
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.cancel").doesNotExist());
```

Các kiểm thử này bảo vệ hợp đồng hypermedia: relation xuất hiện khi hành động khả dụng và biến mất khi không còn hợp lệ. Tuy nhiên, server vẫn phải kiểm tra quyền và trạng thái khi endpoint được gọi trực tiếp; thiếu link không phải là cơ chế bảo mật.

## Relation và CURIE trong HAL

Với API có nhiều relation mở rộng, có thể dùng CURIE (*Compact URI*) để viết relation URI dưới dạng ngắn trong HAL. Ví dụ, relation đầy đủ có thể là `https://api.example.com/rels/orders`, còn dạng rút gọn là `ex:orders`.

CURIE giúp response gọn hơn và liên kết relation với một namespace có thể được tài liệu hóa. Client cần biết cách mở rộng CURIE hoặc theo link profile tương ứng; không nên coi `ex:orders` là một relation IANA chuẩn.

Spring HATEOAS hỗ trợ CURIE thông qua `CurieProvider` và cấu hình hypermedia phù hợp. Chỉ nên dùng khi API thực sự có nhiều relation mở rộng cần một quy ước namespace. Với một vài relation đơn giản, tên relation ổn định cùng tài liệu API có thể dễ quản lý hơn.

## Đặt tên relation ổn định

Relation là một phần của hợp đồng mà client có thể dựa vào lâu dài. Khi thiết kế relation:

1. **Ưu tiên relation IANA khi đúng ngữ nghĩa:** dùng `self`, `next`, `prev`, `first` hoặc `last` cho các vai trò đã được chuẩn hóa.
2. **Đặt tên riêng có ý nghĩa nghiệp vụ:** ví dụ `orders`, `customer` hoặc `cancel`; tránh tên mơ hồ như `link1` hoặc `data2`.
3. **Dùng URI relation khi cần tính liên thông:** URI cho phép định danh toàn cục và cung cấp tài liệu về quan hệ mở rộng.
4. **Không đổi ý nghĩa relation đã công bố:** nếu cần thay đổi ngữ nghĩa, hãy tạo relation mới hoặc có lộ trình chuyển đổi rõ ràng.
5. **Không để client phụ thuộc vào URL:** path có thể đổi trong khi relation và hợp đồng điều hướng vẫn giữ nguyên.
6. **Không dùng title làm khóa:** title có thể bản địa hóa; relation mới là định danh ngữ nghĩa.

Relation nên mô tả quan hệ giữa resource hiện tại và resource đích, không chỉ mô tả hành động của một nút giao diện. Khi cần mô tả thao tác như HTTP method hoặc request body, hãy dùng affordance và media type hỗ trợ thay vì cố nhồi tất cả thông tin vào tên relation.

## Lỗi thường gặp khi kiểm tra relation

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| So sánh `href` để suy ra relation | Đổi path có thể làm client hỏng dù ngữ nghĩa không đổi. | Kiểm tra `Link.getRel()` hoặc relation trong `_links`. |
| Dùng `title` để xác định quan hệ | Bản địa hóa hoặc đổi câu chữ làm logic client sai. | Dùng `LinkRelation` và `rel`. |
| Gõ chuỗi IANA relation rải rác | Dễ sai chính tả và khó chuẩn hóa. | Dùng hằng số `IanaLinkRelations`. |
| Gọi `getRequiredLink` với relation tùy chọn | Response thiếu link hợp lệ theo trạng thái nhưng code lại ném ngoại lệ. | Dùng `hasLink` hoặc `getLink` cho link tùy chọn. |
| Giả định collection luôn có phần tử | Test hoặc code có thể lỗi khi collection rỗng. | Kiểm tra collection rỗng trước khi truy cập item. |
| Nhầm `_embedded` relation với `_links` relation | Client truy cập sai phần cấu trúc HAL. | Phân biệt tên tập phần tử nhúng với quan hệ của link điều hướng. |
| Đổi relation đã công bố mà không chuyển tiếp | Client cũ không tìm thấy link mong đợi. | Giữ relation cũ trong giai đoạn chuyển đổi hoặc phát hành relation mới có kế hoạch. |

## Ghi nhớ

- `LinkRelation` đại diện cho relation; `Link` chứa relation, `href` và metadata của liên kết.
- Dùng `IanaLinkRelations` cho các relation chuẩn như `SELF`, `NEXT`, `PREV`, `FIRST` và `LAST`.
- Dùng `LinkRelation.of(...)` cho relation mở rộng và so sánh relation thay vì phân tích title hoặc path.
- `RepresentationModel.hasLink(...)`, `getLink(...)` và `getRequiredLink(...)` giúp kiểm tra link theo relation.
- `CollectionModel` có relation cấp collection và có thể chứa các item mang link riêng.
- Trong HAL, relation xuất hiện dưới dạng khóa trong `_links`; `_embedded` relation là tên của phần tử nhúng và có vai trò khác.
- Kiểm thử cả relation tồn tại và không tồn tại theo trạng thái, đồng thời xác minh `href` khi hợp đồng yêu cầu.
- Giữ relation ổn định để client có thể tiến hóa cùng API mà không phụ thuộc cấu trúc URL nội bộ.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – LinkRelation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
- [Spring HATEOAS API – IanaLinkRelations](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [Spring HATEOAS API – RepresentationModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/RepresentationModel.html)
- [IANA – Link Relations](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
