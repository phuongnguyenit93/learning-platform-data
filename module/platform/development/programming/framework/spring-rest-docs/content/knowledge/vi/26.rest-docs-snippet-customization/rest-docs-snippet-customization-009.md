# Giữ template tương thích khi nâng cấp Spring REST Docs

## 1. Vì sao nâng cấp có thể làm template tùy chỉnh bị lỗi?

Spring REST Docs tạo snippet bằng cách kết hợp dữ liệu từ operation, descriptor và template Mustache. Template tùy chỉnh thường được đặt trong test resources để thay thế template mặc định, ví dụ:

```text
src/test/resources/
└── org/springframework/restdocs/templates/
    └── asciidoctor/
        ├── request-fields.snippet
        └── response-fields.snippet
```

Các file này giúp tài liệu có tiêu đề, tên cột, nhãn hiển thị và quy ước trình bày riêng. Tuy nhiên, template không phải một lớp giao diện độc lập với thư viện. Nó phụ thuộc vào dữ liệu mà Spring REST Docs cung cấp cho snippet, cách template được nạp, format đang chọn và phiên bản của các module tích hợp.

Khi nâng cấp, có thể gặp các tình huống:

- Template tùy chỉnh vẫn được nạp nhưng biến Mustache không còn phù hợp với model.
- Một snippet mặc định có thay đổi nội dung hoặc cách render.
- API Java mà custom snippet sử dụng đã bị deprecated hoặc bị loại bỏ.
- Phiên bản Spring Framework, JUnit, AsciidoctorJ hoặc REST Assured yêu cầu nâng đồng bộ.
- Build vẫn sinh snippet nhưng bảng mất cột, thiếu dữ liệu hoặc lỗi khi Asciidoctor include.
- Tài liệu generated thay đổi quá nhiều khiến reviewer khó phân biệt thay đổi API với thay đổi format.

Trong module **SPRING_REST_DOCS**, tài liệu REST API được tạo từ test HTTP với MockMvc, WebTestClient hoặc REST Assured. Vì vậy, sau nâng cấp cần xác minh cả hai lớp: test vẫn kiểm chứng request/response và template vẫn trình bày đúng dữ liệu đã kiểm chứng.

Bài này thuộc chương **Snippet customization**. Mục tiêu là xây dựng quy trình nâng cấp có thể lặp lại, biết cách so sánh template của phiên bản đích, kiểm tra custom attributes, xác minh generated snippets và đưa việc kiểm tra vào build/CI.

Sau bài học, bạn có thể:

- Xác định các điểm phụ thuộc giữa template và phiên bản thư viện.
- So sánh template tùy chỉnh với template mặc định của phiên bản đích.
- Kiểm tra format ID, tên snippet, Mustache variables và custom attributes.
- Nâng cấp custom snippet dùng `TemplatedSnippet` cùng API operation.
- Phân biệt lỗi do REST Docs, test framework, Asciidoctor và cấu hình build.
- So sánh output trước/sau nâng cấp và thiết kế kiểm tra hồi quy trong CI.

## 2. Những thành phần cần kiểm tra khi nâng cấp

Một hệ thống Spring REST Docs thường có nhiều thành phần liên quan. Không nên chỉ đổi version của `spring-restdocs-*` rồi giả định các phần còn lại giữ nguyên.

| Thành phần | Điều cần xác minh |
| --- | --- |
| Spring REST Docs core | API snippet, operation model, descriptor và template resolution |
| Module tích hợp | `spring-restdocs-mockmvc`, `spring-restdocs-webtestclient` hoặc `spring-restdocs-restassured` |
| Spring Framework | API MockMvc, WebTestClient, multipart, HTTP abstractions và tương thích nền |
| JUnit/Test framework | Extension, lifecycle và phiên bản JUnit được hỗ trợ |
| AsciidoctorJ và plugin | Khả năng build tài liệu, macro và plugin tương thích |
| REST Assured | API multipart/filter và phiên bản tối thiểu được hỗ trợ |
| Custom Mustache templates | Tên biến, cấu trúc model và fallback |
| Custom snippets | Constructor, `createModel`, Operation APIs và output filename |
| Build tool | Cấu hình dependency, test output và thứ tự Asciidoctor task |

Các thành phần phải tương thích trong cùng một tổ hợp. Ví dụ, nâng cấp REST Docs lên major version mới có thể đồng thời yêu cầu phiên bản Spring Framework hoặc AsciidoctorJ mới hơn. Điều kiện cụ thể phụ thuộc release; luôn đọc tài liệu yêu cầu hệ thống và ghi chú phát hành của version đích.

