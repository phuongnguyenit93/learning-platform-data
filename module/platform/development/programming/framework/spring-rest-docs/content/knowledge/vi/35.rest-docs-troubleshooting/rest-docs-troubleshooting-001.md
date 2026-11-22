# Không sinh snippet do test không chạy

## 1. Hiện tượng và nguyên tắc chẩn đoán

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Snippet chỉ được ghi khi test thực sự chạy tới phần tích hợp Spring REST Docs, thực thi request và gọi `document(...)`/filter tương ứng. Nếu test không được phát hiện, bị bỏ qua, không thuộc task/lifecycle đang chạy hoặc bị loại bởi filter, thư mục generated snippets sẽ không có output mới.

Triệu chứng thường gặp:

- Build thành công nhưng `build/generated-snippets` hoặc `target/generated-snippets` không xuất hiện.
- Thư mục snippets tồn tại nhưng không có thư mục operation mong đợi.
- Asciidoctor báo `include file not found` hoặc operation macro không có nội dung.
- Chạy test từ IDE có snippet, nhưng chạy build command/CI lại không có.
- Test report không có test REST Docs, hoặc test được đánh dấu skipped/ignored.

Điểm cần nhớ: **Asciidoctor không chạy HTTP test và không tạo snippet**. Nó chỉ đọc những file snippet đã có. Hãy chẩn đoán từ test discovery và task/lifecycle trước, rồi mới kiểm tra document filter và output path.

```mermaid
flowchart TD
    A[Không có snippet mới] --> B[Kiểm tra test report]
    B --> C{Test có được phát hiện?}
    C -->|Không| D[Kiểm tra source set, tên class/method, engine]
    C -->|Có| E{Test có thực thi?}
    E -->|Skipped| F[Kiểm tra tag/filter/profile/skip flag]
    E -->|Fail trước document()| G[Đọc exception và setup]
    E -->|Pass| H[Kiểm tra REST Docs filter và output path]
    D --> I[Chạy lại đúng test]
    F --> I
    G --> I
    H --> J[Kiểm tra operation directory và snippet files]
    I --> B
```

## 2. Xác nhận test có thực sự được chạy

Đừng bắt đầu bằng việc sửa Asciidoctor. Trước tiên, mở test report hoặc log của build và tìm tên test class/method tạo snippet.

Các câu hỏi cần trả lời:

1. Test class có nằm trong source set test được build tool nhận diện không?
2. Tên class/method có phù hợp quy tắc discovery của test engine/plugin không?
3. Test có bị exclude bởi include/exclude pattern, tag, group, profile hoặc property không?
4. Test có được chạy hay bị skipped/disabled/ignored?
5. Test có dừng ở lỗi khởi tạo context, dependency injection hoặc setup trước khi gửi HTTP request không?
6. Task/lifecycle đang chạy có bao gồm test source set/module chứa bài REST Docs không?

Một dòng `BUILD SUCCESSFUL` hoặc `BUILD SUCCESS` không chứng minh mọi test mong muốn đã chạy. Build có thể thành công khi không tìm thấy test, khi test bị skip, hoặc khi module chứa test không nằm trong lifecycle hiện tại.

## 3. Kiểm tra Gradle: source set, task và test discovery

Với Gradle, test Java thông thường nằm trong `src/test/java` và được chạy bởi task `test`. Nếu dự án dùng source set tùy chỉnh, integration test có thể thuộc task khác như `integrationTest` hoặc `docsTest`.

Kiểm tra danh sách task:

```bash
./gradlew tasks --all
```

Chạy test task với log chi tiết hơn:

```bash
./gradlew test --info
```

Chạy một test class cụ thể:

```bash
./gradlew test --tests "com.example.docs.BooksDocumentationTest"
```

Nếu test nằm trong task integration riêng:

```bash
./gradlew integrationTest --info
```

Tên task phải là task thực tế của dự án. Không mặc định `test` sẽ chạy các test thuộc source set tùy chỉnh.

