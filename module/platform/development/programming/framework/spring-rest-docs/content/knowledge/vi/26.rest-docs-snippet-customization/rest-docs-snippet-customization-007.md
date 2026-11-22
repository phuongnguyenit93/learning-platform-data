# Tạo snippet mới từ operation context trong Spring REST Docs

## 1. Khi nào cần tạo snippet riêng?

Spring REST Docs có sẵn nhiều snippet cho các khía cạnh phổ biến của HTTP operation, như request/response, headers, fields, parameters, links và multipart parts. Tuy nhiên, một API hoặc nhóm sản phẩm đôi khi cần một phần tài liệu không có sẵn dưới dạng snippet tiêu chuẩn, ví dụ:

- Bảng tóm tắt operation gồm HTTP method, URI, status và Content-Type.
- Danh sách file part kèm filename và media type cho một endpoint upload.
- Bảng correlation header, request ID hoặc thông tin phân trang đã chuẩn hóa.
- Khối ví dụ riêng kết hợp thông tin request và response.
- Metadata kỹ thuật cần đưa vào tài liệu cho từng operation.

Trong Spring REST Docs, mỗi snippet được tạo từ một `Operation`. Operation đại diện cho một lần gọi API đã được ghi nhận, chứa tên operation, request, response và attributes. Ta có thể viết snippet tùy biến để đọc dữ liệu từ operation context, tạo model rồi render bằng Mustache template.

Bài này thuộc chương **Snippet customization** của **SPRING_REST_DOCS**. Module thực hành tạo tài liệu REST API có thể kiểm chứng bằng test HTTP với MockMvc, WebTestClient hoặc REST Assured, sinh snippet cho request, response, payload, parameters và headers, rồi biên soạn tài liệu Asciidoctor/Markdown và đưa vào build/CI.

Sau bài học, bạn có thể:

- Hiểu `Operation` và dữ liệu request/response mà snippet có thể truy cập.
- Phân biệt custom snippet với custom Mustache template của snippet có sẵn.
- Tạo snippet mới bằng `TemplatedSnippet`.
- Đọc method, URI, headers, status và multipart parts từ operation.
- Tạo model an toàn cho template và đặt đúng tên output snippet.
- Đăng ký snippet trong `document(...)` và include nó trong Asciidoctor.
- Kiểm thử, duy trì và bảo vệ dữ liệu nhạy cảm trong custom snippet.

## 2. Operation context là gì?

Khi một test được tài liệu hóa, Spring REST Docs tạo operation context mô tả request đã gửi và response đã nhận. API chính nằm trong package `org.springframework.restdocs.operation`.

`Operation` cung cấp:

| API | Dữ liệu |
| --- | --- |
| `getName()` | Tên operation, thường là identifier truyền vào `document("...")` |
| `getRequest()` | Request đã gửi |
| `getResponse()` | Response đã nhận |
| `getAttributes()` | Attributes gắn với operation |

`OperationRequest` cung cấp các thông tin như:

- `getMethod()`: HTTP method.
- `getUri()`: URI của request.
- `getHeaders()`: HTTP request headers.
- `getContent()` hoặc `getContentAsString()`: request body.
- `getParts()`: multipart parts nếu request là multipart.
- `getCookies()`: cookies gửi trong request.

`OperationResponse` cung cấp:

- `getStatus()`: HTTP status code.
- `getHeaders()`: response headers.
- `getContent()` hoặc `getContentAsString()`: response body.
- `getCookies()`: cookies response.

Với multipart, mỗi `OperationRequestPart` có `getName()`, `getSubmittedFileName()`, `getHeaders()`, `getContent()` và `getContentAsString()`.

Mô hình tổng quát:

```text
HTTP test
   |
   v
DocumentFilter / document(...)
   |
   v
Operation
   +-- getName()
   +-- getAttributes()
   +-- getRequest()
   |     +-- method / URI / headers / body / parts
   |
   +-- getResponse()
         +-- status / headers / body / cookies
   |
   v
Custom Snippet
   |
   +-- đọc dữ liệu cần thiết
   +-- tạo model Map
   +-- render Mustache template
   |
   v
build/generated-snippets/<operation-id>/<snippet-name>.adoc
```

Operation context chứa thông tin của lần gọi HTTP đã ghi nhận. Đây là nguồn phù hợp cho snippet muốn phản ánh kết quả test, thay vì đọc lại dữ liệu fixture bằng một đường riêng.

