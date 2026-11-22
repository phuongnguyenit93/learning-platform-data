# Document upload multipart bằng request parts

## 1. Bài toán capstone

API quản lý tài liệu cho phép client tải lên một file cùng metadata mô tả file đó. Request dùng multipart/form-data với hai part:

- file: nội dung file nhị phân, ví dụ PDF.
- metadata: JSON mô tả tên hiển thị, loại tài liệu và nhãn.

Ví dụ request:

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=...

--...
Content-Disposition: form-data; name="file"; filename="contract.pdf"
Content-Type: application/pdf

<binary file bytes>
--...
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "title": "Hợp đồng dịch vụ",
  "category": "LEGAL",
  "tags": ["signed", "customer"]
}
--...--
```

Nếu chỉ document request body tổng thể, người đọc khó biết mỗi part có tên gì, media type nào, part nào bắt buộc và JSON metadata có field nào. Spring REST Docs cung cấp request parts và request part descriptors để mô tả từng phần của multipart request.

Module **SPRING_REST_DOCS** tạo tài liệu REST API có thể kiểm chứng từ HTTP tests bằng MockMvc, WebTestClient hoặc REST Assured. Các test sinh snippet request, response, payload, parameter và header, sau đó biên soạn Asciidoctor/Markdown và đưa vào build/CI. Bài thuộc chương **Thực hành tổng hợp**, kết hợp multipart request, part metadata, validation và tài liệu hóa contract upload.

Sau bài học, bạn sẽ tạo multipart request gồm file và JSON metadata, document tên/mô tả/trạng thái bắt buộc của từng part, mô tả field bên trong JSON part, kiểm tra part headers/payload và ghép snippet vào Asciidoctor.

## 2. Thiết kế API upload

Endpoint:

```http
POST /api/documents
Content-Type: multipart/form-data
```

| Part | Content type | Bắt buộc | Ý nghĩa |
| --- | --- | --- | --- |
| file | application/pdf | Có | File PDF cần lưu |
| metadata | application/json | Có | Metadata của tài liệu |

Metadata:

```json
{
  "title": "Hợp đồng dịch vụ",
  "category": "LEGAL",
  "tags": ["signed", "customer"]
}
```

Response thành công:

```http
HTTP/1.1 201 Created
Location: /api/documents/doc-1001
Content-Type: application/json

{
  "id": "doc-1001",
  "title": "Hợp đồng dịch vụ",
  "fileName": "contract.pdf",
  "contentType": "application/pdf",
  "size": 24576
}
```

Ví dụ sử dụng tên file và dữ liệu giả. Không dùng tài liệu khách hàng thật hoặc nội dung nhạy cảm trong test documentation.

## 3. Controller nhận request parts

Metadata DTO:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.List;

public record DocumentMetadata(
        @NotBlank @Size(max = 120) String title,
        @NotBlank String category,
        @NotEmpty List<@NotBlank String> tags
) {}
```

Response DTO:

```java
public record DocumentResponse(
        String id,
        String title,
        String fileName,
        String contentType,
        long size
) {}
```

Controller:

```java
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import java.net.URI;

@RestController
class DocumentController {

    @PostMapping(
            path = "/api/documents",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<DocumentResponse> upload(
            @RequestPart("file") MultipartFile file,
            @Valid @RequestPart("metadata") DocumentMetadata metadata) {

        DocumentResponse result = new DocumentResponse(
                "doc-1001", metadata.title(), file.getOriginalFilename(),
                file.getContentType(), file.getSize());
        return ResponseEntity.created(
                URI.create("/api/documents/" + result.id())).body(result);
    }
}
```

Đây là controller minh họa contract. Ứng dụng thực tế cần kiểm tra giới hạn kích thước, content type, file signature, tên file và lưu trữ an toàn. REST Docs ghi lại behavior mà test xác nhận, không tự thực hiện các kiểm tra bảo mật đó.

## 4. Chuẩn bị MockMvc test

Với Spring MVC, tạo MockMultipartFile cho từng part. File part mang bytes của file; metadata part mang JSON bytes và content type application/json.

