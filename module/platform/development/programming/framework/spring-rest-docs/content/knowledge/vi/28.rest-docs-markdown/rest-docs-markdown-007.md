# Xử lý bảng Markdown và nội dung JSON

## Mục tiêu bài học

Trong tài liệu REST API, bảng Markdown thường được dùng để giải thích field, query parameter, path parameter và header. JSON snippet minh họa cấu trúc payload gửi lên hoặc nhận về. Khi ghép nội dung do **Spring REST Docs** sinh vào trang Markdown, cần giữ đúng dữ liệu đã kiểm thử và xử lý các ký tự có ý nghĩa cú pháp như dấu pipe, dấu gạch chéo ngược và dấu backtick.

Bài học thuộc chương **Markdown** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown rồi tích hợp vào build và CI.

Sau bài học, bạn có thể:

- Đọc và tổ chức field table được sinh từ descriptor REST Docs.
- Xử lý dấu pipe, backslash, backtick và nội dung nhiều dòng trong bảng Markdown.
- Giữ JSON body dễ đọc, đúng định dạng và đồng nhất với HTTP snippet.
- Phân biệt JSON body snippet với bảng request-fields/response-fields.
- Tùy chỉnh template hoặc lắp ghép snippet mà không làm sai nội dung.
- Kiểm tra code fence, JSON, UTF-8 và bảng sau khi assembly/render.
- Nối bước sinh snippet, ghép Markdown và kiểm tra đầu ra vào CI.

## 1. Bảng Markdown được dùng ở đâu?

REST Docs dùng descriptor để mô tả cấu trúc request/response. Khi render thành Markdown, các descriptor thường được trình bày dưới dạng bảng. Bảng giúp người đọc tra cứu nhanh tên field, kiểu, mô tả và trạng thái tùy chọn.

Ví dụ bảng request:

| Path | Type | Description |
| --- | --- | --- |
| customerId | Number | Mã khách hàng tạo đơn |
| description | String | Mô tả đơn hàng |
| note | String | Ghi chú bổ sung, không bắt buộc |

Ví dụ bảng response:

| Path | Type | Description |
| --- | --- | --- |
| id | Number | Mã đơn hàng do server cấp |
| status | String | Trạng thái hiện tại |
| createdAt | String | Thời điểm tạo theo ISO-8601 |

Hai bảng này là **field table**. Chúng mô tả schema của JSON; chúng không thay thế HTTP request/response snippet và cũng không chứa toàn bộ giá trị mẫu của payload.

## 2. Sinh bảng từ descriptor thay vì viết tay

Khai báo descriptor trong operation test để REST Docs đối chiếu với payload thật:

~~~java
document("orders-create",
    requestFields(
        fieldWithPath("customerId")
            .description("Mã khách hàng tạo đơn"),
        fieldWithPath("description")
            .description("Mô tả đơn hàng"),
        fieldWithPath("note")
            .optional()
            .description("Ghi chú bổ sung, không bắt buộc")
    ),
    responseFields(
        fieldWithPath("id")
            .description("Mã đơn hàng do server cấp"),
        fieldWithPath("status")
            .description("Trạng thái hiện tại"),
        fieldWithPath("createdAt")
            .description("Thời điểm tạo theo ISO-8601")
    )
)
~~~

Static imports thường dùng:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
~~~

Khi test thực thi, REST Docs kiểm tra descriptor với request/response payload được ghi nhận. Nếu JSON có field chưa được mô tả hoặc descriptor chỉ đến field không tồn tại, chế độ strict có thể làm test thất bại. Đây là tín hiệu cần xem lại contract hoặc descriptor, không nên chỉ bỏ kiểm tra để build chạy qua.

### 2.1. Field lồng nhau và array

Với JSON:

~~~json
{
  "customer": {
    "id": 42,
    "name": "Lan"
  },
  "items": [
    {
      "sku": "KB-01",
      "quantity": 2
    }
  ]
}
~~~

Descriptor có thể dùng path:

~~~java
requestFields(
    fieldWithPath("customer.id").description("Mã khách hàng"),
    fieldWithPath("customer.name").description("Tên khách hàng"),
    fieldWithPath("items[].sku").description("Mã sản phẩm"),
    fieldWithPath("items[].quantity").description("Số lượng")
)
~~~

Nếu muốn mô tả một object/array như một đơn vị thay vì liệt kê mọi phần tử con, cân nhắc subsectionWithPath(...) phù hợp với phiên bản REST Docs. Tránh mô tả cùng object cha và field con theo cách tạo descriptor chồng lấn.