### 2.1. Chốt rõ phiên bản nguồn và phiên bản đích

Trong pull request nâng cấp, ghi rõ:

- Phiên bản Spring REST Docs hiện tại.
- Phiên bản dự định chuyển tới.
- Các module tích hợp được sử dụng.
- Phiên bản Spring Framework và test framework.
- Phiên bản plugin Asciidoctor/REST Assured.
- Bộ template nào đang được override.

Ví dụ bảng theo dõi:

| Thành phần | Trước nâng cấp | Sau nâng cấp |
| --- | --- | --- |
| Spring REST Docs | `3.x.y` | `4.x.y` |
| Spring Framework | `6.x.y` | `7.x.y` nếu release đích yêu cầu |
| AsciidoctorJ | `2.x.y` | `3.x.y` nếu release đích yêu cầu |
| JUnit | `5.x.y` | Phiên bản tương thích với nền mới |
| Custom template format | `asciidoctor` | `asciidoctor` |

Các giá trị chỉ mang tính minh họa. Không sao chép bảng này thành ma trận tương thích chính thức; hãy điền version được xác nhận từ release notes và dependency management của dự án.

## 3. Hiểu hợp đồng giữa snippet và Mustache template

Spring REST Docs dùng template format để tìm template trên classpath. Format mặc định là Asciidoctor, có ID `asciidoctor`; Markdown cũng được hỗ trợ với format ID tương ứng.

Ví dụ override:

```text
src/test/resources/org/springframework/restdocs/templates/asciidoctor/
└── request-fields.snippet
```

Tên template gắn với tên snippet:
- `request-fields.snippet` tạo `request-fields.adoc`.
- `response-fields.snippet` tạo `response-fields.adoc`.
- `http-request.snippet` tạo `http-request.adoc`.

Một template request fields có thể dùng các biến như:

```adoc
{{#title}}
.{{title}}
{{/title}}
|===
|Path|Type|Description|Constraints

{{#fields}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}

{{/fields}}
|===
```

Template dựa vào model mà snippet tương ứng cung cấp. `title` có thể là snippet attribute; `constraints` có thể là descriptor attribute; `fields` là tập dữ liệu field. Khi nâng cấp, không nên giả định rằng mọi snippet sử dụng cùng một model hoặc có cùng các biến.

Các nguyên tắc:

1. Tên snippet quyết định template được tìm.
2. Format ID quyết định package template trên classpath.
3. Mustache variable phải khớp key có trong model.
4. Custom attribute phải được gắn ở đúng cấp: descriptor hay snippet.
5. Fallback cần có cho attribute tùy chọn.
6. Template phải dùng cú pháp phù hợp với output format.

Đổi tên biến trong template mà không kiểm tra model có thể làm cột trống nhưng không nhất thiết khiến test HTTP thất bại. Vì vậy, kiểm tra snippet generated là một bước riêng bắt buộc.

## 4. So sánh với template mặc định của phiên bản đích

Khi nâng version, nguồn đối chiếu tốt nhất là template mặc định được đóng gói cùng đúng artifact Spring REST Docs mục tiêu. Tài liệu trực tuyến có thể mô tả cách tùy biến, nhưng để biết chính xác các biến và cấu trúc model của release đích, cần kiểm tra template nằm trong JAR tương ứng.

Quy trình:

1. Tải dependency version đích qua build hoặc xem artifact từ Maven repository.
2. Mở JAR như một file ZIP.
3. Tìm package template theo format ID, ví dụ `org/springframework/restdocs/templates/asciidoctor/`.
4. Sao chép template mặc định của đúng snippet cần override vào thư mục tạm để so sánh.
5. Dùng diff để xác định thay đổi trong nội dung, Mustache sections và variables.
6. Chỉ đưa các thay đổi cần thiết vào template tùy chỉnh.

Có thể dùng lệnh `jar` để liệt kê nội dung artifact:

```bash
jar tf spring-restdocs-core-<target-version>.jar
```

Sau khi tìm được file template trong JAR, có thể đọc nội dung bằng công cụ ZIP hoặc giải nén vào thư mục làm việc tạm. Không giải nén đè lên `src/test/resources`; mục đích là so sánh, không thay thế template đang dùng.

### 4.1. Tạo bản diff có thể review

Ví dụ:

```bash
git diff --no-index \
  baseline/request-fields.snippet \
  target/request-fields.snippet
```

