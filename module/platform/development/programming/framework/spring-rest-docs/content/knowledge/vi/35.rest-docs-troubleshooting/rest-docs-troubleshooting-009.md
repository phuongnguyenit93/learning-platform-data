# Markdown include sai đường dẫn trong Spring REST Docs

## 1. Vì sao include không tìm thấy snippet?

Spring REST Docs sinh snippet vào output directory, mỗi operation nằm trong thư mục được xác định bởi document identifier. Ví dụ:

```text
build/
  generated-snippets/
    orders/
      get-by-id/
        http-request.adoc
        http-response.adoc
        curl-request.adoc
```

Tài liệu Asciidoctor thường include snippet bằng đường dẫn tương đối với attribute như `{snippets}`. Nếu attribute trỏ sai output root, identifier trong include không khớp, test chưa sinh snippet hoặc build chạy sai thứ tự, Asciidoctor báo không tìm thấy file.

Với Markdown, cú pháp include không phải tính năng chuẩn. Spring REST Docs có thể sinh snippet dạng Markdown, nhưng cách nhúng snippet vào trang tổng hợp phụ thuộc generator, template hoặc static-site tool của dự án. Không mặc định cú pháp `include::...[]` của Asciidoctor cũng hoạt động trong file .md.

Module **SPRING_REST_DOCS** tạo tài liệu REST API có thể kiểm chứng từ HTTP tests bằng MockMvc, WebTestClient hoặc REST Assured. Test sinh snippet cho request, response, payload, parameter và header; sau đó biên soạn Asciidoctor/Markdown và đưa vào build/CI. Bài thuộc chương **Chẩn đoán lỗi**, tập trung chẩn đoán Markdown/Asciidoctor include sai đường dẫn và cách nối đúng output snippet vào tài liệu.

Sau bài học, bạn có thể:

1. Phân biệt output directory, document identifier và snippet filename.
2. Kiểm tra giá trị snippets attribute và đường dẫn include thực tế.
3. Sửa include khi đổi identifier hoặc output directory.
4. Cấu hình Gradle/Maven để test sinh snippet trước khi render.
5. Phân biệt Asciidoctor include với cách nhúng snippet trong Markdown.

## 2. Ba thành phần tạo nên đường dẫn include

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Output directory | build/generated-snippets | Root nơi test ghi snippet |
| Document identifier | orders/get-by-id | Thư mục con của operation |
| Snippet filename | http-request.adoc | File cần include |

Đường dẫn đầy đủ:

```text
build/generated-snippets/orders/get-by-id/http-request.adoc
```

Nếu Asciidoctor khai báo:

```asciidoc
include::{snippets}/orders/get-by-id/http-request.adoc[]
```

thì {snippets} phải trỏ đúng tới build/generated-snippets, không phải build/generated-snippets/orders hoặc chính thư mục get-by-id.

### 2.1. Kiểm tra cây thư mục trước khi sửa include

Không đoán đường dẫn dựa trên tên test hoặc endpoint. Mở output directory sau khi test chạy và xác nhận:

- Thư mục identifier thực tế.
- Tên file snippet thực tế.
- Chữ hoa/chữ thường của từng thành phần.
- File có tồn tại trong đúng module đang build hay không.

Nếu file không tồn tại trong output, lỗi nằm ở bước sinh snippet hoặc output configuration; thay đổi include không thể tạo ra file còn thiếu.

## 3. Cấu hình snippets attribute trong Asciidoctor

Một tài liệu Asciidoctor thường khai báo attribute trỏ tới output root:

```asciidoc
:snippets: build/generated-snippets

= Order API

== Lấy đơn hàng

include::{snippets}/orders/get-by-id/http-request.adoc[]
include::{snippets}/orders/get-by-id/http-response.adoc[]
```

Khi render, Asciidoctor thay {snippets} bằng giá trị attribute. Nếu attribute không được khai báo hoặc build không truyền attribute vào, include có thể được giữ nguyên hoặc bị báo lỗi tùy cấu hình.

### 3.1. Truyền attribute từ Gradle

Ví dụ Gradle Groovy DSL:

```groovy
def snippetsDir = file('build/generated-snippets')

test {
    outputs.dir snippetsDir
    useJUnitPlatform()
}

asciidoctor {
    inputs.dir snippetsDir
    dependsOn test
    attributes 'snippets': snippetsDir
}
```

Ví dụ Kotlin DSL:

```kotlin
val snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.test {
    outputs.dir(snippetsDir)
    useJUnitPlatform()
}

tasks.named("asciidoctor") {
    inputs.dir(snippetsDir)
    dependsOn(tasks.test)
    attributes(mapOf("snippets" to snippetsDir.get().asFile))
}
```

Đây là cấu hình minh họa; plugin Asciidoctor và task name có thể khác theo dự án. Điều quan trọng là output directory phải trùng nơi Spring REST Docs ghi snippets, và Asciidoctor phải chạy sau test.

### 3.2. Truyền attribute từ command line

Có thể truyền attribute khi gọi Asciidoctor CLI:

```bash
asciidoctor -a snippets=build/generated-snippets src/docs/asciidoc/index.adoc
```

Đường dẫn tương đối được diễn giải từ working directory của tiến trình render. Nếu build chạy ở subproject, kiểm tra working directory và dùng project layout nhất quán.

## 4. Đường dẫn tương đối và tuyệt đối

Đường dẫn include tương đối thường được giải quyết theo vị trí file Asciidoctor hiện tại hoặc include base directory do toolchain cấu hình. Không mặc định mọi đường dẫn tương đối đều tính từ repository root.

Ví dụ:

```text
project/
  src/docs/asciidoc/
    index.adoc
  build/generated-snippets/
    orders/get-by-id/http-request.adoc
```

Nếu index.adoc khai báo trực tiếp:

```asciidoc
include::../../build/generated-snippets/orders/get-by-id/http-request.adoc[]
```

relative path được tính theo quy tắc include của Asciidoctor. Nếu chuyển index.adoc sang folder khác, path có thể không còn đúng.

Dùng attribute {snippets} giúp tách vị trí output khỏi vị trí source docs. Khi build ở nhiều môi trường, chỉ cần truyền root path chính xác.

### 4.1. Tránh hard-code đường dẫn máy developer

Không include bằng đường dẫn như:

```asciidoc
include::C:/Users/dev/project/build/generated-snippets/orders/get-by-id/http-request.adoc[]
```

Đường dẫn này chỉ tồn tại trên một máy. Dùng path tương đối theo project hoặc attribute được build truyền vào để local, CI và đồng đội dùng chung cấu hình.

## 5. Identifier trong include phải khớp document(...)

Test:

```java
mockMvc.perform(get("/api/orders/42"))
        .andDo(document("orders/get-by-id"));
```

Include đúng:

```asciidoc
include::{snippets}/orders/get-by-id/http-request.adoc[]
```

Include sai:

```asciidoc
include::{snippets}/order/get-order/http-request.adoc[]
```

URL /api/orders/42 không tự tạo thư mục orders/get-by-id; thư mục được quyết định bởi identifier truyền vào document(...). Khi refactor identifier, cập nhật include và các script kiểm tra snippet bắt buộc.

### 5.1. Placeholder class/method/step

Nếu test dùng:

```java
document("{class-name}/{method-name}/{step}")
```

thì đường dẫn thực tế phụ thuộc class, method và số thứ tự exchange:

```text
build/generated-snippets/
  order-documentation-tests/
    create-and-read-order/
      1/
      2/
```

Không include {class-name} như chuỗi literal nếu Asciidoctor không được truyền giá trị tương ứng. Thông thường tài liệu viết include với tên thư mục đã xác định hoặc build script tạo attribute riêng cho class/method.

## 6. Snippet chưa được sinh khi Asciidoctor chạy

Một nguyên nhân phổ biến là task render chạy trước test. Trong Gradle, khai báo dependency:

```groovy
tasks.named('asciidoctor') {
    dependsOn tasks.test
    inputs.dir file('build/generated-snippets')
}
```

Sau đó chạy:

```bash
./gradlew clean test asciidoctor
```

