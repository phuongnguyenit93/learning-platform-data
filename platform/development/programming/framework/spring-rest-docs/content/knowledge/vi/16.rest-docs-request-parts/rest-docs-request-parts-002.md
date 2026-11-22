# `partWithName` và cách mô tả request part trong Spring REST Docs

## 1. Vai trò của `partWithName(...)`

Một multipart request chia request body thành nhiều part có tên riêng. Mỗi part có thể mang một file nhị phân, một đoạn JSON, văn bản hoặc một loại nội dung khác. Khi tài liệu hóa operation upload, người đọc cần biết API mong đợi những part nào và mục đích của từng part.

Trong **Spring REST Docs**, `partWithName("...")` tạo descriptor cho một part theo đúng tên trong multipart request. `requestParts(...)` nhận các descriptor đó và sinh snippet `request-parts.adoc`.

Ví dụ, endpoint `POST /api/products/{id}/images` nhận hai part:

- `file`: ảnh cần tải lên.
- `metadata`: JSON chứa tiêu đề và mô tả ảnh.

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("file")
        .description("Ảnh sản phẩm cần tải lên"),
    partWithName("metadata")
        .description("Metadata JSON của ảnh")
);
```

Tên API chuẩn là `partWithName(...)`, thuộc `RequestDocumentation`. Phương thức này trả về descriptor cho part; `.description(...)` giải thích ý nghĩa của part đối với client. `requestParts(...)` tổng hợp các descriptor để tài liệu hóa tập part của operation.

Bài học thuộc chương **Request parts** của SPRING_REST_DOCS: tạo tài liệu REST API từ kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured, sau đó kết hợp snippet với Asciidoctor/Markdown và build/CI.

Sau bài này, bạn có thể:

- Dùng `partWithName(...)` để định danh đúng part.
- Viết description ngắn gọn nhưng có ngữ cảnh về nội dung và mục đích.
- Phân biệt part descriptor với field descriptor của JSON nằm bên trong part.
- Xử lý part required, optional và ignored.
- Tổ chức descriptor dùng chung, tránh tên part sai lệch giữa test, controller và tài liệu.

## 2. Tên part phải khớp multipart request

Tên được truyền vào `partWithName(...)` là tên part trong multipart body, thường thể hiện qua tham số `name` của header `Content-Disposition`.

Ví dụ request:

```http
POST /api/products/42/images HTTP/1.1
Content-Type: multipart/form-data; boundary=----Boundary

------Boundary
Content-Disposition: form-data; name="file"; filename="cover.png"
Content-Type: image/png

<binary image data>
------Boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Bìa sách","description":"Ảnh bìa phiên bản mới"}
------Boundary--
```

Các tên part là `file` và `metadata`. Vì vậy descriptor phải dùng đúng hai tên này:

```java
requestParts(
    partWithName("file").description("Ảnh sản phẩm"),
    partWithName("metadata").description("Metadata JSON")
);
```

Các cách viết sau là khác nhau và không tự động tương đương:

- `partWithName("metadata")`
- `partWithName("meta")`
- `partWithName("Metadata")`

Tên part cần thống nhất với client, controller và test. Nếu controller dùng `@RequestPart("metadata")`, descriptor cũng cần trỏ đến `metadata`.

### 2.1. Tên part không phải tên file

Trong một part upload file, `Content-Disposition` có thể có cả `name` và `filename`:

```http
Content-Disposition: form-data; name="file"; filename="cover.png"
```

- `name="file"` là tên part, dùng trong `partWithName("file")`.
- `filename="cover.png"` là tên file do client cung cấp; nó không phải đối số của `partWithName(...)`.

Nếu client đổi tên file thành `product-cover-final.png` nhưng vẫn gửi part tên `file`, descriptor không cần đổi. Tên file và metadata liên quan cần được tài liệu hóa ở phần mô tả riêng khi client cần biết.

### 2.2. Không nhầm tên part với JSON path

Với part `metadata` chứa:

```json
{
  "title": "Bìa sách",
  "description": "Ảnh bìa phiên bản mới"
}
```

`partWithName("metadata")` xác định **toàn bộ part**. Các đường dẫn `title` và `description` bên trong JSON thuộc phạm vi `requestPartFields("metadata", ...)`, không phải các đối số cho `partWithName(...)`.

## 3. Viết description tốt cho từng part

Description của part nên trả lời ba câu hỏi:

1. Part chứa loại dữ liệu gì?
2. Dữ liệu đó dùng để làm gì trong operation?
3. Có yêu cầu quan trọng nào client cần biết ngay không?

Ví dụ:

| Tên part | Mô tả yếu | Mô tả tốt hơn |
| --- | --- | --- |
| `file` | `File` | `Ảnh sản phẩm cần tải lên` |
| `metadata` | `Dữ liệu` | `Metadata JSON mô tả ảnh sản phẩm` |
| `document` | `Tài liệu` | `Tệp PDF hợp đồng đã ký` |
| `signature` | `Chữ ký` | `Ảnh chữ ký của người gửi` |
| `attachments` | `Danh sách` | `Các tệp đính kèm của yêu cầu` |

Description có thể ghi rõ định dạng nếu định dạng là một phần của contract:

```java
partWithName("file")
    .description("Ảnh sản phẩm ở định dạng PNG hoặc JPEG");
