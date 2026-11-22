# Document multipart request bằng `requestParts`

## 1. Multipart request là gì?

Một HTTP request có thể cần gửi nhiều loại nội dung trong cùng một lần gọi. Ví dụ, chức năng tải ảnh sản phẩm cần gửi file ảnh nhị phân cùng metadata JSON như tên ảnh, mô tả, thứ tự hiển thị hoặc mã sản phẩm. Gửi tất cả dưới một JSON thông thường không phù hợp với dữ liệu file nhị phân; gửi file và metadata ở hai request riêng có thể làm quy trình upload phức tạp hơn.

`multipart/form-data` giải quyết bài toán này bằng cách chia request body thành nhiều **part**. Mỗi part có tên riêng, có thể có header và content type riêng. Ví dụ:

- Part `image`: file ảnh, content type `image/png`.
- Part `metadata`: JSON mô tả ảnh, content type `application/json`.

Trong **Spring REST Docs**, `requestParts(...)` tạo snippet mô tả các part được hỗ trợ bởi operation. Các descriptor được tạo bằng `partWithName(...)`. Bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured gửi multipart request thực tế; Spring REST Docs đối chiếu các part trong request với descriptor rồi tạo `request-parts.adoc`.

Bài này thuộc chương **Request parts** của SPRING_REST_DOCS. Sau khi học, bạn có thể:

- Hiểu cấu trúc multipart request và vai trò của từng part.
- Khai báo `requestParts(partWithName(...))` để mô tả tên và mục đích của part.
- Dùng MockMvc tạo request gồm file và JSON metadata.
- Phân biệt `requestParts`, `requestPartBody` và `requestPartFields`.
- Xử lý part bắt buộc, optional, ignored và relaxed.
- Đưa snippet multipart vào Asciidoctor và build/CI.

## 2. Cấu trúc của multipart/form-data

Một request upload có thể được biểu diễn về mặt logic như sau:

```text
POST /api/images
Content-Type: multipart/form-data; boundary=...

Part: image
Content-Disposition: form-data; name="image"; filename="cover.png"
Content-Type: image/png

<bytes của file ảnh>

Part: metadata
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "title": "Bìa sách",
  "description": "Ảnh bìa phiên bản mới"
}
```

Mỗi part có ít nhất một tên. Với part chứa file, header `Content-Disposition` thường kèm `filename`; `Content-Type` cho biết định dạng nội dung. Với part metadata JSON, body là văn bản JSON và `Content-Type` thường là `application/json`.

| Part | Nội dung | Content type ví dụ | Mục đích |
| --- | --- | --- | --- |
| `image` | Bytes của file ảnh | `image/png` | Ảnh cần upload |
| `metadata` | JSON | `application/json` | Thông tin mô tả ảnh |
| `thumbnail` | Bytes ảnh thu nhỏ | `image/jpeg` | Ảnh xem trước, có thể tùy chọn |

**Tên part là một phần của contract API.** Nếu server nhận part tên `metadata`, client gửi `meta` sẽ không tương đương. Descriptor trong Spring REST Docs cần dùng đúng tên được gửi trong multipart request.

## 3. `requestParts(...)` và `partWithName(...)`

Spring REST Docs cung cấp hai phương thức trong `org.springframework.restdocs.request.RequestDocumentation`:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
```

Một descriptor căn bản:

```java
partWithName("image")
        .description("File ảnh cần tải lên");
```

Gom các descriptor vào snippet:

```java
requestParts(
        partWithName("image")
                .description("File ảnh cần tải lên"),
        partWithName("metadata")
                .description("Metadata JSON của ảnh")
);
```

`requestParts(...)` tạo snippet `request-parts.adoc`, trong đó có bảng mô tả các part mà operation hỗ trợ.

Ở chế độ strict:

- Part có trong request nhưng không có descriptor có thể làm test thất bại.
- Descriptor mô tả một part bắt buộc nhưng part đó không xuất hiện trong request cũng làm test thất bại.
- Descriptor `.optional()` cho phép part đã mô tả vắng mặt trong request mẫu.
- Descriptor `.ignored()` nhận diện part nhưng không đưa nó vào snippet và tránh lỗi do part đó không có dòng mô tả.

Với một operation chỉ cần mô tả một số part, `relaxedRequestParts(...)` cho phép các part chưa được mô tả xuất hiện mà không làm test thất bại. Các part descriptor đã khai báo vẫn phải hiện diện, trừ khi được đánh dấu optional.

### 3.1. Part bắt buộc và optional

Ví dụ part `thumbnail` chỉ có ở một số request:

```java
requestParts(
        partWithName("image")
                .description("File ảnh chính"),
        partWithName("metadata")
                .description("Thông tin JSON của ảnh"),
        partWithName("thumbnail")
                .description("Ảnh xem trước nếu client cung cấp")
                .optional()
);
```

`.optional()` ở đây áp dụng cho **sự hiện diện của part**. Nó không có nghĩa body của part được phép là chuỗi rỗng hoặc JSON `null`. Đây là những quy tắc nội dung khác và cần mô tả/kiểm thử riêng.

### 3.2. Part được nhận nhưng không đưa vào snippet

Nếu request có part kỹ thuật đã biết nhưng operation không cần trình bày:

```java
partWithName("clientTrace")
        .description("Mã trace do client gửi")
        .ignored();
