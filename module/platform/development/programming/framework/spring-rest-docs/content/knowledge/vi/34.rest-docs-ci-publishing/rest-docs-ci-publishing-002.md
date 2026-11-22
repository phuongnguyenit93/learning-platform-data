# Chạy Asciidoctor sau khi test hoàn tất

Spring REST Docs tạo snippet khi documentation tests thực hiện request, kiểm tra response và gọi API document. Asciidoctor sử dụng các snippet này để biên soạn trang tài liệu. Vì vậy, **test phải hoàn tất thành công và tạo đủ snippet trước khi Asciidoctor bắt đầu render**.

Nếu Asciidoctor chạy trước test, include có thể không tìm thấy file. Nếu thư mục output còn snippet từ lần build cũ, render đôi khi vẫn thành công nhưng tài liệu không phản ánh code hiện tại. Cấu hình build cần thể hiện dependency rõ ràng, dùng chung output directory và truyền lỗi test tới bước render/publish.

Bài học thuộc chương **CI và phát hành** của module `SPRING_REST_DOCS`. Module tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured, sinh snippet request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và tích hợp vào build, CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao Asciidoctor phải chạy sau documentation tests.
2. Thiết lập dependency giữa task test và task Asciidoctor trong Gradle.
3. Gắn execution Asciidoctor vào Maven lifecycle sau giai đoạn test.
4. Cấu hình một snippets directory thống nhất giữa test recorder và renderer.
5. Clean output cũ và xác minh snippet được tạo trong build hiện tại.
6. Bảo đảm test failure ngăn render và publish.
7. Kiểm tra artifact cuối để tránh tài liệu thiếu hoặc lỗi thời.

## 2. Quan hệ giữa documentation test và Asciidoctor

Documentation test thực hiện HTTP exchange và ghi snippet vào output directory. Asciidoctor đọc các file này qua include directive. Luồng đúng:

```text
Compile test sources
       │
       ▼
Run documentation tests
       │
       ├── Failure ──► Stop build
       │
       ▼
Generate request/response snippets
       │
       ▼
Validate snippet inputs
       │
       ▼
Run Asciidoctor
       │
       ▼
Generate HTML/PDF documentation
       │
       ▼
Archive or publish
```

Asciidoctor không tự chạy documentation tests chỉ vì trang AsciiDoc có include snippet. Build tool phải được cấu hình để task render phụ thuộc task test tạo ra các file đó.

### 2.1. Vì sao chạy riêng Asciidoctor có thể thất bại?

Nếu gọi riêng task Asciidoctor mà không có dependency, generated snippets có thể chưa tồn tại trong clean checkout; include có thể trỏ tới identifier không được test tạo; snippet cũ có thể khiến render dùng nội dung lỗi thời; tài liệu không được xác minh lại khi test hoặc contract thay đổi.

## 3. Thống nhất snippets directory

Một số quy ước thường gặp:

```text
Gradle:
build/generated-snippets/

Maven:
target/generated-snippets/
```

Đường dẫn trên không bắt buộc. Chọn một output directory nhất quán và cấu hình cả test recorder lẫn Asciidoctor plugin cùng dùng giá trị đó.

Ví dụ test:

```java
.andDo(document("orders-get",
    requestHeaders(
        headerWithName("Accept")
            .description("Media type client chấp nhận")
    ),
    responseFields(
        fieldWithPath("id")
            .description("Mã đơn hàng")
    )
));
```

Identifier `orders-get` tạo thư mục con chứa snippet của operation. AsciiDoc include từ đúng thư mục:

```asciidoc
=== Request

include::{snippets}/orders-get/http-request.adoc[]

=== Response

include::{snippets}/orders-get/http-response.adoc[]
```

Nếu test ghi vào build/generated-snippets nhưng Asciidoctor tìm ở target/generated-snippets, build sẽ báo thiếu snippet dù test đã chạy.

## 4. Chạy Asciidoctor sau test với Gradle

Trong Gradle, khai báo task Asciidoctor phụ thuộc task test tạo snippet. Ví dụ khái quát:

```groovy
tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(layout.buildDirectory.dir("generated-snippets"))

    attributes(
        "snippets": layout.buildDirectory
            .dir("generated-snippets")
            .get()
            .asFile
            .absolutePath
    )
}
```

Ví dụ giả định task test ghi snippet vào build/generated-snippets. Cú pháp attribute có thể khác theo version plugin; kiểm tra DSL của version dự án khai báo.

### 4.1. Nếu documentation tests có task riêng

Một số dự án tách unit tests và documentation tests:

```groovy
tasks.named("asciidoctor") {
    dependsOn(tasks.named("docsTest"))
    inputs.dir(layout.buildDirectory.dir("generated-snippets"))
}
```

Tên docsTest chỉ là ví dụ; task thực tế phụ thuộc build script. Task này phải chạy các test có document(...). Nếu Asciidoctor cần cả unit test và documentation test, có thể tạo lifecycle task tổng hợp:

```groovy
tasks.register("prepareRestDocs") {
    dependsOn(tasks.named("test"))
    dependsOn(tasks.named("docsTest"))
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("prepareRestDocs"))
}
```

Chỉ dùng cấu trúc này nếu các task tồn tại. Không thêm tên task giả định mà chưa khai báo.

### 4.2. Chạy từ command line

Khi dependency đã cấu hình:

```bash
./gradlew clean asciidoctor
```

Gradle chạy task phụ thuộc trước Asciidoctor. Có thể gọi task tổng hợp như build nếu dự án đã gắn tài liệu vào lifecycle. Không dựa vào thứ tự gõ nhiều task trên command line thay cho dependency trong build script.

## 5. Chạy Asciidoctor sau test với Maven

Maven thực thi plugin goals theo lifecycle phases. Documentation tests thường chạy trong phase test (Surefire) hoặc integration-test (Failsafe), còn Asciidoctor cần gắn vào phase sau khi nhóm test tạo snippet đã hoàn tất.

Ví dụ khi documentation tests chạy trong Surefire:

```xml
<plugin>
  <groupId>org.asciidoctor</groupId>
  <artifactId>asciidoctor-maven-plugin</artifactId>
  <executions>
    <execution>
      <id>render-rest-docs</id>
      <phase>prepare-package</phase>
      <goals>
        <goal>process-asciidoc</goal>
      </goals>
      <configuration>
        <attributes>
          <snippets>${project.build.directory}/generated-snippets</snippets>
        </attributes>
      </configuration>
    </execution>
  </executions>
</plugin>
```

Đây là cấu trúc minh họa; version plugin, goal, phase và output cần đối chiếu dự án. Phase prepare-package diễn ra sau test, nên phù hợp nếu snippet được tạo trong phase test.

### 5.1. Nếu documentation tests chạy bằng Failsafe

Nếu test integration/documentation được Failsafe chạy ở integration-test và verify, Asciidoctor không được đặt ở prepare-package vì phase này đến trước integration-test. Gắn render vào phase sau khi Failsafe hoàn tất, ví dụ execution thích hợp trong verify, hoặc thiết kế lifecycle riêng bảo đảm thứ tự.

Điểm cần xác minh là task render chỉ chạy sau khi test tạo snippet thành công. Đừng chọn phase chỉ vì tên có vẻ phù hợp; đối chiếu lifecycle thực tế của plugin test.

### 5.2. Lệnh Maven

Với cấu hình test trong Surefire và Asciidoctor gắn sau phase test:

```bash
./mvnw clean verify
```

Với Failsafe, verify là phase thường dùng để hoàn tất integration tests và kiểm tra kết quả. Đảm bảo Asciidoctor execution nằm sau goal xác minh test, không chỉ sau khi test bắt đầu.

## 6. Cấu hình snippets attribute trong AsciiDoc

Một tài liệu có thể khai báo attribute:

```asciidoc
:snippets: build/generated-snippets

= Orders API

== Lấy đơn hàng

=== Request

include::{snippets}/orders-get/http-request.adoc[]

=== Response

include::{snippets}/orders-get/http-response.adoc[]
```

