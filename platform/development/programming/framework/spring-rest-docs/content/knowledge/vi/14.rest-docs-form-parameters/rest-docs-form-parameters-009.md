# Không dùng form documentation cho multipart part trong Spring REST Docs

## 1. Ranh giới giữa form parameters và multipart parts

Spring REST Docs cung cấp các nhóm snippet mô tả những cấu trúc HTTP khác nhau. Với request **application/x-www-form-urlencoded**, dữ liệu được gửi thành các cặp tên/giá trị trong body và được mô tả bằng `formParameters(...)`. Với request **multipart/form-data**, body gồm nhiều part độc lập; mỗi part có header và nội dung riêng. Trường hợp này cần `requestParts(...)`, và dùng `requestPartFields(...)` nếu một part chứa JSON có cấu trúc.

Chọn snippet theo **Content-Type và cấu trúc trên wire**, không theo việc một trường có được gọi là “field của form” trong giao diện:

| Request body | Cấu trúc | Spring REST Docs |
| --- | --- | --- |
| `application/x-www-form-urlencoded` | Các cặp `name=value` nối bằng `&` | `formParameters(...)` |
| `multipart/form-data; boundary=...` | Nhiều part, mỗi part có header và payload | `requestParts(...)` |
| Multipart part chứa JSON | JSON nằm bên trong một part | `requestPartFields(...)` |
| JSON là toàn bộ request body | JSON document ở cấp request | `requestFields(...)` |

Trong module **SPRING_REST_DOCS**, test HTTP bằng MockMvc, WebTestClient hoặc REST Assured tạo snippet cho request, response, payload, tham số và header. Các snippet được biên soạn thành Asciidoctor/Markdown rồi đưa vào build/CI. Dùng `formParameters` để mô tả một multipart upload là sai cấp cấu trúc: tên field của giao diện không thay thế metadata của từng part.

## 2. Hai wire format nhìn từ HTTP

### 2.1. URL-encoded form

```http
POST /preferences HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

email=mai%40example.com&plan=pro&topics=java&topics=spring
```

Body chứa các cặp tên/giá trị. Có thể lặp tên parameter để gửi nhiều giá trị. Nội dung không có part header riêng, filename hay boundary. Dùng `formParameters(...)` để mô tả `email`, `plan` và `topics`.

### 2.2. Multipart form

```http
POST /documents HTTP/1.1
Content-Type: multipart/form-data; boundary=----ExampleBoundary

------ExampleBoundary
Content-Disposition: form-data; name="title"

Tài liệu khóa học
------ExampleBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"category":"lesson","published":false}
------ExampleBoundary
Content-Disposition: form-data; name="attachments"; filename="lesson-a.txt"
Content-Type: text/plain

Nội dung tệp A
------ExampleBoundary--
```

Mỗi part bắt đầu bằng boundary. Header `Content-Disposition` xác định tên part và có thể có filename; `Content-Type` có thể mô tả kiểu nội dung của part. Trong ví dụ:

- `title` là text part.
- `metadata` là JSON part.
- `attachments` là file part.

Đều là **multipart parts**. Part text không trở thành URL-encoded form parameter chỉ vì nội dung của nó là chuỗi. Nếu hợp đồng API nói request dùng multipart, hãy mô tả tên part và mục đích bằng `requestParts(...)`.

Ví dụ đã lược giản để dễ đọc. Multipart thực tế dùng boundary khai báo trong Content-Type và delimiter tuân theo định dạng MIME, gồm CRLF đúng quy tắc. Không tự cố định boundary trong client; hãy để HTTP client tạo boundary tương ứng với body.

## 3. Vì sao `formParameters(...)` không phù hợp với multipart?

`formParameters(...)` sinh snippet cho form parameters của URL-encoded form. Multipart có các đối tượng tài liệu hóa riêng:

- `requestParts(...)` mô tả part có trong multipart request.
- `requestPartFields(...)` mô tả field bên trong part có payload có cấu trúc, ví dụ JSON.
- `requestPartBody(...)` ghi lại nội dung body của một part nếu muốn tài liệu hóa payload thô.

