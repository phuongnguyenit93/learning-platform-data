# Cấu hình Spring REST Docs để dùng Markdown

## 1. Mục tiêu bài học

Spring REST Docs mặc định sinh snippet ở định dạng Asciidoctor. Nếu dự án sử dụng Markdown làm định dạng tài liệu chính, có thể cấu hình Spring REST Docs sinh **Markdown snippets trực tiếp** bằng template format dựng sẵn. HTTP tests vẫn tạo request/response; descriptors vẫn mô tả và kiểm tra payload; chỉ định dạng file snippet thay đổi.

Bài học thuộc chương **Markdown** của module **SPRING_REST_DOCS**. Module tạo tài liệu REST API có thể kiểm chứng từ HTTP tests dùng MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; rồi biên soạn tài liệu và đưa vào build/CI.

Sau bài học, bạn có thể chọn Markdown format, cấu hình từng HTTP client, hiểu output files và custom templates, ghép snippet vào trang cuối và kiểm tra pipeline.

> Markdown snippets không tự tạo website API hoàn chỉnh. Bạn vẫn cần nội dung hướng dẫn, công cụ ghép snippet, Markdown renderer và bước publish.

## 2. Template format Markdown

Spring REST Docs có hai template format dựng sẵn:

| Format | ID | Extension |
| --- | --- | --- |
| Asciidoctor | `asciidoctor` | `.adoc` |
| Markdown | `markdown` | `.md` |

Cấu hình định dạng Markdown qua:

~~~java
.snippets().withTemplateFormat(TemplateFormats.markdown())
~~~

Đây là thiết lập trên `RestDocumentationConfigurer`. Nó đổi cách render snippets, không đổi cách test gửi request, nhận response hay khai báo descriptors.

Sáu snippets mặc định của các bản hiện đại gồm `curl-request`, `http-request`, `http-response`, `httpie-request`, `request-body` và `response-body`. Các bảng `request-fields`, `response-fields`, `path-parameters`, `query-parameters` và headers chỉ sinh khi test khai báo descriptors thích hợp.

## 3. Cấu hình với MockMvc

Dependencies minh họa cho Spring Boot 3.x, JUnit 5, Java 17+:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Dùng JUnit 5 extension và chọn Markdown format khi tạo MockMvc:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.restdocs.templates.TemplateFormats;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class MarkdownDocumentationTest {
    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
            .apply(documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.markdown()))
            .build();
    }
}
~~~

Test sinh snippet:

~~~java
@Test
void documentGetOrder() throws Exception {
    this.mockMvc.perform(get("/api/orders/101")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(101))
        .andDo(document("orders-get",
            responseFields(
                fieldWithPath("id").description("Mã đơn hàng"),
                fieldWithPath("status").description("Trạng thái đơn hàng"),
                fieldWithPath("total").description("Tổng tiền theo VND")
            )
        ));
}
~~~

Ví dụ giả định endpoint và fixture trả JSON có đúng các field được mô tả. Cần imports và test context phù hợp. Nếu dùng `@AutoConfigureRestDocs`, có thể cấu hình thông qua customizer tương ứng với Spring Boot version; hãy bảo đảm đúng MockMvc instance đang được test sử dụng đã gắn Markdown configurer.

Output ví dụ:

~~~text
build/
└── generated-snippets/
    └── orders-get/
        ├── curl-request.md
        ├── httpie-request.md
        ├── http-request.md
        ├── http-response.md
        ├── request-body.md
        ├── response-body.md
        └── response-fields.md
~~~

Output directory phụ thuộc context/configuration. Body snippets có thể rỗng nếu operation không có body; response-fields chỉ sinh khi khai báo `responseFields(...)`.

## 4. Cấu hình với WebTestClient