Trong CI, attribute được truyền từ plugin build thường dễ quản lý hơn. Tránh định nghĩa snippets directory riêng trong test, plugin và file AsciiDoc mà không có một nguồn cấu hình thống nhất.

Nếu dùng Maven, output thường nằm dưới target; nếu dùng Gradle, thường nằm dưới build. Attribute phải khớp output của build tool đang chạy.

### 6.1. Kiểm tra include identifier

Identifier trong document("orders-get", ...) phải khớp đường dẫn trong include. Khi đổi identifier trong test, cập nhật include tương ứng. Thiếu file thường là dấu hiệu test chưa tạo snippet, identifier bị lệch hoặc descriptor chưa sinh file đang include.

## 7. Clean output trước khi test

Snippet cũ có thể che giấu test chưa chạy hoặc operation đã bị xóa. Ví dụ test từng sinh orders-delete, sau đó test bị đổi tên hoặc xóa; nếu không clean, thư mục cũ vẫn có thể tồn tại và Asciidoctor tiếp tục include nó.

Dùng clean build:

```bash
./gradlew clean asciidoctor
```

Hoặc:

```bash
./mvnw clean verify
```

Clean xóa generated output; test tạo lại snippet; render sử dụng output mới. Nếu pipeline tách job, snippets artifact phải được tạo từ đúng commit và không trộn với output của build trước.

### 7.1. Không dùng cache snippet như nguồn sự thật

Cache dependency giúp tiết kiệm thời gian resolve thư viện. Generated snippets là output của test và cần được tái tạo hoặc truyền như artifact có provenance rõ. Không để renderer âm thầm dùng snippets cache cũ khi test không chạy.

## 8. Đảm bảo test failure dừng Asciidoctor

Build tool cần truyền failure của documentation tests tới task render:

- Gradle: task test thất bại phải làm dependency task thất bại; không bật ignoreFailures cho pipeline publish.
- Maven Surefire/Failsafe: test failure phải làm lifecycle dừng hoặc đánh dấu build thất bại; không cấu hình bỏ qua lỗi trong job phát hành.
- CI: không dùng continue-on-error cho bước test tạo snippet hoặc bước render bắt buộc.

Nếu một số test không phải documentation tests có thể chạy riêng, hãy phân nhóm rõ. Task mà Asciidoctor phụ thuộc phải bao gồm toàn bộ documentation tests cần tạo snippet.

### 8.1. Test bị skip không phải test thành công

Task có exit code 0 nhưng test count bằng 0 có thể vẫn không tạo snippet. Kiểm tra test report và số lượng test được thực thi. Khi phát hành tài liệu, validation nên xác nhận các operation bắt buộc đã sinh output.

## 9. Kiểm tra trước và sau khi render

Trước Asciidoctor, xác minh snippet directory có file được include. Sau render, xác minh HTML/PDF được tạo mới.

Checklist trước render:

- Documentation tests đã thực sự chạy.
- Test report không có failure hoặc skipped ngoài dự kiến.
- Snippets directory tồn tại.
- Identifier và file include đều có mặt.
- File không rỗng và thuộc build hiện tại.

Checklist sau render:

- HTML/PDF có build identity hiện tại.
- Không còn nội dung từ snippet cũ.
- Request/response sections hiển thị đúng.
- Không có secret hoặc dữ liệu fixture không được phép công bố.
- Artifact được gắn với đúng commit.

Có thể tạo task verifyDocs hoặc script validation riêng. Task đó nên thất bại với thông báo cụ thể nếu thiếu file.

## 10. Ví dụ task tổng hợp trong Gradle

Có thể tạo task tổng hợp mà developer và CI cùng gọi:

```groovy
tasks.register("restDocs") {
    dependsOn(tasks.named("test"))
    dependsOn(tasks.named("asciidoctor"))
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
}
```

Đây là ví dụ. Nếu project dùng docsTest, thay dependency tương ứng và bảo đảm asciidoctor cũng phụ thuộc task tạo snippet. Tránh vòng dependency; test không được phụ thuộc ngược vào restDocs.