Đừng nhầm `requestFields(...)` với `requestPartFields(...)`. Khác biệt nằm ở cấp payload:

| API | Cấp dữ liệu được mô tả | Ví dụ |
| --- | --- | --- |
| `formParameters` | Tên parameter của URL-encoded body | `topics=java` |
| `requestParts` | Tên part trong multipart body | part `attachments` |
| `requestPartFields` | Field bên trong payload của một part | `metadata.category` |
| `requestFields` | Field trong toàn bộ request JSON body | JSON document ở cấp request |

Trong multipart, `title` cũng là một part. Không đưa `title` vào `formParameters(...)` chỉ vì nó là text. Làm vậy khiến tài liệu trộn hai định dạng body và client không biết phải gửi URL-encoded hay multipart.

## 4. Controller Spring MVC nhận multipart

Ví dụ endpoint nhận tiêu đề, metadata JSON và tối đa hai tệp:

```java
package example.docs;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/documents")
public class DocumentController {
    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<Void> create(
            @RequestPart("title") String title,
            @RequestPart("metadata") DocumentMetadata metadata,
            @RequestPart("attachments") List<MultipartFile> attachments) {
        if (title.isBlank() || attachments.isEmpty() || attachments.size() > 2) {
            return ResponseEntity.badRequest().build();
        }
        if (attachments.stream().anyMatch(MultipartFile::isEmpty)) {
            return ResponseEntity.badRequest().build();
        }
        // Ví dụ: lưu metadata/tệp được lược bỏ.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Part metadata có kiểu Java:

```java
package example.docs;

public record DocumentMetadata(String category, boolean published) {
}
```

Với `@RequestPart("metadata")`, Spring dùng message converter để đọc part có media type phù hợp (trong ví dụ là `application/json`) thành `DocumentMetadata`. Với file upload, `MultipartFile` biểu diễn nội dung và metadata của tệp.

Một số lưu ý:

- `@RequestPart` phù hợp khi part cần chuyển đổi qua message converter, đặc biệt JSON/XML.
- `@RequestParam` cũng có thể bind phần tử multipart trong một số trường hợp Spring MVC, nhưng không làm request trở thành URL-encoded form.
- `consumes = MULTIPART_FORM_DATA_VALUE` khai báo media type của toàn request.
- Client phải gửi đúng tên part: `title`, `metadata` và `attachments`. Nhiều file cùng tên có thể bind vào `List<MultipartFile>`.
- Ứng dụng thật cần giới hạn kích thước, xác thực nội dung, tên tệp, loại media, quyền truy cập và chính sách lưu trữ.

## 5. MockMvc: tạo multipart request

### 5.1. Test với text part và file part

`MockMultipartFile` giúp tạo nội dung test mà không cần tệp thật:

```java
package example.docs;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(DocumentController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class DocumentMultipartDocumentationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentsMultipartRequestParts() throws Exception {
        MockMultipartFile title = new MockMultipartFile(
                "title", "", "text/plain",
                "Tài liệu khóa học".getBytes(StandardCharsets.UTF_8));
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata", "", MediaType.APPLICATION_JSON_VALUE,
                "{\"category\":\"lesson\",\"published\":false}"
                        .getBytes(StandardCharsets.UTF_8));
        MockMultipartFile attachment = new MockMultipartFile(
                "attachments", "lesson-a.txt", "text/plain",
                "Nội dung tệp A".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/documents")
                .file(title)
                .file(metadata)
                .file(attachment))
            .andExpect(status().isCreated())
            .andDo(document("documents/create-multipart",
                requestParts(
                    partWithName("title")
                        .description("Tiêu đề tài liệu dạng text"),
                    partWithName("metadata")
                        .description("Metadata JSON của tài liệu"),
                    partWithName("attachments")
                        .description("Tệp đính kèm; có thể lặp part cùng tên")
                )
            ));
    }
}
```

`title` và `metadata` được dựng bằng `MockMultipartFile`, vì thế chúng cũng là multipart part. Tên constructor đầu tiên là tên part; filename rỗng biểu diễn part không phải file. `attachments` dùng filename để thể hiện file upload.

### 5.2. Tên part lặp lại

Nếu API nhận nhiều tệp cùng tên `attachments`, tạo nhiều `MockMultipartFile`:

```java
MockMultipartFile first = new MockMultipartFile(
        "attachments", "lesson-a.txt", "text/plain",
        "Tệp A".getBytes(StandardCharsets.UTF_8));