```java
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

Thiết lập MockMvc:

```java
@ExtendWith(RestDocumentationExtension.class)
class DocumentUploadDocumentationTests {
    @Autowired WebApplicationContext context;
    MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

Tạo parts:

```java
MockMultipartFile filePart = new MockMultipartFile(
        "file", "contract.pdf", MediaType.APPLICATION_PDF_VALUE,
        "fake-pdf-content".getBytes(StandardCharsets.UTF_8));

MockMultipartFile metadataPart = new MockMultipartFile(
        "metadata", "", MediaType.APPLICATION_JSON_VALUE,
        """
        {
          "title": "Hợp đồng dịch vụ",
          "category": "LEGAL",
          "tags": ["signed", "customer"]
        }
        """.getBytes(StandardCharsets.UTF_8));
```

Trong ví dụ, file bytes là dữ liệu giả để không cần commit PDF thật. Nếu endpoint kiểm tra PDF signature, fixture phải là PDF test hợp lệ nhưng không chứa dữ liệu nhạy cảm.

## 5. Document request parts

requestParts(...) mô tả các part của multipart request:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

mockMvc.perform(multipart("/api/documents")
        .file(filePart)
        .file(metadataPart))
    .andExpect(status().isCreated())
    .andDo(document("documents/upload",
        requestParts(
            partWithName("file").description("File PDF cần tải lên"),
            partWithName("metadata").description("Metadata JSON của tài liệu")
        )
    ));
```

Snippet request-parts.adoc liệt kê các part được document. Part bắt buộc là mặc định; part optional cần đánh dấu:

```java
requestParts(
    partWithName("file").description("File PDF cần tải lên"),
    partWithName("metadata").description("Metadata JSON của tài liệu"),
    partWithName("thumbnail").optional()
            .description("Ảnh xem trước, không bắt buộc")
)
```

Danh sách descriptor phải khớp contract. Part có trong request nhưng chưa document có thể làm test thất bại; descriptor cho part không có trong request cũng có thể làm test thất bại. Cơ chế này giúp phát hiện tài liệu và request lệch nhau.

## 6. Document field bên trong JSON part

requestParts(...) mô tả sự hiện diện và ý nghĩa của part. Để mô tả cấu trúc JSON trong part metadata, dùng requestPartFields(...):

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

requestPartFields(
    "metadata",
    fieldWithPath("title").description("Tiêu đề hiển thị của tài liệu"),
    fieldWithPath("category").description("Nhóm tài liệu"),
    fieldWithPath("tags").description("Danh sách nhãn"),
    fieldWithPath("tags[]").description("Một nhãn của tài liệu")
)
```

Trong test đầy đủ:

```java
mockMvc.perform(multipart("/api/documents")
        .file(filePart)
        .file(metadataPart))
    .andExpect(status().isCreated())
    .andDo(document("documents/upload",
        requestParts(
            partWithName("file").description("File PDF cần tải lên"),
            partWithName("metadata").description("Metadata JSON của tài liệu")
        ),
        requestPartFields(
            "metadata",
            fieldWithPath("title").description("Tiêu đề hiển thị"),
            fieldWithPath("category").description("Nhóm tài liệu"),
            fieldWithPath("tags").description("Danh sách nhãn"),
            fieldWithPath("tags[]").description("Một nhãn")
        )
    ));
```

Spring REST Docs kiểm tra descriptors với JSON payload của part. Nếu thêm field retentionDays nhưng không cập nhật descriptor, test có thể báo undocumented field. Nếu descriptor mô tả field không có trong payload, test cũng có thể thất bại.

### 6.1. Field lồng nhau

Metadata có thể chứa:

```json
{
  "title": "Hợp đồng dịch vụ",
  "owner": {
    "department": "LEGAL",
    "reference": "CASE-42"
  }
}
```

Document:

```java
requestPartFields(
    "metadata",
    fieldWithPath("title").description("Tiêu đề"),
    fieldWithPath("owner").description("Thông tin đơn vị sở hữu"),
    fieldWithPath("owner.department").description("Phòng ban"),
    fieldWithPath("owner.reference").description("Mã tham chiếu")
)
```

relaxedRequestPartFields(...) cho phép field chưa mô tả không làm test thất bại. Chỉ dùng relaxed descriptor khi chủ đích document một phần contract; với contract cần kiểm soát chặt, ưu tiên requestPartFields(...) đầy đủ.

## 7. Document part headers và nội dung file

Một part có thể có Content-Disposition và Content-Type riêng. Dùng requestPartHeaders(...):

```java
import static org.springframework.restdocs.request.RequestDocumentation.requestPartHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;

requestPartHeaders(
    "file",
    headerWithName("Content-Disposition")
        .description("Tên part và tên file được gửi"),
    headerWithName("Content-Type")
        .description("Media type của file")
)
```

Không phải mọi client hoặc multipart encoder đều tạo part headers giống nhau. Hãy kiểm tra snippet thực tế để biết header nào được ghi nhận. Document các header có ý nghĩa với contract.

### 7.1. Document request part body

Nếu part là JSON, có thể tạo snippet body riêng:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

requestPartBody("metadata")
```

Snippet này hữu ích khi muốn hiển thị nguyên JSON metadata bên cạnh bảng field descriptors. Không dùng requestPartBody cho file nhị phân lớn hoặc dữ liệu không phù hợp để in vào tài liệu; file part thường chỉ cần document tên, media type và ý nghĩa.

## 8. Document response và Location

Response thành công nên document status, header Location và payload:

```java
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

responseHeaders(
    headerWithName("Location").description("URI của tài liệu vừa tạo"),
    headerWithName("Content-Type").description("Media type của response")
);

responseFields(
    fieldWithPath("id").description("Mã tài liệu"),
    fieldWithPath("title").description("Tiêu đề"),
    fieldWithPath("fileName").description("Tên file"),
    fieldWithPath("contentType").description("Media type của file"),
    fieldWithPath("size").description("Kích thước file tính bằng byte")
)
```

Gộp requestParts, requestPartFields, requestPartHeaders, requestPartBody và response descriptors vào lời gọi document(...) của operation để tạo bộ snippet hoàn chỉnh.

## 9. Test lỗi multipart

Tài liệu API cần thể hiện các lỗi đầu vào phổ biến:

| Tình huống | Status ví dụ | Ý nghĩa |
| --- | --- | --- |
| Thiếu part file | 400 Bad Request | Request thiếu thành phần bắt buộc |
| Thiếu part metadata | 400 Bad Request | Metadata bắt buộc |
| Metadata JSON sai cú pháp | 400 Bad Request | Không deserialize được part |
| File media type không hỗ trợ | 415 Unsupported Media Type | Sai loại nội dung |
| File vượt giới hạn | 413 Payload Too Large | Kích thước vượt policy |
| Metadata không hợp lệ | 400 Bad Request | Validation thất bại |

Ví dụ document validation error:

```java
mockMvc.perform(multipart("/api/documents")
        .file(filePart)
        .file(new MockMultipartFile(
                "metadata", "", MediaType.APPLICATION_JSON_VALUE,
                """
                {"title":"","category":"LEGAL","tags":[]}
                """.getBytes(StandardCharsets.UTF_8))))
    .andExpect(status().isBadRequest())
    .andDo(document("documents/upload-invalid-metadata"));
```

Status và error body phụ thuộc exception handler của ứng dụng. Document response thực tế, không copy status ví dụ nếu controller/advice đang trả status khác.

## 10. Ví dụ REST Assured

REST Assured tạo multipart request bằng multiPart(...):

```java
given()
        .multiPart("file", new File("src/test/resources/contract.pdf"),
                "application/pdf")
        .multiPart("metadata",
                """
                {"title":"Hợp đồng dịch vụ",
                 "category":"LEGAL",
                 "tags":["signed","customer"]}
                """,
                "application/json")
        .filter(document("documents/upload",
                requestParts(
                    partWithName("file").description("File PDF"),
                    partWithName("metadata").description("Metadata JSON")
                ),
                requestPartFields(
                    "metadata",
                    fieldWithPath("title").description("Tiêu đề"),
                    fieldWithPath("category").description("Nhóm"),
                    fieldWithPath("tags").description("Danh sách nhãn"),
                    fieldWithPath("tags[]").description("Một nhãn")
                )))
        .when()
        .post("/api/documents")
        .then()
        .statusCode(201);
```

Chữ ký overload multiPart(...) có thể khác giữa các phiên bản REST Assured. Chọn overload theo dependency đang dùng và kiểm tra Content-Type của từng part trong request snippet. Dùng file fixture test có nội dung giả.

## 11. Ví dụ WebTestClient

WebTestClient có thể tạo multipart body với MultipartBodyBuilder:

```java
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.core.io.ByteArrayResource;

MultipartBodyBuilder builder = new MultipartBodyBuilder();
builder.part("file", new ByteArrayResource(
        "fake-pdf-content".getBytes(StandardCharsets.UTF_8)) {
    @Override
    public String getFilename() {
        return "contract.pdf";
    }
}).contentType(MediaType.APPLICATION_PDF);

builder.part("metadata", metadata)
        .contentType(MediaType.APPLICATION_JSON);

webTestClient.post()
        .uri("/api/documents")
        .body(BodyInserters.fromMultipartData(builder.build()))
        .exchange()
        .expectStatus().isCreated();
```

Gắn Spring REST Docs WebTestClient documentation filter/configuration vào client và document operation theo tích hợp của dự án. Multipart encoding của WebTestClient có thể khác MockMvc; kiểm tra snippet thực tế để xác nhận tên part, filename và media type.

## 12. Asciidoctor include snippets

Sau khi test chạy, output có thể chứa:

```text
build/generated-snippets/
  documents/upload/
    curl-request.adoc
    http-request.adoc
    http-response.adoc
    request-parts.adoc
    request-part-metadata-fields.adoc
    request-part-file-headers.adoc
    request-part-metadata-body.adoc
    response-headers.adoc
    response-fields.adoc
```

Tên snippet cụ thể phụ thuộc descriptors và template. Kiểm tra output directory thực tế thay vì giả định mọi file trong ví dụ đều được sinh.

Ví dụ Asciidoctor:

```asciidoc
= Document API

== Upload tài liệu

=== Request
include::{snippets}/documents/upload/http-request.adoc[]

=== Request parts
include::{snippets}/documents/upload/request-parts.adoc[]

=== Metadata fields
include::{snippets}/documents/upload/request-part-metadata-fields.adoc[]

=== Response
include::{snippets}/documents/upload/http-response.adoc[]
include::{snippets}/documents/upload/response-fields.adoc[]
```

Attribute snippets phải trỏ tới output root, ví dụ build/generated-snippets. Nếu dùng tên snippet khác do version/template, cập nhật include theo file thực tế.

## 13. Build và CI

Quy trình tổng hợp:

1. Chạy multipart HTTP tests.
2. Xác minh request parts và JSON part descriptors đều pass.
3. Sinh snippet request/response.
4. Render Asciidoctor.
5. Kiểm tra include path và file snippet bắt buộc.
6. Scan output để bảo đảm không có file thật, token hoặc dữ liệu khách hàng.

Ví dụ Gradle:

```bash
./gradlew clean test asciidoctor
```

Ví dụ kiểm tra file:

```bash
test -f build/generated-snippets/documents/upload/request-parts.adoc
test -f build/generated-snippets/documents/upload/http-request.adoc
test -f build/generated-snippets/documents/upload/http-response.adoc
```

Nếu dùng Maven, chạy lifecycle đã cấu hình để test hoàn tất trước Asciidoctor, ví dụ mvn clean verify. Không để tài liệu cũ trong output root làm build xanh khi test multipart không còn sinh snippet.

## 14. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Part không xuất hiện trong snippet | Tên part trong test khác descriptor | Đối chiếu tên file/metadata |
| REST Docs báo undocumented part | Request có part chưa được mô tả | Thêm descriptor hoặc đánh dấu optional đúng contract |
| JSON part không được parse | Sai Content-Type hoặc JSON không hợp lệ | Đặt application/json cho metadata part |
| Không sinh request part fields snippet | Chưa gọi requestPartFields(...) | Thêm descriptors cho JSON part |
| Field mới làm test fail | Payload có field chưa document | Cập nhật contract descriptors |
| File upload không có filename | Multipart resource không cung cấp filename | Đặt filename cho file part |
| Test pass nhưng snippet thiếu part headers | Chưa dùng requestPartHeaders hoặc header không có | Kiểm tra part headers thực tế |
| Asciidoctor include fail | Tên file snippet/identifier sai | Đọc output root và sửa include |
| Multipart request quá lớn | Test fixture hoặc limit không phù hợp | Dùng fixture nhỏ và test limit riêng |

## 15. Bài tập capstone

Xây dựng API POST /api/documents với hai part bắt buộc:

- file: PDF, filename và media type rõ ràng.
- metadata: JSON gồm title, category, tags.

Hoàn thành:

1. Viết controller nhận hai @RequestPart.
2. Tạo MockMvc test với MockMultipartFile cho file và metadata.
3. Dùng requestParts(...) document tên/mô tả các part.
4. Dùng requestPartFields(...) document field metadata.
5. Dùng requestPartHeaders(...) kiểm tra Content-Disposition và Content-Type nếu chúng thuộc contract.
6. Dùng requestPartBody(...) nếu cần hiển thị JSON metadata nguyên bản.
7. Document response 201, Location và response fields.
8. Viết test thiếu part hoặc metadata sai để document error response.
9. Sinh snippet và include trong Asciidoctor.
10. Chạy clean build và kiểm tra CI xác nhận đầy đủ snippets.

**Tiêu chí hoàn thành:** Người tích hợp biết phải gửi những part nào, tên gì, content type nào và cấu trúc metadata ra sao; file và metadata được test cùng một multipart request; response thành công/lỗi được document; snippet được sinh từ test và Asciidoctor include đúng.

## 16. Ghi nhớ

Multipart upload là một HTTP request chứa nhiều part độc lập. Dùng requestParts(...) để mô tả part, requestPartFields(...) để mô tả field của JSON part, requestPartHeaders(...) để mô tả header riêng của part và requestPartBody(...) khi cần hiển thị nội dung part. Tạo test với file fixture giả và metadata JSON UTF-8, xác nhận response/Location, rồi include snippet trong Asciidoctor. Khi contract thay đổi, descriptor phải thay đổi cùng test; CI cần chạy clean test và render để phát hiện part chưa document hoặc snippet bị thiếu.

### Tài liệu tham khảo

- [Spring REST Docs — Documenting Request Parts](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring Framework — Multipart Resolver and Multipart Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
