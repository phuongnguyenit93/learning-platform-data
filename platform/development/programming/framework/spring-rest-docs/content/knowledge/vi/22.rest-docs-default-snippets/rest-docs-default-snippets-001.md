# Danh sách snippet mặc định của Spring REST Docs

## 1. Snippet là gì và được sinh khi nào?

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Snippets mặc định**, các bài kiểm thử HTTP tạo ra những mảnh tài liệu nhỏ gọi là *snippet*. Chúng mô tả request, response, payload, parameter và header mà test đã thực hiện, sau đó được ghép thành tài liệu Asciidoctor hoặc Markdown và đưa vào build/CI.

Spring REST Docs không tự quét mọi endpoint để sinh toàn bộ tài liệu. Test phải gọi API tài liệu hóa, thường là document(...), sau khi thực hiện request. Khi operation được ghi lại, REST Docs tạo các snippet HTTP cơ bản. Những bảng mô tả path parameter, header, JSON field hoặc liên kết chỉ được tạo khi test khai báo descriptor tương ứng.

Với định dạng AsciiDoc mặc định, sáu snippet HTTP cơ bản thường gặp là:

| Tên file | Nội dung |
| --- | --- |
| curl-request.adoc | Lệnh cURL có thể dùng để tái hiện request. |
| httpie-request.adoc | Lệnh HTTPie tương ứng với request. |
| http-request.adoc | Request ở dạng thông điệp HTTP. |
| http-response.adoc | Response HTTP mà test nhận được. |
| request-body.adoc | Body mà client gửi. |
| response-body.adoc | Body mà server trả về. |

Những file này ghi lại operation mà test quan sát. Chúng không tự giải thích nghiệp vụ, không thay thế assertion và không chứng minh toàn bộ API đã được kiểm thử. Muốn có tài liệu về field, parameter, header hoặc link, test phải thêm descriptor phù hợp.

## 2. Sáu snippet HTTP cơ bản

### curl-request.adoc

Snippet này tạo lệnh cURL để người tích hợp API có thể gửi lại request từ terminal.

```bash
curl 'http://localhost:8080/api/products/42' \
  -i \
  -H 'Accept: application/json'
```

Lệnh thực tế phụ thuộc request mà test thực hiện: HTTP method, URI, header và body. Khi dùng RANDOM_PORT, URI có thể chứa port động nếu chưa cấu hình URI hiển thị riêng cho snippet. Khi công bố tài liệu, hãy cấu hình URI để snippet thể hiện host và scheme mà người đọc cần dùng.

### httpie-request.adoc

Snippet này biểu diễn cùng request bằng cú pháp HTTPie:

```bash
http GET :8080/api/products/42 Accept:application/json
```

Đây là một cách trình bày thay thế, không phải request thứ hai và cũng không có nghĩa test đã chạy chương trình HTTPie. REST Docs tạo lệnh minh họa từ operation được ghi lại.

### http-request.adoc

Snippet mô tả request dưới dạng thông điệp HTTP:

```http
GET /api/products/42 HTTP/1.1
Host: api.example.com
Accept: application/json
```

Nó hữu ích khi cần đọc method, path và header ở mức giao thức. Với request có body, phần header và body được phản ánh trong các snippet tương ứng.

### http-response.adoc

Snippet mô tả response HTTP mà test nhận được:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"name":"Mechanical Keyboard"}
```

Status và header là bằng chứng từ operation đã chạy. Nếu response thay đổi, assertion và descriptor có thể phát hiện thay đổi đó.

### request-body.adoc

Snippet chứa body mà client gửi, thường là JSON, form data hoặc payload khác:

```json
{
  "name": "Mechanical Keyboard",
  "price": 89.5
}
```

Nếu operation không có request body, nội dung snippet có thể rỗng hoặc không có nội dung đáng kể. Để mô tả ý nghĩa từng field và kiểm tra cấu trúc payload, cần thêm requestFields(...).

### response-body.adoc

Snippet chứa body server trả về:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "price": 89.5
}
```

Nó giúp người đọc xem payload mẫu. Để có bảng mô tả field và kiểm tra các field ngoài dự kiến, khai báo responseFields(...).

## 3. Snippet bổ sung được tạo từ descriptor

REST Docs có nhiều loại snippet khác ngoài sáu snippet HTTP cơ bản. Chúng xuất hiện khi test truyền descriptor hoặc cấu hình tương ứng vào document(...).

