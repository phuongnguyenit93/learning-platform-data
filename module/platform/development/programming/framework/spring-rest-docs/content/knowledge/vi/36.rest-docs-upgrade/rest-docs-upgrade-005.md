# Kiểm tra template và snippet sau khi nâng cấp

## 1. Mục tiêu

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ test HTTP dùng MockMvc, WebTestClient hoặc REST Assured. Test sinh snippet cho request, response, payload, header, parameter và multipart part; Asciidoctor kết hợp snippet với template và nội dung AsciiDoc để tạo tài liệu.

Sau khi nâng Spring Boot, Spring Framework, Spring REST Docs, Spring Test hoặc Asciidoctor, build có thể vẫn chạy nhưng output tài liệu thay đổi. Nguyên nhân có thể là formatter, serialization, default header, đường dẫn snippet, template extension hoặc phiên bản Asciidoctor.

Bài này hướng dẫn kiểm tra có hệ thống:

- Test còn sinh đủ snippet và operation ID như trước không?
- Nội dung snippet có thay đổi ngoài dự kiến không?
- Template và AsciiDoc include còn tương thích không?
- HTML kết quả có đủ endpoint, fields, links, CSS và ảnh không?
- CI có phát hiện thay đổi tài liệu ngoài ý muốn không?

## 2. Xác định baseline trước khi nâng cấp

Trước khi thay dependency/plugin, lưu một baseline có thể so sánh:

1. Commit/source revision đang phát hành.
2. Java, Spring Boot, Spring Framework, Spring REST Docs và Asciidoctor versions.
3. Lệnh build tạo snippets và HTML.
4. Danh sách operation ID và file snippet được sinh.
5. Một số snippet đại diện cho request, response, fields, headers, parameters và payload.
6. HTML output và các asset cần thiết.

Ví dụ cấu trúc output:

```text
target/
├── generated-snippets/
│   ├── users-get/
│   │   ├── http-request.adoc
│   │   ├── http-response.adoc
│   │   ├── path-parameters.adoc
│   │   └── response-fields.adoc
│   └── users-create/
│       ├── http-request.adoc
│       ├── request-fields.adoc
│       └── http-response.adoc
└── generated-docs/
    ├── index.html
    ├── css/
    └── images/
```

Không coi toàn bộ generated output là golden file một cách máy móc. Chọn các snippet đại diện và xác định phần nào phải ổn định, phần nào có thể thay đổi hợp lệ như timestamp, boundary multipart hoặc generated metadata.

## 3. Giữ test data và HTTP request xác định

Snippet phản ánh request/response thực tế mà test gửi và nhận. Nếu fixture không ổn định, diff sau nâng cấp sẽ nhiễu và khó xác định thay đổi do dependency hay do dữ liệu test.

Ví dụ test dùng dữ liệu cố định:

```java
mockMvc.perform(get("/users/{id}", "42")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("users-get",
        pathParameters(
            parameterWithName("id").description("Mã người dùng")
        ),
        responseFields(
            fieldWithPath("id").description("Mã người dùng"),
            fieldWithPath("name").description("Tên người dùng")
        )
    ));
```

Để snippet ổn định:

- Dùng fixture cố định, không phụ thuộc dữ liệu đang có trong database dùng chung.
- Không sinh ID ngẫu nhiên nếu ID đó xuất hiện trong tài liệu.
- Cố định clock khi response có timestamp.
- Tránh phụ thuộc thứ tự collection nếu contract không bảo đảm thứ tự.
- Dùng locale/timezone xác định khi format ngày giờ.
- Không đưa token, mật khẩu hoặc dữ liệu cá nhân thật vào request/response mẫu.

Với REST Assured hoặc WebTestClient, nguyên tắc tương tự: request body, header và response phải tái lập được qua các lần chạy.

## 4. Kiểm tra operation ID và tập snippet

Operation ID trong hàm document là tên thư mục chứa snippet. Ví dụ:

```java
.andDo(document("users-get", ...))
```

tạo output trong thư mục §users-get§. File AsciiDoc include phải dùng đúng tên:

```asciidoc
include::{snippets}/users-get/http-request.adoc[]
include::{snippets}/users-get/http-response.adoc[]
include::{snippets}/users-get/response-fields.adoc[]
```

Nếu đổi operation ID, template cũ có thể báo missing include hoặc vô tình tham chiếu snippet của operation khác. Sau nâng cấp, đối chiếu:

- Số operation được test thực thi.
- Tên thư mục snippet.
- Danh sách file trong mỗi thư mục.
- Include path trong AsciiDoc.
- Các snippet handler thực sự được cấu hình trong test.

Không chỉ kiểm tra thư mục có tồn tại; thư mục có thể còn file cũ từ build trước. Dùng clean build để phân biệt output hiện tại và stale output.

## 5. So sánh snippet trước và sau nâng cấp

Thực hiện build sạch trên revision trước và revision sau nâng cấp, dùng cùng JDK/toolchain, profile và dữ liệu test. So sánh file theo operation ID.

Ví dụ PowerShell:

```powershell
Get-ChildItem target/generated-snippets -Recurse -File |
    ForEach-Object { $_.FullName.Substring((Resolve-Path target/generated-snippets).Path.Length) } |
    Sort-Object
```

Để tạo checksum cho các file:

```powershell
Get-ChildItem target/generated-snippets -Recurse -File |
    Get-FileHash -Algorithm SHA256 |
    Sort-Object Path
```

Với Git Bash/Linux/macOS có thể dùng:

```bash
find target/generated-snippets -type f | sort
find target/generated-snippets -type f -print0 | sort -z | xargs -0 sha256sum
```

Hash giúp phát hiện file thay đổi, nhưng không giải thích nội dung thay đổi. Với file khác nhau, dùng diff văn bản để xác định:

- Header mới/mất đi.
- JSON formatting hoặc field order thay đổi.
- Request/response body thay đổi.
- Field descriptor hoặc description bị thiếu.
- Path, query parameter hoặc content type khác.

Phân loại mỗi diff thành thay đổi contract, thay đổi định dạng hợp lệ, thay đổi fixture hoặc regression. Không cập nhật golden files chỉ để CI xanh khi chưa hiểu nguyên nhân.

## 6. Kiểm tra template AsciiDoc và extension

Spring REST Docs Asciidoctor extension cung cấp thuộc tính snippets và các macro liên quan. Ví dụ:

```asciidoc
= User API
:toc: left

== GET /users/{id}

=== Request
include::{snippets}/users-get/http-request.adoc[]

=== Response
include::{snippets}/users-get/http-response.adoc[]

=== Response fields
include::{snippets}/users-get/response-fields.adoc[]
```

Sau khi nâng cấp, kiểm tra:

1. Plugin Asciidoctor vẫn load extension Spring REST Docs.
2. Thuộc tính snippets trỏ tới đúng generated-snippets directory.
3. Base directory và source directory không bị đổi ngoài ý muốn.
4. Tất cả include path trỏ tới file tồn tại.
5. Attribute, macro và syntax được plugin version mới hỗ trợ.
6. Các template custom của project vẫn được include đúng.

Nếu log báo missing attribute hoặc include file, xác minh plugin dependency và extension classpath trước khi sửa template. Không thay đường dẫn include thành path máy cá nhân.

## 7. Kiểm tra template tùy chỉnh

Project có thể tùy chỉnh snippet template để đổi cách trình bày request/response. Khi nâng Spring REST Docs, template custom có thể không còn khớp với context hoặc model mà version mới cung cấp.

Quy trình kiểm tra:

- Liệt kê template custom đang override.
- Xác định snippet nào sử dụng template đó.
- So sánh output của snippet mặc định với output custom.
- Kiểm tra placeholder/context được template tham chiếu.
- Render thử với request có header, body, query parameter và response lỗi.
- Xác nhận template không bỏ mất dữ liệu quan trọng.

Không sao chép template nội bộ của version cũ sang version mới mà không đối chiếu implementation/documentation của release mới. Nếu không cần thay đổi giao diện, ưu tiên template mặc định để giảm chi phí bảo trì.

