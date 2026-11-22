# Liên kết bắt buộc, tùy chọn và ignored

## 1. Vì sao phải phân biệt các loại hypermedia link?

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Trong API hướng hypermedia, response không chỉ chứa dữ liệu mà còn cung cấp các liên kết để client khám phá tài nguyên và hành động tiếp theo. Spring REST Docs sinh snippet mô tả relation, địa chỉ href và ý nghĩa của từng link; snippet sau đó được ghép vào Asciidoctor/Markdown và build, CI.

Một response HAL minh họa:

~~~json
{
  "id": 42,
  "name": "Bàn phím cơ",
  "_links": {
    "self": {"href": "/api/products/42"},
    "reviews": {"href": "/api/products/42/reviews"},
    "next": {"href": "/api/products?page=2"}
  }
}
~~~

Không phải mọi relation đều xuất hiện trong mọi response. self thường luôn có ở tài nguyên đã được định danh; next chỉ xuất hiện nếu còn trang tiếp theo; reviews có thể phụ thuộc việc sản phẩm có công bố đánh giá. Nếu tài liệu mô tả mọi link như thể chúng đều bắt buộc, test sẽ thất bại trong những response hợp lệ không có link tùy chọn.

Spring REST Docs cho phép biểu đạt ba ý định:

- **Bắt buộc:** link phải hiện diện trong operation được ghi tài liệu.
- **Tùy chọn:** link có thể xuất hiện hoặc vắng mặt theo hợp đồng.
- **Ignored:** link được chủ ý bỏ qua khi mô tả và kiểm tra tập link trong snippet.

Các ý định này được diễn đạt qua LinkDescriptor, thường tạo bằng linkWithRel(...), rồi truyền vào links(...) hoặc relaxedLinks(...).

## 2. Chuẩn bị descriptor cho hypermedia links

Các static import thường dùng:

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.relaxedLinks;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
~~~

Một descriptor cơ bản:

~~~java
linkWithRel("self").description("Tài nguyên hiện tại")
~~~

linkWithRel("self") chọn link dựa trên quan hệ self; description(...) cung cấp nội dung đưa vào snippet. Descriptor được truyền cho snippet links:

~~~java
mockMvc.perform(get("/api/products/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andDo(document("products-get",
                links(
                        linkWithRel("self")
                                .description("Sản phẩm hiện tại"),
                        linkWithRel("reviews")
                                .description("Đánh giá của sản phẩm"))));
~~~

Đoạn test này giả định response thực tế có cả relation self và reviews, đồng thời MockMvc đã được tích hợp Spring REST Docs và serializer HAL. Nếu thiếu một relation bắt buộc, việc tạo snippet có thể thất bại. Vì vậy, cần quyết định rõ một link là bắt buộc hay tùy chọn theo hợp đồng API.

## 3. Link bắt buộc: descriptor mặc định

Khi tạo descriptor bằng linkWithRel(...) mà không gọi optional(), Spring REST Docs coi relation là bắt buộc đối với operation được tài liệu hóa.

~~~java
links(
        linkWithRel("self")
                .description("Sản phẩm hiện tại"),
        linkWithRel("reviews")
                .description("Danh sách đánh giá"))
~~~

Với chế độ strict mặc định, Spring REST Docs kiểm tra các quan hệ được mô tả có trong response. Nếu response không chứa reviews, snippet links không thể được tạo như mong muốn và test tài liệu báo lỗi. Đây là hành vi có ích khi API cam kết mọi sản phẩm đều cung cấp relation này.

Ví dụ:

~~~java
@Test
void productHasSelfAndReviewsLinks() throws Exception {
    mockMvc.perform(get("/api/products/{id}", 42)
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.reviews.href").exists())
            .andDo(document("products-get",
                    links(
                            linkWithRel("self")
                                    .description("Sản phẩm hiện tại"),
                            linkWithRel("reviews")
                                    .description("Đánh giá của sản phẩm"))));
}
~~~

Hai matcher JSONPath kiểm tra body response trước khi ghi tài liệu; các descriptor tiếp tục tạo bảng mô tả link. Descriptor không thay thế assertions nghiệp vụ khác như status hoặc payload.

### Khi nào nên dùng link bắt buộc?

Chọn descriptor bắt buộc khi API cam kết relation luôn có trong loại response này, client cần relation để hiểu tài nguyên hoặc thao tác tiếp theo, và sự thiếu vắng relation biểu thị lỗi hợp đồng. Nhờ đó CI phát hiện việc controller vô tình xóa, đổi tên hoặc ngừng phát relation.

## 4. Link tùy chọn với optional()

Một relation có thể vắng mặt trong response hợp lệ. Ví dụ next chỉ xuất hiện khi trang hiện tại chưa phải trang cuối; prev không xuất hiện ở trang đầu. Đánh dấu descriptor là optional:

~~~java
links(
        linkWithRel("self")
                .description("Trang hiện tại"),
        linkWithRel("next")
                .optional()
                .description("Trang tiếp theo nếu còn dữ liệu"))
~~~

optional() nói với Spring REST Docs rằng descriptor có thể không tìm thấy trong operation. Nếu link xuất hiện, descriptor vẫn mô tả nó; nếu link vắng mặt, việc thiếu relation đó không làm snippet thất bại chỉ vì sự vắng mặt.

### Ví dụ pagination

Trang đầu có self và next, nhưng không có prev:

~~~json
{
  "_links": {
    "self": {"href": "/api/products?page=0"},
    "next": {"href": "/api/products?page=1"}
  }
}
~~~

Trang cuối có self và prev, nhưng không có next:

~~~json
{
  "_links": {
    "self": {"href": "/api/products?page=5"},
    "prev": {"href": "/api/products?page=4"}
  }
}
~~~

Một bộ descriptor dùng chung cho hai trạng thái:

~~~java
links(
        linkWithRel("self").description("Trang hiện tại"),
        linkWithRel("prev").optional().description("Trang trước"),
        linkWithRel("next").optional().description("Trang tiếp theo"))
~~~

Nếu API có cả first và last, có thể thêm chúng theo đúng quy tắc xuất hiện. Không đánh dấu self thành optional nếu hợp đồng quy định link đó luôn phải có; làm vậy sẽ che giấu lỗi.

### optional() không có nghĩa là bỏ qua khi link xuất hiện

Optional chỉ nới yêu cầu về **sự hiện diện**. Khi relation có xuất hiện trong response, nó vẫn được nhận diện và có thể xuất hiện trong bảng links theo descriptor. Optional không biến link thành thành phần bí mật, cũng không có nghĩa là không cần mô tả.

## 5. Link ignored: nhận diện nhưng không đưa vào tài liệu

Đôi khi response có link nội bộ hoặc relation không thuộc phạm vi tài liệu công khai. Có thể khai báo descriptor ignored:

~~~java
links(
        linkWithRel("self")
                .description("Tài nguyên hiện tại"),
        linkWithRel("internal-audit")
                .ignored())
~~~

ignored() đánh dấu relation được chủ ý bỏ qua trong quá trình tài liệu hóa. Link này không được trình bày như một relation được mô tả thông thường; mục tiêu là cho phép công cụ nhận biết rằng sự hiện diện của nó đã được cân nhắc, thay vì coi đó là relation chưa được mô tả ngoài ý muốn.

Ví dụ response có thêm link nội bộ:

~~~json
{
  "id": 42,
  "_links": {
    "self": {"href": "/api/products/42"},
    "internal-audit": {"href": "/internal/audit/products/42"}
  }
}
~~~

Nếu tài liệu công khai chỉ cần self, có thể cấu hình:

~~~java
links(
        linkWithRel("self").description("Sản phẩm hiện tại"),
        linkWithRel("internal-audit").ignored())
~~~

Không dùng ignored() chỉ để làm test qua khi một relation công khai quan trọng chưa được mô tả. Nếu client cần biết link reviews, hãy mô tả relation đó bằng description(...) để người dùng tài liệu hiểu được ý nghĩa.

### Phân biệt ignored và optional

| Cấu hình | Quan hệ có thể vắng mặt? | Khi quan hệ có mặt |
| --- | --- | --- |
| Descriptor mặc định | Không, relation được kỳ vọng có mặt | Được mô tả trong snippet |
| optional() | Có | Vẫn được mô tả nếu hiện diện |
| ignored() | Không yêu cầu phải xuất hiện | Được bỏ qua trong mô tả/kiểm tra tập link |

Hai lựa chọn phục vụ ý định khác nhau. optional() nói “có thể có hoặc không, nhưng nếu có thì đây là link cần mô tả”; ignored() nói “relation này nằm ngoài phạm vi mô tả của snippet”.

## 6. Strict links và relaxed links

Ngoài trạng thái của từng descriptor, Spring REST Docs còn có hai cách kiểm soát tập relation: strict và relaxed.

### Strict links bằng links(...)

~~~java
links(
        linkWithRel("self").description("Sản phẩm hiện tại"),
        linkWithRel("reviews").description("Đánh giá của sản phẩm"))
~~~

Trong chế độ strict, các link có trong response cần được xử lý bởi descriptor tương ứng. Nếu response có thêm một relation chưa được mô tả, Spring REST Docs có thể báo lỗi để tránh âm thầm bỏ sót một phần hợp đồng hypermedia.

Ví dụ response có self, reviews và seller, nhưng descriptor chỉ khai báo hai link:

~~~json
{
  "_links": {
    "self": {"href": "/api/products/42"},
    "reviews": {"href": "/api/products/42/reviews"},
    "seller": {"href": "/api/sellers/7"}
  }
}
~~~

Trong strict mode, hãy thêm mô tả seller nếu đây là relation công khai:

~~~java
links(
        linkWithRel("self").description("Sản phẩm hiện tại"),
        linkWithRel("reviews").description("Đánh giá"),
        linkWithRel("seller").description("Nhà bán sản phẩm"))
~~~

Hoặc đánh dấu ignored nếu relation nằm ngoài phạm vi được tài liệu hóa và có chủ ý bỏ qua. Tránh chuyển sang relaxed chỉ để che một relation mới mà nhóm chưa xem xét.

### Relaxed links bằng relaxedLinks(...)

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.relaxedLinks;

mockMvc.perform(get("/api/products/{id}", 42))
        .andExpect(status().isOk())
        .andDo(document("products-get",
                relaxedLinks(
                        linkWithRel("self")
                                .description("Sản phẩm hiện tại"))));
~~~

relaxedLinks(...) cho phép response có các relation chưa được descriptor mô tả. Snippet vẫn ghi các link được khai báo, nhưng test không còn yêu cầu toàn bộ link trong response phải được liệt kê.

Đây là lựa chọn phù hợp khi payload có nhiều relation phụ, tài liệu chỉ tập trung vào một nhóm con, hoặc endpoint trả link mở rộng theo quyền, tính năng hay trạng thái. Đổi lại, relaxed links giảm mức kiểm soát thay đổi hợp đồng: API có thể thêm một relation mà test tài liệu không cảnh báo.

### So sánh nhanh

| Chế độ | Quan hệ được mô tả | Quan hệ có mặt nhưng chưa mô tả |
| --- | --- | --- |
| links(...) strict | Phải khai báo, trừ descriptor ignored | Có thể làm test thất bại |
| relaxedLinks(...) | Chỉ cần mô tả các quan hệ được chọn | Được phép tồn tại mà không cần descriptor |
| optional() trong strict | Vẫn là quan hệ được mô tả | Chỉ cho phép chính relation đó vắng mặt |
| ignored() trong strict | Không đưa relation vào phần mô tả | Được công cụ bỏ qua theo chủ ý |

Strict/relaxed là lựa chọn ở cấp snippet; optional/ignored là trạng thái của từng descriptor. Không nhầm hai tầng này.

## 7. Ví dụ MockMvc cho link bắt buộc và tùy chọn

Giả sử endpoint danh sách sản phẩm trả self luôn có, còn prev và next thay đổi theo trang. Test sử dụng Spring Boot, Spring HATEOAS và Spring REST Docs:

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
class ProductPageDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentFirstPage() throws Exception {
        mockMvc.perform(get("/api/products?page=0&size=2")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.next.href").exists())
                .andDo(document("products-page-first",
                        links(
                                linkWithRel("self").description("Trang hiện tại"),
                                linkWithRel("prev").optional().description("Trang trước nếu có"),
                                linkWithRel("next").optional().description("Trang tiếp theo nếu có"))));
    }

    @Test
    void documentLastPage() throws Exception {
        mockMvc.perform(get("/api/products?page=5&size=2")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.prev.href").exists())
                .andExpect(jsonPath("$._links.next").doesNotExist())
                .andDo(document("products-page-last",
                        links(
                                linkWithRel("self").description("Trang hiện tại"),
                                linkWithRel("prev").optional().description("Trang trước nếu có"),
                                linkWithRel("next").optional().description("Trang tiếp theo nếu có"))));
    }
}
~~~

Các URL và số trang là dữ liệu minh họa; endpoint thật phải trả đúng relation tương ứng. Test cuối xác nhận next không tồn tại ở trang cuối, trong khi descriptor đánh dấu optional để cả hai trạng thái hợp lệ dùng chung quy tắc mô tả.

Nếu ứng dụng không dùng Spring Boot auto-configuration cho REST Docs, thay setup bằng RestDocumentationExtension và documentationConfiguration(...) trên MockMvc builder.

## 8. Đưa snippet links vào tài liệu

Khi gọi document("products-page-first", links(...)), Spring REST Docs ghi snippet links.adoc dưới identifier tương ứng. Trang Asciidoctor có thể nhúng:

~~~adoc
== Trang đầu tiên

include::{snippets}/products-page-first/http-response.adoc[]
include::{snippets}/products-page-first/links.adoc[]

== Trang cuối cùng

include::{snippets}/products-page-last/http-response.adoc[]
include::{snippets}/products-page-last/links.adoc[]
~~~

{snippets} phải trỏ đúng output directory của build, thường là build/generated-snippets/ với Gradle hoặc target/generated-snippets/ với Maven. Nếu tài liệu dùng Markdown, cần cơ chế chuyển đổi hoặc nhúng snippet AsciiDoc theo cách dự án thiết kế.

Nên đưa cả HTTP response và links.adoc vào trang. HTTP response cho người đọc thấy cấu trúc representation, còn bảng link diễn giải relation và ý nghĩa mà client nên dựa vào.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test báo thiếu self | Descriptor strict yêu cầu link nhưng response không có | Kiểm tra representation, media type, serializer và link builder; chỉ optional nếu hợp đồng cho phép vắng mặt. |
| Trang cuối lỗi vì thiếu next | next bị khai báo bắt buộc | Dùng optional() nếu trang cuối hợp lệ không có next link. |
| Test báo relation chưa được mô tả | Response có relation mới nhưng strict descriptor chưa khai báo | Mô tả relation đó hoặc đánh dấu ignored khi có chủ ý bỏ qua. |
| Relation quan trọng không xuất hiện trong bảng | Descriptor đánh dấu ignored hoặc dùng sai rel | Bỏ ignored và dùng linkWithRel(...) đúng quan hệ. |
| Dùng relaxed khiến test không phát hiện link lạ | Relaxed snippet cho phép link chưa mô tả | Chuyển sang strict nếu cần kiểm soát hợp đồng đầy đủ. |
| Link có trong JSON nhưng extractor không nhận diện | Media type hoặc định dạng hypermedia không được hỗ trợ/cấu hình | Xác nhận Content-Type, HAL structure và hypermedia configuration. |
| Snippet links không được tạo | Test dừng trước document hoặc chưa gọi links snippet | Kiểm tra test report, andDo(document(...)) và handler. |
| Asciidoctor thiếu links.adoc | Identifier hoặc output path không khớp | Đối chiếu document(...), thư mục snippet và snippets. |

Khi lỗi xảy ra, đọc response thực tế trước khi nới descriptor. Một relation thiếu có thể là lỗi controller; một relation vắng mặt hợp lệ thì cần optional(); một relation nằm ngoài phạm vi tài liệu có thể dùng ignored() hoặc relaxed snippet tùy ý định.

## 10. Bài thực hành

1. Tạo endpoint sản phẩm có relation self và reviews; viết test strict với cả hai descriptor.
2. Tạo response phân trang ở trang đầu và trang cuối; xác minh next/prev thay đổi và đánh dấu optional đúng cách.
3. Thêm relation internal-audit; dùng ignored() khi tài liệu công khai không mô tả relation này và giải thích lý do.
4. Để relation mới xuất hiện nhưng không thêm descriptor; quan sát strict links phát hiện link chưa được tài liệu hóa.
5. Chuyển test sang relaxedLinks(...) và xác định những thay đổi nào sẽ không còn được kiểm tra.
6. Biên soạn Asciidoctor có cả http-response.adoc và links.adoc cho trang đầu/cuối; nối task tài liệu sau bước test trong CI.

**Tiêu chí hoàn thành:** phân biệt đúng link bắt buộc, optional và ignored; hiểu strict links so với relaxed links; sử dụng descriptor đúng hợp đồng; có test cho cả trạng thái link xuất hiện và vắng mặt; snippet được nhúng đúng đường dẫn.

## 11. Checklist trước khi công bố hypermedia links

- [ ] Xác định relation nào bắt buộc theo hợp đồng API.
- [ ] Dùng descriptor mặc định cho link phải xuất hiện.
- [ ] Dùng optional() chỉ khi link có thể vắng mặt trong response hợp lệ.
- [ ] Dùng ignored() khi relation đã được cân nhắc nhưng chủ ý bỏ khỏi mô tả.
- [ ] Chọn links(...) strict khi cần kiểm soát tập relation; chỉ chọn relaxedLinks(...) khi tài liệu có chủ ý mô tả một phần.
- [ ] Assertions xác nhận status, media type và các link quan trọng.
- [ ] Mô tả relation bằng ngôn ngữ dễ hiểu đối với client.
- [ ] Kiểm tra links.adoc, identifier và đường dẫn include.
- [ ] Build/CI sinh snippet mới trước khi biên soạn và xuất bản tài liệu.

**Ghi nhớ:** Link bắt buộc là một cam kết của response; optional() cho phép link có thể vắng mặt nhưng vẫn mô tả nếu xuất hiện; ignored() chủ ý loại relation khỏi phần mô tả; relaxedLinks(...) cho phép các link khác chưa được mô tả. Chọn đúng mức kiểm tra giúp tài liệu Spring REST Docs phản ánh chính xác hợp đồng hypermedia mà client cần dùng.
