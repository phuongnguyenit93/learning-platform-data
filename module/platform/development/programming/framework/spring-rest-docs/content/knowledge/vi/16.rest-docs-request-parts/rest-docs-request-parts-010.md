# Tổ chức snippet multipart dễ đọc

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích cấu trúc multipart/form-data và vai trò của từng part trong request.
- Dùng Spring REST Docs mô tả danh sách part bằng requestParts(...) và partWithName(...).
- Mô tả cấu trúc JSON trong một part bằng requestPartFields(...), đồng thời biết khi nào nên ghi raw body của part.
- Thiết kế documentation test MockMvc cho upload file kèm metadata.
- Chia snippet theo trách nhiệm: tổng quan multipart, metadata fields, nội dung part và ví dụ HTTP request.
- Tổ chức document identifier và Asciidoctor include để trang tài liệu dễ đọc, dễ bảo trì.
- Tránh đưa file nhị phân, thông tin cá nhân hoặc dữ liệu nhạy cảm vào snippet phát hành.

## 1. Multipart request giải quyết bài toán gì?

Một API có thể cần nhận nhiều loại dữ liệu trong cùng một HTTP request. Ví dụ tạo hồ sơ người dùng có thể nhận một file ảnh đại diện, một part JSON chứa tên hiển thị và tùy chọn hồ sơ, cùng một part văn bản chứa ghi chú.

Định dạng multipart/form-data chia request body thành nhiều phần độc lập. Mỗi phần có header và nội dung riêng; ranh giới giữa các part được xác định bằng boundary trong Content-Type.

Ví dụ request đã giản lược:

```http
POST /api/profiles HTTP/1.1
Content-Type: multipart/form-data; boundary=----profile-boundary
Accept: application/json

------profile-boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"displayName":"Lan","visibility":"PUBLIC"}
------profile-boundary
Content-Disposition: form-data; name="avatar"; filename="avatar.png"
Content-Type: image/png

<binary image bytes>
------profile-boundary--
```

Trong ví dụ:

| Part | Content-Disposition | Content-Type | Nội dung |
| --- | --- | --- | --- |
| metadata | name="metadata" | application/json | JSON mô tả hồ sơ |
| avatar | name="avatar", filename="avatar.png" | image/png | Dữ liệu file nhị phân |

Multipart không đồng nghĩa với một file upload. Một request có thể gồm nhiều file, field văn bản và part có cấu trúc JSON/XML. Tài liệu cần cho biết tên part, kiểu nội dung, vai trò, tính bắt buộc và quy tắc validation của từng phần.

## 2. Vì sao cần tổ chức snippet riêng cho từng part?

Nếu chỉ đưa toàn bộ request multipart vào một ví dụ dài, người đọc khó nhận ra những part nào là bắt buộc, part nào chứa file, JSON field nằm trong part nào, file hỗ trợ định dạng và dung lượng ra sao, hoặc một part tùy chọn có thể bỏ qua hay không.

Spring REST Docs cung cấp các descriptor và snippet riêng:

| API | Mục đích |
| --- | --- |
| requestParts(...) | Mô tả những part có trong request |
| partWithName(...) | Khai báo descriptor cho một part theo tên |
| requestPartFields(...) | Mô tả các field của part có cấu trúc, thường là JSON |
| relaxedRequestPartFields(...) | Mô tả một phần field khi có chủ đích không kiểm tra toàn bộ payload part |
| requestPartBody(...) | Ghi lại body của một part cụ thể khi cần minh họa nội dung thô |

Các snippet có trách nhiệm khác nhau. Bảng request parts trả lời request gồm những phần nào; bảng part fields trả lời JSON metadata có field gì; snippet body giúp minh họa nội dung cụ thể khi bảng field chưa đủ.

Không cần đưa raw binary file vào tài liệu. Với file upload, tên part, filename mẫu, media type và mô tả quy tắc file thường hữu ích hơn nội dung bytes.

## 3. Mô tả tổng quan các part bằng requestParts

