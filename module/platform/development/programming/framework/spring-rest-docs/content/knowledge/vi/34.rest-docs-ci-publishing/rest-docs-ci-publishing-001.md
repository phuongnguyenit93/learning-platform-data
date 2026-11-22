# Chạy test tạo snippet trong CI

Spring REST Docs tạo tài liệu từ request và response được ghi nhận khi documentation tests chạy. Vì vậy, pipeline CI phải chạy các test này trước bước Asciidoctor/Markdown render. Nếu test không chạy, snippet có thể thiếu hoặc còn sót từ lần build trước; tài liệu khi đó không phản ánh phiên bản code hiện tại.

Pipeline đáng tin cậy cần thực hiện theo thứ tự: làm sạch output cũ, chạy test tạo snippet, xác minh test và snippet, render tài liệu, sau đó lưu artifact hoặc publish theo quy trình dự án. Test phải là điều kiện bắt buộc của build tài liệu. Khi operation thay đổi mà test tương ứng thất bại, CI cần dừng trước khi phát hành tài liệu không còn khớp API.

Bài học thuộc chương **CI và phát hành** của module `SPRING_REST_DOCS`. Module tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured, sinh snippet cho request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và tích hợp vào build, CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của documentation tests trong pipeline CI.
2. Sắp xếp clean, test, snippet generation và render theo đúng thứ tự.
3. Cấu hình Gradle hoặc Maven để test tạo snippet trước khi Asciidoctor chạy.
4. Phân biệt test task tạo snippet với task render tài liệu.
5. Lưu generated snippets và tài liệu đã render thành build artifacts.
6. Làm cho pipeline tái lập, phát hiện snippet cũ hoặc thiếu.
7. Thiết lập failure gate và kiểm soát dữ liệu nhạy cảm trước khi publish.

## 2. Vì sao phải chạy test tạo snippet trong CI?

Spring REST Docs không sinh nội dung từ controller annotations hoặc file mô tả API độc lập. Snippet được tạo khi test thực hiện request, kiểm tra response và gọi API document. Vì vậy, tài liệu liên hệ trực tiếp với test fixture, hành vi endpoint, assertions về status/header/body, descriptor cho fields/parameters/headers và preprocessors áp dụng trước khi ghi snippet.

Nếu pipeline chỉ render Asciidoctor mà không chạy test, include có thể tham chiếu file không tồn tại hoặc dùng snippet cũ. Tài liệu đôi khi vẫn build thành công nếu file cũ còn sót, nhưng nội dung không còn được kiểm chứng bởi code hiện tại.

### 2.1. Luồng pipeline chuẩn

```text
Checkout source
      │
      ▼
Resolve dependencies
      │
      ▼
Clean generated snippets
      │
      ▼
Run documentation tests
      │
      ├── Test failed ──► Fail CI
      │
      ▼
Verify generated snippets
      │
      ▼
Render Asciidoctor / Markdown
      │
      ▼
Verify rendered documentation
      │
      ▼
Upload build artifacts
      │
      ▼
Publish (nếu pipeline được phép)
```

Snippet generation nằm trong test execution. Asciidoctor chạy sau khi các test liên quan hoàn thành và tạo đủ snippet.

## 3. Tổ chức source và output

Một cấu trúc phổ biến:

```text
project/
├── src/
│   ├── main/
│   └── test/
│       └── java/
│           └── .../
│               └── OrdersDocumentationTests.java
├── src/docs/
│   └── asciidoc/
│       └── index.adoc
├── build/
│   └── generated-snippets/
└── build.gradle
```

Với Maven, output thường ở `target/generated-snippets`; với Gradle, nhiều dự án dùng `build/generated-snippets`. Đây là quy ước thường gặp, không phải đường dẫn bắt buộc. Chọn một output directory nhất quán và cấu hình cả test recorder lẫn Asciidoctor plugin cùng dùng directory đó.

Ví dụ trong test:

```java
.andDo(document("orders-get",
    requestHeaders(
        headerWithName("Accept")
            .description("Media type client chấp nhận")
    ),
    responseFields(
        fieldWithPath("id")
            .description("Mã đơn hàng"),
        fieldWithPath("status")
            .description("Trạng thái đơn hàng")
    )
));
```

Identifier `orders-get` quyết định thư mục con chứa snippet của operation. Tên identifier phải ổn định và được dùng thống nhất trong file AsciiDoc.

### 3.1. Không commit generated snippets như source mặc định

Thông thường, snippet là output được tạo lại từ test, nên nên nằm trong build directory và được tạo trong mỗi CI run. Điều này tránh nhầm file generated cũ với nội dung nguồn.