```

Tuy nhiên, `.description(...)` chỉ ghi thông tin cho người đọc. Nó không xác thực MIME type, nội dung file, kích thước hoặc chữ ký nhị phân. Các ràng buộc này cần được kiểm tra ở endpoint và trong các bài test HTTP.

### 3.1. Dùng thuật ngữ nghiệp vụ nhất quán

Nếu phần tài liệu gọi `product` là “sản phẩm”, hãy dùng cùng thuật ngữ trong các operation:

- `Ảnh sản phẩm cần tải lên`
- `Metadata mô tả sản phẩm`
- `Tài liệu chứng minh nguồn gốc sản phẩm`

Tránh description chỉ lặp lại tên part hoặc dùng từ chung chung như “data”, “info”, “content” mà không giải thích vai trò.

### 3.2. Giữ description ngắn, quy tắc dài đặt riêng

Một câu ngắn thường đủ cho bảng parts:

```java
partWithName("file")
    .description("Ảnh sản phẩm cần tải lên");
```

Nếu cần mô tả chi tiết hơn, có thể viết ở phần operation trong tài liệu Asciidoctor: định dạng được chấp nhận, giới hạn dung lượng, cách xử lý tên file, quy tắc virus scanning hoặc metadata bắt buộc. Không nên nhồi tất cả vào một description dài khó đọc.

## 4. Descriptor bắt buộc, optional và ignored

`partWithName(...)` trả về descriptor có các tùy chọn mô tả trạng thái part.

### 4.1. Part bắt buộc

```java
requestParts(
    partWithName("file")
        .description("Ảnh sản phẩm cần tải lên"),
    partWithName("metadata")
        .description("Metadata JSON của ảnh")
);
```

Trong strict `requestParts(...)`, part đã khai báo là bắt buộc theo mặc định. Nếu request mẫu không có part đó, việc sinh snippet có thể thất bại. Đây là tín hiệu để đối chiếu fixture với contract API.

### 4.2. Part optional

Giả sử `thumbnail` chỉ được client gửi khi có ảnh xem trước:

```java
requestParts(
    partWithName("file")
        .description("Ảnh sản phẩm cần tải lên"),
    partWithName("metadata")
        .description("Metadata JSON của ảnh"),
    partWithName("thumbnail")
        .description("Ảnh xem trước, nếu có")
        .optional()
);
```

`.optional()` cho phép part đã khai báo vắng mặt trong request mẫu. Nó không có nghĩa nội dung part được phép rỗng, null hay sai định dạng. Các quy tắc đó cần xác định riêng cho contract.

### 4.3. Part ignored

Một part kỹ thuật có thể được nhận diện nhưng không cần đưa vào bảng:

```java
requestParts(
    partWithName("file")
        .description("Ảnh sản phẩm cần tải lên"),
    partWithName("metadata")
        .description("Metadata JSON của ảnh"),
    partWithName("clientTrace")
        .description("Mã trace dùng để liên kết log")
        .ignored()
);
```

`clientTrace` được khai báo để tránh coi nó là part chưa được xử lý trong chế độ strict, nhưng không xuất hiện như một dòng trong snippet. `.ignored()` không xóa part khỏi request, không ngăn server đọc nó và không phải biện pháp bảo vệ dữ liệu.

Nếu part ignored có thể vắng trong payload mẫu, kết hợp `.optional()`:

```java
partWithName("clientTrace")
    .description("Mã trace nếu client cung cấp")
    .optional()
    .ignored();
```

### 4.4. Strict và relaxed request parts

Nếu operation cho phép part mở rộng chưa liệt kê, có thể dùng `relaxedRequestParts(...)`:

```java
import static org.springframework.restdocs.request.RequestDocumentation.relaxedRequestParts;

