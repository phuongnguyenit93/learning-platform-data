# Document query parameters bằng `queryParameters` trong Spring REST Docs

## 1. Mục tiêu và ngữ cảnh

Một REST API tìm kiếm thường nhận các tham số sau dấu `?` của URL:

```http
GET /api/books?keyword=spring&page=1&tag=java&tag=api HTTP/1.1
Host: example.com
```

`keyword`, `page` và `tag` là **query parameters**. Chúng có tên và giá trị nằm trong *query string*, khác với:

| Thành phần | Ví dụ | Bộ mô tả tương ứng trong Spring REST Docs |
| --- | --- | --- |
| Query parameter | `?page=1` | `queryParameters(...)` |
| Path parameter | `/books/42` với `{id}` | `pathParameters(...)` |
| Form parameter | Trường `email` trong body `application/x-www-form-urlencoded` | `formParameters(...)` |
| Request header | `Accept-Language: vi` | `requestHeaders(...)` |
| JSON body | `{"page":1}` | `requestFields(...)` |

**Spring REST Docs** tạo tài liệu từ các bài kiểm thử HTTP sử dụng MockMvc, WebTestClient hoặc REST Assured. Khi gắn `queryParameters(...)` vào bước tạo tài liệu, bài kiểm thử vừa sinh mô tả query string, vừa phát hiện tên tham số được gửi nhưng chưa được ghi tài liệu hoặc tham số bắt buộc được mô tả nhưng không có trong request. Nhờ vậy, tài liệu và hành vi HTTP thực tế được kiểm tra cùng nhau.

> **Phạm vi phiên bản:** `queryParameters(...)` có từ **Spring REST Docs 3.0**. Các bản 3.x và 4.x sử dụng API này. Nếu đang nâng cấp từ 2.x, cần thay cách mô tả `requestParameters(...)` cũ bằng `queryParameters(...)` và `formParameters(...)` theo đúng nguồn dữ liệu.

Sau bài này, bạn có thể:

1. Mô tả tên, ý nghĩa, yêu cầu có mặt và trường hợp lặp của query parameters.
2. Sinh file snippet `query-parameters.adoc` bằng kiểm thử HTTP.
3. Phân biệt kiểm tra nghiêm ngặt, `optional()`, `ignored()` và `relaxedQueryParameters(...)`.
4. Ghép snippet vào tài liệu Asciidoctor và cho kiểm thử chạy trong quy trình build/CI.

## 2. Cú pháp cốt lõi

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("keyword").description("Từ khóa cần tìm; bắt buộc"),
    parameterWithName("page").description("Trang, bắt đầu từ 0; mặc định 0").optional(),
    parameterWithName("tag").description("Có thể lặp để lọc theo nhiều nhãn").optional()
)
```

- `queryParameters(...)` là factory tĩnh của `org.springframework.restdocs.request.RequestDocumentation`, nhận các `ParameterDescriptor`.
- `parameterWithName("...")` mô tả **đúng tên** parameter trong query string; `description(...)` giải thích ý nghĩa cho người dùng API.
- `optional()` báo cho REST Docs rằng parameter có thể không xuất hiện trong **request của bài kiểm thử**. Nó không tự thay đổi ràng buộc của controller.
- Một parameter có thể xuất hiện nhiều lần, ví dụ `tag=java&tag=api`. Thông thường chỉ cần **một** descriptor cho tên `tag`; diễn giải việc lặp và quy tắc xử lý trong phần mô tả.

Trong Spring MVC, `@RequestParam(required = false)` hoặc `@RequestParam(defaultValue = "...")` quyết định việc binding tại server. Trong Spring REST Docs, `.optional()` quyết định việc kiểm tra sự hiện diện khi sinh tài liệu. Hai cấu hình này phải phản ánh cùng hợp đồng API nhưng **không tự đồng bộ**.

## 3. Ví dụ hoàn chỉnh với MockMvc và JUnit 5

Giả sử endpoint trả về danh sách sách theo từ khóa và chấp nhận phân trang, lọc nhãn. Để tập trung vào việc tạo snippet, controller minh họa trả về chuỗi đơn giản:

```java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class BookController {

    @GetMapping("/api/books")
    public String findBooks(
            @RequestParam("keyword") String keyword,
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "tag", required = false) List<String> tags) {
        return "keyword=" + keyword + ", page=" + page + ", tags=" + tags;
    }
}
```

Kiểm thử bên dưới cấu hình Spring REST Docs trên MockMvc, gửi query parameters thật và yêu cầu xuất snippet:

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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class BookQueryParametersDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders.standaloneSetup(new BookController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsSearchQueryParameters() throws Exception {
        mockMvc.perform(get("/api/books")
                        .queryParam("keyword", "spring docs")
                        .queryParam("page", "1")
                        .queryParam("tag", "java", "api"))
                .andExpect(status().isOk())
                .andDo(document("books-search",
                        queryParameters(
                                parameterWithName("keyword")
                                        .description("Từ khóa tìm sách, bắt buộc"),
                                parameterWithName("page")
                                        .description("Chỉ số trang từ 0; mặc định 0")
                                        .optional(),
                                parameterWithName("tag")
                                        .description("Nhãn lọc; có thể lặp nhiều lần")
                                        .optional()
                        )));
    }
}
```