Một số dự án có thể chủ động lưu snapshot hoặc publish artifact riêng; khi đó cần quy định rõ cách cập nhật và review. Không để pipeline vô tình dùng snippet từ working tree hoặc cache cũ mà không kiểm tra nguồn gốc.

## 4. Chạy documentation tests với Gradle

Với Gradle, documentation tests thường là một phần của test source set hoặc một task test riêng. Nếu dùng task `test` chung, CI có thể chạy:

```bash
./gradlew clean test
```

Nếu dự án tách documentation tests thành task riêng, ví dụ `docsTest`:

```bash
./gradlew clean test docsTest
```

Tên `docsTest` chỉ là ví dụ; task thực tế phụ thuộc build script. Đảm bảo task tạo snippet được thực thi trước task Asciidoctor.

### 4.1. Gắn thứ tự task

Khi dùng Asciidoctor Gradle plugin, cấu hình task render phụ thuộc task test tạo snippet. Ví dụ cấu trúc khái quát:

```groovy
tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(layout.buildDirectory.dir("generated-snippets"))
}
```

Tên task và đường dẫn phải khớp dự án. Nếu test tạo snippet là `docsTest`, dùng task đó thay cho `test`. Khai báo input directory giúp Gradle hiểu nguồn snippet của task render.

Không chỉ dựa vào việc task chạy đúng thứ tự trong một lệnh CI thủ công; dependency giữa task giúp build vẫn đúng khi developer gọi riêng task Asciidoctor.

### 4.2. Khi test không tạo snippet

Nếu test bị filter, disabled hoặc không được include trong task, output directory có thể thiếu operation. Xác nhận số test được chạy trong log CI và kiểm tra identifier cần thiết có thư mục/file tương ứng.

## 5. Chạy documentation tests với Maven

Với Maven, documentation tests có thể chạy trong lifecycle test/verify tùy cách tổ chức dự án. Một lệnh thường gặp:

```bash
./mvnw clean verify
```

`clean` xóa output cũ; `verify` chạy các phase trước đó và plugin được gắn vào lifecycle. Lệnh chỉ tạo snippet và render tài liệu nếu test/plugin đã được cấu hình đúng trong `pom.xml`.

### 5.1. Đảm bảo Asciidoctor chạy sau test

Nếu dùng Asciidoctor Maven plugin, gắn execution vào phase sau khi documentation tests đã chạy thành công. Ví dụ khái quát:

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

Đây là cấu trúc minh họa; version plugin, goal, phase và output cần đối chiếu với dự án. Nếu documentation test bị cấu hình chạy muộn hơn `prepare-package`, điều chỉnh lifecycle để test hoàn tất trước render.

### 5.2. Chú ý test được skip

Một số cấu hình CI dùng property bỏ qua test. Không phát hành tài liệu dựa trên snippet cũ khi test bị skip. Pipeline publish cần bảo đảm documentation tests thực sự chạy; chỉ kiểm tra exit code của bước render là chưa đủ.

## 6. Liên kết test với Asciidoctor

Trong AsciiDoc, snippet được include bằng identifier tương ứng:

```asciidoc
= Orders API

== Lấy thông tin đơn hàng

=== Request

include::{snippets}/orders-get/http-request.adoc[]

=== Request headers

include::{snippets}/orders-get/request-headers.adoc[]

=== Response

include::{snippets}/orders-get/http-response.adoc[]

=== Response fields

include::{snippets}/orders-get/response-fields.adoc[]
```

Thuộc tính `snippets` phải trỏ đúng output directory mà test đã ghi. Có thể khai báo attribute trong file AsciiDoc hoặc truyền từ plugin build. Tránh hard-code hai đường dẫn khác nhau giữa local và CI.

### 6.1. Markdown và snippet

Markdown không hỗ trợ cú pháp include Asciidoctor theo mặc định. Nếu tài liệu đích là Markdown, cần bước chèn snippet hoặc chuyển đổi rõ ràng trong build. Pipeline phải chạy test trước bước tổng hợp Markdown và kiểm tra các đoạn được chèn lấy từ output hiện tại.

Không giả định copy thủ công snippet vào Markdown sẽ tự đồng bộ với test ở các lần build sau.

## 7. Clean output và tính tái lập

Snippet cũ có thể còn sót trong build directory. Ví dụ test từng sinh `orders-delete`, sau đó test bị đổi tên hoặc xóa; nếu không clean, thư mục snippet cũ có thể vẫn tồn tại và Asciidoctor tiếp tục include nó.

Dùng clean build cho pipeline tài liệu:

```bash
./gradlew clean test asciidoctor
```

