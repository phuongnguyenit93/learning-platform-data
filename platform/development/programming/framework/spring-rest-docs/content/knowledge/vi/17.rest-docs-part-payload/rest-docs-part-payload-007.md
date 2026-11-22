# Phân biệt body của request với body của part trong Spring REST Docs

## 1. Một HTTP request có thể chứa nhiều lớp body

Với request thông thường gửi JSON, request body là payload nằm sau HTTP headers. Nhưng với `multipart/form-data`, body của HTTP request là một envelope gồm boundary, header riêng của từng part và nội dung của từng part:

```http
POST /api/documents HTTP/1.1
Host: api.example.test
Content-Type: multipart/form-data; boundary=----DocBoundary

------DocBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Spring REST Docs","visibility":"TEAM"}
------DocBoundary
Content-Disposition: form-data; name="file"; filename="guide.pdf"
Content-Type: application/pdf

...binary PDF bytes...
------DocBoundary--
```

Trong request trên:

- **Body của request** là toàn bộ multipart envelope, từ boundary mở đầu đến boundary kết thúc.
- **Body của part `metadata`** là riêng chuỗi JSON.
- **Body của part `file`** là riêng các byte của file PDF.

Nếu tài liệu gọi request này là “JSON request”, người tích hợp có thể gửi một JSON body đơn thay vì multipart. Ngược lại, nếu cần giải thích schema JSON của `metadata`, chỉ mô tả toàn bộ request body cũng không giúp người đọc nhận diện các field trong part đó.

Spring REST Docs sinh snippet từ kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Module **SPRING_REST_DOCS** giúp tạo REST API documentation có thể kiểm chứng, biên soạn snippet thành Asciidoctor/Markdown và đưa vào build/CI. Bài thuộc chương **Part payload**, tập trung phân biệt body cấp request và body của một part.

Sau bài học, bạn có thể:

1. Phân biệt HTTP request body với body của một multipart part.
2. Chọn đúng `requestBody()`, `requestFields(...)`, `requestPartBody(...)` và `requestPartFields(...)`.
3. Hiểu vai trò của `requestParts(...)` và part headers.
4. Viết kiểm thử MockMvc cho JSON request thông thường và multipart request.
5. Ghép đúng các snippet vào tài liệu và tránh mô tả sai cấu trúc request.

## 2. Phạm vi của body trong HTTP

`Content-Type` mô tả cách diễn giải body của HTTP message:

| Request | Content-Type | Body ở cấp HTTP |
| --- | --- | --- |
| `POST /api/products` gửi JSON | `application/json` | Một JSON document |
| `PUT /api/profile` gửi XML | `application/xml` | Một XML document |
| `POST /api/documents` gửi multipart | `multipart/form-data; boundary=...` | Multipart envelope gồm nhiều part |
| `POST /api/search` không có payload | Không có body hoặc body rỗng tùy request | Không có payload để mô tả |

Với JSON request thông thường:

```http
POST /api/products HTTP/1.1
Content-Type: application/json

{"name":"Keyboard","price":75}
```

Toàn bộ object JSON là request body. Có thể mô tả payload đó bằng `requestFields(...)` và/hoặc snippet body phù hợp.

Với multipart, HTTP body chứa nhiều part. Mỗi part có header và body riêng; ví dụ JSON là body của part `metadata` còn file PDF là body của part `file`. Content-Type của part không thay đổi Content-Type tổng của request: request vẫn là `multipart/form-data`.

## 3. Bốn snippet payload cần phân biệt

Các API dưới đây thuộc `org.springframework.restdocs.payload.PayloadDocumentation`:

| API | Phạm vi được document | Ví dụ sử dụng |
| --- | --- | --- |
| `requestBody()` | Body của toàn HTTP request | Hiển thị body request dưới dạng snippet |
| `requestFields(...)` | Các field trong request payload chính, thường là JSON | Mô tả `name`, `price` trong JSON body |
| `requestPartBody("metadata")` | Body của part có tên metadata | Hiển thị JSON/text/XML nguyên part |
| `requestPartFields("metadata", ...)` | Các field bên trong body part metadata | Mô tả `title`, `visibility` của JSON part |

