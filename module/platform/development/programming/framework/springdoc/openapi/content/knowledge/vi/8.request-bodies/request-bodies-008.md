# `@RequestPart` cho một phần JSON trong multipart

Một API tải tệp thường cần nhận đồng thời dữ liệu có cấu trúc và nội dung nhị phân. Ví dụ, người dùng gửi thông tin tài liệu như tiêu đề, loại tài liệu và ngày hiệu lực dưới dạng JSON, kèm một tệp PDF. Với Spring MVC, có thể khai báo từng phần bằng `@RequestPart`: Spring dùng `HttpMessageConverter` để chuyển phần JSON thành object Java và bind phần tệp thành `MultipartFile`.

Khi dùng `springdoc-openapi`, cần mô tả request body là `multipart/form-data`, trong đó mỗi phần là một thuộc tính của schema. Phần JSON cần được công bố với content type `application/json`; phần tệp cần schema `string` với format `binary`. Hai mô tả này giúp Swagger UI và client generator hiểu cấu trúc multipart.

## 1. Multipart gồm nhiều phần có kiểu nội dung riêng

Một request `multipart/form-data` được chia thành nhiều part. Mỗi part có tên, header riêng và nội dung riêng. Trình duyệt hoặc HTTP client gửi một boundary để phân tách các phần.

Ví dụ request tải tài liệu có hai part:

| Tên part | Content-Type | Nội dung | Kiểu Java nhận |
| --- | --- | --- | --- |
| `metadata` | `application/json` | JSON gồm tiêu đề, loại tài liệu và thông tin nghiệp vụ | `DocumentMetadata` |
| `file` | `application/pdf` hoặc loại tệp được hỗ trợ | Byte của tệp được tải lên | `MultipartFile` |

HTTP request tổng thể có media type `multipart/form-data`. Từng part có thể có media type khác nhau. Đây là lý do phần JSON cần được gửi kèm `Content-Type: application/json` để Spring chọn converter JSON phù hợp.

## 2. Phân biệt `@RequestPart` và `@RequestParam`

Hai annotation có thể xuất hiện trong cùng một endpoint nhưng phục vụ cách bind dữ liệu khác nhau:

| Annotation | Cách xử lý chính | Trường hợp phù hợp |
| --- | --- | --- |
| `@RequestPart` | Đọc part và dùng `HttpMessageConverter` theo content type của part để chuyển thành kiểu đích | JSON/XML hoặc nội dung có cấu trúc trong multipart; tệp được bind thành `MultipartFile`. |
| `@RequestParam` | Bind request parameter hoặc multipart field qua cơ chế chuyển đổi của Spring | Trường đơn giản như `String`, số, Boolean; cũng có thể dùng với `MultipartFile`. |

Với một phần JSON cần deserialize thành DTO và áp dụng Bean Validation, `@RequestPart` thể hiện rõ ý định hơn:

```java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
ResponseEntity<Void> upload(
    @Valid @RequestPart("metadata") DocumentMetadata metadata,
    @RequestPart("file") MultipartFile file
) {
    documentService.upload(metadata, file);
    return ResponseEntity.accepted().build();
}
```

Spring đọc part có tên `metadata`, xem `Content-Type` của part, rồi dùng converter tương ứng để tạo `DocumentMetadata`. Part `file` được bind thành `MultipartFile`. Nếu gửi JSON dưới dạng một chuỗi thông thường với `@RequestParam String metadata`, ứng dụng phải tự parse chuỗi đó; khi cần deserialize JSON trực tiếp, `@RequestPart` là lựa chọn tự nhiên hơn.

## 3. Tạo DTO cho phần JSON

Định nghĩa DTO mô tả metadata cần gửi:

```java
public enum DocumentCategory {
    CONTRACT,
    INVOICE,
    REPORT
}

public record DocumentMetadata(
    @NotBlank
    @Size(max = 120)
    String title,

    @NotNull
    DocumentCategory category,

    @PastOrPresent
    LocalDate effectiveDate
) {}
```