Hoặc với Maven:

```bash
./mvnw clean verify
```

Các lệnh chỉ phù hợp khi task/lifecycle đã cấu hình đúng. Clean xóa generated output; test tạo lại snippet; render sử dụng output mới.

### 7.1. Kiểm soát cache

Nếu CI cache Gradle/Maven dependencies, đó là cache dependency; không nên cache generated snippets như source có thẩm quyền. Nếu cần cache build output, bảo đảm cache key bao gồm source/test/build configuration liên quan và task kiểm tra input/output đúng.

Đối với pipeline tài liệu public, clean generation thường đơn giản và đáng tin cậy hơn phục hồi snippet từ cache không rõ nguồn.

### 7.2. Kiểm tra output directory

Sau khi test chạy, xác minh directory output tồn tại; mỗi operation có identifier tương ứng; các file được include trong AsciiDoc đều có mặt; file không rỗng và được tạo trong build hiện tại; không còn identifier đã bị xóa hoặc đổi tên.

Có thể dùng script kiểm tra file hoặc task validation riêng. Script nên thất bại với thông báo rõ khi thiếu snippet, thay vì để lỗi chỉ xuất hiện ở bước render.

## 8. Failure gate: khi nào CI phải thất bại?

CI cần dừng nếu:

1. Documentation test thất bại.
2. Test được kỳ vọng chạy nhưng bị skip.
3. Operation cần tài liệu không sinh snippet.
4. Snippet được include không tồn tại hoặc rỗng.
5. Asciidoctor/Markdown render thất bại.
6. Secret scan phát hiện credential hoặc giá trị bị cấm.
7. Artifact không được tạo hoặc không có file tài liệu đầu ra theo yêu cầu.

Không dùng tùy chọn cho build tiếp tục khi test lỗi trong pipeline phát hành tài liệu. Nếu một test không liên quan được phép skip, hãy cấu hình nhóm test rõ ràng; đừng vô tình bỏ qua toàn bộ documentation tests.

### 8.1. Phân biệt lỗi test và lỗi render

| Lỗi | Ví dụ | Bước kiểm tra |
| --- | --- | --- |
| Test thất bại | Status/body không đúng assertion | Test report, application logs |
| Không sinh snippet | Test không chạy hoặc thiếu document(...) | Test count và generated-snippets |
| Include sai path | Identifier khác tên folder | AsciiDoc include và output tree |
| Render thất bại | Attribute hoặc AsciiDoc syntax sai | Asciidoctor logs |
| Nội dung cũ | Build không clean | Clean output và chạy lại test |
| Secret xuất hiện | Fixture/preprocessor không an toàn | Scan snippet và artifact |

## 9. Artifact của CI

Sau khi test và render thành công, lưu artifact cần thiết để review hoặc triển khai:

```text
build/
├── generated-snippets/
│   └── orders-get/
│       ├── http-request.adoc
│       └── http-response.adoc
└── docs/
    └── index.html
```

Có thể lưu generated snippets để debug/review; HTML/PDF đã render để preview; test reports để truy vết; build metadata như commit SHA, build number và version tài liệu.

Artifact nên gắn với commit/build cụ thể. Không trộn snippet của một commit với HTML của commit khác. Khi publish, lấy artifact từ cùng pipeline run đã chạy test và render thành công.

### 9.1. Artifact không thay thế source

Generated snippets và HTML/PDF là build outputs. Source có thẩm quyền vẫn là test, descriptor, nội dung AsciiDoc/Markdown và build configuration. Khi snippet sai, sửa test/preprocessor/descriptor rồi chạy lại pipeline; không chỉnh output artifact bằng tay.

## 10. Bảo mật khi tạo snippet trong CI

CI có thể chạy trong môi trường có nhiều biến môi trường và credential. Documentation tests không nên đọc token production hoặc secret thật chỉ để tạo ví dụ.

- Dùng fixture, test principal hoặc token giả chỉ hợp lệ trong test.
- Không truyền secret CI vào test nếu không cần cho hành vi đang kiểm tra.
- Dùng preprocessors để thay hoặc loại giá trị nhạy cảm khỏi snippet.
- Quét Authorization, Cookie, Set-Cookie, API key, URL token và dữ liệu cá nhân.
- Kiểm tra raw snippets, cURL/HTTPie, HTML/PDF và artifact upload.
- Không in secret vào log test hoặc failure message.

Secret scan là lớp bổ sung; fixture an toàn từ đầu vẫn quan trọng hơn. Nếu credential thật đã được publish, dừng phát hành, đánh giá phạm vi và thu hồi/rotate credential theo quy trình tổ chức.

