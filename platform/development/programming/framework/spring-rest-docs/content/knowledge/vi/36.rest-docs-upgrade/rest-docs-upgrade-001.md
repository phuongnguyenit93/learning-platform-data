# Đọc yêu cầu phiên bản Spring REST Docs

## Mục tiêu bài học

Khi nâng cấp **Spring REST Docs**, việc đầu tiên không phải là đổi số phiên bản dependency rồi chạy build. Cần xác định phiên bản đích yêu cầu JDK, Spring Framework, Spring Boot, build tool và test integration nào; đọc release notes, migration notes và API thay đổi; sau đó kiểm chứng bằng một nhánh nâng cấp nhỏ.

Bài học thuộc chương **Nâng cấp** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng bằng các bài kiểm thử HTTP với **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown rồi tích hợp vào build và CI.

Sau bài học, bạn có thể:

- Xác định đúng phiên bản hiện tại và phiên bản mục tiêu của Spring REST Docs.
- Đọc release notes, migration guide, Javadoc và dependency metadata có liên quan.
- Kiểm tra tương thích với JDK, Spring Framework, Spring Boot, Gradle/Maven và test integration.
- Nhận diện breaking changes, API deprecated và thay đổi template/snippet.
- Lập kế hoạch nâng cấp có thể kiểm chứng và có đường quay lui.
- So sánh snippet trước/sau nâng cấp để phát hiện thay đổi ngoài ý muốn.
- Cập nhật tài liệu và CI sau khi nâng cấp.

## 1. Vì sao phải đọc yêu cầu phiên bản trước?

Spring REST Docs chạy cùng test framework và build system của ứng dụng. Một phiên bản mới có thể:

- Thay đổi phiên bản Java tối thiểu hoặc yêu cầu framework mới hơn.
- Cập nhật API trong các artifact core và integration modules.
- Thay đổi dependency bắc cầu, plugin Asciidoctor hoặc cách cấu hình snippet.
- Loại bỏ API đã deprecated ở phiên bản trước.
- Điều chỉnh template, tên snippet hoặc định dạng output.
- Thay đổi cách tích hợp với JUnit, Spring Test hoặc test client.

Nếu chỉ đổi dependency version mà không kiểm tra các yêu cầu này, lỗi có thể xuất hiện ở compile time, test runtime, task sinh tài liệu hoặc lúc render Asciidoctor.

Quy trình an toàn bắt đầu bằng câu hỏi: **phiên bản mục tiêu yêu cầu gì, dự án hiện tại đang dùng gì, và phần nào của pipeline bị ảnh hưởng?**

## 2. Xác định phiên bản đang dùng

Trước khi đọc release notes, hãy xác định phiên bản thực tế của toàn bộ nhóm dependency REST Docs. Không chỉ xem một dòng trong build file vì version có thể được quản lý qua BOM, version catalog, property hoặc dependency management.

### 2.1. Với Gradle

Kiểm tra build.gradle hoặc build.gradle.kts, gradle/libs.versions.toml, plugin management và dependency constraints. Ví dụ:

~~~groovy
dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc:3.0.3'
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor:3.0.3'
}
~~~

Ví dụ minh họa, không phải khuyến nghị dùng một version cố định cho mọi dự án. Nếu dùng version catalog:

~~~toml
[versions]
springRestDocs = "3.0.3"

[libraries]
spring-restdocs-mockmvc = {
  module = "org.springframework.restdocs:spring-restdocs-mockmvc",
  version.ref = "springRestDocs"
}
~~~

Kiểm tra dependency đã resolve:

~~~powershell
./gradlew dependencyInsight --dependency spring-restdocs --configuration testRuntimeClasspath
~~~

dependencyInsight giúp thấy version được chọn và lý do chọn version đó, kể cả khi dependency khác kéo REST Docs vào gián tiếp. Kiểm tra đúng configuration của test đang tạo snippet.

### 2.2. Với Maven

Kiểm tra pom.xml, parent POM, BOM import, properties và dependencyManagement. Ví dụ:

~~~xml
<properties>
    <spring-restdocs.version>3.0.3</spring-restdocs.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.restdocs</groupId>
        <artifactId>spring-restdocs-mockmvc</artifactId>
        <version>3.0.3</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Kiểm tra dependency tree:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.restdocs
~~~

Đồng thời xác định phiên bản plugin Asciidoctor Maven/Gradle và thư viện được khai báo trong configuration riêng. Một build có thể compile test thành công nhưng task Asciidoctor vẫn thất bại vì extension hoặc plugin không tương thích.

### 2.3. Ghi nhận baseline

Trước khi nâng cấp, lập bảng baseline:

| Thành phần | Giá trị cần ghi |
| --- | --- |
| JDK | Version dùng compile và chạy test |
| Spring Boot | Version plugin/BOM nếu dự án dùng Boot |
| Spring Framework | Version thực tế được resolve |
| Spring REST Docs | Version của core và integration modules |
| JUnit/Spring Test | Version chạy test HTTP |
| Gradle hoặc Maven | Wrapper/version thực tế |
| Asciidoctor plugin | Plugin và version |
| Test integration | MockMvc, WebTestClient hoặc REST Assured |
| Output hiện tại | Snippet IDs, tên file, template format và thư mục output |

Baseline giúp phân biệt lỗi có sẵn với lỗi phát sinh từ nâng cấp.

## 3. Tìm tài liệu chính thức của phiên bản mục tiêu

Ưu tiên nguồn theo thứ tự:

1. **Release notes/changelog** của Spring REST Docs cho các phiên bản từ hiện tại đến mục tiêu.
2. **Migration guide** nếu dự án hoặc nhánh phiên bản có tài liệu chuyển đổi.
3. **Reference documentation** đúng version.
4. **Javadoc/API documentation** của artifact đúng version.
5. Dependency metadata/POM để xác nhận yêu cầu framework và dependency bắc cầu.
6. Issue tracker hoặc release discussion khi release notes chưa giải thích đủ một thay đổi.

Không đọc tài liệu current rồi mặc định đó là API của version đang chạy. URL tài liệu có thể trỏ tới phiên bản mới nhất trong khi dự án đang sử dụng bản cũ. Hãy mở Javadoc và reference đúng version hoặc đối chiếu artifact thực tế đã resolve.

### 3.1. Cách đọc release notes

Với từng bản phát hành nằm giữa version hiện tại và version đích, tìm các nhóm thông tin:

- New features: tính năng mới có cần thay đổi cấu hình không?
- Improvements: hành vi mặc định hoặc output có thay đổi không?
- Deprecations: API nào được đánh dấu deprecated và có phương án thay thế?
- Breaking changes: API bị xóa, đổi chữ ký hoặc đổi hành vi?
- Dependency updates: JDK/Spring/JUnit/REST Assured/Asciidoctor có yêu cầu mới?
- Bug fixes: dự án có đang phụ thuộc vào hành vi lỗi cũ không?

Không bỏ qua release notes của các version trung gian nếu nâng cấp qua nhiều minor/major release. Một breaking change có thể xuất hiện ở bản trung gian rồi được giải thích trong migration notes của bản kế tiếp.

### 3.2. Ghi chú bằng chứng cho mỗi thay đổi

Tạo bảng thay đổi trong pull request hoặc ticket:

| Chủ đề | Nguồn/version | Tác động dự án | Việc cần làm |
| --- | --- | --- | --- |
| Yêu cầu Java | Release notes/POM | JDK CI hiện tại có đáp ứng không? | Nâng JDK hoặc chọn version khác |
| MockMvc integration | Javadoc/changelog | API cấu hình có đổi không? | Cập nhật test setup |
| Snippet template | Reference/release notes | Tên/format snippet có đổi không? | Cập nhật AsciiDoc/Markdown includes |
| Asciidoctor | Dependency metadata | Plugin/extension có tương thích không? | Cập nhật plugin hoặc cấu hình |
| Deprecated API | Javadoc | Test đang gọi API nào? | Chuyển sang API thay thế |