Giả sử endpoint tạo hồ sơ nhận part metadata và avatar. Có thể khai báo:

```java
requestParts(
    partWithName("metadata")
        .description("Metadata JSON của hồ sơ"),
    partWithName("avatar")
        .description("Ảnh đại diện của hồ sơ; định dạng PNG hoặc JPEG")
)
```

Mỗi descriptor đại diện cho tên part. Nội dung description nên giải thích vai trò và ràng buộc mà consumer cần biết:

- Part có chứa JSON hay file?
- Media type nào được hỗ trợ?
- Part có bắt buộc không?
- Có giới hạn kích thước hoặc số lượng không?
- Khi part bị thiếu hoặc sai định dạng, API phản hồi thế nào?

Không dựa vào tên part để suy đoán media type. Hãy kiểm tra Content-Type của part thực tế và ghi rõ contract.

### 3.1. Part tùy chọn

Nếu avatar có thể vắng mặt, descriptor có thể đánh dấu optional:

```java
requestParts(
    partWithName("metadata")
        .description("Metadata JSON của hồ sơ"),
    partWithName("avatar")
        .description("Ảnh đại diện tùy chọn; PNG hoặc JPEG")
        .optional()
)
```

optional() mô tả khả năng part vắng mặt trong request được tài liệu hóa. Nó không tự cấu hình controller để chấp nhận thiếu file, không bỏ qua validation và không tạo file mặc định. Cần có test riêng gửi request chỉ gồm metadata và xác minh hành vi của server.

### 3.2. Strict và relaxed behavior

requestParts(...) mô tả các part được gửi trong exchange. Khi dùng strict documentation, các part thực tế cần được mô tả đầy đủ; part mới xuất hiện có thể khiến test không tạo snippet như mong đợi. Đây là tín hiệu hữu ích khi contract multipart thay đổi.

Đừng chuyển mọi test sang relaxed chỉ để tránh cập nhật tài liệu. Nếu API thêm part signature, nhóm cần quyết định consumer có phải gửi part đó hay không và cập nhật descriptor.

## 4. Mô tả field JSON nằm trong một part

Metadata thường là JSON riêng trong multipart. Ví dụ:

```json
{
  "displayName": "Lan",
  "visibility": "PUBLIC",
  "notifyByEmail": true
}
```

Dùng requestPartFields(...) để mô tả các field thuộc part metadata:

```java
requestPartFields("metadata",
    fieldWithPath("displayName")
        .description("Tên hiển thị của hồ sơ"),
    fieldWithPath("visibility")
        .description("Phạm vi hiển thị: PUBLIC hoặc PRIVATE"),
    fieldWithPath("notifyByEmail")
        .description("Có gửi thông báo qua email hay không")
)
```

Tên part truyền vào requestPartFields là metadata; các field path bên trong được tính từ JSON body của part đó, không có tiền tố metadata.

Ví dụ, nếu JSON part có cấu trúc:

```json
{
  "address": {
    "city": "Da Nang",
    "countryCode": "VN"
  }
}
```

Descriptor path là address.city và address.countryCode, không phải metadata.address.city.

### 4.1. Field tùy chọn trong metadata

Nếu notifyByEmail có thể vắng mặt:

```java
requestPartFields("metadata",
    fieldWithPath("displayName")
        .description("Tên hiển thị"),
    fieldWithPath("visibility")
        .description("Phạm vi hiển thị")
        .optional(),
    fieldWithPath("notifyByEmail")
        .description("Có gửi thông báo email hay không")
        .optional()
)
```

Field optional và part optional là hai cấp khác nhau:

| Cấp | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Part optional | avatar | Toàn bộ part có thể không xuất hiện |
| Field optional | notifyByEmail trong metadata | Part metadata vẫn có, nhưng field này có thể vắng mặt |

Đừng đánh dấu toàn bộ part optional chỉ vì một field bên trong JSON là optional. Cũng không dùng optional() để thay thế việc kiểm tra null, chuỗi rỗng hoặc giá trị mặc định.

## 5. Ví dụ đầy đủ bằng MockMvc

