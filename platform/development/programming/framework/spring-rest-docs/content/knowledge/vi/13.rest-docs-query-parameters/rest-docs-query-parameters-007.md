# Encoding giá trị query và ký tự đặc biệt trong Spring REST Docs

## 1. Vì sao encoding là một phần của hợp đồng API?

Query string thường chứa các giá trị do người dùng nhập: từ khóa có dấu cách, tên sản phẩm chứa dấu cộng, email có ký tự @, bộ lọc có dấu phẩy hoặc văn bản Unicode. Ví dụ:

```http
GET /api/products?q=wireless%20earbuds&tag=C%2B%2B&tag=audio HTTP/1.1
Host: api.example.test
Accept: application/json
```

Sau khi server giải mã đúng query string, các giá trị ứng dụng nhận được lần lượt là:

| Tên | Giá trị sau khi giải mã |
| --- | --- |
| `q` | `wireless earbuds` |
| `tag` (lần 1) | `C++` |
| `tag` (lần 2) | `audio` |

Nếu client encode sai, server có thể nhận một giá trị khác với ý định. Dấu `+` bị hiểu thành dấu cách, dấu `&` làm tách thêm parameter, dấu `#` có thể mở đầu fragment phía client và không được gửi trong HTTP request. Lỗi encoding vì thế ảnh hưởng trực tiếp đến tìm kiếm, lọc và khả năng tái tạo request từ tài liệu.

Trong module **SPRING_REST_DOCS**, Spring REST Docs tạo tài liệu API có thể kiểm chứng từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Bài thuộc chương **Query parameters** này trình bày cách biểu diễn giá trị query có ký tự đặc biệt, cách gửi request chính xác trong test và cách sinh snippet `query-parameters.adoc` để mô tả tên/ý nghĩa tham số. REST Docs ghi nhận request đã gửi; việc encode và decode phải được client, URI builder và ứng dụng thực hiện đúng.

Sau bài học, bạn có thể:

1. Phân biệt query string, URI component và percent-encoding.
2. Xử lý dấu cách, dấu cộng, dấu `&`, `=`, `#`, `%`, dấu phẩy, Unicode và nhiều giá trị lặp.
3. Dùng URI builder hoặc query parameter API thay vì nối chuỗi URL thủ công.
4. Kiểm thử giá trị trước/sau decoding bằng MockMvc và sinh tài liệu Spring REST Docs.

## 2. Cấu trúc query string và percent-encoding

Một URI có dạng tổng quát:

```text
scheme://authority/path?query#fragment
```

Phần query bắt đầu sau dấu `?` và kết thúc trước dấu `#` nếu có fragment. Query thường được biểu diễn bằng các cặp `name=value`, nối với nhau bằng `&`; dấu `=` đầu tiên phân cách tên với giá trị. Đây là quy ước phổ biến của ứng dụng web, và ứng dụng có thể định nghĩa thêm cấu trúc riêng cho giá trị.

Ví dụ:

```text
/api/products?q=wireless%20earbuds&category=audio
```

- `?` bắt đầu query.
- `q=wireless%20earbuds` là một cặp tên/giá trị.
- `&` ngăn cách cặp kế tiếp.
- `%20` là percent-encoding của byte `0x20`, biểu diễn dấu cách trong cách mã hóa UTF-8/ASCII-compatible.

### 2.1. Percent-encoding hoạt động như thế nào?

Percent-encoding thay byte của ký tự cần encode bằng ký hiệu `%HH`, trong đó `HH` là hai chữ số hexadecimal. Với UTF-8, một ký tự Unicode có thể tương ứng nhiều byte, do đó có thể sinh nhiều nhóm `%HH`.

Ví dụ:

