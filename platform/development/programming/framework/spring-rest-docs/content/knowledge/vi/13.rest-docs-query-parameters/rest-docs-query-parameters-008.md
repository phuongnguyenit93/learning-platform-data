# Xác nhận query parameter xuất hiện đúng trong request với Spring REST Docs

## 1. Mục tiêu

Một endpoint tìm kiếm có thể công bố các tham số `q`, `page`, `size` và `status`. Tài liệu ghi rằng client cần gửi `q`, có thể gửi `page` và `size`, còn `status` có thể lặp. Khi request thực tế thay đổi, tài liệu viết tay có thể nhanh chóng lỗi thời:

```http
GET /api/products?q=phone&page=1&size=20&status=ACTIVE HTTP/1.1
Host: api.example.test
Accept: application/json
```

Một thay đổi tưởng nhỏ như thêm `sort=price,asc`, đổi tên `status` thành `state`, hoặc vô tình gửi thêm `internalFlag=true` đều có thể làm hợp đồng HTTP khác với tài liệu đã công bố.

**Spring REST Docs** giúp kiểm chứng tài liệu bằng cách đối chiếu các descriptor với request HTTP thực sự được gửi trong bài kiểm thử. Với `queryParameters(...)` ở chế độ mặc định:

- Mọi query parameter xuất hiện trong request phải được mô tả hoặc được đánh dấu bỏ qua có chủ đích.
- Mọi descriptor bắt buộc phải có mặt trong request đang được document.
- Descriptor `optional()` có thể vắng mặt.

Như vậy, bài kiểm thử tài liệu phát hiện được tên tham số bị bỏ sót hoặc tham số được mô tả nhưng không xuất hiện như hợp đồng yêu cầu. Việc kiểm tra này hữu ích khi sinh snippet cho Asciidoctor/Markdown và đưa vào build/CI.

Trong module **SPRING_REST_DOCS**, các ví dụ áp dụng với MockMvc, WebTestClient hoặc REST Assured. Bài thuộc chương **Query parameters** này tập trung vào cách xác nhận **query string thực tế**, phân biệt tên tham số với giá trị, và xử lý các trường hợp đúng/sai một cách có chủ đích.

Sau bài học, bạn có thể:

1. Hiểu kiểm tra nghiêm ngặt của `queryParameters(...)` và lỗi khi request không khớp descriptor.
2. Phân biệt query parameters với Servlet request parameters hoặc form parameters.
3. Sử dụng `optional()`, `ignored()` và `relaxedQueryParameters(...)` đúng mục đích.
4. Viết test dương tính/âm tính để chứng minh tên query parameter xuất hiện đúng.
5. Sinh snippet tài liệu từ request kiểm thử và để CI phát hiện thay đổi hợp đồng.

## 2. `queryParameters(...)` xác nhận những điều gì?

Một khai báo cơ bản:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("q").description("Từ khóa tìm kiếm; bắt buộc"),
    parameterWithName("page").description("Trang bắt đầu từ 0").optional(),
    parameterWithName("size").description("Số kết quả trên một trang").optional()
)
```

Spring REST Docs tạo các `ParameterDescriptor` từ `parameterWithName(...)`. `queryParameters(...)` tạo snippet cho query parameters của request. Khi snippet được thực thi trong bài test, REST Docs xác nhận sự nhất quán giữa tên xuất hiện và các descriptor.

### 2.1. Hai chiều kiểm tra

| Tình huống | Hành vi trong chế độ mặc định |
| --- | --- |
| Request có `q`, descriptor có `q` | Được mô tả |
| Request có `trackingId`, không có descriptor tương ứng | Lỗi vì request có tham số chưa được document |
| Descriptor có `q`, request không có `q`, descriptor không optional | Lỗi vì tham số bắt buộc chưa xuất hiện |
| Descriptor có `page` và `.optional()`, request không có `page` | Hợp lệ |
| Descriptor `debug` có `.ignored()`, request có `debug` | Tham số được nhận diện nhưng không xuất hiện trong bảng snippet |
| Request có tên chưa mô tả khi dùng `relaxedQueryParameters(...)` | Được phép, nếu mục đích là document một phần request |

Kiểm tra này làm cho snippet trở thành một phần của kiểm thử hợp đồng HTTP. Ví dụ, nếu endpoint bắt đầu gửi thêm `sort` nhưng test document chưa mô tả nó, chế độ mặc định sẽ phát hiện thay đổi.

### 2.2. REST Docs kiểm tra tên, không xác nhận toàn bộ giá trị

`parameterWithName("page")` xác nhận tên `page`. Nó không tự kiểm tra:

- Giá trị `page` có phải số nguyên hay không.
- `page` có âm hoặc nằm trong giới hạn cho phép không.
- `status` có thuộc danh sách enum của ứng dụng không.
- Giá trị có rỗng, có whitespace hay có encoding đúng không.
- Một parameter lặp bao nhiêu lần hoặc các giá trị được kết hợp theo AND/OR như thế nào.

Các quy tắc này cần validation và assertion riêng trong kiểm thử ứng dụng. Đừng dùng thành công của bước document làm bằng chứng rằng mọi giá trị đều hợp lệ.

## 3. Query string thật và Servlet request parameters

Đây là điểm dễ mắc lỗi nhất khi sử dụng MockMvc.

### 3.1. Gửi query string đúng cách

Dùng `queryParam(...)` hoặc đưa query string vào URL:

```java
mockMvc.perform(get("/api/products")
        .queryParam("q", "phone")
        .queryParam("page", "1"));

