# partFields và mô tả cấu trúc part trong Spring REST Docs

## 1. Multipart request có cấu trúc như thế nào?

Nhiều endpoint nhận dữ liệu dạng **multipart/form-data**. Một request có thể mang nhiều phần (part), mỗi phần có tên, header và body riêng. Ví dụ endpoint tải tài liệu lên nhận part `file` chứa file PDF và part `metadata` chứa JSON mô tả tài liệu.

Spring REST Docs có hai mức mô tả cần phân biệt:

- `requestParts(...)` cùng `partWithName(...)` mô tả **cấu trúc các part**: tên part, mục đích và việc part có bắt buộc hay không.
- `requestPartFields(...)` mô tả **các field bên trong payload của một part**, thường dùng cho part JSON.
- `requestPartBody(...)` tạo snippet chứa body của một part để trình bày ví dụ dữ liệu.

Cụm "partFields" trong tên bài nói về nhóm mô tả part và field của part. Trong API Spring REST Docs hiện tại không có method tổng quát tên `partFields(...)`. Cần dùng đúng method theo phạm vi:

| Phạm vi | API đúng | Kết quả |
| --- | --- | --- |
| Danh sách part của multipart request | `requestParts(partWithName(...), ...)` | `request-parts.adoc` |
| Field bên trong JSON part | `requestPartFields("metadata", ...)` | `request-part-metadata-fields.adoc` |
| Body của một part | `requestPartBody("metadata")` | `request-part-metadata-body.adoc` |

Sau bài học, bạn có thể document cấu trúc multipart, mô tả field JSON lồng nhau, chọn strict/relaxed, đánh dấu part hoặc field optional và đưa các snippet vào Asciidoctor/CI.

## 2. Ví dụ hợp đồng: tải tài liệu cùng metadata

Giả sử endpoint `POST /documents` nhận multipart request gồm:

```text
POST /documents
Content-Type: multipart/form-data

Part "file"
  Content-Type: application/pdf
  Filename: handbook.pdf
  Body: bytes của file PDF

Part "metadata"
  Content-Type: application/json
  Body: JSON mô tả tài liệu
```

JSON của part `metadata`:

```json
{
  "title": "Sổ tay nhân viên",
  "description": "Tài liệu hướng dẫn nội bộ",
  "documentType": "HANDBOOK",
  "owner": {
    "team": "People Operations",
    "contactEmail": "people@example.test"
  },
  "tags": [
    "onboarding",
    "policy"
  ]
}
```

Ở đây có hai cấp cấu trúc. Cấp multipart có hai part là file và metadata. Cấp JSON có field title, description, documentType, owner và tags. Bảng part giúp người đọc hiểu endpoint mong đợi phần dữ liệu nào; bảng field giải thích schema bên trong metadata.

## 3. Mô tả cấu trúc part bằng requestParts và partWithName

`requestParts(...)` sinh snippet `request-parts.adoc`. Mỗi `partWithName("...")` mô tả một part mà endpoint hỗ trợ:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("file")
        .description("File PDF cần tải lên"),
    partWithName("metadata")
        .description("Metadata JSON mô tả tài liệu")
)
```

Mô tả part nên trả lời part được dùng để làm gì. Ví dụ "Metadata JSON mô tả tài liệu" hữu ích hơn "Dữ liệu metadata". Bảng này không liệt kê field title, owner hay tags; các field ấy thuộc payload của part JSON và được mô tả ở mục riêng.

### 3.1. Part bắt buộc và part tùy chọn

Mặc định, các part được document phải xuất hiện trong request test. Nếu request gửi một part không được mô tả, strict documentation cũng làm test thất bại. Nếu part thực sự tùy chọn theo contract, dùng `optional()` trên descriptor của part:

```java
requestParts(
    partWithName("file")
        .description("File PDF cần tải lên"),
    partWithName("metadata")
        .description("Thông tin mô tả tài liệu")
        .optional()
)
```

`optional()` ở đây cho phép **toàn bộ part metadata** vắng mặt. Nó khác với `fieldWithPath("description").optional()` trong `requestPartFields`, vốn chỉ cho phép một field bên trong JSON vắng mặt.

### 3.2. Bỏ qua part có chủ đích

Nếu request test có một part kỹ thuật đã biết nhưng không muốn hiển thị trong bảng:

```java
requestParts(
    partWithName("file").description("File tài liệu"),
    partWithName("metadata").description("Metadata JSON"),
    partWithName("internalTrace").ignored()
)
```

`ignored()` ghi nhận rằng part đã được biết và chủ ý loại khỏi snippet. Chỉ dùng khi part đó không thuộc nội dung tài liệu cần công bố; không dùng để che một part mới chưa được review.

### 3.3. Chế độ relaxed cho danh sách part

Nếu chỉ document một tập con part trong một kịch bản, có thể dùng `relaxedRequestParts(...)`:

```java
import static org.springframework.restdocs.request.RequestDocumentation.relaxedRequestParts;

