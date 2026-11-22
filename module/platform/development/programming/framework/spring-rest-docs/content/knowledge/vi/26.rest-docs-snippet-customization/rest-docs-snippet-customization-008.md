# Đặt template trong src/test/resources

## 1. Vì sao vị trí template lại quan trọng?

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test thực hiện request, xác nhận response và khai báo descriptor; Spring REST Docs dùng dữ liệu operation để sinh các snippet về request, response, fields, parameters, headers và hypermedia links. Những snippet này được ghép vào Asciidoctor/Markdown rồi đưa vào build, CI.

Khi cần tùy chỉnh cách trình bày, bạn có thể cung cấp Mustache template riêng. Spring REST Docs tìm template tùy chỉnh trên classpath theo một quy ước cụ thể. Nếu đặt file sai thư mục, sai format ID hoặc sai tên snippet, template mặc định sẽ tiếp tục được dùng mà không nhất thiết báo lỗi rõ ràng.

Vì template thường chỉ phục vụ việc sinh tài liệu trong test, vị trí phù hợp là:

~~~text
src/test/resources/
└── org/
    └── springframework/
        └── restdocs/
            └── templates/
                └── asciidoctor/
                    └── request-fields.snippet
~~~

Đường dẫn này trở thành classpath resource:

~~~text
org/springframework/restdocs/templates/asciidoctor/request-fields.snippet
~~~

Điểm quan trọng là Spring REST Docs tìm theo classpath resource, không tìm bằng đường dẫn tùy ý từ thư mục làm việc hiện tại.

## 2. Cấu trúc thư mục có ý nghĩa gì?

Đường dẫn template có ba phần chính:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Package gốc | Namespace resource Spring REST Docs dùng để tìm template | org/springframework/restdocs/templates |
| Format ID | Chọn bộ template cho định dạng đầu ra | asciidoctor hoặc markdown |
| Tên snippet | Chọn đúng loại snippet muốn override | request-fields.snippet |

Quy tắc tổng quát:

~~~text
src/test/resources/
└── org/springframework/restdocs/templates/
    └── {format-id}/
        └── {snippet-name}.snippet
~~~

Ví dụ:

~~~text
src/test/resources/
└── org/springframework/restdocs/templates/
    ├── asciidoctor/
    │   ├── request-fields.snippet
    │   ├── response-fields.snippet
    │   ├── path-parameters.snippet
    │   ├── query-parameters.snippet
    │   ├── http-request.snippet
    │   ├── http-response.snippet
    │   └── links.snippet
    └── markdown/
        ├── request-fields.snippet
        ├── path-parameters.snippet
        └── links.snippet
~~~

Không cần tạo tất cả các file trên. Chỉ đặt những template thực sự muốn thay đổi. Những template không có bản override sẽ tiếp tục được lấy từ thư viện Spring REST Docs.

## 3. Tên template phải khớp snippet

Tên template là tên snippet, bỏ phần mở rộng đầu ra và dùng hậu tố nguồn .snippet.

| Snippet được tạo | Template cần đặt |
| --- | --- |
| request-fields | request-fields.snippet |
| response-fields | response-fields.snippet |
| path-parameters | path-parameters.snippet |
| query-parameters | query-parameters.snippet |
| request-headers | request-headers.snippet |
| response-headers | response-headers.snippet |
| links | links.snippet |
| curl-request | curl-request.snippet |
| http-request | http-request.snippet |
| http-response | http-response.snippet |

Ví dụ, khi test sử dụng requestFields(...), Spring REST Docs tạo snippet request-fields. Muốn đổi bảng này, tạo request-fields.snippet trong đúng thư mục format. Tạo file fields.snippet hoặc requestFields.snippet sẽ không thay thế template có tên request-fields.

Tên file template phân biệt theo quy ước tên snippet của thư viện. Trên hệ thống build chạy Linux, chữ hoa/chữ thường trong tên resource cũng có thể ảnh hưởng việc tìm file; nên giữ đúng cách viết tên snippet.

## 4. Vì sao đặt trong src/test/resources?

Gradle và Maven đưa tài nguyên trong src/test/resources vào test runtime classpath. Đây là nơi phù hợp cho template chỉ được sử dụng bởi documentation tests:

- Không đóng gói template phục vụ test vào artifact ứng dụng production.
- Template được commit cùng test và có thể review như mã nguồn.
- Mỗi module có thể có quy tắc trình bày riêng mà không ảnh hưởng module khác.
- Khi chạy test, resource lookup có thể tìm thấy template trên classpath.

Phân biệt hai vị trí:

| Vị trí | Classpath | Khi nào phù hợp |
| --- | --- | --- |
| src/main/resources | Runtime classpath của ứng dụng | Tài nguyên ứng dụng cần khi chạy production |
| src/test/resources | Test runtime classpath | Template chỉ dùng để sinh tài liệu trong test |

Không nên đặt template kiểm thử trong src/main/resources chỉ để làm cho việc tìm file có vẻ dễ hơn. Làm vậy có thể khiến template nội bộ bị đóng gói vào artifact ứng dụng và trộn trách nhiệm tài liệu hóa với runtime.

Nếu một dự án chủ động tái sử dụng template cho nhiều module hoặc công cụ, có thể đóng gói template vào test-fixtures hoặc thư viện tài nguyên dùng riêng cho test. Dù chọn cách đó, resource cuối cùng vẫn phải xuất hiện trên classpath của documentation test và giữ đúng package/format/name convention.

## 5. Cấu hình format phải khớp thư mục template

Spring REST Docs cung cấp các template format dựng sẵn như Asciidoctor và Markdown. Format được chọn trong cấu hình snippet:

~~~java
import org.springframework.restdocs.templates.TemplateFormats;

this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
        .apply(documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.asciidoctor()))
        .build();
~~~

Với cấu hình này, thư mục template override phải là:

~~~text
src/test/resources/org/springframework/restdocs/templates/asciidoctor/
~~~

Khi chọn Markdown:

~~~java
.snippets()
.withTemplateFormat(TemplateFormats.markdown())
~~~

Thư mục override tương ứng là:

~~~text
src/test/resources/org/springframework/restdocs/templates/markdown/
~~~

Đặt request-fields.snippet trong thư mục markdown nhưng test vẫn dùng TemplateFormats.asciidoctor() sẽ không tạo override cho lần render Asciidoctor. Hãy kiểm tra cấu hình của chính test client đang sinh snippet, không chỉ kiểm tra một cấu hình chung ở nơi khác.

## 6. Ví dụ đầy đủ: override request-fields

Giả sử muốn thêm cột Constraints vào snippet request fields.

### Bước 1: Tạo file đúng vị trí

~~~text
src/test/resources/org/springframework/restdocs/templates/asciidoctor/request-fields.snippet
~~~

### Bước 2: Viết nội dung Mustache

~~~mustache
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

Đây là ví dụ tối giản để minh họa vị trí và cơ chế override. Trong dự án thật, nên sao chép template request-fields mặc định của đúng phiên bản Spring REST Docs rồi thêm cột cần thiết. Cách đó giúp giữ các thông tin mặc định như optional, ignored, deprecated hoặc metadata đặc thù nếu template phiên bản đang dùng có hỗ trợ.

### Bước 3: Truyền metadata từ descriptor

~~~java
requestFields(
        fieldWithPath("email")
                .description("Địa chỉ email")
                .attributes(key("constraints")
                        .value("Phải đúng định dạng email")),
        fieldWithPath("displayName")
                .description("Tên hiển thị")
                .attributes(key("constraints")
                        .value("Từ 2 đến 80 ký tự")))
~~~

Template lấy constraints từ attribute của mỗi field. Nếu chưa truyền key đó, placeholder tương ứng có thể rỗng. Template không tự suy luận ràng buộc từ controller hoặc Bean Validation.

### Bước 4: Chạy documentation test và kiểm tra output

Sau khi test chạy, kiểm tra thư mục snippet đã cấu hình, thường là:

~~~text
build/generated-snippets/
└── users-create/
    └── request-fields.adoc
~~~

Đây là output directory mặc định thường gặp với Gradle; nếu dự án cấu hình output directory khác, hãy kiểm tra đúng nơi đã cấu hình. Nội dung được sinh ra phải có cột Constraints và giá trị từ attributes.