```

Part này được nhận diện nhưng không trở thành dòng trong `request-parts.adoc`. Nếu nó có thể vắng mặt trong payload mẫu, có thể kết hợp `.optional()` và `.ignored()`.

### 3.3. Strict và relaxed

| API | Part chưa khai báo | Part đã khai báo nhưng thiếu |
| --- | --- | --- |
| `requestParts(...)` | Có thể làm test thất bại | Bắt buộc phải có, trừ khi optional |
| `relaxedRequestParts(...)` | Được phép tồn tại | Bắt buộc phải có, trừ khi optional |
| `.ignored()` trên descriptor | Part được nhận diện và không hiển thị | Theo quy tắc presence của descriptor |
| `.optional()` trên descriptor | Không thay đổi cách xử lý part dư | Cho phép part đã mô tả vắng mặt |

Chỉ dùng relaxed mode khi contract chủ đích cho phép part bổ sung hoặc operation đang minh họa một tập con. Đối với API công khai có cấu trúc ổn định, strict mode giúp phát hiện part mới cần được review.

## 4. Tạo multipart request bằng MockMvc

Ví dụ sau giả định endpoint `POST /api/images` nhận hai part:

- `image`: file PNG bắt buộc.
- `metadata`: JSON bắt buộc.

Endpoint trả `201 Created` khi upload thành công. Dự án đã cấu hình Spring Boot, JUnit 5, MockMvc và dependency `spring-restdocs-mockmvc`.

### 4.1. Dựng các part trong test

Dùng `MockMultipartFile` để tạo part file và part JSON:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

MockMultipartFile image = new MockMultipartFile(
        "image",
        "cover.png",
        MediaType.IMAGE_PNG_VALUE,
        imageBytes
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

Tham số đầu tiên của `MockMultipartFile` là **tên part**. Nó phải khớp với tên mà controller nhận và descriptor tài liệu hóa. Tên file là tham số thứ hai; content type là tham số thứ ba.

### 4.2. Gắn `requestParts(...)` vào operation

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

import java.nio.charset.StandardCharsets;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ImageUploadDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentImageUploadParts() throws Exception {
        byte[] imageBytes = new byte[] { 1, 2, 3, 4 };

        MockMultipartFile image = new MockMultipartFile(
                "image",
                "cover.png",
                MediaType.IMAGE_PNG_VALUE,
                imageBytes
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

        mockMvc.perform(multipart("/api/images")
                    .file(image)
                    .file(metadata)
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andDo(document("images-upload",
                        requestParts(
                                partWithName("image")
                                        .description("File ảnh PNG cần tải lên"),
                                partWithName("metadata")
                                        .description("Metadata JSON của ảnh")
                        )));
    }
}
```

Mảng byte ở ví dụ chỉ là dữ liệu giả lập để trình bày luồng kiểm thử. Với ứng dụng có kiểm tra định dạng file thật, hãy dùng fixture ảnh hợp lệ thay vì bốn byte tùy ý. Assertion HTTP status cần khớp với contract của endpoint thực tế.

Khi bài test chạy thành công, Spring REST Docs tạo snippet:

```text
build/generated-snippets/
└── images-upload/
    ├── http-request.adoc
    ├── http-response.adoc
    └── request-parts.adoc
```

Các snippet bổ sung như cURL hoặc HTTPie phụ thuộc cấu hình. `request-parts.adoc` là bảng part được sinh từ `requestParts(...)`.

## 5. `requestParts` khác `requestPartBody` và `requestPartFields`

Một multipart request có nhiều cấp thông tin. Chỉ mô tả tên part không đồng nghĩa với mô tả body bên trong part đó.

