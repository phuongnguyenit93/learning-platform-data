# Xóa output cũ trước khi xác nhận tài liệu Spring REST Docs

## 1. Vì sao output cũ làm tài liệu sai?

Spring REST Docs sinh snippet từ các HTTP test. Giả sử lần chạy đầu có hai test:

```text
build/generated-snippets/
  order-detail/
    http-request.adoc
    http-response.adoc
  order-create/
    http-request.adoc
    http-response.adoc
```

Sau đó nhóm phát triển xóa test order-create hoặc đổi identifier thành order-create-v2. Nếu lần chạy mới chỉ ghi thêm snippet mà không xóa output cũ, thư mục order-create vẫn còn. Tài liệu Asciidoctor có thể tiếp tục include file cũ và build vẫn thành công, khiến người đọc thấy operation đã bị loại bỏ hoặc contract lỗi thời.

Đây là **stale output**: file được tạo từ lần build trước nhưng không còn được tạo bởi source/test hiện tại. Với Spring REST Docs, stale snippets đặc biệt nguy hiểm vì chúng có thể trông hợp lệ và không gây lỗi biên dịch.

Module **SPRING_REST_DOCS** tạo REST API documentation có thể kiểm chứng bằng HTTP tests với MockMvc, WebTestClient hoặc REST Assured. Test sinh snippet cho request, response, payload, parameter và header; sau đó biên soạn Asciidoctor/Markdown và đưa vào build/CI. Bài thuộc chương **Thư mục output**, hướng dẫn xóa output sinh cũ đúng cách trước khi xác nhận tài liệu.

Sau bài học, bạn có thể:

1. Nhận biết stale snippets và ảnh hưởng của chúng đến tài liệu.
2. Phân biệt output sinh tự động với source tài liệu được quản lý bằng Git.
3. Dùng clean và task dependency để tạo bộ snippet nhất quán.
4. Cấu hình Gradle/Maven để test sinh snippet trước khi Asciidoctor chạy.
5. Kiểm tra output sạch trong CI và tránh xóa nhầm file nguồn.

## 2. Phân biệt generated output với source

| Loại | Ví dụ | Cách quản lý |
| --- | --- | --- |
| Source test | src/test/java/... | Theo dõi trong Git |
| Source Asciidoctor | src/docs/asciidoc/index.adoc | Theo dõi trong Git |
| Snippet sinh tự động | build/generated-snippets/ | Tạo lại từ test |
| Tài liệu đã render | build/docs/asciidoc/ | Tạo lại từ source và snippet |
| Artifact publish | ZIP/PDF/HTML phát hành | Lưu theo pipeline/release policy |

Chỉ các thư mục generated output được xác định rõ mới nên bị xóa khi clean. Không xóa src/test, src/docs, file Asciidoctor nguồn, fixture JSON hoặc tài liệu viết thủ công.

### 2.1. Output directory và identifier

Đường dẫn snippet thường có dạng:

```text
build/generated-snippets/
  <document-identifier>/
    http-request.adoc
    http-response.adoc
    request-fields.adoc
```

Output directory là root. Document identifier là thư mục con của operation. Khi test đổi identifier hoặc bị xóa, thư mục identifier cũ có thể tồn tại nếu output root không được làm sạch.

### 2.2. Vì sao chỉ ghi đè file chưa đủ?

Giả sử lần chạy trước có order-create/http-request.adoc. Lần chạy sau test không còn tạo order-create, nên không có file mới để ghi đè. File cũ vẫn nằm nguyên tại output root. Đây là lý do cần clean output root trước khi sinh lại toàn bộ snippet.

## 3. Xóa đúng output directory

Trước khi clean, xác định:

1. Output directory được Spring REST Docs cấu hình ở đâu.
2. Task nào tạo snippets.
3. Task nào consume snippets.
4. Có task khác dùng chung thư mục đó không.

Ví dụ:

```java
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
```

Hoặc với JUnit 5:

```java
@RegisterExtension
final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("build/generated-snippets");
```

