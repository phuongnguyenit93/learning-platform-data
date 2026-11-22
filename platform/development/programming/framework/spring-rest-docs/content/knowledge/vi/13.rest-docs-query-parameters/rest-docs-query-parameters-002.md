# `parameterWithName` và cách mô tả query parameter trong Spring REST Docs

## 1. Mục tiêu bài học

Trong một REST API có truy vấn tìm kiếm, tên tham số như `q`, `page`, `size` hay `tag` là một phần của hợp đồng giữa client và server. Nếu chỉ đưa ví dụ URL vào tài liệu, người đọc vẫn chưa biết tham số nào bắt buộc, giá trị mặc định là gì hoặc có thể truyền nhiều giá trị hay không.

**Spring REST Docs** sinh tài liệu API từ các bài kiểm thử HTTP chạy bằng MockMvc, WebTestClient hoặc REST Assured. Trong chủ đề **Query parameters**, `parameterWithName(...)` là phương tiện khai báo từng tham số cần mô tả; `queryParameters(...)` tập hợp các khai báo đó thành một snippet có thể đưa vào tài liệu Asciidoctor/Markdown. Cách làm này giúp tài liệu được kiểm tra cùng request thật trong quá trình build và CI.

Sau bài này, bạn sẽ:

- Tạo `ParameterDescriptor` bằng `parameterWithName("...")` và viết `description(...)` đủ thông tin cho người sử dụng API.
- Hiểu khi nào dùng `optional()`, `ignored()`, `attributes(...)` và cách chúng liên hệ với hợp đồng HTTP.
- Phân biệt kiểm tra **sự có mặt/tên** của tham số với kiểm tra **giá trị và quy tắc nghiệp vụ**.
- Tự tạo, đọc và tích hợp `query-parameters.adoc` bằng một kiểm thử MockMvc hoàn chỉnh.

## 2. `parameterWithName` làm công việc gì?

Xét request:

```http
GET /api/articles?q=rest%20docs&page=1&tag=java&tag=spring HTTP/1.1
Host: api.example.test
```

