# Document body của một request part trong Spring REST Docs

## 1. Multipart request có nhiều phần nội dung

Một API tải tài liệu có thể nhận đồng thời file nhị phân và phần metadata mô tả file đó. Client thường gửi request theo định dạng multipart/form-data:

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=----Boundary123

------Boundary123
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "title": "Hướng dẫn Spring",
  "category": "TECHNICAL",
  "visibility": "TEAM"
}
------Boundary123
Content-Disposition: form-data; name="file"; filename="spring-guide.pdf"
Content-Type: application/pdf

...binary PDF content...
------Boundary123--
```

Request có hai part:

- metadata: payload JSON chứa title, category và visibility.
- file: nội dung PDF nhị phân, có filename và media type riêng.

Nếu tài liệu chỉ ghi endpoint POST /api/documents và ví dụ multipart chung, client vẫn chưa biết tên từng part, part nào bắt buộc, metadata có trường nào, trường nào được phép bỏ qua hoặc giá trị nào được chấp nhận.

**Spring REST Docs** hỗ trợ document multipart request theo nhiều mức. requestParts(...) mô tả các part có trong request. requestPartFields(...) mô tả cấu trúc payload bên trong một part có nội dung dạng object, thường là JSON. Khi kết hợp hai API, tài liệu vừa cho biết request gồm những phần nào, vừa mô tả body của riêng part metadata.

Module **SPRING_REST_DOCS** tạo tài liệu REST API có thể kiểm chứng từ kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Bài thuộc chương **Part payload**, tập trung vào việc document body của một request part và đưa snippet sinh ra vào Asciidoctor/Markdown, build và CI.

Sau bài học, bạn có thể:

1. Phân biệt mô tả multipart part với mô tả payload bên trong part.
2. Dùng requestParts(...) để mô tả tên, ý nghĩa và tính bắt buộc của part.
3. Dùng requestPartFields(...) để mô tả các field trong body của một part.
4. Viết kiểm thử MockMvc cho request multipart có JSON metadata và file upload.
5. Tạo snippet và ghép chúng vào tài liệu API.

## 2. Hai lớp tài liệu hóa: part và part payload

### 2.1. Mô tả part bằng requestParts(...)

Part là một phần độc lập trong multipart request. Mỗi part có tên, header riêng và body riêng. Ví dụ:

| Tên part | Content-Type | Body |
| --- | --- | --- |
| metadata | application/json | Object JSON mô tả tài liệu |
| file | application/pdf | Byte của file PDF |

Ta mô tả chúng bằng requestParts(...):

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("metadata")
        .description("Metadata của tài liệu, được gửi dưới dạng JSON"),
    partWithName("file")
        .description("File tài liệu cần tải lên")
)
```

Nhóm descriptor này giúp tài liệu liệt kê các part, giải thích mục đích và kiểm tra part được gửi trong request. Nó chưa mô tả các field bên trong JSON metadata.

### 2.2. Mô tả body của part bằng requestPartFields(...)

Khi một part có payload JSON có cấu trúc, ta có thể document từng field:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

