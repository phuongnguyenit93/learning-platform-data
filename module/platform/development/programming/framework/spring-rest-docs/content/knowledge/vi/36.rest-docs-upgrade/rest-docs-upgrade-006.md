# Kiểm tra output directory và plugin Asciidoctor

## Mục tiêu bài học

Khi nâng cấp Spring REST Docs hoặc build tool, test có thể vẫn chạy thành công nhưng tài liệu không được tạo. Nguyên nhân thường nằm ở output directory, task dependency, cấu hình plugin Asciidoctor, đường dẫn include hoặc việc artifact được tạo ở một thư mục khác với nơi renderer đang tìm.

Bài học thuộc chương **Nâng cấp** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown rồi tích hợp vào build và CI.

Sau bài học, bạn có thể:

- Xác định output directory thực tế của Spring REST Docs.
- Kiểm tra plugin Asciidoctor và extension dependency.
- Nối đúng thứ tự test → snippet → Asciidoctor → artifact.
- Cấu hình snippets attribute và include path chính xác.
- Phân biệt lỗi test, lỗi task, lỗi include và lỗi publish.
- Kiểm tra output trong môi trường CI sạch.
- Phát hiện snippet cũ hoặc output directory không đồng nhất.

## 1. Hiểu luồng sinh tài liệu

Spring REST Docs không tự tạo một website hoàn chỉnh chỉ bằng cách chạy test. Test sinh các snippet; Asciidoctor đọc tài liệu AsciiDoc và include các snippet đó để tạo HTML hoặc artifact khác.

~~~mermaid
flowchart TD
    A["MockMvc / WebTestClient / REST Assured tests"] --> B["Generated snippets"]
    B --> C["AsciiDoc source + include directives"]
    C --> D["Asciidoctor plugin"]
    D --> E["HTML documentation"]
    E --> F["CI artifact / publish"]
~~~

Mỗi bước có đầu vào và đầu ra riêng:

| Bước | Đầu vào | Đầu ra cần kiểm tra |
| --- | --- | --- |
| HTTP tests | Test code và fixture | Test result |
| REST Docs | Operation được document | Snippet theo document identifier |
| Asciidoctor | File AsciiDoc, attributes và snippet | HTML/PDF hoặc artifact đã cấu hình |
| CI | Output tài liệu | Artifact được lưu hoặc publish |

Khi lỗi, xác định bước đầu tiên không tạo ra đầu ra mong đợi. Điều này giúp tránh sửa include path khi thực tế test chưa sinh snippet.

## 2. Xác định output directory của REST Docs

Trong Gradle, cấu hình MockMvc thường dùng MockMvcRestDocumentationConfigurer với RestDocumentationContextProvider. Nếu không chỉ định output directory riêng, integration thường dùng thư mục output được cấu hình trong test setup hoặc convention của dự án.

Ví dụ cấu hình phổ biến:

~~~java
@BeforeEach
void setUp(WebApplicationContext context,
           RestDocumentationContextProvider restDocumentation) {
    this.mockMvc = MockMvcBuilders
        .webAppContextSetup(context)
        .apply(documentationConfiguration(restDocumentation))
        .build();
}
~~~

RestDocumentationContextProvider thường được cung cấp bởi JUnit integration và được cấu hình ở test runtime. Đừng đoán output directory chỉ từ đoạn test; hãy kiểm tra test rule/extension, build script và log của lần chạy thực tế.

Một dự án có thể dùng cấu trúc:

~~~text
build/
└── generated-snippets/
    ├── orders-get/
    │   ├── http-request.adoc
    │   └── http-response.adoc
    └── orders-create/
        ├── http-request.adoc
        ├── request-fields.adoc
        └── response-fields.adoc
~~~

Đây là ví dụ thư mục, không phải quy ước bắt buộc cho mọi dự án. Document identifier như orders-get tạo thư mục con tương ứng; tên file phụ thuộc snippet/template được dùng.

### 2.1. Kiểm tra file snippet sau khi chạy test

Chạy đúng test task:

~~~powershell
./gradlew test
~~~