Query string chứa ba **tên tham số**: `q`, `page` và `tag`. `tag` xuất hiện hai lần nhưng vẫn là một tên tham số. Để sinh tài liệu cho request này:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("q")
        .description("Từ khóa tìm bài viết; bắt buộc, không được rỗng"),
    parameterWithName("page")
        .description("Chỉ số trang bắt đầu từ 0; mặc định 0")
        .optional(),
    parameterWithName("tag")
        .description("Nhãn lọc; lặp tham số để chọn nhiều nhãn, ví dụ tag=java&tag=spring")
        .optional()
)
```

Các thành phần có vai trò khác nhau:

| API | Vai trò |
| --- | --- |
| `parameterWithName("q")` | Tạo một descriptor cho tên query parameter `q` |
| `description("...")` | Cung cấp nội dung giải thích xuất hiện trong bảng tài liệu |
| `optional()` | Cho phép request đang kiểm thử **không có** tham số đó |
| `ignored()` | Khai báo một tham số được biết đến nhưng loại khỏi bảng snippet |
| `attributes(...)` | Gắn metadata bổ sung, có thể dùng trong snippet template tùy biến |
| `queryParameters(...)` | Gom các descriptor và tạo snippet cho **query string** của request |

`parameterWithName(...)` là static factory thuộc `org.springframework.restdocs.request.RequestDocumentation` và trả về `ParameterDescriptor`. Nó tự thân **không tạo file tài liệu**. File chỉ được tạo khi descriptor được đưa vào `queryParameters(...)` và gắn vào bước `document(...)` của một kiểm thử đã cấu hình Spring REST Docs.

> Từ Spring REST Docs 3.0, API dành riêng cho query string là `queryParameters(...)`. `formParameters(...)` dành cho form parameters trong body. Với tài liệu REST Docs 2.x cũ, bạn có thể gặp `requestParameters(...)`; khi dùng phiên bản mới nên phân biệt rõ hai nguồn dữ liệu.

## 3. Viết `description(...)` theo góc nhìn người dùng API

Tên tham số chỉ cho biết **nó được gọi là gì**. Phần mô tả tốt cần trả lời các câu hỏi thực tế:

1. Tham số dùng để làm gì, tác động đến kết quả nào?
2. Giá trị mong đợi thuộc kiểu/định dạng nào: chuỗi, số nguyên, mã ISO, enum...?
3. Có bắt buộc không? Nếu không truyền thì server xử lý ra sao?
4. Giới hạn hoặc tập giá trị hợp lệ là gì?
5. Có thể lặp tham số không? Nếu lặp, kết quả sẽ được kết hợp như thế nào?

Ví dụ:

| Tên | Mô tả quá ngắn | Mô tả đủ để sử dụng |
| --- | --- | --- |
| `q` | Từ khóa | Từ khóa tìm trong tiêu đề và nội dung; bắt buộc, không được để rỗng |
| `page` | Trang | Chỉ số trang từ 0; mặc định 0 khi không truyền |
| `size` | Kích thước | Số kết quả/trang, từ 1 đến 100; mặc định 20 |
| `sort` | Sắp xếp | `createdAt` hoặc `title`; mặc định `createdAt` |
| `tag` | Nhãn | Có thể lặp: `tag=java&tag=spring`; lọc bài viết mang các nhãn được chọn |

Các ràng buộc trên **chỉ là ví dụ về một hợp đồng API**. Chỉ ghi những điều mà controller và kiểm thử của dự án thực sự thực thi. Chẳng hạn, REST Docs không tự xác minh khoảng `size=1..100` chỉ vì chúng ta đưa khoảng này vào `description(...)`.

### 3.1. Tên và giá trị là hai khái niệm khác nhau

- `parameterWithName("page")` mô tả **tên** `page`, không mô tả riêng giá trị `1`.
- `?tag=java&tag=spring` thường cần **một** descriptor `parameterWithName("tag")`; ý nghĩa của nhiều giá trị phải giải thích bằng văn bản.
- `?tag[]=java` có tên tham số thực tế là `tag[]` sau khi giải mã URL. Không tự đổi thành `tag` trong descriptor nếu ứng dụng sử dụng tên có ngoặc vuông.
- `?q=` có tham số `q` nhưng giá trị rỗng; kiểm tra sự có mặt của REST Docs không thay thế validation từ controller.
- `Page` và `page` là hai tên khác nhau; hãy dùng chính xác tên trên HTTP request và trong controller.

### 3.2. Chú thích định dạng và giá trị mặc định

Ví dụ `cursor` là token phân trang, `fromDate` là ngày ISO và `limit` là số nguyên:

```java
queryParameters(
    parameterWithName("cursor")
        .description("Token lấy trang tiếp theo; bỏ qua để bắt đầu từ trang đầu")
        .optional(),
    parameterWithName("fromDate")
        .description("Ngày bắt đầu theo ISO 8601 (yyyy-MM-dd), ví dụ 2026-11-01")
        .optional(),
    parameterWithName("limit")
        .description("Số kết quả tối đa, từ 1 đến 100; mặc định 20")
        .optional()
)
```

Nếu tài liệu cần công bố quy tắc xử lý múi giờ, nhiều giá trị hoặc cách sắp xếp, hãy ghi rõ trong `description(...)` hay phần giải thích endpoint. Tránh viết thông tin không được kiểm chứng là khả năng thực tế của API.

## 4. Ví dụ đầy đủ với MockMvc, JUnit 5 và REST Docs

Controller minh họa nhận từ khóa bắt buộc, chỉ số trang có mặc định và danh sách nhãn tùy chọn:

```java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ArticleController {

    @GetMapping("/api/articles")
    public String findArticles(
            @RequestParam("q") String query,
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "tag", required = false) List<String> tags) {
        String joinedTags = tags == null ? "" : String.join(",", tags);
        return "q=" + query + "; page=" + page + "; tags=" + joinedTags;
    }
}
```

Trong hệ thống thật, endpoint thường gọi service và trả về JSON. Ví dụ trả chuỗi để người học quan sát trực tiếp kết quả binding, tập trung vào việc mô tả tham số.

Kiểm thử:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ArticleQueryParameterDocsTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ArticleController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsQueryParameters() throws Exception {
        mockMvc.perform(get("/api/articles")
                        .queryParam("q", "Spring REST Docs")
                        .queryParam("page", "1")
                        .queryParam("tag", "java", "spring"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "q=Spring REST Docs; page=1; tags=java,spring"))
                .andDo(document("articles-search",
                        queryParameters(
                                parameterWithName("q")
                                        .description("Từ khóa tìm bài viết; bắt buộc"),
                                parameterWithName("page")
                                        .description("Chỉ số trang từ 0; mặc định 0")
                                        .optional(),
                                parameterWithName("tag")
                                        .description("Nhãn lọc; truyền lặp để chọn nhiều nhãn")
                                        .optional()
                        )));
    }
}
```