| API | Mục đích | Snippet |
| --- | --- | --- |
| `requestParts(...)` | Mô tả các part và ý nghĩa của từng part | `request-parts.adoc` |
| `requestPartBody("metadata")` | Đưa body của part `metadata` vào tài liệu | `request-part-metadata-body.adoc` |
| `requestPartFields("metadata", ...)` | Mô tả các field JSON bên trong part `metadata` | `request-part-metadata-fields.adoc` |

### 5.1. Ghi body của part JSON

Khi muốn người đọc thấy nội dung JSON nguyên bản của part `metadata`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

.andDo(document("images-upload",
        requestParts(
                partWithName("image").description("File ảnh"),
                partWithName("metadata").description("Metadata JSON")
        ),
        requestPartBody("metadata")
));
```

Snippet part body giúp người đọc xem ví dụ payload của riêng part. Nó hữu ích khi cấu trúc JSON có ý nghĩa nhưng chưa cần bảng mô tả từng field.

### 5.2. Mô tả field bên trong part JSON

Nếu `metadata` có schema mà client cần hiểu, dùng `requestPartFields(...)`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

.andDo(document("images-upload",
        requestParts(
                partWithName("image").description("File ảnh"),
                partWithName("metadata").description("Metadata JSON")
        ),
        requestPartFields("metadata",
                fieldWithPath("title")
                        .description("Tiêu đề ảnh"),
                fieldWithPath("description")
                        .description("Mô tả ảnh")
                        .optional()
        )
));
```

`requestPartFields("metadata", ...)` kiểm tra cấu trúc JSON **bên trong part `metadata`**. Các descriptor ở đây là `FieldDescriptor`, nên dùng `fieldWithPath(...)` giống khi mô tả request JSON bình thường. Nó không mô tả tên các part của multipart request; phần đó vẫn do `requestParts(...)` đảm nhiệm.

Kết quả snippet:

```text
request-parts.adoc
request-part-metadata-body.adoc
request-part-metadata-fields.adoc
```

Không phải operation nào cũng cần cả ba. Chọn theo nhu cầu người đọc:

- Chỉ cần biết operation nhận file và metadata: `requestParts(...)`.
- Cần xem JSON mẫu trong metadata: thêm `requestPartBody("metadata")`.
- Cần hiểu schema của JSON: thêm `requestPartFields("metadata", ...)`.

### 5.3. Tên part trong các API phải khớp nhau

Nếu part được tạo với tên `metadata`, các lời gọi phải thống nhất:

```java
requestParts(partWithName("metadata").description("Metadata JSON"));

requestPartBody("metadata");

requestPartFields("metadata",
        fieldWithPath("title").description("Tiêu đề ảnh"));
```

Đổi tên một chỗ thành `meta` sẽ trỏ sang part khác hoặc không tìm thấy part tương ứng.

## 6. Dùng WebTestClient và REST Assured

Descriptor dùng cho `requestParts(...)` không phụ thuộc riêng MockMvc. Các module tích hợp có cách gắn snippet tương ứng.

### 6.1. WebTestClient

Một request multipart có thể được dựng bằng `BodyInserters.fromMultipartData(...)`:

```java
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
parts.add("image", imageResource);
parts.add("metadata", metadataResource);

webTestClient.post()
        .uri("/api/images")
        .body(BodyInserters.fromMultipartData(parts))
        .exchange()
        .expectStatus().isCreated()
        .expectBody()
        .consumeWith(document("images-upload",
                requestParts(
                        partWithName("image").description("File ảnh PNG"),
                        partWithName("metadata").description("Metadata JSON")
                )));
```

Khi dùng file upload, `Resource` chứa file nên cung cấp filename phù hợp nếu endpoint cần filename trong `Content-Disposition`. Kiểu content của từng part cũng cần được thiết lập theo cách dựng `HttpEntity` hoặc resource tương ứng trong ứng dụng.

### 6.2. REST Assured

Với REST Assured, filter tài liệu hóa được đặt trong request specification:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

given(this.spec)
        .filter(document("images-upload",
                requestParts(
                        partWithName("image").description("File ảnh PNG"),
                        partWithName("metadata").description("Metadata JSON")
                )))
        .multiPart("image", imageFile)
        .multiPart("metadata", metadataJson, "application/json")
        .when()
        .post("/api/images")
        .then()
        .statusCode(201);
