# Tái sử dụng link descriptors

## 1. Vì sao cần tái sử dụng link descriptors?

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Tái sử dụng**, các bài kiểm thử HTTP ghi lại response và các liên kết hypermedia mà server cung cấp. Nhiều tài nguyên có thể chia sẻ relation quen thuộc như self, profile, collection hoặc next. Việc khai báo lặp lại mô tả relation trong từng test làm tài liệu khó duy trì và dễ không nhất quán.

Spring REST Docs dùng LinkDescriptor để mô tả link. Các descriptor được truyền vào links(...) để sinh snippet links.adoc và kiểm tra relation có trong response. Có thể tổ chức relation dùng chung thành factory method, rồi ghép thêm relation riêng cho từng resource hoặc operation.

Ví dụ HAL:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "_links": {
    "self": {"href": "/api/products/42"},
    "profile": {"href": "/api/profiles/product"},
    "orders": {"href": "/api/products/42/orders"}
  }
}
```

Relation mô tả quan hệ hoặc khả năng; href là URI đích mà server cung cấp. Client nên dựa vào relation để tìm khả năng cần dùng, không tự ghép URL theo một quy ước path cố định.

Sau bài học, bạn có thể tạo LinkDescriptor dùng chung, ghép relation chung với relation riêng, xử lý optional/ignored/relaxed links và giữ strict validation để phát hiện relation mới hoặc bị thiếu.

Ví dụ dùng **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter và MockMvc**. Với WebTestClient hoặc REST Assured, cách gửi HTTP khác nhưng helper descriptor hypermedia vẫn có thể được tổ chức dùng chung.

## 2. LinkDescriptor và links(...)

Descriptor cơ bản:

```java
links(
    linkWithRel("self")
        .description("Liên kết tới tài nguyên hiện tại"),
    linkWithRel("profile")
        .description("Mô tả cấu trúc tài nguyên"),
    linkWithRel("orders")
        .description("Danh sách đơn hàng của sản phẩm")
)
```

linkWithRel(...) tạo descriptor cho relation. description(...) giải thích ý nghĩa của relation đối với client. links(...) đưa các descriptor vào operation documentation, tạo links.adoc và kiểm tra response theo descriptor.

Một số relation thường gặp:

| Relation | Ý nghĩa |
| --- | --- |
| self | Tài nguyên hiện tại |
| profile | Mô tả cấu trúc representation |
| collection | Collection chứa tài nguyên |
| item | Một item trong collection |
| next / prev | Trang kế tiếp / trang trước |
| first / last | Trang đầu / trang cuối |

API cũng có thể dùng relation tùy chỉnh theo domain như orders, customer, cancel, approve hoặc download. Mô tả phải phản ánh hành động thực tế; không suy ra ý nghĩa relation chỉ từ URL.

## 3. Tạo factory cho relation dùng chung

Nếu nhiều tài nguyên có self và profile với cùng ý nghĩa, tạo helper trong test source set:

```java
package com.example.catalog.docs;

import java.util.List;
import org.springframework.restdocs.hypermedia.LinkDescriptor;

import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;

public final class CommonLinkDescriptors {
    private CommonLinkDescriptors() {}

    public static List<LinkDescriptor> resourceLinks() {
        return List.of(
            linkWithRel("self")
                .description("Liên kết tới tài nguyên hiện tại"),
            linkWithRel("profile")
                .description("Mô tả cấu trúc tài nguyên")
        );
    }
}
```

Dùng trong operation:

```java
document("products-find",
    links(CommonLinkDescriptors.resourceLinks())
)
```

Factory method tạo descriptor mới mỗi lần gọi. List.of(...) không cho thêm hoặc xóa phần tử, thuận tiện để giữ cấu trúc nhóm relation ổn định.

### Hằng số hay factory?

Hằng số descriptor chỉ phù hợp khi relation luôn có cùng mô tả và trạng thái ở tất cả operation. LinkDescriptor có các phương thức cấu hình như optional() và ignored(). Không nên chia sẻ instance static rồi thay đổi trạng thái trong từng test. Factory mới phù hợp khi cùng relation bắt buộc ở operation này nhưng optional ở operation khác.

## 4. Ghép relation chung với relation riêng

Endpoint sản phẩm có relation orders; endpoint đơn hàng có customer và cancel. Cả hai đều có self/profile:

```java
static List<LinkDescriptor> productLinks() {
    List<LinkDescriptor> descriptors =
        new ArrayList<>(CommonLinkDescriptors.resourceLinks());
    descriptors.add(
        linkWithRel("orders")
            .description("Danh sách đơn hàng của sản phẩm")
    );
    return descriptors;
}

