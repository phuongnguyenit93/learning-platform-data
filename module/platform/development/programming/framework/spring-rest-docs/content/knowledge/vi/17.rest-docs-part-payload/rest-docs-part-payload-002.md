# RequestPartFields cho các trường trong part JSON

## 1. Khi multipart có một part chứa JSON

Một endpoint upload thường nhận nhiều phần dữ liệu trong cùng HTTP request. Ví dụ, client gửi một file ảnh và một part JSON chứa metadata của ảnh. Đây là request dạng **multipart/form-data**:

- part `image` chứa file nhị phân;
- part `metadata` chứa JSON mô tả tiêu đề, mô tả, nhóm ảnh và thông tin bản quyền.

Với **Spring REST Docs**, `requestPartFields(partName, descriptors...)` dùng để document các field bên trong payload của một request part. API này thuộc `PayloadDocumentation` và hoạt động tương tự `requestFields(...)`, nhưng phạm vi chỉ là payload của part được chỉ định.

Bài học này tập trung vào `requestPartFields` và phân biệt ba mức tài liệu multipart:

| Mục tiêu | API | Nội dung được sinh |
| --- | --- | --- |
| Mô tả những part nào được gửi trong multipart request | `requestParts(...)` với `partWithName(...)` | Bảng tên part và mô tả |
| Hiển thị body của một part | `requestPartBody("metadata")` | Snippet chứa body của part metadata |
| Mô tả từng field trong JSON part | `requestPartFields("metadata", ...)` | Bảng field của JSON part metadata |

Sau bài học, bạn có thể:

- tạo multipart request chứa file và JSON bằng MockMvc;
- dùng `requestPartFields` để mô tả field ở bên trong JSON part;
- hiểu quy tắc kiểm tra strict, field optional, ignored và relaxed;
- sinh snippet body và field riêng cho part;
- tổ chức tài liệu Asciidoctor và đưa việc sinh snippet vào build/CI;
- nhận diện lỗi do sai tên part, sai content type, JSON không hợp lệ hoặc path field không khớp.

## 2. Ví dụ hợp đồng API

Giả sử endpoint `POST /images` nhận hai part:

```text
POST /images
Content-Type: multipart/form-data

Part: image
  Content-Type: image/png
  Filename: cover.png
  Body: bytes của file ảnh

Part: metadata
  Content-Type: application/json
  Body:
```

```json
{
  "title": "Ảnh bìa sản phẩm",
  "description": "Ảnh giới thiệu sản phẩm trong cửa hàng",
  "category": "PRODUCT",
  "copyright": {
    "owner": "Example Store",
    "license": "INTERNAL"
  }
}
```

Mỗi part là một phần riêng của multipart request. Part `image` được xử lý như file; part `metadata` có media type JSON và chứa một object có cấu trúc.

Bảng field của metadata sẽ gồm:

| Path | Ý nghĩa |
| --- | --- |
| `title` | Tiêu đề ảnh |
| `description` | Mô tả ảnh |
| `category` | Nhóm ảnh |
| `copyright.owner` | Chủ sở hữu quyền sử dụng |
| `copyright.license` | Loại giấy phép |

Điểm quan trọng là các path này được tính từ **gốc JSON của part metadata**. Không viết `metadata.title` hoặc `metadata.copyright.owner` trong `requestPartFields("metadata", ...)`, vì tên part đã được chỉ định riêng trong đối số đầu tiên.

## 3. Phân biệt requestParts, requestPartBody và requestPartFields

Ba API giải quyết các nhu cầu bổ sung nhau.

### 3.1. Mô tả sự hiện diện và mục đích của từng part

`requestParts(...)` thuộc `RequestDocumentation`. Nó mô tả những part mà endpoint hỗ trợ:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("image")
        .description("File ảnh cần tải lên"),
    partWithName("metadata")
        .description("Metadata JSON của ảnh")
)
```

Snippet được sinh có tên `request-parts.adoc`. Nó trả lời câu hỏi "request có những part nào?", không liệt kê field trong JSON metadata.

### 3.2. Lấy body của một part

`requestPartBody("metadata")` sinh snippet chứa body của part được chọn:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

requestPartBody("metadata")
```

