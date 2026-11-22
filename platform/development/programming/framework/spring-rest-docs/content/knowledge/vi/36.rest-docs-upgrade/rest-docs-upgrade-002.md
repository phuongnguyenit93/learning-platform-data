# Đối chiếu Spring Boot và Spring Framework tương thích

## 1. Vì sao cần đối chiếu phiên bản?

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ test HTTP dùng MockMvc, WebTestClient hoặc REST Assured. Test sinh snippet cho request, response, payload, header, parameter và multipart part; Asciidoctor/Markdown biên soạn snippet thành tài liệu.

Khi nâng cấp, không thể chỉ thay version Spring REST Docs rồi giả định toàn bộ build tương thích. Các thành phần liên quan gồm Java runtime, Spring Boot, Spring Framework, Spring Test, REST Docs integration, Asciidoctor plugin/AsciidoctorJ và Gradle/Maven wrapper.

Mục tiêu là xác định các phiên bản thực tế được resolve, so sánh với yêu cầu của release mục tiêu rồi nâng cấp có kiểm soát.

## 2. Quan hệ Spring Boot – Spring Framework

Spring Boot cung cấp dependency management để chọn các phiên bản Spring Framework đã được kiểm thử cùng release train. Khi dùng Spring Boot parent POM hoặc BOM, thông thường không cần khai báo version riêng cho các module spring-core, spring-context, spring-webmvc hay spring-test.

| Spring Boot generation | Spring Framework generation thường đi cùng |
| --- | --- |
| Boot 2.x | Framework 5.x |
| Boot 3.x | Framework 6.x |
| Boot 4.x | Framework 7.x |

Bảng chỉ mô tả quan hệ major generation. Không suy ra patch/minor cụ thể; tra BOM của đúng Spring Boot release. Các bản minor/patch trong cùng generation có thể khác nhau theo release train.

Nếu tự override một module Framework, project có thể tạo tổ hợp mà Boot chưa kiểm thử, ví dụ spring-webmvc và spring-test lệch version hoặc spring-core khác generation.

**Nguyên tắc:** chọn Spring Boot release phù hợp Java và yêu cầu sản phẩm; để BOM quản lý Spring Framework trừ khi có lý do kỹ thuật rõ ràng và đã xác minh.

## 3. Các chiều tương thích cần kiểm tra

| Thành phần | Điều cần xác minh |
| --- | --- |
| Java runtime/toolchain | Boot, Framework, REST Docs và build plugin có hỗ trợ Java này không |
| Spring Boot | Release train, BOM và plugin version |
| Spring Framework | Các module được BOM resolve có cùng generation và bộ version nhất quán không |
| Spring REST Docs | Release hỗ trợ Spring Framework/test stack đang dùng |
| Spring Test | Tương thích với Framework và test integration |
| Test client | MockMvc, WebTestClient hoặc REST Assured integration đúng ứng dụng |
| Asciidoctor plugin | Tương thích với AsciidoctorJ và Java |
| AsciidoctorJ | Version extension Spring REST Docs yêu cầu |
| Gradle/Maven | Wrapper và plugin version đáp ứng yêu cầu Boot/plugin |

Một số thay đổi có thể compile thành công nhưng thất bại khi test hoặc Asciidoctor tạo HTML. Kiểm tra cần gồm dependency resolution, compile/test, snippet generation và documentation packaging.

## 4. Dùng Spring Boot BOM làm nguồn phiên bản

### 4.1. Maven với Spring Boot parent

Ví dụ Maven dùng Spring Boot parent:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.x.y</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
    <spring-restdocs.version>4.x.y</spring-restdocs.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.restdocs</groupId>
        <artifactId>spring-restdocs-mockmvc</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Version 3.x.y và 4.x.y là placeholder, không phải một cặp tương thích được bảo đảm. Chọn REST Docs theo tài liệu của release đó và Java/Framework stack của project. Boot parent/BOM thường quản lý version starter và Spring Framework; không pin riêng từng module nếu không có chủ đích.

### 4.2. Maven không dùng Boot parent

