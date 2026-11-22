# Xác nhận phần payload biến đổi theo operation với Spring REST Docs

## 1. Cùng tên part không có nghĩa cùng schema

Một API multipart có thể dùng cùng tên part **metadata** cho nhiều operation, nhưng JSON bên trong part thay đổi theo mục đích thao tác.

**Tạo tài liệu mới**

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=----CreateBoundary

------CreateBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "title": "Spring REST Docs",
  "category": "TECHNICAL",
  "visibility": "TEAM"
}
------CreateBoundary
Content-Disposition: form-data; name="file"; filename="guide.pdf"
Content-Type: application/pdf

...PDF bytes...
------CreateBoundary--
```

**Cập nhật thông tin tài liệu**

```http
PATCH /api/documents/DOC-42 HTTP/1.1
Content-Type: multipart/form-data; boundary=----UpdateBoundary

------UpdateBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "title": "Spring REST Docs - bản cập nhật",
  "visibility": "PRIVATE"
}
------UpdateBoundary--
```

Cả hai request đều có part tên metadata, nhưng contract khác nhau:

| Nội dung | Tạo tài liệu | Cập nhật thông tin |
| --- | --- | --- |
| HTTP operation | POST /api/documents | PATCH /api/documents/{documentId} |
| title | Bắt buộc | Có thể vắng nếu không đổi |
| category | Bắt buộc | Không được nhận trong operation này |
| visibility | Bắt buộc | Có thể vắng nếu không đổi |
| Part file | Bắt buộc | Không được gửi |

Nếu dùng chung một bảng field mà không phân biệt operation, người tích hợp có thể nghĩ category luôn được phép gửi khi cập nhật hoặc file là bắt buộc ở cả hai request. Tài liệu cần phản ánh đúng contract của từng thao tác.

Spring REST Docs sinh snippet từ kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Module **SPRING_REST_DOCS** tạo REST API documentation có thể kiểm chứng, biên soạn snippet thành Asciidoctor/Markdown và đưa vào build/CI. Bài thuộc chương **Part payload**, tập trung xác nhận phần payload của một part thay đổi theo operation, đặt tên snippet riêng và chọn descriptor phù hợp.

Sau bài học, bạn có thể:

1. Nhận biết khi nào cùng tên part có schema khác nhau theo operation.
2. Tạo descriptor **requestPartFields(...)** riêng cho mỗi operation.
3. Dùng **optional()** và **ignored()** đúng với contract của từng request.
4. Chọn **relaxedRequestPartFields(...)** khi chủ động chỉ document một phần payload.
5. Dùng document identifier riêng và tổ chức snippet để người đọc không nhầm lẫn.

## 2. Xác định contract theo operation

Một operation là cách sử dụng API cụ thể, thường được nhận diện bởi HTTP method, URI và mục đích. Hai operation có cùng part name không có nghĩa chúng dùng cùng schema.

Trước khi viết test, lập bảng contract:

| Thuộc tính | createDocument | updateDocumentDetails |
| --- | --- | --- |
| Method/path | POST /api/documents | PATCH /api/documents/{documentId} |
| Part metadata | Bắt buộc | Bắt buộc |
| title | Bắt buộc | Optional |
| category | Bắt buộc | Không nhận trong request này |
| visibility | Bắt buộc | Optional |
| Part file | Bắt buộc | Không nhận |
| Mục tiêu | Khởi tạo tài liệu | Thay đổi thuộc tính |

Bảng này là cơ sở để chọn descriptor và assertion. Nó cũng giúp quyết định hai operation có nên dùng cùng một DTO hay cần request model riêng.

### 2.1. Phân biệt optional với không được hỗ trợ

- **Optional:** client được phép gửi hoặc bỏ qua field theo contract. Nếu gửi, server xử lý field đó.
- **Không được hỗ trợ trong operation:** field không thuộc request contract của operation, dù operation khác có thể dùng cùng tên field.

Ví dụ category bắt buộc khi tạo tài liệu nhưng không được phép thay đổi trong operation cập nhật. Không nên đánh dấu category optional trong descriptor cập nhật chỉ vì nó vắng mặt ở ví dụ. Nếu client gửi category, server cần xác định rõ sẽ từ chối hay bỏ qua. Hành vi đó phải được test và mô tả.

### 2.2. Cùng tên part, schema có thể khác

Một API có thể dùng part metadata theo các schema:

- Tạo tài liệu: title, category, visibility.
- Cập nhật metadata: title, visibility.
- Nhập hàng: source, version, items.

Không hợp nhất các field này thành một schema lớn nếu client không thể gửi tất cả chúng trong một operation. Tài liệu tổng hợp có thể làm tài liệu tham khảo, nhưng mỗi operation vẫn cần mô tả request cụ thể.

## 3. Descriptor riêng cho từng operation

Spring REST Docs cho phép gọi requestPartFields(partName, ...) trong từng lời gọi document(...). Tạo document identifier cho mỗi operation:

```java
document("document-create",
    requestPartFields("metadata",
        fieldWithPath("title").description("Tiêu đề tài liệu"),
        fieldWithPath("category").description("Danh mục tài liệu"),
        fieldWithPath("visibility").description("Phạm vi hiển thị")
    )
)
```

Với operation cập nhật:

```java
document("document-update-details",
    requestPartFields("metadata",
        fieldWithPath("title").description("Tiêu đề mới").optional(),
        fieldWithPath("visibility").description("Phạm vi hiển thị mới").optional()
    )
)
```

Mỗi snippet được sinh từ request tương ứng. Descriptor của operation tạo không ảnh hưởng descriptor của operation cập nhật, dù cả hai đều dùng tên part metadata.

### 3.1. Vì sao document identifier phải riêng?

Identifier xác định thư mục chứa snippet. Nếu hai test cùng ghi vào một identifier và sinh cùng tên snippet, chúng có thể gây nhầm lẫn hoặc ghi đè output. Nên đặt tên mô tả method/path hoặc ý định:

| Operation | Document identifier gợi ý |
| --- | --- |
| Tạo tài liệu | document-create |
| Cập nhật metadata | document-update-details |
| Thay file tài liệu | document-replace-file |
| Nhập lô dữ liệu | document-import-batch |

Tên identifier nên ổn định để Asciidoctor include dễ hiểu.

### 3.2. Document cả part lẫn payload fields

Nếu request tạo có nhiều part, mô tả part và schema của metadata:

```java
document("document-create",
    requestParts(
        partWithName("metadata").description("Metadata tài liệu dạng JSON"),
        partWithName("file").description("File PDF cần tải lên")
    ),
    requestPartFields("metadata",
        fieldWithPath("title").description("Tiêu đề tài liệu"),
        fieldWithPath("category").description("Danh mục tài liệu"),
        fieldWithPath("visibility").description("Phạm vi hiển thị")
    )
)
```

Operation cập nhật chỉ nhận metadata:

```java
document("document-update-details",
    requestParts(
        partWithName("metadata").description("Các thuộc tính cần cập nhật")
    ),
    requestPartFields("metadata",
        fieldWithPath("title").description("Tiêu đề mới; bỏ qua nếu không đổi").optional(),
        fieldWithPath("visibility").description("Phạm vi hiển thị mới; bỏ qua nếu không đổi").optional()
    )
)
```

Danh sách part và schema payload phải phản ánh đúng request thực tế của operation đó.

## 4. Dùng optional() đúng ngữ nghĩa

Descriptor optional() cho biết field có thể vắng mặt trong payload đang document. Nó không tự biến field thành không được hỗ trợ, cũng không tự quyết định default value hoặc validation nghiệp vụ.

Ví dụ update metadata:

```json
{
  "visibility": "PRIVATE"
}
```

Descriptor:

```java
requestPartFields("metadata",
    fieldWithPath("title")
        .description("Tiêu đề mới; bỏ qua nếu không thay đổi")
        .optional(),
    fieldWithPath("visibility")
        .description("Phạm vi hiển thị mới; bỏ qua nếu không thay đổi")
        .optional()
)
```

Trong operation cập nhật partial, hai field có thể vắng. Cần định nghĩa riêng:

- Field vắng mặt: giữ nguyên giá trị hiện tại.
- Field có giá trị: cập nhật sang giá trị mới.
- Field có giá trị null: tùy contract, có thể xóa giá trị, bị từ chối hoặc được xem như không thay đổi.
- Payload không có field nào: có thể bị từ chối vì không có thay đổi.

optional() chỉ mô tả khả năng field vắng trong snippet. Hãy viết assertion và validation để chứng minh quy tắc trên.

## 5. Dùng ignored() khi field xuất hiện nhưng không công bố

ignored() phù hợp khi test request có một field đã biết nhưng tài liệu công khai không cần liệt kê. Ví dụ hệ thống nhận internalTrace để phục vụ tích hợp nội bộ:

```java
requestPartFields("metadata",
    fieldWithPath("title").description("Tiêu đề tài liệu"),
    fieldWithPath("visibility").description("Phạm vi hiển thị"),
    fieldWithPath("internalTrace").ignored()
)
```

Không dùng ignored() chỉ để né việc cập nhật schema. Nếu category không được phép trong operation cập nhật, hãy kiểm thử hành vi khi client gửi category và quyết định contract: từ chối với lỗi phù hợp hay chấp nhận như field nội bộ. Đừng âm thầm ẩn một thuộc tính mà client cần biết.

ignored() cũng không thay thế authorization hoặc bảo vệ dữ liệu. Nó chỉ điều khiển việc field có được đưa vào snippet hay không.

## 6. Khi nào dùng relaxedRequestPartFields()?

Chế độ strict của requestPartFields(...) kiểm tra rằng các field trong payload đã được mô tả và descriptor bắt buộc xuất hiện. Trong một số bài test, ta chỉ muốn document một phần payload, còn những field khác nằm ngoài phạm vi trang tài liệu.

Khi ấy, có thể dùng relaxedRequestPartFields(...):

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedRequestPartFields;

document("document-update-summary",
    relaxedRequestPartFields("metadata",
        fieldWithPath("title").description("Tiêu đề mới")
    )
)
```

