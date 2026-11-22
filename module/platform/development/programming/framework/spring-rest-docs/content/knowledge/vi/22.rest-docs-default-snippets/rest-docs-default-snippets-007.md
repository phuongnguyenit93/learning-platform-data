# request-parts, request-part-name và request-part-body

## Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, nhiều API nhận dữ liệu multipart/form-data, chẳng hạn tải ảnh kèm metadata JSON hoặc gửi nhiều tệp trong một request. Một request multipart được chia thành các **part** độc lập; mỗi part có tên, header/content type và body riêng. Tài liệu cần cho biết client phải gửi những part nào, mỗi part chứa dữ liệu gì và cấu trúc body ra sao.

Spring REST Docs hỗ trợ ba mức mô tả:

- **request-parts**: danh sách các part của request và ý nghĩa của từng part.
- **request-part-body**: nội dung body thô của một part có tên cụ thể.
- **request-part-fields**: các field bên trong body có cấu trúc (ví dụ JSON) của một part có tên cụ thể.

Sau bài này, bạn có thể:

- Phân biệt multipart request với request body JSON thông thường.
- Dùng requestParts và partWithName để mô tả danh sách part.
- Dùng requestPartBody để sinh snippet body cho một part.
- Dùng requestPartFields để mô tả field của JSON part.
- Hiểu cách tên part được đưa vào tên snippet đầu ra.
- Mô tả file upload và metadata theo đúng content type.
- Chọn chế độ strict/relaxed, optional và ignored phù hợp.
- Dùng MockMvc hoặc WebTestClient để sinh snippet multipart có thể kiểm chứng.

## 1. Multipart request gồm những gì?

Một HTTP request có content type multipart/form-data được chia thành nhiều phần. Mỗi phần thường có:

| Thành phần | Ý nghĩa |
| --- | --- |
| Part name | Tên định danh part, ví dụ image hoặc metadata |
| Headers | Header riêng của part, thường có Content-Disposition và Content-Type |
| Filename | Tên file nếu part đại diện cho file upload |
| Content type | Kiểu dữ liệu của body part, ví dụ image/png hoặc application/json |
| Body | Nội dung của part: bytes của file, JSON, text hoặc dữ liệu khác |

Ví dụ upload ảnh kèm metadata:

```text
POST /images
Content-Type: multipart/form-data; boundary=...

--boundary
Content-Disposition: form-data; name="image"; filename="image.png"
Content-Type: image/png

<binary image bytes>
--boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Profile photo","version":"1.0"}
--boundary--
```

Hai part có vai trò khác nhau:

- image chứa nội dung file nhị phân.
- metadata chứa JSON mô tả file.

Tài liệu API nên mô tả tên hai part, mục đích, kiểu nội dung và cấu trúc metadata. Nếu chỉ ghi endpoint nhận multipart/form-data, người dùng API vẫn chưa biết cần gửi part nào và định dạng từng part ra sao.

## 2. Ba mức snippet và tên file được sinh

Spring REST Docs cung cấp các snippet sau:

| API tạo snippet | Nội dung | Tên snippet |
| --- | --- | --- |
| requestParts(...) | Danh sách part, tên và mô tả | request-parts.adoc |
| requestPartBody("metadata") | Body của part tên metadata | request-part-metadata-body.adoc |
| requestPartFields("metadata", ...) | Các field của part tên metadata | request-part-metadata-fields.adoc |

Tên cụ thể được tạo theo part name. Chẳng hạn:

- Part tên image: requestPartBody("image") tạo request-part-image-body.adoc.
- Part tên metadata: requestPartBody("metadata") tạo request-part-metadata-body.adoc.
- Part tên metadata: requestPartFields("metadata", ...) tạo request-part-metadata-fields.adoc.

**Lưu ý về cách gọi tên:** không có một file đầu ra chung tên request-part-name.adoc hoặc request-part-body.adoc. Phần tên part được thay vào tên snippet. Với part metadata, file thực tế có dạng request-part-metadata-body.adoc hoặc request-part-metadata-fields.adoc.

Ba mức mô tả có thể dùng độc lập hoặc kết hợp. Ví dụ, request-parts liệt kê image và metadata; request-part-body cho biết body metadata được gửi ra sao; request-part-fields giải thích ý nghĩa từng field JSON bên trong metadata.

## 3. request-parts: mô tả danh sách part

### 3.1. Dùng requestParts và partWithName

