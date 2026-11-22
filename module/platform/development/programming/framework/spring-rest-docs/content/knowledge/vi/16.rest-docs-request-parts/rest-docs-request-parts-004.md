# Headers của request part trong Spring REST Docs

## 1. Vì sao cần quan tâm đến header của từng part?

Một `multipart/form-data` request có một HTTP request tổng thể, bên trong chứa nhiều part. Mỗi part có tên, nội dung và có thể có các header riêng. Khi upload ảnh cùng metadata JSON, ví dụ:

- Part `image` mang bytes của ảnh và có `Content-Type: image/png`.
- Part `metadata` mang JSON và có `Content-Type: application/json`.
- Part `image` thường có `Content-Disposition` với `name="image"` và `filename="cover.png"`.

Các header này có vai trò khác nhau. Header cấp HTTP như `Authorization`, `Accept` hoặc `Content-Type: multipart/form-data; boundary=...` áp dụng cho toàn request. Header nằm trong một part như `Content-Type: image/png` hoặc `Content-Disposition: form-data; name="image"; filename="cover.png"` mô tả riêng part đó.

Trong Spring REST Docs, `requestHeaders(...)` tạo snippet cho **HTTP request headers cấp ngoài**. `requestParts(...)` mô tả tên và mục đích của part; `requestPartBody(...)` và `requestPartFields(...)` mô tả nội dung part. Spring REST Docs không cung cấp snippet chuẩn riêng có tên `requestPartHeaders(...)`. Vì vậy, khi cần tài liệu hóa header từng part, ta cần trình bày chúng trong ví dụ multipart request hoặc xây dựng snippet tùy biến từ dữ liệu operation.

Bài này thuộc chương **Request parts** của SPRING_REST_DOCS. Module thực hành tạo tài liệu REST API có thể kiểm chứng từ bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured, sau đó đưa snippet vào Asciidoctor/Markdown và build/CI.

Sau bài học, bạn có thể:

- Phân biệt header cấp HTTP request và header của từng multipart part.
- Nhận biết các header thường gặp như `Content-Disposition` và `Content-Type`.
- Dùng `requestHeaders(...)` đúng phạm vi.
- Kết hợp `requestParts(...)`, body part và field part để mô tả multipart contract.
- Kiểm tra header từng part trong test và quyết định khi nào cần snippet tùy biến.
- Tránh nhầm filename, part name, MIME type và boundary.

## 2. Hai lớp header trong multipart request

Ví dụ `POST /api/images` gửi ảnh và metadata:

```http
POST /api/images HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
Content-Type: multipart/form-data; boundary=----UploadBoundary

------UploadBoundary
Content-Disposition: form-data; name="image"; filename="cover.png"
Content-Type: image/png

<bytes của ảnh PNG>
------UploadBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json; charset=UTF-8

{
  "title": "Bìa sách",
  "description": "Ảnh bìa phiên bản mới"
}
------UploadBoundary--
```

Có thể phân lớp như sau:

| Header | Phạm vi | Ví dụ | Mục đích |
| --- | --- | --- | --- |
| `Authorization` | Toàn HTTP request | `Bearer ...` | Xác thực request |
| `Accept` | Toàn HTTP request | `application/json` | Định dạng response client mong đợi |
| `Content-Type` ngoài | Toàn HTTP request | `multipart/form-data; boundary=...` | Báo body là multipart và xác định boundary |
| `Content-Disposition` của part | Một part | `form-data; name="image"; filename="cover.png"` | Xác định tên part và tên file được gửi |
| `Content-Type` của part | Một part | `image/png` | Mô tả định dạng nội dung part |
| `Content-Type` của part JSON | Một part | `application/json; charset=UTF-8` | Chỉ định JSON và charset của metadata |

**Boundary không phải tên part.** Nó là dấu phân cách các phần trong body multipart, do client/HTTP stack tạo và gắn vào `Content-Type` cấp ngoài. Không nên hard-code boundary vào tài liệu hợp đồng vì giá trị này có thể đổi theo từng request.

## 3. Phân biệt API tài liệu hóa header cấp request và part

### 3.1. `requestHeaders(...)` mô tả header ngoài

Spring REST Docs dùng `requestHeaders(...)` cùng `headerWithName(...)` để tài liệu hóa header của toàn HTTP request:

```java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;

.andDo(document("images-upload",
        requestHeaders(
                headerWithName("Authorization")
                        .description("Bearer token dùng để xác thực"),
                headerWithName("Accept")
                        .description("Định dạng response client chấp nhận"),
                headerWithName("Content-Type")
                        .description("Multipart request body")
        ),
        requestParts(
                partWithName("image")
                        .description("Ảnh sản phẩm cần tải lên"),
                partWithName("metadata")
                        .description("Metadata JSON của ảnh")
        )
));
```

Snippet header cấp ngoài thường có tên `request-headers.adoc`. Nó không tự tạo các dòng cho `Content-Type: image/png` hoặc `Content-Disposition` bên trong part.

### 3.2. Header từng part nằm trong multipart body

Với một part file, ví dụ:

```http
Content-Disposition: form-data; name="image"; filename="cover.png"
Content-Type: image/png
```

`requestParts(...)` tạo bảng tên part và mô tả part; nó không phải bảng tất cả header của part. `requestPartBody("metadata")` tạo snippet body của part metadata; nó cũng không phải snippet header chuyên biệt.

Có thể dùng `http-request.adoc` được sinh từ operation để đưa ví dụ HTTP request vào tài liệu. Khi kiểm tra output cụ thể, hãy xác nhận tích hợp và formatter đang dùng thể hiện multipart body/header đến mức nào; đừng giả định `request-parts.adoc` sẽ chứa toàn bộ raw header.

### 3.3. Không có API chuẩn `requestPartHeaders(...)`

Trong API Spring REST Docs hiện hành, những tiện ích chính cho multipart gồm:

| API | Phạm vi |
| --- | --- |
| `requestParts(...)` | Tên và mô tả các part |
| `partWithName(...)` | Descriptor cho một part |
| `requestPartBody("metadata")` | Body của một part |
| `requestPartFields("metadata", ...)` | Field bên trong payload JSON của part |
| `requestHeaders(...)` | Header cấp HTTP request |

Không nên viết `requestPartHeaders(...)` như thể đây là phương thức Spring REST Docs có sẵn. Nếu cần bảng riêng cho header part, có thể tạo snippet tùy biến hoặc mô tả header trong nội dung Asciidoctor cạnh request mẫu.

## 4. Tài liệu hóa multipart request bằng MockMvc

Giả sử endpoint `POST /api/images` nhận `image` và `metadata`, trả `201 Created` khi upload hợp lệ. Dự án đã có Spring Boot, JUnit 5, MockMvc và dependency `spring-restdocs-mockmvc`.

### 4.1. Tạo part với tên file và content type

```java
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

MockMultipartFile image = new MockMultipartFile(
        "image",
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
```

Đối số của `MockMultipartFile` lần lượt bao gồm:

1. `name`: tên part, ví dụ `image`.
2. `originalFilename`: tên file được client gửi, ví dụ `cover.png`.
3. `contentType`: content type của part, ví dụ `image/png`.
4. `content`: bytes của part.

Tên `image` là giá trị cần khớp với `partWithName("image")` và tên tham số controller. `cover.png` là filename, không phải tên part.

### 4.2. Kết hợp request headers và request parts

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ImageMultipartHeadersDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentMultipartRequestHeadersAndParts() throws Exception {
        MockMultipartFile image = new MockMultipartFile(
                "image",
                "cover.png",
                MediaType.IMAGE_PNG_VALUE,
                validPngBytes()
        );

        MockMultipartFile metadata = new MockMultipartFile(
                "metadata",
                "",
                MediaType.APPLICATION_JSON_VALUE,
                """
                {"title":"Bìa sách","description":"Ảnh bìa phiên bản mới"}
                """.getBytes(StandardCharsets.UTF_8)
        );

        mockMvc.perform(multipart("/api/images")
                    .file(image)
                    .file(metadata)
                    .header("Authorization", "Bearer test-token")
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andDo(document("images-upload",
                        requestHeaders(
                                headerWithName("Authorization")
                                        .description("Bearer token xác thực"),
                                headerWithName("Accept")
                                        .description("Định dạng response client chấp nhận"),
                                headerWithName("Content-Type")
                                        .description("Multipart request body")
                        ),
                        requestParts(
                                partWithName("image")
                                        .description("Ảnh PNG cần tải lên"),
                                partWithName("metadata")
                                        .description("Metadata JSON mô tả ảnh")
                        )
                ));
    }

    private byte[] validPngBytes() {
        // Đọc bytes của fixture PNG hợp lệ từ test resources.
        return TestFixtures.validPng();
    }
}
```

Đây là ví dụ minh họa; `TestFixtures.validPng()` đại diện cho helper lấy file fixture của dự án. Khi chạy test thật, thay helper bằng resource PNG hợp lệ và assertion status đúng với endpoint.

Trong ví dụ, `requestHeaders(...)` mô tả `Authorization`, `Accept` và `Content-Type` cấp ngoài; `requestParts(...)` mô tả hai part. Content type từng part được gắn khi dựng `MockMultipartFile`. Bảng request headers không thay thế tài liệu về `image/png` hay `application/json` nằm trong từng part.

## 5. Mô tả metadata JSON bên trong part

`requestParts(...)` chỉ mô tả part ở cấp multipart. Nếu `metadata` chứa JSON, cần dùng API dành cho payload part để mô tả sâu hơn.

### 5.1. Tạo snippet body part

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

.andDo(document("images-upload",
        requestParts(
                partWithName("image").description("Ảnh PNG"),
                partWithName("metadata").description("Metadata JSON")
        ),
        requestPartBody("metadata")
));
```

