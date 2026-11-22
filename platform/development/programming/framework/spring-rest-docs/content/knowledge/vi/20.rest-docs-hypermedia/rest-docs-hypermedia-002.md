# links và linkWithRel để mô tả quan hệ

## 1. Hypermedia links trong hợp đồng API

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Bên cạnh status, header và payload, API hướng hypermedia còn công bố các link để client khám phá tài nguyên và hành động tiếp theo. Spring REST Docs sinh snippet riêng cho các link; snippet được ghép vào Asciidoctor/Markdown và đưa vào build, CI cùng ví dụ request/response.

Ví dụ response theo HAL:

~~~json
{
  "id": 42,
  "name": "Bàn phím cơ",
  "_links": {
    "self": {"href": "https://api.example.com/products/42"},
    "product": {"href": "https://api.example.com/products/42"},
    "reviews": {"href": "https://api.example.com/products/42/reviews"}
  }
}
~~~

Các quan hệ self, product và reviews diễn tả tài nguyên hiện tại và những tài nguyên liên quan. Client có thể dùng quan hệ cùng href để điều hướng thay vì tự ghép URL từ quy tắc đường dẫn ngầm định.

Spring REST Docs cung cấp nhóm API sau:

- links(...): tạo snippet mô tả các hypermedia link của operation.
- linkWithRel("..."): định danh một link bằng quan hệ (rel) của nó.
- linkWithHref("..."): định danh link bằng URI đích khi cần.
- description(...): giải thích ý nghĩa quan hệ đối với client.

Sau bài học, bạn có thể mô tả relation như self, reviews, next bằng links(...) và linkWithRel(...), kiểm tra link bắt buộc/tùy chọn, xử lý link chưa được mô tả và nhúng snippet vào tài liệu.

## 2. links(...) và linkWithRel(...) hoạt động ra sao?

Trong bài kiểm thử MockMvc, các descriptor hypermedia thường được truyền vào document(...):

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;

mockMvc.perform(get("/api/products/{id}", 42))
        .andExpect(status().isOk())
        .andDo(document("products-get",
                links(
                        linkWithRel("self").description("Sản phẩm hiện tại"),
                        linkWithRel("reviews").description("Danh sách đánh giá"))));
~~~

| Thành phần | Vai trò |
| --- | --- |
| links(...) | Tạo snippet descriptor để kiểm tra và ghi các link trong HTTP operation. |
| linkWithRel("reviews") | Chọn link theo quan hệ có giá trị reviews. |
| description(...) | Ghi ý nghĩa quan hệ trong bảng snippet. |
| document("products-get", ...) | Gắn snippet link vào operation có identifier products-get. |

Với response HAL, quan hệ thường nằm ở khóa bên trong _links, còn href là đích điều hướng. Descriptor linkWithRel("reviews") nhận diện link bằng rel; không cần hard-code URL đích nếu URL có thể thay đổi theo host, môi trường hoặc ID tài nguyên.

Luồng tạo tài liệu:

~~~text
MockMvc request
      |
      v
HTTP response chứa HAL _links
      |
      v
andExpect(status / body / headers)
      |
      v
andDo(document("products-get", links(linkWithRel(...))))
      |
      v
Spring REST Docs nhận diện hypermedia format
      |
      v
links.adoc trong generated-snippets
      |
      v
Asciidoctor / Markdown
~~~

links(...) không tạo link trong response. Controller hoặc representation model phải phát ra link đúng; REST Docs chỉ kiểm tra và mô tả link thực sự có trong response.

## 3. Chuẩn bị dự án và hypermedia representation

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring MVC, Spring HATEOAS, JUnit Jupiter và Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-hateoas'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot dependency management nên quản lý phiên bản Spring HATEOAS và Spring REST Docs tương thích. Dự án không dùng BOM cần chọn phiên bản rõ ràng theo Spring Framework đang sử dụng.

Một endpoint có thể trả EntityModel<Product>:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
class ProductController {

    @GetMapping(value = "/api/products/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    EntityModel<Product> getProduct(@PathVariable long id) {
        Product product = new Product(id, "Bàn phím cơ");
        return EntityModel.of(product,
                linkTo(methodOn(ProductController.class).getProduct(id)).withSelfRel(),
                linkTo(methodOn(ReviewController.class).getReviews(id)).withRel("reviews"));
    }
}
~~~

Đoạn trên minh họa cách controller tạo representation và link; Product, ReviewController và getReviews(...) là các kiểu cần định nghĩa trong ứng dụng. EntityModel kết hợp dữ liệu entity và các link; serializer HAL chuyển chúng thành cấu trúc _links.

Khi test bằng MockMvc, nên dùng cấu hình Spring MVC/HATEOAS thực tế để response có media type và serializer tương ứng. Setup phổ biến trong ứng dụng Spring Boot:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class ProductDocumentationTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

