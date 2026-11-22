# Tham số query nhiều giá trị và cách biểu diễn trong Spring REST Docs

## 1. Vì sao một query parameter có thể có nhiều giá trị?

Trong API tìm kiếm, một bộ lọc thường cần nhận nhiều lựa chọn: danh sách nhãn, nhiều mã sản phẩm, nhiều trạng thái hoặc nhiều tiêu chí sắp xếp. Xét request:

```http
GET /api/articles?tag=java&tag=spring&sort=createdAt:desc&sort=title:asc&page=0 HTTP/1.1
Host: api.example.test
```

Ở đây:

- Tên `tag` có **hai giá trị**: `java` và `spring`.
- Tên `sort` có **hai giá trị**: `createdAt:desc` và `title:asc`.
- Tên `page` chỉ có **một giá trị**: `0`.

Mỗi cặp `name=value` là một lần xuất hiện trong query string. Khi một tên lặp lại, ứng dụng phải định nghĩa cách xử lý các giá trị: lấy tất cả, lấy đầu tiên, lấy cuối cùng, loại trùng hoặc báo lỗi. Không nên suy ra cách xử lý chỉ từ cú pháp URL.

**Spring REST Docs** thuộc module `SPRING_REST_DOCS` giúp sinh tài liệu REST API có thể kiểm chứng từ kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Chủ đề bài này là **Query parameters**, cụ thể là cách biểu diễn và mô tả **tham số nhiều giá trị** bằng `queryParameters(...)` và `parameterWithName(...)`, để đoạn mô tả có thể đưa vào Asciidoctor/Markdown và chạy cùng build/CI.

Sau bài học, bạn có thể:

1. Phân biệt nhiều cặp query cùng tên với giá trị duy nhất chứa dấu phân cách.
2. Viết hợp đồng API về số lượng giá trị, thứ tự, giá trị trùng và giá trị rỗng.
3. Kiểm thử request nhiều giá trị qua MockMvc, WebTestClient hoặc REST Assured.
4. Sinh snippet tài liệu query parameters và thêm các assertion cần thiết để kiểm chứng ngữ nghĩa.

## 2. Các kiểu biểu diễn thường gặp

Không có một quy ước duy nhất buộc mọi REST API phải diễn giải chuỗi giá trị theo cùng cách. Các biểu diễn dưới đây **không đương nhiên tương đương**:

| Query string | Ý nghĩa ở mức tên/giá trị HTTP | Điều cần quy định trong API |
| --- | --- | --- |
| `?tag=java&tag=spring` | Tên `tag` xuất hiện hai lần, mỗi lần một giá trị | Có nhận cả hai giá trị không? Kết hợp theo OR hay AND? |
| `?tag=java,spring` | Tên `tag` xuất hiện một lần, giá trị là chuỗi `java,spring` | Dấu phẩy là ký tự dữ liệu hay ký tự phân tách? |
| `?tag[]=java&tag[]=spring` | Tên được truyền là `tag[]`, xuất hiện hai lần | Framework có hiểu cú pháp ngoặc vuông hay cần xử lý riêng? |
| `?tag[0]=java&tag[1]=spring` | Hai tên `tag[0]` và `tag[1]` khác nhau | Có hỗ trợ chỉ số trong tên và xử lý chỉ số thiếu/trùng không? |
| `?sort=createdAt,desc&sort=title,asc` | Hai giá trị của `sort`, mỗi giá trị có dấu phẩy | Mỗi giá trị gồm `field,direction`; thứ tự các lần lặp có ý nghĩa không? |
| `?tag=java&tag=java` | Một tên xuất hiện hai lần với giá trị trùng nhau | Có giữ giá trị trùng, loại trùng hay từ chối không? |

### 2.1. Lặp lại cùng một tên: `tag=java&tag=spring`

Đây là cách biểu diễn trực tiếp nhiều giá trị trong query string:

```http
GET /api/articles?tag=java&tag=spring HTTP/1.1
```

Ưu điểm là không cần đặt ra một dấu phân tách riêng. Client gửi mỗi phần tử bằng một lần xuất hiện của tên `tag`. Với Spring MVC, `@RequestParam List<String>` hoặc `@RequestParam MultiValueMap<String, String>` có thể xử lý cách truyền này.