Giả sử API POST /api/profiles nhận metadata là part JSON bắt buộc và avatar là part file PNG/JPEG tùy chọn.

Ví dụ test:

```java
@Test
void createsProfileWithAvatar() throws Exception {
    MockMultipartFile metadata = new MockMultipartFile(
            "metadata",
            "",
            MediaType.APPLICATION_JSON_VALUE,
            """
            {
              "displayName": "Lan",
              "visibility": "PUBLIC",
              "notifyByEmail": true
            }
            """.getBytes(StandardCharsets.UTF_8)
    );

    MockMultipartFile avatar = new MockMultipartFile(
            "avatar",
            "avatar.png",
            MediaType.IMAGE_PNG_VALUE,
            validPngBytes()
    );

    mockMvc.perform(multipart("/api/profiles")
                    .file(metadata)
                    .file(avatar)
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isCreated())
            .andDo(document("profiles-create",
                    requestParts(
                            partWithName("metadata")
                                    .description("Metadata JSON của hồ sơ"),
                            partWithName("avatar")
                                    .description("Ảnh đại diện PNG hoặc JPEG")
                                    .optional()
                    ),
                    requestPartFields("metadata",
                            fieldWithPath("displayName")
                                    .description("Tên hiển thị"),
                            fieldWithPath("visibility")
                                    .description("Phạm vi hiển thị"),
                            fieldWithPath("notifyByEmail")
                                    .description("Có gửi thông báo email hay không")
                    )
            ));
}
```

Đây là ví dụ cấu trúc; controller, service, response assertions và static imports cần được khai báo theo dự án. validPngBytes() là fixture helper trả về nội dung PNG hợp lệ; không dùng một mảng bytes tùy ý nếu ứng dụng kiểm tra decode ảnh hoặc chữ ký file.

Các import thường cần:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

Ngoài ra cần MockMvc, MockMultipartFile, MediaType, StandardCharsets, Test và các kiểu response/assertion của ứng dụng.

## 6. Tổ chức document identifier và snippet output

Tên trong document(...) quyết định thư mục chứa snippet của exchange:

```java
document("profiles-create", ...)
```

Thư mục output thường có dạng:

```text
build/generated-snippets/
└── profiles-create/
    ├── curl-request.adoc
    ├── http-request.adoc
    ├── request-parts.adoc
    └── ...
```

Các snippet bổ sung do requestPartFields(...) tạo ra được đặt trong cùng operation output theo quy tắc tên snippet của phiên bản REST Docs và cấu hình dự án. Hãy đọc thư mục generated-snippets sau khi test chạy để xác định đúng tên file trước khi viết include; đừng đoán tên output từ tên method Java.

### 6.1. Một document identifier cho một kịch bản

Nên dùng identifier biểu đạt endpoint và hành vi:

| Identifier | Kịch bản |
| --- | --- |
| profiles-create | Tạo hồ sơ có metadata và avatar |
| profiles-create-without-avatar | Tạo hồ sơ chỉ có metadata |
| profiles-create-invalid-metadata | Metadata JSON sai hoặc thiếu field |
| profiles-create-unsupported-avatar | File có media type không hỗ trợ |

Identifier ổn định giúp người đọc và maintainer tìm đúng snippet. Tránh dùng tên quá chung như upload, test1 hoặc tên phụ thuộc thứ tự chạy.

### 6.2. Không ghi raw binary thành snippet văn bản

Không nên dùng raw body snippet để đưa nội dung nhị phân lớn vào tài liệu. Với file ảnh/PDF, tài liệu nên mô tả tên part, tên file mẫu hoặc phần mở rộng, Content-Type hỗ trợ, giới hạn kích thước và quy tắc kiểm tra nội dung.

Nếu cần minh họa một part văn bản nhỏ, requestPartBody(...) có thể tạo snippet body cho part đó. Chỉ dùng raw part body khi nội dung dễ đọc, có ích và không chứa dữ liệu nhạy cảm. Với JSON metadata, requestPartFields(...) thường tạo tài liệu có cấu trúc tốt hơn.

