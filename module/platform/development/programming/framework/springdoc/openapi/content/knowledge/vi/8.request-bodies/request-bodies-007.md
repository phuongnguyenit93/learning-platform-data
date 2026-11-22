# Multipart gồm tệp, nhiều tệp và trường dữ liệu thông thường

API upload thường cần nhận một hoặc nhiều tệp cùng với các trường mô tả như tiêu đề, loại tài liệu, ghi chú hoặc metadata. HTTP biểu diễn nhóm dữ liệu này bằng `multipart/form-data`: mỗi phần (part) có tên, header riêng và nội dung riêng. Spring Boot cung cấp cơ chế binding để chuyển các part thành `MultipartFile`, DTO hoặc kiểu dữ liệu phù hợp; springdoc-openapi mô tả cấu trúc đó trong OpenAPI để Swagger UI và client biết cách gửi request.

Điểm quan trọng là mỗi part có thể mang kiểu nội dung khác nhau. Tệp thường là dữ liệu nhị phân; trường văn bản thường là `text/plain`; metadata có thể là JSON với `application/json`. Vì vậy, tài liệu phải mô tả đúng tên part, kiểu dữ liệu, media type và cách lặp part khi upload nhiều tệp.

## 1. `multipart/form-data` hoạt động như thế nào?

Khác với một request JSON thông thường, multipart chia request body thành nhiều phần. Mỗi phần được ngăn cách bằng một chuỗi boundary do client tạo và khai báo trong header `Content-Type`.

Ví dụ một request có trường `title`, metadata JSON và một file:

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=----UploadBoundary

------UploadBoundary
Content-Disposition: form-data; name="title"
Content-Type: text/plain

Hợp đồng mua bán
------UploadBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"category":"LEGAL","reference":"HD-2026-001"}
------UploadBoundary
Content-Disposition: form-data; name="file"; filename="contract.pdf"
Content-Type: application/pdf

<nội dung nhị phân của tệp>
------UploadBoundary--
```

Một multipart request có thể chứa:

- **Part văn bản**: giá trị đơn như `title`, `description`, `category`.
- **Part JSON**: object có cấu trúc như `metadata`, `options` hoặc thông tin nghiệp vụ phức tạp.
- **Part tệp**: dữ liệu nhị phân, thường có `filename` và content type riêng.
- **Nhiều part cùng tên**: ví dụ `files` xuất hiện nhiều lần để gửi nhiều tệp.

Boundary, `Content-Disposition` và header của từng part thuộc định dạng truyền tải. Client HTTP hoặc trình duyệt thường tạo các giá trị này. Không tự ghép boundary bằng tay trong code ứng dụng khi đã dùng thư viện HTTP hỗ trợ multipart.

## 2. Khai báo endpoint nhận một tệp

Với Spring MVC, kiểu `MultipartFile` biểu diễn một tệp được gửi trong multipart request. Có thể dùng `@RequestPart` để lấy đúng part theo tên:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
class DocumentController {

    @PostMapping(
            path = "/api/documents/upload",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    UploadResponse upload(
            @RequestPart("file") MultipartFile file) {
        return documentService.store(file);
    }
}
```

`consumes = MediaType.MULTIPART_FORM_DATA_VALUE` khai báo endpoint chấp nhận `multipart/form-data`. `@RequestPart("file")` chỉ rõ part có tên `file` được bind vào tham số `MultipartFile`.

Với một file đơn giản, `@RequestParam("file") MultipartFile` cũng có thể được dùng trong Spring MVC. `@RequestPart` thể hiện rõ rằng tham số là một phần của multipart body; nó đặc biệt hữu ích khi request còn có các part phức tạp cần chuyển đổi qua `HttpMessageConverter`.

Trong OpenAPI, tệp thường được mô tả bằng schema kiểu chuỗi với định dạng `binary`:

```yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required:
          - file
        properties:
          file:
            type: string
            format: binary
```

Springdoc có thể suy ra schema tệp từ `MultipartFile`. Nếu kết quả chưa rõ hoặc cần chủ động kiểm soát schema, có thể dùng `@Schema(type = "string", format = "binary")` ở vị trí phù hợp hoặc khai báo request body OpenAPI tường minh.

