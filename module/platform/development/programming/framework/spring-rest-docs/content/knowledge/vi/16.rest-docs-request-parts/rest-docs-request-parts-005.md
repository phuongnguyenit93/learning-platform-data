# Content type của từng part trong Spring REST Docs

## 1. Hai cấp Content-Type trong multipart request

Một request `multipart/form-data` có thể chứa file ảnh, PDF, JSON metadata và văn bản trong cùng một HTTP body. Mỗi phần nội dung có thể có kiểu media riêng, vì vậy cần phân biệt:

- **Content-Type cấp request** mô tả toàn bộ HTTP body là multipart và chứa boundary để phân tách các part.
- **Content-Type cấp part** mô tả định dạng nội dung của một part cụ thể, chẳng hạn `image/png`, `application/pdf` hoặc `application/json`.

Ví dụ endpoint `POST /api/products/42/assets` nhận file ảnh và JSON metadata:

```http
POST /api/products/42/assets HTTP/1.1
Accept: application/json
Content-Type: multipart/form-data; boundary=----AssetBoundary

------AssetBoundary
Content-Disposition: form-data; name="image"; filename="cover.png"
Content-Type: image/png

<bytes ảnh PNG>
------AssetBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json; charset=UTF-8

{
  "title": "Bìa sách",
  "description": "Ảnh bìa phiên bản mới"
}
------AssetBoundary--
```

Trong ví dụ này, `multipart/form-data; boundary=...` là Content-Type của request. `image/png` và `application/json; charset=UTF-8` là Content-Type bên trong từng part.

| Vị trí | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| HTTP request | `multipart/form-data; boundary=...` | Body tổng thể có nhiều part |
| Part `image` | `image/png` | Nội dung part là ảnh PNG |
| Part `metadata` | `application/json; charset=UTF-8` | Nội dung part là JSON |
| Part `document` | `application/pdf` | Nội dung part là PDF |

Không nên đặt `Content-Type: image/png` ở cấp request khi request có nhiều part khác loại. Content-Type ngoài phải thể hiện dạng multipart; từng part mới khai báo media type riêng.

Bài này thuộc chương **Request parts** của SPRING_REST_DOCS. Module thực hành tạo tài liệu REST API có thể kiểm chứng từ bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured, sau đó đưa snippet vào Asciidoctor/Markdown và quy trình build/CI.

Sau bài học, bạn có thể:

- Phân biệt Content-Type cấp request với Content-Type cấp part.
- Thiết lập media type cho file và JSON part trong test.
- Hiểu vai trò của `requestParts(...)`, `requestPartBody(...)` và `requestPartFields(...)`.
- Kiểm tra MIME type, nội dung file và khả năng deserialize JSON part.
- Viết test dương tính và âm tính cho các part có media type khác nhau.
- Công bố quy tắc media type trong tài liệu mà không nhầm mô tả với xác thực.

## 2. Content-Type cấp request và boundary

Một request multipart thường có header ngoài:

```http
Content-Type: multipart/form-data; boundary=----AssetBoundary
```

Boundary là chuỗi đánh dấu vị trí bắt đầu và kết thúc các part trong body. HTTP client hoặc multipart builder thường tạo boundary và đảm bảo giá trị trong header khớp nội dung body.

Không nên tự đặt boundary rồi ghép body thủ công nếu không có lý do đặc biệt. Nếu header khai báo boundary khác với boundary thực tế trong body, server không thể phân tích các part đúng cách.

Trong MockMvc, khi dùng:

```java
mockMvc.perform(multipart("/api/products/42/assets")
        .file(image)
        .file(metadata))
```

Spring test builder dựng multipart request và thiết lập Content-Type cấp request phù hợp. Không cần gán `image/png` cho request tổng thể; media type đó phải được gắn vào `MockMultipartFile` tương ứng.

Nếu API chỉ nhận multipart, controller có thể khai báo:

```java
@PostMapping(
    path = "/api/products/{id}/assets",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public ResponseEntity<Void> upload(
        @PathVariable Long id,
        @RequestPart("image") MultipartFile image,
        @RequestPart("metadata") AssetMetadata metadata) {
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
```

`consumes = MULTIPART_FORM_DATA_VALUE` ràng buộc loại request tổng thể. Nó không nói rằng part `image` phải là PNG hoặc part `metadata` phải là JSON; những điều kiện đó cần được xác định và kiểm tra riêng.

## 3. Chỉ định Content-Type cho từng part bằng MockMvc

`MockMultipartFile` có constructor nhận tên part, filename, content type và bytes:

```java
new MockMultipartFile(
    "image",
    "cover.png",
    MediaType.IMAGE_PNG_VALUE,
    imageBytes
);
```

Các tham số quan trọng:

| Tham số | Ví dụ | Vai trò |
| --- | --- | --- |
| `name` | `image` | Tên part trong multipart request |
| `originalFilename` | `cover.png` | Filename do client gửi |
| `contentType` | `image/png` | Content-Type của part |
| `content` | `imageBytes` | Nội dung part |

Ví dụ tạo hai part có kiểu khác nhau:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

MockMultipartFile image = new MockMultipartFile(
        "image",
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

Tên `image` là tên part cần khớp với `@RequestPart("image")` và `partWithName("image")`. Filename `cover.png` không phải tên part. Content-Type `image/png` được gắn cho part ảnh, còn `application/json` được gắn cho metadata.

### 3.1. Dùng MediaType constants hoặc chuỗi MIME chính xác

Spring cung cấp các hằng số thường dùng:

```java
MediaType.IMAGE_PNG
MediaType.IMAGE_JPEG
MediaType.APPLICATION_PDF
MediaType.APPLICATION_JSON
MediaType.TEXT_PLAIN
MediaType.MULTIPART_FORM_DATA
```

Có thể dùng `MediaType.IMAGE_PNG_VALUE` khi API cần chuỗi Content-Type. Với media type tùy chỉnh hoặc vendor media type, ví dụ `application/vnd.example.asset+json`, hãy dùng đúng giá trị contract công bố.

Không nên suy ra Content-Type chỉ từ phần mở rộng filename. `cover.png` có thể được gửi với MIME type khác; filename và header là dữ liệu client khai báo, không chứng minh bytes thật sự là PNG.

## 4. Tài liệu hóa part và Content-Type

Spring REST Docs cung cấp các API ở những cấp khác nhau:

| API | Nội dung tài liệu hóa |
| --- | --- |
| `requestParts(...)` | Các part được operation nhận |
| `partWithName("image")` | Tên và mô tả một part |
| `requestPartBody("metadata")` | Body của part `metadata` |
| `requestPartFields("metadata", ...)` | Các field trong JSON part |
| `requestHeaders(...)` | Header cấp HTTP request |

Ví dụ:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("image")
        .description("Ảnh sản phẩm; gửi dưới dạng PNG hoặc JPEG"),
    partWithName("metadata")
        .description("Metadata JSON mô tả ảnh")
);
```

`requestParts(...)` tạo snippet `request-parts.adoc` mô tả tên và ý nghĩa part. Nó **không tự xác nhận** `image` thực sự có Content-Type `image/png`, cũng không tự sinh một cột MIME type chuẩn từ `MockMultipartFile.getContentType()`.

Vì vậy, nếu Content-Type từng part là một phần quan trọng của contract, hãy thể hiện rõ trong description hoặc bảng contract riêng, ví dụ:

| Part | Content-Type được chấp nhận | Vai trò |
| --- | --- | --- |
| `image` | `image/png`, `image/jpeg` | Ảnh sản phẩm |
| `metadata` | `application/json` | Thông tin mô tả ảnh |
| `caption` | `text/plain` | Chú thích tùy chọn |

Bảng này là phần nội dung tài liệu do nhóm duy trì; muốn đảm bảo nó đúng, cần có test kiểm tra request part thực tế.

### 4.1. Mô tả body JSON riêng

`requestParts(...)` không tạo bảng field `title` và `description` bên trong `metadata`. Dùng:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

.andDo(document("assets-upload",
        requestParts(
            partWithName("image").description("Ảnh PNG hoặc JPEG"),
            partWithName("metadata").description("Metadata JSON")
        ),
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

Các snippet được tạo lần lượt có thể gồm:

```text
request-parts.adoc
request-part-metadata-body.adoc
request-part-metadata-fields.adoc
```

Tên snippet được tạo theo API và tên part. Chỉ include snippet mà test thực sự yêu cầu sinh.

### 4.2. Header ngoài vẫn là một phạm vi khác

Nếu cần tài liệu hóa `Authorization`, `Accept` hoặc Content-Type cấp request, dùng `requestHeaders(...)`:

```java
requestHeaders(
    headerWithName("Authorization")
        .description("Bearer token xác thực"),
    headerWithName("Accept")
        .description("Định dạng response client chấp nhận"),
    headerWithName("Content-Type")
        .description("Multipart request body")
)
```

`requestHeaders(...)` không thay thế việc ghi lại Content-Type của từng part. Các media type trong từng part nên xuất hiện trong request mẫu, bảng contract hoặc custom snippet nếu cần bảng được sinh tự động.

## 5. Ví dụ MockMvc hoàn chỉnh

Giả định endpoint `POST /api/products/{id}/assets` nhận:

- `image`: PNG hoặc JPEG hợp lệ.
- `metadata`: part JSON có `title` bắt buộc và `description` tùy chọn.
- Response thành công: `201 Created`.

Dự án cần Spring Boot, JUnit 5, MockMvc và `spring-restdocs-mockmvc`.

```java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductAssetContentTypeDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentImageAndJsonPartContentTypes() throws Exception {
        MockMultipartFile image = new MockMultipartFile(
                "image",
                "cover.png",
                MediaType.IMAGE_PNG_VALUE,
                TestFixtures.validPng()
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

        mockMvc.perform(multipart("/api/products/{id}/assets", 42)
                    .file(image)
                    .file(metadata)
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andDo(document("products-upload-asset",
                        requestParts(
                                partWithName("image")
                                        .description("Ảnh PNG hoặc JPEG"),
                                partWithName("metadata")
                                        .description("Metadata JSON của ảnh")
                        ),
                        requestPartBody("metadata"),
                        requestPartFields("metadata",
                                fieldWithPath("title")
                                        .description("Tiêu đề ảnh"),
                                fieldWithPath("description")
                                        .description("Mô tả ảnh")
                                        .optional()
                        )
                ));
    }
}
```

`TestFixtures.validPng()` là helper minh họa, cần thay bằng ảnh PNG hợp lệ trong test resources. Nếu endpoint kiểm tra chữ ký file, một dãy byte tùy ý có thể bị từ chối dù Content-Type được khai báo là `image/png`.

Test trên sinh snippet part, body JSON và fields JSON. Nó **chưa tự tạo bảng Content-Type cho từng part**. Content-Type được chỉ định khi tạo `MockMultipartFile`; endpoint validation và các test khác phải xác nhận server chấp nhận đúng các media type.

## 6. Kiểm tra Content-Type trong controller

Khi controller nhận part file bằng `MultipartFile`, ứng dụng có thể kiểm tra Content-Type mà client khai báo:

```java
private void validateImageContentType(MultipartFile image) {
    String contentType = image.getContentType();

    if (!MediaType.IMAGE_PNG_VALUE.equals(contentType)
            && !MediaType.IMAGE_JPEG_VALUE.equals(contentType)) {
        throw new ResponseStatusException(
                HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                "Only PNG and JPEG images are supported"
        );
    }
}
```

Đây là kiểm tra header MIME do client gửi. Nó không xác nhận bytes thực sự là ảnh PNG hoặc JPEG. Nếu cần bảo đảm định dạng nội dung, hãy kiểm tra file signature hoặc parse nội dung bằng thư viện hình ảnh thích hợp; không chỉ tin vào Content-Type hoặc filename.

### 6.1. JSON part và HttpMessageConverter

Khi controller nhận metadata bằng `@RequestPart` dưới dạng DTO:

```java
@PostMapping(
    path = "/api/products/{id}/assets",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public ResponseEntity<Void> upload(
        @PathVariable Long id,
        @RequestPart("image") MultipartFile image,
        @Valid @RequestPart("metadata") AssetMetadata metadata) {

    // Xác thực file và lưu tài sản.
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
```

Spring MVC dùng `HttpMessageConverter` phù hợp với Content-Type của part để chuyển body JSON thành `AssetMetadata`. Nếu part JSON khai báo sai media type hoặc body không phải JSON hợp lệ, quá trình chuyển đổi có thể thất bại trước khi controller xử lý.

DTO ví dụ:

```java
import jakarta.validation.constraints.NotBlank;

record AssetMetadata(
        @NotBlank String title,
        String description
) {}
```

Cần bật validation và có dependency phù hợp nếu muốn `@Valid` thực thi các ràng buộc. `requestPartFields(...)` giúp tài liệu hóa JSON nhưng không tự kiểm tra `title` không rỗng; validation và negative tests mới xác minh quy tắc đó.

## 7. Viết test âm tính cho media type và nội dung

Một nhóm test upload tốt cần kiểm tra cả header Content-Type và bytes thực tế.

| Trường hợp | Kết quả minh họa | Lý do |
| --- | --- | --- |
| PNG có MIME `image/png`, bytes PNG hợp lệ | Thành công | Đúng media type và định dạng |
| JPEG có MIME `image/jpeg`, bytes JPEG hợp lệ | Thành công nếu contract cho phép | Định dạng được hỗ trợ |
| Part ảnh có MIME `text/plain` | `415` hoặc lỗi theo contract | Content-Type không được hỗ trợ |
| MIME khai báo `image/png` nhưng bytes không phải PNG | Bị từ chối nếu kiểm tra chữ ký file | Không tin MIME client tự khai |
| Metadata có `application/json` và JSON hợp lệ | Thành công | Converter có thể deserialize |
| Metadata có `text/plain` nhưng endpoint yêu cầu JSON | Bị từ chối theo cấu hình converter | Media type không phù hợp |
| Metadata JSON thiếu `title` | Lỗi validation | Vi phạm contract DTO |

Ví dụ test part ảnh sai MIME:

```java
@Test
void rejectUnsupportedImageMediaType() throws Exception {
    MockMultipartFile image = new MockMultipartFile(
            "image",
            "cover.txt",
            MediaType.TEXT_PLAIN_VALUE,
            "not an image".getBytes(StandardCharsets.UTF_8)
    );

    MockMultipartFile metadata = new MockMultipartFile(
            "metadata",
            "",
            MediaType.APPLICATION_JSON_VALUE,
            """
            {"title":"Bìa sách"}
            """.getBytes(StandardCharsets.UTF_8)
    );

    mockMvc.perform(multipart("/api/products/{id}/assets", 42)
                .file(image)
                .file(metadata))
            .andExpect(status().isUnsupportedMediaType());
}
```

Assertion `415` chỉ phù hợp nếu endpoint ánh xạ loại media không hỗ trợ thành `Unsupported Media Type`. Nếu ứng dụng quy định response lỗi khác hoặc controller dùng `400`, hãy viết test theo contract thực tế.

Một test khác nên gửi `image/png` với bytes không hợp lệ để đảm bảo server không chỉ tin header. Đó là kiểm tra nội dung file, không phải chức năng của Spring REST Docs.

## 8. WebTestClient và REST Assured

### 8.1. WebTestClient

Với WebTestClient, có thể gắn header riêng cho từng part bằng `HttpEntity` trong `MultiValueMap`:

```java
HttpHeaders metadataHeaders = new HttpHeaders();
metadataHeaders.setContentType(MediaType.APPLICATION_JSON);

HttpEntity<String> metadataPart =
        new HttpEntity<>(metadataJson, metadataHeaders);

HttpHeaders imageHeaders = new HttpHeaders();
imageHeaders.setContentType(MediaType.IMAGE_PNG);

HttpEntity<Resource> imagePart =
        new HttpEntity<>(imageResource, imageHeaders);

MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
parts.add("image", imagePart);
parts.add("metadata", metadataPart);

webTestClient.post()
        .uri("/api/products/42/assets")
        .contentType(MediaType.MULTIPART_FORM_DATA)
        .body(BodyInserters.fromMultipartData(parts))
        .exchange()
        .expectStatus().isCreated()
        .expectBody()
        .consumeWith(document("products-upload-asset",
                requestParts(
                        partWithName("image").description("Ảnh PNG hoặc JPEG"),
                        partWithName("metadata").description("Metadata JSON")
                )
        ));
```

Đoạn code minh họa cách gắn media type với từng `HttpEntity`; import, resource filename và converter cần điều chỉnh theo loại payload và cấu hình WebTestClient của dự án. Content-Type cấp ngoài vẫn là `multipart/form-data`.

### 8.2. REST Assured

REST Assured có các overload multipart cho phép truyền content type của part:

```java
given(this.spec)
        .filter(document("products-upload-asset",
                requestParts(
                        partWithName("image").description("Ảnh PNG hoặc JPEG"),
                        partWithName("metadata").description("Metadata JSON")
                )))
        .multiPart("image", imageFile, "image/png")
        .multiPart("metadata", metadataJson, "application/json")
        .when()
        .post("/api/products/42/assets")
        .then()
        .statusCode(201);
```

Kiểm tra overload cụ thể theo phiên bản REST Assured đang dùng. Điều cần xác nhận là Content-Type thực sự được gắn vào mỗi part trên wire, không chỉ là giá trị truyền trong test builder.

## 9. Ghi rõ Content-Type trong tài liệu

Vì `requestParts(...)` tập trung vào tên và mô tả part, có thể ghi MIME type ngay trong description:

```java
requestParts(
    partWithName("image")
        .description("Ảnh sản phẩm; Content-Type image/png hoặc image/jpeg"),
    partWithName("metadata")
        .description("Metadata JSON; Content-Type application/json")
);
```

Nếu bảng cần một cột riêng, tạo bảng contract trong Asciidoctor:

```adoc
=== Content-Type của từng part

|===
|Part |Content-Type |Quy tắc

|`image`
|`image/png`, `image/jpeg`
|Bytes phải là ảnh hợp lệ thuộc một trong hai định dạng

|`metadata`
|`application/json`
|JSON có trường `title` bắt buộc
|===
```

Bảng này làm rõ contract cho client. Muốn bảng không bị lỗi thời, kiểm thử nên xác nhận từng media type được chấp nhận và những media type bị từ chối.

Nếu cần bảng tự sinh từ request test, có thể tạo custom snippet từ `OperationRequestPart.getHeaders()`; phần custom cần tự định nghĩa output, template và cách xử lý header. Đừng giả định `request-parts.adoc` mặc định có cột Content-Type.

## 10. Asciidoctor và build/CI

Có thể include các snippet đã được test tạo ra:

```adoc
= Product Asset API
:toc: left

== Upload ảnh và metadata

=== Các part
include::{snippets}/products-upload-asset/request-parts.adoc[]

=== Metadata body
include::{snippets}/products-upload-asset/request-part-metadata-body.adoc[]

=== Metadata fields
include::{snippets}/products-upload-asset/request-part-metadata-fields.adoc[]

=== Media type contract
Xem bảng Content-Type của từng part trong phần hợp đồng multipart.
```

Với Gradle và plugin Asciidoctor đã cấu hình:

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
        +--> Kiểm tra Content-Type ngoài
        |
        +--> Kiểm tra Content-Type từng part
        |
        +--> requestParts / requestPartBody / requestPartFields
        |
        v
Generated snippets
        |
        v
Asciidoctor / bước xuất Markdown
        |
        v
Kiểm tra và xuất bản tài liệu
```

Khi contract đổi từ PNG-only sang PNG/JPEG, phải cập nhật controller validation, test dương tính/âm tính và bảng tài liệu. Không sửa snippet generated thủ công để làm CI xanh. Spring REST Docs thường sinh AsciiDoc; Markdown cần template hoặc bước chuyển đổi riêng.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Request bị từ chối vì outer Content-Type sai | Gán `image/png` cho toàn request | Dùng `multipart/form-data`; đặt MIME riêng cho từng part |
| Metadata không deserialize thành DTO | Part không có `application/json` hoặc body JSON sai | Thiết lập content type và xác nhận converter |
| `request-parts.adoc` không có cột MIME type | Snippet mặc định mô tả part, không phải bảng media type | Ghi trong description/bảng contract hoặc custom snippet |
| File `.png` vẫn bị từ chối | Header hoặc bytes không đúng định dạng được hỗ trợ | Kiểm tra cả MIME type và chữ ký file |
| File MIME khai báo đúng nhưng bytes giả | Tin Content-Type do client cung cấp | Thêm kiểm tra nội dung thực tế |
| `requestHeaders(...)` chỉ hiện multipart | Đang tài liệu hóa header cấp request | Ghi MIME từng part trong bảng contract hoặc custom snippet |
| Test JSON part lỗi converter | Part JSON có content type không phù hợp | Đặt `application/json` và kiểm tra module converter |
| Asciidoctor thiếu snippet | Test chưa tạo snippet hoặc include sai tên | Kiểm tra operation ID và task dependency |

## 12. Bài thực hành

Với endpoint `POST /api/products/{id}/assets`:

1. Tạo part `image` với `image/png` và part `metadata` với `application/json`. Xác nhận outer request vẫn là `multipart/form-data`.
2. Đổi Content-Type của `image` sang `text/plain`; viết test xác nhận server từ chối theo contract.
3. Gửi header `image/png` nhưng dùng bytes không phải PNG. Bổ sung kiểm tra chữ ký file và test âm tính.
4. Đổi Content-Type của metadata sang `text/plain`; xác nhận JSON DTO không được deserialize như request hợp lệ.
5. Thêm `requestPartFields("metadata", ...)` để mô tả `title` và `description`.
6. Viết bảng Asciidoctor nêu Content-Type được chấp nhận cho từng part.
7. Nếu cần bảng được sinh tự động, thiết kế custom snippet đọc headers của `OperationRequestPart`.
8. Chạy test tài liệu hóa và negative tests trước khi Asciidoctor kết xuất tài liệu trong CI.

### Câu hỏi tự đánh giá

- Content-Type của toàn request khác Content-Type của part như thế nào?
- Boundary thuộc lớp nào?
- `MockMultipartFile` nhận Content-Type của part ở tham số nào?
- `requestParts(...)` có tự kiểm tra hoặc tạo cột MIME type không?
- Vì sao file có filename `.png` và header `image/png` vẫn có thể không phải ảnh PNG hợp lệ?
- Khi nào dùng `requestPartFields(...)` thay vì chỉ `requestParts(...)`?
- Cần kiểm tra gì khi thay đổi danh sách MIME type được chấp nhận?

**Ghi nhớ:** `multipart/form-data` là Content-Type của request tổng thể; mỗi part có thể mang một Content-Type riêng. Thiết lập MIME type trong request builder chỉ tạo header cho test, còn endpoint cần xác thực media type và nội dung. `requestParts(...)` mô tả part; hãy dùng bảng contract hoặc custom snippet nếu cần công bố Content-Type của từng part thành một cột riêng.

## Tài liệu tham khảo

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): request parts và tài liệu hóa multipart.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): body và field của JSON part.
- [Spring Framework — `@RequestPart` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestPart.html): cách Spring MVC chuyển đổi nội dung part theo converter.
- [Spring Framework — `MultipartFile` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html): tên file, content type và nội dung file được upload.
