# links và các snippet hypermedia

## 1. Hypermedia trong REST API

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Snippets mặc định**, các bài kiểm thử HTTP không chỉ ghi lại request và response mà còn có thể kiểm tra liên kết điều hướng mà server trả về. Với API theo hướng hypermedia, response chứa dữ liệu tài nguyên cùng các link relation cho biết client có thể đi tiếp tới đâu hoặc thực hiện hành động nào.

Spring REST Docs cung cấp descriptor links(...) để mô tả link relation trong response. Khi test ghi operation bằng document(...) và truyền link descriptor, REST Docs tạo snippet links.adoc.

Ví dụ HAL JSON:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "_links": {
    "self": {"href": "https://api.example.test/products/42"},
    "orders": {"href": "https://api.example.test/products/42/orders"}
  }
}
```

Trong ví dụ, self là relation trỏ tới tài nguyên hiện tại; orders dẫn tới danh sách đơn hàng liên quan; href là URI đích mà server cung cấp; _links là nơi HAL đặt các link trong JSON representation.

Link relation và href có ý nghĩa khác nhau. Relation mô tả quan hệ hoặc khả năng; href là địa chỉ để client điều hướng. Client nên đọc relation thay vì tự ghép URL theo một quy ước path cố định.

## 2. Snippet links.adoc

### 2.1. Descriptor cơ bản

Dùng linkWithRel(...) để định danh relation và description(...) để giải thích:

```java
links(
    linkWithRel("self")
        .description("Liên kết tới sản phẩm hiện tại"),
    linkWithRel("orders")
        .description("Danh sách đơn hàng của sản phẩm")
)
```

Snippet được sinh dưới operation folder, ví dụ:

```text
build/generated-snippets/products-find/links.adoc
```

Bảng link thường hiển thị relation, mô tả và URI/template được trích từ response. Người đọc biết API cung cấp link nào mà không phải đọc thủ công toàn bộ HAL payload.

### 2.2. Relation chuẩn và relation tùy chỉnh

| Relation | Ý nghĩa thường gặp |
| --- | --- |
| self | Tài nguyên hiện tại |
| next | Trang tiếp theo trong collection |
| prev / previous | Trang trước |
| first | Trang đầu tiên |
| last | Trang cuối cùng |
| item | Một item trong collection |
| collection | Collection chứa tài nguyên |
| create | Link tới thao tác tạo tài nguyên nếu API dùng relation này |

API cũng có thể dùng relation tùy chỉnh theo domain, ví dụ orders, cancel, approve hoặc download. Đặt tên relation nhất quán và mô tả chính xác hành động client có thể thực hiện. Không suy ra ý nghĩa của relation chỉ từ URL.

## 3. Ví dụ HAL với MockMvc

### 3.1. Response mẫu

Giả sử endpoint trả chi tiết sản phẩm cùng hai relation:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "_links": {
    "self": {"href": "/api/products/42"},
    "orders": {"href": "/api/products/42/orders"}
  }
}
```

### 3.2. Test và link descriptor

Ví dụ dùng Spring MVC, MockMvc và REST Docs:

```java
@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductHypermediaDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void findProduct() throws Exception {
        mockMvc.perform(
                RestDocumentationRequestBuilders
                    .get("/api/products/{id}", 42)
                    .accept(MediaTypes.HAL_JSON)
            )
            .andExpect(status().isOk())
            .andDo(document("products-find",
                links(
                    linkWithRel("self")
                        .description("Liên kết tới sản phẩm hiện tại"),
                    linkWithRel("orders")
                        .description("Danh sách đơn hàng của sản phẩm")
                )
            ));
    }
}
```

Import tĩnh thường dùng:

```java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
```

Ví dụ sử dụng MediaTypes.HAL_JSON để request HAL representation. Controller phải thực sự trả đúng content type và cấu trúc link tương ứng; nếu response không chứa cấu trúc HAL phù hợp, link extraction có thể thất bại.

### 3.3. Kết quả output

Với operation ID products-find, cấu trúc snippet có thể gồm:

```text
build/generated-snippets/
  products-find/
    http-request.adoc
    http-response.adoc
    response-body.adoc
    links.adoc
```

