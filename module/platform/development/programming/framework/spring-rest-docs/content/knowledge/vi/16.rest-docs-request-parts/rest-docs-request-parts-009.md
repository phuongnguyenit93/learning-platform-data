# Document lỗi kích thước hoặc loại file trong Spring REST Docs

## 1. Vì sao cần tài liệu hóa lỗi upload?

Một endpoint upload multipart thường giới hạn kích thước và loại file được chấp nhận. Ví dụ API nhận ảnh sản phẩm có thể chỉ cho phép PNG/JPEG, giới hạn mỗi file 5 MB và trả lỗi khi client gửi PDF hoặc file quá lớn.

Những quy tắc này là một phần của contract REST API. Client cần biết:
- Những loại file nào được hỗ trợ.
- Giới hạn dung lượng áp dụng cho từng file hoặc toàn request.
- Status HTTP nào được trả khi media type không hợp lệ hoặc payload vượt giới hạn.
- Cấu trúc response lỗi, mã lỗi ổn định và thông tin hữu ích để sửa request.

Trong **SPRING_REST_DOCS**, các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured tạo bằng chứng cho tài liệu. Với multipart upload, `requestParts(...)` mô tả các part của request; `responseFields(...)`, `responseHeaders(...)` và status snippet có thể mô tả kết quả lỗi. Một test lỗi có thể vừa xác nhận API phản hồi đúng, vừa sinh snippet để include vào Asciidoctor/Markdown.

Bài này hướng dẫn tài liệu hóa lỗi kích thước và loại file, tập trung vào hai tình huống thường gặp:

- `413 Payload Too Large` (tên reason phrase hiện dùng thường là **Content Too Large**) khi nội dung vượt giới hạn.
- `415 Unsupported Media Type` khi request hoặc một part dùng media type không được operation hỗ trợ.

Sau bài học, bạn có thể thiết kế contract upload, kiểm tra MIME type và kích thước, viết negative tests, tài liệu hóa error response và nhận biết giới hạn của MockMvc đối với lỗi xảy ra ở servlet container hoặc reverse proxy.

## 2. Thiết kế contract cho endpoint upload

Giả sử `POST /api/products/{productId}/assets` nhận một file ảnh và metadata JSON.

| Thành phần | Contract ví dụ |
| --- | --- |
| Part `file` | Bắt buộc, một file ảnh |
| Content-Type được chấp nhận | `image/png`, `image/jpeg` |
| Kích thước file tối đa | 5 MiB |
| Part `metadata` | Bắt buộc, `application/json` |
| Response thành công | `201 Created` |
| Media type không được hỗ trợ | `415 Unsupported Media Type` |
| File vượt giới hạn nghiệp vụ | `413 Content Too Large` |
| Cấu trúc response lỗi | `code`, `message`, `status`, `path` |

Các con số và status ở đây là **contract minh họa**. Dự án cần quy định rõ:
- Giới hạn tính theo byte, KiB/MiB hay đơn vị khác; nên dùng byte ở logic kiểm tra để tránh mơ hồ.
- Giới hạn áp dụng cho từng file hay tổng multipart request.
- Có tính overhead multipart và metadata vào giới hạn hay không.
- Danh sách media type được cho phép.
- Khi client khai báo MIME type hợp lệ nhưng bytes không đúng định dạng, API trả lỗi nào.
- Error code có ổn định qua các phiên bản hay không.

Ví dụ response lỗi:

```json
{
  "code": "FILE_TOO_LARGE",
  "message": "File must not exceed 5 MiB",
  "status": 413,
  "path": "/api/products/42/assets"
}
```

Với media type không được hỗ trợ:

```json
{
  "code": "UNSUPPORTED_FILE_TYPE",
  "message": "Only PNG and JPEG images are supported",
  "status": 415,
  "path": "/api/products/42/assets"
}
```