Hai nhóm API không thay thế nhau. `requestFields(...)` không có đối số tên part vì nó làm việc với payload cấp request. `requestPartFields(...)` cần tên part để xác định payload cần document.

### 3.1. Request body thông thường

Với JSON body:

```json
{
  "name": "Keyboard",
  "price": 75
}
```

Mô tả field:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

requestFields(
    fieldWithPath("name").description("Tên sản phẩm"),
    fieldWithPath("price").description("Giá sản phẩm")
)
```

Ở đây `name` và `price` thuộc JSON body chính của request.

### 3.2. Body của multipart part

Với part `metadata` có JSON:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

requestPartFields("metadata",
    fieldWithPath("title").description("Tên tài liệu"),
    fieldWithPath("visibility").description("Phạm vi hiển thị")
)
```

Tên part `"metadata"` giúp Spring REST Docs tìm đúng body con. Nếu bỏ hoặc ghi sai tên part, descriptor không trỏ đến payload cần document.

### 3.3. Ví dụ body đầy đủ

Muốn hiển thị nguyên JSON của body chính, dùng `requestBody()`. Với riêng JSON part, dùng `requestPartBody("metadata")`:

```java
requestBody()
requestPartBody("metadata")
```

Không giả định snippet toàn request body sẽ tự tách payload con của multipart thành các ví dụ độc lập. Khi cần nêu body của một part, hãy khai báo snippet part tương ứng.

## 4. Multipart envelope và cấu trúc part

Multipart body có dạng khái quát:

```text
--boundary
part headers

part body
--boundary
part headers

part body
--boundary--
```

Một part thường có:

- `Content-Disposition`: tên trường form, có thể kèm `filename`.
- `Content-Type`: media type của nội dung part.
- Các header khác nếu hợp đồng hoặc ứng dụng sử dụng.
- Body: dữ liệu text, JSON, XML hoặc bytes nhị phân.

Tên part, header và body là ba khía cạnh khác nhau. `requestParts(...)` mô tả part; `requestPartBody(...)` mô tả nội dung; `requestPartFields(...)` mô tả schema của nội dung.

## 5. Mô hình Spring MVC: @RequestBody và @RequestPart

### 5.1. JSON request body với @RequestBody

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

record ProductInput(String name, int price) {}

@RestController
class ProductController {
    @PostMapping(path = "/api/products", consumes = MediaType.APPLICATION_JSON_VALUE)
    ProductInput create(@RequestBody ProductInput input) {
        return input;
    }
}
```

`@RequestBody` gắn với body chính của HTTP request. Khi document payload JSON này, thường dùng `requestFields(...)`.

### 5.2. Multipart part với @RequestPart

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

record DocumentMetadata(String title, String visibility) {}
record DocumentReceipt(String id, String title, String filename) {}

@RestController
class DocumentController {
    @PostMapping(path = "/api/documents", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    DocumentReceipt upload(
            @RequestPart("metadata") DocumentMetadata metadata,
            @RequestPart("file") MultipartFile file) {
        return new DocumentReceipt("DOC-42", metadata.title(), file.getOriginalFilename());
    }
}
```

`@RequestPart("metadata")` yêu cầu Spring đọc body của part `metadata` qua message converter phù hợp. `@RequestPart("file")` nhận file upload. Mặc dù controller nhận object `DocumentMetadata`, JSON của nó vẫn là **part body**, không phải toàn bộ HTTP request body.

`@RequestParam` thường bind query parameters hoặc form parameters. Đừng suy luận rằng mọi tham số controller đều thuộc request body chính; hãy xét vị trí dữ liệu trong HTTP message và cơ chế binding.

## 6. Ví dụ A: document JSON body thông thường

Đây là test MockMvc dành cho JSON request body:

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
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ProductRequestBodyDocumentationTest {
    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ProductController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsJsonRequestFields() throws Exception {
        mockMvc.perform(post("/api/products")
                        .contentType("application/json")
                        .content("""
                                {"name":"Keyboard","price":75}
                                """))
                .andExpect(status().isOk())
                .andDo(document("product-create",
                        requestFields(
                                fieldWithPath("name").description("Tên sản phẩm"),
                                fieldWithPath("price").description("Giá sản phẩm")
                        )));
    }
}
```

Với JSON request, `requestFields(...)` document payload object. Có thể thêm `requestBody()` nếu trang tài liệu cần snippet chứa body nguyên vẹn; chọn snippet theo mục đích và template format của dự án.

## 7. Ví dụ B: document body của một multipart part

### 7.1. Chuẩn bị part

```java
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

