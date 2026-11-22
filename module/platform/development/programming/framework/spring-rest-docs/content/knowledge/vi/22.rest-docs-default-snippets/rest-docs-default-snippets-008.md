# request-part-fields và response-headers

## 1. Hai phần khác nhau của hợp đồng HTTP

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Snippets mặc định**, test HTTP tạo snippet mô tả request và response mà ứng dụng thực sự xử lý. Bài này tập trung vào hai descriptor:

| Descriptor | Snippet | Mục đích |
| --- | --- | --- |
| `requestPartFields(partName, ...)` | `request-part-{part-name}-fields.adoc` | Mô tả các field bên trong payload của một multipart request part |
| `responseHeaders(...)` | `response-headers.adoc` | Mô tả các HTTP header mà server trả về |

`requestPartFields` không mô tả toàn bộ multipart body hay byte của file. Nó trích payload của một part cụ thể rồi kiểm tra các field theo descriptor. `responseHeaders` mô tả metadata ở tầng HTTP response, ví dụ `Location`, `ETag`, `Content-Type` hoặc `Cache-Control`.

Ví dụ dùng **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter và MockMvc**. Spring REST Docs cũng hỗ trợ request part fields với WebTestClient và REST Assured; cách tạo multipart request thay đổi theo client.

## 2. Multipart request và các part

Một multipart request chia body thành nhiều phần. Mỗi part có tên, header và nội dung riêng. Endpoint upload tài liệu có thể nhận part `file` chứa PDF và part `metadata` chứa JSON mô tả tiêu đề, loại tài liệu cùng trạng thái công bố.

Ví dụ:

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=----ExampleBoundary
Accept: application/json

------ExampleBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"API Guide","category":"manual"}
------ExampleBoundary
Content-Disposition: form-data; name="file"; filename="guide.pdf"
Content-Type: application/pdf

...binary file bytes...
------ExampleBoundary--
```

Các descriptor tạo những snippet khác nhau:

| Nội dung | Descriptor | Snippet |
| --- | --- | --- |
| Danh sách part của request | `requestParts(...)` | `request-parts.adoc` |
| Body của part metadata | `requestPartBody("metadata")` | `request-part-metadata-body.adoc` |
| Field bên trong JSON metadata | `requestPartFields("metadata", ...)` | `request-part-metadata-fields.adoc` |
| HTTP header của response | `responseHeaders(...)` | `response-headers.adoc` |

Part `metadata` có cấu trúc JSON nên phù hợp với `requestPartFields`. Part `file` là byte của file, không phải object JSON để mô tả bằng field path. Có thể mô tả file part bằng `requestParts(...)`; chỉ dùng field descriptor cho part có payload có cấu trúc.

## 3. Tạo request-part-metadata-fields.adoc

Giả sử part `metadata` có payload:

```json
{
  "title": "API Guide",
  "category": "manual",
  "published": true,
  "owner": {
    "team": "Platform",
    "email": "docs@example.test"
  }
}
```

Khai báo field descriptor:

```java
requestPartFields("metadata",
    fieldWithPath("title")
        .description("Tiêu đề tài liệu"),
    fieldWithPath("category")
        .description("Nhóm tài liệu"),
    fieldWithPath("published")
        .description("Tài liệu đã công bố hay chưa"),
    fieldWithPath("owner.team")
        .description("Nhóm phụ trách"),
    fieldWithPath("owner.email")
        .description("Email liên hệ")
)
```

REST Docs sinh `request-part-metadata-fields.adoc`. Tên snippet được ghép từ tên part: part `metadata` tạo `request-part-metadata-fields.adoc`; part `settings` tạo `request-part-settings-fields.adoc`. Vì vậy, tên part là một phần của đường dẫn include.

### Optional, ignored và relaxed

Nếu một field hợp lệ có thể vắng mặt, đánh dấu optional:

```java
fieldWithPath("description")
    .description("Mô tả bổ sung")
    .optional()