## 3. Nhận tệp cùng các trường văn bản

Một endpoint upload thường cần cả file và một số trường đơn giản. Với Spring MVC, có thể nhận chúng bằng `@RequestPart` cho tệp và `@RequestParam` cho các trường form:

```java
@PostMapping(
        path = "/api/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
DocumentResponse createDocument(
        @RequestParam("title") String title,
        @RequestParam(name = "description", required = false) String description,
        @RequestPart("file") MultipartFile file) {

    return documentService.create(title, description, file);
}
```

Request tương ứng:

```text
POST /api/documents
Content-Type: multipart/form-data

title       = Hợp đồng mua bán
description = Bản đã ký
file        = contract.pdf
```

`@RequestParam` có thể bind các trường form và multipart file trong Spring MVC. Khi dùng với `String`, `Integer`, enum hoặc kiểu đơn giản, Spring chuyển đổi giá trị theo hệ thống conversion service. Các trường không bắt buộc nên được đánh dấu `required = false` hoặc dùng kiểu phù hợp để thể hiện rõ khả năng vắng mặt.

### 3.1. Dùng `@ModelAttribute` cho một form DTO

Nếu có nhiều trường form đơn giản, gom chúng vào một DTO giúp controller dễ đọc hơn:

```java
public class DocumentUploadForm {
    @NotBlank
    private String title;

    private String description;

    private MultipartFile file;

    // getters và setters
}
```

Controller:

```java
@PostMapping(
        path = "/api/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
DocumentResponse createDocument(
        @Valid @ModelAttribute DocumentUploadForm form) {
    return documentService.create(
            form.getTitle(),
            form.getDescription(),
            form.getFile()
    );
}
```

Spring MVC bind các field form theo tên property. `@ModelAttribute` phù hợp với form gồm các giá trị đơn và file; nó không có nghĩa rằng một field object lồng nhau tự động được parse từ JSON part. Nếu một part chứa JSON độc lập, dùng `@RequestPart` để Spring chọn `HttpMessageConverter` theo content type của part.

### 3.2. Mô tả các trường thông thường trong OpenAPI

Một request body multipart có thể mô tả cả trường văn bản và tệp:

```yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required:
          - title
          - file
        properties:
          title:
            type: string
            description: Tiêu đề tài liệu
          description:
            type: string
            description: Ghi chú tùy chọn
          file:
            type: string
            format: binary
```

Danh sách `required` thể hiện các part bắt buộc. Nó cần khớp với logic binding và validation của server. Nếu `file` có thể vắng mặt, không đưa nó vào `required`; nếu controller bắt buộc file, hãy mô tả điều đó trong schema và kiểm tra runtime.

## 4. Nhận metadata JSON và file trong cùng request

Khi metadata có nhiều thuộc tính hoặc cấu trúc lồng nhau, nên gửi metadata như một JSON part riêng. Dùng `@RequestPart` cho cả metadata và file:

```java
public record DocumentMetadata(
        @NotBlank String title,
        @NotBlank String category,
        String reference
) {}
```

```java
@PostMapping(
        path = "/api/documents/import",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
DocumentResponse importDocument(
        @Valid @RequestPart("metadata") DocumentMetadata metadata,
        @RequestPart("file") MultipartFile file) {
    return documentService.importDocument(metadata, file);
}
```

Spring dùng content type của từng part để chọn cách chuyển đổi. Part `metadata` cần có `Content-Type: application/json` để được chuyển thành `DocumentMetadata` qua JSON message converter. Part `file` được bind thành `MultipartFile`.

Ví dụ gọi bằng curl:

```bash
curl -X POST http://localhost:8080/api/documents/import \
  -F 'metadata={"title":"Hợp đồng mua bán","category":"LEGAL","reference":"HD-2026-001"};type=application/json' \
  -F 'file=@./contract.pdf;type=application/pdf'
```

Nếu part `metadata` bị gửi thành `text/plain` hoặc thiếu content type phù hợp, Spring có thể không tìm được converter để chuyển thành DTO và trả lỗi `415 Unsupported Media Type` hoặc lỗi chuyển đổi nội dung. Hãy kiểm tra header của từng part khi debug.

### 4.1. Mô tả content type của từng part bằng `encoding`

