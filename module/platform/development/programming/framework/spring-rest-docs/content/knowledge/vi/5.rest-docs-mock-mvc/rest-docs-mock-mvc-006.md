# `document(operation)` để sinh snippet với MockMvc

## 1. Từ HTTP operation đến tài liệu có thể kiểm chứng

**Spring REST Docs** sinh tài liệu REST API từ những request và response được ghi nhận trong bài kiểm thử HTTP. Công cụ có các tích hợp dành cho **MockMvc**, WebTestClient và REST Assured; trong chương **MockMvc**, ta sử dụng kết quả của `mockMvc.perform(...)` để sinh **snippet** cho request, response, payload, tham số, header và các thành phần của hợp đồng API.

Một snippet là một phần tài liệu có thể được ghép vào Asciidoctor hoặc Markdown. Khác với ví dụ HTTP viết tay, snippet xuất phát từ dữ liệu kiểm thử thực tế và có thể được tạo lại khi chạy build/CI. Nếu descriptor không khớp request/response, test tài liệu thường thất bại, giúp phát hiện tài liệu đã lạc hậu.

Khi nói “**`document(operation)` để sinh snippet**”, cần phân biệt hai tầng:

- **Ở tầng bài kiểm thử MockMvc:** lập trình viên gọi `.andDo(document("books-get", ...))`. `document(...)` ở đây là phương thức của `MockMvcRestDocumentation`, nhận **identifier** và các `Snippet` tùy chọn rồi trả một `ResultHandler`.
- **Ở tầng xử lý nội bộ:** Spring REST Docs chuyển kết quả HTTP thành một **`Operation`**, chứa request, response và thông tin cần thiết. Các triển khai `Snippet` sử dụng `Operation` này để ghi nội dung snippet ra file. Trong SPI, `Snippet.document(Operation)` là cách một snippet tự tạo nội dung của nó.

Do đó, **không viết `.andDo(document(operation))` với biến `operation` kiểu `Operation` trong bài test MockMvc thông thường**. Hình thức sử dụng thực tế tại test là:

```java
mockMvc.perform(get("/api/books/{id}", "bk-101")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andDo(document("books-get",
                pathParameters(
                        parameterWithName("id").description("Mã sách")),
                responseFields(
                        fieldWithPath("id").description("Mã sách"),
                        fieldWithPath("title").description("Tên sách"),
                        fieldWithPath("price").description("Giá niêm yết"))));
```

Mục tiêu của bài học là hiểu **operation được tạo ra thế nào**, `document(...)` được gọi ở đâu, snippet nào được sinh và làm sao đưa chúng vào tài liệu và quy trình build.

## 2. Cơ chế sinh snippet: nhìn từ request đến file

```text
JUnit Jupiter + RestDocumentationExtension
                |
                v
    RestDocumentationContextProvider
                |
                v
 MockMvcBuilders.standaloneSetup(...)
     .apply(documentationConfiguration(...))
     .build()
                |
                v
       mockMvc.perform(...)
                |
                v
    HTTP request + HTTP response
                |
      andExpect(...) kiểm chứng
                |
                v
  andDo(document("books-get", Snippet...))
                |
                v
       Spring REST Docs Operation
                |
      +---------+-----------+-------------+
      |         |           |             |
      v         v           v             v
  HTTP text  Parameters  JSON fields   Headers
      |         |           |             |
      +---------+-----------+-------------+
                |
                v
    build/generated-snippets/books-get/
                |
                v
    Asciidoctor / Markdown -> CI / publish
```