Nên dùng error code ổn định để client xử lý theo chương trình. Message có thể thay đổi để dễ hiểu hơn; client không nên phụ thuộc vào việc so khớp nguyên văn message.

## 3. Phân biệt Content-Type của request và của part

Multipart có Content-Type ở hai lớp:

```http
POST /api/products/42/assets HTTP/1.1
Content-Type: multipart/form-data; boundary=----UploadBoundary

------UploadBoundary
Content-Disposition: form-data; name="file"; filename="cover.png"
Content-Type: image/png

<binary bytes>
------UploadBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Bìa sách"}
------UploadBoundary--
```

- `multipart/form-data; boundary=...` là Content-Type của **toàn request**.
- `image/png` là Content-Type của **part file**.
- `application/json` là Content-Type của **part metadata**.

Nếu endpoint chỉ nhận multipart, `consumes` thường là `MediaType.MULTIPART_FORM_DATA_VALUE`. Điều này không tự giới hạn media type của từng part. Ứng dụng vẫn cần kiểm tra `file.getContentType()` hoặc sử dụng converter phù hợp cho part JSON.

Khi request tổng thể dùng loại không được endpoint hỗ trợ, Spring MVC có thể trả `415` trước khi controller được gọi. Khi part file có media type không hợp lệ, controller/service hoặc tầng chuyển đổi cần kiểm tra và ánh xạ lỗi theo contract. Hai trường hợp cùng có thể trả 415 nhưng khác nguyên nhân và thông tin lỗi.

## 4. Kiểm tra loại file: MIME type và nội dung thực tế

### 4.1. Content-Type do client khai báo

Với `MultipartFile`, ứng dụng có thể đọc giá trị được client khai báo:

```java
String declaredType = file.getContentType();
```

Ví dụ kiểm tra allowlist:

```java
private static final Set<String> ALLOWED_IMAGE_TYPES =
        Set.of("image/png", "image/jpeg");

void validateDeclaredMediaType(MultipartFile file) {
    String contentType = file.getContentType();

    if (contentType == null || !ALLOWED_IMAGE_TYPES.contains(contentType)) {
        throw new UnsupportedFileTypeException();
    }
}
```

Nên so khớp với allowlist rõ ràng thay vì chấp nhận mọi `image/*`. Giá trị MIME do client khai báo không chứng minh bytes thực sự có định dạng tương ứng.

### 4.2. Kiểm tra chữ ký hoặc parse nội dung

Một client có thể gửi file văn bản nhưng đặt header `Content-Type: image/png`. Nếu chỉ kiểm tra header, file giả có thể vượt qua kiểm tra.

Khi contract yêu cầu file thực sự là PNG hoặc JPEG, cần kiểm tra chữ ký file hoặc parse bằng thư viện phù hợp. Ví dụ khái niệm:

```java
void validateImageContent(byte[] bytes) {
    if (!imageSignatureDetector.isPng(bytes)
            && !imageSignatureDetector.isJpeg(bytes)) {
        throw new InvalidFileContentException();
    }
}
```

`imageSignatureDetector` là thành phần minh họa; chọn thư viện và quy tắc kiểm tra phù hợp với dự án. Kiểm tra magic bytes giúp nhận diện định dạng nhưng không thay thế mọi kiểm tra an toàn nội dung. Nếu cần xử lý ảnh thật, hãy thử decode để xác nhận file có cấu trúc hợp lệ và kiểm soát kích thước ảnh sau giải mã.

### 4.3. Đặt tên lỗi theo nguyên nhân

| Tình huống | Lỗi ví dụ | Status minh họa |
| --- | --- | --- |
| MIME type không nằm trong allowlist | `UNSUPPORTED_FILE_TYPE` | 415 |
| MIME khai báo hợp lệ nhưng bytes sai định dạng | `INVALID_FILE_CONTENT` | 400 |
| Kích thước file vượt giới hạn nghiệp vụ | `FILE_TOO_LARGE` | 413 |
| Metadata JSON sai cú pháp | `INVALID_METADATA` | 400 |
| Metadata part có Content-Type không phù hợp | `UNSUPPORTED_PART_MEDIA_TYPE` | 415 |