## 7. Tổ chức template cho nhiều module

Trong dự án nhiều module, mỗi module có test resources và test runtime classpath riêng. Ví dụ:

~~~text
project/
├── api-users/
│   └── src/test/resources/
│       └── org/springframework/restdocs/templates/asciidoctor/
│           └── request-fields.snippet
├── api-orders/
│   └── src/test/resources/
│       └── org/springframework/restdocs/templates/asciidoctor/
│           └── request-fields.snippet
└── build.gradle
~~~

Hai module có thể dùng cùng đường dẫn resource nhưng nội dung template khác nhau, vì mỗi module chạy test với classpath riêng. Nếu test một module không thấy override, trước hết kiểm tra file có nằm trong test resources của đúng module đó không.

Khi chia sẻ template giữa nhiều module:

1. Đặt template chung trong test-fixtures hoặc một resource artifact dùng riêng cho test.
2. Thêm artifact đó vào test runtime classpath của từng module.
3. Giữ đúng package, format ID và tên snippet.
4. Xác nhận không có resource cùng đường dẫn khác chiếm ưu tiên trên classpath.
5. Chạy documentation test ở từng module để kiểm tra output.

Không giả định một file trong src/test/resources của module A tự động có mặt trên classpath của module B. Cần cấu hình dependency test tương ứng.

## 8. Tránh xung đột resource và kiểm tra classpath

Một số dự án có nhiều thư viện hoặc test fixtures cùng đóng góp tài nguyên dưới package org/springframework/restdocs/templates. Khi đó có thể tồn tại nhiều resource cùng đường dẫn. Cần kiểm tra resource thực tế mà classloader nhìn thấy.

Có thể dùng đoạn Java nhỏ trong test để liệt kê các resource cùng tên:

~~~java
Enumeration<URL> resources =
        Thread.currentThread()
                .getContextClassLoader()
                .getResources(
                        "org/springframework/restdocs/templates/asciidoctor/request-fields.snippet");

while (resources.hasMoreElements()) {
    System.out.println(resources.nextElement());
}
~~~

Nếu có nhiều kết quả, kiểm tra thứ tự và nguồn của từng resource. Không nên dựa vào thứ tự classpath tình cờ để quyết định template nào được dùng. Tốt nhất chỉ có một override có chủ ý cho mỗi tên template trong test runtime classpath của module.

Có thể kiểm tra resource có được tìm thấy hay không:

~~~java
URL template = Thread.currentThread()
        .getContextClassLoader()
        .getResource(
                "org/springframework/restdocs/templates/asciidoctor/request-fields.snippet");

assertThat(template).isNotNull();
System.out.println(template);
~~~

Đoạn này chỉ xác nhận resource tồn tại; việc REST Docs thực sự sử dụng template còn phụ thuộc format đã chọn, tên snippet và quá trình render. Hãy kết hợp kiểm tra classpath với kiểm tra nội dung snippet sinh ra.

## 9. Quan hệ giữa template nguồn và snippet đầu ra

Không nhầm file template nguồn với file snippet đã render:

| File | Vai trò | Ví dụ |
| --- | --- | --- |
| request-fields.snippet | Mustache template được nạp từ classpath | src/test/resources/.../asciidoctor/ |
| request-fields.adoc | Snippet đầu ra sau khi chạy test Asciidoctor | build/generated-snippets/users-create/ |
| request-fields.md | Snippet đầu ra khi dùng format Markdown | Output directory của test |

Template là đầu vào của bước render; snippet là kết quả được ghi vào output directory của operation. Sửa template không tự cập nhật file snippet cũ nếu test chưa chạy lại. Vì vậy, task biên soạn tài liệu phải phụ thuộc vào documentation tests.

Luồng build nên có thứ tự:

~~~text
Clean generated snippets
          |
          v
Run documentation tests
          |
          v
Load template from test classpath
          |
          v
Render snippets to output directory
          |
          v
Run Asciidoctor / Markdown build
          |
          v
Verify documentation artifact
~~~