Trong đó:
- `baseline` là template được đóng gói trong version đang sử dụng.
- `target` là template mặc định trong version đích.

Sau đó so sánh template tùy chỉnh với target để xác định phần override còn cần thiết:

```bash
git diff --no-index \
  target/request-fields.snippet \
  src/test/resources/org/springframework/restdocs/templates/asciidoctor/request-fields.snippet
```

Diff cần được đọc theo ngữ nghĩa:
- Template mới có thêm hoặc bỏ biến nào?
- Có thay đổi section `{{#...}}` hay inverted section `{{^...}}` không?
- Có thêm lambda hoặc helper cho escaping không?
- Cấu trúc bảng có thay đổi không?
- Cột do dự án thêm có giữ được fallback không?

Không copy toàn bộ template mới vào project rồi xóa các customizations hiện có. Trước hết cần hiểu phần thay đổi upstream, sau đó merge có chủ đích.

## 5. Giữ custom attributes hoạt động sau nâng cấp

Giả sử template dùng cột `constraints` và `title`:

```java
requestFields(
    attributes(key("title").value("Thông tin tạo đơn")),
    fieldWithPath("email")
        .description("Email nhận thông báo")
        .attributes(key("constraints").value("Đúng định dạng email"))
);
```

Template:

```adoc
{{#title}}
.{{title}}
{{/title}}
|===
|Path|Type|Description|Constraints

{{#fields}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}

{{/fields}}
|===
```

Sau nâng cấp, hãy xác minh từng lớp:

| Câu hỏi | Cách kiểm tra |
| --- | --- |
| Snippet attributes còn được truyền không? | Kiểm tra lời gọi `requestFields(...)` và output title |
| Descriptor attributes còn được truyền không? | Kiểm tra từng field có đúng key |
| Template còn đọc đúng key không? | So sánh Mustache variables |
| Field thiếu attribute có làm template lỗi không? | Chạy test với descriptor không có custom attribute |
| Field optional/ignored còn đúng không? | Chạy test có và không có field optional |
| Bảng có hiển thị đầy đủ dữ liệu không? | Đọc generated snippet hoặc assertion trên output |

Đặc biệt, attribute tùy chỉnh không phải API validation. `constraints` là nội dung do dự án cung cấp; Spring REST Docs không tự chạy Bean Validation chỉ vì template hiển thị cột đó.

### 5.1. Có fallback để tránh cell trống ngoài ý muốn

Nếu một field không có `label`, template có thể fallback về `path`:

```adoc
{{#fields}}
|{{#label}}{{label}}{{/label}}{{^label}}{{path}}{{/label}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}

{{/fields}}
```

Nếu `constraints` có thể vắng, có thể hiển thị `—` bằng cách cung cấp giá trị mặc định khi tạo model/descriptor hoặc dùng quy ước template đã được kiểm thử. Đừng dựa vào cách Mustache render `null` mà không xác minh output của renderer thực tế.

## 6. Nâng cấp custom snippet dùng `TemplatedSnippet`

Custom snippet thường phụ thuộc API `TemplatedSnippet` và operation model. Các phần cần rà soát:

- Constructor của snippet và cách truyền `snippetName`, `templateName`, attributes.
- Kiểu trả về và visibility của `createModel(Operation)`.
- Các phương thức `Operation`, `OperationRequest`, `OperationResponse` và `OperationRequestPart` mà snippet gọi.
- Kiểu dữ liệu của status, URI, headers, content và parts.
- Cơ chế nạp template và ghi output.
- Exception được phát sinh khi model không đủ dữ liệu.

Ví dụ custom snippet:

```java
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
        return model;
    }
}
```

Khi nâng version:
1. Compile custom snippet với API đích.
2. Kiểm tra import và method signature theo Javadoc/artifact của version đích.
3. Xử lý trường hợp header không tồn tại hoặc collection parts rỗng.
4. Xác minh template vẫn được tìm đúng format.
5. Chạy test để kiểm tra file output và nội dung.

Nếu một API đã deprecated ở version nguồn, đừng chỉ suppress warning. Kiểm tra replacement và thời hạn loại bỏ trong release notes. Nếu API đã bị gỡ ở major version, sửa code theo API thay thế trước khi nâng build toàn bộ.

## 7. Những thay đổi lớn cần kiểm tra khi chuyển major version