Ví dụ hợp đồng do nhóm API lựa chọn:

> `tag` cho phép lặp nhiều lần. API tìm các bài viết mang **ít nhất một** nhãn trong danh sách (logic OR). Nếu gửi nhiều nhãn giống nhau, server chỉ xét nhãn đó một lần.

REST Docs ghi lại diễn giải trên trong `description(...)`. Phần lọc theo OR và loại trùng cần được triển khai, kiểm thử ở tầng ứng dụng.

### 2.2. Phân tách trong một giá trị: `tag=java,spring`

```http
GET /api/articles?tag=java,spring HTTP/1.1
```

Ở cấp query string, đây là **một** cặp tên/giá trị. Việc tách thành hai phần tử chỉ xảy ra nếu cơ chế binding hoặc logic ứng dụng định nghĩa dấu phẩy là dấu phân tách. Một số cách binding collection của Spring MVC có thể chuyển chuỗi phân tách bằng dấu phẩy thành danh sách; hành vi cụ thể cần được kiểm thử với kiểu tham số, converter và cấu hình của endpoint.

Không nên ghi cả hai cách (`tag=a&tag=b` và `tag=a,b`) là được hỗ trợ chỉ vì một test hiện tại nhận cả hai. Nếu giá trị hợp lệ có thể chứa dấu phẩy, cách biểu diễn này còn cần quy tắc escaping/quoting rõ ràng.

### 2.3. Dùng dấu ngoặc vuông hoặc chỉ số trong tên

Một số thư viện client có thể gửi:

```http
GET /api/articles?tag%5B%5D=java&tag%5B%5D=spring HTTP/1.1
```

`%5B` và `%5D` lần lượt là mã URL của `[` và `]`. Sau URL-decoding, tên tham số là `tag[]`. Đây không phải luôn là tên `tag`; cần kiểm tra chính xác cách server binding. Nếu API yêu cầu `tag[]`, descriptor REST Docs phải mô tả tên tương ứng:

```java
queryParameters(
    parameterWithName("tag[]")
        .description("Danh sách nhãn; tên chứa dấu ngoặc vuông và có thể lặp")
)
```

Spring MVC có một số hỗ trợ binding tên có hậu tố `[]`, nhưng mức hỗ trợ phụ thuộc kiểu tham số và cách gửi request. Không mặc định áp dụng quy ước của một thư viện JavaScript cho mọi REST API.

## 3. URL encoding, thứ tự và giá trị rỗng

### 3.1. Encode từng thành phần đúng cách

Giá trị query có thể chứa dấu cách, dấu `+`, dấu `&`, dấu phẩy hoặc ký tự Unicode. Khi tự xây dựng URL, các ký tự có ý nghĩa cú pháp phải được percent-encode đúng cách:

```http
GET /api/articles?tag=C%2B%2B&tag=spring%20web HTTP/1.1
```

Khi giải mã, hai giá trị mong đợi là `C++` và `spring web`. Nếu viết `tag=C++` trực tiếp, dấu `+` có thể bị diễn giải thành khoảng trắng trong một số cơ chế xử lý query theo quy tắc form-encoding. Không nên tự ghép URL từ dữ liệu chưa encode.

Ví dụ với MockMvc:

```java
mockMvc.perform(get("/api/articles")
        .queryParam("tag", "C++", "spring web"));
```

Trường hợp dùng URI builder hoặc HTTP client, hãy để công cụ xây dựng query và encode thành phần theo API của công cụ đó. Kiểm tra request thực tế khi xử lý giá trị chứa ký tự đặc biệt.

### 3.2. Có phụ thuộc thứ tự không?

Hai request sau chứa cùng tập giá trị `tag`:

```http
GET /api/articles?tag=java&tag=spring HTTP/1.1
GET /api/articles?tag=spring&tag=java HTTP/1.1
```

Với bộ lọc kiểu tập hợp, thứ tự thường không quan trọng. Với tham số `sort`, thứ tự có thể được sử dụng để xác định ưu tiên sắp xếp. Nếu thứ tự có ý nghĩa, tài liệu phải quy định rõ và kiểm thử bảo toàn thứ tự ở các lớp client/server được hỗ trợ. Không nên dựa vào thứ tự của query parameters mà chưa có hợp đồng hoặc chưa kiểm thử.