## 3. Phân biệt custom template và custom snippet

Hai cơ chế này có liên quan nhưng giải quyết hai nhu cầu khác nhau.

| Cơ chế | Khi dùng | Kết quả |
| --- | --- | --- |
| Custom Mustache template cho snippet có sẵn | Muốn đổi bố cục `request-fields`, `response-headers`, `http-request`... | Vẫn là snippet có sẵn, nhưng nội dung được render theo template riêng |
| Custom snippet | Cần tạo một loại nội dung/snippet mới từ operation context | Có thêm file output với tên snippet do mình xác định |
| Operation preprocessor | Muốn biến đổi request/response trước khi các snippet đọc chúng | Nội dung operation được chuẩn hóa trước khi tạo snippet |

Ví dụ:
- Đổi cột trong `request-fields.adoc`: override `request-fields.snippet`.
- Thêm file `operation-summary.adoc` chứa method, URI và status: tạo custom snippet `operation-summary`.
- Che token trước khi ghi request headers: dùng preprocessor phù hợp, đồng thời kiểm tra dữ liệu đầu vào của custom snippet.

Không cần tạo snippet mới nếu chỉ muốn đổi tiêu đề, tên cột hoặc cách hiển thị của một snippet đã có.

## 4. Dùng `TemplatedSnippet` để tạo snippet mới

Cách thuận tiện để tạo snippet dựa trên Mustache là kế thừa `TemplatedSnippet` từ package `org.springframework.restdocs.snippet`.

Lớp này chịu trách nhiệm kết nối snippet name với template, render template và ghi file output. Lớp con cung cấp model bằng cách override:

```java
protected abstract Map<String, Object> createModel(Operation operation);
```

Constructor có hai dạng thường dùng:

```java
TemplatedSnippet(String snippetName, Map<String, Object> attributes)

TemplatedSnippet(
    String snippetName,
    String templateName,
    Map<String, Object> attributes
)
```

- `snippetName` quyết định tên file snippet được tạo.
- `templateName` quyết định tên template được tìm trên classpath.
- `attributes` là metadata bổ sung được đưa vào model khi render.

Nếu tên snippet và template giống nhau, có thể dùng constructor hai tham số. Nếu khác nhau, dùng constructor ba tham số.

## 5. Ví dụ: tạo snippet `operation-summary`

Giả sử muốn có thêm bảng tóm tắt mỗi operation:

| Thuộc tính | Giá trị |
| --- | --- |
| Operation | `orders-create` |
| Method | `POST` |
| URI | `/api/orders` |
| Status | `201` |
| Request Content-Type | `application/json` |
| Response Content-Type | `application/json` |

### 5.1. Viết custom snippet class

```java
package com.example.docs;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.restdocs.operation.Operation;
import org.springframework.restdocs.snippet.TemplatedSnippet;

public class OperationSummarySnippet extends TemplatedSnippet {

    public OperationSummarySnippet() {
        super("operation-summary", "operation-summary", Map.of());
    }

    @Override
    protected Map<String, Object> createModel(Operation operation) {
        Map<String, Object> model = new LinkedHashMap<>();

        model.put("operationName", operation.getName());
        model.put("method", operation.getRequest().getMethod().name());
        model.put("uri", operation.getRequest().getUri().toString());
        model.put("status", operation.getResponse().getStatus().value());

        model.put(
                "requestContentType",
                operation.getRequest().getHeaders().getContentType()
        );
        model.put(
                "responseContentType",
                operation.getResponse().getHeaders().getContentType()
        );

        return model;
    }
}
```

Điểm đáng chú ý:

- `operation.getName()` lấy operation identifier được truyền trong `document(...)`.
- Request method và URI đến từ `operation.getRequest()`.
- HTTP status và Content-Type response đến từ `operation.getResponse()`.
- Model là `Map<String, Object>`; key trở thành biến Mustache.
- `Map.of()` được dùng cho attributes ban đầu vì ví dụ chưa cần metadata mặc định.

Nếu ứng dụng dùng Java thấp hơn Java 9, thay `Map.of()` bằng `Collections.emptyMap()`.

### 5.2. Tạo Mustache template

Tạo file:

```text
src/test/resources/
└── org/
    └── springframework/
        └── restdocs/
            └── templates/
                └── asciidoctor/
                    └── operation-summary.snippet
```

Nội dung `operation-summary.snippet`:

```adoc
.Operation summary
|===
|Property|Value

|Operation
|{{operationName}}

|Method
|{{method}}

|URI
|{{uri}}

|Status
|{{status}}

|Request Content-Type
|{{requestContentType}}

|Response Content-Type
|{{responseContentType}}
|===
```

Tên template là `operation-summary`, tương ứng constructor:

```java
super("operation-summary", "operation-summary", Map.of());
```

Template phải nằm trong package format ID đang dùng. Với Asciidoctor mặc định là `org.springframework.restdocs.templates.asciidoctor`; nếu dùng Markdown, đặt template trong package `markdown` và cấu hình format tương ứng.

### 5.3. Đăng ký snippet trong `document(...)`

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
            {"customerId":42,"items":[{"sku":"BOOK-001","quantity":2}]}
            """))
    .andExpect(status().isCreated())
    .andDo(document("orders-create",
        new OperationSummarySnippet(),
        requestFields(
            fieldWithPath("customerId").description("Mã khách hàng"),
            fieldWithPath("items").description("Danh sách mặt hàng"),
            fieldWithPath("items[].sku").description("Mã sản phẩm"),
            fieldWithPath("items[].quantity").description("Số lượng đặt")
        )
    ));
```

`OperationSummarySnippet` là một snippet bổ sung trong cùng operation. Spring REST Docs gọi `document(operation)` trên snippet đó, tạo model từ operation và render template.

Sau test, output có thể gồm:

```text
build/generated-snippets/
└── orders-create/
    ├── operation-summary.adoc
    └── request-fields.adoc
```

Tên file output dùng `snippetName`, còn template được tìm bằng `templateName`.

## 6. Đọc nhiều phần của operation context

Custom snippet hữu ích khi cần kết hợp dữ liệu từ request và response trong cùng một trang. Ví dụ có thể tạo bảng status và headers chính:

```java
@Override
protected Map<String, Object> createModel(Operation operation) {
    Map<String, Object> model = new LinkedHashMap<>();

    model.put("operationName", operation.getName());
    model.put("method", operation.getRequest().getMethod().name());
    model.put("uri", operation.getRequest().getUri().toString());
    model.put("requestContentLength", operation.getRequest().getContent().length);
    model.put("status", operation.getResponse().getStatus().value());
    model.put(
            "responseContentLength",
            operation.getResponse().getContent().length
    );

    return model;
}
```

Có thể bổ sung header đã chọn:

```java
model.put(
    "requestAccept",
    operation.getRequest().getHeaders().getFirst("Accept")
);

model.put(
    "responseContentType",
    operation.getResponse().getHeaders().getContentType()
);
```

Hãy chọn các header có ý nghĩa với người dùng API. Không đưa toàn bộ headers vào tài liệu nếu có nguy cơ lộ `Authorization`, `Cookie`, session identifier hoặc thông tin hạ tầng.

### 6.1. Đọc multipart parts

Với operation upload, `OperationRequest.getParts()` trả về collection các `OperationRequestPart`:

```java
import org.springframework.restdocs.operation.OperationRequestPart;

List<Map<String, Object>> parts = new ArrayList<>();

for (OperationRequestPart part : operation.getRequest().getParts()) {
    Map<String, Object> item = new LinkedHashMap<>();
    item.put("name", part.getName());
    item.put("filename", part.getSubmittedFileName());
    item.put("contentType", part.getHeaders().getContentType());
    item.put("size", part.getContent().length);

    parts.add(item);
}

model.put("parts", parts);
```

Template có thể lặp qua `parts`:

```adoc
|===
|Part|Filename|Content-Type|Bytes

{{#parts}}
|{{name}}
|{{filename}}
|{{contentType}}
|{{size}}

{{/parts}}
|===
```

Đây là ví dụ hữu ích cho tài liệu upload file + metadata. `filename` có thể `null` với part không phải file; nên cung cấp fallback trong model hoặc template để bảng không hiển thị giá trị khó hiểu.

Không đưa nội dung bytes file vào template. Thường chỉ cần tên part, filename đã được kiểm soát, media type và kích thước. Nếu filename có thể chứa dữ liệu riêng tư hoặc đường dẫn không an toàn, hãy chuẩn hóa trước khi tạo model.

## 7. Truyền metadata cho custom snippet

Có hai nguồn thông tin có thể dùng trong custom snippet:

1. **Operation data**: tên operation, request, response và attributes.
2. **Attributes truyền khi khởi tạo snippet**: metadata do test hoặc cấu hình cung cấp.

Ví dụ thêm title và version:

```java
Map<String, Object> attributes = new HashMap<>();
attributes.put("title", "Tóm tắt operation");
attributes.put("apiVersion", "v1");

new OperationSummarySnippet(attributes);
```

Constructor:

```java
public OperationSummarySnippet(Map<String, Object> attributes) {
    super("operation-summary", "operation-summary", attributes);
}
```

`TemplatedSnippet` tự đưa các attributes đã truyền vào model render. Template có thể dùng:

```adoc
{{#title}}
.{{title}}
{{/title}}

.API version: {{apiVersion}}
```

Không cần tự copy attributes vào map trong `createModel(...)`, trừ khi muốn biến đổi hoặc ghi đè có chủ đích. Tránh dùng cùng key cho dữ liệu operation và metadata tùy chỉnh nếu hai nguồn có thể xung đột.

Có thể truyền attributes ở cấp operation thông qua các operation attributes của cấu hình `document(...)` tùy module tích hợp. Với ví dụ cơ bản, truyền trực tiếp vào constructor custom snippet là cách rõ ràng, dễ theo dõi.

## 8. Phát hiện dữ liệu thiếu và xử lý lỗi tạo model

Một custom snippet nên xử lý trường hợp request không có body, response không có Content-Type hoặc operation không phải multipart. Không giả định mọi operation đều có mọi loại dữ liệu.

Ví dụ:

```java
@Override
protected Map<String, Object> createModel(Operation operation) {
    Map<String, Object> model = new LinkedHashMap<>();

    model.put("operationName", operation.getName());
    model.put("method", operation.getRequest().getMethod().name());
    model.put("uri", operation.getRequest().getUri().toString());
    model.put("status", operation.getResponse().getStatus().value());

    model.put(
        "requestContentType",
        operation.getRequest().getHeaders().getContentType() == null
            ? "—"
            : operation.getRequest().getHeaders().getContentType().toString()
    );

    model.put(
        "responseContentType",
        operation.getResponse().getHeaders().getContentType() == null
            ? "—"
            : operation.getResponse().getHeaders().getContentType().toString()
    );

    model.put("requestHasBody", operation.getRequest().getContent().length > 0);
    model.put("responseHasBody", operation.getResponse().getContent().length > 0);

    return model;
}
```

Nếu dữ liệu bắt buộc đối với snippet bị thiếu, nên báo lỗi rõ nghĩa thay vì tạo bảng sai hoặc âm thầm đưa giá trị giả. `createModel(...)` có thể ném runtime exception để dừng sinh snippet; nếu dùng API `ModelCreationException` trong phiên bản dự án, hãy làm theo constructor và contract của phiên bản đó.

Template cần có nhánh điều kiện:

```adoc
{{#requestHasBody}}
Request có body.
{{/requestHasBody}}

{{^requestHasBody}}
Request không có body.
{{/requestHasBody}}
```

Nhánh Mustache giúp template biểu diễn trường hợp có/không có body mà không cần sinh hai template riêng.

## 9. Kiểm thử custom snippet

Custom snippet là một phần của test tài liệu hóa. Cần kiểm tra tối thiểu:

- Test request/response thành công tạo file snippet mong đợi.
- Operation name, method, URI và status trong snippet đúng với HTTP exchange.
- Request không có body hoặc response không có Content-Type không làm template vỡ.
- Multipart request chứa đúng part names và media type nếu snippet có hiển thị parts.
- Attribute có/không có được render với fallback hợp lý.
- Header nhạy cảm hoặc nội dung bí mật không xuất hiện trong output.

Ví dụ test kiểm tra snippet sau khi MockMvc chạy:

```java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"customerId":42}
            """))
    .andExpect(status().isCreated())
    .andDo(document("orders-create",
        new OperationSummarySnippet()
    ));