## 7. Khi nào dùng requestPartBody?

Một số part không phải JSON object nhưng vẫn có body dạng văn bản, ví dụ XML, CSV, manifest hoặc đoạn text mô tả nội dung cần upload.

Khi cần hiển thị nội dung raw của part, có thể dùng:

```java
document("imports-create",
    requestParts(
        partWithName("manifest")
            .description("Manifest CSV mô tả dữ liệu nhập")
    ),
    requestPartBody("manifest")
)
```

Ví dụ này phù hợp nếu manifest là văn bản ngắn. Nếu part là file nhị phân hoặc nội dung dài, hãy tránh đưa toàn bộ body vào snippet; chỉ mô tả metadata của part hoặc cung cấp một ví dụ rút gọn đã được làm sạch ở phần prose.

## 8. Tổ chức Asciidoctor để người đọc đi theo đúng thứ tự

Một trang multipart dễ đọc nên trình bày từ tổng quan đến chi tiết:

1. Mô tả endpoint và mục đích upload.
2. Hiển thị danh sách part.
3. Mô tả JSON metadata fields.
4. Mô tả file part: media type, kích thước và giới hạn.
5. Hiển thị HTTP request mẫu và response.

Ví dụ AsciiDoc:

```asciidoc
== Tạo hồ sơ

Endpoint nhận metadata JSON và ảnh đại diện tùy chọn.

=== Request parts
include::{snippets}/profiles-create/request-parts.adoc[]

=== Metadata fields
include::{snippets}/profiles-create/metadata-fields.adoc[]

=== HTTP request
include::{snippets}/profiles-create/http-request.adoc[]

=== HTTP response
include::{snippets}/profiles-create/http-response.adoc[]
```

Đường dẫn metadata-fields.adoc ở trên là tên minh họa. Tên snippet chính xác do REST Docs version và cách đặt snippet name quyết định; hãy đối chiếu output thật trước khi include. Nếu output tên khác, dùng đúng tên thực tế.

Không cần include mọi snippet được sinh ra. Chỉ đưa vào trang những snippet hỗ trợ người đọc hiểu contract. Tài liệu có thể chia thành các đoạn riêng để tránh một trang dài với nhiều bảng lặp.

## 9. Multipart part validation cần được tài liệu hóa

REST Docs mô tả request đã được test; nó không tự áp dụng validation cho file hoặc metadata. Ứng dụng cần kiểm tra riêng:

| Hạng mục | Ví dụ quy tắc | Test nên có |
| --- | --- | --- |
| Part bắt buộc | metadata phải tồn tại | Request thiếu metadata |
| Part tùy chọn | avatar có thể vắng mặt | Request chỉ có metadata |
| Media type | avatar chỉ nhận image/png hoặc image/jpeg | Upload text/plain hoặc application/octet-stream |
| File size | Tối đa 5 MB | File nhỏ hơn, bằng và vượt giới hạn |
| Filename | Không sử dụng đường dẫn client gửi làm path lưu trữ | Filename chứa ../ hoặc đường dẫn tuyệt đối |
| Nội dung file | Kiểm tra chữ ký/nội dung thay vì chỉ tin Content-Type | File giả MIME hoặc file hỏng |
| Metadata fields | displayName bắt buộc, visibility thuộc enum | Thiếu field, enum không hợp lệ |
| Số lượng file | Tối đa một avatar | Gửi nhiều part avatar nếu endpoint không hỗ trợ |

Không ghi một giới hạn như 5 MB nếu implementation chưa thực thi hoặc test chưa xác nhận. Mô tả cần phản ánh contract đã thống nhất.

### 9.1. Test thiếu part bắt buộc

Ví dụ:

```java
@Test
void rejectsMissingMetadataPart() throws Exception {
    mockMvc.perform(multipart("/api/profiles")
                    .file(new MockMultipartFile(
                            "avatar",
                            "avatar.png",
                            MediaType.IMAGE_PNG_VALUE,
                            validPngBytes()
                    )))
            .andExpect(status().isBadRequest());
}
```

