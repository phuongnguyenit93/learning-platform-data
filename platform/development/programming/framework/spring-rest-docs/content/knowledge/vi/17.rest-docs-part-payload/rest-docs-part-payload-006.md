# File part và phần dữ liệu nhị phân trong Spring REST Docs

## 1. Đặc điểm của file part trong multipart request

Một endpoint tải tệp lên thường nhận request dạng **multipart/form-data**. Request chứa một hoặc nhiều part; mỗi part có tên, header và body riêng. Với file part, body thường là chuỗi bytes của PDF, ảnh, âm thanh hoặc dữ liệu nhị phân khác.

Ví dụ endpoint `POST /documents` nhận part:

```text
Part name: file
Filename: handbook.pdf
Content-Type: application/pdf
Body: bytes của file PDF
```

Khác với part JSON, nội dung file không phải một object JSON gồm các field có thể mô tả bằng `fieldWithPath(...)`. Các byte của file có thể chứa cấu trúc định dạng phức tạp, ký tự không in được, metadata nhị phân hoặc dữ liệu nén.

Spring REST Docs cung cấp `requestParts(...)` và `partWithName(...)` để mô tả **sự hiện diện và mục đích của file part** trong multipart request. Test vẫn có thể kiểm tra filename, media type, kích thước hoặc nội dung file bằng assertion thông thường.

Bài học tập trung vào:

- mô tả file part trong multipart request;
- tạo dữ liệu file nhị phân giả, ổn định cho kiểm thử;
- kiểm tra tên file, content type, kích thước và kết quả xử lý;
- phân biệt file part với JSON/text part;
- quyết định khi nào dùng `requestPartBody(...)` và khi nào không nên đưa body nhị phân vào snippet;
- dùng MockMvc, WebTestClient hoặc REST Assured để sinh tài liệu;
- bảo vệ tài liệu và CI khỏi dữ liệu thật, file quá lớn hoặc thông tin nhạy cảm.

## 2. Mô tả file part bằng requestParts

`requestParts(...)` tạo snippet `request-parts.adoc` mô tả các part mà resource hỗ trợ. Mỗi `partWithName(...)` chỉ ra tên part và mô tả mục đích:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("file")
        .description("File PDF của tài liệu cần tải lên")
)
```

Bảng này giúp người đọc biết request cần một part tên `file` dùng để gửi tài liệu PDF. Nó mô tả **cấu trúc multipart ở cấp part**, không phải schema của bytes bên trong file.

Nếu endpoint nhận thêm part `metadata` là JSON, có thể mô tả cả hai:

```java
requestParts(
    partWithName("file")
        .description("File PDF cần tải lên"),
    partWithName("metadata")
        .description("Thông tin JSON mô tả file")
)
```

Khi đó người đọc hiểu vai trò của từng part. JSON metadata có thể được document riêng bằng `requestPartFields("metadata", ...)`; file bytes không được xem như một tập JSON fields.

### 2.1. Những thông tin file part và bảng request-parts không thay thế cho nhau

Trong hợp đồng multipart thường có các thuộc tính sau:

| Thuộc tính | Ý nghĩa | Cách kiểm tra hoặc tài liệu hóa |
| --- | --- | --- |
| Tên part | Tên client gửi trong multipart body | `partWithName("file")` |
| Filename | Tên file do client cung cấp | Assertion trên `MultipartFile.getOriginalFilename()`; giải thích quy ước trong tài liệu |
| Content-Type | Media type của file part | Assertion trên `MultipartFile.getContentType()`; mô tả loại file được chấp nhận |
| Kích thước | Số bytes của file | Assertion trên `MultipartFile.getSize()`; mô tả giới hạn upload |
| Nội dung bytes | Dữ liệu thực tế của file | Assertion/hash hoặc kiểm thử xử lý; không nhất thiết nhúng bytes vào tài liệu |
| Loại định dạng thực tế | Cấu trúc file bên trong, ví dụ PDF/PNG | Kiểm tra bằng parser/validator phù hợp; không chỉ tin filename hay Content-Type |

Snippet `request-parts.adoc` chủ yếu cung cấp bảng tên part và mô tả. Hãy dùng văn bản API, assertion và kiểm tra nghiệp vụ để làm rõ các thuộc tính còn lại. Không giả định snippet tự tạo một bảng đầy đủ cho filename, media type và kích thước nếu handler không document những thông tin đó.

## 3. Tạo file nhị phân giả cho kiểm thử

Không nên dùng file thật từ máy của lập trình viên hoặc tài liệu nội bộ. Hãy tạo fixture nhỏ, xác định và không chứa dữ liệu nhạy cảm.

Với MockMvc, `MockMultipartFile` nhận tên part, filename, content type và byte array:

```java
byte[] pdfBytes = new byte[] {
    0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x34,
    0x0A, 0x25, (byte) 0xE2, (byte) 0xE3, (byte) 0xCF, (byte) 0xD3
};