Một major version có thể thay đổi baseline Java, Spring Framework, test framework và công cụ kết xuất. Ví dụ, thông tin phát hành chính thức của Spring REST Docs 4.0.0 nêu một số thay đổi nền tảng như loại bỏ API deprecated, ngừng hỗ trợ JUnit 4 và nâng yêu cầu tối thiểu của các dependency nền. Đây là lý do cần đọc release notes thay vì giả định nâng cấp chỉ liên quan tới template.

Checklist cho major upgrade:

- Đọc release notes của từng major/minor đi qua, không chỉ bản đích.
- Kiểm tra minimum Java và Spring Framework.
- Kiểm tra JUnit version và cách cấu hình extension.
- Kiểm tra AsciidoctorJ, Gradle plugin và template format.
- Kiểm tra REST Assured version nếu dùng module này.
- Tìm API deprecated/removal trong custom snippet và test utility.
- Build một test đại diện cho mỗi module tích hợp đang dùng.
- Kiểm tra output của toàn bộ snippet đã override.
- Kiểm tra tài liệu Asciidoctor sau khi include snippet.

Không nâng đồng thời nhiều thư viện lớn nếu chưa có ma trận kiểm tra rõ. Khi có thể, nâng từng nhóm phụ thuộc và lưu lại kết quả để xác định nguyên nhân nếu có regression.

## 8. Kiểm thử hồi quy cho template

Build thành công chỉ chứng minh Java/template được xử lý ở mức nhất định; nó chưa bảo đảm output giữ đúng nội dung mong muốn. Nên có test tài liệu hóa đại diện cho các trường hợp sau:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Request fields chuẩn | Path, type và description |
| Response fields chuẩn | Field response và thứ tự cột |
| Custom title | Tiêu đề được render đúng |
| Custom label | Label hiển thị, path kỹ thuật vẫn được giữ |
| Constraint/example | Cột bổ sung nhận đúng giá trị |
| Descriptor không có custom attribute | Fallback không làm vỡ bảng |
| Optional field | Snippet được tạo khi field vắng |
| Ignored field | Field được kiểm tra nhưng không có dòng |
| Nested fields/array | Path `a.b` và `items[]` hiển thị chính xác |
| Ký tự đặc biệt | `|`, dấu ngoặc và xuống dòng không phá bảng |
| HTTP request/response | Method, URI, status và headers không mất |
| Markdown format | Template đúng format ID và renderer hiểu bảng |

### 8.1. Kiểm tra nội dung generated snippet

Có thể dùng test đọc output file sau khi document operation chạy:

```java
Path snippet = snippetsDir
        .resolve("orders-create")
        .resolve("request-fields.adoc");

String generated = Files.readString(snippet);

assertThat(generated)
        .contains("Các trường tạo đơn hàng")
        .contains("customerId")
        .contains("Số nguyên dương");
```

Đây là ví dụ với AssertJ; cấu hình test của dự án cần xác định `snippetsDir` đúng và đảm bảo assertion chạy sau khi Spring REST Docs đã ghi file.

Ưu tiên assert các nội dung mang ý nghĩa contract. Nếu assert toàn bộ whitespace, dấu cách hoặc line wrapping, thay đổi định dạng nhỏ có thể tạo nhiều test failure không có giá trị. Nếu output là artifact công khai cần ổn định tuyệt đối, có thể dùng golden file, nhưng phải review và cập nhật golden file cùng template một cách có chủ đích.

### 8.2. So sánh output trước và sau nâng cấp

Tạo hai bộ output từ cùng một commit và cùng fixture:
- `snippets-before`: sinh với version nguồn.
- `snippets-after`: sinh với version đích và template đã cập nhật.

So sánh theo operation và snippet name. Phân loại diff:
1. **Thay đổi có chủ đích:** template mới thêm cột hoặc đổi title.
2. **Thay đổi do upstream:** format mặc định hoặc model thay đổi.
3. **Regression:** field biến mất, giá trị rỗng, title sai, path không còn.
4. **Thay đổi HTTP contract:** request/response thực sự đổi do code ứng dụng.

Không gộp cả bốn nhóm thành một lần cập nhật golden file mà không giải thích. Reviewer cần biết điều gì thay đổi vì API và điều gì thay đổi vì renderer.

## 9. Kiểm tra riêng từng template format

Nếu dự án hỗ trợ cả Asciidoctor và Markdown, mỗi format có package template riêng:

```text
src/test/resources/org/springframework/restdocs/templates/
├── asciidoctor/
│   ├── request-fields.snippet
│   └── response-fields.snippet
└── markdown/
    ├── request-fields.snippet
    └── response-fields.snippet
```

