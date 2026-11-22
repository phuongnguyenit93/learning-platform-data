# Định dạng request response khi có body

## 1. Mục tiêu bài học

HTTP request và response có thể mang body ở nhiều định dạng: JSON, XML, form URL-encoded, multipart, văn bản hoặc dữ liệu nhị phân. Với **Spring REST Docs**, bài kiểm thử phải gửi và nhận body theo hợp đồng thực tế; descriptor mô tả payload; tài liệu sau đó được biên soạn bằng Asciidoctor/Markdown và tích hợp vào build, CI.

Bài học thuộc module **SPRING_REST_DOCS**, hướng dẫn tạo tài liệu REST API có thể kiểm chứng từ kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header.

Sau bài này, bạn có thể phân biệt body và media type, kiểm thử nhiều định dạng payload, dùng `requestFields(...)`/`responseFields(...)`, chọn descriptor form/multipart, xử lý body rỗng và tích hợp snippet vào CI.

> Spring REST Docs ghi nhận body của HTTP operation được kiểm thử. Nó không tự tạo endpoint, fixture hoặc message converter. Descriptor giúp xác minh tài liệu khớp payload; chúng không thay thế mọi assertion nghiệp vụ.

## 2. Body và media type

Header `Content-Type` mô tả media type của representation trong body. Nó không thay đổi bytes của body và không biến payload sai định dạng thành payload hợp lệ.

Request JSON:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{"title":"Spring in Action","price":199000}
~~~

Response JSON:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/books/102

{"id":102,"title":"Spring in Action","price":199000}
~~~

Request body do client gửi; response body do server trả. Mỗi chiều có media type riêng theo hợp đồng.

| Media type | Hình thức | Tình huống |
| --- | --- | --- |
| `application/json` | JSON object/array/scalar | Dữ liệu nghiệp vụ REST API. |
| `application/problem+json` | Problem Details JSON | Body lỗi theo RFC 9457. |
| `application/xml` | XML document | Tích hợp hệ thống XML. |
| `application/x-www-form-urlencoded` | Các cặp tên/giá trị đã encode | Form đơn giản. |
| `multipart/form-data` | Nhiều part có headers/body riêng | Upload file và metadata. |
| `text/plain` | Văn bản | API trao đổi text. |
| `application/octet-stream` | Byte sequence | Binary tổng quát. |
| `image/png`, `application/pdf` | Binary theo loại cụ thể | Ảnh, PDF và file tải xuống. |

### 2.1. Body, Content-Type và Content-Encoding

- **Body:** nội dung thực của message.
- **Content-Type:** định dạng representation, ví dụ JSON hoặc XML.
- **Content-Encoding:** cách mã hóa/nén representation, ví dụ `gzip`.

`Content-Encoding: gzip` không làm media type JSON biến thành loại khác. HTTP client có thể tự giải nén trước khi test đọc body; cần xác định test kiểm tra representation đã giải nén hay bytes truyền trên wire.

### 2.2. Spring đọc và ghi body

Trong Spring MVC, `HttpMessageConverter` chuyển đổi HTTP body giữa bytes và kiểu Java. `@RequestBody` đọc body thành DTO/record; response object được converter tuần tự hóa thành body. Mapping có thể giới hạn định dạng qua `consumes` và `produces`.

~~~java
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<BookResponse> create(
        @Valid @RequestBody CreateBookRequest request) {
    BookResponse created = bookService.create(request);
    return ResponseEntity
        .created(URI.create("/api/books/" + created.id()))
        .body(created);
}
~~~

Media type không được hỗ trợ có thể dẫn đến `415 Unsupported Media Type`; representation không đáp ứng `Accept` có thể dẫn đến `406 Not Acceptable`. Body sai cú pháp/không bind được thường dẫn đến `400 Bad Request`, tùy error handling.

## 3. JSON request body

### 3.1. JSON object và field descriptors

Payload tạo sách:

~~~json
{
  "title": "Spring in Action",
  "price": 199000,
  "available": true
}
~~~