**Đọc từng bước:**

1. `RestDocumentationExtension` quản lý ngữ cảnh tạo tài liệu cho JUnit 5; `documentationConfiguration(...)` gắn nó vào MockMvc. Ví dụ dùng `standaloneSetup`; trong Spring Boot có thể dùng MockMvc đã cấu hình qua `@AutoConfigureRestDocs`.
2. `get("/api/books").queryParam(...)` tạo query string của HTTP request. Giá trị `spring docs` được URL-encode bởi request builder; không cần tự nối chuỗi đã encode.
3. `.andExpect(status().isOk())` xác minh endpoint trả về 200; các assertion khác về payload hay quy tắc lọc có thể bổ sung độc lập.
4. `document("books-search", queryParameters(...))` tạo tập snippet có định danh `books-search`, trong đó có mô tả các query parameters.

Với Gradle, output mặc định thường nằm ở:

```text
build/
  generated-snippets/
    books-search/
      query-parameters.adoc
      curl-request.adoc
      http-request.adoc
      http-response.adoc
      ...
```

Trong Maven, vị trí thông thường là `target/generated-snippets/`. Các file khác được tạo theo cấu hình snippet mặc định; tên file tài liệu dành cho query parameters là `query-parameters.adoc` khi dùng template Asciidoctor. Nội dung snippet là bảng mô tả tên parameter và phần `description` đã khai báo.

**Lưu ý về MockMvc:** Với `queryParameters(...)`, hãy đưa dữ liệu vào URL (`get("/api/books?keyword=spring")`) hoặc dùng `queryParam(...)` / `queryParams(...)`. Tránh dùng `.param(...)` / `.params(...)` cho ví dụ này vì chúng chỉ thêm Servlet request parameters, không xác định rõ dữ liệu đến từ query string hay form body. Controller dùng `@RequestParam` có thể vẫn nhận được giá trị qua `.param(...)` trong khi REST Docs không thấy query parameter cần mô tả.

## 4. Kiểm tra nghiêm ngặt và các biến thể descriptor

Mặc định, `queryParameters(...)` kiểm tra hợp đồng về **tên và sự hiện diện** của query parameters trong request đang được kiểm thử:

| Tình huống | Kết quả với `queryParameters(...)` | Cách xử lý |
| --- | --- | --- |
| Request gửi `sort=title` nhưng chưa có descriptor `sort` | Kiểm thử thất bại vì parameter chưa được mô tả | Thêm `parameterWithName("sort")` hoặc loại khỏi request nếu không thuộc hợp đồng |
| Descriptor mô tả `page` nhưng request không có `page` | Kiểm thử thất bại nếu không khai báo optional | Dùng `.optional()` nếu endpoint cho phép bỏ qua `page` |
| Request chứa `trace` nội bộ, không muốn đưa vào bảng | Mặc định vẫn bị coi là chưa được mô tả | Dùng `parameterWithName("trace").ignored()` khi biết request có tham số đó |
| Chỉ muốn mô tả một tập con các tham số có trong request | Mặc định thất bại vì các tên còn lại chưa được mô tả | Cân nhắc `relaxedQueryParameters(...)` cho tình huống có chủ đích |

