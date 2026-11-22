# Snippet template format và engine mặc định

## 1. Hai thành phần quyết định cách snippet được tạo

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Sau khi test thực hiện request và kiểm tra response, REST Docs thu thập dữ liệu operation, kết hợp descriptor và attributes, rồi sinh snippet về request, response, payload, tham số, header hoặc hypermedia links. Các snippet được đưa vào Asciidoctor/Markdown và quy trình build, CI.

Quá trình render có hai khái niệm cần phân biệt:

- **TemplateFormat** xác định định dạng đầu ra: định danh format, phần mở rộng file snippet và vị trí tìm template tương ứng.
- **TemplateEngine** đọc và biên dịch template, nhận model dữ liệu rồi render thành nội dung snippet.

Ở cấu hình thông thường, nhóm phát triển chọn một template format dựng sẵn và dùng Mustache template engine mặc định. Hiểu đúng vai trò của hai thành phần giúp cấu hình Asciidoctor/Markdown nhất quán và biết khi nào cần đổi format, khi nào chỉ cần thay template.

~~~text
HTTP operation + descriptors + attributes
                  |
                  v
             Snippet model
                  |
                  v
          TemplateFormat
      (format ID / extension)
                  |
                  v
            TemplateEngine
        (compile / render)
                  |
                  v
          Generated snippet
                  |
                  v
       Asciidoctor / Markdown build
~~~

## 2. TemplateFormat là gì?

TemplateFormat đại diện cho định dạng snippet. Một format cho biết REST Docs phải tìm nhóm template nào trên classpath và dùng phần mở rộng nào cho file được sinh. Format không chứa logic kiểm tra HTTP và cũng không quyết định operation nào được ghi tài liệu.

Spring REST Docs cung cấp các format dựng sẵn thông dụng:

| Format | Cấu hình | Mục đích |
| --- | --- | --- |
| Asciidoctor | TemplateFormats.asciidoctor() | Sinh snippet phù hợp tài liệu AsciiDoc/Asciidoctor |
| Markdown | TemplateFormats.markdown() | Sinh snippet theo định dạng Markdown |

Format cũng cung cấp ID dùng trong đường dẫn tìm template. Với Asciidoctor, template override nằm dưới thư mục có ID asciidoctor; với Markdown, dùng thư mục có ID markdown. Tên file template tương ứng với tên snippet, thường có phần mở rộng nguồn .snippet. Phần mở rộng file đầu ra do format quy định.

Một cấu trúc resource minh họa:

~~~text
src/test/resources/
└── org/springframework/restdocs/templates/
    ├── asciidoctor/
    │   ├── request-fields.snippet
    │   └── http-response.snippet
    └── markdown/
        ├── request-fields.snippet
        └── http-response.snippet
~~~

Chỉ cần cung cấp template override cho snippet thực sự muốn đổi. Những template khác vẫn dùng tài nguyên mặc định của Spring REST Docs. Cấu trúc trên minh họa cách tra cứu; dự án không cần sao chép toàn bộ template mặc định vào test resources.

## 3. TemplateEngine mặc định làm gì?

TemplateEngine là thành phần xử lý nội dung template. Về mặt chức năng, engine:

1. Tìm và nạp template theo tên snippet cùng resource path của format đã chọn.
2. Biên dịch cú pháp template để có thể tái sử dụng.
3. Nhận model dữ liệu của snippet, gồm những trường như path, type, description hoặc attributes.
4. Render model vào template để tạo văn bản đầu ra.

Spring REST Docs dùng **Mustache** làm template engine mặc định. Cú pháp Mustache sử dụng placeholder và section, ví dụ:

~~~mustache
|Path|Type|Description
{{#fields}}
|{{path}}|{{type}}|{{description}}
{{/fields}}
~~~

Trong ví dụ, fields là tập dữ liệu lặp; path, type và description lấy từ model của từng field descriptor. Engine không tự suy luận nội dung nghiệp vụ như quy tắc validation. Nếu cần cột constraints, test phải truyền attribute tương ứng và template phải đọc attribute đó.

Điểm cần nhớ: TemplateFormat không render nội dung; TemplateEngine không quyết định hợp đồng HTTP. Descriptor và operation cung cấp dữ liệu; format chọn loại template/đầu ra; engine thực hiện việc render.

## 4. Chọn format trong cấu hình MockMvc

Format được chọn thông qua RestDocumentationConfigurer khi cấu hình MockMvc:

~~~java
import org.springframework.restdocs.templates.TemplateFormats;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;

@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
            .apply(documentationConfiguration(restDocumentation)
                    .snippets()
                    .withTemplateFormat(TemplateFormats.asciidoctor()))
            .build();
}
~~~

Để tạo snippet Markdown:

~~~java
this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
        .apply(documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.markdown()))
        .build();
~~~

Nếu format không được cấu hình tường minh, Spring REST Docs dùng định dạng mặc định của cấu hình tương ứng, thường là Asciidoctor. Khai báo rõ format giúp người đọc test hiểu đầu ra mong muốn và tránh việc include tài liệu trỏ sai phần mở rộng.

## 5. Chọn format với WebTestClient và REST Assured

Template format là một phần của cấu hình snippet, không gắn riêng với MockMvc. Các adapter kiểm thử khác cũng nhận cấu hình tài liệu hóa.

Với WebTestClient, cấu hình định dạng trong filter:

~~~java
this.webTestClient = WebTestClient.bindToApplicationContext(this.context)
        .configureClient()
        .filter(documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.markdown()))
        .build();
~~~

Với REST Assured, áp dụng cấu hình REST Docs trong filter:

~~~java
given(this.spec)
        .filter(documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.asciidoctor()))
        .when()
        .get("/api/products/42")
        .then()
        .statusCode(200)
        .apply(document("products-get"));
~~~

Đây là ví dụ minh họa vị trí cấu hình; cách khởi tạo RequestSpecification, RestDocumentationContextProvider và import phụ thuộc test setup của dự án. Dù dùng adapter nào, operation và descriptor quyết định nội dung được ghi; TemplateFormat quyết định định dạng snippet.

## 6. Đường dẫn tra cứu template theo format

Khi chọn format, Spring REST Docs sử dụng ID của format làm thư mục con khi tìm template override. Với format Asciidoctor:

~~~text
org/springframework/restdocs/templates/asciidoctor/request-fields.snippet
~~~

Với format Markdown:

~~~text
org/springframework/restdocs/templates/markdown/request-fields.snippet
~~~

Để một override được tìm thấy, kiểm tra đủ các yếu tố:

- Resource nằm trên classpath của test chạy documentation.
- Package path bắt đầu tại org/springframework/restdocs/templates.
- Thư mục format khớp format đang cấu hình.
- Tên template khớp loại snippet muốn thay, ví dụ request-fields.snippet.
- Resource có encoding và nội dung hợp lệ với template engine.

Nếu test chọn Markdown nhưng template tùy chỉnh chỉ nằm trong thư mục asciidoctor, template override đó sẽ không được dùng cho lần render Markdown. Khi cần hỗ trợ cả hai định dạng, tạo template ở cả hai thư mục với cú pháp đầu ra phù hợp từng format.

## 7. TemplateFormat và phần mở rộng snippet

Format ảnh hưởng cả cú pháp nội dung lẫn phần mở rộng file snippet. Ví dụ cùng operation products-get, một cấu hình Asciidoctor có thể tạo file:

~~~text
build/generated-snippets/
└── products-get/
    ├── http-request.adoc
    ├── http-response.adoc
    └── response-fields.adoc
~~~

Khi dùng Markdown, tên file tương ứng mang phần mở rộng Markdown do format cung cấp:

~~~text
build/generated-snippets/
└── products-get/
    ├── http-request.md
    ├── http-response.md
    └── response-fields.md
~~~

Tên snippet có thể giống nhau, nhưng nội dung template và phần mở rộng khác. Khi thay đổi format, cần đồng bộ:

1. Cấu hình withTemplateFormat(...) của test.
2. Vị trí và cú pháp template override.
3. Tên file snippet được sinh ra.
4. Đường dẫn include trong Asciidoctor hoặc bước nhúng snippet trong Markdown.
5. Task build và artifact tài liệu được xuất bản.

Chỉ đổi format trong test nhưng giữ các include đang trỏ đến .adoc có thể làm tài liệu biên soạn thất bại vì file đầu ra đã đổi sang .md.

## 8. TemplateEngine và TemplateFormat có thể thay đổi độc lập

Trong hầu hết dự án, chỉ cần chọn TemplateFormats.asciidoctor() hoặc TemplateFormats.markdown() và giữ engine mặc định. Nếu muốn điều chỉnh bảng, tiêu đề hay cách hiển thị, override file Mustache tương ứng thường đã đủ.

| Nhu cầu | Thành phần nên thay |
| --- | --- |
| Chuyển snippet từ AsciiDoc sang Markdown | TemplateFormat |
| Thay cách trình bày một snippet nhưng vẫn giữ đầu ra Asciidoctor | Template override |
| Thêm metadata riêng cho field | Descriptor attributes và template |
| Thay cơ chế biên dịch/render template | TemplateEngine, khi engine mặc định không đáp ứng |
| Đổi cú pháp template nhưng vẫn tạo cùng loại định dạng đầu ra | TemplateEngine và bộ template tương ứng nếu dự án triển khai hỗ trợ |

Không nên viết TemplateEngine riêng chỉ để thêm một cột hoặc đổi tiêu đề. Việc tự triển khai engine làm tăng trách nhiệm bảo trì: cần xử lý resource lookup, biên dịch, render, encoding và lỗi template nhất quán với pipeline.

## 9. Khi nào cần TemplateEngine tùy chỉnh?

Engine tùy chỉnh chỉ đáng cân nhắc nếu dự án có yêu cầu mà Mustache mặc định không giải quyết được, ví dụ:

- Tích hợp một hệ thống template khác đã là chuẩn của tổ chức.
- Cần logic render hoặc helper phức tạp vượt quá khả năng của Mustache template.
- Muốn quản lý và cache template theo cơ chế riêng.
- Có nhiều loại đầu ra hoặc quy tắc escape đặc biệt cần kiểm soát tập trung.

Trước khi triển khai, kiểm tra API của đúng phiên bản Spring REST Docs đang dùng: kiểu TemplateEngine, cách tạo Template, cơ chế cung cấp resource và phương thức gắn engine vào cấu hình snippet có thể thay đổi giữa các phiên bản.

Không sao chép một ví dụ triển khai engine từ phiên bản khác rồi giả định nó tương thích. Với yêu cầu thông thường, giữ engine mặc định và tùy chỉnh template/attributes sẽ tận dụng được resource lookup và hành vi render đã được Spring REST Docs hỗ trợ.

## 10. Encoding và tính ổn định của đầu ra

Template là tài nguyên văn bản. Với nội dung tiếng Việt, cần bảo đảm file template và đầu ra được xử lý thống nhất bằng UTF-8. Nếu snippet xuất hiện ký tự lỗi, kiểm tra:

- Encoding của file template trong repository.
- Encoding cấu hình cho quá trình render nếu dự án có tùy chỉnh.
- Encoding mà Asciidoctor/Markdown build sử dụng khi đọc snippet.
- Ký tự đặc biệt của cú pháp đầu ra có được escape phù hợp không.

Template cũng cần tránh phụ thuộc vào dữ liệu thay đổi theo môi trường như host, port, token hoặc thông tin cá nhân. Những dữ liệu động thuộc operation; tài liệu chỉ nên hiển thị giá trị giả ổn định hoặc đã được preprocess.