Trong cả hai trường hợp, build/generated-snippets là output có thể tái tạo. Gradle clean xóa build directory của project, bao gồm snippets và tài liệu đã render trong đó.

**Không dùng lệnh xóa rộng như xóa thư mục hiện hành hoặc toàn bộ source docs.** Hãy dùng task clean của build tool hoặc chỉ xóa đúng generated output root đã xác định.

## 4. Gradle: clean trước test và Asciidoctor

Với Gradle, task clean được cung cấp bởi plugin Base/Java và xóa build directory của project. Lệnh đầy đủ:

```bash
./gradlew clean test asciidoctor
```

Ý nghĩa:

- clean: xóa output build của lần chạy trước.
- test: chạy HTTP tests và sinh Spring REST Docs snippets.
- asciidoctor: ghép snippet mới với tài liệu Asciidoctor và render artifact.

Gradle thực thi các task theo thứ tự quan hệ và dependency. Khi cần chắc chắn Asciidoctor đọc snippet do test vừa sinh, khai báo dependency tường minh.

### 4.1. Khai báo dependency và output directory

Ví dụ Gradle Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.asciidoctor.jvm.convert' version '4.0.4'
}

ext {
    snippetsDir = file('build/generated-snippets')
}

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

Đây là cấu hình minh họa; plugin version, tên task và DSL có thể khác theo dự án. Điểm cốt lõi là test khai báo output snippet, Asciidoctor khai báo input snippet và phụ thuộc vào test.

### 4.2. Khi chỉ muốn xóa snippets

Có thể khai báo task xóa đúng directory:

```groovy
tasks.register('cleanRestDocsSnippets', Delete) {
    delete snippetsDir
}

test {
    dependsOn cleanRestDocsSnippets
    outputs.dir snippetsDir
}
```

Không dùng task này nếu nhiều test task chạy song song hoặc cùng ghi vào một output directory. Nếu có nhiều source set/test task, hãy clean một lần trước toàn bộ producer tasks. Không để mỗi test task xóa output của task khác.

## 5. Maven: clean trước khi tạo snippet

Với Maven, lifecycle clean xóa thư mục target của project. Có thể chạy:

```bash
mvn clean verify
```

Nếu dự án cấu hình Spring REST Docs để test sinh snippet vào target/generated-snippets và Asciidoctor plugin render tài liệu trong lifecycle verify, lệnh này tạo lại output từ trạng thái sạch.

Một số dự án chạy riêng:

```bash
mvn clean test
mvn asciidoctor:process-asciidoc
```

Tên goal và phase phụ thuộc plugin Asciidoctor Maven mà dự án sử dụng. Kiểm tra cấu hình thực tế để bảo đảm test chạy trước goal Asciidoctor, Asciidoctor đọc đúng output, goal không chạy trước khi snippet được sinh và clean không xóa source Asciidoctor.

Nếu cần clean riêng snippets, cấu hình Maven Clean Plugin chỉ xóa target/generated-snippets. Không dùng đường dẫn tương đối mơ hồ có thể trỏ nhầm thư mục trong multi-module build.

## 6. Identifier thay đổi và snippet bị bỏ

Test ban đầu:

```java
@Test
void createOrder() throws Exception {
    mockMvc.perform(post("/api/orders"))
            .andDo(document("order-create"));
}
```

Sau refactor:

```java
@Test
void createOrder() throws Exception {
    mockMvc.perform(post("/api/orders"))
            .andDo(document("orders/create"));
}
```

Nếu không clean, output có thể đồng thời chứa:

```text
build/generated-snippets/
  order-create/       # stale
  orders/
    create/           # mới
```

Nếu Asciidoctor vẫn include order-create, build có thể tiếp tục thành công bằng snippet cũ. Clean output giúp phát hiện include lỗi thời: file không còn được sinh sẽ biến mất và Asciidoctor báo không tìm thấy include.

Điều này hữu ích khi đổi tên test method/document identifier, xóa operation, đổi tên field payload, chuyển output directory hoặc thay cách tổ chức snippet.

## 7. Build sạch không đồng nghĩa mọi dữ liệu đã được kiểm chứng