Với Maven, gắn goal Asciidoctor vào lifecycle phase sau test hoặc verify theo plugin đang dùng:

```bash
mvn clean verify
```

Nếu test thất bại hoặc không chạy, snippet cần include sẽ không được sinh. Kiểm tra test report và output directory trước khi kết luận lỗi nằm ở Asciidoctor.

### 6.1. Stale snippet làm che giấu include sai

Nếu không clean output, file từ lần chạy trước có thể còn tồn tại. Include cũ vẫn thành công dù test hiện tại đã đổi identifier hoặc không còn document operation đó.

Trong CI/release, dùng clean build:

```bash
./gradlew clean test asciidoctor
```

Clean build giúp phát hiện include cũ trỏ tới file không còn được sinh.

## 7. Markdown không có cú pháp include chuẩn

Markdown cơ bản không định nghĩa directive include file như Asciidoctor. Dòng:

```markdown
include::{snippets}/orders/get-by-id/http-request.adoc[]
```

không phải cú pháp Markdown chuẩn. Renderer Markdown thông thường sẽ hiển thị dòng đó như văn bản hoặc xử lý theo extension riêng.

Nếu tài liệu chính dùng Markdown, có một số lựa chọn:

1. Dùng template Markdown của Spring REST Docs để sinh snippet .md, sau đó liên kết hoặc ghép nội dung theo cơ chế site generator.
2. Dùng plugin/include extension của static-site generator mà dự án đã chọn.
3. Dùng script build có kiểm soát để chèn snippet vào Markdown trước khi render.
4. Dùng Asciidoctor làm nguồn tài liệu chính nếu cần include snippet trực tiếp và có nhiều operation.

Không dùng cú pháp Asciidoctor trong Markdown trừ khi pipeline Markdown có extension hỗ trợ rõ ràng. Kiểm tra output HTML để chắc chắn snippet được nhúng thật, không chỉ hiển thị nguyên directive.

### 7.1. Ghép snippet Markdown bằng script

Một script build có thể đọc snippet file và chèn vào marker trong Markdown. Ví dụ marker:

```markdown
## Lấy đơn hàng

<!-- snippet: orders/get-by-id/http-request.md -->
```

Script cần resolve source path dưới output root được cấu hình, fail rõ ràng nếu snippet không tồn tại, không đọc path tùy ý ngoài output root, ghi output vào thư mục generated riêng và chạy sau test sinh snippet nhưng trước Markdown renderer.

Nếu dùng script tùy chỉnh, thêm test cho trường hợp file thiếu và identifier sai.

## 8. Kiểm tra tên file snippet

Tên snippet phụ thuộc operation và snippet template:

| Mục tiêu | File thường gặp |
| --- | --- |
| HTTP request | http-request.adoc |
| HTTP response | http-response.adoc |
| cURL request | curl-request.adoc |
| Request body | request-body.adoc |
| Response body | response-body.adoc |
| Request fields | request-fields.adoc |
| Path parameters | path-parameters.adoc |
| Request headers | request-headers.adoc |

Không đoán filename nếu dự án custom snippet templates hoặc dùng định dạng Markdown. Mở output directory để xem file thực tế.

Một lỗi thường gặp là include request-fields.adoc trong khi test chỉ document requestParameters(...) hoặc chưa gọi requestFields(...). Khi snippet không được tạo, kiểm tra descriptor/test trước khi sửa include.

## 9. Khác biệt Windows và Linux

Windows thường không phân biệt chữ hoa/chữ thường trong path mặc định, trong khi Linux phân biệt. Include:

```asciidoc
include::{snippets}/Orders/Get-By-Id/http-request.adoc[]
```

có thể chạy trên workstation Windows nếu thư mục thực tế là orders/get-by-id, nhưng thất bại trên Linux CI.

Hãy giữ identifier và include cùng cách viết hoa/thường, dùng slash / trong Asciidoctor include path, tránh ký tự đặc biệt hoặc dấu cách trong identifier, không ghép path bằng dấu backslash của Windows trong file Asciidoctor và kiểm tra trên Linux CI hoặc container giống môi trường release.

