# Định dạng tên trường và tiêu đề bảng trong Spring REST Docs

## 1. Vì sao cần tùy biến tên trường và tiêu đề?

Spring REST Docs tạo snippet từ các bài kiểm thử HTTP. Với payload JSON, `requestFields(...)` hoặc `responseFields(...)` sinh bảng gồm đường dẫn, kiểu dữ liệu và mô tả. Bảng mặc định có cấu trúc rõ ràng, nhưng đôi khi chưa khớp cách trình bày của tài liệu sản phẩm:

- Tên JSON như `customerId`, `shippingAddress.postalCode` phù hợp với code nhưng khó đọc với người dùng nghiệp vụ.
- Một số nhóm muốn thêm nhãn hiển thị, quy tắc hoặc ràng buộc cho từng trường.
- Tiêu đề mặc định như “Request fields” chưa nói rõ đây là payload tạo đơn hàng, cập nhật hồ sơ hay lọc báo cáo.
- Các bảng request và response cần thống nhất cách gọi cột, ngôn ngữ và thứ tự thông tin.

Spring REST Docs cho phép tùy biến phần trình bày qua **Mustache snippet templates** và **attributes**. Ta có thể giữ `FieldDescriptor` làm nguồn mô tả có kiểm chứng từ test, sau đó bổ sung nhãn dễ đọc, cột mới và tiêu đề phù hợp cho operation.

Bài này thuộc chương **Snippet customization** của **SPRING_REST_DOCS** — module tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured, rồi biên soạn snippet trong Asciidoctor/Markdown và đưa vào build/CI.

Sau bài học, bạn có thể:

- Hiểu phần nào của bảng snippet được điều khiển bởi descriptor và phần nào do template quyết định.
- Thêm tên hiển thị cho path mà vẫn giữ nguyên đường dẫn JSON thực tế.
- Đổi tên cột, thêm cột ràng buộc và sắp xếp lại nội dung bảng.
- Đặt tiêu đề riêng cho từng snippet hoặc operation.
- Override template cho Asciidoctor và Markdown đúng classpath.
- Duy trì tùy biến nhất quán mà không làm mất khả năng kiểm tra payload của Spring REST Docs.

## 2. Tách dữ liệu mô tả khỏi cách trình bày

Có ba thành phần cần phân biệt:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `FieldDescriptor` | Định nghĩa path, type, description, optional, ignored và metadata của trường | `fieldWithPath("customerId")` |
| Snippet attributes | Bổ sung dữ liệu cho toàn snippet | Tiêu đề `Các trường tạo đơn hàng` |
| Mustache template | Quy định cách hiển thị dữ liệu thành bảng | Đổi cột `Path` thành `Tên trường`, thêm `Ràng buộc` |

Ví dụ descriptor:

```java
fieldWithPath("customerId")
    .type(JsonFieldType.NUMBER)
    .description("Mã khách hàng");
```

Path `customerId` là tên khóa JSON được dùng để đối chiếu request thực tế. Nếu chỉ muốn bảng hiển thị tên tiếng Việt “Mã khách hàng”, không nên đổi path thành một chuỗi tiếng Việt. Hãy giữ path kỹ thuật để REST Docs tiếp tục kiểm tra đúng payload, rồi thêm một attribute riêng cho nhãn hiển thị.

Mô hình đề xuất:

```text
JSON request thực tế
       |
       v
FieldDescriptor
  path = customerId
  type = NUMBER
  description = ...
  label = "Mã khách hàng"
       |
       v
Mustache template
       |
       v
Bảng tài liệu:
Tên trường | Path | Kiểu | Mô tả
Mã khách hàng | customerId | NUMBER | ...
```

Cách tách này giúp đổi ngôn ngữ hoặc phong cách trình bày mà không thay đổi contract HTTP.

## 3. Thêm tên hiển thị cho từng field

### 3.1. Gắn attribute vào `FieldDescriptor`

Spring REST Docs cho phép dùng `.attributes(...)` để gắn dữ liệu riêng cho descriptor. Ví dụ dùng `label` làm tên hiển thị:

```java
import static org.springframework.restdocs.snippet.Attributes.key;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

fieldWithPath("customerId")
    .description("Mã khách hàng tạo đơn")
    .attributes(key("label").value("Mã khách hàng"));
```

Với object lồng nhau:

```java
fieldWithPath("shippingAddress.postalCode")
    .description("Mã bưu chính của địa chỉ giao hàng")
    .attributes(key("label").value("Mã bưu chính"));
```

`path` vẫn giữ `shippingAddress.postalCode`; `label` chỉ cung cấp nội dung cho template.

Có thể định nghĩa các descriptor trong một mảng để tái sử dụng:

```java
private static final FieldDescriptor[] ORDER_FIELDS = {
    fieldWithPath("customerId")
        .type(JsonFieldType.NUMBER)
        .description("Mã khách hàng tạo đơn")
        .attributes(key("label").value("Mã khách hàng")),

    fieldWithPath("items")
        .type(JsonFieldType.ARRAY)
        .description("Danh sách mặt hàng")
        .attributes(key("label").value("Danh sách sản phẩm")),

    fieldWithPath("items[].sku")
        .type(JsonFieldType.STRING)
        .description("Mã định danh sản phẩm")
        .attributes(key("label").value("Mã sản phẩm")),

    fieldWithPath("items[].quantity")
        .type(JsonFieldType.NUMBER)
        .description("Số lượng đặt mua")
        .attributes(key("label").value("Số lượng"))
};
```

Cần import `FieldDescriptor`, `JsonFieldType` và static method `fieldWithPath`, `key` theo dự án. Các descriptor vẫn được REST Docs dùng để đối chiếu request mẫu; attribute `label` chỉ được dùng khi template yêu cầu.

### 3.2. Có nên thay path bằng nhãn hiển thị?

Thông thường nên trình bày cả path và nhãn nếu người đọc cần sao chép JSON hoặc đối chiếu trực tiếp với request:

| Tên hiển thị | Path JSON | Mô tả |
| --- | --- | --- |
| Mã khách hàng | `customerId` | Mã khách hàng tạo đơn |
| Mã sản phẩm | `items[].sku` | Mã định danh sản phẩm |
| Số lượng | `items[].quantity` | Số lượng đặt mua |

Nếu tài liệu dành cho người dùng API kỹ thuật, path JSON nên luôn dễ tìm. Nếu tài liệu hướng tới người dùng nghiệp vụ, có thể ưu tiên nhãn nhưng vẫn giữ path ở cột riêng hoặc phần chi tiết.

Không dùng attribute label như một cách “đổi tên” field trong request. Tên gửi qua HTTP vẫn là path JSON thật.

## 4. Đổi tên cột và thêm cột trong Mustache template

Spring REST Docs dùng Mustache templates để sinh snippet. Template mặc định cho format Asciidoctor được nạp từ classpath dưới package:

```text
org/springframework/restdocs/templates/asciidoctor/
```

Để override bảng request fields, tạo file:

```text
src/test/resources/
└── org/
    └── springframework/
        └── restdocs/
            └── templates/
                └── asciidoctor/
                    └── request-fields.snippet
```

File template tự định nghĩa bố cục bảng:

```adoc
{{#title}}
.{{title}}
{{/title}}
|===
|Tên trường|Path JSON|Kiểu|Mô tả|Ràng buộc

{{#fields}}
|{{#label}}{{label}}{{/label}}{{^label}}{{path}}{{/label}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}

{{/fields}}
|===
```

Ý nghĩa:

- `{{#title}}...{{/title}}`: hiển thị tiêu đề nếu snippet có attribute `title`.
- `{{#fields}}...{{/fields}}`: lặp qua danh sách field descriptor.
- `{{label}}`: attribute tùy chỉnh của descriptor.
- `{{^label}}...{{/label}}`: dùng `path` làm giá trị thay thế nếu descriptor chưa có `label`.
- `{{constraints}}`: attribute tùy chỉnh được thêm ở cấp field.

Trong Mustache, tên biến phải khớp với key của attribute. Vì vậy, nếu Java đặt `key("label")`, template đọc `{{label}}`; nếu dùng `key("constraints")`, template đọc `{{constraints}}`.

### 4.1. Thêm cột Ràng buộc

Gắn metadata cho từng descriptor:

```java
fieldWithPath("customerId")
    .description("Mã khách hàng tạo đơn")
    .attributes(
        key("label").value("Mã khách hàng"),
        key("constraints").value("Số nguyên dương")
    );

fieldWithPath("email")
    .description("Địa chỉ email nhận xác nhận")
    .attributes(
        key("label").value("Email"),
        key("constraints").value("Đúng định dạng email")
    );
```

Template có thể dùng `constraints` để hiển thị cột:

```adoc
|Tên trường|Path JSON|Kiểu|Mô tả|Ràng buộc
{{#fields}}
|{{#label}}{{label}}{{/label}}{{^label}}{{path}}{{/label}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}
{{/fields}}
```

Cột bổ sung giúp bảng giàu thông tin hơn. Tuy nhiên, giá trị `constraints` được người viết cung cấp; nó không tự động chạy Bean Validation và không thay thế test xác minh validation.

### 4.2. Template tối giản hơn

Nếu không cần tên hiển thị riêng, chỉ muốn đổi tên cột:

```adoc
|===
|Trường JSON|Kiểu dữ liệu|Ý nghĩa

{{#fields}}
|{{path}}
|{{type}}
|{{description}}

{{/fields}}
|===
```

Template tùy chỉnh có thể loại bỏ hoặc sắp xếp lại cột, nhưng nên giữ path, type và description nếu chúng cần cho client dùng API.

## 5. Đặt tiêu đề riêng cho từng bảng snippet

Có hai cấp tiêu đề phổ biến: tiêu đề được sinh bên trong snippet bằng attribute và tiêu đề do Asciidoctor đặt ở nơi include.

### 5.1. Attribute `title` cấp snippet

Spring REST Docs cho phép truyền attributes cho toàn snippet thông qua overload `requestFields(attributes(...), descriptors...)`:

```java
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

.andDo(document("orders-create",
    requestFields(
        attributes(key("title").value("Các trường tạo đơn hàng")),
        fieldWithPath("customerId")
            .description("Mã khách hàng tạo đơn"),
        fieldWithPath("items")
            .description("Danh sách mặt hàng")
    )
));
```

Template `request-fields.snippet` có thể đọc `{{title}}`:

```adoc
{{#title}}
.{{title}}
{{/title}}
|===
|Path|Type|Description

{{#fields}}
|{{path}}
|{{type}}
|{{description}}

{{/fields}}
|===
```

Tên attribute `title` không phải trường bắt buộc của `FieldDescriptor`; đó là metadata áp dụng cho snippet được tạo bởi lời gọi `requestFields(...)`.

### 5.2. Tiêu đề do Asciidoctor đặt trước include

Nếu muốn template giữ nguyên, có thể đặt title ở tài liệu `.adoc`:

```adoc
=== Tạo đơn hàng

.Các trường request khi tạo đơn hàng
include::{snippets}/orders-create/request-fields.adoc[]
```

Dòng bắt đầu bằng dấu chấm đặt tiêu đề cho nội dung bảng tiếp theo theo cú pháp Asciidoctor. Cách này phù hợp khi title do người biên soạn tài liệu quản lý ở một chỗ.

### 5.3. Đổi title khi dùng `operation` macro

Nếu dùng macro `operation::...[]` từ phần mở rộng Asciidoctor của Spring REST Docs, có thể tùy biến section title bằng document attribute có tên:

```adoc
:operation-request-fields-title: Các trường đầu vào
:operation-response-fields-title: Các trường trả về

operation::orders-create[]
```

Tên attribute có dạng `operation-{snippet}-title`. Ví dụ trên thay title của section tương ứng với `request-fields` và `response-fields` khi macro include snippet.

Đây là cơ chế title của `operation` macro. Nếu include snippet thủ công bằng `include::...[]`, nên đặt tiêu đề ngay trước include hoặc để custom template tạo tiêu đề.

## 6. Ví dụ hoàn chỉnh: bảng request fields bằng tiếng Việt

Ví dụ dưới đây dùng MockMvc và Spring REST Docs. Giả định endpoint `POST /api/orders` trả `201 Created` khi request hợp lệ.

### 6.1. Test khai báo attributes

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