### 3.3. Giá trị rỗng khác với tham số vắng mặt

| Request | Dữ liệu thể hiện | Câu hỏi nghiệp vụ |
| --- | --- | --- |
| `/api/articles` | Không có tham số `tag` | Có dùng bộ lọc mặc định không? |
| `/api/articles?tag=` | Có tên `tag` với giá trị rỗng | Chấp nhận, bỏ qua hay trả lỗi 400? |
| `/api/articles?tag=java&tag=` | Một giá trị có nội dung và một giá trị rỗng | Loại giá trị rỗng hay từ chối cả request? |
| `/api/articles?tag=java&tag=java` | Có hai giá trị trùng nhau | Có loại trùng không? |

`queryParameters(...)` chủ yếu kiểm tra **tên tham số và việc tên đó có xuất hiện**, không tự phân biệt các quy tắc nghiệp vụ ở bảng trên. Cần assertion/validation riêng cho giá trị rỗng, số lần lặp và giá trị trùng.

## 4. Binding tham số nhiều giá trị trong Spring MVC

Với API nhận nhiều nhãn, một kiểu khai báo phổ biến là:

```java
@GetMapping("/api/articles")
public List<Article> findArticles(
        @RequestParam(name = "tag", required = false) List<String> tags) {
    // Xử lý danh sách giá trị của tag.
    return articleService.findByTags(tags);
}
```

Khi cần đọc **chính xác mọi giá trị theo từng tên** mà không gắn logic vào một tên cố định, có thể dùng `MultiValueMap`:

```java
import java.util.List;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/api/filter-preview")
public List<String> preview(@RequestParam MultiValueMap<String, String> parameters) {
    return parameters.getOrDefault("tag", List.of());
}
```

`MultiValueMap` biểu diễn một khóa có nhiều giá trị. Kiểu dữ liệu này giúp quan sát các lần xuất hiện lặp, song việc giới hạn tên tham số được phép, dữ liệu rỗng và số lượng tối đa vẫn phải do API quy định.

Với `@RequestParam List<String>`, việc chuyển đổi một giá trị như `"java,spring"` thành danh sách có thể khác với cách nhận nhiều cặp `tag`. Hãy viết test cho đúng biểu diễn mà API công bố, đặc biệt khi áp dụng converter tùy biến.

## 5. Document với `parameterWithName` và `queryParameters`

