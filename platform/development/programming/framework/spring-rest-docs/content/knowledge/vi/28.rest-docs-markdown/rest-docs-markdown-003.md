# Include snippet trong tài liệu Markdown

## Mục tiêu bài học

Spring REST Docs sinh các snippet từ bài kiểm thử HTTP. Khi nhóm phát triển xuất bản tài liệu bằng **Markdown**, cần đưa những snippet đã được kiểm chứng vào đúng vị trí trong trang để người đọc thấy request, response, payload, header và tham số cùng phần giải thích. Điểm cần nhớ là **Markdown thuần không định nghĩa cú pháp include file chuẩn**. Vì vậy, quy trình ghép snippet phải do công cụ tài liệu hoặc build của dự án đảm nhiệm.

Bài học thuộc chương **Markdown** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng bằng các bài kiểm thử HTTP với **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown và đưa vào quy trình build, CI.

Sau bài học, bạn có thể:

- Phân biệt cú pháp include của Asciidoctor với Markdown thuần.
- Chọn cách đưa snippet REST Docs vào trang Markdown.
- Cấu hình REST Docs sinh snippet theo template format Markdown nếu phiên bản hỗ trợ.
- Dùng chỉ thị include riêng của trình dựng tài liệu khi dự án có hỗ trợ.
- Ghép nội dung Markdown và snippet bằng tác vụ build có kiểm soát.
- Giữ snippet được sinh từ test, không chỉnh sửa thủ công trong thư mục output.
- Liên kết test, bước ghép tài liệu, kiểm tra liên kết và CI.

## 1. Vì sao cần cơ chế include?

Một bài REST Docs thường sinh nhiều file cho một operation, ví dụ:

~~~text
build/generated-snippets/
└── orders-get/
    ├── curl-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── path-parameters.adoc
    └── response-fields.adoc
~~~

Trang Markdown có thể chứa phần giải thích do người viết biên soạn:

~~~markdown
# Lấy đơn hàng theo ID

Endpoint trả về thông tin một đơn hàng.

## Request

## Path parameters

## Response
~~~

Các phần request/response/descriptor cần lấy từ snippet do test sinh ra. Nếu copy thủ công vào Markdown, nội dung có thể bị cũ sau khi API hoặc test thay đổi. Cơ chế include hoặc lắp ghép ở build giúp tài liệu luôn dùng snippet của lần kiểm thử hiện tại.

## 2. Markdown thuần không có cú pháp include chuẩn

Markdown quy định cách viết heading, paragraph, link, list, table và fenced code block. Nó không định nghĩa một chỉ thị phổ quát để đọc nội dung file khác. Ví dụ:

~~~text
include::build/generated-snippets/orders-get/http-request.adoc[]
~~~

là cú pháp **include của Asciidoctor**, không phải Markdown thuần. Một Markdown renderer thông thường sẽ hiển thị dòng này như văn bản hoặc xử lý theo quy tắc riêng; nó không tự mở file snippet.

Tương tự, các shortcode hoặc HTML comment như sau không phải cú pháp include chung:

~~~markdown
{{< include "orders-get/http-request.md" >}}
<!-- include: build/generated-snippets/orders-get/http-request.md -->
~~~

Một số nền tảng tài liệu có plugin hoặc directive riêng, nhưng chỉ hoạt động khi đúng công cụ dựng trang đã được cấu hình.

Trước khi chọn cách include, hãy xác định **Markdown được render ở đâu**:

| Môi trường tài liệu | Khả năng include |
| --- | --- |
| Markdown thuần, renderer cơ bản | Không có include file chuẩn |
| Asciidoctor | Có directive include trong tài liệu AsciiDoc |
| Static site generator | Có thể cung cấp include directive/plugin riêng |
| Tác vụ build tự ghép file | Có thể chèn snippet thành Markdown hoàn chỉnh trước khi render |
| Nền tảng quản lý tài liệu | Phụ thuộc extension và cách import nội dung |

Đừng thêm directive của một static site generator trước khi xác nhận dự án đang dùng generator đó.

## 3. Phương án thứ nhất: sinh snippet theo Markdown template format

Spring REST Docs tập trung vào việc tạo snippet từ operation đã kiểm thử. Các phiên bản hỗ trợ template format Markdown có thể sinh nội dung snippet ở định dạng Markdown thay vì AsciiDoc. Cần kiểm tra API và dependency version của dự án trước khi cấu hình.

