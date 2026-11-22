# Part bắt buộc, tùy chọn và absent trong Spring REST Docs

## 1. Xác định sự hiện diện của multipart part

Một multipart request gồm nhiều part được nhận diện bằng tên trong `Content-Disposition`. Ví dụ, operation upload tài liệu có thể nhận:

- `file`: tệp PDF cần tải lên.
- `metadata`: JSON chứa tiêu đề và loại tài liệu.
- `thumbnail`: ảnh xem trước, chỉ gửi khi client có ảnh.

Một phần của contract là xác định part nào **bắt buộc**, part nào **được phép vắng mặt** và server phản hồi thế nào khi thiếu part bắt buộc. Trong Spring REST Docs, `requestParts(...)` mô tả các part bằng `partWithName(...)`. Descriptor mặc định yêu cầu part xuất hiện trong request mẫu; `.optional()` cho phép part đã mô tả vắng mặt trong request dùng để sinh snippet.

Cần tách biệt ba lớp quy tắc:

1. **Contract của endpoint:** client có được phép bỏ qua part hay không?
2. **Validation của ứng dụng:** server xử lý thế nào nếu part bắt buộc bị thiếu hoặc part tùy chọn có nội dung không hợp lệ?
3. **Contract của snippet:** request mẫu được dùng để sinh tài liệu có thể thiếu descriptor nào mà không làm việc sinh snippet thất bại?

`optional()` tác động đến lớp thứ ba. Nó không tự làm endpoint chấp nhận request thiếu part.

Bài này thuộc chương **Request parts** của SPRING_REST_DOCS, nơi thực hành sinh snippet từ kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured, rồi đưa vào Asciidoctor/Markdown và build/CI.

Sau bài này, bạn có thể:

- Đánh dấu part required và optional trong `requestParts(...)`.
- Phân biệt part absent với part có mặt nhưng rỗng hoặc chứa file zero-byte.
- Kiểm tra hành vi endpoint với part bị thiếu.
- Hiểu vai trò của `@RequestPart(required = ...)` trong Spring MVC.
- Kết hợp strict/relaxed, ignored và optional để mô tả đúng multipart contract.

## 2. Required và optional trong descriptor

Ví dụ operation `POST /api/documents` nhận hai part:

- `file`: PDF bắt buộc.
- `metadata`: JSON bắt buộc.

Một part `preview` không bắt buộc:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("file")
        .description("Tệp PDF cần tải lên"),
    partWithName("metadata")
        .description("Metadata JSON của tài liệu"),
    partWithName("preview")
        .description("Ảnh xem trước nếu client cung cấp")
        .optional()
);
```

Trong chế độ strict, `file` và `metadata` được xem là required theo mặc định. `preview` được phép vắng mặt trong request mẫu vì descriptor có `.optional()`.

Bảng ý nghĩa:

| Descriptor | Part có trong request mẫu? | Kết quả mong đợi khi tạo snippet |
| --- | --- | --- |
| `partWithName("file")` | Có | Được kiểm tra và mô tả |
| `partWithName("file")` | Không | Có thể làm snippet thất bại vì part bắt buộc thiếu |
| `partWithName("preview").optional()` | Có | Được kiểm tra và mô tả |
| `partWithName("preview").optional()` | Không | Vẫn có thể mô tả part như một phần tùy chọn |
| `partWithName("clientTrace").ignored()` | Có | Được nhận diện nhưng không hiển thị trong bảng |
| `partWithName("clientTrace").optional().ignored()` | Không | Được phép vắng và không xuất hiện trong bảng |

### 2.1. Optional không có nghĩa là ignored

Hai thuộc tính này độc lập:

- `.optional()` nói rằng descriptor có thể không có mặt trong request mẫu.
- `.ignored()` nói rằng descriptor không được đưa thành dòng trong snippet.

Ví dụ part `clientTrace` không bắt buộc và không cần công bố:

```java
partWithName("clientTrace")
    .description("Mã trace nếu client cung cấp")
    .optional()
    .ignored();
```

Nếu `clientTrace` xuất hiện, descriptor nhận diện nó nhưng không hiển thị. Nếu nó vắng mặt, `.optional()` cho phép việc sinh snippet tiếp tục.

### 2.2. Optional không có nghĩa là content rỗng hợp lệ

```java
partWithName("preview")
    .description("Ảnh xem trước nếu có")
    .optional();