Với Spring WebFlux, gắn Markdown format vào documentation filter:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.restdocs.templates.TemplateFormats;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class WebFluxMarkdownDocumentationTest {
    @Autowired
    private ApplicationContext context;

    private WebTestClient webTestClient;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.webTestClient = WebTestClient.bindToApplicationContext(this.context)
            .configureClient()
            .filter(documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.markdown()))
            .build();
    }
}
~~~

Test:

~~~java
webTestClient.get()
    .uri("/api/orders/101")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo(101)
    .consumeWith(document("orders-get-webflux",
        responseFields(
            fieldWithPath("id").description("Mã đơn hàng"),
            fieldWithPath("status").description("Trạng thái"),
            fieldWithPath("total").description("Tổng tiền")
        )
    ));
~~~

Dùng dependency `spring-restdocs-webtestclient`. Ví dụ bind vào ApplicationContext; nếu dự án bind tới server hoặc client khác, đặt filter trên đúng client được test sử dụng.

## 5. Cấu hình với REST Assured

REST Assured sử dụng filter của REST Docs. Chọn Markdown format trong RequestSpecification:

~~~java
RequestSpecification specification =
    new RequestSpecBuilder()
        .addFilter(documentationConfiguration(restDocumentation)
            .snippets()
            .withTemplateFormat(TemplateFormats.markdown()))
        .build();
~~~

Test:

~~~java
given(specification)
    .filter(document("orders-get-restassured"))
    .accept("application/json")
.when()
    .get("/api/orders/101")
.then()
    .statusCode(200);
~~~

Specification phải được cấu hình server/base URI, port và REST Docs context. Filter có thể ghi operation sau khi nhận response nhưng trước khi assertions cuối hoàn tất; CI chỉ publish khi toàn bộ test suite PASS.

## 6. Định dạng nội dung snippet

Ví dụ nội dung Markdown của HTTP request snippet:

~~~http
GET /api/orders/101 HTTP/1.1
Accept: application/json
~~~

Ví dụ bảng response fields:

~~~markdown
|Path|Type|Description|
|---|---|---|
|id|Number|Mã đơn hàng|
|status|String|Trạng thái đơn hàng|
|total|Number|Tổng tiền theo VND|
~~~

Các bảng Markdown mặc định sử dụng cú pháp **Markdown Extra**. Không phải parser Markdown tối giản nào cũng hỗ trợ bảng; hãy xác nhận renderer/site generator thực tế.

REST Docs sinh các phần có thể kiểm chứng. Nội dung viết tay vẫn cần giải thích mục đích endpoint, authentication, quy tắc nghiệp vụ, trình tự thao tác, giới hạn và lỗi thường gặp.

## 7. Tổ chức output và identifier

Identifier nên ổn định, mô tả resource và scenario, đồng thời phân biệt success/error. Ví dụ `orders-get-success` và `orders-get-not-found`. Không dùng lại một identifier cho hai operation khác nhau trong cùng output set.

Cấu trúc thư mục có thể gồm:

~~~text
build/generated-snippets/
├── orders-get-success/
├── orders-get-not-found/
├── orders-create/
└── orders-search/
~~~

Với nhiều test modules, thống nhất output directory hoặc quy tắc merge rõ ràng để tránh các task ghi đè snippet của nhau.

## 8. Custom Markdown templates

Spring REST Docs dùng Mustache templates. Khi chọn Markdown, template được nạp theo format ID `markdown` từ package:

~~~text
org/springframework/restdocs/templates/markdown/
~~~

Ví dụ file template:

~~~text
src/test/resources/org/springframework/restdocs/templates/markdown/
├── http-response.snippet
└── response-fields.snippet
~~~

Muốn override snippet:

1. Lấy template gốc đúng version Spring REST Docs đang dùng.
2. Đặt template cùng tên trong package Markdown của test resources.
3. Chỉ thay phần cần thiết, giữ các variables/snippet attributes quan trọng.
4. Chạy test để xác minh template override được nạp.
5. So output trước/sau để phát hiện field bị mất hoặc escaping sai.

