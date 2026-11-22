# Xử lý nhiều request part cùng loại trong Spring REST Docs

## 1. Mô hình nhiều file cùng part name

Một endpoint upload có thể nhận nhiều file trong cùng request `multipart/form-data`. Ví dụ, ba ảnh đính kèm cho một bài viết được gửi thành ba part riêng, tất cả cùng tên `attachments`:

```http
Content-Disposition: form-data; name="attachments"; filename="front.png"
Content-Type: image/png

<front image bytes>
------boundary
Content-Disposition: form-data; name="attachments"; filename="side.png"
Content-Type: image/png

<side image bytes>
------boundary
Content-Disposition: form-data; name="attachments"; filename="back.png"
Content-Type: image/png

<back image bytes>
```

Mỗi file là một **part occurrence** (một lần xuất hiện trong body). Các occurrence có chung **part name** nhưng có filename riêng. RFC 7578 mục 4.3 quy định nhiều file cho cùng một form field được gửi thành nhiều part riêng, dùng cùng tham số `name`.

Spring REST Docs mô tả tên part bằng `requestParts(...)` và `partWithName(...)`. Snippet `request-parts.adoc` là bảng các part được resource hỗ trợ; nó không biểu diễn cardinality (số lần lặp) của cùng một tên thành các dòng riêng. Vì vậy, document `attachments` một lần và diễn giải đây là trường nhận nhiều file. Test ứng dụng cần xác minh số lượng, filename, content type và các quy tắc của từng file.

Bài này tập trung vào nhiều file cùng tên, nhiều trường file khác tên nhưng cùng media type, collection binding trong Spring MVC, multipart builders của MockMvc/WebTestClient/REST Assured và tích hợp tài liệu vào CI.

## 2. Phân biệt occurrence, part name và media type

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Part occurrence | File thứ nhất, thứ hai, thứ ba | Một lần xuất hiện trong multipart body |
| Part name | `attachments` | Tên trường multipart; nhiều occurrence có thể cùng tên |
| Filename | `front.png` | Tên tệp do client cung cấp |
| Content-Type | `image/png` | Loại nội dung của từng occurrence |

Cùng media type không có nghĩa cùng part name. Ví dụ `frontCover` và `backCover` đều có thể là `image/png` nhưng là hai trường riêng:

```java
requestParts(
    partWithName("frontCover").description("Ảnh bìa trước"),
    partWithName("backCover").description("Ảnh bìa sau")
)
```

Ngược lại, nhiều file của trường `attachments` có cùng part name. Không đổi chúng thành `attachments1`, `attachments2` nếu hợp đồng API định nghĩa một trường lặp.

## 3. Spring MVC bind nhiều file cùng tên

Spring MVC hỗ trợ bind nhiều file cùng parameter name vào `List<MultipartFile>` hoặc `MultipartFile[]`. Ví dụ:

```java
@PostMapping(
    value = "/articles/{articleId}/attachments",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<?> upload(
        @PathVariable String articleId,
        @RequestParam("attachments") List<MultipartFile> attachments) {
    // Validate collection và xử lý từng file.
}
```

`@RequestParam("attachments")` chỉ ra tên trường multipart. Collection biểu diễn các file có cùng tên đó. Không khai báo một `MultipartFile` đơn nếu contract yêu cầu nhận toàn bộ occurrence.

| Kiểu tham số | Khi phù hợp |
| --- | --- |
| `List<MultipartFile>` | Số file thay đổi; thuận tiện validate collection |
| `MultipartFile[]` | Muốn xử lý dưới dạng mảng |
| `MultipartFile` | Contract chỉ cho phép một file |
| `MultiValueMap<String, MultipartFile>` | Cần truy cập nhiều nhóm file theo tên động |

Với collection, quyết định rõ thứ tự có phải một phần contract hay không. Nếu thứ tự không quan trọng, tránh test phụ thuộc thứ tự. Nếu thứ tự có ý nghĩa, chẳng hạn các trang tài liệu, hãy mô tả và kiểm tra quy tắc đó.

