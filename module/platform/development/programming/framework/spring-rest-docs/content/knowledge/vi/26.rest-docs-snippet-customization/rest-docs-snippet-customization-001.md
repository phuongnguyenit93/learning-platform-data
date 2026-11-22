# Customizing generated snippets

## 1. Vì sao cần tùy chỉnh snippet?

**Spring REST Docs** tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test thực hiện request, xác nhận response, rồi Spring REST Docs sinh snippet về request, response, payload, tham số, header và hypermedia links. Các snippet được biên soạn thành Asciidoctor/Markdown và đưa vào build, CI.

Snippet mặc định tạo một cấu trúc nhất quán, nhưng mỗi dự án có thể cần cách trình bày riêng:

- Thêm cột **Constraints** vào bảng request/response fields để thể hiện quy tắc validation.
- Thêm tiêu đề hoặc lời giải thích cho từng bảng.
- Đổi định dạng snippet từ Asciidoctor sang Markdown.
- Điều chỉnh cách hiển thị HTTP request, response hoặc curl command theo quy chuẩn tài liệu.
- Bổ sung snippet mặc định cho mọi operation mà không lặp lời gọi trong từng test.

Spring REST Docs cho phép tùy chỉnh bằng template Mustache và các thuộc tính bổ sung. Dữ liệu vẫn đến từ operation đã kiểm thử; template quyết định cách dữ liệu đó được trình bày.

## 2. Cách Spring REST Docs tạo snippet

Spring REST Docs sử dụng **Mustache templates** để dựng nội dung snippet. Mỗi loại snippet có template tương ứng: request-fields, curl-request, links, http-request, response-fields, v.v.

~~~text
MockMvc / WebTestClient / REST Assured
                 |
                 v
          HTTP operation
                 |
                 v
       Snippet descriptor + attributes
                 |
                 v
          Mustache template
                 |
                 v
      Generated snippet file
                 |
                 v
       Asciidoctor / Markdown build
~~~

Có thể tùy chỉnh ở ba vị trí:

| Vị trí | Điều chỉnh | Ví dụ |
| --- | --- | --- |
| Template | Cấu trúc, tiêu đề, bảng và cách trình bày | Thêm cột Constraints vào request-fields |
| Descriptor attributes | Metadata của từng field hoặc descriptor | constraints, example, format |
| Snippet-level attributes | Metadata chung của một snippet | Tiêu đề Fields for user creation |

Kết hợp các phần này giúp template dùng lại được cho nhiều operation mà mỗi operation vẫn cung cấp dữ liệu mô tả riêng.

## 3. Vị trí đặt template tùy chỉnh

Template được nạp từ classpath trong package org.springframework.restdocs.templates cộng với tên định dạng template đang dùng. Định dạng mặc định là Asciidoctor, có ID asciidoctor, vì vậy template Asciidoctor nằm dưới:

~~~text
src/test/resources/
└── org/
    └── springframework/
        └── restdocs/
            └── templates/
                └── asciidoctor/
                    └── request-fields.snippet
~~~

Tên file template tương ứng với tên snippet. Ví dụ muốn thay template cho snippet curl-request.adoc, tạo file curl-request.snippet trong thư mục template Asciidoctor trên. Với request-fields, tên template là request-fields.snippet.

Quy tắc cần nhớ:

- Giữ đúng package classpath org/springframework/restdocs/templates.
- Thư mục con phải khớp ID định dạng template.
- Tên file phải khớp tên snippet muốn thay thế.
- Dùng phần mở rộng .snippet cho template nguồn Mustache.
- Đặt template trong test resources nếu nó chỉ phục vụ việc sinh tài liệu từ test.

Template tùy chỉnh cùng tên sẽ được dùng để tạo snippet tương ứng. Các snippet khác tiếp tục dùng template mặc định nếu bạn không cung cấp bản override.

## 4. Đổi định dạng snippet: Asciidoctor hoặc Markdown

