# Kiểm tra liên kết thực tế bằng snippet

## 1. Snippet links và kiểm chứng link là hai việc khác nhau

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Với API hypermedia, response chứa các quan hệ như self, next, orders hoặc profile, đi kèm URI đích trong href. Spring REST Docs trích xuất các link này để tạo snippet, sau đó ghép vào Asciidoctor/Markdown và build, CI.

Cần phân biệt hai mục tiêu:

- **Tài liệu hóa link:** mô tả quan hệ và ý nghĩa của link có trong response bằng links(...), linkWithRel(...) hoặc linkWithHref(...).
- **Kiểm chứng link:** xác nhận response có đúng relation, đúng href, đúng path/query và đúng điều kiện xuất hiện theo hợp đồng API.

Ví dụ response HAL:

~~~json
{
  "id": 42,
  "name": "Bàn phím cơ",
  "_links": {
    "self": {"href": "https://api.example.test/api/products/42"},
    "reviews": {"href": "https://api.example.test/api/products/42/reviews"}
  }
}
~~~

Descriptor linkWithRel("reviews") giúp Spring REST Docs tìm relation và tạo bảng links. Để bảo đảm link dẫn đúng tài nguyên, test còn cần xác nhận href theo hợp đồng, chẳng hạn dùng JSONPath. Một snippet đẹp không tự chứng minh URL là chính xác.

## 2. Xác nhận response thực sự là hypermedia

Trước khi kiểm tra link, xác nhận endpoint trả đúng media type và cấu trúc hypermedia. Với HAL, media type thường là application/hal+json.

~~~java
mockMvc.perform(get("/api/products/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links").exists());
~~~

Các điều kiện này xác nhận status mong đợi, media type HAL tương thích với client và body có vùng _links. Nếu endpoint chỉ trả application/json với dữ liệu thuần, không nên giả định links(...) có thể trích xuất cấu trúc HAL. Khi matcher thất bại, in response bằng andDo(print()) hoặc lấy MvcResult để xem body thực nhận.

## 3. Kiểm tra relation bằng linkWithRel(...)

linkWithRel(...) chọn một link dựa trên tên quan hệ. Khi truyền vào links(...), descriptor giúp Spring REST Docs xác nhận quan hệ cần mô tả tồn tại và ghi nó thành snippet.

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

mockMvc.perform(get("/api/products/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andDo(document("products-get",
                links(
                        linkWithRel("self").description("Sản phẩm hiện tại"),
                        linkWithRel("reviews").description("Đánh giá của sản phẩm"))));
~~~

Với chế độ strict, descriptor mặc định yêu cầu relation được mô tả phải có trong response. Nếu reviews bị xóa hoặc đổi tên ngoài dự kiến, test tài liệu có thể thất bại thay vì âm thầm tạo bảng thiếu link.

Xác nhận rel tồn tại chưa đủ để bảo đảm link trỏ đúng URL. Hãy kiểm tra href riêng khi URI là một phần của hợp đồng có ý nghĩa đối với client.

## 4. Xác minh href bằng JSONPath

Với HAL, link được serialize dưới dạng object trong _links, thường có thuộc tính href. JSONPath kiểm tra sự tồn tại và giá trị URI:

~~~java
mockMvc.perform(get("/api/products/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href")
                .value("http://localhost/api/products/42"))
        .andExpect(jsonPath("$._links.reviews.href")
                .value("http://localhost/api/products/42/reviews"))
        .andDo(document("products-get",
                links(
                        linkWithRel("self").description("Sản phẩm hiện tại"),
                        linkWithRel("reviews").description("Đánh giá của sản phẩm"))));
~~~

Các URL trong ví dụ là minh họa. URI thực tế có thể phụ thuộc host, port, context path, proxy hoặc cấu hình link builder. Nên kiểm tra đúng dạng URI mà API cam kết.

So sánh chính xác toàn bộ href khi API cam kết cấu trúc URI ổn định, link chứa query được quy định rõ hoặc link trỏ tới endpoint cụ thể. Nếu host/port do môi trường cấp, so sánh toàn bộ URL tuyệt đối có thể khiến test mong manh. Khi đó xác minh path và query quan trọng, đồng thời kiểm tra URI có thể phân tích được.

## 5. Kiểm tra path và query trong link

Một link có thể đúng relation nhưng sai path parameter hoặc query parameter. Ví dụ link phân trang phải giữ đúng page và size:

~~~json
{
  "_links": {
    "self": {"href": "/api/products?page=1&size=20"},
    "next": {"href": "/api/products?page=2&size=20"},
    "prev": {"href": "/api/products?page=0&size=20"}
  }
}
~~~

