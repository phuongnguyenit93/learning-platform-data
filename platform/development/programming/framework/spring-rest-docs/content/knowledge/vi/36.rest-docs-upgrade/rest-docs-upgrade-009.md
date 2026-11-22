# Xử lý thay đổi định dạng snippet

## 1. Vì sao định dạng snippet có thể thay đổi sau nâng cấp?

Spring REST Docs sinh snippet từ các bài kiểm thử HTTP. Nội dung được tạo bởi operation, field descriptors, attributes và Mustache template. Khi nâng cấp Spring REST Docs, Spring Framework, AsciidoctorJ hoặc template tùy chỉnh, output có thể khác dù HTTP contract không đổi.

Các khác biệt thường gặp:
- Tên hoặc phần mở rộng file snippet đổi do format được cấu hình khác.
- Bảng fields có cột, thứ tự hoặc tiêu đề khác.
- Cách escape ký tự đặc biệt trong AsciiDoc/Markdown thay đổi.
- HTTP request/response snippet hiển thị headers, URI hoặc body khác.
- Template tùy chỉnh dùng biến Mustache không còn được cung cấp như trước.
- File snippet không đổi nhưng Asciidoctor hoặc Markdown renderer tạo HTML khác.

Trong **SPRING_REST_DOCS**, test HTTP bằng MockMvc, WebTestClient hoặc REST Assured tạo bằng chứng cho request, response, payload, parameters và headers. Snippet được biên soạn bằng Asciidoctor/Markdown rồi đưa vào build/CI. Bài thuộc chương **Nâng cấp**, hướng dẫn chẩn đoán và xử lý thay đổi định dạng để nâng cấp thư viện không vô tình che giấu thay đổi API hoặc làm tài liệu sai.

Sau bài học, bạn có thể phân biệt contract drift với rendering change, tạo baseline, so sánh snippet theo operation, đối chiếu template của version đích, cập nhật Mustache variables và kiểm tra output trong CI.

## 2. Ba lớp tạo ra output

| Lớp | Thành phần | Điều quyết định |
| --- | --- | --- |
| HTTP exchange | Request/response được test ghi nhận | Method, URI, status, headers, payload, bytes |
| Snippet generation | REST Docs descriptors, operation model, Mustache template | Snippet nào được tạo, dữ liệu và cấu trúc |
| Document rendering | Asciidoctor, Markdown builder, CSS/theme | HTML/PDF cuối cùng và cách hiển thị |

Nếu `response-fields.adoc` giữ nguyên path nhưng tiêu đề cột đổi, nguyên nhân thường nằm ở template/snippet generation. Nếu file `.adoc` không đổi nhưng HTML đổi, kiểm tra AsciidoctorJ, extension, theme hoặc CSS. Nếu JSON response thực tế đổi, đó có thể là thay đổi contract.

Đừng bắt đầu bằng việc cập nhật snapshot trước khi xác định lớp nào tạo ra khác biệt.

## 3. Phân loại thay đổi định dạng và thay đổi contract

| Dấu hiệu | Loại thay đổi có thể xảy ra | Cách xác minh |
| --- | --- | --- |
| Whitespace hoặc line wrapping khác | Rendering | So sánh nội dung có ý nghĩa |
| Tiêu đề/cột bảng khác | Template | Diff template và generated snippet |
| Field path mới hoặc mất | Contract hoặc descriptor | Kiểm tra JSON thực tế và strict descriptors |
| HTTP status khác | Hành vi ứng dụng/contract | Kiểm tra status assertion và response |
| Header xuất hiện/mất | HTTP exchange hoặc preprocessor | Kiểm tra operation và preprocessors |
| File extension đổi | Format configuration | Kiểm tra format ID và output naming |
| AsciiDoc include không tìm thấy | Build path/task dependency | Kiểm tra snippets directory và include path |
| HTML khác nhưng snippet giống | Renderer/theme | Kiểm tra Asciidoctor và CSS |

Không mặc định mọi diff là formatting. Field response biến mất có thể là breaking change; field mới chưa có descriptor có thể là payload drift. Hãy kiểm tra dữ liệu operation trước khi phân loại.

## 4. Tạo baseline trước khi nâng cấp

Trước khi đổi dependency hoặc template, tạo baseline có thể tái lập:

1. Checkout đúng commit đang phát hành.
2. Dùng cùng JDK, dependency và build tool hiện tại.
3. Chạy cùng documentation tests và fixture.
4. Lưu toàn bộ `build/generated-snippets` làm artifact baseline.
5. Build Asciidoctor/Markdown và lưu output cuối nếu cần kiểm tra rendering.
6. Ghi commit SHA, version Spring REST Docs, format ID và renderer version.

Cấu trúc artifact có thể như sau:

```text
docs-baseline/
├── metadata.txt
├── generated-snippets/
│   ├── products-get/
│   └── products-create/
└── rendered-site/
```

Không nhất thiết commit generated snippets vào source repository nếu dự án không có chính sách đó. Có thể lưu artifact CI hoặc release artifact có thể truy xuất. Baseline cần dùng cùng fixture; nếu fixture thay đổi cùng lúc với thư viện, diff sẽ khó xác định nguyên nhân.

## 5. So sánh output theo từng lớp

### 5.1. So sánh HTTP exchange

Xác nhận test vẫn gửi cùng request và nhận cùng response:
- HTTP method và URI.
- Request/response status.
- Content-Type và headers có ý nghĩa.
- Request/response JSON fields.
- Query/path parameters và multipart parts.

Các assertion như `status().isOk()`, `jsonPath(...)`, `requestFields(...)` và `responseFields(...)` giúp giữ contract rõ ràng. Nếu fixture hoặc endpoint đã thay đổi, ghi nhận riêng trước khi xem xét formatting.

### 5.2. So sánh generated snippets

Sau khi chạy test ở version đích, so sánh từng operation directory:

```text
products-get/
  http-request.adoc
  http-response.adoc
  response-fields.adoc
```

Dùng diff để tìm thay đổi:

```bash
git diff --no-index baseline/products-get target/products-get
```

Đọc diff theo ý nghĩa:
- Field hoặc header nào biến mất?
- Path và type có giữ nguyên không?
- Khác biệt chỉ nằm ở title, table border hoặc whitespace?
- Placeholder/redaction còn hoạt động?
- Custom attributes có được render?

### 5.3. So sánh rendered document

Nếu snippet giống nhau nhưng trang HTML khác, kiểm tra:
- Phiên bản AsciidoctorJ và plugin.
- Asciidoctor extensions và attributes.
- Theme, stylesheet, font và asset.
- Cách include và cấu hình toc.
- Phiên bản Markdown processor.

Không sửa template REST Docs để bù cho thay đổi CSS hoặc renderer nếu snippet nguồn không có vấn đề.

## 6. Đối chiếu template mặc định của version đích

Template tùy chỉnh là phần dễ bị ảnh hưởng khi nâng cấp. Nguồn đối chiếu chính xác là template mặc định trong artifact Spring REST Docs version đích.

Quy trình:
1. Xác định version REST Docs đích và format ID, ví dụ `asciidoctor`.
2. Tải artifact `spring-restdocs-core` đúng version qua build.
3. Liệt kê nội dung JAR và tìm package `org/springframework/restdocs/templates/<format-id>/`.
4. Trích template mặc định của snippet cần override vào thư mục tạm.
5. Diff template cũ và template đích.
6. Diff template tùy chỉnh với template mặc định mới.
7. Merge thay đổi cần thiết, giữ customizations có chủ đích.

Ví dụ liệt kê JAR:

```bash
jar tf spring-restdocs-core-<target-version>.jar
```

So sánh template:

```bash
git diff --no-index baseline/request-fields.snippet target/request-fields.snippet
```

Không copy nguyên template mới vào source rồi xóa customizations. Trước hết xác định upstream thay đổi biến Mustache, lambda, section hoặc cấu trúc model nào.

## 7. Kiểm tra Mustache variables và attributes

Giả sử template tùy chỉnh có:

```adoc
{{#title}}
.{{title}}
{{/title}}
|===
|Tên trường|Path|Kiểu|Mô tả|Ràng buộc

{{#fields}}
|{{#label}}{{label}}{{/label}}{{^label}}{{path}}{{/label}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}

{{/fields}}
|===
```

Các biến có thể đến từ nhiều nguồn:
- `fields`, `path`, `type`, `description`: model của snippet fields.
- `title`: snippet attribute truyền qua lời gọi `requestFields(...)`.
- `label`, `constraints`: attributes gắn vào từng `FieldDescriptor`.

Khi nâng cấp:
- Đối chiếu template mặc định để xác nhận model variables.
- Kiểm tra custom key còn được gắn trong test.
- Giữ fallback khi `label` hoặc `constraints` vắng mặt.
- Kiểm tra cả request và response templates; chúng là snippet độc lập.
- Kiểm tra lambda escaping chỉ dùng trong format hỗ trợ.

