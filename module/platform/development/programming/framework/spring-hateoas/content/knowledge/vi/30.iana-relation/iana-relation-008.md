# Relation about

Một bài đánh giá sản phẩm có thể được công bố như một resource riêng. Client đọc bài đánh giá cần biết sản phẩm nào là đối tượng được đánh giá. Representation của bài đánh giá có thể chứa link với relation `about` trỏ đến resource sản phẩm. Link này diễn đạt rằng sản phẩm là chủ đề của bài đánh giá.

`about` là một link relation được đăng ký trong IANA Link Relations Registry và được định nghĩa tại RFC 6903. Relation này dùng khi target là chủ đề hoặc đối tượng mà resource context nói đến. Trong Spring HATEOAS, hằng `IanaLinkRelations.ABOUT` giúp tạo link với relation chuẩn mà không phải viết chuỗi `"about"` ở nhiều nơi.

## Ý nghĩa của relation about

IANA định nghĩa `about` là quan hệ trỏ đến resource là chủ đề của link context. RFC 6903 minh họa bằng một review có link `about` đến sản phẩm được review. Một context có thể có nhiều chủ đề; khi đó có thể công bố nhiều link cùng relation `about`.

Hãy phân biệt ba thành phần của link:

- **Context:** resource đang chứa hoặc phát ra link, ví dụ bài đánh giá `review-42`.
- **Relation:** ý nghĩa quan hệ giữa context và target, ở đây là `about`.
- **Target:** resource là chủ đề của context, ví dụ sản phẩm `sku-73`.

```text
Review resource (context)
    |
    | rel="about"
    v
Product resource (subject / target)
```

Điểm cần nhớ là hướng liên kết. Nếu một review nói về một sản phẩm, link `about` được đặt trên representation của review và trỏ đến sản phẩm. Relation này không có nghĩa “resource đích mô tả context”; ý nghĩa đó gần với `describedby`.

## Ví dụ HTTP Link header

RFC 6903 minh họa `about` bằng HTTP `Link` header:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Link: <https://shop.example.com/api/products/sku-73>; rel="about"