static List<LinkDescriptor> orderLinks() {
    List<LinkDescriptor> descriptors =
        new ArrayList<>(CommonLinkDescriptors.resourceLinks());
    descriptors.add(
        linkWithRel("customer")
            .description("Khách hàng đã đặt đơn hàng")
    );
    descriptors.add(
        linkWithRel("cancel")
            .description("Hủy đơn hàng nếu trạng thái cho phép")
    );
    return descriptors;
}
```

Dùng:

```java
document("products-find", links(productLinks()));
document("orders-find", links(orderLinks()));
```

Factory giữ relation chung ở một nơi nhưng mô tả relation nghiệp vụ tại đúng resource. Không gom mọi relation của mọi tài nguyên vào một danh sách khổng lồ rồi dùng cho mọi operation; response sẽ bị yêu cầu cung cấp link không thuộc nó.

## 5. Relation cho collection và pagination

Collection thường có link điều hướng trang:

```json
{
  "_embedded": {
    "products": [
      {"id": 42, "name": "Keyboard"},
      {"id": 43, "name": "Mouse"}
    ]
  },
  "_links": {
    "self": {"href": "/api/products?page=0"},
    "next": {"href": "/api/products?page=1"},
    "profile": {"href": "/api/profiles/product-collection"}
  },
  "page": {"size": 20, "number": 0, "totalElements": 45}
}
```

Factory cho collection:

```java
static List<LinkDescriptor> collectionLinks() {
    return List.of(
        linkWithRel("self").description("Trang collection hiện tại"),
        linkWithRel("profile").description("Mô tả cấu trúc collection"),
        linkWithRel("next").description("Trang tiếp theo").optional(),
        linkWithRel("prev").description("Trang trước").optional()
    );
}
```

next có thể vắng ở trang cuối và prev có thể vắng ở trang đầu. Descriptor optional phản ánh điều kiện này. Không đánh dấu mọi relation optional nếu hợp đồng yêu cầu chúng luôn hiện diện; giữ self bắt buộc giúp test phát hiện response thiếu link chính.

## 6. Optional, ignored và relaxed links

| Cách dùng | Ý nghĩa |
| --- | --- |
| Mặc định | Relation được mô tả và kỳ vọng xuất hiện |
| optional() | Relation có thể vắng mặt; nếu xuất hiện vẫn được mô tả |
| ignored() | Relation không được đưa vào bảng và được bỏ qua trong kiểm tra descriptor |
| relaxedLinks(...) | Cho phép response có thêm relation ngoài descriptor |

Không tạo một relation dùng chung rồi ở test A gọi optional(), trong khi test B muốn relation bắt buộc. Tạo factory theo ngữ cảnh:

```java
static LinkDescriptor requiredSelfLink() {
    return linkWithRel("self")
        .description("Liên kết tới tài nguyên hiện tại");
}

static LinkDescriptor optionalNextLink() {
    return linkWithRel("next")
        .description("Trang tiếp theo")
        .optional();
}

static LinkDescriptor requiredNextLink() {
    return linkWithRel("next")
        .description("Trang tiếp theo");
}
```

Strict links giúp phát hiện relation trong response nhưng chưa được mô tả. Nếu test chỉ tập trung vào self trong khi các link phụ được tài liệu hóa ở nơi khác, dùng:

```java
relaxedLinks(
    linkWithRel("self").description("Tài nguyên hiện tại")
)
```

Relaxed mode bỏ qua relation ngoài danh sách descriptor. Không bật mặc định cho mọi operation vì link mới có ý nghĩa nghiệp vụ có thể xuất hiện mà test không cảnh báo nhóm cập nhật tài liệu.

## 7. Relation tùy chỉnh, URI template và CURIE

### Relation tùy chỉnh

```json
{
  "_links": {
    "self": {"href": "/api/orders/9001"},
    "cancel": {"href": "/api/orders/9001/cancellation"},
    "invoice": {"href": "/api/orders/9001/invoice"}
  }
}
```

Mô tả theo nghiệp vụ:

```java
static List<LinkDescriptor> orderActionLinks() {
    return List.of(
        linkWithRel("self").description("Đơn hàng hiện tại"),
        linkWithRel("cancel").description("Hủy đơn hàng"),
        linkWithRel("invoice").description("Lấy hóa đơn của đơn hàng")
    );
}
```

Nếu cancel chỉ được trả khi đơn chưa giao, tài liệu nên nêu điều kiện này hoặc mô tả response variant tương ứng.

### URI template

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

Đây là URI template, không phải URL hoàn chỉnh để gọi nguyên văn. Relation search chỉ ra khả năng tìm kiếm; templated: true cho biết client cần điền biến. Khi tái sử dụng descriptor, không bỏ qua khác biệt giữa relation thường và relation trỏ tới URI template.

### CURIE trong HAL

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

Có thể mô tả custom relation và bỏ qua CURIE infrastructure link nếu trang không cần trình bày:

```java
static List<LinkDescriptor> productHypermediaLinks() {
    return List.of(
        linkWithRel("self").description("Sản phẩm hiện tại"),
        linkWithRel("ex:reviews").description("Đánh giá sản phẩm"),
        linkWithRel("curies").ignored()
    );
}
```

ex:reviews là relation tùy chỉnh; curies định nghĩa cách mở rộng prefix ex. Không dùng CURIE thay cho relation đích.

## 8. Ví dụ MockMvc dùng chung link descriptors

Ví dụ test cho hai response HAL:

```java
@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class HypermediaDocumentationTest {

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
                links(productLinks())
            ));
    }

    @Test
    void findOrder() throws Exception {
        mockMvc.perform(
                RestDocumentationRequestBuilders
                    .get("/api/orders/{id}", 9001)
                    .accept(MediaTypes.HAL_JSON)
            )
            .andExpect(status().isOk())
            .andDo(document("orders-find",
                links(orderLinks())
            ));
    }
}
```

Import tĩnh:

```java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.relaxedLinks;
```

Hai test dùng chung helper cho self/profile nhưng mỗi operation có link riêng. Controller phải trả HAL response với Content-Type và cấu trúc _links phù hợp; nếu dùng hypermedia format khác, cần LinkExtractor tương ứng.

## 9. Tổ chức helper class

Đặt descriptor helper trong test source set:

```text
src/
  test/
    java/
      com/example/api/docs/
        CommonLinkDescriptors.java
        ProductLinkDescriptors.java
        OrderLinkDescriptors.java
        CollectionLinkDescriptors.java