Trong ví dụ:

1. `RestDocumentationExtension` cùng `documentationConfiguration(...)` bật Spring REST Docs cho MockMvc.
2. `get("/api/articles").queryParam(...)` tạo query string, bao gồm hai giá trị của `tag`. Với REST Docs 3+, nên dùng `queryParam(...)` hoặc đặt tham số ngay trong URL khi tài liệu hóa **query parameters**. `param(...)` trong MockMvc biểu diễn Servlet request parameters tổng quát nên có thể gây nhầm với form parameters.
3. Hai assertion `status()` và `content()` xác minh hành vi HTTP của controller; descriptor REST Docs không kiểm tra nội dung trả về.
4. `document("articles-search", queryParameters(...))` yêu cầu sinh tài liệu. Với mặc định template Asciidoctor, file tương ứng nằm tại `build/generated-snippets/articles-search/query-parameters.adoc` khi Gradle được cấu hình dùng thư mục đó (Maven thường dùng `target/generated-snippets/`).

Snippet được sinh ra có nội dung kiểu bảng, gồm tên `q`, `page`, `tag` và phần `description`; chi tiết trình bày phụ thuộc template, phiên bản và cấu hình dự án. Không cần duy trì thủ công bảng này trong tài liệu.

### Chèn bảng vào tài liệu Asciidoctor

```asciidoc
= Articles API

== Tìm bài viết

GET /api/articles

=== Query parameters

include::{snippets}/articles-search/query-parameters.adoc[]
```

Trong build Gradle hoặc Maven, `{snippets}` phải trỏ đến thư mục chứa snippet và task Asciidoctor cần chạy sau các bài kiểm thử tạo snippet. CI nên chạy cả test và bước kết xuất tài liệu để phát hiện khi hợp đồng hoặc đường dẫn snippet bị thay đổi.

## 5. `optional()`: được phép vắng mặt trong request kiểm thử

Đoạn dưới mô tả `q` bắt buộc, `page` tùy chọn:

```java
queryParameters(
    parameterWithName("q").description("Từ khóa bắt buộc"),
    parameterWithName("page")
        .description("Trang từ 0; mặc định 0")
        .optional()
)
```

| Request đang được kiểm thử | Đánh giá phần mô tả trên |
| --- | --- |
| `/api/articles?q=spring&page=2` | Đủ hai tham số đã mô tả |
| `/api/articles?q=spring` | Hợp lệ đối với REST Docs vì `page` là optional |
| `/api/articles?page=2` | Thiếu descriptor bắt buộc `q`; đồng thời controller có thể trả lỗi 400 |
| `/api/articles?q=spring&sort=title` | Có tham số `sort` chưa được mô tả trong chế độ nghiêm ngặt |

**Phân biệt hai lớp ràng buộc:**

```java
// Ở Spring MVC: server cho phép thiếu page, mặc định 0.
@RequestParam(name = "page", defaultValue = "0") int page

// Ở Spring REST Docs: bài kiểm thử có thể không gửi page.
parameterWithName("page")
    .description("Chỉ số trang từ 0; mặc định 0")
    .optional()
```

`.optional()` không biến `@RequestParam` thành tùy chọn, không đặt mặc định, và không cho phép giá trị sai kiểu. Ngược lại, `required = false` hay `defaultValue` trong controller không tự thêm `.optional()` vào descriptor. Khi không có `.optional()`, nếu request được tài liệu hóa thiếu tham số đã khai báo, REST Docs sẽ báo lỗi về tham số chưa có mặt.

## 6. `ignored()`: biết tham số nhưng ẩn khỏi snippet

Đôi khi request có thêm query parameter phục vụ đo đạc nội bộ, ví dụ `debugTrace`, nhưng tài liệu API công khai không cần giải thích nó.