## 4. Document tên part lặp bằng Spring REST Docs

Dùng một descriptor cho tên part:

```java
requestParts(
    partWithName("attachments")
        .description("Danh sách file ảnh; mỗi file được gửi thành một part riêng cùng tên attachments")
)
```

Descriptor tham chiếu `name="attachments"`, không tham chiếu filename. Không tạo descriptor giả cho từng occurrence. Snippet có một dòng cho part name, còn Description nói rõ tính lặp.

**Giới hạn:** `requestParts` document tên part được hỗ trợ và kiểm tra các part theo strict/relaxed mode. Nó không thay thế test kiểm tra số file, giới hạn tối thiểu/tối đa, kích thước hay thứ tự. Những quy tắc đó cần validation/assertion riêng.

### 4.1. File collection đi cùng metadata JSON

Một request có thể có trường lặp `attachments` và một part `metadata`:

```java
requestParts(
    partWithName("attachments")
        .description("Nhiều file ảnh; mỗi file là một part cùng tên"),
    partWithName("metadata")
        .description("Metadata JSON dùng chung cho nhóm ảnh")
),
requestPartFields("metadata",
    fieldWithPath("caption").description("Chú thích chung"),
    fieldWithPath("source").description("Nguồn ảnh")
)
```

`requestPartFields` chỉ mô tả JSON metadata. Không dùng API này để document bytes của file ảnh.

## 5. Ví dụ MockMvc hoàn chỉnh

Ví dụ dùng JUnit 5, Java 17+, MockMvc và Spring REST Docs. Fixture bytes bên dưới chỉ dùng kiểm tra multipart binding; nó không phải ảnh PNG hợp lệ để kiểm thử bộ giải mã ảnh.

```java
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.multipart;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class MultipleAttachmentPartsDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new AttachmentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void uploadSeveralFilesWithOnePartName() throws Exception {
        MockMultipartFile front = new MockMultipartFile(
                "attachments", "front.png",
                MediaType.IMAGE_PNG_VALUE, new byte[] {1, 2, 3});
        MockMultipartFile side = new MockMultipartFile(
                "attachments", "side.png",
                MediaType.IMAGE_PNG_VALUE, new byte[] {4, 5, 6});
        MockMultipartFile back = new MockMultipartFile(
                "attachments", "back.png",
                MediaType.IMAGE_PNG_VALUE, new byte[] {7, 8, 9});

        this.mockMvc.perform(multipart("/articles/{id}/attachments", "42")
                        .file(front)
                        .file(side)
                        .file(back)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.count").value(3))
                .andExpect(jsonPath("$.files[0].filename").value("front.png"))
                .andExpect(jsonPath("$.files[1].filename").value("side.png"))
                .andExpect(jsonPath("$.files[2].filename").value("back.png"))
                .andDo(document("articles-attachments-upload",
                        requestParts(
                            partWithName("attachments")
                                .description("Nhiều file ảnh; mỗi file là một part cùng tên attachments")
                        )
                ));
    }

    @RestController
    static class AttachmentController {

        @PostMapping(
            value = "/articles/{id}/attachments",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        ResponseEntity<Map<String, Object>> upload(
                @PathVariable String id,
                @RequestParam("attachments") List<MultipartFile> attachments) {

            if (attachments.isEmpty() || attachments.size() > 3) {
                return ResponseEntity.badRequest().build();
            }

            List<Map<String, Object>> files = attachments.stream()
                    .map(file -> Map.<String, Object>of(
                            "filename", file.getOriginalFilename(),
                            "contentType", file.getContentType(),
                            "size", file.getSize()))
                    .toList();

            return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
                    "articleId", id,
                    "count", attachments.size(),
                    "files", files
            ));
        }
    }
}
```

