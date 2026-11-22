# Đưa snippet vào artifact hoặc tài liệu phát hành

## 1. Phân biệt snippet trung gian và tài liệu phát hành

Spring REST Docs tạo **snippet** từ các bài kiểm thử HTTP. Các tệp như http-request.adoc, http-response.adoc, request-fields.adoc, curl-request.adoc là đầu vào để biên soạn tài liệu. Chúng thường nằm trong build/generated-snippets (Gradle) hoặc target/generated-snippets (Maven).

Tài liệu phát hành thường là sản phẩm đã được render, ví dụ HTML hoặc PDF. Luồng tạo artifact:

~~~text
MockMvc / WebTestClient / REST Assured tests
                    |
                    v
        generated-snippets/
                    |
                    v
       AsciiDoc source + includes
                    |
                    v
             Asciidoctor
                    |
                    v
        rendered API documentation
                    |
                    v
          release artifact / CI
~~~

Hai loại đầu ra có mục đích khác nhau:

| Đầu ra | Dùng để làm gì? | Phù hợp cho người dùng API? |
| --- | --- | --- |
| Generated snippets | Dữ liệu trung gian để biên soạn, kiểm tra hoặc tái sử dụng | Thường không nên phát hành riêng lẻ |
| HTML | Tra cứu trực tiếp, host trên website hoặc portal | Có |
| PDF | Tài liệu tải xuống, lưu trữ hoặc gửi kèm release | Có |
| AsciiDoc nguồn | Duy trì tài liệu có thể build lại | Phù hợp với nhóm phát triển |
| JAR/ZIP chứa docs | Phân phối tài liệu cùng version ứng dụng | Có, nếu cấu trúc và cách truy cập rõ ràng |

Trong module **SPRING_REST_DOCS**, test HTTP là nguồn kiểm chứng request/response; snippet được biên soạn thành tài liệu Asciidoctor/Markdown rồi tích hợp build/CI. Khi đóng gói, cần quyết định artifact nào phục vụ người dùng API và artifact nào phục vụ nhóm phát triển tái tạo tài liệu.

## 2. Chọn nội dung đưa vào artifact

Trước khi cấu hình Gradle hoặc Maven, xác định mục đích phân phối.

### 2.1. Chỉ phát hành HTML

Đây là lựa chọn phù hợp khi tài liệu được host trên web hoặc portal nội bộ. Người đọc mở index.html và điều hướng qua các trang API.

~~~text
api-docs/
├── index.html
├── images/
├── css/
└── ...
~~~

Artifact chỉ cần chứa thư mục HTML đã render và tài nguyên đi kèm. Không cần đưa toàn bộ snippet vào ZIP/JAR nếu người dùng chỉ cần đọc tài liệu.

### 2.2. Phát hành PDF

PDF phù hợp với tài liệu cần tải xuống hoặc lưu trữ cùng release. PDF cần được render từ AsciiDoc bằng backend/toolchain hỗ trợ PDF, sau đó đưa tệp PDF vào artifact. Không đổi đuôi HTML thành PDF; đây là hai bước render khác nhau.

### 2.3. Phát hành snippets hoặc AsciiDoc nguồn

Snippet có ích khi đội tích hợp muốn xem ví dụ request/response dạng AsciiDoc hoặc curl, đội phát triển muốn tái sử dụng snippet để biên soạn tài liệu tổng hợp, hoặc cần lưu bằng chứng kiểm thử.

Trong trường hợp đó, đóng gói snippets thành ZIP hoặc artifact nội bộ riêng, giữ cấu trúc thư mục theo document identifier. Không phát hành snippet rời rạc mà không có hướng dẫn về version, đường dẫn và cách include.

AsciiDoc nguồn có thể được lưu cùng artifact nếu người nhận cần build lại tài liệu. Cần cung cấp các tài nguyên và cấu hình cần thiết; chỉ gửi một file .adoc trong khi thiếu include và hình ảnh sẽ không đủ để tái tạo tài liệu.

## 3. Gradle: tạo artifact ZIP cho tài liệu HTML

Giả sử task asciidoctor render tài liệu vào build/docs/asciidoc. Có thể tạo ZIP riêng:

~~~groovy
def apiDocsDir = layout.buildDirectory.dir('docs/asciidoc')

tasks.register('apiDocsZip', Zip) {
    dependsOn tasks.named('asciidoctor')
    from(apiDocsDir)
    archiveBaseName = 'registration-api-docs'
    archiveClassifier = 'html'
    destinationDirectory = layout.buildDirectory.dir('distributions')
}
~~~

Chạy:

~~~bash
./gradlew clean apiDocsZip
~~~

Kết quả có dạng:

~~~text
build/distributions/
└── registration-api-docs-html.zip
~~~

Tên file cuối cùng còn phụ thuộc version và archive naming convention của Gradle project. dependsOn bảo đảm Asciidoctor chạy trước khi ZIP lấy nội dung. from(apiDocsDir) đưa tài liệu đã render vào ZIP.

### 3.1. Đưa ZIP vào lifecycle build