Status và error body cần theo API thực tế. Nếu tài liệu cần công bố lỗi thiếu part, dùng document identifier riêng và thêm descriptor cho response lỗi.

### 9.2. Test part tùy chọn vắng mặt

```java
@Test
void createsProfileWithoutAvatar() throws Exception {
    MockMultipartFile metadata = new MockMultipartFile(
            "metadata",
            "",
            MediaType.APPLICATION_JSON_VALUE,
            """
            {"displayName":"Lan","visibility":"PUBLIC"}
            """.getBytes(StandardCharsets.UTF_8)
    );

    mockMvc.perform(multipart("/api/profiles")
                    .file(metadata)
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isCreated())
            .andDo(document("profiles-create-without-avatar",
                    requestParts(
                            partWithName("metadata")
                                    .description("Metadata JSON của hồ sơ"),
                            partWithName("avatar")
                                    .description("Ảnh đại diện tùy chọn")
                                    .optional()
                    )
            ));
}
```

Test này chứng minh kịch bản không có avatar nếu controller thực sự chấp nhận request. Descriptor optional không thể thay assertion status hoặc kiểm tra response.

## 10. Giữ snippet dễ bảo trì khi multipart thay đổi

Khi API phát triển, part có thể được thêm, bỏ hoặc đổi media type. Một số nguyên tắc giúp trang tài liệu ổn định:

- Dùng tên part có ngữ nghĩa, tránh tên ngắn khó hiểu như p1, data2.
- Giữ document identifier gắn với hành vi, không phụ thuộc tên test method.
- Đặt descriptor part ở một vị trí tập trung trong test để tránh lặp mô tả không nhất quán.
- Tạo test riêng cho biến thể quan trọng: thiếu file, file lỗi, metadata invalid.
- Dùng strict descriptors cho phần contract cần kiểm soát đầy đủ.
- Chỉ dùng relaxedRequestPartFields(...) khi snippet cố ý mô tả một phần metadata và phần còn lại được giải thích ở nơi khác.
- Đọc output mới sau mỗi lần đổi REST Docs version hoặc đổi cách đặt snippet.

Nếu một part JSON có nhiều cấp, có thể dùng field path lồng nhau hoặc subsection descriptor để chia bề mặt tài liệu. Không nên đưa cả JSON lớn vào một đoạn prose và bỏ qua bảng field khi consumer cần tra cứu từng trường.

## 11. Bảo vệ dữ liệu trong multipart snippet

Multipart thường chứa thông tin người dùng hoặc file riêng tư. Dùng dữ liệu tổng hợp dành riêng cho test:

- Không upload ảnh giấy tờ, ảnh người dùng hoặc tài liệu thật.
- Không dùng filename chứa tên, email hoặc định danh cá nhân.
- Xóa EXIF/geolocation khỏi fixture hình ảnh nếu không cần kiểm tra metadata đó.
- Không ghi nội dung PDF/CSV có dữ liệu thật vào requestPartBody.
- Không đưa token hoặc cookie vào request header khi tạo snippet.
- Che các field nhạy cảm trong metadata bằng preprocessors nếu chúng xuất hiện trong body snippet.

Ví dụ metadata test:

```json
{
  "displayName": "Example User",
  "contactEmail": "user@example.test",
  "visibility": "PUBLIC"
}
```

Đây là dữ liệu ví dụ. Nếu email, số điện thoại hoặc thông tin nhạy cảm xuất hiện trong payload, hãy dùng fixture giả và xác minh snippet không còn dữ liệu thật.

