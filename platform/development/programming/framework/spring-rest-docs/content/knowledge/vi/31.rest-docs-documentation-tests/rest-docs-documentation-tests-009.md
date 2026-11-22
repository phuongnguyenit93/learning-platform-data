# Test hypermedia link và quan hệ tài nguyên

## 1. Mục tiêu kiểm thử hypermedia

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Kiểm thử tài liệu**, test HTTP vừa xác minh hành vi endpoint vừa tạo snippet làm tài liệu. Với API hypermedia, response không chỉ chứa dữ liệu tài nguyên mà còn cung cấp link relation để client khám phá tài nguyên liên quan hoặc hành động tiếp theo.

Một test hypermedia cần kiểm tra:

- HTTP status và Content-Type đúng với representation được công bố.
- Response có cấu trúc link đúng định dạng, chẳng hạn HAL JSON dùng _links.
- Relation bắt buộc như self xuất hiện và trỏ tới URI phù hợp.
- Relation nghiệp vụ như orders, cancel hoặc reviews được mô tả rõ.
- Relation tùy chọn chỉ được đánh dấu optional khi contract cho phép vắng mặt.
- Descriptor links(...) khớp response để snippet links.adoc có thể được sinh.

Spring REST Docs dùng LinkExtractor để trích link từ response và LinkDescriptor để mô tả relation. Trong strict mode, relation có trong response nhưng chưa được mô tả có thể làm test thất bại; descriptor bắt buộc nhưng response thiếu relation cũng có thể làm test thất bại. Cơ chế này giúp phát hiện contract drift ở tầng hypermedia.

Ví dụ dùng **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter và MockMvc**. Nguyên tắc kiểm tra tương tự với WebTestClient và REST Assured, dù API gửi request khác nhau.

## 2. HAL response và link relation