relaxedRequestParts(
    partWithName("file")
        .description("File tài liệu")
)
```

Ở chế độ relaxed, part chưa được mô tả không làm test thất bại. Descriptor đã khai báo vẫn chịu quy tắc presence/optional. Khi cần kiểm chứng toàn bộ contract multipart, ưu tiên `requestParts` strict.

## 4. Mô tả field bên trong JSON part

`requestPartFields` thuộc `PayloadDocumentation`. Nó nhận tên part và các field descriptor:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

requestPartFields(
    "metadata",
    fieldWithPath("title")
        .description("Tiêu đề tài liệu"),
    fieldWithPath("description")
        .description("Mô tả ngắn"),
    fieldWithPath("documentType")
        .description("Loại tài liệu"),
    fieldWithPath("owner.team")
        .description("Nhóm sở hữu tài liệu"),
    fieldWithPath("owner.contactEmail")
        .description("Email liên hệ của nhóm sở hữu"),
    fieldWithPath("tags[]")
        .description("Các nhãn gắn với tài liệu")
)
```

Snippet được sinh có tên `request-part-metadata-fields.adoc`. Path tính từ **gốc JSON của part metadata**, không bao gồm tên part. Do đó, dùng `owner.team`, không dùng `metadata.owner.team`.

### 4.1. Object lồng nhau và subsection trong JSON part

Nếu `owner` là một object có cấu trúc lớn, bảng tổng quan có thể gom cả nhánh:

```java
requestPartFields(
    "metadata",
    fieldWithPath("title")
        .description("Tiêu đề tài liệu"),
    subsectionWithPath("owner")
        .description("Thông tin nhóm sở hữu tài liệu"),
    fieldWithPath("tags[]")
        .description("Các nhãn của tài liệu")
)
```

`subsectionWithPath("owner")` bao phủ các field hậu duệ của owner trong snippet này. Nếu cần bảng chi tiết riêng cho owner, có thể dùng overload nhận subsection extractor:

```java
requestPartFields(
    "metadata",
    beneathPath("owner").withSubsectionId("owner"),
    fieldWithPath("team")
        .description("Nhóm sở hữu"),
    fieldWithPath("contactEmail")
        .description("Email liên hệ")
)
```

Bảng chi tiết dùng path tương đối với nhánh đã trích. Vì đã chọn `owner`, descriptor là `team` và `contactEmail`, không có tiền tố `owner.`.

### 4.2. Mảng trong JSON part

Với payload:

```json
{
  "title": "Sổ tay nhân viên",
  "tags": ["onboarding", "policy"],
  "attachments": [
    {
      "name": "cover",
      "format": "PDF"
    },
    {
      "name": "appendix",
      "format": "PDF"
    }
  ]
}
```

Có thể document các field của mọi phần tử bằng path có `[]`:

```java
requestPartFields(
    "metadata",
    fieldWithPath("title").description("Tiêu đề tài liệu"),
    fieldWithPath("tags[]").description("Các nhãn"),
    fieldWithPath("attachments[].name")
        .description("Tên tệp đính kèm"),
    fieldWithPath("attachments[].format")
        .description("Định dạng tệp")
)
```