// Cũng có thể biểu diễn query trực tiếp trên URL:
mockMvc.perform(get("/api/products?q=phone&page=1"));
```

Hai cách này thể hiện dữ liệu trong query string. Khi document bằng `queryParameters(...)`, đó là điều cần kiểm thử.

### 3.2. Vì sao `.param(...)` có thể gây nhầm?

MockMvc có API `.param(...)` để thiết lập Servlet request parameters. Servlet parameters có thể được hình thành từ query string hoặc form body `application/x-www-form-urlencoded`; vì vậy chỉ gọi `.param(...)` không nói rõ dữ liệu xuất phát từ đâu.

```java
// Ví dụ này thêm Servlet request parameter tổng quát:
mockMvc.perform(get("/api/products")
        .param("q", "phone"));

// Ví dụ này tạo query parameter rõ ràng:
mockMvc.perform(get("/api/products")
        .queryParam("q", "phone"));
```

Controller có `@RequestParam("q")` có thể nhận được giá trị trong cả hai cách. Tuy nhiên, `queryParameters(...)` được thiết kế cho query string. Để test thể hiện chính xác contract của URL, hãy dùng `.queryParam(...)` hoặc URL có `?q=...`.

### 3.3. Query parameter khác form parameter

| Vị trí của dữ liệu | Ví dụ HTTP | Công cụ document của Spring REST Docs |
| --- | --- | --- |
| Query string | `GET /api/products?q=phone` | `queryParameters(...)` |
| Path segment | `GET /api/products/42` | `pathParameters(...)` |
| URL-encoded form body | `POST /api/login` với `username=...` trong body | `formParameters(...)` |
| JSON request body | `POST /api/products` với JSON | `requestFields(...)` |
| HTTP header | `Accept-Language: vi` | `requestHeaders(...)` |

Không thay `queryParameters(...)` bằng `formParameters(...)` chỉ vì cả hai loại dữ liệu đều được controller nhận qua `@RequestParam`. Hãy chọn snippet dựa trên vị trí tham số thực sự xuất hiện trong HTTP request.

## 4. Descriptor bắt buộc, tùy chọn và bị bỏ qua

### 4.1. Descriptor bắt buộc

Nếu hợp đồng yêu cầu client luôn gửi `q` trong request được document:

```java
queryParameters(
    parameterWithName("q")
        .description("Từ khóa tìm kiếm; bắt buộc")
)
```

Nếu request test không có `q`, REST Docs báo lỗi. Đây là cách xác nhận test đã gửi đúng tên cần thiết.

### 4.2. Descriptor tùy chọn

Nếu client được phép không gửi `page`:

```java
queryParameters(
    parameterWithName("q").description("Từ khóa tìm kiếm"),
    parameterWithName("page")
        .description("Trang bắt đầu từ 0; mặc định 0")
        .optional()
)
```

Khi request có `q` nhưng không có `page`, snippet vẫn được tạo. `page` vẫn có hàng mô tả trong bảng vì nó là một phần của hợp đồng API.

`optional()` nói rằng tên có thể không xuất hiện trong request của bài kiểm thử. Nó không tự đặt giá trị mặc định cho controller và không thay đổi `@RequestParam(required = ...)`.

### 4.3. Descriptor bị bỏ qua có chủ đích

Một số request có thể chứa tham số nội bộ được biết trước nhưng không dành cho tài liệu công khai:

```java
queryParameters(
    parameterWithName("q").description("Từ khóa tìm kiếm"),
    parameterWithName("debugTrace").ignored()
)
```

`debugTrace` được khai báo để REST Docs biết tham số tồn tại, nhưng không được đưa vào bảng snippet. Đây là quyết định có chủ ý; không nên dùng `.ignored()` để che đi tham số công khai mà client cần hiểu.

### 4.4. Chế độ relaxed

```java
import static org.springframework.restdocs.request.RequestDocumentation.relaxedQueryParameters;