Template có thể render thành công nhưng in ô trống nếu biến không còn được cung cấp. Vì vậy cần assertion trên nội dung output, không chỉ dựa vào việc test không ném exception.

## 8. Xác minh format ID và phần mở rộng file

Spring REST Docs chọn template theo format ID. Ví dụ:

```text
src/test/resources/org/springframework/restdocs/templates/
├── asciidoctor/
│   ├── request-fields.snippet
│   └── response-fields.snippet
└── markdown/
    ├── request-fields.snippet
    └── response-fields.snippet
```

Nếu test chuyển từ Asciidoctor sang Markdown nhưng template vẫn nằm trong package `asciidoctor`, template tùy chỉnh có thể không được dùng. Extension output cũng phản ánh format được cấu hình.

Kiểm tra format ở nơi tạo MockMvc/WebTestClient/REST Assured documentation configuration. Ví dụ với MockMvc:

```java
.apply(documentationConfiguration(restDocumentation)
    .snippets()
    .withTemplateFormat(TemplateFormats.markdown()))
```

API cụ thể cần khớp version dependency. Đừng chỉ đổi tên file output bằng script để giả lập Markdown; phải chọn format template tương ứng và dùng renderer phù hợp.

## 9. Kiểm tra escaping và nội dung bảng

Thay đổi Mustache hoặc renderer có thể ảnh hưởng:
- Pipe `|` trong AsciiDoc/Markdown table.
- Dấu ngoặc nhọn, backtick và inline code.
- Nội dung xuống dòng trong description.
- Unicode và ký tự tiếng Việt.
- HTML hoặc ký tự cần escape.

Template Asciidoctor mặc định có thể dùng helper như `tableCellContent` để xử lý pipe trong cell. Nếu override template, kiểm tra helper trong version đích và áp dụng cho custom attributes có thể chứa nội dung tương tự.

Ví dụ descriptor:

```java
fieldWithPath("description")
    .description("Nhãn A | nhãn B; hỗ trợ tiếng Việt");
```

Sau khi sinh snippet, kiểm tra bảng vẫn có đúng số cột và nội dung không bị tách sai. Với Markdown, kiểm tra bằng processor của dự án; cú pháp table và escaping có thể khác AsciiDoc.

## 10. Giữ output ổn định và tránh diff nhiễu

Generated snippets thường được review trong pull request. Để diff dễ đọc:
- Dùng fixture deterministic, không tạo timestamp hoặc UUID ngẫu nhiên trong ví dụ chính.
- Không chèn build time vào từng snippet nếu không cần.
- Chuẩn hóa locale/timezone của test.
- Dùng thứ tự dữ liệu ổn định khi output phụ thuộc collection.
- Giữ operation IDs nhất quán.
- Tách thay đổi template khỏi thay đổi API contract trong pull request khi có thể.

Không nhất thiết khóa mọi byte bằng snapshot test. Có thể kiểm tra các giá trị contract quan trọng; dùng golden file cho artifact cần ổn định tuyệt đối và review mọi lần cập nhật.

## 11. Viết regression tests cho định dạng snippet

| Trường hợp | Assertion |
| --- | --- |
| Request fields | Path, type và description quan trọng còn xuất hiện |
| Response fields | Field public không biến mất |
| Custom title | Tiêu đề được render |
| Custom attributes | Label/constraints/example không bị mất |
| Attribute vắng | Fallback hiển thị đúng |
| Nested/array fields | Path lồng và phần tử mảng chính xác |
| Ký tự đặc biệt | Bảng không bị vỡ |
| Redaction | Token và cookie không xuất hiện |
| Format Asciidoctor | Extension và syntax đúng |
| Format Markdown | Template đúng package và output render được |

Ví dụ assertion:

```java
String generated = Files.readString(
    snippetsDir.resolve("products-get/response-fields.adoc")
);

assertThat(generated)
    .contains("Mã sản phẩm")
    .contains("name")
    .contains("Tên sản phẩm");
```