| Thành phần | Trách nhiệm | Có tự sinh file không? |
| --- | --- | --- |
| `MockMvcRequestBuilders.get/post/...` | Dựng request muốn kiểm thử | Không. |
| `MockMvc.perform(...)` | Thực thi request trong hạ tầng Spring MVC mô phỏng | Không tự động tạo snippet theo từng identifier. |
| `andExpect(...)` | Kiểm tra status, header, payload; sai là test thất bại | Không. |
| `documentationConfiguration(restDocumentation)` | Kết nối Spring REST Docs vào cấu hình MockMvc | Chuẩn bị cơ chế ghi; riêng nó không quyết định operation nào cần ghi. |
| `document("identifier", snippets...)` | Yêu cầu ghi operation đã chạy thành snippet dưới identifier xác định | Có, khi được gọi trong một test đã cấu hình đúng. |
| `Snippet` | Mô tả/ghi một khía cạnh của operation, ví dụ `responseFields` hoặc `pathParameters` | Được Spring REST Docs thực thi trong lúc ghi operation. |

`document(...)` không thay thế assertion. Test tài liệu nên đặt `andExpect(...)` **trước** `andDo(document(...))` để không ghi một response sai hợp đồng như ví dụ thành công. Riêng bộ mô tả trường và tham số của Spring REST Docs cũng có thể phát hiện dữ liệu chưa được tài liệu hóa và làm test thất bại.

## 3. Chuẩn bị môi trường MockMvc + Spring REST Docs

Ví dụ dùng **Java 17+, Spring Boot 3.x, Spring MVC và JUnit Jupiter (JUnit 5)**. Với Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Khi dự án dùng Spring Boot dependency management, để BOM chọn phiên bản Spring REST Docs tương thích. Nếu không dùng BOM, cần khai báo phiên bản phù hợp với Spring Framework, Spring Test và Java đang sử dụng.

Để tạo MockMvc sinh snippet với JUnit Jupiter:

```java
@ExtendWith(RestDocumentationExtension.class)
class BookDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new BookController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

Ở ví dụ rút gọn này, các lớp được import từ `org.junit.jupiter.api`, `org.springframework.restdocs` và `org.springframework.test.web.servlet`; thêm static import `MockMvcRestDocumentation.documentationConfiguration`. `RestDocumentationExtension` cung cấp ngữ cảnh để Spring REST Docs đặt tên và ghi snippet theo lần kiểm thử. Trên `MockMvcBuilder`, `.apply(documentationConfiguration(...))` phải xuất hiện trước `.build()`.

Ví dụ dùng `standaloneSetup` để dễ tập trung vào `document(...)`. Trong ứng dụng thực, có thể thay bằng `webAppContextSetup(webApplicationContext)` hoặc dùng MockMvc được Spring Boot cấu hình và tích hợp Spring REST Docs. Dù chọn kiểu nào, cơ chế `perform → assert → document` vẫn giống nhau.

## 4. Ví dụ hoàn chỉnh: ghi operation GET và POST

Ta tạo API sách nhỏ để minh họa hai kiểu operation:

1. `GET /api/books/{id}` trả `200 OK`, JSON có `id`, `title`, `price` và header `X-Trace-Id`.
2. `POST /api/books` nhận JSON có `title` và `price`, trả `201 Created`, header `Location` và JSON tài nguyên đã tạo.

Lớp JUnit sau đặt controller mẫu trong test để có dữ liệu ổn định. Trong sản phẩm thực, controller nằm trong mã ứng dụng và test nên kiểm chứng những trường hợp phù hợp với hợp đồng API.

```java
import java.net.URI;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class BookDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new BookController())
                .setMessageConverters(new MappingJackson2HttpMessageConverter())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentGetBook() throws Exception {
        mockMvc.perform(get("/api/books/{id}", "bk-101")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string("X-Trace-Id", "trace-doc-01"))
                .andExpect(jsonPath("$.id").value("bk-101"))
                .andExpect(jsonPath("$.title").value("Spring REST Docs"))
                .andExpect(jsonPath("$.price").value(199000))
                .andDo(document("books-get",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Mã định danh của sách")),
                        requestHeaders(
                                headerWithName(HttpHeaders.ACCEPT)
                                        .description("Định dạng response mong muốn")),
                        responseHeaders(
                                headerWithName("X-Trace-Id")
                                        .description("Mã truy vết phản hồi")),
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã sách"),
                                fieldWithPath("title")
                                        .description("Tên sách"),
                                fieldWithPath("price")
                                        .description("Giá niêm yết"))));
    }

    @Test
    void documentCreateBook() throws Exception {
        mockMvc.perform(post("/api/books")
                        .accept(MediaType.APPLICATION_JSON)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"MockMvc Guide","price":165000}
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        HttpHeaders.LOCATION, "/api/books/bk-102"))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value("bk-102"))
                .andExpect(jsonPath("$.title").value("MockMvc Guide"))
                .andExpect(jsonPath("$.price").value(165000))
                .andDo(document("books-create",
                        requestFields(
                                fieldWithPath("title")
                                        .description("Tên sách muốn tạo"),
                                fieldWithPath("price")
                                        .description("Giá sách")),
                        responseHeaders(
                                headerWithName(HttpHeaders.LOCATION)
                                        .description("Đường dẫn của sách mới")),
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã sách mới"),
                                fieldWithPath("title")
                                        .description("Tên sách"),
                                fieldWithPath("price")
                                        .description("Giá niêm yết"))));
    }

    @RestController
    public static class BookController {

        @GetMapping(
                value = "/api/books/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, Object>> find(
                @PathVariable("id") String id) {
            Map<String, Object> book = Map.of(
                    "id", id,
                    "title", "Spring REST Docs",
                    "price", 199000);
            return ResponseEntity.ok()
                    .header("X-Trace-Id", "trace-doc-01")
                    .body(book);
        }

        @PostMapping(
                value = "/api/books",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, Object>> create(
                @RequestBody Map<String, Object> request) {
            Map<String, Object> created = Map.of(
                    "id", "bk-102",
                    "title", request.get("title"),
                    "price", request.get("price"));
            return ResponseEntity.created(
                    URI.create("/api/books/bk-102")).body(created);
        }
    }
}
```

### Phân tích hai lần gọi `document(...)`

**GET `books-get`**:

- `get("/api/books/{id}", "bk-101")` giữ URI template để Spring REST Docs biết `id` là path parameter.
- Các `andExpect(...)` kiểm tra status `200`, media type, header `X-Trace-Id` và nội dung JSON.
- `document("books-get", ...)` ghi HTTP operation dưới identifier `books-get` và sinh snippet `path-parameters`, `request-headers`, `response-headers` và `response-fields` bên cạnh các snippet mặc định.

**POST `books-create`**:

- `post("/api/books")` truyền `Content-Type: application/json` và body JSON chứa hai field.
- Các assertion bảo vệ `201 Created`, `Location` và JSON response trước khi ghi tài liệu.
- `requestFields(...)` mô tả body đầu vào; `responseHeaders(...)` mô tả header `Location`; `responseFields(...)` mô tả body đầu ra.

Các identifier **phải phản ánh operation khác nhau**. Nếu dùng lại cùng một identifier cho nhiều test ghi các response khác nhau, file snippet có thể bị ghi đè hoặc không ổn định khi chạy song song. Tốt nhất dùng một tên riêng, dễ đọc cho mỗi endpoint/tình huống như `books-get`, `books-create`, `books-get-not-found`.

## 5. Các hình thức sử dụng `document(...)`

### 5.1. Chỉ cần snippet mặc định

```java
mockMvc.perform(get("/api/health"))
        .andExpect(status().isOk())
        .andDo(document("health-get"));
```

Ví dụ ngắn này chỉ thích hợp khi `/api/health` được đăng ký trong môi trường test. Không truyền descriptor sẽ yêu cầu Spring REST Docs ghi các snippet mặc định đã cấu hình, chẳng hạn `http-request`, `http-response`, `curl-request`, `httpie-request`, `request-body` và `response-body`. Thành phần và số lượng file tùy phiên bản, cấu hình snippets và dữ liệu thực tế.

### 5.2. Thêm snippet mô tả theo hợp đồng API

```java
.andDo(document("books-get",
        pathParameters(
                parameterWithName("id").description("Mã sách")),
        responseFields(
                fieldWithPath("id").description("Mã"),
                fieldWithPath("title").description("Tên sách"),
                fieldWithPath("price").description("Giá"))));