### 2.2. Optional và null là hai khái niệm khác nhau

Field **optional** có thể vắng mặt trong JSON. Field có giá trị **null** vẫn hiện diện nhưng value là null. Hai trường hợp cần được phân biệt trong contract.

~~~java
requestFields(
    fieldWithPath("customerId").description("Mã khách hàng"),
    fieldWithPath("note")
        .optional()
        .description("Có thể không gửi; nếu gửi thì là chuỗi")
)
~~~

Nếu API cho phép note có giá trị null, cần nói rõ điều đó trong mô tả và kiểm thử riêng. Không coi optional() là chỉ thị rằng giá trị null được chấp nhận.

## 3. Ký tự đặc biệt trong bảng Markdown

Markdown table dùng dấu pipe để phân tách cột. Nếu mô tả field có dấu này, renderer có thể tạo thêm cột ngoài ý muốn.

Ví dụ nội dung cần hiển thị:

~~~text
Giá trị chấp nhận: compact | comfortable
~~~

Trong bảng Markdown, escape pipe bằng dấu gạch chéo ngược:

| Path | Description |
| --- | --- |
| displayMode | Giá trị chấp nhận: compact \| comfortable |

### 3.1. Escape nội dung table trong template

Nếu custom template tạo bảng từ descriptor, cần escape nội dung cell trước khi ghép:

- Pipe phải được escape theo quy tắc của Markdown table.
- Backslash cần được xử lý để không làm mất ký tự escape kế tiếp.
- Nội dung có newline cần được chuyển thành dạng hiển thị một dòng hoặc HTML break nếu renderer cho phép.
- HTML, backtick và entity cần được xử lý theo chính sách output của renderer.

Ví dụ hàm Java tối giản để escape pipe trong một cell:

~~~java
String escapeTableCell(String value) {
    return value
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ");
}
~~~

Đây chỉ là ví dụ cho cell text thông thường. Nếu template cần hỗ trợ HTML, backtick, ký tự điều khiển hoặc Markdown inline phức tạp, hãy dùng bộ escape/template phù hợp thay vì mở rộng bằng các phép replace thiếu kiểm soát.

### 3.2. Backtick trong field name hoặc description

Backtick được dùng để đánh dấu code inline. Nếu nội dung có backtick, chọn delimiter dài hơn chuỗi backtick liên tiếp dài nhất trong nội dung hoặc escape theo renderer. Không để một dấu backtick bên trong làm đóng code span quá sớm.

Nếu tên field là customer.version, hiển thị bằng code span sẽ dễ đọc hơn văn bản thường. Nội dung code span vẫn cần escape nếu có backtick hoặc ký tự đặc biệt.

## 4. Nội dung nhiều dòng trong bảng

Markdown table truyền thống phù hợp với cell ngắn, một dòng. Tránh đưa một đoạn JSON hoặc mô tả nhiều dòng dài vào một ô vì khả năng hiển thị khác nhau giữa renderer.

Hãy giữ table ngắn:

| Path | Type | Description |
| --- | --- | --- |
| options | Object | Các tùy chọn bổ sung |

Sau đó đưa chi tiết vào section riêng:

~~~json
{
  "theme": "dark",
  "locale": "vi"
}
~~~

Cách trình bày này giúp bảng dễ quét, còn cấu trúc phức tạp có chỗ riêng để giải thích.

## 5. JSON body snippet và field table

REST Docs có các snippet khác nhau cho HTTP exchange và payload descriptor. Tùy template/version, tên file có thể có phần mở rộng .adoc hoặc .md. Các nhóm nội dung thường gặp:

| Nội dung | Snippet thường dùng | Dùng để |
| --- | --- | --- |
| HTTP request | http-request | Hiển thị method, URI, header và body |
| HTTP response | http-response | Hiển thị status, header và body |
| Request body | request-body | Hiển thị payload gửi lên, nếu cấu hình snippet này |
| Response body | response-body | Hiển thị payload trả về, nếu cấu hình snippet này |
| Request field table | request-fields | Mô tả field của request body |
| Response field table | response-fields | Mô tả field của response body |

HTTP request/response và request-body/response-body có thể cùng chứa thông tin body ở hai ngữ cảnh hiển thị khác nhau. Đừng nhúng lặp cả hai nếu không mang thêm giá trị cho người đọc.