Giả sử endpoint chấp nhận `tag` lặp nhiều lần, `sort` lặp nhiều lần và `page` một giá trị:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("tag")
        .description("Nhãn cần lọc; được truyền nhiều lần: tag=java&tag=spring"),
    parameterWithName("sort")
        .description("Có thể lặp: sort=field:direction; thứ tự xuất hiện là thứ tự ưu tiên")
        .optional(),
    parameterWithName("page")
        .description("Số trang bắt đầu từ 0, mặc định 0; chỉ nhận một giá trị")
        .optional()
)
```

**Một tên được mô tả bằng một descriptor**, kể cả khi request gửi tên đó nhiều lần. Không cần tạo hai `parameterWithName("tag")` để ghi nhận `tag=java&tag=spring`.

| Đặc điểm | Điều REST Docs có thể kiểm tra | Điều ứng dụng phải tự kiểm tra |
| --- | --- | --- |
| Có tên `tag` hay không | Có, với descriptor bắt buộc hoặc `optional()` | Giá trị rỗng/trống có hợp lệ không |
| Có tên ngoài mô tả như `color` | Chế độ `queryParameters(...)` nghiêm ngặt có thể phát hiện | Server có nên chấp nhận `color` không |
| `tag` xuất hiện hai lần | Ghi nhận tên `tag`, sinh một hàng mô tả | Số lần lặp tối đa, trùng lặp, AND/OR |
| `sort` lặp theo thứ tự | Mô tả bằng văn bản | Parser, trường hợp sai định dạng và thứ tự ưu tiên |
| `page` chứa `abc` | Không đánh giá kiểu số từ `description` | Conversion, validation, HTTP status |

### Phân biệt các cơ chế mô tả

- `.optional()`: cho phép tên parameter không xuất hiện trong request kiểm thử; không có nghĩa chấp nhận mọi giá trị.
- `.ignored()`: biết tên parameter nhưng loại hàng đó khỏi bảng tài liệu.
- `relaxedQueryParameters(...)`: cho phép request có những tên query parameter chưa có descriptor; vẫn kiểm tra sự xuất hiện của descriptor bắt buộc.

Với API chính thức, nên ưu tiên `queryParameters(...)` ở chế độ mặc định để phát hiện khi có tên mới xuất hiện trong request nhưng chưa được mô tả.

## 6. Ví dụ hoàn chỉnh: MockMvc + JUnit 5 + snippet

Controller minh họa trả chuỗi có thể kiểm tra nhanh, thay cho danh sách JSON trong ứng dụng thực tế:

```java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ArticleController {

    @GetMapping("/api/articles")
    public String findArticles(
            @RequestParam("tag") List<String> tags,
            @RequestParam(name = "sort", required = false) List<String> sorts,
            @RequestParam(name = "page", defaultValue = "0") int page) {

        List<String> safeSorts = sorts == null ? List.of() : sorts;
        return "tags=" + String.join("|", tags)
                + ";sorts=" + String.join("|", safeSorts)
                + ";page=" + page;
    }
}
```

Kiểm thử document:

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
class ArticleMultiValueQueryDocsTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ArticleController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsRepeatedQueryParameters() throws Exception {
        mockMvc.perform(get("/api/articles")
                        .queryParam("tag", "java", "spring")
                        .queryParam("sort", "createdAt:desc", "title:asc")
                        .queryParam("page", "0"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "tags=java|spring;sorts=createdAt:desc|title:asc;page=0"))
                .andDo(document("articles-multi-value-query",
                        queryParameters(
                                parameterWithName("tag")
                                        .description("Nhãn lọc; lặp tag để chọn nhiều nhãn"),
                                parameterWithName("sort")
                                        .description("Lặp sort=field:direction để ưu tiên nhiều tiêu chí")
                                        .optional(),
                                parameterWithName("page")
                                        .description("Trang từ 0; mặc định 0; một giá trị")
                                        .optional()
                        )));
    }
}
```

**Ý nghĩa từng phần:**

1. `get(...).queryParam("tag", "java", "spring")` tạo query string có hai giá trị cho cùng tên `tag`. Để mô tả query parameters bằng REST Docs, sử dụng `queryParam(...)` hoặc query string trong URL; `param(...)` của MockMvc chỉ thêm Servlet request parameters tổng quát nên có thể không xác định được nguồn query string.
2. Assertion `content().string(...)` xác minh binding và thứ tự giá trị mà ví dụ kỳ vọng. Đây là kiểm tra **hành vi thực tế**, ngoài phạm vi `queryParameters(...)`.
3. `parameterWithName("tag")` chỉ xuất hiện một lần dù gửi hai giá trị. `.description(...)` công bố cách sử dụng lặp cho client.
4. `sort` và `page` dùng `.optional()` vì server cho phép bỏ chúng khỏi request. Điều này tương ứng với `required = false` và `defaultValue` ở controller, nhưng REST Docs không tự suy luận những annotation đó.
5. `document("articles-multi-value-query", ...)` tạo các snippet sau khi kiểm thử chạy thành công và Spring REST Docs đã được cấu hình.

Trong Gradle dùng vị trí `build/generated-snippets`, snippet query parameters sẽ ở:

```text
build/generated-snippets/
└── articles-multi-value-query/
    ├── query-parameters.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    └── ...
```

Đường dẫn thực tế phụ thuộc cấu hình output; với Maven thường là `target/generated-snippets`. Bảng được sinh có **một hàng cho mỗi tên** `tag`, `sort` và `page`, kèm phần `description(...)`; nó không tự tạo từng hàng cho `tag=java` và `tag=spring`.

### 6.1. Bổ sung kiểm thử về số lượng giá trị

REST Docs không tự xác minh rằng chỉ được lặp `tag` tối đa ba lần hoặc `page` chỉ được xuất hiện một lần. Nếu đây là yêu cầu của API, hãy kiểm tra số phần tử trong controller/service và viết test cho cả trường hợp hợp lệ và không hợp lệ.