```

Nếu field xuất hiện nhưng không cần đưa vào bảng:

```java
fieldWithPath("internalTraceId")
    .ignored()
```

`requestPartFields` ở strict mode giúp phát hiện field trong part chưa được mô tả và descriptor bắt buộc không xuất hiện trong payload. Nếu chỉ muốn mô tả một tập con field trong một kịch bản, dùng `relaxedRequestPartFields(...)`. Relaxed mode bỏ qua field chưa mô tả; chỉ dùng khi phạm vi tài liệu đã được xác định rõ, tránh che thay đổi hợp đồng.

## 4. Ví dụ MockMvc multipart upload

### 4.1. Tạo fixture cho từng part

MockMvc dùng `MockMultipartFile` để tạo part giả. Part `metadata` chứa JSON; part `file` chứa file nhỏ dành riêng cho test:

```java
MockMultipartFile metadata = new MockMultipartFile(
    "metadata",
    "",
    MediaType.APPLICATION_JSON_VALUE,
    """
    {
      "title": "API Guide",
      "category": "manual",
      "published": true
    }
    """.getBytes(StandardCharsets.UTF_8)
);

MockMultipartFile file = new MockMultipartFile(
    "file",
    "guide.pdf",
    MediaType.APPLICATION_PDF_VALUE,
    "fake-pdf-content".getBytes(StandardCharsets.UTF_8)
);
```

Dữ liệu file ở đây chỉ là fixture nhỏ. Test thực tế nên dùng file giả tối thiểu phù hợp với bộ kiểm tra định dạng của ứng dụng.

### 4.2. Ghi part fields

```java
mockMvc.perform(
        multipart("/api/documents")
            .file(metadata)
            .file(file)
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isCreated())
    .andDo(document("documents-upload",
        requestPartFields("metadata",
            fieldWithPath("title").description("Tiêu đề tài liệu"),
            fieldWithPath("category").description("Nhóm tài liệu"),
            fieldWithPath("published").description("Trạng thái công bố")
        )
    ));
```

`document("documents-upload", ...)` ghi một operation. `requestPartFields("metadata", ...)` trích JSON trong part metadata và tạo bảng field. Nếu cần mô tả cả hai part ở cấp multipart, bổ sung `requestParts(...)`; hai descriptor có trách nhiệm khác nhau.

Ví dụ:

```java
requestParts(
    partWithName("metadata")
        .description("Metadata JSON của tài liệu"),
    partWithName("file")
        .description("Nội dung file được tải lên")
)
```

Snippet `request-parts.adoc` mô tả các part. Snippet `request-part-metadata-fields.adoc` mô tả cấu trúc bên trong metadata. Tài liệu thường cần cả hai để người đọc hiểu request gồm những phần nào và JSON metadata có field gì.

## 5. response-headers.adoc

### 5.1. Vai trò của response header

Response header là metadata server gửi cùng status và response body. Một số header thường thuộc hợp đồng API:

| Header | Ý nghĩa thường gặp |
| --- | --- |
| `Content-Type` | Media type của response body |
| `Location` | URI tham chiếu tới tài nguyên vừa tạo |
| `ETag` | Validator đại diện cho một phiên bản representation |
| `Cache-Control` | Quy tắc cache response |
| `Retry-After` | Thời điểm hoặc khoảng chờ trước khi thử lại |
| `X-RateLimit-Limit` | Hạn mức request trong một chu kỳ |
| `X-RateLimit-Remaining` | Số lượt còn lại trong chu kỳ hiện tại |
| `X-RateLimit-Reset` | Thông tin thời điểm reset hạn mức |

Ví dụ, endpoint POST trả `201 Created` và `Location` để client biết URI tài nguyên mới. Endpoint GET có `ETag` để client thực hiện conditional request. Endpoint bị rate limit có thể cung cấp các header cho biết hạn mức và thời gian chờ.

### 5.2. Khai báo responseHeaders

Dùng `responseHeaders(...)` cùng `headerWithName(...)`:

```java
responseHeaders(
    headerWithName("Location")
        .description("URI của tài liệu vừa được tạo"),
    headerWithName("ETag")
        .description("Validator của representation"),
    headerWithName("Content-Type")
        .description("Media type của response body")
)
```

REST Docs sinh `response-headers.adoc`, chứa bảng mô tả header. Không nhầm với `requestHeaders(...)`, vốn tạo `request-headers.adoc` để mô tả header client gửi lên.

### 5.3. Strict validation và optional header

Header được mô tả phải có trong response thực tế. Nếu descriptor nêu header không tồn tại, snippet generation thất bại và test báo lỗi. Cơ chế này ngăn tài liệu công bố một header mà endpoint không trả.

Nếu header có thể vắng mặt theo hợp đồng, đánh dấu optional:

```java
headerWithName("ETag")
    .description("Validator của representation")
    .optional()