Các snippet HTTP cơ bản được tạo cùng operation; links.adoc được thêm khi test khai báo descriptor links(...). Thư mục con lấy từ operation ID, còn thư mục gốc theo REST Docs/Spring Boot hoặc cấu hình outputDir.

## 4. Link optional, ignored và relaxed

### 4.1. Link optional

Một relation có thể không xuất hiện trong mọi response. Ví dụ chỉ sản phẩm còn hàng mới có link purchase:

```java
links(
    linkWithRel("self").description("Sản phẩm hiện tại"),
    linkWithRel("purchase")
        .description("Mua sản phẩm")
        .optional()
)
```

optional() cho biết relation được phép vắng mặt. Nếu API yêu cầu link phải có trong mọi response thì không đánh dấu optional; test cần phát hiện khi server làm mất link bắt buộc.

### 4.2. Link ignored

HAL response có thể chứa relation hạ tầng như curies hoặc link mà trang tài liệu hiện tại không cần trình bày. Dùng ignored() để loại relation đó khỏi bảng:

```java
links(
    linkWithRel("self").description("Sản phẩm hiện tại"),
    linkWithRel("curies").ignored()
)
```

Ignored khác optional: optional cho phép link vắng mặt nhưng vẫn mô tả khi xuất hiện; ignored loại link khỏi snippet và bỏ qua kiểm tra mô tả đối với relation đó.

### 4.3. Relaxed links

Ở strict mode, relation có trong response nhưng không có descriptor có thể làm test thất bại. Điều này giúp phát hiện server thêm hoặc đổi link mà tài liệu chưa đề cập.

Nếu test chỉ muốn mô tả một phần link, dùng relaxedLinks(...):

```java
relaxedLinks(
    linkWithRel("self")
        .description("Sản phẩm hiện tại")
)
```

relaxedLinks(...) bỏ qua relation không được mô tả. Dùng cho tài liệu có phạm vi hẹp hoặc khi phần link khác được mô tả ở nơi khác; không nên dùng mặc định cho mọi operation vì API có thể thay đổi link mà test không còn cảnh báo.

## 5. URI template và CURIE

### 5.1. URI template

Một link có thể chứa URI template:

```json
{
  "_links": {
    "search": {
      "href": "/api/products{?category,page,size}",
      "templated": true
    }
  }
}
```

Client cần biết đây là link template và điền biến phù hợp thay vì gọi nguyên chuỗi như URL hoàn chỉnh. Trong tài liệu, giữ đúng dấu hiệu template và giải thích ý nghĩa biến nếu cần.

### 5.2. CURIE trong HAL

HAL có thể khai báo CURIE để rút gọn custom relation:

```json
{
  "_links": {
    "curies": [
      {
        "name": "ex",
        "href": "https://docs.example.test/rels/{rel}",
        "templated": true
      }
    ],
    "self": {"href": "/api/products/42"},
    "ex:reviews": {"href": "/api/products/42/reviews"}
  }
}
```

Relation ex:reviews có prefix ex, được khai báo trong CURIE curies. Có thể mô tả custom relation:

```java
links(
    linkWithRel("self").description("Sản phẩm hiện tại"),
    linkWithRel("ex:reviews").description("Đánh giá sản phẩm"),
    linkWithRel("curies").ignored()
)
```

CURIE định nghĩa cách mở rộng tên relation; link ex:reviews mới là relation gắn với khả năng xem đánh giá.

## 6. Hypermedia format và LinkExtractor

Spring REST Docs trích link từ response bằng LinkExtractor phù hợp với hypermedia format. Các cấu hình phổ biến gồm HAL và Atom. Nếu response không dùng định dạng mà extractor nhận diện được, link snippet có thể không được tạo đúng.

Các điểm cần kiểm tra:

- Response Content-Type phù hợp với representation, ví dụ application/hal+json cho HAL JSON.
- JSON có cấu trúc link đúng chuẩn, ví dụ HAL dùng _links.
- Test sử dụng đúng hypermedia module/API và extractor cho format đang dùng.
- Relation name trong descriptor khớp với relation server trả về.
- Link có thể templated, optional hoặc chia theo CURIE; mô tả đúng đặc điểm đó.

Nếu ứng dụng dùng format tùy chỉnh, cấu hình LinkExtractor phù hợp cho REST Docs thay vì giả định HAL extractor đọc được mọi JSON có trường links.