MockMultipartFile metadata = new MockMultipartFile(
        "metadata", "", MediaType.APPLICATION_JSON_VALUE,
        """
        {"title":"Spring REST Docs","visibility":"TEAM"}
        """.getBytes(StandardCharsets.UTF_8));

MockMultipartFile file = new MockMultipartFile(
        "file", "guide.pdf", MediaType.APPLICATION_PDF_VALUE,
        "%PDF-demo".getBytes(StandardCharsets.UTF_8));
```

Tham số đầu tiên của `MockMultipartFile` là tên part. Nó phải khớp với `@RequestPart("metadata")`, `@RequestPart("file")` và descriptor `partWithName(...)`.

### 7.2. MockMvc test cho nhiều phạm vi

```java
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class DocumentMultipartDocumentationTest {
    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new DocumentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsPartAndItsJsonPayload() throws Exception {
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata", "", MediaType.APPLICATION_JSON_VALUE,
                """
                {"title":"Spring REST Docs","visibility":"TEAM"}
                """.getBytes(StandardCharsets.UTF_8));
        MockMultipartFile file = new MockMultipartFile(
                "file", "guide.pdf", MediaType.APPLICATION_PDF_VALUE,
                "%PDF-demo".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/documents").file(metadata).file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("DOC-42"))
                .andExpect(jsonPath("$.title").value("Spring REST Docs"))
                .andDo(document("document-upload",
                        requestParts(
                                partWithName("metadata").description("Metadata dạng JSON"),
                                partWithName("file").description("File PDF cần upload")
                        ),
                        requestPartFields("metadata",
                                fieldWithPath("title").description("Tiêu đề tài liệu"),
                                fieldWithPath("visibility").description("Phạm vi hiển thị")
                        ),
                        requestPartBody("metadata")
                ));
    }
}
```

Trong `document(...)`, ba snippet có trách nhiệm khác nhau:

1. `requestParts(...)` mô tả hai part `metadata` và `file`.
2. `requestPartFields("metadata", ...)` mô tả schema JSON trong metadata.
3. `requestPartBody("metadata")` tạo ví dụ body của riêng part metadata.

Không khai báo `requestFields(...)` cho `title` và `visibility` ở test này: chúng thuộc JSON nằm bên trong multipart part. Cũng không dùng `requestBody()` thay cho `requestPartBody("metadata")` khi ý định là hiển thị riêng JSON metadata.

## 8. Có nên document toàn bộ multipart body bằng requestBody()?

Multipart envelope là body của HTTP request ở cấp giao thức. Tuy nhiên, đưa nguyên envelope vào snippet text thường ít hữu ích:

- Boundary có thể do client sinh động, không nên coi boundary cụ thể là giá trị hợp đồng.
- File part có thể là dữ liệu nhị phân, không thể hiện tốt trong snippet văn bản.
- Header riêng của từng part dễ bị chìm trong một khối body dài.
- Người đọc thường cần biết tên, loại và schema từng part để tạo request đúng.

Với multipart endpoint, cách trình bày phổ biến:

| Nhu cầu | Snippet nên dùng |
| --- | --- |
| Liệt kê part và mô tả mục đích | `requestParts(...)` |
| Hiển thị JSON/text body của một part | `requestPartBody("partName")` |
| Giải thích field JSON của một part | `requestPartFields("partName", ...)` |
| Mô tả header của HTTP request | `requestHeaders(...)` |
| Mô tả header riêng của part | Mô tả trong bảng part hoặc tài liệu riêng nếu API yêu cầu |

Chỉ dùng snippet body cấp request khi nó thực sự giúp người đọc hiểu request. Với multipart, tài liệu hóa theo từng part thường rõ ràng và dễ bảo trì hơn.

## 9. Snippet output và Asciidoctor

Với identifier `document-upload`, output thường có các snippet liên quan:

```text
build/generated-snippets/
  document-upload/
    request-parts.adoc
    request-part-metadata-fields.adoc
    request-part-metadata-body.adoc
    http-request.adoc
    http-response.adoc
    ...