Cả ba `MockMultipartFile` đều có name `attachments`, nhưng filename riêng. Controller bind vào `List<MultipartFile>`, kiểm tra giới hạn 1–3 file và trả metadata để test xác minh số lượng và tên tệp. `requestParts` sinh bảng part; các assertions kiểm tra hành vi binding và cardinality của ứng dụng.

### 5.1. Tại sao tham số đầu tiên giống nhau?

Chữ ký `MockMultipartFile(name, originalFilename, contentType, content)` phân biệt part name và filename. Cả ba fixture truyền `attachments` làm name, còn `front.png`, `side.png`, `back.png` là filename. Nếu đổi name thành front/side/back thì đó là ba trường multipart khác nhau.

## 6. Kiểm tra số lượng và metadata từng file

| Quy tắc | Cách kiểm tra |
| --- | --- |
| Ít nhất một file | Collection không rỗng hoặc trả validation error |
| Số file tối đa | Kiểm tra `attachments.size()` |
| Kích thước mỗi file | `MultipartFile.getSize()` |
| Content-Type | `getContentType()` và xác minh định dạng nếu cần |
| Filename | Kiểm tra tên rỗng, độ dài, ký tự và chuẩn hóa |
| Nội dung file | Parser, magic bytes, checksum hoặc kiểm tra nghiệp vụ |
| Thứ tự | Chỉ assert nếu thứ tự là một phần contract |
| File trùng | Kiểm tra checksum hoặc định danh nghiệp vụ nếu cần |

Với giới hạn một đến ba tệp, tạo ca test cho 0, 1, 3 và 4 file. Nếu giới hạn áp dụng cho từng file, kiểm tra từng size; nếu có giới hạn tổng request, tính tổng size của collection. Test lỗi vượt giới hạn nên có operation identifier riêng nếu cần sinh tài liệu lỗi.

Không mặc định thứ tự là contract. Nếu thứ tự không quan trọng, so sánh tập metadata thay vì phụ thuộc chỉ số; nếu có ý nghĩa, định nghĩa và kiểm tra rõ.

## 7. Nhiều tên part nhưng cùng loại file

Nếu endpoint nhận hai vai trò ảnh cố định, tên part khác nhau dù cả hai có Content-Type image/png:

```java
@PostMapping(value = "/products", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
ResponseEntity<?> uploadProductImages(
        @RequestPart("frontCover") MultipartFile frontCover,
        @RequestPart("backCover") MultipartFile backCover) {
    // ...
}
```

Document bằng hai descriptor:

```java
requestParts(
    partWithName("frontCover").description("Ảnh bìa trước"),
    partWithName("backCover").description("Ảnh bìa sau")
)
```

Không dùng collection attachments nếu API định nghĩa hai vai trò cố định. Controller và tài liệu phải phản ánh đúng contract, không chỉ dựa trên việc hai file có cùng media type.

## 8. WebTestClient gửi nhiều part cùng tên

`MultiValueMap<String, Object>` cho phép nhiều giá trị cho một key. Gọi `add` nhiều lần:

```java
MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();

Resource front = new ByteArrayResource(new byte[] {1, 2, 3}) {
    @Override
    public String getFilename() {
        return "front.png";
    }
};
Resource side = new ByteArrayResource(new byte[] {4, 5, 6}) {
    @Override
    public String getFilename() {
        return "side.png";
    }
};

parts.add("attachments", front);
parts.add("attachments", side);

webTestClient.post()
    .uri("/articles/42/attachments")
    .body(BodyInserters.fromMultipartData(parts))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("articles-attachments-upload",
        requestParts(
            partWithName("attachments")
                .description("Danh sách file; nhiều occurrence cùng tên attachments")
        )
    ));
```

Dùng `set` có thể thay giá trị trước đó. WebTestClient cần được gắn documentation filter REST Docs trên builder trước khi build. Test tích hợp nên xác minh server bind đủ các file.

## 9. REST Assured gửi nhiều part cùng tên

REST Assured cho phép gọi `multiPart` nhiều lần với cùng part name:

```java
given(this.spec)
    .filter(document("articles-attachments-upload",
        requestParts(
            partWithName("attachments")
                .description("Danh sách file ảnh; mỗi file là một part cùng tên")
        )
    ))
    .multiPart("attachments", new File("front.png"), "image/png")
    .multiPart("attachments", new File("side.png"), "image/png")
    .multiPart("attachments", new File("back.png"), "image/png")
    .when()
    .post("/articles/42/attachments")
    .then()
    .statusCode(201);
```

Mỗi lời gọi thêm một occurrence. Dùng file fixture trong project, không tham chiếu đường dẫn tùy ý trên máy developer. `spec` và REST Docs filter cần được cấu hình theo test framework của dự án.

## 10. Tên snippet và tài liệu Asciidoctor

Với operation identifier `articles-attachments-upload`, snippet chính thường nằm tại:

```text
build/generated-snippets/
└── articles-attachments-upload/
    ├── request-parts.adoc
    ├── http-request.adoc
    └── http-response.adoc
```

Ví dụ biên soạn:

```asciidoc
== POST /articles/{id}/attachments

Trường attachments nhận từ một đến ba file ảnh.
Client gửi mỗi file thành một part riêng; mọi part trong nhóm
dùng cùng tên attachments. Filename là metadata riêng của từng file.

=== Multipart parts

include::{snippets}/articles-attachments-upload/request-parts.adoc[]

=== Quy tắc collection

* Part name: attachments.
* Số lượng: từ 1 đến 3 file.
* Media type: các định dạng ảnh được endpoint hỗ trợ.
* Mỗi file có filename và nội dung riêng.
* Thứ tự chỉ có ý nghĩa nếu contract quy định rõ.
```

Bảng request-parts document tên part và Description. Cardinality, media type và thứ tự cần được diễn giải theo contract và kiểm tra riêng; không suy ra số lượng tối đa từ một dòng snippet.

## 11. Optional, ignored và relaxed

`optional()` trên descriptor cho phép toàn bộ trường multipart vắng mặt theo contract; nó không xác định số occurrence tối đa. Nếu API cho phép 0–3 file, hãy mô tả rõ và validate collection size từ 0 đến 3.

`ignored()` dùng cho một part đã biết nhưng chủ ý không đưa vào snippet. `relaxedRequestParts(...)` cho phép part name chưa được mô tả xuất hiện mà không làm test thất bại. Relaxed mode không kiểm tra cardinality, size hay bytes.

| Nhu cầu | Cách thực hiện |
| --- | --- |
| Trường attachments bắt buộc | `partWithName("attachments")` không optional |
| Cả trường có thể vắng | Đánh dấu descriptor `optional()` |
| Giới hạn 1–3 file | Validation/assertion trên collection |
| Bỏ qua part kỹ thuật | `ignored()` |
| Document một tập con part name | `relaxedRequestParts(...)` |
| Kiểm tra media type từng file | Duyệt collection và validate từng MultipartFile |

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chỉ nhận một file | Controller bind vào `MultipartFile` đơn | Dùng `List<MultipartFile>` hoặc mảng |
| Files thành các trường khác nhau | Client gửi name front/side/back | Gửi cùng `attachments` và filename riêng |
| Bảng request-parts chỉ có một dòng | Nhầm snippet tên part với bảng occurrence | Giải thích multiplicity và assert collection size |
| WebTestClient chỉ gửi file cuối | Dùng `set` thay vì `add` | Gọi `add` nhiều lần cùng key |
| REST Assured gửi nhầm part | Tên truyền vào `multiPart` không thống nhất | Dùng cùng tên trong mọi lời gọi |
| Test pass dù vượt số file | Chỉ document part name, không validate collection | Thêm assertion/validation cardinality |
| Assertion thứ tự không ổn định | Contract không cam kết thứ tự | So sánh tập hoặc định nghĩa thứ tự rõ |
| Chỉ file đầu được kiểm tra media type | Validation không duyệt collection | Kiểm tra từng file |
| Filename trùng làm ghi đè | Dùng filename client làm tên lưu | Tạo storage key do server quản lý |
| Asciidoctor thiếu snippet | Sai operation ID hoặc test chưa sinh file | Kiểm tra thư mục output và dependency task |