### Kiểm tra source set

Cấu trúc chuẩn:

```text
src/
├── main/java/...
└── test/java/
    └── com/example/docs/BooksDocumentationTest.java
```

Nếu file nằm ở `src/integrationTest/java`, cần source set/task integration được cấu hình. Nếu file đặt nhầm trong `src/main/java`, nó không phải test source thông thường.

Ví dụ khai báo source set integration test (đã lược bớt cấu hình classpath/task):

```groovy
sourceSets {
    integrationTest {
        java.srcDir file('src/integrationTest/java')
        resources.srcDir file('src/integrationTest/resources')
        compileClasspath += sourceSets.main.output
        runtimeClasspath += output + compileClasspath
    }
}
```

Khai báo source set không tự bảo đảm task được chạy trong `check` hoặc trước Asciidoctor. Phải cấu hình task tương ứng và dependency build rõ ràng.

## 4. Kiểm tra JUnit test engine và tên test

Test có thể không được phát hiện nếu test engine hoặc naming convention không khớp.

| Trường hợp | Điều cần kiểm tra |
| --- | --- |
| JUnit 5 | Có JUnit Jupiter engine trong test runtime và `useJUnitPlatform()` nếu cấu hình Gradle cần khai báo. |
| JUnit 4 | Có JUnit 4 runner/provider phù hợp; không trộn cấu hình engine thiếu nhất quán. |
| Test class không được tìm thấy | Tên class có phù hợp include patterns của Gradle/Maven Surefire/Failsafe không? |
| Method không được chạy | Có annotation `@Test`, đúng import JUnit và không bị disable/condition bỏ qua không? |
| Test dùng `@Tag` | Tag filter có loại tag tài liệu ra khỏi lượt chạy không? |
| Test phụ thuộc profile/property | Điều kiện môi trường có khiến test bị disable hoặc assumption không thỏa không? |

Ví dụ JUnit 5 với Gradle:

```groovy
tasks.named('test') {
    useJUnitPlatform()
}
```

Ví dụ test:

```java
import org.junit.jupiter.api.Test;

class BooksDocumentationTest {

    @Test
    void documentGetBook() {
        // Gửi request và gọi Spring REST Docs document filter.
    }
}
```

Kiểm tra đúng import `org.junit.jupiter.api.Test` nếu dự án dùng JUnit 5. Một test dùng annotation từ engine khác nhưng build chỉ cấu hình Jupiter có thể không được phát hiện như mong đợi.

## 5. Kiểm tra filter, tag và điều kiện bỏ qua trong Gradle

Gradle có thể lọc test qua `--tests`, test filters, tag expressions, task configuration hoặc logic điều kiện. Ví dụ:

```bash
./gradlew test --tests "com.example.service.*"
```

Lệnh này chỉ chạy nhóm class khớp pattern. Nếu REST Docs test nằm trong package khác, nó sẽ bị loại.

JUnit 5 tag filter có thể được cấu hình:

```groovy
tasks.named('test') {
    useJUnitPlatform {
        includeTags 'unit'
    }
}
```

Nếu REST Docs test mang tag `documentation`, cấu hình chỉ include `unit` sẽ không chạy chúng. Có thể thêm tag cần thiết hoặc dùng task riêng cho documentation tests:

```groovy
tasks.register('documentationTest', Test) {
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform {
        includeTags 'documentation'
    }
}
```

Đây là ví dụ định hướng; nếu task `test` cũng chạy cùng class, hãy tránh chạy trùng hoặc cấu hình tag tách biệt có chủ đích. Kiểm tra `onlyIf`, `exclude`, `enabled`, `failOnNoMatchingTests` và property tùy chỉnh nếu task bị bỏ qua.

## 6. Các cờ skip test và profile build

Một số lệnh build có thể bỏ qua test hoặc chỉ compile test:

| Lệnh/cấu hình | Hệ quả có thể xảy ra |
| --- | --- |
| `-x test` (Gradle) | Bỏ qua task `test`; snippets không được tạo từ task đó. |
| `-DskipTests` (Maven Surefire convention) | Test có thể được compile nhưng không thực thi. |
| `-Dmaven.test.skip=true` | Có thể bỏ cả compile và chạy test. |
| Profile Maven không active | Plugin/test execution được khai báo trong profile có thể không chạy. |
| Gradle property điều khiển task | Task có thể bị disable hoặc skip theo cấu hình dự án. |
| `@Disabled`, `@Ignore`, assumptions | Test/method có thể không thực thi. |

Nếu mục tiêu là tạo tài liệu, không dùng lệnh skip test trong job tạo snippets. Một job unit test có thể được tối ưu riêng, nhưng documentation job phải chạy đúng test tạo snippet.

## 7. Kiểm tra Maven: Surefire, Failsafe và lifecycle

Maven thường dùng:

- **Surefire** để chạy unit tests trong pha `test`.
- **Failsafe** cho integration tests theo lifecycle `integration-test` và `verify`.

Nếu REST Docs tests nằm trong nhóm integration test nhưng build chỉ gọi `mvn test`, Failsafe có thể chưa chạy. Khi đó hãy dùng lifecycle phù hợp, thường là:

```bash
mvn clean verify
```

Kiểm tra test report:

```text
target/surefire-reports/
target/failsafe-reports/
```

Tên thư mục report tùy plugin cấu hình, nhưng đây là vị trí mặc định thường gặp. Tìm class REST Docs trong report để biết nó được phát hiện, chạy, skipped hay failed.

### Naming convention

Surefire và Failsafe có include patterns mặc định khác nhau. Ví dụ các tên `*Test` thường được Surefire nhận diện; các tên `*IT` thường được dùng cho integration tests với Failsafe. Nếu class tên `BooksDocumentationIT` nhưng chỉ chạy Surefire, test có thể không nằm trong nhóm được thực thi. Kiểm tra cấu hình `<includes>`, `<excludes>` và plugin execution thay vì đổi tên class một cách tùy tiện.

### Skip properties

Kiểm tra lệnh CI và POM xem có `skipTests`, `maven.test.skip` hoặc property riêng của dự án không. Nếu profile chứa Failsafe execution không active, `mvn verify` cũng không chạy integration test thuộc profile đó.

## 8. Xác nhận task/lifecycle có chạy trước Asciidoctor

Một lỗi khác là HTTP test tồn tại nhưng build chỉ gọi Asciidoctor. Ví dụ:

```bash
./gradlew asciidoctor
```

hoặc chỉ gọi goal render tài liệu Maven. Nếu không có dependency task/lifecycle bảo đảm test chạy trước, Asciidoctor có thể đọc thư mục rỗng hoặc snippets cũ.

Với Gradle, khai báo dependency:

```groovy
tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
}
```

Nếu snippets do `integrationTest` tạo, dependency phải trỏ đúng task:

```groovy
tasks.named('asciidoctor') {
    dependsOn tasks.named('integrationTest')
}
```

Với Maven, đặt Asciidoctor execution ở phase sau test tạo snippets và chạy lifecycle tới phase đó, ví dụ `verify` nếu test nằm ở Failsafe. Nếu test execution nằm trong profile, phải kích hoạt profile đó trong documentation build.

Không chỉ nhìn thứ tự trong file cấu hình; xem task graph hoặc build log để xác nhận task thực tế đã được schedule và chạy.

## 9. Nếu test chạy nhưng vẫn không có snippet

Khi test report xác nhận test đã chạy và pass, chuyển sang kiểm tra integration của Spring REST Docs:

1. Test có tạo request thực tế không?
2. REST Docs filter/extension có được gắn vào request không?
3. Test có gọi đúng `document("operation-id", ...)` không?
4. Request có đi tới bước thực thi filter trước khi test kết thúc không?
5. Output directory mà test dùng có trùng với nơi đang kiểm tra không?
6. Test có dùng identifier khác với tên thư mục đang tìm không?