Status cho nội dung sai định dạng cần được quy định nhất quán. Một số API có thể dùng 422 cho nội dung không xử lý được; điều quan trọng là contract phải rõ và test xác nhận status/error code thực tế.

## 5. Kiểm tra kích thước file

`MultipartFile` cung cấp `getSize()` và `isEmpty()`. Có thể kiểm tra giới hạn theo byte:

```java
private static final long MAX_IMAGE_SIZE = 5L * 1024 * 1024;

void validateFileSize(MultipartFile file) {
    if (file.getSize() > MAX_IMAGE_SIZE) {
        throw new FileTooLargeException(MAX_IMAGE_SIZE);
    }
}
```

`5 MiB` bằng `5 * 1024 * 1024` byte. Phân biệt:
- File absent: part không được gửi.
- File empty/zero-byte: part có mặt nhưng size bằng 0.
- File quá lớn: part có mặt và `getSize()` vượt giới hạn.

Nếu contract yêu cầu file không rỗng, kiểm tra `isEmpty()` riêng. Không dùng `isEmpty()` để kết luận part absent.

### 5.1. Giới hạn từng file và tổng request

Có thể có nhiều lớp giới hạn:

| Lớp | Đối tượng được giới hạn | Ví dụ |
| --- | --- | --- |
| Business validation | Một file | `file.getSize() <= 5 MiB` |
| Multipart resolver/container | Một file upload | `max-file-size` |
| Multipart resolver/container | Tổng multipart request | `max-request-size` |
| Reverse proxy/API gateway | Toàn HTTP request body | Giới hạn body tại gateway |

Nếu endpoint nhận nhiều file, giới hạn 5 MiB cho từng file không đồng nghĩa tổng request chỉ được 5 MiB. Ngược lại, tổng multipart request có thể lớn hơn giới hạn file riêng do chứa nhiều file và overhead.

### 5.2. Cấu hình multipart trong Spring Boot

Với servlet stack, các property phổ biến:

```properties
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
```

`max-file-size` giới hạn kích thước một file; `max-request-size` giới hạn tổng multipart request. Các giá trị này phải phối hợp với reverse proxy, gateway và giới hạn hạ tầng.

Cấu hình container có thể từ chối request trước khi controller nhận được `MultipartFile`. Vì vậy, một unit-style MockMvc test gọi trực tiếp MVC không phải lúc nào cũng tái hiện chính xác lỗi do container hoặc gateway phát sinh. Hãy phân biệt:
- Kiểm tra business size trong controller/service: có thể test ổn định với MockMvc.
- Kiểm tra giới hạn multipart resolver/container/proxy: cần integration test với cấu hình runtime thực tế hoặc kiểm thử qua môi trường tích hợp phù hợp.

## 6. Ánh xạ exception thành error response ổn định

Ví dụ exception:

```java
public class FileTooLargeException extends RuntimeException {
    private final long maxBytes;

    public FileTooLargeException(long maxBytes) {
        super("Uploaded file exceeds the allowed size");
        this.maxBytes = maxBytes;
    }

    public long getMaxBytes() {
        return maxBytes;
    }
}

public class UnsupportedFileTypeException extends RuntimeException {
}
```

DTO lỗi:

```java
public record ApiError(
        String code,
        String message,
        int status,
        String path
) {}
```

Ví dụ `@RestControllerAdvice`:

```java
@RestControllerAdvice
class UploadExceptionHandler {

    @ExceptionHandler(FileTooLargeException.class)
    ResponseEntity<ApiError> handleFileTooLarge(
            FileTooLargeException exception,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "FILE_TOO_LARGE",
                "File must not exceed the configured size limit",
                413,
                request.getRequestURI()
        );

        return ResponseEntity.status(413).body(body);
    }

    @ExceptionHandler(UnsupportedFileTypeException.class)
    ResponseEntity<ApiError> handleUnsupportedType(
            UnsupportedFileTypeException exception,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "UNSUPPORTED_FILE_TYPE",
                "Only PNG and JPEG images are supported",
                415,
                request.getRequestURI()
        );

        return ResponseEntity.status(415).body(body);
    }
}
```

Ví dụ minh họa; trong code thật có thể dùng `HttpStatus.PAYLOAD_TOO_LARGE` hoặc status enum tương ứng của phiên bản Spring đang dùng, và cần import `HttpServletRequest`. Tên constant của HTTP status trong framework có thể khác giữa các phiên bản; kiểm tra API của dự án trước khi dùng.

Không trả stack trace, đường dẫn lưu trữ nội bộ, tên bucket hoặc chi tiết parser nhạy cảm cho client. Ghi log nội bộ bằng correlation ID và response lỗi công khai bằng error code ổn định.

## 7. MockMvc: test file sai loại và sinh snippet lỗi

Giả sử endpoint `POST /api/products/{id}/assets` trả `415` khi part `file` không có MIME type được cho phép. Request vẫn chứa metadata JSON hợp lệ.

### 7.1. Dựng request có MIME type không hỗ trợ

```java
MockMultipartFile wrongType = new MockMultipartFile(
        "file",
        "notes.txt",
        MediaType.TEXT_PLAIN_VALUE,
        "not an image".getBytes(StandardCharsets.UTF_8)
);

MockPart metadata = new MockPart(
        "metadata",
        """
        {"title":"Tài sản thử nghiệm"}
        """.getBytes(StandardCharsets.UTF_8)
);
metadata.getHeaders().setContentType(MediaType.APPLICATION_JSON);
```

### 7.2. Tài liệu hóa status và error body

```java
mockMvc.perform(multipart("/api/products/{id}/assets", 42)
        .file(wrongType)
        .part(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isUnsupportedMediaType())
    .andExpect(jsonPath("$.code").value("UNSUPPORTED_FILE_TYPE"))
    .andDo(document("products-upload-unsupported-file-type",
        requestParts(
            partWithName("file")
                .description("File ảnh; chỉ chấp nhận PNG hoặc JPEG"),
            partWithName("metadata")
                .description("Metadata JSON của tài sản")
        ),
        responseFields(
            fieldWithPath("code").description("Mã lỗi ổn định"),
            fieldWithPath("message").description("Mô tả lỗi"),
            fieldWithPath("status").description("HTTP status"),
            fieldWithPath("path").description("Đường dẫn request gây lỗi")
        )
    ));
```

Imports tĩnh tương ứng:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
```

Test này đồng thời xác nhận status, error code và tạo các snippet cho request parts/response fields. `responseFields(...)` phải khớp chính xác JSON lỗi thực tế. Nếu response có thêm field, strict mode có thể yêu cầu mô tả hoặc ignore có chủ đích.

Có thể bổ sung `responseHeaders(...)` khi error response có header contract cần công bố, ví dụ `Content-Type` hoặc correlation header.

## 8. MockMvc: test file vượt giới hạn nghiệp vụ và sinh snippet

Để test kích thước ổn định với MockMvc, ứng dụng cần có business validation dựa trên `MultipartFile.getSize()` trước khi xử lý/lưu file.

Ví dụ giới hạn 5 MiB:

```java
private static final int MAX_FILE_BYTES = 5 * 1024 * 1024;

void validateSize(MultipartFile file) {
    if (file.getSize() > MAX_FILE_BYTES) {
        throw new FileTooLargeException(MAX_FILE_BYTES);
    }
}
```

Tạo byte array vượt giới hạn:

```java
byte[] oversizedBytes = new byte[MAX_FILE_BYTES + 1];