Snippet được sinh có tên `request-part-metadata-body.adoc`, chứa body của part `metadata`.

### 5.2. Tạo snippet fields của JSON part

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

.andDo(document("images-upload",
        requestParts(
                partWithName("image").description("Ảnh PNG"),
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

Snippet `request-part-metadata-fields.adoc` mô tả field bên trong JSON. Đây là field-level payload documentation; nó không phải bảng header của part.

## 6. Khi nào cần snippet tùy biến cho part headers?

Nếu hợp đồng yêu cầu bảng riêng như sau:

| Part | Header | Giá trị hoặc quy tắc |
| --- | --- | --- |
| `image` | `Content-Disposition` | `name="image"`; filename do client cung cấp |
| `image` | `Content-Type` | `image/png` hoặc `image/jpeg` |
| `metadata` | `Content-Disposition` | `name="metadata"` |
| `metadata` | `Content-Type` | `application/json` |

có thể lựa chọn hai cách.

### 6.1. Viết bảng hợp đồng trong Asciidoctor

Nếu header part ổn định và đơn giản, bảng tĩnh là dễ bảo trì:

```adoc
=== Headers của từng part

|===
|Part |Header |Quy tắc

|`image`
|`Content-Disposition`
|`name="image"`; filename do client cung cấp

|`image`
|`Content-Type`
|`image/png` hoặc `image/jpeg`

|`metadata`
|`Content-Disposition`
|`name="metadata"`

|`metadata`
|`Content-Type`
|`application/json`
|===
```

Đây là phần giải thích contract do người viết duy trì. Nó không tự được kiểm chứng bởi `requestParts(...)`; cần test xác nhận content type/filename thực tế.

### 6.2. Tạo custom snippet từ operation request parts

Trong mô hình operation của Spring REST Docs, mỗi `OperationRequestPart` cung cấp thông tin tên part, filename, content và headers. Có thể dùng dữ liệu này để xây dựng snippet riêng nếu muốn bảng được sinh từ request của test.

Ví dụ về dữ liệu có thể đọc trong custom snippet:

```java
import org.springframework.restdocs.operation.Operation;
import org.springframework.restdocs.operation.OperationRequestPart;

for (OperationRequestPart part : operation.getRequest().getParts()) {
    String partName = part.getName();
    String filename = part.getSubmittedFileName();

    // Headers của part, ví dụ Content-Type và Content-Disposition.
    HttpHeaders headers = part.getHeaders();
}
```

Đoạn trên minh họa API dữ liệu để đọc, không phải một snippet hoàn chỉnh. Khi triển khai, cần tạo một lớp implement `Snippet`, nhận `Operation` trong callback tạo snippet, chuyển dữ liệu part thành bảng AsciiDoc/Markdown và ghi output qua cơ chế snippet của Spring REST Docs. Tên file output, template, escaping và xử lý header nhạy cảm cần được xác định trong implementation của dự án.

Nếu chỉ cần header của một vài part, custom snippet có thể chỉ chọn `Content-Type` và `Content-Disposition`, thay vì dump toàn bộ header. Tránh ghi các header chứa token, cookie hoặc thông tin nội bộ vào tài liệu được xuất bản.

## 7. Kiểm tra header từng part trong test

Tài liệu là phần trình bày contract; test HTTP cần xác nhận ứng dụng nhận đúng content type, filename và nội dung part theo yêu cầu.

Các tình huống nên kiểm thử:

| Tình huống | Kỳ vọng theo contract ví dụ |
| --- | --- |
| `image` có `Content-Type: image/png` và bytes PNG hợp lệ | Được chấp nhận |
| `image` có `Content-Type: image/jpeg` và bytes JPEG hợp lệ | Được chấp nhận nếu API hỗ trợ JPEG |
| `image` có `Content-Type: text/plain` | Bị từ chối nếu chỉ nhận ảnh |
| `metadata` có `Content-Type: application/json` | JSON được parse |
| `metadata` có content type không hỗ trợ | Bị từ chối hoặc xử lý theo contract |
| Filename chứa ký tự không hợp lệ | Được chuẩn hóa hoặc bị từ chối theo chính sách |
| Filename bị bỏ trống | Xử lý theo contract, không suy ra từ tên part |

Content-Type do client khai báo không chứng minh bytes thực sự mang định dạng đó. Nếu endpoint cần bảo vệ khỏi file giả MIME type, cần kiểm tra chữ ký file hoặc parse nội dung bằng thư viện thích hợp.

Với MockMvc, `MockMultipartFile` cho phép chỉ định `contentType` và `originalFilename` để tạo fixture có đặc tính khác nhau. Test endpoint nên gửi các biến thể này và xác nhận response status/body. Với test tài liệu hóa, giữ một request mẫu đại diện cho trường hợp thành công và đặt operation ID riêng cho các kịch bản khác nếu cần snippet độc lập.

## 8. WebTestClient và REST Assured

### 8.1. WebTestClient

Để đặt header cho part trong request WebTestClient, có thể bọc nội dung part bằng `HttpEntity` cùng `HttpHeaders` khi xây dựng `MultiValueMap`:

```java
HttpHeaders metadataHeaders = new HttpHeaders();
metadataHeaders.setContentType(MediaType.APPLICATION_JSON);

HttpEntity<String> metadataPart =
        new HttpEntity<>(metadataJson, metadataHeaders);

MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
parts.add("image", imageResource);
parts.add("metadata", metadataPart);

webTestClient.post()
        .uri("/api/images")
        .contentType(MediaType.MULTIPART_FORM_DATA)
        .body(BodyInserters.fromMultipartData(parts))
        .exchange()
        .expectStatus().isCreated()
        .expectBody()
        .consumeWith(document("images-upload",
                requestParts(
                        partWithName("image").description("Ảnh sản phẩm"),
                        partWithName("metadata").description("Metadata JSON")
                )
        ));
```

`HttpEntity` cho phép gắn header vào part khi Spring message converter tạo multipart request. Với file `Resource`, filename có thể được lấy từ `getFilename()`; content type có thể suy ra hoặc thiết lập rõ bằng wrapper phù hợp.

### 8.2. REST Assured

REST Assured hỗ trợ khai báo multipart part cùng content type:

```java
given(this.spec)
        .filter(document("images-upload",
                requestParts(
                        partWithName("image").description("Ảnh sản phẩm"),
                        partWithName("metadata").description("Metadata JSON")
                )))
        .multiPart("image", imageFile, "image/png")
        .multiPart("metadata", metadataJson, "application/json")
        .when()
        .post("/api/images")
        .then()
        .statusCode(201);
```

Cú pháp overload `multiPart(...)` cần được kiểm tra theo phiên bản REST Assured của dự án. Dù dùng builder nào, tên part và content type cuối cùng gửi trên wire mới là dữ liệu cần đối chiếu.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `requestHeaders(...)` không liệt kê `image/png` | Đang mô tả header cấp ngoài | Dùng ví dụ multipart hoặc custom snippet cho header từng part |
| Nhầm `Content-Type` ngoài với `Content-Type` của part | Hai header cùng tên nhưng phạm vi khác nhau | Ghi rõ phạm vi trong tài liệu |
| `requestParts(...)` không hiển thị filename | Snippet mô tả tên/mục đích part | Đưa filename vào request ví dụ hoặc custom snippet nếu cần bảng |
| Nhầm filename với part name | Đọc `filename` thay vì `name` trong Content-Disposition | Dùng `partWithName("image")` theo `name` |
| Metadata JSON không có bảng field | Chỉ gọi `requestParts(...)` | Thêm `requestPartFields("metadata", ...)` |
| Snippet body không xuất hiện | Chưa gọi `requestPartBody("metadata")` | Bổ sung body snippet nếu cần |
| Content type sai nhưng test vẫn qua | Chưa có validation phía endpoint | Thêm kiểm tra và negative test |
| Tài liệu lộ Authorization hoặc Cookie | Ghi raw header nhạy cảm vào snippet | Mask hoặc dùng token giả trong fixture |
| Asciidoctor báo thiếu include | Tên operation hoặc snippet chưa được sinh | Kiểm tra test và output directory |

## 10. Asciidoctor và build/CI

Nguồn tài liệu có thể include các snippet sẵn có:

```adoc
= Image API
:toc: left

== Upload ảnh

=== HTTP request headers
include::{snippets}/images-upload/request-headers.adoc[]

=== Multipart parts
include::{snippets}/images-upload/request-parts.adoc[]

=== Metadata body
include::{snippets}/images-upload/request-part-metadata-body.adoc[]

=== Metadata fields
include::{snippets}/images-upload/request-part-metadata-fields.adoc[]

=== Headers của từng part
Xem bảng contract multipart được duy trì trong phần này hoặc custom snippet của dự án.
```

Chỉ include các snippet mà bài test thực sự tạo. Với Gradle và plugin Asciidoctor đã cấu hình:

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
       +--> requestHeaders (header cấp HTTP)
       |
       +--> requestParts (tên và mô tả part)
       |
       +--> requestPartBody / requestPartFields
       |
       +--> custom snippet nếu cần header từng part
       |
       v
Asciidoctor / bước xuất Markdown
       |
       v
Kiểm tra và xuất bản
```

Nếu dự án xuất Markdown, cần template hoặc bước chuyển đổi riêng; không mặc định Spring REST Docs sinh snippet `.md`. Khi header part thay đổi, test content type/filename và custom snippet (nếu có) phải được chạy lại trong CI.

## 11. Bài thực hành

Với endpoint `POST /api/images`:

1. Tạo `image` và `metadata` với hai content type khác nhau. Xác nhận tên part và `Content-Type` từng part.
2. Thêm `Authorization` và `Accept` ở HTTP request. Dùng `requestHeaders(...)` để mô tả header cấp ngoài.
3. Kiểm tra vì sao `requestHeaders(...)` không tạo các dòng `image/png` và `application/json` cho từng part.
4. Thêm `requestPartBody("metadata")` và `requestPartFields("metadata", ...)` để mô tả body và schema JSON.
5. Viết bảng Asciidoctor mô tả `Content-Disposition` và `Content-Type` của từng part.
6. Nếu cần dữ liệu sinh tự động, tạo custom snippet đọc `OperationRequest.getParts()` và `OperationRequestPart.getHeaders()`.
7. Viết negative tests cho sai MIME type, filename không hợp lệ và metadata sai content type.
8. Kiểm tra snippet không chứa token/cookie thật; chạy test trước khi kết xuất Asciidoctor trong CI.

### Câu hỏi tự đánh giá

- `Content-Type` của toàn request khác `Content-Type` bên trong một part thế nào?
- `requestHeaders(...)` mô tả header ở phạm vi nào?
- `partWithName("image")` liên quan đến `name` hay `filename` trong `Content-Disposition`?
- Vì sao `requestParts(...)` không tạo bảng header cho từng part?
- Khi nào `requestPartBody(...)` và `requestPartFields(...)` hữu ích?
- Dữ liệu nào trong `OperationRequestPart` có thể dùng để xây custom snippet?
- Vì sao cần che Authorization và Cookie trước khi xuất snippet?

**Ghi nhớ:** Multipart có header ở hai lớp: header cấp HTTP và header riêng của từng part. `requestHeaders(...)` chỉ tài liệu hóa lớp ngoài; `requestParts(...)` mô tả các part. Để trình bày header như `Content-Type` và `Content-Disposition` của từng part, hãy dùng ví dụ multipart hoặc custom snippet dựa trên thông tin part của operation, đồng thời kiểm thử các quy tắc đó trên request thực tế.

## Tài liệu tham khảo

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): request parts, part body và part fields.
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html): `requestHeaders` và `responseHeaders` cho header cấp HTTP.
- [Spring REST Docs — `OperationRequestPart` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/OperationRequestPart.html): truy cập tên, filename, nội dung và headers của từng part.