MockMultipartFile second = new MockMultipartFile(
        "attachments", "lesson-b.txt", "text/plain",
        "Tệp B".getBytes(StandardCharsets.UTF_8));

mockMvc.perform(multipart("/documents")
        .file(first)
        .file(second))
    .andExpect(status().isCreated());
```

Một descriptor `partWithName("attachments")` mô tả **tên part**. Nó không tạo hai descriptor theo số file và cũng không tự kiểm tra giới hạn số lượng. Test/assertion riêng phải kiểm tra số tệp, file rỗng, kích thước và loại nội dung.

### 5.3. Chọn đúng descriptor

Trong test multipart, không dùng:

```java
formParameters(
    parameterWithName("title").description("Tiêu đề"),
    parameterWithName("attachments").description("Tệp đính kèm")
)
```

Hãy dùng:

```java
requestParts(
    partWithName("title").description("Tiêu đề dạng text"),
    partWithName("attachments").description("Tệp đính kèm")
)
```

Tên field giống nhau không làm cho hai loại snippet có thể thay thế nhau. Hợp đồng HTTP là multipart, nên bảng snippet cần mô tả đúng tên part.

## 6. Tài liệu hóa JSON part bằng requestPartFields(...)

`requestParts(...)` mô tả sự tồn tại và mục đích của từng part. Nếu một part có cấu trúc JSON, có thể mô tả sâu hơn bằng `requestPartFields("metadata", ...)`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

mockMvc.perform(multipart("/documents")
        .file(title)
        .file(metadata)
        .file(attachment))
    .andExpect(status().isCreated())
    .andDo(document("documents/create-multipart-with-metadata",
        requestParts(
            partWithName("title").description("Tiêu đề dạng text"),
            partWithName("metadata").description("Metadata JSON"),
            partWithName("attachments").description("Tệp đính kèm")
        ),
        requestPartFields("metadata",
            fieldWithPath("category").description("Danh mục tài liệu"),
            fieldWithPath("published").description("Trạng thái xuất bản")
        )
    ));
```

`requestPartFields` đọc payload của part được chỉ định rồi tạo snippet field riêng. Tên field trong descriptor là đường dẫn tương đối bên trong JSON metadata, không phải tên part.

| Cấp | Descriptor | Diễn giải |
| --- | --- | --- |
| Tên part | `partWithName("metadata")` | Có một part tên metadata |
| Field JSON trong part | `fieldWithPath("category")` | Metadata chứa field category |
| Field JSON khác | `fieldWithPath("published")` | Metadata chứa field published |

Nếu metadata JSON có object lồng nhau, dùng path như `owner.name` hoặc `labels[]`. Descriptor phải khớp payload thật trong part. Nếu part là file binary, không dùng `requestPartFields` cho nội dung tệp như thể nó là JSON object.

### 6.1. requestPartBody(...) cho payload raw

Khi muốn ghi lại body của part mà không mô tả từng field, có thể sử dụng snippet body của request part:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

mockMvc.perform(multipart("/documents")
        .file(title)
        .file(metadata)
        .file(attachment))
    .andDo(document("documents/metadata-body",
        requestParts(
            partWithName("metadata").description("Metadata JSON")
        ),
        requestPartBody("metadata")
    ));
```

Chọn cách phù hợp: `requestPartFields` cho hợp đồng JSON có schema rõ ràng; `requestPartBody` cho ví dụ body raw. Có thể kết hợp với `requestParts` để giải thích vai trò của part.

## 7. Phân biệt với JSON body cấp cao nhất

**Request JSON toàn body:**

```http
POST /documents HTTP/1.1
Content-Type: application/json