Ví dụ cấu hình mặc định với template format Markdown, khi phiên bản REST Docs đang dùng cung cấp API tương ứng:

~~~java
import static org.springframework.restdocs.templates.TemplateFormats.markdown;

mockMvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(documentationConfiguration(restDocumentation)
        .snippets()
        .withTemplateFormat(markdown()))
    .build();
~~~

Đây là ví dụ định hướng cấu hình. Tên package, builder method và cách cấu hình phụ thuộc phiên bản Spring REST Docs. Hãy đối chiếu Javadoc của dependency đang dùng; không sao chép markdown() nếu phiên bản hiện tại không cung cấp template format đó. Một số dự án cấu hình template format ở snippet hoặc trong documentation configuration.

Khi dùng template format Markdown, snippet được sinh vẫn là **file fragment**. Việc chuyển từ AsciiDoc snippet sang Markdown snippet không tự động chèn fragment vào trang Markdown chính.

Ví dụ thư mục output có thể trở thành:

~~~text
build/generated-snippets/
└── orders-get/
    ├── http-request.md
    ├── http-response.md
    ├── path-parameters.md
    └── response-fields.md
~~~

Tên file và phần mở rộng cụ thể phụ thuộc snippet/template mà dự án cấu hình. Hãy kiểm tra output thực tế thay vì giả định mọi snippet luôn đổi phần mở rộng .adoc thành .md.

### 3.1. Khi nào chọn Markdown snippet?

Chọn Markdown snippet khi tài liệu cuối được render bằng Markdown renderer, template Markdown đáp ứng định dạng cần thiết, và dự án đã có cơ chế include/assembly fragment. Không chọn chỉ vì file đích có phần mở rộng .md; hãy xác nhận cả cách sinh snippet và cách lắp ghép.

## 4. Phương án thứ hai: dùng include directive của nền tảng Markdown

Một số công cụ dựng tài liệu mở rộng Markdown bằng directive hoặc plugin include. Khi dùng phương án này, quy trình có hai phần:

1. Cấu hình REST Docs sinh snippet dưới dạng Markdown hoặc chuyển snippet sang Markdown.
2. Dùng include directive đúng cú pháp của công cụ đang render trang.

Ví dụ minh họa một directive giả định theo nền tảng:

~~~markdown
## Request

<!-- include: build/generated-snippets/orders-get/http-request.md -->

## Response

<!-- include: build/generated-snippets/orders-get/http-response.md -->
~~~

Đoạn HTML comment trên chỉ là ví dụ, không phải cú pháp include hoạt động mặc định. Renderer phải có plugin hiểu và xử lý nó. Nếu không có plugin, comment có thể bị bỏ qua và snippet không xuất hiện.

Khi thiết lập include plugin:

- Xác nhận đường dẫn tương đối tính từ file nào hoặc thư mục gốc nào.
- Bảo đảm snippet đã tồn tại trước khi static site generator chạy.
- Kiểm tra plugin có cho phép include file bên ngoài thư mục content không.
- Tránh include file tùy ý từ filesystem nếu công cụ có giới hạn bảo mật.
- Xác định cách công cụ xử lý fenced code, HTML và link tương đối bên trong fragment.
- Kiểm tra trang render thực tế; directive còn nguyên trong source không chứng minh nội dung đã được include.

Không có một cú pháp duy nhất cho mọi Markdown renderer. Hãy dùng tài liệu của đúng generator/plugin trong dự án và ghi rõ yêu cầu đó trong build documentation.

## 5. Phương án thứ ba: build-time assembly

Nếu dự án muốn giữ Markdown tương thích rộng, có thể ghép phần tĩnh và snippet thành một file Markdown hoàn chỉnh trước khi render:

~~~text
src/docs/markdown/
├── orders-intro.md
└── customers-intro.md

build/generated-snippets/
└── orders-get/
    ├── http-request.md
    ├── http-response.md
    ├── path-parameters.md
    └── response-fields.md

build/docs-markdown/
└── orders.md
~~~

Tác vụ assembly đọc fragment theo thứ tự đã khai báo, chèn nội dung snippet và ghi file kết quả vào build/docs-markdown. Không ghi file sinh ra vào src/ vì mỗi lần build có thể tạo lại output.

### 5.1. Nội dung tĩnh