relaxedRequestParts(
    partWithName("file").description("Ảnh sản phẩm"),
    partWithName("metadata").description("Metadata JSON")
);
```

Với relaxed mode, part chưa có descriptor được phép tồn tại. Các descriptor đã khai báo vẫn phải có mặt, trừ khi optional. Đổi lại, test không còn phát hiện mọi part mới chưa được công bố.

| Cơ chế | Part đã khai báo | Part dư chưa khai báo | Hiển thị |
| --- | --- | --- | --- |
| `requestParts(...)` | Kiểm tra theo descriptor | Có thể làm test thất bại | Có, trừ ignored |
| `requestParts(...)` + `.ignored()` | Nhận diện nhưng không đưa vào bảng | Strict mode vẫn phát hiện | Không hiện part ignored |
| `relaxedRequestParts(...)` | Kiểm tra theo descriptor | Được phép tồn tại | Chỉ descriptor không ignored |
| `.optional()` | Cho phép descriptor vắng trong request mẫu | Không ảnh hưởng part dư | Không làm part bị ẩn |

Chọn relaxed mode khi multipart contract thực sự cho phép mở rộng. Đối với operation có các part công khai ổn định, strict mode giúp phát hiện part mới để cập nhật tài liệu.

## 5. Ví dụ hoàn chỉnh với MockMvc

Giả sử endpoint `POST /api/products/{id}/images` nhận:

- `file`: file ảnh bắt buộc.
- `metadata`: JSON bắt buộc.
- `thumbnail`: file xem trước tùy chọn.

Endpoint trả `201 Created` khi upload hợp lệ. Dự án đã cấu hình Spring Boot, JUnit 5, MockMvc và `spring-restdocs-mockmvc`.

### 5.1. Tạo MockMultipartFile

```java
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

MockMultipartFile file = new MockMultipartFile(
        "file",
        "cover.png",
        MediaType.IMAGE_PNG_VALUE,
        validPngBytes
);

String metadataJson = """
        {
          "title": "Bìa sách",
          "description": "Ảnh bìa phiên bản mới"
        }
        """;

MockMultipartFile metadata = new MockMultipartFile(
        "metadata",
        "",
        MediaType.APPLICATION_JSON_VALUE,
        metadataJson.getBytes(StandardCharsets.UTF_8)
);
```

Đối số đầu tiên của `MockMultipartFile` là tên part. Đối số thứ hai là filename. Vì vậy, `"file"` phải khớp `partWithName("file")`; `"cover.png"` không phải tên part.

Trong test thực tế, dùng fixture PNG hợp lệ nếu endpoint kiểm tra định dạng hoặc nội dung file. Byte giả lập tùy ý chỉ phù hợp với ví dụ đơn giản mà controller không phân tích ảnh.

### 5.2. Sinh request-parts snippet

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductImageUploadDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentProductImageParts() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "cover.png",
                MediaType.IMAGE_PNG_VALUE,
                validPngBytes()
        );

        String metadataJson = """
                {
                  "title": "Bìa sách",
                  "description": "Ảnh bìa phiên bản mới"
                }
                """;

        MockMultipartFile metadata = new MockMultipartFile(
                "metadata",
                "",
                MediaType.APPLICATION_JSON_VALUE,
                metadataJson.getBytes(StandardCharsets.UTF_8)
        );

        mockMvc.perform(multipart("/api/products/{id}/images", 42)
                    .file(file)
                    .file(metadata)
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andDo(document("products-upload-image",
                        requestParts(
                                partWithName("file")
                                        .description("Ảnh sản phẩm cần tải lên"),
                                partWithName("metadata")
                                        .description("Metadata JSON mô tả ảnh"),
                                partWithName("thumbnail")
                                        .description("Ảnh xem trước nếu có")
                                        .optional()
                        )));
    }

    private byte[] validPngBytes() {
        // Trả về bytes của fixture PNG hợp lệ trong test resources.
        return TestFixtures.validPng();
    }
}
```

Các import và fixture `TestFixtures` là ví dụ minh họa; thay bằng resource test thực tế của dự án. Điều quan trọng là tên part trong `MockMultipartFile` phải trùng với descriptor, và request phải đi qua operation được tài liệu hóa.

Sau khi test thành công, Spring REST Docs sinh snippet trong:

```text
build/generated-snippets/
└── products-upload-image/
    ├── http-request.adoc
    ├── http-response.adoc
    └── request-parts.adoc
```

Tên và số lượng snippet bổ sung phụ thuộc cấu hình. `request-parts.adoc` là output từ `requestParts(...)`.

## 6. Tổ chức descriptor dùng chung