```

Sau khi test, kiểm tra file:

```text
build/generated-snippets/orders-create/operation-summary.adoc
```

Có thể dùng test assertion trên nội dung file nếu dự án muốn khóa format của snippet. Tuy nhiên, tránh kiểm tra toàn bộ khoảng trắng hoặc nội dung trình bày quá mong manh nếu thay đổi template là điều thường xuyên; ưu tiên xác minh các dữ liệu contract quan trọng.

## 10. Tích hợp với WebTestClient và REST Assured

Custom snippet không gắn riêng với MockMvc. Ba module tích hợp đều chuyển request/response đã ghi nhận thành `Operation` trước khi gọi các snippet được cấu hình.

### 10.1. WebTestClient

```java
webTestClient.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(requestBody)
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("orders-create",
        new OperationSummarySnippet(),
        requestFields(
            fieldWithPath("customerId").description("Mã khách hàng")
        )
    ));
```

### 10.2. REST Assured

```java
given(this.spec)
    .filter(document("orders-create",
        new OperationSummarySnippet(),
        requestFields(
            fieldWithPath("customerId").description("Mã khách hàng")
        )))
    .contentType("application/json")
    .body(requestBody)
    .when()
    .post("/api/orders")
    .then()
    .statusCode(201);
```

Cách gắn custom snippet tương tự; phần khác nhau là cách module tích hợp thu thập HTTP exchange. Đảm bảo custom snippet class và template có trên test classpath của module chạy test.

## 11. Tùy biến snippet cho Markdown

Nếu dự án dùng template format Markdown, cần cấu hình format Markdown và đặt template trong package tương ứng:

```text
src/test/resources/
└── org/springframework/restdocs/templates/
    └── markdown/
        └── operation-summary.snippet