relaxedQueryParameters(
    parameterWithName("q").description("Từ khóa tìm kiếm")
)
```

`relaxedQueryParameters(...)` cho phép request có thêm query parameters không được mô tả trong danh sách descriptor. Descriptor đã khai báo nhưng không optional vẫn phải xuất hiện. Vì vậy, chế độ relaxed thích hợp khi tài liệu hóa một phần request, còn tài liệu API chính thức thường nên dùng chế độ nghiêm ngặt để phát hiện tham số mới bị bỏ sót.

## 5. Ví dụ hoàn chỉnh: xác nhận query parameters bằng MockMvc

Giả sử endpoint `GET /api/products` nhận `q` bắt buộc, còn `page` và `size` tùy chọn:

### 5.1. Controller minh họa

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductSearchController {

    @GetMapping("/api/products")
    public String search(
            @RequestParam("q") String query,
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "20") int size) {

        return "q=" + query + ";page=" + page + ";size=" + size;
    }
}
```

### 5.2. Bài test tài liệu hóa request hợp lệ

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
class ProductQueryParametersDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ProductSearchController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsQueryParametersThatAppearInRequest() throws Exception {
        mockMvc.perform(get("/api/products")
                        .queryParam("q", "wireless")
                        .queryParam("page", "1"))
                .andExpect(status().isOk())
                .andExpect(content().string("q=wireless;page=1;size=20"))
                .andDo(document("products-search",
                        queryParameters(
                                parameterWithName("q")
                                        .description("Từ khóa tìm kiếm; bắt buộc"),
                                parameterWithName("page")
                                        .description("Trang bắt đầu từ 0; mặc định 0")
                                        .optional(),
                                parameterWithName("size")
                                        .description("Kích thước trang; mặc định 20")
                                        .optional()
                        )));
    }
}
```

Phân tích:

1. Request thực có hai tên `q` và `page`.
2. Descriptor có ba tên `q`, `page`, `size`; `size` được optional nên không bắt buộc xuất hiện.
3. Assertion nội dung xác nhận `size` được controller đặt mặc định thành 20.
4. `queryParameters(...)` sinh bảng có cả ba tham số, mặc dù request không gửi `size`.

Ví dụ tạo một snippet có ý nghĩa rõ ràng: tài liệu cho client biết `size` có thể bỏ qua và giá trị mặc định là 20.

## 6. Kiểm thử các trường hợp không khớp

Một bài kiểm thử tài liệu thành công chứng minh một request hợp lệ đã được mô tả. Muốn xác minh chính sách nghiêm ngặt, hãy hiểu các trường hợp lỗi thường gặp và dùng chúng như tiêu chí rà soát.

### 6.1. Request có tên chưa được mô tả

Giả sử request gửi `trackingId` nhưng descriptor không khai báo:

```java
mockMvc.perform(get("/api/products")
        .queryParam("q", "wireless")
        .queryParam("trackingId", "abc-123"))
    .andExpect(status().isOk())
    .andDo(document("products-search",
        queryParameters(
            parameterWithName("q").description("Từ khóa tìm kiếm")
        )));
```

Trong chế độ nghiêm ngặt, bước document thất bại vì `trackingId` xuất hiện trong request nhưng chưa được mô tả hoặc đánh dấu ignored. Nếu `trackingId` là một phần hợp đồng public, hãy thêm descriptor và giải thích ý nghĩa. Nếu đó là tham số nội bộ có chủ đích, khai báo descriptor `.ignored()` để xử lý minh bạch.

### 6.2. Descriptor bắt buộc không xuất hiện

```java
mockMvc.perform(get("/api/products")
        .queryParam("page", "1"))
    .andExpect(status().isBadRequest())
    .andDo(document("products-search",
        queryParameters(
            parameterWithName("q").description("Từ khóa tìm kiếm; bắt buộc"),
            parameterWithName("page").description("Trang").optional()
        )));