File src/docs/markdown/orders-intro.md:

~~~markdown
# Orders API

API quản lý đơn hàng.

## Lấy đơn hàng theo ID

Endpoint trả về một đơn hàng theo mã định danh.
~~~

Danh sách snippet cần ghép có thể được quản lý bằng manifest riêng của tác vụ build, ví dụ:

~~~text
SNIPPET: orders-get/path-parameters.md
SNIPPET: orders-get/http-request.md
SNIPPET: orders-get/response-fields.md
SNIPPET: orders-get/http-response.md
~~~

Manifest là đầu vào của assembly, không phải nội dung Markdown để công bố nguyên trạng.

### 5.2. Quy tắc assembly

Một tác vụ assembly tốt cần:

1. Chạy sau test sinh snippet.
2. Nhận danh sách file nguồn và snippet theo thứ tự xác định.
3. Báo lỗi rõ ràng khi snippet bắt buộc không tồn tại.
4. Giữ encoding UTF-8.
5. Chèn heading hoặc khoảng trắng phù hợp để fragment không dính vào nhau.
6. Ghi output vào thư mục build.
7. Không sửa nội dung test hoặc file snippet gốc.

Ví dụ kết quả cuối có thể có hình dạng:

~~~~markdown
# Orders API

API quản lý đơn hàng.

## Lấy đơn hàng theo ID

Endpoint trả về một đơn hàng theo mã định danh.

## Path parameters

| Name | Description |
| --- | --- |
| orderId | Mã đơn hàng |

## Request

~~~http
GET /api/orders/42
Accept: application/json
~~~

## Response

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"OPEN"}
~~~
~~~~

Đây là hình dạng minh họa của file cuối. Nội dung request, response và bảng descriptor trong sản phẩm thật phải lấy từ snippet REST Docs của lần build tương ứng, không viết tay như ví dụ.

## 6. Ví dụ tác vụ Gradle cho assembly

Có thể triển khai task Gradle riêng để ghép Markdown. Ví dụ sau minh họa cấu trúc task; điều chỉnh đường dẫn và tập snippet theo project:

~~~groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')
def markdownSourceDir = layout.projectDirectory.dir('src/docs/markdown')
def assembledDocsDir = layout.buildDirectory.dir('docs-markdown')

tasks.register('assembleMarkdownDocs') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    inputs.dir markdownSourceDir
    outputs.dir assembledDocsDir

    doLast {
        def outputDir = assembledDocsDir.get().asFile
        outputDir.mkdirs()

        def output = new File(outputDir, 'orders.md')
        def intro = new File(markdownSourceDir.asFile, 'orders-intro.md')
        def requestSnippet = new File(
            snippetsDir.get().asFile,
            'orders-get/http-request.md'
        )
        def responseSnippet = new File(
            snippetsDir.get().asFile,
            'orders-get/http-response.md'
        )

        [intro, requestSnippet, responseSnippet].each { file ->
            if (!file.isFile()) {
                throw new GradleException(
                    "Required documentation input not found: ${file}"
                )
            }
        }

        output.setText(
            intro.getText('UTF-8') +
            '\n\n## Request\n\n' +
            requestSnippet.getText('UTF-8') +
            '\n\n## Response\n\n' +
            responseSnippet.getText('UTF-8') +
            '\n',
            'UTF-8'
        )
    }
}
~~~

Task mẫu ghép ba file cố định để minh họa. Dự án thực tế nên quản lý snippet cần thiết trong cấu hình hoặc manifest, thay vì viết một task lớn chứa đường dẫn cho mọi operation. Nếu có nhiều trang API, khai báo output riêng cho từng trang và tránh hai task cùng ghi một file.

### 6.1. Nối task vào luồng build

Nếu có task render Markdown riêng, đặt dependency:

~~~groovy
tasks.named('renderMarkdownDocs') {
    dependsOn tasks.named('assembleMarkdownDocs')
}
~~~

Nếu dùng plugin tài liệu, nối assembleMarkdownDocs vào đúng task xử lý content của plugin đó. Không mặc định mọi plugin đều có task tên renderMarkdownDocs; tên task phụ thuộc công cụ đang dùng.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[HTTP tests: MockMvc / WebTestClient / REST Assured] --> B[Spring REST Docs generates snippets]
    B --> C[Validate required snippets]
    C --> D[Assemble Markdown pages]
    D --> E[Render Markdown site]
    E --> F[Check links and publish artifact]