## 7. Kết hợp link snippet với payload fields

Link snippet mô tả điều hướng, còn payload field snippet mô tả dữ liệu tài nguyên. Một tài liệu chi tiết có thể cần cả hai:

```java
document("products-find",
    links(
        linkWithRel("self").description("Sản phẩm hiện tại"),
        linkWithRel("orders").description("Đơn hàng liên quan")
    ),
    responseFields(
        fieldWithPath("id").description("Mã sản phẩm"),
        fieldWithPath("name").description("Tên sản phẩm")
    )
)
```

Với HAL, _links là phần link của representation. Dùng link descriptor để mô tả relation và field descriptor cho dữ liệu tài nguyên; không xem URL href như một field nghiệp vụ thông thường.

## 8. Include links.adoc trong Asciidoctor

Trong file src/docs/asciidoc/products.adoc:

```asciidoc
= Products API
:toc: left

== Tìm sản phẩm

=== Hypermedia links
include::{snippets}/products-find/links.adoc[]

=== Response
include::{snippets}/products-find/http-response.adoc[]

=== Response fields
include::{snippets}/products-find/response-fields.adoc[]
```

Attribute snippets phải trỏ tới thư mục gốc snippet. Đường dẫn phía sau cần khớp operation ID. Nếu test dùng outputDir riêng, cập nhật attribute trong build.

Không include links.adoc cho operation chưa khai báo links(...) hoặc response không có link phù hợp. Nếu include file không tồn tại, Asciidoctor sẽ báo lỗi khi biên soạn tài liệu.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không sinh links.adoc | Operation chưa gọi links(...) hoặc test không chạy tới document. | Kiểm tra test report và link descriptor. |
| Link extractor không tìm thấy link | Sai Content-Type, cấu trúc HAL sai hoặc extractor không phù hợp. | Kiểm tra response representation và LinkExtractor. |
| Strict mode báo undocumented link | Response có relation chưa khai báo. | Bổ sung descriptor, ignore có chủ đích hoặc dùng relaxedLinks khi phù hợp. |
| Test báo thiếu relation bắt buộc | Descriptor không optional nhưng response không có link. | Sửa server hoặc đánh dấu optional nếu hợp đồng cho phép. |
| Không nhận custom relation | Sai relation name hoặc nhầm CURIE prefix. | Đối chiếu key trong _links và CURIE declaration. |
| URL template bị hiểu như URL cố định | Bỏ qua thuộc tính templated hoặc không giải thích biến. | Giữ URI template và mô tả cách client điền biến. |
| Asciidoctor không tìm thấy links.adoc | Sai operation ID, outputDir hoặc include path. | Đối chiếu file thực tế dưới generated snippets. |
| Payload fields và links bị lẫn | Dùng field descriptor thay cho hypermedia descriptor. | Dùng links(...) cho relation, field descriptor cho dữ liệu tài nguyên. |

## 10. Bài thực hành

Tạo API Catalog trả HAL JSON:

1. GET /api/products/{id} trả thông tin sản phẩm và link self, orders.
2. GET /api/products trả collection với link self, next, prev khi phù hợp.
3. Thêm relation tùy chỉnh ex:reviews cùng CURIE ex.
4. Viết MockMvc test và dùng links(...) để mô tả các relation.
5. Đánh dấu next optional ở trang cuối; đánh dấu curies ignored nếu không cần trình bày.
6. Dùng một test strict để phát hiện relation mới chưa mô tả; dùng relaxedLinks trong test chỉ tập trung vào self.
7. Include links.adoc và http-response.adoc vào Asciidoctor, chạy clean test và dựng tài liệu.

**Tiêu chí hoàn thành:** phân biệt relation với href; giải thích HAL _links, URI template và CURIE; tạo links.adoc bằng descriptor; dùng đúng optional/ignored/relaxed; tài liệu được ghép từ snippet do test sinh ra.

## 11. Tài liệu tham khảo

- [Spring REST Docs — Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs — HypermediaDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/HypermediaDocumentation.html)
- [Spring REST Docs — LinksSnippet API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/LinksSnippet.html)
- [HAL Specification](https://stateless.group/hal_specification.html)
- [IANA — Link Relations](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