### 7.1. Ví dụ một ma trận kiểm tra template

| Snippet | Test case cần có | Nội dung cần xác minh |
| --- | --- | --- |
| http-request | GET có path/query/header | Method, URI, headers |
| http-response | 200 và lỗi 4xx | Status, headers, body |
| request-fields | JSON nested object | Path, type, description, optionality |
| response-fields | Array và nested object | Field path, type, description |
| path-parameters | Endpoint có biến path | Tên và mô tả parameter |
| request-parameters | Query/form parameters | Tên, required/optional, description |
| request-parts | Multipart upload | Part name, content type, mô tả |

## 8. Kiểm tra nội dung snippet theo từng nhóm

### 8.1. Request và response

Kiểm tra method, URL, status code, Content-Type, Accept và các header quan trọng. Nếu một header biến mất sau nâng cấp, xác minh test có gửi header đó và handler có capture nó không.

### 8.2. Payload và field descriptors

Kiểm tra field path, type, description, optionality, ignored fields và relaxed mode. Với JSON nested/array, xác minh đường dẫn mô tả vẫn phản ánh đúng cấu trúc payload.

Không dùng relaxed descriptors để che giấu regression. Nếu một field mới xuất hiện ngoài contract, quyết định rõ field đó cần được mô tả, ignore có chủ đích hay test phải thất bại.

### 8.3. Parameters và headers

Kiểm tra path parameters, query parameters, form parameters và request headers. Một số handler tạo snippet riêng; việc test chạy thành công không có nghĩa mọi snippet đều đã được yêu cầu sinh.

### 8.4. Multipart và binary

Multipart boundary có thể thay đổi giữa các lần chạy. Không so sánh byte-for-byte phần boundary nếu nó không thuộc contract. Tập trung kiểm tra part name, content type, filename và payload được mô tả.

## 9. Kiểm tra HTML sau Asciidoctor

Snippet đúng chưa đủ; tài liệu HTML cuối cùng cũng phải được kiểm tra. Chạy pipeline tài liệu:

```bash
./mvnw clean test
./mvnw prepare-package
```

Hoặc Gradle:

```bash
./gradlew clean test asciidoctor
```

Kiểm tra:

- HTML entry point được tạo.
- Các section/operation mong đợi xuất hiện.
- Không có placeholder chưa resolve như snippets attribute.
- Không có include warning/error.
- Link giữa các trang hoạt động.
- CSS, JavaScript, ảnh và font tồn tại.
- Anchor, table of contents và code block hiển thị đúng.

HTML có thể được tạo nhưng thiếu nội dung nếu include bị bỏ qua hoặc template không còn được gọi. Vì vậy hãy kiểm tra cả nội dung văn bản/heading, không chỉ exit code của build.

## 10. Tự động hóa kiểm tra trong CI

CI nên thực hiện clean build để snippets cũ không che giấu việc test không sinh output. Ví dụ Maven:

```bash
./mvnw clean package
```

Gradle:

```bash
./gradlew clean bootJar
```

Có thể thêm bước kiểm tra cấu trúc output:

```bash
test -f target/generated-snippets/users-get/http-request.adoc
test -f target/generated-snippets/users-get/http-response.adoc
test -f target/generated-docs/index.html
```

Điều chỉnh path theo build tool và output directory thật của dự án. Với Gradle, thường kiểm tra dưới build/generated-snippets và build/docs/asciidoc hoặc outputDir đã cấu hình.

Để phát hiện thay đổi không mong muốn, CI có thể:

1. Sinh snippets từ clean checkout.
2. So sánh danh sách operation/file với manifest mong đợi.
3. Chạy Asciidoctor và fail nếu include/attribute warning được coi là lỗi.
4. Kiểm tra HTML entry point và các asset thiết yếu.
5. Lưu snippet diff hoặc docs artifact làm build artifact để reviewer kiểm tra.

Không nhất thiết commit toàn bộ generated snippets vào Git. Nếu repository chọn lưu golden output, quy định rõ cách cập nhật và yêu cầu review nội dung diff.