Khi part JSON được chuyển thành DTO, Jackson xử lý deserialize và Bean Validation kiểm tra các constraint nếu controller gắn `@Valid` và ứng dụng đã cấu hình validation provider. `@NotBlank`, `@Size`, `@NotNull` và `@PastOrPresent` mô tả điều kiện dữ liệu ở runtime; springdoc có thể phản ánh một số constraint vào schema OpenAPI.

Part JSON phải có cấu trúc phù hợp với DTO, ví dụ:

```json
{
  "title": "Hợp đồng mua bán",
  "category": "CONTRACT",
  "effectiveDate": "2026-11-20"
}
```

Nếu `effectiveDate` được gửi dưới dạng chuỗi ngày, cấu hình Java Time của Jackson phải hỗ trợ `LocalDate`. Định dạng JSON và định dạng query parameter có cơ chế chuyển đổi khác nhau; `@DateTimeFormat` trên tham số query không thay thế cấu hình Jackson cho JSON body.

## 4. Khai báo controller nhận JSON part và file part

Một endpoint Spring MVC có thể nhận hai part như sau:

```java
@RestController
@RequestMapping("/api/documents")
class DocumentController {

    private final DocumentService documentService;

    DocumentController(DocumentService documentService) {
        this.documentService = documentService;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(summary = "Tải tài liệu kèm metadata JSON")
    ResponseEntity<DocumentResponse> upload(
        @Valid @RequestPart("metadata") DocumentMetadata metadata,
        @RequestPart("file") MultipartFile file
    ) {
        DocumentResponse created = documentService.upload(metadata, file);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

Các chi tiết quan trọng:

- `consumes = MediaType.MULTIPART_FORM_DATA_VALUE` giới hạn endpoint nhận request tổng thể có media type multipart/form-data.
- `@RequestPart("metadata")` yêu cầu một part tên `metadata`; Spring chuyển JSON part thành `DocumentMetadata`.
- `@Valid` kích hoạt validation cho DTO sau khi deserialize thành công, với điều kiện method validation/Bean Validation được cấu hình phù hợp.
- `@RequestPart("file")` bind part có tên `file` thành `MultipartFile`.
- `HttpStatus.CREATED` quyết định response thực tế; annotation OpenAPI sẽ mô tả response tương ứng cho client.

Tên trong `@RequestPart` phải khớp chính xác tên part mà client gửi. Nếu client gửi `document` nhưng controller đợi `metadata`, Spring không tìm thấy part và request sẽ thất bại.

## 5. Mô tả schema multipart trong OpenAPI

Springdoc có thể suy luận request body từ tham số `@RequestPart` và `MultipartFile`. Với trường hợp có một part JSON object, nên kiểm tra đặc tả sinh ra để bảo đảm schema và encoding đúng. Có thể khai báo tường minh request body bằng annotation OpenAPI.

Tạo một model chỉ dùng để mô tả hình dạng multipart:

```java
@Schema(name = "UploadDocumentMultipart")
public class UploadDocumentMultipartSchema {

    @Schema(description = "Metadata của tài liệu, gửi dưới dạng JSON")
    public DocumentMetadata metadata;