Không copy template Asciidoctor sang package Markdown vì cú pháp bảng, code fence và escaping khác nhau.

Có thể gắn metadata vào field descriptor rồi tùy chỉnh template để thêm cột riêng, ví dụ cột Constraint. Attribute do dự án đặt tên không tự hiển thị trong template mặc định nếu template không đọc nó.

## 9. Ghép Markdown snippets vào tài liệu cuối

Markdown không định nghĩa cú pháp chuẩn để include một file Markdown vào file khác. Sinh Markdown snippets và ghép chúng vào trang cuối là hai bước riêng.

Có thể dùng:

- Slate hoặc static site generator hỗ trợ include/partials.
- Plugin include cho hệ thống Markdown đang dùng.
- Build task tùy chỉnh đọc snippets và ghép vào trang theo template.
- Bước preprocess tạo trang Markdown hoàn chỉnh trước khi renderer chạy.

Ví dụ trang cuối ở mức khái niệm:

~~~markdown
# Orders API

## Lấy đơn hàng

Endpoint trả thông tin đơn hàng theo ID.

### HTTP request
Nội dung được ghép từ snippet orders-get-success/http-request.md.

### HTTP response
Nội dung được ghép từ snippet orders-get-success/http-response.md.

### Response fields
Nội dung được ghép từ snippet orders-get-success/response-fields.md.
~~~

Các dòng trên chỉ mô tả vị trí cần ghép snippet, không phải directive include của Markdown. Công cụ build phải thay chúng bằng nội dung file thực tế hoặc dùng cú pháp riêng của công cụ đó.

### 9.1. Chọn Markdown dialect

Kiểm tra renderer hỗ trợ:

- Markdown Extra tables.
- Fenced code blocks và inline code.
- Relative links/images.
- Include/partials.
- Syntax highlighting nếu cần.

Nếu bảng descriptors hiển thị sai, cấu hình extension phù hợp hoặc tùy chỉnh template theo dialect mục tiêu. Không sửa tay raw snippet sinh từ test.

## 10. Markdown hay Asciidoctor?

| Tiêu chí | Markdown | Asciidoctor |
| --- | --- | --- |
| Cấu hình | `TemplateFormats.markdown()` | Định dạng mặc định. |
| Extension | `.md` | `.adoc` |
| Bảng | Markdown Extra | Asciidoc table. |
| Include snippet | Cần công cụ bổ sung | Có directive include. |
| Hệ sinh thái | Git hosting và static sites phổ biến | Tài liệu kỹ thuật dài. |
| Custom templates | Package theo format ID Markdown | Package theo format ID Asciidoctor. |

Markdown phù hợp khi nền tảng docs của nhóm đã dùng Markdown, renderer/dialect rõ ràng và có cơ chế ghép snippet. Asciidoctor thuận tiện khi cần include trực tiếp. Chọn theo hệ thống tài liệu của dự án.

## 11. Encoding và nội dung đa ngôn ngữ

Giữ snippets và nội dung viết tay ở UTF-8. Kiểm tra file output sau test, response body không bị lỗi dấu, renderer dùng UTF-8 và locale không vô tình phụ thuộc máy developer. Chuẩn hóa line endings/whitespace ở build step thống nhất thay vì sửa tay từng snippet.

Spring REST Docs cho phép cấu hình snippet encoding qua configurer. Chỉ đổi encoding khi có yêu cầu tương thích; UTF-8 thường phù hợp cho tài liệu web.

## 12. Build và CI

~~~mermaid
flowchart TD
    A["Compile test sources"] --> B["Run HTTP tests"]
    B --> C{"Assertions pass?"}
    C -->|No| D["Fail CI"]
    C -->|Yes| E["Generate Markdown snippets"]
    E --> F["Assemble Markdown pages"]
    F --> G["Run Markdown renderer"]
    G --> H{"Includes and render pass?"}
    H -->|No| D
    H -->|Yes| I["Package / Publish"]
~~~