Sau đó kiểm tra:

~~~powershell
Get-ChildItem -Path build/generated-snippets -Recurse -File
~~~

Nếu dự án cấu hình output ở vị trí khác, thay path bằng thư mục đã xác nhận trong configurer hoặc test output. Kiểm tra ít nhất một operation đại diện và xác nhận nội dung file không rỗng.

### 2.2. Phân biệt output test với output tài liệu

Không nhầm:

- build/generated-snippets: snippet do REST Docs sinh.
- build/docs/asciidoc hoặc build/docs: file tài liệu đã render, tùy plugin và cấu hình.
- build/reports/tests: báo cáo test của Gradle.

Đường dẫn chính xác phụ thuộc build script. Không hard-code một đường dẫn giả định vào include hoặc CI nếu project đã dùng convention khác.

## 3. Cấu hình plugin Asciidoctor trong Gradle

Một build Gradle có thể dùng plugin AsciidoctorJ:

~~~groovy
plugins {
    id 'java'
    id 'org.asciidoctor.jvm.convert' version '4.0.2'
}
~~~

Ví dụ dependency extension và task:

~~~groovy
configurations {
    asciidoctorExt
}

dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc:3.0.3'
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor:3.0.3'
}

tasks.named('asciidoctor') {
    configurations 'asciidoctorExt'
    inputs.dir layout.buildDirectory.dir('generated-snippets')
    attributes 'snippets': layout.buildDirectory.dir('generated-snippets').get().asFile
}
~~~

Các version trong ví dụ chỉ để minh họa. Hãy chọn plugin và Spring REST Docs version tương thích với Gradle/JDK/Spring của dự án. Không nâng plugin Asciidoctor và REST Docs cùng lúc nếu chưa có lý do; tách thay đổi giúp xác định nguyên nhân khi build fail.

asciidoctorExt đưa extension vào classpath của Asciidoctor. Plugin cần được áp dụng và cấu hình đúng để task render hiểu extension và attributes. Nếu không dùng extension của Spring REST Docs, không thêm dependency chỉ vì thấy nó trong ví dụ.

## 4. Nối task test với Asciidoctor

Asciidoctor phải chạy sau khi snippet được sinh. Có thể khai báo dependency:

~~~groovy
tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
}
~~~

Nếu test được chia thành nhiều task, ví dụ test MockMvc và test REST Assured, task Asciidoctor phải phụ thuộc vào tất cả task tạo snippet cần include.

Không tạo dependency vòng tròn. Ví dụ, test không được phụ thuộc Asciidoctor nếu Asciidoctor đã phụ thuộc test.

Luồng build tổng quát:

~~~groovy
tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
}

tasks.named('build') {
    dependsOn tasks.named('asciidoctor')
}
~~~

Tên task có thể khác nếu project tự định nghĩa. Kiểm tra task graph bằng:

~~~powershell
./gradlew asciidoctor --dry-run
~~~

Lệnh dry-run cho biết các task được lập lịch, không chứng minh snippet thực sự được tạo. Sau đó chạy task thật và kiểm tra file output.

## 5. Cấu hình snippets attribute và include

Trong AsciiDoc, dùng document attribute để chỉ thư mục snippet:

~~~asciidoc
:snippets: build/generated-snippets

== Lấy đơn hàng

=== HTTP request

include::{snippets}/orders-get/http-request.adoc[]

=== HTTP response

include::{snippets}/orders-get/http-response.adoc[]
~~~

Trong Gradle, attribute có thể được cấu hình theo output directory:

~~~groovy
tasks.named('asciidoctor') {
    attributes 'snippets': layout.buildDirectory
        .dir('generated-snippets')
        .get()
        .asFile
}
~~~

Hai cách trên phải trỏ tới cùng một thư mục thực tế. Nếu attribute đặt trong source file và build script cũng truyền attribute cùng tên, kiểm tra precedence theo cách Asciidoctor/plugin xử lý thuộc tính.