Ví dụ kiểm thử một lần lặp duy nhất và nhiều lần lặp:

```java
// Trường hợp 1: một nhãn, sort bị bỏ qua.
mockMvc.perform(get("/api/articles")
        .queryParam("tag", "java"))
    .andExpect(status().isOk())
    .andExpect(content().string("tags=java;sorts=;page=0"));

// Trường hợp 2: hai nhãn, sort bị bỏ qua.
mockMvc.perform(get("/api/articles")
        .queryParam("tag", "java", "spring"))
    .andExpect(status().isOk())
    .andExpect(content().string("tags=java|spring;sorts=;page=0"));
```

Các test trên kiểm chứng giá trị binding của controller minh họa. Nếu hợp đồng yêu cầu từ chối phần tử rỗng, số lượng vượt ngưỡng hoặc giá trị không nằm trong danh mục, cần thêm validation và assertion HTTP 4xx cho các trường hợp đó.

## 7. Cách gửi tham số nhiều giá trị bằng WebTestClient và REST Assured

`parameterWithName(...)` và `queryParameters(...)` thuộc API tạo descriptor dùng chung cho các tích hợp Spring REST Docs. Khác biệt ở client gửi request:

### 7.1. WebTestClient

Đặt query string vào URI hoặc dùng URI builder, sau đó gắn snippet vào `consumeWith(document(...))`. Ví dụ khi `webTestClient` đã được cấu hình REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
        .uri(uriBuilder -> uriBuilder
                .path("/api/articles")
                .queryParam("tag", "java", "spring")
                .queryParam("sort", "createdAt:desc", "title:asc")
                .build())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("articles-multi-value-query",
                queryParameters(
                        parameterWithName("tag").description("Nhãn lọc, có thể lặp"),
                        parameterWithName("sort").description("Tiêu chí sắp xếp, có thể lặp")
                                .optional()
                )));
```

`UriBuilder.queryParam(...)` hỗ trợ truyền nhiều giá trị cho cùng một tên. Khi dùng builder, hãy kiểm tra encoding của các giá trị đặc biệt.

### 7.2. REST Assured

Với module `spring-restdocs-restassured` và filter tài liệu hóa đã được khởi tạo, có thể dùng `queryParam(...)` của REST Assured để truyền danh sách hoặc nhiều giá trị (theo overload của thư viện). Ý tưởng:

```java
given()
    .filter(documentationFilter)
    .queryParam("tag", "java", "spring")
    .when()
    .get("/api/articles")
    .then()
    .statusCode(200);
```

Đoạn này chỉ minh họa cách gửi request, chưa thể tự sinh snippet `query-parameters.adoc`: cần cấu hình filter tài liệu hóa với `document(..., queryParameters(...))` hoặc cơ chế tương ứng trong bài kiểm thử REST Assured đầy đủ.

## 8. Đưa snippet vào Asciidoctor/Markdown và build/CI

Nếu dùng Asciidoctor, chèn bảng tham số từ bài kiểm thử vào tài liệu endpoint:

```asciidoc
= Articles API

== Tìm bài viết theo nhiều nhãn

GET /api/articles

Ví dụ: /api/articles?tag=java&tag=spring

=== Query parameters