## 11. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Snippet folder thiếu sau clean build | Test không chạy, test bị skip hoặc operation không được gọi | Kiểm tra test discovery và build flags |
| Include file không tồn tại | Operation ID đổi hoặc handler không sinh snippet đó | So khớp document ID, handler và include path |
| Snippet khác nhiều sau upgrade | Formatter/serializer/default header hoặc fixture thay đổi | Diff nội dung và phân loại từng thay đổi |
| Template custom lỗi | Context/placeholder hoặc extension behavior đổi | Đối chiếu template với release mới |
| Asciidoctor không nhận snippets | Extension không load hoặc attribute path sai | Kiểm tra plugin dependencies và configuration |
| HTML thiếu section | Include bị bỏ, source file khác hoặc operation thiếu | Kiểm tra log, source tree và snippet list |
| HTML có link hỏng | Asset path thay đổi hoặc không copy toàn bộ output | Kiểm tra relative links và archive |
| CI pass nhưng docs stale | Build không clean hoặc task input/output khai báo thiếu | Clean build và kiểm tra task graph |
| Multipart diff luôn thay đổi | Boundary được tạo động | Bỏ qua phần biến thiên không thuộc contract; kiểm tra part semantics |

## 12. Bài thực hành

Thực hiện một lần nâng cấp giả lập cho API User:

1. Chạy baseline trên revision hiện tại và lưu generated-snippets.
2. Ghi danh sách operation ID cùng các snippet file mong đợi.
3. Chạy test có GET user, POST user, query parameter và response fields.
4. Nâng một dependency/plugin trong nhánh thử nghiệm.
5. Chạy clean test và tạo snippets mới.
6. So sánh file list, hash và nội dung snippet trước/sau.
7. Kiểm tra template custom và AsciiDoc include.
8. Chạy Asciidoctor; kiểm tra HTML, headings, links và assets.
9. Tạo JAR và xác minh docs đã được đóng gói nếu dự án phục vụ docs từ ứng dụng.
10. Ghi lại từng diff là expected hay regression và yêu cầu reviewer xác nhận.

**Tiêu chí hoàn thành:** có baseline; test sinh đủ snippet; operation ID/include nhất quán; template hoạt động; HTML đầy đủ; CI phát hiện được output thiếu hoặc thay đổi ngoài dự kiến.

## 13. Câu hỏi tự kiểm tra

**1. Vì sao cần clean build trước khi kiểm tra snippets?**

Để file còn sót từ lần build trước không làm ta tưởng test hiện tại đã sinh đủ output.

**2. Operation ID ảnh hưởng đường dẫn snippet thế nào?**

Operation ID tạo thư mục output; AsciiDoc include phải dùng cùng tên.

**3. Vì sao test pass chưa chứng minh template đúng?**

Test chỉ xác minh request/response và tạo snippet theo handler được gọi. Asciidoctor/template vẫn có thể lỗi hoặc bỏ mất nội dung khi render.

**4. Nên xử lý snippet diff sau nâng cấp ra sao?**

Phân loại thay đổi contract, formatting hợp lệ, fixture biến động và regression; không cập nhật baseline một cách máy móc.

**5. Vì sao cần kiểm tra cả HTML và assets?**

Trang có thể được tạo nhưng thiếu section, CSS, ảnh hoặc link do include/path sai.

**6. Multipart boundary có phải lúc nào cũng cần giống nhau?**

Không. Boundary thường là dữ liệu transport biến thiên; kiểm tra part semantics thay vì yêu cầu boundary cố định nếu nó không thuộc contract.

## Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): cấu hình test, generated snippets và Asciidoctor.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/): snippet generation, descriptors và template customization.
- [Asciidoctor Maven Plugin](https://docs.asciidoctor.org/maven-tools/latest/): xử lý AsciiDoc trong Maven build.
- [Asciidoctor Gradle Plugin](https://docs.asciidoctor.org/gradle-plugin/latest/): task Asciidoctor và cấu hình output.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): khai báo task inputs/outputs để build có thể tái lập.

