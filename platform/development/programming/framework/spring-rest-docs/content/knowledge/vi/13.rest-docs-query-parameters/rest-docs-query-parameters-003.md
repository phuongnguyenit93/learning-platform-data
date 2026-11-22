# Tham số bắt buộc, tùy chọn và absent trong Spring REST Docs

## 1. Vì sao cần phân biệt ba trạng thái?

Giả sử API tìm sản phẩm hỗ trợ:

```http
GET /api/products?q=laptop&page=2&sort=price HTTP/1.1
Host: api.example.test
```

Theo hợp đồng API giả định:

- `q` là từ khóa **bắt buộc**.
- `page` là chỉ số trang **tùy chọn**, mặc định bằng `0` nếu không truyền.
- `sort` là cách sắp xếp **tùy chọn**, mặc định là `relevance`.

Client hoàn toàn có thể gửi `GET /api/products?q=laptop`. Khi đó `page` và `sort` **absent**: tên tham số không xuất hiện trong query string. Điều này khác với `?page=`, nơi tên `page` có mặt nhưng giá trị rỗng.

Trong module **SPRING_REST_DOCS**, tài liệu REST API được tạo từ bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Với chương **Query parameters**, Spring REST Docs dùng `queryParameters(...)` và các descriptor `parameterWithName(...)` để ghi nhận tham số nào phải xuất hiện trong *request được kiểm thử*, tham số nào được phép vắng mặt và tên tham số nào đã được mô tả. Việc kiểm tra này giúp phát hiện tài liệu lệch với ví dụ request khi chạy build/CI.

Sau bài học, bạn sẽ phân biệt được:

1. **Required**: descriptor được khai báo nhưng **không đánh dấu optional**; REST Docs đòi hỏi tham số xuất hiện trong request tài liệu hóa.
2. **Optional**: descriptor dùng `.optional()`; tham số có thể vắng mặt trong request tài liệu hóa.
3. **Absent**: trạng thái thực tế của request khi **không có tên tham số**; không phải một modifier riêng của REST Docs.
4. **Empty / blank / repeated**: tên tham số có mặt nhưng giá trị có thể rỗng, chứa khoảng trắng hoặc xuất hiện nhiều lần; chúng cần kiểm thử giá trị riêng.

## 2. Phân biệt absent, empty, blank và present

| Request | Trạng thái của `q` | Nhận xét |
| --- | --- | --- |
| `/api/products?page=1` | **Absent** | Không có khóa `q` trong query string |
| `/api/products?q=` | **Present, empty** | Có khóa `q` nhưng giá trị là chuỗi rỗng |
| `/api/products?q=%20%20` | **Present, blank** | Sau khi giải mã là hai khoảng trắng |
| `/api/products?q=laptop` | **Present, non-empty** | Có giá trị văn bản |
| `/api/products?q=laptop&q=mouse` | **Present, repeated** | Cùng tên `q` được gửi nhiều lần |

`/api/products?q` (không có dấu `=`) thường được phía server nhìn nhận là một tham số có giá trị rỗng, nhưng cách phân tích chuỗi truy vấn cụ thể phụ thuộc HTTP stack. Không nên dựa vào hình thức này để biểu diễn “absent”.

**Điểm quan trọng:** `queryParameters(...)` kiểm tra chủ yếu **tên và sự hiện diện** của query parameter; nó không tự kiểm tra `q` có rỗng, có chỉ gồm dấu cách, có đúng định dạng hay nằm trong danh sách giá trị hợp lệ. Hãy sử dụng validation trong ứng dụng và assertion HTTP để xác nhận những ràng buộc đó.

## 3. Required và optional ở lớp tài liệu Spring REST Docs