### 4.1. Parameter tùy chọn

```java
queryParameters(
    parameterWithName("keyword").description("Từ khóa bắt buộc"),
    parameterWithName("page").description("Trang, mặc định 0").optional()
)
```

Với mô tả này, request `/api/books?keyword=spring` vẫn tạo snippet thành công dù thiếu `page`. Ngược lại, nếu request thiếu `keyword`, bài kiểm thử tài liệu sẽ thất bại. Nên có kiểm thử riêng cho các giá trị mặc định, kiểu dữ liệu và trường hợp đầu vào không hợp lệ nếu đó là phần quan trọng của API.

### 4.2. Parameter được bỏ qua có chủ đích

```java
queryParameters(
    parameterWithName("keyword").description("Từ khóa tìm kiếm"),
    parameterWithName("trace").ignored()
)
```

Ví dụ request có `?keyword=spring&trace=abc` thì `trace` không xuất hiện trong bảng được sinh ra và không bị xem là parameter chưa được mô tả. Cách này thích hợp khi một tham số kỹ thuật được biết trước nhưng không nên xuất hiện trong tài liệu công khai. Nếu tham số bị bỏ qua cũng có thể vắng mặt, có thể cân nhắc kết hợp `.optional().ignored()` theo hợp đồng kiểm thử.

### 4.3. Chế độ relaxed

```java
import static org.springframework.restdocs.request.RequestDocumentation.relaxedQueryParameters;

relaxedQueryParameters(
    parameterWithName("keyword").description("Từ khóa tìm kiếm")
)
```

`relaxedQueryParameters(...)` **không báo lỗi với các query parameters xuất hiện nhưng chưa có descriptor**. Nó vẫn kiểm tra parameter đã được mô tả mà không xuất hiện, trừ khi được đánh dấu `optional()`. Dùng cách này khi cần tài liệu hóa một lát cắt của request; trong tài liệu API chính thức, nên ưu tiên chế độ nghiêm ngặt để phát hiện thay đổi hợp đồng.

## 5. WebTestClient và REST Assured có gì khác?

`queryParameters(...)` và `parameterWithName(...)` thuộc lớp API tạo descriptor dùng chung. Phần thay đổi giữa các công cụ kiểm thử chủ yếu là **cách gửi request và vị trí gắn `document(...)`**.

Ví dụ khi `WebTestClient` đã được gắn cấu hình Spring REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
        .uri("/api/books?keyword=spring&page=1")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("books-search",
                queryParameters(
                        parameterWithName("keyword").description("Từ khóa tìm sách"),
                        parameterWithName("page").description("Trang bắt đầu từ 0").optional()
                )));
```

Với REST Assured, có thể gắn `document(..., queryParameters(...))` thông qua filter của tích hợp `spring-restdocs-restassured`, và truyền giá trị bằng `queryParam(...)` của REST Assured. Trong cả ba cách, REST Docs phải được cấu hình trước khi yêu cầu sinh snippet; chỉ gọi `queryParameters(...)` mà không gắn vào thao tác tài liệu hóa sẽ không tự tạo file.

## 6. Đưa snippet vào tài liệu và CI

Với Asciidoctor, tạo một trang tài liệu thủ công (ví dụ `src/docs/asciidoc/books.adoc`) và chèn snippet:

```asciidoc
= Books API

== Tìm kiếm sách

GET /api/books

=== Query parameters