MockMultipartFile file = new MockMultipartFile(
    "file",
    "handbook.pdf",
    "application/pdf",
    pdfBytes
);
```

Mảng trên chỉ là fixture byte ngắn để minh họa việc truyền dữ liệu nhị phân; nó **không phải một PDF hoàn chỉnh để kiểm tra parser PDF**. Nếu controller hoặc service cần parse PDF, hãy dùng một fixture PDF nhỏ, hợp lệ, được quản lý trong test resources và có nguồn gốc rõ ràng.

Với một file ảnh giả, có thể dùng byte array riêng và content type tương ứng. Điều quan trọng là fixture phải khớp với mục tiêu test:

- kiểm tra request multipart/binding: bytes nhỏ có thể đủ;
- kiểm tra parser định dạng: cần file mẫu thực sự hợp lệ;
- kiểm tra giới hạn dung lượng: tạo byte array có kích thước phù hợp;
- kiểm tra bảo mật file: cần bộ test chuyên biệt cho file giả mạo, nội dung không hợp lệ hoặc loại file bị cấm.

Đừng dùng một file có tên .pdf nhưng bytes không phải PDF rồi kết luận ứng dụng đã xác thực định dạng. Filename và Content-Type là metadata do client cung cấp; chúng không chứng minh nội dung thực tế.

## 4. Ví dụ MockMvc: document file part và kiểm tra metadata

Ví dụ dùng JUnit 5, Java 17+, Spring MVC Test và Spring REST Docs. Endpoint mẫu nhận file PDF và trả về thông tin đã kiểm tra. Phần lưu trữ file được giản lược để bài tập trung vào multipart documentation.

```java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
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
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class DocumentFileUploadDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new DocumentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void uploadPdfFile() throws Exception {
        byte[] pdfBytes = new byte[] {
            0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x34, 0x0A
        };

        MockMultipartFile file = new MockMultipartFile(
                "file",
                "handbook.pdf",
                MediaType.APPLICATION_PDF_VALUE,
                pdfBytes
        );

        this.mockMvc.perform(multipart("/documents")
                        .file(file)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.filename").value("handbook.pdf"))
                .andExpect(jsonPath("$.contentType")
                        .value(MediaType.APPLICATION_PDF_VALUE))
                .andExpect(jsonPath("$.size").value(pdfBytes.length))
                .andDo(document("documents-upload",
                        requestParts(
                                partWithName("file")
                                        .description("File PDF cần tải lên")
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
        ResponseEntity<Map<String, Object>> upload(
                @RequestPart("file") MultipartFile file) {

            if (file.isEmpty()) {
                return ResponseEntity.badRequest().build();
            }

            return ResponseEntity.status(201).body(Map.of(
                    "filename", file.getOriginalFilename(),
                    "contentType", file.getContentType(),
                    "size", file.getSize()
            ));
        }
    }
}
```

Ví dụ này thực hiện ba việc riêng:

1. `requestParts(...)` tạo bảng mô tả part tên `file`.
2. `jsonPath` xác nhận server nhận đúng filename, content type và size của fixture.
3. Controller mẫu trả metadata để test kiểm tra; trong ứng dụng thật, response có thể chỉ trả document ID hoặc trạng thái upload.

Bảng request-parts không tự biến filename, media type và size thành các cột được kiểm tra. Các assertion phía trên xác nhận cách ứng dụng nhận file trong test case này. Nếu các thuộc tính đó là contract mà client cần hiểu, hãy giải thích thêm trong trang API.

## 5. Có nên dùng requestPartBody cho file nhị phân?

`requestPartBody("file")` có thể tạo snippet body của một request part. Tính năng này hữu ích khi body part là văn bản hoặc JSON mà con người có thể đọc. Với một file nhị phân như PDF, PNG, ZIP hoặc audio, việc render bytes thành văn bản thường không hữu ích:

- dữ liệu có thể chứa byte không in được;
- snippet có thể rất dài hoặc khó đọc;
- một số định dạng có thể bị nén hoặc mã hóa;
- file có thể chứa metadata riêng tư hoặc nội dung nhạy cảm;
- tài liệu có thể phình to và khó review.

Vì vậy, với file part, thông thường nên mô tả part bằng `requestParts(...)` và dùng assertion để kiểm tra metadata/nội dung. Không cần gọi `requestPartBody("file")` chỉ để chứng minh file đã được gửi.

Ví dụ phù hợp cho part JSON:

```java
requestPartBody("metadata")
```

Ví dụ phần JSON này có thể hiển thị rõ trong snippet. Còn file part:

```java
requestParts(
    partWithName("file")
        .description("File PDF của tài liệu")
)
```

Nếu sản phẩm thực sự cần phát hành một file mẫu để client tải xuống, hãy quản lý file mẫu như một artifact/tệp ví dụ riêng trong quy trình phát hành tài liệu. Không dùng snippet body như một cơ chế phát hành file nhị phân trừ khi định dạng và cách hiển thị đã được kiểm soát rõ ràng.

## 6. File part đi cùng metadata JSON

Một endpoint thực tế thường nhận file và metadata:

```text
POST /documents
multipart/form-data
├── file: handbook.pdf (application/pdf, binary)
└── metadata: application/json
    ├── title
    ├── category
    └── visibility
```

Test có thể document cả hai part:

```java
.andDo(document("documents-upload",
    requestParts(
        partWithName("file")
            .description("File PDF cần tải lên"),
        partWithName("metadata")
            .description("Metadata JSON mô tả tài liệu")
    ),
    requestPartFields("metadata",
        fieldWithPath("title").description("Tiêu đề"),
        fieldWithPath("category").description("Nhóm tài liệu"),
        fieldWithPath("visibility").description("Phạm vi hiển thị")
    )
));
```

Bảng part cho biết request có file và metadata. Bảng part fields chỉ document JSON metadata. Không dùng `requestPartFields("file", ...)` cho nội dung PDF vì bytes của file không có cấu trúc field JSON.

Có thể thêm `requestPartBody("metadata")` để hiển thị JSON mẫu. Khi đó tài liệu có ba lớp rõ ràng: bảng part, JSON metadata mẫu và bảng schema metadata.

## 7. Kiểm thử giới hạn và quy tắc file

Spring REST Docs tạo tài liệu; nó không thay thế validation upload. Ngoài `requestParts`, endpoint thường cần các kiểm tra nghiệp vụ:

| Quy tắc | Kiểm thử nên có |
| --- | --- |
| File bắt buộc | Gửi request không có part file và xác minh lỗi phù hợp |
| File không được rỗng | Gửi file zero-byte và xác minh phản hồi |
| Giới hạn kích thước | Gửi file nhỏ hơn, bằng và lớn hơn ngưỡng |
| Loại file được chấp nhận | Kiểm tra content type khai báo và/hoặc định dạng thực tế |
| Filename | Kiểm tra tên rỗng, tên dài, ký tự đặc biệt và xử lý an toàn |
| Tên file trùng | Xác minh quy tắc ghi đè hoặc đổi tên |
| Nội dung file | Kiểm tra parser, checksum hoặc kết quả xử lý tùy nghiệp vụ |
| Quyền upload | Xác minh người dùng chỉ được upload vào vùng được phép |

Ví dụ test giới hạn kích thước không nhất thiết phải sinh cùng snippet công khai. Có thể tách test tài liệu cho kịch bản thành công với test validation/error để kiểm tra các trường hợp biên. Nếu cần document lỗi, dùng identifier riêng như `documents-upload-too-large` để tránh ghi đè snippet thành công.

### 7.1. Content-Type không xác nhận định dạng thực tế

Part có `Content-Type: application/pdf` chỉ thể hiện loại media mà client khai báo. Một client có thể gửi nội dung bất kỳ với header đó. Ứng dụng cần xác thực định dạng theo yêu cầu an toàn của sản phẩm, chẳng hạn kiểm tra magic bytes hoặc parse bằng thư viện phù hợp.

Tương tự, filename có đuôi `.pdf` không bảo đảm bytes là PDF. Tài liệu API nên ghi rõ endpoint chấp nhận loại file nào, giới hạn kích thước ra sao và thông tin nào được kiểm tra, dựa trên behavior thực tế.

### 7.2. Fixture cho dữ liệu nhị phân

Dùng fixture nhỏ, deterministic, có thể tạo từ byte array hoặc file test resource hợp lệ. Không dùng tài liệu thật chứa thông tin cá nhân, hợp đồng, dữ liệu khách hàng hoặc nội dung độc quyền trong snippet hoặc repository.

Nếu test cần file hợp lệ cho parser, file test resource phải nhỏ và có mục đích rõ ràng. Nếu chỉ cần xác minh wiring multipart, fixture byte tối thiểu có thể đủ; đừng mô tả nó là file định dạng hoàn chỉnh.

## 8. File part với WebTestClient

Với WebTestClient, multipart body thường được tạo bằng `BodyInserters.fromMultipartData` với `MultiValueMap`. Để gửi file resource có filename, có thể dùng `ByteArrayResource` override `getFilename()`:

```java
byte[] pdfBytes = new byte[] {
    0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x34
};

Resource pdf = new ByteArrayResource(pdfBytes) {
    @Override
    public String getFilename() {
        return "handbook.pdf";
    }
};

HttpHeaders fileHeaders = new HttpHeaders();
fileHeaders.setContentType(MediaType.APPLICATION_PDF);

HttpEntity<Resource> filePart = new HttpEntity<>(pdf, fileHeaders);

MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
parts.add("file", filePart);

webTestClient.post()
    .uri("/documents")
    .body(BodyInserters.fromMultipartData(parts))
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("documents-upload",
        requestParts(
            partWithName("file")
                .description("File PDF cần tải lên")
        )
    ));
```

WebTestClient cần được cấu hình REST Docs documentation filter trên builder trước khi build. Đoạn trên minh họa phần tạo multipart file part và handler tài liệu; các import, server/client setup và context provider cần được khai báo theo test configuration của dự án.

Nếu API yêu cầu metadata JSON, thêm part metadata dưới dạng object hoặc `HttpEntity` có Content-Type `application/json`. Đảm bảo test gửi đúng media type mà server mong đợi.

## 9. File part với REST Assured

REST Assured hỗ trợ gửi file part qua `multiPart`:

```java
RestAssured.given(this.spec)
    .accept("application/json")
    .filter(document("documents-upload",
        requestParts(
            partWithName("file")
                .description("File PDF cần tải lên")
        )
    ))
    .multiPart("file", new File("handbook.pdf"), "application/pdf")
    .when()
    .post("/documents")
    .then()
    .statusCode(201);
```

`spec` cần được cấu hình với REST Docs filter theo cách tích hợp REST Assured của dự án. File `handbook.pdf` phải là fixture kiểm thử xác định, không phải đường dẫn tới file riêng trên máy developer. Nếu dùng byte array hoặc input stream, hãy xác nhận overload `multiPart` đang sử dụng gửi đúng filename và media type.

## 10. Tên snippet và tài liệu Asciidoctor

Với operation identifier `documents-upload`, `requestParts(...)` tạo `request-parts.adoc` trong thư mục operation:

```text
build/generated-snippets/
└── documents-upload/
    ├── request-parts.adoc
    ├── http-request.adoc
    └── http-response.adoc
```

Nếu test cũng document part metadata, có thể có thêm:

```text
request-part-metadata-body.adoc
request-part-metadata-fields.adoc
```

Tài liệu Asciidoctor có thể viết:

```asciidoc
= Document API
:toc: left

== POST /documents

Tải lên file PDF. Client gửi file trong part file
với media type application/pdf.

=== Các part được hỗ trợ

include::{snippets}/documents-upload/request-parts.adoc[]

=== Kết quả

include::{snippets}/documents-upload/http-response.adoc[]
```

Phần văn bản giải thích các giới hạn filename, kích thước và định dạng nên được viết dựa trên contract thực tế. Snippet request-parts không tự mô tả tất cả quy tắc validation của file.

## 11. Tích hợp Gradle và CI

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

CI nên xác nhận:

1. Test tạo file fixture và multipart request thành công.
2. Part name trong request khớp `partWithName`.
3. Assertion filename, content type, size hoặc nội dung quan trọng chạy thành công.
4. Snippet request-parts được sinh từ test hiện tại.
5. Asciidoctor include đúng operation identifier và snippet name.
6. Không có file thật hoặc dữ liệu nhạy cảm bị đưa vào generated snippets hay repository.

Nếu build dùng Maven, thư mục snippet thường được cấu hình là `target/generated-snippets`; bước biên soạn tài liệu phải chạy sau test sinh snippet.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy part file | Tên trong MockMultipartFile/client khác tên trong descriptor | Đồng bộ tên part từ client, controller tới `partWithName` |
| Test nhận file nhưng filename rỗng | Multipart client/resource không cung cấp filename | Đặt filename trong MockMultipartFile hoặc Resource |
| Content-Type không như mong đợi | File part chưa gắn media type hoặc client serialize khác | Kiểm tra header của part và dùng HttpEntity khi cần |
| File part bị document như JSON | Dùng `requestPartFields` cho bytes nhị phân | Chỉ dùng `requestPartFields` cho part có payload cấu trúc |
| Snippet body chứa ký tự khó đọc | Gọi `requestPartBody` cho PDF/PNG/binary | Chỉ sinh body snippet cho part văn bản/JSON có thể đọc |
| Test pass dù file định dạng sai | Chỉ kiểm tra filename/content type | Parse hoặc kiểm tra nội dung thực tế theo contract |
| Test upload quá lớn làm build nặng | Fixture không kiểm soát kích thước | Dùng fixture nhỏ và test riêng cho giới hạn |
| Tài liệu tiết lộ nội dung file | Dùng file thật hoặc đưa binary body vào snippet | Dùng dữ liệu giả; chỉ document mô tả part và assertion metadata |
| Asciidoctor thiếu request-parts | Test chưa sinh snippet, sai identifier hoặc output directory | Kiểm tra test, operation ID và include path |

## 13. Bài thực hành

Tạo test `DocumentFileUploadDocumentationTest`:

1. Tạo file part `file` bằng `MockMultipartFile` với filename `handbook.pdf`, media type `application/pdf` và byte fixture giả.
2. Dùng `requestParts(partWithName("file"), ...)` để mô tả vai trò của file.
3. Thêm assertion cho filename, content type và kích thước file; nếu parser yêu cầu PDF hợp lệ, dùng fixture PDF hợp lệ thay cho byte array tối thiểu.
4. Thử filename trống và file rỗng; xác minh endpoint xử lý theo contract.
5. Thử file vượt giới hạn; tạo test lỗi riêng và document bằng operation identifier riêng nếu cần.
6. Thêm part metadata JSON; document danh sách part, body JSON và field bằng các handler tương ứng.
7. Không gọi `requestPartBody("file")` cho fixture binary; thử trong môi trường thử nghiệm để quan sát vì sao snippet không phù hợp với tài liệu phát hành.
8. Nhúng `request-parts.adoc` vào Asciidoctor và chạy `./gradlew clean test asciidoctor`.

**Tiêu chí hoàn thành:** bạn mô tả được file part ở cấp multipart, kiểm tra riêng filename/media type/size/content, phân biệt file bytes với JSON fields và lựa chọn snippet không làm tài liệu khó đọc hoặc tiết lộ dữ liệu thật.

## 14. Câu hỏi tự kiểm tra

**1. API nào mô tả file part của multipart request?**

Dùng `requestParts(partWithName("file").description(...))`. Nó mô tả part và vai trò của part trong request.

**2. requestParts có kiểm tra bytes của file đúng định dạng không?**

Không. Nó document sự hiện diện/mục đích của part. Định dạng thực tế cần được xác minh bằng parser, magic bytes hoặc validation phù hợp.

**3. Có nên dùng requestPartBody("file") cho PDF hoặc ảnh không?**

Thông thường không. Body nhị phân khó đọc và có thể làm lộ dữ liệu. Chỉ dùng body snippet cho part văn bản/JSON mà người đọc cần xem nội dung.

**4. Làm sao kiểm tra filename và Content-Type?**

Dùng assertion trên `MultipartFile.getOriginalFilename()` và `getContentType()` hoặc kiểm tra request part headers trong test. Giải thích các quy tắc được hỗ trợ trong tài liệu.

**5. File có Content-Type application/pdf có chắc là PDF không?**

Không. Đây là media type client khai báo. Ứng dụng cần xác thực nội dung thực tế nếu contract hoặc yêu cầu an toàn đòi hỏi.

## Tài liệu tham khảo

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): document request parts, part body và part fields với MockMvc, WebTestClient và REST Assured.
- [Spring Framework — Multipart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): cách Spring MVC bind multipart request và file part.
- [Spring Framework — RequestPart](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestPart.html): ánh xạ part vào tham số controller và xử lý qua HttpMessageConverter.