requestPartFields("metadata",
    fieldWithPath("title").description("Tiêu đề tài liệu"),
    fieldWithPath("category").description("Danh mục tài liệu"),
    fieldWithPath("visibility").description("Phạm vi hiển thị")
)
```

Tham số đầu tiên "metadata" xác định tên part chứa payload cần mô tả. Các FieldDescriptor sau đó mô tả cấu trúc body của chính part này. Không nhầm nó với requestFields(...), vốn mô tả payload của request body chính.

### 2.3. Khi nào dùng API nào?

| API | Phạm vi | Ví dụ |
| --- | --- | --- |
| requestParts(...) | Tên và mô tả từng part trong multipart request | metadata, file |
| requestPartFields("metadata", ...) | Các field bên trong payload của part metadata | title, category, visibility |
| requestFields(...) | Các field trong request body chính thông thường | JSON body của request |
| requestHeaders(...) | Header của HTTP request | Authorization, Accept |
| responseFields(...) | Field trong response payload | documentId, status |

Với part nhị phân như file PDF, thường mô tả part bằng requestParts(...) và nêu quy tắc file (định dạng, giới hạn dung lượng, filename) trong phần mô tả. requestPartFields(...) dành cho payload có cấu trúc field; không dùng nó để liệt kê byte bên trong file nhị phân.

## 3. Cấu trúc requestPartFields(...)

API requestPartFields(...) nhận tên part và danh sách descriptor. Các descriptor sử dụng cùng mô hình FieldDescriptor với các snippet payload khác của Spring REST Docs:

```java
requestPartFields("metadata",
    fieldWithPath("title")
        .description("Tên hiển thị của tài liệu"),
    fieldWithPath("category")
        .description("Danh mục: TECHNICAL, BUSINESS hoặc OTHER"),
    fieldWithPath("visibility")
        .description("Phạm vi: PRIVATE hoặc TEAM")
)
```

Một số descriptor thường dùng:

| Descriptor | Ý nghĩa |
| --- | --- |
| fieldWithPath("title") | Mô tả field có đường dẫn title |
| description("...") | Giải thích ý nghĩa field |
| optional() | Field có thể vắng mặt trong payload đang document |
| type(JsonFieldType.STRING) | Khai báo kiểu dữ liệu để hiển thị trong snippet |
| attributes(...) | Bổ sung metadata cho template tùy biến |
| subsectionWithPath("properties") | Mô tả một object/subsection như một đơn vị, không liệt kê từng field con |

Ví dụ với field tùy chọn:

```java
requestPartFields("metadata",
    fieldWithPath("title").description("Tiêu đề tài liệu"),
    fieldWithPath("description")
        .description("Mô tả bổ sung")
        .optional()
)
```

Nếu request part trong test không có description, descriptor vẫn hợp lệ vì đã đánh dấu optional. Điều này không tự thay đổi validation của ứng dụng hoặc làm cho mọi giá trị của field đều hợp lệ.

### 3.1. Field lồng nhau

Payload metadata có thể là:

```json
{
  "title": "Hướng dẫn Spring",
  "owner": {
    "id": 42,
    "displayName": "Engineering"
  },
  "tags": ["java", "spring"]
}
```

Có thể mô tả từng field lồng nhau:

```java
requestPartFields("metadata",
    fieldWithPath("title").description("Tiêu đề"),
    fieldWithPath("owner.id").description("ID người sở hữu"),
    fieldWithPath("owner.displayName").description("Tên hiển thị người sở hữu"),
    fieldWithPath("tags").description("Danh sách nhãn")
)
```

Đường dẫn field dùng dấu chấm để đi vào object lồng nhau. Nếu muốn mô tả cả object owner như một nhóm mà không liệt kê chi tiết các field con, có thể dùng subsectionWithPath("owner") và giải thích cấu trúc trong description.

### 3.2. Mảng và phần tử lặp

Với payload:

```json
{
  "attachments": [
    {"name": "diagram.png", "mediaType": "image/png"},
    {"name": "notes.txt", "mediaType": "text/plain"}
  ]
}
```

Mô tả cấu trúc phần tử mảng bằng:

```java
requestPartFields("metadata",
    fieldWithPath("attachments").description("Danh sách file đính kèm"),
    fieldWithPath("attachments[].name").description("Tên file"),
    fieldWithPath("attachments[].mediaType").description("Media type của file")
)
```

Dấu [] biểu diễn các phần tử của mảng. Với cấu trúc phức tạp, hãy kiểm tra đúng JSON path mà payload thực tế cung cấp.

## 4. Ví dụ endpoint nhận JSON part và file

Giả sử API POST /api/documents nhận một JSON metadata cùng một file. DTO minh họa:

```java
public record DocumentMetadata(
        String title,
        String category,
        String visibility) {
}
```

Controller:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
class DocumentController {

    @PostMapping(
            path = "/api/documents",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public DocumentReceipt upload(
            @RequestPart("metadata") DocumentMetadata metadata,
            @RequestPart("file") MultipartFile file) {

        return new DocumentReceipt(
                "DOC-1001",
                metadata.title(),
                file.getOriginalFilename(),
                file.getSize());
    }
}

record DocumentReceipt(
        String documentId,
        String title,
        String filename,
        long size) {
}
```