```

Trong ví dụ này, controller yêu cầu `q`; request thiếu `q` nên controller trả lỗi 400. Request không phù hợp với descriptor bắt buộc. Nếu đang document **response lỗi** là một trường hợp riêng, có thể dùng một test riêng mô tả request lỗi và điều chỉnh descriptor đúng với contract của trường hợp đó. Đừng đánh dấu `q` optional chỉ để làm cho một test thiếu tham số vượt qua.

### 6.3. Chỉ mô tả một phần request

Nếu mục tiêu test là document phần tìm kiếm mà `trackingId` không nằm trong phạm vi tài liệu:

```java
document("products-search",
    relaxedQueryParameters(
        parameterWithName("q").description("Từ khóa tìm kiếm")
    )
)
```

Đây là cách chủ động nới kiểm tra các tên chưa được mô tả. Không sử dụng chế độ relaxed nếu mục tiêu của bài test là phát hiện tất cả query parameter mới.

## 7. Request nhiều giá trị và xác nhận tên lặp

Với request:

```http
GET /api/products?status=ACTIVE&status=PREORDER&sort=price,asc&sort=id,asc HTTP/1.1
```

Các tên `status` và `sort` mỗi tên xuất hiện nhiều lần. Trong `queryParameters(...)`, mỗi tên chỉ cần một descriptor:

```java
queryParameters(
    parameterWithName("status")
        .description("Trạng thái sản phẩm; có thể lặp để chọn nhiều trạng thái"),
    parameterWithName("sort")
        .description("Tiêu chí field,direction; có thể lặp theo thứ tự ưu tiên")
)
```

REST Docs xác nhận tên `status` và `sort` nằm trong request và tạo một hàng mô tả cho mỗi tên. Nó không tự xác nhận:

- Số lần lặp tối đa.
- Thứ tự các giá trị được giữ nguyên khi binding.
- Các giá trị có thuộc danh sách cho phép không.
- Nhiều trạng thái kết hợp bằng OR hay AND.

Các nội dung trên phải được mô tả rõ trong `description(...)` và được kiểm tra bằng assertion ứng dụng. Đặc biệt, đừng viết hai descriptor trùng tên chỉ vì request chứa hai giá trị.

## 8. Đọc snippet và tích hợp Asciidoctor/CI

Với cấu hình Gradle ghi snippet vào `build/generated-snippets`, test tạo thư mục:

```text
build/generated-snippets/
  products-search/
    query-parameters.adoc
    http-request.adoc
    http-response.adoc
    curl-request.adoc
    ...
```

Tên thư mục được tạo từ identifier `products-search`. Maven thường sử dụng `target/generated-snippets`; vị trí thực tế phụ thuộc cấu hình của dự án.

Trong tài liệu `src/docs/asciidoc/products.adoc`:

```asciidoc
= Products API

== Tìm kiếm sản phẩm

GET /api/products

=== Query parameters

include::{snippets}/products-search/query-parameters.adoc[]

=== Request

include::{snippets}/products-search/http-request.adoc[]
```

Biến `{snippets}` phải trỏ tới thư mục snippet. Nếu dùng Markdown, cấu hình `TemplateFormats.markdown()` để sinh snippet Markdown và dùng công cụ ghép tài liệu phù hợp; Markdown cơ bản không có cú pháp include chuẩn như Asciidoctor.

Quy trình build/CI:

1. Thêm dependency Spring REST Docs đúng tích hợp: MockMvc, WebTestClient hoặc REST Assured.
2. Cấu hình thư mục snippets làm output của test.
3. Cấu hình task Asciidoctor hoặc bước kết xuất tài liệu phụ thuộc task test.
4. Chạy test và xuất tài liệu trong CI; nếu descriptor không khớp request, test document thất bại và pipeline báo lỗi.

Ví dụ lệnh khi task đã được cấu hình:

```bash
./gradlew test asciidoctor
```

Khi thêm query parameter mới vào request, một bài test document dùng `queryParameters(...)` nghiêm ngặt sẽ giúp phát hiện thiếu descriptor. Khi đổi endpoint hoặc tên parameter, cần cập nhật cả request test lẫn tài liệu mô tả.

## 9. Cách làm với WebTestClient và REST Assured

### 9.1. WebTestClient

Với WebTestClient đã cấu hình Spring REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
        .uri(builder -> builder.path("/api/products")
                .queryParam("q", "wireless")
                .queryParam("page", 1)
                .build())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("products-search-webclient",
                queryParameters(
                        parameterWithName("q").description("Từ khóa; bắt buộc"),
                        parameterWithName("page").description("Trang từ 0").optional(),
                        parameterWithName("size").description("Kích thước trang").optional()
                )));
```

`q` và `page` xuất hiện trong URI được tạo; `size` là optional và có thể vắng mặt. Khi thêm query parameter vào URI mà quên descriptor ở chế độ nghiêm ngặt, bước document phát hiện mismatch.

### 9.2. REST Assured