Không sửa trực tiếp file .adoc hoặc .md được sinh ra để tùy chỉnh định dạng. Thay đổi template nguồn, chạy test lại và để build tái tạo snippet.

## 10. Các lỗi phổ biến khi đặt template

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Template mặc định vẫn được dùng | Template override sai đường dẫn hoặc không ở test classpath | Kiểm tra resource URL bằng classloader và thư mục format ID |
| Asciidoctor override không có hiệu lực | Test đang chọn Markdown hoặc format khác | Kiểm tra withTemplateFormat(...) ở test adapter |
| Chỉ một loại snippet thay đổi | Chỉ tạo template cho một tên snippet | Tạo file riêng cho request-fields, path-parameters, links... cần override |
| Template không được nạp trong module con | Resource nằm ở module khác | Đặt vào test resources đúng module hoặc khai báo test fixture dependency |
| File có tên gần đúng nhưng không được dùng | Tên không khớp snippet name | Dùng đúng tên dạng request-fields.snippet |
| Test chạy local được nhưng CI không thấy file | Resource path sai chữ hoa/thường hoặc không được commit | Kiểm tra tên file và nội dung trên hệ thống build CI |
| Template thay đổi nhưng snippet cũ không đổi | Documentation test chưa chạy lại hoặc output cũ chưa được làm mới | Chạy task test tạo snippet và kiểm tra output directory |
| Có hai template cùng đường dẫn | Nhiều dependency đưa resource trùng tên vào classpath | Liệt kê resource URL và loại bỏ xung đột |
| Include tài liệu không tìm thấy snippet | Output extension hoặc directory không khớp | Kiểm tra TemplateFormat, output directory và include path |

Khi chẩn đoán, đi theo thứ tự: xác nhận test đang dùng format nào, xác nhận template path trong classpath, xác nhận tên snippet, sau đó kiểm tra output. Cách này giúp xác định lỗi ở bước lookup hay bước render.

## 11. Bài thực hành

1. Tạo request-fields.snippet dưới src/test/resources theo format Asciidoctor.
2. Chạy một documentation test và xác nhận resource override được dùng trong output.
3. Tạo thêm path-parameters.snippet và query-parameters.snippet; kiểm tra từng snippet được thay độc lập.
4. Chuyển cấu hình test sang Markdown và tạo template cùng tên dưới thư mục markdown.
5. Dùng classloader liệt kê resource URL để xác nhận template có trên test runtime classpath.
6. Tạo hai module test riêng, đặt cùng tên template nhưng nội dung khác nhau; quan sát classpath độc lập.
7. Tạo một resource trùng đường dẫn trong test fixture rồi chẩn đoán xung đột; sau đó bỏ nguồn trùng.
8. Nối task sinh snippet vào task biên soạn Asciidoctor/Markdown trong CI.

**Tiêu chí hoàn thành:** biết đường dẫn template chuẩn trong src/test/resources; hiểu format ID và snippet name; phân biệt template nguồn với snippet đầu ra; kiểm tra classpath và tránh xung đột; tổ chức được template trong dự án nhiều module.

## 12. Checklist trước khi commit template

- [ ] Template nằm trong src/test/resources của đúng module hoặc test fixture dependency.
- [ ] Package path là org/springframework/restdocs/templates.
- [ ] Thư mục con khớp format ID đang cấu hình.
- [ ] Tên file khớp chính xác tên snippet.
- [ ] Chỉ override các template thực sự cần thay đổi.
- [ ] Template được lưu UTF-8 và dùng cú pháp đúng với Mustache engine mặc định.
- [ ] Test runtime classpath chỉ có override dự kiến, không có resource trùng không rõ nguồn.
- [ ] Documentation test đã chạy lại để tạo snippet mới.
- [ ] Đường dẫn include khớp output directory và phần mở rộng.
- [ ] Build/CI tạo được tài liệu cuối từ snippet mới.

**Ghi nhớ:** Spring REST Docs tìm template tùy chỉnh trên classpath theo package, format ID và tên snippet. Đặt file trong src/test/resources đúng module giúp template chỉ phục vụ documentation tests; kết hợp kiểm tra classpath và output sinh ra sẽ bảo đảm override được dùng đúng trong máy phát triển lẫn CI.