Với part metadata, snippet được sinh có tên `request-part-metadata-body.adoc`. Nó hữu ích khi tài liệu cần hiển thị nguyên JSON mẫu.

### 3.3. Mô tả field trong JSON part

`requestPartFields("metadata", ...)` sinh bảng field:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

requestPartFields(
    "metadata",
    fieldWithPath("title").description("Tiêu đề ảnh"),
    fieldWithPath("description").description("Mô tả ảnh"),
    fieldWithPath("category").description("Nhóm ảnh")
)
```

Snippet được sinh có tên `request-part-metadata-fields.adoc`. Khi dùng `requestPartFields`, Spring REST Docs kiểm tra payload của part metadata theo các descriptor. Nó không document file bytes của part image.

## 4. Ví dụ hoàn chỉnh với MockMvc

Ví dụ dưới đây dùng JUnit 5, Java 17+, Spring MVC Test, MockMvc và Spring REST Docs. Controller nhận file và metadata JSON; phần xử lý lưu file được giản lược để tập trung vào cách document multipart.

```java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
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
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ImageUploadDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new ImageUploadController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void uploadImageWithJsonMetadata() throws Exception {
        MockMultipartFile image = new MockMultipartFile(
                "image",
                "cover.png",
                MediaType.IMAGE_PNG_VALUE,
                "fake-png-content".getBytes()
        );

        String metadataJson = """
                {
                  "title": "Ảnh bìa sản phẩm",
                  "description": "Ảnh giới thiệu sản phẩm trong cửa hàng",
                  "category": "PRODUCT",
                  "copyright": {
                    "owner": "Example Store",
                    "license": "INTERNAL"
                  }
                }
                """;

        MockMultipartFile metadata = new MockMultipartFile(
                "metadata",
                "",
                MediaType.APPLICATION_JSON_VALUE,
                metadataJson.getBytes()
        );

        this.mockMvc.perform(multipart("/images")
                        .file(image)
                        .file(metadata)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andDo(document("images-upload",
                        requestParts(
                                partWithName("image")
                                        .description("File ảnh PNG cần tải lên"),
                                partWithName("metadata")
                                        .description("Metadata JSON mô tả ảnh")
                        ),
                        requestPartBody("metadata"),
                        requestPartFields("metadata",
                                fieldWithPath("title")
                                        .description("Tiêu đề ảnh"),
                                fieldWithPath("description")
                                        .description("Mô tả ảnh"),
                                fieldWithPath("category")
                                        .description("Nhóm ảnh"),
                                fieldWithPath("copyright.owner")
                                        .description("Chủ sở hữu quyền sử dụng"),
                                fieldWithPath("copyright.license")
                                        .description("Loại giấy phép")
                        )
                ));
    }

    @RestController
    static class ImageUploadController {

        @PostMapping(
                value = "/images",
                consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        ResponseEntity<Map<String, String>> upload(
                @RequestPart("image") MultipartFile image,
                @RequestPart("metadata") Map<String, Object> metadata) {

            if (image.isEmpty()) {
                return ResponseEntity.badRequest().build();
            }

            return ResponseEntity.status(201)
                    .body(Map.of("id", "img-100"));
        }
    }
}
```

### 4.1. Vì sao metadata cần content type application/json?

Khi tạo `MockMultipartFile` cho part metadata, đặt:

```java
new MockMultipartFile(
    "metadata",
    "",
    MediaType.APPLICATION_JSON_VALUE,
    metadataJson.getBytes()
)
```

Tên part là `metadata` và media type là `application/json`. Điều này cho Spring MVC biết part có nội dung JSON để chuyển đổi sang kiểu tham số được khai báo trong `@RequestPart("metadata")`.

Nếu part được gửi dưới dạng `text/plain` hoặc không có media type phù hợp, việc chuyển đổi sang `Map` hoặc DTO có thể thất bại trước khi REST Docs document. Đó là lỗi binding/HTTP handling, không phải lỗi của `requestPartFields`.

### 4.2. Tại sao dùng RestDocumentationRequestBuilders.multipart?

Static import trong ví dụ là:

```java
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.multipart;
```

Builder multipart của Spring REST Docs hỗ trợ tích hợp tài liệu cho request được tạo bằng MockMvc. Hãy dùng đúng API import cho ví dụ MockMvc này; không nhầm với multipart builder dành cho các kiểu test client khác.

### 4.3. Vì sao controller nhận Map?

Ví dụ dùng `@RequestPart("metadata") Map<String, Object>` để làm rõ part JSON được chuyển đổi thành object. Trong dự án thật, nên dùng DTO có kiểu cụ thể và validation, ví dụ `ImageMetadata`, để bảo vệ contract. REST Docs đọc payload multipart được gửi trong test; nó không yêu cầu phải dùng Map ở controller.

## 5. Cách đọc snippet được sinh

Với operation identifier `images-upload`, các snippet liên quan thường được ghi vào `build/generated-snippets/images-upload/`:

| Snippet | Nguồn | Nội dung |
| --- | --- | --- |
| `request-parts.adoc` | `requestParts(...)` | Bảng các part image và metadata |
| `request-part-metadata-body.adoc` | `requestPartBody("metadata")` | Body JSON của part metadata |
| `request-part-metadata-fields.adoc` | `requestPartFields("metadata", ...)` | Bảng field trong JSON metadata |
| `http-request.adoc` | Snippet HTTP request mặc định | Request multipart đã thực thi |
| `http-response.adoc` | Snippet HTTP response mặc định | HTTP response của endpoint |

Tên snippet part được tạo từ tên part. Ví dụ part `metadata` tạo `request-part-metadata-fields.adoc`; part `manifest` sẽ tạo `request-part-manifest-fields.adoc`.

### 5.1. Nhúng vào Asciidoctor

Ví dụ `src/docs/asciidoc/images.adoc`:

```asciidoc
= Image API
:toc: left

== POST /images

Upload một file ảnh cùng metadata JSON.

=== Các part của request

include::{snippets}/images-upload/request-parts.adoc[]

=== JSON metadata mẫu

include::{snippets}/images-upload/request-part-metadata-body.adoc[]

=== Các field trong metadata

include::{snippets}/images-upload/request-part-metadata-fields.adoc[]

=== HTTP response

include::{snippets}/images-upload/http-response.adoc[]
```

Bảng `request-parts` giải thích vai trò từng part. Snippet body cho người đọc thấy JSON mẫu. Bảng field làm rõ schema, kiểu/ý nghĩa từng field qua mô tả và được kiểm tra bởi test.

Nếu chỉ cần bảng field, có thể bỏ `requestPartBody`. Nếu chỉ cần liệt kê part mà không document nội dung JSON, `requestParts` có thể là đủ. Chọn snippet theo nhu cầu người đọc thay vì luôn thêm mọi loại snippet.

## 6. Quy tắc strict của requestPartFields

Mặc định, `requestPartFields` hoạt động ở chế độ strict đối với payload của part được chọn:

- Nếu JSON chứa một field chưa có descriptor, test thất bại.
- Nếu descriptor mô tả một field bắt buộc nhưng field không có trong JSON, test thất bại.
- Nếu field được đánh dấu `optional()`, field đó có thể vắng mặt.
- Nếu một descriptor là subsection, các hậu duệ của nhánh đó được xem là đã document trong snippet hiện tại.

Ví dụ, nếu metadata được bổ sung:

```json
{
  "title": "Ảnh bìa",
  "description": "Ảnh sản phẩm",
  "category": "PRODUCT",
  "visibility": "PUBLIC"
}
```

Nhưng bảng chỉ có `title`, `description` và `category`, test strict có thể thất bại vì `visibility` chưa được document. Đây là tín hiệu tốt để nhóm cập nhật tài liệu theo thay đổi contract.

### 6.1. optional()

Nếu `description` không bắt buộc:

```java
fieldWithPath("description")
    .optional()
    .description("Mô tả bổ sung cho ảnh, nếu có")
```

Chỉ dùng `optional()` khi contract cho phép client bỏ qua field. Không dùng nó như một cách làm cho test qua khi fixture sai hoặc path bị gõ nhầm.

### 6.2. ignored()

Nếu có field nội bộ đã biết nhưng không muốn xuất hiện trong bảng:

```java
fieldWithPath("internalSource")
    .ignored()
```

Field được xử lý như đã được bỏ qua có chủ đích và không xuất hiện trong snippet. Chỉ sử dụng với field thật sự không thuộc phần tài liệu công khai; không lạm dụng để che một thay đổi schema chưa được review.

### 6.3. relaxedRequestPartFields()

Nếu chỉ document một phần field trong kịch bản cụ thể, có thể dùng:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedRequestPartFields;

relaxedRequestPartFields(
    "metadata",
    fieldWithPath("title").description("Tiêu đề ảnh"),
    fieldWithPath("category").description("Nhóm ảnh")
)
```

Ở chế độ relaxed, field chưa được document không làm test thất bại. Các descriptor đã khai báo vẫn được kiểm tra theo quy tắc bắt buộc/optional. Đây là lựa chọn cho tài liệu chỉ tập trung một vài field, nhưng khả năng phát hiện field mới trong part sẽ giảm so với strict mode.

## 7. Part JSON có object lồng nhau và mảng

`requestPartFields` dùng cùng cú pháp path của payload documentation. Ví dụ metadata có:

```json
{
  "title": "Ảnh bìa",
  "dimensions": {
    "width": 1600,
    "height": 900
  },
  "tags": [
    "product",
    "campaign"
  ],
  "variants": [
    {
      "name": "thumbnail",
      "format": "WEBP"
    },
    {
      "name": "original",
      "format": "PNG"
    }
  ]
}
```

Các path có thể mô tả:

```java
requestPartFields("metadata",
    fieldWithPath("title")
        .description("Tiêu đề ảnh"),
    fieldWithPath("dimensions.width")
        .description("Chiều rộng ảnh theo pixel"),
    fieldWithPath("dimensions.height")
        .description("Chiều cao ảnh theo pixel"),
    fieldWithPath("tags")
        .description("Danh sách nhãn của ảnh"),
    fieldWithPath("variants[].name")
        .description("Tên biến thể"),
    fieldWithPath("variants[].format")
        .description("Định dạng file của biến thể")
)
```

Dấu chấm biểu thị object lồng nhau; `[]` biểu thị các phần tử của mảng. Path được tính từ **gốc JSON part**, không có tiền tố tên part `metadata`.

Nếu một object lồng nhau lớn nên được tóm tắt, có thể dùng `subsectionWithPath("dimensions")` trong descriptor để mô tả cả nhánh. Khi cần document chi tiết hơn, thêm các field tương ứng trong một snippet riêng hoặc thiết kế bảng để phần quan trọng được kiểm tra strict. Không nên vừa khai báo subsection bao phủ toàn bộ nhánh vừa kỳ vọng snippet đó sẽ phát hiện mọi field con mới.

## 8. Tên part và path phải khớp với request thật

`requestPartFields("metadata", ...)` lấy payload từ part tên `metadata`. Nếu request thực tế gửi tên `meta`, REST Docs không tự suy ra chúng là cùng một phần. Tên part thường được xác định bởi:

- tên trong `MockMultipartFile("metadata", ...)`;
- tên part của client;
- tên trong tham số controller `@RequestPart("metadata")`;
- tên được truyền vào `requestPartFields("metadata", ...)`.

Các tên này phải khớp theo contract.

Một lỗi khác là dùng path đầy đủ gồm tên part:

```java
// Sai: tên part đã được chỉ định riêng.
requestPartFields("metadata",
    fieldWithPath("metadata.title").description("Tiêu đề")
);

// Đúng: path bắt đầu từ gốc JSON của part.
requestPartFields("metadata",
    fieldWithPath("title").description("Tiêu đề")
);
```

Nếu path không khớp JSON, test có thể báo thiếu field được document hoặc field chưa được document. Hãy kiểm tra JSON thực tế của part trước khi đổi descriptor.

## 9. Dùng requestPartFields với WebTestClient và REST Assured

API `requestPartFields` nằm trong `PayloadDocumentation` nên descriptor không phụ thuộc riêng MockMvc. Cách tạo multipart request và gắn `document` thay đổi theo test client.

### 9.1. WebTestClient

Ví dụ tạo multipart body bằng `BodyInserters.fromMultipartData`:

```java
MultiValueMap<String, Object> multipartData = new LinkedMultiValueMap<>();
multipartData.add("image", imageResource);
multipartData.add("metadata", metadataMap);

webTestClient.post()
    .uri("/images")
    .body(BodyInserters.fromMultipartData(multipartData))
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("images-upload",
        requestPartFields("metadata",
            fieldWithPath("title").description("Tiêu đề ảnh"),
            fieldWithPath("category").description("Nhóm ảnh")
        )
    ));
```

`webTestClient` cần được cấu hình Spring REST Docs documentation filter trước khi thực hiện exchange. Các biến `imageResource`, `metadataMap` và client là dữ liệu/cấu hình đã chuẩn bị trong test. Để tạo multipart file ổn định, có thể dùng `ByteArrayResource` override `getFilename()`.

### 9.2. REST Assured

Với REST Assured, dùng `multiPart` để gửi file và part JSON, sau đó gắn snippet qua filter:

```java
Map<String, Object> metadata = new HashMap<>();
metadata.put("title", "Ảnh bìa sản phẩm");
metadata.put("category", "PRODUCT");

RestAssured.given(this.spec)
    .accept("application/json")
    .filter(document("images-upload",
        requestPartFields("metadata",
            fieldWithPath("title").description("Tiêu đề ảnh"),
            fieldWithPath("category").description("Nhóm ảnh")
        )
    ))
    .multiPart("image", new File("cover.png"), "image/png")
    .multiPart("metadata", metadata)
    .when()
    .post("/images")
    .then()
    .statusCode(201);
```

Các đoạn trên minh họa vị trí của handler. Test hoàn chỉnh cần chuẩn bị server/spec/client và dependencies theo cấu hình dự án. Part JSON cần được gửi với media type và serialization phù hợp để payload mà REST Docs quan sát là JSON mong đợi.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy part `metadata` | Tên part trong request khác đối số `requestPartFields` | Đồng bộ tên MockMultipartFile, client, controller và descriptor |
| Không document được field | Path có tiền tố `metadata.` dù part đã được chọn | Dùng path tương đối từ gốc JSON part |
| JSON part không được chuyển đổi | Media type sai hoặc body JSON không hợp lệ | Dùng `application/json` và xác nhận JSON hợp lệ |
| Test báo field chưa document | Payload có field mới hoặc thiếu descriptor | Thêm descriptor hoặc quyết định dùng subsection/ignored có chủ đích |
| Test báo field bắt buộc không tồn tại | Descriptor sai path hoặc field thật sự vắng mặt | Kiểm tra JSON; đánh dấu optional nếu contract cho phép |
| Chỉ có snippet request-parts, không có bảng field | Chỉ gọi `requestParts(...)` | Bổ sung `requestPartFields(...)` |
| Có body snippet nhưng không có bảng field | Chỉ gọi `requestPartBody(...)` | Bổ sung `requestPartFields(...)` |
| Không có file snippet sau test | Test chưa tới document, operation ID sai hoặc output directory khác | Kiểm tra assertion, `document(...)` và cấu hình output |
| Mảng rỗng khiến field trong mảng không được tìm thấy | Fixture không có phần tử chứa path `items[].x` | Sinh schema từ test có phần tử; test mảng rỗng riêng |

## 11. Tích hợp Asciidoctor và CI

Với Gradle Groovy DSL, giả định dự án đã cấu hình Spring REST Docs, test và plugin Asciidoctor:

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

Trong CI, cần xác nhận:

1. Test multipart chạy thành công và đi tới handler `document(...)`.
2. Tên part trong request trùng với part name trong `requestPartFields`.
3. Part JSON có content type phù hợp và payload hợp lệ.
4. Bảng field strict phát hiện field mới hoặc field bắt buộc bị thiếu.
5. Asciidoctor đọc đúng thư mục snippet vừa sinh.
6. Các snippet body/field được include đúng tên trong tài liệu.

Với Maven, thư mục snippet thường là `target/generated-snippets`; bước biên soạn tài liệu phải chạy sau test sinh snippet.

## 12. Bài thực hành

Mở rộng test `ImageUploadDocumentationTest`:

1. **Tạo multipart:** gửi part file `image` và part JSON `metadata`, đặt đúng content type cho từng part.
2. **Document các part:** dùng `requestParts(...)` để mô tả mục đích của image và metadata.
3. **Document body:** dùng `requestPartBody("metadata")` để sinh JSON snippet.
4. **Document field:** dùng `requestPartFields("metadata", ...)` để mô tả title, description, category và copyright.
5. **Thử field mới:** thêm `metadata.visibility` mà chưa khai báo descriptor. Quan sát test strict thất bại; sau đó cập nhật tài liệu.
6. **Thử optional:** bỏ `description` khỏi JSON và dùng `optional()` theo contract; bỏ optional để quan sát kết quả.
7. **Path lồng nhau:** thêm `dimensions.width` và `variants[].format` rồi document chúng bằng path tương đối.
8. **Đổi tên part:** đổi `metadata` thành `details` ở request; đồng bộ controller, `requestPartBody` và `requestPartFields`.
9. **Build tài liệu:** chạy `./gradlew clean test asciidoctor` trong dự án đã cấu hình và xác nhận snippet được include.

**Tiêu chí hoàn thành:** bạn phân biệt được bảng part, body part và bảng field part; tạo được snippet `request-part-metadata-fields.adoc`; giải thích được path tính từ gốc JSON part; và dùng strict/optional/relaxed đúng theo contract.

## 13. Câu hỏi tự kiểm tra

**1. `requestPartFields("metadata", ...)` document điều gì?**

Nó document các field bên trong payload của part tên `metadata` của multipart request.

**2. Snippet được sinh có tên gì?**

Với part `metadata`, bảng field có tên `request-part-metadata-fields.adoc`. Body part có tên `request-part-metadata-body.adoc`.

**3. Có cần viết `metadata.title` trong descriptor không?**

Không. Tên part đã là đối số riêng. Path field bắt đầu từ gốc JSON part, nên dùng `title`.

**4. requestParts khác requestPartFields thế nào?**

`requestParts` mô tả danh sách các part của multipart request; `requestPartFields` mô tả field trong JSON/body của một part cụ thể.

**5. Khi nào dùng relaxedRequestPartFields?**

Khi tài liệu chỉ tập trung một phần field và chấp nhận field chưa document xuất hiện. Với contract cần phát hiện schema drift, ưu tiên chế độ strict.

**6. requestPartFields có document bytes của file ảnh không?**

Không. Nó document field của part payload. File part có thể được mô tả về tên, mục đích và metadata bằng `requestParts`; không đưa nội dung nhị phân ảnh vào bảng JSON metadata.

## Tài liệu tham khảo

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): request parts, request part body, request part fields, strict/relaxed và snippet names.
- [PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html): chữ ký `requestPartFields` và `relaxedRequestPartFields`.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): cấu hình test, snippet và tích hợp tài liệu.