Ghi link và số version cụ thể để reviewer có thể kiểm chứng. Tránh ghi chung chung kiểu “đã xem release notes”.

## 4. Kiểm tra tương thích toàn bộ stack

Spring REST Docs không hoạt động độc lập. Hãy kiểm tra các lớp tương thích:

| Thành phần | Cần xác nhận |
| --- | --- |
| JDK | Phiên bản tối thiểu và bytecode target |
| Spring Framework | Tương thích với Spring Test, Web MVC/WebFlux |
| Spring Boot | BOM và dependency management có chọn đúng REST Docs version không |
| JUnit | Extension/rule và test lifecycle đang dùng có tương thích không |
| MockMvc | Artifact và API cấu hình documentation |
| WebTestClient | WebFlux/Spring Test và documentation configurer |
| REST Assured | API filter và version REST Assured |
| Gradle/Maven | Wrapper, plugin DSL và toolchain |
| Asciidoctor | Plugin, extension và attribute snippet |
| Markdown renderer | Template format hoặc bước assembly hiện tại |

Không nhất thiết mọi dự án phải dùng cùng version của các thành phần này. Điều quan trọng là đối chiếu yêu cầu chính thức của version REST Docs mục tiêu với version được resolve trong chính dự án.

## 5. Phân biệt version của các artifact

Spring REST Docs có các artifact cho core và từng test integration. Ví dụ tên artifact thường gặp:

| Artifact | Vai trò |
| --- | --- |
| spring-restdocs-core | API và cơ chế nền tảng |
| spring-restdocs-mockmvc | Tích hợp MockMvc |
| spring-restdocs-webtestclient | Tích hợp WebTestClient |
| spring-restdocs-restassured | Tích hợp REST Assured |
| spring-restdocs-asciidoctor | Extension hỗ trợ tích hợp Asciidoctor |

Khi khai báo nhiều artifact, cần giữ version đồng bộ theo hướng dẫn của release. Tránh trộn core và integration modules ở những version khác nhau nếu không có chỉ dẫn rõ ràng từ nhà phát hành.

Nếu dùng Spring Boot dependency management, xác định BOM đang quản lý artifact nào. Việc thêm version trực tiếp vào một dependency có thể override version được BOM chọn và gây ra tổ hợp không được kiểm thử.

## 6. Kiểm tra thay đổi API và deprecation

Khi đọc Javadoc/release notes, tìm:

- Class hoặc method bị deprecated.
- Constructor đổi visibility hoặc bị thay thế.
- Method signature đổi kiểu tham số/return type.
- Package được đổi tên hoặc class chuyển module.
- Default behavior thay đổi.
- Integration filter/configurer có thay đổi cách khởi tạo.

Ví dụ, test có thể đang cấu hình documentation trực tiếp trong document(...), trong khi version mới khuyến nghị đặt preprocessing mặc định ở configurer. Chỉ thay đổi khi API mới đã được xác nhận trong Javadoc của version mục tiêu.

Không dựa vào blog hoặc câu trả lời cũ để kết luận method còn tồn tại. Dùng IDE navigation, compile test và Javadoc đúng artifact.

## 7. Kiểm tra thay đổi snippet và template

Một nâng cấp có thể không làm test fail nhưng vẫn làm tài liệu thay đổi:

- Tên snippet hoặc phần mở rộng file khác.
- Cách format HTTP request/response khác.
- Bảng field có thứ tự hoặc nội dung khác.
- JSON pretty-print thay đổi.
- Header được hiển thị hoặc loại bỏ khác.
- Template mặc định hoặc custom template cần cập nhật.

Trước khi nâng cấp, lưu lại một bộ snippet baseline đại diện cho các loại operation:

~~~text
baseline-snippets/
├── orders-get/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   └── response-fields.adoc
└── orders-create/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-fields.adoc
    └── response-fields.adoc
~~~