Một số dự án dùng attribute được cung cấp bởi extension Spring REST Docs. Đọc đúng tài liệu của version đang cài để tránh khai báo trùng hoặc ghi đè giá trị do extension thiết lập.

## 6. Kiểm tra tên snippet và document identifier

Một lỗi phổ biến là include sai tên file:

~~~asciidoc
include::{snippets}/orders-get/http-request.adoc[]
~~~

Trong khi test lại ghi:

~~~java
document("order-get")
~~~

Hai identifier khác nhau sẽ tạo hai thư mục output khác nhau. Kiểm tra:

- Chuỗi truyền vào document(...).
- Thư mục con được tạo trong generated snippets.
- Tên snippet thực tế do REST Docs sinh.
- Phần mở rộng .adoc hay .md theo template format.
- Đường dẫn tương đối của include sau khi Asciidoctor xử lý.

Không đổi tên file thủ công để làm include pass. Sửa document identifier hoặc include dựa trên output thật và chủ đích tài liệu.

## 7. Kiểm tra plugin và version đã resolve

Với Gradle, xem plugin và dependency:

~~~powershell
./gradlew buildEnvironment
./gradlew dependencyInsight --dependency spring-restdocs --configuration testRuntimeClasspath
~~~

Kiểm tra:

- Plugin Asciidoctor có được áp dụng trong đúng module không.
- Plugin version có tương thích Gradle wrapper và JDK không.
- Extension spring-restdocs-asciidoctor có ở đúng configuration không.
- REST Docs core và integration artifact có cùng version không.
- Test task tạo snippet có chạy trước Asciidoctor không.

Với Maven, kiểm tra plugin trong pom.xml, effective POM và execution phase. Không mặc định mvn test tự tạo HTML nếu plugin Asciidoctor được gắn vào phase khác.

## 8. Kiểm tra output directory trong CI

Local build có thể pass vì thư mục build/generated-snippets còn file từ lần chạy trước. CI thường bắt đầu trong workspace sạch nên lỗi đường dẫn hoặc task dependency sẽ xuất hiện.

Trong CI, nên:

1. Dùng Gradle wrapper hoặc Maven version được project pin.
2. Chạy test sinh snippet.
3. Xác nhận các snippet bắt buộc tồn tại.
4. Chạy Asciidoctor.
5. Kiểm tra HTML/artifact output.
6. Upload/publish đúng thư mục đã cấu hình.

Ví dụ pipeline Gradle:

~~~yaml
steps:
  - name: Generate REST Docs and render
    run: ./gradlew clean test asciidoctor

  - name: Verify documentation output
    shell: pwsh
    run: |
      if (-not (Test-Path 'build/docs/asciidoc')) {
        throw 'Asciidoctor output directory not found'
      }
      Get-ChildItem 'build/docs/asciidoc' -Recurse -File
~~~

Đây là ví dụ minh họa; thay đường dẫn bằng output directory thật của plugin và workflow. Một số plugin tạo HTML ở build/docs/asciidoc, nhưng không nên mặc định điều đó nếu task đã tùy chỉnh outputDir.

## 9. Chẩn đoán theo từng lớp

Khi tài liệu không được tạo, kiểm tra theo thứ tự:

| Lớp | Câu hỏi | Hành động |
| --- | --- | --- |
| Test | Test REST Docs có chạy không? | Kiểm tra test report và filter |
| Snippet | File có được tạo không? | Liệt kê output directory |
| Identifier | Thư mục operation có đúng ID? | So sánh document(...) với include |
| Extension | Asciidoctor có nhận extension không? | Kiểm tra configuration/plugin classpath |
| Attribute | {snippets} có trỏ đúng path? | Kiểm tra attribute sau cấu hình |
| Include | File include có tồn tại và đúng extension? | Đối chiếu generated output |
| Render | Task Asciidoctor có thành công? | Đọc log và output directory |
| Publish | Artifact có được upload? | Kiểm tra path trong CI step |

Đừng bắt đầu bằng cách xóa cache hoặc thay plugin version nếu chưa biết lớp nào lỗi. Làm sạch output có kiểm soát có ích để phát hiện stale snippets, nhưng phải bảo đảm task test chạy lại và tạo đủ đầu vào.