```

Tên file cụ thể cần được kiểm tra trong output của phiên bản Spring REST Docs và template format mà dự án đang dùng. Không nên đoán tên snippet rồi đưa vào include nếu chưa xác nhận file tồn tại.

Ví dụ trang Asciidoctor:

```asciidoc
= Document API

== Upload tài liệu

=== Các part của request

include::{snippets}/document-upload/request-parts.adoc[]

=== Schema của metadata

include::{snippets}/document-upload/request-part-metadata-fields.adoc[]

=== Ví dụ metadata body

include::{snippets}/document-upload/request-part-metadata-body.adoc[]

=== HTTP request

include::{snippets}/document-upload/http-request.adoc[]
```

Biến `{snippets}` phải trỏ tới thư mục output snippet. Tên `request-part-metadata-body.adoc` là ví dụ theo quy ước đặt tên; xác minh tên chính xác sau khi chạy test trước khi cố định đường dẫn.

Nếu dùng Markdown, cấu hình `TemplateFormats.markdown()` cho snippet và dùng bước ghép nội dung phù hợp. Markdown cơ bản không có cú pháp include tiêu chuẩn như Asciidoctor.

## 10. WebTestClient và REST Assured

Phạm vi snippet giữ nguyên giữa các test client: body chính và body part là hai khái niệm khác nhau. Điều thay đổi là cách tạo multipart request và cách gắn snippet document vào test.

### 10.1. WebTestClient

`MultipartBodyBuilder` tạo từng part cùng Content-Type:

```java
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.web.reactive.function.BodyInserters;

MultipartBodyBuilder parts = new MultipartBodyBuilder();
parts.part("metadata", """
        {"title":"Spring REST Docs","visibility":"TEAM"}
        """)
        .contentType(MediaType.APPLICATION_JSON);
parts.part("file", new ByteArrayResource("%PDF-demo".getBytes()) {
    @Override
    public String getFilename() {
        return "guide.pdf";
    }
}).contentType(MediaType.APPLICATION_PDF);

webTestClient.post()
        .uri("/api/documents")
        .body(BodyInserters.fromMultipartData(parts.build()))
        .exchange()
        .expectStatus().isOk();
```

Trong test đã tích hợp REST Docs, gắn `requestParts(...)`, `requestPartFields("metadata", ...)` và `requestPartBody("metadata")` vào snippet `document(...)` của WebTestClient. Đoạn trên minh họa tạo request; cần cấu hình REST Docs cho `webTestClient` trước đó.

### 10.2. REST Assured

REST Assured cho phép thiết lập từng part:

```java
given()
        .filter(documentationFilter)
        .multiPart("metadata",
                "{\"title\":\"Spring REST Docs\",\"visibility\":\"TEAM\"}",
                "application/json")
        .multiPart("file", new File("guide.pdf"))
        .when()
        .post("/api/documents")
        .then()
        .statusCode(200);