| Ký tự/dữ liệu | Encoding thường gặp trong query |
| --- | --- |
| Dấu cách | `%20` |
| Dấu cộng `+` | `%2B` |
| Dấu và `&` | `%26` |
| Dấu bằng `=` | `%3D` |
| Dấu phần trăm `%` | `%25` |
| Dấu thăng `#` | `%23` |
| Dấu phẩy `,` | `%2C` (khi cần encode theo component) |
| Dấu gạch chéo `/` | `%2F` (khi cần encode theo component) |
| Chữ `ế` | `%E1%BA%BF` trong UTF-8 |

Percent-encoding áp dụng cho **giá trị hoặc tên component** theo ngữ cảnh. Không encode nguyên URI bằng một hàm encode component, vì như vậy các dấu cấu trúc như `:`, `/`, `?`, `&`, `=` cũng sẽ bị mã hóa và URI không còn đúng cấu trúc.

### 2.2. Dấu cách `%20` và dấu `+` không luôn giống nhau

Đây là nguồn lỗi phổ biến:

| Query | Khi giải mã theo quy ước form URL encoding (`application/x-www-form-urlencoded`) | Ý nghĩa |
| --- | --- | --- |
| `q=wireless%20earbuds` | `wireless earbuds` | Dấu cách percent-encoded |
| `q=wireless+earbuds` | `wireless earbuds` | Dấu `+` được hiểu là dấu cách trong quy ước form encoding |
| `q=C%2B%2B` | `C++` | Dấu cộng dữ liệu đã được encode |
| `q=C++` | Có thể thành `C  ` theo form decoding | Hai dấu cộng có thể bị diễn giải thành hai dấu cách |

Query component trong URI không có một quy tắc decoding phổ quát bắt buộc mọi framework phải xử lý dấu `+` như form body; nhiều framework web dùng quy ước form decoding cho query parameters. Vì vậy:

- Muốn truyền dấu cộng như dữ liệu, encode thành `%2B`.
- Muốn truyền dấu cách, sử dụng URI builder hoặc encoder phù hợp; `%20` là cách biểu diễn rõ nghĩa trong URI.
- Kiểm tra hành vi của HTTP client và server thực tế, nhất là khi ứng dụng nhận dữ liệu bằng các cơ chế khác nhau.

Không tự thay `%20` thành `+` hoặc ngược lại khi ghi ví dụ tài liệu nếu chưa xác minh client của dự án.

## 3. Các ký tự đặc biệt thường gặp

### 3.1. Dấu `&` và `=`

Nếu người dùng tìm kiếm chuỗi `rock & roll`, giá trị cần được gửi như một component:

```http
GET /api/search?q=rock%20%26%20roll HTTP/1.1
```

Nếu gửi `q=rock & roll` mà không encode, dấu `&` có thể mở đầu một parameter khác. Tương tự, khi giá trị chứa dấu `=`, hãy encode thành `%3D` nếu nó không phải dấu phân cách đầu tiên của cặp `name=value`.

### 3.2. Dấu `#`

Fragment được xử lý ở phía client và không được gửi như một phần của request target HTTP. Nếu giá trị tìm kiếm thực sự chứa `#spring`, phải encode dấu `#` thành `%23`:

```http
GET /api/search?q=%23spring HTTP/1.1
```

Viết `/api/search?q=#spring` có thể khiến `#spring` trở thành fragment thay vì dữ liệu server nhận được.

### 3.3. Dấu `%`

Dấu `%` mở đầu một escape sequence. Nếu dữ liệu thực sự có ký tự phần trăm, encode nó thành `%25`. Ví dụ giá trị `discount 20%` được biểu diễn:

```text
q=discount%2020%25
```

Chuỗi `%2G` không phải một escape sequence hợp lệ vì `G` không phải chữ số hexadecimal. Đừng encode thủ công bằng cách thay thế một số ký tự mà không kiểm tra chuỗi `%` đầu vào.

### 3.4. Dấu phẩy và định dạng nhiều giá trị

Nếu API quy ước `sort=price,asc`, dấu phẩy có thể được giữ nguyên như một phần của giá trị:

```text
sort=price,asc
```

Hoặc được encode thành:

```text
sort=price%2Casc
```

Server thường có thể giải mã ra cùng chuỗi `price,asc`, nhưng API client và gateway có thể áp dụng quy tắc riêng. Khi query có nhiều lần xuất hiện cùng tên, ví dụ `sort=price%2Casc&sort=id%2Casc`, mỗi lần xuất hiện vẫn là một giá trị cho tên `sort`.

### 3.5. Unicode và tiếng Việt

Giá trị `điện thoại` khi encode UTF-8 có dạng percent-encoded nhiều byte. Không tự encode từng ký tự theo mã Unicode code point; percent-encoding dùng byte của charset (thực tế hiện nay nên dùng UTF-8).

Ví dụ URL có thể được URI builder tạo ra:

```http
GET /api/search?q=%C4%91i%E1%BB%87n%20tho%E1%BA%A1i HTTP/1.1
```

Khi server giải mã đúng UTF-8, ứng dụng nhận `điện thoại`. Nếu một tầng proxy, gateway hoặc ứng dụng giải mã lặp lại, ký tự có thể bị hỏng hoặc dữ liệu trở thành chuỗi khác. Chỉ giải mã đúng một lần theo contract của framework; tránh gọi decoder thủ công trên giá trị mà Spring đã binding.

## 4. Tên query parameter và giá trị query parameter

Tên parameter cũng có thể cần encoding. Ví dụ tên `filter[name]` có thể được biểu diễn:

```text
filter%5Bname%5D=wireless
```

Sau khi decode, tên là `filter[name]`. Spring REST Docs mô tả **tên ứng dụng nhìn thấy theo cách binding của request**, nên test cần thống nhất descriptor với tên thực tế. Không tự đổi `filter[name]` thành `filter.name` hoặc `filterName` nếu controller không áp dụng quy ước đó.

Một số lưu ý:

- Tên và giá trị đều có thể chứa ký tự phải encode.
- Không encode dấu cấu trúc `&` và `=` khi chúng đang dùng để nối cặp, nhưng encode khi chúng xuất hiện bên trong component.
- Một tên có thể xuất hiện nhiều lần: `tag=java&tag=spring`. Mỗi giá trị phải được encode riêng.
- Query parameter vắng mặt (`/search`) khác với có tên nhưng giá trị rỗng (`/search?q=`), và khác với giá trị chỉ chứa dấu cách (`/search?q=%20`).
- Nếu API cho phép nhiều giá trị trong một component phân tách bằng dấu phẩy, hãy định nghĩa rõ việc xử lý dấu phẩy bên trong dữ liệu thực.

## 5. Dùng URI builder thay vì nối URL thủ công

Nguyên tắc quan trọng: **để thư viện URI/HTTP client encode từng component**. Không tự nối dữ liệu không đáng tin cậy vào URL bằng toán tử `+`.

### 5.1. Spring `UriComponentsBuilder`

Ví dụ xây dựng request URI:

```java
import java.net.URI;
import org.springframework.web.util.UriComponentsBuilder;

String keyword = "rock & roll C++";

URI uri = UriComponentsBuilder
        .fromPath("/api/search")
        .queryParam("q", "{keyword}")
        .encode()
        .buildAndExpand(keyword)
        .toUri();
```

Ở ví dụ trên, placeholder được expand sau bước encode component theo cách của builder. Có thể dùng URI builder ở tầng client/controller test để truyền dữ liệu có dấu cách, `&` và `+`; hãy xác minh URI cuối cùng theo phiên bản Spring đang dùng.

Một cách khác khi xây dựng URI trực tiếp:

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/api/search")
        .queryParam("q", "{value}")
        .buildAndExpand("C++ & Java")
        .encode()
        .toUri();
