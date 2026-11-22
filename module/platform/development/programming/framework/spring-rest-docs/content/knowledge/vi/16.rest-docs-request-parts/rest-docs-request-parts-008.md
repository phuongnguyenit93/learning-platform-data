# Xác nhận multipart request bằng MockMvc

## 1. Vì sao cần kiểm thử multipart request?

Một operation upload thường nhận nhiều loại nội dung trong một HTTP request: file nhị phân, JSON metadata và đôi khi cả text field hoặc file xem trước. Với `multipart/form-data`, mỗi phần được gửi thành một **part** có tên riêng, có thể có `Content-Type`, filename và header riêng.

Ví dụ `POST /api/products/42/assets` nhận:

- `image`: file ảnh PNG hoặc JPEG.
- `metadata`: JSON mô tả ảnh.
- `caption`: text tùy chọn.

MockMvc cho phép dựng request multipart trong bộ kiểm thử Spring MVC mà không cần mở cổng HTTP thật. Ta có thể xác nhận controller bind đúng part, kiểm tra status/body response, kiểm tra validation và dùng chính request đó để sinh snippet Spring REST Docs.

Trong module **SPRING_REST_DOCS**, các bài kiểm thử này là nguồn dữ liệu cho tài liệu REST API. `requestParts(...)` mô tả tên và vai trò các part; `requestPartFields(...)` mô tả field bên trong JSON part; `requestPartBody(...)` đưa ví dụ body của part vào tài liệu.

Sau bài học, bạn có thể:

- Dựng multipart request bằng `MockMvcRequestBuilders.multipart(...)`.
- Dùng `MockMultipartFile` cho file và `MockPart` cho part tổng quát như JSON.
- Gắn Content-Type đúng cho từng part và kiểm tra kết quả binding.
- Kiểm thử part required, optional, absent, empty và file zero-byte.
- Kết hợp MockMvc với `requestParts`, `requestPartFields` và `requestPartBody`.
- Nhận biết giới hạn của MockMvc so với kiểm thử qua servlet container thật.
- Đưa test và snippet vào build/CI.

## 2. Request multipart trong MockMvc

Một request multipart có hai lớp cấu trúc:

```text
HTTP request
Content-Type: multipart/form-data; boundary=...

  Part "image"
    Content-Disposition: form-data; name="image"; filename="cover.png"
    Content-Type: image/png
    Body: <binary bytes>

  Part "metadata"
    Content-Disposition: form-data; name="metadata"
    Content-Type: application/json
    Body: {"title":"Bìa sách"}
```

Content-Type ở cấp request là `multipart/form-data`; boundary chia các part. Mỗi part có thể có Content-Type riêng như `image/png` hoặc `application/json`.

Trong MockMvc, builder `multipart(...)` dựng một multipart request giả lập cho Spring MVC. Builder này tạo request theo cơ chế mock; bạn thêm từng part bằng `.file(...)` hoặc `.part(...)`.

```java
mockMvc.perform(multipart("/api/products/{id}/assets", 42)
        .file(imageFile)
        .part(metadataPart))
    .andExpect(status().isCreated());
```

Điểm cần nhớ:

- Dùng `.file(...)` khi muốn dựng một `MultipartFile` với filename, content type và bytes.
- Dùng `.part(...)` khi cần biểu diễn một part tổng quát và tự cấu hình header.
- Tên part phải khớp tên controller nhận bằng `@RequestPart` hoặc `@RequestParam`.
- Không đặt `image/png` làm Content-Type của toàn request; đó là Content-Type của part ảnh.
- Multipart builder tự dựng request tổng thể. Không tự viết boundary khi dùng builder.

## 3. Dựng file part bằng `MockMultipartFile`

`MockMultipartFile` là tiện ích của Spring Test để tạo một file part trong bộ kiểm thử.

```java
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

MockMultipartFile image = new MockMultipartFile(
        "image",                    // Tên part
        "cover.png",                // Filename client gửi
        MediaType.IMAGE_PNG_VALUE,  // Content-Type của part
        imageBytes                  // Nội dung file
);
```

Constructor thường dùng nhận bốn giá trị:

| Tham số | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `name` | `image` | Tên part trong multipart request |
| `originalFilename` | `cover.png` | Filename do client gửi |
| `contentType` | `image/png` | Content-Type của part |
| `content` | `byte[]` | Bytes của file |

Tên part và filename là hai giá trị khác nhau. `partWithName("image")` dùng `name`, còn `cover.png` là filename được truyền trong `Content-Disposition`.

### 3.1. Sử dụng fixture file trong test resources

Nếu endpoint kiểm tra file signature hoặc parse ảnh, không nên dùng vài byte tùy ý. Đặt một file PNG nhỏ, hợp lệ trong `src/test/resources/fixtures/cover.png`, sau đó đọc bytes:

```java
byte[] imageBytes;

try (InputStream input = getClass()
        .getResourceAsStream("/fixtures/cover.png")) {
    if (input == null) {
        throw new IllegalStateException("Missing PNG test fixture");
    }
    imageBytes = input.readAllBytes();
}

MockMultipartFile image = new MockMultipartFile(
        "image",
        "cover.png",
        MediaType.IMAGE_PNG_VALUE,
        imageBytes
);
```

Fixture phải phù hợp với validator của ứng dụng. Một file có phần mở rộng `.png` và header `image/png` vẫn có thể chứa bytes không phải ảnh PNG.

### 3.2. Tạo file part zero-byte

Để kiểm tra file rỗng:

```java
MockMultipartFile emptyImage = new MockMultipartFile(
        "image",
        "empty.png",
        MediaType.IMAGE_PNG_VALUE,
        new byte[0]
);
```

Part này vẫn có mặt trong request, nhưng không có nội dung. Nó khác với trường hợp client không gửi part `image` chút nào.

## 4. Dựng JSON part bằng `MockPart`

Khi metadata là JSON, `MockPart` cho phép thiết lập header Content-Type riêng:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockPart;

String json = """
        {
          "title": "Bìa sách",
          "description": "Ảnh bìa phiên bản mới",
          "displayOrder": 1
        }
        """;

MockPart metadata = new MockPart(
        "metadata",
        json.getBytes(StandardCharsets.UTF_8)
);
metadata.getHeaders().setContentType(MediaType.APPLICATION_JSON);
```

Tên `metadata` phải giống tên part mà controller nhận. Content-Type `application/json` giúp Spring MVC chọn `HttpMessageConverter` JSON để chuyển body thành DTO khi dùng `@RequestPart`.

Nếu không đặt Content-Type đúng, converter có thể không chọn được cách đọc body hoặc trả lỗi media type. Test nên gửi đúng Content-Type như client thực tế.

### 4.1. Khi nào dùng `MockMultipartFile`, khi nào dùng `MockPart`?

| Tình huống | Công cụ phù hợp |
| --- | --- |
| File upload có filename, content type và bytes | `MockMultipartFile` |
| JSON part cần header `application/json` | `MockPart` |
| Text part đơn giản | `MockPart` |
| Muốn kiểm tra filename file upload | `MockMultipartFile` |
| Muốn tùy chỉnh nhiều header của một part | `MockPart` |

Có thể dùng `MockMultipartFile` cho metadata JSON nếu muốn, bằng cách đặt content type `application/json`; `MockPart` giúp thể hiện ý định rõ ràng hơn khi part không phải file.

## 5. Controller mẫu để kiểm tra binding

Giả sử endpoint nhận file và metadata:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

record AssetMetadata(
        @NotBlank
        @Size(max = 120)
        String title,
        @Size(max = 1000)
        String description,
        Integer displayOrder
) {}
```

Controller minh họa:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
class ProductAssetController {