Clean chỉ bảo đảm không dùng file generated cũ trong vùng output được xóa. Nó không tự chứng minh test bao phủ mọi operation, descriptor phản ánh đầy đủ contract, description đúng nghiệp vụ, public base URL chính xác hoặc snippet được include đúng section.

Vì vậy, quy trình xác nhận cần gồm test, render docs và kiểm tra nội dung/đường dẫn snippet.

### 7.1. Kiểm tra output sau khi test

Sau khi chạy test, kiểm tra output root:

```bash
find build/generated-snippets -type f
```

Với PowerShell:

```powershell
Get-ChildItem -Path build/generated-snippets -Recurse -File |
    Select-Object -ExpandProperty FullName
```

Đối chiếu danh sách identifier với các operation cần document. Nếu thư mục không xuất hiện, kiểm tra test có chạy không, test có gắn document(...) không và output directory có đúng không.

### 7.2. Kiểm tra snippet bắt buộc

Ví dụ:

```bash
test -f build/generated-snippets/orders/create/http-request.adoc
test -f build/generated-snippets/orders/create/http-response.adoc
```

Với PowerShell:

```powershell
Test-Path build/generated-snippets/orders/create/http-request.adoc
Test-Path build/generated-snippets/orders/create/http-response.adoc
```

Kiểm tra file tồn tại chỉ là bước cơ bản. Cần render Asciidoctor để xác nhận include path hợp lệ và tài liệu hoàn chỉnh.

## 8. Incremental build và stale output

Gradle và Maven có thể bỏ qua task nếu cho rằng input/output không thay đổi. Cần khai báo output/input đúng để incremental build đáng tin cậy.

Với Gradle:

- Test khai báo snippets directory là output.
- Asciidoctor khai báo snippets directory là input.
- Asciidoctor phụ thuộc vào test task.
- Clean build được chạy trong CI khi cần xác nhận artifact độc lập với workspace cũ.

Nếu test sinh snippets theo side effect nhưng output directory không được khai báo, Gradle có thể không theo dõi đúng quan hệ task. Nếu Asciidoctor không khai báo input, cache/incremental build có thể không phản ánh thay đổi snippets.

Không phải lúc nào cũng cần clean trước mọi build developer. Build incremental giúp tiết kiệm thời gian. Nhưng pipeline tạo artifact phát hành nên có job clean build định kỳ hoặc mỗi lần release để xác nhận output từ source hiện tại.

## 9. Multi-module project và output directory

Trong Gradle multi-module hoặc Maven reactor, mỗi module thường có build/target riêng:

```text
root/
  api-orders/
    build/generated-snippets/
  api-customers/
    build/generated-snippets/
  api-docs/
    src/docs/asciidoc/
```

Module api-docs có thể tổng hợp snippets từ hai module API. Cần xác định module test nào tạo snippet, module docs nhận snippet từ đâu, task nào phụ thuộc producer tests và clean module nào sẽ xóa output.

Tránh để hai module cùng ghi vào một thư mục dùng chung mà không có namespace riêng. Có thể phân vùng theo module:

```text
build/generated-snippets/
  api-orders/
    orders/create/
  api-customers/
    customers/get-by-id/
```

Nếu copy output sang module docs, thao tác copy phải chạy sau producer tests và nên xóa destination generated trước khi copy để file đã bị loại ở source không còn sót ở destination.

## 10. CI: xác nhận tài liệu từ workspace sạch

Một pipeline tài liệu:

```text
Checkout source
    |
    v
Clean build outputs
    |
    v
Run HTTP documentation tests
    |
    v
Verify generated snippet set
    |
    v
Render Asciidoctor / Markdown
    |
    v
Check links and expected files
    |
    v
Publish build artifact
```

Ví dụ Gradle:

```bash
./gradlew clean test asciidoctor
```

Ví dụ Maven:

```bash
mvn clean verify
```

CI nên chạy trên workspace checkout mới hoặc clean đúng build output trước khi test. Nếu chỉ chạy asciidoctor trên workspace đã tồn tại, snippet từ lần build trước có thể làm tài liệu xanh dù test hiện tại không sinh đủ snippet.