```

Đoạn này là phần nối tiếp của `mockMvc.perform(...).andExpect(...)`; các class và static import tương ứng đã có trong ví dụ đầy đủ ở mục 4. Khi thêm `Snippet`, Spring REST Docs tạo thêm file cho từng loại mô tả. Không cần viết tay từng file `.adoc`.

### 5.3. Tiền xử lý request và response trước khi sinh snippet

`OperationRequestPreprocessor` và `OperationResponsePreprocessor` giúp chỉnh **cách operation được thể hiện trong tài liệu**, thường để làm đẹp JSON hoặc ẩn dữ liệu không nên công bố.

Ví dụ định dạng JSON dễ đọc:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;

// Phần nối tiếp sau mockMvc.perform(...).andExpect(...).
.andDo(document("books-create",
        preprocessRequest(prettyPrint()),
        preprocessResponse(prettyPrint()),
        requestFields(
                fieldWithPath("title").description("Tên sách"),
                fieldWithPath("price").description("Giá sách")),
        responseFields(
                fieldWithPath("id").description("Mã sách"),
                fieldWithPath("title").description("Tên sách"),
                fieldWithPath("price").description("Giá sách"))));
```

`prettyPrint()` chỉ chuẩn hóa nội dung xuất ra snippet, không phải cách sửa response mà controller thực sự trả về trong `andExpect(...)`. Với các dữ liệu nhạy cảm hoặc giá trị biến đổi, có thể cân nhắc các preprocessor hỗ trợ thay đổi header, URI hoặc nội dung, đồng thời bảo đảm snippet vẫn trung thực với hợp đồng API được công bố.

### 5.4. Đường dẫn URI public khác URI của MockMvc

MockMvc chạy trong JVM, không gửi request thật tới server. Để URI hiển thị trong snippet phù hợp với API công khai:

```java
mockMvc = MockMvcBuilders.standaloneSetup(new BookController())
        .apply(documentationConfiguration(restDocumentation)
                .uris()
                    .withScheme("https")
                    .withHost("api.example.com")
                    .withPort(443))
        .build();
```

Host/scheme/port ở đây chỉ phục vụ cách trình bày URI trong tài liệu; request vẫn được MockMvc xử lý cục bộ. Nếu đã có cấu hình builder ở phần 4, chỉnh cấu hình trên chính builder đó thay vì tạo thêm một MockMvc không liên quan.

## 6. Các nhóm snippet và dữ liệu dùng để sinh chúng

Mỗi `Snippet` cần đúng loại dữ liệu trong HTTP operation:

| Mục cần tài liệu hóa | API descriptor thường dùng | Snippet thu được |
| --- | --- | --- |
| HTTP request/response | Snippet mặc định | `http-request.adoc`, `http-response.adoc` |
| Ví dụ lệnh gọi | Snippet mặc định tương ứng | `curl-request.adoc`, có thể có `httpie-request.adoc` |
| JSON request | `requestFields(fieldWithPath(...))` | `request-fields.adoc` |
| JSON response | `responseFields(fieldWithPath(...))` | `response-fields.adoc` |
| Path parameter | `pathParameters(parameterWithName(...))` | `path-parameters.adoc` |
| Query parameter | `queryParameters(parameterWithName(...))` | `query-parameters.adoc` |
| Form parameter | `formParameters(parameterWithName(...))` | `form-parameters.adoc` |
| Header request/response | `requestHeaders(...)`, `responseHeaders(...)` | `request-headers.adoc`, `response-headers.adoc` |
| Multipart part | `requestParts(partWithName(...))` | `request-parts.adoc` |
| Toàn bộ body | Snippet mặc định hoặc snippet body được chọn | `request-body.adoc`, `response-body.adoc` |