## 11. Ví dụ pipeline CI tổng quát

Pipeline có thể được tổ chức thành các bước:

```yaml
steps:
  - name: Checkout
    run: checkout source

  - name: Clean and test
    run: ./gradlew clean test

  - name: Render REST documentation
    run: ./gradlew asciidoctor

  - name: Validate documentation
    run: ./gradlew verifyDocs

  - name: Upload artifacts
    uses: upload-artifact
    with:
      path: build/docs
```

Đây là pseudoconfiguration mô tả thứ tự, không phải workflow YAML có thể chạy nguyên trạng: cú pháp checkout/upload phụ thuộc CI provider và `verifyDocs` là task dự án cần tự định nghĩa. Nếu `asciidoctor` đã phụ thuộc vào `test`, có thể gọi một task tổng hợp; vẫn cần bảo đảm test thực sự chạy và output được clean.

### 11.1. Tách job test và job publish

Với pipeline lớn, có thể tách:

- **Test job:** chạy unit/integration/documentation tests và tạo snippets.
- **Render job:** nhận snippet artifact của cùng commit, render tài liệu.
- **Publish job:** chỉ chạy khi test, validation và render đều thành công.

Nếu tách job, artifact truyền giữa các job phải có commit/build identity rõ. Render job không nên tự lấy snippets từ cache hoặc artifact của lần chạy khác.

## 12. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Asciidoctor báo thiếu snippet | Test chưa chạy hoặc identifier sai | Chạy docs test trước render; kiểm tra identifier |
| Tài liệu vẫn build nhưng nội dung cũ | Generated directory không clean | Clean trước test và render |
| CI không tạo snippet nhưng local có | Documentation test bị exclude/skip trong CI | Kiểm tra test filters và profile |
| Task render chạy trước test | Thiếu dependency giữa tasks | Khai báo dependsOn hoặc lifecycle phase |
| Test pass nhưng file snippet thiếu | Test không gọi document hoặc operation chưa được cover | Kiểm tra test body và output tree |
| Snippet path khác nhau local/CI | Output directory cấu hình rời rạc | Dùng một property/attribute chung |
| Secret xuất hiện trong artifact | Fixture thật hoặc preprocessor chưa áp dụng | Dùng fake data, scan mọi output |
| Publish dù test thất bại | Pipeline cho phép continue-on-error/skip | Thiết lập failure gate |
| Render job dùng snippet khác commit | Artifact/cache không gắn commit | Truyền artifact cùng pipeline run |
| Markdown không include snippet | Dùng cú pháp Asciidoctor như Markdown mặc định | Thêm bước chèn/chuyển đổi rõ ràng |

## 13. Bài thực hành

Tích hợp documentation tests của API orders vào CI. Test tạo snippet cho `GET /api/orders/{id}` và `POST /api/orders`. Tài liệu AsciiDoc include request, response, header và field snippets.

**Nhiệm vụ:**

1. Xác định task Gradle hoặc Maven chạy documentation tests.
2. Chọn một generated-snippets directory thống nhất.
3. Cấu hình clean trước khi chạy test.
4. Đảm bảo test tạo snippet chạy trước Asciidoctor.
5. Thêm kiểm tra file snippet của từng identifier được include.
6. Cấu hình render tài liệu thành HTML hoặc PDF.
7. Thiết lập CI thất bại khi test, validation hoặc render lỗi.
8. Lưu test reports, generated snippets và rendered docs thành artifacts của cùng commit.
9. Thêm secret scan cho raw snippets và bản render.
10. Chạy pipeline từ clean state và xác nhận tài liệu không dùng output cũ.

**Tiêu chí hoàn thành:** documentation tests thực sự chạy trong CI; snippet được tạo mới; render chạy sau test; thiếu snippet hoặc test fail khiến pipeline dừng; artifact gắn với đúng commit; không có secret trong output.

## 14. Ghi nhớ

- Spring REST Docs tạo snippet khi documentation tests chạy; render tài liệu phải diễn ra sau bước này.
- Clean output trước test để tránh snippet cũ che giấu operation thiếu test.
- Gradle cần task dependency phù hợp; Maven cần lifecycle phase bảo đảm test chạy trước Asciidoctor.
- Test, snippet generation, validation và render phải là các bước bắt buộc trước publish.
- Dùng một output directory thống nhất cho recorder và Asciidoctor.
- Lưu snippet, HTML/PDF và test reports như artifacts của cùng commit/build.
- Dùng fixture giả, secret scan và review artifact để tránh công bố dữ liệu nhạy cảm.
- CI chỉ nên publish tài liệu khi test, snippet validation và render đều thành công.
