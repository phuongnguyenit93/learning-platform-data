# Đối chiếu Content-Disposition và tên part

## 1. Phân biệt name và filename

Trong request `multipart/form-data`, mỗi part có header riêng. Header quan trọng để nhận diện trường form là `Content-Disposition`. Với file upload, ví dụ:

```http
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

<binary bytes>
```

Hai tham số trong header có ý nghĩa khác nhau:

- `name="file"` là **tên trường/part** trong multipart form. Server dùng tên này để tìm đúng phần dữ liệu.
- `filename="report.pdf"` là **tên tệp do client cung cấp**. Nó không phải tên part và không phải đường dẫn lưu tệp trên server.

Trong Spring, `MultipartFile.getName()` trả về tên tham số multipart, còn `getOriginalFilename()` trả về filename gốc do client gửi. Tham khảo [MultipartFile Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html).

Bài học này hướng dẫn đối chiếu Content-Disposition với tên part trong Spring MVC và Spring REST Docs, kiểm tra bằng test, viết tài liệu chính xác và tránh sử dụng filename không an toàn.

## 2. Cấu trúc Content-Disposition trong multipart/form-data

Một request có thể chứa file và metadata JSON:

```http
POST /documents HTTP/1.1
Content-Type: multipart/form-data; boundary=----boundary42

------boundary42
Content-Disposition: form-data; name="file"; filename="handbook.pdf"
Content-Type: application/pdf

<file bytes>
------boundary42
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Employee handbook","category":"POLICY"}
------boundary42--
```