Spring REST Docs mặc định tạo snippet theo định dạng Asciidoctor. Markdown cũng được hỗ trợ. Với MockMvc, cấu hình định dạng thông qua RestDocumentationConfigurer:

~~~java
import org.springframework.restdocs.templates.TemplateFormats;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;

@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
            .apply(documentationConfiguration(restDocumentation)
                    .snippets()
                    .withTemplateFormat(TemplateFormats.markdown()))
            .build();
}
~~~

Nếu muốn giữ định dạng mặc định Asciidoctor, có thể cấu hình tường minh:

~~~java
.snippets()
.withTemplateFormat(TemplateFormats.asciidoctor())
~~~

Với WebTestClient:

~~~java
this.webTestClient = WebTestClient.bindToApplicationContext(this.context)
        .configureClient()
        .filter(documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.markdown()))
        .build();
~~~

Định dạng được chọn ảnh hưởng đến template được tìm trên classpath và phần mở rộng của file snippet. Khi override template cho Markdown, dùng thư mục có ID markdown:

~~~text
src/test/resources/org/springframework/restdocs/templates/markdown/request-fields.snippet
~~~

Đổi template format không tự chuyển tài liệu thủ công từ AsciiDoc sang Markdown. Bước biên soạn cuối cùng phải đọc đúng loại snippet được sinh ra. Nếu dự án dùng Asciidoctor include, tiếp tục dùng snippet AsciiDoc; nếu dùng Markdown, cập nhật cơ chế nhúng snippet tương ứng.

## 5. Thêm thông tin vào snippet bằng attributes

Spring REST Docs cung cấp hai nơi để truyền thông tin bổ sung cho template:

1. Gắn attribute vào descriptor bằng attributes(...).
2. Truyền attribute ở cấp snippet khi gọi requestFields(...), curlRequest(...), httpRequest(...), httpResponse(...) và các snippet tương ứng.

Các attribute này được đưa vào quá trình render template. Template Mustache có thể đọc chúng và hiển thị nội dung bổ sung.

### 5.1. Attribute ở cấp field

Ví dụ mỗi request field có một ràng buộc:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.snippet.Attributes.key;

requestFields(
        fieldWithPath("name")
                .description("Tên người dùng")
                .attributes(key("constraints").value("Không được để trống")),
        fieldWithPath("email")
                .description("Địa chỉ email")
                .attributes(key("constraints")
                        .value("Phải có định dạng email hợp lệ")))
~~~

constraints là metadata tự đặt. Spring REST Docs không tự suy luận nội dung validation từ annotation Bean Validation để điền vào attribute này; test author phải truyền giá trị muốn công bố.

### 5.2. Attribute ở cấp snippet

Có thể thêm tiêu đề chung cho bảng request fields:

~~~java
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

requestFields(
        attributes(key("title").value("Các trường khi tạo người dùng")),
        fieldWithPath("name")
                .description("Tên người dùng")
                .attributes(key("constraints").value("Không được để trống")),
        fieldWithPath("email")
                .description("Địa chỉ email")
                .attributes(key("constraints")
                        .value("Phải có định dạng email hợp lệ")))
~~~

title áp dụng cho snippet như một khối; constraints áp dụng cho từng field. Hai cấp attribute có phạm vi khác nhau nên không dùng chung một tên cho những ý nghĩa không liên quan.

## 6. Override template request-fields để thêm cột Constraints

Đây là ví dụ thực tế. Mục tiêu là tạo bảng có bốn cột: Path, Type, Description và Constraints.

### 6.1. Đặt template

Tạo file:

~~~text
src/test/resources/org/springframework/restdocs/templates/asciidoctor/request-fields.snippet
~~~

Nội dung Mustache:

~~~mustache
.{{title}}
|===
|Path|Type|Description|Constraints