Đây là setup rút gọn: SpringBootTest tải cấu hình ứng dụng, AutoConfigureMockMvc cung cấp MockMvc và AutoConfigureRestDocs tích hợp Spring REST Docs theo cấu hình Boot. Nếu dùng RestDocumentationExtension cùng webAppContextSetup(...) thủ công, áp dụng documentationConfiguration(restDocumentation) trên builder.

## 4. Mô tả link theo relation bằng linkWithRel

Một test có thể xác nhận status và content type rồi mô tả các relation:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class ProductDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentProductLinks() throws Exception {
        mockMvc.perform(get("/api/products/{id}", 42)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andDo(document("products-get",
                        links(
                                linkWithRel("self").description("Sản phẩm hiện tại"),
                                linkWithRel("reviews").description("Các đánh giá của sản phẩm"))));
    }
}
~~~

Endpoint phải thật sự trả relation self và reviews; nếu reviews không có trong response, descriptor mặc định sẽ báo thiếu relation. Khi URI đích là phần hợp đồng cần kiểm chứng, có thể bổ sung assertion JSONPath tương ứng.

### Đọc snippet links

Snippet được tạo có tên mặc định là links.adoc dưới identifier. Bảng link được dựng từ relation và mô tả đã khai báo:

| Rel | Description |
| --- | --- |
| self | Sản phẩm hiện tại |
| reviews | Các đánh giá của sản phẩm |

description(...) cung cấp nội dung dễ hiểu cho người dùng API; rel thể hiện loại quan hệ, còn URL đích được trích từ response.

## 5. Dùng linkWithRel cho các quan hệ thường gặp

Quan hệ phản ánh ý nghĩa điều hướng, không đơn giản là tên URL:

~~~java
links(
        linkWithRel("self").description("Tài nguyên hiện tại"),
        linkWithRel("profile").description("Mô tả cấu trúc tài nguyên"),
        linkWithRel("search").description("Tìm kiếm tài nguyên"),
        linkWithRel("next").description("Trang kết quả tiếp theo"),
        linkWithRel("prev").description("Trang kết quả trước"),
        linkWithRel("create").description("Tạo tài nguyên liên quan"))
~~~

Ví dụ này chỉ phù hợp khi response thực tế có đủ relation trên. Mỗi API có thể chọn relation riêng theo hợp đồng và media type. Relation chuẩn như self, next, prev có ý nghĩa phổ biến; relation tùy chỉnh như reviews hoặc create cần được mô tả nhất quán trong API.

### Link pagination

Response danh sách có thể chứa:

~~~json
{
  "_embedded": {
    "products": [
      {"id": 41, "name": "Chuột"},
      {"id": 42, "name": "Bàn phím"}
    ]
  },
  "_links": {
    "self": {"href": "/api/products?page=1"},
    "first": {"href": "/api/products?page=0"},
    "prev": {"href": "/api/products?page=0"},
    "next": {"href": "/api/products?page=2"},
    "last": {"href": "/api/products?page=8"}
  }
}
~~~

Test có thể mô tả từng relation:

~~~java
.andDo(document("products-list",
        links(
                linkWithRel("self").description("Trang hiện tại"),
                linkWithRel("first").description("Trang đầu tiên"),
                linkWithRel("prev").description("Trang trước"),
                linkWithRel("next").description("Trang tiếp theo"),
                linkWithRel("last").description("Trang cuối cùng"))))
~~~

Đoạn trên nối tiếp perform(...) và các matcher. Ở trang đầu hoặc cuối, quan hệ prev hay next có thể vắng mặt; hãy mô tả đúng tính tùy chọn thay vì giả định mọi trang đều có mọi link.

## 6. Link bắt buộc, link tùy chọn và link bỏ qua

Spring REST Docs kiểm tra các link được khai báo với links(...). Có các cách biểu đạt khác nhau:

### Relation bắt buộc

~~~java
links(
        linkWithRel("self").description("Tài nguyên hiện tại"),
        linkWithRel("reviews").description("Các đánh giá"))
~~~

Descriptor mặc định kỳ vọng các relation được mô tả xuất hiện trong operation. Khi API vô tình bỏ mất reviews, test tài liệu có thể thất bại và báo relation chưa được tìm thấy. Đây là cách bảo vệ hợp đồng link bắt buộc.

### Relation có thể vắng mặt

~~~java
links(
        linkWithRel("self").description("Tài nguyên hiện tại"),
        linkWithRel("next")
                .optional()
                .description("Trang tiếp theo nếu còn dữ liệu"))
~~~