    @PostMapping(
        path = "/api/products/{productId}/assets",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    ResponseEntity<UploadResult> upload(
            @PathVariable Long productId,
            @RequestPart("image") MultipartFile image,
            @Valid @RequestPart("metadata") AssetMetadata metadata) {

        if (image.isEmpty()) {
            throw new IllegalArgumentException("Image must not be empty");
        }

        UploadResult result = new UploadResult(
                productId,
                image.getOriginalFilename(),
                metadata.title()
        );

        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }
}

record UploadResult(Long productId, String filename, String title) {}
```

Trong ứng dụng thật, nên dùng exception chuyên biệt và `@ControllerAdvice` để ánh xạ lỗi thành response contract ổn định. Ví dụ trên chỉ minh họa request binding và kết quả để test có thể xác nhận controller đã nhận đúng các giá trị.

`@RequestPart("image")` bind file thành `MultipartFile`; `@RequestPart("metadata")` dùng message converter để chuyển JSON thành `AssetMetadata`. `@Valid` kích hoạt Bean Validation nếu dự án có dependency validation phù hợp.

## 6. Bài test MockMvc đầu tiên

Test dưới đây xác nhận request multipart hợp lệ trả `201 Created`, đồng thời kiểm tra dữ liệu controller nhận được qua response.

```java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.mock.web.MockPart;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductAssetMultipartMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void acceptsImageAndJsonMetadata() throws Exception {
        MockMultipartFile image = new MockMultipartFile(
                "image",
                "cover.png",
                MediaType.IMAGE_PNG_VALUE,
                TestFixtures.validPng()
        );

        String metadataJson = """
                {
                  "title": "Bìa sách",
                  "description": "Ảnh bìa phiên bản mới",
                  "displayOrder": 1
                }
                """;

        MockPart metadata = new MockPart(
                "metadata",
                metadataJson.getBytes(StandardCharsets.UTF_8)
        );
        metadata.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        mockMvc.perform(multipart("/api/products/{productId}/assets", 42)
                    .file(image)
                    .part(metadata)
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.productId").value(42))
                .andExpect(jsonPath("$.filename").value("cover.png"))
                .andExpect(jsonPath("$.title").value("Bìa sách"));
    }
}
```

`TestFixtures.validPng()` là helper minh họa đọc fixture ảnh hợp lệ từ test resources. Thay helper bằng fixture của dự án. Các assertion `jsonPath` kiểm tra response được tạo từ dữ liệu controller đã nhận; nếu controller không trả lại các trường này, có thể dùng `ArgumentCaptor` để xác nhận service được gọi với filename, bytes hoặc metadata đúng.

### 6.1. Kiểm tra service nhận đúng dữ liệu

Trong test dùng mock service, có thể bắt đối số truyền vào bằng Mockito:

```java
ArgumentCaptor<AssetMetadata> metadataCaptor =
        ArgumentCaptor.forClass(AssetMetadata.class);

verify(assetService).upload(
        eq(42L),
        any(MultipartFile.class),
        metadataCaptor.capture()
);

assertEquals("Bìa sách", metadataCaptor.getValue().title());
```

Đối với file, có thể capture `MultipartFile` rồi kiểm tra `getOriginalFilename()`, `getContentType()`, `getSize()` và bytes. Cách này hữu ích nếu response của endpoint không phản chiếu lại dữ liệu đã bind.

## 7. Xác nhận các part bắt buộc và tùy chọn

MockMvc test có thể tạo các biến thể multipart khác nhau. Ví dụ `thumbnail` tùy chọn:

```java
@PostMapping(
    path = "/api/products/{productId}/assets",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> upload(
        @PathVariable Long productId,
        @RequestPart("image") MultipartFile image,
        @RequestPart("metadata") AssetMetadata metadata,
        @RequestPart(value = "thumbnail", required = false)
                MultipartFile thumbnail) {
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
```

Test không gửi thumbnail:

```java
mockMvc.perform(multipart("/api/products/{id}/assets", 42)
        .file(image)
        .part(metadata))
    .andExpect(status().isCreated());
```

Test có thumbnail:

```java
MockMultipartFile thumbnail = new MockMultipartFile(
        "thumbnail",
        "preview.jpg",
        MediaType.IMAGE_JPEG_VALUE,
        TestFixtures.validJpeg()
);

mockMvc.perform(multipart("/api/products/{id}/assets", 42)
        .file(image)
        .part(metadata)
        .file(thumbnail))
    .andExpect(status().isCreated());
```

Khi part optional vắng mặt, tham số controller có thể nhận `null` nếu khai báo `@RequestPart(required = false)`. Ở Spring REST Docs, descriptor tương ứng cũng cần `.optional()` để snippet được tạo từ request mẫu không có part này.

**Hai nơi phải nhất quán:** `required = false` điều khiển binding ở controller; `.optional()` điều khiển kiểm tra descriptor lúc sinh snippet. Cái này không tự thay đổi cái kia.

## 8. Kiểm tra part absent, empty và file zero-byte

Ba tình huống cần được kiểm thử riêng:

| Trường hợp | Cách dựng request | Ý nghĩa |
| --- | --- | --- |
| Absent | Không gọi `.file(...)` hoặc `.part(...)` cho tên đó | Client không gửi part |
| Empty text part | Gửi `MockPart` với `new byte[0]` | Part có mặt nhưng body rỗng |
| Zero-byte file | Gửi `MockMultipartFile` với `new byte[0]` | File part có mặt, kích thước 0 |

Ví dụ kiểm tra part `image` zero-byte:

```java
MockMultipartFile emptyImage = new MockMultipartFile(
        "image",
        "empty.png",
        MediaType.IMAGE_PNG_VALUE,
        new byte[0]
);

mockMvc.perform(multipart("/api/products/{id}/assets", 42)
        .file(emptyImage)
        .part(metadata))
    .andExpect(status().isBadRequest());
```

Kỳ vọng `400` chỉ đúng nếu endpoint đã triển khai quy tắc từ chối file rỗng và exception handler trả status đó. Không suy ra hành vi server từ descriptor REST Docs.

Đối với part required bị thiếu, controller với `@RequestPart("image")` mặc định yêu cầu part. Spring MVC thường trả `400 Bad Request` khi không có part này, nhưng kết quả cuối cùng còn phụ thuộc exception handling. Hãy viết assertion theo response contract thật của ứng dụng.

## 9. Kiểm tra Content-Type của từng part

Request tổng thể phải là `multipart/form-data`; mỗi part có media type riêng. Trong MockMvc:

```java
MockMultipartFile image = new MockMultipartFile(
        "image",
        "cover.png",
        MediaType.IMAGE_PNG_VALUE,
        TestFixtures.validPng()
);

MockPart metadata = new MockPart(
        "metadata",
        metadataJson.getBytes(StandardCharsets.UTF_8)
);
metadata.getHeaders().setContentType(MediaType.APPLICATION_JSON);
```

Test âm tính có thể gửi file với Content-Type không được hỗ trợ:

```java
MockMultipartFile wrongType = new MockMultipartFile(
        "image",
        "cover.txt",
        MediaType.TEXT_PLAIN_VALUE,
        "not an image".getBytes(StandardCharsets.UTF_8)
);
```

Nếu endpoint chỉ nhận PNG/JPEG, test nên xác nhận server từ chối theo contract, ví dụ status `415` hoặc `400` tùy cách ứng dụng ánh xạ lỗi.

Content-Type là giá trị client khai báo. Nếu gửi `image/png` nhưng bytes là văn bản, kiểm tra header thôi chưa đủ. Với upload file, cần kiểm tra nội dung thực tế bằng file signature detector hoặc parser thích hợp nếu yêu cầu sản phẩm đòi hỏi.

## 10. Kết hợp MockMvc với Spring REST Docs

MockMvc kiểm tra hành vi HTTP; Spring REST Docs dùng chính request được test để sinh snippet. Có thể gắn tài liệu hóa vào test thành công:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

mockMvc.perform(multipart("/api/products/{productId}/assets", 42)
        .file(image)
        .part(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isCreated())
    .andDo(document("products-upload-asset",
        requestParts(
            partWithName("image")
                .description("Ảnh sản phẩm; PNG hoặc JPEG"),
            partWithName("metadata")
                .description("Metadata JSON của ảnh")
        ),
        requestPartBody("metadata"),
        requestPartFields("metadata",
            fieldWithPath("title")
                .description("Tiêu đề ảnh"),
            fieldWithPath("description")
                .description("Mô tả ảnh")
                .optional(),
            fieldWithPath("displayOrder")
                .description("Thứ tự hiển thị ảnh")
                .optional()
        )
    ));
```

Ba API đảm nhiệm ba mức thông tin:

| API | Nội dung snippet |
| --- | --- |
| `requestParts(...)` | Tên và mô tả các part |
| `requestPartBody("metadata")` | Body JSON mẫu của part metadata |
| `requestPartFields("metadata", ...)` | Các field bên trong JSON part |

Các descriptor trong `requestPartFields(...)` dùng path tương đối trong JSON part; ví dụ `title`, không phải `metadata.title`.

Nếu có part tùy chọn, khai báo `.optional()` trong descriptor khi request mẫu không gửi part đó. Nếu có field kỹ thuật không muốn hiển thị, dùng `.ignored()` theo đúng contract. `relaxedRequestParts(...)` chỉ nên dùng khi operation chủ đích cho phép part chưa được mô tả.

## 11. Tách test hành vi và test tài liệu hóa

Một bài test có thể vừa xác nhận status/response vừa sinh snippet. Tuy nhiên, nên phân biệt mục tiêu:

- **Test hành vi:** xác minh endpoint chấp nhận/từ chối file, metadata, MIME type và kích thước.
- **Test tài liệu hóa:** dùng request đại diện để sinh `request-parts.adoc`, body và field snippets.
- **Negative test:** xác minh response khi thiếu part required, JSON sai hoặc file không hợp lệ.

Không nhất thiết sinh snippet cho mọi trường hợp lỗi. Tài liệu API thường cần một request thành công đại diện và có thể thêm snippet response lỗi nếu error contract là nội dung cần công bố.

Một test tài liệu hóa thành công không chứng minh endpoint đã xử lý đủ mọi trường hợp sai; một test validation thành công cũng không bảo đảm snippet mô tả đủ mọi part.

## 12. Giới hạn và lưu ý khi dùng MockMvc

MockMvc chạy request qua hạ tầng Spring MVC mock. Nó hữu ích để kiểm tra mapping, binding, validation, controller advice và tích hợp Spring REST Docs, nhưng không phải là một HTTP client gọi tới servlet container thật qua socket.

Vì vậy:

- MockMvc không xác minh reverse proxy, TLS termination hoặc cấu hình gateway.
- Cách parse multipart của mock request không thay thế kiểm thử giới hạn upload trên container thật.
- Không xác minh hành vi mạng khi stream file lớn hoặc client ngắt kết nối.
- Có thể cần integration test chạy ứng dụng với server thật để kiểm tra multipart parsing, max file size, max request size và cấu hình hạ tầng.

Dùng MockMvc cho feedback nhanh ở tầng MVC; bổ sung một số kiểm thử tích hợp qua server thật khi upload là chức năng quan trọng và các giới hạn container ảnh hưởng đến contract.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Controller không nhận được file | Tên part builder khác `@RequestPart` | Đồng bộ tên part |
| Metadata không deserialize thành DTO | Thiếu Content-Type `application/json` | Gắn header vào `MockPart` |
| Dùng `.file()` cho JSON mà quên filename/content type | Builder tạo file part không giống ý định | Dùng `MockPart` hoặc thiết lập đủ tham số `MockMultipartFile` |
| Test absent nhưng lại gửi file rỗng | Request builder vẫn gọi `.file(...)` | Không thêm part vào builder |
| File zero-byte vẫn qua | Chưa có validation `isEmpty()` hoặc kiểm tra nội dung | Thêm quy tắc và test |
| Part optional bị lỗi binding | Controller vẫn `required = true` | Dùng `@RequestPart(required = false)` nếu contract cho phép |
| REST Docs báo thiếu part | Descriptor required nhưng fixture không gửi part | Thêm part hoặc `.optional()` |
| REST Docs báo part chưa được mô tả | Có part mới nhưng strict descriptor chưa cập nhật | Thêm descriptor, ignore hoặc relaxed theo contract |
| Content-Type sai vẫn qua | Chưa kiểm tra media type ở endpoint | Thêm validation và negative test |
| Test chạy nhưng file lớn ngoài thực tế bị lỗi | MockMvc không thay thế container/network test | Thêm integration test với server thật |
| Snippet thiếu metadata fields | Chỉ gọi `requestParts(...)` | Thêm `requestPartFields(...)` |
| Asciidoctor báo include không tồn tại | Test chưa sinh snippet hoặc tên operation sai | Kiểm tra operation ID và task dependency |

## 14. Asciidoctor và build/CI

Nguồn tài liệu có thể include các snippet mà test sinh:

```adoc
= Product Asset API
:toc: left

== Upload ảnh sản phẩm

=== HTTP request
include::{snippets}/products-upload-asset/http-request.adoc[]

=== Các part
include::{snippets}/products-upload-asset/request-parts.adoc[]

=== Metadata JSON
include::{snippets}/products-upload-asset/request-part-metadata-body.adoc[]

=== Metadata fields
include::{snippets}/products-upload-asset/request-part-metadata-fields.adoc[]
```

Với Gradle và plugin Asciidoctor đã được cấu hình, task tài liệu cần phụ thuộc test sinh snippet:

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
MockMvc multipart tests
        |
        +--> Test binding và response
        |
        +--> Test validation / negative cases
        |
        +--> Spring REST Docs tạo snippets
        |
        v
Asciidoctor / bước chuyển Markdown
        |
        v
Kiểm tra và xuất bản tài liệu
```

Khi đổi tên part, Content-Type hoặc DTO metadata, cập nhật controller, fixture, descriptor và tài liệu cùng lúc. Không chỉnh snippet generated bằng tay để làm build xanh. Spring REST Docs thường tạo AsciiDoc; Markdown cần template hoặc bước chuyển đổi được dự án cấu hình riêng.

## 15. Bài thực hành

Với endpoint `POST /api/products/{productId}/assets`:

1. Dựng file part `image` bằng `MockMultipartFile` và JSON part `metadata` bằng `MockPart`.
2. Gắn `image/png` cho file và `application/json` cho metadata. Xác nhận controller bind thành công.
3. Assert status và response có tên file, tiêu đề metadata.
4. Gửi metadata thiếu `title`; xác nhận Bean Validation từ chối request theo error contract.
5. Bỏ hẳn part `image`; xác nhận server xử lý part required bị thiếu.
6. Gửi file zero-byte; so sánh với request không có part.
7. Gửi MIME `text/plain` và bytes không phải ảnh; xác nhận validation.
8. Thêm `requestParts`, `requestPartBody` và `requestPartFields` để sinh snippet.
9. Dùng một test không gửi part optional và thêm `.optional()` cho descriptor.
10. Chạy test sinh snippet trước Asciidoctor trong CI; kiểm tra mọi include đều tồn tại.

### Câu hỏi tự đánh giá

- Khi nào dùng `MockMultipartFile`, khi nào dùng `MockPart`?
- Tên part khác filename như thế nào?
- Vì sao JSON part cần `Content-Type: application/json`?
- `multipart(...)` tạo request loại nào trong MockMvc?
- Absent part khác file zero-byte ra sao?
- `.optional()` trong REST Docs có làm controller chấp nhận part thiếu không?
- `requestParts`, `requestPartBody` và `requestPartFields` mô tả các cấp nào?
- MockMvc không kiểm chứng được những khía cạnh nào của upload qua servlet container thật?

**Ghi nhớ:** Dùng `multipart(...)` để dựng request, `MockMultipartFile` để mô phỏng file và `MockPart` để tạo part tổng quát như JSON. Kiểm tra binding, response và validation bằng MockMvc; sau đó dùng cùng request thành công để sinh `requestParts`, `requestPartBody` và `requestPartFields`. Tách biệt part absent với part rỗng, và bổ sung kiểm thử server thật khi cần xác minh giới hạn container hoặc truyền file qua mạng.

## Tài liệu tham khảo

- [Spring Framework — MockMvc multipart requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html): dựng request HTTP bằng MockMvc và multipart builder.
- [Spring Framework — `MockMultipartFile` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/mock/web/MockMultipartFile.html): tạo file part trong test.
- [Spring Framework — `MockPart` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/mock/web/MockPart.html): tạo multipart part tổng quát và gắn headers.
- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): `requestParts` và tài liệu hóa multipart.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): body và field của JSON part.