| Nhóm | Descriptor/API thường dùng | Tên snippet thường gặp | Thông tin |
| --- | --- | --- | --- |
| Path parameter | pathParameters(...) | path-parameters.adoc | Biến trong URI template, ví dụ {id}. |
| Request parameter | requestParameters(...) hoặc API tương ứng của client | request-parameters.adoc | Tham số gửi cùng request theo cách client/API hỗ trợ. |
| Request header | requestHeaders(...) | request-headers.adoc | Header client gửi. |
| Response header | responseHeaders(...) | response-headers.adoc | Header server trả về. |
| Request field | requestFields(...) | request-fields.adoc | Field của request payload. |
| Response field | responseFields(...) | response-fields.adoc | Field của response payload. |
| Hypermedia link | links(...) | links.adoc | Link relation và đích liên kết trong payload hypermedia. |

Tên và khả năng hỗ trợ descriptor phụ thuộc module client (MockMvc, WebTestClient hoặc REST Assured) và phiên bản Spring REST Docs. Hãy chọn API documentation tương ứng; không áp một import dành cho MockMvc vào WebTestClient.

### Path parameter

Ví dụ endpoint GET /api/products/{id}:

```java
mockMvc.perform(get("/api/products/{id}", 42))
    .andExpect(status().isOk())
    .andDo(document("products-find",
        pathParameters(
            parameterWithName("id").description("Mã sản phẩm")
        )
    ));
```

Với MockMvc, nên dùng RestDocumentationRequestBuilders.get(...) khi cần giữ URI template cho việc trích xuất path parameter. Nếu builder không giữ template, REST Docs có thể không xác định được tên {id} từ URI đã mở rộng.

### Request header và response header

```java
document("products-find",
    requestHeaders(
        headerWithName("Accept")
            .description("Định dạng phản hồi mong muốn")
    ),
    responseHeaders(
        headerWithName("Content-Type")
            .description("Định dạng payload trả về")
    )
)
```

Descriptor cho header giúp tài liệu nói rõ header có ý nghĩa gì. Đối với thông tin xác thực, không để token hoặc cookie thật xuất hiện trong snippet; dùng dữ liệu giả dành riêng cho test và redact trước khi lưu tài liệu.

### Request và response field

```java
document("products-create",
    requestFields(
        fieldWithPath("name").description("Tên sản phẩm"),
        fieldWithPath("price").description("Giá bán")
    ),
    responseFields(
        fieldWithPath("id").description("Mã sản phẩm được tạo"),
        fieldWithPath("name").description("Tên sản phẩm"),
        fieldWithPath("price").description("Giá bán")
    )
)
```

Descriptor field vừa tạo snippet dạng bảng vừa giúp kiểm tra payload với mô tả đã khai báo. Nếu JSON có field chưa được mô tả, test có thể thất bại. Hãy quyết định rõ field nào là tùy chọn, phần nào được bỏ qua có chủ đích và cập nhật descriptor khi hợp đồng thay đổi.

## 4. Cấu trúc thư mục snippet

Tên thư mục con được quyết định bởi operation ID truyền vào document("..."); thư mục gốc do Spring REST Docs/Spring Boot hoặc outputDir quyết định.

Ví dụ Gradle mặc định:

```text
build/
  generated-snippets/
    products-find/
      curl-request.adoc
      httpie-request.adoc
      http-request.adoc
      http-response.adoc
      request-body.adoc
      response-body.adoc
      path-parameters.adoc
      request-headers.adoc
      response-headers.adoc
      response-fields.adoc
```

Với Maven, thư mục gốc mặc định thường là target/generated-snippets/. Không phải operation nào cũng có đủ file được liệt kê: snippet phụ thuộc loại request, body, descriptor và module client. Không nên nhìn output của một GET rồi kết luận POST hoặc operation không body có cùng tập file.

Nếu test cấu hình outputDir thành build/custom-snippets, operation products-find nằm dưới build/custom-snippets/products-find/. Asciidoctor phải đọc đúng thư mục này, không tiếp tục lấy build/generated-snippets.

## 5. AsciiDoc và Markdown

Spring REST Docs mặc định dùng template AsciiDoc nên file snippet thường có phần mở rộng .adoc. Khi cấu hình TemplateFormats.markdown(), snippet có thể được sinh thành .md; thư mục gốc và operation ID vẫn theo nguyên tắc cũ.

Ví dụ cấu hình template Markdown cho MockMvc:

```java
@TestConfiguration(proxyBeanMethods = false)
class RestDocsMarkdownConfiguration
        implements RestDocsMockMvcConfigurationCustomizer {

    @Override
    public void customize(MockMvcRestDocumentationConfigurer configurer) {
        configurer.snippets()
            .withTemplateFormat(TemplateFormats.markdown());
    }
}
```