Path vẫn tính từ root JSON của part. Nếu danh sách rỗng, không có phần tử để đối chiếu những field bên trong mảng; nên dùng fixture có phần tử để sinh bảng schema và test riêng cho trường hợp danh sách rỗng.

## 5. Sinh body snippet của một part

`requestPartBody("metadata")` tạo snippet `request-part-metadata-body.adoc` chứa body của part. Nó hữu ích khi tài liệu cần ví dụ JSON nguyên vẹn:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

requestPartBody("metadata")
```

Body snippet cho thấy dữ liệu mẫu nhưng không tự kiểm tra tính đầy đủ của field. Nếu mục tiêu là bảo vệ schema, kết hợp body snippet với `requestPartFields` strict. Nếu chỉ cần trình bày cấu trúc dữ liệu, bảng field có thể đủ mà không nhất thiết phải include cả body.

## 6. Ví dụ hoàn chỉnh với MockMvc

Ví dụ dùng JUnit 5, Java 17+, Spring MVC Test và Spring REST Docs. Controller nhận file PDF cùng metadata JSON. Phần xử lý lưu file được giản lược để tập trung vào document multipart.

```java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.multipart;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class DocumentUploadDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new DocumentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void uploadDocument() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "handbook.pdf",
                MediaType.APPLICATION_PDF_VALUE,
                "fake-pdf-content".getBytes()
        );

        String metadataJson = """
                {
                  "title": "Sổ tay nhân viên",
                  "description": "Tài liệu hướng dẫn nội bộ",
                  "documentType": "HANDBOOK",
                  "owner": {
                    "team": "People Operations",
                    "contactEmail": "people@example.test"
                  },
                  "tags": ["onboarding", "policy"]
                }
                """;

        MockMultipartFile metadata = new MockMultipartFile(
                "metadata",
                "",
                MediaType.APPLICATION_JSON_VALUE,
                metadataJson.getBytes()
        );

        this.mockMvc.perform(multipart("/documents")
                        .file(file)
                        .file(metadata)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andDo(document("documents-upload",
                        requestParts(
                                partWithName("file")
                                        .description("File PDF cần tải lên"),
                                partWithName("metadata")
                                        .description("Metadata JSON mô tả tài liệu")
                        ),
                        requestPartBody("metadata"),
                        requestPartFields("metadata",
                                fieldWithPath("title")
                                        .description("Tiêu đề tài liệu"),
                                fieldWithPath("description")
                                        .description("Mô tả ngắn"),
                                fieldWithPath("documentType")
                                        .description("Loại tài liệu"),
                                fieldWithPath("owner.team")
                                        .description("Nhóm sở hữu"),
                                fieldWithPath("owner.contactEmail")
                                        .description("Email liên hệ"),
                                fieldWithPath("tags[]")
                                        .description("Các nhãn của tài liệu")
                        )
                ));
    }

    @RestController
    static class DocumentController {

        @PostMapping(
                value = "/documents",
                consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        ResponseEntity<Map<String, String>> upload(
                @RequestPart("file") MultipartFile file,
                @RequestPart("metadata") Map<String, Object> metadata) {

            if (file.isEmpty()) {
                return ResponseEntity.badRequest().build();
            }
            return ResponseEntity.status(201)
                    .body(Map.of("id", "doc-100"));
        }
    }
}
```

### 6.1. Media type của part JSON

Part metadata được tạo với `MediaType.APPLICATION_JSON_VALUE`. Đây là tín hiệu để Spring MVC chọn message converter phù hợp với tham số `@RequestPart("metadata")`. Nếu media type sai hoặc body JSON không hợp lệ, lỗi có thể xuất hiện ở bước binding trước khi REST Docs chạy field descriptor.

Cần phân biệt lỗi HTTP binding/conversion với lỗi document. REST Docs chỉ có thể kiểm tra field của part sau khi request đã tới bước document.

### 6.2. Multipart builder của MockMvc

Ví dụ dùng import:

```java
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.multipart;
```

Đây là multipart request builder được Spring REST Docs cung cấp cho MockMvc. Dùng builder tích hợp tương ứng để request được xử lý trong ngữ cảnh document của REST Docs.

## 7. Snippet được sinh và cách ghép vào Asciidoctor

Với operation identifier `documents-upload`, các snippet liên quan thường nằm trong `build/generated-snippets/documents-upload/`:

| Tệp | Sinh bởi | Vai trò |
| --- | --- | --- |
| `request-parts.adoc` | `requestParts(...)` | Bảng tên và mô tả các part |
| `request-part-metadata-body.adoc` | `requestPartBody("metadata")` | Body JSON của metadata |
| `request-part-metadata-fields.adoc` | `requestPartFields("metadata", ...)` | Bảng field metadata |
| `http-request.adoc` | Snippet HTTP mặc định | Request multipart đã kiểm thử |
| `http-response.adoc` | Snippet HTTP mặc định | HTTP response của endpoint |

Ví dụ `src/docs/asciidoc/documents.adoc`:

```asciidoc
= Document API
:toc: left