MockMultipartFile oversizedFile = new MockMultipartFile(
        "file",
        "large.png",
        MediaType.IMAGE_PNG_VALUE,
        oversizedBytes
);
```

Test và snippet:

```java
mockMvc.perform(multipart("/api/products/{id}/assets", 42)
        .file(oversizedFile)
        .part(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isPayloadTooLarge())
    .andExpect(jsonPath("$.code").value("FILE_TOO_LARGE"))
    .andDo(document("products-upload-file-too-large",
        requestParts(
            partWithName("file")
                .description("Ảnh sản phẩm; giới hạn 5 MiB"),
            partWithName("metadata")
                .description("Metadata JSON của tài sản")
        ),
        responseFields(
            fieldWithPath("code").description("Mã lỗi"),
            fieldWithPath("message").description("Mô tả lỗi"),
            fieldWithPath("status").description("HTTP status"),
            fieldWithPath("path").description("Đường dẫn request")
        )
    ));
```

Đây là test business validation. Nó tạo request lớn hơn giới hạn mà code ứng dụng kiểm tra; không nhất thiết kiểm thử được giới hạn `max-file-size` của servlet container. Nếu container chặn request trước khi MVC nhận được, kết quả có thể khác và cần test tích hợp theo cấu hình server thật.

Khi dùng byte array lớn, hãy giữ fixture ở mức vừa đủ để test nhanh. Không cần tạo file cực lớn nếu contract chỉ yêu cầu xác nhận vượt ngưỡng một byte.

## 9. Kiểm tra bytes giả MIME và file hỏng

Một test hữu ích là khai báo MIME hợp lệ nhưng gửi nội dung không hợp lệ:

```java
MockMultipartFile fakePng = new MockMultipartFile(
        "file",
        "fake.png",
        MediaType.IMAGE_PNG_VALUE,
        "this is plain text".getBytes(StandardCharsets.UTF_8)
);
```

MIME header nói `image/png`, nhưng bytes là văn bản. Nếu API có kiểm tra chữ ký hoặc decode ảnh, test cần xác nhận response lỗi theo contract, ví dụ:

```java
.andExpect(status().isBadRequest())
.andExpect(jsonPath("$.code").value("INVALID_FILE_CONTENT"));
```

Không dùng test này để chứng minh `415` cho MIME không được hỗ trợ: header đang là `image/png`, nên nguyên nhân là nội dung file không hợp lệ. Phân loại lỗi đúng giúp client biết nên đổi Content-Type hay chọn file khác.

## 10. Tổ chức snippet lỗi và Asciidoctor

Giả sử các test tạo operation ID:
- `products-upload-unsupported-file-type`
- `products-upload-file-too-large`

Thư mục snippet có thể gồm:

```text
build/generated-snippets/
├── products-upload-unsupported-file-type/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── request-parts.adoc
│   └── response-fields.adoc
└── products-upload-file-too-large/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-parts.adoc
    └── response-fields.adoc
```

Tên snippet được sinh tùy theo các document snippets đã gắn trong test. Nếu test không gọi `requestParts(...)` hoặc `responseFields(...)`, thư mục tương ứng sẽ không có file đó.

Ví dụ tài liệu `src/docs/asciidoc/products.adoc`:

```adoc
= Product Asset API
:toc: left

== Lỗi khi upload file

=== File dùng media type không được hỗ trợ

HTTP request:
include::{snippets}/products-upload-unsupported-file-type/http-request.adoc[]

Response:
include::{snippets}/products-upload-unsupported-file-type/http-response.adoc[]

Error fields:
include::{snippets}/products-upload-unsupported-file-type/response-fields.adoc[]

=== File vượt giới hạn dung lượng

HTTP request:
include::{snippets}/products-upload-file-too-large/http-request.adoc[]

Response:
include::{snippets}/products-upload-file-too-large/http-response.adoc[]

Error fields:
include::{snippets}/products-upload-file-too-large/response-fields.adoc[]
```

Có thể include `request-parts.adoc` nếu cần cho thấy cấu trúc multipart của request lỗi. Hãy cân nhắc mức độ chi tiết cần công bố; không phải mọi error page đều cần lặp lại toàn bộ request contract.

### 10.1. Tài liệu hóa bảng giới hạn

Bổ sung phần contract tĩnh hoặc được duy trì tập trung:

```adoc
=== Quy tắc file được hỗ trợ

|===
|Quy tắc |Giá trị

|Media type
|`image/png`, `image/jpeg`

|Kích thước tối đa mỗi file
|5 MiB

|Loại file không hỗ trợ
|HTTP `415`, code `UNSUPPORTED_FILE_TYPE`

|File vượt giới hạn
|HTTP `413`, code `FILE_TOO_LARGE`
|===
```

Bảng này diễn đạt chính sách cho client. Để tránh tài liệu lỗi thời, các giá trị phải được review cùng validation/configuration và test. Snippet error response chứng minh response của test; nó không tự lấy giới hạn 5 MiB từ cấu hình ứng dụng.

## 11. Kiểm thử giới hạn container và reverse proxy

Các giới hạn upload có thể được thực thi ở nhiều lớp:

1. Business validation trong controller/service.
2. Multipart resolver và servlet container.
3. Reverse proxy, ingress hoặc API gateway.
4. Hạ tầng lưu trữ hoặc dịch vụ quét file.

MockMvc thích hợp để xác minh business validation vì request đi qua MVC mock. Nhưng nếu request vượt `spring.servlet.multipart.max-file-size`, servlet container có thể từ chối ngay trong bước parse multipart. MockMvc không bảo đảm tái hiện giống hệt container thật ở mọi cấu hình.

Để kiểm thử giới hạn đó:
- Chạy ứng dụng với embedded server và cấu hình multipart thực tế.
- Gửi HTTP request qua client tích hợp, ví dụ WebTestClient với server đang chạy hoặc REST Assured.
- Xác nhận status/error body tại lớp trả response thực tế.
- Nếu proxy/gateway sở hữu giới hạn, kiểm tra trong môi trường có proxy/gateway tương ứng.

Không giả định mọi tầng đều trả cùng JSON error body. Container hoặc proxy có thể trả response khác `@RestControllerAdvice`; nếu muốn error contract đồng nhất, cần cấu hình error handling ở đúng tầng.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| File `text/plain` được chấp nhận | Chưa kiểm tra MIME allowlist | Thêm validation và test 415 |
| File giả PNG vẫn được nhận | Chỉ tin `getContentType()` hoặc filename | Kiểm tra bytes/signature và test nội dung |
| Test MockMvc không tái hiện 413 từ container | Request bị chặn trước MVC ở môi trường thật | Thêm integration test chạy server với multipart limit |
| File lớn bị báo 400 thay vì 413 | Exception mapping chưa thống nhất | Chuẩn hóa error mapping theo contract |
| Error response có field mới làm snippet fail | Strict `responseFields(...)` phát hiện field chưa mô tả | Thêm descriptor hoặc ignore có chủ đích |
| `requestParts(...)` báo part thiếu trong test lỗi | Fixture error không gửi đủ các part descriptor required | Gửi đủ part hợp lệ khác hoặc đánh dấu optional đúng contract |
| Body lỗi không phải JSON | Container/proxy trả HTML hoặc body rỗng | Tài liệu hóa response thực tế ở tầng phát sinh |
| Dùng `415` cho file giả MIME | Nhầm media type khai báo với nội dung file | Tách unsupported media type khỏi invalid file content |
| Giới hạn trong docs lệch config | Sửa một nơi mà quên nơi còn lại | Quản lý contract tập trung và test ngưỡng |
| Test tạo byte array quá lớn gây chậm | Dùng file lớn hơn nhiều so với ngưỡng | Chỉ tạo `maxBytes + 1` cho business validation |

## 13. Build và CI

Với Gradle và plugin Asciidoctor đã cấu hình, task tài liệu cần phụ thuộc test sinh snippet:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
```

Luồng CI:

```text
Multipart negative tests
        |
        +--> MIME type không hỗ trợ -> 415
        |
        +--> File vượt business size -> 413
        |
        +--> File giả MIME / nội dung hỏng -> error theo contract
        |
        v
Spring REST Docs tạo request/response snippets
        |
        v
Asciidoctor / bước chuyển Markdown
        |
        v
Kiểm tra và xuất bản tài liệu
```

Nếu có integration test kiểm tra giới hạn container/proxy, chạy nó trong profile hoặc stage phù hợp. Test đó nên xác nhận response từ môi trường thực tế, còn MockMvc test tiếp tục kiểm tra business validation và sinh snippet ổn định.

Spring REST Docs thường sinh snippet AsciiDoc. Nếu dự án phát hành Markdown, cần template hoặc bước chuyển đổi riêng; không mặc định có `.md` snippets.

## 14. Bài thực hành

Với endpoint `POST /api/products/{id}/assets`:

1. Xác định allowlist `image/png` và `image/jpeg`, đồng thời chọn giới hạn 5 MiB cho mỗi file.
2. Viết test gửi `text/plain` và xác nhận error code `UNSUPPORTED_FILE_TYPE`, status 415.
3. Viết test dùng `maxBytes + 1` để xác nhận business size validation, status 413.
4. Gửi MIME `image/png` với bytes văn bản; xác nhận API phát hiện nội dung không hợp lệ và trả error code riêng.
5. Thêm `requestParts(...)` và `responseFields(...)` để sinh snippet cho hai response lỗi.
6. Include request, response và error fields vào Asciidoctor.
7. Chạy integration test qua embedded server để xác nhận multipart container limit; so sánh response với business validation.
8. Cập nhật bảng policy khi thay đổi allowlist hoặc giới hạn; chạy lại test và build CI.

### Câu hỏi tự đánh giá

- Content-Type của request multipart khác Content-Type của file part thế nào?
- Vì sao filename `.png` và header `image/png` không chứng minh bytes là PNG?
- Khi nào nên trả 415 và khi nào nên trả lỗi nội dung file không hợp lệ?
- `max-file-size` và `max-request-size` giới hạn hai đối tượng nào?
- Vì sao MockMvc test business size không thay thế integration test container?
- `requestParts(...)` và `responseFields(...)` đóng góp gì cho tài liệu lỗi upload?
- Nếu proxy trả 413 trước khi request tới controller, `@RestControllerAdvice` có xử lý được response đó không?
- Làm sao giữ bảng giới hạn trong tài liệu đồng bộ với validation và configuration?

**Ghi nhớ:** Tài liệu hóa lỗi upload cần nói rõ media type được chấp nhận, giới hạn kích thước và cấu trúc response lỗi. Dùng test MockMvc cho quy tắc do ứng dụng kiểm tra và Spring REST Docs để sinh snippet request/response; kiểm thử riêng qua server hoặc proxy khi giới hạn được áp dụng trước MVC. MIME header, filename và bytes file là ba thông tin khác nhau, cần được xác minh đúng tầng.

## Tài liệu tham khảo

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): tài liệu hóa request parts.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): request/response fields và payload snippets.
- [Spring Framework — `MultipartFile` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html): kích thước, content type, filename và bytes của file.
- [Spring Boot — Servlet Web Server](https://docs.spring.io/spring-boot/reference/web/servlet.html): cấu hình ứng dụng servlet; xem thêm thuộc tính multipart theo phiên bản Boot của dự án.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): định nghĩa status 413 Content Too Large và 415 Unsupported Media Type.