{"title":"Tài liệu","category":"lesson"}
```

Dùng `requestFields(...)`.

**Multipart có JSON part:**

```http
POST /documents HTTP/1.1
Content-Type: multipart/form-data; boundary=...

--boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"category":"lesson"}
--boundary--
```

Dùng `requestParts(...)` và `requestPartFields("metadata", ...)`.

**URL-encoded form:**

```http
POST /documents HTTP/1.1
Content-Type: application/x-www-form-urlencoded

title=T%C3%A0i+li%E1%BB%87u&category=lesson
```

Dùng `formParameters(...)`.

Không chọn `requestFields` chỉ vì multipart có một JSON part. `requestFields` nhắm vào JSON document là toàn bộ request payload; JSON part là payload lồng trong multipart và cần `requestPartFields`.

## 8. WebTestClient và REST Assured

### 8.1. WebTestClient

WebTestClient có thể tạo multipart bằng multipart inserter. Ví dụ khái quát cho WebFlux test:

```java
MultipartBodyBuilder builder = new MultipartBodyBuilder();
builder.part("title", "Tài liệu khóa học")
    .contentType(MediaType.TEXT_PLAIN);
builder.part("metadata", new DocumentMetadata("lesson", false))
    .contentType(MediaType.APPLICATION_JSON);
builder.part("attachments", new ByteArrayResource(
        "Nội dung tệp A".getBytes(StandardCharsets.UTF_8)))
    .filename("lesson-a.txt")
    .contentType(MediaType.TEXT_PLAIN);

webTestClient.post()
    .uri("/documents")
    .body(BodyInserters.fromMultipartData(builder.build()))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("documents/webtestclient-multipart",
        requestParts(
            partWithName("title").description("Tiêu đề tài liệu"),
            partWithName("metadata").description("Metadata JSON"),
            partWithName("attachments").description("Tệp đính kèm")
        )
    ));
```

Ví dụ giả định WebTestClient đã tích hợp Spring REST Docs và ứng dụng có handler WebFlux nhận multipart. Cách nhận multipart trong WebFlux khác Spring MVC: có thể dùng `@RequestPart`, `FilePart`, `Part` hoặc `ServerWebExchange` tùy hợp đồng và loại dữ liệu.

### 8.2. REST Assured

Với REST Assured, API multipart cho phép gửi từng part:

```java
given(specification)
    .filter(document("documents/rest-assured-multipart",
        requestParts(
            partWithName("title").description("Tiêu đề"),
            partWithName("metadata").description("Metadata JSON"),
            partWithName("attachments").description("Tệp đính kèm")
        )))
    .multiPart("title", "Tài liệu khóa học", "text/plain")
    .multiPart("metadata",
        "{\"category\":\"lesson\",\"published\":false}",
        "application/json")
    .multiPart("attachments", new File("src/test/resources/lesson-a.txt"))
    .when()
    .post("/documents")
    .then()
    .statusCode(201);
```

Đường dẫn tệp là fixture minh họa; dự án phải cung cấp file trong test resources. Khi gửi multipart, không tự đặt boundary thủ công. HTTP client phải đồng bộ boundary trong header với delimiter của body.

## 9. Tổ chức snippet và Asciidoctor

Nếu test sinh identifier `documents/create-multipart-with-metadata`, thư mục output có thể chứa:

```text
build/generated-snippets/
└── documents/
    └── create-multipart-with-metadata/
        ├── http-request.adoc
        ├── http-response.adoc
        ├── request-parts.adoc
        ├── request-part-metadata-fields.adoc
        └── ...
```

Tên snippet chính xác phụ thuộc operation đã cấu hình và phiên bản Spring REST Docs; hãy đọc output thật sau khi chạy test để viết include đúng. Mẫu Asciidoctor:

```adoc
= Documents API

== Tạo tài liệu multipart

=== HTTP request
include::{snippets}/documents/create-multipart-with-metadata/http-request.adoc[]