```

Thứ tự lời gọi `encode()`, `build()` và `buildAndExpand(...)` có ảnh hưởng đến cách encode template và giá trị expand. Với giá trị động, nên dùng placeholder/biến expand như ví dụ và kiểm tra URI thành phẩm thay vì giả định các overload có hành vi giống nhau.

### 5.2. MockMvc

MockMvc cung cấp `queryParam(...)` để tạo query string trong request:

```java
mockMvc.perform(get("/api/search")
        .queryParam("q", "rock & roll C++"));
```

Request builder nhận giá trị như dữ liệu và tạo query parameter. Không cần tự encode giá trị thành `rock%20%26%20roll%20C%2B%2B` trước khi truyền vào `queryParam(...)`; làm vậy có nguy cơ **double-encode** dấu `%` thành `%25`.

Nếu dùng raw URL:

```java
mockMvc.perform(get("/api/search?q=rock%20%26%20roll%20C%2B%2B"));
```

Ở trường hợp raw URL, chuỗi đã là URL-encoded; không tiếp tục encode thêm lần nữa. Chọn một cách biểu diễn trong mỗi test: truyền giá trị chưa encode qua API query builder, hoặc truyền raw URI đã encode đúng.

### 5.3. WebTestClient

Với WebTestClient:

```java
webTestClient.get()
        .uri(builder -> builder.path("/api/search")
                .queryParam("q", "rock & roll C++")
                .build())
        .exchange()
        .expectStatus().isOk();
```

URI builder chịu trách nhiệm cấu trúc URI. Trong bài test, vẫn cần assertion để xác nhận controller nhận đúng giá trị sau decoding, ví dụ response có trường `query` bằng `rock & roll C++`.

### 5.4. REST Assured

REST Assured cũng cung cấp API truyền query parameters:

```java
given()
        .queryParam("q", "rock & roll C++")
        .when()
        .get("/api/search")
        .then()
        .statusCode(200);
```

Dùng `queryParam(...)` để thư viện xây query string. Nếu cần document bằng Spring REST Docs, gắn filter đã được cấu hình của tích hợp REST Assured; đừng mã hóa thủ công giá trị rồi lại đưa qua một API tiếp tục encode.

## 6. Tránh double-encoding và decoding nhiều lần

Double-encoding xảy ra khi một giá trị đã percent-encoded lại được encode lần nữa:

| Giá trị mong muốn | Encode một lần | Encode thêm lần nữa |
| --- | --- | --- |
| Dấu cách | `%20` | `%2520` |
| Dấu cộng | `%2B` | `%252B` |
| Dấu phần trăm | `%25` | `%2525` |
| Dấu `&` | `%26` | `%2526` |

Ví dụ, ứng dụng muốn nhận `C++`:

1. Giá trị gốc: `C++`.
2. Encode đúng một lần: `C%2B%2B`.
3. Nếu encoder chạy thêm lần nữa, `%` trở thành `%25`, kết quả là `C%252B%252B`.
4. Server decode một lần nhận `C%2B%2B`, không phải `C++`.

Các lỗi thường gặp:

- Gọi `URLEncoder.encode(...)` rồi truyền kết quả vào `queryParam(...)` vốn sẽ encode lần nữa.
- Giải mã thủ công tham số đã được Spring binding.
- Dùng `URLDecoder` cho toàn URI thay vì cho component cần decode.
- Ghép dữ liệu người dùng vào URI trước khi encode và vô tình tạo thêm `&name=value`.
- Lấy raw query string, decode toàn chuỗi rồi parse bằng logic tự viết, khiến dấu `&` hoặc `=` trong giá trị bị hiểu nhầm là cấu trúc.

Hãy chọn một thành phần chịu trách nhiệm encode và một thành phần chịu trách nhiệm decode. Ở tầng controller Spring MVC, ưu tiên đọc giá trị qua `@RequestParam` hoặc `MultiValueMap` đã được framework binding.

## 7. Viết tài liệu Spring REST Docs cho giá trị có ký tự đặc biệt

Giả sử endpoint `GET /api/search` nhận:

- `q`: từ khóa có thể có dấu cách, dấu cộng, dấu `&` và Unicode.
- `tag`: tên lặp, mỗi giá trị là một nhãn độc lập.
- `sort`: giá trị dạng `field,direction`.

Mô tả trong Spring REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("q")
        .description("Từ khóa UTF-8; client encode component, ví dụ rock & roll hoặc C++"),
    parameterWithName("tag")
        .description("Nhãn lọc; có thể lặp nhiều lần, mỗi giá trị được encode riêng")
        .optional(),
    parameterWithName("sort")
        .description("Tiêu chí sắp xếp dạng field,direction; dấu phẩy thuộc giá trị")
        .optional()
)
```