## 13. Build và CI

Với Gradle Groovy DSL, giả định dự án đã cấu hình REST Docs và Asciidoctor:

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

CI nên xác nhận:

1. Test gửi đúng số occurrence của part lặp.
2. Controller bind tất cả file vào collection hoặc array.
3. Assertions kiểm tra giới hạn số lượng.
4. Mỗi file được kiểm tra filename, content type, size và nội dung theo contract.
5. `requestParts` mô tả part name và Asciidoctor include đúng operation.
6. Có test 0, 1, số tối đa và vượt giới hạn.
7. Fixture nhỏ, ổn định, giả lập và không chứa thông tin nhạy cảm.

Với Maven, snippet thường ở `target/generated-snippets`; bước dựng tài liệu chạy sau test sinh snippet.

## 14. Bài thực hành

Mở rộng endpoint `POST /articles/{id}/attachments`:

1. Đổi controller sang `List<MultipartFile>` và gửi ba part cùng tên `attachments`.
2. Dùng một `partWithName("attachments")` có Description giải thích mỗi file là một occurrence cùng tên.
3. Tạo test cho 0, 1, 3 và 4 file; xác minh giới hạn 1–3.
4. Assert filename và Content-Type từng file; thêm trường hợp file rỗng.
5. Quyết định thứ tự có phải contract không; nếu có thì assert, nếu không thì không phụ thuộc index.
6. Dùng `MultiValueMap.add("attachments", ...)` hai lần trong WebTestClient.
7. Gọi `multiPart("attachments", ...)` nhiều lần trong REST Assured.
8. Tạo endpoint khác nhận `frontCover` và `backCover` để phân biệt tên part với media type.
9. Include `request-parts.adoc` và viết quy tắc cardinality trong Asciidoctor.
10. Chạy `./gradlew clean test asciidoctor` trong dự án đã cấu hình.

**Tiêu chí hoàn thành:** phân biệt occurrence, part name và media type; gửi được nhiều file cùng tên; document đúng tên part; kiểm tra cardinality bằng test ứng dụng và giải thích contract trong tài liệu.

## 15. Câu hỏi tự kiểm tra

**1. Nhiều file cùng một field được biểu diễn thế nào?**

Mỗi file là một part riêng nhưng các part dùng cùng tham số `name`; mỗi part có filename riêng.

**2. Spring MVC bind nhiều file cùng tên bằng kiểu nào?**

Có thể dùng `List<MultipartFile>` hoặc `MultipartFile[]`.

**3. Có cần tạo descriptor attachments1, attachments2 và attachments3 không?**

Không. Nếu wire format dùng cùng `name="attachments"`, document một descriptor `partWithName("attachments")` và giải thích trường nhận nhiều file.

**4. request-parts snippet có xác nhận số file không?**

Không. Nó mô tả tên part được hỗ trợ. Cardinality cần được kiểm tra bằng validation/assertion.

**5. frontCover và backCover đều là PNG thì có dùng một descriptor không?**

Không nếu tên part khác nhau. Dùng descriptor riêng cho từng name và mô tả vai trò.

**6. MultiValueMap gửi nhiều part cùng tên bằng cách nào?**

Gọi `add("attachments", value)` nhiều lần; `set` có thể thay giá trị đã gắn với key.

## Tài liệu tham khảo

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): request parts, strict/relaxed documentation và snippet.
- [RFC 7578 — mục 4.3](https://www.rfc-editor.org/rfc/rfc7578.html#section-4.3): nhiều file cho một form field.
- [Spring Framework — Multipart forms](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): bind nhiều file cùng parameter name vào List/array MultipartFile.