Theo [RFC 7578, mục 4.2](https://www.rfc-editor.org/rfc/rfc7578.html#section-4.2), mỗi part phải có Content-Disposition với disposition type `form-data` và tham số `name`. Với dữ liệu file, `filename` nên được cung cấp nếu tên có sẵn và có ý nghĩa, nhưng không bắt buộc trong mọi tình huống. Mỗi part có thể có Content-Type; nếu không có, mặc định là `text/plain`. Với file, nên dùng media type phù hợp nếu biết, nếu không có thể dùng `application/octet-stream`. Xem thêm RFC 7578 mục 4.4.

### 2.1. name nhận diện part; filename mô tả tệp

| Header | Ý nghĩa |
| --- | --- |
| `Content-Disposition: form-data` | Xác định part thuộc multipart form |
| `name="attachment"` | Tên part/field mà controller binding sử dụng |
| `filename="invoice.pdf"` | Tên tệp client khai báo |
| `Content-Type: application/pdf` | Media type được khai báo cho body của part |

Khi filename đổi từ `invoice.pdf` thành `invoice-final.pdf`, part vẫn có thể mang name `attachment`. Controller vẫn nhận đúng part; chỉ metadata tên tệp thay đổi. Ngược lại, đổi name từ `attachment` thành `file` là thay đổi contract request và cần đồng bộ controller/client.

### 2.2. Part không phải file có thể không có filename

Part văn bản hoặc JSON thường có:

```http
Content-Disposition: form-data; name="metadata"
Content-Type: application/json
```

Part này không cần filename vì nó chứa dữ liệu JSON, không phải tệp được chọn từ client. Không yêu cầu mọi part trong multipart request đều phải có filename.

### 2.3. Nhiều file cùng một tên trường

Khi một trường nhận nhiều file, RFC 7578 quy định gửi từng file trong một part riêng nhưng dùng cùng tham số `name`. Nhiều file của trường `attachments` đều mang `name="attachments"`, mỗi part có filename riêng. Spring có thể bind chúng vào `List<MultipartFile>` hoặc `MultipartFile[]`. Xem RFC 7578 mục 4.3.

## 3. Ánh xạ trong Spring MVC

Controller khai báo tên part bằng `@RequestPart`:

```java
@PostMapping(
    value = "/documents",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> upload(@RequestPart("file") MultipartFile file) {
    // ...
}
```

Từ `MultipartFile` có thể đọc:

```java
String partName = file.getName();
String originalFilename = file.getOriginalFilename();
String contentType = file.getContentType();
long size = file.getSize();
```

| Multipart | MultipartFile | Ý nghĩa |
| --- | --- | --- |
| `name="file"` | `getName()` | Tên part |
| `filename="report.pdf"` | `getOriginalFilename()` | Tên file gốc do client gửi |
| Part Content-Type | `getContentType()` | Media type được khai báo |
| Body bytes | `getBytes()` / `getInputStream()` | Nội dung file |

`getOriginalFilename()` có thể chứa path information, tên rỗng hoặc không có giá trị. Spring cảnh báo không nên dùng trực tiếp filename do client gửi; hãy loại bỏ thông tin thư mục, kiểm tra ký tự bất thường và ưu tiên tạo tên lưu trữ do server kiểm soát. Tham khảo [MultipartFile Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html).

Ví dụ controller để quan sát riêng hai giá trị:

```java
@RestController
class DocumentController {

    @PostMapping(
        value = "/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<Map<String, Object>> upload(
            @RequestPart("file") MultipartFile uploadedFile) {

        String storageKey = UUID.randomUUID().toString();

        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
            "partName", uploadedFile.getName(),
            "originalFilename", uploadedFile.getOriginalFilename() == null
                    ? "" : uploadedFile.getOriginalFilename(),
            "contentType", uploadedFile.getContentType() == null
                    ? "" : uploadedFile.getContentType(),
            "size", uploadedFile.getSize(),
            "storageKey", storageKey
        ));
    }
}
```

Đây là ví dụ minh họa. Trong ứng dụng thật, thường chỉ trả document ID hoặc storage key thay vì tiết lộ filename nguyên bản nếu không cần thiết.

## 4. Spring REST Docs mô tả tên part, không tự document filename

Dùng `requestParts(...)` cùng `partWithName(...)` để document part:

```java
requestParts(
    partWithName("file")
        .description("Tệp PDF cần tải lên"),
    partWithName("metadata")
        .description("Metadata JSON của tài liệu")
)
```

Snippet được sinh là `request-parts.adoc`. `partWithName("file")` trỏ tới **name của part**, tương ứng `name="file"` trong Content-Disposition. Nó không trỏ tới `filename="report.pdf"`.

Spring REST Docs kiểm tra part được mô tả có xuất hiện trong request hay không; part xuất hiện nhưng chưa mô tả cũng làm test strict thất bại. Có thể dùng `optional()`, `ignored()` hoặc `relaxedRequestParts(...)` theo contract. Xem [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html).

Snippet request-parts không tự sinh các cột riêng cho filename, Content-Type, kích thước hoặc kết quả xác minh nội dung file. Nếu những thuộc tính này quan trọng với client, giải thích trong phần văn bản và kiểm tra bằng assertions riêng. Không mô tả như thể `requestParts` đang tự xác minh các giá trị ấy.

## 5. MockMvc: kiểm tra name và filename riêng biệt

`MockMultipartFile` nhận tên part và tên file ở hai tham số đầu:

```java
MockMultipartFile file = new MockMultipartFile(
    "file",              // tên part: name
    "report.pdf",        // tên tệp: filename
    MediaType.APPLICATION_PDF_VALUE,
    pdfFixtureBytes
);
```

Nếu đảo hai tham số, tên part sẽ thành `report.pdf` và filename thành `file`. Controller khai báo `@RequestPart("file")` sẽ không nhận part theo tên mong đợi.

### 5.1. Test MockMvc hoàn chỉnh

Ví dụ dùng JUnit 5, Java 17+, MockMvc và Spring REST Docs. Byte fixture dưới đây chỉ dùng để kiểm tra multipart binding/metadata; nếu kiểm thử parser PDF, hãy dùng file PDF hợp lệ trong test resources.

```java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.HttpStatus;
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
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class DocumentContentDispositionTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new DocumentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void uploadSeparatesPartNameAndFilename() throws Exception {
        byte[] bytes = new byte[] {
            0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x34
        };

        MockMultipartFile file = new MockMultipartFile(
                "file", "report.pdf",
                MediaType.APPLICATION_PDF_VALUE, bytes
        );

        this.mockMvc.perform(multipart("/documents")
                        .file(file)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.partName").value("file"))
                .andExpect(jsonPath("$.originalFilename").value("report.pdf"))
                .andExpect(jsonPath("$.contentType")
                        .value(MediaType.APPLICATION_PDF_VALUE))
                .andExpect(jsonPath("$.size").value(bytes.length))
                .andDo(document("documents-upload",
                        requestParts(
                            partWithName("file")
                                .description("Tệp PDF; part name là file")
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

            return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
                "partName", file.getName(),
                "originalFilename",
                    file.getOriginalFilename() == null ? "" : file.getOriginalFilename(),
                "contentType",
                    file.getContentType() == null ? "" : file.getContentType(),
                "size", file.getSize()
            ));
        }
    }
}
```

Test xác minh riêng part name, filename, media type và số bytes. `requestParts` chỉ sinh bảng part; assertions xác nhận Spring bind multipart vào controller đúng như mong đợi.

### 5.2. Metadata JSON là một part khác

Part metadata thường có `name="metadata"`, `Content-Type: application/json` và không cần filename. Dùng `requestParts(partWithName("metadata"))` để mô tả nó, `requestPartBody("metadata")` để hiển thị JSON và `requestPartFields("metadata", ...)` để document schema bên trong.

## 6. Bảng đối chiếu từ wire format tới tài liệu

| Trên multipart wire | Spring MVC | Spring REST Docs |
| --- | --- | --- |
| `name="file"` | `@RequestPart("file")` / `MultipartFile.getName()` | `partWithName("file")` |
| `filename="report.pdf"` | `MultipartFile.getOriginalFilename()` | Văn bản mô tả và assertions riêng |
| Part Content-Type | `MultipartFile.getContentType()` | Văn bản mô tả và assertions riêng |
| Body bytes | `getBytes()` / `getInputStream()` | Không dùng field descriptor JSON cho bytes nhị phân |
| `name="metadata"` | `@RequestPart("metadata")` | `partWithName("metadata")` |
| Metadata JSON | DTO/Map qua message converter | `requestPartFields` và tùy chọn `requestPartBody` |

Nếu cần kiểm tra header part thực tế, bổ sung kiểm thử phù hợp ở tầng multipart parser/binding hoặc integration test. Không kết luận filename đã được document chỉ vì bảng request-parts có dòng file.

## 7. Quy tắc an toàn đối với filename

Filename là dữ liệu client gửi và không đáng tin cậy. RFC 7578 lưu ý phía nhận không được sử dụng tên file một cách mù quáng, cần kiểm tra và không dùng thông tin thư mục có thể xuất hiện trong filename. Spring cũng cảnh báo tên có thể chứa path information hoặc chuỗi như `..`.

Các nguyên tắc cho API upload:

1. **Không dùng trực tiếp làm đường dẫn lưu trữ.** Tạo storage key hoặc filename nội bộ do server quản lý.
2. **Loại bỏ path information.** Không để chuỗi `../../secret.txt` quyết định vị trí ghi file.
3. **Kiểm tra độ dài và ký tự.** Xác định quy tắc cho ký tự điều khiển, tên rỗng và phần mở rộng.
4. **Không tin phần mở rộng.** `report.pdf` không chứng minh bytes là PDF.
5. **Không tin Content-Type do client gửi.** Xác minh nội dung theo yêu cầu thực tế của ứng dụng.
6. **Không ghi filename nhạy cảm vào log hoặc tài liệu công khai.** Dùng fixture giả cho snippet và ví dụ.

### 7.1. filename không phải lúc nào cũng bắt buộc

RFC 7578 nói filename nên được cung cấp cho nội dung file khi tên có sẵn và có ý nghĩa; filename không bắt buộc khi tên không có, không có ý nghĩa hoặc mang tính riêng tư.

### 7.2. Không nhầm filename* với filename

RFC 7578 quy định tham số `filename*` theo cách mã hóa của RFC 5987 không được sử dụng trong `multipart/form-data`. Không áp dụng máy móc hướng dẫn về `filename*` của Content-Disposition trong HTTP response sang Content-Disposition của từng part. Xem [RFC 7578 `4.2](https://www.rfc-editor.org/rfc/rfc7578.html#section-4.2).

### 7.3. Nhiều file cùng tên part

Nếu gửi nhiều ảnh cùng field `attachments`, mỗi file là một part riêng và cùng mang `name="attachments"`; mỗi part có filename riêng. Controller có thể bind vào `List<MultipartFile>` hoặc `MultipartFile[]`. RFC 7578 mô tả cách gửi này tại mục 4.3.

## 8. Tài liệu hóa trong Asciidoctor

Với operation identifier `documents-upload`, `requestParts` tạo `request-parts.adoc` trong thư mục operation:

```text
build/generated-snippets/
└── documents-upload/
    ├── request-parts.adoc
    ├── http-request.adoc
    └── http-response.adoc
```

Có thể giải thích name và filename bên cạnh snippet:

```asciidoc
= Document API

== POST /documents

Request dùng multipart/form-data. Part file có name là "file".
Client có thể gửi filename trong Content-Disposition. Filename là
metadata do client cung cấp và không được dùng trực tiếp làm đường dẫn
lưu trữ.

=== Các part

include::{snippets}/documents-upload/request-parts.adoc[]

=== Quy tắc file part

* Part name là file.
* Filename là tên tệp gốc do client khai báo; có thể không có trong một số luồng.
* Content-Type là media type khai báo cho part.
* Server xác minh định dạng và kích thước theo chính sách upload.
```

REST Docs không tự sinh bảng riêng cho tham số filename từ `requestParts`. Phần giải thích là nội dung biên soạn thủ công; assertions trong test xác minh hành vi thực tế.

## 9. WebTestClient và REST Assured

### 9.1. WebTestClient

Multipart body có thể được tạo bằng `BodyInserters.fromMultipartData`. Resource cần cung cấp filename khi muốn client tạo part có filename:

```java
Resource resource = new ByteArrayResource(pdfBytes) {
    @Override
    public String getFilename() {
        return "report.pdf";
    }
};

HttpHeaders partHeaders = new HttpHeaders();
partHeaders.setContentType(MediaType.APPLICATION_PDF);
HttpEntity<Resource> filePart = new HttpEntity<>(resource, partHeaders);

MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
parts.add("file", filePart);

webTestClient.post()
    .uri("/documents")
    .body(BodyInserters.fromMultipartData(parts))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("documents-upload",
        requestParts(
            partWithName("file").description("Tệp PDF; name của part là file")
        )
    ));
```

WebTestClient cần được cấu hình Spring REST Docs documentation filter trên builder trước khi build. Kiểm tra filename được resource/client đưa vào request như mong đợi.

### 9.2. REST Assured

REST Assured hỗ trợ gửi file part qua `multiPart`:

```java
RestAssured.given(this.spec)
    .filter(document("documents-upload",
        requestParts(
            partWithName("file").description("Tệp PDF; name của part là file")
        )
    ))
    .multiPart("file", new File("report.pdf"), "application/pdf")
    .when()
    .post("/documents")
    .then()
    .statusCode(201);
```

Tên `file` truyền vào `multiPart` là tên part; `report.pdf` là filename. `spec` cần được cấu hình endpoint và REST Docs filter theo dự án. Dùng file fixture kiểm thử xác định, không tham chiếu đường dẫn tùy ý trên máy developer.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@RequestPart("file")` không nhận được file | Multipart `name` khác `file` | Đồng bộ name giữa client, test và controller |
| `getOriginalFilename()` trả tên không mong đợi | Filename đặt nhầm vào tham số name hoặc client không gửi filename | Kiểm tra hai tham số MockMultipartFile và raw part |
| Tưởng `partWithName("report.pdf")` là đúng | Nhầm filename với part name | Dùng `partWithName("file")` nếu name là file |
| `request-parts.adoc` không hiển thị filename | Snippet mô tả part name, không tự tạo cột filename | Diễn giải filename và kiểm tra bằng assertion |
| Filename chứa path | Client gửi tên có thông tin thư mục | Chuẩn hóa tên, bỏ path và tạo storage key an toàn |
| Content-Type báo PDF nhưng parser lỗi | Media type client khai báo không khớp bytes | Xác minh nội dung thực tế bằng parser/validator |
| Metadata JSON không bind được | Sai name, media type hoặc JSON part | Kiểm tra `@RequestPart`, Content-Type và JSON body |
| Tên Unicode bị biến đổi | Khác biệt encoding giữa client/server | Đối chiếu RFC, client và container thực tế; viết test tương thích |
| Nhiều file chỉ nhận một | Client dùng tên part khác nhau hoặc controller chỉ bind một file | Gửi từng file thành part riêng với cùng name và bind collection |

## 11. Build và CI

Với Gradle Groovy DSL, giả định test ghi snippets vào `build/generated-snippets` và dự án đã cấu hình plugin Asciidoctor:

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

Trong CI, kiểm tra:

1. Test gửi đúng part name và filename theo contract mô tả.
2. Test xác minh riêng `getName()` và `getOriginalFilename()`.
3. Media type và nội dung file được kiểm tra theo policy endpoint.
4. `requestParts` mô tả đầy đủ part được hỗ trợ.
5. Asciidoctor include snippet đúng operation identifier.
6. Fixture và generated snippets không chứa tên tệp thật hoặc dữ liệu nhạy cảm.

Test tài liệu thành công không thay thế kiểm thử bảo mật upload. Test filename path traversal, file giả mạo, file quá lớn và quyền truy cập nên được tách riêng; chỉ tạo snippet công khai cho các trường hợp cần thiết.

## 12. Bài thực hành

Tạo test `DocumentContentDispositionTest`:

1. Tạo `MockMultipartFile("file", "report.pdf", "application/pdf", bytes)`.
2. Xác nhận `getName()` là `file` và `getOriginalFilename()` là `report.pdf`.
3. Đổi filename thành `annual-report.pdf` nhưng giữ nguyên part name; xác minh controller vẫn nhận đúng part.
4. Đổi part name thành `attachment`; cập nhật `@RequestPart` và `partWithName` theo contract.
5. Tạo part metadata JSON không có filename; xác nhận nó vẫn hợp lệ theo thiết kế endpoint.
6. Thử filename có path như `../../report.pdf`; xác minh ứng dụng không dùng trực tiếp giá trị đó làm đường dẫn.
7. Tạo nhiều file part cùng name `attachments` và bind collection.
8. Include `request-parts.adoc` vào Asciidoctor, bổ sung giải thích filename rồi chạy `./gradlew clean test asciidoctor`.

**Tiêu chí hoàn thành:** giải thích được `name` và `filename` khác nhau, truy vết được chúng qua MultipartFile, biết snippet request-parts document điều gì và dùng assertions để kiểm tra thuộc tính mà snippet không tự mô tả.

## 13. Câu hỏi tự kiểm tra

**1. Trong Content-Disposition với `name="file"; filename="report.pdf"`, giá trị nào là tên part?**

`name="file"` là tên part. `filename="report.pdf"` là tên tệp do client gửi.

**2. Spring MultipartFile cung cấp hai giá trị này ở đâu?**

`getName()` trả về tên part; `getOriginalFilename()` trả về tên file gốc.

**3. `partWithName("file")` có document filename không?**

Không. Nó chọn part theo name và tạo mô tả part. Filename cần được giải thích trong văn bản và kiểm tra bằng test.

**4. Có thể tin filename để tạo đường dẫn lưu file không?**

Không. Filename do client gửi có thể chứa path hoặc chuỗi nguy hiểm. Hãy chuẩn hóa, xác minh và tạo tên lưu trữ do server quản lý.

**5. Mọi file part có bắt buộc phải có filename không?**

Không. RFC 7578 nói filename nên được cung cấp khi có và có ý nghĩa; trong một số workflow filename có thể không có hoặc không phù hợp để tiết lộ.

## Tài liệu tham khảo

- [RFC 7578 — multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578.html): Content-Disposition, name, filename, nhiều file cho cùng field và Content-Type của mỗi part.
- [Spring Framework — MultipartFile Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html): ý nghĩa getName(), getOriginalFilename(), getContentType() và cảnh báo với filename.
- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): document request parts và strict/relaxed behavior.