```

Chỉ đánh dấu optional nếu API thực sự cho phép header vắng mặt. Không dùng optional để che lỗi triển khai khiến header bắt buộc không được trả.

## 6. Kết hợp multipart fields và response headers trong một operation

Giả sử endpoint upload trả:

```http
HTTP/1.1 201 Created
Location: /api/documents/501
ETag: "doc-v1"
Content-Type: application/json

{"id":501,"title":"API Guide"}
```

Một lần gọi `document(...)` có thể tạo các snippet tương ứng:

```java
document("documents-upload",
    requestParts(
        partWithName("metadata").description("Metadata JSON"),
        partWithName("file").description("File tài liệu")
    ),
    requestPartFields("metadata",
        fieldWithPath("title").description("Tiêu đề"),
        fieldWithPath("category").description("Nhóm tài liệu"),
        fieldWithPath("published").description("Trạng thái công bố")
    ),
    responseHeaders(
        headerWithName("Location").description("URI tài liệu mới"),
        headerWithName("ETag").description("Validator của tài liệu"),
        headerWithName("Content-Type").description("Media type")
    )
)
```

Test chỉ thành công nếu response thực sự có các header được mô tả. Nếu controller chưa thiết lập ETag, bỏ descriptor đó hoặc bổ sung hành vi đúng theo thiết kế API; không giả định header tự xuất hiện.

## 7. Cấu trúc output và include trong Asciidoctor

Với operation ID `documents-upload` và thư mục snippet gốc `build/generated-snippets`, các file liên quan có dạng:

```text
build/generated-snippets/
  documents-upload/
    request-parts.adoc
    request-part-metadata-fields.adoc
    response-headers.adoc
    http-request.adoc
    http-response.adoc
```

Include vào tài liệu:

```asciidoc
== Upload tài liệu

=== Multipart parts
include::{snippets}/documents-upload/request-parts.adoc[]

=== Metadata fields
include::{snippets}/documents-upload/request-part-metadata-fields.adoc[]

=== Response headers
include::{snippets}/documents-upload/response-headers.adoc[]