Spring REST Docs cũng hỗ trợ các mô tả khác như cookie, phần payload của multipart part, subsection và constraints. Không nên khai báo descriptor chỉ để tạo thêm file: **snippet phải khớp operation được thực thi**.

Ví dụ, đối với `GET /api/books/{id}`:

```java
pathParameters(
        parameterWithName("id")
                .description("Mã sách cần tìm"))
```

Nếu test chỉ gọi `get("/api/books/bk-101")`, công cụ có thể không có URI template để gắn tên `id` với đường dẫn thực. Hãy dùng request builder với template `get("/api/books/{id}", "bk-101")` khi muốn sinh snippet path parameter.

Đối với JSON payload, `responseFields(...)` thường yêu cầu mô tả đầy đủ các field xuất hiện trong response. Nếu thiếu `price` mà payload vẫn có `price`, test tài liệu sẽ báo lỗi theo chế độ kiểm tra strict mặc định. Đừng khắc phục bằng cách đánh dấu mọi field là `optional()` hoặc dùng relaxed descriptor một cách tràn lan.

## 7. Strict documentation, field tùy chọn và mô tả một phần

Để tài liệu không bỏ sót dữ liệu API, Spring REST Docs kiểm tra sự tương ứng giữa operation và descriptor. Với JSON:

```json
{
  "id": "bk-101",
  "title": "Spring REST Docs",
  "price": 199000,
  "currency": "VND"
}
```

Nếu viết:

```java
responseFields(
        fieldWithPath("id").description("Mã"),
        fieldWithPath("title").description("Tên"),
        fieldWithPath("price").description("Giá"))
```

thì `currency` chưa được mô tả và strict snippet sẽ làm test thất bại. Giải pháp ưu tiên là thêm `fieldWithPath("currency").description("Đơn vị tiền tệ")` nếu field thuộc hợp đồng API.

Các lựa chọn cần hiểu đúng:

- `fieldWithPath("description").optional()`: field có thể **vắng mặt** hợp lệ; không có nghĩa là được bỏ qua các field khác trong response.
- `fieldWithPath("internalId").ignored()`: field đã được nhận diện và chủ ý không xuất hiện trong bảng mô tả; chỉ dùng khi API thật sự cho phép bỏ qua.
- `relaxedResponseFields(...)` hoặc `relaxedRequestFields(...)`: bỏ qua các field chưa được mô tả. Hữu ích khi tài liệu hóa một phần payload lớn nhưng giảm khả năng phát hiện API thêm field ngoài dự kiến.

Trong một hệ thống dùng tài liệu như một phần hợp đồng, ưu tiên strict descriptor cho endpoint công khai. Nếu có field động theo thời gian hoặc dữ liệu thực tế, hãy chọn tên field và mức kiểm tra dựa trên quy định của API, không theo mục đích làm test qua.

**Quan trọng:** kiểm tra strict của snippet chủ yếu liên quan đến **cấu trúc field và sự hiện diện theo descriptor**. Nó không thay cho `andExpect(jsonPath("$.price").value(199000))` để bảo vệ giá trị nghiệp vụ, hay `andExpect(status().isOk())` để xác nhận đúng status.

## 8. Vị trí file và cách đưa snippet vào Asciidoctor/Markdown

Chạy:

```bash
./gradlew test
```

Với Gradle, nơi ghi snippet mặc định thường là `build/generated-snippets/`; với Maven là `target/generated-snippets/`. Vị trí thực tế phụ thuộc cấu hình build và ngữ cảnh REST Docs. Với hai test của ví dụ, một cây file tiêu biểu là:

```text
build/generated-snippets/
├── books-get/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── curl-request.adoc
│   ├── path-parameters.adoc
│   ├── request-headers.adoc
│   ├── response-headers.adoc
│   └── response-fields.adoc
└── books-create/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    ├── request-fields.adoc
    ├── response-headers.adoc
    └── response-fields.adoc
```