Assert nội dung có ý nghĩa hơn là khóa toàn bộ whitespace nếu format có thể thay đổi. Với golden file, mọi cập nhật cần được review và giải thích.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Snippet thiếu cột sau nâng cấp | Mustache variable không còn trong model hoặc attribute không được truyền | Đối chiếu template mặc định và descriptor attributes |
| Template tùy chỉnh không được nạp | Sai format ID hoặc tên snippet | Kiểm tra classpath và `TemplateFormats` |
| Bảng vỡ khi có pipe | Escape/helper không còn được dùng | Kiểm tra `tableCellContent` và renderer |
| Extension output thay đổi | Format config đã đổi | Chọn format rõ ràng và cập nhật include path |
| Snippet giống nhưng HTML khác | Asciidoctor/theme/CSS thay đổi | Kiểm tra renderer riêng |
| Field biến mất | Contract hoặc descriptor thay đổi | Kiểm tra payload thực và strict descriptors |
| Diff toàn file rất lớn | Formatting change trộn với contract change | Phân loại diff và tách pull request |
| Request template đúng, response sai | Chỉ cập nhật một template | Kiểm tra cả hai phía |
| Markdown không render đúng | Dùng helper/cú pháp riêng Asciidoctor | Dùng template và processor Markdown |
| Build pass nhưng cột trống | Không assertion nội dung generated | Thêm snippet regression tests |

## 13. Asciidoctor và build/CI

Tài liệu AsciiDoc include snippet đã sinh:

```adoc
= Product API
:toc: left

== Lấy sản phẩm

=== Request
include::{snippets}/products-get/http-request.adoc[]

=== Response
include::{snippets}/products-get/http-response.adoc[]

=== Response fields
include::{snippets}/products-get/response-fields.adoc[]
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

Pipeline nâng cấp:

```text
Checkout source + lock dependency versions
                |
                v
Run documentation tests
                |
                v
Generate snippets
                |
                v
Compare contract assertions and snippet output
                |
                v
Build Asciidoctor / Markdown
                |
                v
Review diff + publish artifact
```

Lưu baseline và output mới thành artifact để reviewer so sánh. Khi phát hiện diff, phân loại thành contract, template hoặc renderer trước khi chấp nhận. Không tự động cập nhật golden files chỉ vì build mới tạo output khác.

## 14. Bài thực hành

Giả sử dự án nâng cấp Spring REST Docs và có template tùy chỉnh:

1. Chạy test ở version hiện tại và lưu snippets baseline.
2. Nâng dependency trong branch riêng và chạy lại cùng test/fixture.
3. So sánh HTTP status, headers và payload assertions để xác nhận contract.
4. Diff generated snippets theo từng operation.
5. Trích template mặc định từ artifact version đích và so sánh với template override.
6. Kiểm tra Mustache variables, `title`, `label`, `constraints` và fallback.
7. Kiểm tra format ID, file extension và include path.
8. Thêm description chứa pipe và Unicode; xác minh bảng không bị vỡ.
9. Build HTML bằng Asciidoctor/Markdown processor đúng phiên bản.
10. Phân loại diff, cập nhật regression assertions và review artifact trong CI.

### Câu hỏi tự đánh giá

- Ba lớp nào tham gia tạo tài liệu từ HTTP test đến HTML?
- Làm thế nào phân biệt contract drift với rendering change?
- Vì sao cần baseline được tạo từ cùng fixture?
- Nguồn nào xác nhận Mustache variables của version đích?
- Format ID ảnh hưởng tới việc tìm template và extension ra sao?
- Vì sao snippet có thể render thành công nhưng một cột vẫn trống?
- Khi nào cần kiểm tra Asciidoctor thay vì sửa REST Docs template?
- Nên khóa toàn bộ output hay chỉ các giá trị contract quan trọng?
- CI cần lưu và kiểm tra artifact nào để nâng cấp an toàn?

**Ghi nhớ:** Khi snippet thay đổi sau nâng cấp, hãy xác định khác biệt nằm ở HTTP exchange, snippet generation hay document renderer. Tạo baseline, so sánh output theo operation, đối chiếu template mặc định của version đích và kiểm tra cả request lẫn response. Chỉ chấp nhận diff sau khi đã phân loại và xác minh contract không bị thay đổi ngoài ý muốn.

## Tài liệu tham khảo

- [Spring REST Docs — Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html): Mustache templates và custom attributes.
- [Spring REST Docs — Snippet Template Format](https://docs.spring.io/spring-restdocs/reference/configuration/snippet-template-format.html): format ID và template resolution.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field descriptors và payload snippets.
- [Spring REST Docs — Working with Asciidoctor](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/working-with-asciidoctor.html): include và kết xuất tài liệu.