```java
queryParameters(
    parameterWithName("q")
        .description("Từ khóa tìm bài viết"),
    parameterWithName("debugTrace").ignored()
)
```

Nếu request thực sự có `?q=spring&debugTrace=abc123`, descriptor `debugTrace` cho REST Docs biết tên tham số này đã được xử lý trong đặc tả snippet nhưng nó sẽ không xuất hiện trong bảng xuất ra. Không nên dùng `ignored()` để che đi tham số công khai mà client cần biết.

Khác biệt:

- **`optional()`:** vẫn có hàng mô tả trong tài liệu; request có thể vắng tên đó.
- **`ignored()`:** bỏ hàng mô tả khỏi tài liệu; thường dùng cho tham số kỹ thuật đã biết.
- **`relaxedQueryParameters(...)`:** cho phép các tên query parameter trong request chưa có descriptor, thích hợp khi cố ý ghi lại một phần hợp đồng.

Khi tạo tài liệu chính thức cho một endpoint, nên ưu tiên `queryParameters(...)` nghiêm ngặt và mô tả đủ các tham số client có thể gửi.

## 7. `attributes(...)` và template tùy biến

`description(...)` thường đủ cho bảng tài liệu mặc định. Nếu đội ngũ muốn thêm cột **Ví dụ** hoặc **Quy tắc**, có thể gắn thuộc tính tùy biến vào descriptor:

```java
import static org.springframework.restdocs.snippet.Attributes.key;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

parameterWithName("size")
    .description("Số kết quả trên một trang; mặc định 20")
    .attributes(
        key("example").value("20"),
        key("constraints").value("Số nguyên từ 1 đến 100")
    )
    .optional();
```

Hai thuộc tính `example` và `constraints` chỉ là metadata theo tên do dự án chọn, **không tự thêm cột vào snippet mặc định** và **không tự bật validation**. Để hiển thị chúng, đội ngũ phải tùy biến Mustache template tương ứng với `query-parameters`, sau đó kiểm tra đầu ra kết xuất. Nếu chỉ cần một trang tài liệu ngắn, ghi các thông tin này trực tiếp trong `description(...)` sẽ dễ duy trì hơn.

REST Docs không suy ra tự động mô tả tham số từ annotation `@RequestParam`, `@Min` hay `@Max` trong các ví dụ này. Nếu quy tắc giá trị cần được đảm bảo, hãy dùng validation ở tầng ứng dụng và assertion riêng trong kiểm thử.

## 8. Điều gì khiến kiểm thử sinh tài liệu thất bại?

`queryParameters(...)` ở chế độ mặc định kiểm tra sự nhất quán giữa **tập tên tham số trong request** và **tập descriptor**:

| Hiện tượng | Vì sao | Cách sửa |
| --- | --- | --- |
| Request gửi `page` nhưng chỉ có descriptor `q` | Tên `page` chưa được mô tả | Thêm `parameterWithName("page").description(...)` |
| Mô tả `sort` nhưng request không gửi `sort` | Descriptor bắt buộc bị thiếu trong request | Gửi `sort` trong test hoặc thêm `.optional()` nếu hợp đồng cho phép |
| Descriptor đặt `"tags"` nhưng request gửi `tag` | Hai tên khác nhau | Đồng bộ tên với HTTP request và controller |
| Test dùng `.param("q", "spring")` rồi mô tả bằng `queryParameters(...)` | Servlet request parameter không nhất thiết nằm trong URL | Dùng `.queryParam("q", "spring")` hoặc query string trong URL |
| Test chạy thành công nhưng không có `query-parameters.adoc` | Chưa gắn `queryParameters(...)` vào `document(...)`, hoặc tìm sai identifier/thư mục | Kiểm tra cấu hình REST Docs, identifier và output snippets |
| `?size=abc` vượt qua bước mô tả REST Docs | Descriptor không kiểm tra số nguyên, giới hạn hay enum | Thêm validation HTTP/Bean Validation và test dữ liệu sai |
| `?q=` có tên `q` nhưng vi phạm yêu cầu không được rỗng | Kiểm tra tên khác kiểm tra nội dung | Test ứng dụng trả lỗi phù hợp, ví dụ HTTP 400 |