Khi nâng phiên bản Spring REST Docs, template mặc định và model attributes có thể thay đổi. Nên xem template mặc định của đúng phiên bản như hợp đồng kỹ thuật để đối chiếu bản override. Giữ file override tối thiểu giúp giảm khác biệt khi nâng cấp.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Template override không được dùng | Sai format ID hoặc package path | Đặt template dưới org/springframework/restdocs/templates/{format-id} trên test classpath. |
| Dùng template Asciidoctor nhưng test tạo Markdown | Format đang chọn là Markdown | Tạo template trong thư mục markdown hoặc đổi format cấu hình. |
| Include không tìm thấy snippet sau khi đổi format | Phần mở rộng file đã thay đổi | Kiểm tra output mới và cập nhật include/task tài liệu. |
| Template không render placeholder | Tên biến không có trong model hoặc attributes chưa được truyền | Đối chiếu template với snippet model và descriptor attributes. |
| Cú pháp template hiển thị nguyên văn | Template engine không hiểu cú pháp đang dùng | Dùng cú pháp Mustache với engine mặc định hoặc cấu hình engine tương thích. |
| Ký tự tiếng Việt bị lỗi | Encoding không thống nhất | Chuẩn hóa template và pipeline về UTF-8. |
| Một số snippet vẫn dùng format cũ | Test hoặc adapter khác có cấu hình snippet riêng | Kiểm tra cấu hình của từng test client và documentation test. |
| Template lỗi sau khi nâng phiên bản | Model hoặc template mặc định thay đổi | So sánh template phiên bản mới, cập nhật override và kiểm tra diff output. |

## 12. Bài thực hành

1. Chạy một documentation test với TemplateFormats.asciidoctor() và quan sát phần mở rộng, nội dung snippet.
2. Chuyển test sang TemplateFormats.markdown(); kiểm tra file sinh ra và điều chỉnh đường dẫn include.
3. Tạo hai template request-fields.snippet riêng cho Asciidoctor và Markdown; giữ dữ liệu field giống nhau nhưng đổi cú pháp bảng theo từng format.
4. Truyền attribute constraints vào một field descriptor và hiển thị nó bằng template Mustache.
5. Kiểm tra test MockMvc và WebTestClient có đang dùng cùng format hay không; thống nhất format cho cùng bộ tài liệu.
6. Thử đặt template sai format folder, chạy test và đọc dấu hiệu template mặc định được dùng.
7. Xem diff snippet sau khi chuyển format để bảo đảm nội dung request/response vẫn được giữ.

**Tiêu chí hoàn thành:** giải thích được vai trò khác nhau của TemplateFormat và TemplateEngine; chọn được format Asciidoctor/Markdown; xác định đúng template resource path; hiểu engine Mustache mặc định; đồng bộ phần mở rộng snippet với bước biên soạn tài liệu.

## 13. Checklist cấu hình template format

- [ ] Chọn format đầu ra phù hợp với công cụ biên soạn tài liệu.
- [ ] Cấu hình format nhất quán ở các documentation test.
- [ ] Template override nằm đúng thư mục theo format ID.
- [ ] Tên template khớp snippet muốn tùy chỉnh.
- [ ] Cú pháp template phù hợp với engine đang dùng.
- [ ] Attributes cần thiết đã được truyền từ descriptor/snippet.
- [ ] Encoding UTF-8 được giữ xuyên suốt.
- [ ] Include và phần mở rộng khớp file snippet sinh ra.
- [ ] Build/CI sinh snippet trước khi biên soạn và kiểm tra artifact cuối.

**Ghi nhớ:** TemplateFormat xác định loại snippet và nơi tìm template; TemplateEngine mặc định dựa trên Mustache để biên dịch và render dữ liệu operation thành văn bản. Trong đa số trường hợp, chọn đúng format và tùy chỉnh template là đủ; chỉ thay engine khi có yêu cầu render thực sự khác biệt.

## Tài liệu tham khảo

- Spring REST Docs - Snippet Template Format: https://docs.spring.io/spring-restdocs/reference/configuration/snippet-template-format.html
- Spring REST Docs - Customizing the Output: https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html
- Spring REST Docs API - TemplateFormat: https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/templates/TemplateFormat.html
- Spring REST Docs API - TemplateEngine: https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/templates/TemplateEngine.html