Sau nâng cấp, sinh lại snippet vào output sạch rồi so sánh. Phân loại diff:

1. Thay đổi có chủ đích theo release.
2. Thay đổi do fixture/test hoặc API contract.
3. Thay đổi formatting/template không ảnh hưởng nội dung.
4. Thay đổi bất thường cần điều tra.

Không cập nhật baseline chỉ để làm diff biến mất. Mỗi thay đổi cần có lý do và reviewer hiểu tác động.

## 8. Lập kế hoạch nâng cấp theo từng bước

Một kế hoạch có thể kiểm chứng:

1. Ghi lại baseline version và kết quả build hiện tại.
2. Chọn version đích dựa trên yêu cầu JDK/framework và chính sách hỗ trợ của dự án.
3. Đọc tất cả release notes/migration notes giữa version hiện tại và đích.
4. Liệt kê API deprecated, breaking changes và artifact cần đồng bộ.
5. Cập nhật dependency/plugin ở một thay đổi có phạm vi rõ.
6. Chạy compile và test REST Docs.
7. So sánh snippet baseline với snippet mới.
8. Render Asciidoctor/Markdown và kiểm tra liên kết/output.
9. Chạy CI trên JDK và môi trường build mà dự án hỗ trợ.
10. Ghi lại thay đổi và cách quay lui nếu có sự cố.

Nếu có nhiều major version cách nhau, cân nhắc nâng cấp qua các mốc trung gian được tài liệu hỗ trợ. Việc đi từng bước giúp xác định release nào gây thay đổi khi có lỗi.

## 9. Ví dụ kiểm tra version trong Gradle

Giả sử dự án quản lý version qua version catalog:

~~~toml
[versions]
springRestDocs = "3.0.3"

[libraries]
spring-restdocs-mockmvc = {
  module = "org.springframework.restdocs:spring-restdocs-mockmvc",
  version.ref = "springRestDocs"
}
~~~

Khi nâng cấp, thay version tại một nơi duy nhất theo version đã được xác nhận tương thích:

~~~toml
[versions]
springRestDocs = "VERSION_TARGET"
~~~

VERSION_TARGET chỉ là placeholder. Không copy placeholder vào build thực tế. Cần chọn version cụ thể từ release notes và xác nhận tương thích trước khi commit.

Sau đó kiểm tra:

~~~powershell
./gradlew dependencyInsight --dependency spring-restdocs --configuration testRuntimeClasspath
./gradlew clean test
./gradlew asciidoctor
~~~

Nếu build có task riêng cho WebTestClient hoặc REST Assured, chạy cả các test/task đó. clean test không chứng minh Asciidoctor hoặc custom Markdown assembly hoạt động.

## 10. Ví dụ kiểm tra version trong Maven

Với Maven, quản lý version qua property giúp cập nhật tập trung:

~~~xml
<properties>
    <spring-restdocs.version>3.0.3</spring-restdocs.version>
</properties>
~~~

Sau khi chọn version cụ thể:

~~~bash
mvn clean test
mvn verify
mvn dependency:tree -Dincludes=org.springframework.restdocs
~~~

verify chỉ chạy đúng các plugin/task được khai báo trong lifecycle dự án. Kiểm tra pom.xml để xác nhận bước tạo tài liệu thực sự được nối vào lifecycle; không mặc định Maven tự chạy Asciidoctor chỉ vì dependency đã có mặt.

## 11. Đánh giá rủi ro và đường quay lui

Trước khi merge nâng cấp, trả lời:

- Nếu REST Docs compile fail, dependency nào thay đổi?
- Nếu snippet thay tên, những file AsciiDoc/Markdown nào cần cập nhật?
- Nếu plugin Asciidoctor không tương thích, có thể tách việc nâng cấp plugin khỏi REST Docs không?
- Nếu output tài liệu thay đổi, thay đổi đó có phản ánh contract hay chỉ là formatting?
- Có thể quay về version trước bằng một revert rõ ràng không?