```

Quy ước:

- Tên factory thể hiện nhóm relation, ví dụ resourceLinks(), productLinks() và collectionLinks().
- Chỉ chia sẻ relation khi tên và ý nghĩa thống nhất.
- Tạo descriptor mới nếu trạng thái optional/ignored khác nhau giữa operation.
- Giữ relation nghiệp vụ trong helper của resource tương ứng.
- Tránh một danh sách link toàn cục áp cho mọi response.
- Dùng operation ID riêng cho response variant có hợp đồng link khác nhau.

Chỉ đưa helper vào test-fixture module nếu nhiều module test thực sự cần dùng chung. Không đưa helper tài liệu test vào main source set nếu ứng dụng runtime không cần phụ thuộc Spring REST Docs.

## 10. Include links.adoc trong Asciidoctor

Ví dụ file src/docs/asciidoc/products.adoc:

```asciidoc
= Catalog API
:toc: left

== Tìm sản phẩm

=== Hypermedia links
include::{snippets}/products-find/links.adoc[]

=== HTTP response
include::{snippets}/products-find/http-response.adoc[]

== Tìm đơn hàng

=== Hypermedia links
include::{snippets}/orders-find/links.adoc[]
```

Attribute snippets phải trỏ tới thư mục gốc generated snippets. Đường dẫn phía sau khớp operation ID. Nếu test dùng outputDir riêng, cập nhật attribute trong cấu hình Asciidoctor. Không include links.adoc cho operation chưa khai báo links(...) hoặc response không có link phù hợp.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Relation bị lặp trong bảng | Hai factory cùng tạo một relation. | Kiểm tra danh sách ghép và giữ một nguồn descriptor. |
| Test này làm relation của test khác thành optional | Chia sẻ LinkDescriptor đã cấu hình optional(). | Factory tạo descriptor mới theo operation. |
| Response thiếu link bắt buộc | Server không trả relation đã mô tả. | Sửa implementation hoặc optional nếu contract cho phép. |
| Test báo undocumented link | Strict mode phát hiện relation mới chưa mô tả. | Bổ sung descriptor hoặc relaxed mode có phạm vi rõ. |
| Dùng chung mô tả sai ngữ nghĩa | Relation cùng tên nhưng ý nghĩa khác giữa resource. | Tách factory theo domain/resource. |
| Link template bị xem như URL cố định | Bỏ qua thuộc tính templated hoặc biến trong template. | Mô tả relation và cách client điền biến. |
| CURIE bị mô tả như link nghiệp vụ | Nhầm relation prefix với relation mở rộng. | Mô tả custom relation, ignore CURIE nếu phù hợp. |
| links.adoc không được sinh | Chưa khai báo links(...), test không chạy hoặc sai outputDir. | Kiểm tra operation và thư mục snippet. |
| LinkExtractor không đọc được response | Content-Type/representation không phù hợp. | Kiểm tra HAL/Atom format hoặc extractor riêng. |

## 12. Bài thực hành

Tạo API Catalog trả HAL:

1. GET /api/products/{id} có self, profile và orders.
2. GET /api/orders/{id} có self, profile, customer và cancel.
3. GET /api/products có self, profile, next và prev.
4. Tạo CommonLinkDescriptors cho self/profile; tạo factory riêng cho product, order và collection.
5. Đánh dấu next/prev optional theo trang; giữ self bắt buộc.
6. Tạo một operation strict để phát hiện relation mới và một operation relaxedLinks khi chỉ cần mô tả self.
7. Bổ sung CURIE relation ex:reviews; xác minh descriptor khớp key trong HAL _links.
8. Include links.adoc vào Asciidoctor, chạy clean test và dựng tài liệu.

**Tiêu chí hoàn thành:** tái sử dụng link descriptor mà không lẫn ngữ nghĩa relation; ghép được link chung và riêng; quản lý optional/ignored/relaxed; giải thích relation, href, URI template và CURIE; sinh links.adoc từ test và include đúng operation.

## 13. Tài liệu tham khảo

- [Spring REST Docs — Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs — HypermediaDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/HypermediaDocumentation.html)
- [Spring REST Docs — LinksSnippet API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/LinksSnippet.html)
- [HAL Specification](https://stateless.group/hal_specification.html)
- [IANA — Link Relations](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