{
  "id": "review-42",
  "rating": 5,
  "comment": "Chất lượng tốt và giao hàng nhanh."
}
```

Trong ví dụ, context là representation của review; target là resource sản phẩm. Client có thể theo target để tìm hiểu đối tượng mà review đề cập.

RFC 8288 mô hình hóa link như một kết nối có context, relation type, target và các target attributes tùy chọn. `about` xác định ngữ nghĩa của kết nối; URI trong `href` hoặc `Link` header xác định target cụ thể.

## Biểu diễn about trong HAL

Với HAL, link relation nằm trong `_links`. Representation của review có thể như sau:

```json
{
  "id": "review-42",
  "rating": 5,
  "comment": "Chất lượng tốt và giao hàng nhanh.",
  "_links": {
    "self": {
      "href": "https://shop.example.com/api/reviews/review-42"
    },
    "about": {
      "href": "https://shop.example.com/api/products/sku-73"
    }
  }
}
```

Ở đây:

- `self` trỏ đến chính review.
- `about` trỏ đến sản phẩm là chủ đề của review.
- `rating` và `comment` là dữ liệu của review, không phải link relation.

Một resource có thể có nhiều chủ đề. HAL cho phép biểu diễn nhiều link cùng relation dưới dạng mảng:

```json
{
  "id": "article-18",
  "title": "Đánh giá trải nghiệm mua sắm mùa hè",
  "_links": {
    "self": {
      "href": "https://shop.example.com/api/articles/article-18"
    },
    "about": [
      {
        "href": "https://shop.example.com/api/products/sku-73"
      },
      {
        "href": "https://shop.example.com/api/campaigns/summer-2026"
      }
    ]
  }
}
```

Hai link `about` cho biết bài viết có hai chủ đề: sản phẩm và chiến dịch. RFC 6903 cho phép nhiều `about` links để chỉ ra nhiều subjects. Client nên xử lý relation có thể xuất hiện dưới dạng một link hoặc nhiều link.

## Phân biệt about với các relation gần nghĩa

Không nên dùng `about` cho mọi resource có liên quan. Hãy chọn relation theo ý nghĩa thực tế giữa context và target.

| Relation | Ý nghĩa | Ví dụ target khi context là một review |
| --- | --- | --- |
| `about` | Chủ đề hoặc đối tượng mà context nói đến | Sản phẩm được đánh giá. |
| `related` | Một resource có liên quan nói chung | Một bài đánh giá khác hoặc nội dung liên quan. |
| `describedby` | Resource cung cấp thông tin mô tả context | Tài liệu giải thích cấu trúc review hoặc schema. |
| `profile` | Profile mà representation context tuân theo | Tài liệu profile mô tả semantics của representation review. |
| `type` | Resource xác định kiểu ngữ nghĩa trừu tượng của context | Tài liệu định nghĩa loại resource `ProductReview`. |
| `self` | Chính resource context | URI của review hiện tại. |

Ví dụ, nếu một bài viết nói về sản phẩm A, link `about` đến sản phẩm A. Nếu link dẫn đến tài liệu hướng dẫn cách đọc cấu trúc bài viết, dùng `describedby`. Nếu link dẫn đến một bài viết khác chỉ vì nội dung có liên quan, `related` phù hợp hơn.

## Khi nào nên dùng about?

`about` phù hợp khi client cần khám phá đối tượng hoặc chủ đề mà resource hiện tại đề cập. Một số trường hợp:

- Review trỏ đến sản phẩm được đánh giá.
- Bài viết trỏ đến các chủ đề hoặc thực thể được đề cập.
- Báo cáo trỏ đến dự án, khách hàng hoặc đơn vị là đối tượng phân tích.
- Bản tin trỏ đến sự kiện mà nội dung đang nói đến.
- Biên bản cuộc họp trỏ đến dự án hoặc quyết định được thảo luận.

Không cần thêm `about` chỉ vì hai resource có quan hệ trong database. Hãy hỏi: “Resource hiện tại đang nói về đối tượng nào mà client cần khám phá?” Nếu câu trả lời không rõ ràng, một relation chuyên biệt hoặc `related` có thể diễn đạt đúng hơn.

## Dùng IanaLinkRelations.ABOUT trong Spring HATEOAS

Spring HATEOAS cung cấp `IanaLinkRelations.ABOUT` với kiểu `LinkRelation`. Dùng hằng này để biểu diễn relation chuẩn:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class ReviewModelAssembler
        implements RepresentationModelAssembler<Review, EntityModel<ReviewView>> {

    @Override
    public EntityModel<ReviewView> toModel(Review review) {
        ReviewView view = ReviewView.from(review);

        EntityModel<ReviewView> model = EntityModel.of(view,
            linkTo(methodOn(ReviewController.class).one(review.getId()))
                .withSelfRel());

        model.add(linkTo(methodOn(ProductController.class)
            .one(review.getProductId()))
            .withRel(IanaLinkRelations.ABOUT));

        return model;
    }
}
```

Ví dụ giả định `ReviewView.from(...)` chuyển domain object thành DTO, `Review` có `getProductId()` và `ProductController.one(...)` là endpoint đọc sản phẩm. `methodOn(...)` ghi nhận mapping controller để xây URI; nó không gọi nghiệp vụ của controller.

Đoạn `withRel(IanaLinkRelations.ABOUT)` đặt relation chuẩn `about` lên link trỏ đến sản phẩm. Khi serialize representation bằng HAL, link xuất hiện trong `_links.about`.

## Công bố nhiều chủ đề

Một resource có thể đề cập nhiều subjects. Có thể thêm nhiều link cùng relation `about` vào model:

```java
model.add(linkTo(methodOn(ProductController.class)
    .one(review.getProductId()))
    .withRel(IanaLinkRelations.ABOUT));

if (review.getCampaignId() != null) {
    model.add(linkTo(methodOn(CampaignController.class)
        .one(review.getCampaignId()))
        .withRel(IanaLinkRelations.ABOUT));
}
```