Ví dụ REST Assured:

```java
given(this.specification)
        .filter(document("books-get"))
.when()
        .get("/api/books/42")
.then()
        .statusCode(200);
```

Ví dụ MockMvc:

```java
mockMvc.perform(get("/api/books/{id}", 42))
        .andExpect(status().isOk())
        .andDo(document("books-get"));
```

Ví dụ WebTestClient:

```java
webTestClient.get()
        .uri("/api/books/{id}", 42)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("books-get"));
```

Các đoạn code là ví dụ rút gọn; test cần cấu hình REST Docs integration tương ứng (REST Assured filter, MockMvc documentation configuration hoặc WebTestClient REST Docs filter) và static imports phù hợp với version. Nếu filter không được gắn vào request, test có thể pass mà không tạo snippet.

## 10. Kiểm tra output directory và operation identifier

Đừng mặc định snippet nằm ở một thư mục duy nhất. Các convention phổ biến:

| Build tool | Output mặc định thường dùng |
| --- | --- |
| Gradle | `build/generated-snippets/` |
| Maven | `target/generated-snippets/` |

Dự án có thể tùy chỉnh output directory. Kiểm tra cấu hình `outputDirectory` hoặc snippets directory trong REST Docs setup, sau đó tìm operation identifier chính xác:

```text
generated-snippets/
└── books-get/
    ├── curl-request.adoc
    ├── http-request.adoc
    └── http-response.adoc
```

Thư mục `books-get` được xác định bởi identifier truyền vào `document("books-get", ...)`. Nếu test dùng `books-get-200`, việc tìm `books-get/` sẽ không thấy output.

Để tránh nhầm output cũ:

- Chạy `clean` trước build chẩn đoán.
- Kiểm tra timestamp của operation directory.
- Không chỉnh sửa thủ công generated snippets.
- Xác nhận Asciidoctor `{snippets}` trỏ đúng nơi test ghi file.

## 11. Chẩn đoán từ test report và build log

Đọc kết quả theo thứ tự:

| Kết quả quan sát | Kết luận ban đầu | Bước tiếp theo |
| --- | --- | --- |
| Không có test class trong report | Test không được discovery hoặc module/task không chạy. | Kiểm tra source set, naming convention, include/exclude, module selection. |
| Test có trạng thái skipped | Có filter, tag, disabled condition hoặc skip property. | Xem log lý do skip và cấu hình tương ứng. |
| Test failed trước HTTP request | Setup/context/fixture lỗi. | Sửa lỗi test trước khi xem snippet. |
| Test pass nhưng không có operation folder | Filter/document call hoặc output path sai. | Kiểm tra integration và identifier. |
| Snippet có nhưng Asciidoctor không thấy | `{snippets}` hoặc include path sai. | Đồng bộ output directory và attribute. |
| Local có, CI không có | Lệnh, profile, environment, task graph hoặc cache khác nhau. | So sánh command, properties, test report và build log. |

Đối với Gradle, có thể dùng `--info` hoặc `--debug` khi cần thêm thông tin, nhưng `--debug` có thể tạo log lớn và lộ thông tin môi trường. Chỉ dùng khi cần và rà soát log trước khi chia sẻ.

## 12. Ví dụ quy trình xử lý từ đầu đến cuối

Giả sử `BooksDocumentationTest` có `document("books-get")`, nhưng sau build không có `books-get/`.

**Bước 1 — Chạy đúng test class:**

```bash
./gradlew test --tests "com.example.docs.BooksDocumentationTest" --info
```

Nếu Gradle báo không có test khớp hoặc report không có class, kiểm tra package, source set, test engine và tên class.

**Bước 2 — Kiểm tra test report:**