Nếu project có parent POM riêng, import Boot BOM trong dependencyManagement:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

BOM quản lý dependency nằm trong danh sách của nó. Plugin version và dependency ngoài BOM vẫn cần quản lý riêng.

### 4.3. Gradle

Ví dụ Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.x.y'
    id 'io.spring.dependency-management' version '1.x.y'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc:4.x.y'
}
```

Boot plugin kết hợp dependency management plugin có thể sử dụng BOM tương ứng. Nếu dùng Gradle native platform/BOM, cấu hình platform rõ ràng và tránh nhiều cơ chế override cùng lúc. Thay placeholder bằng version được hỗ trợ bởi môi trường build.

## 5. Xác định version Maven resolve

Không chỉ đọc pom.xml; dependency có thể đến từ starter, transitive dependency, parent hoặc profile.

```bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw dependency:tree -Dincludes=org.springframework
./mvnw dependency:tree -Dincludes=org.springframework.restdocs
```

Effective POM thể hiện cấu hình sau khi kế thừa parent, import BOM và áp dụng profile. Dependency tree cho biết version được chọn và đường đi dependency.

Kiểm tra:

- spring-core, spring-context, spring-webmvc và spring-test có cùng release train không?
- Version đến từ Boot BOM hay project override?
- REST Docs integration có đúng test scope không?
- Có dependency cũ được kéo vào bởi thư viện khác không?

Maven resolve thành công không chứng minh tổ hợp được Spring Boot hỗ trợ; cần so sánh với BOM và release notes.

## 6. Xác định version Gradle resolve

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-restdocs --configuration testRuntimeClasspath
```

Đọc kết quả để biết version được chọn, dependency yêu cầu version và rule tác động đến resolution. Nếu thấy force, strictly, constraint hoặc resolution rule, xác minh chúng có chủ đích và còn cần thiết không.

Không dùng force chỉ để làm dependency tree trông đồng nhất. Tốt hơn là sửa nguồn version ở BOM/platform hoặc dependency management.

## 7. Đối chiếu REST Docs với test stack

| Test client | Integration |
| --- | --- |
| MockMvc | spring-restdocs-mockmvc |
| WebTestClient | spring-restdocs-webtestclient |
| REST Assured | spring-restdocs-restassured |

Chọn integration theo test client thực tế. Không trộn artifact core/extension của các release khác nhau.

Ví dụ Maven:

```xml
<dependency>
    <groupId>org.springframework.restdocs</groupId>
    <artifactId>spring-restdocs-mockmvc</artifactId>
    <version>4.x.y</version>
    <scope>test</scope>
</dependency>
```

Version REST Docs phải tương thích với Spring Framework và Spring Test. Khi chuyển Boot generation, đọc migration/release notes để kiểm tra thay đổi API, Java baseline và yêu cầu test framework.

## 8. Đối chiếu Asciidoctor plugin và AsciidoctorJ

REST Docs test có thể chạy thành công nhưng bước HTML thất bại nếu plugin/extension không tương thích. Phân biệt Asciidoctor Maven/Gradle plugin (tích hợp vào build), AsciidoctorJ (runtime xử lý AsciiDoc) và spring-restdocs-asciidoctor (extension cung cấp thuộc tính/macro REST Docs).

Ví dụ Maven plugin dependencies:

```xml
<plugin>
    <groupId>org.asciidoctor</groupId>
    <artifactId>asciidoctor-maven-plugin</artifactId>
    <version>3.2.0</version>
    <dependencies>
        <dependency>
            <groupId>org.asciidoctor</groupId>
            <artifactId>asciidoctorj</artifactId>
            <version>3.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.restdocs</groupId>
            <artifactId>spring-restdocs-asciidoctor</artifactId>
            <version>4.x.y</version>
        </dependency>
    </dependencies>
</plugin>
```

Đây là ví dụ cấu hình, không phải bộ version bắt buộc cho mọi release. Đối chiếu Getting Started của đúng REST Docs version để chọn Maven plugin/AsciidoctorJ tương thích.