Khi có nhiều link cùng relation, serializer HAL có thể biểu diễn chúng dưới dạng mảng. Nếu association là tùy chọn, chỉ thêm link khi có target hợp lệ. Không tạo `href` rỗng hoặc URI giả để lấp chỗ cho subject chưa xác định.

Không nên dùng nhiều `about` links để mô tả các thao tác khác nhau. Relation này mô tả subjects của context, không phải action. Ví dụ `edit`, `reply` hoặc `cancel` cần relation thể hiện hành động tương ứng.

## Tạo link about bằng URI đã biết

Nếu target là URI ngoài ứng dụng hoặc URI đã được cung cấp bởi một hệ thống khác, có thể tạo `Link` trực tiếp:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

EntityModel<ReviewView> model = EntityModel.of(view);

model.add(Link.of(
    "https://catalog.example.com/products/sku-73",
    IanaLinkRelations.ABOUT));
```

`Link.of(String, LinkRelation)` tạo link từ URI và relation. Dùng `WebMvcLinkBuilder` khi target là endpoint Spring MVC trong ứng dụng; dùng `Link.of(...)` khi URI đã có sẵn hoặc thuộc một dịch vụ khác. Trong cả hai trường hợp, target phải xác định đúng subject của context.

Nếu URI target đến từ dữ liệu người dùng hoặc hệ thống ngoài, hãy xác thực nguồn và scheme được phép. Không tạo link tùy ý từ chuỗi chưa kiểm tra vì client có thể theo link đến host không mong muốn.

## About không phải embedded resource

Link `about` chỉ công bố URI của subject. Nó không nhúng representation của subject vào response.

Ví dụ:

```json
{
  "id": "review-42",
  "_links": {
    "about": {
      "href": "/api/products/sku-73"
    }
  }
}
```

Client cần theo link nếu muốn lấy representation sản phẩm. Nếu API muốn nhúng một projection của sản phẩm, hãy dùng cấu trúc `_embedded` với relation phù hợp và có thể đồng thời cung cấp link `about` đến canonical product resource.

Không nhầm tên relation `about` trong `_links` với embedded relation trong `_embedded`. Hai phần có vai trò khác nhau: `_links` diễn đạt điều hướng và quan hệ; `_embedded` chứa representation của resource liên quan.

## About và chiều liên kết

Relation `about` có ngữ nghĩa theo hướng context đến subject. Ví dụ:

```text
Review ──about──> Product
```

Không tự động đảo chiều thành:

```text
Product ──about──> Review
```

Trong representation sản phẩm, review có thể là một tài nguyên liên quan hoặc collection reviews. API có thể dùng relation `reviews` hoặc `related` tùy semantics đã công bố. `about` trên sản phẩm chỉ phù hợp nếu review thực sự là chủ đề mà representation sản phẩm nói đến, không chỉ vì review tham chiếu sản phẩm.

## Bảo mật và khả năng truy cập target

Một link `about` có thể tiết lộ chủ đề của resource context. Ví dụ, link từ báo cáo nội bộ đến khách hàng hoặc dự án có thể tiết lộ sự tồn tại của thực thể đó.

Trước khi công bố link, hãy xem xét:

- Người dùng hiện tại có được phép biết subject này tồn tại không.
- Target có nằm trong tenant hoặc phạm vi dữ liệu của người dùng không.
- URI có chứa thông tin nhạy cảm hoặc token truy cập không.
- Endpoint target có tự thực hiện authorization khi được gọi không.
- Cache có thể làm lộ link của một người dùng cho người dùng khác không.

Việc xuất hiện link không cấp quyền truy cập. Client có thể gọi target trực tiếp, vì vậy endpoint target vẫn phải xác thực và phân quyền độc lập. Nếu subject không được phép tiết lộ, hãy bỏ link khỏi representation theo chính sách API.

## Kiểm thử relation about

Kiểm thử nên xác nhận relation đúng, URI target đúng và số lượng link phản ánh số subject được công bố.

### Unit test assembler

```java
EntityModel<ReviewView> model = assembler.toModel(review);

assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue();
assertThat(model.hasLink(IanaLinkRelations.ABOUT)).isTrue();
assertThat(model.getLinks(IanaLinkRelations.ABOUT)).hasSize(1);
```

Test này giả định review có một product subject. Với review có thêm campaign subject, kiểm tra số link `about` là `2` và xác nhận cả hai target.

### Kiểm tra HAL response

```java
mockMvc.perform(get("/api/reviews/{id}", reviewId)
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.about.href")
        .value(org.hamcrest.Matchers.endsWith(
            "/api/products/" + productId)));
```

Test này giả định chỉ có một `about` link nên HAL serialize nó thành object. Nếu có nhiều subjects, kiểm tra `_links.about` dưới dạng array và xác nhận từng `href`.

### Kiểm tra nhiều subjects và quyền

Nên có test cho các trường hợp:

- Review có product và campaign: có hai `about` links.
- Review không có campaign: chỉ có link đến product.
- Subject bị ẩn theo quyền: response không công bố link đó.
- Client gọi target không có quyền: endpoint target từ chối theo chính sách authorization.
- URI target được tạo đúng khi chạy sau context path hoặc reverse proxy.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `about` cho mọi resource có liên quan | Client không phân biệt chủ đề với quan hệ liên quan chung. | Chỉ dùng khi target là subject/topic của context. |
| Đảo chiều context và target | Link diễn đạt sai resource nào đang nói về resource nào. | Đặt `about` trên resource context và trỏ đến subject. |
| Dùng `about` để trỏ đến tài liệu schema | Client hiểu nhầm tài liệu mô tả là chủ đề của resource. | Dùng `describedby` cho resource cung cấp mô tả. |
| Dùng `about` như action link | Client không biết đây là subject hay thao tác cần thực hiện. | Dùng relation hành động phù hợp như `edit` hoặc relation riêng đã công bố. |
| Cho rằng `about` tự nhúng target | Client không có representation target trong response. | Theo `href` hoặc thêm embedded projection riêng. |
| Chỉ hỗ trợ một subject | Bỏ sót các chủ đề khác mà context đề cập. | Thêm nhiều link cùng relation `about` khi cần. |
| Công bố subject nhạy cảm | Response làm lộ quan hệ hoặc dữ liệu ngoài quyền. | Áp dụng authorization trước khi tạo link và tại endpoint đích. |
| Dùng chuỗi `"about"` rải rác | Dễ sai chính tả hoặc thiếu nhất quán. | Dùng `IanaLinkRelations.ABOUT`. |

## Ghi nhớ

- `about` trỏ đến resource là chủ đề hoặc đối tượng của link context.
- Ngữ nghĩa được định nghĩa trong RFC 6903 và đăng ký trong IANA Link Relations Registry.
- Với review nói về sản phẩm, context là review và target là sản phẩm.
- Một context có thể có nhiều subjects; có thể công bố nhiều link cùng relation `about`.
- Dùng `IanaLinkRelations.ABOUT` và `withRel(...)` trong Spring HATEOAS.
- `about` khác `related`, `describedby`, `profile`, `type` và `self`.
- `about` chỉ tạo link, không tự nhúng representation target.
- Link không cấp quyền truy cập; bảo vệ target và cân nhắc thông tin subject bị tiết lộ.
- Kiểm thử relation, target URI, nhiều subjects, trường hợp tùy chọn và authorization.

## Tài liệu tham khảo

- [IANA Link Relations Registry – about](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
- [RFC 6903 – Additional Link Relation Types, Section 2](https://www.rfc-editor.org/rfc/rfc6903.html#section-2)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [Spring HATEOAS API – IanaLinkRelations](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [Spring HATEOAS API – LinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/LinkBuilder.html)
- [Spring HATEOAS API – Link](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