Request có thể chứa field khác ngoài title; chế độ relaxed không bắt buộc mọi field xuất hiện trong payload đều phải có descriptor. Descriptor đã khai báo vẫn phải khớp nội dung theo các quy tắc của descriptor, trừ khi được đánh dấu optional.

### 6.1. Strict và relaxed

| Tiêu chí | requestPartFields(...) | relaxedRequestPartFields(...) |
| --- | --- | --- |
| Field có trong payload nhưng không được mô tả | Phát hiện lỗi | Cho phép |
| Descriptor bắt buộc nhưng field vắng mặt | Phát hiện lỗi | Vẫn phát hiện, trừ khi optional |
| Mục đích | Xác nhận schema đầy đủ | Chỉ document một phần payload |
| Nơi phù hợp | Contract chính thức của operation | Tài liệu tổng quan hoặc ví dụ rút gọn |

Không nên dùng relaxed cho tất cả operation chỉ để test dễ chạy. Với tài liệu API công khai, strict giúp phát hiện field mới được thêm mà chưa được xem xét.

### 6.2. Relaxed không mô hình hóa schema động

Nếu payload thay đổi theo discriminator, ví dụ kind=PERSON hoặc kind=COMPANY, hai payload có thể có schema khác nhau. Hãy document từng biến thể hoặc operation tương ứng rõ ràng. relaxedRequestPartFields(...) chỉ nới kiểm tra field chưa mô tả; nó không tự mô hình hóa biến thể, điều kiện phụ thuộc hoặc validation.

