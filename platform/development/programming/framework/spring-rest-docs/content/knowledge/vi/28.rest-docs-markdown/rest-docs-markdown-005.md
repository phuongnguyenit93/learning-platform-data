# Nhúng request, response và field table

## Mục tiêu bài học

Spring REST Docs tạo snippet từ các bài kiểm thử HTTP. Một trang API bằng **Markdown** thường cần bốn phần bằng chứng: HTTP request, HTTP response, bảng mô tả field request và bảng mô tả field response. Ghép đúng các phần này giúp người đọc hiểu cách gọi endpoint, payload phải gửi và dữ liệu sẽ nhận.

Bài học thuộc chương **Markdown** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng bằng test HTTP với **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown rồi tích hợp vào build và CI.

Sau bài học, bạn có thể:

- Xác định snippet cần có để mô tả một operation.
- Phân biệt **http-request**, **http-response**, **request-fields** và **response-fields**.
- Tạo field table từ descriptor được kiểm chứng bằng test.
- Đưa bốn loại snippet vào đúng section của trang Markdown.
- Chọn include plugin hoặc build-time assembly phù hợp với renderer.
- Kiểm tra code fence, table, JSON, content type và dữ liệu nhạy cảm sau khi ghép.
- Nối test sinh snippet với bước render Markdown trong CI.

## 1. Bốn thành phần của một trang API operation

Giả sử có endpoint lấy và tạo đơn hàng. Một trang tài liệu hoàn chỉnh có thể trình bày:

| Thành phần | Snippet REST Docs thường dùng | Nội dung |
| --- | --- | --- |
| HTTP request | **http-request** | Method, URI, request headers và body đã ghi nhận |
| HTTP response | **http-response** | Status, response headers và body |
| Bảng field request | **request-fields** | Tên field, kiểu, mô tả và trạng thái optional/constraints nếu template hỗ trợ |
| Bảng field response | **response-fields** | Tên field trong response, kiểu và ý nghĩa theo descriptor |

REST Docs mặc định thường sinh file AsciiDoc. Khi cấu hình template format Markdown hoặc template riêng, phần mở rộng và cấu trúc file có thể khác. Ví dụ tên dưới đây minh họa bốn fragment dạng Markdown:

~~~text
build/generated-snippets/
└── orders-create/
    ├── http-request.md
    ├── http-response.md
    ├── request-fields.md
    └── response-fields.md
~~~

Không đổi đuôi .adoc thành .md bằng thao tác rename. Nội dung phải được render bằng đúng template Markdown hoặc chuyển đổi qua một bước có kiểm soát.

## 2. Hiểu vai trò của từng snippet

### 2.1. HTTP request: cách client gọi endpoint

Snippet **http-request** trả lời:

- Dùng HTTP method nào?
- Gọi URI nào và truyền path/query parameter ra sao?
- Cần header nào như **Content-Type** hoặc **Accept**?
- Body gửi lên có cấu trúc và giá trị như thế nào?

Ví dụ hình dạng nội dung:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "customerId": 42,
  "description": "Bàn phím"
}
~~~

Đây là ví dụ minh họa; snippet thực tế phải lấy từ operation test. Nếu test gửi token, cookie hoặc dữ liệu cá nhân, cần dùng fixture giả hoặc preprocessing trước khi ghi snippet.

### 2.2. HTTP response: kết quả server trả về

Snippet **http-response** cho biết status, headers và response body:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/731

{
  "id": 731,
  "status": "CREATED"
}
~~~

Người đọc biết request tạo tài nguyên mới, status là **201 Created**, và URI tài nguyên nằm trong **Location**. Nếu API có lỗi nghiệp vụ, nên có operation hoặc test riêng để tài liệu hóa response lỗi.

### 2.3. request-fields: bảng mô tả body client gửi

Snippet **request-fields** được tạo từ **requestFields(...)** và các **fieldWithPath(...)**. Bảng thường mô tả đường dẫn field, kiểu dữ liệu và ý nghĩa.

| Path | Type | Description |
| --- | --- | --- |
| customerId | Number | Mã khách hàng sở hữu đơn hàng |
| description | String | Mô tả ngắn của đơn hàng |

Các cột cụ thể phụ thuộc template snippet. Descriptor là nguồn cho bảng này; không nên tự viết một bảng khác với mô tả không còn khớp test.

### 2.4. response-fields: bảng mô tả body server trả

Snippet **response-fields** được tạo từ **responseFields(...)**:

| Path | Type | Description |
| --- | --- | --- |
| id | Number | Mã định danh đơn hàng được tạo |
| status | String | Trạng thái hiện tại của đơn hàng |