### 3.1. Descriptor bắt buộc

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("q")
        .description("Từ khóa tìm sản phẩm; bắt buộc, không được rỗng")
)
```

Descriptor `q` **không gọi** `optional()` nên là required theo cơ chế kiểm tra của REST Docs. Nếu kiểm thử cố tài liệu hóa request `GET /api/products?page=1`, snippet processor không tìm thấy `q` và báo lỗi về tham số đã mô tả nhưng thiếu trong request.

Không có phương thức `required()` cần gọi trong ví dụ này: **trạng thái mặc định là required**.

### 3.2. Descriptor tùy chọn

```java
queryParameters(
    parameterWithName("q")
        .description("Từ khóa bắt buộc"),
    parameterWithName("page")
        .description("Chỉ số trang bắt đầu từ 0; mặc định 0")
        .optional(),
    parameterWithName("sort")
        .description("Cách sắp xếp; mặc định relevance")
        .optional()
)
```

Với tập descriptor này, cả hai request sau đều có thể vượt qua bước kiểm tra **sự hiện diện tham số**:

```http
GET /api/products?q=laptop&page=2&sort=price HTTP/1.1
```

```http
GET /api/products?q=laptop HTTP/1.1
```

Trong request thứ hai, `page` và `sort` absent, nhưng không gây lỗi mô tả vì đã gọi `optional()`. Các descriptor vẫn là một phần của mô hình snippet, vì vậy vẫn có thể liệt kê chúng trong bảng tài liệu. Tuy nhiên, **đừng mặc định rằng template tạo tài liệu tự trình bày cột "Bắt buộc/Tùy chọn"**: cách hiển thị phụ thuộc template. Hãy ghi quy tắc optional và giá trị mặc định vào `description(...)` hoặc cấu hình cột riêng.

### 3.3. Bảng kết quả dự kiến của cơ chế kiểm tra

Giả sử có descriptor cho `q` (required), `page` (optional), `sort` (optional), ở chế độ mặc định của `queryParameters(...)`:

| Query string | Kiểm tra tên/sự hiện diện | Giải thích |
| --- | --- | --- |
| `?q=laptop` | Đạt | Hai tham số tùy chọn được phép absent |
| `?q=laptop&page=2` | Đạt | `sort` được phép absent |
| `?q=laptop&page=2&sort=price` | Đạt | Đã mô tả tất cả tên có mặt |
| `?page=2` | Không đạt | Thiếu `q` required |
| `?q=laptop&brand=acme` | Không đạt | `brand` có mặt nhưng chưa có descriptor |
| `?q=` | **Có thể đạt kiểm tra tên** | `q` có mặt; giá trị rỗng cần kiểm tra riêng ở ứng dụng |

Các đánh giá trên chỉ xét cơ chế mô tả query parameter, chưa bao gồm HTTP status do controller, security hay validation quyết định.

## 4. Required trong controller khác required trong tài liệu như thế nào?

Trong Spring MVC, `@RequestParam` xử lý việc nhận và ràng buộc tham số:

```java
@RequestParam("q") String q

@RequestParam(name = "page", defaultValue = "0") int page

@RequestParam(name = "sort", required = false) String sort
```

| Cấu hình của controller | Khi tên tham số absent | Quan hệ với REST Docs |
| --- | --- | --- |
| `@RequestParam("q") String q` | Theo mặc định, Spring MVC trả lỗi HTTP 400 vì thiếu `q` | Mô tả `parameterWithName("q")` không gọi `optional()` |
| `@RequestParam(name = "page", defaultValue = "0") int page` | Spring MVC dùng `0`; `defaultValue` cũng được dùng cho giá trị rỗng | Mô tả `page` bằng `.optional()` và ghi rõ mặc định |
| `@RequestParam(name = "sort", required = false) String sort` | Thông thường binding thành `null` với kiểu `String` | Mô tả `sort` bằng `.optional()` nếu client được phép bỏ qua |
| `@RequestParam("sort") Optional<String> sort` | Binding thành `Optional.empty()` khi vắng mặt | Mô tả bằng `.optional()` tương ứng |

Hai cơ chế thuộc **hai tầng độc lập**:

- **Controller/Spring MVC** quyết định request có hợp lệ không, cách chuyển giá trị sang Java và HTTP response.
- **Spring REST Docs** quyết định snippet có khớp những tên tham số trong request kiểm thử không.

`.optional()` trên `ParameterDescriptor` không biến một `@RequestParam` bắt buộc thành tùy chọn. Ngược lại, `required = false` hay `defaultValue` trên controller không tự thêm `.optional()` cho Spring REST Docs.

Nếu khai báo sai hai phía, có thể xuất hiện tình huống tài liệu nói “tùy chọn” nhưng server trả HTTP 400 khi thiếu tham số. Vì vậy phải viết test cho cả hành vi server và sự xuất hiện của snippet.

## 5. Ví dụ đầy đủ: optional thực sự absent trong MockMvc

Controller minh họa:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {

    @GetMapping("/api/products")
    public String search(
            @RequestParam("q") String q,
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "sort", required = false) String sort) {
        String effectiveSort = sort == null ? "relevance" : sort;
        return "q=" + q + ";page=" + page + ";sort=" + effectiveSort;
    }
}
```