Nếu thứ tự query được chuẩn hóa, có thể so sánh trực tiếp:

~~~java
.andExpect(jsonPath("$._links.next.href")
        .value("/api/products?page=2&size=20"))
~~~

Nếu thứ tự query không được bảo đảm, tránh phụ thuộc vào chuỗi URL nguyên vẹn. Lấy href, phân tích bằng URI rồi kiểm tra getPath() và query parameter theo tên/giá trị.

~~~java
import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

static Map<String, String> queryParameters(URI uri) {
    if (uri.getRawQuery() == null) {
        return Map.of();
    }
    return Arrays.stream(uri.getRawQuery().split("&"))
            .map(part -> part.split("=", 2))
            .collect(Collectors.toMap(
                    pair -> URLDecoder.decode(pair[0], StandardCharsets.UTF_8),
                    pair -> URLDecoder.decode(
                            pair.length == 2 ? pair[1] : "",
                            StandardCharsets.UTF_8)));
}
~~~

Sau khi trích xuất href từ response thành URI:

~~~java
assertThat(uri.getPath()).isEqualTo("/api/products");
assertThat(queryParameters(uri))
        .containsEntry("page", "2")
        .containsEntry("size", "20");
~~~

Helper trên minh họa cách kiểm tra query độc lập với thứ tự. Với query có thể lặp tên hoặc encoding phức tạp, dùng parser phù hợp của dự án thay vì Map chỉ lưu một giá trị cho mỗi key.

## 6. Kết hợp linkWithHref(...) khi cần định danh theo URL đích

linkWithRel(...) thường ổn định và giàu ý nghĩa vì relation diễn tả vai trò link:

~~~java
linkWithRel("reviews").description("Các đánh giá của sản phẩm")
~~~

Nếu cần chọn link bằng chính href, Spring REST Docs cũng có linkWithHref(...):

~~~java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithHref;

links(
        linkWithHref("/api/products/42/reviews")
                .description("Trang đánh giá của sản phẩm"))
~~~

Cách này hữu ích khi URI đích là tiêu chí nhận diện phù hợp với mục tiêu tài liệu. Tuy vậy, URL có thể thay đổi theo host, port, version hoặc dữ liệu; dùng relation thường tạo tài liệu ít phụ thuộc môi trường hơn. Dù chọn descriptor nào, hãy có assertion riêng nếu cần xác minh href thực tế.

## 7. Kiểm tra link bắt buộc và link tùy chọn theo trạng thái

Link có thể xuất hiện theo trạng thái tài nguyên hoặc trang collection:

- self: bắt buộc với representation tài nguyên đã định danh.
- next: chỉ có khi còn trang kế tiếp.
- prev: chỉ có khi không phải trang đầu.
- reviews: có thể phụ thuộc chính sách công bố hoặc khả năng hỗ trợ của tài nguyên.

Descriptor dùng optional() khi link có thể vắng mặt trong response hợp lệ:

~~~java
links(
        linkWithRel("self").description("Trang hiện tại"),
        linkWithRel("prev").optional().description("Trang trước"),
        linkWithRel("next").optional().description("Trang kế tiếp"))
~~~

optional() chỉ nới yêu cầu về sự hiện diện của relation đó. Nếu link xuất hiện, nó vẫn được mô tả. Để kiểm tra logic phân trang, viết test cho từng trạng thái cụ thể:

~~~java
@Test
void firstPageHasNextButNoPrevious() throws Exception {
    mockMvc.perform(get("/api/products?page=0&size=20")
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.next.href").exists())
            .andExpect(jsonPath("$._links.prev").doesNotExist())
            .andDo(document("products-page-first",
                    links(
                            linkWithRel("self").description("Trang hiện tại"),
                            linkWithRel("prev").optional().description("Trang trước"),
                            linkWithRel("next").optional().description("Trang kế tiếp"))));
}

@Test
void lastPageHasPreviousButNoNext() throws Exception {
    mockMvc.perform(get("/api/products?page=5&size=20")
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.prev.href").exists())
            .andExpect(jsonPath("$._links.next").doesNotExist())
            .andDo(document("products-page-last",
                    links(
                            linkWithRel("self").description("Trang hiện tại"),
                            linkWithRel("prev").optional().description("Trang trước"),
                            linkWithRel("next").optional().description("Trang kế tiếp"))));
}
~~~

Descriptor optional không khẳng định next có mặt ở trang đầu hay prev có mặt ở trang cuối. JSONPath assertions ở từng test mới kiểm chứng điều kiện cụ thể.

## 8. Kiểm tra link lồng nhau trong embedded resource

Khi response chứa embedded resource, cùng relation có thể tồn tại ở root và bên trong item:

~~~json
{
  "_embedded": {
    "stores": [
      {
        "id": 11,
        "_links": {
          "self": {"href": "/api/stores/11"},
          "products": {"href": "/api/stores/11/products"}
        }
      }
    ]
  },
  "_links": {
    "self": {"href": "/api/stores"}
  }
}
~~~

Kiểm tra link của item đầu tiên:

~~~java
.andExpect(jsonPath("$._embedded.stores[0]._links.self.href")
        .value("/api/stores/11"))
.andExpect(jsonPath("$._embedded.stores[0]._links.products.href")
        .value("/api/stores/11/products"))
~~~

Document relation trong từng embedded resource bằng subsection extractor:

~~~java
links(
        beneathPath("_embedded.stores[]"),
        linkWithRel("self").description("Cửa hàng hiện tại"),
        linkWithRel("products").description("Sản phẩm của cửa hàng"))
~~~

Root links dùng links(...) không có subsection extractor; nested links dùng overload có beneathPath(...). Hai cấp cần được kiểm tra và tài liệu hóa riêng. Nếu chỉ xác nhận root _links.self.href, test chưa nói gì về URL self của từng embedded store.

## 9. Ví dụ MockMvc kết hợp assertions và snippet links

Ví dụ sau xác nhận status, media type, payload, link tồn tại và URI đích; sau đó sinh snippet links:

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
class ProductLinkVerificationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void productLinksMatchTheContract() throws Exception {
        mockMvc.perform(get("/api/products/{id}", 42)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$._links.self.href")
                        .value("http://localhost/api/products/42"))
                .andExpect(jsonPath("$._links.reviews.href")
                        .value("http://localhost/api/products/42/reviews"))
                .andDo(document("products-get",
                        links(
                                linkWithRel("self").description("Sản phẩm hiện tại"),
                                linkWithRel("reviews").description("Đánh giá của sản phẩm"))));
    }
}
~~~

URL trong ví dụ phải điều chỉnh theo cách ứng dụng tạo base URI. Nếu port ngẫu nhiên hoặc proxy khiến host thay đổi, kiểm tra path/query bằng URI parser hoặc thiết lập base URI ổn định cho test. Không nới assertions đến mức chỉ kiểm tra href tồn tại nếu hợp đồng yêu cầu đúng đích.

## 10. Kiểm tra link có thể truy cập được

Kiểm tra chuỗi href đúng cấu trúc chưa bảo đảm tài nguyên đích thực sự hoạt động. Có thể kiểm thử điều hướng qua hai request:

1. Gọi endpoint collection hoặc resource ban đầu.
2. Lấy link href của relation cần theo.
3. Gửi request đến endpoint đích trong test.
4. Kiểm tra status, media type và nội dung đích.

Với MockMvc, một bài test có thể thực hiện hai request với URI đã biết:

~~~java
@Test
void productReviewsLinkLeadsToReviewsEndpoint() throws Exception {
    mockMvc.perform(get("/api/products/{id}", 42)
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.reviews.href")
                    .value("/api/products/42/reviews"));

    mockMvc.perform(get("/api/products/{id}/reviews", 42)
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON));
}
~~~

Đây là test điều hướng minh họa; request thứ hai đang dùng URI đã biết. Nếu muốn kiểm tra client có thể dùng đúng giá trị href nhận được, trích xuất href từ response đầu tiên rồi chuyển thành URI/path để tạo request tiếp theo. Với MockMvc, không gửi URL tuyệt đối của production ra mạng; chuyển href cùng host test thành request URI cục bộ.

Ví dụ trích xuất giá trị:

~~~java
MvcResult first = mockMvc.perform(get("/api/products/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andReturn();

String href = JsonPath.read(
        first.getResponse().getContentAsString(),
        "$._links.reviews.href");
~~~

Sau đó xác định path/query từ href, xác nhận host nằm trong phạm vi test và gọi MockMvc với URI tương ứng. Không lấy URL tùy ý từ response rồi truy cập mạng bên ngoài trong test tự động.

## 11. Identifier và snippet phản ánh link được kiểm chứng

Đặt identifier theo operation rõ ràng:

~~~java
document("products-get",
        links(
                linkWithRel("self").description("Sản phẩm hiện tại"),
                linkWithRel("reviews").description("Đánh giá của sản phẩm")))
~~~

Spring REST Docs ghi snippet links.adoc dưới thư mục operation tương ứng. Trang Asciidoctor có thể đưa snippet vào cùng HTTP response:

~~~adoc
== Xem sản phẩm

include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/http-response.adoc[]

=== Các quan hệ hypermedia

include::{snippets}/products-get/links.adoc[]
~~~

links.adoc giải thích relation và ý nghĩa; http-response.adoc cho thấy response được trả; assertions trong test bảo đảm link có giá trị theo hợp đồng. Ba phần hỗ trợ nhau và không thay thế lẫn nhau. Với Markdown, snippet mặc định thường là AsciiDoc nên cần bước chuyển đổi hoặc nhúng phù hợp.

## 12. Lỗi thường gặp khi kiểm tra link

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| links(...) không tìm thấy relation | Relation không có hoặc sai tên rel | Kiểm tra body _links và descriptor. |
| Relation tồn tại nhưng link đi sai tài nguyên | Chỉ kiểm tra rel, chưa kiểm tra href | Thêm JSONPath assertion hoặc kiểm tra URI. |
| URL tuyệt đối thay đổi giữa dev và CI | Host/port được tạo theo môi trường | Kiểm tra URI path/query hoặc cấu hình base URI ổn định. |
| Link phân trang có query sai | Link builder tạo nhầm page/size/filter | Kiểm tra query bằng URI parser và test cho trang đầu/cuối. |
| Test mong đợi next ở trang cuối | Không xét trạng thái collection | Xác minh hợp đồng; dùng optional descriptor và assertion từng trạng thái. |
| Link root đúng nhưng link item sai | Chỉ kiểm tra _links ở root | Dùng JSONPath đến embedded item và subsection link descriptor. |
| Snippet thiếu link mới | Strict links phát hiện relation chưa mô tả | Quyết định relation có công khai không; mô tả hoặc ignored có chủ ý. |
| Snippet links có nhưng endpoint đích lỗi | Test chỉ kiểm tra href, chưa gọi URI đích | Thêm test điều hướng và kiểm tra response của endpoint liên quan. |
| Asciidoctor thiếu links.adoc | Identifier hoặc output path không khớp | Kiểm tra thư mục snippet và đường dẫn include. |

Khi xử lý lỗi, không hạ strict links hoặc bỏ assertions chỉ để làm pipeline qua. Trước hết xác định response thực tế có vi phạm hợp đồng hay test đang mô tả sai hợp đồng.

## 13. Bài thực hành

1. Tạo endpoint HAL chi tiết sản phẩm với self và reviews; kiểm tra cả relation và giá trị href.
2. Thay base URI hoặc chạy test bằng port ngẫu nhiên; điều chỉnh kiểm tra để không phụ thuộc host nhưng vẫn xác nhận đúng path.
3. Tạo test pagination cho trang đầu, trang giữa và trang cuối; xác nhận self/prev/next cùng query parameter.
4. Tạo collection gồm embedded stores; kiểm tra link products của ít nhất hai item bằng JSONPath và subsection link descriptor.
5. Từ href reviews trong response, kiểm tra endpoint đích trả status và media type đúng.
6. Nhúng links.adoc vào Asciidoctor và nối bước biên soạn sau test tạo snippet trong CI.

**Tiêu chí hoàn thành:** phân biệt mô tả link với kiểm tra link; xác nhận đúng rel và href; kiểm tra path/query, link tùy chọn và liên kết lồng nhau; xác minh endpoint đích; snippet và tài liệu được tạo từ lần chạy test hiện tại.

## 14. Checklist trước khi công bố link

- [ ] Response có đúng media type hypermedia và cấu trúc link mà client sử dụng.
- [ ] links(...) mô tả đúng relation và chế độ strict/optional phù hợp.
- [ ] Assertions xác nhận link bắt buộc thực sự tồn tại.
- [ ] href được kiểm tra theo path/query hoặc URI contract cần bảo vệ.
- [ ] Host/port động không làm test mong manh.
- [ ] Link root và link trong embedded resources được kiểm tra ở đúng cấp.
- [ ] Các endpoint đích quan trọng đã được kiểm tra khả năng truy cập.
- [ ] links.adoc, identifier và đường dẫn include khớp output thực tế.
- [ ] Build/CI chạy test tạo snippet trước khi biên soạn và xuất bản.

**Ghi nhớ:** links(...) và linkWithRel(...) giúp tài liệu hóa các relation có trong response; assertions mới xác nhận link thực tế có đúng href, path, query và hành vi điều hướng. Kết hợp hai phần này giúp snippet Spring REST Docs phản ánh một hợp đồng hypermedia vừa dễ hiểu vừa được kiểm chứng bằng test.