`description(...)` nên nói cách client truyền giá trị và ý nghĩa sau decoding. Spring REST Docs không tự hiển thị một mẫu percent-encoded cho từng giá trị và không tự kiểm tra rằng dữ liệu Unicode được giải mã chính xác. Hãy kết hợp descriptor với assertion response hoặc assertion argument ở server nếu cần xác nhận giá trị.

### 7.1. Ví dụ controller nhận query

```java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SearchController {

    @GetMapping("/api/search")
    public SearchResult search(
            @RequestParam("q") String query,
            @RequestParam(name = "tag", required = false) List<String> tags,
            @RequestParam(name = "sort", required = false) List<String> sorts) {

        return new SearchResult(
                query,
                tags == null ? List.of() : tags,
                sorts == null ? List.of() : sorts);
    }
}

record SearchResult(String query, List<String> tags, List<String> sorts) {}
```

Ứng dụng thực tế có thể trả JSON. Response minh họa nếu gọi với từ khóa `rock & roll C++`:

```json
{
  "query": "rock & roll C++",
  "tags": ["C++", "audio"],
  "sorts": ["price,asc"]
}
```

Response body chứa giá trị đã decode; nó không nhất thiết chứa chuỗi percent-encoded như trên URL.

### 7.2. MockMvc/JUnit 5 tạo snippet