Ở đây `q` bắt buộc. Nếu không gửi `page`, server dùng `0`; nếu không gửi `sort`, controller chủ động chọn `relevance`. Ví dụ dùng phản hồi văn bản để tập trung vào cách binding và tài liệu hóa; API thực tế có thể trả JSON và thêm test cho payload.

Kiểm thử đầy đủ với JUnit 5 và REST Docs:

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
class ProductQueryParametersTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setup(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ProductController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsAbsentOptionalParameters() throws Exception {
        mockMvc.perform(get("/api/products")
                        .queryParam("q", "laptop"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "q=laptop;page=0;sort=relevance"))
                .andDo(document("products-search",
                        queryParameters(
                                parameterWithName("q")
                                        .description("Từ khóa tìm kiếm; bắt buộc"),
                                parameterWithName("page")
                                        .description("Trang từ 0; mặc định 0")
                                        .optional(),
                                parameterWithName("sort")
                                        .description("Cách sắp xếp; mặc định relevance")
                                        .optional()
                        )));
    }

    @Test
    void rejectsAbsentRequiredParameter() throws Exception {
        mockMvc.perform(get("/api/products")
                        .queryParam("page", "2"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void acceptsEmptyQAtBindingLayerWithoutValidation() throws Exception {
        mockMvc.perform(get("/api/products")
                        .queryParam("q", ""))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "q=;page=0;sort=relevance"));
    }
}
```

**Phân tích ba bài kiểm thử:**

1. `documentsAbsentOptionalParameters` chỉ gửi `q`. Spring REST Docs vẫn sinh bảng mô tả `q`, `page` và `sort` vì hai tham số sau có `.optional()`. Assertion chứng minh server thực sự áp dụng mặc định.
2. `rejectsAbsentRequiredParameter` không gửi `q`. Spring MVC phát hiện thiếu `@RequestParam` bắt buộc và trả HTTP 400. Đây là test hành vi lỗi; không nên gắn cùng descriptor required vào bước sinh snippet query parameters cho request cố tình thiếu `q`.
3. `acceptsEmptyQAtBindingLayerWithoutValidation` gửi `q` nhưng giá trị bằng chuỗi rỗng. `@RequestParam("q")` kiểu `String` mặc định không tương đương `@NotBlank`. Nếu hợp đồng yêu cầu từ khóa khác rỗng, cần bổ sung validation hoặc kiểm tra nghiệp vụ, rồi điều chỉnh test kỳ vọng HTTP 400.

Việc dùng `queryParam(...)` thay cho `param(...)` của MockMvc là có chủ đích. `queryParam(...)` đưa tham số vào **query string** để Spring REST Docs có thể tài liệu hóa qua `queryParameters(...)`; `param(...)` chỉ tạo Servlet request parameters tổng quát, có thể không xuất hiện trong query string.

## 6. Kiểm thử absent, empty và invalid có mục đích khác nhau

Khi thiết kế bộ test, nên tách các trường hợp:

| Trường hợp | Ví dụ | Kiểm thử cần xác nhận |
| --- | --- | --- |
| Required có mặt | `?q=java` | Controller xử lý đúng, snippet tạo thành công |
| Optional absent | `?q=java`, không có `page` | Giá trị mặc định hoặc hành vi bỏ lọc phù hợp; snippet không báo thiếu `page` |
| Required absent | `?page=2`, không có `q` | HTTP 400 hoặc lỗi hợp đồng đã định nghĩa |
| Required present nhưng empty | `?q=` | Validation của server xử lý rỗng theo hợp đồng |
| Required present nhưng blank | `?q=%20%20` | Validation kiểm tra khoảng trắng nếu cấm |
| Optional present nhưng sai kiểu | `?q=java&page=abc` | Lỗi binding/validation được kiểm tra riêng |
| Optional present ngoài khoảng | `?q=java&page=-5` | Ràng buộc nghiệp vụ hoặc Bean Validation được kiểm tra riêng |
| Tên chưa mô tả | `?q=java&lang=vi` | `queryParameters(...)` nghiêm ngặt phát hiện `lang` chưa có descriptor |

Lưu ý: HTTP 400 cho rỗng, blank hoặc ngoài khoảng **không tự động xảy ra trong mọi ứng dụng**. Phải có quy tắc binding/validation tương ứng; mã lỗi và response body cần được test theo hợp đồng cụ thể.

### Trường hợp tham số lặp

```http
GET /api/products?q=phone&tag=android&tag=5g HTTP/1.1
```

Hai lần xuất hiện của `tag` không làm thay đổi cách đánh dấu required/optional trong descriptor:

```java
parameterWithName("tag")
    .description("Có thể lặp, ví dụ tag=android&tag=5g; bỏ qua để không lọc theo nhãn")
    .optional()
```

`.optional()` cho phép **không xuất hiện tên `tag`**. Nó không áp đặt giới hạn số lần lặp khi `tag` có mặt; giới hạn số lượng/giá trị phải được xử lý bằng validation ở ứng dụng.

## 7. Những điều `optional()` không làm

| Hiểu nhầm | Thực tế |
| --- | --- |
| Đã gọi `.optional()` thì controller tự nhận tham số tùy chọn | `.optional()` chỉ ảnh hưởng kiểm tra snippet |
| Required nghĩa là giá trị không được rỗng | Required ở REST Docs chủ yếu đòi hỏi **tên** xuất hiện |
| Tham số absent tương đương `?name=` | Absent là **không có tên**; `?name=` là có tên, giá trị rỗng |
| `.optional()` tự sinh cột “Optional” trên mọi tài liệu | Cột và cách hiển thị tùy template; nên mô tả ý nghĩa bằng chữ |
| Dùng `relaxedQueryParameters(...)` thì mọi tham số đều tùy chọn | Relaxed bỏ qua **tên chưa được mô tả**, còn descriptor đã khai báo vẫn cần có mặt nếu không đánh dấu optional |
| `.ignored()` giống `.optional()` | Ignored loại tham số đã biết khỏi bảng tài liệu; optional cho phép vắng mặt và vẫn mô tả nó |

Ví dụ về relaxed:

```java
import static org.springframework.restdocs.request.RequestDocumentation.relaxedQueryParameters;

relaxedQueryParameters(
    parameterWithName("q").description("Từ khóa; bắt buộc"),
    parameterWithName("page").description("Trang").optional()
)
```

Request có thêm `debug=true` không bị coi là chưa được mô tả trong relaxed mode. Nhưng nếu request thiếu `q`, nó vẫn không thỏa descriptor bắt buộc. Để tài liệu API chính thức phát hiện việc bổ sung tên tham số mà nhóm chưa ghi nhận, nên dùng `queryParameters(...)` nghiêm ngặt.

## 8. Tài liệu hóa riêng phản hồi lỗi khi required absent

Đối với HTTP 400 vì thiếu `q`, có thể tạo snippet **request/response** riêng để hướng dẫn client khắc phục. Chẳng hạn, trong một bài kiểm thử đã cấu hình REST Docs:

```java
mockMvc.perform(get("/api/products")
                .queryParam("page", "2"))
        .andExpect(status().isBadRequest())
        .andDo(document("products-search-missing-q"));
```

Lời gọi `document("products-search-missing-q")` mặc định có thể sinh các snippet HTTP request/response. Đoạn này **không truyền `queryParameters(...)` có descriptor `q` required**, bởi mục đích của test là cố tình gửi request thiếu `q`. Tài liệu endpoint chính vẫn lấy bảng query parameters từ test thành công `products-search`.

Với trường hợp cần xuất bảng tham số cho request lỗi, nên thiết kế descriptor thích hợp với chính request đó hoặc dùng một bài kiểm thử tài liệu riêng cho request hợp lệ. Không nên đánh dấu `q` là optional chỉ để hợp thức hóa bài kiểm thử lỗi nếu hợp đồng thật yêu cầu `q`.

## 9. Từ snippet đến Asciidoctor, Markdown và CI

Sau khi chạy test `documentsAbsentOptionalParameters`, đường dẫn snippet mặc định thường tương ứng:

```text
build/generated-snippets/products-search/query-parameters.adoc
```

Đường dẫn thực tế phụ thuộc cấu hình thư mục output của dự án; Maven thường dùng `target/generated-snippets/`.

Để nhúng bảng tham số trong `src/docs/asciidoc/products.adoc`:

```asciidoc
= Products API

== Tìm kiếm sản phẩm

GET /api/products

=== Query parameters

include::{snippets}/products-search/query-parameters.adoc[]

=== Ví dụ request thiếu q

include::{snippets}/products-search-missing-q/http-request.adoc[]
```

Biến `{snippets}` phải trỏ đến thư mục chứa snippet. Với Gradle hoặc Maven, quy trình nên:

1. Khai báo dependency kiểm thử `spring-restdocs-mockmvc` (hoặc `spring-restdocs-webtestclient`, `spring-restdocs-restassured`) phù hợp phiên bản dự án.
2. Cấu hình thư mục sinh snippet và cho task tạo tài liệu phụ thuộc vào test đã sinh snippet.
3. Chạy kiểm thử để tạo snippet; sau đó kết xuất Asciidoctor thành HTML, hoặc dùng template `TemplateFormats.markdown()` nếu dự án chủ đích xuất snippet Markdown.
4. Thực thi toàn bộ luồng trong CI; nếu snippet thiếu, tên bị đổi hoặc kiểm thử hợp đồng thất bại thì bản tài liệu không được coi là đã cập nhật thành công.

Markdown không có cơ chế `include` chuẩn như Asciidoctor; nếu dùng Markdown, cần một bước tổng hợp nội dung hoặc công cụ xuất bản hỗ trợ liên kết snippet tương ứng.

### WebTestClient và REST Assured có áp dụng quy tắc khác không?

Không. `parameterWithName("q")`, `.optional()` và `queryParameters(...)` dùng chung ý nghĩa trong ba tích hợp. Sự khác nhau chủ yếu là cách gửi request và gắn `document(...)`:

- **MockMvc:** `.queryParam(...)` trên request builder, sau đó `.andDo(document(...))`.
- **WebTestClient:** URI chứa query string, sau đó `.expectBody().consumeWith(document(...))`.
- **REST Assured:** `.queryParam(...)` và filter tài liệu hóa của REST Docs.

Trong cả ba trường hợp, absent phải được kiểm thử bằng request thực tế **không gửi tên tham số**; không nên giả lập absent bằng chuỗi rỗng.

## 10. Bài tập thực hành

Cho endpoint:

```http
GET /api/orders?customerId=42&page=0&size=20&status=PAID HTTP/1.1
```

Hợp đồng giả định:

- `customerId`: bắt buộc, là ID số nguyên dương.
- `page`: tùy chọn, số nguyên không âm, mặc định 0.
- `size`: tùy chọn, từ 1 đến 100, mặc định 20.
- `status`: tùy chọn, chỉ nhận `PENDING`, `PAID` hoặc `CANCELLED`; khi absent trả đơn hàng ở mọi trạng thái.

Hãy làm lần lượt:

1. Viết bốn descriptor `parameterWithName(...)`; để `customerId` required và gọi `.optional()` trên ba tham số còn lại.
2. Viết test thành công với request chỉ có `customerId=42`, xác minh giá trị mặc định ở server và sinh `query-parameters.adoc`.
3. Viết test thiếu `customerId` và xác minh lỗi HTTP theo hợp đồng. Không gọi `queryParameters(...)` của endpoint hợp lệ trong test này.
4. Viết test `customerId=` và `customerId=abc`; phân biệt **có tên nhưng giá trị sai** với absent.
5. Thêm `currency=VND` vào request thành công nhưng chưa có descriptor; quan sát lỗi mô tả ở chế độ nghiêm ngặt, sau đó điều chỉnh tài liệu hoặc API cho nhất quán.
6. Chèn snippet vào Asciidoctor và kiểm tra bước build/CI tạo được trang có bảng tham số.

**Tiêu chí đạt:** Test xác minh được tác động của absent lên hành vi controller; snippet không báo thiếu các descriptor optional; required vẫn được kiểm tra; test riêng bao phủ empty/invalid; tài liệu và HTTP request cùng tuân theo một hợp đồng.

## 11. Tổng kết

Trong Spring REST Docs, required/optional là **quy tắc kiểm tra descriptor** còn absent là **trạng thái của request**. `parameterWithName("...")` mặc định bắt buộc; thêm `.optional()` khi tên đó được phép vắng mặt. Hãy kiểm tra `@RequestParam` và validation ở server để tài liệu phản ánh hành vi thực tế, rồi đưa snippet vào Asciidoctor/Markdown và quy trình CI để giữ hợp đồng API luôn được kiểm chứng.

### Tài liệu tham khảo

- [Spring REST Docs Reference — Query parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — `RequestDocumentation` API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring Framework — `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