=== HTTP response
include::{snippets}/documents-upload/http-response.adoc[]
```

`{snippets}` phải trỏ tới thư mục gốc chứa các operation. Đường dẫn phía sau phải khớp operation ID và tên snippet sinh ra. Khi đổi part name trong `requestPartFields`, cập nhật cả tên file include.

## 8. Build và CI

Với Gradle, bảo đảm test sinh snippet trước khi Asciidoctor include:

```groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.named('test') {
    useJUnitPlatform()
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.get().asFile
}
```

Chạy build:

```bash
./gradlew clean test asciidoctor
```

CI nên dùng file fixture giả nhỏ, ổn định và độc lập với máy developer. Sau build, kiểm tra output có file `request-part-...-fields.adoc` và `response-headers.adoc` trước khi publish. Nếu test thất bại vì header/field descriptor không khớp, sửa implementation hoặc descriptor theo hợp đồng thay vì bỏ qua lỗi.

## 9. Bảo vệ dữ liệu và độ tin cậy

Multipart request có thể chứa file, metadata hoặc dữ liệu cá nhân. Response headers có thể chứa cookie, thông tin server hoặc token. Trước khi publish snippet:

- Dùng file fixture nhỏ, giả lập và không chứa dữ liệu khách hàng.
- Không đưa access token, password, session cookie hoặc API key vào metadata.
- Không ghi header xác thực thật vào request snippet.
- Chỉ mô tả response header công khai và có ý nghĩa với client.
- Tránh tài liệu hóa header nội bộ như debug trace hoặc topology nếu chúng không thuộc hợp đồng công khai.
- Nếu cần loại bỏ hoặc thay header nhạy cảm trong snippet, dùng operation preprocessor; nhớ rằng preprocessor chỉ đổi bản ghi tài liệu, không thay runtime behavior.

Descriptor cũng là một dạng kiểm tra hợp đồng. Nếu header bắt buộc biến mất hoặc field mới xuất hiện trong metadata mà chưa được mô tả, test nên báo lỗi để nhóm cập nhật API và tài liệu có chủ đích.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không có request-part-metadata-fields.adoc | Chưa gọi requestPartFields("metadata", ...) hoặc operation chưa chạy. | Kiểm tra test, operation ID và descriptor. |
| Part fields không tìm thấy field | Part metadata không phải JSON như descriptor mong đợi hoặc path sai. | Kiểm tra part Content-Type, body và field path. |
| Test báo undocumented field | Metadata có field chưa được mô tả ở strict mode. | Bổ sung descriptor hoặc dùng relaxed mode có chủ đích. |
| Part file bị mô tả như JSON field | Nhầm file part với metadata part. | Dùng requestParts cho file; requestPartFields cho structured part. |
| Thiếu response-headers.adoc | Chưa khai báo responseHeaders(...). | Thêm descriptor vào operation. |
| Test lỗi vì thiếu response header | Header mô tả không được server trả. | Sửa implementation hoặc đánh dấu optional nếu hợp đồng cho phép. |
| Asciidoctor không tìm snippet | Sai outputDir, operation ID hoặc tên part trong include path. | Kiểm tra cây thư mục sau test. |
| Tài liệu lộ dữ liệu nhạy cảm | Fixture hoặc response header chứa giá trị thật. | Dùng dữ liệu giả và preprocess/redact trước khi ghi. |

## 11. Bài thực hành

Xây dựng endpoint `POST /api/documents` nhận multipart:

1. Part `metadata` chứa JSON gồm `title`, `category` và `published`.
2. Part `file` chứa file PDF giả nhỏ.
3. Response trả 201 Created cùng header `Location`, `ETag` và `Content-Type`.
4. Viết MockMvc test với hai `MockMultipartFile`.
5. Dùng `requestParts(...)` để mô tả hai part.
6. Dùng `requestPartFields("metadata", ...)` để tạo bảng field metadata.
7. Dùng `responseHeaders(...)` để mô tả ba response header.
8. Include request parts, part fields và response headers vào Asciidoctor; chạy clean test và dựng tài liệu.
9. Cố ý đổi tên field hoặc bỏ response header để quan sát strict validation, sau đó cập nhật implementation/descriptor theo hợp đồng.
10. Rà soát output không chứa file thật hoặc header nhạy cảm.

**Tiêu chí hoàn thành:** giải thích được request part khác field trong part; biết tên snippet được ghép từ part name; mô tả response header bằng descriptor chính xác; hiểu strict/optional/relaxed validation; tạo và include snippet trong tài liệu được build từ test.

## 12. Tài liệu tham khảo

- [Spring REST Docs — Request Parts](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-parts.html)
- [Spring REST Docs — Request Part Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-part-payloads.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [Spring REST Docs 3.0.6 — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring REST Docs 3.0.6 — HeaderDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/headers/HeaderDocumentation.html)