optional() phù hợp khi relation có thể không xuất hiện trong một số response hợp lệ, chẳng hạn next ở trang cuối. Khi link có mặt, nó vẫn được mô tả; khi không có, descriptor không làm test thất bại chỉ vì thiếu relation tùy chọn.

### Relation được nhận diện nhưng không đưa vào bảng

~~~java
links(
        linkWithRel("self").description("Tài nguyên hiện tại"),
        linkWithRel("internal-audit").ignored())
~~~

ignored() dùng khi relation có thể xuất hiện nhưng chủ ý không đưa vào bảng mô tả. Chỉ bỏ qua link khi có lý do rõ ràng; nếu relation thuộc API công khai và client cần biết, hãy mô tả nó.

### Relaxed links

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.relaxedLinks;

.andDo(document("products-get",
        relaxedLinks(
                linkWithRel("self").description("Sản phẩm hiện tại"))))
~~~

relaxedLinks(...) phù hợp khi chỉ tài liệu hóa một phần link trong response lớn. Những relation không được mô tả có thể không bị xem là lỗi. Đổi lại, test không còn kiểm soát strict toàn bộ link; nếu một relation mới xuất hiện ngoài dự kiến, tài liệu có thể không cảnh báo.

| Cách khai báo | Link phải có? | Link chưa mô tả |
| --- | --- | --- |
| linkWithRel("x") | Có | Có thể làm test strict thất bại |
| linkWithRel("x").optional() | Không | Các relation khác vẫn theo chế độ strict |
| linkWithRel("x").ignored() | Không cần đưa vào bảng | Được nhận diện và bỏ khỏi mô tả |
| relaxedLinks(...) | Theo descriptor | Cho phép link chưa mô tả |

Chọn chế độ dựa trên hợp đồng API. Với endpoint công khai, strict links giúp tài liệu phản ánh chính xác tập relation mà client được phép sử dụng.

## 7. Dùng linkWithHref khi cần định danh theo URL đích

Thông thường, relation là cách ổn định và giàu ý nghĩa nhất để nhận diện link:

~~~java
linkWithRel("reviews").description("Các đánh giá của sản phẩm")
~~~

Nếu cần chọn link bằng chính href, Spring REST Docs cũng có linkWithHref(...):

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithHref;

links(
        linkWithHref("/api/products/42")
                .description("Trang chi tiết của sản phẩm"))
~~~

Cách này hữu ích khi một response có những link đích cần được nhận diện theo URI cụ thể. Tuy vậy, URL có thể thay đổi theo host, port, version hoặc dữ liệu; dùng relation thường tạo tài liệu ít phụ thuộc môi trường hơn. Không hard-code địa chỉ tuyệt đối nếu operation chạy ở nhiều môi trường.

## 8. Các định dạng hypermedia và việc nhận diện link

Spring REST Docs dùng cơ chế trích xuất hypermedia link phù hợp với định dạng response, chẳng hạn HAL. Với HAL, dữ liệu link nằm trong _links; relation là tên khóa và href là địa chỉ đích. Spring HATEOAS cũng có thể tạo representation khác tùy cấu hình và media type.

Một số lưu ý khi chẩn đoán:

- Kiểm tra response Content-Type có đúng media type hypermedia endpoint công bố, ví dụ application/hal+json, không chỉ là application/json.
- Kiểm tra body thực tế có cấu trúc link mà extractor có thể nhận diện.
- Nếu API dùng định dạng hypermedia tùy chỉnh, cần cấu hình extractor phù hợp thay vì giả định extractor HAL đọc đúng mọi cấu trúc.
- Nếu serializer không tạo _links, linkWithRel(...) không thể tìm relation chỉ vì controller có khai báo link ở một object chưa được serialize đúng cách.

Ví dụ matcher cho HAL:

~~~java
.andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
.andExpect(jsonPath("$._links.self.href").exists())
~~~

Đây là hai matcher nối sau perform(...). Assertion JSONPath xác nhận link thật sự được serialize trong response; links(...) tiếp tục kiểm tra và tạo bảng mô tả relation.

## 9. Ghép snippet links vào Asciidoctor

Giả sử test ghi operation bằng identifier products-get. Spring REST Docs sinh snippet links.adoc trong thư mục tương ứng. Trang Asciidoctor có thể tham chiếu:

~~~adoc
= Products API

== Xem sản phẩm

include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/http-response.adoc[]

=== Các quan hệ hypermedia

include::{snippets}/products-get/links.adoc[]
~~~

{snippets} phải trỏ đến thư mục output snippet của build, thường là build/generated-snippets/ với Gradle hoặc target/generated-snippets/ với Maven, trừ khi dự án cấu hình đường dẫn khác.

Nếu response có nhiều relation:

~~~adoc
== Danh sách sản phẩm