== POST /documents

Tải lên một file tài liệu cùng metadata mô tả.

=== Các part của request

include::{snippets}/documents-upload/request-parts.adoc[]

=== Ví dụ JSON của metadata

include::{snippets}/documents-upload/request-part-metadata-body.adoc[]

=== Cấu trúc field của metadata

include::{snippets}/documents-upload/request-part-metadata-fields.adoc[]

=== HTTP response

include::{snippets}/documents-upload/http-response.adoc[]
```

Văn bản quanh snippet giải thích file part chứa bytes tài liệu còn metadata part chứa JSON. Snippet cung cấp dữ liệu và schema; heading/đoạn văn nói rõ vai trò của chúng.

## 8. Strict, optional, ignored và relaxed

Cần phân biệt strict validation ở cấp danh sách part với strict validation ở cấp field:

| Tình huống | API | Hành vi |
| --- | --- | --- |
| Request có part chưa mô tả | `requestParts(...)` | Strict mode làm test thất bại |
| Descriptor có part bắt buộc nhưng request không gửi | `requestParts(...)` | Test thất bại |
| JSON part có field chưa mô tả | `requestPartFields(...)` | Test thất bại |
| Descriptor field bắt buộc nhưng JSON không có | `requestPartFields(...)` | Test thất bại |
| Field được đánh dấu optional vắng mặt | `requestPartFields(...)` | Được chấp nhận |
| Part được đánh dấu optional vắng mặt | `requestParts(...)` | Được chấp nhận |
| Part chưa mô tả trong relaxed mode | `relaxedRequestParts(...)` | Được bỏ qua |
| Field chưa mô tả trong relaxed mode | `relaxedRequestPartFields(...)` | Được bỏ qua |

`ignored()` khác `optional()`: ignored loại mục đã biết khỏi snippet; optional cho phép mục đó vắng mặt. Relaxed mode chấp nhận mục chưa mô tả xuất hiện. Chọn cơ chế theo contract thay vì dùng chúng chỉ để làm test qua.

### 8.1. Field mới trong JSON part

Nếu metadata được bổ sung field `classification` mà bảng strict chưa khai báo, test có thể thất bại. Nếu field thuộc contract công khai, thêm descriptor và mô tả. Nếu JSON là schema mở và kịch bản chỉ muốn tập trung một vài field, relaxed mode có thể phù hợp, nhưng tài liệu cần nói rõ bảng không bao phủ toàn bộ field.

### 8.2. Part optional và field optional là hai cấp khác nhau

Nếu cả metadata part có thể vắng mặt, đánh dấu part metadata optional trong `requestParts`. Nếu part vẫn bắt buộc nhưng một field như description có thể thiếu, đánh dấu field đó optional trong `requestPartFields`. Nếu part vắng mặt, không có payload để sinh bảng field cho part ấy; dùng test riêng cho biến thể không có metadata.

## 9. Tên part và path phải khớp request thật

Tên part là khóa để REST Docs tìm đúng payload. Các vị trí sau cần thống nhất:

- `MockMultipartFile("metadata", ...)`;
- `@RequestPart("metadata")`;
- `requestParts(partWithName("metadata"))`;
- `requestPartBody("metadata")`;
- `requestPartFields("metadata", ...)`.

Nếu client gửi `details` nhưng test document `metadata`, REST Docs không tự ánh xạ hai tên.

Field path bắt đầu từ root JSON part:

```java
// Không đúng: lặp tên part trong field path.
requestPartFields("metadata",
    fieldWithPath("metadata.title").description("Tiêu đề")
);