OpenAPI dùng `encoding` bên trong Media Type Object để mô tả cách mã hóa từng property của multipart body. Ví dụ:

```yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required:
          - metadata
          - file
        properties:
          metadata:
            $ref: '#/components/schemas/DocumentMetadata'
          file:
            type: string
            format: binary
      encoding:
        metadata:
          contentType: application/json
        file:
          contentType: application/pdf, image/png
```

`encoding.metadata.contentType` nói rõ part `metadata` là JSON. `encoding.file.contentType` giới hạn các loại media type mà tài liệu mong đợi cho part tệp. Danh sách media type được phân cách bằng dấu phẩy. Server vẫn cần kiểm tra loại nội dung thực tế và nội dung file; không nên chỉ tin vào `Content-Type` do client gửi.

Có thể bổ sung schema metadata dùng chung:

```yaml
components:
  schemas:
    DocumentMetadata:
      type: object
      required:
        - title
        - category
      properties:
        title:
          type: string
        category:
          type: string
          enum: [LEGAL, FINANCE, OTHER]
        reference:
          type: string
```

### 4.2. Khai báo encoding trong annotation Swagger

Khi cần điều chỉnh tài liệu do springdoc sinh ra, có thể khai báo request body bằng Swagger Annotations. Ví dụ dưới đây dùng một schema đại diện cho multipart form:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Encoding;
import io.swagger.v3.oas.annotations.media.Schema;