Cấu hình Markdown trên MockMvc có dạng:

```java
this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
    .apply(documentationConfiguration(this.restDocumentation)
        .snippets()
        .withTemplateFormat(TemplateFormats.markdown()))
    .build();
```

Cần xác minh:
- Test thật sự đang dùng format nào.
- Template được nạp từ đúng package.
- Output extension đúng, ví dụ `.adoc` hoặc `.md`.
- Cú pháp bảng phù hợp với renderer đích.
- Các lambda hỗ trợ riêng cho Asciidoctor không bị dùng nhầm trong Markdown.
- Pipeline include Markdown có công cụ xử lý include riêng, vì Markdown không có cơ chế include chuẩn như Asciidoctor.

Một bộ template Asciidoctor chạy tốt không chứng minh bộ Markdown cũng tương thích.

## 10. Dependency và build configuration

Nâng version Spring REST Docs thường cần cập nhật đồng bộ module test và plugin tài liệu.

Ví dụ Gradle khai báo:

```groovy
dependencies {
    testImplementation "org.springframework.restdocs:spring-restdocs-mockmvc:${restdocsVersion}"
    // Hoặc dùng spring-restdocs-webtestclient khi dự án dùng WebTestClient.
    // Chỉ thêm spring-restdocs-restassured nếu dự án thực sự sử dụng REST Assured.
}
```

Nếu dự án dùng version catalog hoặc Spring dependency management, cập nhật tại nguồn version tập trung thay vì hard-code từng dependency.

Kiểm tra dependency graph để phát hiện:
- Hai phiên bản Spring REST Docs bị kéo đồng thời.
- Module tích hợp không cùng version với core.
- Spring Framework bị override bởi version không tương thích.
- JUnit hoặc REST Assured cũ còn được kéo từ test utility.
- AsciidoctorJ/plugin không đáp ứng baseline của bản đích.

Đừng thay dependency bằng phiên bản mới nhất một cách tùy tiện. Chọn một version đích đã được kiểm tra cùng Spring Boot/Spring Framework và build tool của ứng dụng.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Template tùy chỉnh không được dùng | Sai package format ID, sai tên template hoặc resource không có trên test classpath | Kiểm tra đường dẫn và tên snippet |
| Build pass nhưng cột custom trống | Mustache variable không có trong model | Đối chiếu template mặc định target và attributes |
| Title mất sau nâng cấp | Snippet attribute không được truyền hoặc template không đọc `title` | Kiểm tra overload và model output |
| Custom snippet không compile | API hoặc method signature đã thay đổi | Đọc Javadoc/release notes và cập nhật code |
| Bảng bị lệch | Số cell/header không khớp hoặc escaping thay đổi | Render snippet và kiểm tra renderer đích |
| `request-fields` đúng nhưng `response-fields` sai | Chỉ một trong hai template được nâng cấp | Cập nhật/test cả hai template |
| Markdown không dùng template mới | Format ID không phải `markdown` hoặc test chưa cấu hình format | Kiểm tra `TemplateFormats.markdown()` |
| Asciidoctor không include snippet | Build task chạy trước test hoặc đường dẫn output sai | Khai báo task dependency và snippets input |
| Diff snippet quá lớn | Thay đổi formatting trộn với thay đổi API | Phân loại diff theo template, operation và contract |
| Test assertion vỡ vì whitespace | Assertion khóa chi tiết trình bày mong manh | Assert field/value có ý nghĩa hoặc dùng golden file có review |
| Build major mới thiếu JUnit/API | Baseline đã thay đổi | Kiểm tra yêu cầu phiên bản và cập nhật test framework |

## 12. Quy trình nâng cấp đề xuất

Có thể áp dụng tuần tự:

```text
Ghi nhận version nguồn và version đích
              |
              v
Đọc release notes + system requirements
              |
              v
Kiểm tra dependency/module compatibility
              |
              v
Lấy template mặc định của version đích
              |
              v
Diff với template đang override
              |
              v
Cập nhật custom templates và custom snippets
              |
              v
Chạy test tài liệu hóa + assertion output
              |
              v
So sánh snippets trước/sau
              |
              v
Kết xuất Asciidoctor/Markdown
              |
              v
Review diff và merge nâng cấp
```

Ở mỗi bước, lưu kết quả kiểm tra để pull request có thể giải thích:
- Version nào thay đổi.
- Template nào được sửa.
- Custom attribute hoặc API nào được cập nhật.
- Snippet nào có diff.
- Vì sao diff đó được chấp nhận.