```

Cách dựng part cụ thể phụ thuộc overload REST Assured được sử dụng và phiên bản thư viện. Điều quan trọng là tên part gửi đi phải trùng với descriptor và tài liệu hóa phải gắn vào request thực tế.

## 7. Optional, ignored và relaxed cho request parts

### 7.1. Part optional

Ví dụ `thumbnail` không bắt buộc:

```java
requestParts(
        partWithName("image").description("Ảnh chính"),
        partWithName("metadata").description("Metadata JSON"),
        partWithName("thumbnail")
                .description("Ảnh xem trước nếu có")
                .optional()
);
```

Nếu test upload không gửi `thumbnail`, snippet vẫn có thể được sinh vì descriptor đã đánh dấu optional. Nếu test gửi part này, descriptor vẫn mô tả nó.

### 7.2. Part ignored

```java
requestParts(
        partWithName("image").description("Ảnh chính"),
        partWithName("metadata").description("Metadata JSON"),
        partWithName("clientTrace")
                .description("Mã tracing")
                .ignored()
);
```

`clientTrace` được nhận diện nhưng không xuất hiện trong bảng request parts. Nếu part có thể vắng mặt, cần kết hợp `.optional()` theo hợp đồng. `.ignored()` không có nghĩa part trở thành optional, cũng không xóa part khỏi request thực tế.

### 7.3. Relaxed request parts

```java
import static org.springframework.restdocs.request.RequestDocumentation.relaxedRequestParts;

relaxedRequestParts(
        partWithName("image").description("Ảnh chính"),
        partWithName("metadata").description("Metadata JSON")
);
```

Với relaxed mode, part chưa được mô tả được phép tồn tại. Các part đã khai báo vẫn phải có mặt nếu không optional. Chọn relaxed mode khi operation cố tình chỉ tập trung vào một tập con part hoặc cho phép mở rộng part theo contract. Đừng dùng nó để che đi part mới có ý nghĩa nghiệp vụ mà tài liệu nên công bố.

## 8. Kiểm tra content type và validation của từng part

`requestParts(...)` mô tả tên và mục đích của part. Nó không tự bảo đảm:

- Part `image` thực sự là ảnh PNG hợp lệ.
- Part `metadata` là JSON hợp lệ hoặc có đủ field.
- File không vượt giới hạn dung lượng.
- Tên file, extension và MIME type phù hợp với nội dung thật.
- Part optional thỏa các điều kiện liên quan khi xuất hiện.

Các kiểm tra này cần được triển khai ở endpoint và xác minh bằng test HTTP riêng. Ví dụ metadata JSON có thể được kiểm tra bằng `requestPartFields(...)`, nhưng các quy tắc nghiệp vụ như tiêu đề không rỗng hoặc mô tả có độ dài tối đa vẫn cần validation.

Một bảng contract cho operation upload:

| Part | Required | Content type | Quy tắc |
| --- | --- | --- | --- |
| `image` | Có | `image/png` | File PNG hợp lệ, tối đa 5 MB |
| `metadata` | Có | `application/json` | JSON có `title` bắt buộc |
| `thumbnail` | Không | `image/jpeg` | Ảnh xem trước, tối đa 1 MB |
| `clientTrace` | Không | `text/plain` | Chỉ dùng để liên kết log |

Các giá trị dung lượng, MIME type và quy tắc trong bảng là ví dụ; thay bằng contract thật của API.

Với `metadata`, có thể bổ sung:

```java
requestPartFields("metadata",
        fieldWithPath("title")
                .description("Tiêu đề ảnh"),
        fieldWithPath("description")
                .description("Mô tả ảnh")
                .optional()
);
```

Cần thêm negative tests để xác nhận server xử lý đúng khi thiếu `image`, metadata sai JSON, MIME type không được hỗ trợ hoặc file vượt kích thước.

## 9. Asciidoctor và build/CI

Sau khi test tạo snippet, tài liệu Asciidoctor có thể include bảng parts:

```adoc
= Image API
:toc: left

== Upload ảnh

=== Các part của request

include::{snippets}/images-upload/request-parts.adoc[]

=== Metadata JSON

include::{snippets}/images-upload/request-part-metadata-body.adoc[]

=== Các trường metadata

include::{snippets}/images-upload/request-part-metadata-fields.adoc[]
```

Chỉ include các snippet mà test thực sự tạo ra. Nếu operation chỉ dùng `requestParts(...)`, các snippet part body và part fields sẽ không tồn tại.

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
Multipart HTTP test
        |
        v
requestParts / requestPartBody / requestPartFields
        |
        v
Generated snippets
        |
        v
Asciidoctor / bước chuyển Markdown
        |
        v
Kiểm tra và xuất bản tài liệu
```