=== Request parts
include::{snippets}/documents/create-multipart-with-metadata/request-parts.adoc[]

=== Metadata fields
include::{snippets}/documents/create-multipart-with-metadata/request-part-metadata-fields.adoc[]

=== HTTP response
include::{snippets}/documents/create-multipart-with-metadata/http-response.adoc[]
```

Thuộc tính `snippets` phải trỏ đến thư mục gốc, ví dụ `build/generated-snippets`. Cú pháp `include::...[]` là Asciidoctor; Markdown renderer thông thường không tự hiểu cú pháp này. Nếu tài liệu chính dùng Markdown, liên kết đến HTML đã render hoặc dùng bước chuyển đổi được kiểm soát.

Với Gradle Groovy DSL, giả định plugin Asciidoctor đã được cài:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.absolutePath
}
```

CI chạy:

```bash
./gradlew test asciidoctor
```

Nếu descriptor part thay đổi, test document sẽ kiểm tra lại tên part và field. Khi test lỗi hoặc snippet không được sinh, build tài liệu cần thất bại thay vì giữ lại snippet cũ từ build trước.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng `formParameters` cho upload | Nhầm text part với URL-encoded parameter | Dùng `requestParts(partWithName(...))` |
| Dùng `requestFields` cho JSON part | Nhầm payload toàn request với payload lồng trong part | Dùng `requestPartFields("metadata", ...)` |
| Không thấy tên file trong bảng part | Descriptor chỉ có tên và mô tả part | Nhúng `http-request.adoc` để xem ví dụ request/filename/header |
| Multipart request trả 415 | Endpoint `consumes` không nhận multipart hoặc client sai media type | Dùng `multipart/form-data` và kiểm tra mapping |
| Server không đọc được JSON metadata | Part thiếu hoặc sai `Content-Type: application/json` | Gắn media type cho metadata part và kiểm tra converter |
| `requestPartFields` không tìm thấy field | JSON payload khác descriptor hoặc tên part sai | Đối chiếu payload JSON và tên part |
| File rỗng/quá lớn vẫn qua test | Chỉ document tên part, chưa xác minh quy tắc nghiệp vụ | Thêm assertion về kích thước, nội dung và giới hạn số file |
| Tự ghép boundary bằng tay | Header và delimiter trong body không đồng bộ | Để multipart builder/HTTP client tạo boundary |
| Asciidoctor không tìm thấy request-part snippet | Tên tệp include chưa khớp output thật | Kiểm tra thư mục generated-snippets sau test |

## 11. Bài tập thực hành

Xây dựng `POST /assignments` nhận multipart:

| Part | Nội dung | Quy tắc |
| --- | --- | --- |
| `title` | Text | Bắt buộc, không rỗng |
| `metadata` | JSON | Gồm `courseId`, `visibility` |
| `files` | File | Từ 1 đến 3 file, cùng tên part |

Thực hiện:

1. Tạo controller Spring MVC nhận text, JSON metadata và `List<MultipartFile>`.
2. Viết MockMvc test dùng `MockMultipartFile` cho cả ba loại part.
3. Dùng `requestParts(...)` để document các part; dùng `requestPartFields("metadata", ...)` cho JSON metadata.
4. Viết test thiếu `title`, metadata sai, không có file và vượt quá ba file. Xác minh status/response lỗi riêng.
5. Tạo một test tương đương dùng WebTestClient hoặc REST Assured.
6. Nhúng HTTP request, request-parts, metadata fields và response vào Asciidoctor; chạy test trước khi render trong CI.

**Tiêu chí đạt:** tài liệu mô tả đúng multipart body; mỗi text/file/JSON đều được nhận biết là part; JSON part có schema riêng; client có thể tạo request hợp lệ dựa trên tài liệu.

## Tài liệu tham khảo

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html)
- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring Framework — Multipart Forms](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework — MockMultipartHttpServletRequestBuilder API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/web/servlet/request/MockMultipartHttpServletRequestBuilder.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
