# File upload và metadata đi kèm trong Spring REST Docs

## 1. Bài toán upload file kèm metadata

Một API upload thường cần nhận đồng thời file nhị phân và dữ liệu mô tả file. Ví dụ, chức năng tải ảnh sản phẩm cần nhận:

- `file`: bytes của ảnh.
- `metadata`: JSON chứa tiêu đề, mô tả, thứ tự hiển thị hoặc thông tin nghiệp vụ khác.

Nếu tách thành hai HTTP request, client phải quản lý trạng thái upload và metadata qua nhiều bước. Với `multipart/form-data`, client gửi cả hai part trong cùng một request. Mỗi part có tên và Content-Type riêng, giúp server chuyển đổi đúng loại dữ liệu.

Ví dụ operation `POST /api/products/{productId}/assets` nhận:

```http
POST /api/products/42/assets HTTP/1.1
Accept: application/json
Content-Type: multipart/form-data; boundary=----AssetBoundary

------AssetBoundary
Content-Disposition: form-data; name="file"; filename="cover.png"
Content-Type: image/png

<bytes của ảnh PNG>
------AssetBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json; charset=UTF-8

{
  "title": "Bìa sách",
  "description": "Ảnh bìa phiên bản mới",
  "displayOrder": 1
}
------AssetBoundary--
```

Trong SPRING_REST_DOCS, ta dùng các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured để tạo request thật, sau đó dùng Spring REST Docs sinh snippet. Với upload file kèm metadata, các API thường phối hợp là:

- `requestParts(...)` và `partWithName(...)` để mô tả các part.
- `requestPartFields("metadata", ...)` để mô tả các field JSON bên trong part metadata.
- `requestPartBody("metadata")` nếu cần hiển thị body JSON nguyên bản.
- `requestHeaders(...)` nếu cần tài liệu hóa header cấp HTTP như `Authorization` và `Accept`.

Bài này trình bày toàn bộ luồng từ contract, controller, test upload cho tới snippet Asciidoctor và build/CI. Sau khi học, bạn có thể thiết kế operation nhận file + JSON, kiểm tra đúng Content-Type, mô tả cả cấp part lẫn field bên trong part, và phát hiện thay đổi contract bằng test.

## 2. Thiết kế contract multipart

Trước khi viết controller hoặc descriptor, hãy xác định tên và trách nhiệm của từng part.

| Part | Kiểu nội dung | Bắt buộc | Nội dung |
| --- | --- | --- | --- |
| `file` | `image/png` hoặc `image/jpeg` | Có | Ảnh sản phẩm |
| `metadata` | `application/json` | Có | Tiêu đề, mô tả và thứ tự hiển thị |
| `thumbnail` | `image/jpeg` | Không | Ảnh xem trước nếu client cung cấp |

Tên part là một phần của API contract. Nếu controller nhận `@RequestPart("metadata")`, client phải gửi part có `name="metadata"`. `filename="cover.png"` là tên file client gửi; nó không phải tên part.

**Content-Type có hai cấp:**

- Request tổng thể: `multipart/form-data; boundary=...`.
- Từng part: `image/png`, `image/jpeg` hoặc `application/json`.

Không đặt `application/json` làm Content-Type cho toàn request nếu body là multipart gồm file và JSON. Phần JSON phải được gắn `application/json` ở chính part metadata.

Một contract rõ ràng cũng cần quy định cách xử lý file rỗng, MIME type không hỗ trợ, metadata thiếu field, tên file, giới hạn kích thước và part optional. `requestParts(...)` có thể kiểm tra part có được gửi trong request mẫu hay không, nhưng không thay thế các quy tắc validation trên.

## 3. Controller nhận file và JSON bằng `@RequestPart`

Spring MVC dùng `@RequestPart` để lấy từng part theo tên. Với part JSON, Spring chọn `HttpMessageConverter` dựa trên Content-Type của part để chuyển body thành DTO.