## 10. Chẩn đoán theo thông báo lỗi

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Include file not found | Sai output root hoặc identifier | Liệt kê cây generated-snippets |
| Attribute snippets not defined | Chưa khai báo/truyền attribute | Kiểm tra header Asciidoctor và Gradle attributes |
| Include tồn tại local nhưng fail CI | Case-sensitive path hoặc khác working directory | Kiểm tra tên chính xác trên Linux |
| File không tồn tại sau clean | Test không sinh snippet hoặc identifier đã đổi | Chạy test và xem report |
| Markdown hiển thị nguyên include directive | Dùng cú pháp Asciidoctor trong Markdown thuần | Dùng Markdown integration/template hoặc script |
| Chỉ thiếu request-fields snippet | Test không gọi descriptor tương ứng | Kiểm tra requestFields(...) và output |
| Include path lặp build/generated-snippets | {snippets} đã chứa identifier | Đặt attribute về output root |
| Include vẫn lấy nội dung cũ | Stale snippets chưa clean | Chạy clean build |

## 11. Kiểm tra include trước khi publish

Quy trình đề xuất:

1. Xác nhận output directory trong test configuration.
2. Xác nhận identifier trong document(...).
3. Chạy clean và test để sinh snippet mới.
4. Liệt kê snippet files và so sánh với include list.
5. Truyền {snippets} đúng output root cho Asciidoctor.
6. Render tài liệu và kiểm tra output HTML/PDF.
7. Nếu dùng Markdown, xác minh extension/script thực sự nhúng snippet.
8. Chạy cùng pipeline trên Linux CI để phát hiện sai case và path separator.

Ví dụ kiểm tra file bắt buộc:

```bash
test -f build/generated-snippets/orders/get-by-id/http-request.adoc
test -f build/generated-snippets/orders/get-by-id/http-response.adoc
```

Rà soát directive include trong Asciidoctor source:

```bash
rg -n 'include::' src/docs/asciidoc
```

CI nên fail khi file bắt buộc không tồn tại hoặc Asciidoctor không resolve được include. Đừng bỏ qua lỗi include chỉ để build tiếp tục publish tài liệu thiếu nội dung.

## 12. Bài tập thực hành

Một test sinh snippet:

```java
mockMvc.perform(get("/api/orders/42"))
        .andDo(document("orders/get-by-id"));
```

Thực hiện:

1. Cấu hình output root là build/generated-snippets.
2. Tạo Asciidoctor source có attribute snippets.
3. Include http-request.adoc và http-response.adoc từ identifier orders/get-by-id.
4. Cố ý viết sai identifier để quan sát lỗi include.
5. Chạy clean test asciidoctor và xác nhận lỗi được phát hiện.
6. Nếu có Markdown docs, thử dùng directive Asciidoctor trong Markdown thuần; sau đó chọn template/extension hoặc script ghép phù hợp.
7. Chạy pipeline trên Linux CI để xác nhận case và path separator.

**Tiêu chí hoàn thành:** Include trỏ đúng output root, identifier và filename; test sinh snippet trước khi render; Markdown dùng cơ chế nhúng được hỗ trợ; clean build và CI phát hiện file thiếu, stale snippet hoặc sai chữ hoa/chữ thường.

## 13. Ghi nhớ

Đường dẫn snippet gồm output directory, document identifier và snippet filename. Asciidoctor dùng include directive cùng attribute như {snippets}; attribute phải trỏ tới output root và include phải khớp identifier/file thực tế. Test cần chạy trước bước render. Markdown thuần không có cú pháp include file chuẩn, vì vậy cần template, extension hoặc script ghép riêng. Clean output, kiểm tra filename, giữ đúng chữ hoa/chữ thường và chạy trên Linux CI giúp phát hiện include sai trước khi publish.

### Tài liệu tham khảo

- [Spring REST Docs — Getting Started and Snippets](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
- [Asciidoctor — Include Directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/)
- [Asciidoctor Gradle Plugin — Attributes](https://docs.asciidoctor.org/gradle-plugin/latest/common-task-configuration/)