Đây là cấu trúc **minh họa rút gọn**; các snippet mặc định khác như `httpie-request.adoc`, `request-body.adoc` và `response-body.adoc` cũng có thể xuất hiện. Không kết luận một test sai chỉ vì số lượng file khác cây ví dụ; kiểm tra các snippet thật sự được cấu hình và yêu cầu.

Trang Asciidoctor có thể tham chiếu các file:

```adoc
= Books REST API

== Lấy thông tin sách

include::{snippets}/books-get/http-request.adoc[]
include::{snippets}/books-get/path-parameters.adoc[]
include::{snippets}/books-get/request-headers.adoc[]
include::{snippets}/books-get/http-response.adoc[]
include::{snippets}/books-get/response-fields.adoc[]

== Tạo sách

include::{snippets}/books-create/http-request.adoc[]
include::{snippets}/books-create/request-fields.adoc[]
include::{snippets}/books-create/http-response.adoc[]
include::{snippets}/books-create/response-headers.adoc[]
include::{snippets}/books-create/response-fields.adoc[]
```

`{snippets}` là thuộc tính Asciidoctor cần được cấu hình trỏ đến thư mục output. Nếu sản phẩm tài liệu dùng Markdown, cần một bước nhúng hoặc chuyển nội dung snippet thích hợp; snippet mặc định của Spring REST Docs thường ở dạng AsciiDoc.

Một quy trình build/CI nên bảo đảm:

1. **Test HTTP** chạy trên môi trường và dữ liệu xác định trước; assertions phải đạt.
2. **Spring REST Docs** ghi snippet từ các operation trong test.
3. **Tác vụ biên soạn** Asciidoctor/Markdown phụ thuộc vào bước tạo snippet, tránh dùng file cũ.
4. **Xuất bản** chỉ diễn ra sau khi test và tác vụ biên soạn thành công.

Không nên xem một thư mục `generated-snippets` còn tồn tại từ lần build trước là bằng chứng rằng test hiện tại đã pass; hãy đối chiếu kết quả của lần chạy hiện tại.

## 9. Lỗi thường gặp quanh `document(...)`

| Dấu hiệu | Nguyên nhân phổ biến | Cách kiểm tra |
| --- | --- | --- |
| Không có thư mục snippet cho một test | Không gọi `andDo(document(...))` hoặc assertion trước đó thất bại | Xác minh test được thực thi, kết quả matcher và lệnh ghi tài liệu. |
| Lỗi thiếu REST Docs context | Chưa đăng ký `RestDocumentationExtension` hoặc thiếu cấu hình MockMvc | Cấp `RestDocumentationContextProvider` và `.apply(documentationConfiguration(...))` trước `.build()`. |
| File snippet ở sai thư mục | Identifier khác kỳ vọng hoặc output directory khác | Kiểm tra tên `document("...")`, cấu hình REST Docs và cấu hình build. |
| File của hai test trùng nhau | Tái sử dụng identifier cho các operation khác nhau | Đặt identifier riêng theo endpoint/tình huống, đặc biệt khi chạy song song. |
| `pathParameters(...)` báo lỗi | URI không giữ template hoặc descriptor sai tên biến | Dùng `get("/api/books/{id}", id)` và `parameterWithName("id")`. |
| `responseFields(...)` thất bại | Payload có field chưa mô tả, field khai báo không tồn tại hoặc JSON không đúng | Đối chiếu body thực tế, sửa descriptor và kiểm tra content type. |
| `requestFields(...)` thất bại | Body JSON khác với field đã tài liệu hóa | Kiểm tra `Content-Type`, `content(...)` và các field theo đúng dữ liệu đã gửi. |
| `responseHeaders(...)` không tìm thấy header | Header mong muốn không xuất hiện trong operation | Xác nhận với `header().exists(...)` và kiểm tra controller/filter. |
| Snippet có URL `localhost` | URI hiển thị chưa được tùy chỉnh | Dùng cấu hình `.uris().withScheme(...).withHost(...).withPort(...)`. |
| Tài liệu Asciidoctor báo thiếu include | Tên file/snippet sai, test chưa tạo snippet hoặc `{snippets}` chưa trỏ đúng thư mục | Kiểm tra generated snippets thực tế và dependency task biên soạn. |
| Test thành công nhưng ví dụ sai status nghiệp vụ | Chỉ dùng `document(...)` mà thiếu assertions phù hợp | Thêm `andExpect(status/header/body)` trước khi document. |