Nếu muốn build thông thường tạo luôn artifact tài liệu, nối task ZIP vào assemble:

~~~groovy
tasks.named('assemble') {
    dependsOn tasks.named('apiDocsZip')
}
~~~

Khi đó:

~~~bash
./gradlew clean build
~~~

sẽ chạy các task cần thiết theo dependency graph và tạo ZIP docs. Chỉ nối vào assemble nếu mọi lần build đều cần artifact này; nếu tài liệu nặng hoặc chỉ phát hành theo release, giữ task riêng để build nhanh không phải render docs mỗi lần.

### 3.2. Phân phối HTML dưới dạng JAR classifier

Nếu hệ thống phát hành đã quen với Maven repository hoặc Gradle publication, có thể đóng gói tài liệu HTML thành JAR có classifier:

~~~groovy
tasks.register('apiDocsJar', Jar) {
    dependsOn tasks.named('asciidoctor')
    from(apiDocsDir)
    archiveBaseName = 'registration-api'
    archiveClassifier = 'api-docs'
}

artifacts {
    archives tasks.named('apiDocsJar')
}
~~~

JAR ở đây chỉ là container để phân phối HTML và tài nguyên. Người nhận cần giải nén để mở index.html; ZIP thường dễ hiểu hơn khi artifact chủ yếu là website tĩnh.

Với Gradle publishing hiện đại, khai báo artifact trong publication phù hợp với repository đích thay vì phụ thuộc cấu hình archives cũ của một số project. Cấu hình publication cụ thể tùy plugin maven-publish và quy ước phát hành của nhóm.

## 4. Gradle: đóng gói generated snippets riêng

Nếu nhóm cần chia sẻ snippet để module docs khác dùng lại, có thể tạo ZIP riêng:

~~~groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.register('snippetsZip', Zip) {
    dependsOn tasks.named('test')
    from(snippetsDir)
    archiveBaseName = 'registration-api-snippets'
    archiveClassifier = 'snippets'
    destinationDirectory = layout.buildDirectory.dir('distributions')
}
~~~

Task test phải được cấu hình output đúng thư mục này và Spring REST Docs phải ghi snippet vào cùng vị trí:

~~~groovy
tasks.named('test') {
    outputs.dir snippetsDir
}
~~~

Ví dụ test dùng:

~~~java
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
~~~

ZIP snippets giữ cấu trúc identifier:

~~~text
registration-api-snippets.zip
└── registrations/
    └── create/
        ├── http-request.adoc
        ├── http-response.adoc
        └── ...
~~~

Không gộp ZIP snippets vào ZIP HTML một cách mặc định. Chỉ đưa vào khi người nhận thực sự cần dữ liệu trung gian; nếu không, artifact phát hành sẽ lớn hơn và có thể lộ chi tiết test nội bộ không cần thiết.

## 5. Maven: đóng gói HTML bằng Assembly Plugin

Giả sử Asciidoctor Maven Plugin render HTML vào target/generated-docs. Có thể dùng Maven Assembly Plugin để tạo ZIP từ thư mục đó. Tạo descriptor src/assembly/api-docs.xml:

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

Khai báo execution của Assembly Plugin ở phase package hoặc gọi goal sau khi Asciidoctor đã chạy:

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

Các property version cần được quản lý trong POM hoặc parent POM. Quan trọng là phase package chạy sau phase prepare-package trong lifecycle chuẩn, nơi execution Asciidoctor đã được gắn để render docs.

Kết quả có thể có dạng:

~~~text
target/
├── generated-snippets/
├── generated-docs/
└── registration-api-1.0.0-api-docs.zip
~~~

Đường dẫn chính xác phụ thuộc cấu hình plugin và tên artifact. Kiểm tra file ZIP sau build để bảo đảm index.html nằm ở vị trí mong đợi, không bị thêm một lớp thư mục ngoài ý muốn.

## 6. Maven: attach tài liệu như artifact phụ

Nếu repository phát hành dùng Maven coordinates, có thể attach ZIP tài liệu làm artifact phụ để người dùng tải theo cùng groupId/artifactId/version:

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

Artifact phụ có classifier api-docs, nhờ đó không nhầm với JAR ứng dụng. Tên file được attach phải khớp đúng output của Assembly Plugin; nếu hai plugin tạo tên khác nhau, quá trình attach sẽ thất bại.

Sau khi cấu hình đúng, mvn deploy có thể publish artifact chính cùng artifact phụ lên repository Maven theo lifecycle. Kiểm tra package/local staging trước rồi mới đưa vào quy trình phát hành đã được phê duyệt.

## 7. Đưa tài liệu vào release pipeline

Một pipeline điển hình:

~~~text
Compile
  |
  v
Run HTTP documentation tests
  |
  v
Generate REST Docs snippets
  |
  v
Render Asciidoctor HTML/PDF
  |
  v
Package API docs artifact
  |
  v
Verify archive contents
  |
  v
Publish with application release
~~~

CI nên chạy test và render tài liệu trong cùng một build để artifact phản ánh đúng commit đang phát hành. Ví dụ:

~~~bash
# Gradle
./gradlew clean test asciidoctor apiDocsZip

# Maven
mvn clean verify
~~~

Nếu Maven assembly được gắn ở phase package, dùng mvn clean package hoặc phase muộn hơn. Nếu artifact được attach và publish ở deploy, chỉ chạy mvn deploy trong release job đã có bước kiểm tra và quyền phát hành tương ứng.

### 7.1. Kiểm tra nội dung artifact

Trước khi publish, xác nhận:

- Có index.html hoặc PDF ở vị trí root mong muốn.
- CSS, JavaScript, hình ảnh và trang con vẫn nằm đúng cấu trúc tương đối.
- Không thiếu trang do include lỗi hoặc test không chạy.
- Version/commit của docs khớp version ứng dụng.
- Artifact không chứa file tạm, log test, secret hoặc dữ liệu môi trường.
- Nếu đóng gói snippets, cấu trúc document identifier được giữ nguyên.

Nên có bước kiểm tra archive tự động, ví dụ liệt kê ZIP và kiểm tra sự tồn tại của index.html. Nếu tài liệu được host trên web, có thể kiểm tra link nội bộ sau khi giải nén vào staging directory.

## 8. Versioning và tính tái lập

Tài liệu API là một phần của hợp đồng công khai. Nên phát hành cùng version với API hoặc ghi rõ commit/version API mà tài liệu mô tả.

1. Dùng cùng version property với ứng dụng để đặt tên docs artifact.
2. Sinh docs từ đúng commit/tag release.
3. Không lấy snippet của build cũ để render tài liệu cho commit mới.
4. Dùng clean build khi tạo release artifact.
5. Lưu artifact phát hành trong cùng hệ thống lưu trữ release để có thể truy xuất lại.

Ví dụ tên artifact:

~~~text
registration-api-1.4.0-api-docs.zip
registration-api-1.4.0-api-snippets.zip
~~~

Không dùng latest làm định danh duy nhất cho tài liệu lưu trữ. Có thể có alias latest trên website, nhưng artifact bất biến nên mang version cụ thể.

## 9. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| ZIP rỗng | Task đóng gói chạy trước Asciidoctor hoặc sai source directory | Thêm dependency/phase đúng và kiểm tra output directory |
| ZIP thiếu CSS/hình ảnh | Chỉ copy file HTML gốc, không lấy tài nguyên render | Đóng gói toàn bộ thư mục output Asciidoctor |
| Archive có thư mục lồng không mong muốn | Assembly outputDirectory hoặc includeBaseDirectory chưa đúng | Kiểm tra cấu trúc ZIP và chỉnh descriptor |
| Artifact phụ không được publish | Chưa attach artifact hoặc sai classifier/file path | Kiểm tra build-helper execution và file tồn tại |
| Docs không cùng version ứng dụng | Dùng version hard-code riêng hoặc build từ commit khác | Dùng chung version property và build từ release tag |
| Snippet cũ lọt vào release | Không clean output hoặc test không tạo lại đủ snippet | Chạy clean test trước render và package |
| CI có HTML nhưng release không có ZIP | Task ZIP không nằm trong lifecycle/CI command | Thêm task vào build/release pipeline |
| Snippet nội bộ bị phát hành ngoài ý muốn | Đóng gói cả generated-snippets không chọn lọc | Chỉ publish HTML/PDF; tạo artifact snippets riêng khi có nhu cầu |

## 10. Bài tập thực hành

Trong một Spring REST Docs project, tạo tài liệu HTML cho endpoint GET /orders/{id} và đóng gói thành artifact riêng.

Thực hiện:

1. Viết MockMvc test sinh request/response snippet.
2. Cấu hình Asciidoctor render vào thư mục build output.
3. Với Gradle, tạo task ZIP phụ thuộc asciidoctor; với Maven, dùng Assembly Plugin đóng gói thư mục HTML sau phase render.
4. Đặt tên artifact theo artifactId, version và classifier api-docs.
5. Nếu cần phân phối snippet cho module docs khác, tạo artifact api-snippets riêng và giữ nguyên cấu trúc identifier.
6. Chạy clean build và kiểm tra archive có index.html, CSS, hình ảnh và các trang cần thiết.
7. Kiểm tra version docs trùng version release API.

**Tiêu chí hoàn thành:** Artifact tài liệu được tạo sau khi test và render thành công; cấu trúc archive có thể mở/host được; version khớp API; snippet trung gian chỉ được phát hành khi có nhu cầu rõ ràng.

## Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Gradle User Manual — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Gradle User Manual — Publishing](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Apache Maven Assembly Plugin — Usage](https://maven.apache.org/plugins/maven-assembly-plugin/usage.html)
- [Build Helper Maven Plugin — Attach Artifact](https://www.mojohaus.org/build-helper-maven-plugin/attach-artifact-mojo.html)
- [Asciidoctor Maven Plugin — Usage](https://docs.asciidoctor.org/maven-tools/latest/plugin/usage/)