Nạp cấu hình bằng @Import(RestDocsMarkdownConfiguration.class) vào test context. Nếu chuyển sang Markdown, phải cập nhật công cụ ghép tài liệu và đường dẫn include; cú pháp Asciidoctor include ... .adoc không tự chuyển thành include Markdown.

| Định dạng | Phần mở rộng | Công cụ ghép |
| --- | --- | --- |
| AsciiDoc mặc định | .adoc | Asciidoctor |
| Markdown | .md | Markdown processor/static site generator hỗ trợ include hoặc cơ chế ghép riêng |

## 6. Ghép snippet vào Asciidoctor

File nguồn AsciiDoc có thể chọn các snippet cần trình bày:

```asciidoc
= Catalog API
:toc: left

== Tìm sản phẩm

=== HTTP request
include::{snippets}/products-find/http-request.adoc[]

=== cURL
include::{snippets}/products-find/curl-request.adoc[]

=== Path parameters
include::{snippets}/products-find/path-parameters.adoc[]

=== Response
include::{snippets}/products-find/http-response.adoc[]

=== Response fields
include::{snippets}/products-find/response-fields.adoc[]
```

Attribute snippets phải trỏ tới thư mục gốc. Với Gradle, đường dẫn mặc định thường là build/generated-snippets; với Maven, thường là target/generated-snippets. Nếu test dùng outputDir riêng, build phải dùng đúng đường dẫn đó.

Không cần include mọi snippet vào mọi trang. Tài liệu hướng dẫn tích hợp có thể ưu tiên cURL và response fields; tài liệu debug nội bộ có thể hiển thị request/response nguyên dạng và header. Chọn các mảnh phù hợp để trang dễ đọc.

## 7. Build và CI

Với Gradle, khai báo snippet là output của test và input của Asciidoctor:

```groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.named('test') {
    useJUnitPlatform()
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.get().asFile
}
```

Chạy từ trạng thái sạch:

```bash
./gradlew clean test asciidoctor
```

Với Maven, chạy test trước bước Asciidoctor và đặt attribute snippets trỏ tới thư mục dưới target/generated-snippets. Nếu snippet chỉ được sinh bởi integration test ở Failsafe, bước tài liệu phải diễn ra sau các test đó.

CI nên sinh snippet và tài liệu trong cùng pipeline. Không bỏ qua test nếu snippet cần thiết chỉ do test tạo; không publish HTML nếu test hoặc Asciidoctor thất bại. Dùng clean build khi xác minh pipeline để tránh snippet cũ còn sót từ lần chạy trước.

## 8. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Dependency REST Docs tự sinh tất cả snippet khi chạy test. | Phải có operation được ghi bằng document(...). |
| Mọi operation đều có mọi file snippet. | Snippet phụ thuộc loại request, body, descriptor và module client. |
| response-body.adoc giải thích schema JSON. | Nó hiển thị body; bảng mô tả field cần responseFields(...). |
| http-request.adoc tương đương curl-request.adoc. | Một file là thông điệp HTTP, file kia là lệnh cURL tái hiện request. |
| Tên folder tự suy ra từ URL/controller. | Operation ID truyền vào document(...) quyết định folder con. |
| Chuyển template sang Markdown chỉ đổi đuôi file. | Còn phải đổi cách ghép tài liệu và include tương ứng. |
| Snippet có URL production nghĩa là test đã gọi production. | URI có thể được cấu hình/preprocess riêng; test vẫn có thể gọi localhost. |

## 9. Bài thực hành

Tạo hai operation cho API Catalog:

1. GET /api/products/{id}: ghi request, response, path parameter, request header và response fields.
2. POST /api/products: ghi request body, request fields, response header Location và response fields.
3. Chạy test, mở thư mục output và phân loại file thành snippet HTTP cơ bản và snippet descriptor.
4. Viết AsciiDoc include http-request, curl-request, http-response và bảng field của từng operation.
5. Xóa một descriptor rồi chạy lại test để quan sát thay đổi snippet tương ứng và kiểm tra contract.
6. Đổi operation ID và outputDir, cập nhật attribute snippets trong build rồi chạy clean build.
7. Tùy chọn: đổi template format sang Markdown và thiết kế bước ghép snippet .md vào tài liệu.

**Tiêu chí hoàn thành:** kể tên và giải thích được sáu snippet HTTP cơ bản; biết snippet descriptor nào xuất hiện khi khai báo API tương ứng; xác định đúng output folder và operation ID; ghép được snippet vào Asciidoctor; CI tạo tài liệu từ snippet của lần test hiện tại.

## 10. Tài liệu tham khảo

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/index.html)
- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/configuration/default-snippets.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring Boot 3.5 — Auto-configured Spring REST Docs Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