### Khi cần quan sát operation thực tế

Trong lúc debug, có thể dùng:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

mockMvc.perform(get("/api/books/{id}", "bk-101")
                .accept(MediaType.APPLICATION_JSON))
        .andDo(print())
        .andExpect(status().isOk());
```

`print()` hiển thị request, handler, status, header và body cho test, nhưng không tự ghi tài liệu REST Docs. Không in dữ liệu nhạy cảm thật vào log. Khi kiểm tra xong, kết hợp `andExpect(...)` với `document(...)` để sinh snippet được bảo vệ bởi assertions.

## 10. Bài thực hành

1. **Snippet mặc định:** tạo test cho `GET /api/health`, kiểm tra `200 OK` rồi gọi `document("health-get")`. Xác nhận thư mục và file thực tế được sinh.
2. **Path parameter:** thêm `GET /api/books/{id}`, mô tả `id` với `pathParameters(...)`. Thử đổi tên descriptor thành `bookId` và quan sát test thất bại; sửa lại đúng tên.
3. **JSON fields:** thêm field `currency` trong response nhưng chưa cập nhật `responseFields(...)`, quan sát lỗi strict. Thêm descriptor và chạy lại test.
4. **POST và header:** mô tả `requestFields(...)`, `responseHeaders("Location")` và `responseFields(...)`. Xóa header `Location` ở controller để thấy assertion và tài liệu cùng phát hiện hợp đồng thay đổi.
5. **Preprocessor:** áp dụng `preprocessRequest(prettyPrint())` và `preprocessResponse(prettyPrint())` cho một operation JSON; so sánh snippet trước và sau khi định dạng.
6. **Build/CI:** tạo trang Asciidoctor tham chiếu các snippet của `books-get` và `books-create`; cấu hình tác vụ biên soạn phụ thuộc test để dữ liệu luôn mới.

**Tiêu chí hoàn thành:** từng operation có identifier riêng, assertions bảo vệ status/header/body, descriptor khớp dữ liệu thật, snippet được ghi vào đúng đường dẫn, tài liệu cuối được biên soạn từ kết quả test hiện tại.

## 11. Checklist trước khi hoàn tất

- [ ] MockMvc đã tích hợp Spring REST Docs bằng `documentationConfiguration(...)` hoặc cơ chế Spring Boot tương ứng.
- [ ] Request đã dùng đúng method, URI template, query/header/body của endpoint.
- [ ] Có `andExpect(...)` cho status, header và payload quan trọng **trước** `andDo(document(...))`.
- [ ] `document("identifier", snippets...)` dùng tên riêng, ổn định cho từng tình huống HTTP.
- [ ] `pathParameters`, `requestFields`, `responseFields` và các descriptor khác phản ánh operation thực tế.
- [ ] Dữ liệu bí mật hoặc biến đổi đã được xử lý phù hợp trong test và snippet được công bố.
- [ ] Đã kiểm tra đường dẫn generated snippets và mọi `include` được biên soạn thành công.
- [ ] Build/CI tạo snippet mới sau khi test đạt rồi mới biên soạn/xuất bản tài liệu.

**Ghi nhớ:** Trong MockMvc, `document("identifier", snippets...)` là cách gắn **một HTTP operation đã kiểm thử** với các snippet. `Operation` là dữ liệu request/response được Spring REST Docs chuyển cho những `Snippet` ở tầng bên trong. Nhờ kết hợp kiểm chứng HTTP, descriptor và quy trình build, tài liệu REST API trở thành kết quả có thể kiểm tra cùng mã nguồn.