Ví dụ kiểm thử document:

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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class SearchQueryEncodingDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new SearchController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsSpecialCharactersInQueryValues() throws Exception {
        mockMvc.perform(get("/api/search")
                        .queryParam("q", "rock & roll C++")
                        .queryParam("tag", "C++", "audio")
                        .queryParam("sort", "price,asc"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.query").value("rock & roll C++"))
                .andExpect(jsonPath("$.tags[0]").value("C++"))
                .andExpect(jsonPath("$.tags[1]").value("audio"))
                .andExpect(jsonPath("$.sorts[0]").value("price,asc"))
                .andDo(document("search-query-encoding",
                        queryParameters(
                                parameterWithName("q")
                                        .description("Từ khóa UTF-8; có thể chứa khoảng trắng, &, +"),
                                parameterWithName("tag")
                                        .description("Nhãn; có thể lặp và mỗi giá trị được decode riêng")
                                        .optional(),
                                parameterWithName("sort")
                                        .description("Dạng field,direction; dấu phẩy thuộc giá trị")
                                        .optional()
                        )));
    }
}
```

Điểm đáng chú ý:

1. `queryParam("q", "rock & roll C++")` nhận **giá trị gốc**, để MockMvc request builder xây query parameter.
2. Assertion `jsonPath(...)` xác nhận controller nhận dữ liệu sau decoding, không chỉ xác nhận request có tên `q`.
3. Hai giá trị `tag` được truyền bằng một lần gọi `queryParam("tag", "C++", "audio")`; trong tài liệu chỉ cần một descriptor tên `tag`.
4. `queryParameters(...)` tạo snippet cho tên/ý nghĩa tham số; snippet không thay thế test cho giá trị đặc biệt.

Với Gradle cấu hình output ở `build/generated-snippets`, thư mục snippet sẽ là:

```text
build/generated-snippets/
  search-query-encoding/
    query-parameters.adoc
    http-request.adoc
    http-response.adoc
    curl-request.adoc
    ...
```

Đường dẫn thực tế phụ thuộc cấu hình build; Maven thường dùng `target/generated-snippets`.

## 8. Đưa snippet vào Asciidoctor/Markdown và CI

Trang Asciidoctor có thể lấy bảng query parameter trực tiếp từ test:

```asciidoc
= Search API

== Tìm kiếm

GET /api/search

=== Query parameters

include::{snippets}/search-query-encoding/query-parameters.adoc[]

=== Request

include::{snippets}/search-query-encoding/http-request.adoc[]

=== Response

include::{snippets}/search-query-encoding/http-response.adoc[]
```

Để ví dụ URI được đọc dễ hiểu, có thể thêm một đoạn request mẫu đã encode đúng:

```asciidoc
----
GET /api/search?q=rock%20%26%20roll%20C%2B%2B&tag=C%2B%2B&tag=audio&sort=price%2Casc
----
```

Trong Asciidoctor, biến `{snippets}` được cấu hình trỏ đến thư mục snippet của Spring REST Docs. Với Markdown, chọn template Markdown bằng `TemplateFormats.markdown()` và dùng bước ghép snippet tương ứng; Markdown cơ bản không có cơ chế `include` tiêu chuẩn như Asciidoctor.

Quy trình build/CI:

1. Khai báo dependency Spring REST Docs tương ứng với MockMvc, WebTestClient hoặc REST Assured và chọn phiên bản tương thích Spring Boot/Spring Framework.
2. Cấu hình thư mục snippet (ví dụ `build/generated-snippets`) là output của task kiểm thử.
3. Cấu hình task Asciidoctor/đóng gói tài liệu phụ thuộc vào task test để snippet luôn được tạo trước khi render.
4. Chạy test và xuất tài liệu trong CI. Nếu assertion về query value hoặc kiểm thử tài liệu thất bại, pipeline cần báo lỗi.

Ví dụ lệnh Gradle khi dự án đã cấu hình task:

```bash
./gradlew test asciidoctor
```

## 9. WebTestClient và REST Assured

### 9.1. WebTestClient

Khi `webTestClient` đã được cấu hình Spring REST Docs, dùng URI builder để gửi dữ liệu gốc:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
        .uri(builder -> builder.path("/api/search")
                .queryParam("q", "rock & roll C++")
                .queryParam("tag", "C++", "audio")
                .build())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.query").isEqualTo("rock & roll C++")
        .consumeWith(document("search-query-encoding-webclient",
                queryParameters(
                        parameterWithName("q")
                                .description("Từ khóa UTF-8, có thể chứa &, + và dấu cách"),
                        parameterWithName("tag")
                                .description("Nhãn lặp; mỗi giá trị được decode riêng")
                                .optional()
                )));
```

### 9.2. REST Assured

Với REST Assured, truyền giá trị gốc cho `queryParam(...)`:

```java
given()
        .filter(documentationFilter)
        .queryParam("q", "rock & roll C++")
        .queryParam("tag", "C++", "audio")
        .when()
        .get("/api/search")
        .then()
        .statusCode(200)
        .body("query", equalTo("rock & roll C++"));
```

`documentationFilter` cần được cấu hình với tích hợp `spring-restdocs-restassured` và danh sách snippet có `queryParameters(...)`. Câu lệnh HTTP ở trên là phần minh họa việc gửi dữ liệu và assertion; filter không tự suy ra mô tả.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Server nhận `C  ` thay cho `C++` | Dấu `+` không được encode và bị form decoder hiểu thành dấu cách | Encode dấu cộng thành `%2B` hoặc truyền giá trị gốc cho URI builder |
| Server nhận thêm parameter ngoài dự kiến sau `rock & roll` | Dấu `&` chưa được encode trong giá trị | Dùng `%26` hoặc query builder |
| Response nhận `%2520` thay vì dấu cách | Giá trị đã encode `%20` bị encode lần nữa | Chỉ encode một lần; truyền giá trị chưa encode vào `queryParam(...)` |
| Ký tự `#` không xuất hiện ở server | Fragment không được gửi trong HTTP request | Encode ký tự dữ liệu `#` thành `%23` |
| Tiếng Việt bị lỗi dấu | Charset encode/decode không thống nhất hoặc giải mã thủ công nhiều lần | Sử dụng UTF-8 và framework URI/HTTP binding |
| MockMvc test thành công nhưng snippet không thể hiện dấu query như kỳ vọng | Nhầm giá trị đã decode với raw request URI; template/request formatter có cách hiển thị riêng | Kiểm tra request URI và assertion controller; tài liệu hóa ý nghĩa tham số bằng descriptor |
| `queryParameters(...)` báo thiếu parameter | Dùng `.param(...)` thay vì query string thực hoặc tên descriptor sai | Dùng `.queryParam(...)` và đồng bộ tên theo request |
| Tài liệu mô tả ký tự đặc biệt nhưng không có test chứng minh | Chỉ có `description(...)`, chưa có assertion giá trị nhận được | Assert response/body hoặc tham số truyền vào service |

## 11. Bài tập thực hành

Xây dựng API:

```http
GET /api/catalog/search?q=áo%20thun%20C%2B%2B&brand=ACME&brand=North%20Star&tag=summer%26sale HTTP/1.1
```

Hợp đồng:

- `q` là chuỗi UTF-8, có thể chứa dấu cách và dấu cộng; bỏ qua thì không lọc từ khóa.
- `brand` có thể lặp, mỗi giá trị là một thương hiệu độc lập.
- `tag` có thể lặp; dấu `&` bên trong giá trị là dữ liệu, không mở đầu parameter mới.
- Khi tên parameter xuất hiện nhưng giá trị rỗng, API từ chối với HTTP 400.

Yêu cầu:

1. Viết controller nhận `q`, `List<String> brand` và `List<String> tag`.
2. Viết test MockMvc sử dụng `queryParam(...)` với **giá trị gốc**, không encode trước; assert controller nhận đúng `áo thun C++`, `North Star` và `summer&sale`.
3. Viết một test riêng cho raw URI đã percent-encode và so sánh kết quả decoding.
4. Thử cố ý double-encode `%20` và quan sát giá trị server nhận được; thêm test ngăn lỗi này quay lại.
5. Dùng `queryParameters(...)` và `parameterWithName(...)` sinh snippet; chèn snippet vào Asciidoctor và chạy cùng test trong CI.

**Tiêu chí hoàn thành:** Ký tự đặc biệt và Unicode được truyền đúng một lần, giá trị ứng dụng nhận được đúng như contract, query parameters lặp vẫn giữ đúng tên/giá trị, snippet được sinh từ request kiểm thử và tài liệu có thể kết xuất trong build.

## 12. Ghi nhớ

Percent-encoding biểu diễn byte của một thành phần URI; nó không phải thao tác encode toàn URL. Đặc biệt, dấu cộng, dấu cách, `&`, `=`, `#`, `%` và Unicode cần được xử lý đúng ngữ cảnh. Hãy dùng URI builder hoặc API `queryParam(...)`, tránh double-encoding và tự decode dữ liệu đã được framework binding. Trong Spring REST Docs, `queryParameters(...)` mô tả tên/thông tin tham số, còn assertion HTTP chứng minh giá trị sau decoding. Kết hợp cả hai giúp tài liệu API có thể kiểm chứng từ test và được duy trì trong build/CI.

### Tài liệu tham khảo

- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring Framework — URI Links](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html)
- [Spring Framework Javadoc — `UriComponentsBuilder`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html)
- [Java SE — `URLEncoder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLEncoder.html)
- [RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986)
