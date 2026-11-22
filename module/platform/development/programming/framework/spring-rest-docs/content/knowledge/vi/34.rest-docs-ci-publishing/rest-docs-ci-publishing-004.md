# Đưa tài liệu generated vào artifact

## 1. Mục tiêu và luồng tạo artifact

Spring REST Docs tạo snippet từ test HTTP chạy bằng MockMvc, WebTestClient hoặc REST Assured. Các snippet như `http-request.adoc`, `http-response.adoc`, `request-fields.adoc` là dữ liệu trung gian. Asciidoctor dùng chúng cùng tài liệu AsciiDoc nguồn để render HTML/PDF. Bước đóng gói tiếp theo đưa tài liệu đã render vào artifact để CI lưu trữ, release pipeline phát hành hoặc một website nội bộ triển khai.

Luồng thông thường:

~~~text
Source code + documentation tests
                |
                v
         Run HTTP tests
                |
                v
      generated-snippets/
                |
                v
      AsciiDoc + includes
                |
                v
           Asciidoctor
                |
                v
       Rendered HTML / PDF
                |
                v
       ZIP / JAR / PDF artifact
                |
                v
       CI artifact storage / release
~~~

Trong module **SPRING_REST_DOCS**, tài liệu REST API phải phản ánh request/response đã được kiểm chứng. Vì vậy artifact cần được tạo từ cùng commit và cùng lần chạy test của bản build. Không đóng gói snippet cũ hoặc tài liệu render từ một workspace không rõ nguồn gốc.

## 2. Chọn loại artifact

Trước khi cấu hình build, xác định ai sẽ sử dụng artifact:

| Loại artifact | Nội dung | Mục đích |
| --- | --- | --- |
| HTML ZIP | Toàn bộ website HTML và tài nguyên đi kèm | Upload lên CI, tải xuống hoặc triển khai lên static hosting |
| PDF | Tài liệu đã render thành PDF | Tải xuống, lưu trữ hoặc gửi kèm release |
| Snippets ZIP | Các snippet theo document identifier | Chia sẻ với module docs khác hoặc nhóm tích hợp |
| AsciiDoc source bundle | AsciiDoc, include và resources cần thiết | Tái tạo tài liệu ở môi trường khác |
| JAR classifier | HTML hoặc tài liệu được đặt trong JAR | Phân phối qua Maven/Gradle repository |

Thông thường, người dùng API cần HTML/PDF. Snippet phù hợp hơn với nhóm phát triển hoặc pipeline biên soạn tài liệu. Không nhất thiết phát hành mọi loại artifact trong mỗi lần build.

Một HTML artifact cần chứa toàn bộ file liên quan:

~~~text
api-docs/
├── index.html
├── css/
├── js/
├── images/
└── ...
~~~

Chỉ copy index.html sẽ làm mất CSS, hình ảnh hoặc trang con. Hãy đóng gói toàn bộ output directory của Asciidoctor.

## 3. Gradle: tạo ZIP từ tài liệu đã render

Giả sử task asciidoctor render tài liệu vào build/docs/asciidoc. Tạo task ZIP:

~~~groovy
def renderedDocs = layout.buildDirectory.dir('docs/asciidoc')

tasks.register('apiDocsZip', Zip) {
    dependsOn tasks.named('asciidoctor')
    from(renderedDocs)
    archiveBaseName = 'registration-api-docs'
    archiveClassifier = 'html'
    destinationDirectory = layout.buildDirectory.dir('distributions')
}
~~~

Task apiDocsZip có dependency vào asciidoctor, do đó tài liệu được render trước khi ZIP đọc thư mục output.

Chạy:

~~~bash
./gradlew clean apiDocsZip
~~~

Artifact thường nằm dưới:

~~~text
build/distributions/
└── registration-api-docs-html.zip
~~~

Tên cuối cùng còn phụ thuộc version của project và archive naming convention. Có thể thêm version:

~~~groovy
tasks.register('apiDocsZip', Zip) {
    dependsOn tasks.named('asciidoctor')
    from(renderedDocs)
    archiveBaseName = 'registration-api-docs'
    archiveVersion = project.version.toString()
    archiveClassifier = 'html'
    destinationDirectory = layout.buildDirectory.dir('distributions')
}
~~~

### 3.1. Nối vào lifecycle build

Nếu mọi build đều cần artifact tài liệu, có thể nối task vào assemble:

~~~groovy
tasks.named('assemble') {
    dependsOn tasks.named('apiDocsZip')
}
~~~

Khi đó:

~~~bash
./gradlew clean build
~~~

sẽ tạo cả artifact ứng dụng và artifact docs theo dependency graph. Nếu tài liệu chỉ cần trong release job, giữ apiDocsZip là task riêng để tránh render docs ở mọi build local.

### 3.2. Tạo artifact snippets riêng

Nếu module khác cần include snippet, có thể tạo ZIP thứ hai:

~~~groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.register('apiSnippetsZip', Zip) {
    dependsOn tasks.named('test')
    from(snippetsDir)
    archiveBaseName = 'registration-api-snippets'
    archiveVersion = project.version.toString()
    archiveClassifier = 'snippets'
    destinationDirectory = layout.buildDirectory.dir('distributions')
}
~~~

Đảm bảo test task và Spring REST Docs cùng ghi vào build/generated-snippets. Ví dụ:

~~~java
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
~~~

Snippets ZIP giữ nguyên cây thư mục theo document identifier. Không đưa snippets vào HTML ZIP một cách mặc định; chỉ phát hành khi consumer cần tái sử dụng chúng.

## 4. Maven: đóng gói HTML bằng Assembly Plugin

Giả sử Asciidoctor Maven Plugin render tài liệu vào target/generated-docs. Tạo descriptor src/assembly/api-docs.xml:

~~~xml
<assembly xmlns="http://maven.apache.org/ASSEMBLY/2.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/ASSEMBLY/2.2.0
          https://maven.apache.org/xsd/assembly-2.2.0.xsd">
    <id>api-docs</id>
    <formats>
        <format>zip</format>
    </formats>
    <includeBaseDirectory>false</includeBaseDirectory>
    <fileSets>
        <fileSet>
            <directory>${project.build.directory}/generated-docs</directory>
            <outputDirectory>/</outputDirectory>
        </fileSet>
    </fileSets>
</assembly>
~~~

Gắn Maven Assembly Plugin ở phase package:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-assembly-plugin</artifactId>
    <version>${maven.assembly.plugin.version}</version>
    <executions>
        <execution>
            <id>package-api-docs</id>
            <phase>package</phase>
            <goals>
                <goal>single</goal>
            </goals>
            <configuration>
                <descriptors>
                    <descriptor>src/assembly/api-docs.xml</descriptor>
                </descriptors>
                <finalName>${project.artifactId}-${project.version}</finalName>
                <appendAssemblyId>true</appendAssemblyId>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Property maven.assembly.plugin.version phải được khai báo trong POM hoặc parent POM. Phase package diễn ra sau prepare-package; nếu Asciidoctor đã được gắn ở prepare-package, HTML có sẵn trước khi assembly chạy.

Chạy:

~~~bash
mvn clean package
~~~

Kiểm tra output trong target/, ví dụ:

~~~text
target/
├── generated-snippets/
├── generated-docs/
└── registration-api-1.0.0-api-docs.zip
~~~

Tên file thực tế phụ thuộc finalName, appendAssemblyId và cấu hình plugin. Hãy kiểm tra archive sau build để xác nhận index.html nằm ở root mong muốn.

## 5. Đính kèm artifact docs vào Maven publication

Nếu cần publish docs cùng tọa độ Maven của ứng dụng, có thể attach ZIP làm artifact phụ bằng Build Helper Maven Plugin:

~~~xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <version>${build.helper.plugin.version}</version>
    <executions>
        <execution>
            <id>attach-api-docs</id>
            <phase>package</phase>
            <goals>
                <goal>attach-artifact</goal>
            </goals>
            <configuration>
                <artifacts>
                    <artifact>
                        <file>${project.build.directory}/${project.build.finalName}-api-docs.zip</file>
                        <type>zip</type>
                        <classifier>api-docs</classifier>
                    </artifact>
                </artifacts>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đường dẫn file phải khớp chính xác file ZIP do Assembly Plugin tạo. Artifact có classifier api-docs, phân biệt với JAR chính của ứng dụng.

Khi release pipeline chạy mvn deploy, Maven có thể publish artifact chính cùng artifact phụ lên repository đã cấu hình. Kiểm tra package/local staging trước rồi mới đưa vào quy trình phát hành đã được phê duyệt.

## 6. Upload artifact trong CI

Sau khi build tạo ZIP/HTML/PDF, CI cần upload đúng đường dẫn. Ví dụ với GitHub Actions:

~~~yaml
name: Build API documentation

on:
  pull_request:
  push:
    branches: [main]

jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Build documentation
        run: ./gradlew clean test asciidoctor apiDocsZip

      - name: Upload documentation artifact
        uses: actions/upload-artifact@v4
        with:
          name: registration-api-docs
          path: build/distributions/registration-api-docs-*.zip
          if-no-files-found: error
          retention-days: 14
~~~