Khi nhiều test tài liệu hóa cùng một operation hoặc các biến thể của multipart request, nên tách descriptor để tránh sao chép và tạo khác biệt không chủ ý.

```java
import org.springframework.restdocs.request.RequestPartDescriptor;

import static org.springframework.restdocs.request.RequestDocumentation.partWithName;

private static final RequestPartDescriptor[] PRODUCT_IMAGE_PARTS = {
        partWithName("file")
                .description("Ảnh sản phẩm cần tải lên"),
        partWithName("metadata")
                .description("Metadata JSON mô tả ảnh"),
        partWithName("thumbnail")
                .description("Ảnh xem trước nếu có")
                .optional()
};
```

Sau đó tái sử dụng:

```java
.andDo(document("products-upload-image",
        requestParts(PRODUCT_IMAGE_PARTS)
));
```

Việc tái sử dụng có ích khi cùng một contract được test ở nhiều kịch bản. Tuy nhiên, đừng dùng chung descriptor cho các operation có ý nghĩa part khác nhau chỉ vì chúng trùng tên. Description phải đúng với contract của operation cụ thể.

### 6.1. Tổ chức theo nhóm part

Với operation lớn có nhiều part, có thể phân nhóm trong mã nguồn:

- Part nghiệp vụ: `file`, `metadata`.
- Part bổ sung: `thumbnail`, `attachments`.
- Part kỹ thuật: `clientTrace`.

Các nhóm này chỉ là cách tổ chức code. Trong multipart HTTP, tất cả vẫn là part cùng cấp của request body trừ khi body part chứa một cấu trúc lồng riêng như JSON hoặc archive.

## 7. Part descriptor không thay thế mô tả nội dung bên trong part

`partWithName("metadata")` chỉ mô tả part `metadata` ở cấp multipart. Nếu part đó chứa JSON:

```json
{
  "title": "Bìa sách",
  "description": "Ảnh bìa phiên bản mới"
}
```

thì `requestParts(...)` không tự sinh bảng các field `title` và `description`.

Có ba mức tài liệu hóa:

| API | Nội dung | Snippet |
| --- | --- | --- |
| `requestParts(...)` | Tên và ý nghĩa từng part | `request-parts.adoc` |
| `requestPartBody("metadata")` | Body nguyên bản của part | `request-part-metadata-body.adoc` |
| `requestPartFields("metadata", ...)` | Các field trong JSON part | `request-part-metadata-fields.adoc` |

Ví dụ:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

.andDo(document("products-upload-image",
        requestParts(PRODUCT_IMAGE_PARTS),
        requestPartBody("metadata"),
        requestPartFields("metadata",
                fieldWithPath("title")
                        .description("Tiêu đề ảnh"),
                fieldWithPath("description")
                        .description("Mô tả ảnh")
                        .optional()
        )
));
```

`requestPartBody` cho người đọc xem ví dụ body. `requestPartFields` mô tả schema JSON bên trong part. Đây là hai nhu cầu khác nhau; chỉ thêm khi người dùng API cần thông tin tương ứng.

## 8. Những gì description không tự xác thực

Description có thể ghi `Ảnh PNG tối đa 5 MB`, nhưng `partWithName(...)` không kiểm tra những điều kiện đó. Cần test HTTP hoặc validation riêng cho:

- Content type cho phép.
- Nội dung file thực sự tương ứng với MIME type.
- Kích thước file.
- Tên file và ký tự được phép.
- Metadata part là JSON hợp lệ.
- Trường bắt buộc trong metadata.
- Phần mở rộng filename có được phép không.

Ví dụ contract:

| Part | Required | Content type | Quy tắc minh họa |
| --- | --- | --- | --- |
| `file` | Có | `image/png` hoặc `image/jpeg` | File ảnh hợp lệ, tối đa 5 MB |
| `metadata` | Có | `application/json` | Có `title` không rỗng |
| `thumbnail` | Không | `image/jpeg` | File xem trước, tối đa 1 MB |
| `clientTrace` | Không | `text/plain` | Mã liên kết log |

Các điều kiện trong bảng là ví dụ, phải thay bằng contract thực. Một bộ negative tests nên kiểm tra file quá lớn, MIME type không hỗ trợ, metadata sai JSON hoặc thiếu title.

## 9. Kết hợp với Asciidoctor và build/CI

Tài liệu Asciidoctor có thể include snippet:

```adoc
= Product Image API
:toc: left

== Upload ảnh sản phẩm

=== Các part của request
include::{snippets}/products-upload-image/request-parts.adoc[]

