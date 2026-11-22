# Thư mục target/generated-snippets của Maven

## 1. Vai trò của target/generated-snippets

Trong dự án dùng **Apache Maven**, thư mục **target/generated-snippets** thường được cấu hình làm nơi lưu snippet do Spring REST Docs sinh ra khi chạy test. Khi một bài test gọi **document(...)**, REST Docs ghi các tệp mô tả request, response, header, parameter hoặc payload vào thư mục con theo document identifier.

Ví dụ:

~~~text
project/
├── pom.xml
├── src/
│   ├── main/
│   ├── test/
│   └── docs/
│       └── asciidoc/
│           └── index.adoc
└── target/
    └── generated-snippets/
        └── registrations/
            └── create/
                ├── http-request.adoc
                ├── http-response.adoc
                ├── curl-request.adoc
                └── request-fields.adoc
~~~

**target** là thư mục build output thông thường của Maven. **generated-snippets** là tài liệu trung gian được sinh tự động từ test; các tệp này thường được Asciidoctor include để tạo tài liệu API hoàn chỉnh. Nhóm phát triển duy trì test và descriptor làm nguồn, thay vì chỉnh tay snippet đã sinh.

Trong module **SPRING_REST_DOCS**, test HTTP với MockMvc, WebTestClient hoặc REST Assured tạo snippet có thể kiểm chứng. Tài liệu Asciidoctor/Markdown kết hợp các snippet thành trang hướng dẫn API; Maven điều phối test và bước render, CI chạy lại pipeline để bảo đảm tài liệu khớp hành vi endpoint.

## 2. Vì sao Maven thường dùng target/generated-snippets?

Spring REST Docs không bắt buộc mọi dự án Maven phải dùng một đường dẫn cố định. **target/generated-snippets** là quy ước phổ biến vì:

- **target/** là build directory mặc định của Maven, tách kết quả build khỏi mã nguồn.
- **generated-snippets/** thể hiện rõ đây là output được sinh từ test.
- Các snippet có thể được dùng làm input cho plugin Asciidoctor Maven.
- **mvn clean** loại bỏ build output, bao gồm snippet cũ, trước lần build sạch tiếp theo.

Phân biệt các thư mục thường gặp:

| Đường dẫn | Vai trò |
| --- | --- |
| src/test/java | Mã nguồn kiểm thử |
| src/docs/asciidoc | Tài liệu AsciiDoc do nhóm viết |
| target/generated-snippets | Snippet sinh từ kiểm thử |
| target/generated-docs hoặc thư mục output Asciidoctor | Tài liệu đã render, tùy cấu hình plugin |
| target/classes | Class đã compile |

Snippet là kết quả trung gian. HTML/PDF được render là artifact tiếp theo. Không trỏ thuộc tính snippets tới thư mục HTML đã render và không xem snippet là mã nguồn tài liệu được chỉnh trực tiếp.

## 3. Cấu hình Spring REST Docs ghi vào target/generated-snippets

### 3.1. Cấu hình bằng @AutoConfigureRestDocs

Trong Spring Boot test dùng MockMvc, có thể chỉ định output directory ngay trên lớp test:

~~~java
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;

@WebMvcTest(RegistrationController.class)
@AutoConfigureRestDocs(outputDir = "target/generated-snippets")
class RegistrationDocumentationTest {
    // MockMvc tests
}
~~~

Khi test gọi:

~~~java
document("registrations/create", ...);
~~~

snippet sẽ được ghi dưới:

~~~text
target/generated-snippets/
└── registrations/
    └── create/
        ├── http-request.adoc
        ├── http-response.adoc
        └── ...
~~~

Giá trị outputDir trong annotation cho biết vị trí mà Spring Boot test auto-configuration chuyển cho REST Docs. Đây là cấu hình tường minh, dễ đọc khi dự án chỉ có một thư mục output.

Nếu bỏ qua outputDir, hành vi mặc định có thể phụ thuộc phiên bản Spring Boot và cơ chế tích hợp REST Docs. Không nên giả định mặc định luôn là target/generated-snippets. Với dự án Maven, khai báo tường minh và đồng bộ với POM là cách ít gây nhầm lẫn nhất.

### 3.2. Cấu hình qua system property

Spring REST Docs hỗ trợ cấu hình output directory qua system property **org.springframework.restdocs.outputDir**. Maven Surefire có thể truyền property này cho JVM chạy test:

~~~xml
<properties>
<restdocs.outputDir>${project.build.directory}/generated-snippets</restdocs.outputDir>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <systemPropertyVariables>
                    <org.springframework.restdocs.outputDir>
                        ${restdocs.outputDir}
                    </org.springframework.restdocs.outputDir>
                </systemPropertyVariables>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Trong cấu hình này:

- **project.build.directory** thường phân giải thành target.
- **restdocs.outputDir** tạo một property dự án để dùng lại trong POM.
- Surefire đặt system property vào JVM test.
- REST Docs đọc property để ghi snippet nếu test harness không truyền output directory tường minh khác.

**Chọn một nguồn cấu hình chính.** Nếu annotation **@AutoConfigureRestDocs(outputDir = "...")** chỉ định outputDir, giá trị trên annotation có thể ghi đè ý định cấu hình qua system property. Đừng cấu hình annotation trỏ một nơi và Surefire trỏ nơi khác rồi kỳ vọng snippet tự đồng bộ.

### 3.3. Test dùng JUnit extension

Nếu không sử dụng Spring Boot test annotation, có thể cấu hình REST Docs qua **RestDocumentationExtension**:

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

JUnit extension cung cấp context cho REST Docs. Output directory được chọn bởi context provider/extension hoặc cấu hình REST Docs của phiên bản thư viện đang sử dụng. Khi cần Maven dùng target/generated-snippets, hãy xác nhận context provider nhận đúng output path; không chỉ khai báo property trong POM mà không kiểm tra test harness có sử dụng nó.

## 4. Cấu hình plugin Maven để render Asciidoctor

Một Maven build thường có hai giai đoạn liên quan:

1. Surefire chạy test, REST Docs tạo snippet.
2. Asciidoctor Maven Plugin đọc trang AsciiDoc cùng snippet và render HTML/PDF.

POM mẫu (rút gọn, các version plugin cần được quản lý tập trung theo dự án):

~~~xml
<properties>
    <restdocs.outputDir>${project.build.directory}/generated-snippets</restdocs.outputDir>
    <asciidoctor.outputDir>${project.build.directory}/generated-docs</asciidoctor.outputDir>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <systemPropertyVariables>
                    <org.springframework.restdocs.outputDir>
                        ${restdocs.outputDir}
                    </org.springframework.restdocs.outputDir>
                </systemPropertyVariables>
            </configuration>
        </plugin>

        <plugin>
            <groupId>org.asciidoctor</groupId>
            <artifactId>asciidoctor-maven-plugin</artifactId>
            <version>${asciidoctor.maven.plugin.version}</version>
            <executions>
                <execution>
                    <id>generate-api-docs</id>
                    <phase>prepare-package</phase>
                    <goals>
                        <goal>process-asciidoc</goal>
                    </goals>
                    <configuration>
                        <sourceDirectory>src/docs/asciidoc</sourceDirectory>
                        <outputDirectory>${asciidoctor.outputDir}</outputDirectory>
                        <attributes>
                            <snippets>${restdocs.outputDir}</snippets>
                        </attributes>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Đây là khung minh họa để hiểu các liên kết cấu hình, không phải POM hoàn chỉnh dùng trực tiếp mà không kiểm tra phiên bản plugin và dependency management. Property **asciidoctor.maven.plugin.version** cần được khai báo bằng phiên bản đã chọn trong dự án.

### 4.1. Ý nghĩa các phần trong POM

| Thành phần | Vai trò |
| --- | --- |
| restdocs.outputDir | Nguồn cấu hình thư mục snippet |
| Surefire systemPropertyVariables | Truyền output path vào JVM chạy test |
| sourceDirectory | Nơi chứa tệp AsciiDoc nguồn |
| outputDirectory | Nơi plugin ghi tài liệu đã render |
| attributes/snippets | Đường dẫn để giải quyết {snippets} trong include |
| prepare-package | Phase render sau các phase test trước đó trong lifecycle chuẩn |

Đặt render ở phase sau test giúp snippet được sinh trước khi Asciidoctor include chúng. Nếu gắn plugin vào phase quá sớm, tài liệu có thể thất bại vì snippet chưa tồn tại.

### 4.2. Dùng include trong AsciiDoc

Giả sử test sinh identifier **registrations/create-form**, trang **src/docs/asciidoc/index.adoc** có thể viết:

~~~adoc
= Registration API

== Tạo đăng ký bằng form

=== HTTP request
include::{snippets}/registrations/create-form/http-request.adoc[]

=== Form parameters
include::{snippets}/registrations/create-form/form-parameters.adoc[]

=== HTTP response
include::{snippets}/registrations/create-form/http-response.adoc[]
~~~

Maven truyền attribute snippets bằng đường dẫn target/generated-snippets. Đường dẫn include bên dưới attribute được tính theo document identifier và tên snippet. Khi đổi identifier hoặc output directory, cần cập nhật đúng cấu hình/include liên quan.

## 5. Maven lifecycle và thứ tự chạy

Một pipeline thường dùng:

~~~bash
mvn clean verify
~~~

Trong lifecycle Maven chuẩn:

- **test** phase chạy test thông qua Surefire.
- Test gọi document(...) và sinh snippet.
- **prepare-package** diễn ra sau test và trước package.
- Plugin Asciidoctor gắn ở prepare-package render tài liệu từ snippet.
- Các phase tiếp theo có thể đóng gói tài liệu vào artifact nếu POM cấu hình.

Chạy riêng:

~~~bash
mvn test
~~~

sẽ chạy test và sinh snippet nhưng không nhất thiết render Asciidoctor nếu plugin được gắn ở prepare-package. Để tạo tài liệu, hãy gọi phase đủ muộn, ví dụ **mvn prepare-package**, **mvn package** hoặc **mvn verify**.

Ngược lại, chạy riêng goal plugin Asciidoctor mà không chạy test trước có thể khiến thư mục snippet trống hoặc chứa dữ liệu cũ. Trong CI, ưu tiên một lifecycle command duy nhất để Maven quản lý thứ tự thực thi.

## 6. Cấu hình multi-module Maven

Giả sử repository có:

~~~text
root/
├── pom.xml
├── registration-api/
│   ├── pom.xml
│   └── target/generated-snippets/
└── documentation/
    ├── pom.xml
    └── src/docs/asciidoc/index.adoc
~~~

Mỗi Maven module có **project.build.directory** riêng; mặc định là target nằm bên trong module đó. Vì thế test của registration-api có thể tạo snippet ở:

~~~text
registration-api/target/generated-snippets/
~~~

Trong khi module documentation cần đọc snippet từ module API. Cần chọn một trong hai cách:

1. Cấu hình plugin tài liệu trong cùng module có test và snippet.
2. Cấu hình rõ output/input dùng chung hoặc copy artifact snippet qua một bước Maven được quản lý.

Không giả định project.build.directory ở child module tự trỏ đến target của root project. Trong Maven reactor, property đó được giải quyết theo project hiện tại. Với tài liệu tổng hợp nhiều API, thiết kế một đường dẫn chia sẻ rõ ràng và bảo đảm module sinh snippet chạy trước module render docs qua dependency/module ordering.

Nếu dùng đường dẫn chia sẻ ở root, hãy tham chiếu root build directory bằng property phù hợp của Maven sau khi kiểm tra mô hình reactor. Không hard-code đường dẫn tuyệt đối phụ thuộc máy developer.

## 7. Quản lý snippet cũ và build sạch

Snippet cũ có thể còn lại nếu test hoặc document identifier đã bị xóa. Ví dụ build trước sinh:

~~~text
target/generated-snippets/
├── registrations/create/
└── registrations/update/
~~~

Sau khi test update bị xóa, thư mục registrations/update có thể còn tồn tại nếu build không dọn output. Tài liệu khi đó có thể include nhầm snippet cũ và làm người đọc tin rằng API vẫn được kiểm chứng.

Thực hành tốt:

1. Giữ snippet trong target/ để mvn clean quản lý.
2. Chạy mvn clean verify khi cần tái tạo toàn bộ tài liệu.
3. Không chỉnh trực tiếp các tệp generated snippet.
4. Sửa test/descriptor rồi chạy lại lifecycle tạo tài liệu.
5. Không include snippet từ workspace khác hoặc cache cũ mà không kiểm chứng nguồn.

**mvn clean** xóa build output, trong đó có target/generated-snippets; test sau đó tạo bộ snippet mới. Đây là cách đơn giản để tránh tệp mồ côi trong một build sạch.

## 8. Khác biệt với Gradle

Tên thư mục thường thấy phụ thuộc build tool:

| Build tool | Build directory | Snippet directory thường dùng |
| --- | --- | --- |
| Maven | target/ | target/generated-snippets |
| Gradle | build/ | build/generated-snippets |

Hai đường dẫn này là quy ước, không phải giới hạn kỹ thuật của Spring REST Docs. Có thể tùy chỉnh nhưng phải giữ nhất quán giữa test, build task/plugin và Asciidoctor attribute.

Không sao chép nguyên cấu hình Gradle outputs.dir, inputs.dir, dependsOn sang POM. Maven quản lý thứ tự qua lifecycle phase, plugin execution và quan hệ dependency giữa module.

## 9. Sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| target/generated-snippets không tồn tại | Chưa chạy test có document(...), test bị skip hoặc REST Docs chưa cấu hình | Chạy test cụ thể và xem log Surefire |
| Snippet xuất hiện ở build/generated-snippets | Annotation hoặc system property đang trỏ đến đường dẫn Gradle | Đối chiếu outputDir thực tế |
| Test tạo snippet nhưng Asciidoctor không tìm thấy | snippets attribute trỏ sai vị trí hoặc identifier/include không khớp | So sánh absolute path, identifier và tên file |
| mvn test xong nhưng chưa có HTML | Asciidoctor gắn ở phase sau test | Chạy mvn prepare-package hoặc mvn verify |
| HTML chứa snippet cũ | Output không được clean sau khi xóa test/identifier | Chạy mvn clean verify |
| Chạy module docs nhưng thiếu snippet từ module API | Module sinh snippet chưa chạy hoặc output không được chia sẻ | Cấu hình reactor/module ordering và đường dẫn artifact |
| System property không có hiệu lực | Test annotation/context provider chỉ định output path khác | Chọn một cấu hình chính và kiểm tra test harness |
| Snippet có nhưng include lỗi | Đường dẫn tương đối thiếu document identifier | Include đúng thư mục identifier dưới snippet root |

Checklist kiểm tra:

1. Surefire có chạy test tạo tài liệu không?
2. Test harness nhận output directory nào?
3. Snippet được ghi vào target của module nào?
4. Asciidoctor Maven Plugin chạy ở phase nào?
5. Attribute snippets trỏ đúng thư mục snippet không?
6. Include có đúng identifier và tên snippet không?
7. Build sạch có sinh lại được toàn bộ tài liệu không?

## 10. Bài tập thực hành

Trong một Spring Boot Maven project, tạo test MockMvc cho endpoint POST /registrations và sinh http-request.adoc, http-response.adoc, form-parameters.adoc.

Thực hiện:

1. Cấu hình restdocs.outputDir thành project.build.directory/generated-snippets.
2. Truyền system property org.springframework.restdocs.outputDir vào JVM test bằng Surefire.
3. Viết test gọi document("registrations/create-form", ...).
4. Cấu hình Asciidoctor Maven Plugin dùng cùng restdocs.outputDir làm attribute snippets.
5. Gắn execution render tài liệu vào phase sau test, ví dụ prepare-package.
6. Include request, form parameters và response vào trang AsciiDoc.
7. Chạy mvn clean verify, kiểm tra snippet dưới target/generated-snippets/registrations/create-form/ và HTML ở output directory.
8. Xóa hoặc đổi document identifier, build sạch lần nữa và xác nhận tài liệu không dùng snippet cũ.

**Tiêu chí hoàn thành:** Surefire ghi snippet vào đúng target directory; Asciidoctor đọc đúng cùng thư mục; Maven lifecycle bảo đảm test trước render; clean build tạo tài liệu đầy đủ, không phụ thuộc output cũ.

## Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Surefire Plugin — System Properties](https://maven.apache.org/surefire/maven-surefire-plugin/examples/system-properties.html)
- [Asciidoctor Maven Plugin — Usage](https://docs.asciidoctor.org/maven-tools/latest/plugin/usage/)