## 13. Build và CI

Một pipeline Gradle cơ bản cần đảm bảo test sinh snippet chạy trước Asciidoctor:

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

Nếu pipeline có bước lưu snapshot trước/sau nâng cấp, có thể lưu snippet output thành artifact của CI để reviewer tải xuống so sánh. Không để file snapshot cũ trong thư mục generated đang được ghi đè bởi test.

Các stage nên gồm:
1. Compile test và custom snippet.
2. Chạy test tài liệu hóa bằng từng integration module.
3. Assert các snippet quan trọng được tạo và có nội dung.
4. Build Asciidoctor hoặc Markdown output.
5. Kiểm tra include không bị thiếu.
6. Lưu diff/artifact snippet nếu đây là pull request nâng phiên bản.

Ví dụ điều kiện chấp nhận nâng cấp:
- Không còn lỗi compile do API cũ.
- Các operation quan trọng đều sinh snippet.
- Không mất path/type/description hoặc custom attributes.
- Các format được hỗ trợ đều render đúng.
- Các thay đổi output đã được review và phân loại.
- Build tài liệu chạy lại độc lập và tái lập được.

## 14. Bài thực hành

Giả sử dự án có `request-fields.snippet` và `response-fields.snippet` tùy chỉnh:

1. Ghi version Spring REST Docs hiện tại và chọn version đích từ release notes.
2. Xác định các module tích hợp và version Spring Framework, JUnit, AsciidoctorJ đang dùng.
3. Trích xuất template mặc định `request-fields.snippet` từ artifact nguồn và đích.
4. Dùng diff để tìm thay đổi Mustache variables và cấu trúc bảng.
5. Cập nhật template request nhưng giữ custom `label`, `constraints` và `title`.
6. Lặp lại với `response-fields.snippet`; xác nhận cột example không bị mất.
7. Compile `TemplatedSnippet` riêng và cập nhật API đã deprecated/removed nếu có.
8. Chạy test đại diện có label, không có label, optional field và nested field.
9. Sinh snippets ở cả Asciidoctor và Markdown nếu dự án hỗ trợ hai format.
10. So sánh output trước/sau; phân loại diff formatting, upstream và API contract.
11. Build tài liệu trong CI và review artifact.
12. Ghi lại các thay đổi cần chú ý cho lần nâng cấp tiếp theo.

### Câu hỏi tự đánh giá

- Vì sao custom template phụ thuộc vào version Spring REST Docs?
- Template được tìm dựa vào những yếu tố nào?
- Nguồn nào đáng tin cậy để kiểm tra biến Mustache của version đích?
- Vì sao build pass chưa đủ để kết luận template tương thích?
- Descriptor attributes và snippet attributes cần được kiểm tra ở đâu?
- Custom `TemplatedSnippet` cần rà soát các phần API nào?
- Vì sao phải test Asciidoctor và Markdown riêng?
- Làm thế nào tách diff do format khỏi diff do API contract?
- Khi giới hạn upload hoặc error snippet thay đổi, làm sao xác nhận đó là thay đổi chủ đích?
- CI nên kiểm tra những điều kiện nào trước khi chấp nhận nâng cấp?

**Ghi nhớ:** Giữ template tương thích bằng cách coi nó là giao diện phụ thuộc phiên bản. Đối chiếu template mặc định trong artifact đích, rà soát Mustache variables và custom attributes, cập nhật custom snippet theo API mới, rồi chạy test và so sánh output ở từng format. Build thành công chỉ là một phần; reviewer cần thấy các snippet vẫn đầy đủ, chính xác và không mất nội dung tùy biến.

## Tài liệu tham khảo

- [Spring REST Docs — Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html): Mustache template, classpath và attributes.
- [Spring REST Docs — Snippet Template Format](https://docs.spring.io/spring-restdocs/reference/configuration/snippet-template-format.html): Asciidoctor/Markdown và cách chọn template format.
- [Spring REST Docs — System Requirements](https://docs.spring.io/spring-restdocs/reference/index.html): yêu cầu phiên bản nền của Spring REST Docs.
- [Spring REST Docs 4.0.0 Release](https://spring.io/blog/2025/11/18/spring-restdocs-4-0-0): thay đổi major version và dependency baseline.
- [Spring REST Docs 4.0.1 Release](https://spring.io/blog/2026/06/09/spring-restdocs-4/): bug fixes và dependency upgrades của bản 4.0.1.