Ví dụ DTO:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record AssetMetadata(
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
import jakarta.validation.Valid;
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

    private final ProductAssetService assetService;

    ProductAssetController(ProductAssetService assetService) {
        this.assetService = assetService;
    }

    @PostMapping(
        path = "/api/products/{productId}/assets",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    ResponseEntity<Void> upload(
            @PathVariable Long productId,
            @RequestPart("file") MultipartFile file,
            @Valid @RequestPart("metadata") AssetMetadata metadata) {

        assetService.upload(productId, file, metadata);
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Trong operation trên:

- `file` được bind thành `MultipartFile`.
- `metadata` được chuyển từ part JSON thành `AssetMetadata`.
- `@Valid` kích hoạt Bean Validation cho DTO nếu dependency validation đã được cấu hình.
- `consumes = MULTIPART_FORM_DATA_VALUE` giới hạn loại request tổng thể.

`@RequestPart("metadata")` mặc định là required. Nếu muốn metadata có thể vắng, contract và tham số controller cần được thiết kế tương ứng, chẳng hạn `required = false`; việc đánh dấu descriptor optional trong REST Docs không tự thay đổi hành vi controller.

### 3.1. Kiểm tra file trong service

Không nên tin tuyệt đối filename hoặc Content-Type do client gửi. Có thể kiểm tra trước các điều kiện cơ bản:

```java
void validateImage(MultipartFile file) {
    if (file == null || file.isEmpty()) {
        throw new InvalidUploadException("File ảnh không được rỗng");
    }

    String declaredType = file.getContentType();
    if (!MediaType.IMAGE_PNG_VALUE.equals(declaredType)
            && !MediaType.IMAGE_JPEG_VALUE.equals(declaredType)) {
        throw new UnsupportedUploadMediaTypeException(
                "Chỉ hỗ trợ PNG và JPEG"
        );
    }

    // Nếu yêu cầu xác minh định dạng thực tế, cần kiểm tra bytes
    // bằng file-signature detector hoặc parser phù hợp.
}
```

Đây chỉ là kiểm tra cơ bản. MIME type là thông tin client khai báo; một file giả có thể gửi `Content-Type: image/png`. Hệ thống cần xác minh nội dung thực tế, kiểm soát kích thước, tên file, lưu trữ và quyền truy cập theo yêu cầu bảo mật của sản phẩm.

## 4. Tài liệu hóa cấp part bằng `requestParts(...)`

`requestParts(...)` mô tả danh sách part mà operation nhận. Mỗi `partWithName(...)` tạo descriptor cho một part:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("file")
        .description("Ảnh sản phẩm cần tải lên; PNG hoặc JPEG"),
    partWithName("metadata")
        .description("Metadata JSON mô tả ảnh sản phẩm")
);
```

Snippet `request-parts.adoc` mô tả tên part và ý nghĩa của nó. Descriptor part mặc định là required trong request mẫu. Nếu một part có thể vắng, có thể thêm `.optional()`; nếu được nhận diện nhưng không cần hiển thị, dùng `.ignored()`.

Ví dụ có thumbnail tùy chọn:

```java
requestParts(
    partWithName("file")
        .description("Ảnh sản phẩm; PNG hoặc JPEG"),
    partWithName("metadata")
        .description("Metadata JSON của ảnh"),
    partWithName("thumbnail")
        .description("Ảnh xem trước nếu client cung cấp")
        .optional()
);
```

`optional()` chỉ ảnh hưởng kiểm tra hiện diện của descriptor lúc tạo snippet. Nó không làm controller chấp nhận part thiếu và cũng không có nghĩa file zero-byte được coi là hợp lệ.

### 4.1. Strict và relaxed request parts

Với `requestParts(...)`, một part có trong request nhưng chưa có descriptor có thể làm snippet thất bại. Đây là chế độ phù hợp để phát hiện part mới cần được review. `relaxedRequestParts(...)` cho phép part bổ sung chưa khai báo, thích hợp khi contract chủ đích có phần mở rộng. Các descriptor đã khai báo vẫn tuân theo quy tắc required/optional.

Không chuyển sang relaxed chỉ để tránh lỗi khi API thêm một part mới; hãy quyết định xem part đó có phải một phần của contract công khai hay không.

## 5. Mô tả JSON bên trong metadata bằng `requestPartFields(...)`

`requestParts(...)` chỉ mô tả part `metadata` ở cấp multipart. Nó không tự sinh bảng cho `title`, `description` hoặc `displayOrder`. Khi client cần hiểu schema JSON, dùng `requestPartFields(...)`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

requestPartFields("metadata",
    fieldWithPath("title")
        .description("Tiêu đề ảnh"),
    fieldWithPath("description")
        .description("Mô tả ảnh")
        .optional(),
    fieldWithPath("displayOrder")
        .description("Thứ tự hiển thị ảnh")
        .optional()
);
```

Các descriptor ở đây trỏ đến field **bên trong JSON part `metadata`**, vì vậy path là `title`, `description`, `displayOrder`; không thêm tiền tố `metadata.`.

Snippet được sinh có tên tương ứng với part, ví dụ:

```text
request-part-metadata-fields.adoc
```

Nếu muốn hiển thị nguyên body JSON mẫu, bổ sung `requestPartBody("metadata")`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

requestPartBody("metadata");
```

Ba API có phạm vi khác nhau:

| API | Câu hỏi mà snippet trả lời |
| --- | --- |
| `requestParts(...)` | Operation nhận những part nào? |
| `requestPartFields("metadata", ...)` | JSON metadata có những field nào? |
| `requestPartBody("metadata")` | Một payload metadata mẫu trông như thế nào? |

Có thể dùng đồng thời cả ba nếu người đọc cần tên part, schema và ví dụ body.

## 6. MockMvc: tạo file part và JSON metadata

MockMvc hỗ trợ `MockMultipartFile` cho file upload và `MockPart` cho part tổng quát. Dùng `MockPart` cho metadata giúp gắn header `Content-Type: application/json` rõ ràng.

### 6.1. Tạo multipart parts

```java
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.mock.web.MockPart;

MockMultipartFile filePart = new MockMultipartFile(
        "file",
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

MockPart metadataPart = new MockPart(
        "metadata",
        metadataJson.getBytes(StandardCharsets.UTF_8)
);
metadataPart.getHeaders().setContentType(MediaType.APPLICATION_JSON);
```

Tên `"file"` và `"metadata"` là tên part. `cover.png` là filename client gửi. Đặt content type của metadata part thành `application/json` để Spring MVC chọn converter JSON khi bind `@RequestPart("metadata") AssetMetadata`.

### 6.2. Bài test hoàn chỉnh sinh snippet

```java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.mock.web.MockPart;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
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
class ProductAssetUploadDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentFileAndMetadataUpload() throws Exception {
        MockMultipartFile filePart = new MockMultipartFile(
                "file",
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

        MockPart metadataPart = new MockPart(
                "metadata",
                metadataJson.getBytes(StandardCharsets.UTF_8)
        );
        metadataPart.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        mockMvc.perform(multipart("/api/products/{productId}/assets", 42)
                    .file(filePart)
                    .part(metadataPart)
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andDo(document("products-upload-asset",
                        requestHeaders(
                                headerWithName("Accept")
                                        .description("Định dạng response client chấp nhận")
                        ),
                        requestParts(
                                partWithName("file")
                                        .description("Ảnh sản phẩm; PNG hoặc JPEG"),
                                partWithName("metadata")
                                        .description("Metadata JSON mô tả ảnh")
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
    }
}
```

`TestFixtures.validPng()` đại diện cho helper đọc bytes ảnh hợp lệ từ `src/test/resources`. Dùng fixture thật nếu ứng dụng kiểm tra chữ ký file hoặc parse ảnh; một dãy byte giả có thể bị endpoint từ chối dù header khai báo `image/png`.

`multipart(...)` tự dựng request tổng thể với `multipart/form-data` và boundary. Test chỉ cần thiết lập header cấp ngoài thực sự cần thiết, ví dụ `Accept` hoặc `Authorization`; không gán `image/png` cho request tổng thể.

Nếu dùng Spring Security, có thể thêm request post-processor để tạo user hoặc cấu hình token test phù hợp. Không đưa token thật vào snippet được xuất bản.

## 7. Kết quả snippet và cách include tài liệu

Sau khi test thành công, thư mục output có thể chứa:

```text
build/generated-snippets/
└── products-upload-asset/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-headers.adoc
    ├── request-parts.adoc
    ├── request-part-metadata-body.adoc
    └── request-part-metadata-fields.adoc
```

Tên và snippet thực tế phụ thuộc operation được cấu hình. Chỉ include những file mà test có yêu cầu sinh.

Ví dụ `src/docs/asciidoc/products.adoc`:

```adoc
= Product Asset API
:toc: left

== Upload ảnh sản phẩm

=== HTTP request
include::{snippets}/products-upload-asset/http-request.adoc[]

=== Các part của request
include::{snippets}/products-upload-asset/request-parts.adoc[]

=== Metadata JSON
include::{snippets}/products-upload-asset/request-part-metadata-body.adoc[]

=== Các field metadata
include::{snippets}/products-upload-asset/request-part-metadata-fields.adoc[]

=== HTTP request headers
include::{snippets}/products-upload-asset/request-headers.adoc[]
```

Bảng `request-parts.adoc` giải thích file và metadata. Bảng `request-part-metadata-fields.adoc` giải thích schema JSON. Body snippet minh họa một giá trị cụ thể. Kết hợp ba mức này giúp người đọc biết chính xác cách dựng multipart request.

## 8. Validation và các test âm tính

Tài liệu hóa request thành công chưa đủ để đảm bảo endpoint xử lý file an toàn và đúng contract. Nên có test riêng cho các tình huống lỗi:

| Trường hợp | Kết quả mong đợi theo contract ví dụ |
| --- | --- |
| Thiếu `file` | HTTP 400 |
| Thiếu `metadata` | HTTP 400 |
| Metadata không có `title` | HTTP 400 |
| Metadata có JSON sai cú pháp | HTTP 400 |
| `metadata` có Content-Type không phù hợp | Lỗi media type/converter theo cấu hình |
| File zero-byte | HTTP 400 |
| MIME khai báo không hỗ trợ | HTTP 415 hoặc lỗi được API quy định |
| MIME là PNG nhưng bytes không phải PNG | Bị từ chối nếu hệ thống kiểm tra nội dung |
| File vượt giới hạn | HTTP 413 hoặc response lỗi theo cấu hình |

Các mã status trên là ví dụ contract; cần xác nhận theo exception handler và cấu hình thực tế của ứng dụng. Dùng negative tests để chứng minh hành vi endpoint, không suy ra từ việc Spring REST Docs tạo được snippet.

### 8.1. Test metadata thiếu field bắt buộc

```java
@Test
void rejectMetadataWithoutTitle() throws Exception {
    MockMultipartFile filePart = new MockMultipartFile(
            "file",
            "cover.png",
            MediaType.IMAGE_PNG_VALUE,
            TestFixtures.validPng()
    );

    MockPart metadataPart = new MockPart(
            "metadata",
            """
            {"description":"Không có tiêu đề"}
            """.getBytes(StandardCharsets.UTF_8)
    );
    metadataPart.getHeaders().setContentType(MediaType.APPLICATION_JSON);

    mockMvc.perform(multipart("/api/products/{productId}/assets", 42)
                .file(filePart)
                .part(metadataPart))
            .andExpect(status().isBadRequest());
}
```

Test này chỉ đạt nếu controller kích hoạt Bean Validation và ứng dụng ánh xạ lỗi validation thành `400 Bad Request`. Nếu dự án dùng response lỗi có cấu trúc, có thể kiểm tra thêm error code hoặc body.

### 8.2. Giới hạn dung lượng upload

Spring Boot cho phép cấu hình giới hạn multipart qua các property phù hợp với servlet stack, ví dụ:

```properties
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
```

Giới hạn request tổng thể cần lớn hơn hoặc bằng tổng dung lượng các part cộng phần overhead multipart. Giá trị cụ thể phải dựa trên nhu cầu sản phẩm, giới hạn reverse proxy và hạ tầng lưu trữ. Test phải xác nhận server từ chối file vượt giới hạn, thay vì chỉ dựa vào cấu hình.

### 8.3. An toàn khi lưu file

Không nên dùng trực tiếp `originalFilename` làm đường dẫn lưu trữ. Tạo tên file phía server, kiểm tra content type và chữ ký file, giới hạn kích thước, lưu ngoài thư mục thực thi công khai nếu phù hợp, và áp dụng kiểm soát quyền truy cập khi tải xuống. Không đưa file chứa dữ liệu thật hoặc bí mật vào test fixture được công bố.

## 9. WebTestClient và REST Assured

### 9.1. WebTestClient với JSON part

Có thể tạo part JSON bằng `HttpEntity` có header riêng:

```java
HttpHeaders metadataHeaders = new HttpHeaders();
metadataHeaders.setContentType(MediaType.APPLICATION_JSON);

HttpEntity<String> metadataEntity =
        new HttpEntity<>(metadataJson, metadataHeaders);

HttpHeaders fileHeaders = new HttpHeaders();
fileHeaders.setContentType(MediaType.IMAGE_PNG);

HttpEntity<Resource> fileEntity =
        new HttpEntity<>(imageResource, fileHeaders);

MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
parts.add("file", fileEntity);
parts.add("metadata", metadataEntity);

webTestClient.post()
        .uri("/api/products/42/assets")
        .contentType(MediaType.MULTIPART_FORM_DATA)
        .body(BodyInserters.fromMultipartData(parts))
        .exchange()
        .expectStatus().isCreated()
        .expectBody()
        .consumeWith(document("products-upload-asset",
                requestParts(
                        partWithName("file").description("Ảnh sản phẩm"),
                        partWithName("metadata").description("Metadata JSON")
                )
        ));
```

Đây là ví dụ định hướng; resource/file name và converter phụ thuộc loại payload. Với JSON part, `HttpEntity` giúp gắn `Content-Type: application/json` riêng cho metadata.

### 9.2. REST Assured

REST Assured cung cấp cách dựng multipart part với content type cụ thể:

```java
given(this.spec)
        .filter(document("products-upload-asset",
                requestParts(
                        partWithName("file").description("Ảnh sản phẩm"),
                        partWithName("metadata").description("Metadata JSON")
                )))
        .multiPart("file", imageFile, "image/png")
        .multiPart("metadata", metadataJson, "application/json")
        .when()
        .post("/api/products/42/assets")
        .then()
        .statusCode(201);
```

Overload `multiPart(...)` cụ thể cần khớp phiên bản REST Assured dự án đang dùng. Sau khi dựng request, tên part và Content-Type thực tế phải khớp với contract và descriptor.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Controller không bind được metadata DTO | JSON part thiếu `application/json` hoặc JSON sai cú pháp | Gắn Content-Type đúng và kiểm tra converter |
| `requestParts(...)` báo thiếu part | Descriptor required nhưng test không gửi | Bổ sung part hoặc `.optional()` đúng contract |
| Part mới làm snippet thất bại | Strict mode gặp part chưa mô tả | Bổ sung descriptor, ignore có chủ đích hoặc relaxed theo contract |
| Metadata fields không được sinh | Chỉ gọi `requestParts(...)` | Thêm `requestPartFields("metadata", ...)` |
| JSON body snippet không có | Chưa gọi `requestPartBody("metadata")` | Thêm body snippet nếu cần |
| File bị từ chối dù MIME đúng | Bytes không đúng định dạng hoặc fixture không hợp lệ | Dùng file fixture thật và xác minh nội dung |
| Dùng `image/png` cho toàn request | Nhầm media type part với outer request | Dùng `multipart/form-data` cấp request |
| Snippet chỉ mô tả part, không nói rõ schema JSON | Chỉ dùng `requestParts(...)` | Thêm requestPartFields hoặc liên kết schema |
| Filename bị xem là tên part | Nhầm `filename` với `name` | `partWithName` dùng tên part |
| Asciidoctor báo thiếu include | Include snippet chưa được test tạo | Kiểm tra operation ID và task test |

## 11. Build và CI

Với Gradle và plugin Asciidoctor đã được cấu hình, task tài liệu cần phụ thuộc test tạo snippet:

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
Kiểm tra file part + JSON metadata
        |
        +--> Validation / negative tests
        |
        v
Spring REST Docs: requestParts + requestPartFields
        |
        v
Generated snippets
        |
        v
Asciidoctor / bước xuất Markdown
        |
        v
Kiểm tra và xuất bản
```

Khi thay đổi metadata DTO, tên part hoặc danh sách Content-Type, test và snippet phải được tạo lại. Không sửa generated snippet thủ công để che sai lệch. CI nên chạy cả test upload thành công, test validation và bước kết xuất tài liệu.

Spring REST Docs thường tạo snippet AsciiDoc. Nếu dự án phát hành Markdown, cần template hoặc bước chuyển đổi riêng; không mặc định có file `request-parts.md`.

## 12. Bài thực hành

Với endpoint `POST /api/products/{productId}/assets`:

1. Tạo request có file PNG và metadata JSON. Đảm bảo Content-Type cấp request là multipart và mỗi part có media type riêng.
2. Thêm field `altText` vào metadata DTO. Bổ sung `requestPartFields(...)` và kiểm tra snippet.
3. Bỏ `description` khỏi metadata. Đánh dấu descriptor optional và kiểm tra test tài liệu hóa.
4. Gửi metadata với `Content-Type: text/plain`; xác nhận endpoint xử lý theo contract.
5. Gửi file MIME `image/png` nhưng bytes không phải PNG. Thêm kiểm tra nội dung file và test âm tính.
6. Bỏ part `metadata`, sau đó bỏ part `file`; xác nhận status lỗi theo contract và phân biệt với lỗi snippet.
7. Thêm giới hạn dung lượng và test file vượt giới hạn.
8. Include request-parts, metadata body và metadata-fields vào Asciidoctor; đảm bảo CI chạy test trước khi kết xuất.

### Câu hỏi tự đánh giá

- Vì sao file và metadata JSON nên là hai part riêng?
- `@RequestPart("metadata")` cần Content-Type nào để Spring chuyển JSON thành DTO?
- `requestParts(...)` và `requestPartFields(...)` mô tả hai cấp nào?
- Vì sao descriptor field trong JSON part không cần tiền tố `metadata.`?
- Content-Type do client khai báo có chứng minh bytes đúng định dạng không?
- `.optional()` trong descriptor có làm controller chấp nhận part thiếu không?
- Vì sao cần cả positive tests và negative tests cho upload?
- Khi metadata DTO thay đổi, cần tái tạo những snippet nào?

**Ghi nhớ:** Một multipart upload hoàn chỉnh cần mô tả cả part file và part metadata. `requestParts(...)` cho biết operation nhận gì; `requestPartFields("metadata", ...)` giải thích schema JSON; `requestPartBody("metadata")` cho thấy ví dụ JSON cụ thể. Kết hợp các snippet với `@RequestPart`, Content-Type đúng, validation và test HTTP giúp tài liệu phản ánh đúng luồng upload file + metadata của API.

## Tài liệu tham khảo

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): `requestParts`, part body và part fields.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `requestPartFields` và mô tả JSON payload.
- [Spring Framework — `@RequestPart` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestPart.html): bind part và chuyển đổi qua HttpMessageConverter.
- [Spring Framework — `MultipartFile` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html): filename, content type, size và bytes của file upload.