Khi response có nested object hoặc array, dùng path theo cú pháp field của REST Docs, ví dụ **customer.name** hoặc **items[].sku**. Hãy xác nhận path với payload thật và mô tả đầy đủ cấu trúc mà client cần dùng.

## 3. Tạo field table từ test descriptor

Không tự viết request/response field table rồi xem đó là bằng chứng kiểm thử. Hãy khai báo descriptor trong **document(...)** để REST Docs đối chiếu với payload của operation.

Ví dụ MockMvc test:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerId": 42,
              "description": "Bàn phím"
            }
            """))
    .andExpect(status().isCreated())
    .andDo(document("orders-create",
        requestFields(
            fieldWithPath("customerId")
                .description("Mã khách hàng sở hữu đơn hàng"),
            fieldWithPath("description")
                .description("Mô tả ngắn của đơn hàng")
        ),
        responseFields(
            fieldWithPath("id")
                .description("Mã định danh đơn hàng được tạo"),
            fieldWithPath("status")
                .description("Trạng thái hiện tại của đơn hàng")
        )
    ));
~~~

Các static import thường dùng:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
~~~

Đoạn test minh họa vị trí descriptor. Trong test chạy thật, controller phải trả JSON response tương ứng với hai field **id** và **status**, và assertion nên xác nhận status/body theo contract. Khi dùng strict field descriptors, REST Docs giúp phát hiện field thực tế chưa được tài liệu hóa hoặc descriptor không khớp payload.

### 3.1. Field tùy chọn và nested field

Nếu request có field tùy chọn, mô tả rõ:

~~~java
requestFields(
    fieldWithPath("customerId")
        .description("Mã khách hàng"),
    fieldWithPath("description")
        .description("Mô tả đơn hàng"),
    fieldWithPath("note")
        .optional()
        .description("Ghi chú bổ sung, có thể bỏ qua")
)
~~~

Với nested JSON:

~~~java
requestFields(
    fieldWithPath("customer.id")
        .description("Mã khách hàng"),
    fieldWithPath("customer.name")
        .description("Tên khách hàng"),
    fieldWithPath("items[].sku")
        .description("Mã sản phẩm trong từng dòng đơn hàng"),
    fieldWithPath("items[].quantity")
        .description("Số lượng của từng sản phẩm")
)
~~~

Không dùng **optional()** để hợp thức hóa một field luôn bắt buộc trong API. Descriptor phải phản ánh schema và validation thực tế.

### 3.2. Response có nested object hoặc array

Ví dụ response:

~~~json
{
  "id": 731,
  "customer": {
    "id": 42,
    "name": "Lan"
  },
  "items": [
    {
      "sku": "KB-01",
      "quantity": 1
    }
  ]
}
~~~

Descriptor:

~~~java
responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("customer.id").description("Mã khách hàng"),
    fieldWithPath("customer.name").description("Tên khách hàng"),
    fieldWithPath("items[].sku").description("Mã sản phẩm"),
    fieldWithPath("items[].quantity").description("Số lượng")
)
~~~

Nếu cần tài liệu hóa object cha như **customer** hoặc **items**, cân nhắc **subsectionWithPath(...)** theo khả năng của REST Docs version đang dùng. Tránh mô tả cùng một vùng JSON ở cấp cha và cấp con theo cách khiến descriptor chồng lấn.

## 4. Đưa bốn snippet vào trang Markdown

Markdown thuần không có cú pháp include file phổ quát. Vì vậy, có hai cách triển khai thường gặp:

1. Dùng include directive của static site generator/plugin mà dự án thực sự đang sử dụng.
2. Tạo task **build-time assembly** để ghép các fragment thành một file Markdown hoàn chỉnh trước khi render.

Nếu snippet còn là AsciiDoc, có thể tiếp tục dùng Asciidoctor để render tài liệu, hoặc chuyển đổi snippet sang Markdown bằng quy trình riêng. Không đặt **include::...[]** của Asciidoctor vào Markdown rồi kỳ vọng mọi renderer hiểu.

### 4.1. Cấu trúc thư mục đề xuất

~~~text
src/docs/markdown/
└── orders-intro.md

build/generated-snippets/
└── orders-create/
    ├── http-request.md
    ├── http-response.md
    ├── request-fields.md
    └── response-fields.md

build/docs-markdown/
└── orders.md
~~~

File **orders-intro.md** chứa phần giải thích do nhóm biên soạn:

~~~markdown
# Orders API

API cho phép tạo và tra cứu đơn hàng.

## Tạo đơn hàng

Client gửi thông tin khách hàng và mô tả đơn hàng. Server trả về mã đơn hàng cùng trạng thái ban đầu.
~~~

Task assembly ghép nội dung tĩnh với bốn snippet theo đúng thứ tự. File trong **build/docs-markdown** là output để render hoặc publish; không sửa snippet trong **build/generated-snippets** bằng tay.

### 4.2. Hình dạng trang Markdown sau assembly

~~~~markdown
# Orders API

API cho phép tạo và tra cứu đơn hàng.

## Tạo đơn hàng

Client gửi thông tin khách hàng và mô tả đơn hàng.

### HTTP request

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"customerId":42,"description":"Bàn phím"}
~~~

### Request fields

| Path | Type | Description |
| --- | --- | --- |
| customerId | Number | Mã khách hàng |
| description | String | Mô tả đơn hàng |

### HTTP response

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":731,"status":"CREATED"}
~~~

### Response fields

| Path | Type | Description |
| --- | --- | --- |
| id | Number | Mã đơn hàng |
| status | String | Trạng thái |
~~~~

Đây là ví dụ hình dạng trang, không phải snippet REST Docs được tạo trong repository. Khi triển khai, bốn phần phải được đọc từ output thật của test.

## 5. Tác vụ Gradle ghép bốn snippet

Ví dụ task dưới đây giả định test sinh snippet Markdown với đúng tên file đã nêu, phần giới thiệu ở **src/docs/markdown/orders-intro.md** và dự án dùng Gradle Groovy DSL:

~~~~groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')
def sourceDir = layout.projectDirectory.dir('src/docs/markdown')
def outputDir = layout.buildDirectory.dir('docs-markdown')

tasks.register('assembleOrdersMarkdown') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    inputs.file(sourceDir.file('orders-intro.md'))
    outputs.dir outputDir

    doLast {
        def intro = sourceDir.file('orders-intro.md').asFile
        def operationDir = new File(
            snippetsDir.get().asFile,
            'orders-create'
        )
        def names = [
            'http-request.md',
            'request-fields.md',
            'http-response.md',
            'response-fields.md'
        ]
        def headings = [
            '### HTTP request',
            '### Request fields',
            '### HTTP response',
            '### Response fields'
        ]
        def snippets = names.collect { name ->
            new File(operationDir, name)
        }

        def missing = ([intro] + snippets).findAll { !it.isFile() }
        if (!missing.isEmpty()) {
            throw new GradleException(
                'Required documentation inputs not found: ' +
                missing.collect { it.path }.join(', ')
            )
        }

        def result = new StringBuilder()
        result.append(intro.getText('UTF-8').trim()).append('\n\n')
        snippets.eachWithIndex { file, index ->
            result.append(headings[index])
                .append('\n\n')
                .append(file.getText('UTF-8').trim())
                .append('\n\n')
        }

        def destination = outputDir.get().file('orders.md').asFile
        destination.parentFile.mkdirs()
        destination.setText(result.toString(), 'UTF-8')
    }
}
~~~~

Task mẫu ghép một operation để dễ đọc. Với nhiều operation, nên quản lý snippet trong manifest hoặc cấu trúc dữ liệu gồm heading, identifier và danh sách file; tránh nhân bản task gần giống nhau. Kiểm tra cú pháp Gradle theo wrapper của dự án trước khi tích hợp.

### 5.1. Nếu dùng Markdown include plugin

Với plugin include cụ thể, thay task assembly bằng directive mà plugin hỗ trợ. Ví dụ minh họa vị trí mong muốn; comment không phải directive hoạt động mặc định:

~~~markdown
### HTTP request

<!-- plugin-specific include for orders-create/http-request.md -->

### Request fields

<!-- plugin-specific include for orders-create/request-fields.md -->

### HTTP response

<!-- plugin-specific include for orders-create/http-response.md -->

### Response fields

<!-- plugin-specific include for orders-create/response-fields.md -->
~~~

Đọc tài liệu của renderer/plugin để dùng đúng cú pháp, cách phân giải path và điều kiện bảo mật. Kiểm tra HTML sinh ra để xác nhận fragment đã thực sự được include.

## 6. Cấu hình REST Docs sinh snippet

### 6.1. Markdown template format

Nếu phiên bản Spring REST Docs trong dự án hỗ trợ template format Markdown, cấu hình format này cho snippet:

~~~java
import static org.springframework.restdocs.templates.TemplateFormats.markdown;

mockMvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(documentationConfiguration(restDocumentation)
        .snippets()
        .withTemplateFormat(markdown()))
    .build();
~~~

Đây là ví dụ theo API có thể khác giữa các phiên bản. Hãy kiểm tra Javadoc của dependency đang cài trước khi dùng **TemplateFormats.markdown()** và **withTemplateFormat(...)**. Nếu version không hỗ trợ, có thể dùng custom snippet templates hoặc chuyển đổi AsciiDoc sang Markdown bằng một bước đã được kiểm tra.

Template format quyết định cách mỗi snippet được render. Nó không tự ghép bốn fragment vào trang **orders.md**.

### 6.2. Snippet tiêu chuẩn và snippet tùy chỉnh

Khi custom template:

- Giữ tên field và ý nghĩa descriptor.
- Không bỏ qua field chưa được mô tả để làm tài liệu trông hoàn chỉnh giả tạo.
- Giữ phần request/response có đủ thông tin HTTP cần thiết.
- Đảm bảo Markdown table escape ký tự **|** trong nội dung nếu xuất hiện.
- Kiểm tra code fence khi body chứa Markdown hoặc code sample lồng nhau.

Nếu thay đổi template, test vẫn phải kiểm tra dữ liệu operation; template chỉ điều khiển cách hiển thị.

## 7. Kiểm tra request, response và field table

Trước khi publish, kiểm tra mỗi trang operation:

| Kiểm tra | Điều cần xác nhận |
| --- | --- |
| Request snippet | Method, URI, headers và body đúng test |
| Request fields | Mọi field cần thiết đã có descriptor |
| Response snippet | Status, headers và body đúng contract |
| Response fields | Tên, kiểu và mô tả field đúng payload |
| Required/optional | Field optional được đánh dấu đúng; field bắt buộc không bị bỏ sót |
| Nested fields | Path object/array khớp JSON thực tế |
| Content type | JSON/XML/form body được mô tả đúng kiểu |
| Dữ liệu nhạy cảm | Không có token, session ID hoặc PII thật |

Một lỗi thường gặp là request-fields table có đủ field nhưng request body trong snippet lại lấy từ test cũ. Đảm bảo tất cả snippet cho một operation được tạo từ cùng một execution và identifier, không trộn file của hai test hoặc hai phiên bản API.

### 7.1. Kiểm tra descriptor không thừa/thiếu

Với REST Docs field descriptors, kiểm tra strict giúp phát hiện:

- Field thực tế trong payload chưa được tài liệu hóa.
- Descriptor khai báo field không tồn tại.
- Field optional bị mô tả nhầm là bắt buộc hoặc ngược lại.
- JSON structure thay đổi nhưng field table chưa cập nhật.

Nếu API cho phép field động hoặc metadata bổ sung, cân nhắc **subsectionWithPath(...)** hoặc relaxed fields phù hợp; chỉ dùng relaxed descriptor khi có chủ đích và giải thích rõ phần payload không được mô tả chi tiết.

## 8. Lỗi định dạng khi nhúng snippet

**Code fence:** Không bọc một snippet đã có fenced code block trong fence khác cùng độ dài. Nếu trang assembly cần minh họa Markdown có code fence bên trong, dùng fence ngoài dài hơn fence trong.

**Table:** Chừa dòng trống trước và sau bảng. Nếu description có dấu **|**, escape theo quy tắc Markdown hoặc template phù hợp.

**JSON:** Giữ nguyên JSON snippet; không tự pretty-print hoặc sửa response body sau khi test đã sinh, trừ khi bước transform được quản lý và kiểm tra rõ.

**Heading:** Bốn fragment thường không cần heading riêng nếu template chỉ tạo nội dung bảng/code. Đặt heading ở trang chính để tránh TOC lặp hoặc sai cấp.

**Path:** Link/ảnh bên trong fragment có thể được tính từ vị trí fragment hoặc trang cuối tùy renderer. Kiểm tra rendered page thay vì chỉ xem source.

**UTF-8:** Giữ encoding UTF-8 qua test, snippet, assembly và renderer để nội dung tiếng Việt và JSON Unicode hiển thị đúng.

## 9. Tích hợp test → assembly → render trong CI

Luồng build nên có thứ tự:

~~~mermaid
flowchart TD
    A["Run HTTP tests"] --> B["REST Docs generates four snippets"]
    B --> C["Validate snippets exist"]
    C --> D["Assemble Markdown page"]
    D --> E["Render Markdown"]
    E --> F["Check links, tables and code fences"]
    F --> G["Publish documentation artifact"]
~~~

Task assembly phải phụ thuộc vào test. Renderer phải phụ thuộc assembly. Bước publish chỉ chạy khi tất cả kiểm tra trước đó thành công.

Với Gradle:

~~~groovy
tasks.named('assembleOrdersMarkdown') {
    dependsOn tasks.named('test')
}

tasks.named('renderMarkdownDocs') {
    dependsOn tasks.named('assembleOrdersMarkdown')
}
~~~

Tên **renderMarkdownDocs** là ví dụ; thay bằng task thực tế của static site generator hoặc công cụ tài liệu. Không khai báo dependency vòng tròn giữa test, assembly và renderer.

Trong CI, thêm kiểm tra:

1. Tất cả file **http-request**, **http-response**, **request-fields**, **response-fields** bắt buộc đều tồn tại.
2. Trang Markdown cuối có đủ bốn section cho từng operation.
3. Không còn directive include chưa được xử lý.
4. Link nội bộ và asset resolve được.
5. Không có giá trị nhạy cảm trong request/response snippet.
6. Artifact cuối được tạo từ output của cùng lần chạy test.

## 10. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Có HTTP request nhưng thiếu request-fields table | Chưa khai báo **requestFields(...)** hoặc assembly bỏ snippet | Thêm descriptor và đưa fragment vào manifest |
| Field table không khớp payload | Descriptor cũ hoặc operation identifier bị dùng nhầm | Kiểm tra test, JSON và document ID |
| Response body đúng nhưng thiếu response-fields | Chưa khai báo **responseFields(...)** | Thêm descriptor cho field response |
| Markdown hiển thị nguyên include directive | Dùng cú pháp Asciidoctor trong renderer Markdown thuần | Dùng plugin include đúng nền tảng hoặc assembly |
| Snippet .adoc bị nhúng như Markdown | Chưa cấu hình Markdown template/chuyển đổi | Chuyển đổi có kiểm soát hoặc render bằng Asciidoctor |
| Bảng vỡ cột | Description có ký tự **|** chưa escape | Sửa template hoặc escape ký tự |
| JSON bị hiển thị thành văn bản khó đọc | Template hoặc snippet không format body | Chọn template phù hợp; giữ output đồng bộ với test |
| Snippet của hai test bị trộn | Dùng chung identifier hoặc output cũ | Dùng ID duy nhất và quản lý output theo operation |
| Trang có field trùng lặp | Ghép cả bảng thủ công và snippet generated | Chỉ chọn một nguồn field table |
| CI không tìm thấy snippet | Assembly chạy trước test hoặc path sai | Thiết lập task dependency và validate path |
| Trang lộ token/session | HTTP snippet ghi lại giá trị test thật | Dùng fixture giả hoặc preprocessing; rà soát output |

## 11. Bài thực hành

Tài liệu hóa operation tạo đơn hàng:

~~~text
POST /api/orders
~~~

Request:

~~~json
{
  "customerId": 42,
  "description": "Bàn phím"
}
~~~

Response:

~~~json
{
  "id": 731,
  "status": "CREATED"
}
~~~

Yêu cầu:

1. Viết MockMvc test gửi request và assert status/response body.
2. Khai báo **requestFields(...)** cho **customerId**, **description**.
3. Khai báo **responseFields(...)** cho **id**, **status**.
4. Sinh **http-request**, **http-response**, **request-fields**, **response-fields** cho cùng document identifier.
5. Cấu hình Markdown template hoặc chuyển đổi snippet theo quy trình rõ ràng.
6. Ghép bốn snippet vào trang **orders.md** theo thứ tự: request, request fields, response, response fields.
7. Làm assembly thất bại nếu bất kỳ fragment bắt buộc nào bị thiếu.
8. Render trang và kiểm tra table, JSON code fence, heading, UTF-8 và link.
9. Nối test → assembly → render vào CI.

**Tiêu chí hoàn thành:** bốn fragment được sinh từ cùng operation test; field table khớp payload; request và response thể hiện đúng HTTP exchange; trang Markdown cuối được render không lỗi và được tái tạo trong CI.

## Ghi nhớ

Một trang operation thường cần bốn bằng chứng: **http-request**, **request-fields**, **http-response** và **response-fields**. HTTP snippet cho thấy trao đổi thực tế; field snippet mô tả schema qua descriptor đã được REST Docs kiểm chứng. Hãy khai báo **requestFields(...)** và **responseFields(...)** trong cùng operation test, rồi đưa fragment vào section tương ứng của trang Markdown bằng plugin include hoặc build-time assembly. Kiểm tra đủ snippet, field path, code fence, bảng và dữ liệu nhạy cảm trước khi render/publish. Nối test → assembly → renderer trong CI để tài liệu luôn đồng bộ với contract được kiểm thử.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs Payload Documentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html), [Spring REST Docs Template Formats API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/templates/TemplateFormats.html), [Asciidoctor include directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/) và [CommonMark Specification](https://commonmark.org/).