Giữ diff nâng cấp tập trung. Tránh đồng thời refactor toàn bộ test, đổi template, đổi build tool và nâng cấp REST Docs nếu không có lý do. Khi nhiều thay đổi độc lập được trộn, rất khó xác định nguyên nhân của lỗi.

## 12. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Compile fail sau nâng cấp | API bị xóa/đổi chữ ký hoặc JDK không đủ | Đọc migration notes/Javadoc, cập nhật call site hoặc chọn version tương thích |
| NoSuchMethodError lúc chạy test | Core và integration artifacts lệch version hoặc dependency bắc cầu override | Kiểm tra dependencyInsight/dependency tree và đồng bộ version |
| Test pass nhưng Asciidoctor fail | Plugin/extension hoặc snippet path thay đổi | Kiểm tra task, extension dependency và include path |
| Không tìm thấy snippet | Identifier, tên file hoặc output directory khác | So sánh output mới và cập nhật includes có chủ đích |
| Field table thay đổi | Template/version hoặc descriptor thay đổi | Đọc diff và xác nhận payload/descriptor |
| Build local pass, CI fail | JDK, wrapper, Maven/Gradle hoặc cache khác | Pin toolchain và dùng wrapper trong CI |
| Dependency version không như khai báo | BOM, constraint hoặc transitive dependency chọn version khác | Dùng dependencyInsight/tree để tìm nguồn chọn |
| Markdown render lỗi | Template format hoặc extension không được hỗ trợ | Xác nhận renderer và template của version mục tiêu |
| Nâng cấp nhiều version cùng lúc khó debug | Không kiểm tra từng mốc thay đổi | Chia bước theo release/migration guide |
| Diff snippet quá lớn | Fixture động hoặc preprocessing thay đổi | Chuẩn hóa fixture, so sánh theo operation và phân loại diff |

## 13. Bài thực hành

Chọn một dự án Spring REST Docs đang có test MockMvc hoặc REST Assured.

Yêu cầu:

1. Ghi lại JDK, Spring Boot, Spring Framework, REST Docs, JUnit, build tool và Asciidoctor plugin hiện tại.
2. Chọn một version REST Docs mục tiêu và ghi nguồn release notes/reference/Javadoc.
3. Lập bảng yêu cầu tương thích và breaking changes cho từng release cần đi qua.
4. Kiểm tra version thực tế đã resolve bằng Gradle dependencyInsight hoặc Maven dependency:tree.
5. Tạo baseline snippet cho ít nhất một GET và một POST operation.
6. Nâng cấp dependency trong một thay đổi riêng, đồng bộ core và integration artifacts theo hướng dẫn chính thức.
7. Chạy test, sinh lại snippet và so sánh diff.
8. Render tài liệu Asciidoctor/Markdown và kiểm tra includes, field table, link.
9. Chạy pipeline trên JDK/toolchain được dự án hỗ trợ.
10. Ghi lại cách rollback và những thay đổi phải thực hiện trong lần nâng cấp tiếp theo.

**Tiêu chí hoàn thành:** version đích có nguồn xác nhận; dependency thực tế được resolve đúng; test và tài liệu đều build; mọi thay đổi snippet được giải thích; CI tái tạo được kết quả.

## Ghi nhớ

Đọc yêu cầu phiên bản là bước bắt buộc trước khi nâng cấp Spring REST Docs. Xác định baseline thực tế, đọc release notes và migration notes của từng mốc, kiểm tra JDK/Spring/build tool/test integration, đồng bộ các artifact và rà soát API deprecated. Đừng chỉ xác nhận test compile: cần sinh lại snippet, so sánh output và render Asciidoctor/Markdown. Một thay đổi nâng cấp tốt có phạm vi rõ, bằng chứng tương thích cụ thể, CI tái tạo được và đường quay lui minh bạch.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs Releases](https://github.com/spring-projects/spring-restdocs/releases), [Spring REST Docs API Javadoc](https://docs.spring.io/spring-restdocs/docs/current/api/), [Spring Boot Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html), [Gradle dependencyInsight](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html) và [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/).
