# Không tìm thấy output directory

## 1. Phân biệt thư mục snippets và thư mục tài liệu đã render

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ HTTP tests với MockMvc, WebTestClient hoặc REST Assured. Sau khi test chạy qua REST Docs integration, framework ghi các snippet như `http-request.adoc`, `http-response.adoc`, `request-fields.adoc` và `links.adoc` vào một thư mục output. Asciidoctor đọc những file này để tạo HTML/PDF ở một output directory khác.

Vì vậy, khi gặp lỗi “không tìm thấy output directory”, trước hết phải xác định **đang thiếu thư mục nào**:

| Thư mục | Chứa gì? | Thành phần tạo ra |
| --- | --- | --- |
| Generated snippets | Các file `.adoc` theo từng operation, ví dụ `books-get/http-response.adoc`. | Spring REST Docs trong lúc HTTP test chạy. |
| Asciidoctor source | `index.adoc`, các file operation và phần giải thích do nhóm viết. | Người biên soạn tài liệu/repository. |
| Rendered documentation | HTML, PDF hoặc DocBook. | Asciidoctor task/plugin. |

Các đường dẫn thường gặp:

```text
Gradle:
  build/generated-snippets/       # Spring REST Docs snippets
  build/docs/asciidoc/html5/      # HTML output, tùy cấu hình plugin

Maven:
  target/generated-snippets/     # Spring REST Docs snippets
  target/generated-docs/         # Có thể là HTML output, tùy cấu hình plugin
```

Đây là convention phổ biến, không phải đường dẫn bắt buộc. Dự án có thể cấu hình output directory khác. Không nên kết luận thư mục bị thiếu chỉ vì tìm ở path mặc định trong khi build đã được cấu hình custom path.

## 2. Xác định chính xác thành phần nào báo lỗi

Đọc thông báo lỗi và xác định nó đến từ test, Spring REST Docs hay Asciidoctor:

| Dấu hiệu | Khả năng liên quan |
| --- | --- |
| Test chạy nhưng không tạo thư mục `generated-snippets`. | Test không đi qua REST Docs filter, output directory khác hoặc không có operation được document. |
| Lỗi ghi file/directory trong lúc test. | Path không hợp lệ, quyền ghi, parent directory hoặc filesystem. |
| `include file not found`. | Asciidoctor không tìm thấy file snippet được include; có thể do `{snippets}` sai hoặc test chưa sinh file. |
| `operation::...` không có nội dung. | Operation ID không tồn tại trong snippets directory mà extension đang đọc. |
| HTML/PDF không xuất hiện. | Asciidoctor task/plugin chưa chạy, output path khác hoặc render thất bại. |

Đừng tạo thủ công một thư mục rỗng để làm mất lỗi. Cần tìm lý do thành phần chịu trách nhiệm ghi output không tạo được nội dung.

## 3. Kiểm tra nơi Spring REST Docs ghi snippets

Tìm cấu hình REST Docs của test và xác định output directory được truyền vào integration. Những cách cấu hình thường gặp:

- Spring Boot test annotation `@AutoConfigureRestDocs(outputDir = "...")`.
- JUnit `RestDocumentationExtension` với cấu hình output directory phù hợp.
- MockMvc `MockMvcRestDocumentation.documentationConfiguration(...)`.
- WebTestClient `WebTestClientRestDocumentation.documentationConfiguration(...)`.
- REST Assured `documentationConfiguration(restDocumentation)`.

Ví dụ Spring Boot với MockMvc:

```java
@WebMvcTest(BookController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class BookDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void getBook() throws Exception {
        mockMvc.perform(get("/api/books/{id}", 42))
                .andExpect(status().isOk())
                .andDo(document("books-get"));
    }
}
```

Ví dụ dùng `RestDocumentationExtension`:

```java
@ExtendWith(RestDocumentationExtension.class)
class BookDocumentationTest {

    @BeforeEach
    void setUp(WebApplicationContext context,
               RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

Trong ví dụ thứ hai, output directory được cung cấp qua `RestDocumentationContextProvider` và cấu hình extension. Nếu cần custom path, cấu hình extension/provider theo API và version đang dùng; đừng giả định annotation Spring Boot và JUnit extension luôn lấy cùng một path.

Khi dùng REST Assured hoặc WebTestClient, cũng cần gắn filter tương ứng vào request. Nếu filter/documentation configuration không được gắn, test có thể gửi HTTP thành công nhưng không có snippet.

## 4. Đồng bộ output directory với Gradle

Ví dụ Gradle sử dụng `build/generated-snippets`:

```groovy
plugins {
    id 'java'
    id 'org.asciidoctor.jvm.convert' version '3.3.2'
}

configurations {
    asciidoctorExt
}

def snippetsDir = layout.buildDirectory.dir('generated-snippets')

dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor'
}

tasks.named('test') {
    outputs.dir snippetsDir
    useJUnitPlatform()
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    configurations 'asciidoctorExt'
    attributes 'snippets': snippetsDir.get().asFile
}
```

Trong test, cấu hình REST Docs phải ghi vào cùng thư mục `build/generated-snippets`. `outputs.dir` chỉ khai báo output cho Gradle; nó **không tự cấu hình Spring REST Docs ghi vào đó**. Đây là hai việc riêng biệt và phải khớp nhau.

Nếu test đang ghi vào `target/generated-snippets` hoặc một thư mục custom, có hai lựa chọn: đổi test output directory để dùng convention Gradle, hoặc giữ nguyên test path rồi cập nhật `snippetsDir` và Asciidoctor attribute tương ứng. Tránh cấu hình mỗi thành phần một nơi.

## 5. Đồng bộ output directory với Maven

Maven convention thường dùng `${project.build.directory}/generated-snippets`, tương ứng `target/generated-snippets`:

```xml
<properties>
    <restdocs.outputDir>${project.build.directory}/generated-snippets</restdocs.outputDir>
</properties>
```

Với Spring Boot test, có thể dùng property/annotation để đặt output directory theo cấu hình dự án:

```java
@AutoConfigureRestDocs(outputDir = "target/generated-snippets")
class BookDocumentationTest {
    // HTTP tests
}
```

Asciidoctor Maven Plugin cần dùng đúng thư mục đó:

```xml
<configuration>
    <attributes>
        <snippets>${project.build.directory}/generated-snippets</snippets>
    </attributes>
</configuration>
```

Nếu module test và module tài liệu là hai Maven module khác nhau, `${project.build.directory}` được tính riêng cho từng module. Khi đó module docs có thể tìm `module-docs/target/generated-snippets`, trong khi test ghi ở `module-api/target/generated-snippets`. Hãy cấu hình đường dẫn liên module một cách tường minh hoặc chuyển snippets thành artifact mà module docs nhận được.

## 6. Kiểm tra đường dẫn trong multi-module project

Đây là nguyên nhân thường gặp khi chạy cục bộ trong module nhưng CI chạy từ root project.

Ví dụ:

```text
store-parent/
├── api-tests/
│   └── target/generated-snippets/
└── api-docs/
    ├── pom.xml
    └── target/generated-docs/