    @Schema(
        description = "Tệp tài liệu nhị phân",
        type = "string",
        format = "binary"
    )
    public String file;
}
```

Model này là schema phục vụ tài liệu. Controller vẫn bind dữ liệu bằng `@RequestPart` và `MultipartFile`; trường `file` kiểu `String` trong model không phải tham số Java được dùng để đọc byte của tệp.

Khai báo request body và encoding:

```java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
@Operation(
    summary = "Tải tài liệu kèm metadata JSON",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        description = "Gửi metadata dưới dạng JSON và nội dung tệp trong cùng request",
        content = @Content(
            mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
            schema = @Schema(implementation = UploadDocumentMultipartSchema.class),
            encoding = @Encoding(
                name = "metadata",
                contentType = MediaType.APPLICATION_JSON_VALUE
            )
        )
    )
)
ResponseEntity<DocumentResponse> upload(
    @Valid @RequestPart("metadata") DocumentMetadata metadata,
    @RequestPart("file") MultipartFile file
) {
    DocumentResponse created = documentService.upload(metadata, file);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
```

Trong đó:

- `@Content(mediaType = "multipart/form-data")` xác định media type của toàn request body.
- `@Schema(implementation = UploadDocumentMultipartSchema.class)` công bố object schema gồm `metadata` và `file`.
- `@Encoding(name = "metadata", contentType = "application/json")` mô tả part `metadata` chứa JSON.
- `format = "binary"` cho biết thuộc tính `file` là nội dung tệp nhị phân.

Các annotation OpenAPI nằm trong `io.swagger.v3.oas.annotations.*`. Tên annotation `@RequestBody` của OpenAPI khác với `org.springframework.web.bind.annotation.RequestBody`; trong ví dụ đã dùng tên đầy đủ để tránh nhầm lẫn.

Đặc tả OpenAPI thường có cấu trúc tương tự:

```yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        properties:
          metadata:
            $ref: '#/components/schemas/DocumentMetadata'
          file:
            type: string
            format: binary
      encoding:
        metadata:
          contentType: application/json
```

Điều cần kiểm tra là schema có đúng tên part, đúng kiểu object/binary và encoding JSON cho `metadata`. Tên component hoặc cách springdoc tách schema có thể khác theo cấu hình; cấu trúc trên thể hiện các thông tin quan trọng cần có.

## 6. Gửi request bằng curl

Có thể kiểm tra endpoint từ terminal bằng `curl`:

```bash
curl -X POST "http://localhost:8080/api/documents" \
  -F 'metadata={"title":"Hợp đồng mua bán","category":"CONTRACT","effectiveDate":"2026-11-20"};type=application/json' \
  -F 'file=@contract.pdf;type=application/pdf'
```

Tùy chọn `-F` tạo các part của multipart request. Phần `metadata` được gắn `type=application/json`, để Spring chọn JSON message converter. Phần `file` đọc nội dung từ `contract.pdf` và gắn content type của tệp.

Không tự đặt header tổng `Content-Type: multipart/form-data` bằng tay khi dùng `curl -F`. Curl phải tự tạo header có `boundary` và dùng cùng boundary đó để phân tách các part. Nếu ghi đè header mà không cung cấp boundary phù hợp, server có thể không parse được request.

## 7. Hiển thị multipart trong Swagger UI

Khi OpenAPI mô tả request body là `multipart/form-data` với schema object, Swagger UI có thể hiển thị các trường của form. Thuộc tính `file` có `type: string` và `format: binary` thường được trình bày dưới dạng bộ chọn tệp. Thuộc tính `metadata` là object; encoding `application/json` cho biết part này chứa JSON.

Giao diện nhập liệu cụ thể phụ thuộc phiên bản Swagger UI đi kèm và cách schema được sinh. Sau khi khai báo, hãy mở Swagger UI và kiểm tra:

1. Operation hiển thị media type `multipart/form-data`.
2. Có trường chọn tệp cho part `file`.
3. Có thể nhập dữ liệu JSON hợp lệ cho part `metadata` theo cách UI hỗ trợ.
4. Request gửi đi có tên part đúng và metadata part có `Content-Type: application/json`.
5. Server bind được DTO và `MultipartFile` như mong đợi.

Nếu giao diện không tạo được trường JSON object như mong muốn, hãy kiểm tra `/v3/api-docs` trước. Nếu schema và `encoding` đã đúng, khác biệt có thể nằm ở khả năng nhập multipart của phiên bản Swagger UI. Có thể dùng `curl` hoặc HTTP client để xác minh server độc lập với giao diện.

## 8. Validation và giới hạn tệp

JSON part và file part cần được kiểm tra riêng vì chúng có đặc điểm khác nhau.

Với metadata, dùng Bean Validation trên DTO:

```java
public record DocumentMetadata(
    @NotBlank @Size(max = 120) String title,
    @NotNull DocumentCategory category
) {}
```

Với tệp, kiểm tra ít nhất:

- Tệp có rỗng hay không (`file.isEmpty()`).
- Kích thước có vượt giới hạn nghiệp vụ hay không (`file.getSize()`).
- Tên tệp và phần mở rộng có phù hợp chính sách hay không.
- Content type có thuộc danh sách chấp nhận hay không.
- Nội dung thực tế có khớp định dạng được phép hay không; không tin hoàn toàn vào tên tệp hoặc header do client gửi.

Ví dụ kiểm tra cơ bản trong service:

```java
void validateFile(MultipartFile file) {
    if (file.isEmpty()) {
        throw new InvalidUploadException("Tệp không được để trống");
    }

    if (file.getSize() > 10 * 1024 * 1024) {
        throw new InvalidUploadException("Tệp vượt quá 10 MB");
    }

    if (!MediaType.APPLICATION_PDF_VALUE.equals(file.getContentType())) {
        throw new InvalidUploadException("Chỉ chấp nhận PDF");
    }
}
```

Đây chỉ là kiểm tra cơ bản. `getContentType()` lấy thông tin do client cung cấp và có thể giả mạo; hệ thống cần kiểm tra chữ ký tệp hoặc dùng thư viện phân tích định dạng phù hợp trước khi xử lý nội dung. Giới hạn multipart tổng thể cũng nên được cấu hình ở Spring Boot, ví dụ `spring.servlet.multipart.max-file-size` và `spring.servlet.multipart.max-request-size` trong ứng dụng MVC servlet.

## 9. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Thiếu part `metadata` | Tên part không khớp với `@RequestPart` | Đồng bộ tên trong controller, client và schema OpenAPI. |
| JSON part không deserialize được | Part không có `Content-Type: application/json`, JSON sai cú pháp hoặc DTO không tương thích | Kiểm tra header part, payload và Jackson configuration. |
| Nhận lỗi 415 Unsupported Media Type | Không có converter phù hợp với content type của part hoặc request tổng | Kiểm tra `consumes`, content type từng part và message converter. |
| Nhận lỗi 400 Bad Request | Thiếu part bắt buộc, JSON không hợp lệ hoặc validation thất bại | Kiểm tra request, `@Valid` và cách ứng dụng ánh xạ lỗi. |
| Swagger UI hiển thị file như chuỗi thường | Schema file thiếu `format: binary` | Khai báo thuộc tính file là `type: string`, `format: binary`. |
| Swagger UI gửi metadata như text/plain | Encoding cho part JSON chưa được mô tả hoặc UI không hỗ trợ đúng cách | Kiểm tra `encoding.metadata.contentType` trong OpenAPI và thử bằng curl. |
| Request vượt giới hạn kích thước | Cấu hình multipart hoặc giới hạn gateway/proxy thấp hơn kích thước tệp | Đồng bộ giới hạn ở ứng dụng, reverse proxy và hạ tầng. |

## 10. Nguyên tắc áp dụng

- Dùng `consumes = multipart/form-data` cho endpoint nhận nhiều part.
- Dùng `@RequestPart` khi cần chuyển part JSON thành DTO qua `HttpMessageConverter`.
- Gắn `@Valid` cho DTO JSON và khai báo constraint phù hợp.
- Mô tả request body là object multipart; part tệp dùng `type: string`, `format: binary`.
- Dùng `@Encoding` để công bố `contentType` riêng cho part JSON.
- Kiểm tra `/v3/api-docs`, Swagger UI và request thực tế bằng HTTP client.
- Xác minh nội dung tệp và giới hạn dung lượng ở runtime; không dựa vào schema hoặc content type do client khai báo.

`@RequestPart` kết nối từng phần của multipart với kiểu Java tương ứng. Khi mô tả đúng schema và encoding trong OpenAPI, client có thể hiểu rõ phần JSON cần gửi, phần tệp cần chọn và content type của từng phần. Độ tin cậy của API vẫn phụ thuộc vào việc server deserialize, validate và kiểm tra tệp đúng như hợp đồng đã công bố.

## Tài liệu tham khảo

- [Spring Framework – Multipart Resolver and `@RequestPart`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [OpenAPI Specification – Multipart Request Body](https://spec.openapis.org/oas/latest.html)
- [Springdoc OpenAPI – tài liệu chính thức](https://springdoc.org/)
- [Swagger Annotations – `@Content`, `@Encoding` và `@Schema`](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
