# Thêm extra information vào snippet

## 1. Vì sao cần bổ sung metadata cho snippet?

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Sau khi test gửi request và xác nhận response, REST Docs sinh snippet về request, response, payload, tham số, header và hypermedia links. Snippet được biên soạn thành Asciidoctor/Markdown rồi đưa vào build, CI.

Descriptor mặc định chứa thông tin kỹ thuật như field path, kiểu dữ liệu và mô tả. Tài liệu thực tế có thể cần thêm ngữ cảnh: tiêu đề cho bảng, phiên bản hợp đồng API, ghi chú quyền truy cập, ràng buộc validation của từng field hoặc lời dẫn cho lệnh curl.

Spring REST Docs cho phép truyền **attributes** để bổ sung thông tin cho snippet và descriptor. Template có thể đọc attributes rồi trình bày theo quy chuẩn dự án. Nội dung được khai báo cùng test nên có thể review và version-control với ví dụ HTTP.

## 2. Ba phạm vi thông tin cần phân biệt

| Phạm vi | Gắn vào đâu | Ví dụ |
| --- | --- | --- |
| Cấp snippet | Attributes truyền cho snippet | Tiêu đề chung, phiên bản API, ghi chú cho cả bảng |
| Cấp descriptor | Attributes của field, parameter, header hoặc link descriptor | Constraints, giá trị ví dụ, đơn vị đo |
| Cấp template | Placeholder và section trong Mustache | Cách hiển thị title, version, note và giá trị descriptor |

Ví dụ: bảng request fields có title “Tạo người dùng” ở cấp snippet; field email có constraint “Phải đúng định dạng email” ở cấp descriptor; template quyết định title nằm trên bảng và constraint nằm trong cột cuối.

Attributes không sửa request/response, không tạo thêm field và không thay đổi hành vi endpoint. Đây là metadata do test cung cấp để template trình bày. Nếu giá trị không được khai báo hoặc template không đọc đúng key, thông tin sẽ không xuất hiện như mong muốn.

## 3. Tạo attributes bằng Attributes.key(...)

Spring REST Docs cung cấp helper tạo attribute:

~~~java
import static org.springframework.restdocs.snippet.Attributes.key;

key("title").value("Các trường khi tạo người dùng")
~~~

key("title") tạo attribute có tên title; value(...) cung cấp giá trị. Có thể truyền nhiều attributes trong cùng một lời gọi:

~~~java
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

attributes(
        key("title").value("Tạo người dùng"),
        key("api-version").value("v1"),
        key("note").value("Email phải là duy nhất"))
~~~

Các key nên có tên rõ nghĩa và nhất quán. Với key nhiều từ, có thể dùng kebab-case như api-version, sample-value hoặc security-note. Tránh dùng key trùng với biến nội bộ trong template cho một ý nghĩa khác.

## 4. Thêm extra information ở cấp snippet

Một snippet có thể nhận metadata áp dụng cho toàn bộ nội dung được render. Ví dụ với requestFields(...), truyền attributes trước danh sách field descriptors:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

requestFields(
        attributes(
                key("title").value("Các trường khi tạo người dùng"),
                key("api-version").value("v1"),
                key("note").value("Email phải là duy nhất")),
        fieldWithPath("name").description("Tên người dùng"),
        fieldWithPath("email").description("Địa chỉ email"))
~~~

title, api-version và note áp dụng cho bảng request fields này. Chúng không tự động truyền sang curl-request, http-request hoặc operation khác. Muốn snippet khác hiển thị cùng thông tin, truyền attributes cho đúng snippet đó.

Ví dụ với curl request:

~~~java
curlRequest(
        attributes(
                key("title").value("Ví dụ gọi API tạo người dùng"),
                key("api-version").value("v1")))
~~~

Snippet mặc định chỉ hiển thị metadata nếu template của snippet đó đọc những key tương ứng. Truyền attributes và override template là hai bước liên quan nhưng riêng biệt.

## 5. Thêm extra information ở cấp field descriptor

Một bảng thường cần metadata riêng cho từng field, chẳng hạn constraint hoặc ví dụ dữ liệu. Gắn attribute trực tiếp vào descriptor:

~~~java
requestFields(
        fieldWithPath("name")
                .description("Tên người dùng")
                .attributes(key("constraints")
                        .value("Không được để trống; tối đa 80 ký tự")),
        fieldWithPath("email")
                .description("Địa chỉ email")
                .attributes(
                        key("constraints").value("Phải đúng định dạng email"),
                        key("example").value("an@example.test")))
~~~

Field name có metadata constraints; field email có cả constraints và example. Template có thể đọc từng key trong từng phần tử fields.