```

Test trong `api-tests` tạo snippets ở `api-tests/target/generated-snippets`. Asciidoctor chạy trong `api-docs` sẽ không tự nhìn thấy thư mục đó nếu attribute `snippets` trỏ tới `api-docs/target/generated-snippets`.

Hãy xác định:

1. Module nào chứa HTTP documentation tests?
2. Module nào chạy Asciidoctor?
3. Test ghi snippets ở đâu sau khi chạy từ reactor root?
4. Module docs nhận snippets bằng đường dẫn, copy task hay artifact dependency nào?
5. Build có bảo đảm module test chạy trước module docs không?

Không hard-code đường dẫn tuyệt đối của máy developer. Dùng đường dẫn tương đối từ project/module root hoặc cấu hình Maven/Gradle có thể tái lập trong CI.

## 7. Kiểm tra quyền ghi và filesystem

Nếu log cho thấy lỗi tạo directory hoặc ghi file, kiểm tra:

- User chạy Gradle/Maven có quyền ghi vào build directory không?
- Workspace có bị mount read-only hoặc khóa bởi tiến trình khác không?
- Parent directory có tồn tại và là directory thực, không phải file cùng tên không?
- Ổ đĩa còn dung lượng và giới hạn quota không?
- Path có chứa ký tự không hợp lệ, separator sai hoặc quá dài không?
- CI workspace có bị cleanup giữa test và Asciidoctor không?

Trên Linux/macOS có thể kiểm tra:

```bash
ls -ld build build/generated-snippets
test -w build && echo "build directory is writable"
```

Trên PowerShell:

```powershell
Get-Item .\build
Get-Item .\build\generated-snippets -ErrorAction SilentlyContinue
```

Nếu directory chưa tồn tại, `Get-Item` có thể báo không tìm thấy; điều đó chỉ xác nhận path chưa có, không xác định nguyên nhân. Xem log test và quyền ghi của workspace.

Không cấp quyền rộng như `chmod -R 777` để xử lý một lỗi chưa rõ nguyên nhân. Sửa owner/permission ở đúng thư mục build theo user chạy CI.

## 8. Phân biệt output directory của test và output directory của Asciidoctor

Hai cấu hình này thường bị nhầm:

```groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    outputDir = file("$buildDir/docs/asciidoc/html5")
}
```

`snippetsDir` là input của Asciidoctor, còn `outputDir` là nơi lưu HTML được render. Thay đổi `outputDir` không làm Spring REST Docs đổi nơi ghi snippets. Ngược lại, đổi snippets directory không tự đổi nơi HTML được xuất.

Với Maven cũng tương tự: `target/generated-snippets` là input, còn output directory của Asciidoctor Maven Plugin là output HTML/PDF. Khi thấy không có HTML, kiểm tra task/plugin render. Khi thấy include không tìm thấy, kiểm tra snippets path trước.

## 9. Chạy build sạch và xác minh thư mục

Để loại trừ output cũ hoặc cấu hình không được cập nhật, chạy clean build phù hợp.

Gradle:

```bash
./gradlew clean test --info
```

Sau khi test pass, kiểm tra:

```bash
find build/generated-snippets -maxdepth 2 -type f
```

Maven:

```bash
mvn clean test
```

Sau khi test pass, kiểm tra:

```bash
find target/generated-snippets -maxdepth 2 -type f
```

Các lệnh `find` là ví dụ cho shell Unix. Trên PowerShell có thể dùng:

```powershell
Get-ChildItem .\build\generated-snippets -Recurse -File
Get-ChildItem .\target\generated-snippets -Recurse -File
```

Nếu thư mục vẫn không có, kiểm tra test report và REST Docs filter. Nếu operation directory có file nhưng Asciidoctor không tìm thấy, kiểm tra attribute `snippets` và đường dẫn include.

## 10. Chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không có `generated-snippets` sau test | Test không chạy, filter không gắn hoặc output path khác. | Xem test report, `document(...)`, REST Docs setup và output directory. |
| Có `generated-snippets` nhưng không có operation folder | Identifier khác, test không tới document filter hoặc test scenario không chạy. | So sánh `document("operation-id")` và test report. |
| Có operation folder nhưng thiếu một số file | Chỉ một số descriptor/snippet được khai báo hoặc request không tới filter. | Kiểm tra `document(...)` và nội dung thực tế được test ghi. |
| Snippets có ở module A nhưng Asciidoctor tìm trong module B | Multi-module path chưa được chia sẻ. | Cấu hình artifact/copy path hoặc attribute liên module. |
| Include báo file không tồn tại | Attribute `snippets` sai hoặc filename/operation ID sai. | Xác minh file trên đĩa rồi sửa include/attribute. |
| Không tạo HTML/PDF | Asciidoctor task/plugin chưa chạy hoặc render thất bại. | Kiểm tra task lifecycle và output directory riêng của renderer. |
| Lỗi access denied | Workspace hoặc parent directory không cho user ghi. | Sửa permission/owner đúng phạm vi. |
| CI không có output nhưng local có | Path tương đối, module, user, cleanup hoặc task graph khác nhau. | So sánh build command, environment và log của CI. |

## 11. Quy trình xử lý từ đầu đến cuối

Giả sử test pass nhưng `books-get/http-response.adoc` không được tìm thấy:

1. Xem test report để xác nhận đúng test method đã chạy và không bị skip.
2. Tìm lời gọi `document("books-get", ...)` và xác nhận filter/extension được gắn vào request.
3. Kiểm tra cấu hình output directory của Spring REST Docs (annotation, extension hoặc custom setup).
4. Chạy clean test và tìm thư mục operation trong output directory thực tế.
5. Nếu file có ở path A nhưng Asciidoctor đọc path B, đồng bộ `{snippets}` và build configuration.
6. Nếu file không được tạo, đọc test log để tìm lỗi trước/sau khi document filter thực thi.
7. Nếu test và snippets đều đúng, kiểm tra tên file include, chữ hoa/thường và đường dẫn tương đối.
8. Chạy lại Asciidoctor sau khi test đã sinh output thành công.

Không sửa include để trỏ tới một thư mục tình cờ có snippet cũ. Hãy làm cho output directory của test và input directory của tài liệu thống nhất, tái lập được.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Tìm `build/generated-snippets` nhưng không có | Dự án dùng output custom hoặc test chưa ghi snippet. | Kiểm tra REST Docs configuration và test report. |
| `outputs.dir` đã khai báo nhưng directory vẫn rỗng | Gradle output declaration không tự cấu hình REST Docs writer. | Cấu hình test integration ghi đúng path. |
| Đổi Asciidoctor `outputDir` nhưng vẫn lỗi include | Đã đổi HTML output, không đổi snippets input. | Cấu hình attribute `snippets` riêng. |
| Spring Boot và JUnit extension ghi ra hai nơi | Hai test setup dùng cấu hình output khác nhau. | Chuẩn hóa output directory dùng chung. |
| Multi-module build tìm nhầm `target` | `${project.build.directory}` thuộc module hiện tại. | Truyền/copy snippets từ module test sang module docs. |
| Directory có nhưng không ghi được | Permission, mount hoặc quota. | Kiểm tra user và quyền ghi chính xác. |
| Có file cũ nên include vẫn pass | Clean không chạy hoặc output được cache/copy lại. | Clean đúng module và xác minh timestamp/build identity. |
| CI path khác local | Working directory hoặc module invocation khác. | Dùng project-relative configuration và chạy từ cùng entry point. |

## 13. Checklist thực hành

- [ ] Đã xác định đang thiếu snippets directory hay rendered HTML/PDF directory.
- [ ] Test report xác nhận HTTP documentation tests đã chạy.
- [ ] REST Docs filter/extension được gắn vào request và có `document(...)` đúng operation ID.
- [ ] Output directory của Spring REST Docs đã được xác định từ cấu hình thật.
- [ ] Gradle/Maven khai báo đúng input/output nhưng không nhầm khai báo task với cấu hình REST Docs writer.
- [ ] Asciidoctor `{snippets}` trỏ đúng nơi test ghi file.
- [ ] Multi-module build chia sẻ snippets giữa module test và module docs đúng cách.
- [ ] User chạy build có quyền ghi và workspace còn dung lượng.
- [ ] Clean build không dùng snippet cũ.
- [ ] Asciidoctor chạy sau test và dùng đúng snippets của lần build hiện tại.

Khi không tìm thấy output directory, hãy phân biệt nơi Spring REST Docs ghi snippets với nơi Asciidoctor xuất HTML/PDF. Sau đó lần theo cấu hình từ test integration, output directory, build task cho tới `{snippets}` và include path. Trong multi-module project, xác định rõ module sở hữu output và cách module tài liệu nhận output đó. Đồng bộ các đường dẫn và chạy clean build sẽ giúp lỗi được tái hiện và sửa đúng nguyên nhân.

## Tài liệu tham khảo

- [Spring REST Docs – Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started.html)
- [Spring REST Docs – JUnit 5 Support](https://docs.spring.io/spring-restdocs/reference/getting-started.html)
- [Spring REST Docs – Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Gradle – Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Maven – POM Reference: Build](https://maven.apache.org/pom.html#Build)