```

Nội dung ví dụ:

```markdown
### Operation summary

| Property | Value |
| --- | --- |
| Operation | {{operationName}} |
| Method | {{method}} |
| URI | {{uri}} |
| Status | {{status}} |
| Request Content-Type | {{requestContentType}} |
| Response Content-Type | {{responseContentType}} |
```

Tên snippet vẫn là `operation-summary`; format ID quyết định package template và cú pháp output. Chọn cùng một format cho các snippet của một bộ tài liệu để tránh trộn AsciiDoc và Markdown ngoài ý muốn.

Cấu hình format được thực hiện qua `SnippetConfigurer` trong `documentationConfiguration(...)` của module tích hợp. Kiểm tra API của phiên bản Spring REST Docs trong dự án trước khi thay đổi cấu hình hiện hữu.

## 12. Bảo vệ dữ liệu khi đọc operation context

Operation context có thể chứa nội dung nhạy cảm, vì vậy custom snippet chỉ nên lấy đúng dữ liệu cần công bố.

Không đưa trực tiếp các thông tin sau vào snippet công khai:

- `Authorization`, `Cookie`, access token hoặc session ID.
- Email, số điện thoại hoặc dữ liệu nhận diện cá nhân thực.
- File upload thật, đường dẫn lưu trữ nội bộ hoặc filename có thông tin khách hàng.
- URL chứa query parameter bí mật.
- Response body có dữ liệu production.

Nếu cần trình bày header, chỉ lấy allowlist các header đã duyệt. Dùng fixture giả lập. Preprocessor có thể mask hoặc thay thế một số giá trị trước khi ghi snippet, nhưng custom snippet cũng phải được thiết kế để không vô tình xuất dữ liệu khác từ operation.

Với custom part summary, chỉ lấy part name, media type và kích thước nếu các thông tin này cần thiết. Tránh gọi `getContentAsString()` rồi đưa toàn bộ nội dung JSON hoặc file vào bảng chung.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không thấy file custom snippet | Chưa thêm snippet vào `document(...)` | Đăng ký instance trong danh sách snippets |
| Template không được tìm thấy | Sai tên template hoặc sai format package | Đồng bộ `templateName` và đường dẫn classpath |
| File output mang tên không mong muốn | Nhầm snippetName với templateName | Chọn rõ hai tên trong constructor |
| Mustache không thấy biến | Model không đưa key vào map | Kiểm tra `createModel(...)` và tên biến |
| URI hoặc status trống | Đọc sai object hoặc operation không như giả định | Dùng `getRequest()` và `getResponse()` |
| Snippet lỗi với multipart không có file | Giả định mọi request có `getParts()` | Kiểm tra collection rỗng và tạo fallback |
| Bảng hiển thị `null` | Giá trị optional chưa được xử lý | Dùng fallback trong model hoặc template |
| Custom snippet làm lộ token | Duyệt và render toàn bộ headers | Chỉ lấy allowlist, dùng token giả và mask |
| Template Markdown render sai | Dùng cú pháp AsciiDoc hoặc format ID không đúng | Tạo template theo Markdown format và kiểm tra renderer |
| Test pass nhưng snippet không đúng | Chưa kiểm tra nội dung output | Thêm assertion cho operation data quan trọng |
| Custom snippet quá lớn và khó bảo trì | Trộn thu thập dữ liệu, validation và render vào một lớp | Tách model builder, snippet và template |

## 14. Asciidoctor và build/CI

Trong tài liệu nguồn, include snippet mới như các snippet tiêu chuẩn:

```adoc
= Orders API
:toc: left