@Operation(
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
            schema = @Schema(implementation = DocumentMultipartSchema.class),
            encoding = {
                @Encoding(
                    name = "metadata",
                    contentType = MediaType.APPLICATION_JSON_VALUE
                ),
                @Encoding(
                    name = "file",
                    contentType = "application/pdf, image/png"
                )
            }
        )
    )
)
@PostMapping(
    path = "/api/documents/import",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
DocumentResponse importDocument(
        @Valid @RequestPart("metadata") DocumentMetadata metadata,
        @RequestPart("file") MultipartFile file) {
    return documentService.importDocument(metadata, file);
}
```

Schema đại diện có thể khai báo riêng để kiểm soát cấu trúc tài liệu:

```java
public class DocumentMultipartSchema {
    @Schema(description = "Metadata của tài liệu")
    private DocumentMetadata metadata;

    @Schema(type = "string", format = "binary")
    private MultipartFile file;
}
```

Đây là metadata OpenAPI; class schema đại diện không nhất thiết là object được Spring bind trực tiếp. Controller vẫn nhận các part theo tham số `@RequestPart`. Sau khi thêm annotation, luôn kiểm tra `/v3/api-docs` để chắc chắn schema và `encoding` được sinh ra đúng, vì cấu trúc đầu vào và annotation có thể ảnh hưởng kết quả suy luận.

## 5. Upload nhiều tệp

HTML form có thể gửi nhiều file bằng một input có thuộc tính `multiple`:

```html
<input type="file" name="files" multiple>
```

Client gửi mỗi file thành một part riêng có cùng tên `files`. Với Spring MVC, có thể nhận chúng bằng `List<MultipartFile>`:

```java
@PostMapping(
        path = "/api/documents/batch",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
BatchUploadResponse uploadMany(
        @RequestPart("files") List<MultipartFile> files) {
    return documentService.storeAll(files);
}
```

Request có thể chứa nhiều part cùng tên:

```text
Content-Disposition: form-data; name="files"; filename="a.pdf"
...
Content-Disposition: form-data; name="files"; filename="b.pdf"
...
Content-Disposition: form-data; name="files"; filename="c.pdf"
...
```

Trong OpenAPI, mảng file được mô tả bằng array có item `string/binary`:

```yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required:
          - files
        properties:
          files:
            type: array
            items:
              type: string
              format: binary
```

Nếu cần mô tả bằng annotation trên schema DTO:

```java
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;

public class BatchUploadSchema {
    @ArraySchema(
        schema = @Schema(type = "string", format = "binary"),
        arraySchema = @Schema(description = "Danh sách tệp cần tải lên")
    )
    private List<MultipartFile> files;
}
```

Mỗi phần tử trong array tương ứng một part có cùng tên. Trong annotation, `@ArraySchema` giúp mô tả kiểu phần tử và metadata của mảng. Hãy kiểm tra JSON OpenAPI sau khi sinh vì phiên bản Swagger Annotations có thể ảnh hưởng cách annotation được biểu diễn.

Gọi bằng curl bằng cách lặp lại cùng field name:

```bash
curl -X POST http://localhost:8080/api/documents/batch \
  -F 'files=@./contract-a.pdf;type=application/pdf' \
  -F 'files=@./contract-b.pdf;type=application/pdf' \
  -F 'files=@./contract-c.pdf;type=application/pdf'
```

Không gửi ba file thành một chuỗi tên file duy nhất. Mỗi file phải được truyền thành một part riêng theo tên mà controller khai báo.

## 6. Nhiều tệp cùng các trường dữ liệu

Một endpoint batch thường cần một số trường chung cho toàn bộ lô upload, metadata riêng cho từng file hoặc cả hai. Ví dụ đơn giản với trường `folderId`, ghi chú và danh sách file:

```java
@PostMapping(
        path = "/api/folders/{folderId}/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
BatchUploadResponse uploadToFolder(
        @PathVariable UUID folderId,
        @RequestParam("note") String note,
        @RequestPart("files") List<MultipartFile> files) {
    return documentService.storeAll(folderId, note, files);
}
```

OpenAPI body mô tả `note` và `files` trong cùng object:

```yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required: [note, files]
        properties:
          note:
            type: string
          files:
            type: array
            items:
              type: string
              format: binary
```

`folderId` nằm trong path nên được mô tả là path parameter, không nằm trong multipart request body. Khi thiết kế schema, hãy giữ đúng ranh giới giữa path/query parameter và các part trong body.

Nếu mỗi file có metadata riêng, có thể dùng cấu trúc JSON part chứa danh sách metadata và một danh sách file, nhưng cần quy ước cách ghép metadata với file, chẳng hạn theo thứ tự hoặc theo một client-generated ID. Multipart không tự bảo đảm quan hệ ghép giữa hai danh sách độc lập.

## 7. Phân biệt `@RequestParam`, `@RequestPart` và `@ModelAttribute`

Ba cơ chế này có vai trò gần nhau nhưng không giống nhau trong Spring MVC:

| Cơ chế | Dùng khi nào | Cách chuyển đổi |
|---|---|---|
| `@RequestParam` | Trường form đơn giản hoặc file part cần lấy theo tên | Binding và type conversion của Spring. |
| `@RequestPart` | Một part cụ thể, đặc biệt là JSON/XML hoặc dữ liệu cần message converter | Chọn `HttpMessageConverter` theo content type của part. |
| `@ModelAttribute` | Nhiều trường form được gom vào một DTO, có thể gồm `MultipartFile` | Data binding vào các property theo tên. |

Ví dụ lựa chọn:

- `title` là chuỗi đơn: `@RequestParam("title") String title`.
- `file` là một file upload: `@RequestPart("file") MultipartFile file` hoặc `@RequestParam("file") MultipartFile file`.
- `metadata` là JSON object: `@RequestPart("metadata") DocumentMetadata metadata`.
- Nhiều trường form và file đơn giản: `@ModelAttribute DocumentUploadForm form`.

Không nên dùng `@RequestBody` cho một DTO JSON thông thường khi endpoint thực tế nhận `multipart/form-data`. `@RequestBody` thường đọc toàn bộ request body qua một message converter; với multipart, hãy dùng `@RequestPart`, `@RequestParam` hoặc `@ModelAttribute` phù hợp với từng phần.

## 8. Spring MVC và Spring WebFlux

Spring MVC dựa trên Servlet API và thường dùng `MultipartFile`. Spring WebFlux có mô hình multipart reactive, thường dùng `FilePart` hoặc `Part`.

Ví dụ WebFlux:

```java
@PostMapping(
        path = "/api/documents/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<DocumentResponse> upload(
        @RequestPart("file") FilePart file) {
    return documentService.store(file);
}
```

`FilePart` cho phép xử lý nội dung theo kiểu reactive. Với file lớn, nên cân nhắc cách ghi nội dung theo stream để tránh nạp toàn bộ dữ liệu vào bộ nhớ. Các kiểu `MultipartFile` thuộc stack Servlet MVC; không dùng chúng như kiểu mặc định cho WebFlux.

Trong WebFlux, `@RequestParam` chủ yếu dành cho query parameter. Để đọc multipart part, dùng `@RequestPart` hoặc cơ chế `Part`/`Flux<Part>` tương ứng. Không sao chép nguyên cách binding form của Spring MVC sang WebFlux mà không kiểm tra API của framework đang chạy.

Starter springdoc cũng phải khớp với web stack: `springdoc-openapi-starter-webmvc-ui` hoặc `springdoc-openapi-starter-webmvc-api` cho MVC; `springdoc-openapi-starter-webflux-ui` hoặc `springdoc-openapi-starter-webflux-api` cho WebFlux.

## 9. Giới hạn kích thước và kiểm tra file

Tài liệu OpenAPI mô tả loại dữ liệu và có thể mô tả một số giới hạn, nhưng server phải thực thi giới hạn upload ở runtime. Với Spring Boot dùng Servlet MVC, có thể cấu hình kích thước file và tổng request:

```yaml
spring:
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 25MB
```

`max-file-size` giới hạn kích thước một file; `max-request-size` giới hạn toàn bộ multipart request, bao gồm các file và part khác. Tổng request cần lớn hơn hoặc bằng tổng payload dự kiến cộng overhead multipart.

Ngoài giới hạn framework, ứng dụng nên kiểm tra:

- Tệp có rỗng hay không và số lượng file tối đa.
- Phần mở rộng, media type và chữ ký nội dung thực tế của file.
- Tên file do client gửi; không dùng trực tiếp làm đường dẫn lưu trữ.
- Quyền của người upload và quyền truy cập tài nguyên đích.
- Quy trình quét malware hoặc kiểm tra nội dung theo chính sách hệ thống.
- Vị trí lưu trữ, thời gian lưu và cách xóa file tạm khi có lỗi.

`Content-Type` của part do client gửi có thể không đáng tin cậy. Nếu nghiệp vụ chỉ chấp nhận PDF hoặc PNG, hãy xác minh nội dung thật ở server; khai báo `encoding.contentType` trong OpenAPI chỉ giúp mô tả hợp đồng và hỗ trợ client.

## 10. Validation cho multipart request

Các trường metadata có thể dùng Bean Validation. Với JSON part, đặt `@Valid` trước `@RequestPart`:

```java
@PostMapping(
        path = "/api/documents/import",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
DocumentResponse importDocument(
        @Valid @RequestPart("metadata") DocumentMetadata metadata,
        @RequestPart("file") MultipartFile file) {

    if (file.isEmpty()) {
        throw new InvalidUploadException("Tệp không được để trống");
    }
    return documentService.importDocument(metadata, file);
}
```

Với DTO form dùng `@ModelAttribute`, đặt `@Valid` trên tham số DTO để kiểm tra các field có annotation validation. Các ràng buộc như `@NotBlank`, `@Size` hoặc `@Pattern` có thể mô tả trường văn bản; kích thước file và số lượng file cần được kiểm tra bằng logic phù hợp hoặc custom validator.

OpenAPI có thể thể hiện một số ràng buộc trong schema, ví dụ `minItems`, `maxItems`, `minLength` hoặc `maxLength`. Không phải mọi ràng buộc nghiệp vụ của file đều có thể biểu diễn đầy đủ trong schema. Hãy mô tả thêm giới hạn, định dạng chấp nhận và lỗi có thể xảy ra trong operation/response.

## 11. Kiểm tra tài liệu OpenAPI được springdoc sinh ra

Sau khi khai báo endpoint multipart, mở `/v3/api-docs` hoặc endpoint đã cấu hình và kiểm tra:

1. Request body có media type `multipart/form-data`.
2. Tên property trùng với tên part mà controller nhận.
3. File đơn có schema `type: string`, `format: binary`.
4. Nhiều file có schema `type: array` và `items` là `string/binary`.
5. Trường văn bản có kiểu và trạng thái required/optional chính xác.
6. JSON part có schema đúng và `encoding` khai báo `application/json` nếu cần.
7. Content type được phép của file được mô tả phù hợp.

Ví dụ một request body mong muốn:

```yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required:
          - metadata
          - files
        properties:
          metadata:
            $ref: '#/components/schemas/DocumentMetadata'
          files:
            type: array
            items:
              type: string
              format: binary
      encoding:
        metadata:
          contentType: application/json
        files:
          contentType: application/pdf, image/png
```

Nếu springdoc sinh `application/json` thay vì `multipart/form-data`, kiểm tra `consumes` trên mapping và annotation request body. Nếu file xuất hiện như object có các field nội bộ thay vì `string/binary`, hãy khai báo schema tường minh bằng Swagger Annotations và kiểm tra lại output.

## 12. Kiểm thử endpoint upload

### 12.1. Kiểm thử bằng curl

Một file cùng trường văn bản:

```bash
curl -X POST http://localhost:8080/api/documents \
  -F 'title=Hợp đồng mua bán' \
  -F 'description=Bản đã ký' \
  -F 'file=@./contract.pdf;type=application/pdf'
```

Metadata JSON cùng file:

```bash
curl -X POST http://localhost:8080/api/documents/import \
  -F 'metadata={"title":"Hợp đồng","category":"LEGAL"};type=application/json' \
  -F 'file=@./contract.pdf;type=application/pdf'
```

Nhiều file:

```bash
curl -X POST http://localhost:8080/api/documents/batch \
  -F 'files=@./a.pdf;type=application/pdf' \
  -F 'files=@./b.png;type=image/png'
```

Khi dùng `curl -F`, curl tự tạo boundary và header multipart. Trong trình duyệt, khi gửi `FormData` bằng `fetch`, cũng không tự đặt header `Content-Type: multipart/form-data`; để trình duyệt thêm boundary chính xác.

### 12.2. Kiểm thử bằng MockMvc

Spring MVC test hỗ trợ tạo multipart request bằng `MockMultipartFile`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class DocumentUploadTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void uploadsOneFileWithTextFields() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "contract.pdf",
                MediaType.APPLICATION_PDF_VALUE,
                "sample-pdf-content".getBytes(StandardCharsets.UTF_8)
        );

        mockMvc.perform(multipart("/api/documents")
                        .file(file)
                        .param("title", "Hợp đồng mua bán")
                        .param("description", "Bản đã ký"))
                .andExpect(status().isOk());
    }
}
```

Với metadata JSON, tạo một multipart part có content type `application/json`:

```java
MockMultipartFile metadata = new MockMultipartFile(
        "metadata",
        "",
        MediaType.APPLICATION_JSON_VALUE,
        "{\"title\":\"Hợp đồng\",\"category\":\"LEGAL\"}"
                .getBytes(StandardCharsets.UTF_8)
);

MockMultipartFile file = new MockMultipartFile(
        "file", "contract.pdf", MediaType.APPLICATION_PDF_VALUE,
        "sample-pdf-content".getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/documents/import")
                .file(metadata)
                .file(file))
        .andExpect(status().isOk());
```

Với nhiều file, thêm nhiều `MockMultipartFile` có cùng tên `files`:

```java
mockMvc.perform(multipart("/api/documents/batch")
                .file(new MockMultipartFile(
                        "files", "a.pdf", MediaType.APPLICATION_PDF_VALUE,
                        new byte[]{1, 2, 3}))
                .file(new MockMultipartFile(
                        "files", "b.pdf", MediaType.APPLICATION_PDF_VALUE,
                        new byte[]{4, 5, 6})))
        .andExpect(status().isOk());
```

Các đoạn test trên minh họa cách dựng request. Trong dự án thật, bổ sung assertion về số lượng file, tên file, nội dung đã lưu, metadata đã bind và các trường hợp lỗi như thiếu part, sai content type, file rỗng hoặc vượt giới hạn.

## 13. Những lỗi thường gặp

- **Quên `consumes = multipart/form-data`**: mapping có thể không khớp request hoặc tài liệu sinh sai media type. Khai báo rõ `consumes` cho endpoint upload.
- **Tên part không khớp**: controller nhận `@RequestPart("file")` nhưng client gửi `document`; Spring không tìm thấy part cần thiết.
- **Gửi metadata JSON như text/plain**: message converter không thể chuyển part thành DTO. Gửi đúng `Content-Type: application/json` cho part.
- **Dùng `@RequestBody` cho toàn bộ multipart**: chọn `@RequestPart`, `@RequestParam` hoặc `@ModelAttribute` theo từng phần.
- **Mô tả nhiều file thành một chuỗi**: dùng array `string/binary` và gửi nhiều part cùng tên.
- **Đặt `Content-Type` thủ công khi gửi FormData**: có thể làm thiếu boundary; để browser hoặc HTTP client tạo header.
- **Tin `Content-Type` hoặc filename từ client**: kiểm tra nội dung file và chuẩn hóa tên file ở server.
- **Không giới hạn dung lượng request**: cấu hình giới hạn upload và xử lý lỗi vượt ngưỡng.
- **Dùng `MultipartFile` trong WebFlux**: dùng `FilePart`/`Part` theo reactive stack.
- **Chỉ kiểm tra Swagger UI**: gọi endpoint bằng curl hoặc integration test và đối chiếu `/v3/api-docs`.

## 14. Quy trình thiết kế multipart API

1. **Liệt kê từng part**: tên, vai trò, kiểu dữ liệu, bắt buộc hay tùy chọn.
2. **Chọn binding phù hợp**: `@RequestParam` cho trường đơn, `@RequestPart` cho file/JSON part, `@ModelAttribute` cho form DTO.
3. **Khai báo media type**: endpoint dùng `multipart/form-data`; từng part có content type đúng.
4. **Mô tả schema OpenAPI**: file là `string/binary`, nhiều file là array, metadata tham chiếu schema DTO.
5. **Bổ sung Encoding Object**: đặt `contentType` cho JSON part và giới hạn loại file khi cần.
6. **Kiểm tra giới hạn và validation**: kích thước, số lượng, định dạng, nội dung và quyền upload.
7. **Kiểm tra tài liệu sinh ra**: xác nhận `requestBody`, property, `required`, schema và encoding.
8. **Kiểm thử request thật**: dùng curl, MockMvc/WebTestClient và consumer thực tế.

## 15. Checklist review

- [ ] Mapping khai báo `consumes = multipart/form-data`.
- [ ] Tên part trong client trùng với `@RequestPart`, `@RequestParam` hoặc property DTO.
- [ ] Tệp đơn được mô tả bằng `type: string`, `format: binary`.
- [ ] Nhiều tệp được mô tả bằng array của `string/binary` và gửi bằng nhiều part cùng tên.
- [ ] Trường văn bản có schema và trạng thái required/optional chính xác.
- [ ] JSON metadata dùng part `application/json` và được bind bằng `@RequestPart`.
- [ ] `encoding` mô tả đúng content type của từng part khi cần.
- [ ] Spring MVC dùng `MultipartFile`; WebFlux dùng `FilePart`/`Part` phù hợp.
- [ ] Giới hạn kích thước file và tổng request được cấu hình.
- [ ] File được kiểm tra nội dung, quyền truy cập và tên lưu trữ ở server.
- [ ] `/v3/api-docs` thể hiện đúng multipart request body.
- [ ] Integration test bao phủ upload đơn, nhiều file, metadata và trường hợp lỗi.

## 16. Tài liệu tham khảo

- [OpenAPI Specification 3.1.2 – Request Body Object](https://spec.openapis.org/oas/v3.1.2.html#request-body-object)
- [OpenAPI Specification 3.1.2 – Encoding Object](https://spec.openapis.org/oas/v3.1.2.html#encoding-object)
- [OpenAPI Specification 3.1.2 – File Upload](https://spec.openapis.org/oas/v3.1.2.html#considerations-for-file-uploads)
- [Spring Framework – Multipart Forms](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework – Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html)
- [Spring Boot – Servlet Web Applications and Multipart Properties](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [springdoc-openapi FAQ](https://springdoc.org/faq.html)

Một multipart contract tốt phải mô tả chính xác từng part và cách client gửi chúng. Hãy để OpenAPI thể hiện tên, schema, số lượng và content type; để Spring binding nhận đúng định dạng đó; rồi kiểm chứng bằng request integration test. Nhờ vậy, upload một file, nhiều file và metadata có thể được tích hợp nhất quán giữa Swagger UI, SDK và ứng dụng Spring Boot.
