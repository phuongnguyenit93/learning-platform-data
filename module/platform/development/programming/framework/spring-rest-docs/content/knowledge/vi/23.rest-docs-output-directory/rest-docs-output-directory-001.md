# Thư mục generated-snippets mặc định của Gradle

## 1. Vai trò của build/generated-snippets

Trong dự án dùng **Gradle**, thư mục **build/generated-snippets** thường được chọn làm nơi lưu snippet do Spring REST Docs tạo ra khi chạy test. Mỗi lần test gọi **document(...)**, REST Docs ghi các tệp mô tả request, response, header, parameter hoặc payload vào thư mục con theo document identifier.

Ví dụ:

~~~text
project/
├── build.gradle
├── src/
│   ├── main/
│   ├── test/
│   └── docs/
│       └── asciidoc/
│           └── index.adoc
└── build/
    └── generated-snippets/
        └── registrations/
            └── create/
                ├── http-request.adoc
                ├── http-response.adoc
                ├── curl-request.adoc
                └── request-fields.adoc
~~~

Thư mục **build** là output directory của Gradle và thường được tạo lại khi build. **generated-snippets** chứa tài liệu trung gian do test sinh tự động. Các tệp này thường được Asciidoctor include để tạo tài liệu API hoàn chỉnh; chúng không phải mã nguồn cần chỉnh sửa thủ công.

Trong module **SPRING_REST_DOCS**, các bài test HTTP với MockMvc, WebTestClient hoặc REST Assured là nguồn kiểm chứng cho tài liệu. Snippet ghi lại request/response mà test thực hiện; Asciidoctor hoặc Markdown biên soạn chúng thành tài liệu, sau đó CI có thể render trong mỗi lần build. Vì vậy, thư mục output phải thống nhất giữa test, task build và đường dẫn include.

## 2. Vì sao thường dùng build/generated-snippets?

Spring REST Docs không bắt buộc mọi dự án phải dùng đúng một thư mục. Đây là quy ước phổ biến trong cấu hình Gradle:

- **build/** là output directory chuẩn của Gradle, tách kết quả build khỏi mã nguồn.
- **generated-snippets/** diễn tả rõ nội dung là các snippet tài liệu được sinh tự động từ test.
- Đường dẫn tương đối thường được giải quyết theo project directory của Gradle project/module đang chạy task.
- Có thể khai báo thư mục này là output của task test và input của task Asciidoctor.

Phân biệt các thư mục:

| Đường dẫn | Vai trò |
| --- | --- |
| src/test/java | Mã nguồn kiểm thử |
| src/docs/asciidoc | Tài liệu AsciiDoc do nhóm viết |
| build/generated-snippets | Snippet sinh từ kiểm thử |
| build/docs hoặc build/asciidoc | Tài liệu đã render, tùy cấu hình plugin |
| build/classes | Class đã compile |

Thư mục snippet là kết quả trung gian. Thư mục HTML/PDF được render là artifact đầu ra tiếp theo. Không trỏ attribute snippets tới thư mục HTML đã render, cũng không include tệp từ src/test.

## 3. Cấu hình output directory trong test

### 3.1. MockMvc với @AutoConfigureRestDocs

Trong Spring Boot, cách đơn giản là khai báo output directory trên annotation:

~~~java
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;

@WebMvcTest(RegistrationController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class RegistrationDocumentationTest {
    // MockMvc tests
}
~~~

Khi test gọi:

~~~java
document("registrations/create", ...);
~~~

snippet được ghi dưới:

~~~text
build/generated-snippets/
└── registrations/
    └── create/
        ├── http-request.adoc
        ├── http-response.adoc
        └── ...
~~~

Giá trị outputDir là đường dẫn được test harness sử dụng làm thư mục output. Trong dự án nhiều module, hãy xác định test chạy ở Gradle subproject nào và đường dẫn tương đối được giải quyết từ project directory nào; đừng mặc định nó luôn tương đối với thư mục gốc repository.

### 3.2. MockMvc với JUnit extension

Nếu không dùng @AutoConfigureRestDocs, có thể cấu hình REST Docs qua RestDocumentationExtension và truyền context provider cho MockMvc:

~~~java
@ExtendWith({SpringExtension.class, RestDocumentationExtension.class})
@WebMvcTest(RegistrationController.class)
class RegistrationDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(
            WebApplicationContext context,
            RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(context)
            .apply(documentationConfiguration(restDocumentation))
            .build();
    }
}
~~~

Extension cung cấp context cho Spring REST Docs. Nếu cần đổi output directory với cách cấu hình này, hãy dùng constructor/cấu hình của RestDocumentationExtension phù hợp với phiên bản đang dùng. Không cấu hình nhiều cơ chế output khác nhau mà không có lý do; chọn một nguồn cấu hình chính để nhóm biết snippet được ghi ở đâu.

### 3.3. Giữ một đường dẫn thống nhất

Tránh trường hợp annotation cấu hình test ghi vào **build/generated-snippets**, nhưng Gradle lại khai báo:

~~~groovy
def snippetsDir = file('build/snippets')
~~~

Khi đó test ghi vào một nơi, còn Asciidoctor đọc nơi khác. Hãy dùng cùng một giá trị cho:

1. Output directory REST Docs của test.
2. Output directory khai báo trên task test.
3. Input directory và snippets attribute của task Asciidoctor.
4. Đường dẫn gốc dùng trong include::{snippets}/...[].

## 4. Gradle: khai báo test tạo snippet

Ví dụ Groovy DSL:

~~~groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}
~~~

Đoạn này khai báo với Gradle rằng task test tạo nội dung tại build/generated-snippets. Gradle có thể dùng thông tin output khi lập kế hoạch task và kiểm tra trạng thái up-to-date.

Khai báo output không tự cấu hình Spring REST Docs. Test vẫn cần cấu hình output directory, ví dụ:

~~~java
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
~~~

Hai phần cần khớp nhau: annotation điều khiển nơi REST Docs ghi file; outputs.dir mô tả output đó với Gradle.

## 5. Nối task test với asciidoctor

Một cấu hình thường dùng:

~~~groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.absolutePath
}
~~~

Ý nghĩa từng khai báo:

| Khai báo | Ý nghĩa |
| --- | --- |
| outputs.dir snippetsDir | Test task tạo snippet tại thư mục đã chọn |
| dependsOn test | Asciidoctor chạy sau test |
| inputs.dir snippetsDir | Gradle biết Asciidoctor đọc các snippet này |
| attributes snippets | Asciidoctor nhận đường dẫn thay cho biến snippets trong include |

Khi chạy:

~~~bash
./gradlew test asciidoctor
~~~

Gradle chạy test, tạo snippet, rồi dùng snippet làm đầu vào khi render tài liệu. Nếu test thất bại, task Asciidoctor phụ thuộc vào test không thể hoàn tất thành công.

### 5.1. Vì sao cần cả dependency và input?

**dependsOn** mô tả thứ tự thực thi: Asciidoctor cần chạy sau test. **inputs.dir** mô tả dữ liệu mà Asciidoctor đọc để tạo output. Hai khai báo phục vụ hai mục đích khác nhau.

Nếu chỉ thêm dependsOn, thứ tự có thể đúng nhưng Gradle chưa được thông báo đầy đủ về input directory để tính trạng thái task. Nếu chỉ thêm inputs.dir, Gradle biết thư mục được đọc nhưng không nhất thiết biết task test nào phải chạy để sinh dữ liệu đó.

## 6. Include snippet trong Asciidoctor

Giả sử test đã gọi:

~~~java
document("registrations/create",
    requestFields(
        fieldWithPath("email").description("Email đăng ký"),
        fieldWithPath("plan").description("Gói đăng ký")
    )
);
~~~

Trang src/docs/asciidoc/index.adoc có thể include:

~~~adoc
= Registration API

== Tạo đăng ký

=== HTTP request
include::{snippets}/registrations/create/http-request.adoc[]

=== Request fields
include::{snippets}/registrations/create/request-fields.adoc[]

=== HTTP response
include::{snippets}/registrations/create/http-response.adoc[]
~~~

Attribute snippets trỏ tới build/generated-snippets, nên phần include được giải quyết thành đường dẫn đầy đủ bên trong thư mục đó. Dùng {snippets} giúp đổi output directory ở một nơi thay vì lặp lại đường dẫn tuyệt đối ở mọi include.

### 6.1. Đường dẫn include tương đối với snippet root

Nếu identifier là registrations/create, không include:

~~~adoc
include::{snippets}/http-request.adoc[]
~~~

vì tệp nằm dưới thư mục con registrations/create. Đường dẫn đúng là:

~~~adoc
include::{snippets}/registrations/create/http-request.adoc[]
~~~

Tên tệp snippet phải đúng loại operation được tạo. Ví dụ formParameters(...) tạo form-parameters.adoc, requestFields(...) tạo request-fields.adoc và responseFields(...) tạo response-fields.adoc. Kiểm tra tệp thực tế nếu dùng custom snippet hoặc phiên bản REST Docs khác.

## 7. Đường dẫn tương đối và dự án multi-module

### 7.1. Đường dẫn tương đối

file('build/generated-snippets') trong Gradle được giải quyết theo project directory của project thực thi build script. Với dự án một module ở repository root, thường là:

~~~text
<repository>/build/generated-snippets
~~~

Trong cấu trúc multi-project, nếu cấu hình nằm trong subproject service-api, đường dẫn có thể là:

~~~text
<repository>/service-api/build/generated-snippets
~~~

Điều này thường là mong muốn vì snippet thuộc về test của module đó. Nếu muốn tập trung snippet ở root project, phải cấu hình rõ ràng và thống nhất đường dẫn ở test và Asciidoctor; không dựa vào vị trí working directory của IDE.

### 7.2. Dùng layout.buildDirectory

Trong Gradle hiện đại, có thể lấy build directory qua project layout:

~~~groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}
~~~

Đây là Provider cho thư mục output. Khi cần truyền đường dẫn cho REST Docs hoặc Asciidoctor, lấy giá trị từ provider nhất quán theo API Gradle đang dùng. Cấu hình đơn giản với Groovy DSL cũng có thể tiếp tục dùng file('build/generated-snippets'); layout.buildDirectory hữu ích khi dự án tùy biến buildDirectory.

Nếu build directory được đổi qua layout.buildDirectory, đừng để annotation Java vẫn ghi cứng build/generated-snippets trong khi task đọc thư mục build khác. Cần một giá trị cấu hình thống nhất, có thể truyền vào test bằng system property hoặc cấu hình test phù hợp.

## 8. Quản lý snippet cũ và build tái lập

Snippet cũ có thể còn lại nếu test bị xóa hoặc document identifier đổi. Ví dụ lần build trước sinh:

~~~text
registrations/create/
registrations/update/
~~~

Ở lần build mới, test update đã bị xóa nhưng thư mục registrations/update có thể vẫn còn nếu output không được làm sạch theo quy trình build. Khi đó tài liệu có nguy cơ include một ví dụ cũ không còn được kiểm chứng trong lần build hiện tại.

Nguyên tắc thực hành:

1. Để snippet nằm trong thư mục build do Gradle quản lý.
2. Dùng clean hoặc workspace build sạch khi cần tái tạo toàn bộ tài liệu.
3. Không chỉnh tay tệp generated snippet; sửa test/descriptor rồi chạy lại.
4. Không commit snippet cũ như mã nguồn nếu quy trình của dự án yêu cầu chúng được sinh trong build.
5. Kiểm tra output HTML và các include khi đổi identifier hoặc thư mục output.

Ví dụ pipeline local:

~~~bash
./gradlew clean test asciidoctor
~~~

clean xóa output build trước khi chạy lại; sau đó test sinh snippet mới và Asciidoctor render từ kết quả mới. Với build nhanh hằng ngày, có thể chạy task incremental nếu quan hệ input/output được cấu hình đúng.

## 9. Maven dùng thư mục khác theo quy ước phổ biến

Chủ đề này tập trung vào Gradle. Tuy vậy, trong dự án Maven, bạn có thể gặp:

~~~text
target/generated-snippets/
~~~

Đây là quy ước thường thấy ở cấu hình Maven của Spring REST Docs. Maven build output dùng target/, trong khi Gradle thường dùng build/. Không thay đường dẫn trong dự án Maven bằng build/generated-snippets chỉ vì đó là ví dụ của Gradle. Cấu hình REST Docs, plugin tài liệu và include phải thống nhất với build tool đang dùng.

| Build tool | Thư mục snippet thường dùng |
| --- | --- |
| Gradle | build/generated-snippets |
| Maven | target/generated-snippets |

Đây là quy ước cấu hình phổ biến, không phải giới hạn kỹ thuật: cả hai build tool đều có thể dùng đường dẫn tùy chỉnh.

## 10. Kiểm tra khi snippet không xuất hiện hoặc Asciidoctor không tìm thấy file

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| build/generated-snippets không tồn tại | Chưa chạy test có document(...), test bị skip hoặc REST Docs chưa cấu hình | Chạy test cụ thể và xem log |
| Snippet nằm trong target/generated-snippets | Test harness/project đang dùng đường dẫn khác | Đối chiếu output directory của REST Docs |
| Snippet ghi vào subproject nhưng Asciidoctor đọc root | Khác project directory | Kiểm tra absolute path của snippetsDir |
| Include báo file không tồn tại | Identifier hoặc tên snippet sai | Đối chiếu thư mục output và đường dẫn include |
| Tài liệu hiển thị snippet cũ | Output cũ còn sót hoặc task chưa nối dependency | Chạy clean test asciidoctor, kiểm tra task graph |
| Test tạo snippet nhưng Gradle không nhận output | Chưa khai báo outputs.dir | Đăng ký output directory trên test task |
| Asciidoctor chạy trước khi test sinh snippet | Thiếu dependsOn test | Khai báo task dependency |
| Incremental build không nhận thay đổi snippet | Chưa khai báo input directory | Khai báo inputs.dir snippetsDir |

Khi debug, xác nhận lần lượt:

1. Test có thực sự chạy và đi qua lệnh document(...) không?
2. REST Docs đang ghi vào absolute path nào?
3. Identifier đã tạo đúng thư mục con chưa?
4. Tên snippet được include có tồn tại không?
5. Asciidoctor dùng đúng snippets attribute không?
6. Gradle có dependency/input/output đúng không?

## 11. Bài tập thực hành

Trong một Gradle Spring Boot project, cấu hình endpoint POST /registrations và test MockMvc để sinh các snippet http-request.adoc, http-response.adoc và form-parameters.adoc.

Thực hiện:

1. Cấu hình @AutoConfigureRestDocs(outputDir = "build/generated-snippets").
2. Tạo test gọi document("registrations/create-form", ...).
3. Khai báo outputs.dir snippetsDir cho task test.
4. Cấu hình task asciidoctor có dependsOn test, inputs.dir snippetsDir và attribute snippets.
5. Include snippet từ src/docs/asciidoc/index.adoc.
6. Chạy ./gradlew clean test asciidoctor.
7. Xác nhận tệp sinh nằm dưới build/generated-snippets/registrations/create-form/ và HTML đã render có đầy đủ phần request/response.
8. Đổi identifier thành registrations/register-form, cập nhật include và build lại để quan sát đường dẫn output thay đổi.

**Tiêu chí hoàn thành:** Test ghi snippet đúng thư mục, Gradle hiểu output/input và thứ tự task, Asciidoctor include đúng file và build sạch không dùng snippet lỗi thời.

## Tài liệu tham khảo

- [Spring REST Docs — Getting Started (Gradle)](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Gradle User Manual — Organizing Gradle Projects](https://docs.gradle.org/current/userguide/organizing_gradle_projects.html)
- [Gradle User Manual — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html)