{{#fields}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}

{{/fields}}
|===
~~~

Template sử dụng:

- {{title}}: tiêu đề snippet.
- {{#fields}} ... {{/fields}}: lặp qua danh sách field descriptors.
- {{path}}, {{type}}, {{description}}: dữ liệu có sẵn của mỗi field.
- {{constraints}}: attribute bổ sung do test cung cấp.

### 6.2. Truyền attributes trong test

~~~java
@Test
void createUser() throws Exception {
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
                            attributes(key("title")
                                    .value("Các trường khi tạo người dùng")),
                            fieldWithPath("name")
                                    .description("Tên người dùng")
                                    .attributes(key("constraints")
                                            .value("Không được để trống")),
                            fieldWithPath("email")
                                    .description("Địa chỉ email")
                                    .attributes(key("constraints")
                                            .value("Phải có định dạng email hợp lệ")))));
}
~~~

Kết quả minh họa:

| Path | Type | Description | Constraints |
| --- | --- | --- | --- |
| name | String | Tên người dùng | Không được để trống |
| email | String | Địa chỉ email | Phải có định dạng email hợp lệ |

Kiểu field do Spring REST Docs suy ra từ payload được mô tả. Nội dung constraints do test truyền vào. Template có thể dùng lại cho endpoint khác; mỗi operation cung cấp title và constraints tương ứng.

## 7. Tùy chỉnh các snippet khác

Nguyên tắc override template áp dụng cho nhiều loại snippet:

| Snippet | Nội dung |
| --- | --- |
| curl-request | Lệnh curl gọi API |
| http-request | HTTP request |
| http-response | HTTP response |
| httpie-request | Lệnh HTTPie |
| request-body | Request body |
| response-body | Response body |
| request-fields | Bảng request fields |
| response-fields | Bảng response fields |
| path-parameters | Path parameters |
| query-parameters | Query parameters |
| request-headers | Request headers |
| response-headers | Response headers |
| links | Hypermedia links |

Ví dụ, để thay cách trình bày curl request, tạo:

~~~text
src/test/resources/org/springframework/restdocs/templates/asciidoctor/curl-request.snippet
~~~

Template này được dùng thay template mặc định khi format đang dùng là Asciidoctor và operation tạo snippet curl-request. Model attribute có sẵn phụ thuộc loại snippet. Khi override, nên bắt đầu từ template mặc định tương ứng của đúng phiên bản Spring REST Docs rồi chỉnh sửa phần cần thiết. Cách này tránh bỏ sót biến hoặc cấu trúc Mustache mà template mặc định sử dụng.

Tương tự, có thể tạo links.snippet để thay cách trình bày bảng hypermedia links hoặc response-fields.snippet để bổ sung cột mô tả response.

Không nên override mọi template chỉ vì có thể. Mỗi bản override khiến dự án sở hữu thêm một phần định dạng đầu ra và cần được xem xét khi nâng phiên bản Spring REST Docs.

## 8. Giữ default snippets và bổ sung snippet mặc định

SnippetConfigurer cho phép cấu hình các snippet được tạo mặc định cho mỗi operation:

- withDefaults(...): đặt danh sách default snippets cần tạo.
- withAdditionalDefaults(...): bổ sung snippet mặc định vào danh sách hiện có.

Nếu chỉ muốn thêm một snippet mặc định, ưu tiên withAdditionalDefaults(...):

~~~java
this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
        .apply(documentationConfiguration(restDocumentation)
                .snippets()
                .withAdditionalDefaults(new CustomDefaultSnippet()))
        .build();
~~~

CustomDefaultSnippet là lớp snippet do dự án định nghĩa và cần triển khai theo API Spring REST Docs. Nếu dùng withDefaults(...), bạn đang chủ động thay danh sách mặc định; cần cung cấp lại những snippet vẫn muốn sinh như request, response hoặc curl. Dùng nhầm withDefaults(...) có thể làm mất các file snippet mà trang tài liệu hiện đang include.

| Nhu cầu | API |
| --- | --- |
| Chỉ muốn thêm snippet vào bộ mặc định | withAdditionalDefaults(...) |
| Muốn định nghĩa chính xác bộ snippet được tạo | withDefaults(...) |

## 9. Tạo snippet riêng cho dự án

Khi snippet mặc định không thể diễn đạt thông tin cần thiết, có thể tạo snippet riêng và gắn vào operation. Spring REST Docs cung cấp abstraction Snippet để mở rộng.

Ở mức khái niệm, snippet tùy chỉnh cần:

1. Nhận operation đã được thực thi.
2. Tạo model dữ liệu từ request/response hoặc operation attributes.
3. Render template tương ứng bằng template engine.
4. Ghi file vào output directory của operation.

Skeleton mô tả trách nhiệm:

~~~java
public final class ApiSummarySnippet implements Snippet {

    @Override
    public void document(Operation operation) throws IOException {
        // Đọc dữ liệu từ operation.
        // Tạo model cho template.
        // Render template và ghi snippet vào output directory.
    }
}
~~~

Đây là skeleton, chưa phải lớp có thể biên dịch nguyên trạng: phần render cần được triển khai bằng TemplateEngine/template resource resolver tương ứng với phiên bản Spring REST Docs. Với nhu cầu chỉ đổi cách hiển thị snippet có sẵn, override Mustache template thường đơn giản và dễ bảo trì hơn.

Một operation có thể dùng snippet tùy chỉnh:

~~~java
mockMvc.perform(get("/api/users/{id}", 5))
        .andExpect(status().isOk())
        .andDo(document("users-get",
                new ApiSummarySnippet()));
~~~

Lớp custom snippet có thể được thêm vào danh sách default bằng withAdditionalDefaults(...) nếu muốn chạy cho mọi operation thuộc cấu hình MockMvc.

## 10. Những lưu ý về bảo trì template

Tùy chỉnh snippet là mã nguồn của quy trình tài liệu hóa. Cần quản lý nó như một phần của dự án:

- **Đồng bộ phiên bản:** khi nâng Spring REST Docs, kiểm tra template mặc định và model mà Mustache nhận được có thay đổi không.
- **Giữ đủ dữ liệu:** template override phải giữ các cột/placeholder cần thiết để không vô tình bỏ thông tin request hoặc field.
- **Escape nội dung:** dữ liệu từ payload có thể chứa ký tự đặc biệt; dùng cách render/escape phù hợp với cú pháp đích để tránh tạo AsciiDoc/Markdown sai.
- **Tránh ràng buộc không cần thiết:** không nhúng tên môi trường, URL nội bộ hoặc dữ liệu nhạy cảm vào template dùng chung.
- **Tái sử dụng:** đặt quy tắc chung ở template; dữ liệu từng endpoint ở descriptor attributes.
- **Kiểm tra output:** so sánh snippet mới với output mong muốn sau khi test chạy.

Nếu template không được tìm thấy, kiểm tra package path, template format ID, tên snippet và test resources có nằm trong classpath test hay không. Nếu attribute không xuất hiện trong output, kiểm tra tên khóa Mustache có trùng chính xác tên khóa trong attributes(...) không.

## 11. Tích hợp vào build và CI

~~~text
Run documentation tests
          |
          v
Render snippets using project templates
          |
          v
Verify generated-snippets output
          |
          v
Asciidoctor / Markdown build
          |
          v
Publish documentation artifact
~~~

Trong CI, nên:

1. Chạy clean và documentation tests để sinh snippet từ test hiện tại.
2. Biên soạn tài liệu sau khi test hoàn tất.
3. Để build thất bại nếu template không render được hoặc file include bị thiếu.
4. Lưu template tùy chỉnh trong version control cùng test sử dụng chúng.
5. Khi nâng Spring REST Docs, chạy lại bộ test và kiểm tra diff của snippet.

Một thay đổi template có thể làm nhiều file snippet thay đổi cùng lúc. Hãy xem xét diff để xác nhận thay đổi chỉ liên quan trình bày, không làm mất thông tin hoặc thay đổi nội dung được kiểm chứng.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Template tùy chỉnh không được áp dụng | Sai package path hoặc format ID | Đặt trong org/springframework/restdocs/templates/{format-id} trên test classpath. |
| Override nhầm snippet | Tên template không khớp tên snippet | Dùng đúng tên, ví dụ request-fields.snippet. |
| Attribute không hiện trong snippet | Tên key trong Mustache khác key truyền từ descriptor | Đối chiếu key constraints với placeholder constraints. |
| Cột constraints trống | Field descriptor chưa gắn attribute | Bổ sung attributes(key("constraints").value(...)) cho field đó. |
| Template Markdown không được nạp | Vẫn dùng format Asciidoctor hoặc đặt file sai thư mục | Cấu hình TemplateFormats.markdown() và dùng folder markdown. |
| Các snippet mặc định biến mất | Dùng withDefaults(...) và thay toàn bộ danh sách | Dùng withAdditionalDefaults(...) nếu mục tiêu chỉ là bổ sung. |
| Template lỗi sau khi nâng phiên bản | Model hoặc template mặc định thay đổi | So sánh template mặc định phiên bản mới và cập nhật bản override. |
| Tài liệu không build sau thay đổi template | Nội dung tạo ra không hợp lệ với Asciidoctor/Markdown | Mở snippet sinh ra, sửa template rồi chạy lại test và document build. |

## 13. Bài thực hành

1. Tạo template request-fields.snippet trong thư mục Asciidoctor và thêm cột Constraints.
2. Truyền title ở cấp snippet, constraints ở cấp từng field; chạy test và kiểm tra bảng output.
3. Tạo template tương ứng trong thư mục markdown, cấu hình TemplateFormats.markdown() và so sánh output.
4. Override curl-request.snippet để thêm tiêu đề hoặc lời giải thích theo quy chuẩn của nhóm.
5. Dùng withAdditionalDefaults(...) để thêm một snippet mặc định; xác nhận snippet request/response cũ vẫn được tạo.
6. Thử withDefaults(...) với danh sách nhỏ, quan sát snippet nào không còn xuất hiện và khôi phục danh sách cần thiết.
7. Thay đổi template rồi xem diff output trong CI để kiểm tra chỉ định dạng được thay đổi.

**Tiêu chí hoàn thành:** xác định đúng vị trí template theo format ID; override được snippet mặc định bằng Mustache; truyền và hiển thị custom attributes; đổi được Asciidoctor/Markdown; phân biệt withDefaults(...) và withAdditionalDefaults(...); kiểm tra output qua build.

## 14. Checklist trước khi commit template

- [ ] Template nằm đúng package classpath và đúng format ID.
- [ ] Tên file template khớp tên snippet muốn override.
- [ ] Placeholder Mustache dùng đúng model và attribute.
- [ ] Attributes cấp field và cấp snippet được phân biệt rõ ràng.
- [ ] Template vẫn hiển thị đủ thông tin quan trọng của snippet gốc.
- [ ] Format Asciidoctor/Markdown khớp cấu hình test và pipeline tài liệu.
- [ ] Chỉ dùng withDefaults(...) khi chủ ý thay toàn bộ danh sách default snippets.
- [ ] Đã chạy test sinh snippet và kiểm tra nội dung file output.
- [ ] Build tài liệu thành công từ snippet mới.

**Ghi nhớ:** Tùy chỉnh generated snippets chủ yếu là thay template Mustache và bổ sung attributes. Đặt template đúng classpath/format ID, truyền metadata từ descriptor, rồi để test tạo lại snippet giúp dự án thay đổi cách trình bày mà vẫn giữ nguồn dữ liệu được kiểm chứng bởi Spring REST Docs.

## Tài liệu tham khảo

- [Spring REST Docs - Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html)
- [Spring REST Docs - Snippet Template Format](https://docs.spring.io/spring-restdocs/reference/configuration/snippet-template-format.html)
- [Spring REST Docs API - SnippetConfigurer](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/config/SnippetConfigurer.html)