include::{snippets}/articles-multi-value-query/query-parameters.adoc[]
```

Để file `include` hoạt động, cấu hình biến `{snippets}` trỏ đến output của Spring REST Docs. Nếu muốn Markdown, Spring REST Docs cho phép chọn template format Markdown bằng `TemplateFormats.markdown()`; sau đó cần công cụ biên soạn Markdown phù hợp để đưa snippet vào trang cuối cùng.

Luồng xử lý khuyến nghị:

1. Khai báo dependency `spring-restdocs-mockmvc`, `spring-restdocs-webtestclient` hoặc `spring-restdocs-restassured` khớp công cụ kiểm thử.
2. Cho task `test` tạo đầu ra tại thư mục snippet (ví dụ `build/generated-snippets`).
3. Để task Asciidoctor/đóng gói tài liệu **phụ thuộc** task `test`, nhờ vậy snippet được sinh trước khi render trang.
4. Chạy test và build tài liệu trong CI. Khi test hoặc bước biên soạn tài liệu thất bại, pipeline cần báo lỗi để nhóm sửa hợp đồng API hoặc đường dẫn snippet.

REST Docs giúp kiểm tra mô tả *tên query parameters* trong request đang được kiểm thử. Để tài liệu nhiều giá trị đáng tin cậy, kiểm thử cần có thêm assertion cho số lượng, thứ tự, quy tắc AND/OR, loại trùng và validation nếu API cam kết các hành vi này.

## 9. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `tag=java&tag=spring` được ghi thành hai descriptor `tag` | Nhầm số lần xuất hiện với số tên tham số | Chỉ mô tả `parameterWithName("tag")` một lần |
| Document `tag` nhưng test gửi `tag[]` | Tên sau URL-decoding không khớp descriptor | Chuẩn hóa hợp đồng tên parameter và sửa request/descriptor |
| API nhận `tag=java,spring` nhưng có lúc không tách danh sách | Dựa vào converter hoặc định dạng phân tách chưa được quy định | Chọn một định dạng, kiểm thử hành vi parser và tài liệu hóa rõ |
| Các giá trị chứa `+`, `&` hoặc khoảng trắng bị đổi | Ghép URL không encode đúng | Dùng URI builder/queryParam và kiểm tra request gửi đi |
| `queryParameters(...)` thành công nhưng ứng dụng xử lý sai thứ tự `sort` | REST Docs kiểm tra tên, không kiểm tra thứ tự các giá trị | Thêm assertion kết quả xử lý và test ưu tiên sắp xếp |
| Parameter `tag` không có trong request nhưng descriptor bắt buộc | Tên tham số được khai báo nhưng thiếu trong test | Gửi ít nhất một giá trị hoặc thêm `optional()` nếu API cho phép bỏ qua |
| Có dữ liệu `tag` mà snippet không xuất hiện | Sai identifier, thiếu `queryParameters(...)` hoặc cấu hình output | Kiểm tra `document(...)`, thư mục snippets và file `include` |

## 10. Bài tập thực hành

Cho API giả định:

```http
GET /api/products?category=laptop&category=monitor&brand=acme&brand=example&sort=price:asc&page=1 HTTP/1.1
```

Hợp đồng:

- `category` có thể lặp; kết quả thuộc ít nhất một danh mục được chọn.
- `brand` có thể lặp; bộ lọc thương hiệu kết hợp với bộ lọc danh mục theo AND, nhưng các giá trị trong cùng nhóm brand kết hợp theo OR.
- `sort` có thể lặp, cú pháp `field:direction`; ưu tiên theo thứ tự xuất hiện; mặc định `createdAt:desc`.
- `page` chỉ nhận một số nguyên không âm; mặc định 0.
- Với `category` và `brand`, server từ chối giá trị rỗng và giới hạn tối đa 10 giá trị cho mỗi tên.

**Yêu cầu thực hiện:**

1. Viết controller hoặc endpoint minh họa tiếp nhận `List<String>` cho `category`, `brand`, `sort`.
2. Viết test MockMvc dùng `.queryParam("category", "laptop", "monitor")` và tương tự cho `brand`; ghi nhận cả hai giá trị bằng assertion.
3. Tạo `queryParameters(...)` với mỗi tên chỉ một `parameterWithName(...)`; viết `description(...)` nêu rõ cấu trúc, mặc định và cách kết hợp.
4. Thử `brand=acme&brand=` và 11 giá trị `category`. Bổ sung validation server và test xác nhận lỗi phù hợp, vì `queryParameters(...)` không tự kiểm tra các ràng buộc này.
5. Sinh `query-parameters.adoc`, chèn vào tài liệu Asciidoctor và kiểm tra lại bằng build/CI.

**Tiêu chí hoàn thành:** Tài liệu mô tả được cách gửi nhiều giá trị và cách server kết hợp chúng; snippet có một hàng cho mỗi tên query parameter; các test HTTP chứng minh việc binding và xử lý số lượng/thứ tự/giá trị theo hợp đồng.

## Tài liệu tham khảo

- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring Framework — @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