**Các quy tắc giá trị là hợp đồng nghiệp vụ, không phải tính năng mặc định của `parameterWithName`.** Một test tài liệu tốt kiểm tra cả response/status và các descriptor; muốn kiểm tra validation hãy viết thêm test cho trường hợp không hợp lệ.

## 9. Cách sử dụng cùng WebTestClient và REST Assured

Phần mô tả `parameterWithName(...)` và `queryParameters(...)` giữ nguyên khi đổi công cụ kiểm thử. Khác biệt nằm ở thao tác gọi HTTP và cách gắn `document(...)`:

- **MockMvc:** `mockMvc.perform(...).andDo(document("id", queryParameters(...)))`; gửi query string qua `queryParam(...)` hoặc URL.
- **WebTestClient:** tạo URI có query string rồi dùng `expectBody().consumeWith(document("id", queryParameters(...)))` sau khi cấu hình Spring REST Docs cho client.
- **REST Assured:** dùng `queryParam(...)` trong request và filter tài liệu hóa từ module `spring-restdocs-restassured`.

Ví dụ ý tưởng với WebTestClient đã được cấu hình REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
    .uri("/api/articles?q=spring&page=1")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("articles-search",
        queryParameters(
            parameterWithName("q").description("Từ khóa tìm bài viết"),
            parameterWithName("page").description("Trang từ 0").optional()
        )
    ));
```

Đoạn này minh họa phần gọi API; `webTestClient` phải được khởi tạo và cấu hình với Spring REST Docs phù hợp trước đó. Khi chuyển qua REST Assured, không cần viết lại ngữ nghĩa của `description` và `optional`.

## 10. Bài tập tự thực hành

Giả sử nhóm đang xây dựng API:

```http
GET /api/orders?status=PAID&page=0&size=25&sort=createdAt&sort=id HTTP/1.1
```

Hợp đồng dự kiến:

- `status`: tùy chọn; chỉ nhận `PENDING`, `PAID` hoặc `CANCELLED`.
- `page`: tùy chọn; số nguyên từ 0, mặc định 0.
- `size`: tùy chọn; số nguyên từ 1 đến 100, mặc định 25.
- `sort`: tùy chọn; có thể lặp để định nghĩa thứ tự ưu tiên nhiều trường.

**Yêu cầu:**

1. Viết bốn descriptor `parameterWithName(...)`, dùng `.optional()` cho tham số phù hợp và `.description(...)` để nêu đủ định dạng, mặc định, cách lặp.
2. Viết kiểm thử MockMvc gửi request mẫu và sinh `query-parameters.adoc`.
3. Thử thêm `currency=VND` vào request nhưng chưa mô tả; quan sát lỗi khi dùng `queryParameters(...)` nghiêm ngặt rồi bổ sung descriptor nếu đó là tham số hợp lệ.
4. Thử `size=-5` và `status=UNKNOWN`. Xác nhận rằng kiểm thử validation của server phát hiện sai dữ liệu; đừng dựa vào `description(...)` để phát hiện lỗi.
5. Chèn snippet vào Asciidoctor, cho task tạo tài liệu phụ thuộc task test và chạy quy trình đó trong CI.

**Tiêu chí hoàn thành:** Descriptor phản ánh tên và ngữ nghĩa thực tế của query string; request hợp lệ sinh snippet; thay đổi tên hoặc thiếu tham số bắt buộc khiến kiểm thử tài liệu phát hiện vấn đề; validation giá trị được kiểm tra độc lập.

## 11. Ghi nhớ khi triển khai dự án

`parameterWithName(...)` giúp đưa tri thức về tên và ý nghĩa từng query parameter vào bài kiểm thử HTTP; `description(...)` là phần người dùng API đọc trực tiếp. Khi kết hợp descriptor với `queryParameters(...)` và `document(...)`, tài liệu được sinh lại từ test trong build/CI. Hãy ưu tiên mô tả rõ mặc định, giới hạn, tham số lặp và optional, đồng thời kiểm tra ràng buộc giá trị bằng test ứng dụng riêng.

### Tài liệu tham khảo

- [Spring REST Docs Reference — Documenting your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/index.html)
- [Spring REST Docs Reference — Query parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Javadoc — `RequestDocumentation`](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html)
- [Javadoc — `ParameterDescriptor`](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/ParameterDescriptor.html)