@RequestPart("metadata") yêu cầu Spring đọc part metadata với message converter phù hợp. Do part này có Content-Type application/json, JSON có thể được deserialize thành DocumentMetadata. @RequestPart("file") nhận nội dung file qua MultipartFile.

## 5. MockMvc test document body của một request part

### 5.1. Chuẩn bị multipart request

Với MockMvc, dùng MockMultipartFile để tạo từng part. Đặt Content-Type riêng cho metadata và file:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;

MockMultipartFile metadataPart = new MockMultipartFile(
        "metadata",
        "",
        MediaType.APPLICATION_JSON_VALUE,
        """
        {
          "title": "Hướng dẫn Spring",
          "category": "TECHNICAL",
          "visibility": "TEAM"
        }
        """.getBytes(StandardCharsets.UTF_8));

MockMultipartFile filePart = new MockMultipartFile(
        "file",
        "spring-guide.pdf",
        MediaType.APPLICATION_PDF_VALUE,
        "%PDF-demo".getBytes(StandardCharsets.UTF_8));

mockMvc.perform(multipart("/api/documents")
        .file(metadataPart)
        .file(filePart));
```

Trong test mẫu này, phần file dùng bytes minh họa để tập trung vào multipart binding; hệ thống thực cần file mẫu hợp lệ nếu có bước kiểm tra nội dung PDF.

### 5.2. Bài kiểm thử tài liệu hoàn chỉnh

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
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;

@ExtendWith(RestDocumentationExtension.class)
class DocumentUploadDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new DocumentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsMetadataPartPayload() throws Exception {
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata",
                "",
                MediaType.APPLICATION_JSON_VALUE,
                """
                {
                  "title": "Hướng dẫn Spring",
                  "category": "TECHNICAL",
                  "visibility": "TEAM"
                }
                """.getBytes(StandardCharsets.UTF_8));

        MockMultipartFile file = new MockMultipartFile(
                "file",
                "spring-guide.pdf",
                MediaType.APPLICATION_PDF_VALUE,
                "%PDF-demo".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/documents")
                        .file(metadata)
                        .file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.documentId").value("DOC-1001"))
                .andExpect(jsonPath("$.title").value("Hướng dẫn Spring"))
                .andExpect(jsonPath("$.filename").value("spring-guide.pdf"))
                .andDo(document("document-upload",
                        requestParts(
                                partWithName("metadata")
                                        .description("Metadata tài liệu dạng JSON"),
                                partWithName("file")
                                        .description("File PDF cần tải lên")
                        ),
                        requestPartFields("metadata",
                                fieldWithPath("title")
                                        .description("Tiêu đề tài liệu"),
                                fieldWithPath("category")
                                        .description("Danh mục: TECHNICAL, BUSINESS hoặc OTHER"),
                                fieldWithPath("visibility")
                                        .description("Phạm vi hiển thị: PRIVATE hoặc TEAM")
                        )));
    }
}
```

Phần quan trọng nằm trong document(...):

1. requestParts(...) document hai part metadata và file.
2. requestPartFields("metadata", ...) document ba field trong body của part metadata.
3. Các assertion jsonPath(...) xác minh controller đã binding metadata và filename đúng. Chỉ sinh snippet không chứng minh được quy tắc nghiệp vụ hoặc quá trình lưu file thành công.