~~~

## 7. Ví dụ test sinh snippet cho operation

Giả sử test MockMvc dùng document identifier orders-get:

~~~java
mockMvc.perform(get("/api/orders/{orderId}", 42L)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("orders-get",
        pathParameters(
            parameterWithName("orderId")
                .description("Mã đơn hàng cần tra cứu")
        ),
        responseFields(
            fieldWithPath("id").description("Mã đơn hàng"),
            fieldWithPath("status").description("Trạng thái đơn hàng")
        )
    ));
~~~

Với cấu hình template format Markdown phù hợp phiên bản, task assembly có thể nhận các fragment tương ứng. Nếu dự án vẫn dùng AsciiDoc snippet, không đổi đuôi file thành .md một cách thủ công. Cần chuyển đổi bằng công cụ hoặc cấu hình sinh đúng template trước khi assembly.

Phần test sinh snippet và phần assembly có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
| --- | --- |
| document("orders-get", ...) | Gắn snippet với operation đã kiểm thử |
| pathParameters(...) | Xác nhận và mô tả orderId |
| responseFields(...) | Xác nhận và mô tả field response |
| Template format | Quyết định định dạng snippet được sinh |
| Assembly task/include plugin | Đưa snippet vào trang Markdown |
| Markdown renderer | Chuyển Markdown cuối thành HTML hoặc định dạng đích |

## 8. Tổ chức snippet và đường dẫn

Một hệ thống tài liệu nên có quy ước đường dẫn ổn định:

~~~text
src/
└── docs/
    └── markdown/
        ├── orders-intro.md
        └── customers-intro.md

build/
├── generated-snippets/
│   ├── orders-get/
│   └── customer-get/
└── docs-markdown/
    ├── orders.md
    └── customers.md
~~~

Lưu ý:

- Document identifier là khóa để assembly tìm đúng snippet.
- Đổi identifier phải cập nhật manifest hoặc assembly references.
- Đường dẫn snippet là output build; không commit bản copy cũ như nguồn chân lý.
- Không include snippet từ operation khác chỉ vì tên file giống nhau.
- Nếu một snippet được dùng ở nhiều trang, xác định rõ trang nào là nguồn và trang nào tham chiếu.
- Nếu output được chia theo version API, đưa version vào đường dẫn hoặc identifier.

## 9. Link, ảnh và code fence trong fragment

Khi ghép snippet Markdown, cần tránh lỗi định dạng:

**Code fence:** snippet có thể chứa fenced code block. Trang assembly không nên đặt toàn bộ snippet bên trong một code fence khác, nếu không renderer sẽ hiển thị cả snippet như văn bản thuần.

**Heading:** nếu snippet template có heading riêng, kiểm tra cấp heading khi ghép để không phá cấu trúc TOC.

**Link và ảnh:** đường dẫn tương đối trong snippet có thể được tính từ file fragment hoặc trang cuối tùy công cụ. Kiểm tra rendered output để bảo đảm asset được tìm thấy.

**Encoding:** dùng UTF-8 cho Markdown nguồn và snippet. Nội dung tiếng Việt, JSON hoặc header có ký tự Unicode cần được render đúng.

**Khoảng trắng:** chèn dòng trống giữa các fragment để paragraph, table hoặc code block không nối liền nhau.

**Front matter:** nếu static site generator yêu cầu YAML front matter, chỉ thêm ở trang cuối theo quy ước của generator. Không lặp front matter của các fragment vào giữa trang.

## 10. Kiểm tra tài liệu sau khi ghép

Build thành công chưa chắc trang Markdown hiển thị đúng. Bước kiểm tra nên xác nhận:

1. Tất cả snippet bắt buộc tồn tại.
2. Trang cuối có request, response, parameters và fields đúng operation.
3. Không có dòng include của Asciidoctor bị để nguyên trong Markdown thuần.
4. Không còn chỉ thị include chưa được xử lý của plugin.
5. Code fence cân bằng và bảng không bị nối vào paragraph trước.
6. Link và asset tương đối hoạt động sau khi render.
7. Không có token, session ID hoặc dữ liệu test nhạy cảm trong snippet.
8. Nội dung được tái tạo từ lần chạy test hiện tại, không dùng file sinh từ build cũ.

Có thể kiểm tra file bắt buộc trước khi render. Ví dụ PowerShell:

~~~powershell
$required = @(
    'build/generated-snippets/orders-get/http-request.md',
    'build/generated-snippets/orders-get/http-response.md',
    'build/generated-snippets/orders-get/path-parameters.md'
)

$missing = $required | Where-Object { -not (Test-Path -LiteralPath $_) }
if ($missing.Count -gt 0) {
    throw "Missing REST Docs snippets: $($missing -join ', ')"
}
~~~

Điều chỉnh phần mở rộng theo output thực tế. Nếu snippet sinh ra là .adoc, bước kiểm tra không được âm thầm mong đợi .md.

## 11. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Markdown hiển thị nguyên dòng include | Dùng cú pháp Asciidoctor trong Markdown thuần | Dùng Asciidoctor renderer hoặc cơ chế include/assembly của Markdown |
| Include directive không chạy | Plugin/generator chưa cài hoặc chưa bật | Xác nhận đúng renderer và plugin |
| Snippet .adoc được include như .md | Nhầm template format hoặc đổi phần mở rộng thủ công | Cấu hình template Markdown hoặc chuyển đổi có kiểm soát |
| Trang thiếu request/response | Snippet chưa được sinh hoặc sai identifier | Kiểm tra document(...), output directory và manifest |
| Nội dung snippet cũ | Assembly chạy trước test hoặc tái sử dụng output cũ | Nối dependency test → assembly và làm mới output theo chiến lược build |
| Code fence bị vỡ | Lồng snippet trong fence khác hoặc fragment không cân bằng | Ghép nguyên fragment và kiểm tra rendered page |
| Bảng Markdown dính vào đoạn trước | Thiếu dòng trống khi nối fragment | Chèn newline có chủ đích giữa các fragment |
| Link/ảnh không tìm thấy | Base path thay đổi khi fragment được ghép | Chuẩn hóa đường dẫn asset tương đối |
| Include path hoạt động local nhưng hỏng CI | Phụ thuộc working directory hoặc đường dẫn tuyệt đối | Dùng path dựa trên project/build directory |
| Trang chứa token/session thật | HTTP snippet ghi lại giá trị test nhạy cảm | Dùng fixture giả và preprocessor; kiểm tra output |
| Assembler không báo snippet thiếu | Task bỏ qua file không tồn tại | Xem snippet bắt buộc là input và fail sớm khi thiếu |

## 12. Bài thực hành

Tài liệu hóa hai operation:

~~~text
GET /api/orders/{orderId}
POST /api/orders
~~~

Yêu cầu:

1. Viết MockMvc test sinh snippet cho hai operation với identifier orders-get và orders-create.
2. Mô tả path parameter cho GET và request/response fields cho POST.
3. Cấu hình REST Docs sinh Markdown snippet nếu phiên bản đang dùng hỗ trợ template format Markdown; nếu không, chọn một bước chuyển đổi rõ ràng.
4. Tạo trang nguồn orders-intro.md giải thích API.
5. Viết task assembly đưa http-request, http-response, path-parameters, request-fields và response-fields vào đúng section.
6. Làm build thất bại khi một snippet bắt buộc bị thiếu.
7. Render trang cuối và kiểm tra heading, code fence, table, link và UTF-8.
8. Nối test → assembly → renderer trong CI.

**Tiêu chí hoàn thành:** trang Markdown cuối chứa snippet do test sinh; không còn include directive chưa xử lý; nội dung được làm mới mỗi lần build; thiếu snippet làm pipeline thất bại; trang render không lỗi cấu trúc.

## Ghi nhớ

Markdown thuần không có cú pháp include file chuẩn. Spring REST Docs có thể sinh snippet theo template format phù hợp với phiên bản, nhưng fragment vẫn cần được đưa vào trang cuối bằng include plugin của nền tảng hoặc build-time assembly. Không dùng include::...[] của Asciidoctor như thể mọi Markdown renderer đều hiểu nó. Hãy nối test sinh snippet với bước assemble/render, kiểm tra file bắt buộc, code fence, link, encoding và dữ liệu nhạy cảm trước khi xuất bản. Như vậy nội dung Markdown được ghép từ đúng bằng chứng do test HTTP tạo ra.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs Template Formats API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/templates/TemplateFormats.html), [Asciidoctor include directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/) và [CommonMark Specification](https://commonmark.org/).