## 10. Cấu hình Maven ở mức khái niệm

Với Maven, pipeline tương tự nhưng được nối qua plugin executions:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.asciidoctor</groupId>
            <artifactId>asciidoctor-maven-plugin</artifactId>
            <version>VERSION_OF_PLUGIN</version>
            <executions>
                <execution>
                    <phase>prepare-package</phase>
                    <goals>
                        <goal>process-asciidoc</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

VERSION_OF_PLUGIN là placeholder, cần thay bằng version đã xác nhận tương thích. Cấu hình source directory, output directory, attributes, extensions và dependency plugin theo đúng version plugin Maven đang dùng.

Đảm bảo test chạy trước phase tạo tài liệu. Nếu snippets chỉ được sinh bởi một profile hoặc test group, cấu hình Maven phải kích hoạt đúng profile đó trước khi render.

## 11. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Không có generated snippets | Test không chạy hoặc documentation filter không gắn | Kiểm tra test task và setup integration |
| Snippet nằm sai thư mục | Output directory trong test khác attribute của Asciidoctor | Dùng một path thống nhất |
| Include báo file không tồn tại | Document ID hoặc tên snippet không khớp | Đối chiếu output thật |
| Include dùng .md nhưng file là .adoc | Template format không đúng như giả định | Cấu hình template hoặc sửa include |
| asciidoctor không phải task | Plugin chưa apply hoặc sai module | Kiểm tra plugins block và project path |
| Extension không được nạp | Sai configuration hoặc thiếu dependency | Kiểm tra asciidoctorExt/plugin classpath |
| Local pass, CI fail | Stale output hoặc CI không chạy test tạo snippet | Chạy clean test trước Asciidoctor |
| HTML không xuất hiện | OutputDir khác hoặc task không chạy | Kiểm tra task log và cấu hình output |
| Publish artifact rỗng | Upload sai thư mục | Dùng đúng output directory của task |
| Build chạy trước khi snippet hoàn tất | Thiếu task dependency | Nối asciidoctor với task sinh snippet |

## 12. Bài thực hành

Với operation:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42))
    .andExpect(status().isOk())
    .andDo(document("orders-get"));
~~~

Hãy:

1. Xác định output directory mà test đang sử dụng.
2. Chạy test và xác nhận orders-get cùng các snippet thực tế được tạo.
3. Kiểm tra plugin Asciidoctor và version đã resolve.
4. Cấu hình snippets attribute trỏ đúng output directory.
5. Include http-request và http-response vào file AsciiDoc.
6. Nối task Asciidoctor sau task test sinh snippet.
7. Chạy build sạch để phát hiện phụ thuộc vào output cũ.
8. Kiểm tra HTML được tạo và upload đúng artifact trong CI.

**Tiêu chí hoàn thành:** test sinh snippet trong output directory xác định; Asciidoctor resolve đúng include; build sạch tạo HTML; CI lưu đúng artifact và thất bại nếu snippet bắt buộc bị thiếu.

## Ghi nhớ

Khi kiểm tra pipeline Spring REST Docs, lần theo đường đi từ test tới snippet, từ snippet tới Asciidoctor và từ HTML tới CI artifact. Output directory của test phải trùng với đường dẫn mà snippets attribute và include sử dụng. Plugin Asciidoctor cùng extension phải được cấu hình ở đúng module và đúng version; task render phải phụ thuộc vào task sinh snippet. Luôn thử build sạch để phát hiện file cũ, xác nhận tên operation và phần mở rộng snippet, rồi kiểm tra artifact cuối trước khi publish.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs Asciidoctor setup](https://docs.spring.io/spring-restdocs/reference/getting-started/documentation.html), [Asciidoctor Gradle Plugin](https://docs.asciidoctor.org/gradle-plugin/latest/), [Asciidoctor Maven Plugin](https://docs.asciidoctor.org/maven-tools/latest/) và [Gradle task dependencies](https://docs.gradle.org/current/userguide/controlling_task_execution.html).