MockMultipartFile có tham số đầu là tên part. Tên này phải khớp với @RequestPart("metadata"), @RequestPart("file") và tên trong descriptor. Part metadata phải có application/json để Spring chọn converter đọc JSON; file có media type thích hợp với hợp đồng upload.

## 6. Snippet được sinh ra và cách đưa vào Asciidoctor

Với identifier document-upload, Spring REST Docs tạo snippet cho các phần đã document. Những file liên quan thường gồm:

```text
build/generated-snippets/
  document-upload/
    request-parts.adoc
    request-part-metadata-fields.adoc
    http-request.adoc
    http-response.adoc
    curl-request.adoc
    ...
```

Tên snippet cụ thể phụ thuộc snippet/template format và phiên bản Spring REST Docs. request-parts.adoc chứa bảng các part; snippet field của part metadata chứa bảng các field được khai báo trong requestPartFields(...).

Trang tài liệu Asciidoctor có thể chèn:

```asciidoc
= Document API

== Upload tài liệu

POST /api/documents

=== Request parts

include::{snippets}/document-upload/request-parts.adoc[]

=== Metadata part payload

include::{snippets}/document-upload/request-part-metadata-fields.adoc[]

=== HTTP request

include::{snippets}/document-upload/http-request.adoc[]
```

Biến {snippets} phải trỏ đến thư mục output snippet. Nếu dự án sử dụng Markdown, có thể chọn TemplateFormats.markdown() cho snippet và dùng bước ghép Markdown phù hợp; Markdown cơ bản không có cơ chế include tiêu chuẩn như Asciidoctor.

## 7. Payload lồng nhau, field tùy chọn và field không mong muốn

requestPartFields(...) có cơ chế descriptor tương tự các snippet request/response fields khác.

### 7.1. Field tùy chọn

Payload:

```json
{
  "title": "Hướng dẫn Spring",
  "category": "TECHNICAL"
}
```

Nếu visibility không có trong payload của một request có thể document:

```java
requestPartFields("metadata",
    fieldWithPath("title").description("Tiêu đề"),
    fieldWithPath("category").description("Danh mục"),
    fieldWithPath("visibility")
        .description("Phạm vi hiển thị; mặc định TEAM")
        .optional()
)
```

Descriptor optional cho phép field vắng mặt trong payload test nhưng vẫn giữ mô tả của nó trong bảng. Giá trị mặc định TEAM phải được ứng dụng thực thi và kiểm thử riêng.

### 7.2. Field được bỏ qua

Khi payload có một field kỹ thuật đã biết nhưng không muốn xuất hiện trong bảng tài liệu:

```java
requestPartFields("metadata",
    fieldWithPath("title").description("Tiêu đề"),
    fieldWithPath("internalChecksum").ignored()
)
```

Field ignored được nhận diện nhưng không được document như field công khai. Không nên dùng nó để che giấu field client cần biết.

### 7.3. Chỉ mô tả một subsection

Với object có nhiều field con:

```json
{
  "title": "Hướng dẫn Spring",
  "owner": {
    "id": 42,
    "team": "Engineering"
  },
  "audit": {
    "createdBy": "user-7",
    "createdAt": "2026-11-01T09:00:00Z"
  }
}
```

Có thể document từng field bằng đường dẫn đầy đủ hoặc mô tả một object con bằng subsectionWithPath("owner"). Nếu API muốn công bố toàn bộ cấu trúc owner, cách liệt kê owner.id và owner.team giúp người dùng hiểu rõ schema hơn.

## 8. Phân biệt lỗi mô tả part và lỗi mô tả payload