```

Khai báo trên chỉ nói rằng part có thể không xuất hiện. Nó không định nghĩa những tình huống sau có hợp lệ hay không:

- Part `preview` hiện diện với zero byte.
- Part `preview` có content type không hỗ trợ.
- Part `preview` là ảnh nhưng dữ liệu bị hỏng.
- Part `preview` có tên file nhưng không có nội dung.

Các quy tắc đó thuộc validation của endpoint và cần test riêng.

## 3. Phân biệt absent, empty part và zero-byte file

Ba trường hợp sau có thể trông giống nhau khi chỉ xem UI hoặc log tóm tắt, nhưng ý nghĩa HTTP khác nhau.

### 3.1. Part absent

Request không có phần `preview`:

```text
Content-Disposition: form-data; name="file"; filename="report.pdf"
...
Content-Disposition: form-data; name="metadata"
...
```

Không có part nào mang `name="preview"`. Client thực sự đã bỏ qua part này.

### 3.2. Part hiện diện nhưng content rỗng

Request có part `preview` nhưng nội dung không có byte:

```http
Content-Disposition: form-data; name="preview"; filename="preview.png"
Content-Type: image/png

<empty body>
```

Part vẫn xuất hiện trong multipart body. Nó không phải absent; nó là một part có content length bằng zero.

### 3.3. Part hiện diện với filename rỗng hoặc filename không được cung cấp

Tùy client và cách xây dựng multipart request, part có thể có `name="preview"` nhưng không có filename hữu ích. Server cần xác định cách diễn giải trường hợp này. Đừng suy ra absent chỉ từ `MultipartFile.isEmpty()`, vì `isEmpty()` có thể đúng với file zero-byte hoặc dữ liệu không có byte.

| Trạng thái | Có part tên `preview`? | Có byte nội dung? | Ý nghĩa |
| --- | --- | --- | --- |
| Absent | Không | Không áp dụng | Client không gửi part |
| Empty part | Có | Không | Client gửi part nhưng body rỗng |
| File có nội dung | Có | Có | Client gửi file có dữ liệu |
| File zero-byte | Có | Không | File tồn tại về mặt part nhưng kích thước bằng 0 |

**Điểm cần nhớ:** `.optional()` mô tả sự vắng mặt của descriptor trong request mẫu. Nó không được dùng để diễn đạt “nếu part tồn tại thì content được phép zero byte”.

## 4. Thiết kế contract và controller cho part optional

Trong Spring MVC, tham số `@RequestPart` mặc định là required. Khi part thực sự không bắt buộc, có thể khai báo `required = false`.

Ví dụ:

```java
@PostMapping(
    path = "/api/documents",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public ResponseEntity<Void> upload(
        @RequestPart("file") MultipartFile file,
        @RequestPart("metadata") DocumentMetadata metadata,
        @RequestPart(value = "preview", required = false)
                MultipartFile preview) {

    // Kiểm tra file và metadata theo contract.
    // preview có thể là null khi client không gửi part.
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
```

Trong ví dụ này:

- `file` required vì `@RequestPart` mặc định `required = true`.
- `metadata` required vì mặc định required.
- `preview` optional vì `required = false`.

Controller vẫn cần validation cho content của từng part. Ví dụ, `file` có thể không null nhưng là zero-byte; `metadata` có thể được deserialize thành object nhưng thiếu tiêu đề; `preview` có thể có MIME type sai.

### 4.1. Xử lý file required

```java
if (file.isEmpty()) {
    throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "file must contain data"
    );
}
```

`file.isEmpty()` kiểm tra file rỗng hoặc không có dữ liệu theo abstraction `MultipartFile`; nó không thay thế việc xác minh file có đúng định dạng hay không. Để xác thực PDF, hệ thống có thể cần kiểm tra MIME type, chữ ký file hoặc parser phù hợp.

### 4.2. Xử lý part optional

```java
if (preview != null && !preview.isEmpty()) {
    // Kiểm tra content type và xử lý ảnh xem trước.
}
```

Ở ví dụ này, server bỏ qua preview nếu part absent hoặc empty. Một contract khác có thể phân biệt hai trường hợp này và từ chối empty part. Hãy thể hiện lựa chọn đó trong API docs và test.

## 5. MockMvc: sinh snippet với part optional vắng mặt

Giả định endpoint `POST /api/documents` nhận `file` và `metadata` bắt buộc, `preview` optional và trả `201 Created` khi dữ liệu hợp lệ.

### 5.1. Bộ descriptor

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

private static final RequestPartDescriptor[] DOCUMENT_PARTS = {
        partWithName("file")
                .description("Tệp PDF cần tải lên"),
        partWithName("metadata")
                .description("Metadata JSON của tài liệu"),
        partWithName("preview")
                .description("Ảnh xem trước nếu client cung cấp")
                .optional()
};
```

### 5.2. Test gửi part optional

```java
@Test
void documentUploadWithPreview() throws Exception {
    MockMultipartFile file = new MockMultipartFile(
            "file",
            "report.pdf",
            MediaType.APPLICATION_PDF_VALUE,
            validPdfBytes()
    );

    MockMultipartFile metadata = new MockMultipartFile(
            "metadata",
            "",
            MediaType.APPLICATION_JSON_VALUE,
            """
            {"title":"Báo cáo quý","category":"FINANCE"}
            """.getBytes(StandardCharsets.UTF_8)
    );

    MockMultipartFile preview = new MockMultipartFile(
            "preview",
            "preview.png",
            MediaType.IMAGE_PNG_VALUE,
            validPngBytes()
    );

    mockMvc.perform(multipart("/api/documents")
                .file(file)
                .file(metadata)
                .file(preview))
            .andExpect(status().isCreated())
            .andDo(document("documents-upload-with-preview",
                    requestParts(DOCUMENT_PARTS)));
}
```

### 5.3. Test không gửi part optional

Trong test này, chỉ gửi hai part bắt buộc:

```java
@Test
void documentUploadWithoutPreview() throws Exception {
    MockMultipartFile file = new MockMultipartFile(
            "file",
            "report.pdf",
            MediaType.APPLICATION_PDF_VALUE,
            validPdfBytes()
    );

    MockMultipartFile metadata = new MockMultipartFile(
            "metadata",
            "",
            MediaType.APPLICATION_JSON_VALUE,
            """
            {"title":"Báo cáo quý","category":"FINANCE"}
            """.getBytes(StandardCharsets.UTF_8)
    );

    mockMvc.perform(multipart("/api/documents")
                .file(file)
                .file(metadata))
            .andExpect(status().isCreated())
            .andDo(document("documents-upload-without-preview",
                    requestParts(DOCUMENT_PARTS)));
}
```

Test thứ hai là ví dụ trực tiếp về **absent**: request builder không thêm part tên `preview`. Vì descriptor của `preview` optional, snippet có thể được tạo với part này được mô tả là tùy chọn.

Hai operation ID khác nhau giúp giữ snippet riêng:

```text
build/generated-snippets/
├── documents-upload-with-preview/
│   └── request-parts.adoc
└── documents-upload-without-preview/
    └── request-parts.adoc
```

Các snippet HTTP khác phụ thuộc cấu hình. Fixture `validPdfBytes()` và `validPngBytes()` đại diện cho file hợp lệ trong test resources; cần dùng dữ liệu thật phù hợp với validator của ứng dụng.

## 6. Kiểm thử absent khác empty part

Để chắc chắn test đang mô tả đúng contract, viết các tình huống tách biệt:

| Test case | Request builder | Mục tiêu |
| --- | --- | --- |
| Không gửi `preview` | Không gọi `.file(preview)` | Xác nhận optional part absent |
| Gửi `preview` zero byte | `.file(new MockMultipartFile("preview", "preview.png", "image/png", new byte[0]))` | Xác nhận ứng xử với part rỗng |
| Gửi `preview` có byte hợp lệ | `.file(validPreview)` | Xác nhận part có nội dung |
| Gửi `preview` sai MIME type | `.file(wrongContentType)` | Xác nhận validation định dạng |

Một test zero-byte minh họa:

```java
@Test
void rejectEmptyPreviewWhenPartIsPresent() throws Exception {
    MockMultipartFile file = new MockMultipartFile(
            "file", "report.pdf", MediaType.APPLICATION_PDF_VALUE, validPdfBytes()
    );
    MockMultipartFile metadata = new MockMultipartFile(
            "metadata", "", MediaType.APPLICATION_JSON_VALUE,
            """
            {"title":"Báo cáo quý","category":"FINANCE"}
            """.getBytes(StandardCharsets.UTF_8)
    );
    MockMultipartFile preview = new MockMultipartFile(
            "preview", "preview.png", MediaType.IMAGE_PNG_VALUE, new byte[0]
    );

    mockMvc.perform(multipart("/api/documents")
                .file(file)
                .file(metadata)
                .file(preview))
            .andExpect(status().isBadRequest());
}
```

Kỳ vọng `400 Bad Request` ở đây chỉ đúng nếu contract quy định part hiện diện phải chứa file không rỗng và controller đã triển khai validation tương ứng. Nếu API cho phép empty preview, hãy thay assertion theo hành vi đã công bố.

Để kiểm tra absent ở tầng controller, tham số `@RequestPart(value = "preview", required = false)` thường nhận `null` khi part không được gửi. Đối với test tài liệu hóa, việc không thêm `.file(preview)` vào request builder là cách tạo request absent rõ ràng.

## 7. Part bắt buộc bị thiếu: kiểm tra hành vi endpoint

`requestParts(...)` có thể làm bài test tài liệu hóa thất bại nếu descriptor required không xuất hiện trong request mẫu. Đây là kiểm tra của Spring REST Docs, không phải response HTTP của server.

Muốn xác minh server từ chối request thiếu `file`, viết test HTTP riêng:

```java
@Test
void rejectRequestWithoutRequiredFile() throws Exception {
    MockMultipartFile metadata = new MockMultipartFile(
            "metadata",
            "",
            MediaType.APPLICATION_JSON_VALUE,
            """
            {"title":"Báo cáo quý","category":"FINANCE"}
            """.getBytes(StandardCharsets.UTF_8)
    );

    mockMvc.perform(multipart("/api/documents")
                .file(metadata))
            .andExpect(status().isBadRequest());
}
```

Với controller dùng `@RequestPart("file") MultipartFile file`, Spring MVC coi part này là required theo mặc định. Nếu part không có, framework có thể trả lỗi trước khi method controller được gọi. Status cụ thể phụ thuộc exception handling và cấu hình của ứng dụng; `400` là kỳ vọng thường gặp, nhưng test cần phản ánh response contract thực tế.

Có thể tài liệu hóa response lỗi riêng bằng một operation ID khác, nhưng không nên dùng request lỗi làm ví dụ duy nhất cho bảng parts của request thành công.

## 8. Strict, relaxed, ignored và optional

| Cơ chế | Khi part được mô tả nhưng không gửi | Khi có part chưa mô tả | Có hiển thị trong snippet? |
| --- | --- | --- | --- |
| `requestParts(...)` | Required theo mặc định | Có thể làm test thất bại | Có |
| `.optional()` | Cho phép part vắng | Không thay đổi kiểm tra part dư | Có khi part được gửi |
| `.ignored()` | Không tự làm part optional | Nhận diện part đã khai báo | Không |
| `.optional().ignored()` | Cho phép vắng và không hiển thị | Không thay đổi strict mode | Không |
| `relaxedRequestParts(...)` | Descriptor vẫn required trừ optional | Cho phép part dư | Chỉ descriptor không ignored |

Ví dụ `clientTrace` có thể được gửi bởi một số client nhưng không cần công bố:

```java
requestParts(
    partWithName("file").description("Tệp PDF"),
    partWithName("metadata").description("Metadata JSON"),
    partWithName("clientTrace")
        .description("Mã trace nếu client cung cấp")
        .optional()
        .ignored()
);
```

Dùng relaxed mode khi operation chấp nhận các part mở rộng chưa liệt kê. Đổi lại, test không còn phát hiện part mới chưa được mô tả. Với contract public ổn định, strict mode và descriptor optional rõ ràng thường giúp kiểm soát thay đổi tốt hơn.

## 9. Đưa required/optional vào tài liệu Asciidoctor

Snippet `request-parts.adoc` mô tả part theo descriptor. Description nên nói rõ trạng thái tùy chọn khi người đọc cần biết:

```java
partWithName("preview")
    .description("Ảnh xem trước; có thể bỏ qua")
    .optional();
```

Nguồn Asciidoctor:

```adoc
= Document API
:toc: left

== Upload tài liệu có ảnh xem trước

include::{snippets}/documents-upload-with-preview/request-parts.adoc[]

== Upload tài liệu không có ảnh xem trước

include::{snippets}/documents-upload-without-preview/http-request.adoc[]
```

Có thể bổ sung bảng contract để làm rõ yêu cầu nghiệp vụ:

| Part | Required | Ghi chú |
| --- | --- | --- |
| `file` | Có | File PDF có nội dung |
| `metadata` | Có | JSON có tiêu đề |
| `preview` | Không | Nếu gửi phải là ảnh hợp lệ |

Nếu template snippet không hiển thị cột Required/Optional, description hoặc bảng hợp đồng riêng có thể truyền đạt thông tin đó. Không giả định `.optional()` luôn tạo ra một cột riêng trong mọi template.

## 10. Build và CI

Với Gradle và plugin Asciidoctor đã được cấu hình:

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
Multipart HTTP tests
        |
        v
Kiểm tra server với part absent / present / empty
        |
        v
Spring REST Docs đối chiếu requestParts descriptors
        |
        v
request-parts.adoc
        |
        v
Asciidoctor / bước xuất Markdown
        |
        v
Kiểm tra và xuất bản
```

Mỗi khi contract đổi, test nên xác minh cả việc sinh snippet và hành vi endpoint. Nếu `preview` được đổi từ optional thành required, cập nhật đồng thời controller/validation, test có và không có part, descriptor và tài liệu.

Spring REST Docs thường tạo snippet AsciiDoc. Nếu cần Markdown, cấu hình template hoặc bước chuyển đổi riêng; không mặc định có file `request-parts.md`.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Test REST Docs báo thiếu part | Descriptor required nhưng request mẫu không gửi | Thêm part hoặc `.optional()` theo contract |
| Server từ chối request dù descriptor đã optional | Controller vẫn yêu cầu part | Cập nhật `@RequestPart(required = false)` nếu contract cho phép |
| Nhầm part zero-byte với absent | Chỉ kiểm tra `MultipartFile.isEmpty()` | Kiểm tra sự hiện diện của part và nội dung riêng |
| Test absent lại gửi part rỗng | Request builder vẫn gọi `.file(...)` | Không thêm part vào request builder |
| Part mới làm strict snippet thất bại | Chưa có descriptor | Mô tả, ignore có chủ đích hoặc dùng relaxed theo contract |
| Part optional vẫn không xuất hiện trong bảng khi request có mặt | Descriptor được đánh dấu ignored | Bỏ `.ignored()` nếu muốn hiển thị |
| MIME type sai vẫn được nhận | Description chỉ ghi quy tắc, không thực thi validation | Thêm kiểm tra content type và test âm tính |
| Asciidoctor báo thiếu snippet | Include operation ID hoặc snippet chưa được sinh | Kiểm tra tên operation và thứ tự task |

## 12. Bài thực hành

Với endpoint `POST /api/documents`:

1. Khai báo `file` và `metadata` required, `preview` optional bằng `requestParts(...)`.
2. Tạo request có cả ba part; kiểm tra snippet mô tả đầy đủ.
3. Tạo request không gửi `preview`; xác nhận đây là absent chứ không phải part rỗng.
4. Gửi `preview` zero-byte và xác định response theo contract.
5. Bỏ `file` khỏi request; xác nhận server từ chối theo contract và so sánh lỗi HTTP với lỗi snippet khi descriptor required.
6. Đổi `preview` từ optional thành required. Cập nhật controller, test, descriptor và tài liệu.
7. Gửi part `clientTrace` optional và ignored; kiểm tra part vẫn có trên request nhưng không xuất hiện trong snippet.
8. Include snippet vào Asciidoctor và bảo đảm CI chạy HTTP tests trước khi kết xuất tài liệu.

### Câu hỏi tự đánh giá

- Required trong `requestParts(...)` có giống `required = true` của `@RequestPart` không?
- `.optional()` ảnh hưởng bước nào và không ảnh hưởng bước nào?
- Absent khác empty part và zero-byte file ra sao?
- Vì sao `MultipartFile.isEmpty()` không đủ để khẳng định part absent?
- Khi nào cần `@RequestPart(required = false)`?
- Làm thế nào để kiểm tra server từ chối part required bị thiếu?
- Vì sao test sinh snippet và test validation endpoint nên là hai khía cạnh được xem xét riêng?

**Ghi nhớ:** `.optional()` cho Spring REST Docs biết part có thể vắng trong request mẫu dùng để sinh snippet. `@RequestPart(required = false)` mới điều khiển việc Spring MVC có yêu cầu part ở endpoint hay không. Part absent khác với part có mặt nhưng rỗng hoặc file zero-byte; hãy tài liệu hóa và kiểm thử các trường hợp này theo contract thật.

## Tài liệu tham khảo

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): `requestParts`, optional/ignored và relaxed request parts.
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html): `partWithName`, `requestParts` và `relaxedRequestParts`.
- [Spring Framework — `@RequestPart` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestPart.html): thuộc tính `required` khi bind multipart part vào controller.