```

Filter document cần được cấu hình để sinh snippet part và payload tương ứng. Chỉ gọi `multiPart(...)` chưa đủ để tạo snippet nếu không gắn filter với descriptor `requestParts(...)`, `requestPartFields(...)` hoặc `requestPartBody(...)`.

## 11. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng `requestFields(...)` cho JSON metadata nhưng snippet không tìm thấy field | JSON nằm trong part, không phải request body JSON chính | Dùng `requestPartFields("metadata", ...)` |
| `requestBody()` không tạo ví dụ JSON riêng của metadata | Snippet có phạm vi toàn request body | Dùng `requestPartBody("metadata")` |
| Tài liệu gọi multipart request là JSON request | Nhầm content type của part với Content-Type tổng request | Ghi rõ request là multipart và metadata part là JSON |
| Bảng request parts có tên nhưng không có cấu trúc payload | Chỉ dùng `requestParts(...)` | Thêm `requestPartFields(...)` hoặc `requestPartBody(...)` |
| Part JSON bị parse lỗi | Part không có Content-Type phù hợp hoặc body không phải JSON hợp lệ | Thiết lập `application/json` và kiểm tra fixture |
| Snippet request body chứa boundary khó đọc | Cố đưa toàn multipart envelope vào một ví dụ văn bản | Tài liệu hóa riêng part, payload và media type |
| File nhị phân xuất hiện như ký tự khó đọc | Dùng body snippet cho dữ liệu binary | Document file metadata, không dump bytes vào tài liệu |
| Asciidoctor báo thiếu snippet | Tên include dự đoán không khớp output thực tế | Kiểm tra thư mục snippet sau test và sửa include |

## 12. Build và CI

Quy trình triển khai:

1. Khai báo dependency Spring REST Docs phù hợp với MockMvc, WebTestClient hoặc REST Assured.
2. Viết test cho JSON request body và multipart request với part JSON/file riêng biệt.
3. Chọn đúng nhóm descriptor: `requestFields(...)` cho JSON request chính; `requestParts(...)`, `requestPartFields(...)` và `requestPartBody(...)` cho multipart.
4. Cấu hình thư mục snippet như `build/generated-snippets` (Gradle) hoặc `target/generated-snippets` (Maven).
5. Cấu hình task Asciidoctor phụ thuộc task test và include đúng snippet được sinh.
6. Chạy test và render tài liệu trong CI; pipeline phát hiện khi schema body hoặc part thay đổi nhưng descriptor chưa được cập nhật.

Ví dụ lệnh Gradle sau khi dự án đã cấu hình task tương ứng:

```bash
./gradlew test asciidoctor
```

Khi endpoint chuyển từ JSON body đơn sang multipart, đây là thay đổi lớn của hợp đồng HTTP: client phải đổi cách gửi request, media type tổng và cách tạo từng part. Cần cập nhật cả kiểm thử, descriptor và hướng dẫn gọi API.

## 13. Bài tập thực hành

Thiết kế hai endpoint:

**Endpoint A — JSON body**

```http
POST /api/reports
Content-Type: application/json

{"name":"Monthly report","format":"PDF"}
```

**Endpoint B — Multipart**

```http
POST /api/reports/import
Content-Type: multipart/form-data

Part "metadata" (application/json):
{"name":"Monthly report","format":"PDF"}

Part "file" (application/pdf):
...binary content...
```

Thực hiện:

1. Tạo controller cho Endpoint A dùng `@RequestBody ReportInput`; document bằng `requestFields(...)`.
2. Tạo controller cho Endpoint B dùng `@RequestPart("metadata") ReportInput` và `@RequestPart("file") MultipartFile`.
3. Viết MockMvc test cho cả hai endpoint.
4. Với Endpoint B, dùng `requestParts(...)`, `requestPartFields("metadata", ...)` và `requestPartBody("metadata")`.
5. So sánh hai trang tài liệu: cùng schema JSON nhưng một trường hợp là request body chính, trường hợp còn lại là body của part.
6. Include snippet, chạy test và render tài liệu trong CI.

**Tiêu chí hoàn thành:** Chỉ rõ body thuộc cấp request hay part; dùng đúng descriptor cho cả hai endpoint; bảng field và ví dụ body khớp request test; người đọc biết cách gửi JSON body hoặc multipart envelope.

## 14. Ghi nhớ

Body của HTTP request là nội dung ở cấp message. Với multipart, nó là envelope chứa nhiều part, mỗi part có header và body riêng. `requestBody()` và `requestFields(...)` dùng cho payload cấp request; `requestPartBody(partName)` và `requestPartFields(partName, ...)` dùng cho payload của một part; `requestParts(...)` mô tả các part. Chọn đúng phạm vi giúp tài liệu Spring REST Docs mô tả chính xác cách client phải gửi request, đồng thời giữ ví dụ payload và schema có thể kiểm chứng từ test trong build/CI.

### Tài liệu tham khảo

- [Spring REST Docs — Request Parts](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-parts.html)
- [Spring REST Docs — Request Part Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-part-payloads.html)
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring Framework — Multipart Forms and RequestPart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework — RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