### 5.1. Giữ JSON đúng nguồn

Ví dụ request body:

~~~json
{
  "customerId": 42,
  "description": "Bàn phím"
}
~~~

Ví dụ response body:

~~~json
{
  "id": 731,
  "status": "CREATED"
}
~~~

JSON snippet phải phản ánh body mà test thực sự gửi/nhận. Không chỉnh sửa giá trị, xóa field hoặc tự thêm ví dụ vào snippet generated để làm output đẹp hơn. Nếu cần dữ liệu mẫu dễ đọc, hãy thay đổi fixture test và chạy lại REST Docs để snippet tiếp tục được kiểm chứng.

### 5.2. Định dạng JSON

Để JSON dễ đọc:

- Dùng fenced code block với nhãn json.
- Giữ indentation nhất quán.
- Giữ chuỗi Unicode ở dạng UTF-8.
- Không thay đổi kiểu dữ liệu: number không biến thành string, boolean không biến thành chuỗi.
- Giữ null, array và nested object đúng cấu trúc.
- Không bỏ field chỉ vì giá trị đang rỗng.

Pretty-print chỉ thay đổi whitespace, không thay đổi ngữ nghĩa JSON. Tuy nhiên, mọi bước format cần được thực hiện nhất quán và không được làm lệch payload so với HTTP exchange.

## 6. Kết hợp JSON sample với request/response field table

Một section Markdown rõ ràng thường có:

1. Một đoạn giải thích mục đích payload.
2. JSON body snippet để người đọc xem giá trị mẫu.
3. Field table để tra cứu nghĩa của từng field.

Ví dụ:

### Request body

Client gửi thông tin khách hàng và mô tả đơn hàng:

~~~json
{
  "customerId": 42,
  "description": "Bàn phím",
  "note": "Giao vào buổi sáng"
}
~~~

### Request fields

| Path | Type | Description |
| --- | --- | --- |
| customerId | Number | Mã khách hàng |
| description | String | Mô tả đơn hàng |
| note | String | Ghi chú tùy chọn |

JSON cho thấy ví dụ cụ thể. Field table mô tả ý nghĩa và contract. Hai phần không trùng nhiệm vụ.

## 7. Tùy chỉnh template để tạo Markdown table

Nếu output mặc định của REST Docs là AsciiDoc, có thể:

- Dùng Asciidoctor để render snippet và tài liệu.
- Cấu hình template format Markdown nếu phiên bản REST Docs hỗ trợ.
- Tạo custom snippet template để định dạng field table theo chuẩn Markdown.
- Chuyển đổi AsciiDoc snippet sang Markdown bằng công cụ/build step có kiểm tra.

Không đổi đuôi .adoc thành .md bằng rename. Phần mở rộng không biến cú pháp AsciiDoc thành Markdown.

### 7.1. Template table cần giữ dữ liệu gì?

Một field table thường cần tối thiểu:

| Cột | Ý nghĩa |
| --- | --- |
| Path | Đường dẫn field trong payload |
| Type | Kiểu dữ liệu được suy ra hoặc chỉ định bởi REST Docs |
| Description | Ý nghĩa field do người viết descriptor cung cấp |
| Optional | Trạng thái tùy chọn nếu template hiển thị cột này |

Không phải template mặc định nào cũng có cột Optional riêng. Hãy xem output sinh ra và version đang dùng trước khi giải thích phụ thuộc vào cột đó.

Khi tạo custom template, chỉ escape ở bước render cell, không sửa descriptor nguồn. Nhờ vậy, cùng descriptor có thể được dùng bởi nhiều định dạng output.

## 8. Ghép table và JSON snippet vào Markdown

Markdown thuần không có cú pháp include file phổ quát. Dùng include plugin của static site generator nếu dự án có cấu hình, hoặc build-time assembly để tạo trang cuối.

Ví dụ cấu trúc:

~~~text
src/docs/markdown/
└── orders-create-intro.md

build/generated-snippets/orders-create/
├── http-request.md
├── http-response.md
├── request-body.md
├── response-body.md
├── request-fields.md
└── response-fields.md

build/docs-markdown/
└── orders-create.md
~~~

Trang cuối có thể ghép theo thứ tự:

~~~markdown
# Tạo đơn hàng

Client gửi thông tin khách hàng và mô tả đơn hàng.

## HTTP request

[Nội dung snippet http-request được chèn tại đây]

## Request JSON