## 12. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không thấy part trong request-parts snippet | Part name trong descriptor khác tên multipart thực tế | So sánh tên trong MockMultipartFile và partWithName |
| requestPartFields không tìm thấy field | JSON part không đúng cấu trúc hoặc path dùng sai | Đọc body part sau serialize; path tính từ root của part |
| Strict requestParts thất bại khi thêm part mới | Part mới chưa được mô tả | Xác nhận contract rồi bổ sung descriptor |
| Optional part vẫn làm endpoint lỗi | Ứng dụng thực tế chưa hỗ trợ vắng part | Sửa implementation hoặc mô tả đúng yêu cầu |
| Snippet metadata lẫn với file part | Dùng chung raw body mà không chia theo part | Dùng requestPartFields cho JSON và requestParts cho tổng quan |
| Raw file bytes xuất hiện trong artifact | Ghi part nhị phân dưới dạng raw snippet | Không sinh body snippet cho file nhị phân; chỉ mô tả metadata |
| Asciidoctor include không tìm thấy file | Đoán tên snippet thay vì đọc output thực tế | Kiểm tra thư mục generated-snippets rồi sửa include |
| Test chỉ xanh với file giả không hợp lệ | Ứng dụng chưa kiểm tra nội dung file hoặc fixture không đại diện | Dùng fixture hợp lệ và test cả MIME/content/size |

## 13. Checklist tổ chức snippet multipart

- [ ] Đặt tên rõ ràng cho từng part.
- [ ] Dùng requestParts(...) để mô tả danh sách part.
- [ ] Dùng requestPartFields(...) cho JSON part có cấu trúc.
- [ ] Chỉ dùng requestPartBody(...) với nội dung văn bản ngắn, có ích.
- [ ] Đánh dấu optional đúng cấp: part hoặc field.
- [ ] Có test cho part thiếu, part tùy chọn và file không hợp lệ.
- [ ] Mô tả media type, filename, kích thước và quy tắc nội dung.
- [ ] Dùng document identifier ổn định theo kịch bản.
- [ ] Đọc snippet thực tế trước khi viết Asciidoctor include.
- [ ] Không ghi file nhị phân hoặc dữ liệu cá nhân vào artifact.
- [ ] Render tài liệu và kiểm tra mọi include trong CI.

## 14. Bài tập thực hành

Endpoint POST /api/documents nhận:

- metadata: JSON gồm title, category và tags.
- document: file PDF bắt buộc.
- thumbnail: file ảnh tùy chọn.

Hãy thực hiện:

1. Viết test MockMvc dùng ba MockMultipartFile đại diện.
2. Dùng requestParts(...) mô tả metadata, document và thumbnail; đánh dấu thumbnail optional.
3. Dùng requestPartFields("metadata", ...) mô tả title, category và tags.
4. Mô tả giới hạn MIME type và kích thước của PDF/thumbnail bằng prose được đối chiếu với validation thật.
5. Tạo test thiếu document, thumbnail vắng mặt, PDF sai media type và metadata thiếu title.
6. Sinh snippet, kiểm tra output name thực tế rồi include vào Asciidoctor theo thứ tự tổng quan → metadata → file rules → HTTP exchange.
7. Quét artifact để bảo đảm không có filename hoặc nội dung tài liệu thật.

**Câu hỏi tự kiểm tra:** Có nên dùng requestPartBody("document") để ghi toàn bộ bytes của PDF vào tài liệu không? Không. Binary bytes không giúp consumer hiểu hợp đồng và có thể làm artifact rất lớn hoặc chứa dữ liệu nhạy cảm. Hãy mô tả tên part, media type, filename mẫu, giới hạn và validation; chỉ dùng raw body snippet cho part văn bản ngắn khi thực sự có ích.

## Kết luận

Một multipart snippet dễ đọc cần tách rõ danh sách part, cấu trúc metadata và nội dung file. Spring REST Docs cung cấp requestParts(...) để mô tả các part, requestPartFields(...) để mô tả field JSON bên trong một part và requestPartBody(...) cho raw body khi phù hợp. Tổ chức document identifier theo kịch bản, đọc output thực tế trước khi include và sắp xếp trang từ tổng quan đến chi tiết. HTTP test phải chứng minh part bắt buộc/tùy chọn, media type, kích thước và validation; file nhị phân cùng dữ liệu cá nhân cần được thay bằng fixture giả. Khi làm đúng các bước này, tài liệu multipart vừa phản ánh request đã kiểm thử vừa đủ rõ cho client triển khai upload.