### 10.1. Không dùng cache làm nguồn snippet duy nhất

Build cache có thể tăng tốc task nếu input/output được khai báo chính xác. Tuy nhiên, pipeline vẫn cần kiểm tra tính đầy đủ của artifact và quan hệ dependency. Không copy thủ công thư mục snippets cũ vào build để làm Asciidoctor chạy qua.

Nếu cache được bật:

- Khai báo inputs/outputs đúng.
- Không để test sinh file ngoài output directory đã khai báo.
- Không dùng output của commit khác làm artifact của commit hiện tại.
- Có job clean build để kiểm chứng quy trình end-to-end.

## 11. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Tài liệu vẫn có operation đã xóa | Snippet cũ còn trong output root | Chạy clean trước khi sinh snippet |
| Asciidoctor chạy xanh dù test không sinh snippet | File cũ đáp ứng include | Dùng clean workspace và task dependency |
| Snippet mới mất sau khi chạy test task khác | Task khác xóa chung output directory | Chỉ clean một lần trước toàn bộ producer tasks |
| Build developer chậm khi luôn clean | Clean mọi output trong mỗi lần build | Dùng incremental build khi phát triển; clean build ở CI/release |
| File nguồn Asciidoctor bị xóa | Clean nhầm source directory | Chỉ clean build/generated-snippets hoặc build directory |
| Module docs còn snippet đã bị xóa ở module API | Copy không clean destination | Xóa đúng destination generated rồi copy lại |
| Gradle không chạy lại Asciidoctor | Input snippets chưa khai báo | Khai báo inputs.dir và dependsOn(test) |
| Maven render trước khi test hoàn tất | Goal/phase chưa gắn đúng lifecycle | Ràng buộc Asciidoctor goal sau test |
| CI phụ thuộc file từ workspace cũ | Job không checkout sạch hoặc không clean | Dùng clean build và xác nhận snippet set |

## 12. Bài tập thực hành

API orders có hai test document:

```java
@Test
void createOrder() { /* document("orders/create") */ }

@Test
void getOrder() { /* document("orders/get") */ }
```

Lần đầu, output có cả hai thư mục. Sau đó xóa test getOrder và đổi identifier của test tạo thành orders/create-v2.

Thực hiện:

1. Chạy test không clean và quan sát output còn thư mục cũ.
2. Chạy clean test rồi liệt kê output snippet.
3. Xác nhận orders/get và orders/create cũ đã biến mất; orders/create-v2 được sinh.
4. Cập nhật Asciidoctor include sang identifier mới.
5. Chạy clean test asciidoctor và xác nhận render thành công.
6. Cố ý để một include trỏ tới snippet đã xóa để quan sát build thất bại.
7. Thêm quy trình clean build vào CI.

**Tiêu chí hoàn thành:** Output chỉ chứa snippet do test hiện tại sinh; snippet cũ không thể làm build xanh giả; source docs được giữ nguyên; Asciidoctor phụ thuộc test và CI xác nhận artifact từ workspace sạch.

## 13. Ghi nhớ

Snippet Spring REST Docs là generated output, không phải source tài liệu. Khi test hoặc identifier bị xóa/đổi tên, file cũ có thể còn lại và khiến Asciidoctor include contract lỗi thời. Hãy xác định output root riêng, dùng Gradle clean hoặc Maven clean trước clean build, khai báo test là producer và Asciidoctor là consumer của snippets. Với multi-module, clean đúng destination trước khi tổng hợp. Chạy build sạch trong CI/release và xác minh tập snippet sinh ra để tài liệu chỉ phản ánh test/source hiện tại.

### Tài liệu tham khảo

- [Spring REST Docs — Getting Started and Snippet Output](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
- [Gradle — The Base Plugin and clean task](https://docs.gradle.org/current/userguide/base_plugin.html)
- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html)
- [Maven — Clean Plugin](https://maven.apache.org/plugins/maven-clean-plugin/)
- [Asciidoctor Gradle Plugin](https://docs.asciidoctor.org/gradle-plugin/latest/)