=== Body metadata
include::{snippets}/products-upload-image/request-part-metadata-body.adoc[]

=== Các trường metadata
include::{snippets}/products-upload-image/request-part-metadata-fields.adoc[]
```

Chỉ include các snippet mà test đã cấu hình sinh. Nếu operation chỉ gọi `requestParts(...)`, không có snippet body hoặc part fields để include.

Với Gradle và plugin Asciidoctor đã được cấu hình, nối task tài liệu với test sinh snippets:

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
requestParts descriptors
        |
        v
request-parts.adoc
        |
        v
Asciidoctor / bước xuất Markdown
        |
        v
Kiểm tra và xuất bản tài liệu
```

Khi thêm part mới, strict `requestParts(...)` có thể làm test thất bại nếu chưa được mô tả. Nhóm cần quyết định có công bố part, ignore có chủ đích hay cập nhật contract. Không chỉnh snippet generated thủ công để làm build xanh.

Spring REST Docs thường sinh snippet AsciiDoc. Nếu dự án phát hành Markdown, cần template hoặc bước chuyển đổi riêng; không mặc định có `request-parts.md`.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy part | Tên `MockMultipartFile` khác `partWithName(...)` | Đồng bộ tên giữa request, controller và descriptor |
| Test báo part chưa tài liệu hóa | Có part mới nhưng strict `requestParts(...)` chưa khai báo | Thêm descriptor, ignore có chủ đích hoặc relaxed theo contract |
| Test báo thiếu part | Descriptor required nhưng request mẫu không gửi | Bổ sung part hoặc `.optional()` nếu contract cho phép |
| Part ignored vẫn có trong request | `.ignored()` chỉ ẩn dòng trong snippet | Đây là hành vi đúng; nó không xóa part |
| Không có bảng metadata field | Chỉ gọi `requestParts(...)` | Dùng `requestPartFields("metadata", ...)` |
| Không có JSON body snippet | Chưa gọi `requestPartBody("metadata")` | Bổ sung nếu cần ví dụ body |
| Multipart endpoint không nhận file | Tên part, filename hoặc cách dựng body sai | Kiểm tra `Content-Disposition`, content type và request builder |
| Asciidoctor báo thiếu include | Tài liệu include snippet chưa được sinh | Kiểm tra operation id, test task và output directory |

## 11. Bài thực hành

Dựa trên `POST /api/products/{id}/images`:

1. Khai báo `file` và `metadata` bằng `partWithName(...)`; viết description thể hiện rõ mục đích của từng part.
2. Thêm `thumbnail` là optional và chạy hai test có/không có part này.
3. Thêm `clientTrace`, đánh dấu `.ignored()`. Kiểm tra part vẫn được gửi nhưng không có dòng trong `request-parts.adoc`.
4. Đổi tên part request từ `metadata` thành `meta` mà không đổi descriptor. Quan sát lỗi rồi sửa đúng contract.
5. Thêm JSON field `title` và `description` trong metadata; dùng `requestPartFields(...)` để mô tả bên trong part.
6. Dùng `requestPartBody(...)` để include JSON nguyên bản và phân biệt mục đích với bảng fields.
7. Viết negative tests cho MIME type sai, file vượt dung lượng và metadata thiếu `title`.
8. Include snippet vào Asciidoctor và bảo đảm CI chạy test trước khi kết xuất.

### Câu hỏi tự đánh giá

- `partWithName("file")` trỏ đến `name` hay `filename` trong `Content-Disposition`?
- `.description(...)` của part giúp người dùng API hiểu điều gì?
- `.optional()` khác `.ignored()` như thế nào?
- Khi nào nên dùng `relaxedRequestParts(...)`?
- Vì sao `requestParts(...)` không mô tả field JSON bên trong part metadata?
- Khi nào dùng `requestPartBody(...)` và khi nào dùng `requestPartFields(...)`?
- Vì sao mô tả `image/png` không thay thế test kiểm tra nội dung file?

**Ghi nhớ:** `partWithName(...)` xác định một part theo đúng tên trong multipart request; `.description(...)` giải thích mục đích của part; `requestParts(...)` gom descriptor và sinh snippet bảng part. Tên part phải khớp request thực tế, còn nội dung JSON bên trong part cần `requestPartBody` hoặc `requestPartFields` khi tài liệu yêu cầu mức chi tiết đó.

## Tài liệu tham khảo

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): cách tài liệu hóa multipart parts và snippet tương ứng.
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html): `partWithName`, `requestParts` và `relaxedRequestParts`.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): tài liệu hóa các field trong JSON part.