// Đúng: metadata đã được chọn ở đối số đầu tiên.
requestPartFields("metadata",
    fieldWithPath("title").description("Tiêu đề")
);
```

Path sai có thể dẫn tới lỗi thiếu field được document hoặc field chưa được document. Hãy đối chiếu JSON thực tế của part trước khi sửa descriptor.

## 10. Dùng với WebTestClient và REST Assured

### 10.1. WebTestClient

Tạo multipart body bằng `BodyInserters.fromMultipartData`. Khi gửi file resource, có thể dùng `ByteArrayResource` và override `getFilename()` để cung cấp filename.

```java
MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
Resource fileResource = new ByteArrayResource("fake-pdf".getBytes()) {
    @Override
    public String getFilename() {
        return "handbook.pdf";
    }
};
parts.add("file", fileResource);
parts.add("metadata", metadataMap);

webTestClient.post()
    .uri("/documents")
    .body(BodyInserters.fromMultipartData(parts))
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("documents-upload",
        requestParts(
            partWithName("file").description("File PDF"),
            partWithName("metadata").description("Metadata JSON")
        ),
        requestPartFields("metadata",
            fieldWithPath("title").description("Tiêu đề"),
            fieldWithPath("documentType").description("Loại tài liệu")
        )
    ));
```

WebTestClient phải được cấu hình Spring REST Docs documentation filter trước khi exchange. Ví dụ tập trung vào cách gửi multipart và đặt các handler; `parts`, `metadataMap` và client được chuẩn bị trong test.

### 10.2. REST Assured

Với REST Assured, dùng `multiPart` để gửi từng part và gắn handler trong filter:

```java
RestAssured.given(this.spec)
    .accept("application/json")
    .filter(document("documents-upload",
        requestParts(
            partWithName("file").description("File PDF"),
            partWithName("metadata").description("Metadata JSON")
        ),
        requestPartFields("metadata",
            fieldWithPath("title").description("Tiêu đề"),
            fieldWithPath("documentType").description("Loại tài liệu")
        )
    ))
    .multiPart("file", new File("handbook.pdf"), "application/pdf")
    .multiPart("metadata", metadataMap)
    .when()
    .post("/documents")
    .then()
    .statusCode(201);
```

Các ví dụ giả định client/filter, server và dependency REST Docs đã được cấu hình. Part metadata phải được serialize đúng media type mà endpoint yêu cầu.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Không tìm thấy part | Tên part giữa client và descriptor không khớp | Đồng bộ tên trong client, controller và document handlers |
| Bảng part thiếu part | Chưa khai báo `partWithName` hoặc đang dùng relaxed mode | Bổ sung descriptor và dùng strict nếu cần kiểm soát đầy đủ |
| Có bảng part nhưng không có field JSON | Chỉ gọi `requestParts` | Thêm `requestPartFields` |
| Có body JSON nhưng không có bảng field | Chỉ gọi `requestPartBody` | Thêm `requestPartFields` |
| Field path không tìm thấy | Path lặp tên part hoặc không khớp JSON | Dùng path từ root JSON part |
| JSON không chuyển đổi được | Media type hoặc body part sai | Dùng `application/json` và xác minh JSON |
| File part bị xử lý như JSON | Media type/binding sai | Dùng media type file thích hợp; không document file bytes như JSON fields |
| Field mới không bị phát hiện | Dùng relaxed mode hoặc subsection bao phủ nhánh | Dùng strict và descriptor chi tiết khi cần |
| Asciidoctor thiếu snippet | Sai operation ID, tên part hoặc output directory | Kiểm tra tên file được sinh và đường dẫn include |

## 12. Tích hợp build và CI

Với Gradle Groovy DSL, giả định dự án đã cấu hình Spring REST Docs, test và plugin Asciidoctor:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir
}
```