include::{snippets}/books-search/query-parameters.adoc[]
```

Biến `{snippets}` được cấu hình trỏ đến thư mục snippet của build; khi tích hợp `spring-restdocs-asciidoctor` đúng cách, build có thể cung cấp biến này. Với Gradle, luồng cơ bản gồm:

1. Khai báo `testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'` (hoặc dependency tương ứng với WebTestClient/REST Assured) và phụ thuộc kiểm thử JUnit/Spring Test. Chọn phiên bản Spring REST Docs tương thích với Spring Framework và Spring Boot của dự án.
2. Cấu hình thư mục snippet, ví dụ `build/generated-snippets`, làm **output của task `test`**.
3. Cấu hình plugin Asciidoctor và `spring-restdocs-asciidoctor` để task tài liệu đọc từ thư mục snippet; cho task này phụ thuộc task `test`.
4. Chạy `./gradlew test asciidoctor` (hoặc lifecycle tương đương của Maven) trong CI để kiểm thử hợp đồng HTTP trước khi xuất HTML. Nếu test tài liệu thất bại, CI phải thất bại theo.

Mặc định Spring REST Docs tạo các snippet Asciidoctor. Nếu dự án chọn **Markdown** làm template snippet, cấu hình `TemplateFormats.markdown()` trên `RestDocumentationConfigurer`; file sinh sẽ dùng định dạng Markdown. Markdown không có cơ chế `include` chuẩn như Asciidoctor, nên cần công cụ ghép tài liệu tương ứng khi xuất bản.

## 7. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân có thể xảy ra | Cách kiểm tra |
| --- | --- | --- |
| Test báo thiếu `keyword` dù controller vẫn đọc được | Dùng `.param("keyword", ...)` thay cho query string thực | Dùng `.queryParam("keyword", ...)` hoặc kiểm tra URL gửi đi |
| Test thất bại sau khi endpoint bổ sung `sort` | `queryParameters(...)` mặc định yêu cầu mô tả mọi query parameter đã gửi | Thêm descriptor `sort` và cập nhật mô tả hợp đồng |
| Test thất bại khi bỏ `page` | Descriptor `page` chưa gọi `optional()` | Đối chiếu với `@RequestParam`/giá trị mặc định rồi sửa descriptor |
| Có request/response snippets nhưng không có `query-parameters.adoc` | Chưa truyền `queryParameters(...)` vào lần gọi `document(...)` của test đó | Kiểm tra identifier và danh sách snippet trong lời gọi `document` |
| Tài liệu HTML thiếu bảng tham số | File Asciidoctor trỏ sai định danh `books-search`, sai `{snippets}` hoặc task docs chạy trước test | Kiểm tra đường dẫn output và phụ thuộc giữa các task |
| Bảng có tên tham số nhưng không phản ánh giới hạn giá trị | REST Docs chủ yếu kiểm tra **tên/sự có mặt**, không tự xác minh giá trị nghiệp vụ | Mô tả đơn vị, giá trị mặc định, cách lặp; viết assertion/test riêng cho ràng buộc dữ liệu |

## 8. Bài tập thực hành

1. Tạo endpoint `GET /api/books?keyword=java&page=0&size=20&tag=backend&tag=testing`. Trong bảng tài liệu, mô tả `keyword` bắt buộc, `page` và `size` tùy chọn kèm giá trị mặc định, `tag` cho phép nhiều giá trị.
2. Chạy test, sau đó gửi thêm `sort=title` nhưng chưa khai báo descriptor. Quan sát test thất bại; bổ sung mô tả `sort` rồi kiểm tra lại.
3. Bỏ `page` khỏi request. So sánh kết quả khi descriptor có và không có `.optional()`.
4. Mở `query-parameters.adoc`, chèn vào `books.adoc` và kiểm tra tài liệu HTML được sinh từ build.

**Tiêu chí hoàn thành:** Kiểm thử HTTP thành công, tồn tại snippet mô tả đủ tên tham số trong request, các trường tùy chọn có mô tả rõ, và trang tài liệu có bảng query parameters được lấy từ snippet của test.

## Tài liệu tham khảo

- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — `RequestDocumentation` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring REST Docs — Getting Started và đưa snippets vào Asciidoctor](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs 3.0 — thay đổi khi nâng cấp](https://github.com/spring-projects/spring-restdocs/wiki/Spring-REST-Docs-3.0-Release-Notes)