[Nội dung snippet request-body được chèn tại đây]

## Request fields

[Nội dung snippet request-fields được chèn tại đây]

## HTTP response

[Nội dung snippet http-response được chèn tại đây]

## Response JSON

[Nội dung snippet response-body được chèn tại đây]

## Response fields

[Nội dung snippet response-fields được chèn tại đây]
~~~

Các dòng trong ngoặc vuông là vị trí minh họa, không phải include directive hoạt động. Build task/plugin phải thay chúng bằng fragment thật. Nếu http-request đã hiển thị body đủ rõ, có thể không cần section request-body riêng; tránh lặp nội dung.

### 8.1. Quy tắc assembly

Tác vụ ghép nội dung nên:

1. Chạy sau test đã sinh snippet.
2. Xác nhận mọi snippet bắt buộc đều tồn tại.
3. Đọc UTF-8 và giữ nguyên nội dung payload.
4. Thêm heading và dòng trống giữa các fragment.
5. Escape table cell nếu tự dựng bảng từ metadata.
6. Không bọc snippet có code fence trong fence ngoài cùng độ dài.
7. Ghi output vào build/, không ghi đè file nguồn trong src/.

## 9. Ví dụ task Gradle kiểm tra và ghép JSON/table

Ví dụ Groovy DSL sau minh họa việc ghép các fragment có sẵn. Giả định REST Docs đã sinh snippet Markdown với đúng tên:

~~~~groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')
def outputDir = layout.buildDirectory.dir('docs-markdown')

tasks.register('assembleOrderCreateMarkdown') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    outputs.file outputDir.map { it.file('orders-create.md') }

    doLast {
        def operationDir = new File(
            snippetsDir.get().asFile,
            'orders-create'
        )
        def files = [
            'http-request.md',
            'request-body.md',
            'request-fields.md',
            'http-response.md',
            'response-body.md',
            'response-fields.md'
        ]

        def snippets = files.collect { name ->
            new File(operationDir, name)
        }
        def missing = snippets.findAll { !it.isFile() }
        if (!missing.isEmpty()) {
            throw new GradleException(
                'Missing REST Docs snippets: ' +
                missing.collect { it.name }.join(', ')
            )
        }

        def headings = [
            '## HTTP request',
            '## Request JSON',
            '## Request fields',
            '## HTTP response',
            '## Response JSON',
            '## Response fields'
        ]
        def content = new StringBuilder('# Tạo đơn hàng\n\n')
        snippets.eachWithIndex { file, index ->
            content.append(headings[index])
                .append('\n\n')
                .append(file.getText('UTF-8').trim())
                .append('\n\n')
        }

        def target = outputDir.get().file('orders-create.md').asFile
        target.parentFile.mkdirs()
        target.setText(content.toString(), 'UTF-8')
    }
}
~~~~

Đây là task minh họa: chỉ dùng khi project thực sự sinh đủ sáu fragment Markdown nêu trên. Nếu REST Docs sinh .adoc, dùng Asciidoctor hoặc bước chuyển đổi rõ ràng. Nếu không cấu hình request-body/response-body, bỏ chúng khỏi danh sách và chỉ ghép http-request, request-fields, http-response, response-fields. Không tạo fragment giả để làm task pass.

## 10. Kiểm tra bảng và JSON sau khi render

Sau assembly, kiểm tra:

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| Số cột | Mỗi dòng table có cùng số cột |
| Pipe trong description | Không tạo cột phụ ngoài ý muốn |
| Backslash/backtick | Hiển thị đúng, không đóng code span sớm |
| Nội dung nhiều dòng | Đã chuyển sang section riêng hoặc định dạng renderer hỗ trợ |
| JSON syntax | Parse được và giữ kiểu dữ liệu |
| JSON source | Khớp payload test, không bị sửa thủ công |
| Unicode | Tiếng Việt không bị lỗi encoding |
| Code fence | Mở/đóng đúng; fence lồng nhau dùng delimiter ngoài dài hơn |
| Table source | Được sinh từ descriptor, không có bảng thủ công mâu thuẫn |

Có thể dùng JSON parser trong pipeline để xác thực file body snippet nếu fragment chỉ chứa JSON thuần. Nếu snippet có HTTP headers hoặc code fence bao quanh JSON, cần trích đúng vùng body trước khi parse.

### 10.1. Kiểm tra Markdown table

Một kiểm tra cơ bản nên phát hiện:

- Dòng header và separator có cùng số cột.
- Mọi dòng dữ liệu có cùng số cột sau khi tính đến escaped pipe.
- Bảng có dòng trống trước và sau khi cần thiết.
- Không có pipe chưa escape trong text cell nếu template không hỗ trợ.

Regex đơn giản có thể báo các trường hợp đáng ngờ nhưng không thay thế Markdown parser, vì pipe có thể nằm trong code span hoặc HTML. Với site quan trọng, hãy render bằng đúng generator và kiểm tra HTML kết quả.

## 11. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Bảng có thêm cột ngoài ý muốn | Description chứa pipe chưa escape | Escape pipe trong template cell |
| Dấu gạch chéo ngược biến mất | Escape sequence bị xử lý hai lần | Xác định rõ tầng escape và chỉ escape một lần |
| Backtick làm vỡ cell | Code span chứa delimiter không được xử lý | Dùng delimiter phù hợp hoặc escape theo renderer |
| Mô tả dài làm bảng khó đọc | Nhét nhiều dòng vào một cell | Giữ mô tả ngắn, chuyển ví dụ sang section riêng |
| JSON snippet khác payload HTTP | Copy hoặc format thủ công sau test | Dùng snippet generated làm nguồn chính |
| JSON không parse được | Fragment có HTTP wrapper hoặc bị ghép sai | Trích body đúng cách và kiểm tra JSON parser |
| JSON Unicode thành ký tự lỗi | Encoding không thống nhất | Dùng UTF-8 từ test đến renderer |
| Field table thiếu field | Descriptor chưa mô tả hết payload | Cập nhật descriptor hoặc relaxed fields có chủ đích |
| Bảng ghi optional sai | Nhầm optional với nullable | Test riêng field vắng mặt và field null |
| Markdown có directive chưa xử lý | Dùng cú pháp include không thuộc renderer | Dùng đúng plugin hoặc build-time assembly |
| Assembly báo thiếu request-body.md | Version/template không sinh snippet đó | Bỏ fragment không cấu hình hoặc cấu hình đúng template |
| Nội dung lặp hai lần | Ghép cả http-request và request-body mà không cần | Chọn snippet có giá trị bổ sung |

## 12. Bài thực hành

Tạo tài liệu cho endpoint:

~~~text
POST /api/orders
~~~

Request JSON:

~~~json
{
  "customerId": 42,
  "description": "Bàn phím | chuột",
  "note": "Giao hàng buổi sáng",
  "items": [
    {
      "sku": "KB-01",
      "quantity": 2
    }
  ]
}
~~~

Response JSON:

~~~json
{
  "id": 731,
  "status": "CREATED",
  "totalItems": 2
}
~~~

Yêu cầu:

1. Viết MockMvc test gửi request trên và assert response theo contract.
2. Dùng requestFields(...) mô tả customerId, description, note và items.
3. Dùng responseFields(...) mô tả id, status và totalItems.
4. Đảm bảo field description có dấu pipe hiển thị đúng trong Markdown field table.
5. Sinh HTTP request/response và field table từ cùng document identifier.
6. Nếu có request-body/response-body snippet, đưa vào section JSON riêng; nếu không có, dùng HTTP snippet và không giả định file tồn tại.
7. Ghép trang Markdown, render bằng đúng tool của dự án.
8. Kiểm tra JSON syntax, field table, code fence, UTF-8 và link trong CI.

**Tiêu chí hoàn thành:** bảng không vỡ cột do dấu pipe; JSON hợp lệ và khớp payload test; request/response snippet và field table không mâu thuẫn; trang cuối render đúng và có thể tái tạo từ test.

## Ghi nhớ

Field table và JSON snippet phục vụ hai mục đích khác nhau: JSON cho thấy payload mẫu, còn bảng mô tả schema và ý nghĩa field. Hãy sinh bảng từ requestFields(...)/responseFields(...), giữ JSON body đồng bộ với HTTP exchange, escape pipe và ký tự đặc biệt trong table cell, và chuyển phần nội dung nhiều dòng sang section riêng. Chỉ ghép những snippet thực sự được cấu hình sinh. Sau assembly, kiểm tra Markdown bằng renderer thực tế, xác thực JSON, code fence, UTF-8 và dữ liệu nhạy cảm rồi mới publish qua CI.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs Payload Documentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html), [Spring REST Docs Template Formats API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/templates/TemplateFormats.html) và [CommonMark Specification](https://commonmark.org/).