## 9. Ma trận kiểm tra trước khi nâng cấp

| Thành phần | Đang dùng | Mục tiêu | Nguồn xác nhận |
| --- | --- | --- | --- |
| Java | Toolchain/runtime | Version được Boot release hỗ trợ | Boot system requirements |
| Spring Boot | Effective POM/plugin version | Boot release đích | Boot release notes/BOM |
| Spring Framework | Dependency tree | Version do Boot BOM quản lý | Boot BOM |
| Spring REST Docs | Dependency tree | Release tương thích | REST Docs release notes |
| Spring Test | Dependency tree | Version cùng Framework train | Boot BOM |
| Asciidoctor plugin | POM/Gradle plugin | Version hỗ trợ AsciidoctorJ | Plugin documentation |
| AsciidoctorJ | Plugin dependency | Version REST Docs extension hỗ trợ | REST Docs Getting Started |
| Maven/Gradle | Wrapper version | Version được Boot/plugin hỗ trợ | Build tool requirements |

Không điền version mục tiêu bằng phỏng đoán. Với mỗi version, ghi nguồn xác nhận và kết quả resolve sau thay đổi.

## 10. Quy trình nâng cấp có kiểm soát

1. **Ghi nhận baseline:** Java, Boot, dependency tree, wrapper và test result hiện tại.
2. **Chọn Boot release:** xác minh Java baseline, support window và migration notes.
3. **Để Boot quản lý Framework:** bỏ override không cần thiết.
4. **Chọn REST Docs release:** đối chiếu yêu cầu Framework/Spring Test và integration.
5. **Chọn Asciidoctor plugin/J:** theo hướng dẫn của đúng REST Docs release.
6. **Nâng wrapper/plugin:** xác minh Gradle/Maven version đáp ứng yêu cầu.
7. **Resolve dependencies:** chạy effective POM/dependency tree hoặc Gradle dependencyInsight.
8. **Chạy test:** compile và chạy REST Docs tests để sinh snippets.
9. **Biên soạn tài liệu:** chạy Asciidoctor và xác minh HTML.
10. **Package:** tạo JAR/WAR và kiểm tra docs trong archive.
11. **Smoke test:** chạy ứng dụng, gọi URL docs cùng một asset.
12. **Ghi lại matrix:** cập nhật version thực tế và nguồn xác nhận.

Nâng từng nhóm có quan hệ gần nhau; tránh thay đồng thời Java, Boot, REST Docs, Asciidoctor và build tool nếu không cần. Dependency tree và bước kiểm tra riêng giúp khoanh vùng nguyên nhân.

## 11. Lệnh xác minh toàn pipeline

Maven:

```bash
./mvnw -version
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw dependency:tree -Dincludes=org.springframework,org.springframework.restdocs
./mvnw clean test
./mvnw prepare-package
./mvnw package
```

Gradle:

```bash
./gradlew --version
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration testRuntimeClasspath
./gradlew clean test asciidoctor
./gradlew bootJar
```

Kiểm tra archive:

```bash
jar tf target/application.jar
jar tf build/libs/application.jar
```

Nếu docs được nhúng, tìm BOOT-INF/classes/static/docs/index.html và assets. Nếu docs là artifact riêng, kiểm tra ZIP cùng metadata version/source revision.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| NoSuchMethodError trong Spring | Framework modules lệch version hoặc thư viện cũ | Xem dependency tree, bỏ override và dùng BOM |
| ClassNotFoundException trong test | Integration/test dependency thiếu hoặc scope sai | Thêm đúng REST Docs integration ở test scope |
| MockMvc test lỗi sau nâng Boot | Thay đổi Spring Test/MVC API hoặc cấu hình | Đọc migration notes, cập nhật test setup |
| WebTestClient integration lỗi | Sai integration hoặc WebFlux/test stack version | Đối chiếu REST Docs release và dependency tree |
| REST Assured test lỗi runtime | REST Docs integration lệch version | Kiểm tra artifact integration và transitive dependencies |
| Asciidoctor không load extension | Plugin dependency thiếu hoặc sai version | Kiểm tra spring-restdocs-asciidoctor trên plugin classpath |
| AsciidoctorJ báo API không tương thích | Plugin và AsciidoctorJ không cùng compatibility range | Dùng version theo Getting Started |
| Maven resolve version bất ngờ | Parent/BOM/profile/nearest dependency ảnh hưởng | Kiểm tra effective POM và dependency tree |
| Gradle chọn version khác mong muốn | Constraint, force hoặc transitive dependency | Dùng dependencyInsight |
| Local được nhưng CI lỗi | JDK/wrapper/cache/profile khác nhau | Pin toolchain/wrapper, clean build và so sánh resolution |