## 7. Ví dụ hoàn chỉnh: tạo và cập nhật tài liệu

### 7.1. Controller minh họa

Hai operation dùng cùng part metadata nhưng request model riêng:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

record CreateDocumentMetadata(String title, String category, String visibility) {}
record UpdateDocumentMetadata(String title, String visibility) {}
record DocumentReceipt(String id, String title, String visibility) {}

@RestController
class DocumentController {

    @PostMapping(path = "/api/documents", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    DocumentReceipt create(
            @RequestPart("metadata") CreateDocumentMetadata metadata,
            @RequestPart("file") MultipartFile file) {
        return new DocumentReceipt("DOC-42", metadata.title(), metadata.visibility());
    }

    @PatchMapping(path = "/api/documents/{documentId}", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    DocumentReceipt update(
            @PathVariable String documentId,
            @RequestPart("metadata") UpdateDocumentMetadata metadata) {
        return new DocumentReceipt(documentId, metadata.title(), metadata.visibility());
    }
}
```

Đây là ví dụ về hai model request khác nhau dù tên part giống nhau. Hệ thống thực tế cần xử lý field optional theo quy tắc cập nhật và validate payload rỗng/null.

### 7.2. Test document operation tạo

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
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class DocumentOperationsDocumentationTest {
    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new DocumentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsCreateOperationPayload() throws Exception {
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata", "", MediaType.APPLICATION_JSON_VALUE,
                """
                {"title":"Spring REST Docs","category":"TECHNICAL","visibility":"TEAM"}
                """.getBytes(StandardCharsets.UTF_8));
        MockMultipartFile file = new MockMultipartFile(
                "file", "guide.pdf", MediaType.APPLICATION_PDF_VALUE,
                "%PDF-demo".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/documents").file(metadata).file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("DOC-42"))
                .andDo(document("document-create",
                        requestParts(
                                partWithName("metadata").description("Metadata tạo tài liệu"),
                                partWithName("file").description("File PDF của tài liệu")
                        ),
                        requestPartFields("metadata",
                                fieldWithPath("title").description("Tiêu đề mới"),
                                fieldWithPath("category").description("Danh mục tài liệu"),
                                fieldWithPath("visibility").description("Phạm vi hiển thị")
                        )));
    }
}
```

### 7.3. Test document operation cập nhật

```java
@Test
void documentsUpdateOperationPayload() throws Exception {
    MockMultipartFile metadata = new MockMultipartFile(
            "metadata", "", MediaType.APPLICATION_JSON_VALUE,
            """
            {"visibility":"PRIVATE"}
            """.getBytes(StandardCharsets.UTF_8));

    mockMvc.perform(multipart("/api/documents/{documentId}", "DOC-42")
                    .file(metadata)
                    .with(request -> {
                        request.setMethod("PATCH");
                        return request;
                    }))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("DOC-42"))
            .andExpect(jsonPath("$.visibility").value("PRIVATE"))
            .andDo(document("document-update-details",
                    requestParts(
                            partWithName("metadata")
                                    .description("Các thuộc tính cần cập nhật")
                    ),
                    requestPartFields("metadata",
                            fieldWithPath("title")
                                    .description("Tiêu đề mới; bỏ qua nếu không đổi")
                                    .optional(),
                            fieldWithPath("visibility")
                                    .description("Phạm vi hiển thị mới; bỏ qua nếu không đổi")
                                    .optional()
                    )));
}
```

Hai test dùng cùng part name nhưng document identifier và descriptor khác nhau. Test tạo yêu cầu title, category, visibility; test cập nhật chỉ mô tả title và visibility, đều optional theo ví dụ. Trong dự án thực, thêm assertion nghiệp vụ để xác nhận field vắng mặt được xử lý như giữ nguyên giá trị hiện tại.

MockMvc multipart(...) mặc định tạo request POST; khi test endpoint PATCH, ví dụ dùng request post-processor để đổi method. Nếu dự án dùng cấu hình multipart hoặc resolver riêng, bảo đảm test chạy qua đúng cấu hình ứng dụng.

## 8. Payload khác nhau theo discriminator

Một số API dùng cùng operation nhưng payload có biến thể dựa trên field kind. Ví dụ part metadata có thể là:

```json
{
  "kind": "PERSON",
  "person": {
    "fullName": "Nguyen An",
    "dateOfBirth": "1990-01-10"
  }
}
```

Hoặc:

```json
{
  "kind": "COMPANY",
  "company": {
    "legalName": "Example Company",
    "taxCode": "TAX-100"
  }
}
```

Không nên chỉ khai báo tất cả field person và company là optional rồi để người đọc tự suy luận quan hệ giữa chúng. Document biến thể riêng:

| Biến thể | Field yêu cầu | Field không được dùng |
| --- | --- | --- |
| kind=PERSON | person.fullName, person.dateOfBirth | company.* |
| kind=COMPANY | company.legalName, company.taxCode | person.* |

Có thể tạo hai test và hai document identifier, chẳng hạn customer-import-person và customer-import-company. Mỗi test dùng strict requestPartFields(...) với đúng schema biến thể. Trong mô tả operation, giải thích discriminator và điều kiện chọn payload.

Nếu contract thật sự cho phép superset schema với nhiều field optional, có thể document schema chung. Nhưng phải ghi rõ field nào phụ thuộc kind và trường hợp field thuộc biến thể khác bị từ chối ra sao.

## 9. Tổ chức snippet cho nhiều operation

Giả sử test sinh snippet vào build/generated-snippets. Cấu trúc thư mục có thể như sau:

```text
build/generated-snippets/
  document-create/
    request-parts.adoc
    request-part-metadata-fields.adoc
    http-request.adoc
    http-response.adoc
  document-update-details/
    request-parts.adoc
    request-part-metadata-fields.adoc
    http-request.adoc
    http-response.adoc
```

Mỗi operation có thư mục riêng nên có thể giữ tên snippet chung bên trong thư mục mà không gây nhầm lẫn. Tránh cho nhiều operation ghi vào cùng identifier nếu chúng có schema hoặc request khác nhau.

Trong Asciidoctor, tổ chức thành các mục riêng:

```asciidoc
= Document API

== Tạo tài liệu

include::{snippets}/document-create/request-parts.adoc[]
include::{snippets}/document-create/request-part-metadata-fields.adoc[]
include::{snippets}/document-create/http-request.adoc[]

== Cập nhật metadata tài liệu

include::{snippets}/document-update-details/request-parts.adoc[]
include::{snippets}/document-update-details/request-part-metadata-fields.adoc[]
include::{snippets}/document-update-details/http-request.adoc[]
```

Người đọc thấy rõ cùng tên part nhưng hai contract được trình bày trong section operation riêng. Biến {snippets} cần được cấu hình trỏ tới output directory. Với Markdown, dùng TemplateFormats.markdown() và bước ghép snippet phù hợp; Markdown cơ bản không có cú pháp include chuẩn như Asciidoctor.

## 10. Kiểm thử contract thay đổi theo operation

Mỗi operation nên có test thể hiện payload hợp lệ và các điều kiện quan trọng:

| Kiểm tra | Operation tạo | Operation cập nhật |
| --- | --- | --- |
| Thiếu part metadata | Bị từ chối nếu bắt buộc | Bị từ chối nếu endpoint yêu cầu part |
| Thiếu title | Bị từ chối | Có thể chấp nhận và giữ title cũ |
| Thiếu category | Bị từ chối | Không nhận field này; xác định hành vi nếu client gửi |
| Có file | Bắt buộc | Không nằm trong contract |
| Có field ngoài schema | Strict descriptor phát hiện khi document | Strict descriptor phát hiện khi document |
| Payload rỗng | Bị từ chối nếu metadata cần field | Cần định nghĩa rõ có cho phép no-op không |

Các test âm tính không nhất thiết dùng cùng document(...) với test sinh snippet thành công. Có thể viết test validation riêng để xác nhận HTTP status và error body, đồng thời document error response theo mục tiêu tài liệu.

### 10.1. Không dùng một fixture cho mọi operation

Fixture dùng chung dễ khiến test cập nhật vô tình gửi category hoặc file dù endpoint cập nhật không nhận các field ấy. Tạo fixture theo mục tiêu, ví dụ:

- create-document-metadata.json
- update-document-metadata.json
- person-import-metadata.json
- company-import-metadata.json

Điều quan trọng là mỗi fixture biểu diễn một request contract rõ ràng và được dùng trong test tương ứng.

### 10.2. Kiểm tra giá trị, không chỉ cấu trúc

requestPartFields(...) xác nhận field được mô tả phù hợp với payload được kiểm thử. Nó không xác minh toàn bộ quy tắc nghiệp vụ. Hãy bổ sung assertion để xác nhận:

- visibility chỉ nhận các giá trị hợp lệ.
- Field vắng mặt trong PATCH không ghi đè dữ liệu hiện có.
- category không thể thay đổi nếu operation không hỗ trợ.
- kind nhất quán với object person hoặc company.
- File chỉ xuất hiện trong operation cho phép upload.

## 11. WebTestClient và REST Assured

Descriptor payload không phụ thuộc test client. Test client tạo multipart request; Spring REST Docs nhận request đã thực hiện và sinh snippet theo operation identifier.

### 11.1. WebTestClient

Có thể tạo multipart body riêng cho operation tạo:

```java
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.web.reactive.function.BodyInserters;

MultipartBodyBuilder createParts = new MultipartBodyBuilder();
createParts.part("metadata", """
        {"title":"Spring REST Docs","category":"TECHNICAL","visibility":"TEAM"}
        """)
        .contentType(MediaType.APPLICATION_JSON);
createParts.part("file", new ByteArrayResource("%PDF-demo".getBytes()) {
    @Override
    public String getFilename() {
        return "guide.pdf";
    }
}).contentType(MediaType.APPLICATION_PDF);

webTestClient.post()
        .uri("/api/documents")
        .body(BodyInserters.fromMultipartData(createParts.build()))
        .exchange()
        .expectStatus().isOk();
```

Trong lời gọi document(...) của tích hợp WebTestClient, dùng identifier riêng và descriptor metadata của operation tạo. Tạo body builder khác cho PATCH/update, không tái sử dụng payload tạo tài liệu.

### 11.2. REST Assured

REST Assured cũng nên dùng filter/document identifier riêng cho từng operation:

```java
given()
        .filter(documentationFilter)
        .multiPart("metadata",
                "{\"title\":\"Spring REST Docs\","
                        + "\"category\":\"TECHNICAL\",\"visibility\":\"TEAM\"}",
                "application/json")
        .multiPart("file", new File("guide.pdf"))
        .when()
        .post("/api/documents")
        .then()
        .statusCode(200);
```

documentationFilter cần được cấu hình theo tích hợp REST Assured và descriptor của operation đang kiểm thử. Đoạn trên minh họa việc gửi request; nó không định nghĩa một helper có sẵn. Chỉ gọi multiPart(...) chưa đủ để sinh snippet nếu không gắn filter document phù hợp.

## 12. Lỗi thường gặp và cách khắc phục

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Test tạo và cập nhật dùng chung bảng metadata | Dùng cùng identifier hoặc descriptor dù contract khác | Tách identifier và descriptor theo operation |
| category xuất hiện trong request cập nhật và strict document báo lỗi | Request gửi field không thuộc schema cập nhật | Sửa fixture hoặc xác định rõ operation có hỗ trợ field này không |
| Thiếu title ở update khiến document thất bại | Descriptor không optional dù contract cho phép vắng | Đánh dấu optional cho field thật sự optional |
| Dùng ignored để che category mà không kiểm thử | Nhầm field nội bộ với field không được phép | Xác định hành vi khi field xuất hiện và viết test |
| Dùng relaxedRequestPartFields cho mọi test | Không phát hiện field mới bị thêm mà chưa được công bố | Dùng strict ở contract chính; relaxed chỉ trong tài liệu một phần |
| Hai loại payload discriminator bị gộp vào schema quá rộng | Không mô tả quan hệ giữa discriminator và field | Document từng biến thể hoặc mô tả rõ schema hợp nhất |
| Snippet operation này ghi đè operation khác | Dùng chung identifier và tên snippet | Tạo thư mục identifier riêng |
| Tài liệu có snippet đúng nhưng mô tả sai optional | Chỉ dựa vào một fixture mẫu | Bổ sung test absent/null/present và mô tả semantics |

## 13. Tích hợp Asciidoctor và CI

Quy trình:

1. Lập bảng contract cho từng operation trước khi viết descriptor.
2. Tạo test và fixture riêng cho từng operation hoặc từng biến thể payload.
3. Dùng requestParts(...) để mô tả part; dùng requestPartFields(...) strict cho schema đầy đủ của operation.
4. Chỉ dùng optional() cho field có thể vắng; ignored() cho field đã biết nhưng chủ ý không công bố; relaxedRequestPartFields(...) khi cố ý document một phần payload.
5. Dùng document identifier riêng để snippet không va chạm.
6. Include đúng snippet trong từng section operation của Asciidoctor.
7. Chạy test và render tài liệu trong CI. Khi operation thay đổi schema, test tương ứng buộc descriptor của operation đó được xem xét.

Ví dụ lệnh Gradle sau khi task đã được cấu hình:

```bash
./gradlew test asciidoctor
```

Nếu xuất snippet Markdown, cấu hình TemplateFormats.markdown() và ghép snippet theo công cụ tài liệu của dự án. Markdown không có cơ chế include chuẩn giống Asciidoctor.

## 14. Bài tập thực hành

API quản lý media có hai operation:

**Tạo media**

```http
POST /api/media
Content-Type: multipart/form-data

Part "metadata" (application/json):
{
  "name": "Team photo",
  "mediaType": "IMAGE",
  "visibility": "TEAM"
}

Part "file" (image/png):
...binary image...
```

**Cập nhật thông tin media**

```http
PATCH /api/media/MED-10
Content-Type: multipart/form-data

Part "metadata" (application/json):
{"name":"Engineering team photo"}
```

Hãy thực hiện:

1. Xác định schema metadata riêng cho từng operation.
2. Tạo DTO hoặc request model phù hợp; không mặc định hai operation phải dùng chung một DTO.
3. Viết hai MockMvc test dùng cùng tên part metadata nhưng fixture khác nhau.
4. Document operation tạo với name, mediaType, visibility; document operation cập nhật với name optional theo contract.
5. Dùng document identifier media-create và media-update-details.
6. Thử gửi mediaType trong update; xác định server từ chối hay bỏ qua và document hành vi đúng.
7. Sinh snippet riêng, ghép vào hai section Asciidoctor và chạy build/CI.

**Tiêu chí hoàn thành:** Người tích hợp xác định được payload cần gửi cho từng operation; optional và field không hỗ trợ không bị nhầm lẫn; snippet không ghi đè; kiểm thử chứng minh schema và hành vi thực tế.

## 15. Ghi nhớ

Cùng tên part không đồng nghĩa payload có cùng schema trong mọi operation. Hãy xác định contract theo method/path và mục đích, tạo requestPartFields(...) riêng cho từng document identifier, dùng optional() cho field có thể vắng, ignored() cho field đã biết nhưng chủ ý không công bố, và relaxedRequestPartFields(...) khi chỉ document một phần payload. Với biến thể dựa trên discriminator, hãy mô tả rõ từng schema hoặc quy tắc phụ thuộc. Test và snippet riêng cho mỗi operation giúp tài liệu Spring REST Docs phản ánh chính xác request mà client cần gửi trong build/CI.

### Tài liệu tham khảo

- [Spring REST Docs — Request Part Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-part-payloads.html)
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring REST Docs — Request Parts](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-parts.html)
- [Spring Framework — Multipart Forms and RequestPart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