| Key | Ý nghĩa gợi ý | Ví dụ |
| --- | --- | --- |
| constraints | Ràng buộc validation | Không được để trống |
| example | Giá trị minh họa | an@example.test |
| unit | Đơn vị đo | VND |
| format | Quy tắc định dạng | ISO-8601 |
| since | Phiên bản bắt đầu hỗ trợ | v2 |
| sensitivity | Phân loại thông tin | Không ghi log giá trị thật |

Đây là key do dự án quy ước, không phải tất cả đều là thuộc tính chuẩn mà REST Docs tự hiểu. Template phải được viết để đọc các key đã chọn.

## 6. Hiển thị attributes bằng Mustache template

Giả sử muốn thêm title, API version và note ở cấp snippet, đồng thời thêm cột Constraints và Example ở cấp field. Tạo template tùy chỉnh tại:

~~~text
src/test/resources/
└── org/springframework/restdocs/templates/
    └── asciidoctor/
        └── request-fields.snippet
~~~

Nội dung Mustache minh họa:

~~~mustache
{{#title}}
.{{title}}
{{/title}}
{{#api-version}}
Phiên bản API: {{api-version}}
{{/api-version}}
{{#note}}
NOTE: {{note}}
{{/note}}

|===
|Path|Type|Description|Constraints|Example
{{#fields}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}
|{{example}}
{{/fields}}
|===
~~~

Các section title và note chỉ hiển thị khi attributes có giá trị. Section fields lặp qua từng field descriptor. Placeholder constraints và example đọc attributes của field tương ứng. Tên placeholder phải khớp chính xác tên key đã truyền.

## 7. Ví dụ đầy đủ: test truyền metadata và tạo snippet

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void createUserDocumentsExtraInformation() throws Exception {
    mockMvc.perform(post("/api/users")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "name": "An",
                              "email": "an@example.test"
                            }
                            """))
            .andExpect(status().isCreated())
            .andDo(document("create-user",
                    requestFields(
                            attributes(
                                    key("title").value("Các trường khi tạo người dùng"),
                                    key("api-version").value("v1"),
                                    key("note").value("Email phải là duy nhất")),
                            fieldWithPath("name")
                                    .description("Tên người dùng")
                                    .attributes(key("constraints")
                                            .value("Không được để trống")),
                            fieldWithPath("email")
                                    .description("Địa chỉ email")
                                    .attributes(
                                            key("constraints")
                                                    .value("Phải đúng định dạng email"),
                                            key("example")
                                                    .value("an@example.test")))));
}
~~~

Output minh họa:

| Path | Type | Description | Constraints | Example |
| --- | --- | --- | --- | --- |
| name | String | Tên người dùng | Không được để trống | |
| email | String | Địa chỉ email | Phải đúng định dạng email | an@example.test |

Kiểu field do Spring REST Docs suy ra từ payload được mô tả. Constraints và example do test truyền vào. Template có thể dùng lại cho endpoint khác; mỗi operation cung cấp metadata của chính nó.

## 8. Dùng extra information với snippet khác

Snippet-level attributes không chỉ dành cho request fields. Các factory/constructor snippet có hỗ trợ attributes có thể nhận metadata theo cùng nguyên tắc. Chẳng hạn, một curl request có thể cần tiêu đề và đối tượng người đọc:

~~~java
curlRequest(
        attributes(
                key("title").value("Gọi endpoint bằng curl"),
                key("audience").value("Người tích hợp API")))
~~~

Template curl tùy chỉnh có thể hiển thị metadata:

~~~mustache
{{#title}}
.{{title}}
{{/title}}
{{#audience}}
Dành cho: {{audience}}
{{/audience}}
{{{curlRequest}}}
~~~

Placeholder chứa nội dung curl phụ thuộc model template của format và phiên bản. Khi tùy chỉnh snippet có sẵn, bắt đầu từ template mặc định đúng phiên bản rồi giữ lại các placeholder gốc. Ví dụ trên minh họa cách đưa metadata vào template, không thay thế việc kiểm tra model thực tế.

## 9. Quy ước metadata để tránh tài liệu không nhất quán

| Quy ước | Lợi ích |
| --- | --- |
| Dùng key chung cho cùng ý nghĩa | Template có thể tái sử dụng |
| Tên key ngắn, rõ ràng | Hạn chế lỗi đánh máy |
| Có hướng dẫn cho key tùy chọn | Người viết biết lúc nào cần truyền |
| Không khai báo hai giá trị mâu thuẫn | Tránh metadata tự phủ định |
| Dùng giá trị ví dụ giả | Tránh lộ dữ liệu thật |
| Đặt metadata nghiệp vụ trong test/descriptor | Dễ review thay đổi hợp đồng |

Có thể quy ước bộ key dùng chung như title, api-version, note, constraints, example và since. Không cần gắn tất cả key vào mọi snippet; chỉ truyền thông tin có ích cho người đọc loại snippet đó.

### Attribute thiếu hoặc rỗng

Template nên xử lý trường hợp attribute không được truyền. Dùng Mustache section để ẩn dòng khi không có giá trị:

~~~mustache
{{#note}}
NOTE: {{note}}
{{/note}}
~~~

Nếu mọi field đều bắt buộc có constraints, nhóm có thể áp dụng quy ước review hoặc helper tạo descriptor để giảm việc quên metadata. Không điền chuỗi chung như N/A cho mọi field nếu giá trị đó không cung cấp thông tin.

## 10. Attributes không tự động lấy từ Bean Validation

Một hiểu nhầm phổ biến là Spring REST Docs tự đọc annotation như NotBlank, Email, Size rồi tạo nội dung cột constraints. Việc dùng attributes không tự động thực hiện bước đó.

Nếu muốn metadata khớp với validation rules, có thể:

1. Truyền nội dung constraint rõ ràng trong descriptor của test.
2. Tạo helper dùng chung để ánh xạ quy tắc đã định nghĩa sang attributes.
3. Xây snippet/template tùy chỉnh đọc metadata mà dự án đã cung cấp.

Ví dụ khai báo minh bạch trong test:

~~~java
fieldWithPath("email")
        .description("Địa chỉ email")
        .attributes(key("constraints")
                .value("@NotBlank, @Email"))
~~~

Đây là nội dung tài liệu do người viết cung cấp; nó không chứng minh controller thực sự kích hoạt validation. Test vẫn cần gửi payload không hợp lệ và xác nhận response lỗi nếu muốn kiểm chứng quy tắc đó.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Attribute không xuất hiện | Template chưa đọc key đó | Thêm placeholder Mustache phù hợp |
| Placeholder rỗng | Key trong template khác key đã truyền | Đối chiếu tên key chính xác |
| Title xuất hiện trên mọi bảng | Gắn title ở sai cấp hoặc template không kiểm tra section | Đặt snippet-level attributes và dùng conditional section |
| Constraints không đúng field | Gắn attribute vào descriptor khác | Kiểm tra từng field descriptor |
| Metadata không có ở curl snippet | Attribute chỉ được truyền cho requestFields | Truyền attribute cho snippet cần hiển thị và override đúng template |
| Validation metadata lỗi thời | Constraint viết tay không cập nhật cùng code | Review metadata cùng thay đổi validation và bổ sung test |
| Ký tự đặc biệt làm hỏng bảng | Nội dung chưa escape theo format đích | Xử lý ký tự đặc biệt trong template hoặc dữ liệu |
| Thông tin nhạy cảm lọt vào tài liệu | Dùng giá trị thật làm example hoặc note | Thay bằng dữ liệu giả và rà soát artifact |

## 12. Bài thực hành

1. Thêm title, api-version và note cho snippet request-fields.
2. Gắn constraints và example cho từng field khác nhau.
3. Tạo Mustache template có conditional sections để ẩn metadata không được truyền.
4. Tạo template cho curl request và hiển thị tiêu đề riêng.
5. Bỏ một attribute khỏi test, chạy lại và xác nhận template xử lý trường hợp thiếu.
6. Thêm validation cho email, rồi kiểm tra riêng metadata trong snippet và response lỗi khi gửi email không hợp lệ.
7. Xem diff snippet sau khi thay đổi metadata để xác nhận nội dung phản ánh đúng test.

**Tiêu chí hoàn thành:** phân biệt snippet-level và descriptor-level attributes; truyền dữ liệu bằng Attributes.key(...).value(...); hiển thị metadata trong Mustache; xử lý giá trị thiếu; không nhầm metadata tài liệu với kiểm chứng hành vi API.

## 13. Checklist trước khi commit

- [ ] Mỗi attribute có mục đích và phạm vi rõ ràng.
- [ ] Snippet-level attributes được truyền cho đúng snippet.
- [ ] Descriptor-level attributes được gắn vào đúng field/parameter/header/link.
- [ ] Tên key khớp với placeholder Mustache.
- [ ] Template xử lý attribute tùy chọn và không tạo dòng trống khó hiểu.
- [ ] Constraints công bố khớp validation contract hiện tại.
- [ ] Ví dụ dùng giá trị giả, không chứa bí mật hoặc dữ liệu cá nhân.
- [ ] Output snippet đã được tạo lại từ test và đọc kiểm tra.
- [ ] Asciidoctor/Markdown build thành công với template mới.

**Ghi nhớ:** Extra information được truyền qua attributes ở cấp snippet hoặc descriptor, rồi hiển thị bởi template. Tổ chức metadata rõ ràng giúp snippet giàu ngữ cảnh mà vẫn giữ request/response và assertions từ test làm nguồn kiểm chứng cho tài liệu REST API.