Giả sử endpoint upload nhận một file có tên part là file:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

this.mockMvc.perform(multipart("/upload")
        .file("file", "example".getBytes()))
    .andExpect(status().isOk())
    .andDo(document("upload",
        requestParts(
            partWithName("file")
                .description("Tệp cần tải lên.")
        )));
```

requestParts yêu cầu REST Docs tạo snippet mô tả các part. partWithName("file") chọn part có tên file; description giải thích mục đích của part đối với client.

Snippet request-parts.adoc thường có bảng tên part và mô tả. Nó giúp người đọc biết request cần chứa thành phần nào.

### 3.2. Mô tả nhiều part

Với upload ảnh kèm metadata:

```java
this.mockMvc.perform(multipart("/images")
        .file(image)
        .file(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("image-upload",
        requestParts(
            partWithName("image")
                .description("Tệp ảnh cần tải lên."),
            partWithName("metadata")
                .description("Thông tin mô tả ảnh dưới dạng JSON.")
        )));
```

Mỗi part có một tên riêng. Tên trong descriptor phải khớp chính xác với tên part mà client gửi. Ví dụ tên metadata khác với meta-data; REST Docs không tự suy ra hoặc chuẩn hóa tên.

### 3.3. Hành vi strict của requestParts

Ở chế độ mặc định, requestParts kiểm tra sự tương ứng giữa descriptor và request thực tế:

- Part xuất hiện trong request nhưng chưa được mô tả có thể làm test thất bại.
- Part đã mô tả nhưng không xuất hiện trong request cũng làm test thất bại, trừ khi descriptor được đánh dấu optional.
- Part được đánh dấu ignored không xuất hiện trong bảng snippet nhưng vẫn được xử lý khi kiểm tra request.

Nhờ đó, nếu API thêm part mới, bài test tài liệu có thể yêu cầu người viết cập nhật mô tả.

### 3.4. Part tùy chọn và ignored

Một part có thể không bắt buộc:

```java
requestParts(
    partWithName("image")
        .description("Tệp ảnh chính."),
    partWithName("thumbnail")
        .optional()
        .description("Ảnh thu nhỏ; có thể không gửi.")
)
```

Nếu part không cần xuất hiện trong bảng tài liệu nhưng vẫn có trong request test, có thể dùng ignored():

```java
requestParts(
    partWithName("image")
        .description("Tệp ảnh chính."),
    partWithName("clientTrace")
        .ignored()
)
```

optional và ignored có ý nghĩa khác nhau:

- optional cho phép part đã mô tả không xuất hiện trong request.
- ignored xử lý part có trong request mà không đưa nó vào bảng mô tả.

Không dùng optional để che đi part bắt buộc mà endpoint thực sự cần.

### 3.5. Chế độ relaxedRequestParts

Khi muốn chỉ tập trung mô tả một số part của một request lớn, có thể dùng relaxedRequestParts:

```java
relaxedRequestParts(
    partWithName("image")
        .description("Tệp ảnh cần tải lên.")
)
```

Chế độ relaxed cho phép các part khác chưa liệt kê xuất hiện mà không làm test thất bại. Đây là lựa chọn phù hợp khi tài liệu chỉ mô tả một kịch bản con hoặc một nhóm part quan trọng.

Không nên dùng relaxedRequestParts cho mọi endpoint. Nếu tài liệu cần phản ánh đầy đủ hợp đồng multipart, requestParts mặc định giúp phát hiện part mới hoặc part bị thiếu rõ ràng hơn.

## 4. request-part-body: mô tả body của một part

### 4.1. Khi nào dùng requestPartBody?

requestPartBody(partName) tạo snippet chứa body của part có tên đã chọn. Nó hữu ích khi cần hiển thị nội dung của:

- JSON part.
- XML part.
- Text part.
- Body của một part có cấu trúc mà muốn lưu dưới dạng snippet riêng.

Với file nhị phân lớn như ảnh hoặc PDF, snippet body có thể không phải cách trình bày tốt cho người đọc. Nên mô tả loại file, content type, giới hạn kích thước và điều kiện upload trong request-parts hoặc phần giải thích; chỉ tạo body snippet khi representation có ý nghĩa và an toàn để đưa vào tài liệu.

### 4.2. Ví dụ MockMvc

Tạo hai MockMultipartFile:

```java
MockMultipartFile image = new MockMultipartFile(
        "image",
        "image.png",
        "image/png",
        imageBytes
);

MockMultipartFile metadata = new MockMultipartFile(
        "metadata",
        "",
        "application/json",
        """
        {
          "title": "Profile photo",
          "version": "1.0"
        }
        """.getBytes(StandardCharsets.UTF_8)
);
```

Sinh snippet body cho part metadata:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

this.mockMvc.perform(multipart("/images")
        .file(image)
        .file(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("image-upload",
        requestPartBody("metadata")
    ));
```

Snippet được tạo:

```text
build/generated-snippets/
└── image-upload/
    └── request-part-metadata-body.adoc
```

Snippet chứa body đã được REST Docs trích xuất từ part metadata. Tên snippet dựa trên part name truyền vào requestPartBody.

### 4.3. Body snippet không thay thế request-parts

requestPartBody chỉ mô tả nội dung body của part được chọn. Nó không thay thế bảng liệt kê tất cả part và ý nghĩa của chúng. Trong tài liệu hoàn chỉnh, thường có:

```asciidoc
== Multipart request
include::{snippets}/image-upload/request-parts.adoc[]

== Metadata body
include::{snippets}/image-upload/request-part-metadata-body.adoc[]
```

request-parts trả lời câu hỏi “request gồm những part nào?”. request-part-metadata-body cho biết “body của metadata chứa gì?”.

### 4.4. Lưu ý với binary body

Không nên mặc định body file nhị phân có thể biểu diễn thành văn bản. Với image/png, application/pdf hoặc định dạng nhị phân khác:

- Không đưa bytes thô vào tài liệu nếu chúng không đọc được.
- Dùng dữ liệu giả/nhỏ trong test.
- Ưu tiên mô tả filename, content type và quy tắc kích thước.
- Không sử dụng file chứa thông tin cá nhân hoặc bí mật làm fixture.
- Nếu template hoặc snippet không thể hiển thị body theo cách có ích, chỉ tài liệu hóa part metadata và mô tả file bằng văn bản.

## 5. request-part-fields: mô tả các field bên trong part

requestPartFields phù hợp khi một part chứa payload có cấu trúc, ví dụ JSON metadata:

```json
{
  "title": "Profile photo",
  "version": "1.0",
  "visibility": "PRIVATE"
}
```

Khai báo field descriptor:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

this.mockMvc.perform(multipart("/images")
        .file(image)
        .file(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("image-upload",
        requestPartFields("metadata",
            fieldWithPath("title")
                .description("Tiêu đề của ảnh."),
            fieldWithPath("version")
                .description("Phiên bản metadata."),
            fieldWithPath("visibility")
                .description("Phạm vi hiển thị của ảnh.")
        )));
```

Snippet sinh ra:

```text
build/generated-snippets/
└── image-upload/
    └── request-part-metadata-fields.adoc
```

requestPartFields mô tả field của body part tên metadata; nó không mô tả field của toàn bộ multipart request.

### 5.1. Kiểm tra field trong part

requestPartFields mặc định áp dụng kiểm tra payload chặt chẽ giống requestFields:

- Field thực tế trong JSON part nhưng không có descriptor làm test thất bại.
- Descriptor trỏ tới field không có trong body part làm test thất bại, trừ khi optional.
- Có thể dùng ignored để xử lý field nhưng không hiển thị nó trong snippet.
- Field path có cấu trúc nested vẫn cần được mô tả bằng đường dẫn phù hợp.

Ví dụ một JSON part có field mới checksum nhưng descriptor chưa cập nhật; test có thể phát hiện sự khác nhau. Đây là cơ chế giúp tài liệu part metadata đồng bộ với payload thực tế.

### 5.2. Part fields relaxed

Nếu chỉ mô tả một phần body của part, có thể dùng relaxedRequestPartFields:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedRequestPartFields;

relaxedRequestPartFields("metadata",
    fieldWithPath("title")
        .description("Tiêu đề ảnh.")
)
```

Chế độ relaxed cho phép field khác chưa được liệt kê. Dùng khi có chủ ý chỉ mô tả một phần JSON part; nếu cần tài liệu đầy đủ, ưu tiên requestPartFields mặc định.

## 6. Kết hợp ba loại snippet trong cùng một operation

Một bài test upload ảnh có thể tạo cả ba mức mô tả:

```java
this.mockMvc.perform(multipart("/images")
        .file(image)
        .file(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("image-upload",
        requestParts(
            partWithName("image")
                .description("Tệp ảnh PNG cần tải lên."),
            partWithName("metadata")
                .description("Metadata JSON của ảnh.")
        ),
        requestPartBody("metadata"),
        requestPartFields("metadata",
            fieldWithPath("title")
                .description("Tiêu đề ảnh."),
            fieldWithPath("version")
                .description("Phiên bản metadata.")
        )
    ));
```

Các snippet được tạo trong cùng thư mục operation:

```text
build/generated-snippets/
└── image-upload/
    ├── request-parts.adoc
    ├── request-part-metadata-body.adoc
    └── request-part-metadata-fields.adoc
```

Trong AsciiDoc:

```asciidoc
== Upload image

=== Request parts
include::{snippets}/image-upload/request-parts.adoc[]

=== Metadata body
include::{snippets}/image-upload/request-part-metadata-body.adoc[]

=== Metadata fields
include::{snippets}/image-upload/request-part-metadata-fields.adoc[]
```

Không nhất thiết phải tạo cả body snippet và fields snippet cho mọi part. Nếu JSON metadata chỉ cần bảng field, requestPartFields có thể đủ. Nếu cần đưa toàn bộ body mẫu vào tài liệu, thêm requestPartBody. Với file nhị phân, thường chỉ cần request-parts và mô tả bằng văn bản.

## 7. Content-Type và cách chọn snippet

Mỗi part có thể có content type riêng. Chọn cách mô tả theo loại payload:

| Content-Type của part | Ví dụ | Cách mô tả gợi ý |
| --- | --- | --- |
| application/json | Metadata object | requestPartBody và/hoặc requestPartFields |
| text/plain | Ghi chú dạng text | requestPartBody |
| application/xml | XML metadata | requestPartBody; field documentation cần cách xử lý XML phù hợp |
| image/png, image/jpeg | File ảnh | request-parts và mô tả filename/content type; cân nhắc tránh body snippet |
| application/pdf | File PDF | request-parts và mô tả file; thường không include bytes thô |
| application/octet-stream | Dữ liệu nhị phân | Mô tả part và quy tắc truyền dữ liệu |

REST Docs trích xuất body của part theo tên. Hãy bảo đảm tên part đúng và request test thực sự gửi content type/body đại diện. Nếu part JSON bị gửi dưới dạng text/plain hoặc không có content type phù hợp, cách server parse và snippet hiển thị có thể khác kỳ vọng.

## 8. Ví dụ WebTestClient

WebTestClient cũng hỗ trợ tạo multipart request bằng MultiValueMap và BodyInserters:

```java
MultiValueMap<String, Object> multipartData = new LinkedMultiValueMap<>();
multipartData.add("image", imageResource);
multipartData.add("metadata", Map.of(
        "title", "Profile photo",
        "version", "1.0"
));

this.webTestClient.post()
    .uri("/images")
    .body(BodyInserters.fromMultipartData(multipartData))
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("image-upload",
        requestParts(
            partWithName("image")
                .description("Tệp ảnh cần tải lên."),
            partWithName("metadata")
                .description("Metadata JSON của ảnh.")
        ),
        requestPartBody("metadata")
    ));
```

Với Resource upload, có thể override getFilename() để đặt filename cho part:

```java
Resource imageResource = new ByteArrayResource(imageBytes) {
    @Override
    public String getFilename() {
        return "image.png";
    }
};
```

API WebTestClient và cách serialize multipart phụ thuộc phiên bản Spring WebFlux/client. Hãy xác minh request thực tế có Content-Disposition, filename và Content-Type như mong đợi.

## 9. Tên part phải ổn định giữa controller, test và tài liệu

Tên part là một phần của hợp đồng API. Ví dụ controller nhận:

```java
@PostMapping(
        path = "/images",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> upload(
        @RequestPart("image") MultipartFile image,
        @RequestPart("metadata") CreateImageMetadata metadata) {
    // Xử lý upload
    return ResponseEntity.accepted().build();
}
```

Tên trong test:

```java
multipart("/images")
    .file(image)
    .file(metadata)
```

và tên trong REST Docs descriptor phải thống nhất:

```java
requestParts(
    partWithName("image").description("Tệp ảnh."),
    partWithName("metadata").description("Metadata JSON.")
)
```

Nếu controller đổi @RequestPart("metadata") thành @RequestPart("details"), nhưng test vẫn gửi metadata, test có thể thất bại ở bước binding. Nếu test cũng đổi nhưng descriptor không đổi, REST Docs sẽ báo part không khớp. Hãy cập nhật đồng bộ controller, test, descriptor và include path của AsciiDoc.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| request-parts báo part chưa được mô tả | Request có part mới chưa có part descriptor | Thêm partWithName hoặc dùng relaxedRequestParts có chủ ý |
| Descriptor báo không tìm thấy part | Sai tên part hoặc request test không gửi part | Đối chiếu @RequestPart, tên multipart và descriptor |
| request-part-metadata-body.adoc không được tạo | Chưa gọi requestPartBody("metadata") hoặc part không tồn tại | Thêm snippet đúng operation và xác minh multipart request |
| request-part-metadata-fields.adoc không được tạo | Chưa gọi requestPartFields hoặc gọi sai part name | Kiểm tra PayloadDocumentation và tên part |
| Field trong JSON part chưa được tài liệu hóa | requestPartFields strict và descriptor thiếu field | Bổ sung descriptor, ignored hoặc relaxed khi phù hợp |
| Body snippet không đọc được | Part là binary hoặc encoding/content type không phù hợp | Không include binary thô; mô tả file bằng văn bản |
| Metadata được parse thành text thay vì JSON | Content-Type của part thiếu hoặc sai | Gán application/json cho metadata part |
| Filename trống/không đúng | Resource hoặc MockMultipartFile thiếu filename | Khai báo filename đúng trong test |
| Test pass nhưng tài liệu không có part body | Chỉ dùng requestParts mà chưa thêm requestPartBody | Thêm snippet body cho part cần minh họa |
| Tên snippet include không khớp | Nhầm tên mẫu với tên đầu ra có part-name | Dùng đúng request-part-<part-name>-body.adoc hoặc fields.adoc |
| Dùng relaxed che giấu schema change | Các part/field mới không làm test thất bại | Ưu tiên strict nếu muốn kiểm chứng hợp đồng đầy đủ |

## 11. Bài thực hành

1. Tạo endpoint POST /images nhận part image và metadata.
2. Tạo MockMultipartFile cho image với filename image.png và content type image/png.
3. Tạo MockMultipartFile metadata với content type application/json và body gồm title, version.
4. Dùng requestParts để mô tả hai part; kiểm tra request-parts.adoc.
5. Dùng requestPartBody("metadata"); kiểm tra request-part-metadata-body.adoc.
6. Dùng requestPartFields("metadata", ...) để mô tả title và version; kiểm tra request-part-metadata-fields.adoc.
7. Thêm một field mới vào metadata nhưng chưa cập nhật descriptor; quan sát strict requestPartFields làm test thất bại.
8. Thử relaxedRequestPartFields và giải thích trade-off.
9. (Nâng cao) Dùng WebTestClient gửi cùng multipart request và so sánh snippet.

**Câu hỏi tự đánh giá**

1. requestParts mô tả thông tin gì của multipart request?
2. partWithName dùng để xác định phần nào?
3. requestPartBody("metadata") tạo snippet tên gì?
4. requestPartFields khác requestPartBody như thế nào?
5. Vì sao một part JSON nên có Content-Type application/json?
6. optional và ignored khác nhau ra sao đối với part?
7. Khi nào relaxedRequestParts hoặc relaxedRequestPartFields phù hợp?
8. Vì sao không nên include bytes của file ảnh/PDF vào body snippet?

## Tài liệu tham khảo chính thức

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): requestParts, requestPartBody, requestPartFields và tên snippet được sinh.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field descriptors, optional, ignored và relaxed payload documentation.
- [RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html): requestParts, relaxedRequestParts và partWithName.
- [PayloadDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html): requestPartBody, requestPartFields và relaxedRequestPartFields.
- [Spring Framework — Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html): xử lý multipart request trong Spring MVC.

**Kết luận thực hành:** Dùng requestParts để liệt kê và giải thích từng part; dùng requestPartBody khi cần hiển thị nội dung body của một part; dùng requestPartFields khi body part có cấu trúc và cần mô tả từng field. Tên snippet body/fields luôn chứa tên part cụ thể, vì vậy hãy đồng bộ tên trong controller, test, descriptor và file AsciiDoc include. Chạy test với request multipart thực tế để tài liệu phản ánh đúng cấu trúc mà API chấp nhận.