Khi thêm part mới vào endpoint, strict `requestParts(...)` có thể khiến test thất bại nếu part chưa được mô tả. Nhóm cần quyết định có công bố part, ignore nó có chủ đích hay cập nhật contract. Không chỉnh snippet generated bằng tay để làm CI xanh.

Spring REST Docs thường tạo snippet AsciiDoc. Nếu muốn phát hành Markdown, cần template Markdown hoặc bước chuyển đổi được cấu hình riêng; không mặc định có file `request-parts.md`.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy part trong descriptor | Tên part trong `MockMultipartFile` khác `partWithName(...)` | Đồng bộ tên part giữa request, controller và descriptor |
| Test báo part chưa được tài liệu hóa | Multipart request có part mới nhưng strict `requestParts(...)` chưa khai báo | Thêm descriptor, ignore có chủ đích hoặc relaxed theo contract |
| Test báo thiếu part | Descriptor bắt buộc nhưng request mẫu không gửi | Bổ sung part hoặc `.optional()` nếu contract cho phép thiếu |
| Part ignored vẫn có trong HTTP request | `.ignored()` chỉ ẩn dòng trong snippet | Đây là hành vi đúng; nó không xóa part khỏi request |
| Metadata JSON không có bảng field | Chỉ gọi `requestParts(...)` | Thêm `requestPartFields("metadata", ...)` |
| Không có snippet body metadata | Chưa gọi `requestPartBody("metadata")` | Thêm snippet nếu tài liệu cần body mẫu |
| `requestPartFields` báo field chưa mô tả | JSON trong part có field mới hoặc path sai | Cập nhật field descriptor theo JSON của part |
| Multipart endpoint không nhận file | Sai tên part, thiếu filename hoặc dựng body sai định dạng | Kiểm tra `Content-Disposition`, content type và cách tạo request |
| Asciidoctor báo thiếu include | Include snippet không được test tạo ra | Kiểm tra tên operation, task test và snippet đã cấu hình |

## 11. Bài thực hành

Dựa trên endpoint `POST /api/images`:

1. Tạo hai part bắt buộc `image` và `metadata`, sau đó sinh `request-parts.adoc`.
2. Thêm `thumbnail` là part optional. Chạy một test có thumbnail và một test không gửi thumbnail.
3. Thêm `clientTrace` và đánh dấu `.ignored()`. Xác nhận part vẫn được gửi tới endpoint nhưng không xuất hiện trong bảng.
4. Thêm field `title` và `description` vào JSON metadata. Dùng `requestPartFields("metadata", ...)` để sinh bảng field.
5. Dùng `requestPartBody("metadata")` để include JSON body nguyên bản.
6. Cố tình đổi tên part từ `metadata` thành `meta` trong request nhưng không sửa descriptor. Quan sát lỗi, rồi cập nhật contract hoặc fixture đúng.
7. Viết negative tests cho file quá lớn, sai content type và metadata thiếu `title`.
8. Include snippet parts và metadata vào Asciidoctor; xác nhận CI chạy test trước khi kết xuất tài liệu.

### Câu hỏi tự đánh giá

- `requestParts(...)` mô tả cấp nào của multipart request?
- `partWithName("metadata")` phải khớp với phần nào trong request?
- `.optional()` và `.ignored()` trên part khác nhau thế nào?
- Khi nào dùng `relaxedRequestParts(...)`?
- Vì sao `requestParts(...)` không thay thế `requestPartFields(...)`?
- `requestPartBody("metadata")` và `requestPartFields("metadata", ...)` sinh ra những thông tin khác nhau nào?
- Vì sao cần negative tests cho MIME type và kích thước file?

**Ghi nhớ:** `requestParts(...)` mô tả **các part** của multipart request bằng tên và ý nghĩa. Nếu cần tài liệu hóa nội dung của một part, dùng `requestPartBody(...)` để trình bày body hoặc `requestPartFields(...)` để mô tả các field bên trong. Kết hợp các snippet này với test upload thực tế, validation và build/CI giúp tài liệu multipart request theo sát contract của API.

## Tài liệu tham khảo

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): `requestParts`, `relaxedRequestParts`, request part body và request part fields.
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html): `requestParts`, `relaxedRequestParts` và `partWithName`.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): tài liệu hóa field của JSON payload.