Ví dụ giả định project có task apiDocsZip và archive path khớp pattern. Nếu dùng Maven, thay lệnh build và đường dẫn artifact tương ứng, ví dụ mvn clean package và target/*-api-docs.zip.

if-no-files-found: error giúp job thất bại nếu build không tạo artifact. Nếu không có bước này, pipeline có thể báo thành công dù không có tài liệu để tải xuống.

### 6.1. Artifact của CI và artifact phát hành

Không phải artifact nào upload từ CI cũng là artifact public:

| Nơi lưu | Mục đích | Vòng đời |
| --- | --- | --- |
| CI job artifact | Review pull request, tải kết quả build, debug | Có thể retention ngắn |
| Release asset | Tài liệu gắn với phiên bản phát hành | Lưu theo chính sách release |
| Maven/Gradle repository | Chia sẻ artifact theo coordinates/version | Theo chính sách repository |
| Static hosting | Cung cấp website tài liệu cho người dùng | Theo version hoặc alias |

Pull request có thể upload HTML ZIP để reviewer xem trước. Chỉ release job sau khi merge/tag mới publish vào kho phát hành hoặc website public.

## 7. Kiểm tra artifact trước khi upload hoặc publish

Không chỉ kiểm tra task build trả exit code 0. Hãy kiểm tra nội dung archive:

~~~bash
unzip -l build/distributions/registration-api-docs-*.zip
~~~

Giải nén vào thư mục tạm và xác nhận:

- Có index.html ở vị trí người dùng sẽ mở.
- CSS, JavaScript, hình ảnh và các trang con có trong archive.
- Các link nội bộ không trỏ về đường dẫn máy developer.
- Không thiếu trang do include snippet lỗi.
- Artifact không chứa build/, target/, log test hoặc file tạm ngoài ý muốn.

Có thể thêm bước shell đơn giản trong CI:

~~~bash
test -f build/docs/asciidoc/index.html
test -f build/distributions/registration-api-docs-html.zip
~~~

Điều chỉnh path theo cấu hình thật. Kiểm tra file tồn tại là bước cơ bản; với website lớn, nên thêm link checker hoặc smoke test sau khi giải nén.

## 8. Version, provenance và tính tái lập

Tài liệu phải gắn với đúng phiên bản API mà nó mô tả. Artifact nên mang version ứng dụng hoặc commit:

~~~text
registration-api-1.4.0-api-docs.zip
registration-api-1.4.0-api-snippets.zip
~~~

Các nguyên tắc:

1. Sinh docs từ cùng commit/tag dùng để build ứng dụng.
2. Dùng chung version property của ứng dụng khi đặt tên artifact.
3. Chạy clean build trong release job để không lấy snippet cũ.
4. Lưu commit SHA và version vào metadata của release hoặc artifact.
5. Không dùng alias latest làm định danh duy nhất cho artifact bất biến.

Nếu HTML được deploy dưới đường dẫn version, ví dụ /docs/1.4.0/, người dùng có thể tra cứu tài liệu cũ theo đúng phiên bản API. Alias /docs/latest/ có thể trỏ tới version mới nhất nhưng không thay thế archive versioned.

## 9. Bảo vệ dữ liệu trong tài liệu generated

Snippet được tạo từ request/response test, do đó dữ liệu fixture có thể xuất hiện trong artifact. Trước khi phát hành:

- Dùng dữ liệu giả lập, không dùng token, mật khẩu hoặc thông tin khách hàng thật.
- Kiểm tra header Authorization, cookie và các giá trị nhạy cảm có được mask hay không.
- Không ghi log hoặc payload bí mật vào request/response snippet.
- Kiểm tra file đính kèm và nội dung multipart nếu test có upload.
- Giới hạn quyền truy cập nếu artifact chứa endpoint nội bộ hoặc chi tiết chưa công khai.

Nếu cần ẩn dữ liệu, cấu hình preprocessors của Spring REST Docs trong test để loại bỏ hoặc thay thế header/body phù hợp trước khi ghi snippet. Không sửa tay file generated sau khi build để che dữ liệu; cần sửa test/configuration và sinh lại artifact.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| ZIP rỗng | Đóng gói trước Asciidoctor hoặc sai source directory | Thêm dependency/phase và kiểm tra output path |
| ZIP thiếu CSS/hình ảnh | Chỉ lấy index.html | Đóng gói toàn bộ thư mục HTML |
| CI báo thành công nhưng không có artifact | Path upload sai hoặc task package chưa chạy | Bật lỗi khi không tìm thấy file và xác minh archive |
| Maven không attach được ZIP | Đường dẫn file hoặc classifier không khớp | Đối chiếu Assembly output với Build Helper |
| Docs không đúng version | Build từ commit khác hoặc snippet cũ | Dùng clean build và metadata version/commit |
| Artifact lộ dữ liệu nhạy cảm | Fixture chứa secret hoặc không preprocess request/response | Dùng dữ liệu giả và cấu hình masking trong test |
| Link hỏng sau khi giải nén | Archive thiếu tài nguyên hoặc base directory sai | Kiểm tra cấu trúc ZIP và relative links |
| Snippet nội bộ bị phát hành ngoài ý muốn | Đóng gói toàn bộ generated-snippets | Chỉ publish HTML/PDF; snippets là artifact riêng nếu cần |

## 11. Bài tập thực hành

Trong một Spring REST Docs project, tạo artifact HTML cho endpoint GET /orders/{id}.

1. Viết MockMvc test sinh request và response snippets.
2. Cấu hình Asciidoctor render vào build output directory.
3. Với Gradle, tạo task apiDocsZip; với Maven, tạo Assembly descriptor và gắn execution sau phase render.
4. Cấu hình CI chạy clean build, test, render và upload ZIP.
5. Kiểm tra archive có index.html, CSS và các trang cần thiết.
6. Đặt tên artifact theo version ứng dụng và lưu commit SHA.
7. Rà soát snippet để bảo đảm không có token, cookie hoặc dữ liệu thật.
8. Tạo release staging artifact và xác nhận tài liệu có thể mở sau khi giải nén.

**Tiêu chí hoàn thành:** Artifact được tạo sau khi test và render thành công; có đủ tài nguyên để đọc; version/commit truy nguyên được; CI báo lỗi khi thiếu artifact; dữ liệu trong snippet an toàn để phân phối.

## Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Gradle User Manual — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Apache Maven Assembly Plugin — Usage](https://maven.apache.org/plugins/maven-assembly-plugin/usage.html)
- [Build Helper Maven Plugin — Attach Artifact](https://www.mojohaus.org/build-helper-maven-plugin/attach-artifact-mojo.html)
- [GitHub Actions — Uploading Build Artifacts](https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts)