Chạy:

```bash
./gradlew clean test asciidoctor
```

Trong CI, xác nhận:

1. Test multipart chạy tới handler `document(...)`.
2. Tên part trong request khớp đối số của `requestParts`, `requestPartBody` và `requestPartFields`.
3. Part JSON có media type phù hợp và payload hợp lệ.
4. Bảng strict phát hiện part/field mới hoặc mục bắt buộc bị thiếu.
5. Asciidoctor đọc đúng thư mục snippet vừa sinh.
6. Các snippet được include đúng operation identifier và tên part.

Với Maven, thư mục snippet thường là `target/generated-snippets`; bước dựng tài liệu cần chạy sau test sinh snippet.

## 13. Bài thực hành

Tạo test `DocumentUploadDocumentationTest` và thực hiện:

1. Gửi multipart với part `file` và `metadata`, đặt filename và media type phù hợp.
2. Dùng `requestParts` để mô tả mục đích và tính bắt buộc của từng part.
3. Dùng `requestPartBody("metadata")` để sinh JSON snippet.
4. Dùng `requestPartFields("metadata", ...)` để document title, description, owner và tags.
5. Thêm field `metadata.classification` mà chưa khai báo descriptor; quan sát strict test thất bại.
6. Đánh dấu field description optional nếu contract cho phép, rồi kiểm tra trường hợp field vắng mặt.
7. Đánh dấu metadata part optional nếu endpoint cho phép thiếu cả part; viết test riêng cho biến thể không có part.
8. Chuyển `requestParts` sang `relaxedRequestParts` rồi thêm một part chưa mô tả; so sánh strict/relaxed.
9. Include `request-parts.adoc`, `request-part-metadata-body.adoc` và `request-part-metadata-fields.adoc` vào Asciidoctor.
10. Chạy `./gradlew clean test asciidoctor` trong dự án đã cấu hình.

**Tiêu chí hoàn thành:** phân biệt được cấu trúc multipart cấp part với schema JSON bên trong một part, dùng đúng `requestParts`/`requestPartFields`/`requestPartBody`, đặt tên/path chính xác và giải thích strict, optional, ignored, relaxed theo contract.

## 14. Câu hỏi tự kiểm tra

**1. API nào mô tả danh sách part của multipart request?**

`requestParts(partWithName(...), ...)`. Nó sinh bảng tên và mô tả các part.

**2. API nào document field trong JSON part?**

`requestPartFields("metadata", ...)`. Field path tính từ gốc JSON của part.

**3. `partFields(...)` có phải method Spring REST Docs không?**

Không phải tên method tổng quát trong API. Dùng `requestParts` cho danh sách part và `requestPartFields` cho field bên trong một part.

**4. Snippet bảng part và bảng field metadata có tên gì?**

Bảng part là `request-parts.adoc`; bảng field metadata là `request-part-metadata-fields.adoc`.

**5. Khi nào dùng relaxedRequestParts và relaxedRequestPartFields?**

Khi tài liệu chỉ tập trung một tập con part hoặc field và chấp nhận mục khác xuất hiện mà không được mô tả. Với contract cần kiểm soát đầy đủ, ưu tiên strict mode.

**6. Có dùng requestPartFields để document bytes của file không?**

Không. `requestPartFields` mô tả field của payload có cấu trúc, thường là JSON. File part được mô tả ở cấp part; không biến nội dung nhị phân thành bảng field JSON.

## Tài liệu tham khảo

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): request parts, part body, part fields, strict/relaxed và tên snippet.
- [RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html): `requestParts`, `partWithName` và descriptor của part.
- [PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html): `requestPartFields`, `requestPartBody` và subsection extractor.