Xác nhận method có trạng thái passed, không phải skipped. Nếu failed ở Spring context hoặc fixture setup, sửa lỗi đó trước.

**Bước 3 — Kiểm tra document integration:**

Xác nhận test gắn filter/configuration Spring REST Docs và request đi qua filter có `document("books-get")`.

**Bước 4 — Kiểm tra output:**

Tìm `build/generated-snippets/books-get/` hoặc custom output directory đã cấu hình. Xác nhận file mới được tạo.

**Bước 5 — Chạy render:**

```bash
./gradlew clean test asciidoctor
```

Nếu snippet đã có nhưng include lỗi, kiểm tra attribute `{snippets}` và filename trong AsciiDoc. Không tiếp tục sửa test nếu nguyên nhân thực tế chỉ là path include.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Build xanh nhưng không có snippet | Test không được schedule hoặc bị skip. | Đọc test report, kiểm tra task/lifecycle và skip flags. |
| Test class không được tìm thấy | Sai source set, naming pattern hoặc engine. | Đặt test đúng source set và cấu hình JUnit/Surefire/Failsafe phù hợp. |
| Chạy `mvn test` không chạy `*IT` | Integration test thuộc Failsafe execution. | Chạy lifecycle phù hợp như `mvn verify` và kích hoạt profile cần thiết. |
| `./gradlew asciidoctor` không tạo snippet | Chỉ chạy renderer, không chạy test tạo snippet. | Thêm dependency task hoặc chạy `test`/integration task trước. |
| Test bị skip trong CI | `-x test`, `-DskipTests`, tag filter hoặc property. | Sửa command/profile/filter cho documentation job. |
| Test pass nhưng thiếu `document(...)` output | Filter chưa gắn hoặc test dùng identifier khác. | Kiểm tra setup và lời gọi document trong test. |
| Snippet nằm ở thư mục khác | Output directory đã được custom. | Đọc cấu hình REST Docs và đồng bộ `{snippets}`. |
| Asciidoctor báo include không tồn tại | Test chưa tạo file hoặc include filename sai. | Xác nhận file output trước rồi mới sửa include. |
| Local pass nhưng CI thiếu snippet | CI chạy task/profile khác hoặc dùng cache/output cũ. | So sánh lệnh build, test report, profile và clean output. |

## 14. Checklist thực hành

- [ ] Đã xác nhận test class/method xuất hiện trong test report.
- [ ] Test có trạng thái thực thi, không bị skipped/disabled.
- [ ] Source set và task Gradle hoặc Maven lifecycle phù hợp.
- [ ] JUnit engine và test naming convention được cấu hình đúng.
- [ ] Tag, include/exclude, profile và skip flags không loại documentation test.
- [ ] Asciidoctor phụ thuộc đúng task tạo snippets.
- [ ] Test gắn Spring REST Docs filter/extension và gọi `document(...)`.
- [ ] Output directory và operation identifier khớp nơi đang kiểm tra.
- [ ] Build sạch không dùng snippet cũ.
- [ ] Chỉ chạy Asciidoctor sau khi test tạo snippet pass.
- [ ] CI dùng cùng cấu hình test/profile/task như build tài liệu dự kiến.

Khi không có snippet, hãy xác minh test có được phát hiện và thực thi trước khi kiểm tra Asciidoctor. Nếu test không chạy, nguyên nhân thường nằm ở source set, test engine, naming convention, filter/tag, skip flag hoặc lifecycle. Nếu test đã pass, tiếp tục kiểm tra REST Docs filter, `document(...)`, operation identifier và output directory. Cách chẩn đoán theo từng lớp giúp tìm đúng điểm đứt trong luồng test → snippet → Asciidoctor.

## Tài liệu tham khảo

- [Spring REST Docs – Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started.html)
- [Spring REST Docs – Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Gradle – Testing in Java Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Maven Surefire Plugin – Inclusions and Exclusions](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html)
- [Maven Failsafe Plugin – Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html)