include::{snippets}/products-list/http-response.adoc[]
include::{snippets}/products-list/links.adoc[]
~~~

Snippet links.adoc là bảng quan hệ; snippet HTTP response vẫn hữu ích để người đọc thấy dữ liệu và biểu diễn link đầy đủ. Hai phần bổ trợ nhau: response minh họa payload, bảng links giải thích quan hệ ở góc nhìn client.

Với Markdown, snippet mặc định thường là AsciiDoc. Cần chuyển đổi hoặc nhúng nội dung theo cơ chế build mà dự án lựa chọn; không giả định Markdown renderer có thể xử lý trực tiếp mọi cú pháp include::.

## 10. Lỗi thường gặp khi mô tả hypermedia links

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không sinh links.adoc | Test chưa gọi links(...), handler không chạy hoặc test dừng trước bước document | Kiểm tra test report, andDo(document(...)) và identifier. |
| Không tìm thấy relation self | Response không có _links.self, sai media type hoặc serializer không tạo HAL | Kiểm tra body, Content-Type, HATEOAS converter và representation model. |
| Thiếu relation next ở trang cuối | Descriptor coi link tùy chọn là bắt buộc | Dùng optional() nếu link được phép vắng mặt theo hợp đồng. |
| Test báo link chưa mô tả | Có relation mới trong response nhưng descriptor strict chưa khai báo | Bổ sung descriptor hoặc dùng relaxed links khi chỉ cần tài liệu hóa một phần. |
| Link có trong response nhưng không nằm trong bảng | Descriptor dùng sai rel hoặc được đánh dấu ignored() | Đối chiếu tên relation trong _links và descriptor. |
| URI trong snippet khác mong đợi | Host/base URI hoặc link builder tạo URL khác theo môi trường | Kiểm tra cấu hình URI, proxy/base path và cách tạo link. |
| href đúng nhưng relation sai | Link được gắn nhầm relation trong representation | Sửa withRel(...)/withSelfRel() hoặc kỳ vọng tài liệu theo hợp đồng thật. |
| Asciidoctor báo thiếu links.adoc | Include sai identifier/tên snippet hoặc test chưa sinh file | Kiểm tra generated-snippets thực tế và snippets. |
| Test standalone không nhận link HAL | Chưa đăng ký converter/ObjectMapper/HATEOAS support cần thiết | Dùng web application context hoặc cấu hình converter phù hợp. |

## 11. Bài thực hành

1. Tạo endpoint trả EntityModel<Product> với relation self và reviews; viết test MockMvc dùng links(linkWithRel(...)).
2. Thêm endpoint danh sách phân trang với first, prev, next, last. Đánh dấu relation có thể vắng mặt bằng optional() theo đúng trạng thái trang.
3. Thêm relation profile để chỉ tài liệu mô tả schema; giải thích ý nghĩa relation trong descriptor.
4. Thử thêm một relation vào response nhưng không thêm descriptor; quan sát strict links phát hiện link chưa được tài liệu hóa.
5. Tách một test dùng relaxedLinks(...) và so sánh với chế độ strict. Quyết định chế độ nào phù hợp với endpoint công khai.
6. Nhúng links.adoc cùng http-response.adoc vào Asciidoctor, chạy test trước khi biên soạn và kiểm tra include.

**Tiêu chí hoàn thành:** biết cách tạo link trong representation, xác nhận response chứa hypermedia, mô tả quan hệ bằng linkWithRel, xử lý link bắt buộc/tùy chọn/ignored, hiểu strict và relaxed links, sau đó biên soạn snippet đúng đường dẫn.

## 12. Checklist trước khi công bố bảng links

- [ ] Endpoint thật sự trả representation hypermedia và đúng media type.
- [ ] Các relation được khai báo trong descriptor tồn tại trong response hoặc được đánh dấu optional hợp lý.
- [ ] Mỗi relation có description giải thích ý nghĩa đối với client.
- [ ] ignored() chỉ áp dụng cho relation không cần công bố; relaxed links được dùng có chủ đích.
- [ ] linkWithRel(...) phù hợp với hợp đồng; dùng linkWithHref(...) chỉ khi cần nhận diện theo URI.
- [ ] Assertions xác nhận status/content type và các link quan trọng.
- [ ] Identifier và file links.adoc khớp với đường dẫn include.
- [ ] Build/CI chạy test tạo snippet trước khi biên soạn và xuất bản tài liệu.

**Ghi nhớ:** links(...) tạo snippet mô tả hypermedia links của một HTTP operation; linkWithRel(...) chọn quan hệ mà client dùng để hiểu và điều hướng API. Kết hợp descriptor, assertions và snippet links.adoc giúp tài liệu thể hiện không chỉ dữ liệu trả về mà cả cách client khám phá tài nguyên tiếp theo.