Ví dụ response HAL:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "_links": {
    "self": {"href": "https://api.example.test/products/42"},
    "orders": {"href": "https://api.example.test/products/42/orders"},
    "profile": {"href": "https://api.example.test/profiles/product"}
  }
}
```

| Thành phần | Vai trò |
| --- | --- |
| _links | Container chứa các hypermedia link theo HAL |
| self | Relation tới chính tài nguyên hiện tại |
| orders | Relation tới các đơn hàng liên quan |
| profile | Relation tới mô tả profile của representation |
| href | URI đích của link |

Relation mô tả quan hệ hoặc khả năng; href là địa chỉ do server cung cấp. Client nên tìm link theo relation thay vì tự ghép URL từ ID hoặc quy tắc path nội bộ.

## 3. Cấu hình test hypermedia với MockMvc

### 3.1. Dependencies

Ví dụ Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-hateoas'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Spring HATEOAS cung cấp kiểu representation và hỗ trợ tạo HAL link. Spring REST Docs cung cấp integration MockMvc và descriptor cho hypermedia.

### 3.2. Controller minh họa

```java
@RestController
@RequestMapping("/api/products")
class ProductController {
    @GetMapping(path = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    EntityModel<ProductResponse> find(@PathVariable long id) {
        ProductResponse product = new ProductResponse(id, "Mechanical Keyboard");
        return EntityModel.of(product,
            linkTo(methodOn(ProductController.class).find(id)).withSelfRel(),
            linkTo(methodOn(ProductController.class).orders(id)).withRel("orders")
        );
    }

    @GetMapping("/{id}/orders")
    CollectionModel<OrderResponse> orders(@PathVariable long id) {
        return CollectionModel.empty();
    }

    record ProductResponse(long id, String name) {}
    record OrderResponse(long id) {}
}
```

Controller minh họa hai relation self và orders. Ứng dụng thật cần trả collection orders theo dữ liệu phù hợp; fixture test nên ổn định để URI và response có thể kiểm chứng.

## 4. Viết test links(...) và sinh links.adoc

### 4.1. Descriptor relation

```java
links(
    linkWithRel("self").description("Liên kết tới sản phẩm hiện tại"),
    linkWithRel("orders").description("Danh sách đơn hàng của sản phẩm")
)
```

Import tĩnh:

```java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
```

### 4.2. Test hoàn chỉnh

```java
@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductHypermediaDocumentationTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void findProductDocumentsLinks() throws Exception {
        mockMvc.perform(
                RestDocumentationRequestBuilders
                    .get("/api/products/{id}", 42)
                    .accept(MediaTypes.HAL_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href")
                .value(containsString("/api/products/42")))
            .andExpect(jsonPath("$._links.orders.href")
                .value(containsString("/api/products/42/orders")))
            .andDo(document("products-find",
                links(
                    linkWithRel("self").description("Liên kết tới sản phẩm hiện tại"),
                    linkWithRel("orders").description("Danh sách đơn hàng của sản phẩm")
                )
            ));
    }
}
```

Assertion JSONPath kiểm tra link thực tế, còn links(...) kiểm tra và ghi nhận relation vào snippet. Assertion có thể xác minh URI cụ thể; descriptor đảm bảo relation được tài liệu hóa.

### 4.3. Output

Với operation ID products-find, snippet có thể gồm:

```text
build/generated-snippets/
  products-find/
    http-request.adoc
    http-response.adoc
    response-body.adoc
    links.adoc
```

links.adoc được sinh khi operation khai báo links(...). Các snippet HTTP cơ bản phụ thuộc cấu hình và template.

## 5. Strict link validation

Strict mode giúp phát hiện:

1. Response có relation nhưng test chưa mô tả relation đó.
2. Descriptor khai báo relation bắt buộc nhưng response không trả relation.

Ví dụ server bất ngờ thêm relation reviews. Test strict chỉ mô tả self và orders có thể thất bại vì reviews chưa được mô tả. Đây là tín hiệu để nhóm quyết định relation mới có thuộc contract công khai không và cập nhật tài liệu.

Ngược lại, nếu descriptor có cancel nhưng response không có link này, test cũng thất bại. Nếu cancel chỉ được cung cấp khi đơn hàng chưa giao, cần mô tả đúng điều kiện và kiểm tra response variant tương ứng.

### Optional relation

```java
links(
    linkWithRel("self").description("Tài nguyên hiện tại"),
    linkWithRel("next").description("Trang tiếp theo").optional()
)
```

optional() cho phép relation vắng mặt; nếu xuất hiện, relation vẫn được mô tả. Chỉ đánh dấu optional khi hợp đồng cho phép.

### Ignored relation

```java
links(
    linkWithRel("self").description("Tài nguyên hiện tại"),
    linkWithRel("curies").ignored()
)
```

Ignored loại relation khỏi snippet và bỏ qua kiểm tra descriptor đối với relation đó. Không ignore relation nghiệp vụ chỉ để test vượt qua.

### Relaxed links

```java
relaxedLinks(
    linkWithRel("self").description("Tài nguyên hiện tại")
)
```

Relaxed mode bỏ qua các relation chưa được mô tả. Phù hợp với trang tài liệu có phạm vi hẹp khi relation khác được mô tả ở nơi khác. Không dùng relaxed cho mọi operation vì relation mới có thể xuất hiện mà test không yêu cầu cập nhật tài liệu.

## 6. Kiểm thử collection và pagination links

Collection HAL có thể trả self, next, prev, first và last:

```json
{
  "_embedded": {
    "products": [
      {"id": 42, "name": "Keyboard"},
      {"id": 43, "name": "Mouse"}
    ]
  },
  "_links": {
    "self": {"href": "/api/products?page=1"},
    "first": {"href": "/api/products?page=0"},
    "prev": {"href": "/api/products?page=0"},
    "next": {"href": "/api/products?page=2"},
    "last": {"href": "/api/products?page=4"}
  },
  "page": {"size": 2, "number": 1, "totalElements": 10}
}
```

Descriptor:

```java
links(
    linkWithRel("self").description("Trang collection hiện tại"),
    linkWithRel("first").description("Trang đầu tiên"),
    linkWithRel("prev").description("Trang trước").optional(),
    linkWithRel("next").description("Trang tiếp theo").optional(),
    linkWithRel("last").description("Trang cuối cùng")
)
```

Test nên bao gồm trang đầu, trang giữa và trang cuối nếu điều kiện link khác nhau:

| Trường hợp | Link có thể vắng |
| --- | --- |
| Trang đầu | prev |
| Trang giữa | Thường có prev và next |
| Trang cuối | next |
| Collection rỗng hoặc một trang | Tùy contract, có thể không có prev và next |

Không suy luận link chỉ từ số trang nếu server có quy tắc pagination riêng. Kiểm tra response thực tế bằng JSONPath hoặc HAL link matcher, rồi dùng descriptor để tài liệu hóa relation.

## 7. Custom relation, URI template và CURIE

### Custom relation

```java
mockMvc.perform(get("/api/orders/{id}", 9001)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.cancel.href").exists())
    .andDo(document("orders-cancellable",
        links(
            linkWithRel("self").description("Đơn hàng hiện tại"),
            linkWithRel("cancel").description("Hủy đơn hàng")
        )
    ));
```

Một test khác cho đơn đã giao có thể xác minh cancel không tồn tại và dùng descriptor phù hợp với response variant. Nếu API chỉ cung cấp cancel khi được phép, link là tín hiệu capability cho client.

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

Test cần kiểm tra href và thuộc tính templated nếu client phụ thuộc vào template. Đừng coi URI template là URL hoàn chỉnh đã điền biến.

### CURIE

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
    "ex:reviews": {"href": "/api/products/42/reviews"}
  }
}
```

Descriptor:

```java
links(
    linkWithRel("ex:reviews").description("Đánh giá của sản phẩm"),
    linkWithRel("curies").ignored()
)
```

Test có thể kiểm tra key ex:reviews tồn tại trong _links; curies giải thích cách mở rộng prefix, còn ex:reviews là relation nghiệp vụ cần tài liệu hóa.

## 8. LinkExtractor và Content-Type

Spring REST Docs trích link qua LinkExtractor phù hợp với representation. Các định dạng phổ biến có extractor tương ứng, ví dụ HAL và Atom. Nếu response dùng format tùy chỉnh, extractor mặc định có thể không nhận diện được link.

Khi test báo không tìm thấy link, kiểm tra:

1. Response có đúng Content-Type, ví dụ application/hal+json.
2. HAL payload có _links đúng cấu trúc.
3. Test gửi đúng representation qua Accept header.
4. Relation key trong descriptor khớp key response.
5. Nếu format tùy chỉnh, đã cấu hình LinkExtractor phù hợp chưa.

Không giả định mọi JSON có trường links đều là HAL. Content-Type và cấu trúc representation quyết định extractor có thể đọc link hay không.

## 9. Kết hợp links với response fields

Link descriptor kiểm tra relation; response field descriptor kiểm tra dữ liệu tài nguyên:

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

Với HAL, _links là phần hypermedia của representation. Dùng links(...) cho relation và field descriptor cho dữ liệu tài nguyên. Không dùng field descriptor thay cho link relation.

## 10. Include links.adoc trong Asciidoctor

Ví dụ file src/docs/asciidoc/products.adoc:

```asciidoc
= Products API
:toc: left

== Tìm sản phẩm

=== Hypermedia links
include::{snippets}/products-find/links.adoc[]

=== HTTP response
include::{snippets}/products-find/http-response.adoc[]

=== Response fields
include::{snippets}/products-find/response-fields.adoc[]
```

Attribute snippets phải trỏ tới thư mục gốc generated snippets. Đường dẫn phía sau phải khớp operation ID. Nếu operation chưa tạo links.adoc, include sẽ thất bại khi Asciidoctor chạy.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không sinh links.adoc | Chưa gọi links(...) hoặc test chưa chạy tới document. | Kiểm tra test report và descriptor. |
| LinkExtractor không tìm thấy relation | Content-Type hoặc cấu trúc representation sai. | Kiểm tra HAL/Atom format và extractor. |
| Strict mode báo undocumented link | Response có relation chưa mô tả. | Bổ sung descriptor hoặc relaxed có chủ đích. |
| Test báo thiếu relation bắt buộc | Descriptor không optional nhưng response không có link. | Sửa server hoặc optional nếu contract cho phép. |
| Link xuất hiện sai trạng thái | Controller trả link không đúng capability của resource. | Kiểm tra rule nghiệp vụ và response variant. |
| Không nhận custom relation | Sai relation name hoặc CURIE prefix. | Đối chiếu key trong _links và CURIE declaration. |
| URI template bị coi là URL cố định | Không kiểm tra templated flag hoặc biến. | Kiểm tra href và thuộc tính templated. |
| Asciidoctor không tìm thấy snippet | Sai operation ID, outputDir hoặc include path. | Đối chiếu thư mục generated snippets. |

## 12. Bài thực hành

Tạo API Catalog trả HAL JSON:

1. GET /api/products/{id} trả self, orders và profile.
2. GET /api/products trả collection với self, first, prev, next và last.
3. GET /api/orders/{id} trả self và cancel khi trạng thái đơn cho phép.
4. Viết MockMvc test kiểm tra status, Content-Type và URI của relation.
5. Dùng links(...) để mô tả relation; đánh dấu prev/next optional khi contract cho phép.
6. Tạo test strict để phát hiện relation mới chưa được mô tả; dùng relaxedLinks(...) trong test chỉ tập trung vào self.
7. Kiểm tra response có CURIE hoặc URI template.
8. Include links.adoc và http-response.adoc vào Asciidoctor, chạy clean test và dựng tài liệu.

**Tiêu chí hoàn thành:** kiểm tra relation và URI trong HAL; phân biệt relation với href; dùng strict/optional/ignored/relaxed đúng contract; hiểu LinkExtractor và Content-Type; sinh và include links.adoc từ test.

## 13. Tài liệu tham khảo

- [Spring REST Docs — Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs — HypermediaDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/HypermediaDocumentation.html)
- [Spring REST Docs — LinksSnippet API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/LinksSnippet.html)
- [Spring HATEOAS — Reference](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [HAL Specification](https://stateless.group/hal_specification.html)