Build cần bảo đảm test sinh snippet chạy trước task ghép trang; output directory không chứa artifact stale; task assemble chỉ đọc snippet của lần build hiện tại; renderer hỗ trợ Markdown dialect đã chọn; CI chỉ publish khi test, assemble và render đều đạt.

Skeleton Gradle minh họa quan hệ task:

~~~groovy
tasks.register('assembleApiMarkdown') {
    dependsOn tasks.named('test')
    inputs.dir(layout.buildDirectory.dir('generated-snippets'))
    inputs.dir(layout.projectDirectory.dir('src/docs'))
    outputs.dir(layout.buildDirectory.dir('api-markdown'))

    doLast {
        // Gọi công cụ include/preprocess Markdown của dự án.
        // Fail nếu snippet bắt buộc thiếu hoặc source page không hợp lệ.
    }
}
~~~

Đây là skeleton, không phải implementation của Markdown include engine. Nếu snippets được sinh bởi integration test task riêng, assemble phải phụ thuộc đúng task đó chứ không mặc định task test chung.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Vẫn sinh .adoc | Configurer mà test dùng chưa chọn Markdown | Kiểm tra đúng client instance. |
| Không có http-response.md | Test chưa chạy, identifier sai hoặc output dir khác | Kiểm tra test/configurer. |
| Bảng fields hiện như text thường | Renderer không hỗ trợ Markdown Extra | Bật extension hoặc chọn renderer khác. |
| Trang cuối thiếu nội dung snippet | Chưa có bước include/preprocess | Cấu hình công cụ ghép snippet. |
| Template override không có tác dụng | Sai package templates/markdown hoặc filename | Kiểm tra classpath, format ID và template name. |
| Snippet mất field sau tùy chỉnh | Template sai version/format | Lấy template gốc đúng version. |
| Snippet cũ còn sót | Output directory không được quản lý | Quản lý output theo build. |
| Tiếng Việt lỗi encoding | Charset/renderer không dùng UTF-8 | Kiểm tra encoding toàn pipeline. |
| CI render trước khi sinh snippet | Task dependency chưa đúng | Cho assemble phụ thuộc task test thích hợp. |
| REST Assured ghi snippet trước assertion cuối | Filter ghi operation ngay khi response nhận | Chỉ publish sau toàn bộ test suite. |

## 14. Bài thực hành

Thiết lập Markdown cho các endpoint:

- `GET /api/orders/101` trả `200` và JSON body.
- `POST /api/orders` nhận JSON, trả `201`, `Location` và response JSON.
- `GET /api/orders/999` trả `404` theo error contract ứng dụng.

Thực hiện:

1. Cấu hình MockMvc dùng `TemplateFormats.markdown()`.
2. Viết test cho ba operation với identifier riêng.
3. Mở http-request.md, http-response.md, request-body.md, response-body.md, response-fields.md và descriptor snippets liên quan.
4. Xác nhận snippet có extension .md.
5. Tạo custom template trong package `org/springframework/restdocs/templates/markdown` và xác minh output.
6. Chọn cơ chế include/partials; ghép snippets vào trang Markdown cuối.
7. Render bằng Markdown dialect hỗ trợ tables; kiểm tra links, encoding và code blocks.
8. Cấu hình CI chạy test trước assemble/render và không publish khi snippet bắt buộc thiếu.

**Tiêu chí hoàn thành:** Spring REST Docs sinh Markdown snippets trực tiếp; người học giải thích vai trò template format, vị trí custom templates và cách ghép snippet; trang cuối lấy dữ liệu từ test; CI chỉ publish khi test và render đều đạt.

## Tài liệu tham khảo chính thức

- [Spring REST Docs — Snippet Template Format](https://docs.spring.io/spring-restdocs/reference/configuration/snippet-template-format.html)
- [Spring REST Docs — Working with Markdown](https://docs.spring.io/spring-restdocs/reference/working-with-markdown.html)
- [Spring REST Docs — Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