== Tạo đơn hàng

=== Operation summary
include::{snippets}/orders-create/operation-summary.adoc[]

=== Request fields
include::{snippets}/orders-create/request-fields.adoc[]

=== HTTP response
include::{snippets}/orders-create/http-response.adoc[]
```

Với Gradle và plugin Asciidoctor đã cấu hình:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
}
```

Luồng CI:

```text
MockMvc / WebTestClient / REST Assured test
                    |
                    v
             Operation context
                    |
                    v
              Custom Snippet
                    |
                    v
          Model + Mustache template
                    |
                    v
      build/generated-snippets/<operation>/
                    |
                    v
           Asciidoctor / Markdown
                    |
                    v
           Kiểm tra và xuất bản
```

Khi thay đổi custom snippet hoặc template:
1. Chạy test đại diện tạo snippet.
2. Xác nhận đúng output filename và operation ID.
3. Kiểm tra các giá trị method, URI, status, headers hoặc part summary.
4. Kiểm tra không lộ dữ liệu nhạy cảm.
5. Chạy Asciidoctor để xác nhận include hoạt động.
6. Review diff của snippet generated trong pull request.

Không sửa file trong `build/generated-snippets` bằng tay. Thay đổi phải nằm trong class custom snippet, model builder hoặc Mustache template.

## 15. Bài thực hành

Tạo endpoint `POST /api/orders` và thực hiện:

1. Viết `OperationSummarySnippet` kế thừa `TemplatedSnippet`.
2. Đưa operation name, HTTP method, URI và response status vào model.
3. Tạo template `operation-summary.snippet` và xác nhận file `operation-summary.adoc` được sinh.
4. Bổ sung request/response Content-Type và xử lý trường hợp header không có.
5. Tạo snippet khác hiển thị multipart part name, filename, Content-Type và size.
6. Kiểm thử request không có body và operation không phải multipart.
7. Gắn attributes `title` và `apiVersion` khi khởi tạo snippet.
8. Tạo template Markdown trong đúng package format.
9. Chạy cùng custom snippet với WebTestClient hoặc REST Assured.
10. Thêm assertion để xác minh snippet không chứa Authorization token hoặc nội dung file.

### Câu hỏi tự đánh giá

- `Operation` lưu những thông tin nào của một lần gọi API?
- `TemplatedSnippet` khác custom template của snippet có sẵn như thế nào?
- `snippetName` và `templateName` có vai trò khác nhau gì?
- `createModel(Operation)` chịu trách nhiệm gì?
- Làm thế nào để đọc status response và request Content-Type?
- Có thể lấy các multipart part từ API nào?
- Vì sao custom snippet cần xử lý null và collection rỗng?
- Khi nào nên dùng custom snippet thay vì thêm cột vào template có sẵn?
- Làm thế nào kiểm tra output và ngăn lộ dữ liệu nhạy cảm?

**Ghi nhớ:** `Operation` là ngữ cảnh của một lần gọi API đã được test ghi nhận. Custom snippet có thể đọc request/response, tạo model và render bằng Mustache thông qua `TemplatedSnippet`. Dùng custom snippet khi cần một loại nội dung mới; dùng custom template khi chỉ cần thay đổi cách hiển thị snippet hiện có. Luôn giới hạn dữ liệu operation được đưa vào tài liệu công khai.

## Tài liệu tham khảo

- [Spring REST Docs — Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html): Mustache templates và attributes.
- [Spring REST Docs — `TemplatedSnippet` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/snippet/TemplatedSnippet.html): constructor, `createModel`, `document` và snippet name.
- [Spring REST Docs — `Operation` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/Operation.html): operation name, attributes, request và response.
- [Spring REST Docs — `OperationRequest` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/OperationRequest.html): method, URI, headers, content và multipart parts.
- [Spring REST Docs — `OperationRequestPart` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/OperationRequestPart.html): tên, filename, headers và nội dung từng part.