## 13. Bài thực hành

Một service đang dùng Spring Boot và Spring REST Docs. Hãy chuẩn bị nâng cấp:

1. Ghi nhận Java, Boot, Framework, REST Docs, AsciidoctorJ và build tool versions.
2. Chạy Maven effective POM/dependency tree hoặc Gradle dependencies/dependencyInsight.
3. Xác định Framework version nào đến từ Boot BOM và có override nào không.
4. Tra yêu cầu Java/Framework của Boot release mục tiêu.
5. Tra REST Docs release tương thích với Framework/Spring Test mục tiêu.
6. Chọn Asciidoctor plugin và AsciidoctorJ theo hướng dẫn REST Docs.
7. Thay version ở nguồn quản lý tập trung, không pin riêng từng Framework module.
8. Chạy REST Docs test và xác minh snippets.
9. Chạy Asciidoctor, kiểm tra HTML.
10. Package JAR và xác minh docs/assets trong archive.
11. Chạy ứng dụng, kiểm tra URL docs.
12. Lưu compatibility matrix cùng source revision.

**Tiêu chí hoàn thành:** giải thích Boot BOM quản lý Framework; xác định version thực tế bằng dependency tools; đối chiếu Java, Framework, REST Docs và Asciidoctor; nâng cấp không tạo dependency drift; xác minh test, HTML và package.

## 14. Câu hỏi tự kiểm tra

**1. Vì sao không nên pin version từng module Spring Framework?**

Spring Boot BOM quản lý bộ version đã được kiểm thử cùng release train. Pin riêng có thể tạo tổ hợp module không đồng bộ.

**2. Boot 3.x luôn dùng cùng một patch version Framework không?**

Không. Phải xem BOM của đúng Boot release; không suy ra patch/minor từ major generation.

**3. Maven dùng lệnh nào để xem cấu hình sau khi kế thừa parent/BOM?**

help:effective-pom.

**4. Gradle dùng lệnh nào để biết vì sao spring-core được chọn version hiện tại?**

dependencyInsight --dependency spring-core --configuration testRuntimeClasspath.

**5. Vì sao cần kiểm tra Spring REST Docs và AsciidoctorJ cùng nhau?**

Extension REST Docs chạy trên classpath Asciidoctor; plugin và AsciidoctorJ không tương thích có thể làm biên soạn thất bại dù test sinh snippets thành công.

**6. Dependency tree resolve thành công có chứng minh tổ hợp được hỗ trợ không?**

Không. Cần đối chiếu BOM, release notes và yêu cầu tương thích chính thức.

**7. Kiểm tra nào chứng minh upgrade hoàn tất?**

REST Docs tests sinh snippets, Asciidoctor tạo HTML, package chứa docs/assets và ứng dụng phục vụ URL đúng.

## Tài liệu tham khảo

- [Spring Boot — Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/index.html): dependency versions được quản lý bởi từng release Boot.
- [Spring Boot — Managing Dependencies](https://docs.spring.io/spring-boot/reference/using/build-systems.html): dùng parent/BOM và dependency management.
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): dependency, test integration và cấu hình Asciidoctor theo release.
- [Spring Framework — Overview and Requirements](https://docs.spring.io/spring-framework/reference/overview.html): yêu cầu và thông tin nền tảng Framework.
- [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/): dependency tree và công cụ phân tích dependency.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencies và dependencyInsight.