Command:

```bash
./gradlew clean restDocs
```

Clean giúp output cũ bị xóa trước khi task test và render chạy theo dependency graph.

## 11. Ví dụ lifecycle tổng quát trong Maven

Với Maven, một cách đơn giản là gắn Asciidoctor vào phase sau khi test hoàn tất:

```text
validate
   │
compile
   │
test
   │
prepare-package
   │
Asciidoctor render
   │
package
   │
verify
```

Đây là sơ đồ rút gọn cho trường hợp documentation tests chạy ở phase test. Nếu dùng Failsafe, sơ đồ phải phản ánh integration-test và verify; chuyển Asciidoctor tới vị trí sau các phase đó. Lifecycle chính xác còn phụ thuộc execution/plugin binding của project.

## 12. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Asciidoctor báo include file không tồn tại | Test chưa chạy hoặc sai identifier | Gắn dependency và kiểm tra đường dẫn include |
| Render thành công nhưng snippet cũ | Không clean generated output | Clean trước test |
| Gradle gọi riêng asciidoctor không chạy test | Thiếu dependsOn | Khai báo dependency trên task render |
| Maven render trước integration tests | Gắn plugin ở phase quá sớm | Chuyển execution sau Failsafe |
| Test task chạy nhưng không có snippet | Test bị filter/skip hoặc không gọi document | Kiểm tra test report và operation |
| Local chạy, CI lỗi include | Snippets directory khác nhau | Dùng một property/attribute thống nhất |
| Test fail nhưng tài liệu vẫn publish | Ignore failure hoặc continue-on-error | Bỏ cấu hình bỏ qua lỗi |
| Snippet directory không rỗng sau clean | Output nằm ngoài build/target hoặc clean chưa xóa | Xác định output directory và clean đúng nơi |
| HTML có nội dung cũ | Render dùng output cũ hoặc không chạy lại | Clean, test, render trong cùng lifecycle |
| Include response-fields bị thiếu | Descriptor chưa sinh file đó | Sửa descriptor hoặc include đúng file |

## 13. Bài thực hành

Tích hợp tài liệu API orders với Gradle hoặc Maven. Documentation tests tạo snippet cho GET order; AsciiDoc include request, response, headers và fields.

**Nhiệm vụ:**

1. Xác định test task thực sự tạo snippet.
2. Cấu hình Asciidoctor phụ thuộc vào task đó.
3. Chọn snippets directory duy nhất và dùng cùng giá trị ở recorder và renderer.
4. Cấu hình clean output trước test.
5. Nếu dùng Maven Failsafe, đặt Asciidoctor sau giai đoạn integration tests hoàn tất.
6. Xác nhận test failure khiến render/publish dừng.
7. Kiểm tra mọi identifier/file được include tồn tại trước render.
8. Render HTML/PDF từ snippets của build hiện tại.
9. Kiểm tra test report, snippets và artifact gắn cùng commit.
10. Chạy build từ clean state và xác nhận task order đúng.

**Tiêu chí hoàn thành:** Asciidoctor không chạy trước documentation tests; snippets directory thống nhất; test fail hoặc thiếu snippet làm build thất bại; tài liệu render từ output mới, không dùng file cũ.

## 14. Ghi nhớ

- Documentation tests tạo snippet; Asciidoctor đọc và render snippet. Test phải chạy trước render.
- Gradle cần khai báo task dependency, thường qua dependsOn.
- Maven cần gắn Asciidoctor vào phase sau phase thực thi documentation tests; chú ý khác biệt Surefire và Failsafe.
- Recorder và renderer phải dùng chung snippets directory.
- Clean output trước test để tránh snippet cũ che giấu operation chưa được tạo.
- Test failure, test bị skip ngoài dự kiến hoặc thiếu snippet phải ngăn phát hành tài liệu.
- Kiểm tra include trước render và HTML/PDF sau render.
- Build tái lập cần chạy test và render từ cùng source revision, cùng output provenance.