@Test
void documentCreateOrder() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "customerId": 42,
                  "items": [
                    { "sku": "BOOK-001", "quantity": 2 }
                  ]
                }
                """))
        .andExpect(status().isCreated())
        .andDo(document("orders-create",
            requestFields(
                attributes(key("title").value("Thông tin tạo đơn hàng")),
                fieldWithPath("customerId")
                    .description("Mã khách hàng tạo đơn")
                    .attributes(
                        key("label").value("Mã khách hàng"),
                        key("constraints").value("Số nguyên dương")
                    ),
                fieldWithPath("items")
                    .description("Danh sách mặt hàng")
                    .attributes(key("label").value("Danh sách sản phẩm")),
                fieldWithPath("items[].sku")
                    .description("Mã định danh sản phẩm")
                    .attributes(key("label").value("Mã sản phẩm")),
                fieldWithPath("items[].quantity")
                    .description("Số lượng đặt mua")
                    .attributes(
                        key("label").value("Số lượng"),
                        key("constraints").value("Số nguyên lớn hơn 0")
                    )
            )
        ));
}
```

Imports và endpoint ở đây là ví dụ; thêm các static imports của `post`, `content`, `contentType`, `status` và `MediaType` theo test class thực tế. Payload mẫu phải khớp descriptor để snippet được tạo thành công.

### 6.2. Kết quả bảng dự kiến

Với template có năm cột, bảng có thể hiển thị:

| Tên trường | Path JSON | Kiểu | Mô tả | Ràng buộc |
| --- | --- | --- | --- | --- |
| Mã khách hàng | `customerId` | NUMBER | Mã khách hàng tạo đơn | Số nguyên dương |
| Danh sách sản phẩm | `items` | ARRAY | Danh sách mặt hàng | |
| Mã sản phẩm | `items[].sku` | STRING | Mã định danh sản phẩm | |
| Số lượng | `items[].quantity` | NUMBER | Số lượng đặt mua | Số nguyên lớn hơn 0 |

Đây là hình dạng mong đợi của snippet sau khi template được áp dụng. Nội dung cụ thể phụ thuộc JSON thực tế và các descriptor test gửi vào.

## 7. Dùng template riêng cho Markdown

Spring REST Docs hỗ trợ nhiều template format; ngoài Asciidoctor, Markdown cũng có thể được cấu hình. Mỗi format có ID riêng, và template được tải từ package classpath tương ứng.

Với format Markdown, template override nằm dưới package:

```text
src/test/resources/org/springframework/restdocs/templates/markdown/
```

Ví dụ `request-fields.snippet`:

```markdown
{{#title}}
### {{title}}
{{/title}}

| Tên trường | Path JSON | Kiểu | Mô tả |
| --- | --- | --- | --- |
{{#fields}}
| {{#label}}{{label}}{{/label}}{{^label}}{{path}}{{/label}} | `{{path}}` | {{type}} | {{description}} |
{{/fields}}
```

Muốn REST Docs dùng Markdown template format, cấu hình `SnippetConfigurer` khi thiết lập MockMvc:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import org.springframework.restdocs.templates.TemplateFormats;

this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
    .apply(documentationConfiguration(this.restDocumentation)
        .snippets().withTemplateFormat(TemplateFormats.markdown()))
    .build();
```

Tên API và cách cấu hình cụ thể cần khớp phiên bản Spring REST Docs của dự án. Có thể cấu hình tương ứng cho WebTestClient hoặc REST Assured qua `documentationConfiguration(...)` của module tích hợp.

Không đặt file Markdown template trong thư mục `asciidoctor` hoặc ngược lại. Format ID quyết định package trên classpath nơi REST Docs tìm template.

## 8. Ký tự đặc biệt và an toàn khi render bảng

Khi tên trường hoặc description có ký tự `|`, Asciidoctor dùng chính ký tự đó để phân tách cell. Ví dụ description:

```text
Giá trị có thể là A | B
```

Nếu đưa trực tiếp vào bảng mà không escape, cột có thể bị tách sai. Template mặc định Spring REST Docs dùng Mustache lambda `tableCellContent` để escape ký tự pipe trong cell.

Template tùy biến nên cân nhắc dùng:

```adoc
|{{#tableCellContent}}{{description}}{{/tableCellContent}}
```

Áp dụng tương tự với attribute `label` hoặc `constraints` nếu chúng có thể chứa `|`.

Với Markdown table, quy tắc escape phụ thuộc renderer và Markdown flavor đang dùng. Kiểm tra output bằng đúng công cụ build tài liệu của dự án; không giả định mọi Markdown renderer xử lý bảng giống nhau.

Ngoài ra:

- Không đặt dữ liệu bí mật hoặc giá trị thật của người dùng vào attribute chỉ để hiển thị.
- Giữ path kỹ thuật là dữ liệu của contract; label chỉ là nhãn trình bày.
- Chuẩn hóa xuống dòng và ký tự đặc biệt trong mô tả.
- Không đưa HTML tùy ý vào template nếu pipeline xuất bản không cần hỗ trợ.

## 9. Tổ chức template và tránh ảnh hưởng ngoài ý muốn

Template đặt trong `src/test/resources` thường được đưa vào classpath test và dùng khi chạy snippet generation. Một file template có cùng tên với snippet có thể override cách tạo snippet đó cho toàn bộ test sử dụng cùng format và classpath.

Ví dụ tổ chức:

```text
src/test/resources/
└── org/springframework/restdocs/templates/
    ├── asciidoctor/
    │   ├── request-fields.snippet
    │   └── response-fields.snippet
    └── markdown/
        ├── request-fields.snippet
        └── response-fields.snippet
```

Cần chú ý:

1. Override `request-fields.snippet` không tự động override `response-fields.snippet`; mỗi snippet có template riêng.
2. Template dùng chung phải có khả năng xử lý descriptor không có attribute tùy chỉnh; nên đặt giá trị fallback.
3. Nếu nhiều module dùng chung test classpath, template có thể tác động rộng hơn dự kiến. Tổ chức resource theo module và kiểm soát dependency/classpath.
4. Khi nâng phiên bản Spring REST Docs, kiểm tra template tùy chỉnh với các trường dữ liệu mà phiên bản mới cung cấp.

Nếu chỉ một operation cần nhãn khác, attributes cấp descriptor thường đủ. Nếu mọi operation cần đổi cấu trúc cột hoặc ngôn ngữ tiêu đề, template là nơi phù hợp hơn.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Label không xuất hiện | Chưa gắn `.attributes(key("label")...)` hoặc template không đọc `{{label}}` | Kiểm tra key và Mustache variable |
| Path JSON bị đổi thành label | Dùng nhầm label thay cho descriptor path | Giữ path thật; hiển thị label ở cột riêng |
| Cột mới trống | Chưa đặt attribute cho từng descriptor | Gắn `constraints` cho field cần dữ liệu hoặc dùng fallback |
| Title không xuất hiện | Custom template không đọc `{{title}}` | Thêm section `{{#title}}...{{/title}}` |
| Title Asciidoctor không nằm trên bảng | Đặt title sai vị trí hoặc dùng nhầm document attribute | Đặt `.Title` ngay trước include hoặc dùng operation macro đúng cú pháp |
| Template override không có tác dụng | Sai package format hoặc tên template | Kiểm tra `templates/asciidoctor` và `request-fields.snippet` |
| Markdown dùng nhầm cú pháp AsciiDoc | Template format và thư mục không khớp | Cấu hình `TemplateFormats.markdown()` và template `markdown` |
| Bảng vỡ khi description có `\|` | Ký tự pipe chưa được escape | Dùng `tableCellContent` với template Asciidoctor |
| Template request đúng nhưng response sai | Chưa override `response-fields.snippet` | Tạo template response riêng nếu cần |
| Ràng buộc hiển thị nhưng không đúng validation | Attribute được nhập thủ công và lỗi thời | Review cùng Bean Validation và test nghiệp vụ |
| Chạy test không thấy snippet mới | Build dùng output cũ hoặc test không chạy | Kiểm tra output directory và task dependency |

## 11. Tích hợp với Asciidoctor và build/CI

Template tùy chỉnh phải có trên test classpath khi test sinh snippet. Tài liệu nguồn include output đã được sinh:

```adoc
= Orders API
:toc: left

== Tạo đơn hàng

include::{snippets}/orders-create/request-fields.adoc[]
```

Nếu template đã tạo title bên trong snippet thì không cần thêm title trùng ở tài liệu nguồn. Nếu chọn cách để Asciidoctor đặt title, viết:

```adoc
.Các trường đầu vào khi tạo đơn hàng
include::{snippets}/orders-create/request-fields.adoc[]
```

Với Gradle và plugin Asciidoctor đã cấu hình, task tài liệu cần phụ thuộc vào test:

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

Đảm bảo `spring-restdocs-asciidoctor` được cấu hình theo hướng dẫn build của dự án để thuộc tính `snippets` được thiết lập. Template được nạp khi test chạy; Asciidoctor chỉ include các file snippet đã sinh.

Luồng CI:

```text
HTTP tests (MockMvc / WebTestClient / REST Assured)
                    |
                    v
      FieldDescriptor + snippet attributes
                    |
                    v
       Mustache template theo format
                    |
                    v
     request-fields.adoc / request-fields.md
                    |
                    v
             Asciidoctor / Markdown builder
                    |
                    v
            Kiểm tra và xuất bản
```

Khi đổi nhãn hoặc cột, chạy lại test để sinh snippet mới và kết xuất tài liệu. Không chỉnh output generated bằng tay vì lần chạy tiếp theo sẽ ghi đè.

## 12. Bài thực hành

Dùng operation `POST /api/orders`:

1. Thêm `label` cho `customerId`, `items`, `items[].sku` và `items[].quantity`.
2. Tạo `request-fields.snippet` cho Asciidoctor, đổi tên cột thành “Tên trường”, “Path JSON”, “Kiểu”, “Mô tả”.
3. Thêm `constraints` cho `quantity` và đưa thành cột riêng.
4. Truyền attribute `title` là “Thông tin tạo đơn hàng” và hiển thị trong template.
5. Bỏ attribute `label` khỏi một descriptor; xác nhận fallback vẫn hiển thị path.
6. Thêm description chứa ký tự `|`; kiểm tra template dùng `tableCellContent` để không làm vỡ bảng Asciidoctor.
7. Tạo template Markdown và cấu hình `TemplateFormats.markdown()`. So sánh output hai format.
8. Đổi template cho request fields nhưng chưa đổi response fields; quan sát hai bảng và quyết định có cần phong cách thống nhất.
9. Chạy test và Asciidoctor trong CI; review output generated thay vì chỉnh file output trực tiếp.

### Câu hỏi tự đánh giá

- `FieldDescriptor` path khác label hiển thị như thế nào?
- Attribute cấp descriptor và attribute cấp snippet khác nhau ở đâu?
- Vì sao phải override template đúng format ID?
- Tên file template để override request fields là gì?
- `{{#fields}}` và `{{#title}}` có vai trò gì?
- Có thể đặt title cho bảng bằng Asciidoctor mà không sửa template không?
- Vì sao `request-fields.snippet` và `response-fields.snippet` cần được quản lý riêng?
- Làm thế nào giữ bảng không bị vỡ khi mô tả có ký tự `|`?

**Ghi nhớ:** Giữ path JSON làm khóa contract, thêm label để hiển thị thân thiện và dùng Mustache template để thay đổi cột, thứ tự và tiêu đề. Attribute cung cấp dữ liệu; template quyết định cách trình bày. Nhờ vậy, Spring REST Docs vẫn kiểm tra request/response thực tế trong test trong khi bảng tài liệu có thể tuân theo ngôn ngữ và quy ước của sản phẩm.

## Tài liệu tham khảo

- [Spring REST Docs — Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html): Mustache templates, custom attributes và thêm cột cho snippet.
- [Spring REST Docs — Working with Asciidoctor](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/working-with-asciidoctor.html): include snippets, table columns và table titles.
- [Spring REST Docs — Snippet Template Format](https://docs.spring.io/spring-restdocs/reference/configuration/snippet-template-format.html): format ID, Asciidoctor và Markdown templates.
- [Spring REST Docs — `SnippetConfigurer` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/config/SnippetConfigurer.html): cấu hình template format và encoding.