Dependencies minh họa cho Spring Boot 3.x, JUnit 5, Java 17+:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Test MockMvc giả định endpoint và fixture đã tồn tại, trả `201 Created`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class BookBodyDocumentationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentCreateBook() throws Exception {
        mockMvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "title": "Spring in Action",
                      "price": 199000,
                      "available": true
                    }
                    """))
            .andExpect(status().isCreated())
            .andDo(document("books-create",
                requestFields(
                    fieldWithPath("title").description("Tên sách"),
                    fieldWithPath("price").description("Giá sách theo VND"),
                    fieldWithPath("available").description("Sách đang được bán")
                )
            ));
    }
}
~~~

`requestFields(...)` có hai vai trò: sinh bảng mô tả payload và kiểm tra descriptor khớp body. Ở chế độ strict, field xuất hiện nhưng chưa được mô tả hoặc field bắt buộc đã mô tả nhưng vắng mặt sẽ khiến snippet generation thất bại, trừ khi dùng optional/ignored phù hợp. Descriptor không tự kiểm tra `price > 0` hoặc title không rỗng; cần assertion/validation test riêng.

### 3.2. JSON lồng nhau và mảng

~~~json
{
  "customer": {"id": 42, "name": "Lan"},
  "items": [
    {"sku": "BOOK-42", "quantity": 2},
    {"sku": "BOOK-77", "quantity": 1}
  ],
  "note": "Giao giờ hành chính"
}
~~~

Descriptor:

~~~java
requestFields(
    fieldWithPath("customer").description("Thông tin khách hàng"),
    fieldWithPath("customer.id").description("Mã khách hàng"),
    fieldWithPath("customer.name").description("Tên khách hàng"),
    fieldWithPath("items").description("Danh sách dòng hàng"),
    fieldWithPath("items[].sku").description("Mã sản phẩm"),
    fieldWithPath("items[].quantity").description("Số lượng"),
    fieldWithPath("note").description("Ghi chú")
)
~~~

`items[].sku` mô tả field trong các phần tử array, khác JSONPath assertion `$.items[0].sku`. Có thể dùng `subsectionWithPath("customer")` để mô tả tổng quan subtree; khi đó cân nhắc có cần liệt kê chi tiết field con hay không.

Field có thể vắng mặt:

~~~java
requestFields(
    fieldWithPath("title").description("Tên sách"),
    fieldWithPath("description")
        .description("Mô tả, có thể không gửi")
        .optional()
)
~~~

`optional()` cho phép field vắng mặt, không đồng nghĩa với giá trị JSON `null`. `ignored()` bỏ field khỏi bảng một cách có chủ đích. `relaxedRequestFields(...)` cho phép field bổ sung chưa mô tả; chỉ sử dụng khi tài liệu thực sự chỉ mô tả một phần payload, không phải để che schema drift.

## 4. JSON response body

Request và response dùng descriptor tương ứng:

| Chiều | API | Snippet |
| --- | --- | --- |
| Request JSON | `requestFields(...)` | `request-fields.adoc` |
| Response JSON | `responseFields(...)` | `response-fields.adoc` |

Payload minh họa:

~~~json
{
  "id": 102,
  "title": "Spring in Action",
  "price": 199000,
  "available": true
}
~~~

Test có thể xác nhận status, media type, giá trị và schema:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

@Test
void documentGetBook() throws Exception {
    mockMvc.perform(get("/api/books/102")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(102))
        .andExpect(jsonPath("$.title").value("Spring in Action"))
        .andDo(document("books-get",
            responseHeaders(
                headerWithName("Content-Type")
                    .description("Media type của response body")
            ),
            responseFields(
                fieldWithPath("id").description("Mã sách"),
                fieldWithPath("title").description("Tên sách"),
                fieldWithPath("price").description("Giá sách"),
                fieldWithPath("available").description("Trạng thái kinh doanh")
            )
        ));
}
~~~

Đây là method bổ sung vào lớp test ở phần trước, cần import `get` và `status`. `jsonPath(...)` kiểm tra giá trị; `responseFields(...)` kiểm tra và mô tả schema. Với response lồng nhau, có thể dùng path `items[].sku`. Không dùng response fields để khẳng định quy tắc domain chưa được assertion.

## 5. XML request/response

Nếu endpoint thực sự hỗ trợ XML, request ví dụ:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/xml
Accept: application/xml

<book>
  <title>Spring in Action</title>
  <price>199000</price>
</book>
~~~

MockMvc:

~~~java
mockMvc.perform(post("/api/books")
        .contentType(MediaType.APPLICATION_XML)
        .accept(MediaType.APPLICATION_XML)
        .content("""
            <book>
              <title>Spring in Action</title>
              <price>199000</price>
            </book>
            """))
    .andExpect(status().isCreated())
    .andDo(document("books-create-xml"));
~~~

Ví dụ giả định ứng dụng có XML message converter và mapping `consumes`/`produces` tương ứng. Chỉ đổi header mà vẫn giữ body JSON không biến payload thành XML.

Spring REST Docs hỗ trợ mô tả XML payload bằng field path/XPath theo cấu trúc và quy tắc của phiên bản thư viện. Ví dụ minh họa:

~~~java
requestFields(
    fieldWithPath("book.title").description("Tên sách"),
    fieldWithPath("book.price").description("Giá sách")
)
~~~

Đường dẫn thực tế phụ thuộc root element và namespace. Với XML có namespace, cấu hình xử lý namespace phải phù hợp. Luôn xác minh snippet sinh ra; không áp dụng JSON path như `items[].sku` vào XML.

## 6. Form URL-encoded và multipart

### 6.1. Form URL-encoded

~~~http
POST /api/login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=lan&remember=true
~~~

Đây là form body, không phải JSON hay query string. Dùng `formParameters(...)`:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

.andDo(document("login-form",
    formParameters(
        parameterWithName("username").description("Tên đăng nhập"),
        parameterWithName("remember").description("Ghi nhớ phiên đăng nhập")
    )
));
~~~

Đặt descriptor vào lời gọi document của test gửi đúng form media type. Không dùng `requestFields(...)` như thể form body là JSON.

### 6.2. Multipart upload

Multipart gồm nhiều part; mỗi part có thể có tên, filename, media type và nội dung. HTTP client cần tạo boundary đúng. Không tự đặt `Content-Type: multipart/form-data` thiếu boundary khi dựng request thủ công.

~~~java
import org.springframework.mock.web.MockMultipartFile;

import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;

@Test
void documentUploadCover() throws Exception {
    MockMultipartFile file = new MockMultipartFile(
        "file", "cover.png", MediaType.IMAGE_PNG_VALUE,
        new byte[] { 1, 2, 3, 4 }
    );

    mockMvc.perform(multipart("/api/books/42/cover")
            .file(file)
            .param("description", "Book cover"))
        .andExpect(status().isCreated())
        .andDo(document("book-cover-upload",
            requestParts(
                partWithName("file").description("Ảnh bìa sách")
            )
        ));
}
~~~

Ví dụ giả định endpoint nhận part `file` và metadata `description`. Byte array chỉ là fixture. `requestParts(...)` mô tả từng part; nếu cần mô tả form field, dùng descriptor phù hợp và xác minh output thực tế.

## 7. Text, binary và body lớn

Request plain text:

~~~http
POST /api/search HTTP/1.1
Content-Type: text/plain
Accept: text/plain

Spring REST Docs
~~~

Dùng `contentType(MediaType.TEXT_PLAIN)` và `content(...)`; kiểm tra response bằng `content().string(...)`. Không dùng field descriptors của JSON cho text body.

Response file PDF có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice-102.pdf"

(binary bytes)
~~~

Test có thể so sánh bytes, checksum, kích thước hoặc headers. Với file lớn, tránh nhúng toàn bộ binary vào tài liệu; mô tả status, media type, `Content-Disposition`, kích thước và cách tải. Streaming response cần chiến lược test theo cách tiêu thụ stream; `responseFields(...)` không mô tả binary.

## 8. Encoding và serialization

Body JSON có thể chứa Unicode:

~~~json
{"name":"Nguyễn Thị Lan","note":"Giao sách vào buổi sáng"}
~~~

Chuẩn hóa file và fixture theo UTF-8; kiểm tra giá trị deserialize. Không bắt buộc thêm `charset=UTF-8` vào mọi `application/json` nếu hợp đồng không yêu cầu.

Phân biệt các kiểu JSON:

~~~json
{"quantity":2,"quantityText":"2","available":true,"description":null}
~~~

Số `2`, chuỗi `"2"`, boolean `true` và `null` khác nhau. Field descriptor mô tả vị trí/ý nghĩa, không thay thế JSON Schema hoặc assertion kiểu/giá trị. Hai JSON khác khoảng trắng hoặc thứ tự property vẫn có thể tương đương về cấu trúc; nếu chữ ký số/checksum yêu cầu bytes chính xác, phải kiểm tra bytes theo hợp đồng.

## 9. Body rỗng và response đặc biệt

| Trường hợp | Method/status | Quy tắc |
| --- | --- | --- |
| Xóa thành công | `204 No Content` | Không có response body. |
| Cache chưa thay đổi | `304 Not Modified` | Không có response body. |
| HEAD | `HEAD` | Không có response body; headers có thể mô tả GET tương ứng. |
| Response lỗi | `4xx`/`5xx` | Có thể có body lỗi theo contract. |
| Tải file | `200 OK` | Body có thể là binary. |

Test `204`:

~~~java
mockMvc.perform(delete("/api/books/42"))
    .andExpect(status().isNoContent())
    .andExpect(content().string(""));
~~~

Không khai báo `responseFields(...)` cho payload không tồn tại. Với `304`, kiểm tra validator/header và body rỗng. Với `HEAD`, phân biệt metadata response với body thực.

## 10. Preprocess body và bảo vệ dữ liệu

Spring REST Docs hỗ trợ preprocess bản ghi dùng cho snippet. `prettyPrint()` giúp JSON dễ đọc; `removeHeaders(...)` loại bỏ header nhạy cảm khỏi tài liệu; `modifyHeaders()` thay giá trị header trong bản ghi.

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

// Thay lời gọi document(...) cuối test bằng:
.andDo(document("books-create",
    preprocessRequest(
        removeHeaders("Authorization", "Cookie"),
        prettyPrint()
    ),
    preprocessResponse(
        removeHeaders("Set-Cookie", "X-Internal-Trace"),
        prettyPrint()
    ),
    requestFields(
        fieldWithPath("title").description("Tên sách"),
        fieldWithPath("price").description("Giá sách")
    ),
    responseFields(
        fieldWithPath("id").description("Mã sách"),
        fieldWithPath("title").description("Tên sách"),
        fieldWithPath("price").description("Giá sách")
    )
));
~~~

Đây là lời gọi thay thế nếu test đã có `document("books-create", ...)`; không thêm lần thứ hai cùng identifier. Payload phải khớp descriptors và header bị xóa không được đồng thời mô tả là bắt buộc trong bản ghi.

- Dùng fixture giả; không đưa password, token, cookie hay dữ liệu cá nhân thật vào test tài liệu công khai.
- Preprocessor chỉ tác động bản ghi sinh snippet, không sửa request/response gốc mà ứng dụng xử lý.
- Nếu xóa header khỏi bản ghi, không mô tả header đó như header bắt buộc đang hiện diện.
- Không dùng pretty print/masking để che payload sai hợp đồng; assertions phải kiểm tra response gốc.
- Với binary/file lớn, tránh nhúng toàn bộ bytes vào artifact tài liệu.

## 11. WebTestClient và REST Assured

### 11.1. WebTestClient

Ví dụ với client đã cấu hình Spring REST Docs:

~~~java
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.post()
    .uri("/api/books")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue("""
        {"title":"Spring in Action","price":199000}
        """)
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.title").isEqualTo("Spring in Action")
    .consumeWith(document("books-create-webtestclient"));
~~~

`bodyValue(...)` cung cấp payload; `contentType(...)` khai báo định dạng request; `accept(...)` nêu định dạng response mong muốn. Cần module `spring-restdocs-webtestclient` và documentation context phù hợp.

### 11.2. REST Assured

~~~java
import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

given(spec)
    .filter(document("books-create-restassured"))
    .contentType("application/json")
    .accept("application/json")
    .body("""
        {"title":"Spring in Action","price":199000}
        """)
.when()
    .post("/api/books")
.then()
    .statusCode(201)
    .contentType("application/json");
~~~

`spec` là `RequestSpecification` đã cấu hình server và REST Docs. Dùng module `spring-restdocs-restassured` và filter/configurer phù hợp. Filter có thể ghi operation trước khi assertion cuối tại `then()` hoàn tất; CI phải yêu cầu toàn bộ test PASS trước khi publish.

## 12. Biên soạn tài liệu và tích hợp CI

Asciidoctor có thể include snippet:

~~~asciidoc
= Books API

== Tạo sách

=== HTTP request
include::{snippets}/books-create/http-request.adoc[]

=== Request body
include::{snippets}/books-create/request-body.adoc[]

=== Request fields
include::{snippets}/books-create/request-fields.adoc[]

=== HTTP response
include::{snippets}/books-create/http-response.adoc[]

=== Response body
include::{snippets}/books-create/response-body.adoc[]

=== Response fields
include::{snippets}/books-create/response-fields.adoc[]
~~~

Thuộc tính `snippets` phải trỏ tới output directory, ví dụ `build/generated-snippets`. Markdown renderer thuần thường không hiểu trực tiếp cú pháp Asciidoctor include; cần template hoặc bước chuyển đổi/nhúng phù hợp.

~~~mermaid
flowchart TD
    A["HTTP tests"] --> B{"Status/body assertions pass?"}
    B -->|No| C["Fail pipeline"]
    B -->|Yes| D["Spring REST Docs sinh snippets"]
    D --> E["Asciidoctor/Markdown build"]
    E --> F{"Render pass?"}
    F -->|No| C
    F -->|Yes| G["Package / Publish"]
~~~

Task biên soạn phải phụ thuộc task test sinh snippet. Quản lý output directory để tránh include file cũ từ lần chạy trước. Nếu payload schema thay đổi mà descriptor chưa cập nhật, test nên thất bại trước khi tài liệu được phát hành.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `415 Unsupported Media Type` | Content-Type không được endpoint/converter hỗ trợ | Kiểm tra `consumes`, converter và body. |
| `406 Not Acceptable` | Accept yêu cầu representation không được cung cấp | Kiểm tra `produces` và converter. |
| `400 Bad Request` | JSON/XML sai cú pháp hoặc bind/validation thất bại | Xác minh payload và error handling. |
| `request-fields.adoc` fail vì field mới | Payload có field chưa mô tả ở strict mode | Cập nhật descriptor hoặc relaxed mode có chủ đích. |
| XML không parse được | Thiếu converter hoặc media type sai | Cấu hình XML converter và test endpoint. |
| Multipart sai boundary | Tự dựng header thiếu boundary | Dùng multipart builder của HTTP client. |
| JSON Unicode lỗi | Fixture/file sai encoding | Chuẩn hóa UTF-8 theo contract. |
| Binary snippet quá lớn | Nhúng toàn bộ file vào tài liệu | Mô tả metadata, kích thước hoặc checksum. |
| `204` có descriptor JSON | Giả định response có body | Assert body rỗng và bỏ response fields. |
| Secret xuất hiện trong snippet | Fixture/header dùng dữ liệu thật | Dùng dữ liệu giả và preprocess. |
| CI dùng snippet cũ | Docs task không phụ thuộc test hoặc output tồn dư | Ràng buộc task và quản lý artifacts. |

## 14. Bài thực hành

Xây dựng tài liệu cho API quản lý hồ sơ:

| Operation | Body/media type | Kết quả |
| --- | --- | --- |
| `POST /api/profiles` | JSON gồm `name`, `email` | `201 Created`, JSON response có `id`. |
| `GET /api/profiles/42` | Không có request body | `200 OK`, JSON response lồng nhau. |
| `POST /api/profiles/import` | Multipart file CSV và metadata | Ví dụ `202 Accepted` nếu contract hỗ trợ. |
| `POST /api/profiles/form` | Form URL-encoded | Response theo contract. |
| `GET /api/profiles/999` | Không có request body | `404 Not Found` và error schema đã định nghĩa. |

Yêu cầu:

1. Viết test JSON create/get; assert status, media type và field quan trọng.
2. Sinh `request-body`, `response-body`, `request-fields` và `response-fields`.
3. Thêm field optional để thử `optional()` và field chưa mô tả để quan sát strict descriptor.
4. Viết multipart test với file fixture giả và mô tả part qua `requestParts(...)`.
5. Viết form URL-encoded test, phân biệt form parameters với query parameters.
6. Thêm response không body (ví dụ `204` nếu API hỗ trợ) và không mô tả JSON fields.
7. Include snippet vào Asciidoctor; bảo đảm test thành công trước bước publish.

**Tiêu chí hoàn thành:** xác định đúng media type/body từng chiều; mô tả đúng JSON/XML/form/multipart; kiểm chứng payload bằng assertions và descriptor; xử lý body rỗng, binary và dữ liệu nhạy cảm; tích hợp tài liệu sinh từ test vào CI.

## Tài liệu tham khảo

- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/default-snippets.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring Framework — Request Mapping: Consumes and Produces](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