| Dấu hiệu | Phạm vi lỗi | Cách xử lý |
| --- | --- | --- |
| Request gửi part thumbnail nhưng descriptor requestParts(...) chưa có tên này | Part chưa được mô tả | Thêm partWithName("thumbnail") hoặc xử lý theo hợp đồng |
| Request thiếu part metadata trong khi descriptor bắt buộc | Part bắt buộc vắng mặt | Gửi part hoặc đánh dấu optional nếu API cho phép |
| Payload metadata có field author nhưng descriptor không có | Field bên trong part chưa được mô tả | Thêm fieldWithPath("author") |
| Descriptor yêu cầu visibility nhưng JSON không có field đó | Field được mô tả nhưng thiếu trong payload test | Thêm field vào fixture hoặc dùng optional() nếu đúng hợp đồng |
| Part metadata gửi dưới text/plain nhưng controller mong JSON | Message converter không đọc theo định dạng mong đợi | Gán Content-Type application/json cho part |
| File part bị đưa vào requestPartFields(...) | Nhầm payload nhị phân với object payload | Document file bằng requestParts(...), giải thích media type, filename, dung lượng |
| Snippet part được sinh nhưng thiếu bảng metadata | Chỉ gọi requestParts(...), chưa gọi requestPartFields(...) | Thêm snippet mô tả body của part |

## 9. Một số lưu ý về kiểm thử multipart

**Tên part phải thống nhất.** Tên trong multipart request, @RequestPart, requestParts(...) và đối số đầu của requestPartFields(...) phải chỉ cùng một part.

**Content-Type của từng part quan trọng.** JSON metadata nên có application/json; file có thể dùng media type cụ thể như application/pdf hoặc image/png. Không chỉ dựa vào Content-Type tổng của request là multipart/form-data.

**Part JSON và file có vai trò khác nhau.** Một part có thể được parse thành DTO và document field; part file thường là byte stream hoặc MultipartFile. Nếu API nhận thêm part text, nêu rõ charset/format trong mô tả.

**Đừng phụ thuộc vào boundary cụ thể.** Boundary được HTTP client sinh ra; test và tài liệu nên quan tâm tên part, payload và media type, không hard-code boundary vào hợp đồng.

**Xác thực upload cần test riêng.** Loại file, dung lượng tối đa, filename, nội dung file, virus scanning và quyền upload là quy tắc ứng dụng. Descriptor chỉ mô tả payload và không thay thế kiểm thử các điều kiện bảo mật/validation.

## 10. WebTestClient và REST Assured

requestParts(...) và requestPartFields(...) mô tả cùng một khái niệm multipart request, dù cách xây dựng request khác nhau giữa các test client.

### 10.1. WebTestClient

Với WebTestClient đã được cấu hình Spring REST Docs, dùng multipart inserter để gửi part. Ví dụ khái quát:

```java
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.web.reactive.function.BodyInserters;

MultipartBodyBuilder bodyBuilder = new MultipartBodyBuilder();
bodyBuilder.part("metadata", """
        {"title":"Hướng dẫn Spring","category":"TECHNICAL","visibility":"TEAM"}
        """)
        .contentType(MediaType.APPLICATION_JSON);
bodyBuilder.part("file", new ByteArrayResource("%PDF-demo".getBytes()) {
    @Override
    public String getFilename() {
        return "spring-guide.pdf";
    }
}).contentType(MediaType.APPLICATION_PDF);

webTestClient.post()
        .uri("/api/documents")
        .body(BodyInserters.fromMultipartData(bodyBuilder.build()))
        .exchange()
        .expectStatus().isOk();
```

Khi document, gắn snippet requestParts(...) và requestPartFields("metadata", ...) vào cơ chế document(...) của tích hợp WebTestClient. WebTestClient cần được cấu hình REST Docs trước; đoạn code trên minh họa việc tạo request multipart.

### 10.2. REST Assured

REST Assured hỗ trợ gửi multipart parts qua các overload multiPart(...). Ví dụ minh họa:

```java
given()
        .filter(documentationFilter)
        .multiPart("metadata",
                "{\"title\":\"Hướng dẫn Spring\",\"category\":\"TECHNICAL\","
                        + "\"visibility\":\"TEAM\"}",
                "application/json")
        .multiPart("file", new File("spring-guide.pdf"))
        .when()
        .post("/api/documents")
        .then()
        .statusCode(200);
```

Filter documentationFilter cần được cấu hình với tích hợp Spring REST Docs và danh sách snippet có requestParts(...), requestPartFields(...). Cú pháp cụ thể của overload multipart phụ thuộc phiên bản REST Assured; hãy xác nhận Content-Type part thực tế trong request được gửi.

## 11. Build, Asciidoctor và CI

Luồng triển khai:

1. Chọn tích hợp Spring REST Docs phù hợp với test client (spring-restdocs-mockmvc, spring-restdocs-webtestclient hoặc spring-restdocs-restassured).
2. Viết test multipart gửi cả part JSON và part file, kiểm tra response và document các part.
3. Cấu hình thư mục snippet như build/generated-snippets làm output của task test.
4. Cho task Asciidoctor phụ thuộc task test và include request-parts.adoc, snippet field của metadata và các snippet HTTP cần thiết.
5. Chạy test cùng bước render tài liệu trong CI để phát hiện thay đổi tên part hoặc schema metadata chưa được document.

Ví dụ lệnh Gradle khi task đã được cấu hình:

```bash
./gradlew test asciidoctor
```

Khi thay đổi payload metadata, bài test với requestPartFields(...) strict sẽ yêu cầu cập nhật descriptor nếu xuất hiện field mới hoặc field được mô tả bị thiếu. Đây là cơ chế hữu ích để giữ schema part payload đồng bộ với request test.

## 12. Bài tập thực hành

Thiết kế endpoint:

```http
POST /api/media
Content-Type: multipart/form-data

Part "metadata" (application/json):
{
  "name": "Team photo",
  "description": "Ảnh nhóm",
  "labels": ["team", "2026"]
}

Part "image" (image/png):
...binary image...
```

Hợp đồng:

- metadata bắt buộc, là JSON object.
- name bắt buộc; description tùy chọn; labels là mảng chuỗi tùy chọn.
- image bắt buộc, chỉ nhận PNG; giới hạn kích thước do ứng dụng xác định.

Thực hiện:

1. Tạo DTO metadata và controller nhận @RequestPart("metadata") cùng @RequestPart("image").
2. Viết MockMvc test tạo MockMultipartFile cho JSON metadata và file PNG.
3. Dùng requestParts(...) mô tả hai part; dùng requestPartFields("metadata", ...) mô tả name, description, labels.
4. Thử bỏ description khỏi JSON và đánh dấu descriptor optional; thử bỏ name và xác nhận ứng dụng từ chối.
5. Thêm test media type hoặc kích thước file không hợp lệ; khẳng định validation server trả lỗi phù hợp.
6. Sinh snippet và include vào trang Asciidoctor; chạy test cùng render tài liệu trong CI.

**Tiêu chí hoàn thành:** Tài liệu phân biệt rõ hai part, mô tả được schema metadata, phản ánh field bắt buộc/tùy chọn, và kiểm thử xác nhận binding/validation thực tế.

## 13. Ghi nhớ

Một multipart request chứa nhiều part; requestParts(...) mô tả từng part, còn requestPartFields("partName", ...) mô tả payload có cấu trúc bên trong part được chọn. Dùng requestFields(...) cho request body chính thông thường, không thay thế việc mô tả body của multipart part. Kết hợp MockMvc/WebTestClient/REST Assured, assertion ứng dụng và snippet Asciidoctor/Markdown để tài liệu upload có thể kiểm chứng trong build/CI.

### Tài liệu tham khảo

- [Spring REST Docs — Request Parts](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-parts.html)
- [Spring REST Docs — Request Part Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-part-payloads.html)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring Framework — Multipart Resolver and RequestPart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