REST Assured gửi query parameters qua API của request specification:

```java
given()
    .filter(documentationFilter)
    .queryParam("q", "wireless")
    .queryParam("page", 1)
    .when()
    .get("/api/products")
    .then()
    .statusCode(200);
```

`documentationFilter` đại diện cho filter đã cấu hình tích hợp Spring REST Docs với `document(..., queryParameters(...))`. Chỉ gọi `.queryParam(...)` chưa tự sinh snippet nếu không gắn filter document phù hợp.

## 10. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Controller đọc được `q` nhưng snippet báo không có query parameter | Test dùng `.param(...)` hoặc truyền dữ liệu qua form body | Dùng `.queryParam(...)` hoặc URL query thực |
| Request có `sort` khiến document thất bại | Chưa khai báo descriptor `sort` | Thêm `parameterWithName("sort")` và mô tả hoặc dùng ignored có chủ đích |
| Request thiếu `q` khiến document thất bại | Descriptor `q` bắt buộc | Gửi `q`, hoặc chỉ dùng optional nếu hợp đồng thực sự cho phép vắng mặt |
| Bảng tài liệu thiếu tham số tùy chọn | Không khai báo descriptor dù đánh dấu optional ở controller | Thêm descriptor `.optional()`; REST Docs không tự đọc annotation controller |
| Dùng `.ignored()` nhưng parameter vẫn không được xử lý như mong đợi | Descriptor ignored chưa được khai báo trong lần document đó hoặc tên sai | Khai báo đúng tên và kiểm tra request URI |
| Chế độ relaxed che mất tham số public mới | `relaxedQueryParameters(...)` cho phép tên chưa được mô tả | Dùng chế độ strict ở bài test hợp đồng chính |
| Có hai giá trị cùng tên nhưng tạo hai descriptor | Nhầm số lần lặp với số tên parameter | Dùng một descriptor cho mỗi tên và mô tả lặp trong description |
| Snippet tồn tại nhưng trang HTML không có bảng | Sai identifier hoặc sai đường dẫn include; task docs chạy trước test | Kiểm tra folder `products-search`, `{snippets}` và task dependency |

## 11. Bài tập thực hành

Thiết kế endpoint:

```http
GET /api/orders?customerId=CU-10&status=PAID&status=SHIPPED&page=0 HTTP/1.1
```

Hợp đồng:

- `customerId` bắt buộc và chỉ xuất hiện một giá trị.
- `status` tùy chọn, có thể lặp; mỗi giá trị chỉ nhận `PENDING`, `PAID`, `SHIPPED` hoặc `CANCELLED`.
- `page` tùy chọn, mặc định 0 và không âm.
- Mọi query parameter khác chưa được công bố đều phải bị kiểm tra bởi test tài liệu strict.

Thực hiện:

1. Tạo controller Spring MVC dùng `@RequestParam` cho ba tên trên.
2. Viết test MockMvc dùng `.queryParam("customerId", "CU-10")`, `.queryParam("status", "PAID", "SHIPPED")` và `.queryParam("page", "0")`.
3. Document bằng `queryParameters(...)`; `customerId` bắt buộc, `status` và `page` optional.
4. Tạo test request có `debug=true` nhưng chưa có descriptor; quan sát lỗi document, sau đó quyết định thêm descriptor hoặc `.ignored()` theo hợp đồng.
5. Tạo test thiếu `customerId` và xác nhận request không đáp ứng hợp đồng bắt buộc.
6. Sinh snippet, chèn vào Asciidoctor và chạy test cùng task kết xuất trong CI.

**Tiêu chí hoàn thành:** Test document chứng minh request có đúng các tên đã công bố; tham số bắt buộc không bị thiếu; tham số ngoài hợp đồng bị phát hiện; bảng query parameters được sinh từ test và xuất hiện trong trang tài liệu.

## 12. Ghi nhớ

`queryParameters(...)` xác nhận tên query parameter trong request có được mô tả đầy đủ hay không và descriptor bắt buộc có xuất hiện hay không. Dùng `.queryParam(...)` hoặc URL query thực để kiểm thử query string; dùng `.optional()` cho tên được phép vắng, `.ignored()` cho tham số biết trước nhưng ẩn khỏi bảng, và `relaxedQueryParameters(...)` chỉ khi cố ý document một phần request. Kết hợp kiểm tra tên với assertion giá trị và validation ứng dụng để tài liệu Spring REST Docs phản ánh đúng hợp đồng HTTP.

### Tài liệu tham khảo

- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — `RequestDocumentation` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring Framework — `@RequestParam` trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
